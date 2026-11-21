# DESIGN-07-007: BTC5m live parity 与有界无人值守运行

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | Draft V1.1；窄 Design Amendment 交付候选，待主控核对及独立 Design Gate；非实现、独立 Validate 或生产放行 |
| 作者 / 日期 | YQuant Principal；2026-11-19，Asia/Shanghai（UTC+08:00） |
| 来源 RFC | [RFC-07-007](../../rfc/07_trading/RFC-07-007-btc5m-live-parity-and-operations.md) V1.0 |
| 来源 SPEC | [SPEC-07-007](../../spec/07_trading/SPEC-07-007-btc5m-live-parity-and-operations.md) V1.0 |
| 来源任务 | 原 T2 t_44dc54d1（父 t_b946f2c3）；本次 Amendment t_780a6887；仅 live_events 类型/测试有界拆分 |
| ROOT | /home/pascal/workspace/yquant-investment |
| BOT | ROOT/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits |
| 后续 | 独立 Design Gate t_e43a4b06 仍 blocked，待主控核对后释放；L1 t_9edc6973 仍 triage；原 L2/L3、总收口 t_9be36fdf 与独立 Validate t_c6dc70ae 保留原链/hold |

上游输入实体已全文读取。RFC V1.0 SHA256=`38356736b1132689a276be720eed9ff1cd9c009d3d02a0342f9e595f8f8d8416`、SPEC V1.0 SHA256=`12f8afda7b29026fe9139d49024a92b096a91b7b96411a94718de49cb114d873`在本次 Amendment 以 sha256sum 重新核对一致，均不修改。原 Design V1.0 SHA256=`58562e2b78c606467b2d8ca60e67493fec49592371857ae85d53aa75c7f2ec49`为修订基线。上游元数据仍记录 T1 交付时状态及无版本号的同一 Design 路径，是历史阶段记录，不是要求当前 Design 仍为 V1.0。本文 V1.1 继续实现 RFC/SPEC V1.0，仅细化内部模块、范围和测试归属，不改变经济、字段、恢复、授权或24项验收语义，不升级 wire/schema 版本。

## 1. 设计结论与范围

继续唯一 RoundTaker → DecisionCore → Broker → PredictFunTrader。显式新候选共用 phase1_net_shares，live 不创建 PaperCash；原 LiveState 保存实际金额/份额/预占/水位，新增运行元数据及原子量投影，不另建交易主账。Mongo 只记录一次 ARMED 拒绝屏障，不恢复余额、不自动续跑。健康单进程可做不同轮次的合法交易；任何停手/未知/WAIT_CASH 不可自愈回 READY。

原 T2 唯一新增文件是本文；本次 Amendment 唯一可修改文件仍是本文。下文方案均为目标合同；部分接缝已由 L1 落盘，当前已见能力与尚待实现项严格按§2增量说明区分，不能把 planned implementation 当已执行结果。当前不构建、运行业务、读交易秘密、连接 Mongo/私有 API/RPC、真实签名/认证/订单/取消/资金、发外部告警、改服务/调度/权限/profile/依赖或 commit/push。不能以文档静态通过证明可上线或有 alpha。

增量优先级：仅获验收的显式 07-007 候选替代旧 signed legacy / signed-null / 无跨进程保护对应 non-goal；旧07-002/003/004/005/006其余契约、历史 FAIL 和证据不改。普通 paper/live、其他 venue/策略、history/replay、unsigned v2、observer unsigned-only 默认不变；不做混合模型、动量、OBI、主动退出新策略、通用 OMS 或资金循环服务。

## 2. 基线 reconcile 与源码事实

路径均相对 BOT；行号为本轮 read_file 的定位。ROOT main、既有07-006三文档/pipeline/BOT dirty 由 git status 实际观察；不把共享修改归本卡。入场 HEAD 沿上游 ROOT `9e06cdac513cd7ec616ee4f7877913330195fcf2`、BOT `8f5dcba5b0334623bb0faf5c861fc342c1fe514e`，后续需最终身份核验。

| 接缝 | 保留的现有能力 / 证据 | 本轮真实差量 |
|---|---|---|
| arbitrage.rs:47–103,712–832 | 唯一 core / 原 phase1 tick / 正 fill confirm；observer已隔离live | is_phase1 目前由paper决定；原同步 take_candidate 无 live await 接线 |
| phase1.rs:223–365；paper.rs:641–698,880–1063 | 不可变候选、revision、共享 recheck、phase1 clock / 输出失败位 | phase1运行元数据可被live借用；不复制模型或给live虚拟现金 |
| runtime.rs:624–766；runtime/live.rs:75–253,427–559 | 先预占、hash/tombstone、真实snapshot、水位/coverage、原子净现金/净库存、账户对账 | 投影delta的净字段/实际应用有效性；原子预算/mark/latch和控制事件 |
| venue.rs:89–237 | submission/quantity/closure/accounting分离；零成交VWAP例外 | 类型化发送hook、已签边界与严格公开投影；不换OMS |
| fills.rs:87–247；predict_fun.rs:1425–1505 | 固定hash、真实签名/鉴权、原单次POST；NoReplay | 最后 token() 仍可能await；当前无耐久ACK及最终core检查 |
| fills.rs:482–493；predict_fun.rs:477–525,1610–1639 | 签名 maker/taker、最坏档位、限价、实际请求body | 新域验证BUY份额费及原子已签净到账下界；不信option名称 |
| predict_fun.rs:350–352；fills.rs:868–886 | ApiCreatedOrder当前仅order_id；原chain.settled/closed已做真实证明但snapshot不带结构化证明标志 | 接住官方removalLockedUntil和同一读代settled证明，不把不存在字段当已有；只加元数据投影 |
| account.rs:239–290,1098–1295 | 固定账户/decimals/余额/权限、AccountGate预算与unconfirmed | 最后检查只能豁免本单Prepared的自占位，不能误封正路径或放过别单 |
| control.py:957–1064,1565–1703 | 固定签名child、keyring/环境来源、supervise/首次写 | 新版本严格writer/reader、ACK、单账户锁、Mongo屏障、运行final |
| observer.py:965–1015 | reader在调用时局部import btc5m_control | 当前run可能后续按原路径读源码；见§9，不用“已经加载”推定可改 |

07-002已验离线执行/SDK，t_3cfa9034/run3874 PASS_OFFLINE_REPAIR、t_655f69cf/run3876 PASS_LAUNCH_WIRING复用原签收。旧unknown→planned量问题已修，不再列待修；local_signer/cli/sdk_ops固定入口也已存在，不重建或直接修改。实际场馆、余额/批准额/Gas和存储部署仍未验证。

本轮只读官方公开网页：place-orders、fees、order-lifecycle（2026-11-19，链接见§12），明确201非final、MARKET部分FILLED、BUY扣份额及signed fee cap；无账户访问。提取服务403后以浏览器读公开正文，不是绕过venue登录。

V1.1 reconcile（2026-11-19）：以上表格、官方网页读取和行数是原 V1.0 的阶段基线，不冒称本卡重做。主控卡面已核 run3882 的局部候选及 cargo check native0、476 passed / 0 failed / 3 ignored；新增4例仅局部 apply/Broker 回归，本卡未重跑，不能当完整 live 消费者验收。此次定向 read_file 实见 live_events.rs 共1356行，生产1–1172、cfg(test)从1174开始，8例见§11.1；LiveEvent.payload、emitter.envelope/write仍接 Value（217/640/761），尚未满足严格 typed 合同。本修订只给其 types/tests 拆分落点，不将原 T3 计划重新立项。

剩余工程缺口仍保留：paper.rs:900 仅 paper.phase1、live evaluation 恒 false；taker 新入口 check_entry 使用 usd0 全拒绝；共享 emitter/seq/lane/pending 和 expected_hash/ACK/parent-stop 未装配；fills 同步 permit 后 request 再 token.await，FINAL_SEND 及 State→handle→gate/首 poll 线性化未闭合；main 五参数/manifest、完整 native 正反例和 Rust producer→supervise→reader 尚待完成。这些是既有§3–8/§11的 T3 backlog，不是本卡完成声明，也不是新增设计范围。

## 3. 模式、装配与固定输入

### 3.1 显式选择，不升级旧入口

原 control.build_parser 新增 `--live-contract phase1_net_shares`、`--operations-mode supervised|unattended`、`--risk-window-id`、`--authorization-ref`、`--deadline-at`。五者在新signed域全部必需；缺部分、unsigned携带、signed+observer、非固定账户、超旧6h最大预算均在秘密前拒绝。无新开关时维持旧入口和版本，不靠public config的 enable_trading 隐式升级。原 `--duration-hours 6|72` 不变；新live不能带该选项，旧模式也不能带新deadline。argparse需区分未提供与显式提供，不能因旧default=6误拒新入口。

Rust main增加相应 `--controlled-live-contract`、`--controlled-operations-mode`、`--controlled-risk-window-id`、`--controlled-authorization-ref`、`--controlled-live-manifest`。最后一项不是任意路径：只能为本run证据目录的 `live-context.json`，父按固定路径构造；它是无秘密公开启动上下文而非批准token。ControlledRun增加 `live: Option<ControlledLiveOptions>`，原构造器统一None；检索未见定义以外ControlledRun字面构造。新增 `from_live_arguments` 只服务显式新域，验证实际start < deadline、0<预算≤21600秒；旧from_arguments仍精确6h/unsigned72h。受控ID统一原RUN_ID_PATTERN（先语法，不修补），非新域不读取manifest。

Ctx::connect_with_trader继续原trader_factory/account gate。新域在原signed分支构造原Broker后调用 `with_controlled_live(options, clock, supervision)`，要求live/PredictFun/chain56/fixed PredictAccount、原limits和模型固定、PaperCash=None；复用原SystemClock（UTC+含暂停elapsed）。Broker::is_phase1/phase1_clock/entries_stopped支持这一明确上下文。RoundTaker仍据is_phase1创建同DecisionCore::phase1；observer原is_live拒绝保留。

trade_phase1仅将调用处变为：paper用原take_candidate同步返回；live用原Broker的新 `take_live_candidate(...).await`，都反馈正净份额给confirm_fill。不把既有TakeResult变体或所有策略调用改成新协议。live Coinbase在broker秘密/签名/POST前以SOURCE_NOT_ALLOWED拒绝；保留原core可审计的经济诊断，不向07-005 decision.reason塞未定义枚举。live专属拒绝放order/stop.reason；无attempt的来源拒绝以stop SOURCE_NOT_ALLOWED停新增。common Binance域对拍core而非两个公式。

### 3.2 启动上下文与生产绑定的信任边界

仅新live读取固定 `BOT/tools/predictfun/btc5m-live-activation.json`。这是未来人工批准后才可物化的L1公共部署绑定，当前不创建；不是新授权系统、签名token或CLI任意路径。离线测试通过函数参数注入严格同形fake，生产main不开放测试替身。缺文件/未知版本/修改身份均拒绝，不以旧budget bool替代。

该对象精确字段：schema_version=`btc5m-live-activation/1`、authorization_ref、risk_window_id、operations_mode、account_identity、not_before、deadline_at、candidate_digest、storage_binding、gas_policy、takeover_ref。其余字段递归拒绝；ID/时间/地址沿SPEC；takeover_ref是同受控公开ID，非消息地址/自由联系人。storage_binding精确为 deployment_id、database、collection、credential_env、endpoint_id；gas_policy精确为 payer_address、minimum_balance_atoms、maximum_consumption_atoms。两预算均合法BNB atoms且>0，payer限原ChainRead实际读取的account_identity.signer_address（固定Predict Account的owner/Gas支付者），不得用持有USDT的trading_address替代；其他支付者当前GAS_UNAVAILABLE，不扩RPC路径。未批准输入不填伪值。

候选部署提案：database=`tradingagents`，collection=`07_trading_btc5m_live_guard`，credential_env=`YQUANT_BTC5M_GUARD_MONGO_URI`；这是待批准的新独立集合绑定，不声称存在，不访问portfolio/UD/task集合。deployment_id为受控ID；endpoint_id为严格对象{scheme,hosts,replica_set,tls}，scheme固定mongodb（本轮不支持SRV动态改目标），hosts为已批准的规范host:port有序数组，replica_set为已批准名称或显式null，tls为明确bool。URI解析仅在内存提取这四项与绑定精确比较，禁止隐藏多主机/替换URI query中的库或TLS/replicaSet覆盖，未知连接选项拒绝；pymongo固定主机/primary及上述读写策略。未来主控填定并核同物理部署，当前代码无默认实际连接。正式激活冻结一个绑定及其candidate_digest；CLI、run/window、环境替换库名或集合名不能覆盖。URI只从该单一已批准env键读取，不全量load_dotenv、不从URI推断另一个库、不把URI/摘要传child或写证据。URI变化即不能自证仍在同一Mongo部署，须生产Gate核验而非“可连接即通过”。同UID/管理员可改代码、绑定或删库是明确可信操作员边界，不宣称抵御恶意绕过。

固定顺序：公共配置/参数/候选身份/批准绑定语法 → 账户OS锁 → Mongo单次ARMED创建及耐久读回 → 新证据exclusive创建和fsync → 原API来源/keyring一次读取 → 原单child → 原官方完整startup账户/权限/预算核对 → READY。失败不fallback、不自动换run/库/集合/环境/签名器。只枚举环境键存在性的检查可提前；`_api_source`及`_read_owned`实际读交易秘密必须后移至屏障通过。Mongo自身凭据按上述单源仅在获批存储阶段读取，fake两类真实秘密读取计数均0。

`live-context.json`精确为schema_version=`btc5m-live-context/1`、run_id、risk_window_id、authorization_ref、operations_mode、account_identity、started_at、deadline_at、candidate_digest、asset_units、gas_policy、recovery_policy、cash_recovery_policy；不含storage URI、数据库凭据、私钥、JWT、签名字节。父文件exclusive-create/fsync、目录fsync并严格读回后传给child；child核对原argv/固定常量，管道无有效监督时拒绝。文件本身不授予资金动作，实际许可仍由外部执行和风控确认。

## 4. 发送链、耐久ACK与原子边界

### 4.1 新类型接缝及所有权

| 拟新增类型 / 落点 | 精确职责 |
|---|---|
| config/controlled_live.rs::ControlledLiveOptions | typed模式/公开关联/期限/Gas；从原受控入口解析，无Default live |
| runtime/phase1_control.rs | 提取paper.rs现有with_phase1/is_phase1/phase1_clock/phase1_entries_stopped四方法；unsigned仍读原PaperCash.phase1；live读LiveState.controlled.phase1，复用Phase1Run类型 |
| runtime/live_control.rs::ControlledLiveState | 原State.live内唯一运行元数据：phase1、pending candidate、attempt关联、traded原官方身份、latch/stop/READY状态、输出seq；不存第二B/K/R现金表 |
| runtime/live_control.rs::LiveCandidateGuard | 持有Broker共享state/原candidate/clock及监督确认句柄；不拥有可独立下单的client或签名材料 |
| service/venue.rs::ControlledSendGuard | 对象安全窄trait：准备阶段核对事实、等待关键order耐久确认、最后同步许可；默认不支持，不能忽略hook而调用普通place |
| service/venue.rs::SignedExecutionBound | account/market/token/route/fee、gross request、maker/taker原子约束、max_cash/min_net、expiration、hash；无signature/salt/raw请求 |
| service/predict_fun/controlled.rs | 原适配器guarded薄接线、signed bound证明与同一单次写transport；不含模型/资金主账 |
| service/predict_fun/account/controlled.rs | AccountGate::with_prepared_attempt：只允许本单Prepared占位，锁内检查其他block；不清原gate原因 |
| runtime/live_events.rs | 从真实State/ExecutionSnapshot/实际AppliedExecution构造typed事件，拥有有界序号/编码/原stdout出口；委托子types校验，不再内嵌wire定义或测试；无余额应用逻辑 |
| runtime/live_events/types.rs | 私有子模块：SPEC严格wire结构/枚举、键表、标量及递归校验和序列化；只声明数据，不读Broker/venue、不生成delta/seq、不做I/O；父模块保持原导入门面 |
| runtime/live_events/tests.rs | cfg(test)私有子模块：原8例全部同义迁移、严格schema及原子facts/delta投影回归；生产路径与跨消费者测试仍见§11.1 |
| runtime/live_accounting.rs | 原LiveState的原子风险/估值/官方claim投影及loss更新；不以f64 holdings反推原子金额 |
| runtime/live_control/channel.rs | 同stdin的新版小型帧/ACK等待与EOF监视；不建服务/新行情轮询/新心跳机制 |

新增OrderVenue方法 `controlled_reservation_atoms(planned)` 和 `place_controlled_tracked(planned, handle, guard)` 均默认EXECUTION_NOT_ENABLED；前者仅在已核新域BUY市场/份额费metadata下求预占，后者由PredictFunTrader调用与place_tracked共用的原准备/签名/POST主体，仅显式新域带Some(guard)。普通tracked分支None保持原行为。BoundOrder/AttemptHandle是原订单关联，不把candidate或模型塞进全交易所API DTO。

新域事件和执行共用原Broker的单一异步operation lane（tokio::sync::Mutex，仅串行已有run操作，不是另一个Broker/账本/worker）：take_live_candidate、sync/seed/observe/settle/final及其实际producer依次进入，锁外网络await可持lane但不可持State锁。同步EVALUATE使用try_lock，忙则拒绝并停新增，不能等待时仍写另一seq；其后live提交重新核pending candidate。控制watcher仅改State sticky flags、notify，不直接发事件、不抢lane。每一lane操作在原State锁分配序号/构造不可变快照，释放State后按序输出；未完成flush不让下一producer插队。FINAL_SEND已持lane，仅取State/handle/gate，不再获取输出锁。这样不需通用outbox/无限队列，也不把Broker锁跨await；并发预占者必须经同lane及State双重约束。

### 4.2 唯一顺序

1. 原core EVALUATE → Broker记录决策。Broker同State锁核身份、revision、core PRE_SUBMIT、新时钟、停止/loss/账户/原子预算；建立原AttemptHandle和原R0/tombstone。无context裸BUY在所有新phase1入口先拒绝，不能从普通take绕过。
2. 锁外执行原适配器的账户、最终book、权限、签名、JWT、ERC1271等待。每一等待后先检查sticky stop；检测停止即退出后续准备，但已存在hash/事实仍保留。最终book/fee/route必须与冻结候选一致（按原镜像/精度正规化后逐字段、不是容差吞差异）；变化则INPUT_CHANGED终结旧candidate，0POST。更好价也不能暗换旧candidate输入。2026-11-21轻量纠错：此“一致”指最终盘口完整且支持冻结决策——非空、不越过候选限价、深度覆盖冻结股数；越限或深度不足为候选级拒绝（释放本候选、NOT_SUBMITTED证据、不终结窗口），身份/hash/ACK/bound/账户/风控不一致仍硬终止，缺一侧盘口为READ_UNAVAILABLE；不改动本条其他语义。
3. 由已构造order和部署生成SignedExecutionBound；先在原handle保存hash/Prepared，不泄露签名字节。序列化完整 `order` 事件，经stdout发给原supervisor。此时可能阻塞，绝不算FINAL_SEND已经通过。
4. supervisor按§7严格校验该行及前缀，首次追加events.jsonl → flush → fsync文件 → 同目标readback精确本行 → 才写ACK。新started/public-config/live-context及目录必须已耐久；不能用flush或文档里的durability=true冒fsync。ACK丢失/超时/错关联不发送、不重新签名；屏障仍ARMED。
5. 所有await/关键order ACK后，用原client准备完整HTTP请求/单次future；其中JWT已取得、body序列化完成，第一次可能交给transport前再获取最新CheckTime，调用原candidate.recheck（同模型/常量）并重查全部门禁，生成FINAL_SEND快照。不能把旧checked_at或ACK时钟当最终时钟。
6. 最后同锁许可与初次transport poll是一个不可分离的本地线性化区间，细节如下；退出区间后才await网络完成。只有一次初始POST，不401重发、不新salt补单、不重广播同hash。
7. 原snapshot/apply_snapshot与sync_predict消费同hash全部真实事实，晚到/越期限/partial/负EV照记；只把实际正net_inventory增量反馈core entered。已知gross但net不全，账户闭锁和round tombstone仍阻止重下。

关键order的Prepared持久证据在发送前完成；FINAL_SEND本身不能在最终检查与transport之间做阻塞写入。因此其typed快照和下一状态事件在首次poll后按序输出；若失败，资金事实不回滚，audit INCOMPLETE，冷启动仍拒绝。磁盘上Prepared+无后续不能证明未发送：人工按同hash/全窗口核对。不是对每个网络字节做跨进程事务。

### 4.3 stop/EOF与第一次发送许可原子关系

原paper watcher逐字节D/EOF不改；新live仅装一个新版watcher，仍独占原stdin，不开第二读者。生产继承stdin必须验证为pipe且父端有效；watcher先把Readiness结果交Broker，READY前不发送。

新版控制帧仅两种：原单字节 `D`（deadline）；或ASCII `A <seq> <signed_hash>\n`。seq为规范正整数、hash先0x+64hex校验，完整帧≤160 bytes，最多一个待ACK；ACK必须对应本run当前唯一等待的已持久order.seq/hash。无等待/重复/倒序/未来/坏帧/partial EOF → CONTROL_CHANNEL；EOF/读错 → PARENT_LOST。父不可传任意命令、reset、金额或签名。supervisor单线程先判停止/deadline再发ACK，stop关闭stdin，不再发ACK。

watcher发现EOF/stop立即获取原State锁置sticky stop、清尚未消费的ACK许可并notify；它不依赖下个tick、不调用网络。不靠MAX_FAILED_TICKS=3给新增宽限。监督者活着但暂停/远程不可达，下一单必须重新获同hash耐久ACK，无ACK不准发；不声称检测一个保持打开却暂停的父进程的精确失联瞬间，不新造心跳阈值。

最终send使用 `poll_fn`/等价Future包装：第一个poll持State → AttemptHandle → AccountGate固定锁序；核新CheckTime/停止/loss/上下文/账户检查epoch/ACK/signed bound，消耗一次性许可，将原handle/账户门禁标记MayHaveSubmitted，随后在同一poll且无其他await/日志/fsync/锁等待步骤时首次poll原HTTP发送future。该poll必须非阻塞；不是持锁await网络。后续poll不重查并重新发送，只推进同一future；所有准备可能挂起的工作必须在之前完成。guard与writer提前确保事件容量和序号，不因FINAL_SEND输出申请额外锁/IO。

stop先取得State锁则本单0次transport poll/0POST；发送区间先取得锁则此单已是in-flight，随后EOF不能把它改成NotSubmitted，必须同hash继续有界读或交接。对方进程死亡至本机EOF被观察之间不是本方案可消除的物理时间差；验收线性化的是本机观察到stop与首次交付transport。测试必须把第一次poll Pending也算可能提交，不能等HTTP201才立tombstone。不能让final check放在authed_write外，而其内部再次token().await后直接发送。

AccountGate新helper在已有accounts锁内检查budget、mismatch、reconciliation、failed_reads，unconfirmed集合必须恰仅本attempt且其原状态字符串为PREPARED（与handle的AttemptPhase::Prepared同检）；任何别单/MAY_HAVE_SUBMITTED均拒绝。随后同区间将原gate本项更新为MAY_HAVE_SUBMITTED，不调用会再次锁gate的mark_submitted。所有新锁按State→handle→gate，watcher只锁State；不跨await持锁，不引入gate→State反向回调。

ACK等待使用原15秒请求上界与本run deadline的较小值；用原含暂停clock检查，超时AUDIT_UNAVAILABLE停新增。等待不延长5秒span/10秒age/30秒入场界；ACK回来仍需最终重验。错误不能从准备future Drop自动释放；只有明确Prepared+NotSubmitted未交transport的返回才沿原release_not_submitted一次释放。

### 4.4 已签边界、费用与正路径

只新增07-007 BUY MARKET域的边界证明；普通reservation_atoms/cash_with_fee保留。沿原market_amounts与order构造，不增加slippage/isMinAmountOut参数、不把MARKET改成maker/FOK策略。若SDK/API设置将来变化，当前guard不能凭名字认定保证。

- `S=10^18`，Q=order.takerAmount，A=order.makerAmount，b=order.feeRateBps。要求Q精确对应候选下取整gross原子量，signed side=BUY、market/token/account/route及b与候选/实际部署一致；不能因5位有效数字截量而偷偷缩单。A/Q用U512交叉乘法证明不超过candidate.limit。构造时quantity或route变动直接INPUT_CHANGED。
- 官方BUY费从收到份额扣，已签b是费率上界；原子量保守下界 `N_min=Q−floor(Q*b/10000)`，因为min(p,1−p)/p≤1且链费向下舍入。这是最坏执行约束，不是把actual fee改成模型费；真实实际fee/net仍仅来自原snapshot。支持的签名b须满足已读官方合约cap≤1000；core原模型允许域不改，不能证明venue签名域则SIGNED_BOUND_UNPROVEN。
- 对这一已证明BUY份额费域，`max_cash=A`、`min_net_shares=N_min>0`。新 `controlled_reservation_atoms`只在guarded BUY返回候选limit下的向上取整最坏cash（最终A不得超过它）；不沿用普通路径可能额外现金费的保守cash_with_fee，否则每笔接近2的合法净份额单都会被多预占拦截。fills::check_signed_bound在Some(guard)时必须调用这一已证明域的精确A≤R0检查，而不是仍无条件走原cash_with_fee；None保持原完整检查不变。未证明BUY费方向/部署则0签名/POST，而非假设fee=0。
- 原phase1模型仍按07-005算净EV/edge。FINAL_SEND除原recheck外，以实际已签约束保守检查 `N_min*fair−A ≥ 0.03*Q`（统一单位后原core经济比较，金额边界原子量零容差），不通过不发送；不能以平均VWAP通过替代最坏已签价的净EV。不同费率/最坏边界拒绝属于执行约束，不修改同core EVALUATE公式。
- 全单最小N_min不是任何partial保证全额到账；partial按实际gross和费用核算。cap/claim/gross不可拿N_min替代。unexpected collateral fee先按事实入账并保留超预占风险/停手，不能剪实际fee以维护上述假设。

离线正例须含非零bps、合法原构造signed ratio、2/2/10内的实际发送，不能只用fee0、全部拒绝或替换PredictFunTrader证明能力；允许最坏约束比模型初选更严格，但不能把所有合法输入都封死。

已用Fraction独立复算的边界算术向量（不是实际成交/原core输出）：Q=5股份、A=2 USDT、b=200、假设fair=0.5时，N_min=4.9股份，最坏净EV=0.45 USDT，edge=0.09 USDT/gross share，单笔恰2；两个不同市场累计成本4≤10。另核36个quantity/price/rate原子向量的费用下界及−20阈值±1atom。Implement原生正路径仍必须由真实core算其fair/方向，不把这个假设fair硬塞生产core或伪造回执。

## 5. 实际原子量、预算、估值与窗口

### 5.1 原账本扩展，不用Python账本替代

原LiveState.net_cash/net_inventory、applied_q/cash/fees、reservations/watermarks继续唯一原子实绩。controlled元数据只记attempt↔candidate/market、官方结果/mark有效性、stop/latch/seq与时间关联。B/K/R/V均从这一State和其官方归属记录投影；不在Mongo、Python、另一个Broker重复存可交易余额。旧Holding的f64仍作既有显示/兼容视图，新域预算/损失判断不得从该f64乘1e18反求。

apply_snapshot在原State锁内先完整验证再commit。其现有Delta只有四gross/fee字段且default不能区分“未应用”与0；新增内部 `AppliedExecution`结果含原Delta、net_cash_delta:Option<U256>、net_inventory_delta:Option<U256>、applied:bool、duplicate:bool、accounting_complete:bool。原公开Delta及apply_cumulative/其他消费者契约不改：新增受控包装/结果出口，同一原commit产生，不能在Python再算成交易应用。完整commit给六个实际差额；未完整未应用为null；旧/重复快照确认无新增为六个0。原generation/coverage保留，不以其新gross倒推已知field覆盖。

同一LiveState为新域增加 `observed_risk_floor: HashMap<attempt_id,U256>`：在任何snapshot应用前，仅在身份匹配后以已知gross_cash+collateral_fee、net_cash的较大值单调上调保守现金风险下界；未知不覆盖旧值。包括overfill/费用修订等导致原apply拒绝的事实，也必须保留原snapshot的typed审计投影并使status=CONFLICT/全账户停新增，P至少=max(R0,observed_risk_floor)−已应用cash，绝不因拒绝commit而把已经观测的更高风险丢掉。它是原预占的风险下界，不是另一份已成交余额；无法正常入账的现金/NAV派生null，不用裁剪成request或伪造delta。新域原子预算不使用原protected_risk的较低旧值遮盖该下界。

startup新域要求无open_orders、无未解释/继承持仓、无foreign风险且真正可用USDT≥100；原seed_predict其他模式仍按原语义。budget bool仅确认原100分配，不创造真实余额。完整baseline和每次runtime账户检查保存checked_at/elapsed及状态epoch于同State；最终check要求该次准备的完整对账仍对应同版本，≤10秒receipt-bound且无待核风险/失败标志。它是原phase1时效尺度复用，不声称RPC余额实时；每次准备必须真实读全，不靠旧gate success永续放行。

### 5.2 可计算口径

S按started.asset_units校验，当前collateral/share/gas均18（原ChainRead显式验证USDT18、原股份/BNB部署常量）；不猜decimals。USDT金额U256、PNL用有符号整数（checked运算，拒overflow/−0）；中间乘除U512。BNB独列，不与USDT相加。

| 值 | 同State原子投影 / 准入约束 |
|---|---|
| C0 | 固定100*S，窗口分配预算，非整个账户余额 |
| B | C0−窗口实际BUY net_cash累计＋已核同目标现金回收；本轮MANUAL_PAUSE不在进程中执行资金回收，因此正常交易路径不增加赎回收入 |
| K | 本窗口已应用且尚未经济释放/回收的实际net现金成本，按attempt/token/market归属；正claim仍保留成本 |
| P | 原reservations的保守未闭合现金余量；已应用c后该单余量=max(R0,已知更高风险)−c，FINAL且核算完整才释放未成交部分；未知保留原值 |
| 每单/市场/总额 | 1*S≤w≤2*S；K_m+P_m+w≤2*S；K+P+w≤10*S；精确等号允许，禁止EPS/自动升额/缩单 |
| available | min(B−P，完整官方可支用USDT−未闭合预占)，下界不足/未知不交易；外部流不能增C0 |
| V | 有效净股份按原mid估值＋官方正claim；一个token只能在shares或claim中取一次，不双算 |
| U / R | U=V−K；R为已经经济实现的净收益。官方零兑付可经济移除成本K并实现−basis，实际链残余股份另列，不造cash回款 |
| 恒等式 | 完整无外部流：B=100*S+R−K；NAV=B+V；net_pnl=R+U=NAV−100*S；显示累计fee不再扣一次 |
| loss | net_pnl≤−20*S含等号即永久latch；未知mark/net/fees则先DATA_UNAVAILABLE停新增，不能以0/成本/旧mark补绿 |

mark只沿原observe/mid_of及合法性，缺book/失败先invalidate新域mark；每次观察/成交/费用/官方结果后同锁投影并更新latch，且FINAL_SEND再检查。将合法f64 mark转值时用其确定的有理表示（按IEEE754位分解）计算floor(net_atoms*mark)，全程checked/U512；不能先以f64乘巨额atoms造成阈值误判。该数注明VALUATION非cash，不修改paper mark或模型。原始amount事实仍原子量，模型float容差不传递到预算/loss。

新域没有自动SELL/merge/redeem/提款。正claim→WAIT_CASH，B不加claim，K不减，V可用官方值；收到人工资金回收事实也不返回READY。本轮不把手工SDK后的账户差额自动当本run收入，若观察到不属窗口的变化先RECONCILIATION_REQUIRED。未来受权人工报告可用同目标份额/现金读回证明回收，不能回写旧窗口事件或清latch。

Gas策略沿原ChainRead的signer_address原生BNB余额读回；trading_address仅为USDT持仓及账户互斥作用域，不是本支持路径的Gas付款者。不增加任意payer RPC。记录初始G0与每次完整G：G低于minimum或G0−G大于等于maximum即GAS_BUDGET停新增；余额不明/上升或不解释的变化GAS_UNAVAILABLE/RECONCILIATION_REQUIRED，不猜充值。这个保守额度控制是消费余额的运行门禁，不是逐tx费用归属；gas_paid_atoms仍null/NOT_MEASURED直到原消费者可证同payer/tx费用。签名/POST/取消API不消耗链Gas不等于整个窗口Gas0，BNB上限必须未来另批。20 USDT只是停止新增阈值，不保证最大损失/全币种成本≤20。

## 6. 单实例、Mongo屏障、崩溃与人工接管

### 6.1 锁与拒绝屏障

OS锁固定 `ROOT/data/runtime/btc5m-live/locks/predict_fun-56-<固定trading_address小写>-predict-account.lock`。原launcher标准库fcntl.flock(LOCK_EX|LOCK_NB)，生产无路径覆盖；跨run/window/两种值守模式共用，unsigned不触碰。只新建需要的目录/常规锁文件（新建mode0700/0600），不chmod既有资源；拒目录/文件symlink、非本UID、非regular、多硬链接。文件不以退出unlink，以免inode换锁。锁FD父持有到child确证退出/交接，不把锁文件存在当锁有效。

仅父持FD也不足以覆盖父死子活；Mongo屏障保证另一合作启动仍拒绝。后续若父无法确证child退出，不声明锁可解除的安全资金状态；无论OS最终释放，ARMED不变。所有受控新signed必须同scope屏障；旧signed入口以后真实授权也不得与此账户并行，运行占用只保证合作入口，非受控SDK/其他主机需要账户独占声明，不冒称全交易所互斥。

Mongo `_id = predict_fun:56:<固定trading_address小写>:predict-account`，不含run/window/host/operations/signer。先严格地址格式再规范身份比较；host仅scope初始归属，来自os.uname受控短标识，不影响唯一键。屏障恰为SPEC §4.bis字段：_id、schema_version=`btc5m-live-guard/1`、scope={account_identity全部字段,host}、risk_window_id、run_id、state=ARMED、armed_at、authorization_ref、candidate_digest。无余额/订单恢复字段、CLEAN、TTL、owner续租或自动删除。

原launcher同进程lazy import项目已有pymongo（ROOT/.venv/bin/python），不import MongoWriter/LocalMongoAdapter。集合必须已由未来批准部署物化；启动仅list/name/schema绑定只读核对，不create_collection/create_index，不依赖insert隐式建生产集合。以Mongo内建_id唯一性做一次insert_one，WriteConcern(w='majority',j=True)，自动可重试写显式retryWrites=False；primary + ReadConcern('majority')同目标find_one精确核scope/版本/全部原始内容。禁止先find再upsert、超时重insert、找副本旧数据凑通过；读回成功也不能把超时不明确的write重新算成功启动。

durability是实际ACK和读回行为，不是文档字段。driver/绑定/集合/所需存储保证缺失均RECOVERY_GUARD_UNAVAILABLE，duplicate-key或已有/坏版本屏障为RECONCILIATION_REQUIRED，0交易secret/child/POST。现有Mongo若不能majority+j则阻断激活，不修改部署、不加driver/SQLite或新服务。驱动重连/读写socket及serverSelection总上界复用原启动/请求15秒且受本run剩余deadline约束；一次业务尝试，无应用层重试。存储凭据仅父进程内存，不传给child。

### 6.2 崩溃事实矩阵

| 崩溃/失败位置 | 此时允许的真实结论 | 后续新启动 |
|---|---|---|
| 取锁前/抢锁失败 | ALREADY_RUNNING，未取交易秘密/未启child | 当前进程不重试 |
| Mongo写前 | 无屏障成功证据，无child | 人工判断后另次明确启动，不自动loop |
| insert发出但ACK/读回不明 | 可能ARMED，不能说绝未写 | 全拒绝；不得换绑定规避 |
| ARMED后、秘密/child前 | 没有资金发送，屏障仍在 | COLD_START_REFUSE；即使ended显示零单也不自动清 |
| reservation/签名后、order未耐久/无ACK | 明确未交transport才可释放本笔；hash若已知保留 | 屏障继续拒绝，保留证据缺口 |
| order耐久/ACK后、FINAL_SEND前 | Prepared不证明未来未发；本进程明确guard拒绝才NotSubmitted | 同hash人工核，不靠缺POST日志判断 |
| 首次transport poll/响应前 | MayHaveSubmitted/Unknown，R0和hash保留 | 新run/window/日期也全拒绝 |
| snapshot应用后、事件/ended前 | 真实账务已发生，审计可能不完整 | 不补final，不重建100或重放事件下单 |
| 正常final和child退出后 | 分别报告订单/现金/审计完整性，不自动解除ARMED | 仍拒冷启动，无reset/resume命令 |

### 6.3 有界停手、故障和接管

STARTING→READY；READY→STOP_NEW_RISK或WAIT_CASH；二者仅→HANDOFF/ENDED，不回READY。loss_latched只升真，同risk_window永真。原control_changed通知复用，运行内下一次可能POST前即执行关闭许可，不等完整网络tick；不取消已可能发单的future来伪造未发。sync_predict仍同hash有界查询/消费晚到事实；缺hash则人工完整历史核对，不“查不到=零”。

keyring缺失/locked/Prompt在child前拒绝，不Unlock/重读秘密loop/file fallback。keyring启动取出的密钥仍沿原child内存路径；后台锁上keyring并不能撤销已加载私钥，本设计不声称这种能力。运行中原签名/账户/认证失败立刻停新增；不为“检查keyring健康”反复读取私钥。其他非暂态输入/费用/账户故障也sticky停手，旧AccountGate某次读成功不自动解本run停止。

保留原正常cleanup30秒、只读settlement尾查上界600秒；signal/EOF/控制故障不另给新600秒额度。新域finish只调用原被允许的cancel/query，取消API未获该次真实许可则不执行而交接；取消成功/removed/noop/rejected/lock都不证明零风险。原rest继续CONTROLLED_REST_UNSUPPORTED；继承open risk在startup拒绝，离线仍须沿原cancel消费者演练竞争，不重写全OMS。超时kill/reap是同一原清理预算，native返回码/信号/forced_cleanup显式保留。

新增stop typed事件固定reason/takeover_required，本地严格写入并耐久则alert_status=LOCAL_RECORDED；写失败不能虚构已记录，exit非健康/ARMED/缺ended共同作为诚实证据。当前fake接收者只能证明本地调用，不能写外部DELIVERED；未来具体告警接收渠道/可达人员/响应责任另授权确认，发送失败仍停新增。本轮不新增网络告警sender、systemd或自动restart。

人工接管沿原账户/同hash/SDK能力，需核全窗口attempt/hash/late fill、部分量及fees/net、open/removing、官方结果/claim/份额及现金/Gas/R/U/latch；hash缺失或关键日志坏则完整官方账户历史查证。新budget flag、余额健康、换run/collection均不是恢复许可。本轮无自动或手动通用reset按钮；屏障轮转/新实验是以后具体授权操作，原文档保留，同窗口loss已触发不得新增。无法解释就继续阻断。

## 7. 新live wire、字段投影和真实消费者

### 7.1 分版、typed白名单

wire仅 `btc5m-controlled-live.v1`；framing仍 `BTC5M_EVENT ` + 单行UTF8 JSON + LF，含前缀整行≤64KiB，每数组≤1000，新域不借unsigned72h的1MiB例外。全对象精确required键（nullable必须显式在场）、重复JSON键/NaN/Infinity/bool冒数/非法UTF8/null/enum/未知键/未知版本均在首次write前拒绝；不能递归扫掉坏键后变成合法事件。不得承载raw/detail/error/url/签名字节。序号1起连续，final后0事件。

envelope逐键为schema_version、run_id、risk_window_id、event_seq、event_kind、event_time、market_id、token、accounting、payload，恰与SPEC §4.5对应。accounting恰含cash/available/reserved/cost/realized/unrealized/nav/net_pnl/loss_latched/status/reason/mark_time/pending_claim_value/gas_status/gas_paid_atoms。原子量语法/U256/有符号规则、order-ref等完全按SPEC；market/token/id不拿hash替代，不修复截断异常order_id。

10种payload逐键、六个facts子对象、六个delta子键、positions/unresolved数组只取SPEC §4.5原字段，不新增sidecar自由schema。Rust在 live_events/types.rs 定义具体struct+enum（deny_unknown_fields，合法有限浮点先验），Python独立精确键表；不得用serde_json任意map/Option吞缺键表达strict。decision对象直接同义原DecisionDiagnostic，只有phase在live允许FINAL_SEND，paper PRE_APPLY仍原域。SPEC已有reason两个集合分别处理，不能互混；当前源码REASONS混有BROKER_BLOCKED/RUN_STOPPED不构成扩展§4.9通用reason的许可，原8例保全也不冻结这种不合合同的宽校验。

V1.1 内部模块合同（下列新增类型名为实现目标，不是现存/外部新API）：

- 父 live_events.rs 声明私有 `mod types;` 与 `#[cfg(test)] mod tests;`，文件分别为同名子目录 types.rs/tests.rs，无 mod.rs、第三子文件或新 crate。父显式 `pub use self::types::{...}` 保留原公开导入门面：LIVE_SCHEMA_VERSION、LIVE_EVENT_PREFIX、MAX_EVENT_LINE_BYTES、MAX_EVENT_ARRAY_ITEMS、reason、REASONS、is_known_reason、EventKind、LiveAccounting、LiveRunIdentity、LiveEvent、ENVELOPE_KEYS、ACCOUNTING_KEYS、FACT_KEYS、DELTA_KEYS、payload_keys、is_atoms、is_signed_atoms、is_hash、is_order_ref、is_decimal_id、check_exact_keys；新增 LivePayload 及生产者必需的 payload/fact/delta 类型亦从此门面显式导出。不用 wildcard 生产 re-export；live_control/taker 等仍从 runtime::live_events 导入，不直依赖 types 子路径。
- types.rs 拥有上述常量/键表/数据类型/纯语法helper及 LiveAccounting 的纯序列化，新增 LivePayload 十变体分别包 DecisionPayload、ReservationPayload、OrderPayload、ExecutionPayload、ReconciliationPayload、LossLatchPayload、StopPayload、RecoveryPayload、PayoutPayload、FinalPayload。ExecutionFacts 恰六字段、每个 LiveFact 恰 status/atoms/coverage_gross_atoms/reason；ExecutionDelta 恰六字段；LivePosition/UnresolvedAttempt 精确对应原数组项。类型沿原字段、单位、nullable及枚举，不创造财务模型；event_kind 从 payload 变体唯一映射，不允许独立传错 kind。序列化仍为原 envelope 的 event_kind + payload，并非新增tag/嵌套键。
- LiveEvent.payload 及父 emitter 的生产 envelope/write 接缝使用 LivePayload，不再接任意 Value；具体payload结构成员不含自由 Value/Map。decimal ID/atoms/hash/order-ref/时间/闭合enum由受检类型或同模块校验负责，market_id按SPEC十进制ID表示，不能把当前u64 JSON number误冻成新schema。required-nullable必须检查键存在后再解析可空值，不能靠Option默认补缺；重复键在原始JSON解码时拒绝，不能先转Value丢重复键再声称已验。Value/Map只可用于最终编码视图、严格原始输入验证和负例，不作生产payload中转契约。
- 原 LiveEventEmitter 留在父文件；`LiveEventEmitter::validate(&Value)`保留为同一严格校验门面，委托 types 中仅 `pub(super)` 的 validate_envelope；保留原8例实际断言用到的稳定本地错误token（见§11.1），公开reason仍按SPEC映射。types内部check_payload/check_fact/check_positions/check_unresolved/check_hash_array及标量校验默认私有；仅父确需调用的入口收窄至pub(super)，不得为迁测试将生产私有状态升pub(crate)/pub或增测试getter。
- 父保留 quantity_class/closure_kind/submission_kind/phase_kind 以及原事实/应用结果投影责任。snapshot→ExecutionFacts、同次AppliedExecution→ExecutionDelta和core→DecisionPayload在父完成；原facts_json/delta_json/decision_json如保留兼容入口，只序列化同一typed投影，不留第二套推算。types不import State/LiveState/AppliedExecution/ExecutionSnapshot、不读余额或应用快照；live_accounting继续原子账务/估值，不接收wire定义以腾行。
- imports跟职责移动：types仅用serde/chrono/U256/SignedAtoms及同义core诊断数据（需要解码时用同字段受检表示，不修改core）；父保留原venue/snapshot/AppliedExecution、输出/并发依赖。tests用 `use super::*;`，并显式按需引入 serde_json::{json, Value}、chrono::Utc、alloy_primitives::U256、live_accounting::SignedAtoms；测试是父的子模块，可访问父私有emitter状态，原公开helper通过父re-export可见，不越级访问types私有实现。不得顺手执行历史被拒的import/mut清理。

| wire键/字段组 | 唯一原source / 转换 |
|---|---|
| run/window/time/seq/kind/market/token | ControlledRun/LiveOptions、同State单调seq、原ObservationClock及本事件关联；不以写盘时间充official observed_at |
| decision.payload.decision | 原core EVALUATE / candidate.recheck PRE_SUBMIT/FINAL_SEND；完整clock/两侧诊断及原输入，不从执行量反造fair |
| reservation.candidate_id/attempt_id/action/worst_cash_atoms/remaining_atoms/reason | 同State候选关联、原AttemptRecord.local_attempt_id/r0、原LiveState.reservations前后值；RELEASE不等于释放全部成本 |
| order.candidate_id/attempt_id | 原候选↔attempt不可变关联 |
| order.signed_hash/venue_order_id/attempt_phase/submission | 原AttemptHandle.identity及phase/submission；初始hash可null，已签非null；order_id首次获得后固定 |
| order.request_gross_atoms/max_cash_atoms/min_net_shares_atoms/expires_at | 实际SignedExecutionBound；Prepared未签阶段min可null，首次可能POST前必须>0且耐久 |
| order.removal_locked_until | 本轮接住ApiCreatedOrder官方可空RFC3339字段，并按signed hash保存只读metadata；缺失保留null，null本身不作已过锁证明；不猜ApiOrderData字段或固定delay |
| execution.attempt_id/signed_hash/venue_order_id/generation/observed_at/pages_complete | ExecutionSnapshot.identity/generation/observed_at/pages_complete，先与handle核对 |
| execution.quantity_class/gross_q_atoms/accounting_gross_q_atoms | Quantity Unknown→UNKNOWN/null，Known严格Zero/Partial/Full；snapshot.accounting_gross_q单独覆盖 |
| execution.closure/final_gross_q_atoms | Closure Open/Removing/Unproven/Final枚举映射，只有Final取其final_gross_q；evidence自由串不输出 |
| facts.gross_cash/collateral_fee/share_fee/net_cash/net_inventory | Accounting同名Field<U256>；Known→KNOWN/atoms，Unknown→UNKNOWN/null，coverage=snapshot.accounting_gross_q；Unknown原字符串只映固定reason |
| facts.vwap | Accounting.vwap，以USDT/share固定点1e18；确认零成交→NOT_APPLICABLE/null，coverage=0；其他缺值UNKNOWN，不拿limit填VWAP |
| execution.delta六键 | §5原同锁AppliedExecution的gross_q/gross_cash/collateral_fee/share_fee/net_cash/net_inventory实际应用差额；未应用null、确知重复0 |
| execution.tx_hash/settlement_status/settlement_checked_at | snapshot.tx_hash仅身份；存在不升级CHAIN_SETTLED。取下述同hash/同generation元数据的原chain.settled实际结果和检查时间，否则UNVERIFIED或MATCHED；无新RPC权限 |
| reconciliation.scope/checked_at/complete/collateral_atoms/gas_balance_atoms | 原startup/runtime/handoff AccountSnapshot及完整分页/身份核验，保存真实检查时点 |
| reconciliation.positions/open_hashes/foreign_risk | 与窗口token/attempt关联的最小原子facts；陌生账户事实仅foreign_risk=true，不导出完整隐私表；缺页不complete |
| loss_latch.latched/trigger_net_pnl_atoms/reason | 原同State sticky latch及首次触发真实net_pnl；latched只能true，未知损益不伪触阈值 |
| stop.stop_new_risk/reason/takeover_required/alert_status | 原运行stop状态及实际本地写/未来获准投递结果；stop_new_risk只能true |
| recovery.policy/state/reason | 已确认Mongo ARMED及后续只读HANDOFF/RECONCILIATION_REQUIRED；不带重建余额 |
| payout.status/payout_yes/position_net_atoms/claim_value_atoms | 原官方同market固定身份结果及原净库存，DRAW=0.5；未confirmed不算claim |
| payout.cash_received_atoms/tx_hash/observed_at/reason | 原SDK/同目标人工消费者的实际读回；本轮运行正claim无自动回收，cash=null；tx!=cash确认 |
| final.run_status/stop_reason/execution_complete/cash_complete/audit_complete/takeover_required/unresolved/positions | 原State/attempt实际闭合、原事件输出状态；未决数组逐单保留hash/closure/remaining，非计划满额；待兑付cash_complete=false |
| accounting全部金额/status/reason/mark_time/latch/claim/gas | §5从唯一原子State投影；任一未知相关派生null及INCOMPLETE/固定reason，已有K/P不丢；GAS未测为null |

snapshot quantity UNKNOWN可能使原advance_watermark拒绝，仍须发同身份UNKNOWN事实、保留原风险，停新增；不将它当成功apply。new snapshot部分字段Known但coverage不足不因schema合法变COMPLETE。conflict事件可披露原事实与CONFLICT，但不能先commit破坏旧水位。

原DTO真实缺口的最小补充：ApiCreatedOrder仅增加可缺/可null的 `removal_locked_until: Option<DateTime<Utc>>`，serde camelCase对应官方CreateOrderResponseData.removalLockedUntil（已读本地官方OpenAPI：RFC3339 string）；不向未定义该字段的ApiOrderData猜加含义。PredictFunTrader新增 `controlled_metadata: RwLock<HashMap<signed_hash,ControlledOrderMetadata>>`，类型归service/predict_fun/controlled.rs，父构造器及account.rs原synthetic trader factory只初始化空map。metadata精确存known removal时间、对应execution generation、chain_settled:bool、settlement_checked_at:Option<time>，不含金额/秘密；仅显式guarded hash登记，普通路径不消费。create成功捕获锁时刻；查询仍保留初始锁元数据，不能从缺失字段推定解除。原fills::read_order_execution在已有chain.settled调用结果后记录该代bool/实际检查时刻，不多发RPC；错误代明确false/null，不能沿用上一代成功时间。通过新增OrderVenue只读 `controlled_order_metadata(hash)`（默认None）给Broker投影，同hash/代不匹配不称CHAIN_SETTLED。其余snapshot/OrderTicket字面构造和原SDK不增必填字段。

固定错误映射：VenueErrorCode InvalidInput→SIGNED_BOUND_UNPROVEN（候选输入变化显式INPUT_CHANGED）；ExecutionNotEnabled/BudgetUnconfirmed/ReconciliationRequired→RECONCILIATION_REQUIRED；AccountMismatch→ACCOUNT_MISMATCH；ReadUnavailable→READ_UNAVAILABLE；FactIncomplete→FACT_INCOMPLETE；SubmissionUnknown→SUBMISSION_UNKNOWN；TxUnconfirmed→FACT_INCOMPLETE；SdkIncompatible→FACT_INCOMPLETE。内部累计减小/同coverage修改/overfill→FACT_CONFLICT；未知raw错误→READ_UNAVAILABLE或准备阶段FACT_INCOMPLETE，绝不输出原串。keyring Failure边界统一KEYRING_UNAVAILABLE。

Blocked需穷举：Halted/Deadline/LossLatch→decision.diagnostic_reason=RUN_STOPPED，order/stop.reason分别RECONCILIATION_REQUIRED/DEADLINE/LOSS_LATCH；OrderCap/MarketCap/TotalCap/BelowMinimum/NothingHeld/WouldCross/ThinBook/InsufficientCash/MarketRulesUnknown/ControlledRestUnsupported→decision.diagnostic_reason=BROKER_BLOCKED并保留原冻结Broker拒绝enum（decision原字段所允位置）；DataIncomplete→缺输入/CONTEXT_MISSING等原diagnostic，SettlementConflict→MARKET_INVALID并stop FACT_CONFLICT。不往SPEC order.reason增加任意Broker枚举；细分不允许输出处只用FACT_INCOMPLETE。原decision完整对象无Broker额外键时，仅保留已定义reason，不增自定义字段。

### 7.2 原supervisor首次write及ACK

control.py只增加新版分派和薄生命周期，旧validate_event_v1/v2/_EventRelations/unsigned相邻账务逻辑不改。新 `btc5m_live_events.py::validate_live_event`、`LiveRelations`、`LiveEventStore`在原supervise消费点被显式选中，版本来自started，不自动探测升级。关系验证为纯staged变更，schema/公式/关联通过后首次write，再flush/fsync/readback，才提交关系索引/previous并发关键order ACK；I/O失败既不提交关系也不重写该行，保留可能坏尾/合法前缀，停新风险。

LiveRelations只存证据关联和上次已验证累计值，不生成可交易余额或下单。需校验candidate唯一/冻结字段、PRE_SUBMIT→RESERVE→签名Prepared order→FINAL_SEND→MayHaveSubmitted/Submitted、同attempt hash/account/market/token不可变、venue ID只由null变首次值、六facts coverage单调、实际delta与上次已应用投影一致、重复0、remaining与原账务变更一致、latch不降、官方claim不加cash、final引用完整。拒绝含不相关attempt的ACK或execution。

拒绝的FINAL_SEND允许关联到已签Prepared并用明确NotSubmitted order/RELEASE终结，无PRE_APPLY。实际MayHaveSubmitted后即使后续reader无法证明FINAL_SEND链也不能隐藏execution；writer协议破坏后停止新增、保留原合格前缀/ARMED并宣布audit不完整，不伪造修复行/成功final。晚到合法facts在deadline后仍允许写，deadline只管新许可。

序列/容量在原同State出口预分配；输出失败位sticky。stdout阻塞可能延迟准备而触发最终时效拒绝，不在发送线性化区间输出。不能另造不可靠可丢旁路运送关键hash；observer旁路仍与交易协议无关。

### 7.3 文件、reader和结束裁定

新started.json精确沿SPEC §4.bis：schema_version、strategy_contract、operations_mode、risk_window_id、account_identity、authorization_ref、recovery_policy、cash_recovery_policy、asset_units、run_id、started_at、deadline_at、candidate_identity、public_config_identity。asset_units固定字段和单位；candidate_identity精确={main_head,bot_head,binary_sha256,files}，files为编译相关公开源文件的精确路径→SHA表（含本设计allowlist已存在源码、Cargo/lock、signer/SDK只读身份及加载模块）；不能复制环境。public_config_identity精确={sha256,initial_cash,max_order_usd,max_market_usd,max_total_usd,max_loss_usd}，金额100/2/2/10/20是分配参数不是假余额。

`candidate_digest`=按UTF8 canonical JSON（键字典序、无空白、ASCII转义、无NaN）编码{candidate_identity,public_config_identity}的SHA256，只含公开字节；Mongo/activation/live-context用同digest。最终文件hash在最后编辑/构建后采集，旧HEAD不能替代dirty文件身份。固定新候选binary路径见§9，不接任意--binary。

V1.1 的 candidate_identity.files 显式纳入 src/bot/runtime/live_events.rs、src/bot/runtime/live_events/types.rs、src/bot/runtime/live_events/tests.rs 最终字节：types是新编译依赖，tests用于离线证据身份（不声称被生产binary执行）。这三项与原§10精确源码/加载身份表合并去重，不另做全仓快照；模块路径不是schema版本。types/父投影/测试任一变化均不得继续把拆分前cargo证据冒充新候选通过，按§11.1仅补受影响Rust部分，后续真实消费链仍需自身完整证据。

所有证据在新唯一run目录exclusive-create，不覆写旧文件；创建started/public-config/live-context/events后fsync及父目录，order关键ACK在events同目标读回后才发。其他关键execution/latch/stop/payout/final也flush+fsync，不是掉电可靠金融恢复承诺；失败立即sticky stop/INCOMPLETE，崩溃屏障弥补拒绝重启，不自动重建可交易账。

ended.json精确沿SPEC：schema_version、run_id、exit_facts、final_event_seq、final_accounting、incomplete_reason、execution_complete、cash_complete、audit_complete、takeover_required。exit_facts精确保留launcher_exit、child_returncode、child_signal、forced_cleanup、stop_reason；无native结果用null而非0。缺final则seq/accounting=null、AUDIT_UNAVAILABLE、audit_complete=false；child非0/强制cleanup不能因一个final而健康。cash pending可正常停止观察，cash_complete=false且takeover；不能称账户清空。

2026-11-21轻量纠错：`ended.json`在上述精确字段外增加可空`incomplete_detail`；stop/final payload各增加可空`stop_detail`（承载原生已有的失败码，非法值按`UNKNOWN`）。二者仅为停机诊断留证，不改变任何停机、放行、takeover或reason判定。

新 `btc5m_live_events.read_live_run(directory)`只读上述started/public-config/events/ended/live-context；返回精确={schema_version:'btc5m-live-read/1',run_id,status,events,ended,reasons}，status=COMPLETE/INCOMPLETE/UNAVAILABLE，reasons为SPEC固定reason去重按枚举定义顺序。缺全新证据或历史signed-null→UNAVAILABLE/FACT_INCOMPLETE，不迁移旧行；坏尾/漏seq/漏final/identity不符→INCOMPLETE/OUTPUT_INVALID或AUDIT_UNAVAILABLE，不返回“已认证完整”的坏行。实际读文件重新运行同严格schema/LiveRelations、原子恒等式/coverage/费用方向/final关联，不写回、ffill或用余额反推缺失fact。

新reader是审计消费者，不建CLI/报表平台。核心验收必须是真实Rust producer→原control.supervise→第一次write→文件reader，不能靠一堆手工JSON纯函数替代；结构负例可注入同流的单字段破坏并spy首次write=0。正式报告只用既定 data/reports/2026-11-19-btc5m-live-parity-and-operations/report.md及evidence新叶，不另建任务镜像。

## 8. 官方结果、partial、取消与现金回收

复用paper::settle_from_facts/settlement_payout/same_round的纯官方身份/结果验证，不调用apply_settlement的虚拟现金。新域记录首个正fill的原官方market/yes/no/strike/时间/fee身份，仍要求BTCUSDT/300秒/固定起止价、非争议；本地spot/fair绝不结算。WON/LOST/DRAW分别给1/0/0.5官方兑付；冲突sticky停手。

原account.rs中历史/终态验证继续保留，不能仅以fills::closure_from_status的字符串分支放宽全部venue。MARKET partial FILLED需同已绑定MARKET request、原amountFilled和完整matches/pagination、原最终链/账户核对证据才能给Closure::Final{actual_q}；account::原终态检查不足以证明时UNPROVEN。accepted无数量就UNKNOWN；matched可能尚未chain settled；CHAIN_SETTLED仍不等于用户赎回。新测试先走原消费者现有终态证明接缝，不另造一套status判final。

remove回报removalLockedUntil、accepted/noop/rejected需保留已知锁时刻/unknown；remove accepted仅Removing，late fill照原hash应用；取消后查询无记录不释放。新域无自动链上cancel/invalidating nonce或新策略卖出；原cancel能力只在未来具体批准内复用。

首次官方正claim→WAIT_CASH及payout CASH_PENDING，冻结新增，不烧份额、不加B、不把cash_complete置真。0兑付按§5实现经济损失并单列残余份额；无需假redeem现金。人工另获目标/route/数量/Gas许可后沿原cli/sdk_ops/官网操作，receipt+同token余额/USDT读回才形成CASH_CONFIRMED的人工证据；失败保留同tx/hash并停止，不能自动重签。工程测试用原SDK fake reader证明这个区分，不修改或自动调用生产SDK资金入口。即使读到账，本run也不复READY；下一run仍须人工处置屏障，不以“人工以后会看”宣称资金自动连续复投。

### 8.1 已授权缺陷修复：缺失不等于矛盾

Pascal明确批准将paper提前停止缺陷并入正在开发的实盘修复。此项恢复07-004“缺失为Pending、明确矛盾为Conflict”及本SPEC §4.6的既有安全语义；不改RFC/SPEC版本、模型、预算或wire。§8原先复用二态same_round的实现方案在本修复范围内由下述三态取代，§10对paper.rs“helper仅可见性调整”的限制在本修复范围内亦由本节取代。

- 在paper.rs共用一个Match/Incomplete/Contradiction身份分类。已知market、非空token、时间、strike或非空feed矛盾优先；不能被另一字段缺失掩盖。缺失/空token或feed、缺必要时间/strike且无已知矛盾才Incomplete。保留严格BTCUSDT/300秒/有限正价格及两token不同；入场valid_round不放宽。
- paper未决且Incomplete时Pending，无回款、不释放成本、不因误报身份冲突停机；完整一致后仍走RESOLVED+CLOSED、非争议、赢家与价格交叉核验、DRAW及一次入账。已应用结果后读取缺失的身份或结算事实不撤销旧事实、不重复入账、不误报修订；已知身份、已知终价/兑付等与已应用事实明确矛盾仍Conflict并停手。完整但非终态/争议的异常反转不因本修复而自动获得通过。
- live必要身份/读取失败或异常不完整终态不产生虚假payout/现金，不清库存、预占或已有attempt_outcomes；首次停止使用已有DATA_UNAVAILABLE与接管标志，不恢复READY。完整同身份、无争议的正常非终态结果尚未发布不属于读取失败，按下节M-01分类保留Pending而不因未来终价/兑付缺省误停。已停止或WAIT_CASH保留原sticky停止原因，不能为改原因解除/覆写保护。真实矛盾仍FACT_CONFLICT。缺数据后恢复仅补有界只读事实，不解停手、不自动赎回/复投。
- 精确修复allowlist为四个既有BOT相对路径：src/bot/runtime/paper.rs、src/bot/runtime/paper/tests.rs、src/bot/runtime/live_accounting.rs、src/bot/runtime/live_control/tests.rs；允许修改其中必要子集。前三份生产/测试职责仍为原结算与同State账务，最后一份仅原live消费者回归；不新增模块/文件。相对§10原32路径仅追加paper/tests.rs这一测试路径，累计唯一范围33；不向其他阶段扩写权限。生产paper.rs仍须≤2400，live_accounting.rs≤1200；两测试文件≤2400，增长仅本缺陷矩阵，独立Validate审查，跨阈值/跨职责另报而非删断言压线。
- 先在原消费者取得缺元数据误判的RED，再修实现；至少覆盖单项/全部缺失、缺失和真实矛盾混合、恢复只入账一次、已入账后缺读与真实修订、live停新增保风险及原WON/LOST/DRAW。真实HTTP/category失败若未实际取证仍标未证，不把fake MarketData称真实HTTP验证。受影响Rust完整验证绑定最后候选；L1旧560绿灯仅历史，原L3及独立Validate覆盖本修复，无新增设计/验收阶段。

### 8.2 独立验收 M-01 最小修复范围

2026-11-20独立Validate run3908为REVISE：原Broker周期读取完整同身份的正常OPEN轮次时，未来end_price/payout缺省被误当DATA_UNAVAILABLE。此项为既有SPEC A-013/A-021/A-022实现缺口，不改变公开wire、预算、策略、恢复或授权；保留run3908报告及原候选，修后取得新的独立证据，不无修改重跑。

- 先在原Broker消费者取得正常非终态、尚未发布结果时应保持Ready/Pending的RED；补多次周期等待→完整结果一次应用，并在同一core/adapter/client/AccountGate两轮正例之间插入实际结算检查。正常等待不回款、不造claim、不释放成本/预占；不能用所有Pending放行或仅凭open绕开已知矛盾、争议/异常终态、必需身份/读取/mark故障。
- 保留§8.1已知矛盾优先、缺必要事实停新增、已应用事实缺读不撤销/不重入账、既有stop/loss sticky、正claim WAIT_CASH及无自动赎回/复投。区分待决结果分类与已应用结果的修订检查，不以全局放宽incomplete_result破坏另一消费者。
- 本轮严格允许修改且仅修改以下八个既有BOT相对路径的必要子集：src/bot/runtime/paper.rs、src/bot/runtime/paper/tests.rs、src/bot/runtime/live_accounting.rs、src/bot/runtime/live_control/tests.rs、tools/predictfun/btc5m_control.py、tools/predictfun/tests/test_btc5m_control.py、tools/predictfun/README.md、docs/LIVE-TRADING.md。后四个只随新二进制固定路径/SHA与候选身份断言/说明更新，不重写控制器。仍在累计33范围内，无新增业务模块；paper及两Rust测试≤2400行、live_accounting≤1200，Python两文件≤2400。必要回归复用既有fixture、不得削弱/删除旧断言凑行数。
- 新Rust输入必须产生新的候选二进制，精确新路径见§9。L3原29清单、run3907-final3与run3908证据只读保留；本轮四Rust路径属于获准变更，不再要求当前SHA等于旧29清单，其他旧清单路径仍逐字保护。对应Python身份回归必须校验新候选和精确变更分区，不跳过全部上游核对。最后编辑/构建/固定pin后采完整公开身份与digest，原独立Validate卡保留R1失败历史、挂实际Fix依赖并以新候选做R2。

## 9. 当前paper、冻结研究与候选隔离

当前 btc5m-baseline72-002，2026-11-19 12:12:10至2026-11-22 12:12:10 Asia/Shanghai；launcher56913/child56964/session proc_92911e09ac5f，原binary为ROOT/data/reports/2026-11-19-btc5m-observer-runtime-fix/evidence/validate-v11/cargo-target/debug/polymarket-toolkits。原SHA `09ac37334c644c354c5565e5da3e3836815c14bb03161c44386966efaf91eca0`；control `5590892add29593d71d5233e5c14d831da06bad0bee32822e41b966bcd8250f8`；observer `29edb8df1a2b1b1cbe02ee1f0b9ec613a7babe1eb54d3db245acdafb6b71f456`；publiccfg `cf27481d9f1931d06b7ef0d8bdfeee9dead2e3fa2b0153a1917f91c8c591a8be`沿主控已核身份。本卡不接触其进程/环境/期限/配置/加载行为、不重复启动/停止。

原control.run在1627局部import observer；observer._read_trading在968局部import control。当前supervisor结束时write_coverage的当前实现不直接调用reader，但不能据此排除独立后续消费者或__main__与模块名再导入。决定采用保守且可执行隔离：

1. 原fork Rust源码/新模块可以在获批allowlist内开发；它们不会替换当前已加载binary。所有cargo显式独立target，不使用BOT默认target或validate-v11目标。
2. 当前paper存活期间，所有既有 `tools/predictfun/*.py` 及其现有tests/README保持原字节；可新增未被当前run引用的新live模块/新测试，但不修改当前control加载或偷偷改import路径。新模块不是第二runner。
3. control.py及既有Python测试/README的接线必须等待原paper进程实际退出（含已留证的安全提前退出），并由主控确认原run收尾证据及动态加载消费者不再使用这些源码；仅墙钟过2026-11-22不构成许可。实际退出不等于72h完整成功。主控可以另批隔离候选源副本，但那是范围变更，本设计不自行复制现有工具到另一运行根。
4. T3可先完成Rust/新增模块离线工作；若仍需受保护Python文件，则在剩余必需步骤上真实block，不能把半成品complete。没有自动等待/重启/修改期限脚本。最终整体Implement仍须一套候选身份，经主控再放独立Validate。

run3904构建并供run3906/run3907/run3908核验的历史candidate-v1固定根为 `ROOT/data/reports/2026-11-19-btc5m-live-parity-and-operations/evidence/candidate-v1/cargo-target`，binary为其debug/polymarket-toolkits；整个旧制品保留不覆盖。M-01修复后的唯一新候选路径固定为 `ROOT/data/reports/2026-11-19-btc5m-live-parity-and-operations/evidence/candidate-v2/polymarket-toolkits`，由原scratch/btc5m-live-parity-build复用编译缓存执行locked/offline原生build后，仅将实际成功构建的binary复制至该不存在的新目标并核源/目标SHA，不复制整套target、不改candidate-v1。若新目标已有内容，须核真实来源后报主控，不覆盖或另换叶。control.py新域仅把固定binary路径及其实际SHA更新为此候选，不接用户--binary/target参数；生产激活前还须具体最终binary SHA批准，不因固定路径自动可信。旧unsigned72h原run及其binary/证据保持原字节。2026-11-20 Pascal明确授权新的72h paper窗口：原launcher的unsigned72h固定分支可在独立接线验收后改绑已验收candidate-v2；仅新窗口使用，不重启旧run、不改原资金/策略参数。legacy 6h入口及signed新域行为不变，不把旧hash永久施于新源码。

2026-11-20工程接线释放记录：原run已于2026-11-19 21:07:10 Asia/Shanghai因SETTLEMENT_CONFLICT提前停止，L3报告与原ended/final保留；主控在总卡续接前再次定向核原PID56913/56964已不存在，未见control/observer/bot业务消费者。仅对总卡t_9be36fdf释放§10既有四路径：tools/predictfun/btc5m_control.py、tools/predictfun/tests/test_btc5m_control.py、tools/predictfun/README.md、docs/LIVE-TRADING.md，完成原new-live薄接线和离线测试。旧run记录的control SHA仍是历史加载字节，不再作为获准编辑后的当前源码不变要求；原observer、公配置、旧binary、原run全部证据和17项冻结保护保持不变。当前binary与身份复用来源为L3/run3906及其run3904原生构建回执；不因此授权重启paper、实盘运行或解除独立Validate的HOLD。

冻结身份manifest为ROOT/data/reports/2026-11-18-btc5m-joint-forward-validation/evidence/review-preparation/final-freeze.json。已仅读该manifest；保护项是其files表13项、parameters引用1项、manifest自身，以及07-006 Design §2.2列明的两个旧binary：BOT/target/debug/btc_arb_phase1_history、ROOT/data/reports/2026-11-18-btc5m-joint-forward-validation/evidence/main-implementation/btc_arb_phase1_history-v1。共17项身份全部禁止修改/重跑/读中途评分；额外两个binary沿原已核SHA引用，Implement/Validate须从原冻结交接读取预期值，不能以当下任意hash自证正确。旧研究其他制品同样保留，不因未在17项中而可覆写。特别禁止phase1_history及其bin、joint/model/metrics/reference/history_input/history_performance/unified_data改动；新共享phase1方法增加不能修改这些冻结源字节或重跑旧研究。新build不改已冻结binary。

开收工逐项验证：全部冻结及附属清单SHA、旧参数/模型配置、活动paper原四身份/进程及源加载约定、默认target/原binary无覆盖、dirty范围归属。只hash旧研究字节不读取结果/评分；测试不启动paper/99日/14日研究。若核验必需动作被拒则block，不以旧PASS或本卡文档代替。当前本卡可选组合基线诊断因runtime inline+subprocess被拒，已OMITTED并记Kanban；没有换包装重放，所以本文不声称本run重新核过冻结SHA/活动PID。

V1.1仅文档修订，不创建这两个Rust文件、不采集上述运行/冻结组合诊断、不构建；原V1.0组合诊断及L1 session20261119_154343_0fbae1 message120348/120349的import/mut清理均保留NOT_EXECUTED/OMITTED，不换包装/工具/解释器/执行者重放。新增types/tests仅限未来获批L1实现候选，仍遵守本节全部paper/冻结源/binary/Python加载隔离；本文静态自检不是新的运行身份核验，也不解除triage/hold。

## 10. 后续精确allowlist与G3

本卡仅本文可写。下表为V1.1主控及独立Design Gate之后的T3 proposal：原30路径加且仅加 live_events/types.rs、live_events/tests.rs，共32个唯一BOT相对路径，不授权目录或所有功能。单测colocated（含明确的cfg(test)子文件）；主仓tests不加模块单测。已有L1接缝按§2增量识别，表中“新增”描述相对原V1.0基线的交付职责，不声称当前全部缺文件。L1恢复时仅将新增这两路径及父live_events.rs职责写回原卡scope，不连带释放受保护Python或其他lane。

| 精确路径 | 修改/新增与函数边界；真实缺口 / 最小验证 |
|---|---|
| src/main.rs | 修改仅新live参数整组解析/公开manifest交接/原controlled分派；部分参数/错入口0凭据；旧CLI回归 |
| src/config.rs | 修改仅注册controlled_live、ControlledRun.live字段/原构造器None及新解析委托；旧预算解析不变 |
| src/config/controlled_live.rs | 新增typed公开上下文/固定模式/期限/单位/Gas检查及colocated测试 |
| src/bot/arbitrage.rs | 修改仅phase1新live提交await分派、正net反馈与新域数据失败sticky停手；原core/observer/legacy不重写 |
| src/bot/arbitrage/phase1.rs | 修改仅Phase::FinalSend及recheck复用、候选必要只读signed-bound身份accessor；无模型/参数/公式改动 |
| src/bot/runtime.rs | 先原样提取Broker::take到taker.rs；仅State/Broker新元数据、Ctx新域装配、observe/settle/drive/log_summary薄hook，普通分支不变 |
| src/bot/runtime/taker.rs | 新增：原take主体同义迁移、所有phase1裸BUY拒绝；原Predict实际snapshot结果接同一应用出口；不重写其他venue |
| src/bot/runtime/paper.rs | 提取上述四phase1方法至phase1_control；emit_phase1_evaluation/finish/emit_final极小new-live分派；纯官方结果helper仅pub(super)可见性必要调整；paper现金/原v2算法不变 |
| src/bot/runtime/phase1_control.rs | 新增：提取四方法、旧paper签名/行为不变，live读取原State.live受控元数据；不迁paper账本 |
| src/bot/runtime/live.rs | 修改仅controlled元数据字段、apply_snapshot实际应用结果接缝、sync/seed/runtime-account检查前后typed投影、必要crate可见性；advance_watermark及旧unknown保护保留 |
| src/bot/runtime/live_control.rs | 新增：同Broker候选live流程/原子发送guard/运行状态/停止与原有界收尾 |
| src/bot/runtime/live_control/channel.rs | 新增：原stdin新域ACK/D/EOF、有界等待/一次性许可；无网络/秘密 |
| src/bot/runtime/live_control/tests.rs | 新增cfg(test)：同core→原Broker→原Predict适配器synthetic/clock/channel/文件原生fixture，A-001–006/010/012–022 |
| src/bot/runtime/live_accounting.rs | 新增：唯一原LiveState原子投影/估值/claim/loss/Gas域检查，colocated边界测试；不建第二账本 |
| src/bot/runtime/live_events.rs | 原新增候选收敛：typed source投影/有界序号与原stdout出口；私有注册types/tests并显式re-export，校验委托types；不内嵌wire定义/测试 |
| src/bot/runtime/live_events/types.rs | V1.1新增：§7.1严格wire结构/枚举、常量键表、递归/标量校验、纯序列化；无State/venue消费者/应用/输出/序号所有权 |
| src/bot/runtime/live_events/tests.rs | V1.1新增cfg(test)：原8例同义迁移，保留名字/全部断言/注释及私有可见性意图；补typed/schema/真实snapshot与AppliedExecution投影反例；不替代live_control原生链 |
| src/service/venue.rs | 修改仅SignedExecutionBound/ControlledSendGuard、controlled_reservation_atoms/place_controlled_tracked默认拒绝、controlled_order_metadata默认None；不改旧ticket和TakeResult形状 |
| src/service/predict_fun.rs | 先提取request_text/authed_text/authed/authed_write原方法到request.rs，注册controlled；ApiCreatedOrder可空锁字段、trader metadata空map初始化；新域无await末端hook，普通请求行为保留 |
| src/service/predict_fun/request.rs | 新增：上述同义请求/认证方法及prepared单次发送future接缝，colocated401/EOF-before-first-poll测试；读refresh/写NoReplay不变 |
| src/service/predict_fun/controlled.rs | 新增：guarded调用、已签cash/net界限与request首次poll封装，原signer/chain/route直接复用；colocated非零fee/partial正反例 |
| src/service/predict_fun/fills.rs | 修改仅place_tracked共用内部prepare/guarded调用薄接线、check_signed_bound显式新域费方向分派、order锁及原chain.settled实际结果捕获、必要终态消费者映射；旧rest/cancel/parser算法不重写 |
| src/service/predict_fun/account.rs | 修改仅注册account/controlled子模块、原synthetic trader factory初始化metadata空map；原账户/RPC/分页/终态保护不重写 |
| src/service/predict_fun/account/controlled.rs | 新增：原AccountGate同锁prepared-self检查及测试；复用现有终态验证接缝，不清账户失败 |
| tools/predictfun/btc5m_control.py | 待§9条件满足后修改build_parser/run/supervise/check_paths/public_identity/start/ended的new-live薄分派；旧v1/v2/observer加载字节行为保持 |
| tools/predictfun/btc5m_live_guard.py | 新增：同进程lazy Mongo薄接缝、固定公共activation校验、OS锁；fake后端注入仅测试，不作新runner |
| tools/predictfun/btc5m_live_events.py | 新增：严格schema/关系、首次耐久write/ACK、本地stop及只读read_live_run；无下单/资金权限 |
| tools/predictfun/tests/test_btc5m_live_guard.py | 新增：标准库unittest/fake pymongo collection、跨run/window/模式锁与崩溃屏障，0真实存储/凭据 |
| tools/predictfun/tests/test_btc5m_live_events.py | 新增：Rust原生fixture→原supervise→磁盘reader、破坏首次write、fsync/ACK/EOF竞争、单位/秘密负例 |
| tools/predictfun/tests/test_btc5m_control.py | 待§9后仅新参数/新身份表/既有固定child测试适配，旧断言不删/skip；已有套件回归 |
| tools/predictfun/README.md | 待§9后仅07-007小节：新模式/冷启动拒绝/手动现金/授权/固定候选路径，旧命令保留 |
| docs/LIVE-TRADING.md | 修改仅07-007候选差量说明与signed-null兼容限制；不改其他venue或真实操作授权 |

明确只读：Cargo.toml/Cargo.lock、所有requirements/venv、local_signer.py/cli.py/sdk_ops.py及原SDK测试、account原读取算法、spot/observation/quoting/models、observer生产/测试、history/replay及冻结研究、全部既有public config/activation生产文件/凭据/旧证据、上游RFC/SPEC/其他Design/模板、根规则/skills/profile/其他项目。新回归复用SDK测试不等于允许修改它们；发现必须改只读路径先给具体编译/消费者证据交主控调整scope。

G3原V1.0行数来自当时read_file.total_lines实际返回（不是拒绝命令结果）：arbitrage1493、phase1 1566、runtime2370、paper2378、live1957、venue567、predict_fun2392、fills1972、account2390、config1420、main275、control1722、observer1159。本次定向实读live_events1356；run3882的其他候选行数/SHA沿主控卡面交接，不用原行数冒最终候选。父文件受控扩张/架构例外方案如下，不以删除注释压线：

- runtime先把单一take主体508–767迁runtime/taker，释放本次必要live接线空间；不动rest/quote或其他策略。predict_fun先将request_text及四个authenticated方法迁request，正好覆盖本轮“最后token await后守卫”职责，不迁client/market/签名实现。paper先迁四个模式/clock方法再加分派，保留现金主体。三者最终各≤2400；迁移前后旧入口/构造/请求次数必须等价回归。
- account只加module声明及synthetic构造器空map初始化，新方法在其子模块内扩展AccountGate，可访问父私有状态，account仍≤2400；不把2390行直接堆过2400。live、fills、phase1、arbitrage/config/control仅上述接缝受控增长，复杂逻辑和新测试放新单职责模块，不超过2400；这是本Principal明确边界与独立Validate要求。
- 新生产模块目标≤1200；测试live_control/tests可1201–2400，职责仅该新域完整原生链/故障矩阵，独立Review检查。若新模块拟越1200或现有父仍越2400，先停止增长给主控具体分拆修订，不把本表视为无限G3豁免。≥3600绝不新增；本文未授任何豁免。
- live_events.rs及live_events/types.rs各自最终物理文件≤1200行（含注释、空行、声明，不仅扣除cfg(test)后计数）；live_events/tests.rs同职责目标≤1200，不能借live_control/tests的特定档位放大。本次先移原8例和wire定义/语法校验再补严格types，父文件不得在1356行上继续叠加。保留全部原测试断言/注释，不压行、删注释、塞进live_accounting/其他无关模块或新增第三文件；拆后仍超界则给具体职责/行数证据block，不默认豁免。
- 拆分顺序同义提取→旧回归→新增guard/wire/投影→正负例；不做全仓格式化/清理。下一次跨职责新增或越本档即触发新的设计，不批量搬历史测试。

## 11. 实现、验收与证据闭合

实现顺序：§9保护前提 → 原方法同义提取及旧兼容 → 模式/typed原子投影 → guarded同消费者+FINAL_SEND → Mongo/锁fake → 严格producer/首次write/reader → §9允许后原launcher接线 → 最终身份/定向回归 → 独立Validate。既有预建图不另派同卡Review；主控核三实体与allowlist后才解除T3 hold。未闭合Blocker/Major/Minor必须REVISE，不能“带major通过”。

### 11.1 V1.1窄迁移、测试身份与责任

迁移顺序（在原L1恢复且scope写回后执行，本卡不执行）：

1. 以原live_events.rs:1174–1356的cfg(test)模块为源，去外层mod包装移至live_events/tests.rs，父改为cfg(test) mod tests；原8个函数名、注释、全部assert/assert_eq及期望本地错误token保留。只为文件拆分补必要import；不挪到live_control/tests、不删/skip/ignore/弱化断言。
2. 将§7.1指定常量/类型/键表/纯语法校验同义移至types.rs，父显式re-export和validate委托；保留原emitter/源映射/序号/输出在父。先做纯移动的受影响Rust回归，确认测试完整限定名仍为 bot::runtime::live_events::tests::<原名>，无需为物理拆文件改测试路径。
3. 在types职责内落实既有SPEC严格10种payload/六facts/六delta/数组/required-nullable/拒重复键等目标，父生产入口改typed并接同一次snapshot/AppliedExecution。旧8例如需适应typed构造，只改fixture构造/序列化和负例注入位置，全部原断言和预期不改：合法typed对象序列化后注入坏键/缺键/坏reason/false latch，仍调用生产同一validate；禁止cfg(test)替身校验或影子emitter。新缺口另加定向反例，不能把旧schema单测夸大为真实账务恒等式/消费链。
4. 同一运行共享emitter/seq/lane/pending等原T3接线在既有落点继续完成；snapshot→typed event→编码/输出和apply真实增量需覆盖未应用null、确知重复0、UNKNOWN、coverage不足/冲突、零成交仅vwap N/A、非零份额fee。types不重算这些业务事实。逐文件确认生产≤1200，再运行下述受影响测试/check并登记新候选身份；不做全仓快照或为迁移强加新测试总数门槛。

原测试身份与语义（8项均为保全清单，不是新验收数量门槛；同一前缀 bot::runtime::live_events::tests::）：

| 原函数名 | 必须保留的全部原断言所覆盖语义 |
|---|---|
| a_stop_event_round_trips_the_schema | 合法stop envelope经同一生产validate返回Ok；非手工另造通过器 |
| an_unknown_key_is_refused | extra键拒绝，原期望UNKNOWN_KEY:extra不变 |
| a_missing_key_is_refused | 缺takeover_required拒绝，原期望MISSING_KEY:takeover_required不变 |
| an_unknown_reason_is_refused | 非白名单reason拒绝，原期望REASON_INVALID不变 |
| a_latch_may_not_be_reported_as_unlatched | latched=false拒绝，原期望LATCHED_INVALID不变 |
| an_atom_amount_is_canonical | 0及规范整数字符串通过；01、负unsigned、空串、-0、1.5拒绝，-20 signed通过，原全部断言保留 |
| a_hash_is_strict | 0x+64hex通过、63位或非hex拒绝，原全部断言保留 |
| the_reason_set_is_closed | OUTPUT_INVALID通过、WHATEVER拒绝，原全部断言保留；通用/decision集合仍按SPEC分离 |

责任分层：live_events/tests负责上述保全、typed结构递归负例和父真实snapshot/AppliedExecution投影（A-008/009及A-007编码出口部分）；live_control/tests仍负责原core→Broker→Predict适配器→共享emitter的真实原生正反例与seq/lane/ACK/FINAL_SEND/父stop竞争（A-001–006/010/012–022），不能换成types自造量；tools/predictfun/tests/test_btc5m_live_events.py仍负责A-007/008/010/011的真实Rust producer→原supervise首次write/fsync/ACK→磁盘reader终链，原Python保护解除前保持未完成，不以Rust局部绿灯替代。

纯types/tests拆分仅需补跑受影响Rust：下方live_events过滤覆盖原8例及新增严格/投影回归，live_control过滤覆盖导入门面及实际生产接线，live_accounting过滤覆盖跨模块投影依赖，并以原cargo check --all-targets验证其他调用者/测试构造。原有phase1/paper/live/adapter/request/account的结果仅在候选、输入、依赖与运行条件仍适用时复用；若typed签名/实际consumer接线影响这些路径，则补其对应过滤，不一律重跑整个crate/仓库、Python或冻结研究。完整07-007交付仍须下表全部适用验收，未来Python接线后才跑受影响Python终链；不新增固定通过总数，476结果不是迁移后的验收证据。

### 11.2 原24项验收与命令映射

全部工程测试离线，现有SyntheticTransport/fake clock/keyring/SDK/collection；调用真实keyring/API/RPC/DB/外部告警即失败，传入隔离environment防默认.env回落，fake signer必须走原sign_order测试接缝而非真实签名。真正缺依赖不安装；ROOT/.venv/bin/python复用上游已核pymongo4.17.0/eth-account0.14.0/jeepney0.9.0，SDK原专用venv不变。T3须用项目解释器实际import local_signer并在patch secrets为fail的条件下验证兼容；T2未执行该import，不宣称兼容已经动态通过。

| SPEC验收 | 精确最小可证伪场景 / owner |
|---|---|
| A-001 | live_control/tests：同真实core/因果input/clock，原paper与guarded live逐字段对拍；旧cash-edge反例、Down同值及阈值邻值 |
| A-002 | 同原装配显式opt-in/默认兼容、Coinbase paper可用/live0sign+POST、observer0attach |
| A-003 | RoundTaker→Broker→PredictFunTrader健康非零fee；裸BUY/错revision/market/route/fee/q/signed ratio各0POST，live PaperCash=None |
| A-004 | 每个account/book/authorize/sign/token/ERC1271/ACK await注入clock/EOF/stop/loss；30秒、5秒、10秒边界等号及邻值；首poll前stop0POST |
| A-005 | 原adapter accepted→partial FILLED→有证明terminal partial，只应用actual净增量；late fill在deadline后仍记 |
| A-006 | 原单hash timeout/missing/later fill/settled，原POST计数1、新salt/sign计数不增；旧generation/矛盾fee停手 |
| A-007 | live_control/tests真实core/Broker/adapter→父live_events emitter（types编码，非手拼JSON）→test_btc5m_live_events.py中的原supervise→events文件→read_live_run→final；events单测不替代终链 |
| A-008 | live_events/tests保全8例并验证types六facts/六delta/单位和所有键递归负例；Python原首次write消费者复验重复键/非有限/bool/版本混流/非法ID先拒再write；合法未知可null不能补0 |
| A-009 | 原live::tests的apply同coverage/迟费补齐/重复/UNKNOWN，父live_events真实AppliedExecution→types delta在live_events/tests对拍；仅真实commit增量，share fee不再扣现金，实际fee不从模型推断 |
| A-010 | 在order write/flush/fsync/readback/ACK/FINAL_SEND/首poll/响应/apply/ended各点注入崩溃；0POST或可能发单分类精确，坏尾不补final |
| A-011 | 原native exit与final独立：child失败/kill/缺final/未决/坏关系都非健康，claim cash_complete=false |
| A-012 | 两真实隔离fake-launch进程同账户跨run/window/值守争锁至多一child，第二0交易secret；unsigned无锁 |
| A-013 | fake pymongo通过原薄接缝单次insert majority+j/primary majority精确读回；首启READY及同健康进程两不同轮非零费执行；fsync失败0POST |
| A-014 | 退出/崩溃/父死子活/换run/window/日期/OS锁释放，原ARMED仍0secret/child；无自动重启 |
| A-015 | 原子损益−20及±1atom、浮亏/费用/结算同tick第二单、回升不解latch，未知mark立即停，BNB不加USDT |
| A-016 | 绑定变更/普通budget bool/缺hash/坏日志/伪零仓不能恢复；无reset/resume/删屏障命令，旧窗口保留 |
| A-017 | keyring正常/locked/Prompt及签名失败、账户缺页/断流/旧mark；spy 0Unlock/fallback/秘密重读循环，已知K/P不消失 |
| A-018 | EOF在每await、ACK前后及首poll Pending竞态、parent异常/native结果、writer/alert失败/期限：stop不可越过许可，已可能提交不得假未发 |
| A-019 | 复用原remove/query实际consumer，locked/remove accepted/noop/rejected+late fill，只有终态核算全才释放，空列表非证明 |
| A-020 | 每单/市场/总额/真实cash及并发预占独立卡边界，等号/超1atom，R0被实绩超越则保留高风险/halt，不双算、不缩单 |
| A-021 | 原官方pure事实WON/LOST/DRAW/pending/争议→claim WAIT_CASH→原SDK fake receipt+同目标读回，0自动approve/redeem，零赔付无现金 |
| A-022 | 首单/策略pilot/无人授权分开，第一笔成功不自动无人；本地fake不DELIVERED，不称无限恢复/连续资金回收 |
| A-023 | 原signer/SDK/07-004/005受影响回归及旧v1/v2、普通live/paper消费者；复用未变独立证据，不削旧断言；真实副作用计数0 |
| A-024 | 最后编辑后候选SHA、全部冻结/附属清单、旧binary/当前paper四身份与动态加载条件、独立target、未碰配置/进程/旧证据 |

计划命令（非T2已执行；cwd除说明外均BOT；Rust使用现有locked/offline缓存，不能跑ignored联网test）：

```text
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::live_control::tests -- --nocapture
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::live_accounting
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib service::predict_fun::controlled
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib service::predict_fun::request
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib service::predict_fun::account::controlled
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::live_events
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::live_events::tests -- --list
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::arbitrage::phase1::tests
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::paper::tests
cargo test --locked --offline --target-dir <当前profile-scratch>/btc5m-live-parity-build --lib bot::runtime::live::tests
cargo check --locked --offline --all-targets --target-dir <当前profile-scratch>/btc5m-live-parity-build
/home/pascal/workspace/yquant-investment/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_btc5m_live_guard.py
/home/pascal/workspace/yquant-investment/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_btc5m_live_events.py
/home/pascal/workspace/yquant-investment/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_btc5m_control.py
```

尖括号为当前worker实际scratch绝对路径占位，执行前替换，不能字面执行；pytest/cargo subprocess fixture必须显式同独立target，不能回落BOT/target或当前paper target。上述命令是T3/Validate计划，本次V1.1仍只静态检查、不执行cargo或Python业务/fixture。live_events过滤同时匹配父/其types/tests，tests --list仅核原8个完整限定名和新增案例发现，非通过证据；实际执行必须非空且记录原8例结果，不把filter0test或--list当通过，也不新造固定总数门槛。既有SDK/local_signer测试用原专用venv及原已核命令，只有解释器兼容/调用影响才补跑，不重复后端真实keyring验证。原native fixture支持通过cfg(test)专属过滤test并输出真实事件；不是生产binary业务入口。

候选binary仅在整体验证后以显式 `cargo build --locked --offline --bin polymarket-toolkits --target-dir <§9新candidate-v1/cargo-target>` 构建，禁止cargo run/真实启动。命令允许范围不等于runtime必然批准；安全拒绝停该动作和依赖，普通断言/参数错误可按原scope修复。记录实际argv/cwd/native exit/覆盖/未运行项/最终HEAD+源码+binary SHA，不拿管道末端0或开发者摘要替代独立Validate。部分成交真场馆难触发仍保留离线分支，单笔真全额不证明全部分支；offline PASS不代替以后venue生产验收。

## 12. 风险、未决与交接

业务/架构未决冲突：0；本设计不是production-ready声明。所有planned实现有§10落点及§11反例；没有以“留Developer自由决定”掩盖阻断finding。实际部署绑定/collection物化、majority+j保证、项目解释器动态兼容、最终候选、真实资金与Gas/期限/退出/接管/告警渠道都必须后续验证/具体批准，当前缺失安全默认不启动，不把它们伪装本卡实现失败或自动放行。

| 剩余风险 | 当前处理 / 以后最小Gate |
|---|---|
| Mongo凭据或绑定被换、物理耐久不达 | 固定绑定/唯一_id/ACK及读回，trusted operator边界；未来批准具体部署/集合与写，不能凭fixture宣称生产可用 |
| current paper动态加载 | §9要求原进程实际退出及主控确认，安全提前退出不冒完整成功；总卡仅按已记录四路径释放，不放开observer或原运行证据 |
| 原子账投影、reqwest首次poll和ACK错误 | 原生消费者与故障注入逐边界验证，失败REVISE，不靠event文件漂亮推定资金安全 |
| loss/Gas/late fill越阈值 | 停新增而非保证封顶，原hash持续风险；禁止清latch/重签，人工接管 |
| 单host锁及同UID信任 | 不防恶意管理员/外部客户端，真实账户须独占声明，非分布式OMS |
| 资金回收暂停 | WAIT_CASH/MANUAL_PAUSE，原SDK手工另批；无自动连续复投/跨重启恢复 |
| alpha与真实场馆未证 | 离线工程、有人首单、有人策略pilot、无人受限实测独立裁定，不以盈利或在线时长冒工程证据 |

后续主控审核三实体/版本/源码映射/G3/allowlist和零未闭合finding后，才调整预建Implement范围并解除hold；本worker不解除该hold、不自行建真实运行。Implement完成释放预建独立Validate；主控再分别申请有人首单、策略pilot、无人小额的具体账户/链/版本/金额/次数/期限/退出/取消/人工回收/Gas/接管授权。生产Mongo、权限、外部告警、服务/调度或依赖变更没有随工程自动授权。

来源：

- [07-002 Design](DESIGN-07-002-predictfun-live-foundation.md)、[07-003 Design](DESIGN-07-003-predictfun-wsl-nonexport-signer.md)、[07-004 Design](DESIGN-07-004-btc5m-controlled-paper.md)、[07-005 Design](DESIGN-07-005-btc5m-phase1-correctness.md)、[07-006 Design](DESIGN-07-006-btc5m-post-entry-observer.md)；本轮只引用，不回写历史。
- [07-002 closeout](../../../data/reports/2026-11-13-predictfun-live-foundation/closeout.md)及上游/主控Kanban独立签收；不是本卡重验业务结果。
- [官方Place orders](https://dev.predict.fun/trading/place-orders)、[Fees](https://dev.predict.fun/trading/fees)、[Order lifecycle](https://dev.predict.fun/trading/order-lifecycle)：2026-11-19公开浏览器读取，非私有API或交易验证。
- [范围评估](../../../data/reports/2026-11-19-btc5m-live-and-hybrid-assessment/report.md)仅线索，当前源码优先；[final-freeze身份清单](../../../data/reports/2026-11-18-btc5m-joint-forward-validation/evidence/review-preparation/final-freeze.json)仅读manifest、不读评分。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-11-19 | 冻结同core live薄适配、末次await/耐久ACK后原子发送许可、实际原子量投影、单账户Mongo拒绝屏障与人工现金暂停、当前paper隔离、精确allowlist/G3及24项离线验收映射；只交设计 |
| V1.1 | 2026-11-19 | 仅live_events有界拆分：新增types.rs/tests.rs两路径、allowlist由30到32；同步§4/7模块/wire归属、父re-export/import/私有可见性、§9保护/候选身份、§10物理文件G3和§11原8例保全/迁移/受影响Rust回归/真实producer终链；RFC/SPEC仍V1.0、wire仍btc5m-controlled-live.v1，经济/字段/恢复/授权不变；不实现/运行、不解triage/hold |
