# SPEC-06-003: BTC5m phase1 最新模型99日研究行为契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | Draft V1.1，T2按Pascal新决策修订候选，待独立只读Design Gate与主控核验；不是实现/研究或Validate PASS |
| 作者 | YQuant Principal / yquantprincipal |
| 创建 / 最后更新 | 2026-11-18，Asia/Shanghai（UTC+08:00） |
| 来源RFC | [RFC-06-003](../../rfc/06_strategy/RFC-06-003-btc5m-phase1-model-research.md) V1.1 |
| 模块 / 工作区 | 06_strategy；/home/pascal/workspace/yquant-investment |
| 来源任务 | T1 t_225c8483仅交付V1.0；T2 t_d02e821a吸收Pascal 2026-11-18新决策修订V1.1 |
| 适配角色 | Principal Design；Developer Implement；独立Reviewer Validate；主控Gate/Closeout |
| 对应Design | [DESIGN-06-003](../../design/06_strategy/DESIGN-06-003-btc5m-phase1-model-research.md) V1.1；独立实体，待t_780aa76c Gate |

## 1. 需求摘要

经既有facade只读canonical官方轮次/strike/标签和Binance Vision成交1秒线，以5秒因果更新同phase1模型，在固定六时点估值。分析/报告先给全99日M0偏差诊断，再解释八个扩窗验证折的冻结M1/B1和有限M2，末日单列；共享计算无需人为重复读取。标签不得进入Rust估值输入，训练也只能使用训练截止当时可得标签。工程硬门禁、八折合并M1−M0 Brier及日块区间主要证据、稳健性诊断三层分开；评分改善不等于新增方向信息或可交易价值，不要求候选获胜，不生成无盘口收益。

## 2. 范围与职责边界

### 2.1 必须行为与现有能力

P=`skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb`，BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`。

- 已完成：R4 t_c4065ffc/run3822的legacy history/1固定配置性能/消费/退出/来源证据能力；RFC §2所列三个文件SHA本卡已核一致。不重做原矩阵或六组计时，serial为默认。
- 真缺口：BOT/history.rs仍创建legacy core，完整phase1评估要求book；须显式新版本研究纯估值接缝，共享真实phase1状态/概率计算，不复制模型、不伪造book。
- 本轮执行：T3工具、真实小窗与单日pilot；T4先独立验接线/pilot，再一次全99日共享流、M1离线拟合/统计、独立重算和最终报告。完整99日不在T3执行，不默认T4再读第二遍全库。
- Design必须在P与BOT现有职责中冻结逐文件allowlist/精确新增路径/G3、协议wire、现有依赖及固定命令；本SPEC不是任意目录修改许可。公共facade优先只读，旧性能入口输出路径限制不得靠软链/换路径绕过，归本研究主题的最小合法接缝由Design明确。

### 2.2 不做与兼容性

不做合成book/fee/成交/资金曲线、真实或paper交易、生产DB/schema/index写、重新采集、OBI/LLM/动量/退出反手/大扫参、依赖升级/安装、服务/调度/gateway/权限/凭据或生产交易配置改动、外发、其他项目/profile改动。禁git add/commit/push/reset/stash/clean/checkout和BOT切分支/SHA。

07-005 controlled/replay、净份额EV、真实获取/交易门槛与运行权限不变；仅显式研究装配复用其纯状态/计算。旧history/1、replay/1、proxy及旧研究原参数/校验/证据不变，尤其不得放宽history/1的floor校验。研究三floor不成为生产可调参数。旧rescore可信清单只认证原归档，不能用新文件自算hash冒充可信历史。

T1历史仅写本SPEC及对应RFC V1.0；当前T2获准同步本组三文档V1.1。07-001/005三层契约、模板、目录README、角色文件、源码/测试/报告仍只读，不读DB、不拟合/回测。不读取/打印skills/.env全文、秘密或私钥；后续业务数据只经已批准facade安全只读连接。

## 3. 功能规格

| 编号 | 必须行为 | 可观察结果 / 失败边界 |
|---|---|---|
| F-001 | 冻结窗口/A/版本/数据及实验矩阵 | 身份和参数在业务读取/子进程前固定；不自动随日增长 |
| F-002 | 严格label-free因果估值 | 只消费已闭合的5秒网格抽样价格及已可得官方身份/strike；无book也能纯估值，绝不输出候选/成交 |
| F-003 | 连续phase1源状态 | key/epoch、20returns、长gap及无效clock同义；正常跨轮/日不清状态 |
| F-004 | 三候选共享有界流 | M0/M2低/M2高同一顺序/输入身份，各自连续状态；中值就是M0；任一核失败整批不完整 |
| F-005 | 按折当时标签拟合 | B1与M1只用截止C已知的官方非DRAW标签；参数在验证前冻结，无验证反馈 |
| F-006 | 冻结统计和共同分母 | 所有理论槽保留、轮内再轮间等权、二元/DRAW/方向独立、共享块索引 |
| F-007 | 失败保全与可复现 | 完整消费/hash、首尾身份、exclusive-create归属、native退出/清理/partial；失败不发布完成 |
| F-008 | 独立验收、三层判定与合法负结论 | 真实消费者、独立数值及主要指标复算；M0诊断先行，主证据与诊断冲突分列，无改善仍可工程合格，四类研究结论不越界 |

## 4. 数据与接口契约

本节冻结业务字段、约束及失败结果，不预定内部struct/函数签名、模块提取、CLI拼写或物理CSV布局；这些须在T2 Design明确。标“逻辑字段”的名字可作载体映射，但语义不得丢失，Design须逐一给出落点。

### 4.1 固定数据身份、as-of与可得性

| 项 | 固定值 / 要求 |
|---|---|
| 主窗 | [2026-08-10T00:00:00Z,2026-11-17T00:00:00Z)；UTC半开 |
| 最终as-of A | 2026-11-17T15:00:00Z；所有pilot/全窗同一A，最终读/评分截止，不是逐折训练截止 |
| 审计预期 | 99完整UTC日、28512官方轮次记录、8553600根1秒OHLCV、每模型171072个理论评分槽；实际执行独立核对 |
| 数据唯一入口 | 现有UnifiedDataClient.read_btc5m_history及P/history_input.py薄适配；facade签名/Decimal/manifest/verify_consumed不变 |
| 来源 | Predict.fun canonical官方身份/固定strike/结果；Binance Vision BTCUSDT spot、1s trade OHLCV |
| availability_mode | event-time-proxy，warmup_seconds=0；不得冒称observed或严格PIT |
| 身份可得性 | 按facade：proxy使用已存在published_at，否则其既有保守observed后备；不能补starts_at作为未知身份发布时间 |
| strike可得性 | 按facade proxy为官方starts_at；固定官方start_price，不用spot重设 |
| 秒线可得性 | 按facade的close_exclusive；只有close_exclusive≤t且该行≤A才可用 |
| 标签可得性 | 以facade标签available_at为准；当前proxy规则为max(ends_at,resolved_at)，resolved_at缺失无合法标签；不简化成ends_at |
| 标签内容 | 只接受canonical合法UP/DOWN/DRAW；end_price不替代official_outcome；冲突/争议/pending不造标签 |

训练截止C与A是两重约束：训练预测t<C、round.ends_at≤C、label_available_at≤C、label_available_at≤A；全部必须成立。恰在C已可得允许；C后即便A前已知也不能用于该折。训练中后来的折可吸纳此前变为可得的合法标签。官方身份/strike在每个估值t分别要求available_at≤t，A再晚也不得预用。

三流features/metadata/labels必须逐日完整消费，核原manifest、content/provenance、coverage/gap/pending/conflicts，最后verify_consumed。不得把构造bundle、已读count、只有输出hash或自算hash当消费认证。总features包含strike流，不把总features计数误当秒线数。所有来源记录、实际流行数及已消费流身份分开记录。

完整研究数据资格要求：99/99日canonical完整、上述轮次/秒线预期精确相符、无source冲突/缺口/未决标签或未完成流、verify_consumed及首尾身份通过。否则保留可验证的描述性partial及缺口，但本轮总分类为“数据工程不合格”，不能缩窗、补0、插值、改A、漏掉日或发布模型优劣。模型开头WARMUP不是源缺失，不破坏数据完整资格。若未来另行批准接受缺口，须新修订，不能在本轮悄改规则。

### 4.2 5秒更新、评分时刻与来源epoch

1. 更新网格是UTC epoch的5秒倍点t，取主窗内bar_open对应的[t−1秒,t)闭合close；仅发送t∈(start,end]的网格观察。t=start没有窗前bar，不制造首价；t=end可消费最后一根合法bar用于完整性，但无窗口外评分。非网格秒线仍必须读/验证/hash，不更新主EWMA，不能把“1秒输入、每5秒输出”冒称5秒更新。
2. 每轮r六个评分时刻为starts_at+(30,60,120,180,240,270)秒；同刻顺序为已可得身份/strike → 当前闭合spot更新 → 估值。T=ends_at−t精确秒差；270秒偏移剩余30秒合法，不固定成300。窗口按轮starts_at归属，不新增窗口外轮；一槽一记录，不以当时模型是否已暖决定是否建槽。
3. 若当前[t−1,t)bar缺失，不用其他秒线或上一网格close替代该时刻S：该槽MISSING_SPOT；本次不更新。下一有效观察按实际相邻网格有效时间差dt更新，短gap≤300秒沿phase1可形成一个return，而不是补齐多个returns；gap>300秒新epoch，当前价只作首价。缺源数据仍导致§4.1数据资格失败，不能靠这些槽状态把完整性改成通过。
4. source key=(BTCUSDT,Binance,BTCUSDT)表示计算来源；另必记source_dataset=binance-vision、price_kind=trade_close、clock_basis=event_time_proxy。该代理不伪称真实Binance midpoint/在线PRIMARY获取。逻辑proxy_observation_at=t、logical_elapsed=t−start可驱动原phase1状态；实际request_at/received_at未知，不把逻辑相等时刻宣传成真实请求/接收。不向07-005 controlled v2注入伪acquisition字段；T2须明确研究clock与内部既有clock的显式适配和标识。
5. 保留phase1每symbol一个活跃epoch：首个有效价epoch1/FIRST_SAMPLE，samples=0；每次换key均SOURCE_SWITCH，即使回切原源也重新预热；同key保守时间gap>300秒LONG_GAP，等号不断；坏clock按CLOCK_INVALID清当前vol、丢观测、新epoch；无效价不计return。生产observe_phase1的实际检查顺序/计算复用，不新增第二套近似状态机。真实本窗不注入Coinbase或Chainlink；换源/clock反例只在隔离fixture验证。
6. 20个有效returns后才允许sigma/p_up；首价不是return，floor不免预热。正常跨轮/跨UTC日不重置、不中断core进程；不以每折重新冷启动，验证期仅按新价格无监督更新EWMA。不得读未来价格或标签调状态，不补造窗前预热。
7. 新纯估值必须与phase1交易路径共享EwmaVol/digital_up及源状态实际计算。无book/fee/资金/交易clock时依然可给估值；不把交易路径MISSING_INPUT当“无模型概率”，不造book绕gate，也不声明真实执行可回放。保留原A&S CDF近似，不换精确CDF影响主值。
8. 主路径不做1秒更新。可选1秒采样敏感性须明确独立状态/输入身份/预算，不混入主结果，不默认额外全窗读；没做写NOT_EXECUTED及未测稳健性，不把它当已完成。若另获准做且结论反向，按§4.7列为诊断冲突与限制，不自动改主要证据分类、不更名主结果；本轮不因此新增该实验。

### 4.3 模型、共享输入与有界状态

| 标识 | 参数与输出 | 训练 / 限制 |
|---|---|---|
| M0 | half-life300秒；floor0.00005；20returns；5秒主更新；q=Phi(log(S/K)/(sigma√T)−sigma√T/2) | 使用phase1同函数；全窗可描述；不改公式/生产默认 |
| B0 | 恒定概率0.5，方向为abstain | 仅在与模型共同有合法标签/概率的分母评分，不让它的无条件覆盖替代模型覆盖 |
| B1 | Up轮数/(Up轮数+Down轮数)，可为0或1 | 每个训练窗合格官方轮次一次计数，不因六槽重复或M0缺值改频率；只含截止C已知标签；零分母N/A |
| B2 | sign(S−K)，相等abstain | 仅方向；无概率/Brier/logloss，不把0/1硬方向作概率基准 |
| M1 | sigmoid(a·logit(clip(M0,1e-12,1−1e-12))+b)，单个全时点(a,b)，a≥0 | 只在训练窗拟合§4.5；不是每偏移/每状态各拟一套；原M0值不截断改写 |
| M2-low | floor0.000025，其余同M0 | 独立连续core，探索 |
| M2-high | floor0.0001，其余同M0 | 独立连续core，探索 |

只运行三个原生概率候选M0/M2-low/M2-high，中值不重复；M1由M0落盘样本变换，B0/B1/B2由薄统计生成。价格、身份/strike事件只编码/有序消费一次并广播三core，记录共享输入事件序列hash及每核实际接收计数/hash。异floor的数值可以不同，但slot key、身份、price/time、samples/epoch/reset必须一致；中值与M0按同核心结果精确一致，不套旧R4“所有异参p必须相同”的门禁。

内存随单日/固定候选数量有界，不随99日数百万行情对象或全部轮次HashMap增长。允许单UTC日有界输入缓冲/磁盘暂存和小型日/折统计；core只保留活跃symbol/epoch及当前/必要相邻轮身份，过期轮不无限驻留。不能为每个fold或每日重启core以节省状态，也不默认三候选各自读全库。确切内存/管道/子进程清理上限由Design结合pilot冻结。

### 4.4 扩窗与训练/验证配对

令start=2026-08-10T00:00:00Z，C0=2026-09-21T00:00:00Z。j=0..7：Cj=C0+j×7个UTC日；训练预测区间[start,Cj)，验证区间[Cj,Cj+7日)。所有标签再按§4.1截止Cj过滤，不凭t属于训练期就默认已知。八折验证并集[2026-09-21T00:00:00Z,2026-11-16T00:00:00Z)。每个验证槽只属于一折，汇总按实际轮次权重，不简单平均八折比率。

末日诊断[2026-11-16T00:00:00Z,2026-11-17T00:00:00Z)另以C=2026-11-16T00:00:00Z冻结训练M1/B1，不混进主要八折或用于更改候选。首个训练截止前的M1/B1为NOT_APPLICABLE，不用最终拟合值补回全99日。M2不拟合、不由后验最佳floor选择该折参数。

已知94日、旧OOS和部分末日观察造成研究者先验暴露；报告统一标历史时间隔离验证而非盲测。未来确认性样本/真实盘口验证若建议，只是后续方向，不自动开启服务或安排长期运行。

### 4.5 M1拟合行为与失败

对每个训练截止C，从M0合法概率且官方非DRAW、满足标签截止的槽取样。训练每轮r有mr个此类槽，轮内每槽权重1/mr，再使每个有效轮总权重相同、全体权重和为1。DRAW不当0.5训练，六槽不当六个独立轮。

训练目标J(a,b)=加权二元logloss(sigmoid(a·logitclip(p0)+b),y)+λ/2·[(a−1)^2+b^2]，固定λ=0.001，a≥0，b有限。拟合logloss应采用稳定logistic表达，不把评分用clip改成平坦训练目标。固定正则是本轮预声明选择，selection_mode=FIXED；无网格/内部择参，因此无需再划分内验证。未来如改为择正则/加特征必须先修订契约，只能在训练内部更早/更晚时间切分，绝不能用外部八折验证标签。

每折必须保存train_cutoff、预测范围、实际最晚label_available_at、训练唯一轮数/槽数/UP/DOWN/DRAW排除数/因可得性排除数、λ、a/b、目标值、优化器版本/收敛条件、迭代次数/状态。接受条件：有限可行解、a≥0、投影梯度无穷范数≤1e-8，最多500次迭代；不为收敛增加迭代/降精度或根据验证结果重试。

| 情况 | 拟合/评分行为 | 运行和研究解释 |
|---|---|---|
| 无训练概率样本或无合法二元标签 | FIT_EMPTY；a/b/p1=null | 该折M1 N/A，保留所有理论槽/其他模型结果；H2证据不足 |
| 训练只UP或只DOWN | FIT_SINGLE_CLASS；不强行拟合 | 同上；B1若自身频率分母非零仍可为0或1 |
| 有两类但500次内未达条件、参数/目标非有限或不可行 | FIT_NOT_CONVERGED；不输出最后迭代冒充合法p1 | 同上，保留失败原因及目标/迭代事实；不能以identity/M0/B1顶替M1 |
| 合法已收敛 | FIT_OK；冻结(a,b)，只对该验证段及合法M0输入变换 | 验证标签不反馈(a,b)/EWMA；拟合不因验证分数差而重做 |
| 协议/程序异常、非法数值被误记成功或状态未记录 | 工程失败，整次不完整 | 不得包装为正常FIT_NOT_CONVERGED掩盖缺陷 |

FIT_EMPTY/SINGLE_CLASS/NOT_CONVERGED是允许的显式统计不可用状态，不等于子进程/数据工程失败；但八折任一M1不可用，主要H2不作全八折改善声明，总研究不能以剩余有利折评“支持继续验证”。不自动扩训练窗/换标签/降正则；完整记录失败也可工程合格并交付“证据不足”。

### 4.6 分母、指标与重采样

#### 4.6.1 槽、轮次与有效集

理论slot key=(round_start,round_id或该计划轮的缺失身份占位,offset)，计划轮按固定UTC五分钟网格，offset固定六值。占位不是伪造官方round_id；缺身份也保留计划槽。每模型每slot恰有一条状态记录（物理宽/长表由Design映射），不得重复/漏行，不把只输出valued行的文件称完整samples。

各组至少披露：theoretical_slots、observed_identity、valid_probability、known_label、binary_scored、draw_scored、missing_label、unvalued及原因、abstain、directed、correct、共同槽数/共同轮数、六槽完整轮数、零有效槽轮数、覆盖率及分母。标签状态与估值状态正交：例如WARMUP同时有DRAW，不能仅靠一个主reason丢标签计数。

定义比较集：

- C10：M1与M0都合法且非DRAW的配对槽，仅八折验证；为主要H2分母。
- C0B：M0、B0及该折B1合法且非DRAW的共同槽；H1概率比较使用同一集，不能与全99日B0描述分母混名。
- C2：三个floor核心均合法且非DRAW的共同槽；用于所有M2比较，逐模型覆盖另列。
- D02：M0与B2均有方向且官方非DRAW的共同槽；同时列各自方向覆盖和各自accuracy，不用更大的各自分母直接相减。
- payout集：对应比较的合法概率与官方标签含DRAW；与二元集分列，不把二者分母混同。

每个指标/配对差在自己的共同集内，先每轮对实际共同槽等权平均，再对有至少一共同槽的轮次等权；零槽轮保留计数不贡献数值。缺槽不补0、不以理论总槽作已观察损失的分母；同时报告观察覆盖=有效槽/理论槽。六时点表各自在固定offset内按轮等权。另作C10中恰六槽都共同有效的complete-six敏感性，不替代主要C10，不丢弃其外轮次。训练权重按§4.5，标签B1频率按唯一轮，三者不混用。

日/月表保存可加的轮次损失和与轮数；跨期汇总用这些分子/分母，而非平均每日/月/折accuracy。日块重采样也按抽中轮次分子/分母重算，不能简单平均日比率。

#### 4.6.2 指标定义

| 指标 | 数学与适用性 |
|---|---|
| 二元Brier | (p−y)^2，UP=1/DOWN=0；含p=0.5，不含DRAW/缺标签/无p |
| 二元logloss | −y·log(p_clip)−(1−y)·log(1−p_clip)；p_clip=min(1−1e-12,max(1e-12,p))只在评分层；原输出保留 |
| 含DRAW兑付MSE | (p−payout_up)^2，DRAW=0.5；非三分类Brier，不声称M1估计了DRAW概率 |
| 模型方向 | p>0.5为UP，p<0.5为DOWN，精确相等abstain；不用epsilon定义平价 |
| 方向accuracy | 正确方向/有方向且官方非DRAW的对应轮内/轮间加权分母；分子/原始槽计数一并给出 |
| 配对差 | 同轮同槽loss(候选)−loss(参考)，先轮内再轮次等权；负值较好 |
| 校准 | 非DRAW合法概率，固定10等宽桶，bin=min(9,floor(10p))；每桶原始slot数/轮数、权重、mean_p/up_rate；空桶count0、均值null |
| ECE | 同一比较集的轮次归一化槽权重，Σ桶权重×abs(桶mean_p−up_rate)；只是诊断，不取代主要Brier |
| floor占比 | 已预热槽中sigma_raw≤该候选floor的加权比例；sigma_raw为未加floor的EWMA标准差，零波动合法，非冷启动floor默认值 |
| 波动分层 | 因果sigma_raw固定区间[0,0.000025)、[0.000025,0.00005)、[0.00005,0.0001)、[0.0001,+∞)；M2比较层按M0同槽sigma_raw，不按未来收益/标签分层 |
| 价格参考差 | (S/K−1)×10000，单位bps；包含轮内移动，不解释为纯同刻Chainlink/Binance基差 |

零分母全部为null/N/A+明确原因，不用0/NaN/Infinity。按六时点、每折、UTC日/月、波动层及每候选给结果；校准可靠性图和分层图必须从同源载体生成，不手抄数值。含DRAW与非DRAW解释分开。候选数/成交/PnL/交易胜率/Sharpe/MDD等固定N/A+NO_REAL_BOOK_EXECUTION，不用方向accuracy冒充交易胜率。

#### 4.6.3 块bootstrap

主不确定性：成对UTC日整块，1000次，seed42。每一统计期间使用其全部按UTC排序的日历日（包括当日零有效槽），日数n；独立初始化numpy.Generator(PCG64(42))，integers(0,n,size=(1000,n),dtype=int64)。同一期间全部模型、配对差、六时点、complete-six共享同一日索引，不分别随机抽样；同轮所有时点/标签一起进同日块，轮次归其starts_at日。

每次抽中日按其完整轮次分子/分母汇总，零总分母该次为N/A，不重抽凑1000。区间为有效重复的[0.025,0.975]线性分位数，报告valid/invalid重复数；某区间用于支持证据时必须1000次均有效，不用少数有效重复伪称完整支持。主要日块不满足则§4.7证据不足；诊断区间不满足只如实标该诊断不充分及冲突，不自动否决主要证据。索引/分位算法不变，独立期间如每折/全99日描述分别重置同seed，不混期间索引。

7日敏感性固定为circular moving-block：在同一排序日历上，PCG64(42)生成1000组起始日索引，每组ceil(n/7)个，独立均匀取[0,n)；每起点取连续7日，尾端循环接开头，拼接后截至n日，保留重复日。模型/时点仍共用索引，指标/分位同上。n≤7记N/A_INSUFFICIENT_BLOCKS，不将单折退化区间当稳健性；主要八折合并期必须给7日结果。保存/可复算索引或其规范身份，不能把171072槽当独立Bernoulli交易。

### 4.7 数值容差与三层研究判定（V1.1，结果未见前冻结）

以下是本轮正式接受准则，不是已通过结果，不更改生产交易阈值。V1.1按Pascal新决策替代旧V1.0复合采纳筛选；V1.0的历史版本与T1 SHA/交接保留，但旧筛选不再生效。工程数值表、标签/可得性、权重/分母及bootstrap索引契约不变，不得看结果后放宽或以展示舍入充容差。

| 对拍对象 | 允许误差 / 拒绝规则 |
|---|---|
| 身份、窗口、时序、slot key、枚举、标签、计数、epoch/samples、状态、因果允许/拒绝 | 精确一致，零容差；bool不作整数，未知字段/版本不静默忽略 |
| 同输入同floor的同core复用结果、输入hash/manifest | 精确一致，不以概率接近代替来源一致；M2与M0概率本来可不同 |
| Rust/EWMA/同A&S公式独立参考 | abs≤1e-12或rel≤1e-9；近零走abs；边界分类仍零容差 |
| A&S概率与独立精确erf-CDF参考 | 绝对误差≤2e-7，单独列近似误差；不得用此较宽界掩盖同A&S接线错误或替换主函数 |
| 已落参数代回M1、逐样本损失、聚合/区间独立复算 | abs≤1e-12或rel≤1e-9；独立重算使用冻结相同索引/权重，零分母状态精确 |
| 独立重新求解M1 | 仍满足§4.5可行/收敛；a/b各abs或rel≤1e-5、预测abs≤1e-6，J差abs≤1e-10；不收敛不能靠参数接近通过 |
| 报告和CSV | raw浮点保留可往返精度（至少17有效数字）；正文指标/区间8位小数、百分比4位小数、计数整数；由同源raw固定格式渲染逐格相等，无第二手工数值源 |

第一层：工程硬门禁。因果时序/来源/身份、三流完整消费、理论/共同分母、数值/拟合正确性和独立验证全部为硬要求，失败即“数据工程不合格”，不能发表模型排名。正确记录FIT_EMPTY/SINGLE_CLASS/NOT_CONVERGED仍是允许的统计不可用，不把它改称工程异常；它使主要H2证据不足。非法计算却记成功、未记录拟合状态或错误权重仍是工程失败。

第二层：主要研究证据。唯一主要端点仍为C10的八折合并M1−M0 Brier配对差d（先轮内再轮次等权）及成对UTC日块95%区间[L,U]。八折FIT_OK、每折C10非空、主要日块1000次均有效是该端点的可用性条件，不是要求各折都改善。epsilon_d=1e-12只用于数值近零判断，不是经济最小改善阈值，也不用于方向/floor/标签/交易边界。

| 按优先级的条件 | 总报告四类结论 | 解释与动作 |
|---|---|---|
| 任一必需工程硬门禁失败 | 数据工程不合格 | 保partial/缺口，不发模型排名 |
| 工程合格，但任一折拟合N/A、C10空或主要区间不可用 | 证据不足 | 披露缺折/有效重复数，不选剩余有利折，保留M0 |
| 工程合格、主要端点可用，且M1在全部主要共同槽与M0在数值对拍容差内相同 | 假说不支持 | 该冻结映射无可辨评分边际价值，不否定未来所有方法 |
| 工程合格、主要端点可用，U<−epsilon_d | 支持继续验证 | 只支持冻结校准候选的后续验证；同时明示第三层诊断及冲突，不替换M0、不授生产准入 |
| 工程合格、主要端点可用，L>epsilon_d | 假说不支持 | 该冻结候选在主要概率评分上可靠劣化 |
| 其余主要证据（含区间跨/触0或数值近零） | 证据不足 | 无可靠改善保留M0，不换指标/参数反复跑直到赢 |

第三层：稳健性诊断与冲突解释。7日块、各折/六时点、complete-six、logloss/ECE、UTC日/月贡献及leave-one-day-out仍必须按原索引/分母计算和披露；无效时明确N/A原因，不能省略不利结果。它们不是“每项都过”的自动采纳AND筛选器，不设固定logloss/ECE恶化上限、折数配额、全部时点/全部逐日剔除须改善的门槛。逐项记录point/区间/方向/适用性；与主Brier改善反向（例如7日区间不支持、某折/时点劣化、logloss/ECE增加、剔除某日后反向）都列diagnostic_conflicts，含原数值、分母及解释。主证据支持而有冲突时仍如实写“支持继续验证；存在稳健性冲突、不得直接替换M0”，不能把冲突重分类藏掉，亦不能补造稳健性已通过。诊断不反过来选择主端点或事后重训；实际下一步仍须另行冻结/授权，本研究不部署。

H1为次要概率/方向证据：C0B上M0−B0、M0−B1的Brier日块区间分别按上述数值方向判支持/不支持/证据不足，两个基准都列、不只挑赢家；综合概率支持需两者均支持。7日/logloss等为诊断不作额外复合筛选；方向单列D02差与区间，不替代概率结论，不宣称家族显著性。H3只给两个floor、各因果状态/六时点的完整探索差与区间，EXPLORATORY/未多重校正，不选冠军授部署或本轮确认性支持。

报告先给M0诊断，再解释M1/M2。M0十桶/六时点/因果sigma_raw层的mean_p与实际up_rate、预测偏离0.5与实际偏离的方向，支持过度/不足自信的描述；日/月展示可加的轮次损失和/轮数及贡献，floor命中与两个既定M2差用于解释而非后验选赢家。这里只重用既定样本/分层，无新增诊断模型或实验。M1是单调非减概率映射，可能改0.5方向阈值，但评分改善不等于新增市场信息；概率校准、方向覆盖/信息和可交易价值分开。

效应大小d及区间、各折参数与额外拟合/计算/维护成本、trade close对midpoint的代理误差和经济价值未验证必须单列。没有同期midpoint无法量化close-mid误差，标UNKNOWN而非0；无同期份额盘口/费用/执行链不得推PnL、交易胜率或收益最优。无可靠经济最小改善阈值时不虚构数值，即使评分改善仍说明经济意义未知。未改善停止本轮扩参并保留M0；M2只探索，不追加半衰期/OBI/LLM/动量等。总分类、主要证据、诊断冲突和经济适用性分列，不能用一个总词遮掩风险；先验暴露/代理时钟始终披露。

### 4.8 可观察估值/样本状态与失败优先级

研究纯估值状态固定为VALUED、MISSING_IDENTITY、IDENTITY_NOT_AVAILABLE、MISSING_STRIKE、STRIKE_NOT_AVAILABLE、MISSING_SPOT、INPUT_INVALID、CLOCK_INVALID、SPOT_STALE、ROUND_INVALID、WARMUP；不可计算p/sigma为null。重叠拒绝优先：官方身份/strike/round合法可得 → spot存在/数值 → 时钟/年龄 → 预热 → 模型数值；已安全取得字段保留，不能为让状态好看补0。T2映射phase1实际Reason到上述语义，不能吞掉拒绝或把无book交易拒绝强作无概率。

超长gap在下个有效价触发LONG_GAP/new epoch及WARMUP；当前没价为MISSING_SPOT。非法wire、坏schema/重复键/非有限/bool冒数、倒序/重复事件、同round固定strike冲突、输出slot重复/丢失、输入标签混入估值协议均为契约失败，终止批次；不能以每槽INPUT_INVALID继续伪完成。合法缺失源行可建槽但数据资格失败；隔离fixture的合法策略拒绝可继续，原始数据损坏不被降为普通拒绝。

标签状态独立为BINARY_UP/BINARY_DOWN/DRAW/MISSING/PENDING/CONFLICT/AFTER_CUTOFF；训练AFTER_CUTOFF不入训练，但可在最终A允许的事后验证表中合法配对。参数状态见§4.5，统计零分母/区间无效独立保留，不拿一个主reason覆盖全部分母。

## 4.bis 持久化与结果接口

唯一最终正文：data/reports/2026-11-18-btc5m-phase1-model-research/report.md；一切必要CSV/图/原始估值/日志/manifest/参数/退出/复算在同主题evidence/。本节为逻辑字段语义，精确文件名、schema_version字面值、宽/长表及wire落点由T2冻结，不能实现时任选目录。无生产数据库/索引/TTL，无data/tasks/、docs/reports/或第二任务状态源。

### 4.bis.1 样本逻辑字段（均必有列/映射，无默认补值）

| 单字段 | 类型 / 可空规则 | 来源 / 隐私 |
|---|---|---|
| planned_start | UTC整数时间 | 固定理论五分钟网格；L0 |
| round_id | string/null | 真实官方身份；缺身份null，不以伪ID充官方；L0 |
| starts_at | UTC整数/null | 官方事实；L0 |
| ends_at | UTC整数/null | 官方事实；L0 |
| offset | integer | 六值之一；L0 |
| at | UTC整数 | 评分时刻；L0 |
| period | enum | 全窗描述/折验证/末日诊断的显式用途，不把重叠视图重复加总；L1 |
| fold | integer/null | 八折标识或末日独立标识，非适用null；L1 |
| model | enum | M0/M1/M2-low/M2-high/B0/B1/B2；L1 |
| identity_available_at | UTC整数/null | facade原可得时间；L0 |
| strike_available_at | UTC整数/null | 同上；L0 |
| strike | finite number/null | 官方固定K；L0 |
| spot | finite positive/null | 当前网格trade close；L0 |
| bar_open | UTC整数/null | 原秒线open；L0 |
| close_exclusive | UTC整数/null | 原闭合时间；L0 |
| spot_available_at | UTC整数/null | facade原可得时间；L0 |
| source_dataset | enum/null | binance-vision或缺；L0 |
| price_kind | enum | trade_close；L0 |
| clock_basis | enum | event_time_proxy；L1 |
| prediction_source | enum/null | 计算key的Binance或fixture明确来源，fixture/真实证据不混；L0 |
| actual_pair | enum/null | BTCUSDT或fixture合法pair；L0 |
| source_epoch | integer/null | 当前实际core epoch；L1 |
| reset_reason | enum | FIRST_SAMPLE/SOURCE_SWITCH/LONG_GAP/CLOCK_INVALID/NONE；L1 |
| samples | integer | 有效return数，不把首价/重复计样本；L1 |
| sigma_raw | finite nonnegative/null | 已预热原EWMA标准差；L0 |
| sigma | finite positive/null | floor后有效值；冷启动null；L0 |
| floor_hit | bool/null | 已预热时sigma_raw≤floor；L1 |
| secs_left | finite number/null | 真实T，非法round仍保留安全可算值；L0 |
| p_up | finite [0,1]/null | 原core或冻结M1/B概率；B2为null；L0 |
| valuation_status | enum | §4.8或B基准的明确NOT_APPLICABLE；L1 |
| label | enum/null | 官方UP/DOWN/DRAW，仅Python评价；L0 |
| label_available_at | UTC整数/null | 原facade标签可得时间；L0 |
| label_status | enum | 与valuation状态正交；L1 |
| fit_status | enum/null | FIT_*或该模型不适用；L1 |
| parameter_ref | string/null | 指向该折冻结参数身份，不能自由raw错误；L1 |

整数时间使用统一明确单位（现有微秒可得时间不得向下截断提前使用；Design选择精确表示并记录单位），UTC无本地时区歧义。Decimal仅在原适配边界单次转float，保留转换声明与原内容身份；不多次round或改变原facade数据。sample只存必要公共派生数据，不存原连接、环境或HTTP响应全文。

### 4.bis.2 运行/统计证据要求

- 参数与身份记录：主仓/BOT HEAD、dirty范围及实际源码/测试/配置/二进制/依赖身份、协议/公式版本、A/窗口/采样/offset/三个floor/拟合正则/折/权重/bootstrap及判据；源内容身份由facade认证，不以工作树自证数据。首尾逐项核对，发生漂移必须保留两份，不只比较两个结束态。
- 来源记录：每UTC日三个流的原始content/provenance manifest、实际完整消费hash/计数、coverage/gap/pending/conflicts/status、verify结果；理论日/轮/秒/槽与实际输出/原因核对，各核input/output摘要及样本数分开。
- 运行记录：真实argv/cwd、UTC起止、wall、父/子RSS定义、总deadline、每核observed native_exit/summary计数/complete/error/输出行数、terminate/kill/reaped/unreclaimed、读取任务cancelled/reclaimed/unreclaimed/still_tracked。进程高水位不伪称隔离臂峰值，facade open不伪称Mongo物理query。
- 统计载体：先M0校准偏差/六时点/因果层/floor/日月贡献，再M1主要端点与M2探索；保留每折/合并/六时点、含DRAW兑付/方向共同覆盖、bootstrap/LODO/参数与FIT状态及分子/分母/有效重复数。工程资格、primary_evidence、robustness_diagnostics/diagnostic_conflicts、effect_size/complexity_cost、proxy_error/economic_value_status、四类结论分栏；不再用诊断阈值AND布尔决定采纳。正文/图/CSV同raw，独立复算不读正文倒推raw。
- 旧binary/source/报告/失败历史只读保留；新构建绑定新身份，不能覆盖旧绑定binary而冒称原SHA。exclusive-create全新批准路径，已有目录/文件/symlink或创建竞态失败必须保持其字节/条目不变，不在未拥有目录中注入failure。取得归属后失败才写本次partial，真实失败不清洗成成功。
- 保留无自动TTL/删除/覆盖/迁移/上传/备份或从日志resume。临时探针仅当前profile scratch；正式最小证据不只留会被清理的scratch。data被Git忽略不是远程备份。任务进度/交接只在Kanban，T1及当前T2文档阶段不创建运行产物。

## 5. 正式验收矩阵

以下为后续必须真正执行的行为矩阵，不是T1已经PASS。测试输入fixture不得冒充真实99日；正常/反例仅替换输入/时钟/transport边界，不fake整core/runner后验证自制结果。

| 编号 | 接受场景 | 反例与必须结果 / 验证消费者 |
|---|---|---|
| A-001 | 新版本明确接入同phase1纯估值 | history/1默认core不冒充最新；无book/fee仍能估值、绝不造候选/订单；同core真实调用与静态调用图证据 |
| A-002 | UTC5秒网格用恰闭合[t−1,t)close | 未闭合bar/非网格1秒更新/错用[t,t+1)禁止；所有秒线仍消费；t同刻先spot再value、T随offset变化；真实适配→Rust |
| A-003 | 固定官方K、身份/strike在t前可得 | 后到身份/strike、K冲突、错轮/期限、把S重置K拒绝；六理论槽保留，不能未来A放宽t |
| A-004 | 21有效价形成20returns，跨轮/日连续 | 19returns为WARMUP、首价不作return、floor不免预热、每日/每折冷启动禁止；真实phase1状态对拍 |
| A-005 | 同key gap=300秒不断、短缺口按实际dt | >300新epoch/首价samples0；SOURCE_SWITCH及回切重预热；CLOCK_INVALID丢观测；不补returns/借旧源暖态；fixture和实际模型消费者 |
| A-006 | 血缘Binance Vision trade_close/event-time-proxy完整 | 逻辑clock不得冒真实request/received/source延迟或midpoint/Chainlink流；不向controlled v2伪装真实clock；真实输出字段检查 |
| A-007 | M0与两M2共享有序输入、独立连续core | 各核同input hash/count/slot/epoch；异floor值允许不同；中值复用M0且配置旧/1不松；一核失败另核0也整批不完整 |
| A-008 | 单日流式输入及固定core/活跃轮状态 | 多日内存状态不能随累计round/秒线对象线性驻留；不重开每日EWMA；真实pilot资源/状态上界及代码审查 |
| A-009 | 三流完整消费、99日预期及manifest吻合 | 缺日/缺秒/缺轮/未决/冲突/verify失败/内容漂移→数据工程不合格；不补0/改A/缩窗；实际facade读及边界故障fixture |
| A-010 | 标签恰C可得进入该折，≤A事后评价 | C后但A前标签、跨训练尾部未结束轮、DRAW不入训练；改验证标签不改变该折B1/M1/EWMA；折训练真实消费者 |
| A-011 | B1按截止C唯一官方非DRAW轮计频率 | 不按六槽/仅M0有效槽重复计数；零分母null、单类0/1合法；不得用全99日比例 |
| A-012 | 固定λ、轮次权重、单(a,b)、可行收敛FIT_OK | 偷换正则/按时点拟合/验证择参/未收敛仍出p1拒绝；独立目标/梯度/参数/预测对拍按§4.7 |
| A-013 | FIT_EMPTY/SINGLE_CLASS/NOT_CONVERGED显式N/A | 不用M0/identity/B1顶替；八折失败仍保留完整slots/其他模型，H2证据不足；真正代码异常不得伪装允许拟合失败 |
| A-014 | 八折扩窗与末日单列；验证仅价格无监督更新 | 预测/标签截止正确、参数事前冻结；末日/训练前M1不得回填或纳入主要区间；实际分区样本检查 |
| A-015 | 缺概率/缺标签/DRAW/abstain正交计数 | 所有理论槽精确一次；p=0.5在二元但不方向，DRAW只兑付；不把null作0、B2作可靠概率、accuracy作交易胜率 |
| A-016 | C10/C0B/C2/D02与complete-six分母透明 | 不同覆盖不直接相减、缺槽不补0、先轮内再轮间权重；不平均日/折比率；独立原始样本重算 |
| A-017 | 10桶、因果sigma_raw层、floor占比/日月表 | 空桶null、冷启动不算floor命中、不能用未来波动分层；图/表来自同raw；纯基差/三分类解释禁止 |
| A-018 | PCG64(42)1000日块共享索引，7日块敏感性 | 时点/模型分别抽样、丢零样本日、日比率平均、零分母重抽均拒绝；独立索引/区间重算，n≤7七日块N/A |
| A-019 | 独立EWMA/A&S参考与精确erf两路径 | 同A&S按紧容差，近似CDF误差单列不混；ATM/远离strike/低波动/floor/预热/30秒边界向量真实core非零命中 |
| A-020 | 新输出独占创建且成功取得归属 | 既有目录/文件/symlink/竞态保持精确字节条目，不启动DB/core、不注入failure；自己归属后的故障保留partial |
| A-021 | native0且完整summary/输出/输入计数一致 | bool冒数/缺summary/负计数/错行数/缺values、非零/写阻塞/超时/中断均整批不完整；逐核native与PID回收，健康核不得掩盖故障 |
| A-022 | 首尾源码/二进制/依赖/源manifest身份一致 | 漂移、未知版本/标签混入Rust、错误scope→不完整/失败，保留前后；旧binary/证据不改；旧/1/普通phase1生产回归真实通过 |
| A-023 | T3真实小窗/单日pilot，T4先独立校验再一次99日 | pilot预算/对拍/源消费不过不得开全窗；预算外停止不加时/减窗/换预取；不以R4的27.4秒或旧估算当新实测；无需默认第二遍全库 |
| A-024 | M0诊断先行、同源CSV/图/正文、独立三层判定复算 | 工程硬门禁不降；主要八折Brier日块证据/诊断冲突/四类结论分列；反例为主证据改善但7日/时点/logloss等冲突，必须保主证据原判与风险、不得复活旧AND或无条件替换M0；效应/成本/代理误差UNKNOWN及经济价值未验证、H3探索/交易N/A/先验暴露必列，坏数据不排名 |

## 6. 验证范围、执行预算与失败行为

### 6.1 实际执行与独立性

Design必须根据真实现存入口冻结精确命令、解释器/cwd/参数/输入输出/超时/受影响测试与真实消费者filter，不杜撰测试名/计数。Python固定项目.venv/bin/python；Rust仅现有缓存cargo --locked --offline，不安装、不改锁。--offline限制依赖下载，不自动证明业务socket为零；测试用隔离fixture，真实研究只经已准facade读已有数据，不读交易凭据/启动原bot。

T3：必要工程回归、真实5分钟小窗、独立A&S/erf固定向量对拍和固定单UTC日pilot。独立向量不得仅由实现主代码生成期望；可在测试侧独立参考或由非实现者提供，主结果仍唯一Rust计算。T4：独立核同小窗/pilot接线、数据及预算；通过后仅一次正式99日共享M0/M2输入，复用样本训练M1/统计；独立重算主要指标、权重、标签配对、bootstrap、结论和表格，不默认再读99日。缺口只补受影响范围，不能把旧R4 PASS当新增接线/模型结论。

### 6.2 有界成本与停止

T2须在卡预算内冻结真实小窗/单日pilot精确窗、wall/RSS/写盘/verify上限、总原生进程/读取超时及清理余量；预算校准基于实测pilot覆盖全部三核心、完整消费/hash与评分开销，不能只测Rust纯计算。预先确定保守外推方法并另留拟合/bootstrap/独立核验/清理余量，不能看全窗进度临时加时。

全窗启动必须可容纳既有T4五小时总墙钟上限（含独立验证及清理）；Design冻结的子预算必须更小并有明示余量。pilot超限、内存超界、预估超预算、源不合格或必需验收失败即停，不自动提高预算/缩窗/减少候选/改采样/改serial为prefetch/后台续跑；交主控真实缺口。旧45–75分钟/2–4小时是估算，旧R4单日是legacy测量，均非本轮运行保证。

### 6.3 精确失败结果

| 失败类型 | 必须行为 |
|---|---|
| 参数/版本/路径/既有输出冲突 | 在DB/core/业务写前拒绝，非零；旧目标原样，不能自动换ID/路径 |
| 数据不完整/流消费或来源hash失败 | complete=false，保留已拥有partial及精确缺口；不发布完成正文/模型排名 |
| 任一core异常、summary/计数矛盾、管道破裂 | 整批complete=false，不以另一核native0补成功；所有核逐个有观察到的native_exit及实际状态 |
| 总deadline/写入超时/中断 | 停止新增读取/写入，取消未启动任务，terminate→有界wait→kill→有界wait→reap；不阻塞式无界等待 |
| 读取线程无法杀死 | 记unreclaimed/still_tracked，保持追踪，不假装回收、不吞error或重开并发读取；本次不完整 |
| 身份漂移/输出I/O或日志失败 | 保留原异常与成功前缀，清理异常不能覆盖主失败；未知native exit为UNKNOWN，绝不补0 |
| 允许的拟合不可用 | §4.5明确FIT状态，统计N/A、科学结论证据不足；非静默异常/工程成功替代品 |
| 研究评分不改善 | 完整工程/数据仍可完成，按§4.7诚实交付，不反复跑/选参直到赢 |

Design须冻结各CLI数字退出码映射及观察到的子进程native退出记录，未知映射不能在Implement凭猜测选；本文规定所有运行/数据/预算/漂移失败非零，正常无改进且产物完整不应伪装工程错误。complete/工程资格/研究分类三项分开，不能用单个exit0宣称三者全过。

安全拒绝按动作级规则停该动作及依赖；可选转存省略NOT_EXECUTED/OMITTED，不等价重试；必需验收缺口block，不换工具/包装/解释器/后台或主控代跑。不弱化验收/配置权限求通过。普通参数、路径、patch/read-before-write错误在原授权内修复，不当作安全拒绝或依赖安装授权。

## 7. 实现约束与本阶段静态验证

- 不重做R4性能工程、已摄入数据或全仓无关套件；只做接线/统计真实增量与受影响旧协议回归，现有默认语义只读优先。
- 不创建第二份生产模型、Broker、账本、数据Provider/研究平台；独立参考只用于验收，不参与主样本生成。无book估值不等于同执行模型已验证。
- 新单测colocate；G3按项目现行≤1200/1201–2400/2401–3599/≥3600规则。Design说明实际>1200文件职责/增长/拆分触发，必要拆分限当前职责，不以G3名义跨模块重构。1201–2400独立审查沿既有Validate，不新增默认卡。
- 新构建/协议不污染旧历史报告/binary身份，不放宽旧参数门禁；任何范围外必要路径/依赖/生产副作用须先报主控，不能由实现者自行授权。
- T1历史仅两文件静态验证；本T2为三文档实体/版本/互引、新旧判据闭合、提案/分母/边界/矩阵/实现接缝一致性及精确路径git空白检查/SHA。既有07-005三文件首尾hash比对不改正文。未运行cargo/Python业务测试、DB或研究，不报告实现通过。

## 8. 开放问题与交接

开放业务语义问题：无。未验证条件：固定A下真实99日来源/标签完整性、最新5秒phase1接线/数值、pilot成本及正式研究结果；这些后续必须实测，不是本T1完成事实。

Design V1.1冻结内部/执行事项：新wire/字段映射、原计算最小提取、旧binary保全、精确allowlist/G3/测试及CLI、现有依赖拟合/统计、pilot窗/外推/硬上限、退出码与物理产物。除本次Pascal明确批准的判定分层和诊断顺序外，不重选A/候选/折/正则/分母；新业务冲突集中退主控，不偷偷扩权。

本次T2交付同步的RFC/SPEC/Design V1.1实体及SHA、旧新判据闭合清单；原T1 V1.0交接仅为历史，不追认为修订通过。预建独立只读Design Gate t_780aa76c与主控核验后才可恢复既有T3/T4，本文不解锁或自签。最终报告仍只在本主题；进度/依赖/命令/未覆盖项仅Kanban，无第二管理档案。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.0 | 2026-11-18 | 冻结99日/A/5秒因果和epoch、三floor共享连续核心、八折训练可得性、固定Platt/失败、权重/分母/区间/容差/裁定、24项验收及只读有界执行；未实现或运行研究 |
| V1.1 | 2026-11-18 | Pascal新决策：M0诊断先行；§4.7工程/主证据/诊断三层替代旧AND筛选，四分类/A-024/载体一致；数值容差/标签/索引和实验不变；效应/成本/代理与经济未知分列；T2候选待独立Gate |
