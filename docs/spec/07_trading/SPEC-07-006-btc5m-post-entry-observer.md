# SPEC-07-006: BTC5m 持仓后只读观察行为与验收契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | Draft V1.1；2026-11-19 因果水位落盘修订，待独立文档核验与实现验收 |
| 作者 | YQuant Principal / yquantprincipal |
| 创建 / 更新 | 2026-11-18 / 2026-11-19，Asia/Shanghai（UTC+08:00） |
| 来源 RFC | [RFC-07-006](../../rfc/07_trading/RFC-07-006-btc5m-post-entry-observer.md) V1.1 |
| 工作区 / 来源任务 | /home/pascal/workspace/yquant-investment；t_408e60a0 |
| 后续 Design | docs/design/07_trading/DESIGN-07-006-btc5m-post-entry-observer.md V1.1；本次同步既有独立实体 |
| 执行 / 验收角色 | Design: yquantprincipal；Implement: yquantdeveloper；独立 Validate: yquantreviewer；Gate/Closeout: 主控 yquant |

## 1. 需求摘要

新增独立只读观察，默认 OFF，仅允许在原 unsigned controlled phase1 显式 opt-in。对 Broker 实际正净持仓，沿已有 5 秒 tick 复用当次输入和原 phase1_valuation，输出原始概率、波动、来源/时间有效性、双边报价及全持仓 bid 退出估值。保留 ALREADY_ENTERED 早退和原入场、资金/风险、EWMA、交易时钟/事件链全部行为。观察没有候选或执行权，不增加请求/轮询；观察缺数或故障只表示观察不可用/不完整，不改变交易结果。

## 2. 范围与真实基线

### 2.1 必须范围

| 需求 | 必须输出或行为 | 来源 |
|---|---|---|
| R-01 非干扰 | 同输入 OFF/ON 交易 trace/状态完全一致；零额外获取、observe、evaluate、执行 | RFC §3–4；卡面硬边界 |
| R-02 原始模型 | raw p_up/p_down、sigma_raw/sigma、samples、epoch、时钟和失效原因 | RFC §5.1、§5.3 |
| R-03 退出规模 | Broker 净 Q/成本 K；持有 token 全量 bid walk 与深度完整性 | RFC §5.2 |
| R-04 费用证据 | paper 已确认规则与真实未知费用分责，净值/PnL 不伪造 | RFC §5.2 |
| R-05 可消费证据 | 独立版本旁路、首次写入前校验、只读消费、覆盖/失败可见，交易协议不变 | RFC §4.2、§6 |
| R-06 有界生命周期 | 首次可得正持仓至 round 结束/实际结算/run 停止最先边界；无新采集 | RFC §4.1 |

### 2.2 真实源码与文件职责

BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。本表是 Design 定位入口，不是本阶段或后续任意目录写许可；新增路径、精确 allowlist、hook 和测试由 Design 核实。

| 已有路径（相对 BOT） | 当前能力 | 只允许的必要增量职责 |
|---|---|---|
| src/bot/arbitrage.rs | tick_phase1 同 tick 获取，trade_phase1 唯一交易消费链 | 只读旁路薄接线、持仓市场覆盖；不得改原入场次序/时钟 |
| src/bot/arbitrage/phase1.rs | phase1_valuation(&self)、epoch/reset/sigma/samples；evaluate 有副作用 | 如必要，极小只读状态/输入一致性访问；不重构或改交易估值/guard |
| src/bot/runtime.rs | Broker::holding/holdings、Holding、token_book、walk | 优先复用，非必要不改；不执行 take/apply 或改 State |
| src/bot/runtime/paper.rs | paper 现金/费用、filled_candidates、原事件 emitter | 复用事实/规则；如需只读关联只给最小 seam，不改原 emitter/序列语义 |
| src/bot/quoting.rs | Known::get 与 tracked 市场已获 books | 复用，不扩展网络集合/获取频率 |
| tools/predictfun/btc5m_control.py | 严格 v2、supervise、首次 write、关系校验与原 lifecycle | 显式旁路接收/验证/持久化/coverage 薄接线，原交易消费者不变 |
| tools/predictfun/tests/test_btc5m_control.py；现存 Rust 相关测试模块 | 原回归/fake clock/真实 emitter 消费路径 | 定向旁路集成及原行为回归，不削弱旧断言 |

本阶段源码事实见 RFC §2.2；旧 65 笔/4984 事件及 2871 次无概率来自已独立验收复盘，不在本卡重算。旧源时钟未知不因新功能变成已知。所有新逻辑字段在 §4 明确标为待实现契约，不冒称代码已有同名 struct/函数。

### 2.3 非目标与禁止项

不做交易/退出/反手/加仓/对冲、优化退出点、择优回填、PnL 策略反事实、校准/参数搜索、第二 core/Broker/账本/执行器、新采集/WS/服务/队列平台、恢复/调度、真实 API/DB/凭据/依赖变更。原参数和来源 guard、100/2/2/10/20 USDT、poll_secs=5、min_edge=0.03、min_secs_left=30、floor/half-life/样本门槛不变。不开任何新 paper/影子盘或观察服务，不授权 git fetch/merge/add/commit/push/reset/stash/clean/checkout。

V1.0 原文档阶段只写 RFC/SPEC 的范围为历史。V1.1 用户批准同步既有 RFC/SPEC/Design 三实体；本次修复的唯一结果报告使用 data/reports/2026-11-19-btc5m-observer-runtime-fix/report.md 追加节及 evidence/ 新叶，原报告/证据只读保留，无 data/tasks/ 或任务镜像。代码增量仅 Design §3.4.5 三路径。

## 3. 功能规格

| 编号 | 行为 | 可观察要求 / 拒绝边界 |
|---|---|---|
| F-001 | 限定装配 | 默认 OFF，opt-in 仅原 unsigned phase1；普通/signed/history/replay 默认无旁路；开关不授权运行 |
| F-002 | 同 tick 只读采样 | 不重复获取/observe/evaluate；读取真实持仓与原模型，无 CandidateContext |
| F-003 | 原模型原状态 | 同源/epoch 且当前已接受 spot 才估值；预热/换源/断流/时钟错误如实 null |
| F-004 | 双边报价 | Up 来自 Yes book，Down 来自原 mirrored；标镜像来源，不表示两本独立深度 |
| F-005 | 全持仓退出 | 对 Q 净份额按持有 token bids 全额 walk，非 q(order_usd) 或 BUY 侧 ask |
| F-006 | 明确成本口径 | model hold / gross exit / paper net exit / actual fill 四种证据分开 |
| F-007 | 独立输出与消费 | 旁路独立版本/序列/校验/coverage；不进入 BTC5M_EVENT/交易关系图 |
| F-008 | 有界终止与故障 | 无补采样/补数；终止/输出故障不产生资金动作；证据完整性单独报告 |

## 4. 数据与接口契约

### 4.1 输入、采样与非干扰

1. 输入只来自原 tick 已有 ObservedSpot、ObservedBook、官方 TradableMarket/Known、DecisionCore 活跃状态及唯一 Broker 的只读正持仓快照。观察点复用已有真实 CheckTime，禁止为观察新增或重排交易路径的 Clock::now 调用；不能用写盘时刻重新计算交易 T。Design 必须明确快照相对原交易处理的位置以及同 tick 新 fill 是否纳入，且该选择在 OFF/ON 中不改变原链。
2. 每 tick 每已持仓 market/token 至多一条 ACTIVE 记录。已持仓 market 不在 selected 时仍在范围内：复用 Known/tracked 原先已请求的 book 和同 symbol quote；不得重新 evaluate 已脱离 selected 的市场。失败 tick 只用实际已有或明确缺失的输入，不为补观察恢复旧 quote/book 的 freshness。
3. 原 observe_phase1 每有效获取只一次；已持仓原 EVALUATE 仍 ALREADY_ENTERED、无 candidate，观察不生成 decision/candidate ID，不增加 evaluate 次数/修改 last_phase1_check/revision/entered。只读 API 不得隐式 reset、刷新 market revision、触发 marks/loss latch 或消费候选。
4. 观察不调用 Broker::take/take_candidate、apply_buy/apply_sell/apply_settlement、reserve/close/confirm_fill，也不以克隆 core/Broker 后模拟一次交易替代只读。读取 holding 不等于获准修改 holding。
5. 固定同输入、同显式时钟、同初始状态时，OFF/ON 的原交易事件内容/序号/次序、候选/订单/账务/风险/entered/vol 状态、获取/observe/evaluate 和交易时钟调用序列完全相同。测试不能忽略 ID、拒绝原因或数值差异；仅测试 run_id 等装配身份可预声明一对一映射。实际 OS 时间有计算/I/O 开销，不承诺真实运行零延迟；旁路不插入候选至 PRE_APPLY 的临界路径，不允许重试等待或无界缓冲。

### 4.2 有效性与原模型

- 原模型只用原 phase1_valuation(&self)，沿相同有效 floor、EwmaVol/digital_up。raw 表示未校准输出，不是未做 floor 的第二概率。p_down=1−p_up；sigma_raw 为 floor 前、sigma 为原有效 floor 后，单位沿原每平方根秒的波动率。
- 调用前只读核验官方身份/固定 strike/300 秒区间及可得性、当前 now、spot/source/actual_pair、当前活跃 epoch/最后接受 receipt 的匹配、原观察是否接受、20 returns 和有限正值。pure helper 自身不负责全部输入校验，不能仅凭它返回 Ok 宣称当前输入有效。拒绝新 spot 后不能把旧暖 epoch 与未接受新报价混算。
- 时钟沿原 ObservationClock：request_at/received_at、两 elapsed、source_at/source_time_status/freshness_basis；缺 clock 为 null，不补 now。原 request_span≤5000ms、acquisition_age≤10000ms 和真实 source age≤10000ms（均含等号）沿 07-005；未来/倒序/回退/不一致拒绝，不 clamp。观测不会自行修复或重置 core。
- source_at=null + MISSING/RECEIPT_BOUND 合法，表示仅本地获取边界已知；不能冒称源时间已验证。Binance/BTCUSDT 与 Coinbase/BTC-USD 对应，source_state 沿 PRIMARY/DEGRADED/UNAVAILABLE；settlement_provider 仍来自官方 CHAINLINK/UNKNOWN，不替换预测源。
- source/key 变化、gap>300秒、坏时钟等原状态变化只由原 observe/evaluate 路径发生；观察读取 epoch/reset/samples。预热不足 model_reason=WARMUP，概率/sigma 不给零；回切旧源不能借暖历史。
- 0<T<30 秒仍可观察，不能套入场 ROUND_TOO_LATE 门槛；T≤0 无新模型估值，不能用 digital_up 的到期极限当官方结果。run stop/结束后不继续调用模型。
- 模型与盘口/退出独立验证：book 缺失不强制将合法概率清空，spot 缺失不强制将有效 bid 退出毛估值清空。每类各自给 reason，不以单一全局 success 掩盖部分缺数。

### 4.3 报价与全量净库存 bid walk

Q=同一快照 Broker Holding.shares，K=Holding.cost；在本 unsigned phase1 中 Q 已扣 BUY 份额费，K 是原现金成本。不得用 q_gross、原订单金额除当前价、常数2 USDT或另造名义持仓。Q>0 且有限、K≥0且有限，token 必须精确等于本 market yes/no token；token_book 对任何非Yes会镜像，因此调用前必须验证，不能把未知 token 默认为 No。

1. Up bid/ask 从同 tick Yes book，Down bid/ask 通过现有 BookSnapshot::mirrored()/token_book 的原舍入映射。Down 数据标签固定 MIRRORED_YES_BOOK，不伪造独立 No book；两边流动性不能相加用于覆盖 Q。报价不是新仓 BUY 信号。
2. 退出用持有 token 的 bids，从高到低按原顺序，合法价格在(0,1)、size>0且有限，双边 touch 不交叉。空/缺 bid、非法 level/次序、缺/过期/非法 book clock 分别标原因。合法空 bids 按 NO_BID 披露；有 bids 但缺合法 ask 的单边 book 按 INPUT_INVALID，不宣称原受控执行路径可接受的全仓退出报价。双边验证只验证 book 有效性，退出仍严格消费 bids，不使用 mid。禁止为让结果变好排序、删档、补档或使用 mid/avg_cost/上一 tick 的 mark。
3. 全额覆盖 Q 的最短 bid 档前缀必须保留，每项原 price/size，末档不裁成 consumed size。累计消耗使用原 full-size SELL walk 与相同舍入/数值语义；不引入新限价、slippage 策略或订单。覆盖的是可见深度下的假设全额卖出，不代表已提交/保证成交。
4. covered_shares 是在有效可用前缀内实际可覆盖的 min(Q,Σsize)，单位 net shares。足额 depth_complete=true 才给 full exit_vwap 和 gross=Q×VWAP；不足 false，保留已耗尽前缀/covered_shares，VWAP/gross/net/PnL 都 null，不把部分 VWAP 冒称全仓值。无合法输入时 depth_complete=null、covered_shares=null；明确合法空 bids 为不足 false、covered_shares=0，并给 NO_BID。
5. 同原 full walk 的已知浮点容差/clean 保持，不为观察更改它；展示不得把实质少量缺口用整数截断掩盖。测试必须涵盖原 EPS 附近并说明其原既有语义。最多每数组1000档、每观察记录64KiB（含 framing）；前缀超界为 OBSERVATION_LIMIT，depth_complete=null、全额货币值null，不截断伪 complete，也不影响交易。

### 4.4 费用与价值口径

| 量 | 定义 | 可用前提 / 解释 |
|---|---|---|
| model_hold_value | H=Q×p_token；p_token 为 p_up 或 p_down | 有实际 Q 与合法模型；USDT 期望兑付，不是可卖值 |
| model_hold_surplus | H−K | 同上且有原 K；不是已实现 PnL |
| exit_gross_income | G=Q×全量 bid VWAP | 有完整有效退出深度，不含费用 |
| exit_fee | 只在 fee_basis=PAPER_CASH_FEE 时按下述原 paper 规则得到 F | UNKNOWN 不补零 |
| exit_net_income | N=G−F | 完整深度且已确认 paper fee；不是实际到账 |
| exit_pnl_vs_cost | N−K | 相对原 Q 全部成本的假设净退出差，不写回 realized/NAV |

费用证据只有两类：

- PAPER_CASH_FEE：已核本次 controlled fee model=paper_net_shares、有效官方 fee_rate_bps，沿 src/bot/runtime/paper.rs:312–334 的 SELL 现金扣费语义。r=bps/10000，F=Q×r×min(VWAP,1−VWAP)。按现有 paper 在 full walk 的 VWAP 上计费，不擅自改逐档计费。可复用纯 fee helper 的现金等值返回，但不可调用有写副作用的 apply_sell；不可把 helper 的 BUY 净份额返回当卖出规模。Q 不再次扣份额，K 不再加减入场等值 fee。fee_rate_bps=0 明确合法，费用是已知0。
- UNKNOWN：缺费率、语义未确认、不适用或真实 venue 未来 SELL fee 未知；exit_fee/net/PnL=null。真实 fills.rs 需要已报告 collateral/share fee 事实，当前没有未来成交事实，不能以 paper fee 规则填补。没有额外请求以确认费用，不改真实 fill adapter。

PAPER_CASH_FEE 只表示已确认的 paper 假设规则，绝不表示实际 venue 费用/精度/Gas/返佣已测。当前选择沿已有 paper 规则而非引入新执行收费模型；如后续证据显示该规则未知，就退到 UNKNOWN，不改变交易费用或 guard。model_hold_surplus 与 exit_pnl_vs_cost 分别命名，不混入原 accounting.unrealized/nav/net_pnl。

### 4.5 最小观察记录（待实现逻辑 schema）

schema_version 固定 btc5m-post-entry-observer/1。下表冻结逻辑名称/单位/null 与枚举，不预定内部 Rust 类型、函数签名、framing/FD 或文件名。Design 须给出与本表逐一对应的严格 wire schema、精确 writer/首次过滤写入/reader 落点；可作同义分组，不增自由字段袋/原始 HTTP 内容。所有键存在，未知字段递归拒绝；非有限数、bool 冒数字、重复 JSON 键拒绝，不能经序列化 NaN→null 消除原因。只存 L0 行情和 L1 工程身份，不含 L2/L3 秘密/账户敏感数据。

| 逻辑字段 | 类型 / null | 来源与不变量 |
|---|---|---|
| schema_version | 固定 string，非null | btc5m-post-entry-observer/1；新契约，非已有事件版本 |
| run_id | string，非null | 精确现有受控 run；沿原 run 格式，不是钱包身份 |
| observation_seq | positive integer，非null | 观察专属递增序号；不消费 trade event_seq/decision_id |
| market_id | decimal id，非null | 原 market_id，沿原1..78位十进制 ID 约束 |
| token | decimal id，非null | 该观察系列的实际原持仓 token，必须归属该 market |
| sample_state | enum，非null | ACTIVE / ROUND_ENDED / SETTLED / RUN_STOPPED；§4.6 |
| observed_at | UTC timestamp，正常非null | 所复用 tick/check 时点，RFC3339至少毫秒；不是写盘时刻 |
| observed_elapsed_ms | nonnegative integer，正常非null | 同一 CheckTime，原 run 的经过时钟原点 |
| starts_at | UTC timestamp/null | 已知官方开始，缺失null |
| ends_at | UTC timestamp/null | 已知官方结束，缺失null |
| secs_left | finite number/null | (ends_at−observed_at)毫秒差/1000；可负用于结束披露 |
| strike | positive finite number/null | 官方固定起价；缺/无效null，不由 spot 重置 |
| position_net_shares | positive finite number/null | 当前实际净 Q；实际已移除持仓时null，不保留假库存 |
| position_cost | nonnegative finite number/null | 同快照 K，USDT；与 Q 同时可得 |
| prediction_source | enum/null | Binance / Coinbase / null；当次 quote，缺则null |
| actual_pair | enum/null | BTCUSDT / BTC-USD，与 quote 源匹配或共同null |
| source_state | enum，非null | PRIMARY / DEGRADED / UNAVAILABLE；当次 quote 服务状态 |
| source_epoch | positive integer/null | 原 core 当前活跃 epoch；从未初始化null；不伪称该epoch已接受当前quote |
| reset_reason | 原 enum，非null | NONE / FIRST_SAMPLE / SOURCE_SWITCH / LONG_GAP / CLOCK_INVALID |
| settlement_provider | enum，非null | 官方 CHAINLINK / UNKNOWN |
| spot | positive finite number/null | 当次有效数值报价，缺/非法null；有效性仍看 model_reason |
| spot_clock | 原 clock 对象/null | 原 ObservationClock 全字段；缺输入null；source_at可null |
| book_clock | 原 clock 对象/null | 同上，对应唯一 Yes book 与其镜像，不造第二时钟 |
| samples | nonnegative integer，非null | 原当前 epoch returns 数；未初始化为真实0 |
| sigma_raw | nonnegative finite number/null | 已暖合法模型 floor 前波动，未有效估值null；真实0与未知不同 |
| sigma | positive finite number/null | 原有效 floor 后波动，未有效估值null |
| p_up | finite [0,1]/null | 原纯估值 raw 概率，失败null |
| p_down | finite [0,1]/null | 与 p_up 同时null或严格互补（传输容差内） |
| model_reason | enum，非null | §4.7；OK才给完整模型值 |
| up_bid | finite (0,1)/null | 原Yes best bid，缺/无效null |
| up_ask | finite (0,1)/null | 原Yes best ask，缺/无效null |
| down_bid | finite (0,1)/null | 原镜像No best bid，缺/无效null |
| down_ask | finite (0,1)/null | 原镜像No best ask，缺/无效null |
| down_quote_basis | 固定 enum，非null | MIRRORED_YES_BOOK，不能当独立 No 响应 |
| exit_bid_levels | array/null | 持仓 token 最短全额前缀/不足时有效全部bids；每项仅price/size |
| exit_covered_shares | nonnegative finite number/null | §4.3；明确空 bids 为真实0，不是缺数默认0 |
| exit_depth_complete | bool/null | 全额覆盖true，合法不足false，不能判断null |
| exit_vwap | finite (0,1)/null | full Q bid walk；不完整/过期/非法一律null |
| exit_gross_income | nonnegative finite number/null | G，USDT；与 full VWAP 同步有效 |
| exit_reason | enum，非null | §4.7；OK才宣称全额bid可估值 |
| fee_basis | enum，非null | PAPER_CASH_FEE / UNKNOWN；不是实际 fill fee 状态 |
| fee_rate_bps | integer [0,10000]/null | 确认规则的有效费率，未知null，不默认0 |
| exit_fee | nonnegative finite number/null | F，USDT；UNKNOWN或无full VWAP为null |
| exit_net_income | finite number/null | N，USDT；非实际净到账 |
| exit_pnl_vs_cost | finite number/null | N−K，USDT；非已实现PnL |
| model_hold_value | nonnegative finite number/null | H，USDT；无持仓/无合法模型为null |
| model_hold_surplus | finite number/null | H−K，USDT；同上 |

observed_at/elapsed 正常记录必须同时存在。原 clock 无法产生有效时点时不伪造时间：该次记录不输出为正常样本，coverage 明确 CLOCK_UNAVAILABLE/不完整；Design 给出可验证的计数/终止表达。非法但实际读到的时钟值仅在类型合法且能标 CLOCK_INVALID 时保留，不能声称可估值。原始 touch 可以在 book stale 时披露，但 exit_reason 必须 BOOK_STALE 且 full 货币值为空，reader 不能忽略有效性取值。

无持仓时不生成 ACTIVE 序列。已开启系列的 SETTLED/RUN_STOPPED 终止记录可保留 token 身份，实际已无持仓则 Q/K与所有持有/退出货币值null；不得从旧fill复制 Q 冒称当前库存。直接纯函数的无持仓测试也必须无退出规模/货币值，不扩大成全市场无仓观察功能。

### 4.6 生命周期与覆盖

- 起点：首次原 Broker 正 net fill 之后存在实际持仓的可用原 tick，不能在 reservation/blocked/零fill时启动。Design 明确是否同 tick 记录，但必须从首个所定义可用点起一致覆盖，不能按盈利/概率筛点。
- ACTIVE：在已有5秒 tick内采样，0<T，包括末30秒。不要求连续墙钟恰好每5秒，也不补采样；原获取等待/暂停/失败造成间隔如实可见。每个应观察 tick 的失败样本也输出原因，或因无法安全编码/输出而计 coverage 缺口，不能只保存 OK 样本。
- 终点：首次检测 T≤0、原正式结算已移除库存或原 run停止，终止该系列；若同刻同时发生，优先 SETTLED，其次 RUN_STOPPED，其次 ROUND_ENDED。每系列最多一个终止记录；若中断无法生成，coverage 必须不完整，不补造。终止记录不计算新概率/VWAP/退出收入。
- 轮次结束但官方 pending：停止新估值，库存/现金仍由原 Broker 保留，pending及最后 settlement/final 按原协议披露。已有官方结果后可按 run/market/token 只读连接，不把本地 T=0/spot方向当结算或重新启观察。
- run停止/损失latch/deadline之后不因观察再取价、延长loop、继续调用策略或改变原 cleanup预算。已有 tick数据可记录最后状态；缺数据明确不可用。尾查沿原官方结算流程，不增 observer采样任务。
- 观察完整性与交易finalized分开：旁路缺失/坏行/丢行/截断/序号缺口/未终止必须标观察不完整；交易final合法不能抹去观察缺口，观察失败也不能伪造交易失败或改变原资金处理。

### 4.7 原因与缺值约束

model_reason 有限集合：OK、MISSING_INPUT、MARKET_INVALID、INPUT_INVALID、CLOCK_INVALID、REQUEST_TOO_SLOW、SPOT_STALE、INPUT_CHANGED、WARMUP、ROUND_ENDED、SETTLED、RUN_STOPPED。

exit_reason 有限集合：OK、NO_POSITION、MARKET_INVALID、MISSING_BOOK、INPUT_INVALID、CLOCK_INVALID、REQUEST_TOO_SLOW、BOOK_STALE、NO_BID、INSUFFICIENT_DEPTH、OBSERVATION_LIMIT、ROUND_ENDED、SETTLED、RUN_STOPPED。

各域先检查 terminal，再身份/持仓（退出域）、缺输入、输入数值/格式、时钟一致性、请求过慢、age、匹配/暖机（模型域）或bid/深度/记录容量（退出域）。较早失败为主原因，不为记录更多原因继续对无效数据运算。终止原因直接与 sample_state 对应，所有新模型/执行值null。UNKNOWN fee 独立，不将可用 gross 强行变成无盘口；它本身不能使 exit_reason=OK 变成“净值已知”。

真正的 p=0/1、sigma_raw=0、bps=0、合法空 bids covered=0 与 null 不同。对于应有但字段缺失的坏消息，reader 必须拒绝并记观察不完整；对于合法记录中的 unavailable，保留null+reason。不能漏键后用 get(...,0) 或 ffill/interpolation 修复。无 raw 错误/URL/HTTP/body/secret detail 字段。

### 4.8 输出、过滤与只读消费者

1. 交易 btc5m-controlled-paper.v1/v2 的 BTC5M_EVENT 原 envelope/schema/kind/event_seq、decision_id、关系/公式校验、accounting 与 started/ended 含义一律不变。观察不能新增原交易事件、向 source.decision 塞新字段，不能将原 ALREADY_ENTERED 改成 ELIGIBLE 或补 p_up 来冒充原评估。
2. 传输 wire/1 与 §4.5 record/1 固定不变；V1.1 落盘保存完整已验证 SAMPLE envelope（含 after_event_seq 与原 record），使用独立可识别 framing 与独立文件，不是被 supervise 丢弃的自由 tracing。具体传输/文件名由 Design 冻结，不要求新服务/通用队列。显式 OFF 时零观察输出/文件副作用，原行为不变；旧 run 没有旁路为 OBSERVATIONS_UNAVAILABLE，不创建空文件伪完整。
3. 真实 Rust writer→现存 launcher 路由/逐行验证→首次旁路 write→本地只读 reader 全链必须存在。对 schema/run/market/token归属、枚举、时钟/null、公式/深度、序号及原fill关联先验证再落盘；不先写raw再清洗。reader须实际被离线测试调用，可与严格校验复用；不为此新增汇总研究平台。
4. 关联只读使用原单次入场的 (run_id,market_id,token) 到原正BUY fill/settlement/final，按每行实际持久化的 after_event_seq 检查 Q/K 与当时账本；fill_seq 必须不大于水位，ACTIVE 时 settlement_seq 须仍在水位之后，SETTLED 时 settlement_seq 须已在水位内。不能以整个日志 last_seq 或时间推断替代缺失水位。同毫秒先后按该因果水位裁定，跨毫秒显著未来/时钟不一致仍拒绝，不放宽公式/时钟；不以 observer 构造第二本可交易库存/现金。观察自己的序号不能进入 _EventRelations 或影响 previous accounting snapshot。未知 token、没有正fill却声称持仓、重复/倒序序号、坏版本/字段/公式拒绝观察证据。
5. 观察校验/写盘/容量错误只禁用或丢弃旁路当前记录，并使覆盖不完整；不得设置原 Phase1Run.output_failed、halt、stop-new-risk、loss_latch 或触发原 OUTPUT_INVALID 停交易。反过来旧交易坏行仍原失败，不混同为可忽略观察行。旁路秘密/任意错误原文不得落盘，也不得以失败隔离放宽父环境/输出秘密边界。
6. 原行界64KiB/每数组1000/秘密递归过滤不放宽；不可无界积压、重试阻塞或吞掉原交易行。共享pipe物理破损/进程退出等原生命周期仍按原规则，不承诺绕过真实I/O故障继续执行。Design 必须给容量/失败状态的精确落点，并测试旁路自身错误与原协议错误的区别。
7. 固定输入数值对拍 abs≤1e-9 或 rel≤1e-9；序号/枚举/身份/交易状态和动作次数精确相等。旁路传输公式校验可沿原1e-7上限，不能放宽原交易恒等式或深度门槛；用容差通过字段校验不等于能把不足的Q改为full。

## 4.bis 持久化契约

无数据库 schema/索引/TTL 变更或自动恢复。观察文件的 V1.1 物理格式保留已有 SAMPLE envelope 水位，区别于不变的 record/1 逻辑字段。§4.5每个逻辑字段都是旁路记录的待实现字段契约，均必有键、null规则如表；run/seq/market/token/时钟/状态为L1，其余行情/模型/公开费率为L0（和run关联时仍按L1工程证据管理），无L2/L3。Design仅决定同义物理分组/文件名，不可删失语义。

| 存储对象 | 规则 | 生命周期 / 兼容 |
|---|---|---|
| 同一新受控 run 目录内独立观察 JSONL | V1.1：严格既有 SAMPLE envelope，键仅 wire_version/kind/run_id/after_event_seq/record；record 严格对应 §4.5；exclusive-create后追加，仅校验及 as-of 关联通过行 | 无自动删除/TTL/迁移/覆盖/上传；中断保留原字节，禁止resume账本 |
| 同目录观察覆盖状态 | 显式OFF/可用/不完整，接收/有效写入/拒绝/丢失与原因可核对；具体schema由Design明确 | 不写任务进度，不改原ended字段含义，不以无终止冒充完整 |
| 原 events.jsonl/started.json/ended.json/public-config.json | 不混入观察，原字段/验证/保留策略不变 | 旧证据只读，旧缺观察明确unavailable；不补写历史 |
| 工程结果 | data/reports/2026-11-18-btc5m-post-entry-observer/report.md；必要evidence/ | 后续独立Validate记录候选/命令/native exit/覆盖/限制；本阶段不创建 |

V1.1 reader 不改返回的 flat records/API 版本或原 coverage schema。每行水位必须是非负真正整数（不接受 bool），不得超出有效原交易日志；漏水位、错版本、重复/未知键、错 run 等必须拒绝并标 INCOMPLETE。legacy flat-only 文件缺因果水位时标 RELATION_UNRESOLVED，不补写、不默认取 last_seq；其余合法新格式行可独立验证，但不能把整个 run 认证 COMPLETE。旧证据不得迁移/补造。

观察覆盖状态只是输出证据，不保存另一份Q/K/现金账本。没有文件时不能默认为所有tick成功，也不因为交易正常结束默认完整。若无法可靠测得producer丢失数量，明确UNKNOWN/INCOMPLETE，不编造精确0。data被Git忽略，不自动备份；无跨项目复制/外发。

## 5. 验收标准

以下均为后续 Implement/独立 Validate 必需场景，本阶段未执行。只用既有离线输入/synthetic、fake transport/clock或受控测试子进程，不启动真实paper，不联网/读凭据/写DB。

| 编号 | 接受输入 / 正例 | 反例与必须结果 | 真实验证路径 |
|---|---|---|---|
| A-001 | 同固定输入/时钟运行观察OFF/ON | 原交易event序列/内容、candidate/order/现金/预留/库存/realized/fees/risk/latch/entered、vol样本/sigma/epoch/revision、时钟调用顺序完全一致 | 真实RoundTaker→唯一Broker→原emitter/launcher；不mock掉被测方法 |
| A-002 | 持仓后仍原ALREADY_ENTERED，旁路有模型值 | 不生成CandidateContext/新decision、不重复evaluate、不把entered设false，额外take/reserve/close/confirm_fill次数为0 | 真实core/消费者spy与状态快照 |
| A-003 | 一次spot/market/book输入可供多持仓只读观察 | OFF/ON网络调用和observe次数/参数完全一致，原获取失败不补请求；禁任何真实socket/凭据访问 | fake transport→原tick获取与Known tracked链 |
| A-004 | 已暖同源、合法strike/T，原phase1_valuation给结果 | 两侧概率互补、raw与sigma_raw/sigma及floor口径一致，不引入Platt/未来结果；与原纯估值对拍 | 同一core纯估值→旁路→reader |
| A-005 | 19/20returns边界、源切换/回切、gap=300与>300秒 | 按原状态暖机/reset，观察不改变epoch/samples；拒绝的新spot不能混旧暖状态估值 | 原observe/evaluate后只读snapshot；OFF/ON对拍 |
| A-006 | 本地clock合法，source=null且MISSING/RECEIPT_BOUND | 不填source_at，仍可按receipt边界估值，reader不声称真实源freshness | 实存clock序列化/旁路校验 |
| A-007 | request_span=5秒/age=10秒及已可得合法输入 | 超界/未来/倒序/elapsed回退/source与标记矛盾给正确原因与null；不新增now调用或复用旧输入续鲜 | fake clock→真实输入检查/consumer |
| A-008 | model有效但book缺/旧；book有效但spot缺 | 各域独立reason与值，不能整条补零或抹除独立有效值；坏价格/NaN/Infinity不进计算/日志 | 真实旁路构建与序列化/reader |
| A-009 | 实际Up/Down净持仓、不同成本/份额 | Q/K精确取原Broker；不是gross、2美元名义量或BUY再次扣份额；未知token拒绝、不默认镜像No | Broker真实holding→token_book |
| A-010 | Yes/镜像No双边touch与持有token方向 | Down标MIRRORED_YES_BOOK、按原舍入；退出为该token bids，不用asks/mid/另一侧买价；不把两本深度相加 | 原mirrored/token_book→reader |
| A-011 | 多档bid足额，恰好足额/跨末档/不同净Q | 最短前缀原price/size、末档原size、full walk VWAP/covered/gross正确；浮点EPS邻界沿旧语义不改 | 原SELL walk与独立Decimal复核 |
| A-012 | 合法空bids、深度不足、乱序/坏size/交叉或缺ask的单边book | 空bid covered=0/NO_BID；不足false/full金额null；非法或旧clock不能伪可执行，不缩Q/补深度 | 真实bid数据→构建→过滤/reader |
| A-013 | 已确认paper fee，bps=0及正bps、VWAP两侧 | F按原SELL现金规则，Q不再扣份额，N/G/K恒等式正确且不写账；不调用apply_sell估价 | 原fee纯规则→旁路，独立数值复核/State不变 |
| A-014 | fee UNKNOWN或缺费率/未确认venue费用 | gross可有，fee/net/PnL全null；未知不能填0，paper数不能冒实际到账，非零SELL share fee事实不套BUY | fee来源审查+实际reader拒绝矛盾记录 |
| A-015 | 同Q/K合法模型和完整退出值并存 | model_hold_value/surplus与exit_net_income/PnL分别复算，不改原mark/NAV/realized；未成交不生fill | 原Broker+旁路+原事件对拍 |
| A-016 | 已持仓离开selected，Known/tracked已有该book | 仍观察，不增加请求集合/交易evaluate；无持仓/blocked/零fill不能制造ACTIVE退出规模 | rescan变化→原Known→真实旁路 |
| A-017 | 0<T<30秒有效，首次T≤0/官方移仓/runstop | 不套30秒入场限制；到期/结算/停止终止，无新模型/退出值，无T=0概率冒结算；不延长cleanup/采样 | 原tick/lifecycle与官方fixture |
| A-018 | pending后原settlement/final、提前停止/进程中断 | 现金/entered与OFF一致；不重启观察，不补terminal或提前兑付；覆盖不完整可见 | 原settlement/监督链→reader关联 |
| A-019 | 真实Rust旁路输出经launcher验证持久化完整 SAMPLE 水位，再reader按原水位读取 | 不只手拼JSON或单测纯函数；旧交易events原样、旁路不进_EventRelations；真实读回模型/深度/费用/原因正确 | 隔离候选binary离线fixture→现存supervise→首次write→本地reader |
| A-020 | 正常/未知版本/坏run或token/漏键/坏null/重复键/枚举/非有限/bool冒数/坏公式/序号重复倒序缺口 | 坏行不首次写入，覆盖INCOMPLETE；合法null不填0；旁路错误不改变交易trace，原交易坏行仍OUTPUT_INVALID | 真实过滤/写入spy/只读reader；对照原交易错误 |
| A-021 | 合法边界内深度和输出；观察写盘/编码/容量失败 | 1000档/64KiB超界不可截断伪完整，不无界积压/阻塞重试，不写raw秘密；旁路fail不设置Broker output_failed/halt/latch | 真实writer/launcher故障注入及原行为对拍 |
| A-022 | 默认OFF、普通/signed/history/replay旧行为 | 无观察副作用，不放宽v1/v2严格校验/秘密/交易限制；不改冻结文件/参数/binary；所有构建显式隔离target | 受影响旧回归、scope diff及冻结身份逐项核对 |

### 5.1 V1.1 必需增量矩阵

1. Yes/No 均有真实 Rust producer→OS datagram→原 supervisor/receiver→首次 write→reader 的同毫秒 fill 后首样本及多 ACTIVE/terminal；明确断言两侧确属同毫秒，OFF/ON 原交易 trace/状态/请求次数不变。
2. 构造时钟/字段/公式均合法且同毫秒、但 after_event_seq < fill_seq 的负例；先证明 validate_record 成功，再证明 as-of 关联拒绝，不能以 CLOCK 或泛 INVALID_FRAME 冒充 FILL 检查通过。另保留跨毫秒真实 fill 前拒绝。
3. 结算同毫秒边界：水位前 ACTIVE/ROUND_ENDED 合法，SETTLED 必须水位覆盖 settlement；提前 SETTLED/结算后 ACTIVE 拒绝，不能用时间启发式倒推水位。
4. 完整 envelope 的严格键/版本/身份与水位边界、legacy flat-only 缺证据 fail-closed、缺观察 unavailable；历史证据原字节保留，不补水位求绿。

## 6. 测试与证据要求

Design 必须给实存入口和精确 argv/cwd/候选目录，Rust Cargo --offline 且显式 --target-dir 指向本主题独立 evidence 候选构建目录或当前worker scratch；不能默认target覆盖旧binary。Python沿原 tools/predictfun/tests/test_btc5m_control.py 的项目 .venv/bin/python -B -m pytest 精确入口，新增测试路径必须在allowlist列明。不得杜撰测试名/数量、安装依赖、跑ignored联网测试/新paper/99日或读冻结未来表现。--offline只禁依赖获取，不替代业务network调用即失败防线。

独立Validate以最终HEAD+工作树文件清单/hash、输入身份、真实命令/native exit及A-001–022逐项证据裁定。实现者自测不能替代独立验收。保留相关07-004/005既有费用、同锁/候选重验、deadline/官方去重/秘密首次写入回归，不削断言或skip求绿。只读观察不以收益、交易笔数、性能提升或新在线窗口为验收门槛。

本阶段只静态核实两个文档实体/互引、源码/消费者事实、费用来源、范围与矩阵，执行单文件空白检查及hash；不声称任何业务测试已通过。安全拒绝停止对应动作及依赖分支，不换工具/包装/执行人重放；可选搬运可OMITTED，必要验收缺失不能done。普通补丁/并发保护在原scope按原工具纠正。

## 7. 实现约束、冻结与回退

- [final-freeze.json](../../../data/reports/2026-11-18-btc5m-joint-forward-validation/evidence/review-preparation/final-freeze.json) 的全部13个files项及prepare-v03参数、旧target/debug/btc_arb_phase1_history、已保存v1/forward制品只读且hash不变；不改phase1_history.rs、joint/model/metrics/reference/history_input/history_performance/unified_data。phase1.rs虽非冻结清单也只能最小只读访问增量，不改原估值/guard。后续开工/收工逐项身份核对，不能只比git HEAD。
- 共享树dirty是既有基线，不reset/stash/clean/checkout，不把原dirty算本卡变更；Design给精确逐文件增量归属。本阶段没有源码修改许可。后续不改旧证据或gitlink来伪造干净状态。
- G3：当前arbitrage.rs1317行/phase1.rs1519行为受控增长。Design说明职责边界、少量增长原因/拆分触发，其他文件按实际大小；只读观察不成为大重构或通用框架理由。
- 回退为保持/恢复观察OFF，交易语义不变，不回滚账本、不清entered/vol、不改冻结binary/证据、不用git destructive命令处理共享dirty。具体接线回退由Design写在自身allowlist内。
- 若严格非干扰、真实消费者或冻结资产内无法实现，必须给主控最小冲突，不擅改授权/公式/原事件契约。真实源时间、实盘费用/成交/Gas/排队、模型校准和收益改善仍为未验证范围。

## 8. 开放问题与阶段交接

开放业务契约冲突：0。以下是下一Design必须落实的工程决策，不是开放交易语义：精确只读hook/快照点（含同tick新fill）、传输framing/路径/wire分组及reader接口、opt-in拼写、容量和失败/coverage schema、逐文件allowlist/G3、离线真实链与隔离构建命令。不能将这些留到实现时自由发明或默默扩大scope。

V1.0 原文档阶段向 t_7e3ae26e 的交接为历史，不重建已完成原功能。V1.1 三独立实体互引须均为 V1.1；独立文档核验后续接原 Fix t_bfce2064，再交原独立 Validate t_3cfa9034 R2，t_572e8264 仍保持 blocked。

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-11-18 | 冻结同tick只读/非干扰、原模型/clock有效性、净库存bid退出/费用证据、独立旁路消费/覆盖及22项验收 |
| V1.1 | 2026-11-19 | 用户批准因果水位落盘：复用完整已验证 SAMPLE envelope 与原 after_event_seq，reader 按逐行水位验证；legacy 缺水位 fail-closed、不回填；补 Both Yes/No 同毫秒、FILL 负例及结算边界；三实体同步并保留原链及未启动 paper 边界。修订者 yquant。 |
