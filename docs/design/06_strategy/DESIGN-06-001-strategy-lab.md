# DESIGN-06-001: Strategy Lab — QuantDinger 薄调用与最小真实验收

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft（V1.4 方案 C 待独立 Design Gate；不代表 T4/T5 通过） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 / 最后更新 | 2026-10-29 / 2026-10-30 |
| 版本 | V1.4（方案 C：仅延长 spy-ma-smoke 窗口；非整体验收） |
| 来源 RFC | [RFC-06-001 V1.4](../../rfc/06_strategy/RFC-06-001-strategy-lab.md) |
| 来源 SPEC | [SPEC-06-001 V1.4](../../spec/06_strategy/SPEC-06-001-strategy-lab.md) |
| 目标模块 | skills/strategies/strategy-lab/ |
| 设计任务 | t_f1988e16；上游 t_5fcb98dd；docs-only纠正 t_0f6f7508 |
| 主仓基线 | e378bef8d1d89565ccb15b0f5320f5008f9b657e |
| 源码核验时间 | 2026-10-29，Asia/Shanghai（UTC+08:00） |

## 1. 设计摘要

实现一个操作型 SKILL、一个单文件 QuantDinger 调用 CLI、一个原生模板交易样例、一个可重跑研究样例、一个离线分支测试文件。业务仍只有「定义 → 执行 → 交付」；CLI 只串起本次需要的 HTTP 调用和判定，不提供插件、任务注册、后台 worker、数据库、SDK/MCP 或第二套回测/优化器。

本设计细化 SPEC F-001~F-009，不修改 RFC/SPEC 语义：首版交易闭环固定使用 Human JWT（含源码 compile/create/detail）；Agent 仅作为研究行情的显式可选入口。RFC §5.3 允许 Human 源码备用入口，SPEC F-001 已明确 Human 闭环，因此不构成双入口冲突。无 JWT 不能声称完成自动原生进化；Agent-only 回测不替代本次验收。

预算分开记录：进化内部 `estimate.backtestRuns` / `result.summary.actualBacktestRuns`（失败时 `progress.failure.actualBacktestRuns`），以及外层 `POST /api/backtest/jobs` 次数（总数不超过8）。folds固定4，满足平台下限4与SPEC上限4；不能降3或升5。任务可降低其他安全上限但不得提高；不能用folds=3假装成功收缩。真实API、真实UI与离线fixture的证据分栏，未知不能通过。

T2初版只新增本Design；V1.1 docs-only纠正仅同步指定RFC/SPEC/Design五项事实，没有写实现、测试或stub，也未提交研究、进化或回测任务。下面文件及命令仍为后续Implement/Verify的交付契约，不是现存能力声明；不以修订追认旧错误表述。

## 2. 现状分析与事实来源

路径缩写：`QD=skills/trading/auto-trading/quantdinger/QuantDinger/`，`APP=QD/backend_api_python/app/`，`VUE=skills/trading/auto-trading/quantdinger/QuantDinger-Vue/`。Vue 是 QD 的兄弟子模块，不在 QD 内。两者均只读。

| 能力 | 当前源码证据（行号为本次核验基线） | 设计含义 |
|---|---|---|
| 路由挂载 | APP/openapi/register.py:87-105 | Human 源码前缀 /api/strategies；回测 /api/backtest；进化 /api/strategy-evolution；行情 /api/indicator/kline |
| JWT | APP/utils/auth.py:55-83、89-167、232-254；VUE/src/utils/request.js:22-34、268-270 | 正常登录签发的 7 天会话，服务端核对 token_version/active user；Bearer 注入；不能自签或拿 Agent Token 代用 |
| 编译与私有源码 | APP/routes/script_source_routes.py:130-156、180-217；APP/services/script_source.py:247-301 | compile 返回 manifest/backtestRangePolicy；create 返回完整 item，detail 用 id；Human 服务的 private/draft 是默认值，不是拒绝其他值的强制覆盖 |
| 回测与读回 | APP/routes/backtest_center.py:61-110、225-277、441-475；APP/services/backtest_jobs.py:58-80 | sourceId 关联；job 202；job.result.runId；get 返回 run 行而不是直接指标对象 |
| 进化 API | APP/routes/strategy_evolution.py:29-129、142-173 | parameter-space、estimate、run、jobs、cancel；GET 列表为 data.items；列表不带 result，须读单 job |
| 进化参数/预算 | APP/services/strategy_evolution/service.py:99-133、140-182；models.py:75-117 | estimate 会正规化配置，isUpperBound=false；参数只能在声明内，folds 被夹到 4-10，tpe trials 下限24 |
| 进化实际排序 | APP/services/strategy_evolution/engine.py:154-164、219-270、302-330 | trial.score=components.oosReturn，按 score 降序；qualityScore 是诊断，不是实际排序；真实字段为 summary.selectionObjective、selection.objective |
| 统计与复用 | APP/services/strategy_evolution/statistics.py:27-60；evaluator.py:121-181 | summary.maxDrawdown 为 OOS validation 折 drawdown 绝对值的平均；blind 是独立证据，不并入该字段；evaluate_plan 单次回放后切片，非逐折重训 |
| 全段 MDD | APP/services/strategy_v2/runtime.py:1962-1987、2054-2067 | maxDrawdown 是从起始净值开始跟踪峰值的负百分数；峰、谷及时间单列 |
| 真实回测来源 | APP/services/strategy_v2/service.py:371-434；storage.py:165-186、325-349 | data.result 内的指标/provenance/assumptions；data.source_id/params 校验关联；压缩曲线不可重算冒充原生 MDD |
| 行情 | APP/routes/agent_v1/markets.py:76-125、_helpers.py:9-34；APP/routes/kline.py:63-160 | Agent code=0 成功、data.klines、limit≤2000；Human code=1、data 数组、limit≤1000，当前路由无 login_required |
| 原生模板 | QD/backend_api_python/migrations/strategy_v2_templates.sql:22-54；APP/routes/script_source_routes.py:108-116 | strategy_v2_single_ma，SPY 单均线；ma_period/target_pct 均在 handle_data 真正消费；只读 seed，不运行 SQL |
| 付费边界 | APP/routes/settings.py:2087-2099；APP/utils/agent_jobs.py:120-122 | GET /api/settings/public-config 有login_required，先具备可用Human JWT再读取billing_enabled；不是匿名接口；回测可能扣积分，不能仅以402当零费用保护 |
| 取消限制 | APP/utils/agent_jobs.py:577-584 | cancel 标记 durable job；线程/Celery 不保证被强杀，不能承诺远端计算严格在墙钟到点停止 |
| 原生 UI | VUE/src/config/router.config.js:38-49；src/api/strategy.js:30-50；src/views/backtest-center/index.vue:4-24、376、1081 起；StrategyEvolution.vue | 策略 IDE /strategy-ide、回测中心 /backtest-center，进化是中心内 tab，不捏造独立 evolution URL |

源码基线：QD HEAD `4111d4550c9354a278d3926a786c4b2586a673aa`；VUE HEAD `e1d47c9edfb94a48185a5123724dff2e4ce55462`。源码存在不代表部署版本可用。

### 2.1 本阶段最小运行前提核验（非真实接入验收）

- T2核验记录：`python3 -m pip show requests pandas` 返回两者均未找到；这是当时Hermes解释器的历史记录，不代表项目venv缺包。调用CLI、研究脚本和离线测试仍只用标准库（urllib/json/csv/statistics/unittest等）；交易源码中的pandas风格DataFrame属于QuantDinger沙箱，不要求在YQuant本机import/运行策略。
- Pascal 后续确认的本地执行细节：从项目根显式使用 `.venv/bin/python`（本机Python 3.12.13），跨目录使用 `/home/pascal/workspace/yquant-investment/.venv/bin/python`；不得依赖PATH/activate、不新建模块venv、不借用平台后端venv。仅统一本地调用环境，不改变业务/API/验收与交易授权；已有历史验证命令按其真实解释器保留，不追认为项目venv结果。
- 只检查当前进程环境变量是否非空，未读取任何 .env：QUANTDINGER_BASE_URL、QUANTDINGER_AGENT_TOKEN、QUANTDINGER_JWT、QUANTDINGER_TOKEN 均 absent。不能由此推断其他 profile/vault 一定没有凭据，也不能声称已有可用 JWT。
- 只读 HTTP：127.0.0.1:5000/api/health 连接拒绝（curl exit 7）；127.0.0.1:8888/ 与 /api/health HTTP 200，health 为 status=ok；8888 的 /api/strategies/script-sources 与 /api/strategy-evolution/jobs 返回 API endpoint not_found。没有认证请求，没有浏览器登录，没有提交任务。
- 上一条是T2的5000/8888探测历史，保留但不作为正确部署origin结论；8888仅证明存在Web/health，404不等于全平台缺能力。
- V1.1追加主控实测纠正（来源：data/tasks/active/2026-10-29-strategy-lab/design-gate.md:15，本轮复用而非新发网络任务）：2026-10-29 20:29:25 CST（Asia/Shanghai UTC+08:00），http://127.0.0.1:15000/api/health HTTP200 healthy、role=api；该origin的 `/api/settings/public-config` 与 `/api/strategy-evolution/jobs` 均HTTP401、code401、Token missing；http://127.0.0.1:15080/ HTTP200。15000 API/15080 Web可达，缺认证不等于缺路由能力；health/Web200不证明真实业务成功。
- 因此不再保留“正确API origin尚未确认”的旧结论；上述origin是主控探测的可达目标，实际调用仍取主控确认的QUANTDINGER_BASE_URL并核对部署契约。public-config有login_required，调用方须先具备可用Human JWT再读；当前JWT认证可用性、billing_enabled免费开关和UI业务页面仍未验收。不得为本卡读/改.env、收集浏览器token、登录、签新token、重启、部署、升级或建立账号。
- 此为后续真实执行的已披露前提缺口，不是源码设计不可完成的契约矛盾；Implement 可完成离线产物，但 A-003/A-005/UI 未真实完成不得验收 PASS。

## 3. 方案设计

### 3.1 精确文件 allowlist

下表路径均相对主仓；`L=skills/strategies/strategy-lab/`（工具）与 `S=skills/strategies/strategy-lab/strategies/`（策略实例）只作表格缩写，不是可变工作区。除下表与现有两输入外，不添加文件/包/配置。无 `__init__.py`、依赖清单改动或 profile 副本。

| 精确路径 | 动作 / 职责 |
|---|---|
| skills/strategies/strategy-lab/SKILL.md | 新建；三步业务、原生能力路由、自动进化/停止、复现命令、安全边界 |
| skills/strategies/strategy-lab/scripts/quantdinger.py | 新建；一个单文件 CLI，trade/fetch-klines 两个受限命令；HTTP、轮询、判定和摘要输出，不建通用任务引擎 |
| skills/strategies/strategy-lab/tests/test_quantdinger.py | 新建；unittest 离线断言，网络/时钟替身仅在测试里 |
| skills/strategies/strategy-lab/strategies/spy-ma-smoke/README.md | 新建；用途、命令、平台 ID/UI 查询方式，不承诺盈利 |
| skills/strategies/strategy-lab/strategies/spy-ma-smoke/spec.md | 新建；按现有模板实例化 §5.1 的交易接入需求与预算 |
| skills/strategies/strategy-lab/strategies/spy-ma-smoke/config.json | 新建；仅 ma_period、target_pct 实际数值；不存凭据/平台 ID/搜索语义 |
| skills/strategies/strategy-lab/strategies/spy-ma-smoke/strategy.py | 新建；复用官方 strategy_v2_single_ma 原生 V2 源码，不作为本地 CLI 执行 |
| skills/strategies/strategy-lab/strategies/spy-ma-smoke/reports/report.md | 生成；基准/候选/结论、来源、参数、限制、预算、复现命令 |
| skills/strategies/strategy-lab/strategies/spy-ma-smoke/reports/comparison.csv | 生成；全段回测比较表，含每行 runId/参数/合格状态/原因 |
| skills/strategies/strategy-lab/strategies/spy-ma-smoke/reports/ui-check.md | Verify 写入；页面读数或未完成原因，非 API 读回的别名 |
| skills/strategies/strategy-lab/strategies/spy-ma-smoke/reports/source-ui.png | 可选 Verify 截图；只截源码区/名称，避开账户/凭据 |
| skills/strategies/strategy-lab/strategies/spy-ma-smoke/reports/backtest-ui.png | 可选 Verify 截图；最终 run 与指标可读 |
| skills/strategies/strategy-lab/strategies/spy-close-research/README.md | 新建；研究问题、真实取数与二次执行命令 |
| skills/strategies/strategy-lab/strategies/spy-close-research/spec.md | 新建；§5.2 的固定窗口/方法/预算 |
| skills/strategies/strategy-lab/strategies/spy-close-research/research.py | 新建；固定问题研究，无交易、不调用进化 |
| skills/strategies/strategy-lab/strategies/spy-close-research/reports/latest.csv | 生成；标准化真实窗口 OHLCV，供二次执行核对，不建通用快照系统 |
| skills/strategies/strategy-lab/strategies/spy-close-research/reports/report.md | 生成；统计、来源、时间、限制、复现命令及重跑说明 |
| skills/strategies/strategy-lab/strategies/spy-close-research/reports/replay-check.md | Verify 写入；两次命令/exit code/样本量/指标及 CSV 一致性 |
| skills/strategies/SKILL.md | 最小编辑：在“状态”附近插入一个 strategy-lab 路由条目，链接子 SKILL，注明研究/回测与交易运行边界；不改 legacy/trading 规则 |

已有 L/README.md、L/templates/strategy-spec.md 保留不改；父 skills/strategies/README.md 不需要修改，不在实现 allowlist。首版不改变配置字段语义、不整理整个 Trading 模块。临时 pycache 不作为交付物，测试使用 PYTHONDONTWRITEBYTECODE=1。

本 Design 不授予后续任务修改本表外文件的权限；验证阶段工程报告仍按 AGENTS 放 data/reports/<日期>-strategy-lab-verify/report.md，由主控在 Verify 卡独立授权，不作为产品实现文件扩张。业务结果 reports 的局部约定来自 intake §目标与范围，覆盖一般 data 报告目录。

### 3.2 最小调用入口与函数边界

`quantdinger.py trade` 是一次前台、顺序执行的研究命令，直接完成 F-001~F-007，不要求 AI 每次手工点击进化。参数与原生 job ID 仅保留在内存/本轮摘要；没有 resume 队列、守护进程或通用状态机。命令不接收任意 URL path/method、Python eval 或插件。

实现内部采用普通函数（名称冻结）：

- `request_json`：stdlib urllib，固定 operation→method/path 白名单，按 Human/Agent 分别解析信封；HTTP timeout 为 min(30s, 本步剩余秒数)，禁止跨 origin 重定向携带认证。
- `poll_job`：只轮询本命令取得的 jobId；间隔15s；截止时间用 monotonic；回调只接收脱敏的 phase/status/count。
- `save_source`：compile → create → detail；可用 `--source-id` 明确复用已读回且源码/owner 一致的私有 source，不自动覆盖别人的资产。
- `run_backtest`：提交一次 persist=true job → 终态 → runId 读回 → history 关联核对。
- `evolve_once`：适用性检查 → 数值空间限定 → estimate → 唯一一次 run → 终态与列表核对；没有内置搜索算法。
- `select_candidate`：只对已有全段指标作三值硬约束检查/同口径排序；不复算回测或平台统计。
- `fetch_klines`：F-008 的受限分页取数，仅返回行情；与 trade 共用 HTTP 信封处理，不是数据 Provider 接口。
- `write_report`：只序列化明确字段，成功与失败均写本策略报告，不 dump HTTP body、headers、环境或账户。

`research.py` 用 importlib.util 按相对文件路径载入该单文件的 `fetch_klines`，同样方式供 unittest 加载；不要为 import 新建包。导入不得触发 I/O，入口有 main guard。标准库依赖，无 requests/pandas 安装或升级。

CLI 输入（均写进各业务 spec 的实际命令，不从自然语言 Markdown 自动解析）：

| 命令 / 参数 | 对应契约 |
|---|---|
| trade --strategy-dir <dir> [--source-id <id>] | dir 内必有 spec.md/config.json/strategy.py；path resolve 后必须在 S 的单层策略目录，拒绝 ../、符号链接逃逸及覆盖其他目录 |
| --start YYYY-MM-DD --end YYYY-MM-DD --capital <number> --commission <ratio> --slippage <ratio> | 日期严格、start≤end，资金>0；费用为小数比例，显式传原生 API，不能把0.0005当0.05个百分数再除100 |
| --search <name:min:max:step>（可重复） | 仅声明内、optimizable、源码确实消费的数值参数；不声明搜索的数值项固定为 config 值，作为 min=max 行传入；其他固定类型必须与源码默认相同，否则停止报告不支持 |
| --objective totalReturn --max-drawdown-pct <positive percent> | 首版仅提供同窗口全段 totalReturn 降序；硬约束的 MDD 用 -maxDrawdown≤阈值；不自动换目标，不增加复合打分器 |
| --skip-evolution | 仅用户固定参数/成熟日常执行等明确意图；报告跳过理由；新研发默认不跳过 |
| --method grid\|random\|tpe --trials <int> --folds 4 --max-evolution-runs <int> --max-relative-units <int> --wall-seconds <int> | 本轮预算，逐项校验 SPEC 上限，平台会夹值的输入也要先拒绝而非依赖静默夹值；外层 job 上限8、全段复检含基准≤5固定 |
| fetch-klines --data-api human\|agent --market USStock --symbol SPY --timeframe 1D --start ... --end ... | 输出标准化时间升序行情；Human/Agent 显式选择，不在401之后自动切入口；研究脚本调用同一函数 |

样例固定 blindRatio=0.15、trainRatio=0.7、seed=42、costMultipliers=[1,2]、autoPrune=false、monteCarloPaths=100、topCandidates=4；写在样例调用常量及 spec 的语义说明，不另建 task.json。通用 CLI 不添加自动策略生成/自动改源码功能。更复杂市场/目标超出薄入口时如实说明能力边界，由后续具体需求另行派发，不在首版实现框架。

### 3.3 Auth、真实 API 与参数映射

认证传入契约：`QUANTDINGER_BASE_URL` 为已确认的 origin（不带 /api，禁止 userinfo/query 中塞凭据）；`QUANTDINGER_JWT` 为本 CLI 约定的 Human 会话环境入口；`QUANTDINGER_AGENT_TOKEN` 复用官方已有命名，仅用于显式 Agent 行情模式。JWT 变量名是本 Design 定义的进程接口，不是声称 profile .env 已有该键。不要新增/编辑任何 .env、profile/config 或凭据文件。

由主控通过现有安全机制把正常会话注入 worker/进程；本 Skill 不登录、不签 JWT、不读 SECRET_KEY、不解码或收集浏览器存储、不从会话日志捞 token。缺失时无网络写并返回 auth-missing；有变量也须由受保护只读端点成功确认可用性。401/403 一次即停止，不重登/刷新/换 token 绕过。UI 登录遇认证墙，只能沿用现有 vault/操作者流程，headless 无可用凭据则报告阻塞，不索取聊天明文。

首版所有交易 HTTP 用同一个 Human origin/JWT，不混 Agent 用户。source detail.user_id 必须与后续 get run.user_id 一致；平台 GET 已按会话 owner 过滤。报告只存 sourceId/runId/jobId，不保存 user_id 原值。只有将来明确选择 Agent 源码入口时才需两侧 owner 精确验证，本次不实现该分支。

| 顺序 | operation / 真实 method 与 path | 请求关键字段 | 读取与检查 |
|---|---|---|---|
| 0 | GET /api/settings/public-config（先具备可用Human JWT，Authorization随请求发送） | 无业务body；不是匿名接口 | Human code=1，data.billing_enabled必须明确false；401/403、true/缺失则停止，不提交任务/不调用billing路由/不充值；404同样停止 |
| 1 | GET /api/strategies/script-templates | 无 | data.items 中 template_key/key=strategy_v2_single_ma；实现时校对当前模板身份与声明，不运行迁移 SQL |
| 2 | POST /api/strategies/script-sources/compile | code | data.manifest 与 backtestRangePolicy；核对市场/周期/方向/范围；超范围停止，不擅改研究窗口 |
| 3 | POST /api/strategies/script-sources/create | name,code,description,template_key,asset_type=script,visibility=private,status=draft；仅必要 metadata | data.id 作为 sourceId；不传 user_id/strategyId；不使用 publish/update/create-deployment |
| 4 | GET /api/strategies/script-sources/detail?id=<sourceId> | id | name/code/asset_type/visibility/status 与本次输入一致；metadata.strategy_manifest 与 compile 共同字段一致，允许平台增加 canonical 字段；param_schema 声明存在；失败只重读≤1次，不重建 |
| 5 | POST /api/backtest/jobs | sourceId,startDate,endDate,initialCapital,commission,slippage,leverageEnabled=false,leverage=1,params=config,persist=true | 202 data.jobId；不传 code 覆盖 source、不建 strategy/deployment；GET /api/backtest/jobs/<jobId> 至终态 |
| 6 | GET /api/backtest/get?runId=<job.result.runId>；GET /api/backtest/history?sourceId=<sourceId> | ID | data.id/source_id/params/start_date/end_date/成本/owner；指标在 data.result；history 中有该 runId；params 不从源码默认值猜测 |
| 7 | GET /api/strategy-evolution/parameter-space?sourceId=<sourceId> | sourceId | data.scope/parameters；数值声明与 config 接线一致；skip 分支不调用 estimate/run |
| 8 | POST /api/strategy-evolution/estimate | parameterSpace,config,universeSize=1 | data.backtestRuns/relativeUnits/resourceTier/trials/requestedTrials/folds/sampleSufficient/isUpperBound；与本地预算对比，不能认为无 sourceId 的 estimate 已验证源码/日期 |
| 9 | POST /api/strategy-evolution/run | sourceId,startDate,endDate,initialCapital,commission,slippage,leverageEnabled=false,leverage=1,parameterSpace,config | 202 data.jobId；GET /api/strategy-evolution/jobs/<jobId> 终态；成功 result.source.id 与 sourceId 一致；GET /api/strategy-evolution/jobs?sourceId=... 的 data.items 包含 jobId |
| 10 | 对选定候选重复步骤5-6 | params 为固定 config 合并 trial.params | 同窗口、同成本、同 source 的全段指标，不能只用 evolution result.equityCurve（可能只是 blind） |
| 11 | 推荐项重复步骤5-6 | params 为最终推荐的全部参数 | 单独最终 persist run；读回+history 后写报告；复用同一个参数化 private source，不自动覆盖 config.json/Live |
| 超时 | POST /api/backtest/jobs/<jobId>/cancel 或 /api/strategy-evolution/jobs/<jobId>/cancel，再 GET 精确job | 仅本轮仍活动的已知jobId | 记录实际终态或 cancel-unconfirmed；不能把“请求已发”称为远端已停算 |

Human 正常成功 code=1；认证失败可能 code=401（不是0），始终先检查 HTTP 状态。Agent 正常成功 code=0/message/data，不能用 Human 解析器；Agent 错误含 details/retriable，不因此自动重试。run job 的 succeeded 才读取 result；queued/running 非终态；failed/cancelled/未知状态不判通过。

RFC §5.1/§5.3、SPEC F-001/§4已同步事实：Human service接受payload visibility/status，private/draft仅为默认；客户端显式发送并精确读回，私有业务要求不变。三文档统一真实wire字段 `summary.selectionObjective="oosCompoundedReturn"` / `selection.objective="oosCompoundedReturn"`；若部署结构不符则停止披露，不造字段，不以Design覆盖错误SPEC。

### 3.4 控制流、统计口径与六分支

前台一次 trade：输入/认证/免费能力 → compile/save/readback → 基准回测/readback → 检查优化意图与真实参数 → parameter-space → estimate（最多初始+2次收缩）→ run一次 → jobs终态/列表 → 候选证据检查 → 有界全段复检 → 判定 → 如有推荐则最终原生回测/readback → reports。任何技术失败先写已有事实与停止原因，不自动改策略或重启流程。

适用性要求参数声明与消费证据同时存在：样例定位 `context.params.get` 的实际使用，全部默认值与 config 核对；仅有 schema 不算消费。对 runtimeConstant 适配型机器人，本版不自行重写常量接线或宣称兼容，交给现有原生能力/后续具体需求。

候选集合：保留合格基准作为单独一行，进化 topCandidates 按原生次序取最多4个、以完整参数值去重；baseline 参数重复时复用已读回基准，不多提交回测。总共参与全段证据的参数组≤5。所有候选先检查 finite/活动度等适用证据；全段 MDD 硬约束在原生全段结果上检查，不能用平均分窗 MDD 阈值先淘汰、再声称已完成全段核对。任何明确的用户分窗约束独立检查，不能混成全段约束。

平台排序是OOS复合收益（各validation折收益复利），quality/robustness分数不替代用户目标；summary.recommended不是强制通过闸门。`summary.maxDrawdown`仅为validation/OOS折回撤绝对值均值（无validation时源码兜底100），不含blind、不是全段MDD；`summary.blindReturn/blindPassed`单独引用，整份报告可以同时列出两类证据但不可混字段。RFC §5.3、SPEC §4已同步这一口径，不再替旧混合表述作正确性解释。fold复用是单次回放切片，不是逐折拟合；selection.blindUsedForSelection=false仅指原生搜索，后续全段复检包含blind后，报告不得再称本轮最终推荐有完全未触碰的独立留出集。

`select_candidate` 不读取“缺失即0”的指标。逐项得到 PASS/FAIL/UNKNOWN；任何影响结论的 UNKNOWN 优先形成 insufficient-evidence，而不是忽略该候选后宣称其余“均不合格”。全段收益/费用/期间不一致也属 UNKNOWN。全段 maxDrawdown 为非正百分数，先验有限且≤0，再用其相反数与正阈值比较；峰值净值口径≠相对初始本金亏损。合约资金费/强平/gross exposure 关键数据未建模或未知，不得判合格；现货/无融资股票须明确说明这些项不适用，不能无条件把 fundingMode=not_modeled 隐藏掉。

| SPEC §5 分支 | 确定行为与输出 |
|---|---|
| 1 跳过 | scope=none、无optimizable、用户固定参数/禁止优化、研究/成熟日常执行：不调run；报告 skipped+原因。基准仍需核对硬约束，不能跳过即合格 |
| 2 无改进且基准合格 | 合格候选 totalReturn 不高于合格基准（浮点比较容差1e-8个百分点）：baseline-kept，最终以基准参数保存回测 |
| 正常改进 | 合格候选中按全段 totalReturn 降序，平手保留基准；候选间平手保留原生顺序；选candidate并写全参数，不用原生名次替代硬约束 |
| 3 基准不合格/候选合格 | 只在合格候选中选目标最大者，即使绝对收益比不合格基准低；baseline 不参与目标排名 |
| 4 均不合格 | 全部证据已知且全部 FAIL：no-qualified-candidate；不提交最终推荐回测，保留基准/候选证据 |
| 5 证据不足 | 回测失败、指标/身份/成本缺失、相关未建模：insufficient-evidence；不作通过或最终推荐 |
| 6 失败/超预算 | failed/cancelled/workerInterrupted/估算无法收缩等：停止，记录error和progress.failure.messageKey/dominantReason/reasonCounts/actualBacktestRuns，缺字段标未知，run不重试 |

有效的 no-qualified-candidate 是业务结论，不强求样例盈利。首次真实接入验收仍必须得到成功的 evolution 终态、真实判定与最终持久化回测；若实际结果无法形成最终推荐，按事实记录“业务无候选、最终闭环验收未完成”，不能偷偷改窗口/费用/硬约束让验收通过。

### 3.5 预算、错误和有界停止

预算为进程内计数/截止时间，不建持久化预算账本。每次写前计数与检查剩余时间，失败提交也占本地尝试预算，不把失败当免费重试。

| 量 | 默认上限 / 样例值 | 处理 |
|---|---|---|
| 搜索 trials | SPEC≤64；样例4（grid） | tpe不得小于24；grid参数点4已穷举，sampleSufficient按估算真实值，不虚增试验 |
| folds | 固定4 | 平台最低4，首版安全最高4；不能降3或升5；只能缩trials/空间；用户预算folds<4则不run |
| 进化内部回放 | 显式 --max-evolution-runs；样例上限8 | estimate.backtestRuns与成功result.summary.actualBacktestRuns/失败progress.failure.actualBacktestRuns分别记录；样例估算6，不是已知实耗；不乘folds，不与外层8混用 |
| 相对计算量 | 显式 --max-relative-units；样例8 | universeSize=1；estimate并非强上界，实际未知/超预算都如实披露，不再补跑 |
| 外层持久化回测 | ≤8；样例最多6 | 基准1 + 去重候选最多4 + 最终1；内部analysis_only/persist=false回放不算外层job |
| 全段复检参数组 | ≤5 | 基准 + 最多4候选；复用相同基准参数；预算不足截断前声明检查范围，不能称所有搜索点均已全段验证 |
| 研究数据请求 | SPEC≤50；样例每次≤4，两次合计≤8 | 独立于job轮询次数，分页必须游标前进，空/重复页有界停止 |
| 轮询 | 每15s一次 | trade总墙钟样例1200s，默认不得超过1800s；单回测job≤180s，进化job≤600s，均受总剩余时间约束；总预算预留最后30s作取消/精确读回和报告，不在截止后再开等待循环 |
| 估算收缩 | 初始后≤2次 | 第一次减trials（不低于方法最小值），第二次缩已声明数值空间；folds保持4；仍超即停止；不换目标、成本或放宽MDD |
| 实际花费 | 本样例0新增人民币/美元支出、0付费积分 | billing_enabled true/未知即在提交前停止；不配置充值、不调用billing API、不切到其他入口规避计费 |

样例内部估算按当前 singlePass：4 个trial +（2个costMultipliers减1个blind基准缓存）+1个blind=6；不是4×4×2。终态若actual缺失不能报实际为6。客户端无服务端强杀能力，墙钟保证的是停止新提交/停止本地等待并请求取消；cancelled 不保证远端线程停止，报告必须披露。需严格服务端CPU硬预算的后续任务不在本版承诺内，不为此修改子模块。

统一错误：CLI参数/本地路径失败→exit64；平台/契约失败→exit2；证据不足→exit3；认证缺失/401/403→exit4；预算/超时→exit5；正常业务结果（含skip/no-qualified）→exit0。报告保存 classification 与原始业务错误键的安全摘要，不能只用退出码替代结论。POST create/jobs/run 超时可能已经生效：记录 outcome-unknown，不自动重发；只有已知 ID 允许精确读回，人工对照后续处理。GET读回不一致仅按F-001允许重读一次；其他HTTP错误不自动无限重试。最终回测失败保留基准runId与原推荐“未完成确认”，不宣称已完成交付。

### 3.6 持久化、最小隐私与回滚

| 存储对象 | 写触发（文件:函数） | 字段子集 / 来源 | 写前校验与失败 |
|---|---|---|---|
| 平台私有源码 | scripts/quantdinger.py:save_source | 本地name/code/template_key；显式private/draft；平台补canonical metadata | compile通过；detail源码/声明/身份核对；失败不自动删除/重建；保留可识别sourceId，无直写表 |
| 平台回测历史 | scripts/quantdinger.py:run_backtest | sourceId/窗口/资本/费用/params/persist=true来自spec对应CLI/config | get精确run + history；source/owner/params/assumptions匹配；失败不回填伪造指标、不删历史 |
| 平台进化job | scripts/quantdinger.py:evolve_once | sourceId/日期/成本/限定parameterSpace/config | estimate通过再一次run；读单job终态和source过滤列表；失败保留诊断，超时只取消本轮ID |
| spy-ma-smoke/reports/{report.md,comparison.csv} | scripts/quantdinger.py:write_report | 本轮ID、指标、参数、数据来源、限制、预算、阶段状态 | 明确字段构造；不保存账户/headers/原响应；失败保留已有证据，不覆盖既有重要研究结果 |
| spy-close-research/reports/{latest.csv,report.md} | spy-close-research/research.py:main | 真实OHLCV/时间、统计、请求范围、来源/取数时间 | 数据身份/有限值/顺序/唯一性通过；空数据或缺口不能写成成功；写失败非0，不清理上次有效结果 |
| UI / replay证据 | 独立Verifier页面实查/二次执行 | 页面名称、sourceId/runId/jobId、指标读数、时间和命令 | 截图避开账户和凭据，API已查与UI已查分别标记；不包含登录页面/浏览器存储 |

隐私落实到 write_report：只接收经过挑选的业务字段，不接受request/response对象；异常摘要过滤Bearer/JWT样式与token/password/secret字段，不输出原始异常URL/headers；禁用HTTP debug。不打印环境变量值，不落dotenv/登录信息。本地仅最新结果，没有TTL/迁移/schema；重要既有结果不可无提示覆盖，样例正常二次研究更新latest不建version/runs/manifest。原生平台自己生成的source version/数据快照不复制、不关闭，这不违反本地不建快照目录。

回滚为移除本次新增CLI/Skill/样例与父路由的最小diff（由主控另行决定，不在本卡执行）；保留原生平台事实，不自动删源/删job/删run；无DB回滚、无服务重启。仅本地写失败可用同目录临时文件替换保护旧有效报告，临时文件非持久交付物。

### 3.7 UI 查询与未授权调用不可达

不改UI。Verify需在确认的Web origin打开 `/strategy-ide?sourceId=<sourceId>`，核对私有源码名称及实际源码片段；打开 `/backtest-center?sourceId=<sourceId>`，在原生历史列表点击最终run，读取页面显示的runId与收益/MDD/参数。当前页面不保证runId查询参数定位，不捏造 `?runId=` 深链。

进化在回测中心“策略进化”tab中，选择同一个source，找到本轮job历史并核对终态/结果；当前子组件不保证继承sourceId query，需实际选择。UI只查询，不点“应用并保存版本”或部署。ui-check.md记录时间、页面路径、可见读数和查询方式；截图可选但页面实读必须有。认证/页面未就绪则明确未完成，不能从API读回推导UI已经显示。

HTTP白名单仅 §3.3 表及 `GET /api/indicator/kline`、`GET /api/agent/v1/klines`。无任意请求命令。禁止访问 Quick Trade、/api/strategies 的实例创建/启停、deployments、credentials、billing、/api/auth/login、Agent T/C 写接口、源码publish/update/delete；禁止交易所SDK网络入口。策略.py中原生order_target_percent只在历史回测沙箱执行，不是HTTP下单授权；静态审计不能粗暴把该回测API当真实交易路径。研究脚本完全不含该类策略函数。

## 4. 实现计划

1. Developer 先产出白名单内单文件CLI与离线测试；无网络写导入；实现信封、预算/截止、参数消费与判定断言。冻结输入均由本Design给定，不新增上游文档/配置。
2. 补SKILL与两个样例业务spec/README；按当前原生模板复用交易源码；父SKILL只插路由。未真实执行时不把README或状态写为已接入。
3. 在正确origin/既有凭据/免费能力就绪时，执行最小真实交易闭环和研究脚本；每个写动作精确读回。前提缺失即时记录阻塞，不尝试修部署/新造token，不以fixture顶替。
4. 独立Tester按§5逐项实跑/实查，Reviewer独立核对代码、三文档、真实报告与安全；已有有效证据可复用，不重复触发第二次进化。主控Design Gate后才创建后续卡，本卡不创建代码卡。

## 5. 验证样例与可证伪验收

### 5.1 真实交易样例（只验首版接入，不是投资推荐）

固定ID `spy-ma-smoke`；复用 `strategy_v2_single_ma`（USStock:SPY、1d、long_only、warmup260）；当前窗口2017-06-01至2025-12-31（Pascal于2026-10-30批准方案C，仅延长窗口），UTC日期边界、交易所日线交易日语义，报告注明US市场日历。资本USD 10,000；commission=0.0005、slippage=0.0005，leverageEnabled=false、leverage=1。config仅 `ma_period=50,target_pct=0.95`，保留原生策略默认一致。

搜索 ma_period=20..80、step20（4点），target_pct固定0.95（min=max=0.95、step0.05）；grid trials=4、folds=4、trainRatio=0.7、blindRatio=0.15、embargo1、seed42、costMultipliers=[1,2]。先parameter-space核实名称/范围/可调属性，实际部署模板漂移则停止而非偷偷改策略规则。

本样例硬约束：真实市场数据、SPY/无杠杆股票身份、同窗口同成本、finite totalReturn/sharpeRatio/maxDrawdown、原生totalExecutions>0、全段峰值MDD≤50%。目标为合格项全段totalReturn最大；不设盈利保证，不把50%解释为运行时保证。fundingMode=not_modeled仍披露，对无融资SPY资金费不适用；非该市场身份不得套此例外。gross exposure与交易所杠杆分开，现货无杠杆不证明三币合约机器人敞口/强平限额已落实。

预算：内部estimate/actual≤8、relativeUnits≤8、外层jobs≤8且本样例预计最多6、复检参数组≤5、一次evolution run、总墙钟1200s、单backtest180s/evolution600s、轮询15s；零新增付费。成本与窗口来自本接入例子，不作为一般策略默认要求。

方案C复用的只读预检（不是本卡重跑）：`data/reports/2026-10-29-strategy-lab-verify/evidence/2026-10-30-c-window-preflight.json`，原始真实行情为同目录`2026-10-30-c-window-klines.json`；来源QuantDinger公开行情接口，实际2159条SPY/1D，首末2017-06-01T13:30:00Z..2025-12-31T14:30:00Z。以真实时间戳直接调用原生`build_walk_forward_plan`，lookback260、minimumTrainBars1300、minimumValidationBars130、embargoBars1，得到：

| UTC end边界 | sampleCount | developmentBars / blindBars | 各折trainBars | 各折validationBars | effectiveFolds |
|---|---|---|---|---|---|
| 2025-12-31T00:00:00Z | 2158 | 1834 / 323 | 1300,1433,1566,1699 | 132,132,132,134 | 4 |
| 2025-12-31T23:59:59Z | 2159 | 1835 / 323 | 1300,1433,1566,1699 | 132,132,132,135 | 4 |

原生依据（APP为§2缩写）：`services/strategy_evolution/walk_forward.py:66-164`按真实观测、lookback与gap拆分；`engine.py:64-80`取evaluator观测与warmup，`evaluator.py:104-119`过滤本次快照窗口。区间含首尾3136自然日；`services/backtest_limits.py:60-68,103-149`的USStock/1D maxDays3650、原生warmup日历预留对应当前maxSelectedDays3158，与该区间兼容，不改平台上限。变更窗口须核验真实观测与原生有效四折，不能以自然日或estimate.folds当通过证据；此前“约2125条足够四折”的估算已废弃，不作依据。公开行情预检不保证进化evaluator快照相同，真实job仍须核对有效四折、实际覆盖与成本；旧任务内部观测数未由API暴露，不声称已核验其完整取数。

历史与本次额度分开（SPEC V1.4 §8.1）：

| 窗口/轮次 | 已有事实 / 额度 | 执行边界 |
|---|---|---|
| 历史旧窗口2023-01-01..2025-12-31（superseded） | 基准run19成功；进化job `d249d4846e8e493b8d0d316b340f99de` failed，error=observationRangeTooShort | 原始失败及reports/命令原文保留，计入历史，不重试旧job；actualBacktestRuns=None为未报告，不能推断0次；旧基准不充当新窗口基准 |
| 本次2017-06-01..2025-12-31 | Pascal一次性额外授权，最多新建1个原生进化job；本卡未提交、无新jobId | 主控开始前只读核查该窗口已有job，存在则只读回、禁止重复创建；提交结果未知不重发；失败/取消/超预算立即停止，不自动重试 |

通用每次执行恰好一次进化规则及每轮上述预算均不变，不变成普遍2次额度。此次不修改源码、算法、搜索空间、成本或硬约束，不重做已完成CLI兼容修复/离线测试；沿用T4 `t_baaaef0b`与T5 `t_6346409a`。V1.4独立方案C Design Gate完成前主控不执行业务；Gate及文档同步均不等于真实T4/T5通过。

未来命令（独立Gate放行并核查无该窗口job后，才由主控按一次性额度执行；从项目根运行，凭据预先安全注入；本次文档阶段未执行）：

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py trade --strategy-dir skills/strategies/strategy-lab/strategies/spy-ma-smoke --start 2017-06-01 --end 2025-12-31 --capital 10000 --commission 0.0005 --slippage 0.0005 --search ma_period:20:80:20 --objective totalReturn --max-drawdown-pct 50 --method grid --trials 4 --folds 4 --max-evolution-runs 8 --max-relative-units 8 --wall-seconds 1200
```

报告保留baseline/候选各自全段totalReturn/annualizedReturn/sharpeRatio/maxDrawdown/winRate/totalTrades/totalExecutions与比较理由，原生OOS/blind统计另列；benchmarkTotalReturn可用则引用原生SPY基准。卡玛可由原生年化与MDD注明简单比值；换手/信息比率如原生未给且缺必要明细，写“不提供/不可核实”，不能造0或新写回测引擎补齐。样本内外取原生fold证据，披露单次回放切片与最终全段比较的过拟合限制。

### 5.2 真实研究样例与二次重跑

固定ID `spy-close-research`；问题：2024年SPY日收盘的日收益均值、日收益标准差、年化波动率及窗口首末收盘变化。只做统计，不输出模拟交易或伪造平台研究条目。

固定USStock/SPY/1D，窗口2024-01-01至2024-12-31；优先显式Human `/api/indicator/kline`（同平台，当前源码为公开只读），可由已签发R token显式选Agent `/api/agent/v1/klines`，不申请token。before_time取2025-01-01T00:00:00Z的unix秒，从end向前分页；Human每页≤1000，Agent每页≤2000，最多4页，返回time解析为UTC并按请求窗口过滤、去重、升序。下一页游标用最早time严格递减；重复/无进展停止；不把缓存数据称实时成交。

样本至少200条有效日线，close>0，OHLC有限且high≥max(open,close,low)、low≤min(open,close,high)、volume非负；周末/节假日不视为数据缺口，但首末交易日期及任何缺失列明，不补虚假bar。按实际time格式解析秒/毫秒/ISO并测试，不盲猜数量级。源码未透传实际上游供应商时，来源写“QuantDinger <实际endpoint>，底层供应商未由接口披露”，不冒称某供应商。

日收益为连续交易日close比值减1，均值/样本标准差（ddof1），年化波动率乘sqrt252，均在报告注明定义。两次运行都真实取数，每次≤4个data请求/180s，两次合计≤8次；不使用第一次CSV作为第二次的假接入。报告含请求区间、实际首末时间UTC、样本数、来源、提取时间Asia/Shanghai、指标及限制；latest.csv不写提取时间，便于重跑比较。

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/spy-close-research/research.py --data-api human
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/spy-close-research/research.py --data-api human
```

Tester在两次之间保留计数/指标/CSV校验值用于replay-check.md，两次退出0、数据行与派生指标一致（允许报告提取时间不同）。如平台事后数据修订导致差异，记录真实差异及原因，不能伪装一致；该回归验收应报告未通过/未证实。缺数据可用项目既有数据能力处理未来问题，但本样例不能在失败后悄悄换成fixture。

### 5.3 离线断言（不替代接入）

测试文件固定为 L/tests/test_quantdinger.py，stdlib unittest，使用显式假HTTP响应/受控时钟：

- scope=none/无参数/固定参数/成熟执行：run调用数=0，结果skipped且有理由；研究永不进化。
- 估算连续超预算：estimate调用≤3、收缩≤2、run=0、预算退出；folds始终4；tpe不足24及folds<4预检拒绝。
- 进化提交成功后failed/cancelled/workerInterrupted：run恰好1，无最终回测，诊断字段保留；超时cancel只对本轮ID，未知取消状态不冒称停算。
- HTTP401/403：仅一次该请求，无重登/换token/自动fallback；Human code=1与Agent code=0分别识别，HTTP200但业务错误不能判成功。
- 基准合格且候选较差→baseline-kept；基准违反MDD而较低收益候选合格→candidate；全部FAIL→no-qualified且最终run=0；缺失/NaN/相关funding未知→insufficient-evidence（含一项FAIL和另一项UNKNOWN的组合）。
- 平台summary.recommended=true但全段MDD不合格→不推荐；summary平均回撤与全段MDD数值冲突时只认后者；MDD正值/未知拒绝通过；同成本/窗口不一致拒绝比较。
- 数值参数范围越声明/无实际消费拒绝；config固定参数确实进入原生params/parameterSpace，不能在evolution中丢失；相同参数候选去重；完整外层job数≤8与内部backtestRuns分栏。
- create/readback私有/源码/metadata不一致→最多重读1次、create仍1次；run读回检查data.result而非data顶层；失败POST不重发。
- request_json白名单拒绝未授权operation/任意路径；无trade部署调用；write_report丢弃headers/token/password字段，输出无秘密，路径逃逸拒绝；导入测试网络调用数=0。
- 行情空页、重复游标、非法OHLC、时区/时间单位、200条下限、两次固定输入输出一致的算法测试；这些仅验证本地逻辑，真实数据验收另行完成。

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/tests -p 'test_quantdinger.py' -v
```

### 5.4 SPEC 验收映射与证据分栏

| SPEC | 最小实现/可证伪验证 | 不能冒充通过的情形 |
|---|---|---|
| A-001 / S-1,S-5 | SKILL frontmatter可加载、三步/进化/安全正文完整；父SKILL链接能解析 | 只有README或空SKILL |
| A-002 / S-2 | git status含untracked逐项对§3.1，path-scoped diff --check，检查无SDK/包/子模块写 | 只检查tracked diff漏新文件 |
| A-003 / F-001,002,005,007 | 真实sourceId私有读回、baseline run、evolution终态与source列表、final run/history；另有UI实读 | auth失败、404、只有202、只有mock或API读回即说UI已查 |
| A-004 / F-003,006 | comparison.csv完整参数/全段证据，report有平台OOS与最终全段口径及判定；§5.3断言 | 原生排名=硬约束通过、平均分窗=全段MDD、未知当0 |
| A-005 / F-008 | §5.2真实执行两次，CSV/指标/日期身份/来源/预算核对 | 第二次只读第一次文件、随机生成/fixture数据 |
| A-006 / F-009 | unittest实际命令、解释器、case计数和退出码 | 没运行却写PASS |
| A-007 | 审阅HTTP operation白名单及策略仅沙箱执行；否定用例拒绝交易路径 | grep无关键词但保留任意HTTP透传 |
| A-008 | 检查本次文档/代码/报告/控制台无凭据值，测试敏感字段过滤；不读取真实.env做扫描 | 用原始HTTP/环境dump作为证据 |
| A-009 / F-004 | estimate原值vs预算、收缩计数、run=1、内部实际vs外层jobs、超时记录 | 内外回测数混用、超预算自动重启/加预算 |

成功平台写的验证为必要条件，但不等于所有业务/页面验收已完成。Tester记录真实与fixture各自PASS/FAIL/未运行，Reviewer至少抽读交易/研究报告与UI读数；正确处理失败分支的单测通过不表示真实闭环通过。

## 6. 风险、降级与回滚

| 风险 | 应对 / 保留限制 | 完成状态 |
|---|---|---|
| 认证/免费开关未验收 | §2.1追加15000 API/15080 Web可达及401证据，安全注入接口冻结；主控提供既有会话并认证后读public-config，禁止新token/登录/部署 | 本Design可交接；可达不等于真实接入通过，执行前提缺失须报告阻塞 |
| 部署与本地源码版本漂移 | 请求契约/范围/字段不符就停止，保留安全错误键和实际端点，不修改子模块 | 不能用health或source HEAD替代实调 |
| private/draft并非Human服务强制 | 显式字段+detail核对；禁止publish/update | 满足私有保存要求，不依赖不成立的强制假设 |
| 进化排序误读/样本过拟合 | 原生OOS排名与本地全段目标分列；未知不通过；full replay后不声称盲样本仍独立 | 研究推荐非Live授权 |
| 资源取消非强杀、estimate非上界 | 一次run、预估检查、客户端截止和取消读回；不能承诺硬CPU封顶 | 不扩建计算调度/修改引擎；actual缺失明确未知 |
| 未建模合约/成本/敞口 | 只选无杠杆SPY小例；其他市场关键未知不足以通过；G1/G2不变 | 不扩成三币网格研发，不替代实盘限额 |
| UI无会话/无法看到ID | ui-check写未完成并交主控；不得由API推断UI成功 | 不能以截图fixture完成A-003 |
| 本地结果覆盖/秘密泄露 | 字段白名单、目录边界、重要结果保留、无凭据日志 | 不自动删平台事实；reports是否纳Git仍由Pascal Closeout决定 |

## 7. 交接给实现者与主控

- 必须遵守：SPEC六分支、§3.1精确allowlist、Human源码闭环同owner、零付费/零交易/零凭据配置/零子模块修改、一次run、真实读回与真实UI分开；不commit/push。当前仅Design完成，不宣称产品功能/真实验收完成。
- 可自行判断：单文件函数内部排版、提示文案、必要类型注解/测试组织、报告表格布局；不可新增业务阶段、更多provider/SDK/任务持久化或改变策略/成本/目标来追求PASS。
- 需即时报告的运行前提：实际origin与§2.1已知可达目标/部署契约不符、Human JWT未安全注入/失效、认证后免费能力未知、UI认证不可用；不泄露秘密、不替操作者创建凭据、不要求新token。它们阻断真实执行，不阻断离线实现，不要求为了完成文档而部署。
- 退回Principal的条件：声明参数实际不生效、平台契约/统计含义实质变化、需要支持本版以外的目标/市场关键建模、文件清单扩张；如上游语义确实矛盾，给路径/行号停止，不以Design覆盖RFC/SPEC。
- 下一步由YQuant核验三文件并做Design Gate，再创建正式Implement→独立Verify→独立Review；本卡不新增下游任务。报告是否Git提交与运行态凭据提供属于主控/操作者，不隐含授权。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-10-29 | T2设计：单文件薄调用、Human私有源码闭环、双计数预算、原生口径、两个有界真实样例与独立UI验收 |
| V1.1 | 2026-10-29 | docs-only同步RFC/SPEC：Human默认值须显式发送/读回、真实wire字段、validation回撤不含blind、folds固定4与内外预算；追加15000/15080主控探测且保留5000/8888历史，public-config先JWT认证；不追认旧错误、不改业务目标/实现allowlist |
| V1.2 | 2026-10-30 | 按 Pascal 明确裁定将策略/研究实例移到 skills/strategies/<strategy-id>/；同步当前路径清单与本地守卫，不改业务、预算或冻结安全边界 |
| V1.3 | 2026-10-30 | Pascal纠正最终实例根为 skills/strategies/strategy-lab/strategies/<strategy-id>/；取代V1.2直属目录方案，仅同步路径、守卫与导入，不改业务/预算/安全门禁 |
| V1.4 | 2026-10-30 | 方案 C：仅延长交易样例窗口至2017-06-01..2025-12-31；列真实2159/2158条原生四折预检、范围兼容与一次性最多1个新job边界，历史及每轮预算不变，未真实重跑 |

## V1.3 最终目录裁定（2026-10-30，取代 V1.2 目录方案）

当前唯一有效实例位置为 `skills/strategies/strategy-lab/strategies/<strategy-id>/`。两个验证样例分别是 `skills/strategies/strategy-lab/strategies/spy-close-research/` 与 `skills/strategies/strategy-lab/strategies/spy-ma-smoke/`；二者不是用户网格策略、不代表可上线。strategy-lab 根层保留 SKILL、README、scripts、templates、tests，并由 strategies 子目录集中容纳具体实例。不得在 strategy-lab 根层或 skills/strategies 直属层留下这两个实例的副本或兼容 symlink。

V1.2 的直属目录位置已被本节替代，其版本记录保留作历史，不作为当前执行指令。此前已搬文件直接从现场继续收口，不能重建或覆盖已有 reports；历史报告命令/结论与数据逐字保留。CLI 路径守卫仅接受上述实例根的直接子目录，拒绝根外、更深嵌套和 symlink 逃逸。V1.3 当时只调整目录、必要路径/导入与命令，不改策略、算法、API、预算、认证或交易逻辑；目录裁定仍有效，当前 RFC/SPEC/Design 契约版本统一 V1.4，样例窗口及一次性额度以 §5.1 为准。

用户要求继续 T4 的请求保留；目录迁移只做离线验证，不等于解除既有安全暂停或真实业务通过。T4 的凭据传递与诊断拒绝须先按已批准边界纠正，禁止恢复已删除的明文 JWT 文件、禁止重跑被拒辅助诊断；不新增实盘/部署授权。
