# YQuant-Investment · Agent 定义与项目入口

YQuant 是运行在 Hermes Agent 上的量化金融工程师与工程化主控，服务 YQuant-Investment 项目。职责覆盖数据、投研、策略、回测、组合、自动化/策略化/智能化交易、风险、报告与工程协作；列出的领域是职责，不证明具体接口或模块已经部署。

## 投研交易规划入口

- [全局架构](docs/rfc/00_project_overview/RFC-00-001-yquant-investment-global-architecture.md)：模块归属与研究—投资—交易—报告闭环，目前仍为草稿。
- [Trading 框架规划](docs/rfc/07_trading/RFC-26-072-trading-intelligent-trading-framework.md)：交易业务、运行与相邻模块分工，当前为 Draft，不是交易运行授权。
- [Trading 技能入口](skills/trading/SKILL.md)：已建立说明与目录；尚无交易引擎、账户连接、模拟或实盘功能。

## Agent 定义规范 V1

与 Yinglong 使用同一文件职责：SOUL 定身份，AGENTS 定工作规则，配置模板定运行，README 定使用与部署。

| 文件 | 唯一职责 |
|---|---|
| [SOUL.md](SOUL.md) | 身份、使命、心智模型、能力与授权边界 |
| [AGENTS.md](AGENTS.md) | 启动、主控协作、工程规范、验证及现行技能路由 |
| [config.example.yaml](config.example.yaml) | 无秘密的 Hermes 本机运行模板，不是已部署配置 |
| README.md | 导航、部署、验证与回退 |

## 核心工程 Agent

四个现有 Hermes 工程角色的正式定义位于 `profiles/`，每个目录采用 SOUL、AGENTS、config.example、README 四文件。不是新增四个运行实例，不改变当前 AI Coding Pipeline 的角色路由。

| Profile | 职责 | 正式入口 |
|---|---|---|
| `yquantprincipal` | RFC/SPEC/Design、架构、接口、风险与实现计划 | [角色说明](profiles/yquantprincipal/README.md) |
| `yquantdeveloper` | 按已确认需求做最小范围实现 | [角色说明](profiles/yquantdeveloper/README.md) |
| `yquanttester` | 独立验证、回归与证据 | [角色说明](profiles/yquanttester/README.md) |
| `yquantreviewer` | 独立审查、风险和一致性 | [角色说明](profiles/yquantreviewer/README.md) |

角色正文在仓库维护；运行 profile 的 SOUL 链接对应文件。具体模型、fallback、凭据和工具仍以本机配置为准。项目 AGENTS 按任务目录加载，角色 AGENTS 通过角色 SOUL 的明确启动要求读取。

## 其他文件的归属

- [CLAUDE.md](CLAUDE.md)：代码助手的短兼容入口，正式规则在 AGENTS；不再维护第二套正文。
- `skills/`：具体能力和工具方法；`docs/rfc/`、`docs/spec/`、`docs/design/`：工程正式契约。本次不改变 AI Coding Pipeline 的语义或源文件。
- `data/reports/`：验收、验证、评估和调研等结果报告；`data/tasks/`：任务过程与交接记录。具体目录约定见 [AGENTS.md 的报告与过程资料约定](AGENTS.md#报告与过程资料的目录约定)。`data/` 当前不纳入 Git。
- `USER.md`、`MEMORY.md`：私有上下文，本次保持原件不变；分享前单独审计，不能因已 Git 跟踪就认为可公开。
- `TOOLS.md`、`HEARTBEAT.md`：已有本地工具/调度参考，本次不改配置、不搬移正文、不推送；命令和集成状态必须与实际运行核对。敏感本地资料不纳入通用 Agent 发布。
- 密钥、认证、渠道凭据、会话、日志、缓存、数据库和真实交易数据不进入 Agent 定义发布包。

## Hermes 加载与本机部署

- 本机 profile：`/home/pascal/.hermes/profiles/yquant/`；业务工作目录：`/home/pascal/workspace/yquant-investment`。
- profile `SOUL.md` 直接符号链接到项目根 SOUL，原生加载同一正文；项目 AGENTS 由业务工作目录加载。不保存第二份可独立编辑的角色正文。
- `config.yaml`、凭据、渠道、会话与日志保留在 profile；模板不自动加载，不可覆盖完整运行配置。新机器按需合并模板字段并分别设置认证与渠道。
- 链接目标依赖仓库存在；换机器时更新工作目录、技能目录和链接。不可访问时停止，不回退到历史角色正文。
- Windows 原生不支持链接时可使用单向生成的部署文件，但不得在 profile 维护第二份定义。本机 WSL 使用链接。
- 已运行会话的旧提示不会因文件变化自动被证明已刷新；新会话重新构建提示时读取新文件。本次不重启 gateway。
- `scripts/generate_agent_profile.py` 直接读取 SOUL，不依赖旧身份兼容文件；CLAUDE 仅保留代码助手入口。工程流水线语义不变。

## 验证与回退

验收包括四文件、兼容链接、规则保留、无凭据模板、原生 SOUL/项目上下文加载、生成器 fixture 回归及受保护文件哈希。不得用真实生产写入、外发或交易验证定义整理。

2026-10-13 本次迁移持久备份：`/home/pascal/.hermes/profiles/yinglong/backups/agent-definition-unification-20261013-105310/`。包含原件和 manifest；回退前确认没有后续编辑，只恢复列出的对象，不回退其他代码、配置或凭据。
