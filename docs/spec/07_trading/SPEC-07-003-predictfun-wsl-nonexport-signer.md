# SPEC-07-003: Predict.fun WSL 原生非导出 signer

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft；ROI / 必要复用接口阻塞，不是 Accepted / Implemented |
| 作者 | YQuant Principal |
| 创建日期 | 2026-11-15 |
| 最后更新 | 2026-11-15（Asia/Shanghai，UTC+08:00） |
| 来源 RFC | [RFC-07-003](../../rfc/07_trading/RFC-07-003-predictfun-wsl-nonexport-signer.md) V0.1 |
| 目标模块 | 07_trading；唯一现有 Toolkits 子仓 |
| 适配 Agent | yquantdeveloper；独立验收 yquantreviewer；编排 yquant |
| 文档边界 | 冻结行为/拒绝/验收；§8 阻塞闭合前不得派发实现 |

## 1. 需求摘要

为现有 Predict.fun executor 提供显式账户绑定的 Privy 非导出签名选择，不替换策略、风险、订单构造或 venue client。外部模式不读取本地私钥或占位私钥，允许持久凭据只进 WSL Secret Service，短期授权签名密钥只在内存。仅 Predict 认证消息与原风控通过的订单能够签名；任意 RPC、交易发送、重复签单及重复提交都不开放。当前测试目标仅离线/合成实现，不操作任何真实账户；原 CLI 无可直接使用的安全 signer 导出，所需认证适配超过原小改假设，故实现路线/预算和必要库接口明确阻塞；初始交互登录/provisioning 则明确不在本次实现范围。

## 2. 范围

### 2.1 In Scope

- Local / Privy 选择和公开地址/链/模式绑定；保留 Local、无钱包 paper、07-002 的账户和执行语义。
- executor 私有 typed action、精确 EIP-191/EIP-712 编码、签名响应验证和原 consumer 接线。
- Secret Service-only 的精确 slot 访问、失败关闭、序列化 token 轮换、只内存授权密钥生命周期与不确定结果阻断。
- 使用真实待实现 seams 的 synthetic transport / store / clock / synthetic local signer 测试；保留独立 Validate。

### 2.2 Out of Scope

无新 bot/CLOB/钱包服务/HTTP daemon/Windows bridge/DB/调度/通用钱包 CLI；不改模型、资金阈值、策略、订单协议、成交或恢复主账。不增加 funds/approve/redeem/sendTransaction 等动作。不运行真实 device grant、token refresh、wallet authenticate/RPC、Predict JWT 登录/订单、私钥读写或 keyring 凭据操作；不读取共享 `.env` 或 CLI session。不把仅 fake trait 成功当成完整可用的 Privy signer。

`BOT=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。本阶段只创建本文件和来源 RFC。后续代码仍只能在同 BOT：候选新逻辑位置为 `src/service/predict_fun/signer.rs`；既有必要消费者为 `src/service/predict_fun.rs`、`src/service/predict_fun/fills.rs`，装配涉及 `src/config.rs`、`src/main.rs` 及实际构造调用者 `src/bot/runtime.rs`、`src/bot/copy_trading.rs`、既有 check 路径。此处不是最终 allowlist；Design 须按批准复用路线逐文件冻结，不能把代码丢进第二工程或继续堆进大父文件。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | 显式模式装配 | Local / Privy 与公开绑定 | 唯一绑定 signer | Privy 缺字段/失败不回退；不读本地 key，不伪造 dummy |
| F-002 | 严格绑定 | app/wallet/slot/signer/chain/账户模式 | 与原 AccountIdentity 一致的上下文 | 不取第一个 Ethereum wallet；任何失配拒绝 |
| F-003 | 有来源的认证签名 | 原 client 的 auth challenge | 内部 EIP-191 或原 Kernel 包装签名 | 无任意消息入口，无默认 check/paper 远程签名 |
| F-004 | 原订单签名 | 原 Order、deployment、market、原风险许可 | 原 EIP-712 hash 和内部签名字节 | 无通用 hash/typed-data API；字段/域/许可失配先拒绝 |
| F-005 | 安全存储 | 精确自有 slot，元数据 | 已验证记录/错误 | 无 Prompt、无 fallback、无 broad search/自动迁移 |
| F-006 | 只内存密钥 | 官方 authenticate 响应，HPKE 临时密钥 | 有明确到期时间的内存 authorization key | 禁止持久化完整 CLI session；缺 expiry 拒绝 |
| F-007 | 序列化轮换 | 单 slot 独占权、旧 refresh token | 写后读回成功的新持久会话，再发布内存会话 | 响应丢失/保存失败进入不确定停止，不重用旧 token |
| F-008 | 严格响应验证 | provider 返回和原签名上下文 | 验证后的签名或稳定错误 | 错 method/encoding/长度/恢复账户均不交 consumer |
| F-009 | 不重放与阻断 | refresh/签名/提交故障及原 attempt | 拒绝新增，原风险/查询路径保留 | 401 也不自动重签/重播；不重新生成 salt |
| F-010 | 离线可验证性 | 注入 fake store/transport/clock、公开合成 key | 实装路径可观察调用与反例 | 不能由历史 bypass 或预造结果绕过新 seam |
| F-011 | 兼容与范围 | 原 Local / paper / 07-002 consumers | 原签名/风险/成交行为 | 不重开已验收能力，不增加本卡未批依赖/平台 |

## 4. 数据与接口契约

以下为拟新增逻辑类型和必须行为，不声称本树已有同名实现。内部函数排布和 CLI flag 的具体装配由后续 Design 冻结；不得改变数据语义、方法集合或失败边界。

### 4.1 模式、账户与凭据装配

`SignerSelection = Local | Privy(SignerBinding)`；未显式选择保持 Local，供现有调用兼容。Privy 不可由“private_key 为空”隐式推断。

| 字段 | 类型 / 约束 |
|---|---|
| app_id | 显式非空公开 app ID，不从任意环境覆盖到其他 app |
| wallet_id | 显式 Privy wallet ID，不是地址，不通过列表位置猜测 |
| credential_slot | 非秘密稳定 slot 引用；同一 refresh grant 只能有一个活跃 slot，不为每个 chain 复制 token |
| signer_address | 20 字节非零 EVM 地址；输入须先合法解析，再以地址字节比较；不得修正非法原 token |
| chain_id | 与原 deployment 一致，仅原支持的 56 / 97；不是自动网络切换许可 |
| account_mode | Eoa / PredictAccount，使用原含义 |
| trading_address | EOA 等于 signer；PredictAccount 为显式账户地址，不得默认候选 EOA 为 smart account |

候选 `0x2FcDbb1a61f4A0439C9952710eDCe3cee071828c` 只是供未来明确选择的公址，不硬编码为默认或成功身份。`authenticate.wallets` 必须按指定 id 唯一找到 `chain_type=ethereum` 且 address 完全匹配；缺失、重复或地址变化即拒绝。Ethereum wallet 的 chain_type 不证明 provider 实际支持 BNB；本次仅用 fixture 验证上下文绑定。

外部模式须在遗留凭据加载前分流：不打开包含本地私钥的 legacy credentials YAML，不读取 `PM_PRIVATE_KEY`，不创建 PrivateKeySigner，不通过空/合成 key 先构造再替换。非秘密 public config 可沿用；外部所需 Predict API key 来自精确独立 keyring 条目，Privy refresh token 来自本 slot。禁止让外部模式沿用 `AppConfig::load` 全读私钥再忽略；当前 `config.rs:596–649` 正存在这条风险接缝。Local 的现有 loader 和其他 venue 行为不在本次重新治理范围。

原 `AccountIdentity`、RunContext、人工预算确认、链/owner/初始化/ERC-1271、分页、余额/gas/授权/持仓核对不变。公开 signer 选择不等于新预算确认或账户健康。

### 4.2 能力与调用顺序

executor 私有动作仅两种：

- `PredictAuth { binding, challenge }`：challenge 只能由原 Predict client 的固定官方 `/auth/message` 响应产生，且消费于原 `/auth`。本地观测时间与使用相隔不得达到官方 10 分钟期限；这只是防本地缓存过旧，不冒充服务端消息时间戳验证。空消息、来源不符、过期/重用到其他绑定均拒绝。原消息包含 ToS，依旧仅 live 或显式 sign-in 路径允许请求认证签名。
- `PredictOrder { binding, order, market_route, attempt_context }`：Order 必须由原 builder 构造并与原 market/token/side/amounts/expiration 等约束一致；有原风险许可、预留与账户门禁的关联，不能把可伪造的 `approved=true` 当许可。公有接口不得让 Hermes 传任意 JSON/digest 制造该动作。

拒绝顺序：公开输入/模式 → 账户/链/动作/许可验证 → backend/slot 独占及会话有效性 → 生成唯一允许的 provider payload → 一次签名请求 → 严格核验 → 原 consumer。订单继续原 `check_allows_new_order / begin_attempt / check_signed_bound` 等 gate，不以 signer 自建第二风控。认证用于原账户读取的前提，不机械要求“先完成全部已认证账户读取才能获得 JWT”而造成循环。

外部模式普通 `check-venue` 和 paper 不请求远程 order/auth 签名、也不因检查构造 synthetic 私钥；显式 `--sign-in` 的原语义保留但本流水线不实际执行。现有 `predict_fun.rs:1713` 的非 live sample place 会签本地示例订单，故后续必须区分 Local 与 Privy，不能未经许可对真实 wallet 调用 sample signer。只改外部模式，不取消原 Local 离线签名检查。

### 4.3 精确签名编码

所有 `||` 表示字节拼接。`M` 是挑战字符串的原始 UTF-8 字节：不 trim、不 Unicode normalization、不改换行、不先转 hex 文本再当消息。`H`、`K`、domainSeparator 均为 32 字节，不是其 66 字符显示字符串。

| 路由 | 交给 Privy 的动作 | 要验证的摘要与结果 |
|---|---|---|
| EOA 认证 | `personal_sign`，params.message 为原 UTF-8 字符串，encoding=`utf-8` | EIP-191：`keccak256(0x19 || UTF8("Ethereum Signed Message:\n") || ASCII(decimal(len(M))) || M)`；只加一次前缀 |
| EOA 订单 | `eth_signTypedData_v4`，params.typed_data 为原 Order 的完整结构 | `H=keccak256(0x1901 || domainSeparator || structHash(Order))`，等于原 `order_digest`；不得对 H 再 EIP-191 |
| PredictAccount 认证 | 先以 M 求上述 EIP-191 得 H，再按下述 Kernel 包装得 K；`personal_sign` 对 K 的原始 32 字节 | params.message=`0x` + K 的64位hex，encoding=`hex`；provider EIP-191 后恢复 owner；外层包装仍原86字节 |
| PredictAccount 订单 | 原订单 EIP-712 得 H，再按下述 Kernel 包装得 K；同样 `personal_sign` 原始32字节 | encoding=`hex`，不能 encoding=`utf-8` 签 hex 文本；不能再预加一次 EIP-191 |

Kernel 包装完全沿用既有 `sign_for_account`：`wrapped=keccak256(abi.encode(keccak256("Kernel(bytes32 hash)"),H))`；`K=keccak256(0x1901 || KernelDomainSeparator || wrapped)`。Kernel domain 精确为 name=`Kernel`、version=`0.3.1`、chainId=绑定链、verifyingContract=trading_address。provider 返回 owner 的 65 字节签名后，原 executor 拼接 `0x01 || 20字节validator || signature`，validator=`0x845ADb2C711129d4f3966735eD98a9F09fC4cE57`，总86字节。订单 POST 前仍以原 H 和此签名执行原 ERC-1271 门禁。

EOA EIP-191 认证本身不含 chain/domain；chain 只能由执行上下文、wallet 选择和原账户检查约束，不得宣称其具有密码学链隔离。EOA 订单与 Kernel 签名才由各自 domain 纳入 chain/account。

订单 domain 精确为 name=`predict.fun CTF Exchange`、version=`1`、chainId=原 deployment、verifyingContract=原 `deployment.exchange(is_neg_risk,is_yield_bearing)`；不另抄新地址表。Order 类型和字段顺序完全沿 `predict_fun.rs:63–76`：`Order(uint256 salt,address maker,address signer,address taker,uint256 tokenId,uint256 makerAmount,uint256 takerAmount,uint256 expiration,uint256 nonce,uint256 feeRateBps,uint8 side,uint8 signatureType)`。maker/signer=trading_address，taker=原构造值（当前零地址），signatureType=原0；所有数值/精度/金额仍由原 builder 决定。typed_data.primary_type=`Order`；uint256 用精确十进制字符串，uint8 用合法整数，domain.chainId 用精确整数，types 明确 EIP712Domain 与 Order，不经过 JS 不安全浮点转化。每个字段、顺序和 domain 以原 Alloy hash 对拍，不重新实现交易定价/金额算法。

公开官方 fixture 的 Order hash 为 `0xe6a0edf257e9904e5fd4a1b8fdc3dd092e8789c4fa596ff6275097515ee4fd34`；测试必须用官方所列全部原字段重新计算，不硬编码该 hash 当测试通过。

### 4.4 官方传输与签名结果

- Agent Authorization 使用 `https://auth.privy.io/api/oauth/v2/token`（refresh grant）、`/wallets/authenticate`（短期 key）、`/wallets/{指定wallet_id}/rpc`；其完整前缀均为 `/api/oauth/v2`。wallet ID 必须合法且安全编码，不能含路径注入。禁止用户传任意 base URL/headers/method 来扩权，不跟随重定向，不发送 app secret，不拿 server-wallet Basic 示例替代 bearer device grant。
- 只发 `personal_sign` / `eth_signTypedData_v4`；不暴露 `secp256k1_sign`、transaction/user-op/7702/send 类方法。provider 的 general API 支持这些方法不是本 executor 的许可。
- RPC 使用 `privy-app-id`、`privy-grant-type: device_code`、Bearer access token、`privy-authorization-signature`，全部只在 executor 内。请求签名覆盖完整固定 URL、HTTP method、确切 body 和该 device-grant 协议要求的 headers；固定 CLI 中的 payload 只包含 app-id，不能未经对拍就套用通用 API 文档任意增减 header。B-002 要求在实现放行前固定这一映射。
- Privy 请求授权签名与钱包 EIP 签名不同：按 RFC 8785 canonicalize 结构化请求，以 P-256 / SHA-256 产生 DER ECDSA 签名再 base64；不是 secp256k1、Keccak 或 EIP-191。固定 CLI 用 Node crypto PKCS8/SPKI、HPKE 库与 canonicalize；其细节不是 Rust 现成可调用 SDK。HPKE 算法 suite、info/AAD、密钥封装格式及库对拍仍属 B-002，不可自己猜测或手写加密原语。
- 结果仅接纳对象中 `method` 与请求一致、`data.encoding=hex`、`data.signature` 是 `0x` 前缀且严格65字节 r/s/v；r/s 有效、低 s、v=27或28，并恢复到绑定 signer。其他 encoding、扁平兜底 `signature`、缺字段或把整个 JSON 字符串当签名均拒绝。不同官方响应若与该固定形状不兼容，应明确停下来修订协议，不效仿 CLI 的宽松 fallback。
- Kernel 包装前验证 owner 的65字节签名；包装后本地长度/validator 及原 ERC-1271 检查不变。签名只送原内部 consumer，不通过模型/命令 stdout、普通日志、报告或 Kanban 返回。
- provider 请求最多一次；401、403、5xx、断连、响应损坏、超时均不在同调用自动刷新后重放。可在请求前主动完成一次必要续期；收到401后使会话不可用并结束本动作，后续经明确恢复才允许新的合法动作，不复用失败动作自动重签。

通用官方 RPC schema 是类型/编码来源，不构成已证明 device-grant 在 BNB/该钱包上成功的证据。B-002 不闭合时不能用 fake HTTP 结果冒充该协议已实际兼容。

### 4.5 会话与安全轮换

逻辑状态为 `Unavailable → Ready → Renewing → Ready`，任何不明确远端/本地更新进入 `RenewalUncertain`，密钥到期或授权拒绝进入 `ReauthorizationRequired`。无静默“仍可用”状态。

1. 同 slot 使用一个存活期 OS 独占锁，内部 renewal/authorization-key 更新单通道串行；后续实现须证明第二 executor 拒绝 `SESSION_IN_USE`。锁只保护合规消费者，不防同 UID 恶意进程/其他 CLI。禁止运行原 CLI 共享同一 grant；不得声称 Keyring 是跨进程 compare-and-swap token 服务。
2. 每次使用前确认 backend 仍可用/解锁，且 access token 与 authorization key 未过期；正在 Renewing 不接新签名。缺少有效到期时间即拒绝。clock 在测试中可注入，不依赖真实睡眠；具体提前续期裕量由 Design 明确且不延长官方 expiry。
3. refresh 使用旧 refresh token，一次请求。远端响应合法后，先检查 app/slot/绑定和新 token/expiry，再以一个 Secret Service item 更新 §4.bis 允许字段；由独立读取精确核对新 generation/绑定/token，再发布 access token。后续 HPKE authenticate 得到的 key 只在内存，authenticate 失败不把 key 加入持久 item。
4. 即使只更新 authorization key 而 refresh token 未变化，也不允许把它序列化到 keyring。退出/过期丢弃旧内存密钥，尽可能减少副本；不宣称 GC/OS swap/core dump 下绝对物理清零。后续选择具体语言/库时必须说明密钥内存和 crash-dump 边界，不能以“non-export”掩盖本地短期授权密钥存在。
5. refresh 响应丢失、写入失败、精确读回失败或更新中取消：不发签名、不发布新会话、不回退旧 token、不自动重复 refresh，不删真实记录试图重来；记录无秘密的失败类别并停止该 slot。新 token 已保存而读取失败可能仍可在以后人工恢复，不能自动猜测哪一代有效。
6. 崩溃窗口：远端接收旧 refresh token 后、本地新记录提交前，重启只能读到失效旧 token，需要以后重新授权；写成后发布前，重启可从已提交记录开始正常续期但必须重新建立只内存 key，并仍经过 07-002 的对账/新运行预算。不存在远端/Keyring 原子事务或完整跨重启恢复保证。
7. backend 锁定/缺失/失配即使还有未过期内存 key，也停止新签名；不自动调用 unlock/Prompt/重启 backend。撤销 refresh grant 后已有 access JWT 可能仍有效到自然到期（官方文档最长15分钟），不得保证立即远程失效；本地停止必须即时拒绝后续动作。

### 4.6 错误、风险与恢复契约

内部错误逻辑字段为 `code, step, reason, action_ref?`；外层映射到现有 `VenueError` 和 AccountGate，不在共享类型增加一套不相关交易状态机。下表 code 为新 seam 的稳定语义，不假称当前 enum 已存在。

| code | 触发 | 必须行为 |
|---|---|---|
| INVALID_INPUT | 缺 mode 关联字段、坏地址/wallet ID、非法payload/unsupported action | 在 provider/secret 使用前拒绝；无输入回显 |
| ACCOUNT_MISMATCH | app/wallet/address/chain/mode/domain/order 绑定不符 | 阻断账户新增；不换钱包/链/本地 key |
| BACKEND_UNAVAILABLE | bus/owner/collection 错误、locked/missing/需Prompt | 不解锁/不文件 fallback，即使内存 key 未过期也不签 |
| STORAGE_FAILURE | 写入或精确读回失败/重复条目 | 不发布新会话；轮换已可能发生则 RenewalUncertain |
| SESSION_IN_USE | 同 slot 已有执行器 | 拒绝第二实例，不并行 refresh |
| RENEWAL_FAILED | 到期、拒绝、超时、HPKE/密钥格式错误 | 停新签名；refresh 可能发生则不重试，需恢复/重新授权 |
| SIGNER_UNAVAILABLE | 远端拒绝、无有效 key/签名服务不可用 | 停止本动作及新增，不调用 Local |
| INVALID_SIGNATURE | 响应形状/encoding/长度/r/s/v/恢复地址不符 | 不交原 consumer、不 POST |
| SIGNING_UNKNOWN | RPC 可能已处理但没有可验证结果 | 本动作至多一次调用，禁止自动重签/自动下一tick换salt |

步骤/原因只用稳定 token，不透传 HTTP body、request、headers、URL、raw exception/source 或 stdout/stderr。日志只可含 code/step/公开 action_ref/脱敏模式；不得含 token、API key、authorization key、签名及其完整请求载荷。

签名状态不明不自动等价于订单已发送：若原 handle 仍 Prepared 且可证明未 POST，沿原契约处理预留，但必须阻断同一意图的自动重签；一旦 MayHaveSubmitted，保留原 hash/预算和查询链，不能由 signer 错误清掉旧未解释风险。恢复只允许原查询/对账及已有撤单流程；其认证签名同样受 signer 可用性限制，不声称离线 signer 故障时一定还能私有查询。不得为了“恢复”创建新交易或 re-sign 原失败请求。

## 4.bis 持久化契约

仅选 Secret Service login 集合；不创建生产 DB/schema/表/索引/TTL，不读写 `.privy/session.json`，不建替代 secrets 文件。以下为该集成的 L0/L1/L3 说明，不改变全局隐私分类。

| 存储对象 | 字段/属性 | 类型 | 必填 | 规则 | 生命周期 | 隐私 |
|---|---|---|---|---|---|---|
| Secret Service item attributes | service | string | 是 | `yquant.predictfun.privy.v1` | 随显式 slot | L0 |
| 同上 | app_id | string | 是 | 与 SignerBinding 一致 | 同 slot | L1 |
| 同上 | credential_slot | string | 是 | 一个 refresh grant 一个 slot，不复制跨链条目 | 同 slot | L1 |
| 上述 item secret 内 JSON | schema_version | integer | 是 | 1；未知版本拒绝，不自动迁移 | 同 slot | L0 |
| 同上 | app_id | string | 是 | 同属性/运行绑定；防错误条目 | 同 slot | L1 |
| 同上 | credential_slot | string | 是 | 同属性/运行绑定 | 同 slot | L1 |
| 同上 | wallet_id | string | 是 | 仅本次显式钱包，不接受列表首项 | 同 slot | L1 |
| 同上 | signer_address | string | 是 | 合法地址的规范化字节对应小写hex | 同 slot | L1 |
| 同上 | chain_id | integer | 是 | 与批准绑定一致，不充当 refresh grant 的另一个复制 key | 同 slot | L0 |
| 同上 | account_mode | enum | 是 | eoa / predict-account | 同 slot | L0 |
| 同上 | trading_address | string | 是 | 与批准绑定一致 | 同 slot | L1 |
| 同上 | refresh_token | secret string | 是 | 仅执行器内；不得日志/hash回报；无空值/占位 | refresh 后替换；未来显式撤销/删除才清理 | L3，特批 OS store 持久字段 |
| 同上 | generation | unsigned integer | 是 | 成功轮换递增；不是跨进程CAS保证 | 同 slot | L0 |
| 独立 Secret Service item | Predict API key | secret string | mainnet需要时 | service=`yquant.predictfun.api.v1`，精确 app_id/slot/chain 属性，禁止发往 Privy | 未来另批 provisioning，轮换显式执行 | L3 |

以下字段永远不属于持久序列化允许集合：access_token、JWT、authorization_key、authorization_key_expires_at 所关联密钥对象、HPKE 私钥、device_code、钱包主私钥、签名字节、CLI session 原始对象。未知 secret JSON 字段拒绝，不能宽松 deserialize 完再 serialize 回整对象。可保留内存 expiry 但不能为方便恢复保存密钥。

精确访问顺序：检查本会话 `org.freedesktop.secrets` owner/collection 元数据 → default 指向 login 且 unlocked → 仅用上述三个属性精确搜索 → 要求唯一、自有、集合正确 → 读取；写入要求非交互 API，拒绝任何 Prompt 返回，随后独立读取并在内存逐字节核验。不能用“先 metadata 检查，再允许 secret-tool 自动解锁”的竞态路径承诺无 Prompt；选定库/API 必须能在操作时拒绝交互。具体实现依赖属 B-002；当前不安装/不操作真实 backend。

新记录只能由以后明确获准的 provisioning 创建；不存在自动首次登录、从 CLI session 导入或从聊天 token 初始化。本流水线仅 synthetic fake store/transport 验证生产实现的上述逻辑；不要求重跑真实已证明的 WSL 读写基线。删除/清理只允许具体授权的自有条目；不批量扫描、清理其他记录，不自动备份/恢复 token，不将 local-mode 凭据迁移为新模式。

## 5. 验收标准

下表全为后续 Implement/独立 Validate 必须实际运行的离线要求，不是当前通过记录。原生依赖/API/安全存储对拍的未决项必须先闭合，不能以行为 fixture 绕过。

| 编号 | 场景 | 必须观察到的结果 | 验证方式 |
|---|---|---|---|
| A-001 | Privy 明确模式，无真实/占位 local key；对照 Local | 外部 loader 不访问 legacy key 文件/PM_PRIVATE_KEY、不构造 PrivateKeySigner；Local 原行为保持 | 实际配置/constructor consumer；禁止访问即失败的 secret-loader spy，不能仅把已读 key 清空 |
| A-002 | app/wallet ID/链/地址/账户模式错配、重复wallet；EOA vs PredictAccount | 全部在 provider 签名前拒绝；不取第一个钱包，不降级 | 实际 binding validator + authenticate fixture + signer构造路径 |
| A-003 | EOA auth：ASCII、中文、换行；对照签hex文本/双前缀 | UTF-8字节与EIP-191恢复正确；错误编码签名被拒；消息仍原字节 | 真 auth签名seam + synthetic local signer；假 REST challenge → 原 sign_in body构造，网络/JWT登录0 |
| A-004 | EOA Order 官方向量；chain/exchange/token/amount/side/domain逐项篡改 | 原 Alloy Order hash 对拍官方值；typed_data哈希等于原hash；改域/字段不被当原许可 | 真 builder → typed payload → fake provider中合成签名 → 原响应验证；非预造最终hash |
| A-005 | Kernel auth/order；将32字节K误当hex文本；错误account/validator | 与既有 sign_for_account公式等价；65/86字节及owner恢复正确；逐单ERC-1271拒绝路径保留 | 同一个公开合成key通过新 seam和既有公式对拍，假chain read进入原 gate |
| A-006 | backend missing/locked/unavailable、default错集合、重复条目、操作返回Prompt | signer/refresh调用均0，无Prompt调用/解锁/文件fallback；内存key未过期也拒绝 | 生产store适配实际接口的fake D-Bus/API；文件写入/子进程能力spy，不能只返回预设helper错误 |
| A-007 | store成功但读回不一致/失败；混入authorization_key或CLI整session | 拒绝发布新会话，不保存非法字段；令牌/密钥/签名不出stdout/log/Debug/错误链 | 真序列化allowlist→fake store精确读回，使用合成secret哨兵做全输出扫描 |
| A-008 | 并发续期、第二executor同slot、新代token | 唯一refresh调用/提交路径，第二实例SESSION_IN_USE；只有新record读回后才能签名；不因另chain复制slot | 实际锁/renewal状态机，受控fake传输暂停点和调用计数；不靠sleep或单线程预造结果 |
| A-009 | refresh响应丢失、远端成功保存前/保存后发布前故障、任务取消 | RenewalUncertain/重新授权边界准确，旧token不重试；重启不假称恢复authorization key/风险账 | 真状态机逐故障点注入，记录secret访问/refresh/sign计数；fake持久store跨实例重建 |
| A-010 | key/access过期、缺expiry、authenticate/HPKE失败、撤销/renewal拒绝 | 到期key不签，不persist授权key，不自动device登录；failed slot停止新增 | fake clock推进 + 真crypto库适配的合成HPKE/request-signature向量，不只fake解密返回值 |
| A-011 | 签名RPC 401/403/5xx/超时/损坏；不明后多tick同意图 | 同动作provider签名请求至多1；无401内重放，无自动新salt重签；旧风险保持 | 原 fills/Broker/copy必要consumer连贯驱动 + transport/sign计数；synthetic快捷sign bypass必须禁用 |
| A-012 | 错method/encoding/扁平签名/坏长度/高s/错v/恢复错人 | INVALID_SIGNATURE，不进入原POST；任意raw/transaction方法在网络前拒绝 | 实装响应parser+恢复验证，fake REST提交计数0 |
| A-013 | 新seam成功/失败进入原live路径；订单POST不明、迟到成交/重启 | 原07-002的预算/未知身份/不重放/对账/ERC-1271保持；signer错误不清除旧attempt或造满额 | 实际原Builder→signer→fills→Broker，合成REST/RPC/receipt，不直接塞最终State |
| A-014 | Local、paper、普通check、其他venue、包/文件范围 | Local签名向量与既有回归不变；paper/普通外部check无keyring/Privy/sign；G3与依赖/许可符合获准Design | 必要Rust离线回归/编译/格式检查、consumer构造者扫描、实际LOC/依赖清单；不得执行真实CLI/wallet |

## 6. 测试要求

- 模块单测随 BOT 模块 colocate，跨模块集成才可进入主仓根 tests。不在根堆 signer 单测；报告若必要使用 `data/reports/2026-11-15-predictfun-wsl-signer/`，证据在 `evidence/`，不建 `data/tasks/` 或任务正文镜像。
- 主执行测试 seam 必须为实际待实现的 signer transport / SecretStore / clock / 独占锁；仅这些依赖可以用合成替身。现有 `PredictFunTrader::sign_in` 和 `fills::sign_order` 的 `#[cfg(test)] synthetic` 快捷返回会绕过 signer，测试不得借其假通过。Design 须增加能驱动实际 auth/order seam 的测试入口，不重写业务策略。
- 钱包签名使用明确不可充值的公开 synthetic key，仅本地离线生成；不读取真实key，不把本地合成签名称为Privy实测。HPKE/P-256请求签名须通过获准真实库和合成对端验证，避免只测模拟解密/模拟header。
- 安全验证必须包含文件fallback/整session持久化/秘密输出的负断言；对错误先于provider调用、refresh与sign至多一次、跨tick无重签有实际计数。持久化测试证明只存允许字段，并暴露崩溃窗口；不依赖人为锁定/重启用户真实keyring。
- 07-002 原验收不重开。按受影响范围保留Rust Local签名公式、Broker与账户/成交回归、copy构造者兼容和paper，无94日研究/新paper观察/真实网络测试。
- 后续 Design 给出准确 test filter 和逐项命令；允许的验证形态为 BOT 内 `cargo test --offline --locked ...`、`cargo check --offline --locked --all-targets`、受限格式与diff检查。依赖缺失、锁文件不符则报真实阻塞，不能自行安装/换版。本卡不运行这些业务测试；没有测试名/实现时不伪称已存在。
- 独立 Validate 必须绑定实际候选身份、真实命令/exit、覆盖/未覆盖项，检查三层文件存在且互相一致；开发者自测不替代。实际Privy/BNB/Predict兼容、真实token续期、用户keyring冷启动和同UID隔离均明确NOT_EXECUTED，fixture不能替代。

## 7. 实现约束

1. 原 07-002 已经 `OFFLINE_ENGINEERING_ACCEPTED`；只读原三层、报告/证据，不修改旧验收结论或把已完成能力列为当前待实现。
2. 原CLI 0.3.11不是可直接import的signer SDK：bundle有顶层CLI解析、无已确认的安全库导出，内部fallback、authorization_key持久化和401重放必须实际消除，不是wrapper文案约束。禁止运行/导入该bundle试错。
3. 固定CLI许可证声明Apache-2.0，BOT为MIT；若未来批准复制/裁剪，须处理上游许可证/修改标识/适用NOTICE和所选传递依赖，不能删来源/强称全部MIT。当前tarball缺LICENSE/NOTICE文件不是禁止使用的定论，也不是分发审查已通过。
4. 禁止假定当前Cargo具有HPKE/P-256/JCS/Secret Service接口；现有直接依赖未包含它们。新依赖、Node子进程/认证fork、具体库替换须先经§8决定，不以vendoring第三方代码来隐藏维护成本。
5. 遵守G3：predict_fun父2385行、account2390行、fills1972行；新增主体放专责子模块，Design定义必要拆分与增长边界、独立Validate。不能另造钱包runtime/平台或为省行数压缩/省测试。
6. 工作区仅 `/home/pascal/workspace/yquant-investment`；不改其他项目/profile、security policy、服务、调度、全局依赖、Git history/gitlink。运行时安全拒绝后停止被拒动作，不换工具/路径重放。
7. 真实凭据不进入模型、stdout、错误链、报告、Kanban或`.env`；不要读取shared credentials文件来“验证没有私钥”。真实keyring本阶段不写、不解锁、不Prompt、不扫描。新命名空间的合成store测试也不在本卡执行。
8. runtime估算约340–560行、加必要测试约640–1060行，非已测LOC，且尚不含完整device-login/bootstrap。超过原110–220 / 260–470估算以及必要新依赖/认证fork均触发re-anchor；不得降低安全来满足旧数字。

## 8. 开放问题

本 SPEC 的行为、编码与拒绝标准已显式化，但必要复用接口尚不能被称为实现就绪；这是阻塞，不是开发者可自行选择的细节。最小运行凭据入口已定为预先存在、精确绑定且符合 §4.bis schema 的 keyring 条目，缺失即失败关闭，不额外要求本轮实现交互授权。

- B-001：主控/Pascal 需决定是否接受新ROI，选择同 BOT 内受限Node认证派生核心、Rust官方协议库适配、或暂停等待官方可注入库。仅做fake seam若被单独选中，必须相应下调目标，不标本RFC完成。
- B-002：在获准路线内固定真实库/制品、HPKE suite/info/AAD和密钥格式、request authorization payload/header映射、非交互Secret Service API、独占锁实现和许可/依赖边界；无这些不能下发Implement。通用RPC网页的Basic认证示例不得被视为device-grant signer API已经闭合。
- 初始授权边界（已定，非新增阻塞）：本轮不实现交互device登录/provisioning；合成测试通过指定store接缝准备合成记录。未来真实初始化另行授权，不读取CLI session、不聊天导入token、不自动授权钱包；refresh消费测试不证明完整初次接通。

真实账户归属/BNB兼容/真实Predict认证与交易仍属未来另批验证，不要求本卡执行，也不以这些未授权动作构成循环门槛。本卡因上述ROI/接口决策真实阻塞，RFC/SPEC保持Draft；不得仅以文件已存在标阶段验收通过。
