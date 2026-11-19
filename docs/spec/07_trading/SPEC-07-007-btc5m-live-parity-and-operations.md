# SPEC-07-007: BTC5m live 一致性、实际账务与值守运行契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | Draft V1.0；T1 候选，待主控文档 Gate；非实现/独立 Validate/真实运行 PASS |
| 作者 | YQuant Principal / yquantprincipal |
| 创建 / 更新 | 2026-11-19 / 2026-11-19，Asia/Shanghai（UTC+08:00） |
| 来源 RFC | [RFC-07-007](../../rfc/07_trading/RFC-07-007-btc5m-live-parity-and-operations.md) V1.0 |
| 工作区 / 来源任务 | /home/pascal/workspace/yquant-investment；t_b946f2c3 |
| 后续 Design | docs/design/07_trading/DESIGN-07-007-btc5m-live-parity-and-operations.md；T2 另行产出，本卡不创建 |
| 执行 / 验收 | Principal Design；Developer Implement；Reviewer 独立 Validate；主控 Gate/Closeout |

## 1. 需求摘要

显式 07-007 候选使 signed live 与 unsigned paper 共用既有 phase1_net_shares DecisionCore，原 Broker/venue 负责真实执行，不给 live 创建 PaperCash。输出新分版、严格白名单的 live 决策/订单/实际净额/风险/结束证据；旧 signed-null 输出不能证明本轮能力。有人策略 pilot 和无人单次运行共享经济/执行不变量，无人额外覆盖单实例、异常停手和拒绝冷启动。跨重启自动恢复及自动连续复投不在本轮；首次需要人工赎回时停新增，资金读回由原 SDK/人工承接。

## 2. 范围与增量优先级

### 2.1 三类矩阵和事实来源

[RFC §2](../../rfc/07_trading/RFC-07-007-btc5m-live-parity-and-operations.md)的“已验离线基线 / 真实工程缺口 / 生产授权缺口”三矩阵为本 SPEC 的分类依据。BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`；下列路径相对 BOT。

| 当前接缝 | 已有、不得重建 | 本轮必要差量 |
|---|---|---|
| src/bot/arbitrage.rs:69–73；arbitrage/phase1.rs | 唯一 DecisionCore、source/clock/EV/候选 | 显式策略契约与执行模式解耦，沿原 RoundTaker 接 live |
| src/bot/runtime/paper.rs:641–673,880–952 | phase1 时钟/事件/候选当前依赖 paper | 分离必要运行元数据，原 Broker live 薄适配；不是把 paper 撮合迁给 live |
| src/bot/runtime.rs:624–766；runtime/live.rs | attempts、tombstone、实际执行应用及 unknown 闭锁 | final-send guard、真实状态投影及窗口/停新增集成 |
| src/service/venue.rs；predict_fun/fills.rs:95–208 | snapshot/原子量、签名hash、单次POST/账户/权限/签名检查 | 现有适配器最后可能发送前调用同候选检查和耐久证据屏障；保持真实回执语义 |
| tools/predictfun/btc5m_control.py:957–1064,1565–1703 | 固定child、环境、监督、首次过滤、signed接线 | 显式live协议/值守选择、关键事实确认、互斥/冷启动拒绝与审计消费 |
| tools/predictfun/local_signer.py、cli.py、sdk_ops.py | 已有 keyring / lazy FD / 主网API / 资金工具 | 默认不改，只复用；仅直接必要兼容才可在T2逐文件证明 |

不是逐文件实现授权。T2 须把保留项与真实差量分开，给精确新增/修改路径、类型/字段映射、G3、动态加载隔离、离线命令。源码单位/行为与旧文档不一致时以当前源码和仍适用的独立证据为先，不重复修旧 unknown→planned finding。

### 2.2 有限替代、兼容与禁止

仅显式 07-007 候选替代旧 07-005 的 signed 不启 phase1、07-004/005 的 signed final-only/null、07-002/004 的无跨进程保护边界；只扩到本契约的单实例和拒绝冷启动，不冒称自动恢复。旧历史语义/FAIL 保留，不批量回写旧文档/事件。

默认普通 paper/live、其他策略/venue、replay/1、history、07-006 unsigned-only observer 和已运行 paper 不变；旧 v1/v2 仍只读按原版本解释。保留所有原安全 signer、RPC/身份/账户/预算/分页/去重保护，不因 phase1 标签或人在场绕过。混合模型/动量/OBI/alpha优化、主动退出策略、第二 core/Broker/OMS/runner、自动重签/补单/解锁、跨主机互斥、生产 DB/schema/依赖/服务/调度/profile/权限/commit/push 均排除。

本卡仅新增 RFC/SPEC，静态阅读和检查，不写 Design/业务代码/配置/数据库，不启动任何业务。本轮后续工程也只离线 synthetic/fake；真实认证、私有API/链上刷新、真实签名/订单/撤单/资金、外部告警及上线均另授权。

## 3. 功能规格与授权矩阵

| 编号 | 必须行为 | 失败边界 |
|---|---|---|
| F-001 | 显式 contract=phase1_net_shares；execution 与 operations_mode 独立 | 缺 opt-in 保持旧行为；不得旧 signed-null 冒新候选 |
| F-002 | 同 core 候选经济与提交前重验 | 裸 phase1 BUY、无上下文、过期/换源/身份变更不发送 |
| F-003 | 原实际 snapshot 记账、未知保留风险 | 不能拿计划量/模型费/订单status充实际净额 |
| F-004 | 严格 live 事件与真实消费者审计 | 坏事件首次落盘前拒绝；重要输出失败停新增、不假绿 |
| F-005 | 固定风险窗口、现金/预占/浮亏/费用分责 | 换run/换日/重启不清loss；未知不零填 |
| F-006 | 单host同账户单实例、拒绝冷启动 | 抢锁/屏障耐久失败不取signer、不启child；新run_id不能绕过 |
| F-007 | 故障停手与人工接管 | 不自动重启/重签/解锁/改salt，告警失败仍停手 |
| F-008 | MANUAL_PAUSE 资金回收 | 账面settled不回现金；WAIT_CASH停新增，无自动approve/redeem |

| 动作 / 验收层 | 当前T1 | 后续离线Implement/Validate | 以后有人值守真实动作 | 以后无人值守真实动作 |
|---|---|---|---|---|
| 文档、静态检查 | 仅本两文件 | 按阶段allowlist | 不自动需要改文档 | 不自动需要改文档 |
| 原消费者fake、合成子进程 | 不执行 | 允许，凭据/业务网络调用即失败 | 不是实际结果 | 不是实际结果 |
| 真实auth/账户/余额/RPC查询 | 禁止 | 禁止 | 明确目标/时间的只读授权后 | 同左，另含完整就绪/接管核对 |
| 签名、下单、撤单、卖出、approve、redeem | 禁止 | 禁止 | 各动作/额度/次数/期限/退出明确，外部执行及风控确认 | 同左；人在场通过不自动授予无人模式 |
| 自动重启/补单/新salt/清latch | 禁止 | 仅负例证明禁止 | 禁止 | 禁止 |
| 外部告警、生产Mongo/schema、长期调度 | 禁止 | 禁止，只fake接收者/存储 | 另具体授权 | 另具体授权；不能把本地事件说成已通知 |

## 4. 行为、数据与接口契约

以下是新增逻辑合同，不声称源码已有同名类型/API。T2 只决定内部签名、wire同义分组、CLI拼写和文件落点，不重选经济、恢复或授权语义。

### 4.1 模式、准入与风险窗口身份

- execution_mode=UNSIGNED_PAPER / SIGNED_LIVE；operations_mode=SUPERVISED / UNATTENDED。新live仍由原 signed-future-live 固定入口显式选择新契约，不另建runner；不能通过旧config或enable_trading隐式升级。
- 新候选 started 必须绑定：schema_version、strategy_contract、operations_mode、run_id、risk_window_id、固定 account_identity、候选binary/源文件/公开配置SHA、授权引用 authorization_ref、started_at/deadline_at、recovery_policy=COLD_START_REFUSE、cash_recovery_policy=MANUAL_PAUSE。authorization_ref是公开工程关联，不是凭据或自动审批token。
- account_identity 仅 {venue:PREDICT_FUN,chain_id:56,account_mode:predict-account,trading_address,signer_address}，继续07-003固定绑定，不能用signer当持仓账户。地址先严格0x+40hex，再按原绑定比较。run_id沿原受控格式；risk_window_id/authorization_ref沿同受控公开ID语法，不接受任意文本/路径。
- window覆盖一次已批准实验而非一进程/自然日；100 USDT是分配预算C0，不是凭空写入真实账户。startup完整官方对账及原预算确认通过，证实可用资金后才可在限额内活动。当前无真实预算授权，不给本轮填未来金额/期限/Gas批准。
- 准入先公开模式/版本/固定参数/期限/身份 → 单实例锁与持久拒绝屏障 → 原交易秘密来源/keyring → 单一child → 原完整账户/权限/预算核对 → READY。本文0secret计数指交易私钥/行情API/JWT读取，Mongo自身连接凭据只可由以后获批的明确存储绑定取得，不传child，不全量load_dotenv；测试注入fake存储且两类真实凭据读取都为0。失败不fallback、不自动sign-in/check-venue/approve；无有效监督控制通道的受控live拒绝。
- 当前paper及旧signed入口的原期限不能被新选项改变。新真实期限由以后授权固定，双UTC/包含暂停的经过时间任一先到即停；工程fixture可推进fake clock，无真实长跑。

### 4.2 phase1 live 经济与最终发送约束

1. 净份额模型/公式完全继承07-005 §4.1：h(p)=bps/10000×min(p,1−p)，q_net=q×(1−h(p)/p)，cost=q×p，EV=q_net×fair−cost，edge=EV/q（USDT/gross share），min_edge=0.03。BUY不再把份额费等值额扣现金；实际费用另来自官方事实，不替换成模型费。Down镜像、同edge选Down、q向下取整、模型/EWMA/20returns/300秒gap/5与10秒时效/30秒边界等不变。
2. common允许输入子域的paper/live同core输出同p_up/候选/净EV/原因；paper可Coinbase降级，signed保留Binance-only。signed遇Coinbase给SOURCE_NOT_ALLOWED，未签名/未POST；不伪称通过相同经济判断就获得相同执行授权。
3. phase1裸BUY缺candidate即CONTEXT_MISSING。唯一候选冻结原07-005身份、revision/source/epoch/clock/fee、q/limit/两侧诊断。live保留EVALUATE与PRE_SUBMIT，额外FINAL_SEND在最后账户/盘口/权限/认证/签名等待及关键证据确认之后、第一次可能POST之前。每次重新取合法CheckTime，以同core重新计算剩余期限/fair/edge并检查输入/期限/stop/loss/data/account gate。不能持Broker锁跨网络await；预占与最终本地check/send许可状态变更须在原原子保护下序列化。
4. 原venue获取的最终book、fee、market/route和签名maker/taker约束必须可与候选核对；不同输入使旧candidate INPUT_CHANGED终结，不能悄悄沿旧fair签新量。若重考虑，只能在尚未可能提交、仍未入场且授权有效时，由原core新attempt重新评估；不是网络重试补单。signed金额必须遵守原限价、净EV及最坏现金/最低净到账约束；不能凭API的isMinAmountOut/slippageBps名字忽略实际已签约束。不能证明则SIGNED_BOUND_UNPROVEN，0POST。
5. 顺序：候选检查 → 原原子预占 → 原签名及身份校验 → 同hash的order证据经supervisor严格校验且确认耐久 → FINAL_SEND → 原单次POST。关键证据确认失败不发送；确认等待也不能延长freshness/期限。最后检查和交给POST之间不得另做阻塞证据写入/账户请求/等待；必要控制通道由T2复用原管道，不新建服务。终止发生在发送许可前必须0POST，已可能发送的不能靠取消future假装未提交。
6. live无paper PRE_APPLY“拒绝本地模拟成交”语义。POST后实际晚到/部分/负EV/过30秒/到期成交一律按同hash事实入账，即使已经停新增。能取消仅按预批准原cancel流程；不得回滚真实成交取绿灯。
7. 原core只有确认正净fill才confirm_fill；费用/net未知时不捏造净量。原round/intent tombstone从可能发送持续阻止同轮补单；确认正gross但net未知也须账户闭锁，不能因core尚未entered自动再试。部分终态也不补余量。同candidate至多一次初始提交，未知时同hash查询不签名、不广播重发，401/timeout不自动重POST。

### 4.3 实际执行状态：四个维度独立

沿原AttemptPhase/Submission/Quantity/Closure与ExecutionSnapshot，不新造替代OMS。公开投影使用下列固定枚举，原映射由T2按源码逐字段绑定。

| 维度 | 值 / 转移 | 允许与禁止 |
|---|---|---|
| attempt_phase | Prepared → MayHaveSubmitted → Submitted / Closed；Unknown可停在MayHaveSubmitted | hash在可能发送前保留；明确未发才可回收；进程死不当Closed |
| submission | NotSubmitted / RejectedFinal / Accepted / Unknown | HTTP201只是Accepted；异常可能发送即Unknown，不重签 |
| quantity_class | UNKNOWN / ZERO / PARTIAL / FULL | 依据权威实际gross而非净到账或FILLED状态；MARKET部分FILLED仍PARTIAL |
| closure | OPEN / REMOVING / UNPROVEN / FINAL | removalLockedUntil未到、remove accepted、网络错、空列表均不证明FINAL |
| accounting_status | COMPLETE / INCOMPLETE / CONFLICT | quantity已知可核算不全；已知费用0须明确事实；每字段coverage保存 |
| payout_status | UNRESOLVED / CONFIRMED / CONFLICT / CASH_PENDING / CASH_CONFIRMED | 官方结果、链成交settled和赎回到账分别判断；DRAW按官方0.5 |

- 实际Q/C/fees/net依原snapshot完整字段或明确官方映射，按官方ID或完整单调累计coverage去重。generation旧值不回退，矛盾累计/费用修订不自动冲销；partial补齐时只记新覆盖，不重加份额。
- COMPLETE且FINAL时才释放未成交余量；单量全额但费用未知仍占用/停新增。数量完整零且权威不可成交才释放，VWAP=NOT_APPLICABLE，不是0。
- matched、链settled与cash_received各自给可核事实，order_id/signed_hash/tx_hash不能互换。链settled的交易hash不证明用户已redeem。
- 只读查询可有原有界重读/分页；不得新加写操作自动重试。rest受控仍拒绝；意外/继承挂单或撤单竞争保留全部风险，不因本策略不maker就忽略它们。

### 4.4 风险、单位、费用和可用现金

原子量均为十进制ASCII字符串：无符号`0|[1-9][0-9]{0,77}`且≤U256最大值；带符号USDT损益为可选单负号的同义规范整数，禁止−0。ID/hash先格式再比较：market/token沿1..78位十进制ID；signed_hash/tx_hash为0x+64hex。venue_order_id是原API返回的String，不是market/token十进制ID；新公开order-ref类型限定`[A-Za-z0-9_-]{1,128}`，按原字节保留、不得截断/重编码/替换为hash，越界则FACT_INCOMPLETE并保留原signed_hash查询。不用自由响应文本。时间RFC3339显式UTC/offset、毫秒精度，elapsed_ms为拒bool的非负整数；重启不混用经过时钟原点。

- 金额/份额保留asset、decimals与atoms。当前支持部署转换沿原1e18路径，仍须核实metadata一致；缺decimals拒绝，不猜6/18。USDT、BNB、shares不可混加；VWAP/模型价是USDT/gross share，不是持仓成本单价。gross与net原子量严格区分，展示小数不能反馈预算判断。
- 成交实际现金出入用net_cash，份额用net_inventory；额外USDT费只在尚未净额时纳入，份额fee不再从现金/PnL重复扣。累计费是展示项，不从已经净额的NAV再减一次。不同fee币种不支持则INCOMPLETE，不取0。
- 风险窗口C0固定100 USDT；K为该窗口尚未回收成本（含到期未兑付），P为仍可能增加的最坏现金预占。单笔最坏现金（含可能额外现金费）1≤w≤2、市场K_m+P_m+w≤2、K+P+w≤10，且足够真实/预算可用现金。原q向下取整后不满足最低金额就拒绝；不提高2、不改fee公式/参数、不自动缩单凑成功。
- 预占占用为同单已确认成本+尚未闭合余量，不能把整笔R0和确认成本双算，也不能低于max(R0,已知实际更高风险)。未确认风险不默认为0；实际超预占保留更高实绩并halt，不裁剪。P是B受限部分，不能再从NAV重复扣。
- B为窗口真实已到账现金的预算余额，从100开始，只按归属已核的实际现金支出/收入变动；真实总账户余额另外读回，不代替B。可用额≤B−P且≤完整账户读回的可支用USDT减未闭合预占；不把未兑付余额当现金。无法解释的入金/提款/其他客户端交易导致RECONCILIATION_REQUIRED，不自动改C0。
- V为净持仓的有效原mark价值与已确认待兑付claim价值之和，同一资产不可同时作share/claim双计。U=V−K；R为已实现净收益；完整、无外部流的窗口满足B=100+R−K、NAV=B+V、net_pnl=R+U=NAV−100。官方已确认零兑付可移除其经济成本并实现损失，链上残余无价值份额仍独立披露；非零claim在现金/烧份额读回前保留成本，不以预计赎回实现现金收益。真实读不全时相关派生值null+原因，不能强套恒等式反推未知余额。
- mark沿原mid与原有效性；不是模型fair/保证清仓价值。浮亏必须计入20阈值。为与原子现金对账，live估值换算按原有效mark保守向下到USDT原子量，注明VALUATION而非链上cash事实；不修改paper模型/mark。loss判断原子量≤−20 USDT含等号，阈值无epsilon；未获得可用mark/完整风险时DATA_UNAVAILABLE停新增，不能用成本/旧mark证明安全。
- loss_latched一旦真，在同窗口永久真；下一tick、结算回升、换日、换run/重启/改配置不得清除。同tick成交/费用/估值/结算后更新以及每个FINAL_SEND前都检查；native费用BNB单列，不把BNB加USDT。gas_status=NOT_MEASURED / KNOWN / UNAVAILABLE，NOT_MEASURED不等于0；KNOWN需同payer/tx/读回依据，归属不明不得乱扣。本方案20只为USDT累计净损失停新增，不包括无转换依据的BNB；真实授权须另给Gas支付者、BNB可用/消费预算及停止条件，缺则不启动。无新增模型汇率、无保证总损失/回撤≤20声明。

### 4.5 新live事件、严格白名单与真实消费

新schema_version固定`btc5m-controlled-live.v1`；只在显式07-007 signed候选接受。原BTC5M_EVENT framing/64KiB行界/每数组1000界保留，不能用新schema放宽原v1/v2；每次版本按started绑定，禁止混流。event_seq从1严格递增，无重复倒序/漏号；bad line不先write后清洗。

新envelope仅以下全部必填键，nullable明确存在；payload按kind精确匹配下面字段。不存在自由detail/raw/body/error字典。所有对象递归拒未知键、重复JSON键、NaN/Infinity/bool冒数、非法null/enum/身份/关联。验证成功才提交关系索引/写盘，写盘失败不重试可能资金副作用。

| envelope字段 | 类型 / 可空 | 含义 |
|---|---|---|
| schema_version | 固定string | btc5m-controlled-live.v1 |
| run_id | 原受控ID，非null | started匹配 |
| risk_window_id | 受控ID，非null | 窗口不会因run变化重置 |
| event_seq | positive integer，非null | 本run顺序 |
| event_kind | enum，非null | decision / reservation / order / execution / reconciliation / loss_latch / stop / recovery / payout / final |
| event_time | timestamp，非null | 产生事件时点，不伪装报价/官方事实时间 |
| market_id | id/null | 关联市场时必填，否则null |
| token | id/null | 关联token时必填，否则null |
| accounting | accounting对象，非null | 原Broker风险投影，字段如下；合法未知保留null/status |
| payload | kind严格对象，非null | 下表的字段，不能添加未列内容 |

accounting每个键必有：cash、available、reserved、cost、realized、unrealized、nav、net_pnl为对应USDT原子量字符串/null（后三者及realized允许符号）；loss_latched为bool；status=COMPLETE/INCOMPLETE/CONFLICT；reason为§4.9枚举；mark_time为timestamp/null；pending_claim_value为USDT atoms/null；gas_status沿§4.4；gas_paid_atoms为BNB atoms/null。原始代币shares在execution/positions里，不跨token求和称财富。COMPLETE须关键现金/预占/成本/R/U/NAV均可知且恒等式成立；未知snapshot不能使旧真实K/P消失，reserved至少保留已有保守值。gas未测可不影响USDT恒等式，但不能宣称全币种全成本收益已知。

| kind | payload全部字段 / 类型 | 约束 |
|---|---|---|
| decision | decision:07-005 §4.5同义完整对象 | phase限定EVALUATE/PRE_SUBMIT/FINAL_SEND；strategy_contract固定；FINAL_SEND不叫模拟PRE_APPLY；其他null/clock/两侧诊断沿原合同 |
| reservation | candidate_id:id、attempt_id:id、action:RESERVE/RELEASE、worst_cash_atoms:atoms、remaining_atoms:atoms、reason:enum | 同候选/同attempt；RELEASE仅权威闭合/明确未提交；数值是现金预占不是股份 |
| order | candidate_id:id、attempt_id:id、signed_hash:hash/null、venue_order_id:order-ref/null、attempt_phase:enum、submission:enum、request_gross_atoms:atoms、max_cash_atoms:atoms、min_net_shares_atoms:atoms/null、expires_at:time/null、removal_locked_until:time/null、reason:enum | 签名后hash非空；初始Prepared可无hash；首次可能BUY POST前完整signed bound/hash耐久、min_net_shares非null且>0；lock未知不能当已到期 |
| execution | attempt_id:id、signed_hash:hash、venue_order_id:order-ref/null、generation:positive integer、observed_at:time、pages_complete:bool、quantity_class:enum、gross_q_atoms:atoms/null、accounting_gross_q_atoms:atoms/null、closure:enum、final_gross_q_atoms:atoms/null、facts:对象、delta:对象、tx_hash:hash/null、settlement_status:UNVERIFIED/MATCHED/CHAIN_SETTLED/CONFLICT、settlement_checked_at:time/null、reason:enum | facts/coverage及delta见下文；PARTIAL可FINAL；不能用FILLED补请求量；有tx_hash不等于CHAIN_SETTLED，须同交易receipt及同目标状态证实，否则保留UNVERIFIED/MATCHED，不能暗中增加未授权RPC |
| reconciliation | scope:STARTUP/RUNTIME/HANDOFF、checked_at:time、complete:bool、collateral_atoms:atoms/null、gas_balance_atoms:atoms/null、positions:数组、open_hashes:hash数组、foreign_risk:bool、reason:enum | positions每项仅{market_id:id,token:id,net_shares_atoms:atoms,cost_atoms:atoms/null}；只输出窗口关联最小事实，陌生风险标志而非任意隐私全表；读全成功才complete |
| loss_latch | latched:bool、trigger_net_pnl_atoms:signed atoms/null、reason:enum | latched必须true，不能输出解锁；未知损益停新增不伪造触阈值 |
| stop | stop_new_risk:bool、reason:enum、takeover_required:bool、alert_status:LOCAL_RECORDED/DELIVERED/UNAVAILABLE | stop_new_risk必须true；DELIVERED只用于以后已授权接收者确认，当前fake不得冒外部送达 |
| recovery | policy:COLD_START_REFUSE、state:ARMED/RECONCILIATION_REQUIRED/HANDOFF、reason:enum | 不承载可交易余额/自动reset；与持久屏障关联 |
| payout | status:enum、payout_yes:number/null、position_net_atoms:atoms、claim_value_atoms:atoms/null、cash_received_atoms:atoms/null、tx_hash:hash/null、observed_at:time、reason:enum | payout只取合法官方身份/结果；CASH_CONFIRMED须同目标份额/现金读回；未知保持null |
| final | run_status:COMPLETED/STOPPED/INCOMPLETE、stop_reason:enum、execution_complete:bool、cash_complete:bool、audit_complete:bool、takeover_required:bool、unresolved:数组、positions:数组 | unresolved每项仅{attempt_id:id,signed_hash:hash/null,closure:enum,reserved_atoms:atoms,reason:enum}；positions复用reconciliation结构；完成运行≠无持仓，pending不得假现金闭合 |

execution.facts恰含gross_cash、collateral_fee、share_fee、net_cash、net_inventory、vwap六键。每值为严格{status:KNOWN/UNKNOWN/NOT_APPLICABLE,atoms:atoms/null,coverage_gross_atoms:atoms/null,reason:enum}；gross_cash/collateral_fee/net_cash单位USDT，share_fee/net_inventory单位该token份额，vwap沿原适配器固定点单位。status=KNOWN必须atoms/coverage非null，UNKNOWN必须atoms=null；NOT_APPLICABLE仅确认零成交的vwap，其atoms=null。coverage来自原snapshot字段覆盖，不从新gross倒推；不足覆盖不得称COMPLETE。

execution.delta恰含gross_q_atoms、gross_cash_atoms、collateral_fee_atoms、share_fee_atoms、net_cash_atoms、net_inventory_atoms，值为本次唯一原Broker实际应用非负增量atoms；核算未全而未应用的字段为null（不是伪已应用0），重复已知快照确认为无新应用才可0。无法从现存状态直接获得的delta须T2给最小类型投影，不在Python重建可交易账。实际币种/decimals由started的asset_units声明，asset_units恰为{collateral_symbol:USDT,collateral_decimals:integer,share_decimals:integer,gas_symbol:BNB,gas_decimals:integer}；与原部署事实不一致启动拒绝。

supervisor关系规则：decision→candidate→reservation→signed order持久确认→FINAL_SEND→最多一次初始submit；一个candidate可有多代execution而非v2一个fill终态；同attempt identity/hash/account不可变，venue_order_id在首次获知后固定。execution累计/coverage矛盾拒绝，晚到真实事实不能因运行deadline过去被过滤掉。reader必须实际从校验后文件读取，逐事件核对actual增量、预占转换、风险和final，不以拼装JSON纯函数替代真实producer链。

正式final至少拆开运行状态、原生child/launcher退出、订单闭合、资金回收和审计完整性。exit0、无新单或收到final不自动PASS；missing final、未知hash/费用、未终结预占、强制清理、writer/reader关系失败必须INCOMPLETE或takeover，不能写completed资金闭环。待官方结果/赎回可正常停止观察，但cash_complete=false；不能把run_status=COMPLETED解释为账户清空。旧signed的LIVE_ACCOUNTING_UNAVAILABLE仍只读保留，不迁移为新COMPLETE。

### 4.6 有人值守/无人值守可用性与故障状态

运行安全状态：STARTING → READY → STOP_NEW_RISK → HANDOFF / ENDED；READY还可→WAIT_CASH→HANDOFF/ENDED。任何STOP_NEW_RISK或WAIT_CASH后本run不回READY；临时行情失败的恢复也不解已触发的停止/loss。首次STARTING的确定未发故障可以0订单退出，但不能自动重启一个新run。

| 条件 | 新增风险 | 允许行为 / 不代表什么 |
|---|---|---|
| READY且所有输入/账户/预算/监督/期限通过 | 可经同core候选初始发送 | 离线健康正路径必须能到原执行器，不全拒绝取PASS |
| keyring不可用/locked/需Prompt | 0child/0签名/0POST | 原固定失败，无Unlock/其他key/file fallback |
| 行情/账户/RPC失败、缺页、费用/mark未知 | 停新增，保存已知风险 | 原有界只读对账；不以空列表/零值恢复健康 |
| 提交不明/核算冲突/撤单锁/late fill | 停该资金账户全部新增 | 同hash查询、记实际增量、按既有许可取消；不补余量、不释放至零 |
| loss≤−20或deadline到/人工stop/父失联/控制通道故障 | 立即关闭下一发送许可 | 保留in-flight身份及占用；已有可能发送不冒称已撤销 |
| 关键证据/耐久/确认/协议校验失败 | 停新增，audit不完整 | 不回滚真实状态，不把事件故障降为可丢自由日志 |
| child异常/强制kill/宿主重启 | 无自动child复活；冷启动拒绝 | 屏障+缺结束标异常；锁随进程释放不清屏障 |
| 首个正兑付claim待回收 | WAIT_CASH，0新增 | 原手工SDK/官网另授权后读回；不自动继续复投 |
| 告警不可用 | 停新增，takeover_required=true | 本地固定code/退出/屏障仍可见；不假称已有人收到 |

父死亡/控制EOF时，child须独立停新增，不等下一完整网络tick后还发新单；每次可能POST前重检。停止有界沿原30秒正常清理、超时强制并如实未决；原600秒只读尾查上界不能变成自动live赎回授权，超界保留pending，不能无限等健康。MAX_FAILED_TICKS既有撤报价保留，但它不是允许失败期间继续新增的宽限。T2必须按原停止管道给出精确EOF/超时检测与测试点，不凭空新增心跳数值或无限恢复loop。

SUPERVISED工程首单可一笔加预批准退出，由人核官方回执/账单；不要求先自动赎回或无人全能力。SUPERVISED策略pilot必须本轮phase1和新live审计通过。UNATTENDED额外要求下面单实例/冷启动屏障/故障/接管/WAIT_CASH演练，能力定义为一次有限窗口内的自主健康交易，不是自动跨重启恢复或连续资金循环。未来真实无人验收还须明示告警接收者/响应安排和允许退出；本轮不发送外部消息。

### 4.7 单实例、持久屏障、冷启动与人工恢复

1. OS锁作用域固定(host,venue,chain,trading_address,account_mode)，覆盖全部受控signed run、不同run_id/risk_window_id及两种operations_mode；Mongo拒绝屏障的唯一主键不含host，其他host也不能凭新host绕过同账户已有屏障，但不因此宣称实现分布式自动恢复/完整外部客户端互斥。不能只按策略/runID锁；unsigned paper无wallet不抢live锁。仅保证合作消费者，真实账户须声明无其他host/客户端并行；不宣称恶意同UID隔离。
2. 在原launcher取secret/启动child前取得OS排他锁并持有至child确证退出/风险交接；锁失败即ALREADY_RUNNING。父死但child还活时，不得因仅父FD解锁放行另一个child；持久屏障仍拒绝第二次启动。T2用本机已有OS/标准库能力，禁止新服务/包。
3. 同作用域拒绝屏障默认Mongo逻辑LiveRunGuard，使用固定scope作唯一主键，以一次insert创建ARMED、取得持久写确认并同目标读回后才取signer/启child。依赖复用项目venv既有pymongo，不在BOT专用venv安装包；原launcher同进程lazy调用最小存储接缝，不新增worker/服务。单文档足以表示拒绝屏障，不需要多集合恢复事务。主键不得包含run_id/window以绕过唯一性；必须沿Mongo内建_id唯一约束，不能以先find再普通upsert实现互斥。
4. 屏障写入要求writeConcern={w:majority,j:true}且同primary的majority读回精确匹配scope/版本/原始内容；未确认、超时或读取不全均不启child，不盲重insert。实际既有Mongo部署不能满足时阻断激活，不自行扩服务/改配置；当前只fake验证调用/失败顺序。缺明确批准的连接/库/集合绑定、driver/存储不可用、冲突/损坏/未知版本、写或耐久不明全拒绝，无自动删文档重建、文件/易失内存fallback；不导入会load_dotenv的MongoWriter作为资金存储。
5. 屏障一旦ARMED，正常/异常结束、OS重启、锁释放、日志显示零仓都不自动撤销。另一个新run遇屏障直接RECONCILIATION_REQUIRED，0secret/0child/0POST，不用当前余额/参数或普通budget-confirmation单独覆盖。
6. 人工接管只能在明确授权下，由原账户/订单/资金消费者核对窗口内全部attempt/hash、权威终态及late fill、完整现金/净份额/费用、待兑付、R/U/loss和Gas；丢失hash必须完整官方历史核对，不能“查不到即没下过”。保留原窗口和latch证据，无法解释则继续阻断。
7. 本轮没有自动resume/reset/轮转命令；屏障的人工轮转/新窗口开启是后续具体授权操作，旧屏障原始内容留档，不提供一个bool清loss入口。同窗口若loss已触发，不再启动风险新增；以后新实验须主控明示承接累计风险和新授权，不把换窗口当技术性续命。
8. 独立离线验收要证明：首次无屏障、资金/授权完整的fake可READY并实际触发原fake执行器；随后异常的冷启动必拒；同一健康进程内至少两不同轮合法候选可依次执行。不能只测试全拒绝或把未生产部署的屏障当线上已有。

### 4.8 结算、人工回收与final

官方结果仍须同market/token/BTCUSDT/300秒、固定起止价与非争议结果一致；模型/本地spot不结算。DRAW官方0.5只形成相应claim，不保证可卖价或USDT已到账。实际库存烧毁与同笔USDT回读须沿原SDK target/route/receipt，tx hash或success单独不够。

默认MANUAL_PAUSE：首个需要回收的官方正claim即WAIT_CASH并停止新风险，列claim/净份额/成本/未决。可以在已有持仓上完成有界对账，不自动approve/redeem/merge/卖出。人工以后获得具体目标许可后调用原SDK或官网，读回失败保留同hash并停，不重签/重发。即使后来读到账，本run也不自动复READY；下一启动服从冷启动人工核对。若只有官方零兑付，按§4.4记经济损失和链上剩余份额，不造赎回现金。

自动连续运行当前NOT_SUPPORTED；资金回收责任明确由指定接管人承接，不能用虚拟paper回款或“人工以后会看”证明自动周转。资金工具既有能力不重建，未来如另批自动回收须明确有限route/target、Gas/失败/原消费者验收，不能隐式approve所有路线。

### 4.9 错误、重试与失败关闭

新协议reason固定集合：NONE、CONTEXT_MISSING、SOURCE_NOT_ALLOWED、INPUT_CHANGED、SIGNED_BOUND_UNPROVEN、ALREADY_RUNNING、RECOVERY_GUARD_UNAVAILABLE、RECONCILIATION_REQUIRED、SUBMISSION_UNKNOWN、FACT_INCOMPLETE、FACT_CONFLICT、ACCOUNT_MISMATCH、READ_UNAVAILABLE、DATA_UNAVAILABLE、OUTPUT_INVALID、AUDIT_UNAVAILABLE、KEYRING_UNAVAILABLE、LOSS_LATCH、DEADLINE、PARENT_LOST、CONTROL_CHANNEL、MANUAL_STOP、PROCESS_FAILED、CASH_PENDING、CASH_READBACK_UNAVAILABLE、GAS_UNAVAILABLE、GAS_BUDGET、NOT_APPLICABLE。decision.reason保留07-005完整原枚举，不混成此reason；原Broker正常资金/深度拒绝沿diagnostic_reason=BROKER_BLOCKED及其已冻结枚举，T2做显式穷举映射，不放开任意error字符串。

公开参数/身份/依赖缺失在可能发送前拒绝；命令非零，只有明确未提交才可报告NO_SIDE_EFFECT。签名/POST/撤单/赎回可能发生后，不报“绝未执行”，保留关联和未知。查询重读复用原有界政策；写动作只有一次初始尝试，不自动重签、同hash广播重发、新salt补余量或清loss。stdout/stderr/异常仅稳定code/step/reason及允许公开身份，不传raw异常、URL、HTTP body、JWT/API/signature/环境/秘密摘要。

## 4.bis 持久化与兼容契约

默认业务恢复存储方向Mongo；已核项目venv有pymongo 4.17.0/eth-account 0.14.0/jeepney 0.9.0，BOT专用venv无pymongo；不能直接套用MongoWriter/UD缓存的理由见RFC §4。当前选择Mongo单文档拒绝屏障+COLD_START_REFUSE，不是自动恢复/SQLite或第二可交易账本。T2冻结原BOT内的精确存储接缝、逻辑字段映射、OS锁路径和项目解释器兼容；实际部署绑定写成明确待批准的database/collection，不假称已存在，不自动创建生产集合/索引，不在工程测试连接生产Mongo。

| 对象 | 单字段 / 规则 | 类型 / 必填 | 来源 / 生命周期 / 隐私 |
|---|---|---|---|
| Mongo逻辑LiveRunGuard | _id | scope的规范唯一键，是 | venue/chain/trading_address/account_mode；不得含run/window/host以规避同账户唯一；Mongo内建唯一索引，不新建索引；L1 |
| 同上 | schema_version | 固定btc5m-live-guard/1，是 | 创建后保留，无TTL/自动删除；L1 |
| 同上 | scope | account_identity + 初始host公开受控标识，是 | 固定账户为唯一主键来源，host仅原始归属；不可用户随意换存储绑定；L1 |
| 同上 | risk_window_id | 受控ID，是 | 初次窗口引用；后续窗口遇原屏障仍拒绝；L1 |
| 同上 | run_id | 受控ID，是 | 初次启动关联，不作为锁作用域；L1 |
| 同上 | state | 固定ARMED，是 | 不靠退出写CLEAN自动解锁；L1 |
| 同上 | armed_at | UTC timestamp，是 | 在secret/child前实际生成；L1 |
| 同上 | authorization_ref | 受控ID，是 | 非审批token；L1 |
| 同上 | candidate_digest | 64hex SHA，是 | 仅公开binary/源代码/公共配置身份，不含秘密摘要；L1 |
| 同上 | durability | majority+j写确认及primary majority读回 | 行为要求 | 不用文档里的true自证耐久；写超时不重insert，存储异常不取signer/启child |
| OS锁 | 唯一作用域/持有 | 非持久金融字段 | 单host合作消费者互斥；进程释放不删除屏障 |
| 新started.json | schema_version | 固定live版本，是 | exclusive-create新run；L1 |
| 同上 | strategy_contract | 固定phase1_net_shares，是 | 无默认升级；L1 |
| 同上 | operations_mode | SUPERVISED/UNATTENDED，是 | 绑定本次授权；L1 |
| 同上 | risk_window_id | 受控ID，是 | 不按run/日期重置；L1 |
| 同上 | account_identity | §4.1严格对象，是 | 固定身份；L1 |
| 同上 | authorization_ref | 受控ID，是 | 非秘密；L1 |
| 同上 | recovery_policy | COLD_START_REFUSE，是 | 不能advertise自动恢复；L1 |
| 同上 | cash_recovery_policy | MANUAL_PAUSE，是 | 明示无自动连续复投；L1 |
| 同上 | asset_units | §4.5严格对象，是 | 来源原部署事实；L1 |
| 同上 | run_id | 受控ID，是 | 原格式；L1 |
| 同上 | started_at | UTC timestamp，是 | 实际启动尝试起点；L1 |
| 同上 | deadline_at | UTC timestamp，是 | 未来授权固定值，等待不延长；L1 |
| 同上 | candidate_identity | 原公开文件/binary SHA对象，是 | 不复制环境/凭据；L1 |
| 同上 | public_config_identity | 原公开配置SHA及固定参数，是 | 100/2/2/10/20和原模型参数；L1 |
| 新events.jsonl | 每字段/关系 | §4.5逐字段，是 | 校验后追加，关键订单发送前耐久确认；L1，行情L0关联后按L1 |
| 新ended.json | schema_version | 与started一致，是 | 原生退出后独立创建，不覆盖；L1 |
| 同上 | run_id | 受控ID，是 | 与started一致；L1 |
| 同上 | exit_facts | 原launcher/child native exit、signal、forced_cleanup、stop_reason，是 | 不以外层exit0覆盖child失败；L1 |
| 同上 | final_event_seq | integer/null，是 | 真实已写final序号，缺为null；L1 |
| 同上 | final_accounting | §4.5 accounting/null，是 | 真实投影，不补造；L1 |
| 同上 | incomplete_reason | §4.9 reason/null，是 | 不完整必须非null；L1 |
| 同上 | execution_complete | bool，是 | 未决不得真；L1 |
| 同上 | cash_complete | bool，是 | pending claim不得真；L1 |
| 同上 | audit_complete | bool，是 | 坏/缺事件不得真；L1 |
| 同上 | takeover_required | bool，是 | 必需接管显式；L1 |

所有新证据文件保留原字节、屏障保留原始内容，无TTL/自动压缩/删除/迁移/覆写/上传，旧v1/v2只读不补字段。人工轮转屏障需另明确授权并留证据；本轮无生产DB DDL/DML/schema/索引和真实部署。秘密仅原keyring/内存/匿名FD，L3禁止入事件/屏障/报告；Mongo连接秘密不传child/事件，不记录RPC敏感URL/签名字节/API/JWT/完整账户原响应。OS/同UID/管理员、存储物理耐久/人为删除不是本方案可保证隔离；必要Mongo确认/本地审计文件耐久不满足即拒绝，不降级临时目录或其他数据库。

## 5. 可证伪验收矩阵

以下为未来Implement自测及独立Validate要求，本卡未运行业务测试。全部synthetic/fake clock/transport/隔离子进程；业务网络、生产keyring/.env/真实signer/DB调用即失败。不是要求先真实成交才能离线PASS。

| 编号 | 正例 / 必需路径 | 负例 / 必须结果 |
|---|---|---|
| A-001 | 同DecisionCore/同有效Binance输入/clock，原paper和新live候选逐字段对拍概率/两侧fee/净EV/选择/原因/epoch | 旧cash edge通过净edge不达0.03拒绝；精确阈值和Down同edge规则不变；不是两套公式互测 |
| A-002 | 原真实装配显式07-007到phase1，旧默认回归 | 无opt-in旧行为不变；Coinbase只paper降级，live SOURCE_NOT_ALLOWED且0签名/POST；observer仍unsigned-only |
| A-003 | 真实RoundTaker→Broker→Predict适配器，合法候选健康正路径 | 裸BUY/无context/旧revision、错market/fee/route/q/已签bound不可证，均0POST；不注入PaperCash |
| A-004 | 各await与关键证据确认后FINAL_SEND，30秒/5秒/10秒边界和deadline等号 | 账户/book/auth/sign/ack等待使过期、loss、stop、父EOF后不得POST；输入变化旧candidate终结，不能旧fair签新量 |
| A-005 | accepted→known partial FILLED→terminal partial；官方amount/fee/net/实际VWAP | accepted不满额；只应用实际partial；剩余不补单，费用未知不称COMPLETE；actual late fill越期限仍记账 |
| A-006 | 单hash timeout→query missing→later fill→settled，重复/旧代/fee coverage补齐 | 初始POST最多一次、无新salt/重签/同hash重发；查不到不释放，旧代不回退，冲突停全账户新增；沿原consumer |
| A-007 | Rust实际producer→原supervisor→首次write→reader→final，order前耐久确认 | 手拼JSON纯函数不算；signed-null不能当新账务；同hash、candidate、seq、覆盖均实际关联 |
| A-008 | 原子量/decimals、现金和净份额、费用方向及累计/增量对拍 | NaN/Infinity/bool、缺键/未知键/坏ID/hash/null/enum/递归秘密、未知schema或v1/v2混流均在首次写入前拒绝；不回写坏行 |
| A-009 | 重复快照无新增，迟补费用/net原Broker只应用一次 | 0/unknown/N/A不混；coverage未全不假full；Python不另建余额、模型费用不冒actual，BUY份额费不双扣USDT |
| A-010 | 先持久signed hash再发送，崩溃发生在每个write/ack/FINAL_SEND/POST边界 | 发送前失败0POST；可能发送后缺结果则保留hash/最坏占用/INCOMPLETE；不得补final或假NO_SIDE_EFFECT |
| A-011 | 完整final/原生child与launcher结果；pending与可估值仓位明确 | exit0但漏final/未决/坏关系/强制kill/audit缺口非健康；账面settled但未兑付cash_complete=false |
| A-012 | 同host同账户两operations_mode/不同run/window并发争锁 | 至多一child，一方在secret前ALREADY_RUNNING；unsigned不抢live锁；不声称跨host可保证 |
| A-013 | 现有pymongo薄接缝→fake collection首次唯一insert/majority+j/精确读回→READY；同进程至少两不同轮健康候选原fake执行 | duplicate-key/写或读超时/未确认/坏绑定/版本/身份错误不取signer不启child；不重insert、不自动建集合/索引、不fallback文件，不能只有拒绝stub；本地关键审计fsync失败同样0POST |
| A-014 | 崩溃后新run_id/新window/换日/宿主重启/缺ended均遇原屏障 | 全0secret/child/POST、RECONCILIATION_REQUIRED；OS锁释放/当前余额健康不能清屏障/latch |
| A-015 | 进程内R+U恰−20及邻值、回升/结算/同tick第二单 | ≤−20立即锁，后续回升不解；换run不重置；mark未知先停新增，不能靠旧值/成本/浮亏0；Gas另币种不混 |
| A-016 | 持久屏障+已写事件供人工同账户对账，含无hash窗口不完整 | 普通budget bool/换collection或scope/删屏障/新run不构成恢复许可；未解释hash/损失/持仓仍拒；无自动reset命令 |
| A-017 | fake keyring正常/locked/缺失/Prompt、断网/账户缺页/无mark | 失败停新增，无Unlock/file备用/秘密重读循环；丢数据保留K/P/持仓，绝不作零账户 |
| A-018 | 父EOF/监督失联、child异常、控制/证据输出/告警失败、deadline与inflight竞争 | child下一可能POST前停手；原有界退出/原生exit可见，不自动重启；已可能发单即未知，不能假撤销 |
| A-019 | remove accepted+removalLockedUntil+late fill+最终权威不可成交 | 原cancel/query消费者处理竞争，只终态且核算全才释放；rest/继承风险不能靠cancel_all成功当清零 |
| A-020 | 分别考验真实现金不足/单笔/市场/总额/预占并发及实际风险超R0 | 100真预算非仅报表分母，2/2/10各独立约束，等号可、超额拒；不双算/漏算、不自动升额/缩单 |
| A-021 | 官方WON/LOST/DRAW/争议/pending→claim→人工fake原SDK receipt+同目标份额/USDT读回 | 官方结果不代表到账；正claim WAIT_CASH且0新增/自动redeem/approve；错route/读回失败保留未知hash；零兑付不造现金 |
| A-022 | SUPERVISED首单、策略pilot与UNATTENDED能力/授权分别判定 | 有人首单不要求先自动赎回；有人pilot不可用null final通过；无人必须多故障/接管/冷启动，不能声称自动连续复投或外部已通知 |
| A-023 | 原安全signer、SDK lazy FD/API、07-004/005受影响资金/clock及兼容回归 | 仍适用旧独立证据按身份复用；必要回归不删/skip弱化；实际auth/签名/网络/DB调用计数0，依赖/配置/调度/权限不变 |
| A-024 | 最后编辑后的身份、scope/冻结清单及候选隔离核对 | 当前paper进程/环境/期限/source加载行为/binary/evidence不动；旧研究参数/冻结制品不变、不读中途评分；禁止旧target-dir构建 |

金额模型向量可复用07-004 A-009–011及07-002 A-004，另以真实适配器atoms/coverage独立验证，不把旧fixture当真实场馆报告。模型数值对拍abs或rel≤1e-9，原v2传输1e-7不放宽；live原子量/身份/序号/动作计数/预算阈值零容差。不同模式实际fill可不同，但差异必须来自声明的执行事实而非第二经济公式。

## 6. 测试与证据要求

T2须给实际可执行argv/cwd/解释器/既有测试入口与隔离target，按原BOT模块colocated单测及必要集成消费者覆盖上表。Rust使用既有--locked --offline但仍禁止业务网络；Python复用项目或现有predictfun专用venv，不安装包。新测试名/统计数须源码真实存在后再引用；不为整理日志重跑已闭合套件，不运行ignored联网测试、长回测、当前paper/研究或真实binary业务入口。

独立Validate记录最终HEAD+源文件/配置/binarySHA、实际命令/nativeexit、输入依赖/正反例覆盖和未运行项；开发者自测不替代。正式唯一报告 `data/reports/2026-11-19-btc5m-live-parity-and-operations/report.md`，必要 `evidence/`；临时探针仅当前profile scratch。没有data/tasks/任务镜像/逐卡重复报告。真实小资金验证与本轮离线独立Validate分开，不用synthetic签真实PASS，不以盈利或交易笔数门槛求绿。

T1仅静态核对两实体/互引/版本/来源路径/字段和验收映射、scoped diff-check与hash；没有构建或业务测试。安全拒绝停对应动作及依赖分支，不换解释器/工具/包装/worker重放；可选步骤记OMITTED可继续独立授权工作，必需缺口仍block；普通参数/patch/stale保护按原工具在scope内纠正。

## 7. 当前运行保护、实施边界与回退

当前btc5m-baseline72-002（2026-11-19 12:12:10至2026-11-22 12:12:10 Asia/Shanghai）不得改动。active binary、完整SHA和launcher/child/session身份见RFC §6及卡面；control SHA=5590892add29593d71d5233e5c14d831da06bad0bee32822e41b966bcd8250f8，observer SHA=29edb8df1a2b1b1cbe02ee1f0b9ec613a7babe1eb54d3db245acdafb6b71f456，publiccfg沿原run身份cf27481d前缀保留，不反推缺失完整hash。

优先原fork源码+独立候选build/config；T2须先识别当前supervisor后续动态加载的Python源码，可能被当前run再次加载的文件等待paper完成才编辑，不能靠改run source/加载行为或重启隔离。构建禁止使用 `data/reports/2026-11-19-btc5m-observer-runtime-fix/evidence/validate-v11/cargo-target` 或覆盖任何旧binary/证据；新获批候选身份与旧运行身份分区管理，不把旧hash永久当新代码不可变契约。

旧14日四组冻结 `data/reports/2026-11-18-btc5m-joint-forward-validation/evidence/review-preparation/final-freeze.json` 的指定文件/parameters及其附属受保护制品原字节保留，不改参数/重跑/看中途评分。只读manifest身份不等于读取评分。T2最终按当前G3处理：本卡实读arbitrage.rs1493、phase1.rs1566、runtime.rs2370、paper.rs2378、runtime/live.rs1957、predict_fun/fills.rs1972、control.py1722行；大文件增长/跨2400的模块拆分由Principal Design说明，不授权全仓重构。

回退只停候选新增、保留实际账务/hash/占用/latch/屏障，原SDK按明确授权接管；不以旧binary/新run重新试单，不reset/stash/clean/checkout、不改gitlink或共享他人dirty。除本轮两文档外本卡无修改权限。

## 8. 开放问题与阶段交接

业务语义开放冲突0。已选复用项目现有pymongo的Mongo拒绝屏障，不把数据库方法选择退用户；实际生产库/集合/写入/连接绑定须以后明确批准，不能因离线代码完成就写生产。若确需自动跨重启恢复，另做必要字段/事务/fencing最小决策并同步正式合同，不自行加SQLite/包。T2必须完成内部typed字段/source映射、关键order耐久确认与FINAL_SEND hook、OS锁路径/Mongo薄接缝与待批准部署映射、人工接管边界、原supervisor动态加载隔离、allowlist/G3和可执行离线验证；不再把这些留实现者随意决定。

真实Gas预算、批准额度、期限、退出/取消/人工回收目标和可达接管者均为以后实测的明确授权输入，不从历史余额/旧budget flag推定，不在本卡填伪值。本阶段两文档完成静态检查后交主控Gate，按原Full图推进，不自行创建真实运行/同卡重复review或提前Implement。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-11-19 | 冻结phase1 live同core/FINAL_SEND、实际原子量与新live白名单、窗口/单实例/拒绝冷启动、MANUAL_PAUSE回收及24项离线正反例验收 |
