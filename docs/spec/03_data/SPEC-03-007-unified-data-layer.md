# SPEC-03-007: YQuant Unified Data Layer

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-12 |
| 最后更新 | 2026-07-14 |
| 来源 RFC | RFC-03-007 |
| 目标模块 | unified_data（全局数据访问层） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |
| 关联 RFC | RFC-03-003（数据架构）、RFC-00-001（全局架构） |
| 关联 SPEC | SPEC-03-004、SPEC-03-005、SPEC-03-006 |
| 版本号 | V1.2（与 RFC-03-007 V0.3 / DESIGN-03-007 V3.3 同步） |

---


## 0. Design 阶段修订说明（2026-07-12）

根据 Pascal 后续确认，unified_data 新增持久化集合统一使用 MongoDB `03_data_ud_*` 前缀。**DSA 不是运行时数据源，不实现 DSA SQLite / `StockDaily` adapter，DSA 不出现在 `external_fallback_chains` 中**；DSA 既有 SQLite 仅为 DSA 子系统自身所有，与 unified_data 持久化后端无关。统一内部仅有 MongoDB 一条存储主线。

## 0.3 V1.2 文档同步修订说明（2026-07-14 Pascal 架构基线同步）

本次为文档同步修订（无代码改动、无生产副作用）。与 RFC-03-007 V0.3 / DESIGN-03-007 V3.3 同步，保持 Pascal 架构基线在三层文档中措辞一致。本节为 SPEC 内部修订的索引锚点，所有 §X 出现的下列措辞必须与本节一致：

- 「internal-first 读取路径」→ 「TA-CN 既有 → UD 物化 → Query Cache → 外部 Provider」
- 「DSA adapter / DSA SQLite / StockDaily」→ 仅作为分析/参考边界出现；不实现、不出现在 `external_fallback_chains`、不实现为 Provider
- 「物理隔离」→ 一律改为「命名空间隔离（共享同一物理库 `tradingagents`）」

## 0.4 V1.3 文档一致性修复（2026-07-14，Router 全失败对外契约同步）

本次为纯文档一致性修复（无代码改动、无生产副作用），对齐 Phase 1B-A 已确认的架构决策：自 Phase 1B-A 起，`DataRouter` 在所有 Provider 失败时对调用方返回 `DataResult.error(provider="error", source_trace=[...])`，不再以 `AllProvidersFailedError` 作为 Router 主出口，不设兼容开关。本 SPEC 受影响条目：§8 异常表 `AllProvidersFailedError` 行、§10.1 T-011、§10.2 TI-004。`AllProvidersFailedError` 类保留作内部/历史兼容类型，Phase 0 旧基线行为在文档中明确标识为历史描述。

## 0.1 Phase 1A 契约澄清（2026-07-13）

Phase 1A（TA-CN read-only adapter）的精确契约如下，Implement/Verify/Review 阶段以此为准：

**Phase 1A TA-CN MongoDB 只读集合（8 个，不含 DSA SQLite）：**

| # | 集合 | Canonical Object | Adapter 方法 | Service 入口 | Client API |
|---|---|---|---|---|---|
| 1 | `stock_basic_info` | `StockInfo` | `get_stock_info()` / `get_stock_list()` | `metadata_service.get_stock_list()` / `.get_stock_info()` | `get_stock_list()` / `get_stock_info()` |
| 2 | `market_quotes` | `RealtimeQuote` | `get_realtime_quotes()` | `market_data_service.get_realtime_quote()` | `get_realtime_quote()` |
| 3 | `stock_daily_quotes` | `DailyBar` | `get_daily_bars()` | `market_data_service.get_kline_daily()` | `get_kline_daily()` |
| 4 | `stock_financial_data` | `FinancialStatement` | `get_financials()` | `fundamental_service.get_income_statement()` / `.get_balance_sheet()` / `.get_cash_flow()` | `get_income_statement()` / `get_balance_sheet()` / `get_cash_flow()` |
| 5 | `stock_news` | `NewsItem` | `get_news()` | `event_service.get_news()` | `get_news()` |
| 6 | `index_basic_info` | `IndexInfo` | `get_index_info()` / `get_index_list()` | `metadata_service.get_index_list()` / `.get_index_info()` | `get_index_list()` / `get_index_info()` |
| 7 | `index_daily_quotes` | `IndexDailyBar` | `get_index_daily_bars()` | `market_data_service.get_index_daily()` / `sector_service.get_sector_index_bars()` | `get_index_daily()` / `get_sector_index_bars()` |
| 8 | `stock_sector_info` | `SectorClassification` | `get_stock_sector_info()` / `get_stocks_by_sector()` | `sector_service.get_stock_sector()` / `.get_stocks_by_sector()` | `get_stock_sector()` / `get_stocks_by_sector()` |

**Phase 1A 明确不做：**
- 外部 API 调用（Tushare / AKShare provider）→ Phase 1B
- `CacheManager` / `FreshnessPolicy` → Phase 1B
- MongoDB 写入或新增集合（Phase 1A adapter 只读，不写任何集合）
- DSA SQLite / `StockDaily` adapter → **不实现**（DSA 不是运行时数据源；本 SPEC 历史文本中任何"DSA SQLite adapter → Phase 1B"已废弃）
- `task_center` 集成 → Phase 5
- stock framework profile/model 集成 → Phase 6
- `force_refresh` / `provider` 参数（无缓存层、无外部 provider，参数接受但忽略）

**Phase 1A 输入/输出契约：**
- 所有 Client API 输入：`SecurityId`（Phase 0 已实现）+ 可选 `limit` / `start_date` / `end_date` / `classify_system` / `period`
- 所有 Client API 输出：`DataResult`（Phase 0 已实现），`data` 字段为对应 Canonical Object 或其列表
- 空结果：`DataResult.success(data=None/[])` → `freshness="empty"`, `provider="empty"`
- TA-CN MongoDB 不可用：`DataResult.error(...)` → `freshness="empty"`, `provider="error"`, `source_trace=["ta_cn_adapter(error: ...)"]`
- `source_trace`：单 provider 成功为 `["ta_cn_adapter(ok)"]`，失败为 `["ta_cn_adapter(error: ...)"]`
- `freshness`：Phase 1A 固定为 `"delayed"`（非缓存、非实时），由 Phase 1B FreshnessPolicy 覆盖

## 0.2 共享 Mongo / Internal-First 架构基线修订（2026-07-14 Pascal 确认）

以下基线由 Pascal 确认，必须在三层文档（RFC / SPEC / Design）中一致写入，旧语义不能仅靠附注覆盖。

**1. 共享物理数据库**
- Unified Data 与 TA-CN 共用同一物理 MongoDB 数据库 `tradingagents`。
- 不使用物理库隔离；逻辑 ownership 通过集合命名空间前缀实现。

**2. Collection Ownership 隔离**
| 类别 | 集合前缀 | ownership | Unified Data 权限 |
|---|---|---|---|
| TA-CN 既有主集合 | 无前缀 | TA-CN | **只读复用** |
| Unified Data 物化数据 | `03_data_ud_*` | Unified Data | 读写（Phase 1B+） |
| Task Center 元数据 | `10_infra_tc_*` | Task Center | 不读写 |
| Query Cache | `03_data_ud_cache_*` | Unified Data | 读写下短 TTL 缓存 |

Unified Data 绝不回写、覆盖或在 TA-CN 既有无前缀集合中加字段污染。

**3. Internal-First 权威读取路径**
查询时先查共享 Mongo 内部源（TA-CN 既有数据 → UD 物化数据 → Query Cache），内部源全部未命中时再触发外部 Provider（Tushare → AKShare）。外部刷新失败不能阻断已有内部数据读取，必须返回明确的 DataResult 缺失/错误语义。

**4. DSA 不是运行时数据源**
不实现 DSA SQLite / `StockDaily` adapter。DSA 仅在分析/参考中出现。

**5. 三层语义分离**
- TA-CN 既有业务资产（无前缀，ownership: TA-CN）
- Unified Data 可追溯物化数据集（`03_data_ud_*`，非 cache）
- 可丢弃的短 TTL Query Cache（`03_data_ud_cache_*`）

**6. Task Center 先行**
Task Center 的最小 Task / Job / Execution、幂等、重试、执行审计能力须在 Unified Data 物化写入前可用；不创建真实 Job、不启用 cron/systemd 或长期调度。

## 1. 需求摘要

本 SPEC 将 RFC-03-007 中描述的"全局统一数据访问层"落到具体接口签名、数据契约、模块结构和测试矩阵。核心交付物：

1. `SecurityId` 值对象：统一安全标识，支持 A 股 / 港股 / 美股 / Crypto / 指数 / 基金，可从多种代码格式双向转换。
2. `DataResult` 数据类：标准返回结构，包含 data + metadata（provider / fetched_at / data_date / freshness / quality_score / source_trace / warnings）。
3. `DataProvider` 抽象基类与 `Capability` 声明机制：provider 自描述能力，Registry 维护 capability → provider 映射。
4. `ProviderRegistry` 与 `DataRouter`：按 capability 路由请求，管理 fallback 链、审计 metadata。
5. `CacheManager`：MongoDB 优先的缓存层，按数据域 TTL 自动失效。
6. `FreshnessPolicy`：按数据域定义新鲜度策略（realtime / delayed / cached / stale）。
7. MVP 实现：D1 行情、D2 财务、D3 估值、D6 日历、D7 元数据五个域，Tushare + AKShare 两个 provider，A 股优先。

**本 SPEC 不进入 Design 级文件清单。** 具体文件结构、类图、函数签名由后续 Design 阶段产出。

---

## 2. 范围

### 2.1 In Scope

- [ ] `SecurityId` 值对象：`market` + `symbol`，支持 `from_wind_code()` / `from_tushare_code()` / `from_numeric()` / `to_wind_code()` 等转换方法。
- [ ] `DataResult` 数据类：`data` + `security_id` + `domain` + `provider` + `fetched_at` + `data_date` + `freshness` + `quality_score` + `source_trace` + `warnings`。
- [ ] `DataProvider` 抽象基类：`name` 属性 + `capabilities` 属性 + `markets` 属性 + `fetch(domain, operation, security_id, **params)` 方法。
- [ ] `Capability` 声明：格式 `{domain}.{operation}`，如 `market_data.kline_daily`。
- [ ] `ProviderRegistry`：注册 / 查询 / 按 capability 列出 providers。
- [ ] `DataRouter`：按 capability 路由 + fallback 链 + 审计 metadata 记录。
- [ ] `CacheManager`：MongoDB 缓存读写 + TTL 失效 + 强制刷新接口。
- [ ] `FreshnessPolicy`：按数据域定义 TTL 和新鲜度标签规则。
- [ ] MVP Provider：Tushare provider + AKShare provider（A 股行情/财务/估值/日历/元数据）。
- [ ] 查询入口 API：消费方调用的统一函数（如 `get_kline_daily()` / `get_financial()` / `get_calendar()`）。
- [ ] 审计日志：每次查询记录 provider 链 / 耗时 / 结果状态。
- [ ] 单元测试覆盖：SecurityId 转换、DataResult 序列化、Provider 注册/路由、Fallback 切换、Cache 命中/失效、Freshness 标签。
- [ ] 文档同步：新建 `skills/data/unified_data/SKILL.md`。

### 2.2 Out of Scope

- [ ] 不在本次产出 Design 级文件清单（类图、模块文件树、函数签名细节）。
- [ ] 不在本次实现 TA-CN adapter wrapper（阶段 2，长期规划）。
- [ ] **不实现 DSA adapter**：DSA 不是运行时数据源，unified_data 不为 DSA 实现任何 adapter，不纳入 `external_fallback_chains`，不作为 internal source；DSA 仅在分析/参考文档中出现。
- [ ] 不在本次覆盖 D4 资金流、D5 新闻、D8 另类数据、D9 基金（下一阶段）。
- [ ] 不在本次实现实时 WebSocket 行情推送。
- [ ] 不在本次修改 TA-CN / DSA / data-pipeline / data_interface 现有代码。
- [ ] 不在本次新增 MongoDB 集合或修改现有 schema validator。
- [ ] 不在本次实现 provider 性能基准测试。
- [ ] 不在本次实现多市场深度覆盖（港股/美股只做基础日线）。
- [ ] 不在本次实现 Crypto 数据源接入。

---

## 3. 功能规格

### 3.1 SecurityId

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| SID-001 | 构造 SecurityId | `market="CN", symbol="600519"` | `SecurityId` 实例 | market 不在枚举中抛 `ValueError` |
| SID-002 | 从 wind_code 构造 | `"600519.SH"` | `SecurityId("CN", "600519")` | 格式不合法抛 `ValueError` |
| SID-003 | 从 tushare_code 构造 | `"600519.SH"` | `SecurityId("CN", "600519")` | 同上 |
| SID-004 | 从纯数字构造 | `"600519", market="CN"` | `SecurityId("CN", "600519")` | 无法判断市场时抛 `ValueError` |
| SID-005 | 转为 wind_code | `SecurityId("CN", "600519")` | `"600519.SH"` | 不支持的市场返回 None |
| SID-006 | 港股代码构造 | `"00700"` → `SecurityId("HK", "00700")` | SecurityId 实例 | 前导零保留 |
| SID-007 | 美股代码构造 | `"AAPL"` → `SecurityId("US", "AAPL")` | SecurityId 实例 | — |
| SID-008 | 相等与哈希 | 两个相同 SecurityId | `True` / 相同 hash | 可作为 dict key |
| SID-009 | 字符串表示 | `str(SecurityId("CN", "600519"))` | `"CN:600519"` | — |

### 3.2 DataResult

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| DR-001 | 构造成功 DataResult | data=DataFrame, security_id, domain, provider, ... | DataResult 实例 | data 为空 DataFrame 时 `freshness="empty"` |
| DR-002 | 记录 source_trace | fallback 链 `["tushare", "akshare"]` | `source_trace=["tushare(fail)", "akshare(ok)"]` | 单 provider 成功时 `source_trace=["tushare(ok)"]` |
| DR-003 | 记录 warnings | 部分字段缺失 | `warnings=["close is null for 3 rows"]` | 无警告时为空列表 |
| DR-004 | 序列化为 dict | DataResult 实例 | dict（data 转为 records） | DataFrame 不可序列化时抛 `SerializationError` |
| DR-005 | freshness 自动标签 | fetched_at vs data_date vs now | realtime / delayed / cached / stale / empty | 规则由 FreshnessPolicy 定义 |

### 3.3 DataProvider 与 Capability

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| PV-001 | 声明 capability | provider 类属性 `capabilities = {"market_data.kline_daily", ...}` | Registry 可查询 | 重复声明同 capability 不报错（多 provider 允许） |
| PV-002 | 声明市场 | provider 类属性 `markets = {"CN"}` | Router 只路由匹配市场的 provider | 请求不支持的 market 返回空 |
| PV-003 | fetch 调用 | `domain="market_data", operation="kline_daily", security_id=SecurityId("CN","600519"), params={"limit":120}` | `pd.DataFrame` | provider 内部错误抛 `ProviderError` |
| PV-004 | is_available 检查 | 无 | `True` / `False` | token 缺失 / 网络不通时返回 False |
| PV-005 | 不支持的操作 | provider 收到未声明的 capability | 抛 `UnsupportedCapabilityError` | — |

### 3.4 ProviderRegistry 与 DataRouter

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| RG-001 | 注册 provider | `register(TushareProvider)` | Registry 更新 capability → [provider] 映射 | provider name 重复抛 `ValueError` |
| RG-002 | 查询 capability 的 providers | `get_providers("market_data.kline_daily")` | `[TushareProvider, AKShareProvider]`（按优先级） | 无 provider 时返回空列表 |
| RG-003 | 路由请求 | `domain, operation, security_id, params` | `DataResult` | 全部 provider 失败返回 `DataResult.error(...)` |
| RG-004 | Internal-First 路径执行 | 查询先查 TA-CN 既有 → UD 物化 → Query Cache → 外部 Provider `external_fallback_chains` | 第一个命中的数据源结果 | 内部源命中时不触发外部 Provider；外部全部失败返回 DataResult.error，不阻断已有内部数据 |
| RG-005 | 审计记录 | 每次查询 | 写入审计集合：query_id / domain / operation / security_id / provider_chain / elapsed_ms / status | 审计写入失败不影响查询结果（catch-and-log） |
| RG-006 | 强制指定 provider | `provider="tushare"` 参数 | 只走指定 provider，不 fallback | 指定 provider 不可用时抛 `ProviderUnavailableError` |

### 3.5 CacheManager

> **注意**：CacheManager 仅在 internal-first 读取路径的第 3 层（Query Cache）生效。TA-CN 既有集合和 UD 物化集合的查询不经过 CacheManager，由 DataRouter 直接路由到对应 adapter。

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| CA-001 | 缓存读取 | `security_id, domain, params` | 缓存的 DataResult 或 None | 缓存不存在返回 None |
| CA-002 | 缓存写入 | `security_id, domain, params, DataResult` | 无 | MongoDB 写入失败时 catch-and-log，不影响查询 |
| CA-003 | TTL 失效判断 | cached_at vs domain TTL | expired → 返回 None | TTL 由 FreshnessPolicy 定义 |
| CA-004 | 强制刷新 | `force_refresh=True` 参数 | bypass cache，直接调 provider | 强制刷新后写入新缓存 |
| CA-005 | 缓存 key 生成 | security_id + domain + params hash | 确定性 cache key | 相同参数生成相同 key |
| CA-006 | 物化数据写入 | 外部 Provider 成功后的 DataResult | 写入 `03_data_ud_*` 物化集合 | Phase 1B+；与 Query Cache 写入分离；**禁止写入 TA-CN 既有无前缀集合** |

### 3.6 FreshnessPolicy

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| FP-001 | 获取 TTL | `domain="market_data"` | TTL in seconds | 未知 domain 返回默认 3600s |
| FP-002 | 计算新鲜度标签 | fetched_at, data_date, domain, cached | freshness 标签 | 规则见下方 FreshnessPolicy 表 |
| FP-003 | 自定义策略 | config 覆盖默认 TTL | 更新后的 TTL | — |

**FreshnessPolicy 默认规则：**

| 标签 | 条件 |
|---|---|
| `realtime` | fetched_at 距 now < 60s 且非 cached |
| `delayed` | fetched_at 距 now < 15min 且非 cached |
| `cached` | 来自缓存且未过期 |
| `stale` | 来自缓存但已过期（仍返回，但标记） |
| `empty` | data 为空 |

---

## 4. 数据与接口契约

### 4.1 SecurityId

```python
from dataclasses import dataclass
from enum import Enum

class Market(str, Enum):
    CN = "CN"       # A 股
    HK = "HK"       # 港股
    US = "US"       # 美股
    CRYPTO = "CRYPTO"
    INDEX = "INDEX"
    FUND = "FUND"

@dataclass(frozen=True)
class SecurityId:
    """不可变的安全标识值对象"""
    market: Market
    symbol: str

    # 工厂方法
    @classmethod
    def from_wind_code(cls, code: str) -> "SecurityId": ...
    @classmethod
    def from_tushare_code(cls, code: str) -> "SecurityId": ...
    @classmethod
    def from_numeric(cls, code: str, market: Market) -> "SecurityId": ...

    # 转换方法
    def to_wind_code(self) -> str | None: ...
    def to_tushare_code(self) -> str | None: ...

    def __str__(self) -> str:
        return f"{self.market.value}:{self.symbol}"
```

### 4.2 DataResult

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

FreshnessLabel = Literal["realtime", "delayed", "cached", "stale", "empty"]

@dataclass
class DataResult:
    data: Any                      # pd.DataFrame 或 list[dict]
    security_id: SecurityId
    domain: str                    # e.g. "market_data"
    operation: str                 # e.g. "kline_daily"
    provider: str                  # 实际 provider name
    fetched_at: datetime
    data_date: str | None = None   # 业务日期 "YYYY-MM-DD"
    freshness: FreshnessLabel = "cached"
    quality_score: float | None = None
    source_trace: list[str] = field(default_factory=list)  # e.g. ["tushare(fail)", "akshare(ok)"]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict: ...
```

### 4.3 DataProvider

```python
from abc import ABC, abstractmethod

class DataProvider(ABC):
    """数据源抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def capabilities(self) -> set[str]: ...
        """如 {'market_data.kline_daily', 'financial.income_statement'}"""

    @property
    @abstractmethod
    def markets(self) -> set[Market]: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def fetch(
        self,
        domain: str,
        operation: str,
        security_id: SecurityId,
        **params,
    ) -> pd.DataFrame: ...

    def supports(self, capability: str, market: Market) -> bool:
        return capability in self.capabilities and market in self.markets
```

### 4.4 Capability 命名规范

格式：`{domain}.{operation}`

| Capability | 说明 |
|---|---|
| `market_data.kline_daily` | 日线 K 线 |
| `market_data.kline_weekly` | 周线 K 线 |
| `market_data.realtime_quote` | 实时行情快照（读 `market_quotes` 集合） |
| `financial.income_statement` | 利润表 |
| `financial.balance_sheet` | 资产负债表 |
| `financial.cash_flow` | 现金流量表 |
| `valuation.daily_basic` | 每日估值指标（PE/PB/PS） |
| `calendar.trading_days` | 交易日历 |
| `calendar.is_trading_day` | 判断是否交易日 |
| `metadata.stock_list` | 股票列表（读 `stock_basic_info`） |
| `metadata.index_list` | 指数列表（读 TA-CN `index_basic_info`） |
| `metadata.industry_members` | 行业成分股 |
| `metadata.index_members` | 指数成分股 |
| `news.stock_news` | 个股新闻（读 `stock_news` 集合） |

### 4.5 ProviderRegistry

```python
class ProviderRegistry:
    def register(self, provider: DataProvider) -> None: ...
    def get_providers(
        self, capability: str, market: Market | None = None
    ) -> list[DataProvider]: ...
    def list_capabilities(self) -> set[str]: ...
    def list_providers(self) -> list[DataProvider]: ...
```

### 4.6 DataRouter

```python
class DataRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        cache: CacheManager,
        freshness: FreshnessPolicy,
        ta_cn_adapter: "TA_CNMongoAdapter",           # internal-first 第 1 层
        local_mongo_adapter: "LocalMongoAdapter",      # internal-first 第 2 层（UD 物化）
        external_fallback_chains: dict[str, list[str]],  # capability → [provider_name, ...]（仅外部 Provider）
    ): ...

    def query(
        self,
        domain: str,
        operation: str,
        security_id: SecurityId,
        provider: str | None = None,    # 强制指定 provider（跳过 internal-first，仅走外部指定）
        force_refresh: bool = False,
        **params,
    ) -> DataResult: ...
```

> **读取顺序**：TA_CN adapter → LocalMongoAdapter（UD 物化）→ CacheManager → external_fallback_chains。详见 DESIGN-03-007 §8.1。

### 4.7 CacheManager

```python
class CacheManager:
    def __init__(
        self,
        mongo_uri: str | None = None,   # 默认从 .env 加载
        database: str = "tradingagents",
        freshness: FreshnessPolicy | None = None,
    ): ...

    def get(
        self, security_id: SecurityId, domain: str, operation: str, params: dict
    ) -> DataResult | None: ...

    def put(
        self, security_id: SecurityId, domain: str, operation: str, params: dict, result: DataResult
    ) -> None: ...

    def invalidate(
        self, security_id: SecurityId, domain: str | None = None
    ) -> int: ...
```

### 4.8 FreshnessPolicy

```python
class FreshnessPolicy:
    # 默认 TTL（秒）
    DEFAULT_TTLS: dict[str, int] = {
        "market_data": 21600,       # 6h（日线级别）
        "financial": 86400,         # 24h
        "valuation": 43200,         # 12h
        "calendar": 604800,         # 7d
        "metadata": 604800,         # 7d
    }

    def get_ttl(self, domain: str) -> int: ...

    def label(
        self, fetched_at: datetime, data_date: str | None, domain: str, from_cache: bool
    ) -> FreshnessLabel: ...
```

---

## 5. 查询入口 API

消费方通过统一入口函数访问数据。以下为 MVP 阶段暴露的公共 API。

**Phase 1A 范围标注**：标注 `[1A]` 的方法必须在 Phase 1A 由 TA-CN read-only adapter 实现；标注 `[1B+]` 的方法在 Phase 1B 引入外部 provider + cache 后可用。Phase 1A 不实现 `force_refresh`（无缓存层）和 `provider` 参数（无外部 provider）。

```python
# skills/data/unified_data/api.py（伪代码，具体路径由 Design 决定）

from .models import SecurityId, DataResult

# 行情域
def get_kline_daily(  # [1A] 读 stock_daily_quotes
    security_id: SecurityId,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 120,
    adjust: str = "qfq",            # qfq/hfq/none
    provider: str | None = None,    # [1B+]
    force_refresh: bool = False,    # [1B+]
) -> DataResult: ...

def get_realtime_quote(  # [1A] 读 market_quotes
    security_id: SecurityId,
) -> DataResult: ...

# 财务域
def get_income_statement(  # [1A] 读 stock_financial_data
    security_id: SecurityId,
    period: str | None = None,      # 如 "2025Q4"
    provider: str | None = None,    # [1B+]
) -> DataResult: ...

def get_balance_sheet(...) -> DataResult: ...   # [1A]
def get_cash_flow(...) -> DataResult: ...       # [1A]

# 估值域
def get_daily_basic(  # [1B+] 读 stock_basic_info 部分字段 + Tushare daily_basic
    security_id: SecurityId,
    date: str | None = None,
    provider: str | None = None,
) -> DataResult: ...

# 日历域
def get_trading_days(  # [1B+] 需要 Tushare/AKShare 或 exchange_calendar
    market: Market,
    start_date: str,
    end_date: str,
) -> DataResult: ...

def is_trading_day(market: Market, date: str) -> bool: ...  # [1B+]

# 元数据域
def get_stock_list(market: Market) -> DataResult: ...           # [1A] 读 stock_basic_info
def get_stock_info(security_id: SecurityId) -> DataResult: ...  # [1A] 读 stock_basic_info
def get_index_list(market: Market) -> DataResult: ...           # [1A] 读 index_basic_info
def get_index_info(index_id: SecurityId) -> DataResult: ...     # [1A] 读 index_basic_info
def get_index_members(index_id: SecurityId) -> DataResult: ...  # [1B+] 需要外部数据源

# 指数/板块域（读 TA-CN index_basic_info / index_daily_quotes / stock_sector_info）
def get_index_daily(  # [1A] 读 index_daily_quotes
    index_id: SecurityId,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 120,
) -> DataResult: ...
def get_sector_index_bars(  # [1A] 读 index_daily_quotes（申万行业指数）
    sector_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 120,
) -> DataResult: ...
def get_stock_sector(security_id: SecurityId, classify_system: str | None = None) -> DataResult: ...  # [1A] 读 stock_sector_info
def get_stocks_by_sector(sector_code: str, classify_system: str | None = None) -> DataResult: ...      # [1A] 读 stock_sector_info

# 新闻域
def get_news(  # [1A] 读 stock_news
    security_id: SecurityId,
    limit: int = 20,
) -> DataResult: ...
```

---

## 6. Provider 实现规格（MVP）

### 6.1 TushareProvider

| 项 | 值 |
|---|---|
| name | `"tushare"` |
| markets | `{CN}` |
| capabilities | `market_data.kline_daily`, `market_data.realtime_quote`, `financial.income_statement`, `financial.balance_sheet`, `financial.cash_flow`, `valuation.daily_basic`, `calendar.trading_days`, `calendar.is_trading_day`, `metadata.stock_list`, `metadata.index_list`, `metadata.index_members`, `news.stock_news` |
| token 来源 | `.env` → `TUSHARE_TOKEN` |
| is_available | token 存在且非空 |
| fetch 限流 | 遵守 Tushare 频率限制（每分钟 N 次），内置 rate limiter |

### 6.2 AKShareProvider

| 项 | 值 |
|---|---|
| name | `"akshare"` |
| markets | `{CN}` |
| capabilities | `market_data.kline_daily`, `market_data.realtime_quote`, `financial.income_statement`, `financial.balance_sheet`, `financial.cash_flow`, `valuation.daily_basic`, `calendar.trading_days`, `metadata.stock_list`, `metadata.index_list`, `metadata.index_members`, `news.stock_news` |
| 依赖 | `akshare` Python 包 |
| is_available | akshare 可 import |
| fetch 限流 | 内置简单延迟（如 0.5s/次），防封禁 |

### 6.3 默认 External Fallback 链（Internal-First 路径未命中时使用）

> **注意**：以下 fallback 链仅在 internal-first 读取路径（TA-CN 既有 → UD 物化 → Query Cache）全部未命中时触发。外部 Provider 成功后，数据物化写入 `03_data_ud_*` 并写入 Query Cache。

```yaml
external_fallback_chains:
  "market_data.kline_daily": ["tushare", "akshare"]
  "market_data.realtime_quote": ["tushare", "akshare"]
  "financial.income_statement": ["tushare", "akshare"]
  "financial.balance_sheet": ["tushare", "akshare"]
  "financial.cash_flow": ["tushare", "akshare"]
  "valuation.daily_basic": ["tushare", "akshare"]
  "calendar.trading_days": ["tushare", "akshare"]
  "calendar.is_trading_day": ["tushare", "akshare"]
  "metadata.stock_list": ["tushare", "akshare"]
  "metadata.index_list": ["tushare", "akshare"]
  "metadata.index_members": ["tushare", "akshare"]
  "news.stock_news": ["tushare", "akshare"]
```

> DSA 不在 unified_data 的运行时数据源体系中：DSA SQLite / `StockDaily` 不作为 Provider 注册、不写入 `external_fallback_chains`、不被 `DataRouter.query()` 调用。DSA 仅在 unified_data 之外的文档与回测参考中出现。

---

## 7. 配置规格

unified_data 的配置（fallback 链、TTL 覆盖、provider 参数）通过 YAML 或 Python dict 管理：

```yaml
# 伪代码 — 具体路径和格式由 Design 决定
unified_data:
  providers:
    tushare:
      enabled: true
      token_env: "TUSHARE_TOKEN"
      rate_limit_rpm: 200              # 每分钟请求上限
    akshare:
      enabled: true
      request_delay_seconds: 0.5

  external_fallback_chains:            # 仅在 internal-first 路径未命中时使用
    "market_data.kline_daily": ["tushare", "akshare"]
    # ...（见 §6.3）

  cache:
    database: "tradingagents"
    query_cache_prefix: "03_data_ud_cache_"     # Query Cache 集合前缀（可丢弃短 TTL）
    materialized_prefix: "03_data_ud_"          # 物化数据集合前缀（可追溯）
    default_ttl_seconds: 3600

  freshness:
    overrides:
      "market_data": 21600             # 6h
      "financial": 86400               # 24h

  audit:
    enabled: true
    collection: "03_data_ud_query_audit"  # 审计日志集合
```

> **注意**：`collection_prefix: "03_data_03_data_ud_cache_"` 为旧拼写错误，已修正为 `query_cache_prefix: "03_data_ud_cache_"`。

---

## 8. 错误码与异常

| 异常 | 含义 | 触发场景 |
|---|---|---|
| `InvalidSecurityIdError` | SecurityId 格式不合法 | 构造时 market 不在枚举或 symbol 为空 |
| `UnsupportedCapabilityError` | provider 不支持该 capability | provider 收到未声明的操作 |
| `ProviderUnavailableError` | provider 不可用 | token 缺失 / 依赖未安装 / 网络不通 |
| `ProviderError` | provider 内部错误 | API 返回错误 / 解析失败 |
| `AllProvidersFailedError` | **历史/内部类型**：Phase 0 旧基线曾以此异常为 Router 对调用方的全部失败出口。自 Phase 1B-A 起，Router 全部失败时对调用方返回 `DataResult.error(provider="error", source_trace=[...])`，**不抛此异常**。该类保留作内部/历史兼容，不作为 1B+/1C 对外验收语义 | 所有 provider 都抛出异常（内部仍可能构造，但 Router 不外抛） |
| `CacheError` | 缓存读写异常 | MongoDB 连接失败 / 序列化错误（catch-and-log，不向上抛） |
| `SerializationError` | DataResult 序列化失败 | data 包含不可 JSON 序列化的类型 |

---

## 9. 不改动清单（Out of Scope — 禁止修改）

以下文件/目录在 RFC/SPEC 阶段**禁止修改**：

| 路径 | 理由 |
|---|---|
| `skills/apps/TradingAgents-CN/**` | TA-CN 是子项目，本阶段只定义接口边界 |
| `skills/research/daily_stock_analysis/**` | DSA 是独立子系统 |
| `skills/data/data-pipeline/**` | ETL 管道，职责正交 |
| `skills/data/data_interface/**` | RFC-03-003 IReader/IWriter，继续并存 |
| `skills/infra/task_center/**` | 任务中心独立线 |
| `skills/research/stock/**` | stock 框架是消费方，不是本阶段产出 |
| 生产 MongoDB 集合的 schema validator | 不改现有集合约束 |
| cron / systemd / gateway / 外部推送配置 | 不碰调度和推送 |

---

## 10. 测试矩阵

### 10.1 单元测试

| 测试编号 | 测试目标 | 覆盖功能 |
|---|---|---|
| T-001 | SecurityId 构造与转换 | SID-001 ~ SID-009 |
| T-002 | SecurityId 从 wind_code/tushare_code/numeric 构造 | SID-002 ~ SID-004 |
| T-003 | SecurityId 转 wind_code/tushare_code | SID-005 |
| T-004 | SecurityId 相等与哈希 | SID-008 |
| T-005 | DataResult 构造与字段 | DR-001 ~ DR-003 |
| T-006 | DataResult 序列化 | DR-004 |
| T-007 | Provider 注册与查询 | RG-001 ~ RG-002 |
| T-008 | Provider capability 检查 | PV-001, PV-005 |
| T-009 | Router 路由主成功 | RG-003 |
| T-010 | Router fallback 成功 | RG-004 |
| T-011 | Router 全部失败 | RG-003（`DataResult.error(...)`；自 Phase 1B-A 起 Router 不抛 `AllProvidersFailedError`，该异常仅保留为内部/历史类型） |
| T-012 | Router 强制指定 provider | RG-006 |
| T-013 | Cache 命中 | CA-001 |
| T-014 | Cache 未命中 | CA-001（返回 None） |
| T-015 | Cache TTL 过期 | CA-003 |
| T-016 | Cache 强制刷新 | CA-004 |
| T-017 | Freshness 标签计算 | FP-002（5 种标签） |
| T-018 | 审计日志写入 | RG-005 |

### 10.2 集成测试（使用 mock provider）

| 测试编号 | 测试目标 |
|---|---|
| TI-001 | 端到端：query → cache miss → provider → cache write → return |
| TI-002 | 端到端：query → cache hit → return（不调 provider） |
| TI-003 | 端到端：query → provider fail → fallback → success |
| TI-004 | 端到端：query → all providers fail → `DataResult.error(provider="error", source_trace=[...])`（自 Phase 1B-A 起 Router 不外抛 `AllProvidersFailedError`） |

---

## 11. 向后兼容

- 本 SPEC 新建 `skills/data/unified_data/`，不修改任何现有代码，**无破坏性变更**。
- 现有 TA-CN / DSA / data-pipeline / data_interface 不受影响。
- 现有 portfolio MongoDB 集合不受影响。
- unified_data 的物化集合（`03_data_ud_*`）与 Query Cache 集合（`03_data_ud_cache_*`）与 TA-CN 既有无前缀集合、portfolio 业务集合共用同一物理库 `tradingagents`，通过**集合命名空间前缀**（所有权 + 语义层级）逻辑隔离，不依赖物理库隔离。
- unified_data **不实现 DSA adapter**：DSA 仅作为分析/参考上下文存在于文档与回测参考中，不作为 unified_data 的运行时数据源、不出现在 `external_fallback_chains` 中、不在 `DataRouter` 中被路由。

---

## 12. MVP 范围与分阶段 Roadmap

### 12.1 MVP（RFC/SPEC 批准后第一步实现）

- SecurityId + DataResult + DataProvider + Capability + Registry + Router
- CacheManager（MongoDB）+ FreshnessPolicy
- Tushare provider + AKShare provider
- 数据域：D1 行情（日线）+ D2 财务 + D3 估值 + D6 日历 + D7 元数据
- 市场：A 股优先
- 公共查询 API + 单元测试 + 集成测试

### 12.2 Phase 2

- 港股 / 美股基础日线（扩展 SecurityId 转换 + provider market 覆盖）
- D4 资金流域
- BaoStock provider 接入

### 12.3 Phase 3

- TA-CN adapter wrapper（让 TA-CN 通过 unified_data 获取数据）
- ~~DSA adapter wrapper~~ — **不实现**。Pascal 确认（2026-07-14）：DSA 不是运行时数据源，unified_data 不为 DSA 实现任何 adapter；DSA 不出现在 `external_fallback_chains` 中；DSA 仅在分析/参考文档中出现。

### 12.4 Phase 4（远期）

- D5 新闻域 + D8 另类数据 + D9 基金域
- 实时行情推送（WebSocket）
- provider 性能基准与动态优先级

---

## 13. 验收标准

- [ ] RFC 文件存在于 `docs/rfc/03_data/RFC-03-007-*.md`，明确业务价值、架构边界、目标/非目标和风险。
- [ ] SPEC 文件存在于 `docs/spec/03_data/SPEC-03-007-*.md`，明确可执行、可测试的工程契约。
- [ ] SPEC 不进入 Design 级文件清单（无类图、无模块文件树、无函数实现细节）。
- [ ] **共享 Mongo / internal-first 边界**：SPEC 明确说明 Unified Data 与 TA-CN 共用同一物理库 `tradingagents`，通过命名空间前缀（TA-CN 无前缀 / `03_data_ud_*` / `03_data_ud_cache_*`）实现所有权，不依赖物理库隔离；权威读取路径为 internal-first。
- [ ] **不实现 DSA adapter**：SPEC 明确不实现 DSA SQLite / `StockDaily` adapter，DSA 不在 `external_fallback_chains` 中，DSA 仅在分析/参考上下文中出现。
- [ ] **Collection Ownership 不可回写**：SPEC 明确 Unified Data 绝不回写、覆盖或加字段污染 TA-CN 既有无前缀集合。
- [ ] 明确 `unified_data` 与 `data-pipeline`、`task_center`、`stock` 的边界。
- [ ] 中文输出，专业简洁。

---

## 14. 后续 Design 拆分建议

| Design 子阶段 | 建议内容 |
|---|---|
| Design-A | 核心抽象设计：SecurityId / DataResult / DataProvider / Capability / Registry / Router 的类图与方法签名 |
| Design-B | Cache + Freshness + Audit 设计：MongoDB 集合结构、TTL 策略、审计日志格式 |
| Design-C | MVP Provider 设计：Tushare provider + AKShare provider 的 capability 映射与 fetch 实现 |
| Design-D | 公共查询 API 设计：`api.py` 函数签名、参数规范、返回格式约定 |

可合并为一份 Design 文档，也可按子阶段拆分。

---

## 15. 开放问题

（继承自 RFC §12，部分已在 2026-07-14 架构基线修订中解决，见 §0.2）

1. ~~Crypto 数据源是否纳入 MVP？~~ — 仍未纳入 MVP，Phase 6+ 决策。
2. ~~MVP 实时行情深度（免费 API vs 仅日线）？~~ — 仍未决策。
3. ~~缓存集合命名前缀？~~ — **已解决（2026-07-14）**：Query Cache = `03_data_ud_cache_*`，物化数据 = `03_data_ud_*`。
4. ~~Provider 凭据统一管理策略？~~ — 仍未决策，Phase 1B 处理。
5. ~~SecurityId 转换映射持久化？~~ — 纯内存计算，不持久化。

---

## 16. 参考资料

- RFC-03-007：`docs/rfc/03_data/RFC-03-007-unified-data-layer.md`
- RFC-03-003：数据架构标准
- SPEC-03-006：Smart Money OCR Provider Fallback（provider fallback 设计参考）
- TA-CN 数据源：`skills/apps/TradingAgents-CN/app/services/data_sources/`
- DSA 数据源：`skills/research/daily_stock_analysis/data_provider/`
- data-pipeline：`skills/data/data-pipeline/SKILL.md`
