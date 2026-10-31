# SPEC-06-002: 中性永续网格多窗口研究契约

## 元数据

| 项 | 值 |
|---|---|
| 版本 | V1.2 |
| 状态 | T1 契约 PASS 保留；T2 已按 Pascal 离线授权分段修订至 V1.2：B-001 修复要求与最小范围不变，新增离线子阶段执行/验收；技术 pending，未实施、未研究验收 |
| 日期/作者 | 2026-10-31，Asia/Shanghai（UTC+08:00）；YQuant Principal，t_cfccfe2c / t_1af91929 |
| 来源 RFC | [RFC-06-002 V1.2](../../rfc/06_strategy/RFC-06-002-neutral-grid-multi-window-research.md) |
| Design | docs/design/06_strategy/DESIGN-06-002-neutral-grid-multi-window-research.md V1.1，已由独立 T2 分段交付 |
| 权威输入 | data/tasks/active/2026-10-30-neutral-grid-research/pipeline-intake.md |

## 1. 摘要与完成语义

本 SPEC 冻结四 Gate USDT 线性永续合约、四独立三日历月 15m 窗口、前置参数初始化、1000 USDT 保证金/10x 单次放大、真实权益指标、gross 风险审计及全仓组合情景。只复用原生回测，结果不可由本地撮合替代。工具 PASS、研究完整、策略合格分别判定。

B-001 为已知平台单位缺口，见 §8。依据 pipeline-intake 追加决策，最小 Gate 修复授权等待已解除，技术仍 pending；T1 PASS 仅表示修复要求及最小范围冻结，不是平台或16研究 PASS。主控已读回 RFC/SPEC 并按 Pascal 离线授权解除既有 T2 门禁；T2 Design 不要求先修代码。离线子阶段（Gate swap 单位换算、缺证拒绝、消费者衔接、synthetic/offline 测试）可在运行加载与历史取证之前先行实现并验收，`offline_unit_fix` 独立 PASS 不等于 `runtime_loaded`/`historical_evidence`/`full_research_status` 通过。T3 实现→T4 真实独立验证→T5 Review 确认前不得称已修好；16业务提交须先通过 T4 相关独立前检。原 run3395 BLOCKED 为历史事实，后续真实研究可以得出 no-qualified-baseline、历史不足或证据不足，但主指标缺失不能最终 PASS，不能伪造十六次成功。

## 2. 范围与文件约束

T1 仅允许新建/修改以下三个文件：

- docs/rfc/06_strategy/RFC-06-002-neutral-grid-multi-window-research.md
- docs/spec/06_strategy/SPEC-06-002-neutral-grid-multi-window-research.md
- data/tasks/active/2026-10-30-neutral-grid-research/t1-handoff.md

Agent 薄层抽取、研究实例与扩展规范文件 allowlist 仅在未来完整研究子阶段生效，当前禁止实现，作为未来未启用候选冻结；届时不能由 T3 自行扩张，CLI 扩展仍须先局部抽取、Human/trade 行为不变、不要求无关 judgment 全量迁移；研究辅助代码仅协调原生引擎、计算、审计、输出，不建引擎/SDK/常驻服务。

QuantDinger 子模块仅有 B-001 最小例外：T3 按 T2 Design 精确文件/函数 allowlist 修改现有 backend_api_python/app/data_sources/native_crypto.py 的必要 Gate swap 单位/元数据分支、确有消费者必要时的 app/data_sources/crypto.py 单位衔接及对应测试；其余子模块修改禁止。不得改 runtime 撮合、资金模型、生产配置、Binance/spot/其他交易所行为；不做双所整体适配、新切换、跨源对照、新 Agent 端点或扩大16目标矩阵，不建历史元数据平台/数据库迁移。缓存兼容、缺元数据处理与回归细节已由 T2 Design 冻结：缺证/未知在解析与消费两侧 fail closed，返回成功空列表或跨所 fallback 均为失败；缓存命中限制按 G-01 保持未闭合，属线上/完整研究前置，不阻塞合法离线实现/Verify/Review。既有 proxy dirty 按 b001-submodule-baseline.json 排除归属，不修改/还原。

数据库、代理、白名单、账户、生产配置、部署、绑定、发布、真实或 Demo 交易、长期调度仍禁止；禁止 commit/push、reset/stash/clean、新卡/新图、依赖安装/升级、新环境、覆盖旧 evidence、浏览器/JWT/其他凭据。仅使用 Agent 已批准 operation；unsupported 不回落 Human。若真实 E2E 需运行中进程加载源码变更，T2 列现有 unit/最小重启影响交主控判断，不自行重启/部署/另起实例，不把离线 PASS 当实际生效。任务授权不豁免 headless 安全策略，拒绝后不换解释器或包装绕过。

## 3. 功能规格

### 3.1 F-001：冻结矩阵与时间

锚点 A=2026-10-31T00:00:00Z，是已到达的 UTC 午夜；不称 2026-10-31 整日已结束。边界 B(k)=从 A 直接减 3k 个日历月，缺同日时月末截断；Wk=[B(k),B(k-1))。不是向前滚动递归减月。全部 bar 以 UTC 开始时刻标识，15m 的 close_time=open_time+900 秒，只有 close_time<=end 且已收盘才可入窗。

| 窗口 | start（UTC，含） | end（UTC，不含） | API startDate | API endDate（含该整日） | 预期15m根数 |
|---|---|---|---|---|---|
| W1 | 2026-07-31T00:00:00Z | 2026-10-31T00:00:00Z | 2026-07-31 | 2026-10-30 | 8832 |
| W2 | 2026-04-30T00:00:00Z | 2026-07-31T00:00:00Z | 2026-04-30 | 2026-07-30 | 8832 |
| W3 | 2026-01-31T00:00:00Z | 2026-04-30T00:00:00Z | 2026-01-31 | 2026-04-29 | 8544 |
| W4 | 2025-10-31T00:00:00Z | 2026-01-31T00:00:00Z | 2025-10-31 | 2026-01-30 | 8832 |

API runner 会将 endDate 扩为 23:59:59；wire endDate 必须为半开 end 前一天，不传半开 end 日期。原生 runner 按 timestamps<=end 筛选，实际返回时戳仍需复核。旧 2026-08-01 起点与新 W1 不同，不合并去重身份。

市场身份固定 `venue=gate, product=USDT-settled linear perpetual, market_type=swap, frequency=15m`；原生 instrument 采用已验证 parser 的带 venue/swap 标识，必须 round-trip 读回一致，不从简称推断成功。以下十六条为目标，不是完成记录：

| cell_id | 合约 | 窗口 |
|---|---|---|
| PUMPUSDT-W1 | PUMPUSDT | W1 |
| PUMPUSDT-W2 | PUMPUSDT | W2 |
| PUMPUSDT-W3 | PUMPUSDT | W3 |
| PUMPUSDT-W4 | PUMPUSDT | W4 |
| AAVEUSDT-W1 | AAVEUSDT | W1 |
| AAVEUSDT-W2 | AAVEUSDT | W2 |
| AAVEUSDT-W3 | AAVEUSDT | W3 |
| AAVEUSDT-W4 | AAVEUSDT | W4 |
| JUPUSDT-W1 | JUPUSDT | W1 |
| JUPUSDT-W2 | JUPUSDT | W2 |
| JUPUSDT-W3 | JUPUSDT | W3 |
| JUPUSDT-W4 | JUPUSDT | W4 |
| SUIUSDT-W1 | SUIUSDT | W1 |
| SUIUSDT-W2 | SUIUSDT | W2 |
| SUIUSDT-W3 | SUIUSDT | W3 |
| SUIUSDT-W4 | SUIUSDT | W4 |

coverage 必须包含预期数/实际数、首末时间、唯一时间戳数、重复/缺失/错位/未收盘数量与市场身份。不能只凭首末范围或平台 tolerance 推断完整。上市前/无法取全窗：N/A+history_insufficient，保留该目标行，不发截短窗口；其他缺口：insufficient-evidence，不前向填价、不填零。计划冻结后运行顺序按合约列表、每合约 W1→W4；真实失败按 §3.8 停止，剩余行标 not_submitted_due_to_stop，不造 jobId。

### 3.2 F-002：每窗初始化与旧算法解释

训练输入：同 venue、同 swap 日线，截止 close_time<=start，最多最后 365 根已收盘日线；start 本日未收盘日线不可用。最少两根、数量/范围/实际可用时刻逐窗记录。上市后历史短于365可使用现有连续历史，显式 short_training_history；不足两根、缺口或来源不明不得默认参数成功。禁止利用窗口内/结束后的 high/low 或复用旧 spot 极值作正式无前视筛选。

L=min(low)，U=max(high)，要求 0<L<U。对整数 N=3..200，g_pct=100*((U/L)^(1/N)-1)，保留 0.45<=g_pct<=1.5；score=g_pct/C_round_trip_pct，选择最大值，数值平分按较小 N 决定，网格线数=N+1。无可行集合输出 no-feasible-geometry，不改格距或 N 上限。

旧 derive_grid_params.py 常数评分成本=0.14%，输入明确为 gate spot；新评分 C=100*2*(0.0005+0.0005)=0.20%，是可解释的线性往返成本近似，不代表原生每笔限价都会加滑点。记录 old_cost_assumption/new_score_cost/actual_fill_rule；固定正成本下选 N 的排序不因单纯成本比例变化而变成收益优化。不得把此基准称已做收益优化或参数搜索。

每窗参数来源记录训练产品、日线区间、数量、最后收盘时刻、L/U/g/N、参数内容摘要、生成器源码路径/版本/sha256、提交源码sha256；冻结后不得按结果改参。动态锚定本轮关闭，原生中性角色划分/格生命周期保持；无额外优化或进化。参数文件和策略代码不得本地 import 执行；由原生沙箱 compile/backtest 验证。

### 3.3 F-003：唯一杠杆传递

- 初始真实保证金 M0=1000 USDT，API initialCapital=1000，leverageEnabled=true，leverage=10。这是模拟配置，不操作交易所账户。
- 初始名义容量预算 B0=M0*10=10000 USDT，中性 CELL_BUDGET_PCTS 合计1。order_value 输入=M0*w_i，由引擎乘10；成交单位为基础币。禁止把 initialCapital 改10000，或把 strategy value/B0 再乘10。
- 原生 quantity/target_quantity 路径不乘杠杆，复用成交数量退出/再入也不能再乘10。必须核验 value/target_value/target_percent 与 quantity 两类路径及部分成交。
- CLI 未显式要求杠杆时维持既有 false/1 默认；新研究必须显式 10x，compile manifest 必须允许 leverage，result.executionAssumptions 读回核对1000/true/10和成本。缺失为 UNKNOWN，不能用请求替代回执。
- commission=0.0005、slippage=0.0005、funding=not_modeled，保持原生限价/市价各自实际成交规则，不在后处理中重复扣费或额外扣一次滑点。

### 3.4 F-004：保证金指标与有效均值

无外部资金流：E(t)=1000+累计已实现净损益(t)+浮动损益(t)，包含所有已建模成本；核对原生权益会计，不把 short cash credit 当可自由再次分配的独立保证金。净损益=E(T)-1000；R_M_pct=100*(E(T)/1000-1)。

P(t)=max(1000,max_{s<=t}E(s))；MDD_pct=100*max_t((P(t)-E(t))/P(t))。统一正幅度，保留引擎原始负号值及峰/谷时刻；E<0时 MDD 可超过100%，不截断为合格值。35%阈值含等号；equity_stop_loss=-35%不是同一峰值回撤约束。

Sharpe 使用完整等频15m保证金权益：r_i=E_i/E_(i-1)-1，无风险=0，年化因子 K=365*96=35040，S=mean(r)/std_population(r)*sqrt(K)，ddof=0。首项是第一可用 bar-close 至下一 bar-close 的收益；初始保证金单独用于总收益与MDD，不把无对应15m时距的初始化跳变强塞Sharpe。至少两项收益且std>0；零波动、样本不足、任意E<=0、缺bar均输出N/A+原因；原生默认Sharpe=0不覆盖该规则。记录native periodsPerYear以核查与冻结频率一致性，差异不得隐藏。

压缩权益无法重算完整等频 Sharpe。优先在原生策略允许回调记录完整逐bar权益/统计充分量并核对最终净值、样本数、峰谷与原生值；或使用已经证明未压缩的原生结果。单纯从1200点不等距压缩曲线计算后宣称独立核验通过，禁止。

每列均值 mean_j=sum(valid_j)/n_j；N/A不计零且每列显示n_j/4，不采用只保留盈利/合格窗口的幸存者均值。`均值（W1/W2/W3/W4）`固定顺序，N均值可小数但不是可执行N。收益均值非全年累计、Sharpe均值非全年Sharpe；不把四独立1000池拼成连续复利。有效研究窗、指标有效数、合格窗分别计数。

### 3.5 F-005：250% gross 与可证明粒度

G(t)=sum_l |q_l(t)*mark_l(t)|，同合约多/空分别绝对值相加，gross_leverage=G/E，要求E>0且G/E<=2.5。E<=0为失败/破产；不得输出0杠杆表示通过。

挂单不计当前G，但所有未成交/部分成交的开仓余量必须预留；累计库存和同一bar多个挂单成交都计入。开新仓前评估已有仓位+所有可能成交开仓余量+新增候选、交易成本、价格变化下的权益，不能只限制max_open_orders或单笔金额。减仓订单不得当增加风险扣两次；多空不净额抵消。权益下降/价格跳空可能使既有仓位被动越限，必须记录并停止增仓、撤余单、按既定原生时序提交减仓，而非事后把越限删掉。预算是容量上限，不要求满10000名义持仓。

审计记录至少逐15m bar-close覆盖全部实际bar：time、E、long/short数量/均价/估值、G、G/E、开仓余量保留、风险动作、订单状态变化计数、历史峰值、MDD。可在原生日志保留逐bar证据及累计统计；T2须设计可验证格式/连续性，不能新增平台端点或访问私有Broker状态。缺少任一bar、日志截断/不一致即UNKNOWN。

原生回调并非每笔成交后钩子；OHLC内开盘、挂单匹配、保护、收盘顺序不是逐tick真实路径。下采样600持仓和1500订单不足以证明全程<=2.5。必须分别输出 `bar_close_audit=pass/fail/unknown`、`event_audit=pass/fail/unknown`、`intrabar_tick_audit=not_observable`；可见任何实际事件越限即FAIL。只有bar-close证据最多叫bar_close_pass，不能叫无条件实时合规/策略已合格推荐；若强制全事件合格要求而原生取不到，则research insufficient-evidence并上报最小平台缺口，不自行降级。

### 3.6 F-006：全仓组合强平情景

这是冻结的研究假设，不宣称复刻 Gate 历史阶梯/标记价/强平收费规则。每池只有本合约；四合约之间不共享资金。固定观察点为该窗口最后一个完整可验证bar-close，完整证据另附观察时间；不得把策略当时已平仓的历史最大仓位混充期末仓位。无期末持仓输出N/A(no_position)，可另列历史风险时点但不替换主列。

设期末共同参考标记价p0、当前总权益E0，基础币多头数量qL>=0/空头绝对数量qS>=0，方向均价aL/aS；E0已含两腿浮盈亏和已付费用。冻结头寸不再交易、不计funding，不重复将1000分配给两腿。情景价格p>0：

E_s(p)=E0+(qL-qS)*(p-p0)
MM_s(p)=mL*qL*p+mS*qS*p
F_close(p)=f*(qL+qS)*p
H(p)=E_s(p)-MM_s(p)-F_close(p)

主情景常数mL=mS=0.005（研究假设，不冒充历史交易所档位），敏感性0.004/0.006；f=0.0005为假设平仓费，和已付commission分开，不再扣历史费或funding。缺标记价可用同bar close作代理并标price_proxy=last_not_mark；输入不全则N/A而非编造。若另列实际venue档位，须官方有效时点来源验证，不用当前档位倒推历史。

常数MMR时 A=(qL-qS)-mL*qL-mS*qS-f*(qL+qS)，B=E0-(qL-qS)*p0，求A*p+B=0。H(p0)<=0为already_at_or_below_maintenance；A=0且B>0为no_finite_solution，A=0且B<=0为already_breached；p<=0为no_positive_solution。按0<p<p0的最近根填downward组合临界价（有多头时对应多头不利情景）；p>p0的最近根填upward（有空头时对应空头不利情景）；不是强迫两侧各有一个有限解。根正好p0亦为already_breached，数值近零容差须在Design冻结。

某侧无仓输出N/A(no_long/no_short)；即使有多空等量，两腿方向风险抵消但总维持保证金随p变，并不保证没有上行情景根。不可用单腿a*(1±1/10∓MMR)替代，不把原生margin_liquidation事件视为交易所MMR触发。每个价格附E0/qL/qS/aL/aS/p0/m/f、可用保证金（若未知标UNKNOWN，不把cash当等价物）、模式cross/shared_pool、求解状态、公式版本、假设和来源。价格四窗均值只是描述，不是当前持仓阈值。

### 3.7 F-007：PUMP量纲和官方同窗证据

字段必须分开：raw_v_contracts、quanto_multiplier（基础币/张的适用性需按direct合约元数据验证）、base_volume、quote_volume、数据venue/settle/native_contract/bar UTC、元数据有效期与检索时间。Gate官方SDK FuturesCandlestick描述v是合约规模、sum是报价币量；不能用spot数组volume字段或Binance当前行情替代。

标准 volume 统一为基础币。direct线性合约在有效且适用的乘数m下，volume=base_volume=raw_v_contracts*m；原始张数、乘数、单位、产品和来源/有效期/检索时间保留。报价币sum不能用close*base_volume硬充真实值，只可另列近似。参与率按同一bar基础币sum(abs(fill_qty))/base_volume计算，同bar多单合计；同时保留逐订单率与引擎原始cap。base_volume缺失/非正、乘数未知或历史有效性未知为UNKNOWN/缺证，不补零、不默认乘数1，不送入把volume<=0视为无限流动性的撮合路径。不得硬用当前乘数回填历史；旧PUMP source=historical_fallback_no_snapshot、contract_size=1.0 仅为fallback，不是有效历史乘数证据。最小缺证阻断及缓存兼容方式由T2冻结，不改runtime规则、不新建持久化体系。

原生 _liquidity_cap=0.1*volume按订单使用，没有全bar共享10%预算；当前native Gate swap直接把v传入。报告必须明确模拟cap、量纲一致性、partial/filled/deferred/rejected、statusReason、partial事件率的分子/分母和唯一订单partial比例分子/分母；压缩账本缺全量时比例N/A，不能对抽样算全量比例。limit_not_reached的coalesced occurrenceCount不是成交数。

T4需取得Gate同产品同UTC15m官方公开历史bar与平台原始输入逐项对齐；至少逐窗固定首/中/末已收盘bar和出现partial的bar（若无partial如实记录），记录完整请求身份、字段映射、原始数据摘要/来源、数值差异、数量换算。抽样核对不证明全窗量纲与完整性，后者仍需源码链与coverage。若Agent业务通道没有同产品输出能力而需要新增平台支持，STOP上报，不私自直连官方行情API绕过授权。公开文档取证不等于已取得历史业务数据。

不得从partial直接推出真实流动性不足；须区分10%模拟规则、每单与合计、合约乘数、最小lot、库存/保证金限制和价格未触及。错误单位下产生的回测不允许事后仅改报表数字就当有效损益。

### 3.8 F-008：受限执行、幂等与停止

仅既有 Agent whoami/klines/compile/backtest/job GET，不新增Human/浏览器路径；网格generate/Evolution未接入就标unsupported，不假装已调用。若使用本地既有纯生成器，必须在T2明确无业务副作用的导入/源码身份，不能本地执行策略。

T4是唯一真实目标job提交角色；每合约最多4个目标作业，外层job<=8/组、墙钟<=1800秒/组、数据请求<=50/组、Evolution=0。<=8是既有上限，不是额外失败重跑或备用搜索授权。工具离线自检不发业务。以cell+市场+起止+源码/参数+资金/成本+数据身份确定实验身份，先落本地去重记录和稳定Idempotency-Key，再提交；提交前已存在同身份job仅GET读回。已知jobId不为读结果重发POST。

既有同键同体网络不明允许恰好一次幂等重放，不是新作业；两次仍未知立即STOP。冲突409、failed/cancelled/workerInterrupted、预算/超时、401/403、HTTP402、billing.status=charged或charged>0、UNKNOWN影响结论均停止后续提交，保存已有证据；不换token、不自动重试、不扩预算、不自动退款。安全隔离允许首次known上市不足在提交前记N/A后继续其它目标；任何实际job失败仍按停止处理，不伪装上市不足绕过。

真实token只能CLI内部优先QUANTDINGER_AGENT_TOKEN，缺失时skills/.env精确单键QUANT_DINGER_AI_AGENT_TOKEN_MYMQUANT；不打印、复制、报告headers/token或argv值。T1/T2完全不读凭据。billing缺失=absent，不等于free；保留关闭计费为操作人前提与实际收据差别。

### 3.9 F-009：标准输出

报告正文 `data/reports/2026-10-31-neutral-grid-four-window/report.md`，支撑证据在同目录 `evidence/`；过程清单/交接只在既有任务目录。既有原始证据不可覆盖；断点只续取已知job，不增新实验身份。具体文件名/格式及允许字段由T2冻结。

四行汇总遵循backtest-comparison-standard.md：合约、L、U、g_pct、N、保证金收益%、Sharpe、MDD%、多/空组合情景临界价、有效窗口数/4、判定。每个数值列为均值（W1/W2/W3/W4），含N/A和该列n/4，单位一致。

附恰好16目标行：cell/venue/product/instrument、窗口、训练范围/参数源码身份、L/U/g/N、初始保证金/预算/杠杆读回、净损益/已实现/浮动/费用、收益/Sharpe/MDD、成交/配对数、最低权益、实际可见峰值gross和审计粒度、多空情景全部输入/状态、jobId/runId（未提交为null+原因）、source关联差异、cost/funding/billing、coverage、volume乘数/参与率、结论和限制。无实际字段不补0。

平台总成交/配对数以原生未抽样累计统计和日志核对，不用抽样数组len充总数。Agent结果取job.result扁平层，不套Human data.result。runId要求真实正整数，source_id=NULL为Agent既有差异，不视伪造sourceId，不宣称UI历史关联通过。

## 4. 数据与持久化契约

只落本地文件，无新数据库表/集合/TTL、生产schema或迁移。以下为必须保存的语义字段；T2定精确载体，不凭本节泛授权新增文件。

| 对象/字段 | 类型/必填 | 默认/校验 | 生命周期/敏感性 |
|---|---|---|---|
| cell_id | string/是 | §3.1十六值唯一 | 随本轮证据保留；业务非秘密 |
| window_start/end/timezone | ISO string/是 | UTC半开；不可运行后改 | 同上 |
| venue/product/native_instrument | string/是 | gate/swap/USDT/direct身份一致 | 同上 |
| training_start/end/available_at/count | string/int/是或N/A原因 | close<=start；无前视 | 同上 |
| params/code/generator_sha256 | string或结构/已提交必填 | 提交前计算；不含凭据 | 同上 |
| status/reason/coverage | enum+结构/是 | unknown显式，不默认success | 同上 |
| idempotency_key/body_digest/job_id/run_id | string/int/提交时必填 | 同身份去重；null需原因 | 本地审计标识，不含身份凭据 |
| equity/risk/metrics/liquidation/volume | 结构/是或null+原因 | §3.3..3.7；有限数，禁NaN伪装0 | 同上 |
| billing/source_refs/limitations | 结构/是 | absent明确；只允许业务字段 | 不保存headers/账户原始响应 |

历史记录只读保留，完成归档依项目现有规则由Closeout处理；无自动删除、无新定时器。data被Git忽略不等于提交或远程备份。新格式版本需记录schema_version，旧八结果保留original/superseded身份，不自动重写或迁移。

## 5. 验收标准（全部有真实证据才可最终通过）

| 编号 | 验收项 | 证据/失败规则 |
|---|---|---|
| A-001 | RFC/SPEC独立存在且一致，B-001修复要求及最小范围冻结，主控读回；Design独立T2再产出 | T1 PASS仅允许交接设计，不要求技术先修复；主控读回后解除T2，三层不得合并 |
| A-002 | 16唯一单元，UTC半开、锚点月末与wire end一致 | 真实日期/计数验证；旧窗不混入 |
| A-003 | 同venue swap历史及完整coverage | 逐窗根数/连续性/产品身份；上市不足N/A可真实报告，不能称16成功 |
| A-004 | 每窗仅前置收盘日线初始化，算法/成本解释准确 | 源码与参数摘要、last_available<=start；无可行集合不改阈值 |
| A-005 | 1000/true/10与实际下单单一乘数全链一致 | builder→Agent→runner→_target_quantity→成交/权益；quantity不重复放大 |
| A-006 | gross多空绝对值、库存/余单/权益下降审计 | 全量所声明粒度，未知不PASS；bar-close不冒充tick合规 |
| A-007 | 收益/MDD/Sharpe同一保证金权益 | 独立复核、频率/成本/异常规则；压缩点不能验证等频Sharpe |
| A-008 | 全仓多空组合情景、单池MMR假设及N/A | 检查根残差、方向、无仓/无正根/已越线；不复用两份1000 |
| A-009 | PUMP官方同窗/乘数/基础币volume/参与率归因 | T3最小修复或正确既有路径→T4真实独立验证→T5审查；历史缺证UNKNOWN、缺失/非正量不作无限流动性、错误单位旧PNL不追认；相关T4前检未过不提交16业务，未闭合不能研究PASS |
| A-010 | 唯一目标提交与幂等续取、预算与矛盾即停 | 16目标清单对job终态，未提交理由；不补单凑成功 |
| A-011 | 四汇总行+16明细，逐列有效均值、证据溯源 | 无缺失补零、无全年Sharpe宣传；不漏失败目标 |
| A-012 | 工具/真实研究/策略合格三结论分列 | 工具单测通过不等于真实运行/风险通过；主指标缺失最终不PASS |
| A-013 | 独立Implement/Verify/Review及共享基线审计 | 无越界修改，无凭据，无业务假数据；不改旧证据/历史文档 |

策略合格至少要求该有效窗R/Sharpe/MDD有效、MDD<=35%、gross约束在所要求风险粒度有充分证据、市场与单位正确；不额外新增正收益或Sharpe阈值。任何已证越限为不合格，未知为insufficient-evidence。四窗不齐不得称满一年通过；上市不足本身不是工具失败，不能用它掩盖主指标缺失或平台缺口。

## 6. 测试要求

T1文档delta核验与run3395既有证据保留。本节保留原完整研究测试要求，但当前离线子阶段仅启用成交量换算/拒绝/消费者及非Gate回归，精确范围见Design §8的B001-Native、B001-Consumer、NonGate组及其第3条命令；日期、初始化、杠杆、指标、风险、强平、Agent恢复与CLI测试均属未来完整研究候选，本次不实施或重跑。T3离线测试、T4独立复验必须实际执行，不编造日志；`offline_unit_fix` 可独立离线验收，`runtime_loaded`、`historical_evidence`、`full_research_status` 不因离线文件齐全而通过。

- 日期：同锚点月末截断、闰年、闭开相邻不重叠、UTC未收盘、wire含日终转换、16去重、上市不足/缺口不缩窗。
- 初始化：截止恰等start的已收盘日线可用，窗口内日线排除；2..365短样本、非法L/U、无可行N、N+1格线、0.14/0.20解释与固定成本排序。
- 杠杆：M0=1000、权重合计1，经原生value总预算10000，不是100000；quantity不再乘10；旧默认false/1；partial/手续费/readback缺失阻断。
- 指标：1000→1200→900应收益-10%、峰值MDD25%；回撤以峰值不以初始固定分母；零波动/不等频/非正权益输出N/A；缺失均值不补零；亏损窗不得从均值剔除。
- 风险：相等多空净值可为零但gross非零；旧库存+新挂单+同bar多成交；权益下降触发越限；压缩曲线遗漏峰值反例必须得UNKNOWN，不能合格。
- 强平：long_only向下根、short_only向上根、对冲等量总MMR效应、A=0无根、负根、H(p0)<=0、无仓、缺可用保证金/mark代理；方程残差和共享池不重复资金。
- 成交量：合约张/基础币/报价币分离、m!=1、缺元数据/历史有效期未知不可默认1、volume<=0不得无限成交、缓存兼容、多个订单合计cap、状态reason区分与ledger压缩；不得用synthetic fixture冒充PUMP历史证据。T2已冻结最小适配测试和Binance/spot/其他交易所行为不变回归，不扩建数据平台；缓存命中限制按§2属G-01未闭合项。
- 安全/恢复：仅Agent白名单，401/403不切通道，billing absent/charged、同键同体一次重放、409、不明状态停止、已知job只GET、预算跨重启去重。
- 回归：既有CLI测试与patch/import兼容性，局部抽取前后Human/trade语义；本地只用 `PYTHONDONTWRITEBYTECODE=1 /home/pascal/workspace/yquant-investment/.venv/bin/python`，不import策略、不安装。

## 7. 全链路实际验收与禁止替代

T4先核对三文档、已实现B-001修复/正确既有路径的真实独立前检及平台/数据身份；相关前检通过才在授权Agent通道执行冻结矩阵。前检不是T1/T2完成前提；离线子阶段可先行验收（`offline_unit_fix` 独立判定），线上加载/历史证据/完整研究判定分列，T5仍须独立审查技术闭合，full readiness 未闭合前整体不称 full PASS。保存实际compile结果、真实请求体允许字段、202收据、同一job GET终态、flat result及完整允许审计证据、计算明细与报告；每次外部写后GET读回。原生真实job失败即停，其它目标保留未执行状态。

不得将离线fixture、报告格式测试、历史八份结果、数组计数、压缩点、代码静态推断、未执行命令或旧助手说法替代真实结果。若受审批、工具、安全策略、数据或平台能力阻挡，保留实际错误与缺口，不改环境绕过，不降级宣称完成。

## 8. 阻塞与待核验

B-001（授权已定、技术pending，来源 RFC §4/§5 与pipeline-intake追加决策）：当前native Gate swap `v→volume→0.1*volume` 未做合约乘数转换，却限制基础币订单数量。PUMP历史实际乘数数值未在T1取得，不能凭字段名或historical_fallback_no_snapshot的contract_size=1.0推断有效乘数。标准输入须为基础币并保留原始张/乘数/来源证据；历史适用性未知显式缺证，错误匹配PNL不靠报告修复。最小修复按§2与§3.7纳入原T3，优先复用正确既有路径；T2冻结精确allowlist、元数据复用/缓存兼容/缺证行为与回归，不建平台/迁移，不改引擎。T1契约PASS与主控读回已完成，T2已按Pascal离线授权分段修订；离线子阶段不因G-01/02/03阻塞，技术待T3→T4→T5闭合，T4相关独立前检通过前不提交16业务，不重复等待同一已给授权。

C-002（能力核验，不自行扩权）：Agent klines当前不透传venue/product；T2须先证明可经现有原生多频历史/日志拿到同产品前置日线与15m审计，且不使用未来数据。若无可用既有通道，列最小产品/venue/source透传缺口，再报主控，不改平台/不偷走Human或直连官方业务行情。

C-003（真实数据待核验）：历史完整性、上市边界、官方同窗乘数/档位、日志连续性、真实指标均未实测。C-002/C-003不自动授权新接口或历史数据策略变更，具体必要缺口另报主控。不是T1已经完成的结果，也不能将UNKNOWN自动升PASS。OHLC/tick不可观测与funding not_modeled作为明确模型限制保留，不能向用户保证真实交易安全。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-10-31 | 五点可计算契约/验收与安全边界冻结；B-001阻塞，未开始Design/实现/业务 |
| V1.1 | 2026-10-31 | 续接run3395：按Intake最小Gate授权同步状态/范围/单位/禁止条款/验收；T1契约PASS可交接T2，技术pending，原五点不降级；无实现/业务 |
| V1.2 | 2026-10-31 | 续接run3399：按Pascal离线授权冻结B-001离线修复子阶段执行/验收，四状态分列，薄层/研究转未来候选；原五点与16窗口标准保留。主控读回同步校正来源版本、Design已交付状态及当前B001/NonGate测试与未来测试边界；无实现/业务提交 |
