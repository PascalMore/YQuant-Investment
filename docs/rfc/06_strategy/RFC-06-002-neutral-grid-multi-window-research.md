# RFC-06-002: 中性等比永续网格四窗口研究

## 元数据

| 项 | 值 |
|---|---|
| 版本 | V1.2 |
| 状态 | T1 契约 PASS 保留；T2 已按 Pascal 离线授权分段修订至 V1.2：B-001 修复要求与最小范围不变，新增离线子阶段执行/验收；技术仍 pending，非平台/研究通过 |
| 作者 | YQuant Principal / t_cfccfe2c / t_1af91929 |
| 日期 | 2026-10-31，Asia/Shanghai（UTC+08:00） |
| 项目 | /home/pascal/workspace/yquant-investment |
| 来源 | data/tasks/active/2026-10-30-neutral-grid-research/pipeline-intake.md |
| 配套 | [SPEC-06-002](../../spec/06_strategy/SPEC-06-002-neutral-grid-multi-window-research.md) |

## 1. 结论与动机

冻结 Pascal 五点研究的业务语义，复用 Strategy Lab 和 QuantDinger 原生 V2 历史回测，不建第二个引擎。历史八份结果只是一个季度的账户规模对照，不是本次十六窗口结果；不从旧助手口述推断正确 10x、真实流动性不足或全年研究完成。

已知平台单位缺口 B-001：Gate 永续原生数据适配把合约张数 v 直接作为 volume 交给按基础币数量限流的 Broker，链路没有相应乘数换算。仅增加 CLI 杠杆参数无法修复该链路。依据 pipeline-intake §追加决策，Pascal 已授权最小 Gate 单位修复，原 run3395 BLOCKED 保留为历史，授权等待已解除但技术仍 pending。T1 只冻结修复要求，不要求先修代码才能完成需求/Design；主控读回 RFC/SPEC 后才可解除既有 T2 门禁。T3 实现、T4 真实独立验证、T5 Review 确认前，不得称技术已修好；16 业务提交仍须在 T4 相关独立前检通过后。

2026-10-31 Pascal 批准 B-001 离线修复子阶段先行交付：仅 Gate swap 单位换算、缺证拒绝、消费者衔接、合成/offline 测试属当前可执行离线范围，`offline_unit_fix` 可离线验收；`runtime_loaded`、`historical_evidence`、`full_research_status` 分列保留，未经运行中加载、真实历史取证或完整研究不得置 PASS 或合并汇报。原五点最终标准与 16 窗口验收不删除不降级；CLI 抽取、杠杆参数、研究协调器、策略实例与16窗口实施本轮暂不实施、保持待办。

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

已知平台缺口 B-001（授权已定、技术 pending）：Gate v（张）未经换算便与基础币成交量比较，未知产品乘数时不能证明真实模拟参与率与成交容量正确。冻结标准 volume 为基础币；保留 raw_v_contracts、base_volume、乘数、单位、产品身份及来源/有效期/检索时间。优先复用正确既有原生路径。元数据不足不得默认乘数1；旧 PUMP instrumentRulesSnapshot 的 source=historical_fallback_no_snapshot、contract_size=1.0 不是有效历史乘数证据。历史适用性未知须显式 UNKNOWN/缺证，不以当前乘数硬回填历史；缺失或非正 volume 不得送入将其解释为无限流动性的撮合分支。不得事后仅重标报表单位追认错误撮合 PNL，也不得缩放订单冒充修复。

当前离线子阶段 T3 仅可按 T2 Design 精确文件/函数 allowlist 修改现有 app/data_sources/native_crypto.py 的必要 Gate swap 单位/元数据分支、确有消费者必要时的 app/data_sources/crypto.py 单位衔接及对应测试；synthetic/offline 单测是当前授权的唯一测试范围。缓存兼容、缺元数据的阻断方式与回归细节由 T2 冻结；不建历史元数据平台/数据库迁移，不改 runtime 撮合、资金模型、生产配置、Binance/spot/其他交易所行为。既有子模块 proxy dirty 按 b001-submodule-baseline.json 排除归属，不修改/还原。Agent 薄层抽取、杠杆参数透传、研究协调器、策略实例与 16 窗口执行仅为未来未启用候选，本轮禁止实现。

另有能力核验项 C-002：当前 Agent klines 无同产品/venue 参数。T2 若可用现有回测沙箱多频历史+日志无前视导出，需证明同产品身份、历史覆盖、参数冻结先于交易及预算可行；否则需要最小 Agent 行情接口透传产品/venue 与来源字段的额外平台授权。不能调用 Human 路由或直接官方行情 API绕过 Agent 业务通道。仅公开官方文档读取不受此禁止影响。

C-003（历史与真实证据待核验）保持未通过：完整历史、官方同窗乘数/档位、日志连续性与真实指标须后续取证。C-002/C-003 不自动授权新接口或改变历史数据策略，必要缺口须有具体证据后上报。最小 B-001 修复授权仅来自本轮 Intake 追加决策，不降低原五点验收；T1/T2 可围绕该待实现项完成，T4 独立前检未通过前不得提交16业务。若真实 E2E 需要现有进程加载变更，T2 须列现有 unit/最小重启影响交主控判断，不能自行部署、重启、另起实例或把离线 PASS 当实际生效。

## 6. 工程边界

CLI 2502 行的局部抽取约束属于未来完整研究工具阶段：届时仅为 Agent 信封/幂等/参数/结果保存做局部抽取，保持现有 Human/trade 行为与 import/patch 兼容，不全量重构或继续在超阈值文件堆能力。当前B-001离线阶段不改CLI、不执行其70项回归，精确生效范围为Design的Gate适配/消费者及对应测试。

T1 写入仅本 RFC、对应 SPEC、任务目录 t1-handoff.md。复用 06-001，不修改其历史文档；不写 Design。共享 dirty 基线为 workspace-baseline.json，不 reset/stash/clean、不改历史原始 evidence、不 commit/push。

## 7. 验收与阶段

完整链 T1 RFC/SPEC→T2 Design→T3 Implement→T4 独立 Verify+真实研究→T5 Review→T6 Closeout，使用既有图，不创建新卡。2026-10-31 Pascal 授权先行交付 B-001 离线修复子阶段：仅 Gate swap 单位换算、必要消费者衔接、缺证拒绝与 synthetic/offline 测试属当前授权范围；CLI 抽取、杠杆参数、研究协调器、策略实例与 16 窗口执行暂不实施、保持待办。T4 仍为唯一提交本轮目标作业角色，每合约四目标、外层job<=8/组、墙钟<=1800秒/组；研究数据请求<=50/组，禁止借拆组重复预算、进化或自动重跑。

完整执行验收见 SPEC §5。T1 契约 PASS 与 T2 离线分段修订完成后，离线子阶段按 SPEC §5 离线验收先行执行与独立验证；完整研究的实施、独立验证与审查仍按原链推进。原五点/16窗口最终标准不删除不降级。策略 FAIL、上市不足可报告，但主指标缺失不能最终通过。

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
