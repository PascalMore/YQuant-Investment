# SPEC-03-014：Unified Data Phase 3 — 重要持久化扩展契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-20 |
|| 最后更新 | 2026-07-31（V0.19 SPEC P1 受控 Mongo 物化与显式 refresh 的零副作用契约冻结：新增 §P1 完整章节——P1 覆盖 capability 与集合文档语义、MongoDB-first 离线实现边界、internal-first read/explicit refresh/cache write 边界与默认禁止规则、完全副作用矩阵、授权关口、零 I/O 边界与验收准则。不动所有已有 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态。与 RFC-03-014 V0.19 一致。） |
|| 版本号 | V0.19 |
| 来源 RFC | RFC-03-014（Phase 3 持久化扩展，V0.19） |
| 关联 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-011（Phase 2 质量与审计治理）、RFC-03-013（Phase 1E 情绪最小切片） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约基线）、SPEC-03-008（Phase 1B-A 查询平面）、SPEC-03-013（Phase 1E 情绪最小切片） |
| 关联 Design | DESIGN-03-014（Phase 3 持久化扩展详细设计，V0.21） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer, YQuant-Principal（T4 阶段） |

### 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|---|
| V0.1 | 2026-07-20 | 初始创建。将 RFC-03-014 的 Phase 3 三阶段受控分期需求落为可执行契约，定义 SectorSnapshot / CapitalFlowRecord / MarketSentimentSnapshot 三个 domain object 字段级 schema、Provider 注册点、ETLV 验证点、读写路径边界与验收标准。 | YQuant-Principal |
| V0.2 | 2026-07-20 | 修正：字段计数对齐（SectorSnapshot=19, CapitalFlowRecord=17, MarketSentimentSnapshot=22）；SectorSnapshot dataclass Python 语法修复（snapshot_date 移至 market 前）；唯一键全部纳入 market；拆分明细 query 与 ETLV refresh 写入路径；标记硬编码值（超时/限速）为可配置/待验证；AuditLogger 声明默认关闭；记录级可追溯字段表（quality_flags/source_record_id/schema_version 标为待定）；northbound_daily 明确为个股级 scope。 | YQuant-Principal |
| V0.3 | 2026-07-22 | T4 生产就绪扩展。新增 §14 只读预检与真实 Provider Smoke 测试契约（含副作用矩阵、MongoDB 预检规程、Secret Source 审计规程、Smoke 报告 YAML 模板、Zero-Persistence-Write 保证、DDL/DML 独立 Gate 细则、停止条件、成功标准）；新增 §10.bis PR 系列 Gate；§2 追加 T4 In/Out；§7 追加 A-016~A-025 T4 验收项；§9 追加 T4 约束；§11 追加 OQ-7/8/9。 | YQuant-Principal |
| V0.4 | 2026-07-22 | 历史更新——**已被 V0.5 替换**。AKShare 无 Token + 复用 Phase 2 MONGO_URI 同步：AKShare 为匿名数据源，PR-0 跳过密钥审计；MongoDB 连接键从 `MONGODB_URI` 改为 `MONGO_URI`（沿用 Phase 2 已验证只读连接语义）；PR-2/PR-3/PR-4 移除 token 语义改为每小时配额；§14.1 副作用矩阵移除 token 消耗；§14.3 审计表移除 AKSHARE_TOKEN；§11 OQ-8 标记已解决。V0.5 将此 MONGO_URI 单键来源迁移至 skills/.env 五组件键（MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE），V0.4 的 MONGO_URI 语义视为 superseded。 | YQuant-Principal |
| V0.5 | 2026-07-24 | PR-1 凭证来源契约对齐：MongoDB 连接凭据来源从 MONGO_URI + Hermes profile `.env` 改为复用 Phase 2 skills/.env 五组件键（MONGODB_HOST、MONGODB_PORT、MONGODB_USERNAME、MONGODB_PASSWORD、MONGODB_DATABASE），沿用 PortfolioMongoLoader Phase-2 Mongo 认证语义（组件式构造连接，非 URI）；PR-0 审计表对应更新；移除 Hermes profile `.env` 候选路径；历史 MONGO_URI 描述均标为 superseded。 | YQuant-Principal |
| V0.6 | 2026-07-25 | B1-P3A DDL 契约冻结。新增 §14.6.4（PR-DDL-P3A 精确契约：前置条件/集合/索引/写入身份/原子性/rollback 路径/audit 工件/退出码/停止条件/执行人/不授权范围），权威定义引用 DESIGN-03-014 §6.4 V0.13；§10 G-A-1 行停止条件列追加 §14.6.4 + DESIGN §6.4 引用；§10.bis PR-DDL-P3A 行标注「仅 P3-A 已授权冻结、P3-B/P3-C 仍阻塞」并引用 §14.6.4。不动既有 §3.1/§14.4/§14.5/§14.6 通用要求/§14.7/§14.8 条文。 | YQuant-Principal |
| V0.7 | 2026-07-25 | B1-P3B DDL 契约冻结。新增 §14.6.bis（PR-DDL-P3B 精确契约：前置条件/集合/索引/写入身份/原子性/rollback 路径/audit 工件/退出码/停止条件/执行人/不授权范围），权威定义引用 DESIGN-03-014 §6.4.bis V0.14；§10 G-B-1 行停止条件列追加 §14.6.bis + DESIGN §6.4.bis 引用；§10.bis PR-DDL-P3B 行标注「P3-B 已授权冻结、P3-C 仍阻塞」并引用 §14.6.bis。退出码语义按 task 授权：0=PASS / 2=preflight target already exists / 3=collection create fail / 4=index create fail。不动既有 §3.2/§14.4/§14.5/§14.6 通用要求/§14.6.4/§14.7/§14.8 条文。 | YQuant-Principal |
| V0.8 | 2026-07-25 | B1-P3C DDL 契约冻结。新增 §14.6.ter（PR-DDL-P3C 精确契约：前置条件/集合/索引/写入身份/原子性/rollback 路径/audit 工件/退出码/停止条件/执行人/不授权范围），权威定义引用 DESIGN-03-014 §6.4.ter V0.15；§10 G-C-1 行停止条件列追加 §14.6.ter + DESIGN §6.4.ter 引用；§10.bis PR-DDL-P3C 行标注「P3-A + P3-B + P3-C 已全部授权冻结」并引用 §14.6.ter。退出码语义按 task 授权：0=PASS / 2=preflight target already exists / 3=collection create fail / 4=index create fail。不动既有 §3.3/§14.4/§14.5/§14.6 通用要求/§14.6.4/§14.6.bis/§14.7/§14.8 条文。 | YQuant-Principal |
| V0.9 | 2026-07-26 | B2 实测映射契约冻结。新增 §14.4.5（B2 单次只读 smoke 实测映射契约冻结）：依据 2026-07-26 B2 一次性只读 smoke 的冻结证据（真实报告只读副本位于 `/tmp/yquant-b2-pr234-20260726/`，不可移动/提交、不可重跑），冻结六项可执行契约——（1）§14.4.5.2 PR-3 `flow.northbound_daily` 经 `stock_hsgt_individual_em(symbol)` 实际返回北向**持股历史**语义（9 个持股字段），**不是**北向净流入；现有 expected 0/11，缺失 date/stock/northbound_net_inflow；禁止伪装，T2 须三选一（A 分流正确 endpoint / B 变更 capability 语义 / C Pascal 确认放弃净流入），未获选择不得自行实现。（2）§14.4.5.3 PR-4 空返回语义区分（无交易日/schema drift/调用异常），本次 row_count=0 且 actual_fields=0 判定 verdict=fail、empty_semantics=undetermined，T2 须在 reporter 定义 empty_semantics 字段，后续独立 live-read 在交易日复验；本阶段不重跑。（3）§14.4.5.4 PR-2 SSL 网络停止诊断边界（endpoint_unreachable，非代码 defect，禁止与 mapping 修复耦合，仅允许后续单变量网络诊断）。（4）§14.4.5.5 单次 live-read 精确调用预算（PR-2=2/PR-3=3/PR-4=2，本次已用尽）与零写入边界（无重试/无 fallback/零 Mongo/Cache/Audit/DDL/cron）。（5）§14.4.5.6 T2 实现最小文件范围与禁止修改清单。（6）§14.4.5.7 T2 验收准则 7 项。本节为权威可执行契约，RFC §13.4.5 引用本节，DESIGN §15.x V0.16 为工具链设计定义。不动 §3 domain object 字段定义（除非 Pascal 确认选项 B）、不动 §14.6.x DDL 冻结契约、不动既有授权范围。 | YQuant-Principal |
|| V0.10 | 2026-07-26 | **Pascal C+X2 决策同步（Recovery/T2.5）**。§14.4.5.2 PR-3 三选一由 Pascal 2026-07-26 明确选 **C**（当前 Phase 3 不提供 northbound net inflow；`northbound_net_inflow` 保持 None；持股历史不得伪装为净流入；不引入新 endpoint/capability；§3 字段定义不变）。§14.4.5.3 PR-4 空返回语义按 **X2** 收敛：移除 `empty_semantics` reporter 字段与三分类（undetermined/no_trading_data/schema_drift/call_anomaly）；空返回维持 verdict=fail（保守）；reporter 账本同步移除 `worktree_changed`（X1 候选 runtime git-worktree 探测被 X2 否决）。§14.4.5.6 T2 最小文件范围与禁止清单同步更新（移除 empty_semantics/worktree_changed）。§14.4.5.7 验收准则第 2 项移除 empty_semantics 要求。删除全部「未选择/阻塞等待 Pascal」失效文本。§14.4.5.4 PR-2 SSL 边界、§14.4.5.5 零写入边界、§3 domain object、§14.6.x DDL 冻结契约均不变。权威可执行契约，RFC §13.4.5 V0.11 引用本节，DESIGN §4.2.1/§15.14 V0.17 为工具链设计定义。 | YQuant-Principal |
|| V0.12 | 2026-07-29 | **D1/D2/D3 文档同步**。§5.5/A-021/§14.5 source_trace 约束从 blanket 子串匹配修正为精确 `(ok)` 后缀匹配——不允许 `"ud_materialized(ok)"` 或 `"cache(ok)"` 条目；允许 `"ud_materialized(skipped: ...)"`、`"cache(miss)"`。与 D1 裁定对齐，不动 §14.4.5 Pascal C+X2 决策内容、不动 §14.6.x DDL 冻结契约、不动既有授权范围。 | YQuant-Principal |
|| V0.15 | 2026-07-30 | **Pascal 22-field MarketSentimentSnapshot canonical 契约裁定同步**。Pascal 裁定 22 字段全市场多维快照（唯一键 `{market, snapshot_date, snapshot_time}`）为 `MarketSentimentSnapshot` 的 canonical 产品 schema，替代此前离线 T3-B 实现的 10 字段 `sentiment_type` 聚合模型（`{market, sentiment_type, market_date}`）。§3.3 追加 provenance 声明确认 canonical 状态；§1 需求摘要措辞从「候选」升级为「canonical」；§12 追加 developer allowlist（sentiment.py 10→22 字段迁移、fixture 更新、测试断言对齐）。Superseded 离线 10 字段实现保留在磁盘，不作删除，但任何实盘路径必须以 22 字段 canonical 契约为准。不动 §14.4.5.9-§14.4.5.11 B2/R0 裁决内容、不动 §14.6.x DDL 冻结契约、不动既有授权范围。 | YQuant-Principal |
||| V0.17 | 2026-07-30 | **P0 真实 Provider 离线可实现契约冻结**。新增 §P0 完整章节：定义六 capability 精确状态矩阵、真实 Provider 统一接口边界（extract→canonical mapping→validation/provenance→DataResult.source_trace）、P3-A/P3-B/P3-C 逐项 mapping 验收项（PA-/PB-/PC- 系列）、P0 vs P1 vs P2 边界依赖、完全副作用矩阵、旧 checkbox 状态纠正；§7 追加 A-026~A-031 P0 验收项；§2.1/§2.2 更新 P0 In/Out scope。全部真实调用声明为未来授权 smoke/production activation。不动 §14.4.5 B2/R0/Pascal C+X2 裁决、不动 §14.6.x DDL 冻结契约、不动既有授权范围。 | YQuant-Principal |
|  | V0.19 | 2026-07-31 | **P1 受控 Mongo 物化与显式 refresh 的零副作用契约冻结**。新增 §P1 完整章节：P1 覆盖 capability 与集合文档语义、MongoDB-first 离线实现边界、internal-first read/explicit refresh/cache write 边界与默认禁止规则、完全副作用矩阵、授权关口、零 I/O 边界与验收准则。与 RFC-03-014 V0.19 一致。不动 P0/P1/P2 边界定义、不动已有授权范围、不动所有 ❌ 状态。 | YQuant-Principal |

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
- **PR-Gate**：Production Readiness Gate 的缩写，T4 生产就绪阶段的授权关卡。包括 PR-0（MongoDB 连接秘密审计，复用 Phase 2 skills/.env 五组件键 `MONGODB_HOST`/`PORT`/`USERNAME`/`PASSWORD`/`DATABASE`，组件式构造连接非 URI——V0.4 的 `MONGO_URI` 单键来源已 superseded；AKShare 跳过密钥审计）、PR-1（MongoDB 只读预检）、PR-2/3/4（Provider smoke，AKShare 为匿名调用不依赖 PR-0）、PR-DDL-*（DDL 授权）、PR-CANARY-*（手动 canary）。
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
3. **MarketSentimentSnapshot domain object**（**Pascal canonical 契约**）：`models/domain/sentiment.py` 中——22 字段全市场多维快照（类型、必填性、语义严格定义）。唯一键 `{market, snapshot_date, snapshot_time}`。**此 22 字段 canonical 契约取代**此前离线 T3-B 实现的 10 字段 `sentiment_type` 聚合模型（`{market, sentiment_type, market_date}` 唯一键）。离线实现保留在磁盘，不对齐 canonical 契约的部分标记为 superseded。
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
#
# > **Pascal canonical 契约（2026-07-30）**：本 22 字段全市场多维快照（唯一键 {market, snapshot_date, snapshot_time}）
# > 为 MarketSentimentSnapshot 的产品 canonical schema。此前离线 T3-B 实现的 10 字段 sentiment_type 聚合模型
# > （{market, sentiment_type, market_date} 唯一键、frozen=True、slots=True）已被取代。当前磁盘上的 sentiment.py
# > 仍为 10 字段离线实现（保持不删），但任何后续实盘开发、持久化写入、Provider 映射必须本规范为准。

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
| `continuous_limit_up` | list of dict，每条含 `symbol`, `days`, `reason` | reason 为自由字符串 |
| `market_temperature` | 0-100 区间，可 None | 合成指标，Pascal 确认允许 None（不强制合成，禁止编造） |
| `limit_up_pool` / `limit_down_pool` | 每个列表最大 500 个代码 | 若独立提供 `sentiment.limit_up_pool` capability，此集合中的对应字段可为空 |

| `snapshot_date` | 格式 `YYYY-MM-DD` | 唯一键 `{market, snapshot_date, snapshot_time}` 的组成部分 |
| `snapshot_time` | 格式 `HH:MM:SS` 或 `close` | 唯一键组成部分。`close` 表示收盘后快照 |
| `market` | 如 `"CN"` | 唯一键组成部分 |

**MongoDB 唯一键**：`{market, snapshot_date, snapshot_time}`
**MongoDB 索引建议**：
- `{snapshot_date: -1}` — 按日查询
- `{snapshot_time: -1}` — 按时点查询

**温度合成公式待定**：`market_temperature` 为派生字段，由 `sentiment_service` 在 Provider 原始数据上合成。Pascal 确认该字段可保持为 `None`（不强制合成，禁止编造）。T2 Design 阶段需定义合成公式或确认保留为 `None` 由消费方自行计算。

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
| `03_data_ud_market_sector_snapshot` | P3-A | `{market, sector_code, snapshot_date}` | `{sector_code:1, snapshot_date:-1}`, `{snapshot_date:-1}`, `{sector_type:1, snapshot_date:-1}` | 无（物化可追溯数据） |
| `03_data_ud_stock_capital_flow` | P3-B | `{market, symbol, trade_date}` | `{symbol:1, trade_date:-1}`, `{trade_date:-1}` | 无（物化可追溯数据） |
| `03_data_ud_market_sentiment_snapshot` | P3-C | `{market, snapshot_date, snapshot_time}` | `{snapshot_date:-1}`, `{snapshot_time:-1}` | 无（物化可追溯数据） |

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

**异常边界与默认行为**：

| 方法 | 参数无效/缺失 | router 未注入 | Provider 失败 | 空返回 |
|------|-------------|-------------|-------------|--------|
| `get_sector_snapshot` | `sector_code` 为空 → 抛出 `InvalidSecurityIdError` 或等价 ValueError | —（`UnifiedDataClient` facade 保证 router 始终非空；若 SectorService.router is None → `ProviderUnavailableError("P3-A methods require DataRouter: not injected")`，DESIGN-03-014 §5.1） | → `DataResult.error(provider="error", source_trace=["akshare(error: ...)"])` | → `DataResult.success(data=None/is_empty, provider="akshare")` |
| `get_sector_ranking` | `limit` ≤ 0 → 默认 20；`sector_type` 无效值 → 作为查询参数传递，由 Provider 容纳 | 同上 | 同上 | → `DataResult.success(data=[], provider="akshare")` |

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

### 5.5 P3-A 能力级契约（`sector.snapshot` / `sector.ranking`）

| 维度 | `sector.snapshot` | `sector.ranking` |
|------|-------------------|-------------------|
| **Capability** | `"sector.snapshot"` | `"sector.ranking"` |
| **请求参数** | `security_id`（market + sector_code）、`date`（可选 str，默认最近交易日） | `date`（可选 str）、`sector_type`（可选 str，默认全部）、`limit`（可选 int，默认 20） |
| **Router.query() 签名** | `router.query("sector", "snapshot", sid, params={"date": ...})` | `router.query("sector", "ranking", params={"date": ..., "sector_type": ..., "limit": ...})` |
| **DataResult.data 类型** | `SectorSnapshot`（单条） | `list[SectorSnapshot]` |
| **空返回** | 空 → `DataResult.success(data=None, provider="akshare")`；`is_empty=True` | 空 → `DataResult.success(data=[], provider="akshare")`；`is_empty=True` |
| **错误返回** | fetch 失败 → `DataResult.error(provider="error", source_trace=["akshare(error: ...)"])` | 同上 |
| **freshness** | query Step 4 → `"delayed"`；物化命中 → `"cached"` | 同上 |
| **source_trace** | 不含 `"ud_materialized(ok)"`、`"cache(ok)"`；允许 `ud_materialized(skipped: ...)`、`cache(miss)`（A-021） | 同上 |
| **TA-CN 覆盖** | ❌ 注册于 `_TA_CN_NOT_COVERED` | ❌ 注册于 `_TA_CN_NOT_COVERED` |
| **external_fallback_chain** | `["akshare"]` | `["akshare"]` |

**唯一键**：`{market, sector_code, snapshot_date}`（§4.bis.1 / DESIGN §3.1）。相同键重复写入 → upsert 覆盖，不保留历史版本。

**可追溯字段**：仅 `provider` + `fetched_at`。`quality_flags` / `source_record_id` / `schema_version` 均不纳入（DESIGN-03-014 §6.3）。

**测试契约**：STUB_COLUMNS 双定义（`_stub_columns.py` 与 `providers/__init__.py`）须等价（§8 `test_provider_phase3.py`）。fixture 覆盖 industry + concept 板块类型及正常 + 极端行情两种场景（§8.2）。

---

## 6. ETLV 验证点

### 6.1 公共验证点

| # | 验证点 | 描述 | 子阶段 | 验证方式 |
|---|---|---|---|---|
| V-GEN-1 | **唯一键幂等性** | 相同唯一键的重复写入应当 upsert，不产生重复记录 | 全部 | 单元测试：mock 数据库验证 upsert 行为 |
| V-GEN-2 | **Provider fetch 超时** | AKShare fetch 超时（可配置，默认 `30s`；[待验证] AKShare 实际响应时间分布）后降级为 `DataResult.error` | 全部 | 集成测试：mock Provider 模拟超时 |
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
| A-001 | `SectorSnapshot` domain object 定义完整（19 个字段 + `from_dict`） | Python import + `from_dict()` 返回有效对象 | P3-A |
| A-002 | `CapitalFlowRecord` domain object 定义完整（17 个字段 + `from_dict`） | 同上 | P3-B |
| A-003 | `MarketSentimentSnapshot` domain object 定义完整（22 个字段 + `from_dict`） | 同上 | P3-C |
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
| **A-016** | **PR-0 Secret source 审计**：逐候选文件验证存在性 + 可加载性；结果表包括文件路径存在、可读、键声明存在三条独立记录 | 审计报告输出（不包含 secret 值/长度/URI/用户名） | T4 P3-A/B/C |
| **A-017** | **PR-1 MongoDB 只读预检**：连接 ping 成功 + `list_collection_names()` 列出所有集合 + 确认三个 P3 目标集合不存在 | 终端命令输出（不含密码） | T4 P3-A/B/C |
| **A-018** | **PR-2 smoke sector**：单板块代码 ≤3 交易日，零持久化写，产出 YAML 报告包含 connectivity/auth/permissions/field_mapping/data_sample/vs_fixture | 检查报告文件存在且包含全部六节 | T4 P3-A |
| **A-019** | **PR-3 smoke flow**：单标的 ≤3 交易日，零持久化写，产出 YAML 报告同上 | 同上 | T4 P3-B |
| **A-020** | **PR-4 smoke sentiment**：单日期，零持久化写，产出 YAML 报告同上 | 同上 | T4 P3-C |
| **A-021** | **T4 零持久化写验证**：DataRouter.query() 对 P3 capability 的 source_trace 不包含 `"ud_materialized(ok)"` 或 `"cache(ok)"` 条目；允许 `ud_materialized(skipped: ...)` 和 `cache(miss)`；force_refresh 也不产生产生持久化副作用 | Python spy/mock 验证 | T4 P3-A/B/C |
| **A-022** | **连通性/认证/权限/数据合理性四条独立记录**：每条 smoke 报告的 connectivity/auth/permissions 节必须独立、不可互相推导 | 检查 YAML 报告结构 | T4 P3-A/B/C |
| **A-023** | **Secret source 非泄露三布尔检查**：审计输出仅包含存在/不存在/可加载/不可加载/键声明/缺失的布尔结论，不含值/长度/URI/用户名 | 终端输出审计 | T4 P3-A/B/C |
| **A-024** | **失败后不自动重试、不切换写入**：smoke 失败仅记录报告，不写入物化/Cache，不自动重试，不自动回退 | 检查 smoke 报告输出 + 无 MongoDB 变更 | T4 P3-A/B/C |
|| **A-025** | **DDL/DML/真实 refresh 仍阻塞**：T4 阶段不执行 `createCollection`、`createIndex`、`upsert()`、`refresh_xxx()` | 终端检查 MongoDB 集合清单 + 无新写入 | T4 P3-A/B/C |
|| **A-026** | **§P0 精确状态矩阵**：六 capability 状态矩阵（离线已验证/AKShareProvider 注册/Real fetch 实现/Real persistence/Refresh 实现/Live smoke 执行）在三层文档中一致 | 静态核对 RFC §P0.2 → SPEC §P0.2 → DESIGN（待 T2 确认） | P0 全部 |
|| **A-027** | **§P0 统一接口边界**：extract→canonical mapping→validation/provenance→DataResult.source_trace 四阶段管线在 SPEC 中定义；禁止实现范围（真实 API/Mongo/Cache 调用）有显式 forbid list | 静态 grep 确认 §P0.3 含所有 5 项禁止实现项 | P0 全部 |
|| **A-028** | **P3-A 映射验收**：§P0.4 的 PA-1~PA-9 全部通过 | 逐项验证 | P0 P3-A |
|| **A-029** | **P3-B 映射验收**：§P0.5 的 PB-1~PB-10 全部通过；PB-5（northbound 恒 None）/PB-7（refresh 三态守卫）/PB-8（northbound fail path）包含精确 Python 验收断言 | 逐项验证 | P0 P3-B |
|| **A-030** | **P3-C 映射验收**：§P0.6 的 PC-1~PC-11 全部通过；PC-3（market_temperature 恒 None）/PC-4（northbound_net_flow 恒 None）确保不虚构值 | 逐项验证 | P0 P3-C |
|| **A-031** | **P0 vs P1 vs P2 边界**：§P0.7 的三阶段边界表与副作用矩阵（§P0.8）在所有三层文档中一致；实现阶段不越界执行 P1/P2 操作 | 静态核对 + 端到端离线 smoke 确认无真实网络调用 | P0 全部 |

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
| `test_provider_phase3.py` | AKShareProvider Phase 3 新增 capability 的 stub/fake fetch；**STUB_COLUMNS 双定义等价性测试**（`stub_columns.STUB_COLUMNS == providers.STUB_COLUMNS`，DESIGN-03-014 §4.1） | 8 | 全部 | 否 |

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
| G-A-1 | `db.createCollection("03_data_ud_market_sector_snapshot")` + `createIndex()` | MongoDB | 新增集合 3 个索引 | Pascal 确认 schema；DDL 执行按 §14.6.4 PR-DDL-P3A 冻结契约（rollback/audit/exit code 权威定义见 DESIGN §6.4） | P3-A |
| G-A-2 | AKShareProvider 首次真实调用 `sector.snapshot` / `sector.ranking` | AKShare API | [待 Pascal 在具体 Gate 授权时确认的请求预算/计量单位]；当前 Gate 仅确认首次 smoke 可行，不做全量预算估计 | smoke 成功 + 日志审核 | P3-A |
| G-A-3 | 手动触发一日 canary 采集 | MongoDB + AKShare | 当日板块快照写入 | Pascal 审核数据质量 | P3-A |
| G-B-1 | `db.createCollection("03_data_ud_stock_capital_flow")` + `createIndex()` | MongoDB | 新增集合 2 个索引 | Pascal 确认 schema；DDL 执行按 §14.6.bis PR-DDL-P3B 冻结契约（rollback/audit/exit code 权威定义见 DESIGN §6.4.bis） | P3-B |
| G-B-2 | AKShareProvider 首次真实调用 `flow.capital_flow_daily` / `flow.northbound_daily` | AKShare API | [待 Pascal 在具体 Gate 授权时确认的请求预算/计量单位]；当前 Gate 仅确认首次 smoke 可行，不做全量预算估计 | smoke 成功 | P3-B |
| G-B-3 | 手动触发 canary：单日个股资金流采集（分批、限速） | MongoDB + AKShare | 全量标的写入 | Pascal 审核数据质量 | P3-B |
| G-C-1 | `db.createCollection("03_data_ud_market_sentiment_snapshot")` + `createIndex()` | MongoDB | 新增集合 2 个索引 | Pascal 确认 schema；DDL 执行/rollback/audit/exit code 按 §14.6.ter 冻结契约（权威定义 DESIGN §6.4.ter） | P3-C | Pascal 手动确认 |
| G-C-2 | AKShareProvider 首次真实调用 `sentiment.market_snapshot` / `sentiment.limit_up_pool` | AKShare API | [待 Pascal 在具体 Gate 授权时确认的请求预算/计量单位]；当前 Gate 仅确认首次 smoke 可行，不做全量预算估计 | smoke 成功 | P3-C |
| G-C-3 | 手动触发 canary：单日情绪快照采集 | MongoDB + AKShare | 当日情绪数据写入 | Pascal 审核数据质量 | P3-C |

---

## 10.bis T4 生产就绪授权 Gate（PR 系列）

**前置说明**：§10 的 G-* 系列 Gate 为 T3 离线实施阶段的授权关卡。以下 PR-* 系列 Gate 为 **T4 生产就绪阶段**的授权关卡，在 T3 离线实现完成后执行。两系列 Gate 对应不同阶段，互不冲突、互不替换。

| Gate ID | 授权内容 | 触发时机 | 影响范围 | 停止条件 | 涉及子阶段 | 执行人 |
|---|---|---|---|---|---|---|
| **PR-0** | **Secret source 审计**（仅 MongoDB）：逐候选文件证明五组件键 `MONGODB_HOST`、`MONGODB_PORT`、`MONGODB_USERNAME`、`MONGODB_PASSWORD`、`MONGODB_DATABASE`（来自 **skills/.env**，复用 Phase 2 PortfolioMongoLoader 认证语义，组件式构造连接，非 URI）的文件存在、可被进程加载、全部五键声明且非空匹配。**AKShare 跳过密钥审计**——AKShare 为匿名无 token 数据源。**禁止输出值、长度、URI、用户名或全路径+键值组合** | T4 起始 | 文件存在性检查、运行时 env 探测（只读） | 候选文件不存在、任意一键缺失/空白、端口无效、数据库名不等于 `tradingagents` → 标记 MongoDB 为「NOT_AUTHORIZED」；AKShare 跳过 PR-0 检查 | P3-A/B/C | Pascal 或 DevOps |
| **PR-1** | **MongoDB 只读连通预检**：使用 `pymongo.MongoClient` 连接 `tradingagents` 库，ping，列出所有集合，验证无三个 P3 目标集合。**不建集合、不读业务数据** | PR-0 pass | 网络 io（<1s）、MongoDB driver 加载 | 连接失败/认证拒绝/意外发现目标集合已存在 → 停止并记录 | P3-A/B/C | Dev/Agent |
| **PR-2** | **AKShare Provider smoke：`sector.snapshot` + `sector.ranking`** — 单板块代码（`BK0489`），≤3 个交易日窗口，AKShare 匿名只读调用。**零持久化写** | PR-1 pass（AKShare smoke 不依赖 PR-0 pass） | AKShare API 调用 1-2 次、每小时配额 | API 返回错误/字段完全不匹配/json 解析异常 → 停止；差异仅记录在字段映射报告中 | P3-A | Dev/Agent |
| **PR-3** | **AKShare Provider smoke：`flow.capital_flow_daily` + `flow.northbound_daily`** — 单标的（`600519` / `000001`），≤3 个交易日窗口，AKShare 匿名只读调用 | PR-1 pass（AKShare smoke 不依赖 PR-0 pass；可并行于 PR-2） | AKShare API 调用 2-4 次、每小时配额 | API 失败/空返回/北向字段缺失 → 停止并记录 | P3-B | Dev/Agent |
| **PR-4** | **AKShare Provider smoke：`sentiment.market_snapshot` + `sentiment.limit_up_pool`** — 单日期，AKShare 匿名只读调用 | PR-1 pass（AKShare smoke 不依赖 PR-0 pass；可并行于 PR-2/PR-3） | AKShare API 调用 2 次、每小时配额 | API 失败/核心字段缺失 → 停止并记录 | P3-C | Dev/Agent |
| **PR-DDL-P3A** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_market_sector_snapshot` + 索引**（**仅 P3-A 已授权冻结**；P3-B/P3-C 的 PR-DDL 仍阻塞，见 §14.6.4） | PR-2 pass + Pascal 独立确认 | MongoDB 元数据写入——集合创建、索引构建 | 写权限不足/长时间索引重建 → 停止；schema 版本须与 SPEC §3.1 一致；DDL 执行/rollback/audit/exit code 按 §14.6.4 冻结契约（权威定义 DESIGN §6.4） | P3-A | Pascal 手动确认 |
| **PR-DDL-P3B** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_stock_capital_flow` + 索引**（**P3-B 已授权冻结**；P3-C 的 PR-DDL 仍阻塞，见 §14.6.bis） | PR-3 pass + Pascal 独立确认 | MongoDB 元数据写入——集合创建、索引构建 | 写权限不足/长时间索引重建 → 停止；schema 版本须与 SPEC §3.2 一致；DDL 执行/rollback/audit/exit code 按 §14.6.bis 冻结契约（权威定义 DESIGN §6.4.bis） | P3-B | Pascal 手动确认 |
| **PR-DDL-P3C** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_market_sentiment_snapshot` + 索引**（**P3-A + P3-B + P3-C 已全部授权冻结**，见 §14.6.4 / §14.6.bis / §14.6.ter） | PR-4 pass + Pascal 独立确认 | MongoDB 元数据写入 | 写权限不足/长时间索引重建 → 停止；schema 版本须与 SPEC §3.3 一致；DDL 执行/rollback/audit/exit code 按 §14.6.ter 冻结契约（权威定义 DESIGN §6.4.ter） | P3-C | Pascal 手动确认 |
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
- [ ] **OQ-8（V0.5 更新）**：AKShare 无需 token（已确认为匿名数据源），OQ-8 已解决。PR-0 审计仅覆盖 MongoDB 的五组件键（`MONGODB_HOST`/`PORT`/`USERNAME`/`PASSWORD`/`DATABASE`），来源为 `skills/.env`。V0.4 中使用的 `MONGO_URI` 单键来源已 superseded——复用 Phase 2 PortfolioMongoLoader 组件式构造连接语义。
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

### 12.bis Sentiment domain object 10→22 字段迁移变更清单

Pascal 裁定（2026-07-30）确认 22 字段全市场多维快照为 MarketSentimentSnapshot 的 canonical 产品 schema。以下为 T3 Implement 或后续对齐阶段必须执行的文件变更清单。**当前（100%）不对齐 canonical 的离线实现保留不删**，但任何持久化/Provider 调用必须基于 canonical 契约。

#### 12.bis.1 必需变更（Allowlist）

| 路径 | 允许操作 | 约束 |
|------|---------|------|
| `models/domain/sentiment.py` | `MarketSentimentSnapshot` dataclass 从 10 字段（`market`, `sentiment_type`, `market_date`, `score`, `sample_size`, `source`, `provider`, `fetched_at`, `notes`, `metadata`）重构为 22 字段 canonical 契约（`snapshot_date`, `snapshot_time`, `market`, `limit_up_count`, `limit_down_count`, `limit_up_count_ex_st`, `limit_down_count_ex_st`, `advance_count`, `decline_count`, `flat_count`, `total_listed_count`, `market_temperature`, `total_turnover`, `hot_concepts`, `continuous_limit_up`, `max_continuous_days`, `northbound_net_flow`, `limit_up_pool`, `limit_down_pool`, `fetched_at`, `provider`, `raw_payload`），唯一键由 `{market, sentiment_type, market_date}` 改为 `{market, snapshot_date, snapshot_time}`；`from_dict()` 同步更新；关闭 `frozen=True, slots=True`（按 SPEC §3.3 可修改的 dataclass 模式） | 不得保留旧 10 字段的任何引用在新 dataclass 中；不得在`from_dict()` 中引用 `sentiment_type`、`market_date`、`score`、`sample_size`、`notes`、`metadata` 等淘汰字段 |
| `services/sentiment_service.py` | 更新引用类型：所有 `get_market_sentiment_snapshot()` 返回类型改为新 `MarketSentimentSnapshot`；`refresh_market_sentiment_snapshot()` 写入路径基于新 schema | 不改动 read path 的 capability 注册逻辑；不改动 `PersistenceResult`；不改动三态守卫 |
| `tests/fixtures/sentiment_fixtures.py` | fixture 数据从 10 字段重建为 22 字段 canonical 映射；覆盖正常交易日 + 极端行情两种场景 | 至少 2 条记录；所有非 None 字段填充合法值 |
| `tests/test_market_sentiment.py` | 断言更新：字段计数从 10→22；唯一键断言从 `sentiment_type`→`snapshot_date+snapshot_time`；温度范围验证；列表长度约束 | 不得缩减已有测试覆盖的边界条件 |
| `tests/test_sentiment_service.py` | service 层 fixture 引用更新；Spy 断言更新 | 同上 |
| `providers/_stub_columns.py` | `sentiment.market_snapshot` STUB_COLUMNS 更新为 22 字段 canonical 列 | 与 `providers/__init__.py` 保持孪生等价 |
| `providers/__init__.py` | 同上同步更新 | 保持与 `_stub_columns.py` 孪生等价 |
| `models/domain/__init__.py` | 确认 `MarketSentimentSnapshot` 仍在导出列表（保持不变） | 不改变导出符号名 |

#### 12.bis.2 禁止修改（Blocklist）

| 路径 | 理由 |
|------|------|
| `skills/data/unified_data/router.py` | Router 内部编排逻辑不受 domain object 字段变更影响 |
| `skills/data/unified_data/client.py` | client 层仅传递 capability 字符串和 `SecurityId`，不关心 domain object 字段 |
| `skills/data/unified_data/providers/__init__.py` 中的 `STUB_COLUMNS` 孪生必须按 §12.bis.1 同步更新，除此以外的 `providers/__init__.py` 结构保持不变 | 避免 import 冲突 |
| `skills/data/unified_data/models/domain/flow.py` | CapitalFlowRecord 不受 MarketSentimentSnapshot 变更影响 |
| `skills/data/unified_data/services/flow_service.py` | FlowService 不受影响 |
| `skills/data/unified_data/providers/akshare.py` | AKShareProvider 的 sentiment capability 映射更新属独立范围（不在此迁移 task 中） |
| 任何 Template / README / SKILL | 全局规约源不变 |
| 任何 cron / systemd 配置 | 不在 Phase 3 范围 |

#### 12.bis.3 Superseded 声明

离线 T3-B 实现的 10 字段 `MarketSentimentSnapshot`（`frozen=True, slots=True`, 唯一键 `{market, sentiment_type, market_date}`）已被本节 22 字段 canonical 契约**取代**。离线代码保留在磁盘（`models/domain/sentiment.py`），不作删除，但：
- 任何持久化写入必须基于 22 字段 canonical 契约。
- 任何 Provider 映射必须基于 22 字段 canonical 契约。
- 任何新测试必须基于 22 字段 canonical 契约。
- 现有 10 字段测试保留作为 regression baseline。

此 superseded 状态由 Pascal 2026-07-30 裁定锁死，不得未经 Pascal 确认恢复 10 字段为 canonical。

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
| `skills/.env` | 文件存在、可读 | `os.path.isfile() 且 os.access(R_OK)` | 存在/不存在/不可读 |
| `skills/.env` 五组件键 | 五个键均声明且非空——`MONGODB_HOST`、`MONGODB_PORT`、`MONGODB_USERNAME`、`MONGODB_PASSWORD`、`MONGODB_DATABASE` | `os.getenv("MONGODB_HOST")` 等逐一检查 | 全部已声明/缺失 N 个键 |
| Hermes 运行时 env | 五键声明 | `os.getenv(key)` 返回非 None | 已声明/未声明 |
| AKShare 匿名调用 | 无需密钥审计 | —（AKShare 为匿名数据源，无需 token） | 跳过 PR-0 |

**约束**：
- 每条检查仅输出结论（存在/不存在/可加载/不可加载 + 键声明存在/缺失）
- **绝对禁止**：输出值、长度、URI（含 `mongodb://...`、`https://...`）、用户名、全路径+键值组合
- 每个候选 source 独立记录，不归并、不默认降级
- MongoDB skills/.env 五组件键候选 source 全部不存在或键缺失 → 标记 MongoDB 为「NOT_AUTHORIZED」，PR-1（MongoDB 预检）不执行
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
# optional metadata — only emitted when the live-read ran AND ALL
# PR-2 calls failed with ProxyError/ConnectionError. Absent
# (== null in YAML) in dry-run, success, partial-failure, and
# generic RuntimeError paths. See scripts/t4_preflight/smoke_sector.py
# Fix E / DESIGN-03-014 §15.7.1.
endpoint_status: endpoint_unreachable   # optional; absent = not network-blocked
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

### 14.4.5 B2 单次只读 smoke 实测映射契约冻结（V0.9 新增 — 权威可执行契约）

> **权威定位**：本节是 RFC §13.4.5 所引用的**可执行契约层**。工具链设计（字段选择逻辑、reporter 实现、fixture 结构）的权威定义在 **DESIGN-03-014 §15.x（V0.16）**；本节定义业务语义、verdict 边界与禁止行为。如本节与 DESIGN 出现差异，以本节业务语义为准，DESIGN 实现须对齐本节。

#### 14.4.5.1 冻结证据（只读、不可重跑）

| 证据 | 路径 | 性质 |
|---|---|---|
| PR-2 sector | `/tmp/yquant-b2-pr234-20260726/pr2/smoke-sector-20260726.yaml` | 只读副本；不可移动/提交/复制到仓库；不可重跑 |
| PR-3 flow | `/tmp/yquant-b2-pr234-20260726/pr3/smoke-flow-20260726.yaml` | 同上 |
| PR-4 sentiment | `/tmp/yquant-b2-pr234-20260726/pr4/smoke-sentiment-20260726.yaml` | 同上 |

**硬约束**：本阶段（Full Flow T1）不重跑任何 live-read；本次 B2 已用尽单次 live-read 预算（§14.4.5.5）。T2 Design / T3 Implement 的映射修复须基于本冻结证据 + AKShare 公开文档 + 离线 fixture，**不得**以「需要再验证」为由重跑 live-read。

#### 14.4.5.2 PR-3 flow.northbound_daily 语义不匹配（关键阻断）

**冻结事实**（来自 PR-3 smoke 报告）：
- endpoint：`akshare.stock_hsgt_individual_em(symbol='600519')`
- 网络层：success（latency ~1131ms），auth=authorized，permissions=ok
- 返回 5 行（2017-03-16..2017-03-22），actual_fields = 9：
  `持股日期` / `当日收盘价` / `当日涨跌幅` / `持股数量` / `持股市值` / `持股数量占A股百分比` / `今日增持股数` / `今日增持资金` / `今日持股市值变化`
- 现有 expected（脚本 `_EXPECTED_NORTHBOUND_FIELDS`）：`date` / `stock` / `northbound_net_inflow`，外加 flow 侧 8 字段 = 11；matched 0/11；missing = `date` / `stock` / `northbound_net_inflow`。

**语义判定**：该 endpoint 返回**北向持股历史（holding history）**语义，**不是**北向净流入（net inflow）。两者业务语义不同：
- 持股历史：某标的每日北向持股数量、持股市值、占比、日增减——回答「北向持有多少」。
- 净流入：某标的每日北向买卖差额——回答「北向今天净买了多少」。

**禁止伪装（硬约束，T2/T3 必须遵守）**：
- 禁止将 `持股数量` / `持股市值` / `今日增持资金` 等字段别名映射为 `northbound_net_inflow`。
- 禁止在 `CapitalFlowRecord.northbound_net_inflow`（§3.2）中静默填入持股语义的值。
- 禁止在 smoke 报告 / domain object / mapping 文档中把「北向持股历史」表述为「北向净流入」。

**Pascal 决策（2026-07-26）：选 C — 放弃净流入，字段保持 None**

Pascal 已明确选择 **C**：当前 Phase 3 不提供北向净流入数据，`northbound_net_inflow` 保持 None，持股历史作为辅助保留。选项 A、B 均**未被选择**。

| 选项 | 落地动作 | 影响范围 | 状态 |
|---|---|---|---|
| **A. 分流到正确 endpoint** | T2 在 DESIGN §4.2 / §15.6 将 `flow.northbound_daily` 的 fetch 路径指向真正返回北向净流入的 endpoint（候选：`stock_hsgt_fund_flow_summary_sina` / `stock_em_hsgt_north_net_flow_in` 等，T2 须基于 AKShare 公开文档确认）；持股历史 endpoint 另立 capability 或丢弃 | 需新增/调整 capability（超出本卡范围） | **未选（Pascal 2026-07-26 明确放弃）** |
| **B. 变更 capability 语义** | 将 `flow.northbound_daily` 语义改为「北向持股历史」；T2 须回头修订 SPEC §3.2 `CapitalFlowRecord` 的 `northbound_*` 字段定义 | 下游消费方契约变更 | **未选（Pascal 2026-07-26 明确放弃）** |
| **C. Pascal 确认放弃净流入（已选）** | 当前 Phase 3 不提供北向净流入；`northbound_net_inflow` 保持 None；持股历史作为辅助保留 | 能力缺口（已接受） | **✅ Pascal 2026-07-26 已确认选择** |

**C 选项落地约束（硬约束，T2/T3 须遵守）**：
- `flow.northbound_daily` capability **保留**，但其 fetch 路径在当前 Phase 3 **不指向任何真实 endpoint**——`northbound_net_inflow` 恒为 None。
- `CapitalFlowRecord.northbound_net_inflow`（§3.2）字段定义**不变**（仍为 `float | None = None`），只是当前 Phase 3 永不填充非 None 值。
- 持股历史（B2 返回的 9 个持股字段）作为**辅助参考**，T2/T3 可在 DESIGN 工具链中以参考字段标注，但**不得**映射入 `northbound_net_inflow` 或任何 `*_net_inflow` 字段。
- 不引入新 endpoint、新 capability、新 endpoint skeleton。

#### 14.4.5.3 PR-4 sentiment 空返回语义区分

**冻结事实**（来自 PR-4 smoke 报告）：
- endpoint：`akshare.stock_market_fund_flow()` + `akshare.stock_zt_pool_em(date)`
- 网络层：success（latency ~1525ms），auth=authorized，permissions=ok
- row_count=0，actual_fields=0，matched 0/31，missing=[]（actual 为空，无法计算 missing）

**Pascal 决策（2026-07-26）：选 X2 — 空返回语义收敛为保守 fail，移除 empty_semantics 分类**

空返回维持 verdict=fail（保守）。原三分类（无交易日/schema drift/调用异常）的 `empty_semantics` reporter 字段在 X2 下**移除**——reporter 不再输出 `empty_semantics` 分类字段，空返回仅在 memo 中记录观测事实。

| B2 观测事实 | X2 下的 verdict |
|---|---|
| row_count=0 且 actual_fields=0（本次 B2 即此） | **fail**（保守，不进一步细分原因） |
| endpoint 抛异常、返回非 DataFrame、JSON 解析失败 | **fail**（停止该子阶段；记录异常类；不自动重试） |

**本次 B2 判定（按 X2）**：verdict=fail（memo 记录 `matched_ratio=0.00 (0/31); missing=[]; row_count=0; actual_fields=0`）。后续独立 live-read（非本阶段）在交易日复验时，若返回非空数据则按正常字段匹配流程判定；reporter 不再负责区分「无交易日」与「schema drift」的空返回语义。

**X2 落地约束（硬约束，T2/T3 须遵守）**：
- reporter 账本**不输出** `empty_semantics` 字段。
- reporter 账本**不输出** `worktree_changed` 字段（原 X1 候选的 runtime git-worktree 探测被 X2 移除）。
- 空返回 verdict 一律 fail；不引入 verdict 篡改逻辑。
- PR-4 的 expected 字段集仍保留（基于公开文档推断），后续独立 live-read 复验时使用。

#### 14.4.5.4 PR-2 sector SSL 网络停止诊断边界

**冻结事实**（来自 PR-2 smoke 报告）：
- endpoint：`akshare.stock_board_industry_cons_em("BK0489")` ×2
- 两调用均 SSLError（`requests.exceptions`），connectivity=failed，latency_ms=null
- auth=authorized（AKShare 匿名），permissions=restricted
- verdict=fail，`endpoint_status=endpoint_unreachable`
- memo：「endpoint_unreachable: SSLError: requests.exceptions — egress restriction, not a code defect.」

**判定**：PR-2 失败为**网络层 egress 限制**（SSL/TLS 握手失败或出口阻断），**不是代码 defect**，也**不是** mapping 问题。

**边界（硬约束）**：
- 停止 PR-2（sector）后续 smoke，不自动重试。
- 禁止将 PR-2 SSL 失败与 PR-3/PR-4 mapping 修复耦合——三者独立。
- 仅允许后续**单变量网络诊断**（切换网络出口、验证 AKShare 上游可达性、检查 TLS 版本），且须 Pascal 独立授权，不在本 T1 阶段执行。
- PR-2 的 expected 字段集在 T2 须基于 AKShare 公开文档与离线 fixture 推断更新，并明确标注「未 live-read 验证」；**不得**以「需要 live-read 验证」为由阻塞 T2。

#### 14.4.5.5 单次 live-read 精确调用预算与零写入边界

**精确预算（本次 B2 已用尽）**：

| PR | endpoint | 本次实际调用 | 预算上限 | 剩余 |
|---|---|---|---|---|
| PR-2 | `stock_board_industry_cons_em` | 2（均 SSLError） | 2 | 0 |
| PR-3 | `stock_individual_fund_flow` ×2 + `stock_hsgt_individual_em` ×1 | 3（均成功） | 3 | 0 |
| PR-4 | `stock_market_fund_flow` + `stock_zt_pool_em` | 2（均成功但空） | 2 | 0 |

**零写入边界（本次 B2 已遵守，T2/T3 须继承）**：
- 无重试：所有失败仅记录。
- 无 fallback：PR-2 SSL 失败后未切换 endpoint/provider。
- 零 Mongo 写入：无集合/索引/文档变更。
- 零 Cache 写入：无 `CacheManager.put()`。
- 零 AuditLogger 写入：无 `03_data_ud_query_audit` 写入。
- 零 DDL：无 `createCollection` / `createIndex`。
- 零 cron/systemd 注册。

**T2 边界**：T2 Design / T3 Implement 不得引入上述任何写入；mapping 修复仅体现在 expected 字段集、endpoint 选择、reporter 账本字段与 fixture/test 中。

#### 14.4.5.6 T2 实现最小文件范围与禁止修改清单

T2 Design（task t_987fde34）须在以下最小范围内体现映射修正，**禁止无关重构**：

| 文件/文档 | 允许的修改 | 禁止的修改 |
|---|---|---|
| `docs/design/03_data/DESIGN-03-014-*.md` §4.2 | AKShare→Canonical 映射模式（endpoint 选择、字段 alias、单位、日期窗口） | domain object 字段定义（属 SPEC §3） |
| `docs/design/03_data/DESIGN-03-014-*.md` §15.x | 工具链：expected 字段集、endpoint 选择逻辑、reporter 账本字段（provider_attempts/实际调用数/retry_count/fallback_count/mongo_calls/write_operations） | DDL 契约（§6.4 系列）；`worktree_changed`/`empty_semantics` 字段（X2 已移除） |
| `scripts/t4_preflight/smoke_flow.py` | `_EXPECTED_FLOW_FIELDS` / `_EXPECTED_NORTHBOUND_FIELDS`、endpoint 选择（§14.4.5.2 C 已选，northbound 恒 None） | 测试框架结构 |
| `scripts/t4_preflight/smoke_sentiment.py` | `_EXPECTED_SENTIMENT_FIELDS` / `_EXPECTED_LIMIT_UP_FIELDS`（空返回 verdict=fail 保守） | 同上 |
| `scripts/t4_preflight/smoke_sector.py` | expected 字段集（基于公开文档推断） | 同上 |
| `scripts/t4_preflight/provider_client.py` | endpoint 选择、空返回保守 fail 标记 | client 安全边界（单次、限速、零写入） |
| `scripts/t4_preflight/reporter.py` / `models.py` | 账本字段（provider_attempts/实际调用数/retry_count/fallback_count/mongo_calls/write_operations） | 脱敏规则（§15.7.2）；`worktree_changed`/`empty_semantics` 字段（X2 已移除） |
| `skills/data/unified_data/tests/fixtures/*` | 对应 fixture 更新以反映真实字段 | fixture 框架 |
| 对应 `test_*.py` | 断言更新 | 测试覆盖范围缩减 |

**禁止修改**：
- SPEC-03-014 §3（domain object 字段定义）——Pascal 已选 C，不采用选项 B，§3 字段定义不变。
- SPEC/RFC 的 DDL 契约（§14.6.x / §6.4.x）。
- `docs/*template*`、生产代码、配置、secrets、Mongo/缓存/调度。

#### 14.4.5.7 T2 验收准则（7 项）

T2 Design 完成时须满足：
1. PR-3 `flow.northbound_daily` 的 endpoint 选择已落实 §14.4.5.2 Pascal 已选的 **C**（northbound_net_inflow 恒 None，不指向真实 endpoint），且在 DESIGN §4.2 / §15.6 显式标注 C 已选与依据；不引入 A/B 选项的 endpoint skeleton。
2. PR-4 空返回语义按 §14.4.5.3 X2 收敛：reporter **不输出** `empty_semantics` 字段，空返回 verdict=fail（保守）。
3. PR-2 的 expected 字段集已基于公开文档推断更新，且明确标注「未 live-read 验证」。
4. 单次 live-read 预算与零写入边界在 DESIGN §15.x 显式声明，且 T2 未重跑 live-read。
5. smoke 报告账本字段（provider_attempts/实际调用数/retry_count/fallback_count/mongo_calls/write_operations）已在 reporter 定义最小实现；**不包含** `worktree_changed` 与 `empty_semantics`（X2 已移除）。
6. 单元/fixture 测试、离线回归、静态零写入扫描、后续独立 live-read 的验证计划已定义（不在本阶段执行 live-read）。
7. PR-2 SSL 网络诊断仅允许后续单变量网络诊断，未混进 mapping 修复或自动重试。

#### 14.4.5.8 与既有条文的关系

- 本 §14.4.5 是 §14.4（真实 Provider Smoke 规程）在 B2 冻结证据上的**精确化与冻结**，不修改 §14.4.1 通用规则、§14.4.2 报告模板、§14.4.3 报告存储、§14.4.4 失败与偏差处理的既有条文。
- 不修改 §14.6.x DDL 冻结契约（P3-A/B/C 三者仍冻结）。
- 不修改 §3 domain object 字段定义（Pascal 已选 C，§3 字段定义不变）。
- 不修改既有用户授权范围（PR-0 ~ PR-4、PR-DDL-* 的授权语义不变）。

#### 14.4.5.9 B2 全 capability 映射裁决总表

每项 capability 的三态裁决（可真实映射/保持线下 stub/明确 fail-stop），AKShareProvider 注册状态取自当前代码基线（截至 2026-07-29）：

| Capability | B2 实测状态 | AKShareProvider 注册状态 | 映射裁决 | 依据 |
|---|---|---|---|---|
| `sector.snapshot` | SSL 失败（SSLError） | ✅ P3-A stub（注册，无真实调用路径） | **offline stub** — 预期字段集基于 AKShare 公开文档推断，标注「未 live-read 验证」 | §14.4.5.4 PR-2 |
| `sector.ranking` | SSL 失败（同 endpoint） | ✅ P3-A stub | **offline stub** — 同 sector.snapshot | §14.4.5.4 |
| `flow.capital_flow_daily` | 成功（`stock_individual_fund_flow`，均 success） | ❌ 未注册（当前代码仅含 9 项 capability，缺 flow + sentiment 4 项） | **real-mappable** — B2 已验证 endpoint 返回数据；T3 须注册到 AKShareProvider | §14.4.5.2 PR-3 |
| `flow.northbound_daily` | success 但语义不匹配（持股历史≠净流入） | ❌ 未注册 | **fail-stop（Pascal C）** — capability 保留但 fetch 路径不指向真实 endpoint；`northbound_net_inflow` 恒 None | §14.4.5.2 Pascal C |
| `sentiment.market_snapshot` | success 但空返回（row_count=0） | ❌ 未注册 | **offline stub** — verdict=fail（X2 保守）；须交易日 live-read 复验 | §14.4.5.3 Pascal X2 |
| `sentiment.limit_up_pool` | success 但空返回（row_count=0） | ❌ 未注册 | **offline stub** — 同 market_snapshot | §14.4.5.3 |

**AKShareProvider 注册缺口**：当前 `AKShareProvider`（`akshare.py`）仅声明 9 项 capability（7 项 Phase 1D + 2 项 P3-A sector）。`flow.capital_flow_daily`、`flow.northbound_daily`、`sentiment.market_snapshot`、`sentiment.limit_up_pool` 四项**未注册**。T3 须按映射裁决逐项注册：real-mappable 的 `flow.capital_flow_daily` 须注册真实调用路径；offline stub 的 sentiment 和 fail-stop 的 northbound 可注册 stub 路径或暂不注册。

#### 14.4.5.10 Refresh 授权前状态机

`refresh_xxx()` 方法在对应 Gate 授权前的行为契约：

| 状态 | 条件 | `refresh_xxx()` 行为 | 信令 |
|---|---|---|---|
| **未授权（unauthorized）** | `p3_writer=None` | 抛出 `ProviderUnavailableError`；不执行 Provider fetch、不写物化 | 异常 |
| **已注入但未实现（injected-not-implemented）** | `p3_writer` 已注入但 refresh happy-path 未实现 | 抛出 `NotImplementedError` | 异常 |
| **已授权可写入（authorized）** | Gate 授权 + refresh 完整实现 | Provider fetch → upsert → 返回 `PersistenceResult` | 正常返回 |

**每 capability 约束**：
- `sector.snapshot`/`sector.ranking`（offline stub）：refresh 路径仅在 SSL 诊断通过后评估——当前保持在「未授权」或「已注入但未实现」。
- `flow.capital_flow_daily`（real-mappable）：T3 可实现为「已授权可写入」（须对应 G-B-2 授权）。
- `flow.northbound_daily`（fail-stop/C）：**不得**进入「已授权可写入」——恒 None 无数据可写。
- `sentiment.market_snapshot`/`sentiment.limit_up_pool`（offline stub）：保持在「已注入但未实现」直到交易日 live-read 复验。

#### 14.4.5.11 既有实现冲突坐标与修正契约

本节基于 RFC §13.4.5.10 的冲突判定，给出每项冲突在 SPEC 层的精确契约。Developer 按此契约执行代码修复；Verify 按此契约逐项验收。

##### 14.4.5.11.1 冲突 A：`flow_stub.py` 默认 payload northbound 字段

**来源**：`providers/flow_stub.py` 第 78-98 行（Record A 600519）、第 119-139 行（Record C 000001）。

**契约修正**：以下三个 dict key 在 Record A 和 Record C 中**必须为 `None`**（值非 `None` 视为修正不完整）：
- `"northbound_net_inflow": None`
- `"northbound_hold_shares": None`
- `"northbound_hold_ratio": None`

**允许保留**：这三对 key 本身（允许 dict 中带 `None` 值的 key）。Record B（300999）和 Record D（AAPL）的 `None` northbound 值不变。

**验收断言**：
```python
records = _build_default_payload()
for r in records:
    assert r.get("northbound_net_inflow") is None
    assert r.get("northbound_hold_shares") is None
    assert r.get("northbound_hold_ratio") is None
```
即四条记录全部通过（B/D 已经 None，A/C 由非 None 改为 None）。

**不修改**：非 northbound 字段、Record B/D、`_DEFAULT_CAPABILITIES`、`StubFlowProvider` 的 capability/market 声明。

##### 14.4.5.11.2 冲突 B：`flow_service.py` refresh 未授权 fetch→upsert

**来源**：`services/flow_service.py` 第 488-641 行 `refresh_capital_flow()`。

**契约修正**：refresh 行为改为三态守卫：
1. `p3_writer is None` → 抛 `ProviderUnavailableError`（已有，不改）
2. `p3_writer is not None and not self._is_refresh_authorized()` → 抛 `NotImplementedError("Refresh not yet authorized for P3-B flow.capital_flow_daily")`（新增，本卡实现）
3. `p3_writer is not None and self._is_refresh_authorized()` → 现有 happy-path fetch→upsert（未来 G-B-2 Gate 授权后启用）

**新增方法**（`FlowService`）：
```python
def _is_refresh_authorized(self) -> bool:
    """Return True when the refresh path is Gate-authorized.

    Default ``False`` (offline-only safety). The flag is toggled by
    the G-B-2 Gate process after Pascal confirms readiness.
    """
    return False  # T3-P3B offline default — override only via Gate
```

`refresh_capital_flow()` 第 553-558 行（`p3_writer is None` 守卫）之后、第 559 行（capability 断言）之前，插入上述守卫。

**北向 refresh fail path**（本卡范围）：
- `FlowService` 新增 `_northbound_refresh_disallowed()` 返回 `True` + docstring「Pascal C: northbound 永不授权写入」
- `refresh_capital_flow()` 在 capability 断言后检查 `capability == flow.northbound_daily` 时抛 `NotImplementedError`（显式 fail-stop，不进入 fetch/upsert 路径）

**不修改**：`PersistenceResult` dataclass、`_fetch_for_refresh()`、`write_disabled()`、read path `get_capital_flow()` / `get_northbound_flow()`。

**验收断言**：
```python
svc = FlowService(p3_writer=MagicMock())
with pytest.raises(NotImplementedError):
    svc.refresh_capital_flow()
svc._p3_writer.upsert.assert_not_called()  # 未 upsert
```

##### 14.4.5.11.3 冲突 C：文档字符串 northbound 语义

**来源**：
- `models/domain/flow.py` 第 23-24 行 `CapitalFlowRecord` 类 docstring：`northbound_* — only populated for 沪/深港通标的`
- `services/flow_service.py` 第 256-260 行 `get_northbound_flow()` docstring：`only the three northbound_* fields ... are populated`

**契约修正**：上述两处 docstring 追加：
```
(Pascal C — Phase 3: northbound_* fields are ALWAYS None.
 The type signature (float | None) is preserved but no non-None value
 is ever populated in this Phase.)
```

不修改 docstring 以外的任何内容。

##### 14.4.5.11.4 冲突 D：`StubFlowProvider` northbound 投影过滤

**来源**：`providers/flow_stub.py` 第 241-268 行 `StubFlowProvider.fetch()`。

**契约修正**：`fetch()` 在 `operation == "northbound_daily"` 时，对返回列表的每个 dict 执行：
```python
for record in payload:
    record["northbound_net_inflow"] = None
    record["northbound_hold_shares"] = None
    record["northbound_hold_ratio"] = None
```
（类似 `CapitalFlowRecord.from_northbound_dict` 的投影逻辑。）

**不修改**：`flow.capital_flow_daily` 的 fetch 路径、`call_log` 记录、`raise_on_fetch` 逻辑。

**验收断言**：
```python
stub = StubFlowProvider()
result = stub.fetch("flow", "northbound_daily", SecurityId(market="CN", symbol="600519"))
for r in result:
    assert r["northbound_net_inflow"] is None
# capital_flow_daily 不受影响
result2 = stub.fetch("flow", "capital_flow_daily", SecurityId(market="CN", symbol="600519"))
assert result2[0]["main_net_inflow"] is not None  # 非 northbound 字段无影响
```

##### 开发者允许路径与禁止路径

同 RFC §13.4.5.10 Developer allowlist 表。严格按此表执行，越界修改视为验收 FAIL。

##### 最小验收命令

```bash
PYTHONPATH=. python -m pytest tests/data/unified_data/ \
  -k "northbound or refresh_capital_flow or capital_flow" \
  -q --tb=short 2>&1 | tail -20
```

此外独立运行：
```bash
PYTHONPATH=. python -c "
from skills.data.unified_data.providers.flow_stub import _build_default_payload
records = _build_default_payload()
for i, r in enumerate(records):
    assert r.get('northbound_net_inflow') is None, f'Record {i} northbound_net_inflow={r.get(\"northbound_net_inflow\")}'
    assert r.get('northbound_hold_shares') is None
    assert r.get('northbound_hold_ratio') is None
print('OK: ALL 4 records have None northbound fields')
"
```

---

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
- 通过 spy/source trace 验证：`DataResult.source_trace` 中不包含 `"ud_materialized(ok)"` 或 `"cache(ok)"` 条目（允许 `ud_materialized(skipped: ...)`、`cache(miss)`）
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

#### 14.6.4 PR-DDL-P3A 精确契约（B1-P3A 冻结）

> **授权状态**：**仅 P3-A 已冻结**（本 §14.6.4）。P3-B 的 PR-DDL 精确契约见 §14.6.bis；P3-C 的 PR-DDL 精确契约见 §14.6.ter。下游 Implement / Verify / Review 严格按本节冻结契约执行 P3-A 的 DDL。

**权威来源**：DDL 执行语义、rollback 脚本、audit 字段、失败矩阵、退出码的权威定义在 **DESIGN-03-014 §6.4**（V0.13）。本节为 SPEC 层的契约引用与 Gate 集成，不重复完整定义——如本节与 DESIGN §6.4 出现差异，以 DESIGN §6.4 为准。

**PR-DDL-P3A 契约**：

| 维度 | 冻结值 |
|---|---|
| 前置条件 | (a) PR-2 verdict 为 `pass` 或 `conditional_pass`（Pascal 已审阅偏差）；(b) Pascal 已确认 SPEC-03-014 §3.1 schema 最终版；(c) §14.6 DDL Gate 授权要求 1-6 全部满足 |
| 集合 | 仅 `03_data_ud_market_sector_snapshot`（库 `tradingagents`，主仓 `main` 本地工作树） |
| 索引 | 三条——`sector_code_date` / `snapshot_date` / `sector_type_date`，全部 `background: true`（定义见 DESIGN §6.2，本节引用不重述） |
| 写入身份 | 复用现有 `MONGODB_USERNAME`（Phase 2 PortfolioMongoLoader 组件式构造连接语义） |
| 写入原子性 | **失败即停，不自动回滚**；`createCollection` / `createIndex` 在目标已存在时 fail-stop（exit 4），由操作员手动评估 |
| rollback 脚本 | `/tmp/yquant-p3-ddl-p3a-20260725/rollback.js`（dropIndex 反向顺序 + dropCollection；不提交仓库；权威内容见 DESIGN §6.4.1） |
| audit 工件 | stdout + `/tmp/yquant-p3-ddl-p3a-20260725/audit.json`；字段 `{operation, collection, index, ts, exit_code, error, rollback_script_path}`（定义见 DESIGN §6.4.2）；**不引入**新 audit 集合 |
| 退出码 | `0`=DDL 成功；`2`=DDL 失败（非权限、非已存在）；`3`=权限不足；`4`=目标已存在（fail-stop）。退出码 1 不使用（与 §15.5.4 PR-1 conditional pass 语义分离）。退出码定义见 DESIGN §6.4.4 |
| 停止条件 | 任一非 0 退出码即 fail-stop；**不自动回滚**、**不自动重试**；是否运行 rollback.js 由操作员按 DESIGN §6.4.3 失败矩阵的「operator action」列判断 |
| DDL 执行人 | Pascal 手动执行（或 Pascal 授权的 DevOps）；Agent 不直接执行 DDL（与 §14.6 DDL Gate 授权要求 6 一致） |
| 不授权范围 | 不 refresh、不 upsert 业务数据、不写 Cache、不写 AuditLogger（`03_data_ud_query_audit`）、不写 QualitySummary、不动 cron/systemd、不动 `.env`、不建新角色、不动生产代码树 |

**与 §14.6 既有契约的关系**：本 §14.6.4 是 §14.6 DDL Gate 通用要求在 P3-A 上的**精确化与冻结**，不修改 §14.6 的 1-6 授权要求、不修改 §14.6 的 DDL 执行脚本示例（该示例与 DESIGN §6.2 一致）、不修改 §14.7 成功标准与 §14.8 停止条件的既有条文。

#### 14.6.bis PR-DDL-P3B 精确契约（B1-P3B 冻结）

> **授权状态**：**P3-A 与 P3-B 已冻结**（本 §14.6.bis 为 P3-B；§14.6.4 为 P3-A）。P3-C 的 PR-DDL 精确契约见 §14.6.ter。下游 Implement / Verify / Review 严格按本节冻结契约执行 P3-B 的 DDL。

**权威来源**：DDL 执行语义、rollback 脚本、audit 字段、失败矩阵、退出码的权威定义在 **DESIGN-03-014 §6.4.bis**（V0.14）。本节为 SPEC 层的契约引用与 Gate 集成，不重复完整定义——如本节与 DESIGN §6.4.bis 出现差异，以 DESIGN §6.4.bis 为准。

**PR-DDL-P3B 契约**：

| 维度 | 冻结值 |
|---|---|
| 前置条件 | (a) PR-3 verdict 为 `pass` 或 `conditional_pass`（Pascal 已审阅偏差）；(b) Pascal 已确认 SPEC-03-014 §3.2 schema 最终版；(c) §14.6 DDL Gate 授权要求 1-6 全部满足 |
| 集合 | 仅 `03_data_ud_stock_capital_flow`（库 `tradingagents`，主仓 `main` 本地工作树） |
| 索引 | 两条——`symbol_trade_date`（`{symbol:1, trade_date:-1}`）/ `trade_date`（`{trade_date:-1}`），全部 `background: true`（定义见 DESIGN §6.2，本节引用不重述） |
| 写入身份 | 复用现有 `MONGODB_USERNAME`（Phase 2 PortfolioMongoLoader 组件式构造连接语义；与 P3-A 同一账号） |
| 写入原子性 | **失败即停，不自动回滚**；preflight probe 命中目标集合 fail-stop（exit 2）；`createCollection` / `createIndex` 在目标已存在时 fail-stop（exit 4），由操作员手动评估 |
| rollback 脚本 | `/tmp/yquant-p3-ddl-p3b-20260725/rollback-p3b.js`（dropIndex 反向顺序 + dropCollection；不提交仓库；权威内容见 DESIGN §6.4.bis.1；`node --check` 必过） |
| audit 工件 | stdout + `/tmp/yquant-p3-ddl-p3b-20260725/audit-p3b.json`；字段 `{operation, collection, index, ts, exit_code, error, rollback_script_path}`（定义见 DESIGN §6.4.bis.2，collection 固定 `03_data_ud_stock_capital_flow`）；**不引入**新 audit 集合 |
| 退出码 | `0`=PASS（DDL 成功）；`2`=preflight target already exists；`3`=collection create fail；`4`=index create fail。退出码 1 不使用（与 §15.5.4 PR-1 conditional pass 语义分离）。退出码定义见 DESIGN §6.4.bis.4 |
| 停止条件 | 任一非 0 退出码即 fail-stop；**不自动回滚**、**不自动重试**；DDL 前必做独立 read-only probe（`list_collections` / `list_indexes`）确认目标不存在；是否运行 rollback-p3b.js 由操作员按 DESIGN §6.4.bis.3 失败矩阵的「operator action」列判断 |
| DDL 执行人 | Pascal 手动执行（或 Pascal 授权的 DevOps）；Agent 不直接执行 DDL（与 §14.6 DDL Gate 授权要求 6 一致） |
| 不授权范围 | 不 refresh、不 upsert 业务数据、不写 Cache、不写 AuditLogger（`03_data_ud_query_audit`）、不写 QualitySummary、不动 cron/systemd、不动 `.env`、不建新角色、不动生产代码树；P3-A / P3-C 集合（P3-A 已在位 / P3-C 未授权） |

**与 §14.6 既有契约的关系**：本 §14.6.bis 是 §14.6 DDL Gate 通用要求在 P3-B 上的**精确化与冻结**，不修改 §14.6 的 1-6 授权要求、不修改 §14.6 的 DDL 执行脚本示例（该示例与 DESIGN §6.2 一致）、不修改 §14.7 成功标准与 §14.8 停止条件的既有条文。与 §14.6.4（P3-A）平行结构、独立授权。

#### 14.6.ter PR-DDL-P3C 精确契约（B1-P3C 冻结）

> **授权状态**：**P3-A + P3-B + P3-C 已全部冻结**（本 §14.6.ter 为 P3-C；§14.6.4 为 P3-A；§14.6.bis 为 P3-B）。Phase 3 三子阶段 DDL 全部授权。下游 Implement / Verify / Review 严格按本节冻结契约执行 P3-C 的 DDL。

**权威来源**：DDL 执行语义、rollback 脚本、audit 字段、失败矩阵、退出码的权威定义在 **DESIGN-03-014 §6.4.ter**（V0.15）。本节为 SPEC 层的契约引用与 Gate 集成，不重复完整定义——如本节与 DESIGN §6.4.ter 出现差异，以 DESIGN §6.4.ter 为准。

**PR-DDL-P3C 契约**：

| 维度 | 冻结值 |
|---|---|
| 前置条件 | (a) PR-4 verdict 为 `pass` 或 `conditional_pass`（Pascal 已审阅偏差）；(b) Pascal 已确认 SPEC-03-014 §3.3 schema 最终版；(c) §14.6 DDL Gate 授权要求 1-6 全部满足 |
| 集合 | 仅 `03_data_ud_market_sentiment_snapshot`（库 `tradingagents`，主仓 `main` 本地工作树） |
| 索引 | 两条——`snapshot_date`（`{snapshot_date:-1}`）/ `snapshot_time`（`{snapshot_time:-1}`），全部 `background: true`（定义见 DESIGN §6.2，本节引用不重述） |
| 写入身份 | 复用现有 `MONGODB_USERNAME`（Phase 2 PortfolioMongoLoader 组件式构造连接语义；与 P3-A / P3-B 同一账号） |
| 写入原子性 | **失败即停，不自动回滚**；preflight probe 命中目标集合 fail-stop（exit 2）；`createCollection` / `createIndex` 在目标已存在时 fail-stop（exit 4），由操作员手动评估 |
| rollback 脚本 | `/tmp/yquant-p3-ddl-p3c-20260725/rollback-p3c.js`（dropIndex 反向顺序 + dropCollection；不提交仓库；权威内容见 DESIGN §6.4.ter.1；`node --check` 必过） |
| audit 工件 | stdout + `/tmp/yquant-p3-ddl-p3c-20260725/audit-p3c.json`；字段 `{operation, collection, index, ts, exit_code, error, rollback_script_path}`（定义见 DESIGN §6.4.ter.2，collection 固定 `03_data_ud_market_sentiment_snapshot`）；**不引入**新 audit 集合 |
| 退出码 | `0`=PASS（DDL 成功）；`2`=preflight target already exists；`3`=collection create fail；`4`=index create fail。退出码 1 不使用（与 §15.5.4 PR-1 conditional pass 语义分离）。退出码定义见 DESIGN §6.4.ter.4 |
| 停止条件 | 任一非 0 退出码即 fail-stop；**不自动回滚**、**不自动重试**；DDL 前必做独立 read-only probe（`list_collections` / `list_indexes`）确认目标不存在；是否运行 rollback-p3c.js 由操作员按 DESIGN §6.4.ter.3 失败矩阵的「operator action」列判断 |
| DDL 执行人 | Pascal 手动执行（或 Pascal 授权的 DevOps）；Agent 不直接执行 DDL（与 §14.6 DDL Gate 授权要求 6 一致） |
| 不授权范围 | 不 refresh、不 upsert 业务数据、不写 Cache、不写 AuditLogger（`03_data_ud_query_audit`）、不写 QualitySummary、不动 cron/systemd、不动 `.env`、不建新角色、不动生产代码树；P3-A / P3-B 集合（P3-A 与 P3-B 已在位） |

**与 §14.6 既有契约的关系**：本 §14.6.ter 是 §14.6 DDL Gate 通用要求在 P3-C 上的**精确化与冻结**，不修改 §14.6 的 1-6 授权要求、不修改 §14.6 的 DDL 执行脚本示例（该示例与 DESIGN §6.2 一致）、不修改 §14.7 成功标准与 §14.8 停止条件的既有条文。与 §14.6.4（P3-A）/ §14.6.bis（P3-B）平行结构、独立授权。

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

---

## P0 真实 Provider 离线可实现契约冻结

### P0.1 背景与目标

Phase 3 离线实现（T3 Implement）已在工作树中存在并通过 `792 passed`。但离线实现与真实 Provider 之间仍存在文档/代码漂移、Provider 映射缺失、持久化路径未实现、测试覆盖不足四类缺口。本 §P0 定义可在**不发起任何真实 API/Mongo 调用**前提下实施的真实 Provider 接入契约。

本节的精确状态矩阵、统一接口边界、逐 capability 验收项、P0/P1/P2 边界依赖和副作用矩阵与 RFC §P0 一致。所有真实调用声明为未来授权 smoke（P2）或 production activation（P1），禁止在 P0 离线 Implement/Verify 中触发。

### P0.2 六 Capability 精确状态矩阵

| Capability | 离线已验证 | AKShareProvider 注册 | Real fetch 实现 | Real persistence 实现 | Refresh 实现 | Live smoke 执行 |
|---|---|---|---|---|---|---|
| `sector.snapshot` | ✅ stub + 测试 PASS | ✅ P3-A stub | ❌ 未实现 | ❌ 未执行 | ❌ 未实现（三态 unauthorized） | ❌ B2 失败（SSLError） |
| `sector.ranking` | ✅ stub + 测试 PASS | ✅ P3-A stub | ❌ 未实现 | ❌ 未执行 | ❌ 未实现 | ❌ B2 失败（同 endpoint） |
| `flow.capital_flow_daily` | ✅ stub + 测试 PASS | ❌ 未注册 | ❌ 未实现（B2 成功但 `_EXPECTED_FLOW_FIELDS` 未对齐） | ❌ 未执行 | ❌ 未实现（injected-not-implemented） | ✅ B2 成功 |
| `flow.northbound_daily` | ✅ stub + 测试 PASS | ❌ 未注册 | ❌ 未实现（Pascal C: 恒 None） | ❌ 未执行 | ❌ fail-stop（永不写入） | ✅ B2 success 但语义不匹配 |
| `sentiment.market_snapshot` | ✅ 22-field canonical（from_dict/fixture/stub/test 已验证基线） | ❌ 未注册 | ❌ 未实现 | ❌ 未执行 | ❌ 未实现（injected-not-implemented） | ❌ B2 空返回 |
| `sentiment.limit_up_pool` | ✅ 同 market_snapshot（22-field canonical 已验证基线） | ❌ 未注册 | ❌ 未实现 | ❌ 未执行 | ❌ 未实现 | ❌ B2 空返回 |

状态语义同 RFC §P0.2。

### P0.3 真实 Provider 统一接口边界

任何真实 Provider 接入必须遵循以下四阶段管线：

```
Step 1: extract                 → AKShare/其他 Provider → pd.DataFrame/dict
Step 2: canonical mapping       → AKShare 字段 → domain object 字段
Step 3: validation/provenance   → canonical object 字段校验 + provenance 记录
Step 4: DataResult.source_trace → 四阶段结果封装为 source_trace 条目
```

**离线实现范围**（P0 允许，不会触发真实调用）：
- stub fetch → canonical mapping 的纯函数映射测试
- `from_dict()` 松弛映射覆盖所有字段
- `_EXPECTED_*_FIELDS`（STUB_COLUMNS）定义与 `providers/__init__.py` 孪生等价性测试
- Provider endpoint 选择逻辑的文档定义（不激活 endpoint）

**禁止实现范围**（P0 不允许）：
- ❌ 真实 `akshare.stock_xxx()` 调用
- ❌ `P3PersistenceWriter.upsert()` 真实 MongoDB 写入
- ❌ `CacheManager.put()` 真实写入
- ❌ `refresh_xxx()` 中的真实 fetch→upsert 路径
- ❌ 任何形式的外网 / API / MongoDB 网络连接

### P0.4 P3-A 映射验收项（PA-1 ~ PA-9）

| # | 验收项 | 验证方式 |
|---|---|---|
| PA-1 | `_EXPECTED_SECTOR_SNAPSHOT_FIELDS` 基于 AKShare `stock_board_industry_cons_em` 公开文档定义；含板块代码/名称/类型/日期/涨幅/涨跌家数/领涨股/换手率 | 静态检查 |
| PA-2 | `_EXPECTED_SECTOR_RANKING_FIELDS` 基于 `stock_board_industry_rank_em` 公开文档定义 | 静态检查 |
| PA-3 | sector.snapshot 空返回 → `DataResult.success(data=None/is_empty, provider="akshare")`；source_trace 不含 "ud_materialized(ok)" | stub 测试 |
| PA-4 | sector.ranking 空返回 → `DataResult.success(data=[], provider="akshare")` | stub 测试 |
| PA-5 | 字段漂移错误处理：unmapped 额外字段静默忽略；缺失字段填 None/默认值，不抛 KeyError | `from_dict` 测试 |
| PA-6 | 按 `snapshot_date` 降序排序 | stub fixture 断言 |
| PA-7 | `_EXPECTED_SECTOR_*_FIELDS` 与 STUB_COLUMNS 孪生等价 | 孪生等价性测试 |
| PA-8 | STUB_COLUMNS 覆盖 industry + concept 两种板块类型 | fixture 覆盖 ≥2 条 |
| PA-9 | AKShare Provider 字段映射仅在 STUB_COLUMNS 中定义；不创建真实 endpoint skeleton | 静态 grep |

约束同 RFC §P0.4：不得臆定未在公开文档中出现过的字段名；空 ≠ 失败。

### P0.5 P3-B 映射验收项（PB-1 ~ PB-10）

| # | 验收项 | 验证方式 |
|---|---|---|
| PB-1 | `_EXPECTED_FLOW_FIELDS` 基于 B2 冻结证据 + `stock_individual_fund_flow` 公开文档定义；≥10 字段含 symbol/market/trade_date/main_net_inflow/super_large_net_inflow/large_net_inflow/medium_net_inflow/small_net_inflow/main_net_inflow_ratio/margin_balance | 静态检查 |
| PB-2 | `_EXPECTED_NORTHBOUND_FIELDS` 三字段恒 None：northbound_net_inflow / northbound_hold_shares / northbound_hold_ratio | 静态检查（Pascal C） |
| PB-3 | 资金流符号约定：所有 `*_net_inflow` 正=净流入、负=净流出 | fixture + 单元测试 |
| PB-4 | 非沪深港通标的 northbound 字段为 None | stub fixture 断言 |
| PB-5 | `flow_stub._build_default_payload()` Record A/C northbound 字段均为 None | Python 断言：4 条记录全部通过 |
| PB-6 | `StubFlowProvider.fetch("flow", "northbound_daily")` 过滤 northbound 字段为 None | stub 测试 |
| PB-7 | `FlowService(p3_writer=Mock())` → `refresh_capital_flow()` 抛 `NotImplementedError`；不 upsert | pytest.raises + assert_not_called |
| PB-8 | `FlowService` 有显式 northbound fail path（`_is_northbound_refresh_disallowed()` 返回 True） | 静态检查 |
| PB-9 | 空返回语义：空 DataFrame → `DataResult.success(data=[], provider="akshare")` | stub 测试 |
| PB-10 | `_EXPECTED_*_FIELDS` 与 STUB_COLUMNS 孪生等价 | 孪生等价性测试 |

**绝对禁止**：
- ❌ 将北向持股历史（`持股数量`/`持股市值`/`今日增持资金`）别名映射为 `northbound_net_inflow`。
- ❌ 在 `CapitalFlowRecord.northbound_net_inflow` 中填入持股语义的值。
- ❌ 在映射文档中把「北向持股历史」表述为「北向净流入」。
- ❌ 引入 A/B 选项的 endpoint skeleton。

### P0.6 P3-C 映射验收项（PC-1 ~ PC-11）

| # | 验收项 | 验证方式 |
|---|---|---|
| PC-1 | `_EXPECTED_SENTIMENT_FIELDS` 基于 AKShare `stock_market_fund_flow` + `stock_zt_pool_em` 公开文档定义；22-field canonical 契约为唯一基准 | 静态检查 |
| PC-2 | `_EXPECTED_LIMIT_UP_FIELDS` 基于 `stock_zt_pool_em` 公开文档定义 | 静态检查 |
| PC-3 | `market_temperature` 在 fixture + stub 中均为 None | fixture 断言 |
| PC-4 | `northbound_net_flow` 在 fixture + stub 中均为 None | fixture 断言 |
| PC-5 | 22-field `from_dict()` 覆盖全部 22 字段，无 KeyError | 单元测试 |
| PC-6 | 空返回 → `DataResult.success(data=None, provider="akshare")`；verdict=fail（X2 保守） | stub 测试 |
| PC-7 | `get_market_sentiment()` 返回 `MarketSentimentSnapshot`（22-field canonical） | Python 断言 |
| PC-8 | `get_limit_up_pool()` 返回 `list[dict]`（symbol/reason/days） | Python 断言 |
| PC-9 | `refresh_market_sentiment_snapshot()` 三态守卫：p3_writer=None→ProviderUnavailableError；injected→NotImplementedError | pytest.raises |
| PC-10 | `_EXPECTED_*_FIELDS` 与 STUB_COLUMNS 孪生等价 | 孪生等价性测试 |
| PC-11 | freshness `sentiment` vs `market_sentiment` 命名冲突不擅自裁定 | 仅披露 |

**绝对禁止**：
- ❌ 虚构 `market_temperature` 值。
- ❌ 虚构 `northbound_net_flow` 值。
- ❌ 基于 superseded 10 字段模型定义 fixture/expected 字段集。
- ❌ 擅自裁定 `sentiment` vs `market_sentiment` freshness 命名冲突。

### P0.7 P0 vs P1 vs P2 边界

| 阶段 | 名称 | 包含操作 | 授权模式 | 依赖 |
|---|---|---|---|---|
| **P0** | 离线可实现契约 | 静态代码/fixture/mock、孪生等价性测试、refresh 三态守卫 stub、`_EXPECTED_*_FIELDS` 定义、from_dict 松弛映射、离线端到端 smoke | 当前 Kanban 链 | 无 |
| **P1** | 持久化与刷新 | 真实 Mongo DDL/DML、refresh happy-path、CacheManager.put() 激活 | 逐 sub-phase Pascal Gate（G-A/B/C-*） | P0 通过 |
| **P2** | 真实 Smoke & Canary | PR-0~4、PR-DDL-*、PR-CANARY-* | 逐 Gate Pascal 授权 | P1 完成 |

### P0.8 完全副作用矩阵

| 操作 | P0 权限 | P1 权限 | P2 权限 | 风险 |
|---|---|---|---|---|
| 静态代码/fixture/mock | ✅ | ✅ | ✅ | 无 |
| `_EXPECTED_*_FIELDS` / STUB_COLUMNS | ✅ | ✅ | ✅ | 低 |
| Stub Provider 返回 fixture | ✅ | ✅ | ✅ | 无 |
| 真实 AKShare API 调用 | ❌ 禁止 | ❌ 禁止 | ✅ PR-smoke | 低 |
| 真实 Mongo ping/listCollections | ❌ 禁止 | ❌ 禁止 | ✅ PR-1 | 低 |
| 真实 Mongo DDL | ❌ 禁止 | ❌ 禁止 | ✅ PR-DDL-* | 中 |
| 真实 Mongo DML/upsert | ❌ 禁止 | ✅ G-*-2 后 | ✅ PR-CANARY | 中 |
| CacheManager.put() 真实写入 | ❌ 禁止 | ✅ refresh 激活后 | ✅ | 低 |
| refresh_xxx() happy-path | ❌ 禁止 | ✅ G-*-2 后 | ✅ | 中 |
| 任意 cron/systemd/调度 | ❌ 禁止 | ❌ 禁止 | ❌ 禁止（Phase 5） | 高 |

### P0.9 旧 Checkbox 状态纠正

同 RFC §P0.9 的纠正表。核心原则：

1. 旧 checkbox 的「未勾选」不自动等于「未实现」——部分项在离线实现中已落实。
2. 所有「已勾选」必须能追溯到可执行的代码/测试/文档证据。
3. 「真实 Provider 接入完成」「真实 MongoDB 写入完成」「真实 smoke 完成」在任何离线阶段 checkbox 中均不得声称已完成。
4. 后续 Implementation 验收引用本节的「可审计现状」，不再引用旧 checkbox 原始状态。

### P0.10 Developer Allowlist（本 §P0 约束）

与 RFC §13.4.5.10 Developer allowlist 表一致，增加以下 P0 特定约束：

| 路径 | 允许操作 | 约束 |
|---|---|---|
| `providers/_stub_columns.py` | 追加 P3-B/P3-C 的 `_EXPECTED_*_FIELDS` / STUB_COLUMNS 定义 | 与 `providers/__init__.py` 孪生等价 |
| `models/domain/sentiment.py` | 22 字段 canonical `from_dict()` 实现（frozen=False） | 不动 10 字段 superseded 实现；不删旧字段 |
| `services/sentiment_service.py` | 22 字段 canonical 类型引用更新 | 不动 read path 注册逻辑 |
| `services/flow_service.py` | `_is_refresh_authorized()` + `_is_northbound_refresh_disallowed()` 守卫 | refresh happy-path 仍禁止 |
| `providers/flow_stub.py` | `_build_default_payload()` northbound → None 修复；`fetch()` northbound 投影过滤 | 不动其他字段 |
| `tests/fixtures/` | P3-B/P3-C fixture 更新 | 覆盖正常 + 极端行情场景 |

| **禁止修改**：`router.py`、`client.py`、`akshare.py`（P0 不注册真实 endpoint）、`adapters/p3_persistence_writer.py`（P0 不修改写入路径）、任何 `.env`/配置/依赖。

---

## P1 受控 Mongo 物化与显式 refresh 的零副作用契约

### P1.1 背景与作用域

P0 已冻结离线可实现契约（stub Provider、`_EXPECTED_*_FIELDS`、from_dict 松弛映射、孪生等价性测试、refresh 三态守卫 stub）。P1 在 P0 基础上新增受控持久化与显式刷新的代码实现——全部在 mongomock/fake 环境中验证，不触发真实 I/O。

**P1 In Scope**：
- `P3PersistenceWriter.get()` 代码实现（mongomock 验证）
- `P3PersistenceWriter.upsert()` 业务唯一键 upsert 实现（mongomock 验证）
- `CacheManager.put()` 调用代码路径（mock 验证）
- `refresh_xxx()` happy-path 完整编排（mock Provider + mongomock 验证）
- `DataRouter._try_materialized()` capability 参数 + `P3PersistenceWriter` 注入引用
- `_is_refresh_authorized()` toggle 逻辑实现（通过 fixture 配置测试两种状态）
- `northbound_daily` refresh fail-path 守卫（静态验证）
- 对应的单元测试 & fixture 更新

**P1 Out of Scope**：
- ❌ 任何真实 MongoDB 连接、DDL、DML
- ❌ 任何真实 AKShare API 调用
- ❌ G-A/B/C-2 Refresh Gate 的真实激活（属独立后续卡）
- ❌ PR-DDL-* 的 DDL 执行（属 P2）
- ❌ PR-0~PR-4 真实 smoke（属 P2）
- ❌ cron/systemd/调度（属 Phase 5）

### P1.2 P1 vs P0 vs P2 边界依赖更新

| 阶段 | 包含操作 | 授权模式 | 依赖 |
|---|---|---|---|
| **P0**（已完成） | 离线可实现契约（stub/`_EXPECTED_*_FIELDS`/from_dict/孪生等价性/refresh 三态守卫 stub） | 已纳入当前 Kanban 链 | 无 |
| **P1**（本阶段） | 受控物化与显式 refresh 代码路径；P3PersistenceWriter/refresh happy-path/Cache 写入/零 I/O 验证 | 纳入当前 Kanban 链（P1 T1→T2→T3） | P0 全部验收通过 |
| **P1.5**（生产激活后续卡） | G-A/B/C-2 Gate 激活：`_is_refresh_authorized()`→True + refresh happy-path 生产启用 | 逐子阶段 Pascal Gate（G-A/B/C-2） | P1 通过 + Pascal 显式确认 |
| **P2** | 真实 Smoke 与 Canary（PR-0~PR-4、PR-DDL-*、PR-CANARY-*） | 逐 Gate Pascal 授权 | P1.5 完成 |

### P1.3 Capability 级别 P1 状态矩阵

| Capability | 实现状态 | Mongomock 测试 | 生产激活 |
|---|---|---|---|
| `sector.snapshot` refresh happy-path | ✅ P1 实现 | ✅ mock Provider + mongomock | ❌ 需 G-A-2 Gate |
| `sector.ranking` refresh happy-path | ✅ P1 实现 | ✅ mock Provider + mongomock | ❌ 需 G-A-2 Gate |
| `flow.capital_flow_daily` refresh happy-path | ✅ P1 实现 | ✅ mock Provider + mongomock | ❌ 需 G-B-2 Gate |
| `flow.northbound_daily` refresh fail-path | ✅ P1 fail-stop（永不激活） | ✅ 静态检查 + pytest | ❌ 永远不激活（Pascal C） |
| `sentiment.market_snapshot` refresh happy-path | ✅ P1 实现 | ✅ mock Provider + mongomock | ❌ 需 G-C-2 Gate |
| `sentiment.limit_up_pool` refresh happy-path | ✅ P1 实现 | ✅ mock Provider + mongomock | ❌ 需 G-C-2 Gate |

### P1.4 集合/文档语义与 upsert 规则

三个物化集合在生产中位于 MongoDB `tradingagents` 库，通过前缀 `03_data_ud_` 隔离 ownership。P1 实现针对 mongomock 环境验证。

| 集合 | 唯一键 upsert 规则 | 约束 |
|---|---|---|
| `03_data_ud_market_sector_snapshot` | `{market, sector_code, snapshot_date}` → `update_one(filter, {"$set": doc}, upsert=True)` | 同一键的重复写入覆盖，不保留历史版本 |
| `03_data_ud_stock_capital_flow` | `{market, symbol, trade_date}` → 同上 | `northbound_daily` 永不进入 upsert 路径 |
| `03_data_ud_market_sentiment_snapshot` | `{market, snapshot_date, snapshot_time}` → 同上 | 22 字段 canonical 契约为唯一 schema；禁止写入旧 10 字段模型 |

**关键约束**：P3PersistenceWriter 使用自定义业务唯一键（不是 LocalMongoAdapter 的 `materialized_key`）。已在 DESIGN-03-014 §0.4 中冻结。

### P1.5 Refresh 契约

#### P1.5.1 三态守卫

P0 已实现的三态守卫保持。P1 新增完整 refresh happy-path：

| 守卫状态 | 条件 | 行为 | P1 测试验证 |
|---|---|---|---|
| `p3_writer=None` | P3PersistenceWriter 未注入 | `ProviderUnavailableError` | pytest.raises（同 P0） |
| `injected-not-implemented` | p3_writer 存在但 `_is_refresh_authorized()=False` | `NotImplementedError` | pytest.raises（同 P0） |
| **authorized**（P1 新增） | `_is_refresh_authorized()=True` | `fetch()` → canonical mapping → `P3PersistenceWriter.upsert()` → `CacheManager.put()` → 返回 `PersistenceResult` | mock Provider + mongomock 全流程验证 |

#### P1.5.2 Refresh happy-path 伪代码契约

```python
def refresh_xxx(self) -> PersistenceResult:
    # 三态守卫
    if self.p3_writer is None:
        raise ProviderUnavailableError("P3 writer not injected")
    if not self._is_refresh_authorized():
        raise NotImplementedError("Refresh not yet authorized")

    # Step 1: fetch from Provider (mock only in P1)
    raw_data = self.provider.fetch(domain, capability, params)
    # raw_data is pd.DataFrame (mock/fixture in P1)

    if raw_data.empty:
        return PersistenceResult(skipped=0, reason="empty_response")

    # Step 2: canonical mapping
    records = [self._to_canonical(row) for _, row in raw_data.iterrows()]

    # Step 3: upsert to P3PersistenceWriter (mongomock in P1)
    outcome = self.p3_writer.upsert(
        collection=COLLECTION,
        records=[asdict(r) for r in records],
        unique_key=UNIQUE_KEY
    )

    # Step 4: write to CacheManager (mock in P1)
    if outcome.persisted > 0:
        try:
            self.cache_manager.put(cache_key, records)
        except Exception:
            pass  # catch-and-log, don't block refresh

    return PersistenceResult(
        status="ok" if outcome.failed == 0 else "partial",
        capability=capability,
        collection=COLLECTION,
        persisted=outcome.persisted,
        failed=outcome.failed,
        skipped=0,
        reason=None if outcome.failed == 0 else f"{outcome.failed} records failed",
        writer_outcome=outcome
    )
```

#### P1.5.2.bis Cache Key 规范与失败行为

P1 离线 refresh happy-path 中 Step 4 **必须**调用 `CacheManager.put()`（通过 unittest.mock 验证）。
每 service 的 cache key 规范如下：

| Service | Capability | cache_key 格式 | 示例 |
|---------|-----------|----------------|------|
| SectorService | `sector.snapshot` | `"sector:snapshot:{sector_code}:{snapshot_date}"` | `"sector:snapshot:BK0489:2026-07-30"` |
| SectorService | `sector.ranking` | `"sector:ranking:{snapshot_date}"` | `"sector:ranking:2026-07-30"` |
| FlowService | `flow.capital_flow_daily` | `"flow:capital_flow:{symbol}:{trade_date}"` | `"flow:capital_flow:600519:2026-07-30"` |
| SentimentService | `sentiment.market_snapshot` | `"sentiment:market_snapshot:{snapshot_date}"` | `"sentiment:market_snapshot:2026-07-30"` |
| SentimentService | `sentiment.limit_up_pool` | `"sentiment:limit_up_pool:{snapshot_date}"` | `"sentiment:limit_up_pool:2026-07-30"` |

**失败行为**（与 §P1.5.2 Step 4 catch-and-log 一致）：
- `CacheManager.put()` 抛异常时不阻断 refresh 主流程。
- refresh 仍然返回 `PersistenceResult(status="ok", ...)`（不因 cache 写入失败降级）。
- `CacheManager.put()` 接收 `(cache_key, records)`，`records` 为 step 3 upsert 的 `list[dict]`。

**读路径无隐式写约束**（与 §P1.6 一致）：
- 标准 `DataRouter.query()` 或 `UnifiedDataClient.get_*()` 方法绝不调用 `CacheManager.put()`。
- Cache 写入**仅**发生在显式 `refresh_xxx()` 方法的 Step 4。

**Developer allowlist 追加约束**（与 §P1.11 互补）：
- 允许文件：`services/sector_service.py`、`services/flow_service.py`、`services/sentiment_service.py`。
- 这三个文件的 refresh happy-path **必须**包含 Step 4 `CacheManager.put()` 调用。
- 禁止在 `cache_manager.py`、`router.py`、`client.py`、`providers/`、`adapters/` 中添加 Cache 写入。

#### P1.5.3 Northbound fail-path 契约

```python
def refresh_northbound_flow(self, ...) -> PersistenceResult:
    """北向资金 refresh 路径。

    始终 fail-stop。
    不读取真实 AKShare endpoint、不 upsert。
    """
    return PersistenceResult(
        status="skipped",
        capability="flow.northbound_daily",
        collection="03_data_ud_stock_capital_flow",
        persisted=0,
        failed=0,
        skipped=0,
        reason="northbound_refresh_disallowed (Pascal C)",
        writer_outcome=None
    )
```

**测试验证**：
- `refresh_capital_flow()` 在 authorized 态时写入正确的集合和键。
- `refresh_northbound_flow()` 始终返回 skipped。
- `_is_northbound_refresh_disallowed()` 返回 True。

### P1.6 Internal-first Read 契约

`DataRouter.query()` 的 internal-first 读取路径保持不变。P1 实现以下代码路径：

```python
# Router._try_materialized() 在 P3 capability 上
def _try_materialized(self, security_id, domain, operation, params):
    # 仅 P3 capability 走 P3PersistenceWriter
    if self._is_p3_capability(domain, operation):
        if self.p3_writer is None:
            return None  # 降级到下一层
        collection = self._p3_collection_for(domain, operation)
        filter = self._p3_filter_for(security_id, domain, operation, params)
        doc = self.p3_writer.get(collection, filter)
        return doc
    # 非 P3 capability 走 LocalMongoAdapter
    return super()._try_materialized(...)
```

> **实现约束**：三个 helper 方法 `_is_p3_capability()`、`_p3_collection_for()`、`_p3_filter_for()`
> 是 canonical 接口（不可消除）。其内部实现可使用
> `P3_COLLECTION_BY_CAPABILITY`-style dict 作为底层数据存储（O(1) lookup），
> 但 **必须**通过 helper 方法间接调用，不允许在 `_try_materialized()` 中直接引用 dict。
> Helper 提供明确的测试 seam 和未来 P2/P3 扩展点。

**测试验证**：
- P3 capability 在 mongomock 中命中时返回正确的文档。
- P3 capability 在 mongomock 中未命中时返回 None 并降级到下一层。
- P3 capability 在 source_trace 中添加 `"ud_materialized(ok)"`（仅当 `_is_refresh_authorized()=True` 且已写入）。
- 非 P3 capability 不受影响。

### P1.7 零 I/O 验证约束（P1 Implement/Verify）

| 验证项目 | 方法 | 禁止 |
|---|---|---|
| P3PersistenceWriter.get() | mongomock | 真实 MongoDB |
| P3PersistenceWriter.upsert() | mongomock | 真实 MongoDB |
| CacheManager.put() | unittest.mock | 真实 Cache 后端 |
| refresh happy-path 编排 | mock Provider + mongomock | 真实 AKShare / MongoDB |
| `_try_materialized()` | mongomock | 真实 MongoDB |
| DDL createCollection/index | mock（仅验证脚本存在性） | 真实 MongoDB DDL |
| 凭据读取 | 不验证 | 读取 `.env` / 凭据文件 |
| 端到端 smoke | 全 mock 环境 | 任何外网连接 |

任何真实 I/O 的测试必须标注 `@pytest.mark.skip(reason="仅 P2 可执行")` 或等效守卫。

### P1.8 副作用矩阵（仅 P1 离线阶段）

| 操作 | P1 代码路径 | P1 验证允许 | 生产激活授权 |
|---|---|---|---|
| P3PersistenceWriter.get() | 实现 | ✅ mongomock | 无需授权（仅 mock） |
| P3PersistenceWriter.upsert() | 实现 | ✅ mongomock | G-A/B/C-2 Gate |
| CacheManager.put() 调用 | 实现 | ✅ unittest.mock | refresh 激活后 |
| refresh_xxx() happy-path | 实现 | ✅ mock Provider + mongomock | G-A/B/C-2 Gate |
| `_is_refresh_authorized()` toggle | 实现 | ✅ fixture 两种状态测试 | G-A/B/C-2 Gate |
| `DataRouter._try_materialized()` 扩展 | 实现 | ✅ mongomock | 无需授权（仅 mock） |
| DDL 代码（createCollection/index） | 可写 | ❌ 不执行 | PR-DDL-*（P2） |
| 真实 AKShare API | ❌ 不实现 | N/A | PR-2/3/4（P2） |
| 真实 MongoDB DML | ❌ 不实现 | N/A | PR-CANARY（P2） |
| cron/systemd/调度 | ❌ 不实现 | N/A | Phase 5 |

### P1.9 授权关口

本表与 RFC §P1.7 一致。

| Gate | 含义 | P1 阶段状态 |
|---|---|---|
| G-A/B/C-1 DDL Gate | `createCollection`/`createIndex` 授权 | ✅ B1-P3A/B/C 已全部冻结 |
| G-A/B/C-2 Refresh Gate | `_is_refresh_authorized()`→True + refresh 生产激活 | ❌ P1 中不激活 |
| G-A/B/C-3 Canary Gate | 手动 canary 调度授权 | ❌ 不属 P1 范围 |

### P1.10 P1 验收准则

1. `P3PersistenceWriter.upsert()` 在 mongomock 中使用业务唯一键 upsert 正确集合，写入后 `get()` 可正确读取。
2. `refresh_xxx()` 全流程（mock Provider → mongomock upsert → Cache mock）在 authorized 态 PASS；在 unauthorized 态抛出 `NotImplementedError`。
3. `northbound_daily` refresh 路径始终返回 skipped（`_is_northbound_refresh_disallowed()=True`）。
4. `DataRouter._try_materialized()` 在 P3 capability 上通过 mongomock 返回正确的物化数据，source_trace 格式与 RFC §P1.5.2 一致。
5. 全部 P0 验收标准（PA-1~PA-9、PB-1~PB-10、PC-1~PC-11）在 P1 代码变更后继续 PASS。
6. 零真实 I/O：pytest 收集的所有测试不产生外部网络调用或真实文件写入（通过 socket/syscall mock 在 CI 中验证）。
7. 每个 service 的 refresh happy-path 在 authorized 态时 Step 4 的 `CacheManager.put()` 调用通过 unittest.mock 验证（调用计数 ≥1、参数 cache_key 格式符合 §P1.5.2.bis）。
8. `git diff --check` 无冲突标记；`git diff --name-status` 仅显示 RFC 与 SPEC 两份文档的改动。

### P1.11 Developer Allowlist

以下文件允许在 P1 Implement 阶段修改。任何不在列表中的文件改动视为越界。

| 路径 | 允许操作 | 约束 |
|---|---|---|
| `adapters/p3_persistence_writer.py` | 补充 upsert/get 实现；补充 mongomock 兼容性 | 保持 `_assert_fake_db` 守卫；不引入真实 pymongo 连接路径 |
| `services/sector_service.py` | `refresh_sector_snapshot()` / `refresh_sector_ranking()` happy-path 实现（**必须**包含 Step 4 CacheManager.put()） | 三态守卫不变；northbound_ranking 不写入 |
| `services/flow_service.py` | `refresh_capital_flow()` happy-path 实现（**必须**包含 Step 4 CacheManager.put()）；`_is_refresh_authorized()` toggle 实现；`_is_northbound_refresh_disallowed()` 实现 | northbound refresh 始终 fail-stop |
| `services/sentiment_service.py` | `refresh_market_sentiment_snapshot()` / `refresh_limit_up_pool()` happy-path 实现（**必须**包含 Step 4 CacheManager.put()） | 22 字段 canonical 契约为唯一写入 schema |
| `router.py` | `_try_materialized()` 追加 capability 参数 + P3PersistenceWriter 注入引用 | 不影响非 P3 capability 路径；不改变 Step 4 自动 `_materialize()` 行为 |
| `client.py` | 无新增修改（在 P0 范围外） | 保持现有 5 个 lazy service 属性不变 |
| `cache_manager.py` | 无新增修改 | 保持现有 catch-and-log 设计 |
| `tests/` | P1 新增测试：refresh happy-path / mongomock 物化 / toggle 状态 / northbound fail-path | 零真实 I/O；不得调用真实 AKShare/MongoDB |

**禁止修改**：
- ❌ `models/domain/*`（P0 已冻结；P1 不修改 schema）
- ❌ `providers/akshare.py`（真实 endpoint 注册属 P2）
- ❌ `providers/_stub_columns.py` / `providers/__init__.py`（P0 已冻结 expected 字段集）
- ❌ `freshness.py`（PC-11 命名冲突冻结）
- ❌ 任何 `.env`、config、requirements、SKILL.md、README
