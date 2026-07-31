# DESIGN-03-016: 历史行业 sector.ranking 生产 Gate-1~4 rollout 工具与逐 Gate 执行设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-31 |
| 最后更新 | 2026-07-31（V0.4 修订：T2.3 交叉文档闭合——Gate-3 canary 与全量范围来源互斥冻结；历史修订见 Changelog） |
| 来源 RFC | RFC-03-016-historical-sector-ranking-production-rollout（V0.1） |
| 来源 SPEC | SPEC-03-016-historical-sector-ranking-production-rollout（V0.2） |
| 目标模块 | 03_data（数据层）— 生产 rollout 工具与 Gate 执行 |
| 适配 Agent | YQuant-Developer-Engineer（T3 Implement）、YQuant-Test-Engineer（T4 Verify / 逐 Gate 只读 Verify）、YQuant-Reviewer-Principal（T5 Review） |

## 0. 版本说明

V0.1 为初始版本。本设计把 RFC-03-016 的 4 个生产 Gate 与 SPEC-03-016 的可执行契约落实为：

1. 一组**离线可测、dry-run 默认、--apply 显式副作用**的 Gate 工具（`gate1_smoke` / `gate2_ddl` / `gate3_backfill` / `gate4_activate`）+ 共享组件。
2. 每个 Gate 的**精确文件范围（T3 allowlist）**、控制流、接口、report 结构、测试矩阵。
3. **Production activation 卡 action plan**：Review PASS 后逐 Gate 串行执行的精确命令、独立只读 Verify 判定标准、回滚动作。

**V0.2 修订（评审 #864 闭合）**：仅闭合两处——① 连接源收敛为 RFC CR-016-1/2 的唯一受控 `MONGODB_*` 组件来源（`MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE`），组件式构造、不允许 URI、CLI 不再暴露 `--conn`/prefix 选择、无 alias/fallback；② T3 allowlist 统一为 **14 个新文件**（8 工具/数据 + 1 fixture + 5 tests）并全篇一致。**不改变** Gate-1~4 业务语义、退出码与停止条件；report 字段仅替换连接源字段（`conn_prefix` → `conn_source`/`conn_fingerprint`，见 §3.4.4 G1-R-002 落实说明）。

**V0.3 修订（T2.2 交叉文档闭合，Gate `t_e1611476` REVISE 关闭）**：闭合 2 项 MAJOR 与 2 项 MINOR——F1 Gate-3 范围来源唯一化（`--range-file` 进入 CLI synopsis，与成对 `--start-date`/`--end-date` 互斥，无范围来源 → EXIT_PARAM(1)，§8.3 全量命令显式传 `--range-file`）；F2 交易日状态判定由 Gate-4 工具层新建可注入 TradeCalendar / CompletedSessionPolicy 执行（§3.3.5，非修改 03-015 冻结 service），G4-R-003/G4-V-004 以 fake calendar + fake clock 逐项证伪；F3 G1-B-002 过滤白名单统一（含 `market`）；F4 provenance 修正（RFC V0.1 / SPEC V0.2 / DESIGN V0.3）。同步闭合 OBS-1（`conn_prefix` 为被 V0.2 替代的旧概念）、OBS-2（Gate-4 git-status 收敛为 activation 卡路径 allowlist / baseline manifest）。**未改变** V0.1/V0.2 已冻结的 Gate 业务语义、退出码、连接源与 allowlist 总数（仍 14）。

本设计**不修改** 03-015 已冻结语义（schema、pct_chg 口径、完整性判定、结果语义冻结表、warning token、source_trace 枚举）与既有代码；**不执行**任何真实连接 / DDL / DML / Provider / 回填 / 服务 / cron / Git 操作（T3 仅 mongomock + 显式 fixture）。

---

## 1. 设计摘要

RFC-03-016 / SPEC-03-016 定义了生产 rollout 的**契约**（副作用矩阵、停止条件、退出码、审计证据），本设计将其落实为**可实现的工具族与可执行的逐 Gate 动作**。

核心设计决策：

| 决策点 | 结论 | 理由 |
|---|---|---|
| Gate 工具存放位置 | 新建包 `scripts/unified_data/sector_ranking_rollout/` | 与 `scripts/unified_data/audit_rollout.py`（RFC-03-011 生产 DDL 工具先例）同层；`scripts/__init__.py` 已声明 scripts 子包可被测试 import（`scripts.t4_preflight` 先例） |
| 工具与运行时库分离 | Gate 工具全部是**新文件**，不触碰 `skills/data/unified_data/` 任何既有文件 | SPEC §7：实现阶段只新增 Gate 工具文件与测试；03-015 冻结文件清单见 §2.2 |
| 真实写入路径 | 新建 `ProdRankingWriter`（允许真实 pymongo + namespace 白名单），复用 `UpsertOutcome` | 03-015 `HistoricalRankingWriter` 的 `_assert_fake_db` 拒绝真实 pymongo 且文件冻结，Gate-3 必须新增生产 writer |
| 真实读路径 | 新建 `ProdRankingReader`（实现与 `HistoricalRankingWriter.get()` 相同的 duck-typed 接口），注入**冻结的** `HistoricalSectorService` | 复用 03-015 全部冻结读契约（参数校验、token、排序、limit、source_trace），零修改 service |
| Gate-4 激活机制 | `binding_state.json` 开关 + `ProdRankingReader` fail-closed | RFC §5.5「回滚 = 禁用 facade / feature binding」；开关可测、可回滚；consumer 集成属独立变更（G4-R-005） |
| 复用点 | `build_ranking_rows` / `SectorRankingDaily` / `is_valid_trade_date` / `coerce_float` / warning token 常量 | 03-015 已冻结的纯函数与常量，Gate-1/3/4 直接 import |
| 离线/真实分离 | 工具核心逻辑全部可注入 mongomock db；`--apply` 才产生真实副作用；真实执行仅在 production activation 卡 | SPEC §2.2 / RFC §4.1 幂等、可停止、可审计 |
| 退出码 | 严格按 SPEC G0-C-004：0 成功 / 1 参数前置失败 / 2 停止条件 / 3 连接凭据 / 4 verify 失败 | 与 audit_rollout.py 的映射不同，03-016 以 SPEC 为准 |

**成功标准**：Design 文档存在且提供 T3 Implement 的精确 allowlist、每 Gate 工具行为到函数级、测试矩阵、逐 Gate production activation 命令与 Verify 判定；`git diff --check HEAD` 通过；不触碰任何既有文件。

---

## 2. 现状分析

### 2.1 相关目录与文件

| 路径 | 现状 | 本设计关系 |
|---|---|---|
| `scripts/unified_data/audit_rollout.py` | RFC-03-011 生产 DDL/rollout 工具（dry-run 默认、退出码 0-4、allowlist、secrets guard） | **只读参考**（CLI/脱敏/退出码模式）；禁止修改 |
| `scripts/unified_data/audit_smoke.py` | RFC-03-011 smoke 工具 | 禁止修改 |
| `scripts/unified_data/__init__.py` | 已存在 | 不修改 |
| `skills/data/unified_data/models/domain/sector_ranking.py` | `SectorRankingDaily` 9 字段 + `KNOWN_DATASETS` + `is_valid_trade_date` + `coerce_float` + `REQUIRED_FIELDS`（03-015 冻结） | **import 复用**；禁止修改 |
| `skills/data/unified_data/services/historical_sector_service.py` | `HistoricalSectorService`（只读查询）+ `build_ranking_rows` 纯函数 + `BuildOutcome` + `WARNING_EMPTY`/`WARNING_INCOMPLETE`（03-015 冻结） | **import 复用**（Gate-3 用 build_ranking_rows；Gate-4 注入 ProdRankingReader）；禁止修改 |
| `skills/data/unified_data/adapters/historical_ranking_writer.py` | `HistoricalRankingWriter`（mongomock-only，拒绝真实 pymongo；get/upsert/delete；`COLLECTION="03_data_ud_sector_ranking_daily"`；`UNIQUE_KEY`）（03-015 冻结） | **接口参考**（ProdRankingWriter/Reader 对齐其 `get()` 接口）；禁止修改 |
| `skills/data/unified_data/adapters/p3_persistence_writer.py` | `UpsertOutcome`（persisted/failed/failed_keys/errors） | **import 复用**（ProdRankingWriter 返回该类型）；禁止修改 |
| `skills/data/unified_data/adapters/ta_cn_mongo_adapter.py` | TA-CN 只读 adapter（`get_index_list(market)` / `get_index_daily_bars(...)` 读 `index_basic_info` / `index_daily_quotes`） | **只读参考**（Gate-1/3 的查询模式参考）；禁止修改、不在 T3 引用（Gate 工具自带 BudgetReader） |
| `skills/data/unified_data/client.py` | `UnifiedDataClient.get_sector_ranking_history()` 条件性 facade（仅注入 mongomock db 时可测；`historical_ranking_db=None` 时 RuntimeError） | 禁止修改；Gate-4 激活的是**独立的生产读路径**（ProdRankingReader + binding），consumer 集成留待独立变更 |
| `skills/data/unified_data/tests/test_sector_ranking_history.py` | 03-015 离线单测（51 项定向） | 回归范围；禁止修改 |
| `skills/data/unified_data/tests/fixtures/historical_ranking_fixtures.py` | `make_mongomock_db` / `make_valid_ranking_rows` / `EXPECTED_SECTOR_CODES` 等 | 禁止修改；Gate 工具测试用**新增** fixture |
| `skills/.env` | `MONGODB_*` 主连接（`MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE`，库 `tradingagents`）+ `YQUANT_UD_AUDIT_*` 三组身份 | Gate 工具仅使用该唯一受控连接源（五键组件式构造，无 URI/prefix/alias/fallback）；不读取/打印值 |
| `data/rollout/` | 不存在（需创建） | Gate report / logs / reference 的固定产物目录 |

> 注意：`git status` 当前显示 `client.py`、`models/domain/__init__.py`、`providers/akshare.py` 为 03-015 阶段的**未提交修改**。本设计（及后续 T3）**不得**改动这些文件；未提交状态与 03-016 无关，由 orchestrator 在 03-015 closeout 时处理。

### 2.2 精确禁止修改路径（T3 allowlist 外延）

- ❌ 03-015 冻结：`models/domain/sector_ranking.py`、`services/historical_sector_service.py`、`adapters/historical_ranking_writer.py`、`client.py`、`models/domain/__init__.py`、`tests/test_sector_ranking_history.py`、`tests/fixtures/historical_ranking_fixtures.py`
- ❌ P3-A 冻结：`providers/akshare.py`、`providers/sector_client.py`、`providers/_stub_columns.py`、`providers/__init__.py`、`tests/fixtures/sector_activation_fixtures.py`、`tests/test_sector_provider_activation.py` 及 03-014 全部文件
- ❌ 既有 rollout 工具：`scripts/unified_data/audit_rollout.py`、`scripts/unified_data/audit_smoke.py`、`scripts/t4_preflight/**`、`scripts/service_readiness/**`
- ❌ 文档模板：`docs/rfc/RFC-00-000-*`、`docs/spec/SPEC-00-000-*`、`docs/design/DESIGN-00-000-*`、3 层 README
- ❌ 任何 `.env` / config / requirements / SKILL.md / README / router / provider / service 注册

### 2.3 关键复用点与缺口

| 复用点 | 来源 | 用途 |
|---|---|---|
| `build_ranking_rows(rows, expected, dataset, trade_date) -> BuildOutcome` | 03-015 service（冻结） | Gate-3 每交易日构建（100% exact-match、pct_chg 固定公式、稳定排序、连续 rank） |
| `SectorRankingDaily.from_dict` / `REQUIRED_FIELDS` / `coerce_float` / `is_valid_trade_date` / `KNOWN_DATASETS` | 03-015 domain（冻结） | Gate-3 行校验、写后读回字段校验；Gate-4 非法日期 ValueError 语义复用 |
| `WARNING_EMPTY` / `WARNING_INCOMPLETE` / `HistoricalSectorService` | 03-015 service（冻结） | Gate-4 冻结 token 行为复用（注入 ProdRankingReader） |
| `UpsertOutcome` | 03-015 p3_writer（冻结） | ProdRankingWriter.upsert 返回值 |
| `HistoricalRankingWriter.get(collection, filter)` 接口形态 | 03-015 writer（冻结） | ProdRankingReader 对齐该 duck-typed 接口以便注入冻结 service |
| audit_rollout.py 的 CLI/脱敏/退出码模式 | scripts/unified_data（冻结） | common.py 设计模式参考 |

| 缺口 | 本设计补齐方式 | 章节 |
|---|---|---|
| 真实 Mongo 写入需要 production writer | 新建 `ProdRankingWriter`（允许真实 pymongo + namespace 白名单断言） | §3.6 |
| 生产读路径需要真实 reader | 新建 `ProdRankingReader`（duck-typed `.get()`，可注入冻结 service） | §3.7 |
| 真实连接构造 | 新建 `ConnLoader`（仅 `MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE` 五键组件式构造；无 URI/prefix/alias/fallback；不打印值） | §3.3 |
| Gate-1/3 查询预算强制 | 新建 `BudgetReader`（白名单 + limit + maxTimeMS + 统计） | §3.3 |
| 交易日状态判定（未来日/当日未收盘/非交易日，F2） | 新建 `TradeCalendar`（抽象 + `FakeTradeCalendar`）/ `CompletedSessionPolicy` + `SessionStatus`（可注入；common.py 提供）；`ProdRankingReader` 读入口执行；生产以受控 live calendar evidence 激活（fail-closed） | §3.3.5 / §3.7.2 |
| Gate-4 激活/回滚开关 | `binding_state.json` + fail-closed 读取 | §3.7 |

---

## 3. 方案设计

### 3.1 模块/文件改动（T3 Implement allowlist）

#### 3.1.1 新建文件（精确路径，全部允许）

**T3 allowlist 总数 = 14**：8 工具/数据文件（7 工具 + 1 reference 数据）+ 1 fixture + 5 tests。下表为唯一权威清单；与 §4 实现步骤、§5.1 测试矩阵、§7.1 交接、§8 验收一致。

| 文件 | 内容 | 说明 |
|---|---|---|
| `scripts/unified_data/sector_ranking_rollout/__init__.py` | 包标记 + `__all__` 导出 | 空包标记即可 |
| `scripts/unified_data/sector_ranking_rollout/common.py` | `ConnLoader` / `BudgetReader` / `ReportWriter` / JSONL logger / `redact()` / `scan_secrets()` / 退出码常量 / `resolve_report_dir()` / `TradeCalendar`（抽象 + `FakeTradeCalendar`）/ `CompletedSessionPolicy` + `SessionStatus` | 4 个 Gate 工具共享；见 §3.3（policy 见 §3.3.5，F2 闭合） |
| `scripts/unified_data/sector_ranking_rollout/gate1_smoke.py` | Gate-1 只读 smoke + 权威 expected universe 校验 CLI | SPEC §3.2；见 §3.4 |
| `scripts/unified_data/sector_ranking_rollout/gate2_ddl.py` | Gate-2 DDL CLI（createCollection + 唯一索引，幂等） | SPEC §3.3；见 §3.5 |
| `scripts/unified_data/sector_ranking_rollout/prod_repository.py` | `ProdRankingWriter` + `ProdRankingReader` + `BindingState` | Gate-3/4 共用；见 §3.6/§3.7 |
| `scripts/unified_data/sector_ranking_rollout/gate3_backfill.py` | Gate-3 真实 backfill CLI（dry-run / canary / 全量，日级原子，写后读回） | SPEC §3.4；见 §3.6 |
| `scripts/unified_data/sector_ranking_rollout/gate4_activate.py` | Gate-4 读路径激活 CLI（binding 开关 + 只读 smoke） | SPEC §3.5；见 §3.7 |
| `data/rollout/sector-ranking/reference/sw_l1_reference.csv` | SW 2021 L1 一级行业 code/name 参考表（**reference-only**，供 Gate-1 双源交叉核对，不入运行时） | OQ-016-2；见 §3.4 |
| `skills/data/unified_data/tests/fixtures/rollout_fixtures.py` | Gate 工具测试 fixture：`make_sw_index_docs()`、`make_index_basic_docs()`、`make_expected_universe()`、`make_reference_csv(tmp_path)`、`make_binding(tmp_path)`、`make_gate1_report(tmp_path)` | 新增 fixture，不与 03-015 fixture 混用 |
| `skills/data/unified_data/tests/test_sector_ranking_rollout_common.py` | common.py 单测（ConnLoader 形态/脱敏/预算/退出码） | SPEC §6 |
| `skills/data/unified_data/tests/test_sector_ranking_rollout_gate1.py` | Gate-1 单测（G1-B / G1-C / G1-S 全矩阵） | SPEC §6 |
| `skills/data/unified_data/tests/test_sector_ranking_rollout_gate2.py` | Gate-2 单测（G2-D / G2-S） | SPEC §6 |
| `skills/data/unified_data/tests/test_sector_ranking_rollout_gate3.py` | Gate-3 单测（G3-B / G3-S / G3-V） | SPEC §6 |
| `skills/data/unified_data/tests/test_sector_ranking_rollout_gate4.py` | Gate-4 单测（G4-R / G4-S / G4-V） | SPEC §6 |

#### 3.1.2 修改文件

**无。** 本设计不修改任何既有文件（含 `scripts/unified_data/__init__.py` 与 `skills/data/unified_data/tests/conftest.py`）。

> 若 Implement 阶段发现必须修改既有文件（例如 `conftest.py` 需要注册新 fixture），必须按 §7.3 退回 Principal，不擅自修改。

#### 3.1.3 执行入口

工具以模块方式执行（与 repo 根目录可 import 的约定一致）：

```bash
python3 -m scripts.unified_data.sector_ranking_rollout.gate1_smoke --help
```

每个模块含 `if __name__ == "__main__": main()`；`main(argv=None) -> int` 供测试直接调用。

### 3.2 总体控制流

```text
Review PASS（本流水线 T5）
   │
   ▼
orchestrator 创建 Production activation 分阶段卡（RFC PT-016-2，逐 Gate 串行）
   │
   ▼ 每张卡（assignee 按工具职责，body 引用 RFC/SPEC/DESIGN 章节）
   ├─ Gate-1: python3 -m ...gate1_smoke --apply --yes
   │    → yquanttester 只读 Verify（G1-V-001~005）PASS → 建 Gate-2 卡
   ├─ Gate-2: python3 -m ...gate2_ddl --apply --yes
   │    → yquanttester 只读 Verify（G2-V-001~005）PASS → 建 Gate-3 卡
   ├─ Gate-3: canary → verify → Pascal 放行 → 全量 → verify（G3-V-101~105）
   │    → PASS → 建 Gate-4 卡
   └─ Gate-4: python3 -m ...gate4_activate --enable --apply --yes
        → yquanttester 只读 Verify（G4-V-101~105）PASS → rollout 完成
```

工具内部控制流（4 个 Gate 一致）：

```text
main(argv)
  ├─ argparse 解析（--apply / --yes / --report-dir / Gate 专属参数；无 --conn / 无 prefix 选择）
  ├─ [--apply 无 --yes] → 按 dry-run 处理并提示（G0-C-003）
  ├─ dry-run（默认）：打印计划（查询清单 / DDL 计划 / backfill 范围 / binding 状态）
  │      → 退出码 0，零副作用
  └─ apply：
       ├─ ConnLoader().load_db()           （失败 → 退出码 3）
       ├─ 前置校验 / 只读 verify
       ├─ 执行本 Gate 动作
       ├─ 审计证据（report + logs + 快照）
       ├─ secret 扫描（发现泄露 → 退出码 2，SC-016-G0-1）
       └─ 退出码：0 成功 / 2 停止条件命中 / 4 verify 失败
```

### 3.3 共享组件设计（common.py）

#### 3.3.1 退出码常量（对齐 SPEC G0-C-004）

| 常量 | 值 | 语义 |
|---|---|---|
| `EXIT_OK` | 0 | 成功（dry-run / apply / verify 全过） |
| `EXIT_PARAM` | 1 | 参数/前置校验失败（如 `--expected-file` 缺失、日期非法） |
| `EXIT_STOP` | 2 | 停止条件命中（G1-S / G2-S / G3-S / G4-S / SC-016-G0-1） |
| `EXIT_CONN` | 3 | 连接/凭据失败（fail-fast，不降级） |
| `EXIT_VERIFY` | 4 | verify 失败（Gate-2 前置只读 verify / 写后读回 verify / smoke 判定失败） |

#### 3.3.2 `ConnLoader`（connection closure：唯一受控连接源）

> **连接源闭合 ledger（评审 #864，全篇唯一允许形态）**
> ```text
> 连接源 = 环境中的 MONGODB_HOST / MONGODB_PORT / MONGODB_USERNAME / MONGODB_PASSWORD / MONGODB_DATABASE
> 连接形态 = 组件式构造，不允许 URI
> CLI = 不再暴露 --conn 或 prefix 选择
> 无 alias / 无 fallback / 无其他环境变量形态
> 缺失任一必需键 = fail-fast EXIT_CONN(3)，仅记录键名
> 日志/report 不得回显连接值；fingerprint 不包含 username 的可逆/可识别信息
> ```
> 旧方案（禁止，历史说明）：`{PREFIX}_URI` 优先 + 任意 prefix + URI/组件双形态与 RFC CR-016-1/2 唯一受控连接源冲突，已清除；不得实现。

```python
class ConnLoader:
    def __init__(self, *, client_factory: Callable[..., Any] | None = None) -> None: ...
    def load_client(self) -> Any:      # pymongo.MongoClient（组件式构造；测试注入 mongomock）
    def load_db(self) -> Any:          # client.get_database(MONGODB_DATABASE)
    def fingerprint(self) -> dict:     # {"source": "MONGODB_*", "keys_present": [...], "auth_configured": bool}
    def describe_missing(self) -> list[str]:  # 缺失键名列表（不含值）
```

规则（T3 实现必须遵守）：

| 编号 | 规则 |
|---|---|
| CL-1 | 连接源 = 环境中的 `MONGODB_HOST` / `MONGODB_PORT` / `MONGODB_USERNAME` / `MONGODB_PASSWORD` / `MONGODB_DATABASE` 五键（RFC CR-016-1 唯一受控连接源）。组件式构造：`pymongo.MongoClient(host=..., port=int(...), username=..., password=..., authSource=MONGODB_DATABASE)`；**不允许 URI**（无 `{PREFIX}_URI`、无 `mongodb://` 串）、不允许任意 prefix（CLI 无 `--conn`/prefix 参数） |
| CL-2 | 数据库名 = `MONGODB_DATABASE`；`authSource` = `MONGODB_DATABASE`（固定值，不引入 `AUTH_SOURCE` 键） |
| CL-3 | 缺失任一必需键（5 键全必需，`MONGODB_PORT` 无默认值）→ fail-fast 退出码 3（SC-016-G0-2），仅打印缺失键名（`describe_missing()` 返回键名列表，不含值） |
| CL-4 | Client 选项：`serverSelectionTimeoutMS=10000`、`connectTimeoutMS=10000`（G0-C-006 ≤10s） |
| CL-5 | 测试替身：构造参数 `client_factory` 显式注入 mongomock 的 `MongoClient`（或等价注入）；测试**不得读取环境**（零真实 I/O） |
| CL-6 | 任何位置不得打印连接值（host/port/username/password/db 值）；`fingerprint()` 只含结构字段（source 标签 + keys_present + auth_configured），**不含 username 的任何可逆/可识别信息**（G1-R-002 / G1-C-007） |

#### 3.3.3 `BudgetReader`（Gate-1 / Gate-3 查询强制层）

```python
class BudgetReader:
    def __init__(self, db: Any, *, max_find=1000, max_time_ms=30000,
                 server_selection_timeout_ms=10000) -> None: ...
    def count(self, collection: str, filter: dict) -> int
    def distinct(self, collection: str, key: str, filter: dict) -> list
    def find(self, collection: str, filter: dict, *, limit: int = 1000,
             projection: dict | None = None) -> list[dict]
    def aggregate(self, collection: str, pipeline: list[dict]) -> list[dict]
    def stats(self) -> list[dict]      # 每类查询：次数/条数/耗时（G1-B-007）
```

强制规则（SPEC G1-B-001~007 逐条落到代码）：

| SPEC | 实现 |
|---|---|
| G1-B-001 查询类型白名单 | 只暴露 `count` / `distinct` / `find` / `aggregate`；其余 pymongo 方法不封装 |
| G1-B-002 过滤强制 | `find` 的 filter 与 `aggregate` pipeline 第一个 stage（必须为 `$match`）必须含白名单字段 {`sector_code`, `trade_date` 范围, `market`} 至少一个；空 filter / 空 pipeline / 首 stage 非 `$match` / 白名单外字段（如 `{"foo": 1}`）→ 抛 `BudgetViolation`（G1-S-007 → 退出码 2）。`find` 与 `aggregate` 首 stage 使用**同一校验规则**（F3 闭合，SPEC G1-B-002 逐字一致） |
| G1-B-003 结果条数上限 | `find` 默认 `limit<=1000`；调用方显式传入 `limit>1000` 抛 `BudgetViolation` |
| G1-B-004 超时上限 | 每次查询带 `max_time_ms`（默认 30000）与 `server_selection_timeout_ms`（默认 10000） |
| G1-B-005 扫描保护 | 空 filter / 空 pipeline 静态拒绝（G1-S-007 → 退出码 2） |
| G1-B-006 记录范围上限 | Gate-1 累计命中 > 100000 → `BudgetViolation`（提示缩小范围） |
| G1-B-007 预算审计 | `stats()` 计入 report 的 `query_budget` 字段 |

`BudgetViolation` 在 Gate-1/3 的 main 中捕获并映射为退出码 2。

#### 3.3.4 `ReportWriter` + 日志 + 脱敏

```python
REPORT_DIR_DEFAULT = "data/rollout/sector-ranking"

def resolve_report_dir(report_dir: str | None) -> str: ...   # mkdir -p（G0-C-007）

def write_report(report_dir: str, gate: str, payload: dict) -> None:
    # 写 gate{N}-report.json（规范路径，最新证据）+ gate{N}-report-<UTC ISO 文件名安全>.json（归档副本，不覆盖历史，G0-C-010）
    # 写 gate{N}-report.md（人读摘要）

def log_jsonl(report_dir: str, gate: str, record: dict) -> None:
    # 追加到 data/rollout/sector-ranking/logs/gate{N}-<YYYYMMDD>.log（G0-C-008）

def redact(text: str) -> str:
    # 掩码：连接值（MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE 的值）与 *TOKEN*/*SECRET* 已知值；
    # 防御性检测 mongodb(+srv):// 含凭据段（连接不再构造 URI，仅作泄露兜底扫描，SC-016-G0-1）

def scan_secrets(text: str) -> list[str]:
    # 返回命中的泄露类别列表（uri_with_credentials / password_value / token_value / secret_value）；
    # 非空 → SC-016-G0-1 → 退出码 2
```

时间戳：所有 report/log 记录 `timestamp`（UTC ISO-8601，`datetime.now(timezone.utc).isoformat()`，G0-C-010）。

幂等（G0-C-009）：工具重复执行不得改变已有状态；同参数重跑结果一致。Gate-2 幂等靠「先查存在性、规格一致跳过」；Gate-3 幂等靠唯一键 upsert 覆盖；Gate-4 幂等靠 binding 状态文件重写。

#### 3.3.5 `TradeCalendar` / `CompletedSessionPolicy`（交易日状态检查，F2 闭合）

> 冻结 `HistoricalSectorService._validate_trade_date` 仅做 `is_valid_trade_date` 格式校验（historical_sector_service.py:282-286），**不**判定交易日/收盘状态；「未来日 / 当日未收盘」的 ValueError 契约由本组件执行，**不是**修改冻结 service（SPEC §3.5.7 G4-P-001~010 落地）。

```python
class SessionStatus(Enum):
    FUTURE = "future"                     # trade_date > 今日
    TODAY_UNCLOSED = "today_unclosed"     # 今日为交易日且 now < 收盘 cutoff
    TODAY_CLOSED = "today_closed"         # 今日为交易日且 now >= cutoff，或今日非交易日
    PAST_TRADING_DAY = "past_trading_day"
    PAST_NON_TRADING_DAY = "past_non_trading_day"

class TradeCalendar(ABC):
    @abstractmethod
    def is_trading_day(self, date: date) -> bool: ...

class FakeTradeCalendar(TradeCalendar):
    # 测试注入：显式交易日集合；零真实 I/O（CL-5 同纪律）
    def __init__(self, trading_days: set[str]) -> None: ...

class CompletedSessionPolicy:
    CLOSE_CUTOFF = time(15, 0)            # Asia/Shanghai 15:00 CST（15:00 整视为已收盘，G4-P-003）
    TZ = ZoneInfo("Asia/Shanghai")
    def __init__(self, calendar: TradeCalendar, *, now_fn: Callable[[], datetime] | None = None) -> None:
        # now_fn 生产 = lambda: datetime.now(timezone.utc)；测试注入 fake clock
    def classify(self, trade_date: str, now: datetime | None = None) -> SessionStatus:
        # 唯一输入/输出（SPEC G4-P-001/002）；FUTURE / TODAY_UNCLOSED 抛 ValueError（G4-P-004/005）
```

- **唯一输入**：`(trade_date, now)`；**唯一输出**：`SessionStatus`（SPEC G4-P-001/002）。
- **时区/收盘 cutoff**：`Asia/Shanghai`；`CLOSE_CUTOFF = 15:00 CST`（G4-P-003）。
- **错误类型**：`FUTURE` → `ValueError("ERR_FUTURE_DATE ...")`；`TODAY_UNCLOSED` → `ValueError("ERR_TODAY_UNCLOSED ...")`（消息含类别与日期，不含连接值，G4-P-004/005）。
- **fail-closed**：`calendar=None`（生产未配置受控日历证据）→ `CompletedSessionPolicy` 不可用 → 读路径拒绝（SPEC G4-P-008/009，不猜测）。
- **注入点**：`ProdRankingReader.__init__(db, *, binding, policy)`（§3.7.2）；冻结 service 零修改。

**fake calendar + fake clock 逐项证伪（G4-R-003 / G4-V-004，对应 SPEC G4-P-004~007）**：

| SPEC 规则 | fake 注入 | 断言 |
|---|---|---|
| G4-P-004 未来日 | fake clock = 2026-08-01T00:00:00Z；trade_date=2026-08-02 | classify → `FUTURE` → ValueError；反例：fake clock=2026-08-03T00:00:00Z → 同一日期变历史 → 不抛错 |
| G4-P-005 当日未收盘 | FakeTradeCalendar 含 2026-08-01（交易日）；fake clock=2026-08-01T04:00:00Z（=12:00 CST） | classify → `TODAY_UNCLOSED` → ValueError（G4-V-004 正例） |
| G4-P-006 当日已收盘 | 同上；fake clock=2026-08-01T07:30:00Z（=15:30 CST） | classify → `TODAY_CLOSED` → 不抛错（G4-V-004 反例 1） |
| G4-P-007 非交易日 | FakeTradeCalendar 不含 2026-08-02（非交易日）；clock=2026-08-03 | classify(2026-08-02) → `PAST_NON_TRADING_DAY` → 不抛错；读路径 empty token（G4-V-004 反例 2） |

### 3.4 Gate-1 详细设计（gate1_smoke.py）

#### 3.4.1 CLI（对齐 SPEC §3.2.1）

```text
python3 -m scripts.unified_data.sector_ranking_rollout.gate1_smoke \
  [--apply] [--yes] \
  [--min-trade-date YYYY-MM-DD] [--max-trade-date YYYY-MM-DD] \
  [--report-dir data/rollout/sector-ranking]
```

#### 3.4.2 apply 流程（函数级）

```text
main()
  ├─ build_parser() → args
  ├─ resolve_report_dir(args.report_dir)
  ├─ dry-run：print 查询计划（BudgetReader 将发起的查询清单、预算上限、report 路径）→ return 0
  └─ apply：
      ├─ conn = ConnLoader(); db = conn.load_db()                   # 失败 → 3
      ├─ baseline_counts(db)                                          # G1-C-007 / G1-V-005 只读基线
      │     index_daily_quotes.estimatedDocumentCount + index_basic_info.estimatedDocumentCount
      ├─ sw_universe = enumerate_sw_l1(db)                            # G1-C-001 / G1-C-006
      │     BudgetReader.find("index_basic_info", {"market": "CN"})
      │       候选 code 提取顺序：doc.sector_code → doc.code → doc.symbol
      │       过滤前缀 "^801"；重复/非法 → G1-S-003 停止；空 → G1-S-002 停止
      │       type/classify 字段含 concept/region/style → G1-C-006 FAIL（混入 → 停止）
      ├─ cross_check_reference(sw_universe)                           # G1-C-001 双源（OQ-016-2）
      │     reference 文件缺失 → G1-C-001 FAIL（reference_missing）→ 停止并上报
      │     差异（DB 有 reference 无 / reference 有 DB 无 / name 不一致）→ 记入 report.discrepancies
      │     差异影响 canary 候选 → G1-S-005 停止
      ├─ date_range, coverage = compute_coverage(db, sw_universe)    # G1-C-003
      │     distinct("trade_date", {"sector_code": {"$in": codes}}) → min/max + 逐日
      │     coverage_by_date[trade_date] = {expected, observed, ratio}
      │     trade_date_format = 抽样首个 trade_date 的形态（"YYYYMMDD" / "YYYY-MM-DD"）→ 记入 report
      ├─ close_completeness = check_close_completeness(db, universe) # G1-C-004
      │     aggregate: $match {sector_code in codes} + $group by trade_date 统计 close 缺失/非法行
      ├─ source_dist = check_source_distribution(db, universe)       # G1-C-005
      │     aggregate: $match {sector_code in codes} + $group by source
      │     rt 标记（source in {"realtime","intraday","rt"}）→ G1-S-006 停止
      ├─ canary_candidates = select_candidates(coverage, close_completeness, source_dist)
      │     规则（OQ-016-3）：coverage==100% 且 close 完整 且 无 rt 标记 且 非今日（今日判定经 CompletedSessionPolicy 的 now 时钟，§3.3.5）；
      │     recommended = max(trade_date)（最近日最接近当前 schema/source 状态）
      ├─ report = build_report(...)   # G1-R-001~010 + trade_date_format + discrepancies + query_budget
      ├─ write_report(...); write .md
      ├─ scan_secrets(report 全文) → 命中 → SC-016-G0-1 → 2
      └─ return 0 / 2 / 3
```

#### 3.4.3 权威 expected universe 语义（OQ-016-2 解决）

- **主来源**：`tradingagents.index_basic_info`（`market="CN"` + SW L1 code 前缀 `801`）——Gate-1 report 的 `expected_sector_codes` / `expected_sector_names` **只来自主来源**。
- **双源交叉核对**：`data/rollout/sector-ranking/reference/sw_l1_reference.csv`（T3 创建，表头 `sector_code,sector_name,note`，note 记录公开来源 URL 与核对日期，文件头注释标注 `REFERENCE-ONLY`）。差异仅记入 `report.discrepancies`，**不参与** expected universe 构造。
- **reference 缺失**：`enumerate_sw_l1` 正常（主来源可用），但 `cross_check_reference` 报 `reference_missing` → G1-C-001 判定为 FAIL → 停止；Pascal 补 reference 或人工对照申万官网后放行。
- 该文件**不是**运行时 universe 来源，不违反「不得硬编码 universe」（03-015 H-049u 约束的是 expected 注入路径，Gate-3 的 `--expected-file` 仍强制来自 Gate-1 report）。

#### 3.4.4 Report 结构（G1-R-001~010 具体化）

`gate1-report.json`：

> **G1-R-002 落实说明**：`conn_prefix` 是 **SPEC V0.1 的旧字段名**，已被 SPEC V0.2（评审 #865）替换为 `conn_source`（固定标签 `"MONGODB_*"`）+ `conn_fingerprint`（结构字段，无任何连接值）——本 Design 与 SPEC V0.2 逐字一致，**不是**把 SPEC 当前字段改名。因连接源收敛为唯一受控 `MONGODB_*` 组件来源，不再存在 prefix 选择，`conn_prefix` 作为旧概念移除；report 仍满足「记录使用的连接源、不含值」语义（OBS-1 闭合）。

```json
{
  "tool": "gate1_smoke",
  "version": "0.1.0",
  "timestamp": "2026-08-01T02:00:00Z",
  "conn_source": "MONGODB_*",
  "conn_fingerprint": {"source": "MONGODB_*",
                        "keys_present": ["MONGODB_HOST", "MONGODB_PORT", "MONGODB_USERNAME",
                                          "MONGODB_PASSWORD", "MONGODB_DATABASE"],
                        "auth_configured": true},
  "query_budget": [{"kind": "find", "count": 3, "rows": 512, "ms": 1240}],
  "trade_date_format": "YYYYMMDD",
  "expected_sector_codes": ["801010", "801020", "..."],
  "expected_sector_names": {"801010": "农林牧渔", "..."},
  "trade_date_range": {"min": "2010-01-04", "max": "2026-07-30"},
  "coverage_by_date": {"2010-01-04": {"expected": 31, "observed": 31, "ratio": 1.0}},
  "close_missing_by_date": {"2010-01-04": []},
  "source_distribution": {"sw": 90000, "ta_cn": 120},
  "realtime_markers": [],
  "discrepancies": [{"kind": "name_mismatch", "code": "801xxx", "db_name": "...", "ref_name": "..."}],
  "canary_candidates": ["2026-07-29", "..."],
  "recommended_canary": "2026-07-29",
  "checks": {"G1-C-001": "PASS", "G1-C-002": "PASS", "...": "..."},
  "stop_conditions_hit": []
}
```

#### 3.4.5 停止条件映射（G1-S-001~008 → 代码路径）

| SC | 触发点 | 退出码 |
|---|---|---|
| G1-S-001 | `ConnLoader.load_db()` 抛连接/认证异常 | 3 |
| G1-S-002 | `enumerate_sw_l1` 返回空 | 2 |
| G1-S-003 | 候选 code 重复 / 非 `^801` 前缀 / 非法格式 | 2 |
| G1-S-004 | report 无法固化 expected（内部错误） | 2 |
| G1-S-005 | canary 候选为空 或 候选日 coverage<100% / close 缺失 / reference 差异影响候选 | 2 |
| G1-S-006 | `source_dist` 出现 rt 标记 | 2 |
| G1-S-007 | `BudgetViolation`（无过滤扫描 / 超限） | 2 |
| G1-S-008 | `scan_secrets` 命中 | 2 |

### 3.5 Gate-2 详细设计（gate2_ddl.py）

#### 3.5.1 CLI（对齐 SPEC §3.3.1）

```text
python3 -m scripts.unified_data.sector_ranking_rollout.gate2_ddl \
  [--apply] [--yes] \
  [--collection 03_data_ud_sector_ranking_daily] \
  [--report-dir data/rollout/sector-ranking]
```

#### 3.5.2 DDL 常量（对齐 G2-D-001~006）

```python
ALLOWED_COLLECTION = "03_data_ud_sector_ranking_daily"
INDEX_NAME = "uniq_dataset_date_sector"
INDEX_KEY = [("dataset", 1), ("trade_date", -1), ("sector_code", 1)]  # G2-D-002
INDEX_OPTS = {"unique": True, "name": INDEX_NAME, "background": False}
```

#### 3.5.3 apply 流程

```text
main()
  ├─ dry-run：print DDL 计划（createCollection? / createIndex? 基于只读探测）→ 0
  └─ apply：
      ├─ conn/db 加载（失败 → 3）
      ├─ pre_verify（G2-D-006 / G2-S-002）：
      │     db.list_collection_names() 快照（G2-A-003 前置）
      │     目标集合是否存在；存在则 getIndexes 比对规格
      │     规格不一致 → G2-S-003 停止（退出码 2）
      │     db 不可达 → G2-S-002（退出码 4）
      ├─ execute：
      │     集合不存在 → db.create_collection(ALLOWED_COLLECTION)      # G2-D-001
      │     索引不存在 → coll.create_index(INDEX_KEY, **INDEX_OPTS)    # G2-D-002
      │     已存在且一致 → 跳过并报告（幂等）
      ├─ post_verify：
      │     getIndexes 快照比对（key/unique/name）→ 不符 → 退出码 4
      │     list_collection_names() 前后比对：只允许新增 ALLOWED_COLLECTION（G2-A-004）
      ├─ 审计证据：dry-run 日志（G2-A-001）+ apply 日志（G2-A-002）
      │     + 只读 verify 快照（G2-A-003）+ 越权扫描结果（G2-A-004）
      ├─ write_report(...) + scan_secrets → 命中 → 2
      └─ return 0 / 2 / 3 / 4
```

#### 3.5.4 停止条件映射（G2-S-001~006）

| SC | 触发点 | 退出码 |
|---|---|---|
| G2-S-001 | 连接/认证失败 | 3 |
| G2-S-002 | 前置 verify 失败（db 不可达 / 状态异常） | 4 |
| G2-S-003 | 索引已存在但规格不一致（不 drop 重建、不覆盖） | 2 |
| G2-S-004 | 尝试操作白名单外集合（代码层断言 `_assert_namespace`） | 2 |
| G2-S-005 | post_verify 发现目标集合外新建集合/索引 | 2 |
| G2-S-006 | `scan_secrets` 命中 | 2 |

### 3.6 Gate-3 详细设计（gate3_backfill.py + prod_repository.ProdRankingWriter）

#### 3.6.1 `ProdRankingWriter`（prod_repository.py）

```python
class ProdRankingWriter:
    """真实 pymongo 生产写入器（仅限 03_data_ud_sector_ranking_daily）。

    与 HistoricalRankingWriter 平行但允许真实 db；每个操作先过
    _assert_namespace（拒绝目标集合外的一切读写）。
    """
    COLLECTION = "03_data_ud_sector_ranking_daily"
    UNIQUE_KEY = frozenset({"dataset", "trade_date", "sector_code"})

    def __init__(self, db: Any) -> None:
        # db 为真实 pymongo Database（或测试 mongomock）；不接受 None
        ...

    def get(self, collection: str | None = None, filter: Mapping | None = None) -> list[dict]
        # 与 HistoricalRankingWriter.get 同形态；仅允许 COLLECTION
    def upsert(self, records, unique_key=None) -> UpsertOutcome
        # 按唯一键 update_one(upsert=True)；返回 p3_persistence_writer.UpsertOutcome
    def count(self, filter: Mapping) -> int
        # 写后读回行数统计
    def estimated_document_count(self) -> int
        # 越权扫描：目标集合行数快照
```

约束：
- 构造、`get`、`upsert`、`count` 全部先 `_assert_namespace(collection)`——collection 非 `COLLECTION` → 抛 `NamespaceViolation`（→ G3-S-009 退出码 2）。
- upsert 单条失败捕获进 `UpsertOutcome`（与 03-015 语义一致），调用方检查 `outcome.failed == 0`（G3-S-006）。

#### 3.6.2 CLI（对齐 SPEC §3.4.1）

```text
python3 -m scripts.unified_data.sector_ranking_rollout.gate3_backfill \
  --expected-file <gate1-report.json 路径> \
  [--range-file PATH] \
  [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] \
  [--canary-date YYYY-MM-DD] [--apply] [--yes] \
  [--report-dir data/rollout/sector-ranking]
```

#### 3.6.3 范围解析（OQ-016-4 解决；F1 冻结）

| 模式 | 规则 |
|---|---|
| `--canary-date`（无 `--range-file` / 无 `--start-date`/`--end-date`） | 只处理 1 日；`--canary-date` 必须在 `gate1-report.json.canary_candidates` 中，否则退出码 1（G3-S-003）。**canary 单日模式仅在无任何全量范围来源（无 `--range-file`、无 `--start-date`、无 `--end-date`）时合法** |
| `--canary-date` 与任何全量范围来源互斥 | `--canary-date` + `--range-file` → 退出码 1；`--canary-date` + 成对 `--start-date`/`--end-date` → 退出码 1；`--canary-date` + 不成对 start/end 仍按缺配对 → 退出码 1（均 G3-S-003） |
| `--range-file PATH`（全量，推荐） | 值 = Gate-1 report JSON 路径（与 `--expected-file` 相同的 `gate1-report.json`）；范围 = `coverage_by_date` 键集（已确认可用交易日），升序去重（G3-B-013/014）；**默认排除最早可用日**（首日无前一日 close → 必然 empty 失败，避免「自动失败」，G3-B-016）；dry-run 计划显式说明排除的首日与理由 |
| 显式 `--start-date` / `--end-date` | 必须成对（缺一 → 退出码 1）；start ≤ end；两者均 ∈ Gate-1 `trade_date_range`；均经 CompletedSessionPolicy 判定非未来日、非「今日且未收盘」（§3.3.5 / G4-P-004/005）→ 否则退出码 1（G3-S-003） |
| `--range-file` 与 `--start-date`/`--end-date` 互斥 | 同时传入 → 退出码 1（G3-S-003 / G3-B-015） |
| 无任何范围来源 | 退出码 1（G3-S-003）；§8.3 全量命令必须显式传 `--range-file` |

#### 3.6.4 日级处理流程（核心）

```text
process_day(trade_date: str) -> DayOutcome
  ├─ prev_date = ordered_available_dates[day_index - 1]      # 来自 Gate-1 coverage_by_date keys（升序）
  │     day_index == 0 → DayOutcome(status="empty", reason="no-prev-close")
  ├─ docs = BudgetReader.find("index_daily_quotes",
  │        {"sector_code": {"$in": expected_codes},
  │         "trade_date": {"$in": [to_internal(day), to_internal(prev_date)]}})
  ├─ 按 sector_code 组织：day 行（close 必须有限数值） + prev 行（close 作为 pre_close）
  │     缺 day 行 / close 非法 → 该 code 缺失（G3-B-010）
  │     缺 prev 行 → 该 code 不入库（G3-B-004 / H-047~H-048）→ 影响完整性
  │     rt 标记（source ∈ {"realtime","intraday","rt"}）→ 该 code 不入库（G3-B-009 / RT-4；G3-S-010）
  ├─ candidates = [{"sector_code","sector_name","close","pre_close",...} for 每个有效 code]
  ├─ outcome = build_ranking_rows(candidates, expected_codes, "sw2021_ta_cn", day)   # G3-B-005：复用 03-015 冻结纯函数（pct_chg 固定公式、100% exact-match、稳定排序、连续 rank）
  │     outcome.status == "incomplete" → G3-S-004（退出码 2，停止后续日）
  │     outcome.status == "empty"      → G3-S-005（退出码 2，停止后续日）
  ├─ upsert_outcome = writer.upsert([asdict(row) for row in outcome.rows])
  │     upsert_outcome.failed > 0 → G3-S-006（退出码 2，停止后续日）
  ├─ read_back_verify(writer, day)                           # G3-V-001~004
  │     行数 == len(expected)；逐行 SectorRankingDaily.from_dict 校验 9 字段；
  │     排序 pct_chg DESC → sector_code ASC；唯一键无重复
  │     任一不符 → G3-S-007（退出码 2，停止后续日）
  └─ DayOutcome(status="complete", upserted=len(rows), ms=...)
```

字段来源（对齐 SPEC §4.bis）：

| 字段 | 来源 |
|---|---|
| `dataset` | 常量 `"sw2021_ta_cn"`（G3-B-006，不从 TA-CN 推断） |
| `trade_date` | `to_internal()` 反转换：TA-CN `YYYYMMDD` → 输出 `YYYY-MM-DD`（G3-B-007 / H-053）；格式由 Gate-1 `trade_date_format` 决定 |
| `sector_code` / `sector_name` | Gate-1 `expected_sector_codes` / `expected_sector_names`（G3-B-011；缺失 → 行不入库） |
| `pct_chg` | `build_ranking_rows` 固定公式 `(close - pre_close) / pre_close * 100`（G3-B-008 / H-032；禁止使用上游自带 pct_chg） |
| `rank` | `build_ranking_rows` 连续 1-based，tiebreaker sector_code ASC |
| `close` / `pre_close` | TA-CN 文档；`pre_close` 为前一交易日 close（G3-B-004） |
| `updated_at` | `_now_iso()`（UTC ISO-8601），upsert 覆盖时刷新（H-020） |

#### 3.6.5 写后读回（G3-V-001~004 实现）

```python
def read_back_verify(writer, trade_date: str, expected: list[str]) -> None:
    rows = writer.get(filter={"dataset": "sw2021_ta_cn", "trade_date": trade_date})
    assert len(rows) == len(expected)                       # G3-V-001
    for doc in rows:
        SectorRankingDaily.from_dict(doc)                    # G3-V-002（9 字段 + 类型）
    sorted_rows = sorted(rows, key=lambda r: (-r["pct_chg"], r["sector_code"]))
    assert [r["sector_code"] for r in rows] == [r["sector_code"] for r in sorted_rows]  # G3-V-003
    assert len({(r["dataset"], r["trade_date"], r["sector_code"]) for r in rows}) == len(rows)  # G3-V-004
```

#### 3.6.6 Report 结构

`gate3-report.json`：`{tool, version, timestamp, conn_source, conn_fingerprint, range: {start, end, excluded_first}, canary: {date, outcome, read_back}, days: [{trade_date, status, expected, observed, upserted, failed, ms}], summary: {success_days, failed_days, stop_conditions_hit}, expected_sector_codes, expected_sector_names, checks, query_budget}`（G3-A-001~005）。

#### 3.6.7 停止条件映射（G3-S-001~012）

| SC | 触发点 | 退出码 |
|---|---|---|
| G3-S-001 | 连接/认证失败 | 3 |
| G3-S-002 | `--expected-file` 缺失 / JSON schema 不完整（缺 `expected_sector_codes` / `expected_sector_names`） | 1 |
| G3-S-003 | 范围非法（无任何范围来源；`--range-file` 与 `--start-date`/`--end-date` 互斥冲突；start 缺 end（或反之）；`--canary-date` 与任何全量范围来源同时传入〔`--range-file`，或成对 `--start-date`/`--end-date`；与不成对 start/end 仍按缺配对〕；start>end；超 Gate-1 范围；未来日 / 今日未收盘〔CompletedSessionPolicy，§3.3.5〕；canary 不在候选清单） | 1 |
| G3-S-004 | 目标日 `observed != expected`（incomplete） | 2 |
| G3-S-005 | 目标日零有效行（empty） | 2 |
| G3-S-006 | upsert `outcome.failed > 0` | 2 |
| G3-S-007 | 写后读回不一致（行数/字段/排序/唯一键） | 2 |
| G3-S-008 | canary 任一 G3-S-004~007 命中 | 2 |
| G3-S-009 | `NamespaceViolation`（尝试写目标集合外） | 2 |
| G3-S-010 | 检测 rt 标记混入 | 2 |
| G3-S-011 | `scan_secrets` 命中 | 2 |
| G3-S-012 | 任意未知异常（report 记录脱敏异常栈） | 2 |

失败后**不自动** retry / 扩范围 / rollback / drop（RFC §5.4 / G3 禁止自动动作段）；修复后由 Pascal 显式重跑对应日（幂等 upsert 覆盖）。

### 3.7 Gate-4 详细设计（gate4_activate.py + prod_repository.ProdRankingReader + BindingState）

#### 3.7.1 `BindingState`

```python
BINDING_FILE = "binding_state.json"   # 位于 report-dir 下

def load_binding(report_dir: str) -> dict:     # 缺失 → {"enabled": False}
def write_binding(report_dir: str, enabled: bool) -> dict:
    # {"capability": "sector.ranking_history", "enabled": bool, "gate": 4,
    #  "updated_at": ISO, "previous": <旧值>}
```

- Gate-4 **默认 `--disable`**（安全默认，SPEC §3.5.1）；`--enable` + `--apply` + `--yes` 才写 `enabled=true`。
- 回滚 = `--disable` + `--apply` + `--yes`（G4-R-006），**不删除数据**。

#### 3.7.2 `ProdRankingReader`

```python
class ProdRankingReader:
    """生产只读路径：与 HistoricalRankingWriter.get() 同形态，可注入冻结的
    HistoricalSectorService。fail-closed：binding 未启用时拒绝读；交易日状态
    检查经注入的 CompletedSessionPolicy（F2 闭合，§3.3.5）。"""

    def __init__(self, db: Any, *, binding: Callable[[], bool],
                 policy: CompletedSessionPolicy | None = None) -> None:
        # binding 默认 lambda: load_binding(report_dir)["enabled"]；测试注入 lambda
        # policy 必填（生产 = 受控日历证据构造；测试 = FakeTradeCalendar + fake clock）；
        # None → fail-closed：拒绝读（不猜测交易日状态，G4-P-008/009）
        ...

    def get(self, collection: str | None = None, filter: Mapping | None = None) -> list[dict]:
        if not self._binding():
            raise BindingDisabledError("sector.ranking_history production read binding is disabled")
        if self._policy is None:
            raise PolicyUnavailableError("trade-calendar evidence unavailable; fail-closed")
        self._assert_namespace(collection)
        # 1) 交易日状态检查：filter["trade_date"] 经 policy.classify →
        #    FUTURE / TODAY_UNCLOSED 抛 ValueError（G4-P-004/005，Category 1 语义）
        # 2) 与 HistoricalRankingWriter.get 同查询语义（find + list[dict]）
```

注入方式（**零修改**冻结 service）：

```python
policy = CompletedSessionPolicy(
    calendar=live_calendar,          # 生产：受控 live calendar evidence（§8.4）；测试：FakeTradeCalendar
    now_fn=lambda: datetime.now(timezone.utc),   # 测试注入 fake clock
)
service = HistoricalSectorService(
    writer=ProdRankingReader(db, binding=lambda: load_binding(report_dir)["enabled"], policy=policy),
    expected_universe_by_dataset={"sw2021_ta_cn": report["expected_sector_codes"]},
)
result = service.get_sector_ranking_history(trade_date, dataset, limit)
```

冻结读契约（参数校验、Category 1~4 token、排序、limit、source_trace）全部由 service 提供；`ProdRankingReader` 只负责「生产集合读取 + binding 门禁」。契约对齐：

| SPEC | 设计落实 |
|---|---|
| G4-R-001 直读物化集合 | `ProdRankingReader.get(collection=COLLECTION, filter={dataset, trade_date})` 直读，不经 router |
| G4-R-002 冻结 token 行为 | 复用冻结 service：未物化 → `historical-ranking-empty`；完整性失败 → `historical-ranking-incomplete`；成功 → `warnings=[]` |
| G4-R-003 交易日状态检查 | `ProdRankingReader` 内注入的 `CompletedSessionPolicy`（§3.3.5）：未来日 → ValueError（G4-P-004）；当日未收盘 → ValueError（G4-P-005）；当日已收盘/历史交易日/非交易日 → 不抛错（G4-P-006/007）；冻结 service 只做 `is_valid_trade_date` 格式校验，**零修改** |
| G4-R-004 不改 router/fallback/provider | Gate-4 零代码改动；scope diff 断言（G4-S-003） |

#### 3.7.3 CLI（对齐 SPEC §3.5.1）

```text
python3 -m scripts.unified_data.sector_ranking_rollout.gate4_activate \
  --expected-file <gate1-report.json 路径> \
  [--enable|--disable] [--apply] [--yes] \
  [--smoke-dates YYYY-MM-DD[,YYYY-MM-DD]] \
  [--report-dir data/rollout/sector-ranking]
```

#### 3.7.4 apply 流程

```text
main()
  ├─ dry-run：print 当前 binding 状态、smoke 日期清单与预期结果 → 0
  └─ apply：
      ├─ conn/db 加载；--expected-file 校验（缺 → 1）
      ├─ smoke_dates = args.smoke_dates 或默认集：
      │     最近 canary 日（complete 案例）+ 最早可用日（未物化 empty 案例）
      │     + "2026-13-45"（非法格式 ValueError 案例，G4-V-003，冻结 service 格式校验）
      │     + 今日（G4-V-004 Category 1）：policy 以 live clock 分类今日并对照
      │       受控 live calendar evidence（§3.3.5/§8.4）——TODAY_UNCLOSED → 断言 ValueError；
      │       TODAY_CLOSED/非交易日 → 记录 evidence 与分类（离线 T3 已确定性覆盖正例）；
      │       policy 不可用 → fail-closed 不激活（G4-P-008/009）
      ├─ 若 --enable：
      │     a) pre-smoke：以 bypass-binding 的 reader（binding=lambda: True）
      │          跑全部 smoke 用例（G4-V-001~008）           # 先证数据与契约正确
      │          任一失败 → G4-S-002 → 退出码 2（binding 保持 disabled）
      │     b) write_binding(enabled=True)
      │     c) post-smoke：以绑定 reader 重跑 1 个成功案例
      │          （证明 binding 门禁放行真实读；G4-S-005 数据与 Gate-3 快照一致）
      ├─ 若 --disable：
      │     a) write_binding(enabled=False)
      │     b) 以绑定 reader 跑 1 个用例 → 期望 BindingDisabledError（G4-V-104 回滚预案）
      ├─ 越权扫描（path-scoped baseline manifest，OBS-2 闭合）：
      │     基线清单 = §3.1.1 T3 allowlist（14 文件）+ data/rollout/sector-ranking/**
      │     仅对基线清单内路径执行 `git status --porcelain -- <allowlist 路径>` 比对；
      │     基线清单内出现修改/删除/新增外状态 → G4-S-003 / G4-S-004 → 退出码 2
      │     共享树既有 03-015 dirty（client.py / models/domain/__init__.py / providers/akshare.py
      │       / 其他未提交）在基线清单外 → 记入 report.scope_diff，不触发停止
      │     不 reset / 不 stash / 不 clean / 不修改共享树
      ├─ 只读证明：目标集合 estimated_document_count 前后一致（G4-A-004）
      ├─ report + logs + scan_secrets
      └─ return 0 / 2 / 3 / 4
```

#### 3.7.5 Report 结构

`gate4-report.json`：`{tool, version, timestamp, conn_source, conn_fingerprint, binding: {before, after}, smoke_dates, cases: [{id: "G4-V-001", input, expected, actual, passed}], token_verbatim: bool, readonly_proof: {...}, scope_diff: [...], stop_conditions_hit}`（G4-A-001~005）。

#### 3.7.6 停止条件映射（G4-S-001~008）

| SC | 触发点 | 退出码 |
|---|---|---|
| G4-S-001 | 连接/认证失败 | 3 |
| G4-S-002 | pre-smoke 任一用例失败（`--enable` 不生效） | 2 |
| G4-S-003 | 检测到 router/fallback/provider 代码变更（scope diff） | 2 |
| G4-S-004 | 检测到 consumer/service 代码变更（scope diff） | 2 |
| G4-S-005 | 读回数据与 Gate-3 快照不一致（post-smoke 行数/字段比对） | 2 |
| G4-S-006 | `scan_secrets` 命中 | 2 |
| G4-S-007 | 未物化/不完整时返回了部分榜单（冻结 token 行为被破坏） | 2 |
| G4-S-008 | 任意未知异常 | 2 |

### 3.8 数据流/控制流图（汇总）

```text
Gate-1（只读）:  index_basic_info/index_daily_quotes(RO)
   → BudgetReader → report(gate1-report.json) → [Verify G1-V]
Gate-2（DDL）:    tradingagents.03_data_ud_sector_ranking_daily
   → createCollection + createIndex(uniq) → verify 快照 → [Verify G2-V]
Gate-3（写）:     index_daily_quotes(RO) --build_ranking_rows--> ProdRankingWriter
   → 03_data_ud_sector_ranking_daily(upsert) → 写后读回 → report → [Verify G3-V]
Gate-4（读）:     03_data_ud_sector_ranking_daily(RO)
   → ProdRankingReader(binding) → HistoricalSectorService(冻结) → smoke → binding_state → [Verify G4-V]
```

### 3.9 接口与数据结构（汇总）

| 接口 | 契约 | 位置 |
|---|---|---|
| `gate1_smoke.main(argv) -> int` | SPEC §3.2 | `gate1_smoke.py` |
| `gate2_ddl.main(argv) -> int` | SPEC §3.3 | `gate2_ddl.py` |
| `gate3_backfill.main(argv) -> int` | SPEC §3.4 | `gate3_backfill.py` |
| `gate4_activate.main(argv) -> int` | SPEC §3.5 | `gate4_activate.py` |
| `ConnLoader.load_db() -> db` | §3.3.2 | `common.py` |
| `BudgetReader.find/distinct/count/aggregate` | §3.3.3 | `common.py` |
| `TradeCalendar.is_trading_day(date) -> bool` / `FakeTradeCalendar` | §3.3.5 | `common.py` |
| `CompletedSessionPolicy.classify(trade_date, now) -> SessionStatus` | §3.3.5 | `common.py` |
| `SessionStatus` 枚举 | §3.3.5 | `common.py` |
| `ProdRankingWriter.get/upsert/count` | §3.6.1 | `prod_repository.py` |
| `ProdRankingReader.get` | §3.7.2 | `prod_repository.py` |
| `load_binding/write_binding` | §3.7.1 | `prod_repository.py` |
| `get_sector_ranking_history(trade_date, dataset, limit)` | 03-015 冻结读契约（Gate-4 经注入复用） | 冻结 service |

### 3.10 持久化设计（对齐模板 §3.4）

| 存储对象 | 写入触发点（文件:函数） | 写入字段子集 | 写入前过滤/校验 | 错误处理与回滚 |
|---|---|---|---|---|
| `tradingagents.03_data_ud_sector_ranking_daily` | `gate3_backfill.py:process_day()` → `ProdRankingWriter.upsert()`（仅 `BuildOutcome.status=="complete"` 的行） | 9 字段（SPEC §4.bis：dataset/trade_date/sector_code/sector_name/pct_chg/rank/close/pre_close/updated_at） | `build_ranking_rows` 100% exact-match；`SectorRankingDaily.from_dict` 行校验；rt 标记剔除；close/pre_close 有限数值 | upsert 失败计数进 `UpsertOutcome`；`failed>0` → G3-S-006 停止；写后读回不符 → G3-S-007 停止；不自动 rollback/drop；修复后按唯一键幂等重跑 |
| `data/rollout/sector-ranking/gate{N}-report.json/.md` | `common.py:write_report()`（每 Gate apply 结束） | G1-R-001~010 / G3-A / G4-A 字段集 | report 全文过 `scan_secrets`，命中 → SC-016-G0-1 | 写入失败 → 工具报错退出（不进入下一 Gate）；历史 report 以时间戳副本保留，不覆盖 |
| `data/rollout/sector-ranking/logs/gate{N}-*.log` | `common.py:log_jsonl()`（每步动作） | 结构化 JSONL（动作/耗时/计数/脱敏异常） | `redact()` 每个 record | 日志失败不阻断主流程（WARN 记录） |
| `data/rollout/sector-ranking/binding_state.json` | `gate4_activate.py:apply()`（`--enable`/`--disable` + `--apply`） | `{capability, enabled, gate, updated_at, previous}` | 仅由 gate4 工具写入 | `--disable` 为回滚路径；数据永不删除 |
| `data/rollout/sector-ranking/reference/sw_l1_reference.csv` | T3 创建（人工核对后固化） | `sector_code,sector_name,note` | 表头 + code 前缀 `801` | reference-only；不参与运行时；Gate-1 缺失即 STOP |

测试替身：所有写路径在测试中用 mongomock + `tmp_path` report/binding 文件；`ProdRankingWriter`/`ProdRankingReader` 接受 mongomock db，测试断言 upsert 行、namespace 拒绝、binding fail-closed。

### 3.11 UI / 原型设计

无（CLI 工具）。

### 3.12 开放问题解决（OQ-016-1~5 → Design 决策）

| OQ | 问题 | Design 决策 | 章节 |
|---|---|---|---|
| OQ-016-1 | 现有连接源是否满足最小权限（只读/只写/DDL 分离） | **复用 `MONGODB_*` 唯一受控连接源**（RFC CR-016-1），不新建账号/角色（超授权）。静态无法证明其角色权限 → Gate-1 G1-C-007 证明只读、Gate-2 apply 证明 DDL（fail-fast G2-S-001/002）；DDL 权限不足 → STOP 并上报 Pascal（不自动建账号）。残余风险见 §6 | §3.3.2 / §3.4 / §3.5 |
| OQ-016-2 | `index_basic_info` 是否含 SW L1 权威 code/name | 主来源 = `index_basic_info`（`market="CN"` + `^801` 过滤）；双源交叉核对 = `sw_l1_reference.csv`（reference-only）；reference 缺失 → G1-C-001 FAIL → STOP，Pascal 补/人工对照申万官网 | §3.4.3 |
| OQ-016-3 | canary 候选日选定规则 | 候选 = coverage 100% + close 完整 + 无 rt 标记 + 非今日；`recommended = max(trade_date)`（最近日最接近当前 schema/source 状态）；`--canary-date` 必须 ∈ 候选清单 | §3.4.2 |
| OQ-016-4 | 全量 backfill 日期范围解析 | 范围来源二选一：成对 `--start-date`/`--end-date`（Pascal 子范围）或 `--range-file`（Gate-1 全范围，**默认排除最早可用日**）；互斥；无范围来源 → EXIT_PARAM(1)；校验 start≤end ⊆ Gate-1 范围、经 CompletedSessionPolicy 判定已收盘 | §3.6.3 |
| OQ-016-5 | Gate-4 后是否需查询辅助索引 `idx_dataset_date` | 不创建（Gate-2 范围外）；Gate-4 smoke 查询均按 `{dataset, trade_date}` 过滤，由唯一索引前缀支持；留待未来 RFC 评估 | §3.5 / §3.7 |

---

## 4. 实现计划（T3 Implement worker 按 §4.1 ~ §4.6 顺序实现）

### 4.1 Step 1 — 包骨架与共享组件

- [ ] `scripts/unified_data/sector_ranking_rollout/__init__.py`
- [ ] `scripts/unified_data/sector_ranking_rollout/common.py`（ConnLoader / BudgetReader / ReportWriter / logger / redact / scan_secrets / 退出码 / TradeCalendar + FakeTradeCalendar / CompletedSessionPolicy + SessionStatus）
- [ ] `skills/data/unified_data/tests/test_sector_ranking_rollout_common.py`

### 4.2 Step 2 — Gate-1

- [ ] `scripts/unified_data/sector_ranking_rollout/gate1_smoke.py`
- [ ] `data/rollout/sector-ranking/reference/sw_l1_reference.csv`（31 个 SW 2021 L1 code/name，表头 + note 标注公开来源与核对日期；`REFERENCE-ONLY`）
- [ ] `skills/data/unified_data/tests/fixtures/rollout_fixtures.py`（含 Gate-1 fixture）
- [ ] `skills/data/unified_data/tests/test_sector_ranking_rollout_gate1.py`

### 4.3 Step 3 — Gate-2

- [ ] `scripts/unified_data/sector_ranking_rollout/gate2_ddl.py`
- [ ] `skills/data/unified_data/tests/test_sector_ranking_rollout_gate2.py`

### 4.4 Step 4 — Gate-3

- [ ] `scripts/unified_data/sector_ranking_rollout/prod_repository.py`（先实现 `ProdRankingWriter` + `BindingState` 骨架）
- [ ] `scripts/unified_data/sector_ranking_rollout/gate3_backfill.py`
- [ ] `skills/data/unified_data/tests/test_sector_ranking_rollout_gate3.py`

### 4.5 Step 5 — Gate-4

- [ ] `prod_repository.py` 追加 `ProdRankingReader`
- [ ] `scripts/unified_data/sector_ranking_rollout/gate4_activate.py`
- [ ] `skills/data/unified_data/tests/test_sector_ranking_rollout_gate4.py`

### 4.6 Step 6 — 全量验证与收尾

- [ ] 运行全部新单测（5 个 test 文件）
- [ ] 回归 03-015 定向（`test_sector_ranking_history.py`，51 项）与模块全量（1047/1047）保持 PASS
- [ ] `python3 -m scripts.unified_data.sector_ranking_rollout.gate1_smoke --help` 等 4 个工具 help/smoke 可运行（dry-run 路径，零真实 I/O）
- [ ] `git diff --check HEAD` 通过；`git status` 仅新增 allowlist 文件

---

## 5. 测试策略

### 5.1 单元测试（mongomock + 显式 fixture，零真实 I/O）

| 文件 | 覆盖（SPEC §6 编号 → 用例） |
|---|---|
| `test_sector_ranking_rollout_common.py` | CL-1~6（五键组件形态、缺失任一必需键 fail-fast、无 URI/prefix 分支、fingerprint 无连接值/无 username 信息）；G1-B-001~007（BudgetReader 白名单/过滤强制/limit/超时/扫描保护/记录上限/预算统计）；G1-B-002 负向（空 filter → BudgetViolation；aggregate 首 stage 非 `$match` → BudgetViolation；`$match` 无白名单字段 → BudgetViolation；白名单外字段 → BudgetViolation）；G0-C-005（redact/scan_secrets）；退出码常量；G4-P-001~010（CompletedSessionPolicy：FakeTradeCalendar + fake clock 注入逐项断言，fail-closed：policy=None → 拒绝读） |
| `test_sector_ranking_rollout_gate1.py` | G1-C-001~007（权威枚举/参考文件交叉核对/coverage/close 完整性/source 分布/隔离/连接指纹）；G1-S-001~008 每条触发路径 → 退出码；G1-R-001~010 report 字段齐备；G1-V-005 只读证明（计数前后一致） |
| `test_sector_ranking_rollout_gate2.py` | G2-D-001/002 幂等（重复执行跳过）；G2-S-003 规格不一致停止；G2-S-004 namespace 白名单；G2-S-002 前置 verify 失败 → 4；G2-A-001~004 审计证据 |
| `test_sector_ranking_rollout_gate3.py` | G3-B-002 日级原子（一日失败停止后续）；G3-B-003 升序处理；G3-B-004 前一日推导（首日 empty）；G3-B-007 日期转换；G3-B-008 重算 pct_chg（禁止上游值）；G3-B-009/010 rt 剔除、close/pre_close 校验；G3-B-012 incomplete/empty 不物化；G3-B-013~016 范围解析（`--range-file` 取 coverage_by_date 升序去重；默认排除最早日；`--range-file` 与 start/end 互斥 → 1；start 缺 end → 1；无范围来源 → 1；canary/范围来源互斥三负例：`--canary-date` + `--range-file` → 1、`--canary-date` + 成对 `--start-date`/`--end-date` → 1、`--canary-date` + 不成对 start/end → 1〔按缺配对〕；canary 单日模式无范围来源时合法 → 0/dry-run 计划）；G3-S-002~012 触发路径；G3-V-001~004 写后读回；canary 不进入全量（G3-S-008） |
| `test_sector_ranking_rollout_gate4.py` | G4-V-001~008 全部 smoke 用例（complete/empty/非法日期/当日未收盘/跨 dataset 混读/排序/limit/无越权写）；G4-V-004 正/反例（FakeTradeCalendar + fake clock：交易日未收盘 → ValueError；已收盘 → 不抛错；非交易日 → empty token）；G4-S-002~008 触发路径；binding fail-closed（disable 后读取拒绝）；policy fail-closed（无日历证据 → 拒绝读）；`--enable` 顺序（pre-smoke → binding → post-smoke）；回滚预案（G4-V-104） |

### 5.2 集成测试

- 每个 Gate 用 mongomock + fixture（`make_mongomock_db` 的**新增** `rollout_fixtures.py` 版本）端到端跑 `main(argv)`：dry-run 零副作用 → apply 产生 report → 断言 report 与退出码。
- Gate-3 集成：fixture 中构造 31 个 SW L1 code 的连续 3 个交易日文档 → canary + 全量 → 写后读回全部 PASS。
- Gate-4 集成：fixture 物化 canary 日数据 → `--enable` 全套 smoke → `--disable` 回滚证明。

### 5.3 手工验证（不可自动化项）

- 真实 Mongo 连接与权限：仅 production activation 卡（§8）由 Pascal 显式触发后验证。
- 权威 expected universe：Gate-1 真实 smoke 双源核对。
- 当日未收盘（G4-V-004）生产实况：依赖系统时钟与受控 live calendar evidence（§3.3.5/§8.4）；离线单测由 FakeTradeCalendar + fake clock 注入确定性覆盖（正/反例）。

### 5.4 回归范围

- `test_sector_ranking_history.py`（51/51）、`test_sector_provider_activation.py`、模块全量 1047/1047 必须保持 PASS。
- 实现只新增文件，不改既有文件 → 回归失败即视为越界（退回）。

---

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| Gate-1 发现真实数据不足 100%（缺行业/缺 close/日期断裂） | 严格按 G1-S-005 停止；report 记录缺口；canary 候选必须 100% | 不进入 Gate-2；Pascal 决策缩小日期范围或修上游 |
| `index_basic_info` 无 SW L1 枚举或与 reference 冲突 | 双源交叉核对 + discrepancies 记录 | G1-C-001 FAIL → 停止；Pascal 人工对照申万官网 |
| `MONGODB_*` 身份 DDL 权限不足（OQ-016-1 残余） | Gate-2 pre_verify + fail-fast | G2-S-001/002 停止，上报 Pascal（不自动建账号） |
| backfill 中途失败（连接/完整性/upsert/读回） | 日级原子 + G3-S-004~007 停止 + 不自动 retry/rollback/drop | 修复后从失败日幂等重跑（upsert 覆盖） |
| 误写目标集合外 / 误建多余集合 | ProdRankingWriter `_assert_namespace` + Gate-2 白名单 + post_verify 前后比对 | 停止；不自动删除；Pascal 显式授权后才处理 |
| 身份泄露（连接值/密码进日志） | `redact()` + `scan_secrets` + 静态扫描 | SC-016-G0-1 停止；rotate 后重跑 |
| Gate-4 激活后查询行为与离线不符 | 冻结 service 复用 + pre/post-smoke + token 逐字断言 | `--disable` 立即禁用 binding；数据保留 |
| consumer 集成需求被误并入 Gate-4 | 显式 scope diff（G4-S-003/004） | 独立变更上报 Pascal（G4-R-005） |
| 生产无受控交易日历证据（今日是否交易日/收盘状态未知） | CompletedSessionPolicy fail-closed（G4-P-008/009） | Gate-4 卡先取得受控 live calendar evidence；未确认不激活 binding；不猜测 |

---

## 7. 交接给实现者

### 7.1 必须遵守

1. **只新增 §3.1.1 allowlist 文件（共 14 个）**；禁止修改 §2.2 冻结清单任何文件（含 `conftest.py`、`scripts/unified_data/__init__.py`、`client.py`、03-015 全部文件、P3-A、模板、`.env`/config）。
2. **T3 零真实 I/O**：全部测试 mongomock + 显式 fixture；任何工具不得在 T3 触发真实连接/DDL/DML/Provider/回填/cron/Git。
3. **dry-run 默认、`--apply` 显式、`--yes` 确认**（G0-C-001~003）；缺 `--yes` 的 `--apply` 按 dry-run 处理并提示。
4. **退出码严格按 SPEC G0-C-004**（0/1/2/3/4）；与 audit_rollout.py 的映射不同，以 SPEC 为准。
5. **secrets 纪律**：任何输出不得回显连接值（host/port/username/password/db 值）或 token；出现含凭据 URI（防御性检测）/ `*TOKEN*` / `*SECRET*` 即视为泄露（SC-016-G0-1）；`redact()` 与 `scan_secrets()` 必须应用于全部 report/log。
6. **不复用 03-015 `HistoricalRankingWriter` 做真实写入**（其 `_assert_fake_db` 拒绝真实 pymongo）；真实写只走 `ProdRankingWriter`。
7. **expected universe 只来自 Gate-1 report（`--expected-file`）**，不得硬编码（H-049u）；`sw_l1_reference.csv` 仅供 Gate-1 交叉核对，**不参与** Gate-3 注入。
8. **pct_chg 固定公式**：`(close - pre_close) / pre_close * 100`（G3-B-008）；禁止使用上游自带 pct_chg。
9. **不自动 retry / rollback / drop / 删除**：任何失败 → 停止 + report；修复后由 Pascal 显式重跑。
10. **冻结 token 逐字**：`historical-ranking-empty` / `historical-ranking-incomplete`（import 03-015 常量，不自造）。
11. 完成后：验收标准全 PASS → `kanban_complete(status="done", summary=..., metadata={...})`；任何 FAIL → `kanban_block(reason="<哪条验收 FAIL + 期望 vs 实际>")`。残余风险（如 OQ-016-1 真实权限未知）属于 done 的 summary/metadata，**不构成 block 理由**（P-5）。
12. **交易日状态判定只经 `CompletedSessionPolicy`**（§3.3.5）：未来日/当日未收盘 ValueError 由 policy 抛出（ProdRankingReader 读入口），**不得**修改或声称冻结 `HistoricalSectorService` 抛此类异常（F2）。

### 7.2 可自行判断

- `common.py` 内部 helper 命名、`BudgetReader` 的 `projection` 参数默认值、聚合 pipeline 具体形态（在不违反 G1-B 前提下）。
- report `.md` 摘要格式（内容须覆盖结论/关键统计/canary/失败项）。
- `rollout_fixtures.py` 中 fixture 函数命名与拆分方式。
- 单测文件内部组织（可用 pytest 参数化减少重复）。
- `ProdRankingReader.binding` 的默认读取实现细节（读取 `binding_state.json` 的方式与缓存策略）。

### 7.3 遇到以下情况退回 Principal

- 发现必须修改任何冻结文件（§2.2）才能完成工具（如 `conftest.py` fixture 注册、`client.py` 改造）。
- 发现需要新增第三方依赖。
- 发现 SPEC 契约在真实 pymongo 下不可实现（如 `create_index(background=False)` 在目标 MongoDB 版本不可用）。
- 发现 Gate-1 无法从 `index_basic_info` 提取 SW L1 universe 且 reference 亦不可用（需重新定义权威来源）。
- 发现 `MONGODB_*` 身份权限不足且需创建账号/角色（OQ-016-1 需单独授权）。

---

## 8. Production activation 卡 action plan（Review PASS 后执行）

> 前置：本流水线（T1 RFC/SPEC → T2 Design → T3 Implement → T4 Verify → T5 Review）全部完成且 Review PASS（RFC PT-016-1）。orchestrator 创建分 Gate 串行卡（PT-016-2），每张卡 body 引用 RFC §5、SPEC §3、本设计 §3/§8 对应章节。Pascal 逐 Gate 显式触发（RFC §4.2）。

### 8.1 Gate-1 卡

```bash
# 1. dry-run（零副作用，可先于授权验证 CLI 与计划）
python3 -m scripts.unified_data.sector_ranking_rollout.gate1_smoke \
  --report-dir data/rollout/sector-ranking

# 2. apply（Pascal 显式触发；--yes 缺省视为 dry-run）
python3 -m scripts.unified_data.sector_ranking_rollout.gate1_smoke \
  --apply --yes --report-dir data/rollout/sector-ranking
```

独立只读 Verify（yquanttester，判定 PASS 才建 Gate-2 卡）：

| 判定 | 标准 |
|---|---|
| G1-V-001 | `data/rollout/sector-ranking/gate1-report.json` + `.md` 存在；JSON schema 校验通过（G1-R-001~010 + trade_date_format + discrepancies） |
| G1-V-002 | `stop_conditions_hit` 为空；`checks` 全 PASS |
| G1-V-003 | `expected_sector_codes` 非空，与 `index_basic_info` 抽查 5 个 code/name 一致 |
| G1-V-004 | report/log 静态扫描无 secrets |
| G1-V-005 | `index_daily_quotes` / `index_basic_info` `estimatedDocumentCount` 与 Gate-1 前后基线一致（只读证明） |

### 8.2 Gate-2 卡

```bash
python3 -m scripts.unified_data.sector_ranking_rollout.gate2_ddl \
  --apply --yes --report-dir data/rollout/sector-ranking
```

Verify（G2-V-001~005）：`getCollectionInfos` 含目标集合；`getIndexes` 含 `uniq_dataset_date_sector`（key/unique 与 G2-D-002 一致）；无 `idx_dataset_date`；`list_collection_names` 与 Gate-2 前置快照比对无白名单外新增；`portfolio_*` 抽样计数前后一致；无 secrets。

### 8.3 Gate-3 卡（分两步，Pascal 放行全量）

```bash
# 1. canary（至多 1 日，来自 gate1-report.canary_candidates）
python3 -m scripts.unified_data.sector_ranking_rollout.gate3_backfill \
  --expected-file data/rollout/sector-ranking/gate1-report.json \
  --canary-date <recommended_canary> --apply --yes --report-dir data/rollout/sector-ranking
```

Verify canary（G3-V-101）：读回 canary 日 → 行数==expected、9 字段完整、排序稳定、唯一键无重复；`outcome.failed==0`。PASS 后 **Pascal 显式放行全量范围**（G3-B-001）：

```bash
# 2. 全量（范围 = Gate-1 全范围自动排除最早日；必须显式传 --range-file，F1 冻结）
python3 -m scripts.unified_data.sector_ranking_rollout.gate3_backfill \
  --expected-file data/rollout/sector-ranking/gate1-report.json \
  --range-file data/rollout/sector-ranking/gate1-report.json \
  --apply --yes --report-dir data/rollout/sector-ranking

# 2'. 全量子范围（Pascal 显式指定；成对传入；经 CompletedSessionPolicy 校验已收盘）
python3 -m scripts.unified_data.sector_ranking_rollout.gate3_backfill \
  --expected-file data/rollout/sector-ranking/gate1-report.json \
  --start-date 2010-01-05 --end-date 2026-07-30 \
  --apply --yes --report-dir data/rollout/sector-ranking
```

Verify 全量（G3-V-102~105）：`summary.failed_days==0` 且 `stop_conditions_hit` 为空；目标集合外无新增文档；其他集合计数一致；无 secrets；抽查 3 个 trade_date 用 close/pre_close 重算 pct_chg 与库内一致。

### 8.4 Gate-4 卡

```bash
# 0. 受控 live calendar evidence（F2 闭合，G4-P-009）：operator/Pascal 对照权威来源
#    确认「今日是否为交易日、是否已收盘（Asia/Shanghai 15:00 CST）」，写入
#    data/rollout/sector-ranking/gate4-calendar-evidence.json；未确认 → fail-closed 不激活
python3 -m scripts.unified_data.sector_ranking_rollout.gate4_activate \
  --expected-file data/rollout/sector-ranking/gate1-report.json \
  --enable --apply --yes --report-dir data/rollout/sector-ranking

# 回滚演练（Verify 用）：禁用 binding → 证明读取被拒绝 → 重新启用
python3 -m scripts.unified_data.sector_ranking_rollout.gate4_activate \
  --expected-file data/rollout/sector-ranking/gate1-report.json \
  --disable --apply --yes --report-dir data/rollout/sector-ranking
```

Verify（G4-V-101~105）：smoke 全部 PASS（G4-V-001~008）；warning token 逐字一致；activation 卡路径 allowlist / baseline manifest 与基线 diff 为空（共享树既有 03-015 dirty 不计，OBS-2）；`--disable` 后绑定 reader 拒绝读取（回滚预案可执行）；无 secrets；calendar evidence 存在且与当日分类一致（G4-P-009）。

### 8.5 失败处理

任何 Gate 失败 → 暂停，上报 Pascal；**不自动** retry、扩范围、反向 DDL（PT-016-4）。修复路径：Gate-1 数据缺口 → Pascal 决策；Gate-2 权限不足 → Pascal 单独授权或评估连接源；Gate-3 失败日 → 修复后显式重跑该日（幂等）；Gate-4 → `--disable` 回滚。

---

## 9. 声明

本设计中涉及的板块/行业数据为辅助研究数据，不构成交易指令或投资建议。

本设计不修改 RFC-03-015 / SPEC-03-015 / DESIGN-03-015 已冻结内容，不修改 P3-A 任何文件，不修改文档模板。所有引用以交叉引用方式继承，冲突时以 RFC-03-016 / SPEC-03-016 为准。

本设计定义 Gate 工具的**实现与执行设计**，不构成任何真实生产动作的已执行声明；所有 Gate 的真实执行仅在独立 Review PASS 后由 Pascal 逐 Gate 显式触发 production activation 卡。

---

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.4 | 2026-07-31 | 评审 `t_99d11552` REVISE 闭合（F-1）：Gate-3 `--canary-date` 与全量范围来源互斥冻结——与 `--range-file` 同时传入 → 退出码 1、与成对 `--start-date`/`--end-date` 同时传入 → 退出码 1、与不成对 start/end 仍按缺配对 → 退出码 1（§3.6.3 范围解析表新增互斥行 / G3-S-003 触发点扩展）；canary 单日模式仅在无任何范围来源时合法；§5.1 gate3 测试矩阵补三负例。**未改变** canary 候选选择、date range 计算、Gate-3 回填范围、任何生产动作与退出码总体集合（仍 0/1/2/3/4） | YQuant-Codex-Principal |
| V0.3 | 2026-07-31 | T2.2 交叉文档闭合（Gate `t_e1611476` REVISE）：F1 Gate-3 范围来源唯一化（`--range-file` 进 CLI synopsis，与成对 `--start-date`/`--end-date` 互斥，无范围来源 → EXIT_PARAM(1)，§3.6.3/§8.3）；F2 新建可注入 TradeCalendar / CompletedSessionPolicy（§3.3.5，ProdRankingReader 读入口执行，冻结 service 零修改；G4-R-003/G4-V-004 fake calendar + fake clock 逐项证伪）；F3 G1-B-002 过滤白名单统一（含 `market`，find 与 aggregate 首 stage 同规则）；F4 provenance 修正（来源 SPEC V0.1→V0.2）；OBS-1 conn_prefix 旧概念措辞修正（§3.4.4）；OBS-2 Gate-4 git-status 收敛为 activation 卡路径 allowlist / baseline manifest（§3.7.4）。**未改变** V0.1/V0.2 已冻结的 Gate 业务语义、退出码、连接源与 allowlist 总数（仍 14） | YQuant-Codex-Principal |
| V0.2 | 2026-07-31 | 评审 #864 闭合：连接源收敛为唯一受控 `MONGODB_*` 组件来源（五键组件式构造，无 URI/prefix/alias/fallback，CLI 去掉 `--conn`，fingerprint 去 username 派生信息）；T3 allowlist 统一为 14 个新文件并全篇一致。**未改变 Gate 业务语义** | YQuant-Codex-Principal |
| V0.1 | 2026-07-31 | 初始创建：Gate 工具族（gate1_smoke / gate2_ddl / gate3_backfill / gate4_activate + common + prod_repository）文件级设计、T3 allowlist、测试矩阵、OQ-016-1~5 解决、逐 Gate production activation action plan | YQuant-Codex-Principal |
