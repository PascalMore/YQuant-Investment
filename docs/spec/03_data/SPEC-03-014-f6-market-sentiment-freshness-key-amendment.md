# SPEC-03-014 F6 Amendment: `market_sentiment` freshness canonical key 契约规范

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-08-02 |
| 版本号 | V0.1 |
| 父文档 | SPEC-03-014（V0.20） |
| 来源 RFC | RFC-03-014-F6（本契约的 RFC 裁定） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 对应冻结项 | PC-11（freshness `sentiment` vs `market_sentiment` 命名冲突） |

## 1. 校正确认

经 RFC-03-014-F6 裁定确认（Pascal 路线：冻结唯一 canonical key）：

1. **`market_sentiment`** 是 capability `sentiment.market_snapshot` 的**唯一 canonical freshness domain key**（TTL=3600s）。
2. **`sentiment_limit_up_pool`** 是 capability `sentiment.limit_up_pool` 的**独立 canonical freshness domain key**（TTL=3600s）。
3. **`sentiment`** 不是 freshness TTL key——仅是 capability domain 前缀；SPEC-03-014 §4.4 旧行 `"sentiment": 3600` **作废（superseded）**。

本 SPEC 将该裁定转为可执行契约。

## 2. Canonical freshness domain-key 映射（修正版）

### 2.1 §4.4 FreshnessPolicy 默认 TTL 表（替换 SPEC-03-014 §4.4 的 Phase 3 新增行）

```python
# Phase 3 新增 domain TTL（canonical，F6 裁定）
"flow": 43200,                 # 12h — 资金流数据日盘后刷新即可
"sector": 21600,               # 6h — 板块快照收盘后刷新即可
"market_sentiment": 3600,      # 1h — 市场级情绪快照（capability sentiment.market_snapshot；F6 canonical key）
"sentiment_limit_up_pool": 3600,  # 1h — 个股涨停池（capability sentiment.limit_up_pool；F6 canonical key）
# ⚠️ F6 裁定（RFC-03-014-F6）：`"sentiment"` 不再作为 freshness TTL key。
#    `sentiment` 仅保留为 capability domain 前缀（sentiment.market_snapshot / sentiment.limit_up_pool）。
#    禁止在 DEFAULT_TTLS 注册 `"sentiment"`（双 key/alias 会造成 freshness 漂移）。
```

### 2.2 Capability → freshness domain key 映射表

| Capability | 域模型 | freshness domain key | TTL | 语义 |
|------------|--------|----------------------|-----|------|
| `sentiment.market_snapshot` | `MarketSentimentSnapshot`（22 字段全市场多维快照） | **`market_sentiment`** | 3600 | 市场级情绪聚合快照（唯一键 `{market, snapshot_date, snapshot_time}`） |
| `sentiment.limit_up_pool` | `LimitUpPoolRecord`（个股涨跌停详情） | **`sentiment_limit_up_pool`** | 3600 | 个股级涨停池（唯一键 `{market, symbol, trade_date}`，见 SPEC-03-014-F1） |

### 2.3 其他 Phase 3 capability（不变）

| Capability | freshness domain key | TTL |
|------------|----------------------|-----|
| `sector.snapshot` / `sector.ranking` | `sector` | 21600 |
| `flow.capital_flow_daily` / `flow.northbound_daily` | `flow` | 43200 |

## 3. 旧 key 处理与兼容 / 拒绝策略

### 3.1 旧 key `sentiment`

| 层面 | 处理 |
|------|------|
| SPEC-03-014 §4.4 的 `"sentiment": 3600` 行 | **作废（superseded）**，由 §2.1 两行替代；主文档本卡最小更新完成替换 |
| capability domain 前缀（`sentiment.market_snapshot` 字符串第一段、service `DOMAIN`、router `domain` 参数、cache key 前缀 `"sentiment:market_snapshot:{date}"`） | **保留不变**——capability domain 与 freshness TTL key 是两个层级 |
| `FreshnessPolicy.DEFAULT_TTLS` | **不得注册 `"sentiment"`**（当前实现已满足） |

### 3.2 契约约束（验收断言）

| # | 约束 | 验证方式 |
|---|------|---------|
| C-1 | `"market_sentiment" in FreshnessPolicy.DEFAULT_TTLS` 且 `DEFAULT_TTLS["market_sentiment"] == 3600` | Python 断言 |
| C-2 | `"sentiment_limit_up_pool" in FreshnessPolicy.DEFAULT_TTLS` 且 `DEFAULT_TTLS["sentiment_limit_up_pool"] == 3600` | Python 断言 |
| C-3 | `"sentiment" not in FreshnessPolicy.DEFAULT_TTLS`（禁止双 key/alias） | Python 断言 |
| C-4 | `policy.get_ttl("market_sentiment") == 3600`；`policy.get_ttl("sentiment_limit_up_pool") == 3600` | Python 断言 |
| C-5 | 运行时 freshness 查表显式解析：router/service 对 `sentiment.market_snapshot` / `sentiment.limit_up_pool` 查询调用 `FreshnessPolicy.label/get_ttl` 与 `CacheManager.put` 时传入的 domain 为 canonical key，**不得**为 `sentiment`（禁止 fallback 巧合匹配 `_DEFAULT_TTL=3600`） | spy 断言（见 §5.2） |
| C-6 | SPEC-03-014 §4.4 TTL 表键名与代码 `DEFAULT_TTLS` 键名一致（`market_sentiment` / `sentiment_limit_up_pool`，无 `sentiment`） | 静态 grep |

### 3.3 明确不做（Out of Scope）

- ❌ 不修改 TTL 值（3600s 两 key 不变；`flow`/`sector` 不变）。
- ❌ 不修改 capability 字符串、`P3_COLLECTION_BY_CAPABILITY`、`P3_UNIQUE_KEYS_BY_CAPABILITY`、`_TA_CN_NOT_COVERED`。
- ❌ 不修改 cache 集合名 / cache key 格式（`"sentiment:market_snapshot:{snapshot_date}"` 等）。
- ❌ 不修改唯一键、写入 schema、refresh 三态守卫、P3 读路径只读不变量。
- ❌ 不修改 `quality/config.py`（Phase 2 独立 TTL 表，不含 sentiment 域）。
- ❌ 不引入数据迁移（freshness key 为纯配置层，无字段级变更）。
- ❌ 不创建新集合 / 索引（§P1.7 索引设计保持冻结）。

## 4. 缓存 / refresh 影响

| 路径 | 影响 |
|------|------|
| `CacheManager.put()` | `expires_at` 计算使用 `get_ttl(domain)`：修正后 sentiment 缓存显式使用 3600（此前靠 `_DEFAULT_TTL=3600` 兜底巧合相等）。**TTL 值与缓存文档结构不变**，仅查表 key 显式化 |
| `LocalMongoAdapter.get()` / `_try_materialized()` | 物化读路径的 TTL 判定同理显式化；无 schema/键变更 |
| `FreshnessPolicy.label()` | 传入 domain 从 `sentiment` 改为 canonical key 后，`from_cache=True` 分支的 TTL 判定行为不变（两者值均 3600） |
| refresh 路径（`refresh_market_sentiment_snapshot` / `refresh_limit_up_pool`） | 无影响——freshness key 不改变写入唯一键 / upsert 行为 / 三态守卫 |
| freshness 标签语义（realtime/delayed/cached/stale/empty） | 不变 |

## 5. 验收标准

### 5.1 单元测试清单（Verify 阶段）

| # | 测试 | 文件（新增/修改） | 验证命令 |
|---|------|------------------|---------|
| V-1 | canonical key ∈ DEFAULT_TTLS + TTL=3600（C-1/C-2） | `tests/test_freshness_policy.py`（修改） | `pytest` |
| V-2 | `sentiment` 不在 DEFAULT_TTLS（C-3） | `tests/test_freshness_policy.py`（修改） | `pytest` |
| V-3 | `get_ttl` 两 canonical key = 3600（C-4） | `tests/test_freshness_policy.py`（修改） | `pytest` |
| V-4 | router freshness domain 解析 spy：`sentiment.market_snapshot` 查询时 `get_ttl`/`label`/`CacheManager.put` 收到 `market_sentiment`；`sentiment.limit_up_pool` 收到 `sentiment_limit_up_pool`；均不得收到 `sentiment`（C-5） | 新增 router spy 测试（如 `tests/test_router_p3_freshness_domain.py`） | `pytest` |
| V-5 | 既有 `TestFreshnessTableSentiment` 断言继续 PASS（兼容性） | `tests/test_mapping_sentiment.py`（不改，或追加 C-3 断言） | `pytest` |
| V-6 | 全量回归 | `skills/data/unified_data/tests` | `.venv/bin/python -m pytest skills/data/unified_data/tests -q` exit 0 |

### 5.2 静态验证命令

```bash
# 1) 契约层：SPEC §4.4 canonical 键存在且无 sentiment TTL 键
grep -n '"market_sentiment"' docs/spec/03_data/SPEC-03-014-f6-market-sentiment-freshness-key-amendment.md
grep -n '"sentiment_limit_up_pool"' docs/spec/03_data/SPEC-03-014-f6-market-sentiment-freshness-key-amendment.md
# 2) 实现层与契约层键名一致
grep -n '"market_sentiment"' skills/data/unified_data/freshness.py
grep -n '"sentiment_limit_up_pool"' skills/data/unified_data/freshness.py
# 3) 主文档 drift 已清除
grep -n '"sentiment": 3600' docs/spec/03_data/SPEC-03-014-unified-data-phase-3-persistent-data-expansion.md  # 期望无输出
```

## 6. Design / Implement 最小 allowlist

### 6.1 代码（T3 Implement 候选，T2 Design 裁决最终范围）

| 文件 | 允许操作 | 约束 |
|------|---------|------|
| `skills/data/unified_data/router.py` | sentiment capability 的 freshness 查表 domain 解析为 canonical key（capability → freshness domain 派生） | 不改非 P3 capability 路径；不改 Step 4 只读不变量；不改 `_materialize` 行为 |
| `skills/data/unified_data/services/sentiment_service.py` | 仅当解析逻辑落在 service 层时修改；否则不动 | 三态守卫、22 字段 canonical 写入契约不变 |
| `skills/data/unified_data/freshness.py` | 可选：补注释说明 `sentiment` 非 TTL key | 表键已 canonical，无键值变更 |
| `skills/data/unified_data/tests/test_freshness_policy.py` | 追加 V-1~V-3 断言 | 不改既有 FP-001..FP-008 语义 |
| `skills/data/unified_data/tests/test_mapping_sentiment.py` | 追加 C-3（`sentiment` 不在 DEFAULT_TTLS）断言 | 既有 `TestFreshnessTableSentiment` 断言不动 |
| 新增 `skills/data/unified_data/tests/test_router_p3_freshness_domain.py` | V-4 spy 测试 | 零真实 I/O；mongomock/unittest.mock |

### 6.2 文档（T2 Design 阶段）

| 文件 | 允许操作 |
|------|---------|
| `docs/design/03_data/DESIGN-03-014-unified-data-phase-3-persistent-data-expansion.md` | §4.4 跨层标注（line 1052-1056）改为 canonical 已冻结；§11 RD-2 / PC-11 冻结解除；§0.2/§0.3 基线同步 |

### 6.3 禁止修改（Implement 阶段）

- ❌ `quality/config.py`、`cache_manager.py`、`local_mongo_adapter.py`（仅消费 `get_ttl(domain)`，由调用方修正 domain）
- ❌ `providers/*`、`models/domain/*`、`adapters/p3_persistence_writer.py`、`client.py`
- ❌ 任何 `.env`、config、requirements、SKILL.md、README、cron/systemd/webhook

## 7. 未验证事项与残余风险

| # | 事项 | 状态 |
|---|------|------|
| U-1 | 运行时 freshness domain 解析修正（§6.1 router）尚未实施——本卡只读 | 待 T3 Implement + V-4 spy 验证 |
| U-2 | DESIGN-03-014 三层同步未做 | 待 T2 Design（§6.2） |
| U-3 | 真实 Mongo / Provider 行为（PR-1/PR-4）未执行 | 待 P2 Pascal Gate |
| U-4 | `quality/config.py` 若未来覆盖 P3 域需单独裁定 | 观察项，本次不影响 |

## 8. 禁止事项

- ❌ 不得在 `DEFAULT_TTLS` 注册 `"sentiment"`（双 key/alias → freshness 漂移）。
- ❌ 不得依赖 `_DEFAULT_TTL=3600` 兜底为 sentiment 提供 TTL（fallback 巧合 → 漂移）。
- ❌ 不得合并 `market_sentiment` 与 `sentiment_limit_up_pool` 为单 key。
- ❌ 不得修改 TTL 值、capability 契约、唯一键、写入 schema、索引设计。
- ❌ 不得以本契约为由修改 `quality/config.py`（Phase 2 独立表）。
