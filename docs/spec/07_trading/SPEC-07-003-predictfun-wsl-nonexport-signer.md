# SPEC-07-003: Predict.fun WSL 本地私钥 keyring 录入与启动入口

> V0.5（2026-11-15，Asia/Shanghai）：仅在已验收 V0.4 helper 上增 `check --config <公共JSON> --sign-in`，复用固定 Rust `check-venue --sign-in`。默认普通 check/enroll 兼容；登录成功须同时满足 exit0、唯一完整公开签名/登录成功标记及固定账户匹配，失败关闭、零原输出转发、JWT 不持久化。§4.6 冻结新输入/输出，§5 分离工程验收与主控真实认证。新增能力待 Design/Implement/独立 Validate，不以本文完成宣称实现或真实认证 PASS。

以下两段为 V0.4 修复当时记录，相关 finding 已由 §1 的独立 PASS 闭合；不再是 V0.5 待办或真实访问授权。历史失败及 runtime 拒绝保留，不追溯改判。

> V0.4（2026-11-15，Asia/Shanghai，Pascal 已同意继续）：只闭合已定位的 GetSecret 内容类型兼容。写入仍固定 `text/plain; charset=utf-8`；读回仅接受两个精确字符串 `text/plain; charset=utf-8`、`text/plain`，不做 strip/大小写归一/前缀或任意 MIME 匹配，其他值和类型仍拒绝。已闭合的五业务属性精确核验及可选固定 `xdg:schema=org.freedesktop.Secret.Generic` 保持不变；session、空 parameters、64位规范小写 ASCII key、真实派生 signer 校验不放宽。只改 BOT `tools/predictfun/local_signer.py` 与 `tools/predictfun/tests/test_local_signer.py`，依赖/README/Rust/CLI/SDK/旧证据只读。本轮独立 Validate 须跑完整受影响回归及一轮新唯一 synthetic namespace 的真实 login create、独立进程 read、定点清理和成功空搜索；不接真实 key、不签名/认证/交易、不改服务或安全配置。

> 闭合清单与用户重锚：V0.2 离线 helper 已验；V0.3 schema 窄修复经26项回归和33个独立案例通过，但真实读回仍 REVISE；新授权诊断已证明唯一不一致是 content type（其余字节/派生校验均通过），测试条目已清理。来源为现有同主题报告 `schema-validation.md` 与 `evidence/getsecret-diagnosis-8551b398e666463ca14b029a4b8ec472.json`。当前仅此内容类型 finding 开放，不重开 schema/架构；下文原阶段工作/未实装状态句为 V0.2 阶段记录，不作为当前重新设计要求。原失败证据及 runtime 拒绝保留，不以修订改判 PASS。

## 元数据

| 项 | 值 |
|---|---|
| 状态 | V0.5 RFC/SPEC 契约候选：V0.4 synthetic 基线已验；显式 sign-in 待 Design/Implement/独立 Validate，非交易许可 |
| 作者 | YQuant Principal |
| 创建日期 / 最后更新 | 2026-11-15 / 2026-11-15（Asia/Shanghai，UTC+08:00） |
| 来源 RFC | [RFC-07-003](../../rfc/07_trading/RFC-07-003-predictfun-wsl-nonexport-signer.md) V0.5 |
| 目标模块 | 07_trading；现有 BOT 的 tools/predictfun/ |
| 适配 Agent | yquantdeveloper；独立 Validate 为 yquantreviewer；主控 yquant |

## 1. 需求摘要

保持原 Rust 本地 signer、已验收的遮蔽录入/精确 keyring/固定 child 不变，仅增显式登录 flag 与公开成功证据核验。私钥在录入和启动时均派生匹配指定 signer；缺后端、锁定、失配、存取失败均拒绝，无解锁/文件回退。API key 继续既有 `YQUANT_PREDICT_FUN_TOKEN -> PM_PREDICT_API_KEY` 来源，不迁移存储；普通 check/enroll 不变。

基线事实分层（本卡只静态核对，不重复真实操作）：

- V0.4 `t_1b2754f0` 已独立 PASS，仅 synthetic interoperability；[验收报告](../../../data/reports/2026-11-15-predictfun-local-keyring/content-type-validation.md)记录30项回归、56个独立案例及不同进程的真实合成条目 create/read/cleanup。helper SHA256=`438b67a4b60b091cfb8a6c7f9dace1e28a407f737ce8612285d1c1c9da66399c` 与当前源码一致，schema/content-type finding 不重开。
- 用户本人 enroll 成功为主控传入声明，worker 未查询生产条目。主控[普通 check 证据](../../../data/reports/2026-11-15-predictfun-local-keyring/evidence/authorized-check-76642cc133ed41519fc3fc72d6d6b8e2.json)为单次 exit0 / `FIXED_CHECK_CHILD_COMPLETED`，`sample_signature_independently_observed=false`；不能证明签名、登录或认证账户控制。
- 主控报告过旧 debug binary 已经 `cargo build --offline --locked --bin polymarket-toolkits` 重建成功；该 check 证据记录 binary SHA256=`7302b4760d6fa90c43a7df40c439ccb1a92fb2ecb7f14926b5c5b3f966f315e6`。本卡不执行/重建 binary。
- 本卡入场时 helper 尚无 --sign-in 参数，普通 check 丢弃 child 输出；本次仅开发该受限增量。旧报告/失败/拒绝只读，用户真实录入声明不追溯改变旧验收范围。

历史说明：Pascal 已以本地导出路线取代 V0.1 非导出 Agent Authorization；保留 `nonexport` 路径和 run3711 历史，不保留其生效要求、候选钱包或旧 ROI 阻塞。

## 2. 范围

### 2.1 In Scope

既有 TTY/派生/精确 keyring/child-env 均为保留基线；增量仅 check 专属显式 --sign-in、固定 flag 接线、内存公开标记/账户核验、短说明与合成测试。原 signer、订单/Kernel 包装、认证、执行、账户/预算检查均直接复用，07-002 closeout 的 `OFFLINE_ENGINEERING_ACCEPTED` 不重开。

`BOT=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。后续实现上限仅 BOT `tools/predictfun/local_signer.py`、`tools/predictfun/tests/test_local_signer.py`、`tools/predictfun/README.md`。本阶段只允许修订来源 RFC 与本 SPEC，不写 Design 或实现。

### 2.2 Out of Scope

不改 Rust、cli.py、sdk_ops.py、策略/风控/资金工具/配置/Cargo/requirements/lock；不安装或升级包，不另建钱包、服务/daemon、通用 secret store/启动器、IPC、数据库、journal、调度、策略框架或第二认证实现。工程 worker 不读生产 keyring、真实 key/seed/password/凭据 session/生产 `skills/.env`，不执行真实钱包 binary、不联网认证或签名、不调用 provider；不下单/撤单/approve/redeem/转账/充值或激活服务，不要求用户再录 key。主控在独立工程 PASS 与审核后沿本次一次认证授权执行真实登录是分离范围，不授权 worker 或交易。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | 本地遮蔽录入 | 用户真实 TTY；无私钥值参数 | 仅内存中的候选 key | 非 TTY、回显无法关闭、EOF/取消拒绝；不得退为有回显输入 |
| F-002 | 派生与绑定 | 合法私钥、固定公开身份 | 已验证 signer | 格式/标量或地址错误在 store/launch 前拒绝，不签名来证明控制 |
| F-003 | 精确存储 | 已验证 key、自有命名空间 | 写后独立读回一致才成功 | 已有条目/重复/锁定/Prompt/不明写入失败停止，不自动覆盖/重试/删除 |
| F-004 | 精确读取 | 固定条目属性与 login 集合 | 经格式及派生复核的 key | missing/unavailable/locked/readback 异常拒绝，无其他 key/file/backend fallback |
| F-005 | 固定启动 | Design 白名单模式、原公开 config/账户参数 | 原固定 BOT 子进程 | 非法模式/路径/绑定在 secret lookup 前拒绝，无 shell/eval/任意命令/透传尾参数 |
| F-006 | 最小子环境 | 精确 key 与既有 API 来源 | 仅目标子进程拥有 PM_PRIVATE_KEY | 父环境不变，竞争私钥拒绝，其他秘密不扩散；无秘密 argv/文件/日志 |
| F-007 | 兼容与验收 | 合成 store/TTY/child 替身 | 真实入口与 env seam 可测 | 不用 Rust synthetic 签名快捷路径冒充 helper 测试；原风险门禁不变 |
| F-008 | 显式登录 | 仅 check 的布尔 --sign-in；默认 false | 固定 check-venue 尾部追加 --sign-in | enroll/未知/缩写/透传参数仍拒绝；不直接调 SDK、不重写认证、不重试 child |
| F-009 | 登录成功核验 | child exit0、stdout 的唯一完整签名/登录行及合法账户 | §4.6 固定公开成功句 | 标记缺失/歧义/次序错/账户失配或 child 失败均非零，原输出/异常/秘密不外泄 |

## 4. 数据与接口契约

### 4.1 固定公开身份与私钥格式

- venue=Predict.fun，chain=56，原配置 `predict_fun.network=mainnet`，account mode=`predict-account`。
- trading address=`0xfc9eb66e6F22f96608058C0A711Ed048eED8c2E2`；signer=`0x5129330159f4E6a99eF873f86901E3cafa7f9A7D`。
- Binance 登录钱包 `0xb54b2b4667b33661f83f0d6aeebb1bfa295d03be`、新 agent-wallet `0x2FcDbb1a61f4A0439C9952710eDCe3cee071828c` 均不选；不允许通过 CLI/env 改选账户。主控提供的 block `133658449` owner 观察不冒充本卡实测控制证明。
- 私钥输入只接受 64 位 ASCII hex，可带一个 `0x` 前缀；无空值、空白、额外前缀/后缀或自动修复。复用已有 `eth_account.Account.from_key` 等已安装能力验证有效 secp256k1 标量并派生，不自制密码学。不得把原异常或输入打印出来。
- 录入前/启动前按合法解析后的地址字节比较 signer，不混淆 signer 与 trading address。合成测试只能通过内部测试注入选择公开测试身份，不开放生产“任意钱包”CLI。

### 4.2 TTY、keyring 与失败顺序

先解析公开参数与固定目标，验证 TTY/后端前提，再读取候选秘密。录入只读用户控制的 TTY，屏蔽回显；拒绝 stdin 管道、环境私钥、CLI 值、文件、剪贴板或 Hermes 代录。不能沿 `getpass` 的警告 fallback 继续有回显读取；失败/信号/EOF 必须恢复终端状态。录入不要求 API key，不联网、不签任何消息。

后端必须是当前 WSL 会话既有 `org.freedesktop.secrets`，login 集合且 unlocked；default 不指向 login 时拒绝，不修复别名、不启动/重启/解锁服务。只对本功能精确全属性搜索；只接受唯一正确集合/业务属性的条目；仅容许 V0.3 固定 schema 元数据，其他未知/重复/其他集合拒绝。允许的元数据检查不是枚举其他 item 的许可。

操作本身不得请求交互：不调用 Unlock 或 Prompt、不显示/等待密码框；如 API 返回需 Prompt 即失败，不执行 Prompt。超时、权限或 bus/集合错误均稳定失败，等待有界且不自动重试。沿既有固定 Jeepney 适配与9秒业务+1秒清理预算；仅预检 unlocked 后使用会自动解锁的普通 lookup/store 仍不合格。V0.5 不重新选择后端 API，不以历史 secret-tool 成功替代当前约束。

store 仅在目标尚不存在时进行；原条目存在即拒绝，不增加替换/删除管理功能。一次写入后重新精确搜索/读取，在内存逐字节核对后才输出已保存；写入/读回不明不能声明“已成功”或“绝未写入”，不得重试或删条目补救。launch 只读且再次派生核验，无存取失败后读旧文件或父环境 key 的备用分支。

### 4.3 固定子进程与现有配置接缝

`src/main.rs` 已有 `--config`、`--credentials`、`--venue predict-fun`、原预算/RPC 参数；`src/config.rs` 已有 `PM_PRIVATE_KEY`、`PM_PREDICT_API_KEY`、`PM_PREDICT_ACCOUNT` 覆盖。helper 必须显式绑定 venue、mainnet、目标账户；不能只验证 helper 的展示值却让子进程使用另一配置。

沿既有固定 binary=`BOT/target/debug/polymarket-toolkits`、cwd=BOT，不通过 PATH/env 指定任意可执行文件，不 `cargo run` 隐式构建。显式 `--credentials` 固定 `BOT/tools/predictfun/.keyring-no-credentials`，`lexists=true` 即拒绝（含悬空链接），不能落回默认 `config.yaml`。公开 JSON 严格要求 venue=predict_fun、network=mainnet、mock_trading=true、enable_trading=false，拒绝重复键/credentials 字段，必须是显式普通 .json 文件；不读 YAML/.env 验证“没有私钥”。预算门禁沿原 CLI，不自建审批或自动确认。

无模式时只展示用法/拒绝，不启动。普通 check 只交原 `check-venue`，联网读市场/盘口、签未提交样例但不 Terms/登录；显式 --sign-in 才接受 Terms 并认证核验账户，仍不提交订单。不得把 config/live/env 作为隐式升级，不透传 SDK approve/redeem 或任意策略入口。工程测试两分支均只用 fake child，不带真实凭据执行 binary。

### 4.4 环境与秘密边界

启动前检查父环境存在 `PM_PRIVATE_KEY` 即拒绝，只查键存在性，不读取/比较其秘密值；不在 keyring 失败时继承它。legacy credential 文件完全不进入 loader；其他 venue 的 `PM_*` 凭据不得透传此子进程。

保留既有 `YQUANT_PREDICT_FUN_TOKEN -> PM_PREDICT_API_KEY`：helper 从已由既有启动机制提供的源变量在内存映射，不自己 source/解析生产 `skills/.env`，不创建 API key 条目或修改来源。源缺失/空白拒绝；若父进程另带 `PM_PREDICT_API_KEY`，只允许与源一致，冲突拒绝，不暗中择一。子进程只需接收目标 `PM_PREDICT_API_KEY`，不额外复制源别名。

子环境从 Design 白名单显式构造，保留必要 OS、代理/CA 等原运行条件，不全量复制环境；不继承无关凭据、其他账户或加载注入变量。代理配置如含认证信息，只沿既有必要网络环境传递且不得日志输出，不宣称白名单内每个值都公开。固定 `PM_PREDICT_ACCOUNT` 为选定 trading address。keyring 工具若必需接收秘密，只能受控 stdin/内存，不能秘密 argv；也不得继承 BOT 私钥/API key。禁止修改全局 `os.environ`、shell profile/export、临时文件或转交 SDK资金工具。

错误只输出固定 `code/step/reason`，不透传输入、异常链、底层 stdout/stderr、Secret Service 返回体、环境字典、请求或签名。成功只报公开地址/完成状态。退出即尽量释放秘密引用，不承诺 GC、swap/core dump 或同 UID 物理隔离。

### 4.5 拒绝语义

错误类别为 `INVALID_INPUT`（模式/格式/配置）、`TTY_REQUIRED`（无安全输入）、`ACCOUNT_MISMATCH`、`BACKEND_UNAVAILABLE`（含锁定/需交互）、`CREDENTIAL_MISSING`、`STORAGE_FAILURE`（含重复/已有条目/写后不明）、`ENV_CONFLICT`、`LAUNCH_FAILED`。既有细分 reason/exit/有界 timeout 保持，新登录证据错误固定于 §4.6；不新增交易状态机。启动前拒绝不启动 child；child 已启动后的退出或证据失败只报告真实状态，不重启/重试签名或交易。

### 4.6 V0.5 显式 sign-in 输入、输出与证据契约

输入仅扩展既有 `local_signer.py check --config <公共JSON> [--sign-in]`，--sign-in 是无值布尔开关，默认 false；仅 check 子命令接受。不接受 `--sign-in=true`、缩写、未知/尾参数、任意命令/argv、钱包或 binary 覆盖；错误不回显参数，先拒绝再访问秘密。enroll、无命令及 --help 的原语义保留。

child argv 仍为 `[固定绝对binary, --config, 绝对公共JSON, --credentials, 固定缺失路径, --venue, predict-fun, check-venue]`；仅显式登录在尾部增加一个字面 `--sign-in`。shell=false、close_fds=true、stdin=DEVNULL，单次 child、60秒超时及终止/回收不变；父环境不改写，最小 env/API映射/冲突规则与 keyring 核验完全相同。普通分支 stdout/stderr=DEVNULL 不变；登录分支仅在内存接收 stdout/stderr，不写临时输出文件、不重跑 helper/child、不新增网络/SDK调用。

原 Rust 事实（静态来源：`src/main.rs:61–67,199–201`，`src/service/predict_fun.rs:1372–1509,1656–1727`）：先 GET 市场/盘口、`place(..., false)` 签未提交样例，再 GET /auth/message、认证签名（接受 Terms）、POST /auth、GET /account。JWT 只留原 Rust 内存，不向 helper 输出或持久化。`authed_text` 的 ReadOnceRefresh 在认证 GET 遇401时会清 JWT、再登录并重读一次；不能承诺单次 helper 必然只做一次 HTTP 认证，也不更改该既有行为。

stdout 的既有成功标记仅以下两类（不是本卡运行结果）：

1. `signing        ok: 1 share would cost <金额> USDT (not submitted)`；金额语法为 `[0-9]+(?:\.[0-9]+)?`（完整有限非负 ASCII 十进制数），不接受正负号/指数/任意文本/NaN/Infinity；只核结构，不输出或保存金额。
2. `sign-in        ok: API identifies you as <账户>`；账户严格为一个 `0x` 加40位 ASCII hex，先完整格式校验，再按20字节与固定 `0xfc9eb66e6F22f96608058C0A711Ed048eED8c2E2` 比较；允许合法 hex 大小写，不 strip/补前缀/截断/修复 token。

必须完整按行匹配固定字面文本，各恰好一次，签名行先于登录行；不做子串/宽松大小写/ANSI清洗或从 stderr 提取。候选标记前缀行畸形、重复（即使内容相同）、顺序相反、任一缺失均为歧义/无效证据。非标记的市场/盘口等其他文本只丢弃，绝不转发。Rust 创建 signer 失败会打印 `signer         none (...)` 后 `Ok(())`，因此 exit0 本身不够；上述两个标记与账户匹配以及 exit0 缺一不可。

| 模式/结果 | stdout（固定句，末尾换行） | stderr / exit |
|---|---|---|
| enroll 成功 | `Saved and independently verified.` | 空 / 0；原语义不变 |
| 普通 check 成功 | `Check child completed; no trading authorization implied.` | 空 / 0；仅 child 完成，不升级为签名/认证证明 |
| 显式登录成功 | `Sign-in verified for Predict Account 0xfc9eb66e6F22f96608058C0A711Ed048eED8c2E2; no trading authorization implied.` | 空 / 0；只在全部核验满足后输出 |
| 登录证据缺失/畸形/重复/顺序错 | 无成功句 | 固定 JSON `code=LAUNCH_FAILED, step=launch, reason=EVIDENCE_INVALID` / 1 |
| 唯一且格式合法的登录账户失配 | 无成功句 | 固定 JSON `code=LAUNCH_FAILED, step=launch, reason=AUTH_ACCOUNT_MISMATCH` / 1 |

新增错误同样仅 code/step/reason 三字段；畸形/重复优先按 EVIDENCE_INVALID 处理，不从不可信文本拼 reason。child 启动/非零/信号/超时仍按既有 LAUNCH_FAILED 的 START/EXIT/SIGNAL/TIMEOUT、exit1，先判 child 失败，不因残留成功标记放行。参数错误仍 INVALID_INPUT/args/ARGUMENTS、exit2，既有其他错误保持。失败不宣称“认证绝未发生”：POST /auth 可能已发生，仅 helper 不能确认成功，不自动重试。

stdout/stderr、TimeoutExpired/其他异常、签名、JWT、API key、私钥及其长度/摘要不得转发/记录/持久化；不得将原文本放入 JSON、异常链、报告、任务字段。成功只输出上表固定公开账户（不是复制任意捕获字符串），校验完即尽量释放输出/秘密引用，不承诺物理清零。helper 不消费 token，不记录 HTTP 原响应；仍保留同 UID/管理员及子环境/内存的既有威胁边界。

## 4.bis 持久化契约

以下是既有本功能字段级逻辑契约，不是新的全局 store schema；沿原 Design 固定 Secret Service 字面属性名/用途前缀及密钥规范表示。V0.5 不新增持久秘密或 JWT 存储；条目属性仅供精确归属，不形成交易许可。

| 对象 | 字段 | 类型 | 必填 | 规则 | 生命周期 | 隐私 |
|---|---|---|---|---|---|---|
| login item attributes | purpose | string | 是 | 本地 Predict signer 独有含版本命名空间，隔离历史 Privy 和 SDK 条目 | 随条目；未知版本拒绝 | L0 |
| 同上 | chain | string | 是 | 固定 56 | 同条目 | L0 |
| 同上 | account_mode | string | 是 | 固定 predict-account | 同条目 | L0 |
| 同上 | trading_address | string | 是 | 合法地址的规范表示，与固定身份一致 | 同条目 | L1 |
| 同上 | signer_address | string | 是 | 合法地址的规范表示，与派生地址一致 | 同条目 | L1 |
| login item secret | private_key | secret string/bytes | 是 | 唯一私钥，不含 JSON session、API key、JWT 或其他密钥 | 用户显式本地录入创建；无 TTL/自动更新 | L3，既有明确选定的 OS store 例外 |

唯一性必须由精确搜索并检查条目数/归属实现，不能假定后端天然唯一索引。无 DB/表/索引/TTL、普通文件、session 集合、自动迁移、备份或清理其他条目；旧非导出 session 不读取。已有目标拒绝覆盖，失败不自动回滚/删除，真实替换/移除另行具体处理。测试仅在全属性唯一的 disposable namespace 中创建自身 synthetic item，结束后清除该项并精确确认不存在，不能触及生产属性对应记录。

## 5. 验收标准

下表 A-001–009 为既有基线要求，V0.5 不重新实现；后续仍跑完整 helper 受影响回归并新增 S-001–005，不能只跑新 flag 正例。此表不是本卡已运行结果。

| 编号 | 场景与必须结果 | 验证方式 |
|---|---|---|
| A-001 | PTY 遮蔽输入、EOF/取消恢复；非 TTY/回显关闭失败在读 key/store 前拒绝 | 实际 helper + PTY 捕获/termios 断言及受控失败注入，不只 mock 输入函数 |
| A-002 | 公开 synthetic key 真派生匹配；空/坏hex/零/越界/登录钱包或其他 signer 不存不启动 | 使用既有真实库派生 + 实装校验；store/child 调用计数 0 |
| A-003 | 精确唯一条目写入/独立读回，已有/重复/错集合/错属性/损坏 key 拒绝 | 实装存储适配 + 隔离 fake API；计数和精确属性断言，不是预造成功 |
| A-004 | locked/missing/unavailable/Prompt/超时/存储或读回失败均停止 | 实装适配的底层接缝注入；Unlock/Prompt/自动重试/文件 fallback 调用 0；不锁共享后端 |
| A-005 | 固定 binary/命令/config/chain/account；任意命令、改钱包、错网、隐式 live、默认 YAML 路径拒绝 | 真 parser/argv 构造及 fake child 捕获；拒绝发生在 key lookup 前 |
| A-006 | 仅目标 child 获 PM_PRIVATE_KEY/API key/account；父环境不变；竞争私钥/API冲突拒绝 | 实际 launch seam + 无网 fake child，内存断言 env/argv/cwd；禁止执行真钱 binary |
| A-007 | 正常 API 来源映射保持；其他秘密/加载注入变量不传 child 或 keyring 工具 | synthetic 源值/无关秘密哨兵；源缺失/冲突/白名单/代理保留反例；生产 .env 访问 0 |
| A-008 | 各错误/取消/child失败不泄露、不 fallback、不重启；真实 key 访问 0 | 扫描 stdout/stderr/异常/日志与文件写入 spy，合成 secret 哨兵不得出现 |
| A-009 | helper 真实消费者与短说明一致，Rust signer/原预算门禁/SDK资金工具不变 | 独立候选 diff、定向原工具回归及真实入口合成 e2e；不运行任何真钱 check/sign-in/run |

| 编号 | V0.5 新增工程验收（仅 synthetic/fake child/隔离 transport） |
|---|---|
| S-001 | 实际 main/parser：普通 check 未加登录 flag 且保留原输出/DEVNULL；显式 check 仅尾加固定 --sign-in；enroll --sign-in、带值/缩写/未知参数及钱包/binary/任意 argv 透传在 lookup/child 前拒绝 |
| S-002 | 实际 launch seam：exit0 + 唯一完整签名行 + 后续唯一匹配账户行才成功；合法 hex 大小写接受，stdout 只出固定成功句；证明未走 SDK/新认证核心 |
| S-003 | exit0 无 signer/无标记、缺任一标记、仅 stderr 标记、子串/错大小写/ANSI/畸形金额或地址/前后缀、重复同值或冲突/错序、合法错账户均关闭；child非零/信号/超时即使带成功行也失败，错误码按 §4.6 |
| S-004 | 在 stdout/stderr/启动及超时异常注入 synthetic key/API/JWT/signature/代理秘密哨兵；成功和失败均无原文/秘密/长度/摘要外泄，无输出文件/父环境改动；单 child、不重试，超时有回收 |
| S-005 | 登录分支保留固定 binary/cwd/缺失 credentials、strict mainnet/mock/enable_trading、固定 chain/account、最小 env/API来源与冲突、keyring拒绝/no Prompt/no Unlock/no fallback；完整回归及README消费者用法一致，受保护Rust/SDK/依赖/配置零修改 |

验收层次：独立 Validate 的 PASS 只代表 V0.5 离线工程；此后主控审核，沿用户本次一次认证授权执行一次真实 helper 调用（不是保证只有一次内部 HTTP 认证），按相同标记/账户/exit规则判断。真实成功只能归档固定公开状态/账户、候选身份和必要公开执行元数据；不保存原输出/秘密/摘要。缺失授权、环境或 runtime 安全拒绝即停止并说明，不能以 offline PASS 代替 real auth PASS，不追加自动重试或交易动作。证据按需入 `data/reports/YYYY-MM-DD-predictfun-keyring-signin/evidence/` 与同主题唯一 `report.md`，日期用工具确定；本卡不新建报告。

## 6. 测试要求

测试随 `tools/predictfun/tests/`，用既有隔离环境与标准库测试设施；注入 store/child/TTY 等最小依赖，不增加公共测试后门、钱包配置或 generic store 框架。测试用公开已知、永不充值的合成 key；生产固定账户的 mismatch 要走真实校验，测试成功身份只能内部注入。实际 launch seam 必须进入子环境构造/调用，不以预造 dict 或单独测试 helper 函数代替。

独立 Validate 记录候选、实际命令/exit、覆盖/未覆盖；无 Rust delta 不要求重跑整仓交易验证。沿既有 `tools/predictfun/tests/test_local_signer.py` 完整 unittest 回归，Design 细化新增测试，不伪造当前不存在的测试名。V0.4 真实后端 synthetic 证据只读复用，V0.5 工程 worker 仅 fake child/隔离 transport，不为登录补证访问生产 keyring 或执行真实钱包 binary。

用户真实 provisioning 声明不冒充本卡实测；真实签名/认证、当前 keyring 解锁状态、冷启动、网站控制和交易能力均非工程 PASS 证明范围，不以 fixture 冒充。开发者自测不替代独立 Validate；主控真实认证与工程验收严格分离，交易始终不在此次授权内。

## 7. 实现约束

仅 workspace `/home/pascal/workspace/yquant-investment`，不改 `/home/pascal/workspace/yq-yinglong`、其他 profile、Hermes 核心/配置、服务、安全策略、调度、生产库或 Git history/gitlink。共享树 dirty 为上游基线，path-filtered 归属，禁止 reset/stash/clean/checkout/commit/push。runtime 拒绝后立即停止，不改工具/路径绕过。零 Rust/SDK/依赖/配置 delta，不安装/升级任何包；若不能在三个允许文件内完成则报告具体缺口，不自行扩张。组件增量估算见 RFC §10，不是代码行数硬门禁。

历史 D-1 单包例外已属于已验收基线，不是 V0.5 安装许可：既有 `jeepney==0.9.0` 与 wheel SHA256=`97e5714520c16fc0a45695e5365a2e11b81ea79bba796e26f9f1d178cb182683`、隔离 `.venv`、[Design §3.4](../../design/07_trading/DESIGN-07-003-predictfun-wsl-nonexport-signer.md#secret-service-adapter) 固定方法/9+1秒预算不变。五业务属性精确核验及可选固定 `xdg:schema=org.freedesktop.Secret.Generic`、写入 `text/plain; charset=utf-8`/读回仅两精确 `text/plain; charset=utf-8` 与 `text/plain`、相同 session/空 parameters/64位规范小写 ASCII key/真实派生匹配全部保留，不放宽或重新实现。

## 8. 开放问题

与 RFC §11 同步：开放业务契约项0，D-1/D-2 既有接缝已经实现并以 V0.4 synthetic 基线验证；不重开存储/架构。下一 Design 仅细化 §4.6 的参数接线、严格标记提取/错误与 S-001–005 测试，行为/账户/API来源不交实现者再决定。

本轮 RFC/SPEC 可交主控检查，预建 Design 仍 operator-held，须从 V0.4 同步为 V0.5 并消除旧拒绝 sign-in/待实现叙述；三层一致与主控 Design Gate 后才实现。旧非导出阻塞不再生效，不额外创建激活平台、新阶段或替代任务图；真实认证未执行不阻塞本卡文档交付。

## 版本记录

| 版本 | 日期 | 更新内容 |
|---|---|---|
| V0.2 | 2026-11-15 | 本地TTY/keyring固定入口，取代旧非导出路线 |
| V0.3 / V0.4 | 2026-11-15 | 历史schema/content-type修复，V0.4仅synthetic interoperability独立PASS，原REVISE/拒绝不改判 |
| V0.5 | 2026-11-15 | check专属显式sign-in，固定输出/标记与账户核验，普通check/enroll兼容，工程与主控真实认证分离 |