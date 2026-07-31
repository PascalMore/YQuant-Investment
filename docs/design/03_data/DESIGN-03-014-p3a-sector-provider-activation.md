# DESIGN-03-014: P3-A Sector Provider 激活 — 离线实现、Smoke Gate 与回滚设计

## 元数据

| 项 | 值 |
|---|----|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-31 |
| 最后更新 | 2026-07-31（V0.2：RFC/SPEC 版本引用与已批准的 V0.2 对齐；§3.2.1/§3.2.2/§3.3.4/§5.1 的 client 构造语义与已验证实现 akshare.py:236-249,302-305 对齐——未注入 client 时保持 stub，不延迟构造真实 AKShareSectorClient。V0.1 初始创建：基于 T1 RFC/SPEC + AKShare 离线 introspection 修正后的详细设计。修正 T1 endpoint 主张，定义 SectorClient 接口、FakeSectorClient、canonical mapping、allowlist、smoke Gate、回滚策略。） |
| 版本号 | V0.2 |
| 来源 RFC | RFC-03-014-p3a-sector-provider-activation（V0.2） |
| 来源 SPEC | SPEC-03-014-p3a-sector-provider-activation（V0.2） |
| 关联 Design | DESIGN-03-014（Phase 3 主设计 V0.21） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

---

## 1. 设计摘要

本设计将 `sector.snapshot` / `sector.ranking` 两个 capability 从当前 schema-level stub（0-row DataFrame）推进到真实 AKShare endpoint 调用的离线实现路径。

### 1.1 T1 Endpoint 修正（关键）

T1 RFC/SPEC 的 endpoint 主张经 AKShare 离线 introspection 证实部分不成立：

| Capability | T1 主张 endpoint | Introspection 结论 | 修正后 endpoint |
|---|---|---|---|
| `sector.snapshot` | `stock_board_industry_cons_em(symbol)` | ❌ 返回**成分股列表**（每行一只股票），非板块级聚合 | `stock_board_industry_name_em()` + 按 sector_code 过滤 |
| `sector.ranking` | `stock_board_industry_rank_em()` | ❌ **该函数不存在**（`getattr(ak, 'stock_board_industry_rank_em')` → None） | `stock_board_industry_name_em()` |

**根因**：T1 基于 AKShare 公开文档推断，但公开文档使用的函数名与实际安装包（`akshare` 实际导出的函数集）存在差异。`stock_board_industry_rank_em` 在公开文档/社区帖子中被引用，但实际安装包中不存在该函数。

**修正依据**：通过 `inspect.getsource()` 读取 `stock_board_industry_name_em()` 的完整源码，确认其返回全行业板块的宽表 DataFrame，包含排名、涨跌幅、涨跌家数、领涨股、换手率等板块级聚合字段——完全覆盖 `sector.ranking` 和 `sector.snapshot` 的字段需求。

**对 T1 文档的影响**：本 Design §1.1 即为 T1 endpoint 修正的权威记录。后续 T3 Implement worker 以本 Design 为准。T1 RFC/SPEC 的 Open Question OQ-P3A-1（"cons_em 返回的是成分股列表还是板块级聚合？"）由本 introspection **已解答**：cons_em 返回成分股列表，板块级聚合来自 name_em。

### 1.2 核心设计取舍

| 决策点 | 选择 | 理由 |
|---|---|---|
| snapshot 数据源 | `name_em()` 过滤 sector_code | name_em 一次调用返回全行业板块宽表，过滤后即得单板块聚合；避免二次调用 |
| ranking 数据源 | `name_em()` 直接使用 | name_em 本身即全行业排名（按涨跌幅排序） |
| members 字段填充 | T3 阶段**不调用** cons_em | 成分股列表需要额外 endpoint 调用；T3 离线阶段 members 保持 None，后续 Pascal 授权 smoke 中验证后决定是否补充 |
| concept 类型 | T3 设计接口但不激活 | `stock_board_concept_name_em()` 存在且结构相似，但当前阶段仅激活 industry |
| injected client 模式 | 新增 `SectorClient` Protocol | 镜像 Phase 1D `KlineClient` 注入模式；测试注入 `FakeSectorClient`，生产由调用方显式注入 `AKShareSectorClient`（未注入时保持 stub，不延迟构造） |

---

## 2. 现状分析

### 2.1 相关目录与文件

| 路径 | 现状 | 本设计关系 |
|---|---|---|
| `providers/akshare.py` | sector 分支返回 `stub_dataframe_for(capability)` | T3 改造目标：替换为 SectorClient 调用 |
| `providers/kline_client.py` | Phase 1D KlineClient Protocol + Fake/Real 实现 | **设计参考**：SectorClient 镜照此模式 |
| `providers/_stub_columns.py` | `_EXPECTED_SECTOR_SNAPSHOT_FIELDS`（12 列）、`_EXPECTED_SECTOR_RANKING_FIELDS`（8 列）已冻结 | **禁止修改**：T3 不改 STUB_COLUMNS / expected fields |
| `models/domain/sector.py` | `SectorSnapshot` 19 字段 dataclass + `from_dict()` 松弛映射 | **禁止修改**：mapping 目标 schema 不变 |
| `services/sector_service.py` | `get_sector_snapshot()` / `get_sector_ranking()` 通过 router.query() 只读 | **禁止修改**：read path 不变 |
| `tests/test_sector_client.py` | facade 委托测试（Mock service） | **不修改**：已有测试保持 |
| `tests/test_mapping_sector.py` | P0 mapping 契约测试（StubAKShareSectorProvider） | **不修改**：已有测试保持 |
| `tests/test_providers_kline_daily.py` | Phase 1D kline_daily 注入测试模式 | **设计参考**：T3 sector 测试镜照此结构 |
| `tests/fixtures/sector_fixtures.py` | `StubAKShareSectorProvider` | **不修改** |

### 2.2 AKShare `stock_board_industry_name_em()` 返回结构（introspection 证实）

通过 `inspect.getsource(ak.stock_board_industry_name_em)` 读取的完整源码确认，该函数返回以下 12 列宽表：

| 列名 | 类型 | 对应 SectorSnapshot 字段 | 备注 |
|---|---|---|---|
| `排名` | int | `rank` | 1=涨幅最高 |
| `板块名称` | str | `sector_name` | 如"白酒" |
| `板块代码` | str | `sector_code` | 如"BK0489" |
| `最新价` | float | （不映射） | 板块指数价格，canonical schema 无对应字段 |
| `涨跌额` | float | （不映射） | 板块指数涨跌额，canonical schema 无对应字段 |
| `涨跌幅` | float | `pct_chg` | 单位 % |
| `总市值` | float | （不映射） | canonical schema 无对应字段 |
| `换手率` | float | `turnover_rate` | 单位 % |
| `上涨家数` | int | `advance_count` | |
| `下跌家数` | int | `decline_count` | |
| `领涨股票` | str | `leading_stock` | 如"贵州茅台"（注意：可能是名称而非代码） |
| `领涨股票-涨跌幅` | float | `leading_pct_chg` | 单位 % |

**不在 name_em 返回中的 canonical 字段**：

| SectorSnapshot 字段 | 处理方式 |
|---|---|
| `sector_type` | 调用方注入 `"industry"` |
| `snapshot_date` | 请求日期或 fetch 日期 |
| `market` | 常量 `"CN"` |
| `provider` | 常量 `"akshare"` |
| `total_count` | None（name_em 不返回总家数；不编造，不计算 advance+decline） |
| `main_net_inflow` | None（name_em 不返回资金流；需要其他 endpoint） |
| `leading_stock_name` | None（`领涨股票` 可能混合代码和名称；不在 T3 阶段拆分） |
| `members` | None（需要 cons_em；T3 不调用） |
| `fetched_at` | `datetime.now().isoformat()` |
| `raw_payload` | 原始行 dict（可选保留） |

### 2.3 AKShare `stock_board_industry_cons_em(symbol)` 返回结构（introspection 证实）

该函数返回**成分股列表**，每行一只股票：

| 列名 | 备注 |
|---|---|
| `序号` | int |
| `代码` | 股票代码 |
| `名称` | 股票名称 |
| `最新价` / `涨跌幅` / `涨跌额` / `成交量` / `成交额` / `振幅` / `最高` / `最低` / `今开` / `昨收` / `市盈率-动态` / `市净率` / `换手率` | 个股级数据 |

**本设计裁定**：T3 阶段**不调用** cons_em。`members` 字段保持 None。后续 Pascal 授权 smoke 中验证 cons_em 可达性后，在独立的 PR-2 Gate 中决定是否补充 members 填充逻辑。

### 2.4 AKShare `stock_board_concept_name_em()` 返回结构

与 `stock_board_industry_name_em()` 列结构完全一致（12 列），但覆盖概念板块。本设计在 SectorClient 接口中预留 concept 路由，但 T3 阶段仅激活 industry。

---

## 3. 方案设计

### 3.1 模块/文件改动（T3 Implement allowlist）

| 文件 | 改动 | 原因 |
|---|---|---|
| `providers/akshare.py` | sector 分支激活：从 `stub_dataframe_for` → SectorClient 调用 | 核心 Provider 激活 |
| `providers/sector_client.py`（新增） | `SectorClient` Protocol + `AKShareSectorClient` + `FakeSectorClient` | injected client 抽象层 |
| `tests/test_sector_provider_activation.py`（新增） | endpoint 选择、字段映射、空集、异常、sector_type 路由测试 | 离线测试覆盖 |
| `tests/fixtures/sector_activation_fixtures.py`（新增） | AKShare 中文 DataFrame fixture（industry） | 模拟真实返回结构 |

**精确禁止修改路径**：

- ❌ `models/domain/sector.py`（SectorSnapshot 19 字段已冻结）
- ❌ `providers/_stub_columns.py`（STUB_COLUMNS / `_EXPECTED_SECTOR_*_FIELDS` 已冻结）
- ❌ `providers/__init__.py`（twin 定义已冻结）
- ❌ `router.py`（读路径不变）
- ❌ `client.py`（UnifiedDataClient 不变）
- ❌ `adapters/`（LocalMongoAdapter / P3PersistenceWriter 不变）
- ❌ `services/sector_service.py`（read path 不变）
- ❌ `freshness.py`（PC-11 命名冲突冻结）
- ❌ `providers/akshare.py` 的 `kline_daily` 路径（`_fetch_kline_daily` / `_akshare_df_to_daily_bars`）
- ❌ 任何 `.env` / config / requirements / SKILL.md / README
- ❌ P3-B / P3-C 相关文件
- ❌ `tests/test_sector_client.py` / `tests/test_mapping_sector.py` / `tests/test_provider_phase3.py`（已有测试不改）

### 3.2 数据流/控制流

#### 3.2.1 sector.snapshot 调用链（离线 + 后续真实）

```text
SectorService.get_sector_snapshot(sector_code, date)
  │
  ▼
DataRouter.query(domain="sector", operation="snapshot", security_id, params={sector_code, date})
  │
  ▼ Step 4: external fallback
  │
AKShareProvider.fetch(domain="sector", operation="snapshot", security_id, **params)
  │
  ├── _check_capability → "sector.snapshot" ✅ in capabilities
  │
  ▼
  │  [T3 改造点] sector 分支: 未注入 client → stub_dataframe_for(capability) 0-row；
  │              注入 client  → _fetch_sector_snapshot(sector_code, params)
  │
  ▼
_fetch_sector_snapshot(sector_code, params)   ← 仅当显式注入 client 时可达
  │
  ├── self._rate_limiter.acquire()
  │
  ├── self._sector_client 保证非 None（由 fetch() dispatch 守卫，akshare.py:236-249）
  │     不延迟构造：未注入时 fetch() 直接返回 stub，绝不构造/调用真实 AKShare client
  │
  ▼
  │  [测试注入点] 测试传 FakeSectorClient；生产由调用方显式注入 AKShareSectorClient
  │
SectorClient.get_sector_ranking(sector_type="industry")
  │  ← 注意：snapshot 内部复用 ranking endpoint，然后按 sector_code 过滤
  │
  ▼ 返回 pd.DataFrame（全行业 name_em 宽表）
  │
  ├── filter: df[df["板块代码"] == sector_code]
  │
  ▼ 单行 DataFrame 或空 DataFrame
  │
AKShareProvider._to_canonical(df, "sector.snapshot")
  │
  ▼ _akshare_name_em_df_to_sector_snapshot(df, sector_type, snapshot_date)
  │
  ├── 中文字段 → canonical 英文 alias 转换
  ├── _safe_float / _safe_int 容错转换
  ├── 常量注入：market="CN", provider="akshare", sector_type, snapshot_date, fetched_at
  ├── 缺失字段填 None / 0（禁止编造）
  │
  ▼ list[dict]（SectorSnapshot.from_dict 兼容）
  │
  └── 返回 list[dict] → Router 封装 DataResult → Service._coerce_snapshot → SectorSnapshot
```

#### 3.2.2 sector.ranking 调用链

```text
SectorService.get_sector_ranking(date, sector_type, limit)
  │
  ▼
DataRouter.query(domain="sector", operation="ranking", ...)
  │
  ▼
AKShareProvider.fetch(domain="sector", operation="ranking", ...)
  │
  ▼
_fetch_sector_ranking(params)
  │
  ├── self._rate_limiter.acquire()
  ├── [未注入 client] fetch() 返回 stub_dataframe_for(capability)；注入才可达此处
  │
  ▼
SectorClient.get_sector_ranking(sector_type="industry")
  │
  ▼ 返回 pd.DataFrame（全行业 name_em 宽表）
  │
AKShareProvider._to_canonical(df, "sector.ranking")
  │
  ▼ _akshare_name_em_df_to_sector_ranking(df, sector_type, snapshot_date)
  │
  ├── 中文字段 → canonical alias（8 列子集）
  ├── _safe_float / _safe_int
  ├── 常量注入
  │
  ▼ list[dict]
  │
  └── 返回 list[dict] → Router → Service 排序（pct_chg desc）→ list[SectorSnapshot]
```

### 3.3 接口与数据结构

#### 3.3.1 SectorClient Protocol（新增 `providers/sector_client.py`）

与 RFC V0.2 §5.5.1 SectorClient 接口签名一致：

```python
@runtime_checkable
class SectorClient(Protocol):
    """Injectable sector data client abstraction (P3-A).

    Mirrors the Phase 1D KlineClient injection pattern. Two
    implementations:

    * FakeSectorClient — test fixture, no network, no SDK import.
    * AKShareSectorClient — production, lazy-imports ``akshare``,
      calls ``stock_board_industry_name_em()``.

    Both methods internally call the same upstream endpoint
    (``name_em``); ``get_sector_snapshot()`` filters the full result
    by ``sector_code`` at the Client layer.

    Implementations must raise:
    * ProviderUnavailableError for network/timeout/SSL failures.
    * ProviderError for API-internal failures.
    """

    def get_sector_snapshot(
        self,
        sector_code: str,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        """Return board-level aggregate row for a single sector.

        Internally calls ``stock_board_industry_name_em()`` and
        filters by ``sector_code``. Returns a 1-row DataFrame (or
        empty if ``sector_code`` not found).

        Raises:
            ProviderUnavailableError: network/timeout/SSL.
            ProviderError: API internal error / unsupported sector_type.
        """
        ...

    def get_sector_ranking(
        self,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        """Return ranking DataFrame for all sectors of a type.

        Internally calls ``stock_board_industry_name_em()`` and
        returns the full result.

        Raises:
            ProviderUnavailableError: network/timeout/SSL.
            ProviderError: API internal error / unsupported sector_type.
        """
        ...
```

**设计决策**：Protocol 暴露 `get_sector_snapshot()` 和 `get_sector_ranking()` 两个方法。

**理由**（与 RFC V0.2 一致）：
1. snapshot 语义是"获取单板块"，ranking 语义是"获取全量排名"——在 Client 层分离更清晰。
2. Client 层按 `sector_code` 过滤，Provider 层不需要关心过滤逻辑。
3. 如果后续 snapshot 需要不同的 endpoint（如 `spot_em` 获取实时行情），Client 层已预留扩展点。
4. 两个方法底层共享同一个 `name_em()` 调用（AKShareSectorClient 内部可缓存或直接复用）。

#### 3.3.2 AKShareSectorClient（生产客户端，延迟 SDK import）

```python
class AKShareSectorClient:
    """Production AKShare sector client (lazy SDK import).

    AKShare is token-less. ``stock_board_industry_name_em()`` returns
    all industry boards in one call — no pagination, no date parameter.
    The endpoint always returns the latest available snapshot.

    Both ``get_sector_snapshot()`` and ``get_sector_ranking()``
    internally call ``name_em()``; snapshot filters the result by
    ``sector_code``.

    The returned DataFrame column order is frozen by the AKShare
    source code (verified via ``inspect.getsource``):

        排名, 板块名称, 板块代码, 最新价, 涨跌额, 涨跌幅,
        总市值, 换手率, 上涨家数, 下跌家数, 领涨股票, 领涨股票-涨跌幅
    """

    _INDUSTRY_FN_NAME = "stock_board_industry_name_em"
    _CONCEPT_FN_NAME = "stock_board_concept_name_em"

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def _call_name_em(self, sector_type: str) -> pd.DataFrame:
        """Shared internal: call name_em for the given sector_type."""
        import akshare as ak  # lazy import

        if sector_type == "industry":
            fn_name = self._INDUSTRY_FN_NAME
        elif sector_type == "concept":
            fn_name = self._CONCEPT_FN_NAME
        else:
            raise ProviderError(
                f"akshare sector: unsupported sector_type {sector_type!r}; "
                f"only 'industry' and 'concept' are supported"
            )
        fn = getattr(ak, fn_name, None)
        if fn is None:
            raise ProviderUnavailableError(
                f"akshare sector: endpoint {fn_name!r} not found in installed package"
            )
        try:
            df = fn()
        except Exception as exc:
            self._raise_classified(exc)
            raise  # pragma: no cover
        return df if df is not None else pd.DataFrame()

    def get_sector_snapshot(
        self,
        sector_code: str,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        df = self._call_name_em(sector_type)
        if "板块代码" in df.columns and sector_code:
            return df[df["板块代码"] == sector_code].copy()
        return df.iloc[0:0]  # empty with same columns

    def get_sector_ranking(
        self,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        return self._call_name_em(sector_type)
```

**关键约束**：
1. `import akshare` 在方法内部（lazy import），模块顶层无第三方依赖。
2. 使用 `getattr(ak, fn_name, None)` 防御 endpoint 不存在（如 rank_em 的教训）。
3. 异常分类复用 `TushareKlineClient._raise_classified` 的 keyword 匹配逻辑。
4. `name_em()` 无参数——不接受 date / sector_code / limit。返回的是当前最新快照。
5. `_call_name_em()` 是内部共享方法，snapshot 和 ranking 均调用它；snapshot 额外做过滤。

#### 3.3.3 FakeSectorClient（测试 fixture）

与 RFC V0.2 §5.5.1 FakeSectorClient 签名一致：

```python
class FakeSectorClient:
    """Test-only SectorClient implementation.

    Construct with ranking DataFrame (and optional snapshot
    DataFrame). ``get_sector_snapshot()`` filters the ranking
    DataFrame by ``板块代码 == sector_code``; ``get_sector_ranking()``
    returns the full ranking DataFrame. Both methods record every
    invocation in ``call_log``.

    The fake never reads the environment, never imports the real
    SDK, and never performs I/O.
    """

    def __init__(
        self,
        *,
        ranking_df: pd.DataFrame | None = None,
        snapshot_df: pd.DataFrame | None = None,
        exception: BaseException | None = None,
    ) -> None:
        self._ranking_df = ranking_df
        self._snapshot_df = snapshot_df  # if None, derive from ranking_df
        self._exc = exception
        self.call_log: list[dict[str, Any]] = []

    def get_sector_snapshot(
        self,
        sector_code: str,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        self.call_log.append(
            {"method": "snapshot", "sector_code": sector_code, "sector_type": sector_type}
        )
        if self._exc is not None:
            raise self._exc
        # If explicit snapshot_df provided, use it; otherwise filter ranking_df
        if self._snapshot_df is not None:
            return self._snapshot_df.copy()
        if self._ranking_df is None:
            return pd.DataFrame()
        if "板块代码" in self._ranking_df.columns and sector_code:
            return self._ranking_df[self._ranking_df["板块代码"] == sector_code].copy()
        return self._ranking_df.iloc[0:0]

    def get_sector_ranking(
        self,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        self.call_log.append({"method": "ranking", "sector_type": sector_type})
        if self._exc is not None:
            raise self._exc
        if self._ranking_df is None:
            return pd.DataFrame()
        return self._ranking_df.copy()
```

**与 RFC V0.2 的差异说明**：RFC V0.2 FakeSectorClient 接受 `snapshot_df` 和 `ranking_df` 两个独立 fixture。本设计额外支持 `snapshot_df=None` 时从 `ranking_df` 自动派生（按 sector_code 过滤），减少 fixture 重复。如 T3 worker 更倾向于 RFC 的双 fixture 方式，可自行判断——两种方式功能等价。

#### 3.3.4 AKShareProvider 改造点

在 `AKShareProvider.__init__` 新增 `sector_client` 参数：

```python
def __init__(
    self,
    *,
    rate_limit_rpm: int = 200,
    retry_max_attempts: int = 3,
    retry_backoff_base: float = 1.0,
    http_client: KlineClient | None = None,       # Phase 1D kline
    sector_client: SectorClient | None = None,     # P3-A sector (新增)
    request_timeout_seconds: float = 30.0,
    emit_unit_warning: bool = True,
) -> None:
    super().__init__(...)
    self._http_client = http_client
    self._sector_client: SectorClient | None = sector_client  # 新增
    self._request_timeout_seconds = request_timeout_seconds
    self._emit_unit_warning = emit_unit_warning
```

在 `fetch()` 方法中替换 sector 分支：

```python
# 当前（stub）:
if capability in (SECTOR_SNAPSHOT_CAPABILITY, SECTOR_RANKING_CAPABILITY):
    df = stub_dataframe_for(capability)
    return self._to_canonical(df, capability)

# T3 改造后（与 akshare.py:232-249 实现一致）:
if capability in (SECTOR_SNAPSHOT_CAPABILITY, SECTOR_RANKING_CAPABILITY):
    if self._sector_client is not None:
        # 仅显式注入的 client 可走 canonical-mapping 路径；先校验 sector_type
        sector_type = params.get("sector_type", "industry")
        if sector_type not in ("industry", "concept"):
            raise ProviderError(
                f"akshare sector: unsupported sector_type {sector_type!r}"
            )
        if capability == SECTOR_SNAPSHOT_CAPABILITY:
            return self._fetch_sector_snapshot(security_id, params)
        return self._fetch_sector_ranking(params)
    # 未注入 client（默认路径）: 保持 schema-level stub（0-row DataFrame），
    # 不构造、不调用真实 AKShareSectorClient，不触发任何网络 I/O
    return stub_dataframe_for(capability)
```

新增私有方法：

```python
def _fetch_sector_snapshot(self, security_id, params) -> list[dict]:
    """Fetch single board aggregate via the injected SectorClient.

    client 非 None 由 fetch() dispatch 保证；此处不做延迟构造。
    """
    self._rate_limiter.acquire()
    sector_code = params.get("sector_code", "")
    sector_type = params.get("sector_type", "industry")
    snapshot_date = params.get("date") or datetime.date.today().isoformat()
    raw_df = self._sector_client.get_sector_snapshot(
        sector_code=sector_code, sector_type=sector_type,
    )
    return self._to_canonical(
        raw_df, SECTOR_SNAPSHOT_CAPABILITY,
        _snapshot_date=snapshot_date, _sector_type=sector_type,
    )

def _fetch_sector_ranking(self, params) -> list[dict]:
    """Fetch all-board ranking via the injected SectorClient.

    client 非 None 由 fetch() dispatch 保证；此处不做延迟构造。
    """
    self._rate_limiter.acquire()
    sector_type = params.get("sector_type", "industry")
    snapshot_date = params.get("date") or datetime.date.today().isoformat()
    raw_df = self._sector_client.get_sector_ranking(sector_type=sector_type)
    return self._to_canonical(
        raw_df, SECTOR_RANKING_CAPABILITY,
        _snapshot_date=snapshot_date, _sector_type=sector_type,
    )
```

**关键约束**：
1. `_to_canonical` 的 sector 分支需要新增 sector-specific canonical mapping 函数。
2. snapshot_date 注入方式：优先使用 params["date"]，否则用 fetch 日期。**禁止**从 DataFrame 中推断日期（name_em 不返回日期字段）。
3. sector_type 注入方式：由 endpoint 选择决定（industry endpoint → "industry"）。**禁止**从 API 返回中推断。
4. **禁止延迟构造**：`_fetch_sector_*` 内部不再执行 `AKShareSectorClient(...)`。client 非 None 由 `fetch()` dispatch 保证（akshare.py:236-249）；未注入时 fetch() 直接返回 `stub_dataframe_for(capability)`，不构造、不调用真实 client（akshare.py:302-305 文档化）。

#### 3.3.5 Canonical Mapping 函数

新增 `_akshare_name_em_df_to_sector_dicts()` 函数（在 `akshare.py` 模块级）：

```python
# name_em 中文列名 → canonical 英文 alias
_SECTOR_NAME_EM_COLUMN_MAP: dict[str, str] = {
    "排名": "rank",
    "板块名称": "sector_name",
    "板块代码": "sector_code",
    "涨跌幅": "pct_chg",
    "换手率": "turnover_rate",
    "上涨家数": "advance_count",
    "下跌家数": "decline_count",
    "领涨股票": "leading_stock",
    "领涨股票-涨跌幅": "leading_pct_chg",
}

def _akshare_name_em_df_to_sector_dicts(
    raw_df: pd.DataFrame,
    *,
    capability: str,
    snapshot_date: str,
    sector_type: str = "industry",
) -> list[dict]:
    """Map AKShare name_em DataFrame → list[dict] for SectorSnapshot.from_dict.

    Applies:
    1. Column alias (中文 → canonical English).
    2. _safe_float / _safe_int type coercion.
    3. Constant injection (market, provider, sector_type, snapshot_date, fetched_at).
    4. Missing fields → None / 0 (no fabrication).
    5. ranking capability: only 8-column subset.
    """
    ...
```

**字段映射表（权威，基于 introspection 证实）**：

| SectorSnapshot 字段 | AKShare name_em 列名 | 转换 | snapshot 包含 | ranking 包含 |
|---|---|---|---|---|
| `sector_code` | `板块代码` | str 直传 | ✅ | ✅ |
| `sector_name` | `板块名称` | str 直传 | ✅ | ✅ |
| `sector_type` | （注入） | 常量 `"industry"` | ✅ | ✅ |
| `snapshot_date` | （注入） | fetch 日期 `YYYY-MM-DD` | ✅ | ✅ |
| `market` | （注入） | 常量 `"CN"` | ✅ | ✅ |
| `provider` | （注入） | 常量 `"akshare"` | ✅ | ✅ |
| `rank` | `排名` | `_safe_int` | ✅ | ✅ |
| `pct_chg` | `涨跌幅` | `_safe_float` | ✅ | ✅ |
| `leading_stock` | `领涨股票` | str 直传 | ✅ | ❌（ranking 8 列子集不含） |
| `leading_pct_chg` | `领涨股票-涨跌幅` | `_safe_float` | ✅ | ❌ |
| `advance_count` | `上涨家数` | `_safe_int` (默认 0) | ✅ | ✅ |
| `decline_count` | `下跌家数` | `_safe_int` (默认 0) | ✅ | ✅ |
| `total_count` | （不存在） | None（不编造） | ✅(None) | ❌ |
| `turnover_rate` | `换手率` | `_safe_float` | ✅ | ❌ |
| `main_net_inflow` | （不存在） | None | ✅(None) | ❌ |
| `leading_stock_name` | （不存在） | None | ✅(None) | ❌ |
| `members` | （不调用 cons_em） | None | ✅(None) | ❌ |
| `fetched_at` | （注入） | `datetime.now().isoformat()` | ✅ | ❌ |
| `raw_payload` | （可选） | 原始行 dict | ✅(可选) | ❌ |

**ranking ⊂ snapshot 约束**：ranking 只映射 8 列（sector_code, sector_name, sector_type, snapshot_date, rank, pct_chg, advance_count, decline_count），与 `_EXPECTED_SECTOR_RANKING_FIELDS` 一致。snapshot 映射全部 12 expected 列 + dataclass 级别可选字段。

**type coercion 辅助函数**：

```python
def _safe_float(val: Any) -> float | None:
    """Convert to float, return None on failure. Handles '2.35%' → 2.35."""
    if val is None:
        return None
    try:
        if isinstance(val, str):
            val = val.replace("%", "").replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return None

def _safe_int(val: Any) -> int:
    """Convert to int, return 0 on failure."""
    if val is None:
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0
```

### 3.4 持久化设计

无持久化需求。本设计全程保持 P3 query read-only（Zero-Persistence-Write）。`DataRouter.query()` 对 `sector.snapshot` / `sector.ranking` 不触发任何物化写入或 Cache 写入。

`refresh_sector_snapshot()` / `refresh_sector_ranking()` 的三态守卫（unauthorized / injected-not-implemented / authorized）保持不变，本设计不激活 refresh 路径。

### 3.5 UI/原型设计

无。

---

## 4. 实现计划

T3 Implement worker 按以下顺序实现（每步可独立验证）：

### Step 1: 新建 `providers/sector_client.py`

- [ ] 定义 `SectorClient` Protocol（`@runtime_checkable`）
- [ ] 定义 `AKShareSectorClient`（lazy import akshare，调用 `name_em`）
- [ ] 定义 `FakeSectorClient`（fixture 返回 + 异常注入 + call_log）
- [ ] 定义 `__all__`

**验证**：模块可独立 import，无第三方依赖（akshare import 在方法内部）。

### Step 2: 新建 `tests/fixtures/sector_activation_fixtures.py`

- [ ] `_default_industry_ranking_df()`：返回模拟 `stock_board_industry_name_em()` 的中文列 DataFrame（3-5 行，覆盖白酒 BK0489、证券 BK0473 等真实板块代码）
- [ ] `_empty_ranking_df()`：返回空 DataFrame（相同列结构）

**验证**：fixture 列名与 introspection 证实的列名完全一致。

### Step 3: 在 `providers/akshare.py` 新增 sector canonical mapping

- [ ] `_SECTOR_NAME_EM_COLUMN_MAP` 字典
- [ ] `_safe_float()` / `_safe_int()` 辅助函数
- [ ] `_akshare_name_em_df_to_sector_dicts()` 映射函数（支持 snapshot 12 列 / ranking 8 列两种模式）
- [ ] 在 `_to_canonical()` 中新增 sector 分支分发

**验证**：mapping 函数对 fixture DataFrame 产出正确的 `list[dict]`。

### Step 4: 在 `providers/akshare.py` 新增 sector fetch 路径

- [ ] `__init__` 新增 `sector_client` 参数
- [ ] `_fetch_sector_snapshot()` 私有方法
- [ ] `_fetch_sector_ranking()` 私有方法
- [ ] `fetch()` 方法 sector 分支替换（从 stub → SectorClient 调用）

**验证**：注入 FakeSectorClient 后，fetch("sector", "snapshot", ...) 和 fetch("sector", "ranking", ...) 返回正确结果。

### Step 5: 新建 `tests/test_sector_provider_activation.py`

- [ ] endpoint 选择测试（snapshot → name_em 过滤；ranking → name_em 直传）
- [ ] 字段映射测试（中文 DataFrame → SectorSnapshot）
- [ ] 空集处理测试（空 DataFrame → DataResult.success(is_empty)）
- [ ] 异常处理测试（FakeSectorClient 注入 SSLError / ConnectionError / TimeoutError）
- [ ] sector_type 路由测试（industry / concept / unsupported）
- [ ] snapshot 过滤测试（多板块返回中过滤特定 sector_code）
- [ ] call_log 验证（SectorClient 被调用且参数正确）
- [ ] stub 路径回归（其他 6 个 capability 仍返回 stub）

**验证**：全部测试离线通过，零真实 I/O。

### Step 6: 回归测试

- [ ] `test_sector_service.py` 全部 PASS（read path 不变）
- [ ] `test_mapping_sector.py` 全部 PASS（StubAKShareSectorProvider 路径不变）
- [ ] `test_provider_phase3.py` 全部 PASS（P3-A stub 注册不变）
- [ ] `test_providers_kline_daily.py` 全部 PASS（kline_daily 路径不变）
- [ ] `test_sector_client.py` 全部 PASS（facade 委托不变）

---

## 5. 测试策略

### 5.1 单元测试（`test_sector_provider_activation.py`）

| 测试 ID | 覆盖 | 需网络 | 描述 |
|---|---|---|---|
| UT-SA-201 | snapshot 成功路径 | 否 | FakeSectorClient 注入 industry ranking fixture → fetch("sector", "snapshot", sector_code="BK0489") → SectorSnapshot |
| UT-SA-202 | ranking 成功路径 | 否 | FakeSectorClient 注入 industry ranking fixture → fetch("sector", "ranking") → list[SectorSnapshot] |
| UT-SA-203 | snapshot 过滤 | 否 | fixture 含 3 个板块 → snapshot BK0489 只返回 1 条 |
| UT-SA-204 | 字段映射正确性 | 否 | 中文列 → canonical 字段（排名→rank, 涨跌幅→pct_chg, etc.） |
| UT-SA-205 | 空集处理 | 否 | FakeSectorClient 返回空 DataFrame → DataResult.success(is_empty) |
| UT-SA-206 | SSLError 异常 | 否 | FakeSectorClient 注入 SSLError → DataResult.error(provider="error") |
| UT-SA-207 | ConnectionError 异常 | 否 | 同上 |
| UT-SA-208 | TimeoutError 异常 | 否 | 同上 |
| UT-SA-209 | sector_type=industry 路由 | 否 | call_log 确认 sector_type="industry" |
| UT-SA-210 | sector_type=concept 路由 | 否 | call_log 确认 sector_type="concept" |
| UT-SA-211 | sector_type=unsupported | 否 | sector_type="region" → ProviderError |
| UT-SA-212 | stub 路径回归 | 否 | 其他 6 capability 仍返回 stub DataFrame |
| UT-SA-213 | 无注入不构造 | 否 | sector_client=None 时 __init__ 不构造 client；未注入路径保持 stub，首次 fetch 也不延迟构造真实 client（akshare.py:236-249,302-305） |
| UT-SA-214 | snapshot_date 注入 | 否 | params["date"] 优先；None 时用 fetch 日期 |
| UT-SA-215 | 禁止编造验证 | 否 | total_count/main_net_inflow/members 全部 None |

### 5.2 集成测试

复用已有 `test_sector_service.py` / `test_mapping_sector.py` / `test_provider_phase3.py`，确保 read path 不变。

### 5.3 端到端 smoke（后续 Pascal 授权，不在 T3 范围）

见 §7 Smoke Gate。

### 5.4 回归范围

| 测试文件 | 回归原因 |
|---|---|
| `test_sector_service.py` | read path 不变（SectorService 不改） |
| `test_mapping_sector.py` | StubAKShareSectorProvider 路径不变 |
| `test_provider_phase3.py` | P3-A stub 注册不变 |
| `test_providers_kline_daily.py` | kline_daily 路径不变 |
| `test_sector_client.py` | facade 委托不变 |
| `test_providers.py` | AKShareProvider 基础行为不变 |
| `test_router_p3_readonly.py` | P3 query zero-write 不变 |
| `test_router_p3_internal_first_materialized_read.py` | materialized read 路径不变 |

---

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| 真实 name_em 返回字段与 introspection 不一致（版本漂移） | 后续 smoke 验证；字段匹配阈值 ≥90% pass / 70-90% conditional_pass / <70% fail | 回退到 schema-level stub（`stub_dataframe_for`） |
| 真实 name_em SSL 失败（同 B2 cons_em） | 后续 Pascal 授权网络诊断 | 回退到 stub；不自动重试 |
| name_em 返回的 `领涨股票` 字段是名称而非代码 | canonical `leading_stock` 语义可能不精确 | smoke 验证后决定是否拆分为 leading_stock + leading_stock_name |
| sector_client 注入与 http_client 冲突 | 两个 client 独立注入，互不干扰 | kline_daily 用 http_client（KlineClient），sector 用 sector_client（SectorClient） |
| concept endpoint 结构与 industry 不同 | introspection 证实列结构一致（12 列相同） | 如 smoke 发现差异，concept 路由标注「未验证」 |
| Provider 构造函数新增参数破坏已有调用 | sector_client 默认 None，向后兼容 | 已有 `AKShareProvider()` 调用不受影响 |

### 6.1 回滚策略

**T3 实现后如发现 mapping 不匹配**：

1. `fetch()` 方法 sector 分支回退到 `stub_dataframe_for(capability)`（注释掉 SectorClient 调用路径）。
2. 不需要删除 `sector_client.py` / 测试文件 / fixture（保留为设计资产）。
3. 记录回滚原因在 DESIGN 文档中。

**回滚验证**：回退后全部已有测试 PASS（stub 路径是 T3 之前的 baseline）。

---

## 7. 后续真实 Smoke Gate（Pascal 授权，不在 T3 范围）

### 7.1 Smoke 最小参数

| 参数 | sector.snapshot | sector.ranking |
|---|---|---|
| endpoint | `stock_board_industry_name_em()` | `stock_board_industry_name_em()` |
| 标的 | 过滤 `BK0489`（白酒行业） | 全行业（不传 symbol） |
| sector_type | `industry` | `industry` |
| 调用次数 | ≤1 次（name_em 一次返回全部） | ≤1 次（同 endpoint） |
| 写入 | 零写入 | 零写入 |

**注意**：snapshot 和 ranking 共享同一个 endpoint 调用（`name_em()`），因此 smoke 只需 1 次调用即可同时验证两个 capability。

### 7.2 Smoke 动作清单

| 步骤 | 动作 | 验证点 | 影响范围 |
|---|---|---|---|
| S-1 | `ak.stock_board_industry_name_em()` | 返回非空 DataFrame，12 列 | 无（只读） |
| S-2 | 检查列名 | 与 introspection 证实的 12 列匹配 | 无 |
| S-3 | 检查 `板块代码` 列 | 包含 `BK0489` | 无 |
| S-4 | 检查数值列类型 | `涨跌幅` / `换手率` 为 float；`上涨家数` / `下跌家数` 为 int | 无 |
| S-5 | 过滤 `BK0489` 行 | `板块名称` == "白酒"；字段值合理 | 无 |
| S-6 | 检查 SSL 连接 | 无 SSLError | 无 |
| S-7 | 记录 YAML 报告 | connectivity / field_mapping / data_sample / verdict | 无 |

### 7.3 Smoke 停止条件

- SSL 失败 → 停止，不进入 DDL/CANARY Gate
- 字段匹配 <70% → 停止，更新映射后重做
- 返回空 DataFrame → 检查是否非交易日；如是则重试下一个交易日
- `领涨股票` 字段语义不明确 → 记录但不停止（非阻塞 OQ）

### 7.4 Smoke 前置条件

B2 SSL 网络诊断必须先通过。B2 的 SSL 失败是 egress 限制，后续单变量网络诊断（切换网络出口、TLS 版本检查）须 Pascal 独立授权并在 smoke 前完成。

**注意**：B2 测试的是 `cons_em` endpoint，但 `name_em` 和 `cons_em` 访问的是同一组东方财富服务器域名（`17.push2.eastmoney.com` / `29.push2.eastmoney.com`），因此 SSL 诊断结论对两者同等适用。

---

## 8. 交接给实现者

### 8.1 必须遵守

1. **endpoint 必须使用 `stock_board_industry_name_em()`**——禁止使用不存在的 `stock_board_industry_rank_em`。
2. **`stock_board_industry_cons_em` 在 T3 阶段不调用**——返回的是成分股，非板块聚合；members 字段保持 None。
3. **所有真实 AKShare 调用必须通过 SectorClient Protocol**——禁止在 Provider 层直接 `import akshare`。
4. **测试必须使用 FakeSectorClient**——禁止真实网络 I/O。
5. **snapshot_date 不可从 DataFrame 推断**——name_em 不返回日期；用 params["date"] 或 fetch 日期。
6. **sector_type 不可从 API 返回推断**——由 endpoint 选择注入。
7. **禁止编造缺失字段**——total_count / main_net_inflow / members / leading_stock_name 保持 None。
8. **`_safe_float` / `_safe_int` 必须容错**——AKShare 可能返回字符串类型数值。
9. **`__init__` 新增 `sector_client` 参数默认 None**——向后兼容已有调用。
10. **禁止修改 allowlist 以外的文件**（见 §3.1 精确禁止路径）。
11. **完成后状态选择**：验收标准全 PASS → `kanban_complete(status="done")`；任何 FAIL → `kanban_block(reason="...")`。

### 8.2 可自行判断

- `_safe_float` 是否处理 `"2.35%"` 格式（带百分号）——建议处理但非强制。
- `raw_payload` 是否保留原始行 dict——建议保留用于调试。
- fixture 使用哪些真实板块代码——建议 BK0489（白酒）、BK0473（证券）、BK1036（半导体）。
- 是否在 `_to_canonical` 中复用已有的 `_f` 辅助函数——建议不复用（sector 和 kline 的字段语义不同）。

### 8.3 遇到以下情况退回 Principal

- 发现 `stock_board_industry_name_em()` 的返回结构与本 Design §2.2 描述不一致（版本漂移）。
- 发现需要调用 `stock_board_industry_cons_em` 才能获取板块聚合数据（本 Design 假设 name_em 已包含足够字段）。
- 发现 `concept` endpoint 的列结构与 `industry` 不同。
- 发现需要修改 SectorSnapshot schema 或 STUB_COLUMNS（已冻结，不可改）。
- 发现需要新增第三方依赖。

---

## 声明

本设计中涉及的板块/行业数据为辅助研究数据，不构成交易指令或投资建议。

本设计不修改主 DESIGN-03-014 的任何已有内容。所有引用以交叉引用方式继承主设计，冲突时以主设计为准。

本 Design §1.1 的 endpoint 修正是基于 AKShare 离线 introspection（`inspect.getsource` + `inspect.signature`）的权威结论，优先级高于 T1 RFC/SPEC 中基于公开文档推断的 endpoint 主张。
