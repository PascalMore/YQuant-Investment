---
name: unified_data
description: YQuant 全局统一数据访问层（Phase 0 骨架 + Phase 1A TA-CN 只读适配器已交付）。触发场景：新建或修改 unified_data 模块入口（SecurityId / Market / DataResult / Capability）、消费方需要注册/路由 DataProvider，或需要从 fallback 链返回 DataResult；以及 Phase 1B+ 接入 Tushare / AKShare 前的接口澄清。本 SKILL.md 覆盖 Phase 0 骨架与 Phase 1A TA-CN 只读适配器已交付的公共 API，不包含 Phase 1B/1C（External Provider / CacheManager / FreshnessPolicy）及后续 Phase。DSA 不是运行时数据源，不实现 DSA adapter。
version: 0.2.0
platforms: [linux, macos, windows]
environments: [cli, repo, kanban]
metadata:
  hermes:
    tags: [data, unified_data, provider, fallback, phase-0, phase-1a]
    related_skills: [yquant-ai-coding-pipeline, sanity-check, data-pipeline]
---

# unified_data

YQuant Unified Data Layer 的入口说明（Phase 0 骨架 + Phase 1A TA-CN 只读适配器已交付）。来源 RFC-03-007 / SPEC-03-007 / DESIGN-03-007。

> **架构基线（Pascal 确认，2026-07-14 / V0.2 同步）**：Unified Data 与 TA-CN 共用同一物理 MongoDB `tradingagents`，依赖**集合命名空间前缀**（TA-CN 无前缀 / `03_data_ud_*` 物化 / `03_data_ud_cache_*` QueryCache）实现 ownership，不依赖物理库隔离。权威读取路径为 **internal-first**：TA-CN 既有 → UD 物化 → Query Cache → 外部 Provider；外部刷新失败不阻断内部已有数据读取。DSA 仅作为分析/参考上下文出现，不实现任何 DSA adapter，不出现在 `external_fallback_chains` 中。

## 模块定位

`skills/data/unified_data/` 是 YQuant 的全局统一数据访问层（来自 RFC §1）：

- 向上服务于 stock framework、TA-CN、DSA、Argus、portfolio、risk、reports、strategies 等所有消费方。
- 向下通过 `DataProvider` 抽象适配 Tushare / AKShare / BaoStock / yfinance 等多源。
- 定位是**读优先**：查询走本层，ETL 写入仍走 `data-pipeline`，互不重叠。

## Phase 0 公共 API

下列 11 个符号由 `skills/data/unified_data/__init__.py` 导出，是 Phase 0 的全部公共表面。

### 值对象与枚举（`models.py`）

- `SecurityId(market, symbol)` — `frozen=True, slots=True` 不可变值对象。`canonical` 形如 `"CN:600519"`。
  - 工厂方法：`from_wind_code("600519.SH")` / `from_tushare_code("600519.SH")` / `from_full_symbol("000001.SZ")` / `from_numeric("600519", market="CN")`。
  - 转换方法：`to_wind_code()` / `to_tushare_code()` / `to_full_symbol()`，不支持的市场返回 `None`。
  - A 股后缀用 `range()` 前缀集，规避 Python 3.12 leading-zero literal 问题。
- `Market(str, Enum)` — `CN` / `HK` / `US` / `CRYPTO` / `INDEX` / `FUND`。
- `Capability(domain, operation)` — 由 `domain.operation` 组成；提供 `from_string("market_data.kline_daily")` 与 `.name` 属性。
- `DataResult` — 标准返回结构。工厂：
  - `DataResult.success(data, security_id, domain, operation, provider, fetched_at, source_trace=..., warnings=..., **kwargs)`。**Phase 0 默认 `freshness="delayed"`**，空 payload 自动转为 `freshness="empty"` 且 `provider="empty"`（Phase 1 由 FreshnessPolicy 覆盖）。
  - `DataResult.error(security_id, domain, operation, provider, error, fetched_at=None, source_trace=None)`。`provider` 记为 `"error"`，原始 provider 名保留在 `source_trace`。
  - `to_dict()` — Phase 0 不做序列化校验，直接返回 `{**self.__dict__}`；不可序列化场景属 Phase 1（`SerializationError` 由 CacheManager 写入时处理）。
  - `succeeded` / `is_empty` 提供空载分支判定。

### 抽象与组件

- `DataProvider(ABC)` — `name` / `capabilities` / `markets` / `is_available()` / `fetch(domain, operation, security_id, **params)` 抽象方法；自带 `supports(capability, market)` 辅助与 `_assert_capability()` 守卫。
- `ProviderRegistry` — 内存注册：`register(provider)` / `unregister(name)` / `clear()`；查询：`get(name)` / `list_providers()` / `list_provider_names()` / `list_capabilities()` / `get_providers(capability, market=None)` / `has_capability(capability, market=None)`。重名注册抛 `ValueError`；未知 capability / market 返回空列表，不抛异常。
- `DataRouter(registry, config=None)` — 核心入口：`query(domain, operation, security_id, *, provider=None, market=None, params=None, fetched_at=None) → DataResult`。按 capability 解析 fallback 链（`UnifiedDataConfig.capability_fallback_overrides` → `default_fallback_chain` → 注册顺序），跳过 `not registered` / capability-market mismatch / `is_available()=False`；逐 provider 捕获 `UnsupportedCapabilityError` / `ProviderUnavailableError` / `ProviderError`，最终成功返回 `DataResult.success(provider=<name>, source_trace=[...])`，全部失败抛 `AllProvidersFailedError(capability, attempts)`。
- `UnifiedDataClient(registry=None, config=None)` — 消费方 facade，薄包装：`query(...)` 转发到 router；提供 `register_provider(provider)` / `with_providers(providers, config=None)` 工厂；`registry` / `config` / `router` 三个 property。
- `UnifiedDataConfig` — `frozen=True, slots=True` dataclass：`default_fallback_chain: tuple[str, ...]` / `capability_fallback_overrides: Mapping[str, tuple[str, ...]]` / `consumer: str = "unified_data"`。`fallback_for(capability)` 优先取 override，否则返回 default。`UnifiedDataConfig.minimal()` 给出安全默认。

### 异常体系（`exceptions.py`，共 6 类）

- `UnifiedDataError` — 全部 unified_data 异常的基类。
- `InvalidSecurityIdError(UnifiedDataError, ValueError)` — SecurityId 构造失败；同时继承 `ValueError`，保留 idiomatic `except ValueError` 语义。
- `UnsupportedCapabilityError(UnifiedDataError)` — provider 收到未声明 capability。
- `ProviderUnavailableError(UnifiedDataError)` — provider 当前不可用（token 缺失 / 依赖未装 / 网络不通）。
- `ProviderError(UnifiedDataError)` — provider 内部错误。
- `AllProvidersFailedError(UnifiedDataError)` — fallback 链全部失败。携带 `capability` 与 `attempts: list[(provider_name, err)]`，自动渲染 `message`。

## Phase 0 Import 示例

```python
from skills.data.unified_data import (
    SecurityId,
    Market,
    DataResult,
    Capability,
    DataProvider,
    ProviderRegistry,
    DataRouter,
    UnifiedDataClient,
    UnifiedDataConfig,
)

sid = SecurityId(market="CN", symbol="600519")
assert sid.canonical == "CN:600519"

client = UnifiedDataClient.with_providers(
    providers=[...],  # 真实 provider 属 Phase 1
    config=UnifiedDataConfig.minimal(),
)
```

## Phase 0 排除项（明确不在此 Phase）

下列能力在 RFC/SPEC 中规划，但 Phase 0 故意未实现，**不要在本 Phase 引入**：

1. MongoDB 缓存 / `CacheManager`（Phase 1+，集合前缀 `03_data_ud_cache_*`）。
2. `FreshnessPolicy` / TTL 策略（Phase 1；当前 `DataResult.success` 默认 `freshness="delayed"` 由代码硬编码，Phase 1 由策略覆盖）。
3. 真实 provider adapter（Tushare / AKShare / BaoStock / yfinance）。TA-CN MongoDB 只读 adapter 已在 Phase 1A 交付；其余 provider adapter 属 Phase 1B+。**DSA adapter 不在此列**：DSA 不是运行时数据源，不实现任何 DSA SQLite / `StockDaily` adapter。
4. `QualityScorer` / `AuditLogger` / `03_data_ud_query_audit` 写入。
5. Provider 优先级 / 健康检测 / 后台刷新 / Rate limiter 配置（`UnifiedDataConfig` 仅含 `default_fallback_chain` + `capability_fallback_overrides`，无优先级字段）。
6. domain canonical objects（`market_data` / `financial` / `valuation` / `flow` / `sector` / `sentiment` / `dragon_tiger` / `chip` / `news` / `calendar` / `metadata`）—— `DataResult.data` 在 Phase 0 为任意 `Any`，由消费方自行处理。

## 后续 Phase 路线图

Phase 0-7 共 8 个编号阶段（Phase 0 为骨架，Phase 1-7 为业务能力阶段；Phase 1 细分为 1A/1B/1C）。详见 `docs/design/03_data/DESIGN-03-007-unified-data-layer.md` §12：

- Phase 1A ✅ 已交付 — TA-CN read-only adapter for core A-share + index/sector data（覆盖 8 个 TA-CN MongoDB 只读集合：`stock_basic_info` / `market_quotes` / `stock_daily_quotes` / `stock_financial_data` / `stock_news` / `index_basic_info` / `index_daily_quotes` / `stock_sector_info`）+ canonical objects（`StockInfo` / `RealtimeQuote` / `DailyBar` / `FinancialStatement` / `NewsItem` / `IndexInfo` / `IndexDailyBar` / `SectorClassification`）+ domain services + `UnifiedDataClient` facade。
- Phase 1B — External Provider（Tushare / AKShare）+ CacheManager + FreshnessPolicy + LocalMongoAdapter（internal-first 读取路径）。不实现 DSA SQLite adapter（DSA 不是运行时数据源）。
- Phase 1C — 端到端验收 + 测试补齐。
- Phase 2 — Provider Registry 增强 + QualityScorer + AuditLogger。
- Phase 3 — `03_data_ud_*` 持久化集合扩展（板块 / 情绪 / 资金流 / 技术指标）。
- Phase 4 — 龙虎榜 / 筹码 / 热门股票。
- Phase 5 — task_center 集成。
- Phase 6 — Stock Framework 集成。
- Phase 7 — TA-CN / DSA 渐进迁移规划文档。

## 边界声明（对其它 skill）

- unified_data **不写** `portfolio_position` / `portfolio_trade` / `signal` / `stock_pool` 等生产交易集合。
- unified_data **不依赖** TA-CN / DSA / Argus / data-pipeline / task_center / stock framework 的代码（仅在 Phase 1+ 通过 adapter 复用其 schema）。
- 消费方只能通过 `UnifiedDataClient` / `DataRouter` / `ProviderRegistry` / `DataProvider` 这套统一接口访问，不得 `import tushare` / `import akshare` 等第三方 provider 库——provider 实现属本模块内部职责。

## 验证

```bash
ls -la skills/data/unified_data/SKILL.md
head -20 skills/data/unified_data/SKILL.md                          # 确认 YAML frontmatter
PYTHONPATH=. python -c "from skills.data.unified_data import SecurityId, DataResult, UnifiedDataClient; print(SecurityId(market='CN', symbol='600519').canonical)"  # CN:600519
PYTHONPATH=. pytest tests/data/unified_data -q                      # 当前环境 269 passed
```

历史 Review 已知 MINOR（不影响 Phase 0 Closeout，归属 Phase 1）：F2 `to_dict` 无序列化校验 / F3 `success` 默认 `delayed` / F4 `forced provider` 走 `AllProvidersFailedError` 而非 `ProviderUnavailableError` / F5 缺独立 `test_config.py` / F6 `DataResult.error` 硬编码 `provider="error"`。