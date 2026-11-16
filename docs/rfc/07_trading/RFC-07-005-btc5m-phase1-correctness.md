# RFC-07-005: BTC5m 一阶段正确性与诊断契约

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | V1.0，T1 交付候选，待主控文档 Gate；非实现/独立 Validate/运行通过 |
| 作者 | YQuant Principal / yquantprincipal |
| 创建日期 / 最后更新 | 2026-11-16 / 2026-11-16（Asia/Shanghai，UTC+08:00） |
| 所属模块 | 07_trading |
| 来源 | Pascal 已批准的一阶段范围，经 Kanban t_3ee922da 转交 |
| 依赖 RFC | [07-001](RFC-07-001-predictfun-btc5m.md) V1.3、[07-004](RFC-07-004-btc5m-controlled-paper.md) V1.1 |
| 替代 RFC | 不整体替代；仅以下显式增量在新 phase1 策略契约内优先 |
| 派生 SPEC | [SPEC-07-005](../../spec/07_trading/SPEC-07-005-btc5m-phase1-correctness.md) V1.0 |
| AI 适配 | Hermes Kanban Full：Principal RFC/SPEC → Principal Design → Developer → 独立 Reviewer Validate → 主控 Closeout |
| 工作区 | /home/pascal/workspace/yquant-investment；禁止修改其他项目/profile |

## 1. 执行摘要（Executive Summary）

复用现有 DecisionCore、RoundTaker、Broker/paper、replay/history 与固定 btc5m_control 入口，修复受控净份额入场费用语义、隔离预测源状态、补齐断流和时效防线，并在现有事件种类内保存可复算诊断。成功标准是计算正确、输入有效、决定可追溯、前向与回放可对拍，不是 alpha、胜率或收益提升；本次不授权任何新行情驱动的 paper/实盘运行。

## 2. 背景与动机（Background & Motivation）

本文件中 BOT 恒指 `skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`；下列 src/、tools/ 路径均相对 BOT，不是主仓根。

### 2.1 当前事实与来源归属

静态核对基线：主仓 main HEAD `f82f45c53ff68fa63464bb5ec67884d5914ec09b`；BOT main HEAD `a6b4f543ce09e9e2728d9ac1de1781ed3d7e7501`，BOT 工作树干净。主仓两项既有 skill dirty 不属于本卡。源码存在不替代动态验证。

| 当前真实接缝 | 既有能力（保留） | 本次确切缺口及归属 |
|---|---|---|
| src/bot/arbitrage.rs:65–162,363–399 | 唯一 DecisionCore、digital_up、费用后阈值、成交后单轮去重 | controlled Broker 已采用净份额，但 entry 仍为 fair-price-fee；这是本地 07-004 适配漏同步，不是上游旧 cash-fee 口径内部不一致 |
| src/service/spot.rs:26–30,129–175；arbitrage.rs:98–102 | Binance/Coinbase REST、EWMA、20 个 return 预热、floor | SpotQuote 没源/接收时钟；EWMA 只按 symbol、混源且前向无 gap reset，主要继承上游 |
| arbitrage.rs:256–275,328–330 | 原 tick → trade_quotes → Broker::take 消费链 | 请求前时间用于更新，决策 now 被 record_source 标成 observed_at；后者为本地记录适配遗漏 |
| src/bot/runtime/paper.rs:196–281,526–563,750–1034 | 净份额、现金/预占、loss latch、原盘口全额 walk、官方结算去重 | 复用同 State 同锁；补候选上下文和提交前时效重验，不另造 Broker/账本 |
| tools/predictfun/btc5m_control.py:605–774 | 严格字段白名单、原子证据顺序、账务恒等式与类型/秘密拒绝 | 目前无结构化 fair/sigma/strike/盘口，首次写入前校验须同步扩展，不能放开自由日志 |
| src/bot/arbitrage/replay/{types,driver}.rs、history.rs | 显式离线时钟、同 core；proxy 已有 gap 重预热；history 无标签估值 | 新 phase1 需在薄适配中对齐源/费用/时效及真实消费者，不能把已有 replay/history 重做 |

归属以 [origin-audit](../../../data/reports/2026-11-16-btc5m-strategy-diagnosis/origin-audit.md) 为依据。上游固定研究基线是 `71c0e4ff9e299f9a4d81757fd6b15cf54da69b38`，当前 origin/main 已含本地工程，不能称未改上游。

### 2.2 旧证据能回答什么

[诊断报告](../../../data/reports/2026-11-16-btc5m-strategy-diagnosis/report.md) 和 [胜率更正](../../../data/reports/2026-11-16-btc5m-strategy-diagnosis/win-rate-correction.md) 是既有只读证据，不是新 Validate。旧 run `btc5m-20261116-1316-r1` 的 started/public-config、必要两条 summary 样本及 ended 已定向核对；它使用 controlled v1。49 笔的账务复算结论引用更正，不在本卡重跑统计。原记录缺 fair/源时钟/完整决策盘口，不能补造、不重新解释成已保存模型概率；被撤回的 evidence/win-rate-analysis.json 禁作有效结论。discarded 是非协议输出行，不是失败 tick 数。费用、源错配或延迟的机制缺口不等于已证明它们造成多少亏损。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标：仅六项

1. 统一 controlled BUY 净份额兑付与入场 EV，min_edge 保留“每 gross share 的 USDT 期望净收益”分母；legacy cash-fee 明确保留。
2. 预测输入与官方 settlement provider 分责，Binance/Coinbase 状态隔离；fallback 可用于独立 paper 模拟，不代表同结算源或允许 live。
3. 长断流及每次换源清空活跃波动率 epoch 并重新预热；阈值由已有半衰期推导，600 秒仅旧探针场景，不成为配置。
4. 真实记录事件/请求/接收/决策时钟与可用性；提交前再次检查 spot、book、官方轮次期限，缺源时间如实 null。
5. 在现有受控事件种类和递归字段白名单内保存候选/拒绝快照及 candidate→fill/blocked/settlement 关联，支持费用/EV/深度复算。
6. 同核心前向与离线回放薄适配对拍；分开方向命中、入场胜率、净份额、现金净收益，缺数据为 N/A，不造交易结果。

### 3.2 非目标及禁止事项

不做概率校准、动量、OBI、LLM、参数搜索、maker、Kelly、杠杆、WS 或新 Chainlink/oracle 服务；不做 DB/schema、第二执行器/Broker/账本/回测平台、恢复服务。不得修改签名/钱包/API 认证、cron/systemd/gateway、其他 profile、依赖/锁文件、默认 config.json 或原 100/2/2/10/20 USDT 风险预算。不得外部发布、git add/commit/push、reset/stash/clean/restore/checkout 或移动他人工作。

不得启动任何新真实行情驱动 paper 或实盘，不读生产 .env/私钥/YAML 凭据，不做网络/交易/长回测。只允许已审查的纯离线 fixture Broker/CLI/replay 验证。旧 49 笔及 07-001..004 三层契约/历史验收均只读。T1 仅写本 RFC 与对应 SPEC，不写 Design/业务代码/测试/报告/模板/README/AGENTS/SOUL/CLAUDE。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

修正确定的计算与证据接口，不靠增加模型复杂度掩盖缺口。数据事实、模型假设、模拟账务、官方结算各有独立身份，不把价格当真概率。

### 4.2 架构总览

现有采集适配 → 带来源/时钟的输入 → 原 DecisionCore（显式 legacy 或 phase1 策略语义）→ 类型化诊断/候选 → 原 Broker 提交前重验与同锁账务 → 原受控事件 emitter → 原 launcher 递归白名单验证 → 原 events.jsonl。

离线适配使用同一输入语义和 core；执行对拍把决策交给同一现存 Broker 的离线 fixture，而非在 replay 再实现现金账。history 仍只估值，不因新诊断产生盘口、成交或收益。

### 4.3 模块分工与兼容域

phase1 仅用于 unsigned controlled BTC5m 和显式 phase1 离线 replay。普通 paper、signed/live、其他策略/venue、旧 replay/1、proxy 和 history/1 保持默认既有行为；公共类型允许最小 additive 接缝，但不得使旧调用隐式启用 phase1。旧源码“Binance 是结算源”的断言须纠正为预测代理输入的说明，原 signed 的 Binance guard 不因此取消或扩大授权。

## 5. 详细设计（Detailed Design）

### 5.1 业务流程（Flow）

1. 沿固定 unsigned 配置、秘密隔离与一次性启动流程装配 phase1；不新增任意配置开关或真实运行入口。
2. 采集时记录请求开始/成功解码接收的 UTC 和本进程经过时间；源事件时钟只有真实响应携带且语义可核时才有值。当前 REST 无此时钟，就标 RECEIPT_BOUND，不补 now。
3. 验证数值/时钟/来源；按 `(symbol, prediction_source, actual_pair)` 维护独立 EWMA。换源、长 gap、无效时钟进入新 epoch，至少 21 个有效价格产生 20 个 return 才可估值。
4. 每个被选 BTC5m 市场的决策尝试记录两侧估值/edge 或明确不可计算原因；价格/费用/时效失败不能变成看似有效的零。
5. 生成候选时确定 token、gross 目标量及限价；提交前重取当前时钟，以同一不可变输入复算剩余时间/估值/EV并复核年龄。输入改变必须另建关联候选，不能沿用过期候选身份。
6. 仅通过重验与旧资金/深度/损失/截止门禁后进入原 Broker；应用成交前最后检查，不允许候选时合法就绕过延迟后的期限。拒绝资金不变，正成交才确认 entered。
7. 事件验证通过才写证据；协议坏字段/秘密/关联错误沿原 OUTPUT_INVALID 停止流程，不先写 raw 再过滤。官方结算只用原 provider/结果验证及去重，不用预测源本地涨跌代替。

### 5.2 数据模型（Data Model）

SPEC 冻结字段级类型、可空条件及稳定拒绝码：source key/epoch、request/receive/source/decision/submit 时钟、官方 round 身份、p_up/sigma/samples/strike、两侧 fair/price/fee/EV、所需盘口 walk 深度、candidate_id 与成交/结算关联。fair 是模型预期单位兑付，不是盘口价格也不是已验证真概率。

### 5.2bis 持久化策略（Persistence Strategy）

| 数据 | 介质/命名 | 生命周期与边界 |
|---|---|---|
| 正式契约 | docs/{rfc,spec,design}/07_trading/*-07-005-btc5m-phase1-correctness.md，三独立文件 | 本卡仅前二；随显式审查修订，无历史回写 |
| 新诊断 | 既有 run evidence 的 started/public-config/events.jsonl/ended，不增加数据库或第二日志流 | 新版本独立 run，exclusive-create/追加；保留，无 TTL/自动删除/迁移；本卡不创建运行证据 |
| 现金/预占/净库存 | 原 Broker 内存唯一 State/锁 | 本进程生命周期；证据非恢复主账，不新增 resume |
| 工程验收 | 后续唯一 data/reports/2026-11-16-btc5m-phase1-correctness/validation.md 与 evidence/ | 本卡不写；保留，无自动上传/备份；data 被忽略不等于已提交 |

所有新增字段仅 L0 公共行情或 L1 工程关联/模拟金额，不落 L2/L3 原始私密数据、响应全文、环境、密钥、JWT、签名或秘密摘要。Kanban 是唯一任务状态，不建 data/tasks/ 或全文 handoff 镜像。新 schema 不迁移旧证据；回退是后续主控按候选定向撤销本增量，而非重写历史事件。

### 5.3 接口契约（API Contract）

- min_edge=0.03 不改数值、不改成 ROI。controlled edge=`fair*(1-fee_per_gross_share/price)-price`，legacy edge=`fair-price-fee_per_gross_share`。
- gap reset=`elapsed_gap > 300 秒`，等号不断；依据现有 300 秒 EWMA half-life，超过一半衰期的无观测区间不再当连续有效估计。换源无论 gap 多小都重预热，不复用另一源或之前 epoch 的暖状态。
- 固定 poll P=5 秒，spot/book 的本地保守 age 上限为 2P=10 秒，请求跨度上限 P=5 秒，均含等号；这是允许一次轮询延迟但拒绝跨多个周期旧输入的工程时效界，不是实测 edge 寿命或用户收益参数。源时钟存在时同时要求其 age≤10 秒；缺失时只证明本地 acquisition bound。
- 提交与成交应用前实际 `ends_at-now >=30 秒`（含等号），不得用候选时刻或整数舍入掩盖不足 30 秒；run deadline 等号仍优先停新增。
- controlled 证据升级 `btc5m-controlled-paper.v2`，前缀与现有八种 event_kind 保留；新诊断放 summary 的类型化 source.decision 中，不增加自由 candidate/log 事件。v1 只读兼容，不把旧缺字段当新验证成功。
- phase1 离线回放用显式 `btc-arb-replay/2`；/1、history/1/proxy 默认/参数/历史结果不变。不存在时钟/盘口的旧资料只能声明不可重放执行，不补造。

### 5.4 AI 模型设计（如有）

无新增 AI 模型。继续原 driftless lognormal、A&S normal_cdf、300 秒 EWMA half-life、20 returns、vol_floor=0.00005。只修正输入状态与经济映射，不拟合/校准概率；DRAW 实际 payout=0.5，模型 fair 是当前模型的预期兑付假设，不声称模型估计了单独的 DRAW 概率。

## 6. AI 实装规范（AI Implementation Rules）

### 6.1 必须执行

按 SPEC 明确业务语义，再由独立 T2 Design 冻结最小逐文件 allowlist/类型接缝/G3/实际测试命令；不得把代码存在误列为待新建。真实消费者测试必须覆盖 RoundTaker→Broker→emitter→launcher 首次 write 及 replay 对拍，不只测复制公式。数值容差沿 07-004，分类/计数/身份零容差。

### 6.2 先确认的事项

范围外接口、依赖、生产数据、交易或调度变化需主控/Pascal 明确确认。本契约不将阶段二模型优化夹入一期，也不因工程 PASS 自动授权新运行。主控核验 T1 后释放预建 T2，核验 Design 后释放 T3；worker 不自行解除 hold。

### 6.3 绝对禁止

不调用 execute_code 或其包装；历史被拒批量入口记 OMITTED_BY_AUTHORIZATION，不记 PASS。原生文件工具、独立 Git/sha256sum 和后续既有离线测试入口仍受 runtime 许可；新安全拒绝/超时立即 STOP 交主控，不换工具/脚本/worker 绕过。正常 read-before-write/并发保护按原提示处理。

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 影响 | 应对/降级 |
|---|---|---|
| 代理价格和 Chainlink 结算存在基差 | 概率可系统性错误 | 显式 provider≠prediction_source；分层诊断，不新增 oracle，不承诺 alpha |
| REST 无源事件时钟 | 无法证明端到端市场新鲜度 | null+RECEIPT_BOUND、请求跨度/本地年龄拒绝；不标 source verified |
| 换源/长 gap 频繁冷启动 | 信号减少 | 如实 WARMUP；保留既有持仓与结算，不用 floor 绕过预热 |
| 新协议遗漏字段/含秘密 | 无法复算或泄露 | 双端同版白名单，首次 write 前校验，坏协议关闭新增并记录不完整 |
| 对共享文件净增引起 G3/普通回归 | 旧路径损坏 | T2 用实际规模规划；不得照抄旧迁移计划或自动大拆；独立 Validate |
| 修正后仍亏损 | 不能证明策略优势 | 正确性验收不以收益为门槛；旧亏损不重判、后续研究另授权 |

## 8. 备选方案（Alternatives Considered）

- 全局把所有 edge 改成净份额：会改变 legacy 账务/普通消费者，拒绝；采用显式语义。
- 仅每个 source 各留暖 EWMA 并直接切回：会把非连续时期当活跃连续状态，拒绝；每次切换新 epoch。
- 600 秒固定断流配置：没有用户来源且与已有 half-life 无必要对应，拒绝；用 300 秒现有尺度。
- 缺源时间就禁止所有现有 REST 输入：会在未授权换源前使路径完全失效；采用诚实接收界限，不声称源 freshness。
- 新建事件总线/独立 Broker/回测服务或自由 debug 输出：范围和泄露面不必要，拒绝；复用原消费者及白名单。

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收

SPEC A-001–A-022 必须覆盖：费用临界正反例/镜像两侧、源切换与长 gap、20 returns、缺/未来/乱序时钟、候选延迟至不足30秒、陈旧/不足深度、候选与拒绝诊断、关联/重放/官方结算、普通分支回归。后续工程须真实执行离线消费者，不能以文档或单纯编译冒充通过。

### 9.2 非功能验收

无新增依赖/网络/凭据/交易副作用，既有64KiB事件行界限与秘密拒绝保留；不增加收益或耗时硬指标。T1 本身只验两独立文件、来源引用、六范围/禁项、计算边界与反例矩阵及 path-filtered diff/SHA，不跑业务测试。

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分

沿已建 Full 图：本 T1 → 主控文档 Gate → 既有 T2 Design → 主控 Design Gate → 既有 T3 Implement → 独立 Reviewer Validate → 主控 Closeout。没有额外研究、运行或发布阶段。

### 10.2 任务与职责边界

T1 交付本 RFC/SPEC；T2 决定内部类型/精确改动文件/无网命令，不重选业务阈值。已测行数：arbitrage.rs 1007，spot.rs 255，runtime.rs 2354，paper.rs 1458，paper/tests.rs 1321，replay/driver.rs 1116，replay/types.rs 438，history.rs 119，btc5m_control.py 875，test_btc5m_control.py 1194，predict_fun.rs 2398，config.rs 1377。1201–2400 文件需说明增长/拆分触发并由既有独立 Validate 审查；不得把2354/2398行文件继续推过2400而无 Principal Design。T1 不授权拆分，T2 只规划直接必要增量。

## 11. 开放问题（Open Questions）

待实现者决定的业务语义项：无。内部类型名/位置、最小代码组织与具体测试筛选由 T2 在冻结语义内确定。源时间不可用、代理基差、真实盘口/执行延迟、官方原子舍入和盈利能力均未由本阶段验证；按 SPEC 明确降级/拒绝，不猜值。后续真实运行必须另行批准，不阻塞本阶段纯文档交付。

## 12. 参考资料（References）

- [SPEC-07-001](../../spec/07_trading/SPEC-07-001-predictfun-btc5m.md) V1.3：旧 core/replay/history 因果与指标边界。
- [DESIGN-07-001](../../design/07_trading/DESIGN-07-001-predictfun-btc5m.md) V1.3：历史薄入口与默认兼容。
- [SPEC-07-004](../../spec/07_trading/SPEC-07-004-btc5m-controlled-paper.md) V1.1 §4.3–4.8：现金/净份额/官方结果/期限/来源。
- [DESIGN-07-004](../../design/07_trading/DESIGN-07-004-btc5m-controlled-paper.md) V1.3：已落同锁 Broker/launcher 接缝；不是本次重做清单。
- §2 所引诊断/归属/更正；旧证据根 data/reports/2026-11-16-btc5m-controlled-paper/evidence/btc5m-20261116-1316-r1/。
- 具体实现事实以本地 BOT 基线源码为准，未新增外部查询或将上游文案当实测结果。

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-11-16 | 六项一期范围、显式兼容域、经济分母/源状态/时效/诊断版本/同核心对拍与授权边界 | YQuant Principal |
