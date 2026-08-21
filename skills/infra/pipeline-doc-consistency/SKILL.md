---
name: pipeline-doc-consistency
description: "Review and synchronize RFC/SPEC/Design document sets before implementation, especially when late user decisions change storage, schema, naming, or module boundaries."
---

# Pipeline Document Consistency

Use this skill when a YQuant / AI Coding Pipeline effort has multiple RFC / SPEC / Design documents and the user asks for a unified review, implementation readiness check, or late-stage correction before Implement.

## Trigger Conditions

Load this skill when:

- A feature has RFC + SPEC + Design documents across one or more modules.
- The user changes a design decision after RFC/SPEC were already produced.
- The decision affects persistence, database type, collection naming, schema, API boundary, task sequencing, or module ownership.
- A reviewer returns `PASS_WITH_FIXES` or `REVISE` for document consistency.
- You are about to create an Implement task from completed planning docs.
- You have just merged a layered docs-only remediation and want to close it out.
- A Implement / Verify task reached `done` or `timed_out` while the shared worktree still carries uncommitted diff.

## Core Principle

Late user decisions that change **how the system is designed** are not implementation details. They must be synchronized back into every affected planning layer before developer work starts.

Common examples:

- SQLite vs MongoDB.
- Collection prefix naming.
- Production vs test database boundary.
- Read-only adapter vs write path.
- Phase numbering ambiguity, e.g. “Phase 0-7” must be described as 8 numbered phases when Phase 0 is included.
- Adapter phase scope corrections, e.g. if a read-only adapter phase references TA-CN core data, check index/sector collections are not omitted from RFC/SPEC/Design/SKILL.md.
- Which module owns scheduling, data access, or persistence.
- Which documents / phases are authoritative for the first implementation task.

## Workflow

1. **Inventory documents**
   - List all RFC / SPEC / Design files in scope.
   - Group them by module or feature line.
   - Confirm each line has the expected three layers.

2. **Extract hard decisions**
   - Pull user decisions from the current conversation and latest Design Overrides.
   - Classify them as architecture / design / implementation detail.
   - Architecture and design decisions must be reflected in RFC/SPEC/Design, not just task bodies.

3. **Search for stale semantics**
   - Search for old database/storage names, old collection prefixes, old module IDs, deprecated phase descriptions, and old implementation order.
   - Do not rely on a single Design Override if the RFC/SPEC body still says the opposite.
   - **Re-grep every forbidden token across all three layer files** — see Cross-Doc Token-Residual Gate below.

4. **Patch planning docs before Implement**
   - Add a clear “Design 阶段修订说明” or changelog note to earlier layers.
   - Replace stale main-path descriptions in the body.
   - Preserve historical alternatives only in Alternatives / Out of Scope sections and label them as not selected.

5. **Run a consistency review**
   - For non-trivial multi-doc sets, create a real reviewer Kanban task.
   - Ask for verdict: `PASS`, `PASS_WITH_FIXES`, or `REVISE`.
   - If `PASS_WITH_FIXES`, fix blocking items before creating Implement tasks.

6. **Create the first Implement task only after blockers are cleared**
   - Include precise document paths.
   - Include hard constraints and forbidden writes.
   - Keep Phase 0 small; do not let developer implement multiple phases at once.

## Metadata / Provenance Pointer Gate

A three-layer set is **not implementation-ready** merely because newly added sections agree semantically. Every material RFC/SPEC/Design amendment must also update its document-control metadata and provenance pointers.

Before releasing Implement, independently verify all three files for:

- `版本号` and `最后更新` reflect the actual amendment, not an older release;
- a matching version-history/changelog row names the new decision or section;
- SPEC's source-RFC version matches the amended RFC version;
- Design's source RFC/SPEC versions match the amended upstream versions;
- section-specific references (for example RFC §x, SPEC §y, DESIGN §z) resolve to the same capability and decision boundary.

### Blocking pattern

If RFC/SPEC bodies contain new capability contracts but their metadata still advertises old versions, while Design cites those old versions as its source, classify it as a **Design Gate blocker**. `git diff --check` and a completed Design task do not cure stale provenance.

### Required recovery

1. Immediately hold the existing Implement task as a real dependency; do not let the developer infer the intended version baseline.
2. Confirm the live worktree has no new implementation paths before reporting the hold; preserve any concurrent unrelated diff.
3. Create a Principal docs-only correction card with an allowlist limited to the three concrete RFC/SPEC/Design files. It may update metadata, version history, and version/source pointers, but must not silently alter the capability's business semantics.
4. Create a fresh independent Reviewer card after that correction. The review must reject stale pointers, unresolved cross-layer semantic conflicts, or a PASS/APPROVE verdict that lists open Major/Minor issues.
5. Add the new review card as a real parent of the held Implement task. Completed earlier Design cards remain historical evidence only and cannot retroactively gate the new correction.

A metadata-only fix still requires the same zero-production boundary: no provider/network/Mongo/.env/service/DDL activity and no unrelated code/config changes.

## T1 RFC/SPEC → T2 Design 独立放行门禁

适用：Full Flow 的 T1 仅产出 RFC/SPEC，且涉及数据模型、持久化、外部 Provider、查询路径或生产授权时。

**不得**因 task 显示 `done`、文件存在、worker 自述完成或 `git diff --check` 通过而直接创建/放行 T2。它们只证明产物和基础格式，不证明文档可实现。Orchestrator 必须先做独立只读审计，至少核验：

- 计划态与已实现事实不混写；T1 diff 严格限于文档 allowlist；
- 文档引用的既有 API、注册点、TTL/key 语义、测试路径与实际代码一致；
- schema、`from_dict`、验收与测试中的字段/计数一致，代码式示例语法成立；
- unique/idempotency key 覆盖 market/time/record scope，市场级与标的级数据没有含混模型；
- query 保持只读，Mongo/Cache 物化只能在显式、后续授权的 ETLV/refresh ingest 路径发生；
- 记录级 provenance/quality 与冻结的 QualitySummary 分离；外部 Provider 限制和任何真实生产动作均标为待验证或逐项授权。

发现任一阻断项时，**先向用户报告问题概要和影响**。若为 high/major 语义、数据模型、持久化边界或外部 API Gate 问题，必须在用户看到问题后明确确认“继续修订”，再创建仅文档 allowlist 的 T1.x correction card；笼统的先前开发授权不替代这次知情确认。修订卡应 `parents=[实际完成的审计卡]`，并在修订后创建一个**新的独立 reviewer task**重新审计；文档作者的 self-check 或原先审计的 PASS 不可放行 T2。**不得**先派 T2 再以 task body 备注弥补。

共享 worktree 的范围证明必须针对 allowlist 路径执行（如 `git diff --check -- <paths>`、`git diff --name-status -- <paths>`）；无关的全局脏状态只能记录为背景，不能归因于此修订卡或让其作出无法证明的全局 allowlist 声明。无产物的 worker/gateway 失败卡只保留作审计记录，必须创建自包含替代卡，不能 blind retry 或作为后续有效 parent。

详细的可复用检查与决策规则见 `references/t1-rfc-spec-release-gate.md`。

## Intra-Document Contradiction Gate

A document set can pass filename, status, version, checkbox, and cross-reference checks yet still be unsafe to implement when a **single Design** gives two incompatible directives. Before creating or releasing an Implement task, inspect the Design summary, risk table, detailed-design sections, acceptance matrix, and final decision table for each material behavior.

Typical contradiction pattern:

- Design summary / risk table says a behavior is “enabled by default”;
- detailed design / final decision says the same constructor parameter is retained only for compatibility and is currently a no-op;
- RFC/SPEC already lock the no-op behavior.

Treat this as a blocking contract failure, not a wording preference. The developer must not choose an interpretation or widen scope to reconcile it (for example by changing a frozen Router just to make a warning injectable).

### Required response when Implement is already ready

1. Record `file:line` evidence on the completed Design task and the queued Implement task.
2. Prevent Implement from starting (block/hold it as a dependency); do not rely on a chat-only warning.
3. Create a narrowly scoped Principal **Design correction** task. Its allowlist should normally contain only the affected concrete Design file, never templates or implementation files.
4. Link that correction as a real parent of the existing Implement task. A completed original Design parent is historical evidence and cannot gate the correction retroactively.
5. Require the correction to reconcile all occurrences in the Design and re-check the same behavior against RFC and SPEC. Historical changelog language may remain only when explicitly marked superseded.
6. Resume Implement only after the corrected Design has a single executable contract.

This gate applies even if the document metadata says `Final`, its checklist is all checked, and `git diff --check` passes; those are structural checks, not semantic proof.

## Cross-Doc Token-Residual Gate

When a doc-only remediation patches a **specific token or example** in one of the three layer documents (RFC / SPEC / DESIGN), never accept that remediation as closed until the same token has been re-grepped across **all three layer files**. This is the most common way a "PASS" docs task still leaves the contract inconsistent.

Patterns to watch (observed cases):

- `--database=wrong` / `--collection` / `--writer-role` / `--reader-role` appearing as CLI examples or `--verify` exit-code captions in DESIGN after RFC was already simplified to `--apply` / `--verify` only.
- Phase numbering (`Phase 0-7` vs `Phase 1-8`) re-asserted in DESIGN acceptance tables or rollout substeps after RFC normalized the count.
- Old collection prefixes (`UD_*`, `portfolio_*`, `ta_cn_*`) silently re-appearing in tables/captions/metadata blocks even when the main-body text already says "统一为 `YQUANT_UD_AUDIT_*`".

Mandatory closeout check before claiming any docs-only remediation done:

```bash
for p in \
  docs/rfc/<MOD>/RFC-<FEATURE_SLUG>.md \
  docs/spec/<MOD>/SPEC-<FEATURE_SLUG>.md \
  docs/design/<MOD>/DESIGN-<FEATURE_SLUG>.md; do
  grep -nE '<forbidden_token_1>|<forbidden_token_2>|<old_prefix>' "$p" || true
done
```

If any forbidden token still appears **anywhere** in the other two layers — including in `--verify` exit-code rows, G1..GN governance rows, `metadata:` blocks, or one-line code captions — the docs-only card is **not done**. Either:

- expand the card's allowlist to also patch the residual layers, or
- file a follow-up `Docs-R<n+1>` card whose body is **explicitly scoped** to the cross-doc residual, with parents pointing at the previous Docs-R card so the chain stays linear, and with the orchestrator comment carrying the file:line evidence.

This rule overrides the "single layer, narrow fix" common practice. Document scope boundaries are not real until they hold in all three layers.

### Minimal Audit Checklist

- All three layer files searched for the forbidden token(s).
- `git diff --name-status` shows only doc files (no code / test / config bleed).
- `git diff --check` clean.
- Cross-doc residual reviewer (a separate Principal or Reviewer task) has signed off, not the same worker that produced the patch.
- `kanban_comment` records the `file:line` evidence for any residual the next session will need to find.

## File-Scope and Output-Schema Reconciliation

Run this companion gate before releasing an Implement task after any material Design change. A Design remains non-executable when its own change table, exclusions, prose, or snippets disagree—even if its high-level decision is correct.

1. **File scope:** reconcile the change matrix, explicit “do not modify” list, task allowlist, and test plan. A file cannot be both “modified” and “out of scope”. If a required helper is outside the allowlist, name its concrete file and either add it to the contract or redesign the call site; never defer this choice to the developer.
2. **Output schemas:** trace every public or persisted field from producer → attrs/intermediate store → pipeline result → pending/sidecar artifact. A named field (for example `audit_items[]`) must have exactly one schema per location. Do not combine incompatible audit schemas merely to preserve legacy counting; retain the existing channel or use a distinct field.
3. **Pseudocode is contractual:** scan tables, prose, and all snippets for conflicting verbs/tokens such as `combined`, `merge`, `BOTH`, `append`, and “do not modify”. A prose prohibition does not cure contradicting pseudocode.
4. **Independent release evidence:** after a Principal correction card is done, the orchestrator must run path-scoped format checks and targeted residual searches independently. Do not resume Implement based solely on the worker handoff.

If a contradiction survives, keep Implement blocked, create one bounded Principal T2.x correction card, and add it as a real new parent of Implement. Earlier completed Design cards are historical evidence only. After two consecutive narrow corrections for the same design area, stop blind repair loops and require a fresh end-to-end Design audit before release.

## Version-history-table cells are dangerous patch anchors — re-read first

A version-history-table row in long-lived RFC / SPEC / Design documents is **often** a single cell that holds a 2000–10000 character prose entry describing the entire change set. Three pitfalls repeat:

1. The patch tool's "find unique" logic will match an unintended earlier version of the same row when you only quote the first/last sentence and the cell has multiple historical entries with similar opening clauses. The patch silently applies to a wrong version's row and corrupts the historical record of an earlier release.
2. The patch tool's "all-occurrence match" ambiguity can chain-collapse adjacent rows if the prose is even mildly similar.
3. `read_file` with offset/limit pagination truncates the cell content silently — you write a patch based on a partial read and it fails to match.

**Mandatory procedure before any patch that targets a single long cell** (e.g. a `版本号 | 日期 | 更新内容 | 负责人` row containing the full prose description of a release):

```bash
# Step 1: find the row's exact line range
grep -n '<short-stable-anchor>' path/to/file.md
# e.g. grep -n '| V0.38 | 2026-08-07 |' path/to/file.md

# Step 2: read the FULL cell, including ALL lines it spans, no offset.
# Raise read_file limit past the cell size; don't truncate.
read_file(path="path/to/file.md", offset=<row_start_line>, limit=<rows_to_cover_cell>)
```

3. Quote the entire row exactly in `old_string`, including its leading and trailing pipe characters and any embedded markdown. Do not paraphrase, do not collapse whitespace, do not let `read_file`'s truncation mislead you.
4. If the row is so long it exceeds the default 2000-char limit, raise the limit. Don't try to do the patch in two halves — the tool requires a contiguous match.

**Real session example** (2026-08-07, DESIGN-03-014 V0.37→V0.38 version-history row): the row contained a ~3000-character prose entry describing the entire change set, including embedded V0.35 / V0.34 / V0.33 / V0.32 / V0.31 / V0.37 history markers. A first patch attempt that quoted only the first sentence matched an earlier row in the file (the V0.35 entry had similar opening language) and silently truncated V0.35's content. Required a second patch to restore V0.35's full prose before adding the V0.38 row. The cost was two patch operations and one `read_file` re-scan to confirm restoration.

**After the patch**:

```bash
git diff --check -- <file.md>            # must exit 0
grep -c '<expected-new-version-string>' <file.md>   # confirm new content is present
grep -c '<expected-removed-version-string>' <file.md>  # confirm old content gone (or at least reduced by right count)
```

If a version-history-table patch looks like it touched the wrong row, restore the file immediately (`git checkout -- path/to/file.md` in the worktree) and re-read the entire row before retrying. Do not try to patch a misapplied patch on top — that compounds the corruption.

## Distinguish "事实归档" from "契约修订" before touching RFC/SPEC/DESIGN version numbers

Phase 3 work repeatedly hits a non-obvious distinction that drives whether a V+1 is needed at all, and whether the entire Design Gate audit must rerun. Get this wrong and you either falsify history (V unchanged for a real contract change) or trigger an unnecessary audit (V+1 for a fact-only entry).

**Two testable criteria for "事实归档" (no contract change, V+1 still OK):**

1. The new section's body contains an explicit non-modification clause: e.g. "本节为已发生事实归档", "不改本节任何冻结契约条款", "保持 R1/R2 历史事实保持准确不改写".
2. The three-doc mirror sync is byte-identical evidence, not paraphrased. Verify with `sha256sum` on the inserted subsection across RFC/SPEC/DESIGN before commit; the relevant diagnostic content (sha256 of artifact, connectivity, exception chain) must hash to the same value in all three documents.
3. No active capability, threshold, status enum, allowed value, or production gate semantics changes. The new section is purely a record of what happened, with explicit "不主张 ... 通过 / 四 Gate 全过 / R1·R2 翻案" disclaimers.

**If any of the three is false → it is a contract revision**. Treat as Full Flow change: full Design Gate audit, independent Review required, version bump is mandatory regardless of how small the change looks. The fact-archive / contract-change distinction does not relax any of the normal gates for contract revisions.

**Real session example** (2026-08-07, Phase 3 R3 freeze, RFC V0.34→V0.35 / SPEC V0.34→V0.35 / DESIGN V0.37→V0.38):

- The §R3.3.bis.1 subsection was added in all three docs with byte-identical sha256 evidence (diagnostic.yaml sha256 `d087fadcf25a8e7ba9ecc8b9c46133be3da2ee4580db98f18de1a169d633f862` 2417B appearing in all three changelog/version-history rows and the consistency table row).
- Body language was uniformly "事实归档" + "不改 §R3.3.bis 冻结契约" + "不扩展 P3-A / name_em / cons_em / OQ-11 / OQ-11B 既有语义" + "不构成 R3 通过 / 四 Gate 全过 / R1·R2 翻案依据".
- Therefore V+1 is the correct version bump (not "V0.34.1" or a sub-version), but no independent design-correction review chain was required beyond the normal `git diff --check` + sha256 cross-doc verification.

**Anti-pattern**: treating a fact-archive as if it didn't change anything and bumping V0 → V0.1 (or worse, leaving version unchanged). Version is supposed to reflect what someone reading the document can rely on; if a section is now present, the version must reflect that. Skipping the version bump on a fact-archive entry is the same falsification as upgrading without contract change.

**Provenance rule** (cross-doc): each layer's source-pointer row in its `最后更新` header MUST be updated in lockstep (RFC → SPEC → DESIGN pointers all bumped to the new V). If you bump RFC but leave DESIGN pointing at the old V, you have stale provenance, which is a Design Gate blocker (this skill §Metadata / Provenance Pointer Gate).

## Read-only / Hygiene Artifact Boundary Gate

对于只允许 Kanban 查询、评论或本地只读检查的 Intake、Hygiene、Board Governance 任务，**报告默认必须留在 `kanban_complete(summary/metadata)` 或 `kanban_comment`，不得在项目树创建 Markdown、CSV 或其他 artifact**，除非任务 body 明确允许具体路径。

### 为什么普通 diff 检查不够

`git diff --check` 不会发现 untracked 文件；worker 的 `changed_files`、`project_files_modified=0` 或 `git_modified=false` 也不是范围合规的独立证据。Closeout 前必须按 task allowlist 独立执行：

```bash
git status --short --untracked-files=all -- <allowlist-paths>
git diff --name-status -- <allowlist-paths>
git diff --check -- <allowlist-paths>
```

共享工作树已有 dirty 只能作为背景记录；不得 reset/stash/clean，也不得把无关路径归因于当前卡。

### 发现越界 untracked artifact 时

1. 保留原任务及其错误完成声明作为审计证据；不要回写或伪造历史结果。
2. 将必要结论转存到原任务的 durable Kanban comment。
3. 新建最小 Light Flow：Developer 仅删除该精确 artifact；独立 Tester 验证 `test ! -e <path>`、该路径的 `git status --short` 为空、`git diff --check` 通过。
4. 修复卡不得触碰代码、测试、RFC/SPEC/Design、生产资源或其他历史卡状态；用户交付中明确“看板证据已保留、项目树无本卡 artifact”。

## Done-but-Shared-Worktree-Still-Dirty Gate

When a Kanban implementation task (Implement / Verify / Developer) reaches `done` or `timed_out` while the **shared worktree still has partial uncommitted diff** (`git diff --name-status` non-empty, untracked files exist), the orchestrator must:

1. Run a scope-bound audit against the actual task body — not the worker summary — to confirm which allowlist paths changed and what tokens survived.
2. For each surviving forbidden/legacy token, capture `file:line` evidence into a `kanban_comment` on the offending task.
3. Decide retry vs reject:
   - **Retry** when the diff is structurally sound and the next run can finish it cleanly. Pass the continuation constraints as `kanban_comment` instructions, do **not** unblock / re-queue silently.
   - **Reject** when the task was started under a parent that has since been REVISE'd, when its tests/CLI cannot stand on their own, or when it consumed budget on an obsolete contract. Keep the card as audit evidence and create a replacement card with a real satisfiable parent.
4. Never claim a timed-out / partial task is "verified" by quoting its own test counts or self-stated metrics. Real verification is a separate independent run against the final shared worktree.
5. Real production gating (`--apply`, DDL/DML, credentials) is **always** strictly separate from this kind of partial retry — `Pascal` does not lose a single production authorization just because retries happened.

### Minimal Audit Checklist

- `git status --untracked-files=all` taken at the audit moment, not from worker self-reports.
- Each changed file's `grep` of forbidden tokens in the actual diff, not in the final spec.
- Continuation constraints recorded as task comment (so a retry inherits them, not the original body).
- Replacement card (if any) has real, satisfiable `parents` from the Kanban DB, not placeholders.

See `references/cross-doc-residual-gate.md` for a worked example from this skill's lineage (RFC/SPEC/DESIGN `--database=wrong` residual after CLI simplification, plus a timed-out Implement leaving `UD_AUDIT_WRITER_MONGO_*` / `UD_AUDIT_READER_MONGO_*` residuals in `scripts/unified_data/audit_rollout.py`).

## Residual Check Patterns

For MongoDB-first / no-SQLite-main-path decisions, search at least:

```text
SQLite 优先
SQLite 为默认
SQLite 默认
SQLite 表结构（MVP）
SQLite 文件
MVP 实现 SQLite
MongoDB 后端切换
SQLite → MongoDB
```

For collection-prefix decisions, search both old and new prefixes, and check cross-module references.

For shared-physical-db / internal-first decisions, additionally search for:

```text
adapter / 回灌 / 回写 / 加字段 / 字段扩展 / 衍生字段
fallback / 兜底 / 最后一级 / legacy / 末级
外部 Provider → 本地 / 优先 / fallback 链
DSAdapterProvider / StockDaily / SQLiteAdapter
任务调度（cron / systemd / register / create_job）
```

并显式核对：

- “shared physical db” 是否在 RFC/SPEC/Design 三层都明确出现；
- logical ownership（TA-CN 主集合 vs `03_data_ud_*` vs `10_infra_tc_*`）是否三层一致；
- 读取路径是否已经从 “外部 Provider → 本地” 改为 “内部 → 外部”，是否还有反例残留；
- legacy adapter 是否已从设计和路线图中移除，而不是仅在叙述中弱化。

## YQuant MongoDB-first Pattern

When Pascal confirms MongoDB persistence for a YQuant module:

- Put the selected collection prefix in RFC, SPEC, and Design.
- Mark SQLite only as local test / offline fallback / external legacy source adapter where applicable.
- Prohibit developer tasks from writing production decision collections unless explicitly approved.
- Use isolated MongoDB test databases or mocks for tests.

Known prefix pattern from the 2026-07-12 planning session:

```text
unified_data       -> 03_data_ud_*
task_center        -> 10_infra_tc_*
stock framework    -> 08_research_stock_*
```

## Internal-first 与 Shared Mongo 基线（2026-07-14 Pascal 确认）

类级决策落到 Unified Data × Task Center 的 RFC-03-007 / SPEC-03-007 / DESIGN-03-007 + RFC-10-009 / SPEC-10-009 / DESIGN-10-009 三套文档时，必须额外覆盖以下约束：

1. **物理库边界**：相关模块共用同一份 TA-CN MongoDB / `tradingagents` 物理库；写入仍按模块前缀（`03_data_ud_*` / `10_infra_tc_*`）隔离；禁止跨模块回写既有主集合。
2. **internal-first 权威读路径**：读取顺序固定为“TA-CN 既有内部数据 → Unified Data 物化集合（`03_data_ud_*`）→ 外部 Provider”；legacy / SQLite 不得作为运行时 fallback。
3. **三层语义分离**：业务资产、可追溯物化数据集、短 TTL query cache 必须分别定义，禁止把物化 == 缓存。
4. **Phase 依赖**：Task Center 的最小契约（Task/Job/Execution + 幂等 + 重试 + 审计）必须在 Unified Data 物化写入之前可用；DSA adapter / `StockDaily` 从 roadmap 移除。

> 文档同步规则延伸：用户在同一会话里以 ≥3 条架构决策确定新基线后，主控（orchestrator）必须立刻把决策登记进 backward-reference 卡片（`kanban_comment` + `summary`），并创建真实 Kanban 修订任务（assignee=principal，workspace=项目目录）。P-7 “编排层不能改模板 / 全局规约源” 与此并不冲突：本次允许直接 patch 已生效的三层具体文档，但不允许 patch 文档模板或跨项目的全局 SKILL.md。

## Replacement Chain Gate: Late Document Fixes Must Gate Only Future Work

When a late semantic correction (for example, an error-contract change) must be applied before continuing a pipeline:

1. Inspect the relevant Kanban cards' **current statuses and parent links** before adding dependencies.
2. A parent link added after a child is already `done` is **not retroactive**: it cannot force that completed Review/Verify to re-run against the revised documents.
3. Treat completed stages as historical evidence only. If the revised document needs an independent review, create a new review task with the document-verify task as a real parent.
4. If an old implementation/review chain has a permanently blocked parent, do not keep new RFC/SPEC/Design work dependent on it. Create a replacement chain whose first task depends only on real, satisfiable gates, then build the remaining chain from returned task IDs.
5. In user-facing status, distinguish precisely between “previous review passed under the former document baseline” and “future work is gated on the revised-document verification.” Never claim a completed review was retroactively gated.

### Minimal Gate Checklist

- The document correction has a separate Verify task.
- Any future implementation/RFC task has that Verify task in `parents`.
- No replacement task references a known-blocked legacy parent.
- Legacy task chains are explicitly marked obsolete in a task comment or the replacement task body.
- The new task chain uses real task IDs returned by `kanban_create`, not placeholders.

## Project-wide Engineering Standard Change Gate

When a user changes a project-wide engineering standard during an active pipeline—such as a file-size limit, lint threshold, naming convention, or supported runtime—the decision must not be treated as a one-off task-body override.

1. **Update the canonical rule first.** Identify the canonical project source (for example `CLAUDE.md`) and search all in-scope RFC/SPEC/Design documents for direct occurrences of the old threshold or rule. Synchronize only direct contractual references; do not rewrite third-party directories, historical blog posts, or unrelated numeric text.
2. **Separate the new global rule from a legacy-file exception.** Put the new general threshold in the canonical rule. If an existing file already exceeds it and the user permits current work to continue, record a bounded exception in the closest feature Design: affected file, current scope, non-transferability to other files/features, and the condition requiring a future split/redesign. A one-file exception must never silently become a blanket policy.
3. **Do not rewrite historical blocked cards.** Preserve the original blocked Verify task as audit evidence. Create a replacement Verify task whose body explicitly cites the synchronized rule and exception, then make a replacement Review task depend on that Verify task.
4. **Gate verification on document completion.** Do not resume testing while old acceptance text conflicts with the new rule. Once documentation is synchronized, require a fresh independent RED/GREEN and regression run; developer self-reported results remain non-independent evidence.
5. **Keep scope discipline.** Do not force an unplanned large refactor merely to make an already oversized legacy file conform immediately. If a split is needed, create RFC/SPEC/Design for it unless the user explicitly authorizes the refactor.

### Minimal Audit Checklist

- Canonical rule updated.
- All in-scope direct contract references updated or explicitly retained as historical context.
- Any exception has file, scope, expiry/revisit condition, and non-transferability stated.
- Old blocked card is preserved; replacement Verify and Review use real returned Kanban IDs.
- Replacement Verify has no ambiguous old threshold in its acceptance criteria.

## Worker-Crash Replacement Gate for Document Verification

When an independent document Verify worker crashes or reaches its retry limit **without producing commands, findings, or a verdict**, treat that as a runtime-execution failure—not evidence that the documentation passed or failed.

1. Inspect the failed Kanban task attempts. Distinguish a documented contract failure from bare process metadata such as `exit 1` with no captured stderr or report.
2. Preserve the failed task as audit evidence. Add an orchestrator comment that no validation result was produced; do not relabel the crash as PASS/FAIL or blindly reopen the same retry loop.
3. Create a replacement independent Verify/Review card from the last successful, satisfiable planning parent (normally the completed Principal document task), **not** from the blocked/crashed Verify. This prevents an unsatisfiable dependency chain.
4. Carry forward the frozen acceptance criteria and require path-scoped `git status --untracked-files=all`, `git diff --name-status`, `git diff --check`, plus exact semantic searches. In a shared worktree, attribute scope only within the allowlist rather than treating unrelated global dirtiness as a breach.
5. Use a different specialist profile when appropriate (for example Reviewer after Tester retry exhaustion), while preserving independence from the documentation author. A replacement Review may close a documentation-only gate only after it actually runs the evidence checks.
6. Status reporting must say exactly that the previous verifier crashed without a verdict and that replacement independent review is pending; never claim the original verification retried successfully or was retroactively repaired.

### Model Override Integrity (Kanban Runtime Field Is Authoritative)

When a replacement task requires a specific model/provider to restore independence or bypass an exhausted fallback chain:

1. Put the required provider/model in the `kanban_create(model={"provider": ..., "model": ...})` call. A task-body statement such as “force Codex” is not executable configuration.
2. Immediately inspect the created task and verify its **actual** `model_override` field matches the requested provider/model before treating the task as a valid retry.
3. If `model_override` is null or differs, preserve that card as an invalid runtime attempt, annotate the mismatch, and create a new replacement card with the real override. Do not interpret its crash as a review verdict.
4. Before spending another retry budget, run one minimal, read-only one-shot probe using the exact profile/provider/model combination (for example, a literal `PONG` response). This separates credential availability from the document or code under review.
5. Do not change profile config, credential pools, fallbacks, or authentication as a workaround without the user’s explicit approval; those are profile-level operational changes. Prefer a per-task model override when already-authorized credentials work.

## Implementation Order Heuristic

For a stack where stock analysis depends on data and task orchestration:

1. Data layer Phase 0 skeleton and core abstractions.
2. Data layer read-only adapters / canonical service.
3. Task center core entities and state machine.
4. Task center MongoDB backend.
5. Stock framework skeleton and entities.
6. Stock profile/model MVP.

Reason: stock framework consumes canonical data; task center schedules work but does not replace the data service. Implementing stock too early creates mocks and later rework.

## Verdict Self-Consistency and the "Narrow Correction + Single Re-Review" Close-Loop

Across T1/T2 review chains, the most common procedurally broken state is a Reviewer card whose Verdict says `APPROVE` (or `PASS`) while its body / metadata still lists unresolved MAJOR or BLOCKING items. This was observed live during the Phase 3 Design cycle (T2.3 returned APPROVE while still flagging H2=MAJOR). Treat any such combination as a governance defect, not a wording preference.

### Symptom to detect

A Reviewer task whose `result` / `summary` / `metadata.verdict` field says PASS/APPROVE, but whose `findings` or `metadata.major_detail` still lists items with severity ≥ MAJOR that were not fixed in this iteration. The same defect applies to `PASS_WITH_FIXES` / `REVISE` whose attached list contains blocking items that "acknowledge without resolving".

### Required orchestrator response

1. Do not pass the verdict through. The Design Gate is still closed; the next stage (T3 Implement or downstream Design correction) **must not be created** on a verdict that contradicts its own evidence.
2. File an orchestrator `kanban_comment` on the offending card citing the exact MAJOR `file:line` from its findings; do **not** relabel `result` manually — that falsifies audit history. The corrected card will appear later in the chain.
3. Apply the **canonical close-loop** instead of endlessly re-running the same Reviewer:
   - Create one narrowly-scoped `Design Correction` card (assignee=`yquantprincipal`), allowlist = the single affected Design file (or RFC/SPEC when cross-doc), with parents = the offending Review card. Its body must explicitly extract the unresolved MAJORs by `file:line`.
   - After the correction completes, create **one** new independent Review card (parents = the correction card; different `assignee` workers, not a re-spawn of the same review profile pair) whose only job is to confirm the residual items are closed and verdict self-consistency now holds.
4. If a correction card itself crashes / times-out without verdict (clean exit, no `kanban_complete`/`kanban_block`, gateway `protocol_violation`), do not treat it as done. See "Worker-Crash Replacement Gate for Document Verification" above and add an orchestrator comment noting the dispatcher state mismatch.
5. The chain may legitimately need **two** independent review passes (e.g., when correctness shifts a sub-decision) before T3 can be created; a third pass is allowed only if the second surfaced new evidence that wasn't visible earlier. **Three or more** consecutive "very narrow corrections" on the same Design with the same class of residual = pipeline is operating on a moving target; stop and re-anchor with the user before creating further corrections.

### Why this close-loop, not endless reviewer re-runs

- Verdict self-consistency is a stronger signal than "review ran". Re-running the same Reviewer with the same body rarely surfaces new evidence; it burns budget without moving the gate.
- A narrowly-scoped correction card makes the residual item discoverable in the audit trail by `file:line`, instead of being absorbed into a longer review summary.
- A fresh independent card on the corrected file replaces the earlier verdict cleanly; the old card stays in history as the audit trail for *why* the correction was needed.
- This pairs with `design-gate-audit` §"审查预算耗尽或无有效 verdict 的恢复": both substitute **bounded, evidence-linked correction cycles** for unbounded reviewer fan-out.

## References

- `references/mongodb-first-doc-sync-2026-07-12.md` — session-specific details and exact SOP from the 9-document review / MongoDB-first synchronization case.
- `references/internal-first-shared-mongo-2026-07-14.md` — shared TA-CN Mongo + internal-first + Task Center 前置最小化的回检 SOP（comments、决议登记、文档一致性检索清单）。
- `references/cross-doc-residual-gate.md` — 2026-07-17 worked example: cross-doc CLI/namespace token residual and timed-out Implement with partial uncommitted diff (audit commands, retry-vs-reject decision rules, audit checklist).
- `references/verdict-self-consistency-2026-07-21.md` — *(pending)* worked session log of Phase 3 T2.3 verdict-self-contradiction → T2.4 narrow correction → T2.5 single re-review close-loop, including the clean-exit dispatcher protocol-violation recovery. Create on demand from the close-loop section above when a fresh incident recurs.
- `references/phase3-contract-gate-pattern.md` — Contract-dispute SOP for public return/persistence semantics discovered after implementation: freeze REVISE, require Principal adjudication, then use a fresh Implement → Verify → Review chain; also contains the three-layer status-reporting rule.

## Verdict Self-Consistency and the "Narrow Correction + Single Re-Review" Close-Loop

Across T1/T2 review chains, the most common procedurally broken state is a Reviewer card whose Verdict says `APPROVE` (or `PASS`) while its body / metadata still lists unresolved MAJOR or BLOCKING items. This was observed live during the Phase 3 Design cycle (T2.3 returned APPROVE while still flagging H2=MAJOR). Treat any such combination as a governance defect, not a wording preference.

### Symptom to detect

A Reviewer task whose `result` / `summary` / `metadata.verdict` field says PASS/APPROVE, but whose `findings` or `metadata.major_detail` still lists items with severity ≥ MAJOR that were not fixed in this iteration. The same defect applies to `PASS_WITH_FIXES` / `REVISE` whose attached list contains blocking items that "acknowledge without resolving".

### Required orchestrator response

1. Do not pass the verdict through. The Design Gate is still closed; the next stage (T3 Implement or downstream Design correction) **must not be created** on a verdict that contradicts its own evidence.
2. File an orchestrator `kanban_comment` on the offending card with `file:line` evidence from the findings block; do not relabel the card as REVISE/BLOCK manually — that would falsify audit history.
3. Apply the **canonical close-loop** instead of endlessly re-running the same Reviewer:
   - Create one narrowly-scoped `Design Correction` card (assignee=`yquantprincipal`), allow-list = the single affected Design file (or RFC/SPEC when cross-doc), with parents = the offending Review card. Its body must explicitly extract the unresolved MAJORs by `file:line`.
   - After the correction completes, create **one** new independent Review card (parents = the correction card; different `assignee` workers, not a re-spawn of the same review profile pair) whose only job is to confirm the residual items are closed and verdict self-consistency now holds.
4. If a correction card itself crashes / times-out without verdict (clean exit, no `kanban_complete`/`kanban_block`, gateway `protocol_violation`), do not treat it as done. See "Worker-Crash Replacement Gate for Document Verification" above and add an orchestrator comment noting the dispatcher state mismatch.
5. The chain may legitimately need **two** independent review passes (e.g., when correctness shifts a sub-decision) before T3 can be created; a third pass is allowed only if the second surfaced new evidence that wasn't visible earlier. **Three or more** consecutive "very narrow corrections" on the same Design with the same class of residual = pipeline is operating on a moving target; stop and re-anchor with the user before creating further corrections.

### Why this close-loop, not endless reviewer re-runs

- Verdict self-consistency is a stronger signal than "review ran". Re-running the same Reviewer with the same body rarely surfaces new evidence; it burns budget without moving the gate.
- A narrowly-scoped correction card makes the residual item discoverable in the audit trail by `file:line`, instead of being absorbed into a longer review summary.
- A fresh independent card on the corrected file replaces the earlier verdict cleanly; the old card stays in history as the audit trail for *why* the correction was needed.
- This pairs with `design-gate-audit` §"审查预算耗尽或无有效 verdict 的恢复": both substitute **bounded, evidence-linked correction cycles** for unbounded reviewer fan-out.
