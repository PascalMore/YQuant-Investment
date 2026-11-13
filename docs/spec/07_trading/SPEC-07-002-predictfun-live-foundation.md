# SPEC-07-002: Predict.fun 最小实盘接入基础（Toolkits + 官方 SDK）

## 元数据

| 项 | 值 |
|---|---|
| 状态 | V1.1 窄修订草稿；RPC 与官方直接 SDK/Privy 路由输入已闭合，待主控 Gate；非实现/实盘验收通过 |
| 作者 | YQuant Principal |
| 创建日期 / 最后更新 | 2026-11-13 / 2026-11-13（Asia/Shanghai，UTC+08:00） |
| 版本 / 目标模块 | V1.1 / 07_trading |
| 来源 RFC | [RFC-07-002](../../rfc/07_trading/RFC-07-002-predictfun-live-foundation.md) V1.1 |
| 适配 Agent | yquantdeveloper、yquanttester、yquantreviewer；主控 yquant |
| 来源任务 / 工作区 | T1 `t_58c245a7`；`/home/pascal/workspace/yquant-investment` |
| 后续 Design | [DESIGN-07-002](../../design/07_trading/DESIGN-07-002-predictfun-live-foundation.md) V1.1，已独立存在；原 T2 历史保留 |

## 1. 需求摘要

复用唯一 Toolkits Rust 执行链，修正 Predict.fun 成交事实、预算与账户失败处理。官方 `predict-sdk==0.0.22` 仅在同 BOT 的 Python 薄工具中直接调用，不承担策略或订单热路径。工具默认无 signer、无签名、无交易发送；显式 approve/redeem 能力只验证无网 fake 和默认拒绝。后续离线工程验收通过仅支持申请人工值守小规模试运行，不代表真实账户、成交/赎回或盈利已验证。

## 2. 范围

### 2.1 In Scope

- BTC5m `RoundTaker → Broker::take → OrderVenue::place → PredictFunTrader` 的真实回执消费，以及 copy 的 Predict.fun 必要兼容。
- 确认零/部分/全额/未知、实际金额/VWAP/费用/净份额、稳定订单与成交身份、去重增量、未知提交/撤单竞争、账户核对和重启阻断。
- SDK 计划/查询与显式受控授权/赎回入口；直接 import 官方包，锁制品与必要传递依赖，隔离环境。
- 保留原策略、无钱包 paper、历史回放、分页/限额保护及其他 venue 行为的定向回归。

### 2.2 Out of Scope

无新 OMS/数据库/持久 journal/daemon/调度/Web UI、自动赎回、跨日/跨重启自动恢复、SDK submodule/源码移植、dr-manhattan/TS/第二 bot/第二执行工程。无策略优化、数据源/模型/资金参数修改；不重做 94 日研究或 6h paper。当前全流程不执行真实或场馆模拟订单、账户认证/真实签名、私有 API、资金操作、生产库读写或新 paper。

### 2.3 文件边界与层次

`BOT=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/`。实现只落同 BOT；候选接缝为 `src/service/venue.rs`、`src/service/predict_fun.rs`、`src/bot/runtime.rs`、`src/service/order_executor.rs`，候选 helper 为 `src/service/predict_fun/{fills,account}.rs`，工具在 `tools/predictfun/`，说明在 `docs/LIVE-TRADING.md`。这些是职责落位，不是 T1 实现许可或完整 allowlist；T2 必须列清直接消费者/构造者、精确文件及测试/回滚命令，再由主控放行实现。

T1 只写 RFC-07-002、本 SPEC 及 `data/tasks/active/2026-11-13-predictfun-live-foundation/rfc-spec-handoff.md`。不创建 Design，不改旧 07-001、模板、三层 README、源码/测试/配置/锁文件或 gitlink。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | SDK 唯一依赖与薄调用 | 固定 `predict-sdk==0.0.22` | 官方包身份/锁定信息、`predict_sdk` 直接调用 | 不以 HEAD 代发行版，不复制 SDK、不换版绕过不兼容 |
| F-002 | 默认计划/只读检查 | 明确目标、无 signer 账户上下文 | 计划，或真实可读授权状态 | 缺 contracts/RPC/owner 返回不可检查；不为查询加载私钥 |
| F-003 | 显式授权/赎回能力 | 明确操作意图、账户/合约目标和必要参数 | 逐步骤结果和读回证据 | 当前仅 fake；无明确执行意图不得签名/广播 |
| F-004 | 回执事实分类 | 请求约束、官方订单/成交事实 | 独立的成交数量、核算完整性和终态证据 | 不以 accepted/hash/remove/空列表直接判零或全额 |
| F-005 | 实际增量记账 | 去重成交、实际金额/费用/净份额 | 唯一账本增量、VWAP、可用份额与风险占用 | 不用 limit/模型手续费伪造实绩；缺事实保留 unknown |
| F-006 | 提交不明与查询 | 已签 hash、可选 order ID、传输结果 | 原订单查询/未确认、预算保留 | 不重签补单；已可能发送的异常不可丢身份/占用 |
| F-007 | remove 与成交竞争 | remove 回应、后续订单/成交状态 | removing/未闭合，或权威终态且已对账 | remove HTTP 成功不代表不可成交；失败/竞争不清零风险 |
| F-008 | 启动/运行账户核对 | 同链地址/模式、余额/gas/授权、分页持仓/订单/成交 | 已核对可新增或明确阻断原因 | 任一必要读取失败、缺页、身份/账实不符则不新增 |
| F-009 | 重启边界 | 空内存、新运行请求、官方事实和人工确认 | 对账及新预算确认后才允许继续 | 不根据余额非零自动恢复，不声称跨进程去重/预算恢复 |
| F-010 | 既有行为兼容 | paper、历史回放、其他 venue/copy | 原策略/入口与必要编译兼容 | 不让 SDK/密钥成为无钱包 paper 前提，不扩其他策略 |

## 4. 数据与接口契约

以下为强制逻辑字段和行为，不冒充官方 JSON 字段名或当前 Rust struct。T2 决定具体类型/命名及原始字段映射、来源与单位；不能映射的事实按 unknown，不能杜撰字段。

### 4.1 身份、单位与错误

- 账户身份为 chain ID、实际交易/持仓地址、账户模式；signer 地址是独立角色。订单、SDK 工具、授权/资金/持仓读回必须核对同一上下文；不支持的账户模式明确拒绝，不退回猜测的 EOA。
- 订单必须保留本地关联键和发送前已签 hash；venue order ID 仅在收到时填入，二者均保留且不能混用。ID 缺失不能推出未发送；hash 查询暂不支持/查不到也不证明未成交。
- 成交关联订单/market/token/side、官方事实身份与来源时间。时间明确 UTC/时区；份额、抵押币原子精度与展示精度分开，标出 token/decimals，金额标抵押币种。USD 风险折算不替代实际币种金额。
- 数量/价格/金额必须有限、非负且符合官方单位；非法值、份额矛盾、费用币种不支持或字段缺失返回不完整/冲突，不取绝对值、截零或默认零。官方明确零费用才记零。
- 下列是错误类别，不冻结 CLI exit 数值：`INVALID_INPUT`、`EXECUTION_NOT_ENABLED`、`ACCOUNT_MISMATCH`、`READ_UNAVAILABLE`、`FACT_INCOMPLETE`、`SUBMISSION_UNKNOWN`、`RECONCILIATION_REQUIRED`、`TX_UNCONFIRMED`、`SDK_INCOMPATIBLE`。结果必须含失败步骤、原因及可用订单/tx 关联；不可输出凭据。缺字段不能返回健康成功。

### 4.2 成交、终态与核算完整性相互独立

| 数量分类 | 判据 | 允许的记账/预算行为 |
|---|---|---|
| 确认零 | 权威查询确认累计零，且订单已不可继续成交、成交核对完整 | 无成交增量；释放未成交预算；VWAP 不适用而非 0 |
| 已知部分 | 已确认 gross 成交量大于零、小于请求量 | 只应用确认增量；若仍可能成交/核算不完整，保留剩余预算并停止相关新增 |
| 已知全额 | 权威 gross 成交量达到原请求量、无重复/冲突 | 仍须实际金额、费用、净份额完整才能核算完成；净到账小于请求量不等于部分成交 |
| 未知 | 超时/错误/缺失/不可解析，或只收到 accepted 而无可证实成交 | 不生成零/满额事实；保留身份、预算及原因，查询同订单，不重新发单 |

已知部分终态允许结清已确认部分并释放权威未成交余量；全额数量但费用未知仍是不完整核算，不得释放为健康账户。可独立保留“已确认零增量但订单仍 open”的事实，此时不是终态确认零，继续保留风险。不把 `None`、空 matches、查询失败或 FAK 名称当“确认零/满额”。

### 4.3 实际金额、费用、净份额与去重增量

- `Q` 为官方已确认 gross 成交份额，`C` 为同批成交的 gross 抵押币对价；两者须来自真实回执字段或其明确官方单位转换/成交汇总。`VWAP=C/Q` 仅在 `Q>0` 且对价完整时定义。limit 只是签名约束；盘口 walk 价格和模型费率只用于计划/保守风险，不写成 live 实际成交。
- 费用按币种/扣费方向分别记录，净现金和净到账/扣减份额优先使用官方事实；由 gross/fee 派生时必须披露映射并与净字段核对，不能重复扣已净额。若官方费用事实不足，保留数量事实与未知核算，不估成“真实费用”。
- 明确示例语义：对尚未净额的 BUY，实际现金支出为 `C+额外抵押币费用`，可用净份额为 `Q-份额费用`；SELL 的实际现金收入为 `C-额外抵押币费用`，库存实际扣减按官方 gross/份额费用事实映射。SELL 不以请求量/本地估算可卖量代替实际成交，未确认卖出继续保留相关库存/风险。其他币种费用不能悄悄按 0 或 1:1 抵押币处理。
- 去重键优先采用官方唯一成交 ID，并以账户/链/订单上下文限定；无可靠 ID 时仅在可证明同口径、单调且完整的官方累计快照上做差。T2 记录证据与键，不能用轮询时间造新 fill。没有可靠键或累计口径则阻断进一步应用，保持待核对。
- 同 ID 重复/等值累计快照：增量为零；累计由旧到新：只应用差值，累计 VWAP 用累计金额/数量重算，不平均两次 VWAP。旧快照不回退账本；矛盾修订/累计减少不自动冲销，进入核对阻断。并发回调/轮询只能使同一事实原子应用一次。
- 数量已确认但现金/费用暂缺时，必须保留已知风险而不制造完整成本/PnL；补齐时只补未记字段，不把数量再记一遍。可卖量只使用已确认可用净份额；不能以 `Q` 代替尚未确定的净到账。

### 4.4 预算、提交与撤单闭合

- 在可能发单前以既有风控口径预留请求最坏风险，保留单笔/单轮/总敞口/亏损限额；本契约不改变额度或把亏损阈值变成绝不超损保证。
- 未确认、open/removing 或核算不完整的订单：已确认部分风险与未闭合剩余风险均受保护。预算占用表示同订单“已确认占用 + 尚未闭合预留”，不是把整笔原预留与已成交再算两次；在闭合前不因部分/缺字段将总保护降到原保守占用以下。若实际风险超出预留，保留真实更高风险并阻断新增，不裁剪事实取绿灯。
- “相关新增”定义为该资金账户、该 venue 下会增加风险的所有新订单；账户健康/总预算不能隔离时不得仅停一个 token 却允许同账户其他 token 继续。仍允许同身份查询、对账与已有撤单流程，不自动卖出/转账/新风险补单。
- 发送前明确失败且可证明未广播/未提交，或权威拒绝且无可成交风险，方可释放对应预留。任何可能已经发送的异常必须保留结构化待确认事实，不能由 `?`/普通错误路径释放占用或丢掉 hash。
- 网络恢复后只能查同订单并归集增量；本期不自动重新提交，包括同 hash 重发或新 salt 重签。FAK 部分并不授权自动补齐剩余量。
- remove 的受理、HTTP 成功、用户界面 removed 都不是终结风险证据。必须取得该订单不可继续成交的权威状态并归集所有已确认成交，才能按事实释放未成交余量；此之前的 late fill 按同去重规则入账。读不到/无法证明闭合则继续占用、阻断相关新增。

### 4.5 账户、分页与重启

- 启动和运行期复用现有 client、认证刷新、positions 分页、页数上限与启动持仓风险计入，不另写采集器。余额、gas、授权、持仓、未闭合订单/成交读取必须使用同链/地址/模式，来源和可读状态可诊断。
- API/RPC 失败、解析失败、未知 schema、分页中断/游标循环/页数触顶不能产出完整零账户。只有成功且完整的零余额/空持仓才可标 known zero，仍须满足其他风险条件。现有持仓保留，不因失败删除。
- 未知来源持仓、挂单、本地与官方份额/现金不符，或缺必要余额/gas/授权时拒绝新增并列原因；不自动出售陌生资产、批准权限或充值。
- 重启后默认待核对：官方持仓/订单/成交与之前未解释事项先对账，再取得人工对新运行预算的确认。无自动跨日亏损累计恢复、跨进程幂等保证或可靠持久订单意图。T2 定义最小人工确认入口，不让“清空本地状态/改标志”消除未解释风险，不新增持久 OMS。

V1.1 显式输入修正（Pascal 批准，t_188a7257；非新验收层）：

- 主 CLI `--predict-rpc-url <URL>` 是可选参数但 Predict live 新增必须具备的只读上下文；没有默认值、环境/配置 fallback，不复用 polygon_rpc_url，不取 SDK RPC_URLS_BY_CHAIN_ID。使用现有 url::Url 解析绝对 http/https URL、必有 host、禁止 fragment；空白/空值/其他 scheme/相对地址拒绝。URL path/query/userinfo 可能含 secret，只留内存，不写配置/日志。
- main 在 AppConfig::load 读取凭据之前完成 URL、确认声明和每个 reconciled hash 的格式检查；非法 URL 为 INVALID_INPUT/PREDICT_RPC_URL_INVALID，不回显输入。缺 URL 不必先加载凭据来判断：保留 None，只有实际 Predict live gate 报 READ_UNAVAILABLE/MISSING_READ_CONTEXT。paper/非 Predict 不要求 URL，不创建 RPC context/client，不发 RPC；显式非法值仍属 CLI 输入错误。
- 把 `rpc_url: Option<RedactedRpcUrl>` 与可选预算声明、已解释 hash 一起经现有进程内 ConfirmationSlot 一次性交接（扩为 run context，不另建全局槽/服务）；Run/Tui 在分派前安装，CheckVenue 不领取/不隐式链读。trader 领取后绑定其 deployment.chain_id/trading address/mode；声明不匹配 ACCOUNT_MISMATCH，无声明仍不得取得预算确认。URL 本身不证明账户身份。
- 解析/安装不联网；实际 Predict live account reader 首先 eth_chainId，对56/97精确匹配所选 deployment；错误链 ACCOUNT_MISMATCH/CHAIN_MISMATCH、读失败 READ_UNAVAILABLE，不降级其他 endpoint。query、余额、授权、receipt 都复用同一显式上下文；无第二 API client，无新 provider runtime/依赖。
- URL 类型 Debug/Display 一律 `[REDACTED_RPC_URL]`；CLI parse 错误也不得由 clap 默认 error 把完整值打印出来，保留 String 输入后受控校验；不打印 cli/request/reqwest 原始 error/source。诊断只用稳定 code/step/reason，无 host/path/query/userinfo。无 secret URL 示例。HTTP 禁止自动重定向，RPC 不附 REST API key/JWT/header，禁止底层 HTTP trace 泄漏。
- 逐链逐路由资产/validator 与只读 ABI 精确来源为 Design §3.3.5。EOA gas 读取 signer；已支持的直接 SDK/Privy PredictAccount 路由亦读取 Privy signer 的 BNB，USDT/CTF/allowance/operator 读取 trading_address，不读 Kernel 实现常量的余额充数。此 payer 仅指直接 SDK 链上操作路径，不证明用户承担 matcher 结算 gas，不宣称任意 paymaster/Kernel 版本受支持。
- PredictAccount 启动/运行身份门禁：同一显式 RPC 的 chainId=deployment.chain_id，REST 账户/订单 maker/signer=trading_address，固定 validator 的 isInitialized(trading_address)=true，ecdsaValidatorStorage(trading_address)=非零且等于声明 Privy signer。初始化/owner/账户模式/身份不符 ACCOUNT_MISMATCH，读取失败 READ_UNAVAILABLE；不能退回 EOA。所有账户/资产读项、原风险核对与预算确认仍必须成立。
- 每笔既有 PredictAccount 签名在 POST 前验证：H 是绑定本链所选 exchange 和原订单字段的 EIP-712 hash；既有 Kernel 0.3.1 domain（chainId、verifyingContract=trading_address）包装与 EIP-191 路径不变。签名字节必须为 `0x01 + 固定 ECDSA validator + 65字节签名`、总86字节；在同一已核链固定块对 trading_address 调用 isValidSignature(H,该签名)，严格返回 ERC-1271 magic `0x1626ba7e` 才可继续 POST。格式/validator/返回 magic 不符 ACCOUNT_MISMATCH/SIGNATURE_MISMATCH，缺失/错误读回 READ_UNAVAILABLE；均不发送。仅消费已生成签名，不为启动检查生成新签名，不把签名材料放进诊断。owner/初始化和逐单有效性共同构成支持路由控制检查，不增加 rootValidator/isModuleInstalled 泛化枚举门禁。

上述闭合来源均为[本地官方依据](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/rpc-input-correction/official-basis-resolution.md)所列公开正文快照（URL 非不可变 ref，hash 仅固定内容，不是 wheel 映射）：https://dev.predict.fun/trading/approvals ，SHA256 `84b21b78886c9faf6d86a87fcc61b1b80af747a97f6283e62f58bb7ff4a1a6a1`（Privy payer/资产归属）；https://dev.predict.fun/trading/authentication ，SHA256 `a3db7f4d12ce5bdcce2ff28f4b796f81a02d4cac98ce38aba61684519b731cf5`（owner/未设置账户拒绝）；https://dev.predict.fun/resources/order-signing ，SHA256 `9f0c094bfabdbffbb3c1b2d6225887413f04dc0c6cb4d02573f31425dc716c93`（Kernel0.3.1/ERC-1271/86字节公式）。Design §3.3.5 绑定本地文件与历史源码证据限度。本段是原 A-009/010 的可执行细化，不新增/删减验收项。

### 4.6 SDK 工具的无副作用默认与显式操作

1. 固定依赖 `predict-sdk==0.0.22`，import 为 `predict_sdk`；仅隔离工具环境安装及锁定必要传递/测试依赖。无 Python SDK 的 Rust paper/回放仍可用。默认无执行意图时至多 plan；缺目标返回输入错误，不猜目标或执行。
2. plan 输入明确市场/操作范围，使用官方 `get_approval_steps(scope)` 所需最小信息；不读取 signer/secret、不账户认证、不签名、不 RPC 发交易。不得初始化即运行授权。SDK builder 无 signer 不自动证明具备链上 contracts。
3. check 使用显式 owner、同链只读 contracts/RPC 上下文，读回 allowance/operator 等状态；缺条件返回 `READ_UNAVAILABLE`，不把不可检查当 false/0 或自动加载私钥。默认无 signer。当前所有业务验证只使用无网 fake，不进行真实 RPC/账户查询。
4. approve/redeem 是显式能力，不是 plan/check 的 fallback。要求明确执行意图、具体目标和匹配账户；缺任一项在签名/发送前拒绝。当前实际执行仍未授权，只用 fake 证明调用/拒绝顺序；研发批准和安装不充当资金动作批准。
5. ERC20 授权输入必须显式 token、spender 和有限正额度（带单位/decimals）；不静默 `MAX_UINT256`、不默认全 scope。已充足可返回 no-op，不能扩大 allowance。ERC1155 是 operator 布尔权限，不存在金额封顶；必须单列具体 operator、权限含义和显式同意，不能伪装成与 ERC20 相同的有限金额操作。
6. redeem 需明确已结算的 condition、index_set、amount、NegRisk/yield-bearing 路由以及持仓/结算依据。合法标准/NegRisk/yield-bearing/DRAW 按官方 SDK/市场事实处理；不自行编造 DRAW 兑付算法、不默认全余额或自动遍历其他市场。非法/未结算/身份或数量不符先拒绝。
7. 签名只证明签名，tx hash 只证明提交标识；receipt 成功还需同目标资金/份额读回才能标 completed。approve 读回 allowance/operator，redeem 读回归属明确的份额扣减和资金到账。receipt pending/revert/丢失、或到账不可核对分别报告，保留 hash，不自动重签/广播；receipt 成功但到账不明仍 `TX_UNCONFIRMED`/待核对，而非成功到账。
8. 复用官方 `make(chain_id, signer, options)`、`get_approval_steps(scope)`、`check_approvals(steps)`、`set_approval(step, approved, amount)`、`redeem_positions(condition_id, index_set, amount, is_neg_risk, is_yield_bearing)` 的已知方法方向；这是此前 v0.0.22 文本参数名证据，不是返回结构或运行行为证明。只读 contracts 适配可复用官方 ABI/地址，不自行实现资金交易协议。具体 SDK 返回映射留 T2/T3 验证，不兼容报错，不能默认 HEAD 等于发行包。

### 4.7 兼容性与证据输出

Predict.fun 真实 BTC5m consumer 必须直接消费新语义，禁止保留未知 `unwrap_or(requested)` 或用 limit/模型费记实绩的旁路。copy 的 Predict.fun 未知满额分支同样失效；其他 venue 的历史回执语义只做必要兼容，不借共享类型迁移重构策略。paper 继续原撮合/模型费用，输出标 paper 而非官方事实。

运行期诊断须能关联账户模式、market/token、order ID/hash、已确认量/金额、核算完整性、未闭合预算/阻断原因、数据来源/时间；SDK 结果分计划/签名/提交/receipt/读回。私钥、认证 token、签名材料不输出，测试 fixture 明确是假数据，不能伪造真实回执证据。

## 4.bis 持久化契约

无新增生产持久化需求、库/集合/schema/索引/TTL 或迁移。订单关联、去重及预算留在现有进程状态，复用脱敏诊断与官方事实，不承诺跨进程恢复。重启按 §4.5 阻断，不能以日志代可靠主账。

| 对象 | 记录内容 | 生命周期 / 隐私 |
|---|---|---|
| 本主题 `data/tasks/active/2026-11-13-predictfun-live-foundation/` | 阶段、changed_files、真实命令/结果引用、限制 | 主控完成后整目录移 done；不自动删除或复制既有证据；无凭据/私密账户数据 |
| 后续 `data/reports/2026-11-13-predictfun-live-foundation/` 及 evidence | 版本/来源、离线输出、验收项状态与未执行项 | 只追加实际结果；归档不是验收通过或远程备份；公开事实与账户最小脱敏诊断分开 |
| 现有进程状态/脱敏日志 | 订单/tx 关联和核对诊断 | 非新增持久化接口；不新增自动清理/恢复机制，不记录 secret/认证材料 |

本 T1 不创建上述报告目录或业务日志；不更改 `data/` 忽略规则，无生产 schema 回滚事项。

## 5. 验收标准

矩阵是后续 Implement/Verify 的要求，不是 T1 已运行结果。所有数字向量均为无网合成 fixture，金额单位为 fixture 抵押币，不冒充真实账户币种。

| 编号 | 输入/场景 | 必须观察到的输出或错误 | 验证方式 |
|---|---|---|---|
| A-001 | 固定发行依赖及不存在 SDK 的 Rust 环境 | 工具直接 import 0.0.22，锁制品/传递依赖；Rust paper/回放不要求 SDK/密钥 | 隔离依赖身份/API 验证 + 无钱包回归，T1 不安装 |
| A-002 | 无执行意图的默认/plan；check 无 signer；缺 owner/contracts/RPC | 签名/发送调用计数均 0；计划正确；check 缺上下文报 READ_UNAVAILABLE 而非零/自动读 key | SDK 实际可用纯路径及工具 fake 调用计数；secret 访问使用会报错的 fake |
| A-003 | BUY 请求 10 份；权威终态零；对照 accepted 无 fills/open 零 | 前者零增量、VWAP 不适用、释放未成交占用；后者 unknown/未闭合，保留预留并阻断新增 | adapter + 实际 Broker::take fixture，不仅测 copy |
| A-004 | BUY 请求 10；先确认 4@0.40，后 6@0.50；额外抵押币费 0.02、份额费 0.1，均明确未净额 | 首次 Q=4/C=1.60/VWAP=0.40；最终 Q=10/C=4.60/VWAP=0.46，现金支出 4.62、净份额 9.9；不以 limit/请求份额记实绩 | BTC5m adapter→Broker 端到端 fake；SELL 按官方映射另测净收入/库存扣减 |
| A-005 | A-004 成交重复/轮询并发，旧快照后到，累计量不变后费用补齐；另给矛盾累计减少 | 每项事实只应用一次；旧快照无回退，费用补齐不重复份额；冲突报 RECONCILIATION_REQUIRED；中间未闭合预算无提前释放/双算 | 增量/累计/并发定向测试 |
| A-006 | 部分终态、全额量但缺费用/金额、未知净份额、非法 NaN/负值/币种冲突 | 终态完整部分仅记部分并释放权威余量；不完整不报完整实绩/可卖量；错误阻断且不造零/满额 | 解析/记账/Broker 拒绝路径；区分数量与核算完整性 |
| A-007 | 已签 hash 后提交超时/响应损坏，无 order ID；随后仍查不到/恢复出现成交 | 始终保留原 hash/预留；相关新单被拒，同订单查询可用；恢复仅记新事实；提交调用至多初始一次，无新 salt/自动重发 | 假传输与实际 consumer 连续 tick 测试；copy Predict.fun 同样不满额 |
| A-008 | remove 成功后 late partial fill，随后查询失败/仍可成交，最后权威终态并完整对账 | removing 期间占用/阻断保留，late fill 一次入账；仅最后按事实释放未成交余量 | 现有 remove/order_state 的竞争序列 fixture |
| A-009 | 余额/持仓/授权/gas/订单读取失败；持仓多页/缺页/游标循环/触顶；对照完整空账户、链/地址/模式不符 | 失败不变零；保留原风险且拒绝新增；完整空结果才 known zero；身份不符 ACCOUNT_MISMATCH；分页上限保留 | 启动与运行期账户 fake、分页/限额回归 |
| A-010 | 重启空内存但存在未解释订单/旧预算，无人工新预算确认 | 不允许新单，不声称自动恢复；已解释且人工确认后才可按原限额继续 | 无网重启入口/确认条件测试，不新增持久服务 |
| A-011 | approve/redeem 缺执行意图/目标；ERC20 缺额度/无限额、ERC1155 无明确 operator 同意；非法/未结算 redeem；对照合法路由 | 非法在签名/发送前拒绝；合法 fake 仅目标 scope/有限 ERC20 额度，operator 权限单列；标准/NegRisk/yield-bearing/DRAW 不错路由 | 工具 fake SDK 参数/调用顺序及默认拒绝，真实操作 0 |
| A-012 | tx hash 已有但 receipt pending/revert；receipt 成功但 allowance/份额/资金读回失败；最后同目标可确认 | 不报 completed/到账成功、不重发；保留步骤/hash/待核对；只有 receipt 与匹配读回完整才 completed | 工具 receipt/readback fake；脱敏检查 + 原 paper/模型/其他 venue 必要回归 |

## 6. 测试要求

- 单元：解析单位/非法输入、四类数量/核算状态、去重/累计补齐、预算转换、分页错误、SDK 纯计划与拒绝顺序；Rust colocated，Python 测试归工具目录，不放主仓模块单测。
- 集成：以实际 BTC5m Broker 消费链驱动 fake venue/传输/账户；至少覆盖 A-003–A-009 连续状态变化与后续新增拒绝。只测试新 helper、只跑 copy 或只编译均不足。
- 回归：原无钱包 paper、DecisionCore/历史回放、既有风控/分页，以及共享回执直接消费者编译兼容；不启动新 paper 进程，不重跑 94 日研究/6h 观察，不改模型/资金参数求通过。
- 后续 SDK 验证必须记录实际制品版本/API/真实输出；fake 是工具行为证明，不证明链上真实兼容。固定公开无资金测试向量可在获准隔离环境本地离线签名对拍，绝不真实密钥/广播。
- 真实账户认证/私有查询、真实成交/费用/赎回/到账、公开无签名 smoke 均不在本轮业务验证范围；以后按具体授权执行并单列未执行。无“首次真实下单前必须先有真实成交”的循环验收。
- T1 仅本地文档静态契约/链接/范围/空白检查，不运行上述测试、SDK 或业务命令；T2 给出精确可执行验证命令，Verify 由独立角色真实重跑，不把未跑项写 PASS。

## 7. 实现约束

- 本轮来源为 [Intake](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/intake.md) 与 RFC V1.1；旧 [07-001](../../spec/07_trading/SPEC-07-001-predictfun-btc5m.md) 签收不重写，旧禁令不覆盖本轮明确新增研发授权。
- SDK 证据以[恢复输出](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/evidence/sdk-release-prior-output.md) 的级别引用：只证实此前 v0.0.22 ref 的同步方法/参数名，未证实返回结构、制品行为或 tag→commit 映射。HEAD `55381bfed02323c5edbc6eed0f5c603ae84172ef` 不标发行版；Intake 的 `6da1708e1f3a9341f5cfd8d0b91bb66c8f43bef1` 仅主控既有记录。
- 不重做被拒的 tag 网络动作，不变更审批/工具/命令/委派绕过。T1 不联网/安装/SDK/测试；后续只在已核 Design 与 Intake 授权内隔离验证。不能满足契约时保留真实错误，报告具体不兼容，不静默替换版本。
- runtime/predict_fun 大文件按现有 G3 在 T2 交代职责边界、增长与拆分触发，新增主体放 helper；不借机全仓重构。保持查询/分页有界、单笔/轮次/总敞口/亏损保护，不新设资金或性能门槛。
- 禁止读取交易 secret/继承密钥，不真实登录/账户签名/私有 API/场馆模拟或真实订单/链上资金动作/生产数据库读写。凭据不进命令行、Git、日志、测试或交接。真实试运行、首单和资金动作必须以后明确授权。
- 禁改其他项目/Hermes/profile/model/provider/审批/服务/代理/cron/systemd/webhook；禁 git reset/stash/clean/checkout/add/commit/push/gitlink 更新、证据覆盖/删除及共享环境升级。必要 Python 仅项目 `.venv/bin/python` 或后续批准的工具解释器；临时文件仅 profile scratch/本主题 evidence，不用 `/tmp`，不用无人值守 execute_code。

## 8. 开放问题

需求层无待猜的关键语义。本阶段不声称 SDK 发行包及账户运行行为已证实；T2 精确映射字段、SDK contracts 上下文、直接消费者、错误承载和人工预算确认入口，T3/T4 以实际隔离制品与无网测试判定能否满足上文契约。无法满足时具体报 FAIL/阻断，不用 unknown 降级绕过必须验证的拒绝/预算行为。以后未授权的真实动作仅列残余未执行，不构成本次 T1 失败。

V1.1 的 run3669 来源阻断已在本次限定的官方直接 SDK/Privy 路由内闭合；不再以 PREDICT_ACCOUNT_GAS_PAYER_UNPROVEN / PREDICT_ACCOUNT_CONTROL_ROUTE_UNPROVEN 永久拒绝此已支持模式。泛化代付/模块版本不是必需新门禁；真实读失败与控制/签名不符仍具体拒绝。现有 reader 的 MISSING_READ_CONTEXT 仍为未完成代码，不因本文存在而变为已实现；adapter→Broker/G3/独立验收继续待完成，见[窄修订交接](../../../data/tasks/active/2026-11-13-predictfun-live-foundation/rpc-input-correction-handoff.md)追加闭合记录。当前无必需输入未决项，主控 Gate 与真实账户验证/授权不由本卡替代。

## 版本记录

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-11-13 | 从 RFC-07-002 派生成交/预算/账户/SDK 最小可测试契约与 A-001–A-012 矩阵 | YQuant Principal |
| V1.1 | 2026-11-13 | 显式 RPC 参数/凭据前解析/进程内传递/URL 脱敏；官方直接 SDK/Privy gas地址、owner/初始化/逐单ERC-1271谓词闭合；原 A-001–A-012 不变，待主控 Gate | YQuant Principal |
