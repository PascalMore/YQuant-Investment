# RFC-07-007: BTC5m live 一致性与有人/无人值守最小运行安全

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | Draft V1.15；R16 T1 RFC/SPEC 候选，待主控 Gate；不是 R16 实现、独立 Validate 或真实运行通过 |
| 本次窄修订 | V1.15，2026-11-23：R16 拒绝诊断、R15 三 minor 闭合要求、本 run 精确 claim 归属及有界 WAIT_CASH 驱动恢复；现行增量见下节，历史版本原义保留 |
| 作者 | YQuant Principal / yquantprincipal |
| 创建 / 更新 | 2026-11-19 / 2026-11-23，Asia/Shanghai（UTC+08:00） |
| 工作区 / 来源任务 | /home/pascal/workspace/yquant-investment；初版 t_b946f2c3；本轮 t_3691ff23 |
| 来源决策 | Pascal 2026-11-23 已批准本次受限 Full 研发及离线验证；不包括部署、生产选择器/activation、签名授权或资金动作 |
| 对应 SPEC | [SPEC-07-007](../../spec/07_trading/SPEC-07-007-btc5m-live-parity-and-operations.md) V1.15，§R16 为本轮可计算契约 |
| 后续 Design | [DESIGN-07-007](../../design/07_trading/DESIGN-07-007-btc5m-live-parity-and-operations.md) 已存在；本卡只读，R16 映射由下阶段修订，未对齐前不得 Implement |
| 依赖 | 07-002 V1.1、07-003 V0.5、07-004 RFC/SPEC V1.1 / Design V1.3、07-005 V1.0、07-006 V1.1；实际能力以当前源码及独立证据为先 |
| 角色 | 主控 Gate/Closeout；Principal Design；Developer Implement；Reviewer 独立 Validate |


## R16：本轮生效增量（2026-11-23）

本节与 SPEC §R16 V1.15 成对生效；仅替代下文旧阶段状态、已完成能力的待办表述、WAIT_CASH 立即结束及“已精确回收仍不能在本 run 继续”的解释。参数化、同 core、实际账本、原 reason、10s 门禁、所有风险限额与冷启动拒绝不变。Design 当前至 R15 的映射不是 R16 已实现证据；下阶段只补本节真实缺口，不重做平台或原账本。

### R16.1 已验基线与真实差量

基于 [2026-11-23 只读诊断](../../../data/reports/2026-11-23-btc5m-live-diagnostic/report.md)、t_239d0c0c 独立交接及本轮源码静态核对；本文不重跑其业务测试。

| 分类 | 事实 / 定位（路径相对 BOT，符号优先于行号） | 本轮处置 |
|---|---|---|
| 已验离线 R15 | `live_control.rs::check_locked` 在 facts/ACK/permit 仍校验 receipt 完整性、identity、generation、attempt 和 10s；`account.rs::read_account_snapshot` 五腿并发、`reconcile_account_history` 闭合历史记忆化；`fills.rs::place_controlled_tracked` 复用 tick 账户读及独立读并发 | 保留，不重复实现。reviewer run4022：lib638 passed/0 failed/4 ignored，集成15/2/2/4；属上游证据复用，不是本卡新测试 |
| 性能证据边界 | 固定170ms、9次合成：24 calls，book→facts p50约0.860s、旧 end_to_end p50约2.234s；fixture 无历史 hash；before 重复 key/旧标签 | 不能称同版严格前后比，也不能称生产≤5s；按 SPEC §R16.3 修复测量与报告，旧制品原字节保留 |
| R15 三 minor 未闭合 | before JSON 重复 key/旧标签；并发 history 的 `market_for_token` 可能早于 `read_positions` 的 `remember_market`；balances/authorize 双故障优先级缺反例 | 本轮承接闭合，不改 t_239d0c0c 历史 PASS；验证未通过不得以该 PASS 上线 |
| R13 已有局部恢复 | `live_control.rs::credit_claim` / `promote_pending_claim`、严格 reader 的 CASH_CONFIRMED 撤销 CASH_PENDING 已有实现 | 保留精确 atoms 与其他 stop 不可清的规则；已有局部单测不证明 drive 续跑 |
| R16 缺口 A | `live_control.rs::RunControl::must_end`（当前230）将 WaitCash 视为结束；`paper.rs::wait_controlled_stop` → `runtime.rs::drive`（1609–1611）即 finish/return | 区分临时停新增与终止，原 drive 在有界等待读取、精确恢复后继续同 run；不新建 runtime |
| R16 缺口 B | `account.rs::reconcile_account_history`（761–764）跳过 bound_orders；`live.rs::claimed_payouts`（1058–1095）只消费 snapshot.claimed_win，后接 `check_runtime_account` / `credit_claim` | 补本 run 已闭合实际库存的兑付证据接缝，区分启动历史 claim 与本 run 回收，保留唯一账本与旧累计去重 |
| 生产激活缺口 | run018 绑定 R14 SHA256 `96a7ed059eb13253f36c8dd6bd8abf42a803574b7b8171bfa698b1aad7b1e1b7`；上游核验 R15 候选 `bcb5a8c0841df89a403dd4606f951f9f7965ecfe55f58e1bbb33e31f38b75d5c` 未部署 | 不切 selector、不重新授权、不新开 live/paper run；未来另行明确授权 |

run018 是 PredictFun/BSC，不是 Polymarket/Polygon；35 attempts 中34次 NOT_SUBMITTED/INPUT_CHANGED、1次成交，非34次交易所拒单。按 order wall 近似有14次拒绝时 spot/book request age 均≤10s，不能全部归因过期。09:55:06.275 CST CASH_PENDING 后5.407s现金增加2.0384 USDT且持仓空，但原 seq1092 reconciliation 不完整、reader INCOMPLETE/FACT_INCOMPLETE、没有 CASH_CONFIRMED；停机后独立对账不能追认原 run 闭环。mark_time 的缓存最小时间与暂时 generation 失配不另扩为本轮根因。

### R16.2 冻结决策与边界

1. 拒绝按事实区分：无机会/经济规则的正常拒绝；首次可能发送前的本地门禁拒绝；确有权威终态证据的交易所拒单；可能发送后结果未知。只有明确未提交才释放该 attempt 未用预占；Unknown 不清 tombstone/余量、不重发。诊断只在既有 decision/order 流兼容增加有界 stage/detail/检查时钟及 age，不改变 reason、不新建 stop 词汇、不记录 raw 响应/凭据；具体封闭字段见 SPEC §R16.2。
2. 本 run claim 只来自本 run 实际闭合 attempt 的同账户/市场/token/净份额，官方结果与原绑定一致；按 atoms 核对库存减少及现金全量等式，两项缺一不入现金。交易增量与claim现金/库存变动在等式中互斥单列，启动前历史 claim 已在开仓 baseline 中，不再算本 run 收益。现金或官方结果先被不同消费者看到均可暂存证据；账户适配器已证明同目标官方兑付/库存移除/精确现金但runtime尚未消费结果时也立即停新增并进入同一有界等待，最后用同一规则核销一次；不能直接 mock claimed_win 代替适配器完整证据链。
3. 精确恢复还要求：所有正 claim 已核销、剩余经济持仓/挂单/预占/在飞为零，费用与当前 generation 账实闭合、receipt 新鲜；没有其他 stop/loss/degraded/父失联/输出故障且原 deadline 未到。旧现金等待不能遮蔽等待中新增的硬终止；保留原 CASH_PENDING 事件及后来终止证据，不能因首因记录为 CASH_PENDING 就清除后来保护。
4. 等待上界复用现行 SPEC §4.6 的600s只读上限（现有 `live_accounting.rs::LIVE_TAIL_BUDGET`），逻辑名为 CASH_WAIT_BUDGET=600s，而非 R14 READ_FAILURE_BUDGET=120s。从首次可归属正 claim 的 CASH_PENDING 进入时起（含账户适配器先有证明而runtime结果稍后消费的顺序），以包含暂停的双时钟、600s或原 deadline 任一先到为上界；重复结果、部分回收、成功读或读失败均不重置。等待内0新增风险，只复用原只读账户/订单/官方结果消费者；不触发自动 redeem/SELL/提款/approve，也不延长授权。准确触发、清除与终止规则见 SPEC §R16.5。
5. 选择600s是沿用已批准只读上限、避免新调参/调度或猜测兑付SLA的最小政策，不是延迟分位数推导。5.407s仅单次观测，真实领取/到账延迟分布未验证；等待可超时而保持未闭环，不保证人工会在600s内操作。终止后只做原安全收尾，绝不重新开放风险。
6. ≤5s定位为工程目标，不增加或放宽发送准入阈值：主指标从本 tick 首次账户采集请求发起到原子发送许可最后检查完成；另列决策盘口 receipt→同一检查的时长，账户/spot/盘口 receipt age 和 spot/盘口 request age 分列。旧探针 facts 前区间及未含账户读的 end_to_end 不可代替这个目标；尚未做真实目标环境实测。

这里的“同 run 恢复”是已授权风险窗口内、人工或场馆既有机制完成资金回收后的精确事实消费，不是新增资金动作授权、自动赎回系统或冷启动自动恢复。除本节指明的恢复接线与证据缺口外，不改金额、min_edge/min_secs_left、allowance/预算/敞口/止损、签名/ACK/首次发送原子门、身份/generation/unknown 保护、paper 账本或经济模型。

### R16.3 验收与阶段交接

必须按 SPEC §R16.6 的 D16-01–D16-10 逐项覆盖 R15 三 minor、拒绝归因、两种到账顺序、逐 atoms 反例、恢复续驱动、其他 stop/deadline/读失败及 paper/live 配对。Design 冻结 source/wire/consumer 的最小映射和精确 allowlist；实施与独立 Validate 分离。新正式验收仅使用 `data/reports/2026-11-23-btc5m-r16-integrated-validation/report.md` 与其 `evidence/`，不覆盖历史报告/探针/run/candidate、不创建任务镜像；本阶段不写结果报告。T1 只验证两文档实体/版本/互引/契约与 scoped diff-check；R16 业务测试、真实环境性能、部署及资金动作均 NOT_EXECUTED。

## 既有生效契约：公开 run JSON 参数化（2026-11-22）

来源：t_298e36df 与 Pascal 本轮已授权 Light 决定。下文旧 100/2/2、98/1/1/10/20 及历史算术、FAIL、原始 bytes 均保留为历史示例；本节替代其“唯一合法数值”含义，不追认旧运行。新入口显式要求 `controlled_run={budget_usdt,duration_seconds,operations_mode}`，资金仅复用 `strategies.btc_arb.order_usd` 和 `strategies.limits.{max_order_usd,max_market_usd,max_total_usd,max_loss_usd}`。缺省时旧 paper/legacy/replay 行为不变；同一候选 binary 与通用 launcher 从一份公开 JSON 冻结全 run 参数及 config SHA，不从账户现金自动推预算，不换 config 复用 activation。

参数关系为 target≤order≤market≤total≤budget；各金额必须有限、正数、非 bool、无溢出，最多六位 USDT 小数且≤1,000,000,000 USDT（限定到微 USDT，保证现有 f64 DecisionCore 输入的公开十进制往返唯一；风险 atoms 从原始 JSON 数字 token 精确解析，不从 f64 反算；budget_usdt 另可为≤18 位小数的十进制字符串（按 atoms 精确映射，不截断、不四舍五入、不容差），使 C0 能逐 atoms 等于观察到的 collateral，其余金额仍限六位小数）。loss 独立为正，不要求 loss<exposure；原 0.5 USDT dust floor 保留，不自动缩单。当前公开示例 budget=97、target/order/market=1、total=10、loss=20、duration=86400、unattended，仅示例。预算 B=C0+R−K、NAV=C0+net_pnl 的 C0 与 loss/各 cap 全部取本 run 冻结值，原账户现金单独保留。实际 exposure≥total 沿原黏性停止，不重启。

新 controller 从配置 duration 生成 deadline；若显式 CLI deadline/mode 存在须相同否则拒绝。native options/run/context/runtime 与现有双时钟一致；supervised 0<duration≤21600、unattended≤86400，旧 unsigned 6/72h 与旧 signed 6h 不变。started/final/ended 与严格 reader 使用同份 frozen 配置，禁止通过任意预算常数放宽检查；旧 run007..011 只读兼容、不回写。

定向消费者：config.StrictJson/load_controlled → native options → Broker LiveState；arbitrage 原 order_usd→DecisionCore target→attempt；live.seed_predict 预算准入；taker 预占/可用额/check_caps；live_control FINAL_SEND/total stop；live_accounting project_window 预算与 loss；Python control 固定值/started/deadline 与 live_events 首写、关系索引、ended/reader。超大文件仅原位接线，参数解析与新测试放小模块，不扩既有 tests.rs；本次修改仍须由独立 reviewer Validate。

Canonical `tools/predictfun/btc5m_launch.py` 仅机械归位获准旧 wrapper 步骤，复用 control/live_guard/reconcile 事实及 lazy PortfolioMongoLoader。import/参数检查/默认预检无执行副作用。run/window/auth、声明订单 hashes、精确旧 ARMED 目标显式输入；完整新鲜≤900s、同账户/config 的 reconcile、positions/history、无挂单、外部流及 gas、现金≥budget 的资格检查先于 activation 改动、旧 ARMED 轮换、arm、秘密读取及 child。失败上述副作用为零；成功仍需显式执行授权；精确匹配一条旧 ARMED、不通配删除、不重试，保存旧记录及 activation 原 bytes。原 child 再核账户/预算；本轮仅 fake collection/activation/child 离线验证。

## 1. 执行摘要

把现有 phase1_net_shares 决策契约贯通到既有 signed live Broker/适配器，输出可审计的实际执行、现金、净份额、费用及未决风险；不再让 signed 继续 legacy 决策而借用 paper 验收。复用现有 signer、账户门禁、SDK 与 supervisor，增加最小单实例和崩溃后停新风险机制；本轮选择“有界单次无人值守 + fail-closed 冷启动 + 人工回收资金”，不建设自动恢复/OMS 平台。

当前仅批准研发和离线验证。工程 PASS 只能支持以后申请具体真实动作，不证明 alpha、真实余额/权限、链上到账或无人值守部署资格。

## 2. 背景、基线与三类矩阵

BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`；下文 src/、tools/ 相对 BOT。本卡只读源码，不重跑既有业务测试；“已验收”注明复用来源，并非本卡重新签收。

入场主仓 HEAD=`9e06cdac513cd7ec616ee4f7877913330195fcf2`，BOT HEAD=`8f5dcba5b0334623bb0faf5c861fc342c1fe514e`。共享 dirty 含 07-006 三文档、pipeline skill、BOT observer/control/test 的既有修复，不属于本卡增量。

### 2.1 已验证离线基线：保留，不重新立项

| 能力 | 当前源码 / 独立证据 | 限度 |
|---|---|---|
| live 数量/核算/终态分离、实际增量、unknown 闭锁 | src/service/venue.rs:89–237；src/bot/runtime.rs:710–766；runtime/live.rs:115–252；[07-002 closeout](../../../data/reports/2026-11-13-predictfun-live-foundation/closeout.md) | 已有 execution snapshot 应用，不再声称 unknown 回填计划量的旧缺陷仍在；未证明真实场馆 |
| 账户启动/运行对账、分页与预算声明 | runtime/live.rs:281–360 及原 account reader | 已有 fail-closed；内存基线不等于跨重启恢复 |
| 固定 signed child、安全 keyring、SDK lazy pipe/API key | tools/predictfun/btc5m_control.py:1624–1671；cli.py:145–182；sdk_ops.py:409–423 | 不重建 signer/钱包/认证器/资金 SDK；历史认证不证明本轮余额 |
| phase1 净份额 EV、因果时钟、候选重验 | src/bot/arbitrage/phase1.rs；runtime/paper.rs:880–952；07-005 已验一期及后续修复 | 现只绑定 unsigned paper，不可外推 signed |
| observer 因果水位与 72h 固定候选接线 | t_3cfa9034/run3874 PASS_OFFLINE_REPAIR；t_655f69cf/run3876 PASS_LAUNCH_WIRING；当前 control SHA=5590892add29593d71d5233e5c14d831da06bad0bee32822e41b966bcd8250f8 | 复用已闭合证据，不重做 observer，也不扩 live observer |

### 2.2 真实工程缺口：本轮差量

| 缺口 | 现状定位 | 本轮最小目标 / SPEC 验收 |
|---|---|---|
| signed 没进入 phase1 | arbitrage.rs:69–73 依 broker.is_phase1；paper.rs:641–673 要求 PaperCash | 策略契约与执行模式解耦，同 DecisionCore；A-001–004 |
| paper 的同步 take_candidate 不能直接承担 live await | paper.rs:880–920；predict_fun/fills.rs:95–208 中有账户/盘口/授权/认证等待 | 原 Broker 薄适配，最终发送前重验；晚到真实成交必须入账，不因超时丢弃；A-003–006 |
| signed 公开输出只有 null final | control.py:1059–1064、1690–1698 | 独立分版 live 白名单及真实 producer→supervisor→首次 write→reader，非 paper 虚拟账；A-007–011 |
| attempt/tombstone/loss 在内存，run_id 独占不是账户互斥 | runtime/live.rs:19–44；control.py:1610–1614 | 同 host/账户单实例、持久拒绝屏障、冷启动停新增；A-012–016 |
| 故障与现金回收缺运行级闭合契约 | 既有 halt/cancel/SDK 在，但不足以签无人值守 | 复用停止管道，人工接管、未知不释放、到期待兑付不当现金；A-017–022 |

### 2.3 生产授权/真实验证缺口：不是离线实现失败，也不自动放行

| 对象 | 以后必须明确 / 验证 | 当前状态 |
|---|---|---|
| 认证、私有 API/RPC、账户身份/余额/挂单/持仓/Gas/route | 账户、链、版本、只读动作及时间；同目标完整读回 | NOT_AUTHORIZED / NOT_EXECUTED；不能用历史 100 USDT / BNB 快照 |
| 首笔、自动策略 pilot、无人值守 | 分别给金额/次数/期限/退出/取消/停手与接管责任；外部执行及风控确认 | 三者独立递进，不因前项通过自动启后项 |
| allowance/operator、卖出/赎回/其他资金动作 | 指定 market/route/合约、有限 ERC20 额度；ERC1155 合约级权限单列 | SDK 能力已有，但不是全路线批准；不自动 approve |
| 外部告警、长期调度、生产 Mongo/schema | 指定目标和副作用，另行确认 | 本轮均不执行；本地故障信号不冒充外部已送达 |
| alpha | 与执行成本相称的独立研究证据 | NOT_PROVEN；本项目不是收益改进实验 |

## 3. 目标与非目标

### 3.1 必须目标

1. 同样已批准的 BTC5m 输入、状态、时钟与参数，在允许来源的公共子域中，paper/live 的概率、方向选择、净 EV、重验及拒绝同义。成交路径不同，不要求真实成交量/费用等于 paper 模拟量。
2. 原执行器实际 gross/net/cash/fees、已签 hash、未决剩余、账户对账与 final 可逐事实审计；明确 accepted、matched、settled 与已赎回现金不是一回事。
3. 有人值守可做受限工程首单或策略 pilot；无人值守必须再覆盖互斥、故障、冷启动屏障、告警/接管及资金回收暂停。不能只做一个永远拒绝 live 的 stub。
4. 原 100 USDT 本金方案、2 USDT 单笔及单市场、10 USDT 总成本/未决预占、20 USDT 停新增保留。窗口、浮亏、Gas、未兑付和未知分别可解释；20 不是保证最大损失。
5. 独立 Validate 仅离线；以后真实小资金验证单独授权、单独记结果。

### 3.2 非目标

不做混合模型、动量、OBI、校准/参数/fee 公式优化、主动退出新策略、maker、Kelly、杠杆、第二 core/Broker/账本/OMS/runner、钱包或认证改造、自动重新签名/补单/解锁、无限恢复、跨主机 active-active、自动全路线 approve、自动赎回平台。当前不做认证/私有查询/链上刷新/真实签名/下撤单/资金/生产 DB/schema/服务/调度/权限/profile/依赖变更或 commit/push。

### 3.3 有限替代关系

本轮获采纳且实现验收后，仅对显式 07-007 候选：替代 07-005 §2/§4.7 的“phase1 仅 unsigned / signed legacy”，替代 07-004 及 07-005 的“signed final-only/null”，扩展 07-002 §4.5 与 §4.bis、07-004 §4.7 的“无跨进程运行保护”到可检验的冷启动拒绝屏障。不是追认旧合同能力，不改判旧 FAIL，不迁移或回填旧事件。

其余经济模型、单轮一次、资金/时间/官方结算、signer 安全、SDK 语义继续继承。07-006 observer 仍 unsigned-only、默认 OFF；v1/v2 历史语义及当前 run 不改。旧文档不批量回写；本节是显式增量优先级。

## 4. 整体方案与最小依赖决策

唯一链仍为固定 control → 原 Rust RoundTaker/DecisionCore → 原 Broker → PredictFunTrader；SDK 只做原资金工具，不进入策略热路径。新事件是 Broker 原状态的投影，reader 只审计，不能产生可交易余额。phase1 状态不得继续以 PaperCash 是否存在作为 live 准入依据，也不能给 live 注入虚拟 100 现金。

持久化默认 Mongo，已定向核实依赖：BOT Cargo.toml及tools/predictfun/requirements.lock无Mongo driver，BOT专用venv的pymongo元数据为NOT_INSTALLED；但项目`.venv/bin/python`已有pymongo 4.17.0、eth-account 0.14.0、jeepney 0.9.0。以上仅importlib.metadata读取，不导入业务模块/凭据、不连接数据库。项目MongoWriter虽有pymongo，却import即load_dotenv、默认写portfolio_position，普通upsert不提供运行fencing/交易前写障碍；LocalMongoAdapter限定03_data_ud_*且catch-and-log，不可直接套用资金安全存储。

据本任务允许明确fail-closed冷启动，本轮选择recovery_policy=COLD_START_REFUSE：原launcher复用已有项目Python依赖，单host OS互斥 + Mongo中同账户一次性ARMED拒绝屏障，非订单恢复账本。屏障在signer/child前以唯一scope主键创建、取得持久写确认并同目标读回；崩溃后连新run_id也拒绝，正常结束也不自动解除。同进程继续使用原LiveState和完整事件审计，不从文件/Mongo重建可交易余额或自动续跑。不新增SQLite、driver、包、服务；SDK资金工具仍沿其原专用环境。当前Mongo仅设计及fake存储消费者，不做生产连接/写入/schema操作。

T2须冻结原launcher的最小lazy存储接缝、项目解释器与原signer兼容验证、单文档唯一/耐久/读回语义及人工接管。未来实际库/集合绑定必须明确批准，本文的逻辑LiveRunGuard不是声称现网有同名集合；不用portfolio/UD集合、不擅自建生产集合/索引。缺连接绑定、driver、持久写确认或一致读回均拒绝live，不fallback文件/易失内存；不因缺条件自行安装或改变Mongo部署。若以后要求自动跨重启恢复，再对Mongo扩展必要恢复合同，不把当前屏障冒充完整恢复层。无需把已可收敛的方法选择退回用户。

## 5. 业务决策

### 5.1 经济 parity 与授权隔离

继承 07-005 的净份额 EV / gross 分母、模型/参数、20 returns、source epoch、5/10 秒时效和30秒入场界限。unsigned 仍可 Coinbase 降级；signed 仍 Binance-only，并标明预测源并非官方结算流。只在共同允许输入域比较经济 parity；Coinbase 在 live 被拒不是模型漂移。

live 在等待账户/盘口/授权/签名/认证之后、第一次可能 POST 前，以现有 core 对最终签名约束和最新检查时钟再验，不让旧候选穿越期限/停止边界。交易已经可能发送后，仍消费同 hash 的全部实际事实，不用 EV 或30秒门槛拒记晚到成交。未知闭锁与费用事实保留优先于漂亮报表。

### 5.2 风险窗口与现金

窗口绑定一次明确授权实验的 risk_window_id，不按 UTC 日、换轮、退出/重启或 run_id 重置；开始即固定本 run 冻结的 C0 分配预算（受控 run 取 `controlled_run.budget_usdt`；无该字段的历史/legacy 记录为 98 USDT，早期 V1.0 示例 100 仅作历史），真实可用额必须另读证实。没有充值/提款自动扩大预算。R+U 的 USDT 口径含实际交易费及浮亏；mark 无效/费用或未决现金未知即停新增，不能以零填绿灯。净额已含费不再扣一次。

原生 Gas 用 BNB 原子量单列，未知不是0；20 USDT 不含未获币种转换依据的 BNB，不宣称全成本损失封顶。以后真实授权须明确 Gas 支付地址、可消耗 BNB 预算/停止条件；不能临时猜汇率把 BNB 加 USDT。官方赢/平价确认可产生兑付权，但未读回实际 USDT 到账不成为可用现金，不拿 paper 结算回款证明 live 周转。

### 5.3 有人/无人值守与恢复

有人值守首单只要求该单原消费者事实和预批准退出闭合，不以前置自动赎回或无人值守全能力阻塞。有人策略 pilot 要求本轮经济 parity 和完整 live 输出；有人在场不能用 null final 签通过。现行 activation 时长按同一 mode-aware 判定：`supervised` 为 `0 < duration <= 6h`，`unattended` 为 `0 < duration <= 24h`；等号允许、超限及未知 mode 拒绝，controller、guard、metadata 三入口一致。

现行总敞口是已存在的成本加未闭合预占：`cost + reserved >= 10 USDT`（含等号）即复用黏性 stop → 有界安全收尾 → 原 drive 返回，不空转、不自动重启；仅拟新增单会使合计超限时只拒该候选，不把尚未产生的订单算成实际敞口。沿既有安全 reason/detail 表达 `MANUAL_STOP / TOTAL_CAP`，保留原先停止原因、20 USDT loss latch、在飞/未知订单、unresolved 与接管信息，不宣称退出就是平仓。paper 交易语义与现行 98/1/1/10/20/allowance100 不变。

history-only 仓位仅在最新官方结果明确包含目标 token、Yes/No token 对与历史 known 市场的侧别绑定一致，且沿原 settlement 判定得到 RESOLVED/CLOSED、非 contested、payout=0 时解释归零。同 market id 不足以证明身份；缺失、替换、互换或重复/额外 outcome 均 fail-closed，且不得污染后续读取的已知 token 绑定。平局与正兑付只在官方结果已确认、且该 token 的 claim 按 inventory×payout（1e6/5e5）逐 atoms 与持仓精确相等、budget+Σclaim 逐 atoms 等于观测 collateral 时可解释为已收到；未确认、矛盾、未结算、额外持仓、数量不符或任一 atom 差异仍拒绝解释，不新增请求种类或客户端。

无人值守本轮定义为“获限额限时的一次进程内运行，异常停新风险、无人自动重启”。成功首启和至少两轮不同市场的离线正路径必须可走；无风险后健康进程可继续，不能用全拒绝满足验收。异常/断网/关键输出失败/父失联/期限均停新增；允许有界同订单查询和已授权取消，不自动卖出/approve/转账。冷启动永不自动恢复；人工必须核对全部未知 hash/风险窗口损失及官方资金事实，新 run 不能抹掉旧 latch。

资金回收选择 MANUAL_PAUSE：首个需要回收的已结算持仓进入 WAIT_CASH，停止新增并告警，保留待兑付资产；人工另按原 SDK 或官网确认现金回读。不支持自动连续复投，不能把此能力命名为全天候自动赎回系统。未来如明确批准自动回收，仅可按既有 SDK 限定 route/target 承接，须另有可验证合同。

### 5.4 告警与证据

使用现有 supervisor 输出本地、固定 code 的停手/人工接管事件与非健康退出；无自由异常/raw响应/secret。告警投递失败也停新增。当前只离线 fake 告警接收者；未来无人值守实测须明确由谁在何处收到并接管，外部发送需另授权。拒绝屏障/缺结束证据保留异常，不靠告警成功代替账户对账。

## 5.bis 持久化、隐私与回退

| 数据 | 介质 / 边界 | 生命周期 / 恢复 |
|---|---|---|
| 受控启动/实际执行/结束证据 | 原新 run 目录的严格分版 JSON；只选白名单事实 | exclusive-create / 校验后追加，无 TTL/覆盖/补造/自动迁移；不是恢复可交易账本 |
| 同账户 live 拒绝屏障及 OS 锁 | 默认Mongo逻辑LiveRunGuard，同账户scope唯一主键；实际库/集合绑定以后批准，OS锁由T2冻结本host精确路径 | 启动前持久创建/读回，不按退出自动删除；无金融快照恢复；人工核对后另授权轮转，原屏障留档 |
| 风险、订单状态 | 唯一 Broker 内存；公开投影到上述事件 | 崩溃后 UNKNOWN/RECONCILIATION_REQUIRED，不重建100、不续签 |
| 未来完整恢复 | 默认Mongo；当前只有拒绝屏障契约，非自动恢复账 | 若需要再最小授权；本轮无DDL/DML/连接，不替用portfolio或UD集合 |
| secret | 仅原 keyring/内存/匿名管道 | 私钥/API/JWT/签名字节/RPC敏感URL/环境不进事件、屏障、报告或任务 |

chain/account 的固定公开绑定只记录其工程公开身份（L1）；官方公开行情 L0，与交易关联按 L1 管理。最小订单 hash/金额为授权范围内 L1 受控工程证据，不批量导出账户隐私。无 L3 落盘。data 被忽略不等于远程备份；回退是停止候选新增并保留原事实，不删除屏障/unknown/latch，不恢复旧 live binary 继续同预算。

## 6. 实现与正在运行候选隔离

当前 btc5m-baseline72-002：2026-11-19 12:12:10 至 2026-11-22 12:12:10 Asia/Shanghai；launcher56913/child56964，session proc_92911e09ac5f。受保护 binary=`data/reports/2026-11-19-btc5m-observer-runtime-fix/evidence/validate-v11/cargo-target/debug/polymarket-toolkits`，SHA256=`09ac37334c644c354c5565e5da3e3836815c14bb03161c44386966efaf91eca0`；control/observer/publiccfg 身份沿卡面原运行值保留。

T2 必须先区分已加载 Rust binary 与可能被当前 supervisor 以后动态导入的 Python 源码。优先在原 fork 源码工作、所有构建显式独立 target-dir，离线测试使用候选隔离配置/证据。会被当前 run 动态加载的源码在 paper 完成前不得编辑；必要等待，不改其加载行为、不用重启解冲突。不覆盖旧 target/binary/evidence，不变更当前环境/期限/配置/进程，也不重复启动 paper。旧14日 M0/M1/M2low/M3joint 冻结清单、参数、原研究制品逐项保护，不看中途评分。

本卡只新增两份文档。T2 才给原 BOT 内精确 allowlist、G3、最终源码映射与隔离验证命令；module 单测 colocated，主仓 tests 仅集成。禁止全仓重构、修改模板、依赖升级或 git destructive 操作。runtime 安全拒绝停动作及依赖分支，不换包装/工具/worker重放；可选诊断 OMITTED 不代替必需验收。

## 7. 风险与应对

| 风险 / 不确定性 | 应对 / 停止边界 |
|---|---|
| paper/live 相同模型不保证实盘成交和收益 | 同 core 对拍经济决策；实际成交单独核算；alpha 未证 |
| accepted/FILLED/settled 名称误当现金 | 数量、核算、链结算、兑付和提现现金分别证明 |
| cancel locked 或 late fill | removing 风险持续，原订单同 hash 查询；取消成功不释放至零 |
| 输出写失败、进程死于 hash/POST 边界 | 已持久拒绝屏障使冷启动停手；当前事实未知保留，不自动重签 |
| OS 锁只保护本 host 合作消费者 | 不宣称分布式/同UID安全隔离；真实授权指定账户独占，其他 host/非受控客户端不在可保证范围 |
| Gas、跳价、已发订单继续成交 | 单列费用与未决；20 是停止新增阈值，不能保证亏损封顶 |
| 人工回收慢、告警不达 | WAIT_CASH/STOP_NEW_RISK；不拿未兑付占用继续复投，无限恢复非目标 |
| 当前 paper 动态加载被污染 | 设计先隔离；不能隔离就等待到期，不动当前消费者 |

## 8. 备选方案

- 复制 paper core 到 live / 用 Python 决策下单：不选；违反唯一 Rust 模型与执行链。
- 直接令 live=true 或把 live 当 paper 现金：不选；绕过真实净额与未知风险。
- 给BOT专用venv增Mongo包、Rust driver、SQLite journal或新服务：不选；项目venv已有必要包可复用，本轮Mongo单文档拒绝屏障已满足最小冷启动模式，无须自动恢复账本。
- 全自动跨重启恢复/持续赎回：后续明确需求再做；不作为有人首单前置，也不冒称本轮已实现。
- 完全禁 live 然后宣布安全完成：不选；必须有离线可走的健康正路径及故障负路径。

## 9. 验收标准

按 SPEC §5 A-001–A-024 执行。核心是同核心决策、最终可能发送前重验、原实际执行增量、严格 live writer→supervisor→首次持久化→reader、互斥/冷启动/故障/人工回收。所有测试为离线 synthetic/fake transport/clock，不能以 fixture 冒充真实成交；不以盈利/成交数/新在线时长作为工程门槛。只重测本轮受影响路径，仍适用旧独立证据绑定身份后复用。

## 10. 落地与交接

T1 两文档静态一致性/引用/范围/hash → 主控 Gate → T2 独立 Design → Implement → 独立 Validate → 主控 Closeout。三独立文件到 Design Gate 必须齐备，但本阶段不得提前写 Design。唯一后续验收报告为 `data/reports/2026-11-19-btc5m-live-parity-and-operations/report.md`，必要原始 evidence/；本卡不写结果报告或任务镜像。之后主控分别申请有人工程首单、有人策略 pilot、无人小额验证；本卡不创建或启动任何真实阶段。

## 11. 开放问题

业务契约无须猜测的未决项。复用项目已有pymongo并选择“Mongo拒绝屏障、不自动恢复”，不要求用户为此选包。Design必须落实锁路径、Mongo逻辑映射/待批准部署绑定及耐久顺序、最终发送检查hook、typed live wire/schema与原字段映射、准确文件范围/G3、人工核对入口、隔离动态加载及可执行测试。真实账户/Gas预算/期限/告警接管/退出及生产Mongo部署授权是未来启动输入，缺失时live不启动，不阻塞本卡离线文档交付。

## 12. 来源

- [07-002 SPEC](../../spec/07_trading/SPEC-07-002-predictfun-live-foundation.md)、[Design](../../design/07_trading/DESIGN-07-002-predictfun-live-foundation.md)：actual facts、unknown、SDK。
- [07-003 SPEC](../../spec/07_trading/SPEC-07-003-predictfun-wsl-nonexport-signer.md)、[Design](../../design/07_trading/DESIGN-07-003-predictfun-wsl-nonexport-signer.md)：安全 keyring / 固定消费者。
- [07-004 SPEC](../../spec/07_trading/SPEC-07-004-btc5m-controlled-paper.md)、[Design](../../design/07_trading/DESIGN-07-004-btc5m-controlled-paper.md)：资金、期限、监督、SDK接线。
- [07-005 SPEC](../../spec/07_trading/SPEC-07-005-btc5m-phase1-correctness.md)、[Design](../../design/07_trading/DESIGN-07-005-btc5m-phase1-correctness.md)：phase1经济/clock/候选及v2。
- [07-006 SPEC](../../spec/07_trading/SPEC-07-006-btc5m-post-entry-observer.md)、[Design](../../design/07_trading/DESIGN-07-006-btc5m-post-entry-observer.md)：只读观察与水位，不扩 live。
- [当前源码线索评估](../../../data/reports/2026-11-19-btc5m-live-and-hybrid-assessment/report.md)：含2026-11-19官方公开规则链接；本卡重新静态定位源码，不把报告当实现答案。
- skills/data/data_interface/mongo_writer.py:9–21,31–53,69–109；skills/data/unified_data/local_mongo_adapter.py:8–33：只读核对依赖/职责，不导入、不读取凭据、不连接数据库。

历史参数化修订 V1.2：t_298e36df / Pascal Light；其参数化契约继续优先于历史固定示例；本轮当前版本为元数据及§R16的V1.15。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-11-19 | 冻结live经济parity、实际账务证据、两种值守及最小冷启动拒绝/资金回收边界；研发与真实动作分离，保护当前paper和冻结研究 |
| V1.1 | 2026-11-22 | R2 窄纠错：§5.3 明确 supervised≤6h/unattended≤24h 共用判定、实际 cost+reserved≥10u 黏性停止并原 drive 安全返回，以及最新官方/历史 token-side 严格一致后才解释零兑付；不改经济额度、paper、事件版本或运行授权。 |
| V1.2 | 2026-11-22 | 公开 run JSON 参数化（Light）：新受控入口以 controlled_run={budget_usdt,duration_seconds,operations_mode} 与本 run 的 order/limits 冻结全 run 金额与时限，C0/loss/caps 取本 run 值；legacy 缺省与历史记录保持原值。不新增经济授权、真实交易许可或恢复语义。 |
| V1.3 | 2026-11-22 | R7 Validate 文档校正（MINOR-1/2）：§5.2 C0 改为取本 run 冻结预算（legacy 98，早期 100 仅历史示例）；预算/caps 行号指针更新为 live.rs:746–754、taker.rs:419–436、live_control.rs:386–395；常量/上限指针一并校正为 live_accounting.rs:30（MIN_ORDER）、32（BUDGET_C0）、34（MAX_ORDER）、38（MAX_TOTAL）、40（MAX_LOSS），taker.rs:429–436；不改代码/额度/授权语义 |
| V1.4 | 2026-11-22 | R12 窄修订：预算须逐 atoms 等于启动时观察到的 collateral（budget_usdt 支持≤18 位小数的十进制字符串、按 atoms 精确映射，不截断、不容差；±1 atom 即启动前 CASH_BUDGET_MISMATCH 拒绝）；不改经济公式、额度、授权或运行语义 |
| V1.7 | 2026-11-23 | R13 窄修订：确认的正兑付 claim 在官方结果已确认后，按官方结果的 claim_value_atoms 与已兑付份额核对；claim 未确认前不入账为现金 |
| V1.8 | 2026-11-23 | R13b 窄修订：官方结算先到、精确 claim 后到的顺序下，本 run 内允许把该精确 claim 清回 READY；差 1 atom、结果未确认、foreign token 仍停窗 |
| V1.9 | 2026-11-23 | R13c 窄修订：claim 先判定后入账（账户读回只记为已证明待兑付，已确认官方结果逐 atoms 精确相等才入账为现金）；canonical reader 与 Rust 侧对同一合法流给出一致结论（已兑付持仓不进终态 positions、reader 观察 CASH_CONFIRMED 后不再视为停窗） |
| V1.10 | 2026-11-23 | R13d 窄修订：reader 收到 payout `CASH_CONFIRMED` 且该等待由 `CASH_PENDING` 造成时同步解除 `stopped`（其它原因停止仍黏性，并以 producer→reader 双用例覆盖续单与反例）；逐 atoms 预算门等指针改为符号锚定（`seed_predict` 的 `cash_matches_budget_and_claims` 不等即 bail `CASH_BUDGET_MISMATCH`，行号仅辅助）；移除 `live.rs` 未使用的 `cleared_waits`；不改经济、额度或授权语义 |
| V1.15 | 2026-11-23 | R16 T1：对齐 R15/R13/R14 已验基线；冻结兼容拒绝诊断、R15 三 minor 闭合、本 run 精确 claim 与600s/deadline有界 WAIT_CASH 续驱动及新测量/验收定义。仅 RFC/SPEC，不表示实现或部署；R15 原卡历史结论不变。 |
