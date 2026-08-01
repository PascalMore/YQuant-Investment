# SPEC-03-017: 申万指数历史 quote metadata 治理（version/name 归一化）— 可执行契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-08-01 |
| 最后更新 | 2026-08-01 |
| 版本号 | V0.2 |
| 来源 RFC | RFC-03-017-sw-index-daily-quote-schema-governance（V0.2） |
| 目标模块 | 03_data（数据层）— `tradingagents.index_daily_quotes` 历史 metadata 治理 |
| 适配 Agent | YQuant-Developer-Engineer（T3 离线实现）、YQuant-Test-Engineer（T4 独立验证）、YQuant-Reviewer-Principal（T5 审查） |
| 标签 | #data #mongodb #governance #schema #metadata #idempotent #fail-closed |

---

## 0. 术语对齐与基线锚定

- **候选集（candidates）**：满足谓词 `P` 的 `index_daily_quotes` 文档。
- **谓词 `P`**：`data_source == "akshare"` 且 `full_symbol` 以 `.SI` 结尾。
- **权威 universe `U`**：`stock_sector_info`（`classify_system == "SW"`）的 `l1_code` 归一化后加 `.SI` 后缀的集合。
- **合规（compliant）**：`version` 为 BSON int 且值 == 1，且 `name` 字段不存在。
- **本 SPEC 不重复定义**：RFC-03-017 的动机、根因、备选方案、授权与执行分离（A-017-1/2）；冲突时以 RFC 为准。
- **硬边界**：本 SPEC 是**契约文档**，不连接、不修改 MongoDB；唯一被授权的未来生产写 = 对候选记录 `$set {version:1}` / `$unset {name:""}`（RFC A-017-2，未执行）。

---

## 1. 需求摘要

将 RFC-03-017 定义的历史 quote metadata 治理落实为可执行的工具契约：一个 runner 工具以 `census`（只读三重校验）→ `dry-run`（预期计数 + 有界样本）→ `apply`（生产 DML，显式触发）→ `verify`（写后只读 re-census）四模式运行；`census`/`dry-run`/`verify` 零副作用，`apply` 仅对候选记录做字段级 `$set`/`$unset`。工具全部基于 mongomock/fixture 可测；生产执行只在 Pascal 显式触发 production runner 之后发生。验收覆盖：fail-closed 门禁全可测、幂等、可恢复、验证方程全过、无 secrets、无越界写。

---

## 2. 范围

### 2.1 In Scope

- [ ] 候选谓词 `P` 的精确实现与文档化（`data_source == "akshare"` + `full_symbol` `.SI` 后缀）。
- [ ] 权威 universe `U` 的只读推导（`stock_sector_info` SW `l1_code` 归一化；C17-102，空 `U` → C17-103 STOP）。
- [ ] fail-closed 三重证据校验 gates（C17-201 ~ C17-205），观察项 C17-206（不阻断），串行顺序 C17-207；任一 FAIL 停止。
- [ ] dry-run 报告字段（R17-001 ~ R17-007）：候选统计、合规分类、字段/类型分布、有界样本（标识脱敏）、预期 mutation 计数。
- [ ] 幂等 mutation 语义（M17-001 ~ M17-007）：`$set {version:1}` / `$unset {name:""}`，无 upsert/replace/delete/DDL。
- [ ] 批次 / 检查点 / 恢复（B17-001 ~ B17-007）：batch_size、ordered=False、每批 checkpoint、stop-on-error、resume by `_id`。
- [ ] 验证计数方程（V17-001 ~ V17-006）与写后只读 re-census。
- [ ] 失败 / 回滚语义（F17-001 ~ F17-004）：无自动回滚/删除；`name` 恢复独立批准。
- [ ] 副作用矩阵（X17-001 ~ X17-006）。
- [ ] 工具单元测试（mongomock 覆盖门禁、幂等、恢复、方程）。
- [ ] 退出码契约（C17-002）与 CLI 契约（C17-001，C17-008 ~ C17-012）。

### 2.2 Out of Scope

- [ ] 不执行任何真实连接/DDL/DML/回填/服务/cron/Git 操作（本 SPEC 只定义契约）。
- [ ] 不修改 writer 代码（`sw_index_daily_service.py` / `historical_data_service.py`）。
- [ ] 不治理非候选记录（非 `.SI` 后缀、非 akshare 的 `.SI`）：仅 census 观察计数，不 mutate。
- [ ] 不设计 `name` 恢复的自动执行。
- [ ] 不创建/修改索引、集合、schema；不涉及 `03_data_ud_sector_ranking_daily` 或 03-016 Gate-3/Gate-4。
- [ ] 不修改文档模板、3 层 README、其他 RFC/SPEC/DESIGN 文件。

---

## 3. 功能规格

### 3.1 通用 CLI 契约（C17-001 ~ C17-012）

| 编号 | 规则 | 说明 |
|---|---|---|
| C17-001 | 模式 | `--mode {census,dry-run,apply,verify}`；`census` 为默认模式；`apply` 为显式副作用模式 |
| C17-002 | 退出码 | `0`=成功；`1`=参数/前置校验失败；`2`=停止条件命中（gate FAIL / 方程 FAIL）；`3`=连接/凭据失败（fail-fast）；`4`=verify 失败 |
| C17-003 | census 零副作用 | `census`/`dry-run`/`verify` 只读（find/aggregate/count/distinct），零写操作 |
| C17-004 | apply 显式副作用 | 仅 `--mode apply` 执行 `$set`/`$unset`；必须伴随 `--yes`（或等价显式确认），缺 `--yes` 视为 dry-run 并提示 |
| C17-005 | secrets 脱敏 | 所有 stdout/stderr/log/report 不得回显连接值（MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE 的值）；连接身份一律用 `conn_source` + `conn_fingerprint`（仅结构字段：source 标签 + keys_present + auth_configured） |
| C17-006 | 超时 | 每次 Mongo 操作带超时（连接/selection ≤10s，单次查询 maxTimeMS ≤30s）；禁止无限等待 |
| C17-007 | 产物目录 | `data/rollout/index-daily-quote-governance/`；工具 `mkdir -p`；report 文件名带 run_id 与日期，不覆盖历史 |
| C17-008 | 审计日志 | JSONL，记录每批 counts/errors/耗时；写入 `data/rollout/index-daily-quote-governance/logs/` |
| C17-009 | 幂等 | 工具重复执行不改变已有状态；同参数重跑结果一致 |
| C17-010 | 时间戳 | 所有 report/log 记录 UTC ISO-8601 时间戳 |
| C17-011 | `--batch-size` | 默认 500，范围 1..1000，非法值 → EXIT_PARAM(1) |
| C17-012 | 连接源 | 复用 RFC-03-016 唯一受控连接源约定：环境五键组件式构造（MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE）；**不允许 URI/prefix/alias/fallback**；缺失任一必需键 → fail-fast EXIT_CONN(3)，仅报告缺失键名 |

#### 停止条件（通用）

| 编号 | 触发 | 处理 | 退出码 |
|---|---|---|---|
| SC-017-G0-1 | 输出中检测到 secrets（连接值回显 / URI 含凭据段 / 密码 / token） | 立即停止；report 标注泄露；提示 rotate | 2 |
| SC-017-G0-2 | 连接/认证失败（拒绝/超时/认证失败） | 停止；不降级、不换连接 | 3 |

### 3.2 候选集与权威 universe（C17-101 ~ C17-106）

| 编号 | 规则 | 说明 |
|---|---|---|
| C17-101 | 谓词 `P` | `{ "data_source": "akshare", "full_symbol": { "$regex": "\\.SI$" } }`（精确字符串后缀）；禁止前缀/模糊猜测 |
| C17-102 | 权威 universe `U` | `stock_sector_info` 中 `classify_system == "SW"` 的 distinct `l1_code`，每个归一化为 6 位数字 + `.SI` 后缀（归一化逻辑与 `SwIndexDailyService._normalize_code` 一致：去后缀、取 `.` 前部分、大写） |
| C17-103 | U 非空前置 | `U` 为空 → 停止（EXIT_STOP=2），报告 `stock_sector_info` 无 SW 记录 |
| C17-104 | 候选非空处理 | `total_candidates == 0` → 成功 no-op（退出码 0），report 标注 "nothing to do" |
| C17-105 | 候选 `_id` 固化 | census 阶段固化候选 `_id` 列表（或分页键），apply/verify 不重新用谓词查询 |
| C17-106 | 只读边界 | census 只读 `index_daily_quotes`（P 命中）与 `stock_sector_info`（U 推导）；禁止读其他集合 |

### 3.3 Fail-closed 三重证据校验（C17-201 ~ C17-207）

| 编号 | Gate | 通过条件 | 失败动作 |
|---|---|---|---|
| C17-201 | 后缀证据 | 100% 候选 `full_symbol` 以 `.SI` 结尾；distinct 后缀集合 == `{".SI"}` | STOP（EXIT_STOP=2），报告分布 |
| C17-202 | data_source 证据 | 100% 候选 `data_source == "akshare"`；distinct 集合 == `{"akshare"}` | STOP，报告分布 |
| C17-203 | code-family 证据 | P 内 `distinct(full_symbol)` ⊆ U；反例（P 内不在 U 中）计数 == 0 | STOP，报告反例清单（full_symbol + trade_date 计数） |
| C17-204 | market 证据 | 100% 候选 `market == "CN"`（字段存在时）；缺失 market 计数 == 0 | STOP，报告分布 |
| C17-205 | period 证据 | 100% 候选 `period == "daily"`（字段存在时）；缺失 period 计数 == 0 | STOP，报告分布 |
| C17-206 | 观察项（不阻断） | 非候选观察计数：`.SI` 但非 akshare 记录数、akshare 但非 `.SI` 的 SW 候选数（仅报告） | 无 |
| C17-207 | gate 顺序 | C17-201 → C17-202 → C17-203 → C17-204 → C17-205 串行执行；任一 FAIL 即停止，后续 gate 不执行 | — |

### 3.4 合规分类（C17-301 ~ C17-304）

| 编号 | 分类 | 定义 |
|---|---|---|
| C17-301 | `already_compliant` | `version` 为 BSON int 且 ==1 且 `name` 不存在 |
| C17-302 | `missing_version` | `version` 字段缺失（无论 `name` 存在与否） |
| C17-303 | `nonconforming_version` | `version` 存在但非 BSON int 或值 ≠ 1（float/str/int!=1 等） |
| C17-304 | `name_present` / `name_absent` | `name` 字段存在（任意类型）/ 不存在 |

派生计数：`version_fix_needed = missing_version + nonconforming_version`；`both_needed = version_fix_needed ∧ name_present` 的候选数。

### 3.5 Dry-run 报告字段（R17-001 ~ R17-007）

| 编号 | 报告段 | 字段 |
|---|---|---|
| R17-001 | 运行元信息 | `run_id`、`mode`、`ts_utc`、`conn_source`、`conn_fingerprint`（仅结构）、`collection`、`predicate` 序列化 |
| R17-002 | 候选统计 | `total_candidates`、`total_docs_scanned` |
| R17-003 | 合规分类 | `already_compliant`、`missing_version`、`nonconforming_version`、`version_fix_needed`、`name_present`、`name_absent`、`both_needed` |
| R17-004 | 字段/类型分布 | `version` 类型直方图（absent/int==1/int!=1/float/str/other）、`name` 类型直方图（absent/str/non-str）、受保护字段存在性计数（full_symbol/code/symbol/market/trade_date/period/open/high/low/close/pre_close/volume/amount/pct_chg/data_source/created_at/updated_at） |
| R17-005 | 有界样本 | 每类（already_compliant/missing_version/nonconforming_version/name_present/both_needed）至多 5 条；每条仅 `id_prefix`（`_id` 前 6 位 hex，其余脱敏）、`full_symbol`、`trade_date`、`name_presence`、`version_summary`；**不输出原始 name 值、完整 _id、凭据** |
| R17-006 | 预期 mutation | `expected_set_version_ops`、`expected_unset_name_ops`、`expected_update_docs`（V17-003 方程） |
| R17-007 | gate 结果 | 每个 gate（C17-201~205）pass/fail + 证据计数 |

### 3.6 幂等 Mutation 语义（M17-001 ~ M17-007）

| 编号 | 规则 |
|---|---|
| M17-001 | 对每个候选：`version` 缺失或不合规 → `$set {version: 1}`；`name` 存在 → `$unset {name: ""}`；可合并为单条 `update_one({"_id": id}, {"$set": {"version": 1}, "$unset": {"name": ""}})` |
| M17-002 | **无 upsert**（`upsert=False`）、无 replace_one、无 delete_one、无 insert |
| M17-003 | 逐条按 `_id` 定位（census 固化的 `_id` 列表）；批次内不重新用谓词查询 |
| M17-004 | 除 `version`、`name` 外不得触碰任何字段（`_id`/full_symbol/code/symbol/market/trade_date/period/OHLCV/pct_chg/change/data_source/created_at/updated_at/未知字段全部保留） |
| M17-005 | 幂等：已合规记录重跑 no-op（matched 但 modified=0）；分类阶段直接跳过已合规 |
| M17-006 | 无 DDL：不创建集合/索引，不修改既有索引 |
| M17-007 | 写目标仅限 `tradingagents.index_daily_quotes` |

### 3.7 批次 / 检查点 / 恢复（B17-001 ~ B17-007）

| 编号 | 规则 |
|---|---|
| B17-001 | batch_size 默认 500（1..1000，C17-011）；每批至多 `batch_size` 条 update_one |
| B17-002 | 批内 `bulk_write(ordered=False)`；操作彼此独立 |
| B17-003 | 候选按 `_id` 升序排序处理；`_id` 为稳定 resume key |
| B17-004 | 每批写完后持久化 checkpoint `{batch_seq, batch_start_id, batch_end_id, matched, modified, ts_utc}`（JSONL）；checkpoint 成功后进入下一批 |
| B17-005 | stop-on-error：任一批失败 → 立即停止；瞬态错误有界重试 ≤2 次，重试耗尽即停止；不自动扩批/继续 |
| B17-006 | 恢复：从最后成功 checkpoint 恢复；恢复查询 = `P` ∧ `_id > batch_end_id`；已修复记录分类为已合规并跳过 |
| B17-007 | 审计日志每批追加 counts/errors/耗时到 `data/rollout/index-daily-quote-governance/logs/` |

### 3.8 验证计数方程（V17-001 ~ V17-006）

| 编号 | 方程 | 失败动作 |
|---|---|---|
| V17-001 | `total_candidates == already_compliant + missing_version + nonconforming_version == name_present + name_absent` | census 校验失败（EXIT_PARAM=1） |
| V17-002 | `version_fix_needed == missing_version + nonconforming_version` | census 校验失败 |
| V17-003 | `expected_set_version_ops == version_fix_needed`；`expected_unset_name_ops == name_present`；`expected_update_docs == version_fix_needed + name_present − both_needed` | dry-run 校验失败 |
| V17-004 | 写后：`post_total_candidates == pre_total_candidates`（无增删） | verify FAIL（EXIT_VERIFY=4） |
| V17-005 | 写后：`post_version_conforming == post_total_candidates`；`post_name_absent == post_total_candidates` | verify FAIL |
| V17-006 | 写后：累计 `modified_count == expected_update_docs`；累计 `matched_count ≥ modified_count`；受保护字段存在性计数 == pre 分布 | verify FAIL |

### 3.9 失败 / 回滚语义（F17-001 ~ F17-004）

| 编号 | 规则 |
|---|---|
| F17-001 | 无自动回滚、无自动删除；中断 → 从 checkpoint 恢复（幂等收敛） |
| F17-002 | `version: 1` 为终态；重复 apply 为 no-op |
| F17-003 | `name` 恢复仅允许在独立批准的 recovery 操作中执行（从 `stock_sector_info` `l1_code→l1_name` 映射按候选 `full_symbol` 重建回写）；不属于本 RFC，需单独授权 |
| F17-004 | 失败现场保留：checkpoint、审计日志、report 全部保留；不清理、不覆盖 |

### 3.10 副作用矩阵（X17-001 ~ X17-006）

| 编号 | 动作类别 | 目标 | 写? | 授权状态 |
|---|---|---|---|---|
| X17-001 | 只读 census / dry-run | `index_daily_quotes`（P 命中 + 分布）、`stock_sector_info`（U） | 否 | 未来 runner 一部分；Verify/Review 通过 + Pascal 显式触发后执行 |
| X17-002 | 离线代码 / 测试 | mongomock / fixture，零真实 I/O | 否 | 本流水线 T3/T4 |
| X17-003 | **生产 DML** | 仅候选记录：`$set {version:1}` / `$unset {name:""}` | **是（唯一授权写）** | 未执行；Verify/Review 通过 + Pascal 显式触发 |
| X17-004 | 写后只读验证 | `index_daily_quotes` re-census | 否 | 随 DML 执行 |
| X17-005 | 服务重启/同步/调度、03-016 Gate-3/Gate-4、DDL/索引 | — | — | **不授权** |
| X17-006 | 无关集合写入 | 任何非 `index_daily_quotes` 集合 | — | **不授权** |

---

## 4. 数据与接口契约

- 数据实体：`tradingagents.index_daily_quotes`（候选记录）+ `tradingagents.stock_sector_info`（权威 universe，只读）。
- 接口/函数（未来 runner，模块名由 Design 定）：
  - `build_predicate()` → `P`（dict filter）
  - `derive_universe(db)` → `U`（set[str]）
  - `run_census(db, P, U)` → census report（含 gate 结果、分类计数、分布、`_id` 列表）
  - `plan_mutation(census)` → dry-run report（预期计数 + 样本）
  - `apply_mutation(db, ids, batch_size, checkpoint_path)` → JSONL audit + checkpoint
  - `verify(db, P, pre_stats)` → verify report（V17-004~006）
- 兼容性约束：不改动 writer 代码；不修改既有索引（`uk_full_symbol_trade_date`、`idx_trade_date`、`idx_code` 等）；不创建新索引。
- 幂等性/审计要求：apply 幂等；每批 checkpoint；JSONL 审计；report 不覆盖历史。

## 4.bis 持久化契约

本 SPEC 的持久化对象为**已存在的生产集合** `tradingagents.index_daily_quotes` 的候选记录（字段级更新），以及 runner 的**本地产物**（report / audit / checkpoint）。runner 产物不写入 MongoDB。

| 存储对象 | 字段 | 类型 | 必填 | 默认/派生规则 | 生命周期 | 隐私级别 |
|---|---|---|---|---|---|---|
| `tradingagents.index_daily_quotes`（候选记录） | `version` | int | 否（归一化后为 1） | 缺失/不合规时 `$set 1`；值恒为 `1`（与修复后 writer 一致） | 随记录存续，不删除 | L1 |
| `tradingagents.index_daily_quotes`（候选记录） | `name` | string（历史残留） | 否 | `$unset` 移除；恢复仅经独立批准 recovery | 移除后不保留 | L1 |
| 其余全部字段 | `_id`/full_symbol/code/symbol/market/trade_date/period/OHLCV/pct_chg/data_source/created_at/updated_at 等 | 混合 | 是（既有） | 原样保留，绝不触碰 | 随记录存续 | L1 |
| `data/rollout/index-daily-quote-governance/` report/audit/checkpoint | 见 R17/B17 | JSON/JSONL | 是 | run_id + 日期命名 | 保留（可归档），不自动删除 | L2（样本脱敏；无凭据） |

兼容性：`version` 从缺失/不合规归一为 `1` 与修复后 SwIndexDailyService 新写入记录一致；`name` 移除后与 canonical `IndexDailyBar`（无 `name`）一致；旧记录读取策略 = 归一化后统一形状；schema 版本 = `version: 1`；迁移失败 = stop-on-error + checkpoint 恢复，无回滚。

## 5. 行为契约（决策 → 代码层映射）

| RFC 决策 | SPEC 落地点 | 章节 |
|---|---|---|
| 候选集 = akshare ∧ `.SI` 后缀 | 谓词 `P`（C17-101） | §3.2 |
| 权威 universe = `stock_sector_info` SW | `U` 推导（C17-102/103） | §3.2 |
| `.SI` 不得静默纳入非 SW 数据 | fail-closed gates（C17-201~205）+ gate 顺序（C17-207） | §3.3 |
| dry-run 报告字段 | R17-001~007 | §3.5 |
| 幂等 mutation = `$set {version:1}` / `$unset {name:""}` | M17-001~007 | §3.6 |
| 批次/检查点/恢复 | B17-001~007 | §3.7 |
| 验证计数方程 | V17-001~006 | §3.8 |
| 无自动回滚；`name` 恢复独立批准 | F17-001~004 | §3.9 |
| 副作用矩阵；仅生产 DML 授权 | X17-001~006 | §3.10 |
| 独立 Verify/Review 门槛 | T4/T5 验收（A-001~A-004） | §9 |

## 6. 错误契约

| 类别 | 触发 | 处理 | 退出码 |
|---|---|---|---|
| 参数错误 | 非法 `--mode`/`--batch-size`/缺 `--yes` | 提示并停止 | 1 |
| 连接失败 | 缺环境键/连接拒绝/超时/认证失败 | fail-fast，仅报告缺失键名 | 3 |
| Gate FAIL | C17-201~205 任一不满足 | 停止，report 记录证据分布 | 2 |
| 批处理失败 | 任一批 bulk_write 失败（重试 ≤2 次后） | 停止，checkpoint 保留 | 2 |
| secrets 泄露 | 输出含连接值/URI 凭据段/密码/token | 立即停止，提示 rotate | 2 |
| verify 失败 | V17-004~006 任一不成立 | 停止，报告差异 | 4 |
| 空候选 | `total_candidates == 0` | 成功 no-op | 0 |

## 7. 文件改动清单

### 7.1 新增（本任务 T1，唯一允许的改动）

- `docs/rfc/03_data/RFC-03-017-sw-index-daily-quote-schema-governance.md`
- `docs/spec/03_data/SPEC-03-017-sw-index-daily-quote-schema-governance.md`

### 7.2 未来（T2/T3 等流水线阶段，由后续任务另行定义）

- 未来 runner 工具（census/dry-run/apply/verify）、fixture、测试文件（目录与命名由 T2 Design 定义）。

### 7.3 不改动（明确列出）

- `skills/apps/TradingAgents-CN/app/services/sw_index_daily_service.py`
- `skills/apps/TradingAgents-CN/app/services/historical_data_service.py`
- `skills/data/unified_data/models/domain/market_data.py`
- 文档模板（`docs/rfc/RFC-00-000-rfc-template.md`、`docs/spec/SPEC-00-000-spec-template.md`、3 层 README）
- 03-016 相关文件（`docs/{rfc,spec,design}/03_data/*03-016*`、`scripts/unified_data/sector_ranking_rollout/*`）
- 任何生产 MongoDB 集合、索引、配置、cron、服务。

## 8. 测试要求

- 单元测试（T3，mongomock）：
  - `build_predicate` 精确匹配 `.SI` 后缀 + akshare；反例（`.SH`/`.SZ`/无后缀/非 akshare）不命中。
  - `derive_universe`：带/不带 `.SI` 后缀的 `l1_code` 归一化一致；空 U 触发停止。
  - fail-closed gates：构造反例（market≠CN、period≠daily、P 内 full_symbol ∉ U）→ 各 gate FAIL + 退出码 2。
  - 分类：missing/nonconforming/already_compliant/name_present/both_needed 全覆盖。
  - mutation：幂等（apply 两次，第二次 modified=0）；只改 version/name；`_id` 定位；无 upsert（`upsert=False`）。
  - 批次：batch_size 分界（1/500/1000）；ordered=False；stop-on-error；checkpoint 写后恢复（模拟中断 → 恢复 → 收敛）。
  - 方程：V17-001~003（pre）、V17-004~006（post）在 fixture 上成立。
- 集成测试：census → dry-run → apply → verify 全链路在 mongomock fixture 上跑通；report/audit/checkpoint 产物存在且可读。
- 回归测试：既有 `test_sw_index_daily_service.py`（含 repair 断言 `"name" not in doc`、`doc["version"] == 1`）不回归。
- 不可自动化验证项：真实生产集合的 census 分布（须在 Pascal 显式触发的生产 runner 中人工/独立 Verify 复核）；`stock_sector_info` 真实 `l1_code` 归一化覆盖（OQ-017-1）。

## 9. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | RFC/SPEC 存在、互相引用一致、路径正确 | 文件存在 + 交叉链接检查 |
| A-002 | 契约 8 项全覆盖（根因/fail-closed/dry-run/mutation/批次/回滚/副作用矩阵/Verify-Review 门槛） | 逐项对照 RFC §3、SPEC §3 |
| A-003 | 明确声明「本任务不连接/不修改 MongoDB；唯一授权未来写 = 候选记录 `$set`/`$unset`」 | 文本核对 |
| A-004 | T3 实现：全部工具 mongomock 可测、门禁/幂等/恢复/方程测试通过 | T4 独立验证报告 |
| A-005 | T4 Verify：验收标准全过 + 端到端 smoke（fixture）+ 数据合理性抽样 | yquanttester 报告 |
| A-006 | T5 Review：diff + 测试 + 与 RFC/SPEC 一致性 PASS | yquantreviewer 报告 |
| A-007 | Markdown 链接/路径一致性检查通过；`git diff --check` 无空白错误 | 本任务 Completion 步骤 |
| A-008 | 生产 runner 执行前必须已通过独立 Verify/Review；Pascal 显式触发 | 流程门禁 |

## 10. 实现约束

- 禁止事项：任何 Mongo 连接/写入（本任务）；候选记录 replace/delete/upsert/insert；报告/日志输出原始 `name` 值、完整 `_id`、凭据；忽略 gate FAIL 继续；修改 writer 代码/索引/其他集合。
- 依赖限制：仅使用项目既有依赖（pymongo/motor/mongomock）；不新增第三方依赖。
- 性能/安全/风控约束：每次操作带超时；批次有界；样本有界（每类 ≤5）；secrets 零泄露；生产 DML 仅限授权集合与字段。

## 11. 风险与未解决问题

- RFC §7 风险映射全部适用。
- [ ] OQ-017-1：`stock_sector_info.l1_code` 后缀归一化覆盖（待真实 census 复核）。
- [ ] OQ-017-2：非 `.SI` SW 血缘与非 akshare `.SI` 记录的后续治理（建议独立 RFC）。
- [ ] OQ-017-3：`version` 语义是否需要额外记录（本 SPEC 仅归一为 1）。

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.2 | 2026-08-01 | P0 文档修正（kanban `t_c6948c89`）：§2.1 废弃旧编号 `C17-003 ~ C17-007`（证据门禁）引用，统一为 canonical 映射——C17-103=空权威 universe STOP、C17-201~205=串行 census 证据门禁、C17-206=观察项（不阻断）、C17-207=串行 gate 顺序；来源 RFC 同步为 V0.2 | YQuant-Codex-Principal |
| V0.1 | 2026-08-01 | 初始创建（Full Flow T1，kanban `t_a5d83e62`） | YQuant-Codex-Principal |
