# SPEC-10-004: YQuant AI Coding Pipeline Skill 同步与冲突修复

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-27 |
| 最后更新 | 2026-06-30 |
| 版本号 | V1.2 |
| 来源 RFC | RFC-10-004-yquant-ai-coding-pipeline-skill-sync |
| 目标模块 | infra / Hermes Kanban Pipeline |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer, YQuant-Reviewer-Principal |
| 关联 RFC | RFC-10-003-infra-architecture |
| 关联 Design | DESIGN-10-004-yquant-ai-coding-pipeline-skill-sync（待创建） |

## 1. 需求摘要

本 SPEC 将 RFC-10-004 的治理决策落为可执行文件契约、操作契约与验收矩阵。实现者必须把 yquant 主 profile 运行态副本独有的 P-1~P-4 教训与 real-run journal 合并回项目源目录，并删除 4 个 worker profile 的同名 skill 副本；同时保留并更新 yquant 主 profile 副本作为 orchestrator runtime cache。

核心交付物：

1. 项目源 `skills/infra/ai-coding-pipeline/SKILL.md` 包含 P-1~P-4 与正确同步策略；
2. 项目源 `skills/infra/ai-coding-pipeline/references/real-run-journal-2026-06-25.md` 与 yquant 主 profile 运行态 journal md5 一致；
3. `~/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline/` 存在；
4. `~/.hermes/profiles/{yquantprincipal,yquantdeveloper,yquanttester,yquantreviewer}/skills/infra/yquant-ai-coding-pipeline/` 不存在；
5. 验证命令证明不再发生 `Ambiguous skill name`，worker 能进入对话循环。

## 2. 范围

### 2.1 In Scope

- [ ] 修改项目源 `skills/infra/ai-coding-pipeline/SKILL.md`。
- [ ] 新增项目源 `skills/infra/ai-coding-pipeline/references/real-run-journal-2026-06-25.md`。
- [ ] 同步项目源到 yquant 主 profile 运行态副本。
- [ ] 删除 4 个 worker profile 的同名 skill 副本。
- [ ] 运行并记录 md5、find、skill load、模型配置脚本与 Kanban worker smoke 验证。
- [ ] 产出 RFC/SPEC/Design 三层独立文档。

### 2.2 Out of Scope

- [ ] 不修改 Hermes core、skill discovery 或 collision 解析逻辑。
- [ ] 不修改 Hermes 升级脚本、安装脚本或 gateway 配置。
- [ ] 不修改 `~/.hermes/profiles/*/config.yaml` 的模型、fallback、toolset 配置。
- [ ] 不改变 pipeline 的阶段路由、assignee profile、依赖链规则。
- [ ] 不清理历史 Kanban crashed task/run；如需清理，另开任务。
- [ ] 不删除 yquant 主 profile 运行态副本。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | 差异识别 | 项目源 SKILL 与 yquant runtime SKILL | md5 与 diff 摘要 | 如果 yquant runtime 不存在，阻塞并要求人工确认恢复来源 |
| F-002 | P-1~P-4 合并 | runtime SKILL 独有 Pitfalls | 项目源 SKILL 包含 `### P-1` 至 `### P-4` | 不得覆盖核心路由规则 |
| F-003 | 同步策略修正 | 项目源 SKILL `源目录与运行态同步` 章节 | 只同步 yquant，删除 4 个 worker 副本的命令 | 不得保留“同步到所有 profile”的旧命令作为推荐路径 |
| F-004 | journal 回流 | runtime `references/real-run-journal-2026-06-25.md` | 项目源同名文件 | md5 必须一致 |
| F-005 | yquant cache 保留 | 项目源 skill 目录 | yquant 主 profile skill 副本存在且同步到最新项目源 | 不得删除 yquant 主 profile 副本 |
| F-006 | worker 副本删除 | 4 个 worker profile skill 路径 | 目标路径不存在 | 只允许删除精确同名 skill 目录 |
| F-007 | Ambiguous 消除验证 | `find ~/.hermes/profiles ...` | 只输出 yquant 主 profile 一行 | 若输出多于一行，必须继续定位残留副本 |
| F-008 | Hermes skill load 验证 | `yquant-ai-coding-pipeline` skill 名称 | 加载成功且无 Ambiguous | 若命令不支持直接 load，以 worker smoke task 作为替代验证 |
| F-009 | worker smoke 验证 | 测试 Kanban task | worker 进入对话循环并完成 | 若 gateway 未运行，记录为环境阻塞，不伪造结果 |

## 4. 数据与接口契约

### 4.1 路径契约

| 名称 | 路径 | 状态要求 | 说明 |
|---|---|---|---|
| canonical_skill_dir | `/home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/` | 必须存在 | 唯一长期维护源 |
| canonical_skill_md | `skills/infra/ai-coding-pipeline/SKILL.md` | 必须包含 P-1~P-4 | 项目源 SKILL |
| canonical_journal | `skills/infra/ai-coding-pipeline/references/real-run-journal-2026-06-25.md` | 必须存在 | 实跑 journal |
| yquant_runtime_skill_dir | `/home/pascal/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline/` | 必须存在 | 主 profile runtime cache |
| worker_principal_copy | `/home/pascal/.hermes/profiles/yquantprincipal/skills/infra/yquant-ai-coding-pipeline/` | 必须不存在 | 避免 collision |
| worker_developer_copy | `/home/pascal/.hermes/profiles/yquantdeveloper/skills/infra/yquant-ai-coding-pipeline/` | 必须不存在 | 避免 collision |
| worker_tester_copy | `/home/pascal/.hermes/profiles/yquanttester/skills/infra/yquant-ai-coding-pipeline/` | 必须不存在 | 避免 collision |
| worker_reviewer_copy | `/home/pascal/.hermes/profiles/yquantreviewer/skills/infra/yquant-ai-coding-pipeline/` | 必须不存在 | 避免 collision |

### 4.2 输入契约：必须合并的运行态独有内容

| 输入内容 | 来源 | 项目源落点 | 验证方式 |
|---|---|---|---|
| delegate_task 不创建 Kanban DB task 的历史教训 | yquant runtime SKILL 执行模型段 | `## Hermes 执行模型` bullet | grep `delegate_task.*不在 Kanban DB 创建 task 记录` |
| SPEC 文件清单需精确到目录层级 | yquant runtime SKILL 执行模型段 | `## Hermes 执行模型` bullet | grep `SPEC §3 文件清单必须精确到目录层级` |
| worker profile 不保留副本策略 | yquant runtime SKILL 同步段 | `### 源目录与运行态同步` | grep `不要把 worker profile` |
| P-1 Skill name collision | yquant runtime SKILL Pitfalls | `## Pitfalls` | grep `### P-1` |
| P-2 fallback 链透明 | yquant runtime SKILL Pitfalls | `## Pitfalls` | grep `### P-2` |
| P-3 Kanban DB task id | yquant runtime SKILL Pitfalls | `## Pitfalls` | grep `### P-3` |
| P-4 workspace_path | yquant runtime SKILL Pitfalls | `## Pitfalls` | grep `### P-4` |
| real-run-journal-2026-06-25.md | yquant runtime references | 项目源 references | md5sum 一致 |

### 4.3 输出契约：合并后项目源 SKILL 必须包含的章节

- `## Hermes 执行模型`
- `### Hermes Profile 路由`
- `### 源目录与运行态同步`
- `### Kanban 创建规则`
- `## 触发入口`
- `## 编排顺序`
- `### 三层文档强制规则`
- `## 强制角色拆分`
- `## 运行态自检`
- `## Pitfalls（2026-06-25 实跑后补）`
- `## 参考资料`

### 4.4 操作契约：允许执行的命令

```bash
# 1. 合并前证据
md5sum \
  /home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/SKILL.md \
  /home/pascal/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline/SKILL.md

diff -u \
  /home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/SKILL.md \
  /home/pascal/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline/SKILL.md

# 2. journal 回流
cp /home/pascal/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline/references/real-run-journal-2026-06-25.md \
  /home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/references/real-run-journal-2026-06-25.md

# 3. yquant runtime cache 同步
mkdir -p /home/pascal/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline
cp -a /home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/. \
  /home/pascal/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline/

# 4. worker 副本删除
for p in yquantprincipal yquantdeveloper yquanttester yquantreviewer; do
  rm -rf "/home/pascal/.hermes/profiles/$p/skills/infra/yquant-ai-coding-pipeline"
done

# 5. 副本数量验证
find ~/.hermes/profiles -name "SKILL.md" -path "*yquant-ai-coding-pipeline*" -print
```

## 5. 配置契约

本 SPEC 不新增或修改 `config.yaml` 字段。

| 配置项 | 行为 |
|---|---|
| provider/model/fallback | 不修改 |
| gateway / dispatcher | 不修改 |
| profile toolsets | 不修改 |
| skill path | 仅通过文件系统目录存在性治理，不写入 config |

## 6. 行为契约（RFC 决策 → 落地点映射）

| RFC 决策 | SPEC 落地点 | 章节 |
|---|---|---|
| 项目源目录是唯一 canonical source | `canonical_skill_dir` 路径契约；SKILL 同步策略 | 4.1, 4.4 |
| yquant 主 profile 保留运行态副本 | yquant_runtime_skill_dir 必须存在；同步命令只复制到 yquant | 4.1, 4.4 |
| 4 个 worker profile 删除同名副本 | worker_*_copy 必须不存在；rm 精确路径 | 4.1, 4.4 |
| 运行态独有 P-1~P-4 必须回流项目源 | 输入契约列明 7 项 grep 验证 | 4.2 |
| journal 必须进入项目源 references | canonical_journal md5 一致 | 4.1, 4.2 |
| 不修改 Hermes core / config / 路由规则 | Out of Scope 与配置契约 | 2.2, 5 |
| worker smoke task 作为端到端证明 | 验收 A-006 | 9 |

## 7. 错误契约

| 错误情形 | 处理方式 | 是否阻塞 |
|---|---|---|
| yquant runtime SKILL 不存在 | 不猜测内容；阻塞并要求人工确认恢复来源 | 是 |
| runtime journal 不存在 | 不创建空 journal；阻塞并要求人工确认是否跳过或从历史恢复 | 是 |
| find 输出多于 1 行 | 定位残留 worker 副本并删除；重新运行 find | 是 |
| find 输出 0 行 | 说明 yquant 主 profile cache 丢失；重新同步 yquant cache | 是 |
| skill load 命令不可用 | 用 Kanban worker smoke task 替代 | 否，需记录替代验证 |
| gateway 未运行导致 smoke task 不调度 | 记录环境阻塞并要求 operator 启动 gateway | 是 |
| model script 因外部依赖失败 | 记录真实错误，不伪造通过 | 是 |

## 8. 文件改动清单

### 8.1 新增

- `docs/rfc/10_infra/RFC-10-004-yquant-ai-coding-pipeline-skill-sync.md`
- `docs/spec/10_infra/SPEC-10-004-yquant-ai-coding-pipeline-skill-sync.md`
- `docs/design/10_infra/DESIGN-10-004-yquant-ai-coding-pipeline-skill-sync.md`（Design 阶段创建）
- `skills/infra/ai-coding-pipeline/references/real-run-journal-2026-06-25.md`

### 8.2 修改

- `skills/infra/ai-coding-pipeline/SKILL.md`
- `/home/pascal/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline/`（从项目源同步，运行态 cache）

### 8.3 删除

- `/home/pascal/.hermes/profiles/yquantprincipal/skills/infra/yquant-ai-coding-pipeline/`
- `/home/pascal/.hermes/profiles/yquantdeveloper/skills/infra/yquant-ai-coding-pipeline/`
- `/home/pascal/.hermes/profiles/yquanttester/skills/infra/yquant-ai-coding-pipeline/`
- `/home/pascal/.hermes/profiles/yquantreviewer/skills/infra/yquant-ai-coding-pipeline/`

### 8.4 不改动（明确列出）

- `~/.hermes/profiles/*/config.yaml`
- Hermes core / CLI / gateway 源码
- `skills/infra/ai-coding-pipeline/references/pipeline.md`
- `skills/infra/ai-coding-pipeline/references/document-layers.md`
- `skills/infra/ai-coding-pipeline/references/agent-handoff.md`
- `skills/infra/ai-coding-pipeline/references/hermes-kanban-orchestration.md`
- `skills/infra/ai-coding-pipeline/references/spec-from-rfc.md`
- 所有 data / research / portfolio / report 业务模块代码

## 9. 测试要求

| 编号 | 类型 | 命令 / 方法 | 断言 |
|---|---|---|---|
| UT-001 | 文档检查 | `grep -n "### P-[1-4]" skills/infra/ai-coding-pipeline/SKILL.md` | 输出 P-1~P-4 四行 |
| UT-002 | journal 一致性 | `md5sum <runtime_journal> <canonical_journal>` | 两个 md5 相同 |
| UT-003 | profile 副本检查 | `find ~/.hermes/profiles -name "SKILL.md" -path "*yquant-ai-coding-pipeline*"` | 只输出 yquant 主 profile 一行 |
| UT-004 | 禁改检查 | `git diff -- ~/.hermes/profiles/*/config.yaml` 或确认无 config diff | 无 config 修改 |
| IT-001 | 模型脚本 | `python3 skills/common/utils/print_agent_models.py` | exit code 0，正常输出 profile 模型信息 |
| IT-002 | skill load | Hermes skill load / chat 加载该 skill | stderr/stdout 不含 `Ambiguous skill name` |
| IT-003 | Kanban worker smoke | 创建一个只回答 `2` 的 yquantprincipal smoke task | task done，summary 表示进入对话循环 |
| REG-001 | git 范围 | `git status --short` | 只包含本 SPEC/RFC/Design 与 skill/journal 相关变更；既有无关变更不被触碰 |

## 10. 验收标准

| 编号 | 验收项 | 验证方式 | 对应测试 |
|---|---|---|---|
| A-001 | find 只输出 yquant 主 profile 一份 | `find ~/.hermes/profiles ...` | UT-003 |
| A-002 | 项目源 SKILL 包含 P-1~P-4 | grep `### P-1` 至 `### P-4` | UT-001 |
| A-003 | 项目源 journal 存在且与 runtime 一致 | md5sum | UT-002 |
| A-004 | Hermes 加载 skill 不再 Ambiguous | skill load 或 worker smoke 日志 | IT-002 / IT-003 |
| A-005 | model config 自检正常 | `python3 skills/common/utils/print_agent_models.py` | IT-001 |
| A-006 | worker 正常进入对话循环 | smoke task done | IT-003 |
| A-007 | 未修改 profile config 或 Hermes core | git/status/路径检查 | UT-004 / REG-001 |

## 11. 实现约束

- 删除命令必须是精确目录：`.../skills/infra/yquant-ai-coding-pipeline`，不得使用宽泛 glob 删除整个 `skills/infra`。
- 同步方向必须是项目源 → yquant 主 profile，不得用运行态副本反向覆盖项目源（除人工 diff 后挑选内容）。
- 文档中不得包含 API key、OAuth token、完整 secrets 环境变量值。
- 若验收命令失败，必须报告真实失败，不得写“已验证通过”的占位文本。
- Design 阶段必须补充回滚策略：可从项目源重新同步 yquant cache；worker 副本删除无需恢复，除非 Hermes discovery 机制改变。

## 12. 风险与未解决问题

| 风险 | 缓解 | 归属 |
|---|---|---|
| 项目源与 yquant cache 再次漂移 | 后续可新增同步脚本或 CI 检查 | 后续 RFC |
| Hermes 未来 discovery 机制变化 | 保留 RFC/SPEC 记录，必要时重新评估副本策略 | Principal |
| smoke task 依赖 gateway 与模型可用性 | 验证时区分 skill collision 与外部模型/gateway 故障 | Tester |

未解决问题：

- 是否需要把"只同步 yquant cache、删除 worker copy"的逻辑固化到 Hermes profile bootstrap 或项目脚本中？本 SPEC 不处理。
- 是否需要在 Hermes upstream 支持同名 skill 优先级或 shadowing 规则？本 SPEC 不处理。

## 13. Quick Flow 可执行契约

### 13.1 Kanban 任务链契约

Quick Flow 5 阶段对应 4 个 Kanban task：

```text
T1 RFC/SPEC/Design   assignee=yquantprincipal   产出：RFC + SPEC + Design 三份独立文档
T2 Implement          assignee=yquantdeveloper   parents=[T1]
T3 Verify             assignee=yquanttester      parents=[T2]
T4 Closeout           assignee=<orchestrator>    parents=[T3]
```

创建时序：Quick Flow 的 T1/T2/T3/T4 必须在 Intake 阶段一次性创建并写入 Kanban DB：

| Task | 初始状态 | 创建时机 | parents | 衔接机制 |
|---|---|---|---|---|
| T1 RFC/SPEC/Design | `ready` | Intake 当下 | `[]` | dispatcher 立即 claim/spawn |
| T2 Implement | `todo` | 与 T1 同一轮 Intake | `[T1]` | T1 done 后由 `recompute_ready` 自动 promote |
| T3 Verify | `todo` | 与 T1 同一轮 Intake | `[T1, T2]`（最低 `[T2]`） | T2 done 后由 DB 状态机自动 promote |
| T4 Closeout | `todo` | 与 T1 同一轮 Intake | `[T1, T2, T3]`（最低 `[T3]`） | T3 done 后由 DB 状态机自动 promote |

禁止模式：不得在 T1 done 后才创建 T2、T2 done 后才创建 T3、T3 done 后才创建 T4。该串行创建模式把流程正确性绑定到 orchestrator 主 session 活性和通知进程，已在 2026-06-30 yinglong Quick Flow 运行中导致 5h44m 断链。

三份文档的产出顺序与文件命名契约：

| 文档 | 路径模板 | 示例 |
|---|---|---|
| RFC | `docs/rfc/{module}/RFC-{NN}-{XXX}-{short-name}.md` | `docs/rfc/10_infra/RFC-10-004-...md` |
| SPEC | `docs/spec/{module}/SPEC-{NN}-{XXX}-{short-name}.md` | `docs/spec/10_infra/SPEC-10-004-...md` |
| Design | `docs/design/{module}/DESIGN-{NN}-{XXX}-{short-name}.md` | `docs/design/10_infra/DESIGN-10-004-...md` |

文档文件名中的 `{NN}-{XXX}` 必须与来源 RFC 编号一致。

### 13.2 T1 Task Body 最低要求

T1（RFC/SPEC/Design，assignee=yquantprincipal）的 body 必须包含：

- 用户目标和流程模式声明："本任务走 Quick Flow（5 阶段：Intake → RFC/SPEC/Design → Implement → Verify → Closeout）"。
- Intake 阶段已完成 T2/T3/T4 task id 预创建，本 task 完成后由 dispatcher 自动 promote+spawn 后续阶段；不得要求 orchestrator 临时创建下一阶段。
- 预创建任务 ID 清单：`T2=<task_id>`、`T3=<task_id>`、`T4=<task_id>`（由 orchestrator 在 body 中填入）。
- 允许修改的文件范围精确列表。
- 禁止修改的文件范围精确列表。
- 三层文档的精确目标路径（至少给出完整路径示例）。
- 项目约定（文档命名、模块编号、数据库/隐私/凭据约束等）。
- 验收标准清单（每份文档的章节结构要求）。
- 输出语言要求。

### 13.3 T2 Task Body 最低要求

T2（Implement，assignee=yquantdeveloper）的 body 必须包含：

- 来源 RFC/SPEC/Design 的精确文件路径引用。
- Quick Flow 预创建声明：本 task 已在 Intake 阶段预创建，`parents=[T1]`；不得依赖 orchestrator 在 T1 done 后临时创建。
- 允许修改的代码文件范围。
- 禁止修改的代码文件范围。
- 实现约束（来自 SPEC §11 与 Design §7）。
- 验收标准（含端到端 smoke test + 业务合理性 checklist）。
- 需要运行的测试命令或可接受的替代验证方法。
- 输出语言要求。

### 13.4 T3 Task Body 最低要求

T3（Verify，assignee=yquanttester）的 body 必须包含：

- 来源 SPEC 的精确文件路径引用。
- Quick Flow 预创建声明：本 task 已在 Intake 阶段预创建，`parents=[T1,T2]` 或最低 `parents=[T2]`；不得依赖 orchestrator 在 T2 done 后临时创建。
- 验收标准矩阵（来自 SPEC §10）。
- 测试命令与断言列表。
- 端到端 smoke test 具体步骤（含数据合理性抽样检查）。
- 输出语言要求。

### 13.5 T4 Closeout 最低要求

T4 Closeout 由 orchestrator 执行，必须完成：

- 衔接机制核查：确认 T1/T2/T3/T4 均在 Intake 阶段预创建，且 `task_links` 中存在 T2/T3/T4 的 parent 依赖。
- Closeout 自审清单（RFC-10-004 §12.7，≥11 项逐一核查）。
- 变更总结（1-3 句）。
- 残余风险与后续事项。
- 若自审发现问题，按严重度处理：
  - Minor（文档遗漏、命名建议）→ orchestrator 直接修，closeout 记录。
  - Major/High（契约不一致、测试未达标、遗漏关键路径）→ 退回 T2，不 closeout。

### 13.6 验收标准矩阵（Quick Flow 专用）

| 编号 | 验收项 | 验证方式 | 负责阶段 |
|---|---|---|---|
| Q-A-001 | RFC/SPEC/Design 三份文档均存在且章节结构完整 | 文件存在性 + 章节 grep | T1 完成后 orchestrator 门禁 |
| Q-A-002 | 三层文档引用关系正确（RFC → SPEC → Design） | 交叉引用 grep | T1 完成后 orchestrator 门禁 |
| Q-A-003 | T2 实现符合 SPEC/Design 约束 | T3 Verify 测试报告 | T3 |
| Q-A-004 | 验收标准（SPEC §10 + RFC §9）全部通过 | T3 测试报告 + orchestrator 复核 | T3/T4 |
| Q-A-005 | Closeout 自审清单 ≥11 项全部通过 | orchestrator 逐项核查并记录 | T4 |
| Q-A-006 | 文件改动范围在 Design 预期内 | `git diff --stat` 对比 Design §3.1 | T4 |
| Q-A-007 | 未修改禁止清单中的文件 | `git diff --name-only` 交叉检查 | T4 |
| Q-A-008 | T1-T4 在 Intake 阶段一次性预创建且 parent links 存在 | Kanban task/comment/thread + `task_links` 复核 | T4 |

### 13.7 与 RFC-10-004 §12 的对应关系

| RFC-10-004 章节 | SPEC-10-004 落地点 |
|---|---|
| §12.3 触发条件 | orchestrator Intake 阶段判定（不写入 SPEC） |
| §12.4 适用边界 | orchestrator Intake 阶段硬性检查（不写入 SPEC） |
| §12.5 三流程矩阵 | 本 SPEC §13.1 任务链（仅 Quick Flow 部分） |
| §12.6 Kanban 任务链 | 本 SPEC §13.1 |
| §12.7 Closeout 自审清单 | 本 SPEC §13.5（操作化） |
| §12.8 风险与降级 | 本 SPEC §13.5 退回策略 |
| §12.8 orchestrator 串行创建风险 | 本 SPEC §13.10 衔接机制契约 |

### 13.8 与完整流程 SPEC 的兼容性

- Quick Flow 不取代完整流程；两种流程在 Kanban 任务创建时由不同的 task body 驱动。
- 与完整流程共享相同的 profile assignee 路由（`yquantprincipal` / `yquantdeveloper` / `yquanttester` / `yquantreviewer`）。
- P-1~P-11 pitfalls 中以下条目在 Quick Flow 中仍然适用：
  - P-1（Skill name collision）✅
  - P-2（dispatcher fallback）✅
  - P-3（Kanban DB task id 不存在）✅
  - P-4（workspace_path 必须用共享项目目录）✅
  - P-5（worker 完成后不要误 block）✅ — Quick Flow 同样适用
  - P-6（T1 完成后用户决策变更）✅ — Quick Flow 的 T1 是 RFC/SPEC/Design 合并 task
  - P-8（跨项目复用前须发现约定）✅
  - P-9（中途变更骨架/命名规范）✅
  - P-10（凭据/环境文件遮蔽）✅
  - P-11（端到端 smoke test 数据合理性）✅
- P-7（编排层越界改模板）在 Quick Flow 中同样禁止。
- P-12（Quick Flow orchestrator 串行创建风险）在 V1.2 中通过 Intake 一次性预创建 T1-T4 消除。

### 13.9 实现约束（Quick Flow 专用）

- T1 task body 必须显式声明"本任务走 Quick Flow"和流程模式定义。
- orchestrator 必须在 Intake 阶段一次性 `kanban_create` T1/T2/T3/T4，T2/T3/T4 通过 `parents` 保持 `todo`，由 dispatcher 自动 promote。
- T1 产出的 DESIGN 文档必须包含自审清单（≥11 项），T4 Closeout 必须逐项执行。
- orchestrator 不得在 Quick Flow 中自动跳过 Verify 阶段。
- 若 Quick Flow 中途发现风险等级被低估，orchestrator 可升级为完整流程（补开 Design 独立 task 或 Review task）。

### 13.10 衔接机制契约

Quick Flow 的阶段衔接必须满足以下契约：

| 编号 | 契约 | 必须 / 禁止 | 验证方式 |
|---|---|---|---|
| Q-LINK-001 | Intake 一次性创建 T1/T2/T3/T4 | 必须 | `kanban_show` / task thread 中可见 4 个 task id |
| Q-LINK-002 | T1 初始可调度 | 必须 | T1 status=`ready` 或已被 claim 为 `running` |
| Q-LINK-003 | T2/T3/T4 初始不可调度 | 必须 | T2/T3/T4 status=`todo` 且存在 parent links |
| Q-LINK-004 | 后续 promote 由 Kanban DB 状态机完成 | 必须 | 前序 done 后无需新建 task，只发生 `todo→ready→running` 状态变化 |
| Q-LINK-005 | 前序 done 后临时创建下一张 task | 禁止 | 若 task created_at 晚于 parent completed_at，Closeout 记录流程缺陷 |
| Q-LINK-006 | orchestrator 主 session / watcher 是唯一衔接机制 | 禁止 | 任何通知丢失不得导致“下一张 task 不存在” |

该契约与 RFC-10-004 §12.6 对齐，并由 DESIGN-10-004 §3.1 的时序图落地。Light Flow 不强制同步修订为四 task 链，但 Implement→Verify 也应优先使用 parent link 预创建，以降低同类断链风险。

## 14. 版本修订说明

- 当前版本：V1.2
- 修订日期：2026-06-30
- 修订摘要：Quick Flow 衔接机制由 orchestrator 串行创建后续 task 改为 Intake 一次性预创建 T1-T4，并新增 Q-LINK 衔接机制契约，要求 T2/T3/T4 以 parent links 预创建为 `todo` 后自动 promote。
