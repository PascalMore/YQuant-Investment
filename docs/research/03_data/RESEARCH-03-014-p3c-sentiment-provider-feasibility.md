# RESEARCH-03-014 P3-C: 市场情绪与涨停池真实来源覆盖矩阵及决策包

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft）— 本文件为 P3-C Feasibility T1 的独立研究交付物 |
| 作者 | YQuant-Principal（P3-C Feasibility T1, kanban t_65954a09） |
| 创建日期 | 2026-08-03 |
| 版本号 | V0.2 |
| 所属模块 | 03_data（数据层） |
| 目标 capability | `sentiment.market_snapshot`（22 字段 canonical）、`sentiment.limit_up_pool` |
| 权威契约 | RFC-03-014 V0.21 / SPEC-03-014 V0.21 / DESIGN-03-014 V0.27 §3.3、§4.2.1、§4.2.3、§4.2.4（时间语义裁定见 RFC/SPEC V0.21） |
| 裁定 | RFC/SPEC-03-014-F6（freshness canonical key）、RFC/SPEC-03-014-F1（limit_up_pool 业务键）、RFC/SPEC-03-014-F4（读 filter）、**2026-08-03 时间语义裁定（P3-C 收盘后/可重放；snapshot_time=close；实时情绪未来独立 capability）** |
| 关联 B2 证据 | SPEC-03-014 §14.4.5 / DESIGN-03-014 §4.2.1（PR-4 空返回冻结；只读、不可重跑） |
| 标签 | #unified_data #phase3 #sentiment #p3c #feasibility #provider |
| V0.2 更新 | 2026-08-03：同步 P3-C 时间语义裁定（已完成交易日/收盘后/可重放；snapshot_time 仅 close；实时情绪未来独立 capability）与 2026-08-03 交易日 live-read 冻结证据（E22/E23）；更新 §2/§5/§7/§8/§9。 |

> **本文件性质**：这是**零写入、零真实 Provider 调用**的可行性研究/决策包，**不是** adapter 实现，**不是** RFC/SPEC/Design 契约，**不**改变任何现有文档或代码。文档目录 `docs/research/03_data/` 此前不存在，本卡按任务授权仅创建本目录及本文件。
>
> **结论先行**：在现有证据下，`sentiment.market_snapshot` 的 22 字段 canonical schema **不存在完整可信真实来源路径**；`sentiment.limit_up_pool` 的**个股池子子集**存在 SDK 源码级候选（`stock_zt_pool_em` / `stock_zt_pool_dtgc_em`），2026-08-03 交易日 live-read 已验证其**非空返回**（55 行 / 2 行，列名与 SDK 一致），但 `stock_market_fund_flow` 单次 `ConnectionError`、总体 **provider_evidence=fail**——局部池子端点非空**不得夸大为可激活 Provider**。时间语义（2026-08-03 Pascal 裁定）：当前目标为**已完成交易日 / 收盘后 / 可重放**，`snapshot_time` 当前仅 `close`；盘中实时情绪属未来独立 capability（独立 Provider/字段契约/freshness/授权），不在本 Phase 3 范围。**推荐 defer（方案 D）并附 G-1 阶梯（补测 fund_flow + E20 漂移 re-anchor），不创建 pseudo-provider、不重跑已耗尽预算。**

---

## 1. 证据基线（全部只读；禁止重跑 B2）

本节的每一条证据都有明确落点。**任何「可追溯」结论必须能指回下列证据之一**；标为「未知/未验证」的字段不得以字段名、stub、fixture、dry-run smoke 或 freshness closeout 冒充可用性。

### 1.1 契约层（三层文档）

| # | 证据 | 落点 | 内容 |
|---|---|---|---|
| E1 | 22 字段 canonical schema + 字段注入状态表 | DESIGN-03-014 V0.27 §3.3（l.460-614）；SPEC-03-014 §3.3（l.311-413）；RFC-03-014 §5.3.1（l.243-268） | 22 字段契约；唯一键 `{market, snapshot_date, snapshot_time}`；`market_temperature` 允许 None（OQ-2）；`northbound_net_flow` 恒 None（Pascal C） |
| E2 | B2 实测映射契约冻结（PR-4 sentiment） | DESIGN-03-014 §4.2.1（l.743-761）；SPEC-03-014 §14.4.5.3（l.1179-1201） | `stock_market_fund_flow()` + `stock_zt_pool_em(date)` 两调用 row_count=0；X2 空返回 verdict=fail（保守）；reporter 移除 `empty_semantics` 字段 |
| E3 | B2 全 capability 映射裁决总表 | DESIGN-03-014 §4.2.4（l.860-869）；RFC-03-014 §13.4.5.8（l.681-691）；SPEC-03-014 §14.4.5.9（l.1280-1293） | `sentiment.market_snapshot` / `sentiment.limit_up_pool` = **offline stub**；AKShareProvider 未注册这 2 项 capability（注册缺口） |
| E4 | 单次 live-read 预算与零写入边界 | SPEC-03-014 §14.4.5.5（l.1220-1239） | PR-4 预算 2 次已用尽、剩余 0；B2 零 Mongo/Cache/Audit/DDL 写入、无重试、无 fallback |
| E5 | refresh 授权前状态机 | SPEC-03-014 §14.4.5.10（l.1295-1309） | sentiment 两 capability 保持在「已注入但未实现」（`NotImplementedError`），直到交易日 live-read 复验 |
| E6 | P3-C 映射验收项 | RFC-03-014 §P0.6（l.1108-1133） | PC-3 `market_temperature` 全 fixture/stub 为 None（任何非 None 视为 FAIL）；PC-4 `northbound_net_flow` 全 None；PC-6 X2 空返回；PC-11 freshness canonical key 冻结 |
| E7 | 真实 Provider 待验证事项 | RFC-03-014 §5.5（l.289-304） | FV-5 涨停/跌停池接口实时性与准确度；FV-6 温度合成多接口一致性——均待验证 |
| E8 | freshness F6 裁定 | RFC-03-014-F6 / SPEC-03-014-F6 | `market_sentiment`=3600 为 `sentiment.market_snapshot` 唯一 canonical key；`sentiment_limit_up_pool`=3600 为 `sentiment.limit_up_pool` 唯一 key。**freshness key 冻结 ≠ Provider 可用** |
| E9 | F1 / F4 裁定 | RFC-03-014-F1 / F4 | `sentiment.limit_up_pool` 业务键 `{market, symbol, trade_date}`；读 filter 必须含 `market` |
| E10 | 离线 scaffold（只读审计） | `models/domain/sentiment.py`、`services/sentiment_service.py`、`providers/sentiment_stub.py` | 22 字段 dataclass；refresh 三态 default-deny；stub 返回 `OFFLINE-001` 确定性 fixture，`market_temperature=None`、`northbound_net_flow=None`，`raw_payload.live_data=False` |

### 1.2 实测/运行证据

| # | 证据 | 落点 | 内容 |
|---|---|---|---|
| E11 | smoke 报告（4 份） | `docs/rfc/03_data/smoke_reports/smoke-sentiment-20260722/24/26/28.yaml` | 全部 `verdict: pass`，`memo: dry-run — no real calls made`，`actual_calls: 0`。**dry-run 不是 Provider 可用性证据** |
| E12 | B0/B2 live-read 时间事实（本卡新增核查） | `date -d` 本地核查 2026-07-25/26 为周六/周日 | **B0（2026-07-25，0/9 映射）与 B2（2026-07-26，row_count=0）均发生在非交易日（周末）**。`stock_zt_pool_em` 在无交易日时返回空是正常行为——空返回不能证明 endpoint 不可用，也不能证明可用（SPEC §14.4.5.3 已预置「交易日复验」要求） |
| E13 | SDK 源码（只读，akshare 1.17.54，项目 venv） | `.venv/lib/python3.12/site-packages/akshare/stock_feature/stock_ztb_em.py` | `stock_zt_pool_em(date)` 涨停股池：16 列（序号/代码/名称/涨跌幅/最新价/成交额/流通市值/总市值/换手率/封板资金/首次封板时间/最后封板时间/炸板次数/涨停统计/连板数/所属行业），`涨停统计` 形如 `"days/ct"`（连板天数/涨停次数） |
| E14 | 跌停池 SDK 源码 | 同上文件 l.439-501 | `stock_zt_pool_dtgc_em(date)` 跌停股池：17 列（含 封单资金/最后封板时间/板上成交额/连续跌停/开板次数/所属行业）；**限制最近 30 个交易日**（`raise ValueError` 早于 30 日） |
| E15 | 大盘资金流 SDK 源码 | `.venv/.../akshare/stock/stock_fund_em.py` l.347-416 | `stock_market_fund_flow()` 15 列：日期/上证-收盘价/上证-涨跌幅/深证-收盘价/深证-涨跌幅/主力净流入-净额/主力净流入-净占比/超大单…/大单…/中单…/小单…。**无「成交额」列** |
| E16 | 市场活跃度 SDK 源码 | `.venv/.../akshare/stock_feature/stock_market_legu.py` | `stock_market_activity_legu()` 乐咕乐股「赚钱效应分析」：item/value 键值对快照（含「统计日期」），**非日级历史时序**；item 名称来自页面 HTML，SDK 源码未固定 |
| E17 | 全市场实时行情 SDK 源码 | `.venv/.../akshare/stock_a/stock_zh_a_spot.py` l.197-207 | `stock_zh_a_spot_em()` 沪深京 A 股实时行情（含 涨跌幅/换手率/总市值/流通市值）；**实时快照、非收盘后历史**；全市场 ~5000 行，重查询 |
| E18 | 概念板块行情 SDK 源码 | `.venv/.../akshare/stock_a/stock_board_concept_name_em.py` l.129-177 | `stock_board_concept_name_em()` 概念板块列表（板块代码/板块名称/涨跌幅/上涨家数/下跌家数/领涨股票/领涨股票-涨跌幅/换手率/总市值）——`hot_concepts` 的候选（top-N 概念），**不在 B2 契约内** |
| E19 | smoke_sentiment.py B0 重锚 expected 字段集 | `scripts/t4_preflight/smoke_sentiment.py` l.98-143 | `_EXPECTED_SENTIMENT_FIELDS` 15 列（对齐 `stock_market_fund_flow`）；`_EXPECTED_LIMIT_UP_FIELDS` 16 列（序号/代码/名称/涨跌幅/最新价/成交额/流通市值/总市值/换手率/连板数/所属行业/封单金额/封单量/封成比/开板次数/涨停时间） |
| E20 | **SDK 版本漂移（本卡新增核查）** | E13 vs E19 | `_EXPECTED_LIMIT_UP_FIELDS` 与 SDK 1.17.54 `stock_zt_pool_em` 实际列名**有 5/16 列不同**：smoke 期望 `封单金额/封单量/封成比/开板次数/涨停时间`，SDK 实际 `封板资金/首次封板时间/最后封板时间/炸板次数/涨停统计`。说明 expected 字段集与当前 SDK 版本存在漂移（上游改名或版本差异），schema-drift 风险为**已观测事实**而非假设 |
| E21 | 离线 fixture | `tests/fixtures/sentiment_fixtures.py` | 22 字段离线 payload：`market_temperature=None`、`northbound_net_flow=None`；`sample_limit_up_pool_records` 含 封单金额/封成比/连板天数/涨停原因 字段——**这些字段在 SDK zt_pool 中并无同名列，fixture 是契约占位不是实测映射** |
| E22 | 2026-08-03 交易日 live-read 冻结报告（本卡新增，只读、不可重跑） | `/tmp/yquant-p3c-live-read-20260803/report.json` | `trade_date=20260803`（周一交易日）：`stock_zt_pool_em` success 55 行（16 列，列名与 E13 SDK 静态一致）；`stock_zt_pool_dtgc_em` success 2 行（16 列，含 动态市盈率/封单资金/板上成交额/连续跌停/开板次数/所属行业）；`stock_market_fund_flow` 单次 `ConnectionError`（row_count=0）。retry=0 / fallback=0 / mongo=0 / write=0；**boundary PASS、provider_evidence=fail**；stop_reason=`raised:ConnectionError`；预算已耗尽（3/3），不得重跑 |
| E23 | 大盘资金流 SDK 静态确认（本卡新增，只读） | `.venv/.../akshare/stock/stock_fund_em.py` l.347-416 | `stock_market_fund_flow()` **无参数**，底层东方财富 `fflow/daykline/get`、`klt=101`（日线），返回近期**日线**大盘资金流；列=日期/上证·深证收盘与涨跌幅/主力·超大单·大单·中单·小单净流入及占比，**无「成交额」列**（E15 复核） |

### 1.3 本卡新增证据的边界声明

- E12/E15/E16/E17/E18/E20 来自**本地 SDK 源码/系统日历的只读核查**，未发起任何网络调用、未 import 调用 akshare endpoint、未连接 Mongo、未运行 CLI smoke。符合任务「可查公开 Provider 文档或公开 SDK 源码，但不得调用任何真实 endpoint」的授权边界。
- B2 冻结报告（`/tmp/yquant-b2-pr234-20260726/`）当前不在磁盘；其冻结值以 DESIGN/SPEC 转录为准（E2/E3/E4），本卡未重跑 live-read，未违反 §14.4.5.5 预算。
- E22 的 2026-08-03 受控单次 live-read 由独立探针（G-1 前置，非本卡）执行并冻结；本文件仅**只读引用**该报告，未重跑、未发起任何网络调用、未 import 调用 akshare endpoint、未连接 Mongo、未运行 CLI smoke（预算已耗尽，任何新 live-read 须 Pascal 独立授权）。

---

## 2. 覆盖矩阵：`sentiment.market_snapshot` 22 字段

**图例**：原始可得 = `YES`（契约/参数/服务层确定可得）/ `COND`（条件可得，取决于未验证的 endpoint 或需交易日 live-read）/ `UNKNOWN`（无已验证候选）/ `NO`（按裁定恒不提供）。

| # | 字段 | 类型/默认 | 候选来源 | 原始可得 | 时间语义 | 单位/正负 | 可空规则 | 证据等级 | 风险 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `snapshot_date` | str, 必填 | 查询参数 `date` | **YES** | 日历日 | `YYYY-MM-DD` | 必填（唯一键） | HIGH（E1） | 无 |
| 2 | `snapshot_time` | str, 必填 | **当前实现/映射仅可落地 `"close"`**（2026-08-03 裁定；禁止 intraday snapshot） | **YES** | 收盘后（已完成交易日，可重放） | `"close"`（`HH:MM:SS` 属未来盘中独立 capability 才可用） | 必填（唯一键） | HIGH（E1 + 2026-08-03 裁定） | 无（当前仅 close） |
| 3 | `market` | str="CN" | 固定 | **YES** | — | — | 必填（唯一键） | HIGH（E1） | 无 |
| 4 | `limit_up_count` | int=0 | `stock_zt_pool_em(date)` 行计数 | **COND** | 收盘后日级 | 计数 ≥0（含 ST） | 默认 0 | MEDIUM-LOW：SDK 存在（E13）；B2 空返回（E2，周末）；**2026-08-03 交易日 live-read 非空 55 行（E22）** | 含 ST 判定需确认（名称/板块过滤无验证） |
| 5 | `limit_down_count` | int=0 | `stock_zt_pool_dtgc_em(date)` 行计数 | **COND** | 收盘后日级 | 计数 ≥0（含 ST） | 默认 0 | **LOW**：SDK 存在（E14）；**2026-08-03 交易日 live-read 非空 2 行（E22）**；DESIGN §3.3 写「`stock_zt_pool_em`→跌停行计数」与 SDK 事实矛盾（zt_pool 只含涨停，须用 dtgc_pool） | DESIGN 映射错误需修正；新 endpoint 需独立验证 |
| 6 | `limit_up_count_ex_st` | int\|None | 待验证（zt_pool 行 + ST 过滤） | **UNKNOWN** | 收盘后日级 | 计数 ≥0 | 可空 | LOW：DESIGN 标「待 live-read 验证」（E1） | ST 识别（名称/板块过滤）无验证 |
| 7 | `limit_down_count_ex_st` | int\|None | 待验证（dtgc_pool 行 + ST 过滤） | **UNKNOWN** | 收盘后日级 | 计数 ≥0 | 可空 | LOW（E1） | 同上 |
| 8 | `advance_count` | int=0 | 候选：`stock_market_activity_legu`（快照）或 `stock_zh_a_spot_em` 计算或板块级 | **UNKNOWN** | 实时快照 vs 日级语义不齐 | 计数 ≥0 | 默认 0 | **LOW**：DESIGN 标「待确认」（E1）；无已验证候选 | 实时快照≠收盘后历史；板块级≠全市场粒度 |
| 9 | `decline_count` | int=0 | 同上 | **UNKNOWN** | 同上 | 计数 ≥0 | 默认 0 | LOW | 同上 |
| 10 | `flat_count` | int=0 | 同上 | **UNKNOWN** | 同上 | 计数 ≥0 | 默认 0 | LOW | 同上 |
| 11 | `total_listed_count` | int\|None | 候选：spot 行数 / `metadata.stock_list` | **UNKNOWN** | 日级 | 计数 >0 | 可空 | LOW（E1） | 口径（沪深京 vs A股）未定 |
| 12 | `market_temperature` | float\|None | **无（合成字段，无已确认公式）** | **NO**（按裁定） | — | 0-100 | **必须 None** | HIGH：Pascal OQ-2/OQ-6（E1/E6） | **禁止合成清单 #1** |
| 13 | `total_turnover` | float\|None | DESIGN 推断 `stock_market_fund_flow→成交额`（medium，已 superseded） | **UNKNOWN/CONTRADICTED** | 收盘后日级 | 元 | 可空 | **LOW，推断被 SDK 推翻**：E15/E23 显示该 endpoint **无「成交额」列**；净额列单位是亿元资金流非成交额；E22 该 endpoint 亦 `ConnectionError`。**2026-08-03 裁定：无合规来源时字段保持 None/unavailable，资金净流入不得映射 total_turnover** | 需新候选（如 index quotes 聚合 / spot 求和），未验证 |
| 14 | `hot_concepts` | list[str]\|None | 候选：`stock_board_concept_name_em` top-N | **UNKNOWN** | 收盘后日级 | 列表 ≤50 | 可空 | LOW：候选存在（E18），不在 B2 契约 | 概念排名语义/阈值未定 |
| 15 | `continuous_limit_up` | list[dict]\|None | `stock_zt_pool_em` 按 `连板数`/`涨停统计` 分组（days≥2） | **COND** | 收盘后日级 | `{symbol, days, reason}` | 可空 | MEDIUM-LOW：SDK 有 连板数/涨停统计（E13）；B2 空（E2，周末）；**2026-08-03 非空（E22）** | **`reason` 无来源**（见 #24） |
| 16 | `max_continuous_days` | int\|None | 派生自 `continuous_limit_up` | **COND**（派生） | 收盘后日级 | 正整数 | 可空 | MEDIUM：派生契约已定义（E1） | 随 #15 |
| 17 | `northbound_net_flow` | float\|None | **无（Pascal C）** | **NO**（按裁定） | — | 元 | **必须 None** | HIGH：Pascal C（E1/E6）；B2 证实 endpoint 语义为持股历史≠净流入（SPEC §14.4.5.2） | **禁止合成清单 #2** |
| 18 | `limit_up_pool` | list[str]\|None | `stock_zt_pool_em` 代码列 | **COND** | 收盘后日级 | 列表 ≤500 | 可空（capability 独立提供时可为 None） | MEDIUM-LOW（E13/E2；**2026-08-03 非空 E22**） | 自去重不变量；与 capability 重叠边界（E9） |
| 19 | `limit_down_pool` | list[str]\|None | `stock_zt_pool_dtgc_em` 代码列 | **COND** | 收盘后日级 | 列表 ≤500 | 可空 | LOW-MEDIUM（E14；**2026-08-03 非空 E22**） | 新 endpoint 未验证 |
| 20 | `fetched_at` | str\|None | 服务层录制 | **YES** | ISO-8601 | 时间戳 | 可空 | HIGH（E1） | 无 |
| 21 | `provider` | str="" | 服务层写入 `"akshare"` | **YES** | — | — | 必填 | HIGH（E1） | 无 |
| 22 | `raw_payload` | dict\|None | Provider 原始返回 | **COND** | — | — | 可空 | HIGH（E1） | 仅调试/审计，不入查询路径 |

**小结**：22 字段中 **5 个 YES（契约/参数/服务层确定可得）**（#1 snapshot_date、#2 snapshot_time、#3 market、#20 fetched_at、#21 provider），**7 个 COND（条件可得）**（#4/#5/#15/#16/#18/#19/#22，取决于 zt_pool/dtgc_pool 交易日验证），**7 个 UNKNOWN（无已验证候选）**（#6/#7/#8/#9/#10/#11/#14：ex_st×2、advance/decline/flat、total_listed_count、hot_concepts），**2 个 NO（恒 None）**（#12 market_temperature、#17 northbound_net_flow），**1 个 CONTRADICTED**（#13 total_turnover，推断被 SDK 推翻）。合计 5+7+7+2+1 = 22。

**时间语义（2026-08-03 Pascal 裁定）**：本矩阵所有字段面向**已完成交易日 / 收盘后 / 可重放**快照；`snapshot_time` 当前仅 `close`。盘中实时情绪属未来独立 capability（独立 Provider/字段契约/freshness/时间边界/授权），不在本 Phase 3 范围。

---

## 3. 覆盖矩阵：`sentiment.limit_up_pool`（`LimitUpPoolRecord` 关键字段）

| # | 字段 | 类型/默认 | 候选来源 | 原始可得 | 时间语义 | 单位/正负 | 可空规则 | 证据等级 | 风险 |
|---|---|---|---|---|---|---|---|---|---|
| 23 | `symbol` | str, 必填 | `stock_zt_pool_em`→`代码` / `stock_zt_pool_dtgc_em`→`代码` | **COND** | 收盘后日级 | 6 位代码 | 必填（唯一键） | MEDIUM-LOW（E13/E14/E2；**2026-08-03 非空 E22**） | 列名对齐仍待完整 re-anchor |
| 24 | `market` | str, 必填 | 固定 `"CN"` | **YES** | — | — | 必填（唯一键） | HIGH | 无 |
| 25 | `trade_date` | str, 必填 | 查询参数 `date` | **YES** | 日历日 | `YYYY-MM-DD` | 必填（唯一键） | HIGH | 无 |
| 26 | `status` | str="limit_up" | zt_pool→limit_up；dtgc_pool→limit_down | **COND** | 收盘后日级 | 枚举 | 默认 limit_up | MEDIUM-LOW | 跌停池需独立 endpoint（E14） |
| 27 | `limit_up_time` | str\|None | `stock_zt_pool_em`→`首次封板时间`（**非** smoke 期望的 `涨停时间`） | **COND** | 收盘后 | `HH:MM:SS` | 可空 | LOW-MEDIUM | **E20 列名漂移已观测** |
| 28 | `last_price` | float\|None | `最新价` | **COND** | 收盘后 | 元 | 可空 | MEDIUM-LOW | SDK 除 1000 换算（E13 l.97）需复核 |
| 29 | `pct_chg` | float\|None | `涨跌幅` | **COND** | 收盘后 | % | 可空 | MEDIUM-LOW | 正负约定一致 |
| 30 | `order_amount` | float\|None | `封板资金`（SDK 列名，**非** smoke 期望 `封单金额`） | **COND** | 收盘后 | 元 | 可空 | LOW-MEDIUM | **E20 列名漂移** |
| 31 | `turnover_amount` | float\|None | `成交额` | **COND** | 收盘后 | 元 | 可空 | MEDIUM-LOW | 单位核对 |
| 32 | `order_ratio` | float\|None | **SDK zt_pool 无 `封单量` 列**，`封成比=封单/成交额` 无法从该 endpoint 计算 | **UNKNOWN** | 收盘后 | 比率 | 可空 | **LOW**：SDK 无该列（E13） | 无已验证来源 |
| 33 | `turnover_rate` | float\|None | `换手率` | **COND** | 收盘后 | % | 可空 | MEDIUM-LOW | — |
| 34 | `consecutive_days` | int=1 | `连板数` 或 `涨停统计` 的 days | **COND** | 收盘后 | 计数 | 默认 1 | MEDIUM-LOW | `涨停统计` 解析格式（E13）需验证 |
| 35 | `reason` | str\|None | **SDK zt_pool 无「涨停原因」列**；`所属行业` 是行业归属，**不是**涨停原因 | **NO（zt_pool 内无）** | 收盘后 | 自由文本 | 可空 | **LOW**：SDK 事实（E13）；DESIGN/SPEC 未给候选 | **语义缺口**：行业≠原因；不得以行业填充原因 |
| 36 | `market_cap` | float\|None | `流通市值` | **COND** | 收盘后 | 元 | 可空 | MEDIUM-LOW | — |
| 37 | `fetched_at` / `provider` | str\|None / str | 服务层录制 | **YES** | ISO-8601 / — | — | 可空 / 必填 | HIGH | 无 |

**小结**：`LimitUpPoolRecord` 有 **3 个 YES**（market/trade_date/fetched_at·provider）、**10 个 COND**（取决于交易日 live-read 与列名对齐）、**2 个 UNKNOWN/NO**（order_ratio、reason——SDK 无对应列）。

---

## 4. 四种方案可行性/成本/失真风险比较

| 维度 | A. 单 endpoint（仅 `stock_zt_pool_em`） | B. 最小 sourced subset | C. multi-endpoint aggregation | D. defer（维持 offline stub） |
|---|---|---|---|---|
| 覆盖 | 仅涨停侧：limit_up_count、limit_up_pool、continuous_limit_up(days)、LimitUpPoolRecord 部分字段 | 交易日验证后激活有据字段：limit_up_pool capability（10 个 COND 字段）+ market_snapshot 的 COND 子集，其余保持 None | zt_pool + dtgc_pool + fund_flow + concept_name + spot/activity + index quotes | 不注册 sentiment capability；22 字段契约 + stub + freshness keys 维持现状 |
| 可行性 | 中低：**缺跌停侧**；snapshot 至少 10 字段空 | 中：2 个 endpoint（zt_pool + dtgc_pool）live-read + 列名对齐 | 低-中：5+ endpoints，每个需独立 live-read；时间语义混合 | 最高：零风险 |
| 成本 | 低：1 endpoint；但仍需交易日 live-read + SDK 版本对齐 + E20 漂移修正 | 中：2-3 endpoint live-read、映射/单位验证、SDK version pin、漂移报告 | 高：每 endpoint 独立验证（§14.4.5.5 预算外）、日级 vs 实时快照对齐、单位换算（亿元→元）、粒度对齐 | 零 |
| 失真风险 | 中：跌停缺失、空字段用默认/None 呈现需严格纪律 | 低：严格 None/nullable 纪律；subset 语义文档化 | **高**：实时快照（spot）与收盘后 pool 混合造成时间语义失真；advance/decline/flat 口径漂移；诱发「合成温度」诱惑 | 无 |
| 对 Pascal C/OQ-2 | 温度/北向仍 None，无冲突 | 同左 | 若为凑字段而引入合成，**违反 PC-3/PC-4** | 同左 |
| 结论 | 不能作为 market_snapshot 完整源；仅可作 limit_up_pool 第一步 | **推荐路径**（先 capability 后 snapshot） | 仅当明确全字段需求，且逐 endpoint Gate | **当前默认推荐** |

**成本量化注记**：B 方案的一次交易日 live-read 预算建议为 zt_pool×1 + dtgc_pool×1 + fund_flow×1 = 3 次调用（与 PR-4 预算 2 次同量级，需 Pascal 新授权，因 B2 预算已尽 E4）。

---

## 5. 严格禁止合成清单

1. **`market_temperature` 禁止任何非 None 值**：禁止公式、硬编码、替代指标（如 `advance_count/(advance_count+decline_count)`）。Pascal OQ-2/OQ-6，DESIGN §3.3 l.608、SPEC §3.3、RFC §P0.6 PC-3 三重冻结。任何非 None 值 = 验收 FAIL。
2. **`northbound_net_flow` 禁止任何非 None 值**：禁止把北向持股历史（`持股数量`/`持股市值`/`今日增持资金`）别名映射为净流入（SPEC §14.4.5.2 硬约束）；禁止引入 A/B endpoint skeleton。Pascal C 恒 None，`from_dict` 强制置 None。
3. **禁止把 `所属行业` 当 `reason`（涨停原因）填充**：zt_pool 的 `所属行业` 是行业归属，不是涨停原因；行业≠原因（E13，见 #35）。
4. **禁止把 `stock_market_fund_flow` 净额当 `total_turnover`**：该 endpoint 无「成交额」列（E15 推翻 DESIGN §3.3 的 medium 推断）；净额是资金流（亿元）非成交额（元）。
5. **禁止用板块级 上涨家数/下跌家数 冒充全市场 `advance_count`/`decline_count`**：粒度不同；若未来派生必须显式定义契约并标注 derived。
6. **禁止以字段名相近、历史持股、新闻文本、推断或 0 值替代真实 source**（任务 body 绝对禁止项）。
7. **禁止把 offline stub / fixture / dry-run smoke / freshness closeout 当作 Provider 可用性**（E10/E11/E8；F6 结论不得误写为「Provider 已可用」）。
8. **禁止在 B2 live-read 预算用尽后重跑 live-read**（SPEC §14.4.5.5）；任何新 live-read 须 Pascal 独立授权。
9. **禁止创建 pseudo-provider 或注册未验证 capability**：`AKShareProvider` 当前 9 项 capability 不含 sentiment（E3）；注册前必须过 §6 门禁。
10. **禁止把 `stock_market_fund_flow()` 日线序列描述为实时盘中数据**：函数无 date 参数（东方财富 `fflow/daykline/get`、`klt=101` 日线，E23）；使用时必须按返回日线序列按目标 `trade_date/snapshot_date` 精确筛选，不得写成接受指定日期的实时查询（2026-08-03 裁定）。
11. **禁止将局部池子端点非空证据夸大为可激活 Provider**：2026-08-03 live-read 中 zt_pool 55 行 / dtgc 2 行非空仅证明局部池子端点可用，但 `stock_market_fund_flow` 单次 `ConnectionError`、总体 provider_evidence=fail（E22）；sentiment 两 capability 未注册，维持 offline stub/defer。

---

## 6. 真实 Provider 激活前的最小准入门禁

| # | 门禁 | 契约依据 | 内容 |
|---|---|---|---|
| G-1 | **独立交易日 live-read 授权** | SPEC §14.4.5.5（预算已尽）、§14.4.5.3（交易日复验） | Pascal 授权新 live-read（建议 zt_pool/dtgc_pool/fund_flow 各 1 次，共 3 次，严格零写入）。**必须选交易日**——E12 显示历史两次 live-read 均在周末，空返回不能作为可用/不可用证据 |
| G-2 | **source_trace 精确契约** | RFC §5.1.5、D1/D3 裁定 | 每个字段的 source_trace 形如 `akshare(endpoint: <name>, fields: [<mapped_field>], issues: [<deviation>])`；**不含** `ud_materialized(ok)` / `cache(ok)`；允许 `ud_materialized(skipped: ...)` / `cache(miss)` |
| G-3 | **schema-drift 门禁** | RFC §6.3（>50% 字段名不匹配 → 停止） | 激活时按**当前 SDK 版本** re-anchor expected 字段集（E20 已证 5/16 漂移）；生成 expected vs actual 列名漂移报告；漂移>50% 即停，重新调整 domain object schema 后重试 |
| G-4 | **empty/error 契约（X2）** | SPEC §14.4.5.3 | row_count=0 → verdict=fail（保守），不细分原因；endpoint 异常/非 DataFrame → fail，停止该子阶段，不自动重试；reporter 不输出 `empty_semantics` |
| G-5 | **调用预算** | SPEC §14.4.5.5 | 每次激活的 endpoint 数量与调用次数由 Pascal 预先批准；失败仅记录，无 fallback、无自动重试 |
| G-6 | **零写入与回滚边界** | RFC §6、SPEC §14.4.5.5 | PR 阶段（live-read）零 Mongo/Cache/Audit/DDL 写入；PR-DDL-P3C（集合+索引）需 Pascal 手动确认且 schema 与 SPEC §3.3 最终版一致；PR-CANARY 仅一次手动 refresh 写入；失败即终、不降级写入、不自动回滚（rollback 脚本见 DESIGN §6.4.ter）；cron/systemd 独立授权 |

**激活顺序建议**（沿用 RFC §6.2）：G-1 live-read → Pascal 审阅 → PR-DDL-P3C（若推进）→ PR-CANARY → 之后才允许 refresh 激活（G-C-2）与刷新链路。

---

## 7. 给 Pascal 的决策选项与推荐

### 选项 1（推荐）：Defer + 一次低成本前置验证（D→B 阶梯）
- 维持 offline stub 与 22 字段契约；不注册 sentiment capability、不写 adapter。
- G-1 的交易日只读 live-read 已**部分执行**（2026-08-03，E22）：zt_pool 55 行、dtgc_pool 2 行非空、列名与 SDK 静态一致（E13/E14 复核通过）；`stock_market_fund_flow` 单次 `ConnectionError`，该侧仍不可用。预算已耗尽（3/3），若需补测 fund_flow 须 Pascal 新授权；E20 的 5/16 列名漂移仍待完整 re-anchor 与漂移报告。
- 依据：22 字段中 7 个 UNKNOWN + 2 个 NO（恒 None）+ 1 个 CONTRADICTED；即便 7 个 COND 字段全部验证成功，也只能覆盖约一半字段（5 YES + 7 COND = 12/22）。证据不足时默认 defer，符合任务要求「不创建 pseudo-provider」。

### 选项 2：先激活 `sentiment.limit_up_pool`（方案 B 的 capability 先行）
- 在 G-1 live-read 通过且漂移报告修正列名后，先落地 limit_up_pool capability（10 个 COND 字段，E13/E14 支撑），`market_snapshot` 仅填充有据字段、其余 None。
- 注意：`reason`（涨停原因）与 `order_ratio`（封成比）无 SDK 列，保持 None 或另行裁定；不得用 `所属行业` 填充 reason。

### 选项 3：多 endpoint 全字段聚合（方案 C）
- 仅当 Pascal 明确要求全字段覆盖（advance/decline/flat、total_turnover、hot_concepts）时考虑；需逐 endpoint Gate、时间语义对齐、单位换算；成本高、失真风险高。

### 选项 4：直接跳过（维持现状）
- 什么都不做，保留 freshness keys 与 stub。能力缺口已被接受（温度/北向恒 None）；涨停池能力缺口在此选项下长期存在。

**推荐**：**选项 1**。理由：① 现有证据无法支撑 22 字段完整激活（§2 小结）；② 候选端点（zt_pool/dtgc_pool）已在 2026-08-03 交易日验证非空（E22），但 `stock_market_fund_flow` 单次 `ConnectionError`、总体 provider_evidence=fail，且 E20 列名漂移已观测；③ 补测 fund_flow 的单次只读 live-read 成本极低，能把剩余 COND 字段升级为可验证事实，是后续所有选项的共同前置。**在 G-1 完整通过之前，任何「sentiment Provider 已可用」的表述都是错误的。**

---

## 8. 未验证项清单（future work，不在本卡执行）

| # | 未验证项 | 验证方式 | 前置 |
|---|---|---|---|
| U-1 | zt_pool / dtgc_pool 列名完整 re-anchor（2026-08-03 已非空，E22，列名与 SDK 一致）；fund_flow 交易日可用性（2026-08-03 单次 `ConnectionError`，待复验） | G-1 交易日 live-read（预算已尽，需 Pascal 新授权） | Pascal 授权 |
| U-2 | `limit_up_count` 含 ST 口径 | 对照 zt_pool 名称/板块过滤 | U-1 |
| U-3 | `ex_st` 两字段的 ST 过滤可行性 | 静态 + live-read 后判定 | U-1 |
| U-4 | advance/decline/flat 的可信日级来源 | 候选对比（spot 计算 vs activity_legu 快照 vs index quotes） | 独立评估 |
| U-5 | `total_turnover` 的新候选（index_daily_quotes 聚合 / spot 求和） | 契约 + live-read | 独立评估 |
| U-6 | `hot_concepts` 的 concept_name_em top-N 契约 | live-read | 独立评估 |
| U-7 | `reason` / `order_ratio` 的可信来源（若 Pascal 需要） | 额外数据源调研 | Pascal 需求确认 |
| U-8 | SDK 版本 pin 策略（E20 漂移的根因确认：上游改名 vs 版本差异） | 版本对比 | U-1 |

---

## 9. 结论

- `sentiment.market_snapshot` **22 字段 canonical schema 不存在完整可信真实来源路径**；确定性可得仅 5 个（#1/#2/#3/#20/#21：3 唯一键 + 2 元数据），7 个条件可得（#4/#5/#15/#16/#18/#19/#22），7 个未知（#6/#7/#8/#9/#10/#11/#14），2 个恒 None（#12/#17），1 个推断被推翻（#13）。
- `sentiment.limit_up_pool` 的**个股池子子集**有 SDK 源码级候选；2026-08-03 交易日 live-read（E22）已验证 zt_pool / dtgc_pool **非空返回**（55 / 2 行，列名与 SDK 一致），`limit_up_count`/`limit_down_count` 等 COND 字段获得首笔交易日实证；但 `stock_market_fund_flow` 单次 `ConnectionError`、总体 **provider_evidence=fail**——局部池子端点非空**不得夸大为可激活 Provider**。`reason`/`order_ratio` 仍无来源。
- **时间语义（2026-08-03 裁定）**：`sentiment.market_snapshot` / `limit_up_pool` 当前目标为已完成交易日 / 收盘后 / 可重放；`snapshot_time` 当前仅 `close`；盘中实时情绪属未来独立 capability（独立 Provider/字段契约/freshness/时间边界/授权），不在本 Phase 3 范围。
- **`total_turnover`（#13）**：无合规来源时保持 `None`/unavailable；资金净流入不得映射（E15/E23 SDK 无「成交额」列 + E22 该 endpoint `ConnectionError`）。
- **推荐 defer + G-1 阶梯**：2026-08-03 已部分验证（zt_pool/dtgc 非空、列名对齐；fund_flow `ConnectionError`）；若 Pascal 批准，仅补测 fund_flow 1 次并完成 E20 漂移 re-anchor，将 COND 字段升级为可验证事实后再决定 capability 激活；**不创建 pseudo-provider、不注册未验证 capability、不重跑 B2/已耗尽预算**。
- 本卡零写入、零真实调用、零持久化副作用；仅新增 `docs/research/03_data/RESEARCH-03-014-p3c-sentiment-provider-feasibility.md` 一个文件（2026-08-03 live-read 由独立探针执行，本文件仅只读引用 E22）。
