# DESIGN-06-002：中性永续网格四窗口研究与 B-001 最小修复

## 元数据与结论

| 项 | 值 |
|---|---|
| 版本 | V1.7 |
| 日期 | 2026-11-03（V1.7；V1.6 为 2026-11-03 同日续修订），Asia/Shanghai（UTC+08:00） |
| 阶段 | YQuant 按 Pascal 已确认决策同步契约：审计 D-01 局部撤销（V1.5 §12，已实现并独立 Verify）、v=0 零成交 bar 合法化实现契约（V1.6 §13，Pascal 2026-11-03 D1 决策）与消费链 crypto.py 放行契约（本版 §13.4，t_b8db70b3 D2 决策）；§13.1/13.2 的 native 层已由 t_aa056536 实现并通过平台侧验证，§13.4 待实现；历史 G-02 Design t_1f4c8c58 及旧验收记录保留，非本次重开 |
| RFC / SPEC | [RFC-06-002 V1.8](../../rfc/06_strategy/RFC-06-002-neutral-grid-multi-window-research.md)，§9/§10 / [SPEC-06-002 V1.8](../../spec/06_strategy/SPEC-06-002-neutral-grid-multi-window-research.md)，§10/§11；D-01 撤销见 §12（对应 RFC/SPEC V1.6 §9/§10），v=0 合法化见 §13（§13.4 消费链 D2）；§11 训练通道保留 |
| 权威范围 | 本主题data/tasks/active/2026-11-01-grid-g01-g02/{intake,rfc-spec-handoff}.md及父卡；原pipeline-intake与杠杆/三件套授权作为已签收历史保留 |
| 当前判定 | 审计 D-01 局部 Implement→独立 Verify 已完成并通过（离线，D01-01..07 全 CLOSED，t_8a23ea34），主控离线签收，未另开 Review；API 进程已受控重启并真实 HTTP 验证公共 Gate swap 读取与本地重采样（api_runtime_loaded=VERIFIED）；既有 G-02 离线线和五项修复验收保留。G-01（缓存身份）与 G-03（历史乘数适用性）仍 OPEN；historical_evidence=UNKNOWN、full_research_status=DEFERRED，后台角色未加载、原T6仍blocked、16业务禁止 |

B-001四文件及132项/补审、§4杠杆79项/Review APPROVE均为已验收资产。§5-7三件套随后完成独立Verify R3 153项OK、Review t_40f89523 APPROVE、主控offline ACCEPTED，见data/reports/2026-11-01-strategy-lab-leverage-fix/trio-closeout.md；旧R1/R2失败、更正与旧卡不追认成功。§3-8保留既有API/算法/测试契约，不重新列待实现；当前唯一delta为§11的训练OHLC读取与参数预冻结。真实Gate swap全部共用历史volume拒绝路径，不仅PUMP；训练成功不能提供合格volume，四合约真实回测仍failclosed。G-01/02/03不因文档/离线工具通过而闭合；原T6 t_2b5702a5不解除。

本轮t_1f4c8c58仅使用必要文件读取/检索及文档编辑，不运行命令/测试/应用import/网络，不读凭据、不启动服务、不建卡。run3424额外基线审计按Pascal恢复决定取消，OMITTED_BY_AUTHORIZATION，不重采、不重放、不记PASS、不改审批配置。Funding保持not_modeled；不新增端点族/SDK/平台/历史metadata数据库/缓存平台/依赖或runtime撮合资金模型。

> 当前执行修订：Pascal 于 2026-11-02 同意审计 D-01 的局部撤销，见 §12。旧阶段“本卡/本轮/尚未实现”是原时点记录；公共历史缺证阻断及旧 G02-04 断言在本次被替代，不追认旧契约下的验收为错误，也不解除研究锁。§12 的代码实现与独立 Verify 已离线完成，API 进程已受控重启并真实请求验证；后台角色、缓存身份与历史证据仍未闭合。最新修订（V1.6）：§13 是 Pascal 于 2026-11-03 决策（D1）的 `_gate_swap_volume_number` v=0 零成交 bar 合法化实现契约，实现/验证均未发生；五类 gate.swapVolume* 拒绝语义、单位换算链、runtime 撮合器与研究锁不变。 V1.7（t_b8db70b3，D2）：native 层已实现并通过平台侧验证（t_aa056536，237 passed + 1 xfailed）；新增 §13.4 消费链 crypto.py 两处 volume>0 数据有效性谓词放宽（≤0→<0）的精确实现契约，待实现与独立 Verify；R-01 未修复，runtime 撮合器与研究锁不变。

## 1. 输入、基线与已验证事实

本节下方HEAD/行号/哈希/70项及V1.3复核均为对应历史现场，不是本次重新取得的基线。V1.3曾记录父仓HEAD=9978bdc08b9a6ac55304834a49f45eb338b952d1、子模块HEAD=1016b61d381ce536a673de5f5fe552e0bf3fca74及B-001哈希复核一致；quantdinger.py=30cbc8fc…（2472行）、agent_backtest.py=bc940f1c…、test_quantdinger.py=48a16adc…（1314行）、SKILL.md=4f396c1c…为该阶段身份。本卡未采Git/新SHA，不声称当前HEAD/全仓clean或哈希仍一致。三件套现已离线签收，唯一新增待实现delta见§11；旧接口/五点标准保留。

父阶段 t_cfccfe2c 的 run3395 原 BLOCKED/原始证据保留；本轮续接 run3396 的 V1.1，不重做 PUMP 历史取证。父仓 HEAD=5c5fca7d4bdd1b5a027fe48943f1eff3de2a09e3，子模块 HEAD=4111d4550c9354a278d3926a786c4b2586a673aa。

- RFC SHA256：8325b865fbf01ba602d4496188cbab8283a790a99d446c5bc48b7f2cc4798aa3。
- SPEC SHA256：76e4ccce873757f401d42332ce2262bb9aeaea207dfdb7150eeae5aef0e6f9b0。
- 当前四项工具文件与 workspace-baseline.json 哈希逐项一致；native_crypto.py、crypto.py、对应测试与 b001-submodule-baseline.json 一致。
- 本轮真实运行既有 unittest：70 tests，OK，exit0。测试在临时目录使用明确 synthetic/offline fixture，不读取真实凭据、无业务调用；不是 B-001 新实现测试。
- 既有测试通过 importlib.util.spec_from_file_location("offline_quantdinger", MODULE_PATH) 动态导入，并 patch qd._http_send、qd.agent_submit、qd.poll_job、qd.call_data 等；抽取必须保留这些接缝。

以下子模块路径以 `skills/trading/auto-trading/quantdinger/QuantDinger/backend_api_python/` 为前缀：

| 源码位置 | 当前事实及设计含义 |
|---|---|
| app/data_sources/native_crypto.py:217-250,334-349,503-610 | 现有 load_markets 缓存保留 Gate 原始 info；swap v 尚原样进入第6列，spot 分支独立；公共六列 OHLCV 是兼容边界 |
| app/data_sources/crypto.py:589-623,684-714 | 消费前6列并 format_kline；异常可变成空列表，再走 public fallback；必要单位失败不能静默变成跨所/成功空数据 |
| app/services/strategy_v2/market_data.py:153-200,278-345,348-366,560-570 | 有按请求窗缓存及按流共享 frame；可在到达 native 之前命中；单位版本未参与 key，旧 frame 无单位证明 |
| app/services/backtest_cache.py:18-121 | KlineCache 为内存+可选Redis；15m TTL=21600秒，其他如1d为86400秒；重启进程不保证消除Redis旧值 |
| app/services/strategy_v2/service.py:197-229 | 按每个订阅频率回溯 warmup；统一 warmup_bars 并强制验证，不是“最多365、短上市取实际数”接口 |
| app/services/strategy_v2/readiness.py:17-35 | 每个频率历史数不足 warmup_bars 就失败，不支持由策略自行接受2..364根 |
| app/services/strategy_v2/data.py:138-176,274-280 | history 多频接口存在，按事件可用时间截断；不等于训练样本已可在提交前导出 |
| app/services/strategy_v2/runtime.py:1773-1832,2127 | 日志可返回、逐bar回调可记录；并非逐成交钩子；破产分支会跳过策略回调 |
| app/services/strategy_v2/storage.py:361-413 | 权益1200/持仓600/订单成交1500等压缩；logs不在此函数压缩，但实际传输容量尚未验证 |
| app/routes/agent_v1/markets.py:87-125 | klines没有显式venue/product参数及来源/乘数输出契约，不假定symbol后缀能绕过整条实际路由 |
| app/data_sources/factory.py:267-271,328-348 | 先按显式exchange_id/market_type选择source，再把symbol交source；未在选择source前解析symbol后缀，不能用后缀视为已证明同产品路由 |

## 2. 文件级边界

### 2.1 文档修订 allowlist

当前t_1f4c8c58仅可改本Design和data/tasks/active/2026-11-01-grid-g01-g02/design-handoff.md，不改RFC/SPEC/模板/源码/测试/SKILL/历史证据。下面为历史范围，不授予本卡其它写入权。

t_9fddffed仅写原RFC、SPEC、本Design与 data/tasks/active/2026-11-01-strategy-lab-leverage-fix/principal-handoff.md，不写源码/测试/SKILL。本轮t_1b635d49同样只做文档修订：仅写 RFC（升V1.4，同步启用状态）、SPEC（升V1.4）、本Design（升V1.3）与 data/tasks/active/2026-11-01-strategy-lab-leverage-fix/principal2-handoff.md；不写源码/测试/SKILL，不运行测试/编译/业务/网络，不读凭据/env/会话DB。下列为原T2分段修订四文件历史范围，旧交接不改写：

1. docs/design/06_strategy/DESIGN-06-002-neutral-grid-multi-window-research.md（本文件）。
2. data/tasks/active/2026-10-30-neutral-grid-research/t2-handoff.md。
3. docs/rfc/06_strategy/RFC-06-002-neutral-grid-multi-window-research.md。
4. docs/spec/06_strategy/SPEC-06-002-neutral-grid-multi-window-research.md。

上述 RFC/SPEC 修改仅同步 Pascal 已批准的离线分段决定；原 run3397 的两文件范围为历史。禁止修改实现、策略、技能或子模块，不改原五点最终研究标准。

### 2.2 既有开发allowlist（已完成/历史候选；当前增量以§11.1为准）

§4杠杆客户端与§5-7三件套在各自原allowlist内均已实现并离线验收。scripts/quantdinger.py、scripts/agent_backtest.py、tests/test_quantdinger.py、scripts/grid_research.py、tests/test_grid_research.py、neutral-grid-four-window-v1五文件及SKILL.md均是本次只读保护资产；tests/test_agent_backtest.py未新建。下列原候选表/历史授权原样保留为追溯，不能用来扩大G-02范围；本次精确增量仅§11.1。

下表为原候选清单：客户端及grid_research.py/test_grid_research.py已落地签收；通用evidence扩展、稳定键恢复增强、references/backtest-comparison-standard.md标准表重构及旧t3-handoff路径仍未启用：

| 文件 | 职责与允许变更 |
|---|---|
| skills/strategies/strategy-lab/scripts/quantdinger.py | 仅 Agent 局部抽取兼容壳、Agent显式杠杆参数与允许证据返回；Human/trade不变 |
| skills/strategies/strategy-lab/scripts/agent_backtest.py（新） | Agent body、提交/读回流程、结果字段投影；不独立解析凭据、不建HTTP栈 |
| skills/strategies/strategy-lab/scripts/grid_research.py（新） | 纯日期/geometry/coverage/指标/组合情景/汇总与清单协调；仅调用已有Agent函数，不撮合 |
| skills/strategies/strategy-lab/tests/test_quantdinger.py | 既有70回归保留；追加默认false/1及显式10x、抽取兼容断言 |
| skills/strategies/strategy-lab/tests/test_grid_research.py（新） | 纯函数、去重/恢复/停止/报告与证据缺口离线测试 |
| skills/strategies/strategy-lab/SKILL.md | 本次操作备忘/局部抽取与未验证状态，不扩权限，不宣称业务已验收 |
| skills/strategies/references/backtest-comparison-standard.md | 仅补充本轮已冻结时间/分母/有效数表达，不改变原标准与门槛 |
| data/tasks/active/2026-10-30-neutral-grid-research/t3-handoff.md | 实现命令、差异、测试与残余限制 |

本轮窄启用的新研究实例仅一个目录，避免复制16套工具：`skills/strategies/strategy-lab/strategies/neutral-grid-four-window-v1/`，仅 README.md、spec.md、config.json、research.py、strategy.py 五文件（逐文件验收要点见§5-§7与principal2-handoff）。config只数值参数；16单元市场/窗口/训练/冻结参数保存在任务清单，不把字符串塞入 numeric config。research.py是本地协调入口，仅调 quantdinger CLI 与 grid_research 纯函数，不撮合、不发业务请求（本轮离线，真实研究执行仍属未来业务阶段）；strategy.py由平台沙箱执行、本地不得import执行。旧12目录及旧结果只读，不迁移或改写。

子模块原B-001允许文件（均相对子模块根；已离线验收，本次全部只读保护，不再授权修改）：

1. backend_api_python/app/data_sources/native_crypto.py：仅 NativeCryptoPublicClient 的 Gate swap 元数据/单位分支，及仅被该分支调用的新私有 helper；允许在 __init__ 初始化这一分支的有界证据状态。不改其他venue、spot、_float全局语义、网络/代理函数。
2. backend_api_python/app/data_sources/crypto.py：仅 CryptoDataSource.get_kline 的 Gate swap 结果衔接和该特定单位失败的处理。此文件有必要：native六列本身无法携带原始张数、适用性、单位证据，现有format_kline仅传六项且异常可被吞掉。不允许在此再乘一次乘数。「该特定单位失败的处理」按run3401交接补齐为让§3.2五类错误能真正上抛的最小接缝：_fetch_ohlcv 的分页retry catch与外层catch、_fetch_ohlcv_fallback 的两处catch，仅为 gate.swapVolumeMetadataMissing、gate.swapVolumeMetadataInvalid、gate.swapVolumeHistoricalUnverified、gate.swapVolumeInvalid、gate.swapVolumeEvidenceMissing 的 NativeCryptoAPIError 立即 re-raise，可复用仅识别这五类错误的私有helper；其它错误、产品、venue、网络、分页与重试语义不变，get_kline 自身仍保留对同类错误的直接处理。另注意公共 base.py format_kline 会将volume四舍五入两位：Gate 分支必须在其允许范围内保留精确已归一化 volume，不得使小正值变0；不改 base.py。
3. backend_api_python/tests/test_native_crypto_public_client.py：Gate swap单位失败复现与原有多所回归。
4. backend_api_python/tests/test_gate_swap_volume_units.py（新）：消费者字段/错误传播、单位证据缺失及cache前置限制测试；不添加生产cache实现。

原B-001授权不包含app/services/strategy_v2/market_data.py、backtest_cache.py、runtime.py、instrument_rules.py、Agent routes/OpenAPI、公共配置或生产unit。当前仅§11.1明确开启既有Agent klines/OpenAPI的必要增量；缓存/runtime/生产配置仍无授权。

## 3. B-001 最小适配方案（已离线验收，保留原契约，不列本次待实现）

### 3.1 量纲与原始证据

仅处理 `id=gate && market_type=swap`，限定USDT结算direct线性合约。复用现有 load_markets() 中 `markets[canonical].info` 的合约元数据，不为每根bar发元数据请求，不复用交易下单client或凭据。验证native_contract、settle、direct类型及有限正 quanto_multiplier；不以 linear布尔推断所有Gate产品均direct，不取 fallback contract_size=1。

换算唯一发生在 native Gate swap解析：base_volume=raw_v_contracts*quanto_multiplier，第6列返回基础币；消费者只透传。quote_volume仅取官方sum原始值；缺sum为null，不用close*base假充官方值。原始v、sum及乘数字符串保留，不只保存浮点重算值。非有限、缺字段、负值及本轮volume<=0按invalid/unknown终止研究路径，不把0送入无限流动性分支；真实无成交bar也是研究模型无法安全表达的限制，不捏造正epsilon。

证据对象 `gate_swap_volume_v1`：exchange_id、market_type、settle、native_contract、bar_open_utc、interval、raw_v_contracts、raw_quote_sum、quanto_multiplier、base_volume、quote_volume、volume_unit=base、source_endpoint（无凭据）、retrieved_at_utc、metadata_source、metadata_retrieved_at_utc、effective_from/effective_to（未知null）、historical_applicability=verified/unknown、normalization_version=gate_swap_base_v1。原始数值不得由已经转换的volume反除重建。

### 3.2 六列兼容与消费者衔接

不改变公共 `fetch_ohlcv(...)->List[List[Any]]` 的六列长度、顺序和时间单位。native增加只读helper `get_gate_swap_volume_evidence(symbol, timeframe, timestamp_ms)`，按最近一次请求的完整identity及bar索引获取原始对象；每次fetch只保留返回页所需的有界数据，使用现有线程局部机制隔离同client并发请求，缺identity命中不得借用上一symbol/页的证据。

crypto.get_kline在Gate swap native分支读取该helper，在原有format_kline结果上附加数值列 `raw_v_contracts`、`quanto_multiplier`、`quote_volume` 及 `volume_unit`、`volume_normalization_version`、`volume_historical_applicability`，另附严格业务字段投影的 `volume_evidence`。不能全量dump元数据/info；不含账户或HTTP headers。不支持保留完整证据的重采样不称研究可用；本轮1d/15m均原生频率，不用重采样路径规避。

新增特定错误标识 `gate.swapVolumeMetadataMissing`、`gate.swapVolumeMetadataInvalid`、`gate.swapVolumeHistoricalUnverified`、`gate.swapVolumeInvalid`、`gate.swapVolumeEvidenceMissing`，使用现有NativeCryptoAPIError承载。crypto仅对Gate swap这些错误立即上抛，不走公共跨所fallback、不返回成功空列表；其它错误/产品/交易所保持既有行为。错误上下文仅合约/频率/bar/缺失字段，不打印session或原始payload。

上层factory.py:307-325仍可能把异常归为结构化MarketDataFailure和空rows，原生market_data对无有效rows再拒绝；本设计不修改factory公共层。测试必须断言最终不会得到成功frame/回测，而不能假称所有HTTP层都透传相同异常字符串。禁止为“错误更漂亮”扩改公共错误路由。

### 3.3 历史乘数与可执行失败行为

现有load_markets是检索时刻快照，没有历史有效区间。`retrieved_at`不能充作`effective_from`，当前direct类型和正乘数也不能证明过去一年未变。旧instrumentRulesSnapshot source=historical_fallback_no_snapshot、contract_size=1.0一律不作为证据。

只有已有、可审计的同合约历史有效证据覆盖请求bar时，本项研究才可将基础币volume视为历史适用性已验证。按 §12，公共读取不再因该资格 unknown 而 fail closed；当前快照可用于正确换算并返回，但不能作为历史有效性证明。本研究保存 UNKNOWN，原目标提交锁保持；不新增历史元数据平台或公共回测门禁。明确 synthetic fixture 只证明离线逻辑，不能用于真实历史 PASS。

当发现确有可复用历史快照入口时，必须先证明其产品、有效期和来源，再在本设计修订精确接缝；禁止临时硬编码PUMP乘数或给当前快照伪造长期有效期。

保留私有 synthetic 解析接缝作为测试设施，不新增 fetch_ohlcv 公共参数；但正常公共 Gate swap 读取必须同时覆盖无 synthetic、无历史有效期的当前元数据形状成功路径，其 historical_applicability 为 unknown。公共历史读取不再仅因 unknown 拒绝，不能因此宣称历史资格通过。

### 3.4 缓存兼容与停止规则

旧裸六列/旧frame的volume可能仍为张数，不能通过数值大小猜单位，也不能“缓存再乘一次”修复。新证据字段缺失、单位版本不符、部分新旧行拼接，均UNKNOWN；严禁重标旧PNL。

native的证据页只服务本次返回页，不能作为历史cache权威。旧market_data共享frame和KlineCache可在native前命中，因此仅改native/crypto不能保证旧缓存已退出；§10 G-01列为真实加载前提。候选最小运维路径是主控批准后在无在途job时让实际消费者加载新代码，并等待旧缓存失效且验证未再命中旧单位；不得清Redis/数据库、改key、改变请求窗口/产品来躲cache。共享frame没有本次可依赖的TTL，不能仅等待6小时就假定安全；Redis是否启用本卡未读环境、未知。

本次不执行任何reload/restart/cache删除/配置变更。若选择代码级版本化cache，属于额外文件范围，需要主控明确授权后修订设计，不偷塞入crypto导入时清cache。

## 4. Agent 薄层局部抽取与兼容契约（本次仅启用抽取/杠杆/CLI子集）

迁移仅现有 build_agent_backtest_body、billing_contradiction、agent_backtest 的实现到新 agent_backtest.py；quantdinger保留同名同签名兼容壳（新参数keyword-only有默认），不迁移Human、通用HTTP、凭据解析、Budget、poll_job、判定模块。新模块导入时无业务文件/网络/环境读取副作用，实际流程仅调用注入的既有依赖。

为保持动态文件导入及monkeypatch，兼容壳在调用时显式传入现有agent_submit、agent_call、poll_job、new_idempotency_key、LabError及Budget实例，所需常量/纯helper（如_scrub/_finite/_as_dict）仅传最小依赖；不复制通用设施，不传整个模块作伪SDK。新模块不从quantdinger反向import造成双加载。新模块由壳调用时按相邻绝对文件路径加载，不要求测试/用户cwd在scripts，不全局sys.path注入；import quantdinger仍无业务文件/网络/环境读取。依赖在调用时取当前值，不能在导入/默认实参中捕获旧patch对象。先运行既有70项基线，再抽取、再原样回归及新增断言；spy-close-research对CLI helper import继续有效。

新增参数：builder/agent_backtest及兼容壳 keyword-only `leverage_enabled=False, leverage=1`，旧调用不补参也有效。CLI agent-backtest新增 `--leverage-enabled`（store_true，默认False）与 `--leverage`（float，默认1）；handler透传，不影响Human/trade。九个body白名单字段不增删，不传sourceId/persist；1000/true/10原样成为initialCapital/leverageEnabled/leverage，客户端不乘资本或订单，不能用capital10000替代。精确规则如下，均由本次Intake与以下源码支撑，不新增平台限制：

- 纯参数在任何Agent请求（含compile）前校验：leverage_enabled必须是bool；leverage仅非bool的int/float，必须有限且1<=leverage<=100，关闭时必须等于1（1.0等价）。非法字符串/None/容器、bool倍数、NaN/±Inf、0/负值/<1/>100及关闭非1，抛现有LabError/EXIT_USAGE；不clamp、不把字符串true当布尔、不额外限定整数。启用且倍数1合法。
- 只读平台依据（子模块backend_api_python前缀）：app/routes/agent_v1/backtests.py:28-32接受原生杠杆字段、:163-170原样传body；app/services/backtest_jobs.py:48-65传initial_capital/leverage_enabled/leverage；app/services/strategy_v2/contract.py:47的PLATFORM_MAX_LEVERAGE=100.0，:183-186的allow_leverage(value)仅用value>1确定许可，并将max_leverage设为平台100或1，而非用户value的策略专属上限；models.py:142-143据此输出leverageAllowed/maxLeverage。runtime.py:1729-1734仅在requested_leverage>1时要求许可，并检查平台100；不读取manifest.maxLeverage作另一个独立上限。
- 客户端以当前核实的平台100为纯常量上限，不导入平台服务/读环境/联网发现上限。compile返回非空manifest后，仅当请求倍数>1时要求manifest.leverageAllowed严格为True；False/缺失/非bool拒绝，抛LabError/EXIT_CONTRACT，backtest POST及take_outer_job均不得发生。请求倍数1（包括默认关闭）保持旧兼容：不因旧fixture缺leverageAllowed/maxLeverage额外拒绝；原manifestMissing规则仍在。不以原allow_leverage入参或manifest.maxLeverage建立min/max新门槛；正常真实compile的maxLeverage在允许时为100，新增fixture必须准确表达该事实，不伪造“策略上限10”。
- 有效参数顺序仍为budget检查→compile→既有manifest/计费检查→许可检查→take_outer_job→backtest POST→原poll/计费/结果处理；纯参数提前拒绝不消费job或发compile。compile本身是POST，所以上述“manifest在POST前”精确指backtest POST前，而不是compile前即可知许可。保持现有幂等、两次传输失败停止、预算与鉴权/收费停止语义，不新增跨重启恢复。
- 返回现有metrics/context/sampledArrays/billing/compileManifest等投影与报告格式保持，executionAssumptions仅依既有context投影；缺失仍为UNKNOWN，不能以请求伪造回执。本次离线贯通只证明发送字段，不声称运行中引擎/真实1000/true/10已验收。

以下为未来未启用候选，本次禁止实现：追加明确业务投影 `evidence`（logs、原生权益/仓位/订单成交抽样、historyStorage、audit、instrumentRulesSnapshot、dataProvenance、executionAssumptions、positions、attribution、计数）。保留压缩标识，不写全HTTP响应；安全字段过滤必须递归且覆盖日志文本脱敏。Agent job.result扁平层读取，不走Human run详情。

以下为未来未启用候选，本次禁止实现：幂等增强由研究协调器保存稳定键和已知jobId；已有agent-backtest一次流程默认行为不改。新增内部参数可接收固定submit键、已知jobId和receipt回调，compile键独立。POST之前写盘同体摘要与键，202立刻先保存jobId再GET；已知job只GET。崩溃发生在提交后未落receipt时也只允许使用原键同体且累计最多一次重放；尝试计数跨重启保存，未知不产生新键。

2502行文件通过移出流程实现获得净减少，禁止把新研究逻辑放回CLI；不以删除空行达标。新模块各自保持单一职责，若无法净减少或发生无关迁移，停止并交回设计。

## 5. 研究协调与数据/参数接口（已离线验收；16业务执行仍禁止）

下列纯函数已在grid_research.py实现并离线验收，保留原接口契约，不作为本轮重新实现任务；必要实际调用差异在§11显式适配：

- `build_cells(contracts=None, windows_spec=None, anchor_utc=None) -> list[dict]`：显式接受合约清单、窗口结构与UTC锚点，缺省None解析为本轮冻结值——合约顺序PUMPUSDT/AAVEUSDT/JUPUSDT/SUIUSDT、W1..W4窗口结构（SPEC §3.1表）、锚点2026-10-31T00:00:00Z；未来换合约只改传参即用，函数体内不得内嵌第二份硬编码矩阵。默认值语义与去重不变：去重后恰好16唯一目标，日期严格按SPEC §3.1（自锚点直接减3k个日历月、缺同日月末截断、半开窗）；参数化调用按同一规则校验cell_id唯一、窗口半开不重叠、锚点为已到达UTC午夜，非法输入（空/重复/重叠/未到达锚点）报错拒绝，不接受运行时静默改语义。
- `check_coverage(bars, identity, start_utc, end_utc, frequency_seconds) -> dict`：核对每个预期bar、重复冲突、时间对齐与close<=end，不采用平台98%容忍代替。
- `derive_geometry(closed_daily_bars, start_utc) -> dict`：只取前置已收盘最多365根；2..364标短历史，缺口/来源未知不成功；N与成本按SPEC §3.2，平分较小N。
- `margin_metrics(bar_close_rows) -> dict`、`cross_liquidation(snapshot, mmr, close_fee) -> dict`、`summarize_cells(cells) -> dict`：见§7，未知为null+reason。
- `reconcile_audit(logs, cell) -> dict`：验证§6连续性、来源、native计数/净值；不能把summary长度当全量。

清单schema_version=1，固定16项字段遵循SPEC §4；每项状态为planned/prechecked/submitting/submitted/succeeded/history_insufficient/insufficient_evidence/failed/not_submitted_due_to_stop。N/A和未提交均保留null jobId/runId及原因。canonical JSON使用sort_keys、紧凑分隔、UTF-8、拒绝NaN；SHA256包括cell/完整市场/时间/源码/参数/资金成本/数据身份。编译源码先静态纯生成、不在本地import策略，manifest需leverageAllowed和正确instrument。本轮实现落上述清单读写与校验（离线测试用synthetic样例验证载体格式），不产生真实研究manifest；跨进程预算不重置以manifest落盘状态为准，不实现§4未来候选的稳定键跨重启提交恢复增强。

逐合约共享一个deadline与预算累计，不因resume重置：最多4目标job、总外层<=8、数据请求<=50、墙钟<=1800秒、Evolution=0。8不是备用搜索/失败重跑额度。跨进程恢复保留已耗时、提交次数与data请求；无法证明剩余预算则STOP。未知/失败/取消/workerInterrupted/409/鉴权/收费矛盾即停止全部后续提交，生成剩余未提交目标行。本轮实现预算/停止的纯核算与清单状态机（离线可测）；真实job提交与停止行为属未来业务阶段，本轮与三件套实现均不发任何业务请求。

C-002旧结论保留：作业内多频history不能证明提交前冻结，也不能自动添加backtest/probe或假称generate已接入。RFC V1.5 D-06已唯一裁定既有Agent训练OHLC分支，具体落实§11，不再把作业内方案或“主控任选路径”列为开放决策。

## 6. 策略内审计设计与可证明粒度

复用原生robot_v2中性网格模板的格角色/生命周期，关闭动态锚定；原生成器源码只读留sha256，不本地import平台服务。新实例策略按已核对模板生成，仅修改冻结geometry、风险容量检查及审计回调；不开发撮合器。本轮t_1b635d49窄启用本节实例生成契约：strategies/neutral-grid-four-window-v1/strategy.py由协调器按已核对原生中性网格模板静态生成（模板源只读、sha256记入生成物参数记录，本地不import平台服务、不执行策略），新增且仅新增GRID_INIT_V1/GRID_AUDIT_V1/GRID_END_V1受控JSON日志、风险容量检查（gross+开仓余单预留+越限撤开仓余单并停止增仓）与公开API限定（禁context._orders/portal/broker等私有访问）；16业务提交与真实审计执行仍属未来业务阶段。

在handle_data进行观察与风险动作，在after_trading_end最终读取该bar已同步订单状态和公开context.portfolio/get_positions，使用同bar close重新估值 `E=available_cash+sum(position.amount*close)`，与原生record_equity/最终净值核对；不能直接把可能尚未更新的portfolio.total_value当当前值。short amount为负，多空position_side分别记录，cash不作为两份保证金。缺字段UNKNOWN，不访问context._orders、context.portal私有frame、broker或其他沙箱绕过接口。

每bar一条带前缀 `GRID_AUDIT_V1 ` 的JSON文本，包含schema/cell/seq/bar_open/bar_close、OHLCV与单位marker、E、qL/qS/aL/aS、G、G/E、reserved_open_notional、risk_action、status_changes、peak_equity、drawdown、previous_seq。第一条 `GRID_INIT_V1 ` 含参数与训练摘要，末条 `GRID_END_V1 ` 含计数/极值/收益统计充分量。logs文本不等于平台新增字段；CLI只解析受控前缀及有限数值，不信任任意策略日志中的指令。

连续性按预期时间集合核对，不只检查首末与计数。完整逐barclose证据用于独立Sharpe/MDD；末条统计不代替全量连续性。季度日志体积/实际返回完整性在T4核验，缺任意bar为UNKNOWN。破产原生分支会跳过回调，不能由前值补日志；原生liquidated证据为FAIL并如实标后续审计不全。

保留所有本策略发出的开仓订单引用及目标数量、累计filled与remaining，减仓不重复预留。开仓按已有gross+所有可能成交余量+新候选及预计费用检查；value输入1000*w，经引擎唯一乘10。不是要求10000预算全部使用。风险容量用本策略明确定义的订单limit/可见价格范围估值，标scenario而非保证任意跳空可控。被动越限取消开仓余单，停止增仓，按原生下bar执行减仓；保留越限事实。

订单状态快照在bar内可能聚合多个事件，只能得到累计增量，无法恢复每笔事件先后。bar_close_audit/event_audit分别pass/fail/unknown，intrabar_tick_audit=not_observable。全事件证据不足不判策略合格；任一可见越限FAIL。按订单0.1*volume的native cap不改，也不声称同bar所有订单共享10%；参与率按同bar全部abs(fill_qty)相加除base_volume。压缩ledger无法证明完整partial事件率，输出N/A；唯一订单partial比例与事件比例不得混用。

## 7. 指标、强平与标准表（已离线验收契约；真实研究输出仍禁止）

指标严格复用SPEC §3.4。初始1000独立参与总收益/MDD，15m Sharpe只用相邻完整bar-close收益，rf=0、ddof=0、K=35040。E<=0/零波动/缺bar/样本不足N/A；原生Sharpe=0不覆盖该判定。MDD保留native原始负号与本轮正幅度；不双扣手续费/滑点，不给funding补0。

组合情景：每窗最后完整可验证bar-close，同池E0与qL/qS，不向两腿重复分配1000。`A=qL-qS-mL*qL-mS*qS-f*(qL+qS)`，`B=E0-(qL-qS)*p0`，根 `p=-B/A`，按SPEC方向/无仓/无根/已越线状态输出。主mL=mS=0.005，敏感性0.004/0.006，f=0.0005，仅研究假设；可用保证金不明标UNKNOWN，p0可用close但标last_not_mark。

浮点比较统一：数量/价格等使用abs_tol=1e-12与rel_tol=1e-10；A近零阈值 `1e-12*max(1,qL+qS)`，H近零与方程残差阈值 `1e-8*max(1,abs(E0),abs((qL+qS)*p0))` USDT。根与p0在对应价格容差内即already_breached；拒绝非有限输入。记录公式版本cross_linear_v1、实际残差/容差，不用四舍五入后判方向。风险2.5与MDD35的比较保留原始精度，容差仅用于数值核对，不作为放宽业务阈值。

四行汇总固定列遵循既有backtest-comparison-standard；数值格式“均值（W1/W2/W3/W4）；n/4”，缺失写N/A+原因，均值不剔除亏损/不合格窗。恰好16明细，主结论分别tool_status/research_status/qualification；不额外设正收益或Sharpe阈值。四个独立1000池不是连续复利年账。

T4/T5输出载体冻结（本轮实现仅在离线测试临时目录以synthetic样例验证载体格式，不创建真实研究产物、不写 data/reports/2026-10-31-neutral-grid-four-window/；真实产物由未来业务阶段产出）：

- 任务目录 `research-manifest.json`：16计划/去重/键/预算/状态，单写者原子替换；原旧evidence不覆盖。
- `data/reports/2026-10-31-neutral-grid-four-window/report.md`、`comparison.csv`（4行）、`cells.csv`（16行）。
- 同目录evidence内每cell `CELL.result.json`（允许字段投影）、`CELL.audit.jsonl`（受控日志）、`CELL.metrics.json`（独立公式与核对）、`CELL.parameters.json`（前置训练与源码）、`CELL.volume.json`（官方同窗对齐、原始证据与缺证）。
- 提交receipt以每cell独立 `CELL.receipt.json` 保留允许字段；追加读回不覆写原始receipt，未知响应不能假造。data忽略不代表提交/远程备份。

PUMP固定首/中/末bar和partial bar核对不能用派生raw=v/m作为官方第二份证据；必须有真正原始请求身份、同UTC记录及元数据适用性。Agent当前未提供这些字段的原始官方业务读取能力，不能由CLI自行直连补齐，见§10。

## 8. 测试与实现顺序

杠杆子集79项与三件套独立Verify R3 153项OK、Review APPROVE均已验收，本卡不重测。下表L-01..06和三件套集合为受保护既有断言，不删改放宽；G-02新增测试见§11.7，旧153项不冒充新增能力验证：

| 编号 | 当前客户端验收与证据 |
|---|---|
| L-01 默认兼容 | builder和agent_backtest不传新参数仍false/1；真实CLI parser/handler不传flags仍false/1；九字段白名单、原params/资金成本/返回投影不变，既有70项原样通过 |
| L-02 1000/true/10贯通 | builder直接断言；patch qd.agent_submit/poll_job的实际agent_backtest捕获compile→backtest请求顺序及body；真实parser/handler以--capital 1000 --leverage-enabled --leverage 10走实际agent_backtest，fake仅HTTP/submit/poll/凭据解析和隔离文件fixture等边界，不能mock掉整个agent_backtest。三层均assert initialCapital=1000、leverageEnabled is True、leverage=10、资金/订单不二次放大，poll既有job无多发；本地策略文件仅读文本不import |
| L-03 纯参数拒绝 | enabled=非bool（含0/1/字符串/None）与leverage=bool/字符串/None/容器/NaN/±Inf/0/负数/0.5/100.1、关闭却10，builder与实际Agent流程拒绝；流程agent_submit/agent_call/_http_send调用均0、outer_jobs不增长；CLI覆盖非法文本、NaN/Inf、<1/>100及未启用却10，parser或handler明确拒绝且网络0。边界1/100与小数1.5允许，True/1允许；默认false/1不误拒绝 |
| L-04 manifest许可 | 请求10时compile manifest.leverageAllowed=False/缺失/非bool均EXIT_CONTRACT，只有compile、无backtest POST、不消费outer job；True且maxLeverage=100可走10和100边界。默认false/1与True/1不因旧manifest缺新增字段失败。maxLeverage是平台许可映射，不测试/实现虚构的策略专属上限 |
| L-05 安全与既有行为 | 保留70项中的同键同体恰一次重放/两次未知停止、409、401/403、402/charged、billing absent、budget/deadline及Human/trade断言；patch经过新壳仍有效，不引入通道回落、收费放宽、额外job或恢复增强；无token/headers泄露 |
| L-06 抽取与scope | spec_from_file_location动态import及非scripts cwd下调用有效；import无业务文件/网络/环境读取，qd.agent_submit/agent_call/poll_job/_http_send调用时patch生效；原CLI从2502行净减少且无删空白凑数/无关迁移，无反向import/新SDK/HTTP栈；仅allowlist变更、无真实凭据/业务网络 |

杠杆子集开发执行（已按此完成并验收）：既有70项基线→新增拒绝/贯通失败断言→三函数最小抽取及透传→同命令全量回归；Tester独立复验，Reviewer独立审查，不要求16研究/上线或B-001重跑。冻结命令（项目根）：`PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/tests -p 'test_*.py' -v`。解释器已核实Python 3.12.13，不重复环境探测；记录实际命令/cwd/已核实版本来源、原始stdout/stderr与工具原生exit，拒绝立即STOP，不换形状/解释器/执行器绕行。无真实Agent compile/backtest/job或官方业务请求；fixture只证明客户端离线行为。本Principal不运行上述命令。

### 三件套新增离线验收集合（t_1b635d49冻结）

本轮新增 tests/test_grid_research.py（stdlib unittest、synthetic/offline、项目根 .venv），沿用上文冻结 discover 命令自动纳入；既有79项（含原70项回归与杠杆断言）不得删改放宽。最小断言集合：

1. build_cells 参数化与日期：默认值产出恰好16唯一cell（PUMPUSDT/AAVEUSDT/JUPUSDT/SUIUSDT×W1..W4，cell_id与SPEC §3.1一致）；显式传入不同合约清单/窗口结构/锚点按同一规则产出对应cells且不依赖默认硬编码；重复目标去重；自锚点直接减3k日历月、缺同日月末截断、闰年（参数化锚点构造：2028-08-31减6月得2028-02-29、2027-08-31减6月得2027-02-28、冻结锚点2026-10-31减6月得2026-04-30）；窗口半开不重叠；空/重复/重叠/未到达锚点拒绝。
2. wire endDate：逐窗 API endDate=半开end前一天（SPEC §3.1表四窗逐项断言）。
3. derive_geometry：synthetic日线算例得L/U/g_pct/N/格线数N+1，g_pct∈[0.45,1.5]、评分取最大、数值平分取较小N；最多365根且close<=start；2..364标short_history；不足2根/缺口/来源不明/无可行N拒绝且不改阈值。
4. margin_metrics 算例：1000→1200→900 净损益=-100、R=-10%、峰值P=1200、MDD=25%（P(t)=max(1000,max_{s<=t}E(s))口径）；E<=0/缺bar→N/A+原因；压缩曲线不冒充独立核验。
5. Sharpe：完整等频15m正例（rf=0、ddof=0、K=35040）与异常矩阵——零波动、收益样本不足、任意E<=0、缺bar均N/A+原因；原生Sharpe=0不覆盖该判定。
6. cross_liquidation 状态机：long_only向下根、short_only向上根、等量对冲、A近零（1e-12*max(1,qL+qS)）无有限解/已越线、H(p0)<=0 already_at_or_below_maintenance、p<=0 no_positive_solution、无仓N/A(no_position/no_long/no_short)、缺字段N/A；mL=mS=0.005主+0.004/0.006敏感、f=0.0005；容差按§7（1e-12/1e-10、H近零1e-8*max(1,|E0|,|(qL+qS)*p0|)）；拒绝NaN/±Inf。
7. summarize_cells/reconcile_audit：四行汇总列结构与缺失N/A+有效数n/4；审计连续性按预期时间集合逐bar核对（缺任一bar→unknown/fail）、缺seq/冲突时间拒绝、破产跳回调如实FAIL并标后续审计不全、GRID_INIT_V1/GRID_AUDIT_V1/GRID_END_V1前缀与字段完整性、不把summary长度当全量。
8. 载体格式：research-manifest.json（schema_version=1、16项状态机planned/.../not_submitted_due_to_stop、canonical JSON拒绝NaN）、comparison.csv 4行、cells.csv 16行、CELL.*.json/jsonl字段投影，在测试临时目录以synthetic样例验证；不写真实报告目录 data/reports/2026-10-31-neutral-grid-four-window/。

三件套执行纪律与上文一致：无凭据/网络/业务请求、不import执行策略、PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 项目根 ./.venv 解释器、记录实际命令/cwd、原始stdout/stderr与工具原生exit，不伪造输出。实现顺序：既有79项基线→新增失败断言→grid_research纯函数→策略实例五文件生成→全量回归；Tester独立复验，Reviewer独立审查；不要求16研究/上线或B-001重跑。真实job提交/服务加载/缓存操作仍禁止。

以下表与旧命令保留B-001已验收/完整研究候选要求，不是本次新增任务或门禁；其中Leverage/Compatibility已按上表客户端子集启用并验收，Dates/Geometry、Metrics、Liquidation、Risk/Audit、Resume/Safety的离线纯函数子集按上方三件套小节启用（真实引擎fixture与完整研究验收仍延期）：

| 组 | 必测与通过条件 |
|---|---|
| B001-Native | synthetic raw_v=100、m=0.01时base=1，quote=sum不重算；六列不变；m缺失/0/负/NaN/Inf、非direct、原始v缺失/非正、历史区间未知均明确失败；不默认1 |
| B001-Consumer | 标准volume只转换一次；raw与m不丢失，错误不变空列表/跨所fallback；并发两symbol/翻页无旧证据串用，reload替换metadata；旧cache缺marker与新旧混合UNKNOWN |
| NonGate | Gate spot第7原字段映射不变；Binance spot/swap以及现有OKX/Bybit/Bitget/HTX解析/请求参数无差异，不新增metadata请求 |
| Leverage | （未来候选）旧默认false/1；显式1000/true/10；value/target_value/target_percent与quantity链路差异；10000不是100000；partial数量复用不再乘十 |
| Dates/Geometry | （未来候选）16去重、直接减月/月末/闰年、API end前一天；最大365、截止恰等start可用、2..364短历史、无前视与无可行N不放宽 |
| Metrics | （未来候选）SPEC算例1000→1200→900，收益-10%/MDD25%；Sharpe完整等频/零波动/非正/缺bar/有效分母；压缩漏峰反例UNKNOWN |
| Liquidation | （未来候选）long_only/short_only/等量对冲、A=0、无正根、期初已越线、无仓/单侧无仓/缺字段、敏感性与根残差；单池1000不双算 |
| Risk/Audit | （未来候选）两腿gross非净额、旧库存+所有余单、同bar多成交、权益下跌、撤余单、缺seq/冲突时间、破产跳回调；bar证据不升级tick |
| Resume/Safety | （未来候选）同身份只GET、键/体/attempt跨重启、409/失败/收费停止、billing absent不free、组deadline/预算不重置、无token/headers泄露、仅原5 Agent operation |
| Compatibility | 本次客户端部分见L-01/L-05/L-06；旧70项原样通过、动态import/patch/cwd兼容、Human/trade无迁移、CLI净减少；研究扩展仍未启用 |

原B-001执行顺序与132项记录保留，不重做；下列第3条为其历史冻结命令，本次不执行。旧CLI70须由本次开发/验证实际重跑（本Principal不跑），不是沿用run3397代替；当前命令以上文为准，下列第1/2条仅保留旧形式，第4条原生引擎fixture仍为未来研究验收，不属客户端本次门禁。

原T2命令记录（“第一条已执行”仅指原run3397，不是本Principal；其余历史/未来归属见上段）：

1. 项目根：`PYTHONDONTWRITEBYTECODE=1 /home/pascal/workspace/yquant-investment/.venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/tests -p test_quantdinger.py -v`。
2. 项目根：同一解释器 `-m unittest discover -s skills/strategies/strategy-lab/tests -p 'test_*.py' -v`。
3. 子模块backend_api_python工作目录：`PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -p no:cacheprovider tests/test_native_crypto_public_client.py tests/test_gate_swap_volume_units.py -q`；该.venv为后端自身规范测试环境（已含flask与pytest），不安装依赖、不改conftest.py、不换其他解释器。
4. T4单一杠杆引擎fixture须复用现有runtime类的定向测试，不增加生产runtime改动；确切已有测试入口由T3读取后交接，不能凭未见名称宣称已运行。

工具若拒绝命令，保存精确拒绝并STOP，不换解释器/包装绕过。fixture仅工具测试，不是官方历史或真实研究证据。

## 9. 加载、迁移与回滚

原T2只读现场（非当前重查）：systemd user unit quantdinger-api.service、quantdinger-celery-worker.service当时均active；工作目录均为子模块backend_api_python，API监听127.0.0.1:15000。app/tasks/agent_jobs.py:25-40证明Agent backtest由Celery任务导入_run_backtest，不能只刷新HTTP API就声称worker已加载。还存在scheduler/evaluator/trading-worker等unit，不在本轮重启范围。

没有hot reload已生效证据。主控若批准最小加载：先只读确认无在途目标job、实际源码挂载和进程身份，再判断API与Celery worker是否需受控重启；Celery承载其它任务，影响不能假定只限本轮。无需重启frontend/Kafka/Redis/数据库/交易worker。这里是影响说明，不是部署/重启授权，不执行命令、不另起实例。

上述为原完整研究加载影响；本次G-02只读候选的具体加载对象另见§11.8，不据本节顺带重启Celery/evaluator。三函数迁出与三件套均已离线验收；本轮实现范围仅§11.1，策略实例五文件仍只读、不本地import执行、不部署。旧8结果/12目录/06-001保留；无数据库schema/数据迁移、代理/env变更、部署/重启/缓存操作，G-01不能由重启推定闭合。

回滚由实现者按本卡前的逐文件基线恢复自己差异/新文件，不git reset/stash/clean，不还原上游dirty。回滚新代码后同样需主控判断实际加载；已产生错误单位研究结果保留并标invalid，不删除、不重算报表追认。t2只写文档，无生产回滚动作。

## 10. 未闭合项、决策请求与门禁

| ID | 具体未闭合点 | 已有证据 / 最小所需决定 |
|---|---|---|
| G-01 | 修复后的实际加载与旧volume缓存兼容不能由native/crypto局部修改独立保证 | market_data两层缓存可提前命中且无单位版本；共享frame无可依赖TTL，Redis可选。属线上/完整研究前置：离线阶段保持未闭合，不阻塞合法离线实现/Verify/Review；进入线上或完整研究前需主控选择经批准的受控加载/旧cache退出证明，或明确授权最小Gate限定cache版本接缝并修订allowlist；不请求全量缓存平台/删除数据 |
| G-02（C-002） | 唯一方案已设计，尚未实现/运行中API真实读取/16行内容冻结 | RFC D-06、SPEC §9、本Design §11；G-02=OPEN，真实I/O/Agent凭据消费/必要加载需主控具体授权；离线通过不关闭 |
| G-03（C-003实际前检） | 全部真实Gate swap的历史volume适用性及官方同bar原始对照缺证，不仅PUMP | native_crypto.py:618-626/652-681/760-778共用校验，真实当前metadata无历史有效区间，synthetic接缝仅测试；本次不实现G-03，不默认1、不填0、不回退、不开放真实注入 |

G-01/G-02/G-03是线上加载/完整研究执行的前提决定，不是离线子阶段的前置；三者当前均未闭合，full readiness=DEFERRED，不因离线文件齐全而升PASS。G-03中真实数值留T4验证，获取/验证路径须在进入完整研究前明确；无路径不能把UNKNOWN当可实施的完整研究承诺。主控已按Pascal离线授权收窄：当前T3交付与停止条件以本修订及父卡body为准，原完整研究验收保持不变、不悄然消失。

本轮G-02 Design可交接：RFC/SPEC V1.5与Design V1.4的唯一方案、接口、数值与权限一致，精确增量/测试见§11；旧三件套为ACCEPTED不重新实现。本卡完成仅文档设计done，主控读回后派G-02最小Implement→独立Verify→独立Review，不增独立DesignGate卡、不改原T6。真实读取/冻结未完成故G-02仍OPEN；G-01独立、G-03仍OPEN、full readiness=DEFERRED。新拒绝立即STOP，不重放取消审计、不换包装/解释器/执行器。不能因后续实现/真实验收未执行而循环阻塞已完整交付的本Design。

共享dirty归属：workspace-baseline四文件、本轮前已存在RFC/SPEC、原策略/规范资产均不计T2修改；子模块config/data_sources.py、env.example、test_crypto_proxy_no_proxy_semantics.py是上游proxy变更，完全保留。不读取凭据、不开浏览器、不调用业务、不修改任何unit/配置、无commit/push。

## 11. G-02训练OHLC与提交前冻结（本次唯一待实现增量）

### 11.1 精确实现allowlist与职责

以下是主控读回后可派发的实现边界，不是本Principal的写入权。路径不得推断扩展；新文件均为拟新增。主仓前缀`skills/strategies/strategy-lab/`：

| 相对路径 | 变更/职责 |
|---|---|
| scripts/grid_training.py（新） | 独立小适配与CLI；调用既有Agent GET、重验原始证据、调用已验收纯函数/生成器、写本主题冻结载体；不承载提交/撮合/SDK |
| tests/test_grid_training.py（新） | colocated stdlib unittest，覆盖来源/时间/短历史、实际纯函数调用、冻结/篡改/预算停止与CLI边界；不修改旧测试 |

子仓根`skills/trading/auto-trading/quantdinger/QuantDinger/`，保持local main，不commit/push：

| 相对子仓路径 | 变更/职责 |
|---|---|
| backend_api_python/app/data_sources/native_crypto.py | 只追加§11.2的独立训练读取方法及专用私有传输helper；复用现有Session/节流/代理/超时，不改旧_get/load_markets/fetch_ohlcv/volume helper或其它venue |
| backend_api_python/app/services/training_ohlc.py（新） | 严格请求解析、实际身份验证、OHLC规范化/coverage/摘要/业务投影；无持久缓存、factory fallback、volume解析 |
| backend_api_python/app/routes/agent_v1/markets.py | 仅klines新增模式分派和训练错误映射；scope R/市场/标的鉴权留在provider前，旧分支原样保留 |
| backend_api_python/tests/test_training_ohlc.py（新） | colocated pytest，Native训练入口/服务纯验证、请求身份/无重试分页/价格与volume隔离；patch网络，不加载真实配置秘密 |
| backend_api_python/tests/test_agent_training_ohlc_contract.py（新） | Flask test client经真实route/decorator，假token lookup与审计持久化边界、provider边界；参数/权限/错误/两模式包络/tenant回归 |
| backend_api_python/tests/test_ai_agent_contract_alignment.py | 追加klines条件参数与响应schema/错误/scope R一致性断言，保留原断言；仅路径/operation集合相等不足以验证本增量 |
| docs/agent/agent-openapi.json | 仅既有GET klines参数、两模式响应schema及400/401/403/502；不新增operation，不改Human spec/MCP |

不得修改：主仓quantdinger.py（已知2472行，G3架构例外范围不再实质扩张）、agent_backtest.py、grid_research.py及两份旧大测试、SKILL.md、策略实例五文件/模板/旧12目录、标准表；子仓crypto.py、kline.py、factory.py、base.py、所有strategy_v2/runtime/cache、配置/units/conftest.py与B-001两份旧测试。无需通过crypto.get_kline透传：新模式不进入OHLCV服务链，故不改crypto.py是有意的最小化决策，不是漏项。旧API与测试断言完整保留。

后续阶段交接仅本主题任务目录中的`implement-handoff.md`、`verify-handoff.md`、`review-handoff.md`；结果仅本主题报告目录`implement.md`、`verify.md`、`review.md`及evidence下同名前缀的原始命令输出/exit/候选摘要，分别由对应角色写自己的文件，不覆盖既有结果。真实数据/冻结文件精确见§11.6，离线阶段仅临时目录synthetic样例，不提前伪造真实载体。无其它源码/测试/文档扩张。

G3边界：定向读取native_crypto.py为896行、crypto.py为1156行、grid_research.py为943行（读取工具所报，不是本卡新基线清单）；训练服务/主仓适配各自单职责，优先保持<=1200行；若拟扩张native超过1200，须按现行G3披露边界/增长/拆分触发条件并独立Review，不用删空行规避。原测试1430行的历史受控增长保留，本次不追加旧大测试。

### 11.2 调用签名、数据流与真实生产来源

以下为拟新增签名，不声称已经存在：

- Native类方法`fetch_training_ohlc(self, symbol: str, *, before_time: int, limit: int = 365) -> dict`，只允许self.id=gate/self.market_type=swap；不得接受外部metadata/synthetic/provenance/endpoint参数。
- Native私有`_get_training_payload(self, url: str, params: dict | None = None) -> Any`，仅被新训练方法调用；沿用`_throttle()`、`_http_session()`、self.timeout/self._proxies及既有公共User-Agent设施；单次GET、禁重定向/禁自动重试，非2xx或JSON结构失败抛NativeCryptoAPIError。不改变原_get行为/签名；不引入HTTP库或代理配置。
- 新服务`parse_training_request(args: Mapping[str, str], *, now_utc: datetime) -> dict`，纯解析；`normalize_training_payload(payload: dict, request: dict, *, observed_at_utc: str) -> dict`，纯验证/规范化；`get_training_ohlc(*, symbol: str, before_time: int, limit: int = 365) -> dict`，唯一服务I/O入口。now注入用于离线测试，生产由服务端UTC时钟产生。
- route仍是既有`klines()`，无新route/operation；鉴权通过后才调用服务。市场/标的权限失败provider调用0，不能在参数解析或模块导入时创建client/取metadata。

流向固定：Agent klines鉴权/模式检查 → 严格训练请求 → 新服务 → `create_native_crypto_client('gate','swap', timeout_ms=CryptoPublicConfig.TIMEOUT, proxy=CryptoPublicConfig.PROXY)` → 独立训练读取 → 纯验证 → envelope。现有create_native_crypto_client定义在native_crypto.py:872附近；CryptoDataSource._init_native_exchange:257-264证明已有同一公共超时/代理构造惯例。不实例化KlineService/CacheManager来取训练，不用CryptoDataSource的跨所/分页/重试流程；route原有全局_kline_service只继续服务旧分支。

每次训练读取使用新公共client，不复用共享kline/metadata状态，最多一个metadata GET加一个日线GET；两者使用相同已配置公共传输，不读取交易凭据。没有分页/重试或动态URL，Session仅使用原生默认无重试adapter，若实际设施启用了隐式重试必须在进入此路径前拒绝并报预算不可约束，不能重试碰运气。

| 字段 | 实际产生位置/交叉验证 |
|---|---|
| exchange_id/market_type | 新Native实例实际id/market_type，和route必填gate/swap逐项相等；不将请求回显当事实 |
| metadata | 既有公共`https://api.gateio.ws/api/v4/futures/usdt/contracts`返回中按原始name精确选唯一目标，保存实际name/type与实际存在的base/quote/settle业务字段；不是load_markets默认值回填 |
| settle/quote=USDT | 实际futures/usdt路径提供结算命名空间；原始name的quote须USDT；原始settle/quote存在则必须一致。缺这些原始可选字段不伪造“原字段”，在provenance记录来源为路径/合约名；name/type或映射所需字段缺失/冲突502 |
| canonical_symbol/native_contract | 授权symbol解析为BASE/USDT:USDT后与实际唯一name=BASE_USDT/type=direct匹配；响应canonical_symbol用该规范形式，native_contract用真实name。按授权表示只允许BASEUSDT、BASE/USDT、BASE/USDT:USDT等无venue别名，须全部round-trip一致；带@venue/其它settle等冲突形式400，不让_native_symbol丢后缀掩盖冲突 |
| source | 实际公共host、`/api/v4/futures/usdt/candlesticks`、本次实际contract/interval=1d/from/to；from=cutoff减limit个UTC自然日，to=cutoff前一秒，不附加limit冲突参数；不是客户端自填来源 |
| 原始行/时间 | 保存provider JSON数组原始业务行及原始顺序/数值类型；t为Unix秒，不误乘为毫秒；规范化open来自t，close为下一UTC午夜，observed_at为取回时刻，available_at等于close，检索时刻独立记录 |

当前生产metadata事实：native_crypto.py:363-378由当前contracts响应构造markets；:652-681只返id/settle/info；:760-778只认可synthetic来源+覆盖bar的有效期。没有真实历史有效区间。新路径不调用该volume helper、不修改synthetic判据，也不宣称取得历史属性/乘数资格。这里直接留原始目标metadata是为了避免load_markets硬编码settle/缺省quote掩盖证据来源；不建设历史metadata库。

`identity_evidence.metadata_raw`只投影name/type及原始存在的base/quote/settle（保持原值原类型），`metadata_sha256`针对该精确对象；`metadata_source`另存实际host/path、retrieved_at、settlement_basis=endpoint_path、quote_basis=contract_name、metadata_scope=current_snapshot、historical_identity_validity=UNKNOWN。不拷贝整张market/info、quanto_multiplier/账户字段/headers。无实际生产上市字段/语义证据，本实现生产`listing_boundary.status=UNKNOWN`，不虚构create_time或额外上市端点；短返回因此可能正确拒绝，不能为了凑齐G-02扩大来源。

### 11.3 HTTP契约、精确包络和兼容

输入严格沿SPEC §9.2：data_mode省略/ohlcv走旧行为；training_ohlc要求market=Crypto、显式exchange_id=gate/market_type=swap、timeframe=1D、before_time为正整数UTC午夜且不晚于服务端now，limit默认365且2..365整数。beforeTime仅单独出现可用；两游标同时出现400；训练单值参数重复出现也400，避免解析器取首/末值不一致。空值/小数/布尔文字不clamp。ohlcv出现新增identity参数400，未知mode400；默认ohlcv的limit=300、1..2000夹取、原游标/错误/包络不变。

API返回`{code:0,message:'ok',data:...}`，训练data字段精确为：schema_version=grid_training_ohlc_v1、data_mode=training_ohlc、status、reason、market、symbol（授权请求表示）、timeframe=1D、count、identity、identity_evidence、source、klines、normalized_sha256、coverage、synthetic=false、volume_status=not_provided、backtest_eligible=false、historical_volume_validity=UNKNOWN。reason成功为null，失败为明确英文机器标识（细节为计数/字段名，不含原始异常）。

identity包含exchange_id/market_type/settle/contract_type/canonical_symbol/native_contract；每个klines对象包含open_time_utc、close_time_utc、available_at_utc、availability_basis=bar_close_boundary、observed_at_utc、open/high/low/close、identity。没有volume、base_volume、有效乘数、closed/provenance_ok外部开关。source包含provider=native_gate、host/path/query、retrieved_at_utc、raw_rows、raw_rows_sha256、provider_request_count（本次实际发送尝试数）、request_policy={automatic_retries:0,pagination:0,redirects:0}及metadata请求留证。HTTP线缆字节不在摘要声明范围。

coverage精确字段：requested_start_utc/cutoff_utc、requested_limit、raw_count、actual_count、unique_count、first_open_utc/last_open_utc/last_close_utc、duplicate_count/conflicting_count/missing_count/misaligned_count/excluded_unclosed_count/excluded_out_of_range_count、short_training_history、listing_boundary。完整样本short=false；无上市证明的短返回short=null而非true，listing_boundary为{status:'UNKNOWN',reason:'listing_boundary_unverified'}。空数组仍须来源/coverage充分留证且status=insufficient_evidence，不成功空包。

摘要统一SHA256(UTF-8 JSON)，sort_keys=true、ensure_ascii=false、separators=(',',':')、allow_nan=false；raw_rows保留原始业务行（包括存在的v/sum，不认证其单位），raw摘要不排序去重/不转浮点。规范化摘要仅对响应klines精确数组；metadata摘要仅对上述白名单原始对象，服务端与客户端同字节规范。价格字符串可规范化为有限float但布尔/空/非正非法，low<=open,close<=high；原始数值NaN/Inf导致无法安全留证则502结构错误，而原始字符串'NaN'可安全留证但价格非法、200+insufficient_evidence。t须严格整数秒，不接受小数/布尔/缺失默认为0。

错误映射使用现有_helpers.error：非法请求HTTP400/code400/message=training.invalidRequest/retriable=false；401/403沿既有鉴权；源网络/结构错误HTTP502/code502/message=training.sourceUnavailable，身份未知/冲突用training.identityUnverified，data=null/retriable=false。details至多{reason:受控机器标识}，不dump异常/payload/认证信息。数据可留证但数量/连续性/价格不合格返回HTTP200/code0/data.status=insufficient_evidence。旧OHLCV错误仍走旧路径，不能改成训练错误。

OpenAPI 3.0.3单个query参数无法用required动态表达两参数间条件：保留公共参数表，description及`x-training-ohlc-constraints`机器扩展明确模式条件、双游标互斥/范围；200 data用oneOf引用`AgentLegacyKlinesData`/`GridTrainingOhlcData`，后者data_mode枚举唯一training_ohlc，新增对象声明required/类型/枚举/限制。alignment测试验证该扩展与route参数表及schema相符；不改成全局limit默认365、不把训练字段设成旧模式必填、不新增MCP工具或operation。

### 11.4 排序、连续性、短上市与无前视

Native单次有界请求，不向前/后续页取价格、不用CryptoDataSource._fetch_ohlcv。先保存raw，再逐条验证t与价格；规范化升序但保留全部重复供coverage报错，不用fetch_ohlcv:646的timestamp字典静默去重。重复即使值相同仍insufficient_evidence；同t值冲突另计conflicting_count。裁剪边界外与close>cutoff的行，分别计数；raw始终保留，被裁行不进入L/U。非午夜对齐/非法价格不伪装可用；影响结论则拒绝。

完整训练要求：最多limit且最少2根、每相邻open相差一个UTC日、末根close恰等cutoff、完整请求区间无缺日；close=cutoff合法，start当天未收盘不可入。同一根open/close可以相等价，但全样本L<U否则拒绝不产ready。数量不能用limit片段截断掩盖额外重复；只能明确裁剪时间越界。

2..364根：必须有真实同产品上市边界证明请求前部在上市前且从首次可用完整日线至cutoff连续，才short=true。上市当日非完整UTC日不能假当完整日；边界证据须明确首个完整日。纯validator可由内部synthetic fixture验证此分支，生产Native不接受调用者证据注入，也无已证上市来源，故真实短样本保持UNKNOWN/insufficient_evidence。小limit契约测试只证明接口，固定16窗一律365。0/1根有确证上市证据为history_insufficient/N/A，否则UNKNOWN；尾缺日/中缺日/短返回无证明不算上市不足。未来取得合格上市来源须先按已有契约核验/明确接缝，不顺手新增端点或读文件业务通道。

available_at=close仅为原SPEC研究约定；observed_at/retrieved_at可能晚于start，不伪造历史下载或发布时刻。历史身份有效期、发布延迟、volume资格UNKNOWN按SPEC §9.3披露但不单独阻止价格初始化；实际identity更名/冲突、来源/coverage未知则影响训练资格，立即STOP。无前视判断针对参数算法实际接收行，不以响应头时间替代。

### 11.5 主仓薄适配、旧纯函数/生成器复用

拟新增公开接口（只在grid_training.py，不加到quantdinger.py）：

- `validate_training_response(data: dict, cell: dict) -> dict`：无I/O，重算raw/metadata/normalized三个摘要，独立由raw推导OHLC/UTC/身份并比对响应，核验source路径/query/范围与coverage/能力标志；返回{status,reason,bars,identity,evidence}。不得仅信data.status或服务端coverage/provenance布尔。
- `prepare_training_cell(cell: dict, data: dict) -> dict`：真实调用上面验证、`grid_research.check_coverage(..., frequency_seconds=86400)`和`derive_geometry`。验证后拷贝规范行加内部provenance_ok=True再传旧函数，外部data自带provenance_ok不能跳过验证。完整365按请求start验coverage；确证短上市按首个完整日到cutoff验coverage并另验前部上市证据，不用连续尾段掩盖缺口。
- `freeze_training(cells: list[dict], responses: dict[str, dict], *, output_dir: Path) -> dict`：纯业务协调+明确本地写盘，恰好默认16目标，任何未知/停止行保留理由；无网络、无策略执行/compile。
- `verify_training_freeze(manifest_path: Path) -> dict`：只读本地清单及所引用内容、重算全部摘要并重验几何/生成物对应关系，修改任一内容或路径身份不一致即拒绝，不修复、不重抓数据。
- `collect_training(*, base_url: str, output_dir: Path, agent_call: Callable, resolve_agent_token: Callable, now_utc: Callable, monotonic: Callable) -> dict`：显式依赖注入，按cell顺序调用既有Agent GET并冻结；无默认捕获patch对象，不传整个qd模块当SDK。token仅显式调用内部resolver消费，不进入argv/清单/日志。CLI执行此函数只在另行具体授权后；实现/离线Verify中仅fake边界。
- `main(argv: list[str] | None = None) -> int`：`--describe`只内存计划/无token/无网络；`--verify-freeze PATH`只本地校验；`--collect --base-url URL --output-dir PATH`只读Agent收集。互斥、无缺省collect，无token明文flag，无compile/backtest/execute/fetch-direct选项。不把布尔flag视为人类授权凭据。

模块只按相邻绝对文件路径显式加载grid_research与quantdinger，导入无env/文件/网络读取；动态spec_from_file_location、非scripts cwd仍有效，不全局改sys.path，不反向修改旧模块。复用`qd.agent_call('agent_klines', base_url=...,token=...,params=...,timeout=...)`和`qd.resolve_agent_token`，不调agent_submit。params固定data_mode/market/symbol/timeframe/exchange_id/market_type/before_time/limit，limit=365；agent_whoami至多一次且只存市场/scope授权核验结果，不落账户原响应。调用已有`grid_research.build_cells()`和`validate_run_anchor`，不复制日期矩阵/几何算法。HTTP return headers当场丢弃，不进入证据。

旧生成器实际接口为`grid_research.generate_strategy_source(*,cell,template_sha256,geometry=None)`，它转调实例research.py:269-360。调用必须提供完整真实geometry，不使用其90/100/8 synthetic默认；template_sha256读取并校验既有TEMPLATE_SHA256锁定，完整generator链/模板/纯函数文件字节摘要进入证据。身份instrument由实际canonical_symbol构造`Crypto:BASE/USDT@gate:swap`并经后端既有parse_instrument round-trip单测校验，不能把BASE_USDT直接塞INSTRUMENT；主仓不import后端服务。

重要保护边界：旧生成器硬编码EVIDENCE_READY=False、SOURCE_KIND=offline_example_not_research_evidence及TRAINING_SUMMARY未知（实例research.py:310-320），不能把其输出冒称已可执行研究。G-02生成的是按真实geometry冻结但仍锁定的候选源码；参数文件是训练证据权威，清单显式`code_kind=locked_candidate`、`code_execution_eligible=false`，保留代码内锁与审计unknown文字，不AST改写常数、不解锁、不重写生成器/策略。所谓ready仅训练参数ready，不代表backtest/策略ready；该锁不阻碍本次训练价格/参数冻结验收。任何未来试图提交须先在原研究授权内关闭G-01/G-03并审核代码资格；若需改变源码内容，必须重新预冻结并明确标supersedes，旧hash不得追认成新提交源码。本阶段不实现该未来提交/解锁路径。

### 11.6 本地证据、参数与冻结清单的精确载体

基目录`data/reports/2026-11-01-grid-g01-g02/`，不与原四窗口研究报告混写。首次真实授权执行前，创建独占`evidence/g02-training/`目录（已存在即STOP，不覆盖/删改/自动resume），只能写以下固定文件：

- `evidence/g02-training/access-check.json`：脱敏的目标origin、操作白名单、授权引用（非秘密）、whoami校验结果/预算，不存token/headers/user原响应。
- 每cell `evidence/g02-training/CELL.training.json`：已安全投影的完整训练data（raw/metadata/normalized/coverage/source/count/约定），CELL只由默认矩阵产生。
- 每个训练ready的cell `evidence/g02-training/CELL.parameters.json`：schema_version=grid_training_parameters_v1、完整cell/identity/时间/训练/geometry/资金成本/限制/source_hashes和generator_sources；另存params_sha256于清单（不在自身对象内循环散列）。
- 每个训练ready的cell `evidence/g02-training/CELL.strategy.py`：旧生成器静态输出UTF-8精确字节，不import/执行；code_sha256记清单。无可行/N/A/未知行这两路径为null+原因，不补默认代码或参数。
- `evidence/g02-training/budget.json`：累计whoami/klines各cell尝试、provider上限预留与实际回执数、开始/已耗墙钟、stop_reason；同进程单写者，不实现跨重启恢复/预算刷新。
- `g02-training-freeze.json`：schema_version=grid_training_freeze_v1、默认矩阵/anchor、16行items、budget_ref、limits、limitations、status=complete/incomplete、body_sha256（只对去除body_sha256的完整对象计算）。

每parameters完整参数对象包含L/U/N/g_pct/grid_lines/score、n_max=200/g_lower=0.45/g_upper=1.5、old_cost_assumption_pct=0.14/new_score_cost_pct=0.20/actual_fill_rule、训练数量/区间/short/listing、available_at/observed_at/availability_basis、窗口/市场身份，initialCapital=1000/leverageEnabled=true/leverage=10/commission=0.0005/slippage=0.0005/funding=not_modeled/dynamic_anchor=false及生成器源码身份。不能仅写L/U/N而遗漏成本或实际代码依赖。

每清单item固定cell_id/window/start/end/cutoff/identity、status/reason、evidence_ref及其文件SHA、raw_rows_sha256/metadata_sha256/normalized_sha256、training_range/count/last_available/observed_at/short/listing、geometry、parameters_ref/params_sha256、code_ref/code_sha256/code_kind/资格false、generator_sources（path+字节SHA）、job_id=null/run_id=null。item状态仅ready/no-feasible-geometry/history_insufficient/insufficient_evidence；STOP后未读取目标用insufficient_evidence+reason=not_read_due_to_stop，无原始文件则ref/hash=null，不假造响应。清单incomplete不算G-02关闭；确证N/A/no-feasible是有证结论，不删目标。

对象摘要用§11.3规范（复用已存在grid_research.canonical_json，不改其实现），源码/证据文件校验按实际字节，明确区分对象摘要与文件摘要。先独占写各证据/参数/代码文件，读回计算/校验内容，最后写清单及body摘要，原子完成标志不早于文件成功；失败保留已有文件+预算/stop清单，禁止覆盖旧证据或临时声称complete。manifest引用限制在本次目录与明确只读生成器源路径，不接受外部任意文件输入当行情来源。verify-freeze对16行、源文件、各参数对象、策略内容和所有引用逐项复核；未来提交方必须再次调用并核对完整资格，hash存在不是提交授权。

### 11.7 新增离线验收、命令与停止语义

全部stdlib unittest/后端既有pytest，synthetic/offline；网络/数据库/凭据/业务/服务动作0。后端用已有testing app，patch token lookup、_touch_token_last_used、_audit及持久边界；显式禁真实requests/urllib/socket和缓存I/O，provider fake仅边界，不能mock掉整个route/prepare/derive。token假值只在fixture内。沿既有环境，不安装依赖、不改conftest或反复环境探测。

| SPEC编号 | 主断言/承载 |
|---|---|
| G02-01 | 新Agent契约测试经真实GET/decorator验证401、scope/market/instrument 403调用0；参数互斥/边界/小数/重复/未来/非午夜400调用0；默认OHLCV逐字段等旧包络，原错误不改 |
| G02-02 | 新后端训练测试取实际目标metadata与路由路径，name/type/quote/settle缺失冲突、别名映射不符502；主仓独立重算三摘要及raw→normalized对应，分别篡改字段/顺序拒绝 |
| G02-03 | synthetic完整365与纯validator两日确证短上市成功；close=cutoff可入、窗口内/未收盘剔除计数；缺尾/缺日/相同重复/冲突重复/错位/非法价/字符串NaN/数值Inf/0或1/无证明短返回不得ready；raw顺序不被正常化覆盖 |
| G02-04 | 按 §12 修订：同一四合约 Gate fixture 训练得 OHLC 且仍无 volume/backtest_eligible=false；公共 Native 入口使用有效当前元数据正常返回单次换算 OHLCV，历史适用性 unknown，不注入 synthetic parser、不新增公共 metadata 参数。训练无缓存/无frame/无fallback；NonGate/spot回归保持 |
| G02-05 | 新主仓测试spy实际build_cells/check_coverage/derive_geometry/generate_strategy_source调用；不信任provenance=True，16唯一状态行/完整params/锁定代码；逐个篡改raw/metadata/normalized/参数/代码/生成器/清单及尾部未读取行拒绝或如实incomplete；no-feasible与N/A不补参 |
| G02-06 | OpenAPI+alignment新增参数/条件/响应/error/scope测试；真实route结果字段匹配schema；主仓discover含旧153及新测试，旧API/断言不放宽。B-001无需重新跑原132项整链，但触及native须下面最小NonGate/volume回归 |
| G02-07 | 此项真实运行中API证据不得以离线测试替代；mock只检验预计请求与格式，本轮记NOT_EXECUTED，不假称runtime已加载/真实取数已通过 |
| G02-08 | 假钟/假GET验证全局累计预算、提前预留、限额/超时/401/403/402/charged/5xx/身份矛盾/UNKNOWN停止且后续调用0；无POST/headers/token输出；无新进程自动加载/缓存/DB动作 |

后续Implement自检及Tester独立执行的冻结命令（本Principal不执行）：

1. 项目根：`PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/tests -p 'test_*.py' -v`。
2. 子仓backend_api_python目录：`PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -p no:cacheprovider tests/test_training_ohlc.py tests/test_agent_training_ohlc_contract.py tests/test_ai_agent_contract_alignment.py tests/test_agent_current_contract.py tests/test_native_crypto_public_client.py tests/test_gate_swap_volume_units.py -q`。

后端.venv为既有B-001测试环境，命令未在本卡试跑；若依赖/导入/安全策略阻挡，保存实际失败STOP，不安装/改env/换runner。测试防护须在任何可能I/O前生效，不能以testing名称默认安全。原始命令/cwd/解释器来源/stdout/stderr/native exit及每G02编号覆盖与未执行项必须分列。离线通过仅代码工具通过，真实验收另列。

### 11.8 真实验收预算、运行加载影响及主控检查

本卡不执行真实验收。具体授权对象是既有运行中Agent API目标origin（前检记录为http://127.0.0.1:15000，不是本次实测地址）、GET whoami/klines及CLI内部必要Agent token消费、默认四合约四截止、§11.6本地证据保存；不授权Human/研究端直连Gate。源码实现许可不自动包含网络/Agent token或服务动作。

潜在加载对象仅quantdinger-api.service内提供Agent klines的Gunicorn worker，影响同服务其它HTTP请求与在途连接；服务实例数量/实际工作目录/候选挂载由主控在真正实施时确认。训练是同步只读HTTP，不依赖Celery/evaluator/交易worker，无理由顺带加载它们。若候选实现后运行中worker未加载，主控先另行具体确认受控reload/restart对象/影响/时机，worker不执行systemctl、不另起本地API当真实验收。健康/mtime/本地新import只能局部证据；须将经独立验收的候选文件身份与实际挂载/worker加载证据及同运行中API的training响应对照，无法证明就runtime_loaded=NOT_VERIFIED。

预算作用于整个G-02而非每合约/每阶段：whoami<=1、klines每cell<=1且总<=16、后端实际公共请求含metadata/日线/任何隐式尝试<=50、墙钟<=1800秒，无自动重试/分页/替换标的/拆组刷新。collector每cell调用前保守预留该Native方法最多两个provider请求及一个klines尝试，实际回执provider_request_count核对，失败无回执仍计预留不返还；余量不足不发请求。新Native分支固定至多两次GET，禁重定向/自动重试，以定向测试验证；无法约束内部请求则不开始。中断后本次目录已存在即STOP，不通过重启/resume重置预算，也不新建目录继续同一验收；续取必须交主控具体决定。

始终job/compile/backtest/Evolution=0，交易/数据库/缓存写删/长期调度=0。上述数据库0指本工作不主动访问/变更业务数据库；运行中Agent既有鉴权lookup/last_used/audit由原装饰器正常执行，不绕开或关闭，主控授权的GET须明确包含这种既有附随行为，不能宣称GET没有任何服务器内部写入。

401/403/402、charged>0或billing.status=charged、5xx/超时/预算、安全拒绝、摘要/身份矛盾、影响训练资格的UNKNOWN立即STOP保存已有证据，剩余目标留未读取原因，不换token/通道/执行器；billing absent不等于free。既有agent_call保留原收费错误；collector对data.billing存在时核查，缺失记absent，不把header/raw账户写盘。无可行几何/有证上市不足可记录N/A后继续，其它insufficient_evidence不能伪装上市不足。

主控关闭G-02须同时确认：独立Verify/Review的候选身份与默认回归；必要加载和真实GET/凭据消费具体授权；同运行中API的16目标实际取数/有证N/A及全部参数内容预冻结、独立verify-freeze无矛盾、业务POST=0。不能仅mock或本地新进程关闭。当前未实现/未测试/未真实读取，G-02=OPEN、G-03=OPEN、historical_evidence=UNKNOWN、full_research=DEFERRED、原T6不解除。

G-01现成证据已定向读取：evidence/g01-cache-audit.json记录observed_at=2026-11-01T10:51:24.127499+00:00，限定SCAN各matched=0、无payload读取/写删，结果明确OPEN_PENDING_RUNTIME_AND_CACHE_IDENTITY_PROOF；这不是全局无缓存证明、非原子快照，不提升PASS。本训练分支不读写那些缓存，不等待/轮询G-01；若未来必须加cache身份接缝，待主控针对文件/对象具体授权后另修设计，不能挪用本allowlist。

### 11.9 本阶段收口与版本/证据身份

文档语义映射：RFC V1.5 D-06 → SPEC V1.5 §9.1..9.7 → 本Design V1.4 §11.1..11.8。RFC/SPEC中“Design V1.3待子卡同步”是父阶段交付时点描述，本卡完成由本Design与design-handoff记录同步已达V1.4；本卡无权改前两文档，主控读回时可在其权限内最小更新阶段引用，不更改冻结需求。无业务契约冲突/开放方案问题。

已签收SHA仅复用trio-closeout：grid_research.py=19f69b9959ce6b0fe7d14f3e54477f5b1d2953654ea363b113bf0fe4b5a9d33a；test_grid_research.py=913ff228d8b777ae8ce84c876fbc3845eeaa3e1bb3af78a200cf09c49071bb14；不是本卡当前重测。新Design/RFC/SPEC SHA=NOT_COLLECTED，取消额外采集不记PASS、不填假SHA；实现/独立验收阶段仍需按授权实际校准候选身份。共享dirty只按本卡两个文档归属，不宣称其它路径clean或还原上游差异。本卡零源码/测试/SKILL/配置变更、零命令/凭据/网络/数据库/服务动作；Markdown工具未运行linter。最小交接完成后kanban_complete，后续派发归主控、不自行建卡。

## 12. 审计 D-01：公共取数局部撤销（Pascal 已确认）

本节落实 RFC V1.6 §9 / SPEC V1.6 §10，优先替代 §2/§3/§10/§11 中旧阶段的公共历史证明阻断及禁止触及此分支的保护范围；其余研究、训练、权限、资金与执行锁不变。采用 Light Flow 两张正式卡（Implement→独立 Verify），主控先同步本三文档；不另建文档阶段或独立 Review，不把局部撤销扩为平台建设。

### 12.1 精确允许文件与实现边界

相对子仓 `skills/trading/auto-trading/quantdinger/QuantDinger/` 仅允许：

- `backend_api_python/app/data_sources/native_crypto.py`：仅 Gate swap 解析/现有证据产生。撤销 synthetic-only 和历史有效期必备阻断；正常当前元数据来源与检索时间如实留在已有字段，历史适用性 unknown。保留单次换算、产品身份/非法乘数/数值检查、线程/页证据隔离与 F-01 最终返回 limit；训练方法和 _get 等不改。
- `backend_api_python/app/data_sources/crypto.py`：仅 Gate swap 消费/重采样接缝。移除历史适用性必须 verified 的公共前提及基于缺研究证明的重采样禁止；保留已知错误单位/身份/必要数值一致性检查。聚合后 volume 直接来自已换算原始 bar 的既有聚合，不再次乘数、不两位舍入；无法保留原生逐根证据时诚实 unknown，不伪造单 bar volume_evidence。不得重写其它 venue/spot、fallback/代理/分页策略。
- `backend_api_python/tests/test_native_crypto_public_client.py`：更新仅被本决策替代的历史拒绝断言，新增正常生产形状成功反例；保留单位、身份、数值、线程/页边界和 F-01 回归。
- `backend_api_python/tests/test_gate_swap_volume_units.py`：正常 Native→crypto 链的最新/历史读取、unknown 披露、重采样与小正量精度、错误身份/单位拒绝；不把旧裸缓存重标为正确单位。
- `backend_api_python/tests/test_training_ohlc.py`：仅更新 G02-04 四合约“公共必须拒绝”的旧断言为公共可读 unknown；保留训练隔离及所有 F-02..F-05 回归，不改训练服务。

本次开工前已有五项修复 dirty 是合法已验收输入，按本次 before 快照做 delta，不得 checkout/restore/reset/stash/clean 或整文件覆盖制造基线。旧 snapshot/缓存、零量撮合语义不在本次范围，不借撤销修撮合、不默认乘数1、不造正 epsilon。训练服务、Agent 路由/OpenAPI、配置、主仓研究源码全部保护。

### 12.2 验证与停止条件

仅离线 fixture/fake HTTP transport，无真实网络、凭据、数据库/缓存/快照或服务访问。先以正常当前 metadata 无 synthetic 取得针对性 RED，再最小修复；禁止回退源码重放 RED。冻结完整命令在子仓 `backend_api_python/`：

```bash
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -p no:cacheprovider tests/test_training_ohlc.py tests/test_agent_training_ohlc_contract.py tests/test_ai_agent_contract_alignment.py tests/test_agent_current_contract.py tests/test_native_crypto_public_client.py tests/test_gate_swap_volume_units.py tests/test_crypto_kline_exchange_matrix.py -q
```

开发自检一次、独立 Verify 一次，分项对 SPEC D01-01..07 给证据，子集不累计成总数；不增加重复全量/相邻模块测试作为新门禁。记录 cwd/命令/原始 stdout+stderr/原生 exit/候选 SHA 和相对 before 的路径 diff，保护文件按本轮基线核验。主仓三文档由主控同步后为保护输入，验证者只读核对一致性，不重测未变的主仓研究工具。

新安全/审批拒绝立即 STOP 留证并 block，不拆命令/换工具/换执行器绕行。遇真实契约外失败或必须扩文件时停止上报最小 delta；全部范围内验收通过则 done，未部署和 G-03 明确在 OUT 不作为本轮代码失败。仅称 D-01 offline 恢复，不称线上可用或历史/16研究通过。不 commit/push/fetch/merge、不改分支/gitlink、不部署重启/回测交易。

## 13. v=0 零成交 bar 合法化实现契约（Pascal 2026-11-03 D1 决策；native 层已实现，消费链 §13.4 待实现）

本节落实 RFC V1.8 §10 / SPEC V1.8 §11，来源诊断报告 `data/reports/2026-11-03-pathb-probe-jup-15m/nomarketdata-root-cause.md`。§13.1/13.2/13.3 的 native 层实现已由 t_aa056536 完成（平台侧 237 passed + 1 xfailed，xfail 为 §13.4 解除前的契约阻断标记；主仓 185 项基线 185/OK/exit 0），剩余实现增量为 §13.4 消费链放行（D2 决策），仍按 Light Flow（Implement→独立 Verify）；不扩 RFC/SPEC/Design 阶段，不解除 16 窗口研究锁，不消耗 QuantDinger job 配额。

### 13.1 校验函数行为变更的精确实现契约

目标文件 `backend_api_python/app/data_sources/native_crypto.py`（当前 896 行量级，§11.1 G3 边界沿用）。现状（2026-11-03 复核，native_crypto.py:838-854）：`_gate_swap_volume_number(value, field)` 对全部调用点统一执行 `isinstance(value, bool) or not math.isfinite(number) or number < 0 or (field != "sum" and number == 0)` 即拒绝。变更契约：

1. **合法化只在 raw_v_contracts 调用点**（_parse_gate_swap_ohlcv 内 `raw_v_contracts = self._gate_swap_volume_number(raw_v, "raw_v_contracts")` 处）。推荐最小实现：该调用点改为 `raw_v_contracts = self._gate_swap_volume_zero_ok(raw_v, "raw_v_contracts")`，其中 `_gate_swap_volume_zero_ok` 为新增私有 static helper，谓词顺序：非数值/null（含 bool、非数值字符串）→ gate.swapVolumeInvalid；`math.isfinite` 失败 → 同上；`number < 0` → 同上（负值边界即 D1"负值"语义）；`if number == 0: return 0.0`（零成交合法分支）；其余正数原样返回（等价于转发 `_gate_swap_volume_number` 原逻辑）。**负零口径（冻结）**：IEEE 754 下 float("-0") == 0 且 -0.0 < 0 为 False，故字面量 "-0"/-0.0/"-0.0" 经 `number < 0` 不拒绝、经 `number == 0` 自然进入合法分支并返回 0.0——即负零按数值相等语义归入零成交，不视为负值；实现**不得**为负零增加符号位特判（copysign 检查等），该特判属于对 D1 边界的外扩。v==0 合法分支返回后，调用点短路：base_volume 直接取 0.0，不进入乘积调用点（无"负零漏进乘积链被零拒绝"的路径）。
2. **base_volume 乘积调用点不动**：`base_volume = self._gate_swap_volume_number(raw_v_contracts * multiplier, "base_volume")` 保持原函数。v==0 分支在调用点短路：raw_v_contracts==0.0 时 base_volume 直接取 0.0，不调用乘积校验（0×有限正乘数=+0.0 无下溢；若未来乘数出现非有限值，乘数校验已先行拒绝，到不了乘积）。raw_v_contracts>0 时乘积零拒绝完整保留（下溢守卫），非有限拒绝保留（上溢守卫）。短路的等价实现（分支在乘积调用前以 `if raw_v_contracts == 0.0: base_volume = 0.0 else: ...` 表达）同样合规，验收以行为为准，不强制函数拆分形态。
3. **sum 调用点不动**：`quote_volume` 对 sum=="0" 本就放行（sum 字段零值合法），缺失仍 None；不改。
4. **校验顺序不变**：合约身份（id/settle/name/type=direct）→ 乘数（缺失 MetadataMissing、非数值/非有限/非正 MetadataInvalid）→ v（本次唯一变更点）→ 乘积 → sum。乘数缺失 + v==0 的组合仍以 MetadataMissing 拒绝。
5. **不动项清单**：五类错误标识与消息、gate_swap_volume_v1 证据对象字段集合、applicability 判定（synthetic 覆盖区间→verified / 当前快照→unknown，v=0 不改变该判定）、线程/页证据隔离、F-01 最终页边界、_get/训练方法/factory.py/runtime 撮合器、NonGate/spot/其他交易所行为；crypto.py 在本条（§13.1 阶段）不动，其消费链谓词变更由 §13.4（D2）单独授权且仅限该节两处。**禁止引入 epsilon 或任何最小流动性下限**；**禁止把零成交 bar 送入任何 volume>0 前提的撮合可用性分支**（runtime 撮合语义维持不动，见 R-01）。

### 13.2 受影响测试逐文件清单（Implement 与独立 Verify 的断言基线）

平台侧 pytest 集合（均相对子仓 backend_api_python/，不含主仓 185 项 discover，后者见 SPEC §11.3）：

1. `tests/test_native_crypto_public_client.py`（27 个测试函数）：
   - **保留不动**：`test_gate_rejects_missing_non_positive_or_non_finite_raw_v` 的参数表 `[None, "", "bad", "0", "-1", "NaN", "Inf", "-Inf", True]` **必须将 "0" 移除**（v=0 不再属于拒绝集合），其余 8 个形态原样保留并必须继续全部通过；`test_gate_rejects_multiplication_overflow_and_underflow`（("1e308","10") 与 ("1e-300","1e-300")）原样保留；`test_gate_invalid_sum_is_not_silently_zeroed` 原样保留；其余身份/乘数/隔离/F-01 回归全部原样保留。参数表唯一允许的删改就是移除 "0" 并同步新增下述独立零成交用例；不允许改写其余断言或放宽消息匹配。
   - **新增（最低集合）**：(a) v="0" 合法零成交 bar 用例——base_volume 精确 ==0.0、raw_v_contracts==0.0、六列长度/顺序不变、证据对象字段集合与既有完全一致、sum="0" 时 quote_volume==0.0、synthetic 覆盖区间 fixture 下 historical_applicability=="verified"；(b) 生产当前快照 fixture（无 synthetic 标记、无生效区间）下 v="0" 用例——applicability=="unknown"；(c) 负零合法化断言——v="-0" 与 "-0.0" 与 v="0" 行为一致（成功、base_volume==0.0），锁定"负零按数值相等归入零成交、无符号位特判"的冻结口径；(d) 乘数缺失 + v="0" 组合仍 MetadataMissing（校验顺序锁定）；(e) raw_v="1e-300" + multiplier="0.0"（非正乘数）仍 MetadataInvalid——非正乘数先于一切 v 语义。
2. `tests/test_gate_swap_volume_units.py`（11 个测试函数）：
   - **保留不动**：`test_gate_swap_unit_error_propagates_without_retry_or_fallback`（五类错误 × 两窗口共 10 组合）、`test_gate_consumer_rejects_wrong_or_unknown_evidence`、`test_gate_old_or_mixed_cache_fixture_cannot_be_relabeled`、`test_gate_consumer_rejects_missing_evidence_fields`、`test_gate_fallback_catches_also_propagate_unit_errors`（7 形态 × 两路径）全部原样保留并通过。
   - **新增**：v=0 消费链用例必须是**独立测试函数**（不得加入 `test_gate_native_to_consumer_preserves_units_projection_and_small_volume` 的参数表——该表含 `assert row["volume"] > 0` 与小正量精度断言，零量不属于该表语义）：v="0" 时 get_kline 正常返回单行、不抛错、不触发 local/public fallback、volume==0.0、raw_v_contracts==0.0、base_volume==0.0、quote_volume==0.0（sum="0"）、volume_unit=="base"、volume_evidence 字段集合完整。**V1.7 增补（D2/§13.4）**：(i) 删除该用例之上的 `@pytest.mark.xfail(strict=True)` 整块装饰器（当前工作树 148-158 行），函数体与断言不动；(ii) 新增重采样路径独立测试函数：全零成交源 bars（bucket>1 的 mock，source rows volume 全为 "0"）经 get_kline 正常返回、聚合 volume==0.0、volume_unit=="base"、volume_historical_applicability=="unknown"（聚合 bar 无逐根证据，不得伪造 volume_evidence）、不抛错、不走 fallback，锁定 crypto.py:648 谓词放宽。
3. `tests/test_training_ohlc.py`（33 个测试函数）：无 v=0 相关断言（训练通道 volume_status=not_provided 不变），预期零变更；若有失败即实现越界（改到训练通道），停止上报。
4. `tests/test_crypto_kline_exchange_matrix.py`：gate swap 行 mock volume 均为正量，预期零变更；失败即实现越界，停止上报。

预期断言净变化：上述两文件合计新增约 5-7 个测试函数/用例组、test_native_crypto_public_client.py 参数表移除 1 个形态（"0"）；除此之外不得有任何既有断言删改放宽。

### 13.3 验证命令、R-01 披露载体与停止条件

冻结命令（子仓 backend_api_python 工作目录，Implement 自检一次、独立 Verify 一次，不重复累计为门禁）：

```bash
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -p no:cacheprovider tests/test_native_crypto_public_client.py tests/test_gate_swap_volume_units.py tests/test_training_ohlc.py tests/test_crypto_kline_exchange_matrix.py tests/test_agent_current_contract.py -q
```

主仓冻结基线（SPEC §11.3，185 项，项目根执行，实现后必须重跑核对 185/OK/exit 0）：`PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/tests -p 'test_*.py' -v`。记录 cwd/命令/原始 stdout+stderr/原生 exit/候选文件 SHA；仅离线 synthetic fixture，无网络/凭据/数据库/缓存/服务动作，job/compile/backtest=0。

**R-01 披露载体**：实现移交物（implement 移交文档）必须逐字包含 RFC §10.3 披露全文——平台 `_liquidity_cap`（runtime.py:1274-1281）对 volume<=0 返回 None（零成交 bar 上模拟撮合器不设 10% 上限），与研究语义"该 bar 网格限价单不成交"存在差异；该差异按 D1 边界不在本修订修复范围。SPEC V1.7-08 以此为验收项：披露缺失即 Verify 不通过。禁止把披露写成"已修复"或顺带改 runtime。

停止条件：任何保护文件越界修改、既有断言删除放宽（除 §13.2 第 1 条 "0" 形态移除与 §13.2 第 2 条 D2 增补 (i) 的 xfail 装饰器删除外）、185 项基线失败或数量≠185、平台侧既有用例失败、必须扩展 §13.4 之外文件范围、安全/审批拒绝——均 STOP 留证上报，不换工具/解释器/执行器绕行。不 commit/push、不部署重启、不触碰缓存与数据库；本节实现完成后 G-01/G-03 状态不变、16 窗口研究锁不解除，16 窗口是否放行由后续卡按新契约另行评估。

### 13.4 消费链 crypto.py v=0 放行的精确实现契约（D2 决策，t_b8db70b3；本节为剩余唯一实现增量）

来源：RFC V1.8 §10.4（D2 契约决策）、SPEC V1.8 §11.2（V1.7-06/V1.8-01）/§11.4；F 卡实测 `data/tasks/active/2026-11-03-v0-zero-trade-bar-legalization/implement-handoff.md` §5。判定依据：§10.2 第 1 条合法零成交 bar 及其「该 bar 网格限价单不成交」研究语义要求 bar 穿过消费链；原 V1.6 §13.1 第 5 条「不动 crypto.py」与该语义构成内部矛盾，D2 按 D1 既有语义收窄修正，不扩权。

1. **精确变更（`app/data_sources/crypto.py`，仅两处谓词字符变更）**：
   - Site A（重采样路径，crypto.py:648）：`if not math.isfinite(candle[5]) or candle[5] <= 0:` → `if not math.isfinite(candle[5]) or candle[5] < 0:`。
   - Site B（单 bar 路径，crypto.py:694-700 谓词）：`not math.isfinite(candle[5]) or candle[5] <= 0 or evidence["base_volume"] != candle[5]` → `not math.isfinite(candle[5]) or candle[5] < 0 or evidence["base_volume"] != candle[5]`。
   - 两处 raise 的标识 `gate.swapVolumeInvalid` 与消息文本（`normalized volume must match positive native volume`）均不变：消息中 "positive" 描述残留拒绝语义（负值/非有限/证据不一致），上游按标识匹配的立即 re-raise 判定不受影响；不新增、不删除、不移动任何 raise/分支。
2. **语义澄清（防误读）**：本变更是消费链数据有效性网关的放宽，不是 RFC §10.2 第 3 条禁止的「把 volume>0 作为前提的撮合可用性分支」——该分支指 runtime `_liquidity_cap` 等撮合语义；runtime 撮合器不动，R-01 披露全文（RFC §10.3）继续有效且差异未修复；不引入 epsilon。
3. **精确 allowlist**：`backend_api_python/app/data_sources/crypto.py`（仅第 1 条两处谓词）与 `backend_api_python/tests/test_gate_swap_volume_units.py`（§13.2 第 2 条 D2 增补 (i)(ii)：xfail 装饰器整块删除 + 重采样 v=0 独立用例）；除此之外任何文件不动（含 native_crypto.py、runtime.py、factory.py、训练服务、主仓源码）。
4. **验证**：§13.3 冻结 pytest 命令（Implement 自检一次、独立 Verify 一次）——预期平台侧全绿（passed，无 failed/xfailed/xpassed；原 1 xfailed 因 V1.8-01 转常规通过，新增 1 个重采样用例，实际总数以实跑为准，既有用例不得减少）；主仓 185 项冻结基线按 SPEC §11.3 重跑核对 185/OK/exit 0。无网络/凭据/数据库/缓存/服务动作，job/compile/backtest=0。
5. **停止条件**沿用 §13.3；不 commit/push、不部署重启、不触碰缓存与数据库；完成后 16 窗口研究锁仍不解除，是否放行由后续卡按新契约评估。

## 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.7 | 2026-11-03 | t_b8db70b3（E2/D2）：§13 状态更新——§13.1/13.2 的 native 层已由 t_aa056536 实现并通过平台侧验证（237 passed + 1 xfailed，xfail 为 §13.4 解除前阻断标记）；§13.1 第 5 条不动项清单将 crypto.py 改列「除 §13.4 外不动」；§13.2 第 2 条增补消费链测试增量（xfail 装饰器删除 + 重采样 v=0 用例）；§13.3 停止条件例外同步；新增 §13.4 消费链 crypto.py 两处谓词放宽（≤0→<0、保留 isfinite/证据一致性校验、标识与消息不变、R-01 不变）精确实现契约；指向 RFC/SPEC V1.8；仅文档，§13.4 实现/验证未发生，job 0、16 锁不解除 |
| V1.6 | 2026-11-03 | t_e5ac39e6：按 Pascal 2026-11-03 D1 决策增 §13——§13.1 冻结 _gate_swap_volume_number 行为变更契约（合法化仅 raw_v 调用点、base_volume 乘积调用点零拒绝保留即下溢守卫、负零按数值相等归入零成交且禁符号位特判、校验顺序与五类错误/证据对象/sum 缺失 null 不变）；§13.2 受影响测试逐文件清单（test_native_crypto_public_client.py 拒绝参数表唯一删改="0" 移除 + 新增 5 组零成交/负零/顺序用例、test_gate_swap_volume_units.py 新增独立 v=0 消费链用例、training_ohlc/matrix 预期零变更）；§13.3 冻结 pytest 命令 + 主仓 185 项基线重跑核对 + R-01 披露载体（implement 移交物逐字含 RFC §10.3，缺失即 Verify 不通过）+ 停止条件；指向 RFC/SPEC V1.7；仅文档，实现/验证未发生，job 配额 0，16 窗口研究锁不解除 |
| V1.5 | 2026-11-02 | 按 Pascal 决策增 §12，修订 §3.3 / G02-04，局部撤销公共 Gate 历史缺证和重采样阻断；保留单位精度/五项修复/训练和研究锁；指向 RFC/SPEC V1.6；离线实现与独立 Verify 已完成（t_8a23ea34），API 进程已受控重启并真实请求验证；研究准入仍未放行 |
| V1.0 | 2026-10-31 | 基于RFC/SPEC V1.1给出B001最小设计及研究工具候选边界；既有70测试真实通过；明确G-01/G-02/G-03路径缺口，T2 BLOCKED，不实现/不释放T3 |
| V1.1 | 2026-10-31 | 续接run3399：按Pascal离线授权分段修订，指向RFC/SPEC V1.2；T3当前仅B-001离线修复allowlist，§4-7薄层/研究/策略转未来未启用候选；G-01/02/03改列为线上/完整研究前置不阻塞离线；offline_design=PASS、full readiness=DEFERRED。主控读回同步校正§2.1四文件归属、当前B001/NonGate测试与未来CLI/杠杆测试边界、纯synthetic解析接缝及迁移表述；不新增业务语义或文件范围。主控二次同步（run3401交接后、Pascal「请继续」授权）：§2.2 crypto.py补齐_fetch_ohlcv两处catch与_fetch_ohlcv_fallback两处catch仅五类gate.swapVolume*单位错误立即re-raise的最小接缝及format_kline精度注意；§8定向pytest解释器改为backend_api_python自带.venv（不安装依赖）。§3.2行为契约、测试断言与§2.2文件边界不变 |
| V1.2 | 2026-11-01 | t_9fddffed/run3409：指向RFC/SPEC V1.3，B-001离线已验收并保护；仅启用§4三函数抽取/杠杆/CLI，核实平台100与manifest许可真实语义，§8冻结L-01..06离线集合与项目根unittest命令；通用evidence/恢复、§5-7及16研究仍未启用，本卡零源码/测试执行/业务 |
| V1.3 | 2026-11-01 | t_1b635d49/run3413：按Pascal明确授权窄启用§5-7三件套待实现契约（grid_research.py纯函数库含参数化build_cells、margin_metrics/cross_liquidation/summarize_cells/reconcile_audit、策略实例neutral-grid-four-window-v1五文件含GRID_INIT/AUDIT/END_V1审计、风险容量检查与公开API限定）；§2.1/§2.2 allowlist同步、§5-7转窄启用实现规格、§8新增三件套离线测试小节、§9/§10收口；§4杠杆子集记录为已验收（79/79 OK、Review APPROVE t_664a588c）；指向RFC/SPEC V1.4；16业务提交/服务加载/缓存/凭据/§4未启用候选仍禁止，本卡零源码/测试执行/业务 |
| V1.4 | 2026-11-01 | t_1f4c8c58：对齐RFC/SPEC V1.5，三件套改为已离线ACCEPTED；§11冻结唯一Agent训练OHLC分支、主仓/子仓精确allowlist与签名、实际metadata/source/UTC/摘要、短历史未知与volume隔离、复用纯函数及锁定生成代码、16行参数/代码预冻结载体、G02-01..08测试与真实授权/累计预算/加载影响；G01现成证据仍OPEN；取消基线采集不重放，本卡仅文档，G02/G03仍OPEN、runtime NOT_VERIFIED、full_research DEFERRED |
