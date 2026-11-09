# SPEC-07-001: Predict.fun BTC 5m——M1 用户 fork 接入与原版基线

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft；T1 文档待主控校验，未 Implemented，非交易运行授权 |
| 作者 | YQuant Principal（yquantprincipal） |
| 创建日期 | 2026-11-09 |
| 最后更新 | 2026-11-09 |
| 版本 | V1.1 |
| 来源 RFC | [RFC-07-001](../../rfc/07_trading/RFC-07-001-predictfun-btc5m.md) V1.1 |
| 目标模块 | 07_trading |
| 适配 Agent | yquantdeveloper、yquanttester、yquantreviewer；主控 yquant |
| 工作区 | `/home/pascal/workspace/yquant-investment`；禁止修改 `/home/pascal/workspace/yq-yinglong` |
| 后续 Design | `docs/design/07_trading/DESIGN-07-001-predictfun-btc5m.md`（本卡不创建） |
| 来源任务 | t_24ca3fd4 |

## 1. 需求摘要

M1 只接入用户确认的 Toolkits fork，建立原版 Cargo 构建及业务离线测试基线，并校正必要 Trading 入口文档。子模块必须位于指定路径，工作树 main 跟踪 origin/main，主仓用 gitlink 固定实际版本。构建/测试前核查副作用，允许普通依赖下载，不运行机器人或连接钱包，不读取交易凭据。交付真实来源、版本、命令、退出码和测试分类证据，并由独立 Verify 重跑、Review 审查；本期不实现任何执行加固或研究策略增量。

## 2. 范围

### 2.1 In Scope

- 最小 RFC/SPEC/Design 三文件契约链（分阶段交付），已批准方案不再重新选型。
- 用户 fork 来源核验、submodule 登记与原版 main 基线；研究 SHA 与实际 fork SHA 差量。
- 审查后真实运行原版 `cargo build/test`，保留默认跳过及其他危险/联网测试分类；原策略/配置/锁文件不变。
- `skills/trading/SKILL.md` 与 `skills/trading/README.md` 仅修改与本次源码接入/已有 QuantDinger 源码状态直接相关的描述、路径、目录树和契约引用，不扩大运行能力。
- M1 结果与证据、独立复跑、差量缺口及原版基线后 C–H 重估。

### 2.2 Out of Scope

不创建远程 fork，不直接 clone upstream；不接入 polybtcbot/0xalberto 执行工程。不改业务源码、测试、Cargo.lock、依赖、策略参数/配置；不做 UNKNOWN/净份额/费用/挂单占用/预算恢复加固。不创建 Lab 空目录或模块级第二份正式 spec/design，不改 `quantdinger.py`，不做回放/模型/数据采集/夜报。禁止机器人运行（包括 dry-run/shadow）、交易所模拟订单、真实账户签名或连接、充值/approve/下单/撤单/merge/redeem、部署/长期调度、生产数据库写入/schema/索引、外部发送、公共 API/模板/profile/Hermes 变更及 commit/push。

### 2.3 精确文件边界

下表描述整个 M1，非赋予 T1 实现权限。T1 仅可创建/修订本 RFC、本 SPEC 和指定 `rfc-spec-handoff.md`。

| 类型 | 精确落位 | M1 允许动作 |
|---|---|---|
| 正式契约 | `docs/rfc/07_trading/RFC-07-001-predictfun-btc5m.md`、`docs/spec/07_trading/SPEC-07-001-predictfun-btc5m.md`、后续 `docs/design/07_trading/DESIGN-07-001-predictfun-btc5m.md` | 各阶段分别编写，契约变更同步，不把三层合并 |
| 主仓元数据 | `.gitmodules` | 只新增该子模块 section，不调整其他条目 |
| 主仓 gitlink | `skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits` | 仅一个 160000 记录，不逐文件跟踪内容 |
| 原版子模块 | 上述路径内部 | Git 接入、原版 build/test；不提交任何内容差量，构建 `target/` 等正常忽略产物除外 |
| 必要入口修改 | `skills/trading/SKILL.md`、`skills/trading/README.md` | 源码/验证/未授权运行状态和准确路径，不重写模块规划 |
| 后续结果新增 | `data/reports/2026-11-09-predict-btc5m-m1/report.md`、其 `evidence/` | 各阶段真实报告及脱敏日志，不伪造样本 |
| 过程新增 | `data/tasks/active/2026-11-09-predict-btc5m-m1/` | T1 `rfc-spec-handoff.md`；其余阶段仅必要交接 |

明确不动：旧 Intake 报告及其研究存档、`docs/rfc/07_trading/RFC-26-072-trading-intelligent-trading-framework.md`、三层模板/README、其他子模块、根 README、Strategy Lab 工具与实例、任何凭据/运行配置。固定子模块目录不存在时，不提前建同名普通源码目录；存在冲突不覆盖，报告主控。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | 接入前核验用户 fork | §4.1 已确认 URL、接入时读回 GitHub 元数据 | 确认记录及 parent/source 来源证据 | 当前输入已闭合；后续 404/无权限/来源不符停止接入，不自动创建或改用 upstream |
| F-002 | 指定位置登记 submodule | 已确认 fork main | `.gitmodules` path/url/branch、160000 gitlink、主仓 modules 管理的工作树 | 不用 upstream 代替 origin、不嵌套逐文件追踪 |
| F-003 | 保留原版并核对版本 | actual fork main、研究 SHA | main=origin/main=HEAD=gitlink、历史/锁/许可证核验与差量 | 不 checkout 研究 SHA，不同步 upstream，不改分支取绿灯 |
| F-004 | 识别构建/测试副作用与环境 | 实际 fork 文件、Rust/Cargo 版本、测试源码 | 安全审查范围、测试清单、命令计划 | 工具链缺失先报告，不自动安装或全机升级 |
| F-005 | 真实原版构建与安全离线测试 | 已审查的命令/目标、未改锁文件 | 每次日志、退出码、测试状态/计数 | 依赖下载可联网；业务网络/账户/凭据不可用；失败如实保留 |
| F-006 | 最小入口状态校正 | 实际接入与验证结果 | 两个 Trading 入口中的事实状态 | 不把代码存在/编译成功描述为已启用模拟或实盘 |
| F-007 | 独立 Verify 与 Review | 同一实际 SHA、Implement 证据、allowlist | 独立命令日志及逐项审查结论 | 不拿 Implement 日志当独立复跑，不因 skip 给全量通过 |
| F-008 | 基线后差量及 C–H 重估 | 真实原版结果及研究缺口 | 保留/缺失/未测清单、剩余估算及假设 | 未完成原版基线不得宣称已按结果重估；不延伸实现 |

### 3.1 决策落地

| 已定决策及来源 | 可观察行为 | 对应验收 |
|---|---|---|
| 用户要求自己的 fork；恢复授权确认来源；本卡禁止创建远程或当前 clone | F-001；§4.1/§8 输入已闭合，文档阶段不接入 | A-001 |
| 唯一 Toolkits 底座、同 fork 增量、Lab 直接子目录（本卡） | §2 文件范围；后续增量不得作为子模块兄弟工程 | A-007、A-008 |
| 原版优先、保留历史/锁文件/main（本卡及 Intake） | F-002..005，不改策略或测试 | A-002..005 |
| 完整流水线、角色独立（用户及项目协议） | F-007，独立日志及 Review | A-006 |
| 源码接入不等于运行许可（项目协议及本卡） | F-006；无 bot 启动/账户路径 | A-007、A-008 |
| 资金 200/100 已定、细则仍建议（本卡） | 不生成任何生效交易配置 | A-008 |

## 4. 数据与接口契约

### 4.1 输入、配置与兼容性

| 输入 | 规则 | 不接受 |
|---|---|---|
| `fork_url` | 已确认 `https://github.com/PascalMore/Prediction-Markets-Trading-Bot-Toolkits`；无内嵌密码/token；确认来源见 §8 | 根据用户名另拼 URL、Star、upstream URL 或未经确认的镜像 |
| `upstream_repo` | 研究来源恒为 `tarpboi/Prediction-Markets-Trading-Bot-Toolkits`，仅溯源 | 以该地址 clone 取代用户 fork；未经授权 fetch/merge 同步 upstream |
| `research_sha` | 精确保留 `71c0e4ff9e299f9a4d81757fd6b15cf54da69b38` | 把它当强制 checkout 版本或声称就是 actual fork main |
| `submodule_path` | `skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits` | `auto_trading`、其他大小写/层级、逐文件拷贝 |
| `branch` | `.gitmodules` branch、工作树当前分支均为 `main`，工作树上游 `origin/main` | detached HEAD；别的分支或自动改上游默认分支 |
| 运行配置 | 沿用原版文件，M1 不创建/读取交易凭据文件，不改交易参数或 network/live 开关 | 把建议阈值、生效资金、账户/API key 写入配置 |

除上述工程输入，无新 YAML、环境参数或业务 CLI。已有 package/bin 名称保持 `polymarket-toolkits`。现有子模块条目不变；新条目使用项目同样的 path 命名 section。确认 URL 可用 SSH/HTTPS 表达；SSH 等价地址为 `git@github.com:PascalMore/Prediction-Markets-Trading-Bot-Toolkits.git`，origin 与 `.gitmodules` 必须指向同一确认仓库，报告保留实际表示及用户确认来源，不接受凭据嵌入 URL。主控已核验该仓库 `fork=true`、`default_branch=main`，parent/source 均为指定 upstream；Implement 仍须按 §4.2 读回实际状态，不以本次文档同步替代接入验收。

幂等性：重复检查不重复加子模块、不覆盖目录、不主动 pull/升级 main；先读取现有 path、index、分支与 dirty 状态，匹配则验证并保留，冲突则停止接入并报告。子模块登记可产生该路径及 `.gitmodules` 的定向暂存，不代表允许 commit/push 或暂存其他文件。

### 4.2 来源、分支和 gitlink 的可执行判据

Design 应将以下只读观察落实成可复现操作；这些是验收接口，不是要求本卡执行接入命令：

| 观察 | 工具/命令形状 | 必须满足 |
|---|---|---|
| GitHub 来源 | 对用户确认 owner/repo 的只读仓库 API | `fork=true`；记录 `full_name`、`parent.full_name`、`source.full_name`，source 或可验证 parent 链追溯至指定 upstream；404/缺字段不假定通过 |
| 登记 | `git config -f .gitmodules --get-regexp ...` | 目标 section 的 path 精确匹配，url 为确认 fork，branch=`main` |
| 唯一主仓记录 | `git ls-files --stage -- <submodule_path>`，并检查该路径下的已跟踪项 | 恰一条 stage 0 的 mode `160000` 记录，无目录内部逐文件记录 |
| 当前分支与追踪 | 子模块 `git symbolic-ref --short HEAD`、`git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'` | 分别为 `main`、`origin/main`；不接受 detached HEAD |
| 精确版本 | 子模块 `git rev-parse HEAD main origin/main` 与主仓 gitlink 比较 | 三个 SHA 和 gitlink 全相同；记录核验时间，并以确认 fork 的 `git ls-remote ... refs/heads/main` 检查观测到的远端 main |
| 工作树归属 | 检查子模块 `.git` 文件，并解析其中 `gitdir`；主仓 `git rev-parse --git-common-dir` | `.git` 是文件而不是独立目录，解析路径位于主仓 Git common dir 的 `modules/` 内；正确处理相对路径 |
| 原版无修改 | 子模块 `git status --porcelain`、源码差量及 LICENSE/Cargo.lock 内容对比 | 没有业务/配置/测试/锁文件修改；构建忽略产物不视为代码差量；保留上游历史，不做 shallow/source dump 替代 |
| 研究差异 | 对 research SHA 与 actual SHA 的历史/文件差量；LICENSE、Cargo.lock 单独核对 | 记录是否相等、是否祖先、实际差量与已知缺口是否仍存在。与 actual main 不同本身不是失败，不能静默回退 |

远端 main 移动时，先报告观测不一致，不能自动 pull、重建基线或更新 gitlink；主控决定采用的新基线后需重跑受影响验证。若研究 SHA 对象不可取得，先利用已确认 fork 的历史与既有研究存档说明可核对范围；无法核实的差量标缺证据，不伪称已完成，不另 clone upstream 或 checkout 旧版本。

### 4.3 Cargo 与测试接口

- 安全审查对象至少包括实际 fork 的 `Cargo.toml`、Cargo 配置/别名及 `build.rs` 等钩子（如存在）、相关脚本、测试入口/辅助函数和配置加载路径；不能把当前不完整研究存档当全仓审查。遇到构建钩子有业务/凭据副作用，停止相关命令并报告，不能因它是 build 自动放行。
- 记录 `rustc --version`、`cargo --version` 及实际选用 toolchain。缺失或不兼容先报告，不猜 MSRV，不自动安装/升级。已有工具链和锁定依赖可使用；普通依赖下载与本地编译在范围内，依赖升级/改锁不在范围内。
- 最小真实构建为子模块目录中的 `cargo build --locked`；最小测试为审查后的 `cargo test --locked` 默认安全集合。默认 profile 足够，release/all-features/benchmark 不成为额外门槛。保留命令所有目标的真实结果，不只选 S0/S2 小集合冒充全基线。
- `cargo test --locked -- --list` 可在副作用审查后用于清单核对；它编译但不运行测试，不可当测试 PASS。若存在默认非忽略的危险测试，按实际完整测试名显式 `--skip <full_test_name>`，逐项说明，其他安全测试仍须真实执行；不改源码增加 ignore，不按 `live` 名称批量跳过，不运行 `--ignored`/`--include-ignored`。
- Cargo 的 `--offline` 只限制包获取，不拦截测试自身 socket；本 SPEC 的“业务离线”通过所选源码路径无真实场所/钱包/数据库 I/O 确认，不能只看 Cargo 参数。测试所需本地临时文件或 FakeVenue/本地 fixture 不属于生产操作，需与真实端点明确区分。
- 固定公开测试向量的本地签名/SDK 对拍单测可以运行；不得读取账户密钥、创建真实账户订单签名、登录或授权。不得照 README 运行 `cargo run`、二进制、`check-venue`、`--sign-in` 或任何 bot；默认 dry-run 也不例外。
- 失败保留原日志和退出码；不得通过改参数、断言、锁文件、依赖或底座策略取绿灯。不将联网失败重新标为离线测试 skip 以掩盖误执行。

## 4.bis 持久化契约

不新增数据库。下表是 `report.md` 的人工可读字段/表列契约，不要求开发 manifest、JSON schema、解析器或新报告平台。未测字段写“未运行/未知 + 原因”，不填推测值；只有实际未执行的命令 exit_code 才可为空，不能用 0 代替。

| 对象 | 字段/表列 | 类型 | 必填 | 默认/派生 | 生命周期/TTL | 隐私 |
|---|---|---|---|---|---|---|
| report.md 来源表 | task/stage | string | 是 | 真实任务 ID 与 Implement/Verify/Review | 保留本次记录，无 TTL | 工程内部 |
| 同上 | fork_url | string | 是 | §4.1 已确认 URL，保留接入时实际表示 | 同上 | 不含 token |
| 同上 | confirmation_ref | string | 是 | 主控转交的确认引用/任务评论 | 同上 | 不复制私人聊天 |
| 同上 | parent/source | string | 是 | API 读回仓库名及证据引用 | 同上 | 仅仓库来源 |
| 同上 | research_sha | string | 是 | §4.1 固定 40 位 SHA | 同上 | 工程内部 |
| 同上 | actual_sha | string | 是 | 实际 fork main SHA，未接入写未知 | 同上 | 工程内部 |
| 同上 | research_diff | string | 是 | 相等/祖先关系、差量及缺证据说明 | 同上 | 工程内部 |
| report.md 命令表 | cwd | string | 是 | 命令实际目录 | 同上 | 不含凭据路径内容 |
| 同上 | command | string | 是 | 精确可复现命令及选用版本 | 同上 | 不含秘密参数 |
| 同上 | started_at | timestamp string | 是 | 实际起始时间，带 UTC 或时区偏移 | 同上 | 工程内部 |
| 同上 | ended_at | timestamp string | 是 | 实际结束时间，带 UTC 或时区偏移 | 同上 | 工程内部 |
| 同上 | exit_code | integer/null | 是 | 真实进程退出码；未执行为 null 并写原因 | 同上 | 工程内部 |
| 同上 | evidence_ref | path string | 是 | 指向本主题 evidence/ 内真实日志 | 同上 | 脱敏后保存 |
| report.md 测试表 | test_name | string | 是 | 真实测试完整名及 lib/bin/doc 目标 | 同上 | 仅公开代码符号 |
| 同上 | category | string | 是 | 纯计算/本地 fixture（含 SDK 对拍）/真实联网/凭据或交易副作用 | 同上 | 无测试密钥值 |
| 同上 | result | enum string | 是 | PASS/FAIL/SKIP/NOT_RUN；依据实际执行 | 同上 | 工程内部 |
| 同上 | reason | string | 是 | skip/not_run 具体理由；PASS/FAIL 指命令日志 | 同上 | 不泄露账户数据 |
| report.md 结论表 | acceptance_id/result | string | 是 | §5 每项分别给证据与结论 | 同上 | 工程内部 |
| 同上 | remaining_gaps | string | 是 | C–H 保留/缺失/未测及原版后估算假设 | 同上 | 无收益承诺 |
| evidence/ 日志 | 原始命令输出及实际计数 | text | 是 | 按角色/阶段区分，Design 定日志文件名 | 各次独立保留，不覆盖原结果 | 不收集 env/config 凭据全文 |

测试计数按每次命令及 lib/bin/doc 目标分别汇总 passed/failed/ignored/filtered-out，和清单表核对，不把 ignored/filtered-out 加入 passed，不重复计算相同测试多次执行。默认忽略与显式 skip 分开列出，空测试集不构成安全离线测试通过。临时编译文件可沿 Cargo 默认规则存在，但本卡不执行全局缓存/目录清理。

兼容与恢复：现有其他子模块不迁移，既有报告不重写；本次各阶段在同一主题记录新增证据。未设置数据库索引/TTL，没有生产 schema 迁移。`data/` 按现行忽略规则本地保留，不自动公开/远程备份；结束由主控整体归档过程目录到 `data/tasks/done/2026-11-09-predict-btc5m-m1/`，不删除证据。后续业务状态默认 MongoDB，字段/集合/索引/真实写入另阶段明确；无新 SQLite 生产账本。

## 5. 验收标准

本表用于后续整个 M1；当前 T1 只验文档本身，不将下表标为已通过。每项都须有真实证据，缺证据为 NOT_RUN/未完成而非默认 PASS。

| 编号 | 验收项 | 验证方式及失败判据 |
|---|---|---|
| A-001 | 用户 fork 来源成立 | §8 用户确认记录 + 接入时 API parent/source 可追溯；来源错误为 FAIL，当前 URL 输入已闭合；不得 clone upstream 替代 |
| A-002 | 子模块结构/分支一致 | §4.2 登记、唯一 160000、`.git` 文件归属、main/origin/main/HEAD/gitlink 与观测远端 main；任何不一致未解决则 FAIL |
| A-003 | 原版及研究差量可核查 | LICENSE/Cargo.lock/历史保留；接入后工作树内容无改动；列研究差异与是否复现/未测。缺历史/差量证据不通过，不强制 actual SHA 等于 research SHA |
| A-004 | 构建实际成功 | 副作用审查、版本及 `cargo build --locked` 真实日志和退出码 0，构建后锁文件不变；工具链缺失/构建失败或改锁则未通过 |
| A-005 | 原版安全离线测试实际成功 | 审查完整实际测试范围后运行默认安全集合，退出码 0、实际非空安全测试通过；S0/S2 对应测试须覆盖；全部 ignored/skip 分类有理由且不算 PASS。安全测试失败/漏跑/空集/计数不符则未通过 |
| A-006 | 独立验证及审查闭合 | Tester 在同一 SHA 独立重跑 build/test 和来源/分支核验；允许依赖/构建缓存，不要求 clean build。Reviewer 核对三层文档、allowlist、来源/gitlink/日志及未实现边界；失败不能直接 Closeout |
| A-007 | 必要入口准确 | 两份 Trading 入口写实际源码路径、来源及验证状态，QuantDinger 已接入与 Toolkits 原版基线分开，仍明确无新增运行授权；不保留“候选目录未创建”等相关失实断言 |
| A-008 | 范围/副作用守约 | 主仓 diff/暂存和子模块内容差量、运行命令/报告审查：只有 allowlist，未启动 bot/访问交易凭据/业务端点/账户/生产库，无 Lab 空骨架/第二执行工程/公共 CLI 扩展；资金建议未成为生效配置 |
| A-009 | 基线后交接可复现 | report.md/evidence/ 含真实来源/时间/版本/退出码/测试计数，区分 C–H 缺口、未经验证风险及基线后的工期重估假设；无原版结果不得冒充已完成重估 |

M1 PASS = A-001..A-009 全满足。仅网络/副作用测试按已审查范围排除可满足 A-005，但结论必须限定为“原版构建及安全离线测试通过，联网/交易路径未验证”，不得称“全量测试/实盘通过”。构建失败可形成真实失败基线报告，但不能据此判 M1 完成，也不进入 C–H 实现。

## 6. 测试要求

### 6.1 现有单元/本地 fixture 基线

不增加新业务测试框架，先发现实际 fork 全部默认测试并审查。下列为研究 SHA 存档已见案例，需在实际版本核对存在/变更并运行，不冻结未经发现的全仓测试总数：

| 检查面 | 固定源码可见用例/证据 | 期望及边界 |
|---|---|---|
| S0 btc-arb | `src/bot/arbitrage.rs`：`buys_up_when_spot_has_moved_and_the_book_hasnt`、`buys_down_through_the_mirrored_book_when_spot_has_fallen`、`fees_count_against_the_edge`、`stays_out_near_the_end_and_before_the_start_price_is_known` | 原版断言通过；不等于实际费用净份额已正确、Chainlink 标签回放或真实 BTC5m 运行 |
| S2 Predict OBI | `src/bot/orderbook_imbalance.rs`：`imbalance_is_measured_over_the_configured_levels`、`heavy_bids_buy_yes_and_heavy_asks_buy_no`、`exits_on_profit_loss_or_time` 等 | 原版信号/退出单测通过；不等于 Binance OBI 或 5m 可运行 |
| Broker/runtime | `src/bot/runtime.rs`：`paper_take_walks_the_book_and_charges_the_taker_fee` 等 FakeVenue 单测 | 用本地数据运行，无真实钱包/订单；名称含 live 仍以实现分类 |
| Predict 适配及本地 SDK 对拍 | `src/service/predict_fun.rs` 的金额/映射/固定公开签名向量单测 | 仅离线 fixture，不能泛化为已验证提交/撤单/成交 |
| 原版其余安全测试 | 实际 main 的 lib/bin/doc 清单 | 不只挑上述测试；逐目标计数和失败记录 |

固定研究 SHA 中 `service::predict_fun::tests::live_large_trade_feed_reads_real_history` 与 `service::predict_fun::tests::live_testnet_dry_run_pipeline` 已带 `#[ignore = "talks to the Predict.fun testnet API"]`，位于存档 `predict_fun.rs:1979–2005`。M1 不启用它们；需在 actual fork 重新核对，不能假定永远只有两个联网测试。第二个虽叫 dry-run，仍读实时场所并构造签名路径，非 M1 离线集合。

### 6.2 Git 集成、回归与负向检查

- 真实接入检查覆盖 A-001..003；对不存在 URL、错误来源/分支、同名普通目录、独立 `.git` 目录、逐文件记录，规定为停止/FAIL，不实施破坏性构造实验。
- build/test 前后对比锁文件、LICENSE、子模块 tracked/untracked 状态；确保原版没有为绿灯被修改。
- `git diff`/暂存范围核对 `.gitmodules` 仅一个新增 section、仅该 gitlink 和两个入口相关状态变更；已有 QuantDinger 条目/代码不变。不为本次添加全仓测试、编译其他平台或调用其服务。
- 相对文档引用可解析；后续 Review 时三层正式文件均存在。当前 T1 只验证 RFC↔SPEC，未来 Design 用路径声明而非伪造现有链接。

### 6.3 不可由 M1 证明的事项

真实 API 参数/权限/费率/speed bump、Chainlink 实际结算标签与平价、UNKNOWN 对账、买入净份额、跨重启损失预算、撤单锁、钱包可用资金/兑付、策略净优势/盈利、账户地区资格、shadow 和实盘。它们按后续阶段处理，不能把本地单测或 upstream 文案当动态证据。

## 7. 实现约束

1. 来源、分支/gitlink、原版构建/测试和副作用门槛均来自本卡 M1 验收；不新增性能/覆盖率/收益阈值、观察日数或额外平台门禁。
2. 现成 S0/S2 必须复用，不重写多语言核心。研究 SHA 中 OBI `MIN_SECS_LEFT=600`，`tick` 调用 `is_quotable`，后者要求剩余时间不少于该值；因此不能声称现成运行路径已适配已开始的 5m 轮次。M1 原样保留并报告，后续 E 才评估差量。
3. 后续 C 在现有接口修复 UNKNOWN（不能以请求数量冒充成交）、净份额/实际费用、挂单占用和持久化预算/恢复；M1 无这些修复。Chainlink 指定结算/平价 50–50 与 BTC OHLC 非可执行二元 PnL 是后续硬边界，不在 M1 设计新数据契约。
4. 200 USDT/100 USDT 是用户本金及全实验损失约束，不是执行权限或保本承诺；1 USDT 单笔、5 USDT 占用、5 USDT 日停、20 USDT 复核仍为建议。本期不激活任何资金/交易配置。
5. Hermes 仅只读复盘/偏差/记忆，不持有真实签名、订单、运行控制或自动参数发布权限。参考仓库仅研究，不复制许可未清代码，不设第二执行器。
6. 不把缺工具链、网络失败或安全拒绝转化为无限修订契约；按真实错误交主控，禁止换执行器绕过审批。本期不安装/升级工具链或依赖，不 reset/stash/clean，不破坏性覆盖，不 commit/push。

### 7.1 错误契约

本表为阶段报告分类，不新增程序异常类/退出码或运行状态机。

| 情况 | 报告及动作 | 对完成的影响 |
|---|---|---|
| 已确认 fork 接入时 404/无权限 | 留只读证据并停止接入；不再次列为缺 URL、不自动新建或换 upstream | 当前文档输入已闭合；实际无法接入则 A-001 未完成 |
| fork 来源/分支/path 冲突 | 保留预期/实际和只读证据，停止相关写入，交主控 | 对应 M1 验收 FAIL/未完成 |
| 工具链缺失、不兼容、依赖下载/编译失败 | 保留原命令及真实退出码，不自动安装升级/改锁 | A-004 未通过 |
| 安全测试失败或实际范围漏审/漏跑 | 留原结果，不改断言/业务逻辑；先说明根因与范围 | A-005 未通过 |
| 测试依赖真实网络/凭据/交易 | 未运行前分类 SKIP/NOT_RUN 并写具体理由；默认 ignored 保持 | 非 PASS；安全集合满足时可作限定基线通过 |
| 执行结果未知、超时/被终止 | 记录真实终止事实，测试 NOT_RUN/未完成；不猜 exit=0 | 无完成证据，不能算 PASS |
| 验收通过但已知 C–H 风险 | 在总结保留“未实现/未测”，交主控排后续 | 不阻塞本期限定 M1 Closeout |

## 8. 开放问题

接入输入已闭合：用户确认 `https://github.com/PascalMore/Prediction-Markets-Trading-Bot-Toolkits`，主控已用只读 API 核验 `fork=true`、`default_branch=main`、parent/source 均为 `tarpboi/Prediction-Markets-Trading-Bot-Toolkits`。确认依据为任务 `t_24ca3fd4` 的恢复授权正文及主控 UNBLOCK 评论（2026-11-09，Asia/Shanghai）；本卡未重新请求 API 或 clone。此前 404 仅为早前快照，不再作为当前缺失输入。不再次索要 URL、授权新 fork 或重开架构；接入时仍按 F-001/§4.2 核验实际状态。

用户另确认 `https://github.com/PascalMore/predictfun-trading-bot`；主控核验 `fork=true`、`default_branch=main`、parent/source 均为 `0xalberto/predictfun-trading-bot`。它仅作研究参考，不部署、不进入本期子模块/构建范围；fork 存在不证明已取得代码复用许可。polybtcbot 同为研究参考。当前文档不要求账户、交易密钥、资金细则或实盘授权。

Design 的后续范围仅为 M1：精确文件 allowlist、子模块接入与核验操作、基于实际可发现源码的安全测试选择、证据落盘和定向可逆回滚/失败交接。不写 C–H 完整实现，不预建研究骨架；actual fork 的工具链/测试变化属于事实发现。M1 原版完成后再重估 C–H，后续复用同一契约集增量修订。

## 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0 | 2026-11-09 | M1 来源/结构/分支/原版 build-test/入口状态/独立验证契约；后续阶段不激活 |
| V1.1 | 2026-11-09 | 按恢复授权固定已确认 Toolkits fork 输入与 parent/source；0xalberto fork 仅研究，历史 404 不再是当前待输入；未实施 M1 |
