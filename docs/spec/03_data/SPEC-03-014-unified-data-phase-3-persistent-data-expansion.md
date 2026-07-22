# SPEC-03-014：Unified Data Phase 3 — 重要持久化扩展契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-20 |
| 最后更新 | 2026-07-22（V0.4 AKShare 无 Token + 复用 Phase 2 MONGO_URI 同步：§0 PR-Gate 定义更新；§10.bis PR-0 Gate 分割 AKShare 跳过密钥审计 + MongoDB 改为 `MONGO_URI`；PR-2/PR-3/PR-4 移除 token 消耗语义；§14.1 副作用矩阵移除 token 消耗；§14.3 审计表移除 AKSHARE_TOKEN、MONGODB_URI→MONGO_URI；§11 OQ-8 标记已解决） |
| 来源 RFC | RFC-03-014（Phase 3 持久化扩展，V0.3） |
| 关联 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-011（Phase 2 质量与审计治理）、RFC-03-013（Phase 1E 情绪最小切片） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约基线）、SPEC-03-008（Phase 1B-A 查询平面）、SPEC-03-013（Phase 1E 情绪最小切片） |
| 关联 Design | DESIGN-03-014（Phase 3 持久化扩展详细设计，V0.6） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 版本号 | V0.4 |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer, YQuant-Principal（T4 阶段） |

### 版本历史

|| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|---|
|| V0.1 | 2026-07-20 | 初始创建。将 RFC-03-014 的 Phase 3 三阶段受控分期需求落为可执行契约，定义 SectorSnapshot / CapitalFlowRecord / MarketSentimentSnapshot 三个 domain object 字段级 schema、Provider 注册点、ETLV 验证点、读写路径边界与验收标准。 | YQuant-Principal |
||| V0.2 | 2026-07-20 | 修正：字段计数对齐（SectorSnapshot=19, CapitalFlowRecord=17, MarketSentimentSnapshot=22）；SectorSnapshot dataclass Python 语法修复（snapshot_date 移至 market 前）；唯一键全部纳入 market；拆分明细 query 与 ETLV refresh 写入路径；标记硬编码值（超时/限速）为可配置/待验证；AuditLogger 声明默认关闭；记录级可追溯字段表（quality_flags/source_record_id/schema_version 标为待定）；northbound_daily 明确为个股级 scope。 | YQuant-Principal |\n||| V0.3 | 2026-07-22 | T4 生产就绪扩展。新增 §14 只读预检与真实 Provider Smoke 测试契约（含副作用矩阵、MongoDB 预检规程、Secret Source 审计规程、Smoke 报告 YAML 模板、Zero-Persistence-Write 保证、DDL/DML 独立 Gate 细则、停止条件、成功标准）；新增 §10.bis PR 系列 Gate；§2 追加 T4 In/Out；§7 追加 A-016~A-025 T4 验收项；§9 追加 T4 约束；§11 追加 OQ-7/8/9。 | YQuant-Principal |
||| V0.4 | 2026-07-22 | AKShare 无 Token + 复用 Phase 2 MONGO_URI 同步：AKShare 为匿名数据源，PR-0 跳过密钥审计；MongoDB 连接键从 `MONGODB_URI` 改为 `MONGO_URI`（沿用 Phase 2 已验证只读连接语义）；PR-2/PR-3/PR-4 移除 token 语义改为每小时配额；§14.1 副作用矩阵移除 token 消耗；§14.3 审计表移除 AKSHARE_TOKEN；§11 OQ-8 标记已解决。 | YQuant-Principal |

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
- **T4 生产就绪**：Phase 3 离线实现（T1 RFC+SPEC + T2 Design + T3 Implement）完成后，在真实生产环境上执行零写入只读预检与真实 Provider Smoke 的阶段。仅包含 MongoDB 只读连通预检、Secret Source 审计、真实 Provider Smoke（单标的、≤3 日窗口、零持久化写）。**不包含**任何 MongoDB DDL/DML、Cache/业务写入、cron/systemd、外部消息/webhook、`.env` 写入或回显。
- **PR-Gate**：Production Readiness Gate 的缩写，T4 生产就绪阶段的授权关卡。包括 PR-0（MongoDB 连接秘密审计，使用 Phase 2 已验证的 `MONGO_URI`；AKShare 跳过密钥审计）、PR-1（MongoDB 只读预检）、PR-2/3/4（Provider smoke，AKShare 为匿名调用不依赖 PR-0）、PR-DDL-*（DDL 授权）、PR-CANARY-*（手动 canary）。
- **Smoke 报告**：每个真实 Provider smoke 调用产出的结构化 YAML 报告，包含连通性、认证、权限、字段映射、数据样例、vs_fixture 偏差等独立节（§14.4.2）。
- **Zero-Persistence-Write**：DataRouter.query() 对 P3 capability 的全程只读保证——Step 4 外部 Provider fetch 成功后仅返回 DataResult，不触发 `_materialize()`、不写物化集合、不写 Cache、不写 AuditLogger（§14.5）。
- **FV（待验证事实）**：RFC §5.5 定义的生产环境待验证事项，T4 阶段通过真实 Provider smoke 逐一验证。

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
- [ ] **T4 新增**: Secret source 审计（PR-0）：逐候选文件验证存在性 + 可加载性
- [ ] **T4 新增**: MongoDB 只读预检（PR-1）：ping + listCollections + 确认无意外 P3 集合
- [ ] **T4 新增**: Provider smoke sector（PR-2）：单板块代码 ≤3 交易日，只读调用
- [ ] **T4 新增**: Provider smoke flow（PR-3）：单标的 ≤3 交易日，只读调用
- [ ] **T4 新增**: Provider smoke sentiment（PR-4）：单日期，只读调用
- [ ] **T4 新增**: Smoke 报告生成：每 capability 独立 YAML 报告（§14.4.2 模板）

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
- ❌ **T4 禁止**: 任何 MongoDB DDL/DML/索引变更
- ❌ **T4 禁止**: DataRouter.query() 或 force_refresh 路径中的 Cache/物化写入
- ❌ **T4 禁止**: cron/systemd 注册或 canary 持续调度
- ❌ **T4 禁止**: 外部消息/webhook 发送
- ❌ **T4 禁止**: `.env` 写入或 secret 回显
- ❌ **T4 禁止**: 依赖升级（pip install、requirements 变更）
- ❌ **T4 禁止**: Git commit 或分支操作
- ❌ **T4 禁止**: 将单标的 smoke 结论泛化为全量标的工作结论

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
|| A-015 | 文档中明确声明所有数据为「辅助研究数据，不构成交易指令或投资建议」 | `grep -c '辅助研究数据，不构成交易指令或投资建议'` 在 SPEC 三份 domain object docstring 中至少出现 3 次 | 全部 |
|| **A-016** | **PR-0 Secret source 审计**：逐候选文件验证存在性 + 可加载性；结果表包括文件路径存在、可读、键声明存在三条独立记录 | 审计报告输出（不包含 secret 值/长度/URI/用户名） | T4 P3-A/B/C |
|| **A-017** | **PR-1 MongoDB 只读预检**：连接 ping 成功 + `list_collection_names()` 列出所有集合 + 确认三个 P3 目标集合不存在 | 终端命令输出（不含密码） | T4 P3-A/B/C |
|| **A-018** | **PR-2 smoke sector**：单板块代码 ≤3 交易日，零持久化写，产出 YAML 报告包含 connectivity/auth/permissions/field_mapping/data_sample/vs_fixture | 检查报告文件存在且包含全部六节 | T4 P3-A |
|| **A-019** | **PR-3 smoke flow**：单标的 ≤3 交易日，零持久化写，产出 YAML 报告同上 | 同上 | T4 P3-B |
|| **A-020** | **PR-4 smoke sentiment**：单日期，零持久化写，产出 YAML 报告同上 | 同上 | T4 P3-C |
|| **A-021** | **T4 零持久化写验证**：DataRouter.query() 对 P3 capability 的 source_trace 不包含 `materialized`/`cache` 条目；force_refresh 也不产生产生持久化副作用 | Python spy/mock 验证 | T4 P3-A/B/C |
|| **A-022** | **连通性/认证/权限/数据合理性四条独立记录**：每条 smoke 报告的 connectivity/auth/permissions 节必须独立、不可互相推导 | 检查 YAML 报告结构 | T4 P3-A/B/C |
|| **A-023** | **Secret source 非泄露三布尔检查**：审计输出仅包含存在/不存在/可加载/不可加载/键声明/缺失的布尔结论，不含值/长度/URI/用户名 | 终端输出审计 | T4 P3-A/B/C |
|| **A-024** | **失败后不自动重试、不切换写入**：smoke 失败仅记录报告，不写入物化/Cache，不自动重试，不自动回退 | 检查 smoke 报告输出 + 无 MongoDB 变更 | T4 P3-A/B/C |
|| **A-025** | **DDL/DML/真实 refresh 仍阻塞**：T4 阶段不执行 `createCollection`、`createIndex`、`upsert()`、`refresh_xxx()` | 终端检查 MongoDB 集合清单 + 无新写入 | T4 P3-A/B/C |

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

### 9.4 T4 生产就绪约束

- **T4 零写入硬边界**：PR-0~PR-4 的所有步骤设计为「零持久化副作用」——无集合/索引变更、无 MongoDB 写入、无 Cache 写入、无 cron/systemd 注册。任何步骤观察到异常停止条件时立即终止序列，**不降级为写入操作**
- **PR-1 不读业务数据**：MongoDB 只读预检仅执行 `admin.command("ping")` + `list_collection_names()`，不得对 `stock_basic_info`、`market_quotes` 等 TA-CN 业务集合做任何查询
- **PR-2/3/4 单标的有界调用**：每个 smoke 调用仅使用单板块代码/单标的/单日期，日期窗口 ≤3 个交易日，每 capability API 调用 ≤3 次，不自动重试
- **PR-0 禁止 secret 输出**：secret source 审计仅输出存在/不存在/可加载/不可加载的布尔结论，**绝对禁止**输出值、长度、URI（含 `mongodb://...`、`https://...`）、用户名、全路径+键值组合
- **连通性/认证/权限/数据合理性四条必须独立记录**：不得用连通性结论推导认证结论，不得用一次调用结果泛化为全局结论
- **T4 不依赖 mock/offline 结论**：不允许将 mock/offline 结果表述为生产验证；所有烟雾测试必须在真实环境执行
- **T4 不替换 T3 离线测试**：T4 阶段不替代 §8 定义的离线单元测试和 fixture 验证；两者为互补关系
- **PR-DDL 系列仍阻塞**：T4 阶段完成的 smoke 报告作为 Pascal 审阅输入，DDL/DML/真实 refresh 仍需 Pascal 逐项独立授权

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

## 10.bis T4 生产就绪授权 Gate（PR 系列）

**前置说明**：§10 的 G-* 系列 Gate 为 T3 离线实施阶段的授权关卡。以下 PR-* 系列 Gate 为 **T4 生产就绪阶段**的授权关卡，在 T3 离线实现完成后执行。两系列 Gate 对应不同阶段，互不冲突、互不替换。

| Gate ID | 授权内容 | 触发时机 | 影响范围 | 停止条件 | 涉及子阶段 | 执行人 |
|---|---|---|---|---|---|---|
| **PR-0** | **Secret source 审计**（仅 MongoDB）：逐候选文件证明 `MONGO_URI`（沿用 Phase 2 已验证的最小权限只读连接语义）的 `.env` 或等效 secret 源存在、可被进程加载、键声明匹配。**AKShare 跳过密钥审计**——AKShare 为匿名无 token 数据源。**禁止输出值、长度、URI、用户名或全路径+键值组合** | T4 起始 | 文件存在性检查、运行时 env 探测（只读） | 候选文件不存在或 `MONGO_URI` 键缺失 → 标记 MongoDB 为「NOT_AUTHORIZED」；AKShare 跳过 PR-0 检查 | P3-A/B/C | Pascal 或 DevOps |
| **PR-1** | **MongoDB 只读连通预检**：使用 `pymongo.MongoClient` 连接 `tradingagents` 库，ping，列出所有集合，验证无三个 P3 目标集合。**不建集合、不读业务数据** | PR-0 pass | 网络 io（<1s）、MongoDB driver 加载 | 连接失败/认证拒绝/意外发现目标集合已存在 → 停止并记录 | P3-A/B/C | Dev/Agent |
| **PR-2** | **AKShare Provider smoke：`sector.snapshot` + `sector.ranking`** — 单板块代码（`BK0489`），≤3 个交易日窗口，AKShare 匿名只读调用。**零持久化写** | PR-1 pass（AKShare smoke 不依赖 PR-0 pass） | AKShare API 调用 1-2 次、每小时配额 | API 返回错误/字段完全不匹配/json 解析异常 → 停止；差异仅记录在字段映射报告中 | P3-A | Dev/Agent |
| **PR-3** | **AKShare Provider smoke：`flow.capital_flow_daily` + `flow.northbound_daily`** — 单标的（`600519` / `000001`），≤3 个交易日窗口，AKShare 匿名只读调用 | PR-1 pass（AKShare smoke 不依赖 PR-0 pass；可并行于 PR-2） | AKShare API 调用 2-4 次、每小时配额 | API 失败/空返回/北向字段缺失 → 停止并记录 | P3-B | Dev/Agent |
| **PR-4** | **AKShare Provider smoke：`sentiment.market_snapshot` + `sentiment.limit_up_pool`** — 单日期，AKShare 匿名只读调用 | PR-1 pass（AKShare smoke 不依赖 PR-0 pass；可并行于 PR-2/PR-3） | AKShare API 调用 2 次、每小时配额 | API 失败/核心字段缺失 → 停止并记录 | P3-C | Dev/Agent |
| **PR-DDL-P3A** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_market_sector_snapshot` + 索引** | PR-2 pass + Pascal 独立确认 | MongoDB 元数据写入——集合创建、索引构建 | 写权限不足/长时间索引重建 → 停止；schema 版本须与 SPEC §3.1 一致 | P3-A | Pascal 手动确认 |
| **PR-DDL-P3B** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_stock_capital_flow` + 索引** | PR-3 pass + Pascal 独立确认 | MongoDB 元数据写入 | 同上 | P3-B | Pascal 手动确认 |
| **PR-DDL-P3C** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_market_sentiment_snapshot` + 索引** | PR-4 pass + Pascal 独立确认 | MongoDB 元数据写入 | 同上 | P3-C | Pascal 手动确认 |
| **PR-CANARY-P3x** | **手动 Canary**：一次 refresh 调用（手动触发，非 cron），写入对应集合，验证 DataResult 返回正常 | 对应 PR-DDL pass + Pascal 确认 | 真实 MongoDB 写入 | 写入失败/数据质量异常 → 停止不升级到 cron | P3-A/B/C | Pascal 手动执行 |

**关键约束**：
- PR-1（MongoDB 预检）**不读业务数据**——仅 ping + listCollections 命令。不得对 `stock_basic_info`、`market_quotes` 等 TA-CN 集合做查询
- PR-2/PR-3/PR-4 的输出必须**分别记录**连通性、认证、权限、字段映射四方面的观测结论。不得将一次调用结果泛化为全局结论
- PR-DDL 系列与 PR-smoke 系列**完全解耦**——DDL 不是 PR-smoke 的前置要求，smoke 可先行验证 Provider 连通性，DDL 在 Pascal 确认 schema 最终版后才执行
- PR-CANARY 系列与 PR-DDL 系列有依赖——先 DDL 才能写。但每个子阶段独立，P3-A 的 canary 不等待 P3-B 的 DDL
- 同一子阶段的 Gate 建议按 **PR-smoke → Pascal 审阅 smoke 结论 → PR-DDL → PR-CANARY** 顺序执行
- **长期调度（cron/systemd）和 task_center Job 创建仍为独立授权，不在本 T4 范围**

## 11. 开放问题

- [ ] OQ-1：资金流数据是否需要分钟级盘中快照？当前仅日级。如需要，P3-B 的 collection schema 需增加 `snapshot_time` 维度。
- [ ] OQ-2：`market_temperature` 合成公式？当前未定义，留作 Domain Service 内部实现或 T2 Design 裁定。
- [ ] OQ-3：`SectorSnapshot.members` 字段是否必要？如需要，更新频率为每日/每周？
- [ ] OQ-4：3 个子阶段的执行顺序是否接受推荐序（P3-A → P3-B → P3-C）？
- [ ] OQ-5：`03_data_ud_stock_capital_flow` 的倒填（backfill）策略？是否需要回填历史 N 个月数据？若需要，batch size 和限流策略。
- [ ] **OQ-7（T4 新增）**：T4 生产就绪 PR-smoke 的执行人是否由当前 Agent 承担，还是需 Pascal 手动执行？PR-2/PR-3/PR-4 标注为「Dev/Agent」，若 Agent 无真实网络/API 权限则降级为 Pascal 手动
- [ ] **OQ-8（T4 更新）**：AKShare 无需 token（已确认为匿名数据源），OQ-8 已解决。PR-0 审计仅覆盖 MongoDB 的 `MONGO_URI`。
- [ ] **OQ-9（T4 新增）**：Provider smoke 结论中字段映射差异的阈值如何设定？RFC §6.3 提议 >50% 字段不匹配为停止条件——是否调整？

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

---

## 14. T4 生产就绪只读预检与 Provider Smoke 测试契约

### 14.1 副作用矩阵（Mongo/read、Provider/read、token use）

每个 T4 步骤的可能副作用、风险等级与缓解措施：

| 步骤 | 动作 | 可能副作用 | 风险等级 | 缓解措施 |
|---|---|---|---|---|
| PR-0: Secret source 审计 | 检查文件是否存在；`os.environ.get("KEY")` | 无（仅只读探测） | 无风险 | 禁止输出值/长度/URI/用户名；仅记录「存在/不存在」「可加载/不可加载」 |
| PR-1: MongoDB 只读预检 | `MongoClient()` → `admin.command("ping")` → `list_collection_names()` | MongoDB 连接池建立；网络出站流量（~KB） | 低 | 不读业务数据；不建集合；连接超时 <3s |
| PR-2: sector smoke | `akshare.stock_board_industry_cons_em("BK0489")` | AKShare 匿名 API 调用（1 次/调用）；网络流量（~KB） | 低 | 单代码限量；≤3 日窗口；零持久化写 |
| PR-3: flow smoke | `akshare.stock_individual_fund_flow()` | AKShare 匿名 API 调用（2-4 次）；网络流量（~MB） | 低-中（带宽） | 单标的限量；≤3 日窗口；限速 ≥1s/call |
| PR-4: sentiment smoke | `akshare.stock_zt_pool_em()` / `stock_market_fund_flow()` | AKShare 匿名 API 调用（2 次）；网络流量（~KB） | 低 | 单日期限量 |
| PR-DDL: 集合创建 | `db.create_collection()` + `create_indexes()` | MongoDB 元数据变更——不可逆（drop 可撤销但有代价） | **中**（元数据变更） | Pascal 独立确认；schema 版本与 SPEC 最终版一致；提供 `drop_collection()` 回滚脚本 |
| PR-CANARY: 手动写入 | `P3PersistenceWriter.upsert()` → 真实 MongoDB 写入 | 数据写入——可逆（delete_by_filter 可清理） | 中（数据写入） | 手动触发；单次执行；提供清理脚本；不自动重复 |

**核心原则**：PR-0 到 PR-4 的所有步骤设计为「零持久化副作用」——无集合/索引变更、无 MongoDB 写入、无 Cache 写入、无 AuditLogger 写入、无 QualitySummary 写入、无 cron/systemd 注册。任何步骤观察到异常停止条件时立即终止序列，**不降级为写入操作**。

### 14.2 MongoDB 只读预检规程

**适用 Gate**：PR-1

**步骤**：
1. 从受控 secret source（PR-0 已验证）加载 MongoDB 连接参数
2. 建立 `pymongo.MongoClient`（超时 3s）
3. 执行 `admin.command("ping")` → 记录连通性结论
4. 切换到 `tradingagents` 库 → 执行 `list_collection_names()` → 记录全量集合清单（不包含业务数据内容）
5. 逐一检查集合名中是否包含 `03_data_ud_market_sector_snapshot` / `03_data_ud_stock_capital_flow` / `03_data_ud_market_sentiment_snapshot`
6. **如果任一目标集合存在** → 停止 PR-1，记录该集合的创建元数据（`db[collection].options()`），标注为「UNEXPECTED_EXISTENCE」，需 Pascal 判断处理
7. **如果所有目标集合不存在** → PR-1 通过

**禁止事项**：
- ❌ 查询 `stock_basic_info`、`market_quotes`、`stock_daily_quotes` 等 TA-CN 业务集合的数据
- ❌ 创建或修改任何集合、索引、文档
- ❌ 读代替写（不将此行作为开始写入的借口）
- ❌ 在任意环节打印或记录连接串中的密码

**失败处理**：
- 连接失败 → 记录错误类型（DNS 解析/网络超时/认证拒绝），PR-1 失败。不自动重试
- 认证拒绝 → 区分「用户无权限」和「凭据错误」两种场景，分别记录在结论中
- list_collections 无权限 → 降低期望：仅验证可连接即可，集合检查改为「无法执行，需 Pascal 手动确认」

### 14.3 Secret Source 审计规程

**适用 Gate**：PR-0

**候选 Secret Source**（逐项检查，非穷举、不输出值）：

| 候选路径 | 检查内容 | 验证方法 | 结论 |
|---|---|---|---|---|
| `.env`（项目根目录） | 文件存在、可读 | `os.path.isfile() 且 os.access(R_OK)` | 存在/不存在/不可读 |
| `.env` 键 `MONGO_URI` | 声明存在 | `os.getenv("MONGO_URI")` 返回非 None | 已声明/未声明 |
| Hermes profile `.env` | 文件存在、可读 | `os.path.isfile(profile_path) 且 os.access(R_OK)` | 存在/不存在/不可读 |
| Hermes 运行时 env | 键声明 | `os.getenv(key)` 返回非 None | 已声明/未声明 |
| AKShare 匿名调用 | 无需密钥审计 | —（AKShare 为匿名数据源，无需 token） | 跳过 PR-0 |

**约束**：
- 每条检查仅输出结论（存在/不存在/可加载/不可加载 + 键声明存在/缺失）
- **绝对禁止**：输出值、长度、URI（含 `mongodb://...`、`https://...`）、用户名、全路径+键值组合
- 每个候选 source 独立记录，不归并、不默认降级
- MongoDB `MONGO_URI` 候选 source 全部不存在或键缺失 → 标记 MongoDB 为「NOT_AUTHORIZED」，PR-1（MongoDB 预检）不执行
- AKShare 跳过 PR-0 检查——PR-2/PR-3/PR-4 可独立于 PR-0 直接执行匿名只读 smoke
- PR-0 审计结果由 Pascal 审阅确认后进入 PR-1

### 14.4 真实 Provider Smoke 规程

#### 14.4.1 通用规则

| 维度 | 约束 |
|---|---|
| 范围 | 子阶段对应的 capability 各选一（共 6 个 capability） |
| 标的选择 | sector: 单板块代码（推荐 `BK0489`「行业板块」）；flow: 单标的（推荐 `600519` 沪市 + `000001` 深市）；sentiment: 单日期 |
| 日期窗口 | ≤3 个交易日（推荐最近一个完整交易日 + 前两个交易日） |
| 写入 | **零写入**：不写物化集合、不写 Cache、不写 AuditLogger、不写 QualitySummary。仅打印/记录到本地文件 |
| API 调用次数 | 每 capability ≤3 次（单标的 × 单日期 × 重试 0 次）。仅成功调用 1 次 + 异常不自动重试 |
| 输出 | 每个 smoke 调用输出一个「capability smoke 报告」（见 §14.4.2） |
| 并行 | PR-2/PR-3/PR-4 相互独立，可并行执行 |

#### 14.4.2 Smoke 报告 YAML 模板

每 capability 的 smoke 结果必须独立记录为结构化报告：

```yaml
capability: sector.snapshot              # capability 名称
provider: akshare                        # Provider 名
smoke_at: 2026-07-22T03:30:00+08:00      # 实际执行时间（ISO 8601）
stock/代码: BK0489                        # 测试标的
date_range: [2026-07-20, 2026-07-22]     # 请求日期窗口
---
connectivity:
  status: success | failed               # API 连通性结论
  latency_ms: 1234                        # 响应延迟（ms）
  error: null | str                      # 失败时的错误信息
auth:
  status: authorized | unauthorized      # 认证状态
  error: null | str
permissions:
  status: ok | restricted               # 权限状态（是否返回预期数据）
  note: null | str
field_mapping:
  total_expected_fields: 19              # SPEC 定义的字段数
  matched_fields: 18                     # 实际接口返回的匹配字段数
  missing_fields: [field_a, field_b]     # SPEC 有但实际无的字段
  extra_fields: [field_x]                # 实际有但 SPEC 无的字段
  unmatched_types: [field_c → str vs int] # 类型不匹配的字段
data_sample:
  row_count: 15                          # 返回记录数
  sample_rows: 5                         # 前 5 行样例打印
  null_ratio: 0.03                       # 空值占比
vs_fixture:
  deviations:                            # 与离线 fixture 的偏差
    - field: update_date
      fixture_type: str
      actual_type: datetime
      impact: low                        # 偏差影响评估（low/medium/high）
overall:
  verdict: pass | conditional_pass | fail  # 总体评估
  memo: |                               # 自由文本备注
    Sector snapshot data returned successfully.
    Field mapping is 95% compatible with SPEC.
    Remapping needed for: update_date (type change).
```

#### 14.4.3 报告存储

- 所有 smoke 报告写入本地文件（`docs/rfc/03_data/smoke_reports/` 目录），按 capability 命名：`smoke_sector_snapshot_20260722.yaml`
- **不允许写入 MongoDB 或任何持久化存储**
- 报告最终作为附件提供给 Pascal 审阅

#### 14.4.4 失败与偏差处理

| 场景 | 处理 |
|---|---|
| API 返回非 200 或空 DataFrame | 记录错误 → 该 capability 标记为 fail → 停止该子阶段的后续 smoke |
| 认证拒绝（401/403） | 记录错误 → 标记 auth 为 unauthorized → 停止全部 smoke，回查 PR-0 |
| 字段映射完全匹配（≥90% 字段名+类型匹配） | pass → 可直接进入 DDL Gate |
| 字段映射部分匹配（70%-90%） | conditional_pass → 需 Pascal 审阅偏差后决定是否授权 DDL |
| 字段映射匹配度低（<70%） | fail → 停止 → 需更新 domain object schema 后重做 smoke |
| 限流（429） | 记录限流信息 → 标记为 rate_limited → 等待 ≥60s → **不自动重试**（留给 Pascal 判断） |
| 网络超时 | 记录超时 → 标记为 timeout → 不自动重试 |

### 14.5 Zero-Persistence-Write 保证

**DataRouter.query() for P3 capabilities** 全程零持久化写：

- Step 1（TA-CN adapter skip）：P3 capability 注册在 `_TA_CN_NOT_COVERED` → 直接跳过，零副作用
- Step 2（P3PersistenceWriter 读）：仅 `get()` 操作——零写
- Step 3（CacheManager 读）：仅 `get()` 操作——零写
- Step 4（外部 Provider fetch）：成功返回 `DataResult.success()`——**不触发 `_materialize()`**，不写 LocalMongoAdapter、不写 Cache、不写 AuditLogger

任何 `force_refresh` 参数在 P3 query 路径中均**不产生持久化副作用**——`force_refresh` 仅影响 FreshnessPolicy 判断，不改变写入行为。

**显式 refresh 路径**（非 query，属独立 Gate）：
- `refresh_sector_snapshot()` / `refresh_capital_flow()` / `refresh_market_sentiment()` 仅在对应子阶段的 CANARY Gate 授权后执行
- CANARY 之前的任何 refresh 路径调用返回未授权错误，不执行 Provider fetch 和 MongoDB 写入

**验证方式**（A-021）：
- 通过 spy/source trace 验证：`DataResult.source_trace` 中不包含 `"ud_materialized"` 或 `"cache"` 条目
- 通过 mock Router 验证：`_materialize()` 方法在 P3 capability 的 query 路径中不被调用

### 14.6 DDL/DML 独立 Gate 细则

PR-DDL-* 系列 Gate 与 PR-smoke 系列 Gate 的关系：

```
PR-0 (Secret 审计) ──→ PR-1 (MongoDB 预检) ──→ PR-2/3/4 (Smoke)
                                                      │
                                                      ▼
                                              Pascal 审阅 Smoke 报告
                                                      │
                                              §14.4.4 判定 Verdict
                                                      │
                                           ┌──────────┴──────────┐
                                           ▼                     ▼
                                     PASS / CONDITIONAL    FAIL → 停止
                                           │
                                           ▼
                          Pascal 独立确认 schema 最终版
                                           │
                                           ▼
                                     PR-DDL-* (集合创建)
                                           │
                                           ▼
                                     PR-CANARY-* (手动写入)
```

**DDL Gate 授权要求**（全部满足）：
1. 该子阶段的 PR-smoke verdict 为 `pass` 或 `conditional_pass`（Pascal 已审阅偏差并确认可接受）
2. Pascal 已确认 SPEC-03-014 中对应 schema 的最终版本（包含 smoke 发现的字段映射修正）
3. 提供 `createCollection` + `createIndex` 的精确脚本（索引定义、TTL 策略、验证规则）
4. 提供对应的 `dropCollection` 回滚脚本（作为安全网）
5. Pascal 执行或明确授权执行 DDL
6. **DDL 执行人**：Pascal 手动执行（或 Pascal 授权的 DevOps）。Agent 不直接执行 DDL

**DDL 执行脚本示例**（以 P3-A 为例）：
```javascript
// P3-A: 创建板块快照集合
db.createCollection("03_data_ud_market_sector_snapshot");

// 创建索引（在创建集合后执行）
db["03_data_ud_market_sector_snapshot"].createIndex(
    {sector_code: 1, snapshot_date: -1},
    {background: true, name: "sector_code_date"}
);
db["03_data_ud_market_sector_snapshot"].createIndex(
    {snapshot_date: -1},
    {background: true, name: "snapshot_date"}
);
db["03_data_ud_market_sector_snapshot"].createIndex(
    {sector_type: 1, snapshot_date: -1},
    {background: true, name: "sector_type_date"}
);
```

### 14.7 成功标准

T4 生产就绪阶段在以下全部条件满足时视为完成：

1. **PR-0 通过**：Secret source 逐候选文件审计完成，状态为「AUTHORIZED」
2. **PR-1 通过**：MongoDB 可连接、认证正常、目标集合不存在（或 Pascal 已确认意外存在的集合可接受）
3. **PR-2/PR-3/PR-4 至少通过一个子阶段**：对应的 Provider smoke 报告生成，verdict 为 pass 或 conditional_pass
4. **字段映射差异表**：每个 capability 的字段映射对照表已生成，未映射字段已标注
5. **Pascal 审阅完成**：Pascal 审阅所有 smoke 报告并确认是否可进入 DDL Gate
6. **DDL 提案**：针对通过 smoke 的子阶段，DDL Gate 提案已提交（含精确的集合创建脚本和索引定义）
7. **无未解决的阻断**：§14.8 停止条件表中无未关闭的事项

T4 阶段**不要求**所有三个子阶段同时通过 smoke——单子阶段通过的组合是合法的完成状态（如「P3-A 生产就绪 but P3-B/C 待后续」），取决于 Pascal 的判断。

### 14.8 停止条件

| 触发条件 | 对应 Gate | 后续动作 |
|---|---|---|
| Secret source 候选文件不存在 | PR-0 | 标记对应 Provider 为「NOT_AUTHORIZED」，不执行该 Provider 的 smoke |
| MongoDB 连接失败或认证拒绝 | PR-1 | 不执行 PR-2/PR-3/PR-4（全部需 MongoDB 连通） |
| 集合 `03_data_ud_*` 已意外存在 | PR-1 | 停止——记录集合存在情况，需 Pascal 判断是遗留还是意外 |
| AKShare API 返回错误（非 200 / 空 DataFrame / 解析异常） | PR-2/PR-3/PR-4 | 停止对应 Provider 的后续 smoke |
| 字段映射差异过大（>50% 字段名不匹配） | PR-2/PR-3/PR-4 | 停止——需重新调整 domain object schema 后重试 |
| DDL 写入无权限 | PR-DDL | 停止——需 Pascal 手动授予写权限或换连接串 |
| Canary 写入失败或数据质量异常 | PR-CANARY | 停止——不升级到定时采集 |

**禁止绕过**：
- 不允许在 PR-1（MongoDB 预检）成功前执行 Provider smoke（如果 Provider smoke 需要 MongoDB 连接）。但如果 smoke 设计为纯内存验证（仅打印结果），可与 PR-1 并行——由执行人自主判断风险
- 不允许在 PR-0（Secret source 审计）通过前执行真实 API 调用
- 不允许跳过 PR-smoke 直接发起 PR-DDL
- 不允许将 PR-smoke 的连通性结论泛化为「全量标的工作正常」——仅单标的+有限日期结论
- 不允许将 mock/offline 结果表述为生产验证
- 不允许在 PR 阶段执行 `refresh_xxx()` 或 `CacheManager.put()` 或 `P3PersistenceWriter.upsert()`
- **不允许输出 secret 值、长度、URI、用户名或全路径+键值组合**
- 不允许自动重试失败的 smoke——仅记录结论
- 不允许绕过停止条件：任何停止条件触发必须停止，不得在失败后降级为写入操作
