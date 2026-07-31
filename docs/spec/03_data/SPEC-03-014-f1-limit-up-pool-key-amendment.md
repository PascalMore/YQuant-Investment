# SPEC-03-014 F1 Amendment: `sentiment.limit_up_pool` 业务键契约规范

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-31 |
| 版本号 | V0.1 |
| 父文档 | SPEC-03-014（V0.19） |
| 来源 RFC | RFC-03-014-F1（本契约的 RFC 裁定） |
| 来源 Design | DESIGN-03-014-F1（本契约的 Design 定义） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |

## 1. 校正确认

经 RFC-03-014-F1 裁定确认：`sentiment.limit_up_pool` 的正确业务唯一键为 **`{market, symbol, trade_date}`**。本 SPEC 将该裁定转为可执行契约。

## 2. Canonical 能力→键映射（修正版）

### 2.1 §0 能力与集合定义（替换 SPEC-03-014 §0 行）

```text
- **P3-C** = `03_data_ud_market_sentiment_snapshot` 市场情绪快照集合。
  Capabilities: `sentiment.market_snapshot`, `sentiment.limit_up_pool`。
  - `sentiment.market_snapshot` → `MarketSentimentSnapshot`（22 字段全市场多维快照）
  - `sentiment.limit_up_pool` → `LimitUpPoolRecord`（个股涨跌停详情）
```

### 2.2 §P1.7 唯一键表（替换 SPEC-03-014 §P1.7 行 1822-1825）

| 集合 | 业务唯一键 | Upsert 语义 |
|------|-----------|-------------|
| `03_data_ud_market_sector_snapshot` | `{market, sector_code, snapshot_date}` → `update_one(filter, {"$set": doc}, upsert=True)` | 同一键的重复写入覆盖，不保留历史版本 |
| `03_data_ud_stock_capital_flow` | `{market, symbol, trade_date}` → 同上 | `northbound_daily` 永不进入 upsert 路径 |
| `03_data_ud_market_sentiment_snapshot` — `sentiment.market_snapshot` | `{market, snapshot_date, snapshot_time}` → 同上 | 22 字段 canonical `MarketSentimentSnapshot` 为唯一写入 schema |
| `03_data_ud_market_sentiment_snapshot` — `sentiment.limit_up_pool` | `{market, symbol, trade_date}` → 同上 | `LimitUpPoolRecord` 为唯一写入 schema；与 `sentiment.market_snapshot` 共存于同一集合但文档字段集不同 |

### 2.3 §0.4 Capability → Key 表

| Capability | 域模型 | 目标 Collection | 业务唯一键 |
|------------|--------|-----------------|-----------|
| `sector.snapshot` | `SectorSnapshot` | `03_data_ud_market_sector_snapshot` | `{market, sector_code, snapshot_date}` |
| `sector.ranking` | `SectorSnapshot` | `03_data_ud_market_sector_snapshot` | `{market, sector_code, snapshot_date}` |
| `flow.capital_flow_daily` | `CapitalFlowRecord` | `03_data_ud_stock_capital_flow` | `{market, symbol, trade_date}` |
| `flow.northbound_daily` | —（恒 None） | `03_data_ud_stock_capital_flow` | `{market, symbol, trade_date}` |
| **`sentiment.market_snapshot`** | **`MarketSentimentSnapshot`** | **`03_data_ud_market_sentiment_snapshot`** | **`{market, snapshot_date, snapshot_time}`** |
| **`sentiment.limit_up_pool`** | **`LimitUpPoolRecord`** | **`03_data_ud_market_sentiment_snapshot`** | **`{market, symbol, trade_date}`** |

## 3. 凭证式映射（Writer `unique_key_for` 行为规范）

```python
# 以下映射为 canonical 规范，P3PersistenceWriter 必须遵循。
# 任何偏离导致同 collection 的 capability 间键不一致，均构成契约违规。

P3_UNIQUE_KEYS_BY_CAPABILITY: dict[str, frozenset[str]] = {
    "sector.snapshot": frozenset({"market", "sector_code", "snapshot_date"}),
    "sector.ranking": frozenset({"market", "sector_code", "snapshot_date"}),
    "flow.capital_flow_daily": frozenset({"market", "symbol", "trade_date"}),
    "flow.northbound_daily": frozenset({"market", "symbol", "trade_date"}),
    "sentiment.market_snapshot": frozenset({"market", "snapshot_date", "snapshot_time"}),
    "sentiment.limit_up_pool": frozenset({"market", "symbol", "trade_date"}),  # ← F1 确认保持
}
```

## 4. 同一集合的双键共存不变形约束

### 4.1 合规条件

两条 Capability 共享同一 MongoDB 集合时，如果业务唯一键**不同**，则满足以下全部条件为合规：

1. 两个 capability 的 upsert 使用**不同的字段集**作为 `unique_key` 参数——即 `update_one(filter=key_fields, ...)` 中的 filter 字段不同。
2. MongoDB 不施加 document-level schema 约束：集合 `03_data_ud_market_sentiment_snapshot` 在 P3-C 中无 `validator`、无 `validationLevel`，允许异构文档共存。
3. 每个 capability 的域模型 `from_dict()` 对不认识的字段使用 `pop()` 或默认值——不会因未知字段抛出。
4. `P3PersistenceWriter.get()` 查询时，业务层按 capability 判断应使用的 filter 字段集（经由 `Router._try_materialized()` 的 `P3PersistenceWriter.get(collection, filter_by_capability)` 调用链）。

### 4.2 检查清单

| # | 约束 | 验证方式 |
|---|------|---------|
| C-1 | `P3_UNIQUE_KEYS_BY_CAPABILITY` 中 `sentiment.market_snapshot` ≠ `sentiment.limit_up_pool` 的键 | 静态断言 |
| C-2 | 使用 `sentiment.market_snapshot` 键 upsert 的文档与使用 `sentiment.limit_up_pool` 键 upsert 的文档在 MongoDB 中不共享同一条记录 | mongomock dual-upsert 测试 |
| C-3 | `MarketSentimentSnapshot.from_dict(LimitUpPoolRecord.asdict())` 不抛异常（字段超集兼容） | 单元测试 |
| C-4 | `LimitUpPoolRecord.from_dict(MarketSentimentSnapshot.asdict())` 不抛异常（字段超集兼容） | 单元测试 |
| C-5 | `P3PersistenceWriter.get(collection, filter_with_market_snapshot_fields)` 只返回 MarketSentimentSnapshot 文档 | 集成测试 |

## 5. 需要修改的代码位置

### 5.1 文件：`p3_persistence_writer.py`

- `P3_UNIQUE_KEYS_BY_CAPABILITY["sentiment.limit_up_pool"]` = `frozenset({"market", "symbol", "trade_date"})` — **保持不动**（已正确）

### 5.2 文件：`test_router_p3_internal_first_materialized_read.py`

- 方法 `test_sentiment_limit_up_pool_returns_ud_materialized`（line 356-394）：需重写
  - 替换 MarketSentimentSnapshot 形状的数据为 `LimitUpPoolRecord` 形状
  - upsert key 从 `{market, snapshot_date, snapshot_time}` 改为 `{market, symbol, trade_date}`
  - 验证 Assertion 改为检查 `LimitUpPoolRecord` 字段（如 `symbol`、`trade_date`、`status`），而非 `limit_up_count`

### 5.3 文件：`router.py`

- 注释 line 161（`per-stock limit-up/down pool`）正确，无需修改
- 如未来追加，可在 `_TA_CN_NOT_COVERED` 的 `sentiment.limit_up_pool` 条目旁补充键标注

## 6. 禁止事项

- ❌ 不得修改 `P3_UNIQUE_KEYS_BY_CAPABILITY["sentiment.limit_up_pool"]`（已正确）
- ❌ 不得为消除「同一集合双键」添加 MongoDB collection-level validator（超出 P3-C 范围）
- ❌ 不得合并两个 capability 的域模型（MarketSentimentSnapshot 和 LimitUpPoolRecord 语义不同，应保持分离）
- ❌ 不得创建新的索引集合（§P1.7 的索引设计在 P1 中保持冻结）
