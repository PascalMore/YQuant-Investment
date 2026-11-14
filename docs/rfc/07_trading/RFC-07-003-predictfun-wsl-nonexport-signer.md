# RFC-07-003: Predict.fun WSL 原生非导出 signer

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿；ROI / 复用边界阻塞，非已采纳、非 Implement-ready |
| 作者 | YQuant Principal |
| 创建日期 | 2026-11-15 |
| 最后更新 | 2026-11-15（Asia/Shanghai，UTC+08:00） |
| 所属模块 | 07_trading |
| 依赖 RFC | [RFC-07-002](RFC-07-002-predictfun-live-foundation.md)，保留其已完成能力 |
| 替代 RFC | 无 |
| AI 适配 | Hermes Full：RFC/SPEC → Design → Implement → 独立 Validate |
| 标签 | #交易 #非导出签名 #WSL #安全存储 #复用 #ROI |
| 派生 SPEC | [SPEC-07-003](../../spec/07_trading/SPEC-07-003-predictfun-wsl-nonexport-signer.md) |

## 1. 执行摘要（Executive Summary）

在唯一现有 Toolkits Rust bot 内，将本地私钥签名替换点收敛为账户绑定、动作受限的 Privy 非导出 signer，凭据后端只选 WSL Secret Service，保留既有策略、风控、订单编码和对账。本次取证发现原版 CLI 不能作为合规薄 signer 直接复用；满足安全生命周期至少涉及存储与认证重组或新依赖，已触发卡面 ROI 停止条件，因此本稿冻结需求与验收，但不放行后续实现。

成功仅指未来获准候选通过实际离线/合成接缝验收；不代表真实 Privy 控制、BNB 支持、Predict 登录、交易权限、无人值守重启或盈利。当前阻塞不能由仅实现 fake signer 或压缩代码行数消除。

## 2. 背景与动机（Background & Motivation）

- 取证基线：主仓 HEAD `90fca2661e9dafaffcf0d0835ec73073d9be2fa0`；Toolkits HEAD `0b8b31092cbd660a53ced463734c4673de055ed9`。本卡开始时两树均 clean。
- `BOT=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`，下文代码路径相对 BOT。实际 signer、JWT 登录在 `src/service/predict_fun.rs:1263–1508`；订单签名消费者在 `src/service/predict_fun/fills.rs:537–567`，不是独立 `auth.rs`。
- 07-002 的 [closeout](../../../data/reports/2026-11-13-predictfun-live-foundation/closeout.md) 已为 `OFFLINE_ENGINEERING_ACCEPTED`。成交、预算、账户/链检查、Kernel/ERC-1271、无自动重放等是保留基线，旧三层文档中的阶段性“待实现”措辞不作为本次重开缺口。
- [WSL 验证报告](../../../data/reports/2026-11-15-wsl-native-credential-validation/report.md) 与 `evidence/result.json` 证明此前已解锁 login 集合可用、独立精确读回及自身记录清理；它不是 CLI、令牌轮换、钱包签名或冷启动证据。本卡不重跑、不改变真实 keyring。
- 专用候选公址为 `0x2FcDbb1a61f4A0439C9952710eDCe3cee071828c`；不作默认账户，不从地址推断 Privy app/wallet ID、用户控制权或 Predict 兼容性。
- 价值是避免钱包主私钥进入 bot/模型，并缩小执行授权面；没有本次可量化的收益提升或签名时延收益证据。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）

1. 显式 Local / Privy 模式，Privy 模式绑定 app、wallet ID、signer、chain、交易地址和账户模式，不加载真实或占位本地私钥；缺配置不得退回 Local。
2. 只接受由原消费者构造的 Predict 认证挑战与经过原确定性风险门禁的订单；无 Hermes 任意签名、raw RPC、转账或执行能力。
3. WSL Secret Service-only；允许持久令牌与短期签名密钥分离。Privy 解密后的 authorization signing key 以及 HPKE 私钥只留执行进程内存，不继承原 CLI 的整 session 持久化。
4. 失败关闭、序列化轮换、持久化后再发布新会话；签名/提交状态不明不自动重放；完整披露远端轮换和本地提交之间的崩溃窗口。
5. 实装接缝必须可离线驱动并包含反例，不以固定 helper 结果代替真实构造/调用/响应解析/consumer 路径。

### 3.2 非目标（Out of Scope）

不导出、导入或迁移钱包主私钥；不建第二 bot、CLOB client、通用钱包平台、HTTP daemon、Windows bridge、数据库、journal 或 scheduler。不重写策略、修改风险金额/费率、增加自动补单/资金操作或放宽 07-002。不存在本卡授权的真实 keyring 凭据写入、CLI 登录、device grant、Privy authenticate/RPC、Predict JWT 登录、真实签名、approve、交易或部署。

后续流水线的业务验收仍仅离线/合成；真实账户接通需要另行具体授权。本卡只写本 RFC 与对应 SPEC；Design、源码、配置、依赖和锁文件均不在当前写权限内。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

保留原交易执行链，只替换签名能力和必要凭据装配；安全后端成功不等于上层认证实现合规，也不等于同用户进程隔离。

### 4.2 架构总览

`原 DecisionCore / Broker / copy 风控 → 原 PredictFunTrader + 绑定 signer → 仅 PredictAuth / PredictOrder → Privy Agent Authorization 官方签名协议 → 原 JWT / POST orders / 查询与对账`。

链路中 Privy 只返回签名字节给执行器；不接管订单、资金、成交或账本。Secret Service 是凭据存储，不是签名服务。Local 分支继续现有签名公式与行为；paper 不因 Privy 增加 token、keyring、SDK 或网络前提。

### 4.3 模块分工

| 模块 | 职责 |
|---|---|
| 原 BOT 策略、Broker、RiskGuard、AccountGate | 判断是否允许原订单；预留、未解释风险及跨 token 阻断不变 |
| 原 Predict client / order builder / fills | 认证消息来源、订单字段/部署/摘要、单次提交、结果消费与对账 |
| 新的 BOT 内 signer 接缝 | 模式、绑定、typed action 校验、签名字节核验，不提供公网服务 |
| 必要的 Privy 认证/存储适配 | 仅官方 device-token / HPKE / request-signature 生命周期，严格后端与轮换；具体复用方案尚未获准 |
| Hermes / Kanban | 管理工程与脱敏证据，不持有任何 bearer、authorization key 或任意钱包 RPC 入口 |

## 5. 详细设计（Detailed Design）

### 5.1 业务流程（Flow）

1. 先解析公开 signer 选择与账户绑定，再决定凭据装配。Privy 模式不得调用会读取遗留私钥文件或 `PM_PRIVATE_KEY` 的完整 loader；不能先读取再清空字段。
2. 获得该 credential slot 的独占执行权，检查 Secret Service 元数据和精确自有记录。锁定、缺失、重复记录、不可用或需交互解锁均停止，不弹密码、不修复 keyring、不用文件 fallback。
3. 执行器内访问令牌/authorization key 到期前先续期。refresh 响应立即使旧 refresh token 失效；在一个受序列化保护的更新中保存新持久字段并独立精确读回，再发布新的内存会话。HPKE 私钥和解密后的 authorization key 永不落盘。
4. Predict 认证只签原 client 从固定官方认证接口取得的原始 UTF-8 消息。订单只签原 builder 的确切字段；校验同一账户、链、exchange 和原风险许可。认证用于原 live / 显式 sign-in，不把普通 check/paper 变成远程签名动作。
5. 签名响应须通过严格形状、长度、恢复 signer 和消息摘要检查，再交原 consumer。Kernel 路由仍执行既有逐单 ERC-1271；不因使用 Privy 而跳过 owner、余额、gas、授权或预算检查。
6. 后端、续期或签名失败阻断该绑定账户的新签名/新增，保留原 attempt 和风险。签名超时后不自动重签；订单可能提交后继续原查询/对账，不新 salt、不 POST replay。

### 5.2 数据模型（Data Model）

| 实体 | 必要字段 | 约束 |
|---|---|---|
| SignerSelection | Local 或 Privy | 缺省 Local 仅兼容旧调用；显式 Privy 失败不得降级 |
| SignerBinding | app_id、wallet_id、credential_slot、signer_address、chain_id、account_mode、trading_address | 公址不能代 wallet ID；EOA 两地址相等；PredictAccount 保留原控制检查 |
| TypedAction | PredictAuth 或 PredictOrder，加来源/原 attempt 约束 | 不接受任意 method、原始 digest 或任意 typed JSON 的公开入口 |
| PersistentSession | schema_version、slot/app 绑定、wallet 绑定、refresh_token、generation | 仅 Secret Service；不保存授权密钥、HPKE key、JWT、完整 CLI session |
| EphemeralSession | access token/expiry、authorization key/expiry、HPKE 临时材料 | 内存、过期拒绝、禁止 Debug/日志/普通序列化 |
| SignResult / SignFailure | 内部签名字节，或稳定 code/step/reason 与原关联 | 不返回给模型；错误不携原请求、provider body、凭据或签名 |

字节/文本、EIP-191/EIP-712、Kernel 包装和错误语义以 SPEC §4 为唯一可测试细化，不能由实现者改为另一条签名协议。

### 5.2bis 持久化策略（Persistence Strategy）

| 数据类别 | 存储介质与命名 | 生命周期 | 隐私与边界 |
|---|---|---|---|
| Privy refresh token 与最小绑定元数据 | Secret Service login 集合；service=`yquant.predictfun.privy.v1`，精确 app_id + credential_slot | 显式初始化/轮换；撤销、过期或失配停止，不自动删真实记录 | token 为 L3，仅授权执行端可使用；不得进 Git、`.env`、日志、模型或任务字段 |
| Predict API key（外部模式） | 独立精确条目，service=`yquant.predictfun.api.v1`，app/slot/chain 绑定 | 只在未来单独获准的 provisioning 下保存 | L3；与 Privy bearer/header 不交叉发送 |
| access token、JWT、授权签名密钥、HPKE 私钥、钱包签名 | 仅执行器内存 | 到期/退出丢弃；不承诺进程崩溃后的自动恢复 | 不备份、不导出、不写 keyring 整 session 或普通文件 |
| 独占锁 | OS 非秘密锁，按 slot 命名 | 仅进程存活期间持有 | 不存 token，不冒充可靠恢复日志 |

无 DB/schema/索引/TTL 迁移，无 CLI session 自动迁移、文件恢复或 keyring 初始化。只搜索确切自有命名空间，写后精确读回，不能把“store exit=0”当提交完成。远端刷新成功而本地未提交时可能永久丢失可用 refresh token；停止并要求以后获准重新授权，不回滚已失效旧 token。Secret Service 不提供与远端 OAuth 原子事务，文档不宣称零丢失续期。兼容旧 schema 不靠猜测，未知版本拒绝。真实同 UID agent 能调用相同 Secret Service，当前不构成独立 OS 安全边界。

### 5.3 接口契约（API Contract）

无新增 HTTP 服务。逻辑接口仅有绑定查询、`sign_predict_auth(已验证来源挑战)`、`sign_predict_order(原订单及受限许可)`；仅供原 executor 调用。官方 Privy device-grant REST 目标为 `https://auth.privy.io/api/oauth/v2/...`，不能误换成需要 app secret 的通用 server-wallet API。对外禁止暴露 arbitrary personal_sign / typed-data / secp256k1_sign / eth_send*。

固定 CLI 的公开 `rpc` 不符合上述能力收敛；SPEC 定义行为不表示存在可导入 SDK。本稿不假定改环境、包裹 stdout 或先检查 keyring 就能阻止 bundle 内部 fallback/整 session 写入。

### 5.4 AI 模型设计（如有）

无。模型不参与密钥、challenge、订单授权、token 轮换或签名载荷决策。

## 6. AI 实装规范（AI Implementation Rules）

### 6.1 必须执行

保留 07-002 已验收行为，Rust 模块单测 colocated，主仓 tests 仅适合跨模块集成。候选接缝在同 BOT 的 `src/service/predict_fun/`；后续 Design 才冻结完整文件 allowlist、依赖和具体进程组织。`predict_fun.rs` 当前 2385 行、`account.rs` 2390 行、`fills.rs` 1972 行，均不得继续堆认证主体；按 G3 说明边界、增长、拆分触发并独立 Validate，不进行无关重构。

### 6.2 先询问再执行

当前已触发 ROI gate：必须先由主控/Pascal 选择 §8 的实施路线、预算和必要依赖；不得由 Design/Developer 自行选钱包认证 fork。真实授权/初始化、凭据写入、安装、运行配置和账户/资金动作均需另外明确许可。

### 6.3 绝对禁止

不得执行原 CLI/导入 bundle 试探副作用，不读 session 文件/共享 `.env`/真实 token，不让 authorization key 落盘，不用虚假私钥绕过构造要求，不以重启/解锁 keyring 或 Windows 通道“修好”本次设计。禁止改审批/安全策略或绕过 runtime 拒绝，不 commit/push/gitlink/部署。

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 概率 / 影响 | 应对方案 | 降级策略 |
|---|---|---|---|
| CLI 内部弱文件 fallback、整 session 含 authorization_key | 固定制品已确认 / 高 | 不选原样 CLI wrapper；拆分允许持久字段 | 停止外部签名，不退 Local |
| refresh 立即失效与本地保存间崩溃 | 真实存在 / 高 | slot 独占、串行、写后精确读回、提交后发布 | 不再尝试旧 token；重新授权需以后另批 |
| raw RPC 越权、错误账户/域/文本编码 | 存在 / 高 | typed action、原门禁、完整字段/摘要与恢复地址核验 | 拒绝并阻断新增 |
| 同用户进程读取 keyring 或内存 | 未隔离 / 高 | 不向模型发放能力；明确 threat model 限制 | 不承诺强隔离或无人值守安全 |
| 仅 mock 成功掩盖未接入实装 | 存在 / 高 | 测真实装配、传输/存储 seam、旧 bypass 的反例 | 未满足不得签收非导出 signer |
| 大文件/认证 fork 超出小改 ROI | 已触发 / 中至高 | 本稿记录估算与边界，先 re-anchor | 保持旧离线基线，不实施扩张 |

## 8. 备选方案（Alternatives Considered）

### 8.1 固定官方 CLI 的真实复用结论

`@privy-io/agent-wallet-cli@0.3.11` 的 manifest 声明 Apache-2.0，`main` 与两个 bin 同指 `dist/index.js`，没有独立 signer 导出说明。已有固定 tarball 只有 bundle、package.json、README；本卡静态核得无 ES 模块 export 声明模式，并存在 `.parse(process.argv)` / 同类顶层 CLI 解析模式，不能把 main 字段当 side-effect-free library。

bundle 静态包含 OS keychain 失败后 `A.write(...)` 的静默文件回退、login/refresh 持久化 authorization_key、通用 RPC、401 后刷新并重试 RPC。README 与网页并不完全同步，优先采用固定制品事实。公有源码可作协议参考；“加 wrapper 即可复用 signer”不成立。

Apache-2.0 声明允许按其条款使用/修改，不是禁止复用；它也不使派生代码自动变为 BOT 的 MIT。若复制/修改，须保留版权/许可证、提供 Apache-2.0 文本、标识修改，按上游存在情况保留 NOTICE，并核对所选依赖许可证。该 tarball 未附 LICENSE/NOTICE，manifest 不等于完整归属/传递依赖审核。本次不复制、不安装，不能将未完成的再分发检查写成已许可审查通过；也不据此推断所有官方 SDK 不可用。

### 8.2 可选路线与成本门禁

| 路线 | 结论 / 下一决定 |
|---|---|
| 原 CLI 子进程 + wrapper，保持原版 | 不满足失败关闭、只内存授权密钥、受限能力和禁止 replay，淘汰 |
| BOT 内裁剪/改造固定 CLI 的认证核心，限定存储和 RPC | 可能可行，但已是需维护的认证派生代码及 Node 依赖，不是直接 import；必须明确批准范围/许可处理/供应链锁定 |
| BOT 内 Rust 直接实现官方 Agent Authorization 协议 | 保留单语言，但当前 Cargo 不具 HPKE/P-256/JCS/Secret Service 直接依赖，需要新依赖及更多认证代码；不得手写加密原语 |
| 暂停，等待已验证支持 device grant 和可注入安全存储的官方库 | 最小维护成本；当前没有足以放行的固定版本 API 证据 |
| 只做离线 signer trait + fake，provider 永久 unavailable | 可独立缩小研发目标，但不是完成本 RFC 的非导出 signer；不能默认为本卡交付 |

估算为正常可维护排版，不计第三方代码/构建制品/文档：Rust 及 consumer 接线约 80–130 行；安全存储/轮换/独占约 110–180 行；HPKE/请求签名的库适配约 90–150 行；输入/绑定/错误及装配约 60–100 行，总 runtime 约 340–560 行；必要测试约 300–500 行，总约 640–1060 行。这是职责分解估算，不是已实现 LOC，也不含完整交互 device-login/bootstrap。原 110–220 runtime / 260–470 含测试估算不能作为当前可行承诺。

即使后续复用缩短上述估算，新依赖、认证 fork 与尚未固定的必要库接口也已独立触发本卡停止条件。初始登录/provisioning 不在本次最小流水线实现范围，运行只消费预先存在且符合 SPEC 的精确 keyring 条目，缺失即停止。推荐先由主控/Pascal 决定是否接受“同 BOT 内受限认证适配”的新成本，或暂停；不推荐为了压线省测试、允许授权密钥落盘或扩为新钱包平台。

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收

以 SPEC §5 的 A-001–A-014 为后续离线验收：模式装配不读私钥、全绑定、真实 auth/order 编码接缝、严格后端、串行轮换与故障窗口、无 replay、真实 consumer 和 07-002 回归。仅 helper 数字、预造最终签名或硬编码成功不能满足。

### 9.2 非功能验收

秘密/签名不经 stdout、日志、Debug、错误链或模型；不新增 paper 凭据/网络依赖，不改变既有风险门禁、订单事实、Kernel 支持路由。未提出无来源的性能/盈利阈值。当前本卡仅文档静态核对，未运行实现测试；真实 keyring 只复用既有历史合成证据，不宣称当前可用性/续期/签名通过。

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分

先完成主控 re-anchor 与 RFC/SPEC 文档 Gate，再进入独立 Design；Design 文件保留路径为 `docs/design/07_trading/DESIGN-07-003-predictfun-wsl-nonexport-signer.md`，当前不创建。获得明确许可后才 Implement → 独立 Validate → 主控 Closeout；任务状态/依赖只在 Kanban。

### 10.2 任务清单

本 RFC/SPEC 定义需求与失败边界，不作为新任务镜像。后续 Design 必须在批准路线内给出实际可复用制品/API、精确许可处理与文件边界、既有精确凭据条目的装配、合成验证命令和 G3 拆分；若不能闭合必须停止，不将上述决定交给 Developer 猜测。不额外扩展交互登录/provisioning 功能。

## 11. 开放问题（Open Questions）

- B-001（阻塞）：主控/Pascal 是否接受超过原估算的受限认证适配，选择裁剪 Node 认证核心、Rust 官方协议库适配，或暂停？任何选择都不授权钱包平台。
- B-002（阻塞，依赖 B-001）：批准路线的固定库/制品、HPKE suite 与密钥格式、可注入 storage/transport 接口及最小依赖/许可清单尚未形成可执行实现基线。现有 CLI main 不能充当答案。
- 初始授权边界（已定，非新增阻塞）：本轮不实现交互登录/provisioning，合成测试通过指定 store 接缝准备符合 schema 的合成记录；未来真实初始化另批，不依赖原 CLI session（其授权密钥持久化不合规），不让用户在聊天输入 token。不把 refresh 消费测试称为完整初次接通。
- 非本次阻塞的真实未验证项：候选地址归属、真实 app/wallet ID、BNB 实际支持、Predict 实际认证/交易、锁定/冷启动、provider 撤销时效。未来另行授权，不能要求本卡实际调用来“消除”它们。

本稿不存在对 B-001 / B-002 的默示批准；未闭合不得标 Accepted、Implement-ready 或“可直接复用已完成”。

## 12. 参考资料（References）

本卡于 2026-11-15（Asia/Shanghai）只读公开文档；URL 为可变页面，不冒充不可变制品。未调用示例中的认证/钱包接口。

- [SPEC-07-003](../../spec/07_trading/SPEC-07-003-predictfun-wsl-nonexport-signer.md)、只读 [SPEC-07-002](../../spec/07_trading/SPEC-07-002-predictfun-live-foundation.md)、[DESIGN-07-002](../../design/07_trading/DESIGN-07-002-predictfun-live-foundation.md)。
- [WSL 报告](../../../data/reports/2026-11-15-wsl-native-credential-validation/report.md)、[result.json](../../../data/reports/2026-11-15-wsl-native-credential-validation/evidence/result.json)。
- [CLI 预检报告](../../../data/reports/2026-11-14-privy-agent-wallet-cli-preflight/report.md)、[manifest](../../../data/reports/2026-11-14-privy-agent-wallet-cli-preflight/evidence/package-manifest.json)、[static-checks](../../../data/reports/2026-11-14-privy-agent-wallet-cli-preflight/evidence/static-checks.json)、[source-windows](../../../data/reports/2026-11-14-privy-agent-wallet-cli-preflight/evidence/source-windows.json)。
- 固定公有制品：https://registry.npmjs.org/@privy-io/agent-wallet-cli/-/agent-wallet-cli-0.3.11.tgz 。既有 SHA-512 integrity 为 `sha512-oVngYVO0VQzzsobXsc4nCLctgrfKwmRZ9ThggeczmWgLUKONoNX7RsWz3DhSCFf3MePzhr2MgYraxQGzCZLuag==`；本卡复用并静态读取现存公有副本，未重新安装/执行。副本在主控 profile scratch 的 `privy-agent-wallet-cli-0.3.11-audit/`，不是长期部署位置。
- https://docs.privy.io/agent-wallets/agent-authorization ：token/HPKE、只内存 authorization key、refresh 立即轮换、device-grant 路径及撤销后 JWT 到自然到期的限制。
- https://docs.privy.io/agent-wallets/agent-cli ：官方 sandbox 定位及 OS credential manager/file fallback。
- https://docs.privy.io/controls/authorization-keys/using-owners/sign/direct-implementation ：RFC 8785、P-256/SHA-256 请求授权签名；不等于 device-grant SDK 接缝证明。
- https://docs.privy.io/api-reference/wallets/ethereum/personal-sign 与 https://docs.privy.io/api-reference/wallets/ethereum/eth-signtypeddata-v4 ：消息 encoding、typed_data/primary_type 与返回签名结构；其通用 API Basic 认证示例不能移植为本方案凭据来源。
- https://dev.predict.fun/trading/authentication 与 https://dev.predict.fun/resources/order-signing ：EIP-191 认证、EIP-712 订单、Kernel 0.3.1 包装与测试摘要。

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-11-15 | 需求/安全/验收草稿；固定 CLI 复用与许可限度、ROI/库接口阻塞及 provisioning 非目标显式记录；未放行 Design/Implement | YQuant Principal |
