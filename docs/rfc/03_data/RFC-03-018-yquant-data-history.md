# RFC-03-018: Unified Data 独立库与 BTC5m 官方历史每日摄入

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | V1.1历史基线 + V1.2 Step1/2已裁定；待新候选独立Verify及生产补齐，不代表通过 |
| 作者 / 更新 | YQuant Principal基线；YQuant按Pascal裁定增补，2026-11-12，Asia/Shanghai（UTC+08:00） |
| 项目 / 任务 | `/home/pascal/workspace/yquant-investment` / `t_2f744e19` |
| 对应契约 | [SPEC-03-018 V1.1基线及§9 V1.2](../../spec/03_data/SPEC-03-018-yquant-data-history.md)、[DESIGN-03-018 V1.1基线及§2.9 V1.2](../../design/03_data/DESIGN-03-018-yquant-data-history.md) |
| 裁定来源 | [已批准纠偏安排](../../../data/tasks/active/2026-11-11-yquant-data-history/correction-plan.md)；不重新选型 |

## 1. 目标与事实基线

同一 Mongo 实例中，UD 自有数据以非破坏复制、内容核验、装配切换迁至 `yquant-data`；TA-CN 原始数据仍只读 `tradingagents`。复用现有 data-pipeline 和 UD 窄读取，保存 Predict.fun 官方 BTC5m rounds、Binance 官方 spot BTCUSDT 1s 成交 K 线，提供固定历史回填与每天上海 11:00 统一增量。

主窗口固定 `[2026-08-10T00:00:00Z,2026-11-10T00:00:00Z)`：92 个 UTC 日、7948800 秒槽、26496 个名义五分钟槽。名义槽不等于官方实际轮数保证；预热单列，不缩小主窗口、不用样本日替代。

当前候选已落盘。主控停止旧 run3592 后冻结 `evidence/rebaseline/candidate-baseline.json` 的 52 项，回归日志为 1750 passed / 433 warnings / native exit 0 / 23.38s。这只是候选校准，不是独立验收；旧 Design 的“尚未实现”清单不再作为重建依据。精确剩余差分见 Design。

本 RFC 仅替代旧 03-007/008/009/011/014/015/016 中 UD 必须同库及业务库等于认证源的部署限定；TA-CN、行业算法、冻结 R3 与其他业务契约不变。

## 2. 已定范围

| 决策 | 首版交付 |
|---|---|
| 双库 | UD 目标固定 `yquant-data`，认证源沿用合法原连接，禁止全局改 env、隐式回落旧库 |
| 迁移 | 仅五个明确集合及实际 options/index/TTL，源保留、目标冲突不覆盖 |
| 两源 | Predict `btc-updown-5m` 官方 rounds/结算证据；Binance spot BTCUSDT 1s 官方日 ZIP/CHECKSUM |
| 摄入 | 同一入口 backfill/daily，按日、有界批处理、自然键幂等、断点续跑、pending 按 ID 回查 |
| 研究 | 默认稳定窗口快照读取、一次内容摘要、来源/观察时间/标签隔离；不宣称 strict PIT/live 等价 |
| 每日 | 当前 yquant 唯一 script-only/no-agent job，11:00 Asia/Shanghai，成功/失败输出均 local |

迁移集合名不变：`03_data_ud_sector_ranking_daily`、`03_data_ud_query_audit`、`03_data_ud_market_sector_snapshot`、`03_data_ud_market_sentiment_snapshot`、`03_data_ud_stock_capital_flow`。
T1 历史只读 inventory 为 34534/7/0/0/0、options={}；ranking 日期方向 -1，audit TTL 31536000 秒。它们是旧观察值，P1 以现场实际内容/metadata 为准；未知 UD 对象报告，不通配复制或自动扩大本次五集合。

## 3. 数据流与不能削减的底线

官方只读 GET → `data/source/predict-btc5m-history/` raw/ZIP/CHECKSUM → 既有 DataPipeline extract/transform/validate/batch load → `yquant-data` 永久历史/日进度 → UD 窄只读 facade → 研究薄适配。

- raw 精确字节与 SHA-256 先落盘，不覆盖不同 hash；官方 checksum/CRC/schema 失败不能标成功。
- 业务时间保留 int64 UTC 微秒，价格/数量保留 Decimal128；不经 float 损失主数据精度。
- rounds 与秒线各用自然唯一键；重复相同事实不膨胀、不重置首次观察时间；冲突显式报告，不覆盖已接受事实。
- ENDED 不等于 RESOLVED；官方结果/endPrice 只作标签，pending/unavailable/conflict 不伪造标签。
- 两源连续完整水位不能越过缺口；联合水位取两源最小值；空响应、最大时间、count 相等都不是完整证明。
- 凭据、认证头、原连接异常不进 raw/报告；权限不足只报具体 namespace/action，不自动建用户、角色或升权。

## 4. 受限迁移和稳定研究前提

短窗口由主控准备已知 UD 写入口/责任进程清单、操作者在窗口内不提交并发 UD 写的确认及起止时间。复制前后核对源内容与 metadata、目标逐 ID 内容与 metadata；非 TTL 漂移或目标冲突 STOP。TTL 只按原时间及真实过期差集归因，不重置时间、不关闭 TTL。

不要求“全球所有外部 writer 绝对不存在”的证明，不建静默签名/hash/时效 token。逐 ID 内容核对按当前规模有界执行即可；已有 SQLite 摘要内部实现可保留，但不是首版必备设施，不扩成通用 BSON/任意集合迁移框架。实际不支持的结构才 STOP 报告。

研究在读取和消费期间不主动安排本任务写入，并取得该窗口不并发写的操作确认；若实际发生写入/已知变化，当前快照不得当稳定样本，另取稳定窗口重读。保留业务内容摘要、raw 来源及 available_at。观察时刻与业务时刻分离，显式 proxy 仍只是理论可得假设；即使 observed 也不宣称并发条件下严格 PIT。

严格并发快照、逐页反复核验、三流消费确认协议、通用可得时间调度器、复杂公平轮转均移出首版必验；已正确且低维护的增强可保留，不为简化强拆，也不新增其专项门禁。

## 5. 三项独立交付与既有任务链

1. 工程交付：C1 → C2 独立文档检查 → C3 最小差分 → C4 独立 Tester → C5 独立 Reviewer。全线零真实 DB/HTTP/凭据/调度；工程 PASS 只表示实现与底线测试通过。
2. 迁库交付：C5 后 P1 执行冻结迁移 CLI，在主控准备的短窗口做真实五集合复制/核验；不再开发功能、不把本卡 done 当生产授权。
3. 数据交付：P2 执行冻结 CLI，真实首日资源测量、固定 92 日回填、daily 实跑；P3 只读独立核验。价格覆盖、轮次枚举、官方标签及 pending 分列。

原已批准非破坏授权仍有效，短窗口确认是操作事实而不是重复索要授权。执行期环境/权限失败报告具体原因；代码缺陷退回最小 Fix，不偷偷修改已审候选。
主控在 P3 通过后按原授权安装唯一每日 job 并读回 next_run（上海 11:00）；不另设 Activation 阶段。不声称未来自然 tick 已发生。
工程、迁库、数据覆盖分别报告；固定 92 日或每日目标未齐，不能最终全项目 Closeout。

## 6. 风险与边界

| 风险 | 本次处理 |
|---|---|
| 已知入口之外并发写、TTL 变化 | 操作窗口事实 + 源前后/目标内容核对；不是严格并发快照承诺 |
| 官方归档延迟、结算缺失 | 保留日缺口/pending，有限续跑；不能缩分母或换源 |
| 首次回填容量/时长未知 | P2 首日实测 raw/BSON/索引/耗时/RSS 后外推；不把估算当实测 |
| 新库权限不足 | 精确 namespace/action 缺口，STOP 受影响通道，不改 RBAC |
| WSL 休眠漏 tick | 下次 daily 补缺，不改宿主/服务或承诺自动唤醒 |
| 切换后新库已有增量 | 留存增量与摘要，优先修复新库；不得直接切旧丢数据，旧库补写另行授权 |

不触及 Rust、旧 research、交易/签名/资金、外发、其他项目/profile、依赖、服务、全局配置或 Git 写操作；不新建平台、后台 runtime、长期双写或额外阶段。

## 7. 本轮修复补充：Flat 与轻量流程（Pascal明确批准）

Pascal在指出双WON可能表示不涨不跌后，明确要求修复、采用“Implement → 独立Verify → 主控收尾”、省略独立Review，并同步相关文档。本节仅适用于本轮续扫检查点与Flat修复，不追认旧失败、也不豁免原P2/P3生产验收；历史C1–C5及其审查结论保持各自原范围。日期2026-11-11，Asia/Shanghai。

官方Chainlink市场文档区分Up/Down/Flat；已归档5个具体市场的description明确“起止价格完全相同则50-50”，且五条官方startPrice/endPrice相等、Up/Down均WON。不能只凭resolution.name=Up误标上涨，也不能把这类合法平局永久视为源数据错误。以SPEC §8的多证据联合条件映射现有DRAW枚举，不新增预测标签种类、不用Binance或proposedOutcomeId替代官方证据。

只修既有摄入模块，精确范围见Design §2.8。数据来源、原始字节、最终结算日志与时间、精度、幂等、连续水位及特征/标签隔离底线仍适用。不增加平台/集合/依赖/服务。原生产中5条隔离记录及孤立检查点保持不写，后续纠正须列明精确更新范围并获生产授权；离线修复PASS不是生产覆盖PASS。

## 8. Step1/2恢复与补齐修订（2026-11-12 Pascal批准，V1.2增量）

Pascal已批准完成20批审计建议的第1、2项：固定92日缺口/日账闭合、集中恢复逻辑及daily接线修复。沿已选择Light Flow，集中Implement→独立Verify→主控原P2补齐；不新增Principal/独立Review/Activation，不据本次工程通过提前执行正式P3或安装cron。旧§7及历史候选身份只保其原范围。

复用现有两源/同库/CLI；范围不扩至策略/盘口/预热/第三方。修复包括：按错误分类而非统一24小时的日恢复、旧网络due兼容、精确指定日的人工复核入口、持久回查次数退避、日manifest与标签/连续水位闭合、枚举水位维护、显式冻结窗重扫、daily只读规划和apply锚点一致、安全env/file凭据注入与完整退出报告。具体可计算规则见SPEC §9，代码范围见Design §2.9；执行裁定镜像为本主题correction/step12-recovery-contract.md。

生产仍由主控沿原P2执行，仅yquant-data三历史集合及官方raw。Predict08-11/11-09及Binance16未完整日是本次恢复目标；旧Flat只经官方证据/受限loader更新，不手改标签/due/manifest求齐。原始旧20批与失败记录不覆盖。最终幂等、daily生产实跑、原P3及唯一每日job仍分开交付；本次请求不代表全项目验收通过。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.2 | 2026-11-12 | Pascal批准审计建议1/2，新增§8并对齐SPEC §9与Design §2.9；旧C1–C5/Flat/HTTP通过事实保原范围，新的工程及生产尚未签收 |
| V1.0 | 2026-11-11 | 原 T1；逐字副本保留在主题 `evidence/rebaseline/RFC-03-018-v1.0.md` |
| V1.1 | 2026-11-11 | 按已批准纠偏替换主正文：复用候选、有限迁移/稳定读取、三交付分离；固定范围与底线不降 |
