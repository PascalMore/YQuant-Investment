# DESIGN-07-006: BTC5m 持仓后只读观察最小增量设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | Draft V1.0，Design 交付候选；待实现与独立 Validate，不是功能 PASS 或运行授权 |
| 作者 | YQuant Principal / yquantprincipal |
| 创建 / 更新 | 2026-11-18，Asia/Shanghai（UTC+08:00） |
| 来源 RFC | [RFC-07-006](../../rfc/07_trading/RFC-07-006-btc5m-post-entry-observer.md) V1.0 |
| 来源 SPEC | [SPEC-07-006](../../spec/07_trading/SPEC-07-006-btc5m-post-entry-observer.md) V1.0 |
| 来源任务 / 下游 | t_7e3ae26e / 已建 Implement t_5180822f，再交独立 Validate t_9a3fa171 |
| 工作区 ROOT | /home/pascal/workspace/yquant-investment |
| 工程根 BOT | skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits，相对 ROOT |

上游实体已完整读取且互引一致：RFC SHA256 `55a6928e5e1c29a8bd371d36389a5c8e1c3a3556f694d032ea94a628f75bd2a3`；SPEC SHA256 `6216bf2d74a61971d598defbbcdaa5032718264214a6b734c959224b05b491d1`。上游阶段状态文字保留，不回写上游。本文所有新增符号、文件、参数和测试均为待实现契约，不冒称当前已有能力。

## 1. 设计摘要

只在现有 unsigned controlled phase1 中显式 opt-in。保留原 tick 获取、一次 observe、一次 evaluate、ALREADY_ENTERED、候选到唯一 Broker 的执行链、同锁重验、现金/持仓/风险、原交易协议及因果模型。观察没有交易权限，不调用完整 evaluate、克隆交易模拟或修改 entered。

最小方案：

1. 原获取和交易完成后，读取同 tick 输入、原 core 只读状态与 Broker 快照；只观察本 tick 交易前已存在、交易后仍存在的正净持仓。同 tick 新 fill 首次记录在下一原 tick，不插入 candidate→PRE_APPLY 临界路径。
2. 原 Clock 的薄代理只转发原有 now 调用并记住这些真实读数；不新增 now。即使 selected 为空，原 book 获取的 clock 仍可复用。完全没有当前有效读数时只计 coverage 缺口，不用旧时间续鲜。
3. 用继承的匿名 AF_UNIX datagram FD 作进程内本地 IPC，非阻塞、一次 send、不重试，不共用 BTC5M_EVENT 的 stdout 管道。仅增加专用小旁路，不增加网络行情请求、服务、线程池或通用队列。
4. 原 launcher 优先消费交易流；旁路独立校验、关联、首次写入独立 JSONL，再由同一严格本地 reader 读回。只读 after_event_seq 水位处理两条通道的先后竞态，不消费交易序号，不改 _EventRelations。
5. 完整性独立披露。书面承诺是固定输入/显式时钟下状态与动作非干扰，不是 OS、磁盘、CPU 的绝对零延迟。没有新运行授权，不启动 paper、影子盘或观察服务。

## 2. 现状分析与冻结边界

### 2.1 静态核实的接缝

下表路径均相对 BOT；行号是本卡所读共享树定位，不是实现后的稳定行号。

| 路径:位置 | 已有能力 | 本期只读增量 |
|---|---|---|
| src/bot/arbitrage.rs:336–368,400–456 | rescan 失败仍保留 selected attempts；逐 symbol quote/observe 一次；Known 带时钟获取 | 薄生命周期/hook；不补请求，不吞原错误 |
| 同文件:539–658 | 原 evaluate→emit→take_candidate→正 fill confirm_fill；多处 continue | 循环不改，在整个循环之外统一观察；不能只在成功分支采样 |
| src/bot/arbitrage/phase1.rs:515–544,551–664,747–752,929–944 | 纯 phase1_valuation、epoch/reset；observe/evaluate 有状态；entered 早退 | 新增极小只读活跃 key/receipt/floor 快照；原公式、早退与修订不动 |
| src/bot/runtime.rs:99–104,337–354,425–450,1232–1237 | Holding 净 Q/K、全额 walk、读持仓、tracked union、token_book | 新子模块实现同锁只读观察快照，主文件仅注册 |
| src/bot/runtime/paper.rs:271–282,312–334,518–541,676–687 | net_shares 纯 fee 等值、SELL 现金扣费、book 合法性；entries_stopped 会读交易时钟 | 复用纯函数；不得调用 entries_stopped 做额外观察检查；只读快照直接读已有 flags |
| src/bot/quoting.rs:33–88 | Known 记住市场，selected ∪ tracked 已获取 books | 不改它，不扩大 union；已离开 selected 的持仓仍可读 Known.get |
| src/models.rs:132–147 | 原 No 镜像，价格到 1e-9，size 不变 | 原函数直接复用；不是另一份独立流动性 |
| tools/predictfun/btc5m_control.py:99–108,396–459,617–760,1472–1551 | 固定 launcher、独占证据、selectors、先校验/关系再首次 write，普通日志丢弃 | 新 flag、继承 FD、优先交易流的旁路薄接线；原 stdout/stderr 失败路径不放宽 |
| src/bot/arbitrage/phase1/tests.rs:331–403；tools/predictfun/tests/test_btc5m_control.py:1235–1287 | 真实 core→Broker→Rust emitter→supervise 旧离线链 | 保留旧九事件 fixture；另建独立观察 fixture，不改旧断言 |

费用事实沿 SPEC §4.4：paper SELL 在 full walk 的 VWAP 上扣现金；fills.rs 的实际成交费用仍须报告事实，当前观察没有这些事实。REST source_at 仍真实缺失，RECEIPT_BOUND 不认证源端新鲜度。

### 2.2 共享树、冻结与身份

本卡只读 Git 观察：ROOT main HEAD=`523fc1a0cb14f6eb3d7bfcd4122f56d06ee975d7`；BOT main HEAD=`0250eb993958cc2f47e3b6e81e008a59a02b565f`。BOT 开工 dirty 为 arbitrage.rs 仅已有 phase1_history 注册、phase1.rs 已有纯估值提取；两个 phase1_history 文件 untracked。ROOT 既有 infra/strategy dirty 和 06-003 文档/脚本、07-006 RFC/SPEC 均保留，不归本卡。不 fetch，不把本地 origin 缓存说成最新远端。

[final-freeze.json](../../../data/reports/2026-11-18-btc5m-joint-forward-validation/evidence/review-preparation/final-freeze.json) 是冻结身份清单，全部 files 项均只读，包括其中 forward binary；parameters 指向的 prepare-v03/parameters.json 原 hash 不变。另保护 BOT/target/debug/btc_arb_phase1_history 与同主题 evidence/main-implementation/btc_arb_phase1_history-v1。不得更改 phase1_history.rs、其 bin、joint/model/metrics/reference/history_input/history_performance/unified_data 或冻结未来表现；不运行 99 日、不读取未来结果。本文已读取清单，未构建/修改这些文件；Implement/Validate 开收工各核完整清单及额外旧 binary SHA，不只看 HEAD。

## 3. 方案设计

### 3.1 精确 allowlist 与 G3

本卡唯一工程产物为本文。下表仅供后续 Implement，在 ROOT/BOT 的上述展开路径内按职责实施必要 delta，不授权整个目录，不要求为用满白名单而改文件。

| BOT 相对路径 | 新建/修改及严格职责 |
|---|---|
| src/bot/arbitrage/observer.rs | 新建：具体 post-entry 类型、输入验证、纯估值构建、TickClock、系列生命周期、有限 datagram writer；不是策略/执行器 |
| src/bot/arbitrage/observer/tests.rs | 新建 cfg(test)：数值/状态非干扰、fake acquisition、真实发射 fixture 与输出故障；所有新 Rust 功能测试集中此处 |
| src/bot/arbitrage.rs | 修改：注册 observer；RoundTaker 可选 observer；现存 run/tick/rescan-failure/trade 外围薄接线；极小 cfg(test) spot 获取替身与构造器适配；原循环和候选路径不变 |
| src/bot/arbitrage/phase1.rs | 修改：新增 Phase1ObservationState 与 phase1_observation_state(&self, symbol)；只读 key、last_receive、last_source、revision、last_phase1_check、有效 floor；不改原交易/估值函数 |
| src/bot/runtime/observer.rs | 新建：Broker 同锁只读 post_entry_snapshot；极小 paper 时间测试接缝；不发事件、不执行、不读 now 判断 stop |
| src/bot/runtime.rs | 修改仅注册 observer 子模块；既有 walk/token_book/drive/资金算法不变 |
| src/bot/runtime/paper.rs | 修改仅将现有三个 Utc::now 调用委托 runtime::observer::paper_now，以供 cfg(test) 固定时间；生产仍各原位置调用 Utc::now 一次，无新增 clock、事件字段或资金逻辑 |
| src/bot/arbitrage/phase1/tests.rs | 修改仅既有 RoundTaker 字面构造补 observer=None / 新 test seam=None；旧测试/fixture/断言不删改、不再塞新功能大段测试 |
| tools/predictfun/btc5m_observer.py | 新建：具体 /1 wire 验证、只读交易关联索引、接收/存储/coverage、read_observations API；无新运行 CLI/研究平台 |
| tools/predictfun/tests/test_btc5m_observer.py | 新建：严格 consumer/首次 write/故障/实际 Rust 子进程→原 launcher→reader；包含 Decimal 独立算术复核 |
| tools/predictfun/btc5m_control.py | 修改：--post-entry-observer、socketpair 装配、supervise 可选旁路薄接线；public_identity 加本期新增源码/测试；原交易验证/relations/accounting 不改 |
| tools/predictfun/tests/test_btc5m_control.py | 修改仅新 flag 默认/拒绝/身份清单适配，及既有 Cargo 子进程显式隔离 --target-dir；保留所有旧协议/首次写入/秘密/父进程丢失断言 |

无 UI。禁止修改 Cargo.toml/Cargo.lock/依赖、src/main.rs/config.rs/models.rs/service 目录、quoting.rs、live/fills adapter、history/replay、任何配置/凭据、旧三层契约/模板/根规则/旧报告、其他项目/profile；不变更 gitlink，不清理共享 dirty。测试可在当前 profile scratch 写专用临时输入；最终证据仅本报告 evidence 新叶。若需要白名单之外源码或不能在冻结边界实现，应先 REVISE，不以编译困难扩权。

G3 实测：arbitrage.rs 1317、phase1.rs 1519、runtime.rs 2369、paper.rs 2372、btc5m_control.py 1570、test_btc5m_control.py 1542、phase1/tests.rs 2208 行。以上均 1201–2400 受控范围。职责及增长理由：父文件仅生命周期/注册/只读访问/测试适配，复杂 schema/计算/transport/reader/新测试放新小文件。runtime/paper 主体不提取、不大重构；paper 的三个替换不扩张文件。新增文件以单一 observer 职责内聚，目标各不超1200行。若父文件因本期接线将越2400或新模块将越1200，停止增长并提交具体职责/最小拆分修订给主控，不默默跨档。本期独立 Validate 同时检查 G3 与 delta，下一次实质扩展若需向父文件追加算法或再加协议即触发重新拆分评估。

### 3.2 装配、hook 与时钟

#### 3.2.1 默认关闭与实际入口

只向既有 btc5m_control.build_parser 增加 action=store_true 的 --post-entry-observer；默认 false，signed 携该 flag 在任何凭据读取/启动前按 CONTROLLED_MODE/args 拒绝。无路径/可执行文件/采样周期/策略新参数，不改 public-config/started/ended 原 schema。

run 在原证据目录已创建后，仅 ON 建 socket.socketpair(AF_UNIX, SOCK_DGRAM)，双方 nonblocking。child_environment 仍不继承任意父变量；ON 由 launcher 自己插入 BTC5M_POST_ENTRY_FD=<子端FD>，Popen 的 pass_fds 仅额外放行这个 FD，close_fds=True；原 stdin/stdout/stderr 如旧。父立即关闭自己持有的子端。OFF 不建 socket、不传 FD、不建观察文件，Popen 形状保持旧行为。父输入的同名变量不继承，不能成为 opt-in。

arbitrage::run 仅当 !broker.is_live、controlled_run.mode=UnsignedPaper、broker.is_phase1 且继承 FD 有效时装 PostEntryObserver；普通/signed/history/replay 不装。无 flag 不读该内部 FD 以外资源，不读 secrets。附接 FD 要验证十进制且>=3、有效且是已连接 AF_UNIX/SOCK_DGRAM，验证后才接管 OwnedFd/UnixDatagram 所有权；无效/缺失仅旁路不可用，不 panic/关闭其他 FD/改变 run Result。Linux 的必要 fcntl/getsockopt 窄 FFI 可封装在 observer.rs，并记录 SAFETY 与唯一所有权；不新增依赖。此 IPC 无文件 socket、无网络地址、无外部请求。生命周期内最多一个端点，没有后台 worker 或重连。

#### 3.2.2 首次观察与快照点

冻结选择：同 tick 新 fill 不纳入。本 tick 开始进入 phase1 获取前，ON 读取 Broker 正净持仓 token 集合作为 eligibility；原 tick 不因新 fill 改动这个集合。整个 trade_phase1 原循环完成后再读取同锁 post_entry_snapshot，以其当前实际 Q/K 为准；只对 eligibility 中仍正持仓及已开启需终止的系列构建记录。第一次正 fill 的 tick 不生成 ACTIVE，下一原 tick 才是首个定义的可用点。若 fill 后没有下一 tick，coverage 与原 fill 对照报 FIRST_SAMPLE_MISSING，不伪完整。

Broker::post_entry_snapshot(&self, tracked_keys) 在一次 state.lock 内只克隆：所需 Holding、paper.traded 中的首 fill 官方身份、对应 settlements/applied_results 的存在/状态、已有 halted/loss_latched/entry_stop_reason/output_failed bool、当前 phase1.event_seq 原子值。锁外返回不可变 DTO，不返回 &mut、State、候选或现金 API。它不调用 controlled_stopped/phase1_entries_stopped、run.stopped 或任何 now，不刷新 mark/risk/latch；不把读取快照变成新风控判断。tracking 只是身份和终止状态，不是第二份 Q/K/资金账。

post-entry 构建放在 tick_phase1 原 trade_phase1 返回后、原 failed→DATA_INCOMPLETE 返回前；保留原 Result 与 failed 逻辑。即使 quote/book 缺失也构建失败原因或计缺口，不只保存成功样本。trade 返回 Err 或中途 clock Err 时，外围收尾只记观察不可用/缺口，再原样返回 Err，不重新调用交易方法。rescan 失败分支仍只执行原来一次空输入 trade_phase1，在其外围同样记录缺输入；不改 self.rounds、不补 fetch。

每个完整 phase1 tick 一个 TickClock 包装原 Arc<dyn Clock>：每次 now 恰好调用原 inner.now 一次，原样返回 Ok/Err；只为观察保存本次最后成功 CheckTime、是否发生失败/时钟回退。原调用者和次数/顺序不变。quote_observed、Known.observe_with_clock、trade_phase1 接原本同一个 clock 的代理；Broker 内部重验仍使用原 clock，不改之。Clock 代理不引入新的时钟源，不在 observer 中调用 now。OFF 不构建代理；ON 的结果/错误传递必须与 OFF 逐调用一致。

观察时点采用本 tick 已成功读取的最后 CheckTime，不取请求/写盘时刻，不用 max 合成或跳过回退；若本 tick 无可用读数、末次 clock 失败无法证明当前时点，或读数出界，则不编码正常样本，计 CLOCK_UNAVAILABLE 缺口。单独 acquired book 的 received_at/elapsed 来自原获取 clock：selected 为空仍能经代理获得它，因此不需额外 trade/evaluate，也不拿 scan_at（获取前）冒充当前时点。测试 fake acquisition 必须同样调用传入 clock，不手造未发生的“最后读数”。

observe_phase1 的原调用结果旁路保留到本 tick 的局部 accepted_by_symbol；不改变分支/quotes.insert。新纯 accessor 返回真实 key/receipt/source/revision/floor，不触发 observe/reset/bump。只在本 tick 原 observe 返回 Ok、key/receipt 与实际 quote 完全相同、当前时钟/market 合法、状态已暖时调用 phase1_valuation。重复/被拒的 quote 即使碰巧等于旧 last_receive，也不能借旧暖状态估值。观察不能调用 refresh_phase1_market 或 evaluate。

#### 3.2.3 原交易链与生命周期

原链保持：获取→原 observe→原 mark→原 evaluate/emit→原 candidate→原 PRE_SUBMIT/reserve/PRE_APPLY/fill→原 entered；观察的 CPU/序列化/send 仅在整个交易循环之后。没有 observer 计算或 I/O 插入候选到应用之间，也不在两个 selected 市场交易之间插入观察。

观察系列按 (run_id,market_id,token) 管理，每 tick 最多一条，身份稳定排序后输出。含已持仓不在 selected 的市场：用 broker 首 fill 身份与 Known.get 的已知事实对照，只读原 quotes/books。不得为它 refresh/evaluate/新增 symbol 请求。缺 Known/事实冲突时 MARKET_INVALID，缺已有输入时相应 MISSING，不读取缓存 book/quote 续鲜。

终止优先级沿 SPEC：SETTLED > RUN_STOPPED > ROUND_ENDED。同锁快照确认原官方移仓才 SETTLED；flags 已停止则 RUN_STOPPED；当前真实 CheckTime 的 T≤0 才 ROUND_ENDED。终止记录不计算模型、VWAP、退出金额、hold value，持仓已移除则 Q/K=null。圆满到期但 pending 不动库存，后续原 settlement/final 可只读 join，不重新采样。末30秒仍 ACTIVE，不借入场 min_secs_left 禁止观察。

arbitrage::run 在原 drive(&mut bot,&ctx).await 返回后，仅一次 best-effort observer.finish：不延长原 drive/cleanup/tail，不取价、不调用 core 或新的 now。已结束系列不再出 terminal。若停止/结算发生在 tick 外且没有同时刻可复用 CheckTime，不把上一 tick 时间与当前移仓拼成终止样本：END 的 series 终止通知携真实原因、terminal_observation_seq=null，CLOCK_UNAVAILABLE/TERMINAL_MISSING 导致 INCOMPLETE。这是 SPEC §4.5/4.6 允许的无法生成终止样本的诚实表达，不是补采样许可；正常 tick 已终止的系列不受影响。进程硬退出/取消无法 finish 则无 END，reader 同样不完整。该限制不阻塞原资金 cleanup，也不冒称已完整覆盖停止瞬间。

### 3.3 纯值构建、字段与计算

新增核心内部 API（签名细节可按 Rust 借用调整，权限和职责不可改变）：

- DecisionCore::phase1_observation_state(&self, symbol) -> Phase1ObservationState：返回上节只读摘要，含当前有效 floor（调用现有 floor，不用任意 cfg/research floor）。
- Broker::post_entry_snapshot(&self, tracked_keys) -> BrokerObservationSnapshot：同锁读事实，after_event_seq 是观察时原事件已分配的水位，只 load 不 fetch_add。
- PostEntryObserver::after_tick(&mut self, &DecisionCore, tick_inputs, eligibility, broker_snapshot)：&mut 仅限自身 seq/coverage/系列；不接可写 core 或 CandidateContext。
- build_observation(...) -> Result<PostEntryObservation, ObservationEncodingFailure>：纯函数，失败只有固定枚举，不返回/记录原始错误、HTTP 或秘密。
- runtime::observer::paper_now()：生产仅 Utc::now；cfg(test) 可冻结三个既有直接 UTC 读数以精确 OFF/ON 对拍，不可从环境/公共参数控制。

#### 3.3.1 完整 flat record schema

SAMPLE.record 的完整键集合、逐字段类型/null/枚举以 SPEC §4.5 表为唯一规范，本文采用 flat 同名 wire，不改名/分组/漏键。以下列表是实现必须建立的严格键 allowlist（与 SPEC 逐键核对），不是自由字段袋：

```text
schema_version run_id observation_seq market_id token sample_state
observed_at observed_elapsed_ms starts_at ends_at secs_left strike
position_net_shares position_cost prediction_source actual_pair source_state
source_epoch reset_reason settlement_provider spot spot_clock book_clock samples
sigma_raw sigma p_up p_down model_reason up_bid up_ask down_bid down_ask
down_quote_basis exit_bid_levels exit_covered_shares exit_depth_complete
exit_vwap exit_gross_income exit_reason fee_basis fee_rate_bps exit_fee
exit_net_income exit_pnl_vs_cost model_hold_value model_hold_surplus
```

schema_version=btc5m-post-entry-observer/1；run_id 沿原 RUN_ID_PATTERN；market_id/token 为原1..78位十进制 string，不修复或将未知 token 默认映射 No。observed_at 用现有 format_millis，UTC `...SS.sssZ`；elapsed 非负且<=i64::MAX，seq/epoch positive integer（bool不能冒充）。spot_clock/book_clock 原对象完整键为 source_at/source_time_status/freshness_basis/request_at/received_at/request_elapsed_ms/received_elapsed_ms，复用 serialize_millis；保留真实 source_at=null。

所有键存在；未知键递归拒绝，包括所有 envelope/clock/level/coverage。enum 集合、错误主原因顺序、模型/退出/fee 独立有效性沿 SPEC §4.7，不给通用 error/detail/text。数值非有限须在 serialize 前显式检查，不能靠 serde NaN→null 掩盖。非法原输入数值字段为合法 null+对应域原因，不能继续参与运算；无法构造合法记录则计编码缺口。source/pair 非当前合法组合时 INPUT_INVALID；不输出未允许字符串。

模型域先 terminal、官方身份/固定strike/300秒及availability、缺输入、价格/source格式、clock一致/未来/回退、span/age、active key/receipt接受匹配、20returns暖机，再用原 phase1_valuation(symbol,spot,strike,T,active_floor)。p_down=1−p_up，H=Q×p_token，H−K 只为期望兑付差；book 或 fee 失败不抹除合法模型。模型不调用 recheck（它接受 candidate 且含入场规则），不重写 digital_up/EWMA。T 按官方结束减 observed_at 毫秒/1000；非正不估值。所有 threshold 与等号沿 SPEC：request_span≤5000ms、age≤10000ms、gap=300秒不reset，>300秒原路径reset。

#### 3.3.2 bid 深度与费用复用

同锁实际 Q>0、K>=0 均有限且 token 精确归属。Yes book 正常非空双边的数值/顺序/交叉合法性复用原 mid_of 的判定，但绝不使用其 mid 当退出价。合法空 bids 特判 NO_BID/covered=0/complete=false；有 bid 缺 ask 或非法/乱序/交叉为 INPUT_INVALID。空bid判定前仍检查实际存在的 levels/ask 数值、clock，不把非法单边数据称正常空bid。book时钟独立验证，不要求spot有效才能计算 gross。

Up touch 用 Yes，Down 由原 mirrored/token_book，down_quote_basis=MIRRORED_YES_BOOK；调用 token_book 前验证 token。持有 token 的 bids 按原高到低次序构建最短覆盖前缀；末档保留原 size。每档消费 min(remaining,size)，停止条件与 walk 一致 remaining<=1e-9；covered=min(Q,实际消费总份额)，不因该原 EPS 把 covered 强写Q。完整性以原 walk 的 EPS 语义为准并披露其容差，不另设更大容差/截断规模。

全仓 walk 直接调用 runtime::walk(bids,Side::Sell,Q,0.0)：0.0 仅是计算全部可见 bids 的下界，不是提交新限价/新策略。walk 原 clean 到 1e-6；reader 用 Decimal 独立复核同舍入，不能拿未舍入平均值以1e-7容差硬比而误拒原输出。Q<=原EPS的极端输入若 walk产生不在(0,1)的0，标 INPUT_INVALID/full金额null，不把0作为可执行退出价；不改 walk。保留该EPS边界反例。

深度不足保留合法真实前缀/covered，complete=false，exit_vwap/gross/fee/net/PnL全null；stale/非法为complete=null，covered/前缀null（可保留合法touch作为披露）。超过任一输入侧1000档、覆盖前缀>1000或整帧64KiB时不截断伪完整：降为 exit_reason=OBSERVATION_LIMIT，depth/covered/complete/full货币值null，仍可保留合法模型；缩减后的标量记录仍超限则整条不发送并计编码缺口。对full=false，reader不能从前缀的部分均价自造full值。

PAPER_CASH_FEE 仅当前 unsigned controlled 公共 fee_model=paper_net_shares、同官方有效bps、原规则已确认时给出，零bps有效；其他/未知为 UNKNOWN 且bps/fee/net/PnL=null。fee已知且完整walk时，复用 paper::net_shares(Q,VWAP,bps) 的第二返回值F，明确丢弃其BUY净份额返回值；Q绝不再扣份额。G=Q×VWAP，N=G−F，假设exit_pnl=N−K；H=Q×p_token及H−K单独命名。无需提取/改paper费用公式，不调用apply_sell，不修改marks/NAV/realized。reader independently重算并标paper假设，不称真实venue到账/fill/Gas。

### 3.4 物理 wire、持久化与消费者

#### 3.4.1 专用 datagram framing

每个 datagram 为恰好一条 UTF-8 JSON 对象加一个末尾 `\n`；不允许内嵌第二行/尾随内容，含 framing 总长<=65536 bytes；接收缓冲65537检测超限或用recvmsg的MSG_TRUNC检测，不能先截断再json.loads。没有 BTC5M_EVENT 前缀，绝不发送到stdout/stderr。大小检查在producer序列化和parent首次写入前都执行。单次 send 全发或失败；EAGAIN/ENOBUFS/EPIPE/其他错误只计send失败并可停用，不retry/sleep/await/退回交易输出。

严格 envelope 按 kind 分版：

| kind | 必有且仅有的键 / 内容 |
|---|---|
| READY | wire_version, kind, run_id；wire_version固定 btc5m-post-entry-wire/1，run_id精确本run |
| SAMPLE | wire_version, kind, run_id, after_event_seq, record；record为§3.3完整flat对象，run_id相同；after_event_seq为>=0整数，只读原交易水位 |
| END | wire_version, kind, run_id, producer；producer为下述完整对象，不包含raw错误 |

READY在附接成功后一次尝试，END在finish一次尝试；二者不消费observation_seq。不另造 heartbeat/status循环。READY/END重复、未知kind/version或END后SAMPLE为旁路坏帧。总样本序号从1连续分配给每个应输出的系列/tick尝试（包括无法编码/发送的尝试）；下一成功样本因此会暴露gap，不重复发同seq。READY丢失或END丢失一律不能称COMPLETE。

END.producer 必有且仅有：attempted_samples, encoded_samples, sent_samples, dropped_samples, clock_unavailable_samples, encode_failed_samples, send_failed_samples, last_observation_seq, disabled_reason, series。除disabled_reason和series外均非负integer，last_observation_seq=attempted_samples；dropped=clock_unavailable+encode_failed+send_failed；encoded=sent+send_failed；attempted=sent+dropped。计数指SAMPLE，不含READY/END；END的成功与否由parent是否收到判断，producer不能提前宣称END送达。disabled_reason为null或TRANSPORT_INVALID/TRANSPORT_FAILED/OBSERVATION_LIMIT/ENCODING_FAILED之一，不含OS错误原文。

series为最多1000项数组，每项仅market_id,token,terminal_state,terminal_observation_seq。身份唯一；terminal_state为null/ROUND_ENDED/SETTLED/RUN_STOPPED；terminal_observation_seq为正整数或null。只保留身份/终止元数据，不存第二份Q/K；terminal记录发送失败/无时钟时seq=null（相应attempt仍计入drop）。未终止则两者null。超系列容量停用旁路并报OBSERVATION_LIMIT，不改交易。全END也必须<=64KiB；无法发送则parent缺END为INCOMPLETE，不删系列伪完整。

#### 3.4.2 首次 write 前的跨通道关联

新模块 ObserverReceiver 从supervise接收专用socket，不从自由tracing捞JSON。supervise保留原事件验证→_EventRelations.accept→events.write/flush顺序；仅在原事件成功write后调用receiver.note_trade_event(event)，构建只读工程关联索引：原EVALUATE的market/token/固定时间strike身份、正BUY fill的seq/Q/K/fee事实、settlement的seq和final引用。只记原证据引用/关系，不累计新现金或可交易账本，不更改relations/previous/final。

SAMPLE.after_event_seq 可能尚未被父端处理（stdout与datagram无全局次序）。先严格语法/秘密/字段/公式校验，再仅在parent已成功消费至少该水位时做as-of关联并write。水位未到时保留单一有界FIFO：最多16帧且合计<=1MiB；满则丢当前帧并标RELATION_BUFFER_LIMIT，不阻塞/重试子进程。每处理一个原交易事件或一次旁路就绪轮尝试推进FIFO；不按收益排序。seq顺序不能因后帧易验证而越过前帧偷偷重排。

索引按原交易seq判断as-of：fill_seq<=after_event_seq，ACTIVE须尚无seq<=水位的settlement；Q/K与该单次正BUY净Q/原cost匹配，token属该market，固定strike/300秒身份一致；不能因父已经读到更晚settlement而误拒先前ACTIVE。ROUND_ENDED/RUN_STOPPED保有Q时仍与原fill匹配；SETTLED须原settlement已在水位内且Q/K/null正确。若原事件出现本期没有实施的SELL/库存变更，观察关联给UNSUPPORTED_POSITION_TRANSITION，不猜测重建第二账本，交易流仍执行旧规则。无正fill/未知token/身份冲突/无依据Q/K绝不write。

终止时FIFO中仍无匹配水位/缺原fill的帧拒绝并报RELATION_UNRESOLVED。正常EOF或进程退出不能让观察socket使原监督loop无限等待：loop存活条件仍以原stdout/stderr与process为准，不把永久无EOF的datagram加入其存活谓词。原交易流每个select turn优先完整处理原可读chunk，然后至多接收/校验/写入一条观察帧；结束时只在原剩余cleanup预算内做有限drain，未读数量若不知为unknown，不加新budget。原旧坏行仍stop()/OUTPUT_INVALID，不识别成可忽略观察。

#### 3.4.3 存储与coverage完整schema

| 对象（同一个新run目录） | 触发 / 字段 / 校验 | 失败与兼容 |
|---|---|---|
| post-entry-observations.jsonl | ON时ObserverReceiver独占x创建；仅§3.3严格record，首次write前完成schema/公式/身份/水位关联；序列按producer原顺序追加一行并flush | 旁路独立catch，不进入原supervise外层stop；部分写入保留字节、禁重试/覆盖；reader拒绝尾坏行 |
| post-entry-coverage.json | ON时run的finally在原ended处理之外best-effort独占x写一次；下述完整对象 | 写失败不改变facts/final/exit；缺文件reader为INCOMPLETE或UNAVAILABLE，不能自动写回 |
| events.jsonl/started.json/ended.json/public-config.json | 原代码/验证/真实含义不变，无观察键/事件 | OFF/ON原语义相同；旧证据不补写 |
| 工程结果 | 仅data/reports/2026-11-18-btc5m-post-entry-observer/report.md，必要evidence/新叶 | 后续Implement/Validate记录，本文不创建报告 |

coverage必有且仅有：schema_version,run_id,enabled,transport,status,ready_received,end_received,received_samples,written_samples,rejected_samples,unwritten_samples,sequence_gaps,producer,reasons。

- schema_version=btc5m-post-entry-coverage/1；enabled固定true；transport固定UNIX_DGRAM；status为COMPLETE/INCOMPLETE；ready_received/end_received为bool。
- received_samples为可识别SAMPLE帧数；written_samples为完整成功write并flush的记录数；rejected_samples为验证/关联拒绝数；unwritten_samples为其余识别后未能完整写入数，包括容量丢弃/旁路写故障。恒等received=written+rejected+unwritten；无法识别kind的坏帧仅reasons记INVALID_FRAME，不编入精确SAMPLE总数。
- sequence_gaps为缺失observation_seq数量；可由合法END.last_observation_seq与收到且语法合法的不同seq集合核算，END缺失/无效则null而非0；重复/倒序即失败，不只用集合掩盖。producer为合法END.producer或null，不信任未校验对象。
- reasons为去重固定枚举数组：TRANSPORT_SETUP_FAILED, READY_MISSING, END_MISSING, INVALID_FRAME, SEQUENCE_INVALID, SEQUENCE_GAP, RELATION_INVALID, RELATION_UNRESOLVED, RELATION_BUFFER_LIMIT, UNSUPPORTED_POSITION_TRANSITION, WRITE_FAILED, COVERAGE_WRITE_FAILED, PRODUCER_DROPPED, CLOCK_UNAVAILABLE, FIRST_SAMPLE_MISSING, TERMINAL_MISSING, OBSERVATION_LIMIT, TRADING_EVIDENCE_INVALID, TRUNCATED_OUTPUT。无原始路径/异常/HTTP detail；无法写出coverage时COVERAGE_WRITE_FAILED不能自证落盘，由reader报缺文件。
- COMPLETE的必要条件：READY/END有效且唯一、producer无drop/disabled、收写总数与sent一致、seq从1至last连续且无坏帧、所有原正fill系列自下一可用tick起有观察且已terminal，终止seq可读回，关联/语义/文件均合法。零fill时允许READY+合法END+空series的完整空集合，不捏造ACTIVE。交易finalized或exit0不能替代这些条件。

文件append不做恢复、TTL、覆盖、清理、迁移或上传，无DB。字段仅L0行情/L1工程身份；schema重建无自由字符串，沿原_unique_object的重复/秘密键拒绝意图，在新模块实现等价窄helper，不修改旧交易secret检查。错误只存上述固定枚举。OFF零观察文件；旧run无旁路文件reader返回OBSERVATIONS_UNAVAILABLE，不能当complete。ON设置socket/文件失败仍继续原交易；若连coverage也写不了就如实缺证，不能承诺故障时一定有状态文件。

#### 3.4.4 实际只读 reader API

btc5m_observer.py 提供 read_observations(run_directory: Path) -> ObservationReadResult（Python dataclass或严格同键dict均可），返回仅schema_version,run_id,status,records,coverage,reasons；schema_version固定btc5m-post-entry-read/1，status为COMPLETE/INCOMPLETE/OBSERVATIONS_UNAVAILABLE。records为已严格验证的record列表，coverage为严格对象或null，reasons为固定枚举。API只读，不自动创建文件/补键/ffill/插值/回填；未知版本/非法记录不变成合法null。

reader先只读原started/public-config/events/ended，用旧validate_event与_EventRelations及原adjacent accounting规则验证原交易证据，再由新索引验证观察as-of关系和coverage，不把观察送入旧relations。为避免循环import，新模块仅在reader入口局部导入btc5m_control；旧control在runtime装配时局部导入observer，不在模块初始化互相导入。不能因新reader而提取/重写旧交易校验；原相邻账务规则可在本地只读循环等价复核并有旧反例对拍。

原交易坏行使reader返回INCOMPLETE/TRADING_EVIDENCE_INVALID，不输出“已认证”records；原监督仍按旧OUTPUT_INVALID。旁路缺/坏/截断只影响观察status，原run事实不改。reader实际被新离线集成测试调用，读取launcher真实写出的文件和coverage，不只测试手拼JSON。未来研究必须先看status/reason/fee_basis，本文不新增收益汇总/最佳点选择功能。

## 4. 实现顺序

1. 先建立固定输入、显式Clock序列及paper直接UTC的cfg(test)固定接缝；为OFF/ON原完整trace/状态与无额外请求写失败测试。保留旧fixture输出与所有旧断言。
2. 新只读Broker/core快照与observer纯构建；原walk/mirror/fee复用，加入各独立null/reason与末30秒/到期/净份额边界。
3. 加post-trade薄hook/下一tick首样本/selected外覆盖；加继承datagram/READY/END与有限失败计数，不做任何运行配置变更。
4. 新严格receiver/coverage/reader接原launcher，解决双通道as-of水位竞态；随后实际libtest子进程经原run/supervise→文件→reader验证。
5. 净化delta：移除重复模型/收费/执行代码、raw错误、自发新参数/重试；完成冻结身份、allowlist、G3、原回归与A-001–022证据交接。不得以写完文档/一个helper测试代替全链。

## 5. 测试策略与可执行命令

### 5.1 真实fixture与非干扰设计

新Rust测试放observer/tests.rs。新增精确fixture名 bot::arbitrage::observer::tests::post_entry_protocol_consumer_fixture（待实现），不新增生产bin。其body必须调用真实RoundTaker tick_phase1/Strategy.tick获取链、原observe/evaluate/trade/Broker、原emitter和新send；使用cfg(test)固定spot transport及MarketData fake，不mock这些被测方法。Fake记录请求symbol/ids/次数，未声明请求/凭据读取即panic；原spot生产调用封装成薄read_observed_quote，test字段仅替代外部获取结果/错误和既有clock读数，不替代observe/core。Known的selected/tracked union必须真实执行。

OFF/ON独立相同初始状态、相同每次CheckTime/输入序列。paper_now测试接缝固定三个原直接UTC调用，使事件event_time、mark_time与Holding.opened_at也精确相同；不从trace删除时间/ID/reason/字段求相等。仅两run的run_id可预声明一对一映射；数值abs或rel≤1e-9，序号/枚举/次数/调用顺序精确相等。原事件完整逐项比较，Broker现金/available/reserved/holdings/cost/fees/realized/risk/loss/halt/output_failed、core entered/samples/sigma/epoch/revision/next_decision/last_check及调用计数均比较。observe路径不能有CandidateContext/new candidate；已有tick入场次数和持仓后ALREADY_ENTERED保持。

新Python集成通过原control.run的既有popen/check_paths/environment测试接缝，只把原固定外部child替换为隔离target里的libtest精确fixture进程，传真实pass_fds、stdin/stdout/stderr；不新增公共任意command开关，不执行生产run btc-arb。原supervise、原事件emitter、新Rustwriter、socket接收、首次write和reader不得mock。stdin/信号/子进程退出仍真实；对spy仅观察实际write或注入OS错误，不替代验证方法。必须包括datagram先于fill可读、父先读到settlement、socket容量/断开、旁路坏帧/写失败但交易trace不变的情形。

### 5.2 A-001–022 逐项落地

| SPEC项 | 必需真实测试与证据 |
|---|---|
| A-001–003 | OFF/ON完整trace/状态/Clock调用对拍，原持仓ALREADY_ENTERED，候选/预留/close额外0；fake获取请求集合完全相同、rescan/quote/book失败不补请求 |
| A-004–007 | 同core phase1_valuation raw值；19/20returns、同源/切换/回切、gap=300/>300；本tick拒绝重复quote；receipt-only与source时钟；5s/10s含等号及±边界；倒序/未来/回退/缺clock |
| A-008–010 | spot缺但gross可用/book缺但model可用；Up/Down不同真实净Q/K；未知token拒绝；原mirrored舍入和bid方向，不用mid/ask/另一token买价 |
| A-011–014 | 多档bid、末档原size、exact/跨档/EPS附近/Q<=EPS；空bid/缺ask/乱序/交叉/非有限/薄盘；原walk clean到1e-6的Decimal复核；bps0/正费/VWAP两侧/UNKNOWN，State完全不变 |
| A-015–018 | H与N分开复算；已持仓离selected、selected为空仍原Known复用；首fill下一tick、零fill不出ACTIVE；末30秒/到期/pending/settled/runstop优先级；tick外无clock终止为明确INCOMPLETE，无延长cleanup |
| A-019 | 真实Rust fixture进程→原launcher run/supervise→schema/关系校验后首写→新reader；model/深度/fee/reason真实读回，与旧event stream对拍 |
| A-020–021 | duplicate JSON key、bool冒数、版本/漏键/未知键/错run/token/Q/K/null/公式/seq/drop/截断、跨通道关联竞态；1000档/64KiB含framing边界、16帧/1MiB满、READY/END丢失、写失败；旁路不stop原交易，旧协议坏行仍OUTPUT_INVALID |
| A-022 | 默认OFF无FD/观察文件；signed拒flag及普通/history/replay默认回归；旧秘密/首次write/父丢失/deadline/官方去重/费用测试；逐项冻结hash/G3/scope delta |

计数/测试名以实际执行返回为准，不承诺现有测试总数。上表待实现、待独立Validate，并非已通过。

### 5.3 cwd、隔离构建与实际argv

以下均为下游执行命令，本Design阶段不执行构建或业务测试。BOT cwd为 ROOT/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits。

候选target绝对路径固定为 ROOT/data/reports/2026-11-18-btc5m-post-entry-observer/evidence/implement-r1/cargo-target；独立Validate改用同主题evidence/validate-r1/cargo-target，不覆盖既有叶。若这些叶已存在来自先前尝试，先读回并在Kanban声明新叶身份，不覆盖其证据。命令中ROOT须展开成下面绝对路径，不能默认target：

```text
cargo test --offline --locked --target-dir /home/pascal/workspace/yquant-investment/data/reports/2026-11-18-btc5m-post-entry-observer/evidence/implement-r1/cargo-target --lib bot::arbitrage::observer::tests -- --test-threads=1
cargo test --offline --locked --target-dir /home/pascal/workspace/yquant-investment/data/reports/2026-11-18-btc5m-post-entry-observer/evidence/implement-r1/cargo-target --lib bot::arbitrage::phase1::tests -- --test-threads=1
cargo test --offline --locked --target-dir /home/pascal/workspace/yquant-investment/data/reports/2026-11-18-btc5m-post-entry-observer/evidence/implement-r1/cargo-target --lib bot::runtime::paper::tests -- --test-threads=1
cargo test --offline --locked --target-dir /home/pascal/workspace/yquant-investment/data/reports/2026-11-18-btc5m-post-entry-observer/evidence/implement-r1/cargo-target --lib bot::arbitrage::replay::tests -- --test-threads=1
cargo build --offline --locked --target-dir /home/pascal/workspace/yquant-investment/data/reports/2026-11-18-btc5m-post-entry-observer/evidence/implement-r1/cargo-target --bin polymarket-toolkits
```

Python cwd同BOT，使用ROOT/.venv，不安装依赖；唯一给测试子进程的公开构建位置环境变量如下（非凭据、非配置/运行授权）。测试中每一条Cargo子进程argv也必须显式插入--offline --locked --target-dir及该值，不能仅靠环境变量隐式路由；沿原离线fixture方式提取libtest产物，不shell拼命令/选第一个glob产物。

```text
env CARGO_TARGET_DIR=/home/pascal/workspace/yquant-investment/data/reports/2026-11-18-btc5m-post-entry-observer/evidence/implement-r1/cargo-target /home/pascal/workspace/yquant-investment/.venv/bin/python -B -m pytest tools/predictfun/tests/test_btc5m_observer.py tools/predictfun/tests/test_btc5m_control.py
```

旧Python各Cargo调用已核在test_btc5m_control.py，允许仅补显式target隔离，不改变其测试选择/断言。新fixture精确测试argv为对应target/debug/deps下通过Cargo产物身份确认的libtest文件加 `bot::arbitrage::observer::tests::post_entry_protocol_consumer_fixture --exact --nocapture --test-threads=1`；进程由上述pytest原run的popen测试adapter启动，不能改check_paths生产固定入口或把候选复制回target/debug。

所有命令单用途、显式cwd、无联网ignored测试；--offline只禁止依赖下载，fake transport未声明业务网络必须立即失败，不能将offline当业务socket沙箱。若原测试依赖缺失/编译失败，记录native exit并在原scope修复或block；不安装、不删门禁、不伪称PASS。必要原费用/锁/候选重验/deadline/官方结果/秘密回归不因新旁路而取消。

开收工身份采用可审阅的只读scratch脚本或逐个sha256sum：脚本仅读取final-freeze.json列举路径及parameters、上述额外旧binary和本期allowlist，核文件hash/存在性/行数/候选身份；禁止读冻结表现、业务库、凭据、联网或启动子进程。保留起止身份与真实工具返回，摘要写Kanban/最终唯一报告，不另造data/tasks状态镜像。脚本不能用来重放被安全拒绝的动作；安全拒绝停止该动作与依赖分支，必需验收缺失不done。

## 6. 风险、降级与回滚

| 风险 | 具体处置 / 不承诺项 | 回退 |
|---|---|---|
| 观察计算/IPC/父写盘的真实开销 | 不在候选→apply中间；非阻塞单send、无重试、有限深度/记录/索引/接收FIFO；父优先旧流。磁盘write/flush与OS调度仍可能耗时，固定输入对拍不证明真实零延迟 | 不传--post-entry-observer，旧装配与交易语义不变 |
| 子端输出满/断开或编码失败 | drop/disable，seq/counters/缺END披露，不置原output_failed/halt/latch | 无新队列/重连/stdout fallback |
| 父旁路校验/文件错误 | 在新receiver内隔离；原facts/final/exit不改，观察不完整；原交易坏行仍旧错误 | 仅关旁路，不停止资金cleanup |
| series终止无新鲜原CheckTime | END终止通知、不造normal sample、缺terminal明确INCOMPLETE；硬退出缺END | 不额外now/采样/延长run |
| 模型代理、缺源时间/真实费用 | 原模型未校准；receipt-only如实披露；paper收费不是实际fee/fill/Gas | UNKNOWN/null，不“修复”交易源或收费 |
| 镜像/深度限制 | 不是两本独立书、不是排队/撤单/滑点承诺；EPS/clean原语义披露 | 限制或缺数不输出full值 |
| frozen/dirty误归属 | 按快照delta+完整SHA，不清理/checkout、不覆盖旧target/binary | 需要越界则REVISE主控，不松freeze |

回滚不清entered/vol、不重写账户、不恢复旧binary覆盖候选、不删旧证据。观察文件只能作为证据，不用于resume资金账。无授权不部署、不启用生产flag、不新增cron/systemd/网络订阅，不提交推送。

## 7. 交接与Design Gate

必须遵守上游全部R/F/A条款与本精确allowlist；可自行决定局部Rust生命周期/DTO字段布局、Python内部dataclass实现和测试辅助函数名称，不可更改wire/费用/时钟/首样本/终止/关联/容量/null语义。新代码只有上述具体模块，不演进为通用observer框架。

若冻结资产必须改、原guard/fee/clock序列无法保留、实际首次write无法验证关联、隔离构建/真实fixture不可用或需要新生产运行，停止受影响分支并REVISE/block主控；不以“只读”豁免。原已存在功能不列为待重建；未运行验证明确未验。

Design 静态自检关闭项：上游独立实体和V1.0互引、hook与下一tick快照、无新增now/observe/evaluate、selected外覆盖、完整flat字段、独立framing/存储/reader、跨通道水位关联、coverage与故障隔离、G3/allowlist、真实离线fixture/隔离argv和默认OFF回退均已有明确决策；开放业务冲突=0，开放Design finding=0。终止缺clock/源时间缺失/paper费用假设/真实I/O延迟是明确的证据限制，不是默默留给实现者决定的问题。

本阶段完成前再次核RFC/SPEC/Design三个独立实体及上游SHA、本文空白/互引/字段/范围。本文交付不代表代码或A-001–022通过；沿预建Implement→独立Validate释放下游，不新增卡或同卡review。主控收到完成通知仍须核三文档Gate；Implement开工必须重复该前置条件。结果唯一报告在data/reports/2026-11-18-btc5m-post-entry-observer/report.md，任务状态只在Kanban。

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0 | 2026-11-18 | 冻结post-trade/下一tick快照、原时钟复用、非阻塞datagram旁路、严格wire/coverage/reader、as-of关联、allowlist/G3与离线验收 |
