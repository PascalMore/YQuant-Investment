# Infrastructure Module

基础设施模块。

## 职责

- CI/CD 流水线
- 监控与告警
- 部署管理
- 性能优化
- AI Coding 流水线与多 Agent 工程协作规范

## 目录结构

```text
infra/
├── ai-coding-pipeline/  # YQuant AI Coding 七阶段流水线 AgentSkill
├── cicd/                # CI/CD 配置
├── monitoring/          # 监控告警
├── docker/              # 容器化
└── scripts/             # 运维脚本
```

## AgentSkill

- `ai-coding-pipeline/`：定义 YQuant 非平凡研发任务的 Intake -> RFC/SPEC -> Design -> Implement -> Verify -> Review -> Closeout 七阶段工作流。
- 根级 `AGENTS.md` 只保留启用、路由和安全边界；具体阶段门禁、文档分层和交接格式由该 skill 维护。

## 状态

建设中。
