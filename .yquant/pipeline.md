# YQuant AI Coding Pipeline

本文档定义 YQuant 的 AI Coding 七阶段流水线。`docs/rfc` 保留为项目需求/RFC 文档层；`docs/spec` 与 `docs/design` 作为从 RFC 派生出的工程落地层。

## 1. 流水线总览

| 阶段 | Agent | 默认模型 | 主要产出 | 是否允许改代码 |
|---|---|---|---|---|
| 1 Intake 需求澄清 | YQuant | Codex-gpt5.5 | `00-intake.md` | 否 |
| 2 RFC/SPEC 编写 | YQuant-Codex-Principal | Codex-gpt5.5 | RFC 更新、`docs/spec/*.md` | 通常否 |
| 3 Design 设计 | YQuant-Codex-Principal | Codex-gpt5.5 | `docs/design/*.md`、实现计划 | 否 |
| 4 Implement 代码实现 | YQuant-Developer-Engineer | minimax 2.7 | 代码变更、实现记录 | 是 |
| 5 Verify 测试验证 | YQuant-Test-Engineer | minimax 2.7 | 测试、`05-test-report.md` | 仅测试/修正测试夹具 |
| 6 Review 独立审查 | YQuant-Reviewer-Principal | Codex-gpt5.5 | `06-review.md` | 否 |
| 7 Closeout 收尾 | YQuant | Codex-gpt5.5 | `07-closeout.md`、用户交付摘要 | 否 |

## 2. 任务目录

每个非平凡工程任务创建一个任务目录：

```text
tasks/active/YYYY-MM-DD-short-name/
  00-intake.md
  01-rfc-link.md
  02-spec.md
  03-design.md
  04-implementation-plan.md
  05-test-report.md
  06-review.md
  07-closeout.md
```

已完成任务移动到 `tasks/done/`。如果只是修复一行配置或纯文档小改，可跳过任务目录，但仍需在最终回复中说明验证结果。

## 3. 文档分层

`docs/rfc` 是需求与架构约束层：
- 说明为什么要做、业务目标、模块边界、数据/接口方向、验收标准。
- 现有 RFC 可继续作为项目需求文档使用，不需要迁移。
- 修改数据模型、模块边界、对外接口、交易/风控语义时，必须先更新相关 RFC。

`docs/spec` 是工程规格层：
- 从 RFC 抽取可执行需求。
- 明确功能行为、输入输出、错误处理、验收项、测试要求。
- 是 Developer 和 Test Engineer 的直接工作依据。

`docs/design` 是实现设计层：
- 明确文件/模块改动、关键接口、数据流、迁移策略、实现顺序。
- 必须包含测试策略和回滚/降级说明。

## 4. 阶段门禁

### 4.1 Intake
- 输入：用户原始需求、相关上下文。
- 输出：需求摘要、目标/非目标、约束、开放问题、初步验收标准。
- 通过条件：需求边界足够清楚，能进入 RFC/SPEC。
- 回退条件：核心目标、数据源、交易风险或权限不清楚。

### 4.2 RFC/SPEC
- 输入：`00-intake.md`、相关 `docs/rfc`。
- 输出：必要的 RFC 更新、`docs/spec/*.md` 或任务内 `02-spec.md`。
- 通过条件：每条需求都有可验证验收标准。
- 回退条件：RFC 与现有系统约束冲突，或验收标准不可测试。

### 4.3 Design
- 输入：RFC/SPEC、现有代码结构。
- 输出：`03-design.md`、`04-implementation-plan.md`。
- 通过条件：能定位改哪些文件、按什么顺序改、如何验证。
- 回退条件：设计需要新增依赖、改数据库结构、改对外接口但未获确认。

### 4.4 Implement
- 输入：SPEC、Design、Implementation Plan。
- 输出：最小范围代码变更、必要测试。
- 通过条件：实现完整覆盖计划，不引入无关重构。
- 回退条件：设计缺口导致需要扩大范围，或本地验证无法继续。

### 4.5 Verify
- 输入：代码变更、SPEC、验收标准。
- 输出：测试报告，包含执行命令、结果、覆盖范围、未覆盖风险。
- 通过条件：关键测试通过，失败项有明确处置。
- 回退条件：核心验收失败或测试环境不可用且无替代验证。

### 4.6 Review
- 输入：diff、RFC/SPEC/Design、测试报告。
- 输出：按严重程度排序的审查意见。
- 通过条件：无阻塞级问题；剩余风险可接受。
- 回退条件：实现偏离 SPEC、测试缺口影响核心行为、存在安全/交易风险。

### 4.7 Closeout
- 输入：实现结果、测试报告、审查结论。
- 输出：交付摘要、已验证事项、风险、后续项。
- 通过条件：用户能清楚知道改了什么、如何验证、还有什么风险。

## 5. 路由规则

- RFC/SPEC/Design/架构/接口/数据模型：`YQuant-Codex-Principal`。
- 代码实现：`YQuant-Developer-Engineer`。
- 测试验证：`YQuant-Test-Engineer`。
- 独立审查：`YQuant-Reviewer-Principal`。
- 需求入口与收尾交付：`YQuant`。

`Implement`、`Verify`、`Review` 必须由不同角色完成。紧急小修可以合并 Intake/RFC/Design，但不能省略验证说明。

