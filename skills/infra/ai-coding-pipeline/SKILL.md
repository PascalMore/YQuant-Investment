---
name: yquant-ai-coding-pipeline
description: "用于 YQuant 非平凡工程任务的七阶段 AI Coding 流水线：Intake、RFC/SPEC、Design、Implement、Verify、Review、Closeout。"
---

# YQuant AI Coding 流水线

用于 YQuant 的非平凡工程任务，尤其是涉及 RFC/SPEC、设计、代码变更、测试、审查、发布准备、数据模型、API、交易、风控或生产行为的任务。

除非用户明确要求走流水线，否则普通问答、极小拼写修正、只读查询不需要触发本 skill。

## 触发入口

### 显式触发

用户明确提到以下表达时，必须启用完整 AI Coding 流水线：

- “走 AI Coding Pipeline”
- “按流水线执行”
- “按 RFC/SPEC/Design/Implement/Verify/Review/Closeout 流程”
- “先写 RFC/SPEC/Design，再实现”
- “需要独立测试和审查”

### 自动触发

用户没有显式要求，但任务满足以下条件之一时，先向用户确认是否走完整流水线：

- 新增核心功能。
- 对现有功能做非平凡改进、优化、重构、升级。
- 修改架构、数据模型、任务调度、报告生成、投资研究、交易相关逻辑。
- 跨多个模块或多个目录的改动。
- 需要新增或修改 RFC、SPEC、Design 文档。
- 存在较高风险，例如数据正确性、回测结果、外部 API、生产脚本、自动化执行。
- 用户要求“方案评审”“架构设计”“独立 review”“测试验证”。

### 轻量触发

以下任务默认不走完整流水线，除非用户明确要求：

- 文案、注释、README 小改动。
- 对已有功能的小问题修复。
- 不涉及 RFC/SPEC/Design 变更的优化。
- 单文件低风险 bug fix。
- 格式化、路径修正、模板补充。

轻量流程为：

`YQuant Intake -> YQuant-Developer-Engineer Implement -> YQuant-Test-Engineer Verify -> YQuant Closeout`

轻量流程仍必须保留最小 Verify，不能把未验证的实现直接 Closeout。

## 编排顺序

完整流水线固定为：

1. `YQuant`：Intake 需求澄清，确认目标、范围、约束、风险和初步验收标准。
2. `YQuant-Codex-Principal`：RFC/SPEC 编写；当业务语义、接口、数据模型、交易或风控行为发生变化时，先更新相关 RFC，再派生可执行 SPEC。
3. `YQuant-Codex-Principal`：Design 架构设计、详细设计、原型或 UI 设计；定义涉及文件/模块、数据流/控制流、实现顺序、测试、回滚和交接条件。
4. `YQuant-Developer-Engineer`：Implement 代码实现，基于已确认的 SPEC/DESIGN 做最小范围修改。
5. `YQuant-Test-Engineer`：Verify 测试验证，按验收标准独立测试。
6. `YQuant-Reviewer-Principal`：Review 独立审查 diff、测试结果，以及实现与 RFC/SPEC/DESIGN 的一致性。
7. `YQuant`：Closeout 收尾，总结变更、验证结果、残余风险和后续事项。

除非用户明确要求跳过某一步，否则完整流水线不得跳过 Verify 和 Review。

## 强制角色拆分

- Intake 和 Closeout：`YQuant`
- RFC/SPEC/Design：`YQuant-Codex-Principal`，默认模型 `Codex-gpt5.5`
- Implement：`YQuant-Developer-Engineer`，默认模型 `minimax 2.7`
- Verify：`YQuant-Test-Engineer`，默认模型 `minimax 2.7`
- Review：`YQuant-Reviewer-Principal`，默认模型 `Codex-gpt5.5`

除非用户明确覆盖流水线规则，否则 `Implement`、`Verify`、`Review` 必须由不同角色承担。

## 参考资料

只加载当前阶段需要的参考文件：

- `references/pipeline.md`：阶段门禁、任务目录结构、路由规则。
- `references/document-layers.md`：RFC/SPEC/DESIGN 的职责边界。
- `references/agent-handoff.md`：角色交接内容、交付物和退回条件。
