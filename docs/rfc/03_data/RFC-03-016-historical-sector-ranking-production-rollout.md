# RFC-03-016: 历史行业 sector.ranking 生产 Gate-1~4 受控激活

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-31 |
| 最后更新 | 2026-08-03（V0.8 Contract C baseline 集合对齐，本卡 `t_ea99efaa`）：**契约 C（§5.8）baseline 授权集合与 `gate4_activate.py` 实物 `BASELINE_MANIFEST` 对齐**——① 实物核对：`BASELINE_MANIFEST`（gate4_activate.py:62-77）共 **14 条路径**（scripts 7 + data 目录 1 + tests 6），当前工作树 **manifest 内 dirty 恰 7 条**：`common.py`、`gate3_backfill.py`、`gate4_activate.py`、`sector_ranking_rollout_fixtures.py`、`test_sector_ranking_rollout_common.py`、`test_sector_ranking_rollout_gate3.py`、`test_sector_ranking_rollout_gate4.py`（T3 Gate-4 修复 5 文件 + Gate-3 range 修复 2 文件）；三层文档**不在 manifest 内**（docs dirty 属 out_of_manifest，记录不停止）；② **区分两个集合**：baseline commit 集 = **10 条路径**（上述 7 manifest 内 + RFC/SPEC/DESIGN-03-016 三文档），其中 7 条为 G4-S-003 硬性要求、3 条为审计基线完整性；activation 运行前 manifest 内 14 条路径必须全部 clean；③ GIT-016-1 改为**逐路径列出 10 条** `git add` 目标，禁止 `git add -A/.`、restore/reset/stash/clean；④ 新增 baseline 形成前独立 scope/test/secret/manifest diff 验证（§5.8 第 4 步）；⑤ 明确本卡不构成 Git commit / activation / production credential 许可（§5.8 边界声明）；⑥ §7 风险表、§9.1 验收、§10 T2/T3/Baseline、§11 OQ-016-7 同步；依赖 SPEC 更新至 V0.9；对应 DESIGN 更新至 V0.12；V0.7 历史见 Changelog） |
| 版本号 | V0.8 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-015-historical-sector-ranking（V0.5，冻结基线）、RFC-03-011-unified-data-phase-2-quality-audit-governance（§8 生产 MongoDB 副作用矩阵与确认流程先例）、RFC-03-014-p3a-sector-provider-activation（P3-A 边界） |
| 依赖 SPEC | SPEC-03-016-historical-sector-ranking-production-rollout（本 RFC 对应之 SPEC，V0.9） |
| 关联 Design | DESIGN-03-016-historical-sector-ranking-production-rollout（V0.12，本 RFC 对应之实现设计；V0.11 已落实 Gate-4 P0 修复契约 A/B/C，V0.12 本卡同步 baseline 集合对齐）；DESIGN-03-015-historical-sector-ranking.md（V0.5，§8 与附录 A 为本 RFC 的 Gate 参考来源，仅参考，非执行规范） |
| 替代 RFC | 无（03-015 已冻结离线语义，本 RFC 独立定义生产 rollout，不替代、不合并） |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #sector #ranking #production #rollout #gate #mongodb |

---

## 1. 执行摘要

本 RFC 为历史行业板块日涨跌幅排名能力（`sector.ranking_history`，RFC-03-015）定义**生产 rollout 的独立执行规范**，把 DESIGN-03-015 §8 中仅作参考的 4 个生产 Gate（G-015-1 ~ G-015-4）升级为**可停止、可审计、最小权限**的执行阶段：Gate-1 TA-CN SW 历史数据真实可达性 smoke（只读 Mongo）与权威 expected universe 校验 → Gate-2 新集合 `03_data_ud_sector_ranking_daily` 及其唯一索引 DDL → Gate-3 真实 TA-CN 历史 backfill → Gate-4 生产读路径激活。

本 RFC 与对应 SPEC-03-016 **不改变 03-015 已冻结的离线语义**（9 字段 schema、pct_chg 固定口径、100% exact-match 完整性、结果语义冻结表、warning token、source_trace 枚举），只把生产激活动作本身固化为可执行、可分步暂停、可审计的契约。

**授权与执行分离（关键事实）**：Pascal 已明确授权 Gate-1~4 的**生产动作**（Gate-1 只读 smoke、Gate-2 DDL、Gate-3 backfill、Gate-4 读路径激活）。该授权**不取消工程门禁**：本卡与后续 Design/Implement/Verify/Review 全部完成、独立 Review PASS 之后，才能创建分阶段 production activation 卡；在任何流水线阶段完成前，**不得**执行任何真实连接、DDL/DML、Provider 调用、回填、服务/cron 变更或 Git 操作。**2026-08-03 执行状态更新**：Gate-1/2/3 已按 production activation 链执行并经独立只读 Verify（Gate-3 全量回填：1,114 日 / 34,534 行 / 0 failed / 0 stop，canonical report `data/rollout/sector-ranking/gate3-report.json`）；**Gate-4 仍为 NO-GO / P0 BLOCKED**——已获 Pascal 授权（读路径绑定），但本修复链 Review PASS 前禁止 enable/disable，真实 activation 另卡执行 + 独立 Verify 后才生效。

**Gate-4 P0 blocker（2026-08-03 根因审计结论，本卡 `t_1e649585`）**：`gate4_activate.py` 的 enable 路径存在 **fail-closed 原子性缺陷**——`write_binding(True)`（gate4_activate.py:366）在 strict `scope_diff` 检查（gate4_activate.py:391-396，G4-S-003）**之前**执行；G4-S-003 触发时 binding 已被写为 `enabled=true`，且 `except Gate4Stop` 处理器（gate4_activate.py:435-443）不自动回滚 binding。实物证据（`data/rollout/sector-ranking/gate4-report-*.json`）：`gate4-report-20260803T105744.json` 记录 binding before=false / **after=true** / stop=G4-S-003 / scope_diff=[`gate3_backfill.py`, `test_sector_ranking_rollout_gate3.py`]；`105826`/`105832` 重复命中同态；`105840` 由人工 `--disable --apply --yes` 回滚（after=false，`binding_state.json` 现为 `enabled=false`）。此外 literal production CLI 无法构造 `CompletedSessionPolicy`（`main(policy=...)` 仅 Python 注入，`__main__` 不传 → G4-S-002，实物 `gate4-report-20260803T105510.json`），旧 activation 卡 `t_aaeb7319` 曾以 `/tmp` wrapper + `FakeTradeCalendar(coverage_by_date ∪ {today})` 绕过——属被本 RFC 禁止的伪造 calendar 形态。**本 RFC 把该缺陷列为真实 blocker**：Gate-4 保持 NO-GO，任何 APPROVE/PASS 均不构成 enable/disable 放行；修复路径见 §5.5（契约 A/B/C）、§10（T2~T6 修复链）与 §11（OQ-016-6/7/8）。

**成功标准**：RFC/SPEC 两份独立文档存在且互相引用一致；每个 Gate 均具备副作用矩阵、停止条件、审计证据、回滚/禁用语义；不包含模糊"按需/可选/由实现者决定"的生产语义；下一张 Design 卡（T2）拥有精确的输入边界，足以输出工具、测试与精确 action plan。

**关键边界**：本 RFC 仅定义 Gate-1~4 的**动作契约与停止条件**，不定义新数据模型、不修改 03-015 冻结语义、不修改 P3-A 任何文件、不修改文档模板。

---

## 2. 背景与动机

### 2.1 现状

- 离线能力已验收：RFC-03-015 / SPEC-03-015 / DESIGN-03-015 均 V0.5，Closeout `t_86d3783d` 完成；新增核心 `SectorRankingDaily`、mongomock writer、只读 service、conditional facade；离线定向验收 51/51、模块回归 1047/1047。
- 生产 Gate 未执行：DESIGN-03-015 §8 的 Gate-1~4 全部标注 "NOT EXECUTED"，附录 A 是参考设计（"不在 T3 实现"），尚非可执行 rollout 规范。
- 生产连接与身份约定已存在先例：RFC-03-011 §8 定义了生产 MongoDB 副作用矩阵、确认流程、停止条件、金丝雀验收与最小权限身份契约（`YQUANT_UD_AUDIT_{DDL,WRITER,READER}_MONGO_*`）；本 RFC 复用其**机制与格式**，但不复用其集合、角色或用户（sector ranking 是独立能力）。
- skills/.env 已存在 `MONGODB_*` 主连接（数据库 `tradingagents`）与 `YQUANT_UD_AUDIT_*` 三组身份；TA-CN 只读适配器（`ta_cn_mongo_adapter.py`）已存在且只读。

### 2.2 生产与离线的差异（为什么需要独立 RFC）

| 维度 | 离线（03-015 已验收） | 生产（本 RFC 定义） |
|---|---|---|
| Mongo 后端 | mongomock / FakeDatabase | 真实 `tradingagents` MongoDB |
| 写入 | `HistoricalRankingWriter` 拒绝真实 pymongo | Gate-3 需真实 DML（upsert 到新集合） |
| DDL | 不执行（附录 A.4 仅参考） | Gate-2 执行 createCollection + createIndex |
| 数据源 | fixture / 显式 expected universe | Gate-1 权威校验真实 `index_daily_quotes` + expected universe |
| 读路径 | facade 条件性（仅 mongomock 注入时可测） | Gate-4 生产读激活 |
| 失败语义 | 冻结表（Category 1~4） | 冻结表不变 + Gate 级停止条件 / 审计 / 回滚 |

### 2.3 触发原因

1. Pascal 明确授权 Gate-1~4 生产动作（见本卡 body「授权事实」）。
2. DESIGN-03-015 §8 仅定义 Gate 内容与前置条件，未定义**可执行的停止条件、副作用矩阵、审计证据、回滚语义**，不足以让 Design 卡直接输出工具与 action plan。
3. 需要把「离线通过 ≠ 生产启用」的结论固化为流程：生产激活必须走分 Gate 串行 + 独立只读 Verify 判定实物证据。

### 2.4 授权与执行分离原则

**授权事实（Pascal 已确认）**：

| 编号 | 授权动作 | 授权边界 |
|---|---|---|
| A-016-1 | Gate-1：TA-CN SW 历史数据真实可达性 smoke（只读 Mongo）与权威 expected universe 校验 | 只读 `tradingagents.index_daily_quotes`；禁止外部 Provider、router、cache、写入 |
| A-016-2 | Gate-2：新集合 `03_data_ud_sector_ranking_daily` 及其唯一索引 DDL | 只能 DDL 该集合与唯一索引 `{dataset, trade_date, sector_code}`；禁止影响任何已有集合；禁止顺手创建 cache/audit/quality 或业务集合 |
| A-016-3 | Gate-3：真实 TA-CN 历史 backfill | 仅从已验证 TA-CN 的 `index_daily_quotes` 回填 `dataset=sw2021_ta_cn`；固定日期范围与日级原子语义；100% exact-match |
| A-016-4 | Gate-4：生产读路径激活 | 仅激活读路径；不得改 router/fallback/provider |

**执行状态（当前事实，2026-08-03 更新）**：**Gate-3 全量 backfill 已授权、已实际执行并经独立只读 Verify PASS**（1,114 日 / 34,534 行 / 0 failed / 0 stop；canonical report `data/rollout/sector-ranking/gate3-report.json`，2026-08-03T09:03:41Z；apply 走 `--start-date 2021-12-14 --end-date 2026-07-30` 等价于 SPEC G3-B-013「ratio==1.0 + 排除最早满覆盖日」语义，1,115−1=1,114 一致）。**Gate-4 已获 Pascal 授权（生产读路径绑定）但尚未执行 enable/disable**——该授权不允许在本卡或后续修复链 Review PASS 前执行；真实 activation 必须在修复闭环后单独创建 activation + 独立 Verify 卡，由 Pascal 显式触发后才生效。本 RFC 及 SPEC 不得把「授权」误写为「已生效」。

**Gate-3/4 当前状态（修复链同步，2026-08-03）**：Gate-3 **已执行并经独立只读 Verify PASS**（Verify 卡 `t_1ae1dc26`：1,114 日 / 34,534 行 / 唯一键 0 重复 / 抽样 5 日 G3-V-001~004+V-105 全 PASS / report 与 Mongo 1:1）。**Gate-4 consumer binding 仍为 NO-GO**：虽已获 Pascal 授权，但本修复链 Review PASS 前禁止 enable/disable；真实 activation 必须在修复闭环后单独创建 activation + 独立 Verify 卡，Pascal 显式触发后才生效。本 RFC/SPEC 三层文档**不产出、不暗示任何 activation approval**。

**Gate-4 P0 根因审计（2026-08-03，本卡 `t_1e649585` 新增）**：旧 activation 卡 `t_aaeb7319`（blocked，历史证据保留，不得 unblock/retry/改状态）实测暴露两个工具层缺陷：

| 编号 | 缺陷 | 实物证据 | 影响 |
|---|---|---|---|
| P0-016-1 | **fail-closed 原子性**：enable 路径 `write_binding(True)`（gate4_activate.py:366）在 strict `scope_diff`（G4-S-003，gate4_activate.py:391-396）**之前**执行；G4-S-003 触发时 binding 已写 `enabled=true`，`except Gate4Stop`（gate4_activate.py:435-443）不自动回滚 | `gate4-report-20260803T105744.json`：binding before=false / **after=true** / stop=[G4-S-003]；`105826`/`105832` 同态重复；`105840` 人工 `--disable` 回滚（after=false）；`binding_state.json` 现 `enabled=false`（previous=true，updated_at=2026-08-03T10:58:40Z） | 激活失败后 binding 可能残留 enabled=true（部分激活状态），违反「任一失败均证明 binding remains false」 |
| P0-016-2 | **literal CLI 无法构造 policy**：`main(policy=...)` 仅 Python 注入参数；`__main__`/literal `python -m` 不传 → G4-S-002（policy unavailable）fail-closed；无 `--calendar-file` 等 CLI 构造路径；旧卡以 `/tmp` wrapper 注入 `FakeTradeCalendar(coverage_by_date ∪ {today})` 绕过（伪造 calendar，被本 RFC 禁止） | `gate4-report-20260803T105510.json`：stop=[G4-S-002]，binding after=false；`t_aaeb7319` comment 记录 wrapper 行为 | 真实 activation 无法以「无 wrapper、可审计」方式从受控 calendar evidence 构造 policy，必须修订契约 A |

修复契约见 §5.5.1（A：literal CLI policy 构造）、§5.5.2（B：原子 fail-closed 顺序）、§5.5.3/§5.8（C：baseline 前置）；本 RFC 把 P0-016-1/P0-016-2 列为 **Gate-4 真实 blocker**，不因任何 APPROVE/PASS 掩盖（验收 §9.1）。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 定义每个 Gate（1~4）的**副作用矩阵**：read/write/create-index/external action、目标 namespace、最大日期/记录范围、幂等性、停止条件、审计证据、回滚/禁用语义
- [ ] 定义 Gate-1 为纯只读 smoke + 权威 expected universe 校验，固定受控查询预算与 report 路径；失败/不足 100% 必须停止，禁止降级阈值或伪造 ranking
- [ ] 定义 Gate-2 为最小 DDL：仅新集合 + 唯一索引；明确 createCollection 必要性、精确索引名/选项、dry-run/只读 verify、重复执行行为、禁止影响已有集合
- [ ] 定义 Gate-3 为真实 backfill 的可执行契约：固定日期范围（范围来源唯一化：`--range-file` 或成对 `--start-date`/`--end-date` 二选一，无任何范围来源 → EXIT_PARAM(1)）、日级原子语义、100% exact-match、有效 close/pre_close、前一日推导、固定收益公式、no realtime fallback、`outcome.failed==0` 才认定日成功；dry-run / canary / 写后读回 / 失败停止 / 不得自动 rollback/drop
- [ ] 定义 Gate-4 为读路径激活：不改 router/fallback/provider；未物化/不完整返回现有冻结 token；intraday/trade calendar 检查（由 Gate-4 工具层可注入 CompletedSessionPolicy 执行，非修改 03-015 冻结 service）、只读 smoke、consumer/service 变更判定、回滚为禁用 binding 而非删除数据
- [ ] 定义凭据/身份与泄露边界：复用经 Gate-1 验证的唯一连接源/键；无 alias/fallback；不打印 URI/用户名/密码/token；无可用受控连接源必须停止
- [ ] 定义实际 Production task 创建规则：Final Review PASS 后创建、分 Gate 串行、每 Gate 完成后独立只读 Verify 判定实物证据；失败不自动 retry、扩范围或反向 DDL
- [ ] 为 T2 Design 提供精确 inputs：每 Gate 的输入/输出路径、允许文件范围、离线/真实分离、验收证据

### 3.2 非目标（Out of Scope）

- **不执行任何真实连接、DDL/DML、Provider 调用、回填、服务/cron 变更或 Git 操作**（本卡仅文档）
- **不修改 03-015 已冻结语义**（schema、pct_chg 口径、完整性判定、结果语义冻结表、warning token、source_trace 枚举）
- **不修改 P3-A 任何文件**（akshare.py / sector_client.py / fixtures / tests / activation docs）
- **不修改文档模板**（RFC/SPEC/DESIGN 模板与 3 层 README）
- **不创建新数据模型**（沿用 SectorRankingDaily 9 字段 schema）
- **不定义新 dataset 枚举**（第一版仅 `sw2021_ta_cn`）
- **不创建最小权限账号/角色**（超出 Gate-2 授权边界；若 Design 判定需要，作为 Design 前置缺口上报 Pascal，见 §11）
- **不设计增量更新/每日任务调度**（Gate-4 之后由未来 RFC 定义）
- **不定义缓存层、告警推送、Dashboard**（后续阶段）

---

## 4. 整体设计

### 4.1 核心设计哲学

**最小权限**：每个 Gate 只做本 Gate 授权内的一类动作；读、写、DDL 三类权限严格分离；任何动作不得超出目标 namespace。

**可停止**：每个 Gate 有明确停止条件；任一条件触发即暂停 rollout，不自动进入下一 Gate，不自动重试。

**可审计**：每个 Gate 产出实物证据（report / 日志 / 写后读回结果），由独立只读 Verify 判定后才放行下一 Gate。

**幂等**：每个可重复动作（查询、DDL、upsert、读激活开关）重复执行结果一致；失败后可在修复后重跑，但**不自动**重跑。

### 4.2 Gate 链总览

```
Final Review PASS（本流水线）
    ↓
Production activation 分阶段卡（由 orchestrator 在 Review PASS 后创建）
    ↓
Gate-1 只读 smoke + expected universe 校验
    → [独立只读 Verify：实物证据判定] → 通过才进 Gate-2
Gate-2 DDL（新集合 + 唯一索引）
    → [独立只读 Verify：索引/集合存在性与正确性判定] → 通过才进 Gate-3
Gate-3 真实 TA-CN backfill（dry-run → canary → 全量，日级原子）
    → [独立只读 Verify：outcome.failed==0 + 写后读回判定] → 通过才进 Gate-4
Gate-4 生产读路径激活（只读 smoke + binding 状态）
    → [独立只读 Verify：smoke 结果 + 冻结 token 行为判定]
```

### 4.3 与 DESIGN-03-015 §8 / 附录 A 的关系

- DESIGN-03-015 §8（Gate 表）与附录 A（A.1~A.7 参考设计）是**参考来源**，不是执行规范；本 RFC/SPEC 将其中的动作边界、检测信号、DDL 草案升级为可执行契约。
- 冲突处理：附录 A 与 RFC/SPEC 冲突时，以 RFC/SPEC 为准；附录 A 未覆盖的细节（如查询预算、report 路径、canary 选定规则）由本 RFC/SPEC 定义。
- 附录 A.4 的 3 条 DDL 中，本 RFC 只授权前 2 条（createCollection + 唯一索引）；第 3 条查询辅助索引 `idx_dataset_date` 明确**不在 Gate-2 授权范围**（见 §5.3 决策记录）。

### 4.4 模块分工

| 角色 | 职责 |
|---|---|
| YQuant-Principal | 本 RFC/SPEC 定义与后续 Design（工具、测试、action plan） |
| YQuant-Developer | Gate 工具的 Implement（按 Design 最小范围） |
| YQuant-Tester | 独立只读 Verify：判定每个 Gate 的实物证据 |
| YQuant-Reviewer | 独立 Review：diff、测试结果、实现与 RFC/SPEC/Design 一致性 |
| Pascal | 逐 Gate 显式触发 production activation 卡；异常/缺口拍板 |

---

## 5. 详细设计

### 5.1 副作用矩阵（总表）

> 每个 Gate 分别列明 read / write / create-index / external action、目标 namespace、最大日期/记录范围、幂等性、停止条件、审计证据、回滚/禁用语义。SPEC-03-016 §3 给出对应的可执行契约（命令、退出码、产物路径）。

#### 5.1.1 Gate-1 副作用矩阵

| 维度 | 内容 |
|---|---|
| read | 只读 `tradingagents.index_daily_quotes`（TA-CN SW 行业指数日线，按 `full_symbol` 关联 L1 行业代码）；只读 `tradingagents.stock_sector_info`（filter `{classify_system:"SW"}`，distinct `(l1_code,l1_name)` 产出权威 SW L1 universe）；`index_basic_info` 仅作可选元数据交叉核对（见 §5.2 G1-C-001），不得用作 L1 universe 枚举主来源 |
| write | 无（严禁任何写入） |
| create-index | 无 |
| external action | 无外部 Provider / 无 router / 无 cache / 无网络外部调用 |
| 目标 namespace | `tradingagents.stock_sector_info`（只读，universe 来源）、`tradingagents.index_daily_quotes`（只读，行情来源）；`tradingagents.index_basic_info`（只读，仅可选交叉核对） |
| 最大日期/记录范围 | 查询预算内：`trade_date` 覆盖 `index_daily_quotes` 中 SW L1 `full_symbol`（31 个 `.SI` 后缀 code）的全部可用范围（min/max 报告）；记录范围为查询命中文档数，受受控查询预算上限约束（SPEC G1-B-006） |
| 幂等性 | 天然幂等（只读）；重复执行结果一致 |
| 停止条件 | SPEC G1-S-001 ~ G1-S-008（任一触发即停止，不进入 Gate-2） |
| 审计证据 | `data/rollout/sector-ranking/gate1-report.json` + `gate1-report.md`（统计、覆盖率、校验结果、expected universe、证据哈希） |
| 回滚/禁用语义 | 无副作用，无需回滚；报告只读，不产生可回滚状态 |

#### 5.1.2 Gate-2 副作用矩阵

| 维度 | 内容 |
|---|---|
| read | 只读校验：目标集合/索引是否存在、目标数据库可达 |
| write | 无 DML（不插入任何文档） |
| create-index | `tradingagents.03_data_ud_sector_ranking_daily` 的唯一复合索引 `uniq_dataset_date_sector`（`{dataset:1, trade_date:-1, sector_code:1}`，unique=true） |
| external action | 仅 `createCollection`（如不存在）与 `createIndex`；无其他动作 |
| 目标 namespace | `tradingagents.03_data_ud_sector_ranking_daily`（新集合，唯一） |
| 最大日期/记录范围 | 不适用（DDL 无数据） |
| 幂等性 | 幂等：先查存在性；集合已存在 → 跳过 createCollection；索引已存在且规格一致 → 跳过 createIndex；规格不一致 → 停止（G2-S-003） |
| 停止条件 | SPEC G2-S-001 ~ G2-S-006（任一触发即停止，不进入 Gate-3） |
| 审计证据 | DDL 执行日志（dry-run 输出 + apply 输出）+ 只读 verify 结果（`db.getCollectionInfos` / `getIndexes` 快照） |
| 回滚/禁用语义 | 不自动 drop；若 DDL 后 Pascal 决定撤销，只能由 Pascal 显式下发单独授权（不在本 Gate 自动执行）；禁止任何影响已有集合的动作 |

#### 5.1.3 Gate-3 副作用矩阵

| 维度 | 内容 |
|---|---|
| read | 从已验证 TA-CN 的 `tradingagents.index_daily_quotes` 读取目标 trade_date 与前一日 close（前一日推导） |
| write | upsert 到 `tradingagents.03_data_ud_sector_ranking_daily`（仅 `BuildOutcome.status == "complete"` 的正式 ranking 行） |
| create-index | 无（Gate-2 已完成） |
| external action | 无外部 Provider；无 router；无 cache；无 realtime fallback |
| 目标 namespace | 读：`tradingagents.index_daily_quotes`；写：`tradingagents.03_data_ud_sector_ranking_daily` |
| 最大日期/记录范围 | 日期范围由 Gate-1 证据确认的可用范围（或 Pascal 显式指定的子范围）固定；全量命令必须显式传入 `--range-file`（SPEC G3-B-013~016）；单日最多 `expected_sector_codes` 行（SW L1 一级行业全集，Gate-1 权威枚举）；canary 至多 1 个由 Gate-1 证据选定的 completed trade_date。**查询预算范围模型（SPEC G3-B-017~020）**：Gate-3 查询预算**按日 scoped**（每 `process_day` 独立/reset 计数），**不继承** Gate-1 全局累计 100k 上限（G1-B-006，Gate-1 report scope）；日级上限 = `4 × len(expected_sector_codes)` = 124 行（当日 31 + 前一日 31 + 2× 冗余防 schema 漂移），超过 → G3-S-013 停止；全量累计查询命中行数（数据正常 = 1,114 × 62 = 69,068，ratio==1.0 满覆盖日模型，排除最早满覆盖日后）仅 informational 记入 report，**不作为停止条件**；扫描保护（G1-B-001~005：白名单/过滤/≤1000/超时/空 filter 拒绝）全部保留 |
| 幂等性 | upsert 幂等（唯一键覆盖）；同一 trade_date 重复执行覆盖更新，`updated_at` 刷新 |
| 停止条件 | SPEC G3-S-001 ~ G3-S-013（任一触发即停止；失败不自动 retry、扩范围或反向 DDL；G3-S-013 = 单日查询命中 > 日级上限 124 行，表明上游 schema 漂移） |
| 审计证据 | backfill 日志（每 trade_date 的 `outcome`、failed 计数、upserted 计数、per-day query_budget）+ canary 报告 + 写后读回结果 + 全量汇总（success/failed/stop_conditions_hit/total_query_rows[resumption_boundary]）。**已执行实物（2026-08-03T09:03:41Z）**：`data/rollout/sector-ranking/gate3-report.json`（原子 twin `gate3-report-20260803T090341.json`）、`gate3-report.md`、`logs/gate3-20260803.log`；success_days=1,114 / failed_days=0 / stop_conditions_hit=[] / total_query_rows=69,068 / resumption_boundary=2026-07-30；独立只读 Verify `t_1ae1dc26` PASS |
| 回滚/禁用语义 | **不自动 rollback、不 drop**；如需修正已写入数据，重跑该 trade_date 的 upsert（幂等覆盖）；如需删除某日数据，只能由 Pascal 显式单独授权 |

#### 5.1.4 Gate-4 副作用矩阵

| 维度 | 内容 |
|---|---|
| read | 生产读路径：`get_sector_ranking_history(trade_date, dataset)` 直读 `tradingagents.03_data_ud_sector_ranking_daily` |
| write | 无（只激活读路径） |
| create-index | 无 |
| external action | 不修改 router/fallback/provider；不新增服务/cron；consumer/service 变更需单独判定（见 §5.5） |
| 目标 namespace | `tradingagents.03_data_ud_sector_ranking_daily`（只读） |
| 最大日期/记录范围 | 查询任意已物化 trade_date（`YYYY-MM-DD`）；未物化返回冻结 token（empty/incomplete），不返回部分榜单 |
| 幂等性 | 读激活开关幂等；只读 smoke 可重复执行；**binding 切换必须原子 fail-closed**：所有 precondition（含 pre-smoke、scope/baseline diff）在 `write_binding(True)` 之前完成，任一失败证明 binding remains false；post-smoke 失败 → 工具自动 `write_binding(False)` 回滚（契约 B，§5.5.3） |
| 停止条件 | SPEC G4-S-001 ~ G4-S-008（任一触发即停止，回滚为禁用 binding）；G4-S-002 扩展覆盖 policy 构造失败（literal CLI calendar evidence 缺失/非法，契约 A）；G4-S-005 触发时工具必须自动回滚 binding 至 false 并记录 binding_events |
| 审计证据 | 只读 smoke 结果（查询返回、冻结 token 行为、source_trace）+ **binding_events**（顺序化事件日志：precondition-pass / write_binding / post-smoke / rollback，证明原子顺序）+ binding 状态（启用/禁用）+ **calendar evidence 记录**（来源、as_of、交易日数、哈希；不得为伪造 calendar，契约 A） |
| 回滚/禁用语义 | 回滚 = 禁用 facade / feature binding（配置或开关），**不删除数据**；数据保留供审计与重启用。**任何失败路径的最终 binding 必须为 false**：precondition 失败 → 从未写入 true（P0-016-1 修复）；post-smoke 失败 → 自动回滚至 false（G4-S-005 自动 `write_binding(False)`） |

### 5.2 Gate-1：TA-CN SW 历史数据真实可达性 smoke + 权威 expected universe 校验

**目的**：在真实 Mongo 上证明 `index_daily_quotes` 中 SW L1 行业指数日线的可达性、完整性与来源可信度，并产出**权威 expected universe**（SW L1 code/name 全表），作为 Gate-3 backfill 与 Gate-4 完整性判定的唯一输入。

**动作边界（硬约束）**：

- 只读 `tradingagents.stock_sector_info`（universe 来源）、`tradingagents.index_daily_quotes`（行情来源）；`index_basic_info` 仅作可选元数据交叉核对，不得用作 universe 主来源；禁止任何写入、createIndex、drop。
- 禁止外部 Provider、router、cache；所有查询直连 Gate-1 指定的受控 Mongo 连接（§5.6）。
- 固定受控查询预算（SPEC G1-B-001 ~ G1-B-007）：查询类型白名单（count / distinct / find 带过滤 / sample 上限）、超时上限、结果条数上限、禁止无过滤全表扫描。
- 固定 report 路径：`data/rollout/sector-ranking/gate1-report.json`（机器可读）+ `gate1-report.md`（人读）。

**校验项（全部必须 100% 通过，任一失败即停止）**：

| 编号 | 校验项 | 通过标准 | 失败动作 |
|---|---|---|---|
| G1-C-001 | SW L1 code/name 权威枚举 | 从 `tradingagents.stock_sector_info`（filter `{classify_system:"SW"}`）按 `(l1_code,l1_name)` distinct 得到恰好 31 个申万一级行业；`l1_code` 唯一；行业代码 canonical 形态为带 `.SI` 后缀的标识符（例如 `801780.SI`）；**不得**使用 `index_basic_info` 作为 L1 universe 枚举主来源（其 `market="申万指数"` 元数据不含可直接识别申万层级的字段）。`index_basic_info` 仅可作可选元数据交叉核对，且须按生产真实字段语义使用 | 停止 G1-C-FAIL，不进入 Gate-2 |
| G1-C-002 | expected universe 固化 | 将 G1-C-001 枚举写入 report（`expected_sector_codes` = 31 个 L1 code；`expected_sector_names` = code→name 映射），作为后续 Gate 唯一 expected 输入（**不得硬编码于代码**，由 Gate-1 证据注入；canonical code 形态 `.SI` 后缀） | 停止 |
| G1-C-003 | 可用 trade_date 范围 | 以 31 个 L1 code 经 `full_symbol` 关联 `index_daily_quotes`（join field = `full_symbol`，非 `sector_code`），对该全表执行 `distinct(trade_date)`；report 记录 min/max、总日数、逐日 coverage；31/31 全覆盖的共同完整交易日为可用范围（最近完整共同交易日为 2026-07-30）。明确排除 L2/L3 分类（`classify_system="SW"` 的 L1 distinct 已天然排除；`index_daily_quotes` 当前仅有 L1 行情，不得宣称 L2/L3 行情可用） | 覆盖率不足 100% 的天数必须记录；**若任一关键校验日不足 100% 且被选为 canary 候选 → 停止**（不降级阈值） |
| G1-C-004 | close/pre_close 完整性 | 以 `full_symbol` 关联的目标范围内每 `{l1_code/full_symbol, trade_date}` 有有效 `close`（有限数值，缺失应 fail-stop）；`pre_close` 从前一交易日同 `full_symbol` 的 `close` 推导；report 记录缺失清单。最小数据质量：排序行必须有有效 `pct_chg`；`close` 缺失必须 fail-stop。对最早观测日 `pre_close` 缺失的处理：不能以全历史 OHLC 的不相关严格条件阻断已由上游提供有效 `pct_chg` 的同日横截面（具体语义见 SPEC/Design 三层一致） | 缺失行必须记录；`close` 缺失 → fail-stop；影响 canary 候选日 → 停止 |
| G1-C-005 | data_source/source 线索 | 分布统计：`source` 值分布、是否含 realtime/intraday/rt 标记（DESIGN 附录 A.5 RT-4）；确认 SW L1 相关行（经 `full_symbol` 关联的 31 个 L1）source 为可信历史值 | 出现 realtime/intraday 标记的 SW L1 行 → 停止 |
| G1-C-006 | 数据集隔离 | 确认 `index_daily_quotes` 查询仅命中经 `stock_sector_info` L1 universe 的 `full_symbol` 集合（31 个 L1 行业指数），不混入 concept/region/style/大盘指数；过滤基于 `full_symbol ∈ {31 个 L1 full_symbol}` 而非 code 前缀猜测 | 混入 → 停止 |
| G1-C-007 | 连接/身份可用性 | 受控连接源可读目标集合；身份为经确认的只读身份 | 不可读 → 停止并报告（见 §5.6） |

**报告内容（SPEC G1-R-001 ~ G1-R-010）**：连接身份指纹（不含 secrets）、查询统计、覆盖统计、expected universe 表、canary 候选日清单、停止条件命中记录、证据哈希。

### 5.3 Gate-2：新集合 + 唯一索引 DDL

**决策记录（本 RFC 冻结）**：

| 决策点 | 冻结结论 | 理由 |
|---|---|---|
| createCollection 是否必要 | 需要：`createCollection`（如不存在）+ `createIndex` | 显式创建便于审计与权限校验；MongoDB 4.x 默认不存在集合时 createIndex 会隐式建集合，但显式动作保证可审计 |
| 唯一索引规格 | name=`uniq_dataset_date_sector`；key=`{dataset:1, trade_date:-1, sector_code:1}`；unique=true | 与 DESIGN 附录 A.4 一致；保证 `{dataset, trade_date, sector_code}` 唯一键（SPEC-03-015 H-019） |
| 查询辅助索引 `idx_dataset_date` | **不创建**（不在 Gate-2 授权范围） | 本 RFC 只授权集合 + 唯一索引；查询辅助索引留待 Gate-4 后按实际查询量由未来 RFC 评估 |
| dry-run / 只读 verify | 必须：先 dry-run（零副作用）→ 只读 verify 目标集合/索引不存在 → 再 apply | 防止误触 DDL |
| 重复执行行为 | 幂等：已存在且规格一致 → 跳过并报告；规格不一致 → 停止（SC-016-G2-3） | 可重跑，不破坏已有状态 |
| 禁止影响已有集合 | 只允许操作目标新集合；任何其他集合的读为只读校验，写/DDL 均禁止 | 最小权限边界 |

**动作边界（硬约束）**：

- 只能 DDL：`createCollection("03_data_ud_sector_ranking_daily")`（如不存在）+ 唯一索引 `uniq_dataset_date_sector`。
- **不得**顺手创建 cache、audit、quality 或任何业务集合（含 `03_data_ud_query_audit`、`03_data_ud_quality_summary`、`portfolio_*`、`smart_money_*`、`signal_*`、`trade_*`）。
- **不得**修改/删除任何已有集合或索引。
- 凭据：使用 Gate-1 验证的唯一连接源；DDL 动作需足够权限，但身份不打印、不记录（§5.6）。

### 5.4 Gate-3：真实 TA-CN 历史 backfill

**目的**：把已验证 TA-CN 的 `index_daily_quotes` 历史日线，按 03-015 冻结语义（100% exact-match、固定 pct_chg 公式、前一日推导）回填为 `dataset=sw2021_ta_cn` 的正式 ranking 行，写入 `03_data_ud_sector_ranking_daily`。

**动作边界（硬约束）**：

- **只允许**从已验证 TA-CN 的 `index_daily_quotes` 读取；禁止任何其他上游（外部 Provider、realtime、cache、router）。
- 回填目标 dataset 固定为 `sw2021_ta_cn`（常量注入，不从 TA-CN 推断）。
- 固定日期范围选择：范围来源二选一并冻结——`--range-file PATH`（Gate-1 report，读取其 `coverage_by_date`，**仅选择可解析且数值 `ratio == 1.0` 的日期键**——31/31 满覆盖共同完整交易日（2021-12-13 → 2026-07-30 共 1,115 日；部分覆盖日 ratio<1.0 不纳入，100% exact-match 下必然 G3-S-004 停止；**禁止以 `coverage_by_date` 全部键作为 range**）——升序去重，默认排除该满覆盖子集中最早满覆盖日 2021-12-13〔其前一日 2021-12-10 为部分覆盖 → 无完整 prev close〕，计划范围 1,114 日）或成对 `--start-date`/`--end-date`（Pascal 显式子范围，**同样只能在该满覆盖子集上取交集，不能作为绕过 ratio 过滤的替代路径**；范围含满覆盖键集外日期 → fail-fast 停止）；无任何范围来源 → EXIT_PARAM(1)；**无满覆盖日期、非法 ratio（缺失/非数值/不可解析日期键）、用户范围超出满覆盖集合 → 稳定 fail-fast 停止（G3-S-003，EXIT_PARAM(1)，不等 process_day）**；全量命令必须显式传 `--range-file`；SPEC G3-B-001/G3-B-013~016 定义范围解析规则。
- **日级原子语义**：每个 `trade_date` 是独立处理单元；该日全部 expected sector_code 构建为 `complete` 且 upsert `outcome.failed==0` 才认定该日成功；否则该日失败并停止（不自动 retry、不扩范围）。
- **100% exact-match**：`observed_sector_codes == expected_sector_codes` 才生成正式 ranking 并物化（复用 03-015 `build_ranking_rows` 语义）。
- **有效 close/pre_close**：`close` 为有限数值；`pre_close` 从前一交易日同 `full_symbol`（非 `sector_code`）的 `close` 推导；前一交易日无 `close` → 该行不入库（SPEC-03-015 H-047/H-048）。对最早观测日 `pre_close` 缺失，不得以全历史 OHLC 的不相关严格条件阻断已由上游提供有效 `pct_chg` 的同日横截面（语义跨三层一致）。
- **固定收益公式**：`pct_chg = (close - pre_close) / pre_close * 100`；禁止 close-to-open；禁止直接使用上游自带 `pct_chg`（H-030 ~ H-032）。
- **no realtime fallback**：任何 realtime/intraday 标记行不入库（DESIGN 附录 A.5 RT-4）；`trade_date` 必须为已收盘历史交易日（RT-1）；未来日 / 当日未收盘的判定由 Gate-4 工具层可注入 CompletedSessionPolicy 执行（SPEC G4-P-001~010），非修改 03-015 冻结 service；`YYYYMMDD` → `YYYY-MM-DD` 转换（H-053）。
- **canary**：至多 1 个由 Gate-1 证据选定的 completed trade_date；canary 通过（写后读回一致、outcome.failed==0）后，才由 Pascal 显式放行全量范围。
- **写后读回**：每个成功日 upsert 后立即按唯一键读回，校验行数、字段、排序稳定（SPEC G3-V-001 ~ G3-V-004）。
- **失败停止**：任何异常（连接失败、完整性失败、upsert failed>0、读回不一致、身份泄露告警）→ 停止后续日处理；不自动重试、不自动回滚、不 drop。
- **dry-run**：默认 dry-run（零写）；`--apply` 才产生写入。

### 5.5 Gate-4：生产读路径激活

**目的**：激活 `sector.ranking_history` 生产读路径，使 `get_sector_ranking_history(trade_date, dataset)` 直读真实物化集合。

**动作边界（硬约束）**：

- **只激活读路径**：不改 router、fallback、provider；不新增服务/cron。
- **未物化/不完整返回现有冻结 token**：读集合无记录 → `historical-ranking-empty`；完整性失败 → `historical-ranking-incomplete`；成功 → 完整榜单 + `warnings=[]`（RFC-03-015 §5.6.3 冻结表逐字一致）。
- **intraday/trade calendar 检查（CompletedSessionPolicy）**：交易日状态判定由 Gate-4 工具层新建的可注入 TradeCalendar / CompletedSessionPolicy 执行（SPEC G4-P-001~010 + 契约 A 扩展 G4-P-011~015），**不是**修改 03-015 冻结 service（其 `_validate_trade_date` 仅做格式校验）；`trade_date` 为当前交易日且市场未收盘 → policy 判定 TODAY_UNCLOSED → 抛 Category 1 `ValueError`（行为契约与 03-015 §5.1 冻结语义一致）；未来日同理（G4-P-004）；无受控日历证据 → fail-closed，不得猜测；Gate-4 只读 smoke 必须覆盖该行为（SPEC G4-V-004，离线用 fake calendar + fake clock 确定性验证）。
- **只读 smoke**：用生产 reader 身份执行一组只读查询（canary 日成功案例、未物化日 empty 案例、非法 trade_date ValueError 案例），全部通过才认定激活成功。
- **consumer/service 变更判定**：本 RFC 不授权任何 consumer/service 变更；若 Design/Implement 发现现有 consumer 需要改动才能使用新能力，必须作为独立变更上报 Pascal，不并入 Gate-4。
- **回滚 = 禁用 facade / feature binding**：Gate-4 回滚通过禁用读取绑定（配置/开关）实现，**不删除数据**。

**P0 blocker 状态（2026-08-03 根因审计，本卡 `t_1e649585`）**：Gate-4 **NO-GO / BLOCKED**，原因见 §2.4（P0-016-1 fail-closed 原子性缺陷、P0-016-2 literal CLI policy 构造缺陷）与 §1。以下契约 A/B/C 为修复要求，必须在 T2 Design / T3 Implement 落实并经 T4 Verify / T5 Review 通过后，Gate-4 才能进入真实 activation 流程；任何 APPROVE/PASS 不得掩盖未实现的修复。

#### 5.5.1 契约 A：literal production CLI 的 CompletedSessionPolicy 构造契约（无 wrapper、可审计）

| 编号 | 规则 | 说明 |
|---|---|---|
| A-016-1 | **literal CLI 自行构造 policy** | `python -m scripts.unified_data.sector_ranking_rollout.gate4_activate`（`__main__` 直入 `main()`）必须能独立构造 `CompletedSessionPolicy`，**不需要** wrapper 脚本、`/tmp` transport、Python REPL 注入或 `main(policy=...)` 外部传入。`main(policy=...)` 参数仅保留给测试注入（CL-5 同纪律），且当经由 `__main__` 调用时必须为 None（不允许生产路径依赖外部注入） |
| A-016-2 | **calendar evidence 文件来源** | `--enable --apply --yes` 必须显式传 `--calendar-file PATH`（可审计 JSON）：`{"source": <权威来源标识>, "as_of": <YYYY-MM-DD>, "timezone": "Asia/Shanghai", "cutoff": "15:00", "trading_days": ["YYYY-MM-DD", ...]}`。工具从 `trading_days` 精确构造 `TradeCalendar`（`is_trading_day` 查集），再构造 `CompletedSessionPolicy(calendar, now_fn=系统时钟)`。证据文件由 operator/Pascal 对照权威来源（交易所/行情商官方日历）确认后落盘，并记录来源与获取方式 |
| A-016-3 | **fail-stop 语义** | `--calendar-file` 缺失、文件不可读、JSON 非法、schema 非法（缺 `trading_days`/`source`/`as_of`、日期键非 canonical `YYYY-MM-DD`、时区 ≠ `Asia/Shanghai`、cutoff ≠ `15:00`）→ 参数层 fail-fast（G4-S-002，退出码 2），在连接/查询/smoke 之前停止，**不降级、不猜测、不重试** |
| A-016-4 | **禁止伪造 calendar** | 禁止用 `coverage_by_date`、周末规则、`FakeTradeCalendar`、`FakeTradeCalendar(coverage_by_date ∪ {today})` 或任何硬编码日历构造生产 policy（旧 activation 卡 `t_aaeb7319` 的 `/tmp` wrapper 行为被明确禁止）。`coverage_by_date` 是行情覆盖证据，不是交易日历——缺行日可能是非交易日也可能是数据缺失，语义不确定 |
| A-016-5 | **时区/cutoff 固定** | 时区 = `Asia/Shanghai`；收盘 cutoff = 当日 15:00 CST（15:00 整视为已收盘）；与 G4-P-003 一致；calendar evidence 文件必须声明并匹配该值，否则 fail-fast |
| A-016-6 | **证据入报告** | `gate4-report.json` 记录 calendar evidence 结构字段：`source`、`as_of`、`trading_days` 数量、证据文件 SHA-256 哈希；**不**记录完整交易日清单（体积/噪音）；不得记录任何 secrets |

#### 5.5.2 契约 B：原子 fail-closed 执行顺序（所有 precondition 在 `write_binding(True)` 之前）

| 编号 | 规则 | 说明 |
|---|---|---|
| B-016-1 | **precondition 全前置** | `--enable --apply --yes` 的严格顺序：① 连接/凭据加载（G4-S-001）；② policy 从 `--calendar-file` 构造（契约 A，失败 → G4-S-002）；③ pre-smoke 全部用例（G4-V-001~008，bypass-binding reader；任一失败 → G4-S-002）；④ **scope/baseline diff（G4-S-003/004）——必须在 `write_binding(True)` 之前完成**（P0-016-1 修复核心）；⑤ 全部通过后才 `write_binding(True)`；⑥ post-smoke（绑定 reader 重跑成功案例，G4-S-005）；⑦ readonly proof + secret scan。**任一 precondition（①~④）失败 → binding 从未写入 true（remains false）** |
| B-016-2 | **post-smoke 失败自动回滚** | ⑤ 之后 ⑥ 失败（G4-S-005）→ 工具**自动** `write_binding(False)` 回滚，最终态 false，退出码 2；report 记录完整 `binding_events`（见 B-016-3），证明「曾短暂 true → 自动回滚 false」而非「残留 true」 |
| B-016-3 | **binding_events 审计** | report 必须包含顺序化 `binding_events: [{seq, action, state_before, state_after, timestamp}]`，覆盖 precondition-pass、write_binding(true)、post-smoke、rollback(false) 等关键动作；Verify 以该日志证明原子顺序 |
| B-016-4 | **disable/回滚路径** | `--disable --apply --yes`：写 `write_binding(False)` 后以绑定 reader 跑 1 用例 → 期望 `BindingDisabledError`（G4-V-104）；该路径总是成功（回滚优先），只改 binding、不删数据 |
| B-016-5 | **失败证明** | 任何失败路径的 report 必须使「binding 最终为 false」可验证：要么 `binding_events` 无 write_binding(true) 条目（precondition 失败），要么含 rollback 条目（post-smoke 失败）；Verify 判定 G4-V-106/107 |

#### 5.5.3 契约 C：Gate-4 baseline 前置（可审计 Git 基线，需 Pascal 显式授权）

见 §5.8（baseline 前置完整定义：baseline commit 集（10 条精确路径）与 activation manifest-relevant required clean set（14 条 manifest 路径）的关系、`git add/commit` 授权动作、禁止 `git restore` 为推荐路径、独立验证流程）。

### 5.8 Gate-4 baseline 前置（契约 C 完整定义）

**问题（实物）**：`gate4_activate.py` 的 `BASELINE_MANIFEST`（gate4_activate.py:62-77）共 **14 条路径**（scripts 7 + data 目录 1 + tests 6）。当前工作树 **manifest 内 dirty 恰 7 条**：`scripts/unified_data/sector_ranking_rollout/common.py`、`scripts/unified_data/sector_ranking_rollout/gate3_backfill.py`、`scripts/unified_data/sector_ranking_rollout/gate4_activate.py`、`skills/data/unified_data/tests/fixtures/sector_ranking_rollout_fixtures.py`、`skills/data/unified_data/tests/test_sector_ranking_rollout_common.py`、`skills/data/unified_data/tests/test_sector_ranking_rollout_gate3.py`、`skills/data/unified_data/tests/test_sector_ranking_rollout_gate4.py`（= T3 Gate-4 修复 5 文件 + Gate-3 range 修复 2 文件，均未提交）→ 任何 Gate-4 enable 必然 G4-S-003（实测 `gate4-report-20260803T105744.json`）。**三层文档（RFC/SPEC/DESIGN-03-016）不在 `BASELINE_MANIFEST` 内**：docs dirty 属于 out_of_manifest（记录入 `report.scope_diff` 但不触发 G4-S-003，G4-B-006/OBS-2）。**生产 activation 卡不得自行 Git 操作**（`git add/commit/restore/reset/stash/clean` 一律禁止，见 §6.3）。

**两个集合（必须区分，不得混同）**：

| 集合 | 定义 | 对 G4-S-003 的影响 |
|---|---|---|
| **baseline commit 集**（GIT-016-1 的 `git add` 目标） | **10 条路径** = 7 条 manifest 内 dirty + 3 条三层文档（RFC/SPEC/DESIGN-03-016） | 其中 7 条为 G4-S-003 硬性要求（不 commit → activation 必停）；3 条文档为审计基线完整性（不 commit 不触发 G4-S-003，但违背三层一致性/可审计要求） |
| **activation manifest-relevant required clean set** | `BASELINE_MANIFEST` 全部 **14 条路径**（gate4_activate.py:62-77） | activation 运行前必须全部 clean（`git status --porcelain` 对 manifest 内路径为空）；**清单外 dirty（03-014/sentiment/data-pipeline 等共享树既有修改）记录不停止** |

> 关键推论：**只 commit 三层文档 + `gate3_backfill.py` + `test_sector_ranking_rollout_gate3.py`（旧「五候选路径」）不足以通过 activation**——`common.py`/`gate4_activate.py`/fixture/`test_common.py`/`test_gate4.py` 仍 dirty 且均在 manifest 内 → G4-S-003 必然触发。baseline 必须覆盖全部 7 条 manifest 内 dirty 路径；三层文档一并纳入以形成完整、可审计、与修复链一致的单基线 commit。

**前置定义**：Gate-4 activation 生效前，审计通过的 03-016 相关文件必须经独立验证后形成**可审计 Git 基线**（committed ref），使 manifest 内路径对激活 diff 为 clean。流程：

1. 本修复链（T1 → T2 Design → T3 Implement → T4 Verify → T5 Review → Closeout）全部完成、独立 Review PASS。
2. **独立验证（baseline 形成前，T4 Verify / T5 Review 各自独立完成）**：
   - **scope 验证**：`git status --porcelain` 确认 dirty 路径恰为下列 10 条，无新增/删除/改名（`??` 未跟踪不计入 violations）；对 manifest 14 条路径逐条确认状态（7 dirty + 7 clean）。
   - **测试验证**：T4 已运行测试全 PASS（common 58 + gate4 37 + gate1/2/3 130 + 03-015 51 = 276）；T5 独立复核测试结果与代码一致性。
   - **secret 验证**：`git diff` 全文静态扫描无 secrets（URI/密码/token/连接串），`git diff --check` exit 0。
   - **manifest diff 验证**：模拟 activation 的 `_collect_scope_entries`（gate4_activate.py:244-275）只读比对，确认 violations 恰为 7 条 manifest 内路径、out_of_manifest 为其余 dirty（03-014/sentiment 等）；确认 `data/rollout/sector-ranking/`（manifest 目录条目）无 manifest 相关 dirty。
3. **Pascal 显式授权 `git add`/`git commit`**（本 RFC 不代为授权；授权动作必须逐条列出，见下表）。
4. 基线形成后，Gate-4 activation 卡的 scope/baseline diff 在 clean HEAD 上对 manifest 路径为空 → 放行后续 enable 流程。

**baseline commit 集（10 条精确路径，唯一允许的 `git add` 目标）**：

| # | 路径 | 在 manifest 内？ | 当前状态（2026-08-03 实物） |
|---|---|---|---|
| 1 | `docs/rfc/03_data/RFC-03-016-historical-sector-ranking-production-rollout.md` | 否（审计基线） | ` M`（V0.7→V0.8 工作树） |
| 2 | `docs/spec/03_data/SPEC-03-016-historical-sector-ranking-production-rollout.md` | 否（审计基线） | ` M`（V0.8→V0.9 工作树） |
| 3 | `docs/design/03_data/DESIGN-03-016-historical-sector-ranking-production-rollout.md` | 否（审计基线） | ` M`（V0.11→V0.12 工作树） |
| 4 | `scripts/unified_data/sector_ranking_rollout/common.py` | **是** | ` M`（T3 Gate-4 修复产物） |
| 5 | `scripts/unified_data/sector_ranking_rollout/gate3_backfill.py` | **是** | ` M`（Gate-3 range 修复产物） |
| 6 | `scripts/unified_data/sector_ranking_rollout/gate4_activate.py` | **是** | ` M`（T3 Gate-4 修复产物） |
| 7 | `skills/data/unified_data/tests/fixtures/sector_ranking_rollout_fixtures.py` | **是** | ` M`（T3 Gate-4 修复产物） |
| 8 | `skills/data/unified_data/tests/test_sector_ranking_rollout_common.py` | **是** | ` M`（T3 Gate-4 修复产物） |
| 9 | `skills/data/unified_data/tests/test_sector_ranking_rollout_gate3.py` | **是** | ` M`（Gate-3 range 修复产物） |
| 10 | `skills/data/unified_data/tests/test_sector_ranking_rollout_gate4.py` | **是** | ` M`（T3 Gate-4 修复产物） |

> 其余 manifest 7 条路径（`__init__.py`、`gate1_smoke.py`、`gate2_ddl.py`、`prod_repository.py`、`data/rollout/sector-ranking/`、`test_gate1.py`、`test_gate2.py`）当前 CLEAN，无需 commit 但必须保持 clean。

**需要 Pascal 明确授权的 `git add/commit` 动作（精确命令形态）**：

| 编号 | 动作 | 授权要求 |
|---|---|---|
| GIT-016-1 | `git add <上述 10 个精确路径，逐路径列出>`（**禁止** `git add -A` / `git add .` / 通配符 / 目录级 add） | Pascal 显式授权（review PASS 后） |
| GIT-016-2 | `git commit -m "<message>"`，message 说明 03-016 Gate-4 P0 修复链基线（RFC V0.8 / SPEC V0.9 / DESIGN V0.12 / Gate-3 range 修复 / Gate-4 修复链 5 文件） | Pascal 显式授权；不绕过 hooks |
| GIT-016-3 | （可选）基线 commit 打 tag/ref note（如 `refs/notes` 或轻量 tag）便于 activation diff 引用 | Pascal 显式授权 |

**授权边界声明（本卡）**：本卡 `t_ea99efaa` **不构成** Git commit 许可、activation 许可或 production credential 许可。仅定义契约 C 的集合与授权动作形态；实际 `git add`/`git commit` 必须由 Pascal 在独立授权卡/显式指令中逐项批准后执行。本卡未执行、也不授权执行任何 Git/Mongo/Provider/.env/CLI/service/cron 操作。

**禁止事项（不得作为推荐路径）**：

- **`git restore` / `git checkout` / `git reset --hard` / `git stash` / `git clean` 一律不得写为推荐路径**：会丢弃已审查通过的 Gate-3 range 修复与三层文档，违反「不得重跑、不得回滚」事实（§1）。
- 生产 activation 卡自身不得执行任何 Git 操作；Git 基线只能由 Pascal 授权的独立动作完成。
- 清单外 dirty 文件（如 03-014 文档、sentiment 系列、data-pipeline 诊断脚本等共享树既有修改）**不**阻止 activation：按 DESIGN OBS-2 语义记入 `report.scope_diff` 但不触发 G4-S-003；**只有 manifest 内路径**的 dirty 才触发停止。

### 5.6 凭据/身份与泄露边界

| 编号 | 规则 | 说明 |
|---|---|---|
| CR-016-1 | 唯一连接源 | 所有 Gate 复用**经 Gate-1 验证的同一受控连接源/键**（skills/.env `MONGODB_*` 主连接，数据库 `tradingagents`；Gate-1 报告记录该源的只读可达性证据）。不得定义 alias/fallback 连接 |
| CR-016-2 | 禁止别名/回退 | 不得为生产连接定义备用连接串、fallback 身份、容错副本 |
| CR-016-3 | 不打印 secrets | 任何工具/日志/report/comment 不得输出 URI（含 credentials）、用户名、密码、token、connection string 全文 |
| CR-016-4 | 无受控连接源 → 停止 | 若 Gate-1 无法用唯一受控连接源验证（连接失败/权限不足），必须停止并上报，**不得**猜测或改用未验证来源 |
| CR-016-5 | 最小权限缺口 | 若现有实现不支持最小权限账号（如只有超管身份可用），Design 必须记录为**前置缺口**并上报 Pascal（§11），不得擅自创建账号/角色 |
| CR-016-6 | 身份分离 | Gate-1/2/3/4 各自使用同一受控连接源；若后续证明需要独立只读/只写身份，走单独授权，不并入本 RFC |

### 5.7 实际 Production task 创建规则

| 编号 | 规则 | 说明 |
|---|---|---|
| PT-016-1 | Review PASS 前禁止创建 | 实际 production activation 卡**只能在**本流水线（本卡 + 后续 Design/Implement/Verify/Review）Final Review PASS 后创建 |
| PT-016-2 | 分 Gate 串行 | 每 Gate 一张 production activation 卡，`parents` 串行；Gate-N 完成 → 独立只读 Verify 判定 → 才创建 Gate-N+1 卡 |
| PT-016-3 | 独立只读 Verify | 每 Gate 完成后由 yquanttester 以只读方式判定实物证据（report / DDL 快照 / backfill outcome / smoke 结果），判定 PASS 才放行下一 Gate |
| PT-016-4 | 失败不自动动作 | 任何 Gate 失败 → 暂停，上报 Pascal；不自动 retry、不扩范围、不反向 DDL（不 drop/不删除） |
| PT-016-5 | 执行权限 | production activation 卡由 orchestrator 创建，assignee 按工具职责分配（Gate 工具开发=developer，Verify=tester）；每张卡 body 必须引用本 RFC/SPEC 对应 Gate 章节与验收标准 |
| PT-016-6 | **Gate-4 baseline 前置** | Gate-4 activation 卡创建前，契约 C（§5.8）必须完成：修复链 Review PASS + Pascal 授权 `git add/commit` 10 条 baseline 集路径形成可审计基线；activation 卡本身**禁止**任何 Git 操作 |
| PT-016-7 | **activation 与独立生产 Verify 授权点隔离** | Gate-4 activation 卡（执行 enable/disable）与 Gate-4 独立生产 Verify 卡（只读判定）**必须分离**：activation 卡由 Pascal 显式触发并单独授权（含 calendar evidence 落盘授权）；Verify 卡由 yquanttester 执行、**单独取得独立明示的凭据授权选择**（吸取 `t_1ae1dc26` 凭据授权范围偏差审计教训，§7），只读 Mongo、不写 binding、不执行 Git；两张卡不得互相代替 |

---

## 6. AI 实装规范

### 6.1 必须执行

- 每个 Gate 工具必须支持 `--dry-run`（默认）与 `--apply`（显式副作用）两种模式。
- 所有 Mongo 查询带过滤条件与超时；禁止无过滤全表扫描。
- 所有 report 写入 `data/rollout/sector-ranking/` 固定路径，含证据哈希。
- 所有日志/report 脱敏 secrets（URI 不含 credentials、用户名、密码、token）。
- 单元测试覆盖每个 Gate 的停止条件与幂等行为（mongomock 上）。
- 变更保留可追溯记录（Kanban comment + report）。

### 6.2 先询问再执行

- 任何真实生产连接、DDL、DML、回填、读激活动作（必须走 production activation 卡 + Pascal 显式触发）。
- 修改 router / fallback / provider / client facade 现有行为。
- 创建新 Mongo 账号/角色/索引（超出 Gate-2 授权）。
- 变更 consumer/service 以适配新能力。
- 修改 03-015 冻结语义或 P3-A 文件。

### 6.3 绝对禁止

- 硬编码敏感密钥与凭证；打印 URI/用户名/密码/token。
- 在本卡（文档阶段）执行任何真实连接、DDL/DML、Provider、回填、服务/cron、Git 操作。
- 伪造或降级 threshold：不得因数据不足 100% 而放宽完整性判定或手工生成 ranking。
- 自动 rollback / drop / 删除生产数据。
- 修改文档模板或既有 03-015/P3-A 文件。

---

## 7. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| Gate-1 发现真实数据不足 100%（缺行业/缺 close/日期断裂） | 中 | 高 | 严格按停止条件暂停，report 记录缺口；Pascal 决策是否缩小日期范围或修复上游 | 不进入 Gate-2；canary 候选日须 100% 完整 |
| expected universe 权威来源不一致（`stock_sector_info` L1 distinct 与公开申万体系冲突） | 中 | 高 | Gate-1 以 `stock_sector_info` `{classify_system:"SW"}` distinct 为唯一主来源（恰好 31）；`index_basic_info` 仅作可选元数据交叉核对，须按真实 `market="申万指数"` 字段语义使用；以 Pascal 确认的权威为准 | 停止并上报，不猜 |
| DDL 与已有索引规格冲突 | 低 | 中 | 幂等校验 + 规格比对；不一致即停止 | 停止，Pascal 决策 |
| backfill 中途失败（连接/权限/完整性） | 中 | 中 | 日级原子 + 失败停止 + 不自动 retry | 修复后从失败日重跑（幂等 upsert） |
| 误写已有集合 / 误建多余集合 | 低 | 高 | Gate-2/3 工具带 namespace 白名单断言；独立 Verify 复核 | 停止；不自动删除 |
| 身份泄露（URI/密码进入日志） | 低 | 高 | 脱敏过滤器 + 静态扫描 + 泄露即停止并 rotate | 停止，rotate 后重跑 |
| Gate-4 激活后发现查询行为与离线不符 | 低 | 中 | 只读 smoke 覆盖冻结 token 行为；回滚=禁用 binding | 禁用 binding，数据保留 |
| **Gate-4 fail-closed 原子性缺陷（P0-016-1，已发生）** | 已发生 | 高 | `write_binding(True)` 在 scope_diff 之前 + 失败不自动回滚 → binding 残留 enabled=true（实物 `gate4-report-20260803T105744.json`）。**修复契约 B（§5.5.2）**：precondition 全前置、post-smoke 失败自动回滚、binding_events 审计；T2 Design / T3 Implement 落实，T4/T5 独立验证后才解除 Gate-4 BLOCKED | 当前 binding 已人工回滚至 `enabled=false`（fail-closed 恢复）；修复前禁止任何 enable/disable |
| **literal CLI 无法构造 CompletedSessionPolicy（P0-016-2，已发生）** | 已发生 | 高 | `main(policy=...)` 仅 Python 注入，literal CLI 必 G4-S-002；旧卡 `/tmp` wrapper 伪造 calendar 属被禁止形态。**修复契约 A（§5.5.1）**：`--calendar-file` 可审计证据构造 + fail-stop + 禁止伪造 calendar | 修复前 Gate-4 保持 NO-GO；禁止 wrapper/`/tmp`/REPL 注入绕过 |
| **manifest 内 dirty 阻断 Gate-4（契约 C 前置缺失）** | 高（当前即存在） | 高 | 当前工作树 manifest 内 7 条 dirty（`common.py`、`gate3_backfill.py`、`gate4_activate.py`、fixture、`test_common.py`、`test_gate3.py`、`test_gate4.py`）→ G4-S-003 必然触发。修复：修复链 Review PASS 后 Pascal 显式授权 `git add/commit` **10 条 baseline 集**（7 manifest 内 + 三层文档）形成可审计基线（§5.8）；**不得用 `git restore`**（会丢弃已审查修复） | activation 保持 NO-GO；不自行 Git 操作 |
| Gate-3 独立 Verify 凭据授权范围偏差（审计事件 `t_1ae1dc26`） | 已发生 | 低 | Verify 卡 `t_1ae1dc26` 在收到独立明示凭据授权选择前，沿用父任务 `t_df73e76d` 对 `skills/.env` 的临时读取例外完成只读 Mongo Verify；数据核验 PASS，无 DML/DDL、无凭据输出或持久化。**该偏差必须作为既有事实写入 rollout 风险/审计，不得抹除或称为 clean credential closure**；后续 Verify/activation 卡必须取得独立明示的凭据授权选择 | 不触发回滚/重跑；数据证据继续有效；记录在案 |

---

## 8. 备选方案

### 8.1 备选方案 1：一次性全量 rollout（Gate-1~4 合并执行）

- 优点：流程最短。
- 缺点：任一环节失败无法定位；无法分步审计；违背"可停止"原则。
- 不选用原因：生产写入与 DDL 高风险，必须分 Gate 串行 + 独立 Verify（RFC-03-011 §8 先例与本卡任务要求一致）。

### 8.2 备选方案 2：先建最小权限账号再 rollout

- 优点：权限面最小。
- 缺点：创建账号/角色超出本卡授权边界，且当前连接源已可满足只读与 DDL；需额外授权流程。
- 处理：作为 Design 前置缺口（§11）上报；若 Pascal 判定需要，在 Design 阶段单独授权，不阻塞本 RFC 结构。

### 8.3 备选方案 3：用 mongomock 先做生产行为仿真

- 优点：零风险验证工具逻辑。
- 缺点：mongomock 与真实 Mongo 行为差异（索引冲突、权限、读偏好）无法覆盖。
- 处理：作为 Gate 工具的开发测试手段（单元测试），**不替代**真实 smoke；生产验证必须走 Gate-1/Gate-3/Gate-4 的真实只读/写后读回。

---

## 9. 验收标准

### 9.1 功能验收

- [ ] RFC-03-016 与 SPEC-03-016 各自独立、完整、互引（RFC 引用 SPEC 契约，SPEC 引用 RFC 策略），无合并文档
- [ ] 每个 Gate（1~4）均含副作用矩阵（read/write/create-index/external、namespace、最大范围、幂等、停止条件、审计证据、回滚/禁用）
- [ ] Gate-1~4 的可执行契约（查询预算、DDL 规格、backfill 日级原子、读激活）在 SPEC 中无歧义
- [ ] 明确 L1 universe 来源 = `stock_sector_info`（`classify_system="SW"` distinct 31），join field = `index_daily_quotes.full_symbol`，`index_basic_info` 仅可选交叉核对（非主来源）；无旧 `index_basic_info market="CN"` / `sector_code` 前缀作为生产 L1 主路径的表述
- [ ] 明确"授权已签署但未执行"，不把用户"全部授权"误写为动作已执行；**2026-08-03 更新：Gate-3 已授权并已实际执行 + 独立只读 Verify PASS；Gate-4 已获授权但未执行（Review PASS 前置 + 另卡 activation + 独立 Verify），不把"授权"误写为"已生效"**
- [ ] **Gate-3 range 契约修复**：`--range-file` 仅取 `coverage_by_date` 中可解析且数值 `ratio==1.0` 的键并默认排除最早满覆盖日；成对 `--start-date`/`--end-date` 仅在满覆盖子集取交集；无满覆盖/非法 ratio/越界 → fail-fast（G3-S-003）；全文不再允许 full `coverage_by_date.keys()` 作为 range；已完成的 34,534 行不回滚、不重跑
- [ ] **Gate-4 P0 列为真实 blocker（不掩盖）**：§1/§2.4/§5.5/§7 明确 P0-016-1（fail-closed 原子性）与 P0-016-2（literal CLI policy 构造）为真实 blocker；Gate-4 标注 NO-GO / BLOCKED；任何 APPROVE/PASS 不构成 enable/disable 放行；不把「授权」或「已审查」误写为「已生效/已修复」
- [ ] **契约 A 齐备（literal CLI policy 构造）**：§5.5.1 定义无 wrapper 的 `--calendar-file` 构造路径、真实 calendar evidence 来源（source/as_of/timezone/cutoff/trading_days）、fail-stop（G4-S-002（退出码 2））、禁止伪造 calendar（coverage_by_date / FakeTradeCalendar / 硬编码均禁止）
- [ ] **契约 B 齐备（原子 fail-closed）**：§5.5.2 定义所有 precondition（含 pre-smoke、scope/baseline diff）在 `write_binding(True)` 之前完成；任一 precondition 失败证明 binding remains false；post-smoke 失败 → 自动 `write_binding(False)` 回滚 + binding_events 审计；最终态必须 false
- [ ] **契约 C 齐备（baseline 前置）**：§5.8 区分 **baseline commit 集（10 条精确路径：7 manifest 内 dirty + 3 层文档）** 与 **activation manifest-relevant required clean set（manifest 14 条路径全部 clean）**；列出需 Pascal 显式授权的 `git add`/`git commit` 动作（GIT-016-1~3，逐路径列出）；明确**不把 `git restore` 写为推荐路径**；activation 卡禁止自行 Git 操作
- [ ] **D 明确不处理/禁止**：§5.5/§10 明确暂不处理 Mongo DML/DDL、Gate-3 rerun、Provider、cache/router、service/cron/systemd、真实交易、任何写 binding、任何 secrets 读取
- [ ] **E 后续阶段齐备（T2~T6 + activation/Verify 隔离）**：§10 给出修复链 allowlist 与可验证验收；PT-016-6/7 定义 baseline 前置与 activation/独立生产 Verify 授权点隔离
- [ ] 后续 Design 的精确 inputs（每 Gate 工具输入/输出、文件范围预期、离线/真实分离、验收证据）已列出

### 9.2 非功能验收

- [ ] 全文不含模糊"按需 / 可选 / 由实现者决定"的生产语义（静态扫描确认）
- [ ] 不修改 03-015/P3-A/模板；只新增两份文档
- [ ] `git diff --check HEAD` 通过（无空白错误）
- [ ] 无真实连接/DDL/DML/Provider/回填/服务/cron/Git 动作

---

## 10. 落地计划（阶段划分）

| 阶段 | 内容 | 产出 |
|---|---|---|
| T1（本卡） | RFC-03-016 + SPEC-03-016（**V0.7/V0.8 Gate-4 P0 根因审计与契约 A/B/C 修订**） | 两份独立文档 |
| T2 Design | **Gate-4 P0 修复设计**：DESIGN-03-016 升级 V0.11（已由卡 `t_702b97fe` 完成）——落实契约 A（`--calendar-file` 构造 CompletedSessionPolicy，literal CLI 无 wrapper）、契约 B（precondition 全前置、post-smoke 自动回滚、binding_events）、契约 C（baseline 动作计划）；V0.12 由本卡 `t_ea99efaa` 同步 baseline 集合对齐（10 条 commit 集 / 14 条 clean set） | DESIGN-03-016（V0.11→V0.12） |
| T3 Implement | 按 Design 实现 Gate-4 修复（离线可测，dry-run 默认）；建议 allowlist：`scripts/unified_data/sector_ranking_rollout/gate4_activate.py`、`scripts/unified_data/sector_ranking_rollout/common.py`（calendar loader，如 Design 需要）、`scripts/unified_data/sector_ranking_rollout/prod_repository.py`（如 Design 需要）、`skills/data/unified_data/tests/fixtures/sector_ranking_rollout_fixtures.py`（calendar evidence fixture）、`skills/data/unified_data/tests/test_sector_ranking_rollout_gate4.py`、`skills/data/unified_data/tests/test_sector_ranking_rollout_common.py`（如新增 loader）；**精确 allowlist 以 T2 Design 为准，实现只新增/修改 allowlist 内文件** | Gate-4 工具代码 + 测试 |
| T4 Verify | 独立验证：单测 + dry-run + 离线 enable 全路径（mongomock）+ 失败注入（scope_diff dirty → binding remains false；post-smoke fail → 自动回滚；calendar 缺失/非法 → fail-fast）；只读，不触 Mongo/Git | 验证报告 |
| T5 Review | 独立审查 RFC/SPEC/Design/实现一致性；确认 P0-016-1/P0-016-2 已实质修复 | verdict |
| Closeout | 汇总、残余风险 | closeout report |
| **Baseline 形成（Review PASS 后，Pascal 显式授权）** | 按契约 C（§5.8）：`git add` **10 条 baseline 集路径**（7 manifest 内 dirty + 三层文档，逐路径列出） + `git commit` 形成可审计基线；**禁止 `git restore`/`stash`/`clean`**；activation 卡不自行 Git | 基线 commit |
| Production activation（Baseline 后） | **Gate-1/2/3 已执行并验证**；**Gate-4 activation 卡**（Pascal 显式触发 + 单独授权，literal CLI + `--calendar-file`，无 wrapper）→ **独立生产 Verify 卡**（yquanttester，单独凭据授权，只读） | 各 Gate report / 实物证据 |

**D（明确不处理/禁止，本 RFC/SPEC 全程有效）**：Mongo DML/DDL（超出 Gate-2/3 已执行范围）、Gate-3 rerun、Provider、cache/router、service/cron/systemd、任何真实交易、任何写 binding（仅未来 activation 卡可写）、任何 secrets 读取（本卡及后续文档/验证阶段不读 `skills/.env`；Verify/activation 卡需单独授权）。

**E（可验证验收，修复链通过标准）**：T4 Verify 必须实测——① literal CLI `--enable --apply --yes --calendar-file <合法>`（离线 mongomock）全 precondition 通过 → binding=true → post-smoke 通过 → binding=true（binding_events 顺序正确）；② scope_diff 含 manifest 内 dirty → exit 2 + binding remains false（无 write_binding(true) 事件）；③ post-smoke 注入失败 → exit 2 + binding_events 含 rollback(false)，最终态 false；④ `--calendar-file` 缺失/非法 → fail-fast（G4-S-002（退出码 2）），0 fetch/0 smoke/0 write；⑤ `git diff --check` 通过、secrets scan 干净、readonly proof 一致。

---

## 11. 开放问题 / Design 前置缺口

| 编号 | 缺口 | 影响 | 处置 |
|---|---|---|---|
| OQ-016-1 | 现有连接源是否满足最小权限（只读/只写/DDL 三类分离） | Gate-3/4 权限模型 | Design 阶段评估；若需新账号/角色 → 单独授权上报 Pascal |
| OQ-016-2 | ~~`index_basic_info` 是否含 SW L1 权威 code/name~~ **已校正（L1 契约校正）**：L1 universe 唯一主来源 = `stock_sector_info`（`{classify_system:"SW"}` distinct `(l1_code,l1_name)` = 31）；行情 join field = `index_daily_quotes.full_symbol`；`index_basic_info` 不得用作 L1 universe 枚举主来源，仅可作可选元数据交叉核对，须按生产真实 `market="申万指数"` 字段语义使用 | Gate-1 expected universe | **已闭合**：主来源 `stock_sector_info`；Gate-1 report 固化 31 个 L1 code（`.SI` 后缀）+ code→name；`index_basic_info` 交叉核对按真实字段语义 |
| OQ-016-3 | canary 候选日选定规则细节（完整度最高的最近日 vs 最早日） | Gate-3 canary | Design 定义（基于 Gate-1 证据），本 RFC 只约束"至多 1 个 + 100% 完整" |
| OQ-016-4 | ~~全量 backfill 日期范围解析（Gate-1 全范围 vs Pascal 指定子范围）~~ **已闭合（2026-08-03 range 契约修复）**：`--range-file` 仅取 `coverage_by_date` 中可解析且数值 `ratio==1.0` 的键并默认排除最早满覆盖日；成对 `--start-date`/`--end-date` 仅在满覆盖子集取交集；无满覆盖/非法 ratio/越界 → fail-fast（G3-S-003）。实际执行已用 paired `2021-12-14→2026-07-30` 取得等价 1,114 日 | Gate-3 范围 | **已闭合**：SPEC V0.7 G3-B-001/G3-B-013~016/G3-S-003 固化；实现偏差（`--range-file` 取全部键）由后续 Implement 修复 |
| OQ-016-5 | Gate-4 后是否需要查询辅助索引 `idx_dataset_date` | Gate-4 查询性能 | 由未来 RFC 评估，不并入本 rollout |
| OQ-016-6 | **literal CLI policy 构造路径（契约 A）** | Gate-4 activation 可执行性 | T2 Design 定义 `--calendar-file` schema 与 loader；T3 Implement 落实；无 wrapper；证据缺失/非法 fail-stop（§5.5.1 A-016-1~6） |
| OQ-016-7 | **baseline 形成授权（契约 C）** | Gate-4 activation 前置 | 修复链 Review PASS 后 Pascal 显式授权 GIT-016-1~3（§5.8，`git add` 10 条 baseline 集路径）；**不得把 `git restore` 写为推荐路径**；本卡不代为授权 |
| OQ-016-8 | **post-smoke 失败自动回滚（契约 B）** | Gate-4 fail-closed 原子性 | T2 Design / T3 Implement 落实自动 `write_binding(False)` + binding_events；T4 Verify 以失败注入实测（§10 E） |

---

## 12. 参考资料

- RFC-03-015-historical-sector-ranking（V0.5）
- SPEC-03-015-historical-sector-ranking（V0.5）
- DESIGN-03-015-historical-sector-ranking（V0.5，§8 与附录 A）
- RFC-03-011-unified-data-phase-2-quality-audit-governance（§8 副作用矩阵/停止条件/最小权限身份先例）
- RFC-03-014-p3a-sector-provider-activation（P3-A 边界）
- SPEC-03-016-historical-sector-ranking-production-rollout（本 RFC 对应 SPEC）

---

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.8（Contract C baseline 集合对齐，本卡 `t_ea99efaa`） | 2026-08-03 | P0 Principal（Full Flow Contract C 对齐卡，仅三层文档）：**baseline 授权集合与 `gate4_activate.py` 实物 `BASELINE_MANIFEST` 对齐**——① 实物核对 `BASELINE_MANIFEST`（gate4_activate.py:62-77）共 **14 条路径**，当前工作树 **manifest 内 dirty 恰 7 条**（`common.py`、`gate3_backfill.py`、`gate4_activate.py`、`sector_ranking_rollout_fixtures.py`、`test_sector_ranking_rollout_common.py`、`test_sector_ranking_rollout_gate3.py`、`test_sector_ranking_rollout_gate4.py`；T3 Gate-4 修复 5 文件 + Gate-3 range 修复 2 文件）；三层文档**不在 manifest 内**（docs dirty 属 out_of_manifest，记录不停止）；② §5.8 区分 **baseline commit 集（10 条：7 manifest 内 + 三层文档）** 与 **activation manifest-relevant required clean set（manifest 14 条全部 clean）**，明确旧「五候选路径」不足以通过 activation（只 commit 5 条时 `common.py`/`gate4_activate.py`/fixture/`test_common.py`/`test_gate4.py` 仍 dirty → G4-S-003 必触发）；③ GIT-016-1 改为逐路径列出 10 条 `git add` 目标；禁止 `git add -A/.`、restore/reset/stash/clean；④ 新增 baseline 形成前独立 scope/test/secret/manifest diff 验证（T4/T5）；⑤ 明确本卡不构成 Git commit / activation / production credential 许可；⑥ §7 风险表、§9.1 验收、§10 T2/Baseline、§11 OQ-016-7、PT-016-6 同步。**未改变** Gate-1/2/3 契约、退出码总体集合（仍 0/1/2/3/4）、per-day budget 模型、L1 契约、连接源、Gate-3 已执行实物（34,534 行不回滚/不重跑）、契约 A/B 语义。Gate-4 保持 **NO-GO / BLOCKED**（P0-016-1/P0-016-2 修复链 Review PASS + 契约 C baseline 形成 + activation 另卡后才解除）。依赖 SPEC V0.8 → V0.9；对应 DESIGN V0.11 → V0.12 | YQuant-Principal |
| V0.7（Gate-4 P0 根因审计与契约修订，本卡 `t_1e649585`） | 2026-08-03 | P0 Principal（Full Flow T1 修复卡）：**Gate-4 P0 根因审计**——① P0-016-1 fail-closed 原子性缺陷：`gate4_activate.py` enable 路径 `write_binding(True)`（:366）在 strict `scope_diff`（G4-S-003，:391-396）之前执行，G4-S-003 触发时 binding 已写 true 且 `except Gate4Stop`（:435-443）不自动回滚；实物证据 `gate4-report-20260803T105744.json`（before=false/after=true/stop=G4-S-003）、`105826`/`105832` 同态、`105840` 人工 disable 回滚；binding 现 `enabled=false`。② P0-016-2 literal CLI policy 构造缺陷：`main(policy=...)` 仅 Python 注入，literal CLI 必 G4-S-002（实物 `gate4-report-20260803T105510.json`）；旧卡 `t_aaeb7319` 以 `/tmp` wrapper + `FakeTradeCalendar(coverage_by_date ∪ {today})` 绕过，属禁止的伪造 calendar。③ 契约 A（§5.5.1）：literal CLI `--calendar-file` 无 wrapper 构造 CompletedSessionPolicy，可审计证据（source/as_of/timezone/cutoff/trading_days）+ fail-stop + 禁止伪造 calendar。④ 契约 B（§5.5.2）：所有 precondition（含 pre-smoke、scope/baseline diff）在 `write_binding(True)` 之前；任一失败证明 binding remains false；post-smoke 失败自动 `write_binding(False)` 回滚 + binding_events 审计。⑤ 契约 C（§5.8）：Gate-4 baseline 前置——精确五候选路径（RFC/SPEC/DESIGN-03-016、gate3_backfill.py、test_sector_ranking_rollout_gate3.py）+ Pascal 显式授权 GIT-016-1~3（`git add` 五路径 / `git commit` / 可选 tag）；**禁止把 `git restore` 写为推荐路径**；activation 卡禁 Git。⑥ §7 风险表新增 3 条 P0 风险行；§9.1 新增 P0 blocker/契约 A/B/C/D/E 验收项；§10 重构修复链（T2 Design→V0.11、T3 allowlist、T4 失败注入验收、Baseline、activation/独立 Verify 隔离）；§11 新增 OQ-016-6/7/8。⑦ PT-016-6/7：baseline 前置 + activation 与独立生产 Verify 授权点隔离（吸取 `t_1ae1dc26` 教训）。**未改变** Gate-1/2/3 契约、退出码总体集合（仍 0/1/2/3/4）、per-day budget 模型、L1 契约、连接源、Gate-3 已执行实物（34,534 行不回滚/不重跑）。Gate-4 保持 **NO-GO / BLOCKED**。依赖 SPEC V0.7 → V0.8；对应 DESIGN 当前 V0.10（T2 升 V0.11，本卡未改动 DESIGN） | YQuant-Principal |
| V0.6（Gate-3 range 契约修复 + Gate-4 授权前置同步，本卡 `t_a33204a7`） | 2026-08-03 | P0 Principal（Full Flow T1）：① `--range-file` 契约收紧——仅取 `coverage_by_date` 中**可解析且数值 `ratio==1.0`** 的满覆盖键集（禁止以全部键作为 range），默认排除该满覆盖子集最早满覆盖日；成对 `--start-date`/`--end-date` **仅在满覆盖子集上取交集**，不能作为绕过 ratio 过滤的替代路径；无满覆盖日期 / 非法 ratio（缺失、非数值、不可解析日期键）/ 用户范围超出满覆盖集合 → 稳定 fail-fast（G3-S-003，EXIT_PARAM(1)）。② §5.1.3/§5.4 固化 Gate-3 实际执行 + 独立只读 Verify PASS 实物证据（1,114 日 / 34,534 行 / 0 failed / 0 stop；canonical report `data/rollout/sector-ranking/gate3-report.json`）；本修复不回滚、不重跑、不触碰已有 34,534 行。③ §2.4/§1 声明同步：Gate-3 已执行并验证；Gate-4 已获 Pascal 授权但 Review PASS 前禁止 enable/disable，真实 activation 另卡 + 独立 Verify 后才生效。④ §7 风险表固化 Verify 凭据授权范围偏差审计事件（卡 `t_1ae1dc26`：沿用父任务 `skills/.env` 临时读取例外，数据核验 PASS，无 DML/DDL），不得抹除或声称 clean credential closure。OQ-016-4 闭合。**未改变** Gate 契约、退出码总体集合（仍 0/1/2/3/4）、per-day budget 模型、L1 契约、连接源、授权边界。依赖 SPEC 更新至 V0.7；对应 DESIGN 仍为 V0.9（本卡未改动，T2 Design 卡更新指针） | YQuant-Principal |
| V0.5（Gate-4 readiness 卡 `t_e30dc947` 全量范围契约校正 + recovery closure `t_a6b7636e` 收口） | 2026-08-02 | P0 Principal recovery（任务 `t_a6b7636e`，替代 timeout 的 Gate-4 readiness 卡 `t_e30dc947`，只读核验 + 授权包）：**全量 backfill 范围契约与 Gate-1 实物证据不一致校正**——Gate-1 report（2026-08-01T07:27:03Z）`coverage_by_date` 6,422 键中仅 **1,115 个 ratio==1.0 满覆盖日**（2021-12-13 → 2026-07-30，= `canary_candidates` 全集）；5,307 个部分覆盖日（observed=16/27/28，ratio 0.516/0.871/0.903）在 100% exact-match（G3-S-004）下必然 incomplete 停止，**不得纳入全量范围**。① §5.1.3 数值边界：全量范围 6,421 日 → **1,114 日**（满覆盖 1,115 − G3-B-016 排除最早满覆盖日 2021-12-13〔前一日 2021-12-10 部分覆盖〕），全量期望累计 398,102 → **69,068 行**（informational）；② §5.4 `--range-file` 范围限定为 `coverage_by_date` 中 **ratio==1.0 的键**，默认排除最早满覆盖日；③ 依赖 SPEC V0.4 → **V0.6**、关联 Design 增列 DESIGN-03-016 V0.9；④ **Gate-3 全量 backfill 尚未执行/验证（canonical report 仅单日 canary PASS）→ Gate-4 consumer binding 仍为 NO-GO**，本层文档不产出 activation approval。旧数值 6,421/398,102 仅保留于本 changelog 及 V0.3 行（superseded history），不再承担现行行为语义。**未改变** Gate 契约、退出码总体集合（仍 0/1/2/3/4）、per-day budget 模型、L1 契约、连接源、授权边界。SPEC 更新至 V0.6、DESIGN 更新至 V0.9 | YQuant-Principal |
| V0.4（Design Gate `t_1f6c001b` REVISE 七项 minor 闭合 — provenance 指针同步） | 2026-08-01 | P0 Principal amendment（任务 `t_f7922150`）：Design Gate `t_1f6c001b` REVISE 的 M1~M7 全部由 SPEC V0.5 / DESIGN V0.8 闭合（G3-B-018 公式、BudgetReader 构造签名、`reset_stats()` 语义、`total_query_rows` 派生、`failed_days[]` 保留、fixture allowlist、共享目录基线）。本 RFC **无语义变更**，仅同步 provenance：依赖 SPEC V0.4 → V0.5、对应 DESIGN V0.7 → V0.8。**未改变** Gate 契约、退出码总体集合（仍 0/1/2/3/4）、L1 契约、连接源、授权边界 | YQuant-Principal |
| V0.3（Gate-3 查询预算范围校正） | 2026-08-01 | P0 设计校正（任务 `t_888c30fb`），对齐 SPEC V0.4 / DESIGN V0.7：§5.1.3 Gate-3 副作用矩阵「最大日期/记录范围」行引用 per-day scoped budget 模型——Gate-3 查询预算按日 scoped（每 `process_day` 独立/reset 计数），不继承 Gate-1 全局累计 100k 上限（G1-B-006，Gate-1 report scope）；日级上限 = 4 × expected = 124 行，超过 → G3-S-013；全量累计 398,102（informational）不阻断；扫描保护 G1-B-001~005 全保留。停止条件行更新为 G3-S-001~013（新增 G3-S-013 日级越界）；审计证据行加 per-day query_budget + total_query_rows/resumption_boundary。选 Option A（per-day scoped）而非 B（chunk/resume）或 C（aggregate）的 rationale 见 SPEC §3.4.2.bis。**未改变** Gate 业务语义、退出码总体集合、L1 契约、连接源、授权边界。SPEC 更新至 V0.4、DESIGN 更新至 V0.7。**〔superseded history〕**：本行「全量累计 398,102」基于旧假设（coverage_by_date 全键满覆盖），已被 V0.5 校正为 1,114 × 62 = 69,068（ratio==1.0 满覆盖日模型）；本行不再承担现行行为语义 | YQuant-Principal |
| V0.2（L1 契约校正） | 2026-08-01 | 根据 Pascal 最新裁定与 2026-08-01 只读生产核验，校正 L1 universe 来源与 join 契约：universe 主来源 `index_basic_info`(market=CN) → `stock_sector_info`(classify_system=SW distinct l1_code/l1_name = 31)；join field `sector_code` → `index_daily_quotes.full_symbol`；code canonical 形态 `.SI` 后缀；`index_basic_info` 降级为可选元数据交叉核对（须按真实 market="申万指数" 字段语义）；明确 L2/L3 不在本期范围（`index_daily_quotes` 仅 L1 行情）；明确最小数据质量（pct_chg 必须、close 缺失 fail-stop、最早日 pre_close 缺失不得以全历史 OHLC 阻断同日有效横截面）。§5.1.1/§5.2/§5.4/§7/§9.1/§11(OQ-016-2) 同步修订 | YQuant-Principal |
| V0.1（T2.2 修订） | 2026-07-31 | 交叉文档闭合（Gate `t_e1611476` REVISE）：更新依赖 SPEC 版本指针至 V0.2（F4）；Gate-3 范围来源唯一化（`--range-file` / 成对 `--start-date`/`--end-date` 二选一，无范围来源 → EXIT_PARAM(1)，F1）；交易日状态判定归 Gate-4 工具层可注入 CompletedSessionPolicy（非 03-015 冻结 service，F2）。仅修订指针与语义表述，不改变 V0.1 既有设计事实 | YQuant-Principal |
| V0.1 | 2026-07-31 | 初始创建：生产 rollout Gate-1~4 受控激活 RFC（副作用矩阵、Gate 契约、凭据边界、production task 规则） | YQuant-Principal |
