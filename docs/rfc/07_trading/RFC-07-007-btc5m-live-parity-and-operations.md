# RFC-07-007: BTC5m live 一致性与有人/无人值守最小运行安全

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | V1.19；R20非原子现金最小修复需求冻结，Design当前V1.18 §R19，R20待下游；不表示实现/独立验收或生产放行 |
| 本次窄修订 | V1.19，2026-11-26：仅cumulative逐腿floor候选及原settled精确核对；closure/Final/remaining/expiry/市场判定不变；R19独立目标不改 |
| 作者 | YQuant Principal / yquantprincipal |
| 创建 / 更新 | 2026-11-19 / 2026-11-26，Asia/Shanghai（UTC+08:00） |
| 工作区 / 来源任务 | /home/pascal/workspace/yquant-investment；初版 t_b946f2c3；本轮 t_6cbc04c3 |
| 来源决策 | Pascal 2026-11-26最新最小范围：只修NON_ATOMIC_CASH，不改闭合语义，不新增模块/配置/错误码族；本卡仅RFC/SPEC，不授权代码/真实API/账户/生产变更 |
| 对应 SPEC | [SPEC-07-007](../../spec/07_trading/SPEC-07-007-btc5m-live-parity-and-operations.md) V1.19，§R20.1–R20.7、D20-01–02；R19等既有目标保留 |
| 对应 Design | [DESIGN-07-007](../../design/07_trading/DESIGN-07-007-btc5m-live-parity-and-operations.md) 当前V1.18 §R19；R20待既有下游t_0722b40a，本卡不改Design |
| 依赖 | 07-002 V1.1、07-003 V0.5、07-004 RFC/SPEC V1.1 / Design V1.3、07-005 V1.0、07-006 V1.1；实际能力以当前源码及独立证据为先 |
| 角色 | 主控 Gate/Closeout；Principal Design；Developer Implement；Reviewer 独立 Validate |


## R19：第③项原请求出口观测与共享配额调度（2026-11-26，需求冻结）

### R19.1 已验基线、目标与非目标

本节及SPEC §R19只冻结③需求，优先替代本文旧阶段状态及R18中“②③④尚未冻结”的时点描述，不重写R18及①②已验行为。[①最新签收](../../../data/reports/2026-11-26-btc5m-rest-quota-part-1/report.md)为t_a9dea389/run4143及主控Closeout，11目标fixture账户普通REST每观察24→2、部分资格24→4；[②最新签收](../../../data/reports/2026-11-26-btc5m-rest-quota-part-2/report.md)为t_3c4556a5/run4146及主控Closeout，同5系列fixture发现冷6→2、热1，两页目录冷3、热1。均为离线且未部署；不以旧分析中的未实现措辞重开①②，不冒充生产配额实测。

③目标是在原PredictFun REST出口真实观测每次HTTP尝试及其归因，并在同一进程的全部该出口消费者间共享配额准入，消费当前服务端APP反馈、限制自身发量、遇429在reset前阻止同桶继续发送。不能仅打印日志、仅给单调用sleep或全拒绝后签收。保留①同run历史免读、②目标路由/300秒目录、所有当前账户/全分页matches与本run结算读取；不通过删必要读、延长poll/freshness或故障预算换取降耗。

非目标：未知外部进程/主机的配额协调、APP控制台/密钥管理、Redis/分布式限额/独立服务、新HTTP客户端/runner、全WebSocket、自动重试写请求，以及④任何实现。原Closed+Accepted/本run结算扫描仍按既有基线，不借本项结束其轮询。原fixed deadline、R17生命周期、R16现金等待、120s账户/执行/结算读失败预算、行情自身failed_ticks政策、10s发送freshness、≤5s工程目标、资金/签名/ACK/未知提交保护均不变；≤5s不因配额等待改为新的宽松门禁，也不保证配额不足时可交易。

### R19.2 配额事实、权威性与边界

事实来源是[既有只读分析](../../../data/reports/2026-11-26-btc5m-rest-quota-analysis/report.md)§1/2/5及其三份`evidence/headers-*.json`，本卡不访问真实API/控制台/账户/凭据。保存的公共目录、rounds及实际`/v1/markets/orderbooks?ids=…`均为250/60s；后者不得套单市场orderbook的500。官方限额文档当时说明APP内key共享、固定窗口、429和相对秒数RateLimit-Reset；普通旧key240/60s、新APP普通250/60s、交易500/60s、search120/60s是来源边界，不是本key额度的当前证明。相同Remaining=249及s-maxage=3不证明每route独立、缓存请求免费或服务端失效。

配额scope覆盖同进程、同固定API部署的原出口，不能按caller、route、JWT、账户、key实例或client克隆分裂预算。没有公开APP身份可核时，同部署客户端保守共用，不读取/散列/落盘秘密来识别APP；不同部署隔离。路由按实际路径及明确规则归桶，服务端数字反馈约束对应桶，`rpm`等标签不独立证明跨桶同一身份；未知路由不得另领一份可能与已知桶重叠的信用，按SPEC保守同时约束其可能共享桶，不推定它真实归属。原生HTTP交接尝试数是本进程可证事实，不证明socket已发字节或服务端已扣额；Remaining是可能受APP外部请求/缓存/并发影响的服务端反馈，不可相减伪算本程序消耗。

本项必须同时有本地发送上界与服务端剩余额度约束。缺头、坏头、缓存/乱序响应不能补回已经消耗的额度；未取得可信反馈时使用明确保守预算，不无限放行，也不要求先人为打出429。可解释多窗全部同时满足，不能挑最大窗口；无法安全解释的更强政策拒绝受影响准入，不能静默丢掉。具体可计算规则、未知/失效输出见SPEC §R19.2–R19.5。

### R19.3 发送、失败与观测要求

1. 观测必须区分固定method/规范化route/bucket/caller、HTTP attempt与逻辑读、分页/批次/401刷新/冷auth、RPC/其它服务及audit事件。每次实际REST交接只计一次，成功/429/其它HTTP/transport/取消分别可见；排队或本地拒绝不是已发HTTP。不记录URL/query、cursor/ids列表、body、账户地址、key/JWT/signature、raw headers/错误链；沿原脱敏log，不扩live审计wire/schema，不建新sink。
2. 所有原出口请求均须预算准入，含auth、分页和写请求；同桶429对所有优先级生效，普通桶冷却不凭空冻结独立交易桶，依赖未完成则仍不能新交易。优先保证已发生风险的账户/执行/结算核验及原已授权取消，再是当前决策/发送准备，最后目录发现/后台读取；优先级不是额度豁免，不抢占已交接请求。取消/deadline/父失联必须及时终止等待、无额度泄漏；不得持Broker/发送锁跨异步排队。
3. 配额等待计入原观察请求年龄及所属读失败时钟，不能把等待当成功读、刷新receipt/generation或重新给120s。无额度在相应既有错误出口产生安全typed失败；当前读确实完整成功才按原规则清对应失败，不清其他streak、硬stop或deadline。429不在helper内部自动重试；后续原tick/同hash只读可在准入允许后继续。
4. `controlled_write`仍须在`with_send_permit`内第一次poll唯一request future。任何可等待的额度获取在原最终同步许可前完成；许可内重新同步确认额度、stop/身份/receipt/generation/freshness/expiry及原FINAL_SEND条件后，紧邻首次transport poll。若资格被并发429/预算变化撤销且尚未交接，必须0POST并走原明确未发送拒绝/自身预占处理，不在已消费原子许可后sleep或以排队Pending冒充已交接；旧candidate不得获额后直接重放。第一次真正交接后Pending/超时/401/429/响应坏均不重POST、不重新签名或释放未知风险。429官方“不处理”不自动推翻原本地MayHaveSubmitted/Unknown保护。

### R19.4 收益、验收与阶段交接

①②节省已经实现，③不得重复报功。③在相同业务输入/成功请求序列、无节流的离线正例中，不新增REST/RPC、不删当前必要读且健康路径能到原fake发送；饱和/429反例必须实际减少reset前原会继续发出的尝试，同桶并发不得超配，恢复后继续原消费者，不能只测limiter helper。目标是可审计的本进程配额遵守和减少已知冷却期无效请求，不保证服务端零429、固定生产降耗百分比或24小时稳定；服务端外部竞争/新事实/分页/认证成本逐项披露，不把这个边界当作降低①②或发送freshness目标。

必需验收为SPEC D19-01–08：真实原出口→adapter/account/Broker/drive与受控发送，离线替换transport/clock，涵盖冷/热auth、分页/批次、缓存/坏/多窗头、并发/乱序/取消/reset、发送前后边界、原120s/deadline/strict reader和①②组合。原生计数、等待与发送时点、命令/native exit/最终source身份及未测项分列，不用公式/旧报告冒充本项业务PASS。

RFC/SPEC阶段只修改两文档至V1.18；R19需求closed，无需新增平台或额外阶段。内部函数/状态/锁顺序/精确allowlist/G3/fixture与身份闭包由独立Design阶段落实，不在需求阶段抢写。阶段指针同步：Design现为V1.18 §R19.1–R19.9（t_edbfef11），主控仍须核三文档及可执行边界后另放既有Implement行政HOLD，不能凭parent done自动跳阶段。③业务实现/验收/真实配额/部署/交易均未做，④后续未冻结/未实现；后续必要证据仅用`data/reports/2026-11-26-btc5m-rest-quota-part-3/`，不另写任务镜像。

## R18：第①项已核清历史基线免重复读取（2026-11-26，需求冻结）

### R18.1 目标、范围与事实边界

目标是将启动时经原完整核验、已最终结算且现金账务已核清的旧记录，冻结为同次运行的内存历史基线；在原消费者后续完整账户观察及跨BTC5m策略轮次时，实际免除这些旧记录订单详情及官方market/category解释的逐条重复请求。启动前原双fresh与完整审计继续，不得先拿旧文件或本地Closed作为资格。仅第①项，②③④均为后续未冻结/未实现；本节不预设后项接口、参数或实现。原R17、发送前edge及其他既有契约不变。

来源为[只读调查](../../../data/reports/2026-11-26-btc5m-rest-quota-analysis/report.md)及其 `evidence/historical-proof-load.json`、`offline-native-counts.json`。旧保存输出有5条 claimed_win、6条 settled_zero、11个独立 market/token；这些数量不是可跨轮复用资格。调查的热态单页模型为每次账户普通 REST 24 次，其中22次为历史结果；全部具备资格时才有24→2、5秒情景288→24/min的上限收益。该数字是条件需求模型，不是旧运行 HTTP 总量，也不是本项实现后实测。

复用前轮定位并定向核实的原消费者输入（路径相对BOT；不是新实现）：

- `src/service/predict_fun/account.rs:461–505,531–576`：`explain_positions_mode`比较历史净量与当前持仓，缺失token经`official_settlement`的完整market/category、round及有序token pair得到Confirmed的零/正兑付解释；启动正claim还须原`claimed_cash_matches`的逐atoms现金等式。不能仅以总现金拟合代替历史/官方事实核验。
- `account.rs:628–816`：`reconcile_account_history`从第一页走完账户matches分页，未知hash仍拒绝；`history_proven`已有订单Final且账务完整后的净贡献复用。它不单独证明官方结算/到账已核清，本项不得重建增量历史管道或把已有节省重复报为新增收益。
- `account/runtime_claims.rs:8–46,54–119`及`src/bot/runtime/live.rs:648–766,938–964`：原账户读包含positions/history、open orders、账户身份与链余额；`seed_predict`在完整性、精确现金/预算、身份、挂单和持仓一致性检查后才设原账户baseline。运行时本run的bound claim仍核身份、execution generation、链库存及官方结果，不因本项成为旧历史。
- `src/service/predict_fun.rs:929–951`的严格market/category读取及`src/bot/runtime/live_accounting.rs:669–723`的本run逐市场结算、发布后fresh账户/现金复验保留；本项只豁免已核清启动历史解释，不修改通用`settlement_market`、本轮Final或`revised_result`比较规则。

权威性边界：基线保存的是原严格消费者已成功核清的历史事实与账务解释，依据是Pascal明确批准的运行期免轮询政策，不是远端全部字段永久不变的证明。此前取得的[官方 Resolution](https://dev.predict.fun/concepts/resolution)与[Markets and categories](https://dev.predict.fun/concepts/markets)概述不作为精确部署的合约审计结论。已核清基线不再主动轮询字段修订，因此未读取的远端价格/状态/payout修订或重组不能声称被检测；若当前读取已发现矛盾，仍须原硬保护。旧block/run/研究与拒绝事实保留在Kanban历史，不再作为本节待决门槛。

### R18.2 启动资格、有效范围与安全要求

1. 资格须同时具有启动原双fresh/完整账户与历史核验成功、绑定订单Final且账务完整的净贡献、原严格官方结果Confirmed、结算与到账解释已核清、身份/路由一致且无已知冲突。沿原赢/零/半兑付和现金等式，不新发明finality状态或证明协议；本地Closed、声明、空仓、总现金吻合或旧proof文件存在均不足。完整round/provider附加要求仅决定能否免重复读取，不强化原启动准入或通用结算器；仅附加元数据不合格的目标不纳入基线，继续原严格读取，可形成空/部分合格成员集。原有身份/账务/结果冲突、未到账等拒绝保持，合格正例必须真实减少请求，不能以全部不命中签收。
2. 仅绑定必要的account/run/deployment/chain及资产合约route、market、有序YES/NO token pair、目标token/side、历史订单hash/净贡献及原结算/到账解释。基线只在原启动全部核验成功后生效，不回写旧proof/运行证据；启动失败不得部分激活。仅同run内存有效，跨重启/换run/换account不沿用，重新走原完整启动核验。
3. 同scope下符合资格的启动历史必须跨tick/策略轮次实际复用，不再按tick、固定60秒或其他TTL重读旧订单详情及官方market/category；无后台刷新。正常generation推进、跨市场及缓存访问不自动使全部基线失效，也不更新历史证据的观察时间来伪造fresh。当前观察receipt/generation仍来自实际当前读取。
4. 当前余额、gas/allowance、positions、open orders、全量账户matches、新执行/费用、未结算/未到账claim及结果发布后fresh账户/现金核验仍沿原路径。matches仍每次从第一页走完整分页，缺页/失败不得解释成无新历史；不为降耗省略此扫描。
5. 当前读发现新未知hash/token、历史净贡献/费用/持仓或身份/route不一致时，基线不得遮蔽，受影响对象沿原必要证明/typed失败处理；已知结果/身份冲突沿原硬停，保留旧证据与风险，不降级miss吞冲突。无资格对象原严格读取失败不得回退旧成功。真实scope变化不继承旧资格，不能与普通轮次/generation推进混淆。
6. 启动已核清正claim的现金已计入原baseline，不能再次记为本run收益/现金；零兑付不造现金，半兑付及±1atom拒绝不变。本run新增事项不纳入启动基线，继续原Final/结算/到账与R16核销；原fixed deadline、120秒读失败预算、sticky stop、未知提交和所有签名/交易阈值不变。

### R18.3 收益、验收与阶段边界

已核清启动历史在后续观察不再产生其逐条订单详情和官方解释请求，是本项必须达到的行为；全miss、同观察内去重或保留全部原读取不能签收。旧11条保存输出不被本卡追认资格，Design/Implement须从原启动成功输入得到资格，并以synthetic transport经原消费者形成正例，而不是新增“所有REST字段永不修订”的前提。

后续按SPEC §R18.4的D18-01–06，以同输入原adapter→account→Broker连续观察及原producer→严格reader证明普通REST净减少；单列原启动成本、已有history_proven收益、新增资格/冲突处理成本与RPC，不用公式或helper计数冒充原消费者实测。反例包括启动未核清/未到账、缺页、新hash/token、净量/route/身份变化、已观测冲突、重启、跨60秒及当前generation推进；未读到的远端修订明确为不检测，而非伪称硬停覆盖。

需求决策已闭合：Pascal批准的启动已核清历史免轮询，取代未实施60秒TTL建议及旧草案的永久不可修订/逐轮全字段修订检测前提；不引入TTL、后台服务、DB、WebSocket或finality平台。这里只冻结目标、资格/失效和验收，具体接缝、函数、文件范围及回归方法交原Design阶段。主控核两份文件一致性后解除既有Design卡行政HOLD；本卡done本身不构成实现/Validate/生产许可，也不允许启动后项。

## 发送前保守 edge 预检与候选级拒绝增补（2026-11-25，Pascal明确授权）

本节为用户本次“两个事情一并优化，由主控接手”的窄行为增补，优先于历史将所有SIGNED_BOUND_UNPROVEN笼统硬停的表述，不重开R17/结算/接管工程，不修改最坏资金或份额证明。分开“证明缺失/矛盾”与“已证明约束下经济性不合格”。本节不是已测试或生产放行结论。

1. 仅受控PredictFun live候选进入原下单准备时，在本候选RESERVE/sign/POST之前，用已有冻结gross数量Q、候选fee_rate_bps、candidate.fair、候选限价下原reservation现金A与原min_edge，按最终保守检查相同整数公式预检。N_min=Q-floor(Q*b/10000)；V=floor(N_min*fair)沿原exact_floor_mul；所需利润原子量沿原cash_at_limit_atoms(Q,min_edge)。仅V-A>=所需利润才继续；经济性不通过跳过候选、无attempt/预占/签名/POST，不停止窗口。预检是原live Broker准入，不修改共享core/paper模型输出及初筛fee模型，也不保证之后账户/时效/真实签名检查通过。
2. 原guard所有身份/hash/数量/fee/route/签名/receipt/generation/风险检查必须先通过；已证明且正的N_min下，仅经济性不合格、阶段仍为发送许可前的Candidate且原attempt仍Prepared/NotSubmitted时，使用原typed CandidateRefused/封闭INPUT_CHANGED，诊断保留EDGE_BELOW_MIN。沿原release_not_submitted仅释放自身预占、保留hash/tombstone及审计，清本候选，不stop、不takeover，下一原tick产生新candidate再评估；不重试旧candidate。
3. 在Window/send-permit或may-have-submitted/unknown/已发阶段，不扩大软拒绝；无法证明bound、零/非法数量、fee/route/identity/hash不符、算术或取时错误、账户异常、ACK/输出/父失联、loss latch等继续原硬保护。不能仅凭NOT_SUBMITTED或字符串包含edge把其他错误降级。不撤销已有stop，不重启旧run。
4. 共享小函数只复用已存在的minimum_net_shares/exact_floor_mul/cash_at_limit_atoms整数规则，预检和最终guard共用经济性判断；费率签名域原cap、min_edge=0.03、min_secs_left=30、10s新鲜度、预算/敞口/损失阈值、allowance、R17等待/Final、结算及接管均不改。
5. 原生回归分别证明：真实core合格但保守不足的历史参数候选在原Broker预检0sign/POST/RESERVE且运行继续；原guard已准备场景的纯经济性拒绝为typed候选级，Window/真实无证明仍硬错；拒绝后同一Broker/adapter/core下一新候选正常单次fake POST，旧候选不可复用。保留等号/±1atom、零数量/坏费率/身份/bound/未知发送反例，并通过原producer→Python严格reader消费。公式回算不是native RED；必须先原生RED再GREEN。

实现限定BOT原controlled.rs（小经济性helper）、taker.rs（仅准备前预检）、live_control.rs（仅已证明经济性分级）、原live004_regression.rs回归。必要原fixture最小参数化可用tests.rs/controlled/r16_fixture.rs，不新增平台/runner/schema。live_control.rs已1201–2400受控，本次仅替换原check_locked分支、职责不增，不继续堆无关逻辑；共享算法放controlled.rs以保持父职责。两binary重建至本主题新candidate-edge目录，旧制品不覆盖；原control selector及signer reader pin机械绑定、完整source身份新冻结。原shell/生产activation/guard不改，代码绑定不等于启动许可。本次Light Implement→独立Validate，0open才能离线签收，无真实账户/交易/生产写。

## R17：accepted 订单生命周期等待窄修订（2026-11-24）

### R17.1 事实、基线与有限替代

事实源为[根因报告](../../../data/reports/2026-11-24-btc5m-unproven-root-cause/report.md)及其 `evidence/causal-ledger.json`。订单8882120994/8942043150分别107/105次完整零成交读取，五现金/费用/库存字段KNOWN、分页完整，却在accepted后121.792/123.679s以FACT_INCOMPLETE停止，距签名expiry仍有176.432/174.151s。已定位等待分类缺陷，不宣称解释未成交原因。原raw REST status未记录；key-only GET403不证明认证根因，历史eth_call失败不证明当时链状态；到期后原生六声明对账闭合是后来观察，不能追认停机时Final。

当前 R16、冷历史及旧窗口接管均为已有实现基线，不重开其开发或已关闭门禁；接管独立结论 t_84db8f46 为 PASS_OFFLINE_PRELAUNCH_ONLY。旧§R16及下文 Draft、缺口、候选路径、待下一阶段叙述均只保留各自历史含义，不是本轮待办或新授权。R17仅替代“完整零成交仍一律按unread 120s终止”的行为及对应历史补注；R16现金等待600s、原Final/账务/风险/冷启动保护均不变。

历史归因以根因报告§6为准：300s TTL原已存在；R5前run010在完整零成交OPEN后下一候选被拦时约0.77s即FACT_INCOMPLETE。R5 t_74460a41于2026-11-22 16:41–17:11（Asia/Shanghai）把UNKNOWN/0合并为120s有界重读，任务及验收本身要求always-empty到点停机；commit `4b6420f6a11eb5303d1a94949037f52b866d24c3` 的2026-11-23 03:31为自动归档时间，不是首次编码时间。因此是旧过早停机未修完整、R5留下当前生命周期分类缺口，不是今天launcher/reader引入，也不简单归因开发者违约；不重开旧卡。正常已知零成交是成功取得当前数量/账务事实、只是未证明Final，与UNKNOWN/读取缺失不是同一事实类别。

### R17.2 冻结业务决定

1. 仅唯一已知accepted、精确attempt/hash/venue ID/账户/market/token/side绑定、当前完整分页/数量/账务且无冲突的未闭合订单，可以保留原保守预占，持续原execution读取至其已验证签名expiration，再用原120s上限尾查。寿命不来自市场轮次结束、轮询时间或重新构造now+300；MARKET_ORDER_TTL_SECS=300只是当前签名政策，不是新的等待常量。
2. 正常pending不等于Final、不解锁风险。完整零成交可等待；OPEN仍为Open；未知status沿原Unknown处理，不获宽限；部分/晚到成交继续原累计账务/费用/generation/估值消费者，非Final不得释放剩余预占或产生下一单。当前读真正缺失/失败、未知提交仍保留原120s保护，不能全局改为600s。完整定义、双时钟唯一算法、故障交错及同tick优先级见SPEC §R17.1–3。
3. 等待期间0新增订单/RESERVE/重签/重发/自动撤单，保留同hash/tombstone，无风险恢复；原run deadline、loss、identity/事实冲突、父失联、输出及其它硬stop优先。只有实际Final且原完整账务/风险/mark/receipt/generation通过才可清本订单等待，下一tick重新采集输入，经原发送门继续同run；不是复用过期candidate或自动重启。
4. 到期不自动Final；到期后仍无权威关闭证明，最迟在固定expiry+120s（或原窗口/硬stop更早）沿原错误终止并保留未决风险。首次pending的双时钟上限不被成功读、重复快照、轮次切换、调度暂停、回拨或重新进入helper重置。关闭证明保持原ChainRead::closed的严格条件，不能将零持仓/市场结束/REST终态任一单项当成Final。
5. 诊断仅原平台status封闭分类、签名expiry、固定区块时间与关闭分支；复用既有脱敏log，不改事件schema/type、资金恒等式或reader。自由status一律UNRECOGNIZED，不记录原响应、JWT、签名或异常文本；精确落点及不改wire的证明见Design §R17.4。

### R17.3 代价与交接

资金可保守占用至expiry及有界尾查，机会吞吐可能下降；不保证成交、收益、真实延迟或24h稳定。仅一次受限Implement与独立Validate，必需回归见SPEC §R17.4；不新建平台、服务、配置或Full阶段。此卡仅原三文档增量与静态检查，业务实现/测试/构建/真实签名或交易均NOT_EXECUTED；旧工程PASS不代表本缺陷已修复，也不增加部署或启动授权。

## R16：本轮生效增量（2026-11-23）

本节与 SPEC §R16 V1.15 成对生效；仅替代下文旧阶段状态、已完成能力的待办表述、WAIT_CASH 立即结束及“已精确回收仍不能在本 run 继续”的解释。参数化、同 core、实际账本、原 reason、10s 门禁、所有风险限额与冷启动拒绝不变。Design 当前至 R15 的映射不是 R16 已实现证据；下阶段只补本节真实缺口，不重做平台或原账本。

### R16.1 已验基线与真实差量

基于 [2026-11-23 只读诊断](../../../data/reports/2026-11-23-btc5m-live-diagnostic/report.md)、t_239d0c0c 独立交接及本轮源码静态核对；本文不重跑其业务测试。

| 分类 | 事实 / 定位（路径相对 BOT，符号优先于行号） | 本轮处置 |
|---|---|---|
| 已验离线 R15 | `live_control.rs::check_locked` 在 facts/ACK/permit 仍校验 receipt 完整性、identity、generation、attempt 和 10s；`account.rs::read_account_snapshot` 五腿并发、`reconcile_account_history` 闭合历史记忆化；`fills.rs::place_controlled_tracked` 复用 tick 账户读及独立读并发 | 保留，不重复实现。reviewer run4022：lib638 passed/0 failed/4 ignored，集成15/2/2/4；属上游证据复用，不是本卡新测试 |
| 性能证据边界 | 固定170ms、9次合成：24 calls，book→facts p50约0.860s、旧 end_to_end p50约2.234s；fixture 无历史 hash；before 重复 key/旧标签 | 不能称同版严格前后比，也不能称生产≤5s；按 SPEC §R16.3 修复测量与报告，旧制品原字节保留 |
| R15 三 minor 未闭合 | before JSON 重复 key/旧标签；并发 history 的 `market_for_token` 可能早于 `read_positions` 的 `remember_market`；balances/authorize 双故障优先级缺反例 | 本轮承接闭合，不改 t_239d0c0c 历史 PASS；验证未通过不得以该 PASS 上线 |
| R13 已有局部恢复 | `live_control.rs::credit_claim` / `promote_pending_claim`、严格 reader 的 CASH_CONFIRMED 撤销 CASH_PENDING 已有实现 | 保留精确 atoms 与其他 stop 不可清的规则；已有局部单测不证明 drive 续跑 |
| R16 缺口 A | `live_control.rs::RunControl::must_end`（当前230）将 WaitCash 视为结束；`paper.rs::wait_controlled_stop` → `runtime.rs::drive`（1609–1611）即 finish/return | 区分临时停新增与终止，原 drive 在有界等待读取、精确恢复后继续同 run；不新建 runtime |
| R16 缺口 B | `account.rs::reconcile_account_history`（761–764）跳过 bound_orders；`live.rs::claimed_payouts`（1058–1095）只消费 snapshot.claimed_win，后接 `check_runtime_account` / `credit_claim` | 补本 run 已闭合实际库存的兑付证据接缝，区分启动历史 claim 与本 run 回收，保留唯一账本与旧累计去重 |
| 生产激活缺口 | run018 绑定 R14 SHA256 `96a7ed059eb13253f36c8dd6bd8abf42a803574b7b8171bfa698b1aad7b1e1b7`；上游核验 R15 候选 `bcb5a8c0841df89a403dd4606f951f9f7965ecfe55f58e1bbb33e31f38b75d5c` 未部署 | 不切 selector、不重新授权、不新开 live/paper run；未来另行明确授权 |

run018 是 PredictFun/BSC，不是 Polymarket/Polygon；35 attempts 中34次 NOT_SUBMITTED/INPUT_CHANGED、1次成交，非34次交易所拒单。按 order wall 近似有14次拒绝时 spot/book request age 均≤10s，不能全部归因过期。09:55:06.275 CST CASH_PENDING 后5.407s现金增加2.0384 USDT且持仓空，但原 seq1092 reconciliation 不完整、reader INCOMPLETE/FACT_INCOMPLETE、没有 CASH_CONFIRMED；停机后独立对账不能追认原 run 闭环。mark_time 的缓存最小时间与暂时 generation 失配不另扩为本轮根因。

### R16.2 冻结决策与边界

1. 拒绝按事实区分：无机会/经济规则的正常拒绝；首次可能发送前的本地门禁拒绝；确有权威终态证据的交易所拒单；可能发送后结果未知。只有明确未提交才释放该 attempt 未用预占；Unknown 不清 tombstone/余量、不重发。诊断只在既有 decision/order 流兼容增加有界 stage/detail/检查时钟及 age，不改变 reason、不新建 stop 词汇、不记录 raw 响应/凭据；具体封闭字段见 SPEC §R16.2。
2. 本 run claim 只来自本 run 实际闭合 attempt 的同账户/市场/token/净份额，官方结果与原绑定一致；按 atoms 核对库存减少及现金全量等式，两项缺一不入现金。交易增量与claim现金/库存变动在等式中互斥单列，启动前历史 claim 已在开仓 baseline 中，不再算本 run 收益。现金或官方结果先被不同消费者看到均可暂存证据；账户适配器已证明同目标官方兑付/库存移除/精确现金但runtime尚未消费结果时也立即停新增并进入同一有界等待，最后用同一规则核销一次；不能直接 mock claimed_win 代替适配器完整证据链。
3. 精确恢复还要求：所有正 claim 已核销、剩余经济持仓/挂单/预占/在飞为零，费用与当前 generation 账实闭合、receipt 新鲜；没有其他 stop/loss/degraded/父失联/输出故障且原 deadline 未到。旧现金等待不能遮蔽等待中新增的硬终止；保留原 CASH_PENDING 事件及后来终止证据，不能因首因记录为 CASH_PENDING 就清除后来保护。
4. 等待上界复用现行 SPEC §4.6 的600s只读上限（现有 `live_accounting.rs::LIVE_TAIL_BUDGET`），逻辑名为 CASH_WAIT_BUDGET=600s，而非 R14 READ_FAILURE_BUDGET=120s。从首次可归属正 claim 的 CASH_PENDING 进入时起（含账户适配器先有证明而runtime结果稍后消费的顺序），以包含暂停的双时钟、600s或原 deadline 任一先到为上界；重复结果、部分回收、成功读或读失败均不重置。等待内0新增风险，只复用原只读账户/订单/官方结果消费者；不触发自动 redeem/SELL/提款/approve，也不延长授权。准确触发、清除与终止规则见 SPEC §R16.5。
5. 选择600s是沿用已批准只读上限、避免新调参/调度或猜测兑付SLA的最小政策，不是延迟分位数推导。5.407s仅单次观测，真实领取/到账延迟分布未验证；等待可超时而保持未闭环，不保证人工会在600s内操作。终止后只做原安全收尾，绝不重新开放风险。
6. ≤5s定位为工程目标，不增加或放宽发送准入阈值：主指标从本 tick 首次账户采集请求发起到原子发送许可最后检查完成；另列决策盘口 receipt→同一检查的时长，账户/spot/盘口 receipt age 和 spot/盘口 request age 分列。旧探针 facts 前区间及未含账户读的 end_to_end 不可代替这个目标；尚未做真实目标环境实测。

这里的“同 run 恢复”是已授权风险窗口内、人工或场馆既有机制完成资金回收后的精确事实消费，不是新增资金动作授权、自动赎回系统或冷启动自动恢复。除本节指明的恢复接线与证据缺口外，不改金额、min_edge/min_secs_left、allowance/预算/敞口/止损、签名/ACK/首次发送原子门、身份/generation/unknown 保护、paper 账本或经济模型。

### R16.3 验收与阶段交接

必须按 SPEC §R16.6 的 D16-01–D16-10 逐项覆盖 R15 三 minor、拒绝归因、两种到账顺序、逐 atoms 反例、恢复续驱动、其他 stop/deadline/读失败及 paper/live 配对。Design 冻结 source/wire/consumer 的最小映射和精确 allowlist；实施与独立 Validate 分离。新正式验收仅使用 `data/reports/2026-11-23-btc5m-r16-integrated-validation/report.md` 与其 `evidence/`，不覆盖历史报告/探针/run/candidate、不创建任务镜像；本阶段不写结果报告。T1 只验证两文档实体/版本/互引/契约与 scoped diff-check；R16 业务测试、真实环境性能、部署及资金动作均 NOT_EXECUTED。

## 既有生效契约：公开 run JSON 参数化（2026-11-22）

来源：t_298e36df 与 Pascal 本轮已授权 Light 决定。下文旧 100/2/2、98/1/1/10/20 及历史算术、FAIL、原始 bytes 均保留为历史示例；本节替代其“唯一合法数值”含义，不追认旧运行。新入口显式要求 `controlled_run={budget_usdt,duration_seconds,operations_mode}`，资金仅复用 `strategies.btc_arb.order_usd` 和 `strategies.limits.{max_order_usd,max_market_usd,max_total_usd,max_loss_usd}`。缺省时旧 paper/legacy/replay 行为不变；同一候选 binary 与通用 launcher 从一份公开 JSON 冻结全 run 参数及 config SHA，不从账户现金自动推预算，不换 config 复用 activation。

参数关系为 target≤order≤market≤total≤budget；各金额必须有限、正数、非 bool、无溢出，最多六位 USDT 小数且≤1,000,000,000 USDT（限定到微 USDT，保证现有 f64 DecisionCore 输入的公开十进制往返唯一；风险 atoms 从原始 JSON 数字 token 精确解析，不从 f64 反算；budget_usdt 另可为≤18 位小数的十进制字符串（按 atoms 精确映射，不截断、不四舍五入、不容差），使 C0 能逐 atoms 等于观察到的 collateral，其余金额仍限六位小数）。loss 独立为正，不要求 loss<exposure；原 0.5 USDT dust floor 保留，不自动缩单。当前公开示例 budget=97、target/order/market=1、total=10、loss=20、duration=86400、unattended，仅示例。预算 B=C0+R−K、NAV=C0+net_pnl 的 C0 与 loss/各 cap 全部取本 run 冻结值，原账户现金单独保留。实际 exposure≥total 沿原黏性停止，不重启。

新 controller 从配置 duration 生成 deadline；若显式 CLI deadline/mode 存在须相同否则拒绝。native options/run/context/runtime 与现有双时钟一致；supervised 0<duration≤21600、unattended≤86400，旧 unsigned 6/72h 与旧 signed 6h 不变。started/final/ended 与严格 reader 使用同份 frozen 配置，禁止通过任意预算常数放宽检查；旧 run007..011 只读兼容、不回写。

定向消费者：config.StrictJson/load_controlled → native options → Broker LiveState；arbitrage 原 order_usd→DecisionCore target→attempt；live.seed_predict 预算准入；taker 预占/可用额/check_caps；live_control FINAL_SEND/total stop；live_accounting project_window 预算与 loss；Python control 固定值/started/deadline 与 live_events 首写、关系索引、ended/reader。超大文件仅原位接线，参数解析与新测试放小模块，不扩既有 tests.rs；本次修改仍须由独立 reviewer Validate。

Canonical `tools/predictfun/btc5m_launch.py` 仅机械归位获准旧 wrapper 步骤，复用 control/live_guard/reconcile 事实及 lazy PortfolioMongoLoader。import/参数检查/默认预检无执行副作用。run/window/auth、声明订单 hashes、精确旧 ARMED 目标显式输入；完整新鲜≤900s、同账户/config 的 reconcile、positions/history、无挂单、外部流及 gas、现金≥budget 的资格检查先于 activation 改动、旧 ARMED 轮换、arm、秘密读取及 child。失败上述副作用为零；成功仍需显式执行授权；精确匹配一条旧 ARMED、不通配删除、不重试，保存旧记录及 activation 原 bytes。原 child 再核账户/预算；本轮仅 fake collection/activation/child 离线验证。

## 1. 执行摘要

把现有 phase1_net_shares 决策契约贯通到既有 signed live Broker/适配器，输出可审计的实际执行、现金、净份额、费用及未决风险；不再让 signed 继续 legacy 决策而借用 paper 验收。复用现有 signer、账户门禁、SDK 与 supervisor，增加最小单实例和崩溃后停新风险机制；本轮选择“有界单次无人值守 + fail-closed 冷启动 + 人工回收资金”，不建设自动恢复/OMS 平台。

当前仅批准研发和离线验证。工程 PASS 只能支持以后申请具体真实动作，不证明 alpha、真实余额/权限、链上到账或无人值守部署资格。

## 2. 背景、基线与三类矩阵

BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`；下文 src/、tools/ 相对 BOT。本卡只读源码，不重跑既有业务测试；“已验收”注明复用来源，并非本卡重新签收。

入场主仓 HEAD=`9e06cdac513cd7ec616ee4f7877913330195fcf2`，BOT HEAD=`8f5dcba5b0334623bb0faf5c861fc342c1fe514e`。共享 dirty 含 07-006 三文档、pipeline skill、BOT observer/control/test 的既有修复，不属于本卡增量。

### 2.1 已验证离线基线：保留，不重新立项

| 能力 | 当前源码 / 独立证据 | 限度 |
|---|---|---|
| live 数量/核算/终态分离、实际增量、unknown 闭锁 | src/service/venue.rs:89–237；src/bot/runtime.rs:710–766；runtime/live.rs:115–252；[07-002 closeout](../../../data/reports/2026-11-13-predictfun-live-foundation/closeout.md) | 已有 execution snapshot 应用，不再声称 unknown 回填计划量的旧缺陷仍在；未证明真实场馆 |
| 账户启动/运行对账、分页与预算声明 | runtime/live.rs:281–360 及原 account reader | 已有 fail-closed；内存基线不等于跨重启恢复 |
| 固定 signed child、安全 keyring、SDK lazy pipe/API key | tools/predictfun/btc5m_control.py:1624–1671；cli.py:145–182；sdk_ops.py:409–423 | 不重建 signer/钱包/认证器/资金 SDK；历史认证不证明本轮余额 |
| phase1 净份额 EV、因果时钟、候选重验 | src/bot/arbitrage/phase1.rs；runtime/paper.rs:880–952；07-005 已验一期及后续修复 | 现只绑定 unsigned paper，不可外推 signed |
| observer 因果水位与 72h 固定候选接线 | t_3cfa9034/run3874 PASS_OFFLINE_REPAIR；t_655f69cf/run3876 PASS_LAUNCH_WIRING；当前 control SHA=5590892add29593d71d5233e5c14d831da06bad0bee32822e41b966bcd8250f8 | 复用已闭合证据，不重做 observer，也不扩 live observer |

### 2.2 真实工程缺口：本轮差量

| 缺口 | 现状定位 | 本轮最小目标 / SPEC 验收 |
|---|---|---|
| signed 没进入 phase1 | arbitrage.rs:69–73 依 broker.is_phase1；paper.rs:641–673 要求 PaperCash | 策略契约与执行模式解耦，同 DecisionCore；A-001–004 |
| paper 的同步 take_candidate 不能直接承担 live await | paper.rs:880–920；predict_fun/fills.rs:95–208 中有账户/盘口/授权/认证等待 | 原 Broker 薄适配，最终发送前重验；晚到真实成交必须入账，不因超时丢弃；A-003–006 |
| signed 公开输出只有 null final | control.py:1059–1064、1690–1698 | 独立分版 live 白名单及真实 producer→supervisor→首次 write→reader，非 paper 虚拟账；A-007–011 |
| attempt/tombstone/loss 在内存，run_id 独占不是账户互斥 | runtime/live.rs:19–44；control.py:1610–1614 | 同 host/账户单实例、持久拒绝屏障、冷启动停新增；A-012–016 |
| 故障与现金回收缺运行级闭合契约 | 既有 halt/cancel/SDK 在，但不足以签无人值守 | 复用停止管道，人工接管、未知不释放、到期待兑付不当现金；A-017–022 |

### 2.3 生产授权/真实验证缺口：不是离线实现失败，也不自动放行

| 对象 | 以后必须明确 / 验证 | 当前状态 |
|---|---|---|
| 认证、私有 API/RPC、账户身份/余额/挂单/持仓/Gas/route | 账户、链、版本、只读动作及时间；同目标完整读回 | NOT_AUTHORIZED / NOT_EXECUTED；不能用历史 100 USDT / BNB 快照 |
| 首笔、自动策略 pilot、无人值守 | 分别给金额/次数/期限/退出/取消/停手与接管责任；外部执行及风控确认 | 三者独立递进，不因前项通过自动启后项 |
| allowance/operator、卖出/赎回/其他资金动作 | 指定 market/route/合约、有限 ERC20 额度；ERC1155 合约级权限单列 | SDK 能力已有，但不是全路线批准；不自动 approve |
| 外部告警、长期调度、生产 Mongo/schema | 指定目标和副作用，另行确认 | 本轮均不执行；本地故障信号不冒充外部已送达 |
| alpha | 与执行成本相称的独立研究证据 | NOT_PROVEN；本项目不是收益改进实验 |

## 3. 目标与非目标

### 3.1 必须目标

1. 同样已批准的 BTC5m 输入、状态、时钟与参数，在允许来源的公共子域中，paper/live 的概率、方向选择、净 EV、重验及拒绝同义。成交路径不同，不要求真实成交量/费用等于 paper 模拟量。
2. 原执行器实际 gross/net/cash/fees、已签 hash、未决剩余、账户对账与 final 可逐事实审计；明确 accepted、matched、settled 与已赎回现金不是一回事。
3. 有人值守可做受限工程首单或策略 pilot；无人值守必须再覆盖互斥、故障、冷启动屏障、告警/接管及资金回收暂停。不能只做一个永远拒绝 live 的 stub。
4. 原 100 USDT 本金方案、2 USDT 单笔及单市场、10 USDT 总成本/未决预占、20 USDT 停新增保留。窗口、浮亏、Gas、未兑付和未知分别可解释；20 不是保证最大损失。
5. 独立 Validate 仅离线；以后真实小资金验证单独授权、单独记结果。

### 3.2 非目标

不做混合模型、动量、OBI、校准/参数/fee 公式优化、主动退出新策略、maker、Kelly、杠杆、第二 core/Broker/账本/OMS/runner、钱包或认证改造、自动重新签名/补单/解锁、无限恢复、跨主机 active-active、自动全路线 approve、自动赎回平台。当前不做认证/私有查询/链上刷新/真实签名/下撤单/资金/生产 DB/schema/服务/调度/权限/profile/依赖变更或 commit/push。

### 3.3 有限替代关系

本轮获采纳且实现验收后，仅对显式 07-007 候选：替代 07-005 §2/§4.7 的“phase1 仅 unsigned / signed legacy”，替代 07-004 及 07-005 的“signed final-only/null”，扩展 07-002 §4.5 与 §4.bis、07-004 §4.7 的“无跨进程运行保护”到可检验的冷启动拒绝屏障。不是追认旧合同能力，不改判旧 FAIL，不迁移或回填旧事件。

其余经济模型、单轮一次、资金/时间/官方结算、signer 安全、SDK 语义继续继承。07-006 observer 仍 unsigned-only、默认 OFF；v1/v2 历史语义及当前 run 不改。旧文档不批量回写；本节是显式增量优先级。

## 4. 整体方案与最小依赖决策

唯一链仍为固定 control → 原 Rust RoundTaker/DecisionCore → 原 Broker → PredictFunTrader；SDK 只做原资金工具，不进入策略热路径。新事件是 Broker 原状态的投影，reader 只审计，不能产生可交易余额。phase1 状态不得继续以 PaperCash 是否存在作为 live 准入依据，也不能给 live 注入虚拟 100 现金。

持久化默认 Mongo，已定向核实依赖：BOT Cargo.toml及tools/predictfun/requirements.lock无Mongo driver，BOT专用venv的pymongo元数据为NOT_INSTALLED；但项目`.venv/bin/python`已有pymongo 4.17.0、eth-account 0.14.0、jeepney 0.9.0。以上仅importlib.metadata读取，不导入业务模块/凭据、不连接数据库。项目MongoWriter虽有pymongo，却import即load_dotenv、默认写portfolio_position，普通upsert不提供运行fencing/交易前写障碍；LocalMongoAdapter限定03_data_ud_*且catch-and-log，不可直接套用资金安全存储。

据本任务允许明确fail-closed冷启动，本轮选择recovery_policy=COLD_START_REFUSE：原launcher复用已有项目Python依赖，单host OS互斥 + Mongo中同账户一次性ARMED拒绝屏障，非订单恢复账本。屏障在signer/child前以唯一scope主键创建、取得持久写确认并同目标读回；崩溃后连新run_id也拒绝，正常结束也不自动解除。同进程继续使用原LiveState和完整事件审计，不从文件/Mongo重建可交易余额或自动续跑。不新增SQLite、driver、包、服务；SDK资金工具仍沿其原专用环境。当前Mongo仅设计及fake存储消费者，不做生产连接/写入/schema操作。

T2须冻结原launcher的最小lazy存储接缝、项目解释器与原signer兼容验证、单文档唯一/耐久/读回语义及人工接管。未来实际库/集合绑定必须明确批准，本文的逻辑LiveRunGuard不是声称现网有同名集合；不用portfolio/UD集合、不擅自建生产集合/索引。缺连接绑定、driver、持久写确认或一致读回均拒绝live，不fallback文件/易失内存；不因缺条件自行安装或改变Mongo部署。若以后要求自动跨重启恢复，再对Mongo扩展必要恢复合同，不把当前屏障冒充完整恢复层。无需把已可收敛的方法选择退回用户。

## 5. 业务决策

### 5.1 经济 parity 与授权隔离

继承 07-005 的净份额 EV / gross 分母、模型/参数、20 returns、source epoch、5/10 秒时效和30秒入场界限。unsigned 仍可 Coinbase 降级；signed 仍 Binance-only，并标明预测源并非官方结算流。只在共同允许输入域比较经济 parity；Coinbase 在 live 被拒不是模型漂移。

live 在等待账户/盘口/授权/签名/认证之后、第一次可能 POST 前，以现有 core 对最终签名约束和最新检查时钟再验，不让旧候选穿越期限/停止边界。交易已经可能发送后，仍消费同 hash 的全部实际事实，不用 EV 或30秒门槛拒记晚到成交。未知闭锁与费用事实保留优先于漂亮报表。

### 5.2 风险窗口与现金

窗口绑定一次明确授权实验的 risk_window_id，不按 UTC 日、换轮、退出/重启或 run_id 重置；开始即固定本 run 冻结的 C0 分配预算（受控 run 取 `controlled_run.budget_usdt`；无该字段的历史/legacy 记录为 98 USDT，早期 V1.0 示例 100 仅作历史），真实可用额必须另读证实。没有充值/提款自动扩大预算。R+U 的 USDT 口径含实际交易费及浮亏；mark 无效/费用或未决现金未知即停新增，不能以零填绿灯。净额已含费不再扣一次。

原生 Gas 用 BNB 原子量单列，未知不是0；20 USDT 不含未获币种转换依据的 BNB，不宣称全成本损失封顶。以后真实授权须明确 Gas 支付地址、可消耗 BNB 预算/停止条件；不能临时猜汇率把 BNB 加 USDT。官方赢/平价确认可产生兑付权，但未读回实际 USDT 到账不成为可用现金，不拿 paper 结算回款证明 live 周转。

### 5.3 有人/无人值守与恢复

有人值守首单只要求该单原消费者事实和预批准退出闭合，不以前置自动赎回或无人值守全能力阻塞。有人策略 pilot 要求本轮经济 parity 和完整 live 输出；有人在场不能用 null final 签通过。现行 activation 时长按同一 mode-aware 判定：`supervised` 为 `0 < duration <= 6h`，`unattended` 为 `0 < duration <= 24h`；等号允许、超限及未知 mode 拒绝，controller、guard、metadata 三入口一致。

现行总敞口是已存在的成本加未闭合预占：`cost + reserved >= 10 USDT`（含等号）即复用黏性 stop → 有界安全收尾 → 原 drive 返回，不空转、不自动重启；仅拟新增单会使合计超限时只拒该候选，不把尚未产生的订单算成实际敞口。沿既有安全 reason/detail 表达 `MANUAL_STOP / TOTAL_CAP`，保留原先停止原因、20 USDT loss latch、在飞/未知订单、unresolved 与接管信息，不宣称退出就是平仓。paper 交易语义与现行 98/1/1/10/20/allowance100 不变。

启动完整核验及无R18基线资格对象的严格解释中，history-only 仓位仅在最新官方结果明确包含目标 token、Yes/No token 对与历史 known 市场的侧别绑定一致，且沿原 settlement 判定得到 RESOLVED/CLOSED、非 contested、payout=0 时解释归零。同 market id 不足以证明身份；缺失、替换、互换或重复/额外 outcome 均 fail-closed，且不得污染后续读取的已知 token 绑定。平局与正兑付只在官方结果已确认、且该 token 的 claim 按 inventory×payout（1e6/5e5）逐 atoms 与持仓精确相等、budget+Σclaim 逐 atoms 等于观测 collateral 时可解释为已收到；未确认、矛盾、未结算、额外持仓、数量不符或任一 atom 差异仍拒绝解释，不新增请求种类或客户端。启动已完整核清且仍满足R18资格的旧记录在同run后续观察复用原解释，不再重读其官方结果或重计旧claim；当前账户事实及本run新claim继续原fresh读取与现金核销。

无人值守本轮定义为“获限额限时的一次进程内运行，异常停新风险、无人自动重启”。成功首启和至少两轮不同市场的离线正路径必须可走；无风险后健康进程可继续，不能用全拒绝满足验收。异常/断网/关键输出失败/父失联/期限均停新增；允许有界同订单查询和已授权取消，不自动卖出/approve/转账。冷启动永不自动恢复；人工必须核对全部未知 hash/风险窗口损失及官方资金事实，新 run 不能抹掉旧 latch。

资金回收选择 MANUAL_PAUSE：首个需要回收的已结算持仓进入 WAIT_CASH，停止新增并告警，保留待兑付资产；人工另按原 SDK 或官网确认现金回读。不支持自动连续复投，不能把此能力命名为全天候自动赎回系统。未来如明确批准自动回收，仅可按既有 SDK 限定 route/target 承接，须另有可验证合同。

### 5.4 告警与证据

使用现有 supervisor 输出本地、固定 code 的停手/人工接管事件与非健康退出；无自由异常/raw响应/secret。告警投递失败也停新增。当前只离线 fake 告警接收者；未来无人值守实测须明确由谁在何处收到并接管，外部发送需另授权。拒绝屏障/缺结束证据保留异常，不靠告警成功代替账户对账。

## 5.bis 持久化、隐私与回退

| 数据 | 介质 / 边界 | 生命周期 / 恢复 |
|---|---|---|
| 受控启动/实际执行/结束证据 | 原新 run 目录的严格分版 JSON；只选白名单事实 | exclusive-create / 校验后追加，无 TTL/覆盖/补造/自动迁移；不是恢复可交易账本 |
| 同账户 live 拒绝屏障及 OS 锁 | 默认Mongo逻辑LiveRunGuard，同账户scope唯一主键；实际库/集合绑定以后批准，OS锁由T2冻结本host精确路径 | 启动前持久创建/读回，不按退出自动删除；无金融快照恢复；人工核对后另授权轮转，原屏障留档 |
| 风险、订单状态 | 唯一 Broker 内存；公开投影到上述事件 | 崩溃后 UNKNOWN/RECONCILIATION_REQUIRED，不重建100、不续签 |
| 未来完整恢复 | 默认Mongo；当前只有拒绝屏障契约，非自动恢复账 | 若需要再最小授权；本轮无DDL/DML/连接，不替用portfolio或UD集合 |
| secret | 仅原 keyring/内存/匿名管道 | 私钥/API/JWT/签名字节/RPC敏感URL/环境不进事件、屏障、报告或任务 |

chain/account 的固定公开绑定只记录其工程公开身份（L1）；官方公开行情 L0，与交易关联按 L1 管理。最小订单 hash/金额为授权范围内 L1 受控工程证据，不批量导出账户隐私。无 L3 落盘。data 被忽略不等于远程备份；回退是停止候选新增并保留原事实，不删除屏障/unknown/latch，不恢复旧 live binary 继续同预算。

## 6. 实现与正在运行候选隔离

当前 btc5m-baseline72-002：2026-11-19 12:12:10 至 2026-11-22 12:12:10 Asia/Shanghai；launcher56913/child56964，session proc_92911e09ac5f。受保护 binary=`data/reports/2026-11-19-btc5m-observer-runtime-fix/evidence/validate-v11/cargo-target/debug/polymarket-toolkits`，SHA256=`09ac37334c644c354c5565e5da3e3836815c14bb03161c44386966efaf91eca0`；control/observer/publiccfg 身份沿卡面原运行值保留。

T2 必须先区分已加载 Rust binary 与可能被当前 supervisor 以后动态导入的 Python 源码。优先在原 fork 源码工作、所有构建显式独立 target-dir，离线测试使用候选隔离配置/证据。会被当前 run 动态加载的源码在 paper 完成前不得编辑；必要等待，不改其加载行为、不用重启解冲突。不覆盖旧 target/binary/evidence，不变更当前环境/期限/配置/进程，也不重复启动 paper。旧14日 M0/M1/M2low/M3joint 冻结清单、参数、原研究制品逐项保护，不看中途评分。

本卡只新增两份文档。T2 才给原 BOT 内精确 allowlist、G3、最终源码映射与隔离验证命令；module 单测 colocated，主仓 tests 仅集成。禁止全仓重构、修改模板、依赖升级或 git destructive 操作。runtime 安全拒绝停动作及依赖分支，不换包装/工具/worker重放；可选诊断 OMITTED 不代替必需验收。

## 7. 风险与应对

| 风险 / 不确定性 | 应对 / 停止边界 |
|---|---|
| paper/live 相同模型不保证实盘成交和收益 | 同 core 对拍经济决策；实际成交单独核算；alpha 未证 |
| accepted/FILLED/settled 名称误当现金 | 数量、核算、链结算、兑付和提现现金分别证明 |
| cancel locked 或 late fill | removing 风险持续，原订单同 hash 查询；取消成功不释放至零 |
| 输出写失败、进程死于 hash/POST 边界 | 已持久拒绝屏障使冷启动停手；当前事实未知保留，不自动重签 |
| OS 锁只保护本 host 合作消费者 | 不宣称分布式/同UID安全隔离；真实授权指定账户独占，其他 host/非受控客户端不在可保证范围 |
| Gas、跳价、已发订单继续成交 | 单列费用与未决；20 是停止新增阈值，不能保证亏损封顶 |
| 人工回收慢、告警不达 | WAIT_CASH/STOP_NEW_RISK；不拿未兑付占用继续复投，无限恢复非目标 |
| 当前 paper 动态加载被污染 | 设计先隔离；不能隔离就等待到期，不动当前消费者 |

## 8. 备选方案

- 复制 paper core 到 live / 用 Python 决策下单：不选；违反唯一 Rust 模型与执行链。
- 直接令 live=true 或把 live 当 paper 现金：不选；绕过真实净额与未知风险。
- 给BOT专用venv增Mongo包、Rust driver、SQLite journal或新服务：不选；项目venv已有必要包可复用，本轮Mongo单文档拒绝屏障已满足最小冷启动模式，无须自动恢复账本。
- 全自动跨重启恢复/持续赎回：后续明确需求再做；不作为有人首单前置，也不冒称本轮已实现。
- 完全禁 live 然后宣布安全完成：不选；必须有离线可走的健康正路径及故障负路径。

## 9. 验收标准

按 SPEC §5 A-001–A-024 执行。核心是同核心决策、最终可能发送前重验、原实际执行增量、严格 live writer→supervisor→首次持久化→reader、互斥/冷启动/故障/人工回收。所有测试为离线 synthetic/fake transport/clock，不能以 fixture 冒充真实成交；不以盈利/成交数/新在线时长作为工程门槛。只重测本轮受影响路径，仍适用旧独立证据绑定身份后复用。

## 10. 落地与交接

T1 两文档静态一致性/引用/范围/hash → 主控 Gate → T2 独立 Design → Implement → 独立 Validate → 主控 Closeout。三独立文件到 Design Gate 必须齐备，但本阶段不得提前写 Design。唯一后续验收报告为 `data/reports/2026-11-19-btc5m-live-parity-and-operations/report.md`，必要原始 evidence/；本卡不写结果报告或任务镜像。之后主控分别申请有人工程首单、有人策略 pilot、无人小额验证；本卡不创建或启动任何真实阶段。

## 11. 开放问题

业务契约无须猜测的未决项。复用项目已有pymongo并选择“Mongo拒绝屏障、不自动恢复”，不要求用户为此选包。Design必须落实锁路径、Mongo逻辑映射/待批准部署绑定及耐久顺序、最终发送检查hook、typed live wire/schema与原字段映射、准确文件范围/G3、人工核对入口、隔离动态加载及可执行测试。真实账户/Gas预算/期限/告警接管/退出及生产Mongo部署授权是未来启动输入，缺失时live不启动，不阻塞本卡离线文档交付。

## 12. 来源

- [07-002 SPEC](../../spec/07_trading/SPEC-07-002-predictfun-live-foundation.md)、[Design](../../design/07_trading/DESIGN-07-002-predictfun-live-foundation.md)：actual facts、unknown、SDK。
- [07-003 SPEC](../../spec/07_trading/SPEC-07-003-predictfun-wsl-nonexport-signer.md)、[Design](../../design/07_trading/DESIGN-07-003-predictfun-wsl-nonexport-signer.md)：安全 keyring / 固定消费者。
- [07-004 SPEC](../../spec/07_trading/SPEC-07-004-btc5m-controlled-paper.md)、[Design](../../design/07_trading/DESIGN-07-004-btc5m-controlled-paper.md)：资金、期限、监督、SDK接线。
- [07-005 SPEC](../../spec/07_trading/SPEC-07-005-btc5m-phase1-correctness.md)、[Design](../../design/07_trading/DESIGN-07-005-btc5m-phase1-correctness.md)：phase1经济/clock/候选及v2。
- [07-006 SPEC](../../spec/07_trading/SPEC-07-006-btc5m-post-entry-observer.md)、[Design](../../design/07_trading/DESIGN-07-006-btc5m-post-entry-observer.md)：只读观察与水位，不扩 live。
- [当前源码线索评估](../../../data/reports/2026-11-19-btc5m-live-and-hybrid-assessment/report.md)：含2026-11-19官方公开规则链接；本卡重新静态定位源码，不把报告当实现答案。
- skills/data/data_interface/mongo_writer.py:9–21,31–53,69–109；skills/data/unified_data/local_mongo_adapter.py:8–33：只读核对依赖/职责，不导入、不读取凭据、不连接数据库。

历史参数化修订 V1.2：t_298e36df / Pascal Light；其参数化契约继续优先于历史固定示例。本轮RFC/SPEC V1.18 §R19仅冻结③需求；①②按R19.1复用已验未部署基线。R18及旧阶段状态保留各自历史时点含义，不覆盖本轮元数据；R17及既有行为不变，③无实现/验收或生产放行。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.18 Design指针同步 | 2026-11-26 | t_edbfef11仅把对应Design/阶段元数据机械同步为V1.18 §R19.1–R19.9；下方RFC/SPEC阶段历史记录保留，R19需求语义及D19验收不改，Implement仍须主控Gate。 |
| V1.18 | 2026-11-26 | R19仅③RFC/SPEC：复用①②已签收未部署基线；冻结原REST脱敏计数、显式route/bucket/caller、单进程APP共享预算/头部权威性、多窗/并发/取消/429reset、controlled首次poll同步准入和D19-01–08。Design仍V1.17 R18、③待下一阶段；不改代码/测试/阈值/生产状态，不冻结④。 |
| V1.17 | 2026-11-26 | R18仅第①项：依Pascal决策冻结启动完整核验、已最终结算且现金账务核清的同run内存历史基线，免周期重读旧订单详情及官方解释；保留fresh当前账户、全分页matches/已知冲突保护与本run结算。替代未实施TTL及永久不可修订/全字段逐轮修订检测前提，同步SPEC资格和D18验收；仅两文档，无代码/业务实测/生产变更。 |
| V1.16 | 2026-11-24 | R17 Light窄修订：已知accepted完整事实与真实缺失分责，签名expiry及固定双时钟120s尾查、保留原Final/风险与硬stop；仅三文档增量，无源码/业务运行/上线。 |
| V1.0 | 2026-11-19 | 冻结live经济parity、实际账务证据、两种值守及最小冷启动拒绝/资金回收边界；研发与真实动作分离，保护当前paper和冻结研究 |
| V1.1 | 2026-11-22 | R2 窄纠错：§5.3 明确 supervised≤6h/unattended≤24h 共用判定、实际 cost+reserved≥10u 黏性停止并原 drive 安全返回，以及最新官方/历史 token-side 严格一致后才解释零兑付；不改经济额度、paper、事件版本或运行授权。 |
| V1.2 | 2026-11-22 | 公开 run JSON 参数化（Light）：新受控入口以 controlled_run={budget_usdt,duration_seconds,operations_mode} 与本 run 的 order/limits 冻结全 run 金额与时限，C0/loss/caps 取本 run 值；legacy 缺省与历史记录保持原值。不新增经济授权、真实交易许可或恢复语义。 |
| V1.3 | 2026-11-22 | R7 Validate 文档校正（MINOR-1/2）：§5.2 C0 改为取本 run 冻结预算（legacy 98，早期 100 仅历史示例）；预算/caps 行号指针更新为 live.rs:746–754、taker.rs:419–436、live_control.rs:386–395；常量/上限指针一并校正为 live_accounting.rs:30（MIN_ORDER）、32（BUDGET_C0）、34（MAX_ORDER）、38（MAX_TOTAL）、40（MAX_LOSS），taker.rs:429–436；不改代码/额度/授权语义 |
| V1.4 | 2026-11-22 | R12 窄修订：预算须逐 atoms 等于启动时观察到的 collateral（budget_usdt 支持≤18 位小数的十进制字符串、按 atoms 精确映射，不截断、不容差；±1 atom 即启动前 CASH_BUDGET_MISMATCH 拒绝）；不改经济公式、额度、授权或运行语义 |
| V1.7 | 2026-11-23 | R13 窄修订：确认的正兑付 claim 在官方结果已确认后，按官方结果的 claim_value_atoms 与已兑付份额核对；claim 未确认前不入账为现金 |
| V1.8 | 2026-11-23 | R13b 窄修订：官方结算先到、精确 claim 后到的顺序下，本 run 内允许把该精确 claim 清回 READY；差 1 atom、结果未确认、foreign token 仍停窗 |
| V1.9 | 2026-11-23 | R13c 窄修订：claim 先判定后入账（账户读回只记为已证明待兑付，已确认官方结果逐 atoms 精确相等才入账为现金）；canonical reader 与 Rust 侧对同一合法流给出一致结论（已兑付持仓不进终态 positions、reader 观察 CASH_CONFIRMED 后不再视为停窗） |
| V1.10 | 2026-11-23 | R13d 窄修订：reader 收到 payout `CASH_CONFIRMED` 且该等待由 `CASH_PENDING` 造成时同步解除 `stopped`（其它原因停止仍黏性，并以 producer→reader 双用例覆盖续单与反例）；逐 atoms 预算门等指针改为符号锚定（`seed_predict` 的 `cash_matches_budget_and_claims` 不等即 bail `CASH_BUDGET_MISMATCH`，行号仅辅助）；移除 `live.rs` 未使用的 `cleared_waits`；不改经济、额度或授权语义 |
| V1.15 | 2026-11-23 | R16 T1：对齐 R15/R13/R14 已验基线；冻结兼容拒绝诊断、R15 三 minor 闭合、本 run 精确 claim 与600s/deadline有界 WAIT_CASH 续驱动及新测量/验收定义。仅 RFC/SPEC，不表示实现或部署；R15 原卡历史结论不变。 |
| V1.19 | 2026-11-26 | R20 RFC/SPEC按Pascal最新范围冻结：仅非原子现金逐腿floor候选与原settled逐atoms核对、双消费者及D20-01–02；撤回本卡未签收的expiry/市场终态新闭合分支；Design/实现/独立验收待下游，不授予重启。 |

## R20：冷启动 NON_ATOMIC_CASH 的最小现金计算修复（2026-11-26，需求冻结）

### R20.1 当前修订、事实与有限替代

本节及 [SPEC-07-007](../../spec/07_trading/SPEC-07-007-btc5m-live-parity-and-operations.md) V1.19 §R20.1–R20.7为本次现行需求；旧尾注和旧版本行保留其历史阶段含义。对应 [DESIGN-07-007](../../design/07_trading/DESIGN-07-007-btc5m-live-parity-and-operations.md) 当前仍V1.18 §R19，R20由既有下游t_0722b40a落实。本节按Pascal最新授权收窄本卡未签收的R20草稿：仅修cumulative及必要直接调用点，不重构/重命名/迁移，不新增模块、运行时、框架、配置或错误码族；不新增闭合证明分支。

事实源：[根因报告](../../../data/reports/2026-11-26-btc5m-history-not-closed-root-cause/report.md) 及同目录 `evidence/venue-order-matches.json`、`chain-orderfilled.json`、`root-cause-arithmetic.json`、`poststop-read-{1,2,3a}/summary.json`。run `btc5m-live-4d633f8696984a73` 的 Accepted 订单 `0x48a26f35ecf5651d1409958c7fc0aacd2f453c621ed9b0213bce6f6a2d06baef` 有两腿真实成交；现金 `999399999999999999`、gross shares `2629999999999999999`、share fee `52599999999999999`、net shares `2577400000000000000` 均为 atoms，现金币种 USDT。原声明移除后变为 UNEXPLAINED_HISTORY，不能删声明逃避该成交。

静态源码及保存的整数重放证明：两腿输入会在`fills.rs::cumulative`的非零余数拒绝分支失败，经`read_order_execution`错误降级进入`startup_history`的HISTORY_NOT_CLOSED/native exit 4。原生记录只捕获外层错误，未捕获原生细粒度NON_ATOMIC_CASH，故这是源码+数值定位，不是排除所有并存条件的运行追踪。同时，正确CTF Exchange的`getOrderStatus`为`(false,1)`，不是链上关闭；另一neg-risk路由`(false,0)`与本单无关。市场RESOLVED/CLOSED、任务给定签名已过期均不升级为Final证明。

数学措辞澄清：价格 `0.38` 本身可精确编码为 `p=380000000000000000`；不能整除的是份额 atoms 与价格 atoms 的乘积换算为现金 atoms 的结果。此澄清不改变已确诊的 NON_ATOMIC_CASH 故障链，不把有效成交认作非法小数。

R20只替代“非零余数本身即拒绝”的现金计算条件；原settled其余拒绝条件全部保留。SPEC §R17.3/D17-03、closure/Final、remaining=1、签名过期/nonce/市场状态的判定一律不改。主控已核实引入来自2026-11-13 commit `0b8b310`（07-002）；今日①仅抽取startup_history文件未改语义，本卡不重复追查归因。

### R20.2 权威金额与非原子成交决策

1. 订单实际 gross cash 的第一权威为正确 chain/deployment/exchange、该账户原订单的成功 canonical 回执中的完整 ABI `OrderFilled` 金额，并须被同回执 collateral/CTF 实际转账独立印证。BUY 取 makerAmountFilled 为现金、takerAmountFilled 为 gross shares；SELL 相反。事件资产 ID/owner/hash/token/side/market 均须正确；不是任意同 tx 事件或余额变化。topic0 `0xd0a08e8c` 仅是报告中的前缀，不能据此取代完整 ABI topic 校验。
2. 第二层为官方明确给出的逐原子结算金额：若存在，必须与上述链上事实精确相等；冲突即拒绝，不能按优先级静默覆盖。当前 `ApiLeg` 只有 amount/price/fee，没有独立现金字段，不虚构该字段、接口或新 provider。本次不增加无链证明的官方现金 fallback。
3. `q*p` 的整数商仅为报价导出的核对候选，不是支付事实。令 `S=10^18`，逐腿宽整数 `q_i*p_i=S*f_i+r_i`、`0<=r_i<S`；有成交时必须计算 `f_i=floor(q_i*p_i/S)`，保留余数含义，不用浮点、不四舍五入、不先合并余数再 floor。`r_i>0` 不是非法成交；`r_i=0` 也不能豁免链上证明。候选金额与实际金额必须分清来源，未验证候选不得以 Known 支付/可用余额对外使用。
4. 本次支持当前精确十进制报价及逐腿floor规则：原settled逐tx检查本单有效腿`sum(f_i)`与事件现金精确相等，gross shares/fee相等，并核对实际转账净额。全部通过后，数值已被权威实额印证，允许沿原字段/数据流记账；不要求新增事件金额存储、改变settled返回类型或重构数据流。无唯一腿对日志映射时沿原同tx完整集合比较，不虚造配对、不跨tx抵销。差任意1 atom仍拒绝；来源规则不符时不得反改候选求等。
5. 只允许“计算 floor 候选 → 原独立链核对 → 以链上实额记账”；禁止仅删 NON_ATOMIC_CASH 后把 floor 直接视为精确实额，禁止链上值同时充当唯一 expected/actual 而取消报价/数量/费用/转账的独立核对。缺 tx、receipt、fee、完整分页或数量稳定性时保持 Unknown/Unproven，冲突沿原拒绝路径；不得报零、完整或释放风险。正常完整零成交沿原零账务规则，不伪造空 OrderFilled。

真实两腿的 `(f,r)` 分别为 `(132822872628722271,600000000000000000)`、`(866577127371277728,20000000000000000)`，对应链上现金逐 tx 精确相等，因此不能仅因余数而拒绝。把任一 tx 现金增/减 1 atom、把 fee 或实际转账增/减 1 atom，都必须不完整/拒绝。另有合成边界：两腿各 `q=2,p=380000000000000000` 时逐腿 floor 合计 0，合并后 floor 为 1；只能取前者作候选，但这不宣称该微量交易获准实际下单。

### R20.3 闭合语义完全保留

Final 仍表示本单最终可记账成交数量已封闭且不能再产生新增执行，不表示“requested 全成”。实际历史接受仍须 `pages_complete && accounting_complete && closure==Final`；请求数量不补齐、净库存不抹零、未执行余量不记作成交。原完整 FILLED/终态+固定块过期/正确路由关闭或 nonce 失效的合法分支保留，不对一般订单新增市场终结前提。

不新增expiry+市场终态联合证明，不把OPEN过期、remaining=1、市场结束、零仓、min_net_shares达标或金额吻合变成Final。原`closed()`与`read_order_execution`的组合判定原样保留，精确分支复述见SPEC §R20.5；完整成交或原合法终态证明仍可按既有规则Final。算术修复后若原关闭证明不成立，历史读取仍以HISTORY_NOT_CLOSED拒绝，属于预期结果，不是放宽闭合的理由；OrderFilled成功只证明该部分成交，不证明整单或当前账户闭合。

### R20.4 双消费者、不变项与验收

`btc5m_reconcile` 和交易二进制共享原 crate：必须共同采用同一金额来源、floor 核对、费用/净额、closure 语义，并从同一候选源码重建两者；源文件/二进制身份、原 selector/pin 的一致性由 Design 落实。不得只修 reader、只修交易子进程或用旧 reader 配新交易 binary；未完成双消费者核验不能认为冷启动链修复已交付。

不得放宽 `settled()` 的回执成功、transactionHash、canonical block hash/number 与固定块界限、每条 log 的 removed/tx/block/logIndex 身份、完整 ABI topic/emitter、实际 USDT/CTF 转账、事件金额/资产/fee 及净额核对；身份/代币/市场/路由绑定、分页/数量稳定性、未知历史 hash、预算/损失/敞口、10s 新鲜度、Final/风险释放条件、sticky stop、fail-closed takeover 均保留。只读修复不签名、不下单、不撤单、不补余量、不 claim/转账、不写 DB/guard/activation、不变更长期调度。

可执行验收收窄为SPEC §R20.6 D20-01–02：至少一个非原子正例与一个链上现金错配反例，复用已有测试文件/Scenario，必要边界在同一用例参数化，不新增平行框架、不扩大套件时长；既有回归按受影响路径复用。正例必须区分结算通过与历史Final；不得强迫真实remaining=1历史成功。实现者自测与独立Validate分开；本卡只做文档静态核验，不声称Rust测试或账户修复PASS。

### R20.5 风险、阶段与授权分离

本次算术修复需求closed、范围内open为空；独立未决事项为真实历史单Final及旧窗口恢复资格，均不阻塞本次最小修复，也不授权实现者解决。Design只落实最小调用点、精确allowlist/G3、既有Scenario和双binary身份；如需新增模块或改closure才可实现目标，先停止报告缺口/最小选项，由Pascal裁定。需要重建两二进制时沿用原命令并保留`--locked --offline`，不覆盖已发布旧制品；本卡不构建。

旧窗口 OUTPUT_INVALID 已由独立事项修复验收，见 [报告 §12](../../../data/reports/2026-11-26-btc5m-execution-facts-output-fix/report.md)；不修改 Python 观察者或重做该问题。本卡/后续工程修复通过均不等于可重启：仍须原受控入口 fresh 双读、独立验收、主控明确核对；旧窗口恢复资格另行裁定，旧 stop/guard 不解除。Pascal 对修复的同意不变成交易/生产写入授权。本阶段无账户/API/凭据访问，无 Design/代码变更，无真实或模拟交易。
