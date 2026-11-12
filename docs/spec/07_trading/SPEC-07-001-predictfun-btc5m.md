# SPEC-07-001: Predict.fun BTC 5m——M1 基线与 M2 同核心回放研究

## 元数据

| 项 | 值 |
|---|---|
| 状态 | M1/M2 限定离线工程已签收；M3 官方历史预测研究 V1.3 已获准 Light，待实现/独立验收；非交易授权 |
| 作者 | YQuant Principal（M1/M2）；YQuant 主控（M3 用户 Light 授权增量） |
| 创建日期 | 2026-11-09 |
| 最后更新 | 2026-11-12 |
| 版本 | V1.3 |
| 来源 RFC | [RFC-07-001](../../rfc/07_trading/RFC-07-001-predictfun-btc5m.md) V1.3；历史 M2 §13，本轮 M3 §14 |
| 目标模块 | 07_trading |
| 适配 Agent | yquantdeveloper、yquanttester、yquantreviewer；主控 yquant |
| 工作区 | `/home/pascal/workspace/yquant-investment`；禁止修改 `/home/pascal/workspace/yq-yinglong` |
| 后续 Design | `docs/design/07_trading/DESIGN-07-001-predictfun-btc5m.md` V1.3 §19 是本轮 M3 的最小实现契约；历史章节不重做 |
| 来源任务 | M1 t_24ca3fd4；M2 t_36000446 |

适用阶段（以下为 V1.2 历史说明，本轮 M3 另按 V1.3 §16）：§1–§8 及 V1.0/V1.1 版本记录是 M1 历史需求/接入快照；其中“本期禁止回放/Lab/改源码”等只适用 M1。M1 终态见 [最终签收报告 §13](../../../data/reports/2026-11-09-predict-btc5m-m1/report.md)，不是重新执行指令。§9–§15 为当前 M2 增量，验收编号使用 M2 前缀，不覆盖 A-001..009 历史结论；M3/M4/C–H 未因此启动。

## 16. M3 官方历史预测研究（V1.3 当前可计算契约）

本节来自 Pascal 2026-11-12 Light 决定及 RFC V1.3 §14，覆盖旧 M2 对新增官方历史入口的范围限制，旧 proxy 行为/安全负例保留；旧 M1/M2 Full Flow 不扩成本轮额外阶段。本节同时是 V1.3 变更记录。Design V1.3 §19 给出精确路径。

1. 数据唯一入口是现有 UnifiedDataClient.read_btc5m_history 与实例 iter_history_input；复用原合法连接显式注入 Btc5mHistoryReader，不新增UD接口/Provider、不直接旁路查询业务集合。生产只读、HTTP/交易/签名/付费job/调度变更均0。只读已有主窗 [2026-08-10T00:00:00Z,2026-11-12T00:00:00Z)，split=2026-10-10T00:00:00Z，as_of固定执行前当前UTC。全部94日/27072轮保留覆盖分母；IS61日、OOS33日，另列最新2日诊断，不改分区求通过。
2. 显式 event-time-proxy；每秒close仅于close_exclusive可用，时点t只能使用available_at≤t的输入。官方固定strike在starts_at后可用；身份遵守facade可用性，标签独立配对，end_price/outcome/resolved_at不得进入Rust估值输入。每个消费分片须完整消费features/metadata/labels并verify_consumed；content/raw来源与运行前后身份均可追溯。不得用as_of很晚放宽逐决策因果约束，不把理论可用性写成严格PIT。
3. 固定六个偏移30/60/120/180/240/270秒，剩余时间为ends_at-t（30秒边界有效）。Rust原参数不动，采用真实连续1秒价格路径更新唯一DecisionCore；不得逐日冷启动、将strike重新置为spot、把horizon固定300或在Python实现模型。若分片执行，须传原状态或从全窗起始精确连续重放；有限暖启动近似只能另列敏感性，不混进主结果。窗前数据不足不新增采集：首个窗口从已存首价初始化，保留min20returns预热及其排除数。
4. 研究输出与交易结果分开：新的隔离历史估值入口只接受价格与估值请求，不接受或生成book、订单、fill或venue状态。输出round_id、时点、strike、spot、剩余时间、samples/sigma/p_up及可估值原因；保留旧replay/proxy输入验证和输出不变。离线计价core调用不等于实盘执行模型一致性。
5. 方向p>0.5判UP、p<0.5判DOWN、p=0.5 abstain；实际DRAW单列、不强判某侧。方向准确率分母仅非DRAW且已给方向的样本，abstain不计胜负但单列覆盖；二元Brier/log-loss分母是全部非DRAW可评分概率（含p=0.5），0.5概率基准同分母；另给包含DRAW按payout=0.5的兑付Brier，明确它不是二元UP概率评分。log-loss只在统计层以1e-12夹概率，原始Rust概率不改。对照即时方向spot相对固定strike（相等abstain），准确率对比使用共同有效分母，并同时列各自覆盖。不按事后最好偏移选策略。
6. IS/OOS与每个偏移分别汇总，固定10个等宽概率bin（bin=min(9,floor(10*p))）；月度/日度稳定性、sigma floor占比、Chainlink/Binance基差与时点代理限制明确披露。95%区间采用按UTC日整块重采样1000次：每分区独立重置numpy.Generator(PCG64(42))，按排序UTC日n生成integers(0,n,size=(1000,n),dtype=int64)，六时点共享日索引，按各日分子/分母加权合并、不是平均每日比率；分位数[0.025,0.975]、method=linear。主accuracy/Brier/log-loss及相对0.5基准Brier配对差均给区间，零分母无效draw单列/N/A；同轮六时点不作独立观测。缺日保留原因，不插值或缩分母。无参数拟合，IS/OOS为时间分段诊断；如加训练基准只许用IS标签拟合，不窥OOS。
7. 没有份额bid/ask/深度/费用可成交链：真实候选/成交数、成交胜率、净PnL、年化、Sharpe、MDD、Calmar、换手、IR全部N/A+原因；不得通过假盘口、固定0.5买价或零成本生成真实收益。研究结果差也如实完成，不设“必须战胜基准”工程门槛。
8. 完成需真实全94日研究和CSV/正文同源；按源/日保留coverage、content/provenance及真实native退出，部分/预算耗尽不得整体PASS。独立Tester对概率向量、标签时间、统计和载体对拍（rel1e-9、近零abs1e-12；载体/raw汇总rel1e-12，正文按固定展示格式从同源raw渲染后逐格相等（不把展示舍入当raw容差），分类/计数零漂移）；原始A&S近似与精确CDF误差分列。非实现者在Verify前提供独立双路径固定数值，不由Developer代填。只跑必要回归，不重做已通过数据摄入或566工程套件。

### 16.1 reader性能增量（2026-11-12，用户方案2）

只允许既有reader内部去冗余与定向测试，不改facade签名、history_types、history_input、schema、索引、来源或策略。对同一请求，三流逐行顺序/精确Decimal/可得时间、content_manifest/content_sha256、coverage/gap/status及provenance必须与修前等价；保持expected_manifest、未完整消费拒绝、页/行/日账业务内容变更检测、UNKNOWN_SCHEMA_VERSION及原生失败传播。不得通过跳过校验、仅缓存_id/行数/日账摘要或无界缓存实现提速；raw/provenance独立语义不变。实现可复用页级摘要与本页规范化结果、减少不产生目标流的投影及verify中完整业务重算，缓存需请求隔离且不整窗持有行/对象。修前已启动的三个UTC日golden只读保留；同请求修后逐字段/三流摘要对拍，定向变更/跨页/反复读取回归真实执行。完整研究仍按原pilot≤300s/full≤3600s及卡片预算，未实测通过不宣称提速或全量完成，不增10小时预算。

## 1. 需求摘要（M1 历史需求）

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
| V1.2 | 2026-11-10 | 保留 M1 历史并注明已签收来源；新增 §9–§15 M2 需求/数据与因果契约/公共指标复用/降级/验收；Design 后续独立修订 |

## 9. M2 范围、基线与复用

### 9.1 本轮需求与阶段边界

M2 = 同核心 Rust 离线回放 + `predict-btc5m-btc-arb` 首份真实数据研究 + 可复现载体与独立验收；不是执行安全加固或交易激活。仅 T1 RFC/SPEC 和交接为当前写入授权。后续实现路径是本节候选范围，须经 T2 精确 allowlist 冻结，不赋予当前卡实现权限。

| 路径（相对项目根） | M2 后续候选动作/限制 |
|---|---|
| `skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/src/bot/arbitrage.rs` | 抽出同决策/时钟输入及状态确认；保留实时默认行为与其他策略 |
| 同子模块 `src/bot/arbitrage/replay.rs`、`src/bin/btc_arb_replay.rs` 及对应模块内测试 | 新增本地回放与离线测试；不改依赖或 Cargo.lock；模块可见性/编译入口由 Design 确定 |
| `skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/{spec.md,config.json,research.py,README.md,tests/test_research.py}` 及 `reports/` | 本实例 spec 按现成模板填写，不作为第二正式工程 SPEC；config 仅显式离线数值参数，不含 live/network/钱包/资金激活开关 |
| Lab `scripts/equity_metrics.py`、`scripts/grid_research.py`、`tests/test_equity_metrics.py` 及必要定向网格回归 | 公共指标最小提取和兼容 wrapper，不重写网格 |
| Lab `SKILL.md`、`strategies/INDEX.md` | 后续仅增加 Rust 研究入口适用性说明和真实实例状态；不改变公共模板/网格规范 |
| `data/reports/2026-11-10-predict-btc5m-m2/{report.md,evidence/}` | 索引与真实证据，见 §13；不得宣称已产生 |
| `data/tasks/active/2026-11-10-predict-btc5m-m2/` | 各阶段交接；T1 仅 `rfc-spec-handoff.md` |

`service/spot.rs` 优先只读复用；`service/predict_fun.rs` 不默认纳入，只有历史只读数据缺口有证据且本轮必要，T2 才可提出窄范围。不改 runtime live、UNKNOWN/净份额、持久化恢复、QuantDinger、unified_data、risk/reports 平台、其他策略、公共模板、运行配置、profile/Hermes。保持子模块本地 main，不 fetch/checkout/pull/升级/提交/push 或自行同步 gitlink。

### 9.2 已核对复用表（规范 ≠ 代码 ≠ 不适用）

下表行号对应 M2 T1 局部复核时的本地基线，不代表未来行号固定。QD 数据探针直接引用 [既有证据](../../../data/reports/2026-11-10-predict-btc5m-gaps/evidence/quantdinger-readonly-probe.json)，本卡无新 API 请求或 Cargo 运行。

| 资产/真实符号 | 当前事实 | M2 复用性质与约束 |
|---|---|---|
| Toolkits `arbitrage.rs:65–157,172–206`：`RoundTaker::tick`、`round_entry` | tick 依赖时钟/SpotFeed；预热、entered 在适配层；round_entry 私有 | 代码复用：同 Rust 决策，不是复制 Python；只拆必要输入，不改 runtime 执行 |
| `service/spot.rs:148–175,192–204`：`EwmaVol::{update,samples,vol}`、`digital_up` | 正 dt 才增加 return sample；首价格不计 sample；sigma 单位为每平方根秒；半衰期按秒 | 代码直接复用，20 个 return sample 即至少 21 个严格递增有效价格，不是 20 根就暖好 |
| `config.rs:281–302`：`BtcArbConfig::default` | BTCUSDT、min_edge=0.03、order_usd=5.0、min_secs_left=30、vol_floor=0.00005；arbitrage 常量半衰期300秒、MIN_VOL_SAMPLES=20 | 原版离线参数冻结；不得将旧建议 1 USDT 单笔替换成原版基准，也不激活 5 USDT 交易 |
| `service/venue.rs:49–83`：`TradableMarket`、`taker_fee`、`secs_left` | Yes book/No 镜像；费公式 bps/10000 × min(p,1−p)；secs_left 整秒截断 | 沿用原版决策费用/时间语义，不把该费用模型称真实净份额会计 |
| `runtime.rs:127–139`：`Summary::equity` | realized − fees + unrealized，是损益而非账户权益 | 只读语义复用；账户权益需要另加 initial_capital，禁止重复加成本或忽略资本 |
| Lab `quantdinger.py:427,451,820`：`resolve_agent_token`、`agent_call`、`fetch_klines` | 既有单键凭据机制/白名单 HTTP/分页；fetch_klines 会排序且同时间戳后页覆盖 | 代码复用；实例 request 包装在原页层记录预算、重复/冲突和来源；不向2516行脚本追加 Rust 功能 |
| Lab `quantdinger.py:650`：`Budget` | 已有单调墙钟/保留收尾时间，无行情请求计数器 | 可复用墙钟；实例补本次数据请求计数，不谎称 Budget 已覆盖数据请求 |
| Lab `grid_research.py:323–384`：`margin_metrics` | INITIAL_MARGIN 固定；M0 参与收益/MDD，不参与首个 Sharpe 收益；K 实际为365×(86400//frequency)，ddof=0 | 最小抽公共 helper；保留旧 wrapper/输出/NA/reason/判定；具体参数/映射见 §12 |
| Lab `templates/strategy-spec.md`、`templates/research-report.md`、SKILL 退出码/证据/验收 | 已有需求与报告核心字段、独立验收和预算纪律 | 规范复用，不重写模板；本 SPEC 对二元研究适用性作明确限定 |
| 网格 `build_cells`、`cell_qualification`、`write_cells_csv`、`write_comparison_csv` 及表 A/B | 几何、四窗、G/E≤2和35%为网格特定语义 | 不适用本实例，不复用其判定；本次同源 CSV 用 §13 语义，不硬塞网格列 |

### 9.3 可验证功能

| 编号 | 行为及输出 | 失败/边界 |
|---|---|---|
| M2-F-001 | Rust 实时与离线共同使用估值、入场、EWMA及成功入场状态确认 | Python/Bun 生产路径存在第二实现、原版默认改变即失败；隔离验收参考计算不接入生产研究路径 |
| M2-F-002 | 纯本地回放使用显式事件时钟和数据，输出决策/拒绝原因/状态变化 | 无 AppConfig::load、Ctx::connect、SpotFeed 网络实例、签名器、venue/RPC 或 live 开关 |
| M2-F-003 | 核查历史盘口/标签可得性，输出来源、时间、覆盖和缺口 | 不把未查/不可得伪装已支持；不无限联网或启动采集 |
| M2-F-004 | Lab 真实只读 OHLC/本地历史研究、显式窗口/切分/频率、因果 Rust 调用 | 无真实样本则整个 M2 未完成；fixture 另列 |
| M2-F-005 | 公共资本/频率指标计算、原网格 wrapper 零漂移 | 复制公式、字段/数值/NA/reason/判定漂移即失败 |
| M2-F-006 | 同源 CSV/正文、N/A原因、复现与独立数值验收 | 缺载体、丢行、假收益或越级证据声明即失败 |

## 10. M2 回放输入、状态与因果契约

本节冻结语义，T2 决定 Rust 类型/函数名、JSON/JSONL 序列化、CLI 参数拼写及精确文件布局；不在 T1 虚构现有公共 API。所有时间带 UTC/偏移；事件至少表达唯一 event_id、事件时刻、可用时刻、同刻顺序号、来源和证据等级。源时间未知必须显式标未知，不伪造毫秒精度或“真实接收时间”。

### 10.1 输入对象

| 对象 | 必要信息/约束 | 缺失动作 |
|---|---|---|
| 回放控制 | 显式本地输入路径、原版参数、起止/研究时钟、证据模式（fixture/真实历史/真实代理） | 不读取运行 .env/交易 AppConfig，不回退系统当前时间或默认网络 |
| 市场身份 | market_id、BTCUSDT、starts_at/ends_at 且差恰300秒、Yes=Up/No=Down语义与非空不同token、来源/available_at | 无法验证则拒绝该市场；token跨市场冒用、错误时长/标的为输入错误，不猜映射 |
| 市场状态/开盘价 | open、contested/paused、正有限 start_price、规则/来源、当时可用时间 | 未知/未来开盘价不入场；关闭/争议/暂停不入场 |
| spot | 正有限价格、模型source（Binance等或明确代理）、event_at/available_at | 不用未来数据更新 vol；未知时序的真实数据不得升级为实盘等价 |
| 盘口 | market_id/Yes token身份、[0,1]价格、非负深度、排序、两侧来源及时间；沿原版 No 镜像 | 不插值/补造盘口；缺盘口只估值不产生可执行入场；NaN/Inf/越界为输入错误 |
| 本地结果事件 | 与先前决策关联、明确 blocked/零成交/正成交及数量、结果可用时间 | 正有限成交才确认 entered；未知结果停该轮后续新增入场并报告，不用请求 shares 回填；不是 runtime UNKNOWN 修复 |
| 结算标签（仅事后评估） | market/token、官方指定来源、payout_yes、权威结束报告、发布时间、pending/争议/平价状态 | 缺失保留 pending/N/A，不用 spot 或二元报价填；不把最终结算提前泄漏给决策 |

同一 market_id 的 token/起止/标的不可中途被其他市场覆盖；合法状态/开盘价更新必须按当时可用时间生效，不能用今天的完整市场元数据回填所有历史 tick。官方标签的 payout_yes 在平价为0.5，其他情形遵循可核验规则；争议/pending不按输/赢强制落账。

### 10.2 时序、预热与入场状态

1. 按 `(available_at, 同刻顺序号)` 顺序执行，已知event_at须≤available_at；输入乱序拒绝而非悄悄排序修复。EWMA显式at_secs使用该输入的回放可用时钟，保留原版按观察时钟更新的语义；同一symbol有效样本时间严格增加，同刻重复spot不增加sample。决策只消费可用时刻≤该tick的输入；未来标签永远隔离。真实接收时间未知时可用时钟只能是明确标注的代理假设，不得声明真实延迟/线上等价；原始源时刻未知保留UNKNOWN。
2. event_id 重放且载荷相同：忽略并计数；同 ID 不同载荷、同 symbol/时刻冲突价格、同市场/时刻冲突 book：输入失败。允许真实数据同刻不同类型事件，必须有稳定顺序。重复结果不得二次确认/计数。
3. EWMA 沿原版 `half_life_secs=300`；warmup 需要20个有效 return sample，第一价格仅设 last。预热不足只输出原因，不入场；warmup可来自研究前数据但不能来自评估未来。
4. 原版参数、Yes ask/No镜像bid、费用扣边际和 `edge >= 0.03`、`min_secs_left=30` 保持；`secs_left` 沿原版整秒。仅在已开始、未结束、open且非争议且start_price当时已知时评估。回放 BTC/300 秒守卫不改变其他 live 市场范围。
5. 每轮正成交确认后不再产生新入场；Blocked/零成交后可以重试，故“一次入场”不等于“最多计算一次候选”。离线 driver 不能把候选自动视为成交；没有结果证据时输出 candidate/unconfirmed 并停止该轮后续尝试，不伪造交易数/PnL。fixture可显式给本地成交事件，仅标测试证据。
6. 同一输入、参数、二进制版本的决策和状态结果确定性相等；输出不含真实执行时刻造成的不稳定字段。真实运行元数据另列。实时 source 防护、Broker停机/限额及执行适配保持原行为，只对同等输入的共享决策作 parity 声明。

### 10.3 安全与错误

回放进程只能读显式本地文件/标准输入和写显式本地产物；路径/参数错误先失败，不创建网络客户端或读取交易配置。不得依赖“dry-run默认安全”或 Cargo --offline 证明业务离线。构造凭据缺失环境及网络调用禁止的测试，验证回放仍可执行；注入 live/网络参数必须拒绝。具体测试机制由 Design落实，不安装工具或改宿主网络。

回放输入违反身份/类型/时序契约返回契约或用法失败；合法数据但无 warmup/book/标签为可解释缺证据输出，不当崩溃或默认为0。Rust CLI 的具体退出码映射由 Design 冻结，Lab 外层必须遵循 §13.3 现成退出码，不能吞失败当 exit0。

## 11. M2 真实研究与数据降级

### 11.1 可得性核查与取数

实现期先对既有本地资料、已确认官方公开只读能力作有界核查，分别记录“历史份额盘口/深度、当时市场身份/开盘价/费率/状态、官方结算标签”的 source、查询范围/时间、结果/缺口。已知文档存在不等于历史数据可取；接口不存在/无权限/无法确认也要记录，不能创造未见端点。T1直接引用既有QD探针，不重跑。

只允许无签名公开只读来源与已授权QD Agent行情认证，不进入交易凭据、钱包或账户路径；出现需新凭据/签名/付费/改平台的要求停止该分支，可按代理路径继续。不能为补历史缺口开启实时订阅、短期/长期后台采集或 bot。全研究数据请求≤50，业务墙钟≤1800s，调用前检查剩余预算，超限停止、exit5；此限额涵盖可得性请求、重试、分页，不是每个接口各50。QD backtest/evolution/source/job创建次数必须为0；免费不等于允许提交。

QD 只用既有 `fetch_klines(data_api=agent, ...)` 与 `resolve_agent_token`/`agent_call` 体系，按现成凭据边界处理，不输出令牌/headers。401/403即停exit4，不自动换通道/凭据。使用显式start/end和max_pages≤2、单页上限500；若预算/页上限覆盖不了声明窗口，报告缺口，不静默裁成返回窗口再称覆盖完整。精确UTC半开区间在实例侧裁剪；fetch_klines的日期end包含全天不是本实例半开end，必须转换并测试边界。

### 11.2 OHLC 质量与来源

实例参数必须包括观察as_of、样本 `[start_utc,end_utc)`、split_utc、frequency_seconds、warmup长度、数据通道/market/symbol/timeframe、请求/墙钟上限；时段满足start<split<end，频率和timeframe一致，输出记录实际值。另记实际fetch_start与warmup区间，区分bar_open、bar_close可用边界与预测t；预热可在start前，但不混入评估计数。样本选择在看评估结果前冻结；不为求好结果换窗。M2 BTC二元轮次固定300秒与OHLC采样频率是两件事。

- 只使用 `bar_open + frequency_seconds <= as_of` 的闭合bar，未来/未闭合剔除且计数；所有价格正有限，OHLC关系成立，volume有限非负（0不删）。校验UTC对齐、唯一时间戳、间隔、声明范围与实际覆盖、预热与评估各计数。
- `fetch_klines` 内部会合并覆盖同时间戳；实例通过已有request注入在原页层核对原始重复/冲突、保存脱敏OHLC证据，之后才交已有标准化/分页处理。相同bar可去重并计数，冲突bar不能静默后页胜出；不另造HTTP/分页客户端。
- 缺bar不插值、不补0；不跨缺口算连续收益或标签，报告缺失区间及受影响数。允许保留已验证的连续子段做描述研究，但声明窗口覆盖失败不得改成完整。
- 返回无venue/product证明时字段为UNKNOWN并列实际QD来源及配置仅为偏好，不写“Binance现货”或“gate已证明”。现成training_ohlc gate/swap/1D、改全局venue、unified_data新provider均不在范围内。

### 11.3 最低可交付的因果代理研究

缺真实轮内盘口/官方标签时，必须真实执行以下代理分析，不能只写“不足”就停止所有研究：

1. 用闭合OHLC close序列按可用时间送入同一Rust EWMA。每个边界t，当前close已闭合，代理strike取该close，预测期限300秒；调用同Rust估值获得p_up。未来边界t+300秒的close仅事后形成方向代理标签：大于strike为1、小于为0、相等为0.5（平价软标签），与官方标签明确区分。只在两边界真实存在且间隔300秒时构成一条；不得把5m OHLC展开成轮内tick。此最低路径需frequency_seconds=300；实例选其他频率须仍取得300秒配对，否则该指标N/A，不重采样合成。
2. 该代理只检验粗频EWMA和模型在闭合边界上的校准，不包含原策略轮内价差/滞后入场；ATM预测接近0.5是模型性质而非实现失败，不能据此宣称有交易优势。无盘口时决策/成交/PnL栏N/A，不人为给份额买价0.5。
3. 按预测时刻t切分样本内（标签可用时刻≤split）与样本外（t≥split且标签在end前可得）；跨split预测不归入任一区，防止标签泄漏。warmup不计评估样本，样本外EWMA可延续此前已知价格，不拟合或重置参数以改善结果。
4. 每区至少一条有效预测/标签才有该区描述结果；数量和持续期全披露，无统计显著性或盈利门槛。Brier = mean((p−y)^2)，基准为恒定概率0.5的同标签Brier；平价单列计数。报告p_up范围/均值、sigma范围、样本数与逐样本结果；不强行报硬分类准确率。不交易基准仅说明未承担策略风险，不把它当策略收益已知。
5. 压力假设至少披露“来源/官方标签替换风险、粗采样遗漏轮内波动、成本/延迟未测”；真实事件具备时可作显式数据延迟/价差/费用情景，均标假设且不优化原参数。不具备时相关净收益/延迟敏感性数值N/A带原因，禁止用合成市场数据冒充真实压力结果。

允许真实历史分支在相同因果/切分规则下增加真实标签校准和历史候选统计，但不要求另造撮合/账本引擎；不能因真实标签存在就绕过M3会计限制。降级研究总体固定 `insufficient-evidence`，原因至少列轮内盘口/官方标签/venue证明/费用净份额/执行差异中实际缺项。

## 12. M2 公共权益指标与兼容性

仅把 `grid_research.margin_metrics` 的通用计算抽成一次实现，helper显式接收initial_capital、frequency_seconds与时间权益行；旧wrapper保留原INITIAL_MARGIN、缺equity时损益回填及字段映射。M2账户权益若来自Summary，必须是 `initial_capital + Summary.equity()`，后者已含realized−fees+unrealized；不是再减open_cost或重复扣费。不能借此补做真实净份额会计。

冻结现有行为：peak起点为initial_capital；区间收益 =100×(last_equity/initial_capital−1)；net_pnl=last_equity−initial_capital；逐行峰值MDD=(peak−equity)/peak×100。Sharpe只用相邻所给权益的r=right/left−1，不加capital→首行的收益，至少2个收益、连续时间且权益正、population标准差>0才计算；rf=0、ddof=0。无样本、非正权益、缺/重/非原生时间间隔、零波动沿原wrapper保留原status/reason/NA/raw诊断与计数。

注意源码K是 `365 * (86400 // frequency_seconds)`，不是任意频率下的精确除法；不能在提取时顺手修正而造成旧网格漂移。M2频率要求正整数且整除86400，故该域内K等于365×86400/frequency_seconds；旧wrapper既有接受域和结果保持，边界验证的层次由Design明确。initial_capital为正有限数，M2研究显式记录选择值，不自动使用网格INITIAL_MARGIN；缺真实净值时只测试helper，研究收益指标仍N/A，不用200 USDT生成虚假曲线。

报告保留年化收益、Sharpe、MDD、Calmar、换手率、IR行。无可证实账户权益/成本/有效基准序列时N/A+原因；本轮不为凑齐指标新造权益或第二套公式。将来证据足够而实际计算这些附加指标前须由Design冻结其单位、时段和基准；M2降级不依赖它们取数值。压缩权益MDD不等于轮内真实峰值回撤，既有limitation继续披露。

零漂移回归覆盖既有真实网格测试输入及空集、正/非正权益、缺间隔、零波动、不同频率、缺equity回填：提取前后全部key/value/NA/reason/计数/判定一致，不能仅比较一个收益数字。原wrapper入口与默认值不变，不顺带重构网格报表、强平或候选筛选。

## 13. M2 输出、错误与持久化契约

### 13.1 报告与CSV最小语义

唯一正文在实例 `reports/report.md`，按现成research-report模板保留结论摘要、数据/口径、假设/未建模项、限制/不适用、结果明细、复现命令、证据分级。归档索引 `data/reports/2026-11-10-predict-btc5m-m2/report.md` 记录正文相对路径、hash/生成时刻及本主题evidence链接，不手写第二套结果；实例reports中的最新CSV为归档CSV的精确副本或明确链接，不各自再算。若正文后续变更导致hash失配，该归档不能继续被称已验证；本次验证结束后保留正文及归档证据，后续新研究另开主题，不覆写本次研究证据。

| 载体/对象（文件名由T2冻结） | 最小字段/语义 |
|---|---|
| 数据可得性/覆盖记录 | 来源/接口或本地路径、核查时间、请求数/预算、market/symbol/timeframe、实际venue/product或UNKNOWN、范围/as_of/split、原始/闭合/剔除/重复/冲突/缺bar/预热/IS/OOS计数、缺口与判定 |
| Rust回放逐事件CSV/等价可读输出 | event_id/时刻/available_at、证据等级、market/token、输入引用、sigma/p_up、candidate及price/edge或N/A原因、结果确认/entered变化；不将未确认candidate列为成交 |
| 真实代理逐样本CSV | 时间t/标签可用时刻、split、source/venue_status、spot/代理strike、sigma/p_up、proxy_label、Brier及0.5概率基准Brier、标签类型、N/A原因 |
| 比较CSV/正文同源行 | 分栏evidence_type=fixture/real-proxy/real-market，IS/OOS、样本数、指标名/值/单位/口径/原因、research_verdict；计划而未执行栏保留N/A，不丢行 |
| 重现证据 | 输入数据hash、源码/二进制基线与本地diff、原版参数、实际命令/cwd/解释器/起止时间时区/退出码、预算实数、离线测试与独立验收引用；无秘密 |

字段具体序列化/列序由Design一次冻结，CSV与正文由同一已计算行集生成并按相同精度渲染。空缺用N/A且带reason，不写空白/0；0仅是实测零。概率范围[0,1]、sigma非负有限、行键唯一；逐样本Brier汇总可回算。fixture和真实研究不得合并求收益/样本总数或共用“真实策略通过”结论。

### 13.2 证据分级与完成判据

- 可用：仅限实际证据可证明的局部结论，如回放软件行为或真实代理样本统计。
- 证据不足：影响策略结论的任意UNKNOWN；盘口/官方标签不足时总体为 `insufficient-evidence`，真实净PnL/执行等价/实盘就绪固定未验证。
- 不适用：如QD job/run/sourceId/UI读回、网格四折/表A/B/G/E阈值，说明原因，不伪造平台记录。

本SPEC为Lab现有“证据不足fail closed”的M2限定适配：exit3时允许输出已完成的真实代理分析和缺口报告，但不产出“策略研究通过/盈利/实盘就绪”的完成结论，不继续下单/job请求。工程验收可按M2-A矩阵通过；没有真实分析、只有软件fixture或诊断则不能关闭整个M2。该适配不改Lab其他实例的失败行为或公共模板。

### 13.3 Lab退出码和停止规则

| 退出码 | M2语义及动作 |
|---|---|
| 0 | 正常且证据符合当前局部业务结论；不由返回码推出真实净收益或实盘许可；优化固定skipped |
| 2 | 平台/数据契约或Rust调用失败，停止并保留真实错误，不改断言/参数求通过 |
| 3 | 证据不足，含合规真实代理降级；保存分析/缺口与N/A，不伪装0 |
| 4 | 认证缺失/401/403；停止相关调用，不换凭据/通道绕过 |
| 5 | 请求/墙钟预算或超时；停止，不后台重试，不把部分结果称完整 |
| 64 | 参数/本地路径错误；前检拒绝，不启动业务请求 |

任何审批拒绝/超时停止该动作，不换执行器。原始失败、部分产物、ignored/未运行项均保留；无凭据内容、原始认证headers或账号PII写入报告/看板。研究证据只存JSON/CSV/Markdown，无生产数据库/索引/TTL/schema，不迁移QD数据库。过程目录整体归档由主控Closeout处理，T1不搬迁。

## 14. M2 验收与独立验证

### 14.1 后续M2工程验收矩阵

| 编号 | 需求映射 | 可证伪判据/所需证据 |
|---|---|---|
| M2-A-001 | F-001 / §9.2、§10.2 | Rust单一实现及调用关系源码；同输入共享核心与实时适配决策golden对拍；原版默认参数/边界/其他策略回归无漂移，不在Python复制决策 |
| M2-A-002 | F-002 / §10.1、§10.3 | 新回放可实际前台执行，有命令/exit/非空输出；无交易凭据环境、禁止网络调用的测试通过，AppConfig::load/Ctx::connect/签名/venue/RPC路径不可达；live参数拒绝 |
| M2-A-003 | F-002 / §10.1–10.2 | 预热19/20 return边界、BTC/300秒/market-token、未开始/近到期/结束、未来start_price/标签、顺序/重复/冲突、blocked/零/正成交/未知结果测试覆盖；正成交后每轮新增入场数≤1，输入前缀结果不受未来事件改变 |
| M2-A-004 | F-003 / §11.1 | 每类历史数据的可得性有真实来源/范围/观察证据；真实与fixture分列，缺口不被合成盘口/close标签填补；禁止后台采集/账户凭据 |
| M2-A-005 | F-004 / §11.2 | 实际真实样本分析+闭合/范围/去重/冲突/预热/覆盖记录；QD现成函数调用、未知venue披露、半开end与重复页测试；无伪造/插值/未闭合未来bar |
| M2-A-006 | F-004 / §11.3 | 显式start/split/end/frequency及样本内外逐样本载体，最小代理两区各有有效样本；Brier/0.5概率基准可复算、标签因果；缺盘口/官方标签为insufficient-evidence/exit3，收益N/A，不以近0.5概率声称alpha |
| M2-A-007 | F-005 / §12 | 公共helper单一实现/显式资本与频率，Summary损益转换正确；提取前后网格数值、字段、NA/reason、计数和判定drift=0/N；原wrapper入口不变 |
| M2-A-008 | F-006 / §13.1–13.2 | 现成模板全部核心字段、CSV与正文同源、所有计划栏/指标占位有原因、唯一正文及归档索引hash可核；真实净PnL/实盘未验证，fixture不混入真实样本 |
| M2-A-009 | F-003..006 / §11.1、§13.3 | 真实请求计数≤50、业务墙钟≤1800s、QD job/交易/签名/后台/生产写=0；范围diff与命令符合T2 allowlist，依赖/锁/其他子模块不变，未commit/push |
| M2-A-010 | F-001..006 / 本节 | Tester独立执行回放与数值验收、CSV/正文对拍；Reviewer核三层文档/源码/报告一致性及范围，open blocker/major/minor=0后主控Closeout；未运行不计通过 |

M2工程完成=上表全部满足。允许M2-A-006的合规研究降级，不允许M2-A-002仅交代码没跑、M2-A-005没有真实研究，或M2-A-010拿开发者自测当独立验收。无真实数据时保留证据并向主控报告M2未完成，不伪装研究PASS。T1当前只验证两文档互引、增量范围/可计算语义/降级/复用映射与自身文件边界，不宣称此工程矩阵已经执行。

### 14.2 测试与数值验收责任

Rust新增测试与原版受影响安全集合由后续Developer/Tester实际执行；M1历史164/0/3仅引用，不能当M2新测试。测试fixture可控且明确标记；对同核心parity使用原输入/原参数固定预期，不调用真实venue。真实研究验证须用归档原始样本，独立路径重算EWMA/概率样例及Brier/公共权益指标，不能以再次调用实现helper充当独立验收。独立参考计算只在隔离验收中使用，不构成Python生产决策复制；概率对拍的基准是原版A&S近似公式而非擅换精确CDF，两者的模型近似误差不可混同实现漂移。

研究独立验收引用Lab SKILL“研究验收标准与角色分工”：数值重算rel≤1e-9，载体/正文数值rel≤1e-12，判定drift=0/N；零值附近abs容差由Design显式冻结，不能隐含放宽。表A/B列序/脚注检查因本实例不适用改为本实例冻结列序/口径，保留同源要求。基准由非实现者在Verify前双路径生成并落具体数值/容差，Design落实边界向量；T1无真实研究结果，不虚构对拍数字。

Developer/Tester/Reviewer必须不同角色。Tester只读实现、不改断言或覆盖已发布结果；Reviewer检查RFC/SPEC/Design三文件、当前M2版本对齐、报告与diff范围；存在分歧保留预期/实际，不默认实现正确。Independent Verify/Review均不可由T1自评替代。

## 15. M2 Design交接与未完成项

业务语义已定，无需再次请求fork URL、底座选型、账户或资金授权。T2必须在同一DESIGN-07-001中保留M1历史并新增M2实现设计，明确：最小Rust模块/可见性与本地CLI、事件/状态序列化、replay/proxy估值共核边界、输入校验顺序、实例参数及首轮默认窗口/切分、QD原页验证注入、公共helper/wrapper映射和兼容测试、载体列序/文件名、真实运行/离线重现命令、独立数值向量和无网测试方法、精确allowlist及失败交接。不得把T1候选范围当已经批准的Design。

尚待发现的事实：历史份额/官方标签覆盖、后续真实样本时段和来源、构建后新回放实际输出、指标回归和独立验收结果。它们均未在T1运行，不作为已完成能力；如超出M2需M3修复则记录/降级，不自动扩展。主控核验本RFC/SPEC后派T2，核验三层完整和Design Gate后才派Implement；本卡不创建任何下游卡。
