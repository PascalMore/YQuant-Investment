# RFC-06-003: BTC5m phase1 最新模型的99日历史评估与有限优化

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | Draft V1.1，T2吸收Pascal新决策的修订候选；待独立只读Design Gate及主控核验，不是实现、研究完成或Validate PASS |
| 作者 | YQuant Principal / yquantprincipal |
| 创建 / 更新日期 | 2026-11-18，Asia/Shanghai（UTC+08:00） |
| 所属模块 / 工作区 | 06_strategy；/home/pascal/workspace/yquant-investment |
| 来源任务 | T1 t_225c8483仅交付V1.0；T2 t_d02e821a按Pascal 2026-11-18新决策修订V1.1；性能优化已完成 |
| 权威业务输入 | [研究方法提案](../../../data/reports/2026-11-17-btc5m-model-research/research-methodology-proposal.md)，2026-11-17，共91行 |
| 派生SPEC | [SPEC-06-003](../../spec/06_strategy/SPEC-06-003-btc5m-phase1-model-research.md) V1.1 |
| 对应Design | [DESIGN-06-003](../../design/06_strategy/DESIGN-06-003-btc5m-phase1-model-research.md) V1.1；T2独立实体 |
| 依赖契约 | 07-005 phase1正确性；07-001 legacy history；均只读，不整体替代 |
| 流程 | 主控Intake → RFC/SPEC → Design → Implement → 独立Reviewer Validate → 主控Closeout |

## 1. 执行摘要

研究最新版phase1在官方固定strike和真实成交close代理下的概率信息、方向与稳定性；不是缺盘口条件下的历史成交收益回测。复用已签收的读取/共享输入/结果复用及有界退出能力，只补最新phase1的有版本、label-free纯估值接缝与冻结统计实验；允许无改进，不以调出好模型作为成功标准。

本RFC负责研究选择及边界，SPEC负责可执行行为和验收判据，内部类型、逐文件allowlist及命令属于独立Design。V1.1只按Pascal新决策修订本组三文档，其他既有契约只读；文档阶段不读数据库、不拟合、不回测。旧T1的V1.0实体SHA/交接和版本记录保留，不追认为V1.1通过。

## 2. 背景与当前事实

### 2.1 已完成能力、真实缺口与研究执行分开

缩写：P=`skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb`；BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。这两个精确目录仅表示职责定位，不授权任意修改其下文件。

| 分类 | 证据 / 事实 | 本轮处理 |
|---|---|---|
| 已签收性能能力 | t_c4065ffc/run3822，独立R4 PASS；139项及三条真实CLI均native exit0；[report-r4.md](../../../data/reports/2026-11-17-btc5m-research-performance/report-r4.md) | 直接复用，不重做R1–R4/六组计时，不重建性能平台 |
| 性能能力适用域 | legacy history/1、固定floor、多实例同配置控制；预取本次比serial慢 | 主研究默认serial，不承诺99日倍率，不把多实例控制误称异参模型实验 |
| 已存在phase1计算 | BOT/src/bot/arbitrage/phase1.rs已有source key/epoch、20 returns、gap、真实时钟和digital_up/EWMA调用 | 复用实际模型与状态计算，不复制第二份模型 |
| 最新历史接缝缺失 | BOT/src/bot/arbitrage/history.rs:7为btc-arb-history/1，:61仍DecisionCore::new；phase1完整evaluate还要求book | 必须补显式分版的无book纯估值接缝；重编译旧入口不等于最新模型 |
| 真实研究尚未执行 | 99日新协议输入、5秒路径、逐折拟合/评分与新报告 | T3只小窗/pilot；T4先独立验证接线/pilot，再一次全窗研究及独立重算 |

本卡静态核对：主仓main HEAD=523fc1a0cb14f6eb3d7bfcd4122f56d06ee975d7；BOT本地main HEAD=0250eb993958cc2f47e3b6e81e008a59a02b565f且工作树干净。主仓已有P/README.md、history_performance.py及tests/test_history_performance.py三项修改，不是本卡产物，不还原。

R4文件实核SHA256：

- P/history_performance.py：40f1251ed20de8198fed135e41fa78b38fcd5283f73c8fa0f282c4fd483588b3。
- P/tests/test_history_performance.py：f78e6c6516ec55d9bf8efd00882c42bfabd33fb4bd6aefe12805beff71198219。
- P/README.md：f439b9b02ef2a1d1fa4c422b34b7599e64c987ef44b9d4ecf168af72fbf643ae。

源码存在不等于本卡新动态PASS；既有验收按其原候选/输入/适用域复用，新增接线仍需独立验证。

### 2.2 数据与证据局限

来源为canonical Predict.fun官方身份、固定strike、官方结果，以及Binance Vision BTCUSDT现货成交1秒OHLCV，经既有Unified Data facade读取。固定主窗[2026-08-10T00:00:00Z,2026-11-17T00:00:00Z)，既有审计预期99日、28512轮、8553600秒线、171072个六偏移理论槽；本卡不将审计盘点冒称本轮全量消费。

Binance成交close不是实际midpoint，也不是官方Chainlink完整流；event-time-proxy是理论可得时钟，不是真实请求/接收时延或严格PIT。原94日及旧OOS已被查看，新增加日期也不自动未见，统一称“历史时间隔离验证”，不称盲测。

## 3. 目标与非目标

### 3.1 必须目标

1. 用同phase1计算回答H1/H2/H3，保留六时点、所有理论槽、缺失和不适用原因。
2. 明确主采样5秒，t只能使用已闭合的[t-1,t)秒线close；跨轮/日连续、窗前不补造预热，源/epoch/gap与phase1同义。
3. 用训练窗当时已可得标签拟合；冻结M1对M0主要比较、固定扩窗折、共同分母、轮内再轮间等权、成对块bootstrap及明确裁定。
4. 全量真实消费一次共享给三个连续核心；M1只消费M0结果；有界状态、失败partial、身份/消费hash、表格/CSV同源，独立复算。
5. 工程硬门禁、主要研究证据、稳健性诊断三层分开；最终研究分类限“支持继续验证 / 证据不足 / 假说不支持 / 数据工程不合格”。主要结论与诊断冲突分别披露；改善只可支持以后真实盘口/未来独立数据验证，不代表新增市场信息、经济价值已验证、替换M0或部署。
6. 报告先给M0偏差诊断：过度/不足自信、六时点、因果波动层、floor实际影响、日/月损失贡献，再解释M1/M2；仅复用原定样本/桶/分层，共享计算可一次完成，不新增实验或后验挑最佳floor讲故事。

### 3.2 明确不做

不合成盘口/成交/资金曲线，不计算或伪造真实候选/成交数、交易胜率、PnL、年化、Sharpe、MDD、Calmar、换手、IR；这些为N/A并说明缺真实盘口/执行链。不推断min_edge收益最优值，不加OBI、LLM、动量、退出/反手、加仓、半衰期大扫描、在线调参。

不做paper/live、生产DB/schema/index写入、重新采集、服务/cron/systemd/gateway、权限/凭据/交易配置/依赖/安装升级，不更改其他项目或profile。禁止git add/commit/push/reset/stash/clean/checkout；BOT保留本地main，不切SHA或分支。不读取/打印skills/.env全文或秘密。只在后续已批准研究执行中使用既有facade的安全只读连接；当前T2只准本组三份独立文档。

## 4. 核心研究决策

### 4.1 假说与端点

| 假说 | 问题 | 冻结比较 / 解释 |
|---|---|---|
| H1 | M0概率是否包含超越无信息/历史频率的信息，方向是否优于即时方向 | M0与B0、B1共同非DRAW Brier为主要概率证据，logloss辅助；M0与B2只比共同有方向准确率；不能靠高到期命中替代概率证据 |
| H2 | 低复杂度校准是否改善M0 | 唯一主要候选比较为M1−M0验证期Brier差；负值更好；只在训练拟合，验证前冻结 |
| H3 | floor是否造成波动状态/剩余时间相关的偏差 | M2低/高floor相对M0，按因果波动状态及六时点比较；仅探索，不从两者或分层里选冠军后宣称确认性显著 |

H1方向和概率可结论不同；H1不自动成为H2工程运行前提。H3不承担“必须优化成功”的门槛。SPEC §4.7在结果未见前冻结三层判定：不可削弱的工程正确性；M1−M0八折合并Brier配对差和日块区间的主要证据；7日块/各折/六时点/complete-six/logloss/ECE/日贡献等诊断。诊断不再组成自动采纳的复合AND筛选器，反向风险必须显式保留，不能靠重分类隐藏。

### 4.2 候选与复杂度

- M0：phase1原模型，half-life=300秒、floor=0.00005、20个有效returns预热、主更新5秒。
- B0：概率0.5；B1：每折训练窗当时已知的非DRAW官方轮次Up频率，一轮一次计数，验证冻结；B2：sign(S−K)，平价abstain，仅方向。
- M1：M0的单一两参数Platt映射，不增加时点/波动特征。斜率非负，固定identity中心L2正则λ=0.001，不搜索正则；训练目标为轮内/轮间等权的二元logloss加正则，外部主要评价仍为验证Brier。固定正则消除本轮内部择参需求；禁止偷用验证集选择正则或算法版本。
- M2：floor只取0.000025、0.00005、0.0001，中值复用M0，不重复第四个核心。两个探索核心与M0共享同一有序输入，各自独立连续状态；M1为结果变换而非第四个Rust模型。

拟合单类/空样本/不收敛必须明确N/A，不退回identity/M0冒称已拟合；具体行为见SPEC。1秒更新只能显式独立采样敏感性，不默换主口径，不默认额外全窗扫描；未做时如实NOT_EXECUTED，不声称采样稳健。

### 4.3 时间、as-of与纯估值

本轮最终标签/源快照截止A固定为2026-11-17T15:00:00Z，沿用R4已使用的as-of作清晰可比锚点；它不是本卡已验证全窗完整性的声明。所有pilot/全窗均用A，不能因后续执行日期、晚到标签或缺口而自动移动。

每折训练截止C使用训练预测t<C、该轮ends_at≤C、label_available_at≤C且≤A的非DRAW样本；恰在C可得可用，但C后标签绝不因最终A已知而提前拿来训练。全窗评估只事后配对A前合法结果。身份/strike可得性则逐决策t核验，与标签独立。

新历史协议只接受价格观察和固定strike估值请求，不接受end_price/outcome/resolved_at/label、book、fee、订单或结果反馈。预测source归Binance/BTCUSDT，实际数据血缘另记binance-vision/trade_close/event-time-proxy；不得把逻辑代理clock写成07-005真实获取clock。保留phase1源epoch/预热/gap和概率函数，绕开而非满足完整交易gate，不造假book。

### 4.4 扩窗验证与末日诊断

训练从固定起点累计42日起步，随后7日验证；每折训练扩展7日，共8折。首折验证起点2026-09-21T00:00:00Z，验证总段至2026-11-16T00:00:00Z排他；边界的递推公式见SPEC，无随机拆样本。

2026-11-16单日单列最新诊断，使用该日开始前已知训练标签重新冻结M1/B1，不纳入八折主要端点/区间，不因末日结果改变候选。全99日可给M0/B0描述表；M1/B1在首个合法训练截止前为N/A，而非回填未来拟合值。

### 4.5 统计与裁定

非DRAW二元Brier主要、logloss辅助（仅评分clip至[1e-12,1−1e-12]）；DRAW不训练、不计二元/方向分母，另按Up兑付0.5给含DRAW兑付MSE，不能称三分类概率或M1的DRAW校准。

每个比较在共同合法槽内先轮内等权，再轮次等权，保留缺槽/零分母；另给六时点与六槽完整轮次敏感性。配对UTC日块bootstrap1000次/seed42、共享模型和时点索引，另给7日连续块敏感性；不把时点数当独立交易数。固定校准10桶、日/月与因果波动层、floor占比及每折参数；价格相对strike差包含轮内移动，不能冒称同刻跨源纯基差。

数值对拍容差与比较近零用epsilon只服务工程/数值判断，不是经济最小改善阈值。主要端点仍为八折C10合并Brier配对差及日块95%区间；工程合格且主要证据支持改善时只分类“支持继续验证”，诊断冲突另列并限制下一步解释，绝不自动替换M0。主要证据不确定/缺折或拟合N/A为证据不足；可靠劣化或容差内逐槽等同且无边际价值为该冻结候选假说不支持。具体唯一映射见SPEC §4.7。

概率校准、方向信息与可交易价值必须分开。M1是M0的非减Platt映射，可能调整0.5分类边界，但不引入新的市场特征；评分改善不能称新增市场信息。效应大小及区间、双参数/拟合与维护成本、trade close与midpoint不可识别的代理误差、经济价值未验证必须单列。没有可靠经济最小改善阈值时不虚构一个；即使统计改善，经济意义仍未知。M1无可靠改善保留M0，M2只探索、不选冠军部署；不因结果不佳追加半衰期/OBI/LLM/动量等，用模型复杂度遮掩代理数据局限。报告不能看结果后改主指标/候选/分母/窗口，无改进也是合法交付。

## 5. 系统职责与兼容域

facade提供三个隔离流和manifest；Python薄研究消费者负责因果采样/共享输入、结果标签配对、拟合/统计及同源输出；BOT同DecisionCore/phase1负责源状态、EWMA和估值。独立Reviewer用真实消费者/独立参考与样本重算裁定，不由实现者自签。

| 契约域 | 本轮优先语义 | 不变范围 |
|---|---|---|
| 07-005 | 显式研究装配复用其phase1状态与计算，抽出无book估值能力；研究专用floor三值 | controlled v2、replay/2、净份额EV/费用/30秒交易重验/5与10秒真实获取规则、生产默认参数和授权不变 |
| 07-001 | 新研究分版采用99日/5秒/扩窗/本SPEC统计；不套旧94日1秒/split口径 | history/1及其固定floor校验、旧proxy/replay/1/旧研究和历史证据只读兼容 |
| R4性能编排 | 复用共享/消费校验/失败保全/归属/有界退出机制；异参输出不能再套“所有值必须相等” | 旧同配置控制实验精确比较仍有效，旧rescore可信归档不能自认证成新研究证据 |
| 数据facade | 原签名/字段/顺序/Decimal/manifest/verify_consumed优先只读复用 | 不直连Mongo替代facade，不改schema/索引/摄入，不改source时间以迁就实验 |

不能给现有history/1偷偷放宽floor、给生产phase1增可调参入口，或修改07-005三层文档来追认研究权限。内部最小拆分、协议精确版本拼写、输出物理schema及逐文件allowlist由Design冻结；不得重选本RFC的候选/标签/统计语义。

## 5.bis 持久化与可复现性

只保存本地L0公共历史派生字段和L1工程身份，不存凭据/连接串/环境全文/原私密资料，不新增数据库。唯一最终正文为data/reports/2026-11-18-btc5m-phase1-model-research/report.md；必要样本CSV、各折/校准/日月/分层/参数、日志摘要、manifest/hash、native退出、原始估值和独立重算在该主题evidence/。SPEC定义语义字段，Design定义精确文件名/命令与格式，不写第二状态源。

输出独占创建、归属成功后才可写partial；冲突不改旧字节、不自动换目录。开始/结束身份、source/content/provenance、消费完整性及各核心退出/回收必须记录。失败保留partial、不覆盖/删除/迁移/补成功，无TTL/自动上传/备份/resume；data被Git忽略不等于远程保存。新构建不能覆盖旧证据绑定binary再宣称身份相同，Design必须明确保全边界。

## 6. 执行次序与有界成本

T1仅本RFC/SPEC V1.0，原实体SHA和交接保留；T2 t_d02e821a按Pascal新决策同步修订本组三文档V1.1，并基于真实代码确定窄协议/allowlist、G3、原生命令、现有依赖拟合/统计及pilot预算，不写业务代码或读DB。更新后的三层实体须经预建独立只读Design Gate t_780aa76c与主控核验；既有T3/T4继续blocked，旧T1完成不构成V1.1放行。

T3只实现工具、定向回归、真实小窗独立参考向量和一个真实UTC日pilot；不同时承担99日长计算。T4先独立验证接线/相同pilot，再单次99日共享M0/M2流与离线M1拟合/统计，独立复算样本及主要端点，不默认第二遍全库读取。主控最后Closeout；不创建额外默认阶段或自行解锁下游。

只读执行须有总wall deadline、原生子进程与读取超时、固定并行上限和清理预算；Design依据pilot实测wall、父/子RSS、消费/写盘/verify/统计各段做保守外推并给确切上限。全窗启动前必须可容纳在既有T4五小时卡预算及独立核验/清理余量内；估计不符或pilot超限就停止并报告，不自动加预算/改窗口/切prefetch/减少验收。原提案45–75分钟单基线、2–4小时候选计算只是旧估算，R4单日27.4秒也不是本轮phase1/5秒实测，不作为完成承诺。一次成功全窗后复算只读已落样本，无证据缺口不重跑99日。

## 7. 风险、降级与拒绝恢复

| 风险 | 处理 |
|---|---|
| close代理/Chainlink差异、历史先验暴露 | 显式来源和event-time-proxy；历史时间隔离不冒称盲测/真实延迟；不推收益 |
| 标签延后、缺流/冲突、候选身份漂移 | 截止C逐折过滤，A不动；坏数据/消费/hash失败不发模型优劣结论；保留理论槽 |
| 小概率、单类/完全分离、优化不收敛 | 固定正则/收敛契约，失败折N/A，不用M0填；证据不足合法 |
| 缺槽/相关性/多重比较/事后选冠军 | 共同分母、轮次权重、共享日块索引和7日敏感性；H3只探索 |
| 全窗耗时/无界对象或未回收读线程 | 三个连续核心、按日流式/磁盘载体、deadline/partial；不能杀的读取如实unreclaimed并继续追踪 |
| 范围膨胀/回归生产 | 只补真实接缝，旧协议/真实交易配置只读兼容；Design精确allowlist与受影响回归 |

安全拒绝停止该动作及依赖分支；可选日志转存被拒可记NOT_EXECUTED/OMITTED继续独立已授权工作；必需验收缺口block，不换工具/包装/解释器/后台/主控代跑被拒动作。普通参数/路径/补丁并发错误按原范围修复，不误当安全拒绝，不安装依赖或削弱断言求绿。

## 8. 备选方案

- 重跑旧history/1并更名：拒绝，模型语义与5秒采样均未接入。
- 用假book穿过evaluate_phase1：拒绝，会把纯估值混入真实交易门控和伪执行证据。
- 在Python复制EWMA/概率公式：拒绝生产计算双源；仅允许独立验收参考，不参与主结果生成。
- 四个模型各读全库、重新做性能矩阵：拒绝，M1可复用M0、M2中值就是M0，已有性能能力不重做。
- 结果不佳再扩大参数或择正则：拒绝；固定低复杂度候选，无改进可直接交付。

## 9. 验收与交接

业务验收以SPEC A-001–A-024为准：最新核心真实接线、因果5秒、源epoch/gap/预热、三候选共享/有界状态、每折标签过滤、拟合失败、共同分母/统计、消费/来源/身份/退出/归属、独立向量与同源结果。数值容差与研究裁定均在SPEC冻结，不能以测试数量替代反例或以收益作为工程门槛。

T1验收仅：两独立文件互引、提案§1–8完整覆盖、与07-005/旧history兼容边界、无业务未决项；精确路径静态空白检查及SHA256。未执行任何数据读取/模型/业务测试；不宣称实现PASS。

## 10. 开放问题与Design交接

开放业务问题：无。A、候选、折、正则、时序、分母、失败语义及判据由本RFC/SPEC固定。真实数据在A是否完整、phase1 pilot成本、独立数值对拍是后续必须实际验证的条件，不冒称已通过，也不由实现者猜值。

上述内部事项由对应Design V1.1冻结：精确wire/纯估值复用、逐文件allowlist/G3、现有依赖、CLI/native退出、资源/pilot外推、产物schema和旧binary保全。独立Design Gate及主控未核准不得实现；不授权实现者自由扩目录、重选研究判据或提高预算。

## 11. 参考资料与追溯

- 原提案§1–2 → 本RFC§2–3与SPEC§2/4.1；§3–5 → 本RFC§4及SPEC§4.2–4.7；§6 → 本RFC§5–6与SPEC§5–7；§7 → SPEC统计/验收/产物；§8 → 本RFC§6与Design后续实测预算。
- [SPEC-07-005](../../spec/07_trading/SPEC-07-005-btc5m-phase1-correctness.md)、[RFC-07-005](../../rfc/07_trading/RFC-07-005-btc5m-phase1-correctness.md)、[DESIGN-07-005](../../design/07_trading/DESIGN-07-005-btc5m-phase1-correctness.md)：只读phase1边界。
- [SPEC-07-001](../../spec/07_trading/SPEC-07-001-predictfun-btc5m.md) §16、[RFC-07-001](../../rfc/07_trading/RFC-07-001-predictfun-btc5m.md)、[DESIGN-07-001](../../design/07_trading/DESIGN-07-001-predictfun-btc5m.md)：旧history因果/分母/兼容性，不把旧阶段状态当本轮待办。
- P/README.md、spec.md、history_input.py；BOT/history.rs、phase1.rs、service/spot.rs；Unified Data history_reader.py的可得时间与消费契约。本卡只静态读取。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-11-18 | 将原提案冻结为99日研究选择与边界，区分R4已完成/最新接缝/研究执行；不实施、不运行、不改旧三文档 |
| V1.1 | 2026-11-18 | Pascal新决策：M0诊断先行、校准/方向/交易价值分离、工程/主要证据/稳健诊断三层与四分类同步，移除旧复合采纳筛选；固定实验/工程硬门禁不变；T2修订候选待独立Gate，原V1.0交接不追认 |
