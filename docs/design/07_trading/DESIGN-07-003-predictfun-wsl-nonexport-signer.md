# DESIGN-07-003: Predict.fun WSL 本地私钥 keyring 最小入口

> V0.5（2026-11-15，Asia/Shanghai）：在已验收 V0.4 helper 上仅接入 check 专属显式 `--sign-in`，默认普通 check/enroll 不变。复用固定 Rust `check-venue --sign-in`；仅登录分支内存接收输出，按 SPEC §4.6 严格核验 child exit0、唯一完整签名行、其后唯一完整登录行及固定 Predict Account。§3.6 定义最小接线，§5 对应 S-001–005；不改后端/依赖/Rust，不执行真实签名或认证。

以下两段保留 V0.4 修复当时的范围与失败记录；相关 finding 已由 §2 的 V0.4 synthetic 独立 PASS 闭合，不是 V0.5 待实现项、后端测试要求或真实访问授权。原失败与 runtime 拒绝不追溯改判。

> V0.4（2026-11-15，Asia/Shanghai，Pascal 已同意继续）：只闭合已定位的 GetSecret 内容类型兼容。写入仍固定 `text/plain; charset=utf-8`；读回仅接受两个精确字符串 `text/plain; charset=utf-8`、`text/plain`，不做 strip/大小写归一/前缀或任意 MIME 匹配，其他值和类型仍拒绝。已闭合的五业务属性精确核验及可选固定 `xdg:schema=org.freedesktop.Secret.Generic` 保持不变；session、空 parameters、64位规范小写 ASCII key、真实派生 signer 校验不放宽。只改 BOT `tools/predictfun/local_signer.py` 与 `tools/predictfun/tests/test_local_signer.py`，依赖/README/Rust/CLI/SDK/旧证据只读。本轮独立 Validate 须跑完整受影响回归及一轮新唯一 synthetic namespace 的真实 login create、独立进程 read、定点清理和成功空搜索；不接真实 key、不签名/认证/交易、不改服务或安全配置。

> 闭合清单与用户重锚：V0.2 离线 helper 已验；V0.3 schema 窄修复经26项回归和33个独立案例通过，但真实读回仍 REVISE；新授权诊断已证明唯一不一致是 content type（其余字节/派生校验均通过），测试条目已清理。来源为现有同主题报告 `schema-validation.md` 与 `evidence/getsecret-diagnosis-8551b398e666463ca14b029a4b8ec472.json`。当前仅此内容类型 finding 开放，不重开 schema/架构；下文原阶段工作/未实装状态句为 V0.2 阶段记录，不作为当前重新设计要求。原失败证据及 runtime 拒绝保留，不以修订改判 PASS。

## 元数据

| 项 | 值 |
|---|---|
| 状态 | V0.5 Design 候选：既有 V0.4 synthetic 基线保留；显式 sign-in 待主控 Design Gate、Implement 与独立 Validate，非交易许可 |
| 作者 | YQuant Principal |
| 创建 / 最后更新 | 2026-11-15 / 2026-11-15（Asia/Shanghai，UTC+08:00） |
| 来源 RFC | [RFC-07-003](../../rfc/07_trading/RFC-07-003-predictfun-wsl-nonexport-signer.md) V0.5 |
| 来源 SPEC | [SPEC-07-003](../../spec/07_trading/SPEC-07-003-predictfun-wsl-nonexport-signer.md) V0.5 |
| 目标模块 | 07_trading；同 BOT 的 tools/predictfun/ |

## 1. 设计摘要

只给既有本地 keyring helper 增显式登录 flag 与公开证据核验，不动原 signer、策略、认证实现、订单或风控。Pascal 的本地导出决定已取代旧非导出方案；`nonexport` 文件名仅保留历史编号，run3711 不改写，旧 Agent Authorization 不是当前阻塞。

既有 D-1 采用 `jeepney==0.9.0` 的序列化/同步 transport，薄调固定 Secret Service 方法，已随 V0.4 synthetic 基线验收；§3.4 仅保留其协议，不重选、不重装、不重实现。WSL/POSIX 单线程9秒业务+1秒清理总预算不变。D-2 的固定 child 接缝亦已存在；本次仅沿 §3.6 扩展布尔参数、stdio 分支和证据校验。本卡只做静态文档核对，不把既有证据写成本 run 新实测。

## 2. 现状与复用边界

`BOT=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。主仓 HEAD `546518b222708022da0ef8b708cdeba2ad1ad8e6`；BOT HEAD `0b8b31092cbd660a53ced463734c4673de055ed9` 为上游记录。V0.2 当时的 clean 状态不是当前声明；当前 dirty 为上游基线，按精确路径归属，不 reset/stash/clean/checkout/commit/push。

- V0.4 `t_1b2754f0` 已独立 PASS，仅 synthetic interoperability；[content-type-validation.md](../../../data/reports/2026-11-15-predictfun-local-keyring/content-type-validation.md) 为既有30项回归、56个独立案例及不同进程 create/read/cleanup 的来源。沿已核对 helper SHA256=`438b67a4b60b091cfb8a6c7f9dace1e28a407f737ce8612285d1c1c9da66399c`，schema/content-type 不重开；本 run 不重跑该后端验证。
- 用户本人 enroll 成功仅为主控传入用户声明，worker 未访问生产条目。主控[普通 check 证据](../../../data/reports/2026-11-15-predictfun-local-keyring/evidence/authorized-check-76642cc133ed41519fc3fc72d6d6b8e2.json)只证明单 child exit0，未独立观测样例签名，更不能证明登录。该证据记录 debug binary SHA256=`7302b4760d6fa90c43a7df40c439ccb1a92fb2ecb7f14926b5c5b3f966f315e6`，重建成功为主控报告，本 run 不执行/构建 binary。真实认证尚未执行。
- 本卡沿 run3726 已核对的 Rust 事实：`predict_fun.rs:1686–1691` 无 signer 可返回 Ok(())/exit0；`:1713–1725` 提供 §3.6 的字面标记与 opt-in；`:1372–1509` 是原认证及 GET401 ReadOnceRefresh；`fills.rs:157–192` 的 live=false 签样例后不提交。此处复用已有核对，不称新运行证明。

- `src/main.rs:17–69,170–203` 已有 JSON/credentials 路径、venue 与 check-venue；`src/config.rs:596–649` 先读可选 YAML，再应用 PM 环境覆盖。因此仅给 PM_PRIVATE_KEY 不足以阻止旧 YAML 被读取。
- `src/service/predict_fun.rs:1281–1315,1353–1369` 已以 PrivateKeySigner 和 predict_account 形成账户；mainnet 部署 chain=56，不需修改 Rust。`check:1656–1727` 联网读取市场并签未提交样例；无 sign-in 时不接受 Terms、不获取 JWT、不提交订单。
- `tools/predictfun/requirements.lock:13` 锁定 eth-account==0.14.0；现有 sdk_ops.py 已用 Account.from_key。继续使用同目录隔离 Python 与既有 Jeepney，不安装/升级或引入新密码学。本卡未执行导入验证，历史被拒可用性探针不重放。
- V0.1 静态核对的 libsecret-tools/libsecret-1-0=0.20.5-2 不具备所需 store 语义，因此不复用 secret-tool。存在 GIO 动态库不等于允许新增 FFI；选定路线无需 GI、SecretStorage 或系统 Python 包。
- 复用 [07-002 closeout](../../../data/reports/2026-11-13-predictfun-live-foundation/closeout.md) 的离线签收及 [WSL report](../../../data/reports/2026-11-15-wsl-native-credential-validation/report.md) 的历史合成存取证据，不重开策略/执行/资金工具，也不重复 backend 基线。

## 3. 方案设计

### 3.1 后续最小文件 allowlist

本 Design 卡只修订本文件；RFC/SPEC V0.5 只读且上游 Gate 已通过。主控 Design Gate 后的 Implement 仅允许以下三个既有 BOT 相对路径：

| 文件 | 最小职责 |
|---|---|
| tools/predictfun/local_signer.py | check parser 增布尔 flag、launch_check 的固定尾参数与 stdio 分支、私有证据校验、main 的固定成功句；不改 TTY/store/env，不 import 资金工具 |
| tools/predictfun/tests/test_local_signer.py | 更新旧拒绝 sign-in 用例和 TemporaryBot；新增 S-001–005 的真实入口/fake child 反例，完整保留既有回归 |
| tools/predictfun/README.md | 小增显式用法、默认兼容、Terms/签名副作用、公开输出及工程/真实认证分离；不重写旧章节 |

不改 Rust、cli.py、sdk_ops.py、Cargo manifest/lock、requirements.in/lock、配置或其他项目/profile；不安装/升级包。只有一个 helper，不加服务、store 框架、认证核心、调度或额外运行组件；不改既有 `.venv/`/wheel。增量规模沿 RFC §10 的估算，不是行数硬门禁，不为压行数省校验或扩展功能。

### 3.2 数据流与唯一启动模式（D-2 决策）

CLI 仍只有 `enroll` 与 `check --config <明确公共JSON路径> [--sign-in]` 两个子命令；--sign-in 仅 check 的无值布尔开关，默认 false，不接受带值或缩写。缺命令显示固定用法并退出2，`--help` 退出0且零秘密访问。parser 禁止缩写、error 为固定错误，不回显 argv/未知参数。enroll --sign-in、尾参数、命令/可执行文件覆盖、钱包/chain 覆盖、TUI、run 和 SDK approve/redeem 透传仍拒绝。保留原 CLI 与风险门禁，不另造确认系统。

- enroll：参数/竞争环境/TTY/后端元数据与目标不存在检查并断开 → 用户遮蔽输入 → 格式/真实派生匹配 → 新连接重复元数据/不存在检查、单次 create、不替换并断开 → 再新连接精确搜索/独立 GetSecret 读回 → 内存比较后才成功。无 API key 要求，无 provider 联网或签名；TTY 等待不占 D-Bus 预算。
- check：公开路径/JSON/固定 child 校验 → API 来源与冲突校验 → 精确 keyring 读取 → 格式/派生匹配 → 构造单独子环境 → 单次启动既有 `check-venue`。默认联网、签未提交样例，不 sign-in/Terms/JWT；显式 --sign-in 才由原 Rust 接受 Terms、认证并核验账户，仍不提交订单。工程 worker 两分支仅用 fake child/隔离 transport，绝不带真实凭据启动。

BOT 根由 `Path(__file__).resolve().parents[2]` 定位，不靠 cwd、PATH 或环境指定。固定 child 为 `BOT/target/debug/polymarket-toolkits`，cwd=BOT；缺失、非普通文件或不可执行即在 lookup 前拒绝，不 cargo run/自动构建/换 release 路径。本卡不执行或声称重新核验二进制制品。

check 的公共参数必须是显式现存普通 `.json` 文件，解析后要求 venue=`predict_fun`、predict_fun.network=`mainnet`、bot.enable_trading 严格为 false、bot.mock_trading 严格为 true；拒绝重复 JSON 键、畸形对象、credentials 字段、非 JSON/YAML/env 路径。仓库默认 config.json 是 polymarket/testnet，必须拒绝；本卡不为其改配置或写另一个 mainnet 配置。用户以后自行提供公共配置，不由 helper 隐式修复/升级网络或 live 标志。

child argv 固定为 `[绝对binary, --config, 绝对公共JSON, --credentials, BOT/tools/predictfun/.keyring-no-credentials, --venue, predict-fun, check-venue]`；仅显式登录尾加一个字面 `--sign-in`。保留的 credentials 路径必须 `lexists=false`（含悬空链接均拒绝），helper 不创建它、不读默认 config.yaml。shell=false、close_fds=true、stdin=DEVNULL；普通分支 stdout/stderr=DEVNULL，登录分支内存 PIPE 见 §3.6。只报固定结果，原生输出及异常不得转发。等待最多60秒，超时终止/回收单个 child，不自动重启；非零或信号退出先判失败。无预算/RPC/策略参数，因为本入口不执行 run；原 run 的预算、账户、授权和风险检查完全不变。

### 3.3 TTY、格式与环境接缝

local_signer.py 的 `main(argv)` 只负责装配 `enroll()` / `launch_check(config, sign_in=False)` 与固定结果；已有 `read_key_tty()`、`validate_key()`、`build_child_env()` 等接缝保留，可在 unittest 内注入底层 API/child 与公开 synthetic identity，但不开放生产测试 flag、任意 binary 或钱包 CLI。

- TTY：stdin 与 stderr 必须是同一实际 TTY；拒绝 pipe/file，不能绕到 getpass 的回显 fallback。以 termios 保存状态、关闭 ECHO/ECHONL 后读取，finally 恢复；EOF、Ctrl-C、SIGTERM/SIGHUP 处理需恢复终端。输入至多66个 ASCII 字符（含可选前缀），限量读取并要求单行终止；超长/多行拒绝，不把合法前66字符当成功；finally 丢弃未消费输入避免退出后落入 shell。只去掉终端行终止符，不 strip 用户内容。无法确认关闭回显时不读 key、不 store。
- 私钥：只接受 ASCII `[0-9a-fA-F]{64}` 或一个小写 `0x` 前缀，Account.from_key 真正校验标量/派生地址。存储形式固定为无前缀64位小写 ASCII bytes；启动读回须已经是此规范形式。比较合法解析后的地址20字节；不签名验证地址、不打印异常。固定 signer=`0x5129330159f4E6a99eF873f86901E3cafa7f9A7D`，trading address=`0xfc9eb66e6F22f96608058C0A711Ed048eED8c2E2`；两个未选钱包保持 SPEC §4.1 的排除，不提供改选。
- 父环境只检查 PM_PRIVATE_KEY 键存在性即 ENV_CONFLICT，不读其值，enroll/check 均不接收环境候选 key。PM_PREDICT_ACCOUNT 若存在但不等于固定地址则拒绝，不静默改选。
- check 从已提供的 YQUANT_PREDICT_FUN_TOKEN 原样映射 PM_PREDICT_API_KEY；缺失/空白拒绝。父 PM_PREDICT_API_KEY 若存在须与源逐字相同，否则拒绝；不解析/source skills/.env，不把源别名传 child。enroll 不访问 API key。
- child env 只继承已存在的 HOME、USER、LANG、LC_ALL、LC_CTYPE、TZ、HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/NO_PROXY 及其小写形式、SSL_CERT_FILE/SSL_CERT_DIR；固定 PATH=/usr/bin:/bin、RUST_LOG=warn，再添加本次 PM_PRIVATE_KEY/PM_PREDICT_API_KEY/固定 PM_PREDICT_ACCOUNT。不继承其他 PM_*、PYTHONPATH/PYTHONHOME、LD_* 或无关 token。代理/CA 变量可能敏感，不输出白名单值。父 os.environ 不改写。
- 无秘密 argv、temp file、shell export/profile、SDK资金工具或其他辅助子进程。helper 只输出固定 code/step/reason 或公开完成状态；退出释放引用，不宣称内存物理清零。

### 3.4 Secret Service 薄适配（D-1 决策）

<a id="secret-service-adapter"></a>

enroll 的唯一写入目标是已存在的 WSL login collection；default 必须等于 `/org/freedesktop/secrets/collection/login` 且当前 unlocked。不初始化后端、服务/集合/别名，不读取其他 item，不解锁。固定全属性为：purpose=`yquant.predictfun.local-signer.v1`、chain=`56`、account_mode=`predict-account`、trading_address=`0xfc9eb66e6f22f96608058c0a711ed048eed8c2e2`、signer_address=`0x5129330159f4e6a99ef873f86901e3cafa7f9a7d`。Label=`YQuant Predict.fun local signer v1`，secret 为 §3.3 的 ASCII bytes，content type=`text/plain; charset=utf-8`，不存 API/session/JWT。

精确全属性 SearchItems 后检查 unlocked+locked 总数（含跨列表重复路径）、login 路径归属、五项业务 Attributes 精确相等及可选固定 schema（仅允许 `xdg:schema=org.freedesktop.Secret.Generic`，无其他额外属性）；先数目/归属再取唯一自有项元数据，不遍历其他项。无匹配才能 enroll，已有拒绝，重复/属性不符/其他集合拒绝；check 必须唯一 unlocked，Collection.Locked 与 Item.Locked 都为 false。item 必须位于 `login路径 + '/'` 下，不能只比较无边界字符串前缀。create 返回非根 item、prompt=`/` 后才进入独立读回，读回 item 路径须等于 create 返回路径。无 TTL/轮换/迁移/替换/删除命令；写入结果不明不重试、不自动删记录。无跨进程唯一索引；并发导致重复时读回拒绝，不宣称已保存成功。

#### 固定依赖与 transport

既有固定 `jeepney==0.9.0`：官方 PyPI 的 `jeepney-0.9.0-py3-none-any.whl`，SHA256=`97e5714520c16fc0a45695e5365a2e11b81ea79bba796e26f9f1d178cb182683`，MIT、基础包无必需运行依赖、无 extras。V0.2 的单包批准已用于既有实现，不是 V0.5 下载/安装或修改 requirements 的许可；直接复用隔离环境与原 pin/hash，不重建、不重新解析 lock。此节保留 transport 契约，不引入未实装依赖项。

既有 helper 的私有薄适配承担连接、固定调用、归属核验与 `_create_owned` / `_read_owned`，无可配置 backend/插件；以下保留协议职责，不要求按旧设计函数名重构。固定使用 `jeepney.bus.get_bus('SESSION')` 解析当前已有地址；先要求 DBUS_SESSION_BUS_ADDRESS 非空、只含单一 `unix:` 地址（拒绝分号多地址及 autolaunch/TCP），不发现/启动 bus。以 `jeepney.io.blocking.prep_socket(addr, enable_fds=False, timeout=1.0)` 获取已认证 socket，再 `DBusConnection(sock, enable_fds=False)` 发送库内 Hello；这是复用该固定版本已有 transport，不复制认证/编码。必须在调用构造器前持有 sock，构造/Hello 异常也在 finally 关闭它；构造成功则 `conn.close()` 关闭 selector/socket。便利 `open_dbus_connection(auth_timeout=...)` 内 Hello 无 reply 上限，不能把 auth_timeout 当整段限制。

固定调用接缝仅装配下表方法：`new_method_call(DBusAddress(path, bus_name=destination, interface=interface), method, signature, body)`，设 `msg.header.flags = MessageFlag.no_auto_start`（值2，不带 allow_interactive_authorization），用 `conn.send_and_get_reply(msg, timeout=...)`；不使用会自动 Prompt 的包装。先调用 bus 的 GetNameOwner 取得当前 `org.freedesktop.secrets` 唯一 owner，后续本连接的全部 Secret 调用 destination 固定该 unique name，失联即停、不重新找 owner/激活。严查 message_type、预期 reply signature/body/variant 类型；只内部映射 error_name，不 stringify DBusErrorResponse（含返回体）。Hello 由库发给 bus 本身，不会激活 secrets。

| 对象 / interface / 方法 | 输入 signature 与 body（Python tuple） | 输出 signature / 必须验证 |
|---|---|---|
| `/org/freedesktop/DBus` / org.freedesktop.DBus / GetNameOwner | `s`，`('org.freedesktop.secrets',)`；destination=org.freedesktop.DBus | `s`，非空 unique name；NameHasNoOwner 直接 unavailable，不 StartServiceByName |
| `/org/freedesktop/secrets` / org.freedesktop.Secret.Service / ReadAlias | `s`，`('default',)` | `o`，严格等于固定 login 路径，不修改 alias |
| login / org.freedesktop.DBus.Properties / Get | `ss`，`('org.freedesktop.Secret.Collection', 'Locked')` | `v`，variant=`('b', False)`；IsLocked 或 true 立即停 |
| service / org.freedesktop.Secret.Service / SearchItems | `a{ss}`，`(完整固定attributes,)` | `aoao`，unlocked、locked 两列表；只允许 §3.4 的计数/归属 |
| 唯一自有 item / org.freedesktop.DBus.Properties / Get | `ss`，分别 `('org.freedesktop.Secret.Item', 'Locked')` 与 `('org.freedesktop.Secret.Item', 'Attributes')` | `v`，分别 `('b', False)`、`('a{ss}', 五项固定attributes加可选固定schema)`；不读其他项秘密 |
| service / org.freedesktop.Secret.Service / OpenSession | `sv`，`('plain', ('s', ''))` | `vo`，output=`('s', '')`、session 为非根 object path；不协商其他算法 |
| login / org.freedesktop.Secret.Collection / CreateItem | `a{sv}(oayays)b`，`(properties, (session, b'', key_bytes, content_type), False)` | `oo`，item 自有、prompt=`/`；任何非根 prompt 立即 PROMPT_REQUIRED，不 Prompt/Dismiss/等待 Completed |
| 唯一自有 item / org.freedesktop.Secret.Item / GetSecret | `o`，`(session,)` | `(oayays)`，返回 session 相同、parameters=`b''`、content_type 只接受 `text/plain; charset=utf-8` 或 `text/plain` 两个精确字符串，value 为64位规范小写 ASCII bytes，再真派生核验 |
| 已开 session / org.freedesktop.Secret.Session / Close | 无 signature / body=`()` | 空 body；finally 单次尽力关闭，随后总是断开 bus |

properties 只含 `org.freedesktop.Secret.Item.Label: ('s', 固定Label)` 与 `org.freedesktop.Secret.Item.Attributes: ('a{ss}', 固定attributes)`；不设其他字段。plain 是既有本地 session bus 的明文传输算法，空字符串/空 bytes 是协议协商/参数，不是空 keyring 密码；不创建/改密码或后端。接受该选择在本进程、bus、服务及同 UID/管理员边界中的明文暴露，不引入 DH/AES/cryptography 或强隔离承诺。不支持 plain 即失败，不降级另一后端。

每个操作先验证 alias/unlocked、精确搜索；存储前再次检查不存在以涵盖用户输入期间变化，读取前只为唯一合法自有 item 开 session。create 只调用一次 replace=false；返回成功后关闭本连接/session，再以新连接独立 `_read_owned` 搜索/取元数据/OpenSession/GetSecret，与候选内存比较。check 在 `_read_owned` 完成并清理后才构造 child。锁竞态由原始方法的 IsLocked 拒绝处理，绝不 Unlock。服务未知回复形状/业务属性变化或非允许的额外元数据直接失败；create 已尝试后不能把 timeout/断连/异常说成“绝未写入”。

#### 总超时与清理（不是只给 reply timeout）

入口只支持 WSL/POSIX 主线程、同步单连接，不起后台线程或 watchdog 服务。每个后端阶段安装 `signal.setitimer(signal.ITIMER_REAL, 9.0)`，SIGALRM handler 直接抛专用超时异常；monotonic 截止时间=开始+9秒。覆盖 get_bus、socket connect/auth、库内 Hello（可能默认无限等待）、sendall 和 receive/select/解析，不依赖 syscall 自动返回。每次显式方法调用另设 socket timeout 与 reply timeout 均为 `min(2.0, 剩余预算)`；耗尽前直接拒绝，不发新方法。库认证 `prep_socket` 的1秒是附加限制，不是总限制。禁止非主线程或已有活动 ITIMER_REAL 的嵌入调用，缺 signal 支持即 unavailable；不暗中回退为无界/线程等待。

finally 先停业务 timer；有 session 则在新的最多1秒 SIGALRM/socket/reply 清理预算中单次 Close（即使业务已超时），然后无条件关闭连接或构造前取得的 socket、恢复原 handler/无活动 timer。Close 错误不掩盖原失败；无原失败时也失败停止，不带 key 启动 child。总后端阶段预算最多10秒；断开即按 Secret Service 契约释放会话/未完成 prompt，即使 OpenSession 已执行却没收到 path 也不会残留可继续使用的会话。连接前异常无 session，直接清理；不重试 Close/重新连接补救。

enroll 最多三个后端阶段（预检、单次 create、全新连接读回），各≤10秒，合计≤30秒后端等待，用户 TTY 思考时间不计；check 两分支均仅一个≤10秒读取阶段，child 仍独立限60秒。所有错误/取消路径都走 finally；SIGINT/TERM/HUP 的受控退出亦清理，SIGKILL/主机崩溃仅 OS 断连保证，不承诺进程终止前执行 Python finally。以上为既有实现/回归要求，随完整 helper 回归保留，不是本卡新运行观测。

### 3.5 错误与 UI

无图形 UI；TTY 只显示固定遮蔽输入提示和公开结果，不输出输入长度/摘要。错误输出 JSON 三字段 code/step/reason，step 限 args/tty/identity/backend/store/readback/env/launch；禁止原异常、堆栈、D-Bus 返回体、child 原输出和环境字典；登录证据仅产出 §3.6 的固定状态。

退出2：INVALID_INPUT（ARGUMENTS/KEY_FORMAT/PUBLIC_CONFIG/CHILD_PATH/CREDENTIAL_PATH_PRESENT）、TTY_REQUIRED（NOT_TTY/ECHO_UNAVAILABLE/CANCELLED）、ACCOUNT_MISMATCH（SIGNER）、ENV_CONFLICT（PRIVATE_KEY_PRESENT/API_SOURCE/API_CONFLICT/ACCOUNT）。退出1：BACKEND_UNAVAILABLE（UNAVAILABLE/LOCKED/PROMPT_REQUIRED/TIMEOUT）、CREDENTIAL_MISSING（ABSENT）、STORAGE_FAILURE（EXISTS/DUPLICATE/OWNERSHIP/CREATE_UNKNOWN/READBACK/CORRUPT）、LAUNCH_FAILED（START/EXIT/SIGNAL/TIMEOUT；登录另加 EVIDENCE_INVALID/AUTH_ACCOUNT_MISMATCH，见 §3.6）。未进入 CreateItem 前连接/权限/不存在owner/协议错误为 UNAVAILABLE，锁定为 LOCKED，超时为 TIMEOUT；唯一项不存在为 ABSENT；格式损坏为 CORRUPT。进入单次 CreateItem 后结果不明统一 store/CREATE_UNKNOWN，已创建而独立读取或 Close 失败为 readback/READBACK；已有原失败时不以清理异常覆盖它。明确 Prompt 回包仍报 PROMPT_REQUIRED，并提示固定“未确认保存，不自动重试”语义。无继承环境 key、读文件、改后端或重启 child 的分支。退出0按模式仅表示保存并读回一致、普通 child 正常退出，或显式登录证据与固定账户核验通过；均不表示交易授权。

### 3.6 V0.5 显式登录最小接线与严格证据核验

本节实现 SPEC §4.6，不增加认证业务。对现有 `local_signer.py:415–467` 做局部扩展：

1. 仅 check 子 parser 加 `--sign-in` 的 `action=store_true`、默认 false；保持两层 allow_abbrev=false 与固定 parser.error。main 在 check 分支传 `args.sign_in` 给 `launch_check(config, sign_in=False)`，enroll 分支不读取该字段。旧直接调用 `launch_check(config)` 保持普通模式。没有公开 argv、binary、账户或凭据覆盖口。
2. 先原样走 `_check_paths`、`_check_environment`、`_api_source`、`_read_owned`、`build_child_env`，禁止新增 store/SDK/provider 调用。按 §3.2 构造 argv，仅 sign_in 为 true 时 append 固定 `--sign-in`。仍只一次 `subprocess.run(..., timeout=60, check=False)`；普通分支两个输出 DEVNULL 不变，登录分支两个输出 PIPE、保持 bytes（不做有损解码或 stderr 合并）。由 run/communicate 同时消费并在超时 kill/wait 回收单 child，不引入 Popen 重试循环或输出文件。
3. 先判启动异常、TimeoutExpired、returncode，再核验登录 stdout。原 START/TIMEOUT/EXIT/SIGNAL、exit1 映射不变；异常不 stringify、不附原文/异常链，TimeoutExpired 的 output/stderr 同样不可转发。不能用成功标记覆盖 child 非零/信号/超时。保留 child env clear/key 引用释放；所有完成/失败路径亦尽量释放 result/stdout/stderr 引用，不作物理清零承诺。
4. 只新增一个私有、纯内存的证据检查函数（建议 `_verify_sign_in_output(stdout: bytes) -> None`）；只返回成功或固定 Failure，不返回捕获金额/账户/原行。仅扫描 stdout，按 LF 分行、只移除行分隔符，不 strip、ANSI清洗、大小写或 Unicode 归一。以 `b"signing"`、`b"sign-in"` 开头的候选行必须严格 fullmatch 下列 bytes 模式；任一候选畸形即记无效，不能当无关市场文本忽略。其余行只丢弃；带额外前缀/ANSI 的行不能作为成功证据，不做子串搜索。只计两类合法完整行各自数目及先后位置、保留至多一个经格式校验的地址，不保存金额或原行副本；不得遇到首个正例就提前成功，必须扫完排除后续重复/畸形候选。

   签名行模式：`rb"signing        ok: 1 share would cost [0-9]+(?:\.[0-9]+)? USDT \(not submitted\)"`。
   登录行模式：`rb"sign-in        ok: API identifies you as (0x[0-9a-fA-F]{40})"`。

   金额只做 ASCII 十进制结构检查，不转 float、不输出/保存；符号、指数、NaN/Infinity、非 ASCII 数字拒绝。账户先完整格式验证，再由 hex 解析20字节与固定 TRADING_ADDRESS 比较，允许合法 hex 大小写但不修复 token。stderr 永不作为证据。无 signer exit0、缺任一行、重复同值/冲突、错序或畸形候选都报 `Failure("LAUNCH_FAILED", "launch", "EVIDENCE_INVALID")`；结构/唯一/顺序全部成立而合法账户不匹配才报 `Failure("LAUNCH_FAILED", "launch", "AUTH_ACCOUNT_MISMATCH")`。畸形/重复优先于账户失配；两者均 exit1。内存解析的意外异常也只映射固定 EVIDENCE_INVALID，不落到可泄露原异常的输出路径。
5. main 仅在 launch_check 返回后选择固定成功句（末尾换行）：enroll 为 `Saved and independently verified.`；普通 check 为 `Check child completed; no trading authorization implied.`；显式登录为 `Sign-in verified for Predict Account 0xfc9eb66e6F22f96608058C0A711Ed048eED8c2E2; no trading authorization implied.`。stderr 为空，exit0。登录成功句使用固定常量，不复制捕获账户/金额。任何失败均无成功句，stderr 仍仅 code/step/reason 三字段，不输出原 stdout/stderr/异常、私钥/API/JWT/signature、秘密长度或摘要，不写日志/文件/任务字段。

原 Rust 先 GET 市场/盘口并签未提交样例，再 GET /auth/message、签认证消息接受 Terms、POST /auth、GET /account；JWT 只在原 Rust 内存。原 GET401 ReadOnceRefresh 可清 JWT、再登录并重读一次；“一个 helper child、60秒、无 helper 重试”不等于“一次 HTTP 认证”。证据失败/超时可能已发生认证，不能声称绝未认证；只能说 helper 未确认成功并停止，不自动重试。普通 check 不升级为签名/认证证明。

## 4. 实现顺序

沿预建 Kanban 图，不重建或自行解锁 Implement/Validate。RFC/SPEC V0.5 上游 Gate 已通过；本候选交主控 Design Gate（独立文件/同版来源/三文件 allowlist/接线及验收一致）后由主控释放既有 Implement。最小实施顺序：①在现有测试文件增 S-001–005，记录旧 helper 的 RED；②按 §3.6 局部接线，不改存储/依赖/Rust；③完整 helper GREEN 与必要原工具定向回归、短 README；④交独立 Validate 实际运行同候选并裁定。每步记录真实命令/exit、候选身份及未测；任何 runtime 新拒绝停止，不改安全策略或换工具/路径重放。

## 5. 测试策略（后续执行，不是本卡结果）

复用已存在的测试文件与隔离环境，在 BOT 根运行完整 `tools/predictfun/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_local_signer.py -v`。基线30项为既有独立报告结果；本卡不运行、不虚构新增测试函数名或测试数。Implement 记录新增用例旧实现 RED 与最终完整 GREEN；独立 Validate 必须实际执行候选完整套件，不能仅引用开发者自测。

### 5.1 V0.5 必需增量与 SPEC S-001–005 对应

全部测试只用公开 synthetic identity、隔离 transport 与无网 fake child；真正走 main/parser、路径校验、keyring 读取/派生、env 构造及 subprocess 接缝，不能用预造成功 dict/只测私有 regex 代替真实消费者。底层错误可注入，但不能 mock 掉本次待验逻辑。

| SPEC | 最小测试接线与断言 |
|---|---|
| S-001 | main 普通/登录对照，捕获完整 argv/cwd/env/stdio：默认无 flag 且两输出 DEVNULL，显式仅尾加一次 --sign-in 且两输出内存 PIPE；enroll --sign-in、--sign-in=true、--sign 缩写、未知/尾参数、钱包/binary覆盖均 exit2、固定 ARGUMENTS、不回显，lookup/child=0；help/无命令及 enroll 原语义回归 |
| S-002 | 真实无网 fake child 发 exit0、唯一完整 signing 行与其后唯一匹配 sign-in 行；分别以合法混合/大写 hex 地址测试，输出只能是固定成功句+换行、stderr 空。断言一次 child、无 SDK/第二认证调用；账户比较不以捕获字符串拼输出，金额0/整数/小数均按结构接受 |
| S-003 | 按表驱动实际 main/launch：exit0 无 signer/无标记、缺任一行、仅 stderr 标记、子串/额外前后缀/错大小写/ANSI、符号/指数/NaN/Infinity/非ASCII金额、短/长/坏hex/空白地址、重复同值/冲突、错序、完整正例之后再附畸形候选，均 EVIDENCE_INVALID/exit1；唯一合法错账户才 AUTH_ACCOUNT_MISMATCH/exit1；重复+错账户优先 EVIDENCE_INVALID。非零/负returncode/TimeoutExpired 即使带完整成功行仍按 EXIT/SIGNAL/TIMEOUT，不放行；启动异常 START。失败均无成功句 |
| S-004 | 在 stdout/stderr 及启动/超时/解析异常中注入 synthetic key/API/JWT/signature/代理秘密哨兵，检查 helper stdout/stderr/JSON、日志及文件写入 spy 均无原文/秘密/长度/摘要、无异常链输出；成功分支夹杂非标记秘密文本亦不转发。断言父环境不改、child计数1、无输出临时文件/重试；至少一条受控无网 child 实测 timeout kill/wait 回收，不仅 mock 抛 TimeoutExpired（测试内缩短等待可注入，不开放生产 timeout flag） |
| S-005 | 显式登录复跑固定 BOT/binary/cwd、credentials lexists/悬空链接拒绝、strict JSON/mainnet/mock=true/enable_trading=false、chain56/account、API映射及冲突、env白名单；所有启动前拒绝 child=0。沿隔离 transport 证明 missing/locked/重复/错归属/坏schema或content-type/损坏key拒绝及 no Prompt/Unlock/fallback。跑完整 helper 回归、核 README 两模式用法与固定输出，精确候选diff证明受保护 Rust/SDK/Cargo/requirements/配置不变 |

两个既有碰撞点必须最小调整，不删除合法反例：`test_local_signer.py:202–207` 不再把合法 check --sign-in 作为拒绝用例，改为 enroll --sign-in/带值/缩写等仍拒绝场景，合法分支转入 S-001/002；`TemporaryBot:720–727` 原 `sys.argv[-1]=='check-venue'` 保留普通模式断言，再用内部测试场景选择登录尾参数及合成 stdout/returncode，不宽松接受任意尾参数。fake executable 只在当前 profile scratch 下的 TemporaryBot 创建，不改生产 BOT binary，不将秘密写入脚本/配置/断言失败消息或制品。

### 5.2 既有 A-001–009 完整回归保留

- A-001/002：实际 main/enroll + PTY 驱动，捕获输出及 termios 状态；关闭回显失败/pipe/EOF/信号恢复，非法 hex/零/越界/错 signer 时 store/child=0。已知 synthetic key 真正走 Account.from_key，成功身份仅在测试内部注入；生产默认身份必须 mismatch。
- A-003/004：既有固定调用接缝进入真实 Jeepney new_method_call/Message.serialise/Message.from_buffer，以 fake socket/transport 返回合成 reply，不把整个 store 换成恒成功。断言表中全部方法/signature/variant、flags=2、unique owner 固定、replace=false、精确属性/路径/locked/duplicate/未知 extra 属性及错 schema 拒绝、缺省/固定 schema 接受、读回两种精确 content type 接受且其他值/错类型拒绝、Prompt/错误回包/畸形返回、独立新连接读回及会话 Close/断连。Unlock/Prompt/Dismiss/StartServiceByName/自动重试/其他项 GetSecret=0；create 后超时及读回/清理失败不输出成功，失败阶段不启动 child。
- 总超时实测：在实际 helper 后端入口分别注入 connect/auth、构造器 Hello、sendall、reply 的停滞（包括 transport 不理 timeout、持续无关消息），外部 unittest 受控子进程 watchdog 仅作测试兜底；必须由 helper 自身9+1秒预算先退出，不把测试 watchdog 杀死记为通过。计时断言单阶段≤10秒+1秒调度容差，检查 timer/handler、socket 和 session 清理；另测 Close 停滞≤1秒+容差、无 session path 时只断连、非主线程/已有timer拒绝。缺真实时间推进的单纯 mock timeout 不是此项证据；测试不连接共享 bus/锁服务。
- A-005–008：实际 main/launch_check 进入 env+subprocess 接缝，以无网 fake child 捕获 argv/cwd/env/stdio/timeout；断言父环境不变、API映射与冲突、固定账户/网络/命令、旧 YAML 绝不读、无 fallback。注入其他秘密/代理哨兵，检查仅必要代理保留，秘密不出日志/错误/argv/文件；child失败不重启。不执行 Rust 钱包 binary。
- A-009：实际 enroll→独立 lookup→check 的合成消费者路径贯通（隔离底层 API），短说明与 parser 一致；原 test_sdk_identity.py、test_sdk_ops.py 按影响选必要回归，沿既有 unittest discover，不改资金工具/增加公共测试命令。不重跑整仓 Rust，无 Rust 变更时以精确候选 diff 证明原 signer/风控/资金工具未动。
- V0.4 真实 backend synthetic interoperability 只读复用；V0.5 不新建/删除 backend 条目、不查询生产 purpose 或其他 item、不锁/重启集合，不以登录补证重开 backend 流水线。全部本轮工程测试 fake child/隔离 transport，生产 keyring/skills/.env/真实 key 访问0，真实钱包 binary 执行0。

独立 Validate 使用候选真实 helper、fake child 与隔离 transport，记录命令/exit、候选 HEAD/路径/hash、覆盖与未覆盖；开发者自测或历史 secret-tool 成功不能代替。工程 PASS 只证明离线接线与核验，不能证明真实录入、当前 keyring 解锁、签名/认证、网站控制、交易、冷启动或同 UID 隔离。

### 5.3 工程与主控真实认证的分离

独立工程 PASS 后由主控审核，才沿用户本次一次认证授权执行一次真实 helper 调用，使用相同 exit/唯一完整标记/账户规则；worker 不执行、不要求用户重录 key、不通过文档或 fake child 冒充真实成功。一次 child 不承诺一次内部 HTTP 认证；失败停止不追加重试或交易。真实归档只含固定公开状态/账户、候选身份和必要公开执行元数据，不保存原输出/异常/秘密/秘密摘要。后续证据如需归档按 SPEC §5 的同主题唯一 report/evidence 目录；本 Design 卡不新建报告。缺授权/环境或 runtime 新拒绝即停并说明。

## 6. 风险、降级与回滚

无可用非交互接口或总预算能力时唯一降级是停止，不落普通文件、不接环境备用 key。后端/读回错误不自动重试/删除；真实条目替换或移除另行明确处理。V0.5 登录证据缺失/变化时失败关闭，不放宽 regex、不转发日志排障、不尝试 SDK/备用钱包/重启认证。失败不代表认证绝未发生，已发生的 Terms/POST auth 不能靠软件回滚撤销；本入口不持久 JWT。

最小软件回滚是停用新增 --sign-in 分支，保留已验收 V0.4 enroll/普通 check/精确存储。必要时由后续获准修复在三个实现文件内撤销本次增量及同步说明/测试，不用 reset/stash/clean/checkout 覆盖共享 dirty；不卸依赖、不改 Rust/配置、不删除 keyring item、不要求重录。接受同 UID/管理员对 keyring、明文 session bus、内存/child-env 及同用户可改 binary/配置/预留缺失路径的既有威胁边界；不声称能抵抗其并发替换或 SIGKILL，不增加签名服务、状态机或生命周期管理。

## 7. 交接条件与来源

开放业务契约项0。D-1/D-2 的既有接缝已实现并以 V0.4 synthetic 基线验收；V0.5 增量只在 §3.6，三文件 allowlist 见 §3.1，S-001–005 与完整回归见 §5。RFC/SPEC V0.5 来源 SHA256 分别为 `d4abea75ed898350fb253d67df333b9c29e40203e67d8cf47d89c11c49981b2d`、`439d4ee38ed2daffa9ccf727bd3c64fa3a53fa810656b2ab4f856ed430e9c837`，本 run 原生命令核对一致；输入不变才沿该冻结契约实施。

此为 implement-ready Design 候选，不是主控 Design Gate/独立工程/真实认证 PASS。既有 Implement t_3e832ebe 继续 operator-held，主控 Gate 后才可释放；沿其预建独立 Validate t_46bed243，不建新卡、不自行解锁。若不能在三文件内完成或必要测试与设计不符，报告具体缺口；runtime 新拒绝立即停止，不换工具/路径重放或改安全策略。任务状态/交接仅 Kanban，无阶段报告/data/tasks 镜像；不以文档完成增加真实凭据访问许可。

历史静态依据（2026-11-15；不是本 run 联网或动态验证）：[Jeepney 0.9.0 blocking 源码页](https://jeepney.readthedocs.io/en/latest/_modules/jeepney/io/blocking.html)、[wrappers](https://jeepney.readthedocs.io/en/latest/_modules/jeepney/wrappers.html)、[low_level](https://jeepney.readthedocs.io/en/latest/_modules/jeepney/low_level.html)（历史记录标题0.9.0，latest URL 非不可变 wheel）；[官方 Secret Service 方法/会话/plain/Prompt 契约](https://specifications.freedesktop.org/secret-service/latest-single)。wheel identity/MIT/依赖静态来源沿原阶段记录；GitLab 候选 tag URL 返回404不作为证据。run3712 被拒动态探针、run3713 D-1 阻塞及旧 Design run 被拒 execute_code 下载/解包请求均保留；V0.4 后续 synthetic PASS 不追溯改变这些记录。

本卡 run3726 组合静态基线/scratch 命令被 Security scan 拒绝，未执行、无快照/hash结果，保留原 Kanban comment。当前 run3728 仅沿 Pascal 新授权以普通文件工具修订本 Design、必要检查逐条原生命令，不重放旧形状、不增安全/模型/凭据配置、不联网或访问真实账户。本 run 未安装/导入库、未跑业务测试、未访问 keyring/.env/真实凭据，真实认证未运行；这些不因文档静态核对而改变。

## 版本记录

| 版本 | 日期 | 更新内容 |
|---|---|---|
| V0.1 | 2026-11-15 | 历史非导出路线；原 run3711 及其阻塞保留，不再生效 |
| V0.2 | 2026-11-15 | 本地TTY/keyring固定入口；D-1单包/9+1秒预算与D-2固定child设计 |
| V0.3 / V0.4 | 2026-11-15 | schema/content-type窄修复；V0.4 synthetic interoperability已独立PASS，历史REVISE/拒绝不改判 |
| V0.5 | 2026-11-15 | 仅check显式sign-in接线、严格公开证据/账户/固定错误与输出、S-001–005映射、默认兼容及最小回滚；工程与主控真实认证分离 |
