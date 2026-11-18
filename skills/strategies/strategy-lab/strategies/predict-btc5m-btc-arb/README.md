# Predict BTC5m 代理研究实例

本实例读取归档真实OHLC，经 Toolkits 的同一Rust决策核心输出粗频概率；不提供历史可执行PnL，也不启动原机器人。规格见 spec.md；正式工程契约见项目 docs/{rfc,spec,design}/07_trading/ 下的 *07-001-predictfun-btc5m.md。

## 当前状态

2026-11-10 Developer离线恢复研究已执行，研究外层exit3（insufficient-evidence）：实际闭合309根、21个预热价格、288个计划边界，有效IS144/OOS143，末尾1行label_missing。新增HTTP=0，token读取=0。venue/product未知；候选/成交和真实收益均N/A。仅是实现者自测及代理研究，不是独立验收通过或实盘就绪。

唯一研究正文：reports/report.md。配套CSV与coverage均为同一次内存聚合的投影。归档索引：项目 data/reports/2026-11-10-predict-btc5m-m2/report.md；恢复证据在 evidence/recovery-01/，历史未验收材料只读保留。

## 本地构建与测试

全部用已缓存依赖、项目解释器，不安装/升级：

    # cwd = skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits
    cargo build --locked --offline --bin btc_arb_replay
    cargo test --locked --offline -- --list
    cargo test --locked --offline

    # cwd = /home/pascal/workspace/yquant-investment
    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/tests -p 'test_*.py'
    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests -p 'test_*.py'

不启用 --ignored。原3个真实联网Rust测试保持ignored；其余是纯计算/本地fixture。Python测试的合成数据和mock不充当真实研究证据。

## 离线重现和安全边界

本轮已运行的完整命令及固定窗口在唯一正文的“复现命令”和 recovery-01/research/parameters.json；Rust实际argv/native exit/UTC起止/cwd在research/commands.json。独立Tester须使用Design指定的新independent-verify/research目录并加--no-publish；该目录不由Developer预创建。禁止重跑到现有证据/发布路径；任何碰撞都必须停止，不覆盖、删除或自行换目录。

research.py支持 --ohlc-file、--raw-pages-file、--availability-file，归档入口不调用token解析、QD或官方文档HTTP；原页与归档OHLC必须一致。参数冻结先于业务读取。原子x/xb/create_new写入，partial失败保留。无有效两区不能发布完成研究。

原 tests/offline_exec.py 安装仅对子进程生效的Linux x86_64 seccomp过滤；先动态AF_INET socket负对照EPERM，再exec绝对Rust bin，清env至LANG/TZ、空cwd、关闭全部>=3继承FD。现有fixture实际回放exit3，--extra=--live和--extra=--rpc-url实际均64且无业务输出。它不改宿主网络，不读取交易凭据；安装失败不回退假无网。文件访问边界同时依靠显式输入调用图审查，seccomp不是通用文件系统沙箱。

退出码：研究合法代理3；契约/运行I/O失败2；超时5；参数/路径/前检冲突64。合法3不表示交易有效性，也不替代M2-A-001..010的工程验收。

## M3 官方历史入口（2026-11-12，未完成）

新增 history_research.py / history_metrics.py 和隔离 btc_arb_history，旧 research.py/proxy 不变。
固定窗口、六偏移、因果规则及统计口径依三文档 V1.3 §14/§16/§19；不调用 QuantDinger。
一日真实 pilot 已完成数据消费，但约309.5秒超过300秒上限；94日未启动，本次状态 BLOCKED_BUDGET。
原 pilot 外层0是末次verify后漏检超时的已知缺陷，不是预算通过；修复后新增定向回归，未重跑生产读取。
所有旧及 pilot 原始证据保留；详情见项目 data/reports/2026-11-12-btc5m-native-history-research/evidence/developer/budget-assessment.md。

构建及定向测试（项目解释器，不安装依赖）：

    # cwd = Toolkits
    cargo build --locked --offline --bin btc_arb_history
    cargo test --locked --offline --lib bot::arbitrage::history::tests
    # cwd = 项目根
    .venv/bin/python -B -m pytest skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/test_history_research.py skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/test_history_metrics.py skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/test_history_input.py -q

真实执行过的一日 pilot（不可原地重跑，独占输出）：

    .venv/bin/python -B skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/history_research.py --mode pilot --as-of 2026-11-12T09:09:11Z --evidence-dir data/reports/2026-11-12-btc5m-native-history-research/evidence/research/pilot-01 --report data/reports/2026-11-12-btc5m-native-history-research/evidence/research/pilot-01/report.md

全窗命令形状为相同脚本 --mode full --as-of <执行前固定UTC> --evidence-dir <全新且位于本主题evidence/research下的目录> --report data/reports/2026-11-12-btc5m-native-history-research/report.md。
这是复现接口说明，不是新增执行授权；当前超预算禁止启动或覆盖现有报告。正式全窗仍未运行，不能释放Tester或Closeout。
CLI只允许mode/as-of/evidence-dir/report；Rust只允许config/input/output/summary/from-ms/to-ms。无live/RPC/wallet入口。

## M4 研究性能编排（2026-11-17，2026-11-18 Fix1/Fix2 返修）

新增 `history_performance.py`（旁路性能入口，`history_research.py` 与 `history_input.py` 不变）：

- `--mode rescore`：只读复用**已签收**的 `samples.csv`，本地重评分重建 comparison/calibration/daily/monthly，
  与归档统计逐列比对；不启动 Rust、不连 Mongo。
  输入身份必须与固定可信清单（五个文件的 sha256）逐项匹配，且 identities/params/manifests
  互相自洽；**自算 hash 不构成自认证**，其它 source-dir 一律拒绝。
- `--mode window` / `--mode candidates`：用既有 facade / day_events / 既有 Rust history 核心跑显式窗口。
  事件流每日只编码一次并广播给多个**同配置**独立核心（各自连续状态、各自 stdout）。
  每个核心导出**自己的**完整 samples.csv 与四张统计表，编排层逐列精确比较（无容差）。
- 有界预取：最多 2 个并行读取任务 / 有界待消费结果。**未启动**的待读日被取消且**确定不会运行**；
  已启动的读取无法杀死，如实记为 `unreclaimed` 并保留在 registry 中不丢弃。
- **默认 `--strategy serial`**；`prefetch` / `both` 仅显式启用。`candidates` 模式**始终**追加
  `independent` 控制臂（逐实例独立重复读取）；`--strategy` 决定的是是否附加预取臂，不是是否跑独立臂。
- 失败传播：任一实例非零退出、缺 values/summary、partial summary、写入阻塞超时或预取未回收，
  都令该批 `complete=false`，CLI 返回非零（4=批次不完整，2=异常，5=超时，6=源码漂移，7=中断），
  绝不发布伪完整状态。
- 有界退出：stdin 走非阻塞管道 + `select`，总 deadline 约束每次事件写入与最终等待；
  回收顺序为 terminate → 有界 wait（`CORE_WAIT_SECONDS`）→ kill → 有界 wait（`CORE_KILL_SECONDS`）
  → reap，全程只用 `wait4(WNOHANG)`，**不存在**阻塞式 `wait4(pid, 0)`；活着的子进程绝不记为已回收。
- 异常路径同样落盘：超时、open 失败或中断时，partial 状态、每核 native exit / terminate / kill /
  reaped / 未回收标记与 prefetch 的 cancelled / reclaimed / unreclaimed / still_tracked
  写入 `failure.json` 后原异常照常抛出，清理异常不掩盖原异常。
- 原生 summary 契约校验：按 `src/bin/btc_arb_history.rs` 的实际输出检查 `native_exit` / `spots` /
  `values` / `complete` / `error` 五个必需字段、精确类型（bool 不作整数）与
  「值计数 = 实际输出行数」「native_exit 与观测退出码一致」的出口一致性；
  仅写 `{"complete": true}` 或字段缺失一律判失败。
- 运行身份绑定：`identity-start.json` 记录**开始时**的 source/tests/config/binary 及公共 facade
  （client / history_reader / history_types / storage）sha256，`identity-after.json` 与该快照
  **逐项比较**；漂移即保留两份证据并 CLI 返回 6，不再比较两次结束态。
- 跨臂拒绝闸门：main 成功前统一比较各臂的逻辑单流 event/day 内容身份、逐实例完整 samples
  身份与行数、valued 行数、missing-reason 分母，以及 source 摘要的 coverage / missing / pending /
  conflicts / row_counts；独立臂**各 part 的完整 samples** 也逐列比较。独立臂 events 总量是其
  自身重复读取之和，不与共享臂单流值直接相等比较。

边界：`replay/types.rs` 的配置校验锁定原参数，`vol_floor` 仅接受 0.00005。因此本模块只做
**多实例控制实验**（相同冻结配置的多个独立连续核心），**不**交付不同 floor 的模型能力、
**不**放宽 Rust 校验、**不**输出模型择优；后续 M2 / 最新 phase1 研究接线按其自身契约另办。

输出目录固定在本主题 `evidence/` 子树（`developer` / `fix1` / `validate` 皆可），且独占创建、
冲突即失败（不覆盖既有证据）。所有产物只读本地既有归档与真实 facade，不写生产库、调度、paper
或交易配置。

构建及定向测试（项目解释器，不安装依赖）：

    .venv/bin/python -B -m pytest skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/test_history_performance.py -q

    # 结果复用（无 Rust、无 Mongo）
    .venv/bin/python -B skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/history_performance.py \
      --mode rescore \
      --evidence-dir data/reports/2026-11-17-btc5m-research-performance/evidence/fix1/rescore-<run-id>

    # 真实 facade 多实例控制实验（共享输入 vs 独立重复读取）
    # 默认 serial；加 --strategy prefetch 才附加预取臂
    .venv/bin/python -B skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/history_performance.py \
      --mode candidates --instances 2 --strategy serial \
      --start 2026-11-15T23:30:00Z --end 2026-11-16T00:30:00Z \
      --as-of 2026-11-17T15:00:00Z \
      --evidence-dir data/reports/2026-11-17-btc5m-research-performance/evidence/fix1/candidates-<run-id>

CLI 只接受 mode/as-of/start/end/evidence-dir/source-dir/expect-samples-sha256/instances/strategy/budget-seconds；
输出限定在本主题 evidence/ 子树，越界即拒绝。
evidence 目录为**独占创建**：已存在即失败，绝不覆盖既有证据。--instances 上限 3。
每次运行在 evidence 目录写入 `identity-start.json` / `identity-after.json`：argv、cwd、
当前 source/tests/config/binary 与公共 facade 的 sha256，用于把运行绑定到具体候选代码版本；
`sources_unchanged` 是「开始快照 vs 结束快照」的逐项比较结果。
运行还写入 `runs.json`（各臂结果）、`arm-comparison.json`（跨臂拒绝闸门结论）与
失败时的 `failure.json`（partial 状态与清理证据）。

