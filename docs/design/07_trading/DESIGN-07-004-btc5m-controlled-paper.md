# DESIGN-07-004: BTC5m 受控 paper 最小接线

## 元数据与结论

- 版本：V1.3，2026-11-16，Asia/Shanghai（UTC+08:00）；作者：YQuant Principal。仅同步 Pascal 后续启动固定单键来源固化授权（`t_3b2deaac`）；RFC/SPEC 当前 V1.1，资金、期限与 A001–A019 其他行为不变。
- 状态：本增量 Design Gate 候选，不是本增量 Implement、独立 Validate、6h 运行或实盘通过；既有 R3 工程 PASS、F1/F2 闭合作为基线，不重判。
- 来源：[RFC-07-004](../../rfc/07_trading/RFC-07-004-btc5m-controlled-paper.md) V1.1、[SPEC-07-004](../../spec/07_trading/SPEC-07-004-btc5m-controlled-paper.md) V1.1。
- 当前输入 SHA256：RFC V1.1 `3e345812558be1bda426c12c0a24e43e29d520abd33376839f6a18fdc93d1b31`；SPEC V1.1 `daede7b8f106e5ad8e0deab694f6856a72809c702049b57334ce0b89caf5f97d`。主控 Gate 仅补齐本增量验收报告路径与历史保护边界后原生 sha256sum 实测；正文行为不变。历史 V1.0 输入：RFC `c471b6840d516666afcdfbd259cf312e3d8fbf88b967cf435a7cc2dcf4d64ccc`；SPEC `39174c8f1f3dfa6f28f679e9de08099f6eda62d3f6207bdf39d5f79c33da44dd`；旧 Decimal 复算仍复用，不重放已拒组合探针。
- 工作区：`/home/pascal/workspace/yquant-investment`；`BOT=skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。

采用一个固定 Python 启动薄入口、一个现有 Broker 内受控 paper 分支，以及原 SDK CLI 的 lazy keyring→匿名 FD 接线。现金/库存/损失唯一状态仍在 Broker 锁内；不增加执行器、服务、持久账本、恢复流程或通用状态机。V1.3 仅在原 unsigned 来源点补固定单键回退；本卡只同步三层契约。本次以 §2.3 / §3.1 / §8.4 为当前增量，§1–2.2 和 §8.1–8.3 的原阶段事实、规模/全量计划保留为历史，不能据此重做已验工程或扩大本次 allowlist。不触碰/重启/停止/重建当前已启动观察，不重跑任何 6h、不改其证据，不自动开启下一轮。

## 1. 已核基线与实际接缝

原V1.0入场主仓 HEAD `e5ae72212ffd18e6af71dae5457913959e4ffffb`，BOT HEAD `e0eaa1edefe798e4090f87412015d1e5e168a372`，当时均 main、status clean；不是V1.2当前共享树状态。RFC及旧报告中的HEAD/dirty同样只是历史身份，不据此重判旧验收或还原共享树。后续worker记录候选，不自动commit/push/gitlink。

V1.1依据[主控候选校准](../../../data/reports/2026-11-16-btc5m-controlled-paper/evidence/orchestrator-partial-candidate-calibration.json)，沿原Design SHA256 `2d036adf72a6d4bdd7cdabd1ebf2fd26a6345c5792dca7c539b59ee6d36dd164`做增量修订。该证据已固定候选文件SHA/行数，Rust lib为286 passed/0 failed/3 ignored、launcher现有16项OK，均exit0；仅证明现有套件通过，不证明A001–A019覆盖。预算耗尽不是审批拒绝。本卡只定向读接缝，不重跑校准、历史实验或业务测试；以下原位置表保留为V1.0接缝参考，当前消费者见§2.1/§2.2。

V1.2沿V1.1 Design SHA256 `f81edebfa985adc012a2945c889ef28927f044868e1355a6eeb4878d17feb517`定点同步测试提取；当前候选身份及格式化行数采用[run3749开发自测清单](../../../data/reports/2026-11-16-btc5m-controlled-paper/evidence/run3749-selftest.json)和主控已核SHA：runtime.rs为2354行、paper.rs为2380行，内联`#[cfg(test)] mod tests`从1370–1371行起约1011行。此前3141/655等仅为V1.1校准历史。该清单记录lib302 passed/3 ignored、launcher29、replay2及all-targets native exit0，不是独立Validate或完整raw导出，本卡不重跑。已落G3迁移、SDK/core与其已闭合接线不从零重做；本次只给原剩余反例释放文件容量，不删验收。

V1.3 沿 V1.2 Design SHA256 `e959f8b8208242d73d70a2a35d304f274636365e94682e07aa672fdf71121f85` 窄修订，旧身份不替换。当前只读源码确认：`btc5m_control.run:733–755` 先公开校验，再 `check_environment`，后身份/首次证据/child；`check_environment:273–282` 先逐禁键存在性拒绝，再调用 `local_signer._api_source:341–347`；`child_environment:285–289` 为既有白名单。原 `test_a_missing_api_key_is_refused:272–274` 必须保留并隔离不存在 fixture。此次不重做 SDK/core/现金/G3，基线 R3 独立结论见 `t_c158af6d` 及[validation-r3](../../../data/reports/2026-11-16-btc5m-controlled-paper/validation-r3.md)；该结论不覆盖新增回退行为。

| 原位置（模块简称；完整路径见§2） | 保留能力 / 本次调用点 |
|---|---|
| `arbitrage.rs:36–48,220–307` | `run → Ctx::connect → drive → RoundTaker::tick → live_entry/DecisionCore → Broker::take`；只补受控上下文/数据有效性/来源关联，不改模型、300秒选择、20 returns 预热或单轮一次 |
| `runtime.rs:318–335,426–545` | 原 Broker 构造与 take；增加显式受控构造、锁内现金检查/模拟分支，普通构造签名及原 live 路径不变 |
| `runtime.rs:965–1038,1091–1141,1408–1513` | observe/loss/settle/drive；插入净额检查、截止门禁及有限收尾，复用 halted、Ctrl-C、cancel_all |
| `runtime.rs:1260–1289` | 当前即使 paper 也尝试 `PredictFunTrader::new`；必须在受控 unsigned 分支直接跳过，不以构造失败证明无 signer |
| `local_signer.py:311–356,374–412` | 原 `_read_owned`/派生绑定、API 来源、白名单环境和缺失 credentials 规则；只复用函数，不改存储/check/enroll/sign-in |
| `cli.py:122–140`、`sdk_ops.py:561–658` | 原 normalize/target_digest/只读预检/loader/SDK/receipt/同目标读回；新增 keyring 选择，不复制执行流程 |
| `sdk_ops.py:302–312,372–385` | 原 fd_signer_loader 保留；market GET 补主网 x-api-key，并明确拒绝3xx |
| `predict_fun.rs:849–912,1001–1017` | 原 MarketData mapping；原 payout 可仅凭起止价或 outcome 推导，不足以作为本次回款证明。只增携带原始终态/精度/provider 的事实，严格验证放受控 Broker 子模块，不全局改旧 mapping |

事实来源另见：[总体盘点](../../../data/reports/2026-11-16-btc5m-live-readiness-overview/report.md)、[最小金额计划](../../../data/reports/2026-11-16-predictfun-minimum-approval-plan/report.md)、[07-002 closeout](../../../data/reports/2026-11-13-predictfun-live-foundation/closeout.md)、[07-003 报告 §5](../../../data/reports/2026-11-15-predictfun-keyring-signin/report.md)、[旧6h报告](../../../data/reports/2026-11-12-btc5m-forward-paper/run3-6h-report.md)。这些不是本轮新网络/账户实测。旧48笔费用后 -16.219972 USD 与新净份额模式不拼接口径。

## 2. Implement 精确 allowlist 与规模

下表均为BOT相对路径；只允许表列文件及其colocated tests，不是目录授权。未另标的估算保留V1.0量级，不是当前实测或允许从零重写；当前行数引用run3749，不重算历史候选diff。本次唯一新增allowlist项为`src/bot/runtime/paper/tests.rs`，仅test-only；其余文件授权不变，已落候选的保留/提取/补齐以§2.1/§2.2为准。

| 文件 | 增量估算 | 直接消费者 / 必要性 |
|---|---|---|
| 新 `tools/predictfun/btc5m_control.py` | 业务约250–400行 | 主控固定模式启动、公共校验、受限子环境、输出过滤和有界回收；旧60秒 check 不适用6h run，不能扩成任意命令代理 |
| `tools/predictfun/cli.py` | 约60–100行 | SDK 原四个固定命令增加 `--keyring` 选择和 lazy FD scope；不增加第二SDK命令代理 |
| `tools/predictfun/sdk_ops.py` | 约40–70行 | `ReadSession.market` 的 API 来源/header/响应检查；原执行器仅补确认后目标不可变及keyring controller核验 |
| `src/config.rs` | run3749为1377行；V1.1的1272行/+563及原估100–180行均为历史 | 保留opt-in类型/严格公共加载/运行上下文；仅原处补模式差异和输入反例，复用校验，不另复制signed加载器；普通load/default不变 |
| `src/main.rs` | 约40–80行（含colocated测试） | 只对固定 `run btc-arb` 接受受控参数并选加载分支；不改TUI/check默认 |
| `src/bot/runtime.rs` | run3749为2354行；V1.1的3141行/+960/-1为迁移前历史；最终目标仍≤2400行 | 仅保留共享Broker/State声明、普通路径、Ctx装配和受控分派；不得继续向父文件堆受控业务/新测试 |
| 已有 `src/bot/runtime/paper.rs` | run3749为2380行；提取后预计约1370行加必要内部接缝，须实际格式化计数且≤2400 | 同State同锁的生产impl保持原位置，仅提取全部内联测试/fixture；不是第二Broker/账本/执行器，不新增兄弟生产模块；测试例外仅下一行 |
| 新 `src/bot/runtime/paper/tests.rs` | 迁入约1011行加原需求必要剩余测试，须实际格式化计数且≤2400，不承诺精确预测 | 承接paper.rs全部内联测试/fixture及§2.2剩余消费者反例；只由`#[cfg(test)] mod tests;`按Rust默认子模块路径加载，不用include或新runtime抽象，不授权整个目录 |
| `src/bot/arbitrage.rs` | 约40–80行接线，测试约80–150行 | 本轮数据有效性与成交source关联、真实RoundTaker消费者fixture；core算法不变 |
| `src/bot/arbitrage/replay/driver.rs` | 仅现有+1行 | `tradable_market:1071`补`round_facts: None`使新增字段兼容编译；冻结此例外，不许其他replay逻辑、模型、输出或测试树改动 |
| `src/service/venue.rs` | 约30–60行（含测试） | `TradableMarket` additive事实载体，受控结算/精度直接消费；MarketData trait不改签名 |
| `src/service/predict_fun.rs` | run3749为2398行；保留已落事实映射，不继续净增业务 | 只原处修正必要事实映射/少量断言；新验证落paper.rs/venue.rs，paper资金/尾查测试落paper/tests.rs，不扩场馆、认证或SDK签名核心 |
| 新 `tools/predictfun/tests/test_btc5m_control.py` | 约250–450行 | 真parser→公开校验→fake child、期限/输出/回收正反例；复用unittest，无新框架 |
| `tools/predictfun/tests/test_sdk_ops.py` | 约100–200行 | 原SDK真实消费者/匿名FD/API捕获与零读取反例；复用原FakeSession和真实SDK builder |
| 新 `tools/predictfun/btc5m-controlled-paper.json` | 与现有AppConfig形状相当 | 完整公共示例，不改默认config；入口读取后独立冻结为本run的公开快照 |
| `tools/predictfun/README.md`、`docs/LIVE-TRADING.md` | 各约20–40行 | 主控实际命令、禁真执行边界、停止/不恢复及paper与redeem差异；不重写旧说明 |

`local_signer.py`、`test_local_signer.py`、`test_sdk_identity.py` 只读复用/完整回归，不列修改许可；不改Cargo/requirements/锁文件、默认config.json/YAML、spot.rs、quoting.rs、runtime/live.rs、account.rs、copy OrderExecutor、模板、三层README或其他项目/profile。工程报告/必要证据仅按SPEC落 `data/reports/2026-11-16-btc5m-controlled-paper/validation.md` 与 `evidence/`，不由本Design卡创建。

### 2.1 G3最小拆分（已落迁移保留，先测试提取再补反例）

V1.1曾因runtime.rs从2182行增至3141行而定义迁移到当时655行paper.rs的Principal拆分；该批迁移现已落候选，不重新执行。下列1–3保留历史符号边界（行号均为V1.1校准定位），生产实现仍限本次受控paper、同State同锁；当时迁入paper.rs的测试本轮统一提取至paper/tests.rs。V1.2仅新增第4项测试落点例外，不豁免G3，独立审查由既有Validate承担，不另开Review链。

1. 从runtime.rs移至paper.rs内`impl super::State`：`apply_controlled_buy/sell`（300–325）；移至`impl super::Broker`：`with_controlled_paper`、`record_source/source_of`、`paper_snapshot`（407–445、463–468），`controlled_take/controlled_stopped/check_controlled_loss_limit`（841–1115），`controlled_observe`（1409–1433），`invalidate_paper_marks`（1552–1557），`controlled_settle`（1582–1713）。仍读写父State/holdings/realized/fees，同一Mutex，不复制/序列化状态；父模块需调用的内部方法仅`pub(super)`，原公开方法签名不变，不扩大到crate公共API。
2. 将新增`EVENT_PREFIX/emit_event/paper_accounting`（1860–1891）及`log_summary`内受控输出段移至paper.rs，父仅调用/必要re-export，保留原普通summary日志；把新增`controlled/controlled_limits/controlled_with`fixture（2315–2341）和`marked_market`起至末尾受控测试（2962–3140，含属性/注释）移至paper.rs的tests，复用父`test_support`。旧tests、旧FakeVenue/fixture、旧live/普通paper业务全部留原处；禁止删除、压行或复制测试换取行数。
3. 为给剩余期限接线留空间，同批把新增`stop_entries/controlled_run/entry_stop_reason`（447–461、470–473）移入上述Broker impl，`watch_control_channel`（1893–1926）移入paper.rs内部函数；控制监督同时供unsigned/signed使用，signed调用不要求或产生PaperCash。父只保留字段/枚举、受控分派、Ctx和drive调用接线；有界等待/尾查及受控final组装落paper.rs，由原drive调用，不复制drive/策略循环或新建运行器。父收敛量级预计约2300–2400行，实际格式化复核；控制通知须有界唤醒drive，D后EOF须能升级为紧急停止，不能被首次deadline原因吞掉，也不冒充loss latch。
4. 主控Gate后先机械提取当前paper.rs全部内联tests/fixture到唯一新增`src/bot/runtime/paper/tests.rs`，保留全部断言、注释、测试名及`bot::runtime::paper::tests`模块路径；paper.rs以`#[cfg(test)] mod tests;`声明，默认即定位paper/tests.rs，必要时保留/补`use super::*;`。生产impl留原处同State同锁，不移动旧业务、父模块旧tests或其他测试树，不新建兄弟生产模块、不用include或新runtime抽象。测试和专属fixture只在cfg(test)编译；若跨模块fixture可见性需要调整，只用最小`pub(super)`/现有test_support，不扩大公共API或改变生产行为。先跑受影响测试并核对Python原Rust executable/filter消费者仍命中原测试、不因迁位skip，再补§2.2剩余反例。格式化后runtime.rs目标仍≤2400，paper.rs与paper/tests.rs各≤2400；预计paper约1370行、tests约1011行加必要剩余测试，只是量级，必须实际计数。若仍触界，报具体符号/规模给主控，不压行/删断言、不再自行增文件或迁旧业务；本次tests.rs是唯一新增文件例外。

config.rs在run3749为1377行，仍属受控扩张：增长来自公共配置/期限类型、严格解析及测试；本轮仅收敛这些既有职责、共用模式校验，不自动大拆。predict_fun.rs 2398行已近边界，禁止继续堆新业务，新增验证由venue.rs/paper.rs承担，paper测试统一落paper/tests.rs；本次提取后仍适用同一上限：任一文件超2400或超上述职责先报告，不隐式扩大allowlist。格式化行数是报告对象，不是删验收/压行目标；下一次实质性功能扩展须重新说明边界与拆分触发条件。本轮既有独立Validate检查上述迁移、测试提取与G3，不授予长期例外。

### 2.2 候选剩余delta与集中消费者验证

保留run3749已落公共校验/快照/身份、signed原factory/account接线与诚实final、unsigned隔离、同锁现金/净份额/mark/loss/官方结果、SDK空pipe+lazy原loader/目标冻结、launcher selectors/同一cleanup预算/首次落盘白名单及真实Rust协议消费者。它们是开发候选而非独立验收，不重做已闭合SDK/core或已落G3迁移。§2.1本轮只提取测试；原需求必要内部短clock/取消预算接缝仍留原生产位置，专属测试fixture落paper/tests.rs，不新增运行抽象。所有A001–A019及100 USDT/2/2/10/20、费用、unsigned隔离、signed仅合成、deadline/600秒尾查保持原文不变。

当前剩余消费者反例以原Implement comment3645为准：`controlled_take_locked`应用前截止→reservation/release/blocked逐事件；`finish_controlled`真实cancel_all future超时→final；原drive阻塞market整段与同边界信号组合；Python同一cleanup截止的wait预算spy；更完整SELL/LOSS/PENDING/CONFLICT逐事件矩阵与首次write核验。Rust反例/fixture落paper/tests.rs，Python仍在原test_btc5m_control.py，必要内部接缝不扩大公共API。原估90–140格式化行只是这些边界测试/接缝的量级，不是新业务平台；测试提取不减免任何一项验收。

下表保留V1.1缺口/原定位与应有消费者的设计追溯，不是run3749当前待办；其中“被拒”“骨架”“当前”等描述均指V1.1校准候选，后续只补上段剩余项及独立验收查出的具体差异，不从零重建。

| V1.1历史delta / 候选位置 | 原处最小修改及真实消费者 | 集中验证（细项沿§8.1） |
|---|---|---|
| signed被拒：launcher `run:314–317`、`check_fixed_values:141`、`child_arguments:272`；config `ControlledRun::from_arguments:679–681`、`load_controlled_unsigned_paper:976–984`；main `194–208`；Ctx `1943–1946` | 两模式共用公开校验，signed单独核enable=true/mock=false、无paper、固定身份/预算/RPC，之后才用原`_read_owned/build_child_env`；argv携真实mode与原预算/RPC选项。受控load按mode只读允许环境且绝不读YAML，unsigned须装入PM_PREDICT_API_KEY而非清空全部credentials后丢失行情key；signed沿原trader/claim/account gate并装ControlledRun与控制监督，不装cash。普通默认路径不变，不改原签名器 | A001–003/A019真parser→config/main→Ctx/factory→原run的fake正反例；替换`test_the_signed_mode_is_refused`的“合法signed拒绝”目标，保留缺确认/错身份反例；unsigned行情key到原client，构造/认证/RPC均0 |
| SDK骨架未等于匿名FD：cli `run:138–145`；sdk_ops `KeyringSigner/_read_keyring_key/keyring_signer_loader:315–356`、`execute_target:637–701` | 保留已落参数互斥、expected_controller、market API/header；当前loader忽略fd并由KeyringSigner直接派生，不满足§4。原处替换本次新增代理为cli作用域内空pipe+lazy closure→原fd_signer_loader，finally关闭；按§4冻结目标并在预检后/取key前/signed_builder前比较，保留旧直接fd、原SDK builder/receipt/readback，不另造signer | A004–006经cli真入口→execute_target→真实pipe/原loader→原SDK builder；no-op/只读/身份失败取key=0、目标突变不签名、FD失败及信号不泄漏，已发送不明不重发；不是仅新增工具函数测试 |
| 起点/配置/身份：launcher `public_identity:229–236`、`run:325–341` | UTC与CLOCK_BOOTTIME入口即采样，校验耗时也占预算；序列化已校验公共对象一次，以实际写入public-config.json字节SHA填started，child只取该快照。Git固定只读命令解析主/BOT HEAD（兼容submodule .git文件），记录固定受影响文件及实际binary SHA，不读取.git/HEAD文本冒充提交；主题日期取开始UTC转Asia/Shanghai，不依赖cwd/硬编码旧日期 | A001/A015/A016/A018：准备跨deadline无新增、倒拨/暂停不补时；改原配置不影响child快照，捕获child参数与落盘SHA对应；身份失败在child前关闭，不写空SHA/缺身份成功记录 |
| 管道/回收：launcher `run:350–378`、`main:394`；runtime `watch_control_channel:1899`、`drive:2115–2225` | 替换先close stdin再communicate：保持唯一父写端、selectors流式双路drain、期限发D且继续监督；父信号/异常finally有界传播/kill/wait，所有wait受剩余预算约束，不留无超时communicate。线程同锁停新增并经有界通知唤醒drive，未知字节为CONTROL_CHANNEL，EOF/急停优先于正常尾查；launcher按实际exit_facts返回非零而非总return0 | A015/A016实际无网fake executable+pipe，含D前不EOF、D后EOF、父SIGKILL、非零/拒停/异常及实际reap；不能只靠BytesIO/TimeoutExpired mock取绿灯 |
| 截止/尾查：runtime `drive` ticker内期限检查、`settle_resolved:1560`，迁后paper.rs受控settle/尾查 | unsigned将tick/整次market future置于停止/期限外层，预占前与应用前同锁重检；deadline先停新增、原cancel_all≤30秒，再调用paper.rs同Broker/data尾查≤600秒、每市场60秒、整次读取≤min(15秒,余量)，仅已成交未确认市场；急停中断尾查。signed只沿原live未知风险/清理，不drop在途写入、不纸面释放 | A008/A015–017：阻塞tick/market可被期限截断；最后轮迟到只回款一次、一直pending/争议有界、尾查策略/auth/redeem/新增全0；同时验证旧live回归 |
| 资金/事实残缺：迁前`controlled_take:841–1115`、`controlled_settle:1587–1713`及paper.rs helpers；arbitrage `tick:220` | 依§5原处补全：token/显式precision/数值/盘口合法性、同锁walk/预占及不得覆盖未闭合slot、成交前期限和loss重检、费用不二扣Summary；保存首次成交market/两token/300秒身份及已应用官方结果，重复冲突停新增但不追改现金。DRAW仍校验outcomes，不能无条件Confirmed；RoundTaker仅补输入有效性和真实消费者fixture，不改core | A007–014逐事件对拍而非仅纯函数；真正较优VWAP差价、低现金、并发、mark缺失、同tick亏损、错token/时长/起止/outcome、已确认后冲突与重复、真实RoundTaker→take |
| 输出/结束：launcher `read_events:280–304`、`ended:368–378`；迁前`emit_event/paper_accounting`、`log_summary:2227` | 修现有固定协议：Rust补run_id、预占/释放/阻断、来源/扣费份额/单位和去重逐市场final；Python按事件kind白名单递归校验/重建后首次写入，不接受任意prefixed dict、自由文本/provider。双路限长缓冲，坏关键事件中止。真正final与周期summary区分；回收后ended填final_accounting/settlement_status/exit_facts，缺坏final为null+固定原因/exit1，不从日志猜账 | A011/A016/A018：真实协议输出→首次write spy→ended及逐笔复算；嵌套未知字段/金额NaN/重复键/自由文本/哨兵/超长跨chunk/缺final/非零child全测，Gas/source/pending边界披露；不得把外层0当可对账通过 |

规模/ROI：原父接线90–170行、config100–180行及V1.1 launcher398行均为历史估算/候选，不能当当前基线；run3749 launcher为788行、其测试500行。保留一个模式校验/同State/一个输出协议，先机械提取测试再补原反例，不能再堆平台或报告声称收尾。迁入paper/tests.rs不算新增能力；原16项或当前302/29自测数均不证明全矩阵完成。Implement记录实际迁移/净新增/格式化行数、受影响测试覆盖与未覆盖；若仍有契约冲突集中交主控，不自行拒signed、删尾查或削减断言。

### 2.3 V1.3 当前唯一增量与精确 allowlist

只改 BOT 内四个现有文件：`tools/predictfun/btc5m_control.py`（固定路径常量、原 unsigned 来源点及文件精确单键解析）、`tools/predictfun/tests/test_btc5m_control.py`（scratch 隔离与 SPEC B-001–B-006）、`tools/predictfun/README.md`、`docs/LIVE-TRADING.md`（直接启动/环境优先/拒绝口径）。前两者源码读取基线为807/688行，增量只须小型标准库解析和表驱动回归；不另建 wrapper/helper 文件或配置框架。Rust、SDK、local_signer、公开 JSON、依赖/锁文件及全部已验工程保持不变，不重复 §2.1 迁移/测试提取或 §2.2 已闭合实现。

固定路径常量在原 launcher 内定义为 `BOT.parents[4] / "skills/.env"`；local_signer 的 BOT 由本文件位置 `.resolve().parents[2]` 定位，现有 launcher 的项目身份/报告根也复用 BOT.parents[4]，对应本项目 `/home/pascal/workspace/yquant-investment`，不是用户 cwd。此处仅核源码路径关系，不读取生产文件验证。不给调用者任何文件路径、命令或新 runner 参数，测试只能 patch 常量到当前 profile scratch。

## 3. 固定入口与参数装配

### 3.1 运行入口

新增入口的公开接口固定为：

- `btc5m_control.py --mode unsigned-paper --config <显式公共JSON> --run-id <公开ID>`。
- `--mode signed-future-live` 为另一个显式分支，另外必需 `--predict-budget-confirmation` 和 `--predict-rpc-url`；本轮仅fake验证，真实使用另行授权。unsigned拒绝这两个live选项。
- 无默认模式、无缩写、无尾参数转发、无可执行文件/钱包/venue/bot/TUI/期限/资金覆盖选项。run-id只接受ASCII `[a-z0-9][a-z0-9_-]{0,63}`，不得当路径。

复用local_signer的固定错误/JSON hook/API来源/环境常量，不调用其check或launch_check。BOT由本文件位置确定，固定child=`BOT/target/debug/polymarket-toolkits`，固定cwd=BOT，不自动build。V1.3 保持原 run 顺序：全部公开输入/strict JSON/固定参数→unsigned 父禁键检查/按条件文件读取及原 API 来源核验（或原 signed 环境分支）→固定 binary/credentials 路径→身份→独占启动记录与公共快照→原 child_environment/本分支所需密钥→单次 BOT child。新增读取不能抢在公开配置或父禁键检查之前，配置拒绝不能已有首次 write。启动尝试的UTC和CLOCK_BOOTTIME在入口开始即采样，准备/等待不补时。

公开JSON含原完整AppConfig形状，受控新增 `controlled_paper={initial_cash:100,fee_model:"paper_net_shares"}`；unsigned须显式存在，signed须不存在/null。必须显式给出SPEC的BTCUSDT/300、模型0.03/30/0.00005、order=2、limits=2/2/10/20及正确enable/mock，不从旧默认补这些关键项。保留原poll_secs=5、rescan_secs=300、quote_ttl_secs=300；固定配置不得更换host/chain。拒绝重复键、NaN/Infinity、布尔金额、秘密/credentials字段与畸形类型。完整配置写入本run的公开快照后只把该快照给child，不重新读取用户原文件。

保留 `.keyring-no-credentials` 的lexists拒绝（包括悬空链接），不创建它、不读默认 YAML。paper 先按键存在性拒绝 `PM_PRIVATE_KEY`、`PM_FUNDER_ADDRESS`、`PM_SIGNATURE_TYPE`、`PM_API_KEY`、`PM_API_SECRET`、`PM_API_PASSPHRASE`、`PM_PREDICT_ACCOUNT`、`PM_JWT`、`PM_PREDICT_JWT`、`JWT`、`PRIVATE_KEY`、`MNEMONIC`、`SEED`；不取这些值。API 沿原 `_api_source` 的 YQUANT_PREDICT_FUN_TOKEN→PM_PREDICT_API_KEY 映射，只在父源键根本不存在时，才按 SPEC §4.1.1 从固定文件取精确单键到临时环境副本；已有源（包括空白）完全不读文件，空白仍拒绝、不隐式修复。将副本交原 `_api_source`，不改 local_signer；返回 key 仍由现有 child_environment 组装，不导入文件其他项、不改父映射或 os.environ。child 沿原 OS/代理/CA 白名单、固定 PATH/RUST_LOG，paper 只加行情 API key，私钥/钱包/JWT/DBUS/其他 PM_* 为零。

解析仅标准库，按 SPEC §4.1.1 单行可选 export/等号空白/单双引号/尾注释语法完整扫描目标键；UTF-8 严格解码，其他键不导入，不 source/eval/load_dotenv/执行插值，不支持多行/续行。不做通用 dotenv loader。重复目标键即使同值、缺失/空白、不可读/不存在、坏引号/非法尾部、多行/编码错误均 `Refused("API_SOURCE", "env", "API_SOURCE") from None`，exit2，不能传播原行/值/底层异常。原 alias 不同值的冲突仍 `ENV_CONFLICT/env/API_SOURCE`、exit2；不改变既有 check_environment 的错误映射。signed-future-live、SDK、原 check/enroll/sign-in 均保持原 env-only 来源，无新文件回退。

signed在公开校验及固定chain56/账户、预算确认/RPC格式检查之后才调用原 `_read_owned/build_child_env`，进入原Rust signer和07-002账户门禁；不能以公开确认替代真实动作批准，不装配虚拟cash。Predict Account固定 `0xfc9eb66e6F22f96608058C0A711Ed048eED8c2E2`，控制signer固定 `0x5129330159f4E6a99eF873f86901E3cafa7f9A7D`。RPC不得带用户口令/含密查询参数，不输出其URL。

### 3.2 Rust入口与兼容

在现有 `Run` 子命令additive增加 `--controlled-mode`、`--controlled-run-id`、`--controlled-started-at`、`--controlled-deadline-at`，由启动器固定生成，必须成组且只许 `btc-arb/PredictFun/mainnet`。deadline必须等于started+21600秒，不能从尾参数延长。普通run/check/TUI不带这些参数时保持旧分支；配置带controlled_paper但无对应受控unsigned上下文拒绝，不能误跑半套新口径。

`config.rs` 的受控加载先以拒重复键的serde Visitor读取公共对象并核验必填/固定值，再反序列化AppConfig；两个受控分支均不读YAML，确认保留缺失credentials路径。只读取该分支允许的PM环境字段：unsigned仅predict_api_key；signed按原受限装配读取private_key/predict_account/API。不能先走普通load再清掉已读的秘密。`AppConfig`新增默认None的可选paper配置，运行时 `ControlledRun`（mode/run_id/started/deadline及本地经过时间基点）用serde(skip)传给Ctx/Broker；旧直接构造者通过编译回归确认。

Ctx::connect 的unsigned分支在 `PredictFunTrader::new` 前返回 `(taker=None,limit=None,live=false)`，然后启用Broker受控cash；不能构造signer、trader、JWT，也不安装account/RPC读路径。signed及旧分支原样调用原factory/claim_run_confirmation/account gate。测试用内部factory计数接缝证明unsigned未调用构造器，不能只证明place=0。

## 4. SDK lazy keyring与主网API

不新增SDK child/argv代理。原 `cli.py` 四个固定命令增加独立布尔 `--keyring`，与旧 `--signer-fd`互斥；旧直接fd路径、函数默认及fake session_factory/signer_loader签名兼容。新模式先normalize并冻结目标副本/摘要，要求chain56、predict-account、owner与predict_account均为固定资产账户。plan/check（含tx hash读回）可选该账户绑定但不分配秘密pipe、不访问keyring；没有execute/确认、摘要错等仍沿旧错误。

执行模式在通过公开确认检查后创建非stdio匿名 `os.pipe()`（两端均≥3、不可继承），在原execute_target调用周围用finally管理两端；此时pipe为空、keyring读取仍为零。把读端传原signer_fd参数，把lazy closure传原signer_loader参数。为不在closure中猜controller，`execute_target`只additive增加keyword-only `expected_controller: str | None = None`；新keyring模式传固定signer，旧直接fd/注入调用默认None。在原 `controller=session.identity()` 后、任何loader之前核验该值，失配报CONTROLLER_MISMATCH且秘密读取为零。仅当原execute_target在market/allowance或redeem/Gas预检之后实际调用loader时：再次比较目标副本与已确认摘要→原 `_read_owned()`/派生绑定→单次写64位规范key到pipe并关闭写端→调用原 `fd_signer_loader(read_fd)`→关闭读端。没有worker线程/秘密临时文件/秘密环境/第二signer；SDK消费就在本进程，FD不继承给无关child，比另起SDK子进程更小。

所有前置拒绝、只读失败、already-satisfied no-op均不调用closure、FD secret read=0。正常、异常、KeyboardInterrupt/信号、外部超时终止由finally/OS关闭FD；写入量有界且小于pipe容量，不等另一个服务喂key。load_signer仍比较派生signer与原ReadContext(controller)，不是把target.owner改成signer。原execute_target的签名前再读余额/一次SDK调用、expected/broadcast hash、receipt+同目标读回与未知不重发不变；目标副本在预检后/取key前/交signed_builder前再验，变更拒绝而非重算确认。拒绝不得回显原目标文件、异常或密钥。

`ReadSession.market` 仅在实际mainnet market GET时沿现有 `YQUANT_PREDICT_FUN_TOKEN → PM_PREDICT_API_KEY` 来源取key，缺失/空白或来源冲突即失败关闭；保持构造签名与旧testnet/fake session兼容，纯plan不取key、不要求API/keyring/JWT。请求仅发往原固定 `https://api.predict.fun/v1/markets/{已验证正整数id}`，`x-api-key` 仅传该请求，固定 `timeout=15` 秒、`allow_redirects=False` 并保留原no-auth覆盖；明确拒绝3xx及其他非2xx，核验业务envelope成功、返回id与已确认market一致及route匹配。不使用全局Session默认header，不向Web3/RPC、其他host、redirect或日志转发key，不记录秘密或原响应/异常，不改target_digest。请求/解析/核验失败仍为READ_UNAVAILABLE/RECONCILIATION_REQUIRED，是未能检查，不伪造零余额/权限不足或completed。

## 5. Broker资金实现

### 5.1 唯一状态与原子入口

保留State的holdings/resting/marks/realized/fees/halted及原live::LiveState。State增加默认None的 `paper: Option<PaperCash>` 与受控 `entry_stop_reason`；Broker持有可选ControlledRun。PaperCash存B、当前单笔预占（默认空的market/w字段）、本轮mark有效性/时间、独立loss_latched布尔、已成交市场身份与结算去重事实，不建attempt→market映射/注册表，不复制持仓成本/库存/已实现损益。同锁同步take且拒绝rest，单笔字段足以表达校验→预占→成交/释放的局部转换；不得覆盖已有未闭合预占。entry_stop_reason只区别deadline/人工/监督丢失等停止原因，不能用deadline把loss_latched伪造为true，也不形成通用状态机。K从holdings.cost求和，P/P_m从单笔未转换预占及既有resting/live未闭合BUY事实按总量/market求和、同一风险只计一次，R复用state.realized；不为内部fixture另建生产风险记录。新增 `Broker::with_controlled_paper` 必须验证live=false/taker=None/limit=None；失败不返回半配置Broker。内部测试可注入cash1.5/历史R/P，生产CLI不开放这些覆盖。

`runtime.rs::take` 在旧分支之前分派到paper.rs的受控同步分支。该分支从校验、预占、原token_book/walk到成交/释放与loss检查始终持有同一state锁，整个过程无await/OrderVenue调用。数值先验、token与market匹配、显式tick/费用事实、当前数据/截止/loss门禁先检查；`rest`在受控模式固定拒绝 `CONTROLLED_REST_UNSUPPORTED`，不增加maker模型。旧纸面/live分支和未知订单保留机制不重写。

资金公式（USDT；shares为净库存）：

- `B=100+R-K`，`P=Σ剩余最坏BUY预占`，`A=B-P`，`V=Σnet_shares×有效mid`。
- `NAV=B+V`，`net_pnl=NAV-100=R+(V-K)`。P不再次扣NAV，浮盈/待结算收入不加入A。
- 原shares_for向下取整后 `w=q×limit`；必须同时 `1≤w≤2`、`K_m+P_m+w≤2`、`K+P+w≤10`、`w≤A`。非有限/非法份额、p/limit/tick、precision未知、费率非法或净份额负数均先拒绝，不向上凑到1 USDT，不以EPS放大资金。
- 同锁在空的单笔字段建立本笔market/w预占；walk全额成功、对价 `c=q×VWAP≤w` 后同锁 `B-=c; K+=c; P-=w`、清空本笔字段并增加净份额；价差w-c立即可用，不再为该成交保留w。明确未应用/ThinBook/截止拒绝只释放本笔；无终态的预占及既有resting/live未闭合风险保持，cancel受理不当终态。paper无网络提交，因此不制造真实unknown；内部单笔字段/既有事实fixture及原live回归验证未知保留，不新增生产unknown流程。
- 新分支截止重检在预占前及应用成交前，后一处即使已有预占也必须拒绝/释放未应用新增。无await不等于可省门禁；并发take只可顺序经过同锁。

### 5.2 净份额费用、损失检查和坏数据

继续调用市场taker_fee在模拟VWAP计算 `f=(bps/10000)×min(p,1-p)×q`，不新造费率模型。

| 事件 | 同一锁内变化 |
|---|---|
| BUY | `c=q×p; f_q=f/p; q_net=q-f_q`；B只扣c，holding.shares加q_net、cost加c，fees展示加f |
| SELL（只验共享接口） | 不超净持仓；沿原take可夹到净可卖量，但返回实际量，绝不能声称卖了原gross；basis按卖前均成本；B加c-f，R加c-f-basis，K减basis，净库存减实际卖量 |
| 官方回款 | 验证后收入=净库存×payout；B加收入、R加收入-basis、移除库存/K；不另收fee，不在live调用此虚拟回款 |

受控summary的 `fees_in_cash=state.fees` 表示费用已反映净额，使原 `Summary::equity()` 得到R+U，不能再次扣fees。另提供 `PaperSnapshot` 输出B/A/P/K/R及nullable U/NAV/net_pnl、mark有效性/时间；无法估值时不把旧summary的cost fallback用于健康判断。旧Summary字段/默认公式不改，旧模式继续gross+单列费用。

检查位置固定为：每次observe成功写mark后；BUY/SELL/费用应用后；官方回款后；每笔BUY预占前及成交应用前。有效 `R+U≤-20` 即设置原 `state.halted=true` 和paper.loss_latched=true，事件原因LOSS_LATCH；回升/结算不清锁，也不提供reset/resume入口。不是峰值回撤或只加亏损单。halt后策略仍能观察/结算但不能新增，不自动SELL/对冲/redeem。

在受控RoundTaker每个tick开始先使本轮持仓mark有效集合失效；原Known.observe仍拉取rounds+tracked_markets并逐book调用Broker.observe，只有本tick合法双边mid才能恢复对应token有效性。take前必须本tick候选book及全部未结清库存都有有效mark，失败/缺book不以旧mark/成本/零浮亏补齐。保留最后有效数值和时间用于披露，不用于放行。spot有限且>0、book价格/数量合法且双边mid有效才送core/observe。完整成功可解除临时DATA_INCOMPLETE，不解除LOSS_LATCH；原三次失败撤报价保留，无需改quoting.rs或新增恢复器。

source由RoundTaker在原quote→take相邻位置附着本次market/source/观察UTC，成交事件与预占/净额关联；一市场一次entry使其归属唯一。测试可以在内部方法传入SpotQuote，不增加spot生产provider/新feed trait，不复制DecisionCore或通过copy测试冒充消费者。

### 5.3 官方终态与去重

`venue.rs`给TradableMarket增默认None的 `round_facts: Option<RoundFacts>`，载体只含oracle status、trading status、两outcome status、显式decimal_precision、官方price_feed_provider。predict_fun.rs在原tradable映射填这些现有事实，ApiVariantData additive解析 `priceFeedProvider`；缺provider输出UNKNOWN而非推断Binance。缺feeRateBps原反序列化就失败；显式precision缺失不能借旧tick默认取绿灯。其他构造者沿Default保持兼容。

受控settle_resolved调用同一MarketData::market；paper.rs只接受与首次成交记录的market/两token/BTCUSDT/300秒起止身份一致、status=RESOLVED、tradingStatus=CLOSED、非contested、起止价有限且>0的事实。从原payout_yes mapping取值并对照官方start/end：涨1/跌0/精确平价0.5；非平价两outcome必须对应WON/LOST且相反，矛盾为CONFLICT。平价保留原官方把Up标WON的兼容：一WON一LOST不覆盖0.5，不凭WON强改1。缺终态/价格/outcome为PENDING；明确矛盾为CONFLICT，二者均无现金回款。不拿本地spot、到期时间、open=false或仅payout_yes非空当证明。

同一state锁中验证原库存/去重事实后应用回款并记本market结果，重复结果无新增现金；若收到与已应用事实冲突的重复结果，只记CONFLICT且停新增，不追溯改账。保留已成交市场的公开身份/结果用于末轮尾查和最终证据，不从它恢复交易。live仍沿原settle与账户/receipt/资金读回，settled不是redeem到账；不把paper子模块用于live余额。

## 6. 一次性生命周期与证据

### 6.1 截止、停止和尾查

沿原drive，不新建监督服务。启动器用UTC绝对deadline与CLOCK_BOOTTIME经过时间，任一到21600秒即截止；Rust Broker另在每次入场前/应用前检查绝对UTC及其本地经过时间上限。准备时间由父已开始的预算覆盖，WSL暂停后先判截止；时钟倒拨不重置父经过时间。fake clock只内部注入，不开放生产延长参数。

Popen固定argv/cwd、shell=false、close_fds=true，单次BOT child，stdin=PIPE。父写端只由启动器持有；只允许一个固定控制字节D表示deadline，关闭/EOF表示监督丢失或紧急停止。Rust在受控上下文、第一次seed/tick等待之前启动一个标准线程读stdin：收到控制/EOF先经Broker同锁设置entry_stop_reason阻断新风险，再用有界channel通知原drive清理；D之后仍监测EOF，不能因已截止就失去监督丢失检查。不使用退出时可能等待无界stdin blocking task的tokio::io::stdin。线程只设置停止标记，不执行策略/网络/资金记账、不持秘密、不另生进程；正常退出不join等待，OS回收管道。未知输入按CONTROL_CHANNEL失败关闭。

原drive受控分支用biased select优先停止/期限；unsigned的tick和settlement future均置于停止与期限外层，不能只在ticker外判一次。读到D/本地截止即同锁关闭新增，放弃未应用paper预占，走原cancel_all；普通清理≤30秒。之后仅复用同一Broker/data对尚未确认的本次已成交市场进行最多600秒的只读尾查，不再调用策略tick。每市场60秒节奏、请求/整次market读取≤min(15秒,剩余总预算)，包括market+category等内部等待；无重试累加突破总预算。最后一轮延迟结算可应用一次，未确认保留pending及最后有效估值时间。

父在deadline送D后继续收集经白名单验证的结果，最多等待截止后30+600秒；deadline不立刻发SIGINT破坏正常尾查。SIGINT/TERM/HUP或EOF是紧急停止：先关新增/取消，跳过或中断尾查，不为补报告延迟响应，≤30秒kill/wait回收。父异常finally同样传播原SIGINT并有界回收；父被SIGKILL则OS关闭唯一写端，child EOF路径停止。正常尾查完成后child退出，父关闭pipe/drain并wait；卡住则在剩余清理预算内强制kill/reap，不自动重启。

signed分支复用原live tick不随意drop在途写入，共享check_entry及实际预占前同时检查ControlledRun/entry_stop_reason与原账户未知闭锁；控制通知可先关闭新风险，不能等tick结束才把下一单挡住。停止沿原Ctrl-C/cancel_all，未证终态继续保留风险，不能用纸面释放逻辑；signed没有paper尾查/虚拟回款。其真实超时/撤单成功不在本轮宣称已验；本轮只fake证明信号传播和有界父回收。

退出事实分开：launcher_exit、child_returncode/原生signal、stop_reason、forced_cleanup、tail结果。正常窗口结束可launcher_exit=0，但pending/child非零/强杀仍须如实披露，不拿外层0改写child。输入拒绝exit2；启动/强杀/异常/不完整输出exit1；人工信号保留对应中止语义。loss_latched后继续观察不是恢复，deadline后零新增不是已平仓。

### 6.2 最小证据而非主账

实际运行主题 `data/reports/YYYY-MM-DD-btc5m-controlled-paper/` 下固定 `evidence/<run_id>/started.json`、`public-config.json`、`events.jsonl`、`ended.json`。目录/文件exclusive-create；同run目录已存在即拒绝，无覆盖/删除/自动换ID重试。started在child前写成功，记录SPEC要求的schema_version=`btc5m-controlled-paper.v1`、UTC/期限/模式/配置与候选身份。候选为主/BOT HEAD、实际binary和受影响文件SHA；只允许固定原生Git只读身份命令，无用户command/PATH替换。新公开快照不含秘密，实际run不修改tracked示例。

Broker只通过固定前缀 `BTC5M_EVENT ` 后的JSON输出受控事件，涵盖预占/释放/成交/阻断/LOSS_LATCH/结算/summary/final；是唯一账务状态的输出，不是新事件主账。沿SPEC字段输出gross/net/cash/fee方向、B/A/P/K/R/U/NAV、market/token/source时间与provider、pending/conflict及Gas/模拟限制。最终事件含全部尚未结清市场和去重后已确认结果；事件足以按公式逐笔复算，不能只留分母/末行净值。

启动器以selectors同时drain两输出，单行长度有界（64KiB，超限丢弃并记OUTPUT_INVALID）；只接收完整前缀JSON且严格验证字段类型/有限金额/ASCII数字market与token/时间/枚举reason和source/provider。未知字段、自由文本、原HTTP响应/异常/URL、非协议stdout/stderr不写盘、不转发；只记录固定错误/丢弃计数。首次落盘前按字段白名单重建JSON，不靠“先保存raw再脱敏”或仅替换已知token。关键账务事件被拒/丢失即中止并标记证据不完整，不能仍报可对账通过。

ended只在回收后独立创建，含SPEC final_accounting/settlement_status/exit_facts及paper、源回退、Gas NOT_INCURRED/NOT_MEASURED、非alpha限制。若缺/坏final，金额未知用null+固定原因，不从丢弃的日志猜账；缺/坏ended按中断处理。所有证据不是resume输入；同run永不再启动，新run须主控核账及新明确授权，改ID无自动许可。data被忽略不等于备份，不上传秘密/原响应，不建任务状态镜像。

## 7. 稳定拒绝与最小回滚

不新建公共错误框架。Python沿Failure/ToolError的code/step/reason；Rust沿Blocked加必要枚举并映射固定token。新增token固定为：`PUBLIC_CONFIG`、`CONTROLLED_MODE`、`ENV_CONFLICT`、`API_SOURCE`、`API_CONFLICT`、`DUPLICATE_RUN`、`INSUFFICIENT_CASH`、`INVALID_NUMBER`、`MARKET_RULES_UNKNOWN`、`DATA_INCOMPLETE`、`CONTROLLED_REST_UNSUPPORTED`、`LOSS_LATCH`、`DEADLINE`、`PARENT_LOST`、`CONTROL_CHANNEL`、`OUTPUT_INVALID`、`SETTLEMENT_PENDING`、`SETTLEMENT_CONFLICT`、`TARGET_CHANGED`、`CONTROLLER_MISMATCH`；已有OrderCap/MarketCap/TotalCap/BelowMinimum/ThinBook等沿原名称。公开错误不得拼接输入值、keyring返回体或上游异常。

受控BUY优先级：非法输入/身份事实→DEADLINE或已关闭新增→LOSS_LATCH→DATA_INCOMPLETE→最低金额/单笔/市场/总量→现金；拒绝不改变B/K/R/库存，明确本次预占释放只发生一次。pending/conflict不当零损失或已回款；loss锁不因数据恢复消失。SDK沿原错误优先级，前置确认/只读失败不取key，广播后不明保留hash/不重试。

降级只有停止或pending，不能改源/调参/提高2 USDT/补资金/放宽状态解析或调用真实check来修unsigned。最小回滚为停用新btc5m入口、受控opt-in字段和SDK --keyring，保留旧默认消费者、已验keyring/check/sign-in及原SDK直接fd。若需代码撤销，只在本次allowlist回退增量并同步测试/说明，不reset/stash/clean/checkout整个共享树，不删证据/keyring条目、不改依赖。不以停用现金后跑旧paper替代本次受控验收。

## 8. 定向测试、实施顺序与交接

### 8.1 A001–A019 可证伪映射（后续执行）

全部无网/synthetic；合法账户派生正例只内部注入公开测试身份，不伪造固定账户私钥。网络、真实keyring/钱包签名设为调用即失败；测试可用隔离socketpair/匿名pipe/fake executable。数值容差沿SPEC，身份/状态/调用计数零容差。以下是测试设计，不是本卡PASS。

| SPEC | 真实接缝 / 必须断言 |
|---|---|
| A001 | 新Python真parser+config加载及Rust受控load/main测试：缺/错模式、缺值/300/null/布尔金额/非有限/重复键/链网络开关/credentials含悬空链接/任意尾参数；全部秘密/child/网络=0 |
| A002 | Python入口fake child捕获argv/env；Rust实际Ctx装配调用带计数trader factory及Broker.take，合法unsigned构造/派生/auth/place/RPC计数全0；钱包/JWT键在读取值前拒绝 |
| A003 | signed固定fake run的原signer装配、预算/RPC/账户门禁正反例；错身份/开关拒绝；原helper check/enroll/sign-in完整回归，不只看新函数 |
| A004 | cli.run→normalize→execute_target→lazy closure→真匿名pipe→原fd_signer_loader→原SDK builder（底层sign/send fake）；plan/check/tx/缺确认/只读失败/no-op读取均0，旧直接fd保持 |
| A005 | 捕获真实ReadSession.market的requests接缝及RPC fake：mainnet有/无/冲突API，testnet/fake兼容；header仅固定host、3xx不跟随、15秒、坏route/id/envelope关闭，target_digest不变 |
| A006 | 预检期间修改target、错controller/派生、pipe写/读失败、异常/信号/超时回收；签名前拒绝，所有FD关闭；原SDK送出不明/receipt/readback失败保留hash、send/sign只一次、completed=false |
| A007 | 实际受控Broker初始B/A=100；内部cash1.5且其余限额可用时最坏2拒绝资金全不变；普通Broker::new无cash仍可用 |
| A008 | 实际take并发/不同市场五笔各2与第六笔、同市场；内部单笔预占字段/既有resting/live未闭合事实fixture，不建attempt注册表；较优VWAP退差价、ThinBook/取消/unknown保持规则，逐事件B=100+R-K、A=B-P，不双算 |
| A009 | 原take+book q5/p.4/bps200：f=.04、扣.1份、净4.9、B98/K2/P0、U=-.04/NAV99.96，费用不二扣；快照与Summary对拍 |
| A010 | q2.5/p.8：f=.01、扣.0125份、净2.4875；A009库存SELL4.9@.6：gross2.94/fee.0392/net2.9008/B100.9008/R.9008；卖gross5不得产生5份成交，无策略主动退出 |
| A011 | take→原MarketData fake→受控settle：WON/LOST/DRAW的B=102.9/98/100.45、R=2.9/-2/.45、K0；pending/争议/缺起止/错token/非300/冲突不回款，重复无增量，live不虚拟补cash |
| A012 | 真实loss检查R=-19/U=-1锁；-19.999不锁；峰值+10后-11不锁、先赢后亏按累计净额，回升-10仍锁 |
| A013 | 同tick第一fill费用或observe/settle触-20后第二take拒绝；持仓之一book缺失/旧mid/无mid/非法spot导致DATA_INCOMPLETE，现金占用不丢、U未知，不凭旧成本放行 |
| A014 | RoundTaker真tick提取仅输入获取接缝供内部fake quotes/books，仍调用同core/take；非300/无起价/预热不足/29与30秒/单轮一次；Binance/Coinbase成交source逐笔关联，signed source guard保留 |
| A015 | fake UTC/经过时间/内部clock在21599/21600与同边界信号、等待跨deadline/倒拨/暂停恢复；新增前及应用前截止优先，loss后可观察但不重开，不真跑6h |
| A016 | 真无网fake executable+pipe测试正常/非零/SIGINT/超时/拒停和父SIGKILL；child EOF能停且实际reap；同run/缺ended/crash/resume拒绝，startup一次，launcher/native exit分开，≤30秒回收或强杀如实标记 |
| A017 | 同Broker有限尾查fake clock+MarketData：最后轮迟到只兑付一次，一直pending/争议停止于600秒；GET请求夹≤15秒、60秒节奏、只已成交市场，策略/认证/redeem/新增计数0 |
| A018 | stdout/stderr/异常/URL/协议字段/超长行/FD注入synthetic key/API/JWT/signature/代理哨兵，首次文件write spy无哨兵/秘密摘要；坏账务事件停而非丢后PASS；公开事件能复算、Gas和非alpha准确 |
| A019 | 旧helper全套、SDK identity/ops、Rust lib/bin/replay及全部受影响直接构造者实际回归；默认无paper opt-in不变，ignored网络测试不运行，不以编译代替上面消费者 |

测试不为每条A建文件；新Python测试共用表驱动fixture，原WireBackend/TemporaryBot只作为隔离底层复用，SDK仍调用安装的官方builder，Rust资金/尾查测试统一放paper/tests.rs、策略测试仍放arbitrage.rs。Predict映射只少量断言保留在原tests，不搬其他测试树。内部短时钟/短清理预算只测试可注入，至少一条实际OS子进程超时/父退出回收测试，不能全靠mock抛TimeoutExpired。所有临时文件由当前worker的TMPDIR/scratch承接，不用真实BOT binary。现有helper/SDK接线及A004–006已落消费者保留，未变部分引用仍适用证据，不从零重做；校准中的lib与launcher通过不替代完整覆盖；重复键须测嵌套对象/数组内对象，现金用实际Broker序列而非把helper测试注释当矩阵覆盖。

提取必须保留Python `RustProtocolTest`真实消费者：原测试可执行文件filter `bot::runtime::paper::tests::control_pipe_drive_probe`，以及cargo精确filter `bot::runtime::paper::tests::signed_ctx_uses_original_factory_and_identity_bound_budget_gate`、`bot::runtime::paper::tests::protocol_consumer_fixture`仍命中原测试并生成所需事件；不得因文件迁位改名、skip或把零命中exit0当通过。迁移后先执行受影响Rust tests及Python这组消费者，再追加§2.2反例，最后受影响完整回归；test-only源码只经cfg(test)加载，无生产API/行为变更。

### 8.2 后续安全命令

以下仅供Implement/独立Validate按授权执行，本卡未执行；cwd=BOT，每次单条原生命令，不与内联解释器/管道/嵌套shell拼接。Python使用既有隔离环境，不安装依赖：

1. `tools/predictfun/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_btc5m_control.py -v`
2. `tools/predictfun/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_sdk_ops.py -v`
3. `tools/predictfun/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_local_signer.py -v`
4. `tools/predictfun/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_sdk_identity.py -v`
5. `cargo test --offline --locked --lib`（默认不运行ignored网络测试）。
6. `cargo test --offline --locked --bin polymarket-toolkits`。
7. `cargo test --offline --locked --bin btc_arb_replay`（源码实际位于src/bin/，不是不存在的integration-test target）。
8. `cargo check --offline --locked --all-targets`；按实际修改Rust文件运行rustfmt检查，不全仓重排旧格式。

固定运行用法：`tools/predictfun/.venv/bin/python -B tools/predictfun/btc5m_control.py --mode unsigned-paper --config tools/predictfun/btc5m-controlled-paper.json --run-id <主控批准的唯一公开ID>`。仅在独立 PASS、主控核验及该次新授权后才由主控执行；本 Design 不执行、不安排 cron，不提供真实 approve/redeem 或 signed 启动指令。它自身冻结 run-scoped 配置、监督并回收。V1.3 后续直接用原命令无需 inline 包装，父环境源优先、完全缺键才取固定文件单键；原环境空白/冲突或文件无效固定拒绝，不在 argv 填秘密，不自动重试/另起 6h。

### 8.3 原 V1.2 实施顺序与 Gate（历史，不是本增量待办）

1. 主控Gate后先按§2.1第4项机械提取全部paper内联tests/fixture至唯一paper/tests.rs，保留模块路径/测试/断言和原生产位置；不重做V1.1已落impl迁移。跑受影响Rust及Python executable/filter真实消费者，核对非零命中/无迁位skip，再报各文件实际格式化行数。
2. 围绕§2.2当前剩余项补应用前截止/release、cancel_all超时final、阻塞market/边界信号及cleanup wait预算spy；仅加必要内部测试接缝，不迁旧业务/其他tests、不新增生产模块，不重建已闭合SDK/core。
3. 在同一批Rust协议→Python首次write消费者补完整SELL/LOSS/PENDING/CONFLICT逐事件矩阵；保留100 USDT/2/2/10/20、deadline/600秒尾查、普通路径与已落说明，必要时只同步受本次变化影响的说明，不启动真实策略验证功能。
4. 完整受影响回归GREEN、scope/G3/身份/公式检查后，Implement完成释放预建独立Validate；独立角色执行矩阵并在唯一validation报告裁定。任何必需项未覆盖明确NOT_VERIFIED，不能拿旧259/35等历史测试数充新结果。

原 V1.2 文档卡只交主控同卡 Design Gate，不自行 complete 放行 Implement、不另建 Review worker；原 Implement `t_27b504c6`、Validate `t_e5684511` 为历史阶段引用，当前增量沿 §8.4 与现有 Kanban 依赖，不重建旧链。Gate 核对三层来源、必要性、allowlist 与验收；开放业务契约项0，超范围或不可实现冲突须集中交主控，不自行扩范围/削验收。安全拒绝停对应动作并留原证据，不换形态绕行。

本Design的静态核验不证明SDK真实网络/生产keyring、当前余额/权限、签名run、真实approve/redeem/下撤单/到账、6h观察、Gas/排队/部分成交或alpha；这些边界不会因文档完成改变。

### 8.4 V1.3 当前实施、回归与最小回滚

1. 先在原测试文件为固定路径加全套 fixture 隔离：所有缺源场景（包括原 missing-source 断言）patch 到不存在或明确内容的 scratch 文件；禁止意外读生产 skills/.env。用新增 B-001–B-006 获得真实 RED，再只在原 check_environment 的父禁键拒绝之后补“缺键才读→局部副本→原 _api_source”；signed 分支不调用此读取。先把原 source/API 冲突/空白语义保留，再更新两处说明，不新增配置或包装器。
2. 真 run 回归捕获公开校验/禁键拒绝/credential-read/首次证据 write/child 的实际调用顺序。合法 fallback 用原无网 OS fake child 捕获 env；合法原 env 用调用即报错的文件 spy 证明读取 0；坏 JSON/秘密键（两模式大小写/嵌套）、每个父钱包/JWT 键必须先拒绝且读取/write/child/keyring=0。源存在但空白不回退，原别名相等兼容/冲突拒绝；所有文件错误逐项固定脱敏 API_SOURCE，不能只测解析函数。signed 缺源仍拒绝且无读取，合法 signed fake 原链不变。
3. 覆盖 SPEC B-001–B-006 全部语法/重复/缺失/空白/权限或 I/O/引号/多行/编码反例、字面插值不执行、文件其他秘密不入 child/父环境，以及成功/失败 stdout/stderr/全部普通输出无哨兵/秘密摘要；输入 synthetic fixture 是唯一允许保存测试哨兵的输入。保留原 F1 首次 write 拒绝矩阵、F2 Rust 协议 executable/filter 消费者及全套断言，不 skip/删测取绿灯。新旧 launcher 测试只用 profile scratch、fake 网络/keyring/child，不触真实 BOT binary，不 cargo build，不启动/停止/重启现行观察。
4. Implement 与独立 Validate 分别运行受影响完整 launcher 命令：`tools/predictfun/.venv/bin/python -B -m unittest discover -s tools/predictfun/tests -p test_btc5m_control.py -v`，cwd=BOT；保留真实原生 exit、候选 HEAD/四文件 SHA、新矩阵及未覆盖项。SDK/helper/Rust 业务未改，复用仍适用既有独立结果，不跑 §8.2 旧全库清单或任何新 6h。必要新测试原始证据仅放 `data/reports/2026-11-16-btc5m-market-key-bootstrap/evidence/`，不覆盖 R1/R2/R3/当前 run；Implement 不另写重复结果报告，独立 Validate 仅新增同主题 `validation.md`。任务状态/交接仍只在 Kanban，不新建状态镜像。
5. 当前文档卡只做三层静态一致性、逐条原生 git diff-check/sha，交主控 Gate；不提前 complete 释放预建 Implement，不 request_review。本增量完成后仍不自动授权下一次启动。最小回滚只撤销本次四文件中的单键回退/对应说明与新回归，恢复原 env-only 来源；不改变旧资金/费用/生命周期、不改存储/依赖、不删证据、不干预当前运行。
