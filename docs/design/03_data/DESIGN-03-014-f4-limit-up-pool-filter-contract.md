# DESIGN-03-014 F4: `sentiment.limit_up_pool` Materialized-Read Filter 详细设计

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-31 |
| 版本号 | V0.1 |
| 来源 RFC | RFC-03-014-F4（RFC 裁定——materialized-read filter 必须包含 market） |
| 来源 SPEC | SPEC-03-014-F4（SPEC 精确契约——_p3_filter_for() 签名、调用链透传、C-1~C-8 验收清单） |
| 父 Design | DESIGN-03-014（V0.26）、DESIGN-03-014-F1 |
| 目标模块 | unified_data（`skills/data/unified_data/`） |

## 1. 裁定结论

**`_p3_filter_for()` 必须新增 `market` 参数**，并将 `market` 注入到返回的 filter dict 中。`market` 值由 `router.query()` 经 3 层调用链（`_query_external_chain_with_cache` → `_try_materialized` → `_p3_filter_for`）透传。此举消除 materialized-read 路径中缺失 market 字段导致的跨市场记录泄漏风险。

## 2. 详细设计变更

### 2.1 `router.py` 改动

#### 2.1.1 `_p3_filter_for()`（line 587-609）

**变更前**：
```python
@staticmethod
def _p3_filter_for(
    security_id: SecurityId,
    domain: str,
    operation: str,
    params: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build a business-key filter dict for ``P3PersistenceWriter.get()``.

    For P1 offline mode, the filter is a simple passthrough of
    ``params`` (the same dict the caller passes into the router).
    Future sub-stages may enrich it with additional business-key
    fields derived from ``security_id``.
    """
    return dict(params or {})
```

**变更后**：
```python
@staticmethod
def _p3_filter_for(
    security_id: SecurityId,
    domain: str,
    operation: str,
    params: Mapping[str, Any] | None,
    market: str | None = None,  # ← 新增
) -> dict[str, Any]:
    """Build a business-key filter dict for ``P3PersistenceWriter.get()``.

    The filter MUST include ``market`` to prevent cross-market record
    leakage. The ``market`` value comes from the ``query()`` call chain
    (resolved via ``_resolve_market``), not from ``security_id.market``
    (which may be a placeholder for level-pool queries).

    When ``market`` is provided, the returned filter is
    ``{"market": market, **(params or {})}``. When ``market`` is None
    (caller did not pass market), the behaviour falls back to the
    Phase 1B-B passthrough for backward compatibility.

    Args:
        security_id: The :class:`SecurityId` being queried.
        domain: The P3 domain.
        operation: The P3 operation.
        params: Caller-supplied query parameters.
        market: Resolved market string (e.g. ``\"CN\"``). Passed through
            the entire call chain from ``query()``.

    Returns:
        A ``dict`` suitable as a filter for ``P3PersistenceWriter.get()``.
    """
    filter_ = dict(params or {})
    if market is not None:
        filter_["market"] = market
    return filter_
```

#### 2.1.2 `_try_materialized()`（line 611-...）

**调用处变更**（line 686）：
```python
# 变更前
self._p3_filter_for(security_id, domain, operation, params),
# 变更后
self._p3_filter_for(security_id, domain, operation, params, market=market),
```

**签名新增** `market: str | None = None` 作为 keyword-only 参数（与既有 `capability`、`p3_writer` 并列）。

#### 2.1.3 `_query_external_chain_with_cache()`（line 857-...）

**签名新增** `market: str | None = None` 作为 keyword-only 参数（与 `force_refresh` 并列）。

**内部 `_try_materialized()` 调用处**透传 `market=market`。

#### 2.1.4 `query()`（line 295-...）

**`_query_external_chain_with_cache()` 调用处**（line 400-409）新增：
```python
result = self._query_external_chain_with_cache(
    security_id,
    capability,
    domain,
    operation,
    params_dict,
    ts,
    inherited_trace=trace,
    force_refresh=force_refresh,
    market=resolved_market,  # ← 新增
)
```

### 2.2 变更规模总表

| 文件 | 函数 | 变更 | 行数变动 |
|------|------|------|---------|
| `router.py` | `_p3_filter_for()` | 签名新增 `market` kwarg + docstring 更新 + 实现注入 market | ~5 行 |
| `router.py` | `_try_materialized()` | 签名新增 `market` kwarg + 调用处透传 + docstring | ~3 行 |
| `router.py` | `_query_external_chain_with_cache()` | 签名新增 `market` kwarg + 调用处透传 | ~3 行 |
| `router.py` | `query()` | `_query_external_chain_with_cache()` 调用处增加 `market=` | ~1 行 |
| `tests/test_router_p3_readonly.py` | `test_p3_filter_for_*` | 扩展 2 个现有测试 + 新增 2 个测试 | ~20 行 |
| `tests/test_router_p3_internal_first_materialized_read.py` | `test_sentiment_limit_up_pool_returns_ud_materialized` | F1 模板 + 新增 market/cross-market 验证 | ~5 行 |
| `docs/spec/03_data/SPEC-03-014-unified-data-phase-3-persistent-data-expansion.md` | §P1.6 | 伪代码中的 `_p3_filter_for()` 签名修正 | ~5 行 |
| `docs/design/03_data/DESIGN-03-014-unified-data-phase-3-persistent-data-expansion.md` | §P1.4.2 | 伪代码中的 `_p3_filter_for()` 签名修正 | ~5 行 |
| **总计** | | | **~47 行** |

### 2.3 数据流图

```
query(market="CN")
  │  _resolve_market() → "CN"
  ▼
_query_external_chain_with_cache(market="CN")
  │
  ▼
_try_materialized(market="CN")
  │
  ▼
_p3_filter_for(market="CN")
  │
  ▼  filter = {"market": "CN", **{"trade_date": "2026-07-21"}}
  │         = {"market": "CN", "trade_date": "2026-07-21"}
  ▼
P3PersistenceWriter.get(collection="03_data_ud_market_sentiment_snapshot",
                         filter={"market": "CN", "trade_date": "2026-07-21"})
  │
  ▼  MongoDB find(filter)：
     { $and: [
       { "market": "CN" },
       { "trade_date": "2026-07-21" }
     ]}
  │
  ▼  ✅ 返回 CN/2026-07-21 的 limit_up_pool 记录
  ❌ 不会返回 HK/2026-07-21 或 INDEX/2026-07-21 的记录
```

### 2.4 与 F1 Amendment 的关系

| F1 Amendment（DESIGN-03-014-F1） | F4 Amendment（本 Design） | 关系 |
|---------------------------------|--------------------------|------|
| 修正 writer 端文档：§0.4/§P1.7 表拆分为逐 capability 行 | 修正 read 端 filter：`_p3_filter_for()` 注入 market | 正交——F1 修写入侧，F4 修读取侧 |
| 测试：修正 `test_sentiment_limit_up_pool_returns_ud_materialized` 数据形状 | 测试：同上测试新增 market/cross-market 过滤断言 | 叠加——F1 模板基础上增加 filter 验证 |
| Allowlist：`test_router_p3_internal_first_materialized_read.py` + router.py 注释（可选） | Allowlist：追加 `router.py` (4 函数签名) + `test_router_p3_readonly.py` + 2 父文档 | F4 范围是 F1 的超集 |

## 3. Allowlist（Developer 修改范围）

### 3.1 允许修改的文件

| 文件 | 允许操作 | 约束 |
|------|---------|------|
| `router.py` | `_p3_filter_for()` 签名新增 `market` kwarg + 实现注入；`_try_materialized()` / `_query_external_chain_with_cache()` / `query()` 三处签名新增 + 透传 | 仅改这 4 个方法签名与内部调用；不修改 `_try_materialized_legacy`、不修改 `_materialize()`、不修改 `query()` 的 `resolve_market`（已有） |
| `tests/test_router_p3_readonly.py` | 扩展 `test_p3_filter_for_returns_params_passthrough` 为验证 market 参数；新增 `test_p3_filter_for_injects_market` 和 `test_p3_filter_for_none_market` | 保持原有 passthrough 断言不删，仅追加 |
| `tests/test_router_p3_internal_first_materialized_read.py` | `test_sentiment_limit_up_pool_returns_ud_materialized` 方法中追加 market 在 filter 中的断言 | 基于 F1 Design §3.2 模板叠加修改 |
| `docs/spec/03_data/SPEC-03-014-unified-data-phase-3-persistent-data-expansion.md` | §P1.6 伪代码中 `_p3_filter_for()` 签名修正 | 仅改签名相关行 |
| `docs/design/03_data/DESIGN-03-014-unified-data-phase-3-persistent-data-expansion.md` | §P1.4.2 伪代码中 `_p3_filter_for()` 签名修正 | 仅改签名相关行 |
| `docs/rfc/03_data/RFC-03-014-unified-data-phase-3-persistent-data-expansion.md` | §P1 market-必需性 scope text 补充（F4 RFC §4.3 文档同步清单）——该 RFC 已在 F1 P3-C conflation 消除更新中同步，F4 allowlist 补充仅为版本记录 | 仅限 §P1 内 market 相关说明的新增/补正；不修改已有 §5.3、§9、§13（Pascal 授权内容）、§P0 章节 |

### 3.2 禁止修改的文件

- ❌ `services/sentiment_service.py`（调用方式不变，`market="CN"` 硬编码在 P1 可接受）
- ❌ `adapters/p3_persistence_writer.py`（get/upsert 签名不变）
- ❌ `models/domain/sentiment.py`（域模型不变）
- ❌ `tests/test_p3_persistence_writer.py`（writer 测试不变——该文件为 T3-B/T3-D 预存内容，包含 4 个测试类 662 行三集合 writer round-trip 覆盖；F4 不拥有此文件，其内容作为 F1 双键共存证据由 F1 Design §4.1 认可为 F1-range 预存证据；禁止 F4 修改该文件）
- ❌ `tests/test_sentiment_limit_up_pool.py`（from_dict 测试不变）
- ❌ `providers/`、`client.py`、`cache_manager.py`、`freshness.py`
- ❌ 除上述 allowlist 外的任何文件

## 4. Tester 验证命令

### 4.1 单元测试（验证 `_p3_filter_for()` 新行为）

```bash
cd /home/pascal/workspace/yquant-investment
python3 -m pytest skills/data/unified_data/tests/test_router_p3_readonly.py \
  -k "p3_filter_for" -v
```

**预期输出**（4 个测试，全 PASS）：
- `test_p3_filter_for_returns_params_passthrough` — 保留原有断言 + 扩展验证 market 参数
- `test_p3_filter_for_injects_market` — 新增：market="CN" → filter == {"market": "CN", "trade_date": "..."}
- `test_p3_filter_for_empty_params_returns_empty_dict` — 保留
- `test_p3_filter_for_none_market` — 新增：market=None → filter 不包含 market 键

### 4.2 多市场隔离验证

```bash
python3 -m pytest skills/data/unified_data/tests/test_router_p3_internal_first_materialized_read.py \
  -k "sentiment_limit_up_pool or limit_up_pool_returns" -v
```

**预期**：CN 市场 query 只返回 CN 记录；HK/US/INDEX 记录不被返回。

### 4.3 F1 全回归

```bash
python3 -m pytest skills/data/unified_data/tests/test_router_p3_internal_first_materialized_read.py -v
python3 -m pytest skills/data/unified_data/tests/test_router_p3_readonly.py -v
python3 -m pytest skills/data/unified_data/tests/test_sentiment_limit_up_pool.py -v
python3 -m pytest skills/data/unified_data/tests/test_p3_persistence_writer.py -v
```

### 4.4 向后兼容验证

```bash
# 非 P3 capability 路径应无变化
python3 -m pytest skills/data/unified_data/tests/ -k "kline_daily or realtime_quote" -v
```

## 5. 验收标准

| # | 验收标准 | 验证方式 |
|---|---------|---------|
| A-1 | `_p3_filter_for(market="CN")` 返回包含 `"market": "CN"` 的 filter | §4.1 |
| A-2 | `_p3_filter_for(market=None)` 返回不含 market 键的 filter | §4.1 |
| A-3 | `sentiment.limit_up_pool` 查询 CN 市场时只返回 CN 记录 | §4.2 |
| A-4 | `sentiment.limit_up_pool` 查询 2026-07-21 时只返回该日期记录 | §4.2 |
| A-5 | `sentiment.market_snapshot` 与 `sentiment.limit_up_pool` 在同一集合上使用不同 filter 共存 | §4.2 |
| A-6 | `MarketSentimentSnapshot.from_dict(LimitUpPoolRecord.asdict())` 不抛异常 | `test_sentiment_limit_up_pool.py` |
| A-7 | `LimitUpPoolRecord.from_dict(MarketSentimentSnapshot.asdict())` 不抛异常 | `test_sentiment_limit_up_pool.py` |
| A-8 | 非 P3 capability 测试（kline_daily、realtime_quote）全部 PASS，零回归 | §4.4 |
| A-9 | F1 Amendment 所有测试回归 PASS | §4.3 |

## 6. Rollback

| 操作 | 命令 |
|------|------|
| 回滚 router.py 所有变更 | `git checkout -- skills/data/unified_data/router.py` |
| 回滚测试变更 | `git checkout -- skills/data/unified_data/tests/test_router_p3_readonly.py skills/data/unified_data/tests/test_router_p3_internal_first_materialized_read.py` |
| 回滚文档变更 | `git checkout -- docs/spec/03_data/SPEC-03-014-unified-data-phase-3-persistent-data-expansion.md docs/design/03_data/DESIGN-03-014-unified-data-phase-3-persistent-data-expansion.md` |
| F4 文档标记 | 本 F4 三份文档标记为 `superseded`（不退回到之前的版本，只标记无效） |

## 7. 残余风险

| # | 风险 | 影响 | 缓解 |
|---|------|------|------|
| R-1 | `_query_external_chain_with_cache()` 被 `force_refresh=True` 路径中的 `_try_cache()` 调用——需要检查 `force_refresh=True` 的 `_try_materialized` 是否也会传入 market | force_refresh 跳过 Step 2（`_try_materialized`），不走 P3 filter 路径——不受新增参数影响，但需确认代码分支不遗漏 |
| R-2 | `_query_external_chain_with_cache()` 在 `sentiment_service.py` refresh 路径中可能被直接调用（而非通过 `query()`） | P1 离线阶段 refresh 不通过 `DataRouter.query()`，而是直接调用 `P3PersistenceWriter.upsert()`——不受 `_p3_filter_for()` 变更影响 |
| R-3 | 旧测试代码使用 `_p3_filter_for` 的旧签名（4 参数） | 旧签名 `(security_id, domain, operation, params)` 均不传 `market`——`market=None` 默认值确保向后兼容，filter 中不注入 market |

## 8. Implement → Verify 任务拆分

| 阶段 | Assignee | 职责 | 交付物 |
|------|----------|------|--------|
| Implement | `yquantdeveloper` | router.py 4 函数签名变更 + 透传 + 测试扩展 | git diff + pytest §4.1~§4.3 PASS |
| Verify | `yquanttester` | 独立验证：4 项新测试 + F1 全回归 + 非 P3 向后兼容 | 测试报告（§4 全部 PASS） |

> 本 F4 变更只有 2 个阶段的 Kanban 链（Implement → Verify），对应 Quick Flow 的 T1（合并 RFC/SPEC/Design）→ T2（Implement）→ T3（Verify）中的 T2+T3。T1（RFC/SPEC/Design）已在当前任务中完成。

## 9. 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|--------|------|---------|--------|
| V0.1 | 2026-07-31 | 初始创建。F4 Design：_p3_filter_for() 新增 market 参数 + 4 层调用链透传 + C-1~C-8 验证 + 完整 allowlist。 | YQuant-Codex-Principal |
