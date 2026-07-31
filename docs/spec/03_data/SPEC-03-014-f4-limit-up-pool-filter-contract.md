# SPEC-03-014 F4: `sentiment.limit_up_pool` Materialized-Read Filter 契约

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-31 |
| 版本号 | V0.1 |
| 父文档 | SPEC-03-014（V0.19） |
| 来源 RFC | RFC-03-014-F4（本契约的 RFC 裁定） |
| 关联 F1 Amendment | SPEC-03-014-F1（业务键 F1 契约）、DESIGN-03-014-F1 |
| 目标模块 | unified_data（`skills/data/unified_data/`） |

## 1. 校正确认

经 RFC-03-014-F4 裁定确认：**`sentiment.limit_up_pool` 的 materialized-read filter 必须包含 `market` 字段**。`_p3_filter_for()` 的当前 passthrough 行为（`return dict(params or {})`）构成跨市场记录泄漏风险，必须修正为按 capability 语义构造带 market 的业务 filter。

## 2. Read-Key 契约

### 2.1 Date-Level Pool Query 的精确读键

| 查询模式 | 最小 Filter | 语义 | 适用场景 |
|---------|------------|------|---------|
| **Date-level pool**（全市场日级别涨跌停池） | `{market, trade_date}` | 返回指定市场、指定交易日所有涨跌停个股记录 | `get_limit_up_pool(trade_date="2026-07-21")` |
| **Single-stock**（个股涨跌停详情） | `{market, symbol, trade_date}` | 返回指定市场、指定标的、指定交易日的涨跌停记录 | 未来个股查询扩展 |

**Phase 3 P1 离线阶段仅实现 date-level pool 模式**。single-stock 模式定义为扩展语义——当前实现**不需要**支持，但 filter 设计不允许与 future single-stock 模式冲突。

### 2.2 读键与写键的关系

| 操作 | 键/Filter | 关系 |
|------|-----------|------|
| Write（upsert） | `{market, symbol, trade_date}` | 业务唯一键（写路径全键） |
| Read（date-level pool） | `{market, trade_date}` | 读 filter——写键的子集 |
| Read（single-stock） | `{market, symbol, trade_date}` | 读 filter——与写键一致 |

读 filter 是写键的子集或全集。date-level pool 读 filter 是写键的前缀（省略 `symbol`），因此按 `{market, trade_date}` 查询时返回所有匹配的个股记录（`LimitUpPoolRecord`）。

### 2.3 Market 字段来源与传递规范

```
router.query(market="CN", security_id=..., ...)
  │
  ▼
self._resolve_market(market, security_id) → resolved_market = "CN"
  │
  ▼ (新增参数传递链)
_query_external_chain_with_cache(security_id, capability, domain, operation, params, ts, trace, force_refresh, market=resolved_market)
  │
  ▼
_try_materialized(security_id, domain, operation, params, trace, ts, force_refresh, capability, p3_writer, market=market)
  │
  ▼
_p3_filter_for(security_id, domain, operation, params, market=market)
  │
  ▼
return {"market": market, **params}  → 例: {"market": "CN", "trade_date": "2026-07-21"}
```

**调用契约**：

1. `query()` 调用者**必须**显式传入 `market` 参数——不得依赖 `security_id.market` 默认值，因为 `sentiment.limit_up_pool` 使用 `Market.INDEX` 占位符。
2. `_resolve_market()` 将 `market` 解析为字符串（当前代码已验证 line 337 的 `_resolve_market` 已存在）。
3. 解析后的 market 字符串沿调用链透传至 `_p3_filter_for()`。
4. `_p3_filter_for()` 将 `market` 注入 filter dict：`filter = {"market": market, **(params or {})}`。
5. 当 `market` 为 `None` 时（调用者未传入），`_p3_filter_for()` 退化为当前 passthrough 行为（不注入 market）——保持向后兼容。

## 3. `_p3_filter_for()` 精确契约

### 3.1 新签名与行为

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

    For Phase 3 capabilities, the filter MUST include ``market`` to
    prevent cross-market record leakage. The ``market`` value comes from
    the ``query()`` call chain (resolved via ``_resolve_market``), not
    from ``security_id.market`` (which may be a placeholder).

    When ``market`` is provided, the returned filter is
    ``{"market": market, **(params or {})}``. When ``market`` is None
    (caller did not pass it), the behaviour falls back to the Phase 1B-B
    passthrough for backward compatibility.

    Args:
        security_id: The :class:`SecurityId` being queried.
        domain: The P3 domain.
        operation: The P3 operation.
        params: Caller-supplied query parameters.
        market: Resolved market string (e.g. ``"CN"``). Passed through
            the entire call chain from ``query()``.

    Returns:
        A ``dict`` suitable as a filter for ``P3PersistenceWriter.get()``.
    """
    filter_ = dict(params or {})
    if market is not None:
        filter_["market"] = market
    return filter_
```

### 3.2 关键约束

| # | 约束 | 违背后果 |
|---|------|---------|
| F-1 | `filter["market"]` 必须等于 `query()` 调用传入的 `market` 参数（经 resolved），不是 `security_id.market` | 跨市场泄漏 |
| F-2 | `filter["trade_date"]`（当 params 传入时）必须等于调用者传入的 `trade_date` | 跨日期泄漏 |
| F-3 | 当 `market=None` 时，filter 不包含 `"market"` 键（passthrough fallback） | 无 filter 加固——仅非 P3 capability 或旧调用者会触及 |
| F-4 | `_p3_filter_for()` 返回的 dict 必须是新对象（与 params 非同一引用） | 调用者意外修改共享 dict |
| F-5 | `_p3_filter_for()` 不得修改 params 入参 | 副作用 |

## 4. 调用链变更细化

### 4.1 `router.py` 调用链

```python
# --- query() 方法变更点 ---
def query(self, domain, operation, security_id, *, market=None, ...):
    capability = _validate_capability(domain, operation)
    resolved_market = self._resolve_market(market, security_id)  # 已有
    # ...
    result = self._query_external_chain_with_cache(
        security_id,
        capability,
        domain,
        operation,
        params_dict,
        ts,
        inherited_trace=trace,
        force_refresh=force_refresh,
        market=resolved_market,  # ← 新增参数
    )

# --- _query_external_chain_with_cache() 变更点 ---
def _query_external_chain_with_cache(
    self,
    security_id,
    capability,
    domain,
    operation,
    params,
    ts,
    *,
    inherited_trace=None,
    force_refresh=False,
    market=None,  # ← 新增参数
):
    # ... 内部 _try_materialized 调用处 ...
    result = self._try_materialized(
        security_id, domain, operation, params, trace, ts,
        force_refresh=force_refresh, capability=capability,
        p3_writer=self._p3_writer, market=market,  # ← 新增
    )

# --- _try_materialized() 变更点 ---
def _try_materialized(
    self, security_id, domain, operation, params, trace, ts,
    force_refresh=False, *, capability=None, p3_writer=None, market=None,  # ← 新增
):
    # ...
    filter = self._p3_filter_for(security_id, domain, operation, params, market=market)
    # ...
```

### 4.2 变更规模

| 方法 | 变更类型 | 影响行数 |
|------|---------|---------|
| `query()` | `_query_external_chain_with_cache()` 调用处新增 `market=` 参数 | 1 行 |
| `_query_external_chain_with_cache()` | 签名新增 `market` kwarg；`_try_materialized()` 调用处透传 | 2 行 |
| `_try_materialized()` | 签名新增 `market` kwarg；`_p3_filter_for()` 调用处透传 | 2 行 |
| `_p3_filter_for()` | 签名新增 `market` 参数；实现改为 `filter["market"] = market` | 3 行 |

**总计 8 行代码变动**（含已冻结的 `return dict` 行重写）。所有变更在 `router.py` 单个文件中。

## 5. 测试与验证清单

### 5.1 C-1~C-5 扩展（取代 SPEC-03-014-F1 §4.2 的 C-1~C-5）

| # | 约束 | 验证方式 |
|---|------|---------|
| C-1 | `_p3_filter_for()` 收到 `market="CN"` 时，返回的 filter 包含 `{"market": "CN", "trade_date": "2026-07-21"}` | 单元测试（`test_router_p3_readonly.py`） |
| C-2 | `_p3_filter_for()` 收到 `market=None` 时，返回的 filter 不包含 `"market"` 键 | 单元测试 |
| C-3 | 使用 `sentiment.limit_up_pool` 查询 CN 市场时，只返回 CN 市场的记录（不泄漏 HK/US/INDEX 的记录） | mongomock 多市场数据隔离测试 |
| C-4 | 使用 `sentiment.limit_up_pool` 查询 2026-07-21 时，只返回该日期的记录（不泄漏其他日期的记录） | mongomock 多日期数据隔离测试 |
| C-5 | `sentiment.market_snapshot` 与 `sentiment.limit_up_pool` 使用不同的 filter 共存于同一集合——各自 filter 只匹配各自文档 | mongomock 双 capability 共存测试（F1 C-2 扩展） |
| C-6 | `MarketSentimentSnapshot.from_dict(LimitUpPoolRecord.asdict())` 不抛异常 | 单元测试（F1 C-3 不变） |
| C-7 | `LimitUpPoolRecord.from_dict(MarketSentimentSnapshot.asdict())` 不抛异常 | 单元测试（F1 C-4 不变） |
| C-8 | `P3PersistenceWriter.get(collection, filter_with_market_fields)` 只返回对应 market/date 的文档 | 集成测试（F1 C-5 扩展） |

### 5.2 端到端 Verification 命令

```bash
# 1. P3 filter 单元测试
pytest -v tests/test_router_p3_readonly.py -k "p3_filter_for"

# 2. 双 capability mongomock 共存 + 多市场隔离
pytest -v tests/test_router_p3_internal_first_materialized_read.py \
  -k "sentiment_limit_up_pool or limit_up_pool_returns"

# 3. 原有 F1 测试（验证未回归）
pytest -v tests/test_router_p3_internal_first_materialized_read.py \
  -k "sentiment"

# 4. from_dict 跨类型兼容（F1 C-3/C-4）
pytest -v tests/test_sentiment_limit_up_pool.py -k "from_dict"
```

### 5.3 向后兼容验证

| 场景 | 预期行为 |
|------|---------|
| 非 P3 capability（如 `kline_daily`）的 `_try_materialized` 走 `LocalMongoAdapter`，不调用 `_p3_filter_for()` | 无变化 |
| `_p3_filter_for()` 调用时 `market=None` | 返回 passthrough filter，无 market 键 |
| 旧调用代码不传 `market` | `market=None` → passthrough fallback |
| F1 修正的 `test_sentiment_limit_up_pool_returns_ud_materialized` | 使用 `{market, trade_date}` filter + 验证 market 字段 |

## 6. 禁止事项

- ❌ 不得修改 `P3PersistenceWriter.get()` 的签名或实现（filter dict 已支持任意字段）
- ❌ 不得修改 `sentiment_service.py` 的 `get_limit_up_pool()` 签名、placeholder 行为或 `market="CN"` 硬编码（P1 离线阶段可接受）
- ❌ 不得修改其他 P3 capability 的 service 层（`sector_service.py`、`flow_service.py`）
- ❌ 不得在 `router.py` 之外的文件修改 query 方法签名（`_query_external_chain_with_cache`、`_try_materialized` 的 market 参数仅在 router.py 内部传递）
- ❌ 不得为 market 注入创建新的异常类型或日志分类
- ❌ 不得在非 P3 capability 上调用 `_p3_filter_for()`（`_p3_filter_for()` 是 P3 helper，非 P3 走 `_try_materialized_legacy`）

## 7. 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|--------|------|---------|--------|
| V0.1 | 2026-07-31 | 初始创建。F4 读路径 filter 契约：`_p3_filter_for()` 新增 `market` 参数，filter 必须包含 market；调用链透传契约；C-1~C-8 验证清单。 | YQuant-Codex-Principal |
