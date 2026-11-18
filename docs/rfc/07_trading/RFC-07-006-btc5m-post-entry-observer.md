# RFC-07-006: BTC5m 持仓后只读估值观察

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | Draft V1.0；RFC/SPEC 阶段候选，供 Design；不是实现、独立 Validate 或运行授权 |
| 作者 | YQuant Principal / yquantprincipal |
| 创建 / 更新 | 2026-11-18，Asia/Shanghai（UTC+08:00） |
| 模块 / 工作区 | 07_trading；/home/pascal/workspace/yquant-investment |
| 来源任务 | t_408e60a0；Pascal 已明确要求先完善持仓后只读观察 |
| 派生 SPEC | [SPEC-07-006](../../spec/07_trading/SPEC-07-006-btc5m-post-entry-observer.md) V1.0 |
| 后续 Design | docs/design/07_trading/DESIGN-07-006-btc5m-post-entry-observer.md；下阶段独立产出，本阶段不创建 |
| 依赖 / 替代 | 依赖 07-004、07-005 已有受控执行及 06-003 纯估值接缝；不替代或改写它们 |

## 1. 执行摘要

在既有 unsigned phase1 的 5 秒 tick 内，复用同 tick 已获取的 spot/books、同 DecisionCore 的只读 phase1_valuation 和唯一 Broker 的真实净持仓，增加独立、版本化的观察证据。不改变 ALREADY_ENTERED、入场/风险/现金/EWMA 或原交易事件序列，不新增网络获取、退出、加仓、反手或第二决策模型。成功标准是观察有可解释的有效性与成本口径，且同输入下开关观察的原交易行为完全一致；不是证明提前退出能赚钱。

## 2. 背景与事实基线

### 2.1 已验事实与仍缺证据

[既有六小时复盘](../../../data/reports/2026-11-18-btc5m-paper-review/report.md) §7 与 [独立复核](../../../data/reports/2026-11-18-btc5m-paper-review/evidence/independent-review.json) 已核对 65 笔、4984 条事件；其中 2871 次 ALREADY_ENTERED 均无 p_up。该 PASS 只认证描述性复算，alpha 与真实 fill predictability 仍 NOT_PROVEN。不能从旧事件补算不存在的持仓后概率、完整退出盘口或源时间，也不能将无反向成交解读为无反向机会。

本功能为未来合法样本保留持有与退出的可比较输入，不回填旧窗口，不选择事后最优退出点，不重跑 paper、99 日或冻结未来研究。

### 2.2 当前真实源码接缝

以下路径相对 BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`，行号为本阶段所读工作树，不代替后续开工快照。

| 已有接缝 | 核实事实 | 本次边界 |
|---|---|---|
| src/bot/arbitrage.rs:400–456 | tick_phase1 每 symbol 获取报价并 observe_phase1 一次，随后获取带时钟 books | 只复用，不为观察多 quote、observe 或获取 book |
| src/bot/arbitrage.rs:539–658 | 原 evaluate → emit_phase1_evaluation → take_candidate → 正 fill confirm_fill | 原次序、次数、候选与 entered 不变 |
| src/bot/arbitrage/phase1.rs:515–532 | phase1_valuation(&self) 返回 samples/sigma_raw/sigma/p_up | 复用原模型，不复制估值公式；调用前仍须验证当前输入 |
| 同文件:654–664、747–752 | evaluate 可修改检查状态/计数；entered 早退无 candidate | 观察不能重复完整 evaluate，不能假 entered=false |
| src/bot/runtime.rs:99–114、425–430 | Holding 保存 market_id/token/shares/cost/opened_at；Broker 可克隆只读持仓 | shares 在本受控模式为净库存；不新建账本 |
| src/bot/quoting.rs:55–88 | Known 已获取 selected 与 Broker tracked markets 的 book，并保留已知市场 | 已持仓脱离 selected 后仍可复用已获数据；不新增订阅/查询 |
| src/bot/runtime.rs:337–355、1232–1237 | 已有 full-size walk、token_book/No 镜像 | 退出估值只读消费持有 token 的 bids；镜像非独立 No 数据源 |
| src/bot/runtime/paper.rs:268–334 | BUY 扣份额；SELL 在 paper 中扣现金费用 | 可认证 paper 假设口径，不认证真实 venue 未来 SELL fee |
| src/service/predict_fun/fills.rs:1111–1165 | 实际 fill 按已报告 collateral/share fee 记账，缺费保持 UNKNOWN；SELL 非零 share fee 不支持 | 不能仅用 fee_rate_bps 伪称真实净收入已知 |
| tools/predictfun/btc5m_control.py:617–760、1069–1223 | supervise 先 validate/关系检查再首次写事件，普通非协议行被 discarded；v2 严格 schema | 观察必须有明确读取/过滤/持久化链；不得输出无人消费的普通日志或污染交易协议 |

当前 REST ObservationClock.source_at 真实缺失；RECEIPT_BOUND 不能证明远端事件/缓存年龄。此功能披露缺失，不承诺修复 provider。共用目录已有 dirty，以任务开工及 Design allowlist 归属，不清理或重写他人工作。

## 3. 目标、范围与授权

### 3.1 必须目标

1. 对实际正净持仓，在既有 tick 采样原始未校准 p_up、互补 p_down、sigma_raw/sigma、来源 epoch/reset 和输入时钟；无效数据给 null 与原因。
2. 区分双边 touch（Up 与镜像 Down）和持有 token 全量净库存的 bid 侧退出深度/VWAP；不把另一侧价格当已持仓卖价。
3. 区分模型持有价值、无费退出毛收入、已确认 paper 费用假设下的净收入及相对成本的假设损益；真实费用未知时不补零。
4. 输出具稳定版本、身份、有效性与缺失语义；真实 launcher 能接收且本地只读消费者能复核。原交易事件 envelope、字段、顺序/序号和关系规则不变。
5. 同输入/同显式时钟下 OFF/ON 的交易 trace、订单、现金、风险、entered、vol 更新完全一致。观察错误不升级为新交易拒绝条件。

### 3.2 非目标与不可变项

不实现持有/退出/反向策略选择、反手阈值、对冲下单、第二 core、第二 Broker、撮合模型、钱包、持久恢复、通用 observer/runner、实时采样服务、统计平台或任何新网络请求。不得调用观察路径去构造 CandidateContext、take/reserve/fill/close/confirm_fill、修改现金/持仓/marks/latch/entered 或重置 EWMA。原 5 秒 tick、入场门槛/金额/来源 guard/风险/交易时钟及因果状态不变；min_secs_left 是入场规则，不能成为持仓观察末 30 秒的禁区。

默认关闭观察；后续 Design 只在现存 unsigned controlled phase1 内给显式 opt-in 和测试 OFF/ON 装配，不改变生产配置或默认普通/signed/history/replay 行为。实现可用不等于允许启动；本链仅 RFC/SPEC → Design → Implement → 独立 Validate，无新 paper/影子盘、生产 DB/schema/配置、cron/systemd、凭据操作、依赖升级、git commit/push 或外部消息授权。

## 4. 决策与方案比较

### 4.1 采用：只读旁路，不重入交易决策

既有获取和交易评估继续工作；观察使用同 tick 已有输入与已冻结读取时点的 Broker 持仓，读取当前活跃源状态，先验证再调用原纯估值。仅临时构造观察快照，既不模拟一次新买入，也不在运行中选择退出点。必须覆盖已持仓但不再位于 selected 的市场；Known/tracked 已有数据范围足够，不因覆盖需要扩充网络集合。

观察系列最多每 tick 每 market/token 一条，从首个可得正持仓开始；至轮次结束、实际结算移除持仓或原 run 停止的最先边界结束。末次终止记录不伪造终点报价；到期但未官方结算保持 pending，由原 settlement/final 证据说明，不加尾部采样/轮询。

### 4.2 采用：独立版本化观察证据，交易 v2 原样

07-005 的严格 v2 不接受任意 source 新键，且事件序号/候选关系已有消费者。观察不插入原 BTC5M_EVENT 序列，不复用 decision_id/candidate_id，也不改 accounting/NAV。逻辑记录 schema 与有效性见 SPEC §4；独立旁路的精确 framing、落盘文件名、opt-in 拼写、Rust 类型/函数位置和只读读取接口由 Design 确认，并须给真实 writer → launcher filter → 首次 write → reader 的完整路径。新名称均是待实现契约，不能冒称已有 API。

观察格式错误、容量/输出失败只使观察证据不完整或停用旁路；不修改原交易状态、错误分类、时间读取次序或原协议通过/拒绝结果。旧交易协议本身坏行仍执行既有 OUTPUT_INVALID，不以“只读”豁免。新观察通道不能放宽秘密过滤、行界或无限积压；Design 必须说明有界 I/O 与失败隔离。不承诺真实 OS 零延迟；可证明的是固定输入/显式时钟下的决策与状态非干扰，额外 I/O 不得插在候选到应用的临界路径中。

### 4.3 不采用

| 替代方案 | 不采用原因 |
|---|---|
| 将 entered 临时设 false 或把保护后移 | 会生成新候选，改变状态/次数与保护语义 |
| 每 tick 再 observe/evaluate 一次 | 会双更新 EWMA、改变 ID/检查时钟，不是只读 |
| 使用 mid 或 best bid × 库存当全量净退出值 | 忽略 spread/深度/费用，薄盘也会伪造可执行性 |
| 用另一 token 的 ask 直接替代卖出净值 | 买互补 token 与卖出既有 token 是不同交易/现金语义 |
| 输出自由 tracing 日志再事后解析 | 现存 launcher 会丢弃非协议行，且无法保证严格验证/秘密边界 |
| 新建退出模拟器、第二本账或研究优化链 | 当前目标只需观测证据，既无执行授权也无新模型需求 |

## 5. 经济与数据语义

### 5.1 原始模型与持有价值

沿当前 phase1_valuation、当前 floor/活跃 epoch 和同 tick spot/官方 strike、T=ends_at−观察时点。p_down=1−p_up，raw 表示未 Platt/后验校准，不是 quote 隐含概率。不能用未来标签/end_price 推导当时概率；换源、长 gap 和预热只读反映原 core 状态，观察自身不得触发 reset。

持有净份额 Q、原成本 K 均从 Broker 读取。模型持有价值 H=Q×p_token，模型相对成本差 H−K 只是期望兑付差，不是可变现净值或已实现 PnL。到期不调用原 digital_up 的退化极限冒充官方结算。

### 5.2 退出深度与费用

从原 token_book 得到持有 token 的 bid 价格/净份额容量，按原卖出 walk 全额覆盖 Q，保存覆盖所需最短原档前缀；最后一档保留原 size。价格/size 非有限、乱序/交叉/非法、时钟缺失或过期均不可称可执行。深度不足可保留真实前缀和 covered 数量，但 full VWAP/收入为 null，不能缩单、补零、无限外推或假成交。

已存在 paper SELL 的现金扣费规则已由代码确认：按现有 full-size walk 的 VWAP 及 fee_rate_bps 计算 paper 现金费用并从毛收入扣；库存目标始终是已有净 Q，不能再次按 BUY 扣份额得到另一个 Q。SPEC 冻结 PAPER_CASH_FEE 与 UNKNOWN 两种证据标签，前者必须有已确认 paper 语义和有效费率，且不得称真实 venue 净收入。真实 fill accounting 依赖报告的费用事实，当前观察没有这些事实，不新增获取以确认。UNKNOWN 时 gross 可有效，fee/net/PnL 保持 null；明确零费与未知严格区分。

### 5.3 缺失与独立有效性

模型、盘口/退出和费用分别给 reason/status：book 缺失不抹去仍合法的模型值；spot 缺失也不抹去独立有效的 bid 毛退出值；不因两者之一失败把整条补零。真实 source_at=null 合法但带 MISSING/RECEIPT_BOUND。持仓不存在时不能按 2 USDT 或任意常量制造退出规模。

## 6. 持久化与兼容

| 数据 | 介质 / 边界 | 生命周期与隐私 |
|---|---|---|
| 观察快照与 coverage 状态 | 现存 launcher 的同一新 run 证据目录内独立版本化旁路；精确路径由 Design 冻结 | L0 行情、L1 run/market/工程身份；exclusive-create、追加、不覆盖旧证据 |
| 原 started/events/ended/public-config | 保持原协议与真实含义 | 原保留/首次写入/秘密过滤不变，不能插入观察改变序号 |
| 工程验收结果 | data/reports/2026-11-18-btc5m-post-entry-observer/report.md；必要 evidence/ | 仅一个结果报告，无任务镜像/data/tasks；本阶段不写 |
| Broker/core | 原内存事实源，只读克隆或借用 | 无第二库存、现金、恢复账本；观察记录不能用于 resume |

无 DB/schema/索引/TTL、数据迁移、覆盖旧观察、自动删除、备份或外部上传。本地 data 被 Git 忽略不等于备份。旧 run 无旁路时明确 OBSERVATIONS_UNAVAILABLE，不补写历史、不作为完整观察样本；未知版本不能按最新语义读取。

## 7. 冻结资产与工程边界

必须保持 [final-freeze.json](../../../data/reports/2026-11-18-btc5m-joint-forward-validation/evidence/review-preparation/final-freeze.json) 中全部 13 个 files 项、prepare-v03 参数、旧 target/debug/btc_arb_phase1_history 和已保存 v1/forward binary 的原 hash。该文件是身份清单，不是可读取未来表现的许可。尤其不改 phase1_history.rs、joint/model/metrics/reference/history_input/history_performance/unified_data。phase1.rs 不在 FORWARD_FILES 中，但也只允许 Design 必要的最小只读访问增量，不改交易估值/guard 公式。

后续 Cargo build/test 必须 --offline 且显式 --target-dir 指向本报告独立 evidence 候选目录或当前 worker scratch，绝不覆盖旧 target 入口。当前 arbitrage.rs 1317 行、phase1.rs 1519 行属 1201–2400 受控增长；Design 给职责边界、少量增长理由和拆分触发，不以此开大重构。其他大文件按实测 G3 判断，优先薄旁路而非把全部 schema 塞回大文件。

本阶段只允许写本 RFC 与对应 SPEC；其余只读，不写 Design、报告、代码、测试、模板/根规则，不运行业务测试或新 paper。后续逐文件 allowlist、构建/测试命令与 G3 由 Design 落实。

## 8. 验收与风险

SPEC §5 给出必须的接受/反例矩阵。独立 Validate 必须实际执行同输入 OFF/ON 原链对拍、零额外获取/observe/交易副作用、完整 bid walk/费用/null、时钟/epoch/结束、真实 emitter→launcher→本地 reader；不能仅检查 struct 或手拼 JSON。工程验收不以收益/最优点/样本交易数为门槛。

剩余限制：模型错设和代理基差未消除；RECEIPT_BOUND 不认证真实源新鲜度；镜像不是独立 No 深度；即使 full book walk 也不证明排队/撤单/时延/真实 fill/赎回/Gas；频率为原 tick，非连续最大可退出值。观察 I/O 的真实开销需如实披露，不能用一个确定性对拍声称运行时绝对零延迟。没有新授权不启动观察验证这些外部性质。

## 9. 开放问题与交接

开放业务契约冲突：0。Design 必须决定且核实的是内部模块/读取快照时点、独立旁路 framing/文件/consumer API、显式 opt-in 位置、容量/失败隔离与具体离线命令；这些不改变本 RFC/SPEC 的业务语义。若在冻结/非干扰边界内找不到可行接缝，退回主控给最小问题，不自行松绑。

本阶段完成须两个独立实体真实存在、互引 V1.0 一致、契约可供 Design 使用。按既有 parent 链交预建 t_7e3ae26e，不新建阶段或同卡 review。Design 及独立 Validate 仍未完成，文档交付不是功能已上线。

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-11-18 | 冻结只读非干扰、同 tick 数据复用、独立观察证据、净持仓 bid 退出/费用证据与授权/冻结边界 |
