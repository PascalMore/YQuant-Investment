# DESIGN-06-002：中性永续网格四窗口研究与 B-001 最小修复

## 元数据与结论

| 项 | 值 |
|---|---|
| 版本 | V1.1 |
| 日期 | 2026-10-31，Asia/Shanghai（UTC+08:00） |
| 阶段 | T2 Design 分段修订，t_1af91929，run3397 落盘 / run3399 续接 |
| RFC / SPEC | [RFC-06-002 V1.2](../../rfc/06_strategy/RFC-06-002-neutral-grid-multi-window-research.md) / [SPEC-06-002 V1.2](../../spec/06_strategy/SPEC-06-002-neutral-grid-multi-window-research.md) |
| 权威范围 | data/tasks/active/2026-10-30-neutral-grid-research/pipeline-intake.md，含追加最小 Gate 授权 |
| 当前判定 | **离线子阶段 Design Gate PASS（offline_design=PASS）；full readiness=DEFERRED（G-01/G-02/G-03 属线上/完整研究前置，未闭合）；T3 仍由主控读回本修订后解除** |

B-001 最小 Gate 修复的授权已定，技术尚未实施。2026-10-31 Pascal 批准先行交付 B-001 离线修复子阶段：本设计 §3、§3.2、§3.3、§3.4 的换算/拒绝/消费者衔接/缓存限制描述与 §2.2 子模块 allowlist 构成当前 T3 的可执行契约，离线可按 §8 的 B001 组断言实现并验收 `offline_unit_fix`；§10 G-01/G-02/G-03 保持未闭合，属于线上加载/训练通道/历史取证前置，不阻塞合法离线实现/Verify/Review，也不因离线文件齐全而给 full readiness PASS。Agent 薄层与研究协调（§4、§5）及策略实例（§6）为未来未启用候选，当前禁止实现；完整研究路径裁定前，T3 只按离线 allowlist 执行。本卡不自行改阶段范围、放松 SPEC 或创建新图。

仅有文档/离线工具核验，不代表平台已修复、服务已加载或16研究通过。Funding 保持 not_modeled；不做双所增强、切换、跨源比较、新 Agent 端点或交易系统改造。

## 1. 输入、基线与已验证事实

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

### 2.1 本 T2 实际写入 allowlist（本次分段修订共四文件）

1. docs/design/06_strategy/DESIGN-06-002-neutral-grid-multi-window-research.md（本文件）。
2. data/tasks/active/2026-10-30-neutral-grid-research/t2-handoff.md。
3. docs/rfc/06_strategy/RFC-06-002-neutral-grid-multi-window-research.md。
4. docs/spec/06_strategy/SPEC-06-002-neutral-grid-multi-window-research.md。

上述 RFC/SPEC 修改仅同步 Pascal 已批准的离线分段决定；原 run3397 的两文件范围为历史。禁止修改实现、策略、技能或子模块，不改原五点最终研究标准。

### 2.2 T3 精确 allowlist（主控读回本修订后生效；父仓薄层/研究文件为未来未启用候选，当前禁止实现）

当前生效范围仅为下表中的子模块四文件；父仓各文件本轮禁止实现。T4 当前仅独立离线 Verify，PASS 可进入原 T5 独立离线 Review；原 T6 保持 blocked，16 业务不得提交。

以下父仓文件仅为未来完整研究候选，当前禁止修改；其中 t3-handoff.md 是当前离线交接允许路径，不受此未来候选限制：

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

新研究实例仅一个目录，避免复制16套工具：`skills/strategies/strategy-lab/strategies/neutral-grid-four-window-v1/`，仅 README.md、spec.md、config.json、research.py、strategy.py 五文件。config只数值参数；16单元市场/窗口/训练/冻结参数保存在任务清单，不把字符串塞入 numeric config。research.py是协调入口；strategy.py由平台沙箱执行、本地不得import。旧12目录及旧结果只读，不迁移或改写。

子模块允许文件（均相对子模块根）：

1. backend_api_python/app/data_sources/native_crypto.py：仅 NativeCryptoPublicClient 的 Gate swap 元数据/单位分支，及仅被该分支调用的新私有 helper；允许在 __init__ 初始化这一分支的有界证据状态。不改其他venue、spot、_float全局语义、网络/代理函数。
2. backend_api_python/app/data_sources/crypto.py：仅 CryptoDataSource.get_kline 的 Gate swap 结果衔接和该特定单位失败的处理。此文件有必要：native六列本身无法携带原始张数、适用性、单位证据，现有format_kline仅传六项且异常可被吞掉。不允许在此再乘一次乘数。「该特定单位失败的处理」按run3401交接补齐为让§3.2五类错误能真正上抛的最小接缝：_fetch_ohlcv 的分页retry catch与外层catch、_fetch_ohlcv_fallback 的两处catch，仅为 gate.swapVolumeMetadataMissing、gate.swapVolumeMetadataInvalid、gate.swapVolumeHistoricalUnverified、gate.swapVolumeInvalid、gate.swapVolumeEvidenceMissing 的 NativeCryptoAPIError 立即 re-raise，可复用仅识别这五类错误的私有helper；其它错误、产品、venue、网络、分页与重试语义不变，get_kline 自身仍保留对同类错误的直接处理。另注意公共 base.py format_kline 会将volume四舍五入两位：Gate 分支必须在其允许范围内保留精确已归一化 volume，不得使小正值变0；不改 base.py。
3. backend_api_python/tests/test_native_crypto_public_client.py：Gate swap单位失败复现与原有多所回归。
4. backend_api_python/tests/test_gate_swap_volume_units.py（新）：消费者字段/错误传播、单位证据缺失及cache前置限制测试；不添加生产cache实现。

不授权 app/services/strategy_v2/market_data.py、backtest_cache.py、runtime.py、instrument_rules.py、Agent routes/OpenAPI、公共配置或生产unit。若需要其中任一才能闭环，先报告缺口，不能凭此候选表旁注自行扩张。

## 3. B-001 最小适配方案

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

只有已有、可审计的同合约历史有效证据覆盖请求bar时，历史请求才可返回研究可用的基础币volume。现有代码没有给native传历史快照的既有接口，故本设计不虚构一个自动取证路径、不新增持久化系统：未知适用性按上节错误fail closed，T4保存UNKNOWN并停止目标提交。T3可用明确synthetic有效区间fixture证明换算逻辑，但不得将fixture/当前metadata用于真实历史PASS。若主控只授权先修单位链路，则其验收是转换/阻断工具行为，不是历史B-001业务闭合。

当发现确有可复用历史快照入口时，必须先证明其产品、有效期和来源，再在本设计修订精确接缝；禁止临时硬编码PUMP乘数或给当前快照伪造长期有效期。

当前离线成功用例通过 Gate 分支私有的纯解析/换算接缝注入明确标为 synthetic 的元数据及适用区间，覆盖 native→crypto 消费链；不为此增加 fetch_ohlcv 的公共参数或真实历史输入通道。生产 load_markets 当前快照不含已验证历史区间时，实际 Gate swap 历史请求仍按 historical_applicability=unknown 拒绝。测试可验证换算成功不表示生产历史路径可用。

### 3.4 缓存兼容与停止规则

旧裸六列/旧frame的volume可能仍为张数，不能通过数值大小猜单位，也不能“缓存再乘一次”修复。新证据字段缺失、单位版本不符、部分新旧行拼接，均UNKNOWN；严禁重标旧PNL。

native的证据页只服务本次返回页，不能作为历史cache权威。旧market_data共享frame和KlineCache可在native前命中，因此仅改native/crypto不能保证旧缓存已退出；§10 G-01列为真实加载前提。候选最小运维路径是主控批准后在无在途job时让实际消费者加载新代码，并等待旧缓存失效且验证未再命中旧单位；不得清Redis/数据库、改key、改变请求窗口/产品来躲cache。共享frame没有本次可依赖的TTL，不能仅等待6小时就假定安全；Redis是否启用本卡未读环境、未知。

本次不执行任何reload/restart/cache删除/配置变更。若选择代码级版本化cache，属于额外文件范围，需要主控明确授权后修订设计，不偷塞入crypto导入时清cache。

## 4. Agent 薄层局部抽取与兼容契约（未来未启用候选，当前禁止实现）

迁移仅现有 build_agent_backtest_body、billing_contradiction、agent_backtest 的实现到新 agent_backtest.py；quantdinger保留同名同签名兼容壳（新参数keyword-only有默认），不迁移Human、通用HTTP、凭据解析、Budget、poll_job、判定模块。新模块无文件/网络/环境读取副作用。

为保持动态文件导入及monkeypatch，兼容壳在调用时显式传入现有agent_submit、agent_call、poll_job、new_idempotency_key、LabError及Budget实例；新模块不从quantdinger反向import造成双加载。新模块由壳以相邻绝对文件路径加载，不要求测试/用户cwd在scripts，不全局sys.path注入。先运行旧70项，再抽取、再原样回归；spy-close-research对CLI helper import继续有效。

新增参数：builder/agent_backtest keyword-only `leverage_enabled=False, leverage=1.0`；CLI agent-backtest新增 `--leverage-enabled`、`--leverage`，默认不变；仅显式启用且有限1..平台已支持上限，关闭时不得静默接受非1。研究显式1000/true/10，九个body白名单字段不增删，不传sourceId/persist。参数/manifest不符在POST前失败；读回executionAssumptions缺失为UNKNOWN，不能用请求体填回执。

返回现有metrics/context/sampledArrays/billing等字段保持兼容，追加明确业务投影 `evidence`（logs、原生权益/仓位/订单成交抽样、historyStorage、audit、instrumentRulesSnapshot、dataProvenance、executionAssumptions、positions、attribution、计数）。保留压缩标识，不写全HTTP响应；安全字段过滤必须递归且覆盖日志文本脱敏。Agent job.result扁平层读取，不走Human run详情。

幂等增强只由研究协调器保存稳定键和已知jobId；已有agent-backtest一次流程默认行为不改。新增内部参数可接收固定submit键、已知jobId和receipt回调，compile键独立。POST之前写盘同体摘要与键，202立刻先保存jobId再GET；已知job只GET。崩溃发生在提交后未落receipt时也只允许使用原键同体且累计最多一次重放；尝试计数跨重启保存，未知不产生新键。

2502行文件通过移出流程实现获得净减少，禁止把新研究逻辑放回CLI；不以删除空行达标。新模块各自保持单一职责，若无法净减少或发生无关迁移，停止并交回设计。

## 5. 研究协调与数据/参数接口（未来未启用候选，当前禁止实现）

纯函数接口冻结（新grid_research.py，不是已存在API）：

- `build_cells(anchor_utc) -> list[dict]`：固定合约顺序PUMP/AAVE/JUP/SUI，每合约W1..W4，共16唯一目标；日期严格按SPEC §3.1，不接受运行时改锚点。
- `check_coverage(bars, identity, start_utc, end_utc, frequency_seconds) -> dict`：核对每个预期bar、重复冲突、时间对齐与close<=end，不采用平台98%容忍代替。
- `derive_geometry(closed_daily_bars, start_utc) -> dict`：只取前置已收盘最多365根；2..364标短历史，缺口/来源未知不成功；N与成本按SPEC §3.2，平分较小N。
- `margin_metrics(bar_close_rows) -> dict`、`cross_liquidation(snapshot, mmr, close_fee) -> dict`、`summarize_cells(cells) -> dict`：见§7，未知为null+reason。
- `reconcile_audit(logs, cell) -> dict`：验证§6连续性、来源、native计数/净值；不能把summary长度当全量。

清单schema_version=1，固定16项字段遵循SPEC §4；每项状态为planned/prechecked/submitting/submitted/succeeded/history_insufficient/insufficient_evidence/failed/not_submitted_due_to_stop。N/A和未提交均保留null jobId/runId及原因。canonical JSON使用sort_keys、紧凑分隔、UTF-8、拒绝NaN；SHA256包括cell/完整市场/时间/源码/参数/资金成本/数据身份。编译源码先静态纯生成、不在本地import策略，manifest需leverageAllowed和正确instrument。

逐合约共享一个deadline与预算累计，不因resume重置：最多4目标job、总外层<=8、数据请求<=50、墙钟<=1800秒、Evolution=0。8不是备用搜索/失败重跑额度。跨进程恢复保留已耗时、提交次数与data请求；无法证明剩余预算则STOP。未知/失败/取消/workerInterrupted/409/鉴权/收费矛盾即停止全部后续提交，生成剩余未提交目标行。

C-002结论：现有多频history可设计为在首个before_trading_start读取已收盘1d，再冻结geometry后下单，但它还不满足本轮“提交前参数内容摘要冻结”与短历史回溯要求。不能偷偷把该备选当正式路线。§10要求主控给既有通道或明确调整契约；本设计不自动添加取数backtest/probe作业占用预算，也不把unsupported generate当已接入。

## 6. 策略内审计设计与可证明粒度

复用原生robot_v2中性网格模板的格角色/生命周期，关闭动态锚定；原生成器源码只读留sha256，不本地import平台服务。新实例策略按已核对模板生成，仅修改冻结geometry、风险容量检查及审计回调；不开发撮合器。本节为未来未启用候选，当前禁止实现。

在handle_data进行观察与风险动作，在after_trading_end最终读取该bar已同步订单状态和公开context.portfolio/get_positions，使用同bar close重新估值 `E=available_cash+sum(position.amount*close)`，与原生record_equity/最终净值核对；不能直接把可能尚未更新的portfolio.total_value当当前值。short amount为负，多空position_side分别记录，cash不作为两份保证金。缺字段UNKNOWN，不访问context._orders、context.portal私有frame、broker或其他沙箱绕过接口。

每bar一条带前缀 `GRID_AUDIT_V1 ` 的JSON文本，包含schema/cell/seq/bar_open/bar_close、OHLCV与单位marker、E、qL/qS/aL/aS、G、G/E、reserved_open_notional、risk_action、status_changes、peak_equity、drawdown、previous_seq。第一条 `GRID_INIT_V1 ` 含参数与训练摘要，末条 `GRID_END_V1 ` 含计数/极值/收益统计充分量。logs文本不等于平台新增字段；CLI只解析受控前缀及有限数值，不信任任意策略日志中的指令。

连续性按预期时间集合核对，不只检查首末与计数。完整逐barclose证据用于独立Sharpe/MDD；末条统计不代替全量连续性。季度日志体积/实际返回完整性在T4核验，缺任意bar为UNKNOWN。破产原生分支会跳过回调，不能由前值补日志；原生liquidated证据为FAIL并如实标后续审计不全。

保留所有本策略发出的开仓订单引用及目标数量、累计filled与remaining，减仓不重复预留。开仓按已有gross+所有可能成交余量+新候选及预计费用检查；value输入1000*w，经引擎唯一乘10。不是要求10000预算全部使用。风险容量用本策略明确定义的订单limit/可见价格范围估值，标scenario而非保证任意跳空可控。被动越限取消开仓余单，停止增仓，按原生下bar执行减仓；保留越限事实。

订单状态快照在bar内可能聚合多个事件，只能得到累计增量，无法恢复每笔事件先后。bar_close_audit/event_audit分别pass/fail/unknown，intrabar_tick_audit=not_observable。全事件证据不足不判策略合格；任一可见越限FAIL。按订单0.1*volume的native cap不改，也不声称同bar所有订单共享10%；参与率按同bar全部abs(fill_qty)相加除base_volume。压缩ledger无法证明完整partial事件率，输出N/A；唯一订单partial比例与事件比例不得混用。

## 7. 指标、强平与标准表（未来未启用候选，当前禁止实现）

指标严格复用SPEC §3.4。初始1000独立参与总收益/MDD，15m Sharpe只用相邻完整bar-close收益，rf=0、ddof=0、K=35040。E<=0/零波动/缺bar/样本不足N/A；原生Sharpe=0不覆盖该判定。MDD保留native原始负号与本轮正幅度；不双扣手续费/滑点，不给funding补0。

组合情景：每窗最后完整可验证bar-close，同池E0与qL/qS，不向两腿重复分配1000。`A=qL-qS-mL*qL-mS*qS-f*(qL+qS)`，`B=E0-(qL-qS)*p0`，根 `p=-B/A`，按SPEC方向/无仓/无根/已越线状态输出。主mL=mS=0.005，敏感性0.004/0.006，f=0.0005，仅研究假设；可用保证金不明标UNKNOWN，p0可用close但标last_not_mark。

浮点比较统一：数量/价格等使用abs_tol=1e-12与rel_tol=1e-10；A近零阈值 `1e-12*max(1,qL+qS)`，H近零与方程残差阈值 `1e-8*max(1,abs(E0),abs((qL+qS)*p0))` USDT。根与p0在对应价格容差内即already_breached；拒绝非有限输入。记录公式版本cross_linear_v1、实际残差/容差，不用四舍五入后判方向。风险2.5与MDD35的比较保留原始精度，容差仅用于数值核对，不作为放宽业务阈值。

四行汇总固定列遵循既有backtest-comparison-standard；数值格式“均值（W1/W2/W3/W4）；n/4”，缺失写N/A+原因，均值不剔除亏损/不合格窗。恰好16明细，主结论分别tool_status/research_status/qualification；不额外设正收益或Sharpe阈值。四个独立1000池不是连续复利年账。

T4/T5输出载体冻结（本T2不创建）：

- 任务目录 `research-manifest.json`：16计划/去重/键/预算/状态，单写者原子替换；原旧evidence不覆盖。
- `data/reports/2026-10-31-neutral-grid-four-window/report.md`、`comparison.csv`（4行）、`cells.csv`（16行）。
- 同目录evidence内每cell `CELL.result.json`（允许字段投影）、`CELL.audit.jsonl`（受控日志）、`CELL.metrics.json`（独立公式与核对）、`CELL.parameters.json`（前置训练与源码）、`CELL.volume.json`（官方同窗对齐、原始证据与缺证）。
- 提交receipt以每cell独立 `CELL.receipt.json` 保留允许字段；追加读回不覆写原始receipt，未知响应不能假造。data忽略不代表提交/远程备份。

PUMP固定首/中/末bar和partial bar核对不能用派生raw=v/m作为官方第二份证据；必须有真正原始请求身份、同UTC记录及元数据适用性。Agent当前未提供这些字段的原始官方业务读取能力，不能由CLI自行直连补齐，见§10。

## 8. 测试与实现顺序

当前离线子阶段先写失败测试再实现，全部用 backend_api_python 自带 .venv 且禁本地策略import。新测试名称可按场景组织，以下为必须断言行为：

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
| Compatibility | （未来CLI候选）旧70项原样通过，动态文件导入与patch有效，cwd独立、导入无I/O，Human/trade无语义迁移，CLI净减少；本次不改CLI、不重复执行旧70项 |

当前离线子阶段执行顺序：B001失败复现/最小转换与消费者→B001及NonGate定向离线回归→T3交接。旧CLI70回归只复用run3397基线记录，不作为本次新增验证，不重复执行；Agent局部抽取、杠杆、纯研究计算/清单/模板及其测试当前禁止实施。当前冻结命令仅下列第3条；第1/2/4条为未来未启用候选，不是本次门禁。

预期命令（除第一条本轮已执行外，其余为未来验收命令，未运行）：

1. 项目根：`PYTHONDONTWRITEBYTECODE=1 /home/pascal/workspace/yquant-investment/.venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/tests -p test_quantdinger.py -v`。
2. 项目根：同一解释器 `-m unittest discover -s skills/strategies/strategy-lab/tests -p 'test_*.py' -v`。
3. 子模块backend_api_python工作目录：`PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -p no:cacheprovider tests/test_native_crypto_public_client.py tests/test_gate_swap_volume_units.py -q`；该.venv为后端自身规范测试环境（已含flask与pytest），不安装依赖、不改conftest.py、不换其他解释器。
4. T4单一杠杆引擎fixture须复用现有runtime类的定向测试，不增加生产runtime改动；确切已有测试入口由T3读取后交接，不能凭未见名称宣称已运行。

工具若拒绝命令，保存精确拒绝并STOP，不换解释器/包装绕过。fixture仅工具测试，不是官方历史或真实研究证据。

## 9. 加载、迁移与回滚

本轮只读发现 systemd user unit：quantdinger-api.service、quantdinger-celery-worker.service均active；工作目录均为子模块backend_api_python，API监听127.0.0.1:15000。app/tasks/agent_jobs.py:25-40证明Agent backtest由Celery任务导入_run_backtest，不能只刷新HTTP API就声称worker已加载。还存在scheduler/evaluator/trading-worker等unit，不在本轮重启范围。

没有hot reload已生效证据。主控若批准最小加载：先只读确认无在途目标job、实际源码挂载和进程身份，再判断API与Celery worker是否需受控重启；Celery承载其它任务，影响不能假定只限本轮。无需重启frontend/Kafka/Redis/数据库/交易worker。这里是影响说明，不是部署/重启授权，不执行命令、不另起实例。

当前离线阶段仅修改§2.2四个子模块路径及t3-handoff，不新增CLI模块/兼容壳/策略实例；这些迁移只属未来研究候选。旧8结果/12目录/06-001文档保留。进程重启不消除持久cache，旧frame兼容不能靠重启口头解决。无数据库schema/数据迁移，不改代理/env。

回滚由实现者按本卡前的逐文件基线恢复自己差异/新文件，不git reset/stash/clean，不还原上游dirty。回滚新代码后同样需主控判断实际加载；已产生错误单位研究结果保留并标invalid，不删除、不重算报表追认。t2只写文档，无生产回滚动作。

## 10. 未闭合项、决策请求与门禁

| ID | 具体未闭合点 | 已有证据 / 最小所需决定 |
|---|---|---|
| G-01 | 修复后的实际加载与旧volume缓存兼容不能由native/crypto局部修改独立保证 | market_data两层缓存可提前命中且无单位版本；共享frame无可依赖TTL，Redis可选。属线上/完整研究前置：离线阶段保持未闭合，不阻塞合法离线实现/Verify/Review；进入线上或完整研究前需主控选择经批准的受控加载/旧cache退出证明，或明确授权最小Gate限定cache版本接缝并修订allowlist；不请求全量缓存平台/删除数据 |
| G-02（C-002） | 无前视、同产品训练样本在目标提交前冻结的既有可用通道未闭合 | Agent klines当前无显式产品/venue与来源契约；多频warmup365对短上市失败，warmup较小又只回溯较小范围；目标内初始化不能冒称提交前已冻结参数内容。属线上/完整研究前置：离线阶段保持未闭合，不阻塞合法离线实现/Verify/Review；进入完整研究前需主控提供已核验既有读取路径；不自动新增端点/probe作业/调整SPEC |
| G-03（C-003实际前检） | PUMP历史乘数适用性及官方同bar原始对照尚无合法来源闭环 | load_markets仅当前快照、旧rules为fallback；当前受限Agent返回无原始v/m/effective证据。修复可以fail closed，但无法靠当前快照产生合格历史数据。属线上/完整研究前置：离线阶段保持未闭合，不阻塞合法离线实现/Verify/Review；进入完整研究前需主控提供可审计既有证据/允许通道；不要求设计前先完成业务取证、不默认1，不擅自直连官方业务API |

G-01/G-02/G-03是线上加载/完整研究执行的前提决定，不是离线子阶段的前置；三者当前均未闭合，full readiness=DEFERRED，不因离线文件齐全而升PASS。G-03中真实数值留T4验证，获取/验证路径须在进入完整研究前明确；无路径不能把UNKNOWN当可实施的完整研究承诺。主控已按Pascal离线授权收窄：当前T3交付与停止条件以本修订及父卡body为准，原完整研究验收保持不变、不悄然消失。

T2 gate（分段修订后）：三层独立存在、父身份与dirty归属正确、精确文件/接口/失败行为/回归/回滚齐备，离线Design Gate据此判PASS（offline_design=PASS）；full readiness=DEFERRED（G-01/02/03 未闭合），不因文件齐全给full PASS。原T3 t_7bf9d3fa仍由主控读回本修订后解除，本卡不操作子卡。T3 gate仍是实现及离线自检，不提交16业务；B001组为当前唯一测试范围。T4当前仅独立离线Verify，PASS可进入原T5独立离线Review，原T6保持blocked；16业务提交仍须完整研究路径闭合并通过相关独立前检。未知/不合格真实报告保留，主指标缺失最终不得PASS。

共享dirty归属：workspace-baseline四文件、本轮前已存在RFC/SPEC、原策略/规范资产均不计T2修改；子模块config/data_sources.py、env.example、test_crypto_proxy_no_proxy_semantics.py是上游proxy变更，完全保留。不读取凭据、不开浏览器、不调用业务、不修改任何unit/配置、无commit/push。

## 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0 | 2026-10-31 | 基于RFC/SPEC V1.1给出B001最小设计及研究工具候选边界；既有70测试真实通过；明确G-01/G-02/G-03路径缺口，T2 BLOCKED，不实现/不释放T3 |
| V1.1 | 2026-10-31 | 续接run3399：按Pascal离线授权分段修订，指向RFC/SPEC V1.2；T3当前仅B-001离线修复allowlist，§4-7薄层/研究/策略转未来未启用候选；G-01/02/03改列为线上/完整研究前置不阻塞离线；offline_design=PASS、full readiness=DEFERRED。主控读回同步校正§2.1四文件归属、当前B001/NonGate测试与未来CLI/杠杆测试边界、纯synthetic解析接缝及迁移表述；不新增业务语义或文件范围。主控二次同步（run3401交接后、Pascal「请继续」授权）：§2.2 crypto.py补齐_fetch_ohlcv两处catch与_fetch_ohlcv_fallback两处catch仅五类gate.swapVolume*单位错误立即re-raise的最小接缝及format_kline精度注意；§8定向pytest解释器改为backend_api_python自带.venv（不安装依赖）。§3.2行为契约、测试断言与§2.2文件边界不变 |
