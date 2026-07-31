# SPEC-03-016: 历史行业 sector.ranking 生产 Gate-1~4 受控激活 — 可执行契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-31 |
| 最后更新 | 2026-07-31（V0.2 + T2.2 修订：Gate-3 范围来源唯一化 / 交易日 CompletedSessionPolicy / 过滤白名单统一；V0.2 + T2.3 修订：Gate-3 canary 与全量范围来源互斥冻结） |
| 版本号 | V0.2 |
| 来源 RFC | RFC-03-016-historical-sector-ranking-production-rollout（V0.1） |
| 目标模块 | 03_data（数据层）— production rollout |
| 适配 Agent | YQuant-Developer-Engineer（Gate 工具 Implement）、YQuant-Test-Engineer（独立只读 Verify） |
| 标签 | #data #unified_data #sector #ranking #production #rollout #gate #mongodb |

---

## 0. 术语对齐与基线锚定

本 SPEC 定义 03-016 生产 rollout 的**可执行契约**。03-015 已冻结的离线语义（9 字段 schema、pct_chg 固定口径、100% exact-match、结果语义冻结表 Category 1~4、warning token `historical-ranking-empty` / `historical-ranking-incomplete`、source_trace 枚举 `{complete|incomplete|empty}` / `{ok|miss}`）**全部继承，本 SPEC 不重复定义、不修改**。冲突时以 03-015 为准（03-015 是数据语义基线，03-016 是生产激活动作基线）。

### 0.1 本 SPEC 不重复定义的契约

- `SectorRankingDaily` 9 字段 schema 与校验：SPEC-03-015 §3.2.1（H-009 ~ H-018）
- 唯一键与 upsert 语义：SPEC-03-015 §3.2.2（H-019 ~ H-021）
- dataset 枚举与禁混排：SPEC-03-015 §3.3（H-023 ~ H-029）
- 固定收益口径：SPEC-03-015 §3.4（H-030 ~ H-038）
- trade_date 证明与 realtime fallback 排除：SPEC-03-015 §3.5（H-039 ~ H-046）
- 缺数据 fail/empty 契约：SPEC-03-015 §3.6（H-047 ~ H-051c）
- TA-CN 只读上游映射：SPEC-03-015 §3.7（H-052 ~ H-060）
- 迁移隔离：SPEC-03-015 §3.8（H-061 ~ H-064）
- Source Trace 契约：SPEC-03-015 §3.9（H-065 ~ H-070）
- 结果语义冻结表：RFC-03-015 §5.6.3（Category 1~4 + 成功行）

---

## 1. 需求摘要

将 RFC-03-016 定义的 4 个生产 Gate（只读 smoke + 权威 universe → DDL → backfill → 读激活）落实为可执行的工具契约：每个 Gate 有独立 CLI（`--dry-run` 默认 / `--apply` 显式副作用）、固定 report 路径、明确的退出码、停止条件与幂等行为。工具实现阶段（T3）全部基于 mongomock/沙箱可测；真实执行只发生在 production activation 卡被 Pascal 显式触发之后。本 SPEC 的验收标准覆盖：每 Gate 的停止条件全部可测、产物路径固定、secrets 不泄露、真实执行语义无歧义。

---

## 2. 范围

### 2.1 In Scope

- [ ] Gate-1 工具：只读 smoke + 权威 expected universe 校验（查询预算、report 生成、停止条件）
- [ ] Gate-2 工具：DDL（createCollection + 唯一索引），dry-run 默认，幂等，只读 verify 前置
- [ ] Gate-3 工具：真实 backfill（dry-run / canary / 全量，日级原子，写后读回，失败停止）
- [ ] Gate-4 工具：读路径激活（binding 开关 + 只读 smoke + 冻结 token 行为验证）；交易日状态检查由可注入 CompletedSessionPolicy 执行（§3.5.7 G4-P-001~010）
- [ ] 每 Gate 的退出码、report 路径、审计证据格式
- [ ] 独立只读 Verify（yquanttester）判定标准与验收证据
- [ ] Gate 工具单元测试（mongomock 上覆盖停止条件与幂等性）

### 2.2 Out of Scope

- [ ] 不执行任何真实连接/DDL/DML/Provider/回填/服务/cron/Git 操作（本 SPEC 只定义契约）
- [ ] 不修改 03-015 冻结语义、P3-A 文件、文档模板
- [ ] 不创建 Mongo 账号/角色（OQ-016-1，Design 前置缺口）
- [ ] 不创建查询辅助索引 `idx_dataset_date`（Gate-2 范围外）
- [ ] 不定义增量更新/每日调度/cache/告警（未来 RFC）
- [ ] 不修改 router/fallback/provider/consumer/service（Gate-4 只激活读路径）

---

## 3. 功能规格

### 3.1 通用 CLI 契约（全部 Gate 工具共用）

| 编号 | 规则 | 说明 |
|---|---|---|
| G0-C-001 | `--dry-run` 默认 | 未显式传 `--apply` 时，工具只读/只计算/只打印计划，零副作用；退出码 0 |
| G0-C-002 | `--apply` 显式副作用 | 仅显式传 `--apply` 时执行本 Gate 的真实动作（查询写 report / DDL / backfill upsert / binding 切换） |
| G0-C-003 | `--apply` 前置确认 | `--apply` 必须伴随 `--yes`（或等价显式确认参数）；缺 `--yes` 视为 dry-run 并提示，不执行副作用 |
| G0-C-004 | 退出码语义 | `0`=成功；`1`=参数/前置校验失败；`2`=停止条件命中（SC 触发）；`3`=连接/凭据失败（fail-fast）；`4`=verify 失败 |
| G0-C-005 | secrets 脱敏 | 所有 stdout/stderr/log/report 输出必须脱敏：不得回显连接值（MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE 的值）；防御性扫描检测 `mongodb(+srv)://` URI 含凭据段 / 密码 / token / secret（泄露类别 `uri_with_credentials` / `password_value` / `token_value` / `secret_value`），命中即触发 SC-016-G0-1（URI 仅作泄露兜底扫描，**非允许连接形态**） |
| G0-C-006 | 超时 | 每次 Mongo 操作必须带超时（连接超时与 serverSelectionTimeout 由 Design 定义默认值，建议 ≤10s）；禁止无限等待 |
| G0-C-007 | 产物目录 | `data/rollout/sector-ranking/`；工具必须 `mkdir -p` 该目录；report 文件名带 Gate 前缀 |
| G0-C-008 | 日志 | 工具必须输出结构化日志（JSON lines 或等价），含每步动作、耗时、结果计数；日志写入 `data/rollout/sector-ranking/logs/` |
| G0-C-009 | 重复执行 | 工具重复执行不得改变已有状态（幂等）；同参数重跑结果一致 |
| G0-C-010 | 时间戳 | 所有 report/log 记录 UTC ISO-8601 时间戳；report 文件名可含 `YYYYMMDD` 日期段（便于归档，不得覆盖历史 report） |

#### 连接契约（CL-1 ~ CL-6，唯一受控连接源）

全部 Gate 工具共用的连接来源（RFC CR-016-1/2、DESIGN-03-016 V0.2 §3.3.2）：

| 编号 | 规则 |
|---|---|
| CL-1 | 连接源 = 环境中的 `MONGODB_HOST` / `MONGODB_PORT` / `MONGODB_USERNAME` / `MONGODB_PASSWORD` / `MONGODB_DATABASE` 五键（RFC CR-016-1 唯一受控连接源）。组件式构造：`pymongo.MongoClient(host=..., port=int(...), username=..., password=..., authSource=MONGODB_DATABASE)`；**不允许 URI**（无 `{PREFIX}_URI`、无 `mongodb://` 串）、不允许任意 prefix（CLI 无 `--conn`/prefix 参数） |
| CL-2 | 数据库名 = `MONGODB_DATABASE`；`authSource` = `MONGODB_DATABASE`（固定值，不引入 `AUTH_SOURCE` 键） |
| CL-3 | 缺失任一必需键（5 键全必需，`MONGODB_PORT` 无默认值）→ fail-fast 退出码 3（SC-016-G0-2），仅报告缺失键名（不含值） |
| CL-4 | Client 选项：`serverSelectionTimeoutMS=10000`、`connectTimeoutMS=10000`（G0-C-006 ≤10s） |
| CL-5 | 测试替身：构造参数 `client_factory` 显式注入 mongomock 的 `MongoClient`（或等价注入）；测试**不得读取环境**（零真实 I/O） |
| CL-6 | 任何位置不得打印连接值（host/port/username/password/db 值）；report 连接身份字段一律用 `conn_source` + `conn_fingerprint`（不用 `conn_prefix`）；`conn_fingerprint` 只含结构字段（source 标签 + keys_present + auth_configured），**不含 username 的任何可逆/可识别信息** |

#### 停止条件（通用）

| 编号 | 触发 | 处理 | 退出码 |
|---|---|---|---|
| SC-016-G0-1 | 输出中检测到 secrets（连接值回显 / URI 含凭据段 / 密码 / token） | 立即停止；report 标注泄露；提示 rotate | 2 |
| SC-016-G0-2 | 连接/认证失败（连接拒绝、超时、认证失败） | 停止；不降级、不换连接 | 3 |

### 3.2 Gate-1 契约：只读 smoke + 权威 expected universe

#### 3.2.1 CLI 签名

```text
gate1_smoke.py [--apply] [--yes]
               [--min-trade-date YYYY-MM-DD] [--max-trade-date YYYY-MM-DD]
               [--report-dir data/rollout/sector-ranking]
```

- 连接源：CLI **不接收连接源选择参数**；连接一律从环境读取唯一受控 `MONGODB_*` 五键组件式构造（§3.1 连接契约 CL-1~3）；缺失任一必需键 → fail-fast EXIT_CONN(3)，仅报告缺失键名。
- `--min-trade-date` / `--max-trade-date`：可选；缺省时探测全部可用范围。
- `--apply`：执行真实只读查询并写 report；缺省为 dry-run（只打印查询计划与预算检查）。

#### 3.2.2 查询预算（G1-B-001 ~ G1-B-007）

| 编号 | 规则 | 说明 |
|---|---|---|
| G1-B-001 | 查询类型白名单 | 只允许：`count_documents` / `distinct` / `find`（带过滤）/ 聚合 `$match+$group`（带过滤）；禁止无过滤全集合扫描 |
| G1-B-002 | 过滤强制 | 每次 `find` / 聚合必须带过滤字段，白名单 = {`sector_code`（SW L1 前缀 `801*`）, `trade_date` 范围, `market`}（至少一个）；`find` 的 filter 与 `aggregate` pipeline 第一个 stage（必须为 `$match`）使用**同一校验规则**；空 filter / 空 pipeline / 首 stage 非 `$match` / 白名单外字段 → `BudgetViolation`（G1-S-007） |
| G1-B-003 | 结果条数上限 | 单次 `find` 返回 ≤ 1000 条；超限必须按 `trade_date` 分片重查 |
| G1-B-004 | 超时上限 | 单次查询 serverSelectionTimeoutMS ≤ 10s；单次查询 maxTimeMS ≤ 30s |
| G1-B-005 | 扫描保护 | 禁止 `find({})` / `aggregate([])` 无过滤；工具启动时静态校验查询构造（白名单之外抛参数错误） |
| G1-B-006 | 记录范围上限 | Gate-1 全量 report 的最大记录数 10 万条（按 trade_date 分片时累计）；超限停止并提示缩小范围 |
| G1-B-007 | 预算审计 | report 记录每类查询的发起次数、返回条数、耗时；任何预算违规记录为 G1-C-FAIL |

#### 3.2.3 校验项（G1-C-001 ~ G1-C-007）

| 编号 | 校验项 | 通过标准 | 失败动作 |
|---|---|---|---|
| G1-C-001 | SW L1 code/name 权威枚举 | 从 `tradingagents.index_basic_info`（或 Design 确认的等效权威来源）读取 SW L1 行业指数；`sector_code` 唯一；code 前缀为 SW 一级行业（`801xxx`）；数量与申万 2021 一级行业体系一致 | 停止 `G1-C-FAIL`，退出码 2 |
| G1-C-002 | expected universe 固化 | 将 G1-C-001 结果写为 `gate1-report.json` 的 `expected_sector_codes` 数组（str 全表）与 `expected_sector_names` 映射；报告记录来源与校验时间 | 无 expected universe → 停止 |
| G1-C-003 | 可用 trade_date 范围 | 对 expected universe 全表执行 `distinct(trade_date)`；report 记录 min/max、总日数、逐日 coverage | 任一校验日 coverage<100% 且被选为 canary 候选 → 停止 |
| G1-C-004 | close/pre_close 完整性 | 每 `{sector_code, trade_date}` 有有限 `close`；`pre_close` 可从前一交易日 close 推导；report 记录缺失清单 | canary 候选日受影响 → 停止 |
| G1-C-005 | data_source/source 线索 | `source` 字段值分布统计；确认 SW L1 相关行 source 为可信历史值（`sw` 或等价）；检测 realtime/intraday/rt 标记 | 发现 realtime/intraday 标记 → 停止 |
| G1-C-006 | 数据集隔离 | 查询仅命中 SW L1 行业；不混入 concept/region/style | 混入 → 停止 |
| G1-C-007 | 连接/身份可用性 | 唯一受控连接源可读目标集合；报告记录 `conn_fingerprint`（仅结构字段，无连接值/username 可识别信息，CL-6） | 不可读 → 停止，退出码 3 |

#### 3.2.4 停止条件（G1-S-001 ~ G1-S-008）

| 编号 | 触发 | 处理 | 退出码 |
|---|---|---|---|
| G1-S-001 | 连接/认证失败 | 停止；不换连接 | 3 |
| G1-S-002 | G1-C-001 枚举失败（无权威 code/name） | 停止；不猜、不硬编码 | 2 |
| G1-S-003 | G1-C-001 出现重复/非法 sector_code | 停止 | 2 |
| G1-S-004 | expected universe 为空或无法固化 | 停止 | 2 |
| G1-S-005 | canary 候选日 coverage<100% 或 close/pre_close 缺失 | 停止；不降级阈值、不伪造 ranking | 2 |
| G1-S-006 | 检测到 realtime/intraday 标记的 SW L1 行 | 停止 | 2 |
| G1-S-007 | 查询预算违规（无过滤扫描 / 超限） | 停止 | 2 |
| G1-S-008 | 身份泄露告警（SC-016-G0-1） | 停止；rotate | 2 |

#### 3.2.5 Report 内容（G1-R-001 ~ G1-R-010）

`gate1-report.json` 必须包含：

| 编号 | 字段 | 说明 |
|---|---|---|
| G1-R-001 | `tool` / `version` / `timestamp` | 工具标识、版本、UTC 时间戳 |
| G1-R-002 | `conn_source` + `conn_fingerprint` | 连接源标签（固定 `MONGODB_*`）+ 结构指纹（`{source, keys_present, auth_configured}`）；均不含连接值或 username 可识别信息（CL-6） |
| G1-R-003 | `query_budget` | 预算执行统计（每类查询次数/条数/耗时） |
| G1-R-004 | `expected_sector_codes` | 权威 SW L1 code 全表（str 数组） |
| G1-R-005 | `expected_sector_names` | code→name 映射（str→str） |
| G1-R-006 | `trade_date_range` | min/max 可用 trade_date |
| G1-R-007 | `coverage_by_date` | 逐日 coverage（`{trade_date: {expected, observed, ratio}}`） |
| G1-R-008 | `source_distribution` | `source` 值分布；realtime 标记检测结果 |
| G1-R-009 | `canary_candidates` | 100% 完整的 completed trade_date 候选清单（用于 Gate-3 canary 选定） |
| G1-R-010 | `checks` / `stop_conditions_hit` | 每个 G1-C-xxx 通过/失败 + 停止条件命中记录 |

`gate1-report.md` 为人读摘要：结论（PASS/STOP）、关键统计、canary 候选、失败项清单。

#### 3.2.6 Gate-1 Verify 判定（yquanttester 只读）

| 编号 | 判定项 | 通过标准 |
|---|---|---|
| G1-V-001 | report 存在且格式完整 | `gate1-report.json` + `.md` 存在；JSON schema 校验通过（G1-R-001~010 全部字段） |
| G1-V-002 | 无停止条件命中 | `stop_conditions_hit` 为空 |
| G1-V-003 | expected universe 完整性 | `expected_sector_codes` 非空且与权威来源一致（抽查 5 个 code/name） |
| G1-V-004 | 无 secrets | report/log 静态扫描泄露类别为空（无连接值回显 / URI 含凭据段 / 密码 / token） |
| G1-V-005 | 无越权写 | 复查目标集合 `estimatedDocumentCount` 在 smoke 前后一致（只读证明） |

### 3.3 Gate-2 契约：DDL（新集合 + 唯一索引）

#### 3.3.1 CLI 签名

```text
gate2_ddl.py [--apply] [--yes]
             [--collection 03_data_ud_sector_ranking_daily]
             [--report-dir data/rollout/sector-ranking]
```

#### 3.3.2 DDL 规格（G2-D-001 ~ G2-D-006）

| 编号 | 动作 | 规格 | 幂等行为 |
|---|---|---|---|
| G2-D-001 | createCollection | `tradingagents.03_data_ud_sector_ranking_daily` | 已存在 → 跳过并报告；不存在 → 创建 |
| G2-D-002 | 唯一索引 | name=`uniq_dataset_date_sector`；key=`{"dataset":1, "trade_date":-1, "sector_code":1}`；unique=true；background=false | 已存在且规格一致 → 跳过；已存在但规格不一致 → **停止**（G2-S-003） |
| G2-D-003 | 查询辅助索引 | `idx_dataset_date` | **不创建**（本 Gate 范围外，RFC §5.3 决策） |
| G2-D-004 | namespace 白名单 | 工具只允许操作 `tradingagents.03_data_ud_sector_ranking_daily`；其他集合的读写均拒绝 | 越权 → 停止 |
| G2-D-005 | 禁止操作清单 | 不得创建/修改/删除任何其他集合或索引（含 cache/audit/quality/业务集合） | 检测到 → 停止 |
| G2-D-006 | 前置只读 verify | `--apply` 前必须执行只读 verify：集合/索引不存在（或存在但规格一致）；目标数据库可达 | verify 失败 → 停止，不执行 DDL |

#### 3.3.3 停止条件（G2-S-001 ~ G2-S-006）

| 编号 | 触发 | 处理 | 退出码 |
|---|---|---|---|
| G2-S-001 | 连接/认证失败 | 停止 | 3 |
| G2-S-002 | 前置 verify 失败（数据库不可达 / 目标状态异常） | 停止，不执行 DDL | 4 |
| G2-S-003 | 索引已存在但规格不一致 | 停止；不 drop 重建、不覆盖 | 2 |
| G2-S-004 | 尝试操作白名单外集合 | 停止 | 2 |
| G2-S-005 | 检测到目标集合外新建集合/索引 | 停止 | 2 |
| G2-S-006 | 身份泄露告警 | 停止；rotate | 2 |

#### 3.3.4 审计证据（G2-A-001 ~ G2-A-004）

| 编号 | 证据 | 内容 |
|---|---|---|
| G2-A-001 | dry-run 日志 | 计划执行的 DDL 动作清单（无副作用） |
| G2-A-002 | apply 日志 | 实际执行动作 + 每步结果 |
| G2-A-003 | 只读 verify 快照 | `db.getCollectionInfos()` / `db.getCollection().getIndexes()` 的集合/索引规格快照（不含 secrets） |
| G2-A-004 | 越权扫描结果 | 工具内置扫描：确认无白名单外集合/索引变更 |

#### 3.3.5 Gate-2 Verify 判定（yquanttester 只读）

| 编号 | 判定项 | 通过标准 |
|---|---|---|
| G2-V-001 | 集合存在 | `getCollectionInfos` 中 `03_data_ud_sector_ranking_daily` 存在 |
| G2-V-002 | 唯一索引正确 | `getIndexes` 中 `uniq_dataset_date_sector` 存在，key/unique 与 G2-D-002 一致 |
| G2-V-003 | 无多余索引/集合 | 目标集合无 `idx_dataset_date`；无白名单外新集合 |
| G2-V-004 | 无越权写 | 复查其他关键集合（`portfolio_*` 抽样）`estimatedDocumentCount` 前后一致 |
| G2-V-005 | 无 secrets | 日志/快照静态扫描无 secrets |

### 3.4 Gate-3 契约：真实 TA-CN 历史 backfill

#### 3.4.1 CLI 签名

```text
gate3_backfill.py --expected-file <gate1-report.json 路径>
                  [--range-file PATH]
                  [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
                  [--canary-date YYYY-MM-DD] [--apply] [--yes]
                  [--report-dir data/rollout/sector-ranking]
```

- `--expected-file`：必须传入 Gate-1 report（含 `expected_sector_codes` / `expected_sector_names`）；**禁止**代码内硬编码 universe（03-015 H-049u）。
- `--canary-date`：至多 1 个由 Gate-1 证据选定的 completed trade_date；传 `--canary-date` 且未传 `--apply` → dry-run 计划；传 `--canary-date` + `--apply` → 执行 canary 并写后读回，**不**继续全量。**canary 单日模式仅在无任何全量范围来源（无 `--range-file`、无 `--start-date`、无 `--end-date`）时合法**；`--canary-date` 与任何全量范围来源互斥——与 `--range-file` 同时传入 → EXIT_PARAM(1)；与成对 `--start-date`/`--end-date` 同时传入 → EXIT_PARAM(1)；与不成对 start/end 同时传入仍按缺配对 → EXIT_PARAM(1)（均 G3-S-003）。
- 全量模式必须提供**一种范围来源**：`--range-file PATH`（Gate-1 report JSON 路径，取 `coverage_by_date` 有效交易日，默认排除最早可用日）**或**成对 `--start-date`/`--end-date`（Pascal 显式子范围）。`--range-file` 与 `--start-date`/`--end-date` **互斥**；无任何范围来源 → EXIT_PARAM(1)（G3-S-003）；全量范围来源不得与 `--canary-date` 组合（G3-S-003）。范围语义见 G3-B-001 / G3-B-013~016。

#### 3.4.2 日期范围与批次（G3-B-001 ~ G3-B-004 / G3-B-013 ~ G3-B-016）

| 编号 | 规则 | 说明 |
|---|---|---|
| G3-B-001 | 范围来源 | 全量范围二选一：`--range-file PATH`（Gate-1 report JSON，范围 = `coverage_by_date` 键集，默认排除最早可用日）或成对 `--start-date`/`--end-date`（Pascal 显式子范围，⊆ Gate-1 `trade_date_range`）；二者互斥；无任何范围来源 → EXIT_PARAM(1)；范围校验经 CompletedSessionPolicy 判定非未来日、非「当日未收盘」（G4-P-001~010） |
| G3-B-002 | 日级原子 | 每个 `trade_date` 独立处理：读取 → 构建（100% exact-match）→ upsert → 写后读回；任一日失败即停止后续日 |
| G3-B-003 | 处理顺序 | 按 `trade_date` 升序处理（保证前一日 close 推导可用） |
| G3-B-004 | 前一日推导 | `pre_close` 从该 `sector_code` 前一交易日 `close` 取；前一日无数据 → 该行不入库（SPEC-03-015 H-047/H-048） |
| G3-B-013 | `--range-file` 语法与包含日期 | 值为 Gate-1 report JSON 路径（与 `--expected-file` 相同的 `gate1-report.json`）；范围 = 其中 `coverage_by_date` 的键（Gate-1 已确认可用交易日），**不**取 `trade_date_range` 的 min/max 闭区间（避免纳入未覆盖日） |
| G3-B-014 | 排序/去重 | 处理日按 `trade_date` 升序、去重；重复键只处理一次（G3-B-003 保证前一日 close 推导可用） |
| G3-B-015 | 范围上限与互斥 | 处理日数 ≤ `coverage_by_date` 键数；`--range-file` 与 `--start-date`/`--end-date` 互斥，同时传入 → EXIT_PARAM(1)（G3-S-003）；`--start-date`/`--end-date` 必须成对，缺一 → EXIT_PARAM(1)；`--canary-date` 与任何全量范围来源（`--range-file` 或成对 `--start-date`/`--end-date`）互斥，同时传入 → EXIT_PARAM(1)（G3-S-003）；canary 单日模式仅在无任何全量范围来源时合法 |
| G3-B-016 | 默认排除最早可用日 | `--range-file` 模式默认排除 `coverage_by_date` 最早日（首日无前一日 close → 必然 empty 失败，避免「自动失败」）；dry-run 计划显式说明排除的首日与理由；Pascal 显式传成对 `--start-date`/`--end-date` 可覆盖（显式模式不自动排除；若显式范围含最早日，该日按 G3-B-004 语义处理，无前一日 close → empty → G3-S-005 停止，不降级） |

#### 3.4.3 backfill 构建规则（G3-B-005 ~ G3-B-012）

| 编号 | 规则 | 说明 |
|---|---|---|
| G3-B-005 | 复用冻结构建 | 必须复用 03-015 `build_ranking_rows`（或等价纯函数）的语义：pct_chg 固定公式、100% exact-match、稳定排序、连续 rank |
| G3-B-006 | dataset 固定 | 写入 `dataset="sw2021_ta_cn"`（常量注入，不从 TA-CN 推断） |
| G3-B-007 | 日期格式转换 | TA-CN `YYYYMMDD` → 输出 `YYYY-MM-DD`（SPEC-03-015 H-053） |
| G3-B-008 | 禁止上游 pct_chg | 不使用 `index_daily_quotes.pct_chg`；用 close/pre_close 重算（H-032） |
| G3-B-009 | 禁止 realtime fallback | 任何 realtime/intraday/rt 标记行不入库（RT-4）；`trade_date` 必须已收盘（RT-1） |
| G3-B-010 | close/pre_close 有效性 | `close` 为有限数值且 `pre_close != 0`；缺失/非法 → 该行不入库 |
| G3-B-011 | sector_name 来源 | 从 Gate-1 `expected_sector_names` 取；缺失 → 该行不入库 |
| G3-B-012 | 物化不变式 | 仅 `BuildOutcome.status == "complete"` 的行 upsert；incomplete/empty 不物化、不返回部分榜单 |

#### 3.4.4 停止条件（G3-S-001 ~ G3-S-012）

| 编号 | 触发 | 处理 | 退出码 |
|---|---|---|---|
| G3-S-001 | 连接/认证失败 | 停止；不换连接 | 3 |
| G3-S-002 | `--expected-file` 缺失或 JSON schema 不完整 | 停止 | 1 |
| G3-S-003 | 日期范围非法（无任何范围来源；`--range-file` 与 `--start-date`/`--end-date` 同时传入；`--start-date` 缺 `--end-date`（或反之）；`--canary-date` 与任何全量范围来源同时传入〔`--range-file`，或成对 `--start-date`/`--end-date`；与不成对 start/end 仍按缺配对〕；start>end；超出 Gate-1 范围；含未来日或当日未收盘〔CompletedSessionPolicy，G4-P-004/005〕） | 停止 | 1 |
| G3-S-004 | 目标日 observed != expected（incomplete） | 该日失败；停止后续日；不降级、不伪造 | 2 |
| G3-S-005 | 目标日零有效行（empty） | 该日失败；停止后续日 | 2 |
| G3-S-006 | upsert `outcome.failed > 0` | 该日不认定成功；停止后续日 | 2 |
| G3-S-007 | 写后读回不一致（行数/字段/排序不符） | 停止；不自动回滚 | 2 |
| G3-S-008 | canary 失败（任一 G3-S-004~007 命中） | canary 不通过；不进入全量 | 2 |
| G3-S-009 | 尝试写目标集合外 | 停止 | 2 |
| G3-S-010 | 检测 realtime/intraday 标记混入 | 停止 | 2 |
| G3-S-011 | 身份泄露告警 | 停止；rotate | 2 |
| G3-S-012 | 任意未知异常 | 停止；report 记录异常栈（脱敏） | 2 |

**禁止自动动作**：失败后工具不自动 retry、不扩范围、不 drop、不删除已写入数据。修复后由 Pascal 显式重跑对应 trade_date（幂等 upsert 覆盖）。

#### 3.4.5 写后读回（G3-V-001 ~ G3-V-004）

| 编号 | 校验 | 标准 |
|---|---|---|
| G3-V-001 | 行数 | 读回行数 == expected_sector_codes 数量 |
| G3-V-002 | 字段完整 | 每行 9 字段完整且类型正确（SectorRankingDaily 校验通过） |
| G3-V-003 | 排序稳定 | 读回按 pct_chg DESC → sector_code ASC 排序 |
| G3-V-004 | 唯一键 | 无重复 `{dataset, trade_date, sector_code}` |

#### 3.4.6 审计证据（G3-A-001 ~ G3-A-005）

| 编号 | 证据 | 内容 |
|---|---|---|
| G3-A-001 | dry-run 计划 | 日期范围、每批预期行数、canary 日 |
| G3-A-002 | canary 报告 | canary 日构建结果 + 写后读回结果 |
| G3-A-003 | backfill 日志 | 每 trade_date 的 outcome（complete/incomplete/empty）、failed、upserted、耗时 |
| G3-A-004 | 全量汇总 | 成功日数 / 失败日数 / 停止条件命中记录 |
| G3-A-005 | 读回快照 | 抽样日的读回校验结果（G3-V-001~004） |

#### 3.4.7 Gate-3 Verify 判定（yquanttester 只读）

| 编号 | 判定项 | 通过标准 |
|---|---|---|
| G3-V-101 | canary 日数据正确 | 读回 canary 日：行数==expected、9 字段完整、排序稳定、唯一键 |
| G3-V-102 | 全量汇总无失败 | `outcome.failed==0` 对全部目标日；stop_conditions_hit 为空 |
| G3-V-103 | 无越权写 | 目标集合外无新增文档；其他集合 `estimatedDocumentCount` 前后一致 |
| G3-V-104 | 无 secrets | 日志/report 静态扫描无 secrets |
| G3-V-105 | 抽查跨日一致性 | 抽样 3 个 trade_date 的 pct_chg 用 close/pre_close 重算一致 |

### 3.5 Gate-4 契约：生产读路径激活

#### 3.5.1 CLI 签名

```text
gate4_activate.py --expected-file <gate1-report.json 路径>
                  [--enable|--disable] [--apply] [--yes]
                  [--smoke-dates YYYY-MM-DD[,YYYY-MM-DD]]
                  [--report-dir data/rollout/sector-ranking]
```

- 默认 `--disable`（安全默认）；`--enable` + `--apply` + `--yes` 才激活读路径 binding。
- `--smoke-dates`：只读 smoke 使用的日期（默认：Gate-1 canary 候选最近 1 个 + 1 个未物化日 + 1 个非法日期）。

#### 3.5.2 读路径契约（G4-R-001 ~ G4-R-006）

| 编号 | 规则 | 说明 |
|---|---|---|
| G4-R-001 | 直读物化集合 | `get_sector_ranking_history(trade_date, dataset)` 直读 `tradingagents.03_data_ud_sector_ranking_daily`，不经 router |
| G4-R-002 | 冻结 token 行为 | 未物化 → `DataResult.success(data=[], warnings=["historical-ranking-empty"])`；完整性失败 → `historical-ranking-incomplete`；成功 → 完整榜单 + `warnings=[]`（03-015 §5.6.3 逐字） |
| G4-R-003 | 交易日状态检查（CompletedSessionPolicy） | `trade_date` 非法格式 → 冻结 service `is_valid_trade_date` → `ValueError`（现有冻结行为，不改）；`trade_date` 为未来日 → policy 判定 `FUTURE` → `ValueError`（G4-P-004）；为当前交易日且市场未收盘 → policy 判定 `TODAY_UNCLOSED` → `ValueError`（Category 1，G4-P-005）；当日已收盘 / 历史交易日 / 非交易日 → 不抛错，正常读路径（G4-P-006/007）。检查由 Gate-4 工具层可注入 policy 执行（ProdRankingReader 读入口），**不是**修改 03-015 冻结 service |
| G4-R-004 | 不改 router/fallback/provider | 激活仅切换本能力 facade/feature binding；不得改动任何现有路由/回退/Provider 逻辑 |
| G4-R-005 | consumer/service 变更 | 本 Gate 不包含任何 consumer/service 变更；如发现需要 → 独立变更上报 Pascal |
| G4-R-006 | 回滚 = 禁用 binding | `--disable` 立即禁用读路径 binding；数据保留不删除 |

#### 3.5.3 只读 smoke（G4-V-001 ~ G4-V-008）

| 编号 | 用例 | 期望结果 |
|---|---|---|
| G4-V-001 | 成功日（canary 日）查询 | 完整榜单，`warnings=[]`，source_trace `completeness:complete, materialized:ok` |
| G4-V-002 | 未物化日查询 | `data=[]`，`warnings=["historical-ranking-empty"]`，trace `completeness:empty, materialized:ok` |
| G4-V-003 | 非法 trade_date（格式错误） | `ValueError` |
| G4-V-004 | 当日且未收盘 trade_date | `ValueError`（Category 1）——CompletedSessionPolicy 判定（G4-P-005）；离线由 fake calendar + fake clock 注入确定性验证（§6）；生产激活以受控 live calendar evidence 记录当日分类，未收盘交易会话下实跑断言，其余情况记录 evidence 与分类（未定义 → fail-closed 不激活） |
| G4-V-005 | 跨 dataset 混读 | 拒绝（`dataset` 强制过滤） |
| G4-V-006 | 排序稳定 | 返回按 pct_chg DESC → sector_code ASC |
| G4-V-007 | limit 参数 | `limit>0` 截断；`limit=0`/None 返回全部 |
| G4-V-008 | 无越权写 | smoke 全程只读；目标集合/其他集合无变更 |

#### 3.5.4 停止条件（G4-S-001 ~ G4-S-008）

| 编号 | 触发 | 处理 | 退出码 |
|---|---|---|---|
| G4-S-001 | 连接/认证失败 | 停止 | 3 |
| G4-S-002 | smoke 任一用例失败 | 停止；`--enable` 不生效（保持 disable） | 2 |
| G4-S-003 | 检测到 router/fallback/provider 被改动 | 停止 | 2 |
| G4-S-004 | 检测到 consumer/service 改动 | 停止；上报独立变更 | 2 |
| G4-S-005 | 读回数据与 Gate-3 快照不一致 | 停止 | 2 |
| G4-S-006 | 身份泄露告警 | 停止；rotate | 2 |
| G4-S-007 | 未物化/不完整时返回了部分榜单 | 停止（冻结 token 行为被破坏） | 2 |
| G4-S-008 | 任意未知异常 | 停止 | 2 |

#### 3.5.5 审计证据（G4-A-001 ~ G4-A-005）

| 编号 | 证据 | 内容 |
|---|---|---|
| G4-A-001 | binding 状态 | 激活前后 binding 开关状态快照 |
| G4-A-002 | smoke 结果 | 每个 G4-V-xxx 用例的输入/输出/结果 |
| G4-A-003 | 冻结 token 行为验证 | empty/incomplete/complete 三种情形实测记录 |
| G4-A-004 | 只读证明 | smoke 前后集合计数一致 |
| G4-A-005 | 越权扫描 | 无 router/fallback/provider/consumer/service 变更；diff 校验仅针对 activation 卡路径 allowlist / baseline manifest 比对（共享树既有 03-015 dirty 路径不在扫描范围，不得误触发越权停止） |

#### 3.5.6 Gate-4 Verify 判定（yquanttester 只读）

| 编号 | 判定项 | 通过标准 |
|---|---|---|
| G4-V-101 | smoke 全部通过 | G4-V-001~008 全部 PASS |
| G4-V-102 | 冻结 token 逐字一致 | 实际 warning token == 冻结 token |
| G4-V-103 | 无越权变更 | activation 卡路径 allowlist / baseline manifest 与基线 diff 为空（共享树既有 03-015 dirty 不计，OBS-2 闭合） |
| G4-V-104 | 回滚预案可执行 | `--disable` 后可恢复默认（未激活）状态 |
| G4-V-105 | 无 secrets | 日志/report 静态扫描无 secrets |

#### 3.5.7 交易日状态检查（CompletedSessionPolicy 契约，G4-P-001 ~ G4-P-010）

> 交易日状态判定由 Gate-4 工具层**新建可注入组件**执行（common.py 提供 `TradeCalendar` / `CompletedSessionPolicy`，F2 闭合）；**不是**修改 03-015 冻结 service（其 `_validate_trade_date` 仅做 `is_valid_trade_date` 格式校验，不判定交易日/收盘状态）。

| 编号 | 规则 | 说明 |
|---|---|---|
| G4-P-001 | 唯一输入 | `CompletedSessionPolicy.classify(trade_date: str, now: datetime) -> SessionStatus`；`trade_date` 先经 03-015 `is_valid_trade_date` 格式校验；`now` 为 UTC（生产 = 系统时钟；测试 = 注入 fake clock） |
| G4-P-002 | 唯一输出 | `SessionStatus` 枚举：`FUTURE` / `TODAY_UNCLOSED` / `TODAY_CLOSED` / `PAST_TRADING_DAY` / `PAST_NON_TRADING_DAY` |
| G4-P-003 | 时区/收盘 cutoff | 时区 = `Asia/Shanghai`；收盘 cutoff = 当日 15:00 CST（15:00 整视为已收盘）；`now` 转换到 Asia/Shanghai 后判定 |
| G4-P-004 | 未来日 | `trade_date > 今日` → `FUTURE` → 抛 `ValueError`（错误类别 `ERR_FUTURE_DATE`） |
| G4-P-005 | 当日未收盘 | `trade_date == 今日` 且 今日为交易日（`TradeCalendar.is_trading_day`）且 `now < cutoff` → `TODAY_UNCLOSED` → 抛 `ValueError`（`ERR_TODAY_UNCLOSED`，Category 1 语义） |
| G4-P-006 | 当日已收盘 | `trade_date == 今日` 且（今日非交易日 或 `now ≥ cutoff`）→ `TODAY_CLOSED` → 不抛错；读路径正常（未物化 → empty token） |
| G4-P-007 | 历史交易日/非交易日 | `trade_date < 今日`：交易日 → `PAST_TRADING_DAY`（不抛错）；非交易日 → `PAST_NON_TRADING_DAY`（不抛错；读路径未物化 → empty token） |
| G4-P-008 | 日历注入 | 判定依赖 `TradeCalendar.is_trading_day(date)`；离线测试注入 `FakeTradeCalendar` + fake clock（零真实 I/O，CL-5 同纪律）；生产默认不内置交易日历 → fail-closed：未取得受控日历证据时 policy 不可用，读路径拒绝（不猜测交易日状态） |
| G4-P-009 | 生产激活证据 | Gate-4 卡必须先取得受控 live calendar evidence（operator/Pascal 对照权威来源确认今日交易日历与收盘状态并记入 report）；未确认 → fail-closed，不激活 binding（G4-S-002 路径） |
| G4-P-010 | 归因边界 | 交易日状态检查由 Gate-4 工具层 policy 执行（`ProdRankingReader` 读入口）；冻结 service 不抛「未来日/当日未收盘」类 ValueError，文档不得将其归因于冻结 service |

---

## 4. 数据与接口契约

### 4.1 数据实体

| 实体 | 位置 | 说明 |
|---|---|---|
| `gate1-report.json` | `data/rollout/sector-ranking/` | Gate-1 证据（G1-R-001~010） |
| `gate1-report.md` | 同目录 | Gate-1 人读摘要 |
| Gate-2/3/4 report + logs | `data/rollout/sector-ranking/` | 各 Gate 审计证据 |
| 物化集合 | `tradingagents.03_data_ud_sector_ranking_daily` | 9 字段行（03-015 schema） |
| 唯一索引 | `uniq_dataset_date_sector` | `{dataset:1, trade_date:-1, sector_code:1}` unique |
| 上游只读集合 | `tradingagents.index_daily_quotes`、`tradingagents.index_basic_info` | Gate-1/3 读取 |

### 4.2 接口/函数

| 接口 | 契约 |
|---|---|
| `get_sector_ranking_history(trade_date: str, dataset: str, limit: int = 0) -> DataResult` | 03-015 冻结读路径；Gate-4 激活 |
| Gate CLI（gate1_smoke / gate2_ddl / gate3_backfill / gate4_activate） | §3.1~3.5 契约 |

### 4.3 兼容性约束

- 不修改 03-015 已实现代码语义；Gate-3 复用 `build_ranking_rows` 纯函数（或等价）。
- 不修改 P3-A / router / provider / consumer / service 现有行为。
- 生产连接复用 Gate-1 验证的唯一受控连接源（CR-016-1）。

### 4.4 幂等性/审计要求

- DDL：G2-D-001~006 幂等；索引规格不一致 → 停止。
- backfill：按唯一键 upsert 幂等；失败日可显式重跑。
- 读激活：binding 开关幂等。
- 审计：每 Gate report + logs + 独立只读 Verify（G1-V / G2-V / G3-V / G4-V）。

---

## 4.bis 持久化契约

| 存储对象（库.集合/表/路径） | 字段/索引 | 类型 | 必填 | 默认/派生规则 | 生命周期/TTL | 隐私级别 |
|---|---|---|---|---|---|---|
| `tradingagents.03_data_ud_sector_ranking_daily` | `dataset` | str | 是 | `sw2021_ta_cn`（常量注入） | 与行共存 | L1 |
| 同上 | `trade_date` | str | 是 | `YYYY-MM-DD`；已收盘历史交易日 | 与行共存 | L1 |
| 同上 | `sector_code` | str | 是 | SW L1 code（Gate-1 权威） | 与行共存 | L1 |
| 同上 | `sector_name` | str | 是 | Gate-1 `expected_sector_names` | 与行共存 | L1 |
| 同上 | `pct_chg` | float | 是 | `(close-pre_close)/pre_close*100` | 与行共存 | L1 |
| 同上 | `rank` | int | 是 | pct_chg DESC → sector_code ASC，1-based 连续 | 与行共存 | L1 |
| 同上 | `close` | float | 是 | 当日收盘指数 | 与行共存 | L1 |
| 同上 | `pre_close` | float | 是 | 前一交易日 close | 与行共存 | L1 |
| 同上 | `updated_at` | str | 是 | ISO-8601 UTC | 与行共存 | L1 |
| 唯一索引 | `uniq_dataset_date_sector` | — | 是 | `{dataset:1, trade_date:-1, sector_code:1}` unique | 常驻 | — |
| `data/rollout/sector-ranking/` | Gate report + logs | — | — | JSON/MD/JSONL | 保留至 Gate-4 后 30 天（Pascal 可调整） | 不含 secrets |

兼容性说明：新集合第一版只写入 `sw2021_ta_cn`；后续 dataset 扩展遵循 03-015 H-023~H-025 授权流程，不在本 rollout 内。

---

## 5. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-016-001 | RFC/SPEC 独立完整互引 | 静态检查：两份文档存在、交叉引用、无合并 |
| A-016-002 | 每 Gate 副作用矩阵齐备 | 静态检查 §5.1（RFC）与 §3（SPEC）一一对应 |
| A-016-003 | 无模糊生产语义 | 静态扫描：全文不含"按需 / 可选 / 由实现者决定"等生产语义（允许出现在 Out of Scope/非生产上下文） |
| A-016-004 | 授权≠执行 | 文档明确"授权已签署但未执行"；不把用户"全部授权"误写为动作已执行 |
| A-016-005 | Design inputs 齐备 | RFC §10/§11 + SPEC §3 提供每 Gate 工具输入/输出/文件范围/离线真实分离 |
| A-016-006 | 停止条件可测 | 每个 SC/G-S 编号在 SPEC 中有触发条件、处理、退出码 |
| A-016-007 | `git diff --check HEAD` 通过 | 实际运行无空白错误 |
| A-016-008 | 只新增两份文档 | `git status` 无其他新增/修改（P3-A 背景文件除外） |

---

## 6. 测试要求

- 单元测试（mongomock）：
  - Gate-1：预算白名单（G1-B-001~007）、校验项（G1-C-001~007）、停止条件（G1-S-001~008）
  - Gate-2：幂等（G2-D-001~002 重复执行）、规格不一致停止（G2-S-003）、namespace 白名单（G2-S-004）
  - Gate-3：日级原子（G3-B-002）、前一日推导（G3-B-004）、incomplete/empty 不物化（G3-B-012）、失败停止（G3-S-004~007）、写后读回（G3-V-001~004）、范围解析（G3-B-013~016 / G3-S-003：无范围来源 → 1、互斥 → 1、start 缺 end → 1、排除最早日）、canary/范围来源互斥三负例（`--canary-date` + `--range-file` → 1；`--canary-date` + 成对 `--start-date`/`--end-date` → 1；`--canary-date` + 不成对 start/end → 1〔按缺配对〕；canary 单日模式无范围来源时合法 → 0/dry-run 计划）
  - Gate-4：冻结 token 行为（G4-V-002/003/004）、排序（G4-V-006）、limit（G4-V-007）、CompletedSessionPolicy（G4-P-004~007 用 FakeTradeCalendar + fake clock 逐项断言，G4-V-004 正/反例）
- 集成测试：使用 mongomock + 显式 fixture（03-015 既有 fixture 复用），不触真实 Mongo。
- 测试替身（CL-5）：Gate 工具测试仅通过显式 `client_factory` 注入 mongomock（或等价注入）；测试零环境读取（不读 `MONGODB_*` 键、不触真实 Mongo）。
- 回归测试：03-015 定向测试 51/51 + 模块回归 1047/1047 必须保持 PASS（Gate 工具不得破坏离线语义）。
- 不可自动化验证项：真实 Mongo 连接与权限（由 production activation 卡 + Pascal 显式触发验证）；权威 expected universe（Gate-1 真实 smoke）。

---

## 7. 实现约束

- 禁止事项：真实连接/DDL/DML/Provider/回填/服务/cron/Git（本卡与 T3 沙箱阶段）；修改 03-015/P3-A/模板；硬编码 universe；自动 retry/rollback/drop；打印 secrets。
- 依赖限制：不新增第三方依赖（复用 pymongo/mongomock/dotenv 现有栈）。
- 连接实现约束：只允许 §3.1 连接契约（CL-1~6）的组件式五键构造；禁止 URI / `{PREFIX}_URI` / `--conn` / prefix / alias / fallback 连接形态。
- 性能/安全/风控约束：查询预算（G1-B）、超时（G0-C-006）、脱敏（G0-C-005）、namespace 白名单（G2-D-004）、只读证明（G1-V-005 等）。
- Gate 工具实现必须与 DESIGN-03-016 的 allowlist 对齐；实现阶段只新增 Gate 工具文件与测试，不修改既有文件。

---

## 8. 开放问题

- [ ] OQ-016-1：现有连接源是否满足最小权限（只读/只写/DDL 分离）→ Design 评估；若需新账号 → 单独授权
- [ ] OQ-016-2：`index_basic_info` 是否含 SW L1 权威 code/name → Gate-1 双源交叉核对；Design 定义回退来源（不含 alias 连接）
- [ ] OQ-016-3：canary 候选日选定规则细节（完整度最高的最近日 vs 最早日）→ Design 定义（基于 Gate-1 证据）
- [ ] OQ-016-4：全量 backfill 日期范围解析（Gate-1 全范围 vs Pascal 指定子范围）→ Design 定义 CLI 参数与校验
- [ ] OQ-016-5：Gate-4 后是否需要查询辅助索引 `idx_dataset_date` → 未来 RFC 评估，不并入本 rollout

---

## 9. 声明

本 SPEC 中涉及的板块/行业数据为辅助研究数据，不构成交易指令或投资建议。

本 SPEC 定义生产 rollout 的**契约**，不构成任何真实生产动作的已执行声明；所有 Gate 的真实执行仅在独立 Review PASS 后由 Pascal 显式触发 production activation 卡。

本 SPEC 不修改 RFC-03-015 / SPEC-03-015 / DESIGN-03-015 已冻结内容；所有新定义为新增，不与 P3-A 冻结基线冲突。

---

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.2（T2.3 修订） | 2026-07-31 | 评审 `t_99d11552` REVISE 闭合（F-1）：Gate-3 `--canary-date` 与全量范围来源互斥冻结——与 `--range-file` 同时传入 → EXIT_PARAM(1)、与成对 `--start-date`/`--end-date` 同时传入 → EXIT_PARAM(1)、与不成对 start/end 仍按缺配对 → EXIT_PARAM(1)；canary 单日模式仅在无任何范围来源时合法（§3.4.1 / G3-B-015 / G3-S-003）；§6 测试矩阵补三负例。**未改变** canary 候选选择、date range 计算、Gate-3 回填范围、任何生产动作与退出码总体集合 | YQuant-Codex-Principal |
| V0.2（T2.2 修订） | 2026-07-31 | 交叉文档闭合（Gate `t_e1611476` REVISE）：F1 Gate-3 范围来源唯一化（`--range-file` 进 CLI synopsis，与成对 `--start-date`/`--end-date` 互斥，无范围来源 → EXIT_PARAM(1)，G3-B-013~016）；F2 交易日状态判定由 Gate-4 可注入 CompletedSessionPolicy 执行（§3.5.7 G4-P-001~010，非冻结 service）；F3 G1-B-002 过滤白名单统一（sector_code / trade_date 范围 / market，find 与 aggregate 首 stage 同规则）；OBS-2 Gate-4 diff 校验收敛为 activation 卡路径 allowlist / baseline manifest | YQuant-Codex-Principal |
| V0.2 | 2026-07-31 | 评审 #865 闭合：SPEC 连接字段/CLI 与 RFC CR-016-1/2、DESIGN-03-016 V0.2 逐字统一——连接源收敛为唯一受控 `MONGODB_*` 五键组件式构造（§3.1 CL-1~3），CLI 移除 `--conn`/prefix 选择参数，report 字段 `conn_prefix` → `conn_source`/`conn_fingerprint`（G1-R-002），测试替身仅显式 `client_factory` 注入 mongomock（CL-5）。**未改变 Gate-1~4 业务语义、退出码与停止条件** | YQuant-Codex-Principal |
| V0.1 | 2026-07-31 | 初始创建：Gate-1~4 工具可执行契约（CLI/预算/校验/停止条件/report/Verify 判定）、数据与接口契约、测试要求、实现约束、开放问题 | YQuant-Codex-Principal |
