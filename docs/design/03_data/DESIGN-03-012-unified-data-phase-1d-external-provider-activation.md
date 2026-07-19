# DESIGN-03-012: Unified Data Phase 1D — CN 日线真实外部 Provider 激活

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Final |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-18 |
| 最后更新 | 2026-07-20 |
| 来源 RFC | RFC-03-012 V0.2（Phase 1D External Provider Activation，Final） |
| 来源 SPEC | SPEC-03-012 V0.2（Phase 1D External Provider Activation，Final） |
| 关联 RFC | RFC-03-007（总纲）、RFC-03-008（1B-A）、RFC-03-009（1B-B 命名锁定）、RFC-03-011（Phase 2 quality_score 归属） |
| 关联 Design | DESIGN-03-007 / DESIGN-03-008 / DESIGN-03-009 / DESIGN-03-010 / DESIGN-03-011 |
| 目标模块 | unified_data（`skills/data/unified_data/providers/`） |
| 版本号 | V0.2 |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

### 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.2 | 2026-07-20 | T2.1 契约措辞修正：将 §1 item 5、§2.3 兼容性风险表、§3.3.5 参数注释中「单位 warnings 默认开启」的语义残留统一修正为「构造参数保留但当前版本为 no-op，不注入 DataResult.warnings」。RFC-03-012 V0.2 / SPEC-03-012 V0.2 已锁定 no-op 契约，本次仅对齐 Design 措辞。 | YQuant-Principal |
| V0.2 | 2026-07-20 | T2 收口定稿。基于 T1 已定稿的 RFC-03-012 V0.2 / SPEC-03-012 V0.2 审定并更新 Design：元数据状态 Final；测试路径修正（`tests/data/unified_data/` → `skills/data/unified_data/tests/` 对齐近期迁移）；§4 实现计划标为已完成（48 项测试 PASS，代码已交付）；§5.1 测试路径对齐；新增版本历史。 | YQuant-Principal |
| V0.1 | 2026-07-18 | 初始创建。将 RFC-03-012 / SPEC-03-012 的 Phase 1D 需求落为文件级、函数级、签名级的可实现方案；裁定 SPEC §12 七项待决项；发现 Router L809 空 list gap 并给出 empty-payload-raise 方案；完成单位标注 no-op 裁定。 | YQuant-Principal |

---

## 1. 设计摘要

本设计把 RFC-03-012 / SPEC-03-012 的 Phase 1D 需求（CN `market_data.kline_daily` 真实外部 Provider 激活）落为文件级、函数级、签名级的可实现方案。核心设计决策（含对 SPEC §12 七个待决项的裁定）：

1. **HTTP 客户端用 `typing.Protocol`**（`KlineClient`），与 SPEC §4.4 一致。Protocol 提供结构子类型，Fake / 真实 Tushare / 真实 AKShare 三个实现不需显式继承，延迟 SDK import 避免模块级依赖。
2. **真实客户端与 Protocol/Fake 同居 `kline_client.py`**：单文件包含抽象 + 全部实现，真实 SDK import 放在方法体内（延迟 import，与 `is_available()` 的 import guard 模式一致）。
3. **Tushare 用 `pro_api(token).daily(...)`**（非 `pro_bar`）；`daily` 返回不复权口径，与 SPEC §0 锁定一致。
4. **AKShare 用 `stock_zh_a_hist(symbol, period="daily", adjust="")`**：`adjust=""` 不复权，与 Tushare `daily` 口径对齐；`trade_date` 统一转 `YYYYMMDD`（与 DailyBar TA-CN 路径一致，消费方无需判断格式）。
5. **单位 warnings 构造参数 `emit_unit_warning: bool = True` 保留，但当前版本为 no-op**（Router 不改约束下无法注入 `DataResult.warnings`；参数留作未来扩展点，见 §3.7）。
6. **`_to_canonical` 子类各自 override + 内部 capability 分支**：base 类保留 no-op（向后兼容，不破坏未来其他 capability 的 stub 路径）；Tushare/AKShare 子类 override 后按 `kline_daily` vs 其余分支。
7. **Router 包装 `list[DailyBar]` 确认可行**：`router.py:806-824` 把 `provider.fetch(...)` 返回值直接装入 `DataResult.data`，与 TA-CN `get_daily_bars` 路径（返回 `list[DailyBar]`）完全一致；Router 不改。
8. **【关键 gap 发现】空 payload 适配 Router `is not None` 检查**：`router.py:809` 用 `if result_data is not None` 判定成功，空 list `[]` 会被误判为成功（不触发 fallback）。Design 决策：provider.fetch 的 kline_daily 分支在空 payload 时 **raise `ProviderUnavailableError`**（而非返回空 list），让 Router 捕获后记 trace 并继续 fallback。详见 §3.6。

本设计**零生产副作用**：无 Mongo DDL/写入、无真实 API smoke（受控验证项）、无依赖安装、无调度。把后续真实只读 smoke、依赖安装、生产 audit rollout 列为显式门禁（§6.6）。

---

## 2. 现状分析

### 2.1 相关文件

| 文件 | 行数（约） | 状态 |
|---|---|---|
| `skills/data/unified_data/providers/tushare.py` | 146 | 1B-A stub；`fetch()` 调 `stub_dataframe_for()` 返回空壳 DataFrame；docstring 标注「Phase 1B-B」（命名残留，1D 顺手修正） |
| `skills/data/unified_data/providers/akshare.py` | 121 | 1B-A stub；同上 |
| `skills/data/unified_data/providers/base_external.py` | 103 | `_to_canonical` no-op 透传；docstring 标注「Phase 1B-B」 |
| `skills/data/unified_data/providers/_stub_columns.py` | 120 | stub schema 定义；不改 |
| `skills/data/unified_data/providers/rate_limiter.py` | 189 | `RateLimiter` + `with_retry`；不改（沿用 1B-A） |
| `skills/data/unified_data/providers/__init__.py` | 166 | 包导出 + `STUB_COLUMNS` 副本；新增 kline_client 符号导出 |
| `skills/data/unified_data/router.py` | 1194 | **不改**；关键调用点 L806-824（外部链成功分支）、L906（`provider.fetch` 调用）、L889-915（`_attempt_provider_fetch` 异常→trace） |
| `skills/data/unified_data/models/domain/market_data.py` | 189 | `DailyBar` canonical（13 字段）；不改 |
| `skills/data/unified_data/__init__.py` | 150 | 顶层导出；新增 `KlineClient` / `FakeKlineClient` |

### 2.2 现有约束

- **Router 不改**（SPEC §4.6 / §7.3）：`_query_external_chain`、`_attempt_provider_fetch`、`_query_external_single` 签名与行为完全冻结。Provider 必须适配 Router 现有契约，不能要求 Router 适配 Provider。
- **`_attempt_provider_fetch` 返回值语义**（router.py:889-915）：成功 → 返回 `provider.fetch(...)` 的返回值（任意类型）；失败 → 捕获三类异常后返回 `None` 并 append trace。**不捕获的异常**（非 `UnsupportedCapabilityError`/`ProviderUnavailableError`/`ProviderError`）会逃逸到 `_query_external_chain`，破坏 fallback 链——provider 必须确保所有失败路径归一化到这三类异常。
- **`RateLimiter` / `with_retry` 已就位**（rate_limiter.py）：`_RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError)`；`ProviderError` 明确**不在**重试集合（设计意图：caller-visible 失败立即上抛）。`ProviderUnavailableError` 同样不在重试集合——这意味着配额耗尽/超时若归为 `ProviderUnavailableError`，**不会被 `with_retry` 自动重试**，需要 provider 在 fetch 内部显式编排重试或接受单次失败。
- **`DailyBar` 已定义**（market_data.py:92-138）：13 字段，`from_ta_cn_doc` 用 `_f()` helper 处理数值/None 转换。Phase 1D 的 `_to_canonical` 复用 `_f()` 语义（None/NaN/空字符串 → None；非数值抛 `ValueError`）。
- **tushare/akshare 包未安装**：当前环境无这两个包；`is_available()` 返回 False（预期）。激活代码用延迟 import，模块级不依赖安装。
- **`TUSHARE_TOKEN` 环境变量**：生产由 Pascal 授权后配置；测试用 monkeypatch 设非空字符串（不用真实 token）。

### 2.3 兼容性风险

| 风险项 | 等级 | 缓解 |
|---|---|---|
| Router L809 `is not None` 把空 list 误判为成功 | **高** | §3.6 Design 决策：空 payload raise `ProviderUnavailableError` |
| 1B-A 测试对 kline_daily 返回 stub DataFrame 的断言失效 | 中 | §5.4 回归：1B-A `test_providers.py` 中 kline_daily 相关断言需更新为 list[DailyBar] |
| `_to_canonical` 签名变更（返回类型从 DataFrame 到 list[DailyBar] \| DataFrame）破坏 base 类契约 | 中 | §3.3：base 保留 no-op，子类 override 返回类型按 capability 分支；base 签名加 `Any` 返回标注 |
| 跨源单位不一致（手/股、千元/元）被消费方误用 | 高 | §3.7 单位 warnings 当前为 no-op（参数保留但不注入 `DataResult.warnings`）+ SPEC §0 声明 + OQ-2 |
| 真实网络下 `with_retry` 不覆盖 `ProviderUnavailableError` 导致配额耗尽不重试 | 中 | §3.8：接受现状（配额耗尽不应重试），文档标注 |
| 延迟 import 在高并发下首次调用的 import 开销 | 低 | `is_available()` 已做 import guard；fetch 内 import 复用已加载模块 |

---

## 3. 方案设计

### 3.1 模块/文件改动清单（精确）

#### 新增文件（4 个）

| 路径 | 说明 |
|---|---|
| `skills/data/unified_data/providers/kline_client.py` | `KlineClient` Protocol + `FakeKlineClient` + `TushareKlineClient` + `AKShareKlineClient`（单文件，真实 SDK 延迟 import） |
| `skills/data/unified_data/tests/test_kline_client.py` | FakeKlineClient / TushareKlineClient / AKShareKlineClient 单测（含列名校验、空 DataFrame、异常注入、token 不泄露） |
| `skills/data/unified_data/tests/test_providers_kline_daily.py` | TushareProvider/AKShareProvider 的 kline_daily 激活路径单测（注入 FakeKlineClient，覆盖字段映射、空值、缺失列、行丢弃、单位标注、其余 capability 保持 stub） |
| `skills/data/unified_data/tests/test_router_kline_daily_fallback.py` | Router fallback：kline_daily 链 tushare→akshare 全路径矩阵（UT-DR-301~309） |

#### 修改文件（5 个）

| 路径 | 修改内容 |
|---|---|
| `skills/data/unified_data/providers/tushare.py` | ① docstring「Phase 1B-B」→「Phase 1D」（OQ-1 顺手）；② `__init__` 新增 `http_client: KlineClient \| None = None` + `request_timeout_seconds: float = 30.0` + `emit_unit_warning: bool = True` 可选参数（向后兼容）；③ `fetch()` 入口按 capability 分支：`kline_daily` 走真实路径（`_rate_limiter.acquire()` → `self._http_client.get_kline_daily(...)` → `_to_canonical_tushare(...)` → 空 raise `ProviderUnavailableError`），其余走既有 stub 路径；④ 新增 `_to_canonical_tushare(raw_df, capability)` 实现 Tushare 列 → list[DailyBar]（§3.4.1 映射表） |
| `skills/data/unified_data/providers/akshare.py` | 同上（kline_daily 激活；`_to_canonical_akshare` 实现 AKShare 中文列 → list[DailyBar]，含 trade_date YYYYMMDD 转换；docstring 措辞同步） |
| `skills/data/unified_data/providers/base_external.py` | ① docstring「Phase 1B-B」→「Phase 1D」；② `_to_canonical` 返回标注从 `pd.DataFrame` 放宽为 `Any`（支持子类返回 list[DailyBar]）；③ 注释说明 base 保持 no-op，子类按 capability override。**不改方法体逻辑** |
| `skills/data/unified_data/providers/__init__.py` | 导出 `KlineClient`、`FakeKlineClient`、`TushareKlineClient`、`AKShareKlineClient`（加入 `__all__`） |
| `skills/data/unified_data/__init__.py` | 导出 `KlineClient`、`FakeKlineClient`（真实客户端不顶层导出，避免触发顶层 import；消费方按需从 providers.kline_client 导入） |

#### 不改动文件（明确列出，对齐 SPEC §7.3）

`router.py` / `registry.py` / `freshness.py` / `client.py` / `models/**` / `adapters/**` / `local_mongo_adapter.py` / `cache_manager.py` / `audit/**` / `quality/**` / `config.py` / `exceptions.py` / `provider.py` / `_stub_columns.py` / `rate_limiter.py` / `skills/apps/TradingAgents-CN/**` / RFC/SPEC/Design 模板 / RFC-03-012 / SPEC-03-012。

> **base_external.py 的改动边界**：只改 docstring 措辞 + 类型标注 + 注释，**不改方法体逻辑**。这是 Design 的刻意决定——base 类的 no-op `_to_canonical` 是「子类未 override 时的安全默认」，保留它能保证未来新增的 provider 在未实现 canonical 映射前不会崩溃。子类 override 在自身类体内完成，不污染 base。

### 3.2 类图与控制流

```
┌─────────────────────────────────────────────────────────────────────┐
│                DataRouter（不改，1B-A/1B-B 既有）                     │
│   query(..., capability="market_data.kline_daily")                   │
│     └─ Step 4: _query_external_chain()                               │
│          └─ _attempt_provider_fetch(provider, ...)                   │
│               └─ provider.fetch("market_data","kline_daily",sid,**p) │
│                   [透明：对 list[DailyBar] 与 DataFrame 均无感知]      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
┌───────────────────────┐     ┌───────────────────────┐
│  TushareProvider       │     │  AKShareProvider       │
│  fetch() 入口分支:     │     │  fetch() 入口分支:     │
│   capability ==        │     │   capability ==        │
│   "market_data.        │     │   "market_data.        │
│    kline_daily"?       │     │    kline_daily"?       │
│   ├─ 是 → 真实路径     │     │   ├─ 是 → 真实路径     │
│   └─ 否 → stub 路径    │     │   └─ 否 → stub 路径    │
│                        │     │                        │
│  真实路径:             │     │  真实路径:             │
│   1. _check_capability │     │   1. _check_capability │
│   2. is_available()    │     │   2. is_available()    │
│      (Router 已查)     │     │      (Router 已查)     │
│   3. _rate_limiter     │     │   3. _rate_limiter     │
│      .acquire()        │     │      .acquire()        │
│   4. _http_client      │     │   4. _http_client      │
│      .get_kline_daily  │     │      .get_kline_daily  │
│   5. _to_canonical_    │     │   5. _to_canonical_    │
│      tushare(df)       │     │      akshare(df)       │
│      → list[DailyBar]  │     │      → list[DailyBar]  │
│   6. 空 → raise        │     │   6. 空 → raise        │
│      ProviderUnavail   │     │      ProviderUnavail   │
│      ableError         │     │      ableError         │
└──────────┬─────────────┘     └──────────┬─────────────┘
           │                              │
           ▼                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    KlineClient (Protocol)                            │
│   get_kline_daily(security_id, start_date?, end_date?, limit?)       │
│   → pd.DataFrame（provider 原生列）                                   │
│   raises: ProviderUnavailableError / ProviderError                   │
└──────┬──────────────┬──────────────────┬────────────────────────────┘
       │              │                  │
       ▼              ▼                  ▼
┌──────────────┐ ┌────────────────┐ ┌─────────────────┐
│FakeKline     │ │TushareKline    │ │AKShareKline     │
│Client        │ │Client          │ │Client           │
│(测试)        │ │(生产, 延迟      │ │(生产, 延迟       │
│ fixture      │ │ import tushare)│ │ import akshare) │
│ 返回/异常    │ │ pro_api(token) │ │ stock_zh_a_hist │
│ 不读环境     │ │ .daily(...)    │ │ (adjust="")     │
│              │ │ token 不回显   │ │ 无 token        │
└──────────────┘ └────────────────┘ └─────────────────┘
```

### 3.3 接口与数据结构

#### 3.3.1 `KlineClient` Protocol（新增，`kline_client.py`）

```python
from typing import Protocol, Any
import pandas as pd

class KlineClient(Protocol):
    """可注入的 kline_daily HTTP 客户端抽象（Phase 1D）。

    三种实现：
    - TushareKlineClient：生产，延迟 import tushare，调 pro_api(token).daily(...)
    - AKShareKlineClient：生产，延迟 import akshare，调 stock_zh_a_hist(adjust="")
    - FakeKlineClient：测试，按 fixture 返回，不读环境变量

    所有实现不得在异常信息中泄露 token。
    """

    def get_kline_daily(
        self,
        security_id: Any,  # SecurityId，用 Any 避免 Protocol 层硬依赖 models
        start_date: str | None = None,   # YYYYMMDD（统一格式，见 §3.4）
        end_date: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """返回 provider 原生列的 DataFrame。

        Raises:
            ProviderUnavailableError: 网络/超时/配额耗尽/空 payload 上抛层
            ProviderError: API 内部错误 / 缺失关键列
        """
        ...
```

> **Protocol 而非 ABC 的理由**：Protocol 提供结构子类型，FakeKlineClient 不需显式 `class FakeKlineClient(KlineClient)` 继承（鸭子类型即可），减少测试 fixture 的样板代码。真实客户端也不继承，靠结构匹配。

#### 3.3.2 `FakeKlineClient`（测试用，`kline_client.py`）

```python
class FakeKlineClient:
    """测试用 KlineClient 实现，按配置返回 DataFrame 或抛异常。

    不读环境变量、不发网络。构造时传入 fixture DataFrame 或 exception。
    """

    def __init__(
        self,
        *,
        dataframe: pd.DataFrame | None = None,
        exception: Exception | None = None,
    ) -> None:
        self._df = dataframe
        self._exc = exception
        self.call_log: list[dict] = []  # 记录调用参数，便于测试断言

    def get_kline_daily(
        self,
        security_id: Any,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        self.call_log.append({
            "security_id": security_id,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        })
        if self._exc is not None:
            raise self._exc
        if self._df is None:
            return pd.DataFrame()  # 空 DataFrame
        return self._df.copy()
```

#### 3.3.3 `TushareKlineClient`（生产，`kline_client.py`）

```python
class TushareKlineClient:
    """真实 Tushare kline_daily 客户端。延迟 import tushare。

    token 经构造注入（来自环境变量，由 provider 读取后传入），
    客户端本身不读环境变量，便于测试与解耦。
    """

    def __init__(
        self,
        token: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        if not token or not token.strip():
            raise ProviderUnavailableError("tushare token missing")
        self._token = token  # 不打印、不回显、不记录日志
        self._timeout = timeout

    def get_kline_daily(
        self,
        security_id: Any,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        import tushare as ts  # 延迟 import
        ts_code = _to_tushare_ts_code(security_id)  # 600519 → "600519.SH"
        kwargs = {"ts_code": ts_code}
        if start_date:
            kwargs["start_date"] = start_date  # YYYYMMDD
        if end_date:
            kwargs["end_date"] = end_date
        if limit:
            kwargs["limit"] = limit
        try:
            pro = ts.pro_api(self._token)
            df = pro.daily(**kwargs)
        except Exception as exc:
            # 异常分类：配额/网络 → ProviderUnavailableError；其余 → ProviderError
            msg = str(exc).lower()
            if any(k in msg for k in ("quota", "limit", "timeout", "connection")):
                raise ProviderUnavailableError("tushare API unavailable") from exc
            raise ProviderError(f"tushare daily API error") from exc
        return df if df is not None else pd.DataFrame()
```

> **凭据（token）处理**：token 由 provider 从环境变量读取后注入 client 构造参数（对应 RFC §5.6 / SPEC §7.2 的凭据安全约束）。client 不读环境变量、不记录 token、异常 message 脱敏（只描述类别）。这符合 P-10：provider 层 `is_available()` 只检查凭据存在性，fetch 层经 client 消费但不回显、不泄露。

#### 3.3.4 `AKShareKlineClient`（生产，`kline_client.py`）

```python
class AKShareKlineClient:
    """真实 AKShare kline_daily 客户端。延迟 import akshare。无 token。"""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def get_kline_daily(
        self,
        security_id: Any,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        import akshare as ak  # 延迟 import
        symbol = security_id.symbol  # 6 位代码
        kwargs = {"symbol": symbol, "period": "daily", "adjust": ""}
        if start_date:
            kwargs["start_date"] = start_date  # YYYYMMDD
        if end_date:
            kwargs["end_date"] = end_date
        try:
            df = ak.stock_zh_a_hist(**kwargs)
        except Exception as exc:
            msg = str(exc).lower()
            if any(k in msg for k in ("timeout", "connection", "network")):
                raise ProviderUnavailableError("akshare API unavailable") from exc
            raise ProviderError(f"akshare stock_zh_a_hist error") from exc
        return df if df is not None else pd.DataFrame()
```

> **`limit` 参数**：AKShare `stock_zh_a_hist` 不支持 `limit` 参数（只支持日期范围）。Design 决策：`limit` 在 AKShare 客户端被忽略（不传给 SDK），由 provider 层的 `_to_canonical` 在转换后截断（`list[:limit]`）。测试需覆盖 `limit` 传入时 AKShare 路径仍正确截断。

#### 3.3.5 Provider 构造参数扩展（`tushare.py` / `akshare.py`）

TushareProvider 构造新增（向后兼容，全部可选）：

```python
def __init__(
    self,
    *,
    rate_limit_rpm: int = 200,           # 沿用 1B-A
    retry_max_attempts: int = 3,         # 沿用 1B-A
    retry_backoff_base: float = 1.0,     # 沿用 1B-A
    token_env: str = DEFAULT_TOKEN_ENV,  # 沿用 1B-A
    http_client: KlineClient | None = None,        # [1D 新增] None → 默认 TushareKlineClient
    request_timeout_seconds: float = 30.0,         # [1D 新增]
    emit_unit_warning: bool = True,                # [1D 新增] 当前为 no-op（保留构造参数，Phase 1D 不注入 DataResult.warnings，见 §3.7）
) -> None:
```

AKShareProvider 构造新增（同理，无 `token_env`）：

```python
def __init__(
    self,
    *,
    rate_limit_rpm: int = 200,
    retry_max_attempts: int = 3,
    retry_backoff_base: float = 1.0,
    http_client: KlineClient | None = None,        # [1D 新增] None → 默认 AKShareKlineClient
    request_timeout_seconds: float = 30.0,
    emit_unit_warning: bool = True,
) -> None:
```

> **默认 client 的延迟构造**：`http_client=None` 时，provider 不在 `__init__` 立即构造真实 client（避免 token 读取副作用）。在 `fetch()` 的 kline_daily 分支首次调用时，检查 `self._http_client is None` → 构造默认真实 client 并缓存到 `self._http_client`。这样 `is_available()=False` 时永远不会构造真实 client。

### 3.4 字段映射契约（Tushare / AKShare → DailyBar）

#### 3.4.1 Tushare `daily` → DailyBar（锁定 SPEC §4.3.1）

| DailyBar 字段 | Tushare 列 | 转换 | 单位 | 缺失处理 |
|---|---|---|---|---|
| `symbol` | `ts_code` | 去后缀（`"600519.SH"` → `"600519"`） | 6 位代码 | 必填；缺列→`ProviderError("missing required column: ts_code")` |
| `trade_date` | `trade_date` | 透传（`"YYYYMMDD"`） | YYYYMMDD | 必填；缺列→`ProviderError`；行值空→该行丢弃 |
| `open` | `open` | `_f()` | 元 | None |
| `high` | `high` | `_f()` | 元 | None |
| `low` | `low` | `_f()` | 元 | None |
| `close` | `close` | `_f()` | 元 | 关键字段；None→该行丢弃 |
| `pre_close` | `pre_close` | `_f()` | 元 | None |
| `change` | `change` | `_f()` | 元 | None |
| `pct_chg` | `pct_chg` | `_f()` | 百分比（已×100） | None |
| `volume` | `vol` | `_f()` | **手**（1手=100股） | None |
| `amount` | `amount` | `_f()` | **千元** | None |
| `turnover_rate` | — | `None` | — | 恒 None（daily 不提供） |
| `volume_ratio` | — | `None` | — | 恒 None |

> **`_f()` 复用**：从 `models/domain/market_data.py` 导入 `_f` helper（或复制等价逻辑）。None/NaN/空字符串 → None；非数值字符串 → `ValueError`（由 provider 捕获后转 `ProviderError`）。

#### 3.4.2 AKShare `stock_zh_a_hist` → DailyBar（锁定 SPEC §4.3.2）

| DailyBar 字段 | AKShare 列 | 转换 | 单位 | 缺失处理 |
|---|---|---|---|---|
| `symbol` | 入参 `security_id.symbol` | 透传 | 6 位代码 | 必填 |
| `trade_date` | `日期` | `"YYYY-MM-DD"` → `"YYYYMMDD"`（去横杠） | YYYYMMDD | 必填；缺列→`ProviderError("missing required column: 日期")`；行值空→丢弃 |
| `open` | `开盘` | `_f()` | 元 | None |
| `high` | `最高` | `_f()` | 元 | None |
| `low` | `最低` | `_f()` | 元 | None |
| `close` | `收盘` | `_f()` | 元 | 关键字段；None→该行丢弃 |
| `pre_close` | — | `close - 涨跌额`（若 `涨跌额` 可用）或 `None` | 元 | None |
| `change` | `涨跌额` | `_f()` | 元 | None |
| `pct_chg` | `涨跌幅` | `_f()` | 百分比 | None |
| `volume` | `成交量` | `_f()` | **股** | None |
| `amount` | `成交额` | `_f()` | **元** | None |
| `turnover_rate` | `换手率` | `_f()` | 百分比 | None |
| `volume_ratio` | — | `None` | — | 恒 None |

> **trade_date 统一为 YYYYMMDD**（SPEC §12 待决项 #4 裁定）：AKShare 原生返回 `"YYYY-MM-DD"`，Design 决策统一去横杠转 `YYYYMMDD`，与 DailyBar TA-CN 路径（`stock_daily_quotes` 用 YYYYMMDD）一致。消费方拿到 `list[DailyBar]` 无需判断 trade_date 格式。

> **AKShare `limit` 截断**：`stock_zh_a_hist` 不支持 `limit` 参数。`_to_canonical_akshare` 在产出 list 后按 `params.get("limit")` 截断（`list[:limit]`）。

#### 3.4.3 空值与缺失列统一规则（锁定 SPEC §4.3.3）

- **行级空值**：OHLCV 字段为 None/NaN/空字符串 → DailyBar 对应字段 None（`_f()` 语义）。
- **行丢弃**：`close` 或 `trade_date` 为空 → 该行丢弃，不计入 list。
- **列缺失（整个 raw_df 无该列）**：
  - 非关键列（`pre_close`/`turnover_rate`/`change`/`pct_chg`/`vol`/`amount`）→ DailyBar 对应字段 None。
  - 关键列（`ts_code`/`trade_date`/`close` for Tushare；`日期`/`收盘` for AKShare）→ raise `ProviderError("missing required column: {col}")`。
- **整 raw_df 空**（0 行）→ `_to_canonical` 返回空 list → provider fetch raise `ProviderUnavailableError`（§3.6）。

### 3.5 Provider fetch 行为规格（kline_daily 分支伪代码）

```python
# TushareProvider.fetch（kline_daily 分支）
def fetch(self, domain, operation, security_id, **params):
    capability = self._check_capability(domain, operation)  # 沿用，校验 capability

    if capability != "market_data.kline_daily":
        # 其余 12 capability：保持 stub（EP-103）
        df = stub_dataframe_for(capability)
        return self._to_canonical(df, capability)  # base no-op 透传

    # ---- kline_daily 真实路径 ----
    # 1. RateLimiter（EP-106）
    self._rate_limiter.acquire()

    # 2. 延迟构造默认 client（首次）
    if self._http_client is None:
        token = os.environ.get(self._token_env, "")
        self._http_client = TushareKlineClient(
            token=token, timeout=self._request_timeout
        )

    # 3. 调用 client（HC-101）
    start_date = params.get("start_date")  # 期望 YYYYMMDD
    end_date = params.get("end_date")
    limit = params.get("limit")
    raw_df = self._http_client.get_kline_daily(
        security_id, start_date=start_date, end_date=end_date, limit=limit
    )
    # client 内部已把网络/配额/超时异常归一化为
    # ProviderUnavailableError / ProviderError

    # 4. canonical 映射（EP-105）
    bars = self._to_canonical_tushare(raw_df, capability)
    # _to_canonical_tushare 内部：
    #   - raw_df 为 None/空 → 返回 []
    #   - 缺关键列 → raise ProviderError
    #   - 逐行映射，close/trade_date 空的行丢弃
    #   - 返回 list[DailyBar]

    # 5. 空 payload → raise（§3.6，适配 Router L809）
    if not bars:
        raise ProviderUnavailableError(
            "tushare kline_daily: empty payload for "
            f"{security_id.canonical}"
        )

    # 6. 成功 → 返回 list[DailyBar]
    return bars
```

> **AKShareProvider.fetch 对称结构**，差异：`_to_canonical_akshare`（中文列 + trade_date 转换 + limit 截断）；默认 client 为 `AKShareKlineClient(timeout=...)`；单位 warning 为「股/元」。

> **单位 warning 的注入点**：Design 决策——provider fetch **不直接写 warning**（因为 Router 的 `_query_external_chain` 成功分支会覆盖 warnings，见 router.py:823 `warnings=list(inherited_ta_cn_warnings)`）。单位提示需在 Router 出口体现。但 Router 不改（SPEC §4.6）。

> **单位 warning 的最终方案**（§3.7 详述）：由于 Router 成功分支只保留 `inherited_ta_cn_warnings`，provider 无法直接注入 warning。Design 决策：**单位差异通过文档 + DataResult.warnings 在双源 fallback 成功时由 Router 既有逻辑体现**（如「tushare unavailable, fell back to akshare」隐含单位切换）。**单位标注 warnings 默认不注入 DataResult**（修正 SPEC §4.3.3 的「可选追加」为「不追加，文档标注」），理由：Router 不改约束下无法干净注入；单位差异已在 SPEC §0 + 本 Design §3.4 显式声明，消费方自负换算责任（OQ-2）。`emit_unit_warning` 构造参数保留但当前版本为 no-op，留作未来 Router 支持时的扩展点。

### 3.6 Router 契约适配：空 payload 处理（关键 gap）

**发现的问题**：SPEC §3.1 EP-104 契约为「HTTP 客户端返回空 → fetch() 返回空 list（[]）→ Router 视为 empty，继续 fallback」。但 `router.py:806-824` 实际代码：

```python
result_data = self._attempt_provider_fetch(...)  # L806
if result_data is not None:                       # L809
    trace.append(f"{name}(ok)")                   # L810
    ...
    return DataResult(data=result_data, ...)      # L814-824
```

空 list `[]` 满足 `[] is not None` → True，Router 把空 list 当成功，返回 `DataResult(data=[], provider="tushare")`，**不触发 fallback**。这与 SPEC EP-104 语义冲突。

**根因**：Router 的 `is not None` 检查源自 1B-A stub 时代（stub 总返回非空 DataFrame），未覆盖真实路径的空 payload 场景。

**Design 约束**：Router 不改（SPEC §4.6 / §7.3）。

**Design 决策**：provider.fetch 的 kline_daily 分支在 `_to_canonical` 产出空 list 时，**raise `ProviderUnavailableError("kline_daily: empty payload for {sid}")`**。这样：
- `_attempt_provider_fetch`（router.py:910）捕获 `ProviderUnavailableError` → trace append `tushare(unavailable: kline_daily: empty payload for ...)` → 返回 None。
- Router `if result_data is not None` → False → 继续 fallback 到下一个 provider。
- 链耗尽 → `_build_error_result` → `DataResult(provider="error", freshness="empty")`。

**trace 语义对齐**：SPEC §4.5 矩阵写 `tushare(empty)`，实际 trace 会是 `tushare(unavailable: empty payload...)`。语义等价（「该 provider 无数据」触发 fallback），trace 更详细，可接受。测试断言用 `"empty payload" in trace_entry` 或 `"unavailable" in trace_entry`。

**为何不用其他方案**：
- 方案 B（fetch 返回 None）：`_attempt_provider_fetch` 返回 None 时不 append trace，trace 缺少空结果标记，可观测性差。
- 方案 C（新增异常子类如 `EmptyPayloadError`）：`_attempt_provider_fetch` 不捕获它，会逃逸破坏 fallback 链（router.py:889-915 只捕三类异常）。
- 方案 D（改 Router）：违反 SPEC §4.6 不改约束。

**实现者必须遵守**：kline_daily 分支的空 payload **必须** raise `ProviderUnavailableError`，**不得**返回空 list。这是适配 Router 现有契约的硬约束。

### 3.7 单位标注（warnings）最终方案

如 §3.5 注释所述，Router 成功分支（router.py:823）只保留 `inherited_ta_cn_warnings`，provider 无法直接注入 warning 到最终 DataResult。Design 决策：

- **当前版本（Phase 1D）不向 DataResult.warnings 注入单位提示**。`emit_unit_warning` 构造参数保留但为 no-op（未来 Router 支持 provider-contributed warnings 时启用）。
- **单位差异通过文档强约束**：SPEC §0 + 本 Design §3.4.1/3.4.2 已显式声明 Tushare（手/千元）vs AKShare（股/元）差异；消费方读 SPEC/Design 自负换算（OQ-2）。
- **DataResult.warnings 在 fallback 成功时由 Router 既有逻辑体现源切换**：如「ta_cn_internal」warning（TA-CN 失败后外部兜底），隐含数据源切换，间接提示单位可能变化。

> 这是 Design 阶段对 SPEC §4.3.3「可选追加单位 warning」的**修正裁定**：在 Router 不改约束下，单位 warning 注入不可行；保留构造参数为未来扩展点，当前版本靠文档约束。实现者不应尝试在 fetch 内构造 warning 并期望它出现在 DataResult（会被 Router 覆盖）。

### 3.8 限流、重试、超时（锁定 SPEC §3.1 EP-106/107 + RFC §5.3）

| 维度 | Tushare | AKShare |
|---|---|---|
| 限流 | `RateLimiter.acquire()`（1B-A 框架，默认 200 RPM，构造可配） | 同上 |
| 重试 | `with_retry` 框架**不覆盖** `ProviderUnavailableError`（rate_limiter.py:37 `_RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError)`）。配额耗尽/超时归为 `ProviderUnavailableError` → **单次失败不重试**，直接触发 Router fallback | 同上 |
| 超时 | `request_timeout_seconds`（默认 30.0）传入 client 构造，client 内部 SDK 调用受此约束 | 同上 |
| 配额耗尽 | client 捕获 → `ProviderUnavailableError` | N/A |
| 网络超时 | client 捕获 → `ProviderUnavailableError` | 同上 |
| API 内部错误 | client 捕获 → `ProviderError` | 同上 |

> **重试边界说明**：`with_retry` 的 `_RETRYABLE_EXCEPTIONS` 只含 `ConnectionError`/`TimeoutError`（Python 内置）。Tushare/AKShare SDK 的网络异常通常是 SDK 自定义异常（非内置 `ConnectionError`），不会被 `with_retry` 自动重试。Design 决策：**不在 provider 层强行套用 `with_retry`**（避免与 SDK 异常体系冲突），接受「网络抖动 → 单次失败 → Router fallback 到另一源」的降级语义。真实网络下是否需要 provider 内部重试，留作后续 smoke 验证后的调优项（OQ-4 新增）。

> **`RateLimiter` 在 stub 路径不触发**：只有 kline_daily 真实分支调 `_rate_limiter.acquire()`，其余 12/6 capability 走 stub 不触发限流（保持 1B-A 行为）。

### 3.9 持久化设计

**无持久化需求。**（SPEC §4.bis）

Phase 1D 全部组件运行在内存中。数据流：`消费方 → UnifiedDataClient.query() → DataRouter（内存编排）→ Provider.fetch()（HTTP 只读 → list[DailyBar]）→ DataResult（内存返回）`。不触碰 `03_data_ud_*` / `03_data_ud_cache_*` / `03_data_ud_query_audit` / `03_data_ud_quality_summary` 集合。Router 的 `_materialize`（router.py:598-625）在 `self._local_mongo_adapter is None` / `self._cache_manager is None` 时自然跳过（1D 不注入这两个组件）。

### 3.10 UI/原型设计

无。

### 3.11 `datetime.utcnow()` 技术债（锁定 RFC §5.7 / SPEC §7.4）

本阶段**不改造**以下站点的 naive UTC 用法：
- `skills/data/unified_data/local_mongo_adapter.py`（L161/L176/L202）
- `skills/data/unified_data/cache_manager.py`（L155/L167/L192）

理由：1D 不触 LocalMongoAdapter / CacheManager（1B-B 持久化层，本阶段不写入/不注入）。统一 UTC-aware 改造是横切关注点，应作为独立技术债卡（OQ-3），避免扩散 1D 范围。

Phase 1D 新增代码（`kline_client.py` + provider 修改）**不引入新的 `datetime.utcnow()` 调用**。Provider fetch 不生成时间戳（Router 在 `query()` 入口用 `datetime.now(timezone.utc).replace(tzinfo=None)` 统一生成 `ts`）。

---

## 4. 实现计划（已完成 — 供追溯参考）

实现顺序（按此推进已实现并通过 48 项测试验证，单元测试位置已迁移至 `skills/data/unified_data/tests/`）：

- [x] **Step 1**：新建 `kline_client.py`（Protocol + FakeKlineClient + TushareKlineClient + AKShareKlineClient）。单元测试 `test_kline_client.py`（FakeKlineClient 返回/异常/空、TushareKlineClient token 缺失 raise、AKShareKlineClient 延迟 import、call_log 断言）——**已交付**。
- [x] **Step 2**：修改 `base_external.py`（docstring 措辞 + `_to_canonical` 返回标注 `Any` + 注释，**不改逻辑**）——**已交付**。
- [x] **Step 3**：修改 `tushare.py`（docstring 措辞 + 构造新增 3 参数 + fetch kline_daily 分支 + `_to_canonical_tushare`）。单测 UT-TP-201~208——**已交付**。
- [x] **Step 4**：修改 `akshare.py`（对称 Step 3 + `_to_canonical_akshare` + trade_date 转换 + limit 截断）。单测 UT-AK-201~207——**已交付**。
- [x] **Step 5**：修改 `providers/__init__.py` + `unified_data/__init__.py`（导出新符号）——**已交付**。
- [x] **Step 6**：Router fallback 集成测试 `test_router_kline_daily_fallback.py`（UT-DR-301~309 + IT-001~004）——**已交付**。
- [x] **Step 7**：回归 1B-A `test_providers.py`（更新 kline_daily 返回 list[DailyBar] 的断言）+ 全量回归——**已交付**（564 项全 PASS）。
- [x] **Step 8**：安全测试（UT-SEC-401~403：token 不泄露、错误信息脱敏、FakeKlineClient 不读环境变量）——**已交付**。

---

## 5. 测试策略

### 5.1 单元测试矩阵（锁定 SPEC §9.1，补充 Design 细节）

| 测试编号 | 测试目标 | 注入方式 | 断言（Design 补充） |
|---|---|---|---|
| UT-KC-001 | FakeKlineClient 返回 fixture DataFrame | 直接构造 | `get_kline_daily` 返回 copy；call_log 含参数 |
| UT-KC-002 | FakeKlineClient 抛 ProviderUnavailableError | 配置异常 | raise 指定异常；call_log 已记录 |
| UT-KC-003 | FakeKlineClient 返回空 DataFrame | 配置 None | 返回空 DataFrame（0 行） |
| UT-KC-004 | TushareKlineClient token 缺失 raise | 构造 `token=""` | raise `ProviderUnavailableError("tushare token missing")` |
| UT-KC-005 | AKShareKlineClient 延迟 import（akshare 未装时不崩） | mock import | 构造成功；get_kline_daily 时才 import |
| UT-TP-201 | Tushare kline_daily 真实路径成功 | FakeKlineClient 返回 Tushare 列 DF | `list[DailyBar]`，字段映射正确（vol→volume 手、amount 千元） |
| UT-TP-202 | Tushare kline_daily 空 → raise | FakeKlineClient 返回空 DF | fetch raise `ProviderUnavailableError("empty payload")`（§3.6） |
| UT-TP-203 | Tushare 缺 close 列 | FakeKlineClient 返回缺 close 的 DF | raise `ProviderError("missing required column: close")` |
| UT-TP-204 | Tushare 行级 close=None 丢弃 | DF 含 close=NaN 行 | 该行不入 list，其余行入 |
| UT-TP-205 | Tushare HTTP 超时 | FakeKlineClient raise ProviderUnavailableError | fetch 透传 raise（Router 侧 fallback） |
| UT-TP-206 | Tushare 其余 12 capability 保持 stub | 调 kline_weekly 等 | 返回 stub DataFrame；FakeKlineClient.call_log 为空 |
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
| UT-DR-303 | Router tushare 失败 → akshare 兜底 | tushare raise + akshare ok | `provider="akshare"`；warnings 含 fallback |
| UT-DR-304 | Router 两源全失败 | 两源 raise | `provider="error"`；trace 2 个 unavailable/error |
| UT-DR-305 | Router 两源全空（§3.6 gap） | 两源 FakeKlineClient 返回空 → fetch raise | `provider="error"`；freshness="empty"；trace 含 2 个 "empty payload" |
| UT-DR-306 | Router 两源全不可用 | 两源 is_available=False | `provider="error"`；trace 2 个 skipped |
| UT-DR-307 | Router provider="tushare" forced | provider="tushare" | 只走 tushare，不 fallback |
| UT-DR-308 | Router force_refresh 跳过 TA-CN | TA-CN 有数据 + force_refresh=True | `provider="tushare"`；TA-CN 未调 |
| UT-DR-309 | Router quality_score 恒 None | 任意成功路径 | `DataResult.quality_score is None` |
| UT-SEC-401 | is_available 不泄露 token | monkeypatch TUSHARE_TOKEN="secret" | 返回 True/False；不返回/不打印 "secret" |
| UT-SEC-402 | 错误信息不含 token | FakeKlineClient raise 含 token 的异常 | provider re-raise 的 message 不含 token |
| UT-SEC-403 | FakeKlineClient 不读环境变量 | 构造 + 调用 | 不调 os.environ；call_log 不含 token |

### 5.2 集成测试（锁定 SPEC §9.2）

| 测试编号 | 测试目标 |
|---|---|
| IT-001 | 端到端：client.query(kline_daily) → TA-CN 命中 → 返回（不调 external） |
| IT-002 | 端到端：client.query(kline_daily, provider="tushare") → 注入 FakeKlineClient → list[DailyBar] |
| IT-003 | 端到端：client.query(kline_daily, force_refresh=True) → 跳过 TA-CN → tushare fake |
| IT-004 | 端到端：client.query(kline_daily) → tushare fake 失败 → akshare fake 兜底 → list[DailyBar] + warnings |

### 5.3 数据合理性断言（P-11 对齐，锁定 SPEC §9.3）

- **字段一致性**：FakeKlineClient 返回的 Tushare `vol=1234.0` → DailyBar.volume=1234.0（手）；AKShare `成交量=123400` → DailyBar.volume=123400.0（股）。
- **非空性**：成功路径的 list[DailyBar] 必须非空（除非 fixture 显式空 → raise）。
- **不返回 stub**：kline_daily 路径不得返回 `_stub_columns.stub_dataframe_for` 的空壳（断言 `isinstance(result, list)` 且元素为 DailyBar）。
- **关键字段不为 None**：成功路径 DailyBar `close`/`trade_date` 非 None（除非该行被丢弃）。
- **trade_date 格式一致**：Tushare 与 AKShare 路径的 DailyBar.trade_date 均为 YYYYMMDD。

### 5.4 回归测试

- `test_providers.py`（1B-A）：kline_daily 返回 stub DataFrame 的断言**需更新**为 list[DailyBar]（Implement 阶段同步）；其余 12/6 capability 的 stub 断言不变。
- `test_router_internal_first.py`（1B-A）：全 PASS（Router 不改）。
- `test_client_phase1a.py`（1A）：全 PASS（14 域入口不变）。
- `test_router.py`（Phase 0）：全 PASS（向后兼容）。

### 5.5 不可自动化验证项

- **真实 Tushare/AKShare API 可用性**：后续受 Pascal 单独授权的受控 smoke（RFC §9.3）。本卡/实现卡不以此 为执行前提。
- **真实 token 安全性审查**：人工审计 is_available / fetch / client / 错误路径不泄露值。
- **真实网络下 RateLimiter/重试行为**：受控 smoke 阶段验证（§3.8 重试边界说明）。

---

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| Router L809 空 list 误判（§3.6 gap） | Design 决策：空 payload raise ProviderUnavailableError | 实现者必须遵守；测试 UT-TP-202/AK-202/DR-305 覆盖 |
| Tushare/AKShare 列名漂移（API 变更） | §3.4 映射表 + 缺失列 raise ProviderError | 缺关键列 → provider 失败 → Router fallback |
| 跨源单位不一致被消费方误用 | §3.4 显式标注 + SPEC §0 声明 + OQ-2 | 不归一化（Pascal 后续决策） |
| 真实网络 smoke flaky | smoke 非执行前提（§5.5） | fake 客户端单测为主 |
| token 泄露到日志/metadata/异常 | P-10 + UT-SEC-401/402；client 异常脱敏 | 审计审查 |
| 1B-A test_providers.py kline_daily 断言失效 | §5.4 Implement 同步更新断言 | 回归测试覆盖 |
| `with_retry` 不覆盖 ProviderUnavailableError 导致网络抖动不重试 | §3.8 接受现状（单次失败 → Router fallback） | 真实 smoke 后调优（OQ-4） |
| AKShare limit 截断与 Tushare limit 语义不一致 | §3.4.2 + UT-AK-206 | 文档标注 |
| 延迟 import 首次调用开销 | is_available 已做 import guard | 可接受 |
| datetime.utcnow() 技术债扩散 | §3.11 不改造；新代码不引入 | OQ-3 独立技术债卡 |

### 6.1~6.5 副作用矩阵（锁定 RFC §9.3 / SPEC §2.2）

| 动作 | 本阶段 | 后续授权 |
|---|---|---|
| MongoDB DDL / 真实 Mongo 写入 / materialization / cache / audit / quality_summary | ❌ 严禁 | 需 Pascal 单独授权 |
| cron/systemd/webhook | ❌ 严禁 | 独立授权 |
| **真实 Tushare/AKShare 只读 smoke** | ⚠️ 受控验证项 | **需 Pascal 单独批准**；非执行前提 |
| **tushare/akshare 包安装** | ⚠️ 运行环境配置 | **需 Pascal 授权**后安装；代码用延迟 import，不新增 pyproject 依赖 |
| **凭据（TUSHARE_TOKEN）配置** | ⚠️ 运行环境配置 | **需 Pascal 授权**后写入环境变量；代码只读存在性，不回显值（P-10） |

---

## 7. 交接给实现者

### 7.1 必须遵守

1. **文件清单严格按 §3.1**：只新增 4 个文件、修改 5 个文件；不碰 §3.1 不改动清单。
2. **空 payload 必须 raise `ProviderUnavailableError`**（§3.6）：kline_daily 分支 `_to_canonical` 产出空 list 时 raise，**不得**返回空 list（Router L809 会误判）。
3. **`_to_canonical` 映射严格按 §3.4 表**：列名、单位、缺失处理逐字段对齐；`_f()` 复用或等价逻辑。
4. **AKShare trade_date 统一转 YYYYMMDD**（§3.4.2）：去横杠，与 TA-CN 路径一致。
5. **AKShare limit 截断**（§3.4.2）：`stock_zh_a_hist` 不支持 limit，`_to_canonical_akshare` 产出 list 后截断。
6. **真实 SDK 延迟 import**（§3.3.3/3.3.4）：`kline_client.py` 模块级不 import tushare/akshare；import 放在方法体内。
7. **token 不泄露**（P-10）：client 异常 message 脱敏（只描述类别）；FakeKlineClient 不读环境变量。
8. **默认 client 延迟构造**（§3.3.5）：`http_client=None` 时首次 fetch 才构造真实 client；`is_available()=False` 时不构造。
9. **单位 warning 当前为 no-op**（§3.7）：`emit_unit_warning` 参数保留但不向 DataResult 注入（Router 会覆盖）；不尝试在 fetch 内构造 warning。
10. **docstring 措辞同步**（OQ-1）：tushare.py / akshare.py / base_external.py 的「Phase 1B-B」改为「Phase 1D」。
11. **base_external.py 只改 docstring + 标注 + 注释**（§3.1）：不改方法体逻辑。
12. **不新增 pyproject 依赖**（SPEC §7.1）：tushare/akshare 是可选依赖，缺失时 is_available=False。

### 7.2 可自行判断

- `_f()` helper 是从 `models/domain/market_data.py` 导入还是在 provider 内复制等价逻辑（推荐导入，保持单一来源）。
- `_to_tushare_ts_code` / `_to_akshare_symbol` 等辅助函数放在 `kline_client.py` 还是 provider 文件内（推荐放 kline_client.py，与 client 内聚）。
- FakeKlineClient 的 `call_log` 字段命名与结构（测试便利性导向）。
- 测试 fixture 的具体数值（只要覆盖映射表字段即可）。

### 7.3 遇到以下情况退回 Principal

- 发现 Router 代码需要修改才能实现 SPEC 语义（违反 §3.6 / SPEC §4.6 约束）。
- 发现 SPEC §4.3 映射表与 Tushare/AKShare 官方文档不符（API 漂移超出预期）。
- 发现 `_to_canonical` 无法在 base_external.py 不改逻辑的前提下实现（需重构 base 类）。
- 发现空 payload 的 raise 方案在 Router 测试中产生非预期 trace 格式（需协调 trace 断言策略）。
- 发现 AKShare `stock_zh_a_hist` 的 `adjust` 参数行为与文档不符（复权口径争议）。

---

## 8. SPEC §12 待决项裁定汇总

| # | SPEC §12 待决项 | Design 裁定 | 章节 |
|---|---|---|---|
| 1 | HTTP 客户端抽象形态（Protocol vs ABC vs callable） | **`typing.Protocol`**（KlineClient），结构子类型，Fake 不需显式继承 | §3.3.1 |
| 2 | 真实 Tushare SDK 调用（pro_api.daily vs pro_bar） | **`pro_api(token).daily(...)`**（不复权，与 SPEC §0 一致） | §3.3.3 |
| 3 | AKShare adjust/period 默认值 | **`period="daily"`, `adjust=""`**（不复权，与 Tushare daily 对齐） | §3.3.4 |
| 4 | AKShare trade_date 格式（YYYY-MM-DD 透传 vs YYYYMMDD） | **统一转 YYYYMMDD**（去横杠，与 TA-CN 路径一致） | §3.4.2 |
| 5 | 单位 warnings 是否默认开启 | **构造参数 `emit_unit_warning=True` 保留，但当前版本为 no-op**（Router 不改约束下无法注入；§3.7 修正 SPEC §4.3.3） | §3.7 |
| 6 | `_to_canonical` base hook vs 子类 override | **base 保留 no-op，子类各自 override + 内部 capability 分支** | §3.1 / §3.5 |
| 7 | Router 如何包装 list[DailyBar] | **确认可行**：router.py:814 `DataResult(data=result_data)` 透明包装，与 TA-CN get_daily_bars 一致 | §3.2 / §2.2 |
| **gap** | **Router L809 空 list 误判**（SPEC EP-104 与代码冲突） | **空 payload raise ProviderUnavailableError** | §3.6 |

---

## 9. 参考资料

- RFC-03-012：`docs/rfc/03_data/RFC-03-012-unified-data-phase-1d-external-provider-activation.md`
- SPEC-03-012：`docs/spec/03_data/SPEC-03-012-unified-data-phase-1d-external-provider-activation.md`
- RFC-03-007 / SPEC-03-007（总纲，六项不变量）
- RFC-03-008 / SPEC-03-008 / DESIGN-03-008（1B-A provider 框架）
- RFC-03-009 / SPEC-03-009 / DESIGN-03-009（1B-B 命名锁定）
- RFC-03-011 / SPEC-03-011 / DESIGN-03-011（Phase 2 quality_score 归属）
- 现有代码：
  - `skills/data/unified_data/providers/{tushare,akshare,base_external,_stub_columns,rate_limiter}.py`
  - `skills/data/unified_data/router.py`（L806-824 外部链成功分支、L889-915 `_attempt_provider_fetch`、L906 `provider.fetch` 调用）
  - `skills/data/unified_data/models/domain/market_data.py`（`DailyBar` + `_f()` helper）
- Tushare `daily` 文档：https://tushare.pro/document/2?doc_id=27
- AKShare `stock_zh_a_hist` 文档：https://akshare.akfamily.xyz/data/stock/stock.html
