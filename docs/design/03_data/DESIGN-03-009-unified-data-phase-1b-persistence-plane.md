# DESIGN-03-009: Unified Data Phase 1B-B — 持久化缓存平面详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-14 |
| 最后更新 | 2026-07-14 |
| 来源 RFC | RFC-03-009（Phase 1B-B 持久化缓存平面） |
| 来源 SPEC | SPEC-03-009（Phase 1B-B 持久化缓存平面） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-008（Phase 1B-A 查询平面） |
| 关联 Design | DESIGN-03-007（Unified Data Layer 总设计）、DESIGN-03-008（Phase 1B-A 查询平面设计） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 版本号 | V0.1 |

---

## 1. 设计摘要

本设计为 Phase 1B-B（持久化缓存平面）提供**最小可实现的详细设计**，精度到文件路径、类签名、方法合同、时序图和测试矩阵。核心决策：

1. **LocalMongoAdapter 与 CacheManager 分离**：物化（`03_data_ud_*`, 可追溯）与 Query Cache（`03_data_ud_cache_*`, 可丢弃）保持独立组件，均接收 `mongo_db` 句柄而非 URI 以兼容 mongomock。
2. **DataRouter 守卫直接删除**（非条件化）：移除两行 ValueError 守卫，保留 `None` 默认值保障 Step 2/3 自然跳过。1B-A/Phase 0 测试以 `None` 注入，行为零变化。
3. **Step 2/3 编排逻辑在 Router 类体内**实现为三个私有方法（`_try_materialized`, `_try_cache`, `_materialize`），不提取独立 helper 模块——减少文件数、保持内聚。
4. **缓存失败 catch-and-log 全覆盖**：任何 get/put 异常被 `logger.warning` 捕获后静默跳过，不影响查询返回。
5. **零 DDL 研发阶段**：MongoDB 集合/索引创建列为 §6.2 受控运维清单，不进入 Implement 阶段代码。

实现优先级：① LocalMongoAdapter + 单测 → ② CacheManager + 单测 → ③ Router 守卫移除 + 编排 + 集成测试。

---

## 2. 现状分析

### 2.1 相关文件

| 文件 | 行数（约） | 状态 |
|---|---|---|
| `skills/data/unified_data/router.py` | 755 | 1B-A 已交付；含 ValueError 守卫 2 段（L161-170）；四步编排中 Step 2/3 占位跳过 |
| `skills/data/unified_data/local_mongo_adapter.py` | — | **新增**（本 Design） |
| `skills/data/unified_data/cache_manager.py` | — | **新增**（本 Design） |
| `skills/data/unified_data/__init__.py` | 119 | 需导出 LocalMongoAdapter、CacheManager |
| `skills/data/unified_data/freshness.py` | — | 1B-A 已交付；`label(from_cache=True)` 逻辑就位，不修改 |
| `skills/data/unified_data/client.py` | ~330 | 1B-A 已交付；不修改（1B-B 不新增客户端参数） |
| `skills/data/unified_data/registry.py` | ~200 | 1B-A 已交付；不修改 |
| `skills/data/unified_data/provider.py` | 121 | DataProvider ABC；不修改 |
| `skills/data/unified_data/config.py` | 58 | UnifiedDataConfig；不修改 |
| `skills/data/unified_data/exceptions.py` | 71 | 异常体系；不修改 |
| `skills/data/unified_data/models/__init__.py` | 524 | SecurityId/DataResult/Capability 公共契约；不修改 |
| `tests/data/unified_data/conftest.py` | ~200 | 1B-A conftest；新增 FakeLocalMongoAdapter fixture（可选；大部分测试直接传 mongomock） |
| `tests/data/unified_data/test_local_mongo_adapter.py` | — | **新增**（12 条 UT） |
| `tests/data/unified_data/test_cache_manager.py` | — | **新增**（10 条 UT） |
| `tests/data/unified_data/test_router_persistence.py` | — | **新增**（17 条 UT + 4 条 IT） |

### 2.2 现有约束

- 1B-A DataRouter 构造参数 `local_mongo_adapter` / `cache_manager` 已预留但被 ValueError 硬守卫为 `None`。
- `FreshnessPolicy.get_ttl(domain)` 可用（已交付 1B-A），返回秒级 TTL。
- 1B-A 测试全部以 `local_mongo_adapter=None, cache_manager=None` 注入。
- `mongomock` 已在测试依赖中（`mongomock.MongoClient` → `.get_database("tradingagents")` 返回可用的 db 句柄）。
- 项目用 `pymongo` 4.x 作为生产 MongoDB 驱动；`mongomock` 4.x 兼容。
- `ta_cn_adapter` 等 1B-A fixture（`FakeTA_CNAdapter`）可直接复用。

### 2.3 兼容性风险

| 风险项 | 等级 | 缓解 |
|---|---|---|
| DataRouter ValueError 守卫删除后 1B-A 测试仍传 None | 低 | Step 2/3 条件 `is not None` 自然跳过，行为不变 |
| CacheManager 签名变化（SPEC-03-007 §4.7 `mongo_uri` → `mongo_db`） | 低 | 1B-A 未实现 CacheManager，无既有调用方 |
| `mongomock` 与真实 PyMongo Database 类型差异 | 中 | 统一用 `Any` 类型标注；生产 rollout 前补真实 Mongo smoke test |
| `FreshnessPolicy.label(from_cache=True)` 当前不触发 | 低 | CacheManager 写入后自动激活；不需要代码修改 |

---

## 3. 方案设计

### 3.1 模块/文件改动清单

| 文件 | 改动 | 原因 |
|---|---|---|
| `skills/data/unified_data/local_mongo_adapter.py` | **新增**：LocalMongoAdapter 类（get/put/invalidate，mongomock 兼容） | 1B-B 核心组件 |
| `skills/data/unified_data/cache_manager.py` | **新增**：CacheManager 类（get/put/invalidate，mongomock 兼容） | 1B-B 核心组件 |
| `skills/data/unified_data/router.py` | **修改**：删除 ValueError 守卫 2 段；新增 `_try_materialized` / `_try_cache` / `_materialize` 三个私有方法；Step 2/3 调用点插入 query() 编排 | 激活持久化缓存层 |
| `skills/data/unified_data/__init__.py` | **修改**：导出 LocalMongoAdapter、CacheManager | 模块公共接口 |
| `tests/data/unified_data/test_local_mongo_adapter.py` | **新增**：12 条单元测试（mongomock） | 1B-B 测试 |
| `tests/data/unified_data/test_cache_manager.py` | **新增**：10 条单元测试（mongomock） | 1B-B 测试 |
| `tests/data/unified_data/test_router_persistence.py` | **新增**：17 条 UT + 4 条 IT（mongomock + fake provider + FakeTA_CNAdapter） | Step 2/3 集成验证 |
| `tests/data/unified_data/test_router.py` | **不修改**：Step 2/3 None 时退化行为不变，22 条全 PASS | 1B-A 回归 |

### 3.2 类图与数据流

```
┌─────────────────────────────────────────────────────────────────────┐
│                      DataRouter（1B-B 扩张版）                       │
│                                                                     │
│  __init__(..., local_mongo_adapter=None, cache_manager=None)        │
│                                                                     │
│  query(domain, op, sid, *, provider, force_refresh, params)         │
│    │                                                                │
│    ├─ provider 指定? ──► 跳 Step 1-3                                │
│    ├─ force_refresh? ──► 跳 Step 1-3                                │
│    ├─ Step 1: _try_ta_cn()     → TA_CNMongoAdapter   [1B-A 既有]    │
│    ├─ Step 2: _try_materialized() → LocalMongoAdapter  [1B-B 新增]  │
│    ├─ Step 3: _try_cache()     → CacheManager          [1B-B 新增]  │
│    ├─ Step 4: _query_external_chain() → Provider fallback [1B-A]    │
│    │      └─ 成功 → _materialize()                      [1B-B 新增]  │
│    └─ return DataResult                                              │
│                                                                     │
│  属性:                                                              │
│    _local_mongo_adapter: LocalMongoAdapter | None                   │
│    _cache_manager: CacheManager | None                              │
└──────┬────────────┬────────────┬────────────────────────────────────┘
       │            │            │
       ▼            ▼            ▼
┌────────────┐ ┌──────────────┐ ┌─────────────────────┐
│ TA_CN      │ │LocalMongo    │ │ CacheManager        │
│ MongoAdapt │ │Adapter       │ │ (03_data_ud_cache_*)│
│ er（只读）  │ │(03_data_ud_*)│ │ get / put /         │
│ [1B-A]     │ │ get / put /  │ │ invalidate          │
│            │ │ invalidate   │ │ TTL: 短周期         │
│            │ │ TTL: 按域     │ │ 可丢弃              │
└────────────┘ └──────────────┘ └─────────────────────┘
```

### 3.3 控制流：internal-first 完整四步查询

```
client.query(domain="market_data", operation="kline_daily",
             security_id=sid, params=None)
  │
  ▼
DataRouter.query()
  │
  ├─ provider=None, force_refresh=False
  │
  ├─ Step 1: _try_ta_cn(sid, capability, params, trace, ts)
  │    ├─ adapter=None → trace("ta_cn_internal(skipped: no adapter)")
  │    ├─ TA-CN 命中 → return DataResult(provider="ta_cn_internal")
  │    ├─ TA-CN 空(covered) → return DataResult(provider="empty")
  │    └─ 未覆盖/异常 → continue
  │
  ├─ Step 2: _try_materialized(sid, domain, operation, params, trace, ts)
  │    ├─ adapter=None → trace("ud_materialized(skipped: no adapter)")
  │    ├─ 命中+未过期 → return DataResult(provider="ud_materialized",
  │    │                                     freshness="cached")
  │    ├─ 命中+过期 → trace("ud_materialized(stale)"), continue
  │    ├─ 未命中 → trace("ud_materialized(miss)"), continue
  │    └─ 异常 → trace("ud_materialized(error: ...)"), continue  ← catch-and-log
  │
  ├─ Step 3: _try_cache(sid, domain, operation, params, trace, ts)
  │    ├─ manager=None → trace("cache(skipped: no manager)")
  │    ├─ 命中+未过期 → return DataResult(provider=原始provider,
  │    │                                     freshness="cached")
  │    ├─ 命中+过期 → trace("cache(stale)"), continue
  │    ├─ 未命中 → trace("cache(miss)"), continue
  │    └─ 异常 → trace("cache(error: ...)"), continue  ← catch-and-log
  │
  ├─ Step 4: _query_external_chain(...)
  │    ├─ 外部成功 → result = DataResult(provider="tushare")
  │    │               _materialize(sid, domain, op, params, result)
  │    │                 ├─ put 物化 (catch-and-log)
  │    │                 └─ put Cache (catch-and-log)
  │    │               return result
  │    └─ 全部失败 → return DataResult(provider="error",
  │                                        source_trace=[...])
  │
  └─ return DataResult
```

### 3.4 接口与数据结构

#### 3.4.1 LocalMongoAdapter

```python
# 文件: skills/data/unified_data/local_mongo_adapter.py（新增）

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from .freshness import FreshnessPolicy
from .models import DataResult, SecurityId

logger = logging.getLogger(__name__)


class LocalMongoAdapter:
    """受 allow-list 约束的 UD 物化数据读写组件（03_data_ud_*）。

    Step 2 of internal-first path. 只对 UD 自有 03_data_ud_* 集合
    执行 get/put/invalidate，所有操作 catch-and-log 不阻塞 Router。

    Strictly read-only on TA-CN prefixless collections — enforced by
    collection_prefix being locked to "03_data_ud_".
    """

    def __init__(
        self,
        mongo_db: Any,                              # pymongo.database.Database | mongomock.database.Database
        collection_prefix: str = "03_data_ud_",
        freshness: "FreshnessPolicy | None" = None,
    ) -> None:
        self._db = mongo_db
        self._prefix = collection_prefix  # 运行时锁定为 "03_data_ud_"
        self._freshness = freshness or FreshnessPolicy()

    def get(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: "Mapping[str, Any] | None" = None,
    ) -> "DataResult | None":
        """返回未过期的物化 DataResult；未命中/过期返回 None。

        异常时 catch-and-log，返回 None（不阻断调用方）。
        """
        ...

    def put(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: "Mapping[str, Any] | None",
        result: DataResult,
    ) -> None:
        """物化写入外部 Provider 成功后的 DataResult。

        upsert 模式（materialized_key 匹配时替换）。
        写入失败 catch-and-log，不影响查询返回值。
        """
        ...

    def invalidate(
        self,
        security_id: "SecurityId | None" = None,
        domain: "str | None" = None,
    ) -> int:
        """批量失效物化数据，返回删除条数。

        security_id=None + domain=None → 清空全部 03_data_ud_*
        security_id 指定 → 只删除该标的（AND 语义组合 domain）
        domain 指定 → 只删除该域
        """
        ...
```

**构造参数语义**：

| 参数 | 说明 |
|---|---|
| `mongo_db` | MongoDB 数据库句柄（`pymongo.database.Database` 或 `mongomock.database.Database`）。兼容生产与测试。由调用方负责建立连接并传入。 |
| `collection_prefix` | 锁定为 `"03_data_ud_"`。运行时不允许自定义，以硬编码确保不误读到 TA-CN 无前缀集合。 |
| `freshness` | FreshnessPolicy 实例，用于计算 `expires_at`。None 时用默认 `FreshnessPolicy()`。 |

#### 3.4.2 CacheManager（持久化版）

```python
# 文件: skills/data/unified_data/cache_manager.py（新增）

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from .freshness import FreshnessPolicy
from .models import DataResult, SecurityId

logger = logging.getLogger(__name__)


class CacheManager:
    """短 TTL Query Cache（03_data_ud_cache_*）。

    Step 3 of internal-first path. 读写操作全部 catch-and-log，
    缓存问题不阻塞查询。

    接收已就绪的 mongo_db 句柄（pymongo 或 mongomock），
    不接收 mongo_uri 连接串以兼容 mongomock 测试。
    """

    def __init__(
        self,
        mongo_db: Any,                              # pymongo.database.Database | mongomock.database.Database
        collection_prefix: str = "03_data_ud_cache_",
        freshness: "FreshnessPolicy | None" = None,
    ) -> None:
        self._db = mongo_db
        self._prefix = collection_prefix  # 运行时锁定为 "03_data_ud_cache_"
        self._freshness = freshness or FreshnessPolicy()

    def get(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: "Mapping[str, Any] | None" = None,
    ) -> "DataResult | None":
        """返回未过期的缓存 DataResult；未命中/过期返回 None。"""
        ...

    def put(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: "Mapping[str, Any] | None",
        result: DataResult,
    ) -> None:
        """缓存写入成功查询的 DataResult（不区分数据来源）。upsert 模式。"""
        ...

    def invalidate(
        self,
        security_id: "SecurityId | None" = None,
        domain: "str | None" = None,
    ) -> int:
        """批量失效缓存，返回删除条数。语义同 LocalMongoAdapter.invalidate。"""
        ...

    @staticmethod
    def _make_cache_key(
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: "Mapping[str, Any] | None" = None,
    ) -> str:
        """生成确定性 cache_key。

        格式: sha256(f"{security_id}|{domain}|{operation}|{json_params}")[:32]
        params 按 sort_keys=True JSON 序列化确保顺序无关性。
        """
        params_str = json.dumps(params or {}, sort_keys=True)
        raw = f"{security_id}|{domain}|{operation}|{params_str}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
```

**构造参数语义**：

| 参数 | 说明 |
|---|---|
| `mongo_db` | MongoDB 数据库句柄。不接收 `mongo_uri`，以兼容 mongomock 测试。 |
| `collection_prefix` | 锁定为 `"03_data_ud_cache_"`。运行时不允许自定义。 |
| `freshness` | FreshnessPolicy 实例，用于计算 `expires_at`。None 时用默认。 |

#### 3.4.3 DataRouter 变更

```python
# 文件: skills/data/unified_data/router.py（修改）

class DataRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        config: UnifiedDataConfig | None = None,
        *,
        ta_cn_adapter: Any = None,
        local_mongo_adapter: "LocalMongoAdapter | None" = None,  # [1B-B] 移除 ValueError 守卫
        cache_manager: "CacheManager | None" = None,             # [1B-B] 移除 ValueError 守卫
        freshness: FreshnessPolicy | None = None,
        external_fallback_chains: "dict[str, list[str]] | None" = None,
    ) -> None:
        self._registry = registry
        self._config = config or UnifiedDataConfig.minimal()
        self._ta_cn_adapter = ta_cn_adapter
        self._local_mongo_adapter = local_mongo_adapter  # Step 2 (None → 跳过)
        self._cache_manager = cache_manager              # Step 3 (None → 跳过)
        self._freshness = freshness or FreshnessPolicy()
        self._external_fallback_chains = external_fallback_chains or {}
```

**注意事项**：
- **直接删除**两段 ValueError 守卫代码，不是条件化（`# if ...`）
- 保留 `None` 默认值，Step 2/3 的 `is not None` 条件自然跳过
- 属性名带 `_` 前缀（`self._local_mongo_adapter`），与 1B-A 命名一致

#### 3.4.4 新增私有方法

```python
# DataRouter 新增三个私有方法

def _try_materialized(
    self,
    security_id: SecurityId,
    domain: str,
    operation: str,
    params: "Mapping[str, Any] | None",
    trace: list,
    ts: datetime,
) -> "DataResult | None":
    """Step 2: 查 LocalMongoAdapter。命中未过期返回，否则 None。"""
    if self._local_mongo_adapter is None:
        trace.append("ud_materialized(skipped: no adapter)")
        return None
    try:
        cached = self._local_mongo_adapter.get(security_id, domain, operation, params)
        if cached is not None:
            trace.append("ud_materialized(ok)")
            return cached  # provider="ud_materialized", freshness="cached"
        trace.append("ud_materialized(miss)")
        return None
    except Exception as e:
        logger.warning("LocalMongoAdapter.get failed: %s", e)
        trace.append(f"ud_materialized(error: {e})")
        return None


def _try_cache(
    self,
    security_id: SecurityId,
    domain: str,
    operation: str,
    params: "Mapping[str, Any] | None",
    trace: list,
    ts: datetime,
) -> "DataResult | None":
    """Step 3: 查 CacheManager。命中未过期返回，否则 None。"""
    if self._cache_manager is None:
        trace.append("cache(skipped: no manager)")
        return None
    try:
        cached = self._cache_manager.get(security_id, domain, operation, params)
        if cached is not None:
            trace.append("cache(ok)")
            return cached  # freshness="cached", provider=原始 provider
        trace.append("cache(miss)")
        return None
    except Exception as e:
        logger.warning("CacheManager.get failed: %s", e)
        trace.append(f"cache(error: {e})")
        return None


def _materialize(
    self,
    security_id: SecurityId,
    domain: str,
    operation: str,
    params: "Mapping[str, Any] | None",
    result: DataResult,
) -> None:
    """外部 Provider 成功后的物化+Cache 写入。顺序：先物化后缓存。"""
    try:
        self._local_mongo_adapter.put(security_id, domain, operation, params, result)
    except Exception as e:
        logger.warning("LocalMongoAdapter.put failed: %s", e)
    try:
        self._cache_manager.put(security_id, domain, operation, params, result)
    except Exception as e:
        logger.warning("CacheManager.put failed: %s", e)
```

#### 3.4.5 query() 编排变更（Step 2/3 调用点插入）

在 `query()` 方法的 Step 1 之后、Step 4 之前插入（方案 C：始终调用 helper，由 helper 自管 force_refresh trace）：

```python
# === Step 2: [1B-B] UD 物化 ===
# 始终调用 helper（方案 C），由 helper 内自管 force_refresh trace
# 和 adapter=None 跳过。force_refresh=True 时记录
# "ud_materialized(skipped: force_refresh)" 并原路返回 None。
result = self._try_materialized(
    security_id, domain, operation, params, trace, ts,
    force_refresh=force_refresh,
)
if result is not None:
    return result

# === Step 3: [1B-B] Query Cache ===
# 同方案 C：由 _try_cache 内自管 force_refresh trace，
# 不调用 CacheManager.get()。
result = self._try_cache(
    security_id, domain, operation, params, trace, ts,
    force_refresh=force_refresh,
)
if result is not None:
    return result
```

**与 1B-A query() 的差异**：

| 变更点 | 1B-A | 1B-B |
|---|---|---|
| Step 2 代码 | 不存在（被 jump over） | `_try_materialized()` + 返回值检查 |
| Step 3 代码 | 不存在 | `_try_cache()` + 返回值检查 |
| Step 4 成功后 | 只返回 DataResult | 返回前调用 `_materialize()` |
| force_refresh 行为 | Step 1 跳过（if not force_refresh 守卫控制） | Step 1 跳过 + Step 2/3 helper 自管 force_refresh trace：_try_materialized/_try_cache 记录 (skipped: force_refresh) 后返回 None，不调用底层 get()。外部 Provider 仍被调用，成功后 _materialize 写入。 |
| ta_cn_adapter None | Step 1 跳过 | 不变 |
| local_mongo_adapter None | 异常 | Step 2 自然跳过 |
| cache_manager None | 异常 | Step 3 自然跳过 |

#### 3.4.6 集合命名规则

| 组件 | 集合名格式 | 示例 | 说明 |
|---|---|---|---|
| LocalMongoAdapter | `03_data_ud_{operation}` | `03_data_ud_kline_daily` | 物化集合。同一 operation 的所有标的在同一集合中，以 `materialized_key` 唯一标识 |
| CacheManager | `03_data_ud_cache_{operation}` | `03_data_ud_cache_kline_daily` | 缓存集合。同一 operation 的缓存数据在同一集合中，以 `cache_key` 唯一标识 |

**集合不按 security_id 或 domain 组织**——同一 operation 的所有标的物化在同一集合中，通过 `materialized_key` / `cache_key` 区分。

#### 3.4.7 `__init__.py` 导出

```python
# 文件: skills/data/unified_data/__init__.py（追加）

from .local_mongo_adapter import LocalMongoAdapter
from .cache_manager import CacheManager

__all__ = [
    # ... 已有导出 ...
    "LocalMongoAdapter",
    "CacheManager",
]
```

### 3.5 持久化设计

#### 3.5.1 `03_data_ud_*` 物化集合文档信封

| 字段 | 类型 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `_id` | ObjectId | 是 | MongoDB 自动 | — |
| `materialized_key` | string(64) | 是 | `sha256(f"{sid}\|{domain}\|{operation}\|{params_hash}")[:64]` | upsert 查找键；put() 中计算 |
| `security_id` | string | 是 | put() 入参 | 格式 `"CN:600519"` |
| `domain` | string | 是 | put() 入参 | `"market_data"` 等 |
| `operation` | string | 是 | put() 入参 | `"kline_daily"` 等 |
| `params_hash` | string(32) | 是 | `md5(json.dumps(params, sort_keys=True))[:32]` | 参数指纹，去重 |
| `data` | Any | 是 | `DataResult.data` | 序列化 payload。DataFrame → `to_dict(orient="records")` 后的 list[dict]；单值标量直接存 |
| `provider` | string | 是 | `DataResult.provider` | 实际数据来源 |
| `fetched_at` | ISO datetime | 是 | 查询时间 `ts` | 数据实际获取时刻 |
| `data_date` | ISO date(string) | 否 | `DataResult.data_date` | 业务日期 |
| `freshness_at_write` | string | 否 | `DataResult.freshness` | 写入时的 freshness 标签 |
| `source_trace` | string[] | 是 | `DataResult.source_trace` | 完整来源链 |
| `schema_version` | string | 是 | 固定 `"1.0"` | 文档 schema 版本 |
| `materialized_at` | ISO datetime | 是 | `datetime.utcnow()` | 物化写入时间 |
| `expires_at` | ISO datetime | 是 | `materialized_at + FreshnessPolicy.get_ttl(domain)` | 过期时间。读路径根据此字段判定是否返回；不依赖 MongoDB TTL index |

**写入触发点**：`DataRouter._materialize()` → `LocalMongoAdapter.put()` — 外部 Provider 成功后（catch-and-log 模式，同步写入）。

#### 3.5.2 `03_data_ud_cache_*` 缓存集合文档信封

| 字段 | 类型 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `_id` | ObjectId | 是 | MongoDB 自动 | — |
| `cache_key` | string(32) | 是 | `sha256(f"{sid}\|{domain}\|{operation}\|{json_params}")[:32]` | upsert 查找键；put() 中通过 `_make_cache_key()` 计算 |
| `security_id` | string | 是 | put() 入参 | — |
| `domain` | string | 是 | put() 入参 | — |
| `operation` | string | 是 | put() 入参 | — |
| `params_hash` | string(32) | 是 | md5 哈希 | 去重 |
| `data` | Any | 是 | `DataResult.data` | 序列化 payload |
| `provider` | string | 是 | `DataResult.provider` | 原始 provider |
| `fetched_at` | ISO datetime | 是 | `ts` | 查询时间 |
| `data_date` | ISO date(string) | 否 | `DataResult.data_date` | — |
| `source_trace` | string[] | 是 | `DataResult.source_trace` | — |
| `cached_at` | ISO datetime | 是 | `datetime.utcnow()` | 缓存写入时间 |
| `expires_at` | ISO datetime | 是 | `cached_at + FreshnessPolicy.get_ttl(domain)` | — |

**写入触发点**：`DataRouter._materialize()` → `CacheManager.put()` — 与物化写入并行，先物化后缓存（独立 try/except）。

#### 3.5.3 研发阶段持久化策略

| 方面 | 策略 |
|---|---|
| 数据库连接 | `mongomock.MongoClient().get_database("tradingagents")` — 作为 `mongo_db` 传入 |
| 集合创建 | mongomock 自动创建（不显式调用 `create_collection`） |
| 索引创建 | 研发阶段**不创建**生产索引。`expires_at` 过期判定由 LocalMongoAdapter/CacheManager 的 `get()` 中比较 `expires_at vs datetime.utcnow()` 实现，不依赖 MongoDB TTL index |
| DDL | 零 DDL。`create_collection` / `create_index` / `create_view` / `collection_validator` 均不在 1B-B 研发代码中出现 |
| `data` 序列化 | `pd.DataFrame` → `.to_dict(orient="records")`；标量直接存储；list[dict] 为 JSON 兼容格式。不引入额外 schema 校验 |
| 过期物化保留 | 过期文档保留在集合中（Read 路径不返回），供 TTL index 自动清理（生产 rollout）或后台重建参考 |
| 生产 rollout | 见 §6.2 — 不进入 1B-B 研发代码 |

### 3.6 `__init__.py` 导出

```python
# 在 skills/data/unified_data/__init__.py 追加
from .local_mongo_adapter import LocalMongoAdapter
from .cache_manager import CacheManager
```

---

## 4. 实现计划

按依赖关系分四步，每步可独立测试：

| 步骤 | 组件 | 依赖 | 预估时间 |
|---|---|---|---|
| **Step 1：LocalMongoAdapter** | `local_mongo_adapter.py` + `test_local_mongo_adapter.py`（12 条 UT） | mongomock（已有） | 25 min |
| **Step 2：CacheManager** | `cache_manager.py` + `test_cache_manager.py`（10 条 UT） | mongoose | 20 min |
| **Step 3：Router 增强** | ① 删除 ValueError 守卫；② 新增 3 个私有方法；③ Step 2/3 调用点插入；④ `_materialize` 调用插入；⑤ `__init__.py` 导出 | Step 1+2 | 15 min |
| **Step 4：集成测试** | `test_router_persistence.py`（17 UT + 4 IT） | Step 3 | 30 min |

总计预估：**90 min**。

---

## 5. 测试策略

### 5.1 测试基础设施

- mongomock：全部 LocalMongoAdapter / CacheManager 测试用 `mongomock.MongoClient().get_database("tradingagents")`。
- FakeTA_CNAdapter、FakeProvider（1B-A conftest 已有）直接复用。
- 不新增 conftest 修改（`tests/data/unified_data/conftest.py` 不修改）。

### 5.2 单元测试矩阵

#### LocalMongoAdapter（12 条 UT，文件：`tests/data/unified_data/test_local_mongo_adapter.py`）

| 编号 | 测试方法 | 覆盖 SPEC | 关键断言 |
|---|---|---|---|
| UT-LM-001 | test_get_hit_not_expired | LM-102 | 返回 DataResult，provider != "error" |
| UT-LM-002 | test_get_hit_but_expired | LM-103 | 返回 None |
| UT-LM-003 | test_get_miss | LM-102 | 返回 None |
| UT-LM-004 | test_get_exception_returns_none | LM-104 | 返回 None，不抛异常 |
| UT-LM-005 | test_put_then_get | LM-105 | put 后 get 返回相同 data |
| UT-LM-006 | test_put_idempotent | LM-106 | 两次相同 put → materialized_key 唯一；第二次覆盖 |
| UT-LM-007 | test_invalidate_all | LM-107 | 写入 3 条 → invalidate() → 删 3 条，get 全 None |
| UT-LM-008 | test_invalidate_by_security_id | LM-108 | 2 条同标的 + 1 条不同 → 删 2 条，不同标的可读 |
| UT-LM-009 | test_invalidate_by_domain | LM-109 | 2 条不同 domain → 只删指定 domain |
| UT-LM-010 | test_expires_at_calculated | LM-102/103 | put 后文档 `expires_at == materialized_at + TTL` |
| UT-LM-011 | test_collection_prefix_locked | ALL | 构造时不暴露 prefix 修改（硬编码常量） |
| UT-LM-012 | test_never_writes_to_non_prefixed | ALL | 确保集合名始终以 `03_data_ud_` 开头 |

#### CacheManager（10 条 UT，文件：`tests/data/unified_data/test_cache_manager.py`）

| 编号 | 测试方法 | 覆盖 SPEC | 关键断言 |
|---|---|---|---|
| UT-CM-001 | test_get_hit_not_expired | CM-102 | 返回 DataResult |
| UT-CM-002 | test_get_expired | CM-103 | 返回 None |
| UT-CM-003 | test_get_miss | CM-102 | 返回 None |
| UT-CM-004 | test_get_exception_returns_none | CM-104 | 返回 None，不抛异常 |
| UT-CM-005 | test_put_then_get | CM-105 | put 后 get 返回相同 data |
| UT-CM-006 | test_put_idempotent | CM-106 | cache_key 唯一，第二次覆盖 |
| UT-CM-007 | test_invalidate_all | CM-107 | 写入 3 条 → invalidate() → 删 3 条 |
| UT-CM-008 | test_invalidate_by_security_id | CM-107 | 同 LM-008 |
| UT-CM-009 | test_cache_key_deterministic | CM-105 | 同 params 两次 put → cache_key 相等 |
| UT-CM-010 | test_cache_key_params_order_independent | CM-105 | `{a:1,b:2}` vs `{b:2,a:1}` → 相同 cache_key |

#### DataRouter Step 2/3 + 物化链（17 条 UT + 4 条 IT，文件：`tests/data/unified_data/test_router_persistence.py`）

| 编号 | 测试方法 | 覆盖 SPEC | 关键断言 |
|---|---|---|---|
| UT-PR-001 | test_step2_hit | DR-201/202 | provider="ud_materialized" |
| UT-PR-002 | test_step2_stale_continues_to_step3 | DR-203 | 过期物化不返回，进 Step 3 |
| UT-PR-003 | test_step2_miss_step3_hit | DR-206/207 | freshness="cached" |
| UT-PR-004 | test_step2_3_miss_step4_ok | DR-204/209 | provider="tushare" |
| UT-PR-005 | test_step2_exception_continues | DR-205 | trace 含 error，进 Step 3 |
| UT-PR-006 | test_step3_exception_continues | DR-210 | trace 含 error，进 Step 4 |
| UT-PR-007 | test_force_refresh_skips_step2_3 | DR-201/206 | trace 含 skipped，外部成功 |
| UT-PR-008 | test_external_success_materializes | MW-101/102 | put 后 LocalMongoAdapter.get() 可读出 |
| UT-PR-009 | test_external_success_caches | MW-103 | put 后 CacheManager.get() 可读出 |
| UT-PR-010 | test_materialize_put_fail_does_not_block | MW-101 | put 异常 → DataResult 仍正确返回 |
| UT-PR-011 | test_cache_put_fail_does_not_block | MW-101 | put 异常 → DataResult 仍正确返回 |
| UT-PR-012 | test_ta_cn_hit_no_materialize | MW-105 | Step 1 命中 → 物化/Cache 为空 |
| UT-PR-013 | test_provider_external_skips_step2_3 | DR-201/206 | trace 含 skipped |
| UT-PR-014 | test_all_internal_miss_external_fail | 同 1B-A | DataResult.error |
| UT-PR-015 | test_source_trace_full_chain | DR-213/214 | trace 含 4 步（TA-CN/物化/Cache/外部） |
| UT-PR-016 | test_step2_adapter_none_skips | DR-201 | trace "skipped: no adapter" |
| UT-PR-017 | test_step3_manager_none_skips | DR-206 | trace "skipped: no manager" |

### 5.3 集成测试（4 条 IT）

| 编号 | 测试方法 | 测试目标 |
|---|---|---|
| IT-PR-001 | test_full_internal_ta_cn_miss_materialized_hit | 完整 internal-first：TA-CN 空 → 物化命中 → 返回（不调外部） |
| IT-PR-002 | test_full_internal_all_miss_external_ok | 完整 internal-first：全空 → 外部成功 → 返回 + 物化/Cache 写入 |
| IT-PR-003 | test_force_refresh_skip_all_internal | force_refresh: 跳过 Step 1/2/3 → 外部成功 → 写入物化/Cache |
| IT-PR-004 | test_full_internal_all_fail | 全空 + 外部全失败 → DataResult.error |

### 5.4 回归测试

| 测试文件 | 预期 | 备注 |
|---|---|---|
| `tests/data/unified_data/test_router.py` | 22/22 PASS | 1B-A 测试全部传 `None`，Step 2/3 跳过 |
| `tests/data/unified_data/test_router_internal_first.py` | UT-DR-001~012 + IT-001~004 | 1B-A internal-first 测试不受影响 |
| `tests/data/unified_data/test_client_phase1a.py` | 25/25 PASS | `client.py` 不修改 |
| `tests/data/unified_data/test_freshness_policy.py` | 8/8 PASS | 不变 |

### 5.5 不可自动化验证项

- 物化/Cache 集合的生产索引创建脚本正确性（Pascal 审批后由独立 rollout 任务执行）。
- mongomock 与真实 MongoDB 行为偏差（如 `expires_at` 比较 vs TTL index 自动清理）。
- `LocalMongoAdapter.invalidate()` 在生产环境删除大量文档时的性能。

---

## 6. 风险、降级与回滚

| 风险 | 等级 | 应对 | 降级/回滚 |
|---|---|---|---|
| LocalMongoAdapter/CacheManager 的 `mongo_db` 类型标注不覆盖 mongomock 与 pymongo 所有操作差异 | 中 | 统一用 `Any` 类型标注；所有 get/put 操作只使用 `find_one` / `update_one` / `delete_many` 三个基础方法，不在代码中调用 pymongo 专有 API | 如发现 mongomock 不兼容方法，替换为兼容等价方法 |
| Step 2/3 加入后增加 Router 查询延迟（即使 skip） | 低 | skip 判定为 O(1) 成员检查（`self._xxx is not None`）；mongomock get 为内存操作 | Step 2/3 可独立开关（传 None 即可跳过） |
| `_materialize` 写入失败但 catch-and-log 掩盖真实错误 | 低 | logger.warning 记录异常；研发阶段可配置 log level 为 DEBUG 查看；生产补监控告警 | 不需要回滚 — 写入失败不影响查询返回值 |
| 多线程竞态：concurrent `put()` 更新同一 `materialized_key` | 低 | upsert 是原子操作（`update_one({...}, {$set: ...}, upsert=True)`），不会产生重复文档 | 天然幂等，无需回滚 |
| `03_data_ud_*` data 字段序列化方式与消费方期望不匹配 | 中 | DataFrame → `to_dict(orient="records")`（list[dict]）；消费方读取时直接 `pd.DataFrame(data)` 重建 | 如有兼容问题，追加序列化 helper 函数（不修改 schema） |
| 生产 rollout 误执行在研发阶段 | 低 | 研发阶段代码零 DDL；对应运维脚本不在 1B-B 产出物中 | — |

### 6.1 Design 阶段的 SPEC 待决项决议

| SPEC 待决项 | 本 Design 决议 |
|---|---|
| `_try_materialized` / `_try_cache` / `_materialize` 代码位置 | **Router 类体内**。三方法总代码约 40 行，放在类体内保持内聚。不引入独立 helper 模块，减少文件数 |
| 工厂函数组织 | **调用方自行组装**。DataRouter 构造接受已实例化的 adapter/manager。`UnifiedDataClient` 工厂（如 `UnifiedDataClient.create()`）可在将来扩展，1B-B 不新增工厂方法 |
| 过期物化数据保留策略 | **保留在集合中**。Read 路径用 `expires_at` 字段过滤（返回 None），不删除过期文档。生产环境由 TTL index 自动清理。Design 确认此策略满足重建需求：过期物化数据仍保留在集合中，可被后台重建任务读取 |
| `03_data_ud_*` 的 `data` 字段序列化方式 | **`pd.DataFrame.to_dict(orient="records")`** → list[dict]。JSON 兼容，消费方用 `pd.DataFrame(data)` 重建。单值标量直接存储。不引入额外 schema 校验 |

### 6.2 生产 Mongo rollout 清单（Pascal 审批项，不在 1B-B 研发阶段执行）

| 操作 | 对象 | 说明 |
|---|---|---|
| `create_collection` | `03_data_ud_{operation}` | 按项目现有 capability 列表创建物化集合（约 16 个） |
| `create_index` | `materialized_key` 唯一索引 | 物化集合 upsert 查找键 |
| `create_index` | `expires_at` TTL 索引 | 过期自动清理 |
| `create_collection` | `03_data_ud_cache_{operation}` | 缓存集合（约 16 个） |
| `create_index` | `cache_key` 唯一索引 | 缓存 upsert 查找键 |
| `create_index` | 缓存 `expires_at` TTL 索引 | 过期自动清理 |
| `create_index` | `{security_id: 1, domain: 1, operation: 1}` | 物化集合按标的查询优化 |
| `create_index` | `{operation: 1, expires_at: 1}` | 物化集合 invalidate 过滤优化 |
| `create_index` | `{security_id: 1, domain: 1}` | 缓存集合 invalidate 过滤优化 |

**生产 rollout 步骤**（由独立 rollout 任务执行）：
1. Pascal 审批清单（上表）。
2. 运维脚本 `scripts/data/create_ud_collections.py`（idempotent create + 索引创建）。
3. 在 `tradingagents` 数据库上手动执行脚本。
4. 生产 smoke test：用真实 MongoDB 连接验证集合/索引创建及基本读写。
5. 如 `MONGO_URI` 需更新，更新配置/环境变量。

---

## 7. 明确禁止与零副作用声明

### 7.1 不改动文件列表

| 文件 | 理由 |
|---|---|
| `skills/data/unified_data/models/__init__.py` | Phase 0 公共契约不变 |
| `skills/data/unified_data/adapters/ta_cn_mongo_adapter.py` | TA-CN 只读复用 |
| `skills/data/unified_data/provider.py` | DataProvider ABC 不变 |
| `skills/data/unified_data/config.py` | UnifiedDataConfig 不变 |
| `skills/data/unified_data/exceptions.py` | 异常体系保留 |
| `skills/data/unified_data/freshness.py` | FreshnessPolicy 已交付且 from_cache 逻辑就位 |
| `skills/data/unified_data/client.py` | 1B-B 不新增客户端参数 |
| `skills/data/unified_data/registry.py` | 1B-B 不新增 registry 方法 |
| `skills/data/unified_data/rate_limiter.py` | 1B-A 已交付，不修改 |
| `skills/data/unified_data/providers/base_external.py` | 1B-A 已交付，不修改 |
| `skills/apps/TradingAgents-CN/**` | TA-CN 子项目 |
| `skills/research/daily_stock_analysis/**` | DSA 独立子系统 |
| `skills/data/data_interface/**` | RFC-03-003 IReader/IWriter |
| `skills/infra/task_center/**` | 任务中心 |
| 生产 MongoDB 集合 DDL/索引/schema | 零 DDL 研发阶段 |
| cron / systemd / 推送配置 | 不碰调度和推送 |
| RFC/SPEC/Design 文档模板 | 编排层不改模板（P-7） |

### 7.2 零副作用声明

- 不创建任何 MongoDB 集合、索引、schema validator（研发阶段零 DDL）。
- 不做真实 Mongo 写入（全部 mongomock）。
- 不做真实 Tushare/AKShare API 调用。
- 不修改 TA-CN 子项目代码（`skills/apps/TradingAgents-CN/**`）。
- 不修改 Phase 1A 14 个域入口方法（`client.py`）。
- 不修改 Phase 0/1A/1B-A 已有公共契约（SecurityId / DataResult / DataProvider / Capability / Registry / FreshnessPolicy）。
- 不新增 pip 依赖（pymongo、mongomock 已是现有依赖）。
- 不修改 RFC/SPEC/Design 文档模板。
- 不修改 1B-A 的 `_TA_CN_CAPABILITY_METHOD_MAP` 常量。
- 不引入 Feature Flag（守卫直接删除而非条件化）。

---

## 8. 交接给实现者

### 8.1 必须遵守

1. 文件改动范围严格限于 §3.1 文件清单（3 新增 + 2 修改）。**不得修改** §7.1 不改动文件列表中的任何文件。
2. 研发阶段全部用 mongomock，**不得**出现 `MongoClient(host=...)`、`create_collection`、`create_index` 等真实 DDL 调用。
3. `data` 字段序列化：`pd.DataFrame` → `.to_dict(orient="records")`；标量直接存。**不**引入 schema validation 库。
4. catch-and-log 模式：所有异常用 `logger.warning(...)` 记录后 `pass`，**不**做重试/等待/回退。
5. 守卫删除直接删除整段代码（两行 `if ... raise ValueError`），**不**保留注释或条件化分支。保留 `None` 默认值。
6. 测试必须全部用 mongomock + FakeTA_CNAdapter + FakeProvider（conftest 已有），不依赖真实网络或数据库。

### 8.2 可自行判断

1. `materialized_key` 计算中 `params` 为 None 时的处理（用 `{}` 代替）。
2. `SecurityId.__str__()` 的格式（当前为 `"CN:600519"` 格式）— 用 `str(security_id)` 即可。
3. `logger` 的命名空间（建议 `__name__`，即 `"unified_data.local_mongo_adapter"` 等）。
4. 过期判定的时间精度：`datetime.utcnow()` vs `datetime.now(timezone.utc)`，保持一致即可。

### 8.3 遇到以下情况退回 Principal

1. 发现需要修改 `client.py`、`freshness.py`、`config.py`、`registry.py` 等不改动文件清单中的文件。
2. 发现 SPEC 或 Design 与现有代码结构明显冲突，需要架构级调整。
3. 发现 mongomock 不支持某个 pymongo 方法导致无法实现关键功能。
4. 测试发现 Step 2/3 的编排逻辑与 1B-A 现有测试存在未预期的交互（非 None 注入导致 1B-A 测试失败）。

---

## 9. 参考资料

- RFC-03-009：`docs/rfc/03_data/RFC-03-009-unified-data-phase-1b-persistence-plane.md`
- SPEC-03-009：`docs/spec/03_data/SPEC-03-009-unified-data-phase-1b-persistence-plane.md`
- RFC-03-008：`docs/rfc/03_data/RFC-03-008-unified-data-phase-1b-query-plane.md`
- SPEC-03-008：`docs/spec/03_data/SPEC-03-008-unified-data-phase-1b-query-plane.md`
- SPEC-03-007：`docs/spec/03_data/SPEC-03-007-unified-data-layer.md`
- DESIGN-03-008：`docs/design/03_data/DESIGN-03-008-unified-data-phase-1b-query-plane.md`
- DESIGN-03-007：`docs/design/03_data/DESIGN-03-007-unified-data-layer.md`
- 现有代码：
  - `skills/data/unified_data/router.py`（755 行，1B-A DataRouter）
  - `skills/data/unified_data/freshness.py`（FreshnessPolicy，from_cache 逻辑就位）
  - `skills/data/unified_data/models/__init__.py`（SecurityId / DataResult / Capability）
  - `skills/data/unified_data/__init__.py`（模块导出）
  - `tests/data/unified_data/conftest.py`（FakeTA_CNAdapter / FakeProvider）
