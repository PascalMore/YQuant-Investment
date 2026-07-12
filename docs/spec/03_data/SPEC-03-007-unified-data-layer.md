# SPEC-03-007: YQuant Unified Data Layer

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-12 |
| 最后更新 | 2026-07-12 |
| 来源 RFC | RFC-03-007 |
| 目标模块 | unified_data（全局数据访问层） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |
| 关联 RFC | RFC-03-003（数据架构）、RFC-00-001（全局架构） |
| 关联 SPEC | SPEC-03-004、SPEC-03-005、SPEC-03-006 |

---


## 0. Design 阶段修订说明（2026-07-12）

根据 Pascal 后续确认，unified_data 新增持久化集合统一使用 MongoDB `03_data_ud_*` 前缀；DSA 既有 SQLite 仅作为只读 legacy source adapter，不作为 unified_data 新增持久化后端。实现阶段不得新增 SQLite 存储路径。

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
- [ ] 不在本次实现 TA-CN adapter wrapper（阶段 2）。
- [ ] 不在本次实现 DSA adapter wrapper（阶段 3）。
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
| RG-003 | 路由请求 | `domain, operation, security_id, params` | `DataResult` | 全部 provider 失败抛 `AllProvidersFailedError` |
| RG-004 | Fallback 链执行 | provider 链 `[tushare → akshare → baostock]` | 第一个成功的 provider 结果 | 每次尝试记录 attempt metadata |
| RG-005 | 审计记录 | 每次查询 | 写入审计集合：query_id / domain / operation / security_id / provider_chain / elapsed_ms / status | 审计写入失败不影响查询结果（catch-and-log） |
| RG-006 | 强制指定 provider | `provider="tushare"` 参数 | 只走指定 provider，不 fallback | 指定 provider 不可用时抛 `ProviderUnavailableError` |

### 3.5 CacheManager

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| CA-001 | 缓存读取 | `security_id, domain, params` | 缓存的 DataResult 或 None | 缓存不存在返回 None |
| CA-002 | 缓存写入 | `security_id, domain, params, DataResult` | 无 | MongoDB 写入失败时 catch-and-log，不影响查询 |
| CA-003 | TTL 失效判断 | cached_at vs domain TTL | expired → 返回 None | TTL 由 FreshnessPolicy 定义 |
| CA-004 | 强制刷新 | `force_refresh=True` 参数 | bypass cache，直接调 provider | 强制刷新后写入新缓存 |
| CA-005 | 缓存 key 生成 | security_id + domain + params hash | 确定性 cache key | 相同参数生成相同 key |

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
| `market_data.realtime_quote` | 实时行情快照 |
| `financial.income_statement` | 利润表 |
| `financial.balance_sheet` | 资产负债表 |
| `financial.cash_flow` | 现金流量表 |
| `valuation.daily_basic` | 每日估值指标（PE/PB/PS） |
| `calendar.trading_days` | 交易日历 |
| `calendar.is_trading_day` | 判断是否交易日 |
| `metadata.stock_list` | 股票列表 |
| `metadata.industry_members` | 行业成分股 |
| `metadata.index_members` | 指数成分股 |

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
        fallback_chains: dict[str, list[str]],  # capability → [provider_name, ...]
    ): ...

    def query(
        self,
        domain: str,
        operation: str,
        security_id: SecurityId,
        provider: str | None = None,    # 强制指定 provider
        force_refresh: bool = False,
        **params,
    ) -> DataResult: ...
```

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

消费方通过统一入口函数访问数据。以下为 MVP 阶段暴露的公共 API：

```python
# skills/data/unified_data/api.py（伪代码，具体路径由 Design 决定）

from .models import SecurityId, DataResult

# 行情域
def get_kline_daily(
    security_id: SecurityId,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 120,
    adjust: str = "qfq",            # qfq/hfq/none
    provider: str | None = None,
    force_refresh: bool = False,
) -> DataResult: ...

# 财务域
def get_income_statement(
    security_id: SecurityId,
    period: str | None = None,      # 如 "2025Q4"
    provider: str | None = None,
) -> DataResult: ...

def get_balance_sheet(...) -> DataResult: ...
def get_cash_flow(...) -> DataResult: ...

# 估值域
def get_daily_basic(
    security_id: SecurityId,
    date: str | None = None,
    provider: str | None = None,
) -> DataResult: ...

# 日历域
def get_trading_days(
    market: Market,
    start_date: str,
    end_date: str,
) -> DataResult: ...

def is_trading_day(market: Market, date: str) -> bool: ...

# 元数据域
def get_stock_list(market: Market) -> DataResult: ...
def get_index_members(index_id: SecurityId) -> DataResult: ...
```

---

## 6. Provider 实现规格（MVP）

### 6.1 TushareProvider

| 项 | 值 |
|---|---|
| name | `"tushare"` |
| markets | `{CN}` |
| capabilities | `market_data.kline_daily`, `market_data.realtime_quote`, `financial.income_statement`, `financial.balance_sheet`, `financial.cash_flow`, `valuation.daily_basic`, `calendar.trading_days`, `calendar.is_trading_day`, `metadata.stock_list`, `metadata.index_members` |
| token 来源 | `.env` → `TUSHARE_TOKEN` |
| is_available | token 存在且非空 |
| fetch 限流 | 遵守 Tushare 频率限制（每分钟 N 次），内置 rate limiter |

### 6.2 AKShareProvider

| 项 | 值 |
|---|---|
| name | `"akshare"` |
| markets | `{CN}` |
| capabilities | `market_data.kline_daily`, `market_data.realtime_quote`, `financial.income_statement`, `financial.balance_sheet`, `financial.cash_flow`, `valuation.daily_basic`, `calendar.trading_days`, `metadata.stock_list`, `metadata.index_members` |
| 依赖 | `akshare` Python 包 |
| is_available | akshare 可 import |
| fetch 限流 | 内置简单延迟（如 0.5s/次），防封禁 |

### 6.3 默认 Fallback 链

```yaml
fallback_chains:
  "market_data.kline_daily": ["tushare", "akshare"]
  "market_data.realtime_quote": ["tushare", "akshare"]
  "financial.income_statement": ["tushare", "akshare"]
  "financial.balance_sheet": ["tushare", "akshare"]
  "financial.cash_flow": ["tushare", "akshare"]
  "valuation.daily_basic": ["tushare", "akshare"]
  "calendar.trading_days": ["tushare", "akshare"]
  "calendar.is_trading_day": ["tushare", "akshare"]
  "metadata.stock_list": ["tushare", "akshare"]
  "metadata.index_members": ["tushare", "akshare"]
```

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

  fallback_chains:
    "market_data.kline_daily": ["tushare", "akshare"]
    # ...（见 §6.3）

  cache:
    database: "tradingagents"
    collection_prefix: "03_data_03_data_ud_cache_"     # 缓存集合前缀
    default_ttl_seconds: 3600

  freshness:
    overrides:
      "market_data": 21600             # 6h
      "financial": 86400               # 24h

  audit:
    enabled: true
    collection: "ud_audit_log"         # 审计日志集合
```

---

## 8. 错误码与异常

| 异常 | 含义 | 触发场景 |
|---|---|---|
| `InvalidSecurityIdError` | SecurityId 格式不合法 | 构造时 market 不在枚举或 symbol 为空 |
| `UnsupportedCapabilityError` | provider 不支持该 capability | provider 收到未声明的操作 |
| `ProviderUnavailableError` | provider 不可用 | token 缺失 / 依赖未安装 / 网络不通 |
| `ProviderError` | provider 内部错误 | API 返回错误 / 解析失败 |
| `AllProvidersFailedError` | fallback 链全部失败 | 所有 provider 都抛出异常 |
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
| T-011 | Router 全部失败 | RG-003（AllProvidersFailedError） |
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
| TI-004 | 端到端：query → all providers fail → AllProvidersFailedError |

---

## 11. 向后兼容

- 本 SPEC 新建 `skills/data/unified_data/`，不修改任何现有代码，**无破坏性变更**。
- 现有 TA-CN / DSA / data-pipeline / data_interface 不受影响。
- 现有 portfolio MongoDB 集合不受影响。
- unified_data 的缓存集合使用 `03_data_ud_cache_` 前缀，与 portfolio 集合隔离。

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
- DSA adapter wrapper

### 12.4 Phase 4（远期）

- D5 新闻域 + D8 另类数据 + D9 基金域
- 实时行情推送（WebSocket）
- provider 性能基准与动态优先级

---

## 13. 验收标准

- [ ] RFC 文件存在于 `docs/rfc/03_data/RFC-03-007-*.md`，明确业务价值、架构边界、目标/非目标和风险。
- [ ] SPEC 文件存在于 `docs/spec/03_data/SPEC-03-007-*.md`，明确可执行、可测试的工程契约。
- [ ] SPEC 不进入 Design 级文件清单（无类图、无模块文件树、无函数实现细节）。
- [ ] 明确 `unified_data` 与 `data-pipeline`、`task_center`、`stock` 的边界。
- [ ] 明确 TA-CN / DSA 后续 adapter 迁移边界（阶段 2/3，不在 MVP 内）。
- [ ] 明确后续 Design 分阶段建议。
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

（继承自 RFC §12，Design 阶段决策）

1. Crypto 数据源是否纳入 MVP？
2. MVP 实时行情深度（免费 API vs 仅日线）？
3. 缓存集合命名前缀（`03_data_03_data_ud_cache_*`）？
4. Provider 凭据统一管理策略？
5. SecurityId 转换映射持久化（`security_master` 集合）？

---

## 16. 参考资料

- RFC-03-007：`docs/rfc/03_data/RFC-03-007-unified-data-layer.md`
- RFC-03-003：数据架构标准
- SPEC-03-006：Smart Money OCR Provider Fallback（provider fallback 设计参考）
- TA-CN 数据源：`skills/apps/TradingAgents-CN/app/services/data_sources/`
- DSA 数据源：`skills/research/daily_stock_analysis/data_provider/`
- data-pipeline：`skills/data/data-pipeline/SKILL.md`
