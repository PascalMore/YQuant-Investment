# 历史归档：2026-08-19 部署分流准则

本文全文仅为历史记录（2026-11-14 起），不是当前入口或强制规则，无新任务必读要求；保留事故事实，不按其中配方执行。现行契约见 [canonical SKILL](../../SKILL.md)。

原文件：`skills/infra/ai-coding-pipeline/SKILL.md`。
原章节：details「历史：2026-08-19 部署分流准则（全节退役，非当前指令）」。
下方原块按原字节保留；其中相对链接与历史章节号按原文件上下文解释，不作为现行链接或指令。

<!-- ORIGINAL BLOCK BEGIN -->
<details>
<summary>历史：2026-08-19 部署分流准则（全节退役，非当前指令）</summary>

以下至 details 结束的旧 Quick 分流、卡数及角色合并规则全部不再用于新任务。保留当时事实，不执行其操作配方；现行只使用 Full/Light 和统一 Validate。

**核心原则**：当任务涉及生产部署、上线切换、`_EXECUTION_MODE`/其他生产常量切换、capability install、binding 替换等场景时，**状态机精简到 1-2 个状态**，门禁精简到 ≤3 项，**不强制走 SPEC/RFC/DESIGN 三层文档 + P1-P6 阶段门禁**。

### 反例：RFC-18-016 §3.1 的 4 状态机（已禁止照搬）

```text
contract-ready → artifact-ready → runtime-ready → execution-ready
                  （4 状态机 + P1-P6 阶段门禁 = 实际 8-10 张卡才能完成单点切换）
```

这种结构对生产部署/上线/切换类任务是**过度流程化**，成本 8-10 张卡却只换一行常量值。

### 精简准则（≤2 状态、≤3 门禁）

| 任务类型 | 状态数 | 状态名 | 门禁 |
|---|---|---|---|
| **生产部署 / 模式切换 / capability install** | **1** | `preflight-ready` | ① fixture 桥完整 ② 真实 I/O 受 O_EXCL 等原子原语保护 ③ 文档同步 SPEC denylist 即可 |
| **真实 execute_once / execute-write** | **2** | `preflight-ready` + `execution-ready` | `preflight-ready` + ① single-binding active ② Pascal fresh 一次性授权 |
| **legacy retirement / observation phase** | **2** | `verify-clean` + `retired` | ① 健康证据只读 ② legacy invocation evidence = 0 |

### 走法选择（替换 SPEC-18-016 §3.1 决策树）

```
生产部署/上线/模式切换任务到达
   │
   ├─ 仅修改常量（如 _EXECUTION_MODE=execute）？
   │    └─ 是 → **Light Flow**（1-2 文档 + 1-2 卡）
   │            （不再走 P1-P6 阶段，不创建 SPEC/DESIGN 三件套）
   │
   ├─ 真实 execute_once（涉及 capability install / 单次写入）？
   │    └─ 是 → **Quick Flow**（RFC+SPEC 合并 1 卡 + Implement + Verify）
   │            （简化独立 Tester/Reviewer 为 Verify 内嵌两个独立角色确认）
   │
   └─ 跨模块架构变更？
        └─ 是 → **Full Flow**（保留原 6 卡）
```

### 何时仍需要完整三档

- 跨 ≥2 个模块的架构变更
- 涉及交易/风控/真实资金的真实写
- 跨 ≥3 个 deny list 项的变更

### 历史教训（2026-08-19 B1/T5 后卡链）

- **症状**：B1 完成后用户要切换 `_EXECUTION_MODE=dry_run → execute`，orchestrator 默认按 SPEC-18-016 §3.1 的 4 状态机 + P1-P6 阶段门禁，估算需 RFC-18-019 + SPEC-18-019 + DESIGN-18-022（3 文档）+ T1-T5（5 卡）= **8 张卡才能切换一行常量**。
- **根因**：状态机本身过度细化（4 状态 + 6 阶段门禁），把"切换常量"与"真实部署"混为一谈。
- **修复**：本节准则将单点切换拆为 Light Flow（1-2 卡），保留独立 Tester/Reviewer 仅在真实 execute_once 时出现。

### 配套规则

- **状态名要少**：≤2 个，禁止 `contract-ready / artifact-ready / runtime-ready / execution-ready` 这类四段命名
- **门禁要少**：每状态 ≤3 项检查，禁止 P1-P6 的 6 阶段累加
- **单步落地**：常量切换 = 1 卡，不再拆 IMPLEMENT/VERIFY/REVIEW/CLOSEOUT 四卡
- **denylist 同步**：每次简化必须在原 SPEC（如 SPEC-18-016）的 §10 显式同步新增豁免，避免下一次 orchestrator 又按旧规则展开

### 与三流程定位（Full/Quick/Light）的关系

本节**替换** §"三流程定位"中的"Full Flow 适用于高风险、跨模块、交易/风控"边界 ——
**生产部署/上线/模式切换类任务**即使属于"高风险"，也按本节走 Light Flow 起步，**除非**额外触发"完整三档"条件。

---

</details>
<!-- ORIGINAL BLOCK END -->
