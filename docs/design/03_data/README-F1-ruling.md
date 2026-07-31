# F1 Principal 裁断：sentiment.limit_up_pool 业务键契约漂移裁定

## 裁断结论

**`sentiment.limit_up_pool` 保持 `{market, symbol, trade_date}` 键不变。这不是 writer bug — 而是文档级 oversimplification。**

### 根因

`03_data_ud_market_sentiment_snapshot` 集合包含两种文档类型：

| 域模型 | 对应 Capability | 业务唯一键 | 语义 |
|--------|----------------|-----------|------|
| `MarketSentimentSnapshot` | `sentiment.market_snapshot` | `{market, snapshot_date, snapshot_time}` | 市场级情绪聚合快照 |
| `LimitUpPoolRecord` | `sentiment.limit_up_pool` | `{market, symbol, trade_date}` | 个股涨跌停详情 |

DESIGN-03-014 §0.4 和 SPEC-03-014 §P1.7 的键表错误地将两个 capability 合并为单行，掩盖了 dual-key 事实。writer 代码是正确的。

### 需要修正的内容

1. **文档层**（DESIGN §0.4 / SPEC §P1.7）：capability→键表拆分为逐 capability 行
2. **测试层**：`test_router_p3_internal_first_materialized_read.py:356` 的 limit_up_pool 测试使用 MarketSentimentSnapshot 数据测试 limit_up_pool 能力——业务语义混淆，需重写为 LimitUpPoolRecord 数据
3. **代码层**：**无需修改**——writer、域模型、服务层均已正确

## 交付物

三份独立文档已产出：

| 文档 | 路径 | 行数 |
|------|------|------|
| RFC | `docs/rfc/03_data/RFC-03-014-f1-limit-up-pool-key-ruling.md` | ~150 行 |
| SPEC | `docs/spec/03_data/SPEC-03-014-f1-limit-up-pool-key-amendment.md` | ~125 行 |
| Design | `docs/design/03_data/DESIGN-03-014-f1-limit-up-pool-key-amendment.md` | ~175 行 |

## 后续任务建议

建议按 Quick Flow 执行，3 阶段 3 task：

| 阶段 | Assignee | 范围（allowlist） |
|------|----------|------------------|
| Implement | `yquantdeveloper` | `test_router_p3_internal_first_materialized_read.py` 中 `test_sentiment_limit_up_pool_returns_ud_materialized` 方法重写（§3.2 模板）；可选 router.py 注释一致性；可选同步 DESIGN/SPEC/RFC 三父文档 |
| Verify | `yquanttester` | pytest PASS + 双 capability 隔离验证 + from_dict 跨类型兼容 |
| Review | `yquantreviewer` | 审查测试逻辑是否与 F1 裁定一致 |

**禁止实现范围**：writer、域模型、服务层、其他测试文件。
