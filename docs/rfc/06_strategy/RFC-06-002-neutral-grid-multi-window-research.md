# RFC-06-002: 中性等比永续网格四窗口研究

## 元数据

| 项 | 值 |
|---|---|
| 版本 | V1.9 |
| 状态 | 既有 B-001/杠杆/三件套/G-02 离线工程线及 F-01..F-05 已验收；审计 D-01 局部撤销（§9 / SPEC V1.6 §10 / Design V1.5 §12）已实现并通过独立 Verify（离线，335 passed，t_8a23ea34），主控离线签收；API 进程已受控重启并真实 HTTP 验证公共 Gate swap 读取与本地重采样（api_runtime_loaded=VERIFIED，见 data/reports/2026-11-02-quantdinger-d01-local-revert/runtime-verification.md）；G-01（缓存身份）、G-03（历史乘数适用性）仍 OPEN，historical_evidence=UNKNOWN、full_research_status=DEFERRED，后台角色未加载、16业务仍禁止；V1.7 按 Pascal 2026-11-03 D1 决策冻结 v=0 零成交 bar 合法化契约（§10），native 层已由 t_aa056536 实现并通过平台侧验证；V1.8 按 t_b8db70b3 契约决策（D2）将范围扩展至消费链 crypto.py 两处数据有效性谓词（§10.4），消费链放行待实现与独立 Verify |
| 作者 | YQuant Principal / t_cfccfe2c / t_1af91929 / t_9fddffed / t_1b635d49 / t_22b3495f |
| 日期 | 2026-11-03（V1.8；V1.7 为 2026-11-03 同日续修订），Asia/Shanghai（UTC+08:00） |
| 项目 | /home/pascal/workspace/yquant-investment |
| 来源 | data/tasks/active/2026-10-30-neutral-grid-research/pipeline-intake.md |
| 配套 | [SPEC-06-002](../../spec/06_strategy/SPEC-06-002-neutral-grid-multi-window-research.md) |

> 当前修订：Pascal 于 2026-11-02 同意审计 D-01 的局部撤销，执行边界见 §9、SPEC V1.6 §10、Design V1.5 §12。此处“审计 D-01”不是 §3 的“D-01 时间与市场身份”。先前“本卡/本轮/尚未实现”等是旧阶段时点记录；仅与公共取数研究阻断有关的要求由本修订替代，旧验收不追认或抹除。当前撤销已实现并通过独立 Verify（离线），API 进程也已受控重启并真实请求验证；这只关闭“API 已加载”，不表示历史证据通过或研究准入成立。最新修订（V1.7）：Pascal 于 2026-11-03 决策（D1）将 Gate swap 真实零成交 bar（raw_v_contracts==0）从 fail-closed 拒绝网移出、定为合法市场状态，契约见 §10 / SPEC V1.7 §11 / Design V1.6 §13；本修订仅文档契约，实现/验证/运行加载均未发生，不解除 16 业务研究锁。 V1.8（t_b8db70b3，D2 契约决策）：F 卡（t_aa056536）实测证明消费链 crypto.py 两处 volume>0 数据有效性前提仍拒绝 v=0 bar，原 §10.4（V1.7）「不改 crypto.py」与 D1 预期效果「v=0 bar 正常产出、不再抛错」构成文档内部矛盾；按 D1 既有语义将 §10.4 范围扩展至 crypto.py 仅两处谓词放宽（≤0 → <0，即 volume>=0）与对应 xfail 装饰器移除，不扩大 D1 语义边界；消费链放行待实现卡与独立 Verify，R-01 仍未修复，16 业务锁不解除。

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
| app/data_sources/native_crypto.py:838-854（2026-11-03 复核） | _gate_swap_volume_number 对非 sum 字段拒绝 number==0；base_volume 乘积复用同一校验兼作乘法上/下溢守卫；V1.7 §10 将 raw_v_contracts==0 移出拒绝网，负值/非有限/缺字段/乘数校验不变 |
| app/services/strategy_v2/runtime.py:1274-1281（2026-11-03 复核） | _liquidity_cap 对 volume<=0 返回 None（零量 bar 不设 10% 上限）；是 §10 R-01 披露的依据，与上方“volume<=0 返回无上限”既有事实一致 |

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

## 9. 审计 D-01：局部撤销公共 Gate 取数的研究阻断

Pascal 已确认：不应把单项研究的历史证据要求施加给 QuantDinger 通用取数。撤销 Native 公共 Gate swap 解析必须 synthetic 来源/历史有效期覆盖才返回的限制，以及 crypto 公共消费者因历史适用性 unknown 和缺重采样逐根研究证明而拒绝整批数据的限制。真实数据不得伪标 synthetic 或 verified；当前快照的历史适用性诚实保留 unknown。

保留 Gate 张数到基础币的单次换算、精度、必要产品身份/单位/非法数值检查、公共六列接口和已独立验收的 F-01..F-05。不能整提交 revert、整文件还原或重引错误单位；已证明错误的单位/身份、旧裸缓存不得冒充正确基础币证据。恢复既有重采样，但不得将聚合 bar 冒充带原始逐根历史证据的 bar。

本修订优先替代 §5、D-06 及 SPEC/Design 中“公共 OHLCV 历史缺证必须阻断”“旧 OHLCV 必须拒绝才证明训练隔离”及针对旧阶段的禁止修改条款；这些旧表述保留为原阶段契约记录，不再作为本次撤销的验收要求。训练通道的身份、摘要、无 volume、backtest_eligible=false 等要求不变；普通 Agent 分支的产品身份能力未补齐，不删除 training_ohlc。

研究门槛与平台公共可读性分开：G-03、原研究锁、16 业务禁止仍保留；公共可返回 unknown 不证明研究合格。不在公共回测/交易入口另加同类限制，不修改撮合或另建准入系统；本次不声称所有通用消费者会自动拒绝 unknown。局部撤销仅离线代码与直接测试，按 Light Flow 实现→独立验证收口，用户已确认范围，不另建 RFC/SPEC/Design 阶段或独立 Review。精确文件/验收见配套 SPEC §10 与 Design §12。

无真实取数、凭据/数据库/缓存访问、回测/交易、部署/服务加载、commit/push/fetch/merge、分支切换或 gitlink 变更授权。upstream 整合不是本次前提。

## 10. V1.7 修订：v=0 零成交 bar 合法化（Pascal 2026-11-03 D1 决策）

### 10.1 动机与取证摘要

2026-11-03 探针 job（jobId 2b09903769834f7592ddd90a1ce49ebe，2026-11-03T02:44:11Z）以 strategyV2.noMarketData 失败，根因链为：Gate.io 合约 API 在 JUP/USDT 15m 窗口返回 101 根 v=0（无成交）bar → 本地严格校验 `_gate_swap_volume_number` 将 raw_v_contracts==0 判非法并整窗拒绝 → 数据加载层抛 gate.swapVolumeInvalid。完整诊断见 `data/reports/2026-11-03-pathb-probe-jup-15m/nomarketdata-root-cause.md`（下称"诊断报告"），关键取证结论：

1. v=0 bar 数据自洽，是真实零成交而非上游脏数据：OHLC 四价相等 29/29、open 精确等于前一根 close 17/17、sum 同为 0、对照组（v>0）235/260 OHLC 不全等。
2. 严格校验不在上游 v5.8.1（e75f0cfa）中，由本地杠杆修复轨提交 19fe726 按 DESIGN-06-002 V1.1 §3/§3.2 引入；DESIGN-06-002 原文（§3）明确预见真实零成交 bar 并有意选择 fail-closed（"不把 0 送入无限流动性分支；真实无成交 bar 也是研究模型无法安全表达的限制，不捏造正 epsilon"），是经完整流水线（R3 153 项 Verify + Review APPROVE）冻结的契约，不是疏忽。
3. 四标的全采样（2026-08-01 ~ 2026-10-31，15m，Gate 原始 API 直查）均存在零成交 bar：JUP 101/8862（1.14%）、AAVE/SUI/PUMP 各 30/8862（0.34%）；单根 v=0 即整窗拒绝，SPEC-06-002 的 16 窗口研究无一可原样跑通，且不会自愈（每次提交冷缓存必现）。这是系统性阻塞，不是 JUP 特例。

因此本问题定性为"冻结设计契约（有意 fail-closed）与低流动性合约真实市场状态的冲突"，修订它就是契约修订。Pascal 于 2026-11-03 拍板（D1）：将真实零成交 bar 从拒绝网移出、定为合法市场状态。

### 10.2 D1 语义边界（冻结，不得扩大）

以下边界逐条来自 Pascal D1 决策，实现与后续验收均不得超出：

1. **合法 bar**：raw_v_contracts==0（由 Gate v 字段精确数值零判定，含 "0"/0/0.0 等同值形态）为合法零成交 bar：base_volume=0、quote_volume=0（当 sum 存在且为 0 时）、volume_unit=base 与证据对象字段照常产出；行为语义为"该 bar 网格限价单不成交"。
2. **仍拒绝五类**：null/缺字段、负值、非有限值（NaN/±Inf）、乘数缺失或非正、类型非法（bool/字符串非数值）保持既有拒绝语义与既有错误标识，gate.swapVolumeMetadataMissing / gate.swapVolumeMetadataInvalid / gate.swapVolumeHistoricalUnverified / gate.swapVolumeInvalid / gate.swapVolumeEvidenceMissing 五类错误语义不变；其中 raw_v_contracts 的 null/负值/非有限/非数值仍以 gate.swapVolumeInvalid 拒绝。负值边界口径：IEEE 754 负零字面量（"-0"/-0.0）数值上 ==0 且不 <0，按第 1 条归入零成交合法分支，不视为负值，实现不加符号位特判（见 Design §13.1 冻结口径）。
3. **不捏造正 epsilon**：不引入任何"最小流动性下限"或正 epsilon 修正，零成交 bar 不进入任何把 volume>0 作为前提的撮合可用性分支。
4. **单位安全链不变**：raw_v_contracts × quanto_multiplier 单次换算、乘数缺失/非正拒绝、乘法结果上溢/下溢守卫（含 base_volume 乘积结果为非有限值或异常趋零的拒绝）不变；乘数校验先于 v=0 合法化分支执行。
5. **证据对象不变**：gate_swap_volume_v1 字段集合与取值语义不变（v=0 bar 同样携带完整证据；生产当前快照形态下 historical_applicability 如实为 unknown，不因 v=0 升级为 verified；synthetic 测试 fixture 覆盖区间仍按既有判定为 verified，见 SPEC V1.7-01）。
6. **sum 缺失仍为 null**：quote_volume 仅取官方 sum 原始值，缺失仍为 null；sum==0 是合法值（与 v=0 一致），非法形态（null 显式传入、负值、非有限、bool）仍拒绝。
7. **范围收窄**：本修订只改变 v==0 的处理分支；既有流动性 cap（volume>0 时按 DESIGN §3 / SPEC §3.7 的 0.1×volume 逐订单上限）对 volume>0 bar 的行为不变，单位换算、身份校验、历史适用性 unknown 语义、训练通道 volume_status=not_provided、G-01/G-03 状态均不变。

### 10.3 R-01 平台行为披露（必须随实现交付，防止把披露写成已交付）

D1 第 1 条中"该 bar 网格限价单不成交"是研究语义声明；平台模拟撮合器现状（2026-11-03 复核 runtime.py:1274-1281 `_liquidity_cap`）对 volume<=0 的 bar 返回 None（不设 10% 上限），与 RFC §4 既有事实"volume<=0 返回无上限"一致。即：仅按 Design §13 放行 v=0 bar 后，回测器在零成交 bar 上不会自动产生"不成交"行为。本契约不授权修改 runtime 撮合器（平台零量撮合语义明确不在本修订范围）；因此实现必须交付并固定 R-01 披露（位置与载体见 Design §13.3），且研究语义与平台模拟现状的差异必须逐字披露，不得把披露写成已修复。研究语义声明本身可成立的原因：中性格限价单要求价格触及格线才成交，零成交 bar 的 OHLC 四价相等且 open==prev_close，价格未动，挂单在该 bar 触发限价成交的概率由市场结构决定；若后续研究需要平台级零量撮合语义变更，另行走契约修订，不在本修订范围。

### 10.4 实现授权范围与验收增量

**V1.7 原授权（已由 t_aa056536 执行完毕并通过平台侧验证）**：仅 `app/data_sources/native_crypto.py` 的 v=0 处理分支——新增零放行 helper 并改造 raw_v_contracts 调用点；`_gate_swap_volume_number` 本体及 base_volume/sum 调用点不动（下溢/上溢守卫依赖其零拒绝，见 Design §13.1）；受影响测试按 Design §13.2/§13.3。实测结果：平台侧 pytest 237 passed + 1 xfailed（该 xfail 为下方 D2 解除前的显式契约阻断标记），主仓 185 项冻结基线 185/OK/exit 0。

**D2 契约决策（V1.8，t_b8db70b3，主控 yquantprincipal；依据为 D1 既有语义，非语义扩权，Pascal 保留否决权）**：t_aa056536 实测证明 `app/data_sources/crypto.py` 消费链两处 `volume > 0` 数据有效性前提仍拒绝 v=0 bar（crypto.py:648-651 重采样路径、crypto.py:694-700 单 bar 路径，标识 gate.swapVolumeInvalid），原 §10.4「不改 crypto.py」与 D1 预期效果「v=0 bar 正常产出六列与证据，不再抛错」构成文档内部矛盾。§10.2 第 1 条将 v=0 定为合法零成交 bar 且行为语义为「该 bar 网格限价单不成交」，要求该 bar 必须穿过消费链到达研究/回测层，故判定：文件范围扩展至 crypto.py 且仅限两处谓词 `candle[5] <= 0` 放宽为 `candle[5] < 0`（等价 volume>=0 放行；保留 math.isfinite 与单 bar 路径 `evidence["base_volume"] != candle[5]` 一致性校验；错误标识与消息文本均不变）。该变更是消费链数据有效性网关的放宽，不属于 §10.2 第 3 条所禁止的「把 volume>0 作为前提的撮合可用性分支」（该分支指 runtime `_liquidity_cap` 等撮合语义，维持不动，R-01 差异仍未修复）；不引入 epsilon，五类错误对既有拒绝场景的语义不变。对 v=0 本增量，本条优先于 §5/D-06 阶段「既有 volume 校验不得改写或放宽」类旧阶段禁止条款；旧表述保留为原阶段记录。

**V1.8 授权范围**：实现文件仅两个——`app/data_sources/crypto.py`（仅上述两处谓词字符变更，文件其余部分不动）与 `tests/test_gate_swap_volume_units.py`（删除 `test_gate_zero_volume_bar_survives_the_consumer_chain` 之上的 `@pytest.mark.xfail(strict=True)` 整块装饰器（当前工作树 148-158 行），函数体不动；新增重采样路径 v=0 独立用例锁定 crypto.py:648 谓词；其余用例不动）。不改 native_crypto.py（本增量）、runtime 撮合器、训练服务、factory.py、主仓源码。验收：Design V1.7 §13.3/§13.4 冻结命令全绿（无 failed/xfailed/xpassed）+ 主仓 185 项基线重跑 185/OK/exit 0；SPEC V1.8 §11.2（V1.7-06 扩展、V1.8-01）。禁止消耗 QuantDinger job 配额、禁止解除 16 窗口研究锁；16 窗口是否放行由后续卡在消费链实现与独立 Verify 通过后按新契约另行评估。

### 10.5 证据多页累积契约缺口（V1.9，主控按 Pascal 2026-11-03「精简、不发散」指示直接修订）

**D3 契约决策**：v=0 修复（§10.2/§10.4）落地后，探针 job fe16b257（2026-11-03 20:09，单次提交无重试）暴露确定性缺口——92 天 15m 窗口（10356 根）超过 Gate 单页 1000 上限，`_parse_gate_swap_ohlcv` 每页重置证据状态，前 8 批约 9000 根 bar 证据丢失 → `gate.swapVolumeEvidenceMissing`（mock 实证复现，见 `data/tasks/active/2026-11-03-probe-rerun-fe16b257/failure-evidence.md`）。判定：DESIGN V1.1 §2.2/§3.2 逐 bar 证据契约未定义多页累积语义，属契约缺口而非实现错误。修订：同一请求线程内 identity（symbol/interval/native_contract）完全相同的多批拉取，证据按 bar 时间戳累积 merge（容量上界 20000、淘汰最旧）；identity 变化或线程更替仍整体重置。逐 bar 溯源、五类错误、applicability、v=0 合法零成交、R-01 披露（不修复）全部不变。行为契约全文见 Design V1.8 §14；本修订仅文档，实现归 F3 卡，探针重跑由独立执行卡承担，16 窗口研究锁不解除。

## 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.9 | 2026-11-03 | 主控按 Pascal「精简、不发散」指示直接增 §10.5（原 E3 卡 t_20d5afbd 停止，无产出）：D3 契约决策——证据多页累积缺口定案，同 identity 逐页 merge（容量 20000 淘汰最旧）、identity 变化/线程更替仍整体重置；逐 bar 溯源/五类错误/applicability/v=0/R-01 不变；指向 Design V1.8 §14 / SPEC V1.9 §11.5；仅文档，实现归 F3 |
| V1.8 | 2026-11-03 | t_b8db70b3（E2）：D2 契约决策消除 §10.4 内部矛盾——F 卡实测消费链 crypto.py 两处 volume>0 前提仍拒绝 v=0 bar（648-651 重采样、694-700 单 bar），按 D1 既有语义扩展范围至 crypto.py 两处谓词放宽（≤0→<0，保留 isfinite 与证据一致性校验、标识/消息不变）+ test_gate_swap_volume_units.py 的 xfail(strict) 装饰器删除与重采样 v=0 用例；对 v=0 增量替代 §5 旧阶段 volume 校验禁改条款；native 层已实现（t_aa056536，237 passed+1 xfail）、消费链放行待实现/独立 Verify；R-01 未修复；job 0、16 锁不解除；指向 SPEC V1.8 §11 / Design V1.7 §13.4 |
| V1.7 | 2026-11-03 | t_e5ac39e6：按 Pascal 2026-11-03 D1 决策新增 §10，将真实零成交 bar（raw_v_contracts==0）从 fail-closed 拒绝网移出、定为合法市场状态（base_volume=0、quote_volume=0 当 sum==0、该 bar 网格限价单不成交）；保留五类拒绝语义、单次换算链、乘数校验、无 epsilon、证据对象 gate_swap_volume_v1、sum 缺失 null；新增 R-01 披露（平台 _liquidity_cap 对 volume<=0 返回 None 的现状与研究语义差异）；指向 SPEC V1.7 §11 / Design V1.6 §13；仅文档修订，实现/验证/运行加载未发生，16 业务锁不解除 |
| V1.6 | 2026-11-02 | Pascal 同意审计 D-01 局部撤销；§9 将公共可读性与研究历史资格分开，保留单位/精度/五项修复和研究锁；指向 SPEC V1.6 §10 / Design V1.5 §12；撤销实施与独立验收已离线完成（t_8a23ea34，335 passed），API 进程已受控重启并真实请求验证；G-01/G-03 与历史证据仍未闭合 |
| V1.0 | 2026-10-31 | 五点语义、边界、源码事实及 B-001 阻塞；未实施或执行业务 |
| V1.1 | 2026-10-31 | 续接run3395：按Intake最小Gate授权同步状态/范围/单位/禁止条款/验收；T1契约PASS可交接T2，技术pending，原五点不降级；无实现/业务 |
| V1.2 | 2026-10-31 | 续接run3399：按Pascal离线授权冻结B-001离线修复子阶段执行/验收，状态同步T2分段交付；原五点与16窗口标准保留，技术仍pending。主控读回同步校正未来CLI工作与当前离线测试边界；无实现/业务提交 |
| V1.3 | 2026-11-01 | t_9fddffed：同步B-001离线已验收及未加载/历史未知状态；仅启用客户端杠杆透传、三函数必要抽取与离线验收，指向SPEC V1.3 / Design V1.2；通用证据/恢复增强与研究仍未启用，无源码/测试执行/业务提交 |
| V1.4 | 2026-11-01 | t_1b635d49：同步Pascal对Design §5-7三件套窄启用授权——杠杆子集标记已实现并验收（79/79 OK、Review APPROVE），新增三件套待实现契约（grid_research.py参数化纯函数库、指标/强平/汇总、策略实例含GRID_AUDIT_V1审计回调）；§1/§5/§6/§7状态与allowlist最小同步；16业务执行、服务加载/缓存/凭据、通用evidence/稳定键恢复仍不启用；指向SPEC V1.4/Design V1.3，无源码/测试执行/业务提交 |
| V1.5 | 2026-11-01 | t_22b3495f：三件套改列已离线ACCEPTED，保留旧失败；冻结D-06唯一Agent训练OHLC方案及SPEC V1.5 §9，价格/volume能力隔离、来源/时间/参数冻结、鉴权兼容/预算/真实验收边界；Design已由子卡t_1f4c8c58同步至V1.4（三层已同步），本卡仅两文档及交接，基线额外采集OMITTED_BY_AUTHORIZATION，无实现/测试/网络/业务执行 |
