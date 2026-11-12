# DESIGN-03-018: yquant-data 独立库与 BTC5m 官方历史每日摄入

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | V1.1历史基线 + V1.2 Step1/2已裁定；待新候选独立Verify及生产补齐 |
| 作者 / 日期 / 任务 | YQuant Principal；2026-11-11 Asia/Shanghai（UTC+08:00）；`t_2f744e19` |
| 来源契约 | [RFC-03-018 V1.1基线及§8 V1.2](../../rfc/03_data/RFC-03-018-yquant-data-history.md)、[SPEC-03-018 V1.1基线及§9 V1.2](../../spec/03_data/SPEC-03-018-yquant-data-history.md) |
| 唯一裁定 | [correction-plan.md](../../../data/tasks/active/2026-11-11-yquant-data-history/correction-plan.md) |
| 项目 | `/home/pascal/workspace/yquant-investment`；禁止另一项目、profile/配置/依赖/Git 写 |

## 1. 复用基线与差分结论

主控已停止旧 run3592，冻结主题 `evidence/rebaseline/candidate-baseline.json`；52 项均存在，C1 本地逐文件 hash 与冻结值一致。`candidate-regression.log` 为主控实跑 1750 passed / 433 warnings / native exit 0 / 23.38s，只作候选校准，不是独立验收。本卡仅定向读源码/文档，不重跑工程 suite、不执行生产。
原 `evidence/design/allowlist.json` 的 Move 项以 destination 计入 52 路径；两个 audit 测试已在 `scripts/unified_data/tests/`，不得再迁位。旧 V1.0 的“待新增”描述已失效，不重建当前模块。

| 分类 | 可定位符号 / 当前证据 | 本轮处理 |
|---|---|---|
| 可复用候选 | `storage.select_databases/assert_ud_database`、`storage_composition.build_persistent_client`、`UnifiedDataClient.read_btc5m_history`，sector `ConnLoader.load_source_db/load_ud_db` | 仅验证双库、原认证源、facade/真实句柄 guard；不重写装配 |
| 可复用候选 | `migrate_ud_database.build_manifest/compare_collections/copy_collections`、`MigrationDatabase` | 五集合、逐 ID、实际 metadata、insert-only/TTL 核验保留；只修下表静默事实/错误报告 |
| 可复用候选 | `PredictRoundExtractor/BinanceKlineExtractor`、`PredictRoundTransformer/BinanceKlineTransformer`、`HistoryBatchLoader`、`HistoryRunner.run_round_days/run_kline_day`、`IngestionStore` | 保 raw/CHECKSUM、Decimal/微秒、批写读回、游标/日进度与 pending；只补实际底线缺口 |
| 可复用候选 | `Btc5mHistoryReader.read/_scan/_rows`、`HistoryWindow`、`history_input.iter_history_input`、daily 模板 | 稳定窗口读取及来源/标签隔离验证，不重写研究链 |
| 确切剩余 delta | `migrate_ud_database._require_apply_evidence/main`（原512–559、780–782行） | 去外部 writer 绝对排除及静默文件 hash/时效条件；保有限窗口事实/有效权限，错误报告列具体缺少 action |
| 确切剩余 delta | `run_btc5m_history._run_apply`（原383–398行） | pending 回查401/403不能提前 return 饿死 Binance；停 Predict 通道并保另一源预算 |
| 确切剩余 delta | `HistoryRunner._review_round_day/_finish_round_day`（原996–1061行）、CLI `_run_verify/_run_apply` | 目前仅统计 stored/settlement，有少量 resolved 即可 complete；补名义缺槽/重复/身份/重叠与官方状态分列、无未解释缺口才 complete，conflict 退出20 |
| 确切剩余 delta | CLI `_window_start_date/_run_apply`（原315–319、343–345、375–417行） | 非零 warmup 已改变锚点但计划仍从主窗日开始；计划/摄入纳入预热所在 UTC 日，精确锚点和主窗分母不变 |
| 本期不再必验 | reader `_assert_states/_pages` 的逐页复核、`HistoryWindow.verify_consumed`、`HistoryInputBundle.iter_scheduled/verify_consumed` | 严格并发/三流确认/通用可得时间调度不设首版专项门禁；正确内部增强及现有兼容调用可留，不强拆 |
| 本期不再必验 | migration `_index_schema/_index_rows` 的 SQLite 摘要、CLI `Budget.fork`/runner `recheck_pending` 的内部预算组织 | 不要求新建或泛化这些设施；不因删旧门禁而删除安全/数据正确性回归 |

这不是全实现独立审计结论。C3 按以上可定位差分修复；其余候选保留并验证，不按52项重新开工。不额外发明 UT 编号族或任务 runtime。

## 2. C3 精确写 allowlist（原52项的必要子集）

| 路径 | 允许修改的符号/断言 |
|---|---|
| `scripts/unified_data/migrate_ud_database.py` | `_require_apply_evidence/main` 的操作事实与缺权限报告；不重做摘要存储/复制框架 |
| `scripts/unified_data/tests/test_ud_migration.py` | 有确认但无全局writer证明/hash/时效token可执行；缺确认仍零写、具体action缺口、原冲突/TTL/源漂移断言保留 |
| `skills/data/data-pipeline/scripts/run_btc5m_history.py` | `_run_apply/_window_start_date/_run_verify` 的单源故障隔离、预热计划、round覆盖与退出报告 |
| `skills/data/data-pipeline/scripts/btc5m_history/runner.py` | `_review_round_day/_finish_round_day/run_round_days` 直接相关覆盖/状态计数，不加调度平台 |
| `skills/data/data-pipeline/scripts/btc5m_history/tests/test_cli.py` | pending401/403仍尝试Binance、warmup计划、conflict20、verify拒绝缺槽伪完整 |
| `skills/data/data-pipeline/scripts/btc5m_history/tests/test_runner.py` | 缺round/重叠/重复/全pending状态、完整水位不越缺口及既有游标恢复 |
| `tests/data/test_yquant_data_history_integration.py` | 上述差分的跨模块假库/raw离线读回验证；不新增默认real开关或网络/凭据访问 |

没有必要改动的行只验证，不为用满 allowlist 而改。其他45项是候选只读复用，不重新允许整批改写。无新源码/测试文件，无 Move；C3 不修改三契约/SKILL/其他报告主题，不把原52项作为无限修改许可。新发现范围外真实缺陷向主控报告，不自行扩写。
G3：当前 `runner.py` 1216行，职责仅两固定源日编排/日进度/续跑；增长原因仅补缺槽等既定正确性断言。此次不另开大拆分；新增源/新调度能力或继续实质扩展时先按日进度与源日处理边界拆分，由独立 Review 检查。既有 `test_sector_ranking_rollout_gate3.py` 1519行，本次不写；其双库接线已有候选，未来扩展独立场景前先拆职责。router/旧research均不写。

### 2.1 C4 F1–F3 最小修复范围补充（2026-11-11 Pascal确认）

本节只补实现文件清单，不改RFC/SPEC V1.1的字段、身份、标签或验收语义，不重新做架构设计。§2七路径是已完成C3的写范围，保留其历史归属；C4首次独立验证FAIL（run3597）揭示的是原52候选内既有转换缺陷，不能据C3旧PASS宣称已修。C2及C3文档hash是补充前历史身份，后续Fix/C4-R2/C5须绑定本节补充后的实际Design hash；RFC/SPEC保持原字节。

Fix仅允许以下两个原52项路径，不允许第3个代码/测试文件：
- `skills/data/data-pipeline/scripts/btc5m_history/transforms.py`：仅`PredictRoundTransformer.transform_one/_select_variant/_resolve_outcome`及必要小型纯辅助；补upDown/crypto同语义候选及冲突检查；转换前拒绝bool/非整数/非法ID文本，禁止有损修复自然键；未知结果名不再凭indexSet伪造官方方向，保既有明确UP/DOWN/DRAW规则。
- `skills/data/data-pipeline/scripts/btc5m_history/tests/test_transforms.py`：补上述合法嵌套/矛盾嵌套/非法ID（含JSON Decimal路径）/未知结果名负例及明确方向正例，不删既有底线断言。

F1–F3证据与期望见`data/reports/2026-11-11-yquant-data-history/correction-engineering-verify.md`和其`evidence/correction/c4/repro_cases.py`，旧证据只读保留。一个Developer Fix后，原C4卡以R2输出新报告/证据独立复验（先绑定Fix真实parent，修复完成前保持blocked），既有C5及P1–P3链不重建。Fix/C4-R2零真实HTTP/Mongo/env/凭据/服务/cron/交易/外发；不扩大平台或业务契约，任何未授权范围外缺口报告主控。

### 2.2 C5-01–07 集中修复范围与闭合清单（2026-11-11 Pascal同意）

C5/run3600 的 REVISE 与七项 major 保留，完整事实见主题 `correction-engineering-review.md` §1及 `evidence/correction/c5/review_cases.py`。Pascal在完整清单后明确同意集中最小修复。本节只细化既定SPEC V1.1正确性要求和必要文件范围，不改RFC/SPEC业务契约、不重新设计平台；§2/§2.1保持C3/Fix1历史归属及F1–F3已闭合事实。不得因旧C4-R2 PASS或1860测试通过宣称这些新缺口已闭合。

Fix2严格allowlist为以下12个既有路径（6源码+6测试），无第13个源码/测试文件；都来自原52候选。没有必要的行不改，范围不足先报告主控，不把整52项重新开放。

| 路径 | 仅允许的差分 |
|---|---|
| `skills/data/unified_data/history_types.py` | C5-01：现有Decimal规范化精确且不受context精度舍入，稳定内容hash能区分不同可存Decimal128事实 |
| `skills/data/data-pipeline/scripts/btc5m_history/common.py` | C5-07：观察时钟保留实际精度，交给已有ceil-ms路径，禁止截秒造成提前可得 |
| `skills/data/data-pipeline/scripts/btc5m_history/extractors.py` | C5-06：官方归档的预期成员名、本日归属及全文件跨chunk严格顺序/重复校验后再交批写 |
| `skills/data/data-pipeline/scripts/btc5m_history/loader.py` | C5-01/03/04：精确比较、新pending正常到期入队、局部保留枚举与合法按ID补齐raw关联；同事实幂等、终态冲突零覆盖与CAS不弱化 |
| `skills/data/data-pipeline/scripts/btc5m_history/runner.py` | C5-02/03/04/05：显式apply调用的三历史集合必要索引初始化/核验；正常首次pending到期回查、补齐证据/日摘要衔接；规划尊重due且未枚举日期有实际进展 |
| `skills/data/data-pipeline/scripts/run_btc5m_history.py` | C5-02/04：仅显式apply在写前初始化/核验必要索引；verify分别核枚举身份与最新官方补齐raw，不能放宽事实一致性 |
| `skills/data/data-pipeline/scripts/btc5m_history/tests/test_extractors.py` | C5-06的跨chunk逆序/重复/越日/错误成员名及正常多chunk |
| `skills/data/data-pipeline/scripts/btc5m_history/tests/test_loader.py` | C5-01/03/04/07的精度/自然键/回查入队/合法补齐与终态冲突/观察时间控制 |
| `skills/data/data-pipeline/scripts/btc5m_history/tests/test_runner.py` | C5-02/03/04/05的索引、真实回查/日续跑、预算/due/未枚举日期推进 |
| `skills/data/data-pipeline/scripts/btc5m_history/tests/test_cli.py` | C5-02/04的公共apply鲜库/重复/不兼容索引、plan/verify零DDL、补齐后只读verify |
| `skills/data/unified_data/tests/test_btc5m_history_reader.py` | C5-01/07的context无关内容摘要、实际观察前不可读/之后可用 |
| `tests/data/test_yquant_data_history_integration.py` | 完整288槽pending→按ID官方resolved→重新装配模拟重启→重复daily→只读verify；零手改due字段，终态真实不一致仍conflict/不覆盖 |

七项闭合必须一次给出证据：01覆盖34位Decimal128、等值尾零/非等值低位及多个context；02公共apply先核固定三集合自然unique/范围/pending索引、无TTL，重复apply不重复建，不兼容STOP且plan/verify/import零DDL；03首次pending无需手改DB即进入有界按ID回查，未来due不请求、终态不重查、401/403保另一源；04枚举raw和官方按ID结算raw及checksum局部关联，旧pending重放不降级终态，最新事实必须有raw精确证明，日状态/摘要按补齐重核；05未到期pending/缺档不会永久占满历史预算，连续多轮让未枚举日期推进，水位不越缺口；06任何越日行不可入库、全文件顺序/成员名违规明确失败不complete；07观察时间不向下截断，原始/strike/label路径与reader都不得提前可得。

C5-04只在现有记录/日证据中保最小的枚举与按ID补齐raw引用和摘要，不新增集合、通用版本库、确认协议或strict PIT；原raw不改，稳定业务DTO/schema v1不变。C5-02不授权本轮真实DDL；只开发/假库验证已承诺索引，真实历史集合DDL仍在既有P2显式apply，不能混入P1五集合迁移。当前§3“索引沿用候选”由下文修正为必要初始化，非另加Activation。

G3：修前runner为1266行，职责仍是两固定源的日进度/回查/raw衔接；本次增长只能为以上正常续跑和正确性，不增加源或调度层。此次由fresh Review专门核职责/增长/拆分触发，不为减行数做无关重构；今后新增源/新调度能力或进一步非本清单的实质扩张前按源日处理/日进度边界拆分，超过现行G3档位先停报主控。

依赖为一个Fix2（developer）→一个fresh Verify2（tester）→一个fresh Review2（reviewer）；不为七项逐项建链。原C4-R2及C5/run3600保历史，C5不无修复重跑/不改判；P1–P3卡复用，P1先加fresh Review2父边再移除旧失败C5边，仍blocked等待新APPROVE及原短窗口事实。新候选/三契约hash与R1/C4/C5旧证据按新轮次区分，RFC/SPEC字节不变；所有本轮操作只离线，生产NOT_RUN。

### 2.3 Review2剩余两项窄修（Pascal确认：好的，请尽快）

闭合清单已重锚：F1–F3及C5-01/02/03/05/06保持CLOSED，旧Verify2的1885 PASS保其已测范围，Review2/run3603的REVISE保留。仅剩`Review2-01/C5-04`正常pending部分补价的raw重放、`Review2-02/C5-07`响应前观察时间；依据原SPEC V1.1，不改业务契约、不重做前五项、不重开Principal/新平台。完整证据为主题`correction-engineering-review2.md` §1及其原字节`evidence/correction/review2/additional_cases.py`。

Fix3只允许三条既有路径，无第四个源码/测试文件：`skills/data/data-pipeline/scripts/btc5m_history/runner.py`（仅`reconcile_round_raw`及`recheck_pending`直接相关）；`skills/data/data-pipeline/scripts/btc5m_history/tests/test_runner.py`；`tests/data/test_yquant_data_history_integration.py`。源码仅一个runner，旧§2/§2.1/§2.2是各阶段历史归属，不能据旧范围重复改其他模块。

- 01：局部raw续接区分合法非终态单调补齐与最终resolved；未终态不强索不存在的最终resolution_evidence，但当前类别raw/身份/精确hash与必要证据仍核真，不能盲skip、吞坏raw或把pending伪complete。测试原verify/restart两反例及pending→部分补价→后续真实resolved完整链；坏/缺raw、不同身份、终态矛盾仍拒绝，保原288槽日链和已接受事实零覆盖。
- 02：queue due/backoff的moment与观察时钟分离；每个身份请求的类别/status两响应完整取得后再取实际utc_now供新事实观察时间，已有first/start/label时间保留、ceil-ms不提前。`now`仅作due选择/退避注入，不能默认等同晚到响应的观察时刻。测试传输中时钟推进，补strike/label在响应前不可见、ceil后可用，原事实时间不改。

一个Fix3→fresh Verify3→fresh Review3，原失败Review2不重跑、不改判；既有P1先加fresh Review3依赖再摘旧Review2边，仍blocked等批准及原窗口事实。仅本Design补范围/版本记录，RFC/SPEC字节不变，新三契约身份传递到三卡；原52候选身份及三条修前字节存`evidence/correction/fix3/`。runner修前1426行，增长仅本次两固定源正常回查/raw延续，仍依§2.2职责/G3与未来拆分触发，不做无关重构。全部离线，生产NOT_RUN。

### 2.4 Predict 403/1010 的透明应用标识窄修（Pascal同意）

P2/run3609首日出现HTTP403。主控经两次分别获准的单次只读诊断确认：原urllib默认客户端签名返回Cloudflare1010；同key、同URL、同传输仅增加真实`User-Agent: YQuant-DataHistory/1.0`后，于2026-11-11T08:02:39Z取得HTTP200、success=true、100轮及cursor。证据为主题`evidence/correction/p2/access-diagnosis/`两个独立诊断结果；不伪装浏览器、不换凭据/出口、不关闭防护。诊断不是入库或92日覆盖证明。

本次只补HTTP兼容细节与文件清单，不改RFC/SPEC字段、数据源、预算、身份/水位/标签或权限语义，不新开Principal/三文档链。Fix仅允许两个原52项文件，无第三源码/测试文件：
- `skills/data/data-pipeline/scripts/btc5m_history/common.py`：仅在既有`http_get`构造允许的Predict官方GET时添加上述固定真实应用User-Agent，覆盖rounds、status-logs及pending详情；Binance请求头行为保持不变。URL白名单、X-API-Key仅既有方式、禁止redirect、401/403立停和其他重试/预算/时钟规则全不变。
- `skills/data/data-pipeline/scripts/btc5m_history/tests/test_extractors.py`：在现有HTTP替身上断言各Predict入口的应用header/原key头，Binance不被改；401/403仍单次失败不重试/不绕过，原断言不删不弱化。

原工程Review3为UA修复前基线。一个窄Developer Fix→fresh Tester Verify→fresh Reviewer Review取得当前候选证据；不重做旧缺口、不改其他50候选。工程阶段纯离线、无真实HTTP/Mongo/凭据/DB写；完整受影响联合回归由Verify绑定最终候选实跑，Review复用完整证据并做小范围独立控制，不机械重复全量。通过后只恢复原P2，P3继续等待原P2；不重建生产图、不复迁库、不加Activation/单源平台或CLI参数。P2新轮报告使用R2后缀保留run3609失败；允许的业务写入仍仅原P2授权。

### 2.5 Audit CLI 双入口兼容窄修（Pascal确认：按照建议推进）

闭合清单重锚：UA-Fix/run3610已完成；原Verify/run3612的UA定向37通过、独立探针22通过保持有效，完整联合1873通过/19失败保留为FAIL。唯一未闭合项UA-R2-01是两个audit脚本按文件启动时导入新增`ud_lock`失败，不是19个业务缺陷，也不是新的Predict故障。主控已实测同解释器/无PYTHONPATH：两个文件入口各exit1，两个模块入口各dry-run exit0；依据主题`audit-cli-entry-assessment.md`及R2报告，Pascal明确批准以下最小修复。不重做已闭合数据缺口或UA头，不改RFC/SPEC业务契约。

本阶段仅允许四条原52候选路径，无第五源码/测试文件：
- `scripts/unified_data/audit_rollout.py`、`scripts/unified_data/audit_smoke.py`：只在文件执行入口用自身`__file__`确定项目根，复用`run_btc5m_history.py:27-34`现有模式，委派到各自canonical包模块的同一`main()`；模块入口正常运行，main只执行一次。不从cwd猜根、不使用ImportError宽泛兜底、不复制业务逻辑。
- `scripts/unified_data/tests/test_audit_rollout.py`、`scripts/unified_data/tests/test_audit_smoke.py`：保留所有原文件入口断言，补模块入口与相同argv的dry-run/参数错误/缺凭据退出码控制；文件入口从其他cwd仍能定位自身项目，未安装的模块入口仅承诺项目cwd。可按需要最小扩展既有私有测试helper，不删除/跳过19项失败或仅改测法求绿。

仅本进程对经自身文件定位的可信项目根作必要入口引导，不修改环境/用户PYTHONPATH、安装路径/依赖或Hermes安全配置。原业务函数、namespace/身份/DDL/DML/脱敏/锁路径与语义/CLI参数和退出码全不变，`--apply`仍需显式授权。本次实际执行只离线测试/默认dry-run，不真实运行audit apply/verify、不读真实凭据/HTTP/Mongo。生产P2授权不向本卡延伸。

§2/§2.1–2.4均保历史归属；本次从UA-Fix最终52身份冻结四文件修前字节，其余48及UA两文件不变。若既有`test_audit_rollout.py`因必要入口矩阵从当前1126行超过1200，职责仅此CLI的入口/退出码与原审计单测，增长只能来自本阶段参数化覆盖；新增其他业务场景前拆分CLI场景与fixture，独立Review核验增长和职责，不为降行数重构。

只新增一个Developer窄Fix；原`t_8eb24bd2`绑定该Fix后作为R3 fresh独立Verify，修复完成前保持blocked，R1/R2报告/拒绝/反例不覆盖；原未运行`t_d8ce90b7`继续复用并审UA与本次入口累计差分，不拿旧PASS替新候选。完整最终联合由R3实跑一次，Review核字节及完整证据并做少量独立控制。P1迁库已签收不重跑；原P2/P3不重建，不新加Activation/平台。验收通过才恢复原P2。

### 2.6 Predict 官方扁平响应到内部 envelope 的集中适配（Pascal同意）

闭合清单重锚：§2.4 UA与§2.5 audit入口已由run3614 Verify及run3615 Review通过，1904测试保其已测范围事实；P1迁库已签收，均不重做。P2/run3616真实HTTP成功但轮次0入库，唯一新缺口是外部`data[]`每项为扁平category，现有采集透传而扫描/转换/raw再读期待`category+markets`内部envelope。主控用checksum可核的官方100条及匹配status原文离线复现：现实现ORDER_REVERSAL/INVALID_IDENTITY；按已有pending封装作诊断对照100条可转换。证据见主题`predict-response-shape-triage.md`及`evidence/correction/p2/r2/offline-shape-replay.json`。原页降序正常，不归咎官方乱序；测试未覆盖真实wire到内部边界是本方验收遗漏，不拿旧全绿宣称生产可用。

本次仅以下五条原52候选路径，无第六源码/测试文件：
- `skills/data/data-pipeline/scripts/btc5m_history/extractors.py`：在既有Predict枚举与按ID详情边界复用一个薄封装，将官方category/markets组织为原内部envelope；保已有canonical envelope兼容，校验有歧义/坏结构，不静默丢字段或修身份。原HTTP/认证/预算/UA/归档字节和checksum、status引用全不变。
- `skills/data/data-pipeline/scripts/btc5m_history/runner.py`：只让`read_round_page`与`reconcile_round_raw`的官方原始页再解码/列表身份匹配复用同一薄封装，保扫描/day/transformer等内部消费者契约不分叉。首采、日切片、重启/续跑、pending补齐及只读verify使用同一结构解释，不能仅改scan_rounds报错处。
- `skills/data/data-pipeline/scripts/btc5m_history/tests/test_extractors.py`、`skills/data/data-pipeline/scripts/btc5m_history/tests/test_runner.py`、`tests/data/test_yquant_data_history_integration.py`：补真实官方原文或保结构/类型/身份的最小摘录回归，覆盖Extractor→scan/day→原ETVL→假库load→raw再读/只读verify、重启续跑/补齐；旧fixture作为内部canonical样例保留，不重写为伪官方返回，不skip或弱化原断言。可在既有测试文件内固化最小公开样本及来源hash，持久回归不依赖本地ignored原始档案存在；完整100条原文另用于本轮可追溯离线回放。

原始JSON响应/归档不可改，外部wire结构只在采集/raw读取边界转换，不新增DTO/schema/集合/CLI/版本库/数据平台/依赖。排序/身份/唯一键/Decimal/微秒/原始引用/官方标签及水位不放松；真乱序、错身份、重复冲突、坏raw/status仍拒绝。官方样本在目标主窗之外，不计92日覆盖；只有100条不构成完整日，不能为了凑288伪造官方时间/记录或标complete。局部真实页应证明进度正确且不越缺口，原完整日合成fixture继续清楚标记为测试用途。

工程只离线原文回放和假库，不发新HTTP、不访问真实Mongo/凭据、不写生产数据、不改历史raw。先保修前RED，再做五文件最小Fix；一个fresh Verify合验最终候选（真实原页整链+严格负例+完整联合一次），一个fresh Review绑定相同候选与日志并做必要独立控制。已完成的旧Verify/Review不改判或重新作为新候选PASS；原P2/P3复用，新Review作为P2新增真实前置，保run3609/run3616失败及两完整价格日；不新建Activation，不重复迁库/已完整下载。

runner当前1432行，职责仍两固定源日进度、raw与pending续接；增长仅本次共享封装调用，不添调度/源/平台。独立Review核职责与增长，未来新增源/调度能力或非本清单的实质扩张前按源日处理/进度边界拆分；不为减行数做无关重构。其他文件按实际G3阈值检查，避免复制大段fixture。

### 2.7 SHAPE-V-01：官方结算终态的 Loader 窄修（Pascal同意）

闭合重锚：Shape-Fix/run3617五文件适配已完成；Shape-Verify/run3618独立验证官方100条原文ETVL/raw/重启/只读及分页成立，联合1934通过均保留各自范围事实。唯一未闭合major为SHAPE-V-01：`loader.py:370–374`将category/market/trading三个状态变化一律要求新值RESOLVED，误拒已有pending记录向官方`RESOLVED/RESOLVED/CLOSED`终态补齐。反例为`evidence/correction/shape-verify/test_independent_wire.py`，其临时OPEN前态明确为合成，最终字段来自checksum可核官方原文；未修改官方CLOSED求绿。原Verify FAIL与所有原生日志不可覆盖，本阶段是已有契约实现纠错，不新增DTO/状态模型/RFC或SPEC业务语义。

仅允许两个原52候选路径，无第三源码/测试路径：
- `skills/data/data-pipeline/scripts/btc5m_history/loader.py`：仅在`HistoryBatchLoader._may_update`区分结算与交易状态字段，本次新增接受目标为官方`trading_status=CLOSED`，仍须新`settlement_state=resolved`及原管道官方终态证据/身份/价格校验；category_status/market_status变化仍只接受RESOLVED。保既有trading_status=RESOLVED的canonical内部测试兼容，不称其官方真实状态、不改原fixture。不能接受任意状态或pending时无依据的状态变化，已resolved不可覆盖、已接受价格/结果/身份不变、null单调补齐/原CAS/raw与观察时间规则均保留。
- `skills/data/data-pipeline/scripts/btc5m_history/tests/test_loader.py`：固化真实CLOSED终态的Loader更新/读回与负例，保原测试与canonical工厂。category/market误写CLOSED、未知交易状态、无resolved的状态改变、终态回退/冲突、价格或身份改动仍拒绝；保legacy正例及同事实幂等/观察时间。不得修改转换器或旧Verify反例来适配错误实现。

其他50候选（包含§2.6全部五路径）只读保留；原始两官方归档不改。集中Fix后复用blocked Shape-Verify `t_217fca4c`为R2，先挂Fix真实父边，Fix完成且主控核验后才解除；R2使用新报告/证据/交接，不覆盖run3618。重跑原独立九项原字节、当前Loader定向及最终完整联合一次，必须完成原失败的pending→部分补价→官方CLOSED结算→raw再读/重启/只读链，原通过矩阵不退化。原未运行Shape-Review `t_c3a6665e`继续复用，绑定R2当前候选与§2.6+2.7累计七路径归属；复用原P2/P3，不新增Activation或生产图。

本阶段仅离线HTTP/假库，无真实API/Mongo/凭据/生产写/服务/调度/交易/Git写。P1迁库和UA/audit不重做；原P2仍blocked，只有R2 PASS与既有Review APPROVE/open=0/0/0且主控核验后才恢复。旧1934全绿不可抵销新反例失败，也不代表真实92日/daily通过。

### 2.8 续扫检查点与官方Flat最小修复：本轮Light Flow

Pascal明确批准修复、去掉本轮独立Review，并要求同步Flat/50-50相关文档。RFC §7、SPEC §8是本轮新增决策源；此前§2.6/2.7及旧候选hash是历史身份，不能误要求三契约仍等于旧hash。原P2/P3复用，新增Review t_8989e32b因用户缩减流程归档、非审查PASS（解绑期间短暂claim的run3629已随归档回收，不计已完成Review）；复用Implement t_a7d9b3f8 → Verify t_c84735d4 → 主控收尾，本轮不重新开Principal/Design/Review卡。此处是具体契约同步，不改全局流水线规则。

主控诊断与原文来源：`data/reports/2026-11-11-yquant-data-history/predict-scan-checkpoint-triage.md`。活动scan冻结窗与本次计划日错位，日收尾丢掉新manifest引用，stream却已更新cursor；闭合270页原文仍在。修复必须维持cursor/bounds/manifest关联、固定窗复核、预算中断恢复、闭合后后续日能前进；坏hash/缺失/错窗fail-closed，禁止扫描全部raw猜恢复或静默清cursor。旧day引用格式可兼容。不得将计划窗外日虚报complete或让水位越gap。

唯一源码/测试allowlist为既有六文件，不新建模块：
- `skills/data/data-pipeline/scripts/btc5m_history/runner.py`：上述扫描续接；必要时对官方已验证DRAW复核兼容，不加调度层。
- `skills/data/data-pipeline/scripts/btc5m_history/tests/test_runner.py`：同窗/换日/闭合/重启/预算/错引用，DRAW可被完整日检查接受而真正冲突仍阻塞。
- `skills/data/data-pipeline/scripts/btc5m_history/transforms.py`：仅SPEC §8的官方Flat联合证据→现有DRAW，保原状态/唯一方向/身份/最终日志/Decimal底线。
- `skills/data/data-pipeline/scripts/btc5m_history/tests/test_transforms.py`：5条真实样本自包含摘录及强负例；不删多WON非等价/缺规则/缺终态等拒绝底线。
- `skills/data/data-pipeline/scripts/btc5m_history/loader.py`：仅SPEC §8限定的未标注conflict→有完备官方证据的DRAW可修复性；不放开任意conflict/终态覆盖，保CAS/readback/raw_history/观察时间。
- `skills/data/data-pipeline/scripts/btc5m_history/tests/test_loader.py`：假库下上述窄更新、重启重放幂等、恶意变更拒绝与既有保护。

文档仅本RFC/SPEC/Design三份由主控同步；developer不修改它们。实现先RED后GREEN，独立Verify跑整个btc5m_history/tests模块并验证相关CLI/raw重放兼容；不重跑全仓1974。旧52候选身份排除本轮明确六文件，三契约绑定本轮同步后的hash；保护证据仍保持原字节。本轮验收明确区分合法DRAW与真正冲突，不能为守旧测试而继续拒绝合法平局，也不能放宽非等价多赢家。

runner已在1201–2400行受控范围，本次局部bugfix不扩源/调度/职责，不进行大拆分；原G3职责与未来扩张拆分触发仍有效。本轮按用户例外由独立Verify与主控收尾核对职责/净增长，不追加Review。

工程执行零HTTP/真实MongoDB/凭据/生产raw改写/旧5条更正/检查点修复/服务/cron/交易/Git写。生产纠正单列精确namespace/记录/前提与读回，不能自动激活；不开发新的修复CLI/迁移平台。

### 2.9 Step1/2集中恢复修复（2026-11-12，V1.2增量）

源为RFC §8、SPEC §9及Pascal“请按照你的建议，先完成1和2”。复用已完成Flat/检查点/HTTP修复，不按旧52路径重建。原P2 triage仅行政防重派、原P3仍等待；本轮Light Implement→独立Verify→主控补齐，不开独立Review/新Principal/Activation。三契约由主控同步在代码派卡前，worker只读；每轮候选身份按当前实际字节绑定，不误拿旧95/401/1974作为新PASS。

仅9个既有源码/测试路径可写：run_btc5m_history.py；btc5m_history/runner.py、common.py；templates/yquant-data-btc5m-history-daily.sh；btc5m_history/tests/test_cli.py、test_runner.py、test_extractors.py、test_loader.py（上述相对skills/data/data-pipeline/scripts/）；tests/data/test_yquant_data_history_integration.py。不得新增源模块/测试文件，不修改loader.py生产逻辑、transformer、reader、Rust或其他共享dirty。

用现有plan_days/write_day/recheck_pending/scan_rounds/_advance_stream及CLI实现SPEC §9：小型错误分类纯helper、旧暂态due的只读effective解释、精确retry-day及显式restart-scan，不引入新调度层。recheck_attempts只操作元数据、由runner写原记录，保业务hash及旧事实时钟；默认输入按0兼容。重扫仅明确原冻结窗、保原档与旧引用，不能猜失效错误或改变授权窗。默认daily plan传存储锚点。_api_key保env优先并可读取env指定私有普通文件，异常仅停Predict通道不饿死Binance；模板不硬编码当前secret路径，也不自装job。summary必须保源错误和真实退出，不用空results伪成功。

RED覆盖旧due一天、准时回查始终一天、日manifest为空伪闭合、枚举水位不动、daily漏无账日、key-file缺/空/不安全、HTTP异常summary留空；GREEN覆盖正常两源及认证/schema/checksum/Flat/身份/partial-bulk守卫。显式retry校验精确dataset/date/窗口/非complete，显式重扫核冻结窗/旧raw保留/正常续传无flag不变。独立Verify绑定最终候选一次合验btc5m_history/tests与原tests/data/test_yquant_data_history_integration.py，少量reader隔离；不重跑全仓1974，不安装Ruff/依赖。

runner1201–2400受控范围的增长只为当前两固定源恢复/报告，本次无新源/调度职责、不做无关拆分；沿§2.8用户例外由独立Verify及主控核职责/增长，不新增Review。超过2400或范围不足需先报告，不能为用满allowlist重构。

工程worker零真实HTTP/Mongo/env/key/生产raw/服务/cron/Git写。独立Verify通过后主控恢复原P2：网络旧日按15分钟策略生效，两个已批准旧Predict日可显式retry-day，一次一apply，预算原样。补齐数据、manifest/日摘要/连续水位后才报告步骤1完成；步骤2只签修复与安全接线，生产daily/P3/正式job仍按后续阶段，不混称通过。执行镜像见本主题correction/step12-recovery-contract.md。

## 3. 保持的数据流和接口

`原合法连接.client → tradingagents → TA-CN 只读`；同 client 的 `yquant-data → local/cache/明确启用audit/HistoryReader/历史loader`。sector 原组件式 authSource 不变，source_db 供行情，ud_db 供 ranking writer/readback；audit 原身份库不跟业务库走。quality 不借迁库自动激活，P3 fake-only/旧R3不重开。
保 `services/storage_composition.py:build_persistent_client` 的纯装配与 client 构造显式注入，不在 import/普通 facade 构造读 env/连接/DDL；历史 reader 不走会写 audit 的 router 路径。已有包级 lazy OCR 导出已修复，`extractors/__init__.py` 不再列重写项。

两固定源经现有 async `DataPipeline.run` 及四基类；每次一 Predict 页≤100 或价格chunk≤5000，空 LoadResult 只代表空批，不是覆盖。保精确字段映射和 SPEC schema v1，不加 provider 能力/通用 ApiExtractor/新引擎。
`RawArchive → transformer/validator → HistoryBatchLoader(自然键比对/受控补齐/bulk/exact readback) → runner日内容核验 → 日摘要/complete → advance_contiguous → 联合min`。同事实 no-op 保观察时间，已接受事实冲突保raw、不覆盖。
索引遵循既定契约，由显式apply在写前初始化/核验（C5-02修复，不能声称旧候选已具备）：`uniq_predict_round(source,series_slug,round_id)`，round范围与pending索引；`uniq_spot_kline_1s(source,market_type,symbol,interval,open_time_us)`；进度 `(kind,dataset,utc_date)` unique。新三集合无TTL，重复apply不重建等价索引，不兼容索引STOP；plan/verify/import不做DDL。
Predict page chain及pending详情/status-log原始引用保留，不将category.id与market.id拼错；正数start/endPrice、最终官方证据及结果才给标签。Binance原字节SHA256/官方CHECKSUM/CRC、12列时间/Decimal直接解析、缺秒不填，均保原实现与正确性断言。

## 4. 迁移的最小修正

主控在 P1 提供有限操作事实：已知入口/责任进程清单、窗口起止、操作者不并发提交 UD 写的确认，使用既有本地迁移摘要的 quiescence 对象记录即可。事实无需独立签名文件/hash/时效令牌；起止时间是观察边界而非“未到期才有效”的授权机制。缺确认不复制，但不索要不可证明的全球writer排除承诺。
该对象固定为 `start_utc/end_utc`（显式UTC观察边界）、`caller_inventory`（已知入口/责任进程条目列表）、`operator_confirmation`（非空操作确认文字）、`no_concurrent_ud_submissions=true`；不要求 `external_writers_excluded/old_handles_drained` 布尔证明或外部reference/sha256。既有plan/content摘要校验只用于防误用/损坏，不是授权签名或时效token。
已知入口：sector Gate2 DDL/Gate3、audit rollout apply/audit_smoke apply；factory 调用者的 materialize/cache put/invalidate、AuditLogger.log、显式 QualitySummary.update（如已用）。记录仍持旧UD句柄的调用由主控安排自然完成/不并发提交，不擅自停服务/kill其他进程。flock不证明未知外部writer不存在。
迁移仍为拿锁→固定五集合/目标现状/有效权限→源前内容与metadata→仅补缺集合/索引及insert→源后/目标逐ID内容和metadata→摘要。非TTL漂移/目标冲突STOP，无删除/覆盖/回写。已有typed canonical BSON摘要/SQLite可原样保留，实际不支持结构才报错，不扩任意结构兼容。
`_require_apply_evidence` 用既有权限列表计算每个具体namespace的缺失actions，向main输出稳定脱敏分类与namespace/action，不打印身份/URI/原异常；不能被main统统吞成 MIGRATION_FAILED。权限不读得则报告不可核，不自动ensure/create/grant用户角色。
TTL仅原audit fetched_at+31536000秒的真实过期子集，不能拿expired条件豁免字段更新。保 `_metadata_matches/index_signature` 的实际options与索引顺序/方向核验，不预实现未来TTL/validator框架。
切换前失败保源和已复制目标；切换后有新增量保其ID/摘要并先修新库，不自动切旧或向旧库补写。P1 完成必须 exact-target 读回，不把log未报错视为成功。

## 5. 两源按日与必要剩余修正

保现有 `plan_days`、`scan_rounds` 绑定窗口/raw页链、`recheck_pending` 按ID到期回查及 `Budget.fork`；只需各源独立预算、一源失败另一源仍有界尝试，不新增轮转/公平协议。pending401/403时记录Predict失败、跳过该源继续Binance；共同DB/namespace错误只停受影响通道，不换凭据。
round日复核按既有查询读取本日内容，同时算实际round数、自然键重复、有效身份、distinct_start_slots、missing_nominal_slots/区间、overlaps/off-grid、resolved/pending/unavailable/conflict。名义网格 D+{0..287}×300秒为参照，不强删额外官方轮次，不凭count=288冒充正确身份；未解释缺槽/重叠记gap或conflict，不能complete/推进水位。
`_finish_round_day` 合并闭合页链与日复核；`_run_verify` 同样拒绝“仅一条resolved+complete检查点”伪完整。报告枚举与最终标签分开；`_run_apply` 将实际conflict映射20、一般pending/gap/backlog映射10，保持完整水位不越gap。
非零warmup时用精确 `start-warmup_seconds` 作为流锚点，规划其所在完整UTC日作为边缘超集；主窗口不变，研究严格裁剪，预热与主窗分母各算。不为warmup改变92日锚点或每日重扫历史。
保必要日/流断点、raw/page/content摘要与只读verify续核；不新增manifest签名/有效期。默认每源7日/HTTP30秒最多3次/Mongo10秒/总1800秒，已有请求与chunk上限不重选。backfill有界反复显式续跑，未齐exit10。

## 6. 稳定窗口研究与保留增强

保 `UnifiedDataClient.read_btc5m_history → Btc5mHistoryReader.read → HistoryWindow` 签名及分离流；`history_input.iter_history_input` 只做薄DTO转换，不碰旧research.py、Rust、盘口/收益模型。SPEC给出的available_at/观察时间及proxy警告继续生效，Decimal主数据不降精度。
默认使用主控/操作者确认的稳定窗口，读取到消费期间不主动安排本任务写入；一次 `_scan` 内容摘要绑定窗口、schema、来源、排序、as_of/模式、观察时间、覆盖。expected_manifest校验仍用业务内容hash；发生已知写入则丢弃稳定样本结论，重新取稳定窗口，不宣称strict PIT/live等价。
候选 `_pages/_assert_states` 反复检查、`HistoryWindow.verify_consumed` 和 `HistoryInputBundle.iter_scheduled/verify_consumed` 可保留，原调用若依赖其API可继续按现状调用。这些不是新增首版验收协议，也不为去门禁强拆代码；本期不再新做严格并发快照/三流确认/通用调度专项测试。来源/标签隔离、as_of过滤、稳定内容可重复仍是底线。

## 7. C3 定向验证与工程交接

以下命令从项目根运行，均是后续 C3/C4 离线验证，本 C1 未执行。沿用已有测试名，不新增编号族；用Fake/mongomock/HTTP替身，不读真实env或连接生产。

```sh
PYTHONPATH=. .venv/bin/python -m pytest scripts/unified_data/tests/test_ud_migration.py -q
PYTHONPATH=. .venv/bin/python -m pytest skills/data/data-pipeline/scripts/btc5m_history/tests/test_cli.py skills/data/data-pipeline/scripts/btc5m_history/tests/test_runner.py -q
PYTHONPATH=. .venv/bin/python -m pytest tests/data/test_yquant_data_history_integration.py -q
```

每项实际差分先跑相应定向用例；每次候选最终只做一次合并回归，不能用旧1750冒充新候选通过：

```sh
PYTHONPATH=. .venv/bin/python -m pytest scripts/unified_data/tests skills/data/data-pipeline/scripts/btc5m_history/tests skills/data/unified_data/tests skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/test_history_input.py tests/data/test_yquant_data_history_integration.py -q
```

仅验证不重写的底线：现有双库/auth/guard、audit exact readback且零用户角色写、checksum/CRC/Decimal/微秒、幂等与pending补齐、partial bulk/进度失败、BUSY无写、稳定读取/as_of/预热/标签分离、wrapper无LLM/外发。增强回归可留，但不能删除上述断言来变绿。
C3交候选hash/实际改动/定向与合并回归结果、未覆盖风险；C4独立验证、C5独立审查，全部open blocker/major/minor闭合再PASS。工程线不做真实Mongo/HTTP/凭据/迁库/采集/调度。

## 8. 工程通过后的执行边界（仅P1/P2/P3/主控）

只执行已审CLI，不在生产卡继续开发。下列是冻结入口形状，C1–C5不执行；P1短窗口事实按§4填入plan摘要，原非破坏授权不重复申请：

```sh
PYTHONPATH=. .venv/bin/python -m scripts.unified_data.migrate_ud_database plan --report-dir data/reports/2026-11-11-yquant-data-history/evidence/correction/p1
PYTHONPATH=. .venv/bin/python -m scripts.unified_data.migrate_ud_database apply --manifest data/reports/2026-11-11-yquant-data-history/evidence/correction/p1/manifest.json --apply
PYTHONPATH=. .venv/bin/python -m scripts.unified_data.migrate_ud_database verify --manifest data/reports/2026-11-11-yquant-data-history/evidence/correction/p1/manifest.json --report-dir data/reports/2026-11-11-yquant-data-history/evidence/correction/p1
PYTHONPATH=. .venv/bin/python skills/data/data-pipeline/scripts/run_btc5m_history.py backfill --start-utc 2026-08-10T00:00:00Z --end-utc 2026-11-10T00:00:00Z --max-days-per-source 1 --apply --report-dir data/reports/2026-11-11-yquant-data-history/evidence/correction/p2/first-day
PYTHONPATH=. .venv/bin/python skills/data/data-pipeline/scripts/run_btc5m_history.py daily --max-days-per-source 7 --wall-seconds 1800 --apply --report-dir data/reports/2026-11-11-yquant-data-history/evidence/correction/p2/daily
PYTHONPATH=. .venv/bin/python skills/data/data-pipeline/scripts/run_btc5m_history.py verify --start-utc 2026-08-10T00:00:00Z --end-utc 2026-11-10T00:00:00Z --report-dir data/reports/2026-11-11-yquant-data-history/evidence/correction/p3
```

首日命令仍绑定全92日锚点，预算1日只测资源/部分进度，不缩目标；后续同backfill命令用每源7日显式续跑，并以不同本地report目录保各次摘要。只读verify预算截断可用既有 `--resume-report <前次summary.json>` 续核；未核日期不得算PASS。P3不写库、不重下已完整数据，读raw重算并对目标内容核验。
P2首日记录ZIP/CHECKSUM字节、有效/无效/缺秒、真实BSON大小、批次数、各环节耗时与RSS、能读到的存储/索引统计；按真实日/行数外推92日容量/时间，缺统计权限明示，不编造SLA、不删旧数据腾空间。官方未发布/结算等待保pending，代码缺陷退最小Fix，不偷偷改已审候选。
主控于P3通过后安装现有仓库模板 `skills/data/data-pipeline/scripts/templates/yquant-data-btc5m-history-daily.sh` 为当前yquant的普通scripts wrapper，固定项目cwd/venv/daily --apply；不复制凭据、不用symlink逃逸，不启服务/第二gateway。唯一job `yquant-data-btc5m-history-daily`，no-agent/script-only，两delivery=local。
实际scheduler上海时区用 `0 11 * * *`，UTC用 `0 3 * * *`；按本机真实支持方式核有效时区/timeout，不改全局配置。创建前查同名，创建/复用后exact ID读回enabled/script/no-agent/local/next_run，上海必须11:00。不声称未来自然tick已发生，WSL漏跑靠下次daily补缺。
工程PASS、迁库PASS、历史价格/轮次/标签覆盖与每日目标分别交付；固定92日未齐不得最终全项目Closeout。权限/环境失败报具体namespace/action或原因，不自动改RBAC/服务/依赖/配置、不加平台/阶段。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.2 | 2026-11-12 | §2.9九路径集中恢复修复与Light独立Verify，来源RFC §8/SPEC §9；主控原P2补齐，原P3/cron不提前放行 |
| V1.0 | 2026-11-11 | 原 T2；逐字副本保留于主题 `evidence/rebaseline/DESIGN-03-018-v1.0.md` |
| V1.1 | 2026-11-11 | 复用冻结候选，收窄C3七路径差分；删除旧强制静默/并发/调度平台门禁，保底线与三项独立交付；同日Pascal确认后追加§2.1，仅补C4 F1–F3的两个Fix路径及原卡R2复验；随后同意C5七项封闭清单，追加§2.2的Fix2十二路径及fresh Verify/Review，修正§3索引实现事实，不改RFC/SPEC业务契约；Review2后经Pascal重锚确认追加§2.3，仅剩两项的runner及两既有测试窄修 |