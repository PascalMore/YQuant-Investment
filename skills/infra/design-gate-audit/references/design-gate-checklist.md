# Design Gate 审计清单（session reference）

> 用于 T2 → T3 的独立审计记录；保留具体任务 ID、文件路径与命令输出在 Kanban comment，不写入本通用模板。

## A. 阶段与范围

- T2 授权允许修改：`<paths>`
- 工作树新增/修改实现与测试文件：`<paths>`
- 结论：`PASS | 越界 stub，需清理卡`
- 检查：`git status --short -- <implementation> <tests>`、`git diff --check`

## B. 三层契约一致性

| 契约 | RFC | SPEC | Design | 复算/静态证据 | 结论 |
|---|---|---|---|---|---|
| 分支/场景 | | | | | |
| 评分/阈值 | | | | | |
| warning/reason code | | | | | |
| trace/audit schema | | | | | |
| 回滚/降级 | | | | | |

## C. 数值矩阵核对

对每个示例记录：

```text
raw_score = Σ(weight_i × dimension_i) = <value>
tier boundary = <definition>
classification(raw, before display rounding) = <tier>
document value/tier = <value/tier>
```

若 raw 值与文档 tier 不一致，属于阻塞问题；不得通过展示四舍五入掩盖。

## D. 副作用矩阵

| 行为 | fake/noop 是否可测 | 是否涉及真实 DDL/写入 | Pascal 明确确认 | T3 是否允许 |
|---|---:|---:|---:|---:|
| 纯计算/内存状态 | | | 不需要 | |
| 审计/汇总 mock | | | 不需要 | |
| Mongo collection/index | | | | |
| 真实持久化写入 | | | | |
| 真实外部 provider smoke | | | | |

## E. 处置结论

- **PASS**：创建 T3 Implement，并把审计结论与精确文档路径写入 task body。
- **DOC-CORRECTION**：创建 principal 的文档修正卡；限定到三层文档，不允许夹带代码。
- **SCOPE-CLEANUP**：创建 principal 的清理卡；精确列出越界文件，清理后重新审计。
- **PRODUCTION-GATE**：拆出受确认控制的后续阶段；当前 T3 仅允许 fake/noop 实现。
