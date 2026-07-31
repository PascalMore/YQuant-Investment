# RFC-03-014 F1 Amendment: `sentiment.limit_up_pool` 业务键契约裁定

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-31 |
| 版本号 | V0.1 |
| 父文档 | RFC-03-014（V0.19） |
| 关联 SPEC | SPEC-03-014-F1（本裁定之 SPEC） |
| 关联 Design | DESIGN-03-014-F1（本裁定之 Design） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |

## 1. 问题陈述

T3B Review（`t_2352f110`）将 `sentiment.limit_up_pool` 的业务键列为 **F1 Major**：writer 实现为 `{market, symbol, trade_date}`（`p3_persistence_writer.py:175`），但 DESIGN-03-014 §0.4 要求 `sentiment.market_snapshot` 与 `sentiment.limit_up_pool` 共享 `{market, snapshot_date, snapshot_time}`。

## 2. 证据收集

### 2.1 域模型

`sentiment.py`（`models/domain/sentiment.py`）包含两个 dataclass：

- **`MarketSentimentSnapshot`**（22 字段，line 74）：全市场情绪快照。`limit_up_pool: list[str] | None` 为嵌入字段（仅涨停股票代码列表）。Key：`{market, snapshot_date, snapshot_time}`（line 7 明确声明）。
- **`LimitUpPoolRecord`**（line 228）：涨停/跌停池个股记录。每个记录表示一只股票在某个交易日的涨跌停详情（价格、时间、封单金额、连板天数等）。docstring line 236 明确声明：**"The business unique key is `{market, symbol, trade_date}`"**。

### 2.2 现有文档

| 文档 | 章节 | 声称的 limit_up_pool 键 | 评估 |
|------|------|------------------------|------|
| DESIGN-03-014 V0.26 | §0.4（line 144） | `{market, snapshot_date, snapshot_time}` | ❌ 不完整 |
| SPEC-03-014 V0.19 | §P1.7（line 1825） | `{market, snapshot_date, snapshot_time}` | ❌ 不完整 |
| RFC-03-014 V0.19 | §5.3.1/§P1 | 仅针对 `MarketSentimentSnapshot` 的 `{market, snapshot_date, snapshot_time}` | ✅ 正确但需补充 |

### 2.3 现有代码

| 文件 | 行号 | 使用的 limit_up_pool 键 | 评估 |
|------|------|--------------------------|------|
| `p3_persistence_writer.py` | 175 | `{market, symbol, trade_date}` | ✅ 正确 |
| `test_p3_persistence_writer.py` | 55 | `SENTIMENT_UNIQUE_KEY = {market, snapshot_date, snapshot_time}` | ✅ 正确（用于 MarketSentimentSnapshot 测试） |
| `test_sentiment_limit_up_pool.py` | 93-96 | LimitUpPoolRecord 使用 `{market, symbol, trade_date}` | ✅ 正确 |
| `test_router_p3_internal_first_materialized_read.py` | 359-373 | limit_up_pool 测试使用 `{market, snapshot_date, snapshot_time}` upsert MarketSentimentSnapshot | ❌ 业务语义混淆 |

### 2.4 Router 注释

`router.py` line 160-164 注释写道：`sentiment.limit_up_pool is the per-stock limit-up/down pool — a separate capability from market_snapshot but sharing the same collection.` 该注释正确识别了 limit_up_pool 为 per-stock，但文档级映射表未同步。

## 3. 裁定

### 3.1 校正确认

**`sentiment.limit_up_pool` 的正确业务唯一键为 `{market, symbol, trade_date}`**，匹配 `LimitUpPoolRecord` 域模型。writer 代码 `p3_persistence_writer.py:175` **保持不动**。

理由：

1. **域模型权威性**：`LimitUpPoolRecord` 是 `sentiment.limit_up_pool` capability 的返回类型。其构造参数 `symbol`、`market`、`trade_date` 为必填项，docstring 显式声明这三者构成业务唯一键。
2. **集合共存语义**：`03_data_ud_market_sentiment_snapshot` 集合包含两种文档类型——MarketSentimentSnapshot（市场级聚合）和 LimitUpPoolRecord（个股级详情）。它们拥有**不同的业务唯一键**，在同一个 MongoDB 集合中通过不同的字段组合实现 upsert 隔离。这是 MongoDB schema-less 设计下的合法模式。
3. **跨集合类比**：P3-B 的 `flow.capital_flow_daily` / `flow.northbound_daily` 也共享 `03_data_ud_stock_capital_flow` 集合和 `{market, symbol, trade_date}` 键（两个 capability 的键完全一致）。Sentiment 集合的情况不同——两个 capability 有**不同**的键，必须分别声明。

### 3.2 需要修改的文档

| 文档 | 修改内容 |
|------|---------|
| DESIGN-03-014 §0.4 | capability→key 表拆分为每 capability 单行 |
| SPEC-03-014 §P1.7 | 唯一键表拆分为每 capability 单行 |
| RFC-03-014 §P1（引用处） | 补充 dual-key 说明 |

### 3.3 需要修改的测试

| 测试文件 | 修改内容 |
|---------|---------|
| `test_router_p3_internal_first_materialized_read.py:356-394` | `test_sentiment_limit_up_pool_returns_ud_materialized` 当前使用 `MarketSentimentSnapshot` 数据测试 `sentiment.limit_up_pool` 能力——这是业务语义混淆。应改用 `LimitUpPoolRecord` 形状的数据 + `{market, symbol, trade_date}` 键 |

### 3.4 不需要修改的内容

- ❌ `p3_persistence_writer.py` —— 键映射已正确
- ❌ `test_p3_persistence_writer.py` —— `TestMarketSentimentP3Writer` 正确测试 MarketSentimentSnapshot 键
- ❌ `test_sentiment_limit_up_pool.py` —— 正确使用 LimitUpPoolRecord
- ❌ `models/domain/sentiment.py` —— 域模型已正确
- ❌ `services/sentiment_service.py` —— 服务层已正确
- ❌ `router.py`（除注释一致性外）—— 路由逻辑已正确

## 4. 风险

### 4.1 数据冲突风险

在 MongoDB 层面，`{market, "2026-07-21", "close"}`（snapshot）和 `{market, "600519", "2026-07-21"}`（limit-up）是不同的文档。upsert 使用各自的键字段集，不会意外覆盖对方。**无数据冲突风险**。

### 4.2 索引设计风险

PR-DDL-P3C 创建的索引（`snapshot_date` / `snapshot_time`）对 `sentiment.limit_up_pool` 查询效率不高——limit_up_pool 查询通常按 `{market, symbol, trade_date}` 检索。若生产阶段需要，可在未来追加复合索引 `{market: 1, symbol: 1, trade_date: 1}`。P1 阶段不影响。

### 4.3 Router 测试混淆风险

`test_router_p3_internal_first_materialized_read.py` 中 `test_sentiment_limit_up_pool_returns_ud_materialized` 使用 MarketSentimentSnapshot 形状的数据 + `{market, snapshot_date, snapshot_time}` 键来测试 `sentiment.limit_up_pool` 能力。虽然技术上通过了（因为 writer 的 upsert 不校验业务语义，只按传入的 unique_key 操作），但这是**测试意图与真实业务语义的错配**。该测试应修正为使用 LimitUpPoolRecord 形状的数据 + `{market, symbol, trade_date}` 键。

### 4.4 向前兼容性

当前 Disk 中存在的数据（如果有，仅存在于 T3 开发的 mongomock 环境）使用 `{market, symbol, trade_date}` 键，与修正后的文档一致。无迁移需求。

## 5. 关联文档

- SPEC-03-014-F1: 可执行键契约规范
- DESIGN-03-014-F1: 详细设计变更与 allowlist
