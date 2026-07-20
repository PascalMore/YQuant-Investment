# SPEC-03-014：Unified Data Phase 3 — 重要持久化扩展契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-20 |
| 最后更新 | 2026-07-20（V0.2 修正：scope 对齐、MongoDB-first/SQLite 边界、三份 docstring 精确免责措辞、API 预算标记待确认、不改动清单声明为本卡约束） |
| 来源 RFC | RFC-03-014（Phase 3 持久化扩展） |
| 关联 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-011（Phase 2 质量与审计治理）、RFC-03-013（Phase 1E 情绪最小切片） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约基线）、SPEC-03-008（Phase 1B-A 查询平面）、SPEC-03-013（Phase 1E 情绪最小切片） |
| 关联 Design | DESIGN-03-014（Phase 3 持久化扩展详细设计，后续 T2 交付） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 版本号 | V0.2 |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

### 版本历史

|| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|---|
|| V0.1 | 2026-07-20 | 初始创建。将 RFC-03-014 的 Phase 3 三阶段受控分期需求落为可执行契约，定义 SectorSnapshot / CapitalFlowRecord / MarketSentimentSnapshot 三个 domain object 字段级 schema、Provider 注册点、ETLV 验证点、读写路径边界与验收标准。 | YQuant-Principal |
|| V0.2 | 2026-07-20 | 修正：字段计数对齐（SectorSnapshot=19, CapitalFlowRecord=17, MarketSentimentSnapshot=22）；SectorSnapshot dataclass Python 语法修复（snapshot_date 移至 market 前）；唯一键全部纳入 market；拆分明细 query 与 ETLV refresh 写入路径；标记硬编码值（超时/限速）为可配置/待验证；AuditLogger 声明默认关闭；记录级可追溯字段表（quality_flags/source_record_id/schema_version 标为待定）；northbound_daily 明确为个股级 scope。 | YQuant-Principal |

---

## 0. 术语对齐与基线锚定

本 SPEC 继承 RFC-03-007 / SPEC-03-007 / SPEC-03-008 的全部基线，不重述背景，只锁定 Phase 3 必须一致的措辞：

- **Phase 3** = 重要持久化扩展。与 Phase 2（质量审计治理）独立可并行，与 Phase 1E（个股情绪最小切片）正交。
- **P3-A** = `03_data_ud_market_sector_snapshot` 板块/行业快照。Capabilities: `sector.snapshot`, `sector.ranking`。
- **P3-B** = `03_data_ud_stock_capital_flow` 个股资金流。Capabilities: `flow.capital_flow_daily`, `flow.northbound_daily`。
- **P3-C** = `03_data_ud_market_sentiment_snapshot` 市场情绪快照。Capabilities: `sentiment.market_snapshot`, `sentiment.limit_up_pool`。
- **AKShare 是 Phase 3 外部 Provider**：上述六个 capability 的 external_fallback_chain 为 `["akshare"]`。
- **MongoDB 是 Phase 3 唯一生产持久化目标**：所有 `03_data_ud_*` 物化集合以 **MongoDB（`tradingagents` 库）** 为默认生产写入与读取目标。SQLite 仅可用于以下明确限定场景：
  - 现有 legacy adapter 的数据源（如 DSA 的 SQLite 路径——DSA 不是运行时数据源，不出现在外部 fallback 链）
  - 单元测试 / 集成测试中的隔离数据库（如 mongomock 或临时 SQLite 替代）
  - 离线 fallback（仅当 MongoDB 完全不可达且消费方已通过配置显式授权）
  - **禁止**：SQLite 不得作为 Phase 3 正式生产写入目标，不得出现在 `03_data_ud_*` 集合的生产写入路径中。
- **internal-first 读取路径不变**：TA-CN 既有 → LocalMongo（`03_data_ud_*`）→ Cache → 外部 Provider。新集合通过 LocalMongoAdapter 读取。
- **MongoDB `tradingagents` 库**：所有 `03_data_ud_*` 物化集合位于此物理库，通过前缀隔离 ownership。

### 0.1 六项不变量逐条对应（RFC-03-007 §14 / SPEC-03-007 §0.2）

| # | 不变量 | Phase 3 SPEC 落点 |
|---|---|---|
| 1 | 共享物理数据库 `tradingagents` | §6.1：`03_data_ud_*` 集合位于 `tradingagents` 库，命名空间前缀隔离 |
| 2 | Internal-First 读取路径 | §5 读路径：TA-CN → LocalMongo → Cache → AKShare |
| 3 | DSA 不是运行时数据源 | §6.2：不实现 DSA adapter；DSA 不在 external_fallback_chains 中 |
| 4 | Collection Ownership 不可回写 | §6.2：Unified Data 绝不回写 TA-CN 既有无前缀集合 |
| 5 | Task Center 先行 | §6.2：不创建 Task Center Job；canary 手动触发 |
| 6 | 三层语义分离 | §6.1：物化数据 `03_data_ud_*` 可追溯；Query Cache `03_data_ud_cache_*` 可丢弃 |

---

## 1. 需求摘要

将 RFC-03-014 的 Phase 3 三阶段受控分期方案落为可执行契约，核心交付 6 件事：

1. **SectorSnapshot domain object**：`models/domain/sector.py` 中新增——19 个字段（类型、必填性、语义严格定义）。
2. **CapitalFlowRecord domain object**：`models/domain/flow.py` 中新增——17 个字段（类型、必填性、语义严格定义）。
3. **MarketSentimentSnapshot domain object**：`models/domain/sentiment.py` 中新增——22 个字段（类型、必填性、语义严格定义）。
4. **Provider 注册**：AKShareProvider 新增 6 个 capability；external_fallback_chains 注册；FreshnessPolicy 注册；TA_CN_NOT_COVERED 确认。
5. **读写路径定义**：internal-first 读取路径 + 外部 Provider 物化写入路径 + canary 手动触发模式。
6. **测试策略**：colocated 单元测试 + fixture + 离线约束。

---

## 2. 范围

### 2.1 In Scope

- [ ] P3-A: `SectorSnapshot` domain object 定义 + `sector.snapshot` / `sector.ranking` 能力注册
- [ ] P3-A: AKShareProvider 的 `sector.snapshot` / `sector.ranking` fetch 实现
- [ ] P3-A: `03_data_ud_market_sector_snapshot` 物化集合写入 + LocalMongoAdapter 读取
- [ ] P3-A: `sector_service.get_sector_snapshot()` / `sector_service.get_sector_ranking()` 实现
- [ ] P3-B: `CapitalFlowRecord` domain object 定义 + `flow.capital_flow_daily` / `flow.northbound_daily` 能力注册
- [ ] P3-B: AKShareProvider 的 `flow.capital_flow_daily` / `flow.northbound_daily` fetch 实现
- [ ] P3-B: `03_data_ud_stock_capital_flow` 物化集合写入 + LocalMongoAdapter 读取
- [ ] P3-B: `flow_service.get_capital_flow()` / `flow_service.get_northbound_flow()` 实现
- [ ] P3-C: `MarketSentimentSnapshot` domain object 定义 + `sentiment.market_snapshot` / `sentiment.limit_up_pool` 能力注册
- [ ] P3-C: AKShareProvider 的 `sentiment.market_snapshot` / `sentiment.limit_up_pool` fetch 实现
- [ ] P3-C: `03_data_ud_market_sentiment_snapshot` 物化集合写入 + LocalMongoAdapter 读取
- [ ] P3-C: `sentiment_service.get_market_snapshot()` / `sentiment_service.get_limit_up_pool()` 实现
- [ ] 全部：UnifiedDataClient 新增对应域方法（§5.1）
- [ ] 全部：colocated 单元测试 + fixture
- [ ] 全部：Pascal 逐项授权 Gate 确认后执行

### 2.2 Out of Scope

- ❌ 龙虎榜、筹码分布、热门股票（属 Phase 4）
- ❌ Task Center Job 创建、cron/systemd 调度（属 Phase 5）
- ❌ QualitySummary 读写（Phase 2 仍冻结）
- ❌ AuditLogger 启用写入（Phase 2 默认关闭；Phase 3 中不自动写入；需 Pascal 独立授权）
- ❌ Phase 1E 个股级情绪（当前为计划态契约；与 P3-C 正交不互相前置）
- ❌ 真实 API 调用在离线测试阶段（仅 smoke 阶段可调用）
- ❌ MongoDB DDL 在离线测试阶段（仅 Pascal 授权 Gate 后执行）
- ❌ 修改 TA-CN/DSA/Argus/portfolio/data-pipeline/task_center 代码
- ❌ 修改已有 domain object 的字段签名（`StockInfo`, `DailyBar`, `NewsItem` 等）
- ❌ 个股级情绪分数（属 Phase 1E；与 P3-C 市场级情绪正交）
- ❌ DSA adapter 实现或 DSA 数据源集成

---

## 3. Domain Object 字段级契约

### 3.1 SectorSnapshot

```python
# skills/data/unified_data/models/domain/sector.py（追加）

@dataclass
class SectorSnapshot:
    """板块/行业快照（Phase 3 P3-A）。

    每日各板块的聚合快照。每条记录表示一个板块在某交易日收盘后的快照数据。
    消费方可通过 sector.snapshot（单板块）和 sector.ranking（当日排名）获取。

    本数据为辅助研究数据，不构成交易指令或投资建议。
    """
    sector_code: str                           # (必填) 板块代码，如 "BK0489"
    sector_name: str                           # (必填) 板块名称，如 "白酒"
    sector_type: str                           # (必填) 板块类型：industry / concept / region / style
    snapshot_date: str                         # (必填) 快照日期，格式 "YYYY-MM-DD"
    market: str = "CN"                         # (必填) 市场
    provider: str = ""                         # (必填) 数据来源，如 "akshare"

    # 排名与涨跌
    rank: int | None = None                    # [可选] 当日涨幅排名（1=涨幅最高）
    pct_chg: float | None = None               # [可选] 板块涨跌幅 %（如 2.35）

    # 领涨信息
    leading_stock: str | None = None           # [可选] 领涨股代码（如 "600519"）
    leading_stock_name: str | None = None      # [可选] 领涨股名称
    leading_pct_chg: float | None = None       # [可选] 领涨股涨幅 %

    # 涨跌家数
    advance_count: int = 0                     # 上涨家数
    decline_count: int = 0                     # 下跌家数
    total_count: int = 0                       # 成分股总数

    # 资金流与量价
    turnover_rate: float | None = None         # [可选] 板块换手率 %
    main_net_inflow: float | None = None       # [可选] 主力净流入（元）

    # 元数据
    members: list[str] | None = None           # [可选] 成分股代码列表（用于离线分析，非核心查询字段）
    fetched_at: str | None = None              # [可选] 数据获取时间，ISO-8601
    raw_payload: dict | None = None            # [可选] 原始 AKShare 返回（调试/审计用，不用于生产查询路径）

    @classmethod
    def from_dict(cls, d: dict) -> "SectorSnapshot":
        """从字典构造，缺失字段填 None。松弛映射，不抛 KeyError。"""
        return cls(
            sector_code=str(d.get("sector_code", "")),
            sector_name=str(d.get("sector_name", "")),
            sector_type=str(d.get("sector_type", "")),
            snapshot_date=str(d.get("snapshot_date", "")),
            market=str(d.get("market", "CN")),
            provider=str(d.get("provider", "")),
            rank=d.get("rank"),
            pct_chg=d.get("pct_chg"),
            leading_stock=d.get("leading_stock"),
            leading_stock_name=d.get("leading_stock_name"),
            leading_pct_chg=d.get("leading_pct_chg"),
            advance_count=d.get("advance_count", 0) or 0,
            decline_count=d.get("decline_count", 0) or 0,
            total_count=d.get("total_count", 0) or 0,
            turnover_rate=d.get("turnover_rate"),
            main_net_inflow=d.get("main_net_inflow"),
            members=d.get("members"),
            fetched_at=d.get("fetched_at"),
            raw_payload=d.get("raw_payload"),
        )
```

**字段语义与约定**：

| 字段 | 约束 | 说明 |
|---|---|---|
| `sector_code` | 非空，最大 32 字符 | 东方财富板块代码，如 `BK0489` |
| `sector_type` | 枚举值：industry/concept/region/style | 行业/概念/地域/风格 |
| `rank` | 正整数，1=最高 | 若板块指数不可比则 None |
| `pct_chg` | float，无边界约束 | 板块指数当日涨跌幅 |
| `advance_count` + `decline_count` | 应 <= `total_count`，但不强校验 | 由 Provider 数据质量保证 |
| `members` | 最大 1000 个代码 | 长列表主要用于离线分析 |

**查询边界**：
- 主查询维度：`(sector_code, snapshot_date)` 或 `(snapshot_date, sector_type)` 或 `(snapshot_date)` 按 rank 排序
- 禁止在 `members` 字段上建多键索引（数组字段不用于查询条件）

### 3.2 CapitalFlowRecord

```python
# skills/data/unified_data/models/domain/flow.py（Phase 3 新增文件）

@dataclass
class CapitalFlowRecord:
    """个股资金流记录（Phase 3 P3-B）。

    每条记录表示个股在某交易日的资金流向数据。
    消费方可通过 flow.capital_flow_daily（个股）和 flow.northbound_daily（北向资金-个股级）获取。

    本数据为辅助研究数据，不构成交易指令或投资建议。

    record_scope 说明：
    - flow.capital_flow_daily 查询填充全部资金流字段（主力/大单/中单/小单/北向/融资融券）。
    - flow.northbound_daily 查询仅填充 northbound_* 字段（symbol/market/trade_date 必有，其余资金流字段为空）。
    两者共享同一集合 `03_data_ud_stock_capital_flow` 和同一 domain object，但查询时填充的字段子集不同。
    """
    symbol: str                              # (必填) 标的代码，如 "600519"
    market: str                              # (必填) 市场，如 "CN"
    trade_date: str                          # (必填) 交易日，格式 "YYYY-MM-DD"

    # 资金流核心字段
    main_net_inflow: float | None = None     # [可选] 主力净流入（元）；正=净流入，负=净流出
    super_large_net_inflow: float | None = None  # [可选] 超大单净流入（元）
    large_net_inflow: float | None = None    # [可选] 大单净流入（元）
    medium_net_inflow: float | None = None   # [可选] 中单净流入（元）
    small_net_inflow: float | None = None    # [可选] 小单净流入（元）
    main_net_inflow_ratio: float | None = None  # [可选] 主力净流入占比 %（如 8.5）

    # 北向资金（仅沪/深港通标的）
    northbound_net_inflow: float | None = None   # [可选] 北向净买入（元）
    northbound_hold_shares: float | None = None  # [可选] 北向持股数（股）
    northbound_hold_ratio: float | None = None   # [可选] 北向持股比例 %

    # 融资融券
    margin_buy: float | None = None              # [可选] 融资买入额（元）
    margin_sell: float | None = None             # [可选] 融券卖出额（元）
    margin_balance: float | None = None          # [可选] 融资余额（元）

    # 元数据
    fetched_at: str | None = None              # [可选] 数据获取时间，ISO-8601
    provider: str = ""                         # (必填) 数据来源，如 "akshare"

    @classmethod
    def from_dict(cls, d: dict) -> "CapitalFlowRecord":
        """从字典构造，缺失字段填 None。松弛映射，不抛 KeyError。"""
        return cls(
            symbol=str(d.get("symbol", "")),
            market=str(d.get("market", "")),
            trade_date=str(d.get("trade_date", "")),
            main_net_inflow=d.get("main_net_inflow"),
            super_large_net_inflow=d.get("super_large_net_inflow"),
            large_net_inflow=d.get("large_net_inflow"),
            medium_net_inflow=d.get("medium_net_inflow"),
            small_net_inflow=d.get("small_net_inflow"),
            main_net_inflow_ratio=d.get("main_net_inflow_ratio"),
            northbound_net_inflow=d.get("northbound_net_inflow"),
            northbound_hold_shares=d.get("northbound_hold_shares"),
            northbound_hold_ratio=d.get("northbound_hold_ratio"),
            margin_buy=d.get("margin_buy"),
            margin_sell=d.get("margin_sell"),
            margin_balance=d.get("margin_balance"),
            fetched_at=d.get("fetched_at"),
            provider=str(d.get("provider", "")),
        )
```

**字段语义与约定**：

| 字段 | 约束 | 说明 |
|---|---|---|
| `main_net_inflow` | 正=净流入，负=净流出 | 通常为超大单+大单净流入之和 |
| `super_large_net_inflow` | 同上 | ≥500 万元（超大单阈值） |
| `large_net_inflow` | 同上 | ≥100 万且 < 500 万元（大单阈值） |
| `medium_net_inflow` | 同上 | ≥20 万且 < 100 万元（中单阈值） |
| `small_net_inflow` | 同上 | < 20 万元（小单阈值） |
| `northbound_*` | 非沪深港通标的返回 None | 由 Provider 数据质量保证；[待验证] |
| `margin_*` | 融资融券标的返回数值；非标返回 None | [待验证] |

**资金流符号约定**（重要）：所有 `*_net_inflow` 字段统一符号约定：**正值 = 净流入（资金买入）**，**负值 = 净流出（资金卖出）**。消费方应统一使用此约定解析，不需关注 Provider 内部符号。

**禁止字段**：本 domain object 不包含 `raw_payload` 字段——资金流数据量大（全市场日均数千条），不宜携带原始 payload。

### 3.3 MarketSentimentSnapshot

```python
# skills/data/unified_data/models/domain/sentiment.py（Phase 3 追加；Phase 1E 的 StockSentimentScore 同文件）

@dataclass
class MarketSentimentSnapshot:
    """市场情绪快照（Phase 3 P3-C）。

    每条记录表示全市场在某观测时点的情绪/温度快照数据。
    消费方可通过 sentiment.market_snapshot（市场快照）和 sentiment.limit_up_pool（涨停池）获取。

    本数据为辅助研究数据，不构成交易指令或投资建议。
    """
    snapshot_date: str                        # (必填) 快照日期，格式 "YYYY-MM-DD"
    snapshot_time: str                        # (必填) 快照时间，24h 格式如 "15:00:00" 或 "close"
    market: str = "CN"                        # (必填) 市场

    # 涨跌停数据
    limit_up_count: int = 0                   # 涨停家数（含 ST）
    limit_down_count: int = 0                 # 跌停家数（含 ST）
    limit_up_count_ex_st: int | None = None   # [可选] 涨停家数（不含 ST）
    limit_down_count_ex_st: int | None = None # [可选] 跌停家数（不含 ST）

    # 全市场涨跌数据
    advance_count: int = 0                    # 全市场上涨家数
    decline_count: int = 0                    # 全市场下跌家数
    flat_count: int = 0                       # 平盘家数
    total_listed_count: int | None = None     # [可选] 全市场上市公司总数

    # 指数与温度
    market_temperature: float | None = None   # [可选] 市场温度 0-100（基于多指标合成）
    total_turnover: float | None = None       # [可选] 全市场成交额（元）

    # 热门概念与连板
    hot_concepts: list[str] | None = None     # [可选] 当日热门概念列表
    continuous_limit_up: list[dict] | None = None  # [可选] 连板股票：[{"symbol":..., "days": N, "reason":...}]
    max_continuous_days: int | None = None    # [可选] 当日最大连板天数

    # 北向与额外资
    northbound_net_flow: float | None = None  # [可选] 北向资金净流入（元）

    # 涨停/跌停池（可选：若单独提供 limit_up_pool capability，则本字段可为空）
    limit_up_pool: list[str] | None = None    # [可选] 涨停股票代码列表
    limit_down_pool: list[str] | None = None  # [可选] 跌停股票代码列表

    # 元数据
    fetched_at: str | None = None             # [可选] 数据获取时间，ISO-8601
    provider: str = ""                        # (必填) 数据来源，如 "akshare"
    raw_payload: dict | None = None           # [可选] 原始 Provider 返回（调试/审计用）

    @classmethod
    def from_dict(cls, d: dict) -> "MarketSentimentSnapshot":
        """从字典构造，缺失字段填 None。松弛映射，不抛 KeyError。"""
        return cls(
            snapshot_date=str(d.get("snapshot_date", "")),
            snapshot_time=str(d.get("snapshot_time", "")),
            market=str(d.get("market", "CN")),
            limit_up_count=d.get("limit_up_count", 0) or 0,
            limit_down_count=d.get("limit_down_count", 0) or 0,
            limit_up_count_ex_st=d.get("limit_up_count_ex_st"),
            limit_down_count_ex_st=d.get("limit_down_count_ex_st"),
            advance_count=d.get("advance_count", 0) or 0,
            decline_count=d.get("decline_count", 0) or 0,
            flat_count=d.get("flat_count", 0) or 0,
            total_listed_count=d.get("total_listed_count"),
            market_temperature=d.get("market_temperature"),
            total_turnover=d.get("total_turnover"),
            hot_concepts=d.get("hot_concepts"),
            continuous_limit_up=d.get("continuous_limit_up"),
            max_continuous_days=d.get("max_continuous_days"),
            northbound_net_flow=d.get("northbound_net_flow"),
            limit_up_pool=d.get("limit_up_pool"),
            limit_down_pool=d.get("limit_down_pool"),
            fetched_at=d.get("fetched_at"),
            provider=str(d.get("provider", "")),
            raw_payload=d.get("raw_payload"),
        )
```

**字段语义与约定**：

| 字段 | 约束 | 说明 |
|---|---|---|
| `snapshot_time` | 格式 "HH:MM:SS" 或 "close" | `close` 表示收盘后快照 |
| `market_temperature` | 0-100 区间 | 合成指标：[假设] 基于涨跌比、涨停强度、成交额等多指标合成；合成公式由 Domain Service 内部实现 |
| `limit_up_pool` / `limit_down_pool` | 每个列表最大 500 个代码 | 若独立提供 `sentiment.limit_up_pool` capability，此集合中的对应字段可为空 |
| `continuous_limit_up` | list of dict，每条含 `symbol`, `days`, `reason` | reason 为自由字符串 |

**温度合成公式待定**：`market_temperature` 为派生字段，由 `sentiment_service` 在 Provider 原始数据上合成。T2 Design 阶段需定义合成公式或确认保留为 `None` 由消费方自行计算。

---

## 4. 注册点

### 4.1 AKShareProvider Capabilities 扩展

<!-- 假设：AKShareProvider 现有 capabilities 集合可自然扩展；T3 实施阶段确认 import 与 API 可用性 -->

在 `providers/akshare.py` 的 `capabilities` 集合中新增：

```python
# P3-A
"sector.snapshot",        # 板块/行业快照（单板块）
"sector.ranking",         # 板块/行业排名（全部板块按涨幅）

# P3-B
"flow.capital_flow_daily",   # 个股日资金流
"flow.northbound_daily",     # 北向资金日数据

# P3-C
"sentiment.market_snapshot", # 市场情绪快照
"sentiment.limit_up_pool",   # 涨停/跌停池
```

**不改动**：`TushareProvider` 的 capabilities 保持不变（Phase 3 不激活 Tushare 板块/资金流/情绪 API）。

### 4.2 external_fallback_chains

通过 `DataRouter(external_fallback_chains=...)` 构造参数传入（优先级：constructor → `UnifiedDataConfig.fallback_for(capability)` → registry 注册顺序）：

```python
external_fallback_chains = {
    # P3-A
    "sector.snapshot": ["akshare"],
    "sector.ranking": ["akshare"],
    # P3-B
    "flow.capital_flow_daily": ["akshare"],
    "flow.northbound_daily": ["akshare"],
    # P3-C
    "sentiment.market_snapshot": ["akshare"],
    "sentiment.limit_up_pool": ["akshare"],
}
```

**不改动**：现有所有 capability 的 fallback 链不变。

### 4.3 STUB_COLUMNS（`providers/_stub_columns.py`）

在 `STUB_COLUMNS` dict 中新增条目：

```python
# P3-A
"sector.snapshot": [
    "sector_code", "sector_name", "sector_type", "snapshot_date",
    "rank", "pct_chg", "leading_stock", "advance_count", "decline_count",
    "total_count", "turnover_rate", "main_net_inflow",
],
"sector.ranking": [
    "sector_code", "sector_name", "sector_type", "snapshot_date",
    "rank", "pct_chg", "advance_count", "decline_count",
],

# P3-B
"flow.capital_flow_daily": [
    "symbol", "market", "trade_date",
    "main_net_inflow", "super_large_net_inflow", "large_net_inflow",
    "medium_net_inflow", "small_net_inflow", "main_net_inflow_ratio",
    "northbound_net_inflow", "margin_balance",
],
"flow.northbound_daily": [
    "symbol", "market", "trade_date", "northbound_net_inflow", "northbound_hold_shares",
],

# P3-C
"sentiment.market_snapshot": [
    "snapshot_date", "snapshot_time",
    "limit_up_count", "limit_down_count",
    "advance_count", "decline_count", "flat_count",
    "market_temperature", "total_turnover",
    "northbound_net_flow", "hot_concepts",
],
"sentiment.limit_up_pool": [
    "snapshot_date", "snapshot_time",
    "symbol", "reason", "days",
],
```

**不改动**：现有所有 stub 列定义不变。

### 4.4 FreshnessPolicy（`freshness.py`）

在 FreshnessPolicy 的默认 TTL 映射中新增：

```python
# Phase 3 新增 domain TTL（各域在现有 DEFAULT_TTLS 中已有条目，此处确认值不变）
"flow": 43200,         # 12h — 资金流数据日盘后刷新即可
"sector": 21600,       # 6h — 板块快照收盘后刷新即可
"sentiment": 3600,     # 1h — 情绪数据（已有；确认值对市场级情绪仍然适用）
```

**不改动**：现有所有 TTL 值不变。

### 4.5 DataRouter `_TA_CN_NOT_COVERED`（`router.py`）

确认 Phase 3 的六个 capability 均不在 `_TA_CN_CAPABILITY_METHOD_MAP` 中，需在 `_TA_CN_NOT_COVERED` 中新增：

```python
_TA_CN_NOT_COVERED: frozenset[str] = frozenset({
    ...
    # P3-A
    "sector.snapshot",
    "sector.ranking",
    # P3-B
    "flow.capital_flow_daily",
    "flow.northbound_daily",
    # P3-C
    "sentiment.market_snapshot",
    "sentiment.limit_up_pool",
})
```

**不改动**：现有 `_TA_CN_CAPABILITY_METHOD_MAP` 和相关不变量不变。

### 4.6 Capability 常量（如有能力常量模块）

如项目已有常量模式，在相应常量集合中新增：

```python
# P3-A
SECTOR_SNAPSHOT = "sector.snapshot"
SECTOR_RANKING = "sector.ranking"
# P3-B
FLOW_CAPITAL_FLOW_DAILY = "flow.capital_flow_daily"
FLOW_NORTHBOUND_DAILY = "flow.northbound_daily"
# P3-C
SENTIMENT_MARKET_SNAPSHOT = "sentiment.market_snapshot"
SENTIMENT_LIMIT_UP_POOL = "sentiment.limit_up_pool"
```

如无常量模块，Design 阶段裁定是否新增。

---

## 4.bis 持久化契约

### 4.bis.1 集合概览

| 集合名 | 子阶段 | 唯一键 | 索引 | TTL |
|---|---|---|---|---|
|| `03_data_ud_market_sector_snapshot` | P3-A | `{market, sector_code, snapshot_date}` | `{sector_code:1, snapshot_date:-1}`, `{snapshot_date:-1}`, `{sector_type:1, snapshot_date:-1}` | 无（物化可追溯数据） |
|| `03_data_ud_stock_capital_flow` | P3-B | `{market, symbol, trade_date}` | `{symbol:1, trade_date:-1}`, `{trade_date:-1}` | 无（物化可追溯数据） |
|| `03_data_ud_market_sentiment_snapshot` | P3-C | `{market, snapshot_date, snapshot_time}` | `{snapshot_date:-1}`, `{snapshot_time:-1}` | 无（物化可追溯数据） |

**唯一键语义**：同一唯一键的记录通过 upsert（`update_one` with `$set`）更新，相同键的后续写入覆盖先前的完整记录。不保留历史版本（如需版本跟踪属 Phase 5+）。

**记录级可追溯字段**：每条记录至少包含以下字段，用于来源追溯与数据质量判定。这些字段不属于 `03_data_ud_quality_summary`（QualitySummary 仍冻结），不参与 Phase 2 质量评分。

| 字段 | 说明 | 所属 domain object | 待定状态 |
|---|---|---|---|
| `provider` | 数据来源标识，如 `"akshare"` | 全部三个 | 已定 |
| `fetched_at` | 数据获取时间，ISO-8601 格式 | 全部三个 | 已定 |
| `quality_flags` | 非汇总质量标记，`list[str]`；如 `["stale_data", "partial_fill"]`。不写入 QualitySummary 集合 | 全部三个 | **[待定]** T2 Design 裁定是否需要 |
| `source_record_id` | Provider 侧的记录唯一标识（如 AKShare 的行索引或 API 分页 marker） | 全部三个 | **[待定]** T2 Design 裁定是否需要 |
| `schema_version` | 该记录的 domain object schema 版本号（语义版本号） | 全部三个 | **[待定]** T2 Design 裁定是否需要 |

**禁止字段**：上述集合中**不包含** `quality_summary`、`quality_score` 等 Phase 2 质量字段——QualitySummary 仍冻结（RFC-03-011）。

### 4.bis.2 写入策略（仅显式 refresh 路径）

以下写入行为仅发生在显式调用的 refresh 方法中（如 `sector_service.refresh_sector_snapshot()`），**不**发生在标准 `DataRouter.query()` 路径中：

1. **Provider fetch 成功后写入物化集合**：`db[collection].update_one(filter=unique_key, update={"$set": doc}, upsert=True)`
2. **同时写入 Cache**：`CacheManager.put()` 更新 Query Cache（refresh 路径的 Cache 写入为幂等操作）
3. **不写入 AuditLogger**：Phase 2 AuditLogger 为独立授权，不在 Phase 3 默认启用；refresh 方法可预留扩展点（try-pass 模式，不影响主流程）
4. **不写入 QualitySummary**：QualitySummary 仍冻结

**query 路径的 fetch 行为**：标准 `DataRouter.query()` 的 Step 4 从外部 Provider fetch 成功后，**仅**返回 `DataResult.success(data=..., provider="<name>")`，不写入物化集合、不写入 Cache。query 路径全程只读。

### 4.bis.3 数据保留策略

| 数据 | 保留策略 | 备注 |
|---|---|---|
| 板块快照 | 无 TTL，永久保留 | 历史板块表现用于策略回测 |
| 资金流 | 无 TTL，永久保留 | 用于因子计算和回测 |
| 市场情绪 | 无 TTL，永久保留 | 用于市场状态分析和回测 |

> **注意**：无 TTL 策略为默认值。如后续存储成本超出预期，可单独授权添加 TTL 或多个存储分层。此决策不在 Phase 3 范围。

### 4.bis.4 空数据/失败写入处理

| 场景 | 行为 |
|---|---|
| Provider fetch 成功但返回空数据 | 不写入物化集合，不写入 Cache；返回 `DataResult.success(data=[], provider="akshare")` |
| Provider 不可用请求失败 | 返回 `DataResult.error(provider="error", source_trace=["akshare(error: ...)"])`；不写入物化集合 |
| MongoDB 写入失败 | 不阻断查询路径，catch-and-log；Cache 写入也 catch-and-log |

---

## 5. 读路径与写路径边界

### 5.1 UnifiedDataClient 新增方法

| 域 | 方法 | 返回 DataResult.data 类型 | 子阶段 |
|---|---|---|---|
| sector | `get_sector_snapshot(sector_code, date=None)` | `SectorSnapshot`（单条） | P3-A |
| sector | `get_sector_ranking(date=None, sector_type=None, limit=20)` | `list[SectorSnapshot]` | P3-A |
| flow | `get_capital_flow(security_id, limit=60, start_date=None, end_date=None)` | `list[CapitalFlowRecord]` | P3-B |
| flow | `get_northbound_flow(security_id=None, date=None, start_date=None, end_date=None)` | `list[CapitalFlowRecord]`（仅 `northbound_*` 字段；个股级北向） | P3-B |
| sentiment | `get_market_sentiment(date=None)` | `MarketSentimentSnapshot`（单条，收盘后） | P3-C |
| sentiment | `get_limit_up_pool(date=None)` | `list[dict]`（symbol + reason + days） | P3-C |

### 5.2 Read Path（Internal-First）

```
UnifiedDataClient.query("sector", "snapshot", sector_code=SectorCode("BK0489"))
    │
    ├─ Step 1: TA_CNMongoAdapter.sector.snapshot?
    │   [假设/待验证] sector.snapshot 部分数据可通过 index_daily_queries 推导
    │   若推导可行 → 返回 DataResult(provider="ta_cn_internal", freshness="delayed")
    │   若不可行 → 继续 Step 2
    │
    ├─ Step 2: LocalMongoAdapter → 03_data_ud_market_sector_snapshot
    │   命中 + 未过期 → 返回 DataResult(provider="ud_materialized", freshness="cached")
    │   未命中 → 继续
    │
    ├─ Step 3: CacheManager.get() → 03_data_ud_cache_sector_snapshot
    │   命中 + 未过期 → 返回 DataResult(freshness="cached")
    │   未命中 → 继续
    │
    └─ Step 4: AKShareProvider.fetch("sector", "snapshot", ...)
           成功 → 返回 DataResult(provider="akshare", freshness="delayed")
           （不写入物化集合、不写入 Cache——写入仅通过显式 refresh 路径）
```

**关键差异**：
- P3-A 的 Step 1 可覆盖程度[待验证]——`index_daily_quotes` 仅覆盖申万行业指数（L1 级别），不覆盖概念/区域板块
- P3-B 的 Step 1 不可用——资金流非 TA-CN 既有集合范围
- P3-C 的 Step 1 不可用——市场情绪非 TA-CN 既有集合范围

### 5.3 Write Path（生产 — 显式 refresh 路径）

| 触发方式 | 行为 | 授权 |
|---|---|---|
| 显式调用 refresh 方法（如 `sector_service.refresh_sector_snapshot()`） | Provider fetch → 写入 `03_data_ud_*` 物化集合 + CacheManager.put() | Gate G-A-2/G-B-2/G-C-2（首次调用）；canary 门禁见 §10 |
| 手动触发（Canary） | Pascal 手动调用 service.refresh_xxx() → 单次写入 | Gate G-A-3/G-B-3/G-C-3 |
| 长期调度 | 由 Task Center Job 触发（Phase 5） | 不在 Phase 3 范围 |
| CLI 脚本 | 可选的离线回填 CLI（T2 Design 裁定） | 另行授权 |

### 5.4 Write Path（测试/离线）

| 场景 | 行为 |
|---|---|
| 单元测试 | MockProvider 返回 fixture 数据 → 不写 MongoDB |
| 集成测试 | mongomock 注入 → 写入/读取内存集合 |
| Provider smoke | 真实 AKShare API 调用（Gate 授权后）→ 写真实 MongoDB（smoke 专用测试库或临时集合） |

---

## 6. ETLV 验证点

### 6.1 公共验证点

| # | 验证点 | 描述 | 子阶段 | 验证方式 |
|---|---|---|---|---|
| V-GEN-1 | **唯一键幂等性** | 相同唯一键的重复写入应当 upsert，不产生重复记录 | 全部 | 单元测试：mock 数据库验证 upsert 行为 |
|| V-GEN-2 | **Provider fetch 超时** | AKShare fetch 超时（可配置，默认 `30s`；[待验证] AKShare 实际响应时间分布）后降级为 `DataResult.error` | 全部 | 集成测试：mock Provider 模拟超时 |
| V-GEN-3 | **空 Provider 返回** | Provider 返回空 DataFrame → 成功但 data=[] | 全部 | 单元测试 |
| V-GEN-4 | **数据格式** | `snapshot_date` / `trade_date` 格式为 `YYYY-MM-DD` | 全部 | 单元测试：正则校验 |
| V-GEN-5 | **来源可追溯** | `provider` 字段非空 | 全部 | fixture 验证：3 字段均非空 |
| V-GEN-6 | **辅助研究声明** | domain object docstring 标注「辅助研究数据，不构成交易指令或投资建议」 | 全部 | 静态 grep 验证：`grep -c '辅助研究数据，不构成交易指令或投资建议'` 三份 docstring 各至少出现 1 次 |

### 6.2 域特定验证点

| # | 验证点 | 描述 | 子阶段 | 验证方式 |
|---|---|---|---|---|
| V-SEC-1 | **板块类型枚举** | `sector_type` 取值仅为 industry/concept/region/style | P3-A | 单元测试：通过 `from_dict` 验证有效/无效值 |
| V-SEC-2 | **涨跌家数一致性** | `advance_count + decline_count <= total_count` | P3-A | 单元测试：构造不一致数据，确认不抛异常 |
| V-SEC-3 | **资金流符号约定** | 所有 `*_net_inflow` 字段：正=净流入，负=净流出 | P3-B | 单元测试：fixture 数据 + Provider mock 验证符号一致性 |
| V-SEC-4 | **北向资金为空处理** | 非沪深港通标的的北向字段返回 None | P3-B | 单元测试：fixture 覆盖无北向数据场景 |
| V-SEC-5 | **市场温度范围** | `market_temperature` 如果提供，应在 [0, 100] 区间 | P3-C | 单元测试：边界值 0/50/100/None 验证 |
| V-SEC-6 | **涨跌停池长度** | `limit_up_pool` 长度不超过 500 | P3-C | 单元测试：超长列表截断或记录警告 |
| V-SEC-7 | **连续涨停天数** | `max_continuous_days` >= `continuous_limit_up` 中各 days 最大值 | P3-C | 单元测试：fixture 交叉验证 |
| V-SEC-8 | **P3-C 不与 Phase 1E 混淆** | MarketSentimentSnapshot 不包含 StockSentimentScore 字段 | P3-C | 静态检查：确认两类的字段无同名冲突 |

---

## 7. 验收标准

| 编号 | 验收项 | 验证方式 | 子阶段 |
|---|---|---|---|
|| A-001 | `SectorSnapshot` domain object 定义完整（19 个字段 + `from_dict`） | Python import + `from_dict()` 返回有效对象 | P3-A |
|| A-002 | `CapitalFlowRecord` domain object 定义完整（17 个字段 + `from_dict`） | 同上 | P3-B |
|| A-003 | `MarketSentimentSnapshot` domain object 定义完整（22 个字段 + `from_dict`） | 同上 | P3-C |
| A-004 | AKShareProvider 新增 6 个 capability 注册成功 | `registry.has_capability("sector.snapshot", "CN") == True` | 全部 |
| A-005 | external_fallback_chains 中 Phase 3 六项正确注册 | 断言 `chain` 为 `["akshare"]` | 全部 |
| A-006 | FreshnessPolicy flow/sector/sentiment TTL 正确注册 | `policy.get_ttl("flow") == 43200` 等 | 全部 |
| A-007 | `_TA_CN_NOT_COVERED` 含 Phase 3 六项 capability | `"sector.snapshot" in Router._TA_CN_NOT_COVERED` | 全部 |
| A-008 | 现有 Phase 1D 基线测试 Regression PASS | `pytest skills/data/unified_data/tests -q` exit 0 | 全部 |
| A-009 | P3-A 单元测试：mock provider 注册后 Router 查询返回 DataResult.success | Python 断言 | P3-A |
| A-010 | P3-A 单元测试：无 provider 注册时返回 DataResult.error | Python 断言 | P3-A |
| A-011 | P3-B 单元测试：资金流符号约定验证 | Python 断言 | P3-B |
| A-012 | P3-C 单元测试：市场温度范围验证 | Python 断言 | P3-C |
| A-013 | `git diff --check` exit 0 | 终端命令 | 全部 |
| A-014 | `git diff --name-status` 仅含目标文件 | 终端命令 | 全部 |
| A-015 | 文档中明确声明所有数据为「辅助研究数据，不构成交易指令或投资建议」 | `grep -c '辅助研究数据，不构成交易指令或投资建议'` 在 SPEC 三份 domain object docstring 中至少出现 3 次 | 全部 |

---

## 8. 测试要求

### 8.1 单元测试

| 测试文件 | 覆盖内容 | 预期用例数 | 子阶段 | 是否需网络 |
|---|---|---|---|---|
| `test_sector_snapshot.py` | SectorSnapshot 构造、from_dict、字段边界、枚举值 | 8 | P3-A | 否 |
| `test_sector_service.py` | get_sector_snapshot/ranking（mock provider）、空数据、error 分支 | 6 | P3-A | 否 |
| `test_capital_flow.py` | CapitalFlowRecord 构造、from_dict、符号约定、北向空处理 | 10 | P3-B | 否 |
| `test_flow_service.py` | get_capital_flow/northbound_flow（mock provider）、分页、限流 | 6 | P3-B | 否 |
| `test_market_sentiment.py` | MarketSentimentSnapshot 构造、from_dict、温度范围 | 8 | P3-C | 否 |
| `test_sentiment_service.py` | get_market_snapshot/limit_up_pool（mock provider）、连板交叉验证 | 6 | P3-C | 否 |
| `test_provider_phase3.py` | AKShareProvider Phase 3 新增 capability 的 stub/fake fetch、STUB_COLUMNS 验证 | 6 | 全部 | 否 |

### 8.2 Fixture

| Fixture 文件 | 内容 | 子阶段 |
|---|---|---|
| `skills/data/unified_data/tests/fixtures/sector_fixtures.py` | 2 条 SectorSnapshot：industry（白酒）+ concept（AI），正常交易日 + 极端行情 | P3-A |
| `skills/data/unified_data/tests/fixtures/flow_fixtures.py` | 2 条 CapitalFlowRecord：含北向数据（沪深港通标的）+ 不含北向（非标的） | P3-B |
| `skills/data/unified_data/tests/fixtures/sentiment_fixtures.py` | 2 条 MarketSentimentSnapshot：正常交易日 + 极端行情（大量涨停） | P3-C |

### 8.3 回归测试

```bash
# Phase 1D 基线 — 跑前确认
.venv/bin/python -m pytest skills/data/unified_data/tests -q --tb=short  # exit 0

# Phase 3 新增测试（按子阶段）
# P3-A
.venv/bin/python -m pytest skills/data/unified_data/tests/test_sector_*.py -q --tb=short
# P3-B
.venv/bin/python -m pytest skills/data/unified_data/tests/test_capital_*.py skills/data/unified_data/tests/test_flow_*.py -q --tb=short
# P3-C
.venv/bin/python -m pytest skills/data/unified_data/tests/test_market_sentiment*.py skills/data/unified_data/tests/test_sentiment_service*.py -q --tb=short
```

### 8.4 不可自动化验证项

- 「所有数据为辅助研究数据」的声明在 SPEC 三份 domain object docstring 中通过静态 grep 验证（V-GEN-6 / A-015），不再需要手动审核
- Pascal Gate 逐项授权确认：非自动化项

---

## 9. 实现约束

### 9.1 禁止事项

- ❌ 任何形式的真实网络请求在单元测试阶段
- ❌ MongoDB 写入在单元测试和集成测试中（仅 mongomock）
- ❌ 修改 TA-CN adapter 方法签名或 capability 集合
- ❌ 修改已有 domain object（StockInfo, DailyBar, NewsItem 等）
- ❌ 修改 DataRouter 的 query() 逻辑（internal-first 编排不变）
- ❌ 修改 DataResult 或 Capability 的签名
- ❌ 读取 `.env` 或任何凭据文件
- ❌ 创建 Task Center Job、cron/systemd 配置
- ❌ 一次性部署三个子阶段

### 9.2 依赖限制

- 不新增任何第三方 Python 包依赖（AKShare 已在 unified_data 的依赖中）
- AKShare Provider 继承已有的 `DataProvider` ABC，注册到 `ProviderRegistry`

### 9.3 性能/安全/风控约束

- AKShareProvider 的 Phase 3 fetch 方法应遵守与 Phase 1 相同的限流策略（每请求间隔为可配置参数，[待验证] AKShare 实际频率限制）——见 RFC-03-012 §5.2
- `raw_payload` 字段使用 `dict` 而非序列化字符串——MongoDB 原生支持嵌套文档
- 资金流批量回填时需限速（batch size 和间隔待 T2 Design 裁定；[待验证] AKShare 实际限频阈值），避免触发 AKShare 频率限制
- Provider fetch 超时为可配置参数（[待验证] AKShare 实际响应时间分布）——V-GEN-2 中的超时值为建议默认值，非固定值
- 所有 domain object docstring 必须包含「辅助研究数据，不构成交易指令或投资建议」

---

## 10. Pascal 授权 Gate 汇总

| Gate ID | 动作 | 集合/API | 影响范围 | 停止条件 | 子阶段 |
|---|---|---|---|---|---|
| G-A-1 | `db.createCollection("03_data_ud_market_sector_snapshot")` + `createIndex()` | MongoDB | 新增集合 3 个索引 | Pascal 确认 schema | P3-A |
| G-A-2 | AKShareProvider 首次真实调用 `sector.snapshot` / `sector.ranking` | AKShare API | [待 Pascal 在具体 Gate 授权时确认的请求预算/计量单位]；当前 Gate 仅确认首次 smoke 可行，不做全量预算估计 | smoke 成功 + 日志审核 | P3-A |
| G-A-3 | 手动触发一日 canary 采集 | MongoDB + AKShare | 当日板块快照写入 | Pascal 审核数据质量 | P3-A |
| G-B-1 | `db.createCollection("03_data_ud_stock_capital_flow")` + `createIndex()` | MongoDB | 新增集合 2 个索引 | Pascal 确认 schema | P3-B |
| G-B-2 | AKShareProvider 首次真实调用 `flow.capital_flow_daily` / `flow.northbound_daily` | AKShare API | [待 Pascal 在具体 Gate 授权时确认的请求预算/计量单位]；当前 Gate 仅确认首次 smoke 可行，不做全量预算估计 | smoke 成功 | P3-B |
| G-B-3 | 手动触发 canary：单日个股资金流采集（分批、限速） | MongoDB + AKShare | 全量标的写入 | Pascal 审核数据质量 | P3-B |
| G-C-1 | `db.createCollection("03_data_ud_market_sentiment_snapshot")` + `createIndex()` | MongoDB | 新增集合 2 个索引 | Pascal 确认 schema | P3-C |
| G-C-2 | AKShareProvider 首次真实调用 `sentiment.market_snapshot` / `sentiment.limit_up_pool` | AKShare API | [待 Pascal 在具体 Gate 授权时确认的请求预算/计量单位]；当前 Gate 仅确认首次 smoke 可行，不做全量预算估计 | smoke 成功 | P3-C |
| G-C-3 | 手动触发 canary：单日情绪快照采集 | MongoDB + AKShare | 当日情绪数据写入 | Pascal 审核数据质量 | P3-C |

---

## 11. 开放问题

- [ ] OQ-1：资金流数据是否需要分钟级盘中快照？当前仅日级。如需要，P3-B 的 collection schema 需增加 `snapshot_time` 维度。
- [ ] OQ-2：`market_temperature` 合成公式？当前未定义，留作 Domain Service 内部实现或 T2 Design 裁定。
- [ ] OQ-3：`SectorSnapshot.members` 字段是否必要？如需要，更新频率为每日/每周？
- [ ] OQ-4：3 个子阶段的执行顺序是否接受推荐序（P3-A → P3-B → P3-C）？
- [ ] OQ-5：`03_data_ud_stock_capital_flow` 的倒填（backfill）策略？是否需要回填历史 N 个月数据？若需要，batch size 和限流策略。

---

## 12. 不改动清单（Confirm No Changes — 本卡约束，非全局声明）

以下文件/组件在本卡 diff 范围中 **不得出现修改**。本清单仅约束本 SPEC 对应的实现阶段（T3 Implement），不构成对共享 worktree 全局状态的不可证明断言。任何本卡允许的 diff 中触及这些文件的行将触发验收 FAIL：

| 文件/组件 | 理由 |
|---|---|
| `skills/data/unified_data/models/domain/news.py` | NewsItem 保持向后兼容 |
| `skills/data/unified_data/models/__init__.py` 中 `DataResult`/`Capability`/`SecurityId` | Phase 0 公共契约不变 |
| `skills/data/unified_data/client.py` 已有方法签名 | 不修改签名；允许新增方法 |
| `skills/data/unified_data/router.py` `query()` 方法逻辑 | Router internal-first 编排不变 |
| `skills/data/unified_data/providers/tushare.py` capabilities | 不声明 Phase 3 capability |
| `skills/apps/TradingAgents-CN/**` | TA-CN 子项目不修改 |
| `skills/research/daily_stock_analysis/**` | DSA 子系统不修改 |
| `skills/data/data-pipeline/**` | ETL 管道不修改 |
| `skills/data/data_interface/**` | Portfolio IReader/IWriter 不修改 |
| `skills/research/argus/**` | Argus 信号系统不修改 |
| 任何 Template / README / SKILL | 全局规约源不变 |
| 任何 cron / systemd 配置 | 不在 Phase 3 范围 |

---

## 13. 参考资料

- RFC-03-014（Phase 3 持久化扩展）—— 本 SPEC 的来源文档
- DESIGN-03-007（Unified Data Layer 详细设计），§5.3 Phase 3 集合草稿、§6.7 SectorSnapshot / CapitalFlowRecord / MarketSentimentSnapshot 原型
- SPEC-03-007（Unified Data Layer 契约基线）
- SPEC-03-008（Phase 1B-A 查询平面）
- SPEC-03-013（Phase 1E 情绪最小切片）—— Phase 1E StockSentimentScore 与 P3-C MarketSentimentSnapshot 的层级关系
- RFC-03-013（Phase 1E Sentiment Minimal Slice）
- `skills/data/unified_data/providers/akshare.py`（AKShare Provider 实现）
- `skills/data/unified_data/freshness.py`（FreshnessPolicy TTL 注册点）
- `skills/data/unified_data/providers/_stub_columns.py`（STUB_COLUMNS 注册点）
- `skills/data/unified_data/router.py`（external_fallback_chains 通过构造参数传入；_TA_CN_NOT_COVERED 注册点）
