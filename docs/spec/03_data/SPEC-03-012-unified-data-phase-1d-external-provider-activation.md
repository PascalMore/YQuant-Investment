# SPEC-03-012: Unified Data Phase 1D — CN 日线真实外部 Provider 激活

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Final |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-18 |
| 最后更新 | 2026-07-20 |
| 来源 RFC | RFC-03-012（Phase 1D External Provider Activation） |
| 关联 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-008（Phase 1B-A 查询平面）、RFC-03-009（Phase 1B-B 持久化缓存平面）、RFC-03-011（Phase 2 质量与审计治理） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-008（Phase 1B-A 查询平面）、SPEC-03-009（Phase 1B-B 持久化缓存平面） |
| 关联 Design | DESIGN-03-012（Phase 1D CN 日线真实外部 Provider 激活，已交付） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 版本号 | V0.2 |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

### 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.2 | 2026-07-20 | T1 收口定稿。基于当前代码库事实：48 项测试全 PASS、DESIGN-03-012 已交付；SPEC 状态更新为 Final；§10 验收标准全部 ✅；§12 待决项已由 Design 解决并引用 DESIGN-03-012；§2 In/Out of Scope 标记确认。 | YQuant-Principal |
| V0.1 | 2026-07-18 | 初始创建。将 Phase 1D 真实外部 Provider 激活需求落为可执行契约，定义 Tushare 主源 + AKShare 兜底的 `market_data.kline_daily` 激活行为、字段映射表、HTTP 客户端抽象、失败/降级矩阵、测试矩阵、不改动清单。移交 7 项待决项给 Design 阶段。 | YQuant-Principal |

---

## 0. 术语对齐与基线锚定

本 SPEC 继承 RFC-03-007 / SPEC-03-007 / SPEC-03-008 的全部基线，不重述背景，只锁定 Phase 1D 必须一致的措辞：

- **Phase 1D** = External Provider Activation。**不得**称「Phase 1B-B」（1B-B 已由 RFC-03-009 锁定为持久化缓存平面）。1B-A provider stub docstring 已由 Phase 1D 实现同步更新。
- **首批（也是唯一）激活能力** = `market_data.kline_daily`，market = `CN`。Tushare 其余 12 条 capability、AKShare 其余 6 条 capability **保持 stub**（返回 `_stub_columns.stub_dataframe_for(...)` 空壳 DataFrame，行为同 Phase 1B-A）。
- **external_fallback_chains**（`kline_daily`）= `["tushare", "akshare"]`，沿用 Phase 1B-A 默认配置，不改。
- **internal-first 优先级**（`kline_daily`）：Step 1 TA-CN（只读，不变）→ Step 2/3 占位跳过 → Step 4 外部 fallback。`force_refresh=True` 跳过 Step 1；`provider="tushare"` / `"akshare"` forced 分支跳过 Step 1/2/3 且不 fallback。
- **canonical 输出对象** = `DailyBar`（Phase 1A 已定义于 `skills/data/unified_data/models/domain/market_data.py`）。本 SPEC 不修改 `DailyBar` 签名。
- **DataResult 语义**：`provider` ∈ `{"tushare", "akshare", "ta_cn_internal", "empty", "error"}`；`freshness` 由既有 `FreshnessPolicy.label(...)` 计算；`quality_score` 在 Phase 1D **恒为 `None`**（Phase 2 QualityScorer 才填充）。
- **单位差异（已知风险，本阶段不归一化）**：Tushare `vol`=手、`amount`=千元；AKShare `成交量`=股、`成交额`=元；TA-CN `stock_daily_quotes` 单位由 TA-CN 决定。Phase 1D 的 `_to_canonical` **透传 provider 原生单位**，消费方自负跨源换算责任。单位 warnings 当前为 no-op（DESIGN §3.7 裁定）。

### 0.1 与 SPEC-03-007 / SPEC-03-008 的关系

本 SPEC 是 SPEC-03-008（Phase 1B-A 查询平面）的**激活态细化**，不替代它：

- SPEC-03-008 定义了 provider 类骨架、`is_available()`、RateLimiter、重试框架、Router internal-first 编排、`external_fallback_chains`、`DataResult` 语义——**全部沿用**。
- 本 SPEC 只对 `kline_daily` 的 `fetch()`（stub → 真实）、`_to_canonical()`（no-op → Tushare/AKShare 列映射）、可注入 HTTP 客户端抽象制定可执行契约。
- SPEC-03-009（1B-B 持久化）、SPEC-03-011（Phase 2 质量审计）的组件在本阶段**不注入、不启用**。

### 0.2 六项不变量逐条对应（RFC-03-007 §14 / SPEC-03-007 §0.2）

| # | 不变量 | Phase 1D SPEC 落点 |
|---|---|---|
| 1 | 共享物理数据库 `tradingagents` | §7.3 不改动清单：不新增集合；TA-CN adapter 只读复用 |
| 2 | Internal-First 读取路径 | §3.1 EP-101~103：kline_daily 真实外部调用只在 Step 4 / forced 分支 |
| 3 | DSA 不是运行时数据源 | §4.2 external_fallback_chains 只含 tushare/akshare |
| 4 | Collection Ownership 不可回写 | §7.3：不写任何集合 |
| 5 | Task Center 先行 | §2.2 Out of Scope：不实现 Task Center |
| 6 | 三层语义分离 | §4.bis 无持久化：不触碰 `03_data_ud_*` / `03_data_ud_cache_*` |

---

## 1. 需求摘要

将 RFC-03-012 的真实外部 Provider 激活需求落为可执行契约，核心交付 4 件事：

1. **TushareProvider.fetch(kline_daily)**：从 stub 改为经**可注入 HTTP 客户端**调用 Tushare `daily` 接口，`_to_canonical()` 实现 Tushare 列 → `list[DailyBar]` 映射。
2. **AKShareProvider.fetch(kline_daily)**：同上，经可注入 HTTP 客户端调用 AKShare `stock_zh_a_hist`，`_to_canonical()` 实现 AKShare 中文列 → `list[DailyBar]` 映射。
3. **HTTP 客户端抽象**：新增轻量客户端接口（`KlineClient` Protocol），封装真实 SDK 调用；提供 `FakeKlineClient` 用于单测。
4. **既有 Router / Registry / FreshnessPolicy / UnifiedDataClient 完全复用**：不改它们的签名与行为；激活只发生在 provider 内部。

全部组件用 fake HTTP 客户端 + 可注入环境变量验证，**不依赖真实 Tushare token、真实 AKShare 网络、真实 Mongo 写入**。真实网络 smoke 是后续受 Pascal 单独授权的受控验证项（§9.3）。

---

## 2. 范围

### 2.1 In Scope

- [x] TushareProvider：`kline_daily` 的 `fetch()` 改为真实调用路径（经可注入 HTTP 客户端）；`_to_canonical()` 实现 Tushare 列 → `list[DailyBar]`；其余 12 capability 保持 stub。
- [x] AKShareProvider：`kline_daily` 的 `fetch()` 同上；`_to_canonical()` 实现 AKShare 列 → `list[DailyBar]`；其余 6 capability 保持 stub。
- [x] HTTP 客户端抽象：`KlineClient` Protocol + `FakeKlineClient`（测试用）+ `TushareKlineClient` + `AKShareKlineClient`。
- [x] 字段映射契约：Tushare / AKShare 原始列 → `DailyBar` 精确映射表（§4.3），含日期格式、单位、空值、缺失列处理。
- [x] 确定性行为：空结果、字段缺失、超时、限流、重试、可用性判定、双源失败的终态 `DataResult` 全部可执行、可测试。
- [x] `DataResult` 的 `provider` / `source_trace` / `warnings` / `quality_score` 在真实调用路径下与 Phase 1B-A / Phase 2 契约一致（`quality_score` 恒 `None`）。
- [x] 全量文件清单（新增 / 修改 / 测试）精确到文件路径（§8）。
- [x] fake HTTP 客户端测试矩阵覆盖全部行为契约（§9）。

### 2.2 Out of Scope（Phase 1D 不做）

- [x] 不激活 Tushare 其余 12 条 capability（kline_weekly / adj_factor / financial 三表 / daily_basic / calendar / metadata / news）。
- [x] 不激活 AKShare 其余 6 条 capability。
- [x] 不实现 Sector Router（DESIGN-03-010 已明确不在范围）。
- [x] 不做生产副作用：无 MongoDB DDL / 真实 Mongo 写入 / materialization 写入 / cache 写入 / AuditLogger 真实写入 / QualitySummary 启用 / cron/systemd/webhook。
- [x] 不把真实网络 smoke 作为本卡或实现卡的执行前提（§9.3）。
- [x] 不归一化跨源单位（Tushare 手/千元 vs AKShare 股/元）——消费方自负换算（OQ-2）。
- [x] 不改造 `datetime.utcnow()` 技术债（§7.4 / OQ-3）。
- [x] 不修改 `SecurityId` / `DataResult` / `Market` / `Capability` / `DailyBar` / `FreshnessPolicy` 公共契约。
- [x] 不修改 `DataRouter` / `ProviderRegistry` / `UnifiedDataClient` / `TA_CNMongoAdapter` 代码。
- [x] 不修改 TA-CN 子项目代码（`skills/apps/TradingAgents-CN/**`）与 TA-CN 无前缀集合。
- [x] 不修改 Phase 1A 的 14 个域入口方法行为（继续直连 TA-CN adapter）。
- [x] 不修改 RFC/SPEC/Design 文档模板（编排层不改模板，P-7）。
- [x] 不修改 RFC-03-012（本卡只产出 SPEC）。

---

## 3. 功能规格

### 3.1 Provider 行为规格（kline_daily 激活）

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| EP-101 | TushareProvider.fetch(kline_daily) 真实路径 | `domain="market_data", operation="kline_daily", security_id, **params`（params 含 `start_date`/`end_date`/`limit`，均可选） | `list[DailyBar]`（经 `_to_canonical` 转换） | is_available()=False → `ProviderUnavailableError`；HTTP 异常 → `ProviderUnavailableError`/`ProviderError`；空 payload → raise `ProviderUnavailableError`（DESIGN §3.6） |
| EP-102 | AKShareProvider.fetch(kline_daily) 真实路径 | 同上 | `list[DailyBar]` | 同上 |
| EP-103 | Provider.fetch 非 kline_daily capability | 任意非 kline_daily capability | 行为同 Phase 1B-A stub（返回 `stub_dataframe_for(...)` 空壳 DataFrame） | 不发网络请求 |
| EP-104 | 空结果处理 | HTTP 客户端返回空 DataFrame / 空 list | `_to_canonical` 产出 `[]` → fetch **raise** `ProviderUnavailableError`（DESIGN §3.6） | Router 视为 unavailable，继续 fallback |
| EP-105 | 字段缺失处理 | raw_df 缺关键字段（`close` 或 `trade_date`） | 该行丢弃，不计入 list | 缺失列（整个 raw_df 无 `vol` 列）→ 非关键列 None，关键列 raise ProviderError（§4.3） |
| EP-106 | RateLimiter 激活 | 每次 kline_daily fetch 前 | `RateLimiter.acquire()`（沿用 1B-A 框架） | 真实网络下验证；超限等待 |
| EP-107 | 重试激活 | HTTP 异常（超时/5xx） | 指数退避重试（沿用 1B-A 框架）；`ProviderUnavailableError` 不重试（DESIGN §3.8） | 配额耗尽（429 类）不重试，直接 `ProviderUnavailableError` |
| EP-108 | is_available 不变 | 无 | Tushare: token 存在 + import；AKShare: import | 不做网络探测（沿用 1B-A） |

> **EP-103 关键约束**：激活必须**严格限定** `kline_daily`。实现须在 `fetch()` 入口按 capability 分支：`kline_daily` 走真实路径，其余走既有 `_stub_columns.stub_dataframe_for()` + `_to_canonical`（no-op）路径。**不得**对其余 capability 发网络请求。

### 3.2 HTTP 客户端抽象行为

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| HC-101 | 客户端接口 get_kline_daily | `security_id, start_date?, end_date?, limit?` | `pd.DataFrame`（provider 原生列） | 超时 → `ProviderUnavailableError`；API 错误 → `ProviderError`；空 → 空 DataFrame |
| HC-102 | 可注入 | provider 构造参数 `http_client: KlineClient | None` | None 时用默认真实客户端；非 None 时用注入客户端 | 测试注入 FakeKlineClient |
| HC-103 | FakeKlineClient | 配置返回的 DataFrame / 异常 | 按 fixture 返回 | 不发网络 |
| HC-104 | TushareKlineClient | token（经 provider 从环境变量读取后注入） | 调 `tushare.pro_api(token).daily(...)` | lazily import；异常脱敏（P-10） |
| HC-105 | AKShareKlineClient | 无 token | 调 `akshare.stock_zh_a_hist(symbol, period="daily", adjust="")` | lazily import；limit 参数被忽略（由 provider 层截断） |

---

## 4. 数据与接口契约

### 4.1 Provider fetch 签名（激活态，kline_daily 分支）

TushareProvider / AKShareProvider 的 `fetch()` 签名**不变**（Phase 1B-A 已定）：

```python
def fetch(
    self,
    domain: str,
    operation: str,
    security_id: "SecurityId",
    **params: Any,
) -> "pd.DataFrame" | list["DailyBar"]:  # kline_daily 分支返回 list[DailyBar]；其余分支返回 pd.DataFrame（stub）
```

> **返回类型差异**：kline_daily 分支返回 `list[DailyBar]`（canonical），其余 capability 分支返回 `pd.DataFrame`（stub，沿用 1B-A）。Router 的 `provider.fetch(...)` 调用点（`router.py:906`）透明包装返回值到 `DataResult.data`。已确认与 TA-CN 路径的 `get_daily_bars` 返回类型一致。

### 4.2 external_fallback_chains（kline_daily，不改）

```yaml
unified_data:
  external_fallback_chains:
    "market_data.kline_daily": ["tushare", "akshare"]   # 沿用 1B-A 默认，不改
```

### 4.3 字段映射契约（Tushare / AKShare → DailyBar）

#### 4.3.1 Tushare `daily` → DailyBar

Tushare `daily` 接口返回列（Tushare 官方）：`ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount`。

| DailyBar 字段 | Tushare 列 | 转换 | 单位 | 缺失处理 |
|---|---|---|---|---|
| `symbol` | `ts_code` | 去后缀（`"600519.SH"` → `"600519"`） | 6 位代码 | 必填；缺失→抛 `ProviderError` |
| `trade_date` | `trade_date` | 透传（`"YYYYMMDD"`） | YYYYMMDD | 必填；缺失→抛 `ProviderError`；行值空→该行丢弃 |
| `open` | `open` | `_f()` | 元 | None |
| `high` | `high` | `_f()` | 元 | None |
| `low` | `low` | `_f()` | 元 | None |
| `close` | `close` | `_f()` | 元 | 关键字段；None→该行丢弃 |
| `pre_close` | `pre_close` | `_f()` | 元 | None |
| `change` | `change` | `_f()` | 元 | None |
| `pct_chg` | `pct_chg` | `_f()` | 百分比（已×100） | None |
| `volume` | `vol` | `_f()` | **手**（1手=100股） | None |
| `amount` | `amount` | `_f()` | **千元** | None |
| `turnover_rate` | — | `None`（daily 不提供） | — | 恒 None |
| `volume_ratio` | — | `None` | — | 恒 None |

#### 4.3.2 AKShare `stock_zh_a_hist` → DailyBar

AKShare `stock_zh_a_hist` 返回列（中文）：`日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率`。

| DailyBar 字段 | AKShare 列 | 转换 | 单位 | 缺失处理 |
|---|---|---|---|---|
| `symbol` | 入参 `security_id.symbol` | 透传 | 6 位代码 | 必填 |
| `trade_date` | `日期` | `"YYYY-MM-DD"` → `"YYYYMMDD"`（去横杠） | YYYYMMDD | 必填；缺失→抛 `ProviderError`；行值空→丢弃 |
| `open` | `开盘` | `_f()` | 元 | None |
| `high` | `最高` | `_f()` | 元 | None |
| `low` | `最低` | `_f()` | 元 | None |
| `close` | `收盘` | `_f()` | 元 | 关键字段；None→该行丢弃 |
| `pre_close` | — | `close - 涨跌额`（若 `涨跌额` 可用）或 `None` | 元 | None |
| `change` | `涨跌额` | `_f()` | 元 | None |
| `pct_chg` | `涨跌幅` | `_f()` | 百分比 | None |
| `volume` | `成交量` | `_f()` | **股**（非手！） | None |
| `amount` | `成交额` | `_f()` | **元**（非千元！） | None |
| `turnover_rate` | `换手率` | `_f()` | 百分比 | None |
| `volume_ratio` | — | `None` | — | 恒 None |

> **trade_date 统一为 YYYYMMDD**（DESIGN §3.4.2 裁定）：AKShare 原生返回 `"YYYY-MM-DD"`，Phase 1D 统一去横杠转 `YYYYMMDD`，与 TA-CN 路径一致。消费方无需判断格式。

> **AKShare limit 截断**（DESIGN §3.4.2）：`stock_zh_a_hist` 不支持 `limit`，由 provider 的 `_to_canonical` 在产出 list 后截断。

#### 4.3.3 空值与缺失列统一规则

- **行级空值**：任一 OHLCV 字段为 `None`/`NaN`/空字符串 → DailyBar 对应字段 `None`（复用 Phase 1A `_f()` helper 语义）。
- **行丢弃**：`close` 或 `trade_date` 为空 → 该行丢弃，不计入 list。
- **列缺失（整个 raw_df 无该列）**：非关键字段（如 `pre_close`/`turnover_rate`）→ DailyBar 对应字段 `None`；关键列（`close`/`trade_date`/`ts_code` or `日期`）缺失 → 抛 `ProviderError("missing required column: {col}")`，由 Router 视为 provider 失败并 fallback。
- **整 raw_df 空**：`_to_canonical` 返回空 list → fetch 抛 `ProviderUnavailableError`（DESIGN §3.6 适配 Router L809）。

> **单位警示**：DESIGN §3.7 裁定——单位差异通过文档标注（本 SPEC §0 + 表 4.3.1/4.3.2），**不注入 DataResult.warnings**（Router 不改约束下无法干净注入）。`emit_unit_warning` 构造参数保留为未来扩展点，当前版本为 no-op。

### 4.4 HTTP 客户端抽象接口契约

```python
from typing import Protocol, Any
import pandas as pd

class KlineClient(Protocol):
    """可注入的 kline_daily HTTP 客户端抽象（Phase 1D）。

    实现者（同居 kline_client.py）：
    - TushareKlineClient：生产，延迟 import tushare，调 pro_api(token).daily(...)
    - AKShareKlineClient：生产，延迟 import akshare，调 stock_zh_a_hist(adjust="")
    - FakeKlineClient：测试，按 fixture 返回，不读环境变量

    所有实现**不得**在异常信息中泄露 token。
    """

    def get_kline_daily(
        self,
        security_id: "SecurityId",
        start_date: str | None = None,   # YYYYMMDD（统一格式）
        end_date: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """返回 provider 原生列的 DataFrame。

        Raises:
            ProviderUnavailableError: 网络/超时/配额耗尽
            ProviderError: API 内部错误 / 缺失关键列
        """
        ...
```

**provider 构造参数扩展**（向后兼容，新增可选参数）：

```python
class TushareProvider(BaseExternalProvider):
    def __init__(
        self,
        *,
        rate_limit_rpm: int = 200,           # 沿用 1B-A
        retry_max_attempts: int = 3,         # 沿用 1B-A
        retry_backoff_base: float = 1.0,     # 沿用 1B-A
        token_env: str = DEFAULT_TOKEN_ENV,  # 沿用 1B-A
        http_client: KlineClient | None = None,        # [1D 新增] None → 默认 TushareKlineClient（延迟构造）
        request_timeout_seconds: float = 30.0,         # [1D 新增]
        emit_unit_warning: bool = True,                # [1D 新增] 当前为 no-op（DESIGN §3.7）
    ) -> None: ...

class AKShareProvider(BaseExternalProvider):
    def __init__(
        self,
        *,
        rate_limit_rpm: int = 200,
        retry_max_attempts: int = 3,
        retry_backoff_base: float = 1.0,
        http_client: KlineClient | None = None,        # [1D 新增] None → 默认 AKShareKlineClient
        request_timeout_seconds: float = 30.0,
        emit_unit_warning: bool = True,                # [1D 新增] 当前为 no-op
    ) -> None: ...
```

> `request_timeout_seconds` / `rate_limit_rpm` / `retry_*` 的具体默认值（30.0 / 200 / 3 / 1.0）是 SPEC 给出的**初始默认**，DESIGN 已确认。实现从 `config.yaml` 对应字段读取或经构造参数注入，不硬编码在调用处（P-3）。

### 4.5 错误/降级矩阵（DataResult 终态，kline_daily）

| 场景 | `provider` | `freshness` | `source_trace` | `warnings` | `quality_score` |
|---|---|---|---|---|---|
| Tushare 成功 | `"tushare"` | `FreshnessPolicy.label(...)` | `["tushare(ok)"]` | `[]`（单位提示 no-op） | `None` |
| AKShare 兜底成功 | `"akshare"` | `label(...)` | `["tushare(unavailable: ...)", "akshare(ok)"]` | Router 既有 warnings | `None` |
| Tushare 异常 + AKShare 成功 | `"akshare"` | `label(...)` | `["tushare(error: ...)", "akshare(ok)"]` | 同上 | `None` |
| 两源全不可用 | `"error"` | `"empty"` | `["tushare(skipped: unavailable)", "akshare(skipped: unavailable)"]` | `["all external providers unavailable"]` | `None` |
| 两源全失败 | `"error"` | `"empty"` | `["tushare(error: ...)", "akshare(error: ...)"]` | `["all external providers failed"]` | `None` |
| 两源全空（DESIGN §3.6） | `"error"` | `"empty"` | `["tushare(unavailable: empty payload...)", "akshare(unavailable: empty payload...)"]` | `["no data from any provider"]` | `None` |
| `provider="tushare"` forced + 成功 | `"tushare"` | `label(...)` | `["tushare(ok)"]` | `[]` | `None` |
| `provider="tushare"` forced + 不可用 | `"error"` | `"empty"` | `["tushare(skipped: unavailable)"]` | `["tushare unavailable"]` | `None` |
| `force_refresh=True` + TA-CN 有数据 + 外部成功 | `"tushare"/"akshare"` | `label(...)` | `["tushare(ok)"]` 等 | 同上 | `None` |

> 全部终态行为沿用 SPEC-03-008 §4.8 矩阵；Phase 1D 不引入新的 DataResult 形态。`quality_score` 列恒 `None` 是 Phase 1D 的明确约束（Phase 2 才填充）。
> trace 中空 payload 场景实际表现为 `"tushare(unavailable: empty payload...)"`（非 `"tushare(empty)"`），语义等价，测试断言已适配。

### 4.6 Router / Registry / FreshnessPolicy / Client（不改）

- `DataRouter`：签名、四步编排、`provider`/`force_refresh` 语义**完全不变**（SPEC-03-008 §4.1/§4.3）。
- `ProviderRegistry`：`external_fallback_chains` 已含 `kline_daily: ["tushare","akshare"]`，不改。
- `FreshnessPolicy`：纯计算 `label(...)` 复用，不改。
- `UnifiedDataClient.query()`：签名、`force_refresh` 透传不变；14 个域入口方法不变。

---

## 4.bis 持久化契约

**无持久化需求。**

Phase 1D 全部组件运行在内存中：

- TushareProvider / AKShareProvider：`fetch()` 经 HTTP 客户端获取 DataFrame → `_to_canonical` 转 `list[DailyBar]` → 返回 Router → 装入 `DataResult.data`（内存）。**不写入 Mongo、不写入缓存、不写入审计。**
- HTTP 客户端：真实客户端调外部 API（只读），返回 DataFrame；fake 客户端返回 fixture。无落盘。
- TA-CN adapter：Phase 1A 只读复用，不新增写入。
- external_fallback_chains：内存配置，不落盘。

数据流：`消费方 → UnifiedDataClient.query() → DataRouter（内存编排）→ Provider.fetch()（HTTP 只读 → list[DailyBar]）→ DataResult（内存返回）`。全程不触碰 `03_data_ud_*` / `03_data_ud_cache_*` / `03_data_ud_query_audit` / `03_data_ud_quality_summary` 集合。

---

## 5. 行为契约（RFC-03-012 决策 → SPEC 落地映射）

RFC-03-012 §3/§5 的决策逐条映射到 SPEC 落地点：

| # | RFC 决策 | SPEC 落地点 | 章节 |
|---|---|---|---|
| 1 | 首批能力严格只 `CN + kline_daily` | EP-103 其余 capability 保持 stub；§2.2 Out of Scope | §3.1 / §2.2 |
| 2 | Tushare 主源 → AKShare 兜底 | external_fallback_chains `["tushare","akshare"]`；§4.5 矩阵 | §4.2 / §4.5 |
| 3 | 保持 internal-first 优先级与 forced-provider 语义 | Router 不改；§4.6 | §4.6 |
| 4 | 字段映射契约（Tushare/AKShare → DailyBar） | §4.3 映射表（含单位、空值、缺失列） | §4.3 |
| 5 | 跨源单位不归一化 | §0 单位差异声明；DESIGN §3.7 no-op 裁定 | §0 / §4.3 / §10 |
| 6 | DataResult provider/source_trace/warnings/quality_score 兼容 | §4.5 矩阵；quality_score 恒 None | §4.5 |
| 7 | 不得制造或静默返回 stub/假数据 | EP-101/102 真实路径；fake 仅测试 | §3.1 / §9 |
| 8 | 凭据只经环境变量/可注入客户端，不读取/回显/记录 | §7.2 安全约束；HC-104 | §7.2 / §3.2 |
| 9 | 测试分层：fake HTTP / 可注入客户端单测 / Router fallback / 数据合理性 | §9 测试矩阵；48 项 PASS | §9 |
| 10 | 真实网络 smoke 是后续受控验证项，非执行前提 | §9.3 生产副作用矩阵 | §9.3 |
| 11 | 生产副作用：严禁 Mongo DDL/写入/audit/quality_summary/cron | §4.bis 无持久化；§7.3 不改动清单 | §4.bis / §7.3 |
| 12 | 接受 `datetime.utcnow()` 技术债，不扩散 | §7.4；OQ-3 | §7.4 / §10 |
| 13 | 命名锁定为 Phase 1D（非 1B-B） | §0 术语对齐 | §0 |
| 14 | 不改 Phase 0 公共契约（SecurityId/DataResult/DailyBar 等） | §2.2 Out of Scope；§7.3 | §2.2 / §7.3 |
| 15 | 不改 Router/Registry/FreshnessPolicy/Client | §4.6 | §4.6 |
| 16 | Router L809 空 list 误判（DESIGN gap） | DESIGN §3.6 空 payload raise ProviderUnavailableError | §3.1 EP-104 / §4.5 |
| 17 | 单位 warnings 不可注入（Router 不改约束） | DESIGN §3.7 no-op；文档标注 | §4.3.3 / §0 |

---

## 6. 配置契约

### 6.1 provider 配置（kline_daily 激活相关）

```yaml
unified_data:
  providers:
    tushare:
      enabled: true                      # 沿用 1B-A
      token_env: "TUSHARE_TOKEN"         # 环境变量名，不记录值（P-10）
      rate_limit_rpm: 200                # 引用 config.yaml providers.tushare.rate_limit_rpm
      retry_max_attempts: 3              # 引用 config.yaml providers.tushare.retry_max_attempts
      retry_backoff_base: 1.0            # 引用 config.yaml providers.tushare.retry_backoff_base
      request_timeout_seconds: 30.0      # [1D 新增] 引用 config.yaml providers.tushare.request_timeout_seconds
    akshare:
      enabled: true
      request_delay_seconds: 0.5         # 沿用 1B-A
      rate_limit_rpm: 200
      retry_max_attempts: 3
      retry_backoff_base: 1.0
      request_timeout_seconds: 30.0      # [1D 新增]
  external_fallback_chains:
    "market_data.kline_daily": ["tushare", "akshare"]   # 不改
```

> **P-3（不硬编码阈值）**：SPEC 中所有数字（200/3/1.0/30.0/0.5）均为**初始默认值**，实现时必须从 `config.yaml` 对应字段读取或经构造参数注入，**不得**硬编码在调用处。DESIGN 已确认默认值合理，真实网络 smoke 后可调优。

### 6.2 配置键与环境变量名

| 配置键 | 环境变量 | 说明 | 敏感值不记录 |
|---|---|---|---|
| `providers.tushare.token_env` | `TUSHARE_TOKEN` | Tushare token 环境变量名 | ✅ is_available 只检查存在性；fetch 经客户端消费，不回显 |
| `providers.tushare.request_timeout_seconds` | 无 | 单请求超时 | — |
| `providers.akshare.request_timeout_seconds` | 无 | 单请求超时 | — |
| 其余 `providers.*` | 无 | 沿用 1B-A | — |

**安全原则（P-10）**：
- 凭据值**不得**记录在 task metadata、kanban summary、审计日志、测试 fixture、错误信息中。
- 错误信息（`ProviderUnavailableError`/`ProviderError`）只描述类别（「quota exceeded」「timeout」「missing required column: close」），**不含 token**。
- 测试用 monkeypatch 设环境变量或注入 `FakeKlineClient`，**不**用真实 token 跑单测。

---

## 7. 实现约束

### 7.1 依赖限制

- `tushare` / `akshare` 的安装属**运行环境配置**，由 Pascal 授权后在目标环境安装。实现代码用 try/except 包裹 import（沿用 1B-A `is_available()` 模式），**不新增 pyproject 依赖声明**（它们是可选依赖，缺失时 `is_available()=False`）。
- `pandas` 已是项目依赖，不新增。
- HTTP 客户端抽象用 stdlib `typing.Protocol`，不新增依赖。

### 7.2 安全约束

- Tushare token 从环境变量 `TUSHARE_TOKEN` 读取，经构造参数 `token_env`（默认 `"TUSHARE_TOKEN"`）定位，传给 HTTP 客户端。**不记录/不打印/不回显真实值**。
- `is_available()` 只检查存在性（沿用 1B-A）。
- 错误信息脱敏：异常 message 不含 token、不含完整 URL（含 token 的 query string）、不含响应体中的敏感字段。
- 测试 fixture 不含真实 token；`FakeKlineClient` 不读环境变量。

### 7.3 禁止事项（不改动清单）

| 路径 | 理由 |
|---|---|
| `skills/data/unified_data/models/**`（SecurityId / DataResult / Market / Capability / DailyBar / FreshnessLabel） | Phase 0/1A 公共契约不变 |
| `skills/data/unified_data/router.py` | Router internal-first 编排不变（SPEC-03-008 已交付） |
| `skills/data/unified_data/registry.py` | external_fallback_chains 已含 kline_daily，不改 |
| `skills/data/unified_data/freshness.py` | FreshnessPolicy 纯计算复用 |
| `skills/data/unified_data/client.py`（query + 14 域入口方法） | 行为不变 |
| `skills/data/unified_data/adapters/ta_cn_mongo_adapter.py` | Phase 1A 只读复用 |
| `skills/data/unified_data/local_mongo_adapter.py` | 1B-B 持久化层，1D 不触 |
| `skills/data/unified_data/cache_manager.py` | 1B-B 持久化层，1D 不触 |
| `skills/data/unified_data/audit/**`、`skills/data/unified_data/quality/**` | Phase 2 组件，1D 不注入 |
| `skills/apps/TradingAgents-CN/**` | TA-CN 子项目，只读复用 |
| `skills/research/daily_stock_analysis/**` | DSA 独立子系统，不是运行时数据源 |
| `skills/data/data-pipeline/**` | ETL 管道，职责正交 |
| `skills/data/data_interface/**` | RFC-03-003 IReader/IWriter |
| `skills/infra/task_center/**` | 任务中心独立线 |
| `skills/research/stock/**` | stock 框架是消费方 |
| 生产 MongoDB 集合的 schema validator / DDL / 索引 | 不改现有集合约束 |
| cron / systemd / gateway / 外部推送配置 | 不碰调度和推送 |
| RFC/SPEC/Design 文档模板 | 编排层不改模板（P-7） |
| RFC-03-012 | 本卡只产出 SPEC，不改 RFC |

### 7.4 性能约束

- RateLimiter 与重试沿用 1B-A 框架，真实网络下验证；超限等待、超时中断由框架保证。
- `is_available()` 保持 O(1)（环境变量 + import 检查），**不做网络探测**。
- `_to_canonical()` 是纯内存 DataFrame → list 转换，O(n) 行数。

### 7.5 `datetime.utcnow()` 技术债边界

本阶段**不改造**以下站点的 naive UTC 用法（RFC-03-012 §5.7 / OQ-3）：
- `skills/data/unified_data/local_mongo_adapter.py`（L161/L176/L202）
- `skills/data/unified_data/cache_manager.py`（L155/L167/L192）

理由：1D 不触 LocalMongoAdapter / CacheManager（1B-B 持久化层，本阶段不写入/不注入）。统一 UTC-aware 改造是横切关注点，应作为独立技术债卡（OQ-3），避免扩散 1D 范围。Phase 1D 新增代码（`kline_client.py` + provider 修改）**不引入新的 `datetime.utcnow()` 调用**。

---

## 8. 文件改动清单

### 8.1 新增文件

| 路径 | 说明 |
|---|---|
| `skills/data/unified_data/providers/kline_client.py` | `KlineClient` Protocol + `FakeKlineClient` + `TushareKlineClient` + `AKShareKlineClient` |
| `skills/data/unified_data/tests/test_kline_client.py` | KlineClient / FakeKlineClient / TushareKlineClient / AKShareKlineClient 单元测试 |
| `skills/data/unified_data/tests/test_providers_kline_daily.py` | TushareProvider/AKShareProvider 的 kline_daily 激活路径单测（注入 FakeKlineClient） |
| `skills/data/unified_data/tests/test_router_kline_daily_fallback.py` | Router fallback：kline_daily 链 tushare→akshare 全路径矩阵（注入 fake providers） |

### 8.2 修改文件

| 路径 | 修改内容 |
|---|---|
| `skills/data/unified_data/providers/tushare.py` | docstring 措辞 Phase 1B-B → Phase 1D；构造新增 `http_client`/`request_timeout_seconds`/`emit_unit_warning` 可选参数；`fetch()` 按 capability 分支：kline_daily 走真实路径（经 `_http_client`）+ `_to_canonical` 实现 Tushare 列→list[DailyBar]；空 payload raise `ProviderUnavailableError` |
| `skills/data/unified_data/providers/akshare.py` | 同上（kline_daily 激活；`_to_canonical` 实现 AKShare 中文列→list[DailyBar]，含 trade_date YYYYMMDD 转换、limit 截断） |
| `skills/data/unified_data/providers/base_external.py` | docstring 措辞同步；`_to_canonical` 返回标注从 `pd.DataFrame` 放宽为 `Any`；注释说明 base 保持 no-op，子类按 capability override。**不改方法体逻辑** |
| `skills/data/unified_data/providers/__init__.py` | 导出 `KlineClient`、`FakeKlineClient`、`TushareKlineClient`、`AKShareKlineClient` |
| `skills/data/unified_data/__init__.py` | 导出 `KlineClient`、`FakeKlineClient`（真实客户端不顶层导出） |

### 8.3 不改动文件（明确列出）

见 §7.3 禁止事项表。特别注意：`models/**`、`router.py`、`registry.py`、`freshness.py`、`client.py`、`adapters/ta_cn_mongo_adapter.py`、`local_mongo_adapter.py`、`cache_manager.py`、`audit/**`、`quality/**`、`exceptions.py`、`config.py`、`_stub_columns.py`、`rate_limiter.py` 均不改。

---

## 9. 测试要求

### 9.1 单元测试矩阵

| 测试编号 | 测试目标 | mock/注入方式 | 断言 |
|---|---|---|---|
| UT-KC-001 | FakeKlineClient 返回 fixture DataFrame | 直接构造 | `get_kline_daily(...)` 返回配置的 DataFrame；call_log 含参数 |
| UT-KC-002 | FakeKlineClient 抛 ProviderUnavailableError | 配置异常 | raise 指定异常 |
| UT-KC-003 | FakeKlineClient 返回空 DataFrame | 配置 None | 返回空 DataFrame（0 行） |
| UT-KC-004 | TushareKlineClient token 缺失 raise | 构造 `token=""` | raise `ProviderUnavailableError("tushare token missing")` |
| UT-KC-005 | AKShareKlineClient 延迟 import（akshare 未装时不崩） | mock import | 构造成功；get_kline_daily 时才 import |
| UT-TP-201 | Tushare kline_daily 真实路径成功 | FakeKlineClient 返回 Tushare 列 DF | `list[DailyBar]`，字段映射正确（vol→volume 手、amount 千元） |
| UT-TP-202 | Tushare kline_daily 空 → raise | FakeKlineClient 返回空 DF | fetch raise `ProviderUnavailableError("empty payload")`（§3.6） |
| UT-TP-203 | Tushare 缺 close 列 | FakeKlineClient 返回缺 close 的 DF | raise `ProviderError("missing required column: close")`（§4.3.1） |
| UT-TP-204 | Tushare 行级 close=None 丢弃 | DF 含 close=NaN 行 | 该行不入 list，其余行入 |
| UT-TP-205 | Tushare HTTP 超时 | FakeKlineClient raise ProviderUnavailableError | fetch 透传 raise（Router 侧 fallback） |
| UT-TP-206 | Tushare 其余 12 capability 保持 stub | 调 kline_weekly 等 | 返回 stub DataFrame（空壳）；FakeKlineClient.call_log 为空 |
| UT-TP-207 | Tushare is_available 不变 | monkeypatch TUSHARE_TOKEN | token 存在+import → True；否则 False（不打印 token） |
| UT-TP-208 | Tushare 默认 client 延迟构造 | `http_client=None` + monkeypatch token | 首次 fetch 才构造 TushareKlineClient；is_available=False 时不构造 |
| UT-AK-201 | AKShare kline_daily 真实路径成功 | FakeKlineClient 返回 AKShare 中文列 DF | `list[DailyBar]`，trade_date 转 YYYYMMDD，成交量=股、成交额=元 |
| UT-AK-202 | AKShare kline_daily 空 → raise | FakeKlineClient 返回空 | raise `ProviderUnavailableError("empty payload")` |
| UT-AK-203 | AKShare 缺 `收盘` 列 | 缺 close | raise `ProviderError("missing required column: 收盘")` |
| UT-AK-204 | AKShare 行级 close=None 丢弃 | close=NaN 行 | 该行丢弃 |
| UT-AK-205 | AKShare trade_date 格式转换 | `日期="2026-07-18"` | DailyBar.trade_date == `"20260718"` |
| UT-AK-206 | AKShare limit 截断 | limit=5 + 10 行 fixture | 返回 list 长度 5（§3.4.2 limit 截断） |
| UT-AK-207 | AKShare 其余 6 capability 保持 stub | 调 kline_weekly 等 | stub DataFrame；call_log 空 |
| UT-AK-208 | AKShare is_available 不变 | mock import | import 成功 → True |
| UT-DR-301 | Router kline_daily TA-CN 命中不调外部 | FakeTA_CNAdapter 有数据 + FakeProvider | `provider="ta_cn_internal"`；FakeKlineClient.call_log 空 |
| UT-DR-302 | Router TA-CN 未覆盖 → tushare 成功 | tushare FakeKlineClient ok | `provider="tushare"` |
| UT-DR-303 | Router tushare 失败 → akshare 兜底 | tushare raise + akshare ok | `provider="akshare"`；warnings 含 fallback 提示 |
| UT-DR-304 | Router 两源全失败 | 两源 raise | `provider="error"`；trace 2 个 unavailable/error |
| UT-DR-305 | Router 两源全空（§3.6 gap） | 两源 FakeKlineClient 返回空 → fetch raise | `provider="error"`；freshness="empty"；trace 含 "empty payload" |
| UT-DR-306 | Router 两源全不可用 | 两源 is_available=False | `provider="error"`；trace 2 个 skipped |
| UT-DR-307 | Router provider="tushare" forced | provider="tushare" | 只走 tushare，不 fallback |
| UT-DR-308 | Router force_refresh 跳过 TA-CN | TA-CN 有数据 + force_refresh=True | `provider="tushare"`；TA-CN 未调 |
| UT-DR-309 | Router quality_score 恒 None | 任意成功路径 | `DataResult.quality_score is None` |
| UT-SEC-401 | is_available 不泄露 token | monkeypatch TUSHARE_TOKEN="secret" | 返回 True/False；不返回/不打印 "secret" |
| UT-SEC-402 | 错误信息不含 token | FakeKlineClient raise 含 token 的异常 | provider re-raise 的 message 不含 token |
| UT-SEC-403 | FakeKlineClient 不读环境变量 | 构造 + 调用 | 不调 os.environ；call_log 不含 token |

### 9.2 集成测试

| 测试编号 | 测试目标 |
|---|---|
| IT-001 | 端到端：client.query(kline_daily) → TA-CN 命中 → 返回（不调 external） |
| IT-002 | 端到端：client.query(kline_daily, provider="tushare") → 注入 FakeKlineClient → list[DailyBar] |
| IT-003 | 端到端：client.query(kline_daily, force_refresh=True) → 跳过 TA-CN → tushare fake |
| IT-004 | 端到端：client.query(kline_daily) → tushare fake 失败 → akshare fake 兜底 → list[DailyBar] + warnings |

### 9.3 数据合理性断言（P-11 对齐）

- **字段一致性**：FakeKlineClient 返回的 Tushare/AKShare 原始列值 → DailyBar 字段值必须与映射表（§4.3）一致（如 Tushare `vol=1234.0` → DailyBar.volume=1234.0，单位手）。
- **非空性**：成功路径的 `list[DailyBar]` 必须非空（除非 fixture 显式空 → raise `ProviderUnavailableError`）。
- **不返回 stub**：kline_daily 激活路径**不得**返回 `_stub_columns.stub_dataframe_for` 的空壳 DataFrame（断言 `isinstance(result, list)` 且元素为 DailyBar）。
- **关键字段不为 None**：成功路径的 DailyBar `close`/`trade_date` 必须非 None（除非该行被丢弃）。
- **trade_date 格式一致**：Tushare 与 AKShare 路径的 DailyBar.trade_date 均为 YYYYMMDD。

### 9.4 回归测试

- Phase 1B-A 的 `test_providers.py`（stub 路径）全部通过——kline_daily 相关断言已同步更新为 list[DailyBar]。
- Phase 1B-A 的 `test_router_internal_first.py` 全部通过——Router 编排不变。
- Phase 1A 的 `test_client_phase1a.py` 全部通过——14 域入口方法不变。
- Phase 0 的 `test_router.py` 全部通过——向后兼容。

### 9.5 不可自动化验证项

- **真实 Tushare/AKShare API 可用性**：属后续受 Pascal 单独授权的受控 smoke（§9.3 of RFC-03-012）。本卡/实现卡**不**以此 为执行前提。
- **真实 token 安全性审查**：人工审计 is_available / fetch / 错误路径不泄露值。
- **真实网络下 RateLimiter/重试行为**：受控 smoke 阶段验证（DESIGN §3.8 重试边界说明）。

---

## 10. 验收标准

| 编号 | 验收项 | 验证方式 | 状态 |
|---|---|---|---|
| A-001 | TushareProvider kline_daily 经可注入 HTTP 客户端真实调用 | UT-TP-201~205 | ✅ 48/48 PASS |
| A-002 | AKShareProvider kline_daily 同上 | UT-AK-201~205 | ✅ 48/48 PASS |
| A-003 | 字段映射表（§4.3）精确实现 | UT-TP-201, UT-AK-201 字段断言 | ✅ |
| A-004 | 空结果/字段缺失/行丢弃处理正确 | UT-TP-202~204, UT-AK-202~204 | ✅ |
| A-005 | Tushare 其余 12 capability 保持 stub | UT-TP-206 | ✅ |
| A-006 | AKShare 其余 6 capability 保持 stub | UT-AK-207 | ✅ |
| A-007 | Router kline_daily fallback 全路径 | UT-DR-301~308 | ✅ |
| A-008 | DataResult provider/source_trace/warnings 正确 | UT-DR-302~307, §4.5 矩阵 | ✅ |
| A-009 | quality_score 恒 None（Phase 1D 约束） | UT-DR-309 | ✅ |
| A-010 | 单位标注差异通过文档标注（DESIGN §3.7 no-op） | DESIGN §3.7 裁定 + UT-TP-207/AK-205 无 warning 注入 | ✅ |
| A-011 | is_available 不泄露 token | UT-SEC-401 | ✅ |
| A-012 | 错误信息不含 token | UT-SEC-402 | ✅ |
| A-013 | 不返回 stub/假数据冒充真实 | 数据合理性断言（§9.3） | ✅ |
| A-014 | 不新增 Mongo 集合/索引/写入 | grep 新增文件 `create_collection|create_index|insert_one|update_one` → 0 命中 | ✅ |
| A-015 | 不修改 Router/Registry/FreshnessPolicy/Client | `git diff router.py registry.py freshness.py client.py` → 空 | ✅ |
| A-016 | 不修改 models/ DailyBar / DataResult | `git diff models/` → 空 | ✅ |
| A-017 | 不修改 TA-CN 子项目 | `git diff skills/apps/TradingAgents-CN/` → 空 | ✅ |
| A-018 | 不修改 Phase 1A 14 域入口方法 | `git diff client.py` → 空（client.py 在禁改清单） | ✅ |
| A-019 | external_fallback_chains 只含 tushare/akshare | grep SPEC + config 验证 | ✅ |
| A-020 | DSA 不出现在运行时链路 | grep `dsa|DSA|StockDaily` providers/ router.py → 0 命中 | ✅ |
| A-021 | Phase 1B-A 测试回归通过 | test_providers.py / test_router_internal_first.py / test_client_phase1a.py / test_router.py 全 PASS | ✅ |
| A-022 | datetime.utcnow() 技术债未扩散 | `git diff local_mongo_adapter.py cache_manager.py` → 空 | ✅ |

---

## 11. 向后兼容

### 11.1 对 Phase 1B-A 的影响

- TushareProvider / AKShareProvider 的构造新增 `http_client` / `request_timeout_seconds` 可选参数（默认 None / 30.0），现有调用方不传则用默认真实客户端，**向后兼容**。
- `fetch()` 签名不变；kline_daily 分支返回类型从 stub DataFrame 改为 `list[DailyBar]`——这是**预期行为变更**（激活），1B-A 测试中对 kline_daily 返回 stub DataFrame 的断言已同步更新。
- 其余 capability 的 stub 行为完全不变，1B-A 相关测试自然通过。

### 11.2 对 Phase 0/1A 的影响

- Router / Registry / FreshnessPolicy / Client 完全不改，Phase 0/1A 测试自然通过。

### 11.3 对 Phase 1B-B / Phase 2 的影响

- 本阶段不注入 LocalMongoAdapter / CacheManager / AuditLogger / QualityScorer / QualitySummary，1B-B / Phase 2 组件不受影响。

---

## 12. 风险与未解决问题

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| Tushare/AKShare 列名漂移（API 变更） | 中 | 高 | §4.3 映射表 + 缺失列校验（UT-TP-203/AK-203） |
| 跨源单位不一致被消费方误用 | 高 | 高 | §0 声明 + DESIGN §3.7 no-op 裁定 + OQ-2 |
| 真实网络 smoke flaky | 中 | 中 | smoke 非执行前提（§9.5）；fake 客户端单测为主 |
| token 泄露 | 低 | 高 | P-10 + UT-SEC-401/402 |
| 限流/重试真实行为偏差 | 中 | 中 | 框架沿用 1B-A，真实网络下验证 |
| kline_daily 返回类型变更破坏 1B-A 测试 | 高 | 中 | §11.1 同步更新 1B-A 测试断言——已完成 |
| Router L809 空 list 误判（DESIGN §3.6 gap） | 中 | 高 | 空 payload raise ProviderUnavailableError——已实现已验证 |
| datetime.utcnow() 扩散 | 低 | 低 | §7.4 不触；OQ-3 |

### 移交 Design 阶段的待决项（已全部解决，详见 DESIGN-03-012 §8）

1. HTTP 客户端抽象的具体形态（Protocol vs ABC vs callable 工厂）—— **Design 裁定：`typing.Protocol`**
2. 真实 Tushare 客户端具体 SDK 调用（`pro_api(token).daily(...)` vs `pro_bar(...)`) —— **Design 裁定：`pro_api(token).daily(...)`**
3. 真实 AKShare 客户端 `stock_zh_a_hist` 的 `adjust`/`period` 参数默认值 —— **Design 裁定：`period="daily"`, `adjust=""`**
4. AKShare `trade_date` 格式（YYYY-MM-DD 透传 vs 转 YYYYMMDD 统一）—— **Design 裁定：统一转 YYYYMMDD**
5. 单位提示 warnings 是否默认开启 —— **Design 裁定：`emit_unit_warning=True` 保留但为 no-op（Router 不改约束下无法注入）**
6. `_to_canonical` 是 base 类 hook 还是子类各自 override —— **Design 裁定：base 保留 no-op，子类各自 override + 内部 capability 分支**
7. kline_daily 返回 `list[DailyBar]` 的 Router 包装逻辑 —— **Design 确认可行（router.py:814 透明包装）**
8. **[DESIGN 发现 gap]** Router L809 `is not None` 对空 list 的误判 —— **Design 裁定：空 payload raise `ProviderUnavailableError`**

---

## 13. 参考资料

- RFC-03-012：`docs/rfc/03_data/RFC-03-012-unified-data-phase-1d-external-provider-activation.md`
- DESIGN-03-012：`docs/design/03_data/DESIGN-03-012-unified-data-phase-1d-external-provider-activation.md`（§8 待决项裁定、§3.6 Router gap 解决）
- RFC-03-007：`docs/rfc/03_data/RFC-03-007-unified-data-layer.md`（六项不变量 §14）
- RFC-03-008：`docs/rfc/03_data/RFC-03-008-unified-data-phase-1b-query-plane.md`（provider 框架）
- RFC-03-009：`docs/rfc/03_data/RFC-03-009-unified-data-phase-1b-persistence-plane.md`（1B-B 命名锁定）
- RFC-03-011：`docs/rfc/03_data/RFC-03-011-unified-data-phase-2-quality-audit-governance.md`（quality_score 填充归属）
- SPEC-03-007：`docs/spec/03_data/SPEC-03-007-unified-data-layer.md`
- SPEC-03-008：`docs/spec/03_data/SPEC-03-008-unified-data-phase-1b-query-plane.md`（provider 契约来源）
- SPEC-03-009：`docs/spec/03_data/SPEC-03-009-unified-data-phase-1b-persistence-plane.md`
- 现有代码：
  - `skills/data/unified_data/providers/tushare.py`（Phase 1D kline_daily 激活态，13 capability）
  - `skills/data/unified_data/providers/akshare.py`（Phase 1D kline_daily 激活态，7 capability）
  - `skills/data/unified_data/providers/base_external.py`（`_to_canonical` hook）
  - `skills/data/unified_data/providers/_stub_columns.py`（stub schema）
  - `skills/data/unified_data/providers/kline_client.py`（KlineClient Protocol + FakeKlineClient + TushareKlineClient + AKShareKlineClient）
  - `skills/data/unified_data/router.py`（`provider.fetch` 调用点 L906）
  - `skills/data/unified_data/models/domain/market_data.py`（`DailyBar` canonical）
  - `skills/data/unified_data/models/__init__.py`（`DataResult`）
- Tushare `daily` 文档：https://tushare.pro/document/2?doc_id=27
- AKShare `stock_zh_a_hist` 文档：https://akshare.akfamily.xyz/data/stock/stock.html

---

## 14. Phase 1D Closeout 可追溯证据与边界

### 14.1 验证证据清单

| 证据 ID | 来源 | 时效 | 内容 | 覆盖范围 |
|---|---|---|---|---|
| `t_976ad8a2` | Kanban T5 Review | 2026-07-20 | Review PASS | 代码/文档/测试一致性审查 |
| `t_9743d0b2` | Kanban 独立 Verify | 2026-07-20 | 48/48 离线专项测试 PASS，零网络调用；tushare/akshare provider 全部 kline_daily 路径覆盖 | 全部 unit + router fallback 测试 |
| `t_01a2457f` | 真实 Tushare smoke | 2026-07-20 | 单次 CN 600519, 20260713-20260717, Tushare 主路径, 5 bars, OHLC 合理, 1.404s | **仅** CN kline_daily 单标的 5 自然日 Tushare 成功分支 |

### 14.2 真实 smoke 证明的项目（SPEC §10 验收标准验证）

| 验收项 | 证明程度 | 证据 |
|---|---|---|
| A-001：TushareProvider kline_daily 真实调用 | ✅ 直接证明 | smoke 返回 5 条非空 DailyBar，Tushare fetch=1 |
| A-011：is_available 不泄露 token | ✅ 间接证明 | smoke 全程无 token 泄露；环境变量值未出现在任何输出 |
| A-013：不返回 stub/假数据 | ✅ 直接证明 | smoke 收到真实 DailyBar（非 stub DataFrame） |
| A-008：DataResult provider/source_trace 正确 | ✅ 直接证明 | handoff 字段 final_provider=tushare，warnings=[] |
| A-015：不修改 Router/Registry/FreshnessPolicy/Client | ✅ 间接证明 | repo 无 diff（git status/diff 空） |
| A-018：不修改 TA-CN | ✅ 间接证明 | repo 无 diff |

### 14.3 真实 smoke **未**证明的项目（明确边界）

以下验收项在离线测试中通过，但**未在真实网络 smoke 中执行**。任何声称它们「已真实验证」的说法均不准确：

| 验收项 | 覆盖方式 | 真实网络验证状态 |
|---|---|---|
| A-002：AKShareProvider kline_daily 真实调用 | 仅离线 fake 客户端 | ❌ 未执行（smoke 中 Tushare 成功，AKShare 未触发） |
| A-004：空结果/字段缺失/行丢弃 | 仅离线 fake 客户端 | ❌ 未执行（smoke 为正常数据路径） |
| A-005：Tushare 其余 12 capability 保持 stub | 仅离线测试 | ❌ 未执行 |
| A-006：AKShare 其余 6 capability 保持 stub | 仅离线测试 | ❌ 未执行 |
| A-007：Router fallback 全路径（UT-DR-301~308） | 仅离线 fake 客户端 | ❌ 未执行 |
| A-010：单位标注差异（DESIGN §3.7 no-op） | 仅离线测试 | ❌ 未执行 |
| A-014：不新增 Mongo 集合/索引/写入 | 仅 grep 检查 | ✅ 但 grep 是静态分析，非 smoke |
| A-021：1B-A 回归通过 | 仅离线测试 | ❌ 未执行 |

> **结论**：真实 smoke 直接证明的范围是「CN kline_daily 单标的 5 自然日 Tushare 成功路径可正常工作并返回合理 DailyBar」。不可外推至配额、长期稳定性、AKShare、其他 capability、跨源单位场景。

### 14.4 残余风险与证据缺口（不阻断 closeout）

| 缺口 | 影响 | 后续阶段 |
|---|---|---|
| 缺少连续多日配额消耗监控 | 单次 smoke 不反映配额基线 | 建议 Phase 2 smoke 扩展 |
| 缺少 AKShare 真实 fallback 证据 | AKShare → DailyBar 映射仅离线验证 | 建议后续 smoke 强制 AKShare 路径 |
| 缺少多标的场景（不同板块/市值） | 仅单标的（600519 茅台） | 建议 Phase 2 扩展 |
| 缺少 `force_refresh=True` 真实路径证据 | 强制跳过 TA-CN 后外部数据一致性仅离线验证 | 建议后续 smoke 覆盖 |
