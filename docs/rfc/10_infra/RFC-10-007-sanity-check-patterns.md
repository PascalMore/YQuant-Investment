# RFC-10-007：Sanity Check 标准模式 Skill

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-07-08 |
| 版本号 | V0.1 |
| 所属模块 | 10_infra（基础设施 / 工程质量） |
| 来源任务 | Quick Flow T1 `t_a4539961` |
| 依赖 RFC | RFC-10-004-yquant-ai-coding-pipeline-skill-sync, RFC-10-005-hermes-auto-upgrade, RFC-10-006-hermes-upgrade-script-v2 |
| 关联 SPEC | SPEC-10-007-sanity-check-patterns |
| 关联 Design | DESIGN-10-007-sanity-check-patterns |
| 标签 | #infra #quality #sanity-check #fail-fast #skills |

## 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-08 | 初始 RFC：定义 sanity check 的哲学边界、统一模板范围和 Quick Flow 交付边界 | YQuant-Codex-Principal |

## 1. 执行摘要

YQuant 当前存在多处“接口级安全检查 / sanity check”模式，但它们散落在不同 skill、脚本和 worker 习惯中：有些地方已经采用 fail-fast，有些地方仍存在 silent fallback、默认值漂移或危险 no-op 参数。Pascal 对这类问题的偏好很明确：危险的 no-op / silent wrong input 应删除或 fail-fast，而不是只在文档里提醒。

本 RFC 建议新增一个统一的工程质量 skill：`skills/quality/sanity-check/`。该 skill 不替代业务 validation，也不替代运行时 error handling；它沉淀“数据进入业务逻辑之前，对输入和环境的最后一道合理性闸门”，为 worker 在新增功能、修改 CLI、接入文件/数据库/日期字段时提供可复制的 Python 标准模板。

## 2. 问题陈述

### 2.1 当前 sanity check 散落模式

当前 YQuant 项目中 sanity check 以局部经验形式出现：

- 升级脚本：manifest 存在、schema 校验、dirty tree、branch、dry-run 等检查已经较完整。
- MongoDB 读写：`position_date` / `trade_date` / `nav_date` 应保持 `YYYY-MM-DD` 字符串语义，但不同入口缺少统一日期格式闸门。
- Image / Message pipeline：文件路径、业务日期、OCR/解析输入应在进入 pipeline 前检查，避免审计目录错位。
- Outbound report：目标 chat / token / env 缺失时，不应静默落到危险默认收件人。
- 通用 CLI：新增 `store_true` 参数后，如果实现层没有消费该参数，会形成 no-op arg；用户以为安全模式已启用，实际仍跑生产路径。

问题不是“没有任何检查”，而是“每个 skill 各自造轮子，没有统一判断标准、错误消息风格和 fail-fast / warn 选择准则”。

### 2.2 真实反模式证据

T1 扫描发现至少 3 类需要标准化的高风险模式（P0 候选）：

| 证据 | 位置 | 风险 | 建议归类 |
|---|---|---|---|
| 未知 collection 默认用 `position_date` 查询 | `skills/data/data_interface/mongo_reader.py:67-85` | 调用者传错集合名时不会 loud fail，而是可能按持仓日期字段查询错误集合，造成空结果或错结果被当作真实数据 | P0：生产数据正确性 |
| Daily Smart Money report 在目标群缺失时 fallback 到 Pascal 个人 chat id | `skills/reports/daily-smartmoney-analysis/scripts/daily_export_report.py:494-508` | Outbound recipient 缺失属于环境配置错误；静默改发个人账号会掩盖群推送失败，也可能扩大敏感报告泄露面 | P0：外部消息发送 / 隐私 |
| Smart Money watcher 无法从路径提取日期时 fallback 到今天 | `skills/data/data-pipeline/scripts/smart_money_watcher.py:145-151` | 文件路径日期缺失时静默写入今天目录，可能导致 OCR / message 审计日期错位 | P0：数据审计与日期语义 |

同时存在 P1/P2 候选：

- `skills/reports/daily-market-analysis/scripts/main.py:191-192` 捕获 marker mtime 读取异常后 `pass`，更适合 warn。
- `skills/reports/daily-market-analysis/scripts/main.py:253-255` `--debug` 分支引用 `report` 变量，说明 debug 参数需要最小 smoke test 防 no-op / broken arg。

## 3. 哲学层定义

### 3.1 一句话定义

Sanity check 是：在数据流入业务逻辑之前，对输入和环境的最后一道合理性闸门。

它不是 validation（业务规则判断），也不是 error handling（运行时异常恢复）。它的职责是尽早阻止“显然不合理、会静默污染后续状态、用户难以察觉”的输入或环境进入主流程。

### 3.2 三个判定标准

1. Silent vs loud：silent wrong input 一律禁止；错误必须 loud（异常、明确 stderr、非零 exit 或结构化 warning）。
2. Correctable vs fatal：调用方可自动修复且不会改变语义的，可 warn-and-continue；不可自动修复或会污染状态的，必须 fail-fast。
3. Visible cost：用户能否及时察觉？用户察觉不到或要到报告/数据库/外部消息后才发现的，风险等级最高。

### 3.3 与 validation / error handling 的边界

| 类型 | 问题 | 示例 | 所属层 |
|---|---|---|---|
| Sanity check | 输入形态或环境是否足以安全进入主逻辑 | 日期必须是 `YYYY-MM-DD` 字符串；输出路径 parent 可写；目标 collection 属于允许列表 | 本 RFC |
| Validation | 业务对象是否满足业务规则 | 持仓比例在 0~1；策略信号 zone 只能从 CANDIDATE/CORE/EXIT 中选 | 业务 SPEC / schema |
| Error handling | 已进入主逻辑后的异常如何恢复 | Tushare 429 后重试；OCR 超时后走备用 provider | 运行时设计 |

### 3.4 三大反模式

| 反模式 | 典型写法 | 危险 |
|---|---|---|
| silent coercion | `date = kwargs.get('trade_date', datetime.now().strftime('%Y-%m-%d'))` | 传错字段时默默使用今天，审计错位 |
| try/except pass | `try: parse(x); except: pass` | 错误吞掉，后续状态不可解释 |
| no-op arg | `parser.add_argument('--debug', action='store_true')` 但实现未消费或 broken | 用户以为 debug 生效，实际跑生产路径或崩在边缘路径 |

### 3.5 Pascal 偏好固化

本 RFC 将以下偏好固化为工程准则：

- remove/fail-fast dangerous no-op pipeline args rather than only documenting。
- silent wrong inputs are worse than absent inputs。
- 两阶段处理：临时方案 → 复盘 → 长期方案。Sanity check skill 是把复盘沉淀为长期方案。

## 4. 设计目标

### 4.1 Must-Have

- [ ] 新增统一 skill：`skills/quality/sanity-check/`。
- [ ] 提供 6 个常见 sanity check 模板：`interface_arg_check`、`file_existence_check`、`type_coercion_check`、`date_format_check`、`git_state_check`、`mongo_connection_check`。
- [ ] 每个模板包含触发条件、检查逻辑、错误消息、fail-fast vs warn 建议、可 copy-paste 的 Python 标准库代码。
- [ ] 提供 fail-fast vs warn-and-continue 决策表。
- [ ] 提供真实反例目录，至少覆盖 3 条 P0 候选，带文件:行号、风险和修复方向。
- [ ] Worker 在新增功能、改接口、加 CLI 参数、接入文件/Mongo/日期字段时，可加载该 skill 并直接使用模板。

### 4.2 Should-Have

- [ ] 提供 `scripts/self_test.py`，验证模板代码片段的核心行为。
- [ ] 错误消息统一包含字段名、期望、实际、修复建议。
- [ ] 模板默认不引入第三方依赖；需要 MongoDB smoke test 时允许以 optional import 方式处理 pymongo。

### 4.3 Non-Goals

- [ ] 不在本次 T1 直接修复现有反模式代码。
- [ ] 不替代 Pydantic / JSON Schema / Mongo schema validation。
- [ ] 不新增全局 pre-commit hook 或 CI gate。
- [ ] 不要求所有历史脚本一次性迁移。
- [ ] 不触碰生产 MongoDB 数据、真实外部消息发送或交易/风控逻辑。

## 5. 方案概览

### 5.1 新 skill 结构

```text
skills/quality/sanity-check/
├── SKILL.md
├── references/
│   ├── templates.md
│   ├── fail-fast-vs-warn.md
│   └── examples.md
└── scripts/
    └── self_test.py
```

### 5.2 模板选型理由

| 模板 | 选型理由 |
|---|---|
| `interface_arg_check` | YQuant 大量入口是 CLI / script；no-op arg 与危险 flag 会直接误导操作者 |
| `file_existence_check` | 数据管道、报告、skill 产物都依赖文件路径；读写语义不同，需区分 fail-fast / warn |
| `type_coercion_check` | JSON/YAML/CSV/env 输入常是字符串，进入业务前要显式转换且 loud fail |
| `date_format_check` | `position_date` / `trade_date` / `nav_date` 等在 YQuant 中多为 `YYYY-MM-DD` 字符串，混入 datetime 会破坏查询和审计 |
| `git_state_check` | 升级、auto-push、pipeline 编排必须知道 branch/dirty/unpushed 状态 |
| `mongo_connection_check` | `tradingagents` 是关键数据库；生产写入前必须确认连接、db、collection 和可选只读 ping |

未纳入第一版的候选：network_check（瞬时错误过多，应属 retry/error handling）、schema_check（属 validation）、rate_limit_check（属业务/平台策略）、auth_check（属 OAuth/middleware）、permission_check（多数可并入 file existence / OS 层错误）。

## 6. Quick Flow 交付边界

本任务是 Quick Flow T1（RFC/SPEC/Design 合并 task）。T1 只产出三层文档，不直接实现 skill 文件；后续 T2 Implement 按 DESIGN-10-007 的文件清单创建 `skills/quality/sanity-check/`。这是为了保留 Principal / Developer 角色边界，避免 T1 同时设计和实现。

T1 交付物：

1. `docs/rfc/10_infra/RFC-10-007-sanity-check-patterns.md`
2. `docs/spec/10_infra/SPEC-10-007-sanity-check-patterns.md`
3. `docs/design/10_infra/DESIGN-10-007-sanity-check-patterns.md`

T2 预期交付物：

1. `skills/quality/sanity-check/SKILL.md`
2. `skills/quality/sanity-check/references/templates.md`
3. `skills/quality/sanity-check/references/fail-fast-vs-warn.md`
4. `skills/quality/sanity-check/references/examples.md`
5. `skills/quality/sanity-check/scripts/self_test.py`

## 7. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 过度工程化，把 validation/error handling 都塞进 sanity check | skill 难用，worker 不加载 | 在 SKILL.md 首页放边界表和反例 |
| 模板代码过重 | Developer 复制成本高 | 仅用标准库，Mongo 模板 optional import |
| 反例被误读为本次必须修复 | 扩大范围 | examples.md 明确“反例目录，不是 T2 修复清单” |
| fail-fast 过严导致 best-effort report 不中断 | 报告可用性下降 | 决策表区分生产写入/外部发送 vs 只读/调试路径 |

## 8. 验收标准

- [ ] RFC/SPEC/Design 三层文档存在且互相引用一致。
- [ ] SPEC 定义 6 个模板的接口、错误消息和可 copy-paste 代码。
- [ ] DESIGN 给出不超过 6 个实现文件的精确清单，并明确 T2 不改历史业务代码。
- [ ] 至少 3 条 P0 反例带文件:行号、风险和修复方向。
- [ ] fail-fast vs warn-and-continue 决策表存在。
- [ ] 后续 T2 worker 可只读 SPEC/DESIGN 即实现 skill，无需重新查散落代码。
