# 历史归档：P-5 事故与旧 SOP

本文全文仅为历史记录（2026-11-14 起），不是当前入口或强制规则，无新任务必读要求；保留事故事实，不按其中配方执行。现行契约见 [canonical SKILL](../../SKILL.md)。

原文件：`skills/infra/ai-coding-pipeline/SKILL.md`。
原章节：details「P-5 历史事故与旧 SOP（全节退役，非当前指令）」。
下方原块按原字节保留；其中相对链接与历史章节号按原文件上下文解释，不作为现行链接或指令。

<!-- ORIGINAL BLOCK BEGIN -->
<details>
<summary>P-5 历史事故与旧 SOP（全节退役，非当前指令）</summary>

以下至 details 结束的“已有 Reviewer 子任务就 blocked”、定时 unblock、旧 API 形状、Verify→Review 链与耗时表全部不生效；只保留历史记录，不执行旧操作。

**症状**：T3 / T4 / T5 阶段 worker 完成后主动调用 `kanban_complete(..., result="review-required: ...")`，状态变为 `blocked` 等 YQuant（orchestrator）来 unblock。但 YQuant 不会自动监控 blocked 状态，pipeline 在这一步**卡住**：下一阶段（T4 / T5 / Closeout）永远等不到 promote。

**观察**（2026-06-27 实战）：T3' 修复完后 worker blocked 26 分钟无人 unblock，T4' 一直 `todo`，用户问"为什么慢"才暴露问题。

**观察**（2026-07-06 实测，yinglong V1.2 T3）：yquanttester worker 跑完 T3 验证（单测 43/43 + e2e 3 命令 exit 0 + 数据 7/7 PASS + 性能 3 项达标 + 向后兼容 PASS），**仍用 `review-required:` blocked**，reason 写"等 T4 启动 + 人类确认是否接受 V1.2 fixture 限制 + 残余 High 风险是否阻塞上线"。**等用户拍板 4 天未动，T4 永远不会被 dispatcher 自动 promote**。**这是 P-5 错误行为的教科书级反例**：worker 把"残余风险已知 + 不阻塞后续"误判为"必须 human 拍板"。

**修复**（worker 行为约束）：

1. **worker 完成后应直接 `kanban_complete(..., summary=...)` 并 `status="done"`，不要 `review-required:` 标记 blocked**。**Reviewer 阶段本身就是独立 review**——不需要 worker 替 reviewer 预告。

2. **仅在以下情况用 `review-required:` blocked**：
   - 任务真的有非阻塞风险需要 YQuant 即时拍板（如生产配置变更、跨产品影响）
   - 已在子任务里创建 Reviewer 任务并 parents 串联

3. **YQuant（orchestrator）侧的补救路径**：发现某个任务 `blocked` 但无后续任务在跑时，可以直接 `kanban_unblock(task_id)`，dispatcher 会重新 claim 并完成。但**这只是补丁**，根因是 worker 误用 blocked。

4. **P-5 健康检查**：流水线中如发现任何任务连续 10 分钟处于 `blocked` 且 heartbeat 缺失，主动 unblock + 在 T5 closeout 报告里记录事件。

**预防**：完整流程跑完后，YQuant 在 T5 closeout 阶段应**主动**核对：
- T1-T5 状态全部 `done`？
- 没有遗留 `blocked` / `running` 但无 heartbeat 的孤儿任务？
- 如果有，立刻 unblock 或归档。

#### block vs done 决策树（worker 行为约束，2026-07-06 新增）

**核心问题**：worker 跑完验证后，应选 `done` 还是 `blocked`？判定标准：

| 完成情况 | 状态选择 | 理由 |
|---|---|---|
| 验收标准 PASS + 残余风险已知但不阻塞 + 无 Reviewer 子任务 | **`done`** | dispatcher 自动 promote 下一阶段；残余风险写进 `summary` 或 `metadata.residual_risks` |
| 验收标准 FAIL（测试不通过 / 数据错配 / 代码未跑通） | **`blocked`** | 真正阻塞，需 orchestrator 介入修复 |
| 高风险变更需 human 拍板（生产 schema / 凭据 / 跨产品影响） | **`blocked`** | 需人类判断才放行 |
| 已创建 Reviewer 子任务并 `parents` 串联 | **`blocked`** | worker 预告 Reviewer 介入是合法的 |
| **残余 High 风险待 human 拍板**（如真实 e2e 凭证缺失、依赖未验证） | **`done` + 写进 `residual_risks`** | **不构成 block 理由**！除非这个风险**阻断后续阶段** |
| 验收 PASS 但 worker 自己"觉得"需要确认 | **`done`** | worker 替 Reviewer 预告是越权 |

**P-5 黄金法则**：

> **PASS = done（残余风险进 summary/metadata）；FAIL = blocked（写明失败原因 + 哪条验收不达标）。** 两类结果之间不存在中间态。如果 worker 觉得有"需要确认的事"，写进 `summary` 的 "已交付但需确认项" 段，让 Reviewer 阶段或人类在 Closeout 时统一处理。

**判定流程**（worker 写 `kanban_complete` 前的自检）：
1. 跑一遍 task body 列出的验收标准 → 全 PASS？
2. 如果全 PASS → 残余风险是"已知但不阻塞"还是"真正阻塞后续"？
3. 已知不阻塞 → `done` + 风险进 `summary`
4. 真正阻塞 → `blocked` + 写明阻塞原因 + 哪条验收待补
5. 验收 FAIL → `blocked` + 写明哪条 FAIL + 期望值 vs 实际值

**task body 应有的明确指令**（orchestrator 派卡时建议写入）：
```
完成后状态选择：
- 验收标准全 PASS → kanban_complete(status="done", summary=..., metadata={residual_risks: [...]})
- 任何验收 FAIL → kanban_complete(status="blocked", reason="<哪条 FAIL + 期望 vs 实际>")
- 不要因"残余风险待确认"使用 blocked——残余风险属于 done 的 summary/metadata
```

**与 P-2 的关系**：worker 也会因 dispatcher 透明 fallback 跑错模型而 hidden 失败，状态可能误标 `done`。P-5 关注**状态机正确**；P-2 关注**完成的内容质量**。两者都需要监控。

**建议每阶段预期耗时**（基于 2026-06-25 / 06-27 实战均值）：

| 阶段 | 典型耗时 | 主要耗时点 |
|---|---|---|
| T1 RFC/SPEC | 5-10 分钟 | yquantprincipal LLM 推理 |
| T2 Design | 5-10 分钟 | yquantprincipal LLM 推理 |
| T3 Implement | 5-15 分钟 | yquantdeveloper LLM + 测试运行 |
| T4 Verify | **5-15 分钟** | yquanttester 跑测试集 + dry-run 验证 |
| T5 Review | 5-10 分钟 | yquantreviewer LLM 推理 |

> **异常长耗时（如 T4 > 30 分钟）通常说明**：worker 卡在某个测试用例 / LLM 推理 hang / 模型 fallback 慢。可以 `kanban_list status=running` 查 PID + `process(action='poll')` 看 heartbeat 时间。

</details>
<!-- ORIGINAL BLOCK END -->
