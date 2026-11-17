# DESIGN-07-005: BTC5m 一阶段最小增量设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | Draft V1.0，T2 Design 交付候选；待主控 Design Gate，非实现或独立 Validate PASS |
| 作者 | YQuant Principal / yquantprincipal |
| 创建日期 / 最后更新 | 2026-11-16 / 2026-11-16，Asia/Shanghai（UTC+08:00） |
| 来源 RFC | [RFC-07-005](../../rfc/07_trading/RFC-07-005-btc5m-phase1-correctness.md) V1.0 |
| 来源 SPEC | [SPEC-07-005](../../spec/07_trading/SPEC-07-005-btc5m-phase1-correctness.md) V1.0 |
| 来源任务 / 模块 | t_0be95623；Full T2；07_trading |
| 工作区 | /home/pascal/workspace/yquant-investment |
| 适用工程根 BOT | skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits |

输入实体已完整读取并以独立 sha256sum 核对主控 Gate：RFC SHA256=`45b8b18aa3084a7cd2e4b5dbeefd2d2e208c60e93c840086c2c9108f54a54e88`；SPEC SHA256=`9d4c7c4bf4291ca3c00e2eef000514e01c99f6e181ed0ee407383cf80aceb2e1`。二者均 V1.0，业务契约冲突未发现。状态栏保留其 T1 交付时文字，实际准入依据 Kanban 主控已核实体/SHA 的评论，不回写上游文件。

## 1. 设计摘要

本设计只落实 SPEC 六项一期正确性增量：显式净份额 EV、来源 epoch、获取时钟和重预热、提交/应用前复核、v2 诊断与关联、同核心 /2 对拍。保留原 DecisionCore、RoundTaker、同 State 同锁的 Broker、盘口 walk、官方结算、launcher 和 replay/history；不增加执行器、资金账、统计平台或新运行入口。

最小接缝为：

1. 不改 SpotQuote/BookSnapshot 既有字面构造和普通调用契约，新增带 clock 的窄包装；原 REST 获取处记录请求/解码接收时刻。时钟统一来自本次 phase1 装配的同一进程时钟。
2. 在原 DecisionCore 增加显式策略语义及 phase1 状态；新子模块只承载该 core 的增量方法/类型，不复制 EWMA、digital_up 或再造决策引擎。
3. 原 Broker 增加携一次性不可变候选的受限 BUY 方法；裸 take 的 phase1 BUY 拒绝缺上下文，其他原分支默认不变。重验和原现金更新仍在同锁内。
4. 现有八种事件不扩张；原 emitter 与 launcher 同步 unsigned v2，逐行字段/公式/关联验证通过才首次写入。/2 从原 replay 配置的 schema_version 显式选择，不新增 CLI 开关。

本卡实际仅创建本文，不修改任何业务、测试、配置或旧报告。本文中的新增符号、测试和命令均为 T3 planned implementation，不是已运行结果，不作为 Gate finding 或业务 PASS。T2 完成不解除预建 T3 的主控 hold。

## 2. 现状分析

### 2.1 候选基线和保留能力

本次独立 Git 观察：主仓 main HEAD=`f82f45c53ff68fa63464bb5ec67884d5914ec09b`；BOT main HEAD=`a6b4f543ce09e9e2728d9ac1de1781ed3d7e7501`，BOT 工作树干净。主仓两项既有 dirty 是 `skills/infra/worker-budget-recovery/SKILL.md`、`skills/infra/yquant-kanban-repair-orchestration/SKILL.md`；另有 T1 的 RFC/SPEC untracked，均保留不动。新子模块路径的精确文件检索未发现额外 AGENTS.md；按主项目协议执行。

下表行号为上述基线的定位，不承诺 T3 修改后行号。源码存在与先前签收分别举证：07-001/004 已有离线能力按其原签收保留；本卡只做静态核实，不重跑或追认新的动态结论。

| 接缝 | 静态核实的 existing baseline | 真实增量缺口 |
|---|---|---|
| src/bot/arbitrage.rs:65–162,363–399 | DecisionCore、原估值/entry、正 fill 才 entered | entry 仍 cash-fee；symbol-only vol；phase1 的完整 attempt/recheck 不存在 |
| 同文件:244–350 | 原 tick、Known.observe、trade_quotes→Broker.take | 请求前 now 更新 vol；早 return/continue 不留拒绝；record_source 把决策 now 当 observed_at |
| src/service/spot.rs:26–30,65–118 | SpotQuote、Binance 优先/失败 Coinbase/300秒再试、5秒 timeout | 无 actual_pair/acquisition clock；缺受控输入合法性和源隔离 |
| src/bot/quoting.rs:45–64；src/service/predict_fun.rs:1053–1070 | 跟踪持仓市场、读取 batch books、同 tick observe；批量 API 分批获取 | BookSnapshot 无 clock；每批请求时刻不能靠批次全结束后统一 now 伪造 |
| src/bot/runtime/paper.rs:196–237,739–1034 | 净份额、原全额 walk、现金/预占/损失锁/同锁最后 run deadline | 缺一次性候选、真实轮次期限/fair/EV/freshness 重验及执行关联 |
| 同文件:1259–1458 | 原 emitter、accounting、summary/final、官方结果去重 | v1 envelope 无 seq/diagnostic；事件输出须按同锁因果顺序升级 |
| tools/predictfun/btc5m_control.py:418–443,465–602,605–778 | 独占证据创建、有界 supervise、递归白名单、相邻账务核验、首次 write | v2 强制字段/公式/候选生命周期校验缺失；public_identity 固定清单漏 spot 等新影响文件 |
| replay.rs；replay/{types,driver,tests}.rs | 原无网 facade、Driver、显式 available clock、去重、result/label 分离 | /2 严格分版、同 core 时钟/源语义及真实 Broker 结果反馈 |
| history.rs、旧 /1/proxy、其他策略/venue | 原默认估值或普通 cash-fee 消费者 | 无本期新能力；只须回归，不重写 |

增量覆盖关系仅限 phase1：替代 07-001 在该域的 symbol-only/旧 entry 与回放时钟映射，补 07-004 controlled entry/observed_at/诊断缺口。07-004 现金/净库存/mark/loss/deadline/官方结算/秘密隔离及 07-001 旧协议均保留。不修改两者历史三层文档、旧验收和运行授权。

来源归属沿 [origin-audit](../../../data/reports/2026-11-16-btc5m-strategy-diagnosis/origin-audit.md)：混源/断流/请求时序主要继承上游，净份额 gate 漏同步、observed_at 错标和诊断不足属于本地适配遗漏。修正机制不等于已证明亏损归因。旧49笔账务复算可引用[更正](../../../data/reports/2026-11-16-btc5m-strategy-diagnosis/win-rate-correction.md)，不能反推缺失 fair/clock/book；withdrawn win-rate-analysis.json 不作有效结论，不另开6h证明工程正确。

### 2.2 规模事实与约束

本卡通过原生 wc -l 实测：arbitrage.rs 1007；replay.rs 150；replay/types.rs 438；replay/driver.rs 1116；replay/tests.rs 796；runtime.rs 2354；paper.rs 1458；paper/tests.rs 1321；quoting.rs 231；spot.rs 255；venue.rs 556；predict_fun.rs 2398；config.rs 1377；btc5m_control.py 875；test_btc5m_control.py 1194。G3 处理见 §3.6，不照搬 07-004 已落迁移和测试提取计划。

## 3. 方案设计

### 3.1 模块/文件改动：T3 精确 allowlist

表中路径均为 BOT 相对路径，展开式为上述完整 BOT 根加 `/` 加该行路径；不是主仓根的 src/、tools/。只有逐行文件获得所述增量范围，不授权整个目录。`修改`包括该文件内原 colocated tests 的必要回归；`新增`现均未落盘，不是本卡提前写 stub。已存在文件不得从零重建。

| 精确路径 | 性质与最小改动 | 必要性 / SPEC |
|---|---|---|
| src/service/observation.rs | 新增：CheckTime、ObservationClock、ObservedSpot/ObservedBook 窄包装、系统/fixture 时钟接缝及 colocated tests | 同一进程的真实获取/检查时间和明确缺值；S2–S4 |
| src/service/mod.rs | 修改：仅注册 observation 子模块 | 上行类型可被原获取/core/Broker 共用；不改其他 service 注册 |
| src/service/spot.rs | 修改：quote_observed 及原获取 helper 的可选 clock 接线、actual_pair/数值验证；保留 quote API/普通路径；纠正结算源注释 | 真实成功源自己的 request/receive；S2–S4 |
| src/service/venue.rs | 修改：MarketData 增加 observed_books 的默认不支持实现，返回带 clock 包装；原 books/TradableMarket/fee/secs_left 默认行为不变 | phase1 无 clock 时 fail closed，不逼旧 venue 造时间；S4 |
| src/service/predict_fun/books.rs | 新增：仅提取原 batch books 获取循环，复用父 get/to_snapshot/BOOK_BATCH_SIZE；提供 plain/observed 薄适配、colocated fake 获取测试 | 实际每批获取时刻及 predict_fun.rs G3 容量；不是新 provider 或执行模块 |
| src/service/predict_fun.rs | 修改：仅注册 books 子模块、原 MarketData::books 委托与 observed_books 委托；不动签名、认证、API host/header/timeout/事实 mapping | 真实 GET→ObservedBook；S4；G3 先提取再接线 |
| src/bot/quoting.rs | 修改：Known 增加 observe_with_clock；原 observe 和新方法共用既有 tracked-market union/remember/observe 过程，普通调用保持原 books | 不丢旧持仓 mark，不复制另一套行情轮询；S4 |
| src/bot/arbitrage.rs | 修改：注册 phase1；显式 core 语义字段/装配和 phase1 tick/trade_quotes 分派、首次市场/strike availability；原 legacy 算法/测试保留；纠正来源注释 | 唯一前向消费链；S1–S5 |
| src/bot/arbitrage/phase1.rs | 新增：原 DecisionCore 的 phase1 增量 impl、来源 epoch/诊断类型、不可变候选和共享 evaluate/recheck；不复制 digital_up/EwmaVol | 收拢该 core 的直接增量，避免原文件堆积；S1–S5 |
| src/bot/arbitrage/phase1/tests.rs | 新增，仅 cfg(test)：core 状态/门槛、真实 RoundTaker→Broker→emitter、/2 对拍 fixture；新 protocol fixture 的精确名见 §5 | 新能力不只用纯函数自证；S1–S6 |
| src/bot/runtime.rs | 修改：仅原 take 受控 BUY 分派的缺上下文保护及必要内部导入/接线；原签名、普通/live 分支不变 | 裸 take 不可绕过 phase1；S1/S4 |
| src/bot/runtime/paper.rs | 修改：原受控 take 接收可选候选的内部共用路径、同锁 PRE_SUBMIT/PRE_APPLY 重验、复用净份额函数、v2 emitter/关联/seq；其余资金/结算不变量保留 | 原唯一 Broker 与证据输出；S1/S4/S5 |
| src/bot/runtime/paper/tests.rs | 修改：原 cash/同锁/尾查/官方结果反例保留，成功 BUY fixture 携真实有效候选；增加裸 take 拒绝、延迟/释放/关联回归 | 测试随合法上下文升级，不能以禁用 phase1 让旧断言绕过；S4/S5/A-022 |
| src/bot/arbitrage/replay.rs | 修改：原 run 按 config 版本严格解码、统一输入适配/输出序列化；不新增入口/账务/网络 | /2 接入原 facade；S6 |
| src/bot/arbitrage/replay/types.rs | 修改：新增显式 /2 wire 类型和输出 wrapper，原 /1 类型不吞新字段；配置校验分版 | 严格 clock/actual_pair/elapsed/strategy_contract；S6 |
| src/bot/arbitrage/replay/driver.rs | 修改：原 Driver 分版规范化输入、使用同 core、availability/candidate/result 接线；原 /1/proxy 分支保留 | 不造第二 Driver/模型/资金账；S6 |
| src/bot/arbitrage/replay/tests.rs | 修改：/2 流/因果/结果反馈及 /1 原断言回归，复用原 facade | S6/A-019–022 |
| src/bin/btc_arb_replay.rs | 修改仅测试：以现有参数/read_config/run 接缝消费 /2 文件；生产 CLI 参数/执行流程不变 | 配置 schema_version 已足够 opt-in；不造 --phase1 或新 runner |
| tools/predictfun/btc5m_control.py | 修改：按 mode 绑定 v2/v1、严格诊断 schema/公式/关系索引、首次 write 顺序、started/ended 标记、public_identity 精确影响文件清单 | 原监督/写入消费者同步 S5；环境/单键来源逻辑不动 |
| tools/predictfun/tests/test_btc5m_control.py | 修改：unsigned fixture 升级 v2、只读 v1/signed 回归、真实 Rust 新旧协议消费者/破坏/首次 write spy/指标复算 | S5/S6；不读生产文件/不调用真实 bot |
| tools/predictfun/README.md | 修改仅 BTC5m 段：两语义、v2 字段/缺源时间、/2 配置选择、旧证据限制 | 用户可见兼容边界，与实际实现同步 |
| docs/LIVE-TRADING.md | 修改仅受控 BTC5m 段：phase1 是预测代理+模拟，不是 Chainlink 同源/新运行授权 | 避免旧来源解释和工程 PASS 被当实盘许可 |

T3 只可按表实施必要 delta，不要求为“用完白名单”而修改每一行；不需要的接缝保留原字节并在交接说明。本文是允许新增模块的完整名单，新增原因均是当前冻结契约直接必要的类型、时钟或原函数提取，不是平台化建议。

明确只读：src/config.rs、src/models.rs、src/main.rs、arbitrage/history.rs 及其 tests、src/bin/btc_arb_history.rs、runtime/live.rs、predict_fun/account.rs、SDK/local_signer/cli.py/sdk_ops.py、默认 config.json、btc5m-controlled-paper.json、Cargo/requirements/锁文件、旧报告、三层模板/README、AGENTS/SOUL/CLAUDE、其他项目/profile 和既有两项 skill dirty。不改 gitlink、不 git add/commit/push、不 reset/stash/clean/restore/checkout。若实际编译证据要求修改只读文件，先集中报具体符号/调用者给主控，不能自行扩大 allowlist。

工程验收报告仅后续 `data/reports/2026-11-16-btc5m-phase1-correctness/validation.md`，必要原始结果仅同主题 evidence/；不是额外源码授权。T2 不创建报告/运行目录，任务状态只在 Kanban。

### 3.2 数据流/控制流

#### 3.2.1 装配及真实获取

沿原 unsigned fixed launcher→原配置加载→Ctx/Broker→arbitrage::run。`with_controlled_paper` 装入本次 `Phase1Run`；RoundTaker 看到确切 unsigned controlled 上下文后用 `DecisionCore::phase1`，普通 `DecisionCore::new/with_warmup` 继续 legacy。signed 没有 PaperCash，不装 phase1。/2 的 Driver 显式创建相同语义 core。没有用户可调策略开关，不改默认资金/配置/模型参数。

`Phase1Run` 的 clock 为同一个共享只读时钟句柄：获取、core、Broker 使用同一 origin。新 observation 模块的系统实现采样 UTC 与 Linux CLOCK_BOOTTIME；elapsed_ms 是本次实例起点的经过毫秒，包含 suspend。Rust 当前 ControlledRun 仅有 Instant，不能把它冒称已有 BOOTTIME；本增量不改 config.rs 的旧时钟。以标准库 FFI 的小型 clock_gettime(CLOCK_BOOTTIME) 接缝取得 Linux 时钟，不加 libc/依赖或校时服务；unsafe 仅限该函数及已核目标 ABI，返回错误/非Linux不支持时 phase1 失败关闭，不退回会漏暂停的 Instant。fixture 实现只由测试注入显式 UTC/elapsed，生产不开放覆盖参数。旧路径不要求这个新时钟可用。

SpotFeed 的普通 quote 仍返回旧 SpotQuote。phase1 的 quote_observed 在 Binance 或 Coinbase 的实际请求前、成功响应完整解码/数值检查后取样：fallback clock 从成功 Coinbase 请求自己开始，不能包括先前 Binance 失败等待，也不能在 quote 返回后补 request_at。actual_pair 来自真实请求符号；当前源事件时间固定 null/MISSING/RECEIPT_BOUND。phase1 非有限/非正响应视作获取失败，沿原 fallback 政策；普通路径不被静默改阈值。原 5秒 HTTP timeout/300秒重试政策、host/认证均不变。

盘口通过 `Known::observe_with_clock → MarketData::observed_books → PredictFunClient books 子模块`：每批调用原 get 之前取 request，解析并验证该批 book 后取 receive；该批各市场携同一真实 batch clock，不把第一批 receive 改成最后一批完成时间。`plain` 与 `observed` 共用原 batch 循环/映射，只有后者要求 clock/合法输入；原 OrderVenue/单本 book/SDK 不迁移。默认 trait 的 observed_books 不支持时返回缺数据，不能把旧 books 缓存标成刚接收。无可核源 timestamp 仍 null，不从未验证响应字段猜值。

Known 仍将原 ids 与 tracked_markets 去重合并、补已知市场并调用原 Broker.observe；新分支不替代持仓 mark 规则。同 tick 失效/缺 book 不恢复旧 mark、不把 fair 用作 mark。clock 包装不改变 BookSnapshot/mirrored 的原数值和旧调用者。

官方身份/strike 的本地 availability 由 RoundTaker 接收对应 live_rounds 事实时记录，首次有效取得后冻结，后续轮询不能延后或改写该起点；未知保持 null。若整批查询才交付，记录交付时刻这一保守本地可得边界，不猜官方发布时间。strike 仍官方 start_price，不用 spot 重设；身份/固定strike冲突作为 MARKET_INVALID，不能覆盖原快照。

#### 3.2.2 每次评估、候选与拒绝

phase1 每个已选市场每次 tick 必须走 `evaluate_phase1` 一次，不能沿旧已入场/预热不足/缺 book/halted 的 continue 直接丢诊断。获取失败保留已选列表，对能完成的评估写 MISSING_INPUT/其他优先原因后再返回原 tick failure，不伪造输入；完全没有被选市场则无假 market attempt。停止使 drive 未再发起 tick 时不制造事后 attempt。

检查顺序逐字沿 SPEC §4.6；诊断安全可算的字段保留，不为失败填零。`DecisionCore` 为本 run 顺序分配 decision_id；非候选 candidate_id=null；只有 EVALUATE=ELIGIBLE 才令 candidate_id=decision_id。初步门槛通过但薄盘/原资金失败仍应先有该评估，再由真实 Broker 阻断，不能把原 ThinBook 当成功或提前隐藏资金拒绝。

`evaluate_phase1` 对 Up/Down 一起产生快照，Down 使用原 BookSnapshot::mirrored 的舍入与流动性；沿原 shares_for 下取整 q。edge 最大者，精确同值选 Down；不因拒绝换侧/缩单/抬价。非法输入不入 EWMA；正常无 edge 用 EDGE_BELOW_MIN，不是协议失败。

#### 3.2.3 提交到原 Broker

新内部受限方法 `Broker::take_candidate(market, yes_book, candidate)` 只服务 phase1 BUY，仍调用 paper.rs 原 controlled_take_locked 的同一主体，不增加 Broker 类型或余额。原 public take 签名保留：phase1 的裸 BUY 在入口先验以 CONTEXT_MISSING 分支映射为 TakeResult::Blocked(DataIncomplete)，且预占/成交为0；它没有合法candidate，不能伪造id或发一条违反v2关联规则的blocked事件。测试分别断言这个确切分支、返回值及无预占/成交；这不是有候选的正常策略拒绝。普通 take、signed/live 和受控 SELL 的既有合法共享接口不要求伪造候选。没有运行时关闭上下文检查的后门。

CandidateContext 只能由同 core 成功评估建立，内部字段不供外部任意构造/反序列化；包含冻结输入、当前 input revision 和两侧诊断。RoundTaker 在一次性 evaluate→submit 中传这一上下文，不再用 token→last-source 表解释本次 BUY。revision落在同core的phase1输入槽：每symbol的spot/key/epoch失效计数与每market的book/fee/身份失效计数，使用共享Arc<AtomicU64>；候选保留这些句柄和创建时计数，Broker在同锁检查当前计数仍等于冻结值。刷新先递增失效计数，再交付新输入；计数溢出失败关闭，不能重置复用。旧候选若尚未终结，先由原 Broker 输出 INPUT_CHANGED blocked，再生成新 attempt。revision仅是内存输入身份，不进入wire字段或持久化，不是第二资金账或来源历史服务；输出关联只比较SPEC已经列明的冻结输入字段。

Broker 在原 State 锁下注册/核对本次 candidate 的 id、market/token、q/limit、source key/epoch/revision 和实际传入 market/book 是否仍匹配；不可重用已终结候选。当前仅保留一个串行待提交候选槽及已正 fill 的 token→candidate 关联，均在原 PaperCash 内；无候选→资金独立注册表。revision 由本次冻结输入的共享失效标识进行核对，不能靠可变 last-source 字符串替代完整上下文。输入变化的测试必须走该真实检查，不能仅测试两个 struct 不等。

顺序固定为：

    原同锁停止/损失状态 → PRE_SUBMIT 新 clock 与共享 recheck
      → 原 mark/最低金额/资金/限价/全额 walk
      → 原 reservation
      → PRE_APPLY 新 clock、共享 recheck 和 VWAP 净份额 EV
      → 原 apply_buy/holding/cash/fee → 正 net fill → core.confirm_fill

PRE_SUBMIT 失败直接 blocked，无 reservation。原 Broker 拒绝保留原 Blocked reason，diagnostic_reason=BROKER_BLOCKED。reservation 之后失败释放本笔一次，依次 release/blocked，现金、成本、库存、entered 不变。phase1 新原因用原 DataIncomplete 承载，diagnostic_reason 细分；run deadline/停止/损失优先 reason=RUN_STOPPED，不因同时出现30秒信号而放行。正 fill 才 entered，settlement 不清 entered。

PRE_APPLY 是同锁内实际应用前采样/复算的快照，不读取网络。2026-11-17 Pascal 确认的最小实现澄清：为防 stdout 写阻塞成为未复核延迟，PRE_APPLY 先在同锁内有界本地序列化并暂存在本次调用局部缓冲；fill/release 在 reservation 前先编码不可变字段，并以 accounting 标量、event_seq、event_time、diagnostic_reason 的明确编码长度上界预检最终整行容量及剩余序号。动态标量的保守表示宽度预算不是业务阈值，整行仍须遵守原 64KiB 上限。此处不要求应用前固定事后账务的最终字节，不预演或复制账本：成交后从原 Broker 真实状态构造 fill 的 accounting，拒绝释放后从真实状态构造 release 的 accounting；容量或序号不足必须在应用前拒绝。应用前最后一次取时钟、检查/计算，紧邻本地内存更新，二者之间无 await、网络或阻塞 stdout；随后仍在该锁的事件出口按序输出（PRE_APPLY 在 fill 行前）。PRE_APPLY 快照中的 accounting 是采样时的真实应用前账户值，不是 flush 时重新拼成的事后值。不跨调用缓存/持久化局部事件，不形成事件主账；所有走该出口的 v2 事件共享序号/输出顺序，不能让其他线程插队。

如果最终重取 clock 使较早的 PRE_APPLY 失效，只发当前最终检查的快照，不把临时局部计算当已发事件。任何最终检查失败仍 release/blocked，不应用成交；编码/容量失败先按 DIAGNOSTIC_LIMIT 停该候选。实际 stdout I/O 在应用后失败只能停止新增、保留真实 Broker 状态并使 run 证据不完整，不能假装输出成功、回滚已发生账务或补造成功 terminal；这是无持久化事务的明确边界，不新增可靠消息服务。

### 3.3 接口与数据结构

以下为本次确定的内部接缝名，可在不改变 wire/所有权/调用边界的前提下做局部 Rust 风格调整；不得改变 SPEC 字段名、枚举、null 或阈值。wire 字段完整清单以 SPEC §4.3/4.5 为单一来源，不在本文复制第二份易漂移 schema。

| 类型 / 方法落点 | 数据、所有权与使用约束 |
|---|---|
| observation.rs::CheckTime | utc: DateTime<Utc>、elapsed_ms: 非负整数；同一 origin；Clock 只读采样接口可返回固定错误，不夹原系统错误/路径 |
| observation.rs::ObservationClock | 恰为 SPEC clock 全字段；source_at 唯一可空键；当前 REST 均明确缺源时间；不得从决策时间隐式 From/Default 出合法 clock |
| observation.rs::ObservedSpot/ObservedBook | 原 SpotQuote/BookSnapshot 加真实 clock；Spot 另有 actual_pair；缓存 clone 保留原 clock；无全局可变行情缓存 |
| phase1.rs::StrategyContract | LegacyCashFee / Phase1NetShares；旧 core 默认前者，只有受控 unsigned 与 /2 显式后者 |
| phase1.rs::SourceKey/SourceEpoch | symbol/source/actual_pair；每 symbol 一个活跃 epoch，key 是该 epoch 身份。切回旧源不恢复暖数据；源名仅有限 enum |
| phase1.rs::DecisionInputs | 冻结官方身份/strike及availability、spot/book及clock、bps、当前 epoch/samples/sigma、决策时刻；无事后 label/end_price/outcome |
| phase1.rs::DecisionDiagnostic/SideDiagnostic | SPEC 全字段的类型化可空快照；所有键存在；不以自由 serde_json map/raw错误承载拒绝细节 |
| phase1.rs::CandidateContext | 不可变 DecisionInputs、decision_id/candidate_id、所选 token/q/limit 和输入 revision 失效标识；同一候选重验不换输入/所选侧 |
| phase1.rs::DecisionCore 增量 impl | observe_phase1/evaluate_phase1/recheck_phase1；observe 持有状态，recheck 读取冻结估计按新时间计算，不偷偷生成 return 或读取另一个 source 的 sigma |
| paper.rs::Phase1Run | clock 句柄、event_seq、一个未终结候选槽、必要的正 fill 关联；都在原 PaperCash/State 锁保护中，不再保存 B/K/R 副本 |
| paper.rs::take_candidate / emit_decision | 只在原 Broker 和同锁中重验/输出；其他策略不能通过裸 take 成功进入 phase1 BUY；事件 emitter 有界类型化出口 |
| replay/types.rs 版本化 wire | 保留 /1 严格类型；新增 /2 envelope/payload 和 output wrapper，规范化后交同一 Driver。/1 不接受 /2 附加键 |
| btc5m_control.py::validate_event / supervise | validate_event 先类型/范围/公式；supervise 在首次 write 之前再做本 run 序列和关联转移；索引不是余额恢复器 |

#### 3.3.1 费用与选择的唯一实现

生产净份额计算复用 paper.rs::net_shares；phase1 估值、walk 后复核与 apply_buy 都使用这一 helper，不抄第二份 fee 算法。当前helper已通过结果有限性拒绝price=0且已有对应测试，不能误列为缺失能力；它允许net=0，phase1 BUY必须在调用方先验检查合法bps、0<p<1及net>0。非法bps/价格按INPUT_INVALID，合法输入却无正净到账比率按NET_SHARES_INVALID，严格沿SPEC原因优先级。helper也被apply_sell复用，不能为BUY门槛而全局改变SELL的合法现金费用语义。legacy round_entry 继续原 market.taker_fee/cash-fee 表达式，不被 phase1 公式替换。

phase1 在 q/price/bps 合法后由 helper 得 net、fee，再计算 cost=q×p、EV=net×fair-cost、edge=EV/q、ROI=EV/cost、breakeven_fair=p/(net/q)。阈值判断使用未展示舍入的原值，edge>=0.03；初选和执行 VWAP 都须通过。q/limit、最坏预占与全额 walk 不变，真实成交价更优可释放差价，但不能把限价外深度算进可成交。

SPEC A-001 的 p=.4、fair=.4381、bps=200 是[既有诊断报告](../../../data/reports/2026-11-16-btc5m-strategy-diagnosis/report.md)的 Decimal 反例，本文不声称重新计算。T3 要用模型路径构造达到该 fair 的真实估值（必要时在相邻可表示范围内构造），验证旧 cash-fee 通过而新域拒绝；同时保留直接 fee 数值向量。A-002 由测试在真实 f64 运算结果上选恰可表示的门槛及相邻值，禁止用约等于断言代替严格接受/拒绝。

#### 3.3.2 来源与状态机

原 EwmaVol::update/vol 和 digital_up 不复制/调参。phase1 wrapper 用有效 receive_elapsed 更新原 EWMA；相邻 valid receive 的 gap 取 UTC/elapsed 的保守较大值；超过300秒清空，等于300秒不清。已有300秒 half-life 是采用此失效尺度的理由，不是最优阈值证明，600秒只作旧探针反例。

首次 epoch=1/FIRST_SAMPLE；每次 source key 变更无论间隔长短均 SOURCE_SWITCH、新 epoch；同 key 长 gap 为 LONG_GAP；损坏的 spot 时钟为 CLOCK_INVALID、新 epoch且丢弃该观测。创建原因在本 epoch 保留，不在第二个样本改成 NONE。清 last price/variance/samples，当前合法新价只作首价，20 returns 前 sigma/p_up 不造值；floor 不绕预热。换轮不清 vol/entered/仓位，来源失效不清 loss latch/结算去重。

新观测在同 key 出现重复/倒序 receive、source时间非递增、elapsed倒退/未来即 CLOCK_INVALID；原 replay 完全相同 event_id/内容在入 core 前去重，所以不重复 return/reset。相同 receive 时刻不生成 return，非法新的重复观测按上述拒绝。仅 book 时钟非法不误把 spot 计新 return；进程检查时钟倒拨则本次活跃 spot epoch 也失效。价格非法不更新 EWMA，不以0价/0波动补齐；双方获取失败保持账务，不新增。

预测状态 Binance/BTCUSDT=PRIMARY，Coinbase/BTC-USD=DEGRADED；官方 settlement_provider 独立取 round_facts 的 CHAINLINK/UNKNOWN，不进 SourceKey，不能根据 Binance 字符串填官方来源。保留原 signed Binance guard，仅纠正“Binance就是结算源”的说明，不提升其运行权限。

#### 3.3.3 时效与应用前重算

冻结常量不新增配置：P=5秒；request_span<=5秒；acquisition_age<=10秒；真实 source 存在还须 source_age<=10秒；gap>300秒 reset；min20 returns；精确剩余>=30秒。前两年龄量按 SPEC 的 UTC/elapsed max 计算，等号接受，不 clamp 负数。10秒是原轮询尺度的工程获取界，不是已测 alpha 寿命。当前 REST null source 合法，但只能披露 RECEIPT_BOUND，无法证明上游真实 freshness。

每次 EVALUATE/PRE_SUBMIT/PRE_APPLY 使用真实 checked clock，保持原 decision_at/elapsed；重验用 max(当前UTC,decisionUTC+经过时间差) 守住剩余期限，但检测到倒拨仍 CLOCK_INVALID，不能把 max 当修复。secs_left 用精确毫秒差/1000，不用 TradableMarket::secs_left 的整数截断；该旧函数仍供 legacy 使用。输入未变也必须按新剩余时间重新 digital_up/两侧 fair/EV/edge，保留原 sigma，不沿用候选 fair。未选侧可重新诊断但不自动改选。

round 身份/open/争议/可得性仍必验；ends-starts=300秒、starts<=now、ends-now>=30秒。run deadline 含等号且优先；任何被模拟的排队、reservation 后迟延、suspend 或 stdout 前置耗时都以最后 clock 为准，不因候选时合法而豁免。测试要分别在 submit 与 apply 注入29.999秒反例。

#### 3.3.4 回放严格分版与同核心对拍

原 CLI 仍 `--mode replay|proxy --config --input --output --summary --from-ms --to-ms`。/2 只在 replay 模式接受：config.schema_version=btc-arb-replay/2 且 order_usd=2，其他固定参数沿 SPEC；/1 order_usd=5 和 proxy/default/history/1 均不变。未知版本、混版和 /2+proxy 在读入/运行前拒绝，不自动探测输入转成另一个经济口径。

解码先做严格版本化 wire 校验，不先丢字段转 Value：拒重复键/非有限/bool冒数、缺键/错null/unknown递归键。/1 用原类型；/2 envelope 必须 elapsed_ms，spot/book 的 clock 和 actual_pair 按 SPEC §4.8 精确对应 event_at/available/received_elapsed。规范化为一个内部输入再交原 Driver，不新增第二套策略循环。完全重复去重早于 epoch 更新，冲突ID/时间倒序仍原 fail closed。

market/state 首次有效 available_at 分别确定身份与strike/fee可用时点。/2 当前 wire 没有新增官方 provider 字段，不得由 rules_source/source 自由文本推断；本次/2诊断 provider固定UNKNOWN，不擅加provider输入字段。fixture 对拍两侧使用一致的未知 provider，不暗注 CHAINLINK。原 official label/result 仍只能事后评价/确认，不能进入 p_up/EWMA。

/2 output 包含 SPEC decision/strategy_contract，非 tick 的 decision 显式 null；/1 使用原 output serialization 不多出这些键。candidate_event_id 在 /2 result 指向 core 产生的十进制 candidate_id，不是随意 tick event_id；只有正 net filled_shares 才 confirm。新增字段不要通过所有字段 Option/default 的宽松 /1 解析器吞掉。

真实执行对拍放在离线 test fixture：同一因果输入分别喂原 RoundTaker 薄适配与原 Driver；同 candidate 再送现存 Broker::take_candidate，显式 clock 在两次检查点推进，收集它实际输出/结果并反馈 Driver。生产 replay 自己不创建 Broker、不处理余额、不新增 submit/延迟事件；测试端才持原 Broker 并注入合法市场规则/mark。只映射 run_id 等测试装配身份，不能归一化 reason/数值/epoch/顺序掩盖漂移。

方向命中、成交方向胜率、gross/fee/net、现金盈利率分别按 SPEC §4.8 的分子分母复算。指标实现仅测试文件中的离线折叠断言，与实际 Broker 事件对账；不新建指标服务、生产报表或拟合模型。旧资料无 clock/book/fair 时明确 EXECUTION_NOT_REPLAYABLE/DIAGNOSTICS_UNAVAILABLE，不能补公平价或从报价反推真实概率。

### 3.4 持久化设计

不新增 DB/schema/索引/TTL 或第二资金账。新事件仍只入原 run evidence，exclusive-create，不覆盖/迁移 v1、不做 resume/上传/备份。字段隐私仅 L0 公共行情/L1 工程关联与模拟金额；无 L2/L3、原 HTTP 响应、环境、URL、密钥/JWT/signature 或秘密摘要。

| 存储对象 | 精确触发点 | 字段子集/校验顺序 | 错误与回滚 |
|---|---|---|---|
| public-config.json / started.json | btc5m_control.py::run→start_evidence→Evidence.write | 原公开配置校验/禁键/来源隔离/固定身份后，child前独占创建；配置内容不变，unsigned started增加v2及strategy_contract；signed维持v1 | 原公开拒绝/重复run/I/O错误不启动child，不吞错或自动换ID |
| BTC5M_EVENT stdout | paper.rs 原 emit_event 及 emit_decision，同 State 锁出口 | 原8 kinds；unsigned增加schema_version、连续event_seq；诊断只summary.source.decision；有界类型化字段/编码预检 | 必要深度超界则 DIAGNOSTIC_LIMIT 合法拒绝，不成交/不截断伪完整；编码/输出失败停新增，证据不完整 |
| events.jsonl | btc5m_control.py::supervise 原 events.write 之前 | strict JSON→按mode/version逐字段重建→公式/范围→序列/候选/结算关联→原相邻accounting→首次write/flush | 任一失败 OUTPUT_INVALID，坏行 write=0，原有合格前缀保留；停止/回收沿原预算，不清洗重写 |
| ended.json | btc5m_control.py::run finally→Evidence.write | 原native exit/forced cleanup/final事实；unsigned v2+strategy_contract；未终结候选/预占/坏final标不完整；不得编造final/accounting | 独占创建失败如实失败；保留已有字节，不补造completed/terminal，不恢复账户 |
| 本次验证输出 | §5 后续已有测试入口；独立Reviewer写唯一validation.md | 最终HEAD、确切变动文件SHA、native命令/exit、A矩阵证据/未验证项；仅synthetic/fake产物 | 失败/partial保留，不以旧PASS或外层0覆盖；临时文件仅当前profile scratch/TMPDIR |

#### 3.4.1 v2 的首次写入保护

launcher 的 mode/started 固定 unsigned=v2/phase1_net_shares，signed-future-live=v1/final-only。保留 validate_event 作为入口，在原文件内增加小型 schema/关联 helpers，不新建 Python 框架。全部新增对象要求精确键集合、必填的 nullable 键、真实类型（整数拒 bool）、有限范围及有限 enum；source clock、双侧诊断和 depth 递归拒未知键。required 与 nullable 不得继续混为任意 None 可过；限制诊断对象只能出现在 market_id非空/token=null 的 summary，旧总账 summary 仍全局身份null/source=null。

必要盘口前缀取原 token_book/walk 所消费的最短限价内前缀，末档原 size 不裁剪；不足就保存所有限价内档位和 depth_complete=false/walk=null。最多1000项、整行64KiB仍原上限；完整必要前缀装不下则 reason=DIAGNOSTIC_LIMIT、depth相关值null，不成交、不另写raw。Python按原输入顺序重新 walk 校验VWAP/fee/net/EV；这是协议复算校验，不是资金账或另一撮合执行器。

supervise 只持必要关系：last_seq、每decision的一次EVALUATE、当前candidate phase/冻结输入指纹与terminal、正BUY的token/candidate、已结算token。指纹仅对已白名单公共结构做内存比较，不输出秘密摘要。PRE_SUBMIT先于reservation，PRE_APPLY先于fill；所有后续同market/token/q/limit/key/epoch及SPEC已列输入字段对应冻结快照，内部revision不输出也不要求Python读取。fill必须最后重验ELIGIBLE、每candidate最多一个terminal，settlement引用此前正fill且不重复。final遗留pending candidate或未释放reservation属于不完整，不能completed；官方pending持仓仍沿原pending披露，不冒充候选未终结。

诊断公式按原1e-7传输界核验；独立数值对拍仍abs或rel1e-9；身份/计数/阈值分类零容差。qualifies/edge门槛直接比较，不能拿1e-7使edge稍小也合格。坏序列不能先更新关系索引/previous再写失败；校验成功才提交索引更新及持久化，I/O错误停止不重试副作用。

旧 v1 只读校验在 validate_event 的显式只读版本分派中保留，标 DIAGNOSTICS_UNAVAILABLE，不新增读取/迁移 CLI；unsigned supervise绝不接受v1，即使单行只读解析合法。signed继续真实账务不可用final，不能给它装100现金。原 stdout/stderr非协议丢弃、秘密名大小写/嵌套拒绝、哨兵和line-size保护保留，RUST_LOG不放宽。未知/非法协议不是 discarded普通输出，仍OUTPUT_INVALID。

public_identity 的固定影响文件清单必须同步覆盖本次所有实际变动/新增源码与测试及两处BOT说明，继续原 main/BOT HEAD和实际binary SHA；显式列路径，不遍历任意目录。新增文件缺失/读取失败在child和首次证据前拒绝。IdentityTest 的隔离 fake BOT 文件清单同步，不能读真实 .env/credentials 或用测试binary替换生产身份。新三层文档身份在工程交接另记SHA，不改旧started。

### 3.5 UI/原型设计

无。

### 3.6 G3：职责、增长和拆分顺序

此节是本次 Principal Design，不是上限豁免；最终按格式化后真实行数报告，独立审查由既有 Reviewer Validate 承担，不增加同卡审查链。

| 文件/组 | 本次边界与增长原因 | 拆分/停止触发条件 |
|---|---|---|
| runtime.rs（2354） | 父只改 take 分派/上下文缺失保护，新增状态/计算/测试均在paper或phase1；最终<=2400 | 若最小接线仍越2400，先报具体符号，不挪普通/live旧业务或压行 |
| predict_fun.rs（2398） | 必须先机械提取原 MarketData::books 批量获取循环到唯一 books.rs；父只mod及plain/observed委托；不搬原ApiBook/签名/认证/SDK/其他tests；最终<=2400 | 委托后仍越2400或需要碰read/交易核心，停报Principal；不自由提取其他模块 |
| paper.rs（1458）、paper/tests.rs（1321） | 受控扩张：保留一个Broker/State；增长仅候选同锁重验和v2/原回归；两者各<=2400，不重做已完成测试迁位 | 实际预计会越2400或出现第二独立资金/执行职责时先报Principal，不追加兄弟资金模块或删断言 |
| arbitrage.rs（1007）、phase1.rs/phase1/tests.rs（新） | 新增计算/诊断集中phase1，父只装配/薄分派；新增文件常规目标<=1200；若实际1201–2400，说明同core职责增长并交既有独立审查 | 任一达到2401前停止并提交具体拆分设计；不能搬整个旧测试树/复制模型 |
| replay/driver.rs（1116）、types.rs（438）、tests.rs（796） | 版本适配可能进入1201–2400，职责仍原Driver/协议/测试，不加账务；解释新增分版/时钟/对拍的实际行数 | 本次各<=2400；达到2401前报Principal，不凭本段授权任意新driver/schema文件 |
| btc5m_control.py（875）、其测试（1194） | v2递归校验/生命周期及反例可能进入1201–2400；仍原固定launcher与消费者；标准库、不新建框架 | 各<=2400；不能用自由schema/宽松None/删断言缩代码；越界先报 |
| observation.rs、predict_fun/books.rs（新）及其余小文件 | 仅共享观察类型/系统clock和原获取循环；常规目标<=1200 | 超1200先在本次交接说明职责/增长并独立审查；不得超2400，无文件>=3600 |

config.rs（1377）只读；models.rs和默认配置不动，避免给所有旧字面构造加可伪造clock。实现顺序为先精准books提取、验证原plain行为，再接新观察路径；其余能力在原位置增量开发。不得以“G3更安全”为由自动大范围重构或新增依赖。新模块是冻结范围内的直接必要增量，不是将整个文件夹开放。

## 4. 实现计划

以下是一期实现的依赖顺序，不在本 T2 执行。2026-11-17 Pascal 批准预算恢复：保留既有 T3 与 T4，将剩余实现按 Rust 前向/事件闭合 → replay/2 → 原 T3 Python 消费者与最终集成串行调度；前两项作为有界下层实现卡，原 T3 等待其真实 parent 完成，原 T4 仍等待 T3 后做一次统一独立 Validate。此调整只改变调度粒度，不改变 §3.1 文件范围、业务语义、§5 验收义务或运行授权，不增加设计/验收阶段；任何中间卡完成都不等于一期 PASS。

1. 先为 SPEC A-001–022 建 RED：保留旧断言，新增明确phase1的费用门槛、缺上下文和源/时钟反例；新测试仅进入已列文件，测试夹具全scratch/fake。复核本地HEAD/dirty/输入SHA，不能还原共享树。
2. 按§3.6提取books循环并回归plain，接 observation/quote_observed/observed_books/Known；统一时钟origin和真实每批获取时刻，保留旧默认API。先证明获取时刻与缓存/失败不续鲜，再接源epoch。
3. 在同DecisionCore增量impl实现evaluate/recheck/两侧诊断；原Broker同锁接候选、两次重验和v2 emitter。先把真正RoundTaker→Broker反例跑通，再修改Python v2白名单/关联和原unsigned成功fixtures；signed/v1/普通不改经济语义。
4. 原replay按config版本接/2，构造同输入前向/回放与同一Broker结果反馈对拍；真实Rust协议流走原launcher至首次write。补指标口径、字段/秘密/超限/坏关联反例和完整受影响回归，不用复制公式自证。
5. 同步BOT两处说明及精确身份manifest；实际记录G3、scope diff、新旧测试命中/native exit/SHA与未覆盖项。T3完成后由预建独立Reviewer Validate验收，主控Closeout；不启动新paper、不修改任何hold。

任何新runtime安全拒绝/超时立即STOP交主控；execute_code及包装入口为OMITTED_BY_AUTHORIZATION，不调用、不重试。正常stale_write/read-before-write/patch冲突按原工具重读，不误认安全拒绝。禁止新runner、内联解释器批量取证或为绕拒绝换执行方式。

## 5. 测试策略

### 5.1 隔离与真实消费者

本节是后续待执行策略，本T2没有运行cargo/python业务测试。全部synthetic/fake clock/transport；生产网络、真实keyring/trader/sign/auth/RPC入口计数必须0。--offline只限制Cargo下载，不证明业务socket为0；运行前审查测试入口，保留原ignored联网测试不运行。测试中的匿名pipe/fixture subprocess沿既有机制允许，不是新的执行平台。

现有 `RustProtocolTest` 已用真实Rust test executable/filter→固定fake child stream→supervise→events.write；保留并升级其unsigned期望，不删skip取绿灯。必须仍非零命中：

- bot::runtime::paper::tests::protocol_consumer_fixture
- bot::runtime::paper::tests::extended_protocol_consumer_fixture
- bot::runtime::paper::tests::signed_ctx_uses_original_factory_and_identity_bound_budget_gate
- bot::runtime::paper::tests::control_pipe_drive_probe（含Python取得真实test executable后的消费方式）

新增且冻结的综合fixture名为 `bot::arbitrage::phase1::tests::phase1_protocol_consumer_fixture`（planned）。它实际驱动RoundTaker/同core/原Broker并输出v2；Python新测试使用既有cargo精确filter/--nocapture模式获取，按真实run/candidate分流送原supervise，WriteSpy断言首次write仅见验证后事件。不是手工拼JSON替代生产emitter。边界破坏在这份真实输出上逐字段mutation，合法前缀可已写，坏行及之后写入0；坏第一行则events内容为空。

旧Broker纯现金测试保持原费用/金额期望；需要成功BUY的fixture通过同core评估生成合法候选，不用测试专用跳过检查。裸take另断言CONTEXT_MISSING。旧协议消费者的序列会增加diagnostic summary，期望按明确新顺序更新而非删除原reservation/release/cash/settlement断言。未改SDK/helper/来源隔离的既有证据可复用，但受影响launcher整套必须运行，B-001–006必须继续全覆盖且fixture文件路径patch到scratch。

### 5.2 SPEC A-001–022 映射

以下每行是可证伪行为，不把一条测试PASS直接等同整行全部覆盖。测试日志/候选SHA与断言位置由后续真实执行登记；无覆盖项明确NOT_VERIFIED，不能靠历史总测试数替代。

| SPEC | 真实路径/落点 | 必须接受/拒绝及账务、协议断言 |
|---|---|---|
| A-001 | phase1/tests：真实core估值→RoundTaker→Broker；legacy同输入对照 | .4/.4381/200旧cash门槛过、新净份额拒绝；Yes和真实mirrored No均覆盖，fill=0、entered不变，保存两侧edge/fee |
| A-002 | 同core真实side选择/原shares_for | 可表示edge恰.03接受、相邻更低拒绝；最大edge/精确同值Down；ROI不替代门控；不借显示舍入或epsilon |
| A-003 | phase1/tests + paper/tests原net_shares/apply_buy/walk | bps0显式和价格两区域、优价VWAP；缺bps/非有限/bool/0或1价/非法net全拒绝；gross/net/cash不双扣费、不抬q/limit |
| A-004 | 原unsigned装配、paper裸take及普通/runtime/replay回归 | phase1 only unsigned或/2；裸BUY缺上下文无预占/资金变动；普通、signed、其他策略旧默认保留 |
| A-005 | spot.rs fake获取→真实quote_observed→core→emitter | Binance失败→Coinbase→原重试时刻回Binance；actual_pair/provider分开、DEGRADED和新epoch；返回源的request不含先前失败；signed旧guard仍拒Coinbase |
| A-006 | paper/tests原official_settlement/controlled_settle→真实filter | CHAINLINK/UNKNOWN、pending后官方合法终态；错token/market/争议/本地涨跌不回款；重复只一次收入，settlement引用正fill的candidate |
| A-007 | phase1源状态 + /2同序列 | gap=300不断、稍超和旧600场景reset；samples从0，19return拒绝、20return可估值；不加600配置 |
| A-008 | 原EwmaVol由phase1消费者调用 | 首价/相同时刻不作return、21有效价/20returns；floor不免预热，短gap换源仍reset、换轮不reset；切回不恢复暖旧源 |
| A-009 | 获取/规范化→core、replay去重入口 | source=null合法；未来/乱序/重复新观测/elapsed回退拒绝并新epoch；坏价不计数；同ID同内容去重不双reset，同ID改内容拒流 |
| A-010 | observation.rs、spot/books fake transport→core→Broker | 请求跨度5秒/获取age10秒等号合法、稍超分REQUEST_TOO_SLOW/SPOT_STALE/BOOK_STALE；源未来/过旧拒绝；缓存clock不续鲜；每批clock不冒最后批 |
| A-011 | RoundTaker→同锁take_candidate fake clock | submit和apply各自恰30可继续；分别跨到29.999时拒绝；reservation后一次release，B/K/库存/entered不变；同时run deadline优先RUN_STOPPED |
| A-012 | core recheck + 原Broker上下文/应用出口 | 时间流逝重算p_up/fair/EV；edge衰减拒绝；刷新source/epoch/book/fee/strike/revision旧候选INPUT_CHANGED；倒拨/suspend不延长，不跨源借sigma |
| A-013 | 原Known/mark/token_book/walk/controlled_take | 限价内足额才可；限价外够量/薄盘/陈旧book/缺同tick持仓mark不成交，原ThinBook原因保留；Down只镜像原深度、不双算流动性 |
| A-014 | 综合Rust fixture→validate_event→supervise→WriteSpy | WARMUP/EDGE_BELOW_MIN/候选/原资金拒绝都有指定summary；安全可算值不丢，缺值null+reason；两侧全部SPEC键、原深度前缀可复算 |
| A-015 | 实际Rust序列 + launcher关系索引mutation | EVALUATE→PRE_SUBMIT→reservation→PRE_APPLY→BUYfill→settlement；错id/run/market/token/key/epoch/q/limit/seq、重复terminal/兑付拒绝且坏行0write；final悬空候选/预占不完整 |
| A-016 | 原run/supervise和读取版本分派 | unsigned只v2、signed保留v1/final；旧v1只读DIAGNOSTICS_UNAVAILABLE；未知版/重复键/漏键/非法null/enum/bool冒数/unknown递归/坏公式OUTPUT_INVALID，首坏行写0 |
| A-017 | emitter完整必要prefix→原line/array界→launcher | 最短完整prefix和末档原size正确；超1000或64KiB不能伪截断/成交；DIAGNOSTIC_LIMIT标量合法拒绝，depth相关null；原秘密大小写/嵌套保护不弱化 |
| A-018 | 实际fake OS child双路输出→原supervise/写入 | raw错误/URL/API/JWT/signature/环境/代理哨兵在stdout/stderr/协议各位置不落普通输出；合法策略拒绝不是协议坏行；实际EOF/kill/reap/cleanup预算旧断言保留 |
| A-019 | RoundTaker薄输入 vs 原Driver /2→同DecisionCore | 同因果clock/spot/book/identity的samples/sigma/p_up/两侧fee/edge/选择/reason/id相同；切源/gap/延迟/薄盘同义；不以两个自制公式互测 |
| A-020 | 同candidate→同现存Broker fixture→v2→launcher→原Driver result | 逐事件B/A/P/K/R/费用/gross/net/entered/结算对拍；零和blocked不entered；PRE_SUBMIT/PRE_APPLY显式同clock推进；回放无复制余额 |
| A-021 | Python测试仅对实际v2 fixture事件做离线折叠 | p=.5 abstain、DRAW/pending、非DRAW/异价异份额；attempt方向分母/正fill方向胜率/现金盈利率分开；逐token净份额与账务一致；旧49笔不补fair不重判 |
| A-022 | §5.3受影响完整套件 + scope/G3检查 | /1/proxy/history/1、普通paper/其他策略/venue、signed回归；原07-004 A001–019/B001–006受影响断言保留，不删skip；生产网络/凭据/调度/发布0 |

### 5.3 必要命令、接受结果与记录方式

以下供主控Design Gate通过后的Implement及独立Validate使用，cwd一律为完整BOT根；每次单条原生命令，不能以管道最后exit掩盖前面失败，不混内联解释器或新runner。本卡未执行这些业务命令，没有测试计数/通过承诺。

| 命令 | 应接受的真实结果/边界 |
|---|---|
| cargo test --offline --locked --lib | native exit0；受影响共享库全部非ignored测试通过，新旧消费者非零命中；不运行ignored网络测试 |
| cargo test --offline --locked --bin polymarket-toolkits | native exit0，原装配/默认参数回归；不是启动真实bot |
| cargo test --offline --locked --bin btc_arb_replay | native exit0，现有CLI参数和显式/2文件配置消费反例真实命中 |
| cargo test --offline --locked --bin btc_arb_history | native exit0，旧history/1只估值边界不变，不跑历史研究/数据库 |
| cargo check --offline --locked --all-targets | native exit0，原公共类型/其他venue/策略编译；不代替上面行为测试 |
| tools/predictfun/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_btc5m_control.py -v | native exit0，原全套launcher/B矩阵和新v2/真实Rust消费者全过；现有隔离依赖，不安装 |
| cargo test --offline --locked --lib bot::arbitrage::phase1::tests::phase1_protocol_consumer_fixture -- --exact --nocapture | 新fixture创建后必须恰命中该测试并产生非空完整v2流；仅exit0但0 tests不是通过；完整Python测试应实际消费该流 |

原精准Rust filters由现有Python测试调用，不能改名后让消费者0命中。无需无依据重跑未变SDK/keyring全库；若实际影响直接调用者，先核scope再补对应原入口，不获生产权限。脚本/工具链缺失、offline依赖不齐如实阻塞，不安装依赖/重试联网。测试临时文件沿TMPDIR/profile scratch；必要最终证据另存批准validation主题，不覆盖旧run。

格式/范围/身份用独立原生命令：主仓及BOT分别 git status --short --branch、git rev-parse HEAD、git diff --name-status、git diff --check -- 后接本卡实际逐文件路径；新增untracked文件另用 git diff --no-index --check /dev/null <精确路径>，记录工具原生exit及诊断，不能把普通scoped diff没覆盖untracked误称已验；wc -l 对实际变动文件；sha256sum 对最终三文档和实际变动文件逐项显式列路径。Rust仅定向格式检查受影响文件，不全仓重排；不把cargo fmt跨模块改动混入本期。

T2自身只做：RFC/SPEC实体/版本/哈希核验、接缝/模板/路径/职责核对、Design静态覆盖/引用、实际新文档no-index空白检查、path-filtered身份/差量与独立SHA。主控仍须核实体和一致性再解除T3 hold；开发自测不替代独立Validate。

## 6. 风险、降级与回滚

| 风险 | 应对/降级 | 回滚边界 |
|---|---|---|
| 源事件时间不可核、Binance/Coinbase与Chainlink基差 | null+RECEIPT_BOUND、key/epoch隔离；不是端到端freshness或alpha保证；官方结果独立验证 | 不换oracle/新WS、不改模型；坏输入停新增/预热，已有持仓/结算不抹去 |
| 请求慢/换源/长gap导致频繁WARMUP | 原阈值/预热如实拒绝，不靠floor、插值或旧源暖状态恢复 | 无自动调参、补资金/放宽30秒或10秒 |
| 新时钟不可用/倒拨/暂停 | phase1失败关闭、明确CLOCK_INVALID或缺输入；BOOTTIME失败不悄用Instant | 不改系统时钟/依赖/profile；停止并报主控 |
| stdout堵塞/协议/写盘失败 | 应用前无阻塞输出；原监督和有界清理；失败保留真实账务/合格前缀、不完整 | 不增加可靠消息/第二日志流，不重试有副作用写入、不从证据恢复余额 |
| 共享函数/普通消费者回归及G3 | 精确类型包装、原API默认、先小提取后新接线、旧断言完整回归 | 只按最终候选逐文件定向撤销本增量；不reset/clean/stash/移动他人内容 |
| 修正后仍亏损、官方原子舍入/真实延迟未模拟 | 明确工程验收不承诺收益；paper全额walk不是排队/部分成交/Gas/赎回仿真 | 不以新6h、策略搜索或阶段二优化替代当前验收 |

代码回滚由主控在候选身份确认后另行定向处理：先停用该新受控入口的未来启动，保留所有历史v1/v2证据；撤销本期限定字段/接线和已提取books小段时恢复其原plain行为，相关测试/说明一致。不得自动换回旧paper继续新行情运行，不将“兼容域legacy”当作获准交易。没有部署、生产数据库/配置/调度、外部发布或任何新真实运行动作，本Design Gate/工程PASS不会自动授权下一轮。

## 7. 交接给实现者

必须遵守：

- 业务门槛、单位、版本、所有必填nullable字段/原因优先级严格来自RFC/SPEC V1.0；本文只冻结实现落点与最小接缝，不让developer再选经济语义。
- 先核输入SHA和共享树真实状态；仅§3.1文件增量，不动两项既有skill dirty、上游三层契约及旧49笔证据。不commit/push、不切分支/修改权限、不访问任何真实凭据/行情交易。
- 复用同DecisionCore与原Broker，原账务/官方结算/同锁/限价深度不重做；上下文和关系索引不是第二账本；legacy/signed/其他策略默认保留。
- 按§5矩阵执行真实消费者和反例，不仅编译/纯函数；任何未覆盖项明确列出。最终交接写changed_files、main/BOT HEAD与每变动文件SHA、真实native命令/exit、G3实数、覆盖/未验证项。
- 来源失败/时钟/不足期限/坏协议fail closed；不得缩量、换侧、补fair、补terminal、增日志自由字段或以已撤回统计撑结论。

可自行判断：局部函数拆分/私有字段的Rust风格、表驱动fixture组织、错误内部实现；均不得改变公开wire字段、拒绝结果、默认行为、allowlist或测试断言强度。测试名除已冻结真实消费者filter外可在相应原文件自定，报告以实际发现/运行名为准，不杜撰计数。

遇到以下情况一次列全交主控/Principal：冻结契约真正冲突；所需路径超allowlist；系统clock/现有工具链不支持且无合法实现；G3需迁出额外业务；必须修改认证/默认配置/依赖/生产路径；runtime安全拒绝/超时。不能用“留待实现者决定”掩盖业务未决项，也不能因有下游而block已完成Design。

T2仅完成本文交付，预建T3仍等主控Design Gate；不自行实现、不自行unblock、不建或关闭其他卡。后续沿既有Implement→独立Reviewer Validate→主控Closeout，不追加研究/Activation/再6h门禁。明确未验证：业务实现及全A矩阵、真实网络/时钟/延迟、官方原子舍入/订单/Gas/收益能力；本卡无此类PASS声明。

## 版本记录

| 版本 | 日期 | 更新内容 |
|---|---|---|
| V1.0 | 2026-11-16 | 基于已核RFC/SPEC冻结逐文件增量、原核心/同锁候选与时钟、v2首次写入、/2薄适配、A-001–022矩阵、G3和离线交接；未实现/未运行业务测试 |
