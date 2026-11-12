# DESIGN-07-001: Predict.fun BTC 5m——M1 基线与 M2 同核心回放研究

## 元数据

| 项 | 值 |
|---|---|
| 状态 | M1/M2 限定离线工程已签收；M3 官方历史预测研究 V1.3 已获准 Light，待实现/独立验收；非交易授权 |
| 作者 | YQuant Principal（M1/M2）；YQuant 主控（M3 用户 Light 授权增量） |
| 创建日期 / 最后更新 | 2026-11-09 / 2026-11-12 |
| 版本 | V1.3 |
| 来源 RFC | [RFC-07-001](../../rfc/07_trading/RFC-07-001-predictfun-btc5m.md) V1.3，本轮 M3 §14；历史 M2 §13 |
| 来源 SPEC | [SPEC-07-001](../../spec/07_trading/SPEC-07-001-predictfun-btc5m.md) V1.3，本轮 M3 §16；历史 M2 §9–§15 |
| 上游交接 | [M2 rfc-spec-handoff.md](../../../data/tasks/active/2026-11-10-predict-btc5m-m2/rfc-spec-handoff.md)；[M1 历史交接](../../../data/tasks/done/2026-11-09-predict-btc5m-m1/rfc-spec-handoff.md) |
| 目标模块 / 工作区 | 07_trading；`/home/pascal/workspace/yquant-investment` |
| 来源任务 / 阶段 | M1 t_89c7f315、M2 t_dae1a22e/t_bf5ea047 仅历史；M3 用户 Light 授权与本轮 data/tasks/active/2026-11-12-btc5m-native-history-research/intake.md |

阶段适用性（以下为 V1.2 历史说明，本轮 M3 另按 V1.3 §19）：§1–§7 是 M1 历史设计（当时来源 RFC/SPEC V1.1），保留当时未实施、禁止回放/建 Lab/修改源码的语境，不作为 M2 执行指令。M1 终态为 [最终签收报告 §13](../../../data/reports/2026-11-09-predict-btc5m-m1/report.md)：PASS/ACCEPTED，仅原版构建和安全离线测试，164 passed/0 failed/3 ignored 是历史结果。历史过程现已在 `data/tasks/done/2026-11-09-predict-btc5m-m1/`，下文相关路径仅校正归档位置，不追认执行过其中的撤销示例。当前 M2 依 §8–§18，§18 冻结本次恢复 delta，业务语义仍服从 RFC/SPEC V1.2；M3/M4、夜报、机器人/模拟或真实订单、签名、生产库和长期调度均未授权。

## 19. M3 官方历史预测研究（V1.3 当前最小设计）

来源RFC V1.3 §14、SPEC V1.3 §16及Pascal 2026-11-12 Light决定。M1/M2、Recovery及其Full Flow是历史，不重做；本节只新增官方历史预测研究入口，不授权原M3执行加固或实盘。本节是V1.3变更记录。Implement→独立Tester→主控收尾，无额外Principal/Review/Activation。此原生Mongo只读研究不调用QuantDinger，平台HTTP请求/job/付费调用均0，原平台≤50请求/四折等额度不转借也不增加；本次本地pilot≤300s、正式全窗≤3600s，卡片总75m内为构建/测试/交接留预算，超出必须保留partial不追认PASS。

### 19.1 精确实现边界

令LAB=`skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/`，BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/`。只允许以下源码/测试增量：

- LAB/history_research.py（新：只读facade/原history_input、逐秒因果事件编排、调用Rust、统计/CSV/报告）；LAB/history_metrics.py（确需分离统计时才新建，禁止模型）；LAB/tests/test_history_research.py、LAB/tests/test_history_metrics.py（对应新测试，后者仅存在helper时）；LAB/README.md、LAB/spec.md（追加当前研究契约/实际状态，不改旧已发表结果）。
- BOT/src/bot/arbitrage.rs 只加`pub mod history;`，DecisionCore/生产实现和其他字节不得改；BOT/src/bot/arbitrage/history.rs（新：无IO估值薄适配，调用父DecisionCore的observe_spot/valuation）；BOT/src/bot/arbitrage/history/tests.rs（新colocated测试）；BOT/src/bin/btc_arb_history.rs（新：本地文件/stdio流CLI，复用ReplayConfig冻结参数）。Cargo自动发现bin，禁止改Cargo.toml/lock/依赖/生产config。
- 过程data/tasks/active/2026-11-12-btc5m-native-history-research/；唯一新报告data/reports/2026-11-12-btc5m-native-history-research/report.md，CSV/manifest/日志位于其evidence/。旧Lab reports/及所有旧证据只读，不建立第二研究引擎/通用SDK/新DB。

明确只读：LAB/history_input.py、LAB/research.py和其旧测试，除§19.4例外外全部UD/data-pipeline、BOT/src/service/spot.rs、旧replay整树、真实bot/runtime/venue/config，其他子模块、每日job、profile/Hermes、其他项目。只允许本地构建忽略产物；不commit/push/暂存或改gitlink，不切main、不fetch/升级、不启停服务。

### 19.2 薄入口和连续时钟

新CLI只接显式本地config/input/output/summary路径或stdio和时间窗，拒绝未知/live/RPC/wallet参数；不调用AppConfig::load/Ctx::connect/SpotFeed/venue。新线协议`btc-arb-history/1`与旧协议隔离：仅spot输入和round-value请求；请求记录round_id、starts/ends、strike，使用最新已可得spot和ends-now调用原valuation。校验有限正价格、UTC有序时钟、BTCUSDT、300秒round、固定round身份/strike不变、t处于轮内且secs_left≥30、spot不来自未来；无book/fee/fill字段，拒绝未知字段。事件相同时间按明确seq先spot后value；缺价/预热/缺身份保留原因、不造输出概率。

8M秒线以有界流/磁盘载体处理，只对六个估值点输出行，不为每个spot生成巨大业务结果表。整个主研究用同一Rust状态连续读日分片，日界不重置波动率；若必须分段，采用精确同前缀状态重建并证明边界一致，不以1800秒近似暖启动混入主结果。Python只编排、校验、统计，不实现EwmaVol/digital_up。先真实窄窗测成本，再启动一次全窗；数据读取可有界分日，已验证分片不重做ETLV/raw内容验收，仍须facade消费后verify。

### 19.3 固定验收与数值

实现先以固定strike≠spot、剩余270/120/30的反例证明旧入口不支持，再覆盖新薄入口：20return边界、非法时间/未来spot、跨日连续性、同id改strike、end/30秒边界、字段注入、无网络/凭据路径。运行必要原core/旧replay定向回归，不重跑无关全仓；新的研究CLI真实运行非空官方历史，不用mock替代。输入/输出独占创建，旧目标冲突停止；原生非零及partial保留，不包装成成功。

研究固定94日/27072轮×6时点，理论162432评分位置，缺失/暖启动/abstain/DRAW分类单列；coverage分母不缩水。输出至少samples.csv（逐round/时点/分区/概率/标签/原因）、comparison.csv（分区×偏移的样本/评分/基准/区间）、calibration.csv、daily.csv、coverage.json、参数/源manifest/源码与binary SHA、真实命令/原生退出和唯一正文。列清单在实例代码常量固定，同一结果渲染CSV和正文；无权益指标全部N/A。实际文件与字段由实例spec和冻结代码常量逐项列明，不改成网格表A/B。

主控在Verify前提供固定模型向量双路径数值参考，Tester另算实际评分与标签对齐，rel1e-9/abs1e-12；精确CDF只说明原模型A&S近似误差，不用它的误差误判入口漂移。Tester检查本节三项：新入口边界及旧行为、真实全窗覆盖/因果与统计、载体/正文同源及scope。无公开功能问题则PASS/done；负策略结果不是工程FAIL。budget/缺数据真实阻塞要列唯一delta，不新建平台或擅改预算/数据/参数。实现75m/1、独立Verify45m/1，任务级gpt-6.1-sol/openai-codex；实现需留预算交接，不能为了全窗运行丢失状态登记。

### 19.4 reader性能增量与原卡续接（2026-11-12）

用户已选方案2，覆盖旧UD源码只读范围的唯一例外：`skills/data/unified_data/history_reader.py`、`skills/data/unified_data/tests/test_btc5m_history_reader.py`，及必要时新建同目录`test_btc5m_history_reader_performance.py`。不改history_types/client/storage、data-pipeline/生产数据/索引/日调度/Rust模型，不新增服务、Provider、依赖或并行抽取器。既有Lab/Rust候选保留，原t_a03a0dab Implement→t_552769cc Verify续接，不创建新图。

根因证据见本主题evidence/controller/read-cost-attribution.md。优化只改变内部成本：将完整manifest/coverage/output重算与页面内容验证分离，复用页内业务canonical字节/摘要、避免metadata/labels反复投影秒线。可采用请求内每页固定大小内容指纹+既有业务摘要；指纹必须涵盖实际内容，不可仅用_id/计数；指纹改变时按原业务投影重算比较，忽略raw引用的原业务语义保持。最多一页原始/规范化行与O(页数)固定大小摘要，禁止缓存整日/整窗对象、全局可变缓存或凭旧缓存跳过真实读取。每流结束及verify_consumed保留原变化检测，已走过页的变化也须检测，错误码与签名不变。

原reader修前三日golden为2026-08-10、08-11、11-10，固定as_of=2026-11-12T09:09:11Z；必须确认原采集终态成功且三文件/summary完整后才修改源码，不重复旧reader长跑。修后同请求与原golden比较content_manifest、三流逐payload摘要/计数、coverage/missing/pending/conflicts与verified；补provenance及raw-only变化定向测试。添加内容变更、schema/可得时间/label/行增删、已访问页变化、分片状态、请求隔离/重复迭代回归；不删弱旧断言。真实一日pilot复测含三流+verify，记录阶段耗时、查询/规范化次数与RSS；仅在原预算内有望完成才跑固定94日正式研究，超预算保留partial不伪PASS。独立Tester把本增量作为原三项验收的一部分，不重复全窗DB读取。

## 1. 设计摘要

T3 只接入 PascalMore Toolkits fork、复现原版 build/test、修正两份 Trading 入口的源码状态；T4 独立复跑，T5 独立审查，主控 Closeout。本文不执行接入或 Cargo，不改 RFC/SPEC，不创建下游卡。M1 PASS 仍严格等于 SPEC A-001..A-009 全满足；原版失败报告是有效交付证据，但不等于 M1 PASS。

唯一执行底座为 `https://github.com/PascalMore/Prediction-Markets-Trading-Bot-Toolkits`；已确认 `fork=true`、`default_branch=main`，parent/source 均为 `tarpboi/Prediction-Markets-Trading-Bot-Toolkits`。T3 接入前读回，不再请求确认 fork URL，不创建远程 fork。`https://github.com/PascalMore/predictfun-trading-bot` 仅研究，不登记、部署或构建第二工程。

所有门槛仅落实 SPEC §2、§4.2、§4.3、§4.bis、§5：来源/版本、防覆盖、原版构建、安全测试、真实证据和独立审查；不增加性能、收益、覆盖率百分比或 Shadow 观察日数门槛。200 USDT 本金及 100 USDT 全实验最大可接受亏损是用户约束，不是执行授权；1/5/5/20 USDT 分别对应单笔/占用/日停/复核建议，均未激活。Hermes 只读复盘、偏差分析和记忆，无真实账户签名、订单、运行控制或参数发布权限。

## 2. 现状分析

### 2.1 T2 已观察事实及限制

2026-11-09，Asia/Shanghai（UTC+08:00），仅只读观察：

- 主仓分支 `main`；`git status --short` 仅列本期 RFC/SPEC 两个未跟踪文件。它们是上游产物，T3 不暂存、不覆盖。
- `.gitmodules` 已有五个条目，包括 `skills/trading/auto-trading/quantdinger/QuantDinger`、`QuantDinger-Vue`、`QuantDinger-Mobile`，均 `branch=main`；无 Toolkits section。它们不是 M1 允许改动的对象。
- `git ls-files --stage -- skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits` 为空；目标既非现存路径也非符号链接，`realpath -m` 与指定绝对路径一致。主仓 Git common dir 为 `/home/pascal/workspace/yquant-investment/.git`。T3 必须重新观察，不能用本快照替代接入前检查。
- `skills/trading/SKILL.md:3,12–14,45,60–68` 与 `README.md:5–15,19,35–39` 仍有“仅规划”“QuantDinger 候选、目录未创建”和旧 `auto_trading` 路径，需要按真实接入结果最小修正。
- [研究树存档](../../../data/reports/2026-11-09-predict-btc5m-intake/evidence/tarpboi-tree.json) 对应 `71c0e4ff9e299f9a4d81757fd6b15cf54da69b38`；不是完整安装包。研究版 `Cargo.toml` 包/bin 为 `polymarket-toolkits`，入口 `src/main.rs`，依赖包含 HTTP/WebSocket、签名和文件 I/O；不能据此断言实际 main 的 build/test 均安全。
- 研究版 `src/config.rs:584–614` 的 `AppConfig::load` 会尝试读凭据文件和环境覆盖；不得因 mock/dry-run 默认值放行该路径。`src/service/predict_fun.rs:1981–2005` 两个真实 testnet 测试已 ignored；实际 main 仍须重新分类。

本卡未查询 actual fork main SHA，未读取交易凭据，未运行 Cargo；因此工具链、全量实际测试及动态结果均为未测，非 Design 阻塞。当前未发现契约级冲突或目标路径阻塞。

### 2.2 兼容性原则

遵守任务指定的 submodule-main-only-workflow：接入由 `git submodule add -b main` 建立 main 工作树；保持 main 跟踪 origin/main，不 checkout 历史 SHA、不创建额外本地分支、不使用 detached HEAD、不 fetch/merge upstream。研究 SHA 仅用于对象/差量读取。M1 不修改原包名、源码、测试、许可证、锁文件、策略或配置，不借原版失败做业务修复。

## 3. 方案设计

### 3.1 模块/文件改动（精确 allowlist）

以下为 T3 实现阶段范围；T2 实际只创建本文。

| 路径（相对工作区） | T3 允许动作及边界 |
|---|---|
| `.gitmodules` | 仅新增 section `submodule "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits"`，字段 path、url、branch；其他 section 逐字不变 |
| `skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits` | 主仓仅此一个 stage 0、mode 160000 gitlink；原版子模块 main，内部不逐文件跟踪到主仓，不改源码/配置/测试；允许默认忽略的编译产物 |
| `skills/trading/SKILL.md` | 仅 §触发与状态、相关处理方法的状态句、§正式来源增加本契约引用、§实际目录；frontmatter description 只校正“仅规划”状态措辞。分工、安全边界及其他正文不重写 |
| `skills/trading/README.md` | 仅 §当前实际状态与目录树、§入口与分工中的 Trading 状态/本契约链接、§后续增量建设末段的 QuantDinger/Toolkits 源码状态、末节的本次核验范围；不重写模块规划 |
| `data/reports/2026-11-09-predict-btc5m-m1/report.md` | 累加 Implement/Verify/Review 的来源、命令、测试、A 项及 C–H 差量；不覆盖原阶段结果 |
| `data/reports/2026-11-09-predict-btc5m-m1/evidence/` | 按 §3.4 保存每次真实日志与审查记录；不得把真实凭据输出收集进来 |
| `data/tasks/done/2026-11-09-predict-btc5m-m1/` | 历史过程现已归档；当时计划新增必要 implement/verify/review 交接，保留上游交接 |

Git 接入自身生成目标工作树 `.git` 文件、主仓 `.git/modules/` 对应对象及 `.git/config` 对应登记，是接入的必要内部元数据，不是业务配置授权。不手工改其他 Git 配置，不改身份、credential helper、全局 Git 设置或既有模块配置。

禁止触碰：RFC/SPEC 本文来源文件、`docs/{rfc,spec,design}/*template*.md` 及各层 README、`docs/rfc/07_trading/RFC-26-072-trading-intelligent-trading-framework.md`、根 README、其他子模块及 `.gitmodules` 其他 section、`skills/strategies/strategy-lab/`（含 `quantdinger.py` 和任何实例）、`data/reports/2026-11-09-predict-btc5m-intake/` 整个旧报告及 evidence、任何实际凭据/运行配置、任何 `data/` 外的新运行配置、profile/Hermes、`/home/pascal/workspace/yq-yinglong`。公开 Cargo 清单/钩子与配置加载源码只读审查不等于允许修改配置。不得建 Lab 空骨架、第二执行工程、公共 CLI、服务/UI、数据库/schema、调度或推送。

### 3.2 数据流/控制流与命令序列

```text
T3 读取契约/现状 → 来源和路径前检 → 唯一 fork/main 接入
 → 登记/归属/SHA/原版读回 → 实际源码副作用审查
 → 原版 build → 测试清单与安全集合执行 → 状态复核/报告/入口
 → T4 同一 SHA 独立复跑 → T5 审查 → 主控 Closeout
```

任一步失败按 §6 停止对应后续动作。以下所有写入和 Cargo 示例只供获派 T3/T4 执行，不是本卡已经运行的结果。

#### 3.2.1 无人值守命令纪律与公共变量

worker 的 `-q` 是已有 Hermes 运行方式，不加到 Git/Cargo，不嵌套启动新 Hermes worker。用 `terminal` 直接调用短 Git/Cargo/系统命令，配合 `read_file`、`search_files`、`write_file`、`patch`。不用 `execute_code`、内联 Python、解释器启动子进程或新增校验脚本，不改审批策略。安全拒绝立即记录并停止，不换执行器或改写命令绕过。

每个代码块按顺序在同一 terminal 会话执行；先设置下列仅供 shell 拼接路径的变量，不写入配置文件，也不是新增业务输入。若新会话，重跑本块。

```bash
cd /home/pascal/workspace/yquant-investment
export ROOT=/home/pascal/workspace/yquant-investment
export REL=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
export SUB=/home/pascal/workspace/yquant-investment/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
export FORK=https://github.com/PascalMore/Prediction-Markets-Trading-Bot-Toolkits
export RESEARCH=71c0e4ff9e299f9a4d81757fd6b15cf54da69b38
```

记录命令时展开实际路径并保存 cwd。每个有独立判定的命令独立调用 terminal，读取该调用真实 `exit_code`，不把一串命令最后的状态冒充前面的退出码。运行前、后分别直接调用 `date --iso-8601=seconds`，保留带偏移时间；精确命令输出由文件工具保存到 §3.4。Cargo 不使用 `| tee` 或日志管道，防止掩盖失败码；超时/中止只记工具实际终止事实与已见输出，不补造结束码或测试结果。

#### 3.2.2 前置只读检查（T3，写入前）

主仓 cwd 固定为 `$ROOT`，依次独立执行：

```bash
git status --short
git diff --name-status
git diff --cached --name-status
git config -f .gitmodules --get-regexp '^submodule\..*\.(path|url|branch)$'
git ls-files --stage -- "$REL"
git ls-tree HEAD -- "$REL"
realpath -m "$SUB"
test ! -e "$SUB" && test ! -L "$SUB"
git rev-parse --path-format=absolute --git-common-dir
git rev-parse --path-format=absolute --git-path "modules/$REL"
```

用文件工具读取 `.gitmodules`，同时核对所有 section 名、所有 path 值，防止“section 名不同、path 相同”的重复。对最后命令返回的确切 modules 目录由文件工具/直接 `test -e` 检查；本工作区首次接入的完整检查为：

```bash
test ! -e /home/pascal/workspace/yquant-investment/.git/modules/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
```

通过条件：目标及对应 section/path/index/HEAD/modules 槽位均不存在，祖先目录没有把目标重定向到工作区外；`.gitmodules` 无既有未提交或暂存变更。其他路径已有变更不要求清理，只记录并保留。两份入口若已有他人未提交修改，停止该文档编辑并报告碰撞，不覆盖。

幂等分支：若路径已完整匹配已确认 fork/main/主仓管理的子模块，则不再 `add`，转 §3.2.4 验证并记录复用；不得主动 pull。普通目录、符号链接、独立 `.git` 目录、部分登记、孤立 modules 槽位、他人 dirty 内容或不一致 index 都是冲突，保留并停止接入，不覆盖/强制修复。T3 在此重读实际状态，若出现新增冲突向主控写明预期/实际。

只读读取公共 GitHub API，不读取/输出登录凭据：

```bash
curl --fail-with-body --silent --show-error --location https://api.github.com/repos/PascalMore/Prediction-Markets-Trading-Bot-Toolkits
git ls-remote "$FORK" refs/heads/main
```

保存 API 输出，人工核对 `full_name=PascalMore/Prediction-Markets-Trading-Bot-Toolkits`、`fork=true`、`default_branch=main`、parent/source 为指定 upstream（或 SPEC 允许的可验证 parent 链）。缺字段/404/限流/无权限均不得推断通过；停止接入并报告实际访问问题，不改用 upstream、镜像或新建 fork。`ls-remote` 必须恰有该 main ref 的实际 SHA，不以空输出为通过。

#### 3.2.3 接入（仅首次无冲突时，T3）

固定使用 HTTPS 已确认 URL，最小命令为：

```bash
cd /home/pascal/workspace/yquant-investment
git submodule add -b main https://github.com/PascalMore/Prediction-Markets-Trading-Bot-Toolkits skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
```

不先 `mkdir` 同名普通源码目录，不单独 clone 再搬入，不 shallow，不使用 `--force` 或递归接入其他模块。该命令会定向暂存 `.gitmodules` 和 gitlink，允许这一必然效果；不运行全仓 `git add`，不暂存其他文件，不 commit/push。

新增 section 期望内容（实际由 Git 生成，不手工重复追加）：

```ini
[submodule "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits"]
    path = skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
    url = https://github.com/PascalMore/Prediction-Markets-Trading-Bot-Toolkits
    branch = main
```

#### 3.2.4 登记、工作树归属与版本读回（T3/T4）

在 `$ROOT` 逐条执行，保存输出，不只看 add 的退出码：

```bash
git config -f .gitmodules --get-regexp '^submodule\.skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits\.(path|url|branch)$'
git config --local --get submodule.skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits.url
git ls-files --stage -- "$REL"
git -C "$SUB" remote get-url origin
git -C "$SUB" symbolic-ref --short HEAD
git -C "$SUB" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git -C "$SUB" rev-parse HEAD main origin/main
git ls-remote "$FORK" refs/heads/main
git -C "$SUB" rev-parse --show-toplevel
test -f "$SUB/.git" && test ! -d "$SUB/.git"
git -C "$SUB" rev-parse --absolute-git-dir
git rev-parse --path-format=absolute --git-common-dir
git rev-parse --path-format=absolute --git-path "modules/$REL"
git -C "$SUB" rev-parse --is-shallow-repository
git -C "$SUB" status --porcelain=v1 --untracked-files=all
git -C "$SUB" diff --exit-code
git -C "$SUB" diff --cached --exit-code
git -C "$SUB" hash-object Cargo.lock LICENSE
git -C "$SUB" rev-parse HEAD:Cargo.lock HEAD:LICENSE
```

用 `read_file` 读取 `$SUB/.git` 文件（实际完整路径为 `/home/pascal/workspace/yquant-investment/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/.git`），其 `gitdir:` 相对值以该文件所在目录为基准解析；`--absolute-git-dir` 的规范路径必须落在主仓 common dir 的 `modules/` 内，并与目标 modules 槽位一致。不能仅凭 `.git` 是文件或字符串包含 `modules` 就通过；若有符号链接，用 `realpath` 规范化返回的实际路径后再比对。不需要内联脚本。

判据：`.gitmodules` 唯一匹配 section/path，URL 与 origin 指向同一确认 fork；本设计固定 HTTPS，自动 `.git` 后缀表示差异须记明等价来源。`ls-files --stage` 对整个目标前缀恰一条 `160000`、stage 0 记录，内部无逐文件条目；当前分支 `main`、upstream `origin/main`，HEAD/main/origin/main/gitlink/观测远端 main 的 SHA 全同。`--is-shallow-repository=false`，LICENSE/Cargo.lock blob 与工作树 hash 分别相同，工作树及暂存内容无差量。原版历史保留，不用源码 dump 代替。

若 remote main 在接入和验证期间移动，保存两次观察时间与 SHA，停止基线判定，不自动 fetch/pull/更新 gitlink；由主控指定采用的基线后重跑受影响验证。T4 使用 T3 的 actual SHA，不能自己升级。

研究差量在 `$ROOT` 逐条读取：

```bash
git -C "$SUB" cat-file -e "$RESEARCH^{commit}"
git -C "$SUB" merge-base --is-ancestor "$RESEARCH" HEAD
git -C "$SUB" diff --stat "$RESEARCH" HEAD
git -C "$SUB" diff --name-status "$RESEARCH" HEAD
git -C "$SUB" diff "$RESEARCH" HEAD -- LICENSE Cargo.lock Cargo.toml src/bot/arbitrage.rs src/bot/orderbook_imbalance.rs src/bot/runtime.rs src/service/predict_fun.rs
```

仅在对象存在时执行后续比较。ancestor 命令 exit 0 表示祖先、exit 1 表示不是祖先，不把 1 当对象缺失；其他错误单列。记录相等性、历史关系、文件差量及已知缺口是否仍在。对象缺失时仅使用已接入 fork 的已有历史及旧研究存档说明可核查范围；不 clone/fetch upstream、不 checkout 研究 SHA，不把缺差量证据写成 A-003 PASS。

#### 3.2.5 原版构建/测试前副作用审查（T3，T4 复核）

实际 main 文件才是准绳。先用文件工具发现/读取以下对象及其引用，不执行仓库脚本：

| 审查面 | 文件/调用链和必须回答的问题 | 决定 |
|---|---|---|
| 构建选择 | 根/成员 `Cargo.toml` 的 package/workspace/bin/lib/test/example/features/default-features、`build=`、依赖/补丁；`Cargo.lock` 是否跟踪存在；`rust-toolchain`/`rust-toolchain.toml` 如存在 | 原包名与默认目标不改，不猜 MSRV，不改锁或增加 features |
| 构建副作用 | `build.rs` 及清单指定钩子、相关被调用脚本、proc-macro/build-dependency 声明、`.cargo/config`/`.cargo/config.toml`（含祖先目录适用配置）的 aliases/runner/rustc-wrapper/环境引用；CI 工作流只作命令线索 | 缺失记“未发现”；存在则追调用。业务请求、凭据读取或不明外部程序使相关 build/test 停止，不能因是 build 放行 |
| 测试/文档入口 | 实际 `src/lib.rs`、`src/main.rs`、所有测试模块/辅助函数、`tests/`、doctest 和 Cargo 目标；清单发现不只依赖研究树 | 审查 `#[test]`、异步测试、ignore、初始化/Drop/后台任务及间接 I/O；`--list` 也可能编译/启动测试 harness，须先审查 |
| 配置/凭据路径 | `src/config.rs` 中 `AppConfig::load` 及实际配置加载调用者，env 覆盖、文件读写路径、公开 fixture 引用 | 不读取实际凭据文件，不打印 env/配置全文；读取配置加载源码与公开固定 fixture 不等于运行加载真实配置 |
| 业务外部调用 | `src/service/predict_fun.rs`、`spot.rs`、`clob.rs`、`onchain.rs`、`eligibility.rs`、`polymarket_read.rs` 及实际新增模块；HTTP/WS/RPC/数据库、钱包、签名/订单路径 | 分类到每个测试；本地 FakeVenue/固定公开向量可运行，真实场所/testnet/钱包/账户 I/O 不运行 |
| 脚本和运行入口 | `scripts/`、Cargo alias、README 和 `.github/workflows/` 引用的 install/run/check 命令；文件不存在明确记录 | 不运行安装器、bot、二进制、`cargo run`、`check-venue`、`--sign-in`、shadow/dry-run 或部署命令 |
| 环境/工具链 | 当前已安装工具链、有效 Cargo 配置/工具包装与锁定依赖来源；不输出任何真实环境秘密 | 只允许已安装工具链与普通锁定依赖下载/编译，不运行 rustup install/update/default 或系统包升级 |

T3 在 `evidence/implement-01/side-effect-review.md` 写文件:符号/行号、所追调用、每个目标/测试分类及批准的精确命令。仅发现文件名不足以批准。配置文件可能含真实秘密时不打开/复制正文，只检查适用位置并由受控环境确认有效配置；无法确认包装器/配置或测试副作用就停止相关命令、报告缺证据。不遍历用户密钥目录，不 source `.env`，不继承额外账户参数，不设置虚假密钥来“让测试跑起来”。固定公开向量的本地密码学单测允许；任意新建真实账户订单签名不允许。无需新建沙箱平台；安全前提无法落实就如实阻塞执行。

允许联网只包括已确认 fork/公共 GitHub 来源检查，以及 Cargo.lock 对应普通依赖下载。依赖自身 build script 有业务副作用也不放行。禁止真实业务 HTTP/WS/RPC、账户/钱包/生产数据库、测试网交易和实时采集。Cargo `--offline` 不限制测试 socket，不能作为业务离线证明；本期也不以额外全依赖供应链审计替代上述具体入口审查。

#### 3.2.6 工具链、build/test 的最小命令形状

在实际源码审查后检查工具路径；若 rustc/cargo 是 rustup 代理，先通过 `rustup toolchain list` 及已读工具链声明确认所选工具链已安装，避免版本探测触发自动安装。缺失/不兼容只记录到报告，不安装/升级。不得采集全量环境变量。

```bash
cd /home/pascal/workspace/yquant-investment/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
command -v rustc
command -v cargo
rustc --version
cargo --version
```

每条独立 terminal 调用；已安装时记录实际工具链/版本及配置选择依据。然后依次执行，每条另起调用保留真实返回：

```bash
cd /home/pascal/workspace/yquant-investment/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
cargo build --locked
```

```bash
cd /home/pascal/workspace/yquant-investment/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
cargo test --locked -- --list
```

实际默认集合全部安全（包括已忽略项不被执行）时：

```bash
cd /home/pascal/workspace/yquant-investment/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
cargo test --locked
```

默认 profile/default features 足够，不要求 release、all-features、bench 或 clean build。`--list` 不是测试通过；需与源码发现的 lib/bin/doc 目标交叉核对，尤其 doctest 不能因未出现在某一 harness 列表就遗漏。

若实际 main 的以下两个已知测试改成默认非忽略而仍有真实联网副作用，且审查确认没有其他危险默认测试，使用完整名明确排除的命令如下（它是条件分支，不与无 skip 命令重复计作两轮全基线）：

```bash
cd /home/pascal/workspace/yquant-investment/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
cargo test --locked -- --skip service::predict_fun::tests::live_large_trade_feed_reads_real_history --skip service::predict_fun::tests::live_testnet_dry_run_pipeline
```

研究 SHA 中这两项本已 ignored，若 actual 仍如此则运行默认命令，记录为“默认 ignored”，不要再给它们加 skip。出现其他危险默认项，T3 根据真实完整名在命令表逐项追加 `--skip`，先记录具体完整命令与源码理由再执行；不按 `live` 子串批量过滤，不伪造未知名称，不改测试为 ignore。如危险 doctest/自定义 harness 无法安全排除，停止相关命令并标 A-005 未完成，不漏跑后称通过。不运行 `--ignored`/`--include-ignored`。

每个测试用完整名与 lib/bin/doc 目标作为标识，分类为纯计算、本地 fixture（含固定公开 SDK 对拍）、真实联网、凭据或交易副作用。结果独立为 PASS/FAIL/SKIP/NOT_RUN：

- PASS/FAIL 必须来自实际 test 日志；同名多目标分别列，不拿编译成功或 `--list` 当 PASS。
- 默认 ignored 写 `SKIP；mechanism=ignored；源码 ignore 理由`，保留 harness 的 ignored 计数。
- 显式 skip 写 `SKIP；mechanism=explicit_skip；完整名/命令/副作用理由`，对应 harness filtered-out，不并入 ignored；确认过滤只排除预期项。
- 构建失败、未获安全批准或命令未执行写 NOT_RUN，原因具体。若已错误触发真实联网，保留事实，不能事后重标为预先 skip。
- 逐命令、逐目标记录 passed/failed/ignored/filtered-out 与实际清单，重复执行不累加“唯一通过数”；doctest 单列。安全集合必须非空，S0/S2 对应原版单测必须实际覆盖，其他安全默认测试不能漏跑。

构建/测试后在主仓重跑 §3.2.4 的状态、diff、锁文件/许可证 hash 比较，并核对 gitlink 与 SHA 未变。仅默认忽略的 `target/` 等编译产物可保留；新 untracked 配置、账本或业务状态文件不是允许的构建产物，不删除掩盖，停止并报告。构建失败不继续宣称测试基线完成；日志中的警告也保留，不修原版代码取绿灯。

#### 3.2.7 两份入口文档最小校正

T3 使用文件工具定向 patch，保持原分工和权限正文：

1. QuantDinger 分别写现有 `.gitmodules` 的准确三个路径与“源码已登记”；不据此声称三者的功能、本次构建或交易能力已验证，不改其源码/指针。
2. Toolkits 写唯一 fork、准确路径和本契约集引用；接入失败写未接入/失败，build/test 失败写已接入但原版基线未通过，成功写“Implement 原版构建及安全离线测试通过；联网/交易路径未验证，待独立 Verify/Review”。主控 Closeout 前不写 M1 最终通过。
3. 删除本次直接相关的“QuantDinger 候选、目录未创建”及旧 `auto_trading` 路径断言；目录树只列真实存在路径，不预建将来实例。
4. 保留 OctoBot 移除事实，明确未新增模拟/实盘、账户或运行控制授权。技能可发现、源码存在、原版验证、运行许可四者分开。

T3 核对 diff 仅落 §3.1 指定语义区域；T4 验证实际文件，T5 逐句核对状态与证据，不把入口纠错扩成全仓文档治理。

### 3.3 接口与数据结构

无新增 API、程序 CLI、函数签名、业务配置或生产数据模型。输入仍为 SPEC §4.1 固定 fork/path/main/research SHA；输出仅 Git 状态、原版命令结果和人工可读证据。shell 路径变量不是发布参数，研究 SHA 不是运行版本开关。report 表格复用 SPEC §4.bis，不新增 manifest/schema/解析器。

### 3.4 持久化设计（对齐 SPEC §4.bis）

主题根为 `/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/`。以下命名是首轮完整示例；既存文件不得覆盖，重跑用 `implement-02`、`verify-02` 等新目录，report 追加对应节和链接，不把旧 FAIL 改成 PASS。

```text
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/report.md
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/implement-01/source-api.json
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/implement-01/git-preflight.log
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/implement-01/git-add-readback.log
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/implement-01/research-diff.log
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/implement-01/side-effect-review.md
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/implement-01/toolchain.log
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/implement-01/cargo-build.log
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/implement-01/cargo-test-list.log
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/implement-01/cargo-test.log
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/implement-01/tests.md
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/implement-01/git-postcheck.log
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/verify-01/cargo-build.log
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/verify-01/cargo-test.log
/home/pascal/workspace/yquant-investment/data/reports/2026-11-09-predict-btc5m-m1/evidence/review-01/review.md
```

Verify 另存自己的 source-api.json、git-readback.log、side-effect-review.md、toolchain.log、cargo-test-list.log、tests.md、git-postcheck.log，命名同 Implement；不得复制 Implement 日志冒充独立复跑。未运行命令无需造空日志，report 的 evidence_ref 指向记录未运行原因的真实阶段审查文件。

| 存储对象 | 精确写入触发点 | 字段子集/来源 | 写前过滤、错误及回滚 |
|---|---|---|---|
| `.gitmodules` / gitlink | §3.2.3 `git submodule add -b main` | path/url/branch、实际 SHA | 仅确认 fork、无秘密 URL；失败读回部分状态，按 §6 处理 |
| `evidence/implement-01/source-api.json`（Verify 同名独立副本） | §3.2.2 公共 curl 结果后 worker 用 `write_file` 保存实际响应 | fork/full_name/default_branch/parent/source 的公共响应，report 引用 | 不用假 JSON 补缺字段；网络失败保存真实错误日志而非伪造成功响应 |
| 各 `*.log` | 每次直接 terminal 调用返回后，用文件工具保存实际 stdout/stderr/真实退出码及时间记录 | command、cwd、started_at、ended_at、exit_code、工具/版本、输出 | 不加 `env`、凭据全文或账户路径；若工具输出被截断，读取工具给出的完整输出文件后保存，不把 head/tail 当完整日志；无法取全即缺证据 |
| `side-effect-review.md` / `tests.md` | build/test 前源码分类；命令后逐项补结果 | 实际文件:符号/行、目标、test_name/category/result/reason、skip mechanism、计数与命令引用 | 公开向量只记测试符号，不复制密钥值；写失败或未分类完整则不运行下一相关命令 |
| `report.md` | T3/T4/T5 每阶段报告交接前用 `patch` 追加（首次 `write_file`） | 下列必填表字段 | 先读已有文件，保留所有旧结果；写失败保留工具输出并停止完成声明，不新造报告平台 |
| 过程交接 | 历史交接现位于 `data/tasks/done/2026-11-09-predict-btc5m-m1/implement-handoff.md` 等 | 本阶段事实、A 项、停止点、report 路径、下一角色 | 不复制报告第二结论正文；失败模板见 §6.3；归档不改变历史结论 |

report.md 必须包含：

- 来源表：task/stage（真实任务 ID/角色/轮次）、来源日期/时区、fork_url（确认形式及实际 origin 表示）、confirmation_ref（t_24ca3fd4 恢复授权及主控 UNBLOCK 引用）、API parent/source 和证据、research_sha、actual_sha、research_diff（相等/祖先/差量/缺证据）。
- 命令表：每个命令实际 cwd、展开后的 command、选用工具链及版本、started_at、ended_at（UTC 或偏移）、exit_code、evidence_ref。只有未执行可为 null 并写原因；未知终止状态不得填 0，另列真实工具终止事实。
- 测试表：目标 + test_name、category、PASS/FAIL/SKIP/NOT_RUN、reason、ignore/explicit_skip 机制、命令/日志引用；逐目标 passed/failed/ignored/filtered-out 和去重清单。不能凭本设计填预计总数。
- 结论表：A-001..A-009 每项结果、证据引用、未通过/未执行原因；各阶段结论分开，M1 最终结论由主控依 Verify/Review 关门。
- remaining_gaps：C–H 的保留/缺失/未测、原版结果后重估假设、工程时间/授权等待/数据与 Shadow 观察时间分列；无原版结果则写未重估及阻塞。

生命周期：无 TTL、不清理缓存、不删除旧日志；`data/` 仍按现有规则忽略，本地保存不等于提交/备份/允许公开，不改 `.gitignore`。主控最终整体移至 `data/tasks/done/2026-11-09-predict-btc5m-m1/`，T3/T4/T5 不提前搬迁。M1 没有数据库 client、生产写入、schema/索引、mock client 或迁移；测试替身复用原版 FakeVenue/本地 fixture。后续业务状态默认 MongoDB，届时另行设计授权，不引入 SQLite 生产账本。

### 3.5 UI/原型设计

无。

## 4. 实现计划

| 顺序 / 负责人 | 执行动作 | 看到什么才可继续 |
|---|---|---|
| 1 / 主控 | 读取 RFC/SPEC/本文及 T1 交接，另派 T3；本卡不创建任务 | 三层文件独立存在、V1.1 输入语义一致；来源无需再澄清 |
| 2 / T3 yquantdeveloper | §3.2.2 前检、公共 API/remote main；保存 git-preflight/source-api | 无路径/index/元数据碰撞，来源成立；否则按 §6 停止 |
| 3 / T3 | §3.2.3 接入、§3.2.4 读回 | 唯一 gitlink/归属/main/SHA/原版与差量可证，既有模块不变 |
| 4 / T3 | §3.2.5 审查，§3.2.6 build/list/test/postcheck | 真实 build=0；非空安全默认集合通过且 S0/S2 覆盖；危险项全部分类；原版不变 |
| 5 / T3 | §3.2.7 定向入口修正，§3.4 报告，§7 C–H 差量 | 状态与日志一致，allowlist 无越界；交主控/T4，不自称 M1 最终完成 |
| 6 / T4 yquanttester | 同一 SHA 独立来源/归属/版本核验，独立审查并重跑 build/list/test | A-001..A-005、A-007..A-009 的事实逐项验证，日志和计数独立；允许编译/依赖缓存，不运行 clean |
| 7 / T5 yquantreviewer、主控 | §5 观察点审查；主控按 A-001..A-009 Closeout | Review 覆盖三层文件/范围/来源/边界；失败不 Closeout 为 PASS |

## 5. 测试策略与 Verify/Review 观察点

T4 复用本文命令但必须实际重跑；T5 读取证据、diff 和测试清单，不代写测试框架或通过构造破坏性 Git 状态做负向实验。完整测试名以 actual 发现为准，SPEC §6.1 已列 S0/S2/FakeVenue/本地 SDK 参考用例；名称消失或变化时核对实际等价覆盖并说明证据，不偷偷删减验收。

| SPEC 验收 | T4 可核验观察点 | T5 审查要求 |
|---|---|---|
| A-001 / F-001 | 独立公共 API 读回与确认引用；fork/main/parent/source、实际 origin、remote main | 不用 upstream/研究参考 fork 代替；404/缺字段没有假通过 |
| A-002 / F-002..003 | §3.2.4 path/url/branch；目标前缀恰一条 stage 0 的 160000，无内部文件；`.git` 文件 canonical gitdir 归属主仓 modules；HEAD/main/origin/main/gitlink/远端 SHA 一致 | 主仓指针与子模块工作树都审；无 detached/历史 checkout/新分支/自动 pull；已有其他 gitlink 不变 |
| A-003 / F-003 | 非 shallow、LICENSE/Cargo.lock blob 相同；前后 status/源码与暂存 diff 无变化；research SHA 关系及差量可核查 | 缺历史/差量不记 PASS；actual 不同于研究 SHA 本身不是失败；忽略 target 产物不等于忽略业务文件 |
| A-004 / F-004..005 | 工具链/副作用审查、独立 `cargo build --locked` exit 0、完整日志、锁文件不变 | 禁止改锁/依赖/业务源码取绿灯；工具链未安装不伪造 build 结果 |
| A-005 / F-004..005 | 独立清单 + 安全集合命令；S0/S2 实际测试覆盖；逐目标 passed/failed/ignored/filtered-out 与 tests.md 一致 | `--list` 非 PASS；默认 ignored 与显式 skip 分开，非空安全测试成功；网络/交易路径一律未验证 |
| A-006 / F-007 | Tester 与 Implement 同一 SHA、不同真实命令日志；T5 后独立审查结果 | 三层文档存在且分层；不把 Implement 日志当复跑；不省略角色 |
| A-007 / F-006 | 两份入口仅改允许段落，QuantDinger 源码与 Toolkits 基线区分；准确目录/来源/状态/契约引用 | 无“候选目录未创建”等直接失实描述；无新增运行权限或实盘就绪暗示 |
| A-008 / 全范围 | 主仓 `git diff --name-status`、`git diff --cached --name-status`、`git status --short`，再读 `.gitmodules` diff 和两个入口 diff；对照 T3 前快照 | 仅本次 allowlist 增量；未跟踪/忽略 data 报告也审；不误把 T1 文件当 T3 修改，不启动业务或激活资金建议 |
| A-009 / F-008 | report/evidence 逐命令退出码/时区/计数和 C–H 差量重估假设 | 报告可复现、旧失败保留、没有伪造数据/日期/完整测试数；工期与观察时间分开 |

两份入口及本文的本地引用通过文件工具按所在目录解析，未来输出路径使用普通路径声明，不将尚不存在报告当现存链接。正文空白检查使用独立直接 Git 命令；新未跟踪文件另用 `git diff --no-index --check -- /dev/null docs/design/07_trading/DESIGN-07-001-predictfun-btc5m.md`。no-index 可能因存在差异返回 1，必须记录实际退出码及诊断，不能改报 0；不能只凭 tracked `git diff --check` 宣称新文件已校验。

## 6. 风险、降级与回滚

### 6.1 失败停止点

| 情况 | 停止点、证据与交接 | 禁止动作 |
|---|---|---|
| 路径/section/index/modules 或他人修改冲突 | add/入口编辑前停；git-preflight.log 写预期与实际，交主控 | 不覆盖目录、不 stash/reset/clean、不删除既存 modules、不修改他人文件 |
| 来源失败或接入命令失败/安全拒绝 | 停 add 后续；保存 API/命令真实退出码和部分登记只读状态；A-001/002 未完成 | 不换 upstream/执行器、不创建 fork、不强制重试或自动修复部分登记 |
| 工具链缺失/不兼容、锁定依赖获取或编译失败 | 停 Cargo 后续基线声明；toolchain.log/cargo-build.log、report A-004 未通过 | 不自动安装/升级、不改 Cargo.lock/依赖/源码、不降低验收 |
| 审查发现业务/凭据副作用 | 对应命令执行前停；side-effect-review.md 写调用证据/分类 | 不运行 bot、业务网络或账户路径；不靠 `--offline`、虚假密钥或断网失败证明安全 |
| 安全测试失败、漏跑、空集、计数不符 | 保存 cargo-test.log/tests.md，A-005 未通过；可做只读根因分析后交主控 | 不改测试/断言/参数，不把 FAIL 改为 SKIP，不只挑 S0/S2 冒充默认集合 |
| 超时/被终止/结果未知 | 停止判 PASS，记终止事实和已见日志；仅有真实测试结果的项目可单列结果 | 不猜测 exit 0/未输出计数，不自动重跑掩盖旧结果 |
| 构建/测试通过但 C–H 已知未实现 | 保留残余风险；不阻塞限定 M1 审查，只按 §7 交后续 | 不顺手修 UNKNOWN/费用/恢复/OBI，不启动 shadow 或交易 |

构建/测试失败一般保留已成功接入的干净原版子模块供复现，不自动撤销/重新接入。报告先于任何回滚；证据保存失败不能宣称交接齐全。

### 6.2 定向可逆撤销（T3，仅本次新增登记）

只有 T3 前快照证明目标在 HEAD/index/工作树/modules 和本地登记均不存在、`.gitmodules` 原来干净、且没有其他 worker 接手/新增变化时，才可按本节撤销自己新建的接入；复用的既有子模块不适用。无法证明归属或状态变化时只保留现场报主控，不尝试通用清理。

1. 先保存 API、add、postcheck 和失败日志；记录当前 SHA、`.gitmodules` 新增 section 及暂存 diff。两份入口如已修改，只用 `patch` 反向撤销自己本轮的具体文本块，保留其他修改，不整文件覆盖。
2. 用 `patch` 仅删除 `.gitmodules` 本轮新增 section。不要用 checkout/restore 覆盖整个工作树文件。由于前检已要求它原来干净，可在主仓只撤销本轮两条 index 变化：

```bash
cd /home/pascal/workspace/yquant-investment
git restore --staged --source=HEAD -- .gitmodules skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
```

3. 先只读核对本地 submodule section 确为本轮自动新增、无他人修改，再移除这一 section（不是修改 credential helper 或其他配置）：

```bash
cd /home/pascal/workspace/yquant-investment
git config --local --remove-section submodule.skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
```

4. 若工作树目录确为本轮生成且不存在任何未知内容，先检查隔离目标不存在，再定向搬移保留，不删除对象库。完整首轮例子如下；已存在隔离目录则停止，不覆盖：

```bash
test ! -e /home/pascal/workspace/yquant-investment/data/tasks/done/2026-11-09-predict-btc5m-m1/rollback-implement-01
test ! -L /home/pascal/workspace/yquant-investment/data/tasks/done/2026-11-09-predict-btc5m-m1/rollback-implement-01
mv /home/pascal/workspace/yquant-investment/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits /home/pascal/workspace/yquant-investment/data/tasks/done/2026-11-09-predict-btc5m-m1/rollback-implement-01
```

这三条必须逐条检查返回，只有前两条均成功才执行 mv；过程主题目录须已存在。保留主仓 `.git/modules/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits` 不删除。搬移后 `.git` 相对路径不再可用，隔离目录是保全副本不是新可运行仓库；不在隔离目录运行 Git/Cargo。恢复时由主控确认重新接入范围，将目录放回原路径即可恢复原相对 `.git` 关系，再按已保留 section/index/SHA 记录登记并重做 §3.2.4 全部读回。隔离残留和 modules 槽位须在交接明确标注，后续不得盲目再次 add。

5. 用 §5 的主仓 diff/index/status 读回，确认只撤销了本轮登记/入口变化，证据仍在。部分接入失败如没有形成某一对象，跳过对应撤销并记录，不把“不存在”当必须执行的删除动作。

此撤销不运行 reset/stash/clean、`rm -rf`、强制 deinit、全局配置修改、Cargo clean、commit/push；不删既有目录，不回退其他子模块。不能安全撤销就保留现场交主控，不能为了“回滚完成”扩大副作用。

### 6.3 失败交接文案模板

历史交接归档位置为 `data/tasks/done/2026-11-09-predict-btc5m-m1/implement-handoff.md`（Verify 对应用 verify-handoff.md），各字段用实际工具结果填写，不把本段当已发生记录或新的写入指令：

| 字段 | 必填内容 |
|---|---|
| task/stage/时间 | 真实任务 ID、角色、轮次、带时区时间 |
| stopped_at | 精确步骤/命令、cwd、实际 exit_code 或未执行/终止事实 |
| expected / actual | 来源/path/main/SHA/构建/测试中哪项预期与实际不符 |
| acceptance | A-001..A-009 各项当前结果；未执行不得 PASS |
| preserved | report.md 与本轮 evidence 的完整路径；登记/index/工作树/modules 是否保留、是否隔离 |
| rollback | 未执行/定向撤销了哪些具体文本和 Git 元数据；未撤销原因 |
| not_done | 未运行或禁止的动作：无 bot/业务网络/账户/配置激活/commit/push；有偏离如实说明 |
| next_owner/action | 主控需处理的具体访问、环境、碰撞或契约问题；不得笼统要求重新确认已知 URL |

真正的契约级冲突交 Principal/主控，记录预期/实际并 block，不自行改 RFC/SPEC。环境/原版失败交主控裁决后续最小动作，不无限追加设计迭代。

## 7. 交接给实现者与 C–H 重估

### 7.1 T3 必须遵守 / 可判断边界

- 必须遵守：唯一 fork/path/main、原版无改动、§3.1 allowlist、先副作用审查再执行、真实退出码/计数、失败停点、独立 Verify/Review。禁止任何运行/资金/生产数据库/外部发送授权扩张。
- 可自行判断：实际测试的分类、完整 skip 名称、日志的必要分卷、原版公开文件的调用链发现；结论必须有实际源码和命令证据，不新建工具/平台或更改验收语义。
- 退回主控：访问失败、路径/同文件碰撞、工具链/构建/测试失败、remote main 漂移、安全拒绝；这些不当然需要重写契约。仅真正契约语义冲突退 Principal，本文不得越权改 RFC/SPEC。
- T4/T5 使用 §5 观察点；主控另行派发真实角色任务，本卡不建任务。本文 Draft 的完成不代表实施批准或 M1 通过。

### 7.2 原版结果之后才做 C–H 差量重估（不实施）

T3 在 report.md 的 remaining_gaps 节逐项列“现成可保留能力/实际缺失/尚未测/原版证据/拟增量/工程估算区间及假设/数据或 Shadow 观察需求/授权依赖”。T4 验证证据，T5 检查是否夸大复用；本卡不填写虚构工时或观察日数。原版失败时只能列阻塞与暂定假设，明确“未完成原版基线，不作基于成功基线的重估”。

| 后续阶段 | 以 actual 原版结果核对的差量 | 估算方法及边界 |
|---|---|---|
| C 执行加固 | UNKNOWN 不以请求数量回填、买入净份额/实际费用、可成交挂单占用、持久化损失预算与跨重启恢复 | 用实际 Broker/Predict/现有状态路径和安全测试缺口分项估算实现+验证；无新 OMS/第二账本，本期不修 |
| D 回放/Lab 薄入口 | 既有事件记录、可注入时钟、同一 Rust 核心可回放性、Lab 编排缺口 | 分开估算核心注入/事件记录/研究薄入口，后续实例是 Lab 直接子目录；不预建空骨架，不以 BTC OHLC 算二元可执行 PnL |
| E 策略增量 | 复用 S0 btc-arb 与 S2 Predict OBI；核查 MIN_SECS_LEFT=600 与 is_quotable；最小动量/校准及 Binance OBI 对照 | 分开“已有单测通过”和“BTC5m 已适配”；后者未证明。研究参数/标签/交易语义另阶段修订同一契约集 |
| F 只读复盘 | 脱敏事实投影、参数偏差、经验检索 | 估算只读输入与报告差量，不赋予 Hermes 控制/签名/参数发布权 |
| G 故障/无订单观察 | 故障验证、信号对拍、获准无订单观察所需数据与条件 | 工程验证投入和数据积累/Shadow 观察日历时间分列；M1 不做采集或 Shadow，不凭经过固定天数放行 |
| H 小额执行准备 | 具体账户/资金/期限授权与外部执行系统验收缺口 | 工程准备、人工授权等待与获准执行观察分别列；200/100 USDT 不是充值/approve/订单许可，建议阈值不激活 |

工程时间指开发、审查、离线验证的实际工作量；数据/Shadow 观察时间指为后续证据积累经历的日历时间，两者不可相加冒充人日，也不能把等待期算成已获运行授权。授权等待另列。估算只用 actual SHA 的真实构建/测试结果、源码差量和未测风险，保留区间及依赖；后续按具体增量修订本契约集，不预先批量造文档/卡片或第二执行器。Chainlink 指定结算标签、平价 50–50、费用/净份额及 BTC OHLC 非可执行二元 PnL 的既有硬边界不变。

## 版本记录

| 版本 | 日期 | 变更 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-11-09 | 承接 RFC/SPEC V1.1，仅细化 M1 allowlist、fork/main 接入读回、安全原版 build/test、证据、定向撤销、Verify/Review 观察与 C–H 重估方法；未实施 | yquantprincipal |
| V1.1 | 2026-11-10 | 承接 RFC/SPEC V1.2；保留 M1 历史与终态、校正归档路径；新增 §8–§17 M2 单 Rust 核心、本地协议、真实代理研究、指标提取、载体及独立验收设计；仅文档，未实施 M2 | yquantprincipal |
| V1.2 | 2026-11-10 | 来源仍 RFC/SPEC V1.2；保留 V1.1/T2 与 run3555 历史，校准候选而非验收；修订路径、命令、退出和证据引用，新增 §18 最小 Rust 拆分、R1–R7 delta 与 recovery-01 离线续接契约；本卡只改 Design/恢复交接 | yquantprincipal |

## 8. M2 决策、基线与阶段范围

本增量落实 SPEC §9–§15，不覆盖 §1–§7 历史，不新建契约集。V1.1/T2 当时只写本文及 `data/tasks/active/2026-11-10-predict-btc5m-m2/design-handoff.md`，当时接口是 planned implementation。其 Design Gate 只针对当时规划，不证明随后候选实现符合契约。V1.2 已有候选及未实现/偏离项，见 §18 与主控 recovery-assessment；不得继续称“M2 源码尚未创建”，也不得把旧自报测试改写为独立验收。本卡只写本文及 recovery-design-handoff.md，独立文档 Gate 后由主控决定原 T3 续接，不建下游卡、不改原 T3 状态。

2026-11-10 V1.1/T2 历史只读复核：主仓 main，起始 tracked dirty 仅上游 RFC/SPEC；其 SHA256 分别为 `ec9eb57d6f8a9f4ae493b65ede437335d1b5207c8d9063eb33f9f14f9c39ee4d`、`a41d2565910aad25e5437463543c43274b4dd4ef2878479a02e8524b2f5707ac`。Toolkits 当时本地 main/HEAD/缓存 origin/main=`71c0e4ff9e299f9a4d81757fd6b15cf54da69b38`，QD HEAD=`6915e390d3886d441b943aa8ee26cd8d10c959ed`；当时两子模块 tracked/untracked 状态为空，未 fetch，不能称远端当前一致。恢复起点已 dirty：上游三文档和 T3 候选均保留；原版 BOT SHA/gitlink 不因 dirty 变成新版本，候选未提交，身份用原 SHA + 实际源码/diff hash 描述。

下文路径缩写仅作阅读：`BOT=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`；`LAB=skills/strategies/strategy-lab`；`INSTANCE=LAB/strategies/predict-btc5m-btc-arb`；`ARCHIVE=data/reports/2026-11-10-predict-btc5m-m2`；`REC=ARCHIVE/evidence/recovery-01`。均相对项目根，不是新增配置变量；REC 本卡不创建，后续独占创建/碰撞即停，见 §18.4。

### 8.1 后续精确文件清单

| 文件 | 动作与职责（仅后续获派阶段） |
|---|---|
| BOT/src/bot/arbitrage.rs | 已有候选可修：保留原版语义的共享核心/tick/parity；发现违约可在本路径修，不预认正确；原参数、source/Broker 防护/扫描节奏保留 |
| BOT/src/bot/arbitrage/replay.rs | 已有候选可修：收敛为公开 facade 与 JSONL I/O，保留 replay::run API；按 §18.2 拆分，不继续在 2829 行单文件叠功能 |
| BOT/src/bot/arbitrage/replay/types.rs | 新建 colocated 私有模块：现有配置/协议 DTO、summary/error/常量；公开项经 facade 原名重导出，不改协议 |
| BOT/src/bot/arbitrage/replay/driver.rs | 新建 colocated 私有模块：纯内存状态/验证/dispatch/核心调用，不含文件或网络 I/O |
| BOT/src/bot/arbitrage/replay/tests.rs | 新建 cfg(test) colocated 模块：原测试 helpers 与预热/身份/时间/冲突组 |
| BOT/src/bot/arbitrage/replay/tests/state.rs | 新建上述测试子模块：原确认/前缀/proxy/配置/标签组，复用父测试 helpers；无生产代码复制 |
| BOT/src/bin/btc_arb_replay.rs | 已有候选可修：clap 参数、显式本地文件/原子拒覆盖/退出码；仅此新 bin，不运行原 bot |
| INSTANCE/spec.md | 新建：沿现有 strategy-spec 模板填写本研究冻结规则，引用三层契约，不作为第二份工程 SPEC |
| INSTANCE/config.json | 已有候选，校验并保留 schema_version 及 §10.1 六个原数值参数；非交易运行配置，不以恢复调参 |
| INSTANCE/research.py | 已有 1182 行候选可修：R1–R4/R7 参数/原页/离线 Rust/聚合/载体；本次只用归档 OHLC/raw-pages/availability，零新 HTTP/token；行数治理见 §18.2 |
| INSTANCE/README.md | 新建：事实状态、能力限制、真实与离线命令；不称策略盈利或实盘可用 |
| INSTANCE/tests/test_research.py | 新建：实例 I/O、因果、预算、QD 注入、载体测试及实际 CLI 集成；unittest，≤1200 行 |
| INSTANCE/tests/offline_exec.py | 已有候选可修：仅测试用 Linux 无 socket 启动器，R5/§15.2/§18.3；不是旧 scratch 探针授权 |
| INSTANCE/tests/fixtures/replay-config.json、round-events.jsonl、proxy-events.jsonl | 已有三个 fixture 保留，必要修复须列具体差异；原页新反例在 test_research.py 内构造，不新增 fixture 库/伪真实行情 |
| LAB/scripts/equity_metrics.py | 已有候选可修：仅 §13 指标/零漂移，不预认通过；无 QD/网络/研究驱动 |
| LAB/scripts/grid_research.py | 已有候选可修：仅 margin_metrics wrapper/字段映射，其他函数不动 |
| LAB/tests/test_equity_metrics.py | 已有候选可补验证：helper/legacy oracle 全字段、异常、判定，不向既有大测试文件追加 |
| LAB/SKILL.md | 修改：仅补本 Rust 实例的“外部同核心本地研究、代理 exit3 可交分析、网格规范不适用”小段；不改通用模板/预算/其他实例语义 |
| LAB/strategies/INDEX.md | 修改：登记 id、路径、研究/验证真实状态，不虚称交易策略可用 |
| INSTANCE/reports/report.md、events.csv、proxy-samples.csv、comparison.csv、coverage.json | 后续唯一研究正文及载体；CSV/JSON 为 REC/research 同名文件精确副本，不各自计算；目标已有内容即停 |
| ARCHIVE/report.md；REC 下 §12/§18.4 所列文件 | 后续唯一归档索引和恢复新证据；旧 ARCHIVE/evidence（除新 REC 子树外）、superseded、Developer verify-reproduction 全部只读；研究正文只在实例 reports/report.md |
| data/tasks/active/2026-11-10-predict-btc5m-m2/implement-handoff.md、verify-handoff.md、review-handoff.md | 分阶段真实交接；不改上游 rfc-spec-handoff.md/design-handoff.md，不提前整体归档 |

只读/排除：BOT 的 Cargo.toml/Cargo.lock/LICENSE、src/lib.rs、src/bot/mod.rs、src/config.rs、src/models.rs、src/service/spot.rs、src/service/venue.rs、src/service/predict_fun.rs、runtime.rs、其他策略和原版配置；LAB/scripts/quantdinger.py、grid_training.py、所有其他网格实现/测试/实例、两个公共模板、LAB/README.md；QuantDinger 全子模块、.gitmodules/gitlink、Trading 两入口、RFC/SPEC、模板/各层 README、profile/Hermes 和另一个项目。predict_fun.rs 无本轮必要修改，明确不纳入。不存在“同时允许修改和禁止”的文件。

V1.1/T2 记录 grid_research.py=1604、test_grid_research.py=2024，属1201–2400受控区；前者仅指标函数职责，后者只运行不改，新增回归在 test_equity_metrics.py。quantdinger.py=2516，零增量，不以本设计替代独立拆分。原版 arbitrage.rs=279。恢复实测 replay.rs=2829、research.py=1182；前者按 §18.2 先拆再修，后者允许本次受控补齐，不能把旧“每文件≤1200目标”误报已达标或永久豁免。其余新文件目标≤1200，未知范围/额外文件先交主控。

## 9. 单一 Rust 核心与调用图

### 9.1 模块、签名和可见性

arbitrage.rs 增 `pub mod replay;`，原 private round_entry 算法及 RoundEntry 字段保持，只将共享状态抽成 private `DecisionCore`。子模块 replay 可访问父模块私有项；外部 bin 仅访问公开 replay API，不公开 round_entry、RoundTaker 或实时 run 的额外入口。既有 lib.rs→pub bot→pub arbitrage 已连通，Cargo 默认 autobins 未禁用，`src/bin/btc_arb_replay.rs` 自动发现为 `btc_arb_replay`，Rust library crate 名为 `polymarket_toolkits`；不必改清单或锁。

```rust
// planned interfaces, in arbitrage.rs
struct DecisionCore {
    cfg: BtcArbConfig,
    vols: HashMap<String, EwmaVol>,
    entered: HashSet<u64>,
}
impl DecisionCore {
    fn new(cfg: BtcArbConfig) -> Self;
    fn observe_spot(&mut self, symbol: &str, price: f64, at_secs: f64);
    fn valuation(&self, symbol: &str, spot: f64, strike: f64,
                 secs_left: f64) -> Option<Valuation>;
    fn entry(&self, market: &TradableMarket, book: &BookSnapshot,
             spot: f64, now: DateTime<Utc>) -> Option<RoundEntry>;
    fn confirm_fill(&mut self, market_id: u64, shares: f64) -> bool;
}
struct Valuation { samples: u32, sigma: f64, p_up: f64 }
// Pure real-time observation adapter; SpotQuote is the existing spot.rs type.
fn live_entry(core: &DecisionCore, market: &TradableMarket,
              book: &BookSnapshot, quote: SpotQuote,
              now: DateTime<Utc>, is_live: bool) -> Option<RoundEntry>;
// planned public, in replay.rs; DTO fields are frozen in §10
pub fn run<R: std::io::BufRead, W: std::io::Write>(
    config: ReplayConfig, mode: ReplayMode, from_ms: i64, to_ms: i64,
    input: R, output: W,
) -> Result<ReplaySummary, ReplayError>;
```

new/observe_spot 使用原 EwmaVol::new(300)/update；valuation 要求对应 vol.samples≥20，vol.vol(cfg.vol_floor)，调用原 digital_up；entry 对未 entered 且已预热的输入调用原 round_entry（不得另外复制 Up/Down 选择公式）。confirm_fill 仅对 shares>0 插入 entered，返回是否本次新插入；replay 已在 DTO 验证有限非负，实时 TakeResult 原正数守卫保留，不扩大 live 校验域。Valuation 是只读输出，不另行维护概率状态。proxy 遇缺口时仅 driver 丢弃该 symbol 的旧 EwmaVol，复用 observe_spot 重暖；此 reset 不用于实时。

```text
实时 tick:
  原 live_rounds/Known/15s 扫描、过滤保持
  原 Utc::now at_secs -> quote -> core.observe_spot（原观察时钟）
  Known.observe -> Broker halted 检查 -> 原 Utc::now now
  原输入缺失/20 return/source==Binance 防护 -> live_entry -> core.entry
  原 shares_for(order_usd,price) -> Broker.take（仅原实时路径）
  TakeResult::Filled(shares>0) -> core.confirm_fill；Blocked/0 不确认
本地 replay:
  显式事件 available_at_ms -> DTO 验证/缓存 -> core.observe_spot
  tick -> 本地 BTC/300秒/状态/因果守卫 -> core.entry
  显式本地 result -> core.confirm_fill；不调用 Broker.take
本地 proxy:
  真实闭合 close -> spot -> core.observe_spot -> value -> core.valuation
  无 TradableMarket/盘口/候选，不造 token；Python 只配对标签并聚合
```

RoundTaker保留cfg、SpotFeed、Known、rounds、last_scan，vols/entered移至core；cfg用同一BtcArbConfig克隆初始化且以后不动态改。live_entry是tick实际调用的纯适配seam，仅检查is_live且source非Binance则None，否则core.entry；原tick源防护及warn仍原位保留，seam重复同一拒绝条件便于无网络golden证伪，不引入新限制。不可将replay的BTCUSDT/300秒、paused、顺序或严格身份验证加进实时market筛选。实时三次时钟观测、source防护、halted、shares_for/取较大edge（相同edge原max_by顺序取后项）和费用公式不变。只声明同等输入下决策/预热/成功入场parity，不声明接收延迟、真实成交、UNKNOWN/净份额会计等价。spot.rs中旧Binance等同结算源的注释不是本研究官方结算依据，M2不改该文件。

## 10. 本地 CLI、事件和状态协议

### 10.1 CLI 与配置

新 bin 只支持：`btc_arb_replay --mode replay|proxy --config PATH --input PATH|- --output PATH|- --summary PATH --from-ms I64 --to-ms I64`，另有 --help/--version。7个带值选项均必填，无 live/network/venue/RPC/钱包或 AppConfig 参数。from<to且可转换chrono UTC；事件处理区间 `[from_ms,to_ms)`，每行包括预热必须在区间内。config/input/output/summary不得规范化为同路径；仅接受显式本地普通文件/stdio，不自动发现凭据或从cwd补配置。输入只读，输出父目录必须已存在，输出用create_new且不接受已有符号链接，不覆盖现存文件；`-` 只用于input/output，不用于config/summary。stdout仅JSONL（output为文件时stdout为空），诊断stderr固定错误码+行号，无env/认证内容。

config JSON 为严格对象，`schema_version` 字符串固定 `btc-arb-replay/1`，其余6项全为数值，字段：`min_edge: f64=0.03`、`order_usd: f64=5.0`、`min_secs_left: i64=30`、`vol_floor: f64=0.00005`、`half_life_secs: f64=300.0`、`min_vol_samples: u32=20`。拒绝未知/缺字段、bool替数、NaN/Inf；M2 只接受这组原版值，不提供优化开关。构造 BtcArbConfig { symbols: vec!["BTCUSDT"], ... }，从不调用 AppConfig::load。config.json 和 fixture/replay-config.json 同格式，固定参数由 spec 引用，不从自然语言解析。

Rust 退出码：0=本地软件回放完整且无未解释缺证据；2=JSON/schema/身份/时序/结果关联或内部数据契约失败；3=合法输入但预热/市场状态/盘口/标签/结果证据不足，含所有 proxy 分支；5=输出 I/O 或中途读取失败（保留 partial+completed=false）；64=CLI/配置值/本地路径/时间范围错误。Lab 将 Rust 0/3继续聚合，Rust2→外层2，Rust64→外层64，Rust5→外层2并记 rust.ioFailure；外层自身超时→5。输出 schema 不完整/非空输入却空输出→外层2，不以进程0掩盖。帮助/版本0不计 M2-A-002。正常拒绝入场（edge不足/临到期/closed等）不单独导致exit3；缺少必要数据才导致3。fixture没有结算评估需求时不因缺标签强制3，真实市场总体仍受 SPEC 证据上限约束。

### 10.2 JSONL envelope 与 payload

UTF-8，每行一个严格对象，无注释/空行；禁止未知字段、重复JSON对象键、非有限浮点。每个event共8字段：`schema_version`（同上）、`event_id`（非空string）、`event_at_ms`（UTC Unix i64毫秒或null）、`available_at_ms`（UTC Unix i64毫秒）、`seq`（非负u64）、`source`（非空string，来源URL/本地证据标识，无秘密）、`evidence_type`（fixture/real-proxy/real-market）、`payload`。event_at=null表示原源时刻UNKNOWN，不能拿available_at回填真实接收时刻；已知event_at≤available_at，所有毫秒时间须可转换chrono UTC。seq表达同刻顺序，不从类型优先级隐式推导。

payload 严格带 `type`，字段如下（所有下列字段都须出现，可空仅在明确写null处）：

| type / 可用模式 | payload 除 type 外字段、类型与单位 |
|---|---|
| market / replay | market_id:u64；symbol:string=BTCUSDT；starts_at_ms/ends_at_ms:i64且差300000；yes_token/no_token:string非空不同；yes_name="Up"/no_name="Down"；rules_source:string非空 |
| state / replay | market_id:u64；open/contested/paused:bool；start_price:f64正有限或null；fee_rate_bps:u32或null；三个状态布尔不可用缺省值，fee未知不伪造0，须缺证据而不发tick候选 |
| spot / 两模式 | symbol="BTCUSDT"；price:f64正有限；model_source:string（Binance/Coinbase/QuantDinger-proxy等实际声明，不映射成live权限） |
| book / replay | market_id:u64；yes_token:string；bids/asks:数组，每项严格 {price:f64∈[0,1],size:f64≥0}；bid严格递减/ask严格递增，不重排；有两侧时best_bid≤best_ask；深度保留原值，不插值 |
| tick / replay | market_id:u64；只对缓存中当时可用的同market state/book及最新同symbol spot求候选 |
| value / proxy | symbol="BTCUSDT"；strike:f64正有限；horizon_secs:u32=300；strike必须逐值等于同available_at的闭合spot.price，不可任意改成预测未来值 |
| result / replay | market_id:u64；candidate_event_id:string（先前tick.event_id）；status=blocked/filled/unknown；filled_shares:f64≥0或null；detail:string或null。filled必须有数量，blocked必须filled_shares=null且detail非空，unknown数量必须null |
| label / replay | market_id:u64；yes_token:string；status=settled/pending/disputed/tie；payout_yes:f64∈[0,1]或null；official_source/authority_report_ref:string；published_at_ms:i64或null。settled/tie须权威引用及发布时间，tie payout=0.5；pending/disputed不得强填payout |

state.fee_rate_bps为null时driver reason=fee_unknown，不把null写入TradableMarket 0值后计算。label只交事后评估收集器，绝不设置决策market.payout_yes/end_price，value也不接受label；label须引用已建market和对应token，settled/tie的published_at≥market.ends_at且≤available_at，pending/disputed的报告引用可为空字符串但需source。source真实时钟不足仅能标代理假设；proxy模式只允许spot/value且evidence_type=fixture或real-proxy，不凭空创建market/token/label/result；replay仅fixture/real-market，一条流证据等级不混合。真实已验证本地历史可通过replay运行，缺其他证据仍降级，不增加联网读取分支。

### 10.3 验证顺序和状态转换

顺序固定：CLI/路径/配置→逐行语法/重复键/版本/类型→同ID重复→时间排序→身份/数值→当时可用引用→状态更新/决策→写输出。相同event_id的规范化DTO相同忽略、不再输出、summary.duplicate_count+1；同ID不同载荷exit2。去重在顺序验证前，故原行的完全重复可忽略，不能用重复重排时间。其余 `(available_at_ms,seq)` 必须严格递增，拒绝乱序不排序修复；不同类型同毫秒由seq明确次序。symbol同available_at不同spot价格或market同available_at不同book载荷exit2；相同spot同刻同价不增samples（可输出spot_duplicate）；相同book只计重复快照。token所有权、market symbol/起止/Up-Down映射一经market建立不可变；重述相同market允许，不同身份exit2，state/book/result引用未建立market为exit2。

已知market但尚无state/开盘价/book/spot为合法缺证据；每次tick按优先级输出一个主reason：`state_unknown, not_started, ended, closed, contested, paused, start_price_unknown, fee_unknown, spot_unknown, warmup, book_unknown, already_entered, result_unknown, candidate_unconfirmed, near_expiry, edge_below_threshold`。entered/pending守卫在entry前，优先级仅用于诊断，不改变实际允许/拒绝集合；若具备估值输入，近到期/edge拒绝也可输出sigma/p_up。边界：starts≤now<ends，secs_left用原 num_seconds，29秒拒绝、30秒可计算；start_price/state在available_at才生效，不给早期tick回填。future label仅为事后收集，不影响任何前缀决策。

driver状态是每market的 `pending_candidate: Option<event_id>`、`unknown_result: bool` 加 core.entered；不是持久化订单账本。tick候选后pending立即置该id，但entered仍false。关联blocked或filled_shares=0清pending，可后续重试；filled_shares>0确认core.entered并清pending，此轮不再候选。unknown清pending、unknown_result=true，该轮停止新增入场；没有result直到EOF也是candidate_unconfirmed，不自动填成交。unknown之后除重复结果外再发新result为关联错误exit2（不实现对账恢复）。跨market结果、无候选结果、一个候选不同结果重复均exit2；完全重复结果由event_id去重，不能二次计数。不同ID重复同结果关联也exit2，避免重复确认。

回放spot按available_at_ms/1000.0更新，首价格仅设last；19 return不入场，20 return才可。同毫秒同价不增return，严格增加价格时间才调用update。proxy只接收300秒对齐的spot；中间gap清该symbol EWMA并重暖，不能跨缺口累计。warmup缺少、缺标签、未知结果会进入summary缺口，不是填0。输入/参数/二进制相同，输出（含排序）逐字节相同，无 Utc::now/Instant 进入决策行。

### 10.4 输出 JSONL 与 summary

每个唯一输入输出一行，字段顺序冻结为：`schema_version,event_id,event_at_ms,available_at_ms,seq,evidence_type,source,event_type,market_id,yes_token,no_token,symbol,samples,sigma,p_up,candidate,token,price,fair,edge,result_status,filled_shares,entered_before,entered_after,reason`。unknown/not-applicable数值或身份为JSON null；reason须解释本行缺少的决策信息，正常状态更新为`observed`、估值为`valued`、候选为`candidate`、成交确认为`filled_positive`、零为`filled_zero`、blocked为`blocked`、未知为`result_unknown`、标签为`label_evaluation_only`；冲突错误单独stderr，不伪造观测行。candidate为bool或null（非tick），entered在proxy为null。不在输出加入label payout到决策字段。

summary为严格JSON：`schema_version,mode,completed,event_count,output_count,duplicate_count,spot_duplicate_count,candidate_count,positive_fill_count,unconfirmed_count,unknown_result_count,missing_reasons,exit_code`。计数u64；event_count含重复输入行、output_count仅唯一event行；missing_reasons是实际tick/value缺证据reason及`proxy_only`、`official_labels_missing`的去重字典序数组（非决策预热spot不因尚未暖好增加缺口）；completed=false仅中途失败，exit3完整代理分析可completed=true。一个market正成交入场次数≤1；candidate_count不等于成交数。summary不输出输入/环境秘密或壁钟。实际运行版本/起止/命令/文件hash在外层commands.json，不混入确定性流。

公开ReplayConfig字段与§10.1 JSON完全相同；ReplayMode枚举Replay/Proxy序列化replay/proxy；ReplaySummary字段及类型即本节，serde DTO均derive且deny_unknown_fields。公开ReplayError={exit_code:u8,code:string,line:u64,partial:ReplaySummary}，line为1基输入行（I/O/CLI前检为0），code稳定集合 `json_invalid,schema_invalid,time_order,identity_invalid,value_invalid,result_invalid,io_failure,usage_invalid`。run失败由bin写partial summary（若summary本身写失败，只保留stderr与实际退出码，不伪造文件）；CLI解析前失败不要求生成输出。未知选项clap默认错误须映射64，不沿用clap默认2。

## 11. 首份真实研究：冻结窗口与因果路径

### 11.1 实例 CLI / 看结果前的默认值

research.py 必需 `--rust-bin PATH --evidence-dir PATH`，`--data-api` 仅agent（默认agent），可覆盖 `--start-utc/--split-utc/--end-utc/--as-of-utc/--frequency-seconds/--warmup-prices/--max-pages/--max-data-requests/--wall-seconds/--initial-capital`，默认如下。原始 M2 接口有默认在线 QD 入口，但本次恢复必须传 `--ohlc-file PATH`，零 token/HTTP，未传不允许本次执行；不删除既有在线接口或测试其 mock 契约。`--events-file PATH` 仅已有且来源核验过的本地真实market独立流，无此数据不新增/虚构。恢复可显式传 `--raw-pages-file PATH --availability-file PATH`（两项均为本地只读配套路径；省略则取 ohlc-file 同目录同名文件，缺失记录缺证据，不回退网络）。`--no-publish` 只写指定新 evidence-dir、不覆盖实例最新视图；独立Verify必须用此项，生成的待比对正文为该目录下 report-preview.md，非第二份手工正文。不存在live/优化/job/重采样选项。

| 参数 | 首轮冻结默认值 / 校验 |
|---|---|
| start_utc | 2026-11-09T06:00:00Z |
| split_utc | 2026-11-09T18:00:00Z |
| end_utc / as_of_utc | 均2026-11-10T06:00:00Z，as_of不是运行时now；start<split<end≤as_of |
| frequency_seconds / timeframe | 300 / 5m；正整数且整除86400，minimum代理路径只支持300；不接受别的频率后暗中重采样 |
| warmup_prices | 21个start前闭合close，非return数；20 return仍是核心阈值，不因此参数变化而改变 |
| channel/market/symbol | Agent/Crypto/BTCUSDT；venue/product/native_instrument均UNKNOWN（除非返回可验证证明） |
| max_pages / 请求/墙钟 | 2 / 50 / 1800秒，可下调不可上调；timeout每请求≤30秒且≤剩余预算 |
| initial_capital | 200.0 USDT，正有限，仅helper口径声明；本轮无账户权益时不生成曲线或收益 |

所有UTC参数必须带Z/UTC偏移并转换UTC，整300秒对齐。参数校验和输出路径create_new前检在resolve_agent_token/HTTP之前。配置只保存数值，不把时段、URL、token或路径写进config.json；时段在实例spec/CLI/coverage如实记录。覆盖参数必须在评估前写入coverage.parameters，首轮不得看结果后变窗；失败时保留原窗口缺口，不以实际返回范围改写声明窗口。再次研究另主题，不能覆盖本主题；也不建runs/manifest系统。

本轮以“预测边界t∈[start,end)”定义评估范围，bar的open和close另计：warmup close从start−21×300至start−300，故fetch_open_start=start−22×300=2026-11-09T04:10:00Z。保留用于预测的bar须 `fetch_open_start≤bar_open<end−300`，其close为bar_open+300≤as_of且<end；只在label_at=t+300<end且存在真实同频边界时构成标签对。全覆盖理论数（T2本地日期算术已计算，不是实际数据）：warmup21、评估边界288、所需bar309；IS有效配对144、OOS143，最后边界end−300因未来标签=end而不入指标但保留逐样本N/A行。IS规则t<split且label_at≤split；OOS t≥split且label_at<end；其他split跨界排除并计数。两区至少各1有效配对才有局部分析，理论数不能当观测数。

### 11.2 QD 半开区间适配（不重写分页；恢复仅离线/mock）

本节保留原接口的可测试契约，不是本次在线执行授权。恢复只将已有 raw-pages 作为输入重校，并在 unittest 的 request/agent_call mock 中证明分页合并前防冲突；任何真实agent_call/resolve_agent_token均不执行。

直接调 `fetch_klines(data_api="agent",market="Crypto",symbol="BTCUSDT",timeframe="5m",start="2026-11-09",end="2026-11-10",max_pages=2,request=checked_request,...)`。start为fetch_open_start的UTC日期；end为(end_utc−1毫秒)的UTC日期，不能把end所在整天误作本实例的半开终点。helper内部date end包含全天并置下一日午夜cursor，默认本例cursor=2026-11-11T00:00:00Z；原页可能带as_of之后数据，必须先校验原页再按精确时刻剔除。日期膨胀区间两页最多1000行，上述309所需行理论可覆盖，但实际供应方页形态/300根封顶/历史保留未知；两页没到fetch起点就coverage失败，不改窗、不第三页。

checked_request精确签名为`checked_request(operation: str, *, base_url: str, token: str|None, params: dict, timeout: float) -> Any`；只允许operation=`agent_klines`，market/symbol/timeframe固定且limit≤500；Budget.check→实例request_count<上限→request_count加1（失败也算）→`data,_headers=agent_call(...)`→只保留业务OHLC字段和明确来源字段→原页验证→返回原data给fetch_klines。headers永不保存/打印。在线入口在任何HTTP（含官方文档GET）前先resolve_agent_token并检查非空；仅环境QUANTDINGER_AGENT_TOKEN或现成helper单键fallback，不改/自行读取整份skills/.env，不触其他key；auth缺失exit4且0HTTP，401/403立即exit4且不换通道/凭据。base URL沿既有QUANTDINGER_BASE_URL，例http://127.0.0.1:15000，无/api后缀；8000不是本机QD，不探测/切换。不得调用compile/backtest/job/source/evolution。

原页逐行借现成parse_bar_time解析time/timestamp，原生seconds/ms表示由该helper处理，不另猜单位。额外验证所有O/H/L/C正有限、low≤min(open,close)≤max(open,close)≤high、volume有限非负（0有效）、UTC 300秒对齐；用规范UTC timestamp做原页seen键，OHLCV相同去重计数，不同即exit2 `ohlc.conflict`，包括同页和跨页冲突。在fetch_klines后页覆盖前做检查，原始重复次数不丢。排序/日期裁剪仍由fetch_klines，实例再做精确半开剪裁、as_of闭合、唯一性/间隔/预热覆盖，保存page序号、请求参数（无token）、原行数/重复/冲突/闭合剔除数；raw-pages仅OHLC及来源白名单，不写整HTTP响应。

expected_open集合按本例fetch_start到end−300每300秒枚举；observed逐时刻比较，精确集合差生成missing_ranges，coverage_complete=observed==expected，不新增覆盖百分比门槛。越界/未来/未闭合bar单列剔除计数，不当无效价格错漏掉。缺bar不插值/补0，不跨gap计算EWMA连续收益或标签；连续子段可描述，缺口影响的预测保留N/A，不能把子段描述写为完整窗口。UNKNOWN provenance不是bar质量错误，但足以阻止策略级通过。

### 11.3 可得性核查与预算

研究开始、看指标前，顺序读取：既有 `data/reports/2026-11-10-predict-btc5m-gaps/report.md`、其两份QD证据；`data/reports/2026-11-09-predict-btc5m-intake/evidence/sources.json`及其公开规则引用；BOT/src/service/predict_fun.rs公开路由源码，仅确认当前book/series不是历史archive。如传events-file，核其source/范围/当时state/book/官方标签完整性。每类“历史盘口深度、身份/开盘价/状态/费率、官方结算标签”在availability中各有一行：查询范围=本研究窗口，实际检查文件/URL、检查时刻、观测结果/可用范围/缺口。没有本地历史不能推断官方全局不存在，只记`not_verified`/`no_local_history_for_window`，不编造历史端点。

原 V1.1 在线契约曾允许最多3次已知官方文档GET：`https://docs.predict.fun/developers/chainlink-price-markets`、`https://dev.predict.fun/trading/fees`、`https://dev.predict.fun/trading/order-lifecycle`，禁自动redirect/交易client，不以200认定历史能力；这些仅为历史接口边界，本次不得执行任何新GET（含QD/官方文档）、resolve_agent_token 或 credentials fallback。恢复仅读取既有 availability/本地材料，保留原检查时间/来源/UNKNOWN；当前本地审阅时间另列，不伪称重新查询官方。§11.2 在线 request 注入逻辑只用归档原页/mock 测试修复，绝不以本段旧额度授权新取数。需要新数据即交主控，不重取刷结果。

总数据请求=官方文档GET+QD每页+任何实际失败/重试（默认重试0），共≤50，不是每源50。可复用现有Budget(wall_seconds)单调时钟及30秒收尾预留，业务deadline=started+wall−30；每次HTTP和Rust进程前check，now≥deadline不再启动；timeout=min(30,remaining)，子进程timeout≤remaining；最终输出也不得超1800秒。deadline后只能写已有结果/缺口，不继续fetch。超请求/墙钟exit5；统计请求实际数、elapsed_seconds和各类调用数0/真实值。QD job/source/backtest/evolution及签名、订单、后台、生产写调用恒0。无需平台、服务或部署变更。

### 11.4 Rust 代理与结果含义

Python将排序且验证通过的真实闭合bar映射spot，event_at=bar_close（这是推导的闭合边界，不是真实接收时刻），available_at=bar_close是假设“闭合立即可得”的proxy时钟；source指归档bar行，evidence_type=real-proxy，model_source=QuantDinger-proxy。每边界spot seq=0；t在评估域时加value seq=1，strike=当前close、horizon=300，event_id分别`spot:<t_ms>`/`value:<t_ms>`；不展开轮内tick。初始warmup仅spot；由Rust维护sigma/p，Python不计算生产概率/EWMA/买入token。

标签只在Rust输出之后的Python评估表由真实close(t+300)与strike比较生成1/0/0.5；标签类型固定`ohlc-direction-proxy`，future close永不进入value/spot的历史前缀。Rust子进程一律显式env={LANG:C.UTF-8,TZ:UTC}、close_fds=True，无shell，不继承QD或交易凭据；超时记录并终止该本地计算，不后台重试。独立按IS/OOS聚合有效对：Brier=mean((p−y)^2)，baseline同样标签、p固定0.5；tie单列。报告n、p均值/min/max、sigma min/max、边界持续期、缺标签/跨split/未预热计数；不强报硬分类准确率，不把ATM p≈0.5当alpha。无book时candidate/trade/PnL均N/A，不把0.5当买价。样本外EWMA延续已知历史，除真实gap重暖外不重置/拟合。

若显式传events-file，作为real-market独立流：driver输入范围取全部事件最小available_at至最大available_at+1毫秒（包含预热及晚发布标签），研究适配器要求所有tick落[start,end)，预热spot及先前当时可用的market/state/book可在start前，事后label/result可在end后但仅available_at≤as_of才参与本次事后评估。按tick预测时刻及权威label发布时间应用同一IS/OOS规则；标签来源/权威报告引用必须在availability有可核验证据，不仅凭非空字符串认官方。标签缺失/未验证或晚于评估可用边界则Brier为N/A，不用proxy标签顶替。无真实结果则candidate未确认且trade_count/PnL不得推断；本期不计算真实净PnL。此可选分支不取代默认真实OHLC最低研究，不给未知源时钟升级为执行等价。

压力项分列3条：`source_label_replacement`（QD未知来源与官方报告不一致）、`coarse_sampling`（遗漏轮内波动/入场边际）、`cost_latency`（费用净份额/价差/延迟未测）；无真实轮内数据时压力净收益/延迟敏感性值N/A+对应reason，不造情景收益。代理总体固定insufficient-evidence/exit3、optimization=skipped；真实净PnL/执行等价/实盘就绪恒未验证。IS/OOS没有有效真实样本或完全取数失败则整个M2未完成，不以fixture代替。

## 12. 本地持久化及报告载体

### 12.1 文件、行键、列序与单位

原 V1.1 文件名保持，当前写入位置冻结为 §18.4 的 REC 子树：REC/research 下 `parameters.json`（本次显式参数，非manifest）、`availability.json`、`raw-pages.json`、`ohlc.json`、`proxy-input.jsonl`、`proxy-output.jsonl`、`proxy-summary.json`、`events.csv`、`proxy-samples.csv`、`comparison.csv`、`coverage.json`、`commands.json`、`report-preview.md`；REC/cli 下 `fixture-output.jsonl`、`fixture-summary.json` 及负向检查日志；REC 根保存 `scope-diff.patch`、`core-diff.patch`、`numerical-reference.json`、`verify.md`、`review.md` 和总命令索引 `commands.json`（分阶段独占生成/完成后只读，不反复覆盖）。如有已核验本地market流，research 下另有 `market-input.jsonl`/`market-output.jsonl`/`market-summary.json`；无则只保留占位。独立重现子目录见 §18.4。各命令保留 `command-<序号>.log`，按所在阶段目录唯一编号，成功/失败均有真实 stdout/stderr/exit；历史未捕获记 NOT_CAPTURED，不造旧日志。parameters 在读取/评估输入及调用 Rust 前 exclusive 写入；commands 记录实际 cwd/argv/解释器/起止UTC/exit/hash，不收环境或 headers。本 Design 卡不创建上述证据。

原始ohlc.json为带 `schema_version="btc5m-research/1",source,market,symbol,timeframe,venue,product,bars` 的脱敏JSON；bars只保存time秒及O/H/L/C/V。source=QuantDinger Agent、venue/product为UNKNOWN，不用偏好配置填值。CSV UTF-8逗号分隔、LF换行、标准双引号转义；固定列序如下，数值保留`.17g`以回算，不舍入后再判定；NA写字面`N/A`，原因非空，实测0保留0。JSON缺数null+reason，不用非标准NaN。

| 载体 / 行键 | 冻结列序 |
|---|---|
| events.csv / (evidence_type,event_id) | 与§10.4 JSONL字段逐列同序，所有已运行分支合并前加证据分栏并验证event_id在该分栏唯一；bool小写true/false，null转N/A，reason保留 |
| proxy-samples.csv / (evidence_type,t_utc) | `evidence_type,t_utc,label_at_utc,partition,source,venue,product,spot,proxy_strike,sigma,p_up,proxy_label,label_type,brier,baseline_brier,status,reason` |
| comparison.csv / (evidence_type,partition,metric) | `evidence_type,partition,n,metric,value,unit,caliber,reason,research_verdict` |

proxy-samples包含每一个计划评估边界（缺bar同样保留），partition=IS/OOS/excluded，status=ok/insufficient-evidence；缺bar/预热/标签/跨split的reason分别为`bar_missing/warmup/label_missing/cross_split`，多因按此顺序用分号连接。不适用reason=`not_applicable`。完整样本的reason=none（不是空白），label_at永远显示计划t+300，即使标签不存在；标签不是官方。label_at≥end 统一 label_missing，不误计 cross_split；缺 bar 无法观察到的 p/sigma/label 不造值；当前bar存在却缺对应Rust value输出属于契约失败exit2，不能伪装正常warmup。详见 §18.3/R3。

comparison预定义3证据栏 fixture/real-proxy/real-market × IS/OOS两区；fixture纯软件无IS/OOS意义仍保留N/A+not_applicable，不冒充真实分区。每区metric顺序为 `sample_count,tie_count,p_up_mean,p_up_min,p_up_max,sigma_min,sigma_max,brier,baseline_brier,candidate_count,trade_count,net_pnl,interval_return_pct,annualized_return_pct,sharpe,max_drawdown_pct,calmar,turnover_pct,information_ratio`。未运行real-market保留占位，真实代理收益/候选/成交指标N/A，不写0；候选/成交只在有相应真实事件证据的real-market分栏计数，非PnL等价。unit依次为count、count、probability（3项）、second^-0.5（2项）、score（2项）、count（2项）、USDT、percent（2项）、ratio、percent、ratio、percent、ratio；caliber逐行写口径，所有N/A写具体缺口。research_verdict=insufficient-evidence（本轮降级），fixture局部行为在正文独立写可用，不混算n。

coverage.json顶层固定为`schema_version,parameters,source,venue,product,fetch_start_utc,expected_bars,raw_count,unique_count,closed_count,excluded_future_count,excluded_unclosed_count,excluded_range_count,duplicate_count,conflict_count,missing_ranges,warmup_count,evaluation_boundary_count,is_count,oos_count,tie_count,cross_split_count,coverage_complete,request_count,elapsed_seconds,research_verdict,reasons`，schema_version=btc5m-research/1。unknown字段显式UNKNOWN；expected/observed各数独立定义，raw_count跨页含重复、unique在去重后裁剪前、closed在精确窗口后；missing_ranges为[{start_utc,end_utc}]半开缺口。剔除计数互斥按future(bar_open>as_of)→unclosed(close>as_of)→range(精确窗口外)顺序归类；bar_open=as_of归未闭合。warmup_count是实际start前边界数、evaluation_boundary_count是实际[start,end)边界数，is_count/oos_count只计有效已配对标签；理论计划行总数仍可从parameters重建。计数不能用理论值替观测值。

### 12.2 同源与唯一正文

先构造proxy样本行、comparison行及coverage对象，再将同一内存行集写CSV和渲染正文，不允许手算第二份表。正文遵循现有research-report模板所有核心章节，另列fixture/real-proxy/real-market证据、可得性、预算、压力和原版参数。净PnL/执行等价/实盘就绪明确未验证；杠杆/保证金回执、sourceId/runId/jobId/UI、网格表A/B、四fold/G-E/35%均不适用，原因“不提交QD回测/无真实账户权益”，不伪造0或ID。

唯一正文INSTANCE/reports/report.md；ARCHIVE/report.md仅存相对正文路径、修复后正文SHA256、generated_at_utc及 REC 证据链接，明确旧 run3555 结果未验收，不把旧 evidence 或 Developer verify-reproduction 当当前有效基线。实例CSV/coverage是 REC/research 载体精确字节副本；hash变更使当前归档验证失效。初次发布前所有实例/索引目标已有内容即停，不覆盖；Verify以--no-publish写 REC/independent-verify/research，再逐值比较自动 report-preview 与唯一正文，不手写第二正文。以后新研究另主题，不建runs/manifest、TTL、数据库/schema或迁移。data仍Git忽略，本地保存不等于远程备份。

## 13. 公共权益指标：一次计算与零漂移

### 13.1 helper与wrapper签名

LAB/scripts/equity_metrics.py仅stdlib，冻结：

```python
def equity_metrics(
    rows: list[tuple[datetime.datetime, float]], *,
    initial_capital: float, frequency_seconds: int, limitation: str,
) -> dict[str, object]: ...
```

rows由调用者解析为UTC datetime与有限equity，helper不处理损益字段、不接HTTP；initial_capital由调用者保证正有限。helper保持原运算顺序/浮点运算，frequency内部沿旧int转换和整除，不加“必须整除86400”的新legacy门禁。M2入口另行拒绝bool、非正/非整数/不能整除86400频率及非法资本，然后传入helper；legacy wrapper保留旧接受域，包括可int转换的值、frequency>86400时K=0、0导致原ZeroDivisionError等行为，不先运行M2 validator。

旧`margin_metrics(bar_close_rows,frequency_seconds=DEFAULT_FREQUENCY_SECONDS)`签名/default不变：逐行原`_time/_finite`解析，有equity则优先，否则`INITIAL_MARGIN + realized_net_pnl + unrealized_pnl`，每个字段同原调用次序和错误文案；把[(UTC时间,计算权益)]传helper，initial_capital=原INITIAL_MARGIN(1000)，limitation=原COMPRESSED_EQUITY_LIMITATION。helper返回`return_pct`，wrapper仅将它改名为`margin_return_pct`，不留新key；其他key逐字保留。grid模块不再保留第二份计算公式，新研究不import网格/强平逻辑。

helper输出键：`status,reason,net_pnl,return_pct,peak_equity,max_drawdown_pct,raw_max_drawdown_pct,peak_time,trough_time,sharpe,return_count,bar_count,risk_free,ddof,periods_per_year,limitation`，除return_pct改名外映射全为identity。NA="N/A"；无reason仍为None。peak以initial_capital开始；收益/PnL/MDD、peak_time更新只用原严格大于，首行不加capital→首行Sharpe收益。returns仅相邻权益且left>0；valid=非空、时间无gap/duplicate/non-native、所有equity>0。Sharpe至少2收益且pstdev>0，rf=0/ddof=0，K=365*(86400//frequency)。原reason依次追加 `empty equity sample`、`missing/duplicate/non-native bar`、`nonpositive equity`、`insufficient return samples`、`zero volatility`，用`; `连接，不能改中文或排序。

保留反直觉的原诊断：net_pnl有末值即返回（即使非正/缺间隔）；无样本为NA；return_pct仅valid时数值；max_drawdown有equities且无missing就保留（非正可>100%）；raw_MDD有equities即原值，无样本None；peak_time可None；status可能ok而sharpe为N/A（样本不足/零波动），不得“纠正”。K即使空样本也按旧逻辑计算。不扩展成年化/Calmar/换手/IR第二套实现；本轮这些行始终N/A带无真实净值/成本/基准原因。

如果将来从Summary取账户权益，唯一转换是initial_capital+Summary.equity()；后者realized−fees+unrealized已是净损益，不再减open_cost/fees，不拿本期helper测试样本生成研究曲线。§14的固定资本向量只测试helper，不是交易回测。

### 13.2 零漂移路径

原版oracle不得从已改候选冒充提取前代码：BOT内`git show HEAD:src/bot/arbitrage.rs`对应原版golden，主仓`git show HEAD:skills/strategies/strategy-lab/scripts/grid_research.py`对应提取前margin_metrics。恢复先核对既有golden/oracle来源blob/hash，保留可用候选，不无故重建。网格旧函数体仅在test_equity_metrics.py中作为隔离legacy oracle，保留原_time/_finite；同输入比legacy oracle与wrapper全dict（含None/NA/string/诊断/计数），异常比类型+message，原cell_qualification比同风险上下文判定。新helper/新core自身调用两次不能作“旧基准”。

测试矩阵：既有MarginMetricsTests/SharpeTests输入、空列表、单行、2/3/4行、flat、正/0/负equity、缺time、无效/非UTC时间、重/缺/非原生间隔、NaN/±Inf/bool、显式equity优先、缺equity回填、频率300/900/3600/1000/86401及旧可转换"900"/900.9/True/0/-1。最后几项按提取前实际结果/异常作oracle，不根据Design猜异常。全key/value必须精确相等drift=0/N（浮点也尽量保留逐位原操作顺序）；独立数学对拍的容差不能掩盖wrapper漂移。既有网格全部安全单测仍运行，test_grid_research.py不改。

## 14. 独立数值基准与边界向量

### 14.1 V1.1/T2 历史实际算过的纯本地基准

下表是原T2非实现者的历史计算，不是Rust实际输出、真实研究或独立Verify PASS；本次Recovery未运行任何Python/数值命令。原T2于2026-11-10在项目`.venv/bin/python`以前台纯本地输入计算：路径A用float/math的原A&S Horner公式及statistics；路径B用Decimal 60位、A&S系数幂次求和（非同一Horner循环）、Decimal ln/exp/sqrt与有理收益矩；不import生产策略/网络/秘密。精确CDF另用math.erf只作模型近似误差说明，不作实现对拍真值。原命令与输出摘要见V1.1 design-handoff，保留不改。

| 向量 / 输入 | 路径A | 路径B（显示部分有效位） |
|---|---|---|
| digital_up(100,100,0.0001,300) | 0.4996545031716596 | 0.499654503171659620283306258711 |
| digital_up(100.1,100,0.0001,300) | 0.7177586088352752 | 0.717758608835296668596449627533 |
| digital_up(99.9,100,0.0001,300) | 0.2814615116845105 | 0.281461511684488835587519353698 |
| digital_up(100.1,100,0.0005,300) | 0.54422448173688853 | 0.544224481736893816922869260347 |
| 21价格p_i=100*exp(i*0.001)，i=0..20，每300秒，half-life300，floor0.00005；return20后sigma | 0.000057735026918961352 | 0.00005773502691896257645091487805（常量log-return闭式） |
| 非恒定EWMA，价格100/100.1/99.9/100.2，时间秒0/60/180/300，half-life300，floor0.00005；3个return后sigma（直接测EwmaVol，不宣称已预热） | 0.00018390868866670639 | 0.00018390868866671180517822426822（展开权重和） |
| capital1000，4个连续权益1100/1050/1150/1200，frequency900，Sharpe（不含资本→首行） | 100.15527470614849 | 100.155274706148407398311830581 |
| 上例frequency3600，Sharpe | 50.077637353074245 | 50.077637353074203699155915291 |
| 同权益net_pnl / interval_return_pct / MDD | 200 / 19.999999999999996 / 4.545454545454546 | 200 / 20 / 50÷11（百分比数值） |
| 独立聚合fixture (p,y)=(0.4,1),(0.6,0),(0.5,0.5)，Brier / baseline | 0.24 / 0.16666666666666666 | 0.24 / 1÷6 |

前三个A&S值对应精确CDF分别0.49965450589371541、0.71775856492562673、0.28146155655618821；差异是原近似模型误差，不允许改spot.rs换erf以“修复”它。production研究不能使用上表Python参考概率实现；仅隔离验收可使用。常量log-return EWMA的第二路径是闭式variance=(0.001²)/300而非重跑同递推，float构造价格的微小误差已在差异中保留。

### 14.2 容差与责任

独立数学对拍使用 `abs(actual−expected) <= max(abs_tol,1e-9*abs(expected))`，abs_tol按字段冻结：sigma=1e-15、概率/Brier/其他无量纲=1e-12、金额USDT/百分比/Sharpe=1e-9。零附近不使用仅相对容差。CSV/正文同源数值rel=1e-12、abs=1e-15，枚举/NA/reason/计数/行键逐字相等drift=0/N；wrapper兼容全dict精确相等，不借数值容差放宽。确定性JSONL同输入两次逐字节相等。阈值判定按raw值，容差只比数值，不允许把edge<阈值当已达阈值。

主控在Verify派发前（非Developer、非正式验收者）将本节基准及从真实归档输入抽取的首/末/非平价/平价/缺口边界样本，用双路径计算后落`REC/numerical-reference.json`；字段为version、inputs、formula、path_a、path_b、crosscheck_abs、tolerance、source_hash、generator_role/time。本T2表可作为固定数学向量基准，真实样本数值不能预填；真实档案没有的平价/缺口仅用明确 fixture 分栏，不能冒称真实发生。未形成具体真实样本双路径基准不得派Verify；Developer不得代填，Tester不得覆盖。此为既有验收要求，不增正式阶段。若真值与实现不同，保留预期/实际判断哪方错，不默认实现正确。

### 14.3 待实现测试向量（不冒充已运行）

Rust arbitrage模块内`shared_core_matches_original_tick_inputs`：固定UTC时间和原配置，原版S0的Up/Down/fees/near-expiry/no-start案例原样保留；以本地quote/books喂tick实际使用的live_entry，对比修改前原适配条件+保留原round_entry的golden，逐项比较token/price/fair/edge和确认状态；另比较replay driver同输入结果。测试显式Binance-live、Coinbase-live拒绝、Coinbase-paper仍允许。原参数/BTCUSDT/vol_floor/half-life/minsample断言全字段；其他策略安全默认集合仍运行。不创建SpotFeed网络实例/Ctx，不为了测试运行真实tick。核对tick确实调live_entry/core且原source/halted/scan/三次时钟位置未移；同一新core调用两次不算旧版golden。

replay 模块内测试按 §18.2 迁入 tests.rs/tests/state.rs，保留以下验收组的名称/断言/输入（一个组可有多个子case，不冻结虚构总测试数）：

- `warmup_19_20_returns`：首价格samples0、20价格19return拒绝、21价格20return可候选；同刻重复不增sample。
- `identity_and_available_state`：ETH/299/301秒、相同token/跨market token、未来start_price不回填、缺/关闭/争议/暂停状态、未来state、未开始/starts边界/29秒/30秒/ends边界。
- `order_duplicates_and_conflicts`：乱序、同刻seq冲突、同ID同payload忽略、同ID改payload、同刻冲突spot/book、排序错误/NaN/Inf/负depth/越界价格。
- `confirmation_state_machine`：candidate未确认停止该轮→blocked/filled0可重试→filled正数仅一次entered；unknown永远不使用请求份额；错误关联/重复结果/跨market结果拒绝。
- `prefix_causality_and_determinism`：截取每个prefix与完整流对应输出前缀相等；追加未来label/未来state不能改变过去行；两次相同输入字节相等。
- `proxy_has_no_market_or_execution`：spot/value估值、strike必须等当前close、300秒期限、gap清vol重暖；不造book/token，结果只有代理估值。

INSTANCE/tests/test_research.py覆盖：原页同/跨页重复冲突、date end含全天/UTC午夜/精确end−300裁剪、as_of恰闭合与未闭合、缺bar/零volume/非法OHLC、缺预热/跨split/IS标签恰split/OOS标签恰end排除、未来close不进Rust历史前缀、UNKNOWN来源、请求50前后/now==deadline不发新HTTP、401/403/缺token0请求、Rust exit映射、全载体列序/NA原因/唯一正文hash、`.17g`回算、fixture不混n。Brier向量仅测聚合，不进入真实样本计数。

## 15. 验证执行机制与需求映射

### 15.1 后续可复现命令（本卡未执行）

以下只供独立文档 Gate 后主控续接原 T3/后续独立 Tester，检查实际源码无额外副作用后直接terminal前台执行；本卡不执行。每条单独保存真实退出码，不用pipe掩盖。cwd项目根；子模块命令使用terminal.workdir=BOT绝对路径。只用已安装工具链、已缓存锁定依赖，增加 --offline 以阻止恢复构建取网；缺缓存即停，不安装/升级/改锁。新bin不运行原bot。

```text
# BOT cwd，Implement/Tester各自独立运行，先读源码/清单分类
cargo build --locked --offline --bin btc_arb_replay
cargo test --locked --offline -- --list
cargo test --locked --offline

# 项目根，原网格测试不修改；实际测试集合按清单分类后执行
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests -p 'test_*.py'
```

只有已忽略的危险测试继续ignored，不能启用--ignored；遇新默认联网/账户测试须完整名定向skip并记源码理由，其他安全默认集合必须非空且全跑；M1 164/0/3不能替代M2日志。Cargo `--offline`至多用于依赖缓存，不是无网证据。build失败不继续研究/自称新CLI可执行。两个新测试目录使用现有unittest风格，不在项目根tests放单模块测试。加载helper用邻居既有importlib.util文件路径模式，grid wrapper内懒加载`Path(__file__).with_name("equity_metrics.py")`并调用，无全局sys.path更改/包化；既有test_grid_research.py的spec_from_file_location加载方式必须仍可用。

本地fixture实际前台执行（测试启动器内清环境/无socket，输出文件先不存在）：

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/offline_exec.py --rust-bin skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/target/debug/btc_arb_replay --mode replay --config skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/fixtures/replay-config.json --input skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/fixtures/round-events.jsonl --output data/reports/2026-11-10-predict-btc5m-m2/evidence/recovery-01/cli/fixture-output.jsonl --summary data/reports/2026-11-10-predict-btc5m-m2/evidence/recovery-01/cli/fixture-summary.json --from-ms 1794197400000 --to-ms 1794290400000

# Developer：归档真实OHLC离线重现，研究外层预期3；不设URL，不读token，不新取数
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/research.py --ohlc-file data/reports/2026-11-10-predict-btc5m-m2/evidence/ohlc.json --raw-pages-file data/reports/2026-11-10-predict-btc5m-m2/evidence/raw-pages.json --availability-file data/reports/2026-11-10-predict-btc5m-m2/evidence/availability.json --rust-bin skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/target/debug/btc_arb_replay --start-utc 2026-11-09T06:00:00Z --split-utc 2026-11-09T18:00:00Z --end-utc 2026-11-10T06:00:00Z --as-of-utc 2026-11-10T06:00:00Z --frequency-seconds 300 --warmup-prices 21 --max-pages 2 --max-data-requests 50 --wall-seconds 1800 --initial-capital 200 --evidence-dir data/reports/2026-11-10-predict-btc5m-m2/evidence/recovery-01/research

# Tester：独立阶段才运行，全新子目录；其余参数必须与修复后parameters逐项匹配
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/research.py --ohlc-file data/reports/2026-11-10-predict-btc5m-m2/evidence/ohlc.json --raw-pages-file data/reports/2026-11-10-predict-btc5m-m2/evidence/raw-pages.json --availability-file data/reports/2026-11-10-predict-btc5m-m2/evidence/availability.json --rust-bin skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/target/debug/btc_arb_replay --evidence-dir data/reports/2026-11-10-predict-btc5m-m2/evidence/recovery-01/independent-verify/research --no-publish
```

最后一命令其余参数须与 REC/research/parameters.json 逐项匹配（本例为默认值，覆盖过则显式传同值），ohlc-file 禁所有网络/认证/官方文档GET。Rust实际代理命令记录于研究 commands.json，固定 --mode proxy、同config、--input proxy-input.jsonl、--from-ms=fetch起点、--to-ms=end；只执行显式rust-bin，不自动cargo安装/构建。REC 先由 Developer 独占认领，cli/research/independent-verify 各阶段新建，目标存在一律停止，不删除/重跑换路径刷成功。fixture 输出在 cli，研究仅引用其hash、不代跑/复制假证据。两个负向命令复用上述 offline_exec 的参数形状，各用 cli 下独立 negative-live/negative-rpc 文件名，分别追加 `--extra=--live`、`--extra=--rpc-url`，实际外层均应64且不生成业务输出；独立Tester改用 independent-verify/cli 下同名全新目标。不使用 Python -c、heredoc、新临时runner或旧 scratch/check_filter.py 代替。

### 15.2 无凭据与禁止socket验证

offline_exec.py仅测试启动器：stdlib ctypes调用现有libc `prctl(PR_SET_NO_NEW_PRIVS)`及SECCOMP_MODE_FILTER，为子进程安装seccomp BPF，Linux x86_64核对arch后拒绝socket/socketpair/connect/sendto/sendmsg/sendmmsg（EPERM），其他必要本地文件/计算syscall允许。只约束当前子进程，不改宿主网络/服务/安全配置，不需root或新包；不支持/安装失败明确测试FAIL/NOT_RUN，不能默认为skip通过或回退成假无网。先有对照子进程故意创建AF_INET socket，必须EPERM；再同样filter实际exec新Rust CLI。若保留fork/exec，不能仅声称close_fds：先将0/1/2重定向到本地DEVNULL/日志，再关闭全部≥3的继承FD（仅暂留安装失败诊断pipe，该pipe exec前关闭且CLOEXEC），负对照也同样净化；exec后的子进程不留父进程socket/日志外FD。§18.3/R5冻结继承FD反例，不用真实业务连接作探针。

Rust子进程env为显式白名单（仅LANG=C.UTF-8、TZ=UTC，必要的已确认动态库路径才可加且记录键名）；包括研究 run_rust 在内都不继承PATH、HOME、QUANTDINGER_*、交易key/代理变量。cwd用当前任务TMPDIR下新空目录；不复用旧scratch探针或对历史目录做清理。所有路径在切cwd前绝对化；两个 Python 入口的项目根均按祖先中的根AGENTS及本脚本完整项目相对路径匹配定位唯一根，固定本任务工作区 `/home/pascal/workspace/yquant-investment` 作核验，不依赖错误parents[4]/cwd或环境HOME。不唯一/不匹配exit64。构建后的bin独立执行，不调cargo或shell。启动器先做socket负对照并exec CLI，实际非空JSONL/summary预期0或3；--live及--rpc-url负向参数外层均64。该机制与静态调用图共同证明路径安全，不通过假密钥/真实连接验证；cargo --offline不是无socket证明。

静态同步核对新bin/replay从入口到调用图无AppConfig::load/Ctx::connect/SpotFeed::new/reqwest/venue/RPC/签名器/账户文件读取；链接整个lib包含这些符号不等于调用可达。Rust core使用spot模块里的纯EwmaVol/digital_up，不实例化SpotFeed。credential文件不可达以显式配置/文件输入审查+清HOME/空cwd负向执行作证，不能把env缺值本身说成完整文件访问沙箱。未知有效Cargo runner/wrapper或无法落实seccomp时停止相关验证并报主控，不安装工具、不修改审批；M2-A-002未证实不能PASS。

### 15.3 M2-A-001..010 到测试/证据/负责人

| 编号 | 本设计落实 | 后续实际验证与证据 | 主责 |
|---|---|---|---|
| M2-A-001 | §9单核心/实时guard原位，§14.3 golden | 原版S0用例+shared_core_matches_original_tick_inputs；core-diff.patch/源码行号；其他策略安全默认测试新日志；原配置全字段 | Implement自测；Tester复跑；Reviewer核调用图 |
| M2-A-002 | §10 CLI/§15.2 | offline_exec实际前台非空流、seccomp负对照、清env、--live/--rpc-url64；fixture-output/summary及command日志；build成功不代替实际运行 | Implement/Tester分别执行 |
| M2-A-003 | §10.2–10.4/§14.3 | 六组Rust边界向量；prefix每段比对、确认状态与每market正入场≤1；乱序/身份/冲突exit2 | Implement/Tester |
| M2-A-004 | §11.3/§18.3 R4 | 三类实际本地文件/hash/研究范围/可用范围/缺口；原文档GET状态只能标历史声明，保留时间/NOT_CAPTURED，不新HTTP、不伪造核查 | Implement本地核查；Tester只读核证 |
| M2-A-005 | §11.1–11.2 | 原页request注入测试、原始raw-pages/ohlc、coverage集合差/闭合/预热、UNKNOWN披露；真实数据分析非fixture | Implement研究；Tester离线重现 |
| M2-A-006 | §11.4/§12 | IS/OOS各≥1有效真实样本；proxy-samples逐样本Brier/0.5基准回算、split/end边界；真实代理exit3，收益N/A | Implement研究；非实现者基准；Tester独立比对 |
| M2-A-007 | §13–§14 | test_equity_metrics全dict/异常oracle、既有网格tests；capital+Summary损益向量，不二次扣费；wrapper字段/NA/reason/判定零漂移 | Implement；Tester独立数学/兼容检查 |
| M2-A-008 | §12 | CSV精确列序/逐行同源、N/A原因/全部证据栏与指标、正文模板核心章节、归档索引hash和原始输入；no-publish不覆盖 | Tester；Reviewer文档/报告核对 |
| M2-A-009 | §8/§11.3/§16 | commands请求/墙钟实数、零QD job/交易/签名/后台/生产写；主仓及BOT diff/锁/LICENSE/hash/其他子模块状态；未提交推送 | 各阶段；Reviewer范围审查 |
| M2-A-010 | §14.2/§15/§17 | 非实现者双路径reference在Verify前发布；Tester独立执行/只读数值同源验收，Reviewer独立三层/源码/报告审查，未闭合finding=0后主控Closeout | 主控编排；Tester与Reviewer不同角色 |

工程PASS是SPEC十条全部满足，可允许研究insufficient-evidence/exit3；不是实际净PnL/盈利/执行等价/实盘通过。以上是验收要求，当前候选部分已有但 R1–R7 未闭合，不能因旧自报或文档修订填写工程PASS。

## 16. 实施顺序、停止及定向撤销

恢复顺序：本卡最小Design→独立文档Gate（t_fda06da5）→主控明确续接原T3→Developer记录候选diff/hash/归属及原golden/oracle→按 §18.2 先拆再补R1–R7→新bin构建/实际fixture无socket→公共helper/wrapper/安全网格回归→实例测试/参数前冻结/本地可得性核查→归档OHLC零新HTTP重现/唯一载体→非实现者真实双路径基准→独立Tester→独立Reviewer→主控Closeout。复用已存在候选，不重做市场/API/fork调研，不默认已有Rust/研究脚本正确。无真实有效IS/OOS不得关闭M2。

| 失败 | 停止/退出与保全 | 后续归属 |
|---|---|---|
| 契约互相矛盾/身份映射未定 | 实施前停，文件:行+预期/实际；不靠Design覆盖RFC/SPEC | Principal/主控确认，不由Developer选择 |
| 未识别的同文件他人dirty、输出目标已存在 | 已知上游/T3候选保留并记录归属，不以dirty本身拒绝续接；新增碰撞写入前停，不覆盖/清理；保存路径/hash | 主控协调；同文件碰撞留hotspot评论 |
| 审批拒绝/超时 | 立即停该动作，记工具真实结果NOT_RUN，不换解释器/命令形状绕过 | 主控授权/能力问题 |
| Rust build/test/parity/无网执行失败 | 不研究、不声称CLI已交付，保留命令/partial输出/真实失败 | Developer当前allowlist内定位；语义/范围变更交主控 |
| mock认证边界失败或恢复尝试读取凭据/HTTP | 原接口auth退出4保持仅mock回归；恢复不得触发真实认证/取网，发生即停并留真实记录 | 主控处理，不换token/通道/执行器 |
| OHLC冲突/非法输入/Rust契约失败 | exit2，不静默后页覆盖/插值；保存脱敏错误和已取得原页 | Developer实现问题或主控数据来源处理 |
| 缺历史盘口/官方标签/来源证明、部分缺bar | 合法代理分析exit3，保留缺口与逐样本N/A，不伪装完整覆盖或收益 | 后续研究风险；有真实有效两区则可继续工程验收 |
| 无有效真实两区或超预算 | 无真实研究则M2未完成；预算exit5即停，保留诊断，不换窗/加页求通过 | 主控裁定续接范围，不冒称整体完成 |
| 独立基准/实现/载体不一致 | 保留预期/实际；Tester不改实现/断言/基准，Reviewer不能APPROVE with open findings | 主控分派最小修正，不自动加流程/范围 |

恢复不执行删除/搬移/回滚旧候选或证据，失败原地保留。后续若主控明确要求撤销本人源码hunk，只可精确反向patch并先存hash/diff，不能整文件restore/reset；不自动隔离搬迁新文件。归属不明留现场。无rm/mv/fetch/pull/checkout/reset/stash/clean、gitlink同步、commit/push；原锁/依赖/LICENSE/实时配置不变。旧run拒绝的删除或探针不得重试；任何新拒绝立即停，不换执行器或审批配置。无需平台、服务、部署或Activation，不新增资金/收益/覆盖率门槛。

## 17. 本阶段交接边界

原T2交付为Design V1.1及design-handoff，当时未创建M2源码；其纯本地数学计算不替代新CLI/真实研究/独立Verify。当前Recovery交付为V1.2及recovery-design-handoff，候选与旧证据原样保留，本卡只做文档/静态范围检查。后续唯一许可来自独立文档Gate与主控明确续接，不授予交易/账户/签名/运行控制权。200/100 USDT背景、原版5 USDT离线参数不能变成实盘资金配置。

主控核验：RFC/SPEC仍V1.2且来源hash未变，Design来源/版本记录一致；精确allowlist无自相矛盾；SPEC十条及R1–R7有 §15.3/§18 可执行证据路径；Recovery实际只改两文档，path-filtered diff --check、范围status含untracked、候选hash不变。文档验收满足则本卡done以释放既有独立Gate子卡，不宣称Gate/实现通过；契约冲突才block具体file:line。本卡不建子卡、不unblock原T3。M2独立Verify/Review及M3 UNKNOWN/费用净份额/持久化恢复仍未运行；历史盘口、QD来源、粗采样与短样本局限保留。

## 18. M2 Recovery：最小拆分与剩余 delta（V1.2）

### 18.1 授权、候选与历史证据

来源为 [主控 recovery-assessment.md](../../../data/reports/2026-11-10-predict-btc5m-m2/recovery-assessment.md) §22–§46 的 R1–R7/流程偏离，以及 t_bf5ea047 新授权。该报告末尾 AWAITING_USER_AUTHORIZATION 是当时快照；Pascal 于 2026-11-10 知悉缺口和拒绝后继续执行的偏离后明确“同意”最小恢复。新授权不追认旧run合规，不授权重试rm -rf、旧scratch/check_filter.py、审批/profile修改或交易。

原T3 run3555仅一个run，150/150预算耗尽而blocked；主控已确认无活跃旧worker。已有 Rust core/replay/bin、公共helper/wrapper/tests、research.py/fixtures/offline_exec 和真实OHLC证据，但未交付实例测试/文档/发布/正式交接。原worker自报 Rust178/Lab341及IS144/OOS143只保留为自报，Developer自建 verify-reproduction 不是独立Tester；本卡未重新执行。静态定位以本报告旧行号为锚点，迁移后在交接补新符号/行号，不再反复读取整篇replay。

本卡只写 Design 和 recovery-design-handoff 两文件；下述均为后续 planned work，不能据此写已修复/工程PASS。独立Gate只检查恢复文档能否实施，不替代 M2-A-001..010。所有原版/候选hash与dirty归属保留；若发现新人员同文件改动则hotspot并停相关写入，不清场、不把全部dirty归于恢复。

### 18.2 R6：生产 DTO / 纯 driver / 测试的最小职责拆分

精确新增文件仅 §8.1 的 replay/types.rs、replay/driver.rs、replay/tests.rs、replay/tests/state.rs，不增加 Cargo、lib.rs、bot/mod.rs、Python算法或平台。原 replay.rs 2829行中生产部分止于1629，cfg(test)起1630/1631；下表行号是本次只读候选的迁移定位，不是永久代码行号。

| 目标（均 BOT/src/bot/arbitrage/ 下） | 从候选迁移的符号/边界 | 收敛目标（含注释/空行，后续wc实测） |
|---|---|---|
| replay.rs | 保留模块文档、run(498–580)、failure(583–601)、write_rows(604–613)；仅JSONL编解码/流I/O/summary装配 | ≤300行，公开 facade，不保留第二driver/DTO |
| replay/types.rs | ReplayConfig及validate/strategy_config；ReplayMode/EvidenceType/EventType/ResultStatus/LabelStatus；EventEnvelope/Payload/所有payload、OutputRow、ReplaySummary、ReplayError、协议/退出常量（原23–457，MISSING_EVIDENCE_REASONS除外） | ≤550行；present_option与serde字段定义同模块，不丢deny_unknown_fields/校验 |
| replay/driver.rs | MarketState/SpotState(463–490)、DriverFailure/Driver及全部方法(616–1560)、tradable_market/other_id/same_identity/levels(1562–1629)、MISSING_EVIDENCE_REASONS | ≤1200行，纯内存状态机；不含BufRead/Write/路径/进程/网络 |
| replay/tests.rs | 原helpers/T0/ROUND(1632–1872)；warmup_19_20_returns、identity_and_available_state、tick_reasons_follow_the_frozen_priority、the_time_boundaries_are_respected、order_duplicates_and_conflicts（至2398） | ≤900行，保留原case与断言；仅一个helpers源 |
| replay/tests/state.rs | confirmation_state_machine、prefix_causality_and_determinism、proxy_has_no_market_or_execution、the_configuration_only_accepts_the_original_values、a_label_is_only_evaluated_after_the_fact（2399起） | ≤650行；复用父helpers，不复制核心或golden |

模块注册/隐私必须按真实 Rust 层级落实：arbitrage.rs 原 `pub mod replay;` 不变；replay.rs 声明私有 `mod types; mod driver;`、`pub use types::*;`（仅重导出原pub项），并以 `#[cfg(test)] mod tests;` 注册测试。types/driver 不对外pub。保留公开 `replay::{run,ReplayConfig,ReplayMode,ReplaySummary,ReplayError,...}` 名称与JSON字段/错误码；bin无须改import，公开协议不变。测试 tests.rs 内 `mod state;` 对应 replay/tests/state.rs，state.rs 用 `use super::*;` 访问父测试helpers；完整测试名可能多一层state，须映射原名，不靠旧路径过滤漏跑。

父子可达性不是“所有private跨模块自动可用”：types 与 driver 是兄弟。types 中原 private `ReplayConfig::strategy_config`、`ReplaySummary::new` 改为 `pub(super)`，仅replay子树可用；`present_option`/FROZEN_*仍private，冻结阈值从 `super::super::{VOL_HALF_LIFE_SECS,MIN_VOL_SAMPLES}` 引用到arbitrage。driver中的 `Driver` 及 `new/step/finish`、`DriverFailure`及facade读取的exit_code/code/message字段用 `pub(super)`，其余Driver/MarketState/SpotState字段、apply_*/辅助函数保持private。driver以 `use super::types::*` 和 `use super::super::{DecisionCore,MIN_VOL_SAMPLES}` 取DTO与祖先私有核心；Rust后代可访问arbitrage的private DecisionCore及其方法/状态，不能用pub(crate)/pub暴露core解决编译。必要chrono、BookSnapshot/TradableMarket等import各归所属模块；types无需导出I/O或核心。

调用图冻结为：bin → replay::run（facade）→ types解析/summary → driver::Driver::{new,step,finish} → arbitrage::DecisionCore → 原EwmaVol/digital_up/round_entry。实时 tick → 原live_entry → 同一DecisionCore；它不导入driver/types，不引入replay的严格限制。候选已有 with_warmup/vol_samples 等内部方法可复用但仍需原值断言/parity，不为迁移重写成 §9 的示意签名。DTO config.validate 必须满足 §10.1 六个冻结值，不能只验证half-life/min_samples而放行其他改参。

迁移顺序：先记录当前候选源hash/diff、测试清单及已有fixture/golden hash；再只移动DTO并接重导出；再移动完整Driver状态/impl/辅助函数并修最小pub(super)；最后迁移测试helpers与两组测试，移除原内联mod tests重复体。每步短Cargo离线编译/测试（获主控续接后）保留实际结果；第一次有迁移前测试失败也如实保留，不能为了“纯移动通过”删断言。保持原arbitrage golden与所有case、fixture字节不变；新补契约断言单列RED/GREEN。迁移前后按旧测试名→新全名核对同一case集，不以测试总数相等替代断言保留；JSONL同输入两次逐字节与原golden比较、summary枚举/计数/退出不变，若原候选违反冻结契约则留原失败/修复差异而不把它当正确golden。所有文件最终实测行数写交接；driver若超过目标先报主控，不自行多拆或放宽。

research.py不做投机拆分：1182行已有候选本期仅R1–R4/R5路径/R7薄I/O、原页校验、载体/退出修复，不含概率/入场算法。若补齐后1201–2400行，按根规则记受控扩张：增长源只限上述缺失契约、同源渲染及日志；本Design给出职责界限并由既有独立Gate/后续Reviewer审查，不新增一轮平台设计。拆分触发是下一次实质功能扩张（尤其新数据分支/新指标/调度/第二算法），届时先独立Review并冻结局部拆分；若本轮预计≥2401行或增无关职责立即停，不凭本Design继续叠加。本轮未证明需要新Python helper，故不新增helper路径。实例test_research/offline_exec目标各≤1200，不能把测试膨胀藏进research。

### 18.3 R1–R7 closure ledger：实现位置与可证伪验收

所有行均为待实现/验证，负责人固定 Developer 修复/自测 → 独立 Tester 重跑 → Reviewer 核源码/契约/报告；R6另由本次独立文档Gate确认设计，R7及数值基准按 §18.5 分工。原 §15.3 十项矩阵完整保留，以下不降级任何一项。

| 项 / 原报告锚点 | 精确修复位置与冻结 delta | 必须能失败的后续测试 / 对应M2-A |
|---|---|---|
| R1 / research.py:59,1081 | INSTANCE/research.py 的main/CLI出口与Rust映射：增加EXIT_EVIDENCE=3；合法proxy无论两区是否足够均外层3，不把Rust3转外层0；两区不足写未完成/不得发布完成研究，exit3只表示证据不足，不自动表示工程完成。Rust2→2、64→64、5→2并记rust.ioFailure；外层超时5；优先保留原错误，不被finally日志写入改成0 | INSTANCE/tests/test_research.py：真实main(argv)返回3；再用项目解释器执行本research CLI检查进程returncode=3及两区计数/未完成标记。mock子进程各码/超时/schema缺失/非空输入空输出分别断言，不能只检打印；A-006/009 |
| R2 / research.py:312–427 | INSTANCE/research.py checked_request/check_page及离线原页重放共享同一seen生命周期：parse_bar_time→UTC epoch秒+微秒精度校验，epoch%300==0；规范键对应O/H/L/C/V元组，相同重复加计数、冲突exit2 ohlc.conflict。seen跨同一次fetch全部页，校验/保存脱敏页在fetch_klines合并前；缺省volume/类型不私自修复。offline从raw-pages逐页喂同一校验，不只检查已覆盖后的ohlc | test_research内同页/跨页相同条目、改任一OHLCV冲突、seconds/ms等价键、整分钟但1/4分钟错位（秒为0仍拒）、非零秒/微秒、volume0接受；mock现有request注入证明冲突时fetch没有拿到后页覆盖结果；A-005 |
| R3 / research.py:525,687,714,770 | INSTANCE/research.py build_coverage/pair_samples/build_comparison：计划边界枚举[start,end)每300秒，left join真实bars与Rust value；所有计划行保留。无book的candidate/trade/PnL=N/A+proxy_only/no_real_account_equity；不写0。IS t<split且label_at≤split；OOS t≥split且label_at<end；仅t<split<label_at是cross_split，end边界仅label_missing。有效对才计is/oos/tie/n和聚合；无bar列N/A且bar_missing，缺p的实际warmup行才warmup；有输入value却丢输出exit2 | test_research：删除评估bar后计划行键全集不变、缺口重暖；t=split−300有效IS、t=split有效OOS、t=end−300保留N/A且cross_split_count不增；fixture不混n；逐个比较所有比较行/NA/reason，重算有效对Brier/0.5基准；A-005/006/008 |
| R4 / research.py:836–858,909–1007 | INSTANCE/research.py 输入/发布前检、write_json/write_csv/JSONL/日志/availability/parameters，以及BOT新bin的create_new路径必要修复；执行顺序与原子语义见本节后文。离线复用原始availability而不重写历史checked_at；三类可得性对实际文件/hash/范围核查，不以模板句认已核实 | test_research：预置每类目标/符号链接及模拟前检后竞态均拒覆盖，原bytes/hash不变；记录调用顺序parameters先于输入/Rust，fake HTTP/token调用即fail；mock成功/失败/超时都有真实日志与exit。缺历史命令记NOT_CAPTURED、availability历史时间不改；A-004/008/009 |
| R5 / offline_exec.py:124–194,213,245；research.py:41–43,615 | INSTANCE/tests/offline_exec.py：修唯一项目根、净化FD/环境、清空cwd；删除闲置错误run_filtered/control_socket_must_fail等内联runner，只保留一个fork/filter/exec实现与其负对照，不再Python -c/runpy链。INSTANCE/research.py根解析与run_rust也用相同工作区判据/绝对bin和env白名单；不引入新runner文件 | test_research：从根cwd/任意空cwd以绝对脚本和项目相对参数得到同绝对路径，错根/缺文件64且不执行bin；打开故意inheritable普通文件FD，在同一启动器child exec前断言全部≥3已关闭（诊断pipe例外随后关闭），0/1/2均本地而非socket。随后原offline_exec实际seccomp AF_INET负对照EPERM、新CLI非空输出、--live/--rpc-url外层64各独立日志；A-002/009 |
| R6 / replay.rs=2829 | 仅 §18.2 精确Rust colocated模块、原facade/core/bin必要接线；research受控增长不变算法 | Cargo离线安全集合非空、迁移清单/原golden/fixture/前缀对拍、私有可达编译、最终wc逐文件；不只看行数或旧自报；A-001/003/009 |
| R7 / 原缺失尾项 | INSTANCE/tests/test_research.py、spec.md、README.md、reports的五文件；LAB/SKILL.md/strategies/INDEX.md原定窄增量；ARCHIVE/report.md与REC新证据；data/tasks/active/2026-11-10-predict-btc5m-m2/implement-handoff.md。只补原目标，不重建已有core/helper；Verify/Review交接由独立角色写 | unittest实际非空执行，spec/README与真实exit3/命令/UNKNOWN一致；报告模板核心章节/所有计划栏/CSV同源/hash/归档索引/源码身份/缺证据均可核；原十条均映射且未运行项不写PASS；A-007/008/010 |

R3覆盖计数必须使用同一原页事实：raw_count=页行数总和（含相同重复），duplicate_count=相同键同OHLCV的额外出现次数，unique_count=seen去重后且裁剪前条目数；成功无冲突时raw_count=unique_count+duplicate_count。unique按future(bar_open>as_of)→unclosed(close>as_of，含bar_open=as_of)→range→closed互斥分组，和等于unique_count。closed必须属于 §11.1 精确open集合；coverage_complete只比较真实observed和expected集合。离线只有ohlc却无原页时原始raw/duplicate/unique等无法还原必须null+reasons说明，不用裁剪后309或模板0充原页数；有原页则重校并比对精确窗口内内容与ohlc一致，冲突exit2。evaluation_boundary_count仍是实际边界数，不等于计划样本行数；cross_split_count只计实际严格跨split，tie只计有效配对，两区样本不足不能发布为已完成。

R4的次序固定为：纯CLI/参数验证 → 检查输入可读/源目标不相同及所有发布/证据目标（不读输入内容） → 独占创建全新research目录 → exclusive写 parameters.json（含冻结窗口/as_of/预算/原参数、输入路径、离线入口） → 只读输入并记录hash/历史来源 → 原页校验/可得性本地审阅 → Rust → 聚合一次 → 各输出一次性exclusive创建。原子指每个输出用O_EXCL/create_new（Python x/xb且拒目标symlink），不是exists检查后write_text；多文件不承诺事务全成，失败保留partial并停止，不能unlink清场。最终coverage在内存组装完成后只写一次，不先写再覆盖；commands亦在finally仅写一次，涵盖成功/异常/超时。Rust summary/output由Rust独占写，Python不预占该文件；path冲突/既有目录前检exit64，运行期输出I/O失败外层2且留真实诊断，不伪成功。命令日志stdout/stderr可在独占创建的已打开本地log FD中流式保留；参数前检失败/碰撞不向碰撞目录写诊断，以工具真实返回保存到REC/logs，不伪造研究文件。

可得性恢复记录：以 ARCHIVE/evidence/availability.json 为历史声明原件保留，原 checked_at_utc、三个URL/status不替换；新增本地审阅字段 reviewed_at_utc、review_mode=offline_archive_review、checked_files[{path,sha256,available_range,observation,gap}]，三类rows均给明确研究起止和实际文件引用。本地最低来源为 §11.3 已列 gaps/report.md、gaps/evidence/quantdinger-readonly-probe.json、quantdinger-btc5m-bars.json、intake/evidence/sources.json及公开路由源码；只读核对内容所能支持的范围。未核对/无原始日志/文档仅状态声明分别保留not_verified/NOT_CAPTURED/archived_claim，不能升级已核验历史盘口或官方标签；本次新“核查时间”只表示本地文件审阅。若旧材料缺失且无法满足A-004，记录未完成交主控，不能因有模板就通过，也不能自行联网修复。

R5测试不借新临时脚本：seccomp逻辑/负对照/child分支均在修复后的原定offline_exec.py，unittest只导入测试该实现并执行原CLI。所有新进程都由项目解释器、已构建绝对Rust bin或原test CLI启动，不通过shell/Python -c/heredoc；参数注入负对照不尝试真实RPC。安装filter失败或对照能创建socket即FAIL/NOT_RUN，不继续CLI；新审批拒绝立刻停止并留原返回，不用其他工具/解释器“确认一下”。允许的只是本次明确恢复授权后的原定测试，不追认旧scratch探针。

### 18.4 唯一恢复证据根与保全/发布责任

新目录唯一为 `data/reports/2026-11-10-predict-btc5m-m2/evidence/recovery-01/`。本卡不创建它；原T3续接首次开始由Developer确认不存在后exclusive创建，若已存在（含symlink/空目录）停主控，不删除/搬移/自动编号recovery-02。认领后只按下表分区写，某条命令输出碰撞不允许换一个目标重试已拒动作；正常需修复失败时保留现有失败材料，由主控明确续接安排，不循环覆盖。

| REC相对路径 | 写入者/创建时点 | 内容/约束 |
|---|---|---|
| logs/command-<序号>.log、logs/commands.json | Developer，原T3期间，每条短命令实时保存；阶段结束索引一次生成 | 包含迁移前失败、编译/list/安全test/unittest、CLI/研究外层3、git/wc/hash实际输出；序号唯一，成功失败均留；不是Tester验收 |
| cli/fixture-output.jsonl、fixture-summary.json；cli/negative-live.log、negative-rpc.log及命令日志 | Developer，启动器修复后 | 实际fixture非空/负对照EPERM/两个64；负向业务目标名negative-live-output.jsonl/negative-live-summary.json、negative-rpc-output.jsonl/negative-rpc-summary.json，预期不创建，不造空文件 |
| research/（§12.1精确文件） | Developer，单次离线真实OHLC分析 | 源文件来自旧evidence，只读原件并记录hash；copy到新目录的ohlc/raw-pages原字节留源hash，修复后分析文件新hash；旧结果不是golden，不搬旧日志充新日志；零新请求 |
| scope-diff.patch、core-diff.patch | Developer，结束时一次写 | 主仓/BOT实际diff与候选/修复差异说明；包含untracked新文件的内容hash/清单，不能只git diff漏掉未跟踪源码；原SHA/gitlink与新源码hash分列 |
| numerical-reference.json | 主控非实现者，Verify前 | §14双路径具体真实样本数值/来源hash/容差；禁止Developer代填，旧证据中的同名文件只读参考 |
| independent-verify/logs/、independent-verify/cli/、independent-verify/research/ | 独立Tester阶段exclusive创建（本卡/Developer不预创建、不写） | 与Developer同格式的短命令/CLI/真实输入独立重现；research用--no-publish；读修复后输入/源码基线与主控reference，不覆盖任何已发布文件 |
| verify.md、review.md、commands.json | 各独立角色在其阶段独占创建；最终commands.json由主控Closeout一次生成 | verify/review写真实独立结论；总索引只指向各角色已冻结命令索引，不把Developer日志命名为Verify；未执行不预建空PASS文件 |

旧 `ARCHIVE/evidence/` 中除本次新 REC 子树外的所有文件、`superseded/run-before-warmup-*`、`verify-reproduction/` 和原worker失败产物全只读，不递归整理/复制成“新验收”。历史缺日志标 NOT_CAPTURED，command时间/退出不能倒填。新研究request_count/qd_request_count/document_request_count均为实测0；原取数历史请求数与查询时间只作source历史字段分列，不能改成“本次重新请求”。遇矛盾留预期/实际，不改旧证据“修正”。

首次发布仍只有 INSTANCE/reports/report.md，CSV/coverage来自 REC/research 精确字节；自动 report-preview.md只是同源审计快照，不维护第二正文。ARCHIVE/report.md仅索引该正文/新hash/REC/旧未验收历史引用。写前同时核所有实例目标和ARCHIVE索引不存在；若出现此前未知的同名报告不覆盖，本次交主控裁定。无有效真实两区则只保留REC诊断/预览、研究未完成，不发布假“首份研究完成”。测试中只有fixture输出不能补足研究。旧自报与新命令并列标身份，不以本次文档Gate或本地复现洗成已独立验收。

### 18.5 交接/阶段停止与验收上限

本卡完成条件只限版本/路径/隐私/迁移/ledger/证据/命令闭合与实际静态检查；交接仅索引 §8.1、§15.1、§18及实际短git/wc/sha256结果，不复制实现正文。本卡不跑Cargo/Python/新CLI/seccomp/网络，不创建数值基准/证据/测试stub，不读credentials。源码、测试、RFC/SPEC及原历史证据不变；允许本文路径变更不等于本卡可修改实现allowlist。

独立文档Gate完成后必须看verdict而非卡done；APPROVE只允许主控按既定任务图续接原T3的R1–R7，不代表实现正确，REVISE则不开放新增文件。原T3交接须列R1–R7旧锚点→新file:line→命令日志→预期/实际→未完成项，并逐项映射原M2-A矩阵。后续仍是非实现者双路径真实样本基准 → 独立Tester实际回放/数值/载体验收 → 独立Reviewer三层/源码/报告/范围审查；不能拿Developer的verify-reproduction/本卡静态检查替代。任一数据/安全/审批/范围硬缺口如实停止交主控，不放宽契约或添加平台/Activation/资金/收益门槛。
