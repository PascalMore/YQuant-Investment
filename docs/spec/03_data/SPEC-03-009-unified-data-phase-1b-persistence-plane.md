# SPEC-03-009: Unified Data Phase 1B-B — 持久化缓存平面

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-14 |
| 最后更新 | 2026-07-16 |
| 来源 RFC | RFC-03-009（Phase 1B-B 持久化缓存平面） |
| 关联 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-008（Phase 1B-A 查询平面） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-008（Phase 1B-A 查询平面） |
| 关联 Design | DESIGN-03-007（Unified Data Layer 总设计）、DESIGN-03-008（Phase 1B-A 查询平面设计） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 版本号 | V0.2 |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

---

## 0. 基线锚定与语义修正

本 SPEC 继承 SPEC-03-007 / SPEC-03-008 的全部基线，只锁定 Phase 1B-B 必须新增或修正的措辞。

### 0.1 与 SPEC-03-007 / 03-008 的关系

- SPEC-03-007 定义了 unified_data 全局契约（SecurityId / DataResult / DataProvider / Registry / Router / CacheManager / FreshnessPolicy）。
- SPEC-03-008 定义了 1B-A 查询平面（DataRouter internal-first 编排、Provider 框架、TA-CN 映射）。
- 本 SPEC 只对 1B-B 范围内的组件（LocalMongoAdapter、CacheManager 持久化实现、物化/缓存集合、DataRouter Step 2/3 激活）制定可执行契约。
- SPEC-03-007 §4.7 的 CacheManager 签名（`mongo_uri` / `database` 构造参数）在本 SPEC 中被更新为 `mongo_db`（直接接收数据库句柄），以兼容 mongomock 测试。SPEC-03-007 的旧签名标记为 Phase 1B-B 前基线，本 SPEC 签名替代之。

### 0.2 关键语义修正：LocalMongoAdapter 的「只读」歧义

**orchestrator 审计指出 RFC §5.2 存在一处语义歧义**：RFC 标题/摘要称 LocalMongoAdapter「只读 `03_data_ud_*`」，但 §5.4.3、§5.6.2、§7 又规定外部成功后的 `LocalMongoAdapter.put()`、并测试 get/put/invalidate。

**本 SPEC 明确修正为**：

> **对 TA-CN 无前缀集合：严格只读，禁止任何写入。**
> **对 UD 自有 `03_data_ud_*` 集合：LocalMongoAdapter 具备受 allow-list 约束的读写能力。**
> **`put()` 仅在外部 Provider 成功后的物化路径中被调用，且以 catch-and-log 模式执行。生产写入/DDL 另需 Pascal 审批。**

此修正统一了 RFC §5.2（摘要）与 §5.4.3/§5.6.2/§7（详细行为）的不一致。不再保留「只读」作为接口约束。

### 0.3 六项不变量逐条对应（SPEC-03-007 §0.2）

| # | 不变量 | 1B-B SPEC 落点 |
|---|---|---|
| 1 | 共享物理数据库 `tradingagents` | LocalMongoAdapter / CacheManager 读写同一物理库的 `03_data_ud_*` / `03_data_ud_cache_*`（§4.bis） |
| 2 | Internal-First 读取路径 | DataRouter Step 2（物化）+ Step 3（Cache）正式激活，四步路径完整生效（§3.1） |
| 3 | DSA 不是运行时数据源 | 外部链仍只含 `["tushare", "akshare"]`；物化/缓存层不涉及 DSA（§7.1） |
| 4 | Collection Ownership 不可回写 | LocalMongoAdapter 只读写 `03_data_ud_*`；CacheManager 只读写 `03_data_ud_cache_*`；绝不触碰 TA-CN 无前缀集合（§0.2） |
| 5 | Task Center 先行 | 物化写入由 Router 内联触发（同步 catch-and-log），不依赖 Task Center 调度（§3.4） |
| 6 | 三层语义分离 | TA-CN 无前缀（只读）/ UD 物化 `03_data_ud_*`（可追溯）/ Query Cache `03_data_ud_cache_*`（可丢弃），命名空间隔离（§4.bis） |

---

## 1. 需求摘要

将 RFC-03-009 的持久化缓存平面需求落为可执行契约，核心交付 6 件事：

1. **LocalMongoAdapter** 全新实现：受 allow-list 约束的 UD 物化数据读写组件（`03_data_ud_*`），只被 Router 作为 Step 2 调用。对外部调用方无感知。
2. **CacheManager** 全新实现（持久化版）：短 TTL Query Cache 的读写组件（`03_data_ud_cache_*`），仅被 Router 作为 Step 3 调用。**SPEC-03-007 §4.7 的 `mongo_uri` 版签名被本 SPEC 的 `mongo_db` 版替代**，以兼容 mongomock 测试。
3. **DataRouter Step 2/3 激活**：移除 ValueError 守卫，注入 LocalMongoAdapter / CacheManager 实例后 Step 2/3 正式运行。
4. **internal-first 完整四步读优先顺序**：TA-CN → UD 物化 → Query Cache → 外部 Provider；Cache hit 时外部调用为 0。
5. **物化写入链**：外部 Provider 成功（Step 4）后 DataRouter 内联触发 `LocalMongoAdapter.put()` + `CacheManager.put()`，同步 catch-and-log。
6. **缓存失败不阻塞**：LocalMongoAdapter / CacheManager 的全部分 I/O 失败被 catch-and-log，不影响 DataRouter 返回正确结果。

全部组件用 mongomock + fake provider + FakeTA_CNAdapter 验证，不依赖真实 Mongo 连接/写入/DDL。

---

## 2. 范围

### 2.1 In Scope

- [ ] LocalMongoAdapter 实现：`__init__` / `get` / `put` / `invalidate`，仅操作 `03_data_ud_*` 集合。
- [ ] CacheManager 实现（持久化版）：`__init__` / `get` / `put` / `invalidate`，仅操作 `03_data_ud_cache_*` 集合。
- [ ] `03_data_ud_*` 与 `03_data_ud_cache_*` 数据信封定义：document schema、key 组成、TTL/freshness 行为。
- [ ] DataRouter 构造函数守卫移除：直接删除两项 ValueError guard，`None` 默认值使 Step 2/3 自然跳过，由 helper 写具名 skip trace。
- [ ] DataRouter Step 2/3 编排逻辑：激活条件、读优先顺序、过期判定、force_refresh/provider 影响。
- [ ] 物化写入触发链：外部 Provider 成功后的同步写入 + CacheManager.put()、catch-and-log。
- [ ] 缓存失败不阻塞行为：get/put 异常全部 catch-and-log，不阻断 Step 链。
- [ ] 源数据信封的 `expires_at` 字段用于 TTL 过期判定（mongomock 层面按系统时间判断）。
- [ ] 全量文件清单（新增/修改/测试）精确到文件路径。
- [ ] fake/mongomock 测试矩阵覆盖全部行为契约。
- [ ] 生产 Mongo rollout 清单（collection / index / validator 定义），仅作审批参考，1B-B 研发阶段不执行。

### 2.2 Out of Scope（1B-B 不做）

- [ ] ❌ 不做真实 Mongo 连接/写入/DDL（collection/index/validator 创建）— 全部用 mongomock。
- [ ] ❌ 不做真实外部 API 调用（Tushare/AKShare fetch 仍用 1B-A 的 fake/stub）。
- [ ] ❌ 不创建或修改任何 MongoDB 集合（研发阶段零 DDL）。
- [ ] ❌ 不实现 Task Center / 批量回填 / cron / systemd / 后台刷新调度。
- [ ] ❌ 不读取或写入 DSA SQLite / StockDaily。
- [ ] ❌ 不修改 TA-CN 子项目代码（`skills/apps/TradingAgents-CN/**`）。
- [ ] ❌ 不修改 Phase 1A 的 14 个域入口方法行为。
- [ ] ❌ 不修改 RFC/SPEC/Design 文档模板。
- [ ] ❌ 不修改 Phase 0/1A/1B-A 已有公共契约（SecurityId / DataResult / DataProvider / Capability / Registry / FreshnessPolicy）。
- [ ] ❌ 不实现异步物化写入（Phase 5 范围；1B-B 用同步 catch-and-log）。
- [ ] ❌ 不实现 QualityScorer / AuditLogger（Phase 2）。
- [ ] ❌ 不迁移 `_TA_CN_CAPABILITY_METHOD_MAP` 到配置文件（1B-B 保持硬编码常量不变）。

---

## 3. 功能规格

### 3.1 DataRouter Step 2/3 激活

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| DR-201 | Step 2 激活 | `self._local_mongo_adapter is not None` AND provider 未指定外部；force_refresh 于 helper 内部处理（记录 skipped trace，不调底层 get()） | 查 `03_data_ud_*`，命中返回 DataResult | adapter 为 None / provider 指定外部 → 跳过 Step 2；force_refresh 时 helper 内记录 skipped trace 后返回 None |
| DR-202 | Step 2 命中未过期 | LocalMongoAdapter.get() 返回非空且 `expires_at > now` | `DataResult(provider="ud_materialized", freshness="cached")` | — |
| DR-203 | Step 2 命中但过期 | LocalMongoAdapter.get() 返回非空但 `expires_at <= now` | 不返回过期数据，继续 Step 3 | 过期物化不返回，不删除（供后续重建） |
| DR-204 | Step 2 未命中 | LocalMongoAdapter.get() 返回 None | 继续 Step 3 | — |
| DR-205 | Step 2 异常 | LocalMongoAdapter.get() 抛异常 | catch-and-log, trace 记录 `"ud_materialized(error: ...)"`, 继续 Step 3 | 不阻断 |
| DR-206 | Step 3 激活 | `self._cache_manager is not None`；force_refresh 于 helper 内部处理（记录 skipped trace，不调底层 get()） | 查 `03_data_ud_cache_*`，命中返回 DataResult | manager 为 None → 跳过 Step 3；force_refresh 时 helper 内记录 skipped trace 后返回 None |
| DR-207 | Step 3 命中未过期 | CacheManager.get() 返回非空 + 未过期 | `DataResult(freshness="cached")`，provider 保持原值 | — |
| DR-208 | Step 3 命中但过期 | CacheManager.get() 返回非空但过期 | 继续 Step 4 | 过期缓存不返回 |
| DR-209 | Step 3 未命中 | CacheManager.get() 返回 None | 继续 Step 4 | — |
| DR-210 | Step 3 异常 | CacheManager.get() 抛异常 | catch-and-log, trace 记录 `"cache(error: ...)"`, 继续 Step 4 | 不阻断 |
| DR-211 | 物化写入触发 | Step 4 外部 Provider 成功 | 同步调 LocalMongoAdapter.put() + CacheManager.put() | 写入失败 catch-and-log，不影响查询返回值 |
| DR-212 | force_refresh 不阻断物化写入 | Step 4 成功时无论跳过 Step 2/3 与否 | 仍写入物化 + Cache | — |
| DR-213 | Step 2 跳过时 trac e 记录 | adapter 为 None 或 force_refresh | trace 记录 `"ud_materialized(skipped: ...)"` | — |
| DR-214 | Step 3 跳过时 trace 记录 | manager 为 None 或 force_refresh | trace 记录 `"cache(skipped: ...)"` | — |

### 3.2 LocalMongoAdapter

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| LM-101 | 构造 | mongo_db, collection_prefix, freshness | 实例 | mongo_db 可为 mongomock 或生产 PyMongo Database |
| LM-102 | get 命中未过期 | security_id, domain, operation, params | 物化 DataResult（含完整 data payload） | 未命中/过期返回 None |
| LM-103 | get 命中但过期 | 上述 | None（过期不返回） | 文档含 `expires_at`，按系统时间判断 |
| LM-104 | get 异常 | 任何 | catch-and-log, 返回 None | 不抛异常给调用方 |
| LM-105 | put 写入 | security_id, domain, operation, params, result | None（无返回） | 写入物化集合，设置 fetched_at/expires_at。失败 catch-and-log |
| LM-106 | put 幂等 | 同一 security_id+domain+operation+params_hash | upsert（替换已有物化记录） | — |
| LM-107 | invalidate 全量 | 无参数 | 清空 `03_data_ud_*` 全部文档 | 返回删除条数 |
| LM-108 | invalidate 按 security_id | security_id | 只删该标的物化 | 返回删除条数 |
| LM-109 | invalidate 按 domain | domain | 只删该域物化 | 返回删除条数 |
| LM-110 | invalidate 异常 | 任何 | catch-and-log, 返回 0 | 不阻断调用方 |

### 3.3 CacheManager（持久化版）

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| CM-101 | 构造 | mongo_db, collection_prefix, freshness | 实例 | mongo_db 可为 mongomock 或生产 PyMongo Database |
| CM-102 | get 命中未过期 | security_id, domain, operation, params | 缓存的 DataResult | 未命中/过期返回 None |
| CM-103 | get 过期 | 上述 | None（过期不返回） | expires_at 按系统时间判定 |
| CM-104 | get 异常 | 任何 | catch-and-log, 返回 None | 不阻断 |
| CM-105 | put 写入 | security_id, domain, operation, params, result | None | 缓存集合写入，失败 catch-and-log |
| CM-106 | put 幂等 | 同一 cache_key | upsert（替换旧缓存） | — |
| CM-107 | invalidate | security_id=None, domain=None | 删除匹配的缓存文档 | 按参数组合过滤删除，返回删除条数 |
| CM-108 | invalidate 异常 | 任何 | catch-and-log, 返回 0 | 不阻断 |
| CM-109 | force_refresh bypass | CacheManager 不对外暴露 force_refresh；由 Router 负责跳过 Step 3 | — | — |

### 3.4 物化写入触发链（Router 内联）

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| MW-101 | 外部 Provider 成功后触发 | Step 4 返回 DataResult(provider="tushare"/"akshare") | 同步调 LocalMongoAdapter.put() + CacheManager.put() | put 异常 catch-and-log，查询返回值不受影响 |
| MW-102 | 物化集合写入 | LocalMongoAdapter.put(security_id, domain, operation, params, result) | 写入 `03_data_ud_*` 文档 | 失败不影响 Step 4 返回 |
| MW-103 | Cache 集合写入 | CacheManager.put(同上) | 写入 `03_data_ud_cache_*` 文档 | 失败不影响 Step 4 返回 |
| MW-104 | 写入顺序 | 先物化后缓存 | — | 两者独立，一个失败不影响另一个 |
| MW-105 | TA-CN 命中的不写入 | Step 1 命中 | 不触发物化/Cache 写入 | TA-CN 已有数据不需要物化 |

---

## 4. 数据与接口契约

### 4.1 DataRouter 构造函数变更

```python
class DataRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        config: UnifiedDataConfig | None = None,
        *,
        ta_cn_adapter: Any = None,
        local_mongo_adapter: "LocalMongoAdapter | None" = None,  # [1B-B] 可注入
        cache_manager: "CacheManager | None" = None,            # [1B-B] 可注入
        freshness: FreshnessPolicy | None = None,
        external_fallback_chains: dict[str, list[str]] | None = None,
    ) -> None: ...
```

**与 1B-A 的差异**：

| 变化点 | 1B-A 状态 | 1B-B 状态 |
|---|---|---|
| `local_mongo_adapter` | None 必须（ValueError 守卫） | 允许注入；None 时 Step 2 跳过 |
| `cache_manager` | None 必须（ValueError 守卫） | 允许注入；None 时 Step 3 跳过 |
| ValueError 守卫 | 抛 ValueError 阻止非 None | **移除**（两行硬守卫代码删除）；保留 None 默认值向后兼容 |

> **守卫移除策略**：直接删除 `if local_mongo_adapter is not None: raise ValueError(...)` 和 `if cache_manager is not None: raise ValueError(...)` 两段代码。不保留条件化分支——因为 1B-A 测试已不存在（1B-A 测试全部传 None），且移除后 `None` 默认值本身即可确保 Step 2/3 跳过（`if self._local_mongo_adapter is not None` 条件自然返回 False）。不需要 Feature Flag。

### 4.2 LocalMongoAdapter

```python
class LocalMongoAdapter:
    """受 allow-list 约束的 UD 物化数据读写组件（03_data_ud_*）。

    Step 2 of internal-first path. Read-write on UD's own 03_data_ud_*
    collections (with allow-list constraint). Get/put/invalidate all
    catch-and-log on failure — never blocks the Router.

    Strictly read-only on TA-CN prefixless collections (enforced by
    collection_prefix being locked to 03_data_ud_*).
    """

    def __init__(
        self,
        mongo_db: Any,                              # 数据库句柄（生产 pymongo.database.Database 或 mongomock.database.Database）
        collection_prefix: str = "03_data_ud_",
        freshness: "FreshnessPolicy | None" = None,
    ) -> None: ...

    def get(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: Mapping[str, Any] | None = None,
    ) -> "DataResult | None": ...
    # 返回未过期的物化 DataResult；未命中/过期返回 None。
    # 异常时 catch-and-log，返回 None。

    def put(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: Mapping[str, Any] | None,
        result: DataResult,
    ) -> None: ...
    # 物化写入外部 Provider 成功后的 DataResult。
    # upsert 模式（materialized_key 匹配时替换）。
    # 写入失败 catch-and-log，不影响查询返回值。

    def invalidate(
        self,
        security_id: "SecurityId | None" = None,
        domain: str | None = None,
    ) -> int: ...
    # 批量失效物化数据，返回删除条数。
    # security_id=None + domain=None → 清空全部 03_data_ud_*
    # security_id 指定 → 只删除该标的
    # domain 指定 → 只删除该域
    # 组合过滤：AND 语义
```

**构造参数语义**：

| 参数 | 说明 |
|---|---|
| `mongo_db` | MongoDB 数据库句柄（`pymongo.database.Database` 或 `mongomock.database.Database`）。兼容生产与测试。**不接收 mongo_uri**（由调用方负责建立连接）。 |
| `collection_prefix` | 锁定为 `"03_data_ud_"`。**运行时不允许自定义**，以硬编码确保不误读到 TA-CN 无前缀集合。 |
| `freshness` | FreshnessPolicy 实例，用于计算 `expires_at`。None 时用默认 FreshnessPolicy()。 |

**集合命名规则**：

- 集合名 = `collection_prefix + operation`
- 示例：`03_data_ud_kline_daily`、`03_data_ud_income_statement`
- **不**加入 security_id 或 domain 到集合名——同一 operation 的所有标的物化在同一集合中，按 `materialized_key` 或 `(security_id, params_hash)` 唯一标识。

### 4.3 CacheManager（持久化版签名）

```python
class CacheManager:
    """短 TTL Query Cache（03_data_ud_cache_*）。

    Step 3 of internal-first path. Read-write, but failures are
    catch-and-log — cache issues never block a query.

    Accepts a ready mongo_db handle (pymongo or mongomock) instead of
    a connection URI to enable seamless testing with mongomock.
    """

    def __init__(
        self,
        mongo_db: Any,                              # 数据库句柄（生产或 mongomock）
        collection_prefix: str = "03_data_ud_cache_",
        freshness: "FreshnessPolicy | None" = None,
    ) -> None: ...

    def get(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: Mapping[str, Any] | None = None,
    ) -> "DataResult | None": ...
    # 返回未过期的缓存 DataResult；未命中/过期返回 None。
    # 异常时 catch-and-log，返回 None。

    def put(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: Mapping[str, Any] | None,
        result: DataResult,
    ) -> None: ...
    # 缓存写入成功查询的 DataResult（不区分数据来源：TA-CN / 物化 / 外部均可缓存）。
    # upsert 模式（cache_key 匹配时替换）。
    # 写入失败 catch-and-log。

    def invalidate(
        self,
        security_id: "SecurityId | None" = None,
        domain: str | None = None,
    ) -> int: ...
    # 批量失效缓存，返回删除条数。
    # 同 LocalMongoAdapter.invalidate 语义。
```

**构造参数语义**：

| 参数 | 说明 |
|---|---|
| `mongo_db` | MongoDB 数据库句柄。**不接收 mongo_uri**，以兼容 mongomock 测试。 |
| `collection_prefix` | 锁定为 `"03_data_ud_cache_"`。运行时不允许自定义。 |
| `freshness` | FreshnessPolicy 实例，用于计算缓存 TTL 和 `expires_at`。None 时用默认。 |

> **与 SPEC-03-007 §4.7 的关系**：SPEC-03-007 的 CacheManager 构造签名接收 `mongo_uri`（字符串）和 `database`（字符串）。本 SPEC 将其改为 `mongo_db`（数据库句柄）。原因：
> 1. mongomock 不兼容 `mongo_uri` 连接串模式——mongomock 无 URI 解析。
> 2. 调用方（DataRouter 创建方或工厂函数）自行管理数据库连接，CacheManager 只接收已就绪的句柄。
> 3. **向后兼容**：本地没有已存在的 CacheManager 调用方（1B-A 未实现 CacheManager），因此无兼容负担。

**Cache key 组成**：

```
cache_key = sha256(
    f"{str(security_id)}|{domain}|{operation}|{json.dumps(params, sort_keys=True)}"
)[:32]
```

- 确定性：相同参数生成相同 key。
- `params` 按 `sort_keys=True` JSON 序列化，确保顺序无关性。
- key 存储在文档的 `cache_key` 字段，作为唯一索引（生产 rollout 时创建）。

### 4.4 DataRouter.query() 编排伪逻辑（含 Step 2/3）

```
query(domain, operation, sid, provider=None, force_refresh=False, params):
    capability = f"{domain}.{operation}"
    trace = []
    ts = fetched_at or now()

    # provider 参数优先
    if provider == "ta_cn_internal":
        return _query_ta_cn_only(sid, capability, params, trace, ts)
    if provider is not None:
        return _query_external_single(provider, sid, capability, params, trace, ts)

    # === internal-first 完整四步 ===

    # Step 1: TA-CN
    if not force_refresh and self._ta_cn_adapter is not None:
        result = _try_ta_cn(sid, capability, params, trace, ts)
        if result is not None:
            return result                              # 命中或 TA-CN 覆盖但空

    # Step 2: [1B-B] UD 物化
    # force_refresh 由 helper 内部处理（记录 skipped trace，不调底层 get()）
    if self._local_mongo_adapter is not None:
        result = _try_materialized(sid, domain, operation, params, trace, ts, force_refresh=force_refresh)
        if result is not None:
            return result                              # 物化命中未过期

    # Step 3: [1B-B] Query Cache
    # force_refresh 由 helper 内部处理（记录 skipped trace，不调底层 get()）
    if self._cache_manager is not None:
        result = _try_cache(sid, domain, operation, params, trace, ts, force_refresh=force_refresh)
        if result is not None:
            return result                              # Cache 命中未过期

    # Step 4: 外部 Provider
    result = _query_external_chain(sid, capability, params, trace, ts)
    if result.provider != "error":
        _materialize(sid, domain, operation, params, result)   # 物化 + Cache 写入
    return result
```

**`_try_materialized` 行为**：

```python
def _try_materialized(sid, domain, operation, params, trace, ts, force_refresh=False):
    if force_refresh:
        trace.append("ud_materialized(skipped: force_refresh)")
        return None
    try:
        cached = self._local_mongo_adapter.get(sid, domain, operation, params)
        if cached is not None:
            trace.append("ud_materialized(ok)")
            return cached  # provider="ud_materialized", freshness="cached"
        trace.append("ud_materialized(miss)")
        return None
    except Exception as e:
        trace.append(f"ud_materialized(error: {e})")
        return None
```

**`_try_cache` 行为**：

```python
def _try_cache(sid, domain, operation, params, trace, ts, force_refresh=False):
    if force_refresh:
        trace.append("cache(skipped: force_refresh)")
        return None
    try:
        cached = self._cache_manager.get(sid, domain, operation, params)
        if cached is not None:
            trace.append("cache(ok)")
            return cached  # freshness="cached", provider=原始 provider
        trace.append("cache(miss)")
        return None
    except Exception as e:
        trace.append(f"cache(error: {e})")
        return None
```

**`_materialize` 行为**：

```python
def _materialize(sid, domain, operation, params, result):
    try:
        self._local_mongo_adapter.put(sid, domain, operation, params, result)
    except Exception:
        pass  # catch-and-log
    try:
        self._cache_manager.put(sid, domain, operation, params, result)
    except Exception:
        pass  # catch-and-log
```

### 4.5 错误/降级矩阵（含 1B-B 新增路径）

| 场景 | DataResult.provider | DataResult.freshness | DataResult.source_trace | DataResult.warnings | 物化/Cache 写入 |
|---|---|---|---|---|---|
| TA-CN 命中 | `"ta_cn_internal"` | `label(...)` | `["ta_cn_internal(ok)"]` | `[]` | 不写入 |
| TA-CN 空 + 物化命中 | `"ud_materialized"` | `"cached"` | `["ta_cn_internal(empty)", "ud_materialized(ok)"]` | `[]` | 不写入 |
| TA-CN 空 + 物化空 + Cache 命中 | 原始 provider | `"cached"` | `[..., "cache(ok)"]` | `[]` | 不写入 |
| TA-CN 空 + 物化空 + Cache 空 + 外部成功 | `"tushare"` / `"akshare"` | `label(...)` | `[..., "tushare(ok)"]` | `[]` | ✅ |
| TA-CN 空 + 物化命中过期 + Cache 空 + 外部成功 | `"tushare"` | `label(...)` | `["ta_cn_internal(empty)", "ud_materialized(stale)", "cache(miss)", "tushare(ok)"]` | `[]` | ✅（更新过期物化） |
| TA-CN 异常 + 物化异常 + Cache 空 + 外部成功 | `"akshare"` | `label(...)` | `["ta_cn_internal(error: ...)", "ud_materialized(error: ...)", "cache(miss)", "akshare(ok)"]` | `["ta_cn_internal error...", "ud_materialized error..."]` | ✅ |
| 全部内部空 + 全外部失败 | `"error"` | `"empty"` | `[..., "tushare(error: ...)", "akshare(error: ...)"]` | `["all external providers failed"]` | 不写入 |
| force_refresh + 外部成功 | `"tushare"` | `label(...)` | `["ud_materialized(skipped: force_refresh)", "cache(skipped: force_refresh)", "tushare(ok)"]` | `[]` | ✅ |
| provider="tushare" | `"tushare"` | `label(...)` | `["tushare(ok)"]` | `[]` | ✅（写入物化+Cache） |

---

## 4.bis 持久化契约

### 4.bis.1 `03_data_ud_*` 物化集合

**存储对象**：`tradingagents.03_data_ud_{operation}`

**文档信封**：

| 字段 | 类型 | 必填 | 默认/派生规则 | 生命周期/TTL | 隐私级别 |
|---|---|---|---|---|---|
| `_id` | ObjectId | 是 | MongoDB 自动生成 | 随文档删除 | L1 |
| `materialized_key` | string(64) | 是 | `sha256(f"{security_id}\|{domain}\|{operation}\|{params_hash}")[:64]` | 永久（upsert 替换） | L1 |
| `security_id` | string | 是 | SecurityId.__str__()，格式 "CN:600519" | — | L1 |
| `domain` | string | 是 | 如 "market_data"、"financial" | — | L1 |
| `operation` | string | 是 | 如 "kline_daily"、"income_statement" | — | L1 |
| `params_hash` | string(32) | 是 | `md5(json.dumps(params, sort_keys=True))[:32]` | — | L1 |
| `data` | Any | 是 | 序列化后的 payload（pd.DataFrame 转 dict/list 或直接存） | — | L1~L2（按具体数据的隐私级别） |
| `provider` | string | 是 | 实际 provider name，如 "tushare" | — | L1 |
| `fetched_at` | ISO datetime | 是 | 查询实际发生时的时间戳 | — | L1 |
| `data_date` | ISO date(string) | 否 | 业务日期 "YYYY-MM-DD" | — | L1 |
| `freshness_at_write` | string | 否 | 写入时的 freshness 标签 | — | L1 |
| `source_trace` | string[] | 是 | 完整来源链，同 DataResult.source_trace | — | L1 |
| `schema_version` | string | 是 | 固定 "1.0" | — | L1 |
| `materialized_at` | ISO datetime | 是 | 物化写入时间 | — | L1 |
| `expires_at` | ISO datetime | 是 | `materialized_at + FreshnessPolicy.get_ttl(domain)` | 过期后 Read 路径不返回；由 TTL 索引自动清理（生产 rollout） | L1 |

**索引**（生产 rollout 审批项，不在 1B-B 研发阶段执行）：

| 索引名称 | 字段 | 唯一性 | 说明 |
|---|---|---|---|
| `idx_materialized_key` | `{materialized_key: 1}` | 唯一 | upsert 查找键 |
| `idx_expires_at` | `{expires_at: 1}` | 否 | TTL 过期自动清理（MongoDB TTL index） |
| `idx_security_id` | `{security_id: 1, domain: 1, operation: 1}` | 否 | 按标的+域查询优化 |
| `idx_operation` | `{operation: 1, expires_at: 1}` | 否 | invalidate 按 operation 过滤 |

### 4.bis.2 `03_data_ud_cache_*` 缓存集合

**存储对象**：`tradingagents.03_data_ud_cache_{operation}`

**文档信封**：

| 字段 | 类型 | 必填 | 默认/派生规则 | 生命周期/TTL | 隐私级别 |
|---|---|---|---|---|---|
| `_id` | ObjectId | 是 | MongoDB 自动生成 | 随文档删除 | L1 |
| `cache_key` | string(32) | 是 | `sha256(f"{security_id}\|{domain}\|{operation}\|{json.dumps(params, sort_keys=True)}")[:32]` | 永久（upsert 替换） | L1 |
| `security_id` | string | 是 | SecurityId.__str__() | — | L1 |
| `domain` | string | 是 | 如 "market_data" | — | L1 |
| `operation` | string | 是 | 如 "kline_daily" | — | L1 |
| `params_hash` | string(32) | 是 | md5 哈希 | — | L1 |
| `data` | Any | 是 | 序列化 DataResult.data | — | L1~L2 |
| `provider` | string | 是 | 原始 provider name | — | L1 |
| `fetched_at` | ISO datetime | 是 | 查询时的时间戳 | — | L1 |
| `data_date` | ISO date(string) | 否 | 业务日期 | — | L1 |
| `source_trace` | string[] | 是 | 完整来源链 | — | L1 |
| `cached_at` | ISO datetime | 是 | 缓存写入时间 | — | L1 |
| `expires_at` | ISO datetime | 是 | `cached_at + FreshnessPolicy.get_ttl(domain)` | 过期后 Read 返回 None；TTL 索引自动清理 | L1 |

**索引**（生产 rollout 审批项，不在 1B-B 研发阶段执行）：

| 索引名称 | 字段 | 唯一性 | 说明 |
|---|---|---|---|
| `idx_cache_key` | `{cache_key: 1}` | 唯一 | upsert 查找键 |
| `idx_cache_expires_at` | `{expires_at: 1}` | 否 | TTL 索引 |
| `idx_cache_security_id` | `{security_id: 1, domain: 1}` | 否 | invalidate 查询优化 |

### 4.bis.3 研发阶段持久化策略

| 方面 | 策略 |
|---|---|
| 数据库连接 | mongomock (`mongomock.MongoClient().get_database("tradingagents")`) |
| 集合创建 | mongomock 自动创建（不显式调用 `create_collection`） |
| 索引创建 | 研发阶段**不创建**生产索引；mongomock 的 `create_index` 被 mock（索引相关验证收窄为「`expires_at` 字段满足过期行为」） |
| DDL | 零 DDL。`create_collection` / `create_index` / `create_view` / `create_collection_validator` 均不在 1B-B 研发代码中出现 |
| TTL 过期判定 | LocalMongoAdapter/CacheManager 在 get() 中比较 `expires_at` 与 `datetime.utcnow()`，不依赖 MongoDB TTL index |
| 生产 rollout | §12.2 列出生产 rollout 清单，供 Pascal 审批后由独立 rollout 任务执行 |

---

## 5. 行为契约（RFC-03-009 开放问题 → 代码层映射）

| # | RFC 决策/需求 | SPEC 落地点 | 章节 |
|---|---|---|---|
| 1 | LocalMongoAdapter 受 allow-list 约束的读写（非「只读」歧义） | §0.2 语义修正 + §4.2 接口签名含 put() | §0.2 / §4.2 |
| 2 | CacheManager 用 mongo_db 句柄（非 mongo_uri） | §4.3 构造参数为 mongo_db | §4.3 |
| 3 | 物化与缓存集合命名空间前缀 `03_data_ud_*` / `03_data_ud_cache_*` | §4.bis 数据信封 | §4.bis |
| 4 | DataRouter 守卫移除（删除而非条件化） | §4.1 明确删除 ValueError 两行 | §4.1 |
| 5 | 缓存失败不阻断查询 | DR-205 / DR-210 / LM-104 / CM-104 | §3.1 / §3.2 / §3.3 |
| 6 | 外部成功后的物化写入链 | MW-101 ~ MW-105 | §3.4 |
| 7 | 同步写入（catch-and-log） | _materialize() 伪逻辑 | §4.4 |
| 8 | force_refresh 不阻断物化写入 | DR-212 | §3.1 |
| 9 | TA-CN 命中的不写入物化 | MW-105 | §3.4 |
| 10 | 全部内部 + 外部失败返回 DataResult.error | 同 1B-A，Step 2/3 失败不改变 | §4.5 |
| 11 | 过期物化在 Step 2 不返回 | DR-203 | §3.1 |
| 12 | CacheManager 缓存 TA-CN 结果（不区分来源） | §3.3 / §4.4 _materialize | §3.3 |

### 5.1 RFC 开放问题 → SPEC 答案

| # | RFC 开放问题 | SPEC 答案 |
|---|---|---|
| 1 | 物化写入是同步还是异步？ | **同步**（catch-and-log）。因研发阶段用 mongomock 无延迟。生产若延迟敏感，Phase 5 迁移到 Task Center 异步。 |
| 2 | 过期物化数据是否在 Step 2 返回？ | **不返回**。过期物化不阻塞后续 Step，但过期数据仍保留在集合中（不被删除），供重建参考。 |
| 3 | LocalMongoAdapter 是否需要 capability 映射表？ | **不需要**。物化集合按 `operation` 命名（`03_data_ud_{operation}`），通过 `collection_prefix + operation` 直接定位。与 TA-CN 的 capability 映射无关。 |
| 4 | CacheManager 是否缓存 TA-CN 结果？ | **是**。Query Cache 不区分数据来源。TA-CN 域的 TTL 由 FreshnessPolicy 定义（`market_data` = 6h / `financial` = 24h）。 |


---

## 6. 配置契约

### 6.1 构造参数默认值

1B-B 不新增 YAML 配置键。所有构造参数通过 `UnifiedDataClient` 的工厂方法或构造器注入。默认值：

| 组件 | 参数 | 默认值 |
|---|---|---|
| LocalMongoAdapter | `collection_prefix` | `"03_data_ud_"`（常量） |
| LocalMongoAdapter | `freshness` | `FreshnessPolicy()` |
| CacheManager | `collection_prefix` | `"03_data_ud_cache_"`（常量） |
| CacheManager | `freshness` | `FreshnessPolicy()` |
| DataRouter | `local_mongo_adapter` | `None`（Step 2 跳过） |
| DataRouter | `cache_manager` | `None`（Step 3 跳过） |

### 6.2 物化/缓存集合密钥环境变量

1B-B 不新增 Tushare/AKShare 类型的外部密钥。MongoDB 连接由 `UnifiedDataClient` 工厂负责（沿用现有 `MONGO_URI` 环境变量），LocalMongoAdapter / CacheManager 只接收已就绪的数据库句柄。

---

## 7. 实现约束

### 7.1 依赖限制

- 不新增 pip 依赖。`pymongo` 已是项目依赖；`mongomock` 是测试依赖（列在 `dev-requirements.txt` 或 `pyproject.toml` 的 `[tool.pytest.ini_options]` 标记区域）。
- `pandas` 已是项目依赖。
- 不需要 `tushare`、`akshare` 等外部 provider 安装（由 1B-A 的 try/except 包裹）。

### 7.2 安全约束

- LocalMongoAdapter / CacheManager 不处理任何外部凭据。MongoDB 连接由上游工厂管理。
- 物化集合的 `data` 字段包含原始 payload（可能含隐私数据）；隐私级别标注为 L1~L2，具体取决于写入的 domain/operation 数据。**不持久化任何 L3 级别数据**（如用户个人身份信息）。
- `source_trace` 记录 provider 名称和状态，不含凭据或 token 信息。

### 7.3 禁止事项（不改动清单）

| 路径 | 理由 |
|---|---|
| `skills/apps/TradingAgents-CN/**` | TA-CN 子项目，只读复用 |
| `skills/research/daily_stock_analysis/**` | DSA 独立子系统 |
| `skills/data/data-pipeline/**` | ETL 管道，职责正交 |
| `skills/data/data_interface/**` | RFC-03-003 IReader/IWriter |
| `skills/infra/task_center/**` | 任务中心 |
| `skills/research/stock/**` | stock 框架是消费方 |
| 生产 MongoDB 集合的 schema validator / DDL / 索引 | 零 DDL 研发阶段 |
| cron / systemd / gateway / 外部推送配置 | 不碰调度和推送 |
| `skills/data/unified_data/models/**`（SecurityId / DataResult / Capability / Market） | Phase 0 公共契约不变 |
| `skills/data/unified_data/adapters/ta_cn_mongo_adapter.py` | TA-CN 只读复用 |
| `skills/data/unified_data/provider.py` | DataProvider ABC 不变 |
| `skills/data/unified_data/config.py` | UnifiedDataConfig 不变 |
| `skills/data/unified_data/exceptions.py` | AllProvidersFailedError 保留 |
| `skills/data/unified_data/freshness.py` | FreshnessPolicy 纯函数已交付，不修改 |
| Phase 1A 的 14 个域入口方法 | 行为不变 |
| RFC/SPEC/Design 文档模板 | 编排层不改模板（P-7） |
| SPEC-03-007 §4.7 签名 | 本 SPEC 的 CacheManager 签名替代旧签名，但旧 SPEC 文件不修改（兼容性说明见 §5.1） |

### 7.4 性能约束

- LocalMongoAdapter.get() / CacheManager.get() 必须有 MongoDB 索引支持（见 §4.bis），研发阶段用 mongomock 验证查询路径正确即可。
- put() 使用 upsert（单文档写入），不引入批量写入。
- catch-and-log 路径不允许阻塞：异常捕获后 `pass` 或 `logger.warning`，不做重试或等待。
- Step 2/3 的跳过判定为 O(1) 成员检查（`self._xxx is not None`）。

---

## 8. 文件改动清单

### 8.1 新增文件

| 路径 | 说明 |
|---|---|
| `skills/data/unified_data/local_mongo_adapter.py` | LocalMongoAdapter 实现（get/put/invalidate，mongomock 兼容） |
| `skills/data/unified_data/cache_manager.py` | CacheManager 持久化实现（get/put/invalidate，mongomock 兼容） |
| `tests/data/unified_data/test_local_mongo_adapter.py` | LocalMongoAdapter 单元测试（mongomock） |
| `tests/data/unified_data/test_cache_manager.py` | CacheManager 单元测试（mongomock） |
| `tests/data/unified_data/test_router_persistence.py` | DataRouter Step 2/3 + 物化写入链集成测试（mongomock + fake provider） |

### 8.2 修改文件

| 路径 | 修改内容 |
|---|---|
| `skills/data/unified_data/router.py` | 删除 ValueError 守卫 2 段（L161-170）；Step 2/3 编排逻辑：_try_materialized / _try_cache / _materialize 三个私有方法；query() 中插入 Step 2/3 调用点；`local_mongo_adapter` / `cache_manager` 属性暴露 |
| `skills/data/unified_data/__init__.py` | 导出 LocalMongoAdapter、CacheManager |

### 8.3 不改动文件（明确列出）

- 见 §7.3 禁止事项表。
- `skills/data/unified_data/freshness.py`：FreshnessPolicy 已交付且 `from_cache` 逻辑已就位，不修改。
- `skills/data/unified_data/client.py`：`UnifiedDataClient` 不修改（1B-B 不新增客户端参数）。
- `skills/data/unified_data/registry.py`：不修改（1B-B 不新增 registry 方法）。
- `skills/data/unified_data/provider.py`：DataProvider ABC 不修改。
- `skills/data/unified_data/config.py`：不修改。
- 测试基础设施：`conftest.py`、`fixtures/` 已提供 FakeProvider / FakeTA_CNAdapter，不修改。如需新增 fixture（如 FakeLocalMongoAdapter），在 `tests/data/unified_data/fixtures/` 目录下新增文件而非修改既有文件。

---

## 9. 测试要求

### 9.1 单元测试矩阵

#### LocalMongoAdapter（mongomock）

| 测试编号 | 测试目标 | 覆盖功能 | mock 方式 | 断言 |
|---|---|---|---|---|
| UT-LM-001 | get 命中未过期 | LM-102 | mongomock 写入样本文档 + fetche d_at 为 now | 返回 DataResult, provider="tushare" |
| UT-LM-002 | get 命中但过期 | LM-103 | mongomock 写入样本文档，fetched_at 远超 TTL | 返回 None |
| UT-LM-003 | get 未命中 | LM-102 | 空集合 | 返回 None |
| UT-LM-004 | get 异常返回 None | LM-104 | mongomock 注入异常（patch find_one） | 返回 None, 不抛异常 |
| UT-LM-005 | put 写入后 get 返回 | LM-105 | put() 后立即 get() | 返回同 data |
| UT-LM-006 | put 幂等 | LM-106 | 两次相同 put，第二次覆盖 | materialized_key 唯一，第二次替换 |
| UT-LM-007 | invalidate 全量 | LM-107 | 写入 3 条后 invalidate() | 删除 3 条, get 全 None |
| UT-LM-008 | invalidate 按 security_id | LM-108 | 写入 2 条同标的 + 1 条不同标的 | 删除 2 条, 不同标的仍可 get |
| UT-LM-009 | invalidate 按 domain | LM-109 | 写入 2 条不同 domain | 只删除指定 domain |
| UT-LM-010 | expires_at 按 FreshnessPolicy TTL 计算 | LM-102/103 | put 后检查文档 expires_at | `expires_at == materialized_at + TTL` |
| UT-LM-011 | collection_prefix 硬编码锁定 | ALL | 用错误 prefix 构造 | 不适用（prefix 不在构造参数暴露） |
| UT-LM-012 | 只读 TA-CN 前缀 | ALL | 注入指向无前缀集合的查询 | 不查询（LocalMongoAdapter 只操作 03_data_ud_*） |

#### CacheManager（mongomock）

| 测试编号 | 测试目标 | 覆盖功能 | mock 方式 | 断言 |
|---|---|---|---|---|
| UT-CM-001 | get 命中未过期 | CM-102 | mongomock 写入缓存文档 | 返回 DataResult |
| UT-CM-002 | get 过期 | CM-103 | 写入 + expired_at 已过 | 返回 None |
| UT-CM-003 | get 未命中 | CM-102 | 空集合 | 返回 None |
| UT-CM-004 | get 异常返回 None | CM-104 | patch find_one 抛异常 | 返回 None |
| UT-CM-005 | put 写入并取回 | CM-105 | put → get | 返回同 data |
| UT-CM-006 | put 幂等 (cache_key 重复) | CM-106 | 两次相同 put，第二次替换 | cache_key 唯一 |
| UT-CM-007 | invalidate 全量 | CM-107 | 写入 3 条 → invalidate() | 删除 3 条 |
| UT-CM-008 | invalidate 按 security_id | CM-107 | 同 LM-008 | — |
| UT-CM-009 | cache_key 确定性的 | CM-105 | 同 params 两次 put → cache_key 相等 | 相同 |
| UT-CM-010 | cache_key 含 params 顺序无关 | CM-105 | `{a:1,b:2}` vs `{b:2,a:1}` | 相同 cache_key |

#### DataRouter Step 2/3 + 物化链（mongomock + fake provider）

| 测试编号 | 测试目标 | 覆盖功能 | mock 方式 | 断言 |
|---|---|---|---|---|
| UT-PR-001 | Step 2 命中 | DR-201/202 | LocalMongoAdapter.get() 返回 DataResult | provider="ud_materialized" |
| UT-PR-002 | Step 2 过期 → Step 3 | DR-203 | LocalMongoAdapter.get() 返回过期数据 + CacheManager 空 | 进 Step 4 |
| UT-PR-003 | Step 2 空 → Step 3 命中 | DR-206/207 | LocalMongoAdapter 空 + CacheManager 命中 | freshness="cached" |
| UT-PR-004 | Step 2/3 空 → Step 4 | DR-204/209 | 两者全空 + 外部 Provider 成功 | provider="tushare" |
| UT-PR-005 | Step 2 异常 → Step 3 | DR-205 | LocalMongoAdapter.get() 抛异常 | trace 含 error, 进 Step 3 |
| UT-PR-006 | Step 3 异常 → Step 4 | DR-210 | CacheManager.get() 抛异常 | trace 含 error, 进 Step 4 |
| UT-PR-007 | force_refresh 跳过 Step 2/3 | DR-201/206 | force_refresh=True, LocalMongoAdapter/Cache 有数据 | 被跳过, trace 含 skipped |
| UT-PR-008 | 外部成功 → 物化写入 | MW-101/102 | Step 4 返回 DataResult(provider="tushare") | LocalMongoAdapter.get() 后可读出 |
| UT-PR-009 | 外部成功 → Cache 写入 | MW-103 | Step 4 返回 DataResult | CacheManager.get() 后可读出 |
| UT-PR-010 | 物化写入失败不影响查询 | MW-101 | LocalMongoAdapter.put() 抛异常 | DataResult 仍返回正确 |
| UT-PR-011 | Cache 写入失败不影响查询 | MW-101 | CacheManager.put() 抛异常 | DataResult 仍返回正确 |
| UT-PR-012 | TA-CN 命中不触发写入 | MW-105 | Step 1 命中 | 物化/Cache 空 |
| UT-PR-013 | provider 指定外部跳过 Step 2/3 | DR-201/206 | provider="tushare", LocalMongoAdapter/Cache 有数据 | 被跳过，trace 含 skipped |
| UT-PR-014 | 全部内部 + 外部失败 | 同 1B-A | 全部空 + 外部全部不可用 | DataResult.error |
| UT-PR-015 | source_trace 完整 chain | DR-213/214 | 全路径：TA-CN 空→物化空→Cache 空→外部成功 | trace 含 4 步记录 |
| UT-PR-016 | Step 2 adapter=None 跳过 | DR-201 | local_mongo_adapter=None | trace 含 "skipped: no adapter" |
| UT-PR-017 | Step 3 manager=None 跳过 | DR-206 | cache_manager=None | trace 含 "skipped: no manager" |

### 9.2 集成测试

| 测试编号 | 测试目标 |
|---|---|
| IT-PR-001 | 完整 internal-first：TA-CN 空 → 物化命中 → 返回（不调外部） |
| IT-PR-002 | 完整 internal-first：全空 → 外部成功 → 返回 + 物化/Cache 写入 |
| IT-PR-003 | force_refresh: 跳过 Step 1/2/3 → 外部成功 → 写入物化/Cache |
| IT-PR-004 | 全空 + 外部全失败 → DataResult.error |

### 9.3 回归测试

- 1B-A 的 DataRouter 测试（UT-DR-001 ~ UT-DR-012）全部通过（Step 2/3 adapter=None 时跳过，行为不变）。
- Phase 0 的 `test_router.py`（22 个测试函数）全部通过（ta_cn_adapter=None + local_mongo_adapter=None + cache_manager=None 时退化）。
- Phase 1A 的 `test_client_phase1a.py`（25 个测试函数）全部通过（client.py 不修改）。

### 9.4 不可自动化验证项

- 物化集合与缓存集合的生产索引创建脚本正确性（需 Pascal 审批后由独立 rollout 任务执行）。
- mongomock 与真实 MongoDB 行为偏差（`expires_at` 判定 vs TTL index 自动清理）。
- `LocalMongoAdapter.invalidate()` 在生产环境删除大量文档时的性能。

---

## 10. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | LocalMongoAdapter get/put/invalidate 在 mongomock 上正确工作 | UT-LM-001 ~ UT-LM-012 全通过 |
| A-002 | CacheManager get/put/invalidate 在 mongomock 上正确工作 | UT-CM-001 ~ UT-CM-010 全通过 |
| A-003 | DataRouter Step 2/3 激活后完整四步路径正确 | UT-PR-001 ~ UT-PR-017 全通过 |
| A-004 | 外部 Provider 成功后物化 + Cache 写入 | UT-PR-008 / UT-PR-009 |
| A-005 | 缓存失败（get/put 异常）不阻断查询 | UT-LM-004 / UT-CM-004 / UT-PR-005 / UT-PR-006 / UT-PR-010 / UT-PR-011 |
| A-006 | force_refresh 跳过 Step 2/3 | UT-PR-007 |
| A-007 | provider 指定外部跳过 Step 2/3 | UT-PR-013 |
| A-008 | TA-CN 命中不触发写入 | UT-PR-012 |
| A-009 | TTL 过期行为（物化/Cache 过期不返回） | UT-LM-002 / UT-CM-002 / UT-PR-002 |
| A-010 | source_trace 在 Step 2/3 正确记录 | UT-PR-015 / UT-PR-016 / UT-PR-017 |
| A-011 | 全部失败返回 error DataResult（不抛异常） | UT-PR-014 |
| A-012 | DataRouter ValueError 守卫已移除（3 个构造函数传非 None 不抛异常） | 代码审查 + UT-PR-001（adapter 非 None 成功） |
| A-013 | 零真实 Mongo 写入/DDL | grep "create_collection\|create_index\|insert_one\|update_one" 新增文件 → 0 命中（mongomock 自动创建除外） |
| A-014 | 零 TA-CN 无前缀集合写入 | grep "03_data_ud_" 之外的集合名 → 0 命中 |
| A-015 | 1B-A 测试回归通过 | UT-DR-001 ~ UT-DR-012 全通过 |
| A-016 | Phase 0 测试回归通过 | test_router.py 22/22 |
| A-017 | Phase 1A 测试回归通过 | test_client_phase1a.py 25/25 |
| A-018 | 不修改 TA-CN 子项目代码 | `git diff skills/apps/TradingAgents-CN/` → 空 |
| A-019 | 不修改 Phase 1A 14 个域入口方法 | `git diff client.py` → 空 |
| A-020 | 不新增 pip 依赖 | `git diff pyproject.toml` 无新增依赖行 |

---

## 11. 向后兼容

### 11.1 DataRouter 变更对 1B-A/Phase 0 的影响

| 变更点 | 影响 | 兼容性 |
|---|---|---|
| 删除 ValueError 两行守卫 | 1B-A 测试传 None 不触发；Phase 0 测试不传 local_mongo_adapter/cache_manager | ✅ 完全兼容 |
| Step 2/3 编排逻辑 | adapter/manager 为 None → 跳过（`if self._local_mongo_adapter is not None` 自然不进入） | ✅ 完全兼容 |
| local_mongo_adapter / cache_manager 属性暴露 | 新增属性，不破坏已有属性 | ✅ 完全兼容 |
| 新增 `_try_materialized` / `_try_cache` / `_materialize` | 私有方法，不影响外部调用 | ✅ 完全兼容 |

### 11.2 CacheManager 签名变更（相对于 SPEC-03-007 §4.7）

SPEC-03-007 §4.7 定义 CacheManager 构造签名为 `__init__(mongo_uri, database, freshness)`。本 SPEC 改为 `__init__(mongo_db, collection_prefix, freshness)`。

| 影响 | 评估 |
|---|---|
| 已有使用 SPEC-03-007 CacheManager 的代码 | **不存在** — 1B-A 未实现 CacheManager，无既有调用方 |
| 1B-B 测试用 mongomock | 兼容（`mongomock.MongoClient().get_database("tradingagents")` 作为 mongo_db 传入） |
| 生产构建 | 由 `UnifiedDataClient` 工厂或独立工厂函数创建，不暴露给外部调用方 |

### 11.3 UnifiedDataClient 不变

1B-B **不修改** `client.py`。`UnifiedDataClient` 的 query() 方法签名不变。LocalMongoAdapter / CacheManager 的注入通过 `DataRouter` 构造参数（由上层工厂负责组装），不改变客户端接口。

### 11.4 14 个域入口方法不变

Phase 1A 的 14 个域入口方法（`get_kline_daily()`、`get_realtime_quote()` 等）继续直连 TA-CN adapter，不走 DataRouter 的 internal-first 四步路径。1B-B 不改变此行为。这些入口方法的 `force_refresh` 和 `provider` 参数仍接受但当前忽略。

---

## 12. 风险与未解决问题

### 12.1 风险矩阵

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| 物化集合与 TA-CN 既有集合 ownership 混淆 | 低 | 高 | 命名空间前缀隔离（`03_data_ud_*`）；LocalMongoAdapter 只操作该前缀 |
| Cache key 碰撞（不同 params 生成相同 key） | 低 | 中 | sha256 前缀 32 位 + params sort_keys 确定性 key；碰撞概率可忽略 |
| mongomock 与真实 MongoDB 行为偏差 | 中 | 中 | 生产 rollout 前补真实 Mongo smoke test（需 Pascal 审批） |
| TTL 过期行为在 mongomock 中不准确 | 中 | 中 | LocalMongoAdapter/CacheManager 自己判断 expires_at（不依赖 MongoDB TTL index）；mongomock 测试覆盖 |
| 物化写入在真实 Mongo 中延迟影响 Step 4 返回 | 低 | 低 | 同步 catch-and-log 模式保证返回不受写入延迟影响 |
| DataRouter Step 2/3 跳过判定与 1B-A 测试冲突 | 低 | 中 | 保留 None 默认值；Step 2/3 用 `is not None` 条件自然跳过 |
| 生产增量 rollout 需要同时创建多个集合 | 低 | 中 | 见 §12.2 独立 rollout 清单 |
| force_refresh 后外部失败但已有过期物化被跳过 | 低 | 低 | force_refresh 意味着消费方明确要求最新数据；外部失败返回 error 是正确行为 |

### 12.2 生产 Mongo rollout 清单（Pascal 审批项，不在 1B-B 研发阶段执行）

| 操作 | 对象 | 说明 |
|---|---|---|
| `create_collection` | `03_data_ud_{operation}` 每 operation | 按现有 capability 列表（16 个 capability）创建物化集合 |
| `create_index` | `materialized_key` 唯一索引 | 物化集合 upsert 键 |
| `create_index` | `expires_at` | TTL 索引 |
| `create_collection` | `03_data_ud_cache_{operation}` 每 operation | 缓存集合 |
| `create_index` | `cache_key` 唯一索引 | 缓存 upsert 键 |
| `create_index` | 缓存 `expires_at` | TTL 索引 |

**生产 rollout 步骤纲要**（Design 阶段细化）：
1. Pascal 审批清单（本节）。
2. 运维脚本：`scripts/data/create_ud_collections.py`（含 idempotent create + TTL/唯一索引创建）。
3. 运维脚本执行：手动在 `tradingagents` 库上运行。
4. 生产 smoke test：用真实 Mongo 连接验证集合创建、索引创建、LocalMongoAdapter/CacheManager 基本读写。
5. 环境变量/配置更新：如 `MONGO_URI` 或独立 `UD_MONGO_URI` 指向生产数据库。

### 12.3 移交 Design 阶段的待决项

1. `DataRouter` 的 `_try_materialized` / `_try_cache` / `_materialize` 方法的具体代码位置（Router 类体内 vs 独立 helper 模块）。
2. `LocalMongoAdapter` 与 `CacheManager` 的工厂函数组织方式（独立工厂 vs `UnifiedDataClient` 工厂扩展 vs 调用方自行组装）。
3. 过期物化数据在集合中的保留策略：当前用 `expires_at` 字段和 Read 路径过滤（不返回过期），**不删除**过期文档；TTL index 在生产环境自动清理。Design 阶段确认此策略是否满足重建需求。
4. `03_data_ud_*` 的 `data` 字段序列化方式：直接存 DataFrame 的 `to_dict(orient="records")` 输出（list[dict]），还是需要额外 schema 验证。Design 阶段给出 JSON 兼容序列化方案。

---

## 13. 参考资料

- RFC-03-009：`docs/rfc/03_data/RFC-03-009-unified-data-phase-1b-persistence-plane.md`
- RFC-03-008：`docs/rfc/03_data/RFC-03-008-unified-data-phase-1b-query-plane.md`
- RFC-03-007：`docs/rfc/03_data/RFC-03-007-unified-data-layer.md`
- SPEC-03-008：`docs/spec/03_data/SPEC-03-008-unified-data-phase-1b-query-plane.md`
- SPEC-03-007：`docs/spec/03_data/SPEC-03-007-unified-data-layer.md`
- DESIGN-03-008：`docs/design/03_data/DESIGN-03-008-unified-data-phase-1b-query-plane.md`
- DESIGN-03-007：`docs/design/03_data/DESIGN-03-007-unified-data-layer.md`
- 现有代码：
  - `skills/data/unified_data/router.py`（Phase 1B-A DataRouter，755 行，Step 2/3 槽位已预留）
  - `skills/data/unified_data/freshness.py`（FreshnessPolicy 已交付，from_cache 逻辑就位）
  - `skills/data/unified_data/models/__init__.py`（SecurityId / DataResult / Capability）
  - `tests/data/unified_data/conftest.py`（FakeProvider / fixtures）
  - `tests/data/unified_data/fixtures/__init__.py`（FakeDatabase / FakeCollection）
