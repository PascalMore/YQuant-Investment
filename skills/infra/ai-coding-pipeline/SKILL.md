---
name: yquant-ai-coding-pipeline
description: "YQuant / 应龙共享 AI Coding 流水线：Full 或 Light，两者均由独立 Validate 完成测试、反例审查和验收裁定。"
---

# AI Coding 流水线（YQuant / 应龙共享）

用于 YQuant 或应龙项目的非平凡工程任务，尤其是涉及 RFC/SPEC、设计、代码变更、测试、审查、发布准备、数据模型、API、交易、风控或生产行为的任务。

除非用户明确要求走流水线，否则普通问答、极小拼写修正、只读查询不需要触发本 skill。

## 现行契约（2026-11-14，仅适用于后续新任务）
- 现行模式只有 Full / Light。Quick 入口与专用强制规则退役；用户再说 Quick 时，按契约明确程度与风险重新分流：范围、行为和验收已明确且风险可控走 Light，否则走 Full，不按文件数量机械划档。
- Full：Intake → RFC/SPEC → Design → Implement → Validate → Closeout。RFC、SPEC、Design 保留三个独立文件；RFC/SPEC 与 Design 保留两个阶段，不合并为 Plan。
- Light：Intake → Implement → Validate → Closeout。受限任务把已有契约与验收直接写入 body，不为了形式新增三层文档。
- 两者共用下方「统一 Validate」；Intake / Closeout 由主控处理，默认不单独建卡。tester 仅用于旧任务兼容或必要专项，不新增、删除或改名 profile。
- 已创建的旧任务按原契约执行，不自动迁移。本文明确标为历史的段落只保留事故事实，不是新任务指令；不得据其重启 Quick 或执行旧事故配方。
- Kanban 是唯一任务状态源；新任务的目标、范围、计划、负责人、依赖、进度、状态与交接摘要只在 Kanban 管理，不创建或维护 `data/tasks/` 管理档案、pipeline-state.md、body 镜像、逐卡全文 handoff 或重复 Closeout 报告。小任务用 Kanban 结论与必要日志；复杂任务保留一份验收报告和原始证据，报告及必要证据目录沿用目标项目 AGENTS（YQuant 为 `data/reports/YYYY-MM-DD-short-topic/`）。临时探针与中间文件使用当前 profile scratch，不作为第二状态源或任务正文档案；既有 `data/tasks/` 与证据按旧任务原契约保留，不自动删除、迁移、改写或批量归档。

### 统一 Validate（Full / Light 共用） <a id="unified-validate"></a>
默认 `assignee="yquantreviewer"`，独立于实现者；同时负责必要实际测试、真实消费者路径与反例审查、契约/范围/数据合理性核对，最终给出 PASS 或 REVISE。

- 按变更影响选择定向、集成或端到端测试；文档任务执行静态检查，不伪称业务 E2E。产出数据的任务需用真实用户输入检查真实路径和输出合理性；缺权限/环境时明确缺口，不以 fixture 替代真实验证结论。
- 开发者自测不替代独立 Validate。主控核对覆盖与结论，不第三遍全量跑；不为报告或日志整理重复执行。
- 记录候选身份（HEAD + 工作树文件清单或 hash）、命令/exit、覆盖与未验证项。既有独立证据仅在候选、输入、依赖和运行条件仍适用时复用；变动后补跑受影响部分。未测不得称 PASS。
- 发现缺陷退回 Implement 并给最小修复、file:line/行为证据；不得改业务实现后自签通过。未满足必需验收或授权时不能 done。
- 完成本阶段且有预建下游时 `kanban_complete(summary=..., metadata=...)` 释放下游；仅需同卡 review 时 `kanban_request_review`，真实外部阻塞用 `kanban_block`。不因存在下游而 block，不按固定时间盲目 unblock。
- 预算中断先核对已落盘候选与证据：只缺登记则补登记，不重跑；真实验证未完成则记录缺项后续接，不能补写 PASS。

### 授权不随流程简化
生产 DB / schema、真实或模拟交易执行、交易配置、外部消息、长期调度、凭据、依赖升级及大范围重构仍服从项目明确授权边界。卡面授权不等于 runtime 允许，runtime 允许也不等于卡面授权。安全拒绝后停止相关动作，不换工具或路径绕行；只改配置常量不自动触发架构工程，但不免除对应授权及独立 Validate。

## 配套 skill：sanity-check
实现类 worker 在写以下代码时，应当额外加载 `sanity-check` skill（`skills/infra/sanity-check/`）以复用 6 个标准模板：

- CLI 参数 / argparse 新参数 → `interface_arg_check`
- 文件 / 目录读写路径 → `file_existence_check`
- 字符串 → 数值 / 布尔 / 日期转换 → `type_coercion_check`
- `position_date` / `nav_date` / `trade_date` 等 YYYY-MM-DD 字段 → `date_format_check`
- 升级 / auto-push / 仓库操作前置条件 → `git_state_check`
- MongoDB 连接 / database / collection 边界 → `mongo_connection_check`

sanity-check 关注的是「数据流入业务逻辑之前的最后一道闸门」。它与本文档的「P-1~P-13 Pitfalls」**正交**——P-* 描述的是流水线机制坑（worker crash、fallback 透明、parent link 断链等），不会被吸收或替代。两套指引并行生效，需要同时遵守。

## 配套 skill：文档治理三件套（2026-08-21 迁移）
以下三个 skill 是 AI Coding Pipeline 在 RFC / SPEC / Design 文档治理环节的**深度配套**——sanity-check 关注代码层 fail-fast，三件套关注文档层契约收敛。worker 可在对应阶段按需 `skill_view()` 加载，不强制注入：

- `skills/infra/design-gate-audit` —— 在 Full 的 T2 Design 完成、T3 Implement 创建**之前**使用：审计阶段边界、文件范围、可计算契约。适用于含评分、阈值、存储方案、公开 trace 或生产副作用门禁的设计。
- `skills/infra/pipeline-doc-consistency` —— 在 RFC/SPEC/Design 三件套**已存在且用户提出后续决策变更**时使用：跨文档同步治理、统一审查、实现就绪度检查。
- `skills/infra/design-baseline-reconciliation` —— 在已有实现、修复链或并行卡**之后**对 RFC/SPEC/Design 做修订或 Design Gate 审计时使用：把"已完成能力"和"待实现能力"边界画清，避免文档漂移。

三件套与本 SKILL 的关系**正交**：本 SKILL 描述流水线机制（dispatcher / parent links / Pitfalls），三件套描述文档契约收敛方法论。任何一方都不能替代另一方；流水线中遇到文档治理难题时优先 `skill_view('design-gate-audit')` / `pipeline-doc-consistency` / `design-baseline-reconciliation` 按上下文选择加载。

## Hermes 执行模型
本流水线在 Hermes 中使用 **Kanban profile worker** 执行。

- 本 skill 的源代码、参考文档和维护入口在项目内：`/home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/`；配套恢复技能的唯一维护源同在项目：[修复链恢复](../yquant-kanban-repair-orchestration/SKILL.md#current-rules)、[预算恢复](../worker-budget-recovery/SKILL.md#current-rules)，不维护 profile 同名副本。
- 不再维护 `~/.hermes/profiles/*/skills/infra/yquant-ai-coding-pipeline/` 运行态副本；长期修改只落到项目源目录，worker 通过 `workspace_path` 发现项目源 skill。
- 运行态 profile 的模型、fallback、toolsets 等易变配置仍以 `~/.hermes/profiles/<profile>/config.yaml` 为准，项目内只保存路由语义、阶段门禁和可复用 skill 逻辑。
- 当前入口 profile 是 orchestrator，负责 Intake、解析目标工作目录、创建 Kanban 任务、校验阶段门禁和 Closeout。
- 阶段执行必须通过 `kanban_create` 创建真实任务，并设置 `assignee` 为对应 Hermes profile。
- `kanban_create(skills=[...])` 只能引用目标 assignee profile 可见的 **canonical/project skill**。不要把 orchestrator 自己 profile-local 的补丁 skill 传给 worker；worker CLI 会在初始化阶段报 `Unknown skill(s)` 并立即 crash，连 `agent.turn_context` 都不会进入。
- 不要用 `delegate_task` 承担正式流水线阶段；`delegate_task` 只适合短推理子任务，且默认继承父 profile 的模型，不能按单次调用切到 `yquantprincipal` / `yquantdeveloper` 等 profile。
- **历史教训（2026-06-25 RFC-03-006 案例）**：`delegate_task` **不在 Kanban DB 创建 task 记录**，会导致后续阶段 `parents=[前阶段 task_id]` 无法设置，pipeline 自动串联中断。所有流水线阶段必须用 `kanban_create` 派任务，每个阶段设置 `parents`，dispatcher 才能自动 promote。详见 `references/real-run-journal-2026-06-25.md` 关键观察 6。
- **SPEC §3 文件清单必须精确到目录层级**（2026-06-25 教训）：不能写“新建 `providers/` 子包”这种模糊描述，要写“在 `scripts/extractors/providers/` 下新建 10 个文件”。否则 Implement worker 可能写到错的目录层级。详见 `references/real-run-journal-2026-06-25.md` 关键观察 7。
- 不要只在文本中声明“委派给某 Agent”；没有 `kanban_create` 任务就不算真实委派。
- 任务工作目录必须使用下面“项目上下文解析”得到的共享项目目录；禁止 worker 根据自身 profile 名推断项目。

### 项目上下文解析
Intake 开始时必须根据当前 orchestrator profile 解析一次 `PIPELINE_WORKSPACE`：

| Orchestrator profile | `PIPELINE_WORKSPACE` | 项目名称 |
|---|---|---|
| `yquant` | `/home/pascal/workspace/yquant-investment` | YQuant |
| `yinglong` | `/home/pascal/workspace/yq-yinglong` | 应龙 |

- 只允许上述两个映射；无法确认当前 orchestrator 时必须停止并向用户确认。
- 同一条流水线从 Intake 到 Closeout 必须保持同一个 `PIPELINE_WORKSPACE`。
- 每个 `kanban_create` 都必须显式设置 `workspace_kind="dir"` 和解析后的绝对 `workspace_path`。
- 任务正文必须同时写明目标项目绝对路径，并禁止修改另一个项目。
- worker 以任务传入的 `workspace_path` / `$HERMES_KANBAN_WORKSPACE` 为准，不重新解析 orchestrator。

### 项目约定发现与任务正文固化
Pipeline 是跨项目基础设施，但每个项目的文档目录、模块编号、skill/module 命名、持久化规范和凭据位置可能不同。**Intake 在派第一个 worker 前必须发现并固化目标项目约定**，不能把 YQuant 的目录约定照搬到其他项目。

最低发现步骤：
```bash
cd "$PIPELINE_WORKSPACE"
find docs -maxdepth 3 -type f -name 'README.md' -o -name '*-00-000-*template*.md' 2>/dev/null
find skills -maxdepth 3 -name SKILL.md 2>/dev/null | head -80
find config -maxdepth 2 -type f 2>/dev/null | sort
```

Intake 必须把以下内容写进**每个文档类任务（RFC/SPEC/Design）的 body**，不要只放在 README 或 skill 里：

- 目标项目绝对路径与禁止修改的外部项目路径。
- 文档目录命名规则：`docs/{rfc,spec,design}/...` 的具体子目录。
- 文档文件命名规则：`{TYPE}-{NN}-{XXX}-{short-name}.md` 或目标项目实际规则。
- 本任务交付物的**精确目标路径**，至少给 1 个完整示例。
- 项目私有约束（数据库集合前缀、隐私分级、外部 API mock/real 模式、凭据文件位置等）。

**原则**：worker 优先读 task body；README、模板和 skill 是参考材料，不保证被 worker 主动打开。凡是会影响路径、命名、数据契约或安全边界的约定，都必须在 task body 中显式出现。

### Hermes Profile 路由
| 阶段 | Hermes assignee profile | 职责 |
|------|--------------------------|------|
| Intake / Closeout | 当前 orchestrator：`yquant` 或 `yinglong` | 需求澄清、编排、阶段门禁、最终交付 |
| RFC / SPEC / Design | `yquantprincipal` | RFC/SPEC/Design、架构、接口、数据模型、风险评估 |
| Implement | `yquantdeveloper` | 按 Full 的 SPEC/Design 或 Light 已确认契约做最小实现 |
| Validate | `yquantreviewer` | 独立测试、真实消费者/反例审查、通过/退回裁定 |
| 测试专项（非默认） | `yquanttester` | 旧任务兼容或明确指派的测试专项 |

### 源目录与运行态同步
AI Coding Pipeline skill 的 **canonical source 只有项目源目录一份**：
```text
/home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/
```

修改 AI Coding Pipeline 时，只改项目源目录。不要再维护 `~/.hermes/profiles/*/skills/infra/yquant-ai-coding-pipeline/` 运行态副本；否则项目源和 profile 副本会再次漂移，并触发或掩盖 skill collision 问题。

清理 profile 副本：
```bash
rm -rf /home/pascal/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline
for p in yquantprincipal yquantdeveloper yquanttester yquantreviewer; do
  rm -rf "/home/pascal/.hermes/profiles/$p/skills/infra/yquant-ai-coding-pipeline"
done
```

**不要把 worker profile（principal/developer/tester/reviewer）的 skill 副本留下**——它们和项目目录的同名 skill 会触发 **Skill name collision**，worker 启动后立刻 crash（exit 1）且不会进入对话循环。

正确策略（2026-06-28 更新）：
- `yquant` 主 profile：**不保留副本**，通过 YQuant 项目 external skills 目录加载本源文件。
- `yinglong` 主 profile：**不保留副本**，`skills.external_dirs` 直接加载本 canonical skill 目录。
- 4 个 worker profile（principal/developer/tester/reviewer）：**不要放副本**，通过 `workspace_path` 发现项目源目录。

部署后立即验证（应该只看到项目源目录一份）：
```bash
find /home/pascal/.hermes/profiles /home/pascal/workspace/yquant-investment \
  -name "SKILL.md" -path "*ai-coding-pipeline*"
```

### Kanban 创建规则
#### 墙钟上限 `--max-runtime`（每张卡必填，2026-11-06 Pascal 拍板） <a id="runtime-limits"></a>
`agent.max_turns` 管的是轮数，各 profile 统一为 150，修改方式见 `config.yaml`。`--max-runtime` 管的是墙钟时间，**没有默认值**：不传就不设上限，dispatcher 只对设了值的卡执行超时终止。超时后，dispatcher 先 SIGTERM，再 SIGKILL，然后把卡重新排队。因此，每次 `hermes kanban create` / `kanban_create` 都**必须**显式传入：

| 阶段 / assignee | `--max-runtime` | `--max-retries` |
|---|---|---|
| RFC/SPEC、Design（`yquantprincipal`） | `60m` | `1` |
| Implement（`yquantdeveloper`） | `75m` | `1` |
| Validate（`yquantreviewer`） | `60m` | `1` |
| 旧任务/测试专项（`yquanttester`，非默认） | `45m` | `1` |
| 主控明确代执行的行政卡（非默认 Closeout worker） | `30m` | `1` |

- 默认值依据 2026-09 以来已完成 run 的实际时长：各角色 p95 都不超过 37 分钟（reviewer 37.0、principal 25.2、developer 21.6、tester 17.4）。默认值是 p95 的 1.6–3.5 倍，绝大多数卡不会被误杀。历史上最长的几次超过了默认值（principal 74.5、reviewer 70.4），这类长任务应在 body 里写明理由并调大上限。过去出现过 20 次 `elapsed > limit`，原因都是当时手填的 10–30 分钟太紧。
- 只在两种情况下偏离默认值：
  - 卡片 body 写明了理由，例如"长回测轮询""大批量迁移"，可以调大；
  - 范围很窄的续接卡或行政卡，可以调小，例如 `20m`。
- 偏离默认值时，必须在 body 里写明实际值和原因。
- 超时属于 dispatcher 的调度事实，不等于工作失败。恢复处理按 [worker-budget-recovery](../worker-budget-recovery/SKILL.md#current-rules)：先看已落盘的产物，再决定是行政收尾还是收窄后续接，不要盲目重跑。

完整流程必须创建依赖链（依次取得真实 task id 再创建下游，禁止占位 parent）：
```text
T1 RFC/SPEC       assignee=yquantprincipal
T2 Design         assignee=yquantprincipal   parents=[T1]
T3 Implement      assignee=yquantdeveloper   parents=[T2]
T4 Validate       assignee=yquantreviewer    parents=[T3]
```

轻量流程必须创建依赖链：
```text
T1 Implement      assignee=yquantdeveloper
T2 Validate       assignee=yquantreviewer    parents=[T1]
```

下文 T1/T2/T3 等阶段编号均按上述对应模式的任务图解释；文档规划与决策同步段中的 RFC/SPEC、Design、Implement 编号指 Full，历史事故中的编号仅指当时任务。

### 实现期小问题：最小化修复与验证
默认目标是以**完成当前工作所需的最少步骤**收束，而不是为小问题附加完整流程。

- **小型代码或测试问题**：根因明确、范围局限、低风险且在当前 allowlist 内时，在同一张 Implement 卡修复并运行受影响的定向测试或最小复现；沿用既有独立 Validate，不另起设计或多层流水线。
- **小型、可逆的本地写入或元数据修正**：对象、动作和范围明确时，在当前 Implement 卡写入并立即读回/定向核验；沿用独立 Validate，不因“发生写入”额外增加验收阶段或复杂门禁。
- 除统一 Validate 外，只有现有契约或用户要求才增加额外设计或专项卡；不得把“更安全”的自行建议包装成必经步骤。

需要额外设计时，应说明尚未冻结的契约或不可替代的技术前提；敏感数据、外部发送、资金/账户安全、批量或不可逆写入仍取得对应授权与最少保护，不因风险关键词机械扩展成完整工程。

**真实写入也默认最小化**：对对象、动作、范围已明确的小型本地写入或知识库元数据修正，采用“当前 Implement 卡执行 → 立即读回/定向核验”，随后沿用统一独立 Validate；不默认要求 fresh 零写 preflight、一次性 token、额外验收阶段或 Activation 卡。只有删除/覆盖不可恢复数据、外部发送、资金或账户安全、敏感/隐私数据、批量影响，或现有契约明确要求时，才按该风险取得明确授权并增加对应的最少保护。写入结果不明或核验失败时 STOP，不自动重试。

### 三层 scope 纪律（Pascal 2026-09-01 多次纠正）
编辑 AI Coding Pipeline 或同级共享规则时，必须按以下三层审查每一行新增内容，**且前两层只能由现有契约或用户要求触发**：

1. **现有契约明确要求**（可直接落地）：来自已冻结且现行生效的 RFC / SPEC / Design；10-004 的旧 Quick SPEC §13.x 已退役，不能作为现行授权来源。
2. **当前目标直接必要**（可作为必经门禁）：来自当前 task 的验收 / 风险 / 用户已声明需求。
3. **Agent 自行推导的“更安全”建议**（**禁止包装为必经门禁**）：来自“万一出错/万一误用”等防御性假设。

只把 1 + 2 列入正式条款；3 只能写入实现正文或边界说明，**不得进入升级门禁**。升级门禁历史经验上会被反复反转（Pascal 在 2026-09-01 同一会话内连续两次从升级清单中删除“跨模块行为变化”和“权限/授权模型变化”两项）——任何看似“必备”的升级条件都应先质疑是否属于第 3 类。

### 共享规则改后必须去重（canonical 单一源守则）
当修改任意**跨 session 共享**的规则条款时，在本次获授权路径内定向检索 canonical skill、references、相关正式文档和角色说明，确认无同时生效的冲突。历史实例/日志不批量清理，明确非生效即可；发现范围外副本只报告主控，不扩权读取私有 session/记忆或删除其他项目/profile 内容。

共享源仍只有本项目 canonical 目录；配套文档可引用同一契约，不能以“多处字符串命中”为由删历史、删必要路由或跨项目清理。runtime 副本治理需要单独明确授权，不是本次规则修订的执行步骤。

每个 `kanban_create` 的 body 必须包含：
- 本卡的 `--max-runtime` 取值。按上文"墙钟上限"表的默认值；偏离默认值时写明原因。
- 用户目标和当前阶段。
- 相关文件、目录、RFC/SPEC/DESIGN 路径。
- 允许修改的范围和禁止事项。
- 明确交付物。
- 验收标准。
- 需要运行的测试或可接受的替代验证。
- 输出语言要求：中文。
- 命令与工具必须同时符合卡面授权和 runtime 限制；安全拒绝后停止相关动作，不换工具/路径重放。临时探针仅用当前 profile scratch；不读取或输出秘密，不要求无人值守 worker 执行需交互审批的动作。

Orchestrator 创建任务后必须向用户说明目标项目、任务图、任务 ID、assignee、依赖关系和如何追踪状态。

## 触发入口
### 显式触发
用户明确提到以下表达时，必须启用完整 AI Coding 流水线：

- “走 AI Coding Pipeline”
- “按流水线执行”
- “按 RFC/SPEC/Design/Implement/Validate/Closeout 流程”（旧 Verify/Review 术语映射为统一 Validate，不恢复旧默认链）
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
`Orchestrator Intake -> YQuant-Developer-Engineer Implement -> YQuant-Reviewer-Principal Validate -> Orchestrator Closeout`

轻量流程仍必须保留独立 Validate，不能把未验证的实现直接 Closeout。

## 编排顺序：Full Flow
完整流水线固定为：
1. 当前 orchestrator（`yquant` 或 `yinglong`）：Intake 需求澄清，解析并固定 `PIPELINE_WORKSPACE`，确认目标、范围、约束、风险和初步验收标准。
2. `YQuant-Codex-Principal`：RFC/SPEC 编写；当业务语义、接口、数据模型、交易或风控行为发生变化时，先更新相关 RFC，再派生可执行 SPEC。
   - **门禁**：Orchestrator 在此阶段结束后必须校验目标项目 `docs/rfc/` 和 `docs/spec/` 下有对应文件，否则退回。
3. `YQuant-Codex-Principal`：Design 架构设计、详细设计、原型或 UI 设计；定义涉及文件/模块、数据流/控制流、实现顺序、测试、回滚和交接条件。
   - **门禁**：Orchestrator 在此阶段结束后必须校验目标项目 `docs/design/` 下有对应文件，否则退回。
4. `YQuant-Developer-Engineer`：Implement 代码实现，基于已确认的 SPEC/DESIGN 做最小范围修改。
5. `YQuant-Reviewer-Principal`：Validate，按统一规则独立执行必要测试，审查真实消费者、反例及实现与 RFC/SPEC/Design 的一致性，给出通过/退回裁定。
6. 当前 orchestrator：Closeout，总结变更、验收结果、残余风险和后续事项，不另建默认 worker。

完整流程不得跳过独立 Validate；用户明确的本次阶段例外不推广为默认规则。

## 两流程定位（Full / Light）
按契约明确程度与风险分流，不按文件数；后续新任务只选择以下两种：

| 流程 | 阶段数 | 默认 worker 卡数 | 适用场景 | 三层文档 | 独立验收 |
|---|---|---|---|---|---|
| Full | 6 | 4 | 需先澄清/冻结语义、架构、接口或风险 | RFC + SPEC + Design，RFC/SPEC 与 Design 分阶段 | 统一 Validate |
| Light | 4 | 2 | 契约明确、范围受限、风险可控 | 不为形式新增 | 统一 Validate |

原 Quick 需求按本表去往 Light 或 Full；旧链不自动重排。详见 [阶段参考](references/pipeline.md)。

Full / Light 均使用真实 parent links 自动衔接，不以主控持续在线或通知回调代替依赖。

## 生产部署/上线/模式切换：最小范围
只修改已明确的配置常量时不自动升成大工程；按契约明确程度选择 Light 或 Full，仍保留独立 Validate 和项目要求的授权。小型明确本地写入沿用当前 Implement 执行后立即读回/定向核验，不默认新增 preflight/token/Activation 卡。

历史：[2026-08-19 部署分流准则](references/history/deployment-routing-2026-08-19.md) 已退役，仅供审计，非当前指令、无新任务必读要求。

历史：[Quick Flow V1.2 编排、触发与门禁](references/history/quick-flow-v1.2-rules.md) 已退役，仅供审计，非当前指令、无新任务必读要求。

## Orchestrator 主动推进规则
- Intake 完成分流后，按顺序创建真实任务并保存返回 id，再用该 id 创建下游；不等待上游 done 才补依赖，也不使用占位 parent。Full 的文档阶段门禁写入对应任务验收，未通过不得完成该阶段。
- 通过 `kanban_show` 核对 exact task 的 parents、状态与产物；已有下游由 dispatcher 按真实依赖推进，不重复派卡。没有预建下游时补齐合法任务，不盲目 unblock。
- Validate PASS 后主控直接 Closeout，核对结论/覆盖/风险，不另建默认 Closeout worker 或重复全量测试。
- REVISE 给明确缺陷与最小修复，回 Implement 后再独立 Validate；超出现有授权的范围、成本或高风险动作先取得用户决定。用户不继续时明确未完成项，不宣称 PASS。
- 安全拒绝、缺授权或必要环境等真实阻塞保留 blocked；已通过且不阻塞的残余风险进入 summary/metadata。只缺登记的预算中断补登记，不能重跑或伪造结论。

历史：[2026-06/07 主动推进 SOP](references/history/orchestrator-push-sop-2026-06-07.md) 已退役，仅供审计，非当前指令、无新任务必读要求。

### 三层文档强制规则
Full 中 RFC、SPEC、Design **必须分别产出独立文件**，存放在各自目录下；RFC/SPEC 与 Design 分阶段。不允许将 SPEC 或 Design 内容合并到 RFC 中；Light 不为形式新增三层文档。详细规则见 `references/document-layers.md`。

## 阶段决策同步门禁（用户决策变更时）
**核心原则**：**用户决策在 T1/T2 阶段拍板后，编排层（orchestrator）必须在 T3 Implement 派发前，把这些决策同步到对应阶段的产出物中**。任何 T1/T2 完成后的用户决策变更，必须先评估"是否需要回头修订 T1/T2 文档"，再决定是否放行 T3。

### 判定规则
**问：这条决策是否会让已完成的 RFC / SPEC / Design 章节"不准确"或"遗漏关键设计"？**

- **是** → 触发同步门禁（按下面的处理流程）
- **否** → 直接写进 T3 body（或下一阶段 body），不回头修订

### 决策类型 → 影响范围 → 同步策略
| 决策类型 | 典型例子 | 影响范围 | 必须在 T3 派发前同步到 |
|---|---|---|---|
| **设计类** | 用什么数据库 / 集合命名规范 / 隐私分级模型 / 三方凭据占位 | RFC + SPEC + Design | T1 body（派发时），或 T1/T2 完成后用 `kanban_comment` 同步 |
| **架构类** | 1+N Skill 拆分 / 文件清单 / 阶段门禁 / 模块边界 | SPEC + Design | T2 body（派发时），或 T2 完成后补 `Design §3.x` 章节 + `kanban_comment` |
| **细节类** | CLI 参数命名 / 配置默认值 / 错误码文案 / 函数名 | Design | T3 body 内"实现约束"段；不回头修订 T1/T2 |

### 同步处理流程（编排层责任）
```
用户提决策
   ↓
[决策分类判断] 问：这条决策会不会让已完成的 RFC/SPEC/Design 章节"不准确"？
   ↓
  是 → 同步门禁触发：
       1. 找出该决策影响的所有已完成阶段（T1 已 done？T2 已 done？）
       2. 若 T1/T2 仍在跑：用 `kanban_comment` 通知 worker（"已采纳新决策：xxx，请在文档中体现"）
       3. 若 T1/T2 已 done：编排层直接补章节（patch 文档），并在下一阶段 body 顶部声明"前置决策增补：见 [path]#[section]"
       4. 后续阶段：必须等 T1/T2 补完后才能派发
   ↓
  否 → 直接写进 T3 body，不回头
   ↓
[同步完成后] 才能派 T3（Implement 阶段）
```

### 与 P-1~P-5 的关系
- 这是**编排层行为**的规则，不是 worker 行为——worker 不需要主动检查"用户决策是否同步过"
- 但 worker **必须**在开始工作前 read 编排层的 comment（"前置决策增补"），把这些决策作为输入
- 与 P-5（worker blocked 卡住）正交：P-5 是状态机问题，本规则是"决策追溯"问题

### 历史教训（2026-06-28 应龙 RFC-16-001 案例）

**症状**：T1 worker 在 10:03 done，T2 worker 在 10:24 done。期间用户在 10:30 提出"应龙要有专属 MongoDB，集合名加编号前缀"——这是**设计类决策**，影响 RFC §5 架构、SPEC §4.4 配置、Design §3.x 文件清单。编排层在 T3 派发前**未回头补 T1/T2**，只是把"必须用 yinglong-db"写进 T3 body。结果 T2 Design 文档里 0 次出现 "yinglong/mongo/16_travel_/持有化" 关键词，T5 Review 时会找不到"为什么这样设计"的依据。

**修复（本次）**：
- T2 Design 由编排层直接补 §3.8 持有化层（8 个子节）
- T3 comment 显式引用 §3.8 章节作为设计依据

**预防**：本节规则要求，**任何 T1/T2 完成后的用户决策，必须先回头补 T1/T2 文档，再放行 T3**。

## 文档模板变更守则（2026-06-28 新增）

**核心原则**：**文档模板（RFC/SPEC/Design 模板、3 层 README 模板）属于"全局规约源"，所有项目和所有 worker 都会引用**。模板章节结构的变更必须由 `yquantprincipal` 拍板；编排层（orchestrator）不能直接改。

### 适用文件清单

| 文件 | 路径 |
|---|---|
| RFC 模板 | `docs/rfc/RFC-00-000-rfc-template.md` |
| SPEC 模板 | `docs/spec/SPEC-00-000-spec-template.md` |
| DESIGN 模板 | `docs/design/DESIGN-00-000-design-template.md` |
| 3 层 README | `docs/{rfc,spec,design}/README.md` |

### 变更流程

1. **编排层**发现自己需要改模板时 → **不**直接 `patch` / `write_file` 改
2. **派 Kanban 任务**给 `yquantprincipal`，priority 设为高（如 7），body 写明：
   - 触发原因（哪个流水线/案例暴露了模板缺陷）
   - 建议章节（可选，作为初稿）
   - 明确"可重写"，不要把编排层初稿当定稿
3. **principal 改完后**，编排层需要 `cp` 同步到其他项目（yinglong、yquant 等）的对应路径
4. 任何 `kanban_create` 任务**禁止** body 写"直接 patch <template_path>"——只能写"找 principal 走模板变更流程"

### 编排层可以改的文件

| 可以改 | 不可以改 |
|---|---|
| 某个 RFC-16-001 / SPEC-16-001 / DESIGN-16-001 **具体文档** | 文档**模板**（RFC-00-000 / SPEC-00-000 / DESIGN-00-000） |
| 某个 skill 自己的 SKILL.md | ai-coding-pipeline SKILL.md（只能由 principal 改） |
| 某个具体数据（如某 trip 的 final.md） | 全局配置（`config/*.yaml`） |
| `data/<某 trip>/` 临时产物 | 3 层 README 模板 |

### 历史教训（2026-06-28 应龙 RFC-16-001 案例）

**症状**：T1/T2 完成后用户提"应龙要有专属 MongoDB"，编排层在 T2 Design 已 done 之后**直接 patch 3 个文档模板**（RFC/SPEC/DESIGN），给模板加"持久化"章节。补丁里 RFC 模板的"- 异常降级分支"行被误删，需 `git checkout` 撤回。

**根因**：编排层越界。模板是跨项目、跨 worker 的"规约源"，应当由架构师角色（principal）拍板，编排层只负责"用模板"，不应"改模板"。

**预防**：本守则 + P-7 pitfall + 任何模板变更必须派 principal 任务。

## 强制角色拆分

| 阶段 | Agent | Profile 配置 |
|------|-------|--------------|
| Intake / Closeout | 当前 orchestrator | `~/.hermes/profiles/yquant/config.yaml` 或 `~/.hermes/profiles/yinglong/config.yaml` |
| RFC / SPEC / Design | YQuant-Codex-Principal | `~/.hermes/profiles/yquantprincipal/config.yaml` |
| Implement | YQuant-Developer-Engineer | `~/.hermes/profiles/yquantdeveloper/config.yaml` |
| Validate | YQuant-Reviewer-Principal | `~/.hermes/profiles/yquantreviewer/config.yaml` |
| 旧任务/测试专项（非默认） | YQuant-Test-Engineer | `~/.hermes/profiles/yquanttester/config.yaml` |

**模型与 fallback 不写在本 skill 里**——它们是易变事实，每次模型升级都会变化。查询当前实际配置：

```bash
python3 skills/common/utils/print_agent_models.py
```

> ✅ **原则：升级模型时只改 `config.yaml`，skill 不动。** 改完跑一次上面的脚本自检，确认输出与你的预期一致。

`Implement` 与 `Validate` 必须由不同角色承担；同一份统一 Validate 同时包含测试验证与审查裁定，不拆回默认 Verify→Review 链。

## 运行态自检

开始流水线前，orchestrator 必须确认：

- 当前 orchestrator（`yquant` 或 `yinglong`）已启用 `kanban` toolset。
- Hermes gateway 正在运行；否则 Kanban ready task 不会自动派发。
- 目标 assignee profile 存在：`yquantprincipal`、`yquantdeveloper`、`yquanttester`、`yquantreviewer`。
- `~/.hermes/kanban.db` 能记录任务；若任务没有进入 `tasks` 表，说明没有真实委派。
- **只保留项目源目录的 skill，4 个 worker profile 不放同名副本**（避免 Skill name collision 导致 worker 启动崩溃）。

验证命令：

```bash
python3 skills/common/utils/print_agent_models.py
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect('/home/pascal/.hermes/kanban.db')
print(conn.execute('select count(*) from tasks').fetchone()[0])
PY
```

## Pitfalls（2026-06-25 / 06-28 实跑后补）

### P-1: Skill name collision 让 worker 永远进不了对话循环

**症状**：dispatcher 60s 内 spawn worker，子进程立即 crash（exit 1），task 状态先 `running` 再 `crashed`，连续两次失败后进入 `blocked` + `gave_up`。`agent.log` 末尾只有：

```
WARNING tools.skills_tool: Skill name collision for '...': 2 candidates — <path-a>; <path-b>
```

**没有 `agent.turn_context` 日志**，意味着 worker 从未进入对话循环。

**根因**：worker 的 `HERMES_HOME` 指向 `~/.hermes/profiles/<worker>/`，但同时也通过 `workspace_path` 看到项目目录里的同名 skill。两个候选被 Hermes 视为冲突，启动时直接退出。

**修复**：删除 4 个 worker profile（`yquantprincipal/developer/tester/reviewer`）的 `skills/infra/yquant-ai-coding-pipeline/` 副本，只保留项目源目录这一份。worker 通过 workspace discovery 自动加载。

**预防**：流水线部署完成后立即跑一次 `find ~/.hermes/profiles -name "SKILL.md" -path "*yquant-ai-coding-pipeline*"`——应该看不到任何 profile 副本；全局检查只应看到项目源目录一份。

### P-1b: `kanban_create(skills=...)` 引用 profile-local skill 会让 worker 初始化失败

**症状**：worker 进程启动后数秒内 crash，task 连续失败后 `blocked/gave_up`。目标 profile 单独 smoke test 成功，但带 `--skills <some-skill>` 后立即退出：

```text
Error: Unknown skill(s): <skill-name>
```

**根因**：`kanban_create(skills=[...])` 是由目标 assignee profile 的 Hermes CLI 解析，不是由 orchestrator 解析。orchestrator 自己可见的 profile-local skill（例如只在当前 profile `~/.hermes/profiles/<orchestrator>/skills/` 下）对 `yquantprincipal` / `yquantdeveloper` 等 worker 不可见。

**修复**：
- 不要把 orchestrator profile-local skill 放进 `skills=[...]`。
- 若内容对流程通用，提升到 canonical project skill（本文件或项目源目录）并删除 profile-local 副本。
- 若内容只是项目私有约束，把它写进 task body；worker 不需要加载该 skill 也能执行。

**诊断命令**：

```bash
hermes -p <assignee> chat -q '只回复 OK'
hermes -p <assignee> chat --skills <skill-a>,<skill-b> -q '只回复 OK'
```

第一条成功、第二条失败时，优先检查 `skills=[...]` 中是否有 worker 不可见的 profile-local skill。

### P-1c: worker profile `external_dirs` 必须覆盖目标项目 skills 目录（2026-07-01 实测） <a id="p-1c"></a>

**症状**（yinglong 5 阶段 4 task 实跑）：worker 进程在 `plugin discovery` 完成后**静默死掉**，无 turn_context、无 tool call、Python 无异常堆栈；dispatcher 60s 后报 `pid not alive` → crash → 2 次后 `gave_up`。日志末尾最后一行是 `Plugin discovery complete: 38 found, 32 enabled`，看似正常但实际已经死。

**表面现象干扰**：tail 看 worker log 会看到 MCP stdio server 报 `BrokenPipeError`（`mcp-stderr.log`），容易误判为 MCP 根因。但 **BrokenPipe 是父进程死后子进程写 stdout 失败的结果，不是 cause**。

**真实根因**：worker profile 的 `config.yaml` 里 `skills.external_dirs` **只指向 orchestrator 项目**（如 `/home/pascal/workspace/yquant-investment/skills`），**目标项目的 skills 没被加入**。当 `kanban_create` 的 `workspace_path` 指向 yinglong 项目、且 `skills=[travel, ...]` 引用 yinglong 的 skill 时：

1. worker 启动时按 `external_dirs` 加载 skills → yinglong 的 skill 找不到
2. hermes_cli 抛 `Unknown skill(s): travel` 异常
3. 异常发生在 MCP stdio 启动后的某个 thread 里，**被 hermes_cli 静默吞掉**
4. 主进程被 watchdog SIGKILL
5. dispatcher 等不到心跳 → crash

**根因复盘**（yinglong 5h44m 类事故的反向版本）：

| 表象 | 真实 |
|------|------|
| MCP server `BrokenPipeError` | **结果**，不是 cause（父进程死后子进程 stdout flush 失败） |
| `pid not alive` 60s 后触发 | 真实，进程确实死 |
| plugin discovery 后无任何日志 | 异常被 hermes_cli 静默吞掉 |
| 任务 2 次连挂 100% 复现 | 根因 100% 在配置层，不是环境/网络 |

**修复**（最低成本）：

```bash
# 给所有 4 个 worker profile 加入目标项目 skills 路径
for p in yquantprincipal yquantdeveloper yquanttester yquantreviewer; do
  cfg="/home/pascal/.hermes/profiles/$p/config.yaml"
  cp "$cfg" "$cfg.bak-$(date +%Y%m%d-%H%M%S)"
  python3 -c "
import yaml
y = yaml.safe_load(open('$cfg'))
ext = y.setdefault('skills', {}).setdefault('external_dirs', [])
target = '/home/pascal/workspace/yq-yinglong/skills'
if target not in ext:
    ext.append(target)
yaml.dump(y, open('$cfg', 'w'), default_flow_style=False, sort_keys=False, allow_unicode=True)
"
done
```

**预防**（Intake 阶段必做，纳入标准化 checklist）：

1. **目标项目 conventions 发现时同步固化 worker profile `external_dirs`**：新项目/新 worker profile 上线前，**必须**把目标项目 skills 目录加到 4 个 worker profile 的 `external_dirs`，不能依赖 `workspace_path` 自动发现。
2. **P-1b 与 P-1c 的关键区别**：
   - P-1b：`kanban_create(skills=...)` 引用了 orchestrator 自己可见但 worker 不可见的 profile-local skill → `Unknown skill` 立即报错退出
   - P-1c：**`skills=[]` 引用的 skill 名确实存在于项目目录**，但**项目目录不在 worker profile 的 `external_dirs` 中** → 异常被静默吞掉，**更难诊断**
3. **诊断命令**（P-1c 比 P-1b 难在"静默"）：

```bash
# Step 1: 检查 worker profile 能否看到目标 skill
hermes -p yquantprincipal chat -q "只回复 OK" --skills <target-skill>
# 输出 "Error: Unknown skill(s): <target-skill>" = P-1c 命中

# Step 2: 看 worker profile 实际加载的 external_dirs
grep -A 3 "external_dirs" ~/.hermes/profiles/<worker>/config.yaml

# Step 3: 确认 worker 进程启动后是否有 turn_context（= 是否进入对话循环）
grep "turn_context" ~/.hermes/profiles/<worker>/logs/agent.log | tail -3
# 没有 turn_context 出现 = P-1c 静默失败典型症状
```

**长期改进方向**（未实施）：dispatcher 在 spawn worker 时**自动**根据 `workspace_path` 把目标项目 skills 路径注入 `HERMES_SKILLS_EXTERNAL_DIRS` 环境变量，避免每个项目都要手改 4 个 worker profile config。

**预防 checklist（Intake 必跑）**：

```bash
# 流水线部署/复用前，对每个 worker profile 跑一次
for p in yquantprincipal yquantdeveloper yquanttester yquantreviewer; do
  for s in $(ls -1 $PIPELINE_WORKSPACE/skills/); do
    if ! hermes -p $p chat -q "ok" --skills $s 2>&1 | grep -q "^Error"; then
      echo "  $p: $s ✓"
    else
      echo "  $p: $s ✗ (P-1c 命中：worker 看不到项目 skill)"
    fi
  done
done
```

### P-2: dispatcher 透明跑 fallback 链，任务名义 assignee 与实际模型可能不一致

**症状**：`kanban_create(assignee="yquantprincipal")` 派出的 task 实际由 zai/glm-5.2 甚至 MiniMax-M3 完成。task summary 看似完成，但内容质量反映的是 fallback 模型的能力上限，不是 yquantprincipal 的设计意图。

**根因**：dispatcher spawn worker 时设置 `HERMES_HOME=~/.hermes/profiles/<assignee>/`，worker 加载该 profile 的 `config.yaml`。**`config.yaml` 的 `fallback_providers` 是 worker 进程内透明的**：gpt-5.5 失败 → 切 zai → 切 minimax，全程 worker 不报错，task 状态正常变 done。

**观察命令**：

```bash
grep -E "Fallback activated|API call.*model=" \
  ~/.hermes/profiles/<worker>/logs/agent.log | grep "<session_id>"
```

**预防**：高价值任务（RFC/SPEC/Design/Review）派发后监控 worker 日志，确认 primary 模型跑通而非 fallback。如果 gpt-5.5 不可达，先排查 chatgpt.com 网络 / OAuth 凭证，再考虑降级策略（要么换模型，要么先改 `fallback_providers` 把 zai 移到第一位作为暂时妥协）。

### P-3: Kanban DB 任务 ID 不存在时不能 "parents=[]" 强行串联

**症状**：旧 RFC/SPEC 是用文本声明 + `delegate_task` 做的（没有 kanban task），想派 Design 任务并设 `parents=[<SPEC 的 task id>]` 会失败——因为那个 task id 从来没存在过。

**修复**：用 C3 方案——在 Design 任务 body 里**显式引用 SPEC 文件路径**（如 `docs/spec/03_data/SPEC-03-006-*.md`），不依赖 parent task 链路。Design 阶段自己读 SPEC 文件来保证一致性。**不要**为了“补建 parent”创建空的 SPEC 幽灵任务。

### P-4: workspace_path 必须用共享项目目录

**症状**：worker 在自己 profile 的 state.db 目录下工作，不会自动访问项目源目录，导致找不到 skill / RFC / SPEC 文件。

**正确姿势**：

```python
kanban_create(
    ...,
    workspace_kind="dir",
    workspace_path=PIPELINE_WORKSPACE,
)
```

不要用 `workspace_kind="scratch"` 或留空——会丢失共享项目目录上下文。

### P-5: 按真实验收与授权决定完成，不因下游误 block

本阶段已交付且通过本卡验收、有预建下游时 `kanban_complete` 释放下游；只需同卡审查时 `kanban_request_review`，不能两条 lane 同时使用。真正缺必需验收、环境或授权时记录缺口并 `kanban_block`，不能将其包装为“残余风险”而 done。审查发现缺陷退回 Implement；review 列工作使用 `kanban_request_changes`。

主控先读 exact task 和证据再处理异常；不存在“blocked 满若干分钟自动 unblock”规则。完成卡的 summary/metadata 记录候选、命令/exit、未覆盖项和不阻塞风险，不再额外维护状态副本。

历史：[P-5 事故与旧 SOP](references/history/p5-incident-sop.md) 已退役，仅供审计，非当前指令、无新任务必读要求。

### P-6: T1/T2 完成后用户决策变更未回头修订

**症状**（2026-06-28 应龙 RFC-16-001 历史案例，T5 Review 为当时阶段）：用户在 T1 done 后提出"应龙要有专属 MongoDB"——这是影响 RFC §5、SPEC §4.4、Design §3.x 的**设计类决策**。但编排层在 T3 派发时只把决策写进 T3 body，没回头修订 T1/T2。结果 T2 Design 文档里 0 次出现 yinglong-db 关键词，T5 Review 找不到"为什么这样设计"的依据，事实文档与设计依据脱节。

**根因**：编排层把"用户决策"等同于"细节微调"，误判其影响范围。其实判定的标准是**"这条决策会不会让已完成章节不准确"**，而不是"这条决策大不大"。

**预防**：
- 详见本文档"**阶段决策同步门禁（用户决策变更时）**"小节
- 操作上：T1/T2 完成后用户提决策，先问"是否影响已完成的章节"；若影响，必须先回头补章节再放行 T3
- 已 done 阶段由编排层直接补；用 `kanban_comment` 通知下一阶段 worker "前置决策增补在 [path]#[section]"

**P-6 与其他 Pitfalls 的关系**：
- P-1~P-5 都是"运行时坑"（worker crash、fallback 透明、状态机错误等）
- P-6 是"流程坑"——编排层行为问题，不是 worker 问题
- 修复动作是"补文档"，不是"改代码"

### P-7: 编排层越界直接改文档模板

**症状**（2026-06-28 应龙 RFC-16-001 案例）：编排层发现"design 模板没有持久化章节"导致 T2 漏设计，在 T2 已 done 后**直接 patch 3 个文档模板**（RFC/SPEC/DESIGN）。patch 里 RFC 模板的"- 异常降级分支"行被误删，需 `git checkout` 撤回。

**根因**：编排层越界。文档模板是跨项目、跨 worker 的"全局规约源"，章节结构变更应当由架构师角色（principal）拍板，编排层只负责"用模板"，不应"改模板"。编排层视角单一（只看单一项目、单一案例），改出来的章节可能不符合 YQuant 整体风格。

**预防**：
- 详见本文档"**文档模板变更守则**"小节
- 操作上：编排层需要改模板时，**必须**派 Kanban 任务给 `yquantprincipal`（priority 7），body 写明触发原因、建议章节（可选）、明确"可重写"
- `kanban_create` 任务 body 禁止写"直接 patch <template_path>"，只能写"找 principal 走模板变更流程"
- principal 改完后，编排层负责 `cp` 同步到其他项目（yinglong、yquant 等）

**P-7 与 P-6 的区别**：
- P-6：编排层补"已 done 任务的文档"是**允许**的（补救）
- P-7：编排层补"跨任务的模板/全局规约"是**禁止**的（必须委派）
- 简单判定：改**当前流水线实例的产出物** = OK；改**所有流水线实例的规约源** = 不 OK

### P-8: 跨项目复用前必须先发现目标项目命名约定

**症状**：orchestrator 把一个项目的 `docs/{rfc,spec,design}/` 数字域、模块名、文件编号规则照搬到另一个项目，worker 随后按错误路径写 RFC/SPEC/Design；用户需要多轮纠正目录和文件名。

**根因**：pipeline 是通用基础设施，但项目命名是局部约定。worker 不会自动推断目标项目的真实模块/skill 编号，也不一定读取 README。

**修复**：Intake 在派第一个文档任务前必须执行“项目约定发现与任务正文固化”：读取目标项目 docs README、模板、skills/module 目录和 config，并把精确交付路径写入 task body。

**预防**：文档类任务 body 必须给出完整示例，例如：

```text
交付物路径（严格按目标项目约定）：
- docs/rfc/<module-dir>/<RFC-file>.md
- docs/spec/<module-dir>/<SPEC-file>.md
示例：docs/rfc/16_travel/RFC-16-001-travel-planning-ability.md
```

示例只作为目标项目当前约定的展开，不得把某个项目的示例当成跨项目默认值。

### P-9: 中途变更骨架/命名规范时，orchestrator 负责 comment + 兜底搬迁

**症状**：用户在 T1/T2 已经启动后修正文档目录、文件名、模块编号或数据契约。worker 可能已经按旧规则写了一部分产物；如果只在聊天里确认，不通知 worker，后续阶段继续沿用旧规则。

**修复流程**：

```text
1. 立即用 kanban_comment 通知已创建/已 claim 的相关 task：新约定是什么、哪些路径作废。
2. 若 worker 已按旧路径写出产物，orchestrator 负责 mv/rename 兜底，不把纯路径搬迁退回给 worker 重做。
3. 下一阶段 body 顶部写“前置约定变更”，引用新路径和上一阶段修正说明。
4. 若变更会让已完成 RFC/SPEC/Design 内容不准确，触发“阶段决策同步门禁”，先补文档再派实现任务。
```

**预防**：Intake 第一次派任务前，尽量让用户确认“目录/文档命名规范”和“模块编号来源”；但一旦中途变更，状态同步责任在 orchestrator。

### P-10: 凭据/环境文件可能被工具链遮蔽，验证时看"是否真实可用"而不是看起来已写入

**症状**：worker 或 orchestrator 声称已写入 `.env` / config，但后续 API/Mongo/外部服务 auth 仍失败；文件里出现 `***`、占位字符串或被遮蔽值。

**根因**：Hermes 工具链和日志会保护 `*_PASSWORD`、`*_API_KEY`、`*_SECRET`、`*_TOKEN` 等敏感字段。某些写入/展示路径可能把真实值遮蔽成占位，导致"看起来写了，实际不可用"。

**修复**：

- 不在 skill、task metadata、kanban summary 中记录真实秘密。
- 写入凭据后，用最小泄露方式验证：只打印键名、长度、hash 前缀或直接调用目标服务 smoke test。
- auth 失败时，先检查"值是否仍是占位/遮蔽值"，再排查网络和代码。

**预防**：涉及凭据的实现任务，验收标准必须包含"真实连接 smoke test 或只泄露长度的配置读取测试"，不能只检查文件存在。

历史：[P-12 Quick Flow 断链](references/history/quick-flow-p12-breakchain.md) 已退役，仅供审计，非当前指令、无新任务必读要求。

### P-27: 仅使用真实 parent id，禁止占位依赖

Intake 内依次调用创建：取得上游返回的真实 id → 创建下游并传 `parents=[真实 id]` → 读回下游核对依赖。这里的“依次创建”不是等待上游执行 done 后再派下一张。Full 四卡、Light 两卡按现行任务图建立；禁止先建下游靠 worker 自我 block 修链。

历史：[P-27 占位 parent 事故](references/history/p27-placeholder-parent.md) 已退役，仅供审计，非当前指令、无新任务必读要求。

### P-11: 端到端 smoke test 必须包含"数据合理性校验"，不能只看 Phase 跑通（2026-06-29 应龙 Travel Pipeline 案例）

**症状**（历史旧链 T3 Implement → T4 Verify → T5 Review）：Implement 阶段 worker 把 7 P0 全部产出代码、单测 223 passed、T3 → T4 → T5 都 done。但 orchestrator 直接跑端到端 smoke 时发现：**POI 数据返回了北京景点（故宫/雍和宫/天安门）给"舟山朱家尖 4 日亲子自驾"行程**，因为 POI 聚合没按 destination 过滤；**discovery 反向推荐返回 0 候选**，因为 fixture 过滤逻辑把 8 个目的地全过滤掉了。

**根因**：
- T3 Implement 验收标准只检查"代码可跑 + 测试通过"，**没检查 destination/POI/预算等业务字段是否合理**
- T4 Verify 同样只看测试 PASS，没做端到端 e2e 烟测
- T5 Review 只看 diff 与 SPEC 对齐，没真实跑一次用户场景

**现行修复**：
- Implement body 写清真实用户输入、受影响路径和业务合理性断言（例如目的地必须匹配 POI）。
- 统一 Validate 按影响实际运行必要消费者路径，抽样检查真实输出；不能只看 diff 或单测 PASS。缺环境/授权明确未覆盖，不伪称 E2E。

**预防**：任何"产出数据"的 Pipeline，验收标准必须包含"用真实用户输入跑一次 + 人工或脚本检查输出合理性"。特别是 travel/search/recommend 类任务，光看代码和单测不够。

**真实证据**：`data/memory/16_travel_pipeline-smoke-2026-06-29.md`（yinglong 项目）

### P-27b: T1 retry 残留 worker 持 host lock 导致 T2 spawn 失败

**触发**：T1 完成 → dispatcher claim → T2 claim 后 0 秒 spawn → exit_code=1 立即崩溃。
**真因**：T1 retry 进程没死透，worker pid 仍持 host lock "Pascal-Laptop:89124" 等 Kanban DB 互斥锁；T2 worker 启动时获取同一锁失败 → watchdog SIGKILL。
**Fix**：`ps aux | grep <run_id>` 看僵尸 worker → `kill -9 <pid>` → `kanban_block(原 task, kind=capability)` → create T_redo parent=[原 t_teid]。

### P-28: T3 final2 长 retry 残留进程 + judge 误判

**触发**：`kanban_complete` 后 dispatcher 自动起 retry run，worker 进程不杀，run 跑 30+ 分钟超时报废，judger 错判为"需要更多 turns"。
**真因**：`kanban_complete` 不清 retry queue 残留 worker；judger 自身 fallback 模型链也限流，无法稳定判定任务已完成。
**Fix**：manual finalize 必先 `kill -9 <pid>` + `kanban_block(kind=capability)` 原卡 + create 续接卡 parent=[上一级 done]，不依赖 judge force close。

### P-29: Reader/Writer 包级导入与 sys.path 注入不对称的 ImportError

**触发**：新增文件用包级相对导入（`from .candidate_v2_contract import`），测试 `sys.path.insert(scripts)` 后顶层 `import` 直接崩。
**真因**：顶层 import 时模块没有包上下文，`ImportError: attempted relative import with no known parent package`。
**Fix**：加 3 个 `__init__.py`（skills/ + skills/knowledge/ + skills/knowledge/scripts/）让 scripts/ 成为正式 package；测试改 `from knowledge.scripts import`。

### P-30: fallback glm 上大任务超时/低吞吐

**触发**：Full Flow T3 6 task 在 fallback `zai/glm-5.3-flash` 上 60 turns 仅落盘 4/9 文件。
**真因**：130K tokens 输入 + 长 prompt 上退化，300-400s/turn latency；fallback 链对大任务既慢又不稳。
**Fix**：大任务拆 ≤4 交付物/卡；Pascal 拍板时优先 A3 路径（亲手写关键代码，worker 写测试）规避单 worker 超时。

### P-31: judge RateLimitError 已产物 finalize

**触发**：`kanban_complete` judge 连续 3 次 RateLimitError，但产物已 100% 落盘可独立验证。
**真因**：judger 自己的模型链也限流，系统卡在"judge 不可用 → 不能 finalize"单点。
**Fix**：不再依赖 judge force close，改用脱钩续接（新 task parent=[上一级 done]）+ 人工 mark done with real artifacts（grep 文件 + ls 落盘目录）。

历史：[2026-06-29 Quick Flow 五阶段日志](references/history/quick-flow-5stage-2026-06-29.md) 已退役，仅供审计，非当前指令、无新任务必读要求。

## 参考资料

`references/history/` 下八份文件均为历史归档，非当前入口或指令，无新任务必读要求；原块内旧指针按来源上下文解释。
- [部署分流历史](references/history/deployment-routing-2026-08-19.md)
- [Quick V1.2 规则历史](references/history/quick-flow-v1.2-rules.md)
- [主动推进 SOP 历史](references/history/orchestrator-push-sop-2026-06-07.md)
- [P-12 断链历史](references/history/quick-flow-p12-breakchain.md)
- [P-5 事故历史](references/history/p5-incident-sop.md)
- [P-27 占位 parent 历史](references/history/p27-placeholder-parent.md)
- [Quick 五阶段日志历史](references/history/quick-flow-5stage-2026-06-29.md)
- [pipeline Quick 阶段参考历史](references/history/pipeline-quick-flow-legacy.md)

- `references/pipeline.md`：阶段门禁、任务管理与报告落点、路由规则。
- `references/document-layers.md`：RFC/SPEC/DESIGN 的职责边界。
- `references/agent-handoff.md`：角色交接内容、交付物和退回条件。
- `references/hermes-kanban-orchestration.md`：Hermes Kanban profile worker 编排规则。
- `references/quick-flow-journal-2026-06-29.md`：已退役 Quick 历史实跑日志（含 T1-T4 task IDs、产物、关键教训），非当前入口或指令，无新任务必读要求。
- `references/quick-flow-handoff-mechanism.md`：已退役 Quick 历史事故资料，不是当前入口，无新任务必读要求。
- **P-1c 复盘（2026-07-01 yinglong 5 阶段 4 task 实跑）**：worker profile `external_dirs` 不覆盖目标项目 skills 目录时，进程静默 SIGKILL、P-1b 风格的 `Unknown skill` 异常被 hermes_cli 静默吞掉。详见 [P-1c](#p-1c)。
- `references/spec-from-rfc.md`：**SPEC 阶段专用编写手册**——从 RFC 派生 SPEC 时的决策→契约映射模式、12 节章节清单、7 类陷阱（含「不改动清单 P-2」「硬编码版本号 P-3」「向后兼容 P-4」「混淆 SPEC/Design 边界 P-7」）、验证清单与完成回报模板。
- `skills/common/utils/print_agent_models.py`：查看所有 Agent 当前模型/fallback/compression 配置。
- `references/real-run-journal-2026-06-25.md`：已退役历史实跑日志——保留 2026-06-25 RFC-03-006 的真实时序、模型 fallback 观察与 worker crash 复盘，非当前入口或指令，无新任务必读要求。
