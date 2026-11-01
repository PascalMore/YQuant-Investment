# RFC-06-002: 中性等比永续网格四窗口研究

## 元数据

| 项 | 值 |
|---|---|
| 版本 | V1.5 |
| 状态 | B-001与杠杆子集离线已验收；三件套离线ACCEPTED（独立Verify 153项OK、Review APPROVE）；G-02契约已三层冻结（RFC/SPEC V1.5 + Design V1.4 §11），候选尚未实现/真实验收，G-02/G-03=OPEN；runtime_loaded=NOT_VERIFIED、historical_evidence=UNKNOWN、full_research_status=DEFERRED，16业务执行仍禁止 |
| 作者 | YQuant Principal / t_cfccfe2c / t_1af91929 / t_9fddffed / t_1b635d49 / t_22b3495f |
| 日期 | 2026-11-01，Asia/Shanghai（UTC+08:00） |
| 项目 | /home/pascal/workspace/yquant-investment |
| 来源 | data/tasks/active/2026-10-30-neutral-grid-research/pipeline-intake.md |
| 配套 | [SPEC-06-002](../../spec/06_strategy/SPEC-06-002-neutral-grid-multi-window-research.md) |

## 1. 结论与动机

冻结 Pascal 五点研究的业务语义，复用 Strategy Lab 和 QuantDinger 原生 V2 历史回测，不建第二个引擎。历史八份结果只是一个季度的账户规模对照，不是本次十六窗口结果；不从旧助手口述推断正确 10x、真实流动性不足或全年研究完成。

已知平台单位缺口 B-001 的原问题是 Gate 合约张数 v 未经乘数换算就限制基础币订单。仅增加 CLI 杠杆参数不能修复该链路。当前四文件离线修复已通过 T3 run3405、T4 run3406、T5 run3407 及补审 run3408，不重新列为待实现；运行加载与历史有效性仍未通过，16 业务提交仍须相关独立前检。原 run3395 BLOCKED、T1/T2 及补审披露的历史流程偏差/证据缺口均保留，不追认或重做。

2026-10-31 的 B-001 离线子阶段现已验收。2026-11-01 Pascal 同意按现有逻辑最小修复客户端阻塞，来源为 data/tasks/active/2026-11-01-strategy-lab-leverage-fix/intake.md；该杠杆子集（三函数局部抽取、keyword-only 杠杆参数、CLI 贯通与离线验收）已实现并通过独立 Verify/Review（79/79 OK、APPROVE，t_664a588c）。同日先授权 Design §5-7 三件套（参数化 grid_research.py、保证金指标/强平/汇总、neutral-grid-four-window-v1 五文件及 GRID_*_V1 审计），随后完成实现、独立 Verify R3（153项OK）、Review R3（t_40f89523 APPROVE）和主控离线签收，见 trio-closeout.md；V1.4 的“待实现”为当时事实，不再是当前待办。原R1/R2失败披露保留，未被追认成功。16业务执行、服务加载/缓存/凭据、通用 evidence 扩展、稳定键恢复增强仍不启用。原五点最终标准不删除不降级；离线实现通过不证明平台加载、历史或研究通过。

## 2. 目标与非目标

目标：PUMPUSDT、AAVEUSDT、JUPUSDT、SUIUSDT，固定同一 Gate USDT 线性永续产品身份；15m，四个互不重叠的三日历月窗口，独立资金池与参数初始化。交付 PUMP 成交量取证、初始化算法解释、16 单元矩阵、真实保证金指标/风险情景和既有标准表。

不做：Binance+Gate 整体双所适配、新切换能力、跨源对照、扩大16目标矩阵、交易所实盘账户杠杆设置、下单、Demo/Live、部署、进化搜索、优化盈利参数、新 SDK、数据库直写、代理/白名单/凭据/长期调度变更、跨市场替代或新平台端点。funding=not_modeled 已获同意，不为此扩建。

## 3. 冻结决策

### D-01 时间与市场身份

所有数据时刻为 UTC。锚点是 2026-10-31T00:00:00Z，不是 2026-10-31 当日结束。2026-10-31 18:15 Asia/Shanghai 检查时该 UTC 日期尚未结束；取这个已到达的午夜边界，只包含至 2026-10-30 的完整 UTC 日，不包含未来或当天未收盘数据。

边界从同一锚点直接减 0/3/6/9/12 个日历月，目标月无同日时取该月末，禁止递归减月造成日期漂移。W1 最新至 W4 最旧，具体半开范围见 SPEC §3.1。与旧 2026-08-01 起点不同，不能静默追认为同窗重跑。每个产品每窗口独立重置 M0=1000 USDT，不拼接复利。

Gate、swap、USDT 结算和完整合约身份必须显式绑定；旧 gate spot 日线不能充当 swap 参数样本。上市不足或历史不可取保留 N/A，不补零、不换 venue、不用现货、不缩窗。

### D-02 初始化不是收益优化

保留旧算法解释：最近最多 365 根日线 high 最大/low 最小确定 U/L；N=3..200，等比格距 0.45%..1.5%，最大化格距/固定往返成本。固定成本下偏好较大格距，非收益优化、非已完成样本外搜索。

正式新实验每窗只允许使用 start 前已收盘的同产品日线，参数冻结后运行整个窗口。最少两根实际日线且 L>0、U>L；不足 365 根可用全部已有历史，但须逐窗披露实际数量、上市边界与短样本风险；缺口不等于上市不足。无可行 N 为 no-feasible-geometry，不改阈值重试。原脚本成本评分 0.14% 与本轮 commission/slippage 简单双边合计 0.20% 不同，分别保留并解释实际限价成交滑点规则，禁止追改旧证据。

### D-03 单一杠杆与风险

API initialCapital=1000、leverageEnabled=true、leverage=10。生成器按 starting_cash*CELL_BUDGET_PCTS 传入 order_value，由原生 _target_quantity 唯一乘十；quantity 路径不再乘十。10000 是名义可分配预算，不是保证金、不是即刻已持仓，也不是强制全部花完。CLI 兼容默认仍 false/1，新实验显式启用。

gross=sum(abs(多/空持仓名义))/实时保证金净值，限值 2.5，不能净额抵销；挂单不算已持仓，但必须预留潜在开仓容量、计入库存、部分成交和权益下降。35% MDD 是结果筛选，不是承诺所有基准合格，也不等于从初始资金止损 35%。只允许在明确采样粒度上给出合规结论，不声称 OHLC 证明逐 tick 永不越限。

### D-04 主指标与强平情景

收益、MDD、Sharpe 统一使用真实 1000 保证金权益（含未实现损益及已建模成本），不得把旧 10000 账户的百分比乘十。四窗算术均值为描述统计，不称全年累计收益或全年 Sharpe；每列独立有效分母。

强平为同池全仓组合价格情景，不是交易所真实强平引擎；共享保证金不向两腿重复分配。输出向下/向上冲击的组合临界价及对应多/空方向说明、输入时点、MMR 假设、费用、无仓/无有限解/缺输入的 N/A 原因。原生 equity<=0 破产不等于交易所 MMR 强平。公式见 SPEC §3.6。

### D-05 证据与结论分离

工程工具、真实研究完成、策略合格是三条独立判定。某窗不合格或上市不足是允许的真实研究结论，不伪造十六次成功。缺主指标或未知风险证据不能获得最终 PASS；真实研究可如实交付 incomplete/insufficient-evidence 并停止。

## 4. 已核实的源码事实

以下路径均以 `skills/trading/auto-trading/quantdinger/QuantDinger/backend_api_python/` 为前缀；子模块只读 HEAD=4111d4550c9354a278d3926a786c4b2586a673aa，父仓 HEAD=5c5fca7d4bdd1b5a027fe48943f1eff3de2a09e3。行号对应 T1 读取现场，不等于业务 API 实测。

| 证据 | 事实 / 含义 |
|---|---|
| app/services/strategy_runtime/robot_v2.py:155-160,342-371 | 中性格预算合计 1，order_value 输入来自 1000 保证金；max_open_orders 只限制活跃入场挂单数，不限制累计库存 |
| app/services/strategy_v2/runtime.py:1504-1518 | value/target_value/target_percent 乘 self.leverage，quantity/target_quantity 不乘 |
| app/services/backtest_jobs.py:58-65 | API endDate 被扩为该日 23:59:59，不能直接把半开 end 当 wire endDate |
| app/routes/agent_v1/markets.py:87-114；app/services/kline.py:110-137 | Agent klines 不传 exchange_id/market_type；Gate 默认空产品分支可取 spot，不能当同 venue 永续取证通道 |
| app/data_sources/native_crypto.py:579-593；app/data_sources/crypto.py:613-623 | Gate swap 的 v 原样进入 volume，spot 走不同字段；不能混同 |
| app/services/strategy_v2/market_data.py:278-315 | frame 数值化未做合约乘数换算；缺 volume 会填 0，是上游行为而非本研究认可的有效成交量 |
| app/services/strategy_v2/runtime.py:1243-1250,884-886 | volume*0.1 逐订单限制基础币 delta；volume<=0 返回无上限，不代表真实可成交，多个订单不能当全 bar 合计 10% |
| app/services/strategy_v2/runtime.py:1773-1832 | 先处理挂单/开盘回调/保护，再 handle_data、after_trading_end、record_equity；策略回调不是每笔成交后钩子 |
| app/services/strategy_v2/service.py:470-477；storage.py:361-413 | Agent 交付结果也经过压缩，权益约1200、持仓600、订单/成交1500等限制，不能只归咎本地 CLI |
| app/services/strategy_v2/runtime.py:2127；storage.py:365-413 | 原生日志保留通道存在，策略内逐 bar 监测可在 T2 设计；不据此宣称逐成交钩子或无上限真实可用 |
| skills/strategies/strategy-lab/scripts/quantdinger.py:557-581,675-678（父仓路径） | CLI 杠杆固定 false/1，且只保留数组长度，均为薄层必要修正 |

## 5. 能力划分与阻塞

工具层可做：局部抽取 Agent 调用、显式杠杆透传、保留允许字段/结果证据、清单去重、时间适配、保证金指标/汇总/情景计算；策略内日志审计只用原生沙箱允许 API，不建撮合器。

待真实核验：四合约同产品完整日线/15m 历史、PUMP 历史乘数与官方同窗 bar、日志覆盖/大小、真实运行结果和计费。T1 不读凭据、不调用受限业务 API，未声称这些已可用。

B-001 当前为离线修复 PASS、运行/历史未通过：冻结标准 volume 为基础币；保留 raw_v_contracts、base_volume、乘数、单位、产品身份及来源/有效期/检索时间。元数据不足不得默认乘数1；旧 PUMP instrumentRulesSnapshot 的 source=historical_fallback_no_snapshot、contract_size=1.0 不是有效历史乘数证据。历史适用性未知须显式 UNKNOWN/缺证，不以当前乘数硬回填历史；缺失或非正 volume 不得送入将其解释为无限流动性的撮合分支。不得事后仅重标报表单位追认错误撮合 PNL，也不得缩放订单冒充修复。

已验收 B-001、杠杆子集和三件套均为既有资产，不重复开发或重跑原132项作为新阶段任务。V1.4 对 Design §2.2/§5-7 的新增文件授权已经完成；本轮只写本 RFC、SPEC 与 G-02 阶段交接。未来候选实现仅按 D-06/SPEC §9 增加训练价格窄分支、留证和冻结适配；如需在 native_crypto.py/crypto.py 增加独立价格入口，须由下一阶段 Design 精确列出增量及非干扰测试，既有 OHLCV/历史volume校验与既有测试不得改写或放宽。不会由旧allowlist泛授权修改平台。runtime、资金、生产配置、缓存写删、数据库及其他交易所行为不变，共享dirty不还原。

能力缺口 C-002 已有静态定位：Agent klines无同产品/venue参数，沙箱作业内warmup不证明提交前冻结。V1.5 唯一候选改为 D-06 的既有Agent路由训练价格分支；此处替代旧“优先作业内导出”的候选顺序，不追认旧实现。不能调用Human或由研究客户端直连官方行情API绕过Agent通道。

C-003（历史与真实证据待核验）保持未通过：完整历史、官方同窗乘数/档位、日志连续性与真实指标须后续取证。C-002/C-003 不自动授权新接口或改变历史数据策略，必要缺口须有具体证据后上报。最小 B-001 与本次客户端授权不降低原五点验收；本次离线契约/实现不以真实研究先通过为前提，相关独立前检未通过前不得提交16业务。若真实 E2E 需要现有进程加载变更，Design §9 的影响说明仍交主控判断，不能自行部署、重启、另起实例或把离线 PASS 当实际生效。

## 6. 工程边界

CLI 的必要局部抽取已按 Design §4 完成，既有79项已独立验收；三件套按 Design §5-7 完成并离线签收，均非本轮待实现。G-02不向超过2400行的 quantdinger.py 叠加实质能力，不要求无关拆分；复用其既有Agent请求接缝，在独立小适配层调用已验收 derive_geometry/build_cells，不研发初始化或指标算法。既有API/测试断言和1000/true/10、单一杠杆、资金/风险语义保持。

原T1写入范围及workspace-baseline.json仅为历史记录。当前t_22b3495f写入仅本RFC、对应SPEC、data/tasks/active/2026-11-01-grid-g01-g02/rfc-spec-handoff.md；沿用既有证据，不额外采集当前源码/Git基线。复用06-001而不改其文档，不写Design、不reset/stash/clean、不改旧evidence、不commit/push。

## 7. 验收与阶段

原 T1-T5、B-001验收/补审及三件套离线签收保留；原 T6 t_2b5702a5继续blocked。当前t_22b3495f只完成RFC/SPEC，既有子卡t_1f4c8c58再同步Design；主控核对三层后才派G-02 Implement→独立Verify→独立Review，不新建本卡任务图、不重做旧链。G-02真实只读取数需SPEC §9.6的单独具体授权，不包含compile/backtest/job提交；未来16研究仍由原T4唯一提交并保持原预算与停止规则。

完整执行验收见 SPEC §5；本次客户端离线验收见 SPEC §6 与 Design §4/§8。B-001 已验收记录不替代本次客户端测试，本次客户端通过也不替代完整研究。原五点/16窗口最终标准不删除不降级。策略 FAIL、上市不足可报告，但主指标缺失不能最终通过。

### D-06 G-02唯一最小方案：既有Agent klines的显式训练OHLC分支

来源为本主题 intake.md、前检 report.md、t_22b3495f comment3284的已完成静态回源及 trio-closeout.md。修正旧风险表述：所有真实Gate swap OHLCV均进入历史volume元数据校验，当前真实metadata无历史有效区间，阻断不是仅PUMP。价格读取与成交量资格是不同能力；本次解决前者，不改变后者。

| 备选 | 判定与理由 |
|---|---|
| 仅透传exchange_id/market_type，仍取OHLCV | 身份可改善但所有真实Gate swap仍被历史volume校验阻断，不能独立解决G-02 |
| 作业内多频warmup或日志导出 | readiness不是365上限/短历史规则，且参数在提交前未冻结；需先发job，违背当前阶段边界 |
| 客户端直连Gate或人工文件替代 | 新增取数/信任通道，绕开当前Agent授权；未有合格同产品文件证据，不选 |
| 既有GET /api/agent/v1/klines增加data_mode=training_ohlc | 唯一选定；保持scope R与市场/标的鉴权，显式Gate/swap/direct/USDT，使用既有Native公共传输与官方futures/usdt/candlesticks路径，只解析OHLC，回传来源/原始业务行/摘要；不经过OHLCV归一化或回测frame，不声明volume合格 |

新模式限定Crypto、1D、Gate USDT direct swap及UTC训练截止，至多365根、至少2根连续已收盘日线；窗口末端必须接到start。真实原始来源、当前身份metadata及检索时刻留证；不杜撰历史身份/乘数有效期或历史发布时刻。训练价格不含volume，原始v/sum仅是未认证原始业务证据。不得补0、乘数默认1、给真实数据标synthetic、修改历史校验或回落spot/跨所。

每窗读取、验证并调用既有几何算法，全部16目标的参数内容/代码/数据摘要或明确N/A原因在任何未来作业提交前落本地冻结清单；客户端传provenance_ok=True不替代来源验证。短上市必须有实际来源证据，否则短返回/缺口标UNKNOWN，不据空数组认定上市。原四合约四窗/UTC锚点、成本、指标、风控、回测volume failclosed全部保持。G-02离线测试通过不等于真实验收；G-03始终OPEN，G-01并行独立核验，不等待或假定通过。

本卡不改Design/源码/测试/SKILL/旧证据、不运行测试/应用/网络/数据库/服务/凭据动作。被拒的额外基线采集按Pascal恢复授权记OMITTED_BY_AUTHORIZATION，不重试或换执行器，不记PASS。下一阶段只定精确文件和调用签名，不重开方案选择；三层同步前不派Implement。源码实现许可与真实I/O、Agent凭据消费、服务加载/重启分开，后者由主控具体确认。

## 8. 参考与公开来源

- 本轮 pipeline-intake.md、workspace-baseline.json；既有 backtest-comparison-standard.md。
- 原算法：data/reports/2026-10-31-neutral-grid-param-derivation/derive_grid_params.py:26-56,73-108；其输入说明明确 gate spot，旧独立单腿强平近似不沿用为全仓估算。
- 官方 Gate SDK 2026-10-31 公开只读检索：`https://raw.githubusercontent.com/gateio/gateapi-python/master/docs/FuturesCandlestick.md`，v 为合约规模成交量、sum 为报价币成交量；`https://raw.githubusercontent.com/gateio/gateapi-python/master/docs/Contract.md`，描述 quanto_multiplier、maintenance_rate 和风险档位查询字段。未取得 PUMP 任一历史时点乘数数值，不用当前字段定义证明历史档位或实际可得性。这些是字段证据，不是强平公式或账户规则的官方背书。

## 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0 | 2026-10-31 | 五点语义、边界、源码事实及 B-001 阻塞；未实施或执行业务 |
| V1.1 | 2026-10-31 | 续接run3395：按Intake最小Gate授权同步状态/范围/单位/禁止条款/验收；T1契约PASS可交接T2，技术pending，原五点不降级；无实现/业务 |
| V1.2 | 2026-10-31 | 续接run3399：按Pascal离线授权冻结B-001离线修复子阶段执行/验收，状态同步T2分段交付；原五点与16窗口标准保留，技术仍pending。主控读回同步校正未来CLI工作与当前离线测试边界；无实现/业务提交 |
| V1.3 | 2026-11-01 | t_9fddffed：同步B-001离线已验收及未加载/历史未知状态；仅启用客户端杠杆透传、三函数必要抽取与离线验收，指向SPEC V1.3 / Design V1.2；通用证据/恢复增强与研究仍未启用，无源码/测试执行/业务提交 |
| V1.4 | 2026-11-01 | t_1b635d49：同步Pascal对Design §5-7三件套窄启用授权——杠杆子集标记已实现并验收（79/79 OK、Review APPROVE），新增三件套待实现契约（grid_research.py参数化纯函数库、指标/强平/汇总、策略实例含GRID_AUDIT_V1审计回调）；§1/§5/§6/§7状态与allowlist最小同步；16业务执行、服务加载/缓存/凭据、通用evidence/稳定键恢复仍不启用；指向SPEC V1.4/Design V1.3，无源码/测试执行/业务提交 |
| V1.5 | 2026-11-01 | t_22b3495f：三件套改列已离线ACCEPTED，保留旧失败；冻结D-06唯一Agent训练OHLC方案及SPEC V1.5 §9，价格/volume能力隔离、来源/时间/参数冻结、鉴权兼容/预算/真实验收边界；Design已由子卡t_1f4c8c58同步至V1.4（三层已同步），本卡仅两文档及交接，基线额外采集OMITTED_BY_AUTHORIZATION，无实现/测试/网络/业务执行 |
