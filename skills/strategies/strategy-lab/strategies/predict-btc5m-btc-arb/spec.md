# predict-btc5m-btc-arb 实例规格

日期：2026-11-10；时区：UTC。类型：真实 OHLC 代理研究，不是可执行收益回测。

## 正式契约

以项目根 docs/rfc/07_trading/RFC-07-001-predictfun-btc5m.md、docs/spec/07_trading/SPEC-07-001-predictfun-btc5m.md（均 V1.2）及 docs/design/07_trading/DESIGN-07-001-predictfun-btc5m.md V1.2 为准。本文件仅冻结实例适用范围，不替代三层契约。

## 单核心与输入

唯一生产决策为 Toolkits fork 的 arbitrage::DecisionCore，实时入口与 replay driver 共用。Python research.py 仅做文件/原页校验、事件编排、调用 Rust、标签配对和同源载体渲染；不重写 EWMA、digital_up 或入场公式。CLI btc_arb_replay 不读取业务运行配置、钱包或凭据，不调用原机器人。

市场标识 Crypto/BTCUSDT/5m；来源 QuantDinger Agent。venue、product、实际成本、历史份额盘口与权威结算均 UNKNOWN/not_verified。闭合 OHLC 的 close 在边界立即可得仅是代理时钟假设。

## 本轮冻结参数

- start=2026-11-09T06:00:00Z；split=2026-11-09T18:00:00Z。
- end=as_of=2026-11-10T06:00:00Z；窗口半开；频率300秒，预热21个价格（20个收益）。
- fetch open 起点2026-11-09T04:10:00Z；最后计入bar的close严格早于end。
- 初始资本200 USDT只作离线显式参数，不生成虚构账户权益。
- 原值 min_edge=0.03、order_usd=5.0、min_secs_left=30、vol_floor=0.00005、half_life_secs=300.0、min_vol_samples=20，禁止优化或改参。
- 上限 max_pages=2、max_data_requests=50、wall_seconds=1800；本次恢复只读已归档 ohlc/raw-pages/availability，新增HTTP与token读取均为0。

## 校验、配对和输出

原页在客户端合并前按UTC epoch秒与OHLCV元组检查，同/跨页相同条目去重并计数，冲突exit2。对齐为epoch%300==0且无微秒；成交量0有效。离线原页重验并与OHLC窗口内容比较。raw/duplicate/unique为裁剪前口径；unique互斥拆为future、unclosed、range、closed。无原页时原始计数null并说明缺口。

所有[start,end)计划边界均保留。缺bar=bar_missing；已有value但无概率=warmup；缺Rust value输出是契约错误，不能伪装数据不足。标签为下一close相对当前close的方向（1/0/平价0.5），不是官方结算。IS要求t<split且label_at<=split；OOS要求t>=split且label_at<end；仅严格跨split计cross_split；end尾行保留label_missing，不计有效样本。Brier与恒定0.5基准仅在相同有效配对上聚合。

无份额盘口的候选数/成交数为N/A+proxy_only；净PnL、收益、年化、Sharpe、MDD、Calmar、换手、IR为N/A+no_real_account_equity。不用0冒充观察，不把fixture/real-proxy/real-market混计。网格表A/B、四折、G/E及35%阈值不适用；不提交QD回测/进化。

## 原子保全和退出

参数/输入可读性/全部发布目标前检在业务读取前；独占创建全新research目录，先exclusive写parameters。所有载体单次x/xb创建，Rust输出create_new；拒绝既有文件、目录或symlink；失败保留partial，不删除、覆盖或自动换编号。旧availability时间、来源、原观察保留，本地审阅另列文件hash/范围/缺口；缺历史命令日志标NOT_CAPTURED。

研究外层合法代理始终exit3；两区无有效样本则research_completed=false，仅保留预览/诊断，不发布完成研究。Rust2映射2、64映射64、I/O5映射2并记rust.ioFailure；外层超时5。记录真实子进程native exit、UTC起止、白名单env、实际cwd和日志。输出冲突前检64、运行期写入失败2，不能被finally日志改成成功。

## 交付与验收状态

唯一正文 reports/report.md，events.csv、proxy-samples.csv、comparison.csv、coverage.json同源；归档 data/reports/2026-11-10-predict-btc5m-m2/report.md 仅保存指针和hash。Developer恢复证据在其evidence/recovery-01，旧材料只读。

本轮真实离线执行外层exit3，存在真实有效IS/OOS；结果仅支持该窗口粗频概率校准描述。Developer测试不代表独立Verify/Review。主控非实现者双路径数值基准、独立Tester及Reviewer仍须分别完成，真实净PnL与实盘就绪未验证。禁止真实/模拟交易、签名、生产写入、网络重采、服务调度和外发。

## M3 官方历史研究增量（2026-11-12）

仅新增 history_research.py/history_metrics.py，及 Toolkits btc_arb_history 薄入口；旧M2事实/协议不变。
冻结[2026-08-10,2026-11-12) UTC、split=2026-10-10、六偏移30/60/120/180/240/270，原config.json数值不变。
官方strike保持固定，Binance 1s close在close_exclusive可得，身份/strike可得时间不得晚于决策；event-time-proxy非严格PIT。
每日日界只切读窗口，不重置同一Rust进程EWMA；三流完整消费后verify_consumed，标签仅用于Python结果配对。

Python CLI精确选项：--mode {pilot,full} --as-of <UTC> --evidence-dir <全新本主题evidence/research子目录> --report <路径>。
pilot恰首日、预算300s且report必须在该新目录下；full恰冻结94日、预算3600s且唯一report为主题report.md。
命令实例见README；未知参数拒绝；输入输出独占，不覆盖。运行成功0、契约/运行失败2、超时5；argparse参数错误2。
Rust CLI：--config <本地ReplayConfig> --input <PATH|-> --output <PATH|-> --summary <新文件> --from-ms <UTC整数> --to-ms <UTC整数>。
Rust原生0/2/5/64分别为成功/契约/I/O/参数失败；仅spot/value协议btc-arb-history/1，拒绝未知字段及live/RPC/wallet参数。
外层schema_version/at_ms/seq/payload；spot payload为type/symbol/price/available_at_ms，value payload为type/symbol/round_id/starts_at_ms/ends_at_ms/strike/identity_available_at_ms/strike_available_at_ms。
只对value输出，不构造book/fee/订单；同刻spot先于value，seq严格递增，时间不倒退，20returns预热不变。

载体列唯一事实源为代码常量（不手写第二份报告数值）：
- samples.csv / SAMPLE_COLUMNS：round_id,day,partition,offset,at_ms,starts_at_ms,ends_at_ms,strike,spot,spot_at_ms,secs_left,samples,sigma,p_up,label,label_available_at_us,reason。
- comparison.csv/latest.csv / COMPARISON_COLUMNS：partition,offset；COUNTS为total,valued,scored,binary,draw,missing_label,unvalued,warmup,abstain,directed,correct,instant_directed,instant_all_correct,common_directed,common_correct,instant_correct,sigma_floor,basis_count；随后RATIOS各列及主accuracy/Brier/logloss/配对Brier差的lo95/hi95。
- RATIOS列：direction_accuracy,binary_brier,binary_logloss,payout_brier,base05_binary_brier,base05_binary_logloss,base05_payout_brier,brier_delta_vs05,common_model_accuracy,common_instant_accuracy,instant_accuracy,sigma_floor_ratio,basis_mean_bps,basis_abs_mean_bps。
- daily.csv/monthly.csv / DAILY_COLUMNS：partition,day,offset,COUNTS,SUMS,RATIOS；SUMS是RATIOS分子中非计数列的去重有序集。
- calibration.csv / CALIBRATION_COLUMNS：partition,offset,bin,lower,upper,count,mean_p,up_rate。固定10bin，二元非DRAW同分母。
- coverage.json明确理论天/轮/秒/评分位、实际评分位、原因分布、已verify天数、事件数/流hash、耗时/RSS。
- source-YYYY-MM-DD.json/source-manifests.json关联消费content/provenance/coverage/缺口与该次日事件hash；identities.json保存源码/二进制hash；params.json/command.json/run.json/rust-summary.json保存精确参数/命令/原生退出；values.jsonl保留原始Rust结果。

方向准确率排除DRAW/abstain；二元Brier/log-loss含0.5，兑付Brier另含DRAW兑付0.5；log-loss仅统计夹至1e-12。
分区独立PCG64(42)、UTC日整块1000次、六时点共享索引、分子分母加权、linear95%区间；不把六时点当独立轮。
spot相对strike偏差包括轮内价格移动，只是Chainlink/Binance参考诊断，不是同刻纯跨源基差估计。
所有交易/权益指标仍N/A，缺真实份额盘口/费用/执行链；高到期命中不是alpha。

当前状态BLOCKED_BUDGET：一日pilot真实消费完成但超300s；94日未启动、没有全窗报告。原pilot外层0因最后verify后漏检超时，不追认为预算通过；候选已修复并以新增回归验证，不重复生产读取。
证据见本主题evidence/developer/budget-assessment.md；独立Tester未执行，本增量尚未验收。

