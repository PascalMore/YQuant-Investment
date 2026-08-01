# DESIGN-03-017: 申万指数历史 quote metadata 治理 runner（census / dry-run / apply / verify 四模式）

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-08-01 |
| 最后更新 | 2026-08-02 |
| 来源 RFC | RFC-03-017-sw-index-daily-quote-schema-governance（V0.2 契约基线） |
| 来源 SPEC | SPEC-03-017-sw-index-daily-quote-schema-governance（V0.2 契约基线） |
| 目标模块 | 03_data（数据层）— `tradingagents.index_daily_quotes` 历史 metadata 治理 runner |
| 适配 Agent | YQuant-Developer-Engineer（T3 Implement）、YQuant-Test-Engineer（T4 Verify）、YQuant-Reviewer-Principal（T5 Review） |

## 0. 版本说明

V0.3 为闭包修订（kanban `t_ae320c08`）：来源 SPEC 指针 V0.1 → V0.2（契约基线同步）；新增 §10 闭包账本（canonical C17 ID / M2 run-id-resume / 源元数据基线 / 无语义变更声明）。**文档修订 V0.3 ≠ 引用契约基线**：本文档引用的契约基线为 RFC-03-017 V0.2 与 SPEC-03-017 V0.2；V0.3 仅含元数据修正，**无任何语义 runner / mutation 行为变化**；SPEC-03-017 不因下游指针修复而升级（无版本级联）。

V0.2 为 P0 文档修正（kanban `t_c3f567eb`，M2）：补全 `--run-id` CLI 契约（§3.4.1）与 checkpoint lineage 语义（§3.3.4：**新 run-id = 全新 lineage；复用同一 run-id = 从最后成功 checkpoint 恢复**）；production activation runbook（§8）全部 apply/resume 命令显式携带 `--run-id <operator-chosen-id>`；verify 预统计读取说明（§3.7/§8.4）；规模估计算术修正（141,021 → 141,019 = 31 × 4,549）；来源 RFC 更新为 V0.2。

V0.1 为初始版本。本设计把 RFC-03-017 的治理契约与 SPEC-03-017 的可执行契约落实为：

1. 一个**离线可测、dry-run 默认、`--mode apply` 显式副作用**的 runner 工具（`govern_quote_metadata.py`）+ 共享组件（`common.py`）。
2. 候选选择（fail-closed）、census 三重证据校验、dry-run 报告、幂等 mutation、批次/检查点/恢复、写后 verify 的**精确文件范围（T3 allowlist）**、控制流、接口、report 结构、测试矩阵。
3. **Production activation runbook**：Review PASS 后由 Pascal 显式触发生产 DML 的精确命令与授权边界，以及独立的 `name` 恢复（restoration）路径设计（仅经单独批准执行，从 `stock_sector_info` 重建）。

本设计**不修改**任何既有文件（含 `scripts/unified_data/sector_ranking_rollout/*` 03-016 工具族、`skills/data/unified_data/` 任何文件、文档模板）；**不执行**任何真实连接 / DDL / DML / Provider / 回填 / 服务 / cron / Git 操作（T3 仅 mongomock + 显式 fixture）。

---

## 1. 设计摘要

RFC-03-017 / SPEC-03-017 定义了治理的**契约**（候选谓词、fail-closed 门禁、幂等 mutation、批次/检查点、验证方程、副作用矩阵），本设计将其落实为**一个可实现的 runner 工具族**。

核心设计决策：

| 决策点 | 结论 | 理由 |
|---|---|---|
| 工具存放位置 | 新建包 `scripts/unified_data/quote_metadata_governance/` | 与 `scripts/unified_data/sector_ranking_rollout/`（03-016）、`audit_rollout.py`（03-011）同层；`scripts/__init__.py` 已声明 scripts 子包可被测试 import |
| 工具形态 | **单 CLI 四模式**（`--mode {census,dry-run,apply,verify}`），非多工具 | SPEC C17-001 定义单 CLI；四模式共享同一候选谓词、同一 census 结果，天然串行衔接 |
| 工具与运行时库分离 | 全部为**新文件**，不触碰 `skills/data/unified_data/` 任何既有文件 | SPEC §7：实现阶段只新增工具文件与测试 |
| 真实写路径 | 新建 `QuoteMetadataWriter`（允许真实 pymongo + namespace 白名单断言，仅 `tradingagents.index_daily_quotes`） | 03-015 `HistoricalRankingWriter` 的 `_assert_fake_db` 拒绝真实 pymongo 且文件冻结；本治理必须新增生产 writer |
| 候选选择 | `CandidateSelector` 严格按谓词 `P`（`data_source == "akshare"` ∧ `full_symbol` 以 `.SI` 结尾）+ 三重证据门禁（C17-201~207），fail-closed | SPEC §3.2/§3.3；任何证据冲突即停止，不 mutate |
| 幂等 mutation | `bulk_write([UpdateOne({"_id": id}, {"$set": {...}, "$unset": {...}})], ordered=False)`，`upsert=False` | SPEC M17-001~007；无 replace/delete/upsert/insert/DDL |
| 批次/恢复 | batch_size 默认 500（1..1000）；候选按 `_id` 升序；每批 checkpoint JSONL；resume key = `_id` | SPEC B17-001~007；确定性可恢复 |
| 离线/真实分离 | 工具核心逻辑全部可注入 mongomock db；`--mode apply` 才产生真实副作用；真实执行仅在 production activation runbook | SPEC §2.2 / RFC §4.1 幂等、可停止、可审计 |
| 退出码 | 严格按 SPEC C17-002：0 成功 / 1 参数前置失败 / 2 停止条件 / 3 连接凭据 / 4 verify 失败 | 与 audit_rollout.py 的映射不同，03-017 以 SPEC 为准 |
| 规模估计 | ~141,019 条观测（31 个 SW L1 行业 × 约 4,549 个交易日，设计时点数量级估计）；**apply 前必须重新 census，绝不作为硬编码目标** | 任务要求 8；仅用于评估批量规模/耗时，不参与任何门禁判断 |

**成功标准**：Design 文档存在且提供 T3 Implement 的精确 allowlist、runner 四模式行为到函数级、测试矩阵（含零写 dry-run 矩阵）、production runbook 命令与授权边界；`git diff --check` 通过；不触碰任何既有文件。

---

## 2. 现状分析

### 2.1 相关目录与文件

| 路径 | 现状 | 本设计关系 |
|---|---|---|
| `tradingagents.index_daily_quotes` | 生产集合；`SwIndexDailyService` 与 `HistoricalDataService` 双 writer 造成 metadata 漂移（RFC §2.1/§2.2） | **治理目标集合**（未来 apply 唯一写目标） |
| `tradingagents.stock_sector_info` | `classify_system == "SW"` 的 `l1_code → l1_name` 权威映射；RFC-03-016 L1 契约权威 universe 来源 | **只读**：C17-102 权威 universe `U` 推导；`name` 恢复（restoration）唯一数据来源 |
| `scripts/unified_data/audit_rollout.py` | RFC-03-011 生产 DDL/rollout 工具（dry-run 默认、退出码 0-4、allowlist、secrets guard） | **只读参考**（CLI/脱敏/退出码模式）；禁止修改 |
| `scripts/unified_data/sector_ranking_rollout/*` | RFC-03-016 生产 rollout 工具族（gate1~4，当前共享树含未提交修改） | **只读参考**（ConnLoader/redact/scan_secrets 模式）；禁止修改 |
| `skills/data/unified_data/adapters/ta_cn_mongo_adapter.py` | TA-CN 只读 adapter | **只读参考**；本 runner 自带只读查询，不复用（其 `get_index_daily_bars` 不支持 `full_symbol` 过滤，03-016 DP-016-2 记录） |
| `skills/data/unified_data/models/domain/market_data.py` | `IndexDailyBar` canonical，无 `name` 字段 | **证据**（quote 级 `name` 不被消费）；禁止修改 |
| `skills/.env` | `MONGODB_*` 五键主连接（`MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE`，库 `tradingagents`） | runner 仅使用该唯一受控连接源（C17-012）；不读取/打印值 |
| `data/rollout/` | 已存在（03-016 使用 `data/rollout/sector-ranking/`） | 本治理产物目录 `data/rollout/index-daily-quote-governance/`（C17-007） |

> 注意（共享目录基线，沿用 03-016 M7 纪律）：本仓库为共享工作目录，`git status` 的 dirty 集合只是某一时刻快照，不构成归属证明。Verify/Review 判定 03-017 边界时必须使用**路径过滤的基线归属**——仅本设计 §3.1.1 T3 allowlist 与本三份 03-017 文档计入 03-017；§2.2 冻结清单任何文件出现 diff 即视为越界。

### 2.2 精确禁止修改路径（T3 allowlist 外延）

- ❌ 03-016 工具族：`scripts/unified_data/sector_ranking_rollout/**`（`__init__.py`/common.py/gate1~4/prod_repository.py/测试/fixture）
- ❌ 03-015 冻结：`models/domain/sector_ranking.py`、`services/historical_sector_service.py`、`adapters/historical_ranking_writer.py`、`client.py`、`tests/test_sector_ranking_history.py`、`tests/fixtures/historical_ranking_fixtures.py`
- ❌ 03-014 P3-A 冻结：`providers/akshare.py`、`providers/sector_client.py` 等
- ❌ 既有 rollout 工具：`scripts/unified_data/audit_rollout.py`、`audit_smoke.py`、`scripts/t4_preflight/**`、`scripts/service_readiness/**`
- ❌ 文档模板：`docs/rfc/RFC-00-000-*`、`docs/spec/SPEC-00-000-*`、`docs/design/DESIGN-00-000-*`、3 层 README
- ❌ 任何 `.env` / config / requirements / SKILL.md / README / router / provider / service 注册
- ❌ writer 代码：`skills/apps/TradingAgents-CN/app/services/sw_index_daily_service.py`、`historical_data_service.py`（RFC §3.2 非目标）

### 2.3 关键复用点与缺口

| 复用点 | 来源 | 用途 |
|---|---|---|
| 退出码常量（0/1/2/3/4）与语义 | SPEC C17-002 | common.py 常量定义 |
| 连接源五键组件式构造 + fingerprint + 缺失键 fail-fast | SPEC C17-012 / 03-016 `ConnLoader` 模式 | 新建 `ConnLoader` |
| `redact()` / `scan_secrets()` 模式 | SPEC C17-005 / 03-016 common.py 模式 | 新建脱敏与泄露扫描 |
| report 目录/命名/归档模式 | SPEC C17-007/C17-008 / 03-016 `ReportWriter` 模式 | 新建 `ReportWriter` + JSONL logger |
| `_id` 升序排序 + checkpoint resume | SPEC B17-003/B17-004/B17-006 | 新建 `CheckpointStore` |

| 缺口 | 本设计补齐方式 | 章节 |
|---|---|---|
| 真实 Mongo 写入（字段级 `$set`/`$unset`） | 新建 `QuoteMetadataWriter`（允许真实 pymongo + namespace 白名单断言；仅 `tradingagents.index_daily_quotes`） | §3.6 |
| 候选选择 + 三重证据门禁 | 新建 `CandidateSelector` / `CensusEngine` | §3.4 |
| 批次/检查点/恢复 | 新建 `CheckpointStore`（JSONL，resume key `_id`） | §3.6/§3.7 |
| 写后 verify 方程 | 新建 `Verifier`（V17-004~006） | §3.7 |

---

## 3. 方案设计

### 3.1 模块/文件改动（T3 Implement allowlist）

#### 3.1.1 新建文件（精确路径，全部允许）

**T3 allowlist 总数 = 5**：3 工具文件 + 1 fixture + 1 tests。下表为唯一权威清单；与 §4 实现步骤、§5.1 测试矩阵、§7.1 交接、§8 验收一致。

| 文件 | 内容 | 说明 |
|---|---|---|
| `scripts/unified_data/quote_metadata_governance/__init__.py` | 包标记 + `__all__` 导出 | 空包标记即可 |
| `scripts/unified_data/quote_metadata_governance/common.py` | `ConnLoader` / `ReportWriter` / JSONL logger / `CheckpointStore` / `redact()` / `scan_secrets()` / 退出码常量 / `resolve_report_dir()` / 时间戳 helper | runner 共享；见 §3.3 |
| `scripts/unified_data/quote_metadata_governance/govern_quote_metadata.py` | 主 CLI：`CandidateSelector` / `CensusEngine` / `MutationPlanner` / `QuoteMetadataWriter` / `Applier` / `Verifier` + `main(argv) -> int` | SPEC §3；见 §3.4~§3.7 |
| `skills/data/unified_data/tests/fixtures/quote_metadata_governance_fixtures.py` | 测试 fixture：`make_sw_quote_docs()`、`make_sw_universe()`、`make_mixed_quote_docs()`（含 gate 反例）、`make_checkpoint(tmp_path)` 等 | 新增 fixture，不与 03-016/03-015 fixture 混用 |
| `skills/data/unified_data/tests/test_quote_metadata_governance.py` | runner 全矩阵单测（common + census + dry-run + apply + verify） | SPEC §8；见 §5.1 |

#### 3.1.2 修改文件

**无。** 本设计不修改任何既有文件（含 `scripts/unified_data/__init__.py` 与 `skills/data/unified_data/tests/conftest.py`）。

> 若 Implement 阶段发现必须修改既有文件，必须按 §7.3 退回 Principal，不擅自修改。

#### 3.1.3 执行入口

工具以模块方式执行（与 repo 根目录可 import 的约定一致）：

```bash
python3 -m scripts.unified_data.quote_metadata_governance.govern_quote_metadata --help
```

模块含 `if __name__ == "__main__": sys.exit(main())`；`main(argv=None) -> int` 供测试直接调用。

### 3.2 总体控制流

```text
Production activation（仅 Review PASS 后 + Pascal 显式触发，§8）
   │
   ▼
--mode census（只读）：候选 P 查询 + 权威 universe U + 三重证据门禁 C17-201~205
   │  [全部 PASS 才继续；任一 FAIL → EXIT_STOP=2，零写]
   ▼
--mode dry-run（只读）：分类计数 + 字段/类型分布 + 有界样本 + 预期 mutation 计数
   │  [dry-run 零副作用；apply 前必须重跑 census 复核规模估计]
   ▼
--mode apply --yes --run-id <operator-chosen-id>（显式副作用）：按 _id 列表逐批 bulk_write(ordered=False)，
   │  每批 checkpoint，stop-on-error，无自动回滚；resume 复用同一 --run-id（B17-006）
   ▼
--mode verify（只读）：写后 re-census + 计数方程 V17-004~006
   [方程全过 → EXIT_OK；任一 FAIL → EXIT_VERIFY=4]
```

工具内部控制流（四模式一致）：

```text
main(argv)
  ├─ argparse 解析（--mode / --yes / --batch-size / --report-dir；无 --conn / 无 prefix 选择）
  ├─ [--mode apply 无 --yes] → 按 dry-run 处理并提示（C17-004）
  ├─ 非 apply 模式：零副作用，仅只读
  └─ apply：
       ├─ ConnLoader().load_db()           （失败 → 退出码 3）
       ├─ census（C17-201~205 全过才继续；任一 FAIL → 2）
       ├─ 执行 mutation（逐批，checkpoint，stop-on-error）
       ├─ 审计证据（report + logs + checkpoint）
       ├─ secret 扫描（发现泄露 → 2，SC-017-G0-1）
       └─ 退出码：0 成功 / 2 停止条件命中 / 3 连接失败 / 4 verify 失败
```

### 3.3 共享组件设计（common.py）

#### 3.3.1 退出码常量（对齐 SPEC C17-002）

| 常量 | 值 | 语义 |
|---|---|---|
| `EXIT_OK` | 0 | 成功（census/dry-run/apply/verify 全过；含空候选 no-op） |
| `EXIT_PARAM` | 1 | 参数/前置校验失败（非法 `--mode`/`--batch-size`/缺 `--yes`） |
| `EXIT_STOP` | 2 | 停止条件命中（C17-201~205 gate FAIL / SC-017-G0-1） |
| `EXIT_CONN` | 3 | 连接/凭据失败（fail-fast，不降级） |
| `EXIT_VERIFY` | 4 | verify 失败（V17-004~006） |

#### 3.3.2 `ConnLoader`（connection closure：唯一受控连接源）

> **连接源闭合 ledger（与 03-016 一致）**：连接源 = 环境中的 `MONGODB_HOST / MONGODB_PORT / MONGODB_USERNAME / MONGODB_PASSWORD / MONGODB_DATABASE`；连接形态 = 组件式构造，不允许 URI；CLI 不暴露 `--conn` 或 prefix 选择；无 alias / 无 fallback；缺失任一必需键 = fail-fast EXIT_CONN(3)，仅记录键名；日志/report 不得回显连接值（C17-012）。

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
| CL-1 | 连接源 = 环境中的 `MONGODB_HOST` / `MONGODB_PORT` / `MONGODB_USERNAME` / `MONGODB_PASSWORD` / `MONGODB_DATABASE` 五键（C17-012）。组件式构造：`pymongo.MongoClient(host=..., port=int(...), username=..., password=..., authSource=MONGODB_DATABASE)`；**不允许 URI**、不允许任意 prefix |
| CL-2 | 数据库名 = `MONGODB_DATABASE`；`authSource` = `MONGODB_DATABASE`（固定值） |
| CL-3 | 缺失任一必需键 → fail-fast 退出码 3（SC-017-G0-2），仅打印缺失键名 |
| CL-4 | Client 选项：`serverSelectionTimeoutMS=10000`、`connectTimeoutMS=10000`（C17-006 ≤10s） |
| CL-5 | 测试替身：构造参数 `client_factory` 显式注入 mongomock 的 `MongoClient`；测试**不得读取环境**（零真实 I/O） |
| CL-6 | 任何位置不得打印连接值；`fingerprint()` 只含结构字段，**不含 username 的任何可逆/可识别信息**（C17-005） |

#### 3.3.3 `ReportWriter` + JSONL logger + 脱敏

```python
REPORT_DIR_DEFAULT = "data/rollout/index-daily-quote-governance"

def resolve_report_dir(report_dir: str | None) -> str: ...   # mkdir -p（C17-007）
def utc_now_iso() -> str: ...                                # datetime.now(timezone.utc).isoformat()（C17-010）

def write_report(report_dir: str, payload: dict) -> None:
    # 写 quote-governance-report.json（规范路径，最新证据）+ quote-governance-report-<UTC ISO 文件名安全>.json（归档副本，不覆盖历史，C17-007）
    # 写 quote-governance-report.md（人读摘要）

def log_jsonl(report_dir: str, record: dict) -> None:
    # 追加到 data/rollout/index-daily-quote-governance/logs/quote-governance-<YYYYMMDD>.log（C17-008）

def redact(text: str) -> str:
    # 掩码：连接值（MONGODB_* 的值）与 *TOKEN*/*SECRET* 已知值；防御性检测 mongodb(+srv):// 含凭据段（SC-017-G0-1 兜底）

def scan_secrets(text: str) -> list[str]:
    # 返回命中的泄露类别列表（uri_with_credentials / password_value / token_value / secret_value）；
    # 非空 → SC-017-G0-1 → 退出码 2
```

- **report 命名与 run-id 对齐**：canonical `quote-governance-report.json` 始终为最新证据（可被后续模式覆盖）；归档副本 `quote-governance-report-<UTC ISO>.json` 不覆盖历史（C17-007）。每个 report 的 payload 携带 `run_id`（R17-001），checkpoint 文件按 run-id 隔离（`quote-governance-checkpoint-<run_id>.jsonl`，§3.3.4）——report 与 checkpoint 通过 run_id 对齐同一 lineage。

幂等（C17-009）：工具重复执行不改变已有状态；同参数重跑结果一致。census/dry-run/verify 天然幂等；apply 幂等靠「已合规记录跳过 + `$set`/`$unset` 对合规记录为 no-op（matched 但 modified=0）」（M17-005）。

#### 3.3.4 `CheckpointStore`（确定性 checkpoint / resume）

```python
class CheckpointStore:
    def __init__(self, report_dir: str, run_id: str) -> None: ...
    def load(self) -> dict | None:        # 读 quote-governance-checkpoint-<run_id>.jsonl 最后一行；无 → None
    def save(self, record: dict) -> None: # 追加 {batch_seq, batch_start_id, batch_end_id, matched, modified, ts_utc}（B17-004）
```

- checkpoint 文件命名带 `run_id` 与日期，不得覆盖历史（C17-007）。
- **run-id lineage（M2）**：`--run-id` 是 operator 选择的**不可变标识**。**新 run-id = 全新 checkpoint lineage**——`load()` 读不到该 run-id 的 checkpoint 文件 → 从第 0 批开始；**复用同一 run-id = 从最后成功 checkpoint 恢复**——`load()` 读取 `quote-governance-checkpoint-<run_id>.jsonl` 最后一行 → 跳过已 checkpoint 批。生产 apply/resume 必须复用同一 `--run-id`（§8）；自动生成 run-id（`qg-<uuid12>`）无法满足恢复语义，仅限一次性只读模式使用。
- **resume key 确定性**：候选按 `_id` 升序；恢复查询 = 谓词 `P` ∧ `_id > batch_end_id`（B17-006）；已修复记录在分类阶段被识别为已合规并跳过，恢复收敛（M17-005）。
- 每批 `save()` 成功后才进入下一批（B17-004）；`save()` 失败 → 停止（同批失败处理，B17-005）。

### 3.4 Census 详细设计（govern_quote_metadata.py: census 模式）

#### 3.4.1 CLI（对齐 SPEC §3.1）

```text
python3 -m scripts.unified_data.quote_metadata_governance.govern_quote_metadata \
  --mode {census,dry-run,apply,verify} \
  [--run-id <operator-chosen-id>] \
  [--yes] \
  [--batch-size 500] \
  [--report-dir data/rollout/index-daily-quote-governance]
```

- `--mode` 默认 `census`（C17-001）。
- `--mode apply` 必须伴随 `--yes`（C17-004）；缺 `--yes` 视为 dry-run 并提示。
- `--batch-size` 默认 500，范围 1..1000，非法值 → EXIT_PARAM(1)（C17-011）。
- `--run-id`：operator 选择的**不可变标识**（如 `20260801-gov-01`）；缺省自动生成 `qg-<uuid12>`（一次性，不满足恢复语义）。**生产 apply 与 resume 必须显式指定并复用同一 `--run-id`**（M2/B17-006）：新 run-id = 全新 checkpoint lineage；复用同一 run-id = 从最后成功 checkpoint 恢复（§3.3.4）。census/dry-run/verify 建议复用 apply 的 run-id，保持同一 lineage 的 report/checkpoint 命名一致。
- `verify` 模式复用同一 census 候选谓词，但**禁止** `--yes`/`--batch-size` 语义（只读）；传入 `--yes` 时提示忽略。

#### 3.4.2 候选谓词与权威 universe（C17-101 ~ C17-106）

```python
def build_predicate() -> dict:
    return {"data_source": "akshare", "full_symbol": {"$regex": "\\.SI$"}}  # C17-101

def derive_universe(db) -> set[str]:
    # C17-102：stock_sector_info 中 classify_system == "SW" 的 distinct l1_code，
    # 每个归一化为 6 位数字 + ".SI"（与 SwIndexDailyService._normalize_code 一致：去后缀、取 "." 前部分、大写）
    ...
```

- `U` 为空 → 停止（C17-103，EXIT_STOP=2），报告 `stock_sector_info` 无 SW 记录。
- `total_candidates == 0` → 成功 no-op（退出码 0），report 标注 "nothing to do"（C17-104）。
- census 阶段固化候选 `_id` 列表（或分页键）；apply/verify 不重新用谓词查询（C17-105）。
- 只读边界：census 只读 `index_daily_quotes`（P 命中）与 `stock_sector_info`（U 推导）；禁止读其他集合（C17-106）。

#### 3.4.3 Fail-closed 三重证据校验（C17-201 ~ C17-207）

census 阶段必须按顺序执行以下 gates（C17-207：串行；任一 FAIL 即停止，后续 gate 不执行）：

| Gate | 校验内容 | 通过条件 | 失败动作 |
|---|---|---|---|
| C17-201 | 后缀证据 | 100% 候选 `full_symbol` 以 `.SI` 结尾；distinct 后缀集合 == `{".SI"}` | STOP（EXIT_STOP=2），报告分布 |
| C17-202 | data_source 证据 | 100% 候选 `data_source == "akshare"`；distinct 集合 == `{"akshare"}` | STOP，报告分布 |
| C17-203 | code-family 证据 | P 内 `distinct(full_symbol)` ⊆ U；反例计数 == 0 | STOP，报告反例清单（full_symbol + trade_date 计数） |
| C17-204 | market 证据 | 100% 候选 `market == "CN"`（字段存在时）；缺失 market 计数 == 0 | STOP，报告分布 |
| C17-205 | period 证据 | 100% 候选 `period == "daily"`（字段存在时）；缺失 period 计数 == 0 | STOP，报告分布 |
| C17-206 | 观察项（不阻断） | 非候选观察计数：`.SI` 但非 akshare 记录数、akshare 但非 `.SI` 记录数（仅报告） | 无 |
| C17-207 | gate 顺序 | C17-201 → 202 → 203 → 204 → 205 串行 | — |

任何 gate FAIL 时，report 记录证据分布（哪些值、多少条）后停止；禁止降级阈值、禁止忽略反例。

#### 3.4.4 合规分类（C17-301 ~ C17-304）

| 分类 | 定义 |
|---|---|
| `already_compliant` | `version` 为 BSON int 且 ==1 且 `name` 不存在 |
| `missing_version` | `version` 字段缺失（无论 `name` 存在与否） |
| `nonconforming_version` | `version` 存在但非 BSON int 或值 ≠ 1（float/str/int!=1 等） |
| `name_present` / `name_absent` | `name` 字段存在（任意类型）/ 不存在 |

派生计数：`version_fix_needed = missing_version + nonconforming_version`；`both_needed = version_fix_needed ∧ name_present` 的候选数。

**精确 mutation 谓词**（apply 只对以下两类候选发 UpdateOne；已合规候选直接跳过，不发写）：

```text
MUTATE_VERSION: version 缺失 或 version 不合规（非 BSON int 且值 ≠ 1）   → $set {version: 1}
MUTATE_NAME:    name 字段存在（任意类型）                                → $unset {name: ""}
单条合并：update_one({"_id": id}, {"$set": {"version": 1}, "$unset": {"name": ""}})
```

### 3.5 Dry-run 详细设计（dry-run 模式）

dry-run 复跑 census（只读），输出 report：

| 编号 | 报告段 | 字段 |
|---|---|---|
| R17-001 | 运行元信息 | `run_id`、`mode`、`ts_utc`、`conn_source`、`conn_fingerprint`（仅结构）、`collection`、`predicate` 序列化 |
| R17-002 | 候选统计 | `total_candidates`、`total_docs_scanned` |
| R17-003 | 合规分类 | `already_compliant`、`missing_version`、`nonconforming_version`、`version_fix_needed`、`name_present`、`name_absent`、`both_needed` |
| R17-004 | 字段/类型分布 | `version` 类型直方图（absent/int==1/int!=1/float/str/other）、`name` 类型直方图（absent/str/non-str）、受保护字段存在性计数（full_symbol/code/symbol/market/trade_date/period/open/high/low/close/pre_close/volume/amount/pct_chg/data_source/created_at/updated_at） |
| R17-005 | 有界样本 | 每类（already_compliant/missing_version/nonconforming_version/name_present/both_needed）至多 5 条；每条仅 `id_prefix`（`_id` 前 6 位 hex，其余脱敏）、`full_symbol`、`trade_date`、`name_presence`、`version_summary`；**不输出原始 name 值、完整 _id、凭据** |
| R17-006 | 预期 mutation | `expected_set_version_ops`、`expected_unset_name_ops`、`expected_update_docs`（V17-003 方程） |
| R17-007 | gate 结果 | 每个 gate（C17-201~205）pass/fail + 证据计数 |

**规模估计（任务要求 8）**：design 时点（2026-08-01）估计 `index_daily_quotes` 中 SW `.SI` akshare 候选约 **141,019 条观测**（31 个 SW L1 行业 × 约 4,549 个交易日；数量级估计，来源为 03-016 生产 universe 规模与交易日推算）。该估计**仅用于**评估批量规模、运行耗时与产物体积；**apply 前必须重跑 census 得到真实 `total_candidates`**；任何 gate 判定、批次规划、验证方程均使用真实 census 值，**绝不将 141,019 作为硬编码目标或阈值**。`expected_update_docs` 等预期计数一律来自 census 分类，不来自本估计。

### 3.6 Apply 详细设计（apply 模式 + `QuoteMetadataWriter`）

#### 3.6.1 `QuoteMetadataWriter`（govern_quote_metadata.py）

```python
class QuoteMetadataWriter:
    """真实 pymongo 生产写入器（仅限 tradingagents.index_daily_quotes 候选记录）。

    与 HistoricalRankingWriter 平行但允许真实 db；每个操作先过
    _assert_namespace（拒绝目标集合外的一切读写）。
    """
    COLLECTION = "index_daily_quotes"          # namespace: tradingagents.index_daily_quotes（固定，SPEC C17-101/任务要求 2）

    def __init__(self, db: Any) -> None:       # db 为真实 pymongo Database（或测试 mongomock）；不接受 None
        ...

    def _assert_namespace(self, collection: str | None) -> None:
        # collection 非 COLLECTION → 抛 NamespaceViolation（→ 停止，退出码 2）
    def update_one(self, filter: dict, update: dict, *, upsert: bool = False) -> Any:
        # 仅允许 COLLECTION；upsert 恒为 False（M17-002）
    def bulk_write(self, operations: list[Any], *, ordered: bool = False) -> Any:
        # 仅允许 COLLECTION；ordered=False（B17-002）
```

约束：
- 构造、`update_one`、`bulk_write` 全部先 `_assert_namespace`。
- `update` 只能含 `$set`/`$unset` 且键限 `version`/`name`（M17-001/M17-004）；代码层断言禁止其他键。
- 无 `replace_one`/`delete_one`/`insert`/`upsert`（M17-002）。

#### 3.6.2 apply 流程（函数级）

```text
main() --mode apply --yes --run-id <operator-chosen-id>
  ├─ conn = ConnLoader(); db = conn.load_db()                   # 失败 → 3
  ├─ census(db)                                                 # C17-201~205 全过才继续；任一 FAIL → 2
  │     total_candidates == 0 → no-op 退出码 0（C17-104）
  ├─ ids = census.candidate_ids（_id 列表，按 _id 升序，C17-105/B17-003）
  ├─ ckpt = CheckpointStore(report_dir, run_id).load()
  │        # run_id 取自 --run-id（生产显式指定；缺省自动生成不满足恢复语义，M2）
  │        # 该 run-id 已有 checkpoint → resume（最后成功 checkpoint）；无 → 全新 lineage（第 0 批）
  ├─ start_from = ckpt.batch_end_id if ckpt else None           # resume（B17-006）
  ├─ for batch in batches(ids, batch_size):                     # B17-001
  │     if start_from and batch[0] <= start_from: continue      # 跳过已 checkpoint 的批
  │     ops = [UpdateOne({"_id": id},
  │                       {"$set": {"version": 1}, "$unset": {"name": ""}},
  │                       upsert=False) for id in batch
  │             if needs_version(id) or needs_name_unset(id)]   # 已合规 id 不发写（M17-005）
  │     if not ops: 记录 matched=0 modified=0; save checkpoint; continue
  │     result = writer.bulk_write(ops, ordered=False)          # B17-002
  │     # stop-on-error（B17-005）：bulk_write 抛异常 → 有界重试 ≤2 次（瞬态）→ 仍失败 → 停止，checkpoint 保留
  │     ckpt.save({batch_seq, batch_start_id, batch_end_id,
  │                matched, modified, ts_utc})                  # B17-004；save 成功才进入下一批
  ├─ report = build_apply_report(...)   # R17-001~007 + matched/modified 累计 + stop_conditions_hit
  ├─ write_report(...); write .md; log_jsonl 每批审计（B17-007）
  ├─ scan_secrets(report 全文) → 命中 → 2
  └─ return 0 / 2 / 3
```

#### 3.6.3 批次 / 检查点 / 恢复（B17-001 ~ B17-007）汇总

| 编号 | 规则 | 设计落实 |
|---|---|---|
| B17-001 | batch_size 默认 500（1..1000） | `--batch-size`（C17-011）；每批至多 batch_size 条 update_one |
| B17-002 | 批内 `bulk_write(ordered=False)` | `QuoteMetadataWriter.bulk_write(ordered=False)`；操作彼此独立 |
| B17-003 | 候选按 `_id` 升序；`_id` 为稳定 resume key | census 阶段 `ids = sorted(candidate_ids)` |
| B17-004 | 每批写完后持久化 checkpoint | `CheckpointStore.save()`（JSONL，含 batch_seq/start_id/end_id/matched/modified/ts_utc） |
| B17-005 | stop-on-error；瞬态错误有界重试 ≤2 次 | bulk_write 异常 → 重试 ≤2 次（仅限连接/超时类瞬态）→ 仍失败 → 停止；不自动扩批/继续 |
| B17-006 | 恢复：从最后成功 checkpoint；恢复查询 = P ∧ `_id > batch_end_id` | `start_from` 跳过已 checkpoint 批；已修复记录分类为已合规并跳过（幂等收敛） |
| B17-007 | 审计日志每批追加 | `log_jsonl()` 每批 counts/errors/耗时 |

### 3.7 Verify 详细设计（verify 模式）

verify 为只读 re-census，复用同一谓词 `P`（C17-101），输出 verify report：

```text
main() --mode verify [--run-id <同 apply 的 run-id>]
  ├─ conn/db 加载（失败 → 3）
  ├─ pre_stats = 读取最近 census report（同 report-dir 下的 canonical `quote-governance-report.json`；供方程对照）
  │        # 建议复用 apply 的 --run-id 并按 §8 顺序执行：apply 与 verify 之间重跑 census/dry-run 会覆盖
  │        # canonical report → V17-006 对照失真（安全方向失败 EXIT_VERIFY=4）；按 runbook 顺序可规避
  ├─ post = re-census(db, P)（只读）
  ├─ V17-001: total_candidates == already_compliant + missing_version + nonconforming_version == name_present + name_absent
  ├─ V17-002: version_fix_needed == missing_version + nonconforming_version
  ├─ V17-003: expected_set_version_ops == version_fix_needed；expected_unset_name_ops == name_present；
  │           expected_update_docs == version_fix_needed + name_present − both_needed
  ├─ V17-004: post_total_candidates == pre_total_candidates（无增删）
  ├─ V17-005: post_version_conforming == post_total_candidates；post_name_absent == post_total_candidates
  ├─ V17-006: 累计 modified_count == expected_update_docs；累计 matched_count ≥ modified_count；
  │           受保护字段存在性计数 == pre 分布（OHLCV/provenance 原样）
  ├─ 任一 FAIL → EXIT_VERIFY=4，report 记录差异；全部过 → 0
  ├─ write_report + scan_secrets
  └─ return 0 / 4
```

verify 只读；禁止 `--yes` 语义（传入时忽略并提示）；不做任何写。

### 3.8 数据流/控制流图（汇总）

```text
census（只读）: stock_sector_info(RO, U 推导) + index_daily_quotes(RO, P 命中 + 分布)
   → gates C17-201~205 → 分类 → 候选 _id 列表 → census report
dry-run（只读）: census 结果 → 预期 mutation 计数 + 有界样本 → dry-run report
apply（写）:     census 候选 _id → 逐批 bulk_write(UpdateOne, ordered=False, upsert=False)
   → QuoteMetadataWriter(仅 index_daily_quotes) → checkpoint → apply report
verify（只读）:  re-census → V17-001~006 方程 → verify report
restore（独立批准，§3.9）: stock_sector_info(RO, l1_code→l1_name) → 按候选 full_symbol 重建 name → 回写
```

### 3.9 接口与数据结构（汇总）

| 接口 | 契约 | 位置 |
|---|---|---|
| `govern_quote_metadata.main(argv) -> int` | SPEC §3.1 | `govern_quote_metadata.py` |
| `build_predicate() -> dict` | SPEC §3.2（C17-101） | `govern_quote_metadata.py` |
| `derive_universe(db) -> set[str]` | SPEC §3.2（C17-102/103） | `govern_quote_metadata.py` |
| `run_census(db, P, U) -> CensusReport` | SPEC §4（C17-201~207 + 分类 + `_id` 列表） | `govern_quote_metadata.py` |
| `plan_mutation(census) -> DryRunReport` | SPEC §4（R17-001~007） | `govern_quote_metadata.py` |
| `apply_mutation(db, ids, batch_size, ckpt) -> ApplyReport` | SPEC §4（M17/B17） | `govern_quote_metadata.py` |
| `verify(db, P, pre_stats) -> VerifyReport` | SPEC §4（V17-004~006） | `govern_quote_metadata.py` |
| `ConnLoader.load_db() -> db` | C17-012 | `common.py` |
| `CheckpointStore.load/save` | B17-004/006 | `common.py` |
| `ReportWriter.write_report/log_jsonl` | C17-007/008 | `common.py` |
| `redact/scan_secrets` | C17-005 / SC-017-G0-1 | `common.py` |
| `QuoteMetadataWriter.update_one/bulk_write` | M17-001~007 | `govern_quote_metadata.py` |
| **restore_name（独立批准）** | F17-003：从 `stock_sector_info`（`l1_code→l1_name`）按候选 `full_symbol` 重建 quote 级 `name` 并回写 | **不属于本 runner**；仅定义语义，见 §3.9.1 |

#### 3.9.1 `name` 恢复（restoration）路径设计（F17-003，仅语义 + 批准门槛）

- 本 runner **不实现** `name` 恢复自动执行（RFC §3.2 非目标；SPEC F17-003）。
- 恢复操作**仅允许**在独立批准的 recovery 卡中执行，数据来源**仅限** `tradingagents.stock_sector_info`（`classify_system == "SW"` 的 `l1_code → l1_name` 映射，按候选 `full_symbol` 匹配，归一化规则同 `derive_universe`）。
- 恢复写入目标仍仅限 `tradingagents.index_daily_quotes` 候选记录，字段仅 `name`；同样要求 census 三重证据校验、dry-run 默认、checkpoint、stop-on-error、无自动回滚。
- 触发条件：仅当未来发现确有消费者依赖 quote 级 `name`（RFC §7 风险表）；当前审计显示无消费者（RFC §2.3）。
- 批准门槛：Pascal 显式授权 + 独立 RFC/SPEC/Design + Verify/Review PASS；本流水线（03-017）不预授权该操作。

### 3.10 持久化设计（对齐模板 §3.4）

| 存储对象 | 写入触发点（文件:函数/命令） | 写入字段子集 | 写入前过滤/校验 | 错误处理与回滚 |
|---|---|---|---|---|
| `tradingagents.index_daily_quotes`（候选记录） | `govern_quote_metadata.py:apply_mutation()` → `QuoteMetadataWriter.bulk_write(UpdateOne(..., upsert=False))`（仅 `--mode apply --yes`） | 仅 `version`（`$set 1`，缺失/不合规时）与 `name`（`$unset`，存在时）；其余字段绝不触碰（M17-004） | census C17-201~205 全过；mutation 谓词（MUTATE_VERSION/MUTATE_NAME）逐 id 判定；`_id` 定位，批内不重查 | bulk_write 失败 → 有界重试 ≤2 次 → 停止（B17-005），checkpoint 保留；无自动回滚/删除（F17-001）；修复后从 checkpoint 幂等恢复 |
| `data/rollout/index-daily-quote-governance/quote-governance-report.json/.md` | `common.py:write_report()`（各模式结束） | R17-001~007 字段集 + mode 专属（apply 的 matched/modified 累计；verify 的方程结果） | report 全文过 `scan_secrets`，命中 → SC-017-G0-1 | 写入失败 → 工具报错退出；历史 report 以时间戳副本保留，不覆盖（C17-007） |
| `data/rollout/index-daily-quote-governance/logs/quote-governance-*.log` | `common.py:log_jsonl()`（每批动作） | 结构化 JSONL（动作/耗时/计数/脱敏异常） | `redact()` 每个 record | 日志失败不阻断主流程（WARN 记录） |
| `data/rollout/index-daily-quote-governance/quote-governance-checkpoint-<run_id>.jsonl` | `CheckpointStore.save()`（每批成功后） | `{batch_seq, batch_start_id, batch_end_id, matched, modified, ts_utc}` | 仅由 apply 写入；命名带 run_id 与日期；新 run-id = 全新 lineage，复用同 run-id = 恢复（§3.3.4，M2） | save 失败 → 停止（同批失败处理）；不覆盖历史 |

测试替身：所有写路径在测试中用 mongomock + `tmp_path` report/checkpoint 文件；`QuoteMetadataWriter` 接受 mongomock db，测试断言 namespace 拒绝、无 upsert、字段白名单、幂等（第二次 modified=0）。

### 3.11 UI / 原型设计

无（CLI 工具）。

---

## 4. 实现计划（T3 Implement worker 按 §4.1 ~ §4.4 顺序实现）

### 4.1 Step 1 — 包骨架与共享组件

- [ ] `scripts/unified_data/quote_metadata_governance/__init__.py`
- [ ] `scripts/unified_data/quote_metadata_governance/common.py`（ConnLoader / ReportWriter / JSONL logger / CheckpointStore / redact / scan_secrets / 退出码常量 / resolve_report_dir / utc_now_iso）
- [ ] `skills/data/unified_data/tests/fixtures/quote_metadata_governance_fixtures.py`（fixture 骨架）

### 4.2 Step 2 — census + dry-run

- [ ] `govern_quote_metadata.py`：`build_predicate` / `derive_universe` / `run_census`（gates + 分类 + `_id` 列表）/ `plan_mutation`（dry-run report）
- [ ] `test_quote_metadata_governance.py`：谓词、universe、gates、分类、dry-run 计数矩阵

### 4.3 Step 3 — apply + verify

- [ ] `govern_quote_metadata.py`：`QuoteMetadataWriter` / `apply_mutation`（批次/checkpoint/resume）/ `verify`（V17 方程）
- [ ] `test_quote_metadata_governance.py`：幂等、批次分界、stop-on-error、恢复、方程、namespace、无 upsert

### 4.4 Step 4 — 全量验证与收尾

- [ ] 运行全部新单测（1 个 test 文件全矩阵）
- [ ] `python3 -m scripts.unified_data.quote_metadata_governance.govern_quote_metadata --help` 可运行（dry-run 路径，零真实 I/O）
- [ ] `git diff --check HEAD` 通过；03-017 相关改动仅限 §3.1.1 allowlist 文件（路径过滤归属；共享树其他 dirty 不计）

---

## 5. 测试策略

### 5.1 单元测试（mongomock + 显式 fixture，零真实 I/O）

| 覆盖点 | 用例（SPEC §8 编号映射） |
|---|---|
| 谓词 | `build_predicate` 精确匹配 `.SI` 后缀 + akshare；反例（`.SH`/`.SZ`/无后缀/非 akshare）不命中 |
| universe | `derive_universe`：带/不带 `.SI` 后缀的 `l1_code` 归一化一致；空 U 触发停止（C17-103） |
| gates | 构造反例（market≠CN、period≠daily、P 内 full_symbol ∉ U）→ 各 gate FAIL + 退出码 2；gate 顺序（C17-207） |
| 分类 | missing/nonconforming/already_compliant/name_present/both_needed 全覆盖；分类恒等式（V17-001/002） |
| dry-run | R17-001~007 字段齐备；有界样本每类 ≤5、`id_prefix` 6 位 hex、不含 name 值/完整 `_id`/凭据；预期计数方程（V17-003） |
| mutation | 幂等（apply 两次，第二次 modified=0）；只改 version/name；`_id` 定位；无 upsert（`upsert=False`）；字段白名单断言（非 version/name 键 → 抛错） |
| 批次 | batch_size 分界（1/500/1000）；ordered=False；stop-on-error（注入 bulk_write 异常 → 重试 ≤2 → 停止）；checkpoint 写后恢复（模拟中断 → 恢复 → 收敛） |
| 方程 | V17-001~003（pre）、V17-004~006（post）在 fixture 上成立 |
| namespace | `QuoteMetadataWriter` 对非 `index_daily_quotes` collection 抛 `NamespaceViolation` |
| secrets | `redact`/`scan_secrets`：连接值、URI 凭据段、token 命中 → SC-017-G0-1 |
| ConnLoader | 五键组件形态；缺失任一必需键 fail-fast（退出码 3，仅键名）；无 URI/prefix 分支；fingerprint 无连接值/无 username 信息 |

### 5.2 显式零写 dry-run 测试矩阵（任务要求 6）

> 以下矩阵必须全部在 mongomock fixture 上执行，**断言零写**（`db` 为 mongomock，测试结束对比快照无任何文档变化；apply 场景仅覆盖幂等与恢复语义，**不**作为真实 DML 测试）。

| # | 场景 | fixture | 预期退出码 | 零写断言 |
|---|---|---|---|---|
| D1 | `--mode census` 全过（all compliant） | `make_mixed_quote_docs()` 纯合规 | 0 | 集合计数不变 |
| D2 | `--mode census` gate FAIL（market≠CN） | 注入 market="HK" 候选 | 2 | 无写；report 含证据分布 |
| D3 | `--mode census` gate FAIL（P 内 full_symbol ∉ U） | 注入非 universe code | 2 | 无写；report 含反例 |
| D4 | `--mode census` 空候选 | 空集合 | 0 | "nothing to do" |
| D5 | `--mode dry-run` 混合数据（missing/nonconforming/name_present/both_needed） | `make_mixed_quote_docs()` | 0 | 计数方程 V17-001~003 成立；样本合规 |
| D6 | `--mode dry-run` gate FAIL 前置（同一反例） | 同 D3 | 2 | 无写 |
| D7 | `--mode apply` 缺 `--yes` | 混合数据 | 0（按 dry-run 提示） | **零写**（C17-004：缺 `--yes` 视为 dry-run） |
| D8 | `--mode apply --yes` 幂等（首次） | 混合数据（fixture 内 mongomock） | 0 | 写仅 version/name；受保护字段存在性不变 |
| D9 | `--mode apply --yes` 幂等（第二次） | 同上（重跑） | 0 | matched>0 且 modified=0；计数方程全过 |
| D10 | `--mode verify` post 全过 | apply 后 fixture | 0 | 只读；集合计数不变 |
| D11 | `--mode verify` 方程 FAIL（人为破坏一条 name） | apply 后注入 name | 4 | report 记录差异 |
| D12 | `--mode apply --yes --run-id <id>` 中途失败 → 恢复 | 注入 bulk_write 异常 | 2（停止）→ 修复后 0 | checkpoint 保留；**同一 `--run-id` 重跑**从 `batch_end_id` 恢复收敛；换新 run-id 则从第 0 批重新开始（全新 lineage） |

### 5.3 集成测试

- census → dry-run → apply → verify 全链路在 mongomock fixture 上跑通；report/audit/checkpoint 产物存在且可读。
- 规模估计 sanity：fixture 构造 ~141,019 条候选规模（31 code × 4,549 日，可缩减抽样 31 × 100 日）验证批次/checkpoint 吞吐与恢复语义；**仅作为测试规模参数，不验证真实生产数量**。

### 5.4 回归范围

- 03-016 工具族 `test_sector_ranking_rollout_*.py`、03-015 `test_sector_ranking_history.py`（51/51）必须保持 PASS（实现只新增文件，不改既有文件 → 回归失败即视为越界）。

### 5.5 手工验证（不可自动化项）

- 真实生产集合的 census 分布：仅 production activation runbook（§8）由 Pascal 显式触发后验证。
- `stock_sector_info` 真实 `l1_code` 归一化覆盖（OQ-017-1）：T2 后真实 census 复核；apply 前 re-census 时确认。

---

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| 候选集误纳非 SW 数据（未来其他 writer 产生 `.SI` 记录） | 三重证据校验（C17-201~205）+ 权威 universe 子集（C17-203）fail-closed | 任一 FAIL 停止，报告证据分布（RFC §7） |
| 某记录 `_id` 重复/不可排序导致 resume 错乱 | `_id` 唯一性由 Mongo 保证；resume 用 `_id > batch_end_id` | 排序异常即停止，人工介入 |
| 下游消费者依赖 quote 级 `name` | 已审计现行读路径均不消费 `name`（RFC §2.3）；显示名来自 `stock_sector_info.l1_name` | 若发现新消费者，停止并在独立批准的 restore 操作中按 `stock_sector_info` 重建（§3.9.1） |
| 批处理中途失败导致部分记录已更新 | checkpoint + 幂等分类；恢复从最后成功批次继续 | 失败现场保留，人工排查后重跑（F17-004） |
| 误删/误改 provenance 字段 | mutation 仅 `$set {version}` / `$unset {name}`，`_id` 定位，字段白名单断言；验证方程覆盖受保护字段存在性（V17-006） | 任何越界字段变更即停止（M17-004） |
| 生产 DML 执行时机过早 | 强制 Verify/Review 门槛 + Pascal 显式触发（§8） | 未通过门槛前 runner 不执行生产 DML |
| 规模估计与真实 census 偏差（141,019 为估计） | apply 前必须重跑 census 得到真实计数；估计不参与任何门禁判定 | 无（估计仅影响评估，不影响正确性） |
| 身份泄露（连接值/密码进日志） | `redact()` + `scan_secrets` + 静态扫描 | SC-017-G0-1 停止；rotate 后重跑 |

---

## 7. 交接给实现者

### 7.1 必须遵守

1. **只新增 §3.1.1 allowlist 文件（共 5 个）**；禁止修改 §2.2 冻结清单任何文件（含 `conftest.py`、`scripts/unified_data/__init__.py`、03-016 工具族、03-015/P3-A、writer 代码、模板、`.env`/config）。
2. **T3 零真实 I/O**：全部测试 mongomock + 显式 fixture；任何工具不得在 T3 触发真实连接/DDL/DML/Provider/回填/cron/Git。
3. **dry-run 默认、`--mode apply` 显式、`--yes` 确认**（C17-004）；缺 `--yes` 的 `apply` 按 dry-run 处理并提示。
4. **退出码严格按 SPEC C17-002**（0/1/2/3/4）；与 audit_rollout.py 的映射不同，以 SPEC 为准。
5. **secrets 纪律**：任何输出不得回显连接值（host/port/username/password/db 值）或 token；出现含凭据 URI / `*TOKEN*` / `*SECRET*` 即视为泄露（SC-017-G0-1）；`redact()` 与 `scan_secrets()` 必须应用于全部 report/log。
6. **写仅限 `tradingagents.index_daily_quotes` 候选记录**：`QuoteMetadataWriter._assert_namespace`；无 upsert（`upsert=False`）、无 replace/delete/insert、无 DDL。
7. **mutation 字段白名单**：仅 `$set {version: 1}` / `$unset {name: ""}`；其他字段绝不触碰（M17-004）；代码层断言禁止非白名单键。
8. **不自动 retry（超出有界 2 次）/ rollback / drop / 删除**：任何失败 → 停止 + report；修复后由 Pascal 显式重跑（幂等收敛）。
9. **规模估计纪律**：141,019 仅为设计时点估计，**不得硬编码为阈值或目标**；所有计数/判定来自 apply 前真实 census。
10. **候选 `_id` 固化**：apply/verify 使用 census 固化的 `_id` 列表，批内不重新用谓词查询（C17-105）。
11. 完成后：验收标准全 PASS → `kanban_complete(status="done", summary=..., metadata={...})`；任何 FAIL → `kanban_block(reason="<哪条验收 FAIL + 期望 vs 实际>")`。残余风险（如真实生产 census 分布未知）属于 done 的 summary/metadata，**不构成 block 理由**（P-5）。
12. **run-id 纪律（M2）**：`--mode apply` 必须显式 `--run-id <operator-chosen-id>`；resume 复用同一 run-id（新 run-id = 全新 checkpoint lineage，复用 = 从最后成功 checkpoint 恢复，B17-006）；自动生成 run-id 仅限一次性只读模式。

### 7.2 可自行判断

- `common.py` 内部 helper 命名、report `.md` 摘要格式（内容须覆盖结论/关键统计/停止条件）。
- `quote_metadata_governance_fixtures.py` 中 fixture 函数命名与拆分方式（须覆盖 §5.2 矩阵全部场景）。
- 单测文件内部组织（可用 pytest 参数化减少重复）。
- `CheckpointStore` 的文件读取缓存策略与 resume 判定细节（不违反 B17-004/006）。

### 7.3 遇到以下情况退回 Principal

- 发现必须修改任何冻结文件（§2.2）才能完成工具。
- 发现需要新增第三方依赖（SPEC §10：仅 pymongo/motor/mongomock 既有依赖）。
- 发现 SPEC 契约在真实 pymongo 下不可实现（如 `bulk_write(ordered=False)` 语义差异）。
- 发现 `stock_sector_info` 无法推导权威 universe `U`，或 `index_daily_quotes.full_symbol` 与 `l1_code` 归一化 join 不成立（需重新定义权威来源）。
- 发现 `MONGODB_*` 身份权限不足且需创建账号/角色（需单独授权）。

---

## 8. Production activation runbook（Review PASS 后执行）

> **授权边界（任务要求 7 / RFC A-017-2）**：本 runbook 定义的**唯一被授权的未来生产写动作** = 对 `tradingagents.index_daily_quotes` 候选记录执行字段级 `$set {version:1}` / `$unset {name:""}`。其余一切动作（服务重启、同步、调度、03-016 Gate-3/Gate-4、DDL、无关集合写入、`name` 恢复）均不在授权范围内（X17-001~006）。
>
> **执行前置（强制）**：本流水线 **Implement → 独立 Verify（yquanttester）→ 独立 Review（yquantreviewer）全部 PASS 后**，由 Pascal 显式触发生产 runner 执行卡；任何阶段未过，runner 不创建、不执行（RFC §4.2/§9.2 A-008）。执行卡 body 必须引用 RFC §5、SPEC §3、本设计 §3/§8 对应章节。
>
> **run-id 纪律（M2）**：本 runbook 全部命令使用**显式且不可变**的 `--run-id <operator-chosen-id>`（如 `20260801-gov-01`），census/dry-run/apply/verify 复用同一值。**新 run-id = 全新 checkpoint lineage**（从第 0 批开始，忽略既有 checkpoint）；**复用同一 run-id = 从最后成功 checkpoint 恢复**（resume，B17-006）。生产 apply 绝不依赖自动生成 run-id（`qg-<uuid12>`）——那会使中断后的重跑开新 lineage、无法 resume。

### 8.1 阶段 0：re-census（apply 前必做）

```bash
# 只读；产出 census report，获得真实 total_candidates 与分类计数
# --run-id 建议与后续 apply/verify 复用同一值（同 lineage 的 report/checkpoint 命名一致）
python3 -m scripts.unified_data.quote_metadata_governance.govern_quote_metadata \
  --mode census --run-id <run-id> --report-dir data/rollout/index-daily-quote-governance
```

Pascal / 独立 Verify 复核：`stop_conditions_hit` 为空、`checks` 全 PASS、`total_candidates` 与设计时点估计（~141,019）数量级一致（**仅作 sanity，不作硬性阈值**）、无 secrets。

### 8.2 阶段 1：dry-run（零副作用）

```bash
python3 -m scripts.unified_data.quote_metadata_governance.govern_quote_metadata \
  --mode dry-run --run-id <run-id> --report-dir data/rollout/index-daily-quote-governance
```

复核：预期 mutation 计数（V17-003 方程）、有界样本脱敏合规、无 secrets。

### 8.3 阶段 2：apply（Pascal 显式触发，唯一生产写）

```bash
python3 -m scripts.unified_data.quote_metadata_governance.govern_quote_metadata \
  --mode apply --yes --batch-size 500 --run-id <run-id> \
  --report-dir data/rollout/index-daily-quote-governance
```

- `--yes` 缺省视为 dry-run（C17-004），不产生任何写。
- `--run-id <run-id>` 为**不可变标识**：首次 apply 建立 checkpoint lineage；**中断后的 resume = 复用同一 `--run-id` 重跑本命令**，从最后成功 checkpoint 恢复（B17-006）。更换 run-id 视为全新 lineage，将从第 0 批重新开始（幂等收敛、数据安全，但放弃恢复点、全量重扫）。
- 中途失败 → 停止；修复后以**同一 `--run-id`** 从最后 checkpoint 幂等重跑（不自动回滚，F17-001）。

### 8.4 阶段 3：verify（写后只读）

```bash
python3 -m scripts.unified_data.quote_metadata_governance.govern_quote_metadata \
  --mode verify --run-id <run-id> --report-dir data/rollout/index-daily-quote-governance
```

独立 Verify 判定（yquanttester）：V17-001~006 全部成立；`post_version_conforming == post_total_candidates`；`post_name_absent == post_total_candidates`；受保护字段存在性计数与 pre 分布一致（V17-006）；无 secrets。

> verify 复用 apply 的 `--run-id` 并按 §8.1→§8.4 顺序执行：verify 读取 canonical `quote-governance-report.json` 作 pre_stats；若在 apply 与 verify 之间重跑 census/dry-run 会覆盖该文件 → V17-006 对照失真（安全方向失败 EXIT_VERIFY=4）。按本 runbook 顺序可规避。

### 8.5 失败处理

任何阶段失败 → 暂停，上报 Pascal；**不自动** retry（超出有界 2 次）、不扩批、不反向操作（RFC PT/授权边界）。**apply 中断后的恢复 = 以同一 `--run-id` 重跑 §8.3 apply 命令**（从最后成功 checkpoint 恢复，B17-006）；如需放弃恢复点重新开始，才更换新 `--run-id`（全新 lineage，幂等收敛）。修复路径：gate FAIL → 人工核对证据分布后修复数据或缩范围；连接失败 → 检查 `MONGODB_*` 键与网络；verify FAIL → 按报告差异排查（绝不手动删除/回写）。`name` 恢复仅经 §3.9.1 独立批准路径执行，**不属于**本 runbook。

---

## 9. 声明

本设计涉及的板块/行业数据为辅助研究数据，不构成交易指令或投资建议。

本设计不修改 RFC-03-015 / SPEC-03-015 / DESIGN-03-015、03-016 工具族、03-014 P3-A 任何文件，不修改 writer 代码，不修改文档模板。所有引用以交叉引用方式继承，冲突时以 RFC-03-017 / SPEC-03-017 为准。

本设计定义 runner 的**实现与执行设计**，不构成任何真实生产动作的已执行声明；所有真实 DML 仅在独立 Verify/Review PASS 后由 Pascal 显式触发 production activation 执行卡（§8）。

---

## 10. 闭包账本（Closure Ledger）

> 本账本为 03-017 文档闭包修订（kanban `t_ae320c08`）的可审计汇总，供替代评审者判断有界终态。仅记录元数据与交叉引用事实，不改变任何契约语义。

### 10.1 Canonical C17 编号（唯一权威映射）

| 编号 | 语义 | 权威出处 |
|---|---|---|
| C17-001 | CLI 模式语义（`--mode`，census/dry-run/apply/verify 单 CLI） | SPEC §3.1；本文档 §3.2/§3.4.1 |
| C17-002 | 退出码 0/1/2/3/4 | SPEC §3.1；本文档 §3.3.1 |
| C17-103 | 空权威 universe → EXIT_STOP=2 | SPEC §3.2；本文档 §3.4.2 |
| C17-201 ~ C17-205 | 串行 census 证据门禁（fail-closed） | SPEC §3.3；本文档 §3.4.3 |
| C17-206 | 观察项（不阻断） | SPEC §3.3；本文档 §3.4.3 |
| C17-207 | 串行 gate 顺序 | SPEC §3.3；本文档 §3.4.3 |
| C17-301 ~ C17-304 | 合规分类 | SPEC §3.4；本文档 §3.4.4 |

废弃编号（历史，不再使用）：`C17-001` 旧指「U 非空前置」（现为 C17-103）；`C17-003 ~ C17-007` 旧指证据门禁（现为 C17-201 ~ C17-207）。

### 10.2 M2 run-id / resume 基线

- `--run-id` = operator 选择的**不可变标识**；**新 run-id = 全新 checkpoint lineage**；**复用同一 run-id = 从最后成功 checkpoint 恢复**（§3.3.4 / §8，B17-006）。
- 生产 apply / 中断后 resume 必须复用同一 `--run-id`；自动生成 run-id（`qg-<uuid12>`）不满足恢复语义，仅限一次性只读模式（§3.4.1）。

### 10.3 源元数据基线（Source Metadata Baseline）

| 文档 | 文档修订 | 引用契约基线 | 参考关系 |
|---|---|---|---|
| SPEC-03-017 | V0.2（不变） | RFC-03-017 V0.2 | 可执行契约；来源 RFC |
| RFC-03-017 | V0.3（元数据修订） | SPEC-03-017 V0.2 | 本设计来源 RFC 之一 |
| DESIGN-03-017 | V0.3（本次元数据修订） | RFC-03-017 V0.2、SPEC-03-017 V0.2 | 本文档 |

版本语义：RFC-03-017 / DESIGN-03-017 的 V0.3 仅为文档元数据修订（指针修复 + 本账本），契约内容与 V0.2 一致；SPEC-03-017 保持 V0.2，不因下游指针修复而升级（无版本级联）。

### 10.4 无语义变更声明

本次闭包修订**不改变任何语义 runner / mutation 行为**：候选谓词 `P`（C17-101）、fail-closed 门禁（C17-201~207）、幂等 mutation（M17-001~007）、批次/检查点/恢复（B17-001~007）、验证方程（V17-001~006）、退出码（C17-002）、授权边界（A-017-2 / X17-003）均保持 SPEC-03-017 V0.2 契约不变。本次修订仅修改本文档与 RFC-03-017 两个文件；无代码、测试、config、Mongo、runner、CLI、服务、cron、Git 操作。

---

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.3 | 2026-08-02 | 闭包修订（kanban `t_ae320c08`）：来源 SPEC 指针 V0.1 → V0.2（契约基线同步）；新增 §10 闭包账本（canonical C17 ID / M2 run-id-resume / 源元数据基线 / 无语义变更声明）。**文档修订 V0.3 ≠ 引用契约基线**（RFC-03-017 V0.2 / SPEC-03-017 V0.2）；仅元数据修正，无任何语义 runner/mutation 行为变化；SPEC-03-017 不因下游指针修复而升级（无版本级联） | YQuant-Codex-Principal |
| V0.2 | 2026-08-01 | P0 文档修正（kanban `t_c3f567eb`，M2）：补全 `--run-id` CLI 契约（§3.4.1）与 checkpoint lineage 语义（§3.3.4：新 run-id = 全新 lineage；复用同一 run-id = 从最后成功 checkpoint 恢复）；§8 production activation runbook 全部命令显式携带 `--run-id <operator-chosen-id>`，resume 复用同一 run-id；verify 预统计读取说明（§3.7/§8.4）；规模估计算术修正 141,021 → 141,019（31 × 4,549）；来源 RFC 更新为 V0.2 | YQuant-Codex-Principal |
| V0.1 | 2026-08-01 | 初始创建（Full Flow T2，kanban `t_de0b4579`）：单 runner 四模式（census/dry-run/apply/verify）文件级设计、T3 allowlist（5 文件）、零写 dry-run 测试矩阵（D1~D12）、production activation runbook 与授权边界、`name` 恢复路径语义 | YQuant-Codex-Principal |
