# DESIGN-07-001: Predict.fun BTC 5m——M1 fork 接入与原版基线

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft；T2 设计交主控校验，未实施，不是运行授权 |
| 作者 | YQuant Principal（yquantprincipal） |
| 创建日期 / 最后更新 | 2026-11-09 / 2026-11-09 |
| 版本 | V1.0 |
| 来源 RFC | [RFC-07-001](../../rfc/07_trading/RFC-07-001-predictfun-btc5m.md) V1.1 |
| 来源 SPEC | [SPEC-07-001](../../spec/07_trading/SPEC-07-001-predictfun-btc5m.md) V1.1 |
| 上游交接 | [rfc-spec-handoff.md](../../../data/tasks/active/2026-11-09-predict-btc5m-m1/rfc-spec-handoff.md) |
| 目标模块 / 工作区 | 07_trading；`/home/pascal/workspace/yquant-investment` |
| 来源任务 / 阶段 | t_89c7f315；Full Flow T2 Design，仅 M1 A/B |

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
| `data/tasks/active/2026-11-09-predict-btc5m-m1/` | 新增必要 `implement-handoff.md`、后续 `verify-handoff.md`、`review-handoff.md`；保留上游 `rfc-spec-handoff.md`，不提前搬迁归档 |

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
| 过程交接 | 阶段结束或失败时写 `data/tasks/active/2026-11-09-predict-btc5m-m1/implement-handoff.md` 等 | 本阶段事实、A 项、停止点、report 路径、下一角色 | 不复制报告第二结论正文；失败模板见 §6.3，不提前归档 |

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
test ! -e /home/pascal/workspace/yquant-investment/data/tasks/active/2026-11-09-predict-btc5m-m1/rollback-implement-01
test ! -L /home/pascal/workspace/yquant-investment/data/tasks/active/2026-11-09-predict-btc5m-m1/rollback-implement-01
mv /home/pascal/workspace/yquant-investment/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits /home/pascal/workspace/yquant-investment/data/tasks/active/2026-11-09-predict-btc5m-m1/rollback-implement-01
```

这三条必须逐条检查返回，只有前两条均成功才执行 mv；过程主题目录须已存在。保留主仓 `.git/modules/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits` 不删除。搬移后 `.git` 相对路径不再可用，隔离目录是保全副本不是新可运行仓库；不在隔离目录运行 Git/Cargo。恢复时由主控确认重新接入范围，将目录放回原路径即可恢复原相对 `.git` 关系，再按已保留 section/index/SHA 记录登记并重做 §3.2.4 全部读回。隔离残留和 modules 槽位须在交接明确标注，后续不得盲目再次 add。

5. 用 §5 的主仓 diff/index/status 读回，确认只撤销了本轮登记/入口变化，证据仍在。部分接入失败如没有形成某一对象，跳过对应撤销并记录，不把“不存在”当必须执行的删除动作。

此撤销不运行 reset/stash/clean、`rm -rf`、强制 deinit、全局配置修改、Cargo clean、commit/push；不删既有目录，不回退其他子模块。不能安全撤销就保留现场交主控，不能为了“回滚完成”扩大副作用。

### 6.3 失败交接文案模板

写入 `data/tasks/active/2026-11-09-predict-btc5m-m1/implement-handoff.md`（Verify 对应用 verify-handoff.md），各字段用实际工具结果填写，不把本段当已发生记录：

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
