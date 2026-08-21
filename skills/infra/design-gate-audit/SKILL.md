---
name: design-gate-audit
description: 在 Implement 前审计 RFC/SPEC/Design 的阶段边界、文件范围与可计算契约；适用于含评分、阈值、存储方案、公开 trace 或生产副作用门禁的设计。
---

# Design Gate Audit

在 Full Flow 的 T2 Design 完成、T3 Implement 创建之前使用。本 skill 的目标是确认 Design 不只是“文件存在”，而是真正可由不同实现者无歧义地实现、可由测试者证伪，且没有越过阶段或生产边界。

## 触发条件

以下任一情况应在 T2 → T3 之间加载：

- Design task 只授权文档，却涉及 Python/API/config/test 文件清单。
- RFC/SPEC 包含评分公式、阈值、优先级、TTL、状态机、容量估算或行为矩阵。
- 变更影响公开结果字段、`source_trace`、warnings、错误语义或审计事件。
- 计划引入 MongoDB 集合、索引、audit/summary 写入，且生产启用尚未确认。
- T2 worker 的交付说明中出现“stub”“已验证 import”“候选默认值”或“待确认”。

## 审计步骤

### 1. 先校验三层文档与授权范围

1. 确认 RFC、SPEC、Design 都在目标项目的规定目录，编号和互引一致。
2. 读取 T2 task body，抽取“允许修改”和“禁止修改”的准确文件范围。
3. 检查工作树中实现目录与测试目录的新文件；将其与允许范围逐项比对。
4. 文档任务只应留下文档。伪代码、类型签名、fixture 示例可以写在 Markdown 中；可导入的 Python、配置和测试属于 Implement，除非任务明确授权。

若发现越界 stub：停止 T3，创建一个仅清理的 Design-correction task。清理卡只能删除精确列出的越界产物、保留合法文档、运行静态范围检查；不得顺便实现功能。

### 1a. 核验 canonical 路径与 Markdown 检查边界

文档中出现测试、fixture、脚本或产物路径时，不能只检查文档之间是否“写得一致”；还必须与当前工作树核对：

1. 对每个 canonical 根路径执行存在性检查；旧路径不存在而新路径存在时，视为阶段阻断项，即使 RFC/SPEC/Design 三层恰好都还引用旧路径。
2. 对三层文档做精确引用扫描，覆盖 file matrix、验收标准、命令示例、fixture/conftest 说明和附录。只允许同步路径，不得恢复旧目录、复制测试资产或改变测试语义。
3. 章节级静态安全扫描必须按 Markdown heading 的真实范围切片（当前标题到下一个同级或更高级标题），不能用“匹配到文档末尾”的宽泛正则。命中写入型命令时，要报告其章节和用途：它可能是允许的 Activation smoke，而不是 readonly acceptance 的违规。
4. 若静态工具缺少所需正则能力，改用小型本地 Python 文本切片并让断言失败即失败；不得将工具错误或不支持的模式当作“未命中”。

任何上述问题均先创建仅文档的 principal correction task；修正后必须重新跑完整 Design Gate，才能创建 Implement。

### 1b. 生产副作用的 Activation 交接

Design Gate 的放行只允许进入离线 Implement；它绝不是生产上线许可。若 Design 涉及真实 DDL/DML、外部写入、真实 smoke 或 canary，必须将它们保留为 Review PASS 之后的独立 Activation 卡：用户须对精确动作、allow-list 范围、影响与停止规则明确授权；Activation 必须 dry-run 在前，apply 与 readonly verify 分离，且失败不重试有副作用步骤。凭据只能经冻结脚本做最小存在性 preflight，任何日志/metadata 不得含值。详见 `references/production-activation-transition.md`。

### 2. 审计契约可计算性

对每一个可量化的行为矩阵或示例：

1. 从 Design 提取公式、权重、边界和舍入规则。
2. 独立重算示例；分类必须按未舍入 raw value 判断，展示四舍五入不可改变阈值归类。
3. 将结果对照 SPEC 的 API 契约、冻结门禁、行为矩阵和测试预期。
4. 检查每个 Phase 内承诺的分支都仍可被实现和测试；不得把 SPEC 已承诺的分支悄然下沉到未来 Phase。
5. 对每个 warning/reason code/source trace 条目确认稳定格式、顺序和可断言性；不得用模糊子串断言替代公开契约。

发现冲突时，停止 T3，创建仅文档的 principal correction task，要求同步公式、tier、reason code、行为矩阵、fixture 预期和必要的 RFC/SPEC 文本。

### 2a. 简化设计后的语义单义化（防止“表简化、契约仍复杂”）

当用户要求简化数据模型或实现边界时，Gate 不只检查字段数和文件数，还要防止把复杂度转移到可选语义、协议层或未来路径中。

1. **每个失败类别只能有一种可测试结果。** 逐项区分：参数非法、无已物化记录、输入数据质量失败、完整性不足、查询筛选为空。每项必须冻结为唯一的异常/错误结果，或唯一的 empty + warning 结果；`error/empty`、`empty 或 warning` 一类措辞是契约冲突，必须先修文档。
2. **稳定 token 与顺序必须落字。** 若使用 warnings/source trace，定义其 token、顺序、是否写入以及对应 BuildOutcome 状态；测试要断言这些值，不得让 Implement 自行选择错误类型或 warning 文案。
3. **用户要求“最小实现”时，审计实现间接层。** 除最小 domain/repository/service/test 外，新 protocol、fake client、全量常量表、实时侦测、backfill、生产 adapter 或 facade 都必须有当前阶段的直接验收必要性；没有则移入明确标记的 Future Gate，且 T3 allowlist 禁止创建对应文件。
4. **完整性不得用百分比偷换。** 若正式横截面要求完整 universe，采用显式 `observed == expected` 等精确规则；期望集合若尚未经真实数据 Gate 验证，应由调用方/fixture 注入，不能硬编码成未经验证的生产常量。
5. **verdict 自洽优先于摘要词。** Review 的 summary 写 `PASS`/`APPROVE` 不能覆盖 metadata 中任何未闭合 MINOR/MAJOR/BLOCKING。即使标为“observation”，只要它要求 Developer 在 error/empty、字段、顺序或公共行为上自行裁决，就是真实 finding；Gate 必须 `REVISE`，先创建窄范围 Principal 文档修订并重新独立审查。

### 3. 审计候选默认值与生产副作用

将每项设计参数分类：

| 类别 | T3 前处理 |
|---|---|
| 纯计算/内存默认值 | 可作为可覆盖候选实现；需在 Design 明示来源和覆盖优先级。 |
| fake/mongomock/noop 后端 | 可实施与测试；不得需要真实 URI、真实连接或 DDL。 |
| 真实集合、索引、TTL DDL、持久化写入、外部 smoke | 必须保留 Production Gate；没有用户明确确认不得实施或执行。 |

候选参数不能被写成已获生产批准。若参数有多解，Design 应明确决策人、决定时点与 Implement 的安全默认行为。

## Finding 归类与 verdict 自洽

Design Gate 必须区分两类内容，避免出现“APPROVE 但仍列 MAJOR”的伪放行：

1. **已在 RFC/SPEC/Design 明确排入 T3、具有精确 allowlist、实现顺序和可证伪验收的未实现工作**，应标为 `T3 backlog / planned implementation`，而非 Gate finding（不使用 BLOCKING/MAJOR/MINOR severity）。例如待新增的私有守卫、字段集定义或新测试，若其实现路径与验收在 Design 已完整定义，可以作为 T3 的输入。
2. **文档与代码事实不一致、缺少实现路径/测试语义、allowlist 不足、Phase/副作用边界冲突，或 Review 要求先修订文档/契约的事项**，必须是真实 finding。只要有未闭合 `BLOCKING`、`MAJOR` 或 `MINOR` finding，verdict 必须 `BLOCK/REVISE`；不得以“留给 T3 处理”为由 `APPROVE`。

审计输出须把 `planned implementation` 与 `findings` 分栏；若检查中发现原先被写成 Major 的内容其实是完整定义的 T3 backlog，应降为无 severity 的 implementation note，并在最终 verdict 中说明。否则先走 principal 文档修正 → 新独立 Gate，不得创建 T3。

## 放行条件

只有全部满足才创建 T3：

- [ ] 三层文档齐全、编号与引用一致。
- [ ] T2 的文件系统产物没有超越 task body 授权范围。
- [ ] 数值示例与阈值分类可复算且与行为矩阵一致。
- [ ] SPEC 的所有 Phase 内契约仍有明确实现路径和可证伪测试。
- [ ] 公开 trace/warnings/audit schema 的兼容性和断言强度已定义。
- [ ] fake/noop 与生产副作用边界明确；未确认的 DDL/真实写入均未放行。
- [ ] 静态范围检查和 `git diff --check` 已通过。

## 有界轮询 / deadline 状态机门禁

当 Design 定义“预算窗口、固定 cadence、最大轮次数（cap）、starting/failed 终态”时，不能只重算轮次数；必须把 **调度许可** 与 **终态裁决** 分开审计。尤其适用于 readiness、retry、health-check 与冷启动治理。

1. **写出唯一的时钟顺序。** 明确每次循环首先读取 monotonic `now`，在 `now >= deadline` 时必须先进入 deadline 分支；若 Design 禁止 deadline 后新 probe，则不得先调用网络、systemd、端口或任何 round helper 再判定 deadline。
2. **cap 不是终态触发器，除非文档明确如此。** `cap` 通常仅约束 deadline 前可排程/完成的最大轮数。若 RFC/SPEC 写成“仅 `elapsed >= deadline AND consecutive_failures >= threshold` 才可 failed”，实现不得用 `count >= cap` 或 retry counter单独提前失败。
3. **穷尽 deadline 三种测试。** Verify/Review 必须要求并检查可执行测试，而非仅看 pytest 全绿：
   - `elapsed < deadline` 且 `count == cap`：严格断言 `starting`，没有 terminal `failed`；
   - 恰好 `now == deadline`：断言 round helper/网络/systemd 子调用次数不增加，即没有第 N+1 次 probe；
   - `now >= deadline`：仅根据缓存的最后状态裁决；分别覆盖 failure count 达阈值（一次 `failed`）与未达阈值（不得伪造 `failed`）。
4. **测试断言必须与 docstring 同强度。** 若文本写“预算内绝不 failed”，断言必须为 `status == "starting"`，不能写 `{ "starting", "failed" }` 这样的防御性集合。遇到这种不一致，即使全套 pytest PASS，也应列为 Gate blocker。
5. **以真实调用边界验证 cadence。** mock monotonic 时序应覆盖第六轮完成、sleep 到 deadline、deadline branch；不仅断言最终 JSON，还要断言 `_probe_round_*` 的调用次数和无额外 round。不得把底层 runner/subprocess 的原始调用数等同于业务 probe round：一个 round 可包含 health、PID、listener、cgroup 等多个子调用，失败路径也可能追加补偿检查。底层调用数如需覆盖，应单列为内部实现测试，不能承担“deadline 后无第 N+1 轮”的契约证明。报告中明确“轮次起点、最后允许完成时间、deadline observer”三个时间点。
6. **超时实现只算候选，不算交付。** 若 Developer 因 iteration budget 耗尽、timeout、gave_up 或未形成 `kanban_complete` handoff，尽管共享目录已有改动或事后评论声称本地全绿，也不得作为 Gate PASS 依据。保留共享树、不做 reset/revert；新建严格 allowlist remediation card，要求复现 RED、在 round-level seam 建立精确 spy、再产生正式 GREEN handoff。随后必须新建独立 Verify 和 Review，不复用旧的探索性 Verify/Review。

此类问题若被 Gate 发现：先用一个严格 allowlist 的 Design Correction 同步 cap/deadline/threshold 定义，再由 Developer 按 RED→GREEN 修复代码与测试；旧的探索性 Verify 即使 PASS 也不得作为后续正式放行依据。修正后需重新独立 Verify 和 Review，生产 activation 始终另行授权。

## 代码规模阈值（行数）变更审计

当需求把项目级文件行数上限从一个阈值调整到另一个阈值时，不能只改规则文本；这是一项会改变既有 RFC/SPEC/Design 约束力的治理变更。

1. **先确定统计边界**：以 Git 已跟踪的第一方源码与测试文件为样本；排除 `.venv`、vendor、生成依赖和子模块内部第三方代码。报告总文件数、各阈值区间的文件数，以及所有超过旧阈值的第一方文件清单。
2. **区分软/硬阈值**：优先设计为“常规目标阈值 + 需要架构说明的例外区间 + 绝对硬上限”，不要以一个过大的通用上限抹除模块化治理。例外区间必须写清 Principal Design、增长限制和拆分触发条件。
3. **做规约引用清单**：搜索并逐项处理项目规则、RFC、SPEC、Design、测试拆分计划和既有豁免记录。凡是以旧阈值判定“违规”或“必须拆分”的文档，都要改为当前决策下仍准确的语义。
4. **保留审计历史**：既有一次性豁免、当时的实际行数、风险判断与演化承诺不得直接删除；应标为被新治理版本 supersede，并保留原决策的时间点和适用范围。
5. **最小验收**：`git diff --check`；确认所有引用旧阈值的活跃文档已同步；重新统计第一方文件，验证没有文件超过新硬上限。规则变更本身没有运行时代码影响时，不应宣称业务测试证明了政策正确，只需运行受影响文档/质量检查。

## Shared-File 实现链编排

Gate 建议将实现拆成多张卡时，除按职责和单文件行数拆分外，还必须检查**写路径重叠**：

1. 若两张 Developer 卡都会修改同一个实现文件（例如同一个 Router），不得并行派发到共享 `workspace_kind="dir"`；后卡必须以先卡的真实 task id 作为 `parents`，形成串行链。
2. 可以在 Gate 后一次性预创建 Implement → Verify → Review → Closeout，但只能使用每次 `kanban_create` 成功返回的真实 id 建立依赖，不能用占位符或仅在任务正文写“等待上一卡”。
3. 每张 Implement 卡的 allowlist 必须明确到文件。测试卡应只创建与其职责对应的新测试文件；跨卡集成回归由下游独立 Verify 统一覆盖。
4. 对 Router/结果契约这类多出口代码，设计 handoff 要求 Implement 明确“统一出口 helper”或“每个 return 点覆盖”的选择，并令 Verify 检查不存在漏分支；不得把该选择留成不可证伪的泛泛表述。
5. Closeout 的结构化记录若因 worker 输出序列化异常而不完整，Orchestrator 必须在该 Closeout 卡追加一条可读的 `kanban_comment`，补齐 verdict、改动范围、实测计数、安全边界和残余风险；不能以乱码 summary 替代审计记录。

## 审查预算耗尽或无有效 verdict 的恢复

当单张 T2 Review 因范围过大而 `blocked`、timeout 或耗尽 iteration budget 时，**不得**把状态、clean exit 或 worker 摘要当作 `APPROVE` / `REVISE` / `BLOCK`。先读取该卡的 run、summary/metadata、评论、父卡和任何 synthesis 卡的真实证据；无明确 verdict 时，T3 仍冻结。

1. 保留原 blocked 卡作为审计轨迹，并用 comment 写明精确原因；不要无变化地重复同一预算与范围。
2. 按独立验收面拆成 2–3 张 reviewer 卡（架构/只读路径与注入；schema/freshness/provider；写语义/Gate/文档闭合），每张要求 `PASS` 或 `FAIL`、`severity + file:line + 是否阻断 + 最小修正验收`，并只跑 scoped whitespace/static checks。
3. 创建一个 synthesis reviewer 卡，以全部分段卡为 parents：任何 blocker FAIL 必须 `REVISE`；任何父卡无明确 PASS/FAIL 必须 `BLOCK`；仅当全部 PASS 且三层文档一致才可 `APPROVE`。
4. `REVISE` 后仅创建严格 allowlist 的 principal Design Correction；修订完成后必须重新独立复审，不能复用旧 verdict。

尤其要交叉核对：query 的只读承诺与真实 materialize/cache 分支、adapter 的现有 key model 与业务唯一键/多记录写入、provider-success 与 persistence-success 的区别、Cache Gate、dataclass 字段数与 provenance/序列化闭合，以及是否把改变 schema/路由的 OQ 不当推给 T3。详见 `references/review-budget-recovery.md`。

### Verdict 自洽性与下游隔离

Review 的状态、完成事件、`git diff --check` 或摘要中的 PASS/APPROVE 均不能覆盖正文或 metadata 中未闭合的问题：

1. 尚有待修的 BLOCKING / MAJOR / MINOR 时，verdict 必须为 `FAIL` / `REVISE`，不得写“PASS/APPROVE with findings”。不影响 Gate 的观察只能标为 `NOTE`，且不得要求 T3 处理或改变契约。
2. RFC、SPEC、Design 在签名、字段可选性、只读/写入路径、trace 或 Gate 语义上不一致，即为 Design Gate 失败；不得在 Implement body 中指定“以 Design 为准”或要求 developer 裁决。
3. 任一分段审查 FAIL，synthesis 必须 REVISE；synthesis 必须读父卡正文及 metadata，而非只读 verdict 字段。
4. 修订仅限明确 allowlist 文档，之后必须新建独立复审；新的 clean verdict 前，Implement、Activation、真实 Provider/Mongo、DDL/DML、生产写入持续关闭。
5. 对 `_materialize()` 等真实代码方法名，逐行对照当前调用点；不得把它泛化为“持久化”从而绕过 query 与显式 refresh 的副作用边界。

### APPROVE-with-OPEN-MAJOR pattern (orchestrator-side gate)

Observations from live Phase 3 Design cycle (2026-07-21): a Review card can complete with `verdict: APPROVE` while its `metadata.findings` / `metadata.major_detail` still lists MAJOR items that the reviewer "noted but did not block". This is **not** a PASS — it is a self-contradicting verdict and a defective gate. The orchestrator's responsibility is to refuse to pass it downstream and to drive the canonical close-loop below. Treating such a verdict as legitimate because it has the word "APPROVE" in `summary` is the failure mode this rule exists to prevent.

Detection (must run before creating any T3 card off a Review parent):

1. Read the Review card's full `summary`, `metadata`, `findings`, `comments`, and any attached synthesis card. If the verdict field says `APPROVE` / `PASS` while any item with severity MAJOR or BLOCKING appears in the findings and is not closed by this same iteration, treat as **broken verdict**.
2. File a `kanban_comment` on the offending Review card citing the exact MAJOR `file:line` from its findings; do **not** relabel `result` manually — that falsifies audit history. The corrected card will appear later in the chain.
3. Apply the canonical close-loop (NOT endless reviewer re-runs with the same body):
   - Create exactly one narrowly-scoped `Design Correction` card: assignee=`yquantprincipal`, allowlist = the single affected Design file (or RFC/SPEC when cross-doc residual), `parents=[broken Review card]`. Body must quote the unresolved MAJORs by `file:line` extracted from the broken review's findings.
   - After the correction completes, create exactly one new independent Review card (assignee must be a **different profile worker** than the broken review, not a re-spawn of the same assignees) with `parents=[correction card]`. Its only acceptance item is "the items previously flagged as MAJOR are now resolved and verdict self-consistency holds".
4. **先建 closure ledger，再发一次修订卡。** 对同一公开契约（例如 `source_trace`）的一个 Gate finding，不要逐轮只修一处文本差异。Orchestrator 必须先汇总 RFC、SPEC、Design、伪代码和测试矩阵的全部等价表示，形成一张修订清单：枚举值域、分隔符/序列化格式、成功与失败路径、warning/error token、trace 顺序、元数据互引与逐字断言。Principal correction 必须一次性统一该清单；独立 Review 的 body 也必须检查整张清单。这样避免“修完值域 → 再发现分隔符 → 再发现成功行”的无限窄循环。
5. **同一审计面不得连续复用同一 reviewer profile。** 修订后的独立 Gate 必须换用与上一张失败 Gate 不同的 reviewer profile；若可用 reviewer 只有一个，应由 Orchestrator 先自行执行机械性 closure-ledger 扫描，再请求用户决定是否接受第二次同 profile 复审。不能把同一 reviewer 的多次 rerun 伪装成独立性。
6. Two independent review passes total is legitimate when a sub-decision shifted under correction. A **third consecutive** very-narrow correction on the same Design with the same class of residual = operating on a moving target; stop and re-anchor with the user before creating further corrections.
7. If the correction card itself crashes / times-out (clean `rc=0` exit with no `kanban_complete` or `kanban_block`, dispatcher `protocol_violation`), do not treat it as done. Annotate via `kanban_comment` and create a replacement correction card from the actual last successful planning parent — never re-use the crashed one.

### Goal-judge failure containment for narrow document gates

For a narrow RFC/SPEC/Design correction or read-only review with deterministic acceptance, default its Kanban card to **`goal_mode=false`**. A goal judge is useful for genuinely open-ended work, but it adds an infrastructure dependency and must not turn a bounded document correction into repeated retries after the worker has already produced testable evidence.

If a `goal_mode=true` card has already written its allowed artifact and then `kanban_complete` repeatedly fails at the judge layer:

1. Preserve the artifact and add one concise `kanban_comment` containing the exact changed paths, verification commands/results, and the judge error class. Do not burn the iteration budget on repeated completion attempts.
2. Mark the card blocked with the infrastructure reason where the board permits it. A blocked/timed-out card remains **not done**; its worker self-report is never a pass verdict.
3. Create one fresh, **non-goal-mode**, independent read-only verification/review card with a tight acceptance checklist. It must inspect the shared-tree artifacts and run its own scope/diff/static checks; it cannot inherit PASS from the failed card.
4. Do not start T3 merely because the failed correction's files look right. Proceed only after the independent verification/review gives an explicit, self-consistent verdict and the orchestrator records its evidence. If that replacement card also cannot complete, surface the infrastructure blocker rather than recursively creating equivalent cards.

This is a bounded recovery pattern, not a waiver of role separation, production authorization, or a required Design Gate.

Why bounded cycles, not unbounded re-reviews:

- Verdict self-consistency is a stronger signal than "the review ran". Re-running the same reviewer against the same body rarely produces new evidence.
- A narrow correction card makes each unresolved residual **discoverable by `file:line`** in the audit trail — far easier to reference when the next design or the next operator needs to know "why was this changed?".
- A fresh independent card on the corrected file cleanly supersedes the broken verdict; the old card stays in history as evidence for **why** the correction existed.
- This pattern sits alongside `references/review-budget-recovery.md` (which handles the alternative case — review that ran out of budget without verdict, requiring fan-out by acceptance surface). Both replace unbounded reviewer churn with bounded, evidence-linked correction cycles.

## 历史实现与最新冻结契约的漂移检查

当 RFC/SPEC/Design 在某次 Provider smoke、用户裁决或安全收敛后覆盖了旧语义时，T2 文档齐全不等于现有实现已可进入下一张 T3。创建任何 Implement 卡前，执行一次**最新契约 → 当前代码**的反向核对：

1. 从最新三层文档提取不可协商的行为向量：capability 是 fail-stop/stub/real-mappable、字段必须恒为 `None` 还是允许填充、refresh 在各注入状态是否可 fetch/upsert、真实 Provider 是否允许注册/调用，以及 query 的写入禁令。
2. 只读检查现有 domain object、stub/default payload、fixture、service 的 query/refresh 分支和已有测试断言；不能只看文档互引，也不能把旧 task 的 PASS 当作当前语义的证据。
3. 若最新契约要求“字段恒 None”“writer 已注入仍 NotImplementedError”“不得 fetch/upsert”等安全收敛，而历史 stub/fixture、mapper 或 happy-path 仍允许相反行为，即判为**契约—实现漂移**。即使仅发生在 fake/mongomock 路径，也会误导后续实现和测试，属于 T3 前阻断项。
4. 发现漂移时，**不要**创建泛化 T3 或重复旧 Implement。先创建 Principal-only correction card，同步 RFC/SPEC/Design 的代码 allowlist、禁止路径和可证伪验收；随后运行新的独立 Design Gate。仅在 Gate APPROVE 后，才创建最小 allowlist 的 developer repair → fresh Verify → fresh Review 链。
5. 纠正卡必须把用户授权的副作用边界写成代码级行为：例如未注入 writer 的异常、已注入但未实现的异常，以及两条路径的 fetch/upsert 调用数均为零；不得用“只对真实 Mongo 禁止”偷换为“fake/mongomock 可以写”。

此检查特别适用于 capability 映射、fallback/stub、持久化状态机、Provider activation 和字段语义变更，可防止“旧离线实现先行、最新契约后置”导致的重复开发或安全边界回退。

## 生产 rollout 的参数与时间语义闭合

当 Design 定义受控 rollout、backfill 或生产 read activation 时，除通用副作用边界外，必须审计以下常见的“文档可读但不可执行”冲突：

1. **全量范围必须有唯一的可执行输入。** 若 backfill 需要日期范围，CLI synopsis、参数表、伪代码、默认行为、action plan 与测试矩阵必须逐字一致地定义范围来源（例如 `--range-file`、`--start/--end`）、至少一个输入是否必需、参数组合的优先级/互斥性、日期排序去重、最大范围及无输入时的退出码。不得一处要求范围而另一处的“全量命令”不传范围；也不得让 Developer 决定默认范围。
2. **交易时态不能错误归因给格式校验。** “未来日期”“当日未收盘”“已完成交易日”“非交易日”需要可注入的 `TradeCalendar` / `CompletedSessionPolicy` 一类明确 owner、时区/cutoff、输入输出与 fail-closed 行为。现有 service 若只校验日期格式，文档不得声称其判定收盘状态或抛相应 `ValueError`。离线 T3 以 fake calendar + fake clock 证伪；真实 calendar 读取只留到已授权的独立 Activation 卡。
3. **预算过滤规则必须单义。** 对 repository / BudgetReader 的过滤字段白名单、`find` 与 `aggregate` 首阶段校验、空 filter 的错误类型及负向测试，应在 SPEC 与 Design 只定义一套精确集合；不要把 `market` 等字段留在一层而从另一层漏掉。
4. **修订后的 provenance 也属于契约。** RFC/SPEC/Design 任一层版本改变后，重新检查三层 metadata、source-RFC/SPEC pointers 与 changelog。一个 Design 继续指向已修订前的 SPEC 版本，是阻断性漂移，不是文档装饰问题。
5. **日期表示一旦被探测，必须贯穿同一轮的全部 validator。** 若入口通过样本探测 `YYYYMMDD` / `YYYY-MM-DD`（或其他等价表示），Design 必须列出该值传给 coverage、缺失值检查、候选日筛选、canary 排除、报告格式化的全部 callsite；不得允许其中某个 validator 静默回退到硬编码默认格式。Verify/Review 至少要做两套 main/CLI 等价的 injected/mongomock 测试：每套均放入一个缺失 `close` 的 canonical symbol，并断言它既进入 `close_missing` 又不进入 canary；同时确认原默认格式路径未退化。仅测 helper 的显式格式参数不足以证明 main 调用链正确。

这些项任一不一致时，创建覆盖所有受影响 RFC/SPEC/Design 文件的单张 closure-ledger Principal 修订卡；其后重新独立 Gate。不可用多张零散修订把同一执行语义逐轮推给 Implement。

## 失败处置

- **越界 stub / 实现文件**：先清理卡，随后重新运行本审计。
- **数值、tier、行为矩阵冲突**：派 principal 文档修正卡，不派 Implement。
- **生产副作用未获确认**：可继续推进仅 fake/noop 的实现；真实写入任务必须拆分为确认后的受控阶段。
- **RFC/SPEC/Design 任一层不一致**：修正所有受影响层后重审，不可只把临时决定塞进 T3 body。

## 参考

- `references/design-gate-checklist.md`：可复制的审计证据模板与常见矛盾类型。
- 与 `yquant-ai-coding-pipeline` 一起使用：后者负责阶段编排，本 skill 负责 T2 的实质性放行审计。
