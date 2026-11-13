# DESIGN-07-002: Predict.fun 最小实盘接入基础（Toolkits + 官方 SDK）

## 元数据

| 项 | 值 |
|---|---|
| 状态 | V1.1 窄修订草稿；RPC、公开部署/ABI 及官方直接 SDK/Privy 控制输入已闭合，待主控 Gate；不代表实现/验收通过 |
| 作者 | YQuant Principal |
| 创建日期 / 最后更新 | 2026-11-13 / 2026-11-13（Asia/Shanghai，UTC+08:00） |
| 版本 / 目标模块 | V1.1 / 07_trading |
| 来源 RFC | [RFC-07-002](../../rfc/07_trading/RFC-07-002-predictfun-live-foundation.md) V1.1 |
| 来源 SPEC | [SPEC-07-002](../../spec/07_trading/SPEC-07-002-predictfun-live-foundation.md) V1.1 |
| 来源任务 | T2 `t_be35f48a`，parent `t_58c245a7`；工作区 `/home/pascal/workspace/yquant-investment` |
| 授权来源 | [Intake](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/intake.md)；t_188a7257 中 Pascal 批准显式 RPC 的窄修订；只读公开资料及文档静态核验 |

## 1. 设计摘要

继续唯一 Toolkits Rust 订单链。Predict live 回执新增事实载体，Broker 和 copy/exit 消费同一语义；paper 和其他 venue 留原行为。发单前先在既有状态保留风险，再用共享 attempt handle 在 POST 前保存 hash；POST 只尝试一次，包括 401 后也不重放。查询按订单生成完整累计事实，单锁按字段应用差值，不使用轮询时间或 settlementId 充当唯一成交 ID。

官方 Python SDK 仅在同 BOT 的人工薄工具直接 import。plan/check 不加载 signer；approve/redeem 的 SDK 交易构造、签名、发送不移植。通过观察签名结果和 SDK 使用的 provider，发送前保留确定性 tx hash；receipt 与目标资产读回分别判断。发行包身份、返回类型与观察接缝在 T3 隔离验证，不把 HEAD 参考当已证明的发行行为。

本设计不新建 OMS、数据库、journal、服务、UI 或长期任务；无跨进程恢复承诺。已解释风险及人工新预算确认是启动条件，不是清空内存的替代。未授权的真实资金动作不作为本次设计阻断项，也不在本阶段执行。

## 2. 现状分析

### 2.1 已核基线与来源

`BOT=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。以下 BOT 相对路径只在该子仓内展开。

- Toolkits main HEAD `4aaeefafd597bade591867f6b8a94c2677a1554f`；输入及16文件基线由主控恢复核验，见 [恢复证据](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/t2-recovery-check.md)，本轮不重跑基线。
- 历史 V1.0 RFC SHA256 `8aa780371d03ce3cbba1f34febb44fe12ec0c59b92a3b3cd0bfdb7245b8a3e8e`；SPEC SHA256 `c4db506c2d7cdf8956df7816819836868096c7b75898f19aa0d29c579cb40a80`；Design SHA256 `30e5767814866f47b04073ef3f6a7bf7448d90b0beb5d6eb21e2c3ff9103eead`。这些是历史输入，不是 V1.1 的 hash；当前三文档 hash 见窄修订交接。
- [本地 OpenAPI](../../../data/reports/2026-11-10-predict-btc5m-data-gap/evidence/request-08-openapi.json)：版本3.2.0，SHA256 `017435d88afb518644970e57287d89608801db9d9946d1f7049e73d60d2eb650`，历史公开快照，非当前线上验证。
- SDK [发行方法签名恢复](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/sdk-release-prior-output.md)只证此前 v0.0.22 ref 方法/参数名。HEAD [源码参考](../../../data/reports/2026-11-13-predictfun-infra-reuse/evidence/source-snapshots.json) 标识 `55381bfed02323c5edbc6eed0f5c603ae84172ef`；Intake 的 tag commit 记录不扩充为本轮已重验映射。
- 完整既有发现及历史安全拒绝见 [design-handoff](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/design-handoff.md)历史 §3–§6。run3650拒绝未被追认为成功；run3651因 provider 中断，没有正式 Design。
- V1.1 已读 [implementation-handoff](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/implementation-handoff.md) §1/§5：run3668 的 lib224 passed/0failed/3ignored + binary2passed、all-targets exit0 是开发自测，不是独立验收；adapter→Broker/G3 仍未闭合。工具侧冻结候选不改。run3669 的 wheel 公开 constants/ABI 核验保留为历史；本次 run3670 仅读已存官方 HTML 正文、历史 JSON owner 片段与既有 Rust 签名公式，不 import/执行 SDK、不重新提取 wheel/探索 SDK，不追认旧 probe。

### 2.2 实际接缝与兼容性

下列行号/缺陷是原 T2 的实施前基线，不应作为 run3668 当前未修清单；当前已完成与残余差分以 implementation-handoff §2/§5 为准，尤其 copy 未知满额与 POST 401 已有候选修正，不要求重做。

`arbitrage.rs RoundTaker → runtime.rs Broker::take → OrderVenue::place → PredictFunTrader` 才是 BTC5m 消费链。runtime:418–435 未知回退请求量并以 limit/模型费记实绩；order_executor:194–208 是另一路未知满额。position_monitor:131–163 会未知 close、部分或错误后重试，均须修。

predict_fun:1292–1316 的 authed_text 对401重放原 method，包含 POST；1348–1529 已有轮询、hash、remove、order_state、positions；982–984 的 decimal_to_wei_exact 实际是原子整数解析。现有 client、四个 exchange 部署、签单、认证 GET 刷新、分页及 removing 保留，不写第二 client；USDT/CTF/validator 读映射和 BSC RPC 上下文此前并不存在，按 §3.3.5 明确补齐，不声称可直接复用完整部署。

共享 OrderTicket 构造者在 predict_fun、clob、runtime/order_executor/position_monitor 的 colocated fake。copy_trading 读取执行结果。TakeResult 还由 arbitrage、spread_farming、sports_execution、whale_signal、orderbook_imbalance、resolution_sniper 匹配：不新增 TakeResult 变体，不要求修改这些策略。现有 `Blocked::Halted` 承载新增拒绝，详细原因在 Broker 诊断中；不是把已确认零伪装为 blocked。

## 3. 方案设计

### 3.1 模块/文件改动

下表仅为主控通过 Gate 后 T3 的精确源码/文档 allowlist，不是 T2 写权限。M=必须改已有文件；C=仅必要兼容改已有文件；N=必须新建。Rust 测试 colocated，无根 tests/ 模块单测；未列路径不得静默添加。

| 类别 | 文件（BOT 相对） | 改动与必要性 |
|---|---|---|
| M | `src/service/venue.rs` | 新事实/attempt/账户接口与默认拒绝方法；OrderTicket/PostedOrder/RestingState 追加可选执行载体，旧字段保留但 Predict live 禁用旧 fallback |
| M | `src/service/predict_fun.rs` | 引入两个子模块；现有 place/post_limit/query/positions 接线，POST 单次、GET 刷新保留，公共 DTO fee 字段不默认零；主体移 helper |
| M | `src/bot/runtime.rs` | 真实 take/rest/sync_live/seed_from_venue 接线与状态原子应用、现有 summary 不把未知当零；colocated consumer 测试 |
| M | `src/service/order_executor.rs` | Predict 路径先预留、调用 tracked place、按事实增量更新 PositionStore；取消未知满额 |
| M | `src/service/position_monitor.rs` | Predict SELL 未知保留持仓、已确认净扣减一次，禁止自动重发/补余；colocated 多 tick 测试 |
| M | `src/service/position_store.rs` | 现有锁内保存 copy attempt/风险预留及已应用累计水位；不另建持仓主账 |
| C | `src/service/clob.rs` | ticket 新可选字段填 None，其他 venue 行为不变 |
| C | `src/bot/copy_trading.rs` | Predict bootstrap/结果诊断接新 gate；不新增结果枚举、不修改 copy 策略 |
| M | `src/main.rs` | 新增公开、进程内人工确认参数；在既有 live 入口传给 account gate；不改配置文件/模型参数 |
| N | `src/service/predict_fun/fills.rs` | 官方事实解析/查询、累计核对、差值和风险保护纯逻辑；含 colocated 单元/假传输测试 |
| N | `src/service/predict_fun/account.rs` | 同账户 gate、只读 RPC/分页/身份/重启核对、人工确认参数的进程内交接；含 fake 测试 |
| N | `src/bot/runtime/live.rs` | 仅 runtime 私有子模块：Predict live 预留/应用/同步及 consumer 测试；非第二 Broker/执行器 |
| N | `tools/predictfun/cli.py` | argparse 与错误出口，缺子命令按 plan 处理；不加载业务配置/凭据 |
| N | `tools/predictfun/sdk_ops.py` | 直接 SDK 调用、只读 contracts 适配、输入/路由验证、tx 观察、读回及脱敏 |
| N | `tools/predictfun/requirements.in` | 仅直接依赖 predict-sdk==0.0.22；测试使用标准库 unittest |
| N | `tools/predictfun/requirements.lock` | 固定SDK和必要传递依赖版本/制品哈希；不改变 Cargo/共享 venv |
| N | `tools/predictfun/README.md` | 默认安全语义、隔离安装、版本验证、仅 fake 的本轮边界与手工操作说明 |
| N | `tools/predictfun/tests/test_sdk_identity.py` | 实装制品身份/API/无副作用纯路径/返回与观察接缝测试，不真实联网 |
| N | `tools/predictfun/tests/test_sdk_ops.py` | 工具 fake SDK/provider/receipt/余额读回测试及拒绝调用计数 |
| M | `docs/LIVE-TRADING.md` | 实际/未确认语义、新预算确认、SDK与资金权限区别及无自动恢复说明 |

除上表外，仅允许 T3 为隔离依赖生成 BOT `tools/predictfun/.venv/`、`tools/predictfun/.artifacts/` 内容（安装/下载产物，不是额外自研源码），实际阶段交接写既有主题任务目录；实际验证报告放 `data/reports/2026-11-13-predictfun-live-foundation/` 的 report.md/evidence。下载目录/环境不入 Git，不修改忽略规则。本 T2 只写 Design、handoff 和获准 t2_design_static.py。

保护清单：src/bot/arbitrage.rs、src/service/spot.rs、src/config.rs、config.json、config.yaml.example、Cargo.toml、Cargo.lock、主仓 .gitmodules、所有07-001正文；不改资金/模型/价格源。sports_execution 的独立 seed_from_venue 继续经过 Broker 内 gate，故无需改该文件；其他 TakeResult 消费者只做编译/离线回归。

G3：runtime 基线1597行，职责保留组装/公共 Broker、paper、策略驱动；新增 live 状态应用放 runtime/live.rs，经私有 `mod live` 接原 State。predict_fun 基线2284行，主体新增超过2400的风险已触发本 Principal 最小拆分设计：先移与本次相关的 confirmed_fill/order_state/positions 查询与测试到 fills/account，再接 wire；签单及 client 不迁移成另一工程。迁移顺序为提取同义纯解析/测试→旧入口委托→改变 live 语义→回归。两个父文件目标不超过2400；若仍超过，先把本次新增 colocated live 测试移动到上述对应子模块，不能再加第四 helper 或扩大重构。实现后独立 Review 核实际行数/职责；达到3600不得继续。其他原模块非本次拆分对象。

### 3.2 数据流/控制流

#### 3.2.1 两级状态与唯一事实源

Broker::State 保留策略持仓/风险；PositionStore 保留 copy 持仓/风险；两种 bot 不互相复制主账。二者各自将 attempt handle 放进既有锁保护状态。PredictFunTrader 持有一个 `Arc<AccountGate>`，供自身所有 OrderVenue/LimitVenue/copy/monitor 入口共享，仅管理身份、待核对原因及在途许可，不记第二套金额账。当前只承诺同一运行进程/同一 trader 的统一阻断，不承诺多进程钱包互斥。

gate 以 `(chain_id, trading_address, account_mode, venue)` 为键；有未确认提交/核算/账户不健康则该账户 venue 所有新增拒绝，包括其他 token 的新 BUY 和新 SELL。gate.reserve以local_attempt_id幂等：consumer已登记的同handle只推进phase，trader不得再次预留并把自身识别为另一新单；另一个attempt一律受阻断。查询、对账及既有 remove 允许。已知零/已知部分终态不是自动补单许可；原 attempt 查询可继续。

#### 3.2.2 预留→单次提交→同订单查询

1. Broker::take/rest（copy 为 OrderExecutor/PositionMonitor）在既有锁内做限额和账户 gate 检查，分配进程内递增 attempt_id，并创建 `AttemptHandle=Arc<Mutex<AttemptRecord>>`，先保留 R0 与待售份额。锁释放后才可调用任何可能发送的路径。不持锁跨 await。
2. 调用新 `OrderVenue::place_tracked(planned, expiration_secs, live, handle)` / `LimitVenue::post_limit_tracked(order, live, handle)`。原 place/post_limit 保留，Predict 实现统一委托同一个 tracked 核心；其内部直接调用者亦须 gate.reserve，不能绕过统一阻断。其他 venue 默认实现委托原方法，不进入 Predict 逻辑。
3. Predict 在 `fills::submit_once` 中复用现有准备/签单。完成 hash 后先将 hash、签单边界和到期时间写 handle；PredictAccount 按 §3.3.5 用既有签名完成只读 ERC-1271 校验，失败在未 POST 时返回 NotSubmitted/具体拒绝，不标成已可能发单。通过后才标 phase=MayHaveSubmitted，之后才允许调用唯一 POST。签名材料/请求体不放诊断 handle；maker/taker 字段只留约束。先取有效认证 token；发单401只使缓存失效并返回结构化结果，不刷新后重放 POST。GET 的一次认证刷新照旧；认证创建不是订单重发。
4. 明确本地准备/认证失败且 phase 尚未到 MayHaveSubmitted：返回 NotSubmitted，说明证据，可释放预留。POST 前记录 phase 的边界保守地视为“可能发送”；超时/断连/解析错误/401/5xx/无 order ID 均返回 Unknown（保留 hash），不可普通 `?` 丢失。只有响应明确、能证明该 hash 不可成交的拒绝才 RejectedFinal；不能把任意4xx都视为此类。
5. accepted 只填 venue_id，不填成交。在原 FILL_POLL_ATTEMPTS/FILL_POLL_DELAY 上限内调用 reconcile_order；查询失败返回带最后已知事实的 ticket。达到上限不额外起后台任务，不重发。不等待未知订单无限阻塞 drive。
6. Broker 拿回结果后，在同一 State 锁内调用 apply_snapshot；任何 Err、任务取消或 await 未返回时，之前插入的 handle/R0 仍在状态中。后台不依赖局部 ticket 存活。取消前未写 hash亦保留账户阻断，后续只能完整账户核对，不自动释放。copy 同理在 PositionStore；不可将 Drop 设计成退款/释放。
7. sync_live 继续原 tick 上查询待核订单，包含无 venue_id 而有 hash 的 taker 与 resting。没有 hash 的未解释 attempt 无法查询时维持阻断。rest 无 ID 不能被过滤成“不存在”。

authed_text 增加明确重放策略（ReadOnceRefresh / NoReplay），订单/移除等写请求为 NoReplay，GET 可 ReadOnceRefresh。即使同 hash 重发声称幂等也禁止。remove 原有允许的后续查询保留；无自动链上 cancel。

#### 3.2.3 真实 consumer 输出兼容

TakeResult 不扩枚举。Predict live 的完整且新增实际成交 `delta_gross>0` 返回 Filled，shares 为该次已确认 gross 增量，price 为该批实际 C/Q；净可卖量只在 Broker 状态。部分不完整或未知返回 Blocked(Halted)，详细数量/hash/原因在状态中保留；即使已有数量也不以缺失价格构造 Filled。终态确认零返回 Filled{shares:0, price:原 limit} 仅兼容旧返回形状；此 price 明确为约束占位、不是 VWAP，不进实绩，订单事实 VWAP=None。RoundTaker 现有 `shares>0` 才 confirm_fill 的行为不改；gate 阻断不靠改 entered 标志实现。

对后来 sync_live 补齐的成交，只更新同一主账，不再次触发策略新订单。为防 RoundTaker 在未知后未置 entered 而下一 tick 自动新签，Broker 另在原 State 保存该次意图的进程内 tombstone：Predict taker 的键为 market_id/token/side；copy 优先附 source_trade_hash，monitor 为 token/opened_at。凡可能提交后曾 Unknown、不完整、部分或终态零的意图，后续相同键只查询原 attempt，不再 place，即使后来账户恢复健康。Broker 该键保留到本市场结束、copy/monitor保留到本运行人工核对结束，不用固定冷却秒数。完全未提交的本地失败不创建“已提交”tombstone；初始完整全额仍由原策略 entered/持仓规则控制。不修改 protected arbitrage 文件，不把恢复记账当自动补齐 FAK 余量。

OrderExecutor Predict live 不走旧 filled_shares fallback。只按完整净份额与成本增量更新已有 PositionStore，未知保留风险、不建立可 TP/SL 的虚假头寸。PositionMonitor 对任何已尝试 Predict exit 保存 attempt；未知不 close，部分只 reduce 已确认库存扣减且不在下一 tick 重试剩余；明确未提交/终态零亦不自动重复该次退出意图。继续只查询原 attempt；再次退出需新运行人工核对/明确操作，不新增自动重试开关。其他 venue 和 dry-run 保持原行为。

### 3.3 接口与数据结构

以下为 T3 拟新增接口，不声称已存在；函数内部组织可简化，语义/调用顺序不可变。共享类型在 venue.rs，Predict 算法在 fills/account；runtime 私有状态操作在 runtime/live.rs。

#### 3.3.1 类型与错误承载

| 拟类型/接口 | 精确契约 |
|---|---|
| AccountIdentity | chain_id、trading_address、mode(Eoa/PredictAccount)、signer_address、venue；EOA 持仓地址等于 signer；PredictAccount 另验证控制关系 |
| OrderIdentity | local_attempt_id 必需、signed_hash 可选（签成后必有）、venue_order_id 可选；固定 market_id/token/side/account；不可用 ID 替换 hash |
| AttemptRecord | identity、request gross 上限、签名数量/价格/到期约束、R0、reserved_sell、phase、最后事实/失败步骤/原因；不含密钥、JWT、签名和原始账户载荷 |
| Submission | NotSubmitted / RejectedFinal / Accepted / Unknown；和 Quantity/Accounting/Closure 独立 |
| Quantity | Unknown 或 Known{gross_q_atoms, class:Zero/Partial/Full}；Zero 不含终态语义 |
| Accounting | 每字段 Known(value)/Unknown(reason)：gross_cash、collateral_fee、share_fee、net_cash、net_inventory、vwap；只有全部必要字段已知才 Complete |
| Closure | Open / Removing / Unproven / Final{证据来源、链块或权威状态、最终累计量}；HTTP remove 成功不造 Final |
| ExecutionSnapshot | 上述身份/三维事实、generation、完整分页标记、order amountFilled 前后水位、来源端点、UTC观测时间和交易关联；无“成功默认0” |
| OrderTicket/PostedOrder/RestingState | 追加 `execution: Option<ExecutionSnapshot>`；ticket 追加可选 signed_hash/local_attempt_id；Predict live 必须 Some，即使未知；其他 venue 为 None |
| OrderVenue::place_tracked | 参数同 place 加 AttemptHandle，返回 Result<OrderTicket>；Predict 所有可能提交后的异常转结构化 Unknown，外层 Err 仍由 handle 兜底 |
| OrderVenue::execution_snapshot | `(signed_hash: &str) -> Result<ExecutionSnapshot>`，默认 READ_UNAVAILABLE；Predict 委托 fills::reconcile_order |
| OrderVenue::account_snapshot | `() -> Result<AccountSnapshot>`，默认 READ_UNAVAILABLE；Predict 委托 account::read_snapshot；不强迫 Polymarket 实现 |
| LimitVenue tracked/query | post_limit_tracked 同上；order_state 继续原接口并携带 execution，runtime 不用旧 filled_shares 做 live 实绩 |
| fills::apply_cumulative | 输入已应用累计、候选 snapshot，输出分字段 delta/新水位或明确冲突；不自行 mutate Broker |
| runtime/live::apply_snapshot | 在 State 锁内按 attempt_id 校验身份、generation、水位，应用 delta/风险并一次提交新水位；copy 的 PositionStore::apply_execution 在其锁内采用相同纯算法 |

新增字段使用 Option 只为兼容其他 venue；Predict live 缺 execution 是 FACT_INCOMPLETE，不落旧语义。禁止 derive/default 将 fee、金额、状态或账户读失败填0。保留旧模型 f64 仅作有限数展示/策略边界转换，原子核算用现有 alloy U256，乘法用 checked U512 中间量，溢出明确拒绝，不加 Cargo 依赖。

错误 code 沿 SPEC：INVALID_INPUT、EXECUTION_NOT_ENABLED、ACCOUNT_MISMATCH、READ_UNAVAILABLE、FACT_INCOMPLETE、SUBMISSION_UNKNOWN、RECONCILIATION_REQUIRED、TX_UNCONFIRMED、SDK_INCOMPATIBLE。错误结构固定 code/step/reason/identity/known_fields；reason 采用稳定 token（如 PAGINATION_LOOP、PAGE_CAP、MISSING_FEE、CUMULATIVE_DECREASE、POST_NOT_REPLAYED、BUDGET_UNCONFIRMED），不输出原始异常 request/header/secret。多错误 code 优先级：ACCOUNT_MISMATCH→RECONCILIATION_REQUIRED→SUBMISSION_UNKNOWN→READ_UNAVAILABLE→FACT_INCOMPLETE；预算确认不能覆盖这些否决。

#### 3.3.2 原始事实/单位映射

证据定位为本地 OpenAPI 的 JSON pointer，而非杜撰代码行号。`S=/components/schemas`，`P=/paths`。

| 逻辑事实 | 官方来源与转换 | 不足时处理 |
|---|---|---|
| hash / venue ID /状态 | P:/orders/{hash}/get；S:OrderData.order.hash、id、status；核对 ContractOrder maker/signer/tokenId/side 与本地约束 | 不匹配 ACCOUNT_MISMATCH；状态只接受 OPEN/FILLED/EXPIRED/CANCELLED/INVALIDATED，未知非终态 |
| 累计 gross Q | OrderData.amountFilled 原子份额整数；与请求 signed quantity 同口径；现有 parser predict_fun:982–984/1358–1359 为原子解析 | 缺失/负数/小数/超过签名量冲突，保留旧事实不截断 |
| 自身成交 leg | P:/orders/matches/get，orderHashes=原hash，signerAddress=交易账户；S:MatchData.taker/makers 的 OrderFillData | 列表返回可能含其他腿：逐腿再筛 hash、signer、market、outcome.onChainId、quoteType(Bid/Ask)，不将 taker 总量分摊给 maker |
| gross 数量与价格 | 自身 leg.amount / leg.price 原子整数，现有 adapter:960–961,995–996 的 18位映射是当前实现假设；Q_i=q_i/10^18，p_i=p_atoms/10^18 抵押币/份额 | OpenAPI 对 amount/price 本身只写 string，没有额外单位证明；本轮保留此明确映射，须以 Q_i 汇总=amountFilled、链上同腿结算转移/余额增量校验；不能满足则不完整，不根据值大小猜单位 |
| gross C | 同自身 leg 的精确乘积 sum(q_atoms*p_atoms)/10^36 抵押币；保留原子除法余数为精确有理数，直至链上现金转移验证 | 签名 makerAmount/takerAmount 是约束，不能作实际 C；乘积若不能在抵押币原子精度精确表示且缺转移事实，则 C 未核完，不能自行 floor 后标实际 |
| 费用 | S:OrderFillData.fee→Fee.amount（明确 wei）/type COLLATERAL或SHARES；来自自身腿；18位 USDT/份额与当前部署精度须只读核验 | 缺 fee 不是0；未知币种不1:1折算。官方明确 fee.amount=0 才0；其他腿费用不用 |
| 净量/净现金 | 下述 gross/fee 公式；链上 receipt 使用匹配部署官方 ABI 解码的本账户本资产转移读回，或同订单可隔离的余额差 | 非净额原字段才扣费；本轮 API 无净字段，不杜撰 net 字段。不能隔离其他交易差额则不完整 |
| 交易和时间 | MatchData.transactionHash、可选 settlementId、executedAt；executedAt 必须可解析且保留 UTC | settlementId 非已证唯一fill ID；不得用 executedAt/轮询时间代替唯一ID |
| 持仓 | S:PositionData.amount bigint；market/outcome 指定资产；ERC1155 balanceOf 读回原子量 | averageBuyPriceUsd 未注明单位，不当真实成本；未知成本启动风险用份额最大兑付风险，不造均价 |

18位映射沿用既有 Predict 订单约定；USDT/CTF 读部署补充见 §3.3.5，USDT decimals 必须实际只读验证为18，不把 chain/币种写成跨 venue 通则。官方费用说明见 [request-09-fees](../../../data/reports/2026-11-10-predict-btc5m-data-gap/evidence/request-09-fees.html)：taker BUY 从收到的份额扣费，SELL 从收到的 USDT 扣费，maker 无交易费但仍读自身 fee。Fee.type 跟实际 leg 一起决定方向，不把签 feeRateBps 当实际费率。

计算规则：BUY `cash_out=C+F_collateral`、`inventory_in=Q-F_shares`；SELL `cash_in=C-F_collateral`、`inventory_out=Q+F_shares`（若官方该路由不允许SELL份额费而出现它，标冲突而非猜扣法）。必须核对非负及现金/份额读回；净字段若未来出现须新增显式 schema 适配，不能重复扣费。实际 VWAP=C/Q，Q=0 为 None。A-004 的双费合成向量是通用核算 fixture，不宣称当前线上同一 BUY 真有两种费。

BUY 成本记 cash_out，库存记净量；gross VWAP单列，不把含费用成本均价当VWAP。SELL 只按已确认 inventory_out 减持仓，按原成本比例释放成本，realized += cash_in-已释放成本。collateral fee 已入净现金，不再次从 equity 扣；份额费不冒充 USDT fee，不再计一次现金费。Summary.fees 仅展示已知抵押币费；live equity 由已包含费用的 realized/成本推导，paper保留原公式；accounting不完整时 summary 附 incomplete 诊断且不输出“完整实绩”健康标记。

#### 3.3.3 无可靠 fill ID 的累计/并发算法

不采用 `transactionHash:orderHash` 单独去重：一笔 transaction 可有多个自身腿。此 API 未证唯一 fill ID，本轮选择 SPEC 允许的“完整、同口径官方累计快照”，不是另建事件仓库。

`fills::reconcile_order(hash)`：

1. 分配该 hash 单调 generation（在请求发起时，不是回包时）。先 GET /orders/{hash} 得 Q_before；对这个 hash 从第一页完整读取 matches，不使用时间窗口截断订单历史。每页100、最多沿用 POSITION_MAX_PAGES=20的有界完整扫描，orderHashes本次只一笔（不超过官方25）；不用feed的5页截断结果冒充完整。
2. 使用局部记录规范化指纹（txHash、settlementId可空、executedAt、market、完整 taker、按稳定顺序排列 makers，字段含 fee 的原值）识别页间重复/循环。指纹只作重叠/矛盾诊断，不声称官方唯一成交ID。同扫描重复且无法证明是页重叠的记录标 FACT_INCOMPLETE，不把两笔可能相同的合法成交静默合并，也不重复累计；fixture 的重复“快照/回调”在第5步去重。
3. 只汇总自身腿。再 GET /orders/{hash} 得 Q_after。要求 Q_before=Q_after=sum(own q_i)，分页到 cursor 缺失/空的自然末尾，无循环/触顶。否则可独立保留更高且合法的订单数量事实，但金额/费用完整性不成立，下一既有tick再查询；不在本轮内部无限重扫。
4. 完整核算还要求所有自身 fee、价格/单位合法以及相关结算交易 receipt 成功、转移匹配；未链上结算的 off-chain matches 保留待结算，不伪造已到账。所需读取不可用保留具体已知字段，不把整个对象抹成None。
5. State 锁内比较 generation。小于最后已接纳 generation 的回包丢弃（留诊断），相同 generation重复返回零增量。新 generation 各已知累计字段与旧水位逐项比较：等值不变；数量/金额/费用增加按差值；原 Unknown→Known 补该字段且不再次加已知数量；缺失字段不覆盖旧 Known。每个金额/费用/净量字段同时保存 covered_gross_q 与事实来源覆盖范围；Q增加而金额/fee缺失时，旧Known只代表旧覆盖量，不能组成覆盖新Q的Complete。仅所有必要字段均覆盖同一当前累计Q且分页/结算完整时才Complete。累计减少、同一数量且已确认金额/费用被改写为不同值、身份改变均 RECONCILIATION_REQUIRED，保持旧账不自动冲销。合法后来补充费用仅限此前未知字段或数量新增对应费用。
6. 纯 apply_cumulative 先验证所有约束再生成 delta；runtime/PositionStore 在一个锁事务内同时更新已应用水位、持仓/现金/费用及预留，不能先克隆旧 filled、释放锁、按旧差值回写。并发同 snapshot 仅一次有增量。

这允许未知价格/费用时先记“确认 gross 风险事实”，不先生成可卖份额/成本。补齐再建立净持仓一次。查询累计完整性失败不绕过必须实现的真实字段读取：T3 fake 必须返回完整官方形状并进入该 reader；T4 不能仅拿预造 helper 数字替代 adapter→Broker 链。

#### 3.3.4 预算转换、终态及 remove

对每个 BUY，原风控最坏口径预留 R0：签单现金上限加签名允许的额外现金费用上界；保持原单笔/单轮/总敞口/亏损限额数值不变。份额费用不另外当现金预留。初期 signed 上界尚未确定时用请求最坏风险；签完发现约束超出 R0，先重新在锁内检查并补足，不足则未提交拒绝，不能先发后补。

令 B=该订单已确认的实际风险贡献（成本，或已确认更高数量风险下界），未闭合 `protected=max(R0,B)`，剩余预留=`protected-B`；不是 R0+B。不能完整核算时 B可用于保护但不制造持仓成本；聚合 exposure 用 attempt 风险贡献替代该订单已记持仓贡献，避免再算一次。订单闭合且核算完整后 protected=B，仅释放未成交余量；若B>R0保留真实高风险并阻断。SELL 的已持仓成本不因提交降低，预留待售份额在同一库存中锁定（不再加一次同持仓成本）；只有已确认 inventory_out 才减库存/成本，未知余量继续锁。

实际闭合谓词 `closure_proven && accounting_complete && matched_Q==authoritative_final_Q`。closure_proven 要么 FILLED 且达到 signed gross 上限，要么官方终态并有可核对不可再成交依据：已上链失效/撤销状态的只读证明，或链块时间超过原签名 expiration。CANCELLED/INVALIDATED字符串和 remove HTTP成功本身不等于链上不可执行证明；EXPIRED也核对链时钟。链读不具备该证明时继续 Unproven，不能靠两次相同读数/等待固定秒数捏造 finality。

remove→removing期间 late fill 仍走同累计函数；最终终态部分可按实际 B结清并释放余量。终态零需要 Q=0、完整空matches、同订单权威查询及不可继续成交证据；单独 accepted/open零/404/空matches均不算。

#### 3.3.5 账户核对、分页与人工新预算确认

`account::read_snapshot` 只通过现有 Predict client 的 reqwest::Client 与显式 RPC 上下文调用 JSON-RPC，不加第二 API client/采集器。RPC 方法限 eth_chainId、eth_getBalance、eth_call、eth_getTransactionReceipt、eth_getBlockByNumber；账户模式无法证明时停止，不能猜默认。用现有 alloy-sol-types::sol!/SolCall/SolEvent 与 alloy-primitives::Address/B256/U256/keccak256 编解码下面的公开 ABI 子集；Cargo 不变，不引入 alloy-provider，不复制 SDK 算法。Rust 不实现 approve/redeem/merge/cancel、eth_send*、eth_sign* 或 eth_estimateGas。

##### 显式 RPC 的解析/传播（V1.1；尚待实现）

main.rs:17–45 追加 `predict_rpc_url: Option<String>`/`--predict-rpc-url`，不得 clap 默认 value_parser 回显非法 URL；Cli 的 Debug 去掉原始 URL 或实现脱敏版本，不 log 整个 Cli。main:123–137 在 AppConfig::load 前调用 account 的纯 parser：绝对 http/https、有 host、非空、无空白、无 fragment；错误只有 INVALID_INPUT/PREDICT_RPC_URL_INVALID。不选公开默认 endpoint，不从配置/环境/SDK RPC_URLS_BY_CHAIN_ID 补值；合法 URL 包括可能含凭据的 userinfo/path/query，只存在内存并由 RedactedRpcUrl 包装，Debug/Display 固定 `[REDACTED_RPC_URL]`，错误不带原始 cause/URL。

在 account.rs:334–431 现有 RunConfirmation/ConfirmationSlot 上扩展为一次性 run context：`confirmation: Option<RunConfirmation>, reconciled_orders, rpc_url: Option<RedactedRpcUrl>`。保留现有 install/claim 接缝，不新建并行全局槽；main 在 Run/Tui 分派前安装，CheckVenue 不领取，不改变 check 的 opt-in 认证语义。空 URL 和确认声明独立：None URL 不影响 paper，合法 URL 不能自动确认预算。声明和 hash 在凭据前分别验证（hash 严格0x+64 hex）；不匹配声明必须可诊断为 ACCOUNT_MISMATCH，不能静默吞掉。每个已解释 hash 仍须实际查询，不由 flag 放行。

PredictFunTrader::new:1256 在既有构造路径获取且只获取一次 context，绑定所选 deployment 和账户身份；实际 live 模式才保留 RPC read context，paper/非 Predict 丢弃、不创建 client/provider、不请求 RPC。由现有 runtime::Ctx::connect:1078、copy_trading:157 等调用既有 new/claim 路径，不改受保护配置。`claim_run_confirmation`:1284 须保留 reconciled_orders/读上下文而不是 Some(_) 后丢弃；同一 trader 的全部读操作复用已领取 context，第二 trader 不继承。无声明保持 BUDGET_UNCONFIRMED，无 URL 在 live reader 报 READ_UNAVAILABLE/MISSING_READ_CONTEXT，均不得读取成功后自动确认预算。

reader 首先 eth_chainId 精确匹配56/97与 deployment；错链 ACCOUNT_MISMATCH/CHAIN_MISMATCH，超时/JSON-RPC error/缺 result/非法 hex/ABI 不符 READ_UNAVAILABLE。其后用同一已核链上下文进行全部余额/授权/receipt读取。复用 PredictFunClient.http:584 的15秒超时；必要时只在现有 builder 禁止 redirect（REST/RPC均不跟随，不增加 client），不使用 authed_text 的 JWT/API-key 请求构造。日志不包含 endpoint 的任何部分，不输出 reqwest raw error/source/header/request/body；禁用会泄漏 URL 的底层 HTTP trace，非只对 password 打星。不会把 SDK 默认 URL 当 fallback。

##### 逐链逐路由部署（公开文档数据，不是链上验证）

唯一地址来源为安装包公开 `predict_sdk/constants.py:58–88`，SHA256 `a427e5c974b7fdbbf58b183af8065ad0e80ce1a2b017d15f3be686645e9fd9b2`；本轮逐字节核对与 wheel `879cfe183544d931f16c0be5e2c4f927ad127403963d146000904e2c1fc8d6b2` 中同名成员一致。全部9个公开文件的 hash/选取 ABI/地址原文见[public-data-final.json](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/public-data-final.json)，按 files[].path 定位，不 import SDK。wheel 发行身份沿[工具交接](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/t3-tools-handoff.md) §2；没有发行签名/下载URL/tag映射证明。固定 HEAD README 仅补公开 scope 说明，绝不标发行版。

N/Y 为官方 market.isNegRisk/isYieldBearing；BUY/SELL 必须与原 signed order side 和 outcome.onChainId 同时绑定，不能靠 token 名称推断。表中 CTF 是资产存储合约，不把 exchange/adapter/CTF 地址互换。

| chain | N/Y | exchange（常量键） | CTF（常量键） | NegRisk adapter |
|---|---|---|---|---|
| 56 | false/false | CTF_EXCHANGE `0x8BC070BEdAB741406F4B1Eb65A72bee27894B689` | CONDITIONAL_TOKENS `0x22DA1810B194ca018378464a58f6Ac2B10C9d244` | 不适用 |
| 56 | true/false | NEG_RISK_CTF_EXCHANGE `0x365fb81bd4A24D6303cd2F19c349dE6894D8d58A` | NEG_RISK_CONDITIONAL_TOKENS `0x22DA1810B194ca018378464a58f6Ac2B10C9d244` | `0xc3Cf7c252f65E0d8D88537dF96569AE94a7F1A6E` |
| 56 | false/true | YIELD_BEARING_CTF_EXCHANGE `0x6bEb5a40C032AFc305961162d8204CDA16DECFa5` | YIELD_BEARING_CONDITIONAL_TOKENS `0x9400F8Ad57e9e0F352345935d6D3175975eb1d9F` | 不适用 |
| 56 | true/true | YIELD_BEARING_NEG_RISK_CTF_EXCHANGE `0x8A289d458f5a134bA40015085A8F50Ffb681B41d` | YIELD_BEARING_NEG_RISK_CONDITIONAL_TOKENS `0xF64b0b318AAf83BD9071110af24D24445719A07F` | `0x41dCe1A4B8FB5e6327701750aF6231B7CD0B2A40` |
| 97 | false/false | CTF_EXCHANGE `0x2A6413639BD3d73a20ed8C95F634Ce198ABbd2d7` | CONDITIONAL_TOKENS `0x2827AAef52D71910E8FBad2FfeBC1B6C2DA37743` | 不适用 |
| 97 | true/false | NEG_RISK_CTF_EXCHANGE `0xd690b2bd441bE36431F6F6639D7Ad351e7B29680` | NEG_RISK_CONDITIONAL_TOKENS `0x2827AAef52D71910E8FBad2FfeBC1B6C2DA37743` | `0x285c1B939380B130D7EBd09467b93faD4BA623Ed` |
| 97 | false/true | YIELD_BEARING_CTF_EXCHANGE `0x8a6B4Fa700A1e310b106E7a48bAFa29111f66e89` | YIELD_BEARING_CONDITIONAL_TOKENS `0x38BF1cbD66d174bb5F3037d7068E708861D68D7f` | 不适用 |
| 97 | true/true | YIELD_BEARING_NEG_RISK_CTF_EXCHANGE `0x95D5113bc50eD201e319101bbca3e0E250662fCC` | YIELD_BEARING_NEG_RISK_CONDITIONAL_TOKENS `0x26e865CbaAe99b62fbF9D18B55c25B5E079A93D5` | `0xb74aea04bdeBE912Aa425bC9173F9668e6f11F99` |

| chain | USDT | ECDSA_VALIDATOR | KERNEL（实现地址常量，不是用户交易地址） |
|---|---|---|---|
| 56 | `0x55d398326f99059fF775485246999027B3197955` | `0x845ADb2C711129d4f3966735eD98a9F09fC4cE57` | `0xBAC849bB641841b44E965fB01A4Bf5F074f84b4D` |
| 97 | `0xB32171ecD878607FFc4F8FC0bCcE6852BB3149E0` | `0x845ADb2C711129d4f3966735eD98a9F09fC4cE57` | `0xBAC849bB641841b44E965fB01A4Bf5F074f84b4D` |

交易所作用域（不新增 split/convert/redeem 审批要求）：BUY 对本链 USDT 读 allowance(trading_address, 所选 exchange)，至少覆盖本次签名现金上限及允许的额外现金费；SELL 对本行 CTF 读 balanceOf(trading_address, onChainId) 和 isApprovedForAll(trading_address, 所选 exchange)。这与[固定官方 README](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/sdk-head-readme.md):108–116 的 TRADE 单侧含义一致。NegRisk adapter 的操作审批不冒充交易审批，也不把它所有权限设为交易必需；将来资金工具仍按冻结单 scope SDK 路由。

##### 最小只读 ABI / receipt 关联

下表文件均为 wheel 公开 abis/<名称>.json，精确输入/输出/indexed 标记与 SHA 均保存在 public-data-final.json 的对应 selected_abi。只允许选取下列 read/event 数据，不移植 SDK 实现。

| 公开 ABI | 只读方法 / 事件 | 本设计用途与不允许的推论 |
|---|---|---|
| ERC20 | balanceOf(address)→uint256；allowance(address,address)→uint256；Transfer(indexed address from,indexed address to,uint256 value) | 同链本表 USDT；按实际 owner/from/to 关联，不把无关到账或总余额增量当成交 |
| ERC20 扩展：EIP-20 §decimals | decimals()→uint8（view，可选） | 安装包 ERC20.json **没有 decimals**；按[官方 EIP-20 快照](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/eip-20.html) 明确最小 ABI。实际读失败/非18不能默认18；该规范不证明所选 token 真支持或精度值 |
| ConditionalTokens / YieldBearingConditionalTokens | balanceOf(address,uint256)→uint256；isApprovedForAll(address,address)→bool；payoutDenominator(bytes32)→uint256；payoutNumerators(bytes32,uint256)→uint256；getCollectionId(bytes32,bytes32,uint256)→bytes32；getPositionId(address,bytes32)→uint256 | 按行选择 CTF；payout/condition/indexSet 仅只读核对，不发赎回。yield 存款/兑付率不可从标准抵押币1:1猜测 |
| 上述两个 CTF ABI | TransferSingle(indexed address operator,indexed address from,indexed address to,uint256 id,uint256 value)；TransferBatch(indexed address operator,indexed address from,indexed address to,uint256[] ids,uint256[] values) | 检查 emitter=本行 CTF、目标 token、owner方向、数组等长，逐 logIndex 关联；不是接收任意 ERC1155 事件 |
| CTFExchange / NegRiskCtfExchange（同样用于对应 yield exchange 的这些公共 read/event 子集；真实调用不支持即拒绝） | getCollateral()→address；getCtf()→address；registry(uint256)→(uint256 complement,bytes32 conditionId)；getOrderStatus(bytes32)→tuple(bool isFilledOrCancelled,uint256 remaining)；isValidNonce(address,uint256)→bool | 固定 exchange/签名hash/token/nonce，不用任意地址调用。NegRisk getCtf 如返回 adapter，必须由本行 adapter.ctf() 绑定本行 CTF，不直接假定其等于底层 CTF；collateral 如为 wrapped 只能通过 adapter.col()/wcol() 显式识别，不当 USDT |
| 两个 exchange ABI | OrderFilled(indexed bytes32 orderHash,indexed address maker,indexed address taker,uint256 makerAssetId,uint256 takerAssetId,uint256 makerAmountFilled,uint256 takerAmountFilled,uint256 fee)；OrderCancelled(indexed bytes32 orderHash) | 本签名 orderHash + maker=本交易地址；BUY makerAssetId=0/takerAssetId=token，SELL反向，maker/taker金额按角色核对（不是把 taker 地址当自身）。fee事件单位需与自身 REST fee/type/转移核对，不猜现金费；不重复累计 OrdersMatched 汇总事件 |
| NegRiskAdapter | col()/wcol()/ctf()→address；getPositionId(bytes32,bool)→uint256 | wrapped collateral 没有静态默认地址；只从本行 adapter 同块读取；col 对本链 USDT、ctf 对本行 CTF、token/condition对齐；不能用wcol=USDT替代实际资产映射 |
| ECDSAValidator | ecdsaValidatorStorage(address smartAccount)→address owner；isInitialized(address smartAccount)→bool | 同链固定 validator 上查询 trading_address；初始化=true、owner非零且等于声明 Privy signer，配合下述逐单ERC-1271验证，不声称支持所有 Kernel 模块 |
| Kernel | isValidSignature(bytes32,bytes)→bytes4 | 目标是用户 trading_address，不是 KERNEL 实现常量；以原订单hash与既有86字节签名验证，返回0x1626ba7e才通过。rootValidator/isModuleInstalled虽在公开ABI中，但本限定路由不使用泛化模块枚举，不猜bytes21/模块编码 |

receipt 最小身份是 `(chain_id, transactionHash, blockHash, exchange, orderHash, trading_address, token_id, side, logIndex)`；receipt.status 必须1、交易hash等于 matches.transactionHash、blockHash/number与链块读回一致、日志未移除。先匹配本 route exchange 的自身 OrderFilled，再核对同 tx 的 USDT Transfer 与本 CTF TransferSingle/Batch；一 tx 有多个自身腿/不同 order、同资产净转移不能隔离时保持 FACT_INCOMPLETE，不按时间/余额猜归属。receipt.to 不强制是 exchange（可经路由调用），实际关联以正确 emitter/订单事件为准；receipt.from 即实际该笔链交易发送方，不由它倒推未来资金操作 payer。API side/outcome/market、签名约束和事件资产方向必须一致。

闭合读回在同块固定 blockNumber 作 eth_call/eth_getBalance，先取 eth_getBlockByNumber；签名 expiration 只有正数且该块 timestamp 超过它才成立。也可读所选 exchange.getOrderStatus(hash).isFilledOrCancelled=true 或 isValidNonce(maker,signed_nonce)=false 证明不可再执行；remaining 不当 gross Q，须与 REST 累计及自身结算核对。返回(false,0)可能是未见过的默认状态，不代表成交/终态。cancel事件如已在可关联receipt中可作来源，但不新增 eth_getLogs 扫链或链上取消。

EOA：trading_address=signer，原生 BNB 的 gas 读 signer，USDT/CTF 读同地址；不替 matcher/relayer虚构本地授权或 gas 预算。PredictAccount 仅支持本轮已有的官方直接 SDK/Privy 路由：资金/授权属于 trading_address，gas 的 BNB 余额读取 Privy signer，不读取 Kernel 实现地址或以 trading_address 余额替代。官方 approvals 明确 Privy 支付经账户发送的授权交易 gas；这是所支持 SDK 链上操作路径的 payer 依据，不证明用户承担 matcher 订单结算 gas，也不证明网页代付/第三方 paymaster 可用。不新增代付模式、任意 Kernel 版本或模块管理支持。

##### 官方直接路由依据与可执行控制谓词（run3670 闭合 run3669 来源阻断）

以下均为主控已保存的官方公开页面，本次仅解析本地 HTML 为正文，不执行其 script；原 URL 可变化，SHA256 仅固定本次页面内容，不构成 wheel→ref 映射或链上部署证明。[依据裁定](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/official-basis-resolution.md)与[本次纯文本](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/r2-official-bodies.log)保留原文及限度。

| 官方 URL / 本地源 | SHA256 | 直接证据及限度 |
|---|---|---|
| https://dev.predict.fun/trading/approvals / [official-approvals.html](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/official-approvals.html) | `84b21b78886c9faf6d86a87fcc61b1b80af747a97f6283e62f58bb7ff4a1a6a1` | PredictAccount持有资金/授权，SDK通过账户发授权，Privy签名并支付gas，需要BNB；不是matcher结算gas或任意paymaster证明 |
| https://dev.predict.fun/trading/authentication / [official-authentication.html](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/official-authentication.html) | `a3db7f4d12ce5bdcce2ff28f4b796f81a02d4cac98ce38aba61684519b731cf5` | SDK链上验证Privy拥有账户，owner不符/未设置账户失败；不能仅凭REST地址或owner缓存放行 |
| https://dev.predict.fun/resources/order-signing / [official-order-signing.html](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/official-order-signing.html) | `9f0c094bfabdbffbb3c1b2d6225887413f04dc0c6cb4d02573f31425dc716c93` | Kernel0.3.1/ERC-1271、Kernel包装/EIP-191、0x01+两链相同固定validator+65字节签名=86字节；不推导通用模块枚举 |

历史固定 [source-snapshots.json](../../../data/reports/2026-11-13-predictfun-infra-reuse/evidence/source-snapshots.json) SHA256 `ab17d5cb0a1d82bf19a17a298b65a9875dfb449c2a7cba9f9997f9dd6dcb8c21`，记录 https://github.com/PredictDotFun/sdk-python/blob/55381bfed02323c5edbc6eed0f5c603ae84172ef/src/predict_sdk/order_builder.py:195–201 的 ecdsaValidatorStorage(predict_account) 与 signer_account.address 比较，支持复用该直接owner校验；它是历史HEAD，不是发行wheel映射。既有 Rust 本树实际函数名为 sign_for_account（predict_fun.rs:2231–2260），测试 predict_account_signatures_match_sdk_formula（:2484–2497）；已读公式与官方正文一致，本卡未运行签名或该测试，不把静态比较当行为验收。

控制检查分两步，均复用本节显式同链只读上下文及固定 blockNumber，不新增 signer 或签名路径：

1. 启动/每次必要账户核对：chainId等于所选56/97；REST账户及原订单 maker/signer绑定trading_address；validator固定为 `0x845ADb2C711129d4f3966735eD98a9F09fC4cE57`；isInitialized(trading_address)=true；ecdsaValidatorStorage(trading_address)=非零且等于声明Privy signer。初始化false/owner不符/账户模式或身份不符为ACCOUNT_MISMATCH（原因ACCOUNT_NOT_INITIALIZED/OWNER_MISMATCH/既有身份原因），读取缺失/解码错误为READ_UNAVAILABLE。无签名阶段不为检查另签一条挑战。
2. 每笔准备完既有订单签名、POST之前：H为原订单在本链所选exchange的EIP-712 hash；沿现有 `wrapped=keccak256(abi.encode(keccak256("Kernel(bytes32 hash)"),H))`，Kernel domain为name=Kernel/version=0.3.1/chainId/账户地址，`digest=keccak256(0x1901 ‖ domainSeparator ‖ wrapped)`，既有signer对digest的32字节做EIP-191签名。只检查现成结果为1字节0x01+20字节固定validator+65字节签名、总86字节；随后 eth_call 到 trading_address 的 isValidSignature(H,该签名)，ABI bytes4严格解码并等于 `0x1626ba7e`。格式/validator/非magic返回为ACCOUNT_MISMATCH/SIGNATURE_MISMATCH；RPC/revert/无结果/坏ABI为READ_UNAVAILABLE，不POST、不改用其他签法。只读请求可携既有签名字节，但禁止将其打印、存诊断handle或泄漏到日志。

该谓词验证当前支持签名在账户上的实际可接受性，而非仅凭owner记录推定控制；不要求 rootValidator()/isModuleInstalled() 枚举或证明任意Kernel版本。新单未POST的验证失败不能清掉旧attempt风险或既有账户否决。身份/余额/授权/receipt和预算等原门禁仍全部成立；输入来源已闭合，不再以历史两个UNPROVEN原因永久STOP支持模式。真读失败/不匹配仍关闭新增，原A-001–A-012不变，不把输入闭合冒充业务完成。

| 读取项 | 来源与必核内容 |
|---|---|
| 身份 | REST /account.address 等于 trading_address；RPC chainId 等于 deployment；PredictAccount执行上述初始化/owner及逐单ERC-1271谓词，不默认退回EOA，不增加通用模块枚举 |
| 资金/gas | USDT balanceOf(trading_address)、decimals；EOA与支持的直接SDK/Privy PredictAccount路由均读signer的BNB；失败不造0，不以代付假设跳过，也不将其宣称为matcher结算gas预算 |
| 授权 | 明确市场/side的 token/spender allowance 与ERC1155 isApprovedForAll；合约/路由用本节补足的固定表；不拿 GET /account 当余额接口 |
| 持仓 | 原 /positions 分页+链上目标 balanceOf；同链同地址。分页失败不删除旧持仓；held_wei改复用完整分页，不只取一页first100 |
| 未闭合订单 | /orders?status=OPEN 完整分页；只支持OPEN/FILLED列表过滤，不杜撰ALL。运行中所有已签hash即使不在OPEN也逐笔查询 |
| 成交与重启 | /orders/matches?signerAddress=交易账户 分页及所列hash逐笔核对；不以 activity（无稳定hash）代替。列表无法枚举所有历史状态时不能宣称完全恢复，见下述人工核对边界 |

分页统一 `account::collect_pages`，first positions=100、orders/matches=100，最多20页沿用现有position保护；自然无下一cursor才Complete，出现重复cursor/重复页面、解析/中途失败或第20页仍有下一cursor即READ_UNAVAILABLE/对应原因。first范围遵OpenAPI，不在运行时无限加页。完整空页是 KnownZero，失败是 Unknown。运行检查跟随原 sync_live 周期；每次live新发之前作一次有界必要资金/授权/持仓/订单检查并与进程账比较，不增加后台频率/定时器。沿用现有网络超时；原无超时的新增RPC须复用client已有超时构造，不能无限 await。

人工入口：保留 `--predict-budget-confirmation <chain:address:mode>` 与 `--predict-reconciled-order <hash>`（后者可重复）；V1.1 追加上文显式 `--predict-rpc-url`。main凭据前纯解析，既有进程槽一并交接，URL不得被当作非secret声明打印。缺确认仍BUDGET_UNCONFIRMED；确认仅表示“人工已核对此前风险并接受现有预算”，不是覆盖健康检查/提供新金额/自动交易。确认语义不变，RPC不是新的预算层。

重启时以官方完整持仓/OPEN/可枚举成交建立快照；新预算确认必须和逐项可核对的解释相配。每个声明hash都查询，不能由参数直接标已解释。未知来源持仓记 inherited最大兑付风险并阻断新增，不自动卖；可识别但无法恢复成本的旧风险不得作为本轮可卖持仓。旧挂单、未结算成交、未知历史订单或人工无法列出上一运行未闭合hash时不放行，报告 RECONCILIATION_REQUIRED；不声称仅凭现有列表和一条确认能恢复所有历史。已闭合旧hash与现有空/完全解释的账户，加本次明确预算确认才能开始；无跨日亏损自动累计。

运行期任何必须读取失败都将gate标阻断，保留旧状态；恢复读成功只清该读取故障，不能清未确认订单/冲突。总预算或健康无法隔离时整个账户venue停新增。原 startup inherited exposure、removing和所有限额校验保留。工具资金操作与bot不可并行同钱包；本设计无跨进程锁，真实值守须人工保证单运行入口。

#### 3.3.6 SDK 薄工具输入与默认行为

工具不读主仓config/credentials/.env，不扫描继承密钥变量。cli.py以同目录导入sdk_ops；模块import不创建signer/provider，不发RPC。业务函数参数显式依赖注入 `builder_factory/read_context/signer_loader/tx_observer`，生产默认工厂直接import predict_sdk，测试使用严格fake。无子命令按plan，但缺目标INVALID_INPUT；help只解析参数。

- 公共参数：`--chain-id`、`--owner`、`--account-mode eoa|predict-account`，PredictAccount另有`--predict-account`及显式控制关系上下文；plan的明确market/side/neg-risk/yield-bearing scope按SDK ApprovalScope类型构造，不默认全scope。字符串地址/hash先格式校验，不猜格式。
- plan：`OrderBuilder.make(chain_id, signer=None, options=...)`→`get_approval_steps(scope)`；不签、不读key、不RPC。返回每一步token/spender或operator和目标说明。HEAD make无signer没有contracts，不能把builder存在当check可用。
- check：显式owner、RPC/只读contracts上下文，使用SDK导出的地址/ABI，构造无签名只读Web3 contracts；不为查询调用带signer make。不假定check_approvals支持无signer，T3验证支持则调用，不支持则对官方步骤直接只读 allowance/operator 原值并比较；缺任一上下文READ_UNAVAILABLE。ERC20满足条件是原始allowance>=本次显式required_amount，不能用HEAD按MAX_INT256判断的satisfied字段代替。
- approve：必须`--execute`及`--confirm-target`与本次规范化目标完全匹配；ERC20显式`--token --spender --amount-atoms --decimals`，正有限整数、拒绝MAX_UINT256及MAX_INT256哨兵，不能传省略amount；allowance已足则no-op。ERC1155显式`--operator --allow-operator`，输出布尔全operator权限警示，不宣传金额封顶；禁止拿ERC20额度代替同意。
- redeem：显式`--condition-id --index-set 1|2 --amount-atoms`及明确NegRisk/yield-bearing布尔路由，市场/condition/token/结算/CT payouts证据必须一致。无结算证据或payout未记录拒绝。标准DRAW按官方已记录每侧payout处理，不自行预测胜负；NegRisk DRAW非法，不自动分拆/遍历另侧。
- 标准CT SDK路由可能忽略amount（仅HEAD证据），因此工具要求明确`--redeem-full-index-set`，amount必须等于读回该选中index_set的全部余额，并告知交易本身赎回该选定set全部余额而非金额限额；不省略输入金额、不默认全余额，不声称支持标准partial amount。partial请求INVALID_INPUT，SDK调用0。NegRisk支持显式amount<=余额，向SDK传该整数。yield-bearing走对应官方路由，不能猜赎回汇率。

CLI子命令固定为plan/check/approve/redeem；plan另以`--operation approve|redeem`明确计划类型，市场为`--market-id`，审批侧为`--side buy|sell`。所有路由布尔参数要求显式true/false，不以省略猜false。check/写操作的只读上下文来自显式`--rpc-url`与官方地址/ABI，不从secret配置补齐。`--confirm-target`必须等于plan输出的target_digest：对operation、chain、owner、mode、market、side、condition、index_set、amount_atoms、decimals、token、spender/operator、路由布尔及full-index-set同意等本次适用公开字段，按ASCII键排序紧凑JSON（无空白）后SHA256；不适用字段不加入，不含RPC URL、密钥或临时余额。任何scope改变都改变digest，无法匹配则INVALID_INPUT、签名0。receipt复查时check需携原同一目标scope与`--tx-hash`，不只看hash就宣称到账。标准full-selected路径在signer加载前重读余额，变更则停止；仍明确告知外部并发到账可能改变选中set全部赎回量，不能宣称协议层amount封顶。

输入拒绝顺序固定：解析/数值/格式→明确目标与路由→若写操作缺execute/confirm则EXECUTION_NOT_ENABLED→同链身份/控制关系→制品API能力→只读余额/授权/结算/amount及scope核对→记录before→此时才允许显式signer_loader→SDK调用→receipt→readback。plan/check永远不触发signer_loader。读取不足在signer前停止。未来获准写操作的具体入口为 `--signer-fd N`：N为调用方显式提供的非标准输入输出文件描述符，signer_loader(fd)只在上述步骤后读取，不接受命令行私钥/环境变量/默认凭据路径；缺句柄EXECUTION_NOT_ENABLED。读取后本地派生signer地址核对已声明身份/控制关系，失败ACCOUNT_MISMATCH且SDK资金方法调用0。此参数不建立长期凭据存储，本轮只用fake loader，不提供或读取任何真实句柄。

#### 3.3.7 SDK 制品、返回API与广播hash接缝

T3先完成有界兼容检查，再写业务：仅安装predict-sdk==0.0.22及必要传递依赖到工具隔离环境，记录实际wheel/sdist文件、sha256、metadata名称/版本、import路径，requirements.lock固定所有版本/哈希；记录实际解析制品来源，不要求重做被拒tag probe。不得在共享主仓venv装SDK/升级pip工具链；缺制品/基础依赖无法离线验证则具体报SDK_INCOMPATIBLE/阻断，不换版。

test_sdk_identity的实装断言：metadata version==0.0.22、import predict_sdk来自隔离路径、OrderBuilder及相关scope/options/step/transaction result实际导出位置、五个已知同步方法参数名匹配恢复输出；必要参数类型可构造；make无signer/get_approval_steps在所有transport/signer为会抛错fake时成功且调用0。记录实装返回字段（step定位token/spender/operator、TransactionResult的success/receipt/cause或实装等价属性），sdk_ops::normalize_sdk_result将它们映射为工具固定结果，不推断HEAD结构。没有这些字段或等价可验证方式即不兼容停止，不返回伪成功。

hash保护不是复制SDK_handle_transaction：`sdk_ops::observe_transaction`仅包装SDK实际使用的signer/provider接口，委托原方法，不自建交易、签名、nonce、gas或资金calldata。观察sign_transaction的返回raw_transaction，使用实际Web3 keccak得到候选tx hash并在调用send_raw_transaction之前记录 `expected_hash`；包装发送调用先标broadcast_attempted并记录同一raw hash，再委托一次。RPC返回hash须一致。发送异常亦保留expected_hash（“可能广播”，不谎称服务端已接收）；send成功而receipt等待抛错仍保留已获hash。

这需要在固定发行包实例上安全注入/观察其实际signer和Web3 provider；T3 identity先通过fake证明官方set_approval/redeem_positions确实经过该接口、发送次数至多1、receipt异常时handle保留hash，不能仅测自写observer。允许针对实装实例的局部依赖包装，不修改site-packages、不全局monkeypatchSDK、不继承重写资金交易方法。如发行包无法提供这条可观察路径，或内部会重签/自动多次广播，则SDK_INCOMPATIBLE并停止资金能力实现、交主控裁决，不能回退手写协议或把未知无hash当已满足A-012。

固定输出 `operation,target,steps,expected_tx_hash,broadcast_tx_hash,receipt_status,readback_status,completed,error`。approve只在receipt.status==1且同token/spender allowance>=明确目标（operator为同owner/operator=true）后completed。redeem需receipt.status==1，同condition/token份额减少与本次scope相符，同抵押币到账与官方payout/该路由读回相符（官方yield兑换值若无法取得则待核对）；交易receipt匹配本tx/目标owner，不能用账户总余额上涨替代。并行无关转移导致差额无法归属就TX_UNCONFIRMED。

pending/revert/receipt丢失/到账或授权读失败均completed=false，保留hash/步骤；revert标receipt_status=reverted并用TX_UNCONFIRMED表达操作未完成，不自动重试。后续`check --tx-hash`仅复查原交易/目标，不调用资金方法。plan/check signer/广播调用0，approve/redeem fake断言只调用单一scope一次；不采用SDK“all approvals”批量默认。

### 3.4 持久化设计（Persistence Design）

无新增生产持久化需求；无数据库、schema、索引、TTL、迁移、journal或恢复服务。上述attempt/累计/预算只在Broker State、PositionStore及进程gate，不把日志当自动恢复主账。

| 存储对象 | 触发点 | 字段/过滤 | 错误与恢复 |
|---|---|---|---|
| 既有脱敏诊断 | fills::submit_once / runtime::apply_snapshot / sdk_ops::normalize_sdk_result | code/step、账户模式、脱敏地址、market/token、order ID/hash、tx hash、已知累计/完整性/预留；禁止JWT/私钥/签名/headers/原始私密载荷 | 不输出raw exception；日志缺失不自动清风险；进程重启按人工核对 |
| 本主题过程目录 | 各阶段handoff | changed_files、版本来源、真实命令/结果、未执行边界；不放真实secret/原始账户数据 | 本地data忽略，不等于提交/备份；不覆盖历史拒绝证据 |
| 结果主题目录 | T3/T4实际验证后report/evidence | 仅真实离线结果、明确fake来源与SDK制品身份/哈希 | 不以合成回执冒充线上成功，不自动删除/复制/归档 |

### 3.5 UI/原型设计

无。仅现有CLI增量；无Web界面或服务。

## 4. 实现计划

1. 先冻结并实际验证隔离SDK制品/API/纯计划/观察hash接缝（A-001/002/012中的实装部分），失败具体停止；不重做tag网络probe，不读取真实凭据。
2. RED：在表列colocated/Python文件增加矩阵测试，假HTTP、假RPC、假SDK/provider与账户；所有网络/secret访问默认抛错。保留真实失败输出；不能先写helper再只测helper。
3. GREEN：先共享类型与fills/account纯算法，再接原Predict place/POST与tracked handle，然后Broker take/rest/sync、copy/monitor及人工确认入口。按同义提取→改行为顺序控制G3和保护文件。
4. 实现同BOT SDK工具和文档，先plan/check再显式单目标方法；标准redeem amount、operator及hash观察必测。不进入Rust订单热路径。
5. 跑12项定向测试和一次受影响离线回归/编译/格式检查，输出真实命令/退出码、SDK制品信息、changed_files/行数/保护差异；独立Verify/Review由后续角色重跑。T2不执行这些命令。

允许实现者决定局部变量/私有辅助函数和排版；不允许重定上述字段单位、失败优先级、allowlist、闭合谓词、输入拒绝顺序或SDK版本。

## 5. 测试策略

### 5.1 执行位置、fake 边界与命令组

下述全部是 T3/T4 待实施/待运行的验证，非 T2 结果。每条命令独立执行，无组合shell。Rust工作目录为BOT绝对路径；Python命令也从BOT运行，使用tools/predictfun/.venv/bin/python，不使用主仓venv装SDK。

- R(n)：`cargo test --offline --locked aNNN_`，将NNN替换为三位编号（如A-004对应 `cargo test --offline --locked a004_`）。测试名精确见矩阵；不依赖本地钱包/真实API。Cargo缓存缺失不自动联网升级，具体报告。
- P-id：`tools/predictfun/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_sdk_identity.py -v`。
- P-ops：`tools/predictfun/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_sdk_ops.py -v`。
- R-all：`cargo test --offline --locked`；一次受影响回归，包括已有paper撮合/费用、DecisionCore/历史回放纯测试、分页/限额和其他venue，不启动新paper或94日研究。
- C-all：`cargo check --offline --locked --all-targets`；覆盖TakeResult所有直接匹配者和其他venue/fake构造编译。
- Fmt：`cargo fmt --all -- --check`；Diff：`git diff --check`。锁文件不能为通过测试而更新。

SDK安装仅T3隔离环境，先生成固定依赖锁及制品清单，再使用隔离解释器 `-m pip install --require-hashes -r tools/predictfun/requirements.lock`；不在T2安装。锁生成记录实际解析结果/传递依赖和hash，不把HEAD tag commit充作wheel hash。身份验证测试的实际返回适配不兼容即停止，不让开发者自行换协议。

Rust fake应在原Predict client请求接缝注入transport，返回OpenAPI形状JSON；业务RPC使用account helper的只读fake。运行Broker::take、sync_live、seed_from_venue原公共入口，驱动真实解析/adapter，不直接塞最终金额进State。POST计数/签单次数、跨token下一次take被挡、余额/持仓/预留水位是必断言。将provider/signers作为会抛错的fake隔离，不能以localhost服务器与线上连接混用。Python身份/API测试装真实包但provider为fake；其余工具行为用严格fake SDK，再用至少一组真实发行包+fake signer/provider验证资金方法实际接入observer；不真实签名/广播。

### 5.2 A-001–A-012 逐项可证伪映射

| 编号 | consumer入口 / fake边界 | 输入与必须断言 | 精确拟测试名 / 命令 |
|---|---|---|---|
| A-001 | sdk_ops实际import、Ctx::connect无钱包测试；SDK transport默认禁止 | metadata=0.0.22、安装路径/制品锁；无SDK Rustpaper路径不增加SDK或key前提 | `test_a001_distribution_identity_and_api`（test_sdk_identity）；`a001_paper_without_wallet_or_sdk`（runtime/live）；P-id、R(001)、C-all |
| A-002 | cli→sdk_ops→真实纯SDK / fake secret及只读contracts | 缺目标INVALID_INPUT；plan正确scope且sign/send/secret=0；check缺owner/contracts/RPC=READ_UNAVAILABLE；有限allowance不按MAX判断 | `test_a002_plan_and_readonly_check_never_load_signer`、`test_a002_real_sdk_plan_without_transport`；P-ops、P-id |
| A-003 | Predict fake HTTP/RPC→Broker::take | 请求10；终态0+完整空matches+不可执行证据：增量0/VWAP=None/预留0；accepted/open0/404对照保留R0、阻断同账户另token | `a003_broker_terminal_zero_vs_open_unknown`（runtime/live）；R(003) |
| A-004 | Predict自身leg JSON→Broker take/sync→State；含SELL | 4@.40后6@.50；中间Q4/C1.60，最终Q10/C4.60/VWAP.46、现金4.62、净9.9；成本/fees不双扣；SELL10@.50 fee.02时净现金4.98、库存减10；其他腿不计入 | `a004_broker_actual_cash_fee_net_inventory`（runtime/live）、`a004_own_leg_mapping_and_sell`（fills）；R(004) |
| A-005 | sync_live并发→State同锁；fills累计快照 | 重复snapshot/同generation只应用一次，旧generation不回退；Q已知fee后补不重复Q；新generation累计减少或已知费修订报RECONCILIATION_REQUIRED；protected=max(R0,B)，不R0+B | `a005_broker_cumulative_once_under_concurrency`（runtime/live）、`a005_cumulative_field_completion_and_conflict`（fills）；R(005) |
| A-006 | JSON parser→Broker/PositionStore | 完整部分终态只记部分并放余量；全量缺费/价格或未知净量不建可卖头寸；负/NaN/非原子数/未知币种/单位矛盾明确错误，不fallback | `a006_broker_incomplete_and_invalid_facts`（runtime/live）、`a006_invalid_units_and_fee`（fills）；R(006) |
| A-007 | place_tracked→假HTTP→Broker连续tick及copy/monitor | hash后超时/损坏/401/无ID/普通Err与任务取消保留handle/R0；再次take拒绝；恢复只查原hash，后续健康同意图亦不新签，POST<=1、无新salt；copy不满额，SELL未知不close且下一tick不重发 | `a007_broker_submission_identity_and_no_replay`（runtime/live）、`a007_post_401_not_replayed_get_refresh_preserved`（fills）、`a007_copy_unknown_not_full`（order_executor）、`a007_monitor_unknown_sell_no_retry`（position_monitor）；R(007) |
| A-008 | Broker rest/remove/sync→假remove/订单/matches/RPC | remove成功→late部分→查询失败/仍可执行→最终权威闭合；只有最后按实际释放余量，late填一次、保持removing/账户阻断；无ID亦保留hash | `a008_broker_remove_late_fill_closure`（runtime/live）；R(008) |
| A-009 | seed_from_venue及take运行检查→account完整fake | 各余额/gas/授权/订单/持仓失败不归零；多页/循环/缺页/触顶失败保留旧风险；完整空才能knownzero；chain/address/mode不符ACCOUNT_MISMATCH；held_wei多页 | `a009_account_pagination_identity_and_read_failures`（account）、`a009_broker_startup_and_runtime_account_gate`（runtime/live）；R(009) |
| A-010 | main参数解析→install_run_confirmation→seed/take；sports复用入口 | 空内存且旧订单/未知预算阻断；仅确认flag仍不能覆盖风险；错误hash/账户声明不放行；官方已解释+本次人工确认才按原限额可新增 | `a010_restart_confirmation_cannot_override_risk`（account）、`a010_broker_restart_gate`（runtime/live）；R(010)、C-all |
| A-011 | cli→sdk_ops→fakeSDK/只读route/结算 | 缺execute/目标/有限额/operator同意或未结算，sign/send=0；合法明确单scope仅1次；标准partial拒绝、full-selected显式同意；NegRisk显式量、yield正确路由、标准DRAW依payout/NegRiskDRAW拒绝 | `test_a011_explicit_approval_and_redeem_routes`、`test_a011_standard_redeem_amount_not_silently_ignored`（test_sdk_ops）；P-ops |
| A-012 | 实装SDK方法+fake provider观察；工具normalize/readback | hash前/后故障、send返回丢失、receipt pending/revert/丢失、receipt成功但授权/份额/现金读失败：completed=false且hash/步骤保留、send<=1；最后同目标读齐才true；输出无secret/签名；paper/其他venue回归 | `test_a012_real_sdk_broadcast_observer`（test_sdk_identity）、`test_a012_receipt_readback_hash_and_redaction`（test_sdk_ops）；P-id、P-ops、R-all、C-all |

A-004 Decimal合成向量只验证公式，不是真实API回执；T3须另用原子整数JSON驱动adapter。A-005重复快照与单扫描重复歧义记录分开：后者不得用假ID强行去重为完整。A-007取消场景通过task.abort后读取原State handle与再次take计数验证，不只断言返回错误。所有A行本T2未运行，无PASS标记。

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| 官方API amount/price单位说明不足或成交转移不能归属 | 原子映射+官方累计/同交易读回交叉核对，字段保留Unknown | 保留已知数量风险/原预留并停新增，不用模型价格/费率冒充实际 |
| 发行包与HEAD行为不同、无法观察发送hash | T3先验实装API及资金方法fake路径，不改SDK源码 | SDK_INCOMPATIBLE具体停止；不得换版/手写资金交易协议 |
| auth重放、超时/取消后丢身份 | POST NoReplay、共享handle发送前绑定hash、预留不靠局部返回 | 查询同订单，保留预算；不自动重发/补余 |
| remove与链结算竞态 | 明确不可执行证据+最终累计匹配 | 继续removing/Unproven，不能拿removed释放 |
| 无持久恢复/多进程互斥 | 新运行人工核对/预算、单运行入口的限制明示 | 未解释风险不继续；无新增恢复服务/数据库 |
| 标准redeem忽略amount、operator无限权限误解 | 标准选中set全量明确同意与金额核对，ERC1155单列布尔权限 | partial/无同意拒绝，不自动赎回其他set或市场 |
| 原始错误泄漏敏感载荷 | 固定脱敏code/step/身份与事实白名单 | 错误不打印raw；测试使用哨兵secret断言缺席 |
| 大文件/共享接口扩散 | 两个候选helper+runtime私有live模块，保持TakeResult形状 | G3按§3.1最小提取，不改保护策略求通过 |

当前未部署，回滚仅描述候选差量：基于已有baseline/before证据，由后续获准实现者逐文件撤销本次allowlist中新增接线/新文件的候选diff，保留其他卡改动与全部证据；不执行git reset/stash/clean/checkout、删除既有证据、更新gitlink。恢复旧源码不意味着旧live未知满额行为可安全启用；保持live不启用，paper原入口不变。无生产schema回滚、真实资金反向交易或撤销授权动作。本T2不实际执行回滚。

## 7. 交接给实现者

- 必须遵守：来源RFC/SPEC V1.1、精确文件矩阵、单位与错误契约、先预留后可能发送、同hash也不重发、完整性/终态/数量分离、默认无signer、实装SDK前置验证及所有当前禁止动作。三层窄修订输入已按本节官方直接SDK/Privy依据闭合；仍待主控Gate/更新原Implement正文与候选身份，不能据此自动续接实现。
- 可自行判断：私有函数排布、测试fixture局部命名、无语义差异的提取；不得增加隐含可配置资金阈值或第二执行入口。
- 退回条件：固定发行包方法/结果/observer无法满足契约、只读ABI/部署/单位无法映射、需增加allowlist文件/依赖或修改保护文件、上层契约冲突、新安全拒绝。给出file:line或实装制品证据和最小裁决问题，不把问题交开发者猜。
- 本T2静态检查只证明文档结构/链接/路径/空白/公式可复算，不证明SDK或业务正确。T3/T4真实运行后才可填写12行测试结果；独立Verify/Review不跳过。
- 未执行项：联网取证、SDK安装/import执行、Cargo/pytest/业务测试、新paper、真实账号/认证/签名/私有API/订单、链上资金操作、生产数据库、服务/调度修改、Git提交/推送/gitlink更新。后续真实试运行需具体授权，工程通过不等于实盘或盈利。
- 本卡不创建下游，由主控读三层及handoff做Design Gate后派Implement；T2完成仅表示本设计输入闭合，不是Gate替主控签收。

## 版本记录

| 版本 | 日期 | 内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-11-13 | 单次提交/累计事实/实际consumer/账户人工预算/SDK薄工具与12项验证设计；保留发行包及真实资金未验证边界 | YQuant Principal |
| V1.1 | 2026-11-13 | t_188a7257 显式RPC/部署ABI；官方快照闭合直接SDK/Privy gas地址及owner/初始化/逐单ERC-1271控制谓词，保留run3669历史；原20路径矩阵与12项验收不变，待主控Gate | YQuant Principal |
