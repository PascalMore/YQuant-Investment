# 2026-06-25 真实运行日志：RFC-03-006 流水线从 Design 到 Implement

> 退役说明（2026-11-14 起）：本文全文仅为历史记录，不是当前入口或强制规则，无新任务必读要求；旧事实保留，不得按旧阶段链或事故配方执行新任务，也不得以 Closeout 自审替代独立 Validate 验收。

> 本文为真实事故和故障定位的历史复盘记录，不替代 SKILL.md 的现行契约。

## 时序概览

```
2026-06-24 22:24  用户首次提"codex principal 是否在工作"——发现昨晚 SPEC-03-006
                 是 yquant (M3) 写的（以为委派给 yquantprincipal 实际是父 profile）
2026-06-25 19:25  SPEC-03-006 + RFC-03-006 已写完，Design 阶段空缺
2026-06-25 19:25  修复 SKILL.md 路径引用（scripts/infra → skills/common/utils）
2026-06-25 19:30  Round 1 冒烟测试失败：worker crash（exit 1），skill name collision
2026-06-25 20:30  Round 2 冒烟测试通过：删除 4 个 worker profile 副本后，gpt-5.5 跑通
2026-06-25 20:39  Design 任务派发（t_7656d56b，assignee=yquantprincipal）
2026-06-25 21:00  gpt-5.5 重试 3 次 ConnectionError → fallback zai/glm-5.2
2026-06-25 21:00  glm-5.2 撞 429 → fallback MiniMax-M3
2026-06-25 21:01  M3 完成 Design 落盘 45KB / 702 行
```

## 关键观察 1：Kanban dispatcher spawn 真实姿势

```python
# dispatcher 内部行为（来自 kanban_db.py:6802 _default_spawn）：
cmd = [
    *_resolve_hermes_argv(),      # /home/pascal/.../hermes
    "-p", profile_arg,             # 切到目标 profile
    "--accept-hooks",
    "--skills", "kanban-worker",   # 内置
    "--skills", task_skills,       # 任务级 skill（可多个 --skills）
    "chat",
    "-q", "work kanban task <task_id>",
]
env["HERMES_HOME"] = resolve_profile_env(profile_arg)  # 切到 ~/.hermes/profiles/<name>/
```

worker 启动后：
1. 用 `HERMES_HOME` 加载目标 profile 的 `config.yaml`
2. 自动 load `kanban-worker` skill + 任务级 skill
3. worker 主动调 `kanban_list / kanban_show` 读任务 body
4. 完成后必须 `kanban_complete` / `kanban_block`，否则 dispatcher 视作 crash

## 关键观察 2：Skill name collision 触发 worker 启动崩溃

**Round 1 冒烟测试日志**（19:49:30）：

```
WARNING tools.skills_tool: Skill name collision for 'yquant-ai-coding-pipeline':
  2 candidates —
    /home/pascal/.hermes/profiles/yquantprincipal/skills/infra/yquant-ai-coding-pipeline/SKILL.md
    /home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/SKILL.md
```

**之后日志完全停止**——没有 `agent.turn_context`，没有 `API call #1`，没有进入对话循环。worker 在加载 skill 阶段就 crash，exit code=1。

**task_runs 表记录**：
- run #1: pid 962942, exit_code=1, outcome=crashed
- run #2: pid 963187, "not alive" (实际上第二次根本起不来)
- events: created → claimed → spawned → crashed → claimed → spawned → crashed → gave_up

**修复**：删除 4 个 worker profile 的 skill 副本后，Round 2 通过。

## 关键观察 3：gpt-5.5 fallback 链观察

**worker session 20260625_203932_de9e1b 的真实调用链**（Design 任务）：

```
20:39:40  primary: gpt-5.5 / openai-codex          ← 设计意图
20:41:53  ❌ APIConnectionError (attempt 1/3, ~2min wait)
20:44:06  ❌ APIConnectionError (attempt 2/3, ~2min wait)
20:46:24  ❌ APIConnectionError (attempt 3/3)
20:46:24  primary_recovery 重试
20:48:42  ❌ APIConnectionError (attempt 1/3, 第二轮)
20:50:55  ❌ APIConnectionError (attempt 2/3, 第二轮)
20:53:14  ❌ APIConnectionError (attempt 3/3, 第二轮)
20:53:17  ✅ Fallback activated: gpt-5.5 → glm-5.2 (zai)
20:53:25  glm-5.2 API call #1 (latency 824s 第一次冷启动)
20:53:34  glm-5.2 API call #2 (latency 9.2s)
... 16 次 glm-5.2 调用 ...
21:00:22  ❌ RateLimitError HTTP 429 (zai/glm-5.2)
21:00:22  ✅ Fallback activated: glm-5.2 → MiniMax-M3
21:00:38-21:01:42  M3 完成剩余 ~12 次 API call
```

**结论**：yquantprincipal 的 fallback 链 `gpt-5.5 → zai/glm-5.2 → custom:minimax/MiniMax-M3` 是设计意图。这次 gpt-5.5 不可达（chatgpt.com 网络或 OAuth 问题）触发 zai，zai 撞 429 又触发 minimax。**任务完成**但 DESIGN-03-006 是 M3 写的，不是 gpt-5.5。

**如何监控 fallback**：

```bash
grep -E "Fallback activated|API call.*model=" \
  ~/.hermes/profiles/<worker>/logs/agent.log | grep "<session_id>"
```

## 关键观察 4：dispatcher silent crash detection

`kanban_dispatch` 的 reap 逻辑（来自 `hermes_cli/kanban_db.py:5537-5580`）：

1. **每分钟扫一次** `tasks` 表 status=running 且 worker_pid IS NOT NULL 的任务
2. **PID 不在** → 标记 crashed，递增 `consecutive_failures`
3. **failure_limit=2**（dispatcher 级）连续 2 次 crash → 自动 `blocked` + 写 `gave_up` event
4. **protocol_violation**（rc=0 但没调用 kanban_complete）→ failure_limit=1（立即 trip）

所以**两次 skill collision crash** 是 dispatcher 主动放弃的，不是手动 block。修复后重派任务**必须先清理** task_runs 和 task_events，否则 `consecutive_failures` 仍累计。

## 关键观察 5：任务清理模板

```python
import sqlite3
conn = sqlite3.connect('/home/pascal/.hermes/kanban.db')
task_id = "<t_xxx>"
for tbl, col in [("task_events","task_id"),("task_runs","task_id"),
                 ("task_links","parent_id"),("task_links","child_id"),
                 ("task_comments","task_id"),("task_attachments","task_id"),
                 ("kanban_notify_subs","task_id")]:
    conn.execute(f"DELETE FROM {tbl} WHERE {col} = ?", (task_id,))
conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
conn.commit()
```

注意 `consecutive_failures` 字段：删除 task 记录就一并清零了，无需额外处理。

## 已知未解决

- **gpt-5.5 不可达的根因**：2026-06-25 21:00 时段 chatgpt.com ConnectionError。可能原因：(a) 代理配置（~/.bashrc 缺小写 http_proxy）；(b) OpenAI OAuth 凭证过期；(c) ChatGPT 账号限流。待排查。
- **zai/glm-5.2 撞 429**：可能是 z.ai 5h 共享 prompt 池子暂时打满，需观察 1-2h 后是否恢复。
- **DESIGN-03-006 是否需要重做**：当前 M3 写的版本 45KB / 702 行结构合规，但缺 gpt-5.5 视角。Pascal 拍板前不再重做。

## 关键观察 6：Pipeline 不会自动串联的根因（2026-06-25 RFC-03-006 案例）

**症状**：Design 完成后 dispatcher 没有自动 promote Implement 到 ready，必须 orchestrator 手动 `kanban_create` 派下一个阶段。

**根因链**：

1. 昨夜（00:30 ~ 00:55）RFC/SPEC 用**文本声明 + `delegate_task`** 跑完
2. `delegate_task` **不在 Kanban DB 创建 task 记录**——产物在 `docs/` 但 DB 里查不到 task_id
3. 今天派 Design 时 `parents=[SPEC_task_id]` 无法设置（SPEC 不在 DB 里）
4. Design 不带 parent dependency 直接 ready，跑完后 dispatcher 看"无 parent 链" → 不知道下一步该 promote 谁
5. 必须 orchestrator 手动派后续 Implement / Verify / Review / Closeout

**修复方向（预防未来任务）**：

- **所有流水线阶段都必须用 `kanban_create`** 派任务，不再用 `delegate_task` 承担正式流水线阶段
- **每个阶段都设 `parents=[前阶段 task_id]`**，dispatcher 才能自动 promote
- 父任务"已存在"的标准是 **Kanban DB 里有 task_id**，单看 `docs/` 目录下的 md 文件不算
- 历史遗留产物（无 task_id）只能手动一个个阶段派下去，没法走自动串联

## 关键观察 7：模块路径要在 SPEC 阶段就明确（2026-06-25 RFC-03-006 案例）

**症状**：Implement 阶段 worker 把 providers 包写到 `scripts/providers/` 而非 `scripts/extractors/providers/`，与 orchestrator 预期路径不一致。

**根因**：SPEC-03-006 和 DESIGN-03-006 §3 文件清单没有显式约束"providers 包放在哪一层"。worker 选择了顶层 `scripts/providers/`，不算违反 Design，但和 orchestrator 的预期有偏差。

**修复方向（SPEC 阶段必做）**：

- SPEC §3 "涉及文件清单" 必须**精确到目录路径层级**（包括 sub-package 应该放哪）
- 不能写"新建 `providers/` 子包"这种模糊描述，要写"在 `scripts/extractors/providers/` 下新建 10 个文件"
- 涉及已有文件路径改动时，必须列出**完整相对路径**而不是缩写

## 复现 recipe

如果要再做一次端到端验证：

```bash
# 1. 验证 skill 副本只剩 yquant 一份
find ~/.hermes/profiles -name "SKILL.md" -path "*yquant-ai-coding-pipeline*"

# 2. 验证 dispatcher 在跑
grep "kanban dispatcher" ~/.hermes/profiles/yquant/logs/gateway.log | tail -1

# 3. 派一个不写文件的冒烟任务
hermes chat -q "work kanban task <task_id>" --pass-session-id -Q \
  HERMES_HOME=~/.hermes/profiles/yquantprincipal/ \
  HTTP_PROXY=http://172.25.240.1:7897 \
  HTTPS_PROXY=http://172.25.240.1:7897

# 4. 监控 worker 模型使用
watch -n 5 "tail -50 ~/.hermes/profiles/yquantprincipal/logs/agent.log"
```