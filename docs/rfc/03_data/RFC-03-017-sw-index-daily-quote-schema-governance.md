# RFC-03-017: 申万指数历史 quote metadata 治理（version/name 归一化）

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-08-01 |
| 最后更新 | 2026-08-02 |
| 版本号 | V0.3 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-011-unified-data-phase-2-quality-audit-governance（§8 生产 MongoDB 副作用矩阵与确认流程先例）、RFC-03-016-historical-sector-ranking-production-rollout（L1 契约：行情 join field = `index_daily_quotes.full_symbol` `.SI` 后缀值集，`stock_sector_info` 为权威 universe 来源） |
| 依赖 SPEC | SPEC-03-017-sw-index-daily-quote-schema-governance（本 RFC 对应之 SPEC，V0.2 契约基线） |
| 替代 RFC | 无 |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #mongodb #governance #schema #metadata #idempotent #fail-closed |

---

## 1. 执行摘要（Executive Summary）

本 RFC 为 `tradingagents.index_daily_quotes` 中**申万（SW）行业指数历史日线记录的 quote 级 metadata** 定义一次安全、幂等、可审计的历史归一化：对候选记录（`data_source == "akshare"` 且 `full_symbol` 带 `.SI` 后缀）在缺失/不合规时补齐 `version: 1`，并移除已持久化的 quote 级 `name` 字段，**其余全部行情与 provenance 字段原样保留**。

根因是 `SwIndexDailyService` 与 `HistoricalDataService` 两个独立 writer 以不同 upsert 键与字段形状写入同一集合，叠加 SwIndexDailyService schema repair（移除 quote 级 `name`、新增 `version: 1`）之前的历史记录漂移。`stock_sector_info.l1_name` 始终是权威显示名，quote 级 `name` 不被任何现行读路径消费，移除安全。

**成功标准**：RFC/SPEC 两份独立文档存在且互相引用一致；候选选择 fail-closed（`.SI` 后缀 + `data_source` + code-family 证据三重校验，任一不满足即停止）；dry-run 报告字段、幂等 mutation 语义、批次/检查点/恢复、验证计数方程、失败/回滚语义、副作用矩阵全部精确到可执行；后续 T2 Design 拥有精确输入边界。

**关键边界**：本 RFC 仅定义**未来生产 DML 的行为契约**，不连接、不修改 MongoDB；不创建/修改索引与 schema（DDL 未授权）；不涉及服务重启、同步、调度、03-016 Gate-3/Gate-4 或任何无关集合写入。当前任务只产出文档，不做任何 Mongo I/O。

---

## 2. 背景与动机（Background & Motivation）

### 2.1 现状：同一集合存在两个 writer 的 metadata 漂移

`tradingagents.index_daily_quotes` 同时被两个服务写入，二者 upsert 键与记录形状不同：

| 维度 | SwIndexDailyService | HistoricalDataService |
|---|---|---|
| 文件 | `skills/apps/TradingAgents-CN/app/services/sw_index_daily_service.py` | `skills/apps/TradingAgents-CN/app/services/historical_data_service.py` |
| upsert 键 | `{full_symbol, trade_date}`（唯一索引 `uk_full_symbol_trade_date`） | `{symbol, trade_date, data_source, period}` |
| 写入方式 | `UpdateOne(..., $set, upsert=True)` | `ReplaceOne(..., upsert=True)`（整文档替换） |
| `full_symbol` | `f"{code}.SI"`（恒为 `.SI` 后缀） | `_get_full_symbol()`：CN 前缀推导 `.SH/.SZ/.BJ`，**永不产生 `.SI`** |
| `data_source` | 恒为 `"akshare"` | 调用方传入（tushare/akshare/baostock） |
| `period` | 恒为 `"daily"` | 调用方传入，默认 `"daily"` |
| `market` | 恒为 `"CN"` | 调用方传入，默认 `"CN"` |
| quote 级 `name` | **修复前写入**（见 §2.2） | 不写入 |
| `version` | 修复前缺失；**修复后写入 `1`**（见 §2.2） | 写入 `1`（`_standardize_record`） |

结论：`.SI` 后缀 + `data_source == "akshare"` 的组合唯一标识 **SwIndexDailyService 血缘**，是本 RFC 的候选集。

### 2.2 根因：SwIndexDailyService schema repair 之前的历史记录漂移

`skills/apps/TradingAgents-CN` 子模块工作树中存在未提交的 schema repair 修改（`git diff` 实证）：

- `_standardize_dataframe`：删除 `"name": name`（`name` 来自 `_get_l1_sector_map` 的 `stock_sector_info.l1_name`），新增 `"version": 1`；
- `_fallback_realtime_sw`：删除 `"name": self._clean_str(row.get("指数名称"))`，新增 `"version": 1`；
- 对应单测由 `assert doc["name"] == "食品饮料"` 改为 `assert "name" not in doc` + `assert doc["version"] == 1`。

因此 **repair 之前由 SwIndexDailyService 写入的历史记录**：带 quote 级 `name`、缺 `version`；**repair 之后写入的新记录**：无 `name`、带 `version: 1`。同一集合内 `version` 缺失/存在、`name` 存在/缺失混杂，即为本 RFC 要治理的 metadata 漂移。

### 2.3 权威显示名不变式

- `stock_sector_info`（`classify_system == "SW"`，`l1_code` → `l1_name`）是行业显示名的权威来源；`SwIndexDailyService.get_sector_info()` 返回的 `name` 取自 `l1_name`，**不取自 quote 记录**。
- RFC-03-016 L1 契约：行情 join field = `index_daily_quotes.full_symbol`（`.SI` 后缀值集），权威 universe 唯一主来源 = `stock_sector_info`。
- 现行读路径（`IndexDailyBar.from_ta_cn_doc`、sector ranking service、`ta_cn_mongo_adapter`、03-016 rollout 工具）**均不消费 quote 级 `name`**；`IndexDailyBar` canonical 模型无 `name` 字段。
- 因此移除 quote 级 `name` 不破坏任何现有消费者；显示名始终以 `stock_sector_info.l1_name` 为准。

### 2.4 触发原因

1. Pascal 明确授权开始历史数据治理（本任务为**设计文档**，不连接/修改 MongoDB）。
2. 生产集合 `index_daily_quotes` 存在 pre-repair 遗留记录：quote 级 `name` 冗余 + `version` 缺失，造成 schema 不一致，影响可审计性与未来 schema 演进。
3. 需要把「幂等、fail-closed、可恢复、可验证」的历史归一化契约固化为文档，作为后续 Design/Implement/Verify/Review 的输入。

### 2.5 授权与执行分离

| 编号 | 授权动作 | 授权边界 |
|---|---|---|
| A-017-1 | 产出 RFC/SPEC 设计文档 | 仅写 `docs/rfc/03_data/` 与 `docs/spec/03_data/` 下本 RFC/SPEC 两份文件；不编辑模板与无关文档 |
| A-017-2 | （**未来**）生产 DML：对候选记录 `$set {version:1}` / `$unset {name:""}` | 仅限 `tradingagents.index_daily_quotes` 中候选记录；**未授权不执行**，须待本流水线 Verify/Review 通过且 Pascal 显式触发生产 runner |

**当前事实**：A-017-2 为**未执行**的未来授权。本任务及后续流水线阶段（Implement/Verify/Review）全部完成、独立 Review PASS 之后，才能创建生产 runner 执行卡。

---

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）

- [ ] 定义候选集谓词 `P`：`data_source == "akshare"` 且 `full_symbol` 以 `.SI` 结尾。
- [ ] 定义 fail-closed 候选选择：`.SI` 后缀不得静默纳入非 SW 数据；mutation 前必须完成 `data_source`、后缀、code-family（权威 universe 子集）三重 census 校验，任一不满足即停止。
- [ ] 定义 dry-run 报告字段：总数、already compliant、missing-version、nonconforming-version、name-present、both-needed、字段/类型分布、有界样本（标识脱敏）、预期 mutation 计数；不含 secrets。
- [ ] 定义精确幂等 mutation 语义：仅 `$set {version: 1}`（缺失/不合规时）与 `$unset {name: ""}`（仅候选记录）；禁止 replace/delete/upsert/index DDL/日期/OHLCV/provenance 变更。
- [ ] 定义有界批次、ordered/unordered 行为、每批 checkpoint/audit、stop-on-error、resume cursor/key 语义、验证计数方程。
- [ ] 定义失败/回滚语义：无自动回滚/删除；`name` 恢复仅能通过独立批准的 recovery 操作从权威 `stock_sector_info` 映射重建。
- [ ] 定义副作用矩阵：区分只读 census/dry-run、离线代码/测试、生产 DML、写后只读验证；显式声明仅未来生产 DML 被授权；服务重启/同步/调度/Gate-3/Gate-4/DDL/无关集合写入均不授权。
- [ ] 验收标准包含独立 Verify/Review 门槛：生产 runner 执行前必须通过。

### 3.2 非目标（Out of Scope）

- [ ] **不执行任何真实连接、DDL/DML、Provider 调用、回填、服务/cron 变更或 Git 操作**（本 RFC 仅文档）。
- [ ] 不创建/修改/删除索引、集合、schema（`uk_full_symbol_trade_date` 等既有索引原样保留）。
- [ ] 不修改任何 writer 代码（`sw_index_daily_service.py` / `historical_data_service.py` 的 repair 修改不在本 RFC 范围）。
- [ ] 不治理非候选记录：非 `.SI` 后缀的 SW 记录（如 HistoricalDataService 血缘的 `.SH/.SZ/.BJ`）、非 akshare 的 `.SI` 记录，仅计入 census 观察，**不做任何变更**（后续 RFC 候选）。
- [ ] 不设计 `name` 恢复的自动执行（仅定义语义与批准门槛）。
- [ ] 不修改文档模板、3 层 README、其他 RFC/SPEC/DESIGN 文件。
- [ ] 不涉及 03-016 的 Gate-3/Gate-4、sector ranking 集合 `03_data_ud_sector_ranking_daily`。

---

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

**最小权限**：整个治理流程只有一种被授权的写动作——对候选记录做字段级 `$set`/`$unset`；读（census）、写（DML）、验证（写后只读 re-census）三类动作严格分离。

**Fail-closed**：候选选择必须经过三重证据校验（data_source、后缀、code-family universe 子集）；任何证据冲突 → 停止，不 mutate，不猜测。

**幂等**：每个可重复动作（census、dry-run、apply、verify）重复执行结果一致；apply 可安全重跑，已合规记录为 no-op。

**可审计**：census/dry-run/apply/verify 均产出结构化报告与 JSONL 审计日志，含每批 checkpoint；样本标识脱敏，不含 secrets。

**可恢复**：任何中断从最后成功 checkpoint 恢复（resume key = `_id`），不自动回滚、不自动删除。

### 4.2 操作链总览

```
Read-only census（fail-closed 三重校验 + 字段/类型分布）
    ↓ [全部 gate PASS 才继续；任一 FAIL → 停止]
Dry-run report（预期 mutation 计数 + 有界样本）
    ↓ [Pascal 显式触发生产 runner（Verify/Review 通过后）]
Production DML（候选记录逐批 $set/$unset，每批 checkpoint，stop-on-error）
    ↓
Post-write read-only verification（re-census 计数方程校验）
    ↓ [方程全过 → 完成；任一 FAIL → 停止并报告]
```

### 4.3 模块分工

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| Census（未来 runner 只读阶段） | 三重证据校验、字段/类型分布统计 | `tradingagents.index_daily_quotes` + `stock_sector_info`（只读） | census report（JSON + 摘要） |
| Dry-run（未来 runner） | 计算预期 mutation 计数、生成有界样本 | census 结果 | dry-run report |
| DML（未来 runner，生产授权后） | 逐批 `$set`/`$unset` 候选记录 | 候选 `_id` 列表 + mutation 计划 | JSONL 审计日志 + checkpoint |
| Verify（写后只读） | re-census + 计数方程 | 生产集合（只读） | verify report |
| 离线代码/测试（本流水线 T3/T4） | 基于 mongomock/fixture 实现并测试上述逻辑 | fixture 数据 | 测试报告 |

---

## 5. 详细设计（Detailed Design）

### 5.1 候选集定义（Candidate Set）

**谓词 `P`**（精确、可索引）：

```
P = {doc ∈ tradingagents.index_daily_quotes
     | doc.data_source == "akshare"
     ∧ doc.full_symbol 以 ".SI" 结尾（字符串后缀精确匹配）}
```

- `full_symbol` 为字符串；后缀匹配必须精确到字符串末尾，不得使用前缀猜测或模糊匹配。
- `data_source` 为字符串，精确等于 `"akshare"`。

**权威 universe `U`**（fail-closed code-family 证据来源）：

```
U = { normalize(f"{l1_code}.SI") 的集合
      | doc ∈ tradingagents.stock_sector_info, doc.classify_system == "SW" }
```

- `l1_code` 归一化：去掉已存在的 `.SI` 后缀后取 6 位数字段（与 `SwIndexDailyService._normalize_code` 一致），再统一加 `.SI` 后缀。
- `U` 非空是硬性前置（SPEC C17-103：空权威 universe → EXIT_STOP=2）；若 `stock_sector_info` 无 SW 记录 → 停止（fail-closed）。

### 5.2 Fail-closed 三重证据校验（Census Gates，C17-201 ~ C17-207）

> **编号对齐（canonical gate mapping）**：本 RFC 与 SPEC-03-017（§3.1/§3.3）、DESIGN-03-017（§3.4）及 runner 实现共用同一套编号——**C17-001 = CLI 模式语义**（`--mode`，SPEC §3.1）；**C17-103 = 空权威 universe STOP**（§5.1 前置）；**C17-201~205 = 串行 census 证据门禁**（本表）；**C17-206 = 观察项（不阻断）**；**C17-207 = 串行 gate 顺序**。V0.1 草稿曾以 `C17-001` 指代 U 非空前置、以 `C17-003~007` 指代证据门禁，与 SPEC/Design 冲突，自 V0.2 起废弃，不再使用。

mutation **之前**必须对候选集完成以下校验，任一 FAIL 即停止（退出码按 SPEC C17-002），不执行任何写操作：

| Gate | 校验内容 | 通过条件 | 失败动作 |
|---|---|---|---|
| C17-201 | 后缀证据 | 100% 候选 `full_symbol` 以 `.SI` 结尾，且 distinct 后缀集合 = `{".SI"}` | STOP |
| C17-202 | data_source 证据 | 100% 候选 `data_source == "akshare"`，distinct 集合 = `{"akshare"}` | STOP |
| C17-203 | code-family 证据 | P 内 `distinct(full_symbol)` ⊆ U（权威 universe 子集）；反例（P 内不在 U 中）计数 = 0 | STOP |
| C17-204 | market 证据 | 100% 候选 `market == "CN"`（字段存在时）；缺失 market 的候选计数 = 0 | STOP |
| C17-205 | period 证据 | 100% 候选 `period == "daily"`（字段存在时）；缺失 period 的候选计数 = 0 | STOP |
| C17-206 | 观察项（不阻断） | 非候选观察计数（`.SI` 但非 akshare 记录、akshare 但非 `.SI` 的 SW 候选）仅报告，不参与 STOP | — |
| C17-207 | gate 顺序 | C17-201 → C17-202 → C17-203 → C17-204 → C17-205 串行执行；任一 FAIL 即停止，后续 gate 不执行 | — |

- C17-201/202 是对谓词的独立复算（防止谓词实现偏差）；C17-203 是权威 universe 交叉校验；C17-204/205 用于排除其他血缘记录混入（SwIndexDailyService 恒写 `market="CN"`、`period="daily"`）。C17-206 为观察项（不阻断）；C17-207 规定上述门禁必须按 C17-201 → C17-205 串行执行。
- 任何 gate FAIL 时，census report 必须记录证据分布（哪些值、多少条）后停止；禁止降级阈值、禁止忽略反例。

### 5.3 Dry-run 报告字段（R17-001 ~ R17-007）

dry-run 报告（JSON 文件 + 人类可读摘要）必须包含：

1. 运行元信息：run_id、mode（census/dry-run/apply）、UTC 时间戳、`conn_fingerprint`（仅结构字段：source 标签 + keys_present + auth_configured，**不含任何连接值**）、目标集合名、谓词序列化。
2. 候选统计：`total_candidates`（P 命中数）、`total_docs_scanned`。
3. 合规分类计数：`already_compliant`、`missing_version`、`nonconforming_version`、`version_fix_needed`、`name_present`、`name_absent`、`both_needed`。
4. 字段/类型分布：`version` 类型直方图（absent / int==1 / int!=1 / float / str / other）、`name` 类型直方图（absent / str / non-str）、受保护字段存在性计数（full_symbol、code、symbol、market、trade_date、period、open、high、low、close、pre_close、volume、amount、pct_chg、data_source、created_at、updated_at）。
5. 预期 mutation 计数：`expected_set_version_ops`、`expected_unset_name_ops`、`expected_update_docs`（见 §5.6 方程）。
6. 有界样本：每类（already_compliant / missing_version / nonconforming_version / name_present / both_needed）至多 5 条，每条只含 `id_prefix`（`_id` 前 6 位 hex，其余脱敏）、`full_symbol`、`trade_date`、`name_presence`、`version_summary`；**不输出原始 `name` 值、不输出完整 `_id`、不输出任何凭据**。
7. secrets 约束：任何 report/log 不得出现连接值、URI、密码、token；`conn_fingerprint` 仅结构字段。

### 5.4 幂等 Mutation 语义（M17-001 ~ M17-007）

对每个候选记录：

```
若 version 缺失 或 version 不合规（非 BSON int 且值 ≠ 1）：
    $set: { version: 1 }
若 name 字段存在（任意类型）：
    $unset: { name: "" }
两条可合并为单条 update_one({"_id": ...}, {"$set": {"version": 1}, "$unset": {"name": ""}})
```

约束：

- **无 upsert**（`upsert=False`）、**无 replace_one**、**无 delete_one**、**无 insert**。
- 逐条按 `_id` 定位（候选 `_id` 列表在 census 阶段固化），**不在批次内重新用谓词查询**。
- 除 `version`、`name` 外**不得触碰任何字段**：`_id`、`full_symbol`、`code`、`symbol`、`market`、`trade_date`、`period`、OHLCV（open/high/low/close/pre_close/volume/amount）、`pct_chg`、`change`、`data_source`、`created_at`、`updated_at` 及其他未知字段全部保留。
- 幂等性：对已合规记录重跑为 no-op（matched 但 modified=0）；分类阶段直接跳过已合规记录。
- **无 DDL**：不创建集合、不创建/修改/删除索引。
- 写目标仅限 `tradingagents.index_daily_quotes` 一个集合。

### 5.5 批次 / 检查点 / 恢复（B17-001 ~ B17-007）

- **批次大小**：默认 500，范围 1..1000，可配置（`--batch-size`）。
- **ordered/unordered**：批内 `bulk_write(ordered=False)`（操作彼此独立，无批内依赖；unordered 更高效且语义安全，与 SwIndexDailyService 自身一致）。
- **游标**：候选按 `_id` 升序排序处理；`_id` 唯一、不可变，是稳定 resume key。
- **每批 checkpoint**：每批写完后持久化 checkpoint `{batch_seq, batch_start_id, batch_end_id, matched, modified, ts_utc}`（JSONL，写后 fsync 语义由 Design 定义），checkpoint 成功后进入下一批。
- **stop-on-error**：任一批失败（连接/超时/duplicate key 等）→ 立即停止；瞬态错误有界重试 ≤2 次，重试耗尽即停止；不自动扩批、不自动继续。
- **恢复语义**：从最后成功 checkpoint 恢复；恢复查询 = 候选谓词 `P` ∧ `_id > batch_end_id`；已修复记录在分类阶段被识别为已合规并跳过，恢复收敛。
- **审计日志**：每批记录 counts、errors、耗时，追加到 `data/rollout/index-daily-quote-governance/logs/`（目录 `mkdir -p`，文件名带 run_id 与日期，不得覆盖历史日志）。

### 5.6 验证计数方程（V17-001 ~ V17-006）

**分类恒等式**（每候选恰属一类 version 状态、一类 name 状态）：

```
total_candidates = already_compliant + missing_version + nonconforming_version
                 = name_present + name_absent
version_fix_needed = missing_version + nonconforming_version
```

**预期 mutation 计数**：

```
expected_set_version_ops = version_fix_needed
expected_unset_name_ops  = name_present
expected_update_docs     = version_fix_needed + name_present − both_needed
                           （both_needed = version_fix_needed ∧ name_present 的候选）
```

**写后只读验证（re-census，同一谓词 P）**：

```
post_total_candidates == pre_total_candidates          （无增删）
post_version_conforming == post_total_candidates        （全部 version 合规）
post_name_absent        == post_total_candidates        （全部 name 移除）
累计 modified_count     == expected_update_docs
累计 matched_count      ≥ 累计 modified_count
受保护字段存在性计数     == pre 分布                          （OHLCV/provenance 原样）
```

任一方程不成立 → 验证失败（EXIT_VERIFY=4），停止并报告差异。

### 5.7 失败 / 回滚语义（F17-001 ~ F17-004）

- **无自动回滚、无自动删除**：本治理不设计任何回滚动作；中断 → 从 checkpoint 恢复（幂等收敛）。
- `version: 1` 是终态，不存在「降级」路径；重复 apply 为 no-op。
- **`name` 恢复**：仅在独立批准的 recovery 操作中允许——通过 `stock_sector_info`（`l1_code` → `l1_name`）映射按候选 `full_symbol` 重建并回写 quote 级 `name`；该操作**不属于本 RFC**，需要单独授权与文档。
- 失败现场保留：checkpoint、审计日志、report 全部保留，供人工排查；不清理、不覆盖。

### 5.8 副作用矩阵（X17-001 ~ X17-006）

| 动作类别 | 目标 | 写? | 授权状态 |
|---|---|---|---|
| 只读 census / dry-run（未来 runner） | `tradingagents.index_daily_quotes`（P 命中查询 + 分布统计）、`tradingagents.stock_sector_info`（U 读取） | 否 | 未来生产 runner 的一部分；Verify/Review 通过且 Pascal 显式触发后执行 |
| 离线代码 / 测试（本流水线 T3/T4） | mongomock / fixture，零真实 I/O | 否 | 本流水线授权 |
| **生产 DML（未来 runner）** | 仅 `tradingagents.index_daily_quotes` 候选记录：`$set {version:1}` / `$unset {name:""}` | **是（唯一被授权的写）** | 未执行；Verify/Review 通过 + Pascal 显式触发 |
| 写后只读验证（未来 runner） | `tradingagents.index_daily_quotes` re-census | 否 | 同上（随 DML 执行） |
| 服务重启 / 同步 / 调度 | — | — | **不授权** |
| 03-016 Gate-3 / Gate-4 | — | — | **不授权**（与本 RFC 无关） |
| DDL / 索引 / 集合创建 | — | — | **不授权** |
| 无关集合写入 | 任何非 `index_daily_quotes` 集合 | — | **不授权** |

显式声明：**唯一被授权的未来生产写动作 = 对 `tradingagents.index_daily_quotes` 候选记录执行字段级 `$set`/`$unset`**；其余一切动作（重启、同步、调度、Gate-3/Gate-4、DDL、无关集合写）均不在授权范围内。

---

## 6. AI 实装规范（AI Implementation Rules）

### 6.1 必须执行

- 每个未来 runner 阶段单指令只做一件事；只读、写、验证严格分离。
- 命名语义化；核心分类/方程逻辑必须有单元测试（mongomock 上跑通）。
- 所有变更保留可追溯记录（report + JSONL audit + checkpoint）。

### 6.2 先询问再执行

- 任何超出 `$set {version}` / `$unset {name}` 的字段变更（如 OHLCV 修正、日期归一化、其他字段移除）。
- 任何 DDL、索引变更、跨集合写入、连接非 `tradingagents` 数据库。
- `name` 恢复操作的启动。

### 6.3 绝对禁止

- 对候选记录做 replace/delete/upsert/insert。
- 在报告或日志中输出原始 `name` 值、完整 `_id`、连接值、凭据。
- 无 census 校验直接 mutation；忽略 gate FAIL 继续执行。
- 本任务（T1）进行任何 Mongo 连接或数据写入。

---

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| 候选集误纳非 SW 数据（如未来其他 writer 产生 `.SI` 记录） | 低 | 高 | 三重证据校验（C17-201~205）+ 权威 universe 子集（C17-203）fail-closed | 任一 FAIL 停止，报告证据分布 |
| 某记录 `_id` 重复/不可排序导致 resume 错乱 | 低 | 中 | `_id` 唯一性由 Mongo 保证；resume 用 `_id > end_id` | 排序异常即停止，人工介入 |
| 下游消费者依赖 quote 级 `name` | 低 | 中 | 已审计现行读路径均不消费 `name`（§2.3）；显示名来自 `stock_sector_info.l1_name` | 若发现新消费者，停止并在恢复操作中按独立批准重建 |
| 批处理中途失败导致部分记录已更新 | 中 | 低 | checkpoint + 幂等分类；恢复从最后成功批次继续 | 失败现场保留，人工排查后重跑 |
| 误删/误改 provenance 字段 | 低 | 高 | mutation 仅 `$set {version}` / `$unset {name}`，`_id` 定位；验证方程覆盖受保护字段存在性 | 任何越界字段变更即停止 |
| 生产 DML 执行时机过早 | 中 | 高 | 强制 Verify/Review 门槛 + Pascal 显式触发 | 未通过门槛前 runner 不创建/不执行 |

---

## 8. 备选方案（Alternatives Considered）

- **方案 A：全量 re-write/重灌**（按权威 universe 重新回填 `index_daily_quotes`）。
  优点：一步到位的统一形状；缺点：需要 upsert/replace，风险高，会触碰 provenance 与 `_id`，且需要重新拉取外部数据（未授权、成本高）。不选用——本 RFC 只做**字段级增量修正**，保留全部现有数据。
- **方案 B：按 `version` 缺失的旧记录整体删除后重灌**。
  优点：无残留 `name`；缺点：删除是破坏性操作，违反「无自动删除」原则，且重灌依赖外部数据可达性。不选用。
- **方案 C：容忍漂移，只修新写入**。
  优点：零历史动作；缺点：历史记录永远不一致，schema 演进与审计不可靠，未解决根因。不选用——Pascal 已授权治理历史。
- **方案 D：对 `name` 做「保留但标记 deprecated」**。
  优点：不丢数据；缺点：quote 级 `name` 非权威、无消费者，保留只会延续漂移与误导；权威显示名在 `stock_sector_info`，需要时可独立恢复。不选用。

---

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收（本文档）

- [ ] `docs/rfc/03_data/RFC-03-017-sw-index-daily-quote-schema-governance.md` 与 `docs/spec/03_data/SPEC-03-017-sw-index-daily-quote-schema-governance.md` 存在且互相引用一致。
- [ ] RFC §5 覆盖任务契约全部 8 项：根因、fail-closed 候选选择、dry-run 字段、幂等 mutation、批次/检查点/恢复、失败/回滚、副作用矩阵、验收与独立 Verify/Review 门槛。
- [ ] 明确声明「本任务不连接/不修改 MongoDB；唯一授权未来写 = 对 `tradingagents.index_daily_quotes` 候选记录 `$set`/`$unset`」。
- [ ] Markdown 链接/路径一致性检查通过；`git diff --check` 无空白错误。

### 9.2 非功能验收

- [ ] 所有计数、方程、门禁编号在 SPEC 中一一可执行（T3 Developer 可直接实现）。
- [ ] 无 secrets：文档、样本、report 定义均不含凭据与连接值。
- [ ] 幂等性、可恢复性、可审计性语义无歧义。

---

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分

| 阶段 | 产出 | 门槛 |
|---|---|---|
| T1（本任务） | RFC + SPEC | 两份文档存在、互相引用、契约覆盖 |
| T2 Design（yquantprincipal） | 详细设计：工具、CLI、测试、action plan | 基于本 RFC/SPEC，parents=[T1] |
| T3 Implement（yquantdeveloper） | census/dry-run/DML/verify 工具（离线，mongomock 可测） | 单测通过，parents=[T2] |
| T4 Verify（yquanttester） | 独立验证：单测 + 端到端 smoke（fixture）+ 数据合理性抽样 | 验收标准全过，parents=[T3] |
| T5 Review（yquantreviewer） | 独立审查：diff + 测试 + 与 RFC/SPEC 一致性 | PASS 才可创建生产 runner 卡，parents=[T4] |
| Production activation（orchestrator） | 生产 runner 执行卡 | Pascal 显式触发；独立 Verify/Review PASS 后创建 |

### 10.2 任务清单

- [ ] T2：Design 细化 CLI（census/dry-run/apply/verify 四模式）、退出码、report schema、fixture、测试矩阵。
- [ ] T3：按 SPEC 实现，全部基于 mongomock/fixture，零真实 I/O。
- [ ] T4/T5：独立验证与审查。
- [ ] Production：仅限候选记录的 `$set`/`$unset` 生产 DML。

---

## 11. 开放问题（Open Questions）

- [ ] OQ-017-1：`stock_sector_info` 中 `l1_code` 可能带或不带 `.SI` 后缀（`_get_l1_sector_map` 已兼容）；U 归一化规则是否完全覆盖（归一化函数与 SwIndexDailyService `_normalize_code` 一致，待 T2 用真实数据 census 复核）。
- [ ] OQ-017-2：非 `.SI` 后缀的 SW 记录（HistoricalDataService 血缘）与 `.SI` 但非 akshare 的记录是否纳入后续治理（本 RFC 仅 census 观察，不 mutate；建议独立 RFC）。
- [ ] OQ-017-3：`version` 字段语义是否需要额外记录（如 `version_comment`/`schema_version` 文档）——本 RFC 仅把 `version` 归一到 `1`，不新增字段。

---

## 12. 参考资料（References）

- `skills/apps/TradingAgents-CN/app/services/sw_index_daily_service.py`（SwIndexDailyService；工作树含未提交 schema repair）
- `skills/apps/TradingAgents-CN/app/services/historical_data_service.py`（HistoricalDataService）
- `skills/data/unified_data/models/domain/market_data.py`（`IndexDailyBar` canonical，无 `name` 字段）
- `docs/rfc/03_data/RFC-03-016-historical-sector-ranking-production-rollout.md`（L1 契约、副作用矩阵先例）
- `docs/spec/03_data/SPEC-03-016-historical-sector-ranking-production-rollout.md`（可执行契约风格先例）
- `docs/rfc/03_data/RFC-03-011-unified-data-phase-2-quality-audit-governance.md`（§8 生产 MongoDB 副作用矩阵与确认流程先例）

---

## 13. 闭包账本（Closure Ledger）

> 本账本为 03-017 文档闭包修订（kanban `t_ae320c08`）的可审计汇总，供替代评审者判断有界终态。仅记录元数据与交叉引用事实，不改变任何契约语义。

### 13.1 Canonical C17 编号（唯一权威映射）

| 编号 | 语义 | 权威出处 |
|---|---|---|
| C17-001 | CLI 模式语义（`--mode`，census/dry-run/apply/verify 单 CLI） | SPEC §3.1；DESIGN §3.2/§3.4.1 |
| C17-002 | 退出码 0/1/2/3/4 | SPEC §3.1；DESIGN §3.3.1 |
| C17-103 | 空权威 universe → EXIT_STOP=2 | SPEC §3.2；DESIGN §3.4.2；本 RFC §5.1 |
| C17-201 ~ C17-205 | 串行 census 证据门禁（fail-closed） | SPEC §3.3；DESIGN §3.4.3；本 RFC §5.2 |
| C17-206 | 观察项（不阻断） | SPEC §3.3；DESIGN §3.4.3；本 RFC §5.2 |
| C17-207 | 串行 gate 顺序 | SPEC §3.3；DESIGN §3.4.3；本 RFC §5.2 |
| C17-301 ~ C17-304 | 合规分类 | SPEC §3.4；DESIGN §3.4.4 |

废弃编号（历史，不再使用）：`C17-001` 旧指「U 非空前置」（现为 C17-103）；`C17-003 ~ C17-007` 旧指证据门禁（现为 C17-201 ~ C17-207）。见本 RFC §5.2 编号对齐说明。

### 13.2 M2 run-id / resume 基线

- `--run-id` = operator 选择的**不可变标识**；**新 run-id = 全新 checkpoint lineage**；**复用同一 run-id = 从最后成功 checkpoint 恢复**（DESIGN §3.3.4/§8，B17-006）。
- 生产 apply / 中断后 resume 必须复用同一 `--run-id`；自动生成 run-id（`qg-<uuid12>`）不满足恢复语义，仅限一次性只读模式（DESIGN §3.4.1）。

### 13.3 源元数据基线（Source Metadata Baseline）

| 文档 | 文档修订 | 引用契约基线 | 参考关系 |
|---|---|---|---|
| SPEC-03-017 | V0.2（不变） | RFC-03-017 V0.2 | 可执行契约；来源 RFC |
| RFC-03-017 | V0.3（本次元数据修订） | SPEC-03-017 V0.2 | 本文档；依赖 SPEC |
| DESIGN-03-017 | V0.3（本次元数据修订） | RFC-03-017 V0.2、SPEC-03-017 V0.2 | 实现设计；来源 RFC + SPEC |

版本语义：RFC-03-017 / DESIGN-03-017 的 V0.3 仅为文档元数据修订（指针修复 + 本账本），契约内容与 V0.2 一致；SPEC-03-017 保持 V0.2，不因下游指针修复而升级（无版本级联）。

### 13.4 无语义变更声明

本次闭包修订**不改变任何语义 runner / mutation 行为**：候选谓词 `P`（C17-101）、fail-closed 门禁（C17-201~207）、幂等 mutation（M17-001~007）、批次/检查点/恢复（B17-001~007）、验证方程（V17-001~006）、退出码（C17-002）、授权边界（A-017-2 / X17-003）均保持 SPEC-03-017 V0.2 契约不变。本次修订仅修改本文档与 DESIGN-03-017 两个文件；无代码、测试、config、Mongo、runner、CLI、服务、cron、Git 操作。

---

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.3 | 2026-08-02 | 闭包修订（kanban `t_ae320c08`）：依赖 SPEC 指针 V0.1 → V0.2（契约基线同步）；新增 §13 闭包账本（canonical C17 ID / M2 run-id-resume / 源元数据基线 / 无语义变更声明）。**文档修订 V0.3 ≠ 引用契约基线**（SPEC-03-017 V0.2）；仅元数据修正，无任何语义 runner/mutation 行为变化；SPEC-03-017 不因下游指针修复而升级（无版本级联） | YQuant-Codex-Principal |
| V0.2 | 2026-08-01 | P0 文档修正（kanban `t_c3f567eb`，M1）：废弃旧编号 `C17-001`（U 非空前置）与 `C17-003~007`（证据门禁），统一为 SPEC-03-017 §3.1/§3.3 与 DESIGN-03-017 §3.4 的 canonical 映射——C17-001=CLI 模式语义、C17-103=空权威 universe STOP、C17-201~205=串行 census 证据门禁、C17-206=观察项（不阻断）、C17-207=串行 gate 顺序；§5.2 增补编号对齐说明；§7 风险表同步 | YQuant-Codex-Principal |
| V0.1 | 2026-08-01 | 初始创建（Full Flow T1，kanban `t_a5d83e62`） | YQuant-Codex-Principal |
