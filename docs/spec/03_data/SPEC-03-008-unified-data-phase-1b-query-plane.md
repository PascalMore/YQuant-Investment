# SPEC-03-008: Unified Data Phase 1B-A 查询平面与外部降级

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-14 |
| 最后更新 | 2026-07-14 |
| 来源 RFC | RFC-03-008（Phase 1B-A 查询平面） |
| 关联 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-00-001（全局架构） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-006（provider fallback 设计参考） |
| 关联 Design | DESIGN-03-007（待 T2 Design 阶段产出 Phase 1B-A 章节） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 版本号 | V0.1 |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

---

## 0. 术语对齐与基线锚定

本 SPEC 继承 RFC-03-007 / SPEC-03-007 的全部基线，不重述背景，只锁定 1B-A 阶段必须一致的措辞：

- **internal-first 读取路径** = `TA-CN 既有 → UD 物化 → Query Cache → 外部 Provider`。1B-A 阶段 UD 物化与 Query Cache 层不存在（1B-B 才落地），DataRouter 在编排逻辑中保留这两个 slot，运行时跳过，不报错。
- **external_fallback_chains** 仅含 `["tushare", "akshare"]`。DSA 不出现在任何运行时链路（SPEC-03-007 §0.2 第 4 条不变量）。
- **TA-CN adapter 只读**：Phase 1A 已交付的 `TA_CNMongoAdapter` 11 个读方法不变；1B-A 只在 DataRouter Step 1 调用它，不修改其代码。
- **provider name 约定**：TA-CN 内部源在 `DataResult.provider` 中记为 `"ta_cn_internal"`；外部 provider 记为 `"tushare"` / `"akshare"`；无数据/全失败记为 `"error"`。
- **freshness 标签集合**：`{"realtime", "delayed", "cached", "stale", "empty"}`。1B-A 阶段 `from_cache` 恒为 `False`，因此只产出 `realtime` / `delayed` / `empty` 三种。

### 0.1 与 SPEC-03-007 的关系

本 SPEC 是 SPEC-03-007 的子阶段细化，不替代它：

- SPEC-03-007 定义了 unified_data 全局契约（SecurityId / DataResult / DataProvider / Registry / Router / CacheManager / FreshnessPolicy / 14 个入口方法）。
- 本 SPEC 只对 1B-A 范围内的组件（DataRouter 增强、ProviderRegistry 增强、TushareProvider、AKShareProvider、FreshnessPolicy、UnifiedDataClient.query() 接入）制定可执行契约。
- SPEC-03-007 的 `CacheManager`、`LocalMongoAdapter`、Mongo 持久化集合（`03_data_ud_*` / `03_data_ud_cache_*`）在 1B-A **不实现**，由 1B-B 覆盖。

### 0.2 六项不变量逐条对应（RFC-03-007 §14 / SPEC-03-007 §0.2）

| # | 不变量 | 1B-A SPEC 落点 |
|---|---|---|
| 1 | 共享物理数据库 `tradingagents` | §4.3 DataRouter 注入 TA-CN adapter，读同一物理库；不新增集合 |
| 2 | Internal-First 读取路径 | §4.3 DataRouter.query() 四步编排；Step 2/3 slot 预留但跳过 |
| 3 | DSA 不是运行时数据源 | §4.5 external_fallback_chains 只含 tushare/akshare |
| 4 | Collection Ownership 不可回写 | §7.3 不改动清单：TA-CN 代码 / 无前缀集合只读 |
| 5 | Task Center 先行 | §7.1 Out of Scope：不实现 Task Center 集成 |
| 6 | 三层语义分离 | §4.3 Step 1 只读 TA-CN 无前缀集合；1B-A 不触碰 `03_data_ud_*` / `03_data_ud_cache_*` |

---

## 1. 需求摘要

将 RFC-03-008 的查询平面需求落为可执行契约，核心交付 6 件事：

1. **DataRouter** 从 Phase 0 外部 fallback 版升级为 internal-first 编排版：新增 TA-CN adapter 前置查询、`force_refresh` 参数、`provider` 参数的精确语义。
2. **ProviderRegistry** 增强：新增 `external_fallback_chains` 配置注入（capability → 有序 provider name 列表）、availability 检测保持 per-call `is_available()`。
3. **TushareProvider** 全新实现：capability 声明、`is_available()`（token 存在性 + `tushare` 可 import）、`fetch()` 框架（1B-A 返回 fake/stub DataFrame，不做真实 API 调用）、canonical 转换框架、限流/重试框架。
4. **AKShareProvider** 全新实现：同上，`is_available()` 检查 `akshare` 可 import。
5. **FreshnessPolicy** 全新实现：纯函数 `get_ttl(domain)` + `label(fetched_at, data_date, domain, from_cache)`，无 I/O。
6. **UnifiedDataClient.query()** 接入增强版 Router 的 internal-first 路由 + `provider`/`force_refresh` 参数。

全部组件用 fake/mock/in-memory 验证，不依赖真实 Tushare token、真实 AKShare 网络、真实 Mongo 写入。

---

## 2. 范围

### 2.1 In Scope

- [ ] DataRouter 升级：internal-first 四步编排（Step 1 TA-CN → Step 2/3 占位跳过 → Step 4 外部 fallback），`force_refresh` 与 `provider` 参数语义。
- [ ] ProviderRegistry 增强：`external_fallback_chains` 配置注入接口；chain 解析优先级（per-capability override → default chain → registry order）。
- [ ] TushareProvider：name/capabilities/markets/is_available/fetch 完整框架；限流/重试框架（1B-A stub 调用）。
- [ ] AKShareProvider：同上。
- [ ] FreshnessPolicy：DEFAULT_TTLS 表 + `get_ttl()` + `label()` 纯函数。
- [ ] UnifiedDataClient.query() 接入增强版 Router + 新增 `force_refresh` 参数。
- [ ] DataResult 的 `provider` / `freshness` / `source_trace` / `warnings` 在全部降级路径下正确填充。
- [ ] 全量文件清单（新增 / 修改 / 测试）精确到文件路径。
- [ ] fake/mock 测试矩阵覆盖全部行为契约。

### 2.2 Out of Scope（1B-A 不做）

- [ ] 不实现 LocalMongoAdapter（读 `03_data_ud_*` 物化集合）—— 1B-B。
- [ ] 不实现 CacheManager 的 Mongo 持久化（写 `03_data_ud_cache_*`）—— 1B-B。
- [ ] 不创建任何 MongoDB 集合、索引、schema validator。
- [ ] 不做真实 Mongo 写入；TA-CN adapter 只读复用已在 Phase 1A 交付，不新增。
- [ ] 不做真实 Tushare/AKShare API 调用验收；1B-A provider 的 `fetch()` 返回 fake/stub DataFrame。
- [ ] 不实现 Task Center 集成、批量回填、cron/systemd。
- [ ] 不读取/写入 DSA SQLite / StockDaily；DSA 不进入 `external_fallback_chains`。
- [ ] 不修改 TA-CN 子项目代码（`skills/apps/TradingAgents-CN/**`）。
- [ ] 不修改 Phase 1A 的 14 个域入口方法行为（它们继续直连 TA-CN adapter）。
- [ ] 不修改 RFC/SPEC/Design 文档模板。
- [ ] 不修改 Phase 0 已有的 SecurityId / DataResult / DataProvider ABC / Capability 值对象的公共契约（只新增方法/参数，不改已有签名语义）。

---

## 3. 功能规格

### 3.1 DataRouter（internal-first 编排）

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| DR-101 | internal-first 全路径查询 | `domain, operation, sid, provider=None, force_refresh=False` | TA-CN 命中 → `DataResult(provider="ta_cn_internal")`；TA-CN 未命中 → 外部 fallback | TA-CN 异常 catch-and-log，不阻断，继续 Step 4 |
| DR-102 | force_refresh=True 跳过内部源 | 同上，`force_refresh=True` | 跳过 Step 1（TA-CN），直接 Step 4 外部 fallback | provider 参数仍可覆盖 force_refresh |
| DR-103 | provider 指定外部源 | `provider="tushare"` | 跳过 Step 1/2/3，只走 tushare；不 fallback | tushare 不可用 → `DataResult.error(provider="error")` |
| DR-104 | provider="ta_cn_internal" 显式内部源 | `provider="ta_cn_internal"` | 只走 Step 1 TA-CN，不走外部 fallback | TA-CN 未命中 → `DataResult(provider="empty", freshness="empty")` |
| DR-105 | TA-CN adapter 未注入 | Router 构造时 `ta_cn_adapter=None` | Step 1 自动跳过，退化为 Phase 0 外部 fallback 行为 | 向后兼容 Phase 0 测试 |
| DR-106 | 外部 fallback 全部不可用 | 所有 provider `is_available()=False` | `DataResult.error(provider="error", source_trace=[...])` | 不抛异常给调用方，返回 error DataResult |
| DR-107 | 外部 fallback 全部 fetch 失败 | provider 抛 ProviderError/ProviderUnavailableError | `DataResult.error(...)` + source_trace 记录每个失败 | 同上 |
| DR-108 | 无任何 provider 注册 | registry 为空 | `DataResult.error(provider="error", source_trace=[])` | 同上，不抛 AllProvidersFailedError 给调用方 |
| DR-109 | source_trace 完整记录 | 任意路径 | 每步尝试记为 `"{name}(ok)"` / `"{name}(empty)"` / `"{name}(skipped: ...)"` / `"{name}(error: ...)"` | — |
| DR-110 | warnings 聚合降级告警 | fallback 发生（第一优先 provider 失败，第二成功） | `warnings=["{first} unavailable, fell back to {second}"]` | 无降级时为空列表 |

> **关键语义变更（Phase 0 → 1B-A）**：Phase 0 的 DataRouter 在全部 provider 失败时 **抛出 `AllProvidersFailedError`**。1B-A 增强版改为 **返回 `DataResult.error(...)`**，不再向上抛异常。这是 internal-first 路径的明确要求（RFC-03-008 §5.1.2：「外部刷新失败不阻断已有内部数据读取」）。向后兼容策略见 §11。

### 3.2 ProviderRegistry（external_fallback_chains 增强）

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| RG-101 | 注入 external_fallback_chains | `chains={"market_data.kline_daily": ["tushare","akshare"]}` | Registry 内部存储 chain 映射 | 未知 capability 的 chain 被忽略（不报错） |
| RG-102 | 解析 chain 优先级 | capability string | per-capability override → default chain → registry order | 三级 fallback，空列表表示用 registry order |
| RG-103 | get_providers 保持 Phase 0 行为 | capability, market=None | `[DataProvider]` 按 registration order | 不变 |
| RG-104 | availability 检测 | 无（per-call） | Router 在尝试每个 provider 前调 `provider.is_available()` | 不缓存 availability，每次 query 实时检测 |

### 3.3 TushareProvider

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| TP-101 | name 属性 | 无 | `"tushare"` | — |
| TP-102 | capabilities 声明 | 无 | 13 条 capability set（见 §4.5 表） | — |
| TP-103 | markets 声明 | 无 | `{Market.CN}` | — |
| TP-104 | is_available | 无 | `True` if `TUSHARE_TOKEN` 环境变量存在且非空 AND `tushare` 可 import；否则 `False` | 不泄露 token 值 |
| TP-105 | fetch（1B-A stub） | domain, operation, sid, **params | `pd.DataFrame`（fake/stub 数据） | 1B-A 不做真实 API 调用；返回固定 stub DataFrame |
| TP-106 | fetch 不支持的 capability | 未声明的 capability | raise `UnsupportedCapabilityError` | — |
| TP-107 | canonical 转换框架 | fetch 返回的 DataFrame | domain service 转 canonical object 的 hook | 1B-A 框架就位，真实转换逻辑可后续填充 |
| TP-108 | 限流框架 | 无 | 内置 rate limiter（Tushare 免费版默认 200 RPM，可配置） | 1B-A 框架就位；真实限流在真实 API 激活后生效 |
| TP-109 | 重试框架 | 无 | 指数退避重试（可配置次数） | 1B-A 框架就位 |

### 3.4 AKShareProvider

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| AK-101 | name 属性 | 无 | `"akshare"` | — |
| AK-102 | capabilities 声明 | 无 | 8 条 capability set（见 §4.5 表） | — |
| AK-103 | markets 声明 | 无 | `{Market.CN}` | — |
| AK-104 | is_available | 无 | `True` if `akshare` 可 import；否则 `False` | 无需 token |
| AK-105 | fetch（1B-A stub） | domain, operation, sid, **params | `pd.DataFrame`（fake/stub 数据） | 同 TP-105 |
| AK-106 | fetch 不支持的 capability | 未声明的 capability | raise `UnsupportedCapabilityError` | — |
| AK-107 | canonical 转换框架 | 同 TP-107 | 同 TP-107 | — |
| AK-108 | 限流框架 | 无 | 内置简单延迟（默认 `time.sleep(0.5)` 每请求，可配置） | 1B-A 框架就位 |

### 3.5 FreshnessPolicy

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| FP-101 | get_ttl | `domain="market_data"` | TTL 秒数（int） | 未知 domain 返回默认 3600 |
| FP-102 | label — realtime | fetched_at 距 now < 60s, from_cache=False | `"realtime"` | — |
| FP-103 | label — delayed | fetched_at 距 now < 15min, from_cache=False | `"delayed"` | — |
| FP-104 | label — cached | from_cache=True 且未超过 domain TTL | `"cached"` | 1B-A 阶段 from_cache 恒 False，不触发 |
| FP-105 | label — stale | from_cache=True 但已超过 domain TTL | `"stale"` | 1B-A 阶段不触发 |
| FP-106 | label — empty | data 为 None 或空 | `"empty"` | — |
| FP-107 | 自定义 TTL 覆盖 | config 覆盖 DEFAULT_TTLS | 更新后的 TTL 表 | — |
| FP-108 | 纯函数无 I/O | 任意输入 | 不读写文件/网络/Mongo | — |

### 3.6 UnifiedDataClient.query() 接入

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| UC-101 | query 接入增强版 Router | domain, operation, sid, provider=?, force_refresh=?, params=? | DataResult | 委托给 DataRouter.query() |
| UC-102 | force_refresh 透传 | `force_refresh=True` | 透传给 Router | Router 跳过 Step 1 |
| UC-103 | provider 透传 | `provider="tushare"` | 透传给 Router | Router 跳过 internal-first |
| UC-104 | 14 个域入口方法不变 | Phase 1A 签名 | DataResult 直连 TA-CN adapter | 不走 Router（与 1B-A 路由隔离） |

---

## 4. 数据与接口契约

### 4.1 DataRouter（增强版签名）

```python
class DataRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        config: UnifiedDataConfig | None = None,
        *,
        ta_cn_adapter: "TA_CNMongoAdapter | None" = None,   # Step 1 internal source
        local_mongo_adapter: "LocalMongoAdapter | None" = None,  # Step 2 (1B-B 占位，1B-A 传 None)
        cache_manager: "CacheManager | None" = None,            # Step 3 (1B-B 占位，1B-A 传 None)
        freshness: "FreshnessPolicy | None" = None,
        external_fallback_chains: dict[str, list[str]] | None = None,
    ) -> None: ...

    def query(
        self,
        domain: str,
        operation: str,
        security_id: SecurityId,
        *,
        provider: str | None = None,
        force_refresh: bool = False,
        market: Market | str | None = None,
        params: Mapping[str, Any] | None = None,
        fetched_at: datetime | None = None,
    ) -> DataResult: ...
```

**构造参数语义**：

| 参数 | 1B-A 值 | 说明 |
|---|---|---|
| `registry` | 必填 | ProviderRegistry 实例（增强版，见 §4.2） |
| `config` | 可选 | Phase 0 UnifiedDataConfig（`fallback_for` 仍用于 chain 解析的 fallback） |
| `ta_cn_adapter` | 可选（推荐注入） | Phase 1A TA_CNMongoAdapter；None 时 Step 1 跳过 |
| `local_mongo_adapter` | **1B-A 恒 None** | 1B-B 才存在；None 时 Step 2 跳过 |
| `cache_manager` | **1B-A 恒 None** | 1B-B 才存在；None 时 Step 3 跳过 |
| `freshness` | 可选 | FreshnessPolicy 实例；None 时用默认 FreshnessPolicy() |
| `external_fallback_chains` | 可选 | capability → 有序 provider name 列表；None 时用 registry order |

**query() 返回值语义**（四步编排）：

| Step | 条件 | 命中 | 未命中 | 异常 |
|---|---|---|---|---|
| 1 TA-CN | `ta_cn_adapter is not None` AND NOT force_refresh AND provider not in external set | `DataResult(provider="ta_cn_internal")` | 继续 Step 2 | catch-and-log，继续 Step 4 |
| 2 LocalMongo | `local_mongo_adapter is not None`（1B-A 恒 False） | — | 跳过 | — |
| 3 Cache | `cache_manager is not None`（1B-A 恒 False） | — | 跳过 | — |
| 4 External | external_fallback_chains 或 registry order | `DataResult(provider="tushare"/"akshare")` | `DataResult.error(provider="error")` | 记录 source_trace，返回 error |

> **provider 参数与 force_refresh 的优先级**：`provider` 参数优先级最高。若 `provider="tushare"`，则无论 `force_refresh` 为何值，都跳过 Step 1/2/3 只走 tushare。若 `provider="ta_cn_internal"`，只走 Step 1 不走外部。

### 4.2 ProviderRegistry（增强版签名）

```python
class ProviderRegistry:
    # Phase 0 已有方法保持不变：register / unregister / clear / get / list_providers /
    #   list_provider_names / list_capabilities / get_providers / has_capability

    def set_external_fallback_chains(
        self, chains: Mapping[str, Sequence[str]]
    ) -> None:
        """注入 external_fallback_chains 配置。

        chains: capability → 有序 provider name 列表。
        覆盖已有 chains。未知 capability 的 chain 也存储（Router 运行时按需查询）。
        """

    def get_external_fallback_chain(self, capability: str) -> list[str]:
        """返回该 capability 的外部 fallback chain。

        优先级：external_fallback_chains[capability] → 空（由 Router 回退到 registry order）。
        """
```

> **与 Phase 0 UnifiedDataConfig 的关系**：Phase 0 的 `UnifiedDataConfig.capability_fallback_overrides` 仍保留。1B-A Router 解析 chain 的优先级为：`provider 参数 → external_fallback_chains[cap] → config.fallback_for(cap) → registry.get_providers(cap) order`。四级 fallback，保持向后兼容。

### 4.3 DataRouter.query() 编排伪逻辑

```
query(domain, operation, sid, provider=None, force_refresh=False, params):
    capability = f"{domain}.{operation}"
    trace = []
    ts = fetched_at or now()

    # provider 参数优先：直接走指定路径
    if provider == "ta_cn_internal":
        return _query_ta_cn(sid, capability, params, trace, ts, force_external=False)
    if provider is not None:  # 外部 provider 名
        return _query_external_single(provider, sid, capability, params, trace, ts)

    # internal-first 全路径
    if not force_refresh and self._ta_cn_adapter is not None:
        result = _try_ta_cn(sid, capability, params, trace, ts)
        if result is not None:  # 命中或明确 empty（TA-CN 覆盖该域）
            return result

    # Step 2/3 占位（1B-A 跳过）

    # Step 4: 外部 fallback
    return _query_external_chain(sid, capability, params, trace, ts)
```

**`_try_ta_cn` 返回值语义**：

- TA-CN adapter 覆盖该 capability（见 §4.4 映射表）且返回非空 → 返回 `DataResult.success(provider="ta_cn_internal")`
- TA-CN adapter 覆盖该 capability 但返回空 → 返回 `DataResult(provider="empty", freshness="empty")`（表示 TA-CN 有此域但无此标的的数据，不再走外部）
- TA-CN adapter 不覆盖该 capability（如 `valuation.daily_basic`、`calendar.*`）→ 返回 `None`（信号 Router 继续 Step 4）
- TA-CN adapter 异常 → catch-and-log，trace 记录 `"ta_cn_internal(error: ...)"`，返回 `None`（继续 Step 4）

> **关键决策**：TA-CN 返回空时 **不再 fallback 到外部**。这与 RFC-03-008 §5.1.1 的 Step 1 逻辑一致：「TA-CN adapter 未命中（空）→ 继续 Step 4」。但需区分两种「空」：(a) TA-CN 不覆盖该域 → 继续 Step 4；(b) TA-CN 覆盖该域但该标的无数据 → 不继续（内部已有此域，只是无此标的）。Design 阶段需明确 TA-CN adapter 如何区分这两种情况（通过 capability 映射表 §4.4 而非数据返回值）。

### 4.4 TA-CN capability 映射表（Step 1 适用域）

DataRouter Step 1 只对以下 capability 调用 TA-CN adapter。其余 capability 直接跳到 Step 4。

| Capability | TA-CN adapter 方法 | 说明 |
|---|---|---|
| `market_data.kline_daily` | `get_daily_bars(symbol, start_date, end_date, limit)` | 日线 |
| `market_data.realtime_quote` | `get_realtime_quotes(symbol)` | 实时快照 |
| `financial.income_statement` | `get_financials(symbol, report_period)` → 提取 income | 财务（service 层按 statement_type 提取） |
| `financial.balance_sheet` | `get_financials(symbol, report_period)` → 提取 balance | 同上 |
| `financial.cash_flow` | `get_financials(symbol, report_period)` → 提取 cashflow | 同上 |
| `metadata.stock_list` | `get_stock_list(market, status, limit)` | 股票列表 |
| `metadata.stock_info` | `get_stock_info(symbol, market)` | 单只股票信息 |
| `metadata.index_list` | `get_index_list(market)` | 指数列表 |
| `metadata.index_info` | `get_index_info(symbol)` | 单个指数信息 |
| `market_data.index_daily` | `get_index_daily_bars(symbol, ...)` | 指数日线 |
| `news.stock_news` | `get_news(symbol, limit)` | 个股新闻 |

**TA-CN 不覆盖的 capability**（直接走 Step 4）：

- `market_data.kline_weekly`（TA-CN 无周线集合）
- `market_data.adj_factor`（复权因子，Tushare 独有）
- `valuation.daily_basic`（每日估值，TA-CN `stock_basic_info` 有 pe/pb 但非日频估值）
- `calendar.trading_days` / `calendar.is_trading_day`（TA-CN 无独立日历集合）
- `metadata.index_members`（指数成分股，TA-CN 无此集合）

> **Design 阶段待定**：TA-CN capability 映射表是硬编码在 DataRouter 中，还是可配置。本 SPEC 建议硬编码为 Router 内部常量（1B-A 范围固定），1B-B 再考虑配置化。

### 4.5 TushareProvider / AKShareProvider capability 表

| Capability | Tushare | AKShare | 说明 |
|---|---|---|---|
| `market_data.kline_daily` | ✅ | ✅ | A 股日线 K 线 |
| `market_data.kline_weekly` | ✅ | ✅ | 周线 K 线 |
| `market_data.realtime_quote` | ✅ | ✅ | 实时行情快照 |
| `market_data.adj_factor` | ✅ | ❌ | 复权因子（Tushare 独有） |
| `financial.income_statement` | ✅ | ❌ | 利润表 |
| `financial.balance_sheet` | ✅ | ❌ | 资产负债表 |
| `financial.cash_flow` | ✅ | ❌ | 现金流量表 |
| `valuation.daily_basic` | ✅ | ✅ | 每日估值（PE/PB/PS） |
| `calendar.trading_days` | ✅ | ✅ | 交易日历 |
| `calendar.is_trading_day` | ✅ | ✅ | 判断交易日 |
| `metadata.stock_list` | ✅ | ✅ | 股票列表 |
| `metadata.index_members` | ✅ | ❌ | 指数成分股 |
| `news.stock_news` | ✅ | ❌ | 个股新闻 |

Tushare 声明 13 条；AKShare 声明 8 条。交集 = 6 条（kline_daily, kline_weekly, realtime_quote, daily_basic, trading_days, is_trading_day, stock_list 共 7 条——见下方修正）。

> **修正**：AKShare 覆盖的 8 条为 `kline_daily, kline_weekly, realtime_quote, daily_basic, trading_days, is_trading_day, stock_list`。重新清点：AKShare 不覆盖 adj_factor / income_statement / balance_sheet / cash_flow / index_members / stock_news（6 条不覆盖），因此 AKShare 覆盖 13 - 6 = 7 条。上表 AKShare 列共 7 个 ✅。**与 RFC-03-008 §5.2.1 一致**。

### 4.6 FreshnessPolicy 签名

```python
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
        """可选 TTL 覆盖；None 时用 DEFAULT_TTLS。"""

    def get_ttl(self, domain: str) -> int:
        """返回 domain 的 TTL 秒数。未知 domain 返回默认 3600。"""

    def label(
        self,
        fetched_at: datetime,
        data_date: str | None,
        domain: str,
        from_cache: bool,
    ) -> FreshnessLabel:
        """计算 freshness 标签。纯函数，无 I/O。

        规则（按优先级）：
        1. data 为空 → "empty"（由调用方判断 data 后传入信号；本方法接收 data_date=None 作为空信号）
        2. from_cache and 未超过 TTL → "cached"
        3. from_cache and 已超过 TTL → "stale"
        4. not from_cache and fetched_at 距 now < 60s → "realtime"
        5. not from_cache and fetched_at 距 now < 15min → "delayed"
        6. 其余 → "delayed"（兜底）
        """
```

> **1B-A 阶段 from_cache 恒为 False**：FreshnessPolicy 在 1B-A 只产出 `realtime` / `delayed` / `empty`。`cached` / `stale` 标签的激活路径在 1B-B CacheManager 引入后才可用。

### 4.7 UnifiedDataClient.query() 增强签名

```python
class UnifiedDataClient:
    def query(
        self,
        domain: str,
        operation: str,
        security_id: SecurityId,
        *,
        provider: str | None = None,
        force_refresh: bool = False,    # [1B-A 新增]
        market: Market | str | None = None,
        params: Mapping[str, Any] | None = None,
        fetched_at: datetime | None = None,
    ) -> DataResult:
        """委托给增强版 DataRouter.query()。"""
```

> `force_refresh` 是 1B-A 新增参数，默认 `False`，向后兼容 Phase 0 / 1A 调用方。

### 4.8 错误/降级矩阵（DataResult 终态）

| 场景 | DataResult.provider | DataResult.freshness | DataResult.source_trace | DataResult.warnings |
|---|---|---|---|---|
| TA-CN 命中 | `"ta_cn_internal"` | `label(...)` | `["ta_cn_internal(ok)"]` | `[]` |
| TA-CN 异常 + 外部成功 | `"tushare"` / `"akshare"` | `label(...)` | `["ta_cn_internal(error: ...)", "tushare(ok)"]` | `["ta_cn_internal error, fell back to tushare"]` |
| TA-CN 不覆盖 + 外部成功 | `"tushare"` / `"akshare"` | `label(...)` | `["tushare(ok)"]` | `[]` |
| TA-CN 不覆盖 + 外部全不可用 | `"error"` | `"empty"` | `["tushare(skipped: unavailable)", "akshare(skipped: unavailable)"]` | `["all external providers unavailable"]` |
| TA-CN 不覆盖 + 外部全失败 | `"error"` | `"empty"` | `["tushare(error: ...)", "akshare(error: ...)"]` | `["all external providers failed"]` |
| force_refresh + 外部成功 | `"tushare"` | `label(...)` | `["tushare(ok)"]` | `[]` |
| provider="tushare" + 成功 | `"tushare"` | `label(...)` | `["tushare(ok)"]` | `[]` |
| provider="tushare" + 不可用 | `"error"` | `"empty"` | `["tushare(skipped: unavailable)"]` | `["tushare unavailable"]` |
| 无任何 provider 注册 | `"error"` | `"empty"` | `[]` | `["no providers registered"]` |

---

## 4.bis 持久化契约

**无持久化需求。**

1B-A 阶段全部组件运行在内存中：

- DataRouter / ProviderRegistry / FreshnessPolicy：纯内存对象，进程生命周期内有效。
- TushareProvider / AKShareProvider：`fetch()` 返回 in-memory DataFrame，不写入 Mongo。
- TA-CN adapter：Phase 1A 已交付的只读复用，不新增写入。
- external_fallback_chains：内存配置（由构造参数或 `set_external_fallback_chains` 注入），不落盘。

数据流：`消费方 → UnifiedDataClient.query() → DataRouter（内存编排）→ TA-CN adapter（只读 Mongo）/ Provider.fetch()（in-memory stub）→ DataResult（内存返回）`。全程不触碰 `03_data_ud_*` / `03_data_ud_cache_*` 集合。

---

## 5. 行为契约（RFC-03-008 开放问题 → 代码层映射）

RFC-03-008 §10 留有 1 个开放问题，以及 §3/§5 定义了若干必须落地的行为决策。逐条映射：

| # | RFC 决策/需求 | SPEC 落地点 | 章节 |
|---|---|---|---|
| 1 | internal-first 路径：TA-CN → UD 物化 → Cache → 外部 | DataRouter 四步编排，Step 2/3 占位跳过 | §4.1 / §4.3 |
| 2 | TA-CN adapter 只读优先 | DataRouter Step 1 调 TA-CN adapter，capability 映射表限定 | §4.3 / §4.4 |
| 3 | provider 指定跳过 internal-first | `provider` 参数优先级最高，直接走指定路径 | §4.1 / §4.3 |
| 4 | force_refresh 跳过 TA-CN + cache | `force_refresh=True` 跳过 Step 1（及未来 Step 2/3） | §4.1 / DR-102 |
| 5 | 外部链仅为 Tushare → AKShare | external_fallback_chains 只含这两个 name | §4.2 / §4.5 |
| 6 | DSA 不进入运行时链 | external_fallback_chains 不含 DSA | §0.2 / §4.5 |
| 7 | FreshnessPolicy 纯计算 | 无 I/O，`get_ttl` + `label` 纯函数 | §4.6 / FP-108 |
| 8 | 1B-A from_cache 恒 False | freshness 只产 realtime/delayed/empty | §0 / §4.6 |
| 9 | 全部失败返回 error DataResult（不抛异常） | DataRouter 返回 `DataResult.error(...)` | §3.1 DR-106~108 / §4.8 |
| 10 | 14 个域入口方法不变 | 不修改 client.py 的 14 个方法 | §7.3 |
| 11 | provider capability 保守声明 | Tushare 13 条 / AKShare 7 条 | §4.5 |
| 12 | is_available 只检查存在性，不泄露 token | TP-104 / AK-104 | §3.3 / §3.4 / §7.2 |
| 13 | 1B-A 不做真实 API 调用 | fetch 返回 stub DataFrame | TP-105 / AK-105 |
| 14 | **开放问题**：DataRouter 增强是否破坏 Phase 0 query() | 向后兼容：ta_cn_adapter=None 时退化；新增 force_refresh 有默认值 | §11 |

---

## 6. 配置契约

### 6.1 external_fallback_chains 默认配置

```yaml
unified_data:
  external_fallback_chains:
    "market_data.kline_daily": ["tushare", "akshare"]
    "market_data.kline_weekly": ["tushare", "akshare"]
    "market_data.realtime_quote": ["tushare", "akshare"]
    "market_data.adj_factor": ["tushare"]
    "financial.income_statement": ["tushare"]
    "financial.balance_sheet": ["tushare"]
    "financial.cash_flow": ["tushare"]
    "valuation.daily_basic": ["tushare", "akshare"]
    "calendar.trading_days": ["tushare", "akshare"]
    "calendar.is_trading_day": ["tushare", "akshare"]
    "metadata.stock_list": ["tushare", "akshare"]
    "metadata.index_members": ["tushare"]
    "news.stock_news": ["tushare"]
```

### 6.2 provider 配置

```yaml
unified_data:
  providers:
    tushare:
      enabled: true
      token_env: "TUSHARE_TOKEN"        # 环境变量名，不记录值
      rate_limit_rpm: 200               # 默认 200 RPM（Tushare 免费版）
      retry_max_attempts: 3             # 指数退避重试次数
      retry_backoff_base: 1.0           # 退避基数（秒）
    akshare:
      enabled: true
      request_delay_seconds: 0.5        # 每请求延迟
```

### 6.3 freshness TTL 覆盖

```yaml
unified_data:
  freshness:
    overrides:
      "market_data": 21600              # 6h
      "financial": 86400                # 24h
      "valuation": 43200                # 12h
      "calendar": 604800                # 7d
      "metadata": 604800                # 7d
      "news": 3600                      # 1h
```

### 6.4 配置键与环境变量名

| 配置键 | 环境变量 | 说明 | 敏感值不记录 |
|---|---|---|---|
| `providers.tushare.token_env` | `TUSHARE_TOKEN` | Tushare token 环境变量名 | ✅ is_available 只检查存在性 |
| `providers.tushare.rate_limit_rpm` | 无 | 限流配置 | — |
| `providers.akshare.request_delay_seconds` | 无 | 请求延迟 | — |
| `freshness.overrides.*` | 无 | TTL 覆盖 | — |

**安全原则（P-10）**：
- 凭据值不记录在 task metadata、kanban summary、审计日志中。
- `is_available()` 只检查「环境变量是否存在且非空」，不读取/打印值。
- 配置文件中凭据用环境变量名引用（`token_env: "TUSHARE_TOKEN"`），不内联值。

---

## 7. 实现约束

### 7.1 依赖限制

- 不新增 pip 依赖。`tushare` 和 `akshare` 的 import 用 try/except 包裹（`is_available()` 返回 False 时不影响其他 provider）。
- `pandas` 已是项目依赖（Phase 0 DataResult 使用），不新增。
- FreshnessPolicy 只用 stdlib（`datetime`）。

### 7.2 安全约束

- Tushare token 从环境变量 `TUSHARE_TOKEN` 读取，**不记录/不打印真实值**。
- `is_available()` 只检查「变量是否存在且非空」，不泄露值。
- provider fetch 的 stub 数据不含真实凭据。

### 7.3 禁止事项（不改动清单）

| 路径 | 理由 |
|---|---|
| `skills/apps/TradingAgents-CN/**` | TA-CN 子项目，只读复用 |
| `skills/research/daily_stock_analysis/**` | DSA 独立子系统，不是运行时数据源 |
| `skills/data/data-pipeline/**` | ETL 管道，职责正交 |
| `skills/data/data_interface/**` | RFC-03-003 IReader/IWriter |
| `skills/infra/task_center/**` | 任务中心独立线 |
| `skills/research/stock/**` | stock 框架是消费方 |
| 生产 MongoDB 集合的 schema validator / DDL / 索引 | 不改现有集合约束 |
| cron / systemd / gateway / 外部推送配置 | 不碰调度和推送 |
| `skills/data/unified_data/models/**`（SecurityId / DataResult / Capability / Market） | Phase 0 公共契约不变；只新增方法/参数不改已有签名 |
| `skills/data/unified_data/adapters/ta_cn_mongo_adapter.py` | Phase 1A 已交付，只读复用 |
| Phase 1A 的 14 个域入口方法（`client.py` L166-288） | 行为不变，不走 Router |
| RFC/SPEC/Design 文档模板 | 编排层不改模板（P-7） |

### 7.4 性能约束

- DataRouter.query() 的 TA-CN Step 1 不引入额外网络开销（TA-CN adapter 已是 Mongo find）。
- provider `is_available()` 必须是 O(1) 操作（检查环境变量/import），不做网络探测。
- FreshnessPolicy.label() 纯计算，O(1)。

---

## 8. 文件改动清单

### 8.1 新增文件

| 路径 | 说明 |
|---|---|
| `skills/data/unified_data/providers/__init__.py` | provider 包初始化 |
| `skills/data/unified_data/providers/tushare.py` | TushareProvider 实现 |
| `skills/data/unified_data/providers/akshare.py` | AKShareProvider 实现 |
| `skills/data/unified_data/freshness.py` | FreshnessPolicy 实现 |
| `skills/data/unified_data/providers/base_external.py` | 外部 provider 公共基类（限流/重试/canonical 框架） |
| `tests/data/unified_data/test_freshness_policy.py` | FreshnessPolicy 单元测试 |
| `tests/data/unified_data/test_providers.py` | TushareProvider / AKShareProvider 单元测试 |
| `tests/data/unified_data/test_router_internal_first.py` | DataRouter internal-first 编排测试 |

### 8.2 修改文件

| 路径 | 修改内容 |
|---|---|
| `skills/data/unified_data/router.py` | DataRouter 增强：新增 `ta_cn_adapter` / `local_mongo_adapter` / `cache_manager` / `freshness` / `external_fallback_chains` 构造参数；query() 新增 `force_refresh` 参数；实现四步编排逻辑；全部失败改为返回 DataResult.error（不抛异常） |
| `skills/data/unified_data/registry.py` | ProviderRegistry 增强：新增 `set_external_fallback_chains()` / `get_external_fallback_chain()` |
| `skills/data/unified_data/client.py` | UnifiedDataClient.query() 新增 `force_refresh` 参数透传；构造时将 ta_cn_adapter 传给 Router |
| `skills/data/unified_data/__init__.py` | 导出 TushareProvider / AKShareProvider / FreshnessPolicy |

### 8.3 不改动文件（明确列出）

- 见 §7.3 禁止事项表。特别注意：`models/**`、`adapters/ta_cn_mongo_adapter.py`、`exceptions.py`、`config.py`、Phase 1A 的 14 个域入口方法均不改。

---

## 9. 测试要求

### 9.1 单元测试矩阵

| 测试编号 | 测试目标 | 覆盖功能 | mock 方式 | 断言 |
|---|---|---|---|---|
| UT-FP-001 | FreshnessPolicy.get_ttl 已知 domain | FP-101 | 无 mock | `get_ttl("market_data") == 21600` |
| UT-FP-002 | FreshnessPolicy.get_ttl 未知 domain | FP-101 | 无 mock | `get_ttl("unknown") == 3600` |
| UT-FP-003 | label realtime | FP-102 | 固定 now，fetched_at=now-30s | `label(...) == "realtime"` |
| UT-FP-004 | label delayed | FP-103 | fetched_at=now-5min | `== "delayed"` |
| UT-FP-005 | label empty | FP-106 | data_date=None | `== "empty"` |
| UT-FP-006 | label cached（1B-B 预留） | FP-104 | from_cache=True, 未超 TTL | `== "cached"` |
| UT-FP-007 | label stale（1B-B 预留） | FP-105 | from_cache=True, 已超 TTL | `== "stale"` |
| UT-FP-008 | TTL 覆盖 | FP-107 | `FreshnessPolicy(ttl_overrides={"market_data": 100})` | `get_ttl("market_data") == 100` |
| UT-TP-001 | TushareProvider.name | TP-101 | 无 mock | `== "tushare"` |
| UT-TP-002 | TushareProvider.capabilities | TP-102 | 无 mock | 13 条 capability set |
| UT-TP-003 | TushareProvider.markets | TP-103 | 无 mock | `== {Market.CN}` |
| UT-TP-004 | is_available token 存在 | TP-104 | monkeypatch `os.environ` 设 TUSHARE_TOKEN | `== True` |
| UT-TP-005 | is_available token 缺失 | TP-104 | monkeypatch 删除 TUSHARE_TOKEN | `== False` |
| UT-TP-006 | fetch stub 返回 DataFrame | TP-105 | 无真实 API | 返回非空 DataFrame |
| UT-TP-007 | fetch 不支持 capability | TP-106 | 调未声明 capability | raise `UnsupportedCapabilityError` |
| UT-AK-001 | AKShareProvider.name | AK-101 | 无 mock | `== "akshare"` |
| UT-AK-002 | AKShareProvider.capabilities | AK-102 | 无 mock | 7 条 capability set |
| UT-AK-003 | AKShareProvider.markets | AK-103 | 无 mock | `== {Market.CN}` |
| UT-AK-004 | is_available akshare 可 import | AK-104 | mock import 成功 | `== True` |
| UT-AK-005 | is_available akshare 不可 import | AK-104 | mock import 失败 | `== False` |
| UT-AK-006 | fetch stub | AK-105 | 无真实 API | 返回非空 DataFrame |
| UT-DR-001 | internal-first TA-CN 命中 | DR-101 | FakeDatabase + TA_CNAdapter + FakeProvider(external) | `provider == "ta_cn_internal"`，external provider call_log 为空 |
| UT-DR-002 | TA-CN 不覆盖 → 外部成功 | DR-101 | FakeDatabase 空 + FakeProvider(external ok) | `provider == "tushare"` |
| UT-DR-003 | TA-CN 异常 → 外部 fallback | DR-101 | FakeDatabase 抛异常 + FakeProvider(ok) | `provider == "tushare"`，warnings 非空 |
| UT-DR-004 | force_refresh 跳过 TA-CN | DR-102 | FakeDatabase 有数据 + force_refresh=True | `provider == "tushare"`，TA-CN 未被调用 |
| UT-DR-005 | provider="tushare" 只走外部 | DR-103 | FakeDatabase 有数据 + provider="tushare" | `provider == "tushare"`，TA-CN 未被调用 |
| UT-DR-006 | provider="ta_cn_internal" 只走内部 | DR-104 | FakeDatabase 有数据 + provider="ta_cn_internal" | `provider == "ta_cn_internal"` |
| UT-DR-007 | 全部 provider 不可用 | DR-106 | FakeProvider(available=False) x2 | `DataResult.error`，`provider == "error"` |
| UT-DR-008 | 全部 provider fetch 失败 | DR-107 | FakeProvider(raise ProviderError) x2 | `DataResult.error`，source_trace 含 2 个 error |
| UT-DR-009 | 无 provider 注册 | DR-108 | 空 registry | `DataResult.error`，source_trace == [] |
| UT-DR-010 | source_trace 完整 | DR-109 | TA-CN 异常 + tushare 失败 + akshare 成功 | trace == `["ta_cn_internal(error: ...)", "tushare(error: ...)", "akshare(ok)"]` |
| UT-DR-011 | warnings 降级告警 | DR-110 | tushare 不可用 + akshare 成功 | `warnings == ["tushare unavailable, fell back to akshare"]` |
| UT-DR-012 | TA-CN adapter 未注入退化 | DR-105 | ta_cn_adapter=None + FakeProvider(ok) | `provider == "tushare"`（Phase 0 兼容） |
| UT-RG-001 | set_external_fallback_chains | RG-101 | 注入 chains | `get_external_fallback_chain("market_data.kline_daily") == ["tushare", "akshare"]` |
| UT-RG-002 | chain 解析优先级 | RG-102 | external_chains + config override | external_chains 优先于 config |

### 9.2 集成测试

| 测试编号 | 测试目标 |
|---|---|
| IT-001 | 端到端：client.query(kline_daily) → TA-CN 命中 → 返回（不调 external） |
| IT-002 | 端到端：client.query(valuation.daily_basic) → TA-CN 不覆盖 → tushare stub → 返回 |
| IT-003 | 端到端：client.query(kline_daily, force_refresh=True) → 跳过 TA-CN → tushare stub |
| IT-004 | 端到端：client.query(kline_daily, provider="tushare") → 只走 tushare |

### 9.3 回归测试

- Phase 0 的 `test_router.py`（22 个测试函数）全部通过（向后兼容验证）。
- Phase 1A 的 `test_client_phase1a.py`（25 个测试函数）全部通过（14 个域入口方法不变）。

### 9.4 不可自动化验证项

- Tushare/AKShare 真实 API 可用性（1B-A 不做，后续段 `@pytest.mark.network`）。
- 真实 token 安全性审查（人工审计 is_available 不泄露值）。

---

## 10. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | DataRouter 实现 internal-first 四步编排 | UT-DR-001 ~ UT-DR-012 全通过 |
| A-002 | TushareProvider 13 条 capability 完整声明 | UT-TP-002 |
| A-003 | AKShareProvider 7 条 capability 完整声明 | UT-AK-002 |
| A-004 | FreshnessPolicy 纯计算 5 种标签 | UT-FP-001 ~ UT-FP-008 |
| A-005 | UnifiedDataClient.query() 接入 force_refresh | IT-003 |
| A-006 | provider 参数语义矩阵全覆盖 | UT-DR-005, UT-DR-006, IT-004 |
| A-007 | source_trace 全路径完整记录 | UT-DR-010 |
| A-008 | DataResult 错误/告警字段正确 | UT-DR-007 ~ UT-DR-009, UT-DR-011 |
| A-009 | 全部失败返回 error DataResult（不抛异常） | UT-DR-007 ~ UT-DR-009 |
| A-010 | Phase 0 测试回归通过 | test_router.py 22/22 |
| A-011 | Phase 1A 测试回归通过 | test_client_phase1a.py 25/25 |
| A-012 | external_fallback_chains 只含 tushare/akshare | grep SPEC + config 验证 |
| A-013 | DSA 不出现在任何运行时链路 | grep "dsa\|DSA\|StockDaily" providers/ router.py → 0 命中 |
| A-014 | is_available 不泄露 token 值 | 代码审查 + UT-TP-004/005 |
| A-015 | 不新增 Mongo 集合/索引/写入 | grep "create_collection\|create_index\|insert_one\|update_one" 新增文件 → 0 命中 |
| A-016 | 不修改 TA-CN 子项目代码 | `git diff skills/apps/TradingAgents-CN/` → 空 |
| A-017 | 不修改 Phase 1A 14 个域入口方法 | `git diff client.py` 只改 query() 和 __init__ |

---

## 11. 向后兼容

### 11.1 DataRouter 增强对 Phase 0 的影响

Phase 0 的 DataRouter 构造签名为 `__init__(registry, config=None)`，query() 签名为 `query(domain, operation, sid, *, provider=None, market=None, params=None, fetched_at=None)`。

1B-A 增强：

- 构造新增 5 个可选参数（`ta_cn_adapter` / `local_mongo_adapter` / `cache_manager` / `freshness` / `external_fallback_chains`），全部默认 None。
- query() 新增 `force_refresh=False`（默认值）。
- **行为变更**：全部失败时从抛 `AllProvidersFailedError` 改为返回 `DataResult.error(...)`。

**退化路径**（ta_cn_adapter=None 时）：

- Step 1 自动跳过（adapter 为 None）。
- Step 2/3 恒跳过（1B-A）。
- 直接进入 Step 4 外部 fallback。
- 行为等价于 Phase 0 的外部 fallback Router。

**Phase 0 测试兼容**：

- Phase 0 的 `test_router.py` 用 `DataRouter(registry, config)` 构造（无 ta_cn_adapter），自动退化。
- Phase 0 测试中断言 `AllProvidersFailedError` 的用例需要更新为断言 `DataResult.error`。**这是唯一的破坏性变更**，需在 Implement 阶段同步更新 `test_router.py` 中相关断言。SPEC 在此明确声明，Design 阶段需给出具体的测试更新清单。

### 11.2 UnifiedDataClient.query() 对 Phase 0/1A 的影响

- `force_refresh` 新增参数有默认值 `False`，现有调用方不需要修改。
- 14 个域入口方法完全不变。

### 11.3 ProviderRegistry 对 Phase 0 的影响

- 新增 `set_external_fallback_chains` / `get_external_fallback_chain`，不改已有方法签名。
- Phase 0 的 `UnifiedDataConfig.fallback_for()` 仍保留，作为 chain 解析的 fallback。

---

## 12. 风险与未解决问题

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| DataRouter 行为变更（抛异常 → 返回 error）破坏 Phase 0 测试 | 高 | 中 | §11.1 明确退化路径；Implement 同步更新 test_router.py 断言 |
| TA-CN「覆盖但空」vs「不覆盖」区分逻辑不清晰 | 中 | 高 | §4.4 capability 映射表硬编码；Design 阶段明确 Router 如何查询映射表 |
| fake provider 测试与真实 provider 行为偏差 | 中 | 中 | 1B-A 标注「框架 + fake 验证」；后续段补真实 API smoke test |
| external_fallback_chains 硬编码 vs 配置化 | 低 | 低 | 1B-A 通过构造参数注入，默认硬编码；1B-B 再考虑 YAML 加载 |
| Tushare token 泄露到日志 | 低 | 高 | P-10：is_available 只检查存在性；UT-TP-004/005 验证 |

### 移交 Design 阶段的待决项

1. TA-CN capability 映射表的代码组织（Router 内部常量 vs 独立模块 vs 可配置）。
2. TushareProvider/AKShareProvider 的 stub DataFrame 数据形状（需与 canonical object 对齐）。
3. 限流/重试框架的具体实现（decorator vs mixin vs 内嵌）。
4. DataRouter 全部失败时不抛异常的决策是否需要 Feature Flag（渐进迁移）。
5. `provider="ta_cn_internal"` 时 TA-CN 返回空的处理：返回 empty DataResult 还是继续外部 fallback（SPEC §4.3 当前定义为不继续，Design 可复审）。

---

## 13. 参考资料

- RFC-03-008：`docs/rfc/03_data/RFC-03-008-unified-data-phase-1b-query-plane.md`
- RFC-03-007：`docs/rfc/03_data/RFC-03-007-unified-data-layer.md`
- SPEC-03-007：`docs/spec/03_data/SPEC-03-007-unified-data-layer.md`
- SPEC-03-006：provider fallback 设计参考
- DESIGN-03-007：`docs/design/03_data/DESIGN-03-007-unified-data-layer.md`（待 T2 Design 补 1B-A 章节）
- 现有代码：
  - `skills/data/unified_data/router.py`（Phase 0 DataRouter，238 行）
  - `skills/data/unified_data/registry.py`（Phase 0 ProviderRegistry，171 行）
  - `skills/data/unified_data/provider.py`（DataProvider ABC，121 行）
  - `skills/data/unified_data/client.py`（UnifiedDataClient，315 行）
  - `skills/data/unified_data/config.py`（UnifiedDataConfig，58 行）
  - `skills/data/unified_data/exceptions.py`（异常体系，71 行）
  - `skills/data/unified_data/models/__init__.py`（SecurityId / DataResult / Capability，524 行）
  - `skills/data/unified_data/adapters/ta_cn_mongo_adapter.py`（TA-CN 只读 adapter，380 行）
- 测试基础设施：
  - `tests/data/unified_data/conftest.py`（FakeProvider / fixtures）
  - `tests/data/unified_data/fixtures/__init__.py`（FakeDatabase / FakeCollection / FakeCursor）
  - `tests/data/unified_data/fixtures/ta_cn_mock_docs.py`（TA-CN 样本文档）
