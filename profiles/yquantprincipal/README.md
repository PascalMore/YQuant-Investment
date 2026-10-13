# yquantprincipal · 仓库化工程角色

YQuant Principal 的正式定义。角色与现有 Hermes profile 一一对应，不新增 Agent 或改变工程路由。

| 文件 | 用途 |
|---|---|
| [SOUL.md](SOUL.md) | 身份、职责、权限边界和工作协议启动入口 |
| [AGENTS.md](AGENTS.md) | 上下文、最小范围纪律、工作与交付规范 |
| [config.example.yaml](config.example.yaml) | 当前非秘密字段快照；不是完整可直接覆盖的运行配置 |
| README.md | 文件归属、部署、验证与回退 |

## 原生加载与配置

- 本机运行目录：`/home/pascal/.hermes/profiles/yquantprincipal`。
- 运行 SOUL 链接到 `/home/pascal/workspace/yquant-investment/profiles/yquantprincipal/SOUL.md`；原生身份加载读取同一正文。
- 项目根 AGENTS 由实际任务工作目录加载；本角色 AGENTS 通过 SOUL 的明确启动要求读取，不声称它自动被 Hermes 注入。
- 模型、fallback、凭据、工具、渠道、记忆、会话和日志仍在原 profile；本次只改变角色正文归属与 SOUL 链接。
- 链接依赖仓库存在；新机器需调整路径，不回退到旧正文。模板只用于按需合并字段，不能覆盖完整配置。
- 不重启 gateway，不调用模型验证，不改变当前正在运行会话的旧提示；原生读取验证只证明新提示构建的加载路径。

## 来源、验证与回退

原 profile SOUL 的身份、工作边界、纪律和交付段按职责分别归入 SOUL/AGENTS；Principal 的已退役身份引用移除。没有新增权限或复制用户资料。

本次原件与验证清单：`/home/pascal/.hermes/profiles/yinglong/backups/engineering-agents-20261013-124605/`。回退前检查后像，不覆盖后续修改；恢复此 profile 原 SOUL 不等于回退项目代码或运行配置。

验证包括四文件/Markdown 链接、原段落保留、模板脱敏、实际配置哈希不变、运行链接、原生 SOUL 加载和工作协议入口可读。没有把未运行模型/工程任务说成已验证。
