# RFC-03-014 F4: `sentiment.limit_up_pool` Materialized-Read Filter 契约裁定

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-31 |
| 版本号 | V0.1 |
| 父文档 | RFC-03-014（V0.19） |
| 关联 F1 Amendment | RFC-03-014-F1（业务键裁定）、SPEC-03-014-F1、DESIGN-03-014-F1 |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 本 RFC 对应的 SPEC | SPEC-03-014-F4（本裁定之 SPEC 契约） |
| 本 RFC 对应的 Design | DESIGN-03-014-F4（本裁定之 Design 细节） |
| 触发来源 | F1 Final Review `t_587be6fb` — Major: materialized-read filter 跨市场泄漏 |

## 1. 问题陈述

F1 Final Review（`t_587be6fb`）在审查 F1 裁定（writer key `{market, symbol, trade_date}` 正确）的实现范围时，发现一个独立的 **Major** 问题：

`sentiment.limit_up_pool` 的 P3 materialized read 路径中，`_p3_filter_for()`（`router.py:587-609`）仅透传 `params`（`{"trade_date": "..."}`），而 `MarketSentimentService.get_limit_up_pool()`（`sentiment_service.py:356-370`）仅向 `params` 传入 `trade_date`——`market` 过滤字段完全丢失。

**后果**：`P3PersistenceWriter.get(collection, filter={"trade_date": "2026-07-21"})` 返回 `03_data_ud_market_sentiment_snapshot` 集合中所有匹配 `trade_date` 的记录，**不论 market 是 CN、HK、US 还是 INDEX**。这是跨市场记录泄漏风险。

**这不是 writer 的 bug**（F1 已裁定 writer 键正确），**也不是 SPEC/Design 文档层的 oversimplification**（F1 已修正 §0.4 表为逐 capability 行）。**这是 materialized-read 路径的 filter 构建不完整**——在所有已有文档中均未定义「读路径 filter 应包含哪些字段」的精确契约。

## 2. 证据链

### 2.1 调用链

```
sentiment_service.py:365-370
  get_limit_up_pool(trade_date="2026-07-21")
    → self._router.query(
        domain="sentiment",
        operation="limit_up_pool",
        security_id=SecurityId(market=Market.INDEX, symbol="limit_up_pool:2026-07-21"),
        market="CN",           # ← market 传入 query()
        params={"trade_date": "2026-07-21"},
      )

router.py:295-336 query()
  → self._resolve_market(market="CN", security_id)    # market 在这里被 resolve 为 "CN"
  → self._query_external_chain_with_cache(...)          # ← market 未传入！
    → self._try_materialized(...)                       # ← market 未传入！
      → self._p3_filter_for(security_id, domain, operation, params)
        → return dict({"trade_date": "2026-07-21"})    # ← filter 中缺少 market
```

### 2.2 关键观察

| # | 观察 | 证据 |
|---|------|------|
| 1 | `get_limit_up_pool()` 硬编码 `market="CN"` 传入 `router.query()` | `sentiment_service.py:369` |
| 2 | `security_id` 是占位符，`security_id.market = Market.INDEX` | `sentiment_service.py:358-361` |
| 3 | `query()` 通过 `_resolve_market()` 正确解析 market 为 `"CN"` | `router.py:337` |
| 4 | 解析后的 market **未传入** `_query_external_chain_with_cache()` | `router.py:400-409`（签名缺 market 参数） |
| 5 | `_p3_filter_for()` 仅透传 params | `router.py:609` — `return dict(params or {})` |
| 6 | 最终 filter 为 `{"trade_date": "2026-07-21"}`——无 market 隔离 | 组合 O4+O5 的必然结果 |

### 2.3 当前文档覆盖情况

| 文档 | 章节 | 关于 _p3_filter_for 的当前描述 | 评估 |
|------|------|--------------------------------|------|
| SPEC-03-014 V0.19 | §P1.6 | `filter = self._p3_filter_for(security_id, domain, operation, params)` | ❌ 签名缺 market |
| DESIGN-03-014 V0.26 | §P1.4.2 | `filter = self._p3_filter_for(capability, params)` | ❌ 签名缺 market |
| DESIGN-03-014 V0.26 | §P1.4.2 伪代码 | `filter = self._p3_filter_for(capability, params)` | ❌ signature 与实际代码不一致 |
| DESIGN-03-014-F1 V0.1 | §4.1 Allowlist | 未提及 _p3_filter_for | ✅ 不涉及（F1 不涉及读路径） |
| SPEC-03-014-F1 V0.1 | §5.3 `router.py` | 仅注释可选修改 | ✅ 不涉及（F1 不涉及读路径） |

## 3. 裁定

### 3.1 核心裁定

**对于 `sentiment.limit_up_pool` 的 date-level pool query 读路径，materialized-read filter 必须包含 `market` 字段。最小 filter 为 `{market, trade_date}`；如支持 single-stock 查询，扩展为 `{market, symbol, trade_date}`。**

### 3.2 派生裁定

1. **`_p3_filter_for()` 必须接受 `market` 参数**：现有签名 `(security_id, domain, operation, params)` 无法获取 `market`（因为 `security_id` 可能是占位符）。新增 `market` 参数，由调用链自上而下传递。

2. **market 来源**：使用 `router.query()` 调用时显式传入的 `market` 参数值（经 `_resolve_market()` 解析后的字符串值），**不是** `security_id.market`。`query()` → `_query_external_chain_with_cache()` → `_try_materialized()` → `_p3_filter_for()` 逐层透传。

3. **filter 构造策略**：`_p3_filter_for()` 返回的 dict 中，`market` 始终被包含（若调用者未传入，则不覆盖 `security_id.market` 默认值——但当前所有 P3 capability 的调用者均显式传入 `market`）。`params` 中的字段（如 `trade_date`）合并到 filter 中。filter = `{"market": resolved_market, **params}` 行为。

4. **仅 P3 capability 受影响**：本裁定仅作用于 `_try_materialized()` 中调用的 `_p3_filter_for()`。`_p3_filter_for()` 是 P3 专用的 helper——非 P3 capability 不由该路径走，不受影响。

5. **兼容边界**：本裁定不改变已有的 `_p3_filter_for()` 测试行为（当前测试 `test_p3_filter_for_returns_params_passthrough` 仅验证 param copy——该测试可保留但需扩展以验证 market 注入）。

### 3.3 不涉及的范围

- ❌ 不修改 writer 键（F1 裁定 `{market, symbol, trade_date}` 保持不变）
- ❌ 不修改 `LimitUpPoolRecord` 域模型
- ❌ 不修改 `sentiment_service.py` 的调用方式（`market="CN"` 硬编码在 P1 离线阶段可接受）
- ❌ 不修改其他 P3 capability 的调用链（`sector.snapshot`、`flow.capital_flow_daily` 等虽也受 `_p3_filter_for()` 影响，但它们的 `security_id` 使用真实 market——market 注入后 filter 值与现状无差异，仅增加显式 market 字段）
- ❌ 不修改非 P3 capability

## 4. 影响分析

### 4.1 对 F1 裁定的关系

F1 裁定修正了 writer 端的文档错误（dual-key collection 合并在 $\S0.4$/$\S P1.7$ 表）。**本 F4 裁定不推翻 F1**，而是补全读路径的 filter 契约——F1 修正了「写什么键」，F4 定义「按什么 filter 读」。

### 4.2 测试影响

- `test_p3_filter_for_returns_params_passthrough`（`test_router_p3_readonly.py:504`）：需扩展以验证 market 注入行为，但**不改变原测试断言**
- `test_sentiment_limit_up_pool_returns_ud_materialized`（`test_router_p3_internal_first_materialized_read.py:356`）：F1 Design $\S$3.2 的替换模板需同步增加 market 在 filter 中的验证

### 4.3 文档同步清单

| 文档 | 需更新内容 |
|------|-----------|
| SPEC-03-014 $\S$P1.6 | `_p3_filter_for()` 签名 + 伪代码 |
| DESIGN-03-014 $\S$P1.4.2 | `_p3_filter_for()` 签名 + 伪代码 + 不变形约束 |
| SPEC-03-014-F1 $\S$5.3（router.py 注释） | 可选：增加 filter 需要 market 的注释补充 |
| DESIGN-03-014-F1 $\S$4.1（Allowlist） | 追加允许修改 router.py `_p3_filter_for()` 方法 |
| RFC-03-014 $\S$P1 | 补充 materialized-read filter 的 market 必需性说明 |

## 5. 残余风险

| # | 风险 | 影响 | 缓解 |
|---|------|------|------|
| R-1 | 其他 P3 capability（sector.snapshot/ranking、flow.capital_flow_daily）的 `security_id.market` 为真实值——market 注入前后 filter 结果相同，但现有测试可能未显式校验 market 字段 | 假阴性：测试通过但无法证明 market 隔离有效 | F4 Design 中要求所有 P3 filter 测试新增 `market in filter` 断言 |
| R-2 | `query()` 调用者可能不传入 `market`（使用 `security_id.market` 默认） | `_p3_filter_for()` 收到 `market=None`，filter 中不带 market | 定义 `Query 调用契约`：所有 P3 capability 的 `query()` 调用**必须**显式传入 `market` 参数 |
| R-3 | `northbound_daily` 的 `query()` 调用尚未实现（Pascal C 已确认 fail-stop） | 新 `_p3_filter_for()` 签名对 northbound 无实际影响 | 不构成阻断 |

## 6. 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|--------|------|---------|--------|
| V0.1 | 2026-07-31 | 初始创建。F4 裁定：limit_up_pool 的 materialized-read filter 必须包含 market，`_p3_filter_for()` 需新增 market 参数。 | YQuant-Codex-Principal |
