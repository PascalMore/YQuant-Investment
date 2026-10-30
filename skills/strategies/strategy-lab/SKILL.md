---
name: strategy-lab
description: "YQuant Strategy Lab：按「定义 → 执行 → 交付」三步操作 QuantDinger 原生回测/进化与真实数据研究的最小操作 Skill。"
---

# Strategy Lab

按 [RFC-06-001](../../../docs/rfc/06_strategy/RFC-06-001-strategy-lab.md)、
[SPEC-06-001](../../../docs/spec/06_strategy/SPEC-06-001-strategy-lab.md)、
[DESIGN-06-001](../../../docs/design/06_strategy/DESIGN-06-001-strategy-lab.md)（三文档V1.4；方案C独立Design Gate、T4验证及T5首版签收已通过，详见文末状态与正式报告）
运行的操作型 Skill。本文件是面向 AI 的操作约定，不是 runtime；不建第二套回测引擎、任务系统或 SDK。

## 目录职责边界（2026-10-30 用户裁定）

- `skills/strategies/strategy-lab/`：**只放研发工具资产**——本 SKILL、README、`scripts/quantdinger.py`、
  `templates/strategy-spec.md`、`tests/`。
- `skills/strategies/strategy-lab/strategies/<strategy-id>/`：**每个策略/研究实例一个目录**，
  集中在 `strategy-lab/strategies/` 子目录下。
  现有两个样例为 `skills/strategies/strategy-lab/strategies/spy-ma-smoke/`（交易接入冒烟）与
  `skills/strategies/strategy-lab/strategies/spy-close-research/`（研究取数/重跑），
  均非用户网格策略、不代表可实盘。
- 未来新增策略一律建在 `skills/strategies/strategy-lab/strategies/<strategy-id>/`，
  不得建在 `strategy-lab/` 根层，也不得建在 `skills/strategies/` 直属层。
- `quantdinger.py trade --strategy-dir` 只接受
  `skills/strategies/strategy-lab/strategies/` 的**直接子目录**，拒绝更深嵌套、
  根外目录与符号链接逃逸。

## 本地运行环境（Pascal 已确认）

本地 CLI、研究脚本和单测一律显式使用项目 venv Python 3.12，不依赖 PATH 或环境激活：

- 项目根执行：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python ...`
- 跨目录执行：`PYTHONDONTWRITEBYTECODE=1 /home/pascal/workspace/yquant-investment/.venv/bin/python ...`

不得使用 PATH 中的 python3、Hermes 自带解释器或 QuantDinger 后端 venv；不新建模块 venv、不安装依赖。
该约定只统一本地调用环境；策略 `.py` 源码仍在 QuantDinger 平台沙箱执行，本地不 import、不运行。
历史 run/报告保留其真实旧解释器记录，不追认为项目 venv 结果。

## 目录结构

```
strategy-lab/                     # 只放研发工具资产
├── SKILL.md                  # 本文件
├── README.md                 # 已确认方案（上游文档，不改动）
├── templates/strategy-spec.md  # spec.md 模板（上游文档，不改动）
├── scripts/quantdinger.py    # 单文件薄调用 CLI（trade / fetch-klines）
├── tests/test_quantdinger.py # stdlib unittest 离线断言
└── strategies/                # 每个策略/研究一个目录，集中在 strategy-lab 内
    ├── spy-ma-smoke/          # 交易类样例（README/spec/config/strategy.py/reports）
    └── spy-close-research/    # 研究类样例（README/spec/research.py/reports）
```

每个策略/研究一个目录：`spec.md`（需求冻结）、`config.json`（仅交易参数数值）、
主脚本（`strategy.py` 由平台执行 / `research.py` 本地执行）、`reports/`（最新结果）。
不建 version/runs/manifest/快照目录。

## 业务三步

1. **定义**：在 `skills/strategies/strategy-lab/strategies/<id>/` 写 `spec.md`（目标、数据/市场身份、规则、参数、硬约束、
   比较目标、预算）与交易类 `config.json`（仅可调参数数值）。语义冻结在 spec，不从自然语言现场解析。
2. **执行**：
   - 交易类：`scripts/quantdinger.py trade --strategy-dir <dir> ...` 一次前台顺序流程——
     认证与免费能力预检（public-config 先 JWT 认证，`billing_enabled=false` 才提交）→
     compile → create（显式 `visibility=private`、`status=draft`）→ detail 读回 →
     基准回测（persist=true）→ parameter-space → estimate（超预算只收缩 ≤2 次）→
     恰好一次 evolution run → 候选全段复检（参数组含基准 ≤5）→ 六分支判定 →
     有推荐则最终回测并读回 → 写 `reports/report.md` 与 `reports/comparison.csv`。
   - 研究类：目录内 `research.py` 直接执行；只调用行情读接口，不交易、不进化。
3. **交付**：报告记录 `sourceId`/`runId`/`jobId`、判定分类、限制与复现命令；
   平台侧 UI 实查（`/strategy-ide?sourceId=`、`/backtest-center?sourceId=`）由独立 Verify 完成。

## 自动进化与停止规则（SPEC §5 冻结，不现场改判）

- 跳过：scope=none、无 optimizable 参数、用户显式禁优化、研究类/成熟策略日常执行 →
  不调 run，报告 skipped+原因；基准仍须核对硬约束。
- 判定只落在六分支之一：skipped / baseline-kept / candidate / no-qualified-candidate /
  insufficient-evidence / failed（含超预算）。任何影响结论的 UNKNOWN 优先 insufficient-evidence，
  缺失指标不当 0，不把 `summary.maxDrawdown`（validation 折绝对值均值，不含 blind）当全段 MDD；
  硬约束只认全段读回 run 的 `data.result.maxDrawdown`。
- 停止：run 恰好 1 次，failed/cancelled/workerInterrupted/超预算即停，带
  `progress.failure` 诊断，不自动重试、不换窗口/成本/硬约束求通过。
- 预算上限（可下调不可上调）：trials ≤64、全段复检组 ≤5、外层持久化回测 job ≤8、
  研究数据请求 ≤50、墙钟 ≤1800s、folds 固定 4；estimate 与 actualBacktestRuns 分栏记录。

## 命令与退出码

spy-ma-smoke当前仅按2026-10-30批准的方案C延长至2017-06-01..2025-12-31，warmup260、folds4、
源码/算法/搜索空间/成本/硬约束不变。独立方案C Design Gate完成前主控不执行业务；下方trade命令
只在开始前只读核查该窗口无已有job后使用。若已有job则只读回、禁止重复创建；本次一次性额外
授权最多1个新原生进化job，不把通用每次恰好一次进化规则改成2次。历史旧窗口
2023-01-01..2025-12-31（superseded）的run19与failed job `d249d4846e8e493b8d0d316b340f99de`
（observationRangeTooShort）保留并与新窗口job分列，不重试旧job、不改历史reports/命令。
每轮内部backtestRuns/actualBacktestRuns≤8、relativeUnits≤8、外层持久化回测jobs≤8（预计最多6）、
参数组含基准≤5、墙钟1200s、零新增付费保持；失败/取消/超预算立即停、不自动重试，提交结果未知不重发。

变更样例窗口须用真实观测及原生拆分核验有效四折，不能以自然日或estimate.folds当通过证据。
Design V1.4 §5.1所引C预检真实日末2159条/午夜2158条均有效4折；公开取数不保证进化evaluator
快照相同，真实job仍须核对四折、覆盖与成本。actualBacktestRuns=None为未报告，不推断0。

```text
# 交易类（示例固定值来自 spy-ma-smoke/spec.md；凭据由主控经安全机制注入环境）
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py trade --strategy-dir skills/strategies/strategy-lab/strategies/spy-ma-smoke --start 2017-06-01 --end 2025-12-31 --capital 10000 --commission 0.0005 --slippage 0.0005 --search ma_period:20:80:20 --objective totalReturn --max-drawdown-pct 50 --method grid --trials 4 --folds 4 --max-evolution-runs 8 --max-relative-units 8 --wall-seconds 1200

# 研究类（真实取数，两次执行可重跑比对）
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/spy-close-research/research.py --data-api human
```

退出码：`0` 正常业务结果（含 skipped / no-qualified-candidate）、`2` 平台或契约失败、
`3` 证据不足、`4` 认证缺失或 401/403、`5` 预算或超时、`64` 参数或本地路径错误。

## 安全边界

- 凭据仅经进程环境注入：`QUANTDINGER_BASE_URL`（无 /api 后缀）、`QUANTDINGER_JWT`（Human）、
  `QUANTDINGER_AGENT_TOKEN`（仅显式 Agent 行情模式）。不登录、不签 token、不读写 .env、
  不收集浏览器存储；401/403 一次即停，不换 token 绕过。
- HTTP 仅限 CLI 内冻结的 operation 白名单（Design §3.3 表 + 行情两个只读端点）；
  无任意 path/method 透传。禁止 Quick Trade 下单、deployments、credentials、billing、
  `/api/auth/login`、源码 publish/update/delete 等调用路径。
- 策略源码中的 `order_target_percent` 只在平台历史回测沙箱执行，不构成真实下单授权；
  首版交易闭环固定 Human JWT，缺 JWT 如实阻塞，不 mock 替代。
- 报告只存明确业务字段，丢弃 headers/token/password 样式字段；不含凭据、账户或原始 HTTP 响应。
- 不修改 QuantDinger 子模块、不改部署/配置、不 commit/push、不做 Demo/Live 与调度。

## 状态

- 2026-10-30 首版完成：独立方案C Design Gate run3359 APPROVE；T4独立复验 run3362 PASS，48/48测试、A-001~A-009最终矩阵全部通过；原T4卡已关闭。
- T5原卡 t_6346409a 的完整审查 run3369 发现一项摘要精度Minor，修正后由 reviewer run3371 限定复核，最终 full_verdict=APPROVE、open_findings=0；历史REVISE与流程偏离保留，不追认。
- 真实交易样例已完成私有源码、回测、原生进化、最终回测及平台UI核验；研究样例已完成两次真实取数与复算。以上指接入样例，不表示用户PUMP/HYPE/JUP合约网格已实现，也不表示实盘可用或盈利保证。
- 正式证据：[T4验证报告](../../../data/reports/2026-10-29-strategy-lab-verify/report.md)、[T5签收报告（最终第6节）](../../../data/reports/2026-10-30-strategy-lab-final-review/report.md)。报告位于Git忽略的本地data目录，不代表已提交、推送或远程备份。
- 此处仅同步已验收状态，不改变业务契约、代码、样例参数或原始证据；未执行Demo/Live、发单、部署、调度或生产配置变更。
