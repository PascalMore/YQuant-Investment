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

