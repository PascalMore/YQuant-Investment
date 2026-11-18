# DESIGN-06-003: BTC5m phase1 研究接缝与99日实验执行设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | Draft V1.1，T2吸收Pascal新决策的三文档候选；待独立只读Design Gate及主控核验，不是实现或Validate PASS |
| 作者 / 来源任务 | YQuant Principal / yquantprincipal；t_d02e821a |
| 日期 / 时区 | 2026-11-18；Asia/Shanghai（UTC+08:00） |
| 来源RFC | [RFC-06-003](../../rfc/06_strategy/RFC-06-003-btc5m-phase1-model-research.md) V1.1 |
| 来源SPEC | [SPEC-06-003](../../spec/06_strategy/SPEC-06-003-btc5m-phase1-model-research.md) V1.1 |
| 工作区 / 模块 | /home/pascal/workspace/yquant-investment；06_strategy |
| 阶段边界 | 本卡仅同步RFC/SPEC/Design三文档；预建独立Design Gate t_780aa76c后才可主控放行T3；T4独立验证后首次99日/复算/报告；主控Closeout |

历史T1 V1.0：RFC SHA256=`772d7f7d33cc14f72a153c8399a5db2338022b7023cdb7bc819b2858079cff72`；SPEC SHA256=`a53a9ccceddfc9a9bc134d740c380b8aa1cf78da61983b95aad7ab21d84745c4`，本卡修改前原生核对与旧Gate相符。该历史交接保留，不追认为V1.1通过。本次按Pascal 2026-11-18新决策同步修订两上游实体，最终V1.1 SHA另在本卡交接冻结；三文档版本/互引一致，阶段状态只取Kanban。本文命名/资源上限是实现决策，研究判定以新SPEC §4.7三层为准，不是生产参数批准。

## 1. 设计摘要

最小方案是新增显式 `btc-arb-phase1-history/1` 无盘口研究协议和一个隔离本地CLI，在原DecisionCore上调用现存observe_phase1，提取其现有预热/概率计算为交易与纯估值共用的小函数；Python新研究入口只做facade因果采样、广播、标签配对和统计。三个连续核心各保留独立源状态，M1只离线变换已落M0，不再查询价格或运行第四个核心。

不改legacy history/1、ReplayConfig、公共facade、history_input、旧性能入口或其输出根；直接复用性能模块的低层非阻塞写入/有界回收/summary校验，而不调用绑定旧参数/旧目录/旧统计的高层runner。新增入口并非通用研究平台，没有交易、服务、长期调度、数据采集或依赖安装能力。

数据窗口、A、六时点、折、候选、Platt正则、权重、bootstrap及研究判定严格来自RFC/SPEC V1.1；Pascal已明确同意诊断先行与判定收敛，取代旧“尚未采纳”评论及本卡原单Design范围。工程硬门禁不降，主证据与稳健诊断分列，工程完成允许最终“证据不足”或“假说不支持”。

## 2. 当前基线、缺口与兼容边界

### 2.1 本卡实核基线

主仓main HEAD=`523fc1a0cb14f6eb3d7bfcd4122f56d06ee975d7`；BOT本地main HEAD=`0250eb993958cc2f47e3b6e81e008a59a02b565f`，BOT工作树干净。主仓已有P的README、history_performance及其测试三项M，以及本轮RFC/SPEC两项untracked；均不是本卡改动，不还原、不混算差量。

本文路径缩写仅为精确展开，不是目录级授权：

- ROOT=`/home/pascal/workspace/yquant-investment`。
- P=`skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb`。
- BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。
- R=`data/reports/2026-11-18-btc5m-phase1-model-research`；E=`R/evidence`。

| 现有能力与实际符号 | 现状 / 证据适用域 | 本次必要delta |
|---|---|---|
| BOT/src/bot/arbitrage/history.rs:7,54–108；src/bin/btc_arb_history.rs | btc-arb-history/1；DecisionCore::new；legacy估值及严格旧配置，不能称最新phase1 | 原文件只读，新增显式分版适配，不在/1偷换语义 |
| BOT/src/bot/arbitrage/phase1.rs:522–619 | observe_phase1已有真实key/epoch/gap/clock及EwmaVol；reset原因在epoch内保留 | 原方法直接调用，不复制状态机或开第二个模型 |
| 同文件:913–939 | evaluate_phase1经book/费用/执行gate后才计算samples/sigma/digital_up | 仅提取这段模型计算供新纯估值复用；原交易检查顺序不动 |
| BOT/src/service/spot.rs:244–319 | EwmaVol/update/vol与digital_up/A&S原实现 | 全部只读；sigma_raw由已暖state的vol(0.0)取得，不新增近似估计器 |
| P/history_input.py | 三流、Decimal、微秒可得性、verify_consumed已具备 | 只读复用iter_history_input，不用全窗SQLite排序、不改facade |
| P/history_research.py:77–188 | 旧day_events为1秒更新、旧版本、旧slot及毫秒映射；merge_values为旧结构 | 不误列为待重写；新5秒与微秒薄适配在新入口，旧文件保持 |
| P/history_performance.py:538–818 | Instance、_write_event、_reap_core、_close_handles、_finish_core、_check_native_summary | 只读调用低层机制；新入口只补启动argv、严格新版本输出校验与新统计，不调用run_instances/main/_require_subtree |
| 同文件run_instances/_compare_instances/rescore | 同配置实验、累计contexts、旧统计和固定可信归档/性能根；不是异floor研究 | 不放宽旧路径或可信清单，不传新floor绕旧gate，不套异参概率全相同断言 |
| P/history_metrics.py | 已有numpy/PCG64日块、旧slot加权统计 | OFFSETS可只读引用；旧aggregate/contributions不适用于新轮次权重，不改旧结果 |

R4独立签收为t_c4065ffc/run3822，[report-r4.md](../../../data/reports/2026-11-17-btc5m-research-performance/report-r4.md)，139项及三个真实CLI是其原候选/旧协议事实，不是本次新增测试数。保护SHA：history_performance.py=`40f1251ed20de8198fed135e41fa78b38fcd5283f73c8fa0f282c4fd483588b3`，其测试=`f78e6c6516ec55d9bf8efd00882c42bfabd33fb4bd6aefe12805beff71198219`，README=`f439b9b02ef2a1d1fa4c422b34b7599e64c987ef44b9d4ecf168af72fbf643ae`。本文方案不需修改这三文件，也不重做R4/六组计时/预取对照。

### 2.2 旧源码、binary与契约保全

旧BOT源在上述既存Git提交中，T3修改前记录两个目标源的SHA及Git blob身份，保留原对象/分支，不checkout或清理。phase1.rs当前SHA=`9ed1594a2f842acdca408621b4f066baff1b7b889a7e4c3d1d203aabc4cd3237`，arbitrage.rs=`2d84e241c376cc060fa1d69af19ca5de500fbec1b7711c708d557856539b1e2f`；新候选须同时记录新工作树SHA，不能只报同HEAD而冒称同源码。旧history/replay和旧报告原样保留。

旧 `BOT/target/debug/btc_arb_history` 当前SHA=`2b90871b5e0e4c49cc0a0781684be72b4c6c431ed3303f9cc6fdd60f3e76a5f1`，禁止本轮build覆盖。仅构建自动发现的新bin `btc_arb_phase1_history`，路径为 `BOT/target/debug/btc_arb_phase1_history`；新bin另有自己的SHA/源码/协议/编译器/锁文件身份。cargo test旧bin只生成其测试可执行物，不运行旧bin的build命令。若工具链实际触及旧绑定binary导致SHA变化，停下保留事实，不能把新文件称原证据binary。

07-005三实体首尾保护值：RFC=`45b8b18aa3084a7cd2e4b5dbeefd2d2e208c60e93c840086c2c9108f54a54e88`，SPEC=`9d4c7c4bf4291ca3c00e2eef000514e01c99f6e181ed0ee407383cf80aceb2e1`，Design=`4d518d0bf5cbf687ac9b5bfa0d4a04329d00173adac78351335815a9c906ab78`。这些以及07-001旧文档均只读；本轮新研究隔离装配不更改controlled/replay/2或生产运行权限。

## 3. 方案设计

### 3.1 T3逐文件allowlist

每条均为“上述P或BOT精确根 + 下列相对文件”；没有目录通配许可。标新增的符号/测试/CLI是planned implementation，本卡不创建可导入stub。不必为用完allowlist修改不需要的行。

| 精确路径 | 性质 / 仅允许的内容 | 当前缺口与最小验证 |
|---|---|---|
| BOT/src/bot/arbitrage.rs | 修改：仅增加pub mod phase1_history；不改生产装配/参数/legacy算法 | 新隔离模块导出；旧history/replay编译回归 |
| BOT/src/bot/arbitrage/phase1.rs | 修改：新增pub(crate) Phase1ModelValue与DecisionCore::phase1_valuation，原evaluate_phase1模型段委托该方法；observe/reset及交易gate保持 | 同phase1无book估值；同输入交易路径与纯估值p/sigma/samples精确相同 |
| BOT/src/bot/arbitrage/phase1_history.rs | 新增：严格研究Config/Event/Value/History，proxy clock显式适配、最多当前轮状态、研究floor三值与同DecisionCore装配；inline cfg(test) colocated测试 | 分版、标签隔离、连续状态、时序、缺值、round冲突与有界状态 |
| BOT/src/bin/btc_arb_phase1_history.rs | 新增：仅本地file/stdin、exclusive输出、严格逐行解码、summary/接收hash；inline cfg(test)参数/协议消费者测试 | 真实native0/2/5/64和partial；绝不构造AppConfig/Broker/网络 |
| P/phase1_model_research.py | 新增：固定CLI/参数和身份、facade5秒适配、三核广播、逐日上下文/输出合并、产物/预算/报告薄编排 | 新主题路径而不放宽旧性能路径；真实main和真实Rust消费者 |
| P/phase1_model_metrics.py | 新增：M1/B1、共同集轮次权重、日/折/分层统计、bootstrap/判定、raw格式与SVG渲染；没有EWMA/digital_up主计算 | 旧metrics为旧分母；独立小例/梯度/指标复算 |
| P/tests/test_phase1_model_research.py | 新增：colocated真实main/facade边界/三核/所有权/退出/清理/旧配置拒绝测试 | 只替换输入/时钟/transport，不能mock整个runner/core/_finish_core |
| P/tests/test_phase1_model_metrics.py | 新增：训练截止/唯一轮B1/权重/拟合状态/折/统计/图表及反例 | 不用验证标签选参；严格分母/空值/区间/四类裁定 |
| P/tests/phase1_reference.py | 新增：仅验收侧独立EWMA、A&S及erf参考、独立拟合/统计/索引/载体复算，固定只读输入CLI；不可被主样本生成链导入 | 独立参考不是第二份生产模型；T4直接读落盘证据，不连DB/不启动子进程 |

T4源码/测试只读。T3/T4运行产物仅§3.6指定R/E，测试临时文件仅当前profile scratch/TMPDIR。不得修改RFC/SPEC/本文、模板、目录README、P/README.md、P/spec.md、旧研究/性能/输入/metrics及其测试、config.json、BOT/history/replay整树、spot/observation/runtime/Broker/launcher/config、Cargo.toml/Cargo.lock、UD全部文件、其他项目/profile。没有新配置仓库文件、requirements或依赖变更。若发现必须改只读路径，集中报主控，不自由扩展。

### 3.2 同核心纯估值与研究装配

`Phase1ModelValue`只含samples、sigma_raw、sigma、p_up。`DecisionCore::phase1_valuation(symbol,spot,strike,secs_left,floor)`读现有symbols活跃state，先按原MIN_VOL_SAMPLES判预热，再用同EwmaVol::vol和digital_up；无book/fee/market token/entered/Broker参数，不生成CandidateContext，不修改entered/market_revisions。sigma_raw只在已暖时为vol(0.0)，零值合法；sigma=vol(floor)。生产evaluate_phase1保留现有身份/输入/clock/30秒/revision等所有前置检查，再调用该helper并按原Reason映射返回，之后原side/候选生成不变。绝不能提前helper导致生产拒绝优先级变化。

研究History持一个DecisionCore::phase1（内部BtcArbConfig仍用生产固定默认值）和研究Config自己的floor。floor只传给纯估值helper，不改生产core.cfg或原floor(min_edge)。研究Config仅允许三个冻结floor；不得给AppConfig/ReplayConfig增加可调项或让history/1接受研究Config。M0/低/高分别构造三个进程和三个core，中floor就是M0，不再构造第四个中值core。

观察直接调用observe_phase1；key、epoch、samples、reset_reason从原core读取。source切换/回切、gap=300秒与>300、坏clock reset的实际顺序均由原方法决定，不能在Python维护另一份权威EWMA。正常round/day/fold不reset，原生进程从研究起点到终点连续；每个core只持BTCUSDT活跃state及当前round固定事实，禁止增长到全部历史round HashMap。过期round在planned_start推进后移除；同一round的身份/strike位级冲突立即协议失败，较旧round再出现即倒序失败，不以淘汰为由重新接受旧冲突。

### 3.3 新wire、时间单位和clock映射

所有新wire UTC时刻统一Unix整数微秒，后缀`_us`；不得把facade微秒availability向下截断成毫秒。seq为从0起逐事件加1的u64，bool不可代替整数。JSON UTF-8/LF逐行，单行≤64KiB，严格类型/必填nullable/有限数/重复键/未知递归键/未知版本均拒绝；不得先读成丢重复键的宽松map再验证。Rust typed struct/enum用deny_unknown_fields及严格字段解码；Python接收侧用拒重复键的object_pairs_hook，不允许NaN/Infinity。

协议schema_version固定 `btc-arb-phase1-history/1`；配置schema_version固定 `btc-arb-phase1-research-config/1`。这是新研究协议的第一版，不是原btc-arb-history/1或replay/2升级。

Config精确字段：schema_version、symbol（BTCUSDT）、window_start_us、window_end_us、as_of_us、sample_seconds（5）、half_life_secs（300）、min_vol_samples（20）、vol_floor（三值之一）、clock_basis（event_time_proxy）。无min_edge/order_usd/book/label/可调训练字段；三核除vol_floor外完全相同。from/to CLI必须与Config一致，A固定SPEC值。

Event精确外层：schema_version、at_us、seq、payload。payload只有两种：

| type | 必填字段（nullable仍必须有键） | 行为 |
|---|---|---|
| spot | type,symbol,price,bar_open_us,close_exclusive_us,available_at_us,prediction_source,actual_pair,source_dataset,price_kind,clock_basis | 实盘研究source只能Binance/BTCUSDT、binance-vision/trade_close/event_time_proxy；测试侧才显式标fixture并允许合法Coinbase/BTC-USD反例。close=bar_open+1秒，available=close=at，at是UTC5秒倍点，范围(start,end]；价正有限 |
| value | type,symbol,planned_start_us,offset,round_id,starts_at_us,ends_at_us,identity_available_at_us,strike,strike_available_at_us | planned_start为300秒网格，offset六值，at=planned_start+offset秒，planned_start在[start,end)；官方字段缺失用null，不造missing-*官方ID；非法类型/冲突不当作合法缺失 |

value为每个理论槽都发一次，即使缺身份/strike/spot；因此各核输出完整slot状态，不仅输出valued。缺失身份占位只用planned_start与offset，不当作官方身份。迟到身份/strike原微秒时间随value保留，History先按t检可得性再决定是否估值，不能因最终A较晚先用。labels、outcome、resolved_at、end_price、book/fee/订单等在两种payload和Config均非法。

proxy_clock只存在于phase1_history.rs私有适配：对合法spot t构造CheckTime.utc=t、elapsed_ms=(t-window_start_us)/1000；内部ObservationClock的request/received均为逻辑t、elapsed均为逻辑经过毫秒，source_at=None/MISSING/RECEIPT_BOUND。t对齐确保elapsed转换无损；官方availability仍以chrono微秒比较，不经这次转换。明确这是调用原源状态计算所需的代理clock投影，绝不序列化为真实request_at/received_at、不写controlled v2、不把逻辑零跨度称真实零延迟。公开输出只有proxy_observation_at_us、logical_elapsed_ms及clock_basis标识。fixture直接注入原observe_phase1的坏clock以验原方法；正式wire倒序/重复事件先作为协议失败，不在研究流中容忍损坏clock继续。

同刻顺序spot→value；同一时刻不接受第二个spot，value按planned_start/offset唯一，seq连续，at不倒退。只有两个事件类型，身份/strike是value携带的已经分离事实，不另建身份服务。使用不闭合/错秒bar或未知价格来源是协议失败，不降成普通MISSING_SPOT。

Value精确字段：schema_version、seq（原value事件seq）、planned_start_us、offset、at_us、round_id、starts_at_us、ends_at_us、identity_available_at_us、strike_available_at_us、strike、spot、bar_open_us、close_exclusive_us、spot_available_at_us、proxy_observation_at_us、logical_elapsed_ms、prediction_source、actual_pair、source_dataset、price_kind、clock_basis、source_epoch、reset_reason、samples、sigma_raw、sigma、floor_hit、secs_left、p_up、valuation_status。schema_version固定 `btc-arb-phase1-value/1`；有键无值用null，samples未观察为0不冒作一个return。floor_hit只在warm合法时按sigma_raw≤floor，p/sigma冷启动null。label不在此输出。

状态映射按SPEC §4.8：先MISSING_IDENTITY/IDENTITY_NOT_AVAILABLE，再ROUND_INVALID及MISSING_STRIKE/STRIKE_NOT_AVAILABLE的安全事实检查，再MISSING_SPOT/INPUT_INVALID，再CLOCK_INVALID/SPOT_STALE，再WARMUP，再VALUED/INPUT_INVALID数值。身份存在但官方期限不是300秒或不涵盖t、T<30秒时ROUND_INVALID；缺K单独MISSING_STRIKE，不把它笼统称旧MarketInvalid。当前网格无恰闭合spot则MISSING_SPOT，不能用旧缓存当S；旧有效state可保留到下一观察。原observe返回InputInvalid→INPUT_INVALID、ClockInvalid→CLOCK_INVALID、SpotStale或代理年龄拒绝→SPOT_STALE；代理不表达真实慢请求，不制造REQUEST_TOO_SLOW研究状态。无book的交易MissingInput、EdgeBelowMin、BrokerBlocked等不能映射成纯估值失败。所有组合以SPEC拒绝优先级和独立标签状态为准。

### 3.4 因果采样、逐日有界广播和完整消费

新入口的`iter_phase1_day`通过原iter_history_input发精确日交集请求，warmup_seconds=0、A固定、event-time-proxy。每日metadata/strike各最多一个UTC日轮次，先建立有界map并验证唯一round/planned_start/官方K。metadata可以物理提前读到，但value在t时仍检查其available_at_us；“已读入map”不等于“t已可用”。features按原facade顺序读完整，区分DATASET_ROUNDS和DATASET_KLINES，counts分开；不把features总数当秒线数。

所有1s bar均完整消费/校验/参与facade内容认证。仅当close_exclusive是5秒倍点时生成spot，恰取[t−1秒,t)close；其余秒线不更新EWMA。t=start无窗前bar，首个合法网格价才是首价。t=end允许消费/更新最后闭合bar，没有窗口外value。每个计划轮六slot无论有效性皆发value；bar缺失时照发对应value，MISSING_SPOT；下一有效价由原observe按真实dt生成一个return，长gap由原方法reset，不插值或补returns。缺源仍让数据资格失败，不能靠slot状态掩盖。

先处理t的闭合spot再该t的value，T精确为(ends_at_us−at_us)/1秒。5秒主序列跨轮/UTC日/所有折连续；首价不是return，21个有效价才形成20returns。新代码不得直接复用旧day_events的1秒发价/毫秒截断/旧missing-ID，也不改它以免回归旧结果。

一份事件序列只编码一次：同一bytes先写E/<run>/events.jsonl（独占新文件流式追加），再经旧_write_event向三个非阻塞stdin广播。每核单独保存实际成功发送bytes的SHA256/事件计数；任何一核写入/退出失败立即停止新增输入并使整批不完整，不能跳过它继续发布另外两核。

各原生CLI另对自己成功apply的原始LF行维护有界接收链H：H0为32个零字节，Hn=Keccak256(Hn−1拼接该完整行)，使用BOT已存在直接依赖alloy_primitives::keccak256（src/service/predict_fun.rs已有用法），不引新crate或误用SHA3-256。summary记录input_chain_keccak256及accepted_events/last_seq；三核接收链、计数相同，父发送SHA256相同，summary spots+values等于accepted_events，value输出seq/slot完整。Keccak链是实际接收内容身份，父SHA是发送内容身份，两种算法分列、不互称相等；Python无需另装Keccak库。

每核summary保留可复用的native_exit/spots/values/complete/error五字段，追加schema_version=`btc-arb-phase1-summary/1`、accepted_events、last_seq、input_chain_keccak256、max_active_rounds。输出行数须恰为values、单核value数等于计划slot数；各核config/slot/身份/spot/time/epoch/reset/samples精确一致，但异floor的sigma/p允许不同；中值M0不重复计算。旧_finish_core只承担其原有五字段/文件/native校验，新入口再做新增字段精确集合/类型/计数和接收链校验，不能把旧弱schema当完整新认证。

每天三流都耗尽后，调用verify_consumed并落原content/provenance manifest、coverage/missing/pending/conflicts、实际三流counts及各dataset counts。facade内部verify可能重新读底层页，这是原认证的一部分，不称“物理DB只扫一遍”；本设计“一次99日共享流”指一次逻辑研究读取供三core共用。保留每天开始manifest及verify后的身份，不用自算输出hash冒充源认证。任何非complete日/缺行/未决/冲突/认证失败均按SPEC数据工程不合格，不缩窗/补0/移动A。

每日仅保留当日contexts（六槽×当日计划轮）、身份/strike/标签map；立即流式写contexts.jsonl并释放。三核values.jsonl是磁盘流，不全量读成Python list；全流结束核native后，按排序slot将contexts与三个values做streaming merge，逐日写`native-samples.csv`及轻量fit日块，核任何多行/少行/未知字段/错seq。原生端max_active_rounds≤1（推进时淘汰旧轮），状态大小不随99日增长；Python内存只有当前日和固定候选/折/日统计。M1/B0/B1/B2不重开facade/核心。

### 3.5 离线拟合与统计实现

仅用标准库和R4已经使用的numpy，不依赖scipy/sklearn/matplotlib。R4记录该项目解释器的numpy=2.5.0、pandas=3.0.3、pymongo=4.17.0；本Design不运行解释器探针，不冒称当前import通过。T3实际测试/CLI在业务读取前记录当前importlib.metadata版本和必需导入；缺失即阻断，不安装/升级。pandas非新算法必需，版本作为已导入旧性能模块的传递身份保留。

训练输入从逐日已落M0抽取。每日fit块为numpy结构化`.npy`，allow_pickle=False/mmap_mode=r；字段为planned_start_us、offset、at_us、ends_at_us、label_available_at_us（int64），p0（float64），label_code（int8：UP=1/DOWN=0/DRAW=2/缺=-1），valued（bool）。label缺失时间用int64哨兵仅在该内部数组并由label_code先验排除，导出CSV仍null/N/A，绝不拿哨兵当真实UTC。每次最多map一个UTC日，不把所有npy/99日数值或dict一起驻留。fit函数只用该折t<C、ends≤C、label_at≤C且≤A、非DRAW及合法p；每轮有效mr在该次过滤后计算，轮内权重1/mr，全体再除有效轮数，使权重和1。B1从完整官方rounds.csv按唯一轮与同一截止过滤，不依赖M0是否有效或六槽重复。

Platt固定实现标识 `projected-newton-2d/1`：初值(a,b)=(1,0)，x=logitclip(p0)，z=a*x+b。数据项使用logaddexp(0,z)−y*z，sigmoid正负分支稳定计算；梯度为Σw(p−y)(x,1)+λ(a−1,b)，Hessian为Σw*p*(1−p)[[x²,x],[x,1]]+λI，λ=0.001。以numpy.linalg.solve求2维Newton方向；a=0且grad_a≥0时固定a只解b；其他情况试投影a=max(0,a+step)。非下降方向退回投影负梯度，不改变目标/正则。Armijo=1e-4、步长从1开始每次×0.5、最多50次回溯，失败即FIT_NOT_CONVERGED，不按验证结果重启。接受条件沿SPEC：有限可行、投影梯度无穷范数≤1e-8，最多500次外迭代；投影梯度定义为(a−max(0,a−g_a),g_b)。每次目标/梯度按日期、轮、offset排序归约，落objective/PG/迭代事实与优化器版本。空/单类/不收敛均显式FIT_*，不得以最后一步或identity代替。

八折Cj按SPEC公式从2026-09-21每7日递推，另以2026-11-16为末日冻结截止；单(a,b)服务各折全部六时点，不按偏移/状态另拟合；验证标签不进fit调用。不在首个截止前回填M1/B1。partial小窗/pilot没有42日训练窗，M1/B1为NOT_APPLICABLE，其完整拟合行为由隔离fixture测试，而不伪造真实单日拟合。

统计先按共同slot构造C10/C0B/C2/D02和含DRAW对应payout集：每个round先对该集实际有效槽平均，然后各round等权。六offset各自按round等权；complete-six是独立敏感性而非筛主分母。每个UTC日/比较/offset层只保存轮次损失和/有效轮数、slot原计数、校准桶可加权量，跨日/折/月用分子分母合并，不平均日率。不因p缺失提前return而丢官方DRAW/缺标签计数，估值/label/fit状态正交。

日/月、固定sigma_raw层与floor_hit、十桶/ECE、含DRAW兑付MSE、方向abstain/共同覆盖及参考价bps差依SPEC逐项计算；冷启动不算floor命中，M2分层用同槽M0 sigma_raw。B2仅direction列，p_up与概率指标N/A。模型方向用p精确比较0.5，评分clip不改原值。

每个统计期间按完整UTC日历生成PCG64(42)的1000×n int64日块索引；另独立同seed生成7日circular起点并拼接截至n，n≤7敏感性N/A。期间全部模型/时点/complete-six共索引；索引是小型日级矩阵，不保留行情对象。日级分子/分母数组用take/sum重算，零分母记无效不重抽；linear分位数。保存索引npz（无pickle）、日期顺序/hash与有效重复数；主要日块须1000均有效才可支持，诊断区间不完整标诊断不足而非自动否决主要证据。leave-one-day-out从总轮次损失和/轮数减单日量重算，不做额外模型回放。

判定按SPEC V1.1 §4.7三层实现：engineering_checks记录因果/消费/身份/分母/数值/拟合正确性与独立验证的硬门禁；primary_evidence只记录八折C10合并Brier差及日块区间/可用性，按其唯一四分类映射；robustness_diagnostics记录7日块、各折/时点、complete-six、logloss/ECE、日月贡献/LODO的原值/区间/适用性，反向或不支持主要证据的项目写diagnostic_conflicts。拟合允许N/A不冒充工程异常，但主要H2证据不足；所有诊断必须正确计算/披露，不将其结果拼成自动采纳AND。主要区间支持改善而存在诊断冲突时，保留“支持继续验证”及冲突原数值/解释，明确不得直接替换M0；不能换主指标、隐去不利折/时点或让H3冠军接管主比较。

报告/图表固定解释顺序：来源与工程资格→M0偏差（十桶过度/不足自信、六时点、因果sigma层、floor命中/既定两floor差、日月轮次损失贡献）→M1主要端点→稳健性及冲突→完整M2探索→效应大小/区间、复杂度成本、代理误差与经济适用性。只复用原定样本/分层，不新增模型/采集/扫描。M1的非减概率映射可能移动0.5分类边界但没有新增市场特征，校准改善不等于新增方向信息。复杂度记录两参数/九套拟合的wall与维护负担；close-mid误差无同期midpoint只能UNKNOWN，经济价值未验证，无可靠最小经济改善阈值不造数。无可靠M1改善保留M0、M2不选冠军部署，不因结果差追加半衰期/OBI/LLM/动量。1秒敏感性本轮NOT_EXECUTED，不默认第二遍99日或宣称采样稳健。

### 3.6 物理产物、字段落点与所有权

无生产数据库持久化、schema/索引/TTL。所有文件L0公共派生行情或L1工程身份，禁止凭据、连接串/环境全文/HTTP原响应/原私密资料/秘密摘要。T3真实输出叶目录精确为E/developer-small与E/developer-pilot；T4为E/validate-small、E/validate-pilot、E/full、E/audit。这些是不同的首次独占run；目录存在/失败后不得自动换编号重跑或从日志resume，须主控裁定新的精确路径。

启动前用lstat逐段拒绝symlink（含dangling）、验证批准根及路径组合，未知参数/版本/已有报告目标/叶目录冲突均在DB/core前拒绝。只允许沿批准R/E创建缺失的普通祖先目录，祖先存在不表示拥有其内容；叶mkdir(exist_ok=False)成功才获得该run归属。竞态mkdir失败时不进入failure写入，不碰原字节/条目。自身文件一律x/xb或Rust create_new，绝不覆盖旧目标；取得归属后的异常写本run partial，失败日志写错不能覆盖原异常。

| 精确相对run文件 | 触发函数 / 字段与校验 |
|---|---|
| params.json、identity-start.json、identity-after.json、commands.json | main/run_phase1；读取前冻结参数；记录实际argv/cwd/解释器、两个HEAD、显式源/测试/三文档/facade/依赖/新旧binary/锁/编译器身份；首尾逐项对比，缺必需文件拒绝，保留漂移两态 |
| events.jsonl、contexts.jsonl、rounds.csv | iter_phase1_day；前者只有label-free wire；后者逐日context与官方标签，rounds为唯一官方轮。共存不代表标签进入Rust；events/raw输出从不写原连接或环境 |
| source-YYYY-MM-DD.json | consume_day；原content/provenance、coverage/gaps/status、三流与dataset实际counts、verify结果、日发送hash/接收分段计数、open/consume/verify/write阶段wall |
| cores/M0/config.json、cores/M2-low/config.json、cores/M2-high/config.json | start_phase1_core；仅新研究Config，floor唯一差异，固定x创建 |
| 上述每个cores/<model>/command.json、values.jsonl、rust-summary.json、rust-stderr.log | 启动与真实RustCLI写入；后两输出不接受stdout成功回执替代；stderr仅程序固定公开错误，不复制原系统/数据库异常文本 |
| native-samples.csv | merge_phase1_values；宽表一slot一行，公共context与三个原生概率/状态；只对三个core原始值做键合并，不在Python重新定价 |
| fit-days/YYYY-MM-DD.npy、parameters.json | build_fit_days/fit_expanding；结构见§3.5；参数含训练截止、范围/轮槽/排除/最晚label_at/λ/a/b/J/PG/迭代/FIT状态/B1和input hash |
| samples.csv | materialize_samples；长表一slot×每模型一行，七模型均保留，缺值N/A；同一slot只一份实际归属period，不复制全窗视图产生重复样本 |
| statistics.json、comparison.csv、calibration.csv、daily.csv、monthly.csv、volatility.csv、floor.csv、coverage.json、verdict.json | compute_statistics；statistics是同源raw实体，CSV无损投影，coverage含理论/原因/共同分母；verdict分engineering_checks、primary_evidence、robustness_diagnostics、diagnostic_conflicts、research_verdict、effect_size、complexity_cost、proxy_error=UNKNOWN、economic_value_status=NOT_VERIFIED，不用诊断AND冒采纳 |
| bootstrap.npz、bootstrap-identity.json、leave-one-day-out.csv | bootstrap_statistics；索引按期间命名日块/7日块，日期顺序/seed/算法/shape/dtype/有效数及hash，LODO按日保留 |
| calibration.svg、strata.svg | render_figures；标准库SVG，仅从statistics.json对象投影；不装绘图库，不手抄图值 |
| run.json、failure.json | finally/failure；本run才可写，真实complete/error/UTC起止/wall/RSS/每核native/PID/发送与接收counts/hash/cleanup/资格/分类/产物hash；failure只在失败创建，无覆盖重试 |

short/pilot同样保留source/core/样本/基础统计，不声称八折可用，不生成正式正文；full才包含完整parameters/bootstrap/折等产物。fit-days、native-samples为必要可复算本地证据，非缓存服务，无自动删除或TTL。

full的complete仅表示本次计算/产物完整，engineering_checks.independent_validation在独立audit前为PENDING，research_verdict=null；保留primary_evidence与诊断原值，不提前宣称最终四分类已验收。audit读不可变full，给出独立硬门禁及按SPEC复算的最终四分类，publish仅在audit通过时把该分类与原raw同源渲染到唯一正文，不回写full/run或verdict。这不增加第五类研究结论，PENDING只是工程阶段状态。实际工程失败仍非零/不完整，不用PENDING遮掩。

samples.csv的schema_version=`btc5m-phase1-samples/1`，列按SPEC §4.bis.1原顺序逐字段对应：planned_start→planned_start_us；starts_at/ends_at/at/identity_available_at/strike_available_at/bar_open/close_exclusive/spot_available_at/label_available_at分别加_us；round_id/offset/period/fold/model/strike/spot/source_dataset/price_kind/clock_basis/prediction_source/actual_pair/source_epoch/reset_reason/samples/sigma_raw/sigma/floor_hit/secs_left/p_up/valuation_status/label/label_status/fit_status/parameter_ref保持同名。追加schema_version、proxy_observation_at_us、logical_elapsed_ms、direction四列，其余不隐藏丢弃。period为TRAIN_PREFIX、VALIDATION、LATEST；fold为0..7、末日8或不适用null；全99日描述是查询视图，不复制samples行。B0/B1/B2的sigma/epoch等不适用字段null，来源公共事实保留；M1继承M0输入与状态、另有fit_status/parameter_ref。B基准不可估值/不适用用明确NOT_APPLICABLE，禁止冒充三core的WARMUP。nullable文本为N/A，bool为true/false，整数UTC不写浮点；raw float至少17有效数字可往返。

native-samples宽表公共列为上述slot/来源/标签字段，模型局部字段以m0_、m2_low_、m2_high_前缀映射Value的epoch/reset/samples/sigma_raw/sigma/floor_hit/p_up/valuation_status；保存每核value_seq，保证能回查原JSONL。rounds.csv列为round_id、planned_start_us、starts_at_us、ends_at_us、identity_available_at_us、strike_available_at_us、strike、label、label_available_at_us、label_status；只有真实官方轮，缺身份的计划轮仅在样本保留，不造官方行。

所有统计CSV统一包含schema_version=`btc5m-phase1-statistics/1`、period、fold、offset（ALL或六offset）、model、reference、comparison_set、stratum、metric、numerator、denominator、value、lo95、hi95、valid_replicates、invalid_replicates、status；覆盖计数以metric命名逐项输出，校准另有bin/lower/upper/slot_count/round_count/weight/mean_p/up_rate列。daily/monthly另有utc_day/utc_month；不同维度表不相加重复视图。空分母value与区间null/N/A并有status，计数不混入概率值。stdout不成为第二数值源。

独立脚本audit只写E/audit/reference.json、vectors.csv、statistic-differences.csv、identity-start.json、identity-after.json、commands.json、run.json（失败另failure.json），不能改full输入/源码。真实small/pilot的vectors模式只读对应run，在该run下首次独占创建reference/，仅写reference.json、vectors.csv、identity-start.json、identity-after.json、commands.json、run.json（失败另failure.json）；它不修改原run.json。audit先绑定已完整full/run.json与所有输入hash，独立重算后记录pass/缺口；自算hash不是旧可信归档认证。唯一最终正文R/report.md由新入口publish读取full raw及该次独立audit生成，只有audit合格且输入首尾身份一致才用x创建一次。无临时第二正文或手工抄表；正文指标/区间8位小数、百分比4位小数、计数整数，图/CSV同源，M0诊断在M1/M2解释之前；主证据/冲突/效应/成本/代理误差UNKNOWN与经济未验证分栏，不改善仍可完整报告，坏数据不能排名。

### 3.7 资源、退出和清理

默认serial，每次只打开一个日交集；不启用BoundedPrefetcher、更不改prefetch深度。最多三个Rust子进程和一个当前日读取；读取在主线程执行，registry记录当前stage/day/started/finished，未启动日取消即不再打开。原facade每页pymongo.timeout(10)保留，新入口用剩余预算的更小timeout包围open/next/verify，并在每个边界先查deadline；不修改公共reader/连接默认。不把facade open数称物理query数。

Linux CLI在主线程安装SIGALRM/setitimer总业务deadline，SIGINT/SIGTERM进入有界取消，不在信号handler里做业务写入；外层finally停新增/关stdin/落partial/回收。每次_write_event还以min(总剩余,10秒)限制单核写阻塞；不只是循环前检查。normal EOF先关闭全部三个stdin，再用旧_finish_core逐个核native/summary，回收沿原_wait_child(wait4 WNOHANG)→terminate后10秒→kill后5秒→reap；不调用阻塞wait4(pid,0)。三个核预留合计45秒，再留15秒读任务/文件清理；清理总60秒上限。全T4另有总清理/交接余量见§5.3，不能为finally无界等待。

每次开始/日边界/写入批次/fit迭代/统计批次检查资源；运行中采样间隔上限1秒，监测本PID及三个已登记PID的/proc RSS和本run已写字节，不遍历他人进程/任意目录。父RSS≤512MiB；各Rust RSS≤256MiB；四进程RSS合计≤1280MiB。记录ru_maxrss为进程高水位、wait4 usage为相应子进程高水位，不能当隔离阶段峰值或以0代缺测；采样超限立即停新增并失败。有界单日map/contexts/fit块和三个core是内存结构约束，RSS只是额外实测上限。

small/pilot写盘≤128MiB/run，full≤4GiB/run；full前按pilot每完整日实际证据字节保守外推×99×1.5再加512MiB统计余量，必须≤4GiB，启动时statvfs可用量须再覆盖512MiB余量，否则停。构建产物不计研究run写盘额度，不能以此删除旧binary/证据。达到写盘/RSS上限按预算失败，不减少候选/只保存部分slot伪完成。

读取如果不能在deadline/清理内中断返回，记录active_read的unreclaimed/still_tracked且保持追踪，不宣称已回收、不启动后续日或后台续跑。serial没有实际预取任务时cancelled/reclaimed等为真实0；测试才通过受控read barrier验证不可杀读取语义，结束释放barrier并断言测试线程退出，不能遗留测试进程。异常优先级保留原失败和各cleanup_error；native无法观察写UNKNOWN/null，不由summary或父exit补0。

| CLI | 数字退出码（新入口冻结；不改旧入口） |
|---|---|
| Rust btc_arb_phase1_history | 0=完整输入/输出/summary成功；64=参数/Config/前检冲突；2=wire/顺序/身份契约失败；5=文件/写入/summary I/O失败。遇OS信号保存实际负signal/状态，不伪称这些正常码 |
| Python phase1_model_research.py | 0=本模式完整工程输出（不保证研究改善）；64=参数/版本/路径/输出冲突/前检；2=受控程序/协议或I/O异常；4=数据资格/批次完整性/summary/共同身份失败；5=wall/RSS/disk/读写预算失败；6=源码/依赖/binary/已落输入身份漂移；7=中断取消 |
| tests/phase1_reference.py | 0=指定输入的独立对拍完整通过；64=参数/路径/归属前检；4=数值/分母/拟合/载体/判据不符或证据不足以验收；5=预算失败；6=输入/候选漂移；7=取消；其他意外异常2 |

Python argparse默认error需在新入口显式映射64；真实native被观测为0但缺summary、错计数/布尔冒数等仍Python4，不能把native改写为4。数据缺口/未完成verify归4；普通FIT_EMPTY/SINGLE_CLASS/NOT_CONVERGED为统计N/A，保留后工程完整可exit0，但主要H2证据不足。拒绝/碰撞未取得归属时不落failure；测试原样校验旧目录所有条目与字节且DB/core=0。

### 3.8 G3与职责边界

本次实读文件行数：arbitrage.rs=1316、phase1.rs=1500、原phase1/tests.rs=2208、history_performance.py=1657、其测试=1963；旧history.rs=119、bin=61、history_research.py=381、history_input.py=154、history_metrics.py=155。行数来自文件工具，不按旧07-005 Design的历史行数推断当前待拆任务。

arbitrage.rs只加mod，phase1.rs仅同模型小提取与helper，保持各≤2400；新增研究wire/clock/测试在phase1_history.rs，不往原phase1/tests.rs堆实验。其职责仍同DecisionCore、增长原因直接为无book共享计算，独立审查由既有T4承担，不另起审查卡。原性能源码/测试及旧phase1/tests不改，无拆分义务被误列为当前工作。

新增文件以≤1200为常规目标；若同一既定职责实际1201–2400，T3交接说明真实行数/增长原因并由既有T4独立审查；本设计不授权超过2400。将达到2401或出现新平台/第二模型/第二Broker职责时先停报具体函数及路径，不能自由新建更多模块、压行或删测试求过。没有≥3600文件的豁免。

## 4. 实现顺序与阶段交接

1. T3先补隔离反例及测试侧独立A&S/erf/状态参考，记录RED真实原因；不回滚共享树造RED。记录当前HEAD/dirty及新旧候选身份，旧源Git对象/binary只读保全。
2. 只提取phase1纯计算helper、接新研究模块/bin，先证明同floor同输入交易路径精确复用以及legacy/生产拒绝顺序不变，再接Python因果5秒事件。新bin与旧binary路径分离。
3. 接逐日三流完整消费/广播/新输出强校验/有界资源与partial；完成真实main三核正常和故障消费者，不能mock run_phase1/_finish_core/reap后自证。
4. 实现冻结Platt/统计/图表、训练截止与独立复算，先用已知fixture测全八折及反例；再执行§5固定真实small/pilot，形成预算实测和完整证据。
5. T3完成只交工具/测试/small/pilot/候选SHA与预算。主控核真实候选与allowlist后恢复既有T4。T4先独立跑相同small/pilot及必要回归，通过预算准入后首次full，再离线独立audit/publish；不默认第二遍99日、不另建阶段或自行unblock。

T3总卡75分钟，包含工具/编译/定向测试/小窗/pilot/交接；时间不足保留增量和真实缺口，不能把超时改成完成。T4五小时包含首次研究计算与独立验证，不只是“验别人已跑完结果”。

## 5. 验证策略、命令与预算

### 5.1 测试边界与A矩阵

本Design阶段未执行以下业务命令、未读DB或拟合。新增测试/filters均明确标planned，只有T3落地后实际非零命中才算证据，不预报测试数量。fixtures替换外部facade行/clock/pipe读写或输出破坏边界，正常路径和反例均通过真实Python main→三真实Rust核心→合并/统计消费者；不得用整core或runner的自制成功结果验证自己。

| SPEC | 精确实现/测试落点 | 正常、反例与可断言证据 |
|---|---|---|
| A-001 | phase1_history.rs inline tests；test_phase1_model_research.py | 无book/fee纯估值、同phase1helper调用图；原evaluate仍走原gate，无候选/订单；旧history/1不冒名 |
| A-002 | 新iter_phase1_day→真实Rust | 闭合[t−1,t)与5秒网格；改变非网格价格只影响源hash不改变主EWMA；错秒/未闭合拒绝；同刻先spot，六T正确 |
| A-003 | Rust新History与Pythonslot/context | identity/strike恰t可用、t后1微秒拒绝但保slot；缺K/错轮/T<30/固定K位冲突；不能S当K |
| A-004 | 原observe_phase1→新History | 首价samples0、19returns暖不足、20returns可估值；跨轮/跨UTC日/跨fold连续；不补窗前价 |
| A-005 | 新模块inline测试直接原observe_phase1 | gap=300/大于300、短gap按真实dt、切源及回切、无效clock新epoch丢观察；reset_reason保留，无效价不加return |
| A-006 | events/Value/samples真实输出 | dataset/trade_close/proxy逻辑钟；无伪acquisition字段、无controlled v2冒名；fixture与canonical来源分开 |
| A-007 | main三核真实消费者 | 同发送SHA/接收Keccak链/slot/epoch/samples，中值就是M0；低/高允许不同；第三核故障不能被两个native0掩盖 |
| A-008 | 多日fixture+真实pilot | Rust max_active_rounds≤1；Python只当日buffer，RSS/disk/wall记录；连续core不日重启 |
| A-009 | CountingBundle+实际facade认证 | 缺秒/轮/日/pending/conflict/verify失败/manifest漂移精确Python4；保partial不补0/换A；三流与dataset计数明确 |
| A-010 | test_phase1_model_metrics.py训练消费者 | label_at=C可入、C+1微秒/A前不可入、round未结束排除、DRAW不训；改验证标签不变fit/B1/EWMA |
| A-011 | 同文件B1消费者 | 每唯一官方非DRAW轮一次，不依赖M0覆盖/六槽；零分母N/A、单类0/1合法 |
| A-012 | metrics与phase1_reference独立求解 | 固定λ/单(a,b)/轮权重，稳定目标/梯度/PG/收敛；参数代回/目标独立重算；不选验证分数 |
| A-013 | 同文件拟合失败fixture | EMPTY/SINGLE_CLASS/NOT_CONVERGED精确状态、p1=null、不可回填M0；代码异常不能伪装允许的拟合失败 |
| A-014 | 折分区与全samples消费者 | 八折逐C过滤，末日8单列，前42日不回填；验证仅无监督价格更新 |
| A-015 | 样本/coverage与独立重算 | 理论槽精确一次×模型；WARMUP和DRAW同时计；p=.5二元有效但方向abstain，B2无概率/交易胜率 |
| A-016 | 独立手算小例与raw样本重算 | 不同mr/缺槽/零槽，C10/C0B/C2/D02和complete-six；日/折率不直接平均；分子分母精确 |
| A-017 | 固定桶/分层/图表消费者 | 空桶N/A、floor等号、冷启动不算hit、M0因果层；SVG/CSV同statistics，不伪称纯基差/三分类 |
| A-018 | metrics/reference索引 | PCG64共享日历索引、保零样本日、n≤7的7日N/A、零分母不重抽；独立分子/分母与区间重算 |
| A-019 | phase1_reference与真实small/pilot | 独立递推EWMA+同A&S、另erf精确CDF；ATM/远strike/零波动/floor/预热/30秒边界；SPEC两类容差分列 |
| A-020 | test_phase1_model_research.py真实main | existing目录/文件/dangling symlink/mkdir竞态，所有旧字节/条目不变，DB/core=0；自身归属后失败保partial |
| A-021 | 真实三核pipe/输出边界故障 | 缺values/summary/字段、布尔/负数/错spots/错values、brokenpipe/写堵塞/非零/中断；断言Python精确码和每核observed native/PID回收，不能只code!=0 |
| A-022 | 首尾身份与旧回归 | 漂移6、未知schema/标签注入/错scope失败；旧binary SHA不变；同helper生产phase1与旧/1真实回归 |
| A-023 | 两角色相同small/pilot、T4full准入 | 相同A/窗口/三核/消费/预算；超限不开full；不重跑R4，不默认第二遍99日 |
| A-024 | audit/publish消费者 | 从full原样本独立复算工程/主证据/诊断三层与四分类；主Brier日块支持但7日/时点/logloss等冲突的反例须保留主证据原判与风险，不复活旧AND或无条件替换M0；M0诊断先行、效应/成本/代理误差UNKNOWN/经济未知、H3探索/交易N/A和先验暴露 |

phase1_reference.py不import phase1_model_metrics/research/history_performance或读取正文倒推原始结果；只用标准库math/csv/json及numpy。参考EWMA直接按已知公式独立递推，A&S与erf双路径，生产计算不调用参考。独立fit用单独实现的2×2解析Newton/边界KKT与目标检查，而非调用生产optimizer；从raw样本重新构造训练权重和标签截止，按SPEC独立求解容差核9套冻结参数及预测/目标。统计从samples原始行重建轮次分母/日量/PCG64索引/区间/LODO/判据，不读取comparison给自己当期望。Reviewer审查其数学与抽样原始向量后运行，开发者自测不是独立PASS。

audit的模型数值证据复用已独立small/pilot vectors及full首日精确前缀；另审查跨日/跨折状态与接收链，不默认用参考程序重放全部99日价格，更不启动第二遍Rust/DB。全样本独立重算仅指标签/训练/评分/分母和统计；发现接线缺口才补受影响价格范围，超出原预算停报，不为整理报告再扫全库。

真实small为[2026-08-10T00:00:00Z,2026-08-10T00:05:00Z)，pilot为[2026-08-10T00:00:00Z,2026-08-11T00:00:00Z)，均A=2026-11-17T15:00:00Z、warmup0；选择首日是为了与full前缀精确对拍，而非挑有利一天。small只有一个计划轮；pilot理论288轮/86400秒/1728槽，实际须核facade。所有完整输入下，spot数=秒线数/5，value数=计划轮数×6，总事件为两者之和；这些额外数值由真实CLI计算/核对，不用未执行算术展示冒充实测。full理论值仍为SPEC的99日/28512轮/8553600秒线/每模型171072槽。

### 5.2 固定原生命令矩阵

命令中P/BOT/R按§2精确路径展开；不能把这些缩写当另一个cwd。本文代码段是后续待实现/待执行命令，不是本卡实际运行记录。Python全部用ROOT/.venv/bin/python（相对ROOT写.venv/bin/python），不使用BOT私有venv、系统python或任意inline/execute_code/外层subprocess runner。Cargo仅现有缓存--locked --offline，不安装/改锁；不运行--ignored或原bot。每条记录真实argv/cwd/UTC起止/native exit，不能拿管道/工具启动回执当测试退出。

cwd=BOT，离线定向构建/回归：

    cargo build --locked --offline --bin btc_arb_phase1_history
    cargo test --locked --offline --lib bot::arbitrage::phase1_history::tests
    cargo test --locked --offline --lib bot::arbitrage::phase1::tests
    cargo test --locked --offline --lib bot::arbitrage::history::tests
    cargo test --locked --offline --lib bot::arbitrage::replay::tests
    cargo test --locked --offline --bin btc_arb_phase1_history
    cargo test --locked --offline --bin btc_arb_history

上述 `cargo test --locked --offline --bin btc_arb_history` 仅为受保护旧CLI的编译/链接兼容检查：该bin当前没有测试，允许0 tests，但必须native0；它不计为行为测试命中或行为回归通过，也不授权向旧bin添加测试。旧history行为由已列 `cargo test --locked --offline --lib bot::arbitrage::history::tests` 验证。

其余行为测试要求native0且对应filter非零命中，无ignored联网测试。新模块新增冻结综合fixture `bot::arbitrage::phase1_history::tests::pure_valuation_matches_phase1_and_keeps_legacy`（planned），证明生产helper与研究同值/无book/不改legacy；行为测试不以0 tests的exit0通过。新Python消费者测试直接执行实际新binary/固定argv，不用fake core；故障可在外部pipe/输出读取/summary边界施加，不替换core计算。若编译或公共调用影响超出此矩阵，先确认具体依赖再补受影响既有入口，不借此重跑全仓。

cwd=ROOT，Python新增及必要既有薄适配回归（单条）：

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/test_phase1_model_research.py skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/test_phase1_model_metrics.py skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/test_history_input.py -q -p no:cacheprovider

期望native0，真实命中数以实际日志为准。旧R4源码/测试/高层调用不改，不重做其139项全套或三个性能CLI；低层复用在新main反例中真实覆盖，不拿既有性能PASS替代新研究。

新Python主CLI固定选项：`--mode {small,pilot,full,publish} --as-of UTC --evidence-dir PATH`，publish另必需`--source-dir PATH --audit-dir PATH --report PATH`；full另必需`--pilot-dir PATH --independent-pilot-dir PATH --remaining-seconds INTEGER`。其他模式拒绝这些附加参数，所有模式拒绝--start/--end/--floor/--strategy/--prefetch/--live等扩权项。窗口由mode固定；remaining-seconds只收紧剩余预算，不可提高硬上限；T3不允许full/publish，T4按Gate才允许。路径严格限定前述精确目录，tests中仅注入隔离根作为外部filesystem fixture，不改生产常量。

cwd=ROOT，T3两次真实读取：

    .venv/bin/python -B skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/phase1_model_research.py --mode small --as-of 2026-11-17T15:00:00Z --evidence-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/developer-small
    .venv/bin/python -B skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/phase1_model_research.py --mode pilot --as-of 2026-11-17T15:00:00Z --evidence-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/developer-pilot

T4先运行同两命令，仅evidence叶分别改成`validate-small`、`validate-pilot`；这是预声明独立验证，不是冲突后自动换路径。相同小窗/pilot的源manifest/输入/所有native-samples列精确比较（运行wall/PID等另列），full第一日再核同前缀。不要求warmup重启不一致的窗口互相比概率。二者任一非0/预算不满足不开full。

full固定argv模板如下，`<实际剩余整数秒>`必须由T4根据自身卡deadline填入并落commands.json；这是观测预算，不是可任选业务参数，也不能复制18000忽略前置已耗时：

    .venv/bin/python -B skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/phase1_model_research.py --mode full --as-of 2026-11-17T15:00:00Z --evidence-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/full --pilot-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/developer-pilot --independent-pilot-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/validate-pilot --remaining-seconds <实际剩余整数秒>

期望native0且complete/数据资格/三core/消费/hash/样本/统计均合格；单个exit0不等于研究支持。full只读一次逻辑99日；M1/统计就在同一模式离线做，不再访问DB。full尚不创建最终report。

cwd=ROOT，T4独立重算及唯一正文生成：

    .venv/bin/python -B skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/phase1_reference.py --mode audit --source-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/full --evidence-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/audit
    .venv/bin/python -B skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/phase1_model_research.py --mode publish --as-of 2026-11-17T15:00:00Z --evidence-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/full --source-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/full --audit-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/audit --report data/reports/2026-11-18-btc5m-phase1-model-research/report.md

publish是只读完整full/audit并独占创建report的一次派生动作，明确不重新创建/取得full目录归属、不更新full/run.json，不在失败时给已完成full注入failure；它使用report的独占文件归属，冲突/漂移失败无覆盖。原full/audit immutable，发布结果/exit登记Kanban，不创建第二运行状态源。audit0要求SPEC紧容差/精确状态和主要统计/判据全部验证；数据不合格full不可进入publish。publish正常负研究结论0，工程异常非0。

原生子进程argv由新入口固定为新binary `--config <本核config.json> --input - --output <本核values.jsonl> --summary <本核rust-summary.json> --from-us <mode起点整数> --to-us <mode终点整数>`；Rust只接受这些选项（以及--help），不读取业务运行配置。该模板实际展开值须落每核command.json并记录observed native。真实small/pilot的独立参考必须使用下述固定vectors命令读对应真实events/values；新增pytest另测其fixture/反例，不能以纯函数测试冒充真实对拍。T3分别对developer-small和developer-pilot运行（这里列small原生命令，pilot仅替换两个对应叶名）：

    .venv/bin/python -B skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/phase1_reference.py --mode vectors --source-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/developer-small --evidence-dir data/reports/2026-11-18-btc5m-phase1-model-research/evidence/developer-small/reference

T4同样使用validate-small及validate-pilot对应路径，预声明独立创建各自reference；模式不连DB/不启动子进程，业务120秒、清理60秒上限，RSS/写盘沿small上限。vectors要求全真实输入独立递推EWMA/A&S/erf、按slot对拍三floor/epoch/samples/预热/剩余时间；native0且非空向量才通过。参考结果与源码身份绑定，不反向参与主样本生成；full准入同时检查两个pilot/reference均通过。

格式/身份命令仅原生精确路径git status/rev-parse/diff --check与sha256sum，逐项列实际变化路径；新增untracked文件用`git diff --no-index --check /dev/null <精确文件>`单独检查（存在新增差异native1且无空白诊断不是测试exit0）。定向格式检查不得全仓重排。cargo --offline仅限制依赖下载，不证明业务网络为0；离线测试只接fixture，真实研究仅现有facade合法只读连接，无交易/HTTP重采/签名/钱包/外发。

### 5.3 pilot准入、T4子预算和停止

这些为本次资源上限/保守估计规则，不是稳定耗时承诺。原提案45–75分钟/2–4小时和R4单日27.4秒均不当最新phase1实测。T3/T4各small业务上限120秒、pilot业务上限180秒，均另含清理上限60秒；small及其vectors通过才开pilot。pilot计时包括身份/三核启动、三流open/完整消费/verify/hash、编码/三核写入、native收尾/全量value合并、样本写盘及基础统计，不只量Rust计算；分阶段wall与峰值口径分别记录。

T4五小时（18000秒）固定分配：接线/定向回归/独立small+pilot≤2700秒，首次99日价格/三core/合并及fit日块≤10000秒，M1九套冻结拟合/统计/图表≤1800秒，独立数值/拟合/主要统计及最终正文核验≤2400秒，清理/交接预留300秒；合计17200秒，另800秒未分配安全余量。不可把未用余量挪成提高任何子上限或延长卡deadline。实际开始较晚时以剩余时间更紧约束。

令t_p为开发pilot与独立pilot“上述完整业务wall秒数”的较大值，预先固定全99日流/合并成本估计 E_flow=ceil(1.5×99×t_p+300秒)。300秒覆盖全窗固定开销；乘完整pilot（含冷启动开销）是保守外推，不从最快一阶段推倍率。启动前同时要求：两个pilot都数据/接线/参考合格；E_flow≤10000秒；预计E_flow+1800+2400+300+800秒不超过T4实际剩余秒；RSS/disk预估合格且所有必需测试通过。任何不满足立即停止并报告，不改A/99日/三floor/采样/serial，不自动加时/减窗/提高资源。

小窗/单日不能证明全99日稳定：full运行仍有全局/每阶段deadline、资源采样和每日消费闸门。flow超过10000或预留统计/独立复算时间不足时停止，不把已跑前缀当完整研究；拟合/统计超1800同理。若full完整而audit超限，保留完整研究样本但独立验收未完成，卡仍不能PASS或伪造报告。源数据/标签与预期不符即数据工程不合格，不为凑预算删除verify。

T3/T4均每几分钟Kanban heartbeat，长研究至少每小时一次；记录业务子进程PID与命令，工具层后台仅在运行固定获准CLI确有需要时使用，不能用后台续跑跨卡预算或规避被拒动作。进程工具的启动回执/外层状态不是native成功。

## 6. 风险、回滚与拒绝恢复

| 风险 | 处理 / 停止 | 回滚与残余边界 |
|---|---|---|
| 旧core/生产gate被提取改变 | 同floor精确对照、原phase1/旧history/replay回归；生产检查顺序保持 | 仅主控确认后对本期精确源码定向处理；不reset/stash/clean/checkout，不动他人dirty |
| proxy时钟或trade close被误解 | 样本/正文强制来源/逻辑clock声明，真实acquisition未知 | 不推断严格PIT、midpoint、Chainlink同源或收益 |
| 延迟标签/缺日/消费或身份漂移 | C与A双过滤，完整manifest/首尾/hash；失败partial/非零 | 不换窗/补0/造标签/重新采集，不发布模型排名 |
| 不收敛/单类/无改善 | 固定FIT状态和四类裁定，允许负科学结论 | 不增加迭代/变正则/择优重跑，不替换生产参数 |
| 资源超界/pipe阻塞/读取未回收 | deadline/逐核native与取消回收事实，不把健康核当整批成功 | 保留自身partial和旧证据；不后台续跑或重开并发读取 |
| 旧binary证据身份丢失 | 新bin不同路径；旧SHA首尾保护，旧源码Git对象保留 | 不覆盖旧报告绑定文件后自称同身份，不从新归档自认证旧可信历史 |
| 数据仅本地保存 | 仅R/E，raw与引用完整，无自动TTL/删除/上传 | data被Git忽略不表示提交、远程备份或公开许可 |

安全拒绝以工具返回为准，停被拒动作及依赖；可选日志/展示可记NOT_EXECUTED/OMITTED后继续独立已授权文档/检查，不换工具/包装/解释器/路径/后台/主控代跑等价动作。必需验证入口缺失则保留缺口并block，不能削验收求绿；普通参数/路径/patch并发保护错误仍可按原授权定位修复，不当作安装授权。本文不新增Activation/服务或生产副作用门禁。

本卡可选shell算术展示（额外推导各模式事件数）被Tirith拒绝，未执行且不重试；已在Kanban记录。本文只保留明确计数公式供后续真实CLI计算，SPEC已冻结的理论计数有正式来源。T4预算合计的先前独立命令实际native0，17200/800已核；拒绝不冒充测试结果，必要设计检查不依赖被拒展示。

## 7. Design自检与交接

本T2仅交付RFC/SPEC/Design三份独立V1.1文档：实体/互引/哈希、Pascal新决策与旧判据闭合、真实接缝/逐文件allowlist/G3、A-001–A-024、字段/失败/退出/资源/命令静态核对。未读业务DB、未build/cargo/pytest、未运行small/pilot/full、未拟合或验模型优劣；所有planned测试须后续实测。

本卡完成交预建独立只读Design Gate t_780aa76c核三文档V1.1及Pascal决策闭合；该卡已成为既有T3 t_282d52cb真实parent。独立Gate及主控实体/SHA核验后，主控才将§3.1逐文件allowlist与§5命令/预算同步既有T3/T4并决定恢复；两卡仍blocked，本卡不解锁、不自签、不新建图。旧T1 V1.0完成不代表此次修订已获通过。

T3/T4交接必须登记：实际changed_files/G3、两个HEAD与工作树SHA、新旧binary/SPEC/Design/参数/依赖首尾身份，真实命令/cwd/native退出、每核与读取清理状态、三流认证/理论与共同分母、pilot wall/RSS/disk及准入估计、未覆盖项/失败原因。完整验收只在既有独立T4完成，主控最后Closeout。发现真正业务冲突/超allowlist/不可用依赖或预算不能容纳，一次列全交主控；不得把业务选择留给实现者或自行降门禁。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-11-18 | 冻结原phase1纯估值提取、新label-free微秒协议/隔离bin、三core连续共享/低层复用、逐文件范围/G3、现有numpy拟合/统计、真实small/pilot/首次99日与独立复算命令、产物schema/所有权/退出/预算；仅设计未实现 |
| V1.1 | 2026-11-18 | 按Pascal新决策同步上游V1.1、M0诊断先行/三层判定与冲突载体、效应成本/经济未知和停手；主控按独立Gate F-01澄清旧bin命令仅编译兼容检查、允许0 tests但不计行为测试，其余行为测试仍须非零命中；交独立Gate复核，不改固定实验或工程硬门禁，不实施/跑库 |
