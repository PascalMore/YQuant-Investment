# 范围裁定 Cascade：从用户裁定到三层文档 scope-scission 再到 master Re-baseline

来源：2026-08-04 Unified Data Phase-3 R2（Pascal 裁定 `name_em` 实时板块排行移出 Phase 3 目标）。

## 适用场景

用户在中途裁定某 capability **移出本期实现/生产验证目标**（out-of-scope），但该能力已存在于既有文档的 Gate 表、PR 系列、副作用矩阵和状态矩阵中。此时不是"在 changelog 加一行"，而是需要一层一层把可执行契约标为 superseded/out-of-scope，并禁止一切重试/替代 endpoint/live retry。

## 完整链条（本会话验证可行）

```text
1. 用户裁定 → 2. incident/scope 卡 comment 记录裁定（含禁止项）
   → 3. 专用 Gate 三层文档 scope-scission（RFC/SPEC/DESIGN 各自新增 R2 章节）
   → 4. 独立 Verify（三份裁定体 sha256 一致性 + 无残留可执行 PR-2 + 既有契约未破坏）
   → 5. Final Review（0/0/0 APPROVE）
   → 6. master RFC/SPEC Re-baseline（V0.27：新增 §R2 五节 = 完成矩阵 + Gate 授权骨架）
   → 7. 独立 Verify（此处常 FAIL：SPEC 只改 changelog 没落正文）
   → 8. P0 Fix（V0.28，按 FAIL 行号清单逐条修复）→ 9. 第二轮独立 Verify（逐行回核闭环）
   → 10. Final Review → 11. Design（master DESIGN 同步）→ 12. 生产 Gate（需用户逐项授权）
```

## 关键动作细节

### 1. 裁定落档
- 在相关 incident/scope 卡上 comment：能力移出目标、**预算永久废弃**、旧卡标 superseded/historical evidence、禁止项清单（不得 retry/替代 endpoint/实时 refresh/live retry；保持既有禁止如 `cons_em`）。

### 2. 三层文档 scope-scission
- 每份文档独立升版本（RFC V0.3→V0.4、SPEC/DESIGN V0.2→V0.3），各自新增 R2 章节。
- 三份裁定体**逐项一致**，Verify 用 `sha256sum` 抽取比对（注意不同 worker 抽取窗口/归一化会导致 hash 不同，以"字节级一致性独立确认"为准，不要因 hash 值不同误判）。
- 原则：保留历史事实，不删除章节，只追加 (R2) superseded/out-of-scope 标记；P0 incident record 不得删除/改写，只允许追加指向新章节的一行。

### 3. master Re-baseline
- master RFC/SPEC 各自升版本（V0.26→V0.27），新增 §R2 五节：范畴裁定 / 六 capability 完成矩阵（冻结允许最终状态）/ 关键冻结语义 / 四 Gate 授权骨架 / 一致性声明。
- 完成矩阵把每项 capability 的允许终态冻结（如 out-of-scope / production-read-path-validated / provider-unavailable-frozen / intentionally-unavailable），禁止把"失败/未实现/范围外"写成成功。

### 4. Verify 的声明先行陷阱（本会话核心教训）
- **changelog 声称已同步 ≠ 正文已同步**。第一轮 Verify 对 V0.27 FAIL 的三类证据：
  - FAIL-1：SPEC changelog 声称"新增 §R2 章节"、§0 引用"见 §R2"，但正文无 `## R2` → 悬空引用。
  - FAIL-2：SPEC 正文 19 处残留可执行 PR-2 契约未标记（§10.bis PR-2/PR-DDL-P3A、§7 A-018、§10 G-A-2、§14.x、§P0.x、§P1.x），与 changelog 声称"已统一标记"不符；RFC 对应章节已标记但 SPEC 未同步。
  - FAIL-3：RFC 亦有 8 处残留，其中 §13.4.5.8 裁决表仍写"仅允许后续单变量网络诊断后重试 live-read"，**与 R2 禁 live-retry 直接冲突**（禁止性语义冲突，P0 级）。
- Verify 必须：`grep '^## R2'` 证实章节存在；对 changelog 声称的每个行号逐一核验正文标记；补扫全文残留命中并归类（可执行表述 vs 纯历史 changelog/冻结证据行）。

### 5. P0 Fix 闭环
- Fix 卡把 Verify 的 FAIL 行号清单**原样内嵌**为修复清单，每个条目给"旧文本 → 新文本"期望。
- 修复原则：保留历史（删除线 + superseded 标注），PR-DDL 触发条件改写为"仅当未来新 Provider Gate + Pascal 独立确认"，不删除章节。
- 第二轮 Verify 逐行回核 FAIL 清单；补扫残留时允许把"章节级 R2 注覆盖"和"历史 changelog/冻结证据行"归类为不算残留（需说明）。

## 复现数据（2026-08-04 会话）

- 卡链：`t_51c36693`(scope-scission) → `t_5dfe3499`(Verify PASS) → `t_b64c69fc`(Review APPROVE) → `t_e84d9e0d`(Re-baseline V0.27) → `t_876a30bd`(Verify FAIL×3) → `t_164c4f55`(P0 Fix V0.28) → `t_8180cb80`(第二轮 Verify)。
- 两张大文档 Principal 卡（Re-baseline、P0 Fix）均 60/60 迭代预算超时但产物完整；用"超时核验 + 重试 comment 带完整 checklist"fast-path 让重试 run 5-10 分钟只读收口（见 SKILL.md Timeout 段）。
