# RFC-03-009：Unified Data Phase 1B-B — 持久化缓存平面

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-14 |
| 最后更新 | 2026-07-14 |
| 版本号 | V0.1 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-008（Phase 1B-A 查询平面） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-008（Phase 1B-A 查询平面） |
| 替代 RFC | 无（不替代 RFC-03-008，为其 1B-B 子阶段的 RFC） |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #cache #persistence #local_mongo #query_cache |

### 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-14 | 初始创建。定义 Phase 1B-B 持久化缓存平面的需求、范围、ownership、失败与回滚、安全门禁、fake/mock 验收和生产审批点。与 RFC-03-007/008 和已修订 1C 契约保持一致。 | YQuant-Principal |

---

## 1. 执行摘要

RFC-03-008 将 Phase 1B 拆为 1B-A（查询平面）与 1B-B（持久化缓存平面）。1B-A 已在 2026-07-14 交付（313 测试 PASS、零 Mongo 副作用、internal-first 路由编排稳定）。本 RFC 定义 **1B-B 持久化缓存平面**：

- **LocalMongoAdapter**：只读 Unified Data 自有物化集合（`03_data_ud_*`），是 internal-first 路径的第 2 层。
- **CacheManager**：读写短 TTL Query Cache（`03_data_ud_cache_*`），是 internal-first 路径的第 3 层。
- **DataRouter slot-in**：激活 `router.py` 中已预留但被 ValueError 硬守卫的 `local_mongo_adapter` / `cache_manager` 两个构造参数。
- **internal-first 完整四步路径生效**：TA-CN → UD 物化 → Query Cache → 外部 Provider。

**核心约束**：1B-B 研发阶段只用 `fake`/`mongomock`/`in-memory` 验证。**禁止真实 Mongo 连接、写入、DDL、collection/index/validator 创建、真实 API、Task Center/cron/systemd。** 任何生产 collection / index / rollout 均需 Pascal 明确审批。

---

## 2. 背景与动机

### 2.1 现状

Phase 1B-A 已交付以下组件（RFC-03-008 / SPEC-03-008 / DESIGN-03-008）：

- `DataRouter`（`router.py`）：internal-first 四步编排，Step 1（TA-CN）已实现，Step 2/3 占位跳过。
- `ProviderRegistry`（`registry.py`）：增强版，含 `external_fallback_chains`。
- `TushareProvider` / `AKShareProvider`（`providers/`）：capability 声明 + fake/stub fetch。
- `FreshnessPolicy`（`freshness.py`）：纯计算 TTL + label。
- `UnifiedDataClient.query()`：接入 internal-first 路由 + `provider`/`force_refresh` 参数。

**关键现状**：`router.py` 的 `DataRouter.__init__` 已预留 `local_mongo_adapter` 和 `cache_manager` 两个构造参数，但在 1B-A 阶段被 **ValueError 硬守卫**强制为 `None`：

```python
if local_mongo_adapter is not None:
    raise ValueError("local_mongo_adapter is a Phase 1B-B slot; Phase 1B-A must pass None.")
if cache_manager is not None:
    raise ValueError("cache_manager is a Phase 1B-B slot; Phase 1B-A must pass None.")
```

1B-B 的核心任务就是：**实现这两个组件，并移除（或条件化）ValueError 守卫，让 Router 的四步路径完整生效。**

### 2.2 痛点

| 痛点 | 影响 |
|---|---|
| LocalMongoAdapter 不存在 | 外部 Provider 成功获取的数据无法物化存储，每次查询都走外部，浪费配额、增加延迟 |
| CacheManager 不存在 | 相同查询重复走外部 Provider，TTL 缓存层缺失，FreshnessPolicy 的 `cached`/`stale` 标签无法激活 |
| Router Step 2/3 恒跳过 | internal-first 路径只有 2 步生效（TA-CN → 外部），UD 物化 + Query Cache 层缺失 |
| 物化与缓存集合未定义 | `03_data_ud_*` 和 `03_data_ud_cache_*` 的数据信封、key 组成、TTL 规则、invalidate 行为均未契约化 |
| 集合 ownership 授权门禁未落地 | 生产 Mongo 集合创建需 Pascal 审批，但文档未固化审批点 |

### 2.3 为什么 1B-B 在 1B-A 之后

| 维度 | 1B-A 查询平面（已交付） | 1B-B 持久化缓存平面（本 RFC） |
|---|---|---|
| 核心组件 | DataRouter internal-first 编排、Provider 框架、FreshnessPolicy | LocalMongoAdapter、CacheManager、物化集合信封、TTL 索引 |
| I/O 依赖 | 零 Mongo 写入；TA-CN 只读；provider fake | 物化读取 `03_data_ud_*`；缓存读写 `03_data_ud_cache_*`；**生产 rollout 需真实 Mongo DDL** |
| 验证方式 | fake/mock/in-memory 全覆盖 | fake/mongomock/in-memory 验证 + 生产 rollout 门禁（需 Pascal 批准） |
| 风险等级 | 中（路由逻辑正确性） | 中-高（集合写入副作用、TTL 过期行为、ownership 边界） |
| 阻塞关系 | 不依赖 1B-B | 依赖 1B-A 的 Router/Registry 增强已稳定（已满足） |

**核心原则**：1B-B 把持久化层加入 internal-first 路径，但不触碰任何 TA-CN 既有无前缀集合。物化数据（`03_data_ud_*`）与 Query Cache（`03_data_ud_cache_*`）是两层语义分离：物化可追溯、Cache 可丢弃。

### 2.4 失败语义继承

1B-B 继承 1B-A 已确认的失败语义（RFC-03-008 §5.1.2 / SPEC-03-008 §3.1 关键语义变更）：

- 对调用方（消费方），所有 Provider 失败时返回 `DataResult.error(provider="error", source_trace=[...])`。
- `AllProvidersFailedError` 仅作为 Phase 0 历史/内部兼容类型保留，**不作为 Router 主出口异常**。
- internal-first 路径中，外部刷新失败**不阻断**已有内部数据读取：TA-CN 命中 → 返回；TA-CN 未命中 + 物化命中 → 返回；物化未命中 + Cache 命中 → 返回；全部内部未命中 + 外部失败 → 返回 error。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 定义 `LocalMongoAdapter` 的精确公共接口：只读 `03_data_ud_*` 物化集合，按 `(security_id, domain, operation, params)` 查询，返回 `DataResult | None`。
- [ ] 定义 `CacheManager` 的精确公共接口：读写 `03_data_ud_cache_*` 短 TTL Query Cache，含 `get` / `put` / `invalidate` / `force_refresh` 语义。
- [ ] 定义 `03_data_ud_*`（物化）与 `03_data_ud_cache_*`（Query Cache）的**数据信封**（document schema）、key 组成、TTL/freshness 规则、读写/invalidate 行为。
- [ ] 定义 DataRouter 的 **Step 2/3 激活**机制：移除或条件化 ValueError 守卫，让 `local_mongo_adapter` / `cache_manager` 可注入并生效。
- [ ] 定义 **internal-first 完整四步读优先顺序**：TA-CN 既有 → UD 物化 → Query Cache → 外部 Provider；Cache hit 时外部调用为 0。
- [ ] 定义 **allow-list / 幂等 / 静默 / 错误归类 / source_trace** 行为契约。
- [ ] 定义 **缓存失败不得阻塞正常查询**：CacheManager.get/put 异常时 catch-and-log，不影响 DataRouter 返回正确结果。
- [ ] 定义 **fake/mongomock/in-memory 验收边界**：全部组件可被 fake provider + mongomock + in-memory dict 完整验证。
- [ ] 定义 **生产 Mongo rollout 明确门禁**：任何真实 collection / index / validator 创建均需 Pascal 明确审批，不在 1B-B 研发阶段执行。
- [ ] 与 RFC-03-007/SPEC-03-007 的**六项不变量**保持可追溯映射（见 §7）。

### 3.2 非目标（Out of Scope）

- [ ] **不做真实 Mongo 连接/写入/DDL**（collection/index/validator 创建）— 1B-B 研发阶段全部用 mongomock/fake。
- [ ] **不做真实外部 API 调用**（Tushare/AKShare fetch 仍用 1B-A 的 fake/stub）。
- [ ] **不创建或修改任何 MongoDB 集合**（研发阶段零 DDL）。
- [ ] **不实现 Task Center、批量回填、cron/systemd、后台刷新调度**。
- [ ] **不读取或写入 DSA SQLite/StockDaily**；DSA 不进入任何运行时链路。
- [ ] **不修改 TA-CN 子项目代码**（`skills/apps/TradingAgents-CN/**`）。
- [ ] **不修改 Phase 1A 的 14 个域入口方法行为**（继续直连 TA-CN adapter）。
- [ ] **不修改 RFC/SPEC/Design 文档模板**（RFC-00-000 / SPEC-00-000 / DESIGN-00-000）。
- [ ] **不修改 Phase 0/1A/1B-A 已有的 SecurityId / DataResult / DataProvider / Capability / Router / Registry / FreshnessPolicy 的公共契约**（只新增组件、新增参数语义、条件化守卫）。
- [ ] **不实现 QualityScorer / AuditLogger**（Phase 2 范围；1B-B 的 source_trace 已提供轻量级来源链）。

---

## 4. 整体设计

### 4.1 核心设计哲学

**物化与缓存语义分离 + internal-first slot-in + 零生产副作用研发 + 生产 rollout 门禁**：

- **物化数据**（`03_data_ud_*`）：外部 Provider 成功获取的数据**物化存储**，可追溯、可重建、长期保留（按域 TTL 淘汰）。是 internal-first 路径的第 2 层。
- **Query Cache**（`03_data_ud_cache_*`）：对**查询结果**的短 TTL 缓存，可丢弃、命中率优化。是 internal-first 路径的第 3 层。
- 两者共用同一物理数据库 `tradingagents`，通过集合命名空间前缀区分。
- DataRouter 激活 Step 2/3 slot-in，但**研发阶段全部用 mongomock**，生产 rollout 另需审批。

### 4.2 架构总览（1B-B 范围，完整四步路径）

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
│    → 委托给 DataRouter（1B-B 四步完整激活）                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              DataRouter（internal-first 完整四步）                │
│                                                                  │
│  Step 1: TA_CNMongoAdapter 查 TA-CN 既有集合                     │
│          命中 → 返回（provider="ta_cn_internal"）                │
│                                                                  │
│  Step 2: LocalMongoAdapter 查 03_data_ud_*  [1B-B 新激活]        │
│          命中 + 未过期 → 返回（provider="ud_materialized",        │
│                               freshness="cached"）               │
│          未命中 / 已过期 → 继续                                    │
│                                                                  │
│  Step 3: CacheManager 查 03_data_ud_cache_*  [1B-B 新激活]       │
│          命中 + 未过期 → 返回（freshness="cached"）               │
│          未命中 / 过期 / force_refresh → 继续                     │
│                                                                  │
│  Step 4: 外部 Provider fallback 链（Tushare → AKShare）          │
│          命中 → 返回 + 物化写入 03_data_ud_* + CacheManager.put() │
│          全部失败 → DataResult.error(...)                        │
│                                                                  │
│  force_refresh=True → 跳过 Step 1/2/3                            │
│  provider="tushare" → 跳过 Step 1/2/3，只走 Step 4 指定           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌───────────────┐  ┌───────────────────┐
│TA_CNMongo    │  │LocalMongoAdapt│  │CacheManager       │
│Adapter       │  │er             │  │                   │
│(Phase 1A     │  │(1B-B 新增)    │  │(1B-B 新增)        │
│ 只读)        │  │ 只读          │  │ 读写短 TTL Cache  │
│              │  │ 03_data_ud_*  │  │ 03_data_ud_cache_*│
│              │  │ 物化集合      │  │                   │
└──────────────┘  └───────────────┘  └───────────────────┘
```

### 4.3 物化数据与 Query Cache 的语义分离

| 维度 | 物化数据 `03_data_ud_*` | Query Cache `03_data_ud_cache_*` |
|---|---|---|
| ownership | Unified Data | Unified Data |
| 语义 | 可追溯的外部数据物化存储 | 可丢弃的查询结果短 TTL 缓存 |
| 数据来源 | 外部 Provider 成功后物化写入 | 查询成功后缓存写入（含 TA-CN / 物化 / 外部结果） |
| TTL 策略 | 按域 TTL（FreshnessPolicy.get_ttl），过期后可重建 | 按域 TTL，过期后自动失效 |
| 失效行为 | 按 TTL 淘汰 + 手动 invalidate | 按 TTL 自动过期 + force_refresh bypass + invalidate |
| 读路径 | Step 2（在 TA-CN 之后、Cache 之前） | Step 3（在物化之后、外部之前） |
| 可丢弃性 | ❌ 不轻易丢弃（可重建但成本高） | ✅ 可随时丢弃（下次查询自动重建） |
| 文档信封 | 按 domain.operation 组织，含原始 payload + metadata | 按 cache_key 组织，含序列化 DataResult + cached_at |

---

## 5. 详细设计

### 5.1 业务流程：internal-first 完整四步查询

#### 5.1.1 正常路径

```
消费方调用 client.query(domain, operation, security_id, **params)
  │
  ▼
DataRouter.query()
  │
  ├─ provider 参数指定?
  │    └─ "ta_cn_internal" → 只走 Step 1（1B-A 行为不变）
  │    └─ 外部 provider 名 → 只走 Step 4 指定（1B-A 行为不变）
  │
  ├─ force_refresh=True?
  │    └─ 跳过 Step 1/2/3，直接进 Step 4
  │
  ├─ Step 1: 查 TA-CN adapter（只读，Phase 1A 既有）
  │    ├─ 命中 → 返回 DataResult(provider="ta_cn_internal")
  │    ├─ 覆盖但空 → 返回 DataResult(provider="empty")（1B-A 行为不变）
  │    └─ 不覆盖 / 异常 → 继续 Step 2
  │
  ├─ Step 2: [1B-B] LocalMongoAdapter 查 03_data_ud_*
  │    ├─ 命中 + 未过期 → 返回 DataResult(provider="ud_materialized",
  │    │                                freshness="cached")
  │    ├─ 命中但已过期 → 继续 Step 3（过期物化不返回，但可作为 Cache 源）
  │    ├─ 未命中 → 继续 Step 3
  │    └─ 异常 → catch-and-log, trace 记录, 继续 Step 3（不阻断）
  │
  ├─ Step 3: [1B-B] CacheManager 查 03_data_ud_cache_*
  │    ├─ 命中 + 未过期 → 返回 DataResult(freshness="cached")
  │    ├─ 命中但已过期 → 继续 Step 4
  │    ├─ 未命中 → 继续 Step 4
  │    └─ 异常 → catch-and-log, trace 记录, 继续 Step 4（不阻断）
  │
  ├─ Step 4: 外部 Provider fallback 链
  │    ├─ 命中 → 返回 DataResult(provider="tushare"/"akshare")
  │    │         + 异步/同步物化写入 03_data_ud_*（Step 2 源）
  │    │         + CacheManager.put()（Step 3 源）
  │    └─ 全部失败 → DataResult.error(provider="error",
  │                                    source_trace=[...完整链...])
  │
  └─ 返回 DataResult
```

#### 5.1.2 异常降级路径

| 场景 | Router 行为 | DataResult |
|---|---|---|
| TA-CN 命中 | 返回 TA-CN 数据 | provider="ta_cn_internal", freshness=label(...) |
| TA-CN 未命中 + 物化命中（未过期） | 返回物化数据 | provider="ud_materialized", freshness="cached" |
| TA-CN 未命中 + 物化未命中 + Cache 命中（未过期） | 返回 Cache 数据 | provider=原始 provider, freshness="cached" |
| 全部内部未命中 + 外部成功 | 返回外部数据 + 物化写入 + Cache 写入 | provider="tushare"/"akshare", freshness=label(...) |
| 全部内部未命中 + 外部全部不可用 | 返回 error | provider="error", freshness="empty" |
| LocalMongoAdapter 异常 | catch-and-log, 继续 Step 3 | 不因物化异常阻断 |
| CacheManager 异常 | catch-and-log, 继续 Step 4 | 不因 Cache 异常阻断 |
| force_refresh=True | 跳过 Step 1/2/3 | provider=实际 provider |
| provider="tushare" 指定 | 只走 Step 4 tushare | 1B-A 行为不变 |
| 物化命中但过期 | 不返回过期物化，继续 Step 3/4 | — |

### 5.2 LocalMongoAdapter

#### 5.2.1 定位

LocalMongoAdapter 是 internal-first 读取路径的 **第 2 层**，负责只读 Unified Data 自有物化集合（`03_data_ud_*`）。与 `TA_CNMongoAdapter` 的区别：

| 维度 | TA_CNMongoAdapter | LocalMongoAdapter |
|---|---|---|
| ownership | TA-CN | Unified Data |
| 集合前缀 | 无前缀（TA-CN 既有） | `03_data_ud_*` |
| 权限 | 只读复用 | 只读（写由外部 Provider 成功后的物化逻辑负责） |
| 读取路径位置 | Step 1 | Step 2 |

两者共用同一物理数据库 `tradingagents`，通过集合命名空间前缀区分 ownership。

#### 5.2.2 接口契约（供 SPEC 阶段细化）

```python
class LocalMongoAdapter:
    """只读 Unified Data 物化集合（03_data_ud_*）。

    Step 2 of internal-first path. Read-only — writes are performed
    by the materialization logic after external provider success.
    """

    def __init__(
        self,
        mongo_db,                              # 数据库句柄（生产 MongoDB 或 mongomock）
        collection_prefix: str = "03_data_ud_",
        freshness: "FreshnessPolicy | None" = None,
    ) -> None: ...

    def get(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: dict,
    ) -> "DataResult | None": ...
    # 返回未过期的物化 DataResult；未命中/过期返回 None。

    def put(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: dict,
        result: "DataResult",
    ) -> None: ...
    # 物化写入外部 Provider 成功后的 DataResult。
    # 写入失败时 catch-and-log，不影响查询返回值。

    def invalidate(
        self,
        security_id: "SecurityId | None" = None,
        domain: str | None = None,
    ) -> int: ...
    # 批量失效物化数据，返回删除条数。
```

#### 5.2.3 物化集合信封（供 SPEC 阶段细化）

```json
{
  "_id": "ObjectId",
  "materialized_key": "<sha256 hash>",
  "security_id": "CN:600519",
  "domain": "market_data",
  "operation": "kline_daily",
  "params_hash": "<md5 hash>",
  "data": "<原始 payload / 序列化 DataResult.data>",
  "provider": "tushare",
  "fetched_at": "ISO datetime",
  "data_date": "2026-07-14",
  "freshness_at_write": "delayed",
  "source_trace": ["tushare(ok)"],
  "schema_version": "1.0",
  "materialized_at": "ISO datetime",
  "expires_at": "ISO datetime (materialized_at + TTL)"
}
```

### 5.3 CacheManager

#### 5.3.1 定位

CacheManager 是 internal-first 读取路径的 **第 3 层**，负责读写短 TTL Query Cache（`03_data_ud_cache_*`）。与 LocalMongoAdapter 的区别：

| 维度 | LocalMongoAdapter（物化） | CacheManager（Query Cache） |
|---|---|---|
| 集合前缀 | `03_data_ud_*` | `03_data_ud_cache_*` |
| 语义 | 可追溯的外部数据物化 | 可丢弃的查询结果缓存 |
| 数据来源 | 仅外部 Provider 成功 | 任意成功查询（TA-CN / 物化 / 外部） |
| 可丢弃性 | 不轻易丢弃 | 可随时丢弃 |
| TTL | 按域 TTL（较长，可重建） | 按域 TTL（较短，命中率优先） |

#### 5.3.2 接口契约（基于 SPEC-03-007 §4.7，供 SPEC 阶段细化）

```python
class CacheManager:
    """短 TTL Query Cache（03_data_ud_cache_*）。

    Step 3 of internal-first path. Read-write, but failures are
    catch-and-log — cache issues never block a query.
    """

    def __init__(
        self,
        mongo_db,                              # 数据库句柄（生产 MongoDB 或 mongomock）
        collection_prefix: str = "03_data_ud_cache_",
        freshness: "FreshnessPolicy | None" = None,
    ) -> None: ...

    def get(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: dict,
    ) -> "DataResult | None": ...
    # 返回未过期的缓存 DataResult；未命中/过期返回 None。

    def put(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: dict,
        result: "DataResult",
    ) -> None: ...
    # 缓存写入成功查询的 DataResult。写入失败 catch-and-log。

    def invalidate(
        self,
        security_id: "SecurityId | None" = None,
        domain: str | None = None,
    ) -> int: ...
    # 批量失效缓存，返回删除条数。
```

#### 5.3.3 Cache key 组成

```
cache_key = sha256(
    f"{security_id}|{domain}|{operation}|{json.dumps(params, sort_keys=True)}"
)[:32]
```

- 确定性：相同参数生成相同 key。
- 集合映射：`03_data_ud_cache_{operation}`（如 `03_data_ud_cache_kline_daily`）。

### 5.4 DataRouter slot-in 激活

#### 5.4.1 守卫移除策略

1B-A 在 `router.py` 中用 ValueError 硬守卫 `local_mongo_adapter` / `cache_manager` 为 `None`。1B-B 需要：

- **移除 ValueError 守卫**，允许注入 LocalMongoAdapter / CacheManager 实例。
- 保留 `None` 默认值（向后兼容 1B-A 测试：`local_mongo_adapter=None` 时 Step 2 跳过）。
- Step 2/3 的编排逻辑在 SPEC/Design 阶段精确定义。

#### 5.4.2 Step 2/3 激活条件

| Step | 激活条件 | 跳过条件 |
|---|---|---|
| Step 2（物化） | `self._local_mongo_adapter is not None` AND NOT force_refresh AND provider 未指定外部 | adapter 为 None / force_refresh / provider 指定外部 |
| Step 3（Cache） | `self._cache_manager is not None` AND NOT force_refresh | manager 为 None / force_refresh |

#### 5.4.3 物化写入触发

外部 Provider 成功后（Step 4 命中），DataRouter 触发：
1. **物化写入**：`LocalMongoAdapter.put(...)` → `03_data_ud_*`
2. **缓存写入**：`CacheManager.put(...)` → `03_data_ud_cache_*`

两者写入失败均 catch-and-log，不影响查询返回值。

### 5.5 失败与回滚

#### 5.5.1 失败语义矩阵

| 场景 | DataResult.provider | DataResult.freshness | DataResult.source_trace | 物化/Cache 写入 |
|---|---|---|---|---|
| TA-CN 命中 | "ta_cn_internal" | label(...) | `["ta_cn_internal(ok)"]` | 不写入（TA-CN 已有） |
| 物化命中 | "ud_materialized" | "cached" | `["ta_cn_internal(empty)", "ud_materialized(ok)"]` | 不写入 |
| Cache 命中 | 原始 provider | "cached" | `[..., "cache(ok)"]` | 不写入 |
| 外部成功 | "tushare"/"akshare" | label(...) | 完整链 | ✅ 物化 + Cache 写入 |
| 全部失败 | "error" | "empty" | 完整链 | 不写入 |

#### 5.5.2 缓存失败不阻塞

- LocalMongoAdapter.get/put 异常 → catch-and-log → 继续 Step 3/4。
- CacheManager.get/put 异常 → catch-and-log → 继续 Step 4。
- **缓存层永远不阻断查询返回正确结果。**

#### 5.5.3 force_refresh 行为

`force_refresh=True`：
- 跳过 Step 1（TA-CN）。
- 跳过 Step 2（物化读取）。
- 跳过 Step 3（Cache 读取）。
- 直接走 Step 4（外部 Provider）。
- Step 4 成功后**仍写入**物化 + Cache（刷新后更新缓存）。

### 5.6 fake/mock/in-memory 验收边界

#### 5.6.1 研发阶段验证方式

| 组件 | 验证方式 |
|---|---|
| LocalMongoAdapter | mongomock（`mongomock.MongoClient`）作为 `mongo_db` 注入 |
| CacheManager | mongomock 作为 `mongo_db` 注入 |
| DataRouter Step 2/3 | 注入 mongomock-backed 的 LocalMongoAdapter / CacheManager |
| 外部 Provider | 沿用 1B-A 的 fake/stub provider（不做真实 API 调用） |
| TA-CN adapter | 沿用 1B-A 的 FakeTA_CNAdapter |

#### 5.6.2 fake/mock 验收点

- LocalMongoAdapter.get / put / invalidate 在 mongomock 上正确工作。
- CacheManager.get / put / invalidate 在 mongomock 上正确工作。
- DataRouter 四步路径在 fake provider + mongomock + FakeTA_CNAdapter 下全路径矩阵覆盖。
- TTL 过期行为：mongomock 的文档含 `expires_at`，LocalMongoAdapter/CacheManager 按时间判断过期。
- force_refresh 跳过 Step 1/2/3 但仍写入物化 + Cache。
- 缓存异常（mongomock 注入失败模拟）不阻断查询。

### 5.7 安全门禁

#### 5.7.1 集合 ownership 边界

| 集合类别 | 前缀 | ownership | Unified Data 权限 |
|---|---|---|---|
| TA-CN 既有主集合 | 无前缀 | TA-CN | **只读复用，禁止回写** |
| Unified Data 物化数据 | `03_data_ud_*` | Unified Data | 读写 |
| Query Cache | `03_data_ud_cache_*` | Unified Data | 读写下短 TTL 缓存 |
| Task Center 元数据 | `10_infra_tc_*` | Task Center | 不读写 |

**Unified Data 绝不回写、覆盖或在 TA-CN 既有无前缀集合中加字段污染。**

#### 5.7.2 生产 rollout 门禁

1B-B 研发阶段零 DDL。任何生产 collection / index / validator 创建需 Pascal 明确审批：

- `03_data_ud_*` 物化集合创建（按 domain.operation 组织）。
- `03_data_ud_cache_*` 缓存集合创建（按 operation 组织）。
- TTL 索引创建（`expires_at` 字段）。
- `cache_key` / `materialized_key` 唯一索引创建。

**这些均不在 1B-B 研发阶段执行。SPEC/Design 阶段需列出生产 rollout 清单，供 Pascal 审批后由独立 rollout 任务执行。**

---

## 6. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| 物化集合与 TA-CN 既有集合 ownership 混淆 | 低 | 高 | 命名空间前缀隔离（`03_data_ud_*` vs 无前缀）；LocalMongoAdapter 只读写自身前缀 | 审计检查 |
| Cache key 碰撞（不同 params 生成相同 key） | 低 | 中 | sha256 hash + params sort_keys；相同参数确定性 key | invalidate 重建 |
| TTL 过期行为与 FreshnessPolicy 不一致 | 中 | 中 | mongomock 单测全覆盖 TTL 过期；FreshnessPolicy 纯函数（1B-A 已交付） | force_refresh bypass |
| 缓存层异常阻断正常查询 | 中 | 高 | catch-and-log 全覆盖；缓存层永远返回 None/不阻断 | Router 跳过该 Step |
| 物化写入与查询返回的竞态（写入失败但已返回外部数据） | 低 | 低 | 物化写入异步或同步均可，失败 catch-and-log 不影响返回 | 下次查询重建 |
| mongomock 与真实 Mongo 行为偏差 | 中 | 中 | 生产 rollout 前补真实 Mongo smoke test（需 Pascal 审批） | — |
| DataRouter slot-in 破坏 1B-A 现有测试 | 低 | 中 | 保留 `None` 默认值向后兼容；守卫移除用条件化而非删除 | 回退守卫 |
| DDL 生产 rollout 未授权即执行 | 低 | 高 | 研发阶段零 DDL；SPEC 明确列出生产 rollout 清单需 Pascal 审批 | — |

---

## 7. 与 RFC-03-007 六项不变量的可追溯映射

RFC-03-007 §14 / SPEC-03-007 §0.2 定义了 Pascal 确认的六项架构基线不变量。本 RFC 必须与之保持一致：

| # | 不变量 | 1B-B 的体现 |
|---|---|---|
| 1 | **共享物理数据库**：Unified Data 与 TA-CN 共用 `tradingagents` | LocalMongoAdapter / CacheManager 读写同一物理库的 `03_data_ud_*` / `03_data_ud_cache_*` 集合；通过命名空间前缀隔离 |
| 2 | **Internal-First 读取路径**：TA-CN 既有 → UD 物化 → Query Cache → 外部 Provider | DataRouter Step 2（物化）+ Step 3（Cache）正式激活，四步路径完整生效；外部刷新失败不阻断内部已有数据读取 |
| 3 | **DSA 不是运行时数据源** | 1B-B 的物化/缓存层不涉及 DSA；外部链仍只含 `["tushare", "akshare"]` |
| 4 | **Collection Ownership 不可回写** | LocalMongoAdapter 只读写 `03_data_ud_*`；CacheManager 只读写 `03_data_ud_cache_*`；**绝不触碰 TA-CN 无前缀集合** |
| 5 | **Task Center 先行** | 1B-B 不实现 Task Center 集成、不创建 Job、不启用 cron/systemd；物化写入由 Router 内联触发，不依赖调度 |
| 6 | **三层语义分离** | TA-CN 既有资产（无前缀，只读）/ UD 物化（`03_data_ud_*`，可追溯）/ Query Cache（`03_data_ud_cache_*`，可丢弃）三者语义与命名空间清晰区分 |

---

## 8. 备选方案

### 8.1 方案 B：物化与 Cache 合并为单一层

- **优点**：减少一层 internal-first 路径；实现简单
- **缺点**：物化（可追溯、长 TTL）与 Cache（可丢弃、短 TTL）语义混在一起，无法区分"需要重建的持久数据"和"可随时丢弃的缓存"
- **不选原因**：RFC-03-007 §14 不变量 #6 明确要求三层语义分离；合并违反 Pascal 确认的架构基线

### 8.2 方案 C：物化写入由独立后台任务负责（非 Router 内联）

- **优点**：Router 更轻量；物化写入异步不增加查询延迟
- **缺点**：需要 Task Center 调度（Phase 5 范围）；1B-B 阶段 Task Center 未集成
- **不选原因**：违反不变量 #5（Task Center 先行）；1B-B 用 Router 内联触发物化写入（同步 catch-and-log），后续 Phase 5 可迁移到异步

### 8.3 方案 D：CacheManager 不缓存 TA-CN 结果（仅缓存外部结果）

- **优点**：减少 Cache 写入量；TA-CN 已有数据不需要缓存
- **缺点**：TA-CN 查询本身有 Mongo I/O 开销；高频查询同一标的时 Cache 可显著降低延迟
- **不选原因**：Query Cache 定位是"查询结果缓存"，不区分数据来源；是否缓存 TA-CN 结果由 SPEC/Design 阶段的 TTL 策略决定（TA-CN 域的 TTL 可设较短）

---

## 9. 验收标准

### 9.1 本 RFC 阶段验收（RFC 自身）

- [x] RFC 文件存在于 `docs/rfc/03_data/RFC-03-009-unified-data-phase-1b-persistence-plane.md`
- [x] RFC 明确 1B-B 的动机、范围、ownership、失败与回滚（§1-§5）
- [x] RFC 明确 fake/mock 验收边界与生产 rollout 门禁（§5.6 / §5.7）
- [x] RFC 与 RFC-03-007 的六项不变量可追溯映射（§7）
- [x] RFC 明确 LocalMongoAdapter / CacheManager 的定位与接口契约框架（§5.2 / §5.3）
- [x] RFC 明确物化数据与 Query Cache 的语义分离（§4.3）
- [x] RFC 明确 DataRouter slot-in 激活策略（§5.4）
- [x] RFC 明确缓存失败不阻断正常查询（§5.5.2）
- [x] RFC 明确失败语义继承 1B-A（DataResult.error，不抛 AllProvidersFailedError）（§2.4）
- [x] RFC 与 03-007/008 和已修订 1C 契约无矛盾（§7 / §2.4）
- [x] 中文输出，专业简洁

### 9.2 后续 SPEC/Design/Implement 阶段验收（供 T2 参考）

- [ ] LocalMongoAdapter / CacheManager 的精确公共接口、输入/输出、依赖注入方式
- [ ] `03_data_ud_*` 与 `03_data_ud_cache_*` 的数据信封、key 组成、TTL/freshness、读写/invalidate/force_refresh 行为
- [ ] DataRouter Step 2/3 激活的精确编排逻辑（守卫移除、激活条件、物化写入触发）
- [ ] allow-list / 幂等 / 静默 / 错误归类 / source_trace 行为契约
- [ ] 精确文件清单（必须到目录层级）+ fake/mongomock 测试矩阵 + 生产 Mongo rollout 门禁
- [ ] Cache hit 时外部调用为 0 的验证方法

### 9.3 明确不做清单（1B-B 不覆盖）

- [ ] ❌ 不做真实 Mongo 连接/写入/DDL（collection/index/validator 创建）
- [ ] ❌ 不做真实外部 API 调用（Tushare/AKShare fetch 仍用 fake/stub）
- [ ] ❌ 不实现 Task Center / 批量回填 / cron / systemd / 后台刷新调度
- [ ] ❌ 不读取/写入 DSA SQLite / StockDaily
- [ ] ❌ 不修改 TA-CN 子项目代码
- [ ] ❌ 不修改 Phase 1A 的 14 个域入口方法行为
- [ ] ❌ 不修改 RFC/SPEC/Design 文档模板
- [ ] ❌ 不修改 Phase 0/1A/1B-A 已有公共契约
- [ ] ❌ 不实现 QualityScorer / AuditLogger（Phase 2）

---

## 10. 开放问题

1. **物化写入是同步还是异步？**
   - 预期答案：1B-B 用同步写入（catch-and-log），因 mongomock 无延迟。生产环境若延迟敏感，Phase 5 可迁移到 Task Center 异步。SPEC/Design 阶段需明确。

2. **过期物化数据是否在 Step 2 返回？**
   - 预期答案：不返回过期物化（继续 Step 3/4）。但过期物化可作为 Cache 重建源（如 Step 4 成功后更新物化）。SPEC 阶段需明确过期判定逻辑。

3. **LocalMongoAdapter 是否需要 capability 映射表（类似 Router 的 `_TA_CN_CAPABILITY_METHOD_MAP`）？**
   - 预期答案：不需要。物化集合按 `domain.operation` 组织，LocalMongoAdapter 通过 collection_prefix + operation 名直接定位集合。SPEC 阶段需确认集合命名规则。

4. **CacheManager 是否缓存 TA-CN 结果？**
   - 预期答案：是。Query Cache 不区分数据来源。TA-CN 域的 TTL 由 FreshnessPolicy 定义。SPEC 阶段需确认 TA-CN 域的 TTL 是否需要特殊处理。

---

## 11. 参考资料（References）

- RFC-03-007：Unified Data Layer 总纲
- RFC-03-008：Phase 1B-A 查询平面与外部降级
- SPEC-03-007：Unified Data Layer 契约（§3.5 CacheManager / §4.7 CacheManager 签名 / §0.2 六项不变量）
- SPEC-03-008：Phase 1B-A 查询平面 SPEC（§4.1 DataRouter 增强版签名含 local_mongo_adapter / cache_manager slot）
- DESIGN-03-007：Unified Data Layer 总设计（§8.1 internal-first 完整路径 / §8.2 CacheManager 实现要点 / §8.3 FreshnessPolicy）
- DESIGN-03-008：Phase 1B-A 查询平面详细设计（§3.2.2 router.py 修改含 ValueError 守卫）
- Pipeline skill：`skills/infra/ai-coding-pipeline/SKILL.md`
