# DESIGN-07-007: BTC5m live parity 与有界无人值守运行

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | V1.16；R17 Light Principal delta 已冻结，待 Implement / 独立 Validate；静态检查非修复或生产放行 |
| 本次窄修订 | V1.16，2026-11-24：§R17 仅生命周期等待、签名expiry seam、固定预算及G3最小提取；旧R16和历次范围仅为历史，不叠加授权 |
| 作者 / 创建 / 更新 | YQuant Principal；2026-11-19 / 2026-11-24，Asia/Shanghai（UTC+08:00） |
| 来源 RFC | [RFC-07-007](../../rfc/07_trading/RFC-07-007-btc5m-live-parity-and-operations.md) V1.16，§R17 |
| 来源 SPEC | [SPEC-07-007](../../spec/07_trading/SPEC-07-007-btc5m-live-parity-and-operations.md) V1.16，§R17.1–R17.4 |
| 来源任务 | 本轮 t_7987b726；旧R16 t_5f6833d4 / t_3691ff23 / t_ea1ed5d7 及历次修复保留历史 |
| ROOT | /home/pascal/workspace/yquant-investment |
| BOT | ROOT/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits |
| 后续 | 本卡仅三文档delta；完成后kanban_complete交接既有下游Implement，再由独立Validate验收，不另建Full链/同卡review，不自动解锁旧卡或启动交易 |

历史 V1.1 Amendment 记录（非本轮 source pointer）：RFC V1.0 SHA256=`38356736b1132689a276be720eed9ff1cd9c009d3d02a0342f9e595f8f8d8416`、SPEC V1.0 SHA256=`12f8afda7b29026fe9139d49024a92b096a91b7b96411a94718de49cb114d873`当时重新核对一致；原 Design V1.0 SHA256=`58562e2b78c606467b2d8ca60e67493fec49592371857ae85d53aa75c7f2ec49`为当时基线。V1.1只细化内部模块/测试，不升级wire。本轮 source、身份与范围以下节为准，不能把历史未完成清单当R16重建授权。

## 发送前保守 edge 预检与候选级拒绝增补（2026-11-25，Pascal明确授权）

本节为用户本次“两个事情一并优化，由主控接手”的窄行为增补，优先于历史将所有SIGNED_BOUND_UNPROVEN笼统硬停的表述，不重开R17/结算/接管工程，不修改最坏资金或份额证明。分开“证明缺失/矛盾”与“已证明约束下经济性不合格”。本节不是已测试或生产放行结论。

1. 仅受控PredictFun live候选进入原下单准备时，在本候选RESERVE/sign/POST之前，用已有冻结gross数量Q、候选fee_rate_bps、candidate.fair、候选限价下原reservation现金A与原min_edge，按最终保守检查相同整数公式预检。N_min=Q-floor(Q*b/10000)；V=floor(N_min*fair)沿原exact_floor_mul；所需利润原子量沿原cash_at_limit_atoms(Q,min_edge)。仅V-A>=所需利润才继续；经济性不通过跳过候选、无attempt/预占/签名/POST，不停止窗口。预检是原live Broker准入，不修改共享core/paper模型输出及初筛fee模型，也不保证之后账户/时效/真实签名检查通过。
2. 原guard所有身份/hash/数量/fee/route/签名/receipt/generation/风险检查必须先通过；已证明且正的N_min下，仅经济性不合格、阶段仍为发送许可前的Candidate且原attempt仍Prepared/NotSubmitted时，使用原typed CandidateRefused/封闭INPUT_CHANGED，诊断保留EDGE_BELOW_MIN。沿原release_not_submitted仅释放自身预占、保留hash/tombstone及审计，清本候选，不stop、不takeover，下一原tick产生新candidate再评估；不重试旧candidate。
3. 在Window/send-permit或may-have-submitted/unknown/已发阶段，不扩大软拒绝；无法证明bound、零/非法数量、fee/route/identity/hash不符、算术或取时错误、账户异常、ACK/输出/父失联、loss latch等继续原硬保护。不能仅凭NOT_SUBMITTED或字符串包含edge把其他错误降级。不撤销已有stop，不重启旧run。
4. 共享小函数只复用已存在的minimum_net_shares/exact_floor_mul/cash_at_limit_atoms整数规则，预检和最终guard共用经济性判断；费率签名域原cap、min_edge=0.03、min_secs_left=30、10s新鲜度、预算/敞口/损失阈值、allowance、R17等待/Final、结算及接管均不改。
5. 原生回归分别证明：真实core合格但保守不足的历史参数候选在原Broker预检0sign/POST/RESERVE且运行继续；原guard已准备场景的纯经济性拒绝为typed候选级，Window/真实无证明仍硬错；拒绝后同一Broker/adapter/core下一新候选正常单次fake POST，旧候选不可复用。保留等号/±1atom、零数量/坏费率/身份/bound/未知发送反例，并通过原producer→Python严格reader消费。公式回算不是native RED；必须先原生RED再GREEN。

实现限定BOT原controlled.rs（小经济性helper）、taker.rs（仅准备前预检）、live_control.rs（仅已证明经济性分级）、原live004_regression.rs回归。必要原fixture最小参数化可用tests.rs/controlled/r16_fixture.rs，不新增平台/runner/schema。live_control.rs已1201–2400受控，本次仅替换原check_locked分支、职责不增，不继续堆无关逻辑；共享算法放controlled.rs以保持父职责。两binary重建至本主题新candidate-edge目录，旧制品不覆盖；原control selector及signer reader pin机械绑定、完整source身份新冻结。原shell/生产activation/guard不改，代码绑定不等于启动许可。本次Light Implement→独立Validate，0open才能离线签收，无真实账户/交易/生产写。

## 6.6 原入口已知 payout-owner 审计误停的受限交接（2026-11-25）

Pascal 已授权在原 `start-btc5m-live.sh → btc5m_launch.py --auto-prepare` 补齐本类准备。此条只覆盖已知 legacy reader 把同 market/token 的零风险未提交 attempt 计入 payout owner 导致的 `OUTPUT_INVALID / AUDIT_UNAVAILABLE`、缺 final；不是通用 audit reset。旧 run、events、ended、seed/native 均不改写；恢复证明是新 launch-attempt 的派生证据，不是原 final，不把旧 audit 标 COMPLETE。

资格必须同时满足：旧 metadata、公配置、guard candidate digest、activation、seed/native hash、初始 STARTUP 对账/C0 完整绑定；旧已保存 prefix 每条按 canonical reader 严格重放。只接受已确认的 legacy reader/controller SHA 和旧 run 冻结的 legacy 交易 binary SHA（不是当前升级候选的 selector SHA）；该历史 binary 的发送前 PREPARED 必须先落盘并获得 ACK，controller 在第一条输出拒绝后关闭输入且不再 ACK。所有 prefix attempt 必须为有完整 Final execution 的已接受经济订单，或全轨迹从未发送且 CLOSED、无 execution/venue/reserve/applied 的零风险尝试；真实经济 owner 必须唯一且全部已纳入最后完整 reconciliation 的 generation，无未决发送许可。其它 stop、loss latch、未知提交、缺页、未闭合、强杀/清理异常均拒绝。

首个 stop-output 必须完整未截断、stdout、换行且 child 正常退出，恰为 prefix 下一序号的 payout。只允许其中唯一 token 脱敏槽从该 market 唯一已审计经济 owner 派生；长度须与所记原长度一致，派生帧须通过完整严格 stage，且确有同 identity 的零风险候选可解释原唯一性失败。该派生帧不写回旧 events、不当作原始 wire，不独立证明现金到账。

下一 C0 = 旧 public C0 − 全部本窗已审计净买入成本（不是 fresh balance 拟合）。保守按全部成本检查旧及新损失阈值；不放宽任何预算/交易限额。预期历史 = 旧 native 全部 claimed_win/settled_zero + 每个唯一经济 owner 的已校验结算记录；必须精确无序多重集相等，任何新增/遗漏/重复/字段变更拒绝。两次原生 fresh reader 都须完整、分页完毕、账户一致、明确 `positions: []`、无 open、已解释历史、gas 达标；`cash − 全部已到账 claimed_win = 独立 C0` 到 atom，完整账户 facts 一致。正赔付要求 fresh 原生 claimed_win 已确认，不以 CASH_PENDING 或估计权益代替。本受限类别仅接受已审计零赔付或全额赔付，DRAW/其它比率继续拒绝，不推断新的结算语义。

只在上述证明完成后沿既有完整 guard CAS、activation drift、锁及新窗口机制交接。新 attempt 单独保存 prefix/stop/seed/native hash、派生标记、成本和 C0、完整预期历史及双 fresh hash。保留旧窗口失败事实。原 shell、双 binary/4pin、reader、guard、signer、Rust 和策略/阈值均不改；不新增 CLI/启动器、服务或自动重启。

G3：launcher 只保留原流程编排和新分支挂接；纯审计资格与预期历史推导放 `btc5m_payout_recovery.py`，无网络/凭据/子进程/业务写入。controller 只在 LIVE_PATHS 增加该 helper 和回归叶，不扩展职责。受控扩张仅用于本受限分支；下一次新增独立恢复类别前重新审查提取，不把证明逻辑持续堆入 launcher/controller。新增测试独立 colocate，复用原 native_main 假外部边界；范围由独立 Validate 审核。

验收为 Light Implement → 独立 Validate，全部正反例和保护身份通过且 0 open 才 `PASS_OFFLINE_RESTRICTED_PAYOUT_AUDIT_TAKEOVER_ONLY`。离线 fixture 不表示真实账户已闭合；真实对账与启动仅由未来用户原入口调用触发，本次研发不读真实账户、不改生产 guard、不启动交易。

## 结算辅助 GET 的账户错误出口补齐（2026-11-25）

本节是既有 R14/R16 读取失败分层遗漏的窄修补，不改变策略、账务、预算、时效或风控契约。真实 `253cedc2d9f845ac` 只保存了 `RECONCILIATION_REQUIRED / UNKNOWN`，没有底层 HTTP/body；不得据离线复现断言历史请求是 429、503、超时或资金异常。

`account/runtime_claims.rs::read_runtime_account_observation` 唯一结果出口复用 `request::account_read_error(error, "RUNTIME_ACCOUNT")`。包括官方 market/settlement 的辅助读取在内，typed HTTP/reqwest 错误沿原 ReadUnavailable → 既有固定 read-failure streak 降级，期间不新增风险；完整账户读恢复才沿原入口恢复。连续故障不重新锚定预算，超限仍硬停，已硬停不得因后续成功读解除。serde/schema 错误仍 FactIncomplete 硬停；既有 VenueError、身份/generation/账务冲突原样保留；未知非 typed 原因仍 UNKNOWN 安全硬停。不记录 raw body、URL 或凭据，不靠字符串猜测瞬态。

生产逻辑只改上述小出口；native fixture/test 只扩原 `controlled/r16_fixture.rs`、`live_control/tests/r16_cash_drive.rs`，Python 严格消费原生输出只在原 `test_btc5m_r16_integrated.py` 加用例，不扩大 `account.rs`、`live.rs` 或父模块。回归覆盖同 broker/trader/core 的成交→官方结算/到账→GET 故障→读取恢复→下一新候选单次提交，正/零赔付、HTTP/reqwest 类型、非法数据、未知原因、固定预算耗尽与重复读不重复记账。

双 binary 离线重建到本主题 `candidate-settlement-read` 新目录，只机械更新原 controller/signer 的四个 path/hash pin 及对应测试。§6.6 的 ACK 证明仍严格绑定旧 run 的三个 legacy SHA；当前新候选按现行身份/双 fresh 门单独核验，不要求它等于历史 binary，也不泛化 legacy 资格。`qualify` 去掉无关当前 selector 参数，调用点同步；旧证据与未知停机类别不改。本轮不为 `253` 的 UNKNOWN 新增交接类别，原入口仍须保守拒绝该未闭合旧窗口；离线修复不等于可直接启动。wrapper、旧 run、seed/native、guard/activation、配置及交易阈值均不改；保留独立 Validate。

## 6.9 结算辅助读取误停根因修复（2026-11-25）

Pascal批准按根因复核建议直接修复，Implement=YQuant，独立Validate保留；本节取代§6.8对category缺陷“本轮不修”的后续执行范围，不追改历史。历史4549具体HTTP仍未知，保留旧INCOMPLETE/证据、生产双binary/四pin/activation和原启动接管。仅研发修复，不含生产构建绑定或实盘启动。

在原MarketData加默认委托market的settlement_market；仅PredictFun覆盖为同一私有market读取owner的严格category模式。普通market保持可选fallback，必需结算读取的typed HTTP/transport保留至既有account_read_error；不复制解码、不以旧缓存/仅WON或LOST代替完整官方事实。official_settlement与settle_controlled_live均消费严格路径，schema/成功但缺事实/身份和份额或官方结果冲突仍按原硬停。

账户读取保留原Read streak；结算批次使用同一ControlledLiveState内独立Settlement streak，复用原120s常量/note_failure/clear_failure，无新增配置或runtime。结算批次任一typed ReadUnavailable立即结束本批且使账户receipt失效，清晰返回错误，降级期间may_add_risk=false；完整批次成功才清Settlement streak。账户成功、估值成功不得清Settlement，反向也不得清Read；重复失败保留since，等号预算耗尽停止，后续成功不解除既有sticky stop/deadline/loss。未取得完整权威事实不推进本批未处理市场结论；已应用claim仍幂等。清理阶段失败不可伪称完整闭账。

四个库存同名错误仅在既有脱敏tracing出口标固定分支、token、预期/实际atoms、固定block；category失败只记录固定操作/typed分类，不输出raw error/body/header/query。wire/公开stop枚举不变。

G3边界：predict_fun.rs现2316行只提取原market body并加私有严格开关，最终不跨2400；venue.rs1070行仅默认方法；account.rs2923行架构例外仅一行换严格调用及原position处四行分支日志，禁止在其叠算法。live_accounting.rs1263行仅原受控结算读错分派及整批清streak，保持<2400；live_control.rs1814行只增独立streak和既有构造/match，不引第二风控状态机；测试集中原r16_cash_drive.rs840行和原197行fixture及现有Python消费者，若超1200则新小叶需完整身份纳入，不挤行/删断言。live.rs不新增算法；若需诊断仅原边界调用。独立Validate审查增长原因和职责。本轮不做无关模块重构。

验收先category故障真实RED，再账户与原settle_resolved/drive两消费GREEN，覆盖market/category 429/503/transport、成功缺事实/schema、数量1atom/身份/官方修订、正赔付未burn、零赔付合法残留、双streak不互清及120s等号/幂等/超限sticky/deadline。保留同adapter/Broker/DecisionCore跨轮和Rust producer到Python严格reader；只fake外部边界。自测后独立Validate，0open才限定离线PASS；不把隔离单例或旧启动PASS当运行时已修。

## 6.8 已结算终态 INVENTORY_MISMATCH 的受限交接（2026-11-25）

Pascal批准Light并明确要求YQuant接手实现，沿原shell→launcher，不启动实盘。复用§6.7的完整审计、checkpoint/零经济尾部、独立C0、双fresh精确历史及原CAS交接；新增资格只识别已核验交易binary SHA `9e437aa8fc047bbeccc60d5895e9d3418848819e7be9b16bf080fb2b4fbd78e3`与旧88源canonical文件清单SHA `83b07c5e21547216526189db6d111b82a8b7140c4a5dd17b9394a7e9e745d960`组合，精确匹配完整审计、正常退出且无持仓/预占/未决的RECONCILIATION_REQUIRED/INVENTORY_MISMATCH终态。不修改旧UNKNOWN/legacy允许集合，不凭枚举证明历史误报或HTTP原因。

已接受且完整FINAL零成交的订单不冒充never-sent：保留其signed hash、venue/market/token、代次、完整零经济事实和声明；其quantity/gross/final/applied/fee均须为零，既无claim也不扣成本。其余正成交owner必须已完整FINAL、费用覆盖精确、官方零赔付或全额现金确认；DRAW、pending、未知或尾部新经济事实仍拒绝。所有已接受终态订单按审计次序加入下一窗口原声明，从第一次fresh起全部核验。

旧public C0减全部已审计净买入成本独立锚定新C0，损失和额度沿旧新两端限制；既有已到账claim独立计入完整历史，不以fresh余额拟合。原pinned native双读都须完整/稳定、账户gas与分页合格、明确空positions/open、完整官方历史精确多重集与现金逐atoms相等。仅全部通过才走原activation/full-schema guard CAS/单次controller；CAS失败沿原顺序可能已发布activation，但不得删除旧guard或启动child，不宣称所有失败均零本地写。历史final/seed/native不改，派生proof仅存在新attempt，旧run仍INCOMPLETE。

纯资格沿`btc5m_account_recovery.py`复用，launcher仅分派；新colocate叶进入LIVE_PATHS，发布新完整源身份。Rust/双binary/四pin/signer/reader协议、策略、shell、生产配置、category读取缺陷不在本轮变更范围。真实旧4549 prefix+fake fresh+原main和反例须独立Validate；离线通过不代表真实账户闭合或启动授权。

## 6.7 已审计终态、末次账户复核 UNKNOWN 的受限交接（2026-11-25）

Pascal授权主控直接补齐原auto-prepare，实际实现者YQuant，独立Validate保留。本节新增ACCOUNT_READ资格，不放行所有UNKNOWN，也不追认历史HTTP原因。仅支持固定已审计legacy源身份、正常退出、完整canonical审计和final、无损失锁/预占/未决/持仓，停止及ended精确为RECONCILIATION_REQUIRED/UNKNOWN、FACT_INCOMPLETE形状。

最后完整RUNTIME reconciliation必须无open/positions、账务COMPLETE/NONE、cost/reserved0、无pending。其时所有attempt须已权威FINAL且完整经济事实/覆盖/owner/结算闭合，或全轨迹零风险从未发送已关闭；正赔付必须已CASH_CONFIRMED。最后对账之后只允许相同attempt的经济字段完全不变、generation不回退的zero-delta FINAL、无candidate的EVALUATE、同一UNKNOWN stop/HANDOFF及final。每条尾execution须与该checkpoint的完整执行投影相同（除observed_at/generation），最终attempt集合/经济账务/claim不能变化。尾更新不是新的账户对账，不伪造最新generation已重对账；新双fresh必须独立证明所有声明订单、结算和现金。

旧public C0与seed/native/STARTUP互证。新C0=旧public C0−全部本窗已审计净买入成本；最后对账cash=新C0+本窗已确认赔付。新C0不含任何历史/本窗claim，fresh现金减全部已到账claimed_win须精确等于新C0。保守全成本检查旧、新loss门，不按余额拟合或重新获得损失额度。预期历史=旧native完整claimed_win/settled_zero+每个本窗唯一经济owner已确认全额/零赔付；只接受claim为0或净份额，非该两类拒绝，不引入DRAW恢复。两次原生fresh均完整、分页完毕、身份/gas合格、无open且明确positions[]、精确历史多重集与现金atom闭合，任一失败不得写生产交接或启动。

实现放新btc5m_account_recovery.py纯证明叶；launcher只在原重放收集最后完整checkpoint/tail并调用资格，在原双fresh分支复用精确历史比对和loss检查，写新attempt/account-read-recovery.json后沿原guard完整CAS/activation drift/账户锁机制交接。不改旧run/final/seed/native、双binary/4pin/signer/Rust、shell/配置/策略/门槛。不新增CLI/第二启动器/reset/服务/自动重启。旧UNKNOWN仍为旧UNKNOWN；独立证明不是旧审计成功。新叶及colocate测试进入LIVE_PATHS，controller及大测试仅机械成员迁移；launcher受控扩张只增加薄分派，不堆证明。失败矩阵、真实旧prefix+合成fresh→新窗口及原恢复分支回归须独立验收0open；离线PASS不是生产启动或账户已闭合，本次研发不调用真实账户或生产写。

## R17：订单生命周期等待与 G3 最小设计（2026-11-24）

### R17.1 已实现基线及唯一待修缺陷

按[根因报告](../../../data/reports/2026-11-24-btc5m-unproven-root-cause/report.md)及其 `evidence/causal-ledger.json`，本卡定向只读复核：`live.rs::unread_attempt`只将Closed或watermark.gross_q>0视为visible；`re_read_unread_facts`本次调用的Instant+120s结束后，`taker.rs::resolve_blocked_candidate`写FACT_INCOMPLETE。`fills.rs::BoundOrder::expiration`已经保存真实签名expiry；`SignedExecutionBound`也已有expiration，但ControlledOrderMetadata和AttemptRecord没有。正常accepted完整零成交与真正缺失混为一类，才是本轮替代目标；不改签名TTL、账户鉴权、成交策略或Final证明。

R16的cash_wait/claims/runtime_claims、冷历史与旧接管当前均已有实现；源码已见RunControl::must_end区分WaitCash、drive接cash_wait、runtime_claims与account history保护。旧接管t_84db8f46已PASS_OFFLINE_PRELAUNCH_ONLY，不重跑该已关门禁。旧§R16的planned implementation、旧缺口/候选/allowlist/入口行数、旧t_38aafb47续接要求与下文Draft均保留为历史，R17不借其扩权或重做Full。真实两轮raw status、历史固定块关闭状态仍未知；后来的六声明原生闭合不反证当时已Final。本卡只改三文档；以下路径是后续Implement的计划，不是源码已写或业务已测。

根因报告§6补证：R5 t_74460a41在2026-11-22实施UNKNOWN/0共用120s，原任务及独立验收均要求always-empty到点停机；`4b6420f6a11eb5303d1a94949037f52b866d24c3` 是次日03:31自动归档。更早run010已有约0.77s过早停机，300s TTL早已存在。因此补足的是旧问题未修完整的分类/验收缺口，不是今天launcher/reader改坏或单纯开发违约；旧卡不重开。

### R17.2 小 seam、唯一元数据及原控制流

1. 在 `service/venue.rs::OrderVenue` 增加唯一同步只读默认方法 `controlled_order_expiration(&self, identity: &OrderIdentity) -> Result<Option<i64>>`；默认Ok(None)，不触发网络/sign/POST、不授许可。PredictFun在既有fills.rs impl从 `self.bound_orders` 取原BoundOrder；要求原controlled_metadata存在（普通live不启用）、完整identity/hash/accepted venue ID与原handle匹配且expiry合法，才返回Some。None是不支持/缺证明，不用本机now/TTL造值；身份冲突用既有VenueError类型拒绝。不得给AttemptRecord、ExecutionSnapshot、AccountSnapshot或ControlledOrderMetadata增加必填expiry/diagnostic字段，不批量改初始化器。getter不承担本次读取成功证明，仍必须结合刚读到的snapshot与当前generation。
2. `BoundOrder::validate` / `read_order_execution` 已以原合约hash/maker/signer/token/side/expiration/amount双读并比对累计数量；但当前validate没有将ApiOrderData.id与accepted handle的venue_order_id比对。故仅在原fills.rs执行读取的controlled_metadata已登记且handle已accepted/有原venue ID分支，对before和after都做该原字节ID比对；不匹配沿原AccountMismatch拒绝，不能以handle复制的identity“证明”REST ID。历史/普通venue不借本修复重映射status；原submission_from_status及quantity/closure规则只读复用。
3. 新 `runtime/live/order_wait.rs` 只拥有分类/时间元数据和观察helper，不拥有余额/执行状态机。原ControlledLiveState挂一个可空OrderWait，内含逻辑键（run/window/完整OrderIdentity）、首次W0、E/P_m/T_w/T_m、last_check、最新被原消费者接受的generation、连续真正缺失的U0与耗尽标记；最初真正缺失时也记录U0，生命周期组W0/E/P_m/T_w/T_m保持None直到首次正常准入，不伪造expiry。不另存第二份quantity/cash账本。原read failure streak仍属原run，OrderWait不替代其失败原因。纯分类须看本次snapshot及原apply结果，不只看watermark；完整定义与唯一算式严格引用SPEC §R17.1/2，不能另选now+300/600或tail起点。首次入正常pending前已越120s缺失预算或原硬停，不得借后来完整读追认恢复。
4. 将live.rs内现有unread识别/有界re-read小段提取到order_wait.rs，live.rs保留原UNREAD_FACTS_BUDGET/INTERVAL、UnreadFacts及re_read_unread_facts门面以兼容原调用/测试。对正常pending，helper可返回原Resolved让本tick退出阻塞候选处理，但须先持久记OrderWait；Resolved仅“本次处理完成”，不是Final或risk恢复。真正缺失仍原120s有界读；跨helper返回的U0不能清零。sync_predict及consume_snapshot用薄hook接同一分类/预算：成功clear_failure不能清W0；旧generation不能当新成功清故障；实际Final仍由原apply_snapshot_detailed唯一应用/释放，OrderWait不调用另一份释放代码。多owner不猜选一单，沿原阻断/错误处理。
5. 原 `ControlledLiveState::may_add_risk`增加本订单等待存在/耗尽的否决；`must_end`只把耗尽/硬停当结束，不把合法pending当硬stop/WaitCash。原guard/check_caps/refresh_live_risk仍有效，clear_failure和刷新风险不得绕过等待否决。taker::resolve_blocked_candidate只维持原返回码映射并接门面，不能把Pending转换为NothingToRead后放行，也不能对每个新候选重给等待寿命。必要分派代码留原taker，不改模型、价格或签名链。
6. runtime.rs::drive仅原等待分派小hook：现金等待与订单等待分别判定，但任一为真均skip strategy/cancel-on-halt，并继续原sync/官方观察；将直接相关观察组合放order_wait::observe_wait_tick，父不再堆实现。只读future沿原wait_controlled_stop可被父/输出/deadline打断；sync_predict自己取得原operation lane，不要在helper先取lane再调用sync。State锁内准备/提交、锁外await；consume_snapshot继续原lane唯一提交。入/出read及恢复前检查SPEC固定双时钟，原hard stop优先于同tickFinal。
7. skip策略不能顺带停止必要估值。observe_wait_tick对原run.traded内本attempt绑定市场，沿既有MarketData的market/observed_books读取入口及Broker::observe→observe_controlled_live更新原mark_receipts/损失，复用原identity/receipt/round规则；不制造mark、不续用陈旧mark，不新建行情源或调参。部分/晚到fill立即沿原账本应用；无合法mark依旧降级/原预算，无风险恢复。Final后完整账户check_runtime_account、mark、risk/receipt/generation全部重证，下一原tick新candidate才能沿原同core/guard/ACK/permit执行。

OrderWait只有SPEC固定E派生的两个截止，不使用运行期签名TTL查询。`P_m=W0.elapsed_ms+(E-W0.utc)`；`T_w=E+B`；`T_m=P_m+B`，B为原120s。每次使用min(生命周期截止,原deadline,真正缺失/读失败截止)及硬stop；UTC/elapsed任一先到/等号即不恢复。last_check发现回退、时钟失败或溢出沿原DATA_UNAVAILABLE，无重新anchoring；SystemClock已使用CLOCK_BOOTTIME包含暂停，无需改observation.rs。尾查在任一时钟到E/P_m后进入，但截止不是now+B；晚醒立即过期。Final或generation变化不重给额度，未闭合耗尽后finish不得另给600s/新120s风险恢复窗口，原只读安全收尾也不得将本OrderWait重新建成活跃等待。

### R17.3 后续 Implement 精确 allowlist 与 G3

以下均BOT相对路径，仅必要子集；标“新”的文件是planned而非已存在。此表取代本轮旧§R16.6/§10清单，不累加其权限。无公开交易配置、依赖、启动器行为、guard/activation、SDK签名算法、事件类型/reader生产或其它策略修改。已创建Implement卡t_fd7cc2e9另明确要求新离线双binary候选及原selector/pin身份更新；下表仅纳入这部分机械绑定及相应测试，不将其等同交易激活授权。

| 精确路径 | 唯一职责 / 修改边界 |
|---|---|
| src/bot/runtime.rs | 仅drive原观察/skip策略分派，相关观察组合委托新小模块；paper/普通live分支不改 |
| src/bot/runtime/live.rs | 原unread/re-read段提取及保留门面，sync_predict/consume_snapshot薄hook；不扩账本/旧测试 |
| src/bot/runtime/live/order_wait.rs（新） | 纯准入/固定时钟/OrderWait元数据/原只读观察组合，原账务消费者调用；不实现第二OMS/余额 |
| src/bot/runtime/taker.rs | resolve_blocked_candidate必要分派/语义注释，原Expired→FACT_INCOMPLETE、候选规则/发送链不变 |
| src/bot/runtime/live_control.rs | 注册新测试模块、可空OrderWait/原构造点、may_add_risk/must_end窄hook；原cash_wait/credit/guard不重写 |
| src/service/venue.rs | 唯一默认只读controlled_order_expiration方法及docstring，不改DTO必填形状/旧impl |
| src/service/predict_fun/fills.rs | 唯一只读getter、原执行读取前后REST ID检查/四字段日志、cfg(test)注册order_wait_tests；不迁整个执行reader/旧测试 |
| src/service/predict_fun/account.rs | 只在ChainRead::closed原小函数投影固定block time/关闭分支，保留所有证明规则、RPC及短路顺序；不扩history/账户读取 |
| src/service/predict_fun/controlled.rs | 仅必要cfg(test)现有BookTransport可见性/脚本事实接缝，支持真正缺失与完整零的区分，不改生产签名/transport |
| src/service/predict_fun/fills/order_wait_tests.rs（新，cfg(test)） | 复用既有SyntheticTransport/BookTransport/r16_fixture，小transport wrapper脚本化status、完整零/partial/matches、块时间/chain证明与真正缺失故障；native reader回归、可导出fixture供原Broker组合 |
| src/bot/runtime/live_control/tests/order_wait.rs（新，cfg(test)） | D17-01–06真实适配器+Broker/drive/原paper-live共同消费者；原producer经现有Python首写/reader/log边界的离线消费者检查，另有纯clock负例 |
| src/bot/runtime/live_control/tests.rs | 仅下方逐名迁移矩阵的必要fixture/调用步骤替换和helper可见性；同名case/安全断言保留，不净增行、不新增注册/case |
| tools/predictfun/btc5m_control.py | 仅既有LIVE_BINARY/pin/LIVE_PATHS纳入最终新候选及必要源码/测试闭包，不改supervise/log/parser/旧接管行为 |
| tools/predictfun/tests/test_btc5m_control.py | 对应最终绑定断言及D17-03/06原native producer→现有supervise/append_run_log/LiveEventStore/read_live_run小回归；复用既有native_stream/metadata模式，不手拼健康金融事件 |
| tools/predictfun/local_signer.py | 仅既有RECONCILE_BINARY/pin绑定同次新btc5m_reconcile；不改凭据/对账协议或运行入口 |
| tools/predictfun/tests/test_reconcile_failure.py | 仅若该pin对应断言受影响则同步身份预期，原故障/脱敏矩阵不改 |

G3入口已由本卡read_file工具逐文件定位：live.rs2824、fills.rs2335、account.rs2933、live_control/tests.rs3596、runtime.rs2400、live_control.rs1774、venue.rs1056、controlled/r16_fixture.rs170行（物理含空行/注释）。本设计明确处理2401–3599架构例外，不修改根G3、不授>=3600豁免：

- live.rs先同义移出unread/re-read小段、保留原函数门面，再接OrderWait hook；父最终≤入口2824。account.rs只在原closed小函数替换局部返回/投影诊断，原所有分支及RPC不改，最终<3600；不新增等待/状态/历史算法，只有必要诊断小增量，职责增长到关闭证明变化或第二专题即触发新Design。fills.rs只加getter/ID检查/四字段投影及测试注册，最终≤2400，不要求为几十行seam迁移整个reader；本轮逻辑主体已经从live.rs移到order_wait.rs，fills不承担等待算法。
- runtime.rs最终≤入口2400：只换已有等待分派，把新增观察组合写在order_wait.rs；不为压线删注释/断言/挤行。live_control.rs仅元数据/发送否决/预算hook和测试注册，保持≤2400，venue.rs保持≤1200。新order_wait.rs及两个新测试文件各≤1200，controlled.rs保持≤1200；职责扩到第二功能或达到其上界前另给具体最小拆分，不默认无限增长。
- live_control/tests.rs最终≤3596且绝对<3600，只允许下方矩阵明示迁移，不加注册或case；新测试在live_control.rs用cfg(test)+显式path直接注册到相邻小文件。可最小pub(super)/pub(crate)修饰复用已有candidate_tests helper，不搬旧case、不删断言/注释、不压行。原真正缺失仍须stop；完整零的旧“缺失”fixture不能用新实现失败来证明回归，也不能为保护其过早停机预期拒绝本次修复。
- 迁移顺序：live小段同义提取→原live/account/controlled回归→getter/ID校验与预算分类→drive/风险/mark hook→必要旧fixture迁移及新native生命周期/原reader/log集成→受影响回归与最终候选身份。超上述父阈值不能继续叠加；只报具体缺口，禁止无关大拆分。

Python test_btc5m_control.py当前2400行（read_file核对），本次仅上述新候选身份/实际消费者小回归允许进入2401–3599架构例外，绝对<3600；职责仍原固定controller的离线消费者，不写等待算法。先复用现有native_stream/metadata/store/log helper、仅添加本次必要case，再跑对应controller/reader回归；若增长需要独立fixture体系或另一个生命周期专题，拆分触发，不继续父文件堆叠。后续拆分目标为同目录专用order-wait consumer测试文件，仅移动本专题case和必要最小共用helper、保持生产入口/旧case；该未来新路径需主控另明确，不是本卡无限授权。当前不为新增几项回归先迁大量2400行旧测试。btc5m_control.py2293行只机械pin/path更新保持≤2400；两local_signer文件只既有pin断言，不展开新逻辑。以上是新源码变更后必需身份闭合，不重开旧接管语义门禁。

必要旧测试迁移（仅src/bot/runtime/live_control/tests.rs，全部原限定名保留）：

| 符号 | 可迁移的旧fixture/调用 | 必须保全 |
|---|---|---|
| an_order_still_unread_at_the_bound_keeps_the_existing_stop | 原hidden_until实际返回完整OPEN/零matches（controlled.rs:780–793），不是读取缺失；将本用例等待输入改成新fixture的真正UNKNOWN/缺失或明确无expiry，仍耗尽原短测试预算 | FACT_INCOMPLETE、detail原None、未Closed/预占保留；D17-01另证完整零跨120s不stop，不保留旧混类行为 |
| an_accepted_order_whose_facts_lag_is_re_read_before_a_blocked_candidate_stops_the_run | Resolved可提前返回原drive，故将原单次阻塞调用改为原sync/observe轮询至已有hidden_until结束再核对；只补必要调用步骤，不把部分/非Final当完成 | 真成交完整后原net库存、原预占规则、当前mark/generation合法、停止为空、sign/POST各一次；新生命周期尾查另测 |
| a_conflict_observed_while_waiting_keeps_the_existing_conflict_stop；a_re_read_that_reaches_the_run_deadline_stops_with_the_deadline_reason；a_read_whose_clock_fails_without_a_recorded_stop_still_stops_the_run；a_read_that_already_recorded_its_reason_keeps_that_reason | 若短helper返回使故障尚未触发，可改为一次原观察tick/显式当前read触发同一原故障；时钟调用次数变化可调ScriptedClock健康次数，使其仍在原事实应用后失败，不提前换故障 | 原各自FACT_CONFLICT/DEADLINE/FACT_INCOMPLETE、detail/takeover/预算/预占/一次发送断言及故障输入不变，不能泛改reason为新时钟码求绿 |

helper `first_order_with_visible_ack_but_invisible_fill`、`sending_fixture_with_trace` 仅最小可见性/新fixture选择接线；原非本矩阵用例不改变预期。若同名迁移确需净增至3600，不自行删断言或搬大测试，给主控明确迁移方案。

### R17.4 诊断落点与不改 wire 的证明

当前 `fills.rs::read_order_execution` 内同时持有after.status、原bound.expiration及该次 `ChainRead {block,timestamp}`，但ExecutionSnapshot没有raw status；`account.rs::ChainRead::closed`拥有真实关闭分支。这是最小日志seam，不是事件协议缺陷。仅在原fills.rs/closed原分支投影SPEC §R17.3四个封闭字段，经已有tracing输出，不打印ApiOrderData/BoundOrder/错误Debug；不为日志另提整个reader。未知status先match为UNRECOGNIZED；没有成功固定块读则block_time=null、closure_branch=READ_UNAVAILABLE，不杜撰关闭证据。只保留安全关联所需原已验证attempt/hash，不透传自由文本或完整私有对象。

closed局部投影必须保留短路顺序：FILLED且完整量→FILLED_COMPLETE；非认可终态→STATUS_UNPROVEN；timestamp>E→SIGNED_EXPIRY；原isFilledOrCancelled真→CHAIN_CLOSED；否则原nonce无效→NONCE_INVALID；都不满足→STILL_EXECUTABLE；原读错误→READ_UNAVAILABLE但保持原错误返回。不得为日志额外查nonce、增加RPC或把expiration==块时间当关闭。非Final的OPEN/未知仍按原闭合保守性。

实际输出消费者为既有 `tools/predictfun/btc5m_control.py::supervise` 的stderr/非事件行→`append_run_log`→`redact_output`，源码当前有单行STOP_OUTPUT_LIMIT=2048及run总RUN_LOG_LIMIT=64KiB，写失败不改变run stop；不是strict LiveEventStore的事件通道。因此无需扩types/order payload/Python validator/reader或新eventtype，无新sink/平台，生产Python逻辑只读复用、仅前表机械pin/path更新。复用原bounded best-effort log，超额可截断，不能宣称每次轮询诊断均耐久完整或用log替代Final证据；D17-06用无秘密transport注入实际记录验证字段/脱敏/限额及不杀run。新的原金融producer流仍必须经现有first writer/reader证明闭合，不手拼健康事件。

### R17.5 验证与交付边界

SPEC D17-01–06全量映射至相邻order_wait.rs/order_wait_tests.rs测试；核心必须用实际PredictFunTrader/account reader、原Broker/drive/clock与producer，fake仅transport和签名替身，禁止真实账户、keyring、网络、RPC/DB或paper实盘验证。两个真实时间线取ledger原UTC毫秒，各自按字段时间升序推进（第二轮market_end先于旧stop，不强排同一顺序）；status因原证据缺失必须明示注入假设，不将假status回填历史。还须按SPEC测300s签名/120s缺失与尾查的不同预算、完整零跨120、Final前后/部分晚到、expiry坏缺、失败/Unknown连续120、暂停/回拨/重复、deadline/loss/父/输出优先；每段sign/POST/cancel/预占/风险/mark/generation及同run续新轮都有实际断言。

旧 `an_accepted_order_whose_facts_lag_is_re_read_before_a_blocked_candidate_stops_the_run`、`an_order_still_unread_at_the_bound_keeps_the_existing_stop`、冲突/读中deadline用例及 `account::r16_tests::zero_fill_cold_history_keeps_unclosed_orders_unproven` 保留，不借新生命周期放松真正失败或OPEN/unknown终态。R16现金恢复/历史/claim及paper/live相同纯账务/风险/结算路径做受影响配对，差异仅本controlled live等待；其它venue默认getter=None不获得宽限。最终候选变动后只补受影响证据，不重开旧接管门禁，不把根因定位时的3个GREEN当本修复验收。

后续离线验证入口（本卡均NOT_EXECUTED；cwd=BOT，TARGET为执行worker当前scratch独立构建目录，沿既有locked/offline环境，不安装依赖；Python沿Implement卡使用pytest）：

```text
cargo test --locked --offline --target-dir "$TARGET" --lib bot::runtime::live -- --nocapture
cargo test --locked --offline --target-dir "$TARGET" --lib service::predict_fun::account -- --nocapture
cargo test --locked --offline --target-dir "$TARGET" --lib service::predict_fun::controlled -- --nocapture
cargo test --locked --offline --target-dir "$TARGET" --lib service::predict_fun::fills -- --nocapture
cargo test --locked --offline --target-dir "$TARGET" --lib bot::runtime::paper -- --nocapture
cargo check --locked --offline --all-targets --target-dir "$TARGET"
cargo build --locked --offline --target-dir "$TARGET" --bin polymarket-toolkits --bin btc5m_reconcile
CARGO_TARGET_DIR="$TARGET" /home/pascal/workspace/yquant-investment/.venv/bin/python -B -m pytest tools/predictfun/tests/test_btc5m_control.py tools/predictfun/tests/test_btc5m_live_events.py tools/predictfun/tests/test_reconcile_failure.py -q
```

`bot::runtime::live`过滤包含live_control及其新注册测试；实际执行前核对新限定名，0test不算通过，不执行其它ignored联网用例。独立Validate记录实际argv/cwd/native exit、最终HEAD/本次精确源码与双binary身份及未测项；候选物化/权限/证据位置及机械selector更新严格沿既有t_fd7cc2e9，不新增目录门禁、生产部署或激活流程。此Principal卡只交原三文件增量+Kanban摘要，静态检查实体/互引/版本/公式/allowlist/源seam与路径过滤diff；不新建报告/任务镜像、不执行这些业务命令。生产激活/新run/真实资金与24h稳定仍不在本卡，未知历史状态仍未知。

## R16：当前最小实施设计（2026-11-23）

本节实现 RFC/SPEC V1.15 的§R16，优先于本文旧阶段状态、旧文件清单/行数、旧候选构建路径及 WAIT_CASH 即结束/首因遮蔽后来硬停的表述。历史代码缺口、产物、PASS/FAIL及版本记录不删除、不追认；本节是 planned implementation，不是已完成声明。T2只修改本文；不构建业务、不运行业务测试、不访问凭据/账户/网络/数据库，不改代码/测试/配置/模板/README/根规则。生产选择器、activation、签名授权、真实或模拟交易、资金/链上、屏障和调度均不在本轮授权。

### R16.1 实测基线、保留项与替代范围

入口 ROOT main HEAD=`6f85b9f48972b8b3cd547ff9d2add76a1301c6ba`；BOT main HEAD=`4b6420f6a11eb5303d1a94949037f52b866d24c3`。入口 Design SHA256=`686461811e0d2f0238cd8c8594a66eaa8bd5938f339b91144a7eb40971b249dd`；上游 RFC/SPEC SHA256=`05f4fd93ca803b30d62518fe9ffcc705a51bbe5b2439e232de1d534b95f5342e` / `b7581dd585042ad771bfdf4209c9514c401044b51ece86bf288dea8f315d3830`。本卡按入口字节快照归属，不按mtime、共享树累计diff或dirty数量归属。下文src/、tools/均相对元数据BOT。

| 分类 | 当前源码与已核证据 | 本轮精确处置 |
|---|---|---|
| existing offline baseline | R15 t_239d0c0c/run4022：lib638/0/4ignored，bins15/2/2/4；账户并发、发送准备复用tick账户读、闭合历史记忆化；check_locked在facts/ACK/permit核对10s/身份/代际/attempt | 复用上游独立结论，不称本卡重跑；不再实现这些能力 |
| existing offline baseline | R13 credit_claim/promote_pending_claim及reader局部撤销CASH_PENDING；原Broker LiveState/net_cash/net_inventory/claims、同core、原单次POST和unknown/tombstone | 保留；补共同提交与驱动接线，不建立第二账本/reader余额控制器 |
| implementation gap | RunControl::must_end:230把WaitCash当结束；paper::wait_controlled_stop:686→drive:1609–1611/1637提前finish | 区分可撤销等待与终止；在原drive跳过策略新增而继续只读，恢复后下一tick重建候选 |
| implementation gap | account::reconcile_account_history:761跳过bound_orders；live::claimed_payouts:1059只读历史claimed_win，check_runtime_account:1154才核销 | 新增同次账户读取的本run证据出口；不把bound单重新塞进startup历史现金 |
| implementation gap | RunControl::stop仅Ready转换且stop首次胜出；reader只有全局cash_pending且每个CASH_CONFIRMED直接清空 | 临时现金等待与第一硬stop分责；多claim逐项索引，后到硬stop不能被清掉 |
| evidence gap | R15 before重复键/旧标签；book_to_facts_us止于facts而非ACK后permit；旧end_to_end漏账户采集；fixture无历史hash | 旧artifact原字节保留、NON_COMPARABLE；新同版探针只报实际量，不重造before |
| production gap | selector仍candidate-r14；R14 SHA96a7ed05…、R15 bcb5a8c0…均历史只读；run018原reader INCOMPLETE且无CASH_CONFIRMED | 不部署/切换；真实≤5s及到账分布NOT_EXECUTED/NOT_VERIFIED |

不变项逐项继承SPEC：单笔/market/total/budget/loss、min_edge/min_secs_left、10s盘口/账户及原spot规则、allowance、签名/bound/ACK/首次poll原子门、unknown/identity/generation、paper账本/结算与DecisionCore。`phase1.rs::recheck_diagnostic`、`btc5m_control.py::candidate_input_error`、原纯官方身份/settlement helper均只读复用。mark_time最小缓存时间和暂时generation INCOMPLETE不扩为新专题。run018事实以[只读诊断](../../../data/reports/2026-11-23-btc5m-live-diagnostic/report.md)为准：34次是NOT_SUBMITTED/INPUT_CHANGED，不是交易所拒单；5.407s后现金增加不代表原run已恢复。

### R16.2 拒绝诊断的唯一来源与时钟

内部类型在 `service/venue.rs` 定义封闭 `SendCheckStage` / `SendCheckDetail` / `SendCheckObservation`，只携带SPEC §R16.2十个键的类型化值：stage、detail、checked_at、checked_elapsed_ms、tick_started_elapsed_ms、book_receipt_age_ms、spot_receipt_age_ms、account_receipt_age_ms、book_request_age_ms、spot_request_age_ms。不是新的reason/stop枚举。guard在 `live_control/diagnostics.rs` 计算投影，保存在原ControlledLiveState按attempt的最新检查记录；失败记录first-failure，不能被后续清理/成功覆盖。已持State的guard内部直接用mut State记录，不回调会重锁State的通知方法；adapter锁外通知才取State锁。adapter只传有类型的分支结果给原guard；原Error/CandidateRefused/Submission及判断顺序保持，禁止从Display/字符串解析“更精确”原因。

沿 `ControlledSendGuard` 增加默认无副作用的诊断通知方法（不授予许可），携带stage/detail；`LiveCandidateGuard`实现将原phase1 clock取得的CheckTime和同tick/原candidate/LiveAccountRead时钟冻结。adapter本地失败仍走原错误返回，不改变downcast分类；`FrozenAttempt`/market_amounts/check_limit/原bound校验的失败处就地通知，绝不另跑一套价格/深度规则。成功检查也可记NONE；没有可靠CheckTime时order.diagnostic=null，不能伪造checked时钟或Tp。原无法细分且未在下表列出的分支为UNKNOWN，未测/旧流缺键只表示UNKNOWN。

| 原owner/分支（在原顺序处捕获） | stage / detail | 原控制结果不变 |
|---|---|---|
| prepare check_allows_new_order/guard.check_preparation | PREPARE / RUN_STOPPED；若原命中冻结输入为FROZEN_INPUT | 原硬停/拒绝不重分类；同一复合if按原左到右首个命中，不能先查age改优先级 |
| account_snapshot缺失、不完整、receipt过期 | PREPARE或当前FACTS/ACK/SEND_PERMIT / READ_UNAVAILABLE、ACCOUNT_INCOMPLETE、ACCOUNT_STALE | 原READ_UNAVAILABLE；只诊断，不把账户失配当候选可重试 |
| guard.check_book空一侧 | PREPARE / EMPTY_BOOK | 原READ_UNAVAILABLE/EMPTY_BOOK，非交易所拒单 |
| 原market_amounts深度不覆盖、原check_limit越限 | PREPARE / DEPTH、LIMIT_PRICE | 原CandidateRefused/INPUT_CHANGED，确知未发才释放该attempt |
| FrozenAttempt::check_order及原已签界限证明 | SIGNED_BOUND / FROZEN_INPUT或SIGNED_BOUND_UNPROVEN | 只按原失败分支分类；不放宽q/签名ratio/fee/route |
| check_locked身份/指针/候选关联复合检查 | FACTS/ACK/SEND_PERMIT / IDENTITY_MISMATCH、ATTEMPT_MISMATCH、FROZEN_INPUT | 原INPUT_CHANGED及Candidate/Window区别保留；拆诊断标签不拆原判断优先级 |
| check_locked的receipt/complete/identity/generation/next_attempt检查 | 当前stage / ACCOUNT_STALE、ACCOUNT_INCOMPLETE、IDENTITY_MISMATCH、GENERATION_MISMATCH、ATTEMPT_MISMATCH，按源码顺序 | 原READ_UNAVAILABLE，不跳过任何guard |
| recheck_diagnostic返回Reason::SpotStale/BookStale/RoundTooLate/EdgeBelowMin/InputChanged | 当前stage / SPOT_STALE、BOOK_STALE、ROUND_TOO_LATE、EDGE_BELOW_MIN、FROZEN_INPUT | 使用这一次原core结果；ClockInvalid/RequestTooSlow/其余未映射→UNKNOWN，不另复制模型 |
| ACK槽/15s耐久确认故障 | ACK / ACK_UNAVAILABLE | 原AUDIT_UNAVAILABLE/CONTROL_CHANNEL/PARENT_LOST优先级不变 |
| with_send_permit最后callback的失败或成功 | SEND_PERMIT / 对应首个分支或NONE | Tp必须来自gate内callback成功且handoff成立；guard外提前检查不冒充Tp |
| POST权威RejectedFinal或可能提交后异常 | POST / VENUE_REJECTED或SUBMISSION_UNKNOWN | 原权威证据才RejectedFinal；401/timeout/坏响应未知，保留风险/同hash且0重POST |
| 原预算/gas等未列detail的安全失败 | 当前stage / UNKNOWN | 不发明detail/stop、不把不识别当成功 |

同一临界区内仅捕获固定大小enum/时钟/整数；不得新分配无界集合、打印/刷盘、等待另一个测量锁或新增I/O。`LiveCandidateGuard::with_send_permit`原State→handle→gate→first_poll顺序不变；诊断随原后续order发送，`prepare_order`及guard的PREPARED/MAY_HAVE_SUBMITTED两个直接OrderPayload构造点全部接同一字段，不能漏一出口。原reason/diagnostic_reason原字节不改；无attempt的无机会仍只用原decision诊断。

`live_events/order.rs`拥有OrderPayload和其严格校验（从types.rs同义迁移），父types显式re-export，原live_events门面不变。order新增且仅新增可空diagnostic；新producer显式写null或封闭十键对象，新Rust/Python validator对旧流缺键先内存补null、然后原exact校验，不回写。递归未知/重复键、bool冒整数、非负、时间/枚举校验均在首次write前；不以serde默认忽略未知键。reader不以诊断决定放行/资金，仍调用原candidate_input_error校验冻结事实；旧reader不承诺前向兼容。

时钟owner是run.phase1.clock（原UTC+含暂停elapsed）。T0在 `check_runtime_account` 的本tick首个账户请求发起前采，保留至该tick候选/guard；startup seed不是T0，后续record_account_read只记完成receipt、不覆盖T0。Tb取该candidate原book receipt；Tp在ACK后原gate内最后callback成功完成且紧邻第一次transport handoff采；拒绝采Tr，无Tp。主指标`tick_to_send_permit_ms=Tp.elapsed−T0.elapsed`，并列`book_receipt_to_send_permit_ms=Tp.elapsed−Tb.elapsed`；拒绝仅`tick_to_refusal_ms=Tr.elapsed−T0.elapsed`。每个receipt/request age按SPEC双时钟max，任一缺失/负差为null，不夹成0或改变原freshness。5000ms仅目标，不新增/放宽发送门禁。

### R16.3 R15三minor最小闭合

1. 新探针measurement_revision=`btc5m-send-path.r16.1`，单位ms（旧us segment另列单位，不混换）；`timing.rs`旧重复stage不能再拼成object同名key，采用有序segments数组 `{stage,duration_us}`、由serde序列化，report递归拒重复键。新probe实际执行账户采集→同core→原guard/ACK/permit/first_poll，不用decision+旧total或book_to_facts_us拼主指标。n/缺测/成功/本地拒绝/unknown分组、nearest-rank p50/p95/max及RTT/样本数/冷热历史身份均记录；串行运行避免原全局timing窗口交叉。旧before原bytes/hash保留并标NON_COMPARABLE；没有干净R14源可重现就不生成新before，只给新候选绝对值。
2. `account/runtime_claims.rs`承接原read_account_snapshot共同读取主体。positions→history组成有依赖腿（history在positions完成且remember_market后消费declared订单lookup）；open_orders/account/chain仍并发。最终错误判定仍 positions→open_orders→account身份→chain→history，持仓链证明仍按原positions顺序判错。不删除每轮matches、新未声明hash拒绝、完整分页或Closure::Final后memo写入。冷缓存反例让declared hash不出现在matches、market仅positions可提供且positions延迟；热缓存相同输入对照，新增foreign hash即使memo命中仍拒绝。
3. 在既有SyntheticTransport边界注入authorize读失败和balances故障，分别钉住 balances失败→原余额错误；余额可读但不足/零gas→INSUFFICIENT_FUNDS；余额足够→原authorize错误，均0sign/0POST。guard preparation同时变化时仍按fills.rs现有`balances? → check_preparation → funds → authorized? → check_preparation`顺序。只扩cfg(test) transport，不改生产authorize/并发或安全reason。

### R16.4 本run证据出口、精确核销与单一提交者

不用历史ClaimedWin承担runtime含义，也不加会使全仓AccountSnapshot字面构造扩散的必填字段。新增内部 `RuntimeAccountObservation { snapshot: AccountSnapshot, bound_claims: Vec<BoundClaimEvidence> }`；`OrderVenue::runtime_account_observation(&self, closed: &[RuntimeClaimInventory])`默认委托一次原account_snapshot并给空证据（不能产生claim）。`RuntimeClaimInventory`精确为identity:OrderIdentity、execution_generation:u64、inventory_atoms:U256，由Broker在原State锁下从当前Closed、pages/费用/net已完整应用且reserved=0的本runattempt生成，不承载现金或官方结果。PredictFun在原fills.rs的OrderVenue impl委托account/runtime_claims.rs同次读取主体；普通account_snapshot调用同一主体的legacy模式、返回原快照，startup行为不变。不新建client/第二账户读，不新增请求种类。生产唯一调用新增方法的是controlled check_runtime_account；同operation lane、锁外await，回来先核next_attempt/generation版本。

`BoundClaimEvidence`是原事实DTO，不含可交易余额/认证材料；精确字段为identity:OrderIdentity、execution_generation:u64、yes_token:String、no_token:String、inventory_atoms:U256、claim_atoms:U256、payout_millionths:u32。身份含local_attempt/hash/venue id/account/market/token/side；run/window由消费它的冻结run绑定（不由adapter造run id）。仅缺失/已移除同token份额的bound order才尝试生成；持仓尚在时不生成到账证据。把closed输入与bound_orders原handle的Closed/完整identity及adapter当前generations逐项匹配，复制绑定后锁外沿原官方MarketData/official_settlement读取。这里禁止再调用read_bound_execution：其每次读会增加generation，若不经原sync消费就无法对应当前Broker代际；实际执行仍由此前原sync→consume_snapshot唯一消费，closed输入只引用这一次已完整的事实。同账户读前后adapter generation变化则拒绝本次证据，下一轮原sync重证，不伪造代际。用读取前原Yes/No绑定验证完整官方身份/非争议/0.5或1，U512 floor得P。同份额/同token的positions读回、原pinned chain余额/持仓验证不能省略（缺失token也必须沿原chain.position以期望0核链，不能只看REST空列表）。adapter不在此应用执行delta、不resolve新风险、不记B/R，不把“返回候选证据”称现金已核销。

history仍跳过bound hash，startup declared历史解释仍走原claimed_cash_matches(C0+历史claim)。runtime模式对历史claim使用opening baseline消除重复：基线已有的历史Q/P只作旧事实一致性检查，不再要求当前余额等于C0+历史claim，不再计runtime收益。原history/matches未声明新hash和known token绑定保护继续运行；不可简单忽略positions_explained。runtime helper返回原始snapshot完整性与候选bound证据，只有Broker的全量核对成功后才可把该read的positions_explained置为真并发complete reconciliation；不为适配器partial/failure置真。没有本run唯一owner的变化保持RECONCILIATION_REQUIRED。

对应真实投影接缝是 `live_accounting.rs::project_window` 当前以 `facts.opening_claim_cash()` 初始化claimed_cash（入口412行）：本轮改为0，opening_claim_cash仅保留startup对账/来源元数据，不再进入本run的B/R/NAV收益。预算仍为原params.budget=C0，不用Cb抬高预算；B=C0−本run实际支出+本run已核现金，R只含本run已实现损益。账户总collateral用Cb全量两式单列核对，Cb−C0的历史已到账不再次成为可交易预算/本run收益。这样保留原预算恒等式与reader预算校验，不改C0/额度、不把账户总余额和窗口B混同。旧历史run投影不回写；同流fixture同时断言startup资格、实际总账户核对及本run收益三者分责。

新 `live/claims.rs`承接原claimed_payouts及check_account_delta_with_claims的同义纯核对，保留原路径pub(crate)门面供旧调用；新增runtime证据验证只读State。按 `(run,window,account,attempt,hash,market,token)` 唯一逻辑键、当前generation、Closed、预占0、完整费用/net验证，不能仅按token找到first owner；多owner/冲突拒绝。controlled生产runtime只能使用BoundClaimEvidence，不能因默认wrapper证据为空而回退到ClaimedWin造本run收入；旧ClaimRead/ResumedVenue局部fixture显式实现新typed只读出口，按§R16.6.1迁移被新契约替代的断言，其余正反语义保全，仍不是full-path验收。不把已核销inventory从原累计net_inventory删除，否则重复读无法再解释trade-only增量；原claims作为核销集合，pending_claims只保留证据和所依据代际/读版本，不拥有余额。

严格实现SPEC §R16.4的两式：`Cobs=Cb+Din−Dout+sum(P[A∪N])`；每token `Iobs=Ib+ΔI−sum(Q[A∪N])-Z`。Cb是opening snapshot实际collateral，历史收入已含其中；Din/Dout/ΔI仅实际交易累计，排除claim；Z仅已证明零兑付归零。U512中间运算checked再转U256，1 atom差也失败，不跨token抵销、不拿总金额相等替代逐owner校验。DRAW payout_millionths=500000，WON=1000000，floor沿原atoms规则；原official pure helper仍负责结果，禁止从展示f64重建金额。零兑付沿原经济损失/链残余披露，不产生现金claim。

唯一核销提交者仍 `live_control::credit_claim`；`promote_pending_claim`改为同一提交者的委托，不能直接insert另一条账务路径。流程为：lane内读取当前State版本→锁外同次account/官方证据→锁内先验证所有拟入账项和完整等式、当前receipt/generation→构造不可变commit计划→官方runtime outcome存在且精确Q/P时一次commit claims/K/B/R投影及outcome.cash_confirmed。失败全部不部分提交。首次现金证据但runtime官方消费者尚未消费时只保存pending、立即进入同一WAIT_CASH，B/R不动；后续原apply_official_result先保留outcome，再经相同验证/提交者消费pending，必须用当前generation完整read重证，不能靠旧tuple跳过。generation变化使pending失效而非被当foreign或永久删除；新完整同目标证明可续接，W0不重置。已到账不符官方结果是事实冲突，不是读失败。

幂等：相同键且Q/P/generation一致的重复结果/快照/重复pending仅确认旧事实，不再入账/发CASH_CONFIRMED；新的更高generation且Q/P相同只更新证据版本，不再记现金，旧generation拒回退；同键不同Q/P为冲突，保留先前风险/账目不冲销。多个claim分批可分别记现金，但所有正claim闭合且无持仓/挂单/unknown/inflight/预占/费用代际缺口、原risk/receipt/deadline均满足前不恢复；现金核销可以在硬stop后如实补事实，不能解除硬stop。

wire不加payout键/event_kind。顺序单一lane分配seq：已有/首次官方正claim的CASH_PENDING（尚未记现金的accounting）→相应stop CASH_PENDING（仅一次）→完整同次读回核销后的reconciliation→逐项payout CASH_CONFIRMED（有cash_received_atoms）→必要lifecycle→下一tick全新decision/PRE_SUBMIT/RESERVE。现金先到只先发stop CASH_PENDING，不伪造runtime outcome/payout；runtime结果消费后先发真实CASH_PENDING再核销发后两项。多claim先投影本批全部pending，再逐项confirmed。若某项仍缺，不清等待。失败输出毒化emitter并硬停，不重发资金动作/补写final。

reader `LiveRelations`只保留审计关联索引，不创造余额。现金核销/等待清除的payout以已有envelope `(market_id,token)`关联唯一attempt（须Closed且净库存已证明），pending/confirmed/zero按该键集合记录，比较Q/P与官方payout及最近完整reconciliation；重复同值不重计，矛盾现金事实拒绝。`UNRESOLVED/CONFLICT`保持原身份关系校验，不附加Closed或完整净库存前提：原apply_official_result在Closed检查前即可输出合法CONFLICT，reader须能记录尚未闭合attempt的冲突及硬停，绝不能据此核销现金或清等待；D16-08补该partial/inflight冲突producer→reader反例。stop CASH_PENDING记未开放风险的等待；没有runtime payout时也不能因global bool初值为false提前解除。只有全部经济owner均已有零兑付或CASH_CONFIRMED且完整reconciliation、无未闭合attempt才清wait。每条CASH_CONFIRMED不能无条件清全局cash_pending。第一非CASH_PENDING硬stop单独黏性；后来现金不能清，后来CASH_PENDING不能改名。保留旧合法单claim流消费及原严格first writer→关系索引→落盘→reader路径，不手拼健康金融事件替代producer。

### R16.5 WAIT_CASH、硬停止与驱动预算

`live_control/cash_wait.rs`拥有CashWait元数据（W0:CheckTime、待回收逻辑身份集合、终止/过期标记），无第二资金表；挂在原ControlledLiveState。CASH_WAIT_BUDGET直接引用现有LIVE_TAIL_BUDGET=600s，不改其值，不复用READ_FAILURE_BUDGET=120s、不另加配置。RunControl保留临时state/stop观察接口，但其第一硬stop不可被等待遮蔽：现金等待发生后出现非CASH_PENDING stop，WaitCash→StopNewRisk，第一硬stop写入并重置stop_event_emitted让原lifecycle输出新事实；之后更多硬stop不改首个硬因。原CASH_PENDING事件保留，不回写历史。已有硬stop后进入现金等待仅补事实、不改变终态。

| 条件 | must_end / may_add_risk | 原drive动作 |
|---|---|---|
| Ready、无degraded/硬stop/损失/期限 | false / 沿原规则 | 原sync/strategy/settle |
| 有效CashWait，无硬stop | false / false | 原poll tick只读观察，绝不新RESERVE/sign/POST/cancel或策略副作用 |
| 等待中Read/Execution/Valuation短暂失败 | false / false（未耗尽原各自预算） | 继续原降级观察；成功只清对应失败，不清W0/claim |
| 后到人工stop/父EOF/control/output/loss/unknown/事实冲突/原读失败预算耗尽 | true / false | 第一硬stop胜出，原有界cleanup/final/return；不得等到账才停 |
| now达现金600s而原deadline未到 | true / false | 保留CASH_PENDING+takeover_required，final不完整；无新stop词汇 |
| now达原任一时钟deadline（含与到账同tick） | true / false | 原DEADLINE（若无更早硬stop），先关发送；只允许事实消费/收尾 |
| 全部精确核销且仍在双时钟有效窗口、无其余风险/降级/硬停 | false / 原完整guard重验后才可为true | 清本次wait，废弃旧candidate，下一原tick采新输入进入同core/原发送链 |

每次wait入口、read前后、核销恢复前、tick与wait_controlled_stop观察时均取原clock。有效条件同时为 `now.utc < min(W0.utc+600s,deadline_at)` 和 `now.elapsed_ms < min(W0.elapsed_ms+600000,run_elapsed_deadline)`，任一等号即不得恢复；读取失败/倒退标记不可延长等待，沿既有DATA_UNAVAILABLE/CLOCK保护停止。W0首次官方正claim或可归属现金证据任一先到即记，重复/部分回收/成功读/轮次变化不重置。完全清除后未来真实新claim可建立新W0，总run原deadline永不重置。

`runtime.rs::drive`仅小分派：原sync_live仍执行；若处于wait则调用 `cash_wait::observe_wait_tick`（复用原sync/settle/必要mark读的入口及原poll/settlement cadence）并跳过strategy.tick/is_halted的cancel分支，不能让is_halted/entry_stop提前结束或继续策略。helper不得持operation lane再调用自行取lane的sync/settle；各原操作自己串行，State不跨await。等待期间只读future可由原控制通知/期限select中断；不丢弃已可能POST的future、不引入热循环/第二runner/长期调度。`paper.rs::wait_controlled_stop`只观察真正终止和deadline，并调用wait预算检查；paper分支不变。原settlement cadence用现有SETTLE_CHECK_EVERY，fake测试推进tokio时间/原clock而非真实等待600s。

`finish_controlled_live`保留原cleanup30s及只读tail，但已有CashWait时tail上限取W0剩余额度、原期限/原收尾规则较小值，绝不从finish再给600s；现金等待预算已耗尽则无额外恢复窗口。终止后到账可以补核销/完整事实，但不得回Ready/再RESERVE。cash_complete按必要现金事实而非exit0决定；没有全部事实仍INCOMPLETE/接管。600s不是兑付SLA，真实领取延迟分布未验证。

### R16.6 本轮精确allowlist与G3

下表仅授权后续Implement的必要子集，不授权整个目录；均BOT相对路径。原27路径加Pascal明确批准的§R16.6.2唯一既有Python测试路径，当前总范围为28个唯一路径。新模块路径是明确planned文件，并非声称已存在。其它旧§10清单不作为本轮额外权限。表内测试仅cfg(test)/离线synthetic；§R16.6.1/2只授权列明符号的必要fixture/旧断言迁移，不允许顺手搬迁旧大测试、格式化全仓或修改生产selector/activation。

| 精确路径 | 真实缺口 / 符号与最小用例 |
|---|---|
| src/bot/runtime.rs | drive按CashWait跳过策略/保留原只读和退出；D16-06/09原drive不提前finish及真续轮 |
| src/bot/runtime/live.rs | 注册claims子模块、RuntimeAccountObservation接线/T0、版本及commit计划；原历史/普通live行为回归 |
| src/bot/runtime/live/claims.rs（新） | 原claimed_payouts/check_account_delta_with_claims最小同义迁移、runtime唯一owner/两式纯验证；1atom/重复/历史隔离 |
| src/bot/runtime/live_control.rs | 注册cash_wait/diagnostics/两测试子模块；RunControl stop/must_end、credit_claim统一提交、guard各实际分支通知 |
| src/bot/runtime/live_control/cash_wait.rs（新） | W0/预算/无风险只读tick及恢复资格，不记余额；双时钟边界与硬停次序 |
| src/bot/runtime/live_control/diagnostics.rs（新） | 同clock、core结果到封闭诊断/age投影；拒绝优先级和缺测/倒退 |
| src/bot/runtime/paper.rs | wait_controlled_stop窄hook到等待预算/真正终止；paper语义不变 |
| src/bot/runtime/live_accounting.rs | apply_official_result/pending统一提交/事件顺序、project_window排除opening历史claim收益且不抬C0；finish的W0剩余tail；正反到账/历史分责；仅§R16.6.1列明的opening旧测试预期随契约迁移 |
| src/bot/runtime/live_events.rs | prepare_order、claim/reconciliation/lifecycle薄投影，stop新硬因及不重复confirmed；真实producer序号 |
| src/bot/runtime/live_events/types.rs | OrderPayload与order校验同义移出并re-export、旧order缺diagnostic规范化委托；严格门面回归 |
| src/bot/runtime/live_events/order.rs（新） | 原OrderPayload/校验和可空诊断封闭十键；递归坏键/旧流兼容，非资金逻辑 |
| src/bot/runtime/live_events/tests.rs | 原schema回归必要构造适配、未知/重复键/非法age断言；旧8例及已有断言保全 |
| src/service/venue.rs | RuntimeAccountObservation/RuntimeClaimInventory/BoundClaimEvidence和typed诊断DTO、OrderVenue默认只读wrapper/guard通知；不变AccountSnapshot/旧impl必填形状 |
| src/service/predict_fun/account.rs | 注册runtime_claims/r16_tests；将原read_account_snapshot共同读取主体最小移到子模块；不迁整个history/chain/旧测试 |
| src/service/predict_fun/account/runtime_claims.rs（新） | legacy/runtime同次完整读取、positions→history依赖、bound证据及官方身份复用；冷/热/未声明hash |
| src/service/predict_fun/account/r16_tests.rs（新，cfg(test)） | 依赖时序/缓存与历史保护、balances+authorize故障边界；原SyntheticTransport封闭fake |
| src/service/predict_fun/fills.rs | OrderVenue wrapper委托、prepare/sign/bound/POST实际失败诊断通知；原错误返回/并发/首poll保持 |
| src/service/predict_fun/controlled.rs | 仅cfg(test)注册r16_fixture及最小synthetic调用seam；不改生产signed-bound/transport算法 |
| src/service/predict_fun/controlled/r16_fixture.rs（新，cfg(test)） | 扩已有SyntheticRpc/BookTransport为可控账户atoms/官方结果/故障，不替代PredictFunTrader/原sign路径 |
| src/bot/runtime/live_control/tests.rs | 共享fixture/helper必要可见性及§R16.6.1列明两函数的硬stop旧预期原位迁移；禁止净增行/新增case，最终≤3596且绝对<3600；其余旧断言不变 |
| src/bot/runtime/live_control/tests/claim_wait.rs | 仅§R16.6.1列明ClaimRead/ResumedVenue及helper的typed fixture、现金先到/失配硬停旧预期迁移；原10个case同名保全，未被替代的安全断言不变；不以mock替代新adapter/drive链 |
| src/bot/runtime/live_control/tests/r16_cash_drive.rs（新，cfg(test)） | 原drive+实际adapter两种到账顺序、多claim/硬停/边界、emit原始流；D16-06–09 |
| src/bot/runtime/live_control/tests/r16_diagnostics.rs（新，cfg(test)） | 原guard各阶段/未发与unknown/paper-live共同域对拍；D16-01/02/05/10 |
| src/bot/runtime/live_control/tests/send_timing_bench.rs | 同版T0→Tp/Tb→Tp真实测量、严格JSON/历史冷热点条件；D16-03 |
| src/bot/runtime/timing.rs | 旧stage重复键改有序segments/serde输出和revision，保留gated/inert默认；无临界区阻塞测量 |
| tools/predictfun/btc5m_live_events.py | validate_live_event/LiveRelations首写及reader共同支持order.diagnostic、按owner现金等待/硬stop索引；无生产配置/执行权限 |
| tools/predictfun/tests/test_btc5m_r16_integrated.py（新） | 原Rust输出→原supervise/LiveEventStore→read_live_run；原健康流、反例/多claim/硬停/严格JSON |
| tools/predictfun/tests/test_btc5m_live_events.py（既有，Pascal补充授权） | 仅§R16.6.2列明的两处已冻结旧预期迁移；全部原用例/未受影响断言保全 |

实测物理行数（2026-11-23，含空行/注释）：runtime2398、paper2364、live2871、live_control1519、live_accounting1246、live_events692、types1199、live_events/tests576、live_control/tests3596、account2986、fills2309、controlled1124、venue815、timing115、send_timing_bench137、Python live_events896及原test_btc5m_live_events893。不是旧§10各父≤2400的事实；本次不修改根G3、不授≥3600豁免。

- live.rs（2401–3599）：职责仍唯一实绩账/账户对账。只迁上述两个直接相关纯claim helper到live/claims.rs并保持门面；父只增加wrapper/版本/T0接线，不在父写新归属算法或测试。先同义迁移并跑live回归，再添加新证据校验，最后跑原drive/reader。不得为了到2400大搬apply_snapshot/旧测试；本轮最终父≤入口2871、绝对<3600，下次跨职责/超过该入口须新Design。
- account.rs（2401–3599）：职责仍链读/完整history/身份保护；共同账户snapshot主体和新runtime证据放account/runtime_claims.rs，父只注册/委托，不扩history/chain/老测试；最终父≤入口2986、绝对<3600。先迁读取主体→旧snapshot回归→positions依赖及bound证据→cold/hot/unknown反例；不得为压行删注释或改分页/缓存含义。
- live_control/tests.rs（3596）仅可见性修饰及§R16.6.1两函数的reason/state预期原位替换，最终≤3596、绝对<3600；不得删断言/注释、压行或改变fault矩阵凑行数。新增硬停事件/恢复反例仍放指定r16_cash_drive.rs，诊断新case仍放r16_diagnostics.rs，注册放父live_control.rs。本修正不搬旧case、不改限定名；若原位修改确需增长，先给主控精确源/目标（限既定模块）、符号和逐项等价覆盖方案并获准，不能自行广泛重构或挤掉原覆盖。
- runtime/paper/fills继续≤2400且只薄hook；若接线将越界，把本表已指定helper放对应子模块，不默许另建未列文件。live_control/live_accounting≤2400的受控扩张仅本合同职责、独立Validate；新的cash_wait/claims/diagnostics/runtime_claims各≤1200，所有新测试/fixture文件各≤1200。
- types.rs/live_events.rs继续原≤1200硬边界，先移OrderPayload及order校验到order.rs后加字段；order.rs≤1200，不让1199行父直接堆叠。controlled.rs仅cfg(test)注册，保持≤1200；venue/Python live_events/timing及相关小测试目标≤1200。迁移保留可见性门面和测试限定名；仅§R16.6.1逐项列明的新契约替代预期可改，其他旧断言全部保留，非重复实现。

明确只读：phase1.rs及其模型/测试、arbitrage.rs、taker.rs、phase1_control.rs、live_control/channel.rs（原EOF/ACK seam只调用）、predict_fun.rs/request.rs、其余SDK/signer/cli、btc5m_control.py（含selector/candidate_input_error/supervise）、btc5m-live-activation.json、所有公开配置/依赖/锁文件、README/其他文档/observer/history/replay/冻结研究/旧run/旧candidate/生产数据。需要原supervisor可在测试注入只读调用，不能改运行态。未列文件若确有编译/消费者必要缺口，记录证据交主控修窄范围，不自行扩大。

#### R16.6.1 既有测试迁移矩阵（V1.15同版范围修正，2026-11-23）

本节只消除§R16.4/5已冻结行为与旧测试禁改范围的矛盾，不新增业务决策或文件。以下路径均相对BOT，函数名保持原样（包括含旧语义的历史名字），不删除/skip/ignore/xfail。修正的是断言所表达的旧规则，不是把所有失败判成“旧测试错误”；未列符号只沿原allowlist职责，新缺陷不得改测试迁就。所有fault分支、atoms/身份/generation/费用/未知风险负例、原账务不回滚和幂等覆盖必须保全。

| 精确文件 / 函数或fixture | 原期望 / 迁移后的精确期望 | 来源与不允许改变项 |
|---|---|---|
| src/bot/runtime/live_control/tests.rs::live_known_conflicts_override_missing_without_rewriting_outcomes | `applied=true`发生真实冲突后stop仍CASH_PENDING → 与未applied冲突分支同为FACT_CONFLICT、StopNewRisk、0新增；第一硬stop黏性，后来到账不解锁。可原位替换reason及对应旧注释；新增状态/事件反例放r16_cash_drive.rs | SPEC §R16.5终止优先、D16-09；原applied两值/全部15个fault及conflict判定、outcomes不改、net_cash/net_inventory不回滚、冲突必有事件的断言不变；非conflict分支不改成冲突 |
| src/bot/runtime/live_control/tests.rs::incomplete_official_results_preserve_live_risk_and_sticky_reason | `prior=CASH_PENDING`后读到本函数构造的缺失/异常官方事实，旧expected_reason=CASH_PENDING且WaitCash → DATA_UNAVAILABLE且StopNewRisk，修复事实后仍该第一硬stop、不可恢复；READY/OPEN_ATTEMPT仍DATA_UNAVAILABLE，DEADLINE仍DEADLINE/StopNewRisk | 已读apply_official_result的Pending且非normal_unpublished_result分支；本函数全部field均不构成正常unpublished；paper::same_round/revised_result只读复用。SPEC §R16.1原安全门、§R16.5终止优先/D16-09；全部4个prior/20个field、账本/预占/outcomes/原seq幂等及修复后事实可消费断言保留。正常OPEN的assert_normal_result_wait不在本迁移中，不把短暂读失败一律硬停 |
| src/bot/runtime/live_control/tests/claim_wait.rs::{ClaimRead,ResumedVenue}::runtime_account_observation（新增impl方法）；同文件claim_read、claim_snapshot、claimed_win | 旧AccountSnapshot.claimed_win兼任本run证明 → 同一次snapshot加显式BoundClaimEvidence，以当前closed参数/原attempt真实identity、hash、pair、generation、Q/P构造；runtime不再走历史ClaimedWin fallback。允许必要构造/调用及pending内部表示断言改为相同逻辑键/Q/P/版本语义 | SPEC §R16.4.1–6；不额外读账户/执行以推进generation、不从展示f64重建生产金额、不替坏token/差1atom输入“纠正”成合法数据、不虚造owner；原ResumedVenue发送/查询仍委托实际trader。这是局部fixture，不代替D16-06/07真实adapter证据 |
| src/bot/runtime/live_control/tests/claim_wait.rs::a_claim_credited_before_the_official_result_never_stops_the_window | 现金证据先到但runtime结果未消费仍Ready/无stop → WaitCash/CASH_PENDING、may_add_risk=false，保留pending且claims/B/R不加，首次证据记W0；runtime消费完整官方结果并以当前generation完整读重证后才Ready、一次精确credit/COMPLETE | SPEC §R16.4.5–7、§R16.5触发/清除，D16-07；允许必要重读步骤及原状态预期迁移，不允许仅把pending tuple直接提升或删“未确认不入账”断言；最终精确Q/P、cash_confirmed、pending移除/完整性仍保留 |
| src/bot/runtime/live_control/tests/claim_wait.rs::the_real_producer_pays_the_claim_and_the_reader_can_follow_it；the_real_producer_trades_again_after_the_exact_claim_and_the_reader_follows_it；a_later_exact_claim_clears_the_cash_wait_and_the_final_cash_is_complete | 只迁typed ClaimRead/ResumedVenue构造/调用及必要当前读证明，结果先到仍WaitCash，精确现金后Ready/一次credit；后一交易case仍下一不同轮实际两次sign/POST，不把断言改成“无异常即可” | SPEC §R16.4/5、D16-06；原发送/账务/COMPLETE/final语义断言不改；captured_late_exact_claim_final_reports_complete_cash仅受生产者fixture联动，CASH_PENDING历史、final cash_complete=true/takeover=false/run_status=STOPPED预期不变 |
| src/bot/runtime/live_control/tests/claim_wait.rs::the_real_producer_refuses_a_claim_one_atom_short；a_claim_one_atom_short_is_never_booked_as_cash；a_late_claim_that_is_not_exact_leaves_the_cash_wait_in_place | 同次完整账户证据差1atom，旧check_runtime_account.unwrap成功、保留WaitCash/CASH_PENDING（a_claim_one_atom_short还把坏proof留pending）→ 读核对拒绝/Err、StopNewRisk/RECONCILIATION_REQUIRED（无先前硬stop时）；坏proof不能成为可核销pending。claims/B/R不加、不得恢复，final现金不完整/接管保持 | SPEC §R16.4.2–6、§R16.5成功读失配不是瞬时读失败、D16-08/09；只迁错误/终态/坏pending预期，不删1atom注入，不改成容差或假装未收到完整证据。captured_one_atom_short_claim_keeps_the_cash_incomplete的final cash_complete=false/takeover=true断言不变 |
| src/bot/runtime/live_control/tests/claim_wait.rs::a_claim_never_clears_a_stop_that_is_not_the_cash_wait | DATA_UNAVAILABLE先到分支：只迁typed fixture，合法精确proof仍须读核对成功，stop/state/may_add_risk仍DATA_UNAVAILABLE/StopNewRisk/false；runtime结果缺失时只存pending不加现金，不把因fixture没提供typed证明导致的Err当合格结果。foreign token分支：仍Err，旧WaitCash/CASH_PENDING → StopNewRisk/RECONCILIATION_REQUIRED、0新增/0现金；保留错token注入 | SPEC §R16.4.1/4/5及§R16.5第一硬stop黏性、D16-08/09；不把先前DATA_UNAVAILABLE改成新reason，不让foreign proof只等600s；两个分支都保留，不弱化为“不是Ready即可” |
| src/bot/runtime/live_accounting.rs::tests::an_opening_claimed_payout_adds_exactly_its_cash | 函数实际为无attempt、C0=10 USDT、opening历史claim=1 USDT；旧cash=11、net_pnl=+1 → cash=10、net_pnl=0、realized=0、NAV=10，status=Complete与非负零仍保留；opening fixture仍返回1，不改为0规避 | SPEC §R16.4.2/3/6、§4.4预算与收益分责、D16-08及Design §R16.4既有project_window设计；该预期确被新契约替代，不要求把候选project_window改回历史收益重复入账。startup仍核C0+历史现金/实际Cb，两式仍从Cb起算；不能因此削弱startup资格或把历史现金再注入本run预算 |

迁移范围判定：仅上表明列的现金先到状态、失配硬停、opening收益和typed证明是合法旧预期迁移；精确到账后仍不能核销/续轮、硬stop被现金清掉、错误owner/代际/atoms仍获准、重复入账、reader/writer不一致等均是候选缺陷，必须修候选而非降低断言。上表之外未受影响测试保持；不把原日志13fail逐条推定为测试错误或新建13条修复链。新增必要检查在原指定小模块补齐，原10个claim_wait测试同名保留且各安全语义可逐项追溯。

#### R16.6.2 主控接手后的单一路径补充（Pascal明确批准，2026-11-23）

本补充不改变公开契约，也不重开RFC/SPEC阶段。真实失败证据为`evidence/yquant-takeover-reader-red-clean-env.log`（29用例，6个failure记录及7个error记录；其中事件序号漂移已另在生产者审计投影处修复）。唯一新增授权路径为上表`tools/predictfun/tests/test_btc5m_live_events.py`，总28路径、不得增加第29条。仅允许：

- `test_all_nested_missing_and_unknown_keys_before_first_write`：将order的历史可缺省`diagnostic`列入与原`stop_detail`相同的精确兼容例外；其余任意缺键/未知键/首次写入前拒绝与原用例全部保持。新集成测试须单独证明缺diagnostic归一为null、非null诊断的每个必填键缺失仍拒绝。
- `test_a_claim_is_judged_before_it_is_booked_and_the_reader_agrees`：差1 atom已按§R16.6.1成为硬停、拒绝该账户证明；终态必须保留未核销库存，不再要求最后一次早于成交的对账位置等于最终库存。改为严格断言原生final仍不完整/需接管、硬停reason正确、未核销份额与实际执行净份额相等、无CASH_CONFIRMED；精确到账分支仍须最终持仓与有效对账一致并完成现金闭环。不得删除用例、修改1 atom注入、弱化为“无异常”，或放宽生产reader去接受矛盾资金事实。

实现继续由获明确授权的YQuant主控承担，原卡行政HOLD防并发；独立Validate仍由原`yquantreviewer`卡完成。此范围补充不是工程PASS或生产授权。此前27路径及范围修正记录保留历史。

### R16.7 最小真实消费者fixture与验收映射

复用原 `controlled::synthetic_controlled_two_round_trader`、`account::SyntheticTransport`、candidate_tests的真实core/clock/ACK/emitter helper及Python `native_stream`/metadata/原supervise测试模式。新r16_fixture只替换transport事实与时钟，不替换Broker、PredictFunTrader、execution parser、account历史/positions/官方投影、核销/drive/writer/reader。测试默认无socket、真实sign/keyring/API/RPC/数据库/资金方法一经调用即fail；cfg(test) fake签名不产生真实签名或交易。健康金融事件由实际producer输出，不手写JSON；坏流可在真实流副本作单点mutation。

固定结果先到脚本：同core第一轮经原adapter一次fakePOST→实际partial/完整净fill/费用/Closed→原官方消费者确认正claim、T=W0（复现09:55:06.275 CST的相对顺序）→多次原drive poll读到账前现金/持仓，assert无finish、0新sign/POST/RESERVE→推进5407ms，transport将同token份额移除且collateral精确增加P→原runtime_account_observation完成positions/history/chain/官方证据投影→Broker完整两式核销→原producer输出reconciliation/CASH_CONFIRMED→原reader清仅该等待→下一不同300s轮新输入经同core和fake执行器第二次POST。金额使用可配置synthetic合法份额/成本，另以run018公开2.0384份/0.936 USDT/2.0384 USDT作atoms算术fixture，不冒充原run事件重放或重新执行历史交易。

反向脚本：只让account adapter所用MarketData先看到完整官方结果及精确现金/移除证据，runtime官方消费者仍读到正常unpublished；先停新增并记W0、保留pending、不增B/R、不误foreign；后让runtime结果完整，当前generation重读证明→同核销链→下一轮真实fakePOST。正常unpublished使用原三态规则，不虚造结果；两个消费者都无官方结果时保持未知，不能生成到账证明。多claim脚本分别支付并确认，第一笔只入账且等待不清；全部闭合才恢复。所有正例最终都需原drive主动按受控deadline结束并由原final/ended/reader判定，不以abort任务或内存Ready代替续驱动。

| SPEC验收 | 最小真实断言与反例owner |
|---|---|
| D16-01 | r16_diagnostics→live_events/order→Python首写/reader：PREPARE/SIGNED_BOUND/FACTS/ACK/SEND_PERMIT/POST可达分支，stale分列、limit/depth/edge/round非stale；旧合法缺diagnostic流、非法键/bool/age/重复JSON键写前拒绝；decision无机会不编order |
| D16-02 | 原CandidateRefused0POST释放本attempt→下一合法轮；硬身份/ACK失败仍停止。timeout/401/坏响应首次poll后Unknown、原风险/单hash保留、sign/POST次数不增；真正RejectedFinal须权威闭合 |
| D16-03 | send_path_timing_benchmark新revision：T0在账户请求前、Tp在ACK+gate最后检查后，使用不为0的ACK延迟证明未截facts；冷/热declared历史与新hash反例，全部样本/缺测/nearest-rank；旧before NON_COMPARABLE |
| D16-04 | account/r16_tests延迟positions只带market、matches缺declared hash、冷/热两组；完整且原优先级，新未声明hash拒绝/memo不抹扫描 |
| D16-05 | 双故障及prepare竞争矩阵严格按R16.3，原typed错误相等，0sign/POST |
| D16-06 | r16_cash_drive的结果先到脚本；等待0新增且drive未finish，到账后原writer/reader见一次CASH_CONFIRMED，下一不同轮实际到fake执行器；禁止仅mock claimed_win或直接credit_claim |
| D16-07 | 原适配器现金证据先到、runtime结果后到；多claim分批；pending不增B/R/W0不重置、所有owner闭合才续轮；局部claim_wait现金先到旧Ready断言按§R16.6.1迁为WaitCash，不能替代原drive验收 |
| D16-08 | Q/P±1atom、错market/token/side/pair、foreign/多owner/额外现金、未移除库存/挂单/unknown/inflight/fee页缺失、旧generation/冲突重放均不恢复；完整成功读的账实失配为硬停而非可等待；§R16.6.1的opening测试排历史收益但不削startup/Cb证明；DRAW floor/零赔付残余、重复一次收益/一次confirmed |
| D16-09 | fake双时钟W0+599999/600000/600001ms、UTC/elapsed任一先到、原deadline更早/同tick、暂停/回拨；短读失败再成功不清cash wait；120s原读预算耗尽和硬stop/loss/EOF/输出故障两种顺序、同tick到账均0新增，first hard stop不改、尾查不重给600s；§R16.6.1两tests.rs函数迁移后保留完整fault矩阵，原producer输出后到硬stop且reader不会被CASH_CONFIRMED解锁 |
| D16-10 | readonly原core共同输入域pair：概率/方向/净EV/纯拒绝一致，live专属account/claim差异明示；paper账本、R13/R14/R15受影响回归、selector/activation/旧候选/旧证据未改，真实delta不是mtime归属 |

后续命令计划（本T2未执行；cwd=BOT；TARGET替换为当前worker scratch下独立构建目录，Python子进程同样显式CARGO_TARGET_DIR，禁止默认target）：

```text
cargo test --locked --offline --target-dir "$TARGET" --lib bot::runtime::live -- --nocapture
cargo test --locked --offline --target-dir "$TARGET" --lib service::predict_fun::account -- --nocapture
cargo test --locked --offline --target-dir "$TARGET" --lib service::predict_fun::controlled -- --nocapture
cargo test --locked --offline --target-dir "$TARGET" --lib bot::runtime::live_events -- --nocapture
cargo test --locked --offline --target-dir "$TARGET" --lib bot::runtime::live_control -- --nocapture
cargo test --locked --offline --target-dir "$TARGET" --lib bot::runtime::paper -- --nocapture
cargo test --locked --offline --target-dir "$TARGET" --lib bot::arbitrage::phase1 -- --nocapture
cargo check --locked --offline --all-targets --target-dir "$TARGET"
YQUANT_TIMING=1 YQUANT_TIMING_RUNS=9 YQUANT_SYNTH_RTT_MS=170 cargo test --locked --offline --target-dir "$TARGET" --lib bot::runtime::live_control::candidate_tests::send_timing_bench::send_path_timing_benchmark -- --ignored --exact --nocapture --test-threads=1
CARGO_TARGET_DIR="$TARGET" /home/pascal/workspace/yquant-investment/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_btc5m_r16_integrated.py
CARGO_TARGET_DIR="$TARGET" /home/pascal/workspace/yquant-investment/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_btc5m_live_events.py
```

探针使用上行完整限定名；实施若发现实际限定名不同先用--list核对，必须实跑1个目标测试，0test/--list不算通过。仅该已审阅离线ignored探针可显式执行，不跑其它ignored联网测试。9次RTT170是复用旧条件非验收总数门槛，冷热历史分别报告；不是生产达标。所有fixture临时目录使用当前worker scratch，Python测试继承TMPDIR，no network/secret guard显式开启，不安装依赖；缺依赖/必需验收被拒则保留增量block。

### R16.8 交付、身份与文档Gate

实施顺序：记录入口HEAD/精确文件hash及旧selector/activation/candidate身份→两个父文件最小同义迁移/原回归→同次adapter证据与Broker纯核对/统一commit→WaitCash与硬stop/driver→diagnostic/wire/新同版测量→真实Rust producer经原supervise/first writer/reader→最终独立候选与受影响回归。不得在本Design卡执行这些步骤。allowlist内的planned work不标成Gate finding；文档歧义/互相冲突才是finding，未闭合任意blocker/major/minor不能放行。

新唯一候选隔离根固定 `ROOT/data/reports/2026-11-23-btc5m-r16-integrated-validation/evidence/candidate-r16/`，最终binary为其 `polymarket-toolkits`；scratch独立target实际locked/offline build成功后create-new复制并核源/目标SHA，不覆盖已有目标或旧candidate-r14/r15，不修改btc5m_control.py selector/activation/README。候选manifest包含ROOT/BOT HEAD、全部本轮实际源文件hash、入口→最终delta（含新文件）、binary SHA、build命令/native exit、输入fixture与measurement_revision/hash；旧上游dirty通过入口bytes排除归属，mtime不作证。可变源码与历史candidate不相等不自动违规，须看该候选实际delta及本表边界。

新原始日志/JSON/文件delta仅create-new保存主题evidence/下，不能重写历史before/run018/旧report/旧卡PASS。唯一正式验收报告由独立Validate维护在 `ROOT/data/reports/2026-11-23-btc5m-r16-integrated-validation/report.md`（非本T2交付）；原始证据同主题evidence/，临时脚本/profile scratch不建任务状态镜像。报告逐D16项记录实际argv/cwd/native exit、候选/输入/运行条件/未验证项，最终候选改变则补跑受影响项，复用证据须身份/依赖/输入仍适用。

本T2完成前只检查三实体/V1.15/source pointer/本地引用、精确allowlist与新路径、物理行数/迁移边界、可计算两式/时间边界/全部D16 owner、历史保全和定向git diff --check。上游RFC/SPEC无需改冻结语义；其“下阶段Design需修订”是T1阶段记录，现已由本文兑现。业务测试/build/真实PredictFun或BSC≤5s/claim到账分布/部署/交易资金均NOT_EXECUTED；仍不声称能够识别观察上完全相同的抵消外部流，继承账户独占与SPEC §R16.4.8证据限度。工程离线PASS与生产许可严格分离。


## 本轮生效契约：公开 run JSON 参数化（2026-11-22）

来源：t_298e36df 与 Pascal 本轮已授权 Light 决定。下文旧 100/2/2、98/1/1/10/20 及历史算术、FAIL、原始 bytes 均保留为历史示例；本节替代其“唯一合法数值”含义，不追认旧运行。新入口显式要求 `controlled_run={budget_usdt,duration_seconds,operations_mode}`，资金仅复用 `strategies.btc_arb.order_usd` 和 `strategies.limits.{max_order_usd,max_market_usd,max_total_usd,max_loss_usd}`。缺省时旧 paper/legacy/replay 行为不变；同一候选 binary 与通用 launcher 从一份公开 JSON 冻结全 run 参数及 config SHA，不从账户现金自动推预算，不换 config 复用 activation。

参数关系为 target≤order≤market≤total≤budget；各金额必须有限、正数、非 bool、无溢出，最多六位 USDT 小数且≤1,000,000,000 USDT（限定到微 USDT，保证现有 f64 DecisionCore 输入的公开十进制往返唯一；风险 atoms 从原始 JSON 数字 token 精确解析，不从 f64 反算；budget_usdt 另可为≤18 位小数的十进制字符串（按 atoms 精确映射，不截断、不四舍五入、不容差），使 C0 能逐 atoms 等于观察到的 collateral，其余金额仍限六位小数）。loss 独立为正，不要求 loss<exposure；原 0.5 USDT dust floor 保留，不自动缩单。当前公开示例 budget=97、target/order/market=1、total=10、loss=20、duration=86400、unattended，仅示例。预算 B=C0+R−K、NAV=C0+net_pnl 的 C0 与 loss/各 cap 全部取本 run 冻结值，原账户现金单独保留。实际 exposure≥total 沿原黏性停止，不重启。

新 controller 从配置 duration 生成 deadline；若显式 CLI deadline/mode 存在须相同否则拒绝。native options/run/context/runtime 与现有双时钟一致；supervised 0<duration≤21600、unattended≤86400，旧 unsigned 6/72h 与旧 signed 6h 不变。started/final/ended 与严格 reader 使用同份 frozen 配置，禁止通过任意预算常数放宽检查；旧 run007..011 只读兼容、不回写。

定向消费者：config.StrictJson/load_controlled → native options → Broker LiveState；arbitrage 原 order_usd→DecisionCore target→attempt；live.seed_predict 预算准入；taker 预占/可用额/check_caps；live_control FINAL_SEND/total stop；live_accounting project_window 预算与 loss；Python control 固定值/started/deadline 与 live_events 首写、关系索引、ended/reader。超大文件仅原位接线，参数解析与新测试放小模块，不扩既有 tests.rs；本次修改仍须由独立 reviewer Validate。

Canonical `tools/predictfun/btc5m_launch.py` 仅机械归位获准旧 wrapper 步骤，复用 control/live_guard/reconcile 事实及 lazy PortfolioMongoLoader。import/参数检查/默认预检无执行副作用。run/window/auth、声明订单 hashes、精确旧 ARMED 目标显式输入；完整新鲜≤900s、同账户/config 的 reconcile、positions/history、无挂单、外部流及 gas、现金≥budget 的资格检查先于 activation 改动、旧 ARMED 轮换、arm、秘密读取及 child。失败上述副作用为零；成功仍需显式执行授权；精确匹配一条旧 ARMED、不通配删除、不重试，保存旧记录及 activation 原 bytes。原 child 再核账户/预算；本轮仅 fake collection/activation/child 离线验证。

## 1. 设计结论与范围

继续唯一 RoundTaker → DecisionCore → Broker → PredictFunTrader。显式新候选共用 phase1_net_shares，live 不创建 PaperCash；原 LiveState 保存实际金额/份额/预占/水位，新增运行元数据及原子量投影，不另建交易主账。Mongo 只记录一次 ARMED 拒绝屏障，不恢复余额、不自动续跑。健康单进程可做不同轮次的合法交易；任何停手/未知不可自愈回 READY；WAIT_CASH 是唯一可撤销的等待：claim 与已确认官方结果逐atoms精确相等时可清回 READY，其余仍停。

原 T2 唯一新增文件是本文；本次 Amendment 唯一可修改文件仍是本文。下文方案均为目标合同；部分接缝已由 L1 落盘，当前已见能力与尚待实现项严格按§2增量说明区分，不能把 planned implementation 当已执行结果。当前不构建、运行业务、读交易秘密、连接 Mongo/私有 API/RPC、真实签名/认证/订单/取消/资金、发外部告警、改服务/调度/权限/profile/依赖或 commit/push。不能以文档静态通过证明可上线或有 alpha。

增量优先级：仅获验收的显式 07-007 候选替代旧 signed legacy / signed-null / 无跨进程保护对应 non-goal；旧07-002/003/004/005/006其余契约、历史 FAIL 和证据不改。普通 paper/live、其他 venue/策略、history/replay、unsigned v2、observer unsigned-only 默认不变；不做混合模型、动量、OBI、主动退出新策略、通用 OMS 或资金循环服务。

## 2. 基线 reconcile 与源码事实

路径均相对 BOT；行号为本轮 read_file 的定位。ROOT main、既有07-006三文档/pipeline/BOT dirty 由 git status 实际观察；不把共享修改归本卡。入场 HEAD 沿上游 ROOT `9e06cdac513cd7ec616ee4f7877913330195fcf2`、BOT `8f5dcba5b0334623bb0faf5c861fc342c1fe514e`，后续需最终身份核验。

| 接缝 | 保留的现有能力 / 证据 | 本轮真实差量 |
|---|---|---|
| arbitrage.rs:47–103,712–832 | 唯一 core / 原 phase1 tick / 正 fill confirm；observer已隔离live | is_phase1 目前由paper决定；原同步 take_candidate 无 live await 接线 |
| phase1.rs:223–365；paper.rs:641–698,880–1063 | 不可变候选、revision、共享 recheck、phase1 clock / 输出失败位 | phase1运行元数据可被live借用；不复制模型或给live虚拟现金 |
| runtime.rs:624–766；runtime/live.rs:75–253,427–559 | 先预占、hash/tombstone、真实snapshot、水位/coverage、原子净现金/净库存、账户对账 | 投影delta的净字段/实际应用有效性；原子预算/mark/latch和控制事件 |
| venue.rs:89–237 | submission/quantity/closure/accounting分离；零成交VWAP例外 | 类型化发送hook、已签边界与严格公开投影；不换OMS |
| fills.rs:87–247；predict_fun.rs:1425–1505 | 固定hash、真实签名/鉴权、原单次POST；NoReplay | 最后 token() 仍可能await；当前无耐久ACK及最终core检查 |
| fills.rs:482–493；predict_fun.rs:477–525,1610–1639 | 签名 maker/taker、最坏档位、限价、实际请求body | 新域验证BUY份额费及原子已签净到账下界；不信option名称 |
| predict_fun.rs:350–352；fills.rs:868–886 | ApiCreatedOrder当前仅order_id；原chain.settled/closed已做真实证明但snapshot不带结构化证明标志 | 接住官方removalLockedUntil和同一读代settled证明，不把不存在字段当已有；只加元数据投影 |
| account.rs:239–290,1098–1295 | 固定账户/decimals/余额/权限、AccountGate预算与unconfirmed | 最后检查只能豁免本单Prepared的自占位，不能误封正路径或放过别单 |
| control.py:957–1064,1565–1703 | 固定签名child、keyring/环境来源、supervise/首次写 | 新版本严格writer/reader、ACK、单账户锁、Mongo屏障、运行final |
| observer.py:965–1015 | reader在调用时局部import btc5m_control | 当前run可能后续按原路径读源码；见§9，不用“已经加载”推定可改 |

07-002已验离线执行/SDK，t_3cfa9034/run3874 PASS_OFFLINE_REPAIR、t_655f69cf/run3876 PASS_LAUNCH_WIRING复用原签收。旧unknown→planned量问题已修，不再列待修；local_signer/cli/sdk_ops固定入口也已存在，不重建或直接修改。实际场馆、余额/批准额/Gas和存储部署仍未验证。

本轮只读官方公开网页：place-orders、fees、order-lifecycle（2026-11-19，链接见§12），明确201非final、MARKET部分FILLED、BUY扣份额及signed fee cap；无账户访问。提取服务403后以浏览器读公开正文，不是绕过venue登录。

V1.1 reconcile（2026-11-19）：以上表格、官方网页读取和行数是原 V1.0 的阶段基线，不冒称本卡重做。主控卡面已核 run3882 的局部候选及 cargo check native0、476 passed / 0 failed / 3 ignored；新增4例仅局部 apply/Broker 回归，本卡未重跑，不能当完整 live 消费者验收。此次定向 read_file 实见 live_events.rs 共1356行，生产1–1172、cfg(test)从1174开始，8例见§11.1；LiveEvent.payload、emitter.envelope/write仍接 Value（217/640/761），尚未满足严格 typed 合同。本修订只给其 types/tests 拆分落点，不将原 T3 计划重新立项。

剩余工程缺口仍保留：paper.rs:900 仅 paper.phase1、live evaluation 恒 false；taker 新入口 check_entry 使用 usd0 全拒绝；共享 emitter/seq/lane/pending 和 expected_hash/ACK/parent-stop 未装配；fills 同步 permit 后 request 再 token.await，FINAL_SEND 及 State→handle→gate/首 poll 线性化未闭合；main 五参数/manifest、完整 native 正反例和 Rust producer→supervise→reader 尚待完成。这些是既有§3–8/§11的 T3 backlog，不是本卡完成声明，也不是新增设计范围。

## 3. 模式、装配与固定输入

### 3.1 显式选择，不升级旧入口

原 control.build_parser 新增 `--live-contract phase1_net_shares`、`--operations-mode supervised|unattended`、`--risk-window-id`、`--authorization-ref`、`--deadline-at`。五者在新signed域全部必需；缺部分、unsigned携带、signed+observer、非固定账户、非正时长或超过按 mode 的 activation 上限（supervised≤6h、unattended≤24h；等号允许，未知 mode 拒绝）均在秘密前拒绝。无新开关时维持旧入口和版本，不靠public config的 enable_trading 隐式升级。原 `--duration-hours 6|72` 不变；新live不能带该选项，旧模式也不能带新deadline。argparse需区分未提供与显式提供，不能因旧default=6误拒新入口。

Rust main增加相应 `--controlled-live-contract`、`--controlled-operations-mode`、`--controlled-risk-window-id`、`--controlled-authorization-ref`、`--controlled-live-manifest`。最后一项不是任意路径：只能为本run证据目录的 `live-context.json`，父按固定路径构造；它是无秘密公开启动上下文而非批准token。ControlledRun增加 `live: Option<ControlledLiveOptions>`，原构造器统一None；检索未见定义以外ControlledRun字面构造。新增 `from_live_arguments` 只服务显式新域；options 构造、run/manifest 预算绑定和 `check_runtime_config` 共用 `OperationsMode::allows_duration`，按完整精度判定 `0<duration≤21600秒`（supervised）或 `0<duration≤86400秒`（unattended），三处不使用各自常量、不因秒数截断放行超限；运行 validator 还核对预算与实际期限一致。父端 controller/activation guard/metadata 采用同义 mode-aware 判定；未知 mode/非正时长拒绝。原生 options→activation/context→runtime 的 6h/6h+1s/24h/24h+1s 及毫秒邻值由离线原入口回归覆盖，不等于真实 24h 长跑或上线许可；旧from_arguments仍精确6h/unsigned72h。受控ID统一原RUN_ID_PATTERN（先语法，不修补），非新域不读取manifest。

Ctx::connect_with_trader继续原trader_factory/account gate。新域在原signed分支构造原Broker后调用 `with_controlled_live(options, clock, supervision)`，要求live/PredictFun/chain56/fixed PredictAccount、原limits和模型固定、PaperCash=None；复用原SystemClock（UTC+含暂停elapsed）。Broker::is_phase1/phase1_clock/entries_stopped支持这一明确上下文。RoundTaker仍据is_phase1创建同DecisionCore::phase1；observer原is_live拒绝保留。

trade_phase1仅将调用处变为：paper用原take_candidate同步返回；live用原Broker的新 `take_live_candidate(...).await`，都反馈正净份额给confirm_fill。不把既有TakeResult变体或所有策略调用改成新协议。live Coinbase在broker秘密/签名/POST前以SOURCE_NOT_ALLOWED拒绝；保留原core可审计的经济诊断，不向07-005 decision.reason塞未定义枚举。live专属拒绝放order/stop.reason；无attempt的来源拒绝以stop SOURCE_NOT_ALLOWED停新增。common Binance域对拍core而非两个公式。

### 3.2 启动上下文与生产绑定的信任边界

仅新live读取固定 `BOT/tools/predictfun/btc5m-live-activation.json`。这是未来人工批准后才可物化的L1公共部署绑定，当前不创建；不是新授权系统、签名token或CLI任意路径。离线测试通过函数参数注入严格同形fake，生产main不开放测试替身。缺文件/未知版本/修改身份均拒绝，不以旧budget bool替代。

该对象精确字段：schema_version=`btc5m-live-activation/1`、authorization_ref、risk_window_id、operations_mode、account_identity、not_before、deadline_at、candidate_digest、storage_binding、gas_policy、takeover_ref。其余字段递归拒绝；ID/时间/地址沿SPEC；takeover_ref是同受控公开ID，非消息地址/自由联系人。storage_binding精确为 deployment_id、database、collection、credential_env、endpoint_id；gas_policy精确为 payer_address、minimum_balance_atoms、maximum_consumption_atoms。两预算均合法BNB atoms且>0，payer限原ChainRead实际读取的account_identity.signer_address（固定Predict Account的owner/Gas支付者），不得用持有USDT的trading_address替代；其他支付者当前GAS_UNAVAILABLE，不扩RPC路径。未批准输入不填伪值。

候选部署提案：database=`tradingagents`，collection=`07_trading_btc5m_live_guard`，credential_env=`YQUANT_BTC5M_GUARD_MONGO_URI`；这是待批准的新独立集合绑定，不声称存在，不访问portfolio/UD/task集合。deployment_id为受控ID；endpoint_id为严格对象{scheme,hosts,replica_set,tls}，scheme固定mongodb（本轮不支持SRV动态改目标），hosts为已批准的规范host:port有序数组，replica_set为已批准名称或显式null，tls为明确bool。URI解析仅在内存提取这四项与绑定精确比较，禁止隐藏多主机/替换URI query中的库或TLS/replicaSet覆盖，未知连接选项拒绝；pymongo固定主机/primary及上述读写策略。未来主控填定并核同物理部署，当前代码无默认实际连接。正式激活冻结一个绑定及其candidate_digest；CLI、run/window、环境替换库名或集合名不能覆盖。URI只从该单一已批准env键读取，不全量load_dotenv、不从URI推断另一个库、不把URI/摘要传child或写证据。URI变化即不能自证仍在同一Mongo部署，须生产Gate核验而非“可连接即通过”。同UID/管理员可改代码、绑定或删库是明确可信操作员边界，不宣称抵御恶意绕过。

固定顺序：公共配置/参数/候选身份/批准绑定语法 → 账户OS锁 → Mongo单次ARMED创建及耐久读回 → 新证据exclusive创建和fsync → 原API来源/keyring一次读取 → 原单child → 原官方完整startup账户/权限/预算核对 → READY。失败不fallback、不自动换run/库/集合/环境/签名器。只枚举环境键存在性的检查可提前；`_api_source`及`_read_owned`实际读交易秘密必须后移至屏障通过。Mongo自身凭据按上述单源仅在获批存储阶段读取，fake两类真实秘密读取计数均0。

`live-context.json`精确为schema_version=`btc5m-live-context/1`、run_id、risk_window_id、authorization_ref、operations_mode、account_identity、started_at、deadline_at、candidate_digest、asset_units、gas_policy、recovery_policy、cash_recovery_policy；不含storage URI、数据库凭据、私钥、JWT、签名字节。父文件exclusive-create/fsync、目录fsync并严格读回后传给child；child核对原argv/固定常量，管道无有效监督时拒绝。文件本身不授予资金动作，实际许可仍由外部执行和风控确认。

## 4. 发送链、耐久ACK与原子边界

### 4.1 新类型接缝及所有权

| 拟新增类型 / 落点 | 精确职责 |
|---|---|
| config/controlled_live.rs::ControlledLiveOptions | typed模式/公开关联/期限/Gas；从原受控入口解析，无Default live |
| runtime/phase1_control.rs | 提取paper.rs现有with_phase1/is_phase1/phase1_clock/phase1_entries_stopped四方法；unsigned仍读原PaperCash.phase1；live读LiveState.controlled.phase1，复用Phase1Run类型 |
| runtime/live_control.rs::ControlledLiveState | 原State.live内唯一运行元数据：phase1、pending candidate、attempt关联、traded原官方身份、latch/stop/READY状态、输出seq；不存第二B/K/R现金表 |
| runtime/live_control.rs::LiveCandidateGuard | 持有Broker共享state/原candidate/clock及监督确认句柄；不拥有可独立下单的client或签名材料 |
| service/venue.rs::ControlledSendGuard | 对象安全窄trait：准备阶段核对事实、等待关键order耐久确认、最后同步许可；默认不支持，不能忽略hook而调用普通place |
| service/venue.rs::SignedExecutionBound | account/market/token/route/fee、gross request、maker/taker原子约束、max_cash/min_net、expiration、hash；无signature/salt/raw请求 |
| service/predict_fun/controlled.rs | 原适配器guarded薄接线、signed bound证明与同一单次写transport；不含模型/资金主账 |
| service/predict_fun/account/controlled.rs | AccountGate::with_prepared_attempt：只允许本单Prepared占位，锁内检查其他block；不清原gate原因 |
| runtime/live_events.rs | 从真实State/ExecutionSnapshot/实际AppliedExecution构造typed事件，拥有有界序号/编码/原stdout出口；委托子types校验，不再内嵌wire定义或测试；无余额应用逻辑 |
| runtime/live_events/types.rs | 私有子模块：SPEC严格wire结构/枚举、键表、标量及递归校验和序列化；只声明数据，不读Broker/venue、不生成delta/seq、不做I/O；父模块保持原导入门面 |
| runtime/live_events/tests.rs | cfg(test)私有子模块：原8例全部同义迁移、严格schema及原子facts/delta投影回归；生产路径与跨消费者测试仍见§11.1 |
| runtime/live_accounting.rs | 原LiveState的原子风险/估值/官方claim投影及loss更新；不以f64 holdings反推原子金额 |
| runtime/live_control/channel.rs | 同stdin的新版小型帧/ACK等待与EOF监视；不建服务/新行情轮询/新心跳机制 |

新增OrderVenue方法 `controlled_reservation_atoms(planned)` 和 `place_controlled_tracked(planned, handle, guard)` 均默认EXECUTION_NOT_ENABLED；前者仅在已核新域BUY市场/份额费metadata下求预占，后者由PredictFunTrader调用与place_tracked共用的原准备/签名/POST主体，仅显式新域带Some(guard)。普通tracked分支None保持原行为。BoundOrder/AttemptHandle是原订单关联，不把candidate或模型塞进全交易所API DTO。

新域事件和执行共用原Broker的单一异步operation lane（tokio::sync::Mutex，仅串行已有run操作，不是另一个Broker/账本/worker）：take_live_candidate、sync/seed/observe/settle/final及其实际producer依次进入，锁外网络await可持lane但不可持State锁。同步EVALUATE使用try_lock，忙则拒绝并停新增，不能等待时仍写另一seq；其后live提交重新核pending candidate。控制watcher仅改State sticky flags、notify，不直接发事件、不抢lane。每一lane操作在原State锁分配序号/构造不可变快照，释放State后按序输出；未完成flush不让下一producer插队。FINAL_SEND已持lane，仅取State/handle/gate，不再获取输出锁。这样不需通用outbox/无限队列，也不把Broker锁跨await；并发预占者必须经同lane及State双重约束。

### 4.2 唯一顺序

1. 原core EVALUATE → Broker记录决策。Broker同State锁核身份、revision、core PRE_SUBMIT、新时钟、停止/loss/账户/原子预算；建立原AttemptHandle和原R0/tombstone。无context裸BUY在所有新phase1入口先拒绝，不能从普通take绕过。
2. 锁外执行原适配器的账户、最终book、权限、签名、JWT、ERC1271等待。每一等待后先检查sticky stop；检测停止即退出后续准备，但已存在hash/事实仍保留。最终book/fee/route必须与冻结候选一致（按原镜像/精度正规化后逐字段、不是容差吞差异）；变化则INPUT_CHANGED终结旧candidate，0POST。更好价也不能暗换旧candidate输入。2026-11-21轻量纠错：此“一致”指最终盘口完整且支持冻结决策——非空、不越过候选限价、深度覆盖冻结股数；越限或深度不足为候选级拒绝（释放本候选、NOT_SUBMITTED证据、不终结窗口），身份/hash/ACK/bound/账户/风控不一致仍硬终止，缺一侧盘口为READ_UNAVAILABLE；不改动本条其他语义。
3. 由已构造order和部署生成SignedExecutionBound；先在原handle保存hash/Prepared，不泄露签名字节。序列化完整 `order` 事件，经stdout发给原supervisor。此时可能阻塞，绝不算FINAL_SEND已经通过。
4. supervisor按§7严格校验该行及前缀，首次追加events.jsonl → flush → fsync文件 → 同目标readback精确本行 → 才写ACK。新started/public-config/live-context及目录必须已耐久；不能用flush或文档里的durability=true冒fsync。ACK丢失/超时/错关联不发送、不重新签名；屏障仍ARMED。
5. 所有await/关键order ACK后，用原client准备完整HTTP请求/单次future；其中JWT已取得、body序列化完成，第一次可能交给transport前再获取最新CheckTime，调用原candidate.recheck（同模型/常量）并重查全部门禁，生成FINAL_SEND快照。不能把旧checked_at或ACK时钟当最终时钟。
6. 最后同锁许可与初次transport poll是一个不可分离的本地线性化区间，细节如下；退出区间后才await网络完成。只有一次初始POST，不401重发、不新salt补单、不重广播同hash。
7. 原snapshot/apply_snapshot与sync_predict消费同hash全部真实事实，晚到/越期限/partial/负EV照记；只把实际正net_inventory增量反馈core entered。已知gross但net不全，账户闭锁和round tombstone仍阻止重下。

关键order的Prepared持久证据在发送前完成；FINAL_SEND本身不能在最终检查与transport之间做阻塞写入。因此其typed快照和下一状态事件在首次poll后按序输出；若失败，资金事实不回滚，audit INCOMPLETE，冷启动仍拒绝。磁盘上Prepared+无后续不能证明未发送：人工按同hash/全窗口核对。不是对每个网络字节做跨进程事务。

### 4.3 stop/EOF与第一次发送许可原子关系

原paper watcher逐字节D/EOF不改；新live仅装一个新版watcher，仍独占原stdin，不开第二读者。生产继承stdin必须验证为pipe且父端有效；watcher先把Readiness结果交Broker，READY前不发送。

新版控制帧仅两种：原单字节 `D`（deadline）；或ASCII `A <seq> <signed_hash>\n`。seq为规范正整数、hash先0x+64hex校验，完整帧≤160 bytes，最多一个待ACK；ACK必须对应本run当前唯一等待的已持久order.seq/hash。无等待/重复/倒序/未来/坏帧/partial EOF → CONTROL_CHANNEL；EOF/读错 → PARENT_LOST。父不可传任意命令、reset、金额或签名。supervisor单线程先判停止/deadline再发ACK，stop关闭stdin，不再发ACK。

watcher发现EOF/stop立即获取原State锁置sticky stop、清尚未消费的ACK许可并notify；它不依赖下个tick、不调用网络。不靠MAX_FAILED_TICKS=3给新增宽限。监督者活着但暂停/远程不可达，下一单必须重新获同hash耐久ACK，无ACK不准发；不声称检测一个保持打开却暂停的父进程的精确失联瞬间，不新造心跳阈值。

最终send使用 `poll_fn`/等价Future包装：第一个poll持State → AttemptHandle → AccountGate固定锁序；核新CheckTime/停止/loss/上下文/账户检查epoch/ACK/signed bound，消耗一次性许可，将原handle/账户门禁标记MayHaveSubmitted，随后在同一poll且无其他await/日志/fsync/锁等待步骤时首次poll原HTTP发送future。该poll必须非阻塞；不是持锁await网络。后续poll不重查并重新发送，只推进同一future；所有准备可能挂起的工作必须在之前完成。guard与writer提前确保事件容量和序号，不因FINAL_SEND输出申请额外锁/IO。

stop先取得State锁则本单0次transport poll/0POST；发送区间先取得锁则此单已是in-flight，随后EOF不能把它改成NotSubmitted，必须同hash继续有界读或交接。对方进程死亡至本机EOF被观察之间不是本方案可消除的物理时间差；验收线性化的是本机观察到stop与首次交付transport。测试必须把第一次poll Pending也算可能提交，不能等HTTP201才立tombstone。不能让final check放在authed_write外，而其内部再次token().await后直接发送。

AccountGate新helper在已有accounts锁内检查budget、mismatch、reconciliation、failed_reads，unconfirmed集合必须恰仅本attempt且其原状态字符串为PREPARED（与handle的AttemptPhase::Prepared同检）；任何别单/MAY_HAVE_SUBMITTED均拒绝。随后同区间将原gate本项更新为MAY_HAVE_SUBMITTED，不调用会再次锁gate的mark_submitted。所有新锁按State→handle→gate，watcher只锁State；不跨await持锁，不引入gate→State反向回调。

ACK等待使用原15秒请求上界与本run deadline的较小值；用原含暂停clock检查，超时AUDIT_UNAVAILABLE停新增。等待不延长5秒span/10秒age/30秒入场界；ACK回来仍需最终重验。错误不能从准备future Drop自动释放；只有明确Prepared+NotSubmitted未交transport的返回才沿原release_not_submitted一次释放。

### 4.4 已签边界、费用与正路径

只新增07-007 BUY MARKET域的边界证明；普通reservation_atoms/cash_with_fee保留。沿原market_amounts与order构造，不增加slippage/isMinAmountOut参数、不把MARKET改成maker/FOK策略。若SDK/API设置将来变化，当前guard不能凭名字认定保证。

- `S=10^18`，Q=order.takerAmount，A=order.makerAmount，b=order.feeRateBps。要求Q精确对应候选下取整gross原子量，signed side=BUY、market/token/account/route及b与候选/实际部署一致；不能因5位有效数字截量而偷偷缩单。A/Q用U512交叉乘法证明不超过candidate.limit。构造时quantity或route变动直接INPUT_CHANGED。
- 官方BUY费从收到份额扣，已签b是费率上界；原子量保守下界 `N_min=Q−floor(Q*b/10000)`，因为min(p,1−p)/p≤1且链费向下舍入。这是最坏执行约束，不是把actual fee改成模型费；真实实际fee/net仍仅来自原snapshot。支持的签名b须满足已读官方合约cap≤1000；core原模型允许域不改，不能证明venue签名域则SIGNED_BOUND_UNPROVEN。
- 对这一已证明BUY份额费域，`max_cash=A`、`min_net_shares=N_min>0`。新 `controlled_reservation_atoms`只在guarded BUY返回候选limit下的向上取整最坏cash（最终A不得超过它）；不沿用普通路径可能额外现金费的保守cash_with_fee，否则每笔接近1的合法净份额单都会被多预占拦截（单笔上限 `MAX_ORDER_USDT=1`，见 §5.2 与 `live_accounting.rs:34`）。fills::check_signed_bound在Some(guard)时必须调用这一已证明域的精确A≤R0检查，而不是仍无条件走原cash_with_fee；None保持原完整检查不变。未证明BUY费方向/部署则0签名/POST，而非假设fee=0。
- 原phase1模型仍按07-005算净EV/edge。FINAL_SEND除原recheck外，以实际已签约束保守检查 `N_min*fair−A ≥ 0.03*Q`（统一单位后原core经济比较，金额边界原子量零容差），不通过不发送；不能以平均VWAP通过替代最坏已签价的净EV。不同费率/最坏边界拒绝属于执行约束，不修改同core EVALUATE公式。
- 全单最小N_min不是任何partial保证全额到账；partial按实际gross和费用核算。cap/claim/gross不可拿N_min替代。unexpected collateral fee先按事实入账并保留超预占风险/停手，不能剪实际fee以维护上述假设。

离线正例须含非零bps、合法原构造signed ratio、1/1/10（单笔/市场/总额；下单下界门槛 0.5，`live_accounting.rs:30`）内的实际发送，不能只用fee0、全部拒绝或替换PredictFunTrader证明能力；允许最坏约束比模型初选更严格，但不能把所有合法输入都封死。

已用Fraction独立复算的边界算术向量（不是实际成交/原core输出）：Q=5股份、A=2 USDT、b=200、假设fair=0.5时，N_min=4.9股份，最坏净EV=0.45 USDT，edge=0.09 USDT/gross share，单笔恰2；两个不同市场累计成本4≤10。（2026-11-22 口径注：该向量描述的“单笔恰2 USDT”是 1u 口径落地前的历史算术检验事实，原文保留；现行契约下该 2 USDT 单已被 `Blocked::OrderCap` 拒绝——单笔上限 1、市场上限 1（§5.2、`taker.rs:429–436`），向量仅用于费用下界的算术核对，不再代表可发送尺寸。）另核36个quantity/price/rate原子向量的费用下界及−20阈值±1atom。Implement原生正路径仍必须由真实core算其fair/方向，不把这个假设fair硬塞生产core或伪造回执。

## 5. 实际原子量、预算、估值与窗口

### 5.1 原账本扩展，不用Python账本替代

原LiveState.net_cash/net_inventory、applied_q/cash/fees、reservations/watermarks继续唯一原子实绩。controlled元数据只记attempt↔candidate/market、官方结果/mark有效性、stop/latch/seq与时间关联。B/K/R/V均从这一State和其官方归属记录投影；不在Mongo、Python、另一个Broker重复存可交易余额。旧Holding的f64仍作既有显示/兼容视图，新域预算/损失判断不得从该f64乘1e18反求。

apply_snapshot在原State锁内先完整验证再commit。其现有Delta只有四gross/fee字段且default不能区分“未应用”与0；新增内部 `AppliedExecution`结果含原Delta、net_cash_delta:Option<U256>、net_inventory_delta:Option<U256>、applied:bool、duplicate:bool、accounting_complete:bool。原公开Delta及apply_cumulative/其他消费者契约不改：新增受控包装/结果出口，同一原commit产生，不能在Python再算成交易应用。完整commit给六个实际差额；未完整未应用为null；旧/重复快照确认无新增为六个0。原generation/coverage保留，不以其新gross倒推已知field覆盖。

同一LiveState为新域增加 `observed_risk_floor: HashMap<attempt_id,U256>`：在任何snapshot应用前，仅在身份匹配后以已知gross_cash+collateral_fee、net_cash的较大值单调上调保守现金风险下界；未知不覆盖旧值。包括overfill/费用修订等导致原apply拒绝的事实，也必须保留原snapshot的typed审计投影并使status=CONFLICT/全账户停新增，P至少=max(R0,observed_risk_floor)−已应用cash，绝不因拒绝commit而把已经观测的更高风险丢掉。它是原预占的风险下界，不是另一份已成交余额；无法正常入账的现金/NAV派生null，不用裁剪成request或伪造delta。新域原子预算不使用原protected_risk的较低旧值遮盖该下界。

startup新域要求无open_orders、无未解释/继承持仓、无foreign风险且观察到的 collateral atoms 与本 run C0（`params.budget`）加已核验 claim atoms 逐 atoms 相等（`live.rs` 的 `seed_predict` 中 `cash_matches_budget_and_claims(budget, collateral, claim_cash)` 不等即 bail `CASH_BUDGET_MISMATCH`，早于任何下单；行号仅辅助，当前约 live.rs:782–788；`btc5m_launch.py` preflight 同义）；原seed_predict其他模式仍按原语义。budget bool仅确认原98分配，不创造真实余额。完整baseline和每次runtime账户检查保存checked_at/elapsed及状态epoch于同State；最终check要求该次准备的完整对账仍对应同版本，≤10秒receipt-bound且无待核风险/失败标志。它是原phase1时效尺度复用，不声称RPC余额实时；每次准备必须真实读全，不靠旧gate success永续放行。

### 5.2 可计算口径

R2 现行停止链：`live_control::refresh_live_risk` 从原 `risk_exposure` 读取已存在 cost+reserved，达到 `10*S`（含等号）用既有 `stop_with_detail("MANUAL_STOP", "TOTAL_CAP", true, ...)` 停止；原 `wait_controlled_stop` 轮询时同步刷新既存 live 敞口（不重新分类在飞 incomplete 事实），再由原 drive 执行有界 cleanup/final 并返回。该 paper.rs 窄 wiring 在无 live.controlled 时为 no-op，不改 paper 决策/交易语义。拟新增 `w` 尚未产生时不计入现存敞口，单纯 K+P+w 超限仅拒候选。首个 stop/20u loss latch 不被覆盖，不重启、不造平仓，未解订单/预占/净持仓与接管信息仍保留。

R2 账户归零：`account::settled_to_zero` 在原 `MarketData::market`/settlement 判定前后比对读取前历史 known 的完整 Yes/No token 对、目标 token 明确归属及侧别；`PredictFunClient::market` 在更新已知缓存前拒绝同 id 替换/互换/不完整 outcome 对，避免第二次读取误接纳。沿原 settle_from_facts + settlement_payout，仅 RESOLVED/CLOSED、非 contested 且 payout=0 可解释；tie/正兑付/缺元数据/矛盾/pending/额外仓位/数量不符仍 fail-closed，不新增请求/客户端/事件/错误分类。

S按started.asset_units校验，当前collateral/share/gas均18（原ChainRead显式验证USDT18、原股份/BNB部署常量）；不猜decimals。USDT金额U256、PNL用有符号整数（checked运算，拒overflow/−0）；中间乘除U512。BNB独列，不与USDT相加。

| 值 | 同State原子投影 / 准入约束 |
|---|---|
| C0 | 本 run 配置冻结的分配预算，非整个账户余额；无该字段的 legacy 记录为 98*S（`live_accounting.rs:32 BUDGET_C0_USDT`，`budget_c0_atoms()` 在 :52–54） |
| B | C0−窗口实际BUY net_cash累计＋已核同目标现金回收；本轮MANUAL_PAUSE不在进程中执行资金回收，因此正常交易路径不增加赎回收入 |
| K | 本窗口已应用且尚未经济释放/回收的实际net现金成本，按attempt/token/market归属；正claim仍保留成本 |
| P | 原reservations的保守未闭合现金余量；已应用c后该单余量=max(R0,已知更高风险)−c，FINAL且核算完整才释放未成交部分；未知保留原值 |
| 每单/市场/总额 | 0.5*S≤w≤1*S（下界 `MIN_ORDER_ATOMS`、上界 `MAX_ORDER_USDT`）；K_m+P_m+w≤1*S；K+P+w≤10*S；精确等号允许，禁止EPS/自动升额/缩单 |
| available | min(B−P，完整官方可支用USDT−未闭合预占)，下界不足/未知不交易；外部流不能增C0 |
| V | 有效净股份按原mid估值＋官方正claim；一个token只能在shares或claim中取一次，不双算 |
| U / R | U=V−K；R为已经经济实现的净收益。官方零兑付可经济移除成本K并实现−basis，实际链残余股份另列，不造cash回款 |
| 恒等式 | 完整无外部流：B=C0+R−K；NAV=B+V；net_pnl=R+U=NAV−C0（C0 取本 run 冻结值，legacy 示例 98*S）；显示累计fee不再扣一次 |
| loss | net_pnl≤−20*S含等号即永久latch；未知mark/net/fees则先DATA_UNAVAILABLE停新增，不能以0/成本/旧mark补绿 |

mark只沿原observe/mid_of及合法性，缺book/失败先invalidate新域mark；每次观察/成交/费用/官方结果后同锁投影并更新latch，且FINAL_SEND再检查。将合法f64 mark转值时用其确定的有理表示（按IEEE754位分解）计算floor(net_atoms*mark)，全程checked/U512；不能先以f64乘巨额atoms造成阈值误判。该数注明VALUATION非cash，不修改paper mark或模型。原始amount事实仍原子量，模型float容差不传递到预算/loss。

新域没有自动SELL/merge/redeem/提款。正claim→WAIT_CASH，B不加claim，K不减，V可用官方值；收到人工资金回收事实也不返回READY，除非该事实是账户读回证明、且与已确认官方结果逐atoms精确相等的claim。本轮不把手工SDK后的账户差额自动当本run收入，若观察到不属窗口的变化先RECONCILIATION_REQUIRED。未来受权人工报告可用同目标份额/现金读回证明回收，不能回写旧窗口事件或清latch。

Gas策略沿原ChainRead的signer_address原生BNB余额读回；trading_address仅为USDT持仓及账户互斥作用域，不是本支持路径的Gas付款者。不增加任意payer RPC。记录初始G0与每次完整G：G低于minimum或G0−G大于等于maximum即GAS_BUDGET停新增；余额不明/上升或不解释的变化GAS_UNAVAILABLE/RECONCILIATION_REQUIRED，不猜充值。这个保守额度控制是消费余额的运行门禁，不是逐tx费用归属；gas_paid_atoms仍null/NOT_MEASURED直到原消费者可证同payer/tx费用。签名/POST/取消API不消耗链Gas不等于整个窗口Gas0，BNB上限必须未来另批。20 USDT只是停止新增阈值，不保证最大损失/全币种成本≤20。

## 6. 单实例、Mongo屏障、崩溃与人工接管

### 6.1 锁与拒绝屏障

OS锁固定 `ROOT/data/runtime/btc5m-live/locks/predict_fun-56-<固定trading_address小写>-predict-account.lock`。原launcher标准库fcntl.flock(LOCK_EX|LOCK_NB)，生产无路径覆盖；跨run/window/两种值守模式共用，unsigned不触碰。只新建需要的目录/常规锁文件（新建mode0700/0600），不chmod既有资源；拒目录/文件symlink、非本UID、非regular、多硬链接。文件不以退出unlink，以免inode换锁。锁FD父持有到child确证退出/交接，不把锁文件存在当锁有效。

仅父持FD也不足以覆盖父死子活；Mongo屏障保证另一合作启动仍拒绝。后续若父无法确证child退出，不声明锁可解除的安全资金状态；无论OS最终释放，ARMED不变。所有受控新signed必须同scope屏障；旧signed入口以后真实授权也不得与此账户并行，运行占用只保证合作入口，非受控SDK/其他主机需要账户独占声明，不冒称全交易所互斥。

Mongo `_id = predict_fun:56:<固定trading_address小写>:predict-account`，不含run/window/host/operations/signer。先严格地址格式再规范身份比较；host仅scope初始归属，来自os.uname受控短标识，不影响唯一键。屏障恰为SPEC §4.bis字段：_id、schema_version=`btc5m-live-guard/1`、scope={account_identity全部字段,host}、risk_window_id、run_id、state=ARMED、armed_at、authorization_ref、candidate_digest。无余额/订单恢复字段、CLEAN、TTL、owner续租或自动删除。

原launcher同进程lazy import项目已有pymongo（ROOT/.venv/bin/python），不import MongoWriter/LocalMongoAdapter。集合必须已由未来批准部署物化；启动仅list/name/schema绑定只读核对，不create_collection/create_index，不依赖insert隐式建生产集合。以Mongo内建_id唯一性做一次insert_one，WriteConcern(w='majority',j=True)，自动可重试写显式retryWrites=False；primary + ReadConcern('majority')同目标find_one精确核scope/版本/全部原始内容。禁止先find再upsert、超时重insert、找副本旧数据凑通过；读回成功也不能把超时不明确的write重新算成功启动。

durability是实际ACK和读回行为，不是文档字段。driver/绑定/集合/所需存储保证缺失均RECOVERY_GUARD_UNAVAILABLE，duplicate-key或已有/坏版本屏障为RECONCILIATION_REQUIRED，0交易secret/child/POST。现有Mongo若不能majority+j则阻断激活，不修改部署、不加driver/SQLite或新服务。驱动重连/读写socket及serverSelection总上界复用原启动/请求15秒且受本run剩余deadline约束；一次业务尝试，无应用层重试。存储凭据仅父进程内存，不传给child。

### 6.2 崩溃事实矩阵

| 崩溃/失败位置 | 此时允许的真实结论 | 后续新启动 |
|---|---|---|
| 取锁前/抢锁失败 | ALREADY_RUNNING，未取交易秘密/未启child | 当前进程不重试 |
| Mongo写前 | 无屏障成功证据，无child | 人工判断后另次明确启动，不自动loop |
| insert发出但ACK/读回不明 | 可能ARMED，不能说绝未写 | 全拒绝；不得换绑定规避 |
| ARMED后、秘密/child前 | 没有资金发送，屏障仍在 | COLD_START_REFUSE；即使ended显示零单也不自动清 |
| reservation/签名后、order未耐久/无ACK | 明确未交transport才可释放本笔；hash若已知保留 | 屏障继续拒绝，保留证据缺口 |
| order耐久/ACK后、FINAL_SEND前 | Prepared不证明未来未发；本进程明确guard拒绝才NotSubmitted | 同hash人工核，不靠缺POST日志判断 |
| 首次transport poll/响应前 | MayHaveSubmitted/Unknown，R0和hash保留 | 新run/window/日期也全拒绝 |
| snapshot应用后、事件/ended前 | 真实账务已发生，审计可能不完整 | 不补final，不重建98或重放事件下单 |
| 正常final和child退出后 | 分别报告订单/现金/审计完整性，不自动解除ARMED | 仍拒冷启动，无reset/resume命令 |

### 6.3 有界停手、故障和接管

STARTING→READY；READY→STOP_NEW_RISK或WAIT_CASH；STOP_NEW_RISK仅→HANDOFF/ENDED且不回READY；WAIT_CASH 在 claim 与已确认官方结果逐atoms精确相等时可清回 READY，其余仅→HANDOFF/ENDED；wire 上的 payout `CASH_CONFIRMED` 是该撤销事实，reader 同步解除同一 stopped，其它原因的停止不因它解除；停窗原因首因胜出，`CASH_CONFIRMED` 只撤销由 `CASH_PENDING` 造成的停（后续 payout `CASH_PENDING` 不覆盖已存在的其它停止原因）。loss_latched只升真，同risk_window永真。原control_changed通知复用，运行内下一次可能POST前即执行关闭许可，不等完整网络tick；不取消已可能发单的future来伪造未发。sync_predict仍同hash有界查询/消费晚到事实；缺hash则人工完整历史核对，不“查不到=零”。

keyring缺失/locked/Prompt在child前拒绝，不Unlock/重读秘密loop/file fallback。keyring启动取出的密钥仍沿原child内存路径；后台锁上keyring并不能撤销已加载私钥，本设计不声称这种能力。运行中原签名/账户/认证失败立刻停新增；不为“检查keyring健康”反复读取私钥。其他非暂态输入/费用/账户故障也sticky停手，旧AccountGate某次读成功不自动解本run停止。

保留原正常cleanup30秒、只读settlement尾查上界600秒；signal/EOF/控制故障不另给新600秒额度。新域finish只调用原被允许的cancel/query，取消API未获该次真实许可则不执行而交接；取消成功/removed/noop/rejected/lock都不证明零风险。原rest继续CONTROLLED_REST_UNSUPPORTED；继承open risk在startup拒绝，离线仍须沿原cancel消费者演练竞争，不重写全OMS。超时kill/reap是同一原清理预算，native返回码/信号/forced_cleanup显式保留。

新增stop typed事件固定reason/takeover_required，本地严格写入并耐久则alert_status=LOCAL_RECORDED；写失败不能虚构已记录，exit非健康/ARMED/缺ended共同作为诚实证据。当前fake接收者只能证明本地调用，不能写外部DELIVERED；未来具体告警接收渠道/可达人员/响应责任另授权确认，发送失败仍停新增。本轮不新增网络告警sender、systemd或自动restart。

人工接管沿原账户/同hash/SDK能力，需核全窗口attempt/hash/late fill、部分量及fees/net、open/removing、官方结果/claim/份额及现金/Gas/R/U/latch；hash缺失或关键日志坏则完整官方账户历史查证。新budget flag、余额健康、换run/collection均不是恢复许可。本轮无自动或手动通用reset按钮；屏障轮转/新实验是以后具体授权操作，原文档保留，同窗口loss已触发不得新增。无法解释就继续阻断。

### 6.4 指定已 Final 库存误停的下一窗口交接（2026-11-25 受限增补）

Pascal 明确要求在原固定启动入口补齐 `RECONCILIATION_REQUIRED / INVENTORY_MISMATCH` 的受限恢复，而非手工绕行；这是操作者重新调用原入口时的下一窗口交接，不是原 run 回 READY、自动重启或通用 reset。仅正常退出、完整 canonical 旧审计、无 latch、零 reservation/无 unresolved、唯一本 run 已接受且完整 Final 的正净库存 BUY 可取得新鲜查证资格；其他已发送/未知/未闭合 attempt、其它首停原因一律不借此放行。

旧 public C0 与种子必须一致；种子引用的完整旧 native reconciliation 验 hash，并以旧 started 时点验证其当时的新鲜度，初始完整 reconciliation 与其现金一致。下一 C0 先独立锚定为旧 C0 减本 run 已审计净买入成本，绝不按 fresh 余额拟合。潜在全额亏损达到旧或新配置 loss 门限仍拒绝；旧 run 的损失与 INCOMPLETE 不改写。原签名/hash/venue/market/token/当前完整 generation、费用、applied 净份额和 Final position 必须一致。

原两次 pinned reader 从第一次起都使用新锚；各次必须完整/native0、精确同账户/全部历史、空 open/position、原 Gas 门槛与现金等式通过。同一新 token 必须新增恰一条官方 RESOLVED/CLOSED/LOST/0 的 settled_zero；原完整 claimed_win/settled_zero 多重集不变，两读所有账户事实稳定。少一 atom、positive/draw/unknown、无关 claim 抵消或任一缺口均拒绝。记录旧/新 C0、成本和两次 native 证据 hash，原 audit/种子不改。

通过后仅进入现有 activation 原子发布、全 schema 精确 guard CAS、原 controller 单次交接；无重试、无额外 secret/child 路径，不改 guard/wire schema、签名、策略、额度或同窗 sticky/latch。原 HEALTHY/CASH_PENDING/UNFILLED_ORDER 兼容保留。真实账户/生产轮换与实盘启动仍需具体授权，不由本离线修复代做。

### 6.5 指定“已证明未发送的保守 edge 误停”的下一窗口交接（2026-11-25 受限增补）

Pascal 明确要求在原固定启动入口补齐“原固定入口可重新开窗”的最后一条受限分支：当旧 run 的停机原因**本身就是经济性 edge 不合格**（`EDGE_BELOW_MIN`，发生在发送许可之前），且该 run 已用完整 canonical 证据证明**本窗从未发送过任何订单**时，操作者重新调用原入口应能开新窗，而非落入 `HISTORY_REQUIRES_TAKEOVER`。这仍是操作者重新调用原入口时的下一窗口交接，不是原 run 回 READY、自动重启或通用 reset。

**资格判定必须逐项来自本窗自身的完整证据，不得只凭末态摘要：**

- 旧 run 正常退出（launcher/child 退出码、信号、强制清理全部健康）、`audit_complete=true`、无 loss latch、`cash_complete=false`、`takeover_required=true`、`run_status=STOPPED`、`stop_reason=FACT_INCOMPLETE` 且 `stop_detail` 为空、`incomplete_detail` 为空。
- `unresolved` 必须为空、`positions` 必须为空、账务 `reserved=0`、`cost=0`、无待兑付。
- 本窗**每一个** order 事件都必须以 `attempt_phase=CLOSED` 且 `submission=NOT_SUBMITTED` 收尾，其 diagnostic 必须是 `stage=FACTS` + `detail=EDGE_BELOW_MIN`；任一 order 事件出现 `MAY_HAVE_SUBMITTED`/`SUBMITTED`、`UNKNOWN`/`ACCEPTED`/`REJECTED_FINAL`、或任何 venue id，即不得走本分支。
- 本窗不得出现任何 execution 或 payout 事件；候选不得到达 `FINAL_SEND` 阶段——该阶段只存在于已请求发送的订单。

**新 C0 绑定（不得按 fresh 余额拟合）：** 旧 public config 的 C0、旧 `attempt-reserved.json` 种子预算与种子引用的完整旧 native reconciliation（验 hash，并按旧 started 时点验证其当时新鲜度、完整/账户身份一致/空 open/空 position）三者必须一致；初始完整 reconciliation 的现金须与旧 native 一致。下一 C0 **保持旧 C0 不变**（本窗未产生库存与成本），`net_loss_atoms=0`。旧历史 `claimed_win`/`settled_zero` 原样保留，且新窗的 declared history 只能沿用旧种子声明的 hash 列表——**本窗自己那份“已证明未发送”的 signed_hash 不进入 venue 历史**；若它与旧历史碰撞则直接拒绝。

**运行时两次原链新鲜完整读取：** 任何 activation/guard 轮换或 child 之前，原链恰好两次新鲜完整 native 读；两次都必须身份/历史/pagination/open_orders/明确 positions=[]/现金等式通过，且**完整历史 claim/settled_zero 多重集与旧 native 锚精确相等**：允许排列变化，禁止新增、重复、删除、字段改写或等额抵消。本窗未发送，不借此分支解释额外结算记录。两读之间任一字段缺失/null/错类型/±1atom/任一不完整或 drift 均拒绝；现金减 claims 必须精确等于独立锚定的 C0。不新增人工重算 C0 命令、额外 Activation 阶段或独立预检服务。

**G3 受控扩张说明：** `btc5m_launch.py` 因新增上述受限恢复资格、旧现金锚与原双读接线进入 1201–2400 行档位；仍只负责原 CLI 的启动前核验和交接，不承担交易执行、签名、venue 查询实现或通用恢复。增长仅来自本节证明义务；下一次增加新的恢复类别或实质性扩展前，应将纯旧审计/恢复资格按职责提取到受完整身份清单覆盖的模块，保持原 CLI/API 不变。本次由既有独立 Validate 检查职责边界、增量范围及反例，不新增架构阶段。

**旧审计不可改写：** 旧 run/events/ended/config/seed 保持原字节，不改成 COMPLETE；新窗口另写自己的受限恢复证据（`unsent-edge-recovery.json`：旧/新 C0、净损失、未发送 hash 列表、两次 native 证据 hash），沿用单实例/原授权/完整 guard CAS/失败不自动重启。

**其它恢复类别一律不退化：** 原 HEALTHY/CASH_PENDING/UNFILLED_ORDER/FILLED_INVENTORY 兼容保留；上述任一资格项不成立即回到原 `HISTORY_REQUIRES_TAKEOVER`。

## 7. 新live wire、字段投影和真实消费者

### 7.1 分版、typed白名单

wire仅 `btc5m-controlled-live.v1`；framing仍 `BTC5M_EVENT ` + 单行UTF8 JSON + LF，含前缀整行≤64KiB，每数组≤1000，新域不借unsigned72h的1MiB例外。全对象精确required键（nullable必须显式在场）、重复JSON键/NaN/Infinity/bool冒数/非法UTF8/null/enum/未知键/未知版本均在首次write前拒绝；不能递归扫掉坏键后变成合法事件。不得承载raw/detail/error/url/签名字节。序号1起连续，final后0事件。

envelope逐键为schema_version、run_id、risk_window_id、event_seq、event_kind、event_time、market_id、token、accounting、payload，恰与SPEC §4.5对应。accounting恰含cash/available/reserved/cost/realized/unrealized/nav/net_pnl/loss_latched/status/reason/mark_time/pending_claim_value/gas_status/gas_paid_atoms。原子量语法/U256/有符号规则、order-ref等完全按SPEC；market/token/id不拿hash替代，不修复截断异常order_id。

10种payload逐键、六个facts子对象、六个delta子键、positions/unresolved数组只取SPEC §4.5原字段，不新增sidecar自由schema。Rust在 live_events/types.rs 定义具体struct+enum（deny_unknown_fields，合法有限浮点先验），Python独立精确键表；不得用serde_json任意map/Option吞缺键表达strict。decision对象直接同义原DecisionDiagnostic，只有phase在live允许FINAL_SEND，paper PRE_APPLY仍原域。SPEC已有reason两个集合分别处理，不能互混；当前源码REASONS混有BROKER_BLOCKED/RUN_STOPPED不构成扩展§4.9通用reason的许可，原8例保全也不冻结这种不合合同的宽校验。

V1.1 内部模块合同（下列新增类型名为实现目标，不是现存/外部新API）：

- 父 live_events.rs 声明私有 `mod types;` 与 `#[cfg(test)] mod tests;`，文件分别为同名子目录 types.rs/tests.rs，无 mod.rs、第三子文件或新 crate。父显式 `pub use self::types::{...}` 保留原公开导入门面：LIVE_SCHEMA_VERSION、LIVE_EVENT_PREFIX、MAX_EVENT_LINE_BYTES、MAX_EVENT_ARRAY_ITEMS、reason、REASONS、is_known_reason、EventKind、LiveAccounting、LiveRunIdentity、LiveEvent、ENVELOPE_KEYS、ACCOUNTING_KEYS、FACT_KEYS、DELTA_KEYS、payload_keys、is_atoms、is_signed_atoms、is_hash、is_order_ref、is_decimal_id、check_exact_keys；新增 LivePayload 及生产者必需的 payload/fact/delta 类型亦从此门面显式导出。不用 wildcard 生产 re-export；live_control/taker 等仍从 runtime::live_events 导入，不直依赖 types 子路径。
- types.rs 拥有上述常量/键表/数据类型/纯语法helper及 LiveAccounting 的纯序列化，新增 LivePayload 十变体分别包 DecisionPayload、ReservationPayload、OrderPayload、ExecutionPayload、ReconciliationPayload、LossLatchPayload、StopPayload、RecoveryPayload、PayoutPayload、FinalPayload。ExecutionFacts 恰六字段、每个 LiveFact 恰 status/atoms/coverage_gross_atoms/reason；ExecutionDelta 恰六字段；LivePosition/UnresolvedAttempt 精确对应原数组项。类型沿原字段、单位、nullable及枚举，不创造财务模型；event_kind 从 payload 变体唯一映射，不允许独立传错 kind。序列化仍为原 envelope 的 event_kind + payload，并非新增tag/嵌套键。
- LiveEvent.payload 及父 emitter 的生产 envelope/write 接缝使用 LivePayload，不再接任意 Value；具体payload结构成员不含自由 Value/Map。decimal ID/atoms/hash/order-ref/时间/闭合enum由受检类型或同模块校验负责，market_id按SPEC十进制ID表示，不能把当前u64 JSON number误冻成新schema。required-nullable必须检查键存在后再解析可空值，不能靠Option默认补缺；重复键在原始JSON解码时拒绝，不能先转Value丢重复键再声称已验。Value/Map只可用于最终编码视图、严格原始输入验证和负例，不作生产payload中转契约。
- 原 LiveEventEmitter 留在父文件；`LiveEventEmitter::validate(&Value)`保留为同一严格校验门面，委托 types 中仅 `pub(super)` 的 validate_envelope；保留原8例实际断言用到的稳定本地错误token（见§11.1），公开reason仍按SPEC映射。types内部check_payload/check_fact/check_positions/check_unresolved/check_hash_array及标量校验默认私有；仅父确需调用的入口收窄至pub(super)，不得为迁测试将生产私有状态升pub(crate)/pub或增测试getter。
- 父保留 quantity_class/closure_kind/submission_kind/phase_kind 以及原事实/应用结果投影责任。snapshot→ExecutionFacts、同次AppliedExecution→ExecutionDelta和core→DecisionPayload在父完成；原facts_json/delta_json/decision_json如保留兼容入口，只序列化同一typed投影，不留第二套推算。types不import State/LiveState/AppliedExecution/ExecutionSnapshot、不读余额或应用快照；live_accounting继续原子账务/估值，不接收wire定义以腾行。
- imports跟职责移动：types仅用serde/chrono/U256/SignedAtoms及同义core诊断数据（需要解码时用同字段受检表示，不修改core）；父保留原venue/snapshot/AppliedExecution、输出/并发依赖。tests用 `use super::*;`，并显式按需引入 serde_json::{json, Value}、chrono::Utc、alloy_primitives::U256、live_accounting::SignedAtoms；测试是父的子模块，可访问父私有emitter状态，原公开helper通过父re-export可见，不越级访问types私有实现。不得顺手执行历史被拒的import/mut清理。

| wire键/字段组 | 唯一原source / 转换 |
|---|---|
| run/window/time/seq/kind/market/token | ControlledRun/LiveOptions、同State单调seq、原ObservationClock及本事件关联；不以写盘时间充official observed_at |
| decision.payload.decision | 原core EVALUATE / candidate.recheck PRE_SUBMIT/FINAL_SEND；完整clock/两侧诊断及原输入，不从执行量反造fair |
| reservation.candidate_id/attempt_id/action/worst_cash_atoms/remaining_atoms/reason | 同State候选关联、原AttemptRecord.local_attempt_id/r0、原LiveState.reservations前后值；RELEASE不等于释放全部成本 |
| order.candidate_id/attempt_id | 原候选↔attempt不可变关联 |
| order.signed_hash/venue_order_id/attempt_phase/submission | 原AttemptHandle.identity及phase/submission；初始hash可null，已签非null；order_id首次获得后固定 |
| order.request_gross_atoms/max_cash_atoms/min_net_shares_atoms/expires_at | 实际SignedExecutionBound；Prepared未签阶段min可null，首次可能POST前必须>0且耐久 |
| order.removal_locked_until | 本轮接住ApiCreatedOrder官方可空RFC3339字段，并按signed hash保存只读metadata；缺失保留null，null本身不作已过锁证明；不猜ApiOrderData字段或固定delay |
| execution.attempt_id/signed_hash/venue_order_id/generation/observed_at/pages_complete | ExecutionSnapshot.identity/generation/observed_at/pages_complete，先与handle核对 |
| execution.quantity_class/gross_q_atoms/accounting_gross_q_atoms | Quantity Unknown→UNKNOWN/null，Known严格Zero/Partial/Full；snapshot.accounting_gross_q单独覆盖 |
| execution.closure/final_gross_q_atoms | Closure Open/Removing/Unproven/Final枚举映射，只有Final取其final_gross_q；evidence自由串不输出 |
| facts.gross_cash/collateral_fee/share_fee/net_cash/net_inventory | Accounting同名Field<U256>；Known→KNOWN/atoms，Unknown→UNKNOWN/null，coverage=snapshot.accounting_gross_q；Unknown原字符串只映固定reason |
| facts.vwap | Accounting.vwap，以USDT/share固定点1e18；确认零成交→NOT_APPLICABLE/null，coverage=0；其他缺值UNKNOWN，不拿limit填VWAP |
| execution.delta六键 | §5原同锁AppliedExecution的gross_q/gross_cash/collateral_fee/share_fee/net_cash/net_inventory实际应用差额；未应用null、确知重复0 |
| execution.tx_hash/settlement_status/settlement_checked_at | snapshot.tx_hash仅身份；存在不升级CHAIN_SETTLED。取下述同hash/同generation元数据的原chain.settled实际结果和检查时间，否则UNVERIFIED或MATCHED；无新RPC权限 |
| reconciliation.scope/checked_at/complete/collateral_atoms/gas_balance_atoms | 原startup/runtime/handoff AccountSnapshot及完整分页/身份核验，保存真实检查时点 |
| reconciliation.positions/open_hashes/foreign_risk | 与窗口token/attempt关联的最小原子facts；陌生账户事实仅foreign_risk=true，不导出完整隐私表；缺页不complete |
| loss_latch.latched/trigger_net_pnl_atoms/reason | 原同State sticky latch及首次触发真实net_pnl；latched只能true，未知损益不伪触阈值 |
| stop.stop_new_risk/reason/takeover_required/alert_status | 原运行stop状态及实际本地写/未来获准投递结果；stop_new_risk只能true |
| recovery.policy/state/reason | 已确认Mongo ARMED及后续只读HANDOFF/RECONCILIATION_REQUIRED；不带重建余额 |
| payout.status/payout_yes/position_net_atoms/claim_value_atoms | 原官方同market固定身份结果及原净库存，DRAW=0.5；未confirmed不算claim |
| payout.cash_received_atoms/tx_hash/observed_at/reason | 原SDK/同目标人工消费者的实际读回；本轮运行正claim无自动回收，cash=null；tx!=cash确认 |
| final.run_status/stop_reason/execution_complete/cash_complete/audit_complete/takeover_required/unresolved/positions | 原State/attempt实际闭合、原事件输出状态；未决数组逐单保留hash/closure/remaining，非计划满额；待兑付cash_complete=false |
| accounting全部金额/status/reason/mark_time/latch/claim/gas | §5从唯一原子State投影；任一未知相关派生null及INCOMPLETE/固定reason，已有K/P不丢；GAS未测为null |

snapshot quantity UNKNOWN可能使原advance_watermark拒绝，仍须发同身份UNKNOWN事实、保留原风险，停新增；不将它当成功apply。new snapshot部分字段Known但coverage不足不因schema合法变COMPLETE。conflict事件可披露原事实与CONFLICT，但不能先commit破坏旧水位。

原DTO真实缺口的最小补充：ApiCreatedOrder仅增加可缺/可null的 `removal_locked_until: Option<DateTime<Utc>>`，serde camelCase对应官方CreateOrderResponseData.removalLockedUntil（已读本地官方OpenAPI：RFC3339 string）；不向未定义该字段的ApiOrderData猜加含义。PredictFunTrader新增 `controlled_metadata: RwLock<HashMap<signed_hash,ControlledOrderMetadata>>`，类型归service/predict_fun/controlled.rs，父构造器及account.rs原synthetic trader factory只初始化空map。metadata精确存known removal时间、对应execution generation、chain_settled:bool、settlement_checked_at:Option<time>，不含金额/秘密；仅显式guarded hash登记，普通路径不消费。create成功捕获锁时刻；查询仍保留初始锁元数据，不能从缺失字段推定解除。原fills::read_order_execution在已有chain.settled调用结果后记录该代bool/实际检查时刻，不多发RPC；错误代明确false/null，不能沿用上一代成功时间。通过新增OrderVenue只读 `controlled_order_metadata(hash)`（默认None）给Broker投影，同hash/代不匹配不称CHAIN_SETTLED。其余snapshot/OrderTicket字面构造和原SDK不增必填字段。

固定错误映射：VenueErrorCode InvalidInput→SIGNED_BOUND_UNPROVEN（候选输入变化显式INPUT_CHANGED）；ExecutionNotEnabled/BudgetUnconfirmed/ReconciliationRequired→RECONCILIATION_REQUIRED；AccountMismatch→ACCOUNT_MISMATCH；ReadUnavailable→READ_UNAVAILABLE；FactIncomplete→FACT_INCOMPLETE；SubmissionUnknown→SUBMISSION_UNKNOWN；TxUnconfirmed→FACT_INCOMPLETE；SdkIncompatible→FACT_INCOMPLETE。内部累计减小/同coverage修改/overfill→FACT_CONFLICT；未知raw错误→READ_UNAVAILABLE或准备阶段FACT_INCOMPLETE，绝不输出原串。keyring Failure边界统一KEYRING_UNAVAILABLE。

Blocked需穷举：Halted/Deadline/LossLatch→decision.diagnostic_reason=RUN_STOPPED，order/stop.reason分别RECONCILIATION_REQUIRED/DEADLINE/LOSS_LATCH；OrderCap/MarketCap/TotalCap/BelowMinimum/NothingHeld/WouldCross/ThinBook/InsufficientCash/MarketRulesUnknown/ControlledRestUnsupported→decision.diagnostic_reason=BROKER_BLOCKED并保留原冻结Broker拒绝enum（decision原字段所允位置）；DataIncomplete→缺输入/CONTEXT_MISSING等原diagnostic，SettlementConflict→MARKET_INVALID并stop FACT_CONFLICT。不往SPEC order.reason增加任意Broker枚举；细分不允许输出处只用FACT_INCOMPLETE。原decision完整对象无Broker额外键时，仅保留已定义reason，不增自定义字段。

### 7.2 原supervisor首次write及ACK

control.py只增加新版分派和薄生命周期，旧validate_event_v1/v2/_EventRelations/unsigned相邻账务逻辑不改。新 `btc5m_live_events.py::validate_live_event`、`LiveRelations`、`LiveEventStore`在原supervise消费点被显式选中，版本来自started，不自动探测升级。关系验证为纯staged变更，schema/公式/关联通过后首次write，再flush/fsync/readback，才提交关系索引/previous并发关键order ACK；I/O失败既不提交关系也不重写该行，保留可能坏尾/合法前缀，停新风险。

LiveRelations只存证据关联和上次已验证累计值，不生成可交易余额或下单。需校验candidate唯一/冻结字段、PRE_SUBMIT→RESERVE→签名Prepared order→FINAL_SEND→MayHaveSubmitted/Submitted、同attempt hash/account/market/token不可变、venue ID只由null变首次值、六facts coverage单调、实际delta与上次已应用投影一致、重复0、remaining与原账务变更一致、latch不降、官方claim不加cash、final引用完整。拒绝含不相关attempt的ACK或execution。

拒绝的FINAL_SEND允许关联到已签Prepared并用明确NotSubmitted order/RELEASE终结，无PRE_APPLY。实际MayHaveSubmitted后即使后续reader无法证明FINAL_SEND链也不能隐藏execution；writer协议破坏后停止新增、保留原合格前缀/ARMED并宣布audit不完整，不伪造修复行/成功final。晚到合法facts在deadline后仍允许写，deadline只管新许可。

序列/容量在原同State出口预分配；输出失败位sticky。stdout阻塞可能延迟准备而触发最终时效拒绝，不在发送线性化区间输出。不能另造不可靠可丢旁路运送关键hash；observer旁路仍与交易协议无关。

### 7.3 文件、reader和结束裁定

新started.json精确沿SPEC §4.bis：schema_version、strategy_contract、operations_mode、risk_window_id、account_identity、authorization_ref、recovery_policy、cash_recovery_policy、asset_units、run_id、started_at、deadline_at、candidate_identity、public_config_identity。asset_units固定字段和单位；candidate_identity精确={main_head,bot_head,binary_sha256,files}，files为编译相关公开源文件的精确路径→SHA表（含本设计allowlist已存在源码、Cargo/lock、signer/SDK只读身份及加载模块）；不能复制环境。public_config_identity精确={sha256,initial_cash,max_order_usd,max_market_usd,max_total_usd,max_loss_usd}，金额取本 run 配置冻结值（98/1/1/10/20 仅为历史示例/legacy 缺省）是分配参数不是假余额（1u 口径示例：order_usd 1.0、单笔/单市场上限 1、最小下单门槛 0.5、预算按实际可用 98 封顶；2026-11-22 Pascal 授权）。

`candidate_digest`=按UTF8 canonical JSON（键字典序、无空白、ASCII转义、无NaN）编码{candidate_identity,public_config_identity}的SHA256，只含公开字节；Mongo/activation/live-context用同digest。最终文件hash在最后编辑/构建后采集，旧HEAD不能替代dirty文件身份。固定新候选binary路径见§9，不接任意--binary。

V1.1 的 candidate_identity.files 显式纳入 src/bot/runtime/live_events.rs、src/bot/runtime/live_events/types.rs、src/bot/runtime/live_events/tests.rs 最终字节：types是新编译依赖，tests用于离线证据身份（不声称被生产binary执行）。这三项与原§10精确源码/加载身份表合并去重，不另做全仓快照；模块路径不是schema版本。types/父投影/测试任一变化均不得继续把拆分前cargo证据冒充新候选通过，按§11.1仅补受影响Rust部分，后续真实消费链仍需自身完整证据。

所有证据在新唯一run目录exclusive-create，不覆写旧文件；创建started/public-config/live-context/events后fsync及父目录，order关键ACK在events同目标读回后才发。其他关键execution/latch/stop/payout/final也flush+fsync，不是掉电可靠金融恢复承诺；失败立即sticky stop/INCOMPLETE，崩溃屏障弥补拒绝重启，不自动重建可交易账。

ended.json精确沿SPEC：schema_version、run_id、exit_facts、final_event_seq、final_accounting、incomplete_reason、execution_complete、cash_complete、audit_complete、takeover_required。exit_facts精确保留launcher_exit、child_returncode、child_signal、forced_cleanup、stop_reason；无native结果用null而非0。缺final则seq/accounting=null、AUDIT_UNAVAILABLE、audit_complete=false；child非0/强制cleanup不能因一个final而健康。cash pending可正常停止观察，cash_complete=false且takeover；不能称账户清空。

2026-11-21轻量纠错：`ended.json`在上述精确字段外增加可空`incomplete_detail`；stop/final payload各增加可空`stop_detail`（承载原生已有的失败码，非法值按`UNKNOWN`）。二者仅为停机诊断留证，不改变任何停机、放行、takeover或reason判定。

2026-11-22 R4补注：真实`OUTPUT_INVALID`停机在`ended.json`之前exclusive-create一份`stop-output.json`（`schema_version=btc5m-stop-output/1`、`run_id`、`stream`、`bytes`、`newline_terminated`、`truncated`、`text`、`occurred_at`、`child_returncode`），记录首个触发停机的片段并按形状脱敏后截断到2048字符，每run至多一份。该文件（以及`ended.json`的写通）只由“停机原因本身是OUTPUT_INVALID”这一不可变事实决定：模糊审计I/O失败或任何其他停机原因之后到达的尾部输出，既不能改名`stop_reason`，也不能产生该片段或伪造健康收尾。

2026-11-22原位修复补注：`predict_fun/request.rs::account_read_error`由现有account读请求调用，以固定POSITIONS/OPEN_ORDERS/ACCOUNT/MATCHES/HISTORY_ORDER标签、既有错误码和ApiError整数status投影VenueError上下文；不依赖错误显示字符串脱敏，不改变认证刷新及单次POST路径。`live.rs`优先读类型化VenueError，既有内部短码从原cause而非外层上下文取得；首停原样传播到final。Python原validator仅在精确键校验前为旧stop/final补stop_detail=null，原ended校验同样补incomplete_detail=null；归一化只在内存，其他缺键/未知键仍拒绝。不新增字段、事件、模块或诊断sink；既有paper/live recheck_diagnostic与candidate_input_error接线保持。R1修复：请求投影创建独立VenueError而不以context保留原cause；seed_predict/check_runtime_account返回前再次做安全投影，仅保留类型code及受限step/reason（未知为UNKNOWN），覆盖原drive的Debug WARN和收尾消费者，不修改公共runtime日志调用点。用原drive＋真实tracing＋synthetic transport核查stdout/stderr及原producer→持久化reader；同一冻结候选分别通过原paper take_candidate与live_pre_submit，配对比较PRE_SUBMIT完整诊断，保留账户及执行事实差异。

新 `btc5m_live_events.read_live_run(directory)`只读上述started/public-config/events/ended/live-context；返回精确={schema_version:'btc5m-live-read/1',run_id,status,events,ended,reasons}，status=COMPLETE/INCOMPLETE/UNAVAILABLE，reasons为SPEC固定reason去重按枚举定义顺序。缺全新证据或历史signed-null→UNAVAILABLE/FACT_INCOMPLETE，不迁移旧行；坏尾/漏seq/漏final/identity不符→INCOMPLETE/OUTPUT_INVALID或AUDIT_UNAVAILABLE，不返回“已认证完整”的坏行。实际读文件重新运行同严格schema/LiveRelations、原子恒等式/coverage/费用方向/final关联，不写回、ffill或用余额反推缺失fact。

新reader是审计消费者，不建CLI/报表平台。核心验收必须是真实Rust producer→原control.supervise→第一次write→文件reader，不能靠一堆手工JSON纯函数替代；结构负例可注入同流的单字段破坏并spy首次write=0。正式报告只用既定 data/reports/2026-11-19-btc5m-live-parity-and-operations/report.md及evidence新叶，不另建任务镜像。

## 8. 官方结果、partial、取消与现金回收

复用paper::settle_from_facts/settlement_payout/same_round的纯官方身份/结果验证，不调用apply_settlement的虚拟现金。新域记录首个正fill的原官方market/yes/no/strike/时间/fee身份，仍要求BTCUSDT/300秒/固定起止价、非争议；本地spot/fair绝不结算。WON/LOST/DRAW分别给1/0/0.5官方兑付；冲突sticky停手。

原account.rs中历史/终态验证继续保留，不能仅以fills::closure_from_status的字符串分支放宽全部venue。MARKET partial FILLED需同已绑定MARKET request、原amountFilled和完整matches/pagination、原最终链/账户核对证据才能给Closure::Final{actual_q}；account::原终态检查不足以证明时UNPROVEN。accepted无数量就UNKNOWN；matched可能尚未chain settled；CHAIN_SETTLED仍不等于用户赎回。新测试先走原消费者现有终态证明接缝，不另造一套status判final。

remove回报removalLockedUntil、accepted/noop/rejected需保留已知锁时刻/unknown；remove accepted仅Removing，late fill照原hash应用；取消后查询无记录不释放。新域无自动链上cancel/invalidating nonce或新策略卖出；原cancel能力只在未来具体批准内复用。

首次官方正claim→WAIT_CASH及payout CASH_PENDING，冻结新增，不烧份额、不加B、不把cash_complete置真。0兑付按§5实现经济损失并单列残余份额；无需假redeem现金。人工另获目标/route/数量/Gas许可后沿原cli/sdk_ops/官网操作，receipt+同token余额/USDT读回才形成CASH_CONFIRMED的人工证据；失败保留同tx/hash并停止，不能自动重签。工程测试用原SDK fake reader证明这个区分，不修改或自动调用生产SDK资金入口。claim先判定后入账：账户读回只把它记为已证明的待兑付，已确认官方结果逐atoms精确相等时才入账为本run现金并写payout CASH_CONFIRMED（reader据此解除WAIT_CASH观察），差任一atom或结果未确认时claim不入账、cash_complete=false、WAIT_CASH继续。下一run仍须人工处置屏障，不以“人工以后会看”宣称资金自动连续复投。

### 8.1 已授权缺陷修复：缺失不等于矛盾

Pascal明确批准将paper提前停止缺陷并入正在开发的实盘修复。此项恢复07-004“缺失为Pending、明确矛盾为Conflict”及本SPEC §4.6的既有安全语义；不改RFC/SPEC版本、模型、预算或wire。§8原先复用二态same_round的实现方案在本修复范围内由下述三态取代，§10对paper.rs“helper仅可见性调整”的限制在本修复范围内亦由本节取代。

- 在paper.rs共用一个Match/Incomplete/Contradiction身份分类。已知market、非空token、时间、strike或非空feed矛盾优先；不能被另一字段缺失掩盖。缺失/空token或feed、缺必要时间/strike且无已知矛盾才Incomplete。保留严格BTCUSDT/300秒/有限正价格及两token不同；入场valid_round不放宽。
- paper未决且Incomplete时Pending，无回款、不释放成本、不因误报身份冲突停机；完整一致后仍走RESOLVED+CLOSED、非争议、赢家与价格交叉核验、DRAW及一次入账。已应用结果后读取缺失的身份或结算事实不撤销旧事实、不重复入账、不误报修订；已知身份、已知终价/兑付等与已应用事实明确矛盾仍Conflict并停手。完整但非终态/争议的异常反转不因本修复而自动获得通过。
- live必要身份/读取失败或异常不完整终态不产生虚假payout/现金，不清库存、预占或已有attempt_outcomes；首次停止使用已有DATA_UNAVAILABLE与接管标志，不恢复READY。完整同身份、无争议的正常非终态结果尚未发布不属于读取失败，按下节M-01分类保留Pending而不因未来终价/兑付缺省误停。已停止保留原sticky停止原因，不能为改原因解除/覆写保护；WAIT_CASH 仅在精确claim入账时按同一stop事实清除，不因别的理由改写。真实矛盾仍FACT_CONFLICT。缺数据后恢复仅补有界只读事实，不解停手、不自动赎回/复投。
- 精确修复allowlist为四个既有BOT相对路径：src/bot/runtime/paper.rs、src/bot/runtime/paper/tests.rs、src/bot/runtime/live_accounting.rs、src/bot/runtime/live_control/tests.rs；允许修改其中必要子集。前三份生产/测试职责仍为原结算与同State账务，最后一份仅原live消费者回归；不新增模块/文件。相对§10原32路径仅追加paper/tests.rs这一测试路径，累计唯一范围33；不向其他阶段扩写权限。生产paper.rs仍须≤2400，live_accounting.rs≤1200；两测试文件≤2400，增长仅本缺陷矩阵，独立Validate审查，跨阈值/跨职责另报而非删断言压线。
- 先在原消费者取得缺元数据误判的RED，再修实现；至少覆盖单项/全部缺失、缺失和真实矛盾混合、恢复只入账一次、已入账后缺读与真实修订、live停新增保风险及原WON/LOST/DRAW。真实HTTP/category失败若未实际取证仍标未证，不把fake MarketData称真实HTTP验证。受影响Rust完整验证绑定最后候选；L1旧560绿灯仅历史，原L3及独立Validate覆盖本修复，无新增设计/验收阶段。

### 8.2 独立验收 M-01 最小修复范围

2026-11-20独立Validate run3908为REVISE：原Broker周期读取完整同身份的正常OPEN轮次时，未来end_price/payout缺省被误当DATA_UNAVAILABLE。此项为既有SPEC A-013/A-021/A-022实现缺口，不改变公开wire、预算、策略、恢复或授权；保留run3908报告及原候选，修后取得新的独立证据，不无修改重跑。

- 先在原Broker消费者取得正常非终态、尚未发布结果时应保持Ready/Pending的RED；补多次周期等待→完整结果一次应用，并在同一core/adapter/client/AccountGate两轮正例之间插入实际结算检查。正常等待不回款、不造claim、不释放成本/预占；不能用所有Pending放行或仅凭open绕开已知矛盾、争议/异常终态、必需身份/读取/mark故障。
- 保留§8.1已知矛盾优先、缺必要事实停新增、已应用事实缺读不撤销/不重入账、既有stop/loss sticky、正claim WAIT_CASH及无自动赎回/复投。区分待决结果分类与已应用结果的修订检查，不以全局放宽incomplete_result破坏另一消费者。
- 本轮严格允许修改且仅修改以下八个既有BOT相对路径的必要子集：src/bot/runtime/paper.rs、src/bot/runtime/paper/tests.rs、src/bot/runtime/live_accounting.rs、src/bot/runtime/live_control/tests.rs、tools/predictfun/btc5m_control.py、tools/predictfun/tests/test_btc5m_control.py、tools/predictfun/README.md、docs/LIVE-TRADING.md。后四个只随新二进制固定路径/SHA与候选身份断言/说明更新，不重写控制器。仍在累计33范围内，无新增业务模块；paper及两Rust测试≤2400行、live_accounting≤1200，Python两文件≤2400。必要回归复用既有fixture、不得削弱/删除旧断言凑行数。
- 新Rust输入必须产生新的候选二进制，精确新路径见§9。L3原29清单、run3907-final3与run3908证据只读保留；本轮四Rust路径属于获准变更，不再要求当前SHA等于旧29清单，其他旧清单路径仍逐字保护。对应Python身份回归必须校验新候选和精确变更分区，不跳过全部上游核对。最后编辑/构建/固定pin后采完整公开身份与digest，原独立Validate卡保留R1失败历史、挂实际Fix依赖并以新候选做R2。

## 9. 当前paper、冻结研究与候选隔离

当前 btc5m-baseline72-002，2026-11-19 12:12:10至2026-11-22 12:12:10 Asia/Shanghai；launcher56913/child56964/session proc_92911e09ac5f，原binary为ROOT/data/reports/2026-11-19-btc5m-observer-runtime-fix/evidence/validate-v11/cargo-target/debug/polymarket-toolkits。原SHA `09ac37334c644c354c5565e5da3e3836815c14bb03161c44386966efaf91eca0`；control `5590892add29593d71d5233e5c14d831da06bad0bee32822e41b966bcd8250f8`；observer `29edb8df1a2b1b1cbe02ee1f0b9ec613a7babe1eb54d3db245acdafb6b71f456`；publiccfg `cf27481d9f1931d06b7ef0d8bdfeee9dead2e3fa2b0153a1917f91c8c591a8be`沿主控已核身份。本卡不接触其进程/环境/期限/配置/加载行为、不重复启动/停止。

原control.run在1627局部import observer；observer._read_trading在968局部import control。当前supervisor结束时write_coverage的当前实现不直接调用reader，但不能据此排除独立后续消费者或__main__与模块名再导入。决定采用保守且可执行隔离：

1. 原fork Rust源码/新模块可以在获批allowlist内开发；它们不会替换当前已加载binary。所有cargo显式独立target，不使用BOT默认target或validate-v11目标。
2. 当前paper存活期间，所有既有 `tools/predictfun/*.py` 及其现有tests/README保持原字节；可新增未被当前run引用的新live模块/新测试，但不修改当前control加载或偷偷改import路径。新模块不是第二runner。
3. control.py及既有Python测试/README的接线必须等待原paper进程实际退出（含已留证的安全提前退出），并由主控确认原run收尾证据及动态加载消费者不再使用这些源码；仅墙钟过2026-11-22不构成许可。实际退出不等于72h完整成功。主控可以另批隔离候选源副本，但那是范围变更，本设计不自行复制现有工具到另一运行根。
4. T3可先完成Rust/新增模块离线工作；若仍需受保护Python文件，则在剩余必需步骤上真实block，不能把半成品complete。没有自动等待/重启/修改期限脚本。最终整体Implement仍须一套候选身份，经主控再放独立Validate。

run3904构建并供run3906/run3907/run3908核验的历史candidate-v1固定根为 `ROOT/data/reports/2026-11-19-btc5m-live-parity-and-operations/evidence/candidate-v1/cargo-target`，binary为其debug/polymarket-toolkits；整个旧制品保留不覆盖。M-01修复后的唯一新候选路径固定为 `ROOT/data/reports/2026-11-19-btc5m-live-parity-and-operations/evidence/candidate-v2/polymarket-toolkits`，由原scratch/btc5m-live-parity-build复用编译缓存执行locked/offline原生build后，仅将实际成功构建的binary复制至该不存在的新目标并核源/目标SHA，不复制整套target、不改candidate-v1。若新目标已有内容，须核真实来源后报主控，不覆盖或另换叶。control.py新域仅把固定binary路径及其实际SHA更新为此候选，不接用户--binary/target参数；生产激活前还须具体最终binary SHA批准，不因固定路径自动可信。旧unsigned72h原run及其binary/证据保持原字节。2026-11-20 Pascal明确授权新的72h paper窗口：原launcher的unsigned72h固定分支可在独立接线验收后改绑已验收candidate-v2；仅新窗口使用，不重启旧run、不改原资金/策略参数。legacy 6h入口及signed新域行为不变，不把旧hash永久施于新源码。

2026-11-20工程接线释放记录：原run已于2026-11-19 21:07:10 Asia/Shanghai因SETTLEMENT_CONFLICT提前停止，L3报告与原ended/final保留；主控在总卡续接前再次定向核原PID56913/56964已不存在，未见control/observer/bot业务消费者。仅对总卡t_9be36fdf释放§10既有四路径：tools/predictfun/btc5m_control.py、tools/predictfun/tests/test_btc5m_control.py、tools/predictfun/README.md、docs/LIVE-TRADING.md，完成原new-live薄接线和离线测试。旧run记录的control SHA仍是历史加载字节，不再作为获准编辑后的当前源码不变要求；原observer、公配置、旧binary、原run全部证据和17项冻结保护保持不变。当前binary与身份复用来源为L3/run3906及其run3904原生构建回执；不因此授权重启paper、实盘运行或解除独立Validate的HOLD。

冻结身份manifest为ROOT/data/reports/2026-11-18-btc5m-joint-forward-validation/evidence/review-preparation/final-freeze.json。已仅读该manifest；保护项是其files表13项、parameters引用1项、manifest自身，以及07-006 Design §2.2列明的两个旧binary：BOT/target/debug/btc_arb_phase1_history、ROOT/data/reports/2026-11-18-btc5m-joint-forward-validation/evidence/main-implementation/btc_arb_phase1_history-v1。共17项身份全部禁止修改/重跑/读中途评分；额外两个binary沿原已核SHA引用，Implement/Validate须从原冻结交接读取预期值，不能以当下任意hash自证正确。旧研究其他制品同样保留，不因未在17项中而可覆写。特别禁止phase1_history及其bin、joint/model/metrics/reference/history_input/history_performance/unified_data改动；新共享phase1方法增加不能修改这些冻结源字节或重跑旧研究。新build不改已冻结binary。

开收工逐项验证：全部冻结及附属清单SHA、旧参数/模型配置、活动paper原四身份/进程及源加载约定、默认target/原binary无覆盖、dirty范围归属。只hash旧研究字节不读取结果/评分；测试不启动paper/99日/14日研究。若核验必需动作被拒则block，不以旧PASS或本卡文档代替。当前本卡可选组合基线诊断因runtime inline+subprocess被拒，已OMITTED并记Kanban；没有换包装重放，所以本文不声称本run重新核过冻结SHA/活动PID。

V1.1仅文档修订，不创建这两个Rust文件、不采集上述运行/冻结组合诊断、不构建；原V1.0组合诊断及L1 session20261119_154343_0fbae1 message120348/120349的import/mut清理均保留NOT_EXECUTED/OMITTED，不换包装/工具/解释器/执行者重放。新增types/tests仅限未来获批L1实现候选，仍遵守本节全部paper/冻结源/binary/Python加载隔离；本文静态自检不是新的运行身份核验，也不解除triage/hold。

## 10. 后续精确allowlist与G3

本卡仅本文可写。下表为V1.1主控及独立Design Gate之后的T3 proposal：原30路径加且仅加 live_events/types.rs、live_events/tests.rs，共32个唯一BOT相对路径，不授权目录或所有功能。单测colocated（含明确的cfg(test)子文件）；主仓tests不加模块单测。已有L1接缝按§2增量识别，表中“新增”描述相对原V1.0基线的交付职责，不声称当前全部缺文件。L1恢复时仅将新增这两路径及父live_events.rs职责写回原卡scope，不连带释放受保护Python或其他lane。

| 精确路径 | 修改/新增与函数边界；真实缺口 / 最小验证 |
|---|---|
| src/main.rs | 修改仅新live参数整组解析/公开manifest交接/原controlled分派；部分参数/错入口0凭据；旧CLI回归 |
| src/config.rs | 修改仅注册controlled_live、ControlledRun.live字段/原构造器None及新解析委托；旧预算解析不变 |
| src/config/controlled_live.rs | 新增typed公开上下文/固定模式/期限/单位/Gas检查及colocated测试 |
| src/bot/arbitrage.rs | 修改仅phase1新live提交await分派、正net反馈与新域数据失败sticky停手；原core/observer/legacy不重写 |
| src/bot/arbitrage/phase1.rs | 修改仅Phase::FinalSend及recheck复用、候选必要只读signed-bound身份accessor；无模型/参数/公式改动 |
| src/bot/runtime.rs | 先原样提取Broker::take到taker.rs；仅State/Broker新元数据、Ctx新域装配、observe/settle/drive/log_summary薄hook，普通分支不变 |
| src/bot/runtime/taker.rs | 新增：原take主体同义迁移、所有phase1裸BUY拒绝；原Predict实际snapshot结果接同一应用出口；不重写其他venue |
| src/bot/runtime/paper.rs | 提取上述四phase1方法至phase1_control；emit_phase1_evaluation/finish/emit_final极小new-live分派；纯官方结果helper仅pub(super)可见性必要调整；paper现金/原v2算法不变 |
| src/bot/runtime/phase1_control.rs | 新增：提取四方法、旧paper签名/行为不变，live读取原State.live受控元数据；不迁paper账本 |
| src/bot/runtime/live.rs | 修改仅controlled元数据字段、apply_snapshot实际应用结果接缝、sync/seed/runtime-account检查前后typed投影、必要crate可见性；advance_watermark及旧unknown保护保留 |
| src/bot/runtime/live_control.rs | 新增：同Broker候选live流程/原子发送guard/运行状态/停止与原有界收尾 |
| src/bot/runtime/live_control/channel.rs | 新增：原stdin新域ACK/D/EOF、有界等待/一次性许可；无网络/秘密 |
| src/bot/runtime/live_control/tests.rs | 新增cfg(test)：同core→原Broker→原Predict适配器synthetic/clock/channel/文件原生fixture，A-001–006/010/012–022 |
| src/bot/runtime/live_accounting.rs | 新增：唯一原LiveState原子投影/估值/claim/loss/Gas域检查，colocated边界测试；不建第二账本 |
| src/bot/runtime/live_events.rs | 原新增候选收敛：typed source投影/有界序号与原stdout出口；私有注册types/tests并显式re-export，校验委托types；不内嵌wire定义/测试 |
| src/bot/runtime/live_events/types.rs | V1.1新增：§7.1严格wire结构/枚举、常量键表、递归/标量校验、纯序列化；无State/venue消费者/应用/输出/序号所有权 |
| src/bot/runtime/live_events/tests.rs | V1.1新增cfg(test)：原8例同义迁移，保留名字/全部断言/注释及私有可见性意图；补typed/schema/真实snapshot与AppliedExecution投影反例；不替代live_control原生链 |
| src/service/venue.rs | 修改仅SignedExecutionBound/ControlledSendGuard、controlled_reservation_atoms/place_controlled_tracked默认拒绝、controlled_order_metadata默认None；不改旧ticket和TakeResult形状 |
| src/service/predict_fun.rs | 先提取request_text/authed_text/authed/authed_write原方法到request.rs，注册controlled；ApiCreatedOrder可空锁字段、trader metadata空map初始化；新域无await末端hook，普通请求行为保留 |
| src/service/predict_fun/request.rs | 新增：上述同义请求/认证方法及prepared单次发送future接缝，colocated401/EOF-before-first-poll测试；读refresh/写NoReplay不变 |
| src/service/predict_fun/controlled.rs | 新增：guarded调用、已签cash/net界限与request首次poll封装，原signer/chain/route直接复用；colocated非零fee/partial正反例 |
| src/service/predict_fun/fills.rs | 修改仅place_tracked共用内部prepare/guarded调用薄接线、check_signed_bound显式新域费方向分派、order锁及原chain.settled实际结果捕获、必要终态消费者映射；旧rest/cancel/parser算法不重写 |
| src/service/predict_fun/account.rs | 修改仅注册account/controlled子模块、原synthetic trader factory初始化metadata空map；原账户/RPC/分页/终态保护不重写 |
| src/service/predict_fun/account/controlled.rs | 新增：原AccountGate同锁prepared-self检查及测试；复用现有终态验证接缝，不清账户失败 |
| tools/predictfun/btc5m_control.py | 待§9条件满足后修改build_parser/run/supervise/check_paths/public_identity/start/ended的new-live薄分派；旧v1/v2/observer加载字节行为保持 |
| tools/predictfun/btc5m_live_guard.py | 新增：同进程lazy Mongo薄接缝、固定公共activation校验、OS锁；fake后端注入仅测试，不作新runner |
| tools/predictfun/btc5m_live_events.py | 新增：严格schema/关系、首次耐久write/ACK、本地stop及只读read_live_run；无下单/资金权限 |
| tools/predictfun/tests/test_btc5m_live_guard.py | 新增：标准库unittest/fake pymongo collection、跨run/window/模式锁与崩溃屏障，0真实存储/凭据 |
| tools/predictfun/tests/test_btc5m_live_events.py | 新增：Rust原生fixture→原supervise→磁盘reader、破坏首次write、fsync/ACK/EOF竞争、单位/秘密负例 |
| tools/predictfun/tests/test_btc5m_control.py | 待§9后仅新参数/新身份表/既有固定child测试适配，旧断言不删/skip；已有套件回归 |
| tools/predictfun/README.md | 待§9后仅07-007小节：新模式/冷启动拒绝/手动现金/授权/固定候选路径，旧命令保留 |
| docs/LIVE-TRADING.md | 修改仅07-007候选差量说明与signed-null兼容限制；不改其他venue或真实操作授权 |

明确只读：Cargo.toml/Cargo.lock、所有requirements/venv、local_signer.py/cli.py/sdk_ops.py及原SDK测试、account原读取算法、spot/observation/quoting/models、observer生产/测试、history/replay及冻结研究、全部既有public config/activation生产文件/凭据/旧证据、上游RFC/SPEC/其他Design/模板、根规则/skills/profile/其他项目。新回归复用SDK测试不等于允许修改它们；发现必须改只读路径先给具体编译/消费者证据交主控调整scope。

G3原V1.0行数来自当时read_file.total_lines实际返回（不是拒绝命令结果）：arbitrage1493、phase1 1566、runtime2370、paper2378、live1957、venue567、predict_fun2392、fills1972、account2390、config1420、main275、control1722、observer1159。本次定向实读live_events1356；run3882的其他候选行数/SHA沿主控卡面交接，不用原行数冒最终候选。父文件受控扩张/架构例外方案如下，不以删除注释压线：

- runtime先把单一take主体508–767迁runtime/taker，释放本次必要live接线空间；不动rest/quote或其他策略。predict_fun先将request_text及四个authenticated方法迁request，正好覆盖本轮“最后token await后守卫”职责，不迁client/market/签名实现。paper先迁四个模式/clock方法再加分派，保留现金主体。三者最终各≤2400；迁移前后旧入口/构造/请求次数必须等价回归。
- account只加module声明及synthetic构造器空map初始化，新方法在其子模块内扩展AccountGate，可访问父私有状态，account仍≤2400；不把2390行直接堆过2400。live、fills、phase1、arbitrage/config/control仅上述接缝受控增长，复杂逻辑和新测试放新单职责模块，不超过2400；这是本Principal明确边界与独立Validate要求。
- 新生产模块目标≤1200；测试live_control/tests可1201–2400，职责仅该新域完整原生链/故障矩阵，独立Review检查。若新模块拟越1200或现有父仍越2400，先停止增长给主控具体分拆修订，不把本表视为无限G3豁免。≥3600绝不新增；本文未授任何豁免。
- live_events.rs及live_events/types.rs各自最终物理文件≤1200行（含注释、空行、声明，不仅扣除cfg(test)后计数）；live_events/tests.rs同职责目标≤1200，不能借live_control/tests的特定档位放大。本次先移原8例和wire定义/语法校验再补严格types，父文件不得在1356行上继续叠加。保留全部原测试断言/注释，不压行、删注释、塞进live_accounting/其他无关模块或新增第三文件；拆后仍超界则给具体职责/行数证据block，不默认豁免。
- 拆分顺序同义提取→旧回归→新增guard/wire/投影→正负例；不做全仓格式化/清理。下一次跨职责新增或越本档即触发新的设计，不批量搬历史测试。

## 11. 实现、验收与证据闭合

实现顺序：§9保护前提 → 原方法同义提取及旧兼容 → 模式/typed原子投影 → guarded同消费者+FINAL_SEND → Mongo/锁fake → 严格producer/首次write/reader → §9允许后原launcher接线 → 最终身份/定向回归 → 独立Validate。既有预建图不另派同卡Review；主控核三实体与allowlist后才解除T3 hold。未闭合Blocker/Major/Minor必须REVISE，不能“带major通过”。

### 11.1 V1.1窄迁移、测试身份与责任

迁移顺序（在原L1恢复且scope写回后执行，本卡不执行）：

1. 以原live_events.rs:1174–1356的cfg(test)模块为源，去外层mod包装移至live_events/tests.rs，父改为cfg(test) mod tests；原8个函数名、注释、全部assert/assert_eq及期望本地错误token保留。只为文件拆分补必要import；不挪到live_control/tests、不删/skip/ignore/弱化断言。
2. 将§7.1指定常量/类型/键表/纯语法校验同义移至types.rs，父显式re-export和validate委托；保留原emitter/源映射/序号/输出在父。先做纯移动的受影响Rust回归，确认测试完整限定名仍为 bot::runtime::live_events::tests::<原名>，无需为物理拆文件改测试路径。
3. 在types职责内落实既有SPEC严格10种payload/六facts/六delta/数组/required-nullable/拒重复键等目标，父生产入口改typed并接同一次snapshot/AppliedExecution。旧8例如需适应typed构造，只改fixture构造/序列化和负例注入位置，全部原断言和预期不改：合法typed对象序列化后注入坏键/缺键/坏reason/false latch，仍调用生产同一validate；禁止cfg(test)替身校验或影子emitter。新缺口另加定向反例，不能把旧schema单测夸大为真实账务恒等式/消费链。
4. 同一运行共享emitter/seq/lane/pending等原T3接线在既有落点继续完成；snapshot→typed event→编码/输出和apply真实增量需覆盖未应用null、确知重复0、UNKNOWN、coverage不足/冲突、零成交仅vwap N/A、非零份额fee。types不重算这些业务事实。逐文件确认生产≤1200，再运行下述受影响测试/check并登记新候选身份；不做全仓快照或为迁移强加新测试总数门槛。

原测试身份与语义（8项均为保全清单，不是新验收数量门槛；同一前缀 bot::runtime::live_events::tests::）：

| 原函数名 | 必须保留的全部原断言所覆盖语义 |
|---|---|
| a_stop_event_round_trips_the_schema | 合法stop envelope经同一生产validate返回Ok；非手工另造通过器 |
| an_unknown_key_is_refused | extra键拒绝，原期望UNKNOWN_KEY:extra不变 |
| a_missing_key_is_refused | 缺takeover_required拒绝，原期望MISSING_KEY:takeover_required不变 |
| an_unknown_reason_is_refused | 非白名单reason拒绝，原期望REASON_INVALID不变 |
| a_latch_may_not_be_reported_as_unlatched | latched=false拒绝，原期望LATCHED_INVALID不变 |
| an_atom_amount_is_canonical | 0及规范整数字符串通过；01、负unsigned、空串、-0、1.5拒绝，-20 signed通过，原全部断言保留 |
| a_hash_is_strict | 0x+64hex通过、63位或非hex拒绝，原全部断言保留 |
| the_reason_set_is_closed | OUTPUT_INVALID通过、WHATEVER拒绝，原全部断言保留；通用/decision集合仍按SPEC分离 |

责任分层：live_events/tests负责上述保全、typed结构递归负例和父真实snapshot/AppliedExecution投影（A-008/009及A-007编码出口部分）；live_control/tests仍负责原core→Broker→Predict适配器→共享emitter的真实原生正反例与seq/lane/ACK/FINAL_SEND/父stop竞争（A-001–006/010/012–022），不能换成types自造量；tools/predictfun/tests/test_btc5m_live_events.py仍负责A-007/008/010/011的真实Rust producer→原supervise首次write/fsync/ACK→磁盘reader终链，原Python保护解除前保持未完成，不以Rust局部绿灯替代。

纯types/tests拆分仅需补跑受影响Rust：下方live_events过滤覆盖原8例及新增严格/投影回归，live_control过滤覆盖导入门面及实际生产接线，live_accounting过滤覆盖跨模块投影依赖，并以原cargo check --all-targets验证其他调用者/测试构造。原有phase1/paper/live/adapter/request/account的结果仅在候选、输入、依赖与运行条件仍适用时复用；若typed签名/实际consumer接线影响这些路径，则补其对应过滤，不一律重跑整个crate/仓库、Python或冻结研究。完整07-007交付仍须下表全部适用验收，未来Python接线后才跑受影响Python终链；不新增固定通过总数，476结果不是迁移后的验收证据。

### 11.2 原24项验收与命令映射

全部工程测试离线，现有SyntheticTransport/fake clock/keyring/SDK/collection；调用真实keyring/API/RPC/DB/外部告警即失败，传入隔离environment防默认.env回落，fake signer必须走原sign_order测试接缝而非真实签名。真正缺依赖不安装；ROOT/.venv/bin/python复用上游已核pymongo4.17.0/eth-account0.14.0/jeepney0.9.0，SDK原专用venv不变。T3须用项目解释器实际import local_signer并在patch secrets为fail的条件下验证兼容；T2未执行该import，不宣称兼容已经动态通过。

| SPEC验收 | 精确最小可证伪场景 / owner |
|---|---|
| A-001 | live_control/tests：同真实core/因果input/clock，原paper与guarded live逐字段对拍；旧cash-edge反例、Down同值及阈值邻值 |
| A-002 | 同原装配显式opt-in/默认兼容、Coinbase paper可用/live0sign+POST、observer0attach |
| A-003 | RoundTaker→Broker→PredictFunTrader健康非零fee；裸BUY/错revision/market/route/fee/q/signed ratio各0POST，live PaperCash=None |
| A-004 | 每个account/book/authorize/sign/token/ERC1271/ACK await注入clock/EOF/stop/loss；30秒、5秒、10秒边界等号及邻值；首poll前stop0POST |
| A-005 | 原adapter accepted→partial FILLED→有证明terminal partial，只应用actual净增量；late fill在deadline后仍记 |
| A-006 | 原单hash timeout/missing/later fill/settled，原POST计数1、新salt/sign计数不增；旧generation/矛盾fee停手 |
| A-007 | live_control/tests真实core/Broker/adapter→父live_events emitter（types编码，非手拼JSON）→test_btc5m_live_events.py中的原supervise→events文件→read_live_run→final；events单测不替代终链 |
| A-008 | live_events/tests保全8例并验证types六facts/六delta/单位和所有键递归负例；Python原首次write消费者复验重复键/非有限/bool/版本混流/非法ID先拒再write；合法未知可null不能补0 |
| A-009 | 原live::tests的apply同coverage/迟费补齐/重复/UNKNOWN，父live_events真实AppliedExecution→types delta在live_events/tests对拍；仅真实commit增量，share fee不再扣现金，实际fee不从模型推断 |
| A-010 | 在order write/flush/fsync/readback/ACK/FINAL_SEND/首poll/响应/apply/ended各点注入崩溃；0POST或可能发单分类精确，坏尾不补final |
| A-011 | 原native exit与final独立：child失败/kill/缺final/未决/坏关系都非健康，claim cash_complete=false |
| A-012 | 两真实隔离fake-launch进程同账户跨run/window/值守争锁至多一child，第二0交易secret；unsigned无锁 |
| A-013 | fake pymongo通过原薄接缝单次insert majority+j/primary majority精确读回；首启READY及同健康进程两不同轮非零费执行；fsync失败0POST |
| A-014 | 退出/崩溃/父死子活/换run/window/日期/OS锁释放，原ARMED仍0secret/child；无自动重启 |
| A-015 | 原子损益−20及±1atom、浮亏/费用/结算同tick第二单、回升不解latch，未知mark立即停，BNB不加USDT |
| A-016 | 绑定变更/普通budget bool/缺hash/坏日志/伪零仓不能恢复；无reset/resume/删屏障命令，旧窗口保留 |
| A-017 | keyring正常/locked/Prompt及签名失败、账户缺页/断流/旧mark；spy 0Unlock/fallback/秘密重读循环，已知K/P不消失 |
| A-018 | EOF在每await、ACK前后及首poll Pending竞态、parent异常/native结果、writer/alert失败/期限：stop不可越过许可，已可能提交不得假未发 |
| A-019 | 复用原remove/query实际consumer，locked/remove accepted/noop/rejected+late fill，只有终态核算全才释放，空列表非证明 |
| A-020 | 每单/市场/总额/真实cash及并发预占独立卡边界，等号/超1atom，R0被实绩超越则保留高风险/halt，不双算、不缩单 |
| A-021 | 原官方pure事实WON/LOST/DRAW/pending/争议→claim WAIT_CASH→原SDK fake receipt+同目标读回，0自动approve/redeem，零赔付无现金 |
| A-022 | 首单/策略pilot/无人授权分开，第一笔成功不自动无人；本地fake不DELIVERED，不称无限恢复/连续资金回收 |
| A-023 | 原signer/SDK/07-004/005受影响回归及旧v1/v2、普通live/paper消费者；复用未变独立证据，不削旧断言；真实副作用计数0 |
| A-024 | 最后编辑后候选SHA、全部冻结/附属清单、旧binary/当前paper四身份与动态加载条件、独立target、未碰配置/进程/旧证据 |

计划命令（非T2已执行；cwd除说明外均BOT；Rust使用现有locked/offline缓存，不能跑ignored联网test）：

```text
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::live_control::tests -- --nocapture
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::live_accounting
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib service::predict_fun::controlled
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib service::predict_fun::request
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib service::predict_fun::account::controlled
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::live_events
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::live_events::tests -- --list
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::arbitrage::phase1::tests
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::paper::tests
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::live::tests
cargo check --locked --offline --all-targets --target-dir <当前profile-scratch>/btc5m-live-parity-build
/home/pascal/workspace/yquant-investment/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_btc5m_live_guard.py
/home/pascal/workspace/yquant-investment/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_btc5m_live_events.py
/home/pascal/workspace/yquant-investment/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_btc5m_control.py
```

尖括号为当前worker实际scratch绝对路径占位，执行前替换，不能字面执行；pytest/cargo subprocess fixture必须显式同独立target，不能回落BOT/target或当前paper target。上述命令是T3/Validate计划，本次V1.1仍只静态检查、不执行cargo或Python业务/fixture。live_events过滤同时匹配父/其types/tests，tests --list仅核原8个完整限定名和新增案例发现，非通过证据；实际执行必须非空且记录原8例结果，不把filter0test或--list当通过，也不新造固定总数门槛。既有SDK/local_signer测试用原专用venv及原已核命令，只有解释器兼容/调用影响才补跑，不重复后端真实keyring验证。原native fixture支持通过cfg(test)专属过滤test并输出真实事件；不是生产binary业务入口。

候选binary仅在整体验证后以显式 `cargo build --locked --offline --bin polymarket-toolkits --target-dir <§9新candidate-v1/cargo-target>` 构建，禁止cargo run/真实启动。命令允许范围不等于runtime必然批准；安全拒绝停该动作和依赖，普通断言/参数错误可按原scope修复。记录实际argv/cwd/native exit/覆盖/未运行项/最终HEAD+源码+binary SHA，不拿管道末端0或开发者摘要替代独立Validate。部分成交真场馆难触发仍保留离线分支，单笔真全额不证明全部分支；offline PASS不代替以后venue生产验收。

## 12. 风险、未决与交接

业务/架构未决冲突：0；本设计不是production-ready声明。所有planned实现有§10落点及§11反例；没有以“留Developer自由决定”掩盖阻断finding。实际部署绑定/collection物化、majority+j保证、项目解释器动态兼容、最终候选、真实资金与Gas/期限/退出/接管/告警渠道都必须后续验证/具体批准，当前缺失安全默认不启动，不把它们伪装本卡实现失败或自动放行。

| 剩余风险 | 当前处理 / 以后最小Gate |
|---|---|
| Mongo凭据或绑定被换、物理耐久不达 | 固定绑定/唯一_id/ACK及读回，trusted operator边界；未来批准具体部署/集合与写，不能凭fixture宣称生产可用 |
| current paper动态加载 | §9要求原进程实际退出及主控确认，安全提前退出不冒完整成功；总卡仅按已记录四路径释放，不放开observer或原运行证据 |
| 原子账投影、reqwest首次poll和ACK错误 | 原生消费者与故障注入逐边界验证，失败REVISE，不靠event文件漂亮推定资金安全 |
| loss/Gas/late fill越阈值 | 停新增而非保证封顶，原hash持续风险；禁止清latch/重签，人工接管 |
| 单host锁及同UID信任 | 不防恶意管理员/外部客户端，真实账户须独占声明，非分布式OMS |
| 资金回收暂停 | WAIT_CASH/MANUAL_PAUSE，原SDK手工另批；无自动连续复投/跨重启恢复 |
| alpha与真实场馆未证 | 离线工程、有人首单、有人策略pilot、无人受限实测独立裁定，不以盈利或在线时长冒工程证据 |

后续主控审核三实体/版本/源码映射/G3/allowlist和零未闭合finding后，才调整预建Implement范围并解除hold；本worker不解除该hold、不自行建真实运行。Implement完成释放预建独立Validate；主控再分别申请有人首单、策略pilot、无人小额的具体账户/链/版本/金额/次数/期限/退出/取消/人工回收/Gas/接管授权。生产Mongo、权限、外部告警、服务/调度或依赖变更没有随工程自动授权。

来源：

- [07-002 Design](DESIGN-07-002-predictfun-live-foundation.md)、[07-003 Design](DESIGN-07-003-predictfun-wsl-nonexport-signer.md)、[07-004 Design](DESIGN-07-004-btc5m-controlled-paper.md)、[07-005 Design](DESIGN-07-005-btc5m-phase1-correctness.md)、[07-006 Design](DESIGN-07-006-btc5m-post-entry-observer.md)；本轮只引用，不回写历史。
- [07-002 closeout](../../../data/reports/2026-11-13-predictfun-live-foundation/closeout.md)及上游/主控Kanban独立签收；不是本卡重验业务结果。
- [官方Place orders](https://dev.predict.fun/trading/place-orders)、[Fees](https://dev.predict.fun/trading/fees)、[Order lifecycle](https://dev.predict.fun/trading/order-lifecycle)：2026-11-19公开浏览器读取，非私有API或交易验证。
- [范围评估](../../../data/reports/2026-11-19-btc5m-live-and-hybrid-assessment/report.md)仅线索，当前源码优先；[final-freeze身份清单](../../../data/reports/2026-11-18-btc5m-joint-forward-validation/evidence/review-preparation/final-freeze.json)仅读manifest、不读评分。

历史参数化版本 V1.4：t_298e36df / Pascal Light；以上参数化契约优先于历史固定示例。本轮当前版本为元数据及§R17的V1.16。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.16 | 2026-11-24 | R17 Light delta：复用BoundOrder.expiration的唯一默认只读seam，固定双时钟OrderWait、原drive/mark/账务接线，G3仅相关小段提取/相邻新测试；封闭tracing→原run-log不改wire，D17-01–06真实native消费者回归。只文档，无源码/业务测试/运行或生产动作。 |
| V1.15 范围补充 | 2026-11-23 | Pascal明确批准主控直接接手及唯一既有Python测试文件的必要迁移；§R16.6.2限定nullable diagnostic历史兼容和差1 atom硬停后未核销持仓断言，总范围27→28；保留全部旧用例/资金安全反例，RFC/SPEC业务契约、独立Validate及生产禁区不变。 |
| V1.15 | 2026-11-23 | R16 Design：对齐RFC/SPEC V1.15，保留R13/R14/R15离线基线；新增封闭order诊断与真实T0→ACK后最终permit测量映射、三minor闭合、同次账户bound证据/全量atoms核销/唯一credit提交、600s双时钟现金等待与原drive续轮/硬stop优先、精确allowlist及实测G3最小子模块/原消费者反例。同版范围修正t_ea1ed5d7：正文/allowlist/G3/矩阵允许两处tests.rs硬停预期、claim_wait typed fixture/现金先到与失配终态、opening历史收益测试按§R16.6.1迁移；27路径、tests.rs≤3596/<3600、全部旧case/安全覆盖不变，不新增业务语义/版本。旧候选和生产selector不变，仅文档，无实现/业务测试/上线或资金动作。 |
| V1.0 | 2026-11-19 | 冻结同core live薄适配、末次await/耐久ACK后原子发送许可、实际原子量投影、单账户Mongo拒绝屏障与人工现金暂停、当前paper隔离、精确allowlist/G3及24项离线验收映射；只交设计 |
| V1.1 | 2026-11-19 | 仅live_events有界拆分：新增types.rs/tests.rs两路径、allowlist由30到32；同步§4/7模块/wire归属、父re-export/import/私有可见性、§9保护/候选身份、§10物理文件G3和§11原8例保全/迁移/受影响Rust回归/真实producer终链；RFC/SPEC仍V1.0、wire仍btc5m-controlled-live.v1，经济/字段/恢复/授权不变；不实现/运行、不解triage/hold |
| V1.3 | 2026-11-22 | R2 窄修复同步：§3.1 Python 与 native 三消费者分别共用 mode-aware 6h/24h 方法；§5.2 实际敞口≥10u 的黏性停止/原 drive 返回及只刷新敞口的必要 waiter wiring，保留在飞/未知/paper 语义；严格官方与历史 token-side 绑定并阻止缓存污染后再作零兑付解释。旧记录及 98/1/1/10/20/allowance100 不变，不新增文档阶段/运行授权。 |
| V1.4 | 2026-11-22 | 公开 run JSON 参数化（Light）：C0/恒等式与 public_config_identity 改为取本 run 配置冻结值（legacy/历史示例 98/1/1/10/20）；事件与 ended 账务读者按该 run 的 budget/loss 校验，元数据读者保留 public==limits 与 target≤order。不改经济、wire、恢复或授权。 |
| V1.5 | 2026-11-22 | R7 Validate 文档校正（MINOR-1/2）：§5.2 C0 改为取本 run 冻结预算（legacy 98，早期 100 仅历史示例）；预算/caps 行号指针更新为 live.rs:746–754、taker.rs:419–436、live_control.rs:386–395；常量/上限指针一并校正为 live_accounting.rs:30（MIN_ORDER）、32（BUDGET_C0）、34（MAX_ORDER）、38（MAX_TOTAL）、40（MAX_LOSS），taker.rs:429–436；不改代码/额度/授权语义 |
| V1.6 | 2026-11-22 | R12 窄修订：§5.1 startup 要求预算逐 atoms 等于启动时观察到的 collateral（budget_usdt 支持≤18 位小数的十进制字符串、按 atoms 精确映射，不截断、不容差；±1 atom 即启动前 CASH_BUDGET_MISMATCH 拒绝）；不改经济、wire、恢复或授权语义 |
| V1.7 | 2026-11-23 | R13 窄修订：确认的正兑付 claim 在官方结果已确认后，按官方结果的 claim_value_atoms 与已兑付份额核对；claim 未确认前不入账为现金 |
| V1.8 | 2026-11-23 | R13b 窄修订：官方结算先到、精确 claim 后到的顺序下，本 run 内允许把该精确 claim 清回 READY；差 1 atom、结果未确认、foreign token 仍停窗 |
| V1.9 | 2026-11-23 | R13c 窄修订：claim 先判定后入账（账户读回只记为已证明待兑付，已确认官方结果逐 atoms 精确相等才入账为现金）；canonical reader 与 Rust 侧对同一合法流给出一致结论（已兑付持仓不进终态 positions、reader 观察 CASH_CONFIRMED 后不再视为停窗） |
| V1.10 | 2026-11-23 | R13d 窄修订：reader 收到 payout `CASH_CONFIRMED` 且该等待由 `CASH_PENDING` 造成时同步解除 `stopped`（其它原因停止仍黏性，并以 producer→reader 双用例覆盖续单与反例）；逐 atoms 预算门等指针改为符号锚定（`seed_predict` 的 `cash_matches_budget_and_claims` 不等即 bail `CASH_BUDGET_MISMATCH`，行号仅辅助）；移除 `live.rs` 未使用的 `cleared_waits`；不改经济、额度或授权语义 |
| V1.11 | 2026-11-23 | R13e 微修：停窗原因首因胜出——reader 的 payout `CASH_PENDING` 仅在 `stop_reason` 为空或已是 `CASH_PENDING` 时写入停窗，`CASH_CONFIRMED` 只撤销由 `CASH_PENDING` 造成的停；补一条 wire 级反例用例（stop DATA_UNAVAILABLE → payout CASH_PENDING → CASH_CONFIRMED → 后续 RESERVE/FINAL_SEND 仍被拦）；不改经济、额度或授权语义 |
| V1.12 | 2026-11-23 | R14 窄修订：`drive` 与 `wait_controlled_stop` 以 `must_end()`（仅停或输出损坏）结束，降级不再结束窗口；`ControlledLiveState` 新增按类别的连续失败计数与 `READ_FAILURE_BUDGET`(120s)，降级期间 `may_add_risk` 为假但继续观察、成功即清零；`resolve_blocked_candidate` 的 `NothingToRead` 归为 Ok、仅 `Expired` 停；`refresh_live_risk` 将 `UnknownMark` 估值缺口降级、事实缺口与 `Conflict` 保持停机；live 子进程 stderr 与非事件行写入本次 run 有界脱敏日志；不改经济、额度、授权、stop reason 词汇或逐 atoms 门 |
| V1.13 | 2026-11-23 | R14b 窄修订（文档对齐 + 守护断言）：R14 行为补注把「行情读」从 `READ_FAILURE_BUDGET` 降级列举中移除，并注明行情/报价读保持既有 drive `failed_ticks` 路径（`MAX_FAILED_TICKS` 达上限只撤挂单、不退出窗口，不使用 `READ_FAILURE_BUDGET`）；C 项用例断言 degraded 窗口的 drive 不提前返回、复位故障后一次 `check_runtime_account` 即恢复（`degraded=false`、`may_add_risk=true`、`stop=None`、`account_read.is_some()`）；补 Read/Execution 两类 `clear_failure` 用例并保持 per-kind 纹互不清；不改经济、额度、授权、stop reason 词汇或生产行为 |
| V1.14 | 2026-11-23 | R15 窄修订（延迟，不改门禁）：`submit_live_candidate` 不再自读账户（原第二次全量读删除），`place_controlled_tracked` 经 `ControlledSendGuard::account_snapshot()` 使用 tick 在输入前取回并已对账的那次读，`check_locked` 仍逐次复验 receipt 完备/身份/generation/attempt 绑定/10s 新鲜度；`read_account_snapshot` 以 `tokio::join!` 并发五腿并在其后按原序校验、持仓链证明用 `join_all` 并发；关闭历史订单按 hash 记忆化净贡献（新历史仍由 `/orders/matches` 每轮发现）；发送路径 join(book, chain_read) 与 join(balances, authorize)，token/签名/ACK/POST 串行。测试：新增记忆化+新未解释历史用例；探针（`send_timing_benchmark`, RTT=170ms, 9 runs）实测 book→final check 3.262s→0.860s、发送窗口 net_calls 46→24、end_to_end 4.636s→2.234s；候选 `candidate-r15-final` sha256 `bcb5a8c0…`（本卡重试轮对并发后的错误优先级做了两处原位补正：`balances?` 回到 `check_preparation` 之前、每持仓 `market_for_token` 留各自 future 内，仍按持仓原序判定） |

2026-11-22 原位修复补注：`apply_snapshot_detailed` 对"已有ACCEPTED且带venue_order_id、closure非FINAL"的在飞订单不再停机（保持attempt pending、会计仍为INCOMPLETE，观察循环继续），无ACK/身份或账本不匹配/签名hash不符/风控触发仍硬停，订单FINAL或超期仍无法证明时仍停并携带既有码；该路径的停机统一走stop_with_detail，只承载已有码，不新增分类、事件或自由文本。

2026-11-22 R2b事实补注：`signed_hash`只用于事件投影口径（`live_events.rs`按hash把事件归属本窗口订单）；账户delta的`open_orders`规则只认`venue_order_id`（`live.rs::only_in_flight_order`：恰好一个已ACK、持有venue_order_id且未闭合的attempt），hash命中不解锁任何挂单；两者不一致时按fail-closed拒绝，不放行。

2026-11-22 数值口径统一（V1.2）：§4.4/§5.2 的当前生效契约统一为 C0=98*S、0.5*S≤w≤1*S、K_m+P_m+w≤1*S、K+P+w≤10*S、B=98*S+R−K、net_pnl=NAV−98*S，启动可用 USDT≥98，配置身份为 98/1/1/10/20 且最小下单门槛 0.5（`live_accounting.rs:30–40`、`live.rs:746–754`、`taker.rs:419–436`、`live_control.rs:386–395`、`btc5m_control.py:307–308,319,1709`）；§4.4 中“单笔恰2 USDT”的历史算术向量按原值保留并加取代说明，不再代表可发送尺寸。仅文档数值对齐，不改代码/经济公式/授权语义。

2026-11-23 R14 行为补注：候选在本窗口没有任何未决订单事实时被拒（例如 ROUND_TOO_LATE 在提交前拒绝），不构成致命事实缺失，只记录 blocked 事件并继续该窗口，只有确有一个在飞订单、其事实到既有 `UNREAD_FACTS_BUDGET` 仍不可见才以 `FACT_INCOMPLETE` 停窗。live 读路径（账户读、执行读）的瞬时失败改用 paper 的连续失败计数加预算语义：期间禁止新增风险但继续观察，成功即自动清零并恢复，只有连续失败超过具名 `READ_FAILURE_BUDGET`（120s，沿用 `UNREAD_FACTS_BUDGET` 的既有常量风格）才以既有 `READ_UNAVAILABLE` / `DATA_UNAVAILABLE` 停机；行情/报价读保持既有 drive 的 `failed_ticks` 路径（`MAX_FAILED_TICKS` 达上限只撤挂单、不退出窗口，不使用 `READ_FAILURE_BUDGET`），run 内行情侧唯一既有的 `ReadUnavailable` 是 guard 的空候选簿拒绝，未改动。`refresh_live_risk` 中缺新鲜 mark 的 `UnknownMark` 属可恢复的估值缺口、按上述降级处理，而现金/gas 等事实缺口与 `Conflict` 保持原有停机语义（`DATA_UNAVAILABLE` / `FACT_CONFLICT`），不因缺 mark 而降级事实缺口。
