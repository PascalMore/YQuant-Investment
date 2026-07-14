# DESIGN-03-008: Unified Data Phase 1B-A — 查询平面详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-14 |
| 最后更新 | 2026-07-14 |
| 来源 RFC | RFC-03-008 |
| 来源 SPEC | SPEC-03-008 |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约） |
| 关联 Design | DESIGN-03-007（Unified Data Layer 总设计，Phase 1B 定义 §2111-2136） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 版本号 | V0.1 |

---

## 1. 设计摘要

本设计为 Phase 1B-A（查询平面与外部降级）提供**最小可实现的详细设计**，精度到文件路径、类签名、方法合同和测试矩阵。核心决策：

1. **TA-CN capability 映射硬编码**为 `DataRouter` 内部常量 `_TA_CN_CAPABILITY_METHOD_MAP`（dict）—— 1B-A 范围固定，1B-B 再考虑配置化。
2. **DataRouter 行为变更**（抛异常 → 返回 `DataResult.error`）**不引入 Feature Flag**，直接修改；Phase 0 测试同步更新断言。
3. **限流/重试框架**用 `rate_limiter.py`（独立工具模块）提供装饰器 `@with_retry` + 类 `RateLimiter`，TushareProvider/AKShareProvider 通过组合使用。
4. **外部 Provider stub DataFrame** 按 capability 返回预定义列的子集，不调用真实 API。
5. **TA-CN 覆盖但返回空**：不继续外部 fallback（按 SPEC §4.3）；TA-CN 不覆盖 → 继续 Step 4。

实现优先级：先 Router+Registry+FreshnessPolicy 纯逻辑（零外部依赖），再加 Provider 框架（含 rate_limiter），最后 UnifiedDataClient 接入。

---

## 2. 现状分析

### 2.1 相关文件

| 文件 | 行数 | 状态 |
|---|---|---|
| `skills/data/unified_data/router.py` | 238 | Phase 0 外部 fallback 版；需增强 |
| `skills/data/unified_data/registry.py` | 171 | Phase 0 基础版；需增强 |
| `skills/data/unified_data/client.py` | 315 | Phase 0 + 1A 入口方法；需修改 query() 和 __init__ |
| `skills/data/unified_data/provider.py` | 121 | DataProvider ABC；不修改 |
| `skills/data/unified_data/config.py` | 58 | UnifiedDataConfig；不修改 |
| `skills/data/unified_data/exceptions.py` | 71 | 异常体系；不修改（AllProvidersFailedError 保留但不作为 Router 主出口） |
| `skills/data/unified_data/models/__init__.py` | 524 | SecurityId/DataResult/Capability；不修改 |
| `skills/data/unified_data/__init__.py` | 119 | 模块导出；需增加导出 |
| `skills/data/unified_data/adapters/ta_cn_mongo_adapter.py` | 380 | TA-CN 只读 adapter；不修改 |
| `tests/data/unified_data/conftest.py` | 150 | 测试 fixtures；需增强（FakeTA_CNAdapter） |
| `tests/data/unified_data/fixtures/__init__.py` | 163 | FakeDatabase 等；不修改 |
| `tests/data/unified_data/test_router.py` | 449 | Phase 0 路由测试；AllProvidersFailedError 断言需更新 |

### 2.2 现有约束

- TA-CN adapter 11 个读方法签名固定；DataRouter Step 1 通过 `_TA_CN_CAPABILITY_METHOD_MAP` 将 capability 映射到 adapter 方法。
- `DataResult.success()` 将空 payload（None/空 DataFrame）自动转为 `provider="empty"` / `freshness="empty"`。
- `DataResult.error()` 已存在（Phase 0 models），直接可用。
- Phase 0 DataRouter 全部失败时**抛 `AllProvidersFailedError`**，1B-A 必须改为**返回 `DataResult.error()`**。

### 2.3 兼容性风险

| 风险项 | 等级 | 缓解 |
|---|---|---|
| Phase 0 test_router.py 断言 `AllProvidersFailedError` | 高 | 明确更新清单（§5.6），Implement 同步修改 |
| ta_cn_adapter=None 时 Step 1 跳过 → 退化为 Phase 0 行为 | 低 | 已在 SPEC §11.1 定义退化路径 |
| `provider="ta_cn_internal"` 不在 `external_fallback_chains` 中 | 低 | provider 参数优先级最高，不参与 chain 解析 |

---

## 3. 方案设计

### 3.1 模块/类图与查询控制流

```
┌──────────────────────────────────────────────────────┐
│ UnifiedDataClient                                     │
│ ┌──────────────────────────────────────────────────┐ │
│ │ query(domain, operation, sid, *, provider=None,  │ │
│ │       force_refresh=False, ...) → DataResult     │ │
│ │   └─► self._router.query(...)                    │ │
│ └──────────────────────────────────────────────────┘ │
│ 14 个域入口方法（不变，直连 TA-CN）                    │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│ DataRouter（增强版）                                   │
│ ┌──────────────────────────────────────────────────┐ │
│ │ __init__(registry, config, *, ta_cn_adapter=None,│ │
│ │    local_mongo_adapter=None, cache_manager=None, │ │
│ │    freshness=None, external_fallback_chains=None)│ │
│ │                                                   │ │
│ │ query(domain, operation, sid, *, provider=None,  │ │
│ │    force_refresh=False, ...) → DataResult        │ │
│ │                                                   │ │
│ │   provider = "ta_cn_internal"? ──► _query_ta_cn  │ │
│ │   provider = "tushare"/"akshare"? ──► _query_ext │ │
│ │                                                   │ │
│ │   force_refresh=False AND ta_cn_adapter:         │ │
│ │     Step 1: _try_ta_cn() ──► 命中 → DataResult   │ │
│ │                      ──► 覆盖但空 → DataResult    │ │
│ │                      ──► 不覆盖 → None（继续）    │ │
│ │                      ──► 异常 → trace, None      │ │
│ │                                                   │ │
│ │   Step 2/3: 占位跳过（1B-A）                      │ │
│ │                                                   │ │
│ │   Step 4: _query_external_chain()                 │ │
│ │     ├─ resolve chain: external_fallback_chains   │ │
│ │     │  [cap] → config.fallback_for(cap)          │ │
│ │     │  → registry order                          │ │
│ │     ├─ try each: is_available? → fetch           │ │
│ │     ├─ 命中 → DataResult.success(...)             │ │
│ │     └─ 全失败 → DataResult.error(...)            │ │
│ └──────────────────────────────────────────────────┘ │
│                                                       │
│ _TA_CN_CAPABILITY_METHOD_MAP (硬编码常量)             │
│   capability → (adapter_method_name, extra_kwargs)   │
│   共 11 条映射（见 §3.3.3）                           │
└──────────────────────┬───────────────────────────────┘
                       │
          ┌────────────┼──────────────┐
          ▼            ▼              ▼
┌──────────────┐ ┌────────────┐ ┌──────────────┐
│ProviderReg.. │ │FreshnessPol│ │Providers     │
│(增强版)      │ │icy         │ │              │
│              │ │            │ │ TushareProv. │
│+set_ext_fb   │ │get_ttl()   │ │ AKShareProv. │
│ _chains()    │ │label()     │ │              │
│+get_ext_fb   │ │            │ │ base_external│
│ _chain()     │ │            │ │   .py        │
└──────────────┘ └────────────┘ │  (ABC +      │
                                │  RateLimiter │
                                │  + @with_retry│
                                └──────────────┘
```

### 3.2 文件改动清单（精确路径 · 新增/修改）

#### 3.2.1 新增文件（8 个）

| # | 文件路径 | 职责 | 预估行数 |
|---|---|---|---|
| 1 | `skills/data/unified_data/providers/__init__.py` | provider 包初始化 + 公开导出 TushareProvider/AKShareProvider | ~10 |
| 2 | `skills/data/unified_data/providers/base_external.py` | `BaseExternalProvider` ABC：限流 (`RateLimiter`) / 指数退避重试 (`@with_retry`) / canonical 转换框架 (`_to_canonical` hook) | ~80 |
| 3 | `skills/data/unified_data/providers/tushare.py` | `TushareProvider(BaseExternalProvider)`：name/tushare, 13 capability, is_available(token 检测), fetch stub, 限流 200 RPM | ~100 |
| 4 | `skills/data/unified_data/providers/akshare.py` | `AKShareProvider(BaseExternalProvider)`：name/akshare, 7 capability, is_available(import 检测), fetch stub, 限流 0.5s delay | ~80 |
| 5 | `skills/data/unified_data/providers/rate_limiter.py` | `RateLimiter` 类（token bucket）+ `with_retry` 装饰器（指数退避） | ~60 |
| 6 | `skills/data/unified_data/freshness.py` | `FreshnessPolicy`：`DEFAULT_TTLS` 表 + `get_ttl(domain)` + `label(fetched_at, data_date, domain, from_cache)`，纯函数 | ~50 |
| 7 | `tests/data/unified_data/test_freshness_policy.py` | FreshnessPolicy UT（8 条，FP-001~FP-008） | ~80 |
| 8 | `tests/data/unified_data/test_providers.py` | TushareProvider + AKShareProvider UT（13 条，TP-001~007 + AK-001~006） | ~120 |
| 9 | `tests/data/unified_data/test_router_internal_first.py` | DataRouter internal-first 编排 UT + IT（16 条，DR-001~012 + IT-001~004） | ~200 |

> 注：上表共 9 个新增文件（task body 要求至少 8 个新增，此处为 9 个以覆盖 rate_limiter 独立模块）。

#### 3.2.2 修改文件（4 个）

| # | 文件路径 | 修改内容 | 关键变更 |
|---|---|---|---|
| 10 | `skills/data/unified_data/router.py` | ① 构造新增 5 个可选参数；② query() 新增 `force_refresh` 参数；③ 实现四步编排（`_try_ta_cn` / `_query_external_chain` / `_query_ta_cn` / `_query_external_single`）；④ 全部失败返回 `DataResult.error()` 不抛异常；⑤ 增加 `_TA_CN_CAPABILITY_METHOD_MAP` 常量 | 行为变更：抛异常 → 返回 error |
| 11 | `skills/data/unified_data/registry.py` | ① 新增 `_external_fallback_chains: dict[str, list[str]]` 属性；② 新增 `set_external_fallback_chains()`；③ 新增 `get_external_fallback_chain()` | 不修改已有方法签名 |
| 12 | `skills/data/unified_data/client.py` | ① `__init__` 将 `ta_cn_adapter` / `freshness` / `external_fallback_chains` 传入 Router；② `query()` 新增 `force_refresh` 参数透传；③ 14 个域入口方法不变 | `force_refresh` 默认 False，向后兼容 |
| 13 | `skills/data/unified_data/__init__.py` | 导出 TushareProvider / AKShareProvider / FreshnessPolicy / RateLimiter（如需要） | 新增 3-4 个导出 |

### 3.3 接口与数据结构

#### 3.3.1 DataRouter 增强版签名

```python
# 文件: skills/data/unified_data/router.py
from typing import Mapping, Any
from datetime import datetime

class DataRouter:
    # ── TA-CN capability 映射（硬编码常量，11 条）──
    # capability → (adapter_method_name, extra_kwargs_hint)
    # adapter_method_name 是 TA_CNMongoAdapter 的方法名（str）
    # extra_kwargs_hint 用于告知 Router 将 SecurityId 的 symbol 传给哪个参数
    _TA_CN_CAPABILITY_METHOD_MAP: dict[str, str] = {
        # 行号 ~20，位于类体最顶部
        "market_data.kline_daily":  "get_daily_bars",
        "market_data.realtime_quote": "get_realtime_quotes",
        "financial.income_statement": "get_financials",
        "financial.balance_sheet":   "get_financials",
        "financial.cash_flow":       "get_financials",
        "metadata.stock_list":       "get_stock_list",
        "metadata.stock_info":       "get_stock_info",
        "metadata.index_list":       "get_index_list",
        "metadata.index_info":       "get_index_info",
        "market_data.index_daily":   "get_index_daily_bars",
        "news.stock_news":           "get_news",
    }

    # TA-CN 不覆盖的 capability 集合（直接走 Step 4）
    _TA_CN_NOT_COVERED: frozenset[str] = frozenset({
        "market_data.kline_weekly",
        "market_data.adj_factor",
        "valuation.daily_basic",
        "calendar.trading_days",
        "calendar.is_trading_day",
        "metadata.index_members",
    })

    def __init__(
        self,
        registry: ProviderRegistry,
        config: UnifiedDataConfig | None = None,
        *,
        ta_cn_adapter: "TA_CNMongoAdapter | None" = None,   # [1B-A 新增]
        local_mongo_adapter: "LocalMongoAdapter | None" = None,  # [1B-B 占位]
        cache_manager: "CacheManager | None" = None,            # [1B-B 占位]
        freshness: "FreshnessPolicy | None" = None,             # [1B-A 新增]
        external_fallback_chains: dict[str, list[str]] | None = None,  # [1B-A 新增]
    ) -> None:
        self._registry = registry
        self._config = config or UnifiedDataConfig.minimal()
        self._ta_cn_adapter = ta_cn_adapter
        self._local_mongo_adapter = local_mongo_adapter
        self._cache_manager = cache_manager
        self._freshness = freshness or FreshnessPolicy()
        self._external_chains = dict(external_fallback_chains or {})

    def query(
        self,
        domain: str,
        operation: str,
        security_id: SecurityId,
        *,
        provider: str | None = None,
        force_refresh: bool = False,                      # [1B-A 新增]
        market: Market | str | None = None,
        params: Mapping[str, Any] | None = None,
        fetched_at: datetime | None = None,
    ) -> DataResult:
        """internal-first 四步编排查询。全部失败时返回 DataResult.error() 而非抛异常。"""
```

#### 3.3.2 DataRouter 内部方法签名（编排逻辑）

```python
# 以下为 DataRouter 新增私有方法

def _try_ta_cn(
    self,
    capability: str,
    security_id: SecurityId,
    params: dict,
    trace: list[str],
    ts: datetime,
) -> DataResult | None:
    """Step 1 尝试 TA-CN adapter。

    Returns:
        DataResult: TA-CN 覆盖该 capability 且成功（命中或空）。
        None: TA-CN 不覆盖该 capability 或异常——Router 继续 Step 4。
    """
    if capability in self._TA_CN_NOT_COVERED:
        return None  # 不覆盖 → 继续
    if capability not in self._TA_CN_CAPABILITY_METHOD_MAP:
        return None  # 防御：未映射 → 继续

    method_name = self._TA_CN_CAPABILITY_METHOD_MAP[capability]
    try:
        adapter_method = getattr(self._ta_cn_adapter, method_name)
        raw = adapter_method(security_id.symbol, **self._adapter_kwargs(capability, params))
    except Exception as exc:
        trace.append(f"ta_cn_internal(error: {exc})")
        return None  # 异常 → 继续 Step 4

    if raw is None or (isinstance(raw, (list,)) and len(raw) == 0):
        # TA-CN 覆盖该域但无数据 → 返回空 DataResult（不继续外部 fallback）
        trace.append("ta_cn_internal(empty)")
        return DataResult(
            data=None,
            security_id=security_id,
            domain=capability.split(".")[0],
            operation=capability.split(".")[1],
            provider="empty",
            fetched_at=ts,
            freshness="empty",
            source_trace=trace,
        )

    trace.append("ta_cn_internal(ok)")
    freshness_label = self._freshness.label(ts, None, capability.split(".")[0], False)
    return DataResult.success(
        data=raw,
        security_id=security_id,
        domain=capability.split(".")[0],
        operation=capability.split(".")[1],
        provider="ta_cn_internal",
        fetched_at=ts,
        source_trace=trace,
        freshness=freshness_label,
    )


def _query_ta_cn(
    self,
    security_id: SecurityId,
    capability: str,
    params: dict,
    trace: list[str],
    ts: datetime,
    force_external: bool,
) -> DataResult:
    """provider="ta_cn_internal" 显式指定时调用。"""
    ...


def _query_external_single(
    self,
    provider_name: str,
    security_id: SecurityId,
    capability: str,
    params: dict,
    trace: list[str],
    ts: datetime,
) -> DataResult:
    """provider="tushare"/"akshare" 显式指定时调用。"""
    ...


def _query_external_chain(
    self,
    security_id: SecurityId,
    capability: str,
    params: dict,
    trace: list[str],
    ts: datetime,
) -> DataResult:
    """Step 4 外部 fallback 链尝试。全部失败 → DataResult.error()。"""
    # 链解析优先级：
    # 1. external_fallback_chains[capability]（构造注入）
    # 2. self._config.fallback_for(capability)（UnifiedDataConfig）
    # 3. self._registry.get_providers(capability) 按注册顺序
    chain_names = self._resolve_external_chain(capability)
    for name in chain_names:
        provider_obj = self._registry.get(name)
        if provider_obj is None:
            trace.append(f"{name}(skipped: not registered)")
            continue
        if not provider_obj.is_available():
            trace.append(f"{name}(skipped: unavailable)")
            continue
        try:
            data = provider_obj.fetch(
                capability.split(".")[0],
                capability.split(".")[1],
                security_id,
                **params,
            )
        except (ProviderError, ProviderUnavailableError) as exc:
            trace.append(f"{name}(error: {exc})")
            continue
        trace.append(f"{name}(ok)")
        freshness = self._freshness.label(ts, None, capability.split(".")[0], False)
        return DataResult.success(
            data=data,
            security_id=security_id,
            domain=capability.split(".")[0],
            operation=capability.split(".")[1],
            provider=name,
            fetched_at=ts,
            source_trace=trace,
            freshness=freshness,
        )

    # 全部失败 → 返回 error，不抛异常
    trace_clean = [t for t in trace if t] if trace else []
    warnings = []
    if all("skipped: unavailable" in t for t in trace_clean):
        warnings.append("all external providers unavailable")
    elif trace_clean:
        warnings.append("all external providers failed")
    return DataResult.error(
        security_id=security_id,
        domain=capability.split(".")[0],
        operation=capability.split(".")[1],
        provider="error",
        error="All providers failed",
        fetched_at=ts,
        source_trace=trace_clean,
    )


def _resolve_external_chain(self, capability: str) -> list[str]:
    """解析外部 fallback chain。"""
    # 1. 显式注入的 external_fallback_chains
    chain = self._external_chains.get(capability)
    if chain:
        return list(chain)
    # 2. UnifiedDataConfig fallback_for
    chain = self._config.fallback_for(capability)
    if chain:
        return list(chain)
    # 3. Registry order
    providers = self._registry.get_providers(capability)
    return [p.name for p in providers]
```

#### 3.3.3 `_adapter_kwargs` 参数映射

```python
# DataRouter 内部方法
def _adapter_kwargs(self, capability: str, params: dict) -> dict:
    """从 capability + params 构造 adapter 方法所需 kwargs。

    TA-CN adapter 方法接收 symbol/market/limit/start_date 等参数。
    本方法将 SecurityId.symbol 传给 symbol 参数，
    并从 params 透传 start_date/end_date/limit/report_period 等。
    """
    kwargs: dict = {}
    # 提取 TA-CN adapter 支持的关键字
    for key in ("start_date", "end_date", "limit", "report_period", "market", "status"):
        if key in params:
            kwargs[key] = params[key]
    return kwargs
```

#### 3.3.4 ProviderRegistry 增强版签名

```python
# 文件: skills/data/unified_data/registry.py（已有 171 行）
# 在 __init__ 末尾追加新属性，在类尾部追加两个新方法。不修改已有方法签名。

class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, DataProvider] = {}
        self._by_capability: dict[str, list[DataProvider]] = {}
        self._external_fallback_chains: dict[str, list[str]] = {}   # [1B-A 新增]

    # ... 已有方法保持不变 ...

    # ── 1B-A 新增方法 ──
    def set_external_fallback_chains(
        self, chains: Mapping[str, Sequence[str]]
    ) -> None:
        """注入 external_fallback_chains 配置。"""
        self._external_fallback_chains = {k: list(v) for k, v in chains.items()}

    def get_external_fallback_chain(self, capability: str) -> list[str]:
        """返回该 capability 的外部 fallback chain。"""
        return list(self._external_fallback_chains.get(capability, []))
```

#### 3.3.5 BaseExternalProvider（外部 Provider 公共基类）

```python
# 文件: skills/data/unified_data/providers/base_external.py

from abc import abstractmethod
from .rate_limiter import RateLimiter, with_retry

class BaseExternalProvider(DataProvider):
    """外部 API Provider 公共基类。

    提供：
    - _check_capability() — 声明校验
    - _to_canonical() — canonical 转换 hook（1B-A stub：直接返回）
    - 限流装饰器（子类可覆盖 rate_limiter 配置）
    """

    def __init__(self, rate_limit_rpm: int = 200, retry_max: int = 3):
        super().__init__()
        self._rate_limiter = RateLimiter(max_per_minute=rate_limit_rpm)
        self._retry_max = retry_max

    def _check_capability(self, domain: str, operation: str) -> str:
        """校验 capability 并返回 canonical 字符串。同 DataProvider._assert_capability。"""
        return self._assert_capability(domain, operation)

    def _to_canonical(self, raw_df: "pd.DataFrame", capability: str) -> "pd.DataFrame":
        """1B-A stub：直接返回 raw_df。后续段可覆盖为真实转换。"""
        return raw_df
```

#### 3.3.6 TushareProvider / AKShareProvider

```python
# 文件: skills/data/unified_data/providers/tushare.py

class TushareProvider(BaseExternalProvider):
    name = "tushare"
    capabilities = frozenset({
        "market_data.kline_daily", "market_data.kline_weekly",
        "market_data.realtime_quote", "market_data.adj_factor",
        "financial.income_statement", "financial.balance_sheet",
        "financial.cash_flow", "valuation.daily_basic",
        "calendar.trading_days", "calendar.is_trading_day",
        "metadata.stock_list", "metadata.index_members",
        "news.stock_news",
    })
    markets = frozenset({Market.CN})

    def is_available(self) -> bool:
        """检查 TUSHARE_TOKEN 环境变量存在 + tushare 可 import。"""
        import os
        if not os.environ.get("TUSHARE_TOKEN", "").strip():
            return False
        try:
            import tushare  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch(self, domain, operation, security_id, **params) -> "pd.DataFrame":
        capability = self._check_capability(domain, operation)
        # 1B-A stub：返回预定义的 stub DataFrame
        return _stub_dataframe_for(capability)

# 文件: skills/data/unified_data/providers/akshare.py

class AKShareProvider(BaseExternalProvider):
    name = "akshare"
    capabilities = frozenset({
        "market_data.kline_daily", "market_data.kline_weekly",
        "market_data.realtime_quote", "valuation.daily_basic",
        "calendar.trading_days", "calendar.is_trading_day",
        "metadata.stock_list",
    })
    markets = frozenset({Market.CN})

    def is_available(self) -> bool:
        try:
            import akshare  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch(self, domain, operation, security_id, **params) -> "pd.DataFrame":
        capability = self._check_capability(domain, operation)
        return _stub_dataframe_for(capability)
```

#### 3.3.7 stub DataFrame 数据形状

```python
# skills/data/unified_data/providers/__init__.py 内部定义

import pandas as pd

_STUB_COLUMNS: dict[str, list[str]] = {
    "market_data.kline_daily":     ["trade_date", "open", "high", "low", "close", "volume", "amount"],
    "market_data.kline_weekly":    ["trade_date", "open", "high", "low", "close", "volume", "amount"],
    "market_data.realtime_quote":  ["symbol", "name", "price", "change", "pct_chg", "volume", "amount"],
    "market_data.adj_factor":      ["trade_date", "adj_factor"],
    "financial.income_statement":  ["report_period", "total_revenue", "operating_profit", "net_profit"],
    "financial.balance_sheet":     ["report_period", "total_assets", "total_liabilities", "shareholder_equity"],
    "financial.cash_flow":         ["report_period", "operating_cf", "investing_cf", "financing_cf"],
    "valuation.daily_basic":       ["trade_date", "pe", "pe_ttm", "pb", "ps", "ps_ttm", "total_mv"],
    "calendar.trading_days":       ["cal_date", "is_open", "pretrade_date"],
    "calendar.is_trading_day":     ["cal_date", "is_open"],
    "metadata.stock_list":         ["symbol", "name", "area", "industry", "market", "list_date"],
    "metadata.index_members":      ["index_code", "index_name", "con_code", "con_name"],
    "news.stock_news":             ["title", "content", "source", "publish_time"],
}

def _stub_dataframe_for(capability: str) -> pd.DataFrame:
    """返回 1B-A stub DataFrame（包含正确的列名，1-3 行空数据）。"""
    columns = _STUB_COLUMNS.get(capability, ["data"])
    return pd.DataFrame(columns=columns)
```

#### 3.3.8 FreshnessPolicy

```python
# 文件: skills/data/unified_data/freshness.py

from datetime import datetime, timezone
from typing import Mapping
from ..models import FreshnessLabel

class FreshnessPolicy:
    DEFAULT_TTLS: dict[str, int] = {
        "market_data": 21600,    # 6h
        "financial": 86400,      # 24h
        "valuation": 43200,      # 12h
        "calendar": 604800,      # 7d
        "metadata": 604800,      # 7d
        "news": 3600,            # 1h
    }

    def __init__(self, ttl_overrides: Mapping[str, int] | None = None) -> None:
        self._ttls = dict(self.DEFAULT_TTLS)
        if ttl_overrides:
            self._ttls.update(ttl_overrides)

    def get_ttl(self, domain: str) -> int:
        return self._ttls.get(domain, 3600)

    def label(
        self,
        fetched_at: datetime,
        data_date: str | None,
        domain: str,
        from_cache: bool,
    ) -> FreshnessLabel:
        if data_date is None:
            return "empty"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        age = (now - fetched_at).total_seconds()

        if data_date is None:
            return "empty"
        if from_cache:
            ttl = self.get_ttl(domain)
            if age > ttl:
                return "stale"
            return "cached"
        if age < 60:
            return "realtime"
        if age < 900:  # 15 min
            return "delayed"
        return "delayed"
```

#### 3.3.9 UnifiedDataClient 增强版签名

```python
# 文件: skills/data/unified_data/client.py（修改，315 行 → 约 330 行）

class UnifiedDataClient:
    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        config: UnifiedDataConfig | None = None,
        *,
        ta_cn_adapter: TA_CNMongoAdapter | None = None,
        freshness: FreshnessPolicy | None = None,           # [1B-A 新增]
        external_fallback_chains: dict[str, list[str]] | None = None,  # [1B-A 新增]
    ) -> None:
        """... [已有逻辑保留] ...
        1B-A 增强：将 ta_cn_adapter / freshness / external_fallback_chains 传入 Router。
        """
        self._registry = registry if registry is not None else ProviderRegistry()
        self._config = config or UnifiedDataConfig.minimal()
        self._ta_cn_adapter = ta_cn_adapter
        # [1B-A 修改] Router 构造传入新参数
        self._router = DataRouter(
            self._registry,
            self._config,
            ta_cn_adapter=ta_cn_adapter,
            freshness=freshness,
            external_fallback_chains=external_fallback_chains,
        )
        # ... [14 个域入口方法保持不变] ...

    def query(
        self,
        domain: str,
        operation: str,
        security_id: SecurityId,
        *,
        provider: str | None = None,
        force_refresh: bool = False,                        # [1B-A 新增]
        market: Market | str | None = None,
        params: Mapping[str, Any] | None = None,
        fetched_at: datetime | None = None,
    ) -> DataResult:
        return self._router.query(
            domain, operation, security_id,
            provider=provider,
            force_refresh=force_refresh,
            market=market,
            params=params,
            fetched_at=fetched_at,
        )
```

### 3.4 持久化设计

**无持久化需求。**

1B-A 阶段全部组件运行在内存中：
- DataRouter / ProviderRegistry / FreshnessPolicy 纯内存对象。
- TushareProvider / AKShareProvider 的 `fetch()` 返回 stub DataFrame，不读写磁盘/Mongo。
- TA-CN adapter 只读复用（Phase 1A 已交付），不新增写入。
- external_fallback_chains 由构造参数注入，不落盘。

### 3.5 配置与安全边界

#### 3.5.1 配置键与环境变量

| 配置入口 | 来源 | 说明 |
|---|---|---|
| `external_fallback_chains` | DataRouter 构造参数或 ProviderRegistry | capability → 有序 provider name 列表；默认 None（回退 registry order） |
| `TUSHARE_TOKEN` | 环境变量 | TushareProvider.is_available() 只检查存在性；不读取/打印值 |
| `FreshnessPolicy.ttl_overrides` | 构造参数 | 可选 TTL 覆盖 dict |
| `RateLimiter.max_per_minute` | TushareProvider 构造（默认 200） | 可配置限流频率 |

#### 3.5.2 安全约束（P-10 落实）

- `is_available()` 只检查 `os.environ.get("TUSHARE_TOKEN", "").strip() != ""`，不记录/打印值。
- stub DataFrame 不含真实凭据。
- `source_trace` 不记录 token 或 API 响应内容，只记录 provider_name + outcome。
- 配置文件中凭据用环境变量名引用，不内联值。

### 3.6 实现顺序

按依赖关系分三步，每步可独立测试：

| 步骤 | 组件 | 依赖 | 预估时间 |
|---|---|---|---|
| **Step 1：纯逻辑** | ① FreshnessPolicy；② ProviderRegistry 增强（两个新方法）；③ 测试 conftest 新增 FakeTA_CNAdapter | 无外部依赖 | 30 min |
| **Step 2：Router 增强** | ① `_TA_CN_CAPABILITY_METHOD_MAP` 常量；② DataRouter 四步编排；③ `_adapter_kwargs` 参数映射 | Step 1 | 45 min |
| **Step 3：Provider 框架** | ① `rate_limiter.py`；② `base_external.py`；③ TushareProvider / AKShareProvider；④ `_stub_dataframe_for` | 无依赖 | 45 min |
| **Step 4：Client 接入** | ① `UnifiedDataClient.__init__` 修改；② `query()` 加 `force_refresh`；③ `__init__.py` 导出 | Step 1+2 | 15 min |
| **Step 5：测试** | 全部测试文件 | Step 1-4 | 60 min |

---

## 4. 测试策略

### 4.1 测试基础设施增强

`conftest.py` 新增：

```python
# tests/data/unified_data/conftest.py（追加）

class FakeTA_CNAdapter:
    """Fake TA-CN adapter 用于 internal-first 路由测试。

    行为 knobs:
    - collections: dict[str, list[dict]] — 模拟 8 个集合数据
    - raise_on_query: Exception | None — 模拟 adapter 异常
    - covered_capabilities: set[str] — 覆盖的 capability set（默认 = DataRouter._TA_CN_CAPABILITY_METHOD_MAP.keys()）
    """

    def __init__(self, *, collections=None, raise_on_query=None, covered_capabilities=None):
        self._collections = collections or {}
        self._raise = raise_on_query
        self.call_log: list[str] = []
        self._covered = covered_capabilities or set(DataRouter._TA_CN_CAPABILITY_METHOD_MAP.keys())

    def _resolve(self, capability: str) -> str | None:
        """返回 adapter 方法名，或 None（不覆盖）。"""
        return DataRouter._TA_CN_CAPABILITY_METHOD_MAP.get(capability)

    def get_daily_bars(self, symbol, start_date=None, end_date=None, limit=120):
        self.call_log.append("get_daily_bars")
        return self._maybe_raise_or_return("stock_daily_quotes", symbol)

    def get_realtime_quotes(self, symbol):
        self.call_log.append("get_realtime_quotes")
        return self._maybe_raise_or_return("market_quotes", symbol, single=True)

    def get_financials(self, symbol, report_period=None):
        self.call_log.append("get_financials")
        return self._maybe_raise_or_return("stock_financial_data", symbol, single=True)

    def get_stock_list(self, market="CN", status="L", limit=0):
        self.call_log.append("get_stock_list")
        return self._maybe_raise_or_return("stock_basic_info")

    def get_stock_info(self, symbol, market="CN"):
        self.call_log.append("get_stock_info")
        return self._maybe_raise_or_return("stock_basic_info", symbol, single=True)

    def get_index_list(self, market="CN"):
        self.call_log.append("get_index_list")
        return self._maybe_raise_or_return("index_basic_info")

    def get_index_info(self, symbol):
        self.call_log.append("get_index_info")
        return self._maybe_raise_or_return("index_basic_info", symbol, single=True)

    def get_index_daily_bars(self, symbol=None, sector_code=None, start_date=None, end_date=None, limit=120):
        self.call_log.append("get_index_daily_bars")
        return self._maybe_raise_or_return("index_daily_quotes")

    def get_news(self, symbol, limit=20):
        self.call_log.append("get_news")
        return self._maybe_raise_or_return("stock_news")

    def _maybe_raise_or_return(self, coll_name, symbol=None, *, single=False):
        if self._raise:
            raise self._raise
        docs = self._collections.get(coll_name, [])
        if symbol:
            docs = [d for d in docs if d.get("symbol") == symbol]
        if single:
            return docs[0] if docs else None
        return list(docs)


@pytest.fixture
def fake_ta_cn_adapter():
    """返回空数据的 FakeTA_CNAdapter。"""
    return FakeTA_CNAdapter(collections={})


@pytest.fixture
def fake_ta_cn_with_kline(cn_maotai):
    """返回有 K 线数据的 FakeTA_CNAdapter。"""
    return FakeTA_CNAdapter(collections={
        "stock_daily_quotes": [
            {"symbol": cn_maotai.symbol, "trade_date": "20260713", "open": 1600, "close": 1620}
        ]
    })
```

### 4.2 单元测试矩阵（36 条 UT）

#### FreshnessPolicy（8 条，文件：`tests/data/unified_data/test_freshness_policy.py`）

| 编号 | 测试方法 | 覆盖 SPEC 编号 | 断言 |
|---|---|---|---|
| test_get_ttl_known | `get_ttl("market_data")` | FP-101 | `== 21600` |
| test_get_ttl_unknown | `get_ttl("unknown")` | FP-101 | `== 3600` |
| test_label_realtime | fetched_at=now-30s, from_cache=False | FP-102 | `== "realtime"` |
| test_label_delayed | fetched_at=now-5min, from_cache=False | FP-103 | `== "delayed"` |
| test_label_empty | data_date=None | FP-106 | `== "empty"` |
| test_label_cached | from_cache=True, 未超 TTL | FP-104 | `== "cached"` |
| test_label_stale | from_cache=True, 已超 TTL | FP-105 | `== "stale"` |
| test_ttl_override | `FreshnessPolicy({"market_data": 100})` | FP-107 | `get_ttl("market_data") == 100` |

#### Provider（13 条，文件：`tests/data/unified_data/test_providers.py`）

| 编号 | 测试方法 | 覆盖 SPEC | 断言 |
|---|---|---|---|
| test_tushare_name | `TushareProvider().name` | TP-101 | `== "tushare"` |
| test_tushare_capabilities | `TushareProvider().capabilities` | TP-102 | 13 条 |
| test_tushare_markets | `TushareProvider().markets` | TP-103 | `== {Market.CN}` |
| test_tushare_available_token | monkeypatch `TUSHARE_TOKEN="fake"` | TP-104 | `== True` |
| test_tushare_unavailable_no_token | monkeypatch 删除 `TUSHARE_TOKEN` | TP-104 | `== False` |
| test_tushare_fetch_stub | fetch `kline_daily` | TP-105 | 返回非空 DataFrame，含正确列名 |
| test_tushare_fetch_unsupported | fetch 未声明 capability | TP-106 | raise `UnsupportedCapabilityError` |
| test_akshare_name | `AKShareProvider().name` | AK-101 | `== "akshare"` |
| test_akshare_capabilities | `AKShareProvider().capabilities` | AK-102 | 7 条 |
| test_akshare_markets | `AKShareProvider().markets` | AK-103 | `== {Market.CN}` |
| test_akshare_available_import | mock import 成功 | AK-104 | `== True` |
| test_akshare_unavailable_import | mock import 失败 | AK-104 | `== False` |
| test_akshare_fetch_stub | fetch `kline_daily` | AK-105 | 返回非空 DataFrame，含正确列名 |

#### DataRouter internal-first（12 条 UT + 4 条 IT，文件：`tests/data/unified_data/test_router_internal_first.py`）

| 编号 | 测试方法 | 覆盖 SPEC | 关键断言 |
|---|---|---|---|
| test_ta_cn_hit | TA-CN 有数据，无外部 provider | DR-101 | `provider=="ta_cn_internal"`，call_log 仅 TA-CN |
| test_ta_cn_not_covered_external_ok | capability=`valuation.daily_basic`，FAKE external provider | DR-101 | `provider=="tushare"`，call_log 无 TA-CN |
| test_ta_cn_exception_fallback | FakeTA_CNAdapter raise Exception + external ok | DR-101 | `provider=="tushare"`，warnings 含 "ta_cn_internal" |
| test_force_refresh_skip_ta_cn | kline_daily + force_refresh=True | DR-102 | `provider=="tushare"`，call_log 无 TA-CN |
| test_provider_tushare_skip_ta_cn | `provider="tushare"` | DR-103 | `provider=="tushare"`，call_log 无 TA-CN |
| test_provider_ta_cn_internal | `provider="ta_cn_internal"` | DR-104 | `provider=="ta_cn_internal"` |
| test_ta_cn_none_degraded | `ta_cn_adapter=None` + external ok | DR-105 | `provider=="tushare"`（Phase 0 兼容） |
| test_all_external_unavailable | FakeProvider available=False x2 | DR-106 | `DataResult.error`, `provider=="error"` |
| test_all_external_fetch_fail | FakeProvider raise x2 | DR-107 | `DataResult.error`, source_trace 含 2 个 error |
| test_no_provider_registered | 空 registry | DR-108 | `DataResult.error`, source_trace==[] |
| test_source_trace_full | TA-CN exception + tushare fail + akshare ok | DR-109 | trace 3 条完整 |
| test_warnings_fallback | tushare unavailable + akshare ok | DR-110 | `warnings == ["all external providers unavailable"]` |
| **IT-001** | client.query(`kline_daily`) → TA-CN 命中 | IT-001 | 端到端，不调 external |
| **IT-002** | client.query(`valuation.daily_basic`) → TA-CN 不覆盖 → akshare | IT-002 | 端到端 |
| **IT-003** | client.query(`kline_daily`, `force_refresh=True`) → 跳过 TA-CN | IT-003 | 端到端 |
| **IT-004** | client.query(`kline_daily`, `provider="tushare"`) | IT-004 | 端到端 |

### 4.3 回归测试

| 测试文件 | 预期结果 | 备注 |
|---|---|---|
| `tests/data/unified_data/test_router.py` | 22 条需调整 | `AllProvidersFailedError` 断言更新为 `DataResult.error` / `DataResult.succeeded==False` |
| `tests/data/unified_data/test_client_phase1a.py` | 25 条全部通过 | 14 个域入口方法不变 |
| `tests/data/unified_data/test_provider_support.py` | 全部通过 | Phase 0 provider 基础测试不变 |

### 4.4 回归测试更新清单（test_router.py）

以下 7 个测试函数断言 `pytest.raises(AllProvidersFailedError)`，需更新为断言 `DataResult.error`：

| 行号（约） | 测试方法 | 新断言 |
|---|---|---|
| 260 | `test_all_providers_fail_raises_with_attempts` | `result = router.query(...); assert result.provider == "error"; assert result.data is None` |
| 270 | `test_registry_empty_raises` | `result = router.query(...); assert result.provider == "error"; assert result.source_trace == []` |
| 291 | `test_all_skipped_raises` | `result = router.query(...); assert result.provider == "error"` |
| 320 | `test_forced_provider_not_registered_raises` | `result = router.query(...); assert result.provider == "error"` |
| 336 | `test_forced_provider_wrong_capability_raises` | `result = router.query(...); assert result.provider == "error"` |
| 442 | `test_client_propagates_all_providers_failed` | `result = client.query(...); assert result.provider == "error"` |
| — | `test_*_raises` 内任何 `pytest.raises(AllProvidersFailedError)` | 更新 |

---

## 5. 风险、降级与回滚

| 风险 | 等级 | 应对 | 降级/回滚 |
|---|---|---|---|
| DataRouter 行为变更破坏 Phase 0 测试 | 中 | §4.4 明确更新清单；Implement 同步修改 | 回退到 Phase 0 Router（简单 revert） |
| TA-CN「覆盖但空」vs「不覆盖」区分错误 | 高 | `_TA_CN_CAPABILITY_METHOD_MAP` 硬编码 + `_TA_CN_NOT_COVERED` frozenset；UT 全覆盖 | 修正常量即可，不需重构 |
| fake provider 与真实 provider 行为偏差 | 中 | 1B-A 明确标注「框架 + fake 验证」；后续段补 `@pytest.mark.network` | — |
| `force_refresh` 漏透传 | 低 | IT-003 端到端覆盖 | — |
| `source_trace` 遗漏路径 | 中 | UT-DR-010 全路径覆盖 | — |
| `provider="ta_cn_internal"` 返回空时的语义歧义 | 中 | SPEC §4.3 明确：覆盖但空 → 返回 empty DataResult，不继续外部 | 如需变更，改 `_try_ta_cn` 返回值逻辑 |

---

## 6. B 阶段接续接口

1B-B 需要接入时，以下接口已预留：

| 接口 | 1B-A 状态 | 1B-B 接入方式 |
|---|---|---|
| `DataRouter(local_mongo_adapter=...)` | 构造参数已定义，默认 None，Step 2 跳过 | 传入 `LocalMongoAdapter` 实例，Step 2 激活 |
| `DataRouter(cache_manager=...)` | 构造参数已定义，默认 None，Step 3 跳过 | 传入 `CacheManager` 实例，Step 3 激活 |
| `FreshnessPolicy.label(..., from_cache=True)` | `cached`/`stale` 逻辑已实现，当前不触发 | CacheManager 写入后自动激活 |
| `BaseExternalProvider._to_canonical()` | stub 直接返回，hook 已就位 | 覆盖实现真实 `pd.DataFrame → canonical object` 转换 |
| `_TA_CN_CAPABILITY_METHOD_MAP` | 硬编码常量 | 1B-B 可考虑迁移到配置文件 |
| `external_fallback_chains` | 构造参数注入，1B-A 硬编码默认 None | 1B-B 引入 YAML 配置加载 |

---

## 7. 明确禁止与零副作用声明

### 7.1 不改动文件（不变）

| 文件 | 理由 |
|---|---|
| `skills/data/unified_data/models/__init__.py` | Phase 0 公共契约不变 |
| `skills/data/unified_data/models/domain/**` | canonical domain objects 不变 |
| `skills/data/unified_data/services/**` | Phase 1A 域服务不变 |
| `skills/data/unified_data/adapters/ta_cn_mongo_adapter.py` | TA-CN 只读复用 |
| `skills/data/unified_data/provider.py` | DataProvider ABC 不变 |
| `skills/data/unified_data/config.py` | UnifiedDataConfig 不变 |
| `skills/data/unified_data/exceptions.py` | `AllProvidersFailedError` 保留但 Router 不再为主出口抛；已有代码可能依赖此异常类，不删除 |
| `skills/apps/TradingAgents-CN/**` | TA-CN 子项目 |
| `skills/research/daily_stock_analysis/**` | DSA |
| 生产 MongoDB 集合 DDL/索引/schema | 无 Mongo 写入 |
| cron / systemd / 推送配置 | 不碰调度 |

### 7.2 零副作用声明

- 不创建任何 MongoDB 集合、索引、schema validator。
- 不做真实 Mongo 写入。
- 不做真实 Tushare/AKShare API 调用。
- 不修改 Phase 1A 14 个域入口方法。
- 不新增 pip 依赖（`tushare`/`akshare` 的 import 用 try/except 包裹，安装为可选）。
- 不修改 RFC/SPEC/Design 文档模板。

---

## 8. 参考资料

- RFC-03-008：`docs/rfc/03_data/RFC-03-008-unified-data-phase-1b-query-plane.md`
- SPEC-03-008：`docs/spec/03_data/SPEC-03-008-unified-data-phase-1b-query-plane.md`
- SPEC-03-007：`docs/spec/03_data/SPEC-03-007-unified-data-layer.md`
- DESIGN-03-007：`docs/design/03_data/DESIGN-03-007-unified-data-layer.md`
- 现有代码：
  - `skills/data/unified_data/router.py`（238 行，Phase 0）
  - `skills/data/unified_data/registry.py`（171 行，Phase 0）
  - `skills/data/unified_data/client.py`（315 行，Phase 0 + 1A）
  - `skills/data/unified_data/provider.py`（121 行，DataProvider ABC）
  - `skills/data/unified_data/adapters/ta_cn_mongo_adapter.py`（380 行，11 个读方法）
  - `tests/data/unified_data/conftest.py`（150 行）
  - `tests/data/unified_data/fixtures/__init__.py`（163 行，FakeDatabase 等）
  - `tests/data/unified_data/test_router.py`（449 行，22 个测试函数）
