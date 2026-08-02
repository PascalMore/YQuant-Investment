# DESIGN-03-014 F6: `market_sentiment` freshness canonical key 运行时对齐详细设计

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-08-02 |
| 版本号 | V0.1 |
| 来源 RFC | RFC-03-014-F6（PC-11 裁定：`market_sentiment` 为唯一 canonical freshness key） |
| 来源 SPEC | SPEC-03-014-F6（可执行契约：capability → freshness domain 映射、C-1~C-6 断言、V-1~V-6 验收） |
| 父 Design | DESIGN-03-014（V0.26 → V0.27，本卡完成最小同步） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 对应冻结项 | PC-11（freshness `sentiment` vs `market_sentiment` 命名冲突；RFC/SPEC V0.20 已解除冻结，本 Design 同步） |

> 本文件是 DESIGN-03-014-F6 amendment 的独立详细设计，覆盖：
> ① 运行时 freshness 查表显式解析为 canonical key 的精确文件/函数/调用点级设计；
> ② 主 DESIGN-03-014 三层同步的最小更新（§4.4、§P0.7.4、§P1.11、§P1.12 RD-2、§0.2/§0.3、changelog）；
> ③ T3 Implement 文件级 allowlist、测试清单（V-1~V-6）、禁止修改清单、残余风险。
> 不覆盖主 Design 无关内容（SectorSnapshot、22-field schema、P3-A/B 业务逻辑、DDL、Gate 授权均不在本卡范围）。

---

## 1. 裁定结论（RFC-03-014-F6 冻结）

Pascal 已裁定（RFC-03-014-F6 §3.1）：**`market_sentiment` 为 capability `sentiment.market_snapshot` 的唯一 canonical freshness domain key（TTL=3600s）**；**`sentiment_limit_up_pool` 为 capability `sentiment.limit_up_pool` 的唯一 canonical freshness domain key（TTL=3600s）**；`sentiment` **不是** freshness TTL key（仅 capability domain 前缀）。

capability → freshness domain key → TTL 的 canonical 映射：

| Capability | 域模型 | freshness domain key | TTL | 语义 |
|------------|--------|----------------------|-----|------|
| `sentiment.market_snapshot` | `MarketSentimentSnapshot`（22 字段全市场多维快照） | **`market_sentiment`** | 3600 | 市场级情绪聚合快照（唯一键 `{market, snapshot_date, snapshot_time}`） |
| `sentiment.limit_up_pool` | `LimitUpPoolRecord`（个股涨跌停详情） | **`sentiment_limit_up_pool`** | 3600 | 个股级涨停/跌停池（唯一键 `{market, symbol, trade_date}`，见 RFC-03-014-F1） |
| `sector.snapshot` / `sector.ranking` | `SectorSnapshot` | `sector` | 21600 | 不变（identity） |
| `flow.capital_flow_daily` / `flow.northbound_daily` | `CapitalFlowRecord` | `flow` | 43200 | 不变（identity） |

**禁止项**（RFC C-1/C-2 / SPEC §8）：
- ❌ `FreshnessPolicy.DEFAULT_TTLS` 注册 `"sentiment"`（双 key/alias → freshness 漂移）。
- ❌ 运行时 freshness 查表依赖 `_DEFAULT_TTL=3600` 兜底（fallback 巧合 → 静默漂移）。
- ❌ 合并 `market_sentiment` 与 `sentiment_limit_up_pool` 为单 key。

---

## 2. 运行时现状与问题（2026-08-02 代码复核）

### 2.1 现状事实

| # | 事实 | 位置 |
|---|------|------|
| F-1 | `sentiment_service.get_market_sentiment_snapshot()` / `get_limit_up_pool()` 以 `domain=self.DOMAIN`（=`"sentiment"`）调用 `router.query()` | `services/sentiment_service.py` L210-219 / L365-371 |
| F-2 | `query()` Branch 3 从 `capability` 重新派生 `domain, _, operation = capability.partition(".")` → `domain="sentiment"` | `router.py` L372 |
| F-3 | `_query_external_chain_with_cache(..., domain="sentiment", ...)` 把 `domain` 传给 Step 2/3/4 | `router.py` L406-416 |
| F-4 | Step 4 `_query_external_chain` / Branch 2 `_query_external_single` 把 `domain="sentiment"` 传给 `_resolve_external_freshness_label(capability, ts, data_signal, domain)` | `router.py` L1035-1037 / L1115-1117 |
| F-5 | `_resolve_external_freshness_label` 在 data_signal=None（空结果）分支与 non-P3 分支调用 `self._freshness.label(ts, data_signal, domain, False)` —— **domain 参数为 `"sentiment"`** | `router.py` L1217-1226 |
| F-6 | `_materialize()` 在非 P3 成功路径调用 `LocalMongoAdapter.put` / `CacheManager.put(..., domain, ...)`；两者内部用 `get_ttl(domain)` 计算 `expires_at` —— **domain 参数为 `"sentiment"` 时会命中 `_DEFAULT_TTL=3600` 兜底** | `router.py` L867-880；`cache_manager.py` L193；`local_mongo_adapter.py` L203 |
| F-7 | P3 读路径只读不变量：6 个 P3 capability 跳过 `_materialize`（`_is_p3_capability` guard）→ 当前查询路径 **不会** 触发 `CacheManager.put("sentiment")`；但 `_materialize` 的 put-domain 语义错误是**潜在缺陷**（若未来放宽 guard 或新增非 P3 sentiment 类 capability 即触发） | `router.py` L983-991（call-site guard）、L863（in-method guard） |
| F-8 | `CacheManager.get(security_id, domain, operation, params)` 用 `domain` 参与 cache key 计算（SHA256）；`_try_cache` 传给它的 `domain` 是 `"sentiment"` | `cache_manager.py` L118-120、L142-144 |
| F-9 | `FreshnessPolicy.DEFAULT_TTLS` 已有 `market_sentiment=3600` 与 `sentiment_limit_up_pool=3600` 两个 canonical 键，**无** `"sentiment"` 键 | `freshness.py` L49-84 |
| F-10 | 测试 `test_mapping_sentiment.TestFreshnessTableSentiment` 已断言两 canonical 键 ∈ DEFAULT_TTLS + TTL=3600 + `get_ttl` 两键均 3600；**缺**「`sentiment` 不在 DEFAULT_TTLS」断言 | `tests/test_mapping_sentiment.py` L401-436 |

### 2.2 问题定义

1. **运行时 freshness 查表使用错误 key**：`_resolve_external_freshness_label` / `_materialize` 把 capability domain 前缀（`"sentiment"`）当作 freshness/cache TTL 查表 key 传入。`get_ttl("sentiment")` 命中 `_DEFAULT_TTL=3600` 兜底，**恰好**等于目标值——属 fallback 巧合（RFC §4.1）。
2. **canonical 表项从未被命中**：`market_sentiment` / `sentiment_limit_up_pool` 两个 canonical 键存在于 `DEFAULT_TTLS`，但在 sentiment capability 的任意运行时 freshness/cache TTL 查表中均不会被显式命中（RFC §2.1「表项从未被命中」）。
3. **潜在静默漂移**：若未来 `_DEFAULT_TTL` 被调低（如 1800），未修正的 fallback 路径会静默缩短 sentiment 缓存有效期（RFC §4.1 C-2 动机）。

### 2.3 修复目标

- TTL 值不变（`market_sentiment`=3600 / `sentiment_limit_up_pool`=3600）。
- freshness 标签语义不变（realtime/delayed/cached/stale/empty）。
- capability 契约不变（capability 字符串、`P3_COLLECTION_BY_CAPABILITY`、`_TA_CN_NOT_COVERED`、cache key 前缀 `sentiment:...`、DataResult.domain、业务唯一键、写入 schema）。
- 运行时 freshness/cache TTL 查表**显式解析 canonical key**，消除 `_DEFAULT_TTL=3600` fallback 巧合。

---

## 3. 运行时解析设计（capability → freshness domain）

### 3.1 核心函数：`DataRouter._freshness_domain_for(capability)`

**文件**：`skills/data/unified_data/router.py`

新增模块级常量（紧邻 `P3_COLLECTION_BY_CAPABILITY` import 处，`router.py` L86-92 附近）：

```python
# F6 ruling (RFC/SPEC-03-014-F6): capability → canonical freshness domain key.
# Only sentiment capabilities deviate from identity (their capability-domain
# prefix). Everything else maps to the domain prefix (identity), so non-P3
# freshness/cache TTL lookups are byte-for-byte unchanged.
_CAPABILITY_FRESHNESS_DOMAINS: dict[str, str] = {
    "sentiment.market_snapshot": "market_sentiment",
    "sentiment.limit_up_pool": "sentiment_limit_up_pool",
}
```

在 `_is_p3_capability`（L560-574）附近新增静态方法：

```python
@staticmethod
def _freshness_domain_for(capability: str) -> str:
    """Return the canonical freshness domain key for ``capability``.

    F6 ruling (RFC-03-014-F6 / SPEC-03-014-F6 §2.2):

    * ``sentiment.market_snapshot`` → ``market_sentiment``
    * ``sentiment.limit_up_pool`` → ``sentiment_limit_up_pool``
    * every other capability → its domain prefix (identity):
      ``sector.snapshot`` → ``sector``, ``flow.capital_flow_daily`` →
      ``flow``, ``market_data.kline_daily`` → ``market_data``, ...

    The capability-domain prefix (``sentiment``) is deliberately NOT a
    freshness TTL key — it must never be passed to
    :meth:`FreshnessPolicy.label` / :meth:`get_ttl` or to the TTL
    consult inside ``CacheManager.put`` / ``LocalMongoAdapter.put``.
    """
    domain, _, _ = capability.partition(".")
    return _CAPABILITY_FRESHNESS_DOMAINS.get(capability, domain)
```

**设计要点**：
- 与既有 `_is_p3_capability` / `_p3_collection_for` / `_p3_filter_for` 同为 staticmethod 模式，O(1) 查表。
- identity 缺省保证非 sentiment capability 的 freshness/cache 行为**完全不变**（sector→sector、flow→flow、market_data→market_data …）。
- 该函数是运行时解析的**唯一事实来源**；T3 不得在别处硬编码 sentiment 映射。

### 3.2 调用点 1：`_resolve_external_freshness_label`（freshness label 查表）

**文件**：`router.py` L1193-1226

将内部两个 `self._freshness.label(...)` 调用的 domain 参数从入参 `domain` 改为 `self._freshness_domain_for(capability)`：

```python
def _resolve_external_freshness_label(
    self,
    capability: str,
    ts: datetime,
    data_signal: str | None,
    domain: str,
) -> Any:
    """...（docstring 保持，补充 F6 说明）..."""
    # F6 (RFC/SPEC-03-014-F6): the freshness consult must use the
    # canonical freshness domain derived from the capability, NOT the
    # raw capability-domain prefix. ``_freshness_domain_for`` is
    # identity for every non-sentiment capability, so only sentiment
    # lookups change (sentiment → market_sentiment /
    # sentiment_limit_up_pool).
    freshness_domain = self._freshness_domain_for(capability)
    if data_signal is None:
        # Empty payload → ``"empty"``, same as the legacy branch.
        # We do not override this: freshness carries the
        # empty/non-empty signal regardless of capability scope.
        return self._freshness.label(ts, data_signal, freshness_domain, False)
    if capability in P3_COLLECTION_BY_CAPABILITY:
        # D2 contract — external Step-4 success for P3 capability
        # is always reported as ``"delayed"``.
        return "delayed"
    return self._freshness.label(ts, data_signal, freshness_domain, False)
```

> **注意**：`label(..., from_cache=False)` 不触发 `get_ttl`（`freshness.py` L158 仅在 `from_cache=True` 时查 TTL）。故对 sentiment 查询，本调用点的行为**不变**（空结果仍 `"empty"`、P3 成功仍 `"delayed"`），但 domain 参数显式化，spy 可断言（V-4）。真正触发 `get_ttl` 的查表在调用点 2。

### 3.3 调用点 2：`_materialize`（Cache/LocalMongo TTL 查表）

**文件**：`router.py` L832-880

`_materialize` 是 `CacheManager.put` / `LocalMongoAdapter.put` 的唯一调用方（query 路径），两者内部用 `get_ttl(domain)` 计算 `expires_at`。将 put 的 domain 参数改为由 capability 派生的 canonical key：

```python
def _materialize(
    self,
    security_id: SecurityId,
    domain: str,
    operation: str,
    params: Mapping[str, Any] | None,
    result: DataResult,
    *,
    capability: str | None = None,
) -> None:
    """...（docstring 保持，补充 F6 说明）..."""
    # Phase 3 read-only invariant — six P3 capabilities never
    # trigger _materialize. The kw-only ``capability`` is the
    # discriminator; an explicit ``None`` keeps backward
    # compatibility with the Phase 1B-B call sites.
    if capability is not None and self._is_p3_capability(domain, operation):
        return
    # F6 (RFC/SPEC-03-014-F6): the TTL consult inside the adapters
    # (``get_ttl``) must hit the canonical freshness key. For P3
    # capabilities this branch is unreachable (read-only guard above),
    # so this is a future-proofing + correctness fix; for non-P3
    # capabilities ``_freshness_domain_for`` is identity, so the
    # adapter cache/materialized keys are unchanged.
    put_domain = domain
    if capability is not None:
        put_domain = self._freshness_domain_for(capability)
    if self._local_mongo_adapter is not None:
        try:
            self._local_mongo_adapter.put(
                security_id, put_domain, operation, params, result
            )
        except Exception as exc:
            logger.warning("LocalMongoAdapter.put failed in router: %s", exc)
    if self._cache_manager is not None:
        try:
            self._cache_manager.put(
                security_id, put_domain, operation, params, result
            )
        except Exception as exc:
            logger.warning("CacheManager.put failed in router: %s", exc)
```

> **关键约束**：P3 guard（`_is_p3_capability(domain, operation)`）**必须继续使用 capability domain 前缀** `domain`（`"sentiment"`），**不能**改用 `put_domain`——否则 `"market_sentiment.market_snapshot"` 不在 `P3_COLLECTION_BY_CAPABILITY` 中，P3 只读不变量会被破坏。`put_domain` 只用于 put 的 domain 参数（影响 adapter 内部 `get_ttl` 查表与存储 `domain` 字段）。

### 3.4 不变项（禁止修改）

| 组件 | 不变内容 | 理由 |
|------|---------|------|
| `_try_cache` → `CacheManager.get(security_id, domain, operation, params)` | `domain` 保持 `"sentiment"` | `CacheManager.get` 不查 TTL（`cache_manager.py` L140-172 读存储的 `expires_at`）；cache key 参与 SHA256 计算，改 key 会改变缓存命名空间（SPEC §3.3「cache key 前缀不变」）。get 的 domain 只影响 cache key，不影响 freshness 语义 |
| `_try_materialized` → P3 writer filter | `domain` 保持 `"sentiment"` | 业务键 filter 派生（`_p3_filter_for`）使用 capability domain；与 freshness 无关 |
| `DataResult.domain` | 保持 `"sentiment"`（capability domain 前缀） | RFC §3.3：capability domain 与 freshness TTL key 是两个层级；`DataResult.domain` 是 capability 语义 |
| `FreshnessPolicy.DEFAULT_TTLS` | 键值不变（已是 canonical） | 本卡不改 `freshness.py` 表；仅可选补注释（见 §6） |
| `quality/config.py` | 不动 | Phase 2 独立 TTL 表，不含 sentiment 域 |
| `cache_manager.py` / `local_mongo_adapter.py` | 不动 | 仅消费 `get_ttl(domain)`，由调用方（router）修正 domain（SPEC §6.3） |

### 3.5 数据流（修正后）

```
sentiment.market_snapshot query:
  MarketSentimentService.get_market_sentiment_snapshot()
    → router.query(domain="sentiment", operation="market_snapshot")
      → capability = "sentiment.market_snapshot"
      → Branch 3: _query_external_chain_with_cache(..., domain="sentiment", ...)
        → Step 3 _try_cache: CacheManager.get(sid, "sentiment", ...)   # cache key 不变
        → Step 4 _query_external_chain → _resolve_external_freshness_label(
              capability, ts, data_signal, domain)
            └─ freshness_domain = _freshness_domain_for("sentiment.market_snapshot")
                 = "market_sentiment"
            └─ label(ts, data_signal, "market_sentiment", False)       # F6 修正
        → success non-P3 (仅当非 P3): _materialize(..., capability=capability)
            └─ put_domain = _freshness_domain_for(capability)           # F6 修正
            └─ CacheManager.put(sid, put_domain, ...) → get_ttl("market_sentiment") = 3600
```

---

## 4. 测试矩阵（SPEC-03-014-F6 §5 落实）

### 4.1 测试清单

| # | 测试 | 文件 | 验证命令 | 断言要点 |
|---|------|------|---------|---------|
| V-1 | canonical key ∈ DEFAULT_TTLS + TTL=3600（C-1/C-2） | `tests/test_freshness_policy.py`（修改：追加 `TestDefaultTTLSCanonicalSentimentKeys`） | `pytest` | `"market_sentiment" in DEFAULT_TTLS` 且 `== 3600`；`"sentiment_limit_up_pool" in DEFAULT_TTLS` 且 `== 3600` |
| V-2 | `sentiment` 不在 DEFAULT_TTLS（C-3） | `tests/test_freshness_policy.py`（修改） | `pytest` | `"sentiment" not in DEFAULT_TTLS` |
| V-3 | `get_ttl` 两 canonical key = 3600（C-4） | `tests/test_freshness_policy.py`（修改） | `pytest` | `FreshnessPolicy().get_ttl("market_sentiment") == 3600`；`get_ttl("sentiment_limit_up_pool") == 3600` |
| V-4 | router freshness domain 解析 spy（C-5） | **新增** `tests/test_router_p3_freshness_domain.py` | `pytest` | 见 §4.2 spy 模板 |
| V-5 | 既有 `TestFreshnessTableSentiment` 断言继续 PASS（兼容性） | `tests/test_mapping_sentiment.py`（追加 C-3 断言，不动既有断言） | `pytest` | 既有 4 个断言不改；追加 `"sentiment" not in DEFAULT_TTLS` |
| V-6 | 全量回归 | `skills/data/unified_data/tests` | `.venv/bin/python -m pytest skills/data/unified_data/tests -q` | exit 0；基线 1322 passed（2026-08-02） |

### 4.2 V-4 spy 断言模板（`tests/test_router_p3_freshness_domain.py`）

零真实 I/O；`unittest.mock` / mongomock 即可。模板如下（T3 按实际构造签名适配）：

```python
"""Router freshness-domain resolution spy tests (SPEC-03-014-F6 V-4 / C-5).

Proves the runtime freshness/cache TTL consult for sentiment
capabilities resolves to the canonical freshness domain key
(``market_sentiment`` / ``sentiment_limit_up_pool``) and never to the
capability-domain prefix ``sentiment``. Zero real I/O.
"""
from skills.data.unified_data.freshness import FreshnessPolicy
from skills.data.unified_data.router import DataRouter
from skills.data.unified_data.models import Market, SecurityId


class _RecordingFreshnessPolicy(FreshnessPolicy):
    """FreshnessPolicy spy — records the ``domain`` arg of every call."""

    def __init__(self) -> None:
        super().__init__()
        self.label_domains: list[str] = []
        self.get_ttl_domains: list[str] = []

    def label(self, fetched_at, data_date, domain, from_cache):
        self.label_domains.append(domain)
        return super().label(fetched_at, data_date, domain, from_cache)

    def get_ttl(self, domain: str) -> int:
        self.get_ttl_domains.append(domain)
        return super().get_ttl(domain)


def _build_router(*, capability: str, payload: Any):
    """Build a DataRouter with a recording freshness policy and a
    one-shot provider (reuse the _OneShotProvider helper pattern from
    tests/test_router_p3_readonly.py)."""
    ...


def test_freshness_domain_mapping_is_canonical():
    """_freshness_domain_for returns canonical keys for sentiment and
    identity for everything else."""
    router = DataRouter()
    assert router._freshness_domain_for("sentiment.market_snapshot") == "market_sentiment"
    assert router._freshness_domain_for("sentiment.limit_up_pool") == "sentiment_limit_up_pool"
    # identity — sector / flow / non-P3 unchanged
    assert router._freshness_domain_for("sector.snapshot") == "sector"
    assert router._freshness_domain_for("flow.capital_flow_daily") == "flow"
    assert router._freshness_domain_for("market_data.kline_daily") == "market_data"


def test_sentiment_market_snapshot_query_label_uses_canonical_domain():
    """Empty external result → label() receives ``market_sentiment``,
    never ``sentiment`` (C-5)."""
    sid = SecurityId(market=Market.CN, symbol="market:cn")
    router = _build_router(capability="sentiment.market_snapshot", payload=[])  # empty
    result = router.query(domain="sentiment", operation="market_snapshot", security_id=sid)
    assert "market_sentiment" in router.freshness.label_domains
    assert "sentiment" not in router.freshness.label_domains


def test_sentiment_limit_up_pool_query_label_uses_canonical_domain():
    """Empty external result → label() receives ``sentiment_limit_up_pool``."""
    sid = SecurityId(market=Market.CN, symbol="limit_up_pool:2026-08-01")
    router = _build_router(capability="sentiment.limit_up_pool", payload=[])
    result = router.query(domain="sentiment", operation="limit_up_pool", security_id=sid)
    assert "sentiment_limit_up_pool" in router.freshness.label_domains
    assert "sentiment" not in router.freshness.label_domains


def test_get_ttl_never_receives_sentiment_on_query_path():
    """No sentiment-capability query path may call get_ttl with the
    capability-domain prefix ``sentiment`` (C-2/C-5). P3 read-only
    invariant keeps _materialize (the only get_ttl consumer) off the
    query path, and label(from_cache=False) never consults TTL."""
    sid = SecurityId(market=Market.CN, symbol="market:cn")
    router = _build_router(capability="sentiment.market_snapshot", payload=[{"row": 1}])
    result = router.query(domain="sentiment", operation="market_snapshot", security_id=sid)
    assert "sentiment" not in router.freshness.get_ttl_domains


def test_materialize_put_domain_derived_from_capability():
    """Direct _materialize call with a NON-P3 capability → the put
    domain equals ``_freshness_domain_for(capability)`` (identity);
    proves the TTL consult inside CacheManager.put/LocalMongoAdapter.put
    flows from the resolution function (C-5)."""
    sid = SecurityId(market=Market.CN, symbol="600519")
    router, local_spy, cache_spy = _build_router_with_spy_adapters()  # reuse readonly spy helpers
    router._materialize(
        sid, "market_data", "kline_daily", {}, _fake_result(),
        capability="market_data.kline_daily",
    )
    assert local_spy.puts[0][1] == "market_data"   # put domain == identity
    assert cache_spy.puts[0][1] == "market_data"


def test_p3_sentiment_materialize_still_readonly():
    """P3 guard unchanged: _materialize with a sentiment capability is
    a no-op (zero puts) — the read-only invariant is preserved (V-5
    compatibility with test_router_p3_readonly)."""
    sid = SecurityId(market=Market.CN, symbol="market:cn")
    router, local_spy, cache_spy = _build_router_with_spy_adapters()
    router._materialize(
        sid, "sentiment", "market_snapshot", {}, _fake_result(),
        capability="sentiment.market_snapshot",
    )
    assert local_spy.puts == []
    assert cache_spy.puts == []
```

> **V-4 范围说明**：`CacheManager.put` 的 domain 参数无法在 sentiment **查询**路径直接 spy（P3 只读 guard 使 put 零调用，F-7）。V-4 通过 ① `_freshness_domain_for` 映射断言、② label domain spy（空结果分支可观测）、③ 非 P3 `_materialize` put-domain 直调断言、④ P3 `_materialize` 只读回归 四层覆盖 C-5。若 T3 采用「service 层解析」替代方案（SPEC §6.1 备选），则 spy 落点改到 service 对应函数，断言不变。

### 4.3 静态验证命令（对齐 SPEC-03-014-F6 §5.2）

```bash
# 1) 契约层：SPEC canonical 键存在且无 sentiment TTL 键
grep -n '"market_sentiment"' docs/spec/03_data/SPEC-03-014-f6-market-sentiment-freshness-key-amendment.md
grep -n '"sentiment_limit_up_pool"' docs/spec/03_data/SPEC-03-014-f6-market-sentiment-freshness-key-amendment.md
# 2) 实现层与契约层键名一致
grep -n '"market_sentiment"' skills/data/unified_data/freshness.py
grep -n '"sentiment_limit_up_pool"' skills/data/unified_data/freshness.py
# 3) 主文档 drift 已清除
grep -n '"sentiment": 3600' docs/spec/03_data/SPEC-03-014-unified-data-phase-3-persistent-data-expansion.md  # 期望无输出
# 4) F6 运行时解析已落地
grep -n '_freshness_domain_for' skills/data/unified_data/router.py
grep -n '_CAPABILITY_FRESHNESS_DOMAINS' skills/data/unified_data/router.py
```

---

## 5. T3 Implement allowlist（文件级）

> 依据 SPEC-03-014-F6 §6.1，由本 Design 裁决最终范围。**只改下列文件**；不在列表中的任何文件改动视为越界。

| # | 文件 | 允许操作 | 约束 |
|---|------|---------|------|
| 1 | `skills/data/unified_data/router.py` | ① 新增模块级 `_CAPABILITY_FRESHNESS_DOMAINS`；② 新增 `_freshness_domain_for(capability)` staticmethod；③ `_resolve_external_freshness_label` 内 freshness domain 显式化（§3.2）；④ `_materialize` put_domain 派生（§3.3） | 不改非 P3 capability 路径；不改 `_is_p3_capability` / `_p3_collection_for` / `_p3_filter_for` 语义；不改 Step 4 只读不变量；不改 `_materialize` 的 P3 guard（仍用 `domain`）；不改 `_try_cache` / `_try_materialized` 的 domain 传参（§3.4） |
| 2 | `skills/data/unified_data/services/sentiment_service.py` | **默认不动**（解析逻辑集中在 router，本 Design 裁决） | 若 T3 发现 service 独立查表点遗漏，须先回写本 Design 再改 |
| 3 | `skills/data/unified_data/freshness.py` | 可选：补注释说明 `sentiment` 非 TTL key | 表键已 canonical，**无键值变更** |
| 4 | `skills/data/unified_data/tests/test_freshness_policy.py` | 追加 V-1~V-3 断言（新 TestClass 或追加方法） | 不改既有 FP-001..FP-008 / `test_default_ttls_constant` 语义 |
| 5 | `skills/data/unified_data/tests/test_mapping_sentiment.py` | 追加 C-3 断言（`"sentiment" not in DEFAULT_TTLS`） | 既有 `TestFreshnessTableSentiment` 4 个断言不动 |
| 6 | `skills/data/unified_data/tests/test_router_p3_freshness_domain.py` | **新增**：V-4 spy 测试（§4.2 模板） | 零真实 I/O；mongomock/unittest.mock；可复用 `test_router_p3_readonly.py` 的 spy adapter 与 `_OneShotProvider` helper |

---

## 6. 禁止修改清单（对齐 SPEC-03-014-F6 §6.3）

- ❌ `quality/config.py`（Phase 2 独立 TTL 表，不含 sentiment 域）。
- ❌ `cache_manager.py` / `local_mongo_adapter.py`（仅消费 `get_ttl(domain)`，由 router 修正 domain；不改其内部实现）。
- ❌ `providers/*`、`models/domain/*`、`adapters/p3_persistence_writer.py`、`client.py`。
- ❌ `_TA_CN_NOT_COVERED`、`P3_COLLECTION_BY_CAPABILITY`、`P3_UNIQUE_KEYS_BY_CAPABILITY`、capability 字符串、业务唯一键、写入 schema、refresh 三态守卫。
- ❌ 任何 `.env`、config、requirements、SKILL.md、README、cron/systemd/webhook。
- ❌ 在 `DEFAULT_TTLS` 注册 `"sentiment"`；依赖 `_DEFAULT_TTL=3600` 兜底；合并两 canonical key。
- ❌ 修改 TTL 值（3600/3600/21600/43200 不变）。
- ❌ Git commit/push（本 Design 卡只读文档；T3 由 Implement 卡自行决定提交节奏，且不越界）。

---

## 7. 主 DESIGN-03-014 最小同步记录（本卡完成）

| 位置 | 修改前 | 修改后 |
|------|--------|--------|
| 元数据 最后更新 / 版本号 | V0.26（2026-07-31 P1 Design Amendment） | V0.27（2026-08-02 F6 freshness canonical key 同步） |
| changelog | 末行 V0.26 | 追加 V0.27 行 |
| §0.3 `freshness.py` 行（L81） | 注：`sentiment` 已改用 `market_sentiment` 与 SPEC 命名不一致 | 注：`market_sentiment` / `sentiment_limit_up_pool` 已为 canonical（F6 裁定，见 §4.4 与 DESIGN-03-014-F6） |
| §1.2 交付物表行 7（L193） | market_sentiment=3600（注：磁盘与 SPEC 命名不一致…） | market_sentiment=3600（canonical，F6 裁定；`sentiment` 非 TTL key） |
| §4.4（L1052-1056） | ⚠️ 跨层命名不一致：磁盘 `market_sentiment` vs SPEC `sentiment`；需 Principal 发起独立 Full Flow | canonical 已冻结（RFC/SPEC-03-014-F6）：`market_sentiment` / `sentiment_limit_up_pool` 两键；`sentiment` 非 TTL key；运行时解析见 DESIGN-03-014-F6 |
| §P0.7.2（L2304） | `market_sentiment` vs `sentiment` freshness 命名冲突 仅披露，不改 PC-11 | 已裁定（F6）：canonical 冻结，见 DESIGN-03-014-F6 |
| §P0.7.4（L2314-2322） | 命名不一致表：`sentiment` 不动；标注「命名不一致，PC-11」 | 改为 canonical 表：`market_sentiment` / `sentiment_limit_up_pool` 为唯一 key；`sentiment` 非 TTL key |
| §P0.10.4 残余风险（L2448） | Freshness 命名冲突 冻结（PC-11） | 已裁定（RFC-03-014-F6），移除/标注解除 |
| §P1.11（L2878-2884） | PC-11 保持冻结，不擅自裁定 | 冻结解除：canonical 已冻结（F6 裁定），运行时对齐归 F6 Implement |
| §P1.12 RD-2（L2891） | 冻结——不擅自裁定；P3 finalize 前 Pascal 决断 | 已裁定（RFC-03-014-F6）；运行时对齐归 F6 Implement（DESIGN-03-014-F6） |

---

## 8. 残余风险与未验证事项

| # | 事项 | 状态 | 说明 |
|---|------|------|------|
| U-1 | 运行时 freshness domain 解析修正（§3）尚未实施 | 待 T3 Implement + V-4 spy 验证 | 本卡只读，未运行实现验证 |
| U-2 | V-1~V-6 测试断言尚未落地 | 待 T3 Implement / T4 Verify | 本卡仅给出模板与断言要点 |
| U-3 | 真实 Mongo / Provider 行为（PR-1/PR-4）未执行 | 待 P2 Pascal Gate | 与 freshness key 无耦合；TTL 为纯配置层 |
| U-4 | `_DEFAULT_TTL=3600` 兜底在未来被调低时，未修正路径会静默缩短 sentiment 缓存有效期 | 已消除（本设计） | 若未来改 `_DEFAULT_TTL` 需回归 V-4 |
| U-5 | `quality/config.py` 若未来覆盖 P3 域需单独裁定 | 观察项 | 本次不影响 |
| U-6 | 本卡未运行全量 1322 回归（Design 只读，无代码改动） | 本卡无代码改动 | 基线 1322 passed 由 T1（2026-08-02）与直接相关 100 passed（2026-08-02 本卡复核）支撑；T4 Verify 须重跑全量 |

**验证命令（本卡已运行）**：
- `.venv/bin/python -m pytest skills/data/unified_data/tests/test_freshness_policy.py skills/data/unified_data/tests/test_mapping_sentiment.py skills/data/unified_data/tests/test_router_p3_readonly.py skills/data/unified_data/tests/test_router_p3_internal_first_materialized_read.py skills/data/unified_data/tests/test_sentiment_service.py -q` → **100 passed in 0.29s**
- 静态 grep 复核（§2 事实 F-1~F-10、canonical 表项、无 `"sentiment"` TTL key）→ PASS
- `git diff --check` → exit 0（待 §7 同步完成后复跑）
