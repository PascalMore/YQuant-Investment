# SPEC-06-001: Strategy Lab — 最小 QuantDinger 操作型 Skill

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-10-29 |
| 最后更新 | 2026-10-30 |
| 版本 | V1.4（方案 C：仅延长 spy-ma-smoke 窗口；待独立 Gate，非整体验收） |
| 来源 RFC | [RFC-06-001 V1.4](../../rfc/06_strategy/RFC-06-001-strategy-lab.md) |
| 配套 Design | [DESIGN-06-001 V1.4](../../design/06_strategy/DESIGN-06-001-strategy-lab.md) |
| 目标模块 | strategy（skills/strategies/strategy-lab/） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer, YQuant-Reviewer-Principal |

## 1. 需求摘要

实现 `skills/strategies/strategy-lab/` 操作型 Skill：SKILL.md 承载「定义 → 执行 → 交付」业务三步与自动进化子流程的最小编排约定，配最小薄调用脚本与策略目录结构。交易类经 QuantDinger Human API（JWT）完成私有源码保存、原生回测与一次有界原生进化；研究类用平台真实数据跑可重跑 Python。全部判定语义、入口矩阵与停止约束以本 SPEC 为准，Developer 不做语义再决策。

## 2. 范围

### 2.1 In Scope

- [ ] S-1 `skills/strategies/strategy-lab/SKILL.md`：业务三步、自动进化触发/调用/判定/停止规则、目录约定、安全边界（面向 AI 的操作说明，不是 runtime）。
- [ ] S-2 最小薄调用脚本集（Python，标准库 + 现有依赖；单文件 CLI 风格，无 SDK/包结构），文件清单以 Design §allowlist 为准，行为满足 §3。
- [ ] S-3 交易样例目录 `strategy-lab/strategies/<strategy_id>/`（README/spec/config/strategy.py/reports），走完基准回测 → 自动进化 → 判定 → 最终回测闭环。
- [ ] S-4 研究样例目录 `strategy-lab/strategies/<strategy_id>/`（research.py + reports），真实数据可重跑。
- [ ] S-5 父入口路由：`skills/strategies/SKILL.md` 增加指向 strategy-lab 的最小行级说明。

### 2.2 Out of Scope

- [ ] 无平台/引擎/优化器/任务系统/数据库/运行档案；无 version/runs/manifest/强制快照。
- [ ] 不新建 MCP/SDK/统一运行时；不修改 QuantDinger 子模块源码；不改 Agent 网关。
- [ ] 不做自动实盘部署、Demo/Live 下单、调度注册、凭据签发、生产 DB 写。
- [ ] 不把网格示例的全部金融建模功能扩成首版引擎。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | 源码保存并读回：编译校验（`POST /api/strategies/script-sources/compile`）→ `POST .../script-sources/create`（客户端显式 visibility=private, status=draft；Human 服务仅默认这些值，不强制覆盖 payload）→ `GET .../script-sources/detail?id=` 读回 | 策略源码、名称 | sourceId + 读回一致的 detail（name/code/metadata/asset_type/visibility/status；metadata允许平台canonical补充，见Design §3.3） | 编译 400（codeRequired/contractInvalid）→ 停止；创建 500 → 停止；读回不一致 → 仅重读 ≤1 次后停止，create 不重发 |
| F-002 | 基准回测：`POST /api/backtest/jobs`（sourceId + 窗口/成本/params，persist=true）→ 轮询 `GET /api/backtest/jobs/{jobId}` 至 succeeded/failed/cancelled → `GET /api/backtest/get?runId=` 读回 run | spec 窗口与成本 | runId、全段指标（totalReturn/maxDrawdown/sharpeRatio/annualizedReturn/winRate/totalTrades）、dataProvenance、executionAssumptions | 402 insufficient_credits / 400 BacktestRangeLimitError → 如实停止；job failed 带 error → 停止 |
| F-003 | 进化适用性判定：`GET /api/strategy-evolution/parameter-space?sourceId=` | sourceId | 判定结果 ∈ {触发, 跳过+原因} | scope=none / 无 optimizable 参数 / 用户显式禁优化 / 研究类 → 跳过分支，正常交付 |
| F-004 | 预算估算：`POST /api/strategy-evolution/estimate`（parameterSpace + config） | 限定后的参数行、config；folds固定4 | backtestRuns/relativeUnits/resourceTier/minimumRecommendedTrials/sampleSufficient/isUpperBound | 超预算 → 仅收缩 trials/声明内空间后重估 ≤2 次，folds不变；仍超 → 停止并报估算值 vs 内部预算，不虚报实耗 |
| F-005 | 一次有界进化：`POST /api/strategy-evolution/run`（202+jobId）→ 轮询 `GET .../jobs/{jobId}` ≥15s 间隔至终态 → `GET .../jobs?sourceId=` 交叉核对列表可见 | 步骤 F-003/F-004 产物 | 终态 succeeded: result（summary/bestParams/topCandidates/selection）；failed: progress.failure 诊断；cancelled | failed/cancelled/超预算 → 停止并报告；禁止自动重跑或二次 run |
| F-006 | 判定（语义冻结，见 §5）：先核对候选适用证据 → top候选与基准组成最多5组全段证据（已有基准读回复用、参数去重）→ 同窗口同成本原生全段回测过全段硬约束 → 按预定义目标比较；不拿平均分窗MDD先淘汰全段候选 | 进化 result + 候选/基准全段回测 run | 推荐：candidate（+推荐参数）或 baseline-kept 或 no-qualified-candidate 或 insufficient-evidence | 全段回测失败/数据缺失 → insufficient-evidence，不判通过 |
| F-007 | 最终回测与 UI 可查：推荐项跑 `POST /api/backtest/jobs`（persist=true）→ runId 读回 → 报告记录 sourceId/runId 与 UI 入口 | F-006 推荐 | 最终 runId + 本地报告（对比表、参数、限制、平台 ID、复现命令） | 失败 → 报告保留基准 runId 并说明 |
| F-008 | 研究样例：research.py 用 Agent `GET /api/agent/v1/klines`（market/symbol/timeframe/limit/before_time 分页）或等价 Human 接口取真实数据 → 分析 → 写 `<id>/reports/`；同脚本二次执行成功 | spec 的问题定义 | 报告 + 数据来源/参数/时间范围标注 + 复现命令 | 数据缺口 → 报告列明，不伪造；401/403 → 阻塞披露 |
| F-009 | 负分支可断言：无 optimizable 参数跳过、estimate 超预算收缩停止、job failed 停止、401 停止不重试 | 构造的最小 fixture/假响应或断言用例 | 明确断言通过/失败记录 | fixture 验证仅覆盖分支逻辑；接入验收（F-001~F-008）必须真实，两者分开陈述 |

## 4. 数据与接口契约

入口矩阵与请求/响应语义继承 RFC-06-001 §5.3（已对源码核实）；补充实现级要点：

- Human 信封：成功 `{"code":1,...,"data":...}`，普通业务失败 `{"code":0,"msg":"<错误键>","data":...}`；HTTP 400/402/404/500。认证失败可为HTTP401/code401，先检查HTTP状态。认证头 `Authorization: Bearer <既有会话>`，7天、单客户端（token_version），仅从既有安全机制注入；禁止新造 token 或绕认证。
- 进化 `POST /api/strategy-evolution/run` 请求仅接受 `{sourceId, startDate, endDate, initialCapital, commission, slippage, leverageEnabled?, leverage?, parameterSpace[], config}`；parameterSpace 行超出声明范围返回 400 `strategyEvolution.parameterRangeOutsideDeclaration|parameterNotDeclared|parameterStepInvalid`。平台 `config` 合法域：`method∈{tpe,grid,random}`（默认 tpe）、`trials`（tpe≥24，随机/网格上限见平台）、`folds` 4-10、`trainRatio` 0.55-0.85、`blindRatio` 0-0.3、`costMultipliers` 0-10、`seed`；首版客户端另受§8预算约束，folds仅4，不依赖平台夹值。
- 进化 result 关键字段（判定输入）：`summary.recommended/sampleSufficient/oosReturn/oosSharpe/maxDrawdown/blindReturn/blindPassed/actualBacktestRuns`、`bestParams`、`topCandidates[]`、`summary.selectionObjective="oosCompoundedReturn"` 与 `selection.objective="oosCompoundedReturn"`、`validation.{pbo,deflatedSharpe,monteCarlo,costStress}`（各项可 `available:false`）；失败时 `progress.failure.{messageKey,dominantReason,reasonCounts,actualBacktestRuns}`。缺字段如实未知，不伪造另一层级字段（engine.py:219-265）。
- 口径声明（防误读）：`summary.maxDrawdown` 仅为 validation/OOS 折回撤绝对值平均，不含 blind、不是全段最大回撤（statistics.py:27-55；无validation时源码兜底100）。blind证据由 `summary.blindReturn/blindPassed` 独立提供。硬约束核对只认 F-006 原生全段读回 run 的 `data.result.maxDrawdown`（峰值净值口径）。fold 复用是单次回放后按时间切片，不得称逐折重新训练；`selection.blindUsedForSelection=false` 仅描述原生搜索，最终全段复检已包含blind，不能再声称最终选参有完全未触碰的独立留出集。
- 私有性源码依据：Human `app/services/script_source.py:247-283` 接受payload visibility/status，private/draft只是默认；F-001显式字段与精确读回不可省略。Design §3.3固定首版同Human JWT/sourceId/owner闭环。
- 预算字段：内部 `estimate.backtestRuns/relativeUnits` 与成功 `result.summary.actualBacktestRuns`（失败时 `progress.failure.actualBacktestRuns`）分开记录，也与外层持久化backtest jobs分栏；estimate.isUpperBound=false，不能把估算当实耗或服务端硬上界。folds固定4，超预算只降trials/缩空间或停止；首版样例与上限见§8、Design §3.5。
- 零付费预检：先具备可用Human JWT，再以同一认证读 `GET /api/settings/public-config`（settings.py:2087-2099的login_required），明确 `data.billing_enabled=false` 才提交；true/缺失/401/403即停止，不访问billing写接口。该名称不表示匿名可读。
- 回测 job（Human）：`POST /api/backtest/jobs` 202 返回 jobId；请求字段与 Agent 网关不同，接受 `sourceId/strategyId/code` 关联与 `persist`；范围受 compile 返回的 `backtestRangePolicy.maxSelectedDays` 约束（按市场/周期，如 USStock 1D 10 年、1m 30 天）。
- 未授权调用不可达清单：Quick Trade 下单、deployments 创建/启停、credentials、billing、Live 相关 agent 路由（SCOPE_T/C）——Skill 不生成任何对它们的调用。

## 4.bis 持久化契约

平台持久化（QuantDinger 所有，YQuant 只读引用）：qd_script_sources（私有源码，读回验证）、回测 run 仓库（runId、结果、dataProvenance、executionAssumptions）、qd_agent_jobs（kind=strategy_evolution，status/progress/result/error，列表按 sourceId 过滤）。YQuant 本轮不新增任何数据库/集合/schema；不直写平台表。

本地持久化（唯一写入范围，均无 schema 迁移需求）：

| 存储对象（路径） | 字段/内容 | 类型 | 必填 | 生命周期 | 隐私级别 |
|---|---|---|---|---|---|
| `strategy-lab/strategies/<id>/spec.md` | 目标/参数语义/硬约束/预算/验收 | md | 是 | 随策略目录保留 | L1 |
| `strategy-lab/strategies/<id>/config.json` | 可调参数数值 | json | 交易样例是 | 随策略目录保留 | L1 |
| `strategy-lab/strategies/<id>/strategy.py` \| `research.py` | 主脚本 | py | 是 | 随策略目录保留 | L1 |
| `strategy-lab/strategies/<id>/reports/` | 运行结果、报告、证据摘要 | 文件 | 是 | 最新结果即可；重要结论归档 | L1-L2（含平台 ID、指标；不含凭据/账户私密数据） |

凭据流：JWT/agent token 仅经环境变量注入进程，不落盘、不入 reports、不入日志；报告与代码中零秘密。不建 version/runs/manifest/快照目录。

## 5. 判定语义（冻结，Developer/Test/Review 共同验收基准）

进化结果六分支（与 intake 验收 4 一一对应）：

1. 跳过（F-003 输出「跳过」）：`parameter-space` 返回 `scope:"none"`，或无 `optimizable:true` 参数，或用户显式不优化，或研究类/成熟策略日常执行 → 不调 run，交付基准并说明原因。
2. 无改进且基准合格：候选全段口径不优于合格基准（同窗口/同成本）→ 保留基准，报告写明比较依据。
3. 基准不合格但候选合格：基准违反硬约束而候选通过 → 可选候选，不因候选绝对收益较低而拒绝。
4. 均不合格：候选与基准全段口径均违反硬约束 → 报告「无合格候选」，不做最终推荐回测。
5. 关键证据未知：全段回测失败、关键指标缺失，或 `executionAssumptions.fundingMode=not_modeled` 等未建模项影响该市场结论 → 判「证据不足」，不判通过；未建模项在报告显式披露。
6. 失败/超预算：run job failed/cancelled、陈旧中断（workerInterrupted）或 F-004 预算耗尽 → 停止，报告 `progress.failure` 诊断（messageKey/dominantReason/reasonCounts）与实际消耗，不自动重试。

通用规则：硬约束先于目标比较；目标比较必须同口径（同窗口、同成本假设、同指标定义）；`summary.recommended=true` 只是平台建议信号，不替代 F-006 判定；推荐仅作用于本轮研究，不写运行配置、不触 Live。

## 6. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | SKILL.md 可加载且含三步流程、进化子流程与安全边界；父 SKILL.md 路由可达 | 读文件 + 路由描述核对 |
| A-002 | 薄脚本与样例目录仅出现在 Design allowlist 内 | path-scoped `git status --untracked-files=all` + `git diff --check` 对照 allowlist |
| A-003 | 交易样例真实闭环：客户端显式private/draft，sourceId的visibility/status/code等按F-001读回一致；基准runId读回、进化job终态+列表交叉核对、最终runId读回 | API 实调 + 精确读回比对（fixture 不得替代） |
| A-004 | 判定输出符合 §5 六分支之一，核对summary.selectionObjective与selection.objective；summary.maxDrawdown仅validation折绝对值平均、不含blind，硬约束用全段data.result.maxDrawdown；最终选参触及留出集如实披露 | 报告内容核对 + 字段/口径/判定逻辑单元断言 |
| A-005 | 研究样例：真实数据、reports 落盘、同脚本二次执行成功 | 实跑两次比对输出 |
| A-006 | 负分支（F-009）断言通过 | 单测/断言脚本运行记录 |
| A-007 | 未授权调用不可达：脚本源码 grep 无下单/deploy/credentials 调用 | grep 审计 |
| A-008 | 凭据零泄露：文档/代码/报告/日志无 token 值 | grep 秘密模式审计 |
| A-009 | 预算与停止：estimate预检生效，folds恒为4，超预算仅减trials/缩空间 ≤2 次后停止；进化仅run一次；内部估计/实际与外层jobs分别符合§8/Design预算，不得增大安全上限 | 日志/报告核对（估计与actual未知不得混写） |

## 7. 测试要求

- 单元测试：判定函数（§5 分支映射）、参数行构造（范围裁剪）、错误信封解析。fixture 仅用于此层。
- 集成（真实）：F-001~F-008 按 A-003/A-005 真实执行；无凭据/平台不可用时明确阻塞披露，不降级为 mock 验收。
- 回归：二次执行研究脚本输出一致（允许时间戳类字段差异）。
- 不可自动化验证项：UI 页面人工实查（sourceId/runId 在原生界面可见）由 Verify 阶段以截图或页面读数留证。

## 8. 实现约束

- 禁止事项：修改 QuantDinger 子模块源码；新建 SDK/MCP/包结构；直写平台 DB；Demo/Live/调度/凭据操作；提交研究/进化/回测任务以外的任何平台写；把 fixture 结果冒充真实验收；无限进化循环。
- 运行环境：Pascal 已确认本地CLI、研究脚本和测试从项目根显式使用 `.venv/bin/python`（本机核验为Python 3.12.13）；不使用Hermes自带解释器、不新建模块venv、不借用QuantDinger后端venv。跨工作目录使用该解释器的项目绝对路径；平台沙箱环境保持平台所有。
- 依赖限制：首版CLI、研究脚本和离线测试仅用Python标准库，不新增三方依赖。Design §2.1的T2缺包记录属于当时的Hermes解释器，不代表项目venv缺包。平台沙箱内策略的DataFrame不要求在本地执行。
- 性能/安全/风控约束：安全上限trials ≤64、全段复检参数组（含基准）≤5、外层持久化 `POST /api/backtest/jobs` ≤8、研究数据API调用 ≤50、墙钟 ≤30分钟；任务可下调，不得上调这些上限。folds固定4（平台下限4，首版上限4），不能降3或升5；任务只允许<4则停止。轮询间隔≥15s；所有写动作读回验证；进程退出码非0即该步骤失败。
- 内部回放与外层持久化job是不同预算：内部上限按Design §3.5显式声明，首版样例backtestRuns/actualBacktestRuns≤8、relativeUnits≤8；外层基准1+去重候选最多4+最终1，最多6且受总上限8。内部analysis_only/persist=false不算外层job。4个grid点、costMultipliers=[1,2]、blindRatio=0.15、universeSize=1时，估算 `4+(2-1)+1=6`、relativeUnits=6，不乘folds（service.py:111-116）；actual未知不得记6。估算并非强上界，实际超预算/未知如实披露并停止补跑，不能承诺取消强杀远端计算。样例墙钟1200s等更低值见Design §5.1。

### 8.1 方案 C 样例执行契约（仅 spy-ma-smoke，2026-10-30）

- 来源为 RFC V1.4 §5.5 的 Pascal 批准：当前唯一窗口 2017-06-01..2025-12-31，旧 2023-01-01..2025-12-31 窗口 superseded，仅保留历史证据；旧基准 run19 不作为新窗口同口径基准。源码/算法不变，不要求再实现已完成的 CLI 兼容修复或修改 Python/测试。
- 不变值：warmup260、folds4、capital10000 USD、commission/slippage各0.0005、无杠杆、ma_period基准50/搜索20..80 step20、target_pct固定0.95、grid4 trials、trainRatio0.7、blindRatio0.15、embargo1；其余样例设置及硬约束继承 Design §5.1 与样例 spec，不放宽。
- 本次一次性额外额度仅为新窗口最多新建1个原生进化 job。旧 job `d249d4846e8e493b8d0d316b340f99de` failed（observationRangeTooShort）计入历史，原样保留且不重试；新窗口 job 单独列示，未执行不编造ID。主控开始前须只读核查该窗口已有 job；存在则只读回、禁止重复创建，提交结果未知也不得自动重发。通用每次执行恰好一次进化/失败即停规则不变，不变成普遍2次额度。
- 新一轮内部 backtestRuns/actualBacktestRuns≤8、relativeUnits≤8、外层持久化回测jobs≤8（预计最多6）、参数组含基准≤5、总墙钟1200s、单回测180s/进化600s、轮询15s、零新增付费；失败/取消/超预算立即停，不自动重试。历史与本轮分别记录，actualBacktestRuns缺失或None写“未报告”，不写0。
- 范围兼容而非放宽平台规则：区间含首尾3136自然日；USStock/1D原生maxDays3650，warmup按原生函数预留，当前客户端maxSelectedDays3158。实际提交仍须核对compile返回策略，不修改上限或日期解析语义。
- 复用真实预检 `data/reports/2026-10-29-strategy-lab-verify/evidence/2026-10-30-c-window-preflight.json`：日末2159条、午夜2158条，原生build_walk_forward_plan均effectiveFolds=4，详见Design §5.1。变更窗口须用真实观测及原生拆分核验有效四折，自然日或estimate.folds不作通过证据；公开取数不保证evaluator快照相同，真实任务仍须核对有效四折、覆盖、成本与终态。
- 仅更新指定六个Markdown，沿用T4 `t_baaaef0b`/T5 `t_6346409a`，独立方案C Design Gate完成前主控不执行业务。此次文档同步未真实重跑，不改历史reports/命令原文，不代表A-003或T4/T5通过。

## 9. 运行前提与开放问题

- Design §3.3已固定进程入口 `QUANTDINGER_BASE_URL` / `QUANTDINGER_JWT`，不声称profile已配置；仅由主控经现有安全机制注入，不读/改.env、不登录、不收集浏览器token、不请求新token。认证可用性与免费开关仍未验收，是后续真实运行前提，不是交给Developer裁决的业务语义。
- 复用主控2026-10-29 20:29:25 CST（Asia/Shanghai UTC+08:00）探测：127.0.0.1:15000/api/health HTTP200 healthy role=api；public-config与strategy-evolution/jobs均HTTP401/code401/Token missing；127.0.0.1:15080/ HTTP200。仅证明可达及未认证响应，不等于免费开关、真实业务或UI已验收；早先5000/8888历史及追加纠正在Design §2.1，不追认旧origin推断。

## 版本记录

| 版本 | 日期 | 更新内容 |
|---|---|---|
| V1.0 | 2026-10-29 | 初始功能、判定语义与验收契约 |
| V1.1 | 2026-10-29 | 与RFC/Design同步五项closure：纠正Human默认私有性、wire字段、validation回撤与blind独立、固定folds和双计数预算；追加正确端口探测/JWT前置；纠正依赖与凭据核实表述，不改变业务目标 |
| V1.2 | 2026-10-30 | 按 Pascal 明确裁定将策略/研究实例移到 skills/strategies/<strategy-id>/；同步当前路径清单与本地守卫，不改业务、预算或冻结安全边界 |
| V1.3 | 2026-10-30 | Pascal纠正最终实例根为 skills/strategies/strategy-lab/strategies/<strategy-id>/；取代V1.2直属目录方案，仅同步路径、守卫与导入，不改业务/预算/安全门禁 |
| V1.4 | 2026-10-30 | 同步方案 C 窗口、真实2159/2158条四折预检和新窗口最多1个job的一次性额度；历史保留、每轮预算及通用停止规则不变，未真实重跑 |

## V1.3 最终目录裁定（2026-10-30，取代 V1.2 目录方案）

当前唯一有效实例位置为 `skills/strategies/strategy-lab/strategies/<strategy-id>/`。两个验证样例分别是 `skills/strategies/strategy-lab/strategies/spy-close-research/` 与 `skills/strategies/strategy-lab/strategies/spy-ma-smoke/`；二者不是用户网格策略、不代表可上线。strategy-lab 根层保留 SKILL、README、scripts、templates、tests，并由 strategies 子目录集中容纳具体实例。不得在 strategy-lab 根层或 skills/strategies 直属层留下这两个实例的副本或兼容 symlink。

V1.2 的直属目录位置已被本节替代，其版本记录保留作历史，不作为当前执行指令。此前已搬文件直接从现场继续收口，不能重建或覆盖已有 reports；历史报告命令/结论与数据逐字保留。CLI 路径守卫仅接受上述实例根的直接子目录，拒绝根外、更深嵌套和 symlink 逃逸。V1.3 当时只调整目录、必要路径/导入与命令，不改策略、算法、API、预算、认证或交易逻辑；目录裁定仍有效，当前 RFC/SPEC/Design 契约版本统一 V1.4，样例窗口及一次性额度以 §8.1 为准。

用户要求继续 T4 的请求保留；目录迁移只做离线验证，不等于解除既有安全暂停或真实业务通过。T4 的凭据传递与诊断拒绝须先按已批准边界纠正，禁止恢复已删除的明文 JWT 文件、禁止重跑被拒辅助诊断；不新增实盘/部署授权。
