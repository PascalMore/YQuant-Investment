---
name: design-baseline-reconciliation
description: 在工程流水线中对齐 RFC/SPEC/Design 与当前共享工作树的已验证实现基线，防止把已完成能力误列为待实现。
---

# Design Baseline Reconciliation

适用于已有实现、修复链或并行卡之后，对 RFC/SPEC/Design 进行新增、修订或 Design Gate 审计的工程任务。尤其用于“文档说 not yet，但代码与 Verify 已完成”的漂移风险。

本 skill 是对项目 AI Coding Pipeline 的补充门禁：不改变角色拆分和正式 Kanban 流程。

## 触发信号

满足任一项即执行本流程：

- Design 将已有 schema、`from_dict()`、stub、fixture、服务方法或测试列为 T3 待实现。
- 已完成的修复链改变了“已实现 / 未实现”的事实，但三层文档仍含旧 checkbox、状态表或 allowlist。
- Developer 的 allowlist 含有无法指出真实缺口的文件。
- Design amendment 只修改了 Design，却影响 RFC/SPEC 的阶段状态或验收语义。

## 目标

1. 让文档准确描述**当前已验证的离线基线**。
2. 将 Implement 范围收缩到确实未完成、可定位的最小工作。
3. 保持“离线已实现”与“生产已激活”严格分离。
4. 在任何 Implement 前消除 RFC/SPEC/Design 的阶段状态冲突。

## 操作步骤

### 1. 建立事实优先级

按以下顺序确定事实，不以旧文档的待办推断当前代码状态：

1. 当前共享工作树中目标文件与符号。
2. 最近独立 Verify / Review 的结果与所运行命令。
3. 变更链的明确用户裁定。
4. RFC、SPEC、Design 的既有描述。

共享树并行时，只能按本卡 allowlist 做 path-filtered diff 归属；禁止 reset、stash、clean 或用全树 dirty 状态否定当前卡。

### 2. 逐项做“已完成 / 真实缺口”分类

对 Design 或 T3 allowlist 的每个 artifact 建立分类：

| 分类 | 判据 | 文档处理 |
|---|---|---|
| 已验证离线基线 | 文件/符号存在，且有相关独立测试或验证证据 | 标注 `existing offline baseline`；从 T3 待办移除 |
| 未验证既有代码 | 文件存在但无可接受证据 | 不得宣称已完成；列为验证缺口而非直接重写 |
| 真实实施缺口 | 可精确指向缺少的字段、函数、guard、映射或测试 | 保留在 T3，写明文件、符号和验收测试 |
| 生产激活缺口 | real provider、网络、Mongo、DDL/DML、refresh happy-path、canary/live smoke | 归 P1/P2 或项目授权 Gate，不得混入离线 T3 |

### 3. 收缩 Design 与 Implement 范围

- 不重复实现已验证的 domain object、fixture、stub 或现有测试。
- 对每个保留的 T3 项，必须给出：`文件路径 + 符号/字段集 + 为什么当前缺失 + 最小测试`。
- “文档推断未实现”不是证据。
- 若某能力仅为 fail-stop 或 injected-not-implemented，准确描述它的当前状态；不得将其宣传为 real fetch 或写入能力。

### 4. 三层同步扫描

只要状态从“未实现”变为“已验证离线基线”，就扫描 RFC/SPEC/Design 中的：

- 阶段状态表、capability matrix、checkbox；
- developer allowlist 与测试矩阵；
- 验收条款、残余风险表和版本历史；
- 相关 schema、唯一键及 freshness/trace 约束。

若 Design 已修正但 RFC/SPEC 仍保留冲突叙述：

1. **禁止派发 Implement**。
2. 先派 Principal 做最小 RFC/SPEC amendment。
3. 完成后再做 Design 一致性复核。
4. 确认三层一致后，才派最小 Implement。

### 5. 保留边界与未决裁定

- 不得因对齐离线文档而擅自选定 schema、freshness key、交易/风控或持久化语义。
- 用户未裁定的冲突明确标为冻结，列入 residual risks；不能写成“已解决”。
- 离线基线完成不表示任何真实 Provider、Mongo persistence、DDL/DML、refresh、canary 或 live smoke 已完成。

## 验收标准

- T3 allowlist 中每项均有真实缺口证据。
- RFC/SPEC/Design 不再对同一 artifact 的实现状态作出矛盾声明。
- 文档改动通过 `git diff --check`。
- 共享树范围审计只报告本卡 allowlist 内的变动；无破坏性 Git 操作。
- 文档类卡不触发网络、HTTP、Mongo、DDL/DML、refresh、服务或 cron。

## 常见陷阱

- **只看旧 Design**：会把已修复的实现重复列入 T3。
- **只改 Design**：RFC/SPEC 的旧 checkbox 会重新制造设计门禁冲突。
- **把 offline ready 说成 production ready**：掩盖真实外部数据、持久化与授权 Gate。
- **依赖全树 git status 判断越界**：共享工作树中其他链的变更不是当前卡范围。

## 参考案例

- `references/p3-p0-baseline-drift.md`：P3-P0 共享树中“已验证 22-field 离线基线被误列为 T3 待办”、以及随后发现 RFC/SPEC checkbox 未同步的简要案例。

## 与其他技能的关系

- 正式阶段、Kanban 角色和审批语义：遵循 `yquant-ai-coding-pipeline`。
- 文档三层结构与交叉引用：配合 `pipeline-doc-consistency`。
- Implement 前的文件范围与可计算契约审计：配合 `design-gate-audit`。
