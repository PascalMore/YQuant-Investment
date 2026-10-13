# yquantprincipal · 工作协议

身份、职责与核心授权边界见 [SOUL.md](SOUL.md)。本文件是此角色工作方法与交接规范的正式来源，不复制主控全文或详细工具教程。

## 项目与上下文

- 每次任务先读取本文件和目标项目的 AGENTS，按任务读取相关 SPEC/Design、代码和 skill。
- 任务 `workspace_path` / `$HERMES_KANBAN_WORKSPACE` 与已授权范围优先；无显式任务工作目录时默认 `/home/pascal/workspace/yquant-investment`。服务 Yinglong 时必须遵循其项目约定，不照搬 YQuant 路径或命名。
- 下方既有事实来源清单用于 YQuant 任务；私有 USER/MEMORY/TOOLS 只读取当前任务必要且获准的内容，不复制到角色定义或其他项目。

## 事实来源

处理 YQuant 任务时，优先读取项目目录中的 canonical 文档：

- `/home/pascal/workspace/yquant-investment/AGENTS.md`
- `/home/pascal/workspace/yquant-investment/SOUL.md`
- `/home/pascal/workspace/yquant-investment/CLAUDE.md`
- `/home/pascal/workspace/yquant-investment/USER.md`
- `/home/pascal/workspace/yquant-investment/MEMORY.md`
- `/home/pascal/workspace/yquant-investment/TOOLS.md`

不要维护这些文件的第二份副本。Hermes profile 只保存运行身份和 profile 级状态。

## 最小设计职责

只有需求语义、接口、数据模型、授权边界或副作用范围存在会改变实现的未决项时，才创建 RFC/SPEC/Design 或单独设计阶段。对于对象、动作、范围和验收均已明确的受限任务，应把必要边界直接写入实现任务，不得为了形式完整新增平台、runtime、长期服务或文档阶段。每项新增门禁必须标明既有契约来源及其与本次副作用的直接关系。

## 输出要求

输出必须结论先行，说明假设、决策、方案、风险、验收标准和下一步。
如果进入完整 AI Coding Pipeline，RFC、SPEC、Design 必须分别落在项目规定目录，不能合并。

## 工具与工程路由

- 具体方法引用对应 canonical skill；工具说明仍沿用当前项目来源。本次不拆分、迁移或复制 TOOLS 内容。
- 正式工程阶段继续使用共享 AI Coding Pipeline 的当前契约与既有 assignee，不修改阶段、门禁或调度逻辑。
- 模型、fallback、工具和渠道以本机 profile/config.yaml 为准；config.example.yaml 只是脱敏模板，不自动启用能力。
- 根 IDENTITY 已退休，身份来源为 SOUL，不按历史目录清单重新创建旧身份文件。

## 定义维护

此目录核心四文件：SOUL、AGENTS、config.example、README。角色正文只在仓库维护；profile 的 SOUL 为运行链接。重要职责/边界变更需明确授权、版本记录和验证，不能借文件归位改变职责。
