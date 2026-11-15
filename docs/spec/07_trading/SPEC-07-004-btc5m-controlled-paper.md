# SPEC-07-004: BTC5m 受控 unsigned paper 与最小运行接线

## 元数据

| 项 | 值 |
|---|---|
| 状态 | V1.0 RFC/SPEC 阶段契约候选；不是实现、工程验收或运行通过 |
| 作者 | YQuant Principal |
| 创建日期 / 最后更新 | 2026-11-16 / 2026-11-16（Asia/Shanghai，UTC+08:00） |
| 来源 RFC | [RFC-07-004](../../rfc/07_trading/RFC-07-004-btc5m-controlled-paper.md) V1.0 |
| 模块 / 工作区 | 07_trading；`/home/pascal/workspace/yquant-investment` |
| 需求 / 下游 | Kanban `t_5b6a743f`；预建 Design `t_020c4222`，不重建任务链 |
| 后续 Design | `docs/design/07_trading/DESIGN-07-004-btc5m-controlled-paper.md`，本阶段不创建 |
| 角色 | Design：yquantprincipal；Implement：yquantdeveloper；独立 Validate：yquantreviewer；运行：主控 yquant |

## 1. 需求摘要

固定入口区分 unsigned paper 和另行授权的 signed future-live，前者不读 keyring、不构造 signer/trader、不做认证或订单请求。唯一策略仍是 `arbitrage.rs DecisionCore/RoundTaker → runtime Broker → Predict venue`。受控 paper 显式启用 100 USDT 虚拟现金、单笔 2 USDT、单市场 2 USDT、同时成本及预占 10 USDT、累计净亏损 20 USDT 锁存停新增。六小时是有界观察窗而非保证持续开仓，截止后只核对已有成交的官方结算；工程仅离线合成验证，实际观察须独立 PASS 和主控核验后由主控启动。

## 2. 范围与既有消费者

### 2.1 保留基线与必要增量

- [SPEC-07-001](SPEC-07-001-predictfun-btc5m.md)：唯一模型/回放、BTCUSDT/300 秒筛选、单轮一次入场；不重跑 94 日研究。
- [SPEC-07-002](SPEC-07-002-predictfun-live-foundation.md)：成交/净额/去重/未知订单闭锁、账户/RPC/预算确认、SDK target digest/显式执行/不盲重发/receipt/读回。其离线工程已签收，不把旧阶段的“待实现”重列为本轮任务。
- [SPEC-07-003](SPEC-07-003-predictfun-wsl-nonexport-signer.md)：精确 keyring、派生绑定、固定 check/enroll/显式 sign-in；V0.5 已验，主控真实认证已匹配账户。存储属性、schema/content-type、后端选择和历史失败不重判。
- 已有 `runtime.rs` halt、Ctrl-C、cancel_all、连续数据失败撤报价、实时账户未知闭锁直接复用。新增是固定 run/SDK 接线、opt-in 现金与净份额费用、即时风险重检及有限退出，不重建这些能力。
- 静态缺口以 RFC §2 与本卡读取的当前代码为准；旧 paper 的 100 USD 只是报告分母，不能当作已有现金限制。

### 2.2 排除与阶段授权

本卡只新建 RFC-07-004、本 SPEC；可读公开源码/契约/指定本地报告并做文档静态检查。不写 Design/代码/测试/配置/报告，不执行网络、真实 keyring、SDK 或 BOT 业务命令。后续工程 worker 也不访问生产 keyring、`skills/.env`、私钥/JWT/seed，不真实签名/认证/广播/下撤单/approve/redeem/私有账户或余额探针；只 synthetic key、fake transport 与明确离线测试。

不新增依赖、钱包/认证核心、第二策略/执行器/OMS、数据库/持久账本、daemon/调度、自动充值/赎回/授权、跨进程恢复、数据源或调参。保持 main，不 reset/stash/clean/checkout/commit/push；不改 gitlink、其他项目/profile、模板和三层 README。不把签收资金准备、SDK 安装或短窗正收益称为资金/收益闭环。

### 2.3 后续最小文件职责边界（不是本卡修改许可）

下列路径均相对 `BOT=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。Design 必须裁剪并给精确 allowlist、直接消费者及 G3 说明；不得把目录整体当白名单。

| 职责 | 允许规划的落位上界 | 受限内容 |
|---|---|---|
| 固定入口/FD | `tools/predictfun/local_signer.py`、必要时新增 `tools/predictfun/btc5m_control.py` | 复用旧 keyring；固定模式，无任意命令转发；可将运行装配放单一新薄 helper，不复制后端 |
| SDK 接线 | `tools/predictfun/cli.py`、`tools/predictfun/sdk_ops.py` | lazy signer-fd 与 market API key；保持现有 session/signer 注入测试接缝和默认兼容 |
| 受控参数/期限装配 | `src/config.rs`、必要的 `src/main.rs`、`src/bot/runtime.rs` | additive opt-in，原默认值/旧调用保持；非全局改 paper 语义 |
| Broker 现金/费用 | `src/bot/runtime.rs`，必要时新增 `src/bot/runtime/paper.rs` | 单一 Broker 状态/锁，helper 不持有第二份交易账本 |
| 数据与策略接缝 | 必要的 `src/bot/arbitrage.rs`、`src/service/predict_fun.rs`、`src/service/venue.rs` | 只限受控模式装配、必要事实有效性/来源标记；不改模型、筛选算法、live 费用事实或认证协议 |
| 测试 | 上述 Rust 模块 colocated tests；`tools/predictfun/tests/test_local_signer.py`、`test_sdk_ops.py`、必要时 `test_btc5m_control.py` | 实际入口→原消费者 fake 集成，保留旧测试；不得搬整个测试树 |
| 公开配置/使用说明 | 必要时新增 `tools/predictfun/btc5m-controlled-paper.json`；`tools/predictfun/README.md`、`docs/LIVE-TRADING.md` | 仅公共参数和已实现的固定入口说明；不改默认 `config.json`/YAML/任何秘密 |

新 helper 是现有模块内职责拆分候选，不要求全部创建；如仍需范围外文件，先报告主控，不自行扩张。Cargo/requirements/锁文件不变。工程唯一验收报告为 `data/reports/2026-11-16-btc5m-controlled-paper/validation.md` 和 `evidence/`，不建 data/tasks 或重复状态档案。

## 3. 功能规格

| 编号 | 行为 | 可观察结果 / 失败边界 |
|---|---|---|
| F-001 | 固定运行模式、公开输入先验 | 无模式只用法/拒绝；只固定 BTC5m；错配置在取秘密/child/网络前拒绝；不隐式 live |
| F-002 | 真 unsigned paper | keyring/钱包派生/signer/trader/auth/RPC/订单发送调用全为 0；只行情与官方结果 GET |
| F-003 | 受限 signed future-live 接线 | 显式模式、固定账户、预算/RPC及真实授权分离；沿旧 signer 和账户门禁；工程只 fake |
| F-004 | SDK keyring→FD / market API key | target 与确认、只读预检先于取 key；只给固定 SDK 消费者匿名 FD；主网 market GET 带 API key，不发送到 RPC |
| F-005 | 现金/库存/预占不可复用 | 100 进入 Broker 可用现金；拒绝超现金/超 2/超 10，预占→成交或释放原子且不双占；pending settlement 不回款 |
| F-006 | 显式净份额费用 | BUY 费扣份额、SELL 费扣现金；净库存计价/结算，累计费用仅展示，不再重复扣 |
| F-007 | 累计净亏损锁存 | 本次起点累计 R+U≤-20 即停新增；回升不解锁、无自动重启/续跑；不是峰值回撤或保证封顶 |
| F-008 | 21600 秒截止与有界回收 | deadline 先关闭新增，再取消/回收、官方结果尾查；不因数据失败延长、不在尾查开仓 |
| F-009 | 官方结算与证据 | 一次兑付、DRAW 正确、pending 不造结算；Binance/Coinbase/官方结算源分别记录，Gas 未发生 |
| F-010 | 默认兼容 | 旧 check/enroll/sign-in、SDK 显式 fd、普通无钱包 paper/回放/其他策略与 venue 保持原行为 |

## 4. 数据与接口契约

以下字段为必须可观察的逻辑接口，不声称当前 Rust/SDK 已有同名 struct/JSON。Design 决定内部类型/CLI 拼写和传递方式，不重选本节业务语义。

### 4.1 固定配置、身份与启动顺序

| 项 | 受控 paper 固定值 / 规则 |
|---|---|
| venue / network / chain | Predict.fun / mainnet / 56；不能借普通 config 覆盖到其他 host/链 |
| strategy / symbol / cadence | btc-arb / 仅 `[BTCUSDT]` / `round_interval_secs=300`，缺失/null/0/其他时长拒绝 |
| 模型参数 | `min_edge=0.03`、`min_secs_left=30`、`vol_floor=0.00005`；原 EWMA/20 returns 预热、单轮一次、轮询与原限价/盘口 walk 不变 |
| 本金与金额 | initial_cash=100 USDT；`order_usd=2`、`max_order_usd=2`、`max_market_usd=2`、`max_total_usd=10`、`max_loss_usd=20`；不得缺失后继承旧 5/25/100/25 默认 |
| 开关 | 显式 unsigned 模式，`enable_trading=false`、`mock_trading=true`，controlled cash/net-share fee opt-in；实际 Broker live=false |
| 生命周期 | 一次 21600 秒；不能由用户尾参数延长、循环重跑或覆盖风险预算 |

1. 先解析模式/路径/公开 JSON/完整固定配置与生命周期，再校验环境/API 来源，最后才允许该分支所需秘密和 child。JSON 拒绝重复键、NaN/Infinity、credentials/秘密字段及畸形类型；布尔不当金额，数值必须有限且满足范围。固定 `.json`、固定 BOT cwd/binary，不读默认 YAML、`.env` 或 shell profile。
2. 沿 07-003 固定缺失 credentials 路径，`lexists=true`（包括悬空链接）拒绝，不让 loader 回落默认 YAML。新公开配置是另一个 opt-in 文件，不覆盖旧默认。
3. paper 父环境出现 `PM_PRIVATE_KEY` 或显式钱包/JWT 注入时，仅按键存在性拒绝，不读/记录值；child env 只保留必需 OS/代理/CA 与行情 API key，禁止无关 `PM_*`、钱包、JWT、加载注入变量。不调用普通 check/check-venue 作为 paper 前置证明；其会尝试样例签名。Rust 受控 paper 也须直接绕过 `PredictFunTrader::new`，不能依赖 signer 构造失败来达到“无钱包”。
4. API 来源沿既有 `YQUANT_PREDICT_FUN_TOKEN → PM_PREDICT_API_KEY` 内存映射，源缺失/空白或目标同名变量冲突拒绝；不自己加载生产 `.env`，不创建新 API key 存储。不修改父环境。秘密不可进入 argv、临时文件、配置、进程异常/日志或任务字段。
5. signed future-live 为单独显式分支，须匹配固定 chain56 / predict-account / trading address `0xfc9eb66e6F22f96608058C0A711Ed048eED8c2E2`，signer `0x5129330159f4E6a99eF873f86901E3cafa7f9A7D`。仅该分支可用原 keyring→原 Rust signer；配置须显式 enable_trading=true/mock_trading=false，保留 2/2/10/20、原 RPC/预算确认/账户/未知订单门禁，不装配 paper 虚拟现金。公开确认是人工声明，不自动产生真实授权；本轮不运行这个真实分支。
6. 无 shell/eval、任意 executable/PATH 覆盖、任意 bot/TUI、argv 尾转发、自动 sign-in/approve/redeem 或 keyring unlock/Prompt/fallback。原 enroll/check/sign-in 的固定行为不借新增 run 改写。

### 4.2 SDK 目标、FD 与只读请求

- 固定 keyring 模式仅包装现有 `cli.py`/`sdk_ops.py` 的单一 plan/check/approve/redeem 目标；不暴露任意 command。目标仍显式包含 chain、账户、market、route、额度/份额/具体合约与同意，沿原 canonical target_digest 绑定，不静默注入历史 allowance=10 USDT 提案或全局 operator 同意。
- `target.owner` 沿 SDK 含义为资产持有人（固定 Predict Account），不是 Gas signer；只读 controller 必须等于固定 signer。SDK 路由/余额/权限/结算、Gas 和同目标读回语义继续用 07-002，不自制交易协议。
- plan、check（含原 tx hash 读回）、无执行许可/缺确认/摘要失配、只读失败及已满足 no-op：keyring/FD secret read/signer/签名/发送均为 0。运行在原 `execute_target` 的 signer_loader 点才 lazy 取得已精确核验的 key，不能先读 key 再把结果交给只读预检。
- 只允许现有非 stdio 匿名 pipe/FD（fd≥3），只继承给固定 SDK 消费者，传给既有 `fd_signer_loader`；不以秘密 argv、环境私钥、普通文件、默认 fd0 或第二 signer 实现替代。父写端/子读端在成功、拒绝、异常、超时、信号各分支关闭/回收，不留下另一个 child/进程持有。原直接 `--signer-fd` 消费者继续可用；新 keyring 模式与外部 fd 互斥，不能暗中择一。
- mainnet `ReadSession.market` 只向原固定 `https://api.predict.fun/v1/markets/{explicit_id}` 注入 `x-api-key`，不向 RPC、其他 host、redirect 或日志转发；保留 timeout=15 秒、禁重定向及 route/id 检查。需要 mainnet market 读取而无 key 则失败关闭；纯 plan 不要求 key，旧 testnet/fake session 和既有调用签名保持兼容，不额外要求 keyring/JWT。
- target/config 在取 key 与执行前必须仍为已确认值，不能在摘要确认后换链/地址/market/route/额度；秘密派生失配先拒绝。只读上下文失败为未能检查，不是零余额/权限不足的伪事实。SDK 一次执行调用、未知保留 hash、不重签/重发、receipt+同目标读回才能 completed，沿原语义不变。

### 4.3 受控 paper 资金、预占和风险不变量

单位：现金/成本/PnL 均 USDT，库存为 outcome shares，价格为 USDT/share，时间记录 UTC 或显式时区。旧字段名 `_usd` 在该部署按 USDT 风险预算使用，不代表本轮已测 USDT/USD 汇率。采用现有 f64 计算和盘口 walk 精度，不引入依赖；验收数值用 `abs≤1e-9 或 rel≤1e-9` 对拍，身份/状态/计数零容差，不利用容差放大资金。

定义：`C0=100`；`B` 为已发生虚拟现金余额；`K=Σ未平仓净库存成本`；`R` 为累计已实现净损益；`P=Σ尚未成交/未闭合 BUY 的剩余最坏现金预占`；`A=B-P` 为可用现金；`V=Σ净库存×有效 mark`。本轮无充值/提款/借款/杠杆。

- 初始 `B=A=C0=100`、`K=R=P=0`、净库存为 0。完整账务始终满足 `B=C0+R-K`、`NAV=B+V`、`net_pnl=NAV-C0=R+(V-K)`。P 是 B 的受限部分，不从 B 再减一次计算 NAV。
- 下 BUY 前，对原数量向下取整后的 gross shares `q`、limit `L`，最坏对价 `w=q×L`；必须同时 `1≤w≤2`、该市场 `K_m+P_m+w≤2`、`K+P+w≤10`、`w≤A`，且无 halt/截止/数据或账户闭锁。2/10/20 是不同维度，100 不能仅出现在输出收益率中。
- 校验和预占必须在同一 Broker 原子状态中进行，不能两个并发 take 各自看到旧现金后都通过。新受控 paper 不安装真实 OrderVenue，因此不调用 `place(...,false)` 做签名 dry-run。盘口全额 walk 成功后，用实际模拟对价 c 取代该笔预占：`B-=c`、`K+=c`、`P-=w`，有效净份额增加；价差 `w-c` 重新可用。实际 c 不得大于 w；异常不裁剪或借款取绿灯。
- 明确未成交/尚未应用的本地拒绝释放对应预占；未知/未闭合风险保留。成交成本与同笔已转换的预占不得重叠。已有挂买单计入 P；取消受理本身不证明可释放，继续沿旧终态/去重规则。受控 BTC5m 不新增 maker 策略，若共享 rest 接口启用该资金状态，也不能绕过现金门禁（可明确拒绝受控模式 rest）。
- 未到官方确认的持仓即使到期或浮盈，也保留 K/净库存，不增加 B/A。换轮、空持仓 API、summary、断网、错误/重启不得视为回款。已确认卖出/官方结算按 §4.4、§4.6 才释放相应成本/库存和净现金。
- 现金不足/超过限额/非法数值/不兼容场馆规则均在应用成交前拒绝，并给稳定原因；不自动缩上限以外的金额、补仓、放宽 min_edge、借钱、提高 2 USDT 或自动舍入向上。仅保留原 `shares_for` 的向下取整与合法 tick/精度；若取整后低于最低买入 1 USDT，拒绝。不用 `shareThreshold=100` 推导最小买入，依据为官方明确规则；市场当前规则不能确认则停该新增，不造成功。

### 4.4 新模式的费用、净库存与成本分配

受控模式显式标记 `paper_net_shares`（逻辑标签），旧 paper gross+单列等值费用模式继续保留。新模式模拟费率取市场 feeRateBps，`r=bps/10000`，对原 walk 得到的模拟 VWAP p 和 gross shares q，`f=r×min(p,1-p)×q`（USDT 等值）；这是现有模型费用在模拟 VWAP 上的计算，非逐笔实际撮合或链上取整证明。p 必须有限且 `0<p<1`，费率/数量须合法，净份额不得负数；无法取得有效数据拒绝，不默认缺失费用为零。

| 动作 | 现金 / 净份额 / 成本与损益 |
|---|---|
| BUY | c=q×p；份额费用 `f_q=f/p`；净到账 `q_net=q-f_q`；B 扣 c 而非 c+f，库存只加 q_net，成本加 c。持仓均价是 `cost/q_net`，不是成交 VWAP。fee 展示累加 f，并记录扣份额数量 f_q |
| SELL（只验共享记账，不给策略新增主动退出） | 最多卖已确认未占用的净库存；gross 对价 c=q_sell×p；现金净收入 c-f；扣 q_sell 库存，按卖前平均成本分摊 basis；`R+=c-f-basis`、`B+=c-f`、`K-=basis`。不得用原 gross 买入量扩大可卖量 |
| 官方结算 | payout∈[0,1]，现金收入 q_net×payout；`R+=收入-basis`、`B+=收入`、移除相应库存/K，无另收模拟交易费 |

R 与 U=`V-K` 已反映实际模拟净额，`fee_total`/`fee_in_shares` 仅审计展示；不再对 `R+U` 或 `B+V` 扣 fee_total。若复用现有 Summary::equity/fees_in_cash，必须使其结果与该恒等式一致，不让旧 `realized-fees+unrealized` 再扣一次。新报告分别列 gross 模拟对价、净份额、费用扣取方向、现金净额、R/U/NAV，不把模型预计成本标成 live 官方费用。舍入/精度沿实现明示，保留足够数字供复算；不宣称已模拟官方原子取整。

### 4.5 20 USDT 亏损锁存与数据失败

1. `net_pnl=R+U≤-20`（包括恰好 -20）立刻设置本次 latched halt，阻止所有增加风险的 BUY。检查时点为每次成交/费用/结算/估值变化完成后，以及下一笔新增校验前；同 tick 第一笔触阈值后不能等下一 observe 再挡第二笔。
2. 估值沿现有成功观察盘口 midpoint（No 为 1-Yes），不是模型 fair，也不是可执行清仓价值；仅已发生交易费进入净额，不额外假定未来卖出费/Gas。持有到结算，不因 halt 自动卖出/对冲/赎回。20 是累计起点损益阈值，不是盈利峰值回撤、亏损单绝对额之和或已实现损失单项。
3. 本轮所需行情/持仓 mark 读取失败或不可用时不允许用旧值/买入成本 fallback 证明健康后新增；保留库存/资金占用，报告估值不可用/旧值时间，不造零浮亏。成功读回可解除临时 data block，但不能解除已触发的 loss latch。原连续 tick 失败撤报价保留，不另造自动恢复服务。
4. 后续回升/结算后高于 -20 仍 halted=true；亏损可能因跳变/观察间隔超过 20，不承诺保证封顶或已平仓。终止、崩溃、重启均不得把同次 C0/亏损窗口恢复为新预算，见 §4.7。

### 4.6 官方结算与虚拟回款

仅复用 Predict `MarketData` 的官方市场/轮次事实：同 market/token/BTCUSDT/精确 300 秒，非争议/未确认状态，官方起止价与 outcome 可交叉核对；合法 `payout_yes` 在现有官方 mapping 中取得，No 为 1-payout_yes。官方精确平价 DRAW 按 0.5；明确结果冲突/缺失、尚未结算或争议保留 pending，不能只因 ends_at 已过而补值，不用 Binance/Coinbase 本地涨跌替代官方结果。

paper 在官方结果成功验证并应用该净库存兑付时，才一次性增加 B/A 并释放 K。重复轮询、重复结果、重复尾查不能再次回款；冲突进入待核对，不追溯自动改账。live 沿原账户/receipt/资金读回处理，`settle_resolved` 的账面 settled 不是 USDT 已 redeem 到账；未到账利润不得当实际可用现金。paper 虚拟即刻回款不证明实盘赎回等待、Gas 或真实周转能力。

### 4.7 六小时观察、退出与不重启

- 记录一次运行 run_id、开始 UTC、固定预算/配置/候选身份及 21600 秒 deadline。计时从实际启动尝试开始，含 child 启动、等待、数据断连与 WSL 暂停；不能按成功 tick 数累计六小时。使用绝对 UTC 截止与经过时间保护，任一先到即停新增；倒拨不能延长，重获执行时在 tick/新增前先判截止。
- 无损失/人工中止时才观察至 deadline；亏损触发后可继续只读观察和结算至原 deadline，但永不新增，因此六小时不等于六小时持续入场。没信号/全部拒绝也可完成观察，不强求成交数/盈利。
- deadline 边界含等号，新增门禁优先于同时可用信号；已预占但未应用的 paper 新增不得在截止后成交。先原子关闭新增，再沿原 Ctrl-C/cancel_all/信号传播和进程回收，正常清理预算最多 30 秒，卡住则终止并回收子进程，标记强制/不完整，不重启。SIGINT/人工提前停也同样无新单；紧急取消/信号不必为尾查延迟响应。
- 截止后只对本次已有成交相关市场（特别是最后一轮）补官方只读结算检查。尾查最多 600 秒墙钟，总含请求等待；每市场按原 60 秒结算检查节奏、单请求不超过 15 秒且夹到剩余预算，不能请求耗尽后再无限等待。尾查不运行新策略、不签名/下撤真实订单、不 redeem，不延长入场窗；可在尚存 Broker 只读收尾中应用兑付，或复用现有离线对账器生成最终官方结果，不能由对账器恢复交易/重新注资。退出/尾查由固定入口监督，精确装配位置归 Design。
- 尾查结束未确认：pending 市场/净份额/成本、最后有效估值及其时间、不可最终化损益单列；不填零、不按预测结算、不无限续查。总额区分已实现最终部分、估值部分与最终化状态。
- 一次性启动记录须 exclusive-create，在启动 child 前成功写入；已有同 run 启动记录拒绝重入（正常/中断/损失均一样）。缺/坏结束记录视为中断；不支持 restart/resume，不从日志恢复账户，不按进程退出成功自动重建 100 USDT。人工须核账和新的明确授权才可启动新观察；改 run_id 不是绕过原授权的许可。无需新持久交易账本/系统互斥服务。
- 父启动器失去监督不得留下无限期 child；停止传播/有界生命周期必须在无网 fake child 证明。分别记录 launcher exit、child native exit/signal、截止原因与清理结果；例如外层 exit0 不能抹掉 child timeout=124。不得丢弃所有运行日志再声称可对账。

### 4.8 来源、输出和错误

每笔模拟成交关联 run/market/token/side、gross/net 份额、VWAP/对价、feeRate/费用单位及扣取方向、B/A/P/K/R/U/NAV、来源时间、spot source。模型输入继续 Binance；沿原 paper 允许 Coinbase fallback，但单独汇总其成交数/损益，不能与 Binance-only live 同等举证。官方 settlement provider 来自官方元数据（已有样本 CHAINLINK），未知明确未知，不把源码 Binance 结算注释当官方来源。

Gas 标 `NOT_INCURRED`/`NOT_MEASURED`，可说明模拟未扣 Gas，但不填伪造 gasUsed/BNB支出或“实测零成本”。paper 是原全额盘口 walk 或拒绝，非排队/真实部分成交/网络执行/赎回时延模拟。六小时结果不年化、不声称持续 alpha，不与旧 gross 模式结果拼成同口径收益序列。

错误至少能区分输入/配置、环境冲突、秘密后端、目标确认/身份、缺行情 API key、现金不足、单笔/单市场/总量、最低金额/精度/深度、数据不完整、loss latch、deadline、重复 run、启动/超时/回收、官方结果 pending/conflict。可沿原枚举，Design 冻结新 token，不要求全部引入公共错误类。拒绝前的调用计数/资金不变可断言；错误只固定 code/step/reason 和允许的公开关联，不输出底层异常/原响应/含密 URL/环境。首次写日志前完成脱敏；不能先落 raw 再清洗。

## 4.bis 持久化与证据

无生产 DB/schema/索引/TTL/迁移。Broker 内存为本次虚拟现金/预占/净库存/损失唯一计算状态；运行证据不是可恢复主账。现有 keyring 的秘密 schema、存储和权限不变，API key/JWT 不持久化。本节是证据最小字段要求，不是新任务状态表。

实际 paper 由主控按启动日独立主题 `data/reports/YYYY-MM-DD-btc5m-controlled-paper/` 保存，路径与工程 validation 分离且不覆盖；Design 选该主题下精确证据文件名。以下都是公开或最小工程内部数据（L0/L1），无 L2/L3 原始私密数据；测试秘密仅内存，不落证据。

| 对象 | 单字段/规则 | 类型 | 必填 / 来源 | 生命周期 |
|---|---|---|---|---|
| 一次性启动证据 | schema_version | string | 是，新模式版本；旧报告不当新账 | exclusive-create，保留，无自动删除/TTL |
| 同上 | run_id | string | 是，本次唯一公开关联 | 同上；存在即拒绝复用 |
| 同上 | started_at | timestamp | 是，实际 UTC/offset | 同上 |
| 同上 | deadline_at | timestamp | 是，started_at+21600 秒 | 同上 |
| 同上 | mode | enum | 是，unsigned/signed 明确 | 同上 |
| 同上 | candidate_identity | object | 是，HEAD/实际 binary及受影响文件 SHA | 同上，不含秘密摘要 |
| 同上 | public_config_identity | object | 是，公开配置 SHA 与有效100/2/2/10/20等参数 | 同上，不复制秘密或全部环境 |
| 脱敏事件 | event_time | timestamp | 是，来源/观察时间区分 | 追加保留，同主题无自动清理 |
| 同上 | run_id | string | 是，引用本次启动 | 同上 |
| 同上 | market_id | string/null | 涉及市场必填 | 同上 |
| 同上 | event_kind | enum/string | 是，模拟成交/预占/释放/阻断/结算等 | 同上 |
| 同上 | accounting | object/null | 涉及记账必填，§4.3–4.4各金额/数量/单位/扣费方向 | 同上；不作恢复输入 |
| 同上 | source | object/null | 行情/结果必填，来源、时间和公开证据引用 | 同上 |
| 结束证据 | exit_facts | object | 是，launcher/child原生退出/信号/强制清理/原因 | 独立创建，缺失视为中断 |
| 同上 | final_accounting | object | 是，B/A/P/K/R/U/NAV和loss_latched，缺估值则null+原因 | 同上 |
| 同上 | settlement_status | object | 是，confirmed/pending/conflict逐市场及最终化标志 | 同上 |
| 同上 | limitation | string/list | 是，paper/Gas/源回退/非alpha与未覆盖 | 同上 |

工程报告只记录候选、实际命令/exit、矩阵结论与证据引用。数据当前被 Git 忽略，不为归档改忽略规则、不自动上传/备份、覆盖/删除/迁移旧证据；不创建手工任务/阶段状态文件。旧报告格式只读保留，新模式独立标记，不能悄悄改历史数值。

## 5. 验收标准

以下是后续工程/运行要求，不是本阶段已执行结果。所有数值正反例均是 synthetic/fake；默认 fixture 100/2/2/10/20、bps=200，除特意内部注入的小现金/历史损益边界。公开固定账户只能测绑定/拒绝；成功派生使用内部注入的公开 synthetic 身份，不伪造固定账户私钥。

| 编号 | 输入 / 场景 | 必须结果 / 消费者验证 |
|---|---|---|
| A-001 | 无模式、错 symbol/300、参数缺失或非有限/类型错误、wrong chain/venue/enable/mock、credentials存在或悬空链接、重复JSON、任意argv/binary/TUI | 真 parser/入口在 keyring/child/网络前拒绝；不隐式选模式或继承旧资金默认 |
| A-002 | 合法 unsigned；父环境夹钱包/JWT/其他秘密；keyring/trader/auth/place fake设为调用即失败 | 合法运行上述调用均0，子环境只行情必要项；禁止钱包注入在读取值前拒绝；不执行 check-venue/sign-in/私有RPC；实际 Rust connect seam 证明不构造 trader |
| A-003 | signed future-live 合法fake与错身份/缺预算/RPC/错开关；普通check/enroll/sign-in | 合法仅固定原run/signing链；反例拒绝、旧账户闭锁不绕过；原三入口完整回归，无真实调用 |
| A-004 | SDK plan/check/tx读回、无execute/摘要错误、只读失败、already-satisfied；合法执行fake | 前者keyring/FD read/签名/发送0；后者只在原loader点取精确synthetic key，匿名FD到原loader→原SDK，账户/摘要相同；直接旧signer-fd回归 |
| A-005 | SDK market 请求捕获，mainnet有/无/冲突API key，testnet和fake session；redirect/error | 主网正确header只到固定market host，缺/冲突拒绝；RPC/其他host/重定向无key/JWT；不修改target_digest、不加认证；超时、route/id反例仍关闭 |
| A-006 | SDK摘要确认后目标变更、key派生失配、FD失败/信号/超时、广播后不明或receipt/readback失败 | 前者签名前拒绝；FD/child无泄漏；后者保留同hash与未完成、不重发、不伪造completed；沿原ops完整回归 |
| A-007 | 初始实际Broker cash100；内部fixture cash1.5、其他限额允许，BUY最坏2；对照旧无现金模式 | 初始B=A=100；低现金拒绝且资金不变，不能只测10总量后推断有现金约束；旧模式不要求本金 |
| A-008 | 5个不同市场各最坏2未闭合/持仓；第6个；同市场重复；并发预占；成交均价优于限价；拒绝/取消/未知 | 10等号可、>10拒绝，同市场>2拒绝；并发不超限；预占转实际成本/退价差只一次；未知不释放，已成交与原预占不双算；实际Broker take而非仅纯函数 |
| A-009 | BUY q=5,p=0.4，当前mark=0.4，bps200 | gross支出2、fee等值0.04/扣0.1份、净4.9、B98/K2/P0、U=-0.04、NAV99.96、净损益-0.04，非-0.08；费用不额外扣现金 |
| A-010 | BUY q=2.5,p=0.8，bps200；A-009净库存卖4.9@0.6；尝试卖原gross5 | 前者fee0.01、扣0.0125份、净2.4875，非固定扣名义2%；SELL gross2.94、fee0.0392、net2.9008、B100.9008、R0.9008；卖5拒绝/不超过净库存，不造5份成交；不改变策略为主动卖出 |
| A-011 | A-009分别获官方WON/LOST/DRAW；到期但pending、结果冲突、重复查询与最后轮尾查 | 最终B分别102.9/98/100.45，R分别2.9/-2/0.45，K=0；pending/conflict无回款、不解占；重复回款0；live账面结算不冒充redeem到账 |
| A-012 | 累计R=-19、U=-1；对照-19.999；利润峰值+10后到-11；先赢后亏 | -20含等号锁存、-19.999不触loss；峰值回撤21但起点-11不触；以净累计非亏单总和判断；回升至-10仍halted |
| A-013 | 当前成交费用/估值/结算恰令净损益到-20，同tick第二笔；mark缺失/读取失败 | 第一笔后立即锁、第二笔拒绝；不能等下一轮observe；数据失败保留占用且停新增、标不可估值，不以旧mark/成本/零浮亏取绿灯 |
| A-014 | 原RoundTaker→Broker fake连续tick；BTC非300/无起价/预热不足/剩余29秒、恰30秒、一次入场；Binance和Coinbase | 原筛选/预热/费用后edge/单轮一次不变；29拒绝/30可参与原判断；paper fallback单列，signed Binance guard保留；不复制core或只测copy |
| A-015 | fake clock在21599/21600、同边界信号、网络阻塞/时钟倒拨/暂停；有loss halt继续观察 | 21600先停新增，阻塞/倒拨不补时；暂停恢复先判deadline；loss回升不恢复；用可控时钟证明，不真跑6h；无信号不强制下单 |
| A-016 | fake child正常、非零、SIGINT、超时、拒绝停止、父监督丢失；同run再次启动、缺结束、崩溃后尝试resume | 取消/停止传播并有界回收，清理≤30秒或强制且如实标记；同run拒绝/无恢复、不重建本金/亏损，launcher与child退出分开；原急停机制不被替换 |
| A-017 | 最后一轮官方结果延迟后到；尾查一直失败/争议；600秒预算耗尽 | 只已成交市场GET；原60秒节奏/请求≤15秒夹预算，0新增/认证/redeem；延迟结果只兑付一次；到预算停止并pending，损益不伪最终化 |
| A-018 | stdout/stderr/异常/URL/FD/child输出夹synthetic API/key/JWT/signature/代理哨兵；保存证据 | 首次落盘前过滤，输出及普通文件无秘密/秘密摘要；公开关联与账务足以复算；无全环境/raw响应泄漏，Gas未发生与alpha限制准确 |
| A-019 | 旧paper/replay/其他策略/venue，07-003完整helper与07-002 SDK ops及共享调用构造者 | additive opt-in默认不变、可编译、必要受影响回归真实通过；不以只测新helper/编译代替端到端fake；不运行联网ignored测试 |

数值向量在 T1 用 Python Decimal 从上述公式复算，不是实现测试或真实场馆事实。复杂多次预占/成交/卖出/结算序列须逐事件核验 §4.3 恒等式，不只比较最终报告余额。

实际六小时观察另列主控运行核对，不是工程 worker 必跑项：候选和有效配置匹配、无钱包/JWT、启动/结束/退出事实、实际可观察时长、成交/拒绝与停止后零新增、逐笔费用/净库存/现金和官方末轮结果对账、pending/数据源/Gas边界、结果与未完成项。真实启动失败/中断如实记录，不以 synthetic PASS 冒充观察完成；不强求正收益/成交数。

## 6. 测试与本阶段自检

- Design 提供精确安全命令与测试隔离接缝：原 Rust Broker/DecisionCore/连接装配的 fake 集成、Python真实 parser→公开校验→子环境/FD→原SDK消费者 fake，不能只测字符串或新纯函数。
- 现金100与2/10/20分别反例；内部低现金 fixture 只测Broker约束，不开放生产任意本金CLI。亏损历史可在内部 fixture注入，不新增持久恢复设施。
- 仅无网、隔离 synthetic；原API/keyring/backend使用会报错的fake，固定真钱binary不执行。停止测试可运行无网fake executable/受控匿名pipe/隔离socketpair，不连接真实服务。测试临时文件仅当前profile scratch。
- 默认兼容回归覆盖受影响的helper完整测试、SDK identity/ops、Rust运行时/模型/回放与直接构造者；不重跑94日/旧6h，不升级依赖换绿灯。具体测试名由Design按实存源码确认，不杜撰计数。
- 独立Validate记录候选HEAD+文件SHA、真实命令/原生exit、A-001–019覆盖、失败与未验证范围；三独立文档存在且一致才进入实现。开发者自测不替代独立验收，不因旧offline签收重开已关闭finding。
- 本T1只检查两文档实际存在/引用/占位/空白/范围/公式与向量、path-filtered git diff-check并记录身份。不运行以上业务测试、不声称SDK网络或真实账户/资金闭环。

## 7. 安全与交接约束

worker只在指定工作区和本阶段文件内工作；上游README/requirements/helper/tests和07-003文档dirty是基线，path-filtered审计，不reset/stash/clean/覆盖。runtime拒绝立即停止该动作，原拒绝留Kanban，不换工具/profile/路径重放。敏感值不进命令参数/普通文件/报告/日志/聊天，首次日志前脱敏；不承诺同UID/管理员/进程内存或物理清零隔离。

本阶段交主控核验RFC/SPEC后释放已有Design。Design负责精确types/CLI/文件allowlist/G3/增量估算、调用点、实现顺序、测试和最小回滚；不能把本节已冻结金额、费用/现金、退出/授权语义再交实现者决定。后续独立工程PASS只支持主控已获准的一次unsigned paper；签名run、allowance/operator、真实订单/redeem/到账、长期运行、盈利资格均另行明确授权/验证，不默默增加第二流水线或运行服务。

## 8. 开放问题与版本

开放业务契约项：0。动态行情/费率/最低精度、SDK真实网络、当前账户余额/权限、真实资金闭环与盈利未由本轮文档证明；无法满足时按上文拒绝/待核对，非实现者自由猜测。真实账户历史100 USDT/0.00499 BNB不是本轮刷新，100虚拟本金与真钱余额无绑定。

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-11-16 | 从RFC-07-004冻结固定模式、SDK接线、100现金/2/2/10/20、净份额费用、累计亏损锁存、21600秒和有界尾查、A-001–019及授权分离 |
