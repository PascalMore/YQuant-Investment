# 历史归档：2026-06-29 Quick Flow 五阶段日志

本文全文仅为历史记录（2026-11-14 起），不是当前入口或强制规则，无新任务必读要求；保留事故事实，不按其中配方执行。现行契约见 [canonical SKILL](../../SKILL.md)。

原文件：`skills/infra/ai-coding-pipeline/SKILL.md`。
原章节：「Quick Flow 5 阶段流程模式（2026-06-29 历史日志，全部退役）」整节，止于参考资料前。
下方原块按原字节保留；其中相对链接与历史章节号按原文件上下文解释，不作为现行链接或指令。

<!-- ORIGINAL BLOCK BEGIN -->
## Quick Flow 5 阶段流程模式（2026-06-29 历史日志，全部退役）

> 本节全文仅是历史，不是当前入口。2026-06-30 V1.2 本身也已于 2026-11-14 退役；以下“当前规则”仅指历史时点，不适用于新任务。

> ⚠️ **历史快照**：本节是 2026-06-29 首次落地 Quick Flow 时的实现日志，**当前流程规则已由 2026-06-30 V1.2 改造取代**：① Intake 必须一次性预创建 T1-T4 全部（不是串行）；② parent links 全链 `[T1]/[T1,T2]/[T1,T2,T3]`（不是简化版 `[T1]/[T2]/[T3]`）；③ Closeout 自审清单 13 → **15 项**（含 #1/#2 Intake 预创建核验）；④ 适用 pitfall P-1~P-11 → **P-1~P-12**（含 V1.2 新增的 P-12 orchestrator 串行调度风险）。本节保留作为历史参考，**不要**当当前规则使用。

> 完整 RFC/SPEC/Design 文档：RFC-10-004 §12 / SPEC-10-004 §13 / DESIGN-10-004（yquant 项目 `docs/` 下 V1.2 版本为准）

**5 阶段 4 task Kanban 链（历史版本，仅供参考）**：
```
T1 RFC/SPEC/Design   (yquantprincipal)   ← 1 task 产 3 份独立文档
T2 Implement         (yquantdeveloper)   parents=[T1]
T3 Verify            (yquanttester)      parents=[T2]
T4 Closeout          (orchestrator)      parents=[T3]
```

**适用边界**：中等风险、明确需求、改动 3-8 文件、单模块、不触交易/风控

**与 Full / Light 区别（历史）**：
- Full Flow (7 阶段 / 6 task)：高风险、跨模块、交易/风控 → 保留独立 Review
- **Quick Flow (5 阶段 / 4 task)**：中风险 → 去掉 Review，以 **Closeout 自审清单 (13 项 → V1.2 已扩 15 项)** 替代
- Light Flow (3 阶段 / 2 task)：单文件低风险 bug fix / 注释 / 格式

**Quick→Full 升级路径**：
- T1 RFC/SPEC/Design 阶段发现改动实际跨模块 → 把 T2 后面的 task 改成 Full 链
- T2 Implement 阶段发现触动交易/风控逻辑 → 升级到 Full Flow 补 Review 阶段
- Orchestrator 应在 T2 任务 body 显式声明升级条件

**失败模式**（Orchestrator 监控信号）：
- T1 done 后 T2 一直 ready 未 claim → 父任务检查失败
- T2 done 后 T3 一直 ready 未 claim → 同上
- 任何 task done 通知到达但 children 24h 内未 promote → 主动 unblock + 记录事件
- T3 Verify 发现 P-11 端到端数据不合理 → 升级到 Full Flow 重新跑

**P-1~P-13 pitfalls 全部适用于 Quick Flow**（2026-07-01 实测新增 P-1c worker profile `external_dirs` 必须覆盖目标项目 skills 目录）
<!-- ORIGINAL BLOCK END -->
