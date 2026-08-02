# RFC-03-014 F6 Amendment: `market_sentiment` freshness canonical key 裁定

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-08-02 |
| 版本号 | V0.1 |
| 父文档 | RFC-03-014（V0.20） |
| 关联 SPEC | SPEC-03-014-F6（本裁定之 SPEC） |
| 关联 Design | DESIGN-03-014（待 T2 Design 阶段同步，见 §5） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 对应冻结项 | PC-11（RFC/SPEC/DESIGN §P0.6 / §P1.9 之 freshness 跨层命名冲突披露） |
| 标签 | #unified_data #phase3 #freshness #sentiment #pc11 |

> 编号说明：03-014 既有 amendment 标签为 f1（`sentiment.limit_up_pool` 业务键）、f4（limit_up_pool 读 filter）、p3a（sector Provider 激活）。RFC-03-014 §10.2 的 P1 Fake-only Closeout 行已使用「F1/F4/F5」作为评审发现序号，为免与新 amendment 混淆，本卡采用 **F6** 标签。F6 不是评审发现序号，而是 PC-11 裁定 amendment 序号。

## 1. 问题陈述

P0/P1 冻结项 **PC-11** 披露了 freshness domain-key 的跨层契约冲突：同一市场情绪数据在文档与实现中使用了不一致的 freshness key 命名。

- 实现层（磁盘 `skills/data/unified_data/freshness.py` `FreshnessPolicy.DEFAULT_TTLS`）使用 **`market_sentiment`**（=3600）与 **`sentiment_limit_up_pool`**（=3600）两个 key。
- 契约层（SPEC-03-014 §4.4）却声明 **`"sentiment": 3600`** 单 key。
- 三层文档（RFC §P0.6 PC-11 / §P1.9、SPEC §P0.6 PC-11、DESIGN §4.4 / §11 RD-2）一致将此冲突冻结为「仅披露、不擅自裁定」，并标记裁定时机为「P3 三层文档 finalize 前，由 Pascal 单独决断」。

Pascal 已选定路线：**冻结 `market_sentiment` 为唯一 canonical freshness key**。本 RFC 将该路线落为裁定，SPEC-03-014-F6 落为可执行契约。

## 2. 证据收集

### 2.1 实现层（磁盘事实，2026-08-02 复核）

| 文件 | 位置 | freshness key | TTL | 备注 |
|------|------|---------------|-----|------|
| `skills/data/unified_data/freshness.py` | `DEFAULT_TTLS` | `market_sentiment` | 3600 | 市场级情绪快照域 |
| `skills/data/unified_data/freshness.py` | `DEFAULT_TTLS` | `sentiment_limit_up_pool` | 3600 | 涨停池域（个股级） |
| `skills/data/unified_data/freshness.py` | `DEFAULT_TTLS` | （无 `sentiment` key） | — | 当前表不含 `sentiment` |
| `skills/data/unified_data/services/sentiment_service.py` | `DOMAIN = "sentiment"` | capability domain 前缀 | — | `sentiment.market_snapshot` / `sentiment.limit_up_pool` |
| `skills/data/unified_data/router.py` | `query()` / `_query_external_chain_with_cache()` | 运行时把 `domain`（=`"sentiment"`）传入 `FreshnessPolicy.label/get_ttl` 与 `CacheManager.put` | — | **关键事实**：运行时 freshness 查表使用 `"sentiment"`，命中 `_DEFAULT_TTL` 兜底 3600；`market_sentiment` / `sentiment_limit_up_pool` 两个表项在 sentiment capability 查询中从未被命中 |

### 2.2 契约层（磁盘事实，2026-08-02 复核）

| 文档 | 章节 | 声称 | 评估 |
|------|------|------|------|
| SPEC-03-014（V0.19） | §4.4（line 511） | `"sentiment": 3600, # 1h — 情绪数据（已有；确认值对市场级情绪仍然适用）` | ❌ 与实现表键名不一致（漂移源） |
| SPEC-03-014（V0.19） | §7 A-006（line 738） | `FreshnessPolicy flow/sector/sentiment TTL 正确注册` | ⚠️ 措辞需对齐 canonical key |
| SPEC-03-014（V0.19） | §P0.6 PC-11（line 1717）/ §P0.6 禁止（line 1723）/ §P1.9 / §P1.11 禁止（line 2043） | 命名冲突不擅自裁定；`freshness.py` 冻结 | ✅ 冻结事实，本卡解除 |
| RFC-03-014（V0.19） | §P0.6 PC-11（line 1126）/ 禁止（line 1132）/ §P1.9（line 1343-1349） | 同上 | ✅ 冻结事实，本卡解除 |
| DESIGN-03-014 | §4.4（line 1052-1056）/ §11（RD-2 等） | 披露磁盘 `market_sentiment` 与 SPEC `sentiment` 不一致；PC-11 冻结 | ✅ 冻结事实；**同步动作归 T2 Design 阶段**（本卡不修改 Design） |

### 2.3 测试层（磁盘事实，2026-08-02 复核）

| 测试文件 | 断言 | 评估 |
|---------|------|------|
| `tests/test_mapping_sentiment.py` `TestFreshnessTableSentiment` | `market_sentiment` ∈ DEFAULT_TTLS、`sentiment_limit_up_pool` ∈ DEFAULT_TTLS、两者 TTL=3600、`get_ttl` 两 key 均 3600 | ✅ 已按实现事实固定；**缺**「`sentiment` 不得作为 TTL key」断言 |
| `tests/test_freshness_policy.py` | 基础 `get_ttl`/`label` 契约 | ✅ 未涉及 sentiment key，无需语义变更 |

### 2.4 其他 active 实现 key 排查

| 表面 | 位置 | 是否受影响 |
|------|------|-----------|
| `quality/config.py` `_DEFAULT_DOMAIN_TTL` | Phase 2 QualityScorer 独立 TTL 表（market_data/financial/news/metadata/index） | ❌ 不含 sentiment 域，本次裁定不影响；若未来 QualityScorer 覆盖 P3 域需单独裁定 |
| capability domain `sentiment` | capability 字符串、`P3_COLLECTION_BY_CAPABILITY`、`_TA_CN_NOT_COVERED`、cache key 前缀（`"sentiment:market_snapshot:{date}"`） | ✅ 保留不变——capability domain 与 freshness TTL key 是两个层级 |
| cache 集合名 `03_data_ud_cache_*` | CacheManager | ✅ 不受影响 |

## 3. 裁定

### 3.1 Canonical freshness domain key 冻结

**`market_sentiment` 为 P3-C 市场级情绪快照（capability `sentiment.market_snapshot`）的唯一 canonical freshness domain key，TTL = 3600s。** 与 `sentiment_limit_up_pool`（capability `sentiment.limit_up_pool`，TTL = 3600s）**并列且互不替代**。

capability → freshness domain key → TTL 的 canonical 映射：

| Capability | 域模型 | freshness domain key | TTL | 语义 |
|------------|--------|----------------------|-----|------|
| `sentiment.market_snapshot` | `MarketSentimentSnapshot`（22 字段全市场多维快照） | **`market_sentiment`** | 3600 | 市场级情绪聚合快照 |
| `sentiment.limit_up_pool` | `LimitUpPoolRecord`（个股涨跌停详情） | **`sentiment_limit_up_pool`** | 3600 | 个股级涨停/跌停池 |

### 3.2 `sentiment_limit_up_pool` 与 `market_sentiment` 的区分

- **层级不同**：`market_sentiment` 覆盖市场级聚合（`{market, snapshot_date, snapshot_time}` 唯一键）；`sentiment_limit_up_pool` 覆盖个股级池（`{market, symbol, trade_date}` 唯一键，见 RFC-03-014-F1）。
- **TTL 语义独立**：两者当前同为 3600s，但**必须**保留独立 key——未来若个股池需要更短 TTL（盘中高频）或市场快照改为日级低频，可以互不影响地单独调整，不构成 freshness 漂移。
- **禁止合并**：不得把 `sentiment_limit_up_pool` 并入 `market_sentiment` 或 `sentiment` 单 key。

### 3.3 旧 key `sentiment` 的语义

- `sentiment` 是 **capability domain 前缀**（capability 字符串 `sentiment.market_snapshot` / `sentiment.limit_up_pool` 的第一段），在 router 的 `domain` 参数、service `DOMAIN` 常量、cache key 前缀中**继续保留**。
- `sentiment` **不是** freshness TTL key：SPEC-03-014 §4.4 的 `"sentiment": 3600` 行**作废（superseded）**，由 `market_sentiment` + `sentiment_limit_up_pool` 两行替代。
- `FreshnessPolicy.DEFAULT_TTLS` 不得注册 `"sentiment"` 键（当前实现已满足）。

### 3.4 兼容 / 拒绝策略

| # | 策略 | 说明 |
|---|------|------|
| C-1 | **禁止双 key / alias** | `DEFAULT_TTLS` 不得同时出现 `sentiment` 与 `market_sentiment`（alias 会造成 freshness 语义分裂）；`sentiment` 恒不作为 TTL key |
| C-2 | **禁止 fallback 巧合匹配** | 运行时 freshness 查表不得依赖 `_DEFAULT_TTL=3600` 兜底「恰好等于」目标 TTL。当前 `get_ttl("sentiment")` 命中兜底 3600 属巧合，必须改为显式解析到 canonical key |
| C-3 | **TTL 值不变** | `market_sentiment`=3600、`sentiment_limit_up_pool`=3600 与历史语义一致，freshness 标签（realtime/delayed/cached/stale/empty）行为不变 |
| C-4 | **capability 契约不变** | capability 字符串、`P3_COLLECTION_BY_CAPABILITY`、`P3_UNIQUE_KEYS_BY_CAPABILITY`、`_TA_CN_NOT_COVERED`、cache key 格式、唯一键、写入 schema 全部不变 |
| C-5 | **无数据迁移** | freshness key 是纯配置层（TTL 表 / 查表参数），不落为文档字段；生产集合无字段级变更，无迁移需求 |
| C-6 | **运行时解析必须显式** | router/service 对 sentiment capability 的 freshness/cache TTL 查表必须传入 canonical key（`market_sentiment` / `sentiment_limit_up_pool`），不得传 `sentiment`。这是消除「表项从未命中」的关键修正 |

### 3.5 需要修改的文档

| 文档 | 修改内容 | 阶段 |
|------|---------|------|
| SPEC-03-014 §4.4 | `"sentiment": 3600` 行替换为 `market_sentiment` + `sentiment_limit_up_pool` 两行并指向本 F6 契约 | 本卡（最小更新） |
| SPEC-03-014 §7 A-006 / §P0.6 PC-11 / §P1.9 / §P1.11 | 措辞与冻结状态对齐 | 本卡（最小更新） |
| RFC-03-014 §P0.6 / §P1.9 / 元数据 changelog | PC-11 冻结解除并指向本 F6 裁定 | 本卡（最小更新） |
| DESIGN-03-014 §4.4 / §0.2 / §11 RD-2 | 跨层标注从「不一致披露」改为「canonical 已冻结」；RD-2 冻结解除 | **T2 Design 阶段**（本卡禁止修改 Design） |

### 3.6 需要修改的代码（判定：是——最小运行时对齐）

| 文件 | 修改内容 | 是否必改 |
|------|---------|---------|
| `skills/data/unified_data/router.py` | sentiment capability 的 freshness 查表 domain 解析为 canonical key（或等价：把 freshness domain 从 capability 派生后传入 `label/get_ttl`） | **是**（消除 fallback 巧合；属运行时对齐，P0/P1 冻结已解除） |
| `skills/data/unified_data/services/sentiment_service.py` | 若解析逻辑放在 service 层则改；若集中在 router 则不动 | 视 Design 裁决 |
| `skills/data/unified_data/freshness.py` | 表键已为 canonical，可不动；仅当需要补注释说明 `sentiment` 非 TTL key | 可选 |
| `skills/data/unified_data/tests/test_mapping_sentiment.py` | 追加「`sentiment` 不在 DEFAULT_TTLS」断言 | 是（验收） |
| `skills/data/unified_data/tests/test_freshness_policy.py` | 追加 canonical key 断言（见 SPEC-03-014-F6 §5） | 是（验收） |
| 新增 router freshness domain 解析 spy 测试 | 断言 `get_ttl`/`label` 收到 `market_sentiment` / `sentiment_limit_up_pool` 而非 `sentiment` | 是（验收） |

**不需要修改**：`quality/config.py`（Phase 2 独立表）、`cache_manager.py`、`local_mongo_adapter.py`（仅消费 `get_ttl(domain)`，由调用方修正 domain）、`providers/*`、`models/domain/*`、`p3_persistence_writer.py`、`client.py`。

## 4. 风险

### 4.1 运行时 TTL 语义风险（低）

修正前 `get_ttl("sentiment")` 依赖 `_DEFAULT_TTL=3600` 兜底，与目标值巧合相等；修正后显式命中 `market_sentiment`=3600。**TTL 值与 freshness 标签行为不变**，无缓存过期时间突变风险。但若未来 `_DEFAULT_TTL` 被调低，未修正的 fallback 路径会静默缩短 sentiment 缓存有效期——这正是 C-2 禁止 fallback 巧合匹配的原因。

### 4.2 双 key 漂移风险（中，本裁定消除）

若保留 `sentiment` 与 `market_sentiment` 双 key，未来调整一个忘记另一个，会造成 freshness 行为分裂且难以排查。F6 裁定后 DEFAULT_TTLS 恒无 `sentiment`，通过测试断言（C-1）防止回归。

### 4.3 文档残留风险（低）

RFC/SPEC 主文档的 PC-11 冻结语句与 §4.4 旧行在本卡最小更新中解除/替换；DESIGN 的同步归 T2 Design 阶段。若 Design 阶段遗漏，三层文档将出现「RFC/SPEC 已决断、DESIGN 仍披露」的不一致——故本卡在 §5 明确列出 DESIGN 同步为 Design 阶段验收项。

### 4.4 向前兼容性

无数据迁移；无字段 schema 变更；无 capability/集合/索引变更；测试基线不受文档修改影响（本卡不改代码）。现有 `TestFreshnessTableSentiment` 断言（两 canonical key ∈ DEFAULT_TTLS、TTL=3600）继续成立。

## 5. 关联文档与后续

- **本卡产出**：RFC-03-014-F6（本文件）、SPEC-03-014-F6（本裁定之 SPEC）
- **本卡最小更新**：RFC-03-014 主文档（V0.19→V0.20，PC-11 解除）、SPEC-03-014 主文档（V0.19→V0.20，§4.4 修正 + PC-11 解除）
- **T2 Design 阶段（下一卡）**：
  - DESIGN-03-014 同步（§4.4 跨层标注、§11 RD-2、§0.2/§0.3 基线）
  - 运行时解析修正的精确代码 allowlist（见 SPEC-03-014-F6 §6）与测试清单
- **T3 Implement 阶段（待 Design）**：按 SPEC-03-014-F6 §6 allowlist 执行代码对齐 + 测试
