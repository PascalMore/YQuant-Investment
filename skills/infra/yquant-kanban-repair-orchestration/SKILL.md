---
name: yquant-kanban-repair-orchestration
description: "YQuant 工程流水线中真实验证失败后的修复链重建、独立门禁与 Closeout 卫生。"
---

# YQuant Kanban Repair Orchestration

## 当前规则优先（2026-11-14） <a id="current-rules"></a>

- 本技能及原有 `references/` 的唯一维护源为项目 `skills/infra/yquant-kanban-repair-orchestration/`；不维护 profile 同名副本，frontmatter name 不变。
- 后续新任务服从 [AI Coding Pipeline 现行契约](../ai-coding-pipeline/SKILL.md#unified-validate)：Full / Light 共用独立 `yquantreviewer` Validate（测试、消费者/反例审查与裁定），tester 非默认；Full 保留 RFC/SPEC、Design 两阶段及三份独立文件。修复沿已有图闭合，不因恢复默认新增 Verify→Review、设计或 Closeout worker。
- 新任务的目标、范围、计划、负责人、依赖、进度、状态与交接摘要只在 Kanban；不创建或维护 `data/tasks/`、任务正文镜像、逐卡全文 handoff 或重复 Closeout 报告。小任务用 Kanban 结论及必要日志，复杂任务一份正式验收报告与原始证据；目录遵循目标项目 AGENTS，YQuant 为 `data/reports/YYYY-MM-DD-short-topic/`，临时探针/中间文件仅用当前 profile scratch，不作第二状态源。
- 下文及 `references/` 中的 Quick、分离 Verify→Review、tester 默认验收、强制正文/交接镜像与独立 Closeout 卡均仅属旧任务兼容或原事故记录，不对新任务生效；原失败结论、file:line、报告与证据保留，不据旧配方批量迁移历史或新增门禁。仅缺登记时复用适用证据，不重跑；真实缺陷仍须最小修复与新候选的独立 Validate。
- 下文历史中的配置/模型/认证操作、外部通知订阅、生产写入及 SQLite 兜底不构成本次或今后任务授权；须同时满足明确卡面授权与 runtime 限制。看板优先使用原生 `kanban_*` 工具；安全拒绝停止对应动作，不换形态重放。历史凭据注入示例服从当前凭据工具与项目边界，不复制秘密。
- 配套 [worker-budget-recovery](../worker-budget-recovery/SKILL.md#current-rules)同为项目源。下文点名的 `yquant-agent-operations` 是主控 profile-local 配套，不假定 worker 可见；新任务所需边界应内联卡面或引用本项目现行契约，不为此迁入第三个技能。

## 恢复方法与旧任务兼容参考

> 补充参考：`references/review-required-late-timeout-recovery.md` 说明代码卡已按 review-required 阻塞后收到迟到 timeout 通知时，如何以真实 Kanban 状态和路径过滤实物恢复流水线、避免重复实现。

> 用户中途裁定某 capability 移出本期目标时，按 `references/scope-scission-cascade.md` 走「裁定落档 → 三层文档 scope-scission → Verify/Review → master Re-baseline → Verify FAIL→P0 Fix 闭环」的完整链条；重点防止"changelog 声明已同步但正文未同步"的声明先行陷阱。

> 若严格 allowlist 修复卡被 auto-decomposer 擅自改派、重写 body、拆子卡或在共享树创建未追踪 `handoff/`，按 `references/auto-decomposition-contamination.md` 先止损、保全现场，并用可信上游 parent 重建源码实物驱动的 Verify → Review；不得把被污染 root 或其 child 当作通过依据。

> 研究类产出（多窗口汇总表、风险判定重算、指标载体）没有代码 bug 要修，只有一份产物要证明它对，因此**不需要完整修复链**。这类任务的验收角色分工、对拍基准生成规则、检查项数量控制与旧清单退役映射，按 `references/research-output-verification-role-split.md` 执行：验收归单角色完成，复审只在「改了多层契约文档 **且** 涉交易/风控语义」时才开，技能文档修订与纯数值研究均不触发。

适用于 YQuant Full / Light 中，独立 Validate（旧链为 Verify 或 Review）发现真实缺陷后，需要修复并重新取得独立证据的工程任务。它补充通用 AI Coding Pipeline：重点是**失败证据保留、替代链重建、关闭旧链残留与诚实 Closeout**；以下旧链步骤按上方当前规则优先解释，不作为新任务默认图。

## 核心原则

- 验收失败就是失败：不能因为旧测试大多通过而放行。
- 保留首次失败的 run、报告、交接和反例原字节作为审计证据，禁止改判或覆盖。区分「无修改重试以冲掉 FAIL」与「新 Fix 后独立 R2」：后者可按下述条件复用原卡，原 FAIL 仍是有效历史。
- 修复后的独立 Verify 必须针对新候选取得 fresh 证据。满足「blocked Verify 原地转复验」条件时优先复用原卡作为 R2；不满足才新建替代复验卡。已经执行或失败的 Review 必须取得对新候选的 fresh 独立审查。原 Review 从未开始、仍为 todo 且验收范围未变时可复用：Verify ID未变就只更新正文及证据入口；Verify ID改变则先绑定新依赖，再移除旧失败依赖并读回，不能把旧候选的审查结果当成新候选已通过。
- 按原流程的必要门禁 Closeout：Full Flow 要求独立验收 PASS（现行合为一个 Validate 阶段，由 reviewer 同时做测试验证与审查裁定）；Light Flow 的明确、局部修复保留独立验收与既有 Closeout 自审，不因发现一个实现 bug 自动新增第二个验收阶段或重开 RFC/SPEC/Design。
- 离线验证通过不等于真实 OCR、数据库写入、服务重启或生产生效；Closeout 必须分开陈述。
- 用户要求整体梳理多轮执行时，先把批次证据、真实数据、分片状态与交付契约合成一张闭合清单，再汇报；不要继续用批次数或下一批编号代替剩余工作。数据同步的取证顺序见 `references/real-platform-acceptance-triage.md` 的“多批数据同步：先核缺口，再裁定恢复”。
- 用户只批准建议中的部分阶段时，在任务正文和下游卡注明本次完成边界；若数据恢复依赖代码修复，先完成必要修复与独立验证，再续原已授权执行，不按建议编号机械并行，也不自动启动未批准的最终验收或长期调度。
- 用户纠正「该调整的是校验依据，不是再加一套架构/机制」时，修复动作必须落在**判定依据本身**（阈值、证据口径、校验顺序、拒绝条件），不得用新增 helper、框架、第二客户端或通用验证层来绕开原问题。这类纠正要同步三层契约与后续卡面，否则下游仍按旧依据继续实现。
- 多角色流水线共用 `dir` 工作树时，候选字节、受保护字节、历史证据字节必须**分清单记账**；获准变更的路径只能从保护清单中“减去”，其余项 SHA 逐字沿用旧值，不得按当前字节重算。详见 `references/candidate-identity-ledger.md`。

## 规约/文档语义改造的修复链：allowlist 必须含引用闭包

当被修对象是共享规约本身（canonical skill、根 `AGENTS.md`、角色 SOUL/AGENTS、正式 RFC/SPEC/Design），验收退回的典型 finding 不在“修改对象”而在**被引用但未修改的历史文件**：规范正文直接链接的实跑日志/验证报告仍以祈使句现行语气表达旧规则，读者读到即照执行。

- 派卡时把“直接修改清单 + 规范正文直接引用的文档清单”一起写进 allowlist；不写也要在验收契约里显式要求检查引用目标的存在性与现行语气，否则必然在此处退回。
- 历史段只加一句“历史”提示不够：正文中残留“必须/一律”祈使句仍是现行语气；`<details>` 折叠对模型无效，折叠段照样完整进入上下文。真正的减法是把成规模历史迁到 `references/history/`，正文只留指针。
- 修复后由编排层做受限校准（实际变更集合恰为授权集合、其余候选与旧证据字节未变、最终 hash 与作者自报一致），独立复验复用原卡只复核新差异。**被安全扫描拒绝的聚合探针标记 OMITTED_BY_AUTHORIZATION，不换命令形状等价重现**；替代证据用窄而直接的原生命令。
- 编排层或 worker 走过的越权路径（绕过审批、被拒后换命令继续）单独作为流程事件记账，与功能结论分列；用户保留其成果不等于追认其执行方式，下游不得沿用“只读所以不受停手约束”一类辩解。

完整的现行层扫描表、引用闭包判定与冻结范围修复链见 `yquant-agent-operations` 的 `references/rule-doc-refactor-acceptance.md`。

## 何时重建链

出现真实缺陷后，先停止无修复重跑，再选择 fresh 验收的载体；不要把 blocked 状态本身当作必须重建整图的理由。

1. 原卡从未 PASS、失败证据可按轮次保留、验收语义不变且无阻塞循环限制时，优先下述「原卡 R2」；只新增必要 Fix，保留尚未运行的下游门禁。
2. P0/安全边界变化使原验收不再适用、公开契约或验收范围改变、旧 PASS 将被混用、或已触发阻塞循环限制时，保留旧链并创建窄替代链。
3. Review 要求修复后重新独立验证时，必须取得对新候选的 fresh 证据；fresh 指新候选上的独立运行，不必然指新卡 ID。

不要把旧失败卡**原样** `kanban_unblock` 当作修复后复验卡；不改 scope 的重跑会混淆失败证据与新实现证据。失败证据已按轮次分文件隔离时，按下一节原地转复验。

### blocked Verify 原地转复验（同一卡升 R2 门禁）

原 Verify 卡因真实 FAIL / needs_input block（非通道故障）、失败证据已按轮次分文件落盘（R1 报告、交接、run 历史）时，可原地复用该卡作为修复后复验门禁，避免卡片图重排：

1. 建 Fix 卡：allowlist 仅 findings 涉及的文件，body 逐条内嵌 file:line 证据与最小修复要求。
2. `hermes kanban link <fix-id> <verify-id>` 给原 Verify 卡追加新父边；先加边，后动状态。
3. 覆盖原 Verify 卡 body 为 R2 范围：逐条核验 finding 真实闭合（新增反例断言存在且通过）＋完整验收矩阵无回归；R2 证据一律用新后缀文件名（如 `verify-*-r2-*`），禁止覆盖 R1 报告与交接。
4. Fix done 后先按窄修前的路径/hash基线核对实际变更集合、受保护文件和原失败证据，再 `unblock` 原卡；不能只相信作者自报的修改文件与通过数。读回 parents/status、R2 正文与镜像，以及最新 run 的 id/PID，区分“已解除阻塞”“可派发”“实际运行”；dry-run 通过不等于 worker 已启动。R1 的失败 comment、run 历史与报告全部保留，不改判、不删除。
5. 下游尚未运行且仍依赖原 Verify 的 Review/Closeout 无需重挂。更新其正文镜像并读回：明确 R1 失败报告是历史、R2 报告/交接/候选身份才是当前审查入口，避免 Review 只读默认旧报告而重复裁定同一 FAIL。单列已授权的文档范围补充及 Fix 路径，不能拿旧 C3 allowlist 或旧 Design hash 误判新 Fix 越界。
6. 用 `hermes kanban show <id> --json` 核对当前卡与后代的真实依赖和状态，并逐字比对正文与镜像；当前 CLI 的依赖数组位于返回对象顶层 `parents`，不是假定嵌套的 `task.parents`。先核实际返回结构，不能因编辑成功就声称门禁已串好。

**重复阻塞计数不会因原地升级轮次而自动清零。** 同一 Verify 卡先后产出 R1、R2 真实 FAIL 时，即使分文件留证并更新 body，第二次 block 仍可能触发 `block_loop_detected` 而进入 `triage`。原地复验前先读现有 block 事件的 recurrences/limit；不要把换标题或新 run 当作新的阻塞预算。已进入 triage 且仍有真实缺陷时，保留失败卡，不用 complete 或数据库修改制造通过，也不无修复重派；用户授权剩余最小 delta 后建立窄 Fix → fresh Verify，并复用从未执行的 Review（先加新 Verify 父边、更新正文，再删旧 triage 父边，最后读回）。fresh Verify 完成不会自动释放仍挂在旧 triage 卡下的 Review，必须核对真实 parents；尚未成功改挂时如实报告审查未启动。

### 退出 `triage` 列的唯一受支持路径

`block_loop_detected` 之后，卡不再接受 unblock / promote / schedule / reassign，直接 `complete` 也可能报 unknown id 或 terminal state——这不是卡损坏或 ID 丢失，不要连续盲试状态动词。唯一受支持的退出是 `hermes kanban specify <task-id> --author <orchestrator> --json`，它把卡降级回 todo 交由 dispatcher 重新 promote。

**specify 会用辅助 LLM 重写标题与正文**，所以冻结正文的卡必须按序做：① 先把现行 body 存成任务目录镜像；② specify；③ 立即 `hermes kanban edit <id> --title "<原标题>" --body "$(<镜像>)"` 把契约正文恢复；④ `hermes kanban show <id> --json` 读回，确认正文逐字一致（比对只对双方 `rstrip("\n")`）、parents 未变、status 已从 triage 变为 ready；⑤ 读回新 run 的 id/PID 与心跳后才称“已重新派发”。

指定模型（`hermes kanban set-model`）与恢复正文顺序要分开做：先写正文并读回，再恢复派发。`--json` 返回 `ok:false` 且 reason 是瞬时 LLM 错误（APIConnectionError）表示卡未被改动，重试一次是对的；持续超时/跳过则停止重发，不要把“specify 没生效”读成卡坏了。

通用恢复规则见 [worker-budget-recovery](../worker-budget-recovery/SKILL.md#current-rules)，抽查见其[候选契约清单](../worker-budget-recovery/references/candidate-contract-spot-checks.md)；本节只覆盖 YQuant 看板的旧 triage 退出形状。候选字节/受保护字节/历史证据字节的分清单记账见本 skill 的 `references/candidate-identity-ledger.md`。

## 过重契约：替换契约，而不是打补丁

> 完整流程、最小信号识别表、派卡前矛盾自检表与汇报格式见 `references/over-engineered-contract-replacement.md`。

“设计太复杂，按最简单的方式做”是与“简化文档措辞”不同的一类裁定：它否定的是**已冻结的契约本身**。沿用原卡继续跑，等于让每个下游 worker 重新读一遍并重新实现被你否掉的分类表，每一轮都耗掉一次完整 worker 运行，并且再产出一轮修订循环。

按以下顺序执行：

1. **先停止失效契约的执行，再改安排。** 查询当前 run；有活跃 worker 时用 `hermes kanban reclaim <id> --reason '<用户已批准契约纠偏>'`，读回终止事件后冻结旧卡。只发 comment 不证明旧 worker 已停。保留源码、测试、旧文档副本与失败证据，不 reset/stash/clean，不把旧卡改成 PASS。
2. **先校准已有候选，再裁剪需求。** 冻结精确路径/hash，必要时运行一次原受影响完整回归，区分已验证基线、尚未验证代码与真实缺口。同时看测试耗时与 Agent 往返/探索成本，不能仅凭大测试计数认定测试太重；主控校准不冒充独立验收。
3. **按当前价值划清底线与增强。** 列出当前目标必需的数据正确性、安全边界及其最小充分证据，再列用户批准移出首版的泛化、并发保证和附加机制。一次有限迁移先处理已知集合/真实 metadata，不预建任意数据平台；数据采集保留来源、时间精度、幂等、缺口和标签隔离。不把移除复杂度变成降低这些底线，也不以安全为名自动恢复已否增强。
4. **一次替换权威契约，不在旧正文后叠豁免。** 用短清单写清精确文件、执行顺序、常量的作用对象、允许写动作与不做项；受影响的独立 RFC/SPEC/Design 同步主正文、版本和互引。先保留旧版本证据，再消除活跃旧条款与新裁定的冲突，不重新铺陈已拍板的备选方案。
5. **复用正确成果，只改可定位差分。** 已正确且有覆盖的增强可以留在内部，但不再是首版新增必验条件；不要为了显得简单而强拆正确代码。把未通过的原断言区分为数据/安全底线和已退役契约，保留前者，只对后者有据调整并列映射，禁止删断言求绿。
6. **按可独立交付的结果解耦，不按机制继续拆卡。** 用户批准后，将工程可用、真实迁移、历史覆盖/每日运行分别定义成功范围；工程门禁不等待生产密钥或回填日历，生产执行也不顺手编码。工程 PASS 不等于生产 PASS；固定全量目标未取消时，不用样本日代替，覆盖、缺口和未结算标签分别报告。不要为每个状态再建平台或独立 Activation 阶段。
7. **只建立必要的替代依赖。** 先检查已有图；范围未变且未运行的卡可按既有规则复用，契约已变的旧卡留审计并明确 superseded。新卡逐张使用真实 parent 与 idempotency key，正文内联同一份短裁定并指向完整冻结文件；不复制整段历史日志。用 `show --json` 逐张核 body、必要依赖、模型、工作目录及状态；生产尚缺事实时预先 blocked，避免空跑。独立门禁按已选流程保留，不因纠偏再堆重复审查。
8. **派卡前做一次矛盾核对。** 检查禁止项与验收是否冲突、常量是否悬空、测试路径是否已迁位、工具是否能完成指定动作、旧强制机制是否仍潜伏在下游正文。汇报删掉/保留了哪些要求、已经验证的实物和当前真正执行的卡，不以建卡数或调度恢复冒充产品进展。

对用户汇报时要给**契约的差量**（“这些概念没了，现在只靠这两个信号定案”），而不是只描述新链，否则用户无法判断复杂度是否真的降下来了。

### 状态询问与阻塞汇报的写法

- 用户问「当前进度」时，先给**阶段 + 实物变化 + 下一真实依赖 + 生产边界**，再给计数；不要复述上一轮已说过的结论，也不要把开发自测当独立验收。每轮新增的独立证据（新鲜命令、fresh Verify、Review）才写进结论，其余只说“未变”。
- 区分三种状态并逐项写明：**已通过（工程离线）**、**仍阻塞（附具体缺口）**、**NOT_RUN（生产/网络/DB/写库/调度）**。合并成一句“基本完成”会让生产覆盖被误读。
- 阻塞时给**一行可执行替代方案**让用户拍板（例：改用直接静态只读 Git 而非解释器包装），不要只报告阻塞现象；也不要重复索要用户已给过的授权。
- 迟到的重复状态通知（同一卡、同一结论再次推送）只需确认“与上一轮一致、无新增”，不重新展开分析、不重复建卡。

## 卡 body 内部矛盾会直接吃掉一轮 worker 运行

worker 因 body 自相矛盾而 `needs_input` block 不是 worker 缺陷，是编排缺陷，且完全可预防。派卡前逐条对照：

- 验收要求全文不得出现某 token ↔ 同一 body 又要求 changelog/摘要必须写出该 token。
- 设计章节列了常量 ↔ 冻结步骤与下游实现卡都没有该常量及其作用对象。
- “不得修改 X” ↔ 同一 body 的验收要求修改 X。

命中时**在派卡前**就改口径，别让 worker 用一次运行去发现你自己写出来的矛盾。

### 停手条件写得过宽，同样会让 worker 停在一半

“遇到任何拒绝/失败立即停止并留证”这类写法会被 worker 套用到**非安全类**返回上，代价是一整轮只走到半路。最常见的两种误伤：

- **文件工具的前置校验**：局部 patch 后整文件 write 被要求“先完整重读当前文件”（防陈旧覆盖 / 匹配失败）。这是工具自带的恢复协议，不是安全审批拒绝；按提示完整重读后正常合并写入属原授权工作。不写清楚时 worker 会自行撤销半成品并 block，等主控批准一次本该允许的文件写入。
- **正常的能力性失败**：测试断言失败、依赖缺失提示、参数校验拒绝，属于工程信号，不是“需要人批准”。

因此停手条件必须显式限定为**安全审批 / 策略 / 凭据边界**类拒绝，并另写一句：文件工具的前置校验按其提示正常恢复，不视为拒绝、不单独 block、不需追加授权。判据是工具返回语义，不是返回码名字。

## CLI 取数与范围核验的实操坑

- **先做一次看板发现，再按真实ID定点读取**：已有卡ID时直接 `hermes kanban show <id> --json`；只有查重或发现任务图时才运行 `hermes kanban list --json > <任务目录>/board-before.json`。list 返回会混入其它 tenant/项目的历史卡且体积可达数兆字节，判断当前卡状态一律用 `show <id>`，不要从 list 的截断输出推断当前卡是否 done。解析落盘响应后只输出相关卡的ID、标题、状态、角色和工作目录；不要把全板正文送进上下文，因为历史卡可能令单次输出膨胀到数兆字节，挤掉当前证据。需要完整正文或依赖时再对目标卡用 `show`，不要重新倾倒全板。仅遇到响应内未转义控制字符时使用 `json.loads(text, strict=False)`，保留原始响应，不把宽松解析当作字段或契约校验。
- `git diff --check` **不覆盖 untracked 文件**。对每个新建文件执行 `git diff --no-index --check /dev/null <path>`，同时记录退出码、stdout 与 stderr；如需特定空白规则，另在获准范围明确配置。`--no-index` 带有差异退出码语义：新增内容可返回 1 且没有空白错误诊断，不得据此判成验收失败或强求返回 0；出现空白错误诊断或其他执行错误则不能放行。普通 tracked diff 返回 0 也不证明 untracked 文件已检查。
- 汇总验证计数前先定义口径，并对逐项结果程序化求和：正向断言、链接检查、用例数和 RED 对照分别列出；RED 中预期出现的失败不能混算为正向全部通过，重复运行同一组断言也不能宣传为新增覆盖。合计与明细不符时先纠正文案/统计，不重做已经通过的实现或增开工程门禁。
- 对 `todo` 状态的卡调用 `kanban_block` 会被 API 直接拒绝（`cannot block <id>`），改 `kind` 也无效；此时只能用 durable `kanban_comment` 隔离，并明确它不会被重新派发。
- 批量 `block --ids ...` 可能只冻结了前一张卡并以非零退出。逐张 `show` 读回确认，不要因整体非零就重跑全部，也不要因一条成功提示就宣称全部已冻结。

## 修复进度查询：区分存活、落盘与验收

1. 先查原卡、修订卡、独立门禁和待执行后代的当前 `show <id> --json`，自动完成/阻塞通知只作为查询触发，不作为重新建卡或再次请求开工的理由。
2. 分开读取当前 `task.status`、顶层 `latest_summary`、最新 run 的 outcome/metadata 与最后有效事件；旧 run 的 blocked 摘要不能覆盖卡已回到 todo 的当前状态，`task.result` 为空也不代表没有交接。
3. 对比精确 allowlist 文件的存在性、版本头、SHA256 和路径过滤状态；同时列出尚不存在的交付物。仅有 PID/心跳，不能宣称文档已修订、代码已实现或门禁已通过；即使哈希改变，也须核对改动内容后才能声称某条 finding 已闭合。
4. 心跳持续但文件未变时，用 `hermes kanban log <id> --tail <bytes>` 读取有界日志，区分读取/定位、准备写入、实际落盘、执行验证和等待外部调用。`--tail` 的参数是字节数，不是行数；不要倾倒整份日志或凭存活信号断言没有卡顿。
5. 面向用户先给当前阶段与实物变化，再给独立门禁、下一真实依赖和生产动作边界；文件仍未变时直说“修订仍在运行，新版本尚未落盘”。不按耗时、心跳数或建卡数推算完成百分比，不把作者自检当独立复核。

## Timeout / iteration-budget 耗尽的恢复协议

`timed_out`、`Iteration budget exhausted` 或 dispatcher reclaim **不是实现失败结论，也不是通过结论**。在创建重试或替代链前，Orchestrator 必须做一次当前树的证据校准：

1. `kanban_show` 读取最后 run 的 error、heartbeat 与 metadata；核对这是否是 iteration budget、进程超时还是显式测试失败。**注意 dispatcher 竞态：timeout 通知到达时，dispatcher 可能已自动 claim 一个新 run。** 若新 run 只是对同一宽任务的 unchanged replay，先立即 `kanban_block(kind="transient")` 冻结它，再做盘点；不要让第二个 worker 在未校准候选产物和失败原因前继续修改共享树。
2. 对共享工作树执行只读盘点：`git status --short --untracked-files=all`、path-filtered `git diff --stat` / `git diff --check`、候选文件存在性；必要时检查 worker PID 是否仍存活。不得 reset/stash/clean。
3. 对候选实现运行**原卡所列最小完整定向测试集合**，并保留真实计数；不要只因新文件可存在或 scoped `diff --check` 通过就放行。timeout 后已落盘的代码既不能因未交接而丢弃，也不能因文件存在就直接放行。失败须先分为冻结契约与既有静态断言冲突、候选生产代码缺陷、或测试/实现接口失配。
4. 若测试失败，先区分：
   - 生产行为缺陷；
   - 新测试误用既有公开 API / 结果语义；
   - 文档或 allowlist 契约漂移。
   使用实际函数签名、数据模型/结果对象定义与失败 traceback 校准，禁止根据 worker 沉默或旧文档猜测。对混合失败逐条给出生产缺陷或测试缺陷的证据：先核对 fixture 是否满足 venv/可执行文件等入口前提，避免把合法 skip 当作业务失败；再对照既有 argv 与 cwd 契约，避免为满足新测试而把正确的相对路径改成绝对路径。过滤后的空文件可能是正确结果，不应要求内容包含输出文件名。
5. 将旧任务 `block` 并在 comment 写入命令、通过/失败计数、file:line 根因和替代链 ID。不要直接让 dispatcher 自动重试同一任务。
6. **最小修复原则**：若失败仅是新测试误用既有稳定契约，则 Fix-N allowlist 只包含该测试；明确禁止改生产代码、放宽断言、删除测试或扩大 mapping。Verify-N 必须再次验证该公开契约及原有行为。
7. 若生产代码确有问题，Fix-N 只允许已批准的最小 production allowlist，取得新的独立 Verify；仅在原流程要求时追加独立 Review。

保留 timeout 卡作为运行历史；Closeout 必须依赖替代链已通过的必要门禁，不能以旧 timeout 的 downstream todo 卡作为放行依据。

### 两轮连续 iteration-budget 耗尽：改走窄范围 “path-filtered reconciliation”，不要做第三次重写

如果同一冻结契约缺口在**前一张 Fix 卡**和紧接的**独立 Verify 卡**上连续两次耗尽 iteration budget，**不要**再派一张要求把两轮工作合并重做的宽 Fix。宽任务会 (1) 同样原因再次超时的概率更高；(2) 把“哪部分候选其实已经落地”藏在一次往返里；(3) 让 worker 为了塞进预算而放松冻结范围。

正确做法是 **path-filtered reconciliation**：

1. 立刻停手，直接读活的工作树。`git diff --stat -- <allowlist>` 加既有测试复跑，确认前一轮候选已经覆盖哪些契约条目。
2. 派新的 Fix 卡，body 必须**逐项**列出前一轮已落地的内容与仅剩的缺口；allowlist 只允许关闭剩余缺口，禁止重新打开前一轮已经收敛的条目。
3. Verify-N 的 body 必须明确接受前一轮候选作为基线：重新跑完整验收矩阵（不只是新缺口），并对 path-filtered diff 做归属核验后给出判定。
4. 给两张旧超时卡加 `superseded by <replacement ids>` 永久 comment，**不解除**。

**触发条件**（任一即可）：
- 活的工作树已含前一轮预期的改动（path-filtered diff 看到预期插入）；
- 剩余缺口在活树或上一轮 worker 最后 comment 中可观察，不是“沉默”导致的未知；
- 不加新 Fix 重跑冻结测试集时，前一轮 gap 部分已通过。

**不应走这条路径**（回退到既有 recovery 步骤）：
- 工作树不包含超时卡的任何改动 → 这属于 *handoff gap*，不是“部分实现”，按“timeout/gave_up 卡 ≠ 实现缺失”段重跑校准；
- 超时由 worker 崩溃引起，而非模型迭代耗尽 → 先修崩溃，不要再开新卡。

本模式补充 `references/fixed-command-micro-verify.md`（候选已完整落盘、只需 tester 判定）和 “Verify-FAIL recovery” 链（候选不合格需要新修）；本模式处理“候选部分到位、单次窄 Fix 收尾”的中间情形。

### 运行时长上限截断（`elapsed Ns > limit`）不是 iteration-budget 耗尽

带 `max_runtime_seconds`（如 720s）的 Verify/Implement 卡，其超时错误签名是 `elapsed 725s > limit 720s`（事件附 worker PID 与 `retry_status=ready`），与 `Reached maximum iterations (N)`（`agent.max_turns` 轮数耗尽，各 profile 现为 150）是**两种不同故障**：前者是单次运行墙钟超限，不是测试失败，也不证明候选完整。各角色 `--max-runtime` 默认值以 [AI Coding Pipeline 墙钟上限](../ai-coding-pipeline/SKILL.md#runtime-limits)表为准（唯一源），不在本 skill 重复。

**先判候选完整度，再选择恢复路径。** 下述“复用成果、只补收尾”快路径仅适用于所需产物已完整落盘且可独立核验的情况，此时不要重复建实现链。若仅修改了版本头、changelog 或部分正文，另一层文档仍为旧版本，或缺少完整 handoff，不得解释为“已完成，只差交接”；按下文“Timeout 留下文档但没有 handoff”做 NO-GO 审计，保留部分成果、定位剩余缺口，再决定最小续接。版本号和 changelog 的闭环声明不能覆盖正文残留冲突。终态通知中的 `retry_status=ready` 也不是新 worker 已启动的证据，须读回当前 status 与最新 run。

完整候选的恢复顺序：

1. 读该 assignee profile 的 scratch 目录，枚举 worker 留下的验证脚本与 pytest basetemp（时间戳可证明哪些验收项已实际执行）。
2. **亲自复跑这些脚本作为校准**（compile、保护哈希、coverage 名单比对、探针断言等），取得全绿的独立证据；Orchestrator 校准不是验收，仅用于决定恢复路径。
3. 给卡 comment 写明：超时是时长上限非失败；已完成项清单 + 校准结果；重派后**只补收尾**（真实 dry-run 读回、行数/计数清点、`kanban_complete` 交接），禁止重跑已完成项。
4. `kanban_unblock` 重派；带该 comment 的第二次运行通常几分钟内即可 PASS 收口，避免再撞同一上限。

### 窄机械收尾的 Orchestrator 直做：候选补全的诚实边界

多轮 worker 预算耗尽后，若剩余 delta 只是**零语义的机械改动**（压缩注释/行数以满足 Design 上限、合并重复 fixture、恢复一行被丢的诊断字段），再派同角色卡大概率同因超时。此时 Orchestrator 可以直做收尾，但必须守住边界：

- 只动剩余缺口的精确文件；逐次用 `ast.parse` / `compile()` 校验语义等价，并对测试函数名集合做前后 diff，证明零覆盖丢失。
- 完成后跑**完整冻结回归**（不是只跑被改文件）并记录真实计数与 `git diff --check`。
- 以 `kanban_complete` 关闭 Fix 卡，summary 逐项写明改动、命令、计数与零生产副作用——这是**候选交接**，不是验收。
- fresh 独立 Verify + Review 不可省略；「Orchestrator 自己改的」不构成跳过独立门禁的理由。

禁止把此模式扩展到任何语义性改动（断言、契约、生产逻辑）——那必须仍走 developer 卡，不得以「只是小改」为由自我实现。

**契约文档是例外**：用户对一张即将发散的契约修订卡裁定「精简、不要发散」时，Orchestrator 直接停止该卡（complete 注明改走精简路线）并**亲自完成窄文档修订**（RFC/SPEC/Design 各一个窄小节：行为契约 + 验收矩阵 + 精确实现范围，一次定案不铺陈备选方案）。文档是 Orchestrator 自己的仲裁工具，不是被验对象；实现卡与独立 Verify 照常派 worker，不因文档直做而豁免。区分边界：改文档语义可以直做，改代码/测试语义永远回 worker 卡。

### 替代链下的未 claim `todo` 后代：durable comment 隔离，不要尝试 `kanban_block`

替换链是新建 Fix 而不是已 done Implement 的小修时，原链的 `todo` Review / Closeout 后代**不在新 parent 链上**。`kanban_block` 在已 `todo` 状态上**会直接被 API 拒绝**（返回 `cannot block <id>`），改 `kind` 也无效。强行 unblock 一个 stale `todo` 会让 dispatcher 立即重新 claim 并跑一遍过时的 smoke。

正确隔离顺序：

1. 在新 Fix / Verify 卡创建之前或同时，给**每张**未 claim 的 `todo` 后代（Review、Closeout）发一条 durable comment，明确写出「do not dispatch / do not rerun；replacement chain = `<新 fix id>` → `<新 verify id>` → `<新 review id>`」和 `superseded by` 引用。
2. 给被替换的 `blocked` 父卡（Verify）发同一条 comment，让父卡**保持 blocked**：即使 dispatcher 重算 ready 也不会 promote，因为所有 todo 后代都没有真实 parent 满足条件。
3. 把这些 `todo` 行明确归类为 **quarantined board debt**，在 Closeout 报告里以 id 列出并说明终态延后原因。
4. 替换链完成后，**不要**解除或 archive 这些卡，除非用户明确批准；它们只保留作为审计证据。

**批量冻结按卡核验**：一次 `block --ids ...` 可能已冻结前一张卡、却因后一张卡的状态迁移不受支持而以非零退出。立即逐张 `show` 确认 status、parent、最新 run 与暂停评论；不得因整体非零就重复全部操作，也不得因出现一条成功提示就宣称全部已冻结。对仍为 todo 的卡，证明它确实依赖未完成或已暂停的父卡，才能称后续执行被阻挡。

**判断信号**：当新 Fix 的 `parents=[<上一步 done>]` 而原 Review / Closeout 仍 `todo` 时，这条规则一定适用。

若独立 Verify、Review 或 Closeout 尚为 todo、从未开始运行且验收范围未变，可复用相应待执行卡：先取得替代上游的真实 ID，用 `hermes kanban link <new_parent> <pending_child>` 添加新依赖，再 `hermes kanban unlink <old_parent> <pending_child>` 移除旧失败依赖；Review 应等待 fresh Verify，不直接越过它依赖 Fix。更新任务正文及逐张 `hermes kanban show <id> --json` 读回 parents，先加后删以避免短暂提前放行。该条只覆盖从未运行的待执行卡。已失败的 Verify 另按「blocked Verify 原地转复验」条件判断；已运行或失败的 Review 仍须保留旧证据并取得对新候选的 fresh 审查。不要为形式整齐重建已存在的完整图。

### timeout/gave_up 卡 ≠ 实现缺失：先跑冻结回归再决定建链

卡状态为 `timed_out` / `gave_up` / `blocked` 且 worker comment 留有失败分类时，**comment 中的失败计数是中间态快照，不是当前事实**。2026-08-07 P3-C T3 案例：卡因 iteration budget 60/60 两次超时被冻结，worker comment 留"161 passed / 4 failed"，被连续多日当作"未完成"；Orchestrator 在创建 Fix-N 前先做两项只读校准——

1. `git log --oneline -5 -- <allowlist 文件>`：候选实现可能已被 auto-commit（如 277752e）完整提交，diff 早已不在工作树；
2. **实跑原卡冻结回归命令**：对原卡所列测试文件执行 pytest，得到 165 passed 全绿。

若校准后全绿 → 这是**交接缺口（handoff gap）不是实现缺口**：直接创建 Verify → Review 链验证既有 commit（Verify body 明确"验证已落地 commit，非重新实现"），**不要创建 Fix-N 重建链**，避免重复实现与重复建卡。只有校准后确实存在可复现失败，才进入 Fix-N 路径。

## 严格 allowlist 漏项：公共契约迁移影响既有回归

当恢复验证发现失败位于**当前严格 allowlist 之外**的既有 colocated 测试时，不能以“只是测试”直接修改，更不能把它当作无关 flaky failure。常见触发是公共方法签名或稳定异常语义迁移：测试因缺少新必传参数而在真正要验证的行为（例如缺 writer 的既有错误）之前抛出 `TypeError`。

1. 先保存真实 traceback、旧测试的行为意图、当前公开签名和最小失败计数；区分：
   - 测试确实误用已批准的新公共契约；
   - 测试期待的异常类型与稳定错误码契约漂移；
   - 生产实现本身仍不符合文档。
2. 若缺失测试路径不在 allowlist，立即停止 Fix-N；不得凭“仅测试”扩展范围，也不得修改生产实现以迁就旧测试。
3. 请求用户明确重锚：唯一新增路径、理由、保持的公共语义和禁止扩大项。若用户未授权，维持 BLOCK。
4. 用户授权后先判断变化层次。若只为修复既有契约缺陷补充精确文件清单、没有改变字段/状态/接口/验收语义，且用户已确认最小范围，由主控只补 Design 的阶段专属 allowlist 与范围记录即可；不要自动重开 Principal 文档链或改动未受影响的 RFC/SPEC。保留上一实现阶段原清单及其历史归属，Fix 清单独立列出 exact N / no N+1。若公开语义、跨层权威或归属仍冲突，再走 **Principal-only scope reconciliation**，同步受影响正文、互引、职责矩阵和禁止项。
5. 对齐后记录新文档 hash，并在 Fix、复验、Review 正文中区分旧历史身份和当前权威身份；只创建必要的窄 Fix，按原卡 R2 或替代链条件选择门禁。Fix 仅修改获批路径；如异常语义已冻结为稳定错误码，修正测试断言，禁止将生产实现放宽回旧 `TypeError` 或 legacy 行为。
6. replacement Verify-N 必须重新运行原冻结回归，另外证明：显式新参数能使测试到达原本意图的分支、date/cache/side-effect 契约仍成立、且未触发任何真实 I/O。fresh Review-N 必须检查文档的 N 文件 allowlist 与最终 diff 一致，且 verdict 为 0 open blocker/major/minor 才可 Closeout。

不要把该分支压缩成连续“窄文档修订”循环：每次范围改变必须有新的真实失败证据和用户重锚；同一公开契约反复发生范围漂移时，先向用户汇总 closure ledger，再决定是否继续。

## Worker 卡预算耗尽的预防：先写测试，再改实现

反复出现「Iteration budget exhausted」且同一冻结缺口反复跨卡时，根因通常不是问题太难，而是 worker 把预算花在**通读与重复定位**上，而非落盘。派卡与续接时按以下顺序约束：

1. **第一项文件写入必须是测试**（先 RED），实现改动在测试之后；已有测试文件缺失时，先补测试文件再修源码，否则每次重跑都只能得到「导入即崩」而非真实失败清单。
2. **修一处 → 立刻跑一次冻结命令**，用真实失败清单驱动下一轮；禁止连续多轮读取后才动手。
3. **一轮合并 2–3 个相关修复**，不要一个小改动跑一次测试；也不要一次改一大片。
4. **把「读源码找因」与「跑测试」交替**，避免连续几十次 read_file 把预算耗尽后才第一次 patch。
5. 续接卡 body 必须写出**已落盘的部分**与**仅剩缺口**，并禁止重做已闭合项；否则重试 worker 会重复劳动并再次耗尽。
6. 明确要求保留预算给交接（comment + complete）：预算耗尽而无 handoff 的卡，下一轮无法区分「实现缺失」与「交接缺失」。

### 权威语义必须预先写进卡 body：worker 会为契约出处烧掉整轮预算

当卡涉及某个公式/常量/口径的**语义修正**时，worker 的默认行为是寻找"权威出处"（翻 SKILL、翻 git 历史、翻 Design、翻 kanban 历史）来验证卡内描述是否准确——即使卡里已经写了公式，它仍会反复检索同一出处（实测同一张卡被 comment 澄清两次后仍在 grep 历史）。这是 worker 的 fail-closed 纪律，不是缺陷，但编排层可以预防：

1. **派卡时在 body 顶部写一句权威声明**：「本文描述与 <SKILL/契约文件> <节名> 一致，该文件是唯一权威；禁止为确认语义再检索 git 历史/历史卡/会话记录」。把"停止检索"写成显式禁止项，而不是假设 worker 会自行判断。
2. **卡内写明所有候选变体的裁定结果**：若语义存在多种可能的实现（如费用计入权益侧还是计入保证金系数），直接写「正确方案是 X，变体 Y 与验收标准 Z 冲突，不得采用」。留白会让 worker 做 empirical validation 并耗尽预算。
3. **steer comment 的预期效果有限**：comment 到达 worker 时机取决于其当前 turn 边界；若它已进入检索循环，连续两条澄清 comment 可能都被后续 turn 覆盖。真正的止损动作是**冻结+重派一张把答案写全的窄卡**，而不是第三次 comment。
4. **同时警惕反向风险**：若卡内"答案"本身写错了（如给了与既有冻结实现冲突的字面改法），worker 的实证否决可能是对的——收口前必须独立复算数学再判定采信谁（见下条）。

### Worker 否决卡面指令时：先独立复算数学，再裁定采信谁

极小执行卡里预写的"标准答案"与既有实现/验收断言冲突时，worker 可能正确地否决卡面并按自己的方案实现（例如卡面写「权益侧减 F」，但费用已在保证金系数 MF=mmr+fee 里计过一次，权益侧再减就是双计费；worker 改为只在 MF 计费并用闭式解测试锁死）。处置顺序：

1. **不盲采任何一方**：用卡内验收断言、既有发布值、以及 worker 方案三者做独立数学复算（手工推方程 + 用旧值对拍），确认谁与冻结契约一致。
2. **复算证实 worker 正确时**：在收口 comment/result 里显式记录「worker 否决了卡面指令，独立复算证实其正确，卡面指令错误的原因」，让审计链看得到这次抗命是被验证的。
3. **复算证实卡面正确时**：回退 worker 改动并按卡面重派，同时排查自己派卡时为何写出错误答案。
4. 对比验证还可能揭示「旧发布值本就用了某个口径所以零漂移」——数值零漂移不等于语义已冻结，仍要把隐式口径用测试锁死，防止未来被错误"修复"。

## unittest定向选择：不要同时传整文件与未限定方法

执行少数指定用例时，为每个位置参数使用完整 `module.Class.method`；不要把测试文件路径与未限定的 `Class.method` 并列传给 `python -m unittest`，前者会加载整模块、后者会被当独立模块导入，既扩大执行范围又产生伪导入错误。派窄修复前把已实测的完整selector写进正文，以实际 `Ran N tests` 核对方法数；subTest失败记录另计。普通选择器错误不是安全拒绝，先保存越界执行事实、核保护hash与副作用；原授权范围未变且无新拒绝时，由主控纠正原卡后续接，不将它自动升级为新一轮用户授权或重建图。新安全拒绝仍必须停止。

## 测试失败计数口径：subTest 会放大失败数

unittest 的 `subTest` 会让一条用例产生多条失败记录，`FAILED (failures=6, errors=10)` 不等于 16 个独立失败用例（部分用例含参数化 subTest）。汇总时必须**按用例去重**并同时给出两个数（记录数 / 去重用例数），否则会误判修复范围与预算。报告中明确标注口径。

## fixture 缺字段会让下游用例全部提前失败

离线 fixture 若缺一个必需字段（如回测读回的 `initial_capital`），受影响的用例会在**基线阶段就抛错**，使后续演化、六分支、预算分支断言全部连带失败，看起来像几十个独立缺陷。修复顺序：**先让 fixture 复刻真实平台的正常响应（完整字段），再重跑**，然后才处理真正剩余的失败。反之，若直接放宽实现（例如把资金核验、来源核验从 FAIL 降为 UNKNOWN）来「让测试通过」，是用弱断言掩盖生产缺陷——正确做法是补齐 fixture 的正常态字段，同时**保留**缺失/异常态的负例断言。

## Worker 通道故障与代码故障必须分开裁定

worker 崩溃时先读 run 的 `error` 与 worker 输出，再决定恢复路径：

- **通道/模型侧故障**（TLS 握手失败、rate limit、provider 不可达、worker 进程秒退）：这是运行前提问题，不是实现失败结论。换用已实测可用的 provider/model（先做最小只读探针确认任一通道可用），并按任务粒度做 model override，**不修改 profile 的 provider/fallback 配置**。恢复时优先「复用成果 + 只补收尾」，不重建实现链。
- **读 worker 日志时，最后一级 fallback 的错误不是根因**：provider 依次 fallback 时，日志会把每一级失败都打出来（例：目标模型 `403 HTML` → 备用 `429 weekly limit` → 再备用 `402 insufficient balance`），最后一条往往只是“最后一个还剩的通道也挂了”。根因是**目标模型那一级的首个错误**；后面几级只说明备用链也已耗尽。裁定通道故障时按“目标模型首个错误 + 备用链耗尽范围”两段交付，不要把末级 `402 余额不足` 当成根因，也不要因为末级错误而认定某 provider 永久不可用。
- **通道恢复后复用原卡重派，不新建卡**：worker 因 provider/出口不可达而 crashed、rate_limited 或 retries exhausted 时，卡上没有实现缺陷证据。顺序是：① 用当次探针确认通道真的恢复（“几分钟前还能用”不是证据）；② 清除池侧陈旧状态，否则会以**第二个不同原因**再失败一次并被误归因到模型 pin；③ `hermes kanban unblock <id> --reason "…" ` 把原卡推回 ready；④ `hermes kanban dispatch --dry-run --json` 预检该卡确实可 spawn；⑤ `hermes kanban dispatch --json` 正式派发。卡上的 `model_override`、parents 与既有产物全部保留，不建替代卡；重跑前给卡 comment 写明“只补剩余缺口、禁止重做已完成项”。
- **探针必须跑在 assignee profile 上**：orchestrator 自己 profile 的一次成功调用不能证明 worker 的通道可用——两者用不同的 model/provider 默认值与凭据池。用 `hermes -p <assignee> chat --model <m> --provider <p> -q '只回复 OK'` 探针，退出码与回复都正常才算该通道此刻可用。
- **dispatch 被冷却挡住不等于卡坏**：返回 `respawn_guarded: [{reason: "rate_limit_cooldown"}]` 是看板的限流冷却守卫。冷却从最近 run 的 `ended_at` 起算（默认 300s，可用 `HERMES_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS` 覆盖），读 `kanban show --json` 的 `runs[-1].ended_at` 算出剩余秒数，等到期后 dispatch 一次即可；反复 dispatch 试探只会累积无意义事件。此期间不要改契约、不要重建卡、不要把模型不可用写成代码失败。
- **凭据池要按条目看状态**：同 provider 池内多条凭据时，一条 `usage_limit_reached` 不等于通道整体不可用——`hermes auth list <provider>` 会逐条给出 label/priority/状态。探针成功即证明仍有可用条目，此时**不改 profile 默认模型**；只有清除与实际失败原因不符的陈旧 exhausted 标记才用 `hermes auth reset <provider> [id]`，且先备份 auth 文件、不刷新认证、不改优先级。
- **代码/测试侧故障**（断言失败、导入错误、预算超限）：才是修复链的输入。

不要把通道故障写成「该工具/该 provider 不可用」的长期结论；它随时可能恢复，可复用的是「先做最小探针区分通道与代码，再选可用通道并按卡 override」这一动作。

## CLI 形状陷阱（每次先 `--help`，不要凭记忆写参数）

`hermes kanban` 的子命令参数形状与直觉不同，写错时只会报 “unrecognized arguments”，而**不会**部分执行——因此参数错误是无副作用的，但会浪费一轮：

- `create` 的标题是**位置参数**（`hermes kanban create --json "<title>" --body-file <path>`），没有 `--title`；也没有 `--board`（board 用 `--board <slug>` 只在其它子命令或全局位置出现，先 `--help` 确认）。多行正文用 `--body-file`，避免 shell 引用改写。
- `comment` 的正文是**位置参数**：`hermes kanban comment <task-id> "<text>"`，没有 `--message`；`--max-len` 控制长度。**`--body` 在 comment 上不存在**（写 `--body` 报 `unrecognized arguments: --body`；`--body-file` 只有 `create` 支持）。多行正文用 shell 变量或先写 scratch 文件再 `"$(cat file)"` 传入，避免命令行长度与引用改写。**`kanban steer` 子命令不存在**——对 running 卡的 mid-run 注入只有 `comment` 一条通道。
- `link` 语义是 `link <parent> <child>`；**子卡已在 running 时会被拒绝**（“child is already running”）。补挂依赖前先 `show` 读回子卡状态；子卡运行中且父边确实缺失时，不要反复重试——先确认该边是否已在创建时通过 `--parent` 写入。
- **依赖子卡创建后必须正向读回两项**：父门禁尚未完成时，`hermes kanban show <child_id> --json` 的 `task.status` 应为 `todo`（或有明确人工HOLD的`blocked`，不得`ready`/`running`），且返回对象顶层 `parents` 应包含真实父卡 ID；先核本机返回结构，不假定依赖数组位于 `task` 内。只确认“link 成功”不够——漏传 `parents=` 的子卡会以 `ready` 立即开跑，事后 link 会被 running 拒绝；此时按「reclaim → link → 读回整图确认仅一张卡 running/ready」回收，并审计共享树副作用。
- **共享树并发写同一路径时，用内容而非 mtime 判断是否被覆盖**：并行卡都可能写 `<instance>/reports/agent-backtest.md`。`ls -la` 的 mtime 变化不等于内容变化，必须用 `git diff --stat -- <path>` 判读：diff 为空 = 内容未变（无害），diff 非空 = 一张卡覆盖了另一张卡的证据，须归因后再定处置。不要因 mtime 变了就判定历史证据被污染。
- `archive <task-id>` 用于关闭一张**从未被派发**的卡（零改动、零 run）；它不等于删除（删除是 `archive --rm`）。
- `unblock <task-id> --reason "<text>"` 是把 blocked 卡推回 `ready` 的标准形状；`block` 的原因是位置参数并需 `--kind`；**`block` 不接受 `--reason` 标志**（报 `unrecognized arguments: --reason`），原因文本直接作为位置参数。
- `complete <task-id> --summary "<text>"` 可用于**行政性关闭**已被替代链取代的旧卡（摘要须写明“工作由哪张卡完成、为何不重跑”），但不得用它替代独立门禁的 PASS。`--force` 覆盖 live-claim guard（关闭 worker 的 run），适用于"worker 已死、结论已落在报告/证据/comment 里"的收尾；`--result` 与 `--summary` 分工：前者写结论与证据，后者写给下游的交接摘要。
- **审批门超时 ≠ 已批准**：命令明确返回等待用户超时、未执行时，停止该动作，保留原始命令并说明当前门禁未恢复；不得自行改写参数、归一化Unicode、换执行器或把概括性的业务同意当成本次工具审批。用户明确要求重发审批后，原样重发同一命令到原审批通道；审批成功后读取精确目标的状态、真实parents和正文，区分ready与已有新run的running。首次提交前可用短命令和持久正文镜像减少引用/扫描噪音，但不能在被拒后用改写命令规避审批。

## 用户纠正措辞是持久规则：全局术语问题当场全链清扫

用户纠正一个术语（如「不要再提配额」）时，动作不止是回复里改口：把旧措辞从**所有持久载体**里清掉——任务卡 comment、技能文档、后续卡面 body——并写明替代措辞。单一回复改口而不清载体，下一张卡、下一个 worker 会原样复发。此类纠正优先写入对应技能的 SKILL.md 正文（不是 memory），因为它约束的是这类任务的写法。

## 停发散的契约卡：用户裁定「精简」时主控直接窄修订

契约修订卡按原始卡面（铺陈多个备选方案、多设计决策点）派发后，用户裁定「精简、不要发散」时，正确动作是：**立即停止该卡**（complete 注明改走精简路线、无产出无副作用），**主控亲自完成窄文档修订**（RFC/SPEC/Design 各一个窄小节：行为契约定案 + 可计算验收矩阵 + 精确到文件与行段的实现范围），然后派窄实现卡与独立 Verify。不要让原卡继续按发散卡面跑完——那会浪费整轮 worker 且产出仍需返工。文档是主控的仲裁工具，直做不违反「不自己执行」边界；实现与验证永远回 worker。

Verify 因「缺外部凭据/缺会话」被 block 时：

1. 先明确该前提是否已获用户授权；**未授权不得自行登录、签发 token、读改 `.env`、或以 vault 发现扩大授权**。
2. 获授权后由主控完成**一次性**凭据准备（不落报告、不落代码），只把「注入方式 + 有效期等元信息 + 验证结论」写进续接卡 body；真实取值不进对话、报告或仓库。
3. 续接卡 body 必须写明：注入方式、禁止事项（不得写入报告/源码/配置、不得 export 到持久 shell）、以及**两种且仅两种合法终态**（全项通过 → PASS；仍有真实缺陷 → FAIL + file:line + 复现）。禁止以「环境问题」笼统收尾。
4. 被 block 的旧卡保留为审计历史，不改写其结果；续接仍在原卡上完成时，用 body 覆盖 + `unblock` 并读回确认，不要新建平行卡。

### 阻塞根因落在用户自有文件时：先给选项，而不是直接改数据

真实链路失败有时不是代码缺陷，而是**用户自有文件与生产解析器口径不一致**（如凭据文件里 `KEY = value` 带空格，而生产解析器只认 `KEY=`）。此时有两个方向：**修解析器**（宽容化，兼容两种形态）或**修数据**（把文件改成生产解析器认的形态）。二者都改变行为，必须由用户裁定：

- 主控不得默认改动用户自有凭据/配置文件的**内容**；先把两个方向的代价列清（代码改动面 + 新增回归 vs. 数据改动面 + 今后手写格式漂移风险）再问。
- 用户自己处理了文件后，**只做只读核验**：确认目标键的格式事实（如等号位置、长度、前缀形状）而不输出取值，并直接用生产解析函数做一次无网络读回（是否解析到 / 长度 / 前缀形状）。不要因为“应该已经改好”就再执行一次改写脚本——先读现状。
- 若解析器本身仍只认一种形态，把这一残留风险写进交接：用户今后手动编辑该文件时若恢复另一种形态，会重现同类阻塞。这属于**可选的防御性加固**，交由用户在后续阶段决定，不在验证卡里顺手改。
- 阻塞原因被用户消除后，原卡 `unblock` 重跑即可，不需要新建平行卡或重新分解；但卡上要 comment 写明「阻塞根因如何消除 + 谁做的 + 剩余风险」，保留审计链。

## 用户中途纠正目标布局：迁移收口，而不是重做

用户在对账途中改变目标路径或目录形态（例如把策略实例从模块直属层改到模块内 `strategies/` 子目录）时，按以下顺序收口：

1. **先停正在跑的 worker**：核对精确 argv 确认 PID 属于本卡，再 TERM 该 PID 并用 `ps` 确认已退出；不按 profile 名或宽泛模式杀进程，也不重启业务服务。停手后才改指令，避免 worker 按已作废目标继续搬文件。
2. **不重建迁移链**：在原 Implement／Verify 卡上覆盖 body、读回确认，把"最终位置 + 已落盘的部分 + 仅剩缺口"写清。平行建卡会让下游 parent 断链，并重复已闭合的工作。
3. **先核对受保护产物再放行**：纠正前为每个文件留 SHA256 基线；纠正后先确认源码、配置、已生成报告等受保护文件 hash 未变、且同一实例只存在于一个位置，再 unblock worker。若受保护文件已变或出现多份并存，STOP 交主控裁定，不合并覆盖。
4. **目标已存在不等于冲突**：worker 可能在收到纠正时已把文件搬到正确位置。此时应接管该候选、只修剩余引用与测试，而不是按"源缺失/目标已存在"报冲突并重搬。
5. **三层文档用取代式新版本**：旧裁定被新裁定替代时，新增版本行并在正文写明"本节取代上一版路径方案"，旧版本行保留为历史；同一契约不允许同时有两个生效版本。同步范围只限路径、文件清单与守卫，不动业务语义。
6. **目录迁移不等于重新执行**：已生成的报告、复现命令原文与结论逐字保留，不因移动重跑、改写或覆盖；只有新生成的报告才使用新路径。
7. **路径守卫随新根收紧**：CLI 只接受实例根的**直接子目录**，拒绝更深嵌套、根外目录与 symlink 逃逸；测试要把被否位置写成负例，并保持原用例数不变。
8. 迁移类的纯路径重组按 Light Flow（Developer Implement → 独立 Tester Verify → Closeout）执行，不因文件数量启动 RFC/SPEC/Design；Verify 独立复跑冻结回归并核对受保护 hash。

## 标准替代任务图

先确定原流程要求，再选择最小替代链。Quick/Light Flow 中根因明确、未改变公开契约且位于既有 allowlist 的修复，采用 `Fix-N → 独立 Verify-N → Closeout 自审`；下图适用于原流程已要求独立 Review 的情况。不要把修复图当作自动升级 Full Flow 的依据。

```text
已冻结旧 Verify (historical evidence)
              │
              └── P0 Fix-N (developer)
                       └── Verify-N (tester)
                                └── Review-N (reviewer)
                                         └── Closeout (orchestrator)
```

创建卡片时：
- Fix-N 父任务为最后一个已完成、且包含待修契约的实现/修复卡。
- Verify-N 父任务为 Fix-N；Review-N 父任务为 Verify-N。
- 全部使用共享项目目录、严格 allowlist、明确禁止生产副作用。
- 新 Verify body 必须写出旧失败的最小可复现数据矩阵和严格期望值。
- 每张新卡创建后立即 `hermes kanban notify-subscribe <task-id> --platform <平台> --chat-id <会话ID> --delivery-mode wake` 绑定当前会话来源；完成/阻塞回传事件驱动交接，不轮询。

## 文档门禁失败时的替代链

当 Review 发现 RFC / SPEC / Design 的主文档仍与 amendment 或实现契约冲突时，**不得让已排队或已启动的 Implement 继续编码**。按以下顺序处理：

1. 用源文件与精确行号复核冲突，而不是只采信 worker 摘要；扫描主文档中所有重复表/章节，不能只修首次发现的一处。
2. 将正在运行的 Implement 置为 `dependency` block，理由明确为“文档门禁失败，禁止对矛盾契约编码”；同时核对其尚未留下越界代码 diff。
3. 创建 Principal 文档修正卡：RFC、SPEC、Design 各自独立或逐层修正既有三件套。验收必须要求主正文与 amendment 零冲突、关键词扫描覆盖旧表述、给出最终 code allowlist。
4. 已被阻断的 Implement **不能解除后复用**。创建 replacement Implement → fresh Verify → fresh Review；Verify 先确认前置文档存在且旧冲突文本消失，再测代码。
5. **不要把 `blocked`、`timed_out` 或 `gave_up` 误当作旧卡的终态。** Kanban 在 parent link 被补齐、parent 随后完成或 dispatcher 重新计算 ready 后，旧卡可能再次 `promote/claim`，甚至在先前显示 retries exhausted 后产生新的 completed run。每次收到旧卡状态通知都必须重新 `kanban_show`：核对最新 run 的开始时间是否晚于 document gate，并重查实际 diff 和测试证据。若旧卡确实在门禁通过后完成，仍不得跳过 replacement 链；由 replacement Implement 仅做 **path-filtered reconciliation**，把它作为候选产物重新归属，不得重复编码或直接放行。
6. replacement Implement 的正文必须显式禁止 `git reset`、`git stash`、`git clean`。共享 `dir` 中历史 worker 的暂存或清理操作属于流程违规；替代 Verify 只能用当前工作树、路径过滤 diff 和可重跑测试重建证据。
7. Closeout 只能依赖 replacement Final Review。若旧 Closeout 因既有 parent 已 done 自动启动，立即 block；创建 replacement Closeout 或追加真实 Final Review parent。不要以旧 blocked Review 作为新链 parent，避免依赖死锁。

文档契约与代码契约不一致时，既有测试通过也不能证明实现正确；实现前 document gate 优先于吞吐量。

## 共享工作树的基线丢失与残留 worker 遏制

当此前已独立核验、但**尚未提交**的 RFC/SPEC/Design 从共享 `dir` 工作树消失或回退到 HEAD，而旧 Implement 仍可被 dispatcher 重新 claim 时，必须将其视为 document gate 的重大失效，而不是普通 timeout 或可直接恢复的候选产物：

1. 用当前磁盘版本号、章节锚点、`git status --short`、path-filtered diff 与 mtime 复核；上一次 PASS 仅是历史审计证据，不能替代当前文件事实。不得凭 worker summary 手工宣称文档仍存在。
2. 立即 block 所有依赖失效契约的旧 Implement，并追加 comment 记录丢失的文档版本/章节、当前 dirty 路径与禁止继续编码的原因。注意：`kanban_block` 后 parent recompute 仍可能自动 promote 旧卡，必须再次 `kanban_show`。
3. 对每个仍在运行的 worker 核对精确 PID/命令行；若它继续写入共享树，先 TERM、仍存活才 KILL **仅该 task 的精确 PID**。不得按 profile 名或宽泛模式杀进程。
4. 保留残余 dirty 文件，不得 reset/stash/clean；它们只是未验收候选，不能当作丢失文档的替代基线。
5. 重新建立 **RFC → SPEC → Design** 串行恢复链；每层完成后以当前磁盘实物独立验收。不得直接复用失效 Design 的 in-memory handoff 或重新启动旧 Implement。
6. 新 Design 通过后，如候选代码存在 allowlist 归属歧义，先 Principal-only scope reconciliation，再新建 replacement Implement → fresh Verify → fresh Review。所有生产 Gate 授权必须重新以恢复后的当前基线为准。

详细取证与任务图见 `references/shared-dir-baseline-loss-and-worker-stop.md`。当基线恢复同时伴随 P0 阈值/状态修正、迟到 timeout 通知或旧 worker 在 block 前已被 claim 的竞态时，追加执行 `references/document-gate-recovery-race.md`：以当前 card/runs/PID/磁盘为准，阻止旧契约继续传播，并仅杀精确 task PID。

### 文档 Gate 修正的级联冻结规则

当 RFC/SPEC/Design 的**活跃公开契约**（阈值、状态词汇、Gate 预算、授权边界）出现冲突时，不能让下游卡继续“先写后补”。

1. 先冻结所有可能固化旧契约的下游 SPEC / Design / Implement；`kanban_block` 本身不是进程已停的证据，必须复查最新 run 与精确 PID。
2. 创建 Principal-only P0 文档卡，严格单文件 allowlist；要求全文扫描活跃 Gate 正文，区分允许保留的 changelog 历史叙述和不得保留的可执行旧表述。
3. 以一个唯一、可定位的输入重锚（例如配置常量或已冻结的 Design 判定），明确正反边界，例如“匹配率 `<70%` fail-stop，`≥70%` 才可继续”。
4. P0 完成后，不解除/复用旧下游卡；用其当前磁盘候选作为输入建立新的 replacement 文档卡。新卡必须引用已修正的权威版本，而非旧 handoff。
5. 每一条旧卡的 `blocked` / `timed_out` 通知都可能是迟到状态事件；重新 `kanban_show`、检查最新 event/run、精确 PID 和 diff，绝不据通知文字判断重试或完成。

## 生产 Gate 的“可完成性”预检（防止可预测的部分写入）

对逐日/逐批生产回填，**canary PASS 不等于全量可安全执行**。在全量 `--apply` 前，Orchestrator 必须用零副作用 dry-run 与实际 canary 报告做一次可计算预检：

1. 从真实 Gate-1 report / dry-run 读取计划日期数、首日排除规则和实际查询范围；不得只依据 CLI 名称或文档宣称推断。
2. 用 canary 的真实 `query_budget`（或受控最小复现）计算全量查询行数下界：`planned_days × 每日最小命中行数`；将该结果与共享 reader 的累计上限、单日上限和每次查询上限分别比较。
3. 如果现有全局预算会在全量完成前确定触发，**禁止执行全量 apply**，即使该阈值看似“安全保护”。必须把它认定为生产工作流契约缺陷，而非通过提高阈值绕过。
4. 先创建 Principal 文档校正卡，明确预算作用域（job / chunk / day）、数值上限、停止码、扫描保护不变量、日级原子与幂等恢复边界、以及 per-day 与总量审计字段；随后重新走 Design Gate → Implement → Verify → Review。
5. 若 canary 已在失败后留下目标日期的行，重试只能使用已验证的唯一键幂等 upsert；禁止为“清场”擅自删除。后续全量仍须等待实际 canary retry PASS。
6. Gate-4 或任何读路径激活始终以**实际全量 Gate-3 成功**为前置；文档修订、dry-run 和 canary 均不能替代该证据。

## Timeout 中已有合格文档产物时

Principal / Review 卡因 iteration budget 耗尽而 `timed_out`，但已在共享树留下限定范围文档并写出完整 handoff 时：先以 `kanban_show`、路径过滤 diff、`git diff --check` 和三层一致性审计判断产物，不以状态猜测。若证据充分，向原卡追加“重试仅复核并完成、禁止重复编辑/重复建卡”的 comment；其 parent-gated child 保持冻结，直到原卡正式完成。不要替其他 worker 直接完成其卡，也不要把 timeout 当作自动放行。

**大文档类（master RFC/SPEC 1500+ 行）Principal 修订卡反复 60/60 超时是常态**：内容写完、只剩收口时预算耗尽，且重试 worker 若按 body 重新执行会重复编辑造成污染。经验证的 fast-path：

1. **超时核验先查版本头 + mtime 窗口 + diff 范围**：`stat -c '%y %n'` 确认双文件 mtime 一致且落在任务窗口，`grep '版本号'` 确认目标版本已落，`git diff --check` exit 0，确认 diff 仅限 allowlist 文件。
2. **抽查 Verify 曾指认的语义修复点**（不是只看版本号）：直接 `sed -n` Verify 报告列出的行号区间，确认被标记段落确实改写（如 SPEC §R2 章节真实存在、PR-2 行带 superseded/out-of-scope、裁决表冲突行已改）。版本号存在不等于正文修复完整。
3. **重试 comment 必须给出完整再核验 checklist**（版本、章节锚点、上一轮 FAIL 的完整行号清单、diff --check、allowlist 范围、零 I/O），并明确「若全部满足直接 complete；若有遗漏仅对 allowlist 做最小修复；禁止重新编辑已满足项」。本模式两次复现均让重试 run 在 5-10 分钟内只读核验收口，未产生重复编辑。

## Timeout 留下文档但没有 handoff：先作 NO-GO 审计，不能直接续跑

当 Principal 卡 timeout 且共享树中留下 RFC/SPEC/Design 修改、但没有 `kanban_complete` handoff 或授权包时，按下面流程处理；这不同于“已有完整 handoff 的合格文档产物”。

1. **冻结原卡自动 retry**：用 `kanban_block(kind="transient")` 留存 iteration-budget / timeout 事实；在原卡 comment 写明“禁止 unchanged replay”。不要把 `timed_out`、随后出现的 `blocked` 通知或文件存在当作审批结论。
2. **先做只读三层审计**：读取 metadata、主正文中的可执行条款、版本互引与 changelog；用 path-filtered diff、`git diff --check` 及关键词扫描区分历史 superseded 数字和仍在当前时态承担行为语义的旧表述。版本号更新、changelog 更新和依赖指针更新必须同时成立。
3. **以实物 report 反证文档假设**：解析既有 Gate 报告，只输出计数/布尔摘要；重点验证 coverage、canary、全量范围、停止条件及实际 run 模式。不可从“canary PASS”推导“全量 backfill PASS”。
4. **生产 Gate 前置证据不因文档修订而满足**：若 Gate-4/read binding 要求 Gate-3 全量成功，则文档对齐、dry-run 或单日 canary 一律只得出 `NO-GO`；不得提前生成 activation approval，也不得执行 binding、live-read、refresh 或 backfill。
5. **建立短小替代 Principal-only closure 卡**：严格限定到已漂移的 RFC/SPEC/Design allowlist，要求 closure ledger、Gate 的 NO-GO 结论与可重跑静态/JSON 交叉检查；禁止改报告、代码、测试或任何生产资源。该卡完成后必须接 fresh Verify → fresh Review，而不是恢复原 timeout 卡。
6. **NO-GO Closeout 与 production activation 严格分离**：closure 链的 Closeout 只能声明「文档/证据一致性已关闭，production gate 仍 NO-GO」，并列出未发生的 binding、backfill、refresh、DDL/DML、服务或调度动作。它不得成为后续生产卡的 parent authorization，也不得将 `APPROVE` 转述为 activation approval。真实路径必须由 Pascal 对一张新的、独立的生产卡逐项授权：先执行全量前置 Gate，再进行独立只读 Verify，最后才评估读绑定/activation。

典型信号：文档将 Gate-1 `coverage_by_date` 的所有键误当作全量可用范围，但 100% exact-match 只允许 `ratio==1.0` 的日期；此时必须将主正文的日期数、累计预算、首日排除规则与 report 事实同步，而不是仅在 changelog 加一行校正。

## 文档卡「声明先行」缺陷：changelog/元数据声明与正文不一致

文档修订类卡的常见失败不是改错，而是**只改了 changelog / 元数据行、正文没有同步**。典型表现：changelog 声称「新增 §X 章节」「统一标记 superseded / out-of-scope」，§0 术语也引用「见 §X」，但正文实际缺失该章节或残留大量未标记的可执行旧契约。Verify 若只查版本号与 changelog 存在就会漏过，必须把「声明 vs 正文」作为独立核验项：

1. **章节存在性用全文 grep 证实**：`grep '^## R2'` 等直接命中目标章节；changelog 声称新增的章节与正文引用点必须可解析，否则是悬空引用 → FAIL。
2. **逐行核验 changelog 声称的每个行号**：changelog 声称「§7 A-018、§10 G-A-2、§14.x、§P0.x、§P1.x 已统一标记」时，对每个声称位置逐一确认正文有 (R2)/superseded/out-of-scope 标记；「声称已标但正文未标」是独立 FAIL 证据，即使 RFC 对应章节已标（两文档不同步同样 FAIL）。
3. **「禁止性语义冲突」是 P0**：正文残留的旧可执行表述若与最新裁定直接冲突（如「仅允许后续单变量网络诊断后重试 live-read」 vs 新裁定「禁止 live-retry」），必须改标 out-of-scope，不能仅加旁注或保留为历史定义。
4. **Fix 卡把 Verify 的 FAIL 证据原样内嵌为检查表**：将 Verify 报告中的行号清单（如 19 处 SPEC + 8 处 RFC）逐条写进 Fix body 的修复清单，避免 Fix worker 重新扫描范围或漏改；每个条目给出「旧文本 → 新文本」期望。修复原则是保留历史事实（删除线 + superseded 标注），不删除章节。
5. **修复后新一轮 Verify 必须逐行回核 Fix 清单**，不能只抽查；同时补扫全文残留（`PR-2`/`name_em` 命中中，可执行表述均应带标记或被章节级 R2 注覆盖，纯历史 changelog/冻结证据行可归类不算残留）。

## 共享 helper 的能力域语义隔离

当 Verify 发现新 capability 的阈值/状态契约与共享 helper 的遗留三态或 exit-code 语义冲突时，先全仓扫描定义、调用方、状态消费者与测试。不要为了一个 capability 全局删除仍被 sibling path 使用的状态；若契约只限该 capability，优先采用向后兼容的显式 capability/scope 参数，并同时锁定新 capability 边界与默认 legacy 行为。完整判定与任务图见 `references/capability-scoped-shared-helper-repair.md`。

## 新链的创建纪律：CLI 机制要能抗中断

重建或新建流水线时，Kanban CLI 的调用方式本身就会影响可审计性：

- **先保存任务正文镜像，再创建或编辑**：创建用 `hermes kanban create <title> --body-file <镜像路径>`，不要把多行正文直接拼进命令。编辑既有卡先查 `hermes kanban edit --help`，不要猜测存在 `update` 子命令；本机 `edit` 未提供 `--body-file` 时，在 Bash 用 `hermes kanban edit <id> --body "$(<镜像路径)"` 原样传入已保存正文，再按正文镜像校验步骤读回比对。已获批准的命令形状才能执行；不能用此方式改写被安全策略拒绝的命令。
- **`--json` 输出重定向到任务目录再解析**，不要用 `hermes kanban create ... --json | python3 -c ...`。每张卡保留独立的创建响应和精确目标读回文件，中断后先从这些响应恢复真实ID、核对看板，再决定是否创建；不要删掉创建回执后靠重复建卡恢复进度。只向上下文输出本轮核验所需字段，完整正文留在任务镜像和原始响应中。
- **逐张创建、逐张拿到真实 id**。把六张 create 合并进一次 shell 调用时，中途一张被拒就无法判断哪些 id 已存在，重跑会产生重复卡。
- **先按阶段语义列 expected edges，再用 `hermes kanban show <id> --json` 校验实际图**。不能只证明 parents 等于创建时传入的值，因为传入值本身也可能错；Verify 必须以实际 Implement 为前置，Closeout 必须等待最终 Review，不能把依赖 Design 或仅等待 Implement/Verify 当作等价替代。逐张核对真实 id、必要边、无反向/自依赖，以及未满足前置的卡仍为 `todo`；合法的传递依赖可保留，不为图形整洁删边。发现漏边时先用受支持的 `link <parent> <child>` 补齐，再读回精确目标，未核验前不得声称“串联正确”。
- **只读回读命令被审批拒绝/超时时，不得改写命令重试**。记录“已确认什么、未确认什么”并在面向用户的报告里如实分开陈述；不要用另一条等价路径绕过。
- **`--parent` 是硬派发门，不是上下文引用**：create 挂 parent（尤其父卡 blocked/未 done）会让 dispatcher 拒绝 spawn 子卡（pass 显示 `Spawned: 0`、子卡停留 todo），`promote` 也会以 "unsatisfied parent dependencies" 拒绝并给出唯一出路（complete the parents or drop the link）。只想表达"继承上下文/背景来源"时把背景写进 body，不挂 parent；确需依赖时父卡必须真实可完成。父卡核验完成后不必手动派发，下一轮 dispatch 自动 spawn。
- **反复 `Spawned: 0` 且无报错时，逐个 parent 查状态**：dispatcher 对 parent 未 done 的卡静默跳过（不报错、不提示根因），诊断只能靠逐张 `show <parent-id>` 看 status。任何一个 blocked/未收口的父卡（如留证冻结卡）都会永久锁住整条下游链；解法只有两个：complete 冻结父卡（审计结论进 `--result`），或 `unlink <frozen-parent> <child>` 把子卡从死链摘除（血缘改由 body/comment 记录）。此外后继卡可同时是两张卡的 child（如既挂 fee 卡又挂 Verify），link/unlink 后必须读回 parents 数组确认最终边集。
- **link/unlink 边会累积，读回才算数**：unlink 参数顺序是 `<parent> <child>`；每条边变更后 `show <child> --json` 读回 parents 确认。串行修复链（Fix→Fix→Verify）只把 Verify 挂在**最后一个** Fix 上；把每个中间 Fix 都挂到 Verify 会造成门禁冗余与提前触发。
- **冻结慢 worker 的行政收口序列**：`complete` 被拒 "a live worker is running it" 时不要 `--force`，先 `reclaim <id>` 释放 claim（终止该 run 并退回可 complete 状态），再 `complete --result <已核验产物清单与遗留去向>`。

## 主控直做收尾的边界：可核验的机械尾项可代 worker 收口

Worker 因 iteration budget 耗尽而未 `kanban_complete` 时，卡会停在 blocked/gave_up，下游 Verify 卡拿不到 parent 释放。此时主控可以代为收口，但必须先取得**实物证据**再动看板：

1. 逐项核验该卡 body 列出的验收项：文件存在性、受保护文件 SHA256 与基线一致、路径过滤 diff、冻结回归命令真实退出码、相对链接可达、未遗留被否位置（副本/shim/symlink）。
2. 在卡上写一条 comment 说明「哪些收尾项是主控补做的、命令与计数是什么」，再调 `kanban_complete`，summary 里同时写清「本卡 PASS 只覆盖 X，不代表真实业务/UI/生产通过」。
3. 独立 Verify 与 Review 不可省——主控自己做的校准只是放行依据，不是验收；下游 Verify 卡仍须独立重跑。
4. 只有**机械、零语义**的尾项（链接检查、diff --check、hash 比对、状态收口）才可主控直做；任何断言、契约、生产逻辑改动都必须回到 developer 卡。

**必须披露执行主体。** 主控代做收尾时，summary/comment 要写明「最终判定由主控独立执行并留证，非该 worker 自报」，并附真实命令与计数。后来者会把 worker 自检与主控校准混为一谈，把未执行的 worker 交接当成已完成的独立验证。

**gave_up 卡 unblock 会触发 dispatcher 重新 claim。** 之前 gave_up 的卡一旦 unblock，dispatcher 可能立刻拉起新 run，卡随即回到 running，此时 `kanban complete` 会被拒（"a live worker is running it"）。正确顺序：先 `show <id> --json` 确认新 run 是不是「同宽任务的 unchanged replay」；是则先给 comment 约束它只做收尾/只读核验，再等它自然收口；不是则先 TERM 精确 PID。不要用 `--force` 绕过 complete 拒绝，也不要在主控收尾的同时放任一个新 worker 重写同一片共享树。

## Quota-wall requeue ≠ 工作未完成：先验实物，再 comment 放行

Provider 配额墙杀 worker 时，卡会留下一个与 iteration-budget 耗尽**不同**的指纹：

```
last_failure_error: pid 74936 exited rate-limited (quota wall) — requeued without counting a failure
runs: [(None, 'rate_limited'), (None, 'rate_limited'), (None, 'running')]
```

dispatcher 会重排队，所以卡状态又回到 `ready`/`running`，但 worker 可能**已经产出完整交付物**，只是死在调 `kanban_complete` 之前。2026-11-03 实例：E2 契约决策卡（principal）已把 RFC/SPEC/Design 三份 V1.8 修订全部写完并被下游实现卡实际采用，却因配额墙反复重排队，看起来像「没做完」。

处理顺序（与 timeout 段落同源，但指纹不同，不可混用）：

1. **先读 `last_failure_error` 与 `runs`**：`rate_limited` / `quota wall` 表示「进程被杀」，不是「worker 中途放弃」。
2. **直接验共享树的实物**，不要等重跑：文档卡读版本头 + 新增章节 + 目标小节；代码卡跑 `git status --short` + 路径过滤 diff。产出完整即为交付完成。
3. **不要建替代卡，也不要等重排队跑完**——重跑的 worker 会用同样代价重做一遍已经完成的工作。正确动作是：在卡上发一条 durable `kanban_comment`，写明「已核验哪些文件/版本/章节、结论是什么」，然后推进下游链。
4. **不得手改卡的 `result` 字段**（伪造审计历史）；comment 才是修正通道。
5. **配额墙不豁免门禁**：实物完整 ≠ PASS，下游仍须独立 Verify/Review 取得独立证据。

反面教训：把配额墙重排队当作「未完成」→ 要么空等冗余重跑、要么建重复卡，两者都白烧预算；把配额墙当作「已通过」而不验树 → 可能接受真正残缺的产出。**先验树，再 comment，再推进。**

## Verify 卡预算耗尽但已落盘 PASS 结论：卡状态是噪音，证据是事实

独立 Verify 卡因 iteration budget 耗尽停在 `blocked`，但它**已经**把结论写进报告、evidence 目录和卡上 comment。此时卡的状态不是结论，是**收尾动作没跑完**的残留。

处置（不要重跑 Verify，也不要当作未做）：

1. 读 `task.status`、`last_failure_error`、`runs`（确认是 `timed_out`/`gave_up` 而非真实 FAIL），再读 `latest_summary` 与 comments——**结论通常在 comments/latest_summary，不在 `task.result`**。
2. **验实物而非信 summary**：报告文件含结论节、evidence 有原始命令输出、冻结命令的**原生 exit code** 与计数在证据里。
3. **区分「一次跑」与「多轮跑」**：同一卡跑过多次时，证据**按轮次分前缀**（`verify-g-*` / `verify-g2-*`），报告保留 `report.prior-run.md` 对照版——审计能看出「两轮独立重跑结论一致」。
4. **补写缺失交接文件时只做产物索引，不改写结论**：worker 只差交接文件（`*-handoff.md`）时，主控补写该文件，内容限于「产物清单 + 真实命令/exit/计数 + 未运行边界 + 下游入口」；**不得**改写 worker 的判定方向、结论措辞或任何计数数字，也不得在补写文件里追加 worker 未做的验证。补写文件必须写明「真实执行者是 worker，行政登记者是主控」。
5. **闭合前复跑候选身份，确认无漂移**：用 worker 报告里引用的同一份候选/保护 SHA 清单再跑一次 `sha256sum --check`（cwd 与 worker 一致），exit 0 才证明验收期间输入未变；漂移则该报告不得行政收口。这条检查成本极低，却能挡住「worker 跑完测试后共享树又被改动」这一最常见的伪 PASS 路径。
6. `kanban complete --force` 闭合（覆盖 live-claim guard）。`--result` 写结论摘要（矩阵计数、命令、exit code、**未闭合项**），`--summary` 写给下游的交接摘要。
7. **闭合 ≠ 免除下游**：契约里声明「实物完整 ≠ PASS」的部分（未做的真实网络验证、未闭合的 Gate）必须原样进 `--result`。
8. **行政闭合后下游卡可能停在 `ready` 且没有 run**：父卡变 done 只解除依赖门禁，dispatcher 未必立即 spawn。显式 `hermes kanban dispatch --json` 一次并读回下游卡最新 run 的 id/`worker_pid`/status，才称「下游已启动」；只看到 `ready` 只能说「已排队」。

## 验收报告自身的事实错误：追加勘误，不覆盖原报告

独立 Verify / Review 报告如果**自身**写错了事实（测试归属模块、格式检查范围、warning 归类、报告引用路径），修复方式不是改写原报告——原报告是下游按路径取证的引用对象，覆盖它会断掉证据链。正确做法：

1. **新增追加式勘误文件**（如 `verify-correction-r1.md`），逐条写「原表述 → 更正后表述 → 回源证据路径」。被勘误的原报告、`*-handoff.md`、原始日志**保持原字节**，并用 SHA 清单证明未变。
2. **回源原始日志逐项核对**，不凭印象改：模块归属回源码文件与行号；格式范围回全量格式日志里的 `Diff in` 计数与具体文件行；warning 数量按 target 分列（lib / lib test / 依赖 future-incompat 不混算）。勘误每一条都要能被下一轮独立验收用一条命令复现。
3. **勘误不改结论方向**：事实更正只修事实陈述，不得借勘误放宽判定标准或把 FAIL 改写成 PASS；原结论（如 REVISE）与原 open finding 数量原样保留。
4. **勘误必须成为下一轮门禁的输入入口**：修复链的 Verify / Review 正文显式指向勘误文件，并要求「按勘误后的口径重判相关条目」，否则下游仍按旧报告口径读。
5. **口径类勘误要落进卡面而不只留在报告**：错误表述（例如「全部格式差异都在未改动文件」）会误导后续 reviewer 的范围判断，修正后要在三文档/卡面同步同一口径。

## 契约缺口导致的二次修订链：不要把实现卡越界成“顺手改代码”

实现卡自检实测出**契约层面的缺口**时（例：解析层已放行某取值，消费链上还有第二道同谓词拒绝），
正确链条是：契约修订 → 实现 → **留证上报 + 契约决策卡（只出文档）** → 窄增量实现 → 一次合验。

- **实现卡不得顺手修缺口**：缺口属冻结契约范围，必须回到契约层决策，否则实现绕过了自己要遵守的文档。正确动作是按 Design 停止条件 STOP 留证、把缺口定位到文件+行号+复现、并在交接里点名下一张卡做什么。
- **契约决策卡只出文档**：principal 改 RFC/SPEC/Design，并写出下一张实现卡的**精确 allowlist**（文件 + 行 + 具体改法，精确到字符级），不要只写“放宽校验”。
- **按已批准的封闭缺陷清单组织最小修复包，不按 finding 数量逐项建链**：一次列全 file:line、期望/实际、精确源码与既有测试路径，以及已闭合不重做的条目；同一候选上的相关缺陷优先集中修复，再做一次独立合验及原流程要求的审查。只有真实前置依赖、冲突写路径或单卡执行预算不能承载时才拆实现卡，避免每个小问题重复跑完整门禁。
- **合验绑定最终候选，不混用中间通过记录**：存在多个必要实现卡时，让一次独立 Verify 覆盖其完整受影响矩阵与原反例；用最终文件身份确认所有修复同时存在，不能把各卡先后各自通过当作联合通过。
- **契约内部矛盾当场修**：三文档版本记录表与正文冻结口径不一致时（如正文“负零按数值相等归入零成交” vs 版本记录“负零仍拒绝”），这是契约矛盾，Verify 无权放行，编排层先修再放行下游。

## 子模块 + 主仓的提交纪律：一次会话内完成，gitlink 同步

项目含 git submodule（如平台上游仓）时，变更往往跨两层：**子仓代码** + **主仓文档/gitlink**。提交纪律：

1. **先提交并推送子仓**（子仓分支固定 `main`）；子仓 push 成功后再动主仓。
2. **主仓必须同步 gitlink**：`git add <submodule path>` 把 gitlink 指到子仓新 HEAD，再连同文档/脚本 commit。提交后核对 **主仓 gitlink SHA == 子仓 HEAD**，不一致就是漏提交。
3. **子仓工作树必须干净**：子仓有未提交改动时，主仓 gitlink 指向旧 commit，代码实际不在主仓记录里。
4. **不 checkout 别人的子模块分支或 `<sha>` 检出**——始终本地 `main`；官方上游分支名不必与本地一致。
5. **提交前排查“看似本次改动、实为历史遗留”的文件**：主仓工作树可能混有前序卡留下的文档/配置改动。逐个 `git diff` 看内容，判断是本次范围还是遗留；遗留改动要么单独 commit 并在 message 说明来源，要么明确排除，**不要静默混入本次 commit**（会让责任边界无法审计）。典型信号：本次只改 2 个文件但 `git status` 显示 17 个 —— 先逐个核对 diff 再分组提交。
6. **推送后核验**：主仓 `git status --short` 空、子仓 `git status --short` 空、gitlink SHA == 子仓 HEAD，三项全过才算完成。

## 修复“某取值被拒/校验过严”类缺陷：全链路 grep 同一谓词

通用形态：**同一业务谓词在多层代码里各有一份拒绝实现**。只修抛错那一处，消费链会在下一层再拒一次，生产症状原样复现。

排查纪律：把谓词（`volume > 0` / `<= 0` / `is None`）**全仓 grep**，列出解析层、转换层、消费/聚合层、撮合层的**全部**拒绝点与行号；逐点判定该取值是**合法状态**还是**无效输入**；合法状态必须表达为“不动作”，不能表达为“整窗失败”；只有合法状态才进契约修订；改完后逐点复核合法值走通、非法值仍被拒且**错误标识与消息不变**。

## 分页拉取会重置逐项状态：先 mock 复现，再修复，再同款自证

逐项证据/审计账本（每根 bar、每条记录一份 trace）叠加分页拉取时，检查状态在**每一页进入时**是累积还是重置——`state.bars = page_evidence` 这类整本重写会让消费端逐项核验在除最后一页外的所有页上失败，且报错落在证据缺失而非数据本身，极易误诊为数据问题。处理顺序：

1. **先 mock 最小复现**：两页假数据串行解析，断言页 1 的条目在页 2 解析后仍可查。两页足够证明机理，不需要真实交易所数据。
2. **修复语义三件套**：同 identity 逐页 merge（新页同 key 覆盖旧条目）+ 容量上界淘汰最旧（防无界增长）+ identity 变化/线程更替仍整体重置（保住不跨窗口借用语义）。只改状态重置/赋值段，不动消费端。
3. **移交物必须含同款 mock 自证**：修复前用来复现失败的那个实验，修复后重跑并展示原失败断言转为通过。修复针对的就是这个复现，交接里没有它就等于没证明。
4. **验收矩阵单列跨页条目**：三批全可查、换身份重置、容量淘汰、同 key 覆盖各一条，与单页语义条目分开。

## 独立 Verify 的两条硬要求：反向回退实验 + 独立探针

“全部测试通过”**不足以**判定实现正确——恒真断言同样会全绿。Verify body 应强制：

1. **反向回退实验**：把候选实现回退（只读副本，不污染共享树），重跑**新增用例**，新增用例必须失败。失败数对得上 → 新用例确实锁定本次变更。
2. **独立探针**：用**不复用测试文件工厂函数**的最小脚本直接打生产路径；复用测试工厂会让探针继承被测代码的假设。

另：**测试通过 ≠ 契约全部满足**。Verify 必须按契约**逐条验收矩阵**取证（每条给期望/实际/证据位置），不得以“测试绿了”代替逐条核对；实现方自报 PASS 不作为证据，计数由 Verify 自己实跑取得。

**完整回归由独立 Verify 绑定最终候选执行；Review 不机械重复同一套。** Reviewer 先核当前源码/测试/契约逐路径 hash、Verify 原始日志 hash、真实命令/原生退出码与覆盖矩阵，再独立执行原失败反例和少量新边界控制。候选及相关执行前提相同、完整证据可追溯时，明确记录复用哪一轮全量，不复述为本人重跑。发现相关字节/前提变化、证据缺失或真实新反例时，补最小受影响验证；新反例成立就撤销整体放行，不能以复用的全绿覆盖它。只有确需刷新完整矩阵时才再跑全套，避免把独立审查等同重复计算。

（零成交 bar 这类“合法取值被拒”的取证方法、语义边界与验收矩阵写法见 `references/zero-trade-bar-and-validation-rejection.md`。）

## 真实接入验收的失败归因

客户端失败不等于平台失败。认证后跑真实平台闭环（回测/进化/数据）时，先按 `references/real-platform-acceptance-triage.md` 做归因，再决定重跑、修复还是环境处置。

**环境层故障不进入修复链。** 当失败原因是外部依赖不可达（代理隧道断、目标 API 超时、DNS 异常、凭据文件格式与解析器口径不一致），先完成分层归因再决定动作：修代码会把手工改数据当成“代码没 bug”、把外部抖动固化成永久断言；而用户自己就能消除环境侧根因时，重建实现链纯属浪费。

处理顺序：

1. **先分离环境层与代码层**：用只读探针证明外部依赖当前状态（直连 vs 代理对照、DNS 答案、provider 可达性），并读回真实失败日志（认证失败发生在请求发出前 = 客户端侧；上游返回业务错误 = 平台侧）。
2. **环境层阻塞时，卡保持 blocked 并写清“阻塞条件 + 判定命令”**，让用户看到可执行的消除动作（重启代理、改一处配置格式），而不是拿到一个“修代码”的建议。
3. **用户选定方案后**才动代码或数据：若选择改实现，派出窄 Fix 卡并补对应离线回归；若选择改数据，由用户自行处理，主控只做**只读核验**（格式事实 + 生产解析函数读回），不得代改用户自有凭据/配置文件内容。
4. **未被选中的方向**（例如已派但未采用的实现修复卡）应当 **archive** 掉并写明“用户选择了另一方案”，不要留在板上等待被派发。
5. 环境恢复后**原卡 unblock 重跑**，不新建平行卡、不重复已通过的离线阶段。

**不要在报告里把“外部服务当前不可用”写成“该能力不可用”。** 前者是当下状态且随时可能恢复，后者是能力结论；后续会话会把前者误读成永久约束。

配套的凭据纪律：向 worker 交付认证态时，JWT 只允许进程内注入，不得写明文文件到 scratch/临时目录（`0600` 权限不等于未持久化），不得进 argv 或命令行 header；被安全扫描拒绝的诊断命令不得换执行器（改写脚本、改用别的 interpreter）继续等价操作——应停下并由主控裁定合规替代路径。

## 修复卡要求

Fix-N body 必须列出：
1. 原失败的文件/行为证据；
2. 修复边界与禁止触碰的文件；
3. 不能通过放宽断言、宽泛匹配或批量覆盖规避；
4. 新增回归必须直击失败模式；
5. 实际测试、`git diff --check` 与路径 allowlist 审计要求。
6. 当 finding 源于缺陷 fixture（如不完整样例恰被 happy-path 接受而暴露校验缺口），body 必须显式授权「有据修正该 fixture 并在交接记录修正内容」，同时禁止删测试、放宽断言、为通过而弱化校验；不授权则 worker 无法动手，不禁止则会静默放水。

若批准的 delta 精确到一行，先锁定旧候选的完整 SHA256；修复后用只读副本将新行替回旧行并重算哈希，必须严格等于旧候选，才能证明其余字节未变。另对实际新守卫做行为验证：模型须读取或校准安装文件中的条件，硬编码旧条件的模型只保留为 RED 证据；字节身份与模型通过都不能冒充目标语言原生解析或真实服务执行。

## Verify-N 要求

Verify-N 必须只读，独立运行。它需要：
- 重新构造触发失败的最小混合输入；
- 对每个关键行/状态做严格断言；
- 验证 accepted/pending 分流，而非只检查状态字段；
- 对命令包装器，捕获传给 subprocess/run_cmd 的完整 argv 并严格断言参数形状；不得仅断言成功 detail 或 audit，因为 mock 可掩盖丢失的标志、残留的位置参数和索引偏移。
- 修改命令参数时，先区分解析索引相对原参数列表还是包含可执行文件的完整 argv；前置 executable 后必须显式换算索引，避免把 `-r` 等标志覆盖为文件路径。
- 使用混合输入同时验证过滤目标、保留项、注释及无 opt-in 的默认命令不变；过滤内容正确并不等于可执行命令正确。
- 对能解析多种选项拼写的包装器，逐一验证分离形式与等号形式（如 `-r file`、`--requirement file`、`--requirement=file`）；替换路径时保留选项语义，因为同一解析索引可能指向路径 token，也可能指向包含选项前缀的整个 token。
- 将配置或 requirements 副本迁移到临时目录时，用本地混合 fixture 验证嵌套相对引用的实际解析结果，而非仅断言原行保留或 argv 正确；`-r`/`-c` 等引用可能按引用文件所在目录解析，文件内容不变也会改变行为。读取已安装消费者的解析代码，或使用其无网络解析入口核验；不要以无条件成功的 subprocess mock 替代此检查，也不要借引用修复擅自扩大递归过滤范围。
- 从临时资源创建点列出成功、输入缺失、写入异常、子进程失败及 dry-run 的退出矩阵，逐项断言资源被清理；只覆盖执行子进程的 `finally` 会漏掉准备阶段的提前返回。严格只读验证优先用 `compile(source, filename, 'exec')`，避免额外生成 pyc。
- 在 subprocess/run_cmd mock 执行期间读取并快照临时副本内容、消费消费者解析器的结果；函数返回后仅检查清理结果，因为正确的 `finally` 会删除文件，返回后再读取会制造测试失败。解析器返回生成器时必须实际迭代并断言解析出的条目，而非只创建生成器或检查引用文本。
- 对有持久化摘要的多源 CLI，单列中断验收矩阵：在每个源边界分别注入 `KeyboardInterrupt`，覆盖尚无结果、已有部分结果及前一源已完成的场景。从公共入口同时断言契约退出码、源级 `INTERRUPTED`、已取得结果保留且不重复、未启动源不伪报完成。`KeyboardInterrupt` 不属于 `Exception`，顶层捕获并返回正确退出码仍可能丢失源级事实；需要修复时只在负责该摘要的窄边界标记中断，用 `finally` 汇入已取得结果，并以裸 `raise` 原样传播，不扩成吞掉所有 `BaseException` 的通用容错。先原样重跑独立失败选择器，再跑新增矩阵和完整受影响回归；中断摘要完整不等于数据库回滚或生产覆盖完整。
- 用不同源目录下的同名输入验证多文件副本隔离；必须包含完整源路径不同、直接父目录 basename 也相同的反例（如 `serviceA/reqs/requirements.txt` 与 `serviceB/reqs/requirements.txt`），不能只用父目录名不同的两个输入。严格断言完整 argv 中副本路径不同、各副本内容分别保留本根依赖，并在 run_cmd 回调期间实际消费消费者解析器，证明第一根依赖未被第二根覆盖。只用 filename 或 parent.name + filename 命名仍会碰撞，返回 pass 或总测试数全绿均不能替代这些断言；尚未完成独立反例验证的命名方案不得写成已通过。
- 对照文档验收示例与代码规范化结果，分别核验大小写、分隔符归一化及去重保序；正确实现与错误示例冲突时修正文档，不放宽匹配或删除正确断言。以 PEP 503 为例，`Long_Bridge` 等价于 `long-bridge`，并不等价于 `longbridge`。
- 重跑相关回归；
- 明确覆盖范围与真实环境未覆盖项；
- **反向回退实验**：回退候选实现后新增用例必须失败（证明非恒真）；
- **独立探针**：不复用测试文件工厂函数，用最小脚本直接打生产路径；
- 按契约**逐条**验收矩阵取证，不得以"测试全绿"代替逐条核对；
- **证明可移植性，而不只是绿**：回归若读取 git-ignored 的本地原始档案，在有该档案的机器上必绿、在任何其他 checkout 上必失败。要求独立门禁在档案缺失的受控条件下重跑该回归（monkeypatch 造缺失，绝不删除或移动真实文件），并把 ignored 档案依赖当作测试交付缺陷修在测试文件内部（内联最小公开摘录 + 来源 SHA 常量），而不是写进报告当注意事项；
- **自建控制违反被测契约时，先分清谁错**：若控制失败源于自身期望值违反契约（例如把"补齐时观察时间不得移动"的字段改新后又断言读回全等），那是控制前提错误，不是产品缺陷。按契约还原控制输入后重跑，保留首次失败日志并标注不计产品缺陷；不得反向推翻已成立的结论，也不得改产品代码去迎合错误的期望；
- **按阶段重算差分归属，不引用旧报告结论**：多阶段修复链（每阶段各有 baseline 与 allowlist）必须以各阶段 baseline 的 hash 链程序化重算每阶段变更路径与累计并集，再与设计文档的阶段清单逐条比对；拿某一阶段的局部清单去判断另一阶段越界会误报，也不要把上一阶段的 PASS 当作当前候选的 PASS；
- 多轮重跑时**证据按轮次分文件**并保留对照版报告，不覆盖历史证据。

## Closeout 清单

1. 新 Fix、Verify 均为 `done`，Verify=PASS；原流程要求 Review 时，还须对修复后候选完成独立 Review 且 done/APPROVE。可复用从未执行、范围未变并已重绑 fresh Verify 的原 Review 卡，但不能复用旧候选的 PASS；不要求 Review 的流程执行既有 Closeout 自审。
2. 检查修复链的实际测试、独立复现、diff 完整性与范围证据。逐项将失败反例映射到独立 Verify 的实际输入与期望/实际结果；任务正文要求检查某反例、worker 泛称“多根不覆盖”或现有测试全绿，都不是该反例已执行的证据。若 Closeout 发现新反例，保留已有通过事实但撤销整体放行，报告漏检的具体输入，不将其包装为新增用户需求。连续局部修复时先汇总 closed/open 验收清单，再在用户确认的既有范围内闭合，不重做已通过项。
3. 在旧 Verify 的下游遗留卡添加说明：该卡由替代链取代，仅作失败审计，不得被重试或误报通过。
4. 面向用户的结论区分：
   - 代码/规则是否完成；
   - 独立离线门禁是否完成；
   - 生产只读访问、DDL/DML、服务变更与交易分别执行了什么。真实数据库只读plan已运行时，明确“已读、未写”，不能笼统写全部生产NOT_RUN。
5. 工程批准后复用已授权的生产卡，不另造Activation或重复索要同一执行范围。若现行契约仍缺操作者短窗口事实，只请求该事实并保持原HOLD；有限的本机进程/timer观察不能替代操作者不并发提交确认，也不能升级为全球writer不存在证明。确认后沿已审入口执行并exact读回，不把只读准备或离线APPROVE写成生产已生效。

## 常见失败模式

- **只验起终态，漏掉合法中间态**：对允许空字段单调补齐的数据链，独立验证覆盖 `pending → 部分字段补齐且仍pending → 最终resolved`，每阶段重新装配组件模拟重启，并用原枚举raw与最新详情/结算raw执行只读核验。不能把只测 `pending → resolved` 的全绿推导为正常续跑完整；中间态不得强索尚不存在的最终证据，也不得靠盲skip、吞坏raw或伪complete修复。已闭合项保留，只对遗漏调用链集中窄修。
- **请求前时钟冒充响应观察时间**：验证 observed/as-of 可得性时，在类别、状态日志等响应体的实际 `read()` 中推进注入时钟；HTTP句柄返回不等于完整响应已取得。至少用两条不同身份连续回查，分别检查新strike和新label在各自完整响应前不可读、各自ceil存储时刻后可读，不能共用首条记录的观察时刻。队列选择/退避的 `moment` 或显式 `now` 不等于后来数据的观察时间；另用显式未来due控制排除错误推迟，保已有首次事实时间。反例走真实ETVL、持久化读回及reader；只测非整秒helper或只在HTTP打开时推进时钟，会漏掉读体延迟与跨身份串时。

- **代码宽泛回写**：依目标代码/名称的整列 mask 覆盖同批其他行。修复须绑定实际命中行的稳定身份，禁止仅按 target code 回写。
- **旧卡状态污染**：失败 Verify 的 child Review 仍处于 todo。保留它，但用 comment 标记替代链；不要让其成为当前放行依据。
- **测试掩盖缺陷**：现有回归通过但缺少混合批次/拒绝分支。以独立最小复现优先，补严格回归后才放行。
- **无修复的 Verify 重跑循环**：首次发现可复现的 Major/Blocker 后，一次列全 file:line、期望/实际、命令和最小修复建议并停止。取得必要授权后先做窄 Fix，再按上述条件选择原卡 R2 或 fresh 卡；禁止不改正文、不加真实 Fix 依赖就直接 unblock。复验先确认 findings 对应的候选/回归确有新 diff，原反例保持原字节重跑，最终对当前候选独立跑一次完整受影响矩阵；无相关修改则保持 BLOCK，不反复刷同一全量 suite。
- **公共入口遗漏**：schema 迁移不能只更新 dataclass、fixtures 与内部 service 测试；必须从实际 public stub/provider entrypoint 构造 smoke，确认输出已是 canonical payload，不能让旧字段经默认值映射成貌似有效的新记录。
- **错误的“已生效”表述**：工作树、离线测试、生产服务是不同状态；必须分别报告。
- **三层事实归档镜像编号冲突**：向 RFC/SPEC/DESIGN 三文档镜像追加同一事实归档子节（如 Closure Ledger）时，先 `grep '^### R3\.'` 三文档现有编号；若某文档的编号已被占用（2026-08-07 案例：SPEC 已有 `R3.11 一致性声明`），**统一改用下一可用编号（R3.12）并在三文档一致使用**，不得让 RFC/Design 用 R3.11 而 SPEC 用 R3.12 造成跨文档错位。镜像正文的互引（"与 RFC V0.x §R3.12 / SPEC V0.y §R3.12 镜像"）必须逐字一致；版本号、来源指针、关联 Design 指针同步更新后才 commit。
- **auto-commit 捆绑 worktree 调查产物入库（`.worktrees/` 卫生）**：仓库 auto-commit 会把 `.worktrees/<task-id>/` 下的调查脚本与报告（含生产计数快照，如 precheck_report.json）误提交进 main。正确处理（2026-08-07 实例 commit 09fdffa）：用 `git update-index --force-remove <files>`（等价 `git rm --cached` 但避免 recursive-delete 审批守卫）从索引移除、**本地保留**作审计证据、`.gitignore` 追加 `.worktrees/`，commit 仅含 .gitignore + 删除。Fix → Verify（7/7：索引零残留 / gitignore 条目 / HEAD==origin/main / 本地保留 / commit 纯净 / diff --check / 无引用断裂）→ Review 闭环。

### 迟到完成与范围 minor 的二次收口

共享 `dir` 中的旧 Implement 即使曾显示 `timeout` / `gave_up`，在补齐 parent 后仍可能被 dispatcher 重新 claim 并产生**晚于 document gate 的有效 completed run**。必须按最新 run 的时间、真实 diff 与测试判断其是否是可审计候选；但候选完成绝不免除 replacement/reconciliation 的独立门禁。

若 fresh Review 报告功能 PASS/APPROVE，却同时保留任何 scope、allowlist 或 provenance 的 `MINOR`，该裁定自相矛盾：立即冻结所有 Closeout，并走 **Principal-only scope reconciliation → fresh Verify → fresh Review**。不要删除正确的测试来制造范围合规；Principal 必须为每个实际变更确定唯一责任阶段，并使 RFC/SPEC/Design 的 allowlist 与互引显式支持该归属。新的 Review 只有明确写出 `0 open blocker/major/minor` 才能放行。

同一原则适用于被标作 `OBS` / “非阻塞观察”的**文档契约漂移**：若 Review 指出版本指针、伪代码、默认行为、真实 I/O 授权边界或 smoke 条件与实现不一致，则它不是可以由 Closeout “顺手修正”的备注。立即冻结 Closeout，创建 **Principal 文档对齐 → 独立 Verify（路径范围 + 定向回归）→ 独立 Review（明确 APPROVE、open_findings=0）**。修订只能触及相关具体 RFC/SPEC/Design 产物；不得借文档对齐改生产代码、测试、依赖或配置。Closeout 仅依赖该补救链最终审查，且仍要把未授权真实 Provider/Mongo/DDL/DML/cron/smoke 作为残余风险，而非完成能力。

详见 `references/replacement-verification-chain.md` 的任务图、Closeout 文案和三行隔离示例，以及 `references/shared-dir-late-completion-and-scope-reconciliation.md` 的迟到完成、scope minor 与替代收口流程。对「Implement 超时但共享树已有候选文件、无 handoff」的固定 T3R 归属/交接模式，见 `references/timeout-candidate-reconciliation.md`。若 T3R 或长 Verify 因 iteration budget 超时、而候选实物已由 Orchestrator 校准，改用 tester 的固定四命令 micro Verify；详见 `references/fixed-command-micro-verify.md`。若 goal-mode worker 已落地实现但 `kanban_complete` judge 失败或 iteration budget 用尽，必须冻结旧卡、以源码与实测为准启动独立 Verify，禁止连续创建同角色重跑卡；详见 `references/goal-mode-terminal-failure-recovery.md`。

### 终态关闭被 kanban_complete 拒绝时的窄授权 SQLite 兜底（2026-08-07）

> 本节全文仅保留 2026-08-07 的事故处置与当时授权，非当前操作入口；不得据此直接写看板 SQLite 或将历史授权推广到新任务。

两种情况下 `kanban_complete` 会拒绝一个本应合法的终态关闭：

1. **`triage` 状态（`block_loop_detected` 后）**：卡先 review-required block → unblock → 再次 block 触发循环检测落入 `triage`，`kanban_complete` 返回 "unknown id or already terminal"，即使实现已完成、证据已在 comment 线程。
2. **`goal_mode=1` 卡 judge 拒绝**：goal-mode judge 在完成时返回 `RateLimitError`/拒绝，`kanban_complete` 失败，尽管实现已完成且独立 Verify/Review 证据齐全。

当工作确实终态（实现完成、Verify/Review 证据在 run/comment 元数据）、仅看板 API 拒绝时，Pascal 已授权窄范围直改 SQLite：

```sql
UPDATE tasks SET status='done', completed_at=<unix_ts>, current_run_id=NULL WHERE id='<task_id>';
```

安全纪律（防止变成习惯）：

- **仅限可证明终态的卡**：证据在 run/comment metadata，关闭是审计轨迹收口，不是"宣称完成"。
- **绝不用于 running 卡，绝不制造独立 Verify/Review 未产生过的 PASS**。
- **每次先试 `kanban_complete`**，仅 API 明确拒绝时才用 SQLite。
- 记录与正常完成相同的 verdict/reason metadata（如 `superseded-by-...`、`provider-unavailable-frozen`），保持 run 历史可解读。
