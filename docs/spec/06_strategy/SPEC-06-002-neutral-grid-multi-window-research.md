# SPEC-06-002: 中性永续网格多窗口研究契约

## 元数据

| 项 | 值 |
|---|---|
| 版本 | V1.5 |
| 状态 | B-001与杠杆子集离线已验收；三件套离线ACCEPTED（Verify R3 153项OK、Review APPROVE）；本轮仅§9 G-02契约冻结，候选尚未实现/真实验收，G-02/G-03=OPEN；runtime_loaded=NOT_VERIFIED、historical_evidence=UNKNOWN、full_research_status=DEFERRED，16业务执行仍禁止 |
| 日期/作者 | 2026-11-01，Asia/Shanghai（UTC+08:00）；YQuant Principal，t_cfccfe2c / t_1af91929 / t_9fddffed / t_1b635d49 / t_22b3495f |
| 来源 RFC | [RFC-06-002 V1.5](../../rfc/06_strategy/RFC-06-002-neutral-grid-multi-window-research.md)，D-06唯一方案 |
| Design | docs/design/06_strategy/DESIGN-06-002-neutral-grid-multi-window-research.md V1.4（§11.1..11.9已与RFC/SPEC V1.5对齐）；§4及§5-7均已离线验收；三层已同步，Implement由主控按§11.1派发 |
| 权威输入 | data/tasks/active/2026-10-30-neutral-grid-research/pipeline-intake.md |

## 1. 摘要与完成语义

本 SPEC 冻结四 Gate USDT 线性永续合约、四独立三日历月 15m 窗口、前置参数初始化、1000 USDT 保证金/10x 单次放大、真实权益指标、gross 风险审计及全仓组合情景。只复用原生回测，结果不可由本地撮合替代。工具 PASS、研究完整、策略合格分别判定。

B-001四文件离线修复已验收，见§8，不重新待实现或重跑132项。杠杆子集已通过独立Verify 79项与Review；Design §5-7三件套随后完成独立Verify R3 153项OK、Review t_40f89523 APPROVE及主控离线ACCEPTED，来源为data/reports/2026-11-01-strategy-lab-leverage-fix/trio-closeout.md。V1.4的待实现表述仅保留为历史版本事实，R1/R2失败与更正不追认成功。当前唯一delta是§9的G-02训练价格通道及提交前冻结，未实现、未真实取数。§9在该窄范围替代旧C-002候选与平台只读限制，其他原五点/16窗契约不变；不把旧签收写成新待办。16业务仍须相关独立前检及授权；主指标缺失不能最终PASS，不伪造十六次成功。

## 2. 范围与文件约束

原T1仅允许以下三个文件（历史范围，非当前授权）：

- docs/rfc/06_strategy/RFC-06-002-neutral-grid-multi-window-research.md
- docs/spec/06_strategy/SPEC-06-002-neutral-grid-multi-window-research.md
- data/tasks/active/2026-10-30-neutral-grid-research/t1-handoff.md

已验收杠杆子集为quantdinger.py、agent_backtest.py、test_quantdinger.py及SKILL最小同步；已签收三件套为grid_research.py、test_grid_research.py及neutral-grid-four-window-v1五文件，不重新实现。当前t_22b3495f只可改本RFC、本SPEC、data/tasks/active/2026-11-01-grid-g01-g02/rfc-spec-handoff.md；不改Design/模板/源码/测试/SKILL/既有证据。下一阶段Design精确冻结§9候选的主仓/子仓文件增量、函数签名与定向测试，再由主控派发实现；不往quantdinger.py增加能力，不做无关拆分。通用evidence/恢复增强、标准表重构及16业务仍未启用。

QuantDinger子模块本卡只读。B-001四文件既有OHLCV逻辑和测试仍受保护；未来§9只允许训练OHLC独立入口及必要透传、既有Agent klines/OpenAPI/alignment同步，精确文件由Design列出，不以§9泛授权改旧解析器。runtime撮合、资金、生产配置、Binance/spot/其他交易所、缓存写删均不改；不做双所适配、新端点族、历史metadata平台/数据库迁移。G-01由主控并行限定只读核验，结果未读到不声称PASS；既有回测历史volume缺证仍failclosed，不修改/还原共享dirty。

数据库、代理、白名单、账户、生产配置、部署、绑定、发布、真实或 Demo 交易、长期调度仍禁止；禁止 commit/push、reset/stash/clean、依赖安装/升级、新环境、覆盖旧 evidence、浏览器/JWT/其他凭据。本worker不新建卡/新图，客户端后续由主控读回后派发。仅使用 Agent 已批准 operation；unsupported 不回落 Human；本次离线子阶段不发任何业务请求。若未来真实 E2E 需运行中进程加载源码变更，Design §9 的影响说明交主控判断，不自行重启/部署/另起实例，不把离线 PASS 当实际生效。任务授权不豁免 headless 安全策略，拒绝后不换解释器或包装绕过。

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

coverage 必须包含预期数/实际数、首末时间、唯一时间戳数、重复/缺失/错位/未收盘数量与市场身份。不能只凭首末范围或平台 tolerance 推断完整。上市前/无法取全窗：N/A+history_insufficient，保留该目标行，不发截短窗口；其他缺口：insufficient-evidence，不前向填价、不填零。计划冻结后运行顺序按合约列表、每合约 W1→W4；真实失败按 §3.8 停止，剩余行标 not_submitted_due_to_stop，不造 jobId。工具接口上，目标矩阵由 grid_research.build_cells 显式接受合约清单/窗口结构参数生成（缺省值即上表冻结矩阵与锚点 2026-10-31T00:00:00Z），未来换合约只传参、不改函数体；本轮语义、去重与日期规则不变。

### 3.2 F-002：每窗初始化与旧算法解释

训练输入：同 venue、同 swap 日线，截止 close_time<=start，最多最后 365 根已收盘日线；start 本日未收盘日线不可用。最少两根、数量/范围/实际可用时刻逐窗记录。上市后历史短于365可使用现有连续历史，显式 short_training_history；不足两根、缺口或来源不明不得默认参数成功。禁止利用窗口内/结束后的 high/low 或复用旧 spot 极值作正式无前视筛选。

L=min(low)，U=max(high)，要求 0<L<U。对整数 N=3..200，g_pct=100*((U/L)^(1/N)-1)，保留 0.45<=g_pct<=1.5；score=g_pct/C_round_trip_pct，选择最大值，数值平分按较小 N 决定，网格线数=N+1。无可行集合输出 no-feasible-geometry，不改格距或 N 上限。

旧 derive_grid_params.py 常数评分成本=0.14%，输入明确为 gate spot；新评分 C=100*2*(0.0005+0.0005)=0.20%，是可解释的线性往返成本近似，不代表原生每笔限价都会加滑点。记录 old_cost_assumption/new_score_cost/actual_fill_rule；固定正成本下选 N 的排序不因单纯成本比例变化而变成收益优化。不得把此基准称已做收益优化或参数搜索。

每窗参数来源记录训练产品、日线区间、数量、最后收盘时刻、L/U/g/N、参数内容摘要、生成器源码路径/版本/sha256、提交源码sha256；冻结后不得按结果改参。实际检索时刻与按收盘边界定义的可用时刻分列，精确契约见§9。动态锚定本轮关闭，原生中性角色划分/格生命周期保持；无额外优化或进化。参数文件和策略代码不得本地import执行；仅复用已验收纯函数/生成器，不在本卡发compile/backtest。

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

原生 _liquidity_cap=0.1*volume按订单使用，没有全bar共享10%预算；原T1现场native Gate swap直接把v传入（现离线修复状态见§8，不追改旧证据）。报告必须明确模拟cap、量纲一致性、partial/filled/deferred/rejected、statusReason、partial事件率的分子/分母和唯一订单partial比例分子/分母；压缩账本缺全量时比例N/A，不能对抽样算全量比例。limit_not_reached的coalesced occurrenceCount不是成交数。

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

T1文档delta、run3395及B-001 132项/补审证据保留，本轮不重跑B-001。杠杆79项与三件套集合已独立执行并签收；下列保留为既有测试契约及完整研究候选，不是本卡新运行要求。G-02后续独立测试新增项仅见§9.7，本卡tests_executed=0，不以额外环境/测试探测补文档门禁：

- 保留既有70项 unittest，不删除/放宽断言；新增默认false/1及1000/true/10从builder→Agent实际流程→真实parser/handler→请求体的离线贯通，不以仅helper或mock掉整个agent_backtest替代。
- leverage_enabled严格bool，leverage仅非bool的int/float有限值，启用时1..100（允许小数，非整数专限），关闭时仅1；非法类型/NaN/±Inf/越界/关闭非1明确拒绝且无请求，不clamp。请求>1必须在compile后、backtest POST前取得manifest.leverageAllowed=true；精确maxLeverage语义见Design，不自行新增策略上限。
- 默认调用/Human与trade、幂等/401/403/409/计费与预算/轮询/返回投影语义保持；动态文件import、cwd独立、导入无业务I/O、qd.agent_submit/agent_call/poll_job/_http_send等patch继续生效。
- 全部synthetic/offline；无真实凭据、网络、策略import、业务请求或依赖安装。开发自检与Tester独立复验实际运行并记录命令、cwd、解释器版本、原始stdout/stderr与原生exit，不能把未执行命令写为通过。
- 三件套新增：tests/test_grid_research.py 覆盖 build_cells 参数化/16去重/直接减月/月末截断/闰年、wire endDate前一天、365短历史、几何与指标算例、Sharpe异常矩阵、强平状态机、审计连续性/破产跳回调/缺seq、载体格式synthetic样例（精确断言以 Design §8 三件套小节为准）；策略实例五文件生成器测试含GRID_*_V1前缀、风险容量检查与公开API限定离线断言，不本地import执行策略。
- 三件套纪律：stdlib unittest、synthetic/offline、项目根 .venv、无凭据/网络/业务请求；既有79项（含70旧）不得删改放宽；全量 discover 冻结命令自动纳入新测试文件。

冻结命令（项目根）：`PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/tests -p 'test_*.py' -v`。解释器已核实Python 3.12.13，不重复探测环境。本Principal只写文档不运行；后续客户端通过只代表离线客户端能力，不改变四项B-001/研究状态。以下为原完整研究测试，除上述当前子集外不构成本次门禁：

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

B-001（offline_unit_fix=PASS；runtime_loaded=NOT_VERIFIED、historical_evidence=UNKNOWN）：四文件离线修复与132项记录复用不重做，来源仍为data/reports/2026-10-31-gate-volume-offline-fix/review.md及补审。真实Gate swap共用历史volume校验；不只是PUMP，不能拿当前metadata或fallback的1.0证明任意四合约历史适用性。G-02训练OHLC不产生合格基础币volume、不关闭G-03；相关前检及授权前不提交16业务，full_research_status=DEFERRED。

C-002（静态缺口已定位，候选未实现）：Agent klines当前无venue/product回执，作业内warmup不能证明提交前冻结；V1.5只选§9训练OHLC分支，替代旧候选顺序。无Human或研究端直连官方业务行情，无新增平台/端点族。

C-003（真实数据待核验）：历史完整性、上市边界、官方同窗乘数/档位、日志连续性、真实指标均未实测。C-002/C-003不自动授权新接口或历史数据策略变更，具体必要缺口另报主控。不是T1已经完成的结果，也不能将UNKNOWN自动升PASS。OHLC/tick不可观测与funding not_modeled作为明确模型限制保留，不能向用户保证真实交易安全。

## 9. G-02训练价格通道增量契约（V1.5，尚未实现）

### 9.1 唯一范围与能力隔离

决策源RFC D-06；本主题intake.md、data/reports/2026-11-01-grid-g01-g02-precheck/report.md、t_22b3495f comment3284与trio-closeout.md为事实来源。已有静态回源表明：markets.py:76-125有scope R/市场/标的校验但无产品透传；native_crypto.py:618-626对所有Gate swap调用OHLCV解析；:652-681仅当前metadata，历史有效性校验不认可真实当前快照；readiness不是提交前参数冻结。旧三件套已离线验收，不重新研发算法。

仅扩展既有GET /api/agent/v1/klines，新增显式训练OHLC模式。后端复用现有Native公共请求设施及Gate futures/usdt/candlesticks，不引入HTTP栈/依赖、Human路由、研究端直连、文件输入或作业内初始化。新增价格入口只提取t/o/h/l/c，不调用_parse_gate_swap_ohlcv，不生成OHLCV数组，不送入回测DataFrame/缓存或撮合。默认OHLCV路径、原volume验证、标准单位、所有非Gate行为保持。训练分支不读写现有持久/共享kline缓存，不新增缓存平台；源端当前metadata内存复用可留痕，但不当历史快照。

价格响应声明volume_status=not_provided与backtest_eligible=false，不含标准volume/base_volume/有效乘数，绝不以0或1占位。raw_rows中v/sum如有，仅为未认证原始字段，不能用于撮合；synthetic始终false。真实回测Gate volume仍需历史有效证据，缺证继续gate.swapVolumeHistoricalUnverified等既有错误；不开放synthetic接缝或关闭校验。G-03=OPEN。

### 9.2 HTTP输入、权限与兼容

以下字段是拟新增正式契约，不宣称当前API已经支持：

| 字段 | training_ohlc约束 |
|---|---|
| data_mode | 新增枚举ohlcv/training_ohlc；省略等于ohlcv；未知值400 |
| market / symbol | market必须Crypto；symbol使用现有Agent标的授权表示，不用native别名绕权限；四目标按§3.1 |
| exchange_id / market_type | 新增；训练模式两者必填且恰为gate/swap；不走默认所/产品，不接受冲突后再覆盖 |
| timeframe | 既有参数，训练仅接受1D；内部映射1d；其他值400，不默改 |
| before_time | 既有Unix秒，训练必填，严格正整数字符串、UTC午夜、不得在服务端当前时刻之后；值即该窗start；beforeTime兼容别名仅单独出现时可用，两者同时出现训练模式400 |
| limit | 训练省略为365，显式值严格整数2..365，非法/越界400，不沿用clip_int静默夹取；查询范围为截止前limit个UTC自然日，不扩大范围凑满样本 |

保留agent_required(SCOPE_R)、market_allowed、instrument_allowed及既有tenant/token隔离；鉴权/市场和标的权限拒绝在任何provider调用之前。按授权symbol解析后，对解析所得canonical/native映射再次检查一致性，不扩大权限集合。新模式只接受实际Gate metadata确认的id、USDT结算、type=direct并核对合约映射/报价USDT；缺字段或不符拒绝，不从请求回显推定实际身份。

旧调用未给新增字段时：默认OHLCV响应包络、默认参数、游标、原错误/行为均不变，不能把旧默认Gate spot重标为swap。ohlcv模式携带新增exchange_id/market_type则400（本增量不泛化OHLCV的身份路由）；训练模式不支持其他venue/product，400且不回退。OpenAPI的新增参数、条件必填/上下限、两种响应与错误及scope R必须同改，test_ai_agent_contract_alignment.py与必要路由契约测试覆盖；不新增operation/SDK/MCP能力。

### 9.3 来源、时间与响应（新模式）

保留既有包络code/message/data；成功读取返回HTTP200/code=0，data至少包含下表。数据合格性由data.status决定，HTTP200不代表G-02通过。

| 字段 | 内容与实际来源 |
|---|---|
| schema_version / data_mode / status / reason | grid_training_ohlc_v1 / training_ohlc / ok或insufficient_evidence；原因显式，不能成功空列表 |
| market / symbol / timeframe / count / klines | 兼容外层字段；klines为结构化OHLC对象，不是六列OHLCV；count严格等于规范化条数 |
| identity | exchange_id=gate、market_type=swap、settle=USDT、contract_type=direct、canonical_symbol、native_contract；请求路由+实际metadata的id/settle/quote/info.type与合约映射交叉验证后产生 |
| identity_evidence | 当前metadata原始业务字段及摘要、metadata检索时刻；metadata_scope=current_snapshot、historical_identity_validity=UNKNOWN；不杜撰生效区间，不取quanto_multiplier充当历史资格 |
| source | provider=native_gate、实际无凭据公共来源host/path、实际contract/interval/from/to查询、retrieved_at_utc、raw_rows及raw_rows_sha256；来源路径为现有Gate /api/v4/futures/usdt/candlesticks，不是客户端填的venue |
| klines每行 | open_time_utc来自原始t秒；close_time_utc=open_time+一个UTC自然日；open/high/low/close来自o/h/l/c，严格有限正数且low<=open,close<=high；identity引用实际验证身份 |
| 时间留证 | 每行available_at_utc=close_time_utc，availability_basis=bar_close_boundary；observed_at_utc=实际取回时刻，与retrieved_at分列；不声称已有历史发布/归档快照 |
| coverage | requested_start/cutoff、raw/actual/unique数量、首末open/close、重复/冲突/缺口/错位/剔除未收盘数、short_training_history、listing_boundary证据或UNKNOWN |
| 能力限制 | synthetic=false、volume_status=not_provided、backtest_eligible=false、historical_volume_validity=UNKNOWN；价格可用不提升后两项 |

raw_rows保留provider返回的原始业务行（t/o/h/l/c/v/sum存在则原值原类型保留，不补字段），不含headers/token/账户材料；不宣称为HTTP线缆字节。身份metadata同样仅保留上述业务白名单。摘要统一SHA256：UTF-8 JSON，sort_keys=true、ensure_ascii=false、separators=(',', ':')、allow_nan=false；对象键排序而数组原顺序保留，raw_rows不得先排序/去重/转float后冒称原始。摘要对精确保存的该对象计算；另对规范化OHLC对象数组计算normalized_sha256。客户端重算并校验两个摘要和身份metadata摘要，不把服务端单个布尔provenance_ok当证明。

日线可用时刻是冻结的“收盘边界可用”研究约定，不是交易所历史发布延迟实测；当前retrieved_at可能晚于窗口start，不伪造过去下载时间。若要求历史发布时刻/历史身份变更证据而本来源不具备，则对应资格UNKNOWN并披露；不发明有效期。本轮按原§3.2收盘边界约定做无前视价格初始化，不扩建历史归档。G-02所需身份资格是实际Gate futures/usdt路径、native_contract与当前direct/USDT映射的一致性，不宣称取得全历史产品属性有效期；若发现更名/产品变更等具体冲突则影响训练资格、必须停止。历史身份有效期/发布延迟/volume资格的显式UNKNOWN是本次不解决的限制，不单独作为训练价格资格失败；不得据此提升这些限制为PASS。

### 9.4 连续性、短历史与错误

单窗最多一个有界日线请求覆盖[cutoff-limit日,cutoff)，provider from/to据此生成（秒边界，to不越cutoff前一秒）；不取窗口内日线，不翻页到更早价格凑数。保留原始返回顺序，规范化可按open升序；禁止静默去重掩盖重复或冲突。边界外/未收盘行只在明确时间裁剪时排除并记计数，不参与极值；窗口内数据不得进入算法。训练末根close必须恰等cutoff，相邻open相差一个UTC自然日，至少2根、最多limit根。low/high单根可相等，但总体L<U，否则算法拒绝。

若limit=365、返回365根连续且接到cutoff，可形成完整训练段；2..364根仅在实际同产品上市边界证据证明请求范围前部为上市前、上市后无缺口时，允许short_training_history=true并披露风险。证据须记录实际来源、原始字段/值、检索时刻与摘要，不假定当前metadata一定提供上市时间，不杜撰字段或读路径。缺上市证据的短返回、空返回、尾部缺日/中间缺口、重复/冲突、价格非法、时区错位均insufficient_evidence，不把更早样本补入或缩小目标窗。不到两根有明确上市证据则history_insufficient/N/A，否则UNKNOWN。后续固定矩阵均请求365，显式较小limit仅供接口契约验证，不替代完整研究训练。

| 行为 | HTTP / 结果 |
|---|---|
| 非法输入/不支持模式组合 | 400/code=400，message=training.invalidRequest，retriable=false；provider调用0 |
| 未认证/缺scope/市场或标的不许 | 复用既有401/403契约；provider调用0，绝不换token/通道 |
| provider网络/结构错误、身份缺失或冲突 | 502/code=502，message=training.sourceUnavailable或training.identityUnverified，data=null、retriable=false；可保留无秘密details.reason，不输出原始异常/凭据；原始NaN/Inf导致JSON不能安全留证也属结构错误 |
| 有原始响应但连续性/数量/上市证明不足 | 200/code=0，data.status=insufficient_evidence，reason明确且保留上述来源/coverage；调用方结论UNKNOWN/N/A，不生成可提交参数 |
| 真实价格合格、但几何无可行N | 数据status=ok；本地既有derive_geometry返回no-feasible-geometry，保留该目标与原因，不改阈值重试 |

5xx/超时、缺字段、摘要不符、未知影响结论均停止后续真实取数并保存已有证据；接口retriable标志不授予自动重试。已知上市不足可按原安全隔离记N/A后继续，不能把任意缺证当上市不足。默认OHLCV继续其既有错误语义，训练错误不取代历史volume错误。

### 9.5 提交前冻结：复用已验收纯函数

新增薄适配只负责Agent读取/验证/留证，将验证通过的日线映射为derive_geometry既有输入；provenance_ok仅在原始摘要、实际身份、coverage和close<=start全部核验后由适配层赋值，不接受用户布尔值代替证据。不改变build_cells、derive_geometry、生成器与指标算法既有API/断言，不重新优化参数；独立小模块承载，不扩展quantdinger.py。

按§3.1固定四合约四窗，一次性准备全部16行冻结清单。每行包括cell_id/完整身份/window/start/cutoff、原始/规范化/metadata摘要与证据相对路径、数量/首末/available_at/observed_at及时间约定、上市/coverage状态、几何全部L/U/g/N及成本约定、生成器与纯函数源码摘要、完整参数对象与params_sha256、最终生成但未执行的策略源码及code_sha256、status/reason。可执行行的params/code必须先写入本地，再计算冻结清单摘要；不只存文件名或mtime。所有摘要按§9.3规范（源码按原文件字节），持久化前必须排除秘密。

清单包含ready/no-feasible-geometry/history_insufficient/insufficient_evidence，不漏目标；N/A原因有证据，不补默认参数。整个清单在任何未来compile/backtest提交之前冻结；后续提交再次按内容校验摘要，变更则STOP，不能事后补冻结。此卡不提交，也不新增去重恢复平台。载体位于data/reports/2026-11-01-grid-g01-g02/及evidence/，由Design定精确文件名；旧证据只读不覆盖。存在UNKNOWN时允许交付已取得证据但G-02保持OPEN；无可行几何或确证上市不足为真实已解决的N/A而非伪造成功实验。

### 9.6 授权、预算与真实验收终点

三层同步后的实现任务只许可Design精确文件增量及无网络/无凭据的离线自检；本RFC/SPEC任务不授予worker任何源码修改、测试、应用import、网络、凭据、数据库、服务加载权限。run3424额外源码/Git基线采集被安全拒绝（tool_calls_made=0），按Pascal后续恢复决定正式取消，记OMITTED_BY_AUTHORIZATION而非PASS；不在此卡或Design以terminal/execute_code/临时runner重采、不改审批配置。

真实G-02验收必须通过正在运行且已确认加载候选的Agent API读取，不可用新起本地进程/mock替代。主控另行取得具体授权：限定现有Agent目标地址、GET whoami/klines操作、现有CLI内部必要Agent token消费方式、四合约四截止、本地无秘密证据保存与下列预算。旧§3.8凭据位置只描述既有路径，不给本worker读取权；G-01仅Redis例外不扩展到Agent。若需quantdinger-api.service等运行对象重载/重启，先列实际对象、影响及验证方式交主控具体确认，不启动、部署或另起实例。不得顺带加载celery/evaluator、写删缓存或进数据库。

建议并冻结为后续具体授权的最大只读预算：整个G-02验收而非每重启/每阶段分别计，whoami至多1次，klines每cell至多1次且总计至多16次；后端实际对Gate的公共请求（含身份metadata加载、日线、任何分页/重试）总计<=50次，墙钟<=1800秒。无自动重试/替换标的/绕通道；不足以完成则停止报缺口，由主控决定，不拆组刷新预算。明确job/compile/backtest/Evolution=0，交易/数据库/缓存写删/长期调度=0。provider内部隐式重试也计预算，若无法约束则不得开始真实验收。401/403/402、charged>0或billing.status=charged、安全拒绝、预算/超时、身份/摘要矛盾、UNKNOWN影响结论立即STOP；billing absent不等于免费。

G-02只有在独立Verify/Review确认实现与默认路径回归、主控确认必要运行加载和真实只读授权、真实16目标取数/分类及参数内容冻结证据齐备且无影响训练资格的UNKNOWN时方可关闭；§9.3明确排除的历史有效期/发布延迟/volume资格仍如实UNKNOWN。有确证N/A须列证据，不能声称16成功。仅离线mock PASS或参数文件存在不能关闭。G-01结果独立、G-03仍OPEN、historical_evidence=UNKNOWN、full_research=DEFERRED；本阶段不解除原T6或16作业禁止。

### 9.7 可验证验收矩阵（后续实现/独立Verify使用，本卡不执行）

| 编号 | 成功/失败断言与证据 |
|---|---|
| G02-01 | 默认无新增参数的请求/包络/错误兼容；新模式scope R、市场与标的拒绝、native别名冲突均在provider前停止；非法组合/小数limit/越界/双游标/非午夜拒绝，调用数0 |
| G02-02 | 实际gate/swap/USDT/direct metadata与原生contract一致才回执；缺失/spot/跨所/身份矛盾502，不能回显请求冒充实际来源；raw与metadata摘要客户端重算一致，篡改一字段拒绝 |
| G02-03 | synthetic离线365日/两日短上市证据可用；close恰等start可入、未收盘排除留计数；末根落后一天、缺日、重复/冲突、错位、NaN/Inf/非正价、短返回无上市证据、0/1根不得产ready参数 |
| G02-04 | 相同原始Gate fixture可取训练OHLC而原OHLCV仍因历史volume缺证拒绝；四合约均覆盖，不只PUMP；无volume填0/乘数1/synthetic伪标，无缓存/回测frame接入；非Gate/spot原行为回归 |
| G02-05 | 既有build_cells与derive_geometry被真实调用而非重新实现；16行无漏、参数/代码/原始/规范化摘要冻结，之后改任一内容则拒绝；no-feasible与上市N/A保留原因，provenance布尔无证输入拒绝 |
| G02-06 | OpenAPI条件参数/两模式响应/权限/错误与路由一致，alignment/定向单元测试通过；既有B-001/杠杆/三件套断言不删改放宽。具体命令与文件由Design冻结，旧153项证据不冒充新增测试 |
| G02-07 | 经另行授权的运行中Agent实际返回同产品原始行与来源时间/hash，每窗最多365连续日线或确证N/A；真实参数/代码内容先冻结、业务POST计数0；未加载、缺token授权、数据不足或运行不明则G-02 OPEN，不伪造PASS |
| G02-08 | 预算跨阶段累计、错误/计费/身份未知即停，未执行目标留原因；日志/本地证据不含headers/token；G-01未被假定PASS，G-03未被价格成功关闭，无重启/缓存/数据库/交易越权 |

本卡完成标准仅两独立文档及交接齐备、唯一方案/接口/权限/数值/失败语义无开放问题，可交接既有Design子卡；尚未实现与真实授权/取数缺口是已披露的后续工作，不误当本卡文档阻塞。后续Design须保留已验收三件套状态，列精确主仓/子仓文件及调用签名、原路径保护与最小离线测试、实际加载影响和上述真实验收清单；不得重选业务方案或扩大权限。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-10-31 | 五点可计算契约/验收与安全边界冻结；B-001阻塞，未开始Design/实现/业务 |
| V1.1 | 2026-10-31 | 续接run3395：按Intake最小Gate授权同步状态/范围/单位/禁止条款/验收；T1契约PASS可交接T2，技术pending，原五点不降级；无实现/业务 |
| V1.2 | 2026-10-31 | 续接run3399：按Pascal离线授权冻结B-001离线修复子阶段执行/验收，四状态分列，薄层/研究转未来候选；原五点与16窗口标准保留。主控读回同步校正来源版本、Design已交付状态及当前B001/NonGate测试与未来测试边界；无实现/业务提交 |
| V1.3 | 2026-11-01 | t_9fddffed：指向RFC V1.3 / Design V1.2；B-001离线已验收并保护；仅启用三函数局部抽取/可选杠杆贯通与小集合离线验收，既有70项保留；完整研究与其他候选不启用，本卡无源码/测试执行/业务提交 |
| V1.4 | 2026-11-01 | t_1b635d49：按Pascal授权窄启用§5-7三件套待实现契约（grid_research.py参数化纯函数库、指标/强平/汇总计算、策略实例neutral-grid-four-window-v1五文件含GRID_AUDIT_V1审计回调）；§1状态、§2 allowlist、§3.1工具接口注、§6三件套测试集合同步；杠杆子集标记已验收（79/79 OK、Review APPROVE）；指向RFC V1.4/Design V1.3；16业务执行、服务加载/缓存/凭据/通用evidence/稳定键恢复仍禁止，本卡无源码/测试执行/业务提交 |
| V1.5 | 2026-11-01 | t_22b3495f：纠正三件套为已离线ACCEPTED，独立§9冻结G-02唯一训练OHLC模式、scope R/身份/兼容、来源/收盘可用时刻/原始与规范化摘要、连续短历史与UNKNOWN、16参数预冻结、预算与真实授权验收；Design已由子卡t_1f4c8c58同步至V1.4；本卡仅文档交接、测试/网络/业务执行0，取消的额外基线采集OMITTED_BY_AUTHORIZATION，G-02/G-03未闭合 |
