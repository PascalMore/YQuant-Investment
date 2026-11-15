# RFC-07-003: Predict.fun WSL 本地私钥 keyring 录入与启动入口

> V0.5（2026-11-15，Asia/Shanghai）：在已验收 V0.4 helper 上仅增显式 `check --config <公共JSON> --sign-in`，复用固定 Rust `check-venue --sign-in`，接受 Predict.fun Terms 并核验认证账户。不默认登录，不增加 run/TUI、下撤单或资金入口。普通 check/enroll 兼容；登录成功必须有 child exit0、唯一有效的公开签名成功行及登录账户成功行，且账户匹配固定 Predict Account；只收内存、白名单提取，禁止转发原输出/异常或持久化 JWT。具体输入/输出与反例见 SPEC §4.6、§5。当前仅 RFC/SPEC 契约冻结，新增能力尚未实现或验收；Design 由预建下游修订至同版后再进入实现。

以下两段为 V0.4 修复当时的范围/待验记录，已由 §2 的独立验收事实闭合；不作为 V0.5 的待办或真实访问授权，历史失败与安全拒绝不改判。

> V0.4（2026-11-15，Asia/Shanghai，Pascal 已同意继续）：只闭合已定位的 GetSecret 内容类型兼容。写入仍固定 `text/plain; charset=utf-8`；读回仅接受两个精确字符串 `text/plain; charset=utf-8`、`text/plain`，不做 strip/大小写归一/前缀或任意 MIME 匹配，其他值和类型仍拒绝。已闭合的五业务属性精确核验及可选固定 `xdg:schema=org.freedesktop.Secret.Generic` 保持不变；session、空 parameters、64位规范小写 ASCII key、真实派生 signer 校验不放宽。只改 BOT `tools/predictfun/local_signer.py` 与 `tools/predictfun/tests/test_local_signer.py`，依赖/README/Rust/CLI/SDK/旧证据只读。本轮独立 Validate 须跑完整受影响回归及一轮新唯一 synthetic namespace 的真实 login create、独立进程 read、定点清理和成功空搜索；不接真实 key、不签名/认证/交易、不改服务或安全配置。

> 闭合清单与用户重锚：V0.2 离线 helper 已验；V0.3 schema 窄修复经26项回归和33个独立案例通过，但真实读回仍 REVISE；新授权诊断已证明唯一不一致是 content type（其余字节/派生校验均通过），测试条目已清理。来源为现有同主题报告 `schema-validation.md` 与 `evidence/getsecret-diagnosis-8551b398e666463ca14b029a4b8ec472.json`。当前仅此内容类型 finding 开放，不重开 schema/架构；下文原阶段工作/未实装状态句为 V0.2 阶段记录，不作为当前重新设计要求。原失败证据及 runtime 拒绝保留，不以修订改判 PASS。

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | V0.5 RFC/SPEC 契约候选：V0.4 synthetic 基线已验；显式 sign-in 待 Design/Implement/独立 Validate，非交易许可 |
| 作者 | YQuant Principal |
| 创建日期 / 最后更新 | 2026-11-15 / 2026-11-15（Asia/Shanghai，UTC+08:00） |
| 所属模块 | 07_trading |
| 依赖 RFC | [RFC-07-002](RFC-07-002-predictfun-live-foundation.md)，保留已验收实现 |
| 替代 RFC | 无；同编号修订，不新建平行文档 |
| AI 适配 | Hermes Full；独立 Validate，任务与交接仅在 Kanban |
| 标签 | #交易 #本地私钥 #SecretService #最小入口 |
| 派生 SPEC | [SPEC-07-003](../../spec/07_trading/SPEC-07-003-predictfun-wsl-nonexport-signer.md) V0.5 |

## 1. 执行摘要（Executive Summary）

按 Pascal 已确认的导出私钥路线，复用现有 Rust `PrivateKeySigner` 和已验收的本地遮蔽录入、WSL Secret Service 存储及固定子进程入口。V0.5 只增加显式登录与认证账户核验，不重写认证。工程 worker 仅以公开身份、合成密钥和 fake child 验证；用户已本人 enroll 的声明不等于 worker 访问授权。真实认证须在独立工程 PASS、主控审核后，由主控沿用用户本次一次认证授权执行，不能以工程 PASS 宣称真实认证已通过。

文件名中的 `nonexport` 仅为历史标识，不再承诺非导出签名。旧非导出方案及其 Agent Authorization / ROI 阻塞由用户新决定取代，不是当前要求或阻塞；不改写 Kanban run3711 历史。

## 2. 背景与动机（Background & Motivation）

- V0.2 初始 HEAD 为主仓 `546518b222708022da0ef8b708cdeba2ad1ad8e6`、BOT `0b8b31092cbd660a53ced463734c4673de055ed9`；当时 clean 是历史事实。V0.5 入场已有 dirty 是上游基线，仅按路径归属，不 reset/stash/clean/checkout/commit/push。
- `BOT=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。`src/config.rs:596–649` 已支持环境私钥/API key/账户覆盖；`src/service/predict_fun.rs:1281–1315` 已构造本地 signer 与 Predict Account，不需要新签名协议。
- [07-002 closeout](../../../data/reports/2026-11-13-predictfun-live-foundation/closeout.md) 为 `OFFLINE_ENGINEERING_ACCEPTED`。原策略、订单、账户核验、预算、不重放、授权/赎回工具直接复用，不重开其实现阶段。
- [WSL 合成验证](../../../data/reports/2026-11-15-wsl-native-credential-validation/report.md) 已证明当时已解锁 login 集合的精确合成存取及清理，不证明当前解锁、冷启动或新入口无 Prompt。
- 现有隔离工具锁定 `eth-account==0.14.0`，`sdk_ops.py` 已使用 `Account.from_key`；复用其地址派生能力，不自行实现 secp256k1。既有 Jeepney 无交互存储接线已在 V0.4 synthetic 基线验收；V0.5 不安装/升级包或改依赖。
- 收益是补齐受控的本地秘密入口，减少密钥进入聊天、命令参数或文件的机会；不承诺盈利、签名提速或同 UID 强隔离。
- V0.4 已由 `t_1b2754f0` 独立 PASS（仅 synthetic interoperability）：30项回归、56个独立案例及三独立进程 create/read/cleanup，见 [content-type-validation.md](../../../data/reports/2026-11-15-predictfun-local-keyring/content-type-validation.md)。本卡静态核对 helper SHA256=`438b67a4b60b091cfb8a6c7f9dace1e28a407f737ce8612285d1c1c9da66399c` 一致，schema/content-type finding 已闭合；历史 REVISE 不追溯改判，也不重做此能力。
- 用户本人 enroll 成功为主控传入的用户声明，本 worker 未读取生产条目。主控普通 check 的[一次证据](../../../data/reports/2026-11-15-predictfun-local-keyring/evidence/authorized-check-76642cc133ed41519fc3fc72d6d6b8e2.json)仅为 exit0 / `FIXED_CHECK_CHILD_COMPLETED`，stdout 已丢弃，不能独立证明样例签名、登录或账户控制。
- 主控已报告固定 debug binary 从过旧版本以 `cargo build --offline --locked --bin polymarket-toolkits` 重建成功；上述 check 证据记录 SHA256=`7302b4760d6fa90c43a7df40c439ccb1a92fb2ecb7f14926b5c5b3f966f315e6`。这是上游制品事实，不是本卡重建/执行或登录证明。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）

1. 用户只在自己的真实 TTY 遮蔽输入私钥；本地派生地址与选定 signer 不符时，在存储前拒绝。
2. 仅向既有 WSL Secret Service login 集合的精确自有条目存取；无解锁、Prompt、自动后端初始化、文件 fallback 或错误后重试。
3. 只启动原 BOT 的固定可执行文件及 Design 明列模式；将私钥只放入该子进程的 `PM_PRIVATE_KEY`，绑定 Predict.fun、chain 56、指定 Predict Account。
4. 保留 `YQUANT_PREDICT_FUN_TOKEN -> PM_PREDICT_API_KEY` 既有来源映射；不迁移 API key、不加载竞争私钥、不把其他秘密传给辅助进程。
5. 合成测试驱动实际录入/存储/启动装配与 child-env 接缝，独立 Validate，不以假成功函数代替候选实现。
6. 仅 check 显式 `--sign-in` 才将固定同名 flag 交给原 Rust；登录输出同时证明未提交样例签名路径与认证账户匹配，不能以 child exit0 代替。普通 check/enroll 不变，不添加 helper 重试或其他认证实现。

### 3.2 非目标（Out of Scope）

无 Rust runtime/签名公式/策略/风控修改，无新钱包、API、Node 服务、通用秘密管理框架、IPC、钱包 RPC、数据库、journal 或长期调度。不实现 Privy CLI、HPKE、device grant、refresh 或会话迁移；不复制 07-002 的订单/审批/赎回代码。

当前阶段只修订本 RFC 与 SPEC；不写 Design、代码、配置、依赖或新报告。工程 worker 全程禁止读取生产 keyring、真实私钥、seed、密码、凭据 session、生产 `skills/.env`，禁止执行真实钱包 binary、联网认证/签名、provider 调用、资金或实盘激活；不要求用户重新录 key。主控在独立工程 PASS 和审核后执行本次一次真实认证是分离的授权范围，不授权工程 worker 或交易动作。新 runtime 安全拒绝立即停止，不换工具/路径绕行。

## 4. 整体设计（Overall Design）

用户本地 TTY → 格式与派生 signer 核验 → 精确 login 条目写入/独立读回；以后用户明确启动 → 公开参数与后端检查 → 精确读回/派生核验 → 固定 BOT 子进程环境 → 原执行链。

helper 只装配输入、存储和启动，不接管任何签名/交易判定；Secret Service 不是签名服务。Hermes 只持有公开契约与合成测试证据。失败关闭，没有备用钱包、旧私钥文件或自动修复路线。

## 5. 详细设计（Detailed Design）

### 5.1 业务流程（Flow）

录入先检查参数/TTY/后端可用且解锁，再遮蔽读取；回显关闭失败、EOF、取消或格式/地址错误均终止且不存储。成功只在精确写入后另行读回、在内存核对一致时报告；写入结果不明不重试、不假称未写入或自动删记录。

启动先验证固定命令、公开配置和账户绑定，再读精确密钥并复核 signer。显式避开默认 `config.yaml` 的凭据读取；已有 `PM_PRIVATE_KEY` 存在即拒绝，不读取其值后挑选优先级。子环境单独构造，不修改父环境、shell profile，不输出秘密或传入 argv/临时文件。原预算确认、账户/链/ERC-1271、余额/gas/授权、未解释风险门禁不变。

普通 `check-venue` 联网读市场/盘口并签未提交示例订单；带 `--sign-in` 才继续获取认证消息、签署接受 Terms、POST 认证与 GET 账户。它不是“无签名检查”，也不是订单提交。helper 仅启动一个 child、等待仍最多60秒，失败/超时不重启；原 Rust `authed_text` 对认证 GET 的401可清 JWT 后重新登录并重读一次，不能承诺“一次 helper = 一次 HTTP 认证”。不修改原 refresh/retry 或创建新循环，无默认隐式登录、自由命令或任意参数透传。

### 5.2 数据模型（Data Model）

固定公开身份：venue=Predict.fun，chain=56，mode=`predict-account`；交易地址 `0xfc9eb66e6F22f96608058C0A711Ed048eED8c2E2`；signer `0x5129330159f4E6a99eF873f86901E3cafa7f9A7D`。合法解析后按地址字节比较，不能把畸形 token 修正成有效身份。

Binance 登录钱包 `0xb54b2b4667b33661f83f0d6aeebb1bfa295d03be` 和新 agent-wallet `0x2FcDbb1a61f4A0439C9952710eDCe3cee071828c` 均非本次 signer。主控提供的 2026-11-15 block `133658449` 公开 owner 读回及用户所见导出 UI 是选定依据，不等于私钥控制、网站会话或实际签名已证明；本卡不重复链读。

### 5.2bis 持久化策略（Persistence Strategy）

既有唯一持久秘密为该 signer 的本地私钥：精确绑定的 Secret Service login item，五项业务属性只含公开用途/账户/链/signer/版本；仅容许 V0.3 固定 schema 元数据，不增加搜索属性。字段要求见 SPEC §4.bis；沿原 Design 固定字面属性、表示格式及非交互 API，V0.5 不新增持久秘密。禁止 session 集合、通用 keyring 自动择后端、其他条目搜索、普通文件/`.env`/Git/任务字段存储。

条目无 TTL/自动轮换/备份或迁移。录入仅由用户显式本地操作创建；已有条目不得隐式覆盖。读回失败即停止，可能已写入的状态如实说明；不自动删除。真实条目的替换/删除不新增管理命令。V0.5 测试使用隔离 transport，不访问生产 keyring；既有合成后端证据只读复用。API key 保持既有来源，不创建其 keyring schema。JWT 仅原 Rust 内存使用，不向 helper 提供或新增持久化，登录不改变本地存储 schema。

### 5.3 接口契约（API Contract）

仅“本地录入”和“有限启动”两个职责；有限启动含默认普通 check 与显式 check --sign-in，不新增子命令、HTTP/钱包 API。固定 binary、缺失 credentials 路径、strict mainnet/mock=true/enable_trading=false、chain56、身份、最小 env 与 API 映射不变。enroll 不接受 --sign-in，未知/缩写/透传参数在秘密访问前拒绝。输入输出冻结于 SPEC §4.6；Design 只细化接线，不再选择业务语义。

登录分支仅在内存收 child 输出，从 stdout 严格提取现有 `signing        ok: … USDT (not submitted)` 与 `sign-in        ok: API identifies you as …` 行；各唯一、格式完整、顺序正确且账户合法解析后等于固定 Predict Account，加上 exit0 才可输出固定公开成功句。缺失/重复/歧义/失配/child失败均非零退出，不能输出成功；stderr 不作成功证据。其余市场文本不转发，原输出、异常、签名、JWT、API key、私钥及其摘要均不落日志/文件/任务字段。普通 check 仍丢弃 child 输出且只表示 child 正常结束，不能悄悄升级其证据语义。

### 5.4 AI 模型设计（如有）

无。模型不接收私钥，不决定钱包、签名内容或交易许可。

## 6. AI 实装规范（AI Implementation Rules）

V0.5 后续实现上限仅 BOT `tools/predictfun/local_signer.py`、`tools/predictfun/tests/test_local_signer.py`、`tools/predictfun/README.md`。不改 Rust、cli.py、sdk_ops.py、Cargo、requirements/lock、配置、其他项目/profile；不安装/升级任何包，不新增服务/daemon/调度、通用启动器或第二认证核心。不 commit/push/reset/stash/clean/checkout/切分支。

历史 V0.2 D-1 单包例外已用于既有基线，V0.5 不重开安装或 requirements 写入：`jeepney==0.9.0`，固定 wheel SHA256=`97e5714520c16fc0a45695e5365a2e11b81ea79bba796e26f9f1d178cb182683`；沿既有 `.venv` 与[Design §3.4](../../design/07_trading/DESIGN-07-003-predictfun-wsl-nonexport-signer.md#secret-service-adapter) 的无 Prompt 适配及9+1秒预算。既有五属性、可选固定 schema、两精确 content-type、规范 key/session/parameters 与派生核验全部保留；本次不修改存储协议或依赖。

若固定接缝无法小范围实现，报告具体缺口，不借新依赖、手写加密或认证核心扩张。runtime 拒绝后停止该动作，不换工具/路径绕过；真实认证按 §3.2 分离执行。

## 7. 风险与应对（Risks & Mitigations）

- 导出私钥的泄漏影响高：仅用户本地遮蔽输入、精确存储、最小子环境；不能称非导出或硬件隔离。
- 后端锁定/失联、存取竞态：操作本身无 Prompt、有限等待，失败停止；只做事前元数据检查再调用会解锁的工具不合格。
- 误用登录钱包/旧环境 key/默认 credentials：固定绑定、存前与启动前派生复核、拒绝竞争 key，并显式隔离旧 loader 文件路径。
- 同 UID/管理员可访问 keyring、进程内存及子环境；GC、swap/core dump 不保证物理清零。本轮明确接受该限制，不据此建立新签名服务。
- 合成测试不能证明真实账户可用；用户 enroll 声明、普通 check exit0、V0.5 离线 PASS 与真实认证 PASS 必须分开。登录输出只核验既有成功标记及账户，不是 JWT 内容/链上 owner/网站会话或交易能力证明；同 UID 改 binary/配置的既有风险不扩大为强隔离承诺。

## 8. 备选方案（Alternatives Considered）

已选择本地 signer + keyring 薄入口。非导出 Agent Authorization 已被 Pascal 取代，不继续旧协议研发；文件/环境全局 export、把私钥交给 Hermes、通用命令 runner 均不选。新增 wallet runtime/密钥管理平台不符合本次 ROI。

## 9. 验收标准（Acceptance Criteria）

后续工程按 SPEC §5 实测：TTY 遮蔽与拒绝、派生匹配、精确存储/读回及故障、无 Prompt/fallback/leak、固定子进程与 env、公开绑定、API 映射和其他秘密边界。原 signer 与风险链不变，仅跑受影响回归，不重做 07-002。

本卡验收仅两份独立一致契约、引用与受限静态 diff 检查；不把文档完成写成入口已实装。无新增性能、盈利或交付时长门禁。

## 10. 落地计划（Implementation Plan）

沿预建 Full 增量图：本次 RFC/SPEC → 主控核验后释放 Design → 主控 Design Gate → Implement → 独立 Validate → 主控收口。不新建阶段/任务图；Design 保持 operator-held，路径为 `docs/design/07_trading/DESIGN-07-003-predictfun-wsl-nonexport-signer.md`。当前 Design V0.4 的“拒绝 sign-in/只有两命令”和旧待实现记录须由下一卡同步，三层 V0.5 一致前不放行实现。

只扩展已有 helper/parser、登录证据提取和 fake-child 测试/短用法。增量粗估40–80实现行、80–150测试行；不是实测 LOC、硬上限或小时承诺，不为压行数省校验或增加架构。

## 11. 开放问题（Open Questions）

- 开放业务契约项：0。D-1/D-2 的既有 keyring/固定 child 接缝已实现且 V0.4 synthetic 基线已验，不再列为待实现。
- 下一 Design 卡仅细化 SPEC §4.6 的参数接线、严格标记提取及错误/测试实现；不得改变默认不登录、固定身份、最小子环境或真实认证分离规则。

RFC/SPEC 可交主控检查，不表示 Design Gate 或实现已通过。旧非导出 B-001/B-002 不适用；真实认证尚未执行，不是本阶段文档交付的阻塞，也不能伪称通过。

## 12. 参考资料（References）

- [SPEC-07-003](../../spec/07_trading/SPEC-07-003-predictfun-wsl-nonexport-signer.md)、[SPEC-07-002](../../spec/07_trading/SPEC-07-002-predictfun-live-foundation.md)、[DESIGN-07-002](../../design/07_trading/DESIGN-07-002-predictfun-live-foundation.md)。
- [07-002 closeout](../../../data/reports/2026-11-13-predictfun-live-foundation/closeout.md)、[WSL report](../../../data/reports/2026-11-15-wsl-native-credential-validation/report.md)。
- BOT `src/config.rs`、`src/main.rs`、`src/service/predict_fun.rs`、`tools/predictfun/{requirements.lock,sdk_ops.py,README.md}`；公开身份/路线决定来源为 Kanban `t_db16b30c` 当前正文。

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-11-15 | 历史非导出方案，原 run3711 阻塞记录保留在 Kanban；不再生效 | YQuant Principal |
| V0.2 | 2026-11-15 | 按 Pascal 决定改为本地私钥/keyring 薄入口，复用原 signer；真实 provisioning 与本轮合成准备分离 | YQuant Principal |
| V0.3 / V0.4 | 2026-11-15 | 历史 schema/content-type 修复，V0.4 synthetic interoperability 独立 PASS；原 REVISE/拒绝不改判 | YQuant 主控/独立 Validate |
| V0.5 | 2026-11-15 | 仅显式 check --sign-in，冻结公开标记/账户核验与零秘密输出；默认兼容，工程与主控真实认证分离 | YQuant Principal |