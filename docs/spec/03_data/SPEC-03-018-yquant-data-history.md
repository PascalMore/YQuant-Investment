# SPEC-03-018: yquant-data 迁移与 BTC5m 官方历史摄入契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | V1.1历史基线 + V1.2 Step1/2已裁定；待新候选独立Verify及生产补齐 |
| 作者 / 更新 / 任务 | YQuant Principal；2026-11-11 Asia/Shanghai（UTC+08:00）；`t_2f744e19` |
| 来源 / 设计 | [RFC-03-018 V1.1基线及§8 V1.2](../../rfc/03_data/RFC-03-018-yquant-data-history.md)、[DESIGN-03-018 V1.1基线及§2.9 V1.2](../../design/03_data/DESIGN-03-018-yquant-data-history.md) |
| 唯一裁定 | [correction-plan.md](../../../data/tasks/active/2026-11-11-yquant-data-history/correction-plan.md)；本版主正文替代旧版冲突条款 |

## 1. 固定边界

UD 自有读写目标为同实例 `yquant-data`，TA-CN 原始数据只读 `tradingagents`；认证源沿用原合法连接，不从业务库名推导。不改通用 MongoReader/Writer 默认、全局 env、旧行业算法/R3；本 SPEC 仅替代旧契约的 UD 同库/认证耦合部署限定。
主窗口 `[2026-08-10T00:00:00Z,2026-11-10T00:00:00Z)` 固定 92 日、7948800 秒槽、26496 名义五分钟槽；UTC 半开边界，秒线按 open_time_us、round 按 starts_at_us 归属。输入显式 UTC，拒绝 naive/非零 offset；warmup_seconds 非负默认 0，预热覆盖单列，不计主窗口分母。
当前 52 路径候选复用，代码/测试的精确剩余范围见 Design；不把旧待建清单当现状，不迁位已迁测试。C1–C5 零真实 DB/HTTP/凭据/调度；P1/P2 只执行冻结 CLI，P3 独立只读核验，主控最后安装 job。

## 2. 迁库交付契约

仅从 `tradingagents` 复制同名五集合至 `yquant-data`：
`03_data_ud_sector_ranking_daily`、`03_data_ud_query_audit`、`03_data_ud_market_sector_snapshot`、`03_data_ud_market_sentiment_snapshot`、`03_data_ud_stock_capital_flow`。

- 主控列已知 UD 写入口/责任进程、窗口起止和操作者不并发提交 UD 写的确认。没有静默签名/hash/时效 token，也不要求全局外部 writer 不存在证明；锁仅拦已接入入口，不冒充全局静默。
- 执行时只读 inventory 本次五集合与实际 metadata；发现未知 UD 集合报告，不通配复制、不自动扩清单。源仅 find/list，目标仅缺失集合/索引初始化及 insert，不 drop/delete/rename/回写源或覆盖冲突目标。
- 保 `_id`、BSON 类型、全部字段与原时间；同 ID 同内容 skip，不同内容或业务唯一键不同 ID STOP。复制前后源与目标逐 typed ID 全内容对比，不以 count/抽样替代。
- options/索引按实际业务语义保存：名称、键顺序/方向、unique、sparse、partial、collation、TTL 等存在才核；服务端 UUID/ns/v 等排除并说明。ranking `uniq_dataset_date_sector` 键为 `(dataset +1,trade_date -1,sector_code +1)`；audit `fetched_at_ttl(fetched_at +1)` 保 31536000 秒。
- 非 TTL 源漂移必须 STOP。TTL 仅豁免原 fetched_at+TTL 在观察结束前已过期且实际消失的 ID 子集；剩余内容 exact-match，不能重置时间、关闭 TTL、人工删数模拟自然过期。
- 当前规模的有界逐 ID 摘要足够；已有 SQLite 内部索引可留，不强制该设施或任意 BSON/任意集合兼容。实际不支持的 options/TTL/结构 STOP 报告。
- 核验后才使用新装配；切换前失败保留目标与摘要，源不动；切换后已有新增量不得直接切旧丢数据，留存增量并由主控决定修复/另行授权重放，不自动反向写或双写。
- 权限仅报告具体 `namespace/action` 缺项；源 find/list，目标 createCollection/createIndex/find/insert，摄入另需 update，历史 reader 仅 find；audit 保独立身份/原认证源，不自动建用户/角色或升权。

## 3. 两源存储与精度契约

所有新历史/进度 schema_version=1，无 TTL；旧缓存/审计 TTL 不改。L0=公开市场值，L1=运行/本地引用，L3 凭据禁止落盘。业务时间 int64 UTC 微秒、价格/数量 Decimal128，读取 Decimal/无损字符串；NaN/Inf/不可表示精度拒绝，不经 float。本地观察时间向上毫秒或保精确微秒，不提前可得性。

| 对象 | namespace / 唯一键 |
|---|---|
| rounds | `yquant-data.03_data_ud_predict_btc5m_rounds`；`(source,series_slug,round_id)` unique |
| 价格 | `yquant-data.03_data_ud_binance_spot_klines_1s`；`(source,market_type,symbol,interval,open_time_us)` unique |
| 日/流进度 | `yquant-data.03_data_ud_history_ingestion`；稳定 `_id`，`(kind,dataset,utc_date)` unique；stream.utc_date 显式空字符串 |

共用字段保留 `schema_version,source,fetched_at,raw_ref,raw_sha256,record_sha256,first_observed_at`；raw hash 为原字节 SHA-256，record hash 为固定业务投影摘要。相同事实重试不改首次观察时间；观察时间仍参与研究可用性摘要，不因排除于业务 record hash 而丢弃。
raw 根 `data/source/predict-btc5m-history/`：Predict `predict.fun/<抓取UTC日>/<sha256>.json`；Binance `binance-vision/<行情UTC日>/<官方ZIP名>/<sha256>.zip`，另存官方 CHECKSUM 与原始/缺口引用摘要。先完整校验再原子落盘，不覆盖不同 hash，不自动清理；不得保存请求认证头/秘密/原连接异常。

### 3.1 Predict

只用官方 `GET /v1/series/btc-updown-5m/rounds?status=ENDED&first=100&after=<opaque>`，新到旧游标闭合覆盖窗口；重复游标、反向排序、空页/空 LoadResult 不证明完整。pending 仅按已知身份回查官方市场/类别详情及 `GET /v1/markets/status-logs?ids=...`（每批≤100），不访问账户/订单/签名端点。
category.id 精确十进制文本→round_id，与 market_id/condition_id 分开；series_slug 固定 btc-updown-5m，duration=300000000 微秒、feed_symbol=BTCUSDT，拒绝 ETH/15m/多市场歧义。variantDetails.upDown/crypto、variantData 与对应 market 同语义非空值必须一致，不以优先级掩盖冲突。
保留身份 `round_slug,market_id,condition_id,published_at_us`；时间/价格 `starts_at_us,ends_at_us,start_price,end_price,price_feed_provider,price_feed_symbol`；原状态 `category_status,market_status,trading_status`；结算 `settlement_state,official_outcome,resolution_evidence,resolved_at_us`；观察/回查 `start_price_observed_at,label_observed_at,next_check_at`。缺官方 publishedAt 记 null，不猜历史发布时间。
ENDED 仅表示结束。resolved 需同 market 的最终 RESOLVED 日志时间、明确 UP/DOWN/DRAW 官方结果、正数 start/endPrice、身份一致；缺证据 pending，REMOVED/404/410 unavailable，矛盾 conflict。DRAW 只能据明确官方终态；既有单一明确DRAW结果继续有效，官方双WON的Flat/50-50联合证据例外见§8，不能仅凭相等价格、规则描述或proposedOutcomeId造标签。已归档真实平局可作来源证据，默认测试须使用自包含静态摘录，不依赖ignored原档存在。
同键相同事实 no-op，pending→resolved 原行补齐且保旧 raw 引用；身份/事件时间不得变，已接受终态关键事实冲突不覆盖。标签与 endPrice 不进特征。

### 3.2 Binance

固定 `https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1s/BTCUSDT-1s-YYYY-MM-DD.zip` 及 `.CHECKSUM`，无 REST/monthly/futures/第三方后备。必须 checksum、ZIP CRC、成员/CSV schema 通过；404 记 ARCHIVE_NOT_PUBLISHED_OR_MISSING，不猜发布日期 SLA。
12 列依序映射 `open_time_us,open,high,low,close,volume,close_time_us,quote_volume,number_of_trades,taker_buy_base_volume,taker_buy_quote_volume,ignore`；另存 `close_exclusive_us,source_timestamp_unit='us',source_row,market_type='spot',symbol='BTCUSDT',interval='1s'`。`close_exclusive_us=open_time_us+1000000=close_time_us+1`，open 必须秒边界且属本日。
检查列数/明确表头、严格时间顺序、自然键重复/冲突、正价格/非负数量交易数、`low<=min(open,close)<=max(open,close)<=high`；不能补值/插值/前填或默设 0。官方零量 candle 可存。已接受秒线非等值修订保新 raw 并报 conflict，不自动改历史事实。

## 4. 日进度、续跑与退出

dataset 固定 `predict_btc5m_rounds`、`binance_spot_btcusdt_1s`。日 `_id=day/<dataset>/<YYYY-MM-DD>`，保 `window_start_us/window_end_us,state,counts,gap_manifest_ref,raw_manifest_ref,content_sha256,last_attempt_at,next_retry_at,error_code,updated_at`；流 `_id=stream/<dataset>`，保 `ingestion_start_us,enumerated_through_us,complete_through_us,scan_cursor,scan_upper_us,scan_lower_us,updated_at`。
raw→transform/validate→bulk→exact-target 读回→日内容/覆盖核对→日 complete→连续水位。partial bulk、ack 不明、进度失败不提交 complete；中断 running 按未完成重放，自然键去重。每批价格≤5000、Predict 页≤100；不整窗载入内存。
日 state 为 pending/running/complete/gap/failed/conflict。价格 complete 需 86400 个有效唯一秒槽、checksum/schema/读回正确、无冲突。round 枚举闭合、身份/startPrice/官方标签完整且无未解释时间缺口/冲突才 complete；实际轮数与名义槽分别报告，不拿“有几条 resolved”代表全日完整。
水位从显式 ingestion_start 按连续 complete 日前进，遇 gap 停；枚举边界不等于结算完整，联合完整水位取两源最小值、任一 null 则 null。已完整日后发现冲突需撤回相应完整水位。
backfill 固定主窗口，按日有界续跑；daily 要求已初始化，以实际启动 UTC 当日 00:00 为 exclusive cutoff，处理最近完整日、未完成日/缺口及到期 pending，不每日重扫三个月。游标绑定原窗口，可复用已存页链恢复；失效在有界缺口内重扫，不能跳缺口。
每源有独立日/请求/时间上限，一源普通故障或 Predict 401/403 停该通道，不切凭据，另一源有预算仍执行；共同 DB/namespace 权限失败可停受影响通道。不要求复杂公平调度器。HTTP 默认30秒/最多3次，Mongo每操作10秒，每源默认7日、总墙钟1800秒；429/5xx 退避受预算，认证/schema/checksum/conflict不自动重试。
同机写入口共用非阻塞 flock；BUSY 不发请求/不开写。plan 及未带 --apply 的摄入只规划，不下载/DDL/初始化；verify 只读。原始/内容摘要与必要断点保留，不建 runtime/审批或时效令牌。
退出：0=显式计划成功或本次目标两源完整；10=gap/pending/backlog/预算截断；20=参数/NOT_INITIALIZED/认证/权限/schema/checksum/conflict/readback；30=BUSY；40=timeout/已知中断。conflict 不能仅报普通 pending。报告各源实际覆盖/未处理、错误、原始引用、内容摘要、各水位及联合水位；不因失败吞掉错误具体 namespace/action。

## 5. 稳定窗口窄读取

保持 facade 签名 `read_btc5m_history(start_utc,end_utc,*,warmup_seconds=0,as_of_utc,availability_mode='observed',expected_manifest=None) -> HistoryWindow`，只读已存数据，无网/写/DDL/旧库 fallback。round 按 `(starts_at_us,round_id)`、秒线按 open_time_us 稳定分页；主窗和预热单列，缺口返回 partial 而不缩分母。
使用前提：读取至消费完毕不主动安排本任务写入，操作者确认该窗口无并发 UD 写；已知发生写入就丢弃稳定样本结论，换稳定窗口重读。一次窗口/业务内容摘要包含数据、来源、schema、排序、窗口、as_of、模式、影响可用性的观察时间与覆盖；同内容同参数 hash 一致，expected_manifest 不符报 DATASET_CHANGED。raw 引用另作 provenance，不需通用版本平台。
HistoryWindow 保分离 features/round metadata/labels、coverage/missing/pending/conflicts 和 availability_assumptions；元数据白名单不泄露 settlement_state/endPrice/outcome。只返回 available_at_us≤as_of 的行；使用特征还须遵守逐行可得时间，不因 as_of 很晚提前使用后验值。

| 内容 | observed 默认 available_at | 显式 event-time-proxy |
|---|---|---|
| OHLCV | max(close_exclusive_us,first_observed_at) | close_exclusive_us |
| startPrice | max(starts_at_us,start_price_observed_at) | starts_at_us，缺历史发布时间警告 |
| 身份 | 不早于 first_observed_at 及已知 published_at_us | published_at_us，缺失则 first_observed_at |
| 官方标签/endPrice | max(ends_at_us,resolved_at_us,label_observed_at) | max(ends_at_us,resolved_at_us)，无结算时间仍不可用 |

旧 raw 无可信抓取时间只能用当前实际观察下界，不用 mtime/事件时间伪造。observed 回填在历史时点可能无可用数据；所有模式均不得宣称 strict PIT/live 等价、成交或净收益证明。Binance OHLC 不是 Chainlink oracle、盘口/bid/ask mid。
严格并发快照、逐页重复核验、三流消费确认协议、通用可得时间调度器不再是首版验收前提；候选正确增强可保留原 API/内部实现，不要求新机制或强拆。薄研究适配不改旧 research/Rust/策略模型。

## 6. 三项交付的可计算验收

| 交付 | 最小可计算断言 | 证据 |
|---|---|---|
| 工程 | 双库/认证隔离与真实句柄 guard；raw/checksum/微秒/Decimal/自然键/标签底线；失败注入后 complete 不越 gap，重复同事实业务键/摘要/观察时间不变；稳定窗重复摘要一致；默认无网/真实 DB | C3 定向测试及最终一次合并回归；C4 独立测试、C5 独立审查；不拿旧1750当新候选PASS |
| 迁库 | 五集合（含空）逐 ID missing/extra/different/非TTL source_drift=0；实际 options/index 等价，TTL 差异可逐 ID 解释；源零本任务写、目标零覆盖，缺权限逐 namespace/action 列明 | P1 前后 inventory/内容摘要/命令范围与目标读回，P3 独立只读核验 |
| 历史覆盖 | 价格 valid_unique/7948800 及缺秒区间；round 实际身份/重复/缺口/名义槽分列；resolved 标签/pending/unavailable/conflict 分列；每日实跑各源结果与连续水位可复核 | P2 首日资源实测+92日 raw/CHECKSUM/页链/DB内容核验+daily；P3只读复核，首日/fixture不替代92日 |

最终完整要求价格秒槽齐、round 枚举/身份及官方标签齐、无未解释缺口/冲突/pending、完整水位覆盖固定窗口，并完成每日目标；否则如实“工程/迁库可分别PASS，数据未完成”，不能全项目 Closeout。归档保存不等于已结算，不能为通过删安全或数据正确性断言。

## 7. 每日调度与权限归属

仅主控在 P3 通过后按原授权安装 `yquant-data-btc5m-history-daily` 唯一 job，当前 yquant、script-only/no-agent，deliver/failure-deliver 均 local；业务脚本留仓库、profile 仅最小普通文件 wrapper，无 secret/LLM/外发。读回 exact job、enabled/schedule/实际时区/script/no-agent/delivery/next_run，换算上海 11:00（UTC03:00）；不凭 shell 时区猜、不声称未来自然 tick 已测。
原非破坏授权仍有效；窗口事实由主控准备，不重复请求授权。本卡 done 仅释放 C2。P1/P2 不再编码；实际缺陷退最小 Fix，环境失败留具体原因，不自动 RBAC/配置/依赖改造。禁止交易、旧库破坏/回写、其他项目/profile、Rust/旧 research、Git 写；不新增平台/服务/Activation。

## 8. 官方Flat/50–50的窄范围契约补充（Pascal批准）

本节按用户要求同步，与RFC §7、Design §2.8一致，覆盖§3.1对双WON一律拒绝的旧理解；不撤销唯一UP/DOWN及显式DRAW正常路径，不放松真实矛盾的拒绝。流程仅本轮Implement→独立Verify→主控收尾，无独立Review；原P2/P3验收保留。

### 8.1 识别与证据

仅对已通过现有source/series、单一market、category/market/condition、BTCUSDT/300秒身份及变体一致性检查的官方数据，以下条件同时满足才将现有`official_outcome`映射为`DRAW`：
1. market为真实RESOLVED；最终同market的唯一RESOLVED日志及合法resolved_at_us继续按现有路径要求，缺日志/不完整状态仍非resolved，不能只凭ENDED。
2. outcomes恰好为可识别且身份无歧义的Up(indexSet=1)、Down(indexSet=2)，二者都WON，无第三个/重复/未知结果；不能把任意多WON视为平局。
3. 官方正数startPrice/endPrice经既有Decimal无损解析后精确相等；upDown/crypto等已知重复字段不矛盾。不得四舍五入或使用容差造成相等，不借Binance价格替代。
4. 同一market的官方description明确声明起止完全相等时50-50。实际原文为`If the two prices are exactly equal, the market will resolve 50-50.`；允许不改变语义的空白/大小写标准化，不做宽泛关键词猜测，不信外部自由文本。
5. resolution原始字段保留：如其对象指向Up或Down，仅在与该实际outcome身份一致且上述Flat联合证据成立时不能据此伪标方向；未知名字、索引/ID身份矛盾仍拒绝。不要求一个实际上不存在的resolution.name=Draw字段，也不篡改原文求绿。

resolution_evidence保两边原始WON、原resolution、规则原句/来源、Flat/50-50判定依据，并标识这是官方市场规则支持的均分兑付，不冒称已读链上payout vector。平局不是两边各全额兑付。无须新增标签枚举或存储字段族；可在现有evidence对象内保存最少结构化语义。仅价格相等、仅描述、仅双WON、仅proposedOutcomeId均不足。特征/标签隔离与观察时间不变。

### 8.2 历史误分类的可修复性与生产边界

Loader在假库开发/验证中仅可增加一条受限路径：当前state=conflict且official_outcome/resolution_evidence均未接受有效标签，候选在§8.1全部通过且为resolved/DRAW，身份、业务事件时间、原非空价格等事实均不变时，允许补齐官方标签/证据；保留raw_history、首次观察时间、实际新标签观察时间、既有CAS和精确readback。不得将该例外泛化到任意conflict或覆盖已接受UP/DOWN/DRAW/非空矛盾证据，不许重写原始raw或回填虚构早期label_observed_at。其它未授权业务字段变化仍拒绝。

此处只授权实现与mongomock验证，不授权改写生产5条记录或孤立stream/day指针。真实纠正须列精确namespace、自然键/记录ID、CAS旧值、允许改字段、原始引用、停止条件与更新后读回；不额外扩建修复平台。不以数据库现有conflict直接证明官方源错误。

### 8.3 独立验证

自包含静态摘录覆盖实际5条等价价格/规则/双WON、原UP/DOWN/显式DRAW路径；负例覆盖不相等、缺规则/终态/日志、额外或重复winner、错误index/身份、非法价格/变体矛盾；假库覆盖conflict→DRAW的窄更新、合法重复重放幂等、已接受终态不可覆盖、原始历史/观察时间/完整水位。缺最终日志的已归档摘录不能冒充日志已验证样本，测试日志替身须明确标注。正常模块回归和新的候选hash以本轮为准，不拿旧1974 PASS代替。

## 9. Step1/2恢复补充（2026-11-12，V1.2增量）

Pascal批准历史缺口/日闭合及集中恢复接线，沿Light Implement→独立Verify→主控执行。本文段对§4未定细节及与本段冲突的旧实现描述优先，§1–8数据/权限/Flat底线不变；详细执行镜像见本主题correction/step12-recovery-contract.md，精确代码范围见Design §2.9。

- 日冷却：既有限次HTTP仍失败的HTTP_NETWORK_ERROR/HTTP_SERVER_ERROR/HTTP_RATE_LIMITED为15分钟，已知更长服务Retry-After不可缩短；BUDGET_EXHAUSTED/正常SCAN_NOT_CLOSED下次有界调用可续；官方缺档/普通待结算/明确coverage gap保24小时。认证/权限/schema/CSV/checksum/真正业务conflict不自动重试。旧暂态日按min(存储due,last_attempt+15分钟)解释，不手工清due；正常尝试后由既有日提交写新结果，plan只读。
- 增加重复`--retry-day DATASET:YYYY-MM-DD`显式人工复核，限有效窗口/截止前非complete日，固定dataset，默认不开；只对显式指定日越过原冷却/人工审查要求，不是无条件接受输入。主控本轮只指定Predict08-11与11-09；新真实冲突仍拒绝，已接受终态不覆盖。plan/无apply零HTTP/DDL/DML。
- pending操作元数据可加recheck_attempts，旧值缺失按0；实际有HTTP请求的一次回查才累计，n=1/2/3/≥4后的等待分别1/2/4/7天，跨进程稳定，不按迟到时间算。它不进入业务内容hash或更改schema版本，原观察时间/结果证据仍按实际完整响应处理。
- 行补齐不等于日complete。缺day.raw_manifest_ref时保“行已补、日未闭合”，正常冻结窗重枚举取得真实闭合证据后重核全日身份/槽/标签/摘要，再提交与推进水位；不扫描全raw猜引用或手写complete。
- enumerated_through_us从锚点按连续具合法闭合枚举证据的日推进，可区别于结算complete，但不越未知缺槽/身份错误；价格按已核归档覆盖日推进。完整连续水位保遇缺即停、可撤回及联合min，不能用最大已存时间替代。
- `--restart-scan`为显式恢复原活动冻结lower/upper/utc_dates的重扫选择，不是自动归类未知API错误。只有apply能改变指针；保留旧manifest/raw及引用证据，仍在原预算内，仅重扫同一窗。无flag正常恢复不变；认证/网络/坏hash/身份错误不能触发静默清指针或全窗扩扫。
- 默认daily只读规划与apply同用stream锚点及实际cutoff，缺初始化报NOT_INITIALIZED；固定backfill仍92日。新增选项不能让无apply产生业务副作用。
- 凭据env PM_PREDICT_API_KEY优先，备选env PM_PREDICT_API_KEY_FILE指向既有安全私有普通文件；只在运行读取，不打印/复制key、不把pruned scratch位置写死业务源码。不改用户env/profile/secret文件。缺失/不安全/空内容报脱敏错误、Predict请求前失败，Binance有预算仍执行。模板只传递既有注入契约，不安装调度。
- 每源异常在summary明确error_code，顶层exit_code与真实main返回一致；报告显式retry/重扫、stored/effective due及延后原因，不追认20批未知退出。原两源独立预算/flock/HTTP30s最多3次/每源7日/墙钟1800/max_requests1000/chunk5000均不扩。

仅新候选独立Verify后才恢复原P2生产。生产仅官方raw及yquant-data三历史集合，旧Flat更正仍遵守§8、CAS/观察时钟与终态保护。不得借恢复改旧库/账户/策略/RBAC/服务/配置/cron/Git。最终生产幂等/daily/P3及每日job不因本增量工程PASS而通过。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.2 | 2026-11-12 | §9冻结Step1/2错误分类/due兼容、精确复核/重扫、回查次数、枚举水位、daily锚点、安全key-file与报告；来源RFC §8，范围Design §2.9；待新候选验收 |
| V1.0 | 2026-11-11 | 原 T1 契约；逐字副本保留于主题 `evidence/rebaseline/SPEC-03-018-v1.0.md` |
| V1.1 | 2026-11-11 | 按纠偏替换正文；保数据底线/接口，迁移限五集合、稳定窗读取、三交付分离，不沿用旧UT编号族/额外协议门禁 |