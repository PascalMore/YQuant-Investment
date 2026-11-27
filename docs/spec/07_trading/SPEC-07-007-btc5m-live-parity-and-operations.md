# SPEC-07-007: BTC5m live 一致性、实际账务与值守运行契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 / 版本 | V1.20；§R21 下单前异常退出的受限恢复规格冻结；R21 Design/实现/独立验收未交付，实盘仍 HOLD |
| 本次窄修订 | V1.20，2026-11-27：只新增指定历史窗口的资格及原双读接线契约；D21-01–07；R20 及更早契约保留 |
| 作者 | YQuant Principal / yquantprincipal |
| 创建 / 更新 | 2026-11-19 / 2026-11-27，Asia/Shanghai（UTC+08:00） |
| 来源 RFC | [RFC-07-007](../../rfc/07_trading/RFC-07-007-btc5m-live-parity-and-operations.md#r21) V1.20，§R21.1–R21.4 |
| 工作区 / 来源任务 | /home/pascal/workspace/yquant-investment；初版 t_b946f2c3；本轮 t_247f4962 |
| 对应 Design | [DESIGN-07-007](../../design/07_trading/DESIGN-07-007-btc5m-live-parity-and-operations.md) §6.3–6.5（含 G3）为只读基线；已落盘 §R20 V1.19 不变，§R21 待 t_74644667 同步 |
| 执行 / 验收 | Principal Design；Developer Implement；Reviewer 独立 Validate；主控 Gate/Closeout |


## R19：第③项原请求出口观测与共享配额调度（2026-11-26，需求冻结）

本节落实RFC V1.18 §R19，只覆盖③；R18及旧章节中的阶段状态保留其当时时点含义，以本节/元数据为现行状态。①②已签收未部署基线及证据见RFC §R19.1，不重开设计或重报节省。④后续未冻结/未实现。本节中的字段、结果名和公式为可测试的逻辑合同，不预定新公开API、Rust结构、模块/锁实现或live wire；这些由下一Design落实到原出口及原消费者。

### R19.1 输入、输出与观测口径

输入必须能确定同进程固定API部署、实际HTTP method/规范化route、下述bucket、发起该请求的原业务caller/优先级、原逻辑操作及页/批/认证尝试归属、取消/硬stop与原截止、请求前及响应时双时钟、HTTP整数状态或transport失败类别、有限数字配额/缓存头。caller封闭为DISCOVERY、BOOKS、ACCOUNT、EXECUTION、SETTLEMENT、CONTROLLED_SEND、CANCEL、OTHER；auth作为子操作继承原caller/优先级，独立原认证入口属OTHER。逻辑操作关联仅用进程内数字ID，页/批序号为非负整数，非分页为null；outcome封闭为SUCCESS、HTTP_ERROR、TRANSPORT_ERROR、BODY_ERROR、LOCAL_REFUSED、CANCELLED。页cursor、原URL/query、ids列表、body、自由status/错误链和凭据不作为观测值。当前调用者不得由异步任务全局可变标签猜测；账户解释调用market/category时仍能归到该账户读，而不全部标作发现。

每次原REST transport首次交接分配进程内单调attempt序号（此前为null，通过逻辑操作ID关联排队），记一笔本地发送消耗；每个分页、book批次、auth两路和401允许的唯一重读各自计数。沿原脱敏log固定输出：method、route模板、bucket、封闭caller、逻辑操作/页或批序号、attempt序号、queued/handed_off/completed或cancelled的类别、queue_wait_ms、从交接到完成的duration_ms、HTTP status/null、封闭outcome，以及已校验数字配额和头部可信度分类。时间差非负且须合法取时；无法确定保留unknown/null，不夹0。一次attempt只计一次handed_off，终态至多一次；本地拒绝/尚未交接取消为0HTTP，已交接取消仍算已发；若响应头已收到则保留已知整数HTTP状态，否则状态未知。日志用固定标签与整数，不记录秘密/账户地址/原header及任意字符串，不输出key/JWT/signature的摘要。

输出行为为：允许一次交接；尚未交接、可取消的有界等待；或尚未交接的明确拒绝。交接计数指首次poll可发HTTP的原transport future，未等同socket已发字节/服务端已扣额；即使Pending或立即失败仍保守计入本地预算，不能把队列future的poll算成交接。已交接后只能报告真实HTTP/transport结果，不把被取消future当成未提交。RPC/Binance/Coinbase不计入Predict REST，原timing::net_calls和audit/event数不冒充REST总量；不为得到RPC数字增加任何RPC。逻辑操作、page/batch与HTTP attempt是不同计数，分列而不相加重叠总数；服务端Remaining另列为反馈，不当成本进程实际扣额。沿现有tracing/原测试transport，不新建sink、指标服务或事件schema；日志失败不创造发送许可，也不篡改原关键审计失败语义。

### R19.2 scope、route与缺头保守预算

同进程同固定API部署的原request出口共用状态，涵盖client克隆、不同实例、账户/JWT/key及所有caller；没有可核公开APP身份时保守合并同部署，不按秘密值分桶或读取新凭据。主网/测试网部署独立，不跨进程持久化/恢复/分布式协调；换client/新run不得给同进程仍有效的配额重新充值。没有当前服务端限额证明时，本地保守上界为下表，不声称这些是当前key实际限额：

| bucket逻辑名 | 实际route匹配，移除query且参数用模板 | 本地上界 / 来源 |
|---|---|---|
| ORDINARY | `/markets/orderbooks`先精确匹配；`/series`及其rounds、`/markets`、`/markets/{id}`、`/categories`、`/categories/{slug}`、`/account`、`/positions`、`/auth/message`、`/auth` | 每60s最多240次；源自分析普通旧key240/60s，低于公共250/60s。批量books必须属本桶，不能按名称含orderbook套500 |
| TRADING | `/orders`及其子路由；单市场`/markets/{id}/orderbook`，参数必须确为原合法ID且非批量路径 | 每60s最多500次；分析保存的官方交易路由分类，不是本key额度证明，收到更低有效反馈立即进一步约束 |
| SEARCH_OR_UNKNOWN | 其余未在上两行精确识别的路径，含search；不凭相似名字升级 | 每60s最多120次，保守采用分析中最小默认类；同时占用ORDINARY及TRADING的本地额度并满足它们的有效反馈/冷却，避免未知路径实际共享已知桶却另获一份额度。未知route日志只记OTHER，不反显原path |

匹配优先以精确批量例外→明确模板→OTHER，不将每个route独立配置一份额度。scope/bucket是本地保守共享域，不推断服务端不同bucket一定独立或同名标签就是APP ID；已明确归桶的普通/交易路由不额外套跨桶总额。未知路由是显式保守例外：其反馈/429约束所有可能共享桶，但观测HTTP attempt仍仅一笔，不按占用桶数重复计算；不猜它实际属普通/交易/search中的哪类。若反馈显示本桶更紧则受其约束，未识别低于上述默认的真实自定义限额仍可能先产生429，须如实披露，不承诺首次即零429。全部method均计一次，包括冷认证/刷新和原已授权写；不为探知额度增加额外请求。

本地上界是滑动窗口保证：在时刻t的准入线性化点之前，对所有适用窗口w，未持占位的新请求须满足`S_w(t)+H_w(t)+1 <= L_w`；S是此前已交接、其发送时刻在`(t-W_w,t]`内的次数（不含当前待准入请求），H是已授予但未交接且尚有效的额度占位。当前请求已在H中时要求`S_w(t)+H_w(t) <= L_w`并转换占位为发送，不再加1。表中60s本地上界持续存在；当前反馈只能进一步收紧，250反馈不把240本地安全余量变成新增信用。W使用含暂停的单调经过时钟，不猜服务器自然分钟边界；这比服务端固定窗口保守，属于本次明确取舍而非把单route当250。允许健康低于预算的真实路径，不以永久全拒绝代替调度。

### R19.3 数字头、多窗与权威性

1. 有限解析范围：兼容单组三头`RateLimit-Limit / RateLimit-Remaining / RateLimit-Reset`，以及既有探针识别的同标签`RateLimit-Policy`之q/w与`RateLimit`之r/t配对。L/q及W为正整数，R/r为非负且不大于对应L，reset/t为非负相对秒数，不是epoch/毫秒；拒bool、负数、非有限数、溢出、截断及冲突重复。允许HTTP字段名大小写和合法空白；只接受完整、无歧义的条目，不沿探针正则挑子串跳过坏项。多窗按同一安全标签唯一关联，不按列表位置强配；日志仅输出校验数字及本地window序号，不透传远端标签。没有q/w的独立reset仍可仅作429冷却下界。该子集是本项支持范围，不宣称覆盖未取证的全部标准扩展。
2. 每桶支持最多4个不同有效窗口（含本地60s，重复同W合并从严）；这是覆盖当前单窗及有限多窗输入的本地支持边界，不是服务端政策只有4窗的事实。有限响应头解析需有字节/条目上限，具体界限由Design按原HTTP边界给出。不认识的fresh政策、无法关联/冲突的有效多窗或超过支持数，不选宽松子集：记POLICY_UNINTERPRETABLE，受影响桶保持本进程新准入拒绝（换client/run不清除），本run沿原错误/失败预算退出，不新增控制台探针或盲降到宽松默认。单组三头缺失/普通畸形且无可确认新政策时只记MISSING/MALFORMED，保留已有约束和本地预算；不能因一次坏头清空先前紧限额。没有服务端w的单组三头使用本地60s作为本项支持的已知窗口，若另有政策冲突则不能猜；新窗口单位不被识别时不伪装60s。
3. 当前可用反馈限定同桶、同部署、实际收到HTTP响应的数字头。明确cache HIT/STALE/REVALIDATED、Age>0、stale warning或缓存年龄无效者为缓存/不可信反馈；不提供新的剩余额度/重置，不证明当前服务端状态。DYNAMIC/MISS/BYPASS且Age缺失或0可作当前反馈；仅有s-maxage不等于HIT。无缓存来源信息为UNKNOWN，只能从严收紧、不能释放旧约束或增加信用。重复Remaining=249不是免费请求：所有本地交接仍计S。已缓存的429也必须触发本地冷却，不能因缓存标志忽略429。
4. 对可信反馈的每个窗口，receipt双时钟为C，reset为d，逻辑有效期是`C.utc+d`及`C.elapsed_ms+1000*d`；额度恢复须两者均到、任一时钟异常/回退/溢出不能提前恢复。每个反馈给本桶增加未来发送的上界：`G=max(0,R-U)`，U为不能证明已被该响应计入的本地其它已交接请求数（至少包括该请求开始时仍在途的其它请求，及此后交接而响应未确定覆盖者）。尚未交接占位还须扣除，不能让并发都消费同一个R；当前返回请求不重复从R扣一次。所有有效上界取交集，新/乱序/缓存响应不得回补已发/占位或撤销较早尚有效的紧约束。未来每次交接消耗各适用G，响应应用与准入必须有可线性化的顺序；精确归并/存储属Design，不允许用最后响应覆盖剩余额度。
5. 对多窗同时应用各自L/W及G/失效时间，最紧者阻塞；同W多个有效反馈合并从严，不丢独立较长窗口。学到的L/W政策保留，后续可信政策可更新，但不能在旧约束有效期内放松它；缺坏/缓存头不删除已有政策。旧反馈到期只移除该反馈的剩余约束，不能擦掉仍有效的其它窗、本地S/H或429冷却；本地到期消耗只按原发送时刻老化。正常响应R=0且Reset=0或缺坏时，剩余额度不得立即回满，按本桶最长已知W从本次receipt计一个保守禁止新交接的区间，沿原失败预算而非忙循环。坏/缺/缓存头从不续写业务receipt或创建服务器免费额度。重启无旧信用；本地预算和冷启动仍适用，不承诺知道外部进程先前已用多少。

### R19.4 429、并发、优先级与取消

429响应在头可见时即更新所属桶冷却，不能等body读取/JSON解析成功；保留该次HTTP计数。可信正数Reset以本次receipt+Reset为至少等待的双截止；缺失、坏、0或缓存/未知可信度反馈至少等待本桶最长已知W（未学习时60s）。后者若仍能独立校验出正数Reset，则取`max(最长已知W,Reset)`为等待秒数，只作冷却下界、不作补额依据，不能因为缓存/缺其它头忽略一个更晚Reset。所有生效截止均须双时钟都到，不把0当成马上可重试。已存在冷却只能取更晚截止，2xx/401/同值头不能提早解冻；同桶所有caller/优先级及尚未交接占位都重新校验。冷却前已交接者允许原事实返回，但其迟到响应不清429。跨bucket不无依据冻结；未完成的普通桶依赖仍阻断需要该事实的交易。单独Retry-After不替代已取证的RateLimit-Reset，不新增429自动重试。

本进程同一额度的并发竞争必须原子，N个并发请求至多获当前可用额度数；不能先发完再靠日志发现超量。允许正常原并发账户腿，不要求把整个读串行化。优先级为：P0原当前账户/在飞execution/结算与已授权安全取消（其必要auth继承P0）；P1当前行情/发送准备及controlled初始写；P2目录/round发现及无当前风险的后台元数据。同优先级FIFO；更高优先级等待时不得给新到的低优先级占位，但不抢占已交接请求；低优先级可因持续P0或期限而失败，明确记录，不保证外部额度不足时无饥饿。不另设未获依据的每类额度保留百分比，不借P0绕冷却或自动执行cancel。caller沿实际用途传播，方法名本身不决定优先级。

等待有界于原逻辑操作已有截止、run deadline、所属失败预算及取消/硬stop；队列/占位集合必须有Design给定的有限容量，超量明确未发失败，不无限堆积。任何占位取消/超时/未交接拒绝恰释放一次；一经交接，无论transport错误/429/取消都不退还本地发送消耗。冷却或截止与获得额度同tick竞争时，先重检取消/硬stop/期限，等号不发送。等待时不得持Broker/attempt/发送门锁，不用阻塞sleep拖住其它安全消费者。父失联/输出故障/人工stop沿原控制机制唤醒/拒绝，不等Reset后再处理；不通过drop已发future伪造0POST。

### R19.5 读失败预算与controlled原子发送

配额排队是原读的一部分，其request_at不得挪到获额/响应后；原book/spot/account freshness须含等候，receipt仍取真实完整解码/核验完成时点，不能改request_at或仅看刚取得的receipt来掩盖旧请求。对R14账户Read/Execution及既有Settlement streak，额度不足首次阻止取得必要当前事实时即进入相应原失败计时；wait/下一tick/新header/reset不能重置since，120s与原deadline任一到即原停止，不另外再给等待后的120s。只有实际当前完整成功读可按原规则清对应streak；不能用只获额、单页成功、2xx坏body或其它消费者成功清零。行情仍原failed_ticks，不套账户120s；R17固定签名expiry/尾查、R16现金600s、sticky stop均不改变。原已存在的超时可更早结束单次读；内层等待不能把外层失败升级为无限挂起。

原`request.rs::controlled_write`在`with_send_permit`内首次poll request future，`fills.rs::place_controlled_tracked`已在此前完成token/签名/链检查/ACK。新增额度必须先在最终同步许可之外完成可等待准入；其后仍以原guard/当前CheckTime复核账号receipt、generation、绑定hash/quantity/route、book/spot/request年龄、expiry、deadline、stop/loss/监督及FINAL_SEND。额度占位不是发送许可、不是MayHaveSubmitted，也不冻结freshness；可等待位置及同步二次准入的内部方法交Design。

在原同步许可至首次真正transport poll之间，必须再次验证本桶额度占位/冷却版本仍有效，并原子转换为已消耗；与并发429的胜负须可线性化。配额变紧/取消/超界且尚未交接时0POST、保留明确未发送证据，按原拒绝/错误与自身未用预占处理，不清旧tombstone/硬stop。不得在`with_send_permit`的first_poll callback里首次遇额度等待并返回配额Pending，不在State/handle/gate锁内await、sleep或再次排队，不先耗原发送许可再等待；不得使新的quota锁与原State→handle→gate产生反向等待。最终检查到首次poll之间无额外I/O/日志刷盘/认证或锁外异步间隙，原保护不被额度快路径替代。

首次真正交接后唯一future的Pending/立即失败/401/429/timeout/坏响应均不构造第二POST，不因预算回退重签或广播同hash，保留MayHaveSubmitted/Unknown及原预占/账务/同hash读取。官方429“不处理”不是本项授权修改原Unknown证明。只读401仍限原一次刷新重读，每次auth/重读独立受预算及原总截止约束；429不能触发401刷新分支或原请求helper自动重试。配额缺口读用既有ReadUnavailable安全码及固定日志分类；明确未发送的controlled拒绝沿原typed路径，已可能发送沿原SubmissionUnknown；不新增stop reason或自由错误文本。

### R19.6 可计算验收与收益归因

同一离线脚本化业务输入/分页/认证/并发/时钟，分别给出：logical操作/页或批、实际handed_off次数（按bucket/route/caller/结果）、未发送拒绝/取消、等待区间、Reset前后发送时点；HTTP总量只取handed_off并与transport逐条一一对应。RPC/其它服务及audit另列已有可证计数，不拿原timing计数代替；未测为未测。所有准入在其线性化点当时有效的`S+H<=L`与反馈剩余约束、冷却期间0新交接须可用事件时点复核。新反馈把L降到已有S之下或G降到已授H之下时，不追改/退款已发事实，所有尚未交接占位失去无条件发送资格；0新增直至重新满足新约束，不能要求撤销过去HTTP或以旧许可继续超发。

健康低负载、相同成功序列下，相对已验①②候选不增加任何REST/RPC验证请求，①合格旧历史后续详情/官方0读、当前全页matches继续，②原目标路由与300s目录语义/冷热计数不退回；健康受控候选可到一次fake POST，不能全拒绝。饱和/429同输入对照必须在已知冷却期实际阻止原会继续发的请求，恢复后仍能完成原必要当前读；不是通过放宽freshness/延后deadline/删当前事实/新增自动重试完成。节省只报该fixture实际被抑制的attempt，不重复归③为①②的24→2/冷6→2收益；不把分析339–352/min条件模型当历史HTTP或新实现产能。

### R19.7 原消费者必需验收（Design细化，后续Implement/独立Validate执行；本卡未运行）

| 编号 | 输入与真实消费者 | 必须结果 / 反例 |
|---|---|---|
| D19-01 | 原request出口/真实adapter下目录、rounds、批量books、单市场book、账户/订单分页、冷auth与一次401刷新；原log/transport双计数 | 每次交接一对一且route/bucket/caller正确，批量250证据不误用500、同桶不按route拆额；auth/页/批/重读单列，0POST本地拒绝不算HTTP；RPC/audit不混。跨异步caller不串标签；恶意path/query/body/header/异常含secret哨兵，log/Debug/持久流均不泄漏 |
| D19-02 | 原出口注入三头与q/w-r/t；正例单窗/多窗，缺坏/重复/冲突/负数/溢出/不支持窗口、DYNAMIC/MISS/HIT/Age/s-maxage/未知缓存来源 | 本地保守上界、全部窗及R-U同时约束；坏缺不补额，缓存249重复仍每次扣本地；250不放大本地240，未知/超支持政策不挑宽松窗；未知reset不按epoch猜；无新增探针 |
| D19-03 | 同进程不同client/克隆/caller/key标签同时请求、同桶余额只够部分；mainnet/testnet隔离、乱序响应/在途重叠、新反馈降限低于已有S/H及未知route | 额度/占位线性化、无双消费/重复充值/迟到回补；降限不追改已发，但尚未发全部重检；未知路由不另领可能共享桶的信用、HTTP仍一笔。正常账户原并发仍能完成，另client/new run不能清同进程旧冷却；不同部署不串；并发与内存边界/取消无泄漏 |
| D19-04 | 原多caller同桶收到429，body挂起/坏JSON、Reset正数/0/缺坏/缓存；迟到2xx、重复429及独立bucket | 头到即冷却，同桶Reset前0新交接、两时钟均到且其它窗可用才恢复；不清已有更晚冷却，不因另一bucket成功解冻，不自动重试；普通依赖失败不放行交易。HTTP429保留原typed读失败，不冒充旧历史冲突 |
| D19-05 | P0账户/在飞/结算、P1准备/POST、P2发现竞争；排队/占位前后取消、deadline/stop/父EOF/输出失败同tick | 预算与冷却对所有级别生效、高优先级先于新低级、同级FIFO，已发不抢占；有限等待/容量，未发恰释放一次，已发不退款。无Broker锁跨等待、无busy loop；无未获授权cancel/写动作 |
| D19-06 | 同原guard/handle/gate/controlled_write受控消费者：等待后仍新鲜正例；等待至freshness/expiry/deadline边界，获额后并发429/stop、同步最后检查前后竞态 | 正例最多一次fake POST且first poll确在原同步许可内；拒绝在交接前0POST、不伪造MayHaveSubmitted、不排队后发旧单；许可内无额度Pending/sleep/await。交接后Pending/立即错/401/429/timeout/取消/坏响应均不重POST，Unknown/tombstone/预占保持，不借quota许可替代原全部校验 |
| D19-07 | 原account/Broker/drive的Read/Execution/Settlement分别额度不足→短暂恢复，连续120s边界及原deadline更早、暂停/双时钟回退；R17/R16/行情回归 | since从事实首次被阻止起、队列/reset不重置；仅完整当前成功清本streak，不跨清、不伪造receipt/generation。120s等号及更早硬stop仍停止；R17固定expiry+尾查、现金600s不续命；行情保持原failed_ticks。错误仍安全typed、事实冲突硬保护 |
| D19-08 | ①②同真实adapter→account/Broker连续观察与原read_rounds/策略，加原producer→supervisor首次write→strict reader；原paper/live/发送/控制受影响回归 | 保持①24→2/部分24→4资格语义及②同5系列冷2/热1、两页冷3/热1；当前matches/本run claim/结果发布fresh现金及原Final保护不删。低负载不新增REST/RPC、原健康fake POST可走，429前后同脚本实际少发无效尝试并恢复；原严格wire/未知hash/±1atom/输出故障反例不变。不是仅limiter helper/纯公式或另造客户端测试 |

### R19.8 closed/open、必要取舍与阶段输入

需求closed：原出口计数/脱敏、同进程同部署保守共享、route例外及本地240/500/120上界、有限多窗及反馈从严、429reset、并发/优先级/取消、读预算和首次poll同步准入、D19-01–08。open需求语义为空；明确取舍为保守滑动上界可少于服务端固定窗吞吐、无公开APP身份时合并同部署可能过限流、缓存/外部竞争无法保证零429、不支持政策fail-closed；不降低①②降耗目标、10s门禁/≤5s目标或120s预算。上述本地规则不是推断当前key真实配额，不要求真实账户/API补证才做离线Design。

Design必须在原链内选择最小状态/函数/锁与取消唤醒、头解析和队列有限上界、同步额度转换/失效接缝、safe错误映射及原fixture的HTTP状态+headers输入，列精确allowlist/G3/身份闭包/可运行RED-GREEN及原消费者映射；不能改本节经济/配额/失败语义，也不新增runner/平台/依赖。RFC与本SPEC V1.18独立存在；阶段指针同步：Design现为V1.18 §R19.1–R19.9（t_edbfef11）。主控已放行独立Design阶段，仍须在后续Implement前核三文档一致性/精确allowlist/G3/可执行边界后另放Implement行政HOLD；done不代表③实现/业务PASS/生产许可，④后续未冻结/未实现。后续正式必要结果只用`data/reports/2026-11-26-btc5m-rest-quota-part-3/`及evidence，本阶段仅静态文档与Kanban交接，无结果报告/任务镜像。

## R18：第①项已核清历史基线免重复读取（2026-11-26，需求冻结）

本节对应RFC §R18，仅启动已完整核验、最终结算且现金账务核清的旧记录免重复读取；②③④均为后续未冻结/未实现。不引入wire/schema、容器、函数/API或实现文件决策；这里只冻结同run内存基线的行为合同，不是已实现能力。Pascal已明确批准不再主动轮询该基线的字段修订，取代未实施60秒TTL建议及旧草案永久不可修订/逐轮全字段修订检测前提；不声明远端所有字段永不变化。

### R18.1 输入、输出与 scope

启动资格及后续解释缺失历史token时所需的逻辑输入如下；复用原事实类型/状态，不宣称已有一个新基线结构，也不要求新增finality证明字段：

| 输入 | 完备要求 / 用途 |
|---|---|
| 绑定上下文 | 同进程及冻结run、account（含chain、账户模式/地址）、deployment/资产/合约route；换scope不得继承资格，跨重启不恢复。普通策略轮次/generation不是scope变化 |
| 启动历史 | 原声明订单/hash及完整执行/费用/账务、Final闭合与已证明净贡献、market ID、有序YES/NO token pair、目标token/side；声明或本地Closed不等于已证明。只包含原启动核验成功覆盖的旧记录 |
| 启动官方结算 | 原严格market/category完整round事实：币种/300s轮次/strike/provider、起止价格、oracle/trading/outcome状态、争议标志、payout及原round身份；沿原Confirmed及0/0.5/1精确兑付规则，不由文件存在或状态字符串推定 |
| 启动已核清账务 | 原完整账户/历史/官方结果消费者已成功接受的逐token解释及现金核验：`explain_positions_mode`、正claim的`claimed_cash_matches`，以及`seed_predict`的完整性/身份/持仓一致性、精确预算现金与原账户baseline输入。须指向同一成功启动输入；不得只以总现金拟合替代订单净贡献/官方结果/到账解释；零兑付沿原解释不造现金 |
| 当前观察 | 原完整分页/账务/余额/positions/open orders/全量账户matches/新执行及费用、当前receipt/generation、当前已观测新事实/矛盾；这些仍实际fresh读取，不从基线生成 |

判定结果仅有三种行为（非新公开枚举）：

- 允许复用：原启动完整核验已成功、该旧记录结算/现金账务已核清，同scope/目标且当前读无不一致/已知冲突；免其旧订单详情与官方market/category解释重读，保留原净贡献/结算及到账解释，不能据此重记收益或代替当前账户事实。
- 不具资格/不适用：非启动基线成员、启动未核清、输入不全或当前新事实使旧解释不再适用，走原必要严格证明及typed失败。未发布/争议/未到账不能补旧成功；读取失败绝不stale-if-error。真正换scope/重启须重新完整启动核验，不从旧文件恢复资格。
- 已知矛盾：当前读取或原消费者已发现结果/身份/数量等冲突时沿原硬停，保留预占/风险/旧证据；不得覆盖后重试或把冲突降为miss。已有硬stop永不被基线命中撤销。

最小scope覆盖同一冻结run内的连续完整账户观察，策略进入下一BTC5m市场仍复用相同旧历史目标；不同market不得混用。基线仅内存且成员固定为启动已核清历史，本run新增记录不纳入；持久化、跨run/账户/进程共享不在范围。一次观察内去重不算完成。

### R18.2 资格、失效及新事实发现

对历史目标i，`startup_qualified_i = startup_full_audit_succeeded AND startup_history_member_i AND order_final_accounting_complete_i AND strict_official_confirmed_i AND baseline_metadata_qualified_i AND settlement_cash_cleared_i AND startup_identity_route_bound_i AND no_known_conflict_i`；`eligible_i = startup_qualified_i AND same_run_account_deployment_route_i AND same_market_ordered_pair_token_side_net_contribution_i AND current_observation_complete AND no_observed_inconsistency_i AND no_known_conflict_i`。各谓词仅取上述原消费者实际成功输入/当前完整读的可计算真值，未知不当true；不再含远端字段永久不可修订或轮询全部修订源的条件。这里的完整round/provider是新增的“免重复读取资格”，不是对原启动准入或通用结算器的新拒绝条件：只允许实际已读的CRYPTO_UP_DOWN、BTCUSDT、CHAINLINK、完整起止时间且相差300秒、合法起止价格及原Confirmed共同满足者加入基线。仅这些附加元数据缺失/不适用/不匹配时，该历史目标不加入基线，保留原严格读取和原启动结果；可提交空或部分合格成员集。不得仅因此把原本positions_explained=true改成false或让启动硬拒绝；原身份/账务/官方结果冲突、未到账及原必要检查失败仍原样拒绝。原双fresh/审计全部成功后才可使用资格，任一启动必要检查失败不得部分激活；复用原事实状态，不新建资格平台。

1. 仅启动已核清旧记录的订单净贡献及结算/到账解释可复用；原双fresh/完整审计不使用尚未生效的历史基线跳读。当前余额/gas/allowance、positions、open orders、全量账户matches、新执行/费用、未结算/未到账claim仍fresh，原10s与失败预算不变。当前receipt/generation绑定实际当前采集，历史输入保留原观察语义，不伪造为新观察。
2. 同run内符合资格的旧历史，不按tick、固定60秒或其他TTL重读订单详情和官方market/category，无后台刷新。普通跨策略市场、当前generation推进或缓存访问不失效整批基线；不靠每tick全miss回到原读取来逃避降耗验收。
3. matches每次仍从第一页走完原完整分页，未知hash/token、净贡献/费用变化、持仓重现/数量不等及身份/route变化不能被基线遮蔽，受影响解释转原必要证明。未知历史仍原`RECONCILIATION_REQUIRED:UNEXPLAINED_HISTORY`；缺页/读失败不得当零或“无新事实”。已有`history_proven`仅是净贡献复用，不独立授予本项结算/到账资格，也不要求重做已验证的原记忆化。
4. 已观测结果修订、round/token/side或数量/route矛盾立即沿原`FACT_CONFLICT`或原typed硬保护；保留旧证据与风险，不覆盖/吞错。基线不主动检测远端未读到的字段修订或重组，不设检测时限承诺，不伪称“没有修订”；若原当前读取确已观测矛盾则不可忽略。没有资格是原严格读取/原失败，不伪造冲突；已知冲突也不能当普通miss。
5. 启动已核清claim留在原账户baseline，正claim不重复入账；零兑付不造现金，半兑付与±1atom拒绝不变。本run claim继续原exact_floor_mul/atoms、库存和现金核销；未到账仍CASH_PENDING/原不完整，不得以基线认定cash_complete。`account/runtime_claims.rs`中本run bound claim及`settle_controlled_live`/`revised_result`原路径、本run结果发布后的fresh账户/现金核验不改；不改变本轮Final轮询或通用`settlement_market`。
6. 跨重启/换run/换account/deployment/资产route不恢复资格，重新走原启动完整核验；旧proof/运行证据不改写。本地Closed、声明、空仓、总现金拟合、旧文件、REST终态或等待时长均不能替代资格公式。无TTL/服务/DB/WebSocket/finality平台，原fixed deadline、120秒读失败预算、sticky stop、未知提交保护及业务签名/交易阈值不变。

### R18.3 可计算成本与验收口径

同输入的一次启动后成功完整账户观察，以原消费者实际route计数定义：`C_base = C_shared + Σ(H_i + L_i)`，`C_new = C_shared + Σ(不复用目标的H_i + L_i) + V + D`。H_i为旧订单详情在原路径实际发生的普通REST次数（已有history_proven命中时为0），L_i为旧官方market/category解释实际次数；C_shared为当前账户等不变路径中实际计入普通REST桶的请求；账户matches仍全分页扫描，其交易桶请求另列，不混入该普通REST公式。V为本项资格/不适用检查新增普通REST，D为本项其他新增普通REST，互斥归因。正常合法基线目标后续H_i/L_i请求须为0，不能以新验证请求等价补回；净节省`C_base-C_new`必须为正，不能只报hit。启动完整核验成本单列并纳入连续观察总量对照，不冒充已省；分页/冷认证/不具资格/已观测冲突或失败路径另列，RPC及其它服务请求也单列，不混当Predict REST。

既有调查单页热历史模型中H_i=0、C_shared=2、11个独立market均L_i=2；24→2和5秒情景288→24/min仅在全部启动合格、V=D=0时成立，是引用的条件需求模型，非本卡新计算/实测或生产HTTP总量。旧保存的5条claimed_win/6条settled_zero不直接认证资格。必须用原启动成功输入形成可命中正例、证明后续实际少读；保留全部原请求、全miss或同观察去重不能签收，不把已有history_proven收益当本项新增。

### R18.4 原消费者必需验收（Design细化，Implement/独立Validate执行，本卡未运行）

| 编号 | 输入 / 原消费者 | 验收要求与反例 |
|---|---|---|
| D18-01 | 同一synthetic transport下原PredictFun adapter→account reader→Broker，原启动成功后至少两次独立完整观察，覆盖跨tick/下一market/generation及超过60秒 | 对照原路径与候选逐route计数：启动双fresh/审计仍实际执行，只有全部成功才生效；合格旧目标后续订单详情及官方market/category请求为0，普通REST净减少，跨60秒不刷新。启动/新增验证/RPC成本单列；全miss、同次去重、只测helper或公式均不通过；11目标情景逐目标说明资格，不能追认旧真实文件 |
| D18-02 | 原历史订单Final/完整执行账务→严格market/category→round/token/side→启动精确现金核验 | 赢/零/半兑付均须原完整成功输入及合格元数据才能成为基线；原缺必要字段/争议/未发布/未Final/账务缺失/未到账/±1atom/原pair或结果矛盾仍原拒绝或不完整。仅新增免读所需provider/feed/variant/时间元数据不合格时，不入基线但不强化启动或原官方判定，保留原成功/失败与后续严格读取；空/部分合格集提交不得冒充实际降耗，完整BTC5正例另测命中。不因启动必要失败部分生效。不凭Closed/声明/空仓/总现金拟合/文件存在命中；双fresh任一必要失败不准使用基线跳读 |
| D18-03 | 合法基线后的未轮询远端字段变化，与当前实际读到的结果/身份/数量/route矛盾分别注入 | 前者不新增旧结果请求、不声称检测或据此伪造冲突；后者必须原硬停并保留旧证据/风险/sticky stop，不覆盖或降为miss。无资格对象严格读取失败仍typed失败、不stale-if-error；本run官方结果读取中的revised_result反例保持 |
| D18-04 | 原全分页matches/positions/账户/执行读：新foreign hash/token、净贡献/费用变化、持仓重现/数量不等、缺页及失败；重启/换run/account/deployment/route | matches从第一页走完分页，异常历史及原失败码保留；当前变化不得被hit遮蔽，须原必要证明/冲突保护。真正scope变化不继承资格且重走原启动完整核验；普通market/generation推进不使全部基线退回重读。当前余额/开放订单/新执行仍实际fresh |
| D18-05 | 原claim/现金核销→账本/原producer→严格reader | 启动赢/零/半兑付账务与重复观察一致，旧现金/收益不重复入账；本run两种R16到账顺序、结果发布后fresh现金读、错净量/±1atom/未到账反例仍沿原路径。不把本run新增/未核清记录纳入启动基线，不仅mock claimed_win绕过原适配器证据链 |
| D18-06 | 原paper/live结算与账户/发送保护；原tracing或必要synthetic route计数 | 不改本run Closed+Accepted sync/Final、settle_controlled_live/revised_result及通用settlement_market；原fixed deadline/120秒读失败预算/10s freshness/阈值/sticky stop/未知提交保护不变。无新客户端/TTL/后台刷新/服务/DB/WebSocket/配额平台，不改旧proof；仅离线fixture/transport，不运行真实或模拟交易，不读真实API/账户/凭据。不以离线计数冒充生产配额或历史HTTP总量 |

### R18.5 决策闭合与最小阶段输入

本项需求已冻结，无未决语义输入：资格以原启动完整核验/最终结算/现金核清成功为依据，运行期明确不再主动轮询该历史基线的字段修订。公开文档不提升为合约审计结论；没有永久不可修订证明不再构成门禁，也不要求Design发明TTL/确认数或finality平台。未轮询远端变更的不可见性是已接受边界，不伪称仍逐轮检测全部旧字段。原始proof、旧运行/拒绝及研究事实保留，不追认历史验证。

下一阶段只需以本节及RFC §R18为输入，围绕原启动成功账户baseline和历史缺仓解释选择最小接缝、绑定/失效方法、精确allowlist与D18-01–06离线正反例；本节不抢写Design方法。本卡完成不自动解除既有Design行政HOLD，主控须先核两份V1.17独立文件/条款一致性，再放Design；实现、独立Validate及主控Closeout尚未完成，后项②③④继续未冻结/未实现。

## 发送前保守 edge 预检与候选级拒绝增补（2026-11-25，Pascal明确授权）

本节为用户本次“两个事情一并优化，由主控接手”的窄行为增补，优先于历史将所有SIGNED_BOUND_UNPROVEN笼统硬停的表述，不重开R17/结算/接管工程，不修改最坏资金或份额证明。分开“证明缺失/矛盾”与“已证明约束下经济性不合格”。本节不是已测试或生产放行结论。

1. 仅受控PredictFun live候选进入原下单准备时，在本候选RESERVE/sign/POST之前，用已有冻结gross数量Q、候选fee_rate_bps、candidate.fair、候选限价下原reservation现金A与原min_edge，按最终保守检查相同整数公式预检。N_min=Q-floor(Q*b/10000)；V=floor(N_min*fair)沿原exact_floor_mul；所需利润原子量沿原cash_at_limit_atoms(Q,min_edge)。仅V-A>=所需利润才继续；经济性不通过跳过候选、无attempt/预占/签名/POST，不停止窗口。预检是原live Broker准入，不修改共享core/paper模型输出及初筛fee模型，也不保证之后账户/时效/真实签名检查通过。
2. 原guard所有身份/hash/数量/fee/route/签名/receipt/generation/风险检查必须先通过；已证明且正的N_min下，仅经济性不合格、阶段仍为发送许可前的Candidate且原attempt仍Prepared/NotSubmitted时，使用原typed CandidateRefused/封闭INPUT_CHANGED，诊断保留EDGE_BELOW_MIN。沿原release_not_submitted仅释放自身预占、保留hash/tombstone及审计，清本候选，不stop、不takeover，下一原tick产生新candidate再评估；不重试旧candidate。
3. 在Window/send-permit或may-have-submitted/unknown/已发阶段，不扩大软拒绝；无法证明bound、零/非法数量、fee/route/identity/hash不符、算术或取时错误、账户异常、ACK/输出/父失联、loss latch等继续原硬保护。不能仅凭NOT_SUBMITTED或字符串包含edge把其他错误降级。不撤销已有stop，不重启旧run。
4. 共享小函数只复用已存在的minimum_net_shares/exact_floor_mul/cash_at_limit_atoms整数规则，预检和最终guard共用经济性判断；费率签名域原cap、min_edge=0.03、min_secs_left=30、10s新鲜度、预算/敞口/损失阈值、allowance、R17等待/Final、结算及接管均不改。
5. 原生回归分别证明：真实core合格但保守不足的历史参数候选在原Broker预检0sign/POST/RESERVE且运行继续；原guard已准备场景的纯经济性拒绝为typed候选级，Window/真实无证明仍硬错；拒绝后同一Broker/adapter/core下一新候选正常单次fake POST，旧候选不可复用。保留等号/±1atom、零数量/坏费率/身份/bound/未知发送反例，并通过原producer→Python严格reader消费。公式回算不是native RED；必须先原生RED再GREEN。

实现限定BOT原controlled.rs（小经济性helper）、taker.rs（仅准备前预检）、live_control.rs（仅已证明经济性分级）、原live004_regression.rs回归。必要原fixture最小参数化可用tests.rs/controlled/r16_fixture.rs，不新增平台/runner/schema。live_control.rs已1201–2400受控，本次仅替换原check_locked分支、职责不增，不继续堆无关逻辑；共享算法放controlled.rs以保持父职责。两binary重建至本主题新candidate-edge目录，旧制品不覆盖；原control selector及signer reader pin机械绑定、完整source身份新冻结。原shell/生产activation/guard不改，代码绑定不等于启动许可。本次Light Implement→独立Validate，0open才能离线签收，无真实账户/交易/生产写。

## R17：完整 accepted 执行事实的有界等待（2026-11-24）

本节仅实现RFC §R17，优先于旧R14补注中“所有在飞零成交一律120s”的解释。R16/冷历史/接管已实现，不重做旧Draft缺口或旧Gate；其账务、现金600s、unknown、Final、身份/额度及授权保持。事实及未取得的历史raw status/链状态见RFC §R17.1；本节为待实施合同，不是业务测试结果。

R5 t_74460a41原任务/验收将UNKNOWN与0合并为120s到点停机，完整零成交与真正缺失的区别当时未冻结；本节补足该生命周期语义，不追认旧实现违约、不归因今天launcher/reader，不重开旧卡。详细Git/时间来源见根因报告§6及RFC §R17.1。

### R17.1 唯一准入与事实分类

仅显式controlled PredictFun live启用；旧venue默认不提供lifetime便不获新宽限。正常pending须同时满足：

- 当前run恰一个未闭合且可能已提交的attempt；其记录及本次snapshot均Submission::Accepted，原accepted venue_order_id非空且精确匹配、signed_hash合法且同原bound、账户/chain/market/token/side/local_attempt及原requested/签名amount约束全部一致。Unknown、多owner、未知提交不进入正常pending。
- 必须是本次真实execution读取，完整分页、`gross_q_before == gross_q_after == accounting_gross_q == quantity.gross_q`，五现金/费用/库存项KNOWN且各覆盖当前gross_q；`accounting_complete()`及原apply/累计单调/费用/net/风险检查通过。零成交vwap沿原N/A语义，不强造价格。不能仅凭旧watermark、旧完整读或重复generation推断当前健康；重复旧generation不重置任何时钟或清真实失败。
- expiry来自该attempt原签名bound，正整数Unix seconds、可表示为UTC且checked毫秒算术不溢出，所有绑定一致；首次正常pending时尚未到该expiry。缺失、坏值、错hash/identity、无法证实归属不获宽限；错误沿原类型硬停，单纯不支持/缺expiry沿原unread预算，不推now+300、不回填AttemptRecord或改全仓构造器。

OPEN→Accepted/Open，FILLED/CANCELLED/EXPIRED/INVALIDATED按原submission/closure映射；未识别status→Unknown/Unproven，不能因历史accepted而覆盖本次Unknown。零/部分成交、Closure::Open或Unproven可在完整事实与上述准入下观察；不把FILLED部分量或终态文本直接Final。已有部分成交仍经原累计增量/费用/net/mark/generation路径，不能因gross_q>0就停止跟踪非Final订单；完整Final路径保持原判定，不强制所有成交等到expiry。

### R17.2 固定双时钟算法（唯一预算口径）

时间单位为毫秒；E为已验证签名expiration换算UTC毫秒。B为原UNREAD_FACTS_BUDGET=120s（生产120000ms；原测试参数可缩短，不改公开配置）。首次满足§R17.1时在原phase1.clock取得W0=(utc,elapsed_ms)，冻结完整逻辑键及E；记：

`remaining = checked(E - W0.utc)`（首次须>0）；`P_m = checked(W0.elapsed_ms + remaining)`；`T_w = checked(E + B)`；`T_m = checked(P_m + B)`。

这些值持有于原run内同attempt的等待元数据，跨helper返回/下一tick保留，不是每次调用的Instant。pending有效阶段为 `now.utc < E && now.elapsed_ms < P_m`；任一先到进入尾查，尾查结束锚点仍为T_w/T_m，不是在发现到期的now再加120s。最终有界条件为 `now.utc < min(T_w,deadline_at) && now.elapsed_ms < min(T_m,run_deadline_elapsed_ms)`；任一等号或超过不再恢复/新增风险。市场300s轮次结束不是E，MARKET_ORDER_TTL_SECS=300只解释原签名，不参与重建等待寿命。

每次tick、read前后、准备恢复及停止观察检查原双时钟。elapsed须包含暂停（现有SystemClock/CLOCK_BOOTTIME）；wall或elapsed相对上一读回退、取时失败、算术溢出均沿原DATA_UNAVAILABLE/时钟fail-closed路径，不夹0、不重锚。进程调度暂停至边界外，恢复即判超界，不能再补一段尾查；wall前跳可更早终止，wall回拨不能延长。成功读、重复快照、部分/晚到成交、generation变化、换市场、临时读失败与恢复均不重置W0/E/P_m/T_w/T_m；同一逻辑键不得删除后重建以续命。仅实际Final及原恢复条件成立后才清本次等待；硬stop/超界保留耗尽事实，原final收尾不能重新给它600s或120s恢复额度。进程重启不复用elapsed原点，仍走现行冷启动/人工接管，不新增恢复存储。

真正缺失/Unknown仍以首次该连续缺失起点U0计原120s双时钟上限；真正execution读取失败仍走R14 Execution failure streak及原120s，不因订单有较晚expiry而暂停。重入helper不能重置U0；收到新的、当前完整且绑定正确的成功读才可按原规则清对应失败，不清W0。连续缺失/读失败截止、T_w/T_m、原deadline/硬stop取更早者；交替正常pending与短故障不会延长固定生命周期。完整成功但矛盾不是“暂时失败”，立即沿原冲突保护；原已有硬停缺失分支不改成宽限。无expiry的旧venue/旧fixture保留原预算及拒绝语义，不授予推测性生命周期。

### R17.3 控制流、Final及终止优先

- 在原Broker/drive内观察：每个原poll tick仍sync同hash execution、原账户/必要mark/官方结果；候选被拒触发的re_read也消费同一份元数据，不能只从unread筛掉零成交后不轮询。正常pending不是RunControl硬stop或CASH_PENDING，`must_end`不因合法pending为true，但`may_add_risk=false`；各清失败/刷新风险分支也不得意外打开风险。无新RESERVE/sign/POST/补单/自动cancel，不创建第二runner或状态机。只中断只读future，不丢弃可能提交的发送future，不跨await持State锁或递归获取operation lane。
- 当前读先沿原consume_snapshot/apply/事件/账务消费。释放仍只由原Actual Final且完整分页/quantity/费用/net路径执行，normal pending和时间到期自身不释放；partial已证实支出按原账本应用，未用剩余预占不因等待释放。Final后风险/mark/receipt/generation/账户不完整仍不得恢复。清等待后下一原tick重采输入，经同DecisionCore/预算/ACK/最终许可；不对旧candidate续发。
- 每次观察先判已有硬stop、父/输出/loss/identity冲突、原deadline及已耗尽预算；与Final同tick时先关新增，Final可如实补事实，不撤销硬stop。deadline沿DEADLINE、真实读失败耗尽沿原READ_UNAVAILABLE/DATA_UNAVAILABLE、未知提交沿原保护；生命周期尾查耗尽仍无Final沿FACT_INCOMPLETE并接管，禁止新stop reason。FINAL不完整时预占/风险保留，不能因exit0标COMPLETE。
- 原ChainRead::closed不放松：完整FILLED且q=requested可闭合；否则必须认可终态FILLED/CANCELLED/EXPIRED/INVALIDATED，再有固定链块timestamp严格大于签名expiry，或同路由filled-or-cancelled/nonce失效。OPEN及未知status即使本机已过expiry仍不算Final；本机时钟决定“等多久”，固定区块证据决定“可否关闭”，两者不混用。
- 本次只允许原日志诊断，封闭字段为 `venue_status`=OPEN/FILLED/CANCELLED/EXPIRED/INVALIDATED/UNRECOGNIZED、`expiration`=验证后的Unix seconds或null、`block_time`=该次固定块Unix seconds十进制字符串或null、`closure_branch`=FILLED_COMPLETE/SIGNED_EXPIRY/CHAIN_CLOSED/NONCE_INVALID/STATUS_UNPROVEN/STILL_EXECUTABLE/READ_UNAVAILABLE；判定顺序严格复用上述原分支，非新增资金状态。既有log framing/长度/脱敏继续有效，无raw自由文本、签名、JWT、URL/body，无新event_kind、wire键、reason或sink；没有读到的值明确null，不造历史status。

### R17.4 必需回归（后续离线执行，非本卡已测）

| 编号 | 真实消费者路径 / 输入 | 必须证明及反例 |
|---|---|---|
| D17-01 | fake双时钟+native PredictFunTrader/account reader→原Broker/sync/resolve→drive；重放ledger的两组accepted/market_end/expiry/stop时点 | 在121.792/123.679s与各自107/105次完整零读取不误stop，持续同hash原读取；不是硬编码OPEN假称历史raw status，而是分别注入受支持status假设并明示 |
| D17-02 | 签名300s/缺失120s；E前/等号/后、E+120s前/等号/后，原deadline更早/同tick；晚调度至尾查外 | 正常完整零跨120s仍观察；尾查不从醒来时间起算，等号无风险恢复；成功读/重复generation/换轮/暂停/双时钟任一先到/回拨/缺clock均不能重置上界 |
| D17-03 | 实际REST双读/matches分页/chain固定块→真实Final/原producer/严格writer与reader→同run下一新轮fake执行器 | expiry后仍OPEN/UNRECOGNIZED、q部分FILLED、只有本机过期、只有零持仓均非自动Final；除原FILLED完整量分支外，链timestamp==E且无其它关闭证明仍不Final；认可终态+timestamp>E或原链/nonce证明才关闭。Final+当前账户/risk/mark/generation合法才可续轮，旧attempt sign/POST恰一次、无cancel/补余量 |
| D17-04 | 当前完整零→partial/晚到fill→Final，重复/旧generation、费用页缺失、数量变化、1atom差/overfill/错身份 | 原累计账务一次应用、净风险与预占规则不变；partial未Final不释放剩余/不新单；Unknown/缺分页/缺五项/错误hash或venue ID/坏缺expiry/多个owner不得宽限，真正缺失/连续失败120s仍stop，完整成功矛盾立即硬stop |
| D17-05 | pending先到与硬stop先到、读中deadline/loss/父EOF/control/output、与Final同tick | 无一被pending遮蔽，第一硬stop保留；终止后Final仅补事实，不能恢复；read可中断且无死锁/热循环，读失败成功仅清对应failure，不清生命周期 |
| D17-06 | 生产原有tracing→既有脱敏stderr/log边界；native producer→原first writer/reader；paper/live真实共同账务/结算/风险消费者配对 | 状态分类未知为UNRECOGNIZED、expiry/block_time缺则null、关闭分支准确，注入自由敏感status/错误不泄露；wire及旧合法流不变，paper/其它venue行为不变，R16现金/冷历史/旧接管不退化 |

每项至少由实际native适配器和原Broker/drive组合提供关键正反例，不以fake OrderVenue helper单测替代；fake仅transport/clock/订单签名替身，拒绝真实网络/凭据/账户/DB。最终候选身份与受影响回归由独立Validate记录在既有卡及其授权证据位置，本卡不新建报告或路径门禁。实现文件/G3及原测试保全见Design §R17.3/5；本卡业务测试、构建、生产/模拟运行均NOT_EXECUTED。

## R16：本轮生效增量（2026-11-23）

本节优先于下文同题旧条款和旧阶段叙述；仅替代 WAIT_CASH 立即结束、只接历史 claimed_win 的缺口及“精确回收仍不能在同 run 继续”的解释。F-008/MANUAL_PAUSE 仍禁止自动资金动作，不禁止人工/场馆既有机制回收经证明后在原风险窗口继续。已有 R14 读失败降级与 R15 提速、R13 局部核销/reader 清除均是保留基线，不是重建任务。完整事实/定位与证据限度见 RFC §R16.1；本节全部为待 Design/实现/独立 Validate 的合同，非完成声明。

### R16.1 范围与基线协调

BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`，下文 src/、tools/ 相对 BOT。两处已复核的真实缺口是 `src/bot/runtime/live_control.rs::RunControl::must_end` → `paper.rs::wait_controlled_stop` → `runtime.rs::drive` 对 WaitCash 立即 finish/return，以及 `src/service/predict_fun/account.rs::reconcile_account_history` 跳过 bound_orders 而 `src/bot/runtime/live.rs::claimed_payouts` 仅消费 snapshot.claimed_win。只接通这些缺口及 R15 三 minor/必要诊断，不重写账本、settlement core 或交易框架。

不变项：单笔金额、min_edge/min_secs_left、盘口/账户10s新鲜度及原 spot 规则、预算/allowance/敞口/止损、签名/ACK/首次发送原子门、identity/generation/unknown 保护。无自动 redeem/SELL/提款/approve、冷启动恢复、deadline延长或其他 stop/loss 解锁。paper 只复用现有纯规则作配对，不为 parity 改其账本。Pascal 2026-11-23 仅授权研发/离线验证；生产选择器、activation/签名授权、真实或模拟交易执行、网络账户/凭据/链上动作、生产DB/屏障/调度写入均不在本轮。mark_time 投影及暂时 generation INCOMPLETE 不扩成独立专题。

### R16.2 拒绝分类与兼容诊断

| 事实类别（说明口径，非新增 wire 枚举） | 判断依据 | 风险与归因 |
|---|---|---|
| 正常无机会/经济拒绝 | 原 decision 的 phase/reason/两侧诊断，未产生可提交候选 | 0新增风险；不是运行故障或交易所拒单 |
| 本地门禁拒绝 | attempt 可证明仍 NOT_SUBMITTED；原 candidate/guard/bound/账户/ACK 等分支拒绝 | 原候选级拒绝继续窗口，硬安全门按原语义终止；仅明确未发且无未决事实才释放本 attempt 未用预占，不影响其他风险 |
| 交易所终态拒单 | 确有发送且权威答复映射原 RejectedFinal/REJECTED_FINAL、终态和零成交/核算完备 | 不把 INPUT_CHANGED 或 HTTP status 单独当交易所终态；原闭合条件满足才释放 |
| 提交未知 | 已可能发送，timeout/401/坏响应/断线不能证明未提交或权威终态 | 保留同 hash/tombstone/保守预占，原同 hash 查询，无重新签名/POST；诊断不得将 Unknown 降成 NOT_SUBMITTED |

沿 `btc5m-controlled-live.v1` 的既有 order payload 增加唯一可空键 `diagnostic`，不增加 event_kind 或 reason。旧流缺键仅在内存规范化为 null，不回写；decision 继续原07-005诊断，不给无 attempt 的拒绝编造 order。新 producer 对本轮可达的失败分支提供有类型诊断；旧流的空值只能解释为 UNKNOWN，不能倒推 run018 各次拒绝原因。首次 writer、typed producer、关系校验及 canonical reader 必须同步支持封闭对象；老 reader 不保证能消费新可选字段，新 reader 必须消费原合法旧流，不以忽略未知键实现兼容。

diagnostic 非 null 时恰含下列键；没有自由 error/raw/body、额外账户详情、URL、密钥或签名字节：

| 键 | 类型 / 约束 | 来源与语义 |
|---|---|---|
| stage | enum PREPARE / SIGNED_BOUND / FACTS / ACK / SEND_PERMIT / POST | 实际发生拒绝或完成校验的边界；不是猜测的最后成功步骤 |
| detail | 封闭安全码 enum | 下述实际分支映射，不能由异常文本解析/拼接 |
| checked_at / checked_elapsed_ms | 既有 timestamp / 非负拒bool整数 | 本次检查的同一 CheckTime，elapsed 同本 run 原点 |
| tick_started_elapsed_ms | 非负拒bool整数/null | 本 tick 首次账户采集请求发起时的 elapsed；不从事件 wall 推测；拿不到为 null |
| book_receipt_age_ms / spot_receipt_age_ms / account_receipt_age_ms | 非负拒bool整数/null | 在 checked_at 按双时钟计算的各 receipt age，三者不得混成一个 age |
| book_request_age_ms / spot_request_age_ms | 非负拒bool整数/null | 各原始 request age，另列而不拿 receipt age 替代实际 freshness gate |

detail 允许集：NONE、UNKNOWN、BOOK_STALE、SPOT_STALE、ACCOUNT_STALE、FROZEN_INPUT、LIMIT_PRICE、DEPTH、ROUND_TOO_LATE、EDGE_BELOW_MIN、EMPTY_BOOK、ACCOUNT_INCOMPLETE、IDENTITY_MISMATCH、GENERATION_MISMATCH、ATTEMPT_MISMATCH、SIGNED_BOUND_UNPROVEN、RUN_STOPPED、ACK_UNAVAILABLE、READ_UNAVAILABLE、VENUE_REJECTED、SUBMISSION_UNKNOWN。NONE 仅检查成功；未被已知分支覆盖为 UNKNOWN。已有 core 的精确拒绝分支应映射到对应 detail；不得把所有 INPUT_CHANGED 归为 STALE。具体映射由 Design 逐分支列出，不准改变 guard 原求值/错误优先级、硬停与候选拒绝之分。以上只属诊断词汇，不进入 stop reason 集合；原 reason/diagnostic_reason 原字节与判定保持不变。

各 age=max(checked.wall−receipt或request.wall, checked.elapsed−receipt或request.elapsed)，两者都非负才有效；时钟倒退/缺时钟为 null，不截成0、不新增放行。新鲜度仍由原两时钟 guard 判定；account receipt 不代表链块时间，REST receipt 不代表上游 event time。诊断在原检查中取值、后沿原事件管道发出；SEND_PERMIT 成功时仅捕获固定大小的值，交给首次 POST 之前不得新增阻塞 I/O/日志确认/网络等待。身份/hash/account 故障仍按原 fail-closed，不因诊断字段可空而放行。

### R16.3 ≤5s 目标与 R15 三 minor 闭合

精确测量定义：T0=同一 drive tick 首次账户采集请求发起（前移账户读之前）；Tb=该候选决策实际使用的原盘口校验 receipt；Tp=签名及耐久 ACK 完成后、原子发送许可内最后一次校验完成、紧邻首次 transport handoff 前。主目标 `tick_to_send_permit_ms=Tp.elapsed−T0.elapsed <= 5000`；并列 `book_receipt_to_send_permit_ms=Tp.elapsed−Tb.elapsed`，不包括交易所响应耗时。拒绝在 Tr 发生时只报告 `tick_to_refusal_ms=Tr−T0`，不得伪造 Tp；在最后许可再次被拒时，Tp 不算成功发送样本。Tp 后的 transport handoff/POST 响应另按原 trace 留证，不能把网络答复叫 final check。

同次成功/拒绝应关联 candidate/attempt 与 §R16.2 的检查点，book/spot/account receipt age 三列、spot/book request age 两列，保留 null/缺测计数。≤5s是性能目标，不是新发送阈值；原10s门禁不得放宽。新报告列全部样本的 n、成功/本地拒绝/unknown 分组、p50/p95（nearest-rank）、max、输入/候选身份、RTT模型与冷/热历史条件；样本不足仅报告实测，不新增交易笔数或收益门槛。真实 PredictFun/BSC 目标环境测量 NOT_EXECUTED，必须另授权；合成/重放不签生产达标。

| R15 遗留 | 必须闭合的最小结果 | 不可接受的替代 |
|---|---|---|
| before JSON 重复 key/旧标签 | 新输出递归拒重复键、统一 measurement revision/指标定义/单位；同探针、同fixture、同RTT/次数及声明的冷/热历史条件才标直接可比。旧 before 原字节不改，标 NON_COMPARABLE；可复现的基线才另存新证据，否则只撤回旧直接比较并报告新候选绝对值 | 默默用 last-key-wins 修旧 JSON；拿 R14 生产13.8s与R15合成2.234s作前后比；为基线 checkout/reset/stash 共享树 |
| positions-first 缓存依赖 | 保留并发可证明独立的腿，history 在 lookup 所需 market 绑定可用后才能消费；增加“declared hash 不在 matches、market 仅 positions 提供且 positions 被延迟”的冷缓存反例与热缓存对照 | 靠调度偶然顺序、全局预热、catch 后放行或删除历史读取/未知 hash 检查 |
| balances/authorize 双故障优先级 | 有可注入 authorize 失败的离线 fixture；断言余额读取失败优先，其次可读但不足余额/零gas→原 INSUFFICIENT_FUNDS，再其次余额足够→authorize 原失败；每种0签名/0POST，受影响 preparation 竞争也按原顺序 | 只代码审查、只测单故障、因另一路成功而忽略失败或改变 reason |

R15 上游独立 PASS 与3 minor原结论保留；本轮逐项用新证据关闭，不回写历史卡。当前 `send_timing_bench.rs::book_to_facts_us` 截在 facts（早于 ACK/permit），旧 end_to_end 不含前移账户读，故0.860s/2.234s不能冒充上述主目标。fixture无历史hash意味着缓存收益未计时，必须如实标注；不要求为了显得更快重做已验提速。

### R16.4 精确 claim 归属及核销

1. 唯一主账仍是原 Broker LiveState；在其原锁/operation lane 内消费事实，不持锁跨网络 await。核销逻辑键绑定 `(run_id,risk_window_id,account_identity,attempt_id,signed_hash,market_id,token)` 及所依据 generation；复用已有身份，不把账户余额变化当 claim ID。恰好一个本 run owner 才可核销，错 token/foreign/多 owner歧义不猜归属。attempt须 Closed、execution pages/费用/net完整、剩余预占0；本 run bound_order不能因从历史扫描跳过而失去归属证据，也不能为补它把该单当历史收入重复计。
2. 设 Cb 为已保存 opening baseline 的实际 collateral（不是裸配置 C0），Ib(t)为baseline库存；Dout/Din为baseline后本run已唯一应用的实际交易净现金支出/收入，ΔI(t)为这些交易的实际净库存变化。三者均累计自baseline，明确排除下式单列的claim现金、claim库存移除与零兑付归零Z；故核销后的重复读也不会把claim再计入Din/ΔI。Q_i为本run闭合attempt可归属净份额。官方结果沿原严格 market/token-pair/side/round身份与非争议确认规则，p_i仅0、0.5、1，`P_i=floor(Q_i × payout_millionths / 1_000_000)`按原atoms乘除/溢出保护，不能从f64展示值反算；该floor是原兑付规则而非允许±1atom容差。
3. 对已核销集合 A 和本次拟核销集合 N，要求所有 i 的同token库存移除量精确等于Q_i、拟入现金精确等于P_i，且在同一完整、同身份、当前generation的账户读回中同时成立：`Cobs = Cb + Din − Dout + Σ(i∈A∪N)P_i`；`Iobs(t) = Ib(t) + ΔI(t) − Σ(i∈A∪N,token_i=t)Q_i − Z(t)`。Z(t)仅原已证明零兑付份额归零量，不含正claim且不产生现金；所有token分别比较，不跨token相抵。持仓/挂单完整分页、链/账户身份和原history新未声明hash检查继续有效。startup历史claim已纳入Cb，不再次加Σ；不能用 `C0+claims` 代替runtime已发生支出的全量等式。确认一组有多个claim时必须各自唯一归属，不靠总金额相等省略逐项核对。
4. “余额增加”或“positions空”单项均不构成入账；必须有原适配器/账户消费者的同目标库存与官方兑付证据，再用上述全量等式核对。外来现金无本run归属、错token、仍持有份额、差1atom、未闭合费用/generation或无法解释的额外风险一律不恢复；不能设置 positions_explained=true 来跳过证明。startup历史证明与runtime本run证明须分责，现有 ClaimedWin 的历史C0解释不能冒充本run现金证明。不新增资金工具调用/第二客户端/自动链上操作。
5. 官方结果先被runtime确认而账户现金未到：记录CASH_PENDING、保留K/claim与风险，继续有界读；现金及库存证据先被账户适配器读到、runtime结果尚未消费：仅保留pending evidence，不增加B/实现收益，立即按§R16.5进入同一WAIT_CASH并从首次该证据起计时、0新增风险，等原官方结果消费者确认后用同一核销条件再判。此“现金先到”不是官方未确认时凭余额猜结果；适配器能提供官方证明但runtime尚未消费是可覆盖顺序，两个消费者都缺结果时证据仍未知，不伪造ClaimedWin。不得让同一可归属pending证据在先后两次检查间被丢弃或误当foreign而提前终止；generation改变须新完整读回重证，不能拿旧pending绕过当前generation保护；真正无法解释的变化沿原reconciliation拒绝。
6. 重复官方结果、重复快照、同一claim再次出现只核销一次，旧generation不能回退；相同键不同Q/P是冲突，不冲销重入账。仅在完整读回、官方结果及等式都通过后原子提交claims/K/B/R变动，发一次有cash_received_atoms的CASH_CONFIRMED，canonical reader也仅应用一次；任一失败不部分记现金。若多个claim尚待回收，已证实项可以入账，但不得清除整个等待；reconciliation、payout和下一次RESERVE的序列由Design绑定到真实producer→writer→reader，不依赖手拼JSON。
7. 恢复前还须：无剩余经济持仓（零兑付链上残余单列）、无open/removing/unknown/inflight、预占0、当前generation/费用/账户完整且receipt仍新鲜；所有正claim闭合；无其他终止/loss/degraded，原deadline未到。核销成功不是直接POST许可：废弃旧candidate、重新采集输入并经原 DecisionCore、预算、签名、ACK及最终发送门。保留同轮tombstone，不补已成交余量。cash_complete只在全体必要现金事实闭合时为真。
8. 这是原账户事实模型内的精确归属，不冒称链上逐tx资金来源审计：若已有事实提示外部流或归属歧义，必须拒绝，不能用等式掩盖。观察上完全相同的外部转移/入金与兑付无法仅靠余额证明来源，不能宣称能识别任意抵消的外部流；真实运行仍继承账户独占约束。以后若要求此类链上provenance，需要另行授权数据/接口，不在本轮偷加RPC或资金动作。

### R16.5 WAIT_CASH 有界等待与原 drive 恢复

- 触发：原官方结果消费者对本run闭合净库存确认正claim且未核销，或账户适配器先提供同目标官方正兑付/库存移除/精确现金证据、但runtime结果尚未消费，二者任一先出现即READY→WAIT_CASH；后者只暂存pending evidence，不加B。若已存在不可恢复stop则不把它改成WAIT_CASH。首次进入记录原同一CheckTime W0及该批待回收身份，0新增风险；runtime后来消费结果、结果重复、部分核销/读成功或失败、轮次变化不重置W0。
- 独立等待预算：逻辑 `CASH_WAIT_BUDGET=600s`，复用现行 `live_accounting.rs::LIVE_TAIL_BUDGET` 的600s只读上限，不修改该既有常量；不是 `READ_FAILURE_BUDGET=120s`，也不复用读失败计数。有效等待仅在 `now.utc < min(W0.utc+600s,deadline_at)` 且 `now.elapsed_ms < min(W0.elapsed_ms+600000,原run经过时钟deadline)` 时成立，任一先到/等号即不得恢复；双时钟缺失/倒退不能延长窗口。W0仅在本轮等待完整清除时移除，未来另一轮真实新claim可另建等待，但总run deadline永不重设。
- 等待动作：`may_add_risk=false`，无新RESERVE/签名/POST；原drive按已有poll/settlement读取节奏继续账户/同hash执行/官方结果观察及原必要mark，不新建定时服务、不热循环。`must_end`/`wait_controlled_stop`不得只因可等待的WaitCash立即触发finish；不能只改must_end后仍由is_halted或entry_stop提前return，也不能在等待时跑出有资金副作用的策略路径。读操作保留原请求超时；等待截止/父EOF/控制及输出故障须能中断等待，不以长await延后发送关门。
- 清除：仅§R16.4全部通过且硬终止条件未出现，清除这一CASH_PENDING等待与其临时停新增标记；记CASH_CONFIRMED后继续同run原drive，直到新的合法轮次实际到原fake执行器，不能只断言内存Ready。恢复后输入、receipt/generation均重新证明，fresh receipt不免原检查。
- 终止优先：人工stop、原deadline、loss latch、父失联/控制/输出故障、unknown/事实冲突、读失败耗尽原预算或现金等待耗尽，立即取消恢复资格，走原有界安全收尾/final/return。CASH_PENDING是可撤销等待而非可遮蔽后续硬停的首因；后到硬stop作为新的既有stop事件保留、reader也锁住，历史CASH_PENDING不删除。终止首因仍按既有优先/先到规则保留；即使后来CASH_CONFIRMED可如实入账，也不解除硬stop或loss、不再RESERVE。`DATA_UNAVAILABLE→CASH_PENDING→CASH_CONFIRMED`与反向先现金等待后硬stop两种都必须锁住后续新增。
- 等待耗尽仍有pending：复用现有CASH_PENDING及takeover_required，final现金不完整；不新增“恢复成功”或stop reason来遮盖缺口。恰好在600s/deadline边界才读到精确到账，也只能消费事实/安全收尾，不能恢复。原deadline优先记录DEADLINE；已有更早硬stop不改。等待期间的瞬时Read/Execution/Valuation失败沿R14各自120s降级计数，成功只清对应失败，不能清cash wait；已成功读但账实冲突不是瞬时读失败，不能借120s或600s豁免。
- 收尾仍沿原30s清理/既有只读尾查，不因等待重新给现金恢复计时或再次开放风险；同一现金等待从W0到只读尾查也不重置600s额度。截止后缺必要事实如实INCOMPLETE/接管，无自动重启、redeem/SELL/提款/approve或清屏障。600s选择沿用已批准只读上限、避免新增数值/配置，不是到账SLA；真实延迟分布NOT_VERIFIED，run018的5.407s单例不用于推定分位数。

### R16.6 本轮可证伪验收矩阵与证据

本矩阵增量补充A-001–A-024；仅离线fake clock/transport，无凭据/网络账户/生产写入。下述是后续必须执行的覆盖，不是已存在测试名或本卡PASS。

| 编号 | 必需消费者/正例 | 反例 / 完成标准 |
|---|---|---|
| D16-01 | 原decision正常无机会；真实guard各可达拒绝→order诊断→首次writer→reader | stale book/spot/account分别、非过期INPUT_CHANGED的limit/depth/edge/round、identity/generation/ACK各分支；原reason/求值优先级不变，禁止自由文本/秘密/未知键/重复键，旧流缺diagnostic可读 |
| D16-02 | 明确未发本地拒绝后下一合法轮可继续，预占仅释放该attempt | 未发新增风险0；权威RejectedFinal与Unknown分开，timeout/401/坏响应不当未发、不释放unknown、不二次POST；硬安全拒绝仍硬停 |
| D16-03 | 新同版探针严格JSON、主目标T0→Tp及Tb→Tp、receipt/request age分列；冷/热历史有标记 | 旧before不可比显式声明，缺测计数；Tp含ACK/最终原子检查，end_to_end不漏账户采集；合成/重放不得签生产≤5s |
| D16-04 | positions-only market、declared hash不在matches，延迟positions且冷缓存→完整账户读；热缓存对照 | 不因history抢跑lookup误拒；新未声明hash仍拒绝；保留闭合记忆化/完整分页与错误优先级 |
| D16-05 | balances/authorize双故障注入，逐项固定§R16.3顺序 | 余额读失败、余额可读但不足/零gas、余额足够且authorize失败；0签名/0POST，原失败码不变 |
| D16-06 | 真实适配器账户/官方事实投影→runtime精确核销→producer→严格writer→reader→原drive：结果先到、现金后到 | 等待中0新增、drive未finish；精确到账后CASH_CONFIRMED且同run下一新轮实际到fake执行器，不补旧轮；非仅直接调用credit_claim |
| D16-07 | 反向顺序：账户适配器先证明现金/同token移除，runtime官方结果延迟；多claim分批到 | 确认前不加B/不解等候，不误foreign停死；最后结果到且全体闭合才一次恢复；一项未闭合不恢复 |
| D16-08 | 重复账户/官方/claim、旧generation重放及startup历史claim与本run claim同流 | Q或P差1atom、错market/token/side、foreign/外来现金、持仓未移除、未知owner/多owner、额外挂单/inflight/费用缺口/读页不全均不恢复；重复不重复B/R/收益，历史现金不算本run收益；零兑付/官方DRAW按原atoms规则 |
| D16-09 | fake双时钟测试W0+600s前/等号/后、原deadline更早、暂停与回拨；等待中短暂读失败后成功 | 不重置W0或延长deadline；读失败120s耗尽仍终止，成功读不清现金等待；硬stop/loss/父EOF/输出故障先后两序及与到账同tick均不再新增；终止后到账只补事实，final未闭环不假绿 |
| D16-10 | paper/live共同允许输入域，同core规则配对；R13/R14/R15受影响回归与最终候选身份/实际delta | 概率/方向/净EV/纯拒绝同义；live专属账户/现金/真实执行差异有明示，paper账本未改；保护门、历史run/candidate/证据、selector/activation未变；不把上游dirty按mtime算本卡越界 |

新唯一正式验收报告为 `data/reports/2026-11-23-btc5m-r16-integrated-validation/report.md`，原始证据放其 `evidence/`，新文件create-new不覆盖历史；取代下文针对初版的旧报告路径作为本轮输出位置。临时探针只用当前profile scratch，不建data/tasks或任务状态镜像。各项记录最终候选HEAD+实际delta/hash、原生argv/cwd/exit、来源/输入/运行条件与未验证项；旧独立证据仅在身份/输入仍适用时复用。Design给最小精确文件/符号/wire/reader映射、G3与离线命令，不能把这些任务再写成全平台待办；未同步Design不进入Implement。

本T1只改独立RFC/SPEC两文件并实际做静态实体/版本/互引/契约/scoped diff-check；Design只读。R16业务测试、真实环境延迟及claim分布、生产部署/选择器/activation/签名授权、真实/模拟交易和资金动作均NOT_EXECUTED；不重写R15旧卡PASS或自动解锁/归档旧blocked/triage。

## 既有生效契约：公开 run JSON 参数化（2026-11-22）

来源：t_298e36df 与 Pascal 本轮已授权 Light 决定。下文旧 100/2/2、98/1/1/10/20 及历史算术、FAIL、原始 bytes 均保留为历史示例；本节替代其“唯一合法数值”含义，不追认旧运行。新入口显式要求 `controlled_run={budget_usdt,duration_seconds,operations_mode}`，资金仅复用 `strategies.btc_arb.order_usd` 和 `strategies.limits.{max_order_usd,max_market_usd,max_total_usd,max_loss_usd}`。缺省时旧 paper/legacy/replay 行为不变；同一候选 binary 与通用 launcher 从一份公开 JSON 冻结全 run 参数及 config SHA，不从账户现金自动推预算，不换 config 复用 activation。

参数关系为 target≤order≤market≤total≤budget；各金额必须有限、正数、非 bool、无溢出，最多六位 USDT 小数且≤1,000,000,000 USDT（限定到微 USDT，保证现有 f64 DecisionCore 输入的公开十进制往返唯一；风险 atoms 从原始 JSON 数字 token 精确解析，不从 f64 反算；budget_usdt 另可为≤18 位小数的十进制字符串（按 atoms 精确映射，不截断、不四舍五入、不容差），使 C0 能逐 atoms 等于观察到的 collateral，其余金额仍限六位小数）。loss 独立为正，不要求 loss<exposure；原 0.5 USDT dust floor 保留，不自动缩单。当前公开示例 budget=97、target/order/market=1、total=10、loss=20、duration=86400、unattended，仅示例。预算 B=C0+R−K、NAV=C0+net_pnl 的 C0 与 loss/各 cap 全部取本 run 冻结值，原账户现金单独保留。实际 exposure≥total 沿原黏性停止，不重启。

新 controller 从配置 duration 生成 deadline；若显式 CLI deadline/mode 存在须相同否则拒绝。native options/run/context/runtime 与现有双时钟一致；supervised 0<duration≤21600、unattended≤86400，旧 unsigned 6/72h 与旧 signed 6h 不变。started/final/ended 与严格 reader 使用同份 frozen 配置，禁止通过任意预算常数放宽检查；旧 run007..011 只读兼容、不回写。

定向消费者：config.StrictJson/load_controlled → native options → Broker LiveState；arbitrage 原 order_usd→DecisionCore target→attempt；live.seed_predict 预算准入；taker 预占/可用额/check_caps；live_control FINAL_SEND/total stop；live_accounting project_window 预算与 loss；Python control 固定值/started/deadline 与 live_events 首写、关系索引、ended/reader。超大文件仅原位接线，参数解析与新测试放小模块，不扩既有 tests.rs；本次修改仍须由独立 reviewer Validate。

Canonical `tools/predictfun/btc5m_launch.py` 仅机械归位获准旧 wrapper 步骤，复用 control/live_guard/reconcile 事实及 lazy PortfolioMongoLoader。import/参数检查/默认预检无执行副作用。run/window/auth、声明订单 hashes、精确旧 ARMED 目标显式输入；完整新鲜≤900s、同账户/config 的 reconcile、positions/history、无挂单、外部流及 gas、现金≥budget 的资格检查先于 activation 改动、旧 ARMED 轮换、arm、秘密读取及 child。失败上述副作用为零；成功仍需显式执行授权；精确匹配一条旧 ARMED、不通配删除、不重试，保存旧记录及 activation 原 bytes。原 child 再核账户/预算；本轮仅 fake collection/activation/child 离线验证。

## 1. 需求摘要

显式 07-007 候选使 signed live 与 unsigned paper 共用既有 phase1_net_shares DecisionCore，原 Broker/venue 负责真实执行，不给 live 创建 PaperCash。输出新分版、严格白名单的 live 决策/订单/实际净额/风险/结束证据；旧 signed-null 输出不能证明本轮能力。有人策略 pilot 和无人单次运行共享经济/执行不变量，无人额外覆盖单实例、异常停手和拒绝冷启动。跨重启自动恢复及自动连续复投不在本轮；首次需要人工赎回时停新增，资金读回由原 SDK/人工承接。

## 2. 范围与增量优先级

### 2.1 三类矩阵和事实来源

[RFC §2](../../rfc/07_trading/RFC-07-007-btc5m-live-parity-and-operations.md)的“已验离线基线 / 真实工程缺口 / 生产授权缺口”三矩阵为本 SPEC 的分类依据。BOT=`skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits`；下列路径相对 BOT。

| 当前接缝 | 已有、不得重建 | 本轮必要差量 |
|---|---|---|
| src/bot/arbitrage.rs:69–73；arbitrage/phase1.rs | 唯一 DecisionCore、source/clock/EV/候选 | 显式策略契约与执行模式解耦，沿原 RoundTaker 接 live |
| src/bot/runtime/paper.rs:641–673,880–952 | phase1 时钟/事件/候选当前依赖 paper | 分离必要运行元数据，原 Broker live 薄适配；不是把 paper 撮合迁给 live |
| src/bot/runtime.rs:624–766；runtime/live.rs | attempts、tombstone、实际执行应用及 unknown 闭锁 | final-send guard、真实状态投影及窗口/停新增集成 |
| src/service/venue.rs；predict_fun/fills.rs:95–208 | snapshot/原子量、签名hash、单次POST/账户/权限/签名检查 | 现有适配器最后可能发送前调用同候选检查和耐久证据屏障；保持真实回执语义 |
| tools/predictfun/btc5m_control.py:957–1064,1565–1703 | 固定child、环境、监督、首次过滤、signed接线 | 显式live协议/值守选择、关键事实确认、互斥/冷启动拒绝与审计消费 |
| tools/predictfun/local_signer.py、cli.py、sdk_ops.py | 已有 keyring / lazy FD / 主网API / 资金工具 | 默认不改，只复用；仅直接必要兼容才可在T2逐文件证明 |

不是逐文件实现授权。T2 须把保留项与真实差量分开，给精确新增/修改路径、类型/字段映射、G3、动态加载隔离、离线命令。源码单位/行为与旧文档不一致时以当前源码和仍适用的独立证据为先，不重复修旧 unknown→planned finding。

### 2.2 有限替代、兼容与禁止

仅显式 07-007 候选替代旧 07-005 的 signed 不启 phase1、07-004/005 的 signed final-only/null、07-002/004 的无跨进程保护边界；只扩到本契约的单实例和拒绝冷启动，不冒称自动恢复。旧历史语义/FAIL 保留，不批量回写旧文档/事件。

默认普通 paper/live、其他策略/venue、replay/1、history、07-006 unsigned-only observer 和已运行 paper 不变；旧 v1/v2 仍只读按原版本解释。保留所有原安全 signer、RPC/身份/账户/预算/分页/去重保护，不因 phase1 标签或人在场绕过。混合模型/动量/OBI/alpha优化、主动退出策略、第二 core/Broker/OMS/runner、自动重签/补单/解锁、跨主机互斥、生产 DB/schema/依赖/服务/调度/profile/权限/commit/push 均排除。

本卡仅新增 RFC/SPEC，静态阅读和检查，不写 Design/业务代码/配置/数据库，不启动任何业务。本轮后续工程也只离线 synthetic/fake；真实认证、私有API/链上刷新、真实签名/订单/撤单/资金、外部告警及上线均另授权。

## 3. 功能规格与授权矩阵

| 编号 | 必须行为 | 失败边界 |
|---|---|---|
| F-001 | 显式 contract=phase1_net_shares；execution 与 operations_mode 独立 | 缺 opt-in 保持旧行为；不得旧 signed-null 冒新候选 |
| F-002 | 同 core 候选经济与提交前重验 | 裸 phase1 BUY、无上下文、过期/换源/身份变更不发送 |
| F-003 | 原实际 snapshot 记账、未知保留风险 | 不能拿计划量/模型费/订单status充实际净额 |
| F-004 | 严格 live 事件与真实消费者审计 | 坏事件首次落盘前拒绝；重要输出失败停新增、不假绿 |
| F-005 | 固定风险窗口、现金/预占/浮亏/费用分责 | 换run/换日/重启不清loss；未知不零填 |
| F-006 | 单host同账户单实例、拒绝冷启动 | 抢锁/屏障耐久失败不取signer、不启child；新run_id不能绕过 |
| F-007 | 故障停手与人工接管 | 不自动重启/重签/解锁/改salt，告警失败仍停手 |
| F-008 | MANUAL_PAUSE 资金回收 | 账面settled不回现金；WAIT_CASH停新增，无自动approve/redeem |

| 动作 / 验收层 | 当前T1 | 后续离线Implement/Validate | 以后有人值守真实动作 | 以后无人值守真实动作 |
|---|---|---|---|---|
| 文档、静态检查 | 仅本两文件 | 按阶段allowlist | 不自动需要改文档 | 不自动需要改文档 |
| 原消费者fake、合成子进程 | 不执行 | 允许，凭据/业务网络调用即失败 | 不是实际结果 | 不是实际结果 |
| 真实auth/账户/余额/RPC查询 | 禁止 | 禁止 | 明确目标/时间的只读授权后 | 同左，另含完整就绪/接管核对 |
| 签名、下单、撤单、卖出、approve、redeem | 禁止 | 禁止 | 各动作/额度/次数/期限/退出明确，外部执行及风控确认 | 同左；人在场通过不自动授予无人模式 |
| 自动重启/补单/新salt/清latch | 禁止 | 仅负例证明禁止 | 禁止 | 禁止 |
| 外部告警、生产Mongo/schema、长期调度 | 禁止 | 禁止，只fake接收者/存储 | 另具体授权 | 另具体授权；不能把本地事件说成已通知 |

## 4. 行为、数据与接口契约

以下是新增逻辑合同，不声称源码已有同名类型/API。T2 只决定内部签名、wire同义分组、CLI拼写和文件落点，不重选经济、恢复或授权语义。

### 4.1 模式、准入与风险窗口身份

- execution_mode=UNSIGNED_PAPER / SIGNED_LIVE；operations_mode=SUPERVISED / UNATTENDED。新live仍由原 signed-future-live 固定入口显式选择新契约，不另建runner；不能通过旧config或enable_trading隐式升级。
- 新候选 started 必须绑定：schema_version、strategy_contract、operations_mode、run_id、risk_window_id、固定 account_identity、候选binary/源文件/公开配置SHA、授权引用 authorization_ref、started_at/deadline_at、recovery_policy=COLD_START_REFUSE、cash_recovery_policy=MANUAL_PAUSE。authorization_ref是公开工程关联，不是凭据或自动审批token。
- account_identity 仅 {venue:PREDICT_FUN,chain_id:56,account_mode:predict-account,trading_address,signer_address}，继续07-003固定绑定，不能用signer当持仓账户。地址先严格0x+40hex，再按原绑定比较。run_id沿原受控格式；risk_window_id/authorization_ref沿同受控公开ID语法，不接受任意文本/路径。
- window覆盖一次已批准实验而非一进程/自然日；受控 run 的 C0 取本 run 配置冻结的分配预算（legacy 缺省 98 USDT，`live_accounting.rs` 的 `BUDGET_C0_USDT=98` 为历史常量；`live.rs` 的 `seed_predict` 中 `cash_matches_budget_and_claims(budget, collateral, claim_cash)` 要求观察到的 collateral atoms 与本 run C0 加已核验 claim atoms 逐 atoms 相等——含 claims，不等即 bail `CASH_BUDGET_MISMATCH`，早于任何下单；行号仅辅助（当前约 live.rs:782–788，随字段演进可动），`btc5m_launch.py` preflight 同义），不是凭空写入真实账户。startup完整官方对账及原预算确认通过，证实可用资金后才可在限额内活动。当前无真实预算授权，不给本轮填未来金额/期限/Gas批准。
- 准入先公开模式/版本/固定参数/期限/身份 → 单实例锁与持久拒绝屏障 → 原交易秘密来源/keyring → 单一child → 原完整账户/权限/预算核对 → READY。本文0secret计数指交易私钥/行情API/JWT读取，Mongo自身连接凭据只可由以后获批的明确存储绑定取得，不传child，不全量load_dotenv；测试注入fake存储且两类真实凭据读取都为0。失败不fallback、不自动sign-in/check-venue/approve；无有效监督控制通道的受控live拒绝。
- 当前paper及旧signed入口的原期限不能被新选项改变。新受控 live 的 activation 三入口共用 mode-aware 判定：`supervised` 时 `0 < duration <= 6h`，`unattended` 时 `0 < duration <= 24h`，等号允许、超限及未知 mode 拒绝；不把 unattended 授权扩到 supervised。具体运行仍须有效授权；native options、run/manifest 预算绑定和 runtime validator 同样共用 `OperationsMode::allows_duration` 的 6h/24h 完整精度判断，不用整秒截断放过超限；双UTC/包含暂停的经过时间任一先到即停；工程fixture可推进fake clock，无真实长跑。

### 4.2 phase1 live 经济与最终发送约束

1. 净份额模型/公式完全继承07-005 §4.1：h(p)=bps/10000×min(p,1−p)，q_net=q×(1−h(p)/p)，cost=q×p，EV=q_net×fair−cost，edge=EV/q（USDT/gross share），min_edge=0.03。BUY不再把份额费等值额扣现金；实际费用另来自官方事实，不替换成模型费。Down镜像、同edge选Down、q向下取整、模型/EWMA/20returns/300秒gap/5与10秒时效/30秒边界等不变。
2. common允许输入子域的paper/live同core输出同p_up/候选/净EV/原因；paper可Coinbase降级，signed保留Binance-only。signed遇Coinbase给SOURCE_NOT_ALLOWED，未签名/未POST；不伪称通过相同经济判断就获得相同执行授权。
3. phase1裸BUY缺candidate即CONTEXT_MISSING。唯一候选冻结原07-005身份、revision/source/epoch/clock/fee、q/limit/两侧诊断。live保留EVALUATE与PRE_SUBMIT，额外FINAL_SEND在最后账户/盘口/权限/认证/签名等待及关键证据确认之后、第一次可能POST之前。每次重新取合法CheckTime，以同core重新计算剩余期限/fair/edge并检查输入/期限/stop/loss/data/account gate。不能持Broker锁跨网络await；预占与最终本地check/send许可状态变更须在原原子保护下序列化。
4. 原venue获取的最终book、fee、market/route和签名maker/taker约束必须可与候选核对；不同输入使旧candidate INPUT_CHANGED终结，不能悄悄沿旧fair签新量。若重考虑，只能在尚未可能提交、仍未入场且授权有效时，由原core新attempt重新评估；不是网络重试补单。signed金额必须遵守原限价、净EV及最坏现金/最低净到账约束；不能凭API的isMinAmountOut/slippageBps名字忽略实际已签约束。不能证明则SIGNED_BOUND_UNPROVEN，0POST。2026-11-21轻量纠错：本条“最终book与候选一致”只解释为最终盘口完整且足以支持冻结决策——非空、不越过候选限价、深度覆盖冻结股数；越限或深度不足均为候选级拒绝（释放本候选预占、按NOT_SUBMITTED记录证据、保持窗口，不终结整窗）；身份/hash/ACK/bound/账户/风控不一致仍为硬终止；缺一侧盘口为READ_UNAVAILABLE。其余语义不变。
5. 顺序：候选检查 → 原原子预占 → 原签名及身份校验 → 同hash的order证据经supervisor严格校验且确认耐久 → FINAL_SEND → 原单次POST。关键证据确认失败不发送；确认等待也不能延长freshness/期限。最后检查和交给POST之间不得另做阻塞证据写入/账户请求/等待；必要控制通道由T2复用原管道，不新建服务。终止发生在发送许可前必须0POST，已可能发送的不能靠取消future假装未提交。
6. live无paper PRE_APPLY“拒绝本地模拟成交”语义。POST后实际晚到/部分/负EV/过30秒/到期成交一律按同hash事实入账，即使已经停新增。能取消仅按预批准原cancel流程；不得回滚真实成交取绿灯。
7. 原core只有确认正净fill才confirm_fill；费用/net未知时不捏造净量。原round/intent tombstone从可能发送持续阻止同轮补单；确认正gross但net未知也须账户闭锁，不能因core尚未entered自动再试。部分终态也不补余量。同candidate至多一次初始提交，未知时同hash查询不签名、不广播重发，401/timeout不自动重POST。

### 4.3 实际执行状态：四个维度独立

沿原AttemptPhase/Submission/Quantity/Closure与ExecutionSnapshot，不新造替代OMS。公开投影使用下列固定枚举，原映射由T2按源码逐字段绑定。

| 维度 | 值 / 转移 | 允许与禁止 |
|---|---|---|
| attempt_phase | Prepared → MayHaveSubmitted → Submitted / Closed；Unknown可停在MayHaveSubmitted | hash在可能发送前保留；明确未发才可回收；进程死不当Closed |
| submission | NotSubmitted / RejectedFinal / Accepted / Unknown | HTTP201只是Accepted；异常可能发送即Unknown，不重签 |
| quantity_class | UNKNOWN / ZERO / PARTIAL / FULL | 依据权威实际gross而非净到账或FILLED状态；MARKET部分FILLED仍PARTIAL |
| closure | OPEN / REMOVING / UNPROVEN / FINAL | removalLockedUntil未到、remove accepted、网络错、空列表均不证明FINAL |
| accounting_status | COMPLETE / INCOMPLETE / CONFLICT | quantity已知可核算不全；已知费用0须明确事实；每字段coverage保存 |
| payout_status | UNRESOLVED / CONFIRMED / CONFLICT / CASH_PENDING / CASH_CONFIRMED | 官方结果、链成交settled和赎回到账分别判断；DRAW按官方0.5 |

- 实际Q/C/fees/net依原snapshot完整字段或明确官方映射，按官方ID或完整单调累计coverage去重。generation旧值不回退，矛盾累计/费用修订不自动冲销；partial补齐时只记新覆盖，不重加份额。
- COMPLETE且FINAL时才释放未成交余量；单量全额但费用未知仍占用/停新增。数量完整零且权威不可成交才释放，VWAP=NOT_APPLICABLE，不是0。
- matched、链settled与cash_received各自给可核事实，order_id/signed_hash/tx_hash不能互换。链settled的交易hash不证明用户已redeem。
- 只读查询可有原有界重读/分页；不得新加写操作自动重试。rest受控仍拒绝；意外/继承挂单或撤单竞争保留全部风险，不因本策略不maker就忽略它们。

### 4.4 风险、单位、费用和可用现金

原子量均为十进制ASCII字符串：无符号`0|[1-9][0-9]{0,77}`且≤U256最大值；带符号USDT损益为可选单负号的同义规范整数，禁止−0。ID/hash先格式再比较：market/token沿1..78位十进制ID；signed_hash/tx_hash为0x+64hex。venue_order_id是原API返回的String，不是market/token十进制ID；新公开order-ref类型限定`[A-Za-z0-9_-]{1,128}`，按原字节保留、不得截断/重编码/替换为hash，越界则FACT_INCOMPLETE并保留原signed_hash查询。不用自由响应文本。时间RFC3339显式UTC/offset、毫秒精度，elapsed_ms为拒bool的非负整数；重启不混用经过时钟原点。

- 金额/份额保留asset、decimals与atoms。当前支持部署转换沿原1e18路径，仍须核实metadata一致；缺decimals拒绝，不猜6/18。USDT、BNB、shares不可混加；VWAP/模型价是USDT/gross share，不是持仓成本单价。gross与net原子量严格区分，展示小数不能反馈预算判断。
- 成交实际现金出入用net_cash，份额用net_inventory；额外USDT费只在尚未净额时纳入，份额fee不再从现金/PnL重复扣。累计费是展示项，不从已经净额的NAV再减一次。不同fee币种不支持则INCOMPLETE，不取0。
- 风险窗口C0取本 run 配置冻结的分配预算（legacy 缺省 98 USDT，`live_accounting.rs:32` 为历史常量）；K为该窗口尚未回收成本（含到期未兑付），P为仍可能增加的最坏现金预占。单笔最坏现金（含可能额外现金费）0.5≤w≤1（下限 `live_accounting.rs:30 MIN_ORDER_ATOMS=0.5`，上限 `MAX_ORDER_USDT=1`）、市场K_m+P_m+w≤1、K+P+w≤10（`taker.rs:419–436`、`live_control.rs:386–395`），且足够真实/预算可用现金。原q向下取整后不满足最低金额就拒绝；不提高单笔/市场上限、不改fee公式/参数、不自动缩单凑成功。
- 当前实际敞口 `K+P >= 10 USDT`（含等号）触发既有黏性 stop，沿 graceful cleanup/final 进入原 drive 返回，不空转、不重启；使用既有 `MANUAL_STOP` reason 与安全 `TOTAL_CAP` detail，不新增事件或错误类别。候选 `w` 尚未预占时不计为实际敞口；`K+P<10` 但 `K+P+w>10` 仅拒候选。保留已有 stop、20u loss latch、在飞/未知订单的保守余量、unresolved 和人工接管，退出不等于平仓。
- 预占占用为同单已确认成本+尚未闭合余量，不能把整笔R0和确认成本双算，也不能低于max(R0,已知实际更高风险)。未确认风险不默认为0；实际超预占保留更高实绩并halt，不裁剪。P是B受限部分，不能再从NAV重复扣。
- B为窗口真实已到账现金的预算余额，从本 run C0 开始（legacy 缺省 98；`live_accounting.rs:32` 为历史常量），只按归属已核的实际现金支出/收入变动；真实总账户余额另外读回，不代替B。可用额≤B−P且≤完整账户读回的可支用USDT减未闭合预占；不把未兑付余额当现金。无法解释的入金/提款/其他客户端交易导致RECONCILIATION_REQUIRED，不自动改C0。
- V为净持仓的有效原mark价值与已确认待兑付claim价值之和，同一资产不可同时作share/claim双计。U=V−K；R为已实现净收益；完整、无外部流的窗口满足B=C0+R−K、NAV=B+V、net_pnl=R+U=NAV−C0（legacy 示例 C0=98）。官方已确认零兑付可移除其经济成本并实现损失，链上残余无价值份额仍独立披露；非零claim在现金/烧份额读回前保留成本，不以预计赎回实现现金收益。真实读不全时相关派生值null+原因，不能强套恒等式反推未知余额。
- mark沿原mid与原有效性；不是模型fair/保证清仓价值。浮亏必须计入20阈值。为与原子现金对账，live估值换算按原有效mark保守向下到USDT原子量，注明VALUATION而非链上cash事实；不修改paper模型/mark。loss判断原子量≤−20 USDT含等号，阈值无epsilon；未获得可用mark/完整风险时DATA_UNAVAILABLE停新增，不能用成本/旧mark证明安全。
- loss_latched一旦真，在同窗口永久真；下一tick、结算回升、换日、换run/重启/改配置不得清除。同tick成交/费用/估值/结算后更新以及每个FINAL_SEND前都检查；native费用BNB单列，不把BNB加USDT。gas_status=NOT_MEASURED / KNOWN / UNAVAILABLE，NOT_MEASURED不等于0；KNOWN需同payer/tx/读回依据，归属不明不得乱扣。本方案20只为USDT累计净损失停新增，不包括无转换依据的BNB；真实授权须另给Gas支付者、BNB可用/消费预算及停止条件，缺则不启动。2026-11-21轻量纠错：本支持的Predict Account路径保留原ChainRead不变，Gas payer必须等于固定account_identity.signer_address；trading_address仍为USDT持仓账户和锁/屏障作用域，不能替代Gas payer，不新增任意支付者RPC。无新增模型汇率、无保证总损失/回撤≤20声明。

### 4.5 新live事件、严格白名单与真实消费

新schema_version固定`btc5m-controlled-live.v1`；只在显式07-007 signed候选接受。原BTC5M_EVENT framing/64KiB行界/每数组1000界保留，不能用新schema放宽原v1/v2；每次版本按started绑定，禁止混流。event_seq从1严格递增，无重复倒序/漏号；bad line不先write后清洗。

新envelope仅以下全部必填键，nullable明确存在；payload按kind精确匹配下面字段。不存在自由detail/raw/body/error字典。所有对象递归拒未知键、重复JSON键、NaN/Infinity/bool冒数、非法null/enum/身份/关联。验证成功才提交关系索引/写盘，写盘失败不重试可能资金副作用。

| envelope字段 | 类型 / 可空 | 含义 |
|---|---|---|
| schema_version | 固定string | btc5m-controlled-live.v1 |
| run_id | 原受控ID，非null | started匹配 |
| risk_window_id | 受控ID，非null | 窗口不会因run变化重置 |
| event_seq | positive integer，非null | 本run顺序 |
| event_kind | enum，非null | decision / reservation / order / execution / reconciliation / loss_latch / stop / recovery / payout / final |
| event_time | timestamp，非null | 产生事件时点，不伪装报价/官方事实时间 |
| market_id | id/null | 关联市场时必填，否则null |
| token | id/null | 关联token时必填，否则null |
| accounting | accounting对象，非null | 原Broker风险投影，字段如下；合法未知保留null/status |
| payload | kind严格对象，非null | 下表的字段，不能添加未列内容 |

accounting每个键必有：cash、available、reserved、cost、realized、unrealized、nav、net_pnl为对应USDT原子量字符串/null（后三者及realized允许符号）；loss_latched为bool；status=COMPLETE/INCOMPLETE/CONFLICT；reason为§4.9枚举；mark_time为timestamp/null；pending_claim_value为USDT atoms/null；gas_status沿§4.4；gas_paid_atoms为BNB atoms/null。原始代币shares在execution/positions里，不跨token求和称财富。COMPLETE须关键现金/预占/成本/R/U/NAV均可知且恒等式成立；未知snapshot不能使旧真实K/P消失，reserved至少保留已有保守值。gas未测可不影响USDT恒等式，但不能宣称全币种全成本收益已知。

| kind | payload全部字段 / 类型 | 约束 |
|---|---|---|
| decision | decision:07-005 §4.5同义完整对象 | phase限定EVALUATE/PRE_SUBMIT/FINAL_SEND；strategy_contract固定；FINAL_SEND不叫模拟PRE_APPLY；其他null/clock/两侧诊断沿原合同 |
| reservation | candidate_id:id、attempt_id:id、action:RESERVE/RELEASE、worst_cash_atoms:atoms、remaining_atoms:atoms、reason:enum | 同候选/同attempt；RELEASE仅权威闭合/明确未提交；数值是现金预占不是股份 |
| order | candidate_id:id、attempt_id:id、signed_hash:hash/null、venue_order_id:order-ref/null、attempt_phase:enum、submission:enum、request_gross_atoms:atoms、max_cash_atoms:atoms、min_net_shares_atoms:atoms/null、expires_at:time/null、removal_locked_until:time/null、reason:enum | 签名后hash非空；初始Prepared可无hash；首次可能BUY POST前完整signed bound/hash耐久、min_net_shares非null且>0；lock未知不能当已到期 |
| execution | attempt_id:id、signed_hash:hash、venue_order_id:order-ref/null、generation:positive integer、observed_at:time、pages_complete:bool、quantity_class:enum、gross_q_atoms:atoms/null、accounting_gross_q_atoms:atoms/null、closure:enum、final_gross_q_atoms:atoms/null、facts:对象、delta:对象、tx_hash:hash/null、settlement_status:UNVERIFIED/MATCHED/CHAIN_SETTLED/CONFLICT、settlement_checked_at:time/null、reason:enum | facts/coverage及delta见下文；PARTIAL可FINAL；不能用FILLED补请求量；有tx_hash不等于CHAIN_SETTLED，须同交易receipt及同目标状态证实，否则保留UNVERIFIED/MATCHED，不能暗中增加未授权RPC |
| reconciliation | scope:STARTUP/RUNTIME/HANDOFF、checked_at:time、complete:bool、collateral_atoms:atoms/null、gas_balance_atoms:atoms/null、positions:数组、open_hashes:hash数组、foreign_risk:bool、reason:enum | positions每项仅{market_id:id,token:id,net_shares_atoms:atoms,cost_atoms:atoms/null}；只输出窗口关联最小事实，陌生风险标志而非任意隐私全表；读全成功才complete |
| loss_latch | latched:bool、trigger_net_pnl_atoms:signed atoms/null、reason:enum | latched必须true，不能输出解锁；未知损益停新增不伪造触阈值 |
| stop | stop_new_risk:bool、reason:enum、takeover_required:bool、alert_status:LOCAL_RECORDED/DELIVERED/UNAVAILABLE | stop_new_risk必须true；DELIVERED只用于以后已授权接收者确认，当前fake不得冒外部送达 |
| recovery | policy:COLD_START_REFUSE、state:ARMED/RECONCILIATION_REQUIRED/HANDOFF、reason:enum | 不承载可交易余额/自动reset；与持久屏障关联 |
| payout | status:enum、payout_yes:number/null、position_net_atoms:atoms、claim_value_atoms:atoms/null、cash_received_atoms:atoms/null、tx_hash:hash/null、observed_at:time、reason:enum | payout只取合法官方身份/结果；CASH_CONFIRMED须同目标份额/现金读回；未知保持null |
| final | run_status:COMPLETED/STOPPED/INCOMPLETE、stop_reason:enum、execution_complete:bool、cash_complete:bool、audit_complete:bool、takeover_required:bool、unresolved:数组、positions:数组 | unresolved每项仅{attempt_id:id,signed_hash:hash/null,closure:enum,reserved_atoms:atoms,reason:enum}；positions复用reconciliation结构；完成运行≠无持仓，pending不得假现金闭合 |

2026-11-21轻量纠错：stop与final的payload各增加一个**可空键`stop_detail`**，值为原生代码中已存在的失败码字符串（例如ACCOUNT_LEDGER_MISMATCH、READ_FAILED、LOCAL_ACCOUNTING_UNPROVEN；无诊断时为null；非法/超长值按`UNKNOWN`），仅用于停机归因，不承载自由文本、地址、URL或凭据。对应`ended.json`增加可空键`incomplete_detail`并原样透传该值。其余payload字段、封闭白名单、reason枚举，以及停机/放行判定语义一律不变。

2026-11-22轻量修复补注：旧v1 stop/final缺少`stop_detail`、旧ended缺少`incomplete_detail`时，仅在内存中于精确键校验前补null；其他必需键及未知键仍严格校验，不回写历史、不补造final。私有账户读请求在原边界按ApiError整数status、reqwest/serde_json错误类型安全投影为固定操作标签加既有READ_UNAVAILABLE/FACT_INCOMPLETE码（HTTP另带整数状态，如`POSITIONS_READ_UNAVAILABLE_HTTP_503`）；VenueError原reason及既有短码保留，未知自由文本仍UNKNOWN，不保存body、URL/query或原始stderr，不增诊断sink/重试。该补注不认定历史run006的原始根因。R1修复：账户请求类型投影不保留原始cause；启动及runtime账户检查返回前只保留安全类型code/step/reason或既有短码/UNKNOWN，Debug链、普通日志与持久协议同样不得披露原始错误。

2026-11-22 R2b事实补注：`signed_hash`仅为事件投影口径（`live_events`按hash归属本窗口订单），不参与账户delta放行；`open_orders`放行规则只认`venue_order_id`——仅当恰好一个attempt已ACK、持有`venue_order_id`且未闭合时，列表每一项都必须等于该id才放行，hash命中不足以豁免；启动路径仍对任何非空挂单列表拒绝。

execution.facts恰含gross_cash、collateral_fee、share_fee、net_cash、net_inventory、vwap六键。每值为严格{status:KNOWN/UNKNOWN/NOT_APPLICABLE,atoms:atoms/null,coverage_gross_atoms:atoms/null,reason:enum}；gross_cash/collateral_fee/net_cash单位USDT，share_fee/net_inventory单位该token份额，vwap沿原适配器固定点单位。status=KNOWN必须atoms/coverage非null，UNKNOWN必须atoms=null；NOT_APPLICABLE仅确认零成交的vwap，其atoms=null。coverage来自原snapshot字段覆盖，不从新gross倒推；不足覆盖不得称COMPLETE。

execution.delta恰含gross_q_atoms、gross_cash_atoms、collateral_fee_atoms、share_fee_atoms、net_cash_atoms、net_inventory_atoms，值为本次唯一原Broker实际应用非负增量atoms；核算未全而未应用的字段为null（不是伪已应用0），重复已知快照确认为无新应用才可0。无法从现存状态直接获得的delta须T2给最小类型投影，不在Python重建可交易账。实际币种/decimals由started的asset_units声明，asset_units恰为{collateral_symbol:USDT,collateral_decimals:integer,share_decimals:integer,gas_symbol:BNB,gas_decimals:integer}；与原部署事实不一致启动拒绝。

supervisor关系规则：decision→candidate→reservation→signed order持久确认→FINAL_SEND→最多一次初始submit；一个candidate可有多代execution而非v2一个fill终态；同attempt identity/hash/account不可变，venue_order_id在首次获知后固定。execution累计/coverage矛盾拒绝，晚到真实事实不能因运行deadline过去被过滤掉。reader必须实际从校验后文件读取，逐事件核对actual增量、预占转换、风险和final，不以拼装JSON纯函数替代真实producer链。

正式final至少拆开运行状态、原生child/launcher退出、订单闭合、资金回收和审计完整性。exit0、无新单或收到final不自动PASS；missing final、未知hash/费用、未终结预占、强制清理、writer/reader关系失败必须INCOMPLETE或takeover，不能写completed资金闭环。待官方结果/赎回可正常停止观察，但cash_complete=false；不能把run_status=COMPLETED解释为账户清空。旧signed的LIVE_ACCOUNTING_UNAVAILABLE仍只读保留，不迁移为新COMPLETE。

### 4.6 有人值守/无人值守可用性与故障状态

运行安全状态：STARTING → READY → STOP_NEW_RISK → HANDOFF / ENDED；READY还可→WAIT_CASH→HANDOFF/ENDED。任何STOP_NEW_RISK后本run不回READY；WAIT_CASH是本run内唯一可撤销的等待：只有当账户读回证明的claim与已确认官方结果逐atoms精确相等（同一净份额、同一兑付金额）时，该等待才可清回READY，其余WAIT_CASH（差1 atom、结果未确认、foreign token）仍停窗；该撤销在 wire 上由 payout `CASH_CONFIRMED`（含 `cash_received_atoms`）承载，canonical reader 据此解除同一等待，不得把该 run 随后的 RESERVE/FINAL_SEND 判为 OUTPUT_INVALID；其它原因造成的停窗不因该记录解除；停窗原因首因胜出，`CASH_CONFIRMED` 只撤销由 `CASH_PENDING` 造成的停（后续 payout `CASH_PENDING` 不覆盖已存在的其它停止原因）。临时行情失败的恢复也不解已触发的停止/loss。首次STARTING的确定未发故障可以0订单退出，但不能自动重启一个新run。

| 条件 | 新增风险 | 允许行为 / 不代表什么 |
|---|---|---|
| READY且所有输入/账户/预算/监督/期限通过 | 可经同core候选初始发送 | 离线健康正路径必须能到原执行器，不全拒绝取PASS |
| keyring不可用/locked/需Prompt | 0child/0签名/0POST | 原固定失败，无Unlock/其他key/file fallback |
| 行情/账户/RPC失败、缺页、费用/mark未知 | 停新增，保存已知风险 | 原有界只读对账；不以空列表/零值恢复健康 |
| 提交不明/核算冲突/撤单锁/late fill | 停该资金账户全部新增 | 同hash查询、记实际增量、按既有许可取消；不补余量、不释放至零 |
| loss≤−20或deadline到/人工stop/父失联/控制通道故障 | 立即关闭下一发送许可 | 保留in-flight身份及占用；已有可能发送不冒称已撤销 |
| 关键证据/耐久/确认/协议校验失败 | 停新增，audit不完整 | 不回滚真实状态，不把事件故障降为可丢自由日志 |
| child异常/强制kill/宿主重启 | 无自动child复活；冷启动拒绝 | 屏障+缺结束标异常；锁随进程释放不清屏障 |
| 首个正兑付claim待回收 | WAIT_CASH，0新增 | 原手工SDK/官网另授权后读回；不自动继续复投 |
| 告警不可用 | 停新增，takeover_required=true | 本地固定code/退出/屏障仍可见；不假称已有人收到 |

父死亡/控制EOF时，child须独立停新增，不等下一完整网络tick后还发新单；每次可能POST前重检。停止有界沿原30秒正常清理、超时强制并如实未决；原600秒只读尾查上界不能变成自动live赎回授权，超界保留pending，不能无限等健康。MAX_FAILED_TICKS既有撤报价保留，但它不是允许失败期间继续新增的宽限。T2必须按原停止管道给出精确EOF/超时检测与测试点，不凭空新增心跳数值或无限恢复loop。

SUPERVISED工程首单可一笔加预批准退出，由人核官方回执/账单；不要求先自动赎回或无人全能力。SUPERVISED策略pilot必须本轮phase1和新live审计通过。UNATTENDED额外要求下面单实例/冷启动屏障/故障/接管/WAIT_CASH演练，能力定义为一次有限窗口内的自主健康交易，不是自动跨重启恢复或连续资金循环。未来真实无人验收还须明示告警接收者/响应安排和允许退出；本轮不发送外部消息。

### 4.7 单实例、持久屏障、冷启动与人工恢复

1. OS锁作用域固定(host,venue,chain,trading_address,account_mode)，覆盖全部受控signed run、不同run_id/risk_window_id及两种operations_mode；Mongo拒绝屏障的唯一主键不含host，其他host也不能凭新host绕过同账户已有屏障，但不因此宣称实现分布式自动恢复/完整外部客户端互斥。不能只按策略/runID锁；unsigned paper无wallet不抢live锁。仅保证合作消费者，真实账户须声明无其他host/客户端并行；不宣称恶意同UID隔离。
2. 在原launcher取secret/启动child前取得OS排他锁并持有至child确证退出/风险交接；锁失败即ALREADY_RUNNING。父死但child还活时，不得因仅父FD解锁放行另一个child；持久屏障仍拒绝第二次启动。T2用本机已有OS/标准库能力，禁止新服务/包。
3. 同作用域拒绝屏障默认Mongo逻辑LiveRunGuard，使用固定scope作唯一主键，以一次insert创建ARMED、取得持久写确认并同目标读回后才取signer/启child。依赖复用项目venv既有pymongo，不在BOT专用venv安装包；原launcher同进程lazy调用最小存储接缝，不新增worker/服务。单文档足以表示拒绝屏障，不需要多集合恢复事务。主键不得包含run_id/window以绕过唯一性；必须沿Mongo内建_id唯一约束，不能以先find再普通upsert实现互斥。
4. 屏障写入要求writeConcern={w:majority,j:true}且同primary的majority读回精确匹配scope/版本/原始内容；未确认、超时或读取不全均不启child，不盲重insert。实际既有Mongo部署不能满足时阻断激活，不自行扩服务/改配置；当前只fake验证调用/失败顺序。缺明确批准的连接/库/集合绑定、driver/存储不可用、冲突/损坏/未知版本、写或耐久不明全拒绝，无自动删文档重建、文件/易失内存fallback；不导入会load_dotenv的MongoWriter作为资金存储。
5. 屏障一旦ARMED，正常/异常结束、OS重启、锁释放、日志显示零仓都不自动撤销。另一个新run遇屏障直接RECONCILIATION_REQUIRED，0secret/0child/0POST，不用当前余额/参数或普通budget-confirmation单独覆盖。
6. 人工接管只能在明确授权下，由原账户/订单/资金消费者核对窗口内全部attempt/hash、权威终态及late fill、完整现金/净份额/费用、待兑付、R/U/loss和Gas；丢失hash必须完整官方历史核对，不能“查不到即没下过”。保留原窗口和latch证据，无法解释则继续阻断。
7. 本轮没有自动resume/reset/轮转命令；屏障的人工轮转/新窗口开启是后续具体授权操作，旧屏障原始内容留档，不提供一个bool清loss入口。同窗口若loss已触发，不再启动风险新增；以后新实验须主控明示承接累计风险和新授权，不把换窗口当技术性续命。
8. 独立离线验收要证明：首次无屏障、资金/授权完整的fake可READY并实际触发原fake执行器；随后异常的冷启动必拒；同一健康进程内至少两不同轮合法候选可依次执行。不能只测试全拒绝或把未生产部署的屏障当线上已有。

### 4.8 结算、人工回收与final

严格读取的官方结果仍须同market/token/BTCUSDT/300秒、固定起止价与非争议结果一致；模型/本地spot不结算。启动完整核验或不具R18基线资格的history-only 仓位解释归零前，目标 token 必须明确属于最新官方 Yes/No outcomes，且完整 token 对/侧别与读取前的历史 known 市场绑定一致；同 market id 不足以放行，缺失/替换/互换/重复/额外 outcome 不得默认当 No，拒绝结果不得污染下一次的 known 绑定。复用原 settle_from_facts/settlement_payout，只有 RESOLVED/CLOSED、非 contested 且目标 payout=0 才可解释归零；平局与正兑付只在官方结果已确认、该 token 的 claim 按 inventory×payout（1e6/5e5）逐 atoms 与持仓精确相等、budget+Σclaim 逐 atoms 等于观测 collateral 时才可解释为现金已到账；缺元数据、矛盾、未结算、额外持仓、数量不符或任一 atom 差异仍 fail-closed。启动已完整核清且仍满足R18资格的旧记录在同run后续观察复用其原结算/到账解释，不周期重读旧官方结果、不重计旧现金；本run新claim与当前账户fresh/现金核销不受该豁免影响。不增加请求种类或客户端。DRAW官方0.5只形成相应claim，不保证可卖价或USDT已到账。实际库存烧毁与同笔USDT回读须沿原SDK target/route/receipt，tx hash或success单独不够。

默认MANUAL_PAUSE：首个需要回收的官方正claim即WAIT_CASH并停止新风险，列claim/净份额/成本/未决。可以在已有持仓上完成有界对账，不自动approve/redeem/merge/卖出。人工以后获得具体目标许可后调用原SDK或官网，读回失败保留同hash并停，不重签/重发。claim先判定后入账：账户读回只把claim记为已证明的待兑付，只有当已确认官方结果逐atoms精确等于该claim（同净份额、同兑付金额）时才入账为本run现金并清回READY；差任一atom、结果未确认或token不属于本run时，claim不入账、cash_complete=false、WAIT_CASH继续，reader亦须观察到仍未停窗解除。下一启动服从冷启动人工核对。若只有官方零兑付，按§4.4记经济损失和链上剩余份额，不造赎回现金。

自动连续运行当前NOT_SUPPORTED；资金回收责任明确由指定接管人承接，不能用虚拟paper回款或“人工以后会看”证明自动周转。资金工具既有能力不重建，未来如另批自动回收须明确有限route/target、Gas/失败/原消费者验收，不能隐式approve所有路线。

### 4.9 错误、重试与失败关闭

新协议reason固定集合：NONE、CONTEXT_MISSING、SOURCE_NOT_ALLOWED、INPUT_CHANGED、SIGNED_BOUND_UNPROVEN、ALREADY_RUNNING、RECOVERY_GUARD_UNAVAILABLE、RECONCILIATION_REQUIRED、SUBMISSION_UNKNOWN、FACT_INCOMPLETE、FACT_CONFLICT、ACCOUNT_MISMATCH、READ_UNAVAILABLE、DATA_UNAVAILABLE、OUTPUT_INVALID、AUDIT_UNAVAILABLE、KEYRING_UNAVAILABLE、LOSS_LATCH、DEADLINE、PARENT_LOST、CONTROL_CHANNEL、MANUAL_STOP、PROCESS_FAILED、CASH_PENDING、CASH_READBACK_UNAVAILABLE、GAS_UNAVAILABLE、GAS_BUDGET、NOT_APPLICABLE。decision.reason保留07-005完整原枚举，不混成此reason；原Broker正常资金/深度拒绝沿diagnostic_reason=BROKER_BLOCKED及其已冻结枚举，T2做显式穷举映射，不放开任意error字符串。

公开参数/身份/依赖缺失在可能发送前拒绝；命令非零，只有明确未提交才可报告NO_SIDE_EFFECT。签名/POST/撤单/赎回可能发生后，不报“绝未执行”，保留关联和未知。查询重读复用原有界政策；写动作只有一次初始尝试，不自动重签、同hash广播重发、新salt补余量或清loss。stdout/stderr/异常仅稳定code/step/reason及允许公开身份，不传raw异常、URL、HTTP body、JWT/API/signature/环境/秘密摘要。

## 4.bis 持久化与兼容契约

默认业务恢复存储方向Mongo；已核项目venv有pymongo 4.17.0/eth-account 0.14.0/jeepney 0.9.0，BOT专用venv无pymongo；不能直接套用MongoWriter/UD缓存的理由见RFC §4。当前选择Mongo单文档拒绝屏障+COLD_START_REFUSE，不是自动恢复/SQLite或第二可交易账本。T2冻结原BOT内的精确存储接缝、逻辑字段映射、OS锁路径和项目解释器兼容；实际部署绑定写成明确待批准的database/collection，不假称已存在，不自动创建生产集合/索引，不在工程测试连接生产Mongo。

| 对象 | 单字段 / 规则 | 类型 / 必填 | 来源 / 生命周期 / 隐私 |
|---|---|---|---|
| Mongo逻辑LiveRunGuard | _id | scope的规范唯一键，是 | venue/chain/trading_address/account_mode；不得含run/window/host以规避同账户唯一；Mongo内建唯一索引，不新建索引；L1 |
| 同上 | schema_version | 固定btc5m-live-guard/1，是 | 创建后保留，无TTL/自动删除；L1 |
| 同上 | scope | account_identity + 初始host公开受控标识，是 | 固定账户为唯一主键来源，host仅原始归属；不可用户随意换存储绑定；L1 |
| 同上 | risk_window_id | 受控ID，是 | 初次窗口引用；后续窗口遇原屏障仍拒绝；L1 |
| 同上 | run_id | 受控ID，是 | 初次启动关联，不作为锁作用域；L1 |
| 同上 | state | 固定ARMED，是 | 不靠退出写CLEAN自动解锁；L1 |
| 同上 | armed_at | UTC timestamp，是 | 在secret/child前实际生成；L1 |
| 同上 | authorization_ref | 受控ID，是 | 非审批token；L1 |
| 同上 | candidate_digest | 64hex SHA，是 | 仅公开binary/源代码/公共配置身份，不含秘密摘要；L1 |
| 同上 | durability | majority+j写确认及primary majority读回 | 行为要求 | 不用文档里的true自证耐久；写超时不重insert，存储异常不取signer/启child |
| OS锁 | 唯一作用域/持有 | 非持久金融字段 | 单host合作消费者互斥；进程释放不删除屏障 |
| 新started.json | schema_version | 固定live版本，是 | exclusive-create新run；L1 |
| 同上 | strategy_contract | 固定phase1_net_shares，是 | 无默认升级；L1 |
| 同上 | operations_mode | SUPERVISED/UNATTENDED，是 | 绑定本次授权；L1 |
| 同上 | risk_window_id | 受控ID，是 | 不按run/日期重置；L1 |
| 同上 | account_identity | §4.1严格对象，是 | 固定身份；L1 |
| 同上 | authorization_ref | 受控ID，是 | 非秘密；L1 |
| 同上 | recovery_policy | COLD_START_REFUSE，是 | 不能advertise自动恢复；L1 |
| 同上 | cash_recovery_policy | MANUAL_PAUSE，是 | 明示无自动连续复投；L1 |
| 同上 | asset_units | §4.5严格对象，是 | 来源原部署事实；L1 |
| 同上 | run_id | 受控ID，是 | 原格式；L1 |
| 同上 | started_at | UTC timestamp，是 | 实际启动尝试起点；L1 |
| 同上 | deadline_at | UTC timestamp，是 | 未来授权固定值，等待不延长；L1 |
| 同上 | candidate_identity | 原公开文件/binary SHA对象，是 | 不复制环境/凭据；L1 |
| 同上 | public_config_identity | 原公开配置SHA及固定参数，是 | 98/1/1/10/20和原模型参数；L1 |
| 新events.jsonl | 每字段/关系 | §4.5逐字段，是 | 校验后追加，关键订单发送前耐久确认；L1，行情L0关联后按L1 |
| 新ended.json | schema_version | 与started一致，是 | 原生退出后独立创建，不覆盖；L1 |
| 同上 | run_id | 受控ID，是 | 与started一致；L1 |
| 同上 | exit_facts | 原launcher/child native exit、signal、forced_cleanup、stop_reason，是 | 不以外层exit0覆盖child失败；L1 |
| 同上 | final_event_seq | integer/null，是 | 真实已写final序号，缺为null；L1 |
| 同上 | final_accounting | §4.5 accounting/null，是 | 真实投影，不补造；L1 |
| 同上 | incomplete_reason | §4.9 reason/null，是 | 不完整必须非null；L1 |
| 同上 | execution_complete | bool，是 | 未决不得真；L1 |
| 同上 | cash_complete | bool，是 | pending claim不得真；L1 |
| 同上 | audit_complete | bool，是 | 坏/缺事件不得真；L1 |
| 同上 | takeover_required | bool，是 | 必需接管显式；L1 |
| 新stop-output.json | schema_version/run_id | 固定btc5m-stop-output/1及受控ID，是 | 真实OUTPUT_INVALID停机的触发片段记录，create-new一次性；L1 |
| 同上 | stream/bytes/newline_terminated | stdout/stderr、原始字节数、原始是否以换行结束，是 | 原片段元数据，不改写原文；L1 |
| 同上 | truncated/text | bool及按形状脱敏后最多2048字符，是 | 秘密名值/Bearer/带凭据URI/裸64hex替换为脱敏标记；L1 |
| 同上 | occurred_at/child_returncode | UTC timestamp及int/null，是 | 与ended同源的停机时刻和原生退出事实；L1 |

`stop-output.json`只在停机原因本身是`OUTPUT_INVALID`（EOF残留、超长行、stderr行三类真实触发，或store拒绝该行）时create-new一次，写在该run的`ended.json`之前。模糊审计I/O失败既不写该文件也不写`ended.json`，`stop_reason`保持原样；其他停机原因之后到达的尾部输出不写该文件、也不改变`stop_reason`，该run仍按原原因正常写`ended.json`。

所有新证据文件保留原字节、屏障保留原始内容，无TTL/自动压缩/删除/迁移/覆写/上传，旧v1/v2只读不补字段。人工轮转屏障需另明确授权并留证据；本轮无生产DB DDL/DML/schema/索引和真实部署。秘密仅原keyring/内存/匿名FD，L3禁止入事件/屏障/报告；Mongo连接秘密不传child/事件，不记录RPC敏感URL/签名字节/API/JWT/完整账户原响应。OS/同UID/管理员、存储物理耐久/人为删除不是本方案可保证隔离；必要Mongo确认/本地审计文件耐久不满足即拒绝，不降级临时目录或其他数据库。

## 5. 可证伪验收矩阵

以下为未来Implement自测及独立Validate要求，本卡未运行业务测试。全部synthetic/fake clock/transport/隔离子进程；业务网络、生产keyring/.env/真实signer/DB调用即失败。不是要求先真实成交才能离线PASS。

| 编号 | 正例 / 必需路径 | 负例 / 必须结果 |
|---|---|---|
| A-001 | 同DecisionCore/同有效Binance输入/clock，原paper和新live候选逐字段对拍概率/两侧fee/净EV/选择/原因/epoch | 旧cash edge通过净edge不达0.03拒绝；精确阈值和Down同edge规则不变；不是两套公式互测 |
| A-002 | 原真实装配显式07-007到phase1，旧默认回归 | 无opt-in旧行为不变；Coinbase只paper降级，live SOURCE_NOT_ALLOWED且0签名/POST；observer仍unsigned-only |
| A-003 | 真实RoundTaker→Broker→Predict适配器，合法候选健康正路径 | 裸BUY/无context/旧revision、错market/fee/route/q/已签bound不可证，均0POST；不注入PaperCash |
| A-004 | 各await与关键证据确认后FINAL_SEND，30秒/5秒/10秒边界和deadline等号 | 账户/book/auth/sign/ack等待使过期、loss、stop、父EOF后不得POST；输入变化旧candidate终结，不能旧fair签新量 |
| A-005 | accepted→known partial FILLED→terminal partial；官方amount/fee/net/实际VWAP | accepted不满额；只应用实际partial；剩余不补单，费用未知不称COMPLETE；actual late fill越期限仍记账 |
| A-006 | 单hash timeout→query missing→later fill→settled，重复/旧代/fee coverage补齐 | 初始POST最多一次、无新salt/重签/同hash重发；查不到不释放，旧代不回退，冲突停全账户新增；沿原consumer |
| A-007 | Rust实际producer→原supervisor→首次write→reader→final，order前耐久确认 | 手拼JSON纯函数不算；signed-null不能当新账务；同hash、candidate、seq、覆盖均实际关联 |
| A-008 | 原子量/decimals、现金和净份额、费用方向及累计/增量对拍 | NaN/Infinity/bool、缺键/未知键/坏ID/hash/null/enum/递归秘密、未知schema或v1/v2混流均在首次写入前拒绝；不回写坏行 |
| A-009 | 重复快照无新增，迟补费用/net原Broker只应用一次 | 0/unknown/N/A不混；coverage未全不假full；Python不另建余额、模型费用不冒actual，BUY份额费不双扣USDT |
| A-010 | 先持久signed hash再发送，崩溃发生在每个write/ack/FINAL_SEND/POST边界 | 发送前失败0POST；可能发送后缺结果则保留hash/最坏占用/INCOMPLETE；不得补final或假NO_SIDE_EFFECT |
| A-011 | 完整final/原生child与launcher结果；pending与可估值仓位明确 | exit0但漏final/未决/坏关系/强制kill/audit缺口非健康；账面settled但未兑付cash_complete=false |
| A-012 | 同host同账户两operations_mode/不同run/window并发争锁 | 至多一child，一方在secret前ALREADY_RUNNING；unsigned不抢live锁；不声称跨host可保证 |
| A-013 | 现有pymongo薄接缝→fake collection首次唯一insert/majority+j/精确读回→READY；同进程至少两不同轮健康候选原fake执行 | duplicate-key/写或读超时/未确认/坏绑定/版本/身份错误不取signer不启child；不重insert、不自动建集合/索引、不fallback文件，不能只有拒绝stub；本地关键审计fsync失败同样0POST |
| A-014 | 崩溃后新run_id/新window/换日/宿主重启/缺ended均遇原屏障 | 全0secret/child/POST、RECONCILIATION_REQUIRED；OS锁释放/当前余额健康不能清屏障/latch |
| A-015 | 进程内R+U恰−20及邻值、回升/结算/同tick第二单 | ≤−20立即锁，后续回升不解；换run不重置；mark未知先停新增，不能靠旧值/成本/浮亏0；Gas另币种不混 |
| A-016 | 持久屏障+已写事件供人工同账户对账，含无hash窗口不完整 | 普通budget bool/换collection或scope/删屏障/新run不构成恢复许可；未解释hash/损失/持仓仍拒；无自动reset命令 |
| A-017 | fake keyring正常/locked/缺失/Prompt、断网/账户缺页/无mark | 失败停新增，无Unlock/file备用/秘密重读循环；丢数据保留K/P/持仓，绝不作零账户 |
| A-018 | 父EOF/监督失联、child异常、控制/证据输出/告警失败、deadline与inflight竞争 | child下一可能POST前停手；原有界退出/原生exit可见，不自动重启；已可能发单即未知，不能假撤销 |
| A-019 | remove accepted+removalLockedUntil+late fill+最终权威不可成交 | 原cancel/query消费者处理竞争，只终态且核算全才释放；rest/继承风险不能靠cancel_all成功当清零 |
| A-020 | 分别考验真实现金不足/单笔/市场/总额/预占并发及实际风险超R0 | 100真预算非仅报表分母，2/2/10各独立约束，等号可、超额拒；不双算/漏算、不自动升额/缩单。（2026-11-22 口径注：该条冻结的 100/2/2 为旧 1u 前验收事实，保留原文不改写；现行契约见 §4.4——C0=98 USDT、单笔下界 0.5（`live_accounting.rs:30`）且上限 1、单市场 ≤1、总额 ≤10，旧“2/2”单笔/市场额度已被 1/1 取代，等号/超额/不双算等判定语义不变。） |
| A-021 | 官方WON/LOST/DRAW/争议/pending→claim→人工fake原SDK receipt+同目标份额/USDT读回 | 官方结果不代表到账；正claim WAIT_CASH且0新增/自动redeem/approve；错route/读回失败保留未知hash；零兑付不造现金 |
| A-022 | SUPERVISED首单、策略pilot与UNATTENDED能力/授权分别判定 | 有人首单不要求先自动赎回；有人pilot不可用null final通过；无人必须多故障/接管/冷启动，不能声称自动连续复投或外部已通知 |
| A-023 | 原安全signer、SDK lazy FD/API、07-004/005受影响资金/clock及兼容回归 | 仍适用旧独立证据按身份复用；必要回归不删/skip弱化；实际auth/签名/网络/DB调用计数0，依赖/配置/调度/权限不变 |
| A-024 | 最后编辑后的身份、scope/冻结清单及候选隔离核对 | 当前paper进程/环境/期限/source加载行为/binary/evidence不动；旧研究参数/冻结制品不变、不读中途评分；禁止旧target-dir构建 |

金额模型向量可复用07-004 A-009–011及07-002 A-004，另以真实适配器atoms/coverage独立验证，不把旧fixture当真实场馆报告。模型数值对拍abs或rel≤1e-9，原v2传输1e-7不放宽；live原子量/身份/序号/动作计数/预算阈值零容差。不同模式实际fill可不同，但差异必须来自声明的执行事实而非第二经济公式。

## 6. 测试与证据要求

T2须给实际可执行argv/cwd/解释器/既有测试入口与隔离target，按原BOT模块colocated单测及必要集成消费者覆盖上表。Rust使用既有--locked --offline但仍禁止业务网络；Python复用项目或现有predictfun专用venv，不安装包。新测试名/统计数须源码真实存在后再引用；不为整理日志重跑已闭合套件，不运行ignored联网测试、长回测、当前paper/研究或真实binary业务入口。

独立Validate记录最终HEAD+源文件/配置/binarySHA、实际命令/nativeexit、输入依赖/正反例覆盖和未运行项；开发者自测不替代。正式唯一报告 `data/reports/2026-11-19-btc5m-live-parity-and-operations/report.md`，必要 `evidence/`；临时探针仅当前profile scratch。没有data/tasks/任务镜像/逐卡重复报告。真实小资金验证与本轮离线独立Validate分开，不用synthetic签真实PASS，不以盈利或交易笔数门槛求绿。

T1仅静态核对两实体/互引/版本/来源路径/字段和验收映射、scoped diff-check与hash；没有构建或业务测试。安全拒绝停对应动作及依赖分支，不换解释器/工具/包装/worker重放；可选步骤记OMITTED可继续独立授权工作，必需缺口仍block；普通参数/patch/stale保护按原工具在scope内纠正。

## 7. 当前运行保护、实施边界与回退

当前btc5m-baseline72-002（2026-11-19 12:12:10至2026-11-22 12:12:10 Asia/Shanghai）不得改动。active binary、完整SHA和launcher/child/session身份见RFC §6及卡面；control SHA=5590892add29593d71d5233e5c14d831da06bad0bee32822e41b966bcd8250f8，observer SHA=29edb8df1a2b1b1cbe02ee1f0b9ec613a7babe1eb54d3db245acdafb6b71f456，publiccfg沿原run身份cf27481d前缀保留，不反推缺失完整hash。

优先原fork源码+独立候选build/config；T2须先识别当前supervisor后续动态加载的Python源码，可能被当前run再次加载的文件等待paper完成才编辑，不能靠改run source/加载行为或重启隔离。构建禁止使用 `data/reports/2026-11-19-btc5m-observer-runtime-fix/evidence/validate-v11/cargo-target` 或覆盖任何旧binary/证据；新获批候选身份与旧运行身份分区管理，不把旧hash永久当新代码不可变契约。

旧14日四组冻结 `data/reports/2026-11-18-btc5m-joint-forward-validation/evidence/review-preparation/final-freeze.json` 的指定文件/parameters及其附属受保护制品原字节保留，不改参数/重跑/看中途评分。只读manifest身份不等于读取评分。T2最终按当前G3处理：本卡实读arbitrage.rs1493、phase1.rs1566、runtime.rs2370、paper.rs2378、runtime/live.rs1957、predict_fun/fills.rs1972、control.py1722行；大文件增长/跨2400的模块拆分由Principal Design说明，不授权全仓重构。

回退只停候选新增、保留实际账务/hash/占用/latch/屏障，原SDK按明确授权接管；不以旧binary/新run重新试单，不reset/stash/clean/checkout、不改gitlink或共享他人dirty。除本轮两文档外本卡无修改权限。

## 8. 开放问题与阶段交接

业务语义开放冲突0。已选复用项目现有pymongo的Mongo拒绝屏障，不把数据库方法选择退用户；实际生产库/集合/写入/连接绑定须以后明确批准，不能因离线代码完成就写生产。若确需自动跨重启恢复，另做必要字段/事务/fencing最小决策并同步正式合同，不自行加SQLite/包。T2必须完成内部typed字段/source映射、关键order耐久确认与FINAL_SEND hook、OS锁路径/Mongo薄接缝与待批准部署映射、人工接管边界、原supervisor动态加载隔离、allowlist/G3和可执行离线验证；不再把这些留实现者随意决定。

真实Gas预算、批准额度、期限、退出/取消/人工回收目标和可达接管者均为以后实测的明确授权输入，不从历史余额/旧budget flag推定，不在本卡填伪值。本阶段两文档完成静态检查后交主控Gate，按原Full图推进，不自行创建真实运行/同卡重复review或提前Implement。

历史参数化修订 V1.4：t_298e36df / Pascal Light；其参数化契约继续优先于历史固定示例。本轮RFC/SPEC V1.18 §R19仅冻结③需求，①②按RFC R19.1复用已验未部署基线；R18及旧阶段状态保留各自历史时点含义，不覆盖本轮元数据。R17及既有行为不变，③无实现/验收或生产放行。

## 版本记录

| 版本 | 日期 | 内容 |
|---|---|---|
| V1.18 Design指针同步 | 2026-11-26 | t_edbfef11仅把对应Design/阶段元数据机械同步为V1.18 §R19.1–R19.9；下方RFC/SPEC阶段历史记录保留，R19需求语义及D19验收不改，Implement仍须主控Gate。 |
| V1.18 | 2026-11-26 | R19仅③RFC/SPEC：冻结原REST观测/计数/脱敏、同进程scope与显式route桶/保守上界、多窗/头部权威性/缓存/乱序、429reset、优先级/并发/取消、120s/固定deadline及controlled首次poll同步准入，D19-01–08原消费者验收；复用①②已验未部署基线。Design仍V1.17 R18，本卡不改Design/代码/测试/生产状态，④未冻结/未实现。 |
| V1.17 | 2026-11-26 | R18仅第①项：依Pascal决策冻结原启动完整核验/最终结算/现金核清的同run内存历史基线资格，免周期重读旧详情及官方解释；同步输入/三分支输出/资格公式/净成本/D18-01–06，保留fresh当前账户、全分页matches、已观测冲突与本run结算/现金保护。替代未实施TTL及永久不可修订/逐轮全字段检测前提；仅两文档，无业务实测。 |
| V1.16 | 2026-11-24 | R17：完整accepted准入、固定签名expiry双时钟及120s尾查/故障预算、原Final/预占/硬stop不变、封闭log诊断及D17-01–06 native/drive回归；Light文档delta，无业务实测。 |
| V1.0 | 2026-11-19 | 冻结phase1 live同core/FINAL_SEND、实际原子量与新live白名单、窗口/单实例/拒绝冷启动、MANUAL_PAUSE回收及24项离线正反例验收 |
| V1.1 | 2026-11-22 | 事实补注：已有ACCEPTED且带venue_order_id、closure仍非FINAL的订单视为在飞；在飞期间的未完成快照为事实未到，不得作为run级停机理由；只有无ACK/身份或账本不匹配/签名hash不符/风控触发，或订单已FINAL/超期仍无法证明时，才停机并携带既有失败码 |
| V1.2 | 2026-11-22 | 纯文档数值对齐：§4.1/§4.4 的当前生效契约改为 C0=98 USDT、单笔 0.5≤w≤1、单市场 ≤1、总额 ≤10、B 从 98 起、恒等式 NAV/98；A-020 的旧 100/2/2 作为历史验收事实保留原文并加显式取代说明。无代码/语义/金额授权变更 |
| V1.3 | 2026-11-22 | R2 V1/V2/V3：§4.1 三入口共用 mode-aware 6h/24h 正时长边界；§4.4 区分实际敞口≥10u 的 sticky stop/cleanup/drive 返回与拟新增单超额的拒单；§4.8 官方完整 token/side 绑定和历史一致后才解释零兑付，拒绝不污染后读。预算/限额、20u loss、paper、旧证据和上线授权不变。 |
| V1.4 | 2026-11-22 | 公开 run JSON 参数化（Light）：C0/金额改为取本 run 配置冻结值（legacy/历史示例仍为 98/1/1/10/20），并按 target≤order≤market≤total≤budget 校验；事件与 ended 账务读者取该 run 的 budget/loss，元数据读者保留 public==limits 且不发明 target==cap。不改经济、授权或历史证据。 |
| V1.5 | 2026-11-22 | R7 Validate 文档校正（MINOR-1/2）：§4.4 C0 改为取本 run 冻结预算（legacy 98，早期 100 仅历史示例）；预算/caps 行号指针更新为 live.rs:746–754、taker.rs:419–436、live_control.rs:386–395，常量指针校正为 live_accounting.rs:30/32/34/38/40；不改代码/额度/授权语义 |
| V1.6 | 2026-11-22 | R12 窄修订：§4.1 逐 atoms 相等门行号校正为 live.rs:757–764；预算须逐 atoms 等于启动时观察到的 collateral（budget_usdt 支持≤18 位小数的十进制字符串、按 atoms 精确映射，不截断、不容差；±1 atom 即启动前 CASH_BUDGET_MISMATCH 拒绝）；不改经济、额度或授权语义 |
| V1.7 | 2026-11-23 | R13 窄修订：确认的正兑付 claim 在官方结果已确认后，按官方结果的 claim_value_atoms 与已兑付份额核对；claim 未确认前不入账为现金 |
| V1.8 | 2026-11-23 | R13b 窄修订：官方结算先到、精确 claim 后到的顺序下，本 run 内允许把该精确 claim 清回 READY；差 1 atom、结果未确认、foreign token 仍停窗 |
| V1.9 | 2026-11-23 | R13c 窄修订：claim 先判定后入账（账户读回只记为已证明待兑付，已确认官方结果逐 atoms 精确相等才入账为现金）；canonical reader 与 Rust 侧对同一合法流给出一致结论（已兑付持仓不进终态 positions、reader 观察 CASH_CONFIRMED 后不再视为停窗） |
| V1.10 | 2026-11-23 | R13d 窄修订：reader 收到 payout `CASH_CONFIRMED` 且该等待由 `CASH_PENDING` 造成时同步解除 `stopped`（其它原因停止仍黏性，并以 producer→reader 双用例覆盖续单与反例）；逐 atoms 预算门等指针改为符号锚定（`seed_predict` 的 `cash_matches_budget_and_claims` 不等即 bail `CASH_BUDGET_MISMATCH`，行号仅辅助）；移除 `live.rs` 未使用的 `cleared_waits`；不改经济、额度或授权语义 |
| V1.11 | 2026-11-23 | R13e 微修：停窗原因首因胜出——reader 的 payout `CASH_PENDING` 仅在 `stop_reason` 为空或已是 `CASH_PENDING` 时写入停窗，`CASH_CONFIRMED` 只撤销由 `CASH_PENDING` 造成的停；补一条 wire 级反例用例（stop DATA_UNAVAILABLE → payout CASH_PENDING → CASH_CONFIRMED → 后续 RESERVE/FINAL_SEND 仍被拦）；不改经济、额度或授权语义 |
| V1.12 | 2026-11-23 | R14 窄修订：live 健壮性对齐 paper——候选被拒不致命（无未决事实的 NothingToRead 不再停窗，仅 Expired 保持 FACT_INCOMPLETE）；瞬时读失败按连续失败计数 + 具名 `READ_FAILURE_BUDGET`(120s) 降级（禁新增风险、继续观察、清零可恢复，超预算才以既有 `READ_UNAVAILABLE`/`DATA_UNAVAILABLE` 停）；估值缺口（UnknownMark）降级、事实缺口保持既有停机；子进程 stderr 与非事件行留证不杀运行；不改经济、额度、授权、stop reason 词汇或既有逐 atoms 门 |
| V1.13 | 2026-11-23 | R14b 窄修订（文档对齐 + 守护断言）：R14 行为补注把「行情读」从 `READ_FAILURE_BUDGET` 降级列举中移除，并注明行情/报价读保持既有 drive `failed_ticks` 路径（`MAX_FAILED_TICKS` 达上限只撤挂单、不退出窗口，不使用 `READ_FAILURE_BUDGET`）；补 C 项守护断言（degraded 窗口不提前返回、一次成功读即恢复）与 Read/Execution 两类 `clear_failure` 用例；不改经济、额度、授权、stop reason 词汇或生产行为 |
| V1.14 | 2026-11-23 | R15 窄修订（延迟，不改门禁）：live 的账户全量读前移到 tick 获取决策输入之前（drive 的 `sync_live`），发送准备复用这次 receipt-bound 读——守卫在 facts/ack/permit 每次仍复验完备性、身份、ledger generation、attempt 绑定与 10s 新鲜度（`MAX_ACQUISITION_AGE_MS` 未改）；账户读各腿（持仓/挂单分页/`/account`/链快照/历史）并发、按原顺序校验返回原 reason；已证明 `Closure::Final` 且账务完整的关闭历史订单记忆化其净贡献，仍每轮扫 `/orders/matches`，新出现的未声明 hash 仍 `RECONCILIATION_REQUIRED:UNEXPLAINED_HISTORY`；发送路径仅并行可证明独立的读（book 与链快照、balances 与 authorize），签名/ACK/POST 与依赖前序结果的调用保持串行。不改经济、额度、allowance、stop reason 词汇、fail-closed 语义或 paper 路径行为 |
| V1.15 | 2026-11-23 | R16 T1：对齐 R15/R13/R14 已验基线；冻结兼容拒绝诊断、R15 三 minor 闭合、本 run 精确 claim 与600s/deadline有界 WAIT_CASH 续驱动及新测量/验收定义。仅 RFC/SPEC，不表示实现或部署；R15 原卡历史结论不变。 |
| V1.19 | 2026-11-26 | R20 RFC/SPEC按Pascal最新范围冻结：仅非原子现金逐腿floor候选与原settled逐atoms核对、双消费者及D20-01–02；撤回本卡未签收的expiry/市场终态新闭合分支；Design/实现/独立验收待下游，不授予重启。 |
| V1.20 | 2026-11-27 | R21：冻结指定旧窗的原始证据/原生控制流/旧 C0 绑定、两次新鲜原生只读、activation/全 guard CAS/单次交接及 D21-01–07；旧审计与其他恢复不改，不授权实盘。 |

2026-11-23 R14 行为补注：候选在本窗口没有任何未决订单事实时被拒（例如 ROUND_TOO_LATE 在提交前拒绝），不构成致命事实缺失，只记录 blocked 事件并继续该窗口，只有确有一个在飞订单、其事实到既有 `UNREAD_FACTS_BUDGET` 仍不可见才以 `FACT_INCOMPLETE` 停窗。live 读路径（账户读、执行读）的瞬时失败改用 paper 的连续失败计数加预算语义：期间禁止新增风险但继续观察，成功即自动清零并恢复，只有连续失败超过具名 `READ_FAILURE_BUDGET`（120s，沿用 `UNREAD_FACTS_BUDGET` 的既有常量风格）才以既有 `READ_UNAVAILABLE` / `DATA_UNAVAILABLE` 停机；行情/报价读保持既有 drive 的 `failed_ticks` 路径（`MAX_FAILED_TICKS` 达上限只撤挂单、不退出窗口，不使用 `READ_FAILURE_BUDGET`），run 内行情侧唯一既有的 `ReadUnavailable` 是 guard 的空候选簿拒绝，未改动。`refresh_live_risk` 中缺新鲜 mark 的 `UnknownMark` 属可恢复的估值缺口、按上述降级处理，而现金/gas 等事实缺口与 `Conflict` 保持原有停机语义（`DATA_UNAVAILABLE` / `FACT_CONFLICT`），不因缺 mark 而降级事实缺口。

## R20：冷启动 NON_ATOMIC_CASH 的最小整数账务契约（2026-11-26）

### R20.1 来源、版本、范围与证据状态

本节来自 [RFC-07-007](../../rfc/07_trading/RFC-07-007-btc5m-live-parity-and-operations.md) V1.19 §R20.1–R20.5，两文件分别独立存在，旧尾注保留历史阶段含义；[Design](../../design/07_trading/DESIGN-07-007-btc5m-live-parity-and-operations.md) 当前V1.18 §R19，R20待t_0722b40a。本节按Pascal最新范围撤回未签收草稿中的新闭合分支及十项扩张验收，只修cumulative及必要直接调用点；不重构/重命名/迁移，不新增模块、运行时、框架、配置或错误码族。

事实源为 [根因报告](../../../data/reports/2026-11-26-btc5m-history-not-closed-root-cause/report.md) 及其 `evidence/venue-order-matches.json`、`chain-orderfilled.json`、`root-cause-arithmetic.json`、`poststop-read-{1,2,3a}/summary.json`。run `btc5m-live-4d633f8696984a73`、订单 `0x48a26f35ecf5651d1409958c7fc0aacd2f453c621ed9b0213bce6f6a2d06baef`有两腿成功OrderFilled。源码+保存的整数重放定位了`cumulative`非零余数拒绝→execution降级→startup_history的HISTORY_NOT_CLOSED/native exit 4；原生仅记录外层错误，未捕获原生细粒度NON_ATOMIC_CASH，不能宣称已排除全部并存拒绝条件。移除声明则UNEXPLAINED_HISTORY，不允许删声明绕开历史。

链上正确 CTF Exchange `0x8BC070BEdAB741406F4B1Eb65A72bee27894B689` 的状态为 `(false,1)`；市场 RESOLVED/CLOSED。根因报告的“0.38 不可精确表示”在本契约中严格解释为乘积现金有非零余数：`p=380000000000000000` 自身可精确表示。完整 OrderFilled ABI topic 必须校验，报告 `0xd0a08e8c` 仅前缀，不能用前缀匹配实现核对。摘要并非完整 receipt/transfer/签名 expiry/固定块 timestamp/nonce 证明；本节不裁定真实订单现已满足 Final。

本节只取代“非零余数本身即拒绝”的现金计算条件；settled其余拒绝条件全部保留。R17.3/D17-03的OPEN/过期反例、原完整成交及终态关闭、remaining=1、expiry/nonce/市场状态判定均不改；R16/R17等待与R18/R19独立目标不改。主控已核实引入来自2026-11-13 commit `0b8b310`（07-002），今日①仅抽取startup_history文件未改语义，不重查归因。逻辑变量不要求新增wire/schema或数据流。

### R20.2 输入与权威性

| 输入 | 必需语义 |
|---|---|
| 原订单绑定 | chain/deployment/exchange路由、trading address/maker/signer、hash/venue ID、market/token/side、原签名maker/taker/requested/expiry沿原消费者；不新增nonce读取或签名证明获取流程 |
| 官方执行读 | 原 before/after 订单完整绑定及同一累计量、全部 matches 页/无循环或歧义重复、own legs、精确十进制 q/p、明确 fee amount/type、tx；Q 不得超 requested |
| 结算证明 | 正确链/路由且成功 canonical receipt，原完整 OrderFilled 及 collateral/CTF 实际转账；tx/block/log 身份和固定块上界沿原 settled 检查 |
| 原闭合输入 | 原固定块时间、订单状态、getOrderStatus/isValidNonce沿原closed读取与分支；市场状态不变成新增关闭证据，不增加请求 |
| 时间与消费者 | 原 request/receipt/generation/双时钟新鲜度；reader 和 live child 使用同候选共享 crate；不把 receipt 时间或本机时间当链 T |

权威顺序为：经独立实际转账印证的正确 OrderFilled 金额 > 与其精确相等的场馆显式逐 atoms 结算金额 > 报价导出的 floor 核对候选。这里的顺序不是冲突覆盖规则：前两者若冲突必须拒绝。当前 ApiLeg/ApiMatch 不提供独立现金字段，不能虚构字段或无链 fallback。只有报价时，即使乘积能整除，也无权报告已支付或已结算。完整零成交沿原账务零值与闭合门，不要求不存在的成交回执。

### R20.3 唯一整数算法与状态转换

所有 atoms 为非负整数；乘法用足够宽整数，累计/减法 checked，禁止浮点。设 `S=1000000000000000000`，对每条有效 own leg：

- `n_i=q_i*p_i`，`f_i=n_i div S`，`r_i=n_i mod S`，`n_i=S*f_i+r_i`，`0<=r_i<S`。
- 无论 `r_i=0` 还是 `r_i>0`，都计算逐腿 floor 候选 `f_i`；非零余数不得单独触发 NON_ATOMIC_CASH。不得用 ceil、四舍五入或 `floor(sum(n_i)/S)` 取代 `sum(f_i)`。
- 在每个 tx 的本单/同资产/同方向完整集合内，`Q_rest_tx=sum(q_i)`、`C_quote_tx=sum(f_i)`、`Fc_rest_tx=sum(collateral_fee_i)`、`Fs_rest_tx=sum(share_fee_i)`。缺 fee 不等于 0；不支持的费种组合保持原不完整/拒绝。
- 独立解码同集合事件：BUY 的 `(C_event,Q_event)=(sum(makerAmountFilled),sum(takerAmountFilled))`，SELL 对调；maker/taker asset ID 必须分别对应 collateral 0 与原 token/side。每个匹配事件必须与原 owner/hash 绑定，不把 tx 中其他订单或 counterparty 的量混入。
- 当前支持的精确报价/floor 路由必须满足 `Q_event_tx=Q_rest_tx`、`C_event_tx=C_quote_tx`、`F_event_tx=Fc_rest_tx+Fs_rest_tx`，且沿原规则至少一种 fee 总额为 0、费用单位绑定正确；不能把两种单位的非零 fee 相加解释。无唯一 leg↔log 映射时只在原严格 tx 集合比较，不创造逐腿映射或新增成交 ID。
- 再独立核对转账净额（下一节）；全部通过后数值满足`gross_cash=sum(C_event_tx)=sum(C_quote_tx)`、`gross_q=sum(Q_event_tx)`，允许沿原字段/返回类型记账，不要求另存链上金额或改变settled接口。若场馆另给实额也须逐tx相等；跨tx的`+1/-1`不得抵销签收。
- before/after/matches 满足 `Q_before=Q_after=sum(Q_rest_tx)`，全分页结束无缺失才可 pages_complete；数量变化不拼接成成功。不能靠改分页布尔值、重写数量或跳 settled 得到成功。

floor是报价核对必需的整数化步骤，只有相同tx完整链上金额及实际转账均证明后才能成为已结算金额。来源规则不符或`C_event!=C_quote`时不能自动接受或修正expected；链上支付事实可留作诊断，不能声称完整账务通过。缺失保持Unknown/Unproven，不将旧快照/估计/零填为Known。严格沿原错误分类：settled返回false时原execution把净现金/库存置SETTLEMENT_UNPROVEN，原返回Err或身份硬拒绝仍按原路径；不得为本次改造新增硬错误、改写原因或伪造成功。无需新增余数字段、持久化或typed reason。

### R20.4 净额、边界与真实金额向量

对每 tx，`C=C_event_tx,Q=Q_event_tx,Fc=Fc_rest_tx,Fs=Fs_rest_tx`：

- BUY：预期现金支出 `C+Fc`，预期净库存流入 `Q-Fs`；要求 collateral `out-in=C+Fc`、目标 token `in-out=Q-Fs`。
- SELL：预期现金收入 `C-Fc`，当前原支持路径要求 `Fs=0`、预期库存流出 `Q`；要求 collateral `in-out=C-Fc`、目标 token `out-in=Q`。本修订不启用 SELL share fee。
- 任一 checked 运算失败、费用缺失/单位错、上式任一原子不等均不完整/拒绝。VWAP 只能由已证实金额按原整数派生，不反推或覆盖支付实额。原预算、损失、mark 与 claimed cash 恒等式不改。

本次 BUY 向量（现金单位为 USDT atoms，份额/费用为本 token atoms）：

| 腿 | q | p | floor f | remainder r | 链上现金 | share fee |
|---|---|---|---|---|---|---|
| 1 | 349533875338742820 | 380000000000000000 | 132822872628722271 | 600000000000000000 | 132822872628722271 | 6990677506774856 |
| 2 | 2280466124661257179 | 380000000000000000 | 866577127371277728 | 20000000000000000 | 866577127371277728 | 45609322493225143 |

合计 `C=999399999999999999,Q=2629999999999999999,Fc=0,Fs=52599999999999999,net_inventory=2577400000000000000`；原 requested `2630000000000000000` 减实际 Q 为 1，不能补成成交。net_inventory 与签名 min_net_shares 精确相等只是经济数量事实，不证明订单关闭。该表是已给历史证据向量，不声称本卡已跑 synthetic/native 消费者。

边界：腿 1 事件现金改为 `132822872628722270` 或 `132822872628722272`，即使 net transfer 同步改动，仍违反独立 floor 等式；只改 net transfer 则违反净额等式。两 tx 分别 `+1/-1` 即使总现金不变也失败；fee/share quantity 任意 `±1` 同样失败。两条合成腿 `q=2,p=380000000000000000`，逐腿 floor 合计 0，合并 floor 为 1，禁止后者；此向量只验算法，不授予微量下单。正常原子正例可用 `q=S,p=380000000000000000`，得 `f=380000000000000000,r=0`，仍须独立回执/转账。

### R20.5 原闭合谓词保留及反例

只复述当前`account.rs::closed`，不修改它：设`Q`为实际累计份额、`R`为requested、`s`为平台状态、`E`为原签名expiration、`T`为原固定块timestamp。按原短路顺序：`s=FILLED && Q=R`返回FILLED_COMPLETE；否则仅`s`属于`FILLED/CANCELLED/EXPIRED/INVALIDATED`才继续，OPEN或未识别状态返回STATUS_UNPROVEN；继续后`E>0 && T>E`返回SIGNED_EXPIRY，否则正确exchange的isFilledOrCancelled为true返回CHAIN_CLOSED，否则原maker/nonce=0读取为false返回NONCE_INVALID，最后STILL_EXECUTABLE。RPC失败、原整数转换与身份检查沿原错误路径，不新增nonce语义或默填其它历史签名。

`read_order_execution`仍要求`Q_before=Q_after=sum(q_i)`且原closed为真才生成Final；否则OPEN保持Open，其余Unproven。全分页及原数量/身份/settled门各自保留。`startup_history`仍严格要求`pages_complete && accounting_complete && closure==Final`。Final成交量始终是Q，不补成R；实额核对与闭合互不替代。

反例：OPEN即使E已过期、市场RESOLVED/CLOSED、OrderFilled成功、remaining=1、零仓或净份额达标，也仍不能绕过STATUS_UNPROVEN。原允许状态但不满足过期/chain closed/nonce失效时仍STILL_EXECUTABLE；remaining本身不增加分支。`T=E`不满足原SIGNED_EXPIRY的严格大于条件，但原其它合法分支仍可证明闭合。本次不改这些判定，也不强加市场终态条件。算术修复后真实历史仍可能HISTORY_NOT_CLOSED，属于预期结果，不能为转绿改Final。

### R20.6 必需验收矩阵（Design 细化，Implement/独立 Validate 执行；本卡未运行）

| ID | 原消费者输入/覆盖 | 必须断言 |
|---|---|---|
| D20-01 | 在现有测试文件/Scenario重放本节两腿非原子金额，经原execution→settled消费者；历史成功子例只沿用已具原合法Final证明的fixture | 旧候选在cumulative因余数失败；新候选现金999399999999999999、share fee52599999999999999、净份额2577400000000000000被原回执/transfer精确核对，账务完整；不能只过helper。真实remaining=1输入若无原Final证明仍拒绝历史，不伪称真实账户已成功 |
| D20-02 | 复用同Scenario，把某tx事件现金改为其floor候选±1 atom；可同用例参数化转账同步改/仅转账改、跨tx抵销，不另建矩阵框架 | 原settled现金/净额等式仍拒绝，execution保持SETTLEMENT_UNPROVEN、不报完整可用现金；即使closure有原Final证明，历史仍因账务不完整拒绝，不用事件值反改expected |

至少增加上述一正例一反例；必要整数边界复用同文件参数化或既有测试，不新增平行框架、不扩大套件时长，不要求新十项测试链。已有原子/零成交、费用/身份/闭合保护按受影响路径复用，不取消任何拒绝条件。离线fixture明确真实金额与合成receipt/transfer/状态字段，摘要JSON不能冒充完整回执。本卡不跑业务测试/真实账户/API。

两消费者`btc5m_reconcile`与交易二进制必须共享同候选crate及相同正反例结论，不能只修reader或只过helper；由Design映射既有消费者入口。需要重建时沿用原命令并使用`--locked --offline`、保留两binary与源码身份，不覆盖已发布旧制品；具体构建/selector/pin同步点交Design，不猜当前运行hash、不部署/改交易配置。

### R20.7 不得放宽、closed/open 与阶段交接

不得削减：settled 的成功回执、tx/block/log 身份及 canonical 固定块/完整 ABI/emitter、金额/实际转账/fee 等式；账号/原签名 hash/venue ID/market/token pair/side/四类 exchange 路由绑定；分页完整/数量稳定/overfill/未知历史保护；预算/损失/敞口、10s freshness 与 request/receipt/generation、Final 才能释放剩余风险、sticky stop 与 fail-closed takeover。不得引入数额带宽、补齐 1 atom 或跳过核对；这些来源为原 §4/R17、根因报告§6 与本卡明确约束，不是新建安全平台。

closed：非零余数不单独拒绝、逐腿floor候选/原settled权威实额精确核对、费用/净额与原闭合全部保留、双消费者、D20-01–02及授权分离。范围内open需求：无。Design只落实cumulative及必要直接调用点的最小修改、精确allowlist/G3、原Scenario与双binary身份；不新增模块/配置/错误码族、不重构。如果必须改closure或扩大范围才可交付本算术目标，先停止报告缺口和最小选项，由Pascal裁定。

范围外待决：真实remaining=1订单能否按原规则Final，以及旧OUTPUT_INVALID窗口恢复资格，均未完成、不阻塞本次算术修复，却阻止宣称可重启；本阶段未核清完整receipt/transfer及真实闭合输入，不赋予新增expiry/市场证明语义。修复后原生读仍可fail-closed，只有另获授权的fresh原生读可报告当前账户结果。修复通过不等于可重启，仍须原受控入口fresh双读、独立验收与主控核对。旧OUTPUT_INVALID观察者修复已有独立验收，见 [报告 §12](../../../data/reports/2026-11-26-btc5m-execution-facts-output-fix/report.md)，不表示原启动脚本已能恢复该窗口；不新增恢复分支。

本卡仅 RFC/SPEC 追加及文档检查；Design 未更新、业务实现/构建/业务测试/账户读取均 NOT_EXECUTED。不读凭据、不调场馆 API、不签名/POST/撤单/补余量/claim/转账、不写 DB/guard/activation、不改调度/真实交易配置。不额外创建任务或恢复平台，沿预建 Design→Implement→独立 Validate；主控核对产物和所需授权后推进，不由阶段 done 自动授予生产或旧窗口恢复许可。

<a id="r21"></a>
## R21：指定窗口下单前异常退出的受限恢复契约（2026-11-27）

### R21.1 来源、作用域与状态

本节落实 [RFC-07-007 V1.20 §R21.1–R21.4](../../rfc/07_trading/RFC-07-007-btc5m-live-parity-and-operations.md#r21)，只在原 `scripts/start-btc5m-live.sh` → `tools/predictfun/btc5m_launch.py` 的 `--auto-prepare` 启动准备中扩展一个历史资格；不改 Shell 或暴露新入口。只适用于旧 `btc5m-live-4d0577d73dee4106` 与旧交易制品 SHA-256 `06954cb544d700c5c18933018aca949d897e67182c5a28668a2cb9b8834e8543` 联合绑定的精确窗口。按 [Design](../../design/07_trading/DESIGN-07-007-btc5m-live-parity-and-operations.md) §6.3–6.5 继承故障、接管和 G3。§6.5 的 `UNSENT_EDGE` 仍须完整旧审计；其“最后一条”是当时范围，不排斥本次单窗补充。RFC/SPEC §R20 及其历史阶段描述不改；R21 不改变 `HISTORY_NOT_CLOSED`、Final 或任何场馆闭合条件。

定点证据为 [pre-send-exit-recovery-intake.json](../../../data/reports/2026-11-27-btc5m-fact-incomplete-stop/evidence/pre-send-exit-recovery-intake.json)（SHA-256 `a98ce32fa6b45395ed79f1e46e7dbccfc95e8ce07099ffdf8f4ea2833456e729`，16 项本地交叉检查）。其中 `source_sha256` 列出应读取并核验的原字节路径；`checks`、历史读数摘要及现有 `exit 4 / HISTORY_IDENTITY` 均不是独立准入信号。[旧制品及来源绑定](../../../data/reports/2026-11-27-btc5m-fact-incomplete-stop/evidence/closed-reread-bound-candidate/binding.json) 与 [新制品绑定](../../../data/reports/2026-11-27-btc5m-fact-incomplete-stop/evidence/context-root-production-binding.json) 分属不同证明：新交易制品 SHA-256 `66f1286dae49bfc9b4ce2d7e66897c42d1034d20cccd341bfeac8f65d3482f21`，未换 reconciler；`t_6b2c9b97` 的[独立离线验收](../../../data/reports/2026-11-27-btc5m-fact-incomplete-stop/evidence/context-root-fixed-candidate/validation.md) 仅覆盖打包/凭据前门禁，不能当作本资格或实盘验证。

### R21.2 进入新鲜对账前必须闭合的历史证据

下列条件为合取，只认同一次执行、同一份冻结证据；先闭合历史，再触达新的原生账户读取。Design 须精确展开路径/字段/校验顺序，不把 intake 的 `true`、run/错误名白名单或摘要相等单独当作验证。

| 绑定 | 必须成立 |
|---|---|
| 唯一窗口、旧 guard/activation | 对应唯一旧 run 目录与唯一启动尝试目录；旧 `started.json`、`live-context.json`、`public-config.json`、`ended.json`、启动尝试/轮转记录，共同与现有账户锁下 `_check_old_guard` / `_old_activation` 查得的同一 `ARMED` 窗口及存储绑定一致。逐项核对 run、风险窗、授权引用、账户身份、候选 digest、旧时序与模式，保留原完整校验。旧 metadata 仍经 `btc5m_live_events.check_metadata` / `candidate_digest` 的既有身份规则，不能拿当前候选摘要换旧摘要。 |
| 完整来源与旧原生因果 | `started` 的完整候选身份（HEAD、文件成员与摘要、交易二进制）须与旧绑定相符，原 `launch-dispatch.json` 实际记录的命令/参数、制品与规范 context 路径归属同一窗口，且只有一次 controller 调用承诺和记录、没有重试证据。旧制品实际字节及相关源字节须有绑定，以 `src/main.rs::main` → `src/config/controlled_live.rs::read_live_context` 的可审计顺序、原调用和旧制品独立差分共同证明：同一错误分支在 control pipe/activation/manifest 读取、业务配置及 `bot::run` 前返回，因此未进入账户业务、签名、permit/ACK/可能发送路径。差分不是历史执行追踪，不以新制品或源码相似替代旧绑定。 |
| 原日志与退出 | 原 `run-log.txt` 精确为该次唯一 tagged `[stderr] Error: CONTROLLED_MODE: LIVE_CONTEXT_PATH` 行及行尾，`events.jsonl` 是原始零字节；`ended.json` 为 `PROCESS_FAILED` / launcher=1 / child=1 / signal=null / forced_cleanup=false，`audit_complete`、`cash_complete`、`execution_complete` 都为 false，`final_accounting`/`final_event_seq` 为 null，`incomplete_reason=AUDIT_UNAVAILABLE` 且原 takeover 标记保留。日志与空事件只做交叉证据；截断、额外字节/事件、冲突或存在任何后续许可、未知发送或成交证据，不得进入本分支。不得改写旧 run 或合成 final、账务、零风险或完整审计记录。 |
| 旧尝试、轮转、C0 与声明 | 原 `barrier-rotation.json`、`attempt-reserved.json`（seed）、原调用与 `started` 必须互相闭合；seed 固定一次 handoff/no retry，并绑定 `reconciliation.json` 原字节摘要。以旧 run public-config 定值为 C0 权威，核验与尝试配置、seed 预算及旧原生读中的现金等式相同；本窗 C0 为 `80760100000000000001` USDT atoms，无该失败窗引入的成本或损益调整。沿旧 seed 的完整有序 25 条声明，核对 dispatch、两次读及汇总；不追加、移除、重排、去重、以空列表替代或推断本窗出现新订单。 |
| 旧双读与汇总 | `reconciliation-pass-1.json`/`reconciliation-pass-2.json` 的原始摘要须与旧 `account-read-recovery.json` 当时的证明相符；与 seed 引用的 `reconciliation.json` 一起交叉核对同账户、声明、两读当时合法时序、完整只读成功链、分页/历史解释、显式空挂单/持仓、Gas 与逐 atom 现金等式。以旧提交/启动时点及当时门槛验证原新鲜度；若原生 exit 未单独存档，只能由已绑定的原完整读结果与原 anchored `prepare_account` 成功链共同证明，不补造退出记录。两读与汇总的规范化完整账户事实及完整 `claimed_win`/`settled_zero` 多重集一致。它们只证明旧基线，不计入新鲜双读；当时 `account-read-recovery.json` 是旧启动准备的来源，不是本失败窗的新 final。 |

`btc5m_launch._stopped_window` 原拒绝基线为 exit 4 / `HISTORY_IDENTITY`；`btc5m_payout_recovery.known_ended` 只认其原 `OUTPUT_INVALID` / child=0 形态，不扩展、不改 `check_ended`。对本精确对象完整证明后只返回可进入原 `prepare_account` 的受限资格、旧 C0、完整声明及可追溯历史基线；其余保留原分类/拒绝。缺失、歧义、不匹配、原始材料不可信或原生顺序无法可靠证明均 **NO-GO**：本类 0 次新鲜账户读、0 次 activation 发布/guard CAS/controller；保留原拒绝或接管，不以余额相符反推未发送。

### R21.3 两次新鲜完整原生只读

复用 `btc5m_launch._main` 的 `AccountLock`、guard 快照及 `prepare_account` → `local_signer.reconcile_account`；仅同一次原启动准备内依序两次，第一读之前已将旧 C0 与同一完整有序声明绑定到两次输入。不得走普通首读容许 exit 4 或由 `cash - claims` 反定 C0 的分支；失败立即终止，不补读、不自动重试、无新增人工轮次。两次必须各自是此次实做的原 pinned reader、原生 exit 0、`read_only=true`、`complete=true`、原账户身份/完整分页和历史解释（含 `positions_match_history` / `positions_explained`），且各自满足原新鲜度。不能用缓存、旧两读、聚合 `reconciliation.json` 或同一次读的复制品充数。

各次应显式包含 `open_orders=[]` 和 `positions=[]`，不以默认空值接受缺键；必须过原 Gas 门、`_cash_snapshot(..., require_complete=True)` 及逐 atom `collateral_atoms = C0 + Σ(confirmed claimed_win.claim_atoms)`，无容差，不以等额抵销代替逐项核对。两读规范化的完整账户事实须一致（沿 `_account_facts` 比较业务事实，不把读时间/采样块等采样元数据误当漂移；字段完整/可解释仍各自验证）。各次的完整 `claimed_win`、`settled_zero` 多重集必须分别与已证旧锚严格相同，只允许记录排列变化，拒绝缺失、null、重复增量、删除、字段改写及新增历史，即使总金额不变。声明列表按原有序比较，与派彩多重集的排列规则不同。保留原 `preflight` 对输出配置/对账记录的复验，并在新尝试的原证据目录保留旧来源、锚及两次新原生输出的可追溯绑定；不回填历史文件。

### R21.4 原 activation、全 guard CAS 与单次交接

`btc5m_launch.launch` 仍在任何轮换前做原授权/部署/参数、`read_barrier` 全快照一致性及 activation/context 核验。沿原账户锁保护准备与轮转；两读及其校验成功后，沿原 `activate` 的旧字节一致性、原子发布与读回，再由 `rotate` 按**全**旧 guard 快照 CAS、检查仅删除一条且读回已不存在，最后才能按原账户锁交接顺序移交 `dispatch` → `btc5m_control.run` 一次，不放宽任何原控制端授权或 guard 校验。旧 run 不回 READY，不重置 loss latch，不把 R21 视为取消原冷启动或后续运行门禁。

第一读失败时只有 1 次已尝试原生读，不启动第二读；第二读失败时至多 2 次。两类均无 activation 发布、guard CAS 或 controller。双读以后，guard 漂移或发布前 activation 字节漂移拒绝交接；CAS 失败可能已经发布 activation，读回失败也可能已经发生部分副作用。按原顺序如实保留状态，不声称两系统原子事务，不自动回滚/修复/重试，不 dispatch。仅本次全部门禁通过可有一次交接，交接返回也不是实盘启动成功证明。

### R21.5 可证伪验收（后续离线执行）

用冻结原件的受控 fixture，通过原消费者和明确的外部替身；故障注入在隔离副本，不能改原件。记录每例实际 reads、activation 发布、全 guard CAS/读回、controller 次数、拒绝阶段/码与原证据前后摘要。除历史拒绝基线外不给本节发明公开退出码；由 Design 映射既有拒绝边界。

| ID | 输入或扰动 | 断言 |
|---|---|---|
| D21-01 | 冻结原窗 fixture：先旧 `_stopped_window` 路径，再用候选原 parser/main，只替换外部边界，以替身提供两个足额、完整且无漂移的新鲜读结果 | 旧入口 exit 4 / `HISTORY_IDENTITY`；候选历史资格不改旧 `INCOMPLETE`，两次原生读边界调用从第一次起用旧 C0 与同一份 25 条声明；原门禁齐备才有一次 activation 发布、一次全 guard CAS 成功及一次 controller 交接。不得只过纯 helper。 |
| D21-02 | 改 run/账户/风险窗/授权/digest、缺/重复归档、交易二进制或来源不匹配；截断 stderr、追加日志/事件、信号/强制清理、出现发送许可/未知提交/晚到成交 | 即使余额相符也不获本类资格；0 新鲜账户读，0 发布/CAS/controller，不生成旧 final。 |
| D21-03 | 原轮转或单次 dispatch 证据冲突、错 seed 或 reconciliation SHA、错旧 C0、历史两读/汇总/声明不闭合（含历史证明 hash 不符） | 0 新鲜账户读，0 发布/CAS/controller；旧两读不能代替新两读。 |
| D21-04 | 任一新读非 0、不完整、不新鲜、错身份/声明、挂单或持仓非空/缺失、Gas 低或现金差 ±1 atom | 首读失败仅 1 次，次读失败仅 2 次；0 发布/CAS/controller，无拟合、重读或重试。 |
| D21-05 | 两读规范化事实漂移；或两次均呈现同一份额外/删改/重复历史（含净额不变）；对照仅重排原两类记录 | 漂移或历史改变拒绝，0 发布/CAS/controller；仅重排且完整原子事实无差异不误拒。若首读已经违背历史基线，不做第二读。 |
| D21-06 | 锁/旧 guard/旧 activation 不符；双读后 guard 或 activation 漂移；activation 发布/读回失败；CAS 失败或读回仍有 guard | 锁或历史前置失败 0 原生读；双读后漂移 2 次读且无发布/CAS；activation 未通过则不做 CAS，即使文件可能已发布；CAS 或其读回失败不得二次尝试或 dispatch，单列可能已发布/轮转的事实。 |
| D21-07 | 普通健康、原受限恢复及其拒绝例（包括 `OUTPUT_INVALID`/child=0 原分类、`UNSENT_EDGE` 完整审计要求、未知提交/晚到成交、loss latch 与风险阈值触发） | 旧接受、拒绝与副作用语义逐项不变，不引入任何其他窗口、停因或恢复类旁路。 |

### R21.6 不变项与阶段交接

不改 Shell、Rust、原制品/编译路径修复、guard/activation/事件 wire 及 DB 接口/schema、签名、策略、交易参数、风险阈值、原授权、历史证据；不新增通用重启逻辑、公共参数、服务、人工对账轮次或替代入口。T2 `t_74644667` 只同步 Design 和来源指针，依 §6.5 G3 规划纯历史资格及 launcher 最小接线、确切 allowlist、实际 `btc5m_control.public_identity`/`LIVE_PATHS` 及固定身份测试闭合。需要扩大范围或无法可靠闭合时停止，不另作放宽。

本轮只做 RFC/SPEC 和静态证据检查，未运行 launcher、账户、guard/activation、RPC、网络、业务测试或生产操作；未更改 Design、代码、制品、历史证据，不 commit/push。Design/实现/独立 Validate 与真实账户/生产授权分开；本契约及未来离线通过均不表示生产恢复，当前实盘仍 HOLD。
