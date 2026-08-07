# SPEC-03-014：Unified Data Phase 3 — 重要持久化扩展契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-20 |
| 最后更新 | 2026-08-07（**V0.35（2026-08-07，事实归档：§R3.3.bis.1 2026-08-07 受控直连诊断 fail-stop 事实归档）**：本卡为 V0.34 §R3.3.bis 冻结契约下的"已发生事实"事实归档，**不改 §R3.3.bis 任何冻结契约条款**；新增 §R3.3.bis.1 子节记录 2026-08-07 受控直连诊断 fail-stop（一次性、不动 Design/代码/服务/网关；诊断脚本 `/tmp/r3_diag_minimal.py` + 报告 `/tmp/yquant-g-cf-live-r3-diag-79f89ae8/` sha256=d087fadcf25a8e7ba9ecc8b9c46133be3da2ee4580db98f18de1a169d633f862 2417B；connectivity=error / error_class=ConnectionError / exception_chain 三层 RemoteDisconnected；`effective_http_timeout_seconds=null` 未注入 10s；零 retry/fallback/Mongo/DDL/DML/Git/服务；不主张 R3 通过、四 Gate 全过、R1/R2 翻案、扩展 P3-A/name_em/cons_em/OQ-11/OQ-11B 既有语义；关联 Kanban 卡 `t_73e26ca7` `t_55ebd64b` 已挂 evidence comment 并显式 frozen-per-Pascal-2026-08-05-scope-narrowing，重启 R3 完整版需显式 unblock + 新建 replacement 链）；V0.34 §R3.3.bis R1/R2 历史事实保持准确不改写；RFC/DESIGN 同步升级 RFC-03-014 V0.34→V0.35 / DESIGN-03-014 V0.37→V0.38 镜像同一子节。V0.34（2026-08-05，G-CF-LIVE-R3 受控诊断契约新增）**：Pascal 明确授权 R3 最终单次 live-read（本卡仅写入契约、未执行）——新增 §R3.3.bis「G-CF-LIVE-R3：AKShare 直连与真实 HTTP timeout 受控诊断」：唯一 endpoint `stock_individual_fund_flow(stock='600519', market='sh')`、唯一 600519/CN、candidate date 2026-08-04（仅报告元数据）；direct transport 仅子进程临时清空 `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`、`NO_PROXY` 仅本机最小默认值，不改 shell profile/.env/系统/服务/网关；调用预算至多 1 次逻辑 Provider 调用、真实 HTTP request timeout=10s、零 retry/零 fallback/零替代 endpoint；零 Mongo/cache/refresh/upsert/DDL/DML/Git 写/服务变更；DNS/TCP/TLS/HTTP/timeout/schema 异常立即 fail-stop 并保留脱敏异常层级（异常类、message 摘要、cause/urllib3 子类）、不得重放本 Gate；临时报告 `/tmp/yquant-g-cf-live-r3-20260804-<run-id>/`（目录 0700、YAML 0600，账本字段 provider_attempts/actual_calls/retry/fallback/mongo/write=0/direct_transport/effective_http_timeout_seconds）；不产生生产结论、不替代四 Gate 链；rollback 仅撤销未来 R3 代码路径、不回滚历史报告/数据；R1/R2 历史事实保持准确（均为 `ConnectionError`、经继承代理环境、`DEFAULT_TIMEOUT_SECONDS=3` 未传至 AKShare 1.17.54 内部 `requests.get`）。V0.31 P3-A read-path 结果词汇三态统一仲裁（P0 Contract Arbitration，对应 RFC-03-014 V0.31 / DESIGN-03-014 V0.35）：§R2.2 P3-A 盘后/历史 read-path 允许的最终状态由旧双态 `production-read-path-validated` / `read-path-unavailable-by-design` 并入 R2 唯一三态——成功态唯一映射 `production-validated`（仅 read-path scope，≠ 实时 Provider 验证，仅能由未来获授权且实际执行、独立验证的 G-R2-1 census 产生，本文档裁定不产生任何生产结论）；不可用态唯一映射 `provider-unavailable-frozen`；schema drift / 认证失败 / 越界写入 / Verify 未通过 = 非结论 fail-stop（不落三态）；`intentionally-unavailable` 对 P3-A read-path 不适用；禁止杜撰第四/第五状态。**V0.32（2026-08-05，P3-B S1 独立重建）**：新增 §R3「P3-B 真实资金流生产验证与受控物化契约」——从 V0.31 基线独立重建（此前未提交的 SPEC V0.32 草稿已被工作树 `git restore`/checkout 类动作整体回退，本卡不依赖历史 worker summary 宣称恢复成功）；唯一真实目标 `flow.capital_flow_daily` → `stock_individual_fund_flow`；`flow.northbound_daily` 恒 `intentionally-unavailable`/None fail-stop（禁 `stock_hsgt_individual_em`/endpoint skeleton/DDL/canary/验收）；四 Gate 严格串行且逐个 Pascal 授权——G-CF-LIVE（零 Mongo live-read，600519、≤3 completed dates、≤3 calls、≥1s 间隔、3s 超时、零写、失败冻结）→ G-CF-DDL（唯一 `tradingagents.03_data_ud_stock_capital_flow` + 两索引，权威契约 §14.6.bis / DESIGN §6.4.bis）→ G-CF-CANARY（600519 × 一个 completed date × ≤1 doc）→ G-CF-POST（独立只读验收）；completed-date 复用 `skills.infra.date_utils` / `CompletedSessionPolicy` 契约，OQ-11 保持独立子链；生产结论仅能由四 Gate 全部实际执行 + 独立 Verify 产生，本卡零真实动作。**V0.33（2026-08-05，P0 阈值纠正同步）**：RFC-03-014 V0.33 P0 阈值纠正后同步——G-CF-LIVE 字段映射停止条件由旧 `>50% 字段名不匹配` 同步为 `字段映射匹配率 <70% fail-stop / ≥70% 才可通过`（对齐 `MATCH_RATIO_CONDITIONAL=0.70`，唯一阈值输入，见 RFC V0.33 §R3.10 / DESIGN §15.6.2 / §R2.4 G-R2-2）；§R3.3 / §R3.9 / §R3.10 与 §14.8 停止条件表字段映射行、§11 OQ-9 同源表述一并同步（旧 >50% 表述废弃）。详见版本历史 V0.32 / V0.33 条目；保留 V0.31 及更早全部条目。） |
| 版本号 | V0.36 |
| 来源 RFC | RFC-03-014（Phase 3 持久化扩展，V0.36） |
| 关联 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-011（Phase 2 质量与审计治理）、RFC-03-013（Phase 1E 情绪最小切片） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约基线）、SPEC-03-008（Phase 1B-A 查询平面）、SPEC-03-013（Phase 1E 情绪最小切片） |
| 关联 Design | DESIGN-03-014（Phase 3 持久化扩展详细设计，V0.38） |
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
|  | V0.20 | 2026-08-02 | **F6 freshness canonical key 裁定同步**。Pascal 裁定冻结 `market_sentiment` 为 capability `sentiment.market_snapshot` 的唯一 canonical freshness domain key（TTL=3600），`sentiment_limit_up_pool` 为 capability `sentiment.limit_up_pool` 的唯一 canonical key（TTL=3600）；`sentiment` 不再是 freshness TTL key（仅 capability domain 前缀）。§4.4 旧行 `"sentiment": 3600` 替换为两个 canonical 行；§7 A-006、§P0.6 PC-11（含绝对禁止）、§P1.11 冻结项同步解除并指向 F6 契约。禁止双 key/alias/fallback 造成 freshness 漂移。权威可执行契约见 `SPEC-03-014-F6`，裁定见 `RFC-03-014-F6`。不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态。 | YQuant-Principal |
|  | V0.21 | 2026-08-03 | **P3-C 时间语义裁定同步**。Pascal 裁定 `sentiment.market_snapshot` 与 P3-C 相关 `sentiment.limit_up_pool` 当前目标为**已完成交易日 / 收盘后 / 可重放**；`snapshot_time` 当前实现/映射仅可落地 `close`，禁止 intraday snapshot；实时情绪路径（盘中实时）属未来独立 capability——需独立 Provider/字段契约/freshness/时间边界与新的用户授权，不得以本卡放行。使用 `stock_market_fund_flow()` 必须按其返回日线序列按目标 `trade_date/snapshot_date` 精确筛选（无 date 参数、`klt=101` 日线，不得写成接受指定日期的实时查询）；资金净流入不得映射 `total_turnover`。2026-08-03 受控单次 live-read 冻结（zt_pool 55 行 / dtgc 2 行 / fund_flow 单次 `ConnectionError`；boundary PASS、Provider evidence FAIL；预算耗尽，报告 `/tmp/yquant-p3c-live-read-20260803/report.json`，不得重跑），sentiment 两 capability 未注册、保持 offline stub/defer，局部池子端点非空不得夸大为可激活 Provider。§0、§2.1、§3.3、§4.2、§5.1、§P0.6、§14.4.5.3、§14.4.5.9 同步。不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态。 | YQuant-Principal |
|  | V0.22 | 2026-08-03 | **Design Gate REVISE closure（P3-C Principal Closure，对应 RFC/SPEC-03-014 V0.22 / DESIGN-03-014 V0.29）**。一次性闭合独立 Design Gate REVISE 的 2 MAJOR + 1 MINOR：① **EOD 验证执行契约**（§3.3 冻结）：唯一 validation owner = `MarketSentimentService` 公开入口（`get_market_sentiment_snapshot` / `get_limit_up_pool` / `refresh_market_sentiment_snapshot` / `refresh_limit_up_pool`）；注入最小只读 `CompletedSessionPolicy` 协议（方法签名冻结：`session_status(date: str) -> SessionStatus`，接受 canonical `YYYY-MM-DD`，经可注入 fake calendar + fake clock 判定已完成 A 股交易日；T3 禁止读真实日历/系统日期/网络）；public ingress 在 provider fetch / writer upsert / cache put 之前 fail-fast；错误类型/稳定 code/message 唯一（`SentimentSessionValidationError` + code `INVALID_DATE_FORMAT` / `INVALID_SNAPSHOT_TIME` / `NOT_TRADING_DAY` / `FUTURE_TRADING_DAY` / `SESSION_NOT_COMPLETED`）；snapshot_time 非 close 输入统一在 **service 层**处理（domain `from_dict` 保持宽松解析 seam）。② **`total_turnover` 强制 None**：domain `from_dict` 规范化（与 `northbound_net_flow` 恒 None 同构），默认 offline stub / canonical fixtures 全部 `None`，任意非 None 输入（含资金净流入映射）不得进入输出。③ **测试矩阵修正**：删除不存在的 `tests/test_market_sentiment.py` 引用，改为真实 `test_market_sentiment_22field.py`；基线按 Gate 证据 5 文件 98 passed + 22field 既有文件划分；T3 最小 allowlist 明确（§12.bis.1 更新：sentiment.py / sentiment_stub.py / sentiment_fixtures.py / sentiment_service.py / colocated tests 增补）。§3.3、§5.1、§7、§8.1、§8.2、§12.bis.1、§14.4.5.9 同步。不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态。 | YQuant-Principal |
| V0.23 | 2026-08-03 | **P3-C Principal Closure-2（closure-only 文档修订，对应 RFC-03-014 V0.23 / DESIGN-03-014 V0.30）**。独立 closure Verify `t_1761343d` verdict = **FAIL**（2 个未闭合 MAJOR），本卡一次性修订：① **`refresh_limit_up_pool` 可执行 EOD 契约**——服务签名冻结为 `refresh_limit_up_pool(trade_date: str, *, p3_writer=None, provider=None)`（§3.3 EOD-1 / EOD-3 / EOD-5、§5.1、§7 A-032、§8.1 同步）；本轮 refresh **不允许** `None`/latest 语义；`trade_date` 必须 canonical `YYYY-MM-DD`，由 `CompletedSessionPolicy` 在 provider fetch / writer upsert / cache put **之前**校验（5 个既有错误 code 的日期相关分支适用，无新增模糊 code）；happy path 将同一 canonical `trade_date` 传入 provider params 并用于 date-scoped cache key，**不得先 fetch 后推断日期**。② **唯一 7 文件 closure-only T3 allowlist**——新增 §12.bis.4「P3-C V0.22/V0.29 closure-only T3 allowlist」，路径集合与 RFC §5.3.5 / DESIGN-03-014 §8.3 逐项严格相同（`models/domain/sentiment.py` / `providers/sentiment_stub.py` / `tests/fixtures/sentiment_fixtures.py` / `services/sentiment_service.py` / `tests/test_market_sentiment_22field.py` / `tests/test_sentiment_service.py` / `tests/test_mapping_sentiment.py`），对本轮 T3 **优先于所有旧 Phase-3 总体迁移表**（含 §12.bis.1 旧 10 项表）；显式禁止 `providers/akshare.py`、provider registry/fallback、router、writer、Mongo、cache、client facade、refresh activation、网络、外部 provider、调度；§12.bis.1 中不在 7 项内的 P3-C 行标记 superseded / non-applicable；`refresh_limit_up_pool` 离线 service 签名/guard/test 属 T3，真实执行仍禁止。§3.3、§7、§8.1、§8.2、§12.bis.1、§12.bis.4 同步。不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态。 | YQuant-Principal |
| V0.24 | 2026-08-03 | **P3-C Scope Reconcile（用户授权，仅文档；对应 RFC-03-014 V0.24 / DESIGN-03-014 V0.31）**。Pascal 明确授权：维持 `refresh_limit_up_pool(trade_date: str, ...)` 已批准 EOD 契约，并将唯一 T3 allowlist 从 7 项**最小扩展至 8 项**——唯一新增 `skills/data/unified_data/tests/test_sentiment_limit_up_pool.py`（触发证据：旧 T3 retries exhausted；恢复验证实测 161 passed / 4 failed，其中 1 个失败位于未被允许修改的 `tests/test_sentiment_limit_up_pool.py:283`——新 mandatory `trade_date` 签名使该遗留测试 TypeError，表明测试 allowlist 漏项）。§12.bis.4 升级为「P3-C V0.24/V0.31 closure-only T3 allowlist」并逐项列出恰好 8 个路径；第 8 项唯一职责：更新既有 fake refresh / missing-writer regression 显式提供 canonical `trade_date` + 验证 mandatory-date 契约与 ProviderUnavailable/error behavior，不得引入任何 Provider/registry/router/writer/Mongo/cache/client/network/refresh activation/scheduling 文件；`test_sentiment_service.py` 继续负责 mandatory-date、稳定错误码和零副作用 spies；新增第 8 项不得成为扩大生产范围的依据。保留全部冻结项：offline stub/defer；AKShare sentiment 未注册、live-read 不重跑；`total_turnover=None`；OQ-10/OQ-11；F6 TTL/key；真实 refresh 仍禁止。不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态。 | YQuant-Principal |
| V0.25 | 2026-08-03 | **OQ-11 生产 CompletedSessionPolicy 可执行契约（Pascal 明确推进，仅文档；对应 RFC-03-014 V0.25）**。§3.3 新增 EOD-7 系列：① 唯一事实源 = `skills.infra.date_utils`（动态 `exchange_calendars.get_calendar('XSHG')`，实测 `exchange_calendars==4.13.2`、timezone `Asia/Shanghai`、`session_close` = UTC 07:00 = Shanghai 15:00），production policy 仅经正式 adapter/contract 消费，禁止复制清单/直连 provider 网络/以 `TRADING_DAYS_2026` 为真相，裸 `is_trading_day()` 不得为唯一判定；② 最小 public/internal 接口边界——现有 date_utils API 保持兼容，production-only adapter（`AShareCompletedSessionPolicy`）显式依赖注入 clock、禁止 `datetime.now()` 隐式读取，生产 composition root 才提供 real clock；canonical `YYYY-MM-DD` 严格性，禁止宽松 `YYYYMMDD` 静默通过 public 边界；③ 状态优先级/判定表与 fail-closed 映射（calendar 不可用/越界/clock 无时区/异常 → 明确不可判定/可映射错误，禁止 fallback 与误判 NOT_A_TRADING_DAY）；④ 可审计字段清单；⑤ 兼容四态 `SessionStatus` 与五稳定 code，internal adapter error 规定到 service 映射；⑥ 测试矩阵（fake calendar + fake timezone-aware clock，零 I/O）与 T2 provisional 文件 allowlist。§7 A-037、§11 OQ-11 同步标记已裁定。不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态。 | YQuant-Principal |
| V0.26 | 2026-08-04 | **OQ-11 生产注入 Gate 授权契约（Pascal 明确授权但尚未执行，仅文档；对应 RFC-03-014 V0.26）**。§3.3 新增 EOD-8 系列：① 授权边界仅含真实 XSHG calendar 与覆盖区间预检 / timezone-aware real clock 的 production composition root / fail-closed E2E 验证 / 服务重启后实际行为核验 / 零写入只读证明；不授权 Provider/Mongo/DDL-DML/cache put/refresh/canary/cron-systemd 长期调度/网关-webhook/Git/秘密。② composition root 候选与依赖方向：当前仓库无生产 root 事实（无 SystemClock 实现、无 composition 模块、无 sentiment 生产进程入口）；候选（T2 裁定，不得超出）`services/composition.py`（最小装配模块）/ `services/__init__.py` 扩展 / `client.py` 构造 / `scripts/unified_data/` 新增 production CLI（当前无进程入口）；依赖方向唯一 root → `AShareCompletedSessionPolicy(clock=SystemClock)` → `date_utils` strict seam → `exchange_calendars`，禁反向依赖与业务语义倒灌 date_utils。③ real clock 仅 timezone-aware datetime（`datetime.now(tz=ZoneInfo("Asia/Shanghai"))` 归一 Shanghai），构造期 fail-closed（`NaiveClockError` fail-fast），错误描述可观察但无敏感数据。④ calendar preflight 五项：identity（XSHG）/version/库（现场读取 `exchange_calendars.__version__` 对照，历史实测 4.13.2）、timezone、coverage 窗口（first/last session）、指定 trading/not-trading/session-close 样例（T2 以 calendar 输出事实裁定）；禁网络与 fallback/周末推断/`TRADING_DAYS_2026`/裸 `is_trading_day()`。⑤ E2E：被测单元 `AShareCompletedSessionPolicy(clock=injectable_clock)`，可注入可控 datetime + fake/受控 real-calendar（仅本地库，无网络）；六类断言（已收盘/未收盘/非交易日/未来日/calendar 不可用或越界/naive clock）+ 每路径零写入（0 Provider/0 Mongo/0 cache/0 refresh/0 网络/0 文件写）。⑥ 服务重启仅既有运维入口，服务名/命令 T2 以仓库事实裁定（当前仓库无 in-repo systemd unit；HEARTBEAT.md host 级 cron 条目均非目标服务依据）；无可安全重启目标则 fail-stop，禁臆造/增设 unit；重启前后最小健康/行为 check。⑦ 回滚仅撤销 production composition injection 恢复 `completed_session_policy=None`；禁 DB 回滚/删除、禁自动回滚；失败分类（必须保持 disabled / 可本地修复后重验 / 注入后异常撤销重验）。⑧ 阶段分层：T2 Design-only → T3 local implementation only → T4 独立离线/受控验证 → T5 独立 review → T6 Production Activation 仅 T5 PASS 后执行，本次授权不得扩大到禁止对象。⑨ 副作用矩阵（T1~T5 全 0；唯一运行时动作在 T6 = 真实 clock/calendar 本地读取 + 既有服务重启一次，不可行则 fail-stop）。§7 A-038、§11 OQ-11 同步。保留 V0.25 全部冻结项：date_utils 唯一事实源、四态判定链、fail-closed、可审计、兼容五稳定 code、offline adapter 已验收（DESIGN-03-014 V0.32 §OQ-11）、生产注入未执行；保留 V0.24 全部冻结项：offline stub/defer；AKShare sentiment 未注册、live-read 不重跑；`total_turnover=None`；OQ-10；F6 TTL/key；真实 refresh 仍禁止。不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态。 | YQuant-Principal |
| V0.27 | 2026-08-04 | **R2 生产 Re-baseline：name_em 实时板块排行移出 Phase 3 目标 + 生产验证完成矩阵 + 生产 Gate 授权骨架（Pascal 2026-08-04 范畴裁定，仅文档；对应 RFC-03-014 V0.27）**。① **R2 范畴裁定同步**（与 P3-A readonly-gate 三层文档 R2——SPEC §0.2 / RFC §2.6 / DESIGN §2.7——逐项一致）：`stock_board_industry_name_em()` / 行业板块 `name_em` 属实时板块排行，不在 Phase 3 实现/生产验证目标；PR-2 的 name_em 单次预算**永久废弃**，`t_55d44505`/`t_81432128` 标记 **superseded / historical evidence**，不得 unblock/retry/创建 replacement probe/改用其他 AKShare endpoint；**禁止**为 name_em 新建 Provider recovery、替代 endpoint、实时 refresh 或任何 live retry；**禁止**调用 `cons_em`。P3-A 仅保留盘后/历史、按 trade_date 可复现的 sector read-path 验证（消费既有历史集合/物化数据，不发起实时 Provider 调用）；PR-2 历史结果（ProviderUnavailable + netprobe 越界）保留为历史事实，不得作为生产能力失败或 recovery 依据。② **生产验证完成矩阵冻结（新增 §R2.2）**：六 capability 分别冻结「允许的最终状态 / 证据要求 / 禁止表述」——P3-A sector.snapshot/sector.ranking（实时）= out-of-scope（不验证）；P3-A sector 盘后/历史 read-path = ~~production-read-path-validated~~ 或 ~~read-path-unavailable-by-design~~（V0.31 三态统一仲裁：并入 `production-validated`（仅 read-path scope）/ `provider-unavailable-frozen`，见 V0.31 条目）；P3-B flow.capital_flow_daily = production-validated 或 provider-unavailable-frozen；P3-B flow.northbound_daily = intentionally-unavailable（Pascal C）；P3-C sentiment.market_snapshot / limit_up_pool = production-validated 或 provider-unavailable-frozen。③ **关键冻结语义（新增 §R2.3）**：三张 `03_data_ud_*` 集合为 designated historical baseline（只读 census 可用、禁止重复 DDL；schema drift → 先修设计不就地改库）；`P3PersistenceWriter` 拒绝真实 pymongo（任何生产写入前需新生产 writer/身份/DDL/rollback 设计，Full Flow，不得绕过）；northbound 持股历史不得伪装净流入（正确验证是 None/unavailable fail-stop）；P3-C close-only / completed-session / `total_turnover=None` / Provider 未注册（live-read 预算耗尽不重跑）；OQ-11 本地策略注入已验证但无可安全消费进程，T6 保持 fail-stop，不得臆造 systemd/cron。④ **后续生产 Gate 授权骨架（新增 §R2.4）**：P3-A read-path census / P3-B capital-flow chain / P3-C route decision / consumer-restart 分别定义目标 namespace/数据源、精确 read/write/DDL 命令 allowlist、最大调用数/写入数/输出限制、fail-stop 停止条件与回滚/禁用语义、输出脱敏规则、独立 Verify 身份边界。⑤ **一致性**：§0、§2.1、§7 A-018、§10 G-A-2、§10.bis PR-2/PR-DDL-P3A、§14.1、§14.4.1、§14.4.5.4/§14.4.5.5/§14.4.5.7/§14.4.5.9/§14.4.5.10、§14.7、§14.8、§P0.2/§P0.4/§P0.7/§P0.8、§P1.3/§P1.9 残留 name_em 实时验证表述统一标记 superseded / out-of-scope（保留历史事实，不删除）；新增 §R2 章节。不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态（除 name_em/PR-2 相关 R2 标记）、不修改 DESIGN-03-014 master。 | YQuant-Principal |
| V0.28 | 2026-08-04 | **R2 契约修复（对应 RFC-03-014 V0.28；独立 Verify `t_876a30bd` FAIL 闭环）**。在 V0.27 基础上按 Verify 证据最小修复：① **新增 §R2 章节**（R2.1 范畴裁定 / R2.2 六 capability 生产验证完成矩阵 / R2.3 关键冻结语义 / R2.4 后续生产 Gate 授权骨架 / R2.5 一致性声明），以 SPEC 可执行契约语言镜像 RFC §R2，消除 §0 术语与 changelog 对 §R2 的悬空引用；② **正文残留可执行 PR-2 契约补标/改写**——§7 A-018、§10 G-A-2、§10.bis PR-2 行 / PR-DDL-P3A 触发（改为不依赖 PR-2）/ PR-3、PR-4 并行语义 / 关键约束、§14.1、§14.4.1、§14.4.5.4（R2 注）/§14.4.5.5 预算表/§14.4.5.7 验收项 3、7/§14.4.5.9 裁决表 sector 行/§14.4.5.10（refresh 已禁）、§14.6 流程图与 §14.6.4 PR-DDL-P3A 前置条件 (a)、§14.7 成功标准、§14.8 停止条件、§P0.2 sector 行/§P0.4 PA-1~9/§P0.7 P2 行、§P1.3 refresh 行/§P1.8 副作用矩阵/§P1.9 G-A/B/C-2——统一标记 superseded / out-of-scope（R2）或改写触发条件，与 RFC §R2、P3-A readonly-gate R2（RFC §2.6 / SPEC §0.2 / DESIGN §2.7）逐项一致。保留 V0.27 及更早全部行；不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态（除 name_em/PR-2 相关 R2 标记）、不修改 DESIGN-03-014 master。 | YQuant-Principal |
| V0.29 | 2026-08-04 | **残留 PR-2 行收尾同步（对应 RFC-03-014 V0.29；P0 第二轮）**。RFC §6.2/§6.3/§6.4 残留 PR-2 可执行行补标/改写（§6.3 停止条件表与 §6.4 禁止绕过清单对齐本 SPEC §14.8 已清理语义；§6.2 PR-3/PR-4 触发列对齐 §10.bis）。本 SPEC 正文无改动，仅 changelog 同步 V0.29。保留 V0.28 及更早全部行；不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态（除 name_em/PR-2 相关 R2 标记）、不修改 DESIGN-03-014 master。 | YQuant-Principal |
| V0.30 | 2026-08-04 | **§R2 标题版本语义消歧与元数据同步（对应 RFC-03-014 V0.30；第三轮 Verify `t_10255c16` FAIL-R3-1 闭环）**。§R2 标题内嵌来源版本（V0.28）补注「V0.28 引入；V0.29 同步」，显式说明标题内嵌来源版本与当前文档版本 V0.29 的关系；本 SPEC 正文无改动，仅标题语义与元数据版本号/来源 RFC/changelog 同步。保留 V0.29 及更早全部行；不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态、不修改 DESIGN-03-014 master。 | YQuant-Principal |
| V0.31 | 2026-08-04 | **P3-A read-path 结果词汇三态统一仲裁（P0 Contract Arbitration，对应 RFC-03-014 V0.31 / DESIGN-03-014 V0.35）**。Orchestrator 2026-08-04 定位公开契约冲突：master DESIGN-03-014 V0.34 §R2.4 规定生产结论词汇仅允许 `production-validated` / `provider-unavailable-frozen` / `intentionally-unavailable`，而 RFC/SPEC §R2.2 P3-A read-path 行仍使用旧双态 `production-read-path-validated` / `read-path-unavailable-by-design`。本卡仲裁（不放松 `name_em`/`cons_em` 禁令、不将 read-path census 等同实时 Provider 验证）：① P3-A read-path census **成功** → **唯一** `production-validated`（scope 仅限盘后/历史 read-path，≠ 实时 Provider 验证；仅能由未来获授权且实际执行、独立验证的 G-R2-1 census 产生；本文档裁定不产生任何生产结论）；② census **不可用**（集合不存在 / by-design 无安全消费进程说明）→ **唯一** `provider-unavailable-frozen`（不可用证据冻结 + fail-stop，不自动重试）；③ **非结论 fail-stop（不落三态）**：schema drift → 先修设计（Full Flow）不得就地改库；认证失败 → 无法区分不可用与未授权，不自动重试；空集合（0 行且无 by-design 解释）→ 无数据可验证；任何写入尝试 → 越界 fail-stop（G-R2-1 无 write/DDL）；独立 Verify 未通过 → Gate 不关闭；④ `intentionally-unavailable` 对 P3-A read-path **不适用**（无 Pascal C 决策，该态仅保留给 P3-B `flow.northbound_daily`）；⑤ **禁止杜撰第四/第五状态**；⑥ §R2.2 矩阵 P3-A read-path 行、状态语义与 V0.27 changelog 残留旧术语同步修订，§R2 标题补注「V0.31 三态统一仲裁」。保留 V0.30 及更早全部行；不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态、不修改 P3-A readonly-gate 三件套、不修改任何代码/测试/配置/脚本/报告产物。 | YQuant-Principal |
| V0.32 | 2026-08-05 | **P3-B S1 真实资金流生产验证与受控物化契约（独立重建；对应 RFC-03-014 V0.32 / DESIGN-03-014 V0.35 待下游同步）**。触发事实：此前未提交的 SPEC V0.32 / Design V0.36 已被工作树 `git restore`/checkout 类动作整体回退，恢复核验卡 `t_eb2ed46e` 记录的 R3 文件内容已不在磁盘，不能继续以其结论作为当前代码的活跃契约。本卡从当前 V0.31 基线独立重建 SPEC §R3（不依赖历史 worker summary 宣称恢复成功；零真实动作；离线/mock 不构成生产验证）。① **唯一真实目标**：`flow.capital_flow_daily` → `stock_individual_fund_flow`（B2 冻结证据 real-mappable，见 §14.4.5.2）；`flow.northbound_daily` 恒 `intentionally-unavailable`/None fail-stop（Pascal C，§14.4.5.2 / §R2.2），禁止 `stock_hsgt_individual_em`、endpoint skeleton、DDL/canary/验收。② **四 Gate 严格串行且逐个明确 Pascal 授权**：G-CF-LIVE（零 Mongo live-read，600519、最多 3 个 completed trading dates、≤3 calls、≥1s 间隔、3s 超时、零 Mongo/cache/refresh/upsert/DDL/DML/Git 写、失败冻结不换标的/日期/endpoint）→ G-CF-DDL（唯一 `tradingagents.03_data_ud_stock_capital_flow` + 两索引 `symbol_trade_date`/`trade_date`，权威契约 §14.6.bis / DESIGN §6.4.bis）→ G-CF-CANARY（600519 × 一个 completed date × ≤1 doc，显式 refresh → upsert，delete_by_filter 清理）→ G-CF-POST（独立只读验收：ping/list_collection_names/find/count_documents，Verify 不重复真实调用）；禁止第四路径、自动推进、fallback、隐式重试。③ **completed-date 契约**：必复用 `skills.infra.date_utils` / `CompletedSessionPolicy` 契约（canonical `YYYY-MM-DD`、XSHG 交易日、session close、fail-closed，见 V0.25/V0.26 EOD-7/EOD-8）；OQ-11 保持独立子链，不在 P3-B 实现 composition。④ **生产结论产生条件**：仅四 Gate 全部实际执行及独立 Verify 通过才产生（三态词汇 `production-validated` / `provider-unavailable-frozen`；northbound 恒 `intentionally-unavailable`）。⑤ **下游 Design 仅文档层精确需求**：§R3.10 逐项指定（工具链/写入身份/验收输出/阈值一致性/不扩展边界），不得提前引用或认可当前工作树两份 dirty Python（`scripts/t4_preflight/{config.py,provider_client.py}`）。⑥ 不扩展 P3-A/P3-C/OQ-11/name_em/cons_em 既有语义；§R3.11 一致性声明标注 Design 仍待下游同步。 | YQuant-Principal |
| V0.33 | 2026-08-05 | **P0 阈值纠正同步：R3 字段映射停止条件 50%→70%（对应 RFC-03-014 V0.33）**。触发事实：RFC-03-014 V0.33 P0 阈值纠正已将真实 Provider 字段映射差异停止条件从旧 `>50% 字段名不匹配` 统一为「匹配率 ≥70% 才可通过；<70% fail-stop」，对齐项目常量 `MATCH_RATIO_CONDITIONAL=0.70`（scripts/t4_preflight/config.py）与 DESIGN §15.6.2 / §R2.4 G-R2-2；旧 >50% 表述为公开执行契约冲突（P0），已由 RFC V0.33 废弃。本卡按 RFC V0.33 §R3.10 同步指令执行 SPEC 层下游同步：① §R3.3 G-CF-LIVE 停止条件同步为 `字段映射匹配率 <70%（≥70% 才可通过）`；② §R3.9 第 1 项 G-CF-LIVE 可执行契约补入映射阈值；③ §R3.10 阈值一致性改为 `<70% fail-stop / ≥70% 才可通过`，唯一阈值输入 = `MATCH_RATIO_CONDITIONAL=0.70`；④ **§14.8 停止条件表字段映射行同步为 `<70%`**；⑤ **§11 OQ-9 标记 V0.33 已纠正**（RFC §6.3 / SPEC §11 同源 >50% 提议替换为 <70% 裁定）。仅改 SPEC 一份；不动 RFC/Design/Python/tests/config/scripts/data/Git；无 secret；零真实动作。 | YQuant-Principal |
| V0.34 | 2026-08-05 | **G-CF-LIVE-R3：AKShare 直连与真实 HTTP timeout 受控诊断契约（Pascal 明确授权最终单次 live-read，仅文档；对应 RFC-03-014 V0.34）**。新增 §R3.3.bis「G-CF-LIVE-R3」可执行契约（镜像 RFC V0.34 §R3.9 第 9 项）：① **唯一 endpoint/API**：AKShare `stock_individual_fund_flow(stock='600519', market='sh')`，严禁换 endpoint/标的/日期；report target `600519/CN`；candidate date `2026-08-04`（仅报告元数据）。② **direct transport**：仅本次子进程临时清空 `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`，`NO_PROXY` 仅保留本机最小默认值；不改 shell profile/.env/系统/服务/网关配置。③ **调用预算**：至多 1 次逻辑 Provider 调用、真实 HTTP request timeout=10s、≥1s 间隔（仅一次则不触发）、零 retry/零 fallback。④ **禁止**：Mongo（含连接/ping）、cache、refresh/upsert、DDL/DML、Git 写/commit、服务/cron/gateway 变更、替代 provider/endpoint/日期/标的。⑤ **失败**：任何 DNS/TCP/TLS/HTTP/timeout/schema 异常立即 fail-stop，保留脱敏异常层级（异常类、message 摘要、cause/urllib3 子类），不得重放本 Gate。⑥ **临时报告**：批准 `/tmp/yquant-g-cf-live-r3-20260804-<run-id>/`（目录 0700、YAML 0600），账本记录 provider_attempts/actual_calls/retry/fallback/mongo/write=0 与 direct_transport、effective_http_timeout_seconds。⑦ **定位**：R3 是**新一次独立授权 Gate**，不是 R1/R2 自动重试；R1/R2 历史事实（均 `ConnectionError`、经继承代理环境；`DEFAULT_TIMEOUT_SECONDS=3` 未传至 AKShare 1.17.54 内部 `requests.get`）不改写；不产生生产结论、不替代四 Gate 链；rollback 仅撤销未来 R3 代码路径、不回滚历史报告/数据。⑧ 不扩展 P3-A/name_em/cons_em/OQ-11 既有语义。§R3.3.bis 表 + §R3.9 第 9 项 + §R3.11 一致性声明同步；RFC-03-014 V0.34 同步镜像。仅改 SPEC 一份；不动 RFC/Design/Python/tests/config/scripts/data/Git；无 secret；零真实动作。 | YQuant-Principal |
| V0.35 | 2026-08-07 | **事实归档：§R3.3.bis.1 2026-08-07 受控直连诊断 fail-stop（不对 §R3.3.bis 冻结契约做任何修订；对应 RFC-03-014 V0.35 / DESIGN-03-014 V0.38）**。触发事实：Pascal 2026-08-05 21:16 收窄 R3 目标为"一次性 AKShare 可达性与返回格式诊断"，明令禁止 Design/代码变更；2026-08-07 18:11 执行一次性受控诊断（不修代码、不动 Design、不动 .env/服务/网关；诊断脚本 `/tmp/r3_diag_minimal.py`），唯一 endpoint `akshare.stock_individual_fund_flow(stock='600519', market='sh')` + 600519/CN + 2026-08-04 + 子进程临时清空 6 个 proxy 变量 + 1 次逻辑调用 + `effective_http_timeout_seconds=null`（未注入 10s）+ `requests.get` 默认 timeout 探测 = `None`（证实 `DEFAULT_TIMEOUT_SECONDS=3` 未传至 AKShare 1.17.54 内部 `requests.get`）+ TCP 443 握手全部成功（28–55ms）+ connectivity=error / error_class=requests.exceptions.ConnectionError / exception_chain 三层 RemoteDisconnected + 零 retry/fallback/Mongo/DDL/DML/Git/服务。① **本卡为"已发生事实"事实归档**（V0.35），**不改 V0.34 §R3.3.bis 任何冻结契约条款**；不重新打开 R3 完整 Design→Implement→Verify→Review 链路；不构成"G-CF-LIVE-R3 通过 / 四 Gate 全过 / R1/R2 翻案 / 扩展 P3-A / name_em / cons_em / OQ-11 / OQ-11B 既有语义"的依据。② 新增 §R3.3.bis.1 子节（事实归档条目，镜像 RFC V0.35 §R3.3.bis.1），逐项记录上述诊断结果 + 产物 sha256/size + 关联 Kanban 卡 `t_73e26ca7` / `t_55ebd64b`（已挂 evidence-only comment id=1244/1245 + blocked 终态冻结，reason=`frozen-per-Pascal-2026-08-05-scope-narrowing`）。③ V0.34 §R3.3.bis R1/R2 历史事实（均 `ConnectionError`、经继承代理环境、`DEFAULT_TIMEOUT_SECONDS=3` 未传至 AKShare 1.17.54 内部 `requests.get`）保持准确不改写。④ 头部"最后更新"追加本轮条目；版本号 V0.34→V0.35（事实归档条目按惯例升 V+1）；"来源 RFC"指针同步 V0.34→V0.35。⑤ RFC-03-014 V0.34→V0.35 / DESIGN-03-014 V0.37→V0.38 同步镜像同一 §R3.3.bis.1 子节。仅改 RFC/SPEC/DESIGN 三份文档；不动 Python/tests/config/scripts/data/Git/Hermes/profile/.env/服务/网关；无 secret；零真实写入动作。 | YQuant-Principal |
|
---
## 0. 术语对齐与基线锚定

本 SPEC 继承 RFC-03-007 / SPEC-03-007 / SPEC-03-008 的全部基线，不重述背景，只锁定 Phase 3 必须一致的措辞：

- **Phase 3** = 重要持久化扩展。与 Phase 2（质量审计治理）独立可并行，与 Phase 1E（个股情绪最小切片）正交。
- **P3-A** = `03_data_ud_market_sector_snapshot` 板块/行业快照。Capabilities: `sector.snapshot`, `sector.ranking`。
- **P3-B** = `03_data_ud_stock_capital_flow` 个股资金流。Capabilities: `flow.capital_flow_daily`, `flow.northbound_daily`。
- **P3-C** = `03_data_ud_market_sentiment_snapshot` 市场情绪快照。Capabilities: `sentiment.market_snapshot`, `sentiment.limit_up_pool`。
- **AKShare 是 Phase 3 外部 Provider**：上述六个 capability 的 external_fallback_chain 为 `["akshare"]`。**R2（2026-08-04）：P3-A `sector.snapshot`/`sector.ranking` 实时板块排行（`name_em`）已移出 Phase 3 实现/生产验证目标——该 chain 对 P3-A 实时为计划态/out-of-scope（§R2）；P3-B/P3-C 不变。**
- **P3-C 时间语义（2026-08-03 Pascal 裁定）**：`sentiment.market_snapshot` / `sentiment.limit_up_pool` 当前目标为**已完成交易日 / 收盘后 / 可重放**；`snapshot_time` 当前仅 `close`；盘中实时情绪属未来独立 capability（独立 Provider/字段契约/freshness/时间边界/新用户授权），不在本 Phase 3 范围。`stock_market_fund_flow()` 无 date 参数（`klt=101` 日线），使用时必须按返回日线序列按目标 `trade_date/snapshot_date` 精确筛选，资金净流入不得映射 `total_turnover`。
- **MongoDB 是 Phase 3 唯一生产持久化目标**：所有 `03_data_ud_*` 物化集合以 **MongoDB（`tradingagents` 库）** 为默认生产写入与读取目标。SQLite 仅可用于以下明确限定场景：
  - 现有 legacy adapter 的数据源（如 DSA 的 SQLite 路径——DSA 不是运行时数据源，不出现在外部 fallback 链）
  - 单元测试 / 集成测试中的隔离数据库（如 mongomock 或临时 SQLite 替代）
  - 离线 fallback（仅当 MongoDB 完全不可达且消费方已通过配置显式授权）
  - **禁止**：SQLite 不得作为 Phase 3 正式生产写入目标，不得出现在 `03_data_ud_*` 集合的生产写入路径中。
- **internal-first 读取路径不变**：TA-CN 既有 → LocalMongo（`03_data_ud_*`）→ Cache → 外部 Provider。新集合通过 LocalMongoAdapter 读取。
- **MongoDB `tradingagents` 库**：所有 `03_data_ud_*` 物化集合位于此物理库，通过前缀隔离 ownership。
- **T4 生产就绪**：Phase 3 离线实现（T1 RFC+SPEC + T2 Design + T3 Implement）完成后，在真实生产环境上执行零写入只读预检与真实 Provider Smoke 的阶段。仅包含 MongoDB 只读连通预检、Secret Source 审计、真实 Provider Smoke（单标的、≤3 日窗口、零持久化写）。**不包含**任何 MongoDB DDL/DML、Cache/业务写入、cron/systemd、外部消息/webhook、`.env` 写入或回显。
- **PR-Gate**：Production Readiness Gate 的缩写，T4 生产就绪阶段的授权关卡。包括 PR-0（MongoDB 连接秘密审计，复用 Phase 2 skills/.env 五组件键 `MONGODB_HOST`/`PORT`/`USERNAME`/`PASSWORD`/`DATABASE`，组件式构造连接非 URI——V0.4 的 `MONGO_URI` 单键来源已 superseded；AKShare 跳过密钥审计）、PR-1（MongoDB 只读预检）、PR-2/3/4（Provider smoke，AKShare 为匿名调用不依赖 PR-0）、PR-DDL-*（DDL 授权）、PR-CANARY-*（手动 canary）。**R2（2026-08-04）：PR-2（sector 实时 smoke）已 superseded / out-of-scope——name_em 实时板块排行移出 Phase 3 目标，PR-2 预算永久废弃（§R2）**。
- **Smoke 报告**：每个真实 Provider smoke 调用产出的结构化 YAML 报告，包含连通性、认证、权限、字段映射、数据样例、vs_fixture 偏差等独立节（§14.4.2）。
- **Zero-Persistence-Write**：DataRouter.query() 对 P3 capability 的全程只读保证——Step 4 外部 Provider fetch 成功后仅返回 DataResult，不触发 `_materialize()`、不写物化集合、不写 Cache、不写 AuditLogger（§14.5）。
- **FV（待验证事实）**：RFC §5.5 定义的生产环境待验证事项，T4 阶段通过真实 Provider smoke 逐一验证。
- **R2 生产验证 Re-baseline（2026-08-04，V0.27）**：`name_em` 实时板块排行移出 Phase 3 实现/生产验证目标；PR-2 预算永久废弃（`t_55d44505`/`t_81432128` superseded / historical evidence）；禁止为 name_em 新建 Provider recovery/替代 endpoint/实时 refresh/live retry；禁止调用 `cons_em`。P3-A 仅保留盘后/历史、按 trade_date 可复现的 sector read-path 验证。六 capability 生产验证完成矩阵与后续生产 Gate 授权骨架见 §R2（与 P3-A readonly-gate SPEC §0.2 / RFC §2.6 逐项一致）。
- **R3 P3-B 真实资金流生产验证与受控物化契约（2026-08-05，V0.32 引入；V0.33 P0 阈值纠正同步；V0.34 G-CF-LIVE-R3 直连诊断）**：P3-B S1 `flow.capital_flow_daily` 的唯一真实 Provider 目标为 `stock_individual_fund_flow`；`flow.northbound_daily` 恒 `intentionally-unavailable`/None fail-stop（Pascal C，禁 `stock_hsgt_individual_em`/endpoint skeleton/DDL/canary/验收）；四 Gate G-CF-LIVE → G-CF-DDL → G-CF-CANARY → G-CF-POST 严格串行且逐个 Pascal 授权（禁止第四路径、自动推进、fallback、隐式重试）；**V0.34 新增 §R3.3.bis「G-CF-LIVE-R3」独立授权异常 Gate**（唯一 endpoint `stock_individual_fund_flow(stock='600519', market='sh')`、600519/CN、candidate date 2026-08-04、direct transport 清空 `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`、1 call/10s timeout、零 retry/fallback、零写、fail-stop 脱敏异常、临时报告 `/tmp/yquant-g-cf-live-r3-20260804-<run-id>/`、rollback 仅撤销未来 R3 代码路径；R3 是**新一次独立授权 Gate**、非 R1/R2 自动重试、R1/R2 历史事实不改写、不产生生产结论、不替代四 Gate 链）；completed-date 复用 `skills.infra.date_utils` / `CompletedSessionPolicy` 契约，OQ-11 保持独立子链；生产结论仅能由四 Gate 全部实际执行 + 独立 Verify 产生。字段映射停止条件统一为「匹配率 ≥70% 才可通过；<70% fail-stop」（对齐 `MATCH_RATIO_CONDITIONAL=0.70`，唯一阈值输入）。可执行契约见 §R3（与 RFC-03-014 V0.34 §R3 逐项一致）。

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

- [x] P3-A: `SectorSnapshot` domain object 定义 + `sector.snapshot` / `sector.ranking` 能力注册（P0 ✅ offline）
- [ ] P3-A: AKShareProvider 的 `sector.snapshot` / `sector.ranking` fetch 实现（**R2（2026-08-04）：name_em 实时板块排行移出 Phase 3 目标——本项 out-of-scope，不再属 P2 真实 Provider smoke；仅保留盘后/历史 read-path 验证，见 §R2**）
- [x] P3-A: `03_data_ud_market_sector_snapshot` 物化集合写入 + P3PersistenceWriter 读取（P1 ✅ mongomock fake-only；❌ 真实 MongoDB 属 P1.5/P2）
- [x] P3-A: `sector_service.get_sector_snapshot()` / `sector_service.get_sector_ranking()` 实现（P0 ✅ offline）
- [x] P3-B: `CapitalFlowRecord` domain object 定义 + `flow.capital_flow_daily` / `flow.northbound_daily` 能力注册（P0 ✅ offline）
- [ ] P3-B: AKShareProvider 的 `flow.capital_flow_daily` / `flow.northbound_daily` fetch 实现（❌ 属 P2 真实 Provider smoke）
- [x] P3-B: `03_data_ud_stock_capital_flow` 物化集合写入 + P3PersistenceWriter 读取（P1 ✅ mongomock fake-only；❌ 真实 MongoDB 属 P1.5/P2；⚠️ northbound_daily 始终 fail-stop Pascal C）
- [x] P3-B: `flow_service.get_capital_flow()` / `flow_service.get_northbound_flow()` 实现（P0 ✅ offline；northbound 恒 None-Pascal C）
- [x] P3-C: `MarketSentimentSnapshot` domain object 定义（22 字段 canonical）+ `sentiment.market_snapshot` / `sentiment.limit_up_pool` 能力注册（P0 ✅ canonical 22-field；AKShareProvider 未注册，保持 offline stub/defer——2026-08-03 裁定）
- [ ] P3-C: AKShareProvider 的 `sentiment.market_snapshot` / `sentiment.limit_up_pool` fetch 实现（❌ 属 P2 真实 Provider smoke）
- [x] P3-C: `03_data_ud_market_sentiment_snapshot` 物化集合写入 + P3PersistenceWriter 读取（P1 ✅ mongomock fake-only；❌ 真实 MongoDB 属 P1.5/P2；limit_up_pool 独立键 `{market, symbol, trade_date}` 已验证 F1/F4）
- [x] P3-C: `sentiment_service.get_market_snapshot()` / `sentiment_service.get_limit_up_pool()` 实现（P0 ✅ offline）
- [x] 全部：UnifiedDataClient 新增对应域方法（§5.1）（P0 ✅ offline；未含 flow/sentiment service 属性需 T3 补充）
- [x] 全部：colocated 单元测试 + fixture（P0 ✅ offline）
- [ ] 全部：Pascal 逐项授权 Gate 确认后执行（❌ 未授权——DDL Gate 已冻结但 Refresh/Canary Gate 均未激活）
- [ ] **T4 新增**: Secret source 审计（PR-0）：逐候选文件验证存在性 + 可加载性（❌ 属 P2，未执行）
- [ ] **T4 新增**: MongoDB 只读预检（PR-1）：ping + listCollections + 确认无意外 P3 集合（❌ 属 P2，未执行）
- [ ] **T4 新增**: Provider smoke sector（PR-2）：单板块代码 ≤3 交易日，只读调用（**R2（2026-08-04）：superseded / out-of-scope——PR-2 预算永久废弃，不再属 P2 未执行项，不得执行；见 §R2**）
- [ ] **T4 新增**: Provider smoke flow（PR-3）：单标的 ≤3 交易日，只读调用（❌ 属 P2，未执行）
- [ ] **T4 新增**: Provider smoke sentiment（PR-4）：单日期，只读调用（❌ 属 P2，未执行）
- [ ] **T4 新增**: Smoke 报告生成：每 capability 独立 YAML 报告（§14.4.2 模板）（❌ 属 P2，未执行）

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
- ❌ **R2（2026-08-04）**: 为 name_em 新建 Provider recovery / 替代 endpoint / 实时 refresh / 任何 live retry；执行 PR-2 smoke 或创建 one-call continuation（PR-2 预算永久废弃，§R2）；调用 `cons_em`；任何 P3-A 实时板块排行的生产验证

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
    snapshot_time: str                        # (必填) 快照时间，24h 格式如 "15:00:00" 或 "close"。当前实现/映射仅可落地 "close"（收盘后快照），禁止 intraday snapshot（2026-08-03 裁定）
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
            # Pascal 2026-08-03 裁定：total_turnover 当前无合规来源，
            # 恒 None（与 northbound_net_flow 同构 fail-stop）。
            # 任意输入的非 None 值（含资金净流入映射）不得进入输出。
            total_turnover=None,
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
| `total_turnover` | **恒 None（2026-08-03 裁定）** | 全市场成交额（元）。当前无合规来源（`stock_market_fund_flow` 返回列无「成交额」），`from_dict` 强制规范化为 `None`；资金净流入不得映射本字段 |
| `limit_up_pool` / `limit_down_pool` | 每个列表最大 500 个代码 | 若独立提供 `sentiment.limit_up_pool` capability，此集合中的对应字段可为空 |

| `snapshot_date` | 格式 `YYYY-MM-DD` | 唯一键 `{market, snapshot_date, snapshot_time}` 的组成部分 |
| `snapshot_time` | 格式 `HH:MM:SS` 或 `close` | 唯一键组成部分。`close` 表示收盘后快照。**当前 Phase 3 实现/映射仅可落地 `close`（已完成交易日/可重放），禁止 intraday snapshot**（2026-08-03 裁定） |
| `market` | 如 `"CN"` | 唯一键组成部分 |

**MongoDB 唯一键**：`{market, snapshot_date, snapshot_time}`
**MongoDB 索引建议**：
- `{snapshot_date: -1}` — 按日查询
- `{snapshot_time: -1}` — 按时点查询

**温度合成公式待定**：`market_temperature` 为派生字段，由 `sentiment_service` 在 Provider 原始数据上合成。Pascal 确认该字段可保持为 `None`（不强制合成，禁止编造）。T2 Design 阶段需定义合成公式或确认保留为 `None` 由消费方自行计算。

**P3-C 时间语义冻结（2026-08-03 裁定）**：`sentiment.market_snapshot` / `sentiment.limit_up_pool` 当前目标为已完成交易日 / 收盘后 / 可重放；`snapshot_time` 当前仅 `close`。盘中实时情绪属未来独立 capability——需独立 Provider/字段契约/freshness/时间边界与新的用户授权，不得以本卡放行。`total_turnover` 无合规来源时保持 `None`/unavailable——`stock_market_fund_flow()` 返回列无「成交额」（SDK 静态，见 RESEARCH-03-014 E15/E23），资金净流入不得映射为 `total_turnover`。

**EOD 验证执行契约（V0.22 Design Gate REVISE closure 冻结；V0.23 Closure-2 修正 `refresh_limit_up_pool` 签名，本规范为权威可执行契约）**：

**EOD-1 唯一 validation owner**：`MarketSentimentService`（`services/sentiment_service.py`）的公开入口：
- `get_market_sentiment_snapshot(snapshot_date: str, snapshot_time: str = "close")`
- `get_limit_up_pool(trade_date: str | None = None)`
- `refresh_market_sentiment_snapshot(snapshot_date: str, snapshot_time: str = "close", *, provider=None)`
- `refresh_limit_up_pool(trade_date: str, *, p3_writer=None, provider=None)`

四个入口**必须**执行 EOD 校验（get_limit_up_pool 的 `trade_date=None` 表示「最近可用日期」——**仅读路径例外**，允许跳过 completed-session 校验；显式传入日期时校验）。**`refresh_limit_up_pool` 的 `trade_date` 为本轮 refresh 必填参数——不允许 `None`/latest 语义**；`trade_date` 必须 canonical `YYYY-MM-DD`，由 `CompletedSessionPolicy` 在 provider fetch / writer upsert / cache put **之前**校验（5 个既有错误 code 的日期相关分支适用于本入口：`INVALID_DATE_FORMAT` / `NOT_TRADING_DAY` / `FUTURE_TRADING_DAY` / `SESSION_NOT_COMPLETED`，无新增模糊 code）；happy path 将同一 canonical `trade_date` 传入 provider params 并用于 date-scoped cache key，**不得先 fetch 后从 records 推断日期**。校验逻辑不得分散交由 domain、provider、router 或 caller 裁决。

**EOD-2 注入 seam（`CompletedSessionPolicy`）**：新增最小只读协议：

```python
class SessionStatus(Enum):
    COMPLETED = "completed"              # 已完成 A 股交易日
    NOT_A_TRADING_DAY = "not_a_trading_day"
    FUTURE_TRADING_DAY = "future_trading_day"
    SESSION_NOT_COMPLETED = "session_not_completed"

class CompletedSessionPolicy(Protocol):
    """只读协议：判定某 canonical YYYY-MM-DD 是否「已完成 A 股交易日」。

    实现必须通过可注入 fake calendar（交易日序列判定）+ fake clock
    （当前时间判定）组合出上述 SessionStatus；禁止 T3 直接读真实
    交易日历、系统日期或网络。生产实现未来由授权 Gate 注入。
    """

    def session_status(self, date: str) -> SessionStatus: ...
```

注入点：`MarketSentimentService.__init__(..., completed_session_policy: CompletedSessionPolicy | None = None)`。`None` 默认表示离线宽松模式（保留现有 stub 路径）；注入后 service 在四个公开入口调用 `session_status(date)`。

**EOD-3 输入规范与失败语义**：public service 接受 canonical `YYYY-MM-DD`；以下五类失败均在 provider fetch / writer upsert / cache put **之前** fail-fast，错误类型/稳定 code/message 唯一（禁止 `error 或 empty` 模糊分支）：

| 场景 | 触发条件 | 异常 | 稳定 code |
|---|---|---|---|
| 格式非法 | 非 `YYYY-MM-DD` 或不可解析日期 | `SentimentSessionValidationError` | `INVALID_DATE_FORMAT` |
| 非 close | `snapshot_time != "close"`（仅 market_snapshot 类入口） | 同上 | `INVALID_SNAPSHOT_TIME` |
| 非交易日 | policy 返回 `NOT_A_TRADING_DAY` | 同上 | `NOT_TRADING_DAY` |
| 未来交易日 | policy 返回 `FUTURE_TRADING_DAY` | 同上 | `FUTURE_TRADING_DAY` |
| 未完成当日 | policy 返回 `SESSION_NOT_COMPLETED` | 同上 | `SESSION_NOT_COMPLETED` |

**refresh 无 latest/None 语义（V0.23 Closure-2）**：`refresh_limit_up_pool` 的 `trade_date` 必填，上表 5 个 code 的日期相关分支（`INVALID_DATE_FORMAT` / `NOT_TRADING_DAY` / `FUTURE_TRADING_DAY` / `SESSION_NOT_COMPLETED`）直接适用于本入口，无新增模糊 code；happy path 将同一 canonical `trade_date` 传入 provider params 并用于 date-scoped cache key，**不得先 fetch 后从 records 推断日期**。

`SentimentSessionValidationError(UnifiedDataError)` 携带 `code: str` 与稳定 message 模板；`code` 为可断言公共 token（SPEC/Design 引用同一枚举）。

**EOD-4 `snapshot_time` 处理层**：非 close 输入统一在 **service 层** fail-fast（唯一层）。`MarketSentimentSnapshot.from_dict` 保持离线 canonical parsing seam（宽松解析，不裁决业务语义），但所有 public ingress 不得产生/持久化 intraday。`get_limit_up_pool` 的 trade_date 仅校验「已完成交易日」，不涉及 snapshot_time。

**EOD-5 测试契约**：T3 以 fake completed session policy + spy 证明：(a) close + completed day 走现有离线路径（1 provider fetch / 可选 upsert）；`refresh_limit_up_pool` 的 fake policy 必须记录收到显式 canonical `trade_date`，happy path 的 provider params 含同一 `trade_date`、cache key 为 date-scoped；(b) 非 close、格式错误、非交易日、未来日、未完成当日均为唯一失败，且每个失败 `0 provider fetch / 0 writer upsert / 0 cache put`。不要求真实 provider、真实时钟、真实 calendar、Mongo 或网络。

**EOD-6 `total_turnover` 强制 None**：canonical output（默认 offline stub、canonical fixtures、`MarketSentimentSnapshot.from_dict` ingress）必须强制 `None`；任何输入的非 None 值（包括伪造资金净流入）都不得进入输出。唯一实施层为 domain `from_dict` 规范化（与 `northbound_net_flow` 恒 None 同构），使所有 mapping/fixture/injection 一致。

**EOD-7 生产 `CompletedSessionPolicy` 可执行契约（V0.25 OQ-11 裁定，对应 RFC-03-014 V0.25；本规范为权威可执行契约，T2 Design 承接精确文件 allowlist）**：

**EOD-7.1 唯一事实源与消费边界**：A 股交易日历底座 = `skills.infra.date_utils`（内部优先动态 `exchange_calendars.get_calendar('XSHG')`；当前环境实测 `exchange_calendars==4.13.2`、calendar `XSHG`、timezone `Asia/Shanghai`、`session_close` = UTC 07:00 = Shanghai 15:00）。生产 `CompletedSessionPolicy` 只能通过正式 adapter/contract 消费 date_utils；**禁止**复制交易日清单、直连 provider 网络取日历、以 `TRADING_DAYS_2026` 硬编码 fallback 为生产真相、以裸 `is_trading_day()` 作为 production policy 唯一判定。**明确选择「复用 date_utils 底座 + 小型 adapter」方案，禁止新建孤立日历模块**。

**EOD-7.2 最小 public/internal 接口边界**：
- 现有 `date_utils` 公共 API（`is_trading_day` / `get_latest_trading_day` / `get_next_trading_day` / `get_trading_dates` / `parse_date` / `format_date`）**保持兼容，不改变签名与语义**。
- 新增 production-only adapter：命名裁定为 **`AShareCompletedSessionPolicy`**，实现 `CompletedSessionPolicy` Protocol（`session_status(date: str) -> SessionStatus`）。构造必须**显式依赖注入 clock**（timezone-aware，如 `Callable[[], datetime]` 或等价 Clock 协议）；**禁止 `datetime.now()` / `date.today()` 隐式读取**。生产 composition root 是唯一允许提供 real clock 的位置；测试/离线一律注入 fake clock。
- 内部 calendar 查询必须能**区分三种结果**：calendar unavailable / 日期越界 / 真实非交易日；不得把前两者折叠成 `False`。date_utils 若需扩展严格查询能力，必须新增**独立方法**（不改现有 API 行为），由 adapter 专用。
- 适配层若抛出 internal adapter error，必须在 service 层映射为既有可判定语义，**不得新增含混 public token**（映射规则见 EOD-7.5）。

**EOD-7.3 canonical 日期严格性**：`CompletedSessionPolicy.session_status(date)` 与 `MarketSentimentService` 四个公开入口的日期参数必须严格接受 canonical `YYYY-MM-DD`。date_utils 当前宽松解析（`YYYYMMDD` 等）**不得**在 public 边界静默通过——非 canonical 输入在 service 层按既有 `INVALID_DATE_FORMAT` 处理；policy/adapter 对非 canonical 输入应直接返回格式错误，不落入宽松解析。

**EOD-7.4 close instant 来源与 cutoff grace**：close instant 以 `calendar.session_close(date)`（或等价 date_utils 严格封装）产生；**禁止硬编码裸 `15:00` 作为唯一真相**（当前 XSHG 实测 close = UTC 07:00 = Shanghai 15:00，但必须以 calendar 输出为准）。若使用业务 cutoff grace（如 close 后 N 分钟才视为 COMPLETED），必须声明为**独立、可配置、可审计的 policy 参数**（如 `cutoff_grace: timedelta`），与日历事实分离；`cutoff_grace=timedelta(0)` 为默认（即 close 到达即 COMPLETED）。

**EOD-7.5 状态优先级/判定表与 fail-closed 映射**：`session_status(date)` 判定严格按以下优先级，未知依赖状态**不允许**误判为 `NOT_A_TRADING_DAY`：

| 优先级 | 场景 | 结果 | 说明 |
|---|---|---|---|
| 1 | 非 canonical `YYYY-MM-DD` / 不可解析 | 格式错误 | service 映射 `INVALID_DATE_FORMAT` |
| 2 | calendar 依赖不可用 / 日期越界 / calendar 异常 | **不可判定（fail-closed）** | 返回明确「不可用」结果或抛 internal adapter error，service 映射为可判定失败；**禁止** fallback 到 `TRADING_DAYS_2026`、周末规则或 latest |
| 3 | clock 无时区 / 无法判定当前 Shanghai 时间 | **不可判定（fail-closed）** | 同上；构造时即校验 clock timezone，缺失则 fail-fast |
| 4 | 非 XSHG 交易日 | `NOT_A_TRADING_DAY` | 仅当 calendar 明确回答「非交易日」时才允许 |
| 5 | 晚于 Shanghai 当前交易日 | `FUTURE_TRADING_DAY` | date > 当前 Shanghai 日期 |
| 6 | 当前交易日且未达 close/cutoff | `SESSION_NOT_COMPLETED` | date == 当前交易日 且 now < session_close(+grace) |
| 7 | 当前交易日已过 close/cutoff，或历史交易日 | `COMPLETED` | now >= session_close(+grace) 或 date < 当前交易日（已由步骤 4 确认交易日） |

internal adapter error 到 service 的映射：`CalendarUnavailableError` / `DateOutOfRangeError` / `NaiveClockError`（名称以 T2 Design 为准）一律在 service 层转换为 fail-fast，且**不新增 public error code**；若 service 无法给出既有五 code 之一，则按依赖不可用语义（`ProviderUnavailableError` 或既有等价错误）抛出，禁止静默返回成功或误判为 `NOT_A_TRADING_DAY`。

**EOD-7.6 可审计字段**：production policy 每次判定仅记录最小审计字段（**不记录日历全量数据或凭证**）：calendar identity/version、timezone、cutoff policy id、输入日期、clock 来源类别（real/fake）、最终 `SessionStatus`、降级/错误原因（如有）。审计写入走既有 AuditLogger 约定（默认关闭），不在本契约新增日志侧写。

**EOD-7.7 测试矩阵与零 I/O**：production adapter 单元测试必须使用 **fake calendar + fake timezone-aware clock** 覆盖 EOD-7.5 全部优先级路径（含 calendar unavailable、日期越界、clock 无时区、异常分支），并断言：(a) 每个不可判定路径不落入 hardcoded fallback（不引用 `TRADING_DAYS_2026`、不引用周末规则）；(b) 所有判定路径 `0 provider fetch / 0 writer upsert / 0 cache put / 0 Mongo / 0 网络`。date_utils 自身的单元测试必须覆盖「calendar 异常 / 越界时不落入 hardcoded fallback」的 production adapter 分支。真实 calendar / 真实 clock / 网络在本阶段全部禁止。

**EOD-7.8 T2 Design provisional 文件 allowlist（仅建议，本阶段禁止写代码）**：T2 Design 在下列候选内裁定精确文件范围（**不得超出**，且不得触碰下列「禁止动」清单）：
- 建议候选：`skills/infra/date_utils.py`（新增严格查询独立方法，保持现有 API 兼容）、`skills/infra/` 下新增 production adapter 文件（如 `session_policy.py` 或等效，含 `AShareCompletedSessionPolicy` + internal adapter errors）、`skills/data/unified_data/services/sentiment_service.py`（仅 composition root 注入 real clock 时引用；离线注入 seam 保持 `None` 宽松路径）、对应 colocated 测试文件（fake calendar + fake clock）。
- **禁止动**：`skills/data/unified_data/providers/akshare.py`（不得直连取日历）、provider registry/fallback、router、writer、Mongo、cache、client facade、`models/domain/sentiment.py` 既有 canonical 契约字段、Gate-4 相关（`binding_state.json`、Gate-4 CLI）、`skills/data/data-pipeline/**`。`refresh_limit_up_pool` 真实执行仍禁止；生产注入时机与 Gate 归属由 Pascal 在 Design 验收后另行授权。

**EOD-8 生产注入 Gate 授权契约（V0.26 OQ-11 生产注入 Gate，Pascal 明确授权但尚未执行；对应 RFC-03-014 V0.26；本规范为权威可执行契约，T2 Design 承接精确文件 allowlist 与重启/验证命令）**：

**EOD-8.1 授权边界**：本次 Pascal 授权仅含 ① 真实 XSHG calendar 与覆盖区间预检；② timezone-aware real clock 的 production composition root；③ fail-closed E2E 验证；④ 服务重启后的实际行为核验；⑤ 不触发 Provider / Mongo / refresh / cache 写入的只读证明。**不授权（始终禁止）**：外部 Provider 请求、Mongo 连接/DDL/DML、cache put、refresh/upsert、canary、cron/systemd 长期调度配置、网关/webhook、Git 提交或任何秘密读取/输出。本授权**不构成**「production enabled」或「E2E PASS」声明——实际注入与验证仅能在 T6 且 T5 review PASS 后执行。**EOD-7.8 所述「生产注入时机与 Gate 归属由 Pascal 在 Design 验收后另行授权」已由本 V0.26 授权满足**：Gate 归属与时机按 EOD-8.8 执行（T6 Production Activation，仅 T5 PASS 后），其余 EOD-7 离线契约（T1/T2/T3 阶段禁注入）原样保留。

**EOD-8.2 production composition root 候选与依赖方向**：
- **现状事实**：当前仓库无生产 composition root（无 `SystemClock` 实现、无 composition 模块、无 sentiment 生产进程入口）；既有 `UnifiedDataClient._get_sentiment_service()`（`client.py`）是库级装配点，不注入 `completed_session_policy`，本契约不把该 facade 自动视为 production root。
- **候选位置（T2 Design 在下列内裁定精确位置，不得超出）**：
  a) 新增 `skills/data/unified_data/services/composition.py`（最小装配模块，含 `build_production_sentiment_service(clock: Clock | None = None) -> MarketSentimentService` 纯装配函数；`clock=None` 保持离线宽松路径）；
  b) `skills/data/unified_data/services/__init__.py` 扩展（仅当 T2 裁定不新增文件）；
  c) `skills/data/unified_data/client.py` `UnifiedDataClient` 构造（仅当生产入口统一经 client facade，且不得改变 P3-C closure-only allowlist 既有约束语义）；
  d) `scripts/unified_data/` 下新增 production CLI 入口（当前无 sentiment 生产进程入口；若 T2 以仓库事实裁定不存在真实服务进程则排除该项）。
- **依赖方向（唯一允许）**：composition root → `session_policy.AShareCompletedSessionPolicy(clock=SystemClock)` → `date_utils` strict seam（`query_trading_day_status` / `session_close_strict` / `parse_date_strict`）→ `exchange_calendars`；`MarketSentimentService(..., completed_session_policy=policy)` 经既有注入 seam 接收。
- **禁止**：反向依赖（`date_utils` 不得 import 业务层 / `session_policy`）、把 cutoff / 业务语义 / clock 倒灌 `date_utils`、以 `is_trading_day()` 宽松路径作为 production 判定、复制交易日清单。

**EOD-8.3 real clock 契约**：`SystemClock`（T3 新增，实现 `Clock` Protocol）仅返回 timezone-aware `datetime`，统一归一 `Asia/Shanghai`（`datetime.now(tz=ZoneInfo("Asia/Shanghai"))`）。构造期 fail-closed：`AShareCompletedSessionPolicy(clock=...)` 在 `__init__` 即校验 clock（naive / 非 datetime / `now()` 异常 → `NaiveClockError` fail-fast），禁止 `datetime.now()` / `date.today()` 隐式读取。错误描述可观察但无敏感数据：错误实例仅携带 date（输入）、clock_source_class（`type(clock).__name__`，real/fake 判别）、reason（人类可读原因）；**不携带**日历全量数据、不携带凭证、不携带用户数据。

**EOD-8.4 真实 XSHG calendar preflight 验证项（T6 执行；T4 仅以受控 real-calendar dry-run 验证脚本正确性，不执行注入/重启）**：

| # | 验证项 | 判定 | 禁止 |
|---|---|---|---|
| 1 | identity：`exchange_calendars.get_calendar('XSHG')` 成功且 calendar identity = XSHG | PASS/FAIL | 无 |
| 2 | version/库：现场读取 `exchange_calendars.__version__`，与当前环境记录对照（历史实测 4.13.2；**不得假设**，必须现场读取） | PASS/FAIL（版本漂移记录差异，不自动 pass） | 不得跳过 |
| 3 | timezone：calendar 时区 = Asia/Shanghai（或 close 输出归一后等价的 UTC offset） | PASS/FAIL | 不得以裸 `15:00` 替代 |
| 4 | coverage：first_session / last_session 覆盖窗口记录 | PASS/FAIL | 不得 fallback 到 `TRADING_DAYS_2026` / 周末推断 |
| 5 | 指定样例：至少一个已知交易日（TRADING）/ 一个已知非交易日（NOT_TRADING）/ 一个 session-close（close instant tz-aware）；样例日期由 T2 以 calendar 输出事实裁定，本规范不硬编码 | PASS/FAIL | 不得网络、不得宽松解析、不得裸 `is_trading_day()` |

**EOD-8.5 受控 E2E 验证接口与断言集**：被测单元 = `AShareCompletedSessionPolicy(clock=injectable_clock)`；clock 注入可控 `datetime`（可复现日期/时刻），calendar 注入 fake 或受控 real-calendar（仅本地库调用，无网络）。断言集（六类 + 零写入）：

| # | 场景 | 可复现注入 | 预期 |
|---|---|---|---|
| 1 | 已收盘交易日 | 历史交易日 + clock 晚于 close | `SessionStatus.COMPLETED` |
| 2 | 未收盘交易日 | 当前交易日 + clock 早于 close | `SessionStatus.SESSION_NOT_COMPLETED` |
| 3 | 非交易日 | 明确非交易日 | `SessionStatus.NOT_A_TRADING_DAY` |
| 4 | 未来日期 | 未来交易日 | `SessionStatus.FUTURE_TRADING_DAY` |
| 5 | calendar unavailable / out-of-range | fake calendar → UNAVAILABLE / OUT_OF_RANGE / ERROR | fail-closed：`CalendarUnavailableError` / `DateOutOfRangeError`；service 映射 `ProviderUnavailableError`；**不误判** `NOT_A_TRADING_DAY` |
| 6 | naive clock | clock 返回 naive datetime | 构造期 `NaiveClockError`（fail-fast） |
| 7 | 零写入 | spy/import 审计 | 每条判定路径 `0 provider fetch / 0 writer upsert / 0 cache put / 0 Mongo / 0 网络 / 0 文件写` |

**EOD-8.6 服务重启边界**：仅可使用项目既有服务运维入口；服务名/命令由 T2 以当前仓库事实裁定（当前仓库无 in-repo systemd unit；HEARTBEAT.md 记录的 host 级 cron/systemd 条目——全球市场日报 08:00、SmartMoney 20:30、Argus 20:35、酒店抓取 06:10、auto-push 03:30——均非 OQ-11 目标服务的依据）。若当前没有可安全重启的目标服务 → **fail-stop**，不得臆造或增设 unit。重启前后均需最小健康/行为 check：重启前记录进程/服务状态 + 对已知 completed day 的判定路径结果；重启后重跑同一 check 并对比。

**EOD-8.7 回滚语义**：仅撤销 production composition injection，恢复 `completed_session_policy=None`（离线宽松路径）；**禁止 DB 回滚/删除、禁止自动执行回滚**（回滚动作由 Pascal 明确指令或 T6 失败后人工执行）。失败分类：
- **必须保持 disabled**：calendar preflight 任一验证项 FAIL、real clock 校验失败、E2E 零写入断言 FAIL → 不注入，保持 `None`，回退到 T5 状态。
- **可本地修复后重验**：preflight 脚本缺陷、样例选取错误、环境/路径问题 → 修复后重跑 T4/T6 preflight，不改变契约。
- **注入后观察异常**：service 行为与 EOD-7/EOD-8 契约不符 → 按 T6 rollback 流程撤销注入恢复 `None`，重跑 T4 验证 + T5 review。

**EOD-8.8 阶段分层与 Gate 归属**：T2 Design-only（裁定 root 精确位置 / SystemClock / preflight 命令 / 重启目标 / 健康 check / E2E 运行方式）；T3 local implementation only（仅 composition 模块 + SystemClock + 本地 preflight 脚本 + 单测；禁止激活注入、禁止触碰默认 `None`）；T4 独立离线/受控验证（fake clock/calendar 全断言 + 零写入证明；受控 real-calendar dry-run）；T5 独立 review（RFC/SPEC/DESIGN 一致性 + 授权边界复核）；T6 Production Activation **仅 T5 PASS 后**执行（真实 clock/calendar preflight + 注入 + 既有服务重启 + 前后行为核验）；本次授权不得扩大到禁止对象。

**EOD-8.9 副作用矩阵**：

| 阶段 | 运行时动作 | 授权状态 |
|---|---|---|
| T1（RFC/SPEC） | 0（仅文档） | ✅ 本文档 |
| T2（Design） | 0（仅设计文档） | ✅ 本文档 |
| T3（local implementation） | 0（仅本地代码/单测；禁激活注入、禁网络/Mongo/cache/refresh） | ✅ 本文档 |
| T4（独立验证） | 0（fake/受控环境；受控 real-calendar dry-run 仅本地库，无网络、无注入、无重启） | ✅ 本文档 |
| T5（独立 review） | 0（仅审查） | ✅ 本文档 |
| **T6（Production Activation）** | 真实 clock 读取（`datetime.now(tz=...)`）+ 真实 calendar 本地库读取（无网络）+ 既有服务重启（一次，T2 裁定，不可行则 fail-stop） | ✅ 仅 T5 PASS 后；Pascal 本次授权唯一运行时动作 |
| 始终 0 | Provider 请求 / Mongo 连接/DDL/DML / cache put / refresh/upsert / canary / cron-systemd 长期调度配置 / 网关/webhook / Git 提交 / 秘密读取/输出 | ⛔ 永不授权 |

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

**注册状态（2026-08-03 冻结）**：sentiment 两 capability（`sentiment.market_snapshot` / `sentiment.limit_up_pool`）在 AKShareProvider **未注册**（当前 9 项 capability，含 P3-A sector 2 项，见 §14.4.5.9）；保持 offline stub/defer。上方链为**计划态契约**，仅在 G-1 交易日 live-read 通过 + Pascal 授权后激活（§14.4.5.3 2026-08-03 冻结证据；RESEARCH-03-014 §6 门禁）。

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
"sentiment_limit_up_pool": 3600,  # 1h — 个股涨停池（capability sentiment.limit_up_pool；F6 canonical key，见 SPEC-03-014-F6）
"market_sentiment": 3600,       # 1h — 市场级情绪快照（capability sentiment.market_snapshot；F6 canonical key，见 SPEC-03-014-F6）
# ⚠️ F6 裁定（RFC-03-014-F6 / SPEC-03-014-F6）：`"sentiment"` 不再是 freshness TTL key。
#    `sentiment` 仅保留为 capability domain 前缀（sentiment.market_snapshot / sentiment.limit_up_pool）。
#    禁止在 DEFAULT_TTLS 注册 `"sentiment"`（双 key/alias 会造成 freshness 漂移）。
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
| `03_data_ud_market_sentiment_snapshot` — `sentiment.market_snapshot` | P3-C | `{market, snapshot_date, snapshot_time}` | `{snapshot_date:-1}`, `{snapshot_time:-1}` | 无（物化可追溯数据）；MarketSentimentSnapshot 22 字段 canonical 契约为唯一写入 schema |
| `03_data_ud_market_sentiment_snapshot` — `sentiment.limit_up_pool` | P3-C | `{market, symbol, trade_date}` | `{trade_date:-1}`, `{market:1, trade_date:-1}` | 无（物化可追溯数据）；LimitUpPoolRecord 为唯一写入 schema。读路径 date-level pool filter 为 `{market, trade_date}`（详见 F1 amendment `SPEC-03-014-F1` 键裁定 + F4 amendment `SPEC-03-014-F4` 读 filter 裁定） |

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
| sentiment | `get_market_sentiment(date=None)` | `MarketSentimentSnapshot`（单条，收盘后；已完成交易日可重放，`snapshot_time=close`） | P3-C |
| sentiment | `get_limit_up_pool(date=None)` | `list[dict]`（symbol + reason + days） | P3-C |

**异常边界与默认行为**：

| 方法 | 参数无效/缺失 | router 未注入 | Provider 失败 | 空返回 |
|------|-------------|-------------|-------------|--------|
| `get_sector_snapshot` | `sector_code` 为空 → 抛出 `InvalidSecurityIdError` 或等价 ValueError | —（`UnifiedDataClient` facade 保证 router 始终非空；若 SectorService.router is None → `ProviderUnavailableError("P3-A methods require DataRouter: not injected")`，DESIGN-03-014 §5.1） | → `DataResult.error(provider="error", source_trace=["akshare(error: ...)"])` | → `DataResult.success(data=None/is_empty, provider="akshare")` |
| `get_sector_ranking` | `limit` ≤ 0 → 默认 20；`sector_type` 无效值 → 作为查询参数传递，由 Provider 容纳 | 同上 | 同上 | → `DataResult.success(data=[], provider="akshare")` |
| `get_market_sentiment` | **EOD 校验（V0.22）：`snapshot_date` 非 canonical `YYYY-MM-DD` → `SentimentSessionValidationError(code=INVALID_DATE_FORMAT)`；`snapshot_time != "close"` → `code=INVALID_SNAPSHOT_TIME`；注入 `CompletedSessionPolicy` 后判定非已完成交易日 → `NOT_TRADING_DAY` / `FUTURE_TRADING_DAY` / `SESSION_NOT_COMPLETED`。全部在 provider fetch / writer upsert / cache put 之前 fail-fast** | router 未注入 → `ProviderUnavailableError("MarketSentimentService has no router wired; pass `router=...` at construction time to enable reads.")` | → `DataResult.error(provider="error", ...)` | → `DataResult.success(data=None, provider="empty")` |
| `get_limit_up_pool` | **EOD 校验（V0.22）：显式 `trade_date` 非 canonical `YYYY-MM-DD` 或非已完成交易日 → 同上异常/code；`trade_date=None` 表示最近可用日期，跳过 completed-session 校验** | router 未注入 → 同上 `ProviderUnavailableError` | → `DataResult.error(provider="error", ...)` | → `DataResult.success(data=[], provider="empty")` |

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
| A-006 | FreshnessPolicy flow/sector/market_sentiment/sentiment_limit_up_pool TTL 正确注册（F6 canonical key，见 SPEC-03-014-F6 §2） | `policy.get_ttl("flow") == 43200`、`policy.get_ttl("market_sentiment") == 3600`、`policy.get_ttl("sentiment_limit_up_pool") == 3600`；`"sentiment" not in FreshnessPolicy.DEFAULT_TTLS` | 全部 |
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
| **A-018** | **PR-2 smoke sector**：单板块代码 ≤3 交易日，零持久化写，产出 YAML 报告包含 connectivity/auth/permissions/field_mapping/data_sample/vs_fixture（**R2（2026-08-04）：superseded / out-of-scope——PR-2 预算永久废弃，本验收项不再可执行；P3-A 生产验证改以 §R2.2 完成矩阵 + §R2.4 G-R2-1 read-path census 为准**） | 检查报告文件存在且包含全部六节（历史判据） | T4 P3-A |
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
| **A-032** | **EOD 验证 owner（V0.22，V0.23 Closure-2 修正签名）**：`MarketSentimentService` 四个公开入口（`get_market_sentiment_snapshot` / `get_limit_up_pool` / `refresh_market_sentiment_snapshot` / `refresh_limit_up_pool(trade_date: str, *, p3_writer=None, provider=None)`）为唯一 validation owner；`refresh_limit_up_pool` 的 `trade_date` 必填 canonical `YYYY-MM-DD`，本轮 refresh 不允许 None/latest，校验不得分散到 domain/provider/router/caller | Python 断言：调用任一入口 + fake CompletedSessionPolicy，验证失败路径全部在 service 层抛 `SentimentSessionValidationError`；fake policy 记录 `refresh_limit_up_pool` 收到显式 canonical `trade_date`，happy path 的 provider params 含同一值 | P3-C |
| **A-033** | **EOD 注入 seam（V0.22）**：`CompletedSessionPolicy` 协议可注入 `MarketSentimentService`（`session_status(date: str) -> SessionStatus`，接受 canonical `YYYY-MM-DD`，经 fake calendar + fake clock 判定）；T3 不读真实日历/系统日期/网络 | Python 断言：注入 fake policy 返回各 SessionStatus，断言 service 映射唯一 code | P3-C |
| **A-034** | **EOD 失败语义（V0.22）**：格式非法 / 非 close / 非交易日 / 未来日 / 未完成当日五类失败均唯一 code（`INVALID_DATE_FORMAT` / `INVALID_SNAPSHOT_TIME` / `NOT_TRADING_DAY` / `FUTURE_TRADING_DAY` / `SESSION_NOT_COMPLETED`），且每个失败 `0 provider fetch / 0 writer upsert / 0 cache put` | Python spy 断言（mock provider / mock writer / mock cache） | P3-C |
| **A-035** | **`total_turnover` 强制 None（V0.22）**：默认 offline stub、两条 canonical fixture、`MarketSentimentSnapshot.from_dict` 输出的 `total_turnover` 均为 `None`；任意输入提供非 None（含资金净流入映射）时输出仍为 `None` | Python 断言：stub 默认 payload、fixture、`from_dict({"total_turnover": 123})` | P3-C |
| **A-036** | **测试矩阵精确 allowlist（V0.22）**：SPEC §8.1 不再引用不存在的 `tests/test_market_sentiment.py`；已存回归基线（Gate 证据：`test_sentiment_service.py` / `test_sentiment_limit_up_pool.py` / `test_router_p3_freshness_domain.py` / `test_mapping_sentiment.py` / `test_provider_phase3.py`，98 passed）与 `test_market_sentiment_22field.py` 既有基线并列；T3 只增补真实 colocated 测试文件 | heading-slice 文本扫描 + `pytest skills/data/unified_data/tests/test_market_sentiment_22field.py skills/data/unified_data/tests/test_sentiment_service.py skills/data/unified_data/tests/test_mapping_sentiment.py skills/data/unified_data/tests/test_sentiment_limit_up_pool.py` 通过 | P3-C |
| **A-037** | **生产 `CompletedSessionPolicy` 契约（V0.25 OQ-11 裁定）**：① 唯一事实源 = `skills.infra.date_utils`（`exchange_calendars.get_calendar('XSHG')`，实测 `exchange_calendars==4.13.2`、timezone `Asia/Shanghai`、`session_close` = UTC 07:00 = Shanghai 15:00），production policy 仅经正式 adapter/contract 消费，禁止复制清单 / 直连 provider 网络 / 以 `TRADING_DAYS_2026` 为真相 / 裸 `is_trading_day()` 为唯一判定；② production-only adapter（`AShareCompletedSessionPolicy`）显式注入 timezone-aware clock，禁止 `datetime.now()` 隐式读取；③ EOD-7.5 判定表全路径（invalid / calendar unavailable / 越界 / not trading / future / pre-close / completed）用 fake calendar + fake timezone-aware clock 覆盖且零 I/O；④ 未知依赖状态不误判 `NOT_A_TRADING_DAY`，fail-closed 不落入 hardcoded fallback；⑤ 四态 `SessionStatus` 与五稳定 code 兼容性不变 | 静态核对 §3.3 EOD-7 系列 + Python 断言（fake calendar + fake clock，断言判定表与零副作用，断言无 `datetime.now()` 隐式读取） | P3-C（OQ-11） |
| **A-038** | **OQ-11 生产注入 Gate 授权契约（V0.26，Pascal 明确授权但尚未执行）**：① 授权边界仅含真实 XSHG calendar 与覆盖区间预检 / timezone-aware real clock 的 production composition root / fail-closed E2E 验证 / 服务重启后实际行为核验 / 零写入只读证明，不授权 Provider/Mongo/DDL-DML/cache put/refresh/canary/cron-systemd 长期调度/网关-webhook/Git/秘密；② composition root 候选（`services/composition.py` / `services/__init__.py` 扩展 / `client.py` 构造 / `scripts/unified_data/` CLI）与依赖方向（root → `AShareCompletedSessionPolicy(clock=SystemClock)` → `date_utils` strict seam → `exchange_calendars`，禁反向依赖与业务语义倒灌 date_utils）；③ real clock 仅 timezone-aware datetime 归一 Asia/Shanghai，构造期 `NaiveClockError` fail-fast，错误描述无敏感数据；④ calendar preflight 五项（identity / version-库 / timezone / coverage / 指定 trading-not_trading-session_close 样例）禁网络与 fallback；⑤ E2E 六类断言 + 每路径零写入（0 Provider/0 Mongo/0 cache/0 refresh/0 网络/0 文件写）；⑥ 服务重启仅既有运维入口、T2 以仓库事实裁定、无可安全重启目标则 fail-stop、禁臆造/增设 unit、重启前后最小健康/行为 check；⑦ 回滚仅撤销 production composition injection 恢复 `completed_session_policy=None`，禁 DB 回滚/删除、禁自动回滚、失败分类明确；⑧ T2 Design-only → T3 local implementation only → T4 独立离线/受控验证 → T5 独立 review → T6 Production Activation 仅 T5 PASS 后执行；⑨ 副作用矩阵仅 T6 有运行时动作（真实 clock/calendar 本地读取 + 既有服务重启一次），其余阶段全 0 | 静态核对 §3.3 EOD-8 系列 + T2/T3/T4 各阶段验收命令按 EOD-8.4/8.5/8.6 执行；`git diff --check` exit 0 | P3-C（OQ-11 生产注入 Gate） |

---

## 8. 测试要求

### 8.1 单元测试

| 测试文件 | 覆盖内容 | 预期用例数 | 子阶段 | 是否需网络 |
|---|---|---|---|---|
| `test_sector_snapshot.py` | SectorSnapshot 构造、from_dict、字段边界、枚举值 | 8 | P3-A | 否 |
| `test_sector_service.py` | get_sector_snapshot/ranking（mock provider）、空数据、error 分支 | 6 | P3-A | 否 |
| `test_capital_flow.py` | CapitalFlowRecord 构造、from_dict、符号约定、北向空处理 | 10 | P3-B | 否 |
| `test_flow_service.py` | get_capital_flow/northbound_flow（mock provider）、分页、限流 | 6 | P3-B | 否 |
| `test_market_sentiment_22field.py` | MarketSentimentSnapshot 构造、from_dict、温度范围；**V0.22 增补：`total_turnover` 强制 None 断言（stub 默认 + fixture + from_dict 非 None 输入）** | 32（既有）+ 增补 | P3-C | 否 |
| `test_sentiment_service.py` | get_market_snapshot/limit_up_pool（mock provider）、连板交叉验证；**V0.22 增补：EOD 验证 owner + CompletedSessionPolicy 注入 + 5 类失败唯一 code + 0 side-effect spy；V0.23 Closure-2 增补：`refresh_limit_up_pool(trade_date)` 显式 canonical 日期 + fake policy 收到同一 `trade_date` + provider params 含同值** | 25（既有）+ 增补 | P3-C | 否 |
| `test_sentiment_limit_up_pool.py` | limit_up_pool 读/写路径（mock provider）；**V0.24（Scope Reconcile）增补：fake refresh / missing-writer regression 显式提供 canonical `trade_date` + mandatory-date 契约与 ProviderUnavailable/error behavior 验证** | 15（既有）+ 增补 | P3-C | 否 |
| `test_mapping_sentiment.py` | AKShare→Canonical 映射、**V0.22 增补：total_turnover 不得映射资金净流入负例** | 23（既有）+ 增补 | P3-C | 否 |
| `test_provider_phase3.py` | AKShareProvider Phase 3 新增 capability 的 stub/fake fetch；**STUB_COLUMNS 双定义等价性测试**（`stub_columns.STUB_COLUMNS == providers.STUB_COLUMNS`，DESIGN-03-014 §4.1） | 27（既有） | 全部 | 否 |

### 8.2 Fixture

| Fixture 文件 | 内容 | 子阶段 |
|---|---|---|
| `skills/data/unified_data/tests/fixtures/sector_fixtures.py` | 2 条 SectorSnapshot：industry（白酒）+ concept（AI），正常交易日 + 极端行情 | P3-A |
| `skills/data/unified_data/tests/fixtures/flow_fixtures.py` | 2 条 CapitalFlowRecord：含北向数据（沪深港通标的）+ 不含北向（非标的） | P3-B |
| `skills/data/unified_data/tests/fixtures/sentiment_fixtures.py` | 2 条 MarketSentimentSnapshot：正常交易日 + 极端行情（大量涨停）；**V0.22：两条 fixture 的 `total_turnover` 均强制 `None`（无合规来源，禁止伪造成交额）** | P3-C |

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
- **PR-2/3/4 单标的有界调用**（**R2（2026-08-04）：PR-2 已 superseded / out-of-scope、预算永久废弃，本约束仅适用于 PR-3/PR-4，见 §R2**）：每个 smoke 调用仅使用单板块代码/单标的/单日期，日期窗口 ≤3 个交易日，每 capability API 调用 ≤3 次，不自动重试
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
| G-A-2 | AKShareProvider 首次真实调用 `sector.snapshot` / `sector.ranking`（**R2（2026-08-04）：superseded / out-of-scope——name_em 实时板块排行移出 Phase 3 目标，G-A-2 不再授权任何 sector 实时调用；P3-A 改以 §R2.4 G-R2-1 read-path census 为准**） | AKShare API | [待 Pascal 在具体 Gate 授权时确认的请求预算/计量单位]；当前 Gate 仅确认首次 smoke 可行，不做全量预算估计 | smoke 成功 + 日志审核 | P3-A |
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
| **PR-2** | ~~**AKShare Provider smoke：`sector.snapshot` + `sector.ranking`** — 单板块代码（`BK0489`），≤3 个交易日窗口，AKShare 匿名只读调用。**零持久化写**~~ — **superseded / out-of-scope（R2，2026-08-04）**：name_em 实时板块排行移出 Phase 3 实现/生产验证目标，PR-2 预算**永久废弃**；本行保留为历史 Gate 定义，**不得执行**（不得 unblock/retry/创建 replacement probe/改用其他 AKShare endpoint；禁止调用 `cons_em`）。P3-A 仅保留盘后/历史 sector read-path 验证，见 §R2.2 | ~~PR-1 pass（AKShare smoke 不依赖 PR-0 pass）~~（历史触发条件，不再适用） | ~~AKShare API 调用 1-2 次、每小时配额~~（预算废弃） | ~~API 返回错误/字段完全不匹配/json 解析异常 → 停止；差异仅记录在字段映射报告中~~（历史停止条件，不再适用） | P3-A | Dev/Agent |
| **PR-3** | **AKShare Provider smoke：`flow.capital_flow_daily` + `flow.northbound_daily`** — 单标的（`600519` / `000001`），≤3 个交易日窗口，AKShare 匿名只读调用 | PR-1 pass（AKShare smoke 不依赖 PR-0 pass；可并行于 PR-4；**R2（2026-08-04）：PR-2 已废弃，不再存在与 PR-2 的并行语义，见 §R2**） | AKShare API 调用 2-4 次、每小时配额 | API 失败/空返回/北向字段缺失 → 停止并记录 | P3-B | Dev/Agent |
| **PR-4** | **AKShare Provider smoke：`sentiment.market_snapshot` + `sentiment.limit_up_pool`** — 单日期，AKShare 匿名只读调用 | PR-1 pass（AKShare smoke 不依赖 PR-0 pass；可并行于 PR-3；**R2（2026-08-04）：PR-2 已废弃，不再存在与 PR-2 的并行语义，见 §R2**） | AKShare API 调用 2 次、每小时配额 | API 失败/核心字段缺失 → 停止并记录 | P3-C | Dev/Agent |
| **PR-DDL-P3A** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_market_sector_snapshot` + 索引**（**仅 P3-A 已授权冻结**；P3-B/P3-C 的 PR-DDL 仍阻塞，见 §14.6.4。**R2 注：PR-2 已 superseded / out-of-scope（2026-08-04），不再作为 DDL 前置；PR-DDL-P3A 冻结状态不变——B1-P3A 已冻结，权威契约见 §14.6.4 / DESIGN §6.4**） | **仅当未来新 Provider Gate 完成（如 §R2.4 G-R2-1 read-path census 或新授权 smoke）+ Pascal 独立确认**（历史触发 `PR-2 pass` 已随 R2 废弃） | MongoDB 元数据写入——集合创建、索引构建 | 写权限不足/长时间索引重建 → 停止；schema 版本须与 SPEC §3.1 一致；DDL 执行/rollback/audit/exit code 按 §14.6.4 冻结契约（权威定义 DESIGN §6.4） | P3-A | Pascal 手动确认 |
| **PR-DDL-P3B** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_stock_capital_flow` + 索引**（**P3-B 已授权冻结**；P3-C 的 PR-DDL 仍阻塞，见 §14.6.bis） | PR-3 pass + Pascal 独立确认 | MongoDB 元数据写入——集合创建、索引构建 | 写权限不足/长时间索引重建 → 停止；schema 版本须与 SPEC §3.2 一致；DDL 执行/rollback/audit/exit code 按 §14.6.bis 冻结契约（权威定义 DESIGN §6.4.bis） | P3-B | Pascal 手动确认 |
| **PR-DDL-P3C** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_market_sentiment_snapshot` + 索引**（**P3-A + P3-B + P3-C 已全部授权冻结**，见 §14.6.4 / §14.6.bis / §14.6.ter） | PR-4 pass + Pascal 独立确认 | MongoDB 元数据写入 | 写权限不足/长时间索引重建 → 停止；schema 版本须与 SPEC §3.3 一致；DDL 执行/rollback/audit/exit code 按 §14.6.ter 冻结契约（权威定义 DESIGN §6.4.ter） | P3-C | Pascal 手动确认 |
| **PR-CANARY-P3x** | **手动 Canary**：一次 refresh 调用（手动触发，非 cron），写入对应集合，验证 DataResult 返回正常 | 对应 PR-DDL pass + Pascal 确认 | 真实 MongoDB 写入 | 写入失败/数据质量异常 → 停止不升级到 cron | P3-A/B/C | Pascal 手动执行 |

**关键约束**：
- PR-1（MongoDB 预检）**不读业务数据**——仅 ping + listCollections 命令。不得对 `stock_basic_info`、`market_quotes` 等 TA-CN 集合做查询
- PR-3/PR-4 的输出必须**分别记录**连通性、认证、权限、字段映射四方面的观测结论。不得将一次调用结果泛化为全局结论（**R2（2026-08-04）：PR-2 已 superseded / out-of-scope，从本约束移除，见 §R2**）
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
- [x] **OQ-9（T4 新增，V0.33 已纠正）**：Provider smoke 结论中字段映射差异的阈值如何设定？**已裁定**：字段映射匹配率 ≥70% 才可通过、<70% fail-stop（对齐 `MATCH_RATIO_CONDITIONAL=0.70` / DESIGN §15.6.2 / §R3.3）；RFC §6.3 / 本 SPEC §14.8 旧 >50% 提议已被 RFC-03-014 V0.33 P0 阈值纠正替换并随本卡同步。
- [ ] **OQ-10（2026-08-03 新增）**：实时市场情绪路径（盘中实时 snapshot）是否立项？已裁定属未来独立 capability——需独立 Provider/字段契约/freshness/时间边界与新的用户授权，本 Phase 3 不放行。另：`stock_market_fund_flow` 在 2026-08-03 live-read 中单次 `ConnectionError`，若未来需要大盘资金流侧数据，须 Pascal 独立授权新的交易日 live-read（预算已耗尽，见 §14.4.5.3）。
- [x] **OQ-11（V0.22 新增，V0.25 已裁定，V0.26 生产注入 Gate 已授权未执行）**：生产环境 `CompletedSessionPolicy`（真实 A 股交易日历 + 系统时钟）由哪个 Gate/Provider 注入？**V0.25 裁定**：底座唯一事实源 = `skills.infra.date_utils`（动态 `exchange_calendars.get_calendar('XSHG')`，实测 `exchange_calendars==4.13.2`、timezone `Asia/Shanghai`、`session_close` = UTC 07:00 = Shanghai 15:00）；生产 policy 通过正式 adapter/contract 消费（四态判定链、fail-closed、可审计、兼容五稳定 code，见 §3.3 EOD-7 系列与 RFC-03-014 §5.3.1 EOD-7）；offline adapter（`AShareCompletedSessionPolicy` + date_utils strict seam）已由 DESIGN-03-014 V0.32 §OQ-11 定义并验收，默认 `completed_session_policy=None` 离线宽松路径保持不变。**V0.26（2026-08-04，Pascal 明确授权但尚未执行）**：生产注入 Gate 授权契约冻结——授权边界仅含真实 XSHG calendar 与覆盖区间预检 / timezone-aware real clock 的 production composition root / fail-closed E2E 验证 / 服务重启后实际行为核验 / 零写入只读证明（见 §3.3 EOD-8 系列与 RFC-03-014 §5.3.1 EOD-8）；后续分层 T2 Design-only → T3 local implementation only → T4 独立离线/受控验证 → T5 独立 review → T6 Production Activation 仅 T5 PASS 后执行；本次授权不得扩大到 Provider/Mongo/cache/refresh/cron/网关/webhook/Git/秘密。

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

> **V0.24（Scope Reconcile）**：本表为 10→22 字段迁移的**总体**变更清单（历史/总路线）。本轮 P3-C T3 仅允许 §12.bis.4「P3-C V0.24/V0.31 closure-only T3 allowlist」中的 8 个文件；本表中不在该 8 项内的 P3-C 相关行（`providers/_stub_columns.py`、`providers/__init__.py`、`models/domain/__init__.py`）对本轮标记为 **superseded / non-applicable**，Developer 不得从本表取额外路径。

#### 12.bis.1 必需变更（Allowlist）

| 路径 | 允许操作 | 约束 |
|------|---------|------|
| `models/domain/sentiment.py` | `MarketSentimentSnapshot` dataclass 从 10 字段（`market`, `sentiment_type`, `market_date`, `score`, `sample_size`, `source`, `provider`, `fetched_at`, `notes`, `metadata`）重构为 22 字段 canonical 契约（`snapshot_date`, `snapshot_time`, `market`, `limit_up_count`, `limit_down_count`, `limit_up_count_ex_st`, `limit_down_count_ex_st`, `advance_count`, `decline_count`, `flat_count`, `total_listed_count`, `market_temperature`, `total_turnover`, `hot_concepts`, `continuous_limit_up`, `max_continuous_days`, `northbound_net_flow`, `limit_up_pool`, `limit_down_pool`, `fetched_at`, `provider`, `raw_payload`），唯一键由 `{market, sentiment_type, market_date}` 改为 `{market, snapshot_date, snapshot_time}`；`from_dict()` 同步更新；关闭 `frozen=True, slots=True`（按 SPEC §3.3 可修改的 dataclass 模式）。**V0.22：`from_dict()` 中 `total_turnover` 强制规范化为 `None`（与 `northbound_net_flow` 恒 None 同构 fail-stop）；`snapshot_time` 保持宽松解析（不裁决业务语义，非 close 拒绝在 service 层）** | 不得保留旧 10 字段的任何引用在新 dataclass 中；不得在`from_dict()` 中引用 `sentiment_type`、`market_date`、`score`、`sample_size`、`notes`、`metadata` 等淘汰字段 |
| `services/sentiment_service.py` | 更新引用类型：所有 `get_market_sentiment_snapshot()` 返回类型改为新 `MarketSentimentSnapshot`；`refresh_market_sentiment_snapshot()` 写入路径基于新 schema。**V0.22：四个公开入口（`get_market_sentiment_snapshot` / `get_limit_up_pool` / `refresh_market_sentiment_snapshot` / `refresh_limit_up_pool`）为唯一 EOD validation owner；新增 `CompletedSessionPolicy` 注入参数（`session_status(date) -> SessionStatus`，fake calendar + fake clock）；非 close 输入在 service 层 fail-fast（`INVALID_SNAPSHOT_TIME`）。V0.23（Closure-2）：`refresh_limit_up_pool` 签名冻结为 `refresh_limit_up_pool(trade_date: str, *, p3_writer=None, provider=None)`，`trade_date` 必填 canonical `YYYY-MM-DD`，本轮 refresh 不允许 None/latest，happy path 将同一 `trade_date` 传入 provider params 并用于 date-scoped cache key** | 不改动 read path 的 capability 注册逻辑；不改动 `PersistenceResult`；不改动三态守卫；`completed_session_policy=None` 时保持现有离线宽松路径（不破坏既有测试） |
| `skills/data/unified_data/tests/fixtures/sentiment_fixtures.py` | fixture 数据从 10 字段重建为 22 字段 canonical 映射；覆盖正常交易日 + 极端行情两种场景。**V0.22：两条 fixture 的 `total_turnover` 强制为 `None`** | 至少 2 条记录；所有非 None 字段填充合法值 |
| `skills/data/unified_data/tests/test_market_sentiment_22field.py` | **V0.22（既有文件增补）**：追加 `total_turnover is None` 断言（默认构造、stub 默认 payload、from_dict 非 None 输入 → 输出仍 None）；断言更新：字段计数从 10→22；唯一键断言从 `sentiment_type`→`snapshot_date+snapshot_time`；温度范围验证；列表长度约束 | 不得缩减已有测试覆盖的边界条件；`tests/test_market_sentiment.py` 不存在，禁止引用 |
| `skills/data/unified_data/tests/test_sentiment_service.py` | service 层 fixture 引用更新；Spy 断言更新。**V0.22（既有文件增补）**：EOD 验证 owner 契约——fake CompletedSessionPolicy 注入 + spy 证明 5 类失败唯一 code + `0 provider fetch / 0 writer upsert / 0 cache put`；close + completed day 走现有离线路径 | 同上 |
| `skills/data/unified_data/tests/test_mapping_sentiment.py` | **V0.22（既有文件增补）**：追加「资金净流入不得映射 `total_turnover`」负例（mapping/input 提供非 None `total_turnover` 或资金净流入字段时，输出仍 `None`） | 不得缩减已有测试覆盖的边界条件 |
| `providers/_stub_columns.py` | `sentiment.market_snapshot` STUB_COLUMNS 更新为 22 字段 canonical 列。**V0.23（Closure-2）：本轮 P3-C T3 non-applicable（不在 §12.bis.4 closure-only 8 项内，superseded）** | 与 `providers/__init__.py` 保持孪生等价 |
| `providers/__init__.py` | 同上同步更新。**V0.23（Closure-2）：本轮 P3-C T3 non-applicable（不在 §12.bis.4 closure-only 8 项内，superseded）** | 保持与 `_stub_columns.py` 孪生等价 |
| `providers/sentiment_stub.py` | **V0.22（T3 最小 allowlist 追加）**：`_DEFAULT_SENTIMENT_PAYLOAD` 的 `total_turnover` 由 `850_000_000_000.0` 改为 `None`（无合规来源，禁止伪造成交额）；docstring 同步 | 仅改默认 payload 与注释；不改 provider 协议/能力声明 |
| `models/domain/__init__.py` | 确认 `MarketSentimentSnapshot` 仍在导出列表（保持不变）。**V0.23（Closure-2）：本轮 P3-C T3 non-applicable（不在 §12.bis.4 closure-only 8 项内，superseded）** | 不改变导出符号名 |

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

#### 12.bis.4 P3-C V0.24/V0.31 closure-only T3 allowlist

本 closure-only allowlist 由 P3-C Principal Closure-2（RFC/SPEC-03-014 V0.23、DESIGN-03-014 V0.30）冻结，并经 **用户授权 scope reconciliation（RFC/SPEC-03-014 V0.24、DESIGN-03-014 V0.31）** 最小扩展——原因：public `refresh_limit_up_pool` 必填日期迁移影响既有 colocated 回归（旧 T3 retries exhausted；恢复验证实测 161 passed / 4 failed，`tests/test_sentiment_limit_up_pool.py:283` 遗留 TypeError 表明测试 allowlist 漏项）。对本轮 P3-C T3 **优先于所有旧 Phase-3 总体迁移/实施范围表**（本 SPEC §12.bis.1、DESIGN-03-014 §8.1/§8.2 及任何 P3-C 相关总表）。T3 仅允许修改以下 **8 个文件**（三层路径集合逐项、严格相同；heading-slice 提取必须精确等于此集合，不得含第 9 项）：

1. `skills/data/unified_data/models/domain/sentiment.py`
2. `skills/data/unified_data/providers/sentiment_stub.py`
3. `skills/data/unified_data/tests/fixtures/sentiment_fixtures.py`
4. `skills/data/unified_data/services/sentiment_service.py`
5. `skills/data/unified_data/tests/test_market_sentiment_22field.py`
6. `skills/data/unified_data/tests/test_sentiment_service.py`
7. `skills/data/unified_data/tests/test_mapping_sentiment.py`
8. `skills/data/unified_data/tests/test_sentiment_limit_up_pool.py`

**第 8 项唯一职责**：`skills/data/unified_data/tests/test_sentiment_limit_up_pool.py` 仅用于更新既有 fake refresh / missing-writer regression，使其显式提供 canonical `trade_date`，并验证新的 mandatory-date 契约与原有 ProviderUnavailable/error behavior。**不得**引入任何 Provider/registry/router/writer/Mongo/cache/client/network/refresh activation/scheduling 文件。原 7 项中的 `test_sentiment_service.py` 继续负责 mandatory-date、稳定错误码和零副作用 spies；新增第 8 项**不得**成为扩大生产范围的依据。保留全部冻结项：offline stub/defer；AKShare sentiment 未注册、live-read 不重跑；`total_turnover=None`；OQ-10/OQ-11；F6 TTL/key；真实 refresh 仍禁止。

**Blocklist（显式禁止，否定语义）**：`providers/akshare.py`、provider registry/fallback、router、writer、Mongo、cache、client facade、refresh activation、网络、外部 provider、调度均不得在本轮 T3 修改/激活。§12.bis.1 总表中不在上述 8 项内的 P3-C 相关行对本轮标记为 **superseded / non-applicable**，Developer 不得从旧表取额外路径。`refresh_limit_up_pool` 本身不得被排除为「activation」：离线 service 签名/guard/test（含 `trade_date` 契约）属 T3 允许范围，真实 refresh 执行仍禁止。

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
| PR-2: sector smoke | ~~`akshare.stock_board_industry_cons_em("BK0489")`~~ — **superseded / out-of-scope（R2，2026-08-04）**：name_em 实时板块排行移出 Phase 3 目标，PR-2 预算永久废弃，本行保留为历史副作用定义、**不得执行**（禁止为 name_em 新建 recovery/替代 endpoint/实时 refresh/live retry；禁止调用 `cons_em`） | ~~AKShare 匿名 API 调用（1 次/调用）；网络流量（~KB）~~（历史） | 低 | ~~单代码限量；≤3 日窗口；零持久化写~~（历史缓解措施，不再适用） |
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
- AKShare 跳过 PR-0 检查——PR-3/PR-4 可独立于 PR-0 直接执行匿名只读 smoke（**R2（2026-08-04）：PR-2 已 superseded / out-of-scope、预算永久废弃，从可独立执行清单中移除，见 §R2**）
- PR-0 审计结果由 Pascal 审阅确认后进入 PR-1

### 14.4 真实 Provider Smoke 规程

#### 14.4.1 通用规则

| 维度 | 约束 |
|---|---|
| 范围 | 子阶段对应的 capability 各选一（共 6 个 capability） |
| 标的选择 | sector: 单板块代码（推荐 `BK0489`「行业板块」）——**R2（2026-08-04）：PR-2 已 superseded / out-of-scope，sector 实时 smoke 不再执行（见 §R2.2）**；flow: 单标的（推荐 `600519` 沪市 + `000001` 深市）；sentiment: 单日期 |
| 日期窗口 | ≤3 个交易日（推荐最近一个完整交易日 + 前两个交易日） |
| 写入 | **零写入**：不写物化集合、不写 Cache、不写 AuditLogger、不写 QualitySummary。仅打印/记录到本地文件 |
| API 调用次数 | 每 capability ≤3 次（单标的 × 单日期 × 重试 0 次）。仅成功调用 1 次 + 异常不自动重试 |
| 输出 | 每个 smoke 调用输出一个「capability smoke 报告」（见 §14.4.2） |
| 并行 | PR-2/PR-3/PR-4 相互独立，可并行执行（**R2（2026-08-04）：PR-2 已 superseded / out-of-scope，并行语义仅适用于 PR-3/PR-4，见 §R2**） |

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

**2026-08-03 交易日 live-read 补充冻结（G-1 前置，本卡同步）**：受控单次 live-read（`trade_date=20260803`）——`stock_zt_pool_em` success 55 行（16 列，列名与 SDK 1.17.54 静态一致）、`stock_zt_pool_dtgc_em` success 2 行（16 列）、`stock_market_fund_flow` 单次 `ConnectionError`（row_count=0）。边界 PASS（零重试/零 fallback/零 Mongo/零写入），**provider_evidence=fail**（总体 Provider 证据失败）。zt_pool/dtgc_pool 交易日非空仅证明局部池子端点可用，**不得夸大为可激活 Provider**；`stock_market_fund_flow` 仍不可用，且其返回列无「成交额」，不得映射 `total_turnover`。调用预算已耗尽（3/3），冻结报告 `/tmp/yquant-p3c-live-read-20260803/report.json` 只读、不得重跑；任何新 live-read 须 Pascal 独立授权。时间语义：当前目标为已完成交易日/收盘后/可重放，`snapshot_time` 仅 `close`（2026-08-03 裁定）。详细冻结表见 RFC-03-014 §13.4.5.11。

#### 14.4.5.4 PR-2 sector SSL 网络停止诊断边界

> **R2 注（2026-08-04）**：本节为 **历史冻结事实**。Pascal 范畴裁定将 `name_em` 实时板块排行移出 Phase 3 实现/生产验证目标，**PR-2 已 superseded / out-of-scope、预算永久废弃**——本节记录的 SSLError 与「单变量网络诊断」路径**不得**作为 P3-A 生产能力失败或后续 recovery 依据，也不得据此发起任何 live retry / 替代 endpoint / recovery（见 §R2 与 P3-A readonly-gate SPEC §0.2）。以下内容保留为历史定义。

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
- ~~仅允许后续**单变量网络诊断**（切换网络出口、验证 AKShare 上游可达性、检查 TLS 版本），且须 Pascal 独立授权，不在本 T1 阶段执行~~ — **superseded（R2，2026-08-04）**：PR-2 预算永久废弃，**禁止**据此发起任何 live retry / 单变量网络诊断后重试 live-read（见 §R2.1 / §R2.2）。
- PR-2 的 expected 字段集在 T2 须基于 AKShare 公开文档与离线 fixture 推断更新，并明确标注「未 live-read 验证」；**不得**以「需要 live-read 验证」为由阻塞 T2。

#### 14.4.5.5 单次 live-read 精确调用预算与零写入边界

**精确预算（本次 B2 已用尽）**：

| PR | endpoint | 本次实际调用 | 预算上限 | 剩余 |
|---|---|---|---|---|
| PR-2 | `stock_board_industry_cons_em` | 2（均 SSLError） | 2 | 0 —— **R2（2026-08-04）：PR-2 预算永久废弃（superseded / out-of-scope），剩余预算不再消耗** |
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
3. PR-2 的 expected 字段集已基于公开文档推断更新，且明确标注「未 live-read 验证」。（**R2（2026-08-04）：PR-2 已 superseded / out-of-scope；本条为历史 T2 验收项，不再作为 P3-A 实时验证依据，见 §R2.2**）
4. 单次 live-read 预算与零写入边界在 DESIGN §15.x 显式声明，且 T2 未重跑 live-read。
5. smoke 报告账本字段（provider_attempts/实际调用数/retry_count/fallback_count/mongo_calls/write_operations）已在 reporter 定义最小实现；**不包含** `worktree_changed` 与 `empty_semantics`（X2 已移除）。
6. 单元/fixture 测试、离线回归、静态零写入扫描、后续独立 live-read 的验证计划已定义（不在本阶段执行 live-read）。
7. ~~PR-2 SSL 网络诊断仅允许后续单变量网络诊断，未混进 mapping 修复或自动重试~~ — **superseded（R2，2026-08-04）**：PR-2 预算永久废弃，**禁止**据此发起任何 live retry / 单变量网络诊断后重试 live-read（§R2.1）。

#### 14.4.5.8 与既有条文的关系

- 本 §14.4.5 是 §14.4（真实 Provider Smoke 规程）在 B2 冻结证据上的**精确化与冻结**，不修改 §14.4.1 通用规则、§14.4.2 报告模板、§14.4.3 报告存储、§14.4.4 失败与偏差处理的既有条文。
- 不修改 §14.6.x DDL 冻结契约（P3-A/B/C 三者仍冻结）。
- 不修改 §3 domain object 字段定义（Pascal 已选 C，§3 字段定义不变）。
- 不修改既有用户授权范围（PR-0 ~ PR-4、PR-DDL-* 的授权语义不变）。

#### 14.4.5.9 B2 全 capability 映射裁决总表

每项 capability 的三态裁决（可真实映射/保持线下 stub/明确 fail-stop），AKShareProvider 注册状态取自当前代码基线（截至 2026-07-29）：

| Capability | B2 实测状态 | AKShareProvider 注册状态 | 映射裁决 | 依据 |
|---|---|---|---|---|
| `sector.snapshot` | SSL 失败（SSLError） | ✅ P3-A stub（注册，无真实调用路径） | ~~**offline stub** — 预期字段集基于 AKShare 公开文档推断，标注「未 live-read 验证」~~ — **out-of-scope（R2，2026-08-04）**：name_em 实时板块排行移出 Phase 3 目标、PR-2 预算永久废弃，**禁止 live-retry / 单变量网络诊断后重试**；本裁决保留为历史定义（见 §R2.2 / §14.4.5.4 R2 注） | §14.4.5.4 PR-2（历史） |
| `sector.ranking` | SSL 失败（同 endpoint） | ✅ P3-A stub | ~~**offline stub** — 同 sector.snapshot~~ — **out-of-scope（R2，2026-08-04）**：同 sector.snapshot（禁止 live-retry，历史定义，见 §R2.2） | §14.4.5.4（历史） |
| `flow.capital_flow_daily` | 成功（`stock_individual_fund_flow`，均 success） | ❌ 未注册（当前代码仅含 9 项 capability，缺 flow + sentiment 4 项） | **real-mappable** — B2 已验证 endpoint 返回数据；T3 须注册到 AKShareProvider | §14.4.5.2 PR-3 |
| `flow.northbound_daily` | success 但语义不匹配（持股历史≠净流入） | ❌ 未注册 | **fail-stop（Pascal C）** — capability 保留但 fetch 路径不指向真实 endpoint；`northbound_net_inflow` 恒 None | §14.4.5.2 Pascal C |
| `sentiment.market_snapshot` | success 但空返回（row_count=0） | ❌ 未注册 | **offline stub** — verdict=fail（X2 保守）；须交易日 live-read 复验 | §14.4.5.3 Pascal X2 |
| `sentiment.limit_up_pool` | success 但空返回（row_count=0） | ❌ 未注册 | **offline stub** — 同 market_snapshot | §14.4.5.3 |

**AKShareProvider 注册缺口**：当前 `AKShareProvider`（`akshare.py`）仅声明 9 项 capability（7 项 Phase 1D + 2 项 P3-A sector）。`flow.capital_flow_daily`、`flow.northbound_daily`、`sentiment.market_snapshot`、`sentiment.limit_up_pool` 四项**未注册**。T3 须按映射裁决逐项注册：real-mappable 的 `flow.capital_flow_daily` 须注册真实调用路径；offline stub 的 sentiment 和 fail-stop 的 northbound 可注册 stub 路径或暂不注册。

> **2026-08-03 更新（本段 superseded 部分）**：sentiment 两 capability 保持 offline stub/未注册、**defer**——2026-08-03 live-read 总体 provider_evidence=fail（§14.4.5.3），局部池子端点非空不得夸大为可激活 Provider。本段 B2 时点「offline stub 的 sentiment 可注册 stub 路径」指引 superseded：注册前必须过 G-1 交易日 live-read + Pascal 授权（RFC-03-014 §13.4.5.11；RESEARCH-03-014 §6）。

#### 14.4.5.10 Refresh 授权前状态机

`refresh_xxx()` 方法在对应 Gate 授权前的行为契约：

| 状态 | 条件 | `refresh_xxx()` 行为 | 信令 |
|---|---|---|---|
| **未授权（unauthorized）** | `p3_writer=None` | 抛出 `ProviderUnavailableError`；不执行 Provider fetch、不写物化 | 异常 |
| **已注入但未实现（injected-not-implemented）** | `p3_writer` 已注入但 refresh happy-path 未实现 | 抛出 `NotImplementedError` | 异常 |
| **已授权可写入（authorized）** | Gate 授权 + refresh 完整实现 | Provider fetch → upsert → 返回 `PersistenceResult` | 正常返回 |

**每 capability 约束**：
- `sector.snapshot`/`sector.ranking`（~~offline stub~~ — **out-of-scope（R2，2026-08-04）：name_em 实时板块排行移出 Phase 3 目标，实时 refresh 已禁止、永不 authorized**）：~~refresh 路径仅在 SSL 诊断通过后评估——当前保持在「未授权」或「已注入但未实现」~~ — **R2 语义：任何实时 refresh / SSL 诊断后评估均不构成可执行路径**（见 §R2.1 / §R2.2）。
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
PR-0 (Secret 审计) ──→ PR-1 (MongoDB 预检) ──→ PR-3/4 (Smoke)
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

> **R2（2026-08-04）**：图中 smoke 框原为 `PR-2/3/4 (Smoke)`；PR-2（sector 实时 smoke）已 **superseded / out-of-scope**（预算永久废弃），仅 PR-3/PR-4 为可执行 smoke，PR-2 不构成任何 DDL 前置（见 §R2）。

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
| 前置条件 | (a) ~~PR-2 verdict 为 `pass` 或 `conditional_pass`（Pascal 已审阅偏差）~~ — **R2（2026-08-04）：PR-2 已 superseded / out-of-scope（预算永久废弃），前置改为「仅当未来新 Provider Gate 完成（如 §R2.4 G-R2-1 read-path census 或新授权 smoke）+ Pascal 独立确认」**；(b) Pascal 已确认 SPEC-03-014 §3.1 schema 最终版；(c) §14.6 DDL Gate 授权要求 1-6 全部满足 |
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
3. **PR-3/PR-4 至少通过一个子阶段**（**R2（2026-08-04）：PR-2 已 superseded / out-of-scope，不再作为成功标准；P3-A 收尾判据以 §R2.2 完成矩阵为准**）：对应的 Provider smoke 报告生成，verdict 为 pass 或 conditional_pass
4. **字段映射差异表**：每个 capability 的字段映射对照表已生成，未映射字段已标注
5. **Pascal 审阅完成**：Pascal 审阅所有 smoke 报告并确认是否可进入 DDL Gate
6. **DDL 提案**：针对通过 smoke 的子阶段，DDL Gate 提案已提交（含精确的集合创建脚本和索引定义）
7. **无未解决的阻断**：§14.8 停止条件表中无未关闭的事项

T4 阶段**不要求**所有三个子阶段同时通过 smoke——单子阶段通过的组合是合法的完成状态（如「P3-A 生产就绪 but P3-B/C 待后续」），取决于 Pascal 的判断。

### 14.8 停止条件

| 触发条件 | 对应 Gate | 后续动作 |
|---|---|---|
| Secret source 候选文件不存在 | PR-0 | 标记对应 Provider 为「NOT_AUTHORIZED」，不执行该 Provider 的 smoke |
| MongoDB 连接失败或认证拒绝 | PR-1 | 不执行 PR-3/PR-4（**R2（2026-08-04）：PR-2 已 superseded / out-of-scope，不再列入；其余 smoke 需 MongoDB 连通，见 §R2**） |
| 集合 `03_data_ud_*` 已意外存在 | PR-1 | 停止——记录集合存在情况，需 Pascal 判断是遗留还是意外 |
| AKShare API 返回错误（非 200 / 空 DataFrame / 解析异常） | PR-3/PR-4（**R2：PR-2 已 superseded / out-of-scope，见 §R2**） | 停止对应 Provider 的后续 smoke |
| 字段映射匹配率 <70%（≥70% 才可通过；对齐 `MATCH_RATIO_CONDITIONAL=0.70` 与 §R3.3） | PR-3/PR-4（**R2：PR-2 已 superseded / out-of-scope，见 §R2**） | 停止——需重新调整 domain object schema 后重试 |
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
| `sector.snapshot` | ✅ stub + 测试 PASS | ✅ P3-A stub | **out-of-scope（R2）**——name_em 实时板块排行移出 Phase 3 目标，不实现真实 fetch | ❌ 未执行 | ❌ 未实现（三态 unauthorized；**R2：实时 refresh 永不 authorized**） | **out-of-scope（R2）**——❌ B2 失败（SSLError）为历史事实，不重跑 |
| `sector.ranking` | ✅ stub + 测试 PASS | ✅ P3-A stub | **out-of-scope（R2）**——同 sector.snapshot（name_em 移出 Phase 3 目标） | ❌ 未执行 | ❌ 未实现（**R2：实时 refresh 永不 authorized**） | **out-of-scope（R2）**——❌ B2 失败（同 endpoint）为历史事实，不重跑 |
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

> **R2 注（2026-08-04）**：本节 PA-1~PA-9 保持为**离线契约 / 历史验收项**。name_em 实时板块排行已移出 Phase 3 实现/生产验证目标（PR-2 预算永久废弃），本节**不得**作为实时 Provider 激活或 recovery 的依据；P3-A 生产验证仅限盘后/历史 read-path（§R2.2）。PA-9「不创建真实 endpoint skeleton」约束在 R2 下升级为绝对禁止（实时 fetch 整体 out-of-scope）。

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
| PC-11 | freshness canonical key 已冻结（F6 裁定）：`market_sentiment`（capability `sentiment.market_snapshot`）与 `sentiment_limit_up_pool`（capability `sentiment.limit_up_pool`）为唯一 key；`sentiment` 非 TTL key；禁止双 key/alias/fallback | 断言见 SPEC-03-014-F6 §3.2 C-1~C-6 |

**绝对禁止**：
- ❌ 虚构 `market_temperature` 值。
- ❌ 虚构 `northbound_net_flow` 值。
- ❌ 基于 superseded 10 字段模型定义 fixture/expected 字段集。
- ❌ 在 `FreshnessPolicy.DEFAULT_TTLS` 注册 `sentiment` 或引入双 key/alias/fallback（F6 裁定后，见 SPEC-03-014-F6 §3.2）。

**P3-C 时间语义冻结项（2026-08-03 裁定同步）**：
- `sentiment.market_snapshot` / `sentiment.limit_up_pool` 当前目标 = 已完成交易日 / 收盘后 / 可重放；`snapshot_time` 当前仅可落地 `close`，禁止 intraday snapshot。
- 实时情绪路径（盘中实时）属未来独立 capability——需独立 Provider/字段契约/freshness/时间边界 + 新的用户授权，不得以本卡放行。
- `stock_market_fund_flow()` 无 date 参数（`klt=101` 日线）；使用时必须按其返回日线序列按目标 `trade_date/snapshot_date` 精确筛选；不得写成接受指定日期的实时查询。
- `total_turnover` 无合规来源时保持 `None`/unavailable；资金净流入（主力/超大单等）**不得**映射为 `total_turnover`（SDK 静态：fund_flow 无「成交额」列；2026-08-03 live-read 该 endpoint `ConnectionError`）。
- Provider 证据失败（boundary PASS / provider_evidence FAIL，§14.4.5.3），sentiment 两 capability 未注册，保持 offline stub/defer；局部池子端点（zt_pool 55 行 / dtgc 2 行）非空证据不得夸大为可激活 Provider。

### P0.7 P0 vs P1 vs P2 边界

| 阶段 | 名称 | 包含操作 | 授权模式 | 依赖 |
|---|---|---|---|---|
| **P0** | 离线可实现契约 | 静态代码/fixture/mock、孪生等价性测试、refresh 三态守卫 stub、`_EXPECTED_*_FIELDS` 定义、from_dict 松弛映射、离线端到端 smoke | 当前 Kanban 链 | 无 |
| **P1** | 持久化与刷新 | 真实 Mongo DDL/DML、refresh happy-path、CacheManager.put() 激活 | 逐 sub-phase Pascal Gate（G-A/B/C-*） | P0 通过 |
| **P2** | 真实 Smoke & Canary | PR-0 Secret 审计、PR-1 MongoDB 只读预检、PR-3/4 真实 Provider smoke（**R2（2026-08-04）：PR-2（sector 实时 smoke）已 superseded / out-of-scope，P2 不再包含 P3-A 实时 smoke，见 §R2**）、PR-DDL-* 集合创建、PR-CANARY-* 手动 canary | 逐 Gate Pascal 授权（PR-0、PR-1、PR-3/PR-4、PR-DDL-*、PR-CANARY-*；PR-2 永久废弃） | P1 完成 |

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
| `sector.snapshot` refresh happy-path | ✅ P1 实现 | ✅ mock Provider + mongomock | ❌ 需 G-A-2 Gate（**R2（2026-08-04）：G-A-2 已 superseded / out-of-scope——实时 refresh 永不 authorized，P3-A 生产验证仅限盘后/历史 read-path，见 §R2.2**） |
| `sector.ranking` refresh happy-path | ✅ P1 实现 | ✅ mock Provider + mongomock | ❌ 需 G-A-2 Gate（**R2（2026-08-04）：同 sector.snapshot——G-A-2 已 superseded，实时 refresh 永不 authorized，见 §R2.2**） |
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
| `03_data_ud_market_sentiment_snapshot` — `sentiment.market_snapshot` | `{market, snapshot_date, snapshot_time}` → `update_one(filter, {"$set": doc}, upsert=True)` | 22 字段 canonical `MarketSentimentSnapshot` 为唯一写入 schema；禁止写入旧 10 字段模型 |
| `03_data_ud_market_sentiment_snapshot` — `sentiment.limit_up_pool` | `{market, symbol, trade_date}` → `update_one(filter, {"$set": doc}, upsert=True)` | `LimitUpPoolRecord` 为唯一写入 schema；与 `sentiment.market_snapshot` 共存于同一集合（异构文档，异键），写入不冲突（详见 F1 amendment `SPEC-03-014-F1` 键裁定 + F4 amendment `SPEC-03-014-F4` 读 filter 裁定） |

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
| SentimentService | `sentiment.limit_up_pool` | `"sentiment:limit_up_pool:{trade_date}"` | `"sentiment:limit_up_pool:2026-07-30"` |

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
        filter = self._p3_filter_for(security_id, domain, operation, params, market=market)  # F4: 注入 market 防止跨市场泄漏
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
| 真实 AKShare API | ❌ 不实现 | N/A | PR-3/4（P2）（**R2（2026-08-04）：PR-2 已 superseded / out-of-scope，从生产激活授权中移除，见 §R2**） |
| 真实 MongoDB DML | ❌ 不实现 | N/A | PR-CANARY（P2） |
| cron/systemd/调度 | ❌ 不实现 | N/A | Phase 5 |

### P1.9 授权关口

本表与 RFC §P1.7 一致。

| Gate | 含义 | P1 阶段状态 |
|---|---|---|
| G-A/B/C-1 DDL Gate | `createCollection`/`createIndex` 授权 | ✅ B1-P3A/B/C 已全部冻结 |
| G-A/B/C-2 Refresh Gate | `_is_refresh_authorized()`→True + refresh 生产激活 | ❌ P1 中不激活（**R2（2026-08-04）：G-A-2（sector 实时 refresh 激活）已随 PR-2 废弃——name_em 实时板块排行移出 Phase 3 目标，P3-A 实时 refresh 永不 authorized；G-B-2/G-C-2 不变，见 §R2**） |
| G-A/B/C-3 Canary Gate | 手动 canary 调度授权 | ❌ 不属 P1 范围 |

### P1.10 P1 验收准则（Fake-only Closeout ✅）

- [x] `P3PersistenceWriter.upsert()` 在 mongomock 中使用业务唯一键 upsert 正确集合，写入后 `get()` 可正确读取。
- [x] `refresh_xxx()` 全流程（mock Provider → mongomock upsert → Cache mock）在 authorized 态 PASS；在 unauthorized 态抛出 `NotImplementedError`。
- [x] `northbound_daily` refresh 路径始终返回 skipped（`_is_northbound_refresh_disallowed()=True`）。
- [x] `DataRouter._try_materialized()` 在 P3 capability 上通过 mongomock 返回正确的物化数据，source_trace 格式与 RFC §P1.5.2 一致。
- [x] 全部 P0 验收标准（PA-1~PA-9、PB-1~PB-10、PC-1~PC-11）在 P1 代码变更后继续 PASS。
- [x] 零真实 I/O：pytest 收集的所有测试不产生外部网络调用或真实文件写入（通过 socket/syscall mock 在 CI 中验证）。
- [x] 每个 service 的 refresh happy-path 在 authorized 态时 Step 4 的 `CacheManager.put()` 调用通过 unittest.mock 验证（调用计数 ≥1、参数 cache_key 格式符合 §P1.5.2.bis）。
- [x] `git diff --check` 无冲突标记；`git diff --name-status` 仅显示 RFC 与 SPEC 两份文档的改动。

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
- ❌ `freshness.py`（P1 历史限制：PC-11 命名冲突冻结——该冻结已由 RFC/SPEC-03-014-F6 裁定解除；P1 任务仍不得修改 freshness.py，运行时 freshness 对齐归 F6 Implement 阶段）
- ❌ 任何 `.env`、config、requirements、SKILL.md、README

---

## R2 生产验证完成矩阵与后续生产 Gate 授权骨架（V0.28 引入；V0.29 同步；V0.31 三态统一仲裁）

> **定位**：本节为 **Phase 3 生产验证 re-baseline** 的 SPEC 可执行契约层（Pascal 2026-08-04 R2 范畴裁定，优先级最高），与 RFC-03-014 §R2 **逐项对应**；与 P3-A readonly-gate 三层文档 R2（RFC-03-014-p3a-readonly-gate §2.6 / SPEC-03-014-p3a-readonly-gate §0.2 / DESIGN-03-014-p3a-readonly-gate §2.7）**逐项一致**。本节是后续每个生产 Gate 的权威基线；主文档其余章节的 PR-2/实时 sector 表述均以本节为准。V0.27 changelog 与 §0 术语对 §R2 的引用由本节承接，不再悬空。

### R2.1 范畴裁定（name_em 移出 Phase 3 目标）

**裁定**：`stock_board_industry_name_em()` / 行业板块 `name_em` 属于**实时板块排行**，不在本次 Unified Data Phase 3 的实现/生产验证目标之内。以下为可执行契约：

1. **PR-2 的 name_em 单次预算永久废弃**（不因 scope removal 留作后门）：`t_55d44505` / `t_81432128` 标记为 **superseded / historical evidence**，不得 unblock、retry、创建 replacement probe 或改用其他 AKShare endpoint。
2. **禁止**为 name_em 新建 Provider recovery、替代 endpoint、实时 refresh 或任何 live retry。
3. **禁止**调用 `cons_em`（`stock_board_industry_cons_em`——成分股列表非板块级聚合主数据源，保持既有禁止）。
4. P3-A 仅保留**盘后/历史、按 trade_date 可复现**的 sector read-path 验证（消费既有历史集合/物化数据，**不发起任何实时 Provider 调用**）。
5. PR-2 历史结果（一次尝试 `ProviderUnavailable`、一次越界 netprobe）保留为历史事实，但**不得**作为 P3-A 生产能力失败或后续 recovery 依据。

**可验证项**：
- 静态 grep：SPEC/RFC/P3-A readonly-gate 三层文档中，任何将 PR-2 描述为可执行 Gate 的表述必须带 superseded / out-of-scope（R2）标记；`sector.snapshot`/`sector.ranking` 实时验证不得出现在任何授权/验收路径中。
- 静态 grep：`cons_em` 仅允许出现在历史冻结证据或禁止表述中。

### R2.2 六 capability 生产验证完成矩阵（冻结）

对以下六项分别冻结「允许的最终状态」「证据要求」「禁止表述」。**允许的最终状态**是 Phase 3 生产验证可接受的收尾状态；达到其一即视为该 capability 完成，其余状态一律不构成完成。

| 子域 | Capability | 允许的最终状态 | 证据要求 | 禁止表述 |
|---|---|---|---|---|
| P3-A | `sector.snapshot`（实时） | **out-of-scope（不验证）** | R2 裁定落档（§R2.1 + P3-A readonly-gate RFC §2.6 / SPEC §0.2）；历史 PR-2 结果（ProviderUnavailable + netprobe 越界）保留为历史事实 | 不得声称实时板块排行 production-validated（旧 read-path 专属术语已并入三态，见 §R2.2 状态语义）；不得新建 Provider recovery / 替代 endpoint / 实时 refresh / live retry；不得调用 `cons_em` |
| P3-A | `sector.ranking`（实时） | **out-of-scope（不验证）** | 同 `sector.snapshot`（实时） | 同 `sector.snapshot`（实时） |
| P3-A | sector 盘后/历史 read-path | **production-validated**（仅 read-path scope）或 **provider-unavailable-frozen** | 成功：Pascal 授权 G-R2-1 只读 census 实际执行 + 独立 Verify 静态验收（集合存在且唯一键 canonical、按 trade_date 可复现、行数 ≥ 1、零写入、0 实时 Provider 调用）；不可用：集合不存在 / by-design 无安全消费进程说明（证据冻结 + fail-stop） | 不得以 read-path 验证证明实时 Provider 可用；不得伪装实时激活；不得在 census 中发起 Provider 调用；schema drift / 认证失败 / 越界写入 / Verify 未通过 = 非结论 fail-stop（不落三态，§R2.2 状态语义） |
| P3-B | `flow.capital_flow_daily` | **production-validated** 或 **provider-unavailable-frozen** | 受控 smoke/canary（Pascal 授权）真实 Provider 调用成功 + 字段映射报告 + 零持久化写（smoke 阶段）；或 ProviderUnavailable 冻结证据 + fail-stop | 不得将 mock/offline 表述为生产验证；不得伪装北向字段；不得以局部样本泛化全量标的 |
| P3-B | `flow.northbound_daily` | **intentionally-unavailable（Pascal C）** | Pascal C 裁定引用（§14.4.5.2 / RFC-03-014 §13.4.5.2）；`northbound_net_inflow` 恒 None 静态断言 | 持股历史不得伪装为净流入；不得引入 A/B 选项 endpoint skeleton；不得声称 production-validated |
| P3-C | `sentiment.market_snapshot` | **production-validated** 或 **provider-unavailable-frozen** | 已完成交易日 / close-only / 可重放；受控 smoke（Pascal 授权）或冻结证据；`total_turnover=None`；Provider 未注册保持 offline stub/defer | 不得声称盘中实时；不得虚构 `market_temperature` / `northbound_net_flow`；不得把局部池子端点非空夸大为可激活 Provider；live-read 预算耗尽不重跑 |
| P3-C | `sentiment.limit_up_pool` | **production-validated** 或 **provider-unavailable-frozen** | 同 `sentiment.market_snapshot`（`trade_date` 必填契约 + `CompletedSessionPolicy` 校验） | 同 `sentiment.market_snapshot` |

**状态语义**（仅允许 R2 唯一三态，与 DESIGN-03-014 V0.35 §R2.4 生产结论词汇一致；与 RFC §R2.2 状态语义逐项一致）：
- `production-validated` = 受控真实调用（Pascal 授权 smoke/canary）成功且证据冻结；
- `provider-unavailable-frozen` = 真实调用失败/不可用，ProviderUnavailable 证据冻结 + fail-stop；
- `intentionally-unavailable` = Pascal 决策（C）明确不提供。

**P3-A read-path census 结果 → 三态唯一映射（V0.31 仲裁）**：
- **成功**（仅 read-path scope）→ **`production-validated`**：仅当满足全部证据——Pascal 授权 G-R2-1 实际执行 bounded read（ping/list/find/count）、designated baseline 集合存在且唯一键 canonical、按 trade_date 可复现（日期窗口 ≤ 5 交易日、行数 ≥ 1、计数一致）、零写入证明、无 schema drift、独立 Verify 静态验收通过。**≠ 实时 Provider 验证**：不得以 census 成功证明 `sector.snapshot` / `sector.ranking` 实时可用；该态仅能由未来获授权且实际执行、独立验证的 Gate 产生——**本文档裁定不产生任何生产结论**。
- **不可用** → **`provider-unavailable-frozen`**：集合不存在（designated baseline 缺失）或 by-design 无安全消费进程说明（延续 OQ-11 T6 fail-stop 语义）；不可用证据冻结 + fail-stop，不自动重试。
- **非结论 fail-stop（不落任何三态；禁止杜撰第四/第五状态）**：schema drift → 先修设计（Full Flow），不得就地改库；认证失败 → 无法区分「不可用」与「未授权」，不落态、不自动重试（凭据/授权修复后需重新获权执行）；空集合（0 行且无 by-design 解释）→ 无数据可验证，不落态；任何写入尝试 → 越界 fail-stop（G-R2-1 无 write/DDL）；独立 Verify 未通过 → Gate 不关闭。
- **`intentionally-unavailable` 对 P3-A read-path 不适用**：无 Pascal C 决策拒绝提供 read-path 验证；该态仅保留给 P3-B `flow.northbound_daily`（Pascal C）。

### R2.3 关键冻结语义

- **三张 `03_data_ud_*` 集合为 designated historical baseline**（R1 裁定延续）：`03_data_ud_market_sector_snapshot` / `03_data_ud_stock_capital_flow` / `03_data_ud_market_sentiment_snapshot` presence 本身不是 FAIL，而是 PR-1 PASS 基线；**只读 census 可用，禁止重复 DDL**；若发现 schema drift → **先修设计（Full Flow）**，不得就地改库。
- **`P3PersistenceWriter` 当前拒绝真实 pymongo**（`_assert_fake_db`）：任何生产写入前需要**新的生产 writer / 身份 / DDL / rollback 设计**（Full Flow：RFC/SPEC/Design → Implement → Verify → Review），**不得绕过**。
- **P3-B northbound**：持股历史不得伪装为净流入；正确验证是 `None`/unavailable fail-stop（Pascal C）。
- **P3-C**：close-only / completed-session / `total_turnover=None` / Provider 未注册（既有 live-read 预算耗尽不重跑）。
- **OQ-11**：本地策略注入（`AShareCompletedSessionPolicy` + date_utils strict seam）已验证，但**无可安全消费进程**；T6 保持 fail-stop，**不得臆造 systemd/cron**。

### R2.4 后续生产 Gate 授权骨架

每个后续生产 Gate 按下表六维定义；**任何不在 allowlist 内的命令/动作 = 越界 fail-stop**。独立 Verify 身份：Verify worker 只做静态/报告验收，**不重复执行任何真实调用**。

| Gate | 目标 namespace / 数据源 | read / write / DDL 命令 allowlist | 最大调用数 / 写入数 / 输出限制 | 停止条件（fail-stop） | 回滚 / 禁用语义 | 输出脱敏规则 | 独立 Verify 身份边界 |
|---|---|---|---|---|---|---|---|
| **G-R2-1：P3-A read-path census** | MongoDB `tradingagents.03_data_ud_market_sector_snapshot`（designated historical baseline）；数据源 = 既有历史集合/物化数据 | read：`ping` + `list_collection_names` + `find`（唯一键/日期窗口 filter）+ `count_documents`；write：无；DDL：无（禁止重复 DDL） | find ≤ 10 次；返回行数 ≤ 1000；日期窗口 ≤ 5 个交易日 | 认证失败 / 集合不存在（或 by-design 说明）/ schema drift（先修设计）/ 任何写入尝试 → 立即停止 | 无写入无需回滚；census 报告仅本地 redacted 文件（`docs/rfc/03_data/smoke_reports/` 或 /tmp，不提交） | 不输出 secret/URI；仅集合名、唯一键样例、行数、日期窗口、schema 字段名（不含值） | Verify 仅核对 census 报告静态字段与零写入证明，不得连接 Mongo/Provider |
| **G-R2-2：P3-B capital-flow chain** | MongoDB `tradingagents.03_data_ud_stock_capital_flow`（baseline）；数据源 = `flow.capital_flow_daily` 受控 smoke/canary | read：`ping` + `list_collection_names` + `find`（`{market, symbol, trade_date}` filter）+ `count_documents`；write：仅 Pascal 授权 smoke（零持久化）或 canary（单次显式 refresh → upsert）；DDL：禁止 | smoke ≤ 3 次调用 / 标的 ≤ 2；canary 单次 refresh；输出 ≤ 报告体积 | API 失败 / 空返回 / 字段映射 <70% / 写权限失败 / northbound 伪装 → fail-stop，不自动重试 | smoke 零写入无需回滚；canary 写入用 `delete_by_filter` 清理（提供脚本）；禁 DB 回滚/删除自动执行 | 不输出 secret；仅映射摘要字段名/类型；样本行脱敏（无全量 payload） | Verify 对照 smoke/canary 报告 + 冻结契约逐项验收，不重复真实调用 |
| **G-R2-3：P3-C route decision** | MongoDB `tradingagents.03_data_ud_market_sentiment_snapshot`（baseline）；数据源 = 已完成交易日 close-only 可重放 | read：`ping` + `list_collection_names` + `find`（`{market, snapshot_date}` filter）+ `count_documents`；write：仅 Pascal 授权 smoke（单日期、零持久化）或 canary（单次 `refresh_limit_up_pool(trade_date)` 等显式 refresh → upsert）；DDL：禁止 | smoke ≤ 2 次调用 / 单日期；canary 单次；输出 ≤ 报告体积 | API 失败 / 空返回 / close-only 校验失败（非 close、未完成 session）/ `total_turnover` 非 None → fail-stop | smoke 零写入；canary 用 `delete_by_filter` 清理；禁自动回滚 | 不输出 secret；仅映射摘要字段名/类型；样本行脱敏 | Verify 只做静态验收（报告 + 契约），不触发真实调用 |
| **G-R2-4：consumer / restart** | 既有服务进程入口（OQ-11，T2 以仓库事实裁定）；数据源 = 本地策略注入（`AShareCompletedSessionPolicy` + date_utils strict seam） | read：仅既有运维入口；write：仅撤销注入（恢复 `completed_session_policy=None`）；DDL：无 | 重启 ≤ 1 次；健康/行为 check ≤ 3 条命令（如对已知 completed day 判定路径结果一致） | 无可安全重启目标 → fail-stop（禁臆造/增设 unit）；健康 check FAIL → 回滚撤销注入 | 仅撤销 production composition injection 恢复 `completed_session_policy=None`；禁 DB 回滚/删除、禁自动回滚 | 不输出 secret；仅记录 service 名 / 时间 / 健康布尔 | Verify 独立复核前后行为一致性与授权边界（不执行重启） |

**执行约束**：
- 每个 Gate 均为独立 Pascal 授权；授权边界以本节六维为准，不得扩大到禁止对象（Provider/Mongo/DDL/DML/cache/refresh/canary/cron-systemd/网关/webhook/Git/秘密）。
- P3-A 实时（name_em）与 `cons_em` 在全部四个 Gate 中均为 0 调用。
- Gate 成功 ≠ 生产激活或可交易信号；完成矩阵最终状态（§R2.2）是唯一收尾判据。

### R2.5 一致性声明

- 本 §R2 与 RFC-03-014 §R2、P3-A readonly-gate R2（RFC-03-014-p3a-readonly-gate §2.6 / SPEC-03-014-p3a-readonly-gate §0.2 / DESIGN-03-014-p3a-readonly-gate §2.7）逐项一致；如有差异，以本节 + P3-A readonly-gate R2 为准。
- 主文档历史章节（§2.1 / §7 / §10 / §10.bis / §14 / §P0 / §P1）中所有 PR-2/实时 sector 表述保留为历史事实，统一以「superseded / out-of-scope（R2）」标记，不删除、不重写冻结事实。**V0.28（2026-08-04）已按独立 Verify（t_876a30bd）FAIL 证据补全正文残留行标记并新增本节，消除 §0 术语与 changelog 的悬空引用。**
- 本卡未修改 DESIGN-03-014 master；其 R2 同步由后续 Design 卡处理。
- **V0.31：P3-A read-path 结果词汇已并入 R2 唯一三态（§R2.2 状态语义），与 DESIGN-03-014 V0.35 §R2.4 生产结论词汇逐项一致，不再存在 read-path 专属双态；DESIGN-03-014 master 已同步（V0.34 R2 Design Sync + V0.35 三态统一仲裁，见 DESIGN-03-014 §R2）。**

---

## R3 P3-B 真实资金流生产验证与受控物化契约（V0.32 引入；独立重建；V0.33 P0 阈值纠正；V0.34 G-CF-LIVE-R3 直连诊断）

> **定位**：本节为 **P3-B S1 `flow.capital_flow_daily` 真实资金流生产验证与受控物化链**（capital-flow chain）的 SPEC 可执行契约层（Pascal / Orchestrator 2026-08-05 恢复裁定，优先级最高），与 RFC-03-014 V0.34 §R3 **逐项对应**（V0.32 独立重建 + V0.33 P0 阈值纠正 + V0.34 G-CF-LIVE-R3 直连诊断）。触发事实：此前未提交的 SPEC V0.32 / Design V0.36 已被工作树 `git restore`/checkout 类动作整体回退，恢复核验卡 `t_eb2ed46e` 记录的 R3 文件内容已不在磁盘，**不能继续以其结论作为当前代码的活跃契约**；本卡从当前 V0.31 SPEC 基线**重新、独立**产出 §R3，使其成为新的可验证文件事实。本节是后续每个 P3-B S1 生产 Gate 的权威可执行基线；主文档其余章节的 PR-3/PR-DDL-P3B/PR-CANARY 表述均以本节为准。**本卡零真实动作**：离线/mock 不构成生产验证，任何生产结论只能由本节四 Gate 全部实际执行及独立 Verify 产生（§R3.8）。
>
> **与 §R2.4 G-R2-2 的关系**：§R2.4 G-R2-2 定义了「P3-B capital-flow chain」六维授权骨架；本节在其基础上将 P3-B S1 `flow.capital_flow_daily` 的**四 Gate 精确化为可执行契约**（G-CF-LIVE → G-CF-DDL → G-CF-CANARY → G-CF-POST），逐一冻结参数、命令 allowlist、停止条件、回滚/清理语义、输出脱敏与 Verify 身份边界。G-R2-2 骨架中与本节的差异以本节为准。

### R3.1 唯一真实目标与 northbound 永久排除

1. **唯一真实 Provider 目标**：`flow.capital_flow_daily` → AKShare `stock_individual_fund_flow`（B2 冻结证据 real-mappable，见 §14.4.5.2 / RFC-03-014 §13.4.5.2）。本节四 Gate 的调用、DDL、canary、验收对象**仅限**该 capability 与其目标集合 `03_data_ud_stock_capital_flow`。
2. **`flow.northbound_daily` 恒 `intentionally-unavailable` / None fail-stop**（Pascal C 裁定，§14.4.5.2 / §R2.2 完成矩阵行）：`northbound_net_inflow` / `northbound_hold_shares` / `northbound_hold_ratio` 恒 None；**禁止** `stock_hsgt_individual_em`、**禁止** northbound endpoint skeleton、**禁止** northbound 的 DDL/canary/验收路径。本节的任何 Gate 不得将 northbound 作为调用对象、写入对象或验收对象。
3. **保留既有禁令**：`name_em` / `cons_em` 禁令与 §R2.1 范畴裁定原样保留（0 调用）；P3-A 实时板块排行与本链无关。

### R3.2 四 Gate 严格串行链总览

**严格串行且逐个明确 Pascal 授权**，顺序不可调换、不可并行、不可跳过：

```
G-CF-LIVE（零 Mongo live-read） → G-CF-DDL（唯一集合 + 两索引） → G-CF-CANARY（600519 × 一个 completed date × ≤1 doc） → G-CF-POST（独立只读验收）
```

- 每个 Gate 均为**独立 Pascal 授权**；前一个 Gate 的 pass + 独立 Verify 通过是后一个 Gate 的触发前置；**禁止自动推进**（任何 Gate 不得自动触发下一个 Gate）。
- **禁止第四路径**（任何不在四 Gate allowlist 内的命令/动作 = 越界 fail-stop）、**禁止 fallback**（不得以替代 endpoint / 替代标的 / 替代日期 / 替代集合完成目标）、**禁止隐式重试**（失败即冻结，不自动重试，不换标的/日期/endpoint）。
- 每个 Gate 的授权边界以本节六维为准，不得扩大到禁止对象（Provider 非授权 endpoint / Mongo 非授权命令 / DDL 非授权集合 / cache / refresh / canary 越界 / cron-systemd / 网关 / webhook / Git / 秘密）。

### R3.3 G-CF-LIVE：零 Mongo live-read（真实 Provider 只读 Smoke）

| 维度 | 冻结值 |
|---|---|
| 目标 capability | `flow.capital_flow_daily` → AKShare `stock_individual_fund_flow` |
| 标的 | 唯一 `600519`（CN） |
| 日期 | 最多 **3 个 completed trading dates**（completed-date 判定契约见 §R3.7） |
| 调用预算 | **≤ 3 calls**（AKShare 匿名只读调用）；**≥ 1 秒间隔**；**3 秒超时** |
| 写入 | **零 Mongo / 零 cache / 零 refresh / 零 upsert / 零 DDL / 零 DML / 零 Git 写**（含 Mongo 连接、ping、list、find、count 一律禁止——本节 G-CF-LIVE 是**零 Mongo live-read**） |
| 输出 | 映射摘要（字段名/类型）、行数、前 N 行脱敏样例、source_trace 摘要；不输出 secret/URI/全量 payload |
| 停止条件（fail-stop） | API 失败 / 空返回 / 字段映射匹配率 <70%（≥70% 才可通过；对齐 `MATCH_RATIO_CONDITIONAL=0.70` 与 DESIGN §15.6.2 / §R2.4 G-R2-2） / 任何写入尝试 / 超时 / Verify 未通过 → **立即停止并冻结**；**不换标的、不换日期、不换 endpoint、不自动重试** |
| 触发前置 | Pascal 明确授权（本卡未授权、未执行；历史 PR-3 预算已耗尽，B2 证据不重跑，见 §14.4.5.5） |
| Verify 身份边界 | Verify worker 仅对照 live 报告 + 冻结契约静态验收，**不重复任何真实调用** |

### R3.3.bis G-CF-LIVE-R3：AKShare 直连与真实 HTTP timeout 受控诊断（V0.34 新增；Pascal 明确授权最终单次 live-read）

> **定位**：`G-CF-LIVE-R3` 是 **Pascal 明确授权的最终单次 live-read** 可执行契约（本卡仅写入契约，不执行）。**R3 是「新一次独立授权 Gate」，不是 R1/R2 的自动重试、不是对既有 G-CF-LIVE（§R3.3）的替换、不是四 Gate 链的一部分**；R1/R2 历史事实（均 `ConnectionError`、经继承代理环境；`DEFAULT_TIMEOUT_SECONDS=3` 未传至 AKShare 1.17.54 内部 `requests.get`）**保持准确、不改写**。本 Gate 的唯一目的：在 **direct transport（临时清空代理环境变量）** 与 **真实 HTTP timeout=10s** 条件下，对唯一 endpoint 执行**至多 1 次**真实只读 Provider 调用，产出受控诊断报告；**不产生任何生产结论**（三态词汇不因本 Gate 落盘，见 §R3.8）、**不替代/不跳过四 Gate 链**（G-CF-LIVE → G-CF-DDL → G-CF-CANARY → G-CF-POST 仍各自需要独立 Pascal 授权与实际执行）。

| 维度 | 冻结值 |
|---|---|
| 目标 capability | `flow.capital_flow_daily` → AKShare `stock_individual_fund_flow` |
| 唯一 endpoint/API | `stock_individual_fund_flow(stock='600519', market='sh')`；**严禁换 endpoint/标的/日期** |
| report target | `600519/CN` |
| candidate date | `2026-08-04`（**仅报告元数据**，非调用参数） |
| direct transport | 仅本次子进程临时清空 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`；`NO_PROXY` 仅保留本机最小默认值；**不改 shell profile、`.env`、系统/服务/网关配置** |
| 调用预算 | **至多 1 次逻辑 Provider 调用**；真实 HTTP request **timeout=10s**；≥1s 间隔（若仅一次则不触发）；**零 retry / 零 fallback** |
| 写入 | **零 Mongo**（含连接/ping/list/find/count）、**零 cache**、**零 refresh/upsert**、**零 DDL/DML**、**零 Git 写/commit**、**零服务/cron/gateway 变更** |
| 失败（fail-stop） | 任何 DNS/TCP/TLS/HTTP/timeout/schema 异常**立即 fail-stop**；保留**脱敏异常层级**（异常类、message 摘要、cause/urllib3 子类）；**不得重放本 Gate**（不换标的/日期/endpoint、不自动重试） |
| 输出 | 映射摘要（字段名/类型）、行数、前 N 行脱敏样例、source_trace 摘要；不输出 secret/URI/全量 payload |
| 临时报告 | 批准路径 `/tmp/yquant-g-cf-live-r3-20260804-<run-id>/`；目录 0700、YAML 0600；账本字段：`provider_attempts`、`actual_calls`、`retry`、`fallback`、`mongo`、`write`（=0）、`direct_transport`、`effective_http_timeout_seconds` |
| 回滚（rollback） | **仅撤销未来 R3 代码路径**（若后续实现 live-read 工具链，撤销其可执行路径/脚本）；**不回滚历史报告/数据**（R1/R2 历史报告、既有冻结契约、任何 Mongo 数据均不动） |
| 触发前置 | **Pascal 明确授权（本次已授权，仅契约，本卡未执行）** |
| Verify 身份边界 | Verify worker 仅对照 live 报告 + 冻结契约静态验收，**不重复任何真实调用** |
| 当前事实陈述 | R1/R2 均为 `ConnectionError`（经继承代理环境）；`DEFAULT_TIMEOUT_SECONDS=3` 未传至 AKShare 1.17.54 内部 `requests.get`；本轮基线 = **RFC V0.34 / SPEC V0.34 / Design V0.37**（基线时为 RFC/SPEC V0.33 → Design V0.37；本卡同步 SPEC 至 V0.34）；R1/R2 历史事实不改写 |

**与 §R3.3 G-CF-LIVE 的关系**：§R3.3 是四 Gate 链第一环（≤3 completed dates / ≤3 calls / 3s 超时 / 不设代理变量要求），本 §R3.3.bis 是 Pascal 单独授权的**单次直连诊断异常 Gate**（1 call / 10s / direct transport），两者授权独立、互不替代；本 bis 的失败或成功均**不改变** §R3.3 G-CF-LIVE 的冻结值。

### §R3.3.bis.1 2026-08-07 受控直连诊断 fail-stop（事实归档；不改本 §R3.3.bis 冻结契约）

> **本节为"已发生事实"事实归档**，**不修改 §R3.3.bis 任何冻结契约条款**；不重新打开 R3 完整 Design→Implement→Verify→Review 链路；不构成任何"G-CF-LIVE-R3 通过"或"四 Gate 全过"或"R1/R2 fail-stop 被翻案"的依据。本子节为 RFC-03-014 V0.35 §R3.3.bis.1 镜像。

**触发**：Pascal 2026-08-05 21:16 收窄目标为"一次性 AKShare 可达性与返回格式诊断"，明令禁止 Design/代码变更。

**执行**（不修代码、不动 Design、不动 .env/服务/网关；进程级只读 + 子进程 snapshot/restore）：

| 维度 | 结果 |
|---|---|
| endpoint / 标的 / 日期 | `akshare.stock_individual_fund_flow(stock='600519', market='sh')` / 600519/CN / candidate date `2026-08-04`（仅报告元数据；未换、未改） |
| direct transport | 子进程临时清空 `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`（含小写形），`NO_PROXY`/`no_proxy` 仅保留本机最小默认值；进程结束已恢复；**未**触 shell profile/.env/服务/网关 |
| 调用预算 | 实际 1 次逻辑 Provider 调用（未触发 `≥1s` 间隔规则） |
| HTTP timeout=10s | **未注入**；`requests.get` 默认 timeout 探测结果 = `None`（证实 `DEFAULT_TIMEOUT_SECONDS=3` 未传至 AKShare 1.17.54 内部 `requests.get` 的既有假设） |
| `effective_http_timeout_seconds` 报告字段 | `null`（诚实标注本次未注入 timeout=10s） |
| TCP 443 握手 | `hq.sinajs.cn` / `push2.eastmoney.com` / `datacenter-web.eastmoney.com` / `datacenter.eastmoney.com` 全部成功（28–55ms） |
| DNS/TCP/TLS | 端口可达 |
| **connectivity** | `error` |
| **error_class** | `requests.exceptions.ConnectionError` |
| **exception_chain** | ① `requests.ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))` ② `urllib3.exceptions.ProtocolError: ('Connection aborted.', RemoteDisconnected(...))` ③ `http.client.RemoteDisconnected: Remote end closed connection without response` |
| 副作用清单 | `provider_attempts=1`, `actual_calls=1`, `retry=False`, `fallback=False`, `mongo=False`, `write=False`, `git=False`（全部为 False / 0） |

**R1/R2 历史事实保持不改写**（V0.34 §R3.3.bis 锚定值）：均 `ConnectionError`（经继承代理环境）；`DEFAULT_TIMEOUT_SECONDS=3` 未传至 AKShare 1.17.54 内部 `requests.get`。

**不产生的结论**（与 §R3.8 / §R3.10 / §R3.11 一致性声明一致）：

- 本次 fail-stop **不**作为"G-CF-LIVE-R3 通过"的依据；
- 本次 fail-stop **不**声称"四 Gate 全过"；
- 本次 fail-stop **不**声称"R1/R2 fail-stop 被翻案"；
- 本次 fail-stop **不**扩展 P3-A / `name_em` / `cons_em` / OQ-11 / OQ-11B 既有语义；
- 本次 fail-stop **不**导致任何 DDL / DML / Provider / Mongo / Git 写入；
- 本次 fail-stop **不**触发 northbound / canary / freshness / DDL / PR-DDL 等其他 Gate 链。

**产物路径**（0700 dir / 0600 yaml）：

- `/tmp/yquant-g-cf-live-r3-diag-<run-id>/diagnostic.yaml`（sha256=`d087fadcf25a8e7ba9ecc8b9c46133be3da2ee4580db98f18de1a169d633f862`，2417B）
- `/tmp/yquant-g-cf-live-r3-diag-<run-id>/diagnostic.json`（sha256=`6d5732094bb621ae951779af13c596c1efe798e39e396883022945dee0e05819`，2764B）
- 诊断脚本：`/tmp/r3_diag_minimal.py`（只读、无项目副作用、可复用）

**关联 Kanban 卡**：

- `t_73e26ca7`（replacement R3 Design）— 已在 blocked 终态冻结；evidence-only comment id=1244 已挂账本；reason=`frozen-per-Pascal-2026-08-05-scope-narrowing`。
- `t_55ebd64b`（旧 R3 Design，父链污染冻结）— 已在 blocked 终态；comment id=1245 镜像 evidence；**不**作为 parent 复用。

**重启条件**（Pascal 后续显式授权时）：若 Pascal 重启 R3 完整 Design→Implement→Verify→Review 链，需新建 replacement T2 / T3 / T4 / T5 / T6 卡（含可恢复 timeout=10s 注入机制 + 子进程代理环境 snapshot/restore 实现 + 脱敏异常层级记录）；本 §R3.3.bis.1 evidence **不构成放行依据**，仅作为 2026-08-07 受控直连诊断 fail-stop 的不可篡改审计痕迹。

### R3.4 G-CF-DDL：唯一集合 + 两索引

| 维度 | 冻结值 |
|---|---|
| 目标 | **唯一** MongoDB 集合 `tradingagents.03_data_ud_stock_capital_flow`（库 `tradingagents`） |
| 唯一键 | `{market, symbol, trade_date}`（§4.bis.1 集合表） |
| 索引 | 恰好两索引——`symbol_trade_date`（`{symbol:1, trade_date:-1}`）与 `trade_date`（`{trade_date:-1}`），全部 `background: true`（定义见 DESIGN §6.2 / §6.4.bis，本节引用不重述） |
| 权威契约 | **§14.6.bis PR-DDL-P3B（B1-P3B 冻结）** + **DESIGN-03-014 §6.4.bis**（V0.14）；如本节与权威契约出现差异，以权威契约为准 |
| 命令 allowlist | read-only preflight probe（`list_collections` / `list_indexes`）→ `createCollection` → `createIndexes`（两索引） |
| 写入原子性 | **失败即停，不自动回滚**；preflight probe 命中目标集合 fail-stop（exit 2）；`createCollection`/`createIndex` 目标已存在 fail-stop（exit 4），由操作员手动评估 |
| 退出码 | `0`=PASS；`2`=preflight target already exists；`3`=collection create fail；`4`=index create fail（退出码 1 不使用） |
| rollback 脚本 | `/tmp/yquant-p3-ddl-p3b-20260725/rollback-p3b.js`（dropIndex 反向顺序 + dropCollection；不提交仓库；`node --check` 必过） |
| audit 工件 | stdout + `/tmp/yquant-p3-ddl-p3b-20260725/audit-p3b.json`；字段 `{operation, collection, index, ts, exit_code, error, rollback_script_path}`；**不引入**新 audit 集合 |
| DDL 执行人 | **Pascal 手动执行**（或 Pascal 授权的 DevOps）；Agent 不直接执行 DDL |
| 不授权范围 | 不 refresh、不 upsert 业务数据、不写 Cache、不写 AuditLogger（`03_data_ud_query_audit`）、不写 QualitySummary、不动 cron/systemd、不动 `.env`、不建新角色、不动生产代码树；P3-A / P3-C 集合不在本 Gate 范围 |
| 触发前置 | G-CF-LIVE pass + Pascal 独立确认 schema（§3.2 最终版） |
| 停止条件（fail-stop） | 任一非 0 退出码即 fail-stop；**不自动回滚**、**不自动重试**；是否运行 rollback-p3b.js 由操作员按 DESIGN §6.4.bis.3 失败矩阵的「operator action」列判断 |
| Verify 身份边界 | Verify 仅核对 audit 工件、退出码、rollback 脚本语法与零越界声明，不执行 DDL |

### R3.5 G-CF-CANARY：600519 × 一个 completed date × ≤1 doc

| 维度 | 冻结值 |
|---|---|
| 标的 | 唯一 `600519`（CN） |
| 日期 | **一个 completed trading date**（completed-date 判定契约见 §R3.7；不得 latest/None 语义） |
| 写入上限 | **≤ 1 doc**（幂等键 `{market: "CN", symbol: "600519", trade_date}` 唯一） |
| 执行方式 | **单次显式 refresh**（手动触发，非 cron）→ `flow.capital_flow_daily` provider fetch → canonical mapping → upsert 至 `03_data_ud_stock_capital_flow`（写入身份/路径须满足 §R2.3「P3PersistenceWriter 拒绝真实 pymongo」约束下的授权设计，由后续 Design 精确规定，本卡不臆造） |
| 清理 | 提供 `delete_by_filter` 清理脚本；canary 后按 Pascal 决定清理或保留 ≤1 doc 证据 |
| 停止条件（fail-stop） | 写入失败 / 数据质量异常（字段缺失、类型错误、唯一键冲突） / 写入 > 1 doc / Verify 未通过 → 停止，不升级到定时采集，不自动重试 |
| 触发前置 | G-CF-DDL pass（集合 + 两索引在位）+ Pascal 明确授权 |
| 不授权范围 | 不自动重复、不 cron/systemd 长期调度、不扩大标的集、不扩大日期窗口、不触发 northbound、不写 cache |
| Verify 身份边界 | Verify 对照 canary 报告 + 冻结契约逐项静态验收（含 ≤1 doc、唯一键、字段映射、清理脚本），不重复真实调用 |

### R3.6 G-CF-POST：独立只读验收

| 维度 | 冻结值 |
|---|---|
| 目的 | 对 G-CF-CANARY 的写入做**独立只读验收**，形成 P3-B S1 `flow.capital_flow_daily` 的生产结论（§R3.8） |
| 命令 allowlist | read 仅限：`ping` + `list_collection_names` + `find`（`{market, symbol, trade_date}` filter）+ `count_documents`；write：无；DDL：无 |
| 输出 | 集合存在性、唯一键 canonical、行数（≤1）、日期窗口、字段名清单（不含值）、零写入证明 |
| 停止条件（fail-stop） | 认证失败 / 集合不存在 / schema drift（先修设计 Full Flow，不就地改库）/ 任何写入尝试 / 计数 ≠ 预期 / Verify 未通过 → fail-stop，不落生产结论 |
| Verify 身份边界 | Verify worker 只做静态/报告验收，**不连接 Mongo、不重复任何真实调用**；G-CF-POST 本身可由独立执行人完成，最终结论需独立 Verify 复核 |

### R3.7 completed-date 契约与 OQ-11 边界

1. **completed-date 必复用 `skills.infra.date_utils` / `CompletedSessionPolicy` 契约**（V0.25 EOD-7 / V0.26 EOD-8 冻结语义）：本链 G-CF-LIVE 与 G-CF-CANARY 选择的「completed trading dates」必须经 canonical `YYYY-MM-DD` → XSHG 交易日 → 已到达 session close 的判定链（`calendar.session_close(date)`，禁止硬编码裸 `15:00` 为唯一真相）；**禁止** `TRADING_DAYS_2026`、周末规则或 latest fallback 作为生产真相；fail-closed（calendar 不可用 / 越界 / clock 无时区 → 明确不可判定，不悄悄降级）。
2. **OQ-11 保持独立子链**：production composition root（`AShareCompletedSessionPolicy(clock=SystemClock)` 注入等，V0.26 EOD-8）属 OQ-11/OQ-11B 子链，**不在 P3-B 实现 composition**；本链只消费 completed-date 判定契约，不新增/不扩展 OQ-11 的授权对象。
3. 本卡（SPEC 重建）**不执行**任何 completed-date 判定真实调用；相关判定仅作为后续 Gate 的执行前置契约。

### R3.8 生产结论产生条件

- **生产结论（`production-validated` / `provider-unavailable-frozen`）只能由四 Gate 全部实际执行及独立 Verify 通过产生**（§R2.2 状态语义；P3-B `flow.capital_flow_daily` 行允许的最终状态 = `production-validated` 或 `provider-unavailable-frozen`）；`flow.northbound_daily` 恒 `intentionally-unavailable`（Pascal C）。
- **本卡零真实动作**：离线/mock/文档表述**不构成**生产验证；本文档不产生任何生产结论。
- 非结论 fail-stop（不落三态，沿用 §R2.2）：schema drift → 先修设计；认证失败 → 不自动重试；空返回/空集合 → 无数据可验证；任何越界写入 → fail-stop；独立 Verify 未通过 → Gate 不关闭。

### R3.9 RFC → SPEC 逐项镜像（9 项可执行契约，不得扩展语义）

RFC-03-014 V0.34 §R3.9 指定后续 SPEC 必须**逐项镜像**以下可执行契约（V0.32 重建 + V0.33 P0 阈值纠正 + V0.34 G-CF-LIVE-R3）；本 SPEC 逐项承接如下（与 RFC 逐字一致，仅调整自引用编号）：

1. **G-CF-LIVE 可执行契约**（§R3.3）：`stock_individual_fund_flow` + 600519 + ≤3 completed dates + ≤3 calls + ≥1s 间隔 + 3s 超时 + 零 Mongo/cache/refresh/upsert/DDL/DML/Git 写 + **字段映射匹配率 <70% fail-stop（≥70% 才可通过；对齐 `MATCH_RATIO_CONDITIONAL=0.70`）** + 失败冻结（不换标的/日期/endpoint）+ 输出脱敏规则。
2. **G-CF-DDL 可执行契约**（§R3.4）：唯一 `tradingagents.03_data_ud_stock_capital_flow` + 两索引（`symbol_trade_date` / `trade_date`，`background: true`）+ preflight probe + 退出码 0/2/3/4 + rollback 脚本路径 + audit 字段 + DDL 执行人 = Pascal + 不授权范围。
3. **G-CF-CANARY 可执行契约**（§R3.5）：600519 × 一个 completed date × ≤1 doc + 单次显式 refresh → upsert + 幂等键 `{market, symbol, trade_date}` + delete_by_filter 清理 + 不自动重复。
4. **G-CF-POST 可执行契约**（§R3.6）：read 仅 `ping` / `list_collection_names` / `find` / `count_documents`，write/DDL 无，独立只读验收边界。
5. **completed-date 判定契约**（§R3.7）：复用 `skills.infra.date_utils` / `CompletedSessionPolicy`，fail-closed，禁硬编码日历/fallback。
6. **禁止事项**（§R3.1 / §R3.2）：第四路径、自动推进、fallback、隐式重试、`stock_hsgt_individual_em`、northbound skeleton/DDL/canary/验收、`name_em`/`cons_em`、OQ-11 composition。
7. **三态词汇与不落态语义**（§R3.8 / §R2.2）：`production-validated` / `provider-unavailable-frozen` / `intentionally-unavailable`（northbound 唯一）；schema drift / 认证失败 / 空返回 / 越界写入 / Verify 未通过 = 非结论 fail-stop。
8. **Verify 身份边界**（§R3.3–§R3.6）：Verify worker 仅静态/报告验收，不重复任何真实调用。
9. **G-CF-LIVE-R3 可执行契约**（§R3.3.bis，V0.34 新增）：唯一 endpoint `stock_individual_fund_flow(stock='600519', market='sh')` + report target `600519/CN` + candidate date `2026-08-04`（仅报告元数据）+ direct transport（仅本次子进程临时清空 `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`，`NO_PROXY` 仅本机最小默认值，不改 shell profile/.env/系统/服务/网关）+ 至多 1 次逻辑 Provider 调用 + 真实 HTTP request timeout=10s + ≥1s 间隔（仅一次则不触发）+ 零 retry/零 fallback + 零 Mongo（含连接/ping）/cache/refresh/upsert/DDL/DML/Git 写/服务变更 + 失败保留脱敏异常层级（异常类、message 摘要、cause/urllib3 子类）且不得重放本 Gate + 临时报告 `/tmp/yquant-g-cf-live-r3-20260804-<run-id>/`（目录 0700、YAML 0600，账本字段 provider_attempts/actual_calls/retry/fallback/mongo/write=0/direct_transport/effective_http_timeout_seconds）+ 不产生生产结论 + rollback 仅撤销未来 R3 代码路径不回滚历史报告/数据 + R3 是独立授权 Gate（非 R1/R2 自动重试，R1/R2 历史事实不改写）。

### R3.10 下游 Design 仅文档层精确需求（本卡不授权任何真实动作）

下游 Design（DESIGN-03-014 §R3 重建）必须在本节范围内给出**仅文档层**的精确设计；本卡不提前引用、不认可、不采纳当前工作树两份 dirty Python（`scripts/t4_preflight/config.py` / `scripts/t4_preflight/provider_client.py`）作为契约证据，Design 亦不得以其为事实来源：

1. **G-CF-LIVE 工具链**：定义 live-read 调用封装与报告模板（映射摘要、行数、脱敏样例、source_trace 摘要、boundary/provider 双结论、单次失败冻结）；执行身份/路径须满足零 Mongo/cache/refresh/upsert/DDL/DML/Git 写约束。
2. **G-CF-DDL 工具链**：以 §14.6.bis / DESIGN §6.4.bis 为权威契约，定义 preflight probe、createCollection/createIndexes、rollback-p3b.js、audit-p3b.json 的执行细节与失败矩阵；DDL 执行人 = Pascal，Agent 不直接执行。
3. **G-CF-CANARY 写入路径**：满足 §R2.3「P3PersistenceWriter 拒绝真实 pymongo」约束下的**新生产 writer / 身份 / DDL / rollback 设计**（Full Flow：RFC/SPEC/Design → Implement → Verify → Review，不得绕过）；定义单次显式 refresh → upsert 的调用链、幂等键与 delete_by_filter 清理脚本。
4. **G-CF-POST 验收输出**：定义只读命令 allowlist 的输出模板（集合存在性、唯一键 canonical、行数、日期窗口、字段名清单、零写入证明）。
5. **completed-date 消费**：复用 `skills.infra.date_utils` / `CompletedSessionPolicy` 契约，fail-closed；不实现 OQ-11 composition。
6. **阈值一致性**：字段映射停止条件唯一公开阈值为「匹配率 ≥70% 才可通过；<70% fail-stop」（对齐 `MATCH_RATIO_CONDITIONAL=0.70`，唯一阈值输入；旧字段名不匹配阈值表述已由 RFC-03-014 V0.33 P0 阈值纠正废弃，§14.8 同源行已随本卡同步）；Design 不得引入与本节冲突的替代阈值或在本链静默改写停止条件。
7. **不扩展边界**：不改 P3-A / P3-C / OQ-11 / OQ-11B / name_em / cons_em 既有语义与状态。
8. **G-CF-LIVE-R3 工具链（V0.34 新增，§R3.3.bis）**：定义 direct transport 直连诊断调用封装（子进程临时清空 `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`、`NO_PROXY` 仅本机最小默认值；不改 shell profile/.env/系统/服务/网关）、真实 HTTP request timeout=10s 的施加与验证（`effective_http_timeout_seconds` 记录）、至多 1 次逻辑 Provider 调用的预算护栏、脱敏异常层级报告（异常类、message 摘要、cause/urllib3 子类）、临时报告 `/tmp/yquant-g-cf-live-r3-20260804-<run-id>/` 的 0700/0600 权限与账本字段（provider_attempts/actual_calls/retry/fallback/mongo/write=0/direct_transport/effective_http_timeout_seconds）；Design 须明确本 Gate 是独立授权异常 Gate（非 R1/R2 自动重试）、不产生生产结论、rollback 仅撤销未来 R3 代码路径不回滚历史报告/数据。

### R3.11 一致性声明

- 本 §R3 与 §R2.4 G-R2-2（P3-B capital-flow chain 骨架）、§R2.2 完成矩阵 P3-B 行、§14.6.bis（PR-DDL-P3B 冻结契约）、DESIGN-03-014 §6.4.bis 逐项一致；如有差异，以本节 + 权威冻结契约（SPEC §14.6.bis / DESIGN §6.4.bis）为准。
- **DESIGN-03-014（当前 V0.37；基线本轮时 V0.33 → Design V0.37）**：Design §R3（P3-B S1 重建）已在 V0.37 独立重建（恢复核验卡 `t_eb2ed46e` 之外、由 Design V0.37 卡产出）；本 SPEC V0.34 卡**不修改、未宣称** Design 已同步——Design §R3.3.bis「G-CF-LIVE-R3」是否纳入属后续 Design 卡范畴。基线对齐：本轮 §R3 重建 + V0.33 P0 阈值纠正 + V0.34 G-CF-LIVE-R3 直连诊断均以 **RFC V0.34** 为唯一 RFC 上游；本 SPEC V0.34 镜像 + 与 Design V0.37 §R3 一致性由后续 Design 增量同步卡保证，本卡不动 Design。
- **V0.34（2026-08-05，G-CF-LIVE-R3）**：本节新增 §R3.3.bis「G-CF-LIVE-R3」独立授权契约（唯一 endpoint `stock_individual_fund_flow(stock='600519', market='sh')`、600519/CN、candidate date 2026-08-04、direct transport、1 call/10s timeout、零 retry/fallback、零写、fail-stop 脱敏异常、临时报告 `/tmp/yquant-g-cf-live-r3-20260804-<run-id>/`、rollback 仅撤销未来 R3 代码路径）；R3 是**新一次独立授权 Gate**，不是 R1/R2 自动重试；R1/R2 历史事实（均 `ConnectionError`、经继承代理环境；`DEFAULT_TIMEOUT_SECONDS=3` 未传至 AKShare 1.17.54 内部 `requests.get`）不改写；不产生生产结论、不替代四 Gate 链；不扩展 P3-A/P3-C/OQ-11/OQ-11B/name_em/cons_em 既有语义。RFC-03-014 V0.34 §R3.3.bis/§R3.9 第 9 项同步镜像。
- 本卡未扩展 P3-A / P3-C / OQ-11 / OQ-11B / name_em / cons_em 的既有语义；未修改任何代码/测试/配置/脚本/数据；未执行 DDL/DML/Provider/Mongo/Git 写入；未读取 `.env`/secret；未调用网络/AKShare/Mongo/Provider。

### R3.12 Phase 3 收口事实归档（V0.36，2026-08-07）

本子节为**事实归档**（不改任何冻结契约条款），与 RFC-03-014 V0.36 §R3.12 / DESIGN-03-014 V0.39 §R3.12 镜像，记录 2026-08-07 Phase 3 全部任务链收口的历史事实，供审计与追溯。关联 Kanban 卡均已在看板保留完整 evidence comment。

#### 一、P0 三链完整闭环（0 blocker / 0 major / 0 minor）

| 链 | Implement | Verify | Review | 关键契约 |
|---|---|---|---|---|
| T6 Fix（600519+3s）| `t_bd702b21` done | `t_8138a09b` PASS 8/8 | `t_6fcb4cf3` APPROVE | 600519 固定 target 不可绕过；`DEFAULT_TIMEOUT_SECONDS=3` |
| T6RR Fix（9 项口径）| `t_f3cf3465` done | `t_645be03e` PASS 34+144 | `t_0aa4580c` APPROVE | 4 处 docstring 统一"P3-B canonical expected subset (9 项)"；akshare 1.17.54 静态事实 13 列无股票代码 |
| T4R（smoke P0 收敛）| `t_3bc54206` done | `t_1bb2a989` PASS 144 | `t_83495656` REVISE→Minor-1 Fix `t_5626e1b7`→Verify `t_d8ff8da1` PASS→Review `t_ce772dfc` APPROVE | 5 files allowlist；`MATCH_RATIO_CONDITIONAL=0.70`；phantom anchor 清除（注释锚点改指 DESIGN §4.2.2/§15.14.1） |

#### 二、微型 Verify replacement 三链（原卡 iteration budget timeout 冻结）

| replacement | 内容 | 结果 | superseded 原卡 |
|---|---|---|---|
| `t_2e885585` | OQ-11 严格交易日 policy | PASS（96 passed）| `t_2bd68372` |
| `t_e6efa5e3` | Step-4 脱敏投影与历史基线 | PASS（144 passed ≥119）| `t_eeea25d9` |
| `t_81d7c7ad` | V0.2 r0 E-005/W-001 契约 | PASS（19 passed，产物在 llm-wiki 仓库）| `t_6f646f4b` |

#### 三、真实生产证据

| 项 | 结果 | 证据 |
|---|---|---|
| PR-2 name_em 单次 smoke（08-04）| ProviderUnavailableError fail-stop | `t_55d44505` blocked evidence |
| PR-2 name_em 轻量重试（08-07，Pascal 重新授权）| ProviderUnavailableError（SSL/连接级），预算=1 耗尽 | `t_91ffe99e` done，verdict=`provider-unavailable-frozen` |
| Step-4 T3 三 Gate | PR-0 CONDITIONAL_AUTHORIZED / PR-1 Mongo 只读可达 + 3 集合在场（designated baseline）/ PR-2 由并行卡 frozen 覆盖 | `t_81432128` done |
| 结论 | name_em 按 R2 永久废弃语义不变；三集合=designated historical baseline（RFC V0.27 §R2.3），presence 非 PR-1 FAIL | Pascal 2026-08-07 确认 |

#### 四、仓库卫生事实归档

- commit `09fdffa`（2026-08-07）：`.worktrees/t_997a95a3/` 4 个误提交文件（investigate.py / precheck.py / precheck_report.json / write_report.py，含生产 MongoDB 计数快照）从 git 索引移除（本地保留作审计证据），`.gitignore` L85 追加 `.worktrees/`
- 链：Fix `t_8602c56e` done → Verify `t_1003d459` PASS 7/7 → Review `t_9fd250be` APPROVE

#### 五、测试与验证总账

- t4_preflight：144 passed（多轮独立复跑一致）
- unified_data：1426 passed（全量）+ 165（6 文件回归）
- infra session_policy：96 passed
- 全程零真实 I/O（除已授权的 PR-2 单次 smoke + git push 09fdffa）；git diff --check 全绿
