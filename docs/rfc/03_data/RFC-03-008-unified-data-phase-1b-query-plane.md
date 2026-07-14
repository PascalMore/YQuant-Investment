# RFC-03-008：Unified Data Phase 1B-A — 查询平面与外部降级

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-14 |
| 最后更新 | 2026-07-14 |
| 版本号 | V0.1 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-00-001（全局架构） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约）、DESIGN-03-007（详细设计） |
| 替代 RFC | 无（不替代 RFC-03-007，为其 Phase 1B 的子阶段拆分 RFC） |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #provider #router #freshness #query-plane |

### 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-14 | 初始创建。将 RFC-03-007 Phase 1B 拆分为 1B-A（查询平面）与 1B-B（持久化缓存平面），本文档定义 1B-A 的需求、边界、风险与验收。 | YQuant-Principal |

---

## 1. 执行摘要

RFC-03-007 将 Unified Data Layer 的 Phase 1B 定义为「External Provider + Cache + Freshness」。在深入 Design 阶段后发现，Phase 1B 的内容横跨两个耦合度完全不同的关切面：

1. **查询平面（Query Plane）**：ProviderRegistry 路由、DataRouter internal-first 路径编排、Tushare/AKShare provider 的能力声明与外部 fallback、FreshnessPolicy 纯计算、UnifiedDataClient 读取入口的 `provider`/`force_refresh` 语义边界。这部分 **可完全用 fake/mock/in-memory 验证，不依赖真实 Mongo 写入**。
2. **持久化缓存平面（Persistence Cache Plane）**：LocalMongoAdapter（读 `03_data_ud_*` 物化集合）、CacheManager（写 `03_data_ud_cache_*`）、Mongo 连接注入、TTL 索引。这部分 **强依赖真实 Mongo I/O 与集合管理**。

本 RFC（RFC-03-008）定义 **1B-A 查询平面**。1B-B 持久化缓存平面由后续独立 RFC/SPEC 覆盖。拆分的核心价值：让路由与降级逻辑在零 Mongo 副作用的条件下先行验证、先行 Review，把风险隔离到最小。

---

## 2. 背景与动机

### 2.1 现状

Phase 0 骨架与 Phase 1A（TA-CN read-only adapter）已交付：

- `skills/data/unified_data/` 下已有 `SecurityId`、`DataResult`、`DataProvider` ABC、`ProviderRegistry`（Phase 0 版）、`DataRouter`（Phase 0 外部 fallback 版）、`UnifiedDataClient`（14 个 Phase 1A 域入口方法）、`TA_CNMongoAdapter`（8 集合只读）。
- **当前 DataRouter 是 Phase 0 外部 fallback 版**：它只做「按 fallback chain 顺序尝试 provider」，没有 internal-first 路径编排，没有 TA-CN adapter 前置查询。
- **当前 UnifiedDataClient 有两条独立路径**：`query()` 走 Phase 0 Router（外部 provider fallback），14 个域入口方法走 TA-CN adapter 直连。两条路径之间 **没有任何编排**。
- TushareProvider 和 AKShareProvider **尚未实现**。

### 2.2 痛点

| 痛点 | 影响 |
|---|---|
| 没有 internal-first 路由编排 | 消费方无法通过单一 `query()` 接口获得「先查 TA-CN 内部，再查外部」的语义 |
| 外部 provider 未实现 | TA-CN 没覆盖的数据域（如 valuation.daily_basic、calendar.trading_days）无法获取 |
| `provider`/`force_refresh` 参数语义未定义 | Phase 1A 的 14 个入口方法没有这两个参数；`query()` 有 `provider` 但无 `force_refresh` |
| FreshnessPolicy 未实现 | DataResult 的 freshness 标签全靠硬编码（Phase 1A 固定 `"delayed"`），无法按域自动计算 |
| 两条路径割裂 | 消费方需要知道「哪个域走 TA-CN、哪个域走 Router」，认知负担高 |

### 2.3 为什么拆分 1B-A 与 1B-B

| 维度 | 1B-A 查询平面（本 RFC） | 1B-B 持久化缓存平面（后续） |
|---|---|---|
| 核心组件 | ProviderRegistry 增强、DataRouter internal-first 编排、TushareProvider、AKShareProvider、FreshnessPolicy、UnifiedDataClient `query()` 接入 | LocalMongoAdapter、CacheManager（Mongo 持久化）、TTL 索引创建 |
| I/O 依赖 | 无真实 Mongo 写入；TA-CN adapter 只读（Phase 1A 已交付）；provider 用 fake 替代 | 真实 Mongo 写入 `03_data_ud_cache_*`；真实 Mongo 读取 `03_data_ud_*` |
| 验证方式 | fake/mock/in-memory 全覆盖 | 需要 mongomock + 真实 Mongo smoke test |
| 风险等级 | 中（路由逻辑正确性、provider 声明一致性） | 中-高（Mongo 写入副作用、TTL 过期行为、集合创建授权） |
| 阻塞关系 | 不依赖 1B-B | 依赖 1B-A 的 Router/Registry 增强已稳定 |

**拆分原则**：先让「查询应该怎么路由、降级语义是什么」在零副作用条件下验证通过，再加持久化层。如果路由逻辑有缺陷，在 1B-A 阶段修复成本最低。

### 2.4 触发原因

RFC-03-007 Phase 1B 的 Design 详稿（DESIGN-03-007 §2111-2136）将 Provider + Cache + LocalMongoAdapter 打包在一个 Phase 中。实际编排时发现：

1. LocalMongoAdapter 和 CacheManager 的 Mongo 持久化需要 Pascal 对集合创建做明确授权（DESIGN-03-007 §17「新增 MongoDB 集合创建前需 Pascal 确认」），这是一个 **外部依赖决策点**。
2. Router/Provider/Freshness 的纯逻辑可以 **完全独立于 Mongo 写入**，先行验证。
3. 将两者打包会让 Verify 阶段的测试矩阵复杂化（需要同时 mock Mongo + mock provider），违反「单一变量」测试原则。

因此编排层决定将 Phase 1B 拆为 A/B 两个子段，A 先行。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 定义 DataRouter 的 **internal-first 路径编排**：TA-CN adapter 只读优先 →（1B-B 的 LocalMongoAdapter/Cache 占位）→ 外部 Provider fallback。1B-A 阶段 LocalMongoAdapter/Cache 层不存在，路径跳过，但路由编排逻辑必须为后续 slot-in 做好设计。
- [ ] 实现 `TushareProvider` 与 `AKShareProvider` 的 **能力声明（capability）、可用性检测（is_available）、canonical 转换框架、错误/降级语义**。1B-A 不做真实 API 调用验证；验证用 fake provider 替代。
- [ ] 实现 `FreshnessPolicy` 的 **纯计算逻辑**：按 domain 返回 TTL、按 fetched_at/data_date/from_cache 计算 freshness label。无 I/O。
- [ ] 定义 `UnifiedDataClient.query()` 的 **`provider` 参数与 `force_refresh` 参数语义边界**，并接入 internal-first 路由。
- [ ] 定义 `ProviderRegistry` 从 Phase 0 版到 1B-A 版的 **增量增强**（external fallback chain 配置、availability 检测钩子）。
- [ ] 全部组件 **可被 fake/mock/in-memory 完整验证**，不依赖真实 Tushare token、真实 AKShare 网络、真实 Mongo 写入。
- [ ] 与 RFC-03-007/SPEC-03-007 的 **六项不变量** 保持可追溯映射（见 §7）。

### 3.2 非目标（Out of Scope）

- [ ] **不实现 LocalMongoAdapter**（读取 `03_data_ud_*` 物化集合）— 1B-B。
- [ ] **不实现 CacheManager 的 Mongo 持久化**（写 `03_data_ud_cache_*`）— 1B-B。
- [ ] **不创建任何 MongoDB 集合、索引、schema validator**。
- [ ] **不做真实 Mongo 连接/写入**（TA-CN adapter 的只读复用已在 Phase 1A 交付，不在本段新增）。
- [ ] **不用真实 token/API 做验收**。验收仅基于 fake/mock/in-memory provider。
- [ ] **不实现 Task Center、批量回填、cron/systemd**。
- [ ] **不读取或写入 DSA SQLite/StockDaily**；不实现 DSA runtime adapter/fallback。
- [ ] **不修改 TA-CN 子项目代码**；不改变 TA-CN 无前缀集合文档。
- [ ] **不覆盖 Phase 1A 的 14 个域入口方法的行为**（它们继续直连 TA-CN adapter，不受 1B-A 路由增强影响；1B-A 增强的是 `query()` 路径和新增的外部 provider 能力）。

---

## 4. 整体设计

### 4.1 核心设计哲学

**internal-first 路由 + provider 可插拔 + 纯计算 freshness + 零 Mongo 写入验证**：

- DataRouter 按 internal-first 顺序编排查询：先查 TA-CN adapter（Phase 1A 已交付），内部未命中再走外部 Provider fallback 链（Tushare → AKShare）。
- Provider 以 capability 声明自身能力，Router 按 capability + market 路由 + fallback。
- FreshnessPolicy 是纯函数式计算，不读不写 I/O。
- 所有组件可用 fake provider + in-memory dict 完整验证。

### 4.2 架构总览（1B-A 范围）

```
┌─────────────────────────────────────────────────────────────────┐
│                    消费方（Consumers）                            │
│  stock | TA-CN | Argus | Portfolio | Risk | Reports | ...       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              UnifiedDataClient（查询入口）                        │
│                                                                  │
│  query(domain, operation, sid, provider=?, force_refresh=?)     │
│    → 委托给 DataRouter                                          │
│                                                                  │
│  [Phase 1A] 14 个域入口方法 → TA-CN adapter 直连（不变）         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              DataRouter（internal-first 编排）                    │
│                                                                  │
│  Step 1: TA_CNMongoAdapter 查 TA-CN 既有集合                     │
│          命中 → 返回（provider="ta_cn_internal"）                │
│                                                                  │
│  Step 2: [1B-B 占位] LocalMongoAdapter 查 03_data_ud_*           │
│          → 1B-A 阶段跳过（层不存在）                              │
│                                                                  │
│  Step 3: [1B-B 占位] CacheManager 查 03_data_ud_cache_*          │
│          → 1B-A 阶段跳过（层不存在）                              │
│                                                                  │
│  Step 4: 外部 Provider fallback 链（Tushare → AKShare）          │
│          命中 → 返回（provider="tushare"/"akshare"）             │
│          全部失败 → DataResult.error(...)                        │
│                                                                  │
│  force_refresh=True → 跳过 Step 1/2/3（未来含 cache）            │
│  provider="tushare" → 只走 Step 4 指定 provider                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              ProviderRegistry（注册 + capability 索引）           │
│                                                                  │
│  Phase 0 能力 + 1B-A 增强：                                      │
│  · external_fallback_chains（capability → [provider_name]）     │
│  · availability 钩子（is_available 按需检测）                     │
│  · provider 优先级（按注册顺序或显式配置）                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Providers（外部数据源适配）                          │
│                                                                  │
│  TushareProvider          │ AKShareProvider                     │
│  · capabilities 声明      │ · capabilities 声明                  │
│  · is_available()         │ · is_available()                     │
│  · fetch() → DataFrame    │ · fetch() → DataFrame                │
│  · canonical 转换框架     │ · canonical 转换框架                 │
│  · 限流/重试框架          │ · 限流框架                           │
│  (1B-A: 框架+fake验证,    │ (1B-A: 框架+fake验证,               │
│   真实API调用的激活在后续)│  真实API调用的激活在后续)            │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              FreshnessPolicy（纯计算）                            │
│                                                                  │
│  get_ttl(domain) → int（按域 TTL 查表）                          │
│  label(fetched_at, data_date, domain, from_cache) → FreshnessLabel│
│  无 I/O，纯函数式                                                │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 模块分工

| 组件 | 1B-A 职责 | 与 Phase 0/1A 的关系 |
|---|---|---|
| **DataRouter** | 从 Phase 0 外部 fallback 版升级为 internal-first 编排版 | Phase 0 版仅做 provider chain；1B-A 新增 TA-CN 前置查询 + force_refresh/provider 参数语义 |
| **ProviderRegistry** | 从 Phase 0 纯内存索引版增强：新增 external fallback chain 配置、availability 钩子 | Phase 0 版已有 register/get/get_providers；1B-A 增加 chain 配置 |
| **TushareProvider** | 全新实现：能力声明、is_available、fetch 框架、canonical 转换、限流/重试框架 | 不存在（Phase 0 无具体 provider） |
| **AKShareProvider** | 全新实现：同上 | 不存在 |
| **FreshnessPolicy** | 全新实现：纯计算 TTL + freshness label | Phase 1A freshness 全部硬编码 "delayed" |
| **UnifiedDataClient.query()** | 接入 internal-first 路由 + provider/force_refresh 参数 | Phase 0 query() 走旧 Router；1B-A 改走增强版 Router |
| **TA_CNMongoAdapter** | 不修改（Phase 1A 已交付） | 被 DataRouter 在 Step 1 调用 |

---

## 5. 详细设计

### 5.1 业务流程：查询路由

#### 5.1.1 正常路径 — internal-first 查询

```
消费方调用 client.query(domain, operation, security_id, **params)
  │
  ▼
DataRouter.query()
  │
  ├─ force_refresh=True?
  │    └─ 是 → 跳过 Step 1/2/3，直接进 Step 4（外部 Provider）
  │
  ├─ provider 参数指定?
  │    └─ 是 → 跳过 Step 1/2/3，直接走指定 provider（Step 4 的子集）
  │
  ├─ Step 1: 查 TA-CN adapter（只读，Phase 1A 既有）
  │    ├─ TA-CN adapter 覆盖该 domain.operation?
  │    │    └─ 否 → 继续 Step 4（该域不在 TA-CN 8 集合范围）
  │    ├─ TA-CN adapter 返回数据?
  │    │    └─ 命中 → 返回 DataResult(provider="ta_cn_internal",
  │    │                                freshness=FreshnessPolicy.label(...),
  │    │                                source_trace=["ta_cn_internal(ok)"])
  │    │    └─ 未命中（空） → 继续 Step 4
  │    └─ TA-CN adapter 异常（连接不可用等）
  │         → 记录 source_trace, 继续 Step 4（不阻断）
  │
  ├─ Step 2: [1B-B 占位] LocalMongoAdapter
  │    → 不存在，跳过
  │
  ├─ Step 3: [1B-B 占位] CacheManager
  │    → 不存在，跳过
  │
  ├─ Step 4: 外部 Provider fallback 链
  │    ├─ 从 ProviderRegistry 取 external_fallback_chains[capability]
  │    │    → 默认 ["tushare", "akshare"]
  │    ├─ 逐个尝试：
  │    │    ├─ TushareProvider.is_available()?
  │    │    │    └─ True → fetch() → 成功 → 返回 DataResult
  │    │    │    └─ False → 记录 skipped, 尝试下一个
  │    │    └─ AKShareProvider.is_available()?
  │    │         └─ True → fetch() → 成功 → 返回 DataResult
  │    │         └─ False → 记录 skipped
  │    └─ 全部失败 → DataResult.error(provider="error",
  │                                    freshness="empty",
  │                                    source_trace=[...完整链...])
  │
  └─ 返回 DataResult
```

#### 5.1.2 异常降级路径

| 场景 | Router 行为 | DataResult |
|---|---|---|
| TA-CN adapter 命中 | 返回 TA-CN 数据 | provider="ta_cn_internal", freshness=label(...) |
| TA-CN adapter 异常（连接失败等） | catch-and-log, 记录 source_trace, 继续 Step 4 | 不因 TA-CN 异常阻断 |
| TA-CN adapter 未命中 + 外部 Provider 全部成功 | 返回第一个成功的外部 provider 数据 | provider="tushare"/"akshare", freshness=label(...) |
| TA-CN adapter 未命中 + 外部 Provider 全部不可用 | 返回 error | provider="error", freshness="empty" |
| TA-CN adapter 未命中 + 外部 Provider 全部 fetch 失败 | 返回 error | provider="error", freshness="empty" |
| force_refresh=True | 跳过 TA-CN + cache，直接走外部 | provider=实际 provider |
| provider="tushare" 指定 | 只走 tushare，不 fallback | tushare 不可用 → error |
| 无任何 provider 注册 | 直接返回 error | provider="error", freshness="empty" |

### 5.2 Provider 能力声明与降级边界

#### 5.2.1 Capability 表（1B-A 范围）

以下 capability 在 1B-A 由 TushareProvider 和/或 AKShareProvider 声明：

| Capability | Tushare | AKShare | 说明 | 1B-A 状态 |
|---|---|---|---|---|
| `market_data.kline_daily` | ✅ | ✅ | A 股日线 K 线 | 框架 + fake 验证 |
| `market_data.kline_weekly` | ✅ | ✅ | 周线 K 线 | 框架 |
| `market_data.realtime_quote` | ✅ | ✅ | 实时行情快照 | 框架 |
| `market_data.adj_factor` | ✅ | ❌ | 复权因子（Tushare 独有） | 框架 |
| `financial.income_statement` | ✅ | ❌ | 利润表 | 框架 |
| `financial.balance_sheet` | ✅ | ❌ | 资产负债表 | 框架 |
| `financial.cash_flow` | ✅ | ❌ | 现金流量表 | 框架 |
| `valuation.daily_basic` | ✅ | ✅ | 每日估值（PE/PB/PS） | 框架 |
| `calendar.trading_days` | ✅ | ✅ | 交易日历 | 框架 |
| `calendar.is_trading_day` | ✅ | ✅ | 判断交易日 | 框架 |
| `metadata.stock_list` | ✅ | ✅ | 股票列表 | 框架 |
| `metadata.index_members` | ✅ | ❌ | 指数成分股 | 框架 |
| `news.stock_news` | ✅ | ❌ | 个股新闻 | 框架 |

> 注：1B-A 标注「框架 + fake 验证」意味着 provider 类的 `fetch()` 方法签名、capability 声明、is_available 检测、错误异常体系全部实现，但真实 Tushare/AKShare API 的调用代码可以是 stub（返回 fake DataFrame），因为本段验收 **不用真实 token**。真实 API 调用的激活在后续段或独立 smoke test 中验证。

#### 5.2.2 Provider 降级边界

| 维度 | TushareProvider | AKShareProvider |
|---|---|---|
| markets | `{CN}` | `{CN}` |
| is_available 条件 | token 存在（`TUSHARE_TOKEN` 环境变量非空）+ `tushare` 可 import | `akshare` 可 import |
| 限流框架 | 内置 rate limiter（Tushare 免费版 200 次/分钟） | 内置简单延迟（`time.sleep(0.5)` 每请求） |
| fetch 错误 | `ProviderError`（API 内部错误）/ `ProviderUnavailableError`（配额耗尽/网络不通） | 同左 |
| canonical 转换 | fetch 返回 DataFrame → domain service 转为 canonical object → 包入 DataResult | 同左 |
| fallback 优先级 | 外部链中第一优先 | 外部链中第二优先（兜底） |

### 5.3 FreshnessPolicy 纯计算逻辑

FreshnessPolicy 在 1B-A 是纯函数，不读写 I/O：

```python
class FreshnessPolicy:
    DEFAULT_TTLS = {
        "market_data": 21600,    # 6h
        "financial": 86400,      # 24h
        "valuation": 43200,      # 12h
        "calendar": 604800,      # 7d
        "metadata": 604800,      # 7d
        "news": 3600,            # 1h
    }

    def get_ttl(self, domain: str) -> int:
        return self.DEFAULT_TTLS.get(domain, 3600)

    def label(self, fetched_at, data_date, domain, from_cache) -> str:
        """返回 realtime / delayed / cached / stale / empty 之一"""
```

**freshness 标签规则**：

| 标签 | 条件 |
|---|---|
| `realtime` | fetched_at 距 now < 60s 且非 from_cache |
| `delayed` | fetched_at 距 now < 15min 且非 from_cache |
| `cached` | from_cache 且未超过 domain TTL |
| `stale` | from_cache 但已超过 domain TTL |
| `empty` | data 为空/None |

> 1B-A 阶段 `from_cache` 永远为 False（无 cache 层），因此 freshness 只会是 realtime/delayed/empty。当 1B-B 引入 CacheManager 后，`from_cache=True` 的路径才会激活 cached/stale 标签。

### 5.4 UnifiedDataClient 查询入口语义

#### 5.4.1 `query()` 参数语义

| 参数 | 语义 | 1B-A 行为 |
|---|---|---|
| `domain` + `operation` | 组成 capability 字符串 | 同 Phase 0 |
| `security_id` | 查询标的 | 同 Phase 0 |
| `provider` | 强制指定 provider，跳过 internal-first + fallback | 只走指定 provider；不可用时返回 error |
| `force_refresh` | 绕过内部缓存层（TA-CN + 未来 cache） | True → 跳过 Step 1（TA-CN），直接走外部 |
| `params` | 传给 provider.fetch() 的额外参数 | 同 Phase 0 |

#### 5.4.2 `provider` 与 `force_refresh` 的交互矩阵

| provider | force_refresh | 行为 |
|---|---|---|
| None | False（默认） | internal-first 全路径：TA-CN → 外部 fallback |
| None | True | 跳过 TA-CN，直接走外部 fallback |
| "tushare" | any | 只走 tushare（跳过 TA-CN + 跳过 fallback） |
| "ta_cn_internal" | False | 只走 TA-CN（显式指定内部源） |

#### 5.4.3 与 Phase 1A 14 个域入口方法的关系

Phase 1A 的 14 个域入口方法（`get_kline_daily`、`get_stock_info` 等）**行为不变**，继续直连 TA-CN adapter。1B-A 不修改它们。

1B-A 增强的是 `query()` 方法：它从 Phase 0 的纯外部 fallback 升级为 internal-first 编排。消费方有两个选择：

1. 调用 14 个域入口方法 → 直连 TA-CN（Phase 1A 行为，无外部 fallback）。
2. 调用 `query(domain, operation, sid)` → 走 internal-first 全路径（TA-CN → 外部 fallback）。

> 后续阶段（1B-B 或 1C）可以将 14 个域入口方法统一收编到 `query()` 路径，但 1B-A 不做这个收编，避免破坏 Phase 1A 的验收。

### 5.5 credentials / rate-limit / 网络错误风险模型

#### 5.5.1 凭据管理

| 凭据 | 来源 | 1B-A 行为 |
|---|---|---|
| Tushare token | 环境变量 `TUSHARE_TOKEN` | provider 从环境变量读取；**不记录/不打印真实值**；is_available 检查「变量是否存在且非空」 |
| AKShare | 无需 token（免费公开 API） | is_available 检查 `akshare` 是否可 import |

**安全原则**（DESIGN-03-007 §17 / P-10）：
- 凭据值不记录在 task metadata、kanban summary、审计日志中。
- is_available 只检查「存在性」，不泄露值。
- 配置文件中凭据用环境变量占位符引用。

#### 5.5.2 限流与网络错误

| 错误类型 | 异常类 | Router 处理 | DataResult |
|---|---|---|---|
| Provider 配额耗尽 | `ProviderUnavailableError` | 记录 source_trace，尝试下一个 provider | 最终在 DataResult.warnings 体现 |
| Provider API 内部错误 | `ProviderError` | 记录 source_trace，尝试下一个 | 同上 |
| 网络超时 | `ProviderUnavailableError` | 同上 | 同上 |
| Capability 不支持 | `UnsupportedCapabilityError` | provider 声明中不含此 capability，Router 跳过 | 不进入此 provider 的 fetch |
| 所有 provider 失败 | `AllProvidersFailedError`（内部） | 返回 DataResult.error | provider="error", freshness="empty" |

#### 5.5.3 DataResult 错误/告警字段

| 字段 | 内容 | 示例 |
|---|---|---|
| `provider` | 实际提供数据的 provider 名 | "ta_cn_internal" / "tushare" / "akshare" / "error" |
| `freshness` | 新鲜度标签 | "delayed" / "realtime" / "empty" |
| `source_trace` | 完整尝试链 | ["ta_cn_internal(ok)"] 或 ["ta_cn_internal(empty)", "tushare(fail: quota exceeded)", "akshare(ok)"] |
| `warnings` | 非致命告警 | ["tushare quota exceeded, fell back to akshare"] |

---

## 6. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| internal-first 路由编排逻辑错误（TA-CN 应优先但被跳过） | 中 | 高 | fake provider 测试覆盖全路径矩阵；source_trace 完整记录 | force_refresh=True 可绕过 |
| Provider capability 声明与实际 fetch 能力不一致 | 中 | 中 | is_available 做最小化检查（不依赖网络）；capability 声明保守（只声明已验证的域） | 不支持的 capability 自动跳过 |
| Tushare token 泄露到日志/metadata | 低 | 高 | P-10 规范：不记录凭据值；is_available 只检查存在性 | 审计审查 |
| FreshnessPolicy 标签逻辑与 FreshnessPolicy 表不一致 | 低 | 中 | 纯函数单元测试全覆盖；freshness 标签规则表进 SPEC | — |
| Phase 1A 14 域入口方法与 query() 行为不一致（消费方困惑） | 中 | 低 | 文档明确区分两条路径；后续段统一收编 | 消费方按需选择 |
| fake provider 测试与真实 provider 行为偏差 | 中 | 中 | 后续段补真实 API smoke test；1B-A 标注「框架 + fake 验证」 | — |
| DataRouter 从 Phase 0 版升级破坏现有 Phase 0 测试 | 低 | 中 | Phase 0 测试用 fake provider 不受影响；增强版保持向后兼容 | 回退到 Phase 0 Router |

---

## 7. 与 RFC-03-007 六项不变量的可追溯映射

RFC-03-007 §14 / SPEC-03-007 §0.2 定义了 Pascal 确认的六项架构基线不变量。本 RFC 必须与之保持一致：

| # | 不变量 | 1B-A 的体现 |
|---|---|---|
| 1 | **共享物理数据库**：Unified Data 与 TA-CN 共用 `tradingagents` | DataRouter Step 1 通过 Phase 1A 的 TA_CNMongoAdapter 读取同一物理库；1B-A 不新增任何集合 |
| 2 | **Internal-First 读取路径**：TA-CN 既有 → UD 物化 → Query Cache → 外部 Provider | DataRouter 编排严格遵守此顺序；1B-A 阶段 UD 物化/Cache 层不存在（占位跳过），但编排逻辑已为 slot-in 做好准备 |
| 3 | **DSA 不是运行时数据源** | 1B-A 的 external_fallback_chains 只含 ["tushare", "akshare"]；DSA 不出现在任何运行时链路 |
| 4 | **Collection Ownership 不可回写** | 1B-A 不写任何集合；TA-CN adapter 只读（Phase 1A 已保证） |
| 5 | **Task Center 先行** | 1B-A 不实现 Task Center 集成、不创建 Job、不启用 cron/systemd |
| 6 | **三层语义分离** | 1B-A 不操作任何集合；TA-CN 既有集合（Step 1 只读）与 UD 物化/Cache（1B-B 才引入）语义边界清晰 |

---

## 8. 备选方案

### 8.1 方案 B：1B-A 与 1B-B 合并为一个 Phase（不拆分）

- **优点**：减少 pipeline 阶段数；一次 Implement/Verify/Review 覆盖全部
- **缺点**：Mongo 持久化（1B-B）的集合创建需要 Pascal 授权，是一个外部依赖决策点；如果与纯路由逻辑（1B-A）打包，Verify 阶段需要同时 mock Mongo + mock provider，测试矩阵复杂化
- **不选原因**：违反单一变量测试原则；拆分让路由逻辑先行验证，风险隔离更好

### 8.2 方案 C：1B-A 包含真实 Tushare/AKShare API 调用验证

- **优点**：一次性验证 provider 真实可用性
- **缺点**：需要真实 token（P-10 安全约束）、依赖网络可用性、验收不稳定（Tushare 限流/网络波动可能导致 flaky test）
- **不选原因**：本 RFC 明确规定验收仅基于 fake/mock；真实 API smoke test 作为可选 `@pytest.mark.network` 在后续段处理

### 8.3 方案 D：DataRouter 升级时废弃 Phase 0 Router，新建 Router2

- **优点**：Phase 0 测试完全不受影响
- **缺点**：两套 Router 并存增加维护成本；消费方需要知道用哪个
- **不选原因**：增强版 Router 保持 API 向后兼容（`query()` 签名不变，新增参数有默认值），Phase 0 测试自然通过

---

## 9. 验收标准

### 9.1 本 RFC 阶段验收（RFC 自身）

- [x] RFC 文件存在于 `docs/rfc/03_data/RFC-03-008-unified-data-phase-1b-query-plane.md`
- [x] RFC 明确回答了 task body 要求的 6 个问题（见 §1-§7）
- [x] RFC 与 RFC-03-007 的六项不变量可追溯映射（§7）
- [x] RFC 明确 1B-A 与 1B-B 的拆分边界（§2.3）
- [x] RFC 明确 internal-first / provider 指定 / force_refresh / stale fallback 的业务语义（§5.1/§5.4）
- [x] RFC 明确 Tushare/AKShare capability 与降级边界（§5.2）
- [x] RFC 明确 credentials/rate-limit/网络错误的风险模型（§5.5）
- [x] RFC 明确通过/失败验收与不做的清单（§9.2/§9.3）
- [x] 中文输出，专业简洁

### 9.2 后续 SPEC/Design/Implement 阶段验收（供 T2 参考）

- [ ] DataRouter internal-first 路径编排可用 fake provider + in-memory TA-CN mock 验证全路径矩阵
- [ ] TushareProvider / AKShareProvider 的 capability 声明、is_available、fetch 框架完整
- [ ] FreshnessPolicy 纯计算逻辑单元测试全覆盖
- [ ] `query()` 的 provider/force_refresh 参数语义矩阵（§5.4.2）全覆盖
- [ ] source_trace 在所有路径（成功/跳过/失败）下完整记录
- [ ] DataResult 的 provider/freshness/warnings 字段在各降级场景下正确

### 9.3 明确不做清单（1B-A 不覆盖）

- [ ] ❌ 不实现 LocalMongoAdapter
- [ ] ❌ 不实现 CacheManager 的 Mongo 持久化
- [ ] ❌ 不创建任何 MongoDB 集合/索引/schema
- [ ] ❌ 不做真实 Mongo 连接/写入
- [ ] ❌ 不用真实 token/API 做验收
- [ ] ❌ 不实现 Task Center / 批量回填 / cron / systemd
- [ ] ❌ 不读取/写入 DSA SQLite / StockDaily
- [ ] ❌ 不修改 TA-CN 子项目代码
- [ ] ❌ 不改变 Phase 1A 14 域入口方法的行为
- [ ] ❌ 不修改 RFC/SPEC/Design 文档模板

---

## 10. 开放问题

1. **DataRouter 增强是否破坏 Phase 0 的 `query()` 行为？**
   - 预期答案：不破坏。增强版 Router 的 `query()` 签名保持向后兼容（新增 `force_refresh` 参数有默认值 False）。Phase 0 的 fake provider 测试在无 TA-CN adapter 注入时，Step 1 自动跳过（adapter 为 None），行为退化为 Phase 0 的外部 fallback。SPEC/Design 阶段需明确这个退化路径。

2. **Provider 的真实 API 调用代码在 1B-A 实现到什么程度？**
   - 预期答案：1B-A 实现 provider 类的完整框架（capability 声明、is_available、fetch 方法签名、错误异常体系、canonical 转换入口），但 `fetch()` 内部的真实 Tushare/AKShare API 调用可以是 stub（返回结构正确的 fake DataFrame）。SPEC 需定义「框架完整」的精确边界。

3. **external_fallback_chains 配置是硬编码还是配置文件驱动？**
   - 预期答案：1B-A 可以在 `UnifiedDataConfig` 中定义默认链（capability → [provider_name]），不需要外部 YAML 文件。后续段可引入 YAML 配置。SPEC 需确定默认值。

---

## 11. 参考资料

- RFC-03-007：Unified Data Layer 总纲（`docs/rfc/03_data/RFC-03-007-unified-data-layer.md`）
- SPEC-03-007：Unified Data Layer 契约（`docs/spec/03_data/SPEC-03-007-unified-data-layer.md`）
- DESIGN-03-007：Unified Data Layer 详细设计（`docs/design/03_data/DESIGN-03-007-unified-data-layer.md`），特别是 §7.4（internal-first 读取路径）、§8.1（缓存与读取架构）、§12 Phase 1B 定义
- 现有代码：`skills/data/unified_data/` Phase 0 骨架 + Phase 1A TA-CN adapter
- Pipeline skill：`skills/infra/ai-coding-pipeline/SKILL.md`

---

## 12. 文档关系说明

本文档（RFC-03-008）是 RFC-03-007 Phase 1B 的 **子阶段拆分 RFC**，不替代 RFC-03-007。关系如下：

```
RFC-03-007（Unified Data Layer 总纲）
  ├── Phase 0：骨架（已交付）
  ├── Phase 1A：TA-CN read-only adapter（已交付）
  ├── Phase 1B：External Provider + Cache + Freshness
  │     ├── Phase 1B-A：查询平面与外部降级（本 RFC）
  │     └── Phase 1B-B：持久化缓存平面（后续 RFC）
  ├── Phase 1C：端到端验收
  └── Phase 2-7：后续阶段
```

后续 SPEC（SPEC-03-008）和 Design 将基于本 RFC 的边界定义，进一步细化到方法签名级契约和文件清单级设计。
