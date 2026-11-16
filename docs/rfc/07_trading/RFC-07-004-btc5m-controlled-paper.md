# RFC-07-004: BTC5m 受控 unsigned paper 与最小运行接线

## 元数据

| 项 | 值 |
|---|---|
| 状态 | V1.1 固定单键来源修订，待主控 Gate；不是本增量实现、运行或实盘验收通过 |
| 作者 | YQuant Principal |
| 创建日期 / 最后更新 | 2026-11-16 / 2026-11-16（Asia/Shanghai，UTC+08:00） |
| 模块 / 工作区 | 07_trading；`/home/pascal/workspace/yquant-investment` |
| 需求来源 | 原始 `t_5b6a743f`；本次 `t_3b2deaac` 转交的 Pascal 2026-11-16 后续启动单键来源固化授权 |
| 派生 SPEC | [SPEC-07-004](../../spec/07_trading/SPEC-07-004-btc5m-controlled-paper.md) |
| 当前 Design | [DESIGN-07-004](../../design/07_trading/DESIGN-07-004-btc5m-controlled-paper.md) V1.3；原 V1.0 独立下阶段产出安排保留为历史 |
| 依赖 | [07-001](RFC-07-001-predictfun-btc5m.md)、[07-002](RFC-07-002-predictfun-live-foundation.md)、[07-003](RFC-07-003-predictfun-wsl-nonexport-signer.md)，不替代其历史签收 |

## 1. 执行摘要

复用唯一 `DecisionCore/RoundTaker → runtime Broker → Predict venue`，补足固定安全运行入口、现有 keyring 到 SDK signer-fd / 主网 market API-key 的接线，以及 opt-in 的虚拟现金约束。完成 Full 工程与独立 Validate、主控核验后，只由主控启动一次 6 小时 unsigned paper：初始虚拟本金 100 USDT、单笔上限 2 USDT、同时敞口上限 10 USDT、费用后累计净亏损达到 20 USDT 锁存停新增；不是实盘许可或 alpha 证明。

V1.1 仅将后续 unsigned-paper 启动的单键来源固化进原入口：父环境完全缺少 `YQUANT_PREDICT_FUN_TOKEN` 时，允许在公开配置与父钱包/JWT 拒绝之后，从固定项目 `skills/.env` 精确读取该键到临时内存副本，复用原 API 来源核验及 child 白名单。已有键（包括空白）不回退、不覆盖；signed/SDK/check/enroll/sign-in 不增加文件回退。既有 R3 工程 PASS、F1/F2 闭合为本次输入基线，不重新开发或宣称本增量已验；原阶段事实/身份保留为历史，当前修订范围以本段和 §5.1 为准。不触碰、重启、停止或重建当前已启动观察，不重跑任何 6h、不修改其证据；修订不授予下一轮自动启动许可。

## 2. 背景、事实与增量边界

`BOT=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。本阶段静态读取当前源码与以下本地报告，不联网、不读取任何生产秘密、不重跑历史实验。

| 已有事实 | 本轮直接复用 | 本轮不据此声称 |
|---|---|---|
| [07-002 closeout](../../../data/reports/2026-11-13-predictfun-live-foundation/closeout.md)：离线执行底座已签收 | 实际成交/未知订单/去重/账户核验、不盲重发、预算确认、撤单竞争与 RPC/签名门禁 | 真实下撤单、approve/redeem 或到账已闭环 |
| [07-003 验收及主控真实认证 §5](../../../data/reports/2026-11-15-predictfun-keyring-signin/report.md) | 精确 keyring、派生绑定、固定 child、普通 check / opt-in sign-in | 策略 run 或 SDK signer-fd 已接通；不重开旧 schema/content-type 失败 |
| `arbitrage.rs:174–209,220–356` 已有 BTCUSDT / 精确时长选择、Binance live guard、单轮一次入场 | 同模型、同 core、同数据源与 round 选择 | 名称 arb 是无风险套利；源码中 Binance 等于官方结算源的注释不是官方事实 |
| `runtime.rs:426–439,963–975,1026–1038,1407–1497` 已有限额、halt、Ctrl-C、cancel_all | 急停/停新增/撤单及数据失败保护 | halt 能平仓、20 USDT 是绝不超损保证、已有跨进程恢复 |
| [旧 6h paper](../../../data/reports/2026-11-12-btc5m-forward-paper/run3-6h-report.md)：48 笔，费用后 -16.219972 USD | 有界启动、日志与官方 settlement 对账的既有方法 | 100 USD 原报告分母是 Broker 现金；原 5/25 参数验证覆盖新 2/10/20 |
| [总体盘点](../../../data/reports/2026-11-16-btc5m-live-readiness-overview/report.md)、[最小金额计划](../../../data/reports/2026-11-16-predictfun-minimum-approval-plan/report.md) | 必要接缝与官方规则来源、有限授权/全局 operator 的区别 | 历史 100 USDT / 0.00499 BNB 是本轮刷新；提案 allowance=10 USDT 已获执行授权 |

静态已见缺口：`local_signer.py:448–503` 只支持 check，不能承载 6h run；`sdk_ops.py:302–312,372–385` 有 signer-fd 消费者但无 keyring 接线、market GET 未注入 API key；`runtime.rs:220–280,503–545` 的 paper 以 gross 份额与单列现金等值费用记账，无 100 USDT 现金账。07-004 仅增加这些必要能力，不重新开发旧执行底座或认证核心。

候选身份（入场只读）：主仓 HEAD `546518b222708022da0ef8b708cdeba2ad1ad8e6`，BOT HEAD `0b8b31092cbd660a53ced463734c4673de055ed9`，均 main；上游 07-003 文档及 BOT README/requirements 的 tracked 修改、local_signer.py/tests untracked 是基线，不能 reset/stash/clean/checkout 或当作本卡越界。

## 3. 目标与非目标

### 3.1 必须目标

1. 明确区分 unsigned paper 与需另行真实授权的 signed future-live；模式、配置、公开身份、限额先校验，paper 永不接触 keyring、钱包或 JWT，不隐式升级。
2. 使用现有 SDK CLI/ops 的目标摘要、显式确认、身份/路由/读回、不盲重发机制，补 keyring→匿名 signer-fd 与固定主网 market API-key 接线；工程仅 synthetic/fake 验证。
3. 100 USDT 进入 Broker 实际可用现金/预占校验；2 是单笔，10 是同时风险占用，20 是从本次起点累计净损益的停新增阈值，互不替代。单市场上限 2 USDT，对应既有单轮只入一次。
4. unsigned paper 的新模式采用显式净份额扣费账，不能沿旧纸面费用口径冒充官方净到账；保持旧默认消费者兼容。
5. 6h 墙钟有界观察、触发后仍可观察/结算但零新增；期限结束不续跑，并有有界官方结果尾查。资金未结清不可重复使用。
6. 产出可复算的资金、来源、停新增、结束及 settlement 证据；真实执行/资金闭环与收益判断分别列明未完成项。

### 3.2 非目标

不调参、不换 Binance 输入、不复制 core、不走 copy OrderExecutor、不引入第二 bot/SDK/钱包/认证协议、OMS、数据库、持久账本、daemon、调度或研究平台。不重跑 94 日研究；其无盘口 PnL，不作为本次盈利门禁。不给无人值守、自动恢复、真实 Gas/排队/部分成交/到账时延或可持续 alpha 结论；不批准 allowance/operator、真实首单或实盘启动。

原 V1.0 T1 只新建本 RFC 与 SPEC。当前 V1.1 文档卡只同步本 RFC、SPEC 和独立 Design，不写代码/测试/配置/报告/技能/模板/三层 README，不访问其他项目或 profile。本增量后续代码范围限 SPEC §2.3 的 V1.1 限定，不重新开放原全量工程范围。

## 4. 方案选择与职责

### 4.1 采用方案

固定薄运行入口只装配原 Rust binary、受限公共配置、最小环境和有限生命周期；paper 使用 market API key，不构造 trader/signer，Broker opt-in 启用虚拟现金与净份额语义。signed 分支复用现有 keyring 和 Rust signer，SDK 资金分支复用现有 CLI/ops 与匿名 FD；两者在本轮只以 fake 执行消费者验证，不由工程 worker 真实启动。

限额、资金不变量和停止状态仍由 Broker 执行，不把 Python 日志分析器当第二交易核心。已存在的取消/对账/未知闭锁继续工作；尾查只是只读结果核验，不能借机开仓或兑付。

### 4.2 不采用方案

- 仅改报告分母：无法阻止已承诺现金/未结清资金二次支出。
- 全局更改 paper 默认或风险默认：影响回放、其他策略及旧消费者；本次 opt-in 即足够。
- 自动 redeem/充值/补 allowance：paper 无需，且资金动作未授权。
- 为一次观察建设持久恢复平台：超出范围；本次明确禁止同次运行重启/续跑，以一次性启动记录防误重入，账本只在内存。

## 5. 业务契约决策

### 5.1 启动与授权

公开模式、目标和配置先检查，再取 API key / signer。unsigned 路径只接受 mainnet Predict 公共行情、BTCUSDT / 300 秒、`enable_trading=false`、`mock_trading=true`、新受控资金参数；显式缺失 credentials 路径不得存在（含悬空链接），不读默认 YAML 或 shell profile。唯一文件例外是父环境根本不存在 `YQUANT_PREDICT_FUN_TOKEN` 时，在公开配置通过且父钱包/JWT 按键存在性拒绝之后，读取固定项目 `skills/.env` 的精确同名键；不加载整个文件的变量，不执行 source/eval/load_dotenv、变量或命令替换，不新增秘密存储/任意路径选项。读取到临时环境副本后仍经原 `local_signer._api_source` 与 `child_environment`：已有源含空白均不读文件，空白仍拒绝，`PM_PREDICT_API_KEY` 冲突仍拒绝，父环境不变。不执行 check-venue 样例签名来证明 unsigned。

该例外只支持单行赋值的可选 export、等号空白、引号及尾注释；重复目标键（同值也拒绝）、缺失/空值、不可读、坏引号、多行或编码错误一律固定脱敏 `API_SOURCE`，不输出原行/值/底层异常，细则见 SPEC §4.1.1。公共 JSON 的秘密键大小写/嵌套拒绝仍在首次 write 之前，新文件读取也不得抢在公开配置或父钱包拒绝之前。后续已获准启动可直接调用原入口，不需 inline 包装；signed future-live、SDK、原 check/enroll/sign-in 完全不增加此文件回退。

signed future-live 必须显式选择，声明同账户预算并保留 07-002 全部账户、链、RPC、授权、未知风险检查；没有未来真实动作批准不能运行。工程实现具备该受限分支不等于当前批准真实调用。SDK plan/check/tx 只读核验不加载 signer；执行分支必须先确认具体 target digest，再取精确 keyring，FD 只交固定 SDK 消费者；不开放任意 command/argv/钱包/可执行文件。

固定公开身份为 chain56，Predict Account `0xfc9eb66e6F22f96608058C0A711Ed048eED8c2E2`，控制 signer `0x5129330159f4E6a99eF873f86901E3cafa7f9A7D`；资产地址与 signer 不混用。SDK target.owner 沿现有含义为持仓账户，链上控制读回才与 signer 匹配。工程正例只能内部注入公开 synthetic 身份，不能伪造固定账户私钥。

### 5.2 现金、费用和风险

以 100 USDT 为虚拟初始现金；可用现金是已记净现金减去未成交买入预占，不能加浮盈、未结算兑付、真实钱包历史余额或未读回资金。持仓成本与剩余订单预占合计受 10 USDT 同时限额约束，同一现金风险只占一次；不会因“10 小于 100”而省略现金门禁。

新受控 paper 模式：BUY 的模拟交易费从 gross 份额扣除，现金只扣 gross 对价；SELL 费从 gross 现金收入扣除。可卖/可兑付仅 net 份额，PnL 用净现金与 net 库存，不再重复扣等值手续费。保留旧 paper 记账作为旧模式，不把两次结果直接拼接为同口径。模型 fee、模拟费用和 live 官方费用是三种证据，不相互冒充。公式与数值用例见 SPEC §4.3–4.5、§5。

累计净损益以本次初始资金为基点（不是盈利峰值回撤、也不是只累计亏损单）：已实现净损益 + 浮动净损益（含交易费）≤ -20 USDT 即锁存停新增。每次成交/资金或估值变化后以及新增前检查；回升不解锁。20 是触发阈值，不是立即平仓/绝不超损承诺。拒绝/未知/数据缺失不造假健康状态。

### 5.3 结算与退出

持有到官方结果，不新加策略主动卖出；亏损触发不自动卖出。paper 仅在官方 settlement 已验证后把 net 份额兑付计入虚拟现金，一次且只一次；到期时间经过、本地 Binance 方向或预测概率都不构成 settlement。live 的账面 settled 不等于 redeem 到账，不因此释放真实可用现金；07-002 真实余额与对账门禁不变。

观察期限固定 21600 秒，以包含进程等待/网络中断的墙钟计时；到期立即关闭新增，再走原 Ctrl-C/cancel_all 与有限回收。停止后仅对已成交相关市场（含最后一轮）做只读官方尾查；尾查有独立有限预算，不延长入场窗，未读到则保留 pending/损益未最终化而不是无限等待或按模型结算。SPEC 冻结边界，Design 细化调用位置。

同一次运行无 restart/resume；正常结束、halt、崩溃或失去启动器监督后不得自动重建 100 USDT/重置损失窗口。已有运行启动记录即拒绝同一 run 再启动，缺/坏结束证据视为中断而非授权重试；新一轮须主控核账及新的明确授权，不借改 run_id 绕过。此为一次观察纪律，不承诺持久恢复账本。

### 5.4 数据来源和能力限度

模型继续使用 Binance，保留既有 paper 的 Coinbase fallback，但标记每笔 source，单列 fallback 成交/损益，不宣称与 Binance-only live 同等证据。官方结果来源按市场元数据记录（既有样本为 CHAINLINK），不可把 Binance 价格当官方结果或声称本轮已测基差。

paper 仍是原盘口 walk 的全额或拒绝模拟；不新增排队/真实部分成交模型。Gas 标 NOT_INCURRED / NOT_MEASURED，不填虚构 gasUsed/BNB 支出；零模拟 Gas 不等于实盘零成本。六小时正收益也只能是短窗模拟结果。

### 5.5 持久化与审计边界

无生产 DB/schema/索引/TTL 或新主账。虚拟现金、预占、净份额、累计损益和 halt 属本次 Broker 内存；只保存一次性公开启动/结束证据、脱敏事件和结果用于核验，不能由日志自动恢复交易。

原全量验收报告 `data/reports/2026-11-16-btc5m-controlled-paper/validation.md`、后续 R2/R3 及其 `evidence/` 均保留原字节。本 V1.1 单键来源增量仅由独立 Validate 产出 `data/reports/2026-11-16-btc5m-market-key-bootstrap/validation.md`，必要原始证据放同主题 `evidence/`；Implement 不另写重复结果报告。实际 paper 仍按原启动主题归档，不受本增量影响。任务/进度/交接只在 Kanban，无新建 data/tasks、任务镜像或重复状态报告。证据 exclusive-create，不覆盖旧历史，无自动删除/TTL/迁移/备份；data 被 Git 忽略，不等于远程备份。秘密、JWT、签名材料和含密钥 URL 不落盘，首次输出前脱敏。现有 keyring 私钥条目不迁移/改属性，API key 保持既有来源。

## 6. 验收与阶段分离

原 T1 成功标准为两独立文件及公式/边界检查；当前修订成功标准为 RFC V1.1、SPEC V1.1、Design V1.3 三独立文件一致、单键例外与旧禁读条款无冲突、定向 diff/空白及 SHA 检查后交主控 Gate。本卡不执行实现回归；后续必须真实 run 验证读取/首次 write/child 顺序、回退成功、合法原环境零文件读取、全部拒绝及无秘密落盘（SPEC §5 B-001–B-006），不能以 R3 PASS 代替本增量验收。

原全量流程由 Design 固定接缝/allowlist/G3/回滚与测试，再经 Implement 和独立 Validate 覆盖原 SPEC 矩阵；本次复用仍适用证据，仅补受影响增量。工程 PASS 不证明真实账户资金动作、SDK 网络可用性或 6h 运行结果。不重复创建文档链或重跑现行观察；后续 unsigned 启动及真实 signed/资金执行仍按各自明确授权边界处理。

## 7. 风险、替代与未完成事项

- 旧 paper 净亏损、94 日研究无盘口 PnL：本轮不以盈利为工程通过条件，也不保证产生信号或交易。
- 2 USDT 名义兼容既有官方 buy≥1 USDT 规则，但当前市场 tick/精度/深度/费率仍须逐笔检查；不兼容拒绝，不自动提高上限或放宽 min_edge。
- 数据延迟/缺失、撤单失败、未结算或净值跳变可越过阈值；保留占用与缺证据，不用期末回升擦除 halt。
- unsigned 模拟现金在官方结果读到时即回收，实盘还须赎回和到账，周转能力不可外推。
- 同 UID/管理员/进程内存、配置与二进制并发替换的既有威胁边界保留，不承诺物理清零或强隔离；不是本次新增平台的理由。
- 依赖升级、真实 keyring/认证/签名/订单/授权/赎回/私有探针、服务调度与生产写入均未授权给工程 worker；runtime 拒绝立即停该动作，不换工具/路径绕行。

## 8. 开放问题与版本

开放业务契约项：0。具体 Rust 类型/CLI 拼写、helper 拆分、测试名称和回收细节由 Design 在 SPEC 已冻结行为内决定，不将资金、费用、重启或授权语义下放实现者。真实资金/订单/收益未闭环是明确未执行范围，不是已解决事实。

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0 | 2026-11-16 | 基于已验 07-001/002/003，冻结一次受控 paper 与必要安全接线的增量范围 |
| V1.1 | 2026-11-16 | 仅允许后续 unsigned-paper 缺源时从固定 skills/.env 读取精确单键；冻结环境优先、脱敏拒绝与新回归，其余行为及当前运行不变 |
