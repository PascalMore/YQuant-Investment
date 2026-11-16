# SPEC-07-005: BTC5m 一阶段正确性与诊断契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 | V1.0，T1 交付候选，待主控文档 Gate；非实现或独立 Validate PASS |
| 作者 | YQuant Principal / yquantprincipal |
| 创建日期 / 最后更新 | 2026-11-16 / 2026-11-16（Asia/Shanghai，UTC+08:00） |
| 来源 RFC | [RFC-07-005](../../rfc/07_trading/RFC-07-005-btc5m-phase1-correctness.md) V1.0 |
| 模块 / 工作区 | 07_trading；/home/pascal/workspace/yquant-investment |
| 来源任务 | t_3ee922da；Pascal 已批准六项一期范围，未批准新行情 paper/实盘 |
| 适配角色 | Design: yquantprincipal；Implement: yquantdeveloper；独立 Validate: yquantreviewer；Gate/Closeout: 主控 yquant |
| 后续 Design 路径 | docs/design/07_trading/DESIGN-07-005-btc5m-phase1-correctness.md（T2 另行产出，不声称已存在） |

## 1. 需求摘要

仅在 unsigned controlled BTC5m 与显式 phase1 离线回放中启用净份额 EV、来源隔离、断流重预热、真实时钟和提交/成交应用前重验。复用现有 DecisionCore、RoundTaker、Broker 同 State 同锁、原盘口 walk、官方结算及 launcher 白名单，不新造执行/账务平台。新证据必须能够复算候选、拒绝和成交，并明确源时间缺失及模型局限。普通调用和旧协议默认不变，工程通过不等于获准真实运行或证明 alpha。

## 2. 范围

### 2.1 六项 In Scope 与来源

| 范围 | 必须行为 | 来源与验收 |
|---|---|---|
| S1 费用/EV | 两费用口径显式隔离；min_edge 分母不变 | RFC §3.1 第1项、§5.3；A-001–004 |
| S2 来源 | 预测源 key 隔离、fallback/恢复、官方 provider 分责 | RFC §3.1 第2项；A-005–006 |
| S3 状态 | 换源/长断流/非法时钟新 epoch，20 returns 重预热 | RFC §3.1 第3项；A-007–009 |
| S4 时间 | 真实 acquisition/source/decision 时钟；提交及应用前年龄/到期复核 | RFC §3.1 第4项；A-010–013 |
| S5 诊断 | 八种受控事件内的类型化快照与候选关联；首次 write 前校验 | RFC §3.1 第5项；A-014–018 |
| S6 一致性 | 同 core 前向/回放和原消费者对拍；指标分母分开 | RFC §3.1 第6项；A-019–022 |

增量优先级：仅本契约的 phase1 域覆盖 07-001 的 symbol-only EWMA/旧 replay 费用和 07-004 的 controlled entry 费用、observed_at 误标及缺诊断部分。07-004 的现金/预占/净库存/损失锁存/期限/官方结果/无钱包/秘密隔离均继续生效，07-001 的原协议、proxy/history 不隐式变更。旧文档/结果只读，不回写历史授权。

### 2.2 Out of Scope

不做校准、动量、OBI、LLM、参数搜索、新 WS/Chainlink/oracle 服务、maker/Kelly/杠杆、第二 Broker/账本/回测平台、DB/schema、签名/钱包/API 认证改造、依赖升级、cron/systemd/gateway/其他 profile 修改；不改默认 config.json、100/2/2/10/20 USDT 或默认普通策略；禁止外部发布及 git add/commit/push。禁止任何新真实网络行情驱动 paper/实盘、生产凭据/keyring/私钥读取、长回测。只允许后续按 Design 运行纯离线 fixture。旧49笔缺 fair/真实源时钟，不补造；withdrawn win-rate-analysis.json 不作为结论。

T1 只写本 SPEC 与对应 RFC，不写 Design、业务代码、测试、报告、模板/README/AGENTS/SOUL/CLAUDE。不得执行 execute_code 或其包装；历史被拒入口为 OMITTED_BY_AUTHORIZATION，不是 PASS。新安全拒绝/超时立即 STOP 交主控，不换执行方式绕过；正常文件并发保护按工具要求重读。

### 2.3 真实基线与文件职责

BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`；下表所有 src/、tools/ 均相对 BOT。主仓 main HEAD=f82f45c53ff68fa63464bb5ec67884d5914ec09b；BOT main HEAD=a6b4f543ce09e9e2728d9ac1de1781ed3d7e7501，工作树干净。主仓两项既有 skill dirty 非本卡。

| 当前接缝 | 保留，不新建 | 必要增量职责（非整个文件可任改） |
|---|---|---|
| src/bot/arbitrage.rs | DecisionCore、RoundTaker、正 fill 才 entered | 显式语义、源 epoch、两侧诊断、候选上下文与重验 |
| src/service/spot.rs | 原 REST/fallback、EwmaVol、digital_up | acquisition 时钟/实际 pair；输入验证；纠正预测/结算说明 |
| src/bot/runtime.rs；src/bot/runtime/paper.rs；src/bot/runtime/paper/tests.rs | 唯一 Broker、现金/预占/锁/限价深度/结算去重 | phase1 BUY 必须带上下文、同锁最后重验、关联事件及回归 |
| src/bot/arbitrage/replay/types.rs、driver.rs、tests.rs | 现存显式时钟驱动和本地 result seam | 显式 /2 薄适配，/1 不变；真实消费者对拍 |
| src/bot/arbitrage/history.rs | 纯估值，无盘口/交易输出 | 默认保持 /1，只有共享类型编译所需接缝，不新增执行能力 |
| src/models.rs、src/service/venue.rs | 现有 book/token/官方 round 类型 | 如直接必要，最小 additive 时钟/上下文接缝；不伪称现有字段 |
| tools/predictfun/btc5m_control.py；tools/predictfun/tests/test_btc5m_control.py | 固定入口、递归白名单、首次写入/有界退出 | unsigned v2 解析/强制字段/关联及真实 Rust emitter 消费者 |

这不是 T3 最终 allowlist；T2 必须精确列逐文件新增/修改、类型位置、测试命令及直接必要原因，不授权任意目录。config.rs 仅确有需要的类型兼容，不改默认配置/资金；replay CLI 如需分版选择，T2 必须列出现有 src/bin/btc_arb_replay.rs 的最小接线范围，不能新 runner。其余新增模块需 T2 在同职责内明确路径和 G3 理由，不能实现时自由扩张。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 / 边界 |
|---|---|---|---|
| F-001 | 显式选择策略语义 | unsigned controlled 或 /2 | phase1_net_shares；其他默认 legacy_cash_fee |
| F-002 | 同经济口径入场 | fair、可买价、bps、gross 量 | 净份额 EV/edge；无效输入拒绝，不零填 |
| F-003 | 来源状态隔离 | symbol/source/actual_pair、接收时钟 | 独立 key/epoch/samples；切换/长 gap 不跨接 return |
| F-004 | 时钟和连续性检查 | source 可空、request/receive/elapsed 必填 | RECEIPT_BOUND 或 SOURCE_AND_RECEIPT；clock invalid 不入样本 |
| F-005 | 候选到成交重验 | 冻结市场/输入/数量/限价及新 now | 同 core 重算剩余时间/fair/EV、年龄及深度；过期不成交 |
| F-006 | 结构化诊断/关联 | 每个已选市场每 tick 的决策尝试 | summary.source.decision；candidate→reservation/release/fill/blocked/settlement |
| F-007 | 协议关闭失败 | 严格 v2 schema/有限数/枚举/关联 | 接受后才写 events；错误沿 OUTPUT_INVALID 停新增/收尾 |
| F-008 | 同核心对拍/指标分离 | 离线因果流与确定时钟 | 决策及 Broker 输出同义；方向/胜率/净份额/现金不同指标 |

## 4. 数据与接口契约

本节冻结可观察字段名与业务行为，不声称当前代码已经具备同名 struct；内部 Rust API/参数位置由 T2 决定，不重选本节语义。

### 4.1 单位、费用与选择规则

价格 p 是 USDT/gross share 的可买价，fair 是模型预期每净份额兑付 USDT，不是报价、更不是验证过的真实概率。q 是目标 gross shares；bps 为整数 0..10000，r=bps/10000，h(p)=r×min(p,1-p) 为每 gross share 的费用 USDT 等值。

| 模式 | 数量/现金事实 | 入场 edge（USDT/gross share） |
|---|---|---|
| legacy_cash_fee | gross 库存，fee 单列并从权益扣；原消费者不改 | fair-p-h(p) |
| phase1_net_shares | cost=q×p；fee=q×h(p)；fee_shares=fee/p；net=q-fee_shares；B 只扣 cost | fair×(1-h(p)/p)-p |

phase1 总预期净收益 EV=net×fair-cost=q×edge；附带 ROI=EV/cost，仅诊断，不作为门槛。保本 fair=p/(1-h(p)/p)，净到账比率为0时保本值为 null 并拒绝 NET_SHARES_INVALID，不允许无兑付份额入场。不得改成 EV/net、ROI 或把净份额再扣等值现金。BUY/SELL/结算成本分摊与 R/U/NAV 仍沿 07-004 §4.3–4.6。

1. 固定 min_edge=0.03、order_usd=2、min_secs_left=30、vol_floor=0.00005、half_life=300、min_vol_samples=20、poll_secs=5，100/2/2/10/20 不变；不加用户可调新阈值。phase1 选择由固定 unsigned controlled 装配或 /2 显式版本决定，缺 opt-in 的旧调用保持 legacy。signed 分支不获新能力。
2. Up fair=p_up，价格=Yes best ask；Down fair=1-p_up，价格=既有 BookSnapshot::mirrored() 的 No best ask。镜像沿既有1e-9舍入，不另造两本独立流动性。两侧合法且 edge>=min_edge 才候选；edge 最大者，精确相等沿旧迭代顺序选择 Down。另一侧不因未选中被当作成交。
3. q 沿原 shares_for(order_usd,limit) 向下取整，最坏 q×limit 仍须满足原最低1 USDT、单笔/市场/总量/现金。初选按 touch/limit 算 edge；原全额 walk 的实际 VWAP 再算 net/fee/EV，并在应用前仍要求 edge>=0.03。不提高限价、不向上取整、不自动改另一侧或缩单凑成功；深度不足全拒绝，不伪部分成交。
4. spot/strike/sigma 必须有限且正，0<p<1，q>0；fair/p_up∈[0,1]；bps 不得由缺值默认成0；所用 book level 的价格/size 有限、价格在(0,1)、size>0、按既有买入排序；双边 touch 不交叉。非法项不进模型/账务。未知市场规则沿 MarketRulesUnknown，零费是明确 bps=0，非缺值。
5. 原 driftless lognormal、A&S normal_cdf/EWMA 公式不拟合、不替换。时间用精确毫秒差/1000，不使用 num_seconds 截断来通过30秒边界。DRAW 官方兑付0.5；当前模型 fair 是既有连续模型假设下的预期兑付，不假造独立 DRAW 概率。

### 4.2 来源 key、fallback 与波动状态

- key=(symbol,prediction_source,actual_pair)。本范围 symbol=BTCUSDT；Binance 对应 actual_pair=BTCUSDT，Coinbase 对应 BTC-USD；币种基差不可抹去。settlement_provider 只来自官方 round_facts，允许 CHAINLINK/UNKNOWN，未知不填 Binance；它不进入预测源 key，更不以该字符串替代官方结果验证。
- 保持原 Binance 优先、失败后 Coinbase、300秒后再试 Binance 的获取政策；原请求超时5秒不放宽。非法数值响应也视为源获取失败，不把 NaN/0 喂 EWMA。Coinbase 仅是 unsigned 独立降级 paper 输入，标 DEGRADED；Binance 标 PRIMARY；两者均非官方 Chainlink 流。同源恢复不取消 loss latch，不释放持仓/预占。双方失败沿原 tick/data failure 处理，保留账务且不新增，不造报价或零波动。
- 每个 symbol 只有一个活跃 epoch。epoch 从1开始、每次 reset 递增；首次 FIRST_SAMPLE，每次 key 变化 SOURCE_SWITCH（即使刚用过该 key 也不能恢复暖历史）；同 key 距上个有效 receive 的保守 elapsed gap>300秒时 LONG_GAP；gap=300秒不 reset。依据是沿用300秒 half-life：超过一个半衰期无观测，不再把之前估计视为连续有效；不是证明最优阈值。600秒仅旧探针，不是新配置。
- reset 清除该活跃估计的 last price/variance/samples，当前有效新价仅作为首价，samples=0；后续同 epoch 严格递增的有效接收时钟形成 return，20 returns 才可估值。floor 只能约束已暖 sigma，不能替代预热。换轮不清 vol，换源/gap 不清 entered/已有持仓/结算去重。
- 本范围 EWMA dt 使用有效 receive 的经过时间，不用源时间或请求前 now；source_at 仅作真实性/年龄校验。无效价格不更新状态；无效时钟（§4.3）清空活跃 vol、epoch 增加、reset_reason=CLOCK_INVALID，丢弃该观测，下一有效价为新首价。相同接收时刻的重复样本不生 return；回放相同 event_id/相同内容沿原去重，不重复触发 reset，ID同而内容冲突拒绝流。
- PRIMARY↔DEGRADED 后须完成本源本 epoch 预热才恢复候选；不设额外恢复计数、回切滞回或新服务。保留原 signed Binance guard，不将“Binance 标签”修辞升级为已证明同结算源；本契约不授权 signed 交易。

### 4.3 时钟可用性、年龄与阈值

clock 对象的全部键必填，可空仅 source_at。UTC 用 RFC3339 带 Z/offset、至少毫秒精度；elapsed_ms 是本次进程起点的非负整数经过毫秒，使用包含暂停时间的时钟（沿已有 BOOTTIME 能力），回放用显式同义时钟，不能用重启后原点混接。

| clock 字段 | 类型 | 含义 / 约束 |
|---|---|---|
| source_at | timestamp/null | 真实源事件时刻；当前 spot REST 和 BookSnapshot 无可核此值，必须 null |
| source_time_status | enum | MISSING 或 PRESENT；与 null/非null一一对应 |
| freshness_basis | enum | RECEIPT_BOUND 或 SOURCE_AND_RECEIPT；不能把前者称源时间已验证 |
| request_at | timestamp | 本次实际请求发出前；fallback 是该成功源自己的请求开始，不含前一失败源等待 |
| received_at | timestamp | 完整响应解码且校验完成；缓存返回不能更新此值 |
| request_elapsed_ms | integer | 请求开始的经过时钟 |
| received_elapsed_ms | integer | 成功接收的经过时钟 |

decision_at / decision_elapsed_ms 是调用 core 前的真实决策时钟；submit_at/submit_elapsed_ms 是 Broker 提交前时钟；apply_at/apply_elapsed_ms 是同锁内、实际记账前最后时钟。不复用 decision now 冒充 observed_at。旧 observed_at 在 v2 移除，v1 只读字段不得翻译成真实源时钟。

对 spot 与 book 分别检查：request≤received≤当前 UTC，elapsed 同序；当前时钟不得早于本次 candidate 的 UTC/elapsed；source 存在时 source≤received，且同 key 的 source 时刻不得倒退/重复（有交易序列且同毫秒的未来扩展不在本期）。负时刻、未来接收/源时间、倒序/重复观测、elapsed 倒退均 CLOCK_INVALID，不 clamp 成0；未取得输入则 MISSING_INPUT，所有 clock 为 null，不构造假 clock。当前 REST source=null 合法，不因此禁用路径。

保守 request_span=max(received_at-request_at,received_elapsed-request_elapsed)，保守 acquisition_age=max(nowUTC-request_at,nowElapsed-request_elapsed)；两项都不能为负。request_span≤P=5秒，acquisition_age≤2P=10秒，含等号；source 存在还须 nowUTC-source_at≤10秒。用 request 开始作 acquisition 下界比仅接收 age 更保守；同时存 receive age 供解释，不能以刚解码掩盖请求等待。P 来自原5秒轮询/请求超时，2P 表示允许一个额外轮询周期，非实测 alpha 寿命或用户参数。无源时间仅证明本地获取边界，无法证明缓存/代理上游真实 freshness。

- 时钟倒拨不能延长有效期。重验使用有效 now=max(当前UTC,candidate.decision_at+(当前elapsed-candidate.elapsed))，既按当前 wall 也按连续经过时间守住 ends_at；检测倒拨仍 CLOCK_INVALID，不靠 max 修复为合法候选。向前跳时按更早失效处理，不增加校时服务或容忍未来时间阈值。
- round identity/strike 的可用时间必须≤decision_at；start_price 只能来自原官方市场事实，不在每轮把 spot 重设成 strike。starts_at≤now，ends_at-starts_at=300秒，ends_at-now≥30秒（精确差、含等号），open 且非 contested；缺或冲突沿 MARKET_INVALID 拒绝。不把事后 end_price/outcome 注入估值。
- 持仓 mark 继续沿原同 tick 有效性/data block，不以新的候选年龄检查取消旧持仓保护。spot 失败不伪造新价，book 失败不刷新旧 mark。官方待定结算不受预测输入 freshness 通过与否替代，仍按官方身份/结果验证。

### 4.4 候选提交与应用前的不可绕过条件

每个被原筛选选中的市场每 tick 都产生一个 evaluation attempt（含 WARMUP/已入场/缺数据），先记录 §4.5 的 EVALUATE 快照。未被选中的其他市场不新增扫描诊断。只有 EVALUATE=ELIGIBLE 才生成 candidate_id；没有信号不用创建假候选。

1. candidate 冻结 market/token/starts_at/ends_at/strike、source key/epoch、spot/book 输入及 clock、bps、q/limit、decision_at 和两侧估值。每次 submit 再取新时钟，以同一输入重算 secs_left/p_up/fair/edge，不沿用候选 fair。PRE_SUBMIT 快照必须先于 reservation/fill。输入被刷新或 source/epoch/身份/费用变化则旧候选 INPUT_CHANGED 终结，若再考虑交易须新 attempt/candidate，不借旧 id 改内容。
2. 原 Broker 的 phase1 BUY 缺上下文直接 DataIncomplete/CONTEXT_MISSING，禁止从旧公开 take 接缝绕过；普通 non-phase1 调用无该新要求。T2 决定传类型化参数还是受限方法，不新增第二 Broker，也不让可变 token→last-source 全局表替代一次性候选上下文。
3. Broker 复用原风险/mark/限价/全额深度校验。同锁在 reservation 之后、apply_buy/库存变更之前再次取 clock，写 PRE_APPLY 快照并重验新 fair/EV、spot/book年龄、轮次剩余≥30秒、run deadline/停止/损失锁存；任何 await/排队/阻塞后都不能用之前 now 放行。run deadline 等号优先停新增。若此时失败，释放本笔未应用 reservation 一次、blocked，无现金/成本/库存/entered变化。
4. 实际 VWAP 上的费用/净份额/EV 按 §4.1 复算；不能在别处保存另一套费公式。正 net fill 才 confirm_fill，零 fill/blocked 不算 entered。同轮最多一次仍沿原 core；结算不解除 entered。应用前不自动读网络新 book；是“当前时间复核被冻结输入”，过旧即拒绝，非伪称实时再取价。
5. 新计算/证据无效时 fail closed，不部分写账、事后改输出或用自由日志代替诊断；原 Broker 同锁、现金、损失、deadline、官方结算去重保持优先。并发/生命周期错误沿旧保护，不借诊断再开资金账。

### 4.5 v2 事件与字段级诊断

unsigned phase1 的 started/ended 标 schema_version=btc5m-controlled-paper.v2，增加 strategy_contract=phase1_net_shares；公共配置内容/资金不改，公开 SHA 继续记录。Rust 每行前缀仍 BTC5M_EVENT ，八种 kind 仍 fill/settlement/loss_latch/summary/final/reservation/release/blocked。v2 event envelope 在旧七字段外仅增加 schema_version（固定 v2）和 event_seq（从1严格递增整数）。旧七字段 run_id/event_kind/market_id/token/accounting/source/event_time 不改基本类型；event_time 是发出记录时刻，不是报价时刻。

v2 summary 分两类：旧总账 summary 的 market_id/token/source 仍 null；诊断 summary 的 market_id 必填、token=null、source 恰为 {decision:对象}。诊断不改账务，accounting 为当时真实快照，缺有效 mark 的 U/NAV/net_pnl 一起 null，不能造0。普通 fill 等不允许塞 decision 自由对象。

以下表每行单字段；对象中所有列出的键必须存在。未取得/不可计算字段按所列 null 规则，不省键、不填0、不写 NaN/Infinity。所有新增数据为 L0 公共行情或 L1 工程关联；无 L2/L3。对象/数组只有这些字段，任意 unknown key 递归拒绝。

| decision 字段 | 类型 / 可空 | 含义 |
|---|---|---|
| decision_id | decimal-string | run 内从1递增的 attempt，使用旧id型的1..78位十进制字符 |
| candidate_id | decimal-string/null | 首次 ELIGIBLE 时等于 decision_id；未候选为 null，后续重验保持不变 |
| phase | enum | EVALUATE / PRE_SUBMIT / PRE_APPLY |
| strategy_contract | enum | 固定 phase1_net_shares |
| reason | enum | §4.6 稳定诊断原因，成功为 ELIGIBLE |
| symbol | enum | BTCUSDT |
| prediction_source | enum/null | Binance / Coinbase；尚未取得报价为 null |
| actual_pair | enum/null | BTCUSDT / BTC-USD；与 source 对应或共同 null |
| source_state | enum | PRIMARY / DEGRADED / UNAVAILABLE |
| source_epoch | integer/null | 当前 epoch；从未有输入为 null |
| reset_reason | enum | NONE / FIRST_SAMPLE / SOURCE_SWITCH / LONG_GAP / CLOCK_INVALID；该 epoch 创建原因，直到下一epoch保持 |
| settlement_provider | enum | 官方 CHAINLINK / UNKNOWN；不得从预测源派生 |
| starts_at | timestamp/null | 官方开轮；缺为 null |
| ends_at | timestamp/null | 官方结束；缺为 null |
| identity_available_at | timestamp/null | 本地获得该官方身份的接收时刻，不能事后重写 |
| strike_available_at | timestamp/null | 本地首次获得该官方固定strike的接收时刻；不是猜测官方发布时间 |
| strike | number/null | 官方固定起价；缺或非法为 null |
| spot | number/null | 有效预测输入；缺/非法为 null |
| spot_clock | clock/null | §4.3；未取得输入为 null |
| book_clock | clock/null | §4.3；未取得输入为 null |
| decision_at | timestamp | 初次评估时刻，重验不改 |
| decision_elapsed_ms | integer | 同上经过时钟 |
| checked_at | timestamp | 当前 phase 的真实检查时刻 |
| checked_elapsed_ms | integer | 当前 phase 的经过时钟 |
| secs_left | number/null | ends_at-effective_now，单位秒；缺 ends 为 null；允许负数用于到期拒绝 |
| samples | integer | 当前 epoch return 数，未初始化为0 |
| sigma | number/null | 仅已暖且数值合法时给有效sigma；冷启动为 null |
| p_up | number/null | 仅输入/时间/预热允许估值才有；拒绝不消灭此前已合法算出的值 |
| best_yes_bid | number/null | 当前被验证 book touch；缺/非法 null |
| best_yes_ask | number/null | 同上 |
| fee_rate_bps | integer/null | 官方有效整数；未知为 null，明确0合法 |
| selected_token | id/null | 初次被选token；无候选null；重验失败仍保留原token |
| up | side-diagnostic | Up侧，字段见下表 |
| down | side-diagnostic | Down侧，字段见下表 |

| side-diagnostic 字段 | 类型 / 可空 | 含义 |
|---|---|---|
| token | id | 官方 outcome token，非法市场无法取得时此整个 side 对象为 null |
| fair | number/null | p_up 或1-p_up，缺估值null |
| limit_price | number/null | 本侧可买touch，镜像用原规则；缺/非法null |
| gross_shares | number/null | 按原 shares_for 向下取整目标量，缺合法价格null |
| fee_per_gross_share | number/null | h(limit)，缺价格/bps null |
| net_shares | number/null | 候选q在limit扣费后份额 |
| cost | number/null | q×limit，不含第二次现金费用 |
| ev | number/null | net×fair-cost |
| edge | number/null | ev/q，阈值分母为gross |
| roi | number/null | ev/cost，非门控 |
| breakeven_fair | number/null | §4.1；净比率0时null |
| qualifies | bool/null | 数学edge是否达标；缺任一前提null；不代表Broker已放行 |
| depth_levels | array/null | 满足q所需的最短可买前缀，或耗尽时全部限价内level；每项仅 {price:number,size:number}；未有合法book/q则null |
| depth_complete | bool/null | 前缀能否覆盖整个q；不能用截断冒充不足；缺前提null |
| walk_vwap | number/null | 原全额walk结果；不足为null |
| execution_net_shares | number/null | q按walk_vwap扣费后份额；无walk null |
| execution_cost | number/null | q×walk_vwap |
| execution_ev | number/null | execution_net_shares×fair-execution_cost |
| execution_edge | number/null | execution_ev/q |

levels 必须是原输入的可验证前缀，不按成本过滤或重排以提高EV；同价level沿原顺序，末档保存原size（非裁成已吃数量）。这足以复算本次目标量，不要求保存远端整本无关深度。单数组仍≤1000项，整行仍≤64KiB；必要前缀无法在原界限内完整保存则拒绝本次 DIAGNOSTIC_LIMIT，不成交，不提高上限或写第二原始日志。其拒绝快照仅保留可在界限内的标量与 depth_levels=null/depth_complete=null，reason 明示，不能自称可复算原完整walk。

关联字段（除已列外不加任意详情）：v2 reservation/release/BUY fill/blocked 的 source 增加 decision_id、candidate_id、diagnostic_reason；candidate非null，source 原字段/单位仍按旧kind必填。新 freshness/context/EV重验拒绝的 source.reason 用既有 DataIncomplete，diagnostic_reason 给确切 §4.6 原因；旧Broker拒绝保留原 reason，diagnostic_reason=BROKER_BLOCKED。BUY fill 的 diagnostic_reason=ELIGIBLE，原 price_source 改为 {name:Binance|Coinbase,clock:§4.3}，不再有 observed_at。SELL 只回归共享账务，不新增策略卖出；不强造卖出candidate。settlement.source 增加 candidate_id（指该token本run唯一正BUY fill），其他 shares/payout/income/basis/provider/units不变。final原字段/已交易市场净份额/结果状态不变，不嵌套整份诊断。

顺序/幂等要求：同run event_seq无重复/倒序；每decision_id先有且仅有一个EVALUATE；candidate非null只允许该id初次ELIGIBLE。PRE_SUBMIT在reservation之前，PRE_APPLY在fill之前；fill必须匹配同market/token/candidate、q、价格限价、source key/epoch，最后重验ELIGIBLE。每candidate至多一个 terminal BUY fill或blocked；release只释放未应用reservation，非terminal。settlement必须引用此前成功BUY，同token最多一次实际兑付；输入改变终结旧candidate。launcher仅保存必要关联索引（非第二资金账本），逐行校验再写；final时有未终结候选/预占则标运行不完整，不能判completed。因中断缺后文时保留真实已写事件，不补造terminal。

### 4.6 拒绝原因、缺值与检查顺序

reason 是固定 enum，不允许 raw错误、URL、环境、secret或任意detail。按以下顺序确定主reason，较早失败优先；已安全算出的其他诊断可保留，不继续用无效输入计算。无数值不等于数值0。

| 优先级 / 原因 | 判据 | 结果 / 直接必要理由 |
|---|---|---|
| 1 RUN_STOPPED | run deadline/父停止/已halt或loss latch | 停新增；旧生命周期优先 |
| 2 ALREADY_ENTERED | 原core已正成交 | 不重复买；保留原单轮保护 |
| 3 MARKET_INVALID | 身份/时段/strike可用性/官方规则缺失或冲突 | 不猜市场事实 |
| 4 MISSING_INPUT | spot/book或其必要本地clock缺失 | 不把决策now当获取时间 |
| 5 INPUT_INVALID | 非有限/非法价格、bps、level或模型值 | 不污染模型/现金 |
| 6 CLOCK_INVALID | §4.3未来/倒序/重复/倒拨/elapsed错误 | 本观测不计return，vol新epoch |
| 7 REQUEST_TOO_SLOW | 任一request_span>5秒 | 慢请求不能伪fresh |
| 8 SPOT_STALE | spot保守age或真实source age>10秒 | 决策输入有效性 |
| 9 BOOK_STALE | book对应age>10秒 | 交易输入有效性 |
| 10 ROUND_TOO_LATE | 实际剩余<30秒（含已到期） | 防延迟越界；30秒等号合法 |
| 11 INPUT_CHANGED | 候选后market/strike/key/epoch/fee/book/spot变化 | 旧候选不可换内容复用 |
| 12 WARMUP | 当前epoch samples<20 | 不用floor绕过预热 |
| 13 NET_SHARES_INVALID | 净到账比率≤0或非法 | 没可兑付份额不得买 |
| 14 EDGE_BELOW_MIN | 两侧无edge>=0.03，或已选侧重验edge/VWAP edge不足 | 对齐实际费用EV |
| 15 DIAGNOSTIC_LIMIT | 必要诊断无法在原64KiB/数组界内完整输出 | 不能一边成交一边丢关键证据 |
| 16 BROKER_BLOCKED | 原最低金额/资金/市场/总量/mark/深度等拒绝 | 原source.reason细分，ThinBook不得当零成交成功 |
| CONTEXT_MISSING | phase1 BUY未携候选上下文（Broker入口先验） | 调用即拒绝，无预占/成交 |
| ELIGIBLE | 当前phase全部适用前提通过 | 仅表示该检查通过，仍非最终成交 |

EVALUATE 可先算数学candidate，深度/资金仍由Broker裁定；候选深度不足也必须先留快照再ThinBook拒绝，不得记fill。Clock_invalid 重置只针对spot序列时钟损坏；仅book/当前检查时钟损坏不把未损坏的spot误计新return，当前候选拒绝，发生进程时钟倒拨时活跃spot epoch同样失效。未选市场不强制输出拒绝记录。

### 4.7 协议版本、首次写入与普通兼容

- unsigned新run固定v2；signed-future-live继续既有v1/final-only/真实账务不可用语义，不借v2改变认证/签名/费用/运行权限。v1文件只读解析按旧语义展示，明确 DIAGNOSTICS_UNAVAILABLE，不迁移/补字段/混合统计，不把旧 observed_at 当源时钟。live Binance guard保留，不因注释纠正解除限制。
- launcher按mode/started绑定schema；unsigned收到v1/未知版本、错run、重复键、非有限数、bool冒数、缺键/非法null、unknown枚举、递归unknown字段、坏关联或公式矛盾，沿既有OUTPUT_INVALID退出/停止/回收与结束不完整流程，绝不把坏行先写events.jsonl再清洗，也不把协议事件当discarded普通日志吞掉。原非协议输出丢弃/秘密哨兵防线保持，RUST_LOG不放开为debug。
- Rust emitter与Python validate_event必须一起升级，以真实 emitter→原 supervise/run→首次证据write的消费者证明，不只测拼装JSON。保持原64KiB行界与秘密字段大小写/嵌套拒绝；新symbol/enum/id不接受自由字符串。schema或类型坏行仍OUTPUT_INVALID，正常策略拒绝则是合法summary/blocked，不混成协议故障。
- 诊断数值按07-004计算对拍 abs≤1e-9 或 rel≤1e-9；协议原账务equal的既有1e-7传输恒等式校验保留，不放宽为交易门槛epsilon；新公式校验按同1e-7传输界限，独立数值对拍仍1e-9。身份、分类、计数、阈值接受/拒绝零容差；edge恰好0.03可、稍小不因容差放行。
- 默认普通paper/gross、其他策略/venue、signed/live、replay/1、proxy、history/1原参数/输出/行为保持；允许最小additive公共类型接缝，不让旧调用必须伪造时钟，也不自动启用phase1。

### 4.8 同核心前向/回放及指标口径

显式 btc-arb-replay/2 选择phase1_net_shares和固定order_usd=2，其余min_edge/min_secs_left/floor/half-life/samples沿§4.1。原/1继续order_usd=5及legacy；不改既有proxy默认，不让history/1生成book/订单。/2仍用原replay入口与驱动，不新增二进制/通用回测服务。

/2 envelope保留原event_id/event_at_ms可空/available_at_ms/seq/source/evidence_type/payload，schema_version改/2，并增加必填非负整数elapsed_ms，表示该行消费时的进程经过时钟，逐行不倒退。对spot/book payload在原字段外增加clock（§4.3）及spot.actual_pair；spot.model_source限定Binance/Coinbase，actual_pair与之匹配。market/state固定身份/strike/fee的本地可用时点取对应首次有效envelope.available_at_ms，沿原因果规则保存。source事件time可空不等于available时间可空，available_at_ms≤消费时点；真实未可得数据不可预用。对spot/book，available_at_ms等于clock.received_at的UTC毫秒，elapsed_ms等于received_elapsed_ms；event_at_ms与clock.source_at同为null或精确等值，不用它覆盖received。所有新增键递归拒绝未知，/1不接受/2键。

/2输出原字段保留，并增加decision（与§4.5同义，UTC由毫秒显式转换）及strategy_contract；tick行的decision为EVALUATE快照，非tick行为null。candidate_event_id沿原字段名引用该EVALUATE所生成的十进制candidate_id，不猜测为其他event_id；positive filled_shares明确为net shares才confirm，零/blocked不entered。未知、重复、身份错误结果沿原fail closed。result/label不得进入p_up/EWMA；label仅事后评价，公开结果待定不补造。回放driver本身仍不算第二份资金账：决策对拍用同core，执行对拍将同candidate交给现存Broker的隔离fixture，把它实际产生的result再交原driver。PRE_SUBMIT/PRE_APPLY由该原Broker消费者调用共享重验并发出v2事件，延迟由测试fixture的同一显式clock推进，不为此给replay新增订单/延迟事件种类。对拍时只允许run_id等测试装配身份的声明映射，数值/理由/选择/状态不能归一化掉差异。

| 指标 | 明确分子/分母或单位 | 缺失/限制 |
|---|---|---|
| 方向命中 | 每个EVALUATE已估值p_up>0.5判UP、<0.5判DOWN；正确数/有方向且官方非DRAW样本 | p=0.5 abstain、DRAW、pending/缺估值分别计数，不进该分母；这是attempt级非独立轮次统计 |
| 入场方向胜率 | 正BUY且官方非DRAW的胜笔数/此类已结算笔数 | DRAW/pending单列；不是全部候选方向命中、不是现金盈利率 |
| 净份额 | 逐笔gross、fee_shares、net，按token汇总 | 不把不同token份额加总称财富，不把gross计兑付 |
| 现金收益 | 每笔net×官方payout-cost；总R、U、B、NAV沿原账务 | pending的最终收益N/A；U是mark估值非最终现金，不重复扣fee |
| 现金盈利率（如展示） | 已最终结算净PnL>0笔数/全部最终结算笔数，零收益单列 | DRAW也可能净盈利，不与方向胜率混名 |
| 分层与覆盖 | 按预测source/epoch分层，保留attempt、候选、阻断、fill、结算计数 | 不按quote价格当概率，不插值缺fair，不年化/做显著性承诺 |

只需能从这些事件离线复算，不新建统计平台/研究全窗/基准拟合。只有/1、history或旧v1证据时，无完整clock/book/fair就明确EXECUTION_NOT_REPLAYABLE/DIAGNOSTICS_UNAVAILABLE；净PnL若有真实账务可复算，但不得反推缺失fair、候选/拒绝数。旧49笔原更正/验收不重判。

## 4.bis 持久化契约

无生产数据库、schema/索引/TTL迁移，无第二账本/自动恢复。以下新增字段均受§4.5严格模式约束；每个字段的类型/可空/来源已逐字段定义，未列字段沿07-004。统一保留策略：exclusive-create新run、事件追加；保留无自动TTL/删除/覆盖/迁移/上传/备份；data被Git忽略不等于已远程保存。中断保留原字节，不从日志resume或重建100本金。

| 存储对象 | 单字段/规则 | 类型/必填 | 默认/派生 | 生命周期/隐私 |
|---|---|---|---|---|
| 原started.json | schema_version | string/是 | unsigned v2、signed v1，按mode绑定 | 新run创建；L1 |
| 原started.json | strategy_contract | enum/unsigned是 | phase1_net_shares | 同上；L1 |
| 原events.jsonl | schema_version | string/v2是 | 与started一致 | 追加保留；L1 |
| 原events.jsonl | event_seq | integer/v2是 | 从1递增，无重复倒序 | 同上；L1 |
| 原events.jsonl | source.decision | object/诊断summary是 | §4.5逐字段，仅summary允许 | 同上；字段L0/L1 |
| 原events.jsonl | source.decision_id | id/候选执行事件是 | 对应先前EVALUATE | 同上；L1 |
| 原events.jsonl | source.candidate_id | id/候选执行及settlement是 | 对应唯一候选/已正BUY | 同上；L1 |
| 原events.jsonl | source.diagnostic_reason | enum/候选执行事件是 | §4.6或原Broker拒绝映射 | 同上；L1 |
| 原events.jsonl | source.price_source.clock | clock/BUY fill是 | 原输入clock，不重置成now | 同上；L0/L1 |
| 原ended.json | schema_version | string/是 | 与started一致 | 独立结束记录；L1 |
| 原ended.json | strategy_contract | enum/unsigned是 | phase1_net_shares | 同上；L1 |
| 原ended.json | final/exit事实 | 原结构/是 | 仍记native child/launcher/强制清理/不完整/pending | 同上；L1 |
| Broker内存 | 候选关联/时钟/epoch | 类型化/适用时是 | 随原State，不复制B/K/R账 | 进程结束失效；不resume；L1 |

运行证据仍在主控另行批准的新 data/reports/YYYY-MM-DD-btc5m-controlled-paper/evidence/<run_id>/，原public-config.json/started/events/ended命名及秘密隔离顺序保留；本卡不创建新run。后续工程独立验收仅 data/reports/2026-11-16-btc5m-phase1-correctness/validation.md及evidence/，不建data/tasks/、手工状态表或全文handoff镜像。

## 5. 验收标准

以下为待实现/待独立Validate的可执行矩阵，非本卡业务PASS。输入全为synthetic、fake clock/transport或既有离线fixture；真实网络、生产凭据/签名调用计数必须0。反例必须经真实消费者，不仅比较复制公式。

| 编号 | 接受输入 / 正例 | 拒绝 / 反例与必须结果 | 验证路径 |
|---|---|---|---|
| A-001 | p=.4、fair=.4381、bps200、足够深度/预热 | 旧cash edge通过但phase1净edge不足.03，0fill/0entered；数值来源为诊断报告的Decimal反例，不当本卡新计算 | 同core→RoundTaker→Broker；镜像No同例 |
| A-002 | fair取(.03+p)/(1-h(p)/p)，edge恰阈值的可精确表示fixture | edge稍低严格拒绝，不用近似epsilon放行；ROI不替代edge；两个side比最大值、精确同值选Down | core/真实选择消费者；数值边界由实际f64可表示邻值构造 |
| A-003 | bps0明确、p<.5和>.5各例；原q下取整、walk优价 | 缺bps/负数/bool/非有限/p0或1/net比率0拒绝；不默认零费、不提高q/limit | DecisionCore+原Broker cash/净份额；保留07-004费用向量 |
| A-004 | 固定unsigned自动phase1，显式/2 | 普通paper/旧replay/1/其他策略仍legacy；signed不启phase1；缺上下文的phase1 take拒绝且钱不变 | 真实装配及共享调用者回归 |
| A-005 | Binance连续，故障→Coinbase，原300秒后回试成功 | key/actual_pair/provider分开，切回不借暖状态，Coinbase单列DEGRADED；无真实Chainlink时钟伪装 | fake获取→core→诊断；signed旧guard回归 |
| A-006 | 官方CHAINLINK、UNKNOWN真实未知；pending后合法官方结果 | 本地spot涨跌/不同market/token/争议/冲突不结算；重复官方结果只一次兑付，candidate关联到原正fill | 原settlement Broker+真实事件filter |
| A-007 | 同key gap=300秒不断；gap>300重置 | 旧600秒探针也重置但不新增600配置；reset当前价samples0，预热19return拒绝、20可 | core状态+前向/replay同输入 |
| A-008 | 同源21个有效价格形成20returns | 首价/相同时间重复不能作return，floor不免预热；换源无论短gap均新epoch；换轮不清vol | 原EWMA消费者，不单测自制计数器 |
| A-009 | 合法receive递增，source可空 | spot时钟未来/倒序/重复/elapsed回退→CLOCK_INVALID、新epoch；坏价格不入样本；旧event_id去重不双reset | 获取/事件适配→core |
| A-010 | request_span=5秒、acquisition_age=10秒边界；当前REST source=null | 任一稍超分别REQUEST_TOO_SLOW/STALE；source未来或age超界拒绝；不能改received到now续鲜 | fake request/receive→真实决策/提交 |
| A-011 | candidate剩余≥30；submit/apply都恰30可继续门控 | 候选时足够但submit或reservation后到29.999秒拒绝、释放一次，现金/库存/entered不变；run deadline同时到优先拒绝 | RoundTaker→同锁Broker的两次fake时钟推进 |
| A-012 | 输入未变，新时钟重算fair/EV，VWAP合法 | source/epoch/book/fee/strike改变旧candidate终结；时间流逝导致edge不足拒绝，不能沿用旧fair；倒拨/暂停不能延长 | 原take应用前及emitter |
| A-013 | 两侧合法、限价内足额深度 | 限价外够量不算、薄盘全拒绝、陈旧book/缺同tick mark拒绝；Down深度必须真实镜像不双算 | 原token_book/walk/Broker，而非另写撮合 |
| A-014 | WARMUP/EDGE_BELOW_MIN/ELIGIBLE/原Broker资金拒绝均有快照 | 模型缺值null+reason，不造0；含p_up/fair/sigma/strike/time/clock/bps/两侧深度，拒绝也保留安全可算值 | Rust emitter→Python validate_event→首次write spy |
| A-015 | EVALUATE→PRE_SUBMIT→reservation→PRE_APPLY→BUYfill→settlement同id | 未知candidate、错run/market/token/source epoch、重复terminal/settlement、seq倒序、final遗留未完成不得伪完成 | 真实launcher逐行状态及原账务去重 |
| A-016 | v2按mode/started匹配；v1只读展示 | unsigned接v1/未知版、漏键、错误null/枚举、bool冒数、重复键、unknown递归字段/坏公式→OUTPUT_INVALID；坏行首次写入0 | 原supervise/run与write spy；保留v1/signed回归 |
| A-017 | 最短完整depth前缀可复算VWAP/净EV且在原界限内 | 需要超1000/64KiB不能截断伪完整或成交；DIAGNOSTIC_LIMIT标量拒绝；原秘密名大小写/嵌套及哨兵不落盘 | emitter/launcher真实边界fixture |
| A-018 | 正常拒绝是合法summary/blocked、账务保持不变 | 夹raw错误/URL/API/JWT/signature/环境/代理哨兵的stdout/stderr/协议行在首次write前拒绝或既有过滤；不增自由日志 | 真实run fake child+真实Rust输出消费者 |
| A-019 | 同连续spot/clock/book/market及same submit/apply推进，前向与/2同core | 比较samples/sigma/p_up/两侧fee/edge/选择/理由/id；source切换/gap/延迟/薄盘均一致；不能两个公式互测冒充同core | 原RoundTaker薄适配 vs 原replay driver |
| A-020 | 同candidate交同现存Broker fixture，结果反馈replay | 逐事件cash/reserved/cost/realized/net shares/fee/entered/官方结算全等；零/blocked不entered，不能回放复制账本 | DecisionCore→Broker→emitter→launcher→result adapter |
| A-021 | 非DRAW方向样本、abstain、DRAW/pending，异价异份额BUY | 分开方向分母/成交胜率/净份额/现金；无fair不反推，缺book/clock不声称执行可回放；旧49笔不补造不重判 | 从v2实际fixture事件复算并与原账户逐事件对拍 |
| A-022 | 默认旧/1、proxy、history/1、普通paper、其他venue/策略继续原输出 | 共享类型编译回归真实通过；无新网络/签名/配置/依赖/调度/发布；A001–019及B001–006受影响旧断言不删不skip弱化 | 受影响完整模块/launcher回归与scope diff |

## 6. 测试要求与本阶段验证范围

- T2必须基于实际源码冻结最小路径/命令和G3边界，不能只用编译或纯函数测试代替上述RoundTaker→Broker→emitter→launcher首次write及/2对拍。Rust测试沿既有cargo --locked --offline入口；Python沿tools/predictfun/tests/test_btc5m_control.py项目现有测试入口。具体筛选/工作目录/fixture隔离由T2在实存测试上确认，不杜撰测试名/计数。
- fake transport/keyring/auth/trader/真实network均设置调用即失败；测试fake child/clock可沿已有机制，临时文件仅当前profile scratch/TMPDIR。--offline不等于禁业务socket，仍须逐入口审查。禁止运行真实固定bot、ignored联网测试、旧6h/94日研究或安装/升级依赖。
- 共享模块变更保留原模型向量、普通paper gross、受控现金/净份额/同锁/亏损/deadline/官方去重回归；无需重做已签收SDK/签名工程，但如碰直接公共调用者必须定向证明兼容。developer自测不是独立Validate。
- 独立Validate记录最终候选HEAD+变动文件SHA、真实命令及native exit、A-001–022逐项证据/未运行项；不得用历史失败/旧PASS覆盖新候选。收益/成交数量不是验收门槛，不加coverage%/性能/真实运行门禁。
- T1只静态核对两文件、引用、来源、scope、单义边界与反例矩阵；git path-filtered diff及新文件no-index whitespace检查、独立sha256sum。数值例引用既有诊断向量，不声称本卡已运行公式测试。没有执行本节业务测试，不判实现PASS。

## 7. 实现约束与风险

T2沿现行G3按实际行数决定最小增量，不自动大拆：RFC §10.2记录runtime.rs2354、paper.rs1458、paper/tests.rs1321、predict_fun.rs2398、config.rs1377，其余以实际核对为准。受控增长文件需职责/增长/拆分触发与独立审查；超过2400须有Principal Design，不把旧Design的历史迁移清单当本次需要重做。

来源归属以[origin-audit](../../../data/reports/2026-11-16-btc5m-strategy-diagnosis/origin-audit.md)为准：混源EWMA、断流/请求时序主要继承上游；净份额gate不同步、observed_at误标和受控诊断不足是本地适配遗漏。机制缺口不等于已证明亏损因果。代理基差、source clock不可得、原模型错误和官方原子舍入未被本契约验证；RECEIPT_BOUND不能当端到端新鲜度证明。

保留07-004无钱包/固定单键来源/首次写入/监督/现金和官方结算边界，不读取.env或真实keyring验证文档。共享dir禁止reset/stash/clean/restore/checkout/覆盖或移动他人工作，不改gitlink，不动已列两项skill dirty。新增范围外平台、依赖、生产数据/交易/调度或参数变化须主控/Pascal另行确认。

## 8. 开放问题与交接

开放业务语义问题：无。源时间实际不可用、真实网络延迟/官方舍入/盈利能力为明确未验证范围，不让实现者猜值或默认为已满足。内部类型名/最小代码组织、分版CLI拼写与具体测试筛选是T2 Design职责，必须维持本契约语义。

T1仅交付RFC V1.0及本SPEC V1.0，由主控核实实体/一致性后释放预建T2 t_0be95623；T2/T3原hold不自行解除，不建新卡或同卡重复review。后续独立Validate与主控Closeout保留；任何工程PASS都不自动授权新paper/live运行。

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-11-16 | 冻结六项一期行为、两费用口径/分母、源key/epoch、300秒gap与20returns、5/10秒时效/30秒重验、v2白名单/关联、/2同core对拍及22项矩阵；旧协议/普通分支和运行授权保持 |
