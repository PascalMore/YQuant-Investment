# RFC-07-001: Predict.fun BTC 5m——M1 基线与 M2 同核心回放研究

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | M1/M2 限定离线工程已签收；M3 官方历史预测研究 V1.3 已获准 Light，待实现/独立验收；非交易授权 |
| 作者 | YQuant Principal（M1/M2）；YQuant 主控（M3 用户 Light 授权增量） |
| 创建日期 | 2026-11-09 |
| 最后更新 | 2026-11-12 |
| 版本 | V1.3 |
| 所属模块 | 07_trading |
| 依赖 RFC | [RFC-26-072](RFC-26-072-trading-intelligent-trading-framework.md)（模块职责规划，非已实现公共执行服务） |
| 替代 RFC | 无；本 RFC 是首个受限场景契约，不替代模块规划 |
| 派生 SPEC | [SPEC-07-001](../../spec/07_trading/SPEC-07-001-predictfun-btc5m.md) |
| AI 适配 | M1/M2 历史 Full Flow；本轮 M3：Developer → Tester → YQuant Closeout（Light） |
| 来源任务 | M1 t_24ca3fd4；M2 t_36000446；工作区 `/home/pascal/workspace/yquant-investment` |
| 标签 | #交易 #复用 #源码接入 #离线基线 #授权边界 |

适用阶段（以下为 V1.2 历史说明，本轮 M3 另按 V1.3 §14）：§1–§12 保留 M1 需求及接入时点快照，不能把其中“本期”“不回放/不建 Lab”等 M1 限制解释为 M2 禁令；M1 最终状态以 [签收报告 §13](../../../data/reports/2026-11-09-predict-btc5m-m1/report.md) 为准。§13 是本轮 M2 的增量决策，派生 SPEC §9–§15；原有 Design V1.0 仅覆盖 M1，须另经 T2 增量设计后才能实施 M2。后续 C–H 是历史规划，不是本轮自动授权。

## 14. M3 官方历史预测研究（V1.3 当前增量）

2026-11-12 Pascal 明确选择“轻量：最小契约同步→实现并跑研究→独立验收”。M1/M2 的执行记录、旧 proxy 协议及结果原样保留；此前正文中 M3 未授权/待另阶段等陈述仅为当时范围，本节只追加官方历史预测研究，不授权执行加固、模拟/真实订单或改变原策略模型。M2 最终签收见 t_5207d097；UD 数据和每日摄入另按 03-018，已完成，不重做。

复用链固定为 UnifiedDataClient.read_btc5m_history → 实例 history_input.py → 同一 Rust DecisionCore。正式市场为 Predict.fun BTC5m 官方 start_price/UP-DOWN-DRAW，标的输入为 Binance Vision BTCUSDT spot 1s closed-candle close，不冒充实时 top-of-book 或 Chainlink 同源报价。研究主要落在既有 Lab 实例；允许 fork 内独立、无网/无钱包的薄历史估值入口调用原 valuation，以不放宽旧 replay/proxy 的 strike=spot/horizon=300 防线。不得复制 EWMA/digital_up/round_entry 到 Python。

本轮分析已有 [2026-08-10T00:00:00Z,2026-11-12T00:00:00Z) 94 日、27072 轮，时间切分2026-10-10，轮内偏移30/60/120/180/240/270秒。只读事件时间代理，固定官方strike、逐秒因果波动率和真实剩余时间；无调参/优化/进化。方向/概率/校准与基准对比可研究；没有份额历史盘口及执行证据，不产生成交、PnL、收益曲线或实盘资格。

本轮仅 Implement→独立 Tester→主控收尾，不新增 Principal/Review/Activation；三层各增量先于实现同步。具体可计算规则以 SPEC §16、实现范围以 Design §19 为准。此为 V1.3 变更记录：最小新增研究入口与官方秒级研究，不修改 V1.2 旧研究协议或其他交易能力。

2026-11-12 性能增量：Pascal 在实测读取冗余后选择方案2，允许在同一轻量链最小优化既有 Unified Data history reader；不重建数据层、不改接口/存储/模型，不以10小时预算或并行查询掩盖重复计算。此增量覆盖本轮原“UD源码全部只读”的限制，仅放开Design §19.4列明的reader及其colocated测试；保留业务摘要、三流与变更检测语义，先证等价和真实单日成本再续全窗。

## 1. 执行摘要（Executive Summary，M1 历史需求）

沿用 Pascal 已批准的唯一 Toolkits 底座方案，先交付 M1：最小正式契约、用户 fork 子模块接入、未经业务修改的原版构建/离线测试基线与必要入口状态校正。成功是来源及 Git 状态可追溯、真实构建和业务离线测试可复现，不是策略盈利、执行加固完成或实盘就绪；用户已确认 Toolkits fork，主控已用只读 API 核验来源（§11），准确 URL 输入已闭合，本卡仍不接入源码。

## 2. 背景与动机（Background & Motivation）

- [Intake 研究报告](../../../data/reports/2026-11-09-predict-btc5m-intake/report.md) 已完成公开规则及固定源码核查，研究 SHA 为 `71c0e4ff9e299f9a4d81757fd6b15cf54da69b38`。未构建、未运行第三方测试、未接入子模块；静态证据不是动态验收。
- `tarpboi/Prediction-Markets-Trading-Bot-Toolkits` 已有 Rust venue、Broker/runtime、`btc-arb` 和 Predict 盘口 OBI。应在用户自己的 fork 内升级，不因 Rust/Python/Bun 差异重造策略、签名器或执行器。
- 现有计划 A–H 覆盖的工作较大。先完成 A/B，使后续加固与研究建立在实际可构建基线上；收益是减少重复开发和错误状态声明，不承诺复用比例或 alpha。
- `.gitmodules` 已登记 QuantDinger 系列源码，但 Trading 入口仍称其候选且目录未创建。M1 仅校正相关源码状态，不治理全仓历史文档。
- 早前快照中，主控报告 `PascalMore` 账号仓库列表未发现对应 fork，候选 URL 查询返回 404；该结果不再代表当前状态。2026-11-09 恢复授权中，用户确认 Toolkits 与 0xalberto 项目已 fork，主控已用只读 API 核验 §11 的准确来源。确认依据为本任务更新正文及主控 UNBLOCK 评论，本卡不重复调研、不自行创建远程对象；旧 Intake 中 namespace 待确认等描述仅作历史快照。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）

1. RFC、SPEC、Design 分别位于 `docs/{rfc,spec,design}/07_trading/`，统一编号 `07-001-predictfun-btc5m`；当前 T1 仅产 RFC/SPEC，Design 另阶段产出。
2. 将 §11 已确认 Toolkits fork 作为 origin，以 main 分支接入指定子模块；接入阶段读回验证 GitHub fork 关系、gitlink 和 `.git` 归属，保留历史、LICENSE、Cargo.lock。
3. 对实际 fork main 原版审查构建/测试副作用，真实执行锁文件约束下的构建与安全离线测试；依赖下载可联网，业务测试不得连接真实场所或钱包。
4. 独立 Verify 重跑，Review 对照 allowlist、证据及未实现边界；保留每次真实命令、退出码、测试计数、跳过原因。
5. 校正 `skills/trading/SKILL.md` 与 `skills/trading/README.md` 的相关源码状态，并在原版基线后记录 C–H 差量和剩余工作量重估。

### 3.2 非目标（Out of Scope）

M1 不修改 Toolkits 业务源码、测试断言、策略或交易配置，不实现 UNKNOWN/费用/持久化恢复，不启动任何 bot、dry-run/shadow、交易所模拟订单或实时采集。不创建 Lab 空骨架、回放入口、模型、夜报调度、通用 OMS/消息总线/服务/UI；不扩写 `quantdinger.py`。不读取交易凭据、连接账户、做账户签名、充值、approve、下单、撤单、merge/redeem；不做部署、cron/systemd、外部消息发送、生产数据库写入/schema/索引变更。200 USDT 本金和 100 USDT 全实验最大可接受亏损不是上述动作授权。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

先复现原版，再基于差量迭代；源码接入、离线验证和获准运行分别举证，不以其中一个替代另一个。

### 4.2 架构总览

```text
用户确认的 Toolkits fork（origin/main）
  → YQuant 指定子模块（工作树 main + 精确 gitlink SHA）
  → 原版构建 + 安全离线测试证据
  → 独立 Verify / Review / 主控 Closeout
  → 后续按同一契约集增量推进 C–H（本期不实施）
```

唯一拟接入路径为 `skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/`。后续自有增量必须留在该 fork 内，例如子模块内部 `predictfun_btc5m/`；不得建立与子模块并列的第二执行工程。Intake 报告 ASCII 树的兄弟目录为笔误，按任务已明确的同 fork 原则修正理解；本期不修改旧报告，不复制模块级 `spec.md/design` 为第二正式契约。

### 4.3 模块分工

| 模块 | 既定职责 | M1 交付与边界 |
|---|---|---|
| Trading / Toolkits | 唯一预测市场执行底座；后续承载获准版本 | 仅源码与原版构建/测试，不开放运行入口 |
| Strategy Lab | 后续回放、基线/挑战者、样本外与交付 | M1 不创建；旧未来示例 id 为 `predictfun-btc-5m`，已由 M2 §13 统一为 `predict-btc5m-btc-arb`，不创建旧实例 |
| QuantDinger | 现有支持范围内的 BTC 特征/方向研究 | 不增加 Predict 执行路径，不把二元份额伪装 BTC 现货 |
| Data / Risk / Portfolio / Reports | 未来数据规范、确定性约束、已对账事实投影与报告 | M1 无新业务接口、集合或服务 |
| Hermes | 只读脱敏复盘、参数偏差、研究提案、跨会话记忆 | 无签名、订单、运行控制或自动发布生产参数权限；M1 仅工程文档/离线验证 |

## 5. 详细设计（Detailed Design）

### 5.1 业务流程（Flow）

1. 主控核验 T1 两文档后另派 Design；Design 冻结 M1 文件 allowlist、接入/核验操作、安全测试范围、证据与回滚方式。fork 输入已闭合，不以此追加澄清；T1/T2 文档阶段仍不得 clone。
2. Implement 开始接入前，使用 §11 已确认 Toolkits fork URL，读回 GitHub 元数据，确认 `fork=true`、parent/source 可追溯至指定 upstream，且 main 可用；URL 不符则停止该接入步骤，不能改用 upstream 或自动创建 fork。
3. 按现有子模块模式登记 `path/url/branch=main`，工作树 main 跟踪 origin/main，记录实际 SHA 与研究 SHA 差异；不得自动同步 upstream、切换旧研究 SHA 或使用 detached HEAD 求一致。
4. 审查实际 fork 的 Cargo 入口、构建钩子、配置加载、全部待运行测试及其外部调用，再执行真实 build/test。不得照抄 README 的 `cargo run`、`check-venue`、`--ignored` 等操作。
5. 报告原版结果、实际跳过项和已知缺口；基线通过后才重估 C–H，不在 M1 顺手加固。Verify 独立重跑，Review 审查来源、状态、构建及文档，主控完成 M1 Closeout。

异常分支：接入时 fork 不可访问或来源不符仅停止相关接入并报主控，不把已闭合输入重新列为待确认；工具链缺失、锁定构建失败或安全离线测试失败应保留真实错误并报主控，不自动全机升级、改锁文件、改策略或持续设计迭代。缺证据不标 PASS；已有文件/目录冲突不覆盖、不 stash/reset/clean。

### 5.2 数据模型（Data Model）

M1 只有工程证据，无新增订单/市场/账本业务模型。最小证据实体及字段在 SPEC §4/§4.bis 冻结：

| 实体 | 必须表达的事实 | 关系 |
|---|---|---|
| 来源基线 | 用户确认 fork、parent/source、research SHA、actual main SHA、差量 | 以实际子模块 SHA 关联构建与验证 |
| 命令结果 | 角色、工作目录、精确命令、版本、起止时间/时区、退出码、日志引用 | 每次运行各自记录，不覆盖旧结果 |
| 测试范围 | 真实测试名、分类、运行/跳过及原因、实际计数 | 与命令日志及原版测试清单核对 |
| M1 结论 | 验收逐项结果、未完成项、C–H 差量及估算限制 | 不将原版 PASS 外推为业务安全/收益 |

### 5.2bis 持久化策略（Persistence Strategy）

| 数据类别 | 存储介质/路径 | 生命周期 | 隐私与边界 |
|---|---|---|---|
| 正式契约 | Git 文件 `docs/{rfc,spec,design}/07_trading/{TYPE}-07-001-predictfun-btc5m.md` | 随审批修订，不复制第二正文 | 工程资料；本卡不 commit/push |
| fork 来源与固定版本 | 主仓 `.gitmodules`/gitlink、子模块 main 及 LICENSE/Cargo.lock/历史 | 本期不自动同步或升级；后续变更须可追溯 | 远程 URL 不含 token；不读取账号凭据 |
| 基线/验证结果及脱敏日志 | `data/reports/2026-11-09-predict-btc5m-m1/report.md`、其 `evidence/` | 保留本次各阶段证据，不设 TTL、不自动删除/归档 | 不含密钥、账户私密数据；`data/` 被忽略，不等于远程备份 |
| 阶段交接 | `data/tasks/active/2026-11-09-predict-btc5m-m1/` | 整体任务结束由主控归档到同名 `done/`；T1 不提前搬迁 | 仅工程路径、结论、待办，无凭据 |

恢复依靠保留的 SHA、锁文件、原始日志和完整阶段记录；Git 源码与本地忽略的报告分别保存，不虚称已备份。M1 无生产 schema/迁移。后续新业务状态默认 MongoDB，集合、索引及写入须届时设计并单独授权；不引入 SQLite 生产账本，不迁移 QuantDinger 自身数据库。

### 5.3 接口契约（API Contract）

本期没有新 HTTP API、CLI 或业务函数签名。接口是用户确认的 fork URL、Git 子模块及现有 Cargo build/test；SPEC 定义各输入、观察值、通过/失败与证据格式。保留原包名 `polymarket-toolkits` 和原有构建入口，不借接入重命名工程。

### 5.4 AI 模型设计（如有）

M1 不训练、加载或发布 AI 模型，不引入在线 LLM；不冻结 C–H 的概率、订单或账本字段。后续同一 Rust 策略核心供回放与获准运行复用，Lab 是研究编排，不复制多语言决策核心。

## 6. AI 实装规范（AI Implementation Rules）

### 6.1 必须执行

- 只按 SPEC 与后续 Design 的 M1 allowlist 接入和验证；基线源码不变，LICENSE、Cargo.lock 和历史不变。
- 审查构建/测试副作用；明确“允许依赖下载”与“禁止业务联网”。默认 dry-run 仍可能读实时盘口并签名，不属于 M1 离线测试。
- 允许审查后运行仅使用仓库公开固定测试向量的本地密码学单测；不读取真实凭据，不为真实账户或实时盘口创建签名。
- 如原版测试名称含 `live`，按真实依赖分类：FakeVenue 单测不等于真实账户运行；测试名称不是联网授权或跳过依据。

### 6.2 先询问再执行

准确 fork URL 已确认，不再次索要 URL 或申请新建 fork，不重新讨论底座选择。新增依赖/锁文件或业务变更、工具链安装/升级及运行/资金/生产数据库等越界事项，先报告主控并取得相应明确授权，不能自动兜底实施。

### 6.3 绝对禁止

直接 clone upstream、自行建远程 fork、擅自 checkout 研究 SHA、同步 upstream、以跳过当 PASS、为绿灯更改业务逻辑或测试。禁止在文档、命令或日志写凭据；不修改 `/home/pascal/workspace/yq-yinglong`、公共模板、profile/Hermes，不 commit/push。

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| 接入时 fork 不可访问或来源不符 | 未测；输入已确认 | 无法接入 | 使用 §11 固定来源，接入时读回 GitHub parent/source | 停止相关接入并报告，不 clone upstream |
| actual main 与研究 SHA 漂移 | 未测 | 静态结论/命令可能变化 | 基于实际 SHA 重审并列差异 | 保持 main，不回退旧 SHA，报告差量 |
| 工具链/依赖/原版测试失败 | 未测 | M1 基线不完整 | 实际版本、退出码、原始错误；不改锁或自动升级 | 停在可证实结果，交主控处理 |
| 将默认 dry-run 当离线 | 已有代码可见 | 可能联网/账户签名 | 只运行审查通过的 build/test，不运行 bot/venue 检查 | 有副作用测试分类跳过且不计 PASS |
| UNKNOWN 回填、净份额/费用和恢复缺口 | 静态已见、动态未测 | 真实风险/账本错报 | 记录为后续 C 加固；M1 不激活执行 | 不运行、不开真实资金权限 |
| S2 被误称已支持 BTC5m | 静态已见 | 错误复用承诺 | 原 OBI `MIN_SECS_LEFT=600` 且运行路径调用 `is_quotable`；已开始 5m 轮次不可据此视为适用 | M1 保留原版；后续 E 评估最小适配，不另造策略 |
| 参考仓库许可不完整 | 研究已报告 | 无权复制代码 | polybtcbot、0xalberto 仅研究思想/对照，不接入执行工程 | 将来确需复制时先核实授权 |

## 8. 备选方案（Alternatives Considered）

- 直接 clone upstream 或拷贝源码：虽快，但违反用户 fork 和子模块要求，不选。
- 并行维护 Toolkits、polybtcbot、0xalberto 三套执行器：预算/订单/恢复分裂，重复维护且参考代码授权未清，不选。
- 立即重写 Python 策略、改造 QuantDinger 为二元市场：已有 Rust S0/S2 被重复实现，且 OHLC 撮合不能等价二元份额执行，不选。
- 将 A–H 全放入首版或先造通用平台：不能尽快得到可测原版基线，超出本阶段目标，不选。原架构已定，不把这些备选重新交用户选型。

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收

具体判据见 SPEC §5：用户 fork 来源可追溯；指定 path/url/main、160000 gitlink、主仓管理的 `.git` 文件及 main=origin/main 一致；保留历史/许可证/锁文件并记录研究差异；真实原版 build/test、分类及日志齐全；入口文档区分源码、验证和运行许可。当前 T1 仅要求两独立文件互引可解析、M1 行为可测、已确认 fork 输入一致。

### 9.2 非功能验收

独立 Verify 重跑与 Review 无范围越界；命令、版本、SHA、时间/时区、退出码和测试计数可复核。不设本期吞吐、时延、覆盖率百分比、收益或观察日数门槛；新增门禁仅来自本卡来源/版本/原版验证/副作用边界，不夹带 C–H 运行要求。

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分

| 阶段 | 内容及退出条件 | 不在该阶段宣称 |
|---|---|---|
| A/B = M1 | 本契约集 → Design → 用户 fork 接入 → 原版 build/test → Verify → Review → Closeout | UNKNOWN/费用/恢复已修复，策略盈利或获准运行 |
| C | 既有 Predict/Broker 的 UNKNOWN、净份额/费用、挂单占用、持久化预算与跨重启恢复加固 | 新 OMS/第二账本 |
| D | 既有接口上的事件记录、可注入时钟、replay 与 Lab 薄入口 | BTC OHLC 等于二元份额可执行 PnL |
| E | S0=既有 btc-arb、S2=既有 Predict OBI；最小动量/校准与 Binance OBI 差量对比 | 现有 Predict OBI 就是 Binance 深度信号，或已适配 BTC5m |
| F | 脱敏只读复盘、参数偏差、经验检索 | Hermes 控制运行/签名/发布参数 |
| G | 后续故障测试、信号对拍、获准无订单观察 | M1 已执行 shadow，或仅凭观察日数放行 |
| H | 经具体资金/账户/期限授权的小额执行验收准备与外部系统执行 | 本金/亏损容忍等于充值/approve/交易许可 |

C–H 后续增量复用本 RFC/SPEC/Design 契约集，按实际范围修订，不预建大量文档。市场硬边界：Chainlink 指定报告为结算标签，平价 50–50；BTC OHLC 不代表二元份额成交/可执行 PnL。UNKNOWN 不得以请求数量回填；买入净份额、费用、仍可成交的挂单占用和持久化损失预算为 C 必须处理事项。200 USDT 初始本金、100 USDT 全实验最大可接受亏损是用户约束；1 USDT 单笔、5 USDT 占用、5 USDT 日停、20 USDT 复核仍是建议，未激活。

### 10.2 任务清单

T1 只写 RFC/SPEC 与交接；主控读回后派 T2 Design。T3 Implement、T4 Verify、T5 Review 由不同角色承担，主控 Closeout；本卡不自行创建下游卡。M1 成功后才以实际构建/测试结果重估 C–H，区分工程时间、授权等待与数据观察；Intake 工时仅为未构建前估算，不为构建失败无限追加设计迭代。

## 11. 开放问题（Open Questions）

M1 fork 输入已闭合，无需再次向用户确认。依据：任务 `t_24ca3fd4` 恢复授权正文与主控 UNBLOCK 评论（2026-11-09，Asia/Shanghai）；下表为主控只读 API 核验的交接事实，不声称本卡重新查询或已克隆。

| 用途 | 用户确认 URL | 主控核验元数据 |
|---|---|---|
| 唯一生产底座；M1 唯一拟接入子模块 | https://github.com/PascalMore/Prediction-Markets-Trading-Bot-Toolkits | `fork=true`；`default_branch=main`；parent/source 均为 `tarpboi/Prediction-Markets-Trading-Bot-Toolkits` |
| 仅研究参考，不部署、不登记第二子模块 | https://github.com/PascalMore/predictfun-trading-bot | `fork=true`；`default_branch=main`；parent/source 均为 `0xalberto/predictfun-trading-bot` |

已拥有参考 fork 不等于代码许可已补齐或可部署。其余底座/目录/分工/阶段边界已定；实际工具链、fork main SHA/研究差异及安全测试列表是接入时可发现事实，不是重开架构选型的问题。资金细则、认证市场参数及运行授权是后续 C–H 边界，不是当前文档门槛。

## 12. 参考资料（References）

- [Intake 报告](../../../data/reports/2026-11-09-predict-btc5m-intake/report.md)、[来源记录](../../../data/reports/2026-11-09-predict-btc5m-intake/evidence/sources.json)、[固定源码树](../../../data/reports/2026-11-09-predict-btc5m-intake/evidence/tarpboi-tree.json)。研究存档不完整，不是可运行安装包。
- [Toolkits 固定版本](https://github.com/tarpboi/Prediction-Markets-Trading-Bot-Toolkits/tree/71c0e4ff9e299f9a4d81757fd6b15cf54da69b38)；本地存档相对 `evidence/tarpboi/`：`src/bot/arbitrage.rs:33–78,230–277`、`orderbook_imbalance.rs:1–8,26,60–96`、`runtime.rs:419–435,971–975`、`src/service/predict_fun.rs:1979–2005`、`docs/LIVE-TRADING.md:3–5`。均为静态核查，不是运行结果。
- [Predict BTC5m 市场规则](https://predict.fun/market/btc-updown-5m)、[Chainlink 说明](https://docs.predict.fun/developers/chainlink-price-markets)、[费用](https://dev.predict.fun/trading/fees)、[订单生命周期](https://dev.predict.fun/trading/order-lifecycle)；来源日期和验证边界见 Intake。
- [项目 AGENTS](../../../AGENTS.md)、[Trading 技能](../../../skills/trading/SKILL.md)、[Trading 目录说明](../../../skills/trading/README.md)、[Strategy Lab](../../../skills/strategies/strategy-lab/SKILL.md)、[流水线](../../../skills/infra/ai-coding-pipeline/SKILL.md)。

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-11-09 | 从已批准 Intake 收敛 M1 A/B；明确 fork 待确认、原版验证及后续边界 | yquantprincipal |
| V1.1 | 2026-11-09 | 按原卡恢复授权同步已确认 Toolkits/研究 fork 来源；闭合 URL 输入，旧 404 保留为早前快照；验证过程见交接 | yquantprincipal |
| V1.2 | 2026-11-10 | 保留 M1 历史及最终签收来源；新增 §13 M2 同核心回放、Lab 真实研究、降级/复用与阶段边界；不修改 Design 或代码 | yquantprincipal |

## 13. M2 增量：同核心离线回放与首份真实研究

### 13.1 背景、授权与目标

Pascal 于 2026-11-10 明确要求按 AI Coding Pipeline 推进并限定“M2”（任务 t_36000446）。M1 已完成用户 fork 接入、原版构建与安全离线测试，独立证据为 164 passed / 0 failed / 3 ignored；不是完整策略回测或实盘就绪。本轮不重建 M1、不重跑其 Cargo 基线或已有数据探针作为 T1 交付。

M2 必须同时交付：可执行且测试过的同核心 Rust 回放、Strategy Lab 实例 `predict-btc5m-btc-arb`、一份真实数据研究与同源 CSV/报告/复现命令。工程完成与研究结论分开：数据不足可按 §13.5 的已批准降级完成工程，但不得声称获得真实净 PnL、完整执行等价回测或实盘放行。

本轮事实来源为 [缺口报告](../../../data/reports/2026-11-10-predict-btc5m-gaps/report.md) 及其脱敏证据；T1 局部源码复核见 SPEC §9.2。2026-11-10 本地观测 Toolkits main/HEAD/缓存 origin/main 为 `71c0e4ff9e299f9a4d81757fd6b15cf54da69b38`，QuantDinger HEAD 为 `6915e390d3886d441b943aa8ee26cd8d10c959ed`；未 fetch，不将本地缓存等同实时远端状态。

### 13.2 范围与非目标

必须目标：

1. 把原版 `round_entry`、`digital_up`、`EwmaVol` 和入场状态复用为单一 Rust 决策路径；实时适配与回放消费同一逻辑，不在 Python/Bun 重写概率或入场公式。
2. 独立本地回放入口读取显式输入与事件时钟，验证 BTCUSDT/300 秒市场和 token 身份、预热、因果顺序、一次成功入场/轮次、重复记录和未知结果。无交易配置加载、网络、签名器或 live 开关。
3. Lab 薄研究脚本复用现成 QuantDinger Agent 行情认证/HTTP/分页；只做 I/O、Rust 调用、指标聚合与报告。首份研究须实际分析真实样本，不能仅交工具或 fixture。
4. 最小提取公共资金权益指标 helper，显式资本与频率；保留网格 wrapper 和既有结果/字段/判定，不能再复制一套收益/MDD/Sharpe。
5. 复用 Lab spec/report 模板核心字段、退出码、证据分级、预算纪律及独立验收；正文和 CSV 由同一行集生成。

不做：M3 UNKNOWN/费用净份额/恢复加固、M4/实盘准备、OBI/动量/LLM/参数优化、后台采集、夜报、第二执行器或研究平台、unified_data crypto provider、QuantDinger 改造、公共模板改写。不得启动机器人/模拟或真实订单、账户签名/充值/approve/撤单/redeem、生产库/DDL/索引、服务/长期调度或外发消息。200 USDT 本金和 100 USDT 全实验损失容忍只记背景，不生成生效交易配置；原版 `order_usd=5` 是离线基准参数，不是资金授权。

### 13.3 核心决策与职责

```text
显式本地事件/配置 → Toolkits Rust 同一决策核心 → 回放决策/原因/状态证据
现成 QuantDinger 只读行情 → Lab 实例验证与因果适配 → Rust 估值/回放
  → Python 聚合与同源 CSV/报告 → Tester 独立重算 → Reviewer → 主控 Closeout
```

- Trading/Toolkits 仍是唯一决策与执行底座；M2 仅抽出可注入时钟/输入的决策能力，现有实时默认参数、source 防护及其他策略不变。不把回放验证器的新 BTC/300 秒输入限制扩散成全局 live 策略变更。
- 同核心是“同决策函数、同 EWMA 更新、同成功入场确认语义”，不是承诺离线撮合与线上执行等价。原版只有正成交才标记 entered；Blocked/零成交不能锁死轮次，UNKNOWN 不可回填全量成交。回放只消费本地明确的结果事实/测试结果，不修 runtime live。
- Python 生产研究路径不计算数字期权概率、不选买入 token；代理研究无份额盘口时只调用 Rust 估值，不虚构市场盘口触发入场。仅独立验收的隔离参考计算可按冻结公式重算，不作为第二生产策略或运行分支。fixture 的可控输入只能证明软件行为。
- Risk/Reports/Data 仅沿用既有规范，无新服务、集合、账本或调度。JSON/CSV 是研究证据，不是生产恢复记录。

### 13.4 数据与复用决策

BTC5m 是到期时长，不是足够的行情采样间隔。完整入场回放需要因果可用的轮内 spot、Yes 盘口（Down 侧沿原版镜像）、深度、市场身份/开盘价/费率/状态；官方 Chainlink 指定报告、平价、暂停/争议及 pending 必须保留。Binance/Coinbase/QD close 都不是官方结算替代品。

现有 QD 只读实测 300 根 BTCUSDT/5m，采样时 299 闭合、1 未闭合；返回无 venue/product provenance。只能声称“QuantDinger Agent BTCUSDT OHLC 代理”，不声明 Binance 现货、gate 实际来源或官方标签。普通 OHLCV 路由不接受 exchange_id/market_type；training_ohlc 的 gate/swap/1D 不适用于此任务。不得通过全局配置换 venue 或新增 provider 绕过。

复用性质与真实函数见 SPEC §9.2：HTTP/认证/分页与 Rust 估值是代码复用；Lab 模板/退出码/验收是规范复用；网格四窗、G/E、35% 和表 A/B 是本实例不适用。研究窗口、切分、频率必须是显式实例参数，不把本次样本长度硬编码成平台常量。

### 13.5 证据降级与输出

先记录历史预测份额/官方标签可得性，再选择分支；不能以只有 OHLC 直接判全策略可回测。

| 可得性 | 本轮允许的研究 | 结论上限 |
|---|---|---|
| 有真实轮内输入、权威标签及相应费用/成交证据 | 同核心历史决策回放；分栏列覆盖与未建模项 | 可以报告证据支撑的决策/模型或明确假设的收益；未修会计不能称真实净 PnL，实盘仍未验证 |
| 缺份额盘口/官方标签，但有真实闭合 OHLC | fixture 回放测试 + 因果 OHLC 概率/波动代理研究（SPEC §11.3） | 工程可验收，研究 `insufficient-evidence`、exit 3；策略净收益/实盘未验证 |
| 连有效真实代理样本也没有 | 保留真实失败/缺口诊断，软件测试与缺口分列 | M2 未完成；不能只凭 fixture 关闭整个 M2 |

概率基准可为恒定概率 0.5（不是份额买价）；不交易基准不等于已知策略收益。真实标签缺失时禁止填假结算、合成盘口、0.5 买价、mock 收益或将 UNKNOWN 当 0。报告必须区分 fixture、真实代理、真实市场回放三栏，即使某栏未运行也保留原因。

### 13.6 交付、持久化与验收

正式契约仍只此 RFC、对应 SPEC、后续原 Design 增量三文件。M2 当前 T1 只改前两文件及 `data/tasks/active/2026-11-10-predict-btc5m-m2/rfc-spec-handoff.md`；不创建下游卡、不写实现级 Design。

研究唯一正文为实例 `skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/reports/report.md` 最新视图。正式归档 `data/reports/2026-11-10-predict-btc5m-m2/report.md` 仅为指向该正文的归档索引（标明 hash/时间），其 `evidence/` 保存本次输入、CSV、命令及测试证据；实例引用这些载体而非维护第二套结论。不可把索引视为已远程备份；`data/` 仍 Git 忽略。再次研究另建日期主题，不覆盖本次原始证据，不建通用 runs/manifest 系统。

SPEC §14 的 M2-A-001..010 是后续 M2 工程验收，全部满足才可 Closeout；研究 `insufficient-evidence` 的合规降级不豁免真实研究、独立 Verify/Review 或可执行回放。报告涵盖样本内外、成本、年化/Sharpe/MDD/Calmar/换手/IR 的适用性、基准、压力假设；无收益序列时保留 N/A 原因，不填代理收益。

完整流程仍为 T1 RFC/SPEC → 主控校验 → T2 Design → Design Gate → Implement → Verify → Review → Closeout；三个实现/验证/审查角色隔离。T2 冻结精确接口/文件 allowlist/离线负向测试与回归路径，原 Design V1.0 不能直接用于 M2 实现。无吞吐、收益、覆盖率百分比、固定四窗或强制观察天数新门槛。

### 13.7 风险、替代方案与开放项

| 风险 | 应对/停止边界 |
|---|---|
| 同核心重构悄悄改变线上行为 | 原参数/输入 golden 对拍及其他策略回归；runtime live、依赖、锁文件不改 |
| 无轮内盘口，粗 OHLC 代理被夸大 | 按 §13.5 降级，明示概率代理不验证原策略入场优势 |
| 分页去重遮住冲突/未闭合/来源未知 | 实例侧在标准化前检查原页冲突，闭合与覆盖因果验证；不扩 QD 平台 |
| 费用/净份额和 Summary.equity 被误当真实账户净值 | PnL 与资本分离，真实净 PnL 未验证；M3 另授权 |
| 共享指标提取改变网格语义 | 真实行为保留，包括首条权益不进入首个 Sharpe 收益；定向零漂移回归 |
| 历史数据不可得或预算耗尽 | 记录可得性与缺口，exit 3/5；不自动后台采集、换通道/凭据或超预算 |

不选 Python 重写策略、QD bar 引擎模拟二元市场、独立行情平台或先做 M3：均不解决本轮最小同核心/证据目标且越界。当前无待 Pascal 决策的范围 blocker；历史数据是否可得是后续有界事实发现，不假定可用。T2 待定仅为接口序列化/模块布局、样本参数默认值、源码级安全测试与具体复现命令，不得改变本节业务语义或扩大授权。门禁来源均为本任务目标、Lab 现行规范或既有资金/副作用边界，未将主观安全建议升级为额外阶段。
