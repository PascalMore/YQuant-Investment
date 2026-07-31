# DESIGN-03-014 F1: `sentiment.limit_up_pool` 业务键裁定详细设计

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-31 |
| 版本号 | V0.1 |
| 来源 RFC | RFC-03-014-F1（RFC 裁定） |
| 来源 SPEC | SPEC-03-014-F1（SPEC 契约） |
| 父 Design | DESIGN-03-014（V0.26） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |

## 1. 裁定结论

**`sentiment.limit_up_pool` 保持当前 writer 的 `{market, symbol, trade_date}` 键不变。** 这是 `LimitUpPoolRecord` 域模型的正确业务唯一键。DESIGN-03-014 §0.4 的 capability→键表需要修正为按 capability 逐行声明，而非按集合打包声明。

## 2. 详细设计变更

### 2.1 Capability → Collection → Key 表（替换 DESIGN-03-014 §0.4 表）

**修正前**：

| Capability | 目标 Collection | 业务唯一键 |
|------------|-----------------|-----------|
| `sentiment.market_snapshot`, `sentiment.limit_up_pool` | `03_data_ud_market_sentiment_snapshot` | `{market, snapshot_date, snapshot_time}` |

**修正后**：

| Capability | 目标 Collection | 域模型 | 业务唯一键 |
|------------|-----------------|--------|-----------|
| `sentiment.market_snapshot` | `03_data_ud_market_sentiment_snapshot` | `MarketSentimentSnapshot` | `{market, snapshot_date, snapshot_time}` |
| `sentiment.limit_up_pool` | `03_data_ud_market_sentiment_snapshot` | `LimitUpPoolRecord` | `{market, symbol, trade_date}` |

**设计依据**：

同一 MongoDB 集合容纳两种不同键异构文档，在 Phase 3 的受控离线开发模式下是安全的：
- P3PersistenceWriter 的 `upsert()` 接收调用者传入的 `unique_key` 参数，不校验文档字段与键字段的一致性——这意味着同集合自然支持异键文档共存。
- 两个 capability 的 `refresh_xxx()` 分别使用各自的键，互不干扰。
- `get()` 按调用者传入的 filter 查询——只要 filter 字段匹配正确文档类型即可。

### 2.2 数据流图

```
sentiment.market_snapshot refresh:
  Provider fetch → MarketSentimentSnapshot domain → upsert(collection, records, unique_key={market, snapshot_date, snapshot_time})

sentiment.limit_up_pool refresh:
  Provider fetch → LimitUpPoolRecord domain → upsert(collection, records, unique_key={market, symbol, trade_date})

Router _try_materialized() for sentiment.market_snapshot:
  P3PersistenceWriter.get(collection, filter={market, snapshot_date, snapshot_time})

Router _try_materialized() for sentiment.limit_up_pool:
  P3PersistenceWriter.get(collection, filter={market, symbol, trade_date})
```

## 3. 测试矩阵

### 3.1 现有测试状态

| 测试文件 | 测试类/方法 | 当前键 | 业务语义正确性 | 是否需要修改 |
|----------|------------|--------|--------------|------------|
| `test_p3_persistence_writer.py` | `TestMarketSentimentP3Writer`（line 521） | `{market, snapshot_date, snapshot_time}` | ✅ 正确测试 MarketSentimentSnapshot | 不修改 |
| `test_sentiment_limit_up_pool.py` | `TestLimitUpPoolDataclassSchema`（line 93） | `{market, symbol, trade_date}`（LimitUpPoolRecord 构造） | ✅ 正确测试 LimitUpPoolRecord | 不修改 |
| `test_router_p3_internal_first_materialized_read.py` | `test_sentiment_limit_up_pool_returns_ud_materialized`（line 356） | `{market, snapshot_date, snapshot_time}`（但以 MarketSentimentSnapshot 数据测试 limit_up_pool 能力） | ❌ 业务语义混淆 | **需要修改** |

### 3.2 需要修改的测试（line 356-394）

**问题**：`test_sentiment_limit_up_pool_returns_ud_materialized` 在 writer 中 upsert 了一条 MarketSentimentSnapshot 形状的记录（含 `limit_up_count`、`snapshot_date`、`snapshot_time`），然后使用 `sentiment.limit_up_pool` capability 来读回它。这混淆了两个能力：

1. `sentiment.limit_up_pool` 应返回 `LimitUpPoolRecord`（per-stock），不是 aggregation-level 的 `limit_up_count`
2. upsert key 应为 `{market, symbol, trade_date}`，不是 `{market, snapshot_date, snapshot_time}`

**替换内容**：

```python
def test_sentiment_limit_up_pool_returns_ud_materialized(self):
    \"\"\"``sentiment.limit_up_pool`` → materialized hit (LimitUpPoolRecord).\"\"\"
    writer = _make_writer()
    record = {
        "market": "CN",
        "symbol": "600519",
        "trade_date": "2026-07-21",
        "status": "limit_up",
        "limit_up_time": "09:30:05",
        "last_price": 150.25,
        "pct_chg": 10.0,
        "provider": "limit_up_stub",
        # Minimal fields — the row proves the upsert/get round-trip.
    }
    writer.upsert(
        collection=SENTIMENT_COLLECTION,
        records=[record],
        unique_key=frozenset({"market", "symbol", "trade_date"}),
    )
    placeholder_symbol = "limit_up_pool:2026-07-21"
    sid = SecurityId(market=Market.INDEX, symbol=placeholder_symbol)
    router, spy = _build_router_with_spy(
        writer=writer,
        capability="sentiment.limit_up_pool",
        security_id=sid,
    )
    result = router.query(
        domain="sentiment",
        operation="limit_up_pool",
        security_id=sid,
    )
    assert result.provider == "ud_materialized"
    assert result.freshness == "cached"
    assert len(spy.call_log) == 0
    assert "ud_materialized(ok)" in result.source_trace
    assert isinstance(result.data, list)
    assert result.data and result.data[0]["symbol"] == "600519"
    assert result.data[0]["trade_date"] == "2026-07-21"
```

### 3.3 P1 验收标准补充

在 SPEC-03-014 §P1.10 现有 8 项后追加：

| # | 验收标准 | 验证方式 |
|---|---------|---------|
| 9 | 同一集合中，`sentiment.market_snapshot` 与 `sentiment.limit_up_pool` 使用不同的业务唯一键 upsert 后，get 查询各自返回正确的文档 | mongomock 双 capability 隔离测试 |
| 10 | MarketSentimentSnapshot 与 LimitUpPoolRecord 的 from_dict 在对方文档数据上不抛异常 | 跨类型序列化松弛测试 |

## 4. Allowlist（Developer 修改范围）

### 4.1 允许修改的文件

| 文件 | 允许操作 | 约束 |
|------|---------|------|
| `tests/test_router_p3_internal_first_materialized_read.py` | 修改 `test_sentiment_limit_up_pool_returns_ud_materialized` 方法（§3.2 模板） | 仅改该单个方法；不修改其他 Router 测试 |
|| `router.py` | 注释一致性更新（可选） | 不修改逻辑；仅限注释。**注意**：F4 Amendment（DESIGN-03-014-F4）覆盖此行的逻辑限制——`_p3_filter_for()` 的方法签名和实现逻辑变更由 F4 Design §2.1 授权 |
|| `docs/design/03_data/DESIGN-03-014-unified-data-phase-3-persistent-data-expansion.md` | §0.4 capability→key 表拆分为逐 capability 行 | 保持同一集合名称 `03_data_ud_market_sentiment_snapshot` |
|| `docs/spec/03_data/SPEC-03-014-unified-data-phase-3-persistent-data-expansion.md` | §P1.7 唯一键表拆分 + §0 能力说明更新 | 保持 §P1.7 表的结构完整性 |
|| `docs/rfc/03_data/RFC-03-014-unified-data-phase-3-persistent-data-expansion.md` | §5.3.1 补充 dual-key 说明 | 不修改已有裁定内容 |
|| `tests/test_p3_persistence_writer.py` | **预存认可**——T3-B/T3-D 原有的三集合 writer round-trip 覆盖（`TestRefreshWritesViaP3Writer` / `TestCapitalFlowP3Writer` / `TestMarketSentimentP3Writer` + `TestAllP3CollectionsCovered`）提供 F1 双键共存的合法证据，F1 不主动修改该文件 | 仅认可为 F1 证据来源，不触发修改；禁止 F1 在该文件中新增/删除内容；该文件不受 F4 Design §3.2 prohibit list 的负面包裹——F4 不拥有该文件 |
### 4.2 禁止修改的文件

- ❌ `adapters/p3_persistence_writer.py`（键映射已正确，F1 裁定确认保持）
- ❌ `models/domain/sentiment.py`（域模型已正确）
- ❌ `services/sentiment_service.py`（服务层已正确）
- ❌ `tests/test_p3_persistence_writer.py`（TestMarketSentimentP3Writer 正确）
- ❌ `tests/test_sentiment_limit_up_pool.py`（正确）
- ❌ 除上述 allowlist 外的任何文件

### 4.3 Implement → Tester → Reviewer 任务拆分

| 阶段 | Assignee | 职责 | 交付物 |
|------|----------|------|--------|
| Implement | `yquantdeveloper` | 修改 `test_router_p3_internal_first_materialized_read.py` 中 `test_sentiment_limit_up_pool_returns_ud_materialized` 方法（按 §3.2 模板）；可选更新 router.py 注释 | git diff + pytest PASS §3.2 方法的替换 + router 注释一致性（可选） |
| Verify | `yquanttester` | 独立验证：pytest 测试通过；验证同集合双 capability upsert/get 隔离；from_dict 跨类型兼容 | 测试报告（27/27 原有 + 1 新修正 PASS） |
| Review | `yquantreviewer` | 审查改动的测试逻辑是否与 F1 裁定一致；确认 DESING/SPEC/RFC 三层文档已同步或已记录待同步 | Review PASS/REVISE |

## 5. Rollback 与兼容性

### 5.1 兼容性评估

- **写入兼容性**：writer 键 `{market, symbol, trade_date}` 与 F1 裁定一致——无写入路径需回滚。
- **读取兼容性**：`sentiment.limit_up_pool` 读路径（Router → `_try_materialized` → `P3PersistenceWriter.get`）传递的 filter 由调用者拼装，按 `{market, symbol, trade_date}` 查询——与键一致，读取正确。
- **测试兼容性**：`test_sentiment_limit_up_pool_returns_ud_materialized` 修改后仅改变数据形状和断言，不改变测试框架、fixture 注入方式或 Router 的测试基础设施。其他测试不受影响。

### 5.2 Rollback 操作

若 F1 裁定被 Pascal 退回：

1. `git checkout -- tests/test_router_p3_internal_first_materialized_read.py` 恢复原始测试
2. 恢复 router.py 注释（如果有变动）
3. 本三层文档标记为 superseded

## 6. 残余风险

| # | 风险 | 影响 | 缓解 |
|---|------|------|------|
| R-1 | `test_router_p3_internal_first_materialized_read.py` 当前测试（修改前）在 CI 中不会失败，因为它使用 `{market, snapshot_date, snapshot_time}` upsert + 读回 `sentiment.limit_up_pool`——writer 接受了这个 key。但它测试的是「快照被当作 limit_up_pool 读取」，不是真实的 limit_up_pool 业务场景 | 测试语义错误，但无功能破坏 | F1 修改后修复 |

## 7. 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|--------|------|---------|--------|
| V0.1 | 2026-07-31 | 初始创建。F1 裁定：`sentiment.limit_up_pool` 保持 `{market, symbol, trade_date}`，文档级 §0.4 表需修正。 | YQuant-Codex-Principal |
