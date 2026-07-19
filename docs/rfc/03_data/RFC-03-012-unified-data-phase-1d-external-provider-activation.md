# RFC-03-012：Unified Data Phase 1D — CN 日线真实外部 Provider 激活

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 终稿（Final） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-18 |
| 最后更新 | 2026-07-20 |
| 版本号 | V0.2 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-008（Phase 1B-A 查询平面）、RFC-03-009（Phase 1B-B 持久化缓存平面）、RFC-03-011（Phase 2 质量与审计治理） |
| 依赖 SPEC | SPEC-03-008（Phase 1B-A 查询平面）、SPEC-03-009（Phase 1B-B 持久化缓存平面）、SPEC-03-012（Phase 1D External Provider Activation） |
| 关联 Design | DESIGN-03-012（Phase 1D CN 日线真实外部 Provider 激活，已交付） |
| 替代 RFC | 无（不替代任何 RFC；为 Phase 1B 框架激活真实网络调用的独立子阶段） |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #provider #tushare #akshare #kline_daily #external-activation #phase1d |

### 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.2 | 2026-07-20 | T1 收口定稿。基于当前代码库事实：Tushare/AKShare `kline_daily` 真实激活已实现并通过 48 项测试；DESIGN-03-012 已交付；RFC 状态从 Draft 更新为 Final，§3.1/§3.2 全部 ✅ 确认，§9.2 标记实现完成，交叉引用对齐，OQ-1/4 已关闭。 | YQuant-Principal |
| V0.1 | 2026-07-18 | 初始创建。将「真实外部 Provider 激活」从 Phase 1B-A 框架中拆出为独立 Phase 1D，解释与 1B-A/1B-B 的命名衔接；首批能力严格限定 `CN + market_data.kline_daily`，Tushare 主源 → AKShare 兜底。 | YQuant-Principal |

---

## 1. 执行摘要（Executive Summary）

Phase 1B-A 已交付 TushareProvider / AKShareProvider 的**能力声明、可用性判定、限流重试、canonical 转换框架**，但 `fetch()` 返回的是 `_stub_columns.STUB_COLUMNS` 定义的空壳 DataFrame，不发任何网络请求（`is_available()` 也仅检查 token 存在性与 importability）。Phase 1D 把 `market_data.kline_daily` 这一**唯一能力**从 stub 激活为真实网络调用：Tushare 为主源、AKShare 为兜底，输出 Phase 1A 已定义的 `DailyBar` canonical 对象，完整融入既有 internal-first 读取路径与 `DataResult` 语义。

本阶段**不新增能力**（不加周/月线、复权、财务、新闻、交易日历、估值、指数成分），**不触生产副作用**（无 Mongo DDL/DML、无缓存写入、无 AuditLogger 真实写入、无 QualitySummary、无调度），**不修改 Phase 0 公共契约**（`SecurityId` / `DataResult` / `Market` / `Capability` 签名不变）。真实网络 smoke 是后续受控验证项，不构成本卡或实现卡的执行前提。

## 2. 背景与动机（Background & Motivation）

### 2.1 现状

- **查询平面已稳定**：`DataRouter` 已实现 internal-first 四步编排（TA-CN 只读 → UD materialized → Query Cache → 外部 Provider fallback），`provider` / `force_refresh` / forced-provider 语义矩阵已由 Phase 1B-A 交付并被测试覆盖。Router 在 Step 4 通过 `provider_obj.fetch(domain, operation, security_id, **params)` 调用 provider，对 provider 是 stub 还是真实实现完全透明（`router.py:906`）。
- **外部 Provider 已激活 kline_daily**：`skills/data/unified_data/providers/tushare.py` 与 `akshare.py` 的 `fetch()` 在 `kline_daily` 分支走真实网络调用（经可注入 `KlineClient`），其余 12/6 capability 保持 stub。模块 docstring 已同步更新为「Phase 1D」。命名衔接见 §2.3。
- **`tushare` / `akshare` 属可选依赖**：`is_available()` 检查 importability；未安装时返回 `False`，provider 自动跳过（与 Phase 1B-A 行为一致）。安装需 Pascal 授权。

### 2.2 痛点

| 痛点 | 影响 |
|---|---|
| 外部 Provider 不发网络请求 | TA-CN 未覆盖的标的/时段、或 `force_refresh=True` 路径下，`query()` 对 `kline_daily` 无法返回真实外部数据 |
| stub DataFrame 与真实 payload 形状偏差 | canonical 转换从未被真实字段（Tushare 的 `ts_code`/`trade_date`/`vol`/`amount`；AKShare 的 `日期`/`开盘`/`成交量` 等）压力测试，后续若直接接入缓存/审计层会暴露映射漏洞 |
| 限流/重试框架未在真实网络下验证 | `RateLimiter` 与重试退避（Phase 1B-A 框架）只在内存被构造，真实配额耗尽/超时的行为是理论值 |
| 缺少「真实外部数据 → DailyBar」的字段映射契约 | Tushare 与 AKShare 的列名、单位、日期格式、空值语义差异显著，若不固化映射表，实现者会各自猜测 |

### 2.3 命名衔接：为何是 Phase 1D 而非 1B-B

Phase 1B-A 的 provider stub docstring 把真实 API 激活标注为「Phase 1B-B」，但这一标注从未被任何 RFC/SPEC 形式化：

- **RFC-03-009** 已将 **Phase 1B-B** 定义为「持久化缓存平面」（LocalMongoAdapter + CacheManager + `03_data_ud_*` / `03_data_ud_cache_*` 物化与缓存集合）。这是 Pascal 已确认的归属，不可回退。
- **RFC-03-010** 是 **Phase 1C**「端到端验收与测试收口」，**DESIGN-03-010** 已明确 Sector Router 不在其范围。
- **RFC-03-011** 是 **Phase 2**「质量评估、审计与运行治理」。

为避免与 1B-B 持久化平面冲突，本阶段正式定义为 **Phase 1D: External Provider Activation**，紧接 1C 之后、Phase 2 之前/并行。stub docstring 中残留的「Phase 1B-B」字样已由 Phase 1D 实现同步更新为「Phase 1D」。

> **命名锁定**：后续所有 SPEC/Design/代码注释统一使用 **Phase 1D** 指代「真实外部 Provider 激活」。Phase 1B-B 永远指持久化缓存平面。

### 2.4 触发原因

需求驱动：消费方（strategies / portfolio / reports）需要 `kline_daily` 在 TA-CN 缺数据时能从外部补齐，且 `force_refresh=True` 路径要有真实数据返回。Phase 1B-A 的框架已就位，激活真实调用的风险被隔离在单一 capability + 单一 market 内，是验证「外部 Provider → DailyBar → DataResult」端到端语义的最小可行切片。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）

- [x] **激活 `market_data.kline_daily`（CN only）的真实网络调用**：TushareProvider 主源、AKShareProvider 兜底。其余 12 条 Tushare capability 与 6 条 AKShare capability **保持 stub 不变**。
- [x] **固化字段映射契约**：Tushare / AKShare 原始列 → `DailyBar` canonical 的精确映射表，含日期格式、单位、空值、复权口径处理。
- [x] **保持 internal-first 优先级与 forced-provider 语义**：`kline_daily` 的真实外部调用只在 Step 4（外部 fallback）或 `provider="tushare"` / `provider="akshare"` forced 分支触发；TA-CN 只读优先级、`force_refresh` 跳过内部源的语义不变。
- [x] **确定性行为**：输入（`SecurityId`、日期范围、`limit`）、输出（`DataResult` 携带 `list[DailyBar]` 或 error）、日期格式、OHLCV/amount 单位、空结果、字段缺失、超时、限流、重试、可用性判定、双源全失败的终态行为全部可执行、可测试。
- [x] **`DataResult` 兼容性**：`provider` / `source_trace` / `warnings` / `quality_score` 字段在真实调用路径下与 Phase 1B-A / Phase 2 契约一致；**不得制造或静默返回 stub/假数据**。
- [x] **凭据与 token 安全**：Tushare token 只经环境变量/可注入客户端处理；**不得读取、回显、记录**真实秘密（P-10）。
- [x] **测试分层**：fake HTTP / 可注入客户端单测、Router fallback 测试、数据合理性断言；真实网络 smoke 是后续受控验证项。

### 3.2 非目标（Out of Scope）

- [x] **不加周线/月线、复权因子、财务三表、新闻、交易日历、估值、指数成分、实时行情的真实激活**（保持 stub）。
- [x] **不迁移消费方**：不修改 strategies / portfolio / reports / stock framework 的调用代码；消费方迁移属后续阶段。
- [x] **不实现 Sector Router**（DESIGN-03-010 已明确不在范围）。
- [x] **不实现 Task Center 集成、批量回填、cron/systemd/webhook**。
- [x] **不做生产副作用**：本阶段严禁 MongoDB DDL、真实 MongoDB 写入、materialization/cache 写入、AuditLogger 真实写入、QualitySummary 启用。
- [x] **不修改 Phase 0 公共契约**：`SecurityId` / `DataResult` / `Market` / `Capability` 值对象的签名与语义不变；`DataResult.success` / `DataResult.error` 工厂语义不变。
- [x] **不修改 TA-CN 子项目代码**（`skills/apps/TradingAgents-CN/**`）与 TA-CN 无前缀集合。
- [x] **不修改 Phase 1A 的 14 个域入口方法行为**（继续直连 TA-CN adapter）。
- [x] **不修改 RFC/SPEC/Design 文档模板**（编排层不改模板，P-7）。
- [x] **不把真实网络 smoke 作为本卡或实现卡的执行前提**（见 §9.3）。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

**最小能力切片 + 可注入客户端 + 既有 internal-first 路径复用 + 零生产副作用**：

- 只激活 `kline_daily`，把「真实外部数据 → canonical」的端到端语义在最窄范围内验证，风险隔离。
- 真实网络调用封装在**可注入的 HTTP 客户端**后面（构造参数或工厂），单测用 fake 客户端，真实 smoke 用真实客户端，遵循 Phase 1B-A「框架 + fake 验证」的同款测试哲学。
- 完全复用 Phase 1B-A 的 Router / Registry / provider 类骨架；激活只发生在 `fetch()` 与 `_to_canonical()` 内部。
- 任何持久化、审计、质量汇总均不启用，保持 Phase 1B-A 的「零 Mongo 写入」边界。

### 4.2 架构总览（Phase 1D 范围）

```
消费方 query(domain="market_data", operation="kline_daily", sid, ...)
   │
   ▼
UnifiedDataClient.query()  →  DataRouter（internal-first，不变）
   │
   ├─ Step 1: TA-CN adapter（只读，不变；命中即返回 provider="ta_cn_internal"）
   ├─ Step 2/3: 占位跳过（1B-B 层，不变）
   └─ Step 4: 外部 fallback 链  →  kline_daily: ["tushare", "akshare"]
        │
        ▼
   TushareProvider.fetch(kline_daily)          AKShareProvider.fetch(kline_daily)
     · is_available()（token 存在 + import）     · is_available()（import）
     · RateLimiter.acquire()                     · RateLimiter.acquire()
     · _http_client.get_kline_daily(...)         · _http_client.get_kline_daily(...)
        （可注入：fake / 真实 tushare / 真实 akshare）
     · _to_canonical(raw_df, "market_data.kline_daily")
        Tushare 列 → DailyBar                    AKShare 列 → DailyBar
     · 返回 list[DailyBar]                       · 返回 list[DailyBar]
        │
        ▼
   DataRouter 包入 DataResult.success(data=list[DailyBar], provider="tushare"/"akshare",
                                       source_trace=[...], freshness=label(...))
```

### 4.3 模块分工

| 组件 | Phase 1D 职责 | 与既有阶段的关系 |
|---|---|---|
| **TushareProvider** | `kline_daily` 的 `fetch()` 从 stub 改为真实调用（经可注入客户端）；`_to_canonical()` 实现 Tushare 列 → `list[DailyBar]`；其余 12 capability 保持 stub | 类骨架、`is_available()`、RateLimiter、重试框架沿用 1B-A |
| **AKShareProvider** | `kline_daily` 同上；`_to_canonical()` 实现 AKShare 列 → `list[DailyBar]`；其余 6 capability 保持 stub | 同上 |
| **HTTP 客户端抽象** | 新增轻量客户端接口（`KlineClient` Protocol），封装 Tushare/AKShare 的真实 SDK 调用；Fake 实现用于单测 | 1B-A 未有，1D 新增 |
| **DataRouter** | 不修改 | Step 4 调 `provider.fetch(...)` 对实现透明 |
| **ProviderRegistry** | 不修改 | external_fallback_chains 已含 `["tushare","akshare"]` |
| **FreshnessPolicy** | 不修改 | `label()` 纯计算复用 |
| **UnifiedDataClient** | 不修改 | `query()` / 14 域入口方法不变 |
| **DataResult / DailyBar** | 不修改 | 沿用 Phase 0 / 1A 契约 |

## 5. 详细设计（Detailed Design）

### 5.1 业务流程：kline_daily 外部获取

#### 5.1.1 正常路径

```
Router Step 4 解析 kline_daily 链 → ["tushare", "akshare"]
  │
  ├─ TushareProvider.is_available()?
  │    └─ False → trace "tushare(skipped: unavailable)"，尝试 AKShare
  │    └─ True  → RateLimiter.acquire() → _http_client.get_kline_daily(sid, start, end, limit)
  │         ├─ 返回非空 raw_df → _to_canonical → list[DailyBar]
  │         │    └─ 非空 → 返回给 Router，包入 DataResult.success(provider="tushare")
  │         ├─ 返回空 → _to_canonical 产出 [] → fetch raise ProviderUnavailableError
  │         │    (DESIGN §3.6: 适配 Router L809 "is not None" 检查)
  │         └─ 抛 ProviderError/ProviderUnavailableError → trace，尝试 AKShare
  │
  └─ AKShareProvider.is_available()?
       └─ False → trace "akshare(skipped: unavailable)"
       └─ True  → RateLimiter.acquire() → _http_client.get_kline_daily(...)
            ├─ 非空 → canonical → DataResult.success(provider="akshare")
            ├─ 空 → fetch raise ProviderUnavailableError
            └─ 异常 → trace
  │
  └─ 两源均未返回非空 → DataResult.error(provider="error", source_trace=[...], freshness="empty")
```

> **空结果 fallback**：与 Phase 1B-A 的 Router 契约一致——外部 provider 返回空属于「该 provider 无此数据」，Router 继续尝试链中下一个 provider；链耗尽后返回 `DataResult.error`。这与 TA-CN「覆盖该域但空」不 fallback 的语义**不同**（TA-CN 由 capability 映射表判定覆盖性，外部 provider 由链顺序自然推进）。

#### 5.1.2 异常降级路径

| 场景 | Router 行为 | DataResult |
|---|---|---|
| Tushare 配额耗尽 / 网络超时 | `ProviderUnavailableError` → trace + 尝试 AKShare | 最终成功则 `provider="akshare"` + warnings；全失败则 error |
| Tushare API 内部错误 | `ProviderError` → trace + 尝试 AKShare | 同上 |
| AKShare 网络不通 | `ProviderUnavailableError` → trace | 链耗尽 → error |
| 两源全不可用（token 缺失 + import 失败） | 均 `is_available()=False` | `provider="error"`, freshness="empty", source_trace 含 2 个 skipped |
| 两源全返回空 | fetch raise ProviderUnavailableError（DESIGN §3.6） | `provider="error"`, freshness="empty", trace 含 "empty payload" |
| `provider="tushare"` forced + tushare 不可用 | 不 fallback | `provider="error"`, source_trace=`["tushare(skipped: unavailable)"]` |
| `force_refresh=True` + TA-CN 有数据 | 跳过 Step 1，直接 Step 4 | `provider="tushare"/"akshare"` |
| 不支持的 capability（如 `kline_weekly`） | provider 仍走 stub 路径 | 行为同 Phase 1B-A（stub DataFrame） |

### 5.2 字段映射契约（Tushare / AKShare → DailyBar）

`DailyBar` canonical 字段（Phase 1A 已定义，`skills/data/unified_data/models/domain/market_data.py`）：`symbol`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `change`, `pct_chg`, `volume`, `amount`, `turnover_rate`, `volume_ratio`。

#### 5.2.1 Tushare `daily` 接口映射

Tushare `pro.daily(ts_code, start_date, end_date, limit)` 返回列（Tushare 官方）：`ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount`。

| DailyBar 字段 | Tushare 列 | 转换 | 单位/格式 |
|---|---|---|---|
| `symbol` | `ts_code` | 去交易所后缀（`"600519.SH"` → `"600519"`） | 6 位代码 |
| `trade_date` | `trade_date` | 透传（`"YYYYMMDD"` 字符串） | YYYYMMDD（Tushare 原生 YYYYMMDD） |
| `open/high/low/close/pre_close` | 同名 | `float()` | 元（Tushare `daily` 为不复权前收盘价口径） |
| `change` | `change` | `float()` | 元 |
| `pct_chg` | `pct_chg` | `float()` | 百分比（已 ×100，如 1.23 表示 1.23%） |
| `volume` | `vol` | `float()` | **手**（Tushare `vol` 单位为手，1 手 = 100 股） |
| `amount` | `amount` | `float()` | **千元**（Tushare `amount` 单位为千元） |
| `turnover_rate` | — | `None`（`daily` 不提供，需 `daily_basic`） | — |
| `volume_ratio` | — | `None`（同上） | — |

> **单位警示**：Tushare `vol`（手）与 `amount`（千元）与 TA-CN `stock_daily_quotes` 的 `volume`/`amount` 单位可能不同。Phase 1A 的 `DailyBar.from_ta_cn_doc` 直接透传 TA-CN 值。**本阶段不统一跨源单位**——每个 provider 的 `_to_canonical` 按该 provider 的原生单位填入 DailyBar，消费方需知悉跨源单位差异。统一单位属后续阶段（开放问题 OQ-2）。

#### 5.2.2 AKShare `stock_zh_a_hist` 映射

AKShare `ak.stock_zh_a_hist(symbol, period="daily", start_date, end_date, adjust="")` 返回列（中文）：`日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率`。

| DailyBar 字段 | AKShare 列 | 转换 | 单位/格式 |
|---|---|---|---|
| `symbol` | 入参 `symbol` | 透传（AKShare 用 6 位代码） | 6 位代码 |
| `trade_date` | `日期` | `"YYYY-MM-DD"` → `YYYYMMDD`（去横杠） | YYYYMMDD |
| `open/high/low/close` | `开盘/最高/最低/收盘` | `float()` | 元 |
| `pre_close` | — | 计算 `close - 涨跌额` 或 `None` | 元 |
| `change` | `涨跌额` | `float()` | 元 |
| `pct_chg` | `涨跌幅` | `float()` | 百分比 |
| `volume` | `成交量` | `float()` | **股**（AKShare 单位为股，与 Tushare 手不同！） |
| `amount` | `成交额` | `float()` | **元**（AKShare 单位为元，与 Tushare 千元不同！） |
| `turnover_rate` | `换手率` | `float()` | 百分比 |
| `volume_ratio` | — | `None` | — |

> **跨源单位不一致是已知风险**：Tushare vol=手、amount=千元；AKShare volume=股、amount=元。本阶段不归一化（单位 warnings 当前为 no-op，Router 不改约束下无法注入；DESIGN §3.7 裁定）。消费方自负跨源换算责任（OQ-2）。

#### 5.2.3 空值与字段缺失

- 任一 OHLCV 字段为 `None`/`NaN`/空字符串 → DailyBar 对应字段为 `None`（`_f()` helper 已处理，见 `DailyBar.from_ta_cn_doc`）。
- 整行关键字段（`close` 或 `trade_date`）缺失 → 该行丢弃，不计入 `list[DailyBar]`。
- 整个 raw_df 为空 → `_to_canonical` 返回空 list → provider fetch 抛 `ProviderUnavailableError`（DESIGN §3.6：适配 Router L809 `is not None` 检查），Router 捕获后继续 fallback。

### 5.3 限流、重试、超时

| 维度 | Tushare | AKShare |
|---|---|---|
| 限流 | RateLimiter（1B-A 已注入，默认 200 RPM，可配置） | RateLimiter（同上）+ 可选每请求延迟 |
| 重试 | `with_retry`（1B-A 框架）不覆盖 `ProviderUnavailableError`；网络抖动 → 单次失败 → Router fallback（DESIGN §3.8） | 同上 |
| 超时 | 单请求超时由 HTTP 客户端配置（默认 30s） | 同上 |
| 配额耗尽 | 抛 `ProviderUnavailableError`（触发 Router fallback） | N/A（无配额） |
| 网络超时 | 抛 `ProviderUnavailableError` | 同上 |
| API 内部错误 | 抛 `ProviderError` | 同上 |

> RateLimiter 与重试框架已在 1B-A 就位，1D 只在真实网络下验证其行为，不重构框架。

### 5.4 可用性判定（is_available）

沿用 Phase 1B-A 契约，**不改逻辑**：

- **TushareProvider**：`TUSHARE_TOKEN` 环境变量存在且非空 **AND** `tushare` 可 import。**只检查存在性，不读取/打印 token 值**（P-10）。
- **AKShareProvider**：`akshare` 可 import。

> 激活后 `is_available()` 仍只做结构性检查，**不做网络探测**——网络探测成本高且会消耗配额，由 `fetch()` 的异常路径处理。

### 5.5 DataResult 语义

| 场景 | `provider` | `freshness` | `source_trace` | `warnings` | `quality_score` |
|---|---|---|---|---|---|
| Tushare 成功 | `"tushare"` | `FreshnessPolicy.label(...)` | `["tushare(ok)"]` | `[]`（单位提示不注入，DESIGN §3.7） | `None`（Phase 2 才填充） |
| AKShare 兜底成功 | `"akshare"` | `label(...)` | `["tushare(unavailable: ...)", "akshare(ok)"]` | Router 既有警告（如 TA-CN fallback 提示） | `None` |
| 两源全失败 | `"error"` | `"empty"` | 完整 trace | `["all external providers failed"]` | `None` |
| 两源全空 | `"error"` | `"empty"` | `["tushare(unavailable: empty payload...)", "akshare(unavailable: empty payload...)"]` | `["no data from any provider"]` | `None` |

> `quality_score` 在 Phase 1D 保持 `None`（Phase 2 QualityScorer 才填充）；本阶段**不**在 Router 出口注入 QualityScorer。

### 5.6 凭据与安全

| 凭据 | 来源 | 处理 |
|---|---|---|
| Tushare token | 环境变量 `TUSHARE_TOKEN`（变量名可经构造参数覆盖，用于测试） | provider 经环境变量名读取，传给可注入 HTTP 客户端；**不记录、不回显、不打印**；`is_available()` 只检查存在性 |
| AKShare | 无需 token | — |

**P-10 硬约束**：
- 凭据值**不得**出现在 task metadata、kanban summary、审计日志、测试 fixture、错误信息中。
- 测试用 monkeypatch 设环境变量或注入 fake 客户端，**不**用真实 token 跑单测。
- 错误信息（如 `ProviderUnavailableError`）只描述类别（「quota exceeded」「timeout」），不含 token。

### 5.7 `datetime.utcnow()` 技术债

当前 `local_mongo_adapter.py`、`cache_manager.py` 各有 2 处 `datetime.utcnow()`（naive UTC，Python 3.12 已弃用）。**本阶段不改造这些站点**，理由：
- 1D 不触 LocalMongoAdapter / CacheManager（两者属 1B-B，且本阶段不写入）。
- Router / models / freshness 的 `datetime.now(timezone.utc).replace(tzinfo=None)` 是 UTC-aware 后剥 tz，语义等价且非弃用路径。
- 统一 UTC-aware 改造是横切关注点，应作为独立技术债卡处理，避免扩散 1D 范围。

OQ-3 记录后续改造项。

## 6. AI 实装规范（AI Implementation Rules）

### 6.1 必须执行
- 单指令只做一件事，使用相对路径。
- 代码简洁可控，命名语义化。
- 核心逻辑（字段映射、空值处理、异常分类）补充单元测试。
- 所有变更保留可追溯记录。

### 6.2 先询问再执行
- 修改数据结构、新增第三方依赖（`tushare` / `akshare` 的安装属运行环境配置，由 Pascal 授权）。
- 变更对外接口、影响现有业务逻辑。
- 涉及密钥、权限、配置变更。

### 6.3 绝对禁止
- 硬编码敏感密钥与凭证。
- 随意删除历史文件与目录。
- 无方案大范围重构代码。
- **制造或静默返回 stub/假数据**冒充真实外部数据。
- 真实网络 smoke 未经 Pascal 单独授权在生产环境运行。

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| Tushare/AKShare 列名或单位变更（API 漂移） | 中 | 高 | 字段映射表在 SPEC 固化；映射代码加列存在性校验，缺失列抛明确错误 | 缺失关键字段 → 该 provider 视为失败，Router fallback |
| 跨源单位不一致（Tushare 手/千元 vs AKShare 股/元）被消费方误用 | 高 | 高 | DESIGN §3.4 显式标注单位；DESIGN §3.7 no-op 裁定（Router 不改约束下无法注入 warning） | 不归一化（OQ-2） |
| 真实网络 smoke 不稳定（限流、波动）导致 flaky | 中 | 中 | smoke 是后续受控项，不进 CI；单测用 fake 客户端 | smoke 失败不阻断本卡 |
| token 泄露到日志/metadata | 低 | 高 | P-10：is_available 只检查存在性；错误信息脱敏；测试不用真实 token | 审计审查 |
| Router L809 空 list 误判 | 中 | 高 | DESIGN §3.6：空 payload raise ProviderUnavailableError，UT-TP-202/AK-202/DR-305 覆盖 | 已实现，已验证 |
| 限流/重试在真实网络下行为偏差 | 中 | 中 | 1D 在真实网络下验证；超时/重试参数可配置 | 框架沿用 1B-A，可回退 |
| `datetime.utcnow()` 技术债扩散 | 低 | 低 | 本阶段不改造，OQ-3 记录 | 独立技术债卡 |

## 8. 备选方案（Alternatives Considered）

### 8.1 方案 B：一次性激活全部 13 条 Tushare capability
- **优点**：减少阶段数，消费方一次获得全部外部能力。
- **缺点**：风险大、测试矩阵爆炸（13 capability × 2 provider × 异常路径）；字段映射契约需一次性固化 13 套；违背「最小切片验证」原则。
- **不选原因**：`kline_daily` 是最核心、最高频的能力，先把它做透，再增量激活其余。

### 8.2 方案 C：不引入可注入 HTTP 客户端，直接在 `fetch()` 内调 `tushare.pro_api()`
- **优点**：代码更短。
- **缺点**：无法用 fake 客户端单测；真实网络 smoke 成为唯一验证手段，违反「测试分层」与「真实 smoke 非执行前提」。
- **不选原因**：违背 Phase 1B-A「框架 + fake 验证」哲学；可注入客户端是 fake/真实分离的标准模式。

### 8.3 方案 D：归一化跨源单位（Tushare 手→股、千元→元）
- **优点**：消费方无需知悉源差异。
- **缺点**：归一化逻辑会增加 provider 复杂度；TA-CN 的单位也需纳入考量；归一化口径需 Pascal 确认（手 vs 股、千元 vs 元哪个为 canonical）。
- **不选原因**：本阶段保持 DailyBar 透传 provider 原生单位，归一化属后续跨源一致性阶段（OQ-2）。

## 9. 验收标准（Acceptance Criteria）

### 9.1 本 RFC 阶段验收（RFC 自身）
- [x] RFC 文件存在于 `docs/rfc/03_data/RFC-03-012-unified-data-phase-1d-external-provider-activation.md`。
- [x] RFC 解释了命名为 Phase 1D 的衔接（§2.3）。
- [x] RFC 与 RFC-03-007 六项不变量可追溯映射（§11）。
- [x] RFC 明确首批能力只限 `CN + market_data.kline_daily`（§3.1）。
- [x] RFC 明确 Tushare 主源 → AKShare 兜底的降级语义（§5.1）。
- [x] RFC 固化 Tushare/AKShare → DailyBar 字段映射契约（§5.2）。
- [x] RFC 明确凭据/限流/重试/超时/单位风险模型（§5.3/§5.6）。
- [x] RFC 明确生产副作用矩阵（§9.3）。
- [x] 中文输出，专业简洁。

### 9.2 后续阶段验收（已通过 SPEC/Design/Implement/Verify）
- [x] Tushare/AKShare 的 `kline_daily` 真实调用经可注入 HTTP 客户端实现（`kline_client.py`，48 项测试 PASS）。
- [x] 字段映射表（§5.2）在 SPEC §4.3 / DESIGN §3.4 固化为可执行契约。
- [x] fake HTTP 客户端 + Router fallback 单测共 48 项覆盖全部路径（PASS）。
- [x] Router fallback 测试全路径矩阵（UT-DR-301~309 全部 PASS）。
- [x] 数据合理性断言覆盖字段一致性、非空性、关键字段非 None（§9.3 对齐）。
- [x] DataResult 语义与 §5.5 矩阵一致（quality_score 恒 None 已验证）。

### 9.3 生产副作用矩阵（本阶段严禁）

| 动作 | 本阶段 | 后续授权 |
|---|---|---|
| MongoDB DDL（createCollection/createIndex） | ❌ 严禁 | 需 Pascal 单独授权（Phase 1B-B / Phase 2 已有流程） |
| 真实 MongoDB 写入（materialization/cache/audit/quality_summary） | ❌ 严禁 | 同上 |
| AuditLogger 真实写入 | ❌ 严禁 | Phase 2 授权流程 |
| QualitySummary 启用 | ❌ 严禁 | Phase 2 授权流程 |
| cron/systemd/webhook 调度 | ❌ 严禁 | 独立授权 |
| **真实 Tushare/AKShare 只读 smoke（API 调用）** | ⚠️ 受控验证项 | **需 Pascal 单独批准**；不作为本卡或实现卡的执行前提 |

> 真实 API 只读 smoke 会消耗 Tushare 配额并产生外部网络调用，属「需 Pascal 单独批准的动作」，在本卡与实现卡中均以 fake 客户端验证为主，真实 smoke 留待 Pascal 授权后单独执行。

## 10. 开放问题（Open Questions）

1. **[已关闭] stub docstring 措辞同步**：`tushare.py` / `akshare.py` / `base_external.py` 的 docstring 已由 Phase 1D 实现同步更新为「Phase 1D」。无需额外维护 pass。
2. **跨源单位归一化**：Tushare（手/千元）与 AKShare（股/元）单位不一致，本阶段不归一化。后续是否引入 canonical 单位（如统一为股/元）需 Pascal 决策，并同步影响 TA-CN `stock_daily_quotes` 的单位语义。
3. **`datetime.utcnow()` 技术债**：`local_mongo_adapter.py` / `cache_manager.py` 共 4 处 naive UTC，本阶段不改造。建议作为独立技术债卡，统一 UTC-aware 改造。
4. **[已关闭] HTTP 客户端抽象形态**：Design 裁定为 `typing.Protocol`（`KlineClient`）。DESIGN-03-012 §3.3.1。

## 11. 与 RFC-03-007 六项不变量的可追溯映射

RFC-03-007 §14 / SPEC-03-007 §0.2 的六项架构基线不变量，Phase 1D 的体现：

| # | 不变量 | Phase 1D 的体现 |
|---|---|---|
| 1 | **共享物理数据库** `tradingagents` | 1D 不新增任何集合；TA-CN adapter 只读复用（Step 1，不变） |
| 2 | **Internal-First 读取路径** | kline_daily 真实外部调用只在 Step 4 或 forced-provider 分支触发；TA-CN 优先级、`force_refresh` 跳过内部源语义不变 |
| 3 | **DSA 不是运行时数据源** | external_fallback_chains 只含 `["tushare", "akshare"]`；DSA 不出现在任何链路 |
| 4 | **Collection Ownership 不可回写** | 1D 不写任何集合；TA-CN 无前缀集合只读 |
| 5 | **Task Center 先行** | 1D 不实现 Task Center、不创建 Job、不启用 cron/systemd |
| 6 | **三层语义分离** | 1D 不触碰 `03_data_ud_*` / `03_data_ud_cache_*`；TA-CN 既有集合（Step 1 只读）与外部 provider（Step 4）边界清晰 |

## 12. 参考资料（References）

- RFC-03-007：`docs/rfc/03_data/RFC-03-007-unified-data-layer.md`（Unified Data Layer 总纲，六项不变量 §14）
- RFC-03-008：`docs/rfc/03_data/RFC-03-008-unified-data-phase-1b-query-plane.md`（Phase 1B-A 查询平面，provider 框架）
- RFC-03-009：`docs/rfc/03_data/RFC-03-009-unified-data-phase-1b-persistence-plane.md`（Phase 1B-B 持久化缓存平面，命名锁定）
- RFC-03-010：`docs/rfc/03_data/RFC-03-010-unified-data-phase-1c-e2e-validation.md`（Phase 1C 端到端验收，Sector Router 边界）
- RFC-03-011：`docs/rfc/03_data/RFC-03-011-unified-data-phase-2-quality-audit-governance.md`（Phase 2 质量与审计，`quality_score` 填充归属）
- DESIGN-03-012：`docs/design/03_data/DESIGN-03-012-unified-data-phase-1d-external-provider-activation.md`（Phase 1D 详细设计，含 §3.6 Router gap 解决、§8 待决项裁定）
- 现有代码：
  - `skills/data/unified_data/providers/tushare.py`（Phase 1D kline_daily 激活态，13 capability）
  - `skills/data/unified_data/providers/akshare.py`（Phase 1D kline_daily 激活态，7 capability）
  - `skills/data/unified_data/providers/base_external.py`（`_to_canonical` hook）
  - `skills/data/unified_data/providers/_stub_columns.py`（stub schema）
  - `skills/data/unified_data/providers/kline_client.py`（KlineClient Protocol + FakeKlineClient + TushareKlineClient + AKShareKlineClient）
  - `skills/data/unified_data/router.py`（internal-first 编排，`provider.fetch` 调用点 L906）
  - `skills/data/unified_data/models/domain/market_data.py`（`DailyBar` canonical）
  - `skills/data/unified_data/models/__init__.py`（`DataResult.success` / `.error`）
- Tushare `daily` 接口文档：https://tushare.pro/document/2?doc_id=27
- AKShare `stock_zh_a_hist` 接口文档：https://akshare.akfamily.xyz/data/stock/stock.html
