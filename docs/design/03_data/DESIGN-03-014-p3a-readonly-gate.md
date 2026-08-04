# DESIGN-03-014: P3-A PR-0 / PR-1 / PR-2 受控只读 Gate — 执行编排与证据设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-08-04 |
| 最后更新 | 2026-08-04 |
| 版本号 | V0.3 |
| 来源 RFC | RFC-03-014-p3a-readonly-gate（V0.4） |
| 来源 SPEC | SPEC-03-014-p3a-readonly-gate（V0.3） |
| 关联 Design | DESIGN-03-014（Phase 3 主设计 V0.33，§15.x T4 preflight 工具链）；历史 DESIGN-03-014-p3a-sector-provider-activation（fake-only，**不得重新激活**，本卡不继承其执行授权） |
| 目标模块 | t4_preflight（`scripts/t4_preflight/`）+ unified_data providers（`skills/data/unified_data/providers/`） |
| 适配 Agent | YQuant-Developer-Engineer（T3 controlled execution / R1 后 developer Fix 卡）、YQuant-Test-Engineer（T4 Verify） |
| 设计阶段约束 | 本卡零真实 I/O；仅静态读取/本地 import/AST；唯一允许新增文件为本 Design |

---

## 1. 执行摘要（结论先行）

本 Design 将 T1 RFC/SPEC 定义的 **PR-0（凭证源可用性审计）→ PR-1（Mongo 只读预检）→ PR-2（有界 name_em smoke）** 三 Gate 串行链落为**受控只读 Gate 的精确编排**（V0.1 为一次性执行卡；R1 修订后 §7 改为 developer Fix → fresh Verify → Review → one-call PR-2 continuation，见 §2.6）。关键结论：

1. **PR-0 安全实现已存在且可复用**：`scripts/t4_preflight/audit_secret.py` + `secrets.py::SecretVerifier` 是唯一 sanctioned 实现。其数据结构 `SecretProbeResult` **结构上无法携带值**（仅 source_name + 四个布尔），探测方法只产出 boolean，值永不进入日志/print/YAML——满足「不读 value、不泄漏 key existence beyond approved boolean」。
2. **PR-1 执行入口为 `PreflightRunner`**（`scripts/t4_preflight/mongo_client.py`），`PortfolioMongoLoader` 仅作**五键组件语义参考**，不承担 ping/listCollections（其公开面为 upsert/load 写方法，无只读预检方法）。`mongo_calls ≤ 2` 由「ping + list_collection_names」两个 allowlist 命令计数得出；`write_operations = 0` 由命令级 allowlist 结构性保证。
3. **PR-2 执行入口必须固定为 `AKShareSectorClient`（name_em-only）**：`get_sector_ranking(sector_type="industry")` 单次调用 `stock_board_industry_name_em()`。历史 `smoke_sector.py` / `provider_client.py::fetch_sector_snapshot` 的 `cons_em` 路径**确认存在且被本链禁止**（代码证据：`provider_client.py:295` `fn_name="stock_board_industry_cons_em"`）。
4. **T3 证据以 stdout 优先**；PR-0/PR-1 复用既有 CLI（产出 redacted YAML 到 smoke_reports 允许路径）；PR-2 因历史 CLI 含 cons_em 路径不可用，使用 name_em-only 内联片段，输出 redacted YAML 到 stdout（可选的 `/tmp` 临时文件完成后删除）。
5. **T4 Verify 分工**：离线可复验项（报告 schema、账本、命令 trace、静态 grep、git diff、/tmp 残留）由 T4 独立执行；**PR-2 单次预算请求绝不重放**，T4 仅审计 T3 redacted evidence。
6. **R1 状态更新（2026-08-04）**：T3（`t_81432128`）已执行 PR-0（`CONDITIONAL_AUTHORIZED`，evidence 逐 key 记录不合规）与 PR-1（`mongo_calls=2`、`write_operations=0`，三张基线集合存在）；**PR-2 未执行（actual_calls=0）**；PR-1 **不可重放**。详见 §2.6。

**Gate pass 含义**：PR-0 pass = 五键可加载（仅可用性，不授权读取值）；PR-1 pass = tradingagents 只读可达 + **三张 designated baseline 集合 presence 可观测（存在即预期基线，非 FAIL；R1）** + 零写入证明；PR-2 pass = name_em 单次返回非空 + 字段匹配 ≥90% + 零持久化。**任一 pass 均不等于生产激活、数据入库或可交易信号**。

**R1 修订要点（2026-08-04，详见 §2.6）**：① 三集合（`03_data_ud_market_sector_snapshot` / `03_data_ud_stock_capital_flow` / `03_data_ud_market_sentiment_snapshot`）明示为 **designated historical baseline**，presence 非 PR-1 FAIL、禁止枚举陌生集合名；② PR-0 外部输出收敛为 single aggregate verdict + generic source-kind + generic error-class（禁止逐 key 名称/状态/password marker/路径）；③ 既有两份 gitignored evidence 为不合规本地工件，developer Fix 仅删除/替换为合规聚合版；④ PR-1 不可重放，PR-2 预算未消耗，仅 Fix+Verify+Review 通过后另立 one-call continuation；⑤ file-declared / runtime env absent = conditional，非 secret 值有效性或生产授权。

**R2 修订要点（2026-08-04，详见 §2.7）**：Pascal 范畴裁定 `name_em` 实时板块排行移出 Phase 3 实现/生产验证目标——PR-2 预算**永久废弃**（不因 scope removal 留作后门），one-call continuation **不再创建**；`t_55d44505` / `t_81432128` 标记 superseded / historical evidence；**禁止**为 name_em 新建 Provider recovery / 替代 endpoint / 实时 refresh / 任何 live retry；P3-A 仅保留盘后/历史、按 trade_date 可复现的 sector read-path 验证（消费既有历史集合/物化数据）。PR-0/PR-1 契约保持有效（历史只读预检证据仍有效，不重放）；PR-2 执行设计与编排段落整段标注 out-of-scope，保留为历史。

---

## 2. 静态核验事实（当前代码入口，2026-08-04 本卡核验）

> 本节省略分析过程，直接给出 T3/T4 可依赖的已核验事实。所有路径相对 repo 根 `/home/pascal/workspace/yquant-investment`。

### 2.1 环境与依赖（离线核验）

| 项 | 值 | 证据 |
|---|---|---|
| 锁定 venv | `.venv/bin/python`（Python 3.11/3.12 pyc 共存，以运行解释器为准） | `.venv/bin/python` 存在 |
| akshare | 1.17.54 | `pip list` |
| pymongo | 4.17.0 | `pip list` |
| python-dotenv | 1.2.2 | `pip list` |
| pandas | 3.0.3 | `pip list` |
| 包结构 | `scripts/` 为常规包（`scripts/__init__.py` 存在）；`skills/` 为 PEP 420 namespace 包（无 `skills/__init__.py`，`skills/data/__init__.py` 存在），`skills.data.unified_data.providers` 可自 repo 根导入（`__pycache__` 有历史导入证据） | 目录/文件检查 |

### 2.2 PR-0 入口核验

| 事实 | 证据 |
|---|---|
| 唯一候选来源 `skills/.env`；候选键五枚 `MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE` | `config.py::SKILLS_ENV_PATH`、`CANDIDATE_ENV_FILES=("skills/.env",)`、`CANDIDATE_SECRET_KEYS` |
| `SecretVerifier` 方法面：`probe_file`（仅 `is_file`，dry-run）、`probe_file_live`（+ `os.access(R_OK)`）、`probe_env`（live 时 `os.getenv(key) is not None`，值即刻丢弃）、`probe_env_in_file`（live 时 `read_text` + `f"{key}=" in text` 子串判断，布尔 only） | `secrets.py` L56-192 |
| `SecretProbeResult` 字段仅 `source_name/file_exists/file_readable/key_declared/is_loadable`，无值字段 | `models.py` L22-30 |
| CLI：`python -m scripts.t4_preflight.cli audit-secret [--live-read] [--output-dir ...] [--timeout ...]`；无 `--apply/--force/secret` 参数 | `audit_secret.py::build_arg_parser` |
| 报告：`audit-secret-YYYYMMDD.yaml` 写 `docs/rfc/03_data/smoke_reports/`（默认 output-dir）+ 打印 stdout | `audit_secret.py::run_audit` |
| exit 语义：0=authorized / 1=conditional_authorized / 3=unauthorized；2=报告写失败 | `audit_secret.py::run_audit` |

### 2.3 PR-1 入口核验

| 事实 | 证据 |
|---|---|
| `PortfolioMongoLoader(config: Optional[dict] = None)`：五键组件语义参考；公开面 = `upsert_*`/`load_all`/`load_trade`/`close`（**写路径**）；`_get_client()` 私有构造 URI（authSource=admin）；**无公开 `ping`/`list_collection_names`** | `skills/data/data-pipeline/scripts/loaders/mongodb_loader.py` L17-62 |
| `PreflightRunner(resolver: LegacyConfigResolver \| None = None)` → `run_preflight(*, live: bool = False, timeout: int = 3) -> MongoPreflightResult`；流程 = `resolve(live=True)` → `build_client(live=True, timeout=3)`（组件式 `MongoClient(host, port, username, password, authSource=MONGODB_DATABASE, serverSelectionTimeoutMS=3000)`）→ `admin.command("ping")` → `db.list_collection_names()` → P3 集合比对 → `close()` | `mongo_client.py` L607-718 |
| `MongoPreflightResult.connectivity ∈ {success, dns_failure, timeout, auth_failure, env_missing, dry_run, skipped}`；`p3_collections_found` 为与 `P3_BUSINESS_COLLECTIONS` 交集（**现状代码字段；R1 契约要求 Fix 后外部 evidence 改为 `baseline_collections`/`baseline_unexpected` 语义，见 §2.6/§5.5**） | `models.py` L49-60、`mongo_client.py` |
| exit 映射：env_missing→3、dns/timeout/auth→2、p3_collections_found 非空→2、collections=None（list 未授权）→1、success→0；dry-run→0（信息性）（**现状代码映射；R1 裁定三集合 presence 非 FAIL，developer Fix 需按 §2.6 调整 external evidence 与 verdict 语义**） | `preflight_mongo.py::_verdict_for` L92-114 |
| 命令 allowlist（只读）：`admin.command("ping")` + `list_collection_names()`（+ 意外集合存在时 `options()` + `close()`）；禁止 find/aggregate/count/watch/DDL/DML | `mongo_client.py` 模块 docstring、`config.py::PREFLIGHT_MAX_OPERATIONS=4` |
| CLI：`python -m scripts.t4_preflight.cli preflight-mongo [--live-read] [--output-dir ...] [--timeout ...]`；无 URI 参数 | `preflight_mongo.py::build_arg_parser` |

### 2.4 PR-2 入口核验

| 事实 | 证据 |
|---|---|
| `AKShareSectorClient.__init__(self, *, timeout: float = 30.0)`（keyword-only）；`get_sector_ranking(sector_type="industry")` → `_call_name_em("industry")` → 惰性 `import akshare` → `ak.stock_board_industry_name_em()`；`get_sector_snapshot(sector_code, sector_type="industry")` 同一响应内存过滤（**不产生第二次网络调用**） | `skills/data/unified_data/providers/sector_client.py` L203-267 |
| `sector_type="concept"` 分支调用 `stock_board_concept_name_em`；其他值 → `ProviderError`。T3 **只允许 `"industry"`** | 同上 L227-250 |
| 异常分类 `_raise_classified`：`ProviderUnavailableError`（timeout/connection/network/eof/ssl/tls/certificate/disconnect/reset/broken pipe 关键词、isinstance ConnectionError/TimeoutError、type 名 sslerror/tlserror）；否则 `ProviderError`；endpoint 在已装 akshare 中缺失 → `ProviderUnavailableError` | `sector_client.py` L167-200、L240-244 |
| `skills/data/unified_data/exceptions.py`：`ProviderUnavailableError(UnifiedDataError)`、`ProviderError(UnifiedDataError)` 已导出 | exceptions.py L38-42 |
| 12 列 expected（离线源码验证、docstring 冻结）：`排名/板块名称/板块代码/最新价/涨跌额/涨跌幅/总市值/换手率/上涨家数/下跌家数/领涨股票/领涨股票-涨跌幅` | `sector_client.py` L214-219、SPEC F-PR2-006 |
| 匹配阈值：≥0.90 pass / 0.70-0.90 conditional / <0.70 fail | `config.py::MATCH_RATIO_PASS/CONDITIONAL` |
| **历史 cons_em 路径（本链禁止）**：`scripts/t4_preflight/smoke_sector.py` live-read 两次调用（`fetch_sector_snapshot` → `stock_board_industry_cons_em(BK0489)` + `fetch_sector_ranking` → name_em）；`provider_client.py:295` `fn_name="stock_board_industry_cons_em"` | `smoke_sector.py` docstring L6-14、`provider_client.py` L283-313 |
| 主 DESIGN §15.14.2 endpoint 表仍列 `cons_em`/`rank_em`（V0.2 前内容）——**本链以 P3-A RFC/SPEC V0.2 裁定为准**：`rank_em` 不存在、`cons_em` 返回成分股列表非板块级主源、`name_em` 为共享主 endpoint | DESIGN-03-014 §15.14.2；RFC-03-014-p3a-readonly-gate §4.2 |
| 账本 `LedgerBlock`：`provider_attempts/actual_calls/retry_count/fallback_count/mongo_calls/write_operations` | `models.py` L160-192、`config.py::LEDGER_FIELDS` |

### 2.5 历史报告格式基线（evidence 对齐用）

- `preflight-mongo-YYYYMMDD.yaml`（dry-run 样例）：`preflight_mongo.{generated_at, live_read, connectivity, latency_ms, collections, p3_collections_found, warnings, detail}` + `overall.verdict`。
- `smoke-sector-YYYYMMDD.yaml`（dry-run 样例）：`capability/provider/smoke_at/test_target/date_range/preflight` + `connectivity/auth/permissions/field_mapping/data_sample/vs_fixture/overall` +（V0.16 起）`ledger`。
- **注意**：现行 `preflight_mongo.py` 的 YAML **不输出 `ledger` 块**（`LedgerBlock` 仅挂在 `SmokeReport`）。PR-1 的 `mongo_calls`/`write_operations` 记账由 §5.3 定义的外层命令级审计补齐。

### 2.6 R1 冻结事实与 Pascal 裁定（2026-08-04）

> 本卡为**契约/文档 amendment**。以下事实来自已执行 T3（`t_81432128`）与 Pascal 裁定，本卡不重跑任何 live evidence。仅可 stat evidence 路径，不读取内容。

**已冻结 T3 事实**：

| 项 | 冻结值 | 来源 |
|---|---|---|
| PR-0 verdict | `CONDITIONAL_AUTHORIZED`；evidence/handoff 记录了逐 `MONGODB_*` key declared/runtime 状态（**未泄露值/URI/长度/hash**，仍违反「只输出联合 boolean」契约） | `t_81432128` handoff |
| PR-1 执行 | 仅 `ping + list_collection_names`；`mongo_calls=2`、`write_operations=0`；未读取业务文档；三张 P3 预期集合存在 | `t_81432128` handoff |
| PR-2 执行 | **未执行**，`actual_calls=0` | `t_81432128` handoff |
| 既有 evidence 文件 | `docs/rfc/03_data/smoke_reports/audit-secret-20260804.yaml`、`docs/rfc/03_data/smoke_reports/preflight-mongo-20260804.yaml`（gitignored，仅 stat 确认存在） | 本卡 stat |

**Pascal 裁定（写死为契约）**：

1. 三集合（`03_data_ud_market_sector_snapshot`、`03_data_ud_stock_capital_flow`、`03_data_ud_market_sentiment_snapshot`）= **designated historical baseline（intentional pre-existing）**：presence 本身 **不是** PR-1 FAIL，而是 PR-1 PASS 基线；**禁止输出或枚举陌生集合名**；不允许 read business docs、不允许 DDL/DML。
2. PR-0 外部输出仅 **single aggregate authorization verdict + generic source-kind + generic redacted error-class**；禁止逐 key 名称、逐 key presence/runtime/declaration 状态、password marker、路径、值/长度/hash/URI。
3. 既有两份 gitignored evidence = **不合规本地工件**：developer Fix **必须仅**删除或替换为合规聚合版；审计事实保留在 Kanban，**不复制不合规内容到 repo/docs**。
4. **PR-1 不可重放**；**PR-2 预算未消耗**，仅 developer Fix → fresh Verify → Review 均通过后，才可新建**单独的 one-call continuation**。
5. PR-0「file-declared / runtime env absent」= `conditional_authorized`，**不等价于** secret 值有效性或生产授权。

> **R2 注（2026-08-04）**：本节的 R1 裁定 4（「PR-2 预算未消耗，仅 developer Fix → fresh Verify → Review 通过后另立 one-call continuation」）已被 §2.7 R2 裁定**取代**：PR-2 预算**永久废弃**，不再创建 continuation。本节其余冻结事实保留为历史。

### 2.7 R2 Scope-Scission：name_em 实时板块排行移出 Phase 3 目标（Pascal 2026-08-04 裁定）

> 本节为 **R2 scope-scission 契约**（Pascal 2026-08-04 范畴裁定，优先级最高），覆盖并取代此前所有将 PR-2 视为可执行目标的表述。以下裁定写死为契约，三份文档（RFC §2.6 / SPEC §0.2 / DESIGN §2.7）逐项一致。

**裁定**：`stock_board_industry_name_em()` / 行业板块 `name_em` 属于**实时板块排行**，不在本次 Unified Data Phase 3 的实现/生产验证目标之内。

1. **PR-2 的 name_em 单次预算永久废弃**（不因 scope removal 留作后门）：`t_55d44505` / `t_81432128` 标记为 **superseded / historical evidence**，不得 unblock、retry、创建 replacement probe 或改用其他 AKShare endpoint。
2. **禁止**为 name_em 新建 Provider recovery、替代 endpoint、实时 refresh 或任何 live retry。
3. P3-A 仅保留**盘后/历史、按 trade_date 可复现**的 sector read-path 验证（消费既有历史集合/物化数据，不发起任何实时 Provider 调用）。
4. PR-2 历史结果（一次尝试 `ProviderUnavailable`、一次越界 netprobe）保留为历史事实，但**不得**作为 P3-A 生产能力失败或后续 recovery 依据。

---

## 3. 设计原则与全局 OUT

- **授权链 = 命令级 allowlist + 零写入证明 + fail-stop**。三 Gate 串行：PR-0 → PR-1 → PR-2；任一 Gate exit ≥ 1 即停在该 Gate，记录证据，不 fallback、不重试、不降级为写入。**R2（§2.7）**：PR-2 已 **superseded / out-of-scope**，可执行链仅 PR-0 → PR-1（PR-1 亦不可重放，R1）；PR-2 设计保留为历史，不得执行。
- **全局 OUT（Fix 卡 / one-call continuation / Verify 均适用）**：真实 Mongo/Provider/HTTP/网络调用超出本链 allowlist 者；读取/打印/序列化/hash/枚举 secret value、URI credentials、`.env` 内容；DDL/DML、upsert、refresh、cache/file 写入（除 §7 允许的 redacted evidence 与 `/tmp` 临时文件）；原始 payload 保存；Mongo 业务读（find/aggregate/count/索引）；任意其他 Provider/HTTP endpoint；`cons_em`（任何路径）；P3-B/P3-C/northbound；services/restarts/cron/systemd/gateway/webhook；配置/依赖修改；Git stage/commit/push/reset/stash/clean；`--force/--apply/--write/--exec/--commit` 类参数。

---

## 4. PR-0 — Credential source availability audit（凭证源可用性审计）

### 4.1 安全实现方法（不读 value、不泄漏 key existence beyond approved boolean）

T3 直接复用既有 sanctioned 实现，**禁止自写解析 `.env` 的代码**：

1. **文件存在性**：`SecretVerifier.probe_file` → `os.path.isfile`（dry-run 亦不调 `os.access`）。
2. **文件可读性**：`probe_file_live` → `os.access(path, os.R_OK)`；**不读内容**。
3. **键声明探测（live）**：`probe_env_in_file(path, key, live=True)` → 单次 `read_text` 后执行 `f"{key}=" in text` **子串判断**，只产出 `key_declared: bool`。不解析值、不提取 `=` 右侧内容、不计算长度。dry-run 不读文件，`key_declared=None`。
4. **env 可加载性（live）**：`probe_env(key, live=True)` → `os.getenv(key) is not None`；返回值**即刻丢弃**，不得赋值给可序列化/可打印的名称。
5. **聚合（R1 收紧）**：外部输出仅 `SecretAuditResult` 的 `overall.verdict`（`authorized` / `conditional_authorized` / `unauthorized`）+ generic `source_kind` + generic `error_class`；**不再输出 `sources[]` 逐 key 明细、`missing_keys`、逐 key declared/runtime 状态**。内部可保留布尔探测用于判定，但不得进入任何外部序列化路径（YAML/stdout/handoff）。
6. **双层防泄漏**：第一层 `SecretProbeResult` 无值字段（结构性不可能携带值）；第二层 `Sanitizer` 序列化前清洗（`reporter.py`，规则见 §15.7.2：strip secret patterns / 截断长字符串 / 移除含 value/password/secret 字段）。

**边界**：`MONGODB_PORT` 非 int、`MONGODB_DATABASE != "tradingagents"` 的**值级校验在 PR-1 resolver 执行**（`mongo_client.py::resolve(live=True)`），PR-0 审计仅产出聚合判定。两级都满足「exit 3 + 不构造客户端 + 链停止」的可观测契约（与 RFC §5.1/§5.2 一致；SPEC F-PR0-006 的判定项由 PR-0 聚合审计 + PR-1 值级校验共同覆盖，语义无冲突）。**R1 语义澄清（§2.6 裁定 5）**：「file-declared / runtime env absent」= `conditional_authorized`，不等价于 secret 值有效性或生产授权。

### 4.2 状态机

```
START → [probe file exists/readable] → [live? probe keys declared + env loadable]
      → verdict:
          file exists + 五键 declared + env loadable        → authorized (0)     → 进入 PR-1
          部分满足（如文件存在但 env 不可加载，或反之）      → conditional_authorized (1) → 记录 + 暂停，Pascal 审阅后再定
          文件不存在 / 无键声明 / 不可加载                    → unauthorized (3)   → 链停止
          报告写入失败                                       → fail (2)           → 链停止
STOP（任何非 0）：不 fallback 其他来源；不执行任何写入；证据 YAML + stdout 记录。
```

### 4.3 参数与预算

| 项 | 值 |
|---|---|
| 执行命令 | `python -m scripts.t4_preflight.cli audit-secret --live-read --timeout 3`（从 repo 根，`.venv/bin/python`） |
| 环境变量白名单 | 无注入/导出。可被工具**布尔探测**的键：`MONGODB_HOST/MONGODB_PORT/MONGODB_USERNAME/MONGODB_PASSWORD/MONGODB_DATABASE`（仅 `is not None` 判定，值不落盘不输出）；标准运行变量（PATH/HOME）继承；禁止新增任何含 secret 的 env |
| 最长运行时间 | ≤ 15s（纯本地文件/环境探测，无网络） |
| 网络请求预算 | 0 次网络调用 |
| 报告写权限 | 仅 `docs/rfc/03_data/smoke_reports/audit-secret-YYYYMMDD.yaml`（redacted evidence 允许路径）+ stdout |

### 4.4 可公开脱敏输出 schema（R1 收紧：仅聚合）

```yaml
# audit-secret-YYYYMMDD.yaml（R1 契约版：single aggregate verdict + generic source-kind + generic error-class）
generated_at: "…"
source_kind: "phase2_skills_env"      # generic 来源种类标签，不含路径、不含键名
overall:
  verdict: authorized                 # authorized / conditional_authorized / unauthorized（仅聚合）
  error_class: null                   # generic redacted error-class（如 file_missing / env_unloadable），不含原始异常细节
```

**禁止字段（R1）**：任何逐 key 名称、逐 key presence/runtime/declaration 状态、password marker、路径、值、长度、URI、用户名、端口号、全路径+键值组合、`.env` 内容片段、`sources[]` 逐 key 明细、`missing_keys`。

### 4.5 fail-stop

exit 0 → 继续 PR-1；exit 1 → 记录 conditional 证据，暂停待 Pascal 审阅；exit 2/3 → 链停止，不执行 PR-1/PR-2。AKShare smoke（PR-2）本身不依赖 PR-0 授权，但本链为串行 Gate 链，**链序停止**优先（见 §6.1）。

---

## 5. PR-1 — MongoDB read-only preflight（Mongo 只读预检）

### 5.1 执行入口（已核验，禁止猜测）

- **执行器**：`PreflightRunner`（`scripts/t4_preflight/mongo_client.py`）——公开构造 `PreflightRunner(resolver=None)`，公开方法 `run_preflight(*, live=True, timeout=3)`。内部固定执行 `admin.command("ping")` + `list_collection_names()`（仅 `ALLOWED_DATABASE`）。
- **`PortfolioMongoLoader` 的角色**：五键组件语义参考（host/port/username/password/database 组件式、非 URI、默认 `tradingagents`），**不承担 ping/listCollections 执行**——其公开面是 upsert/load 写方法，无只读预检 API。T3 **不得**直接调用其私有 `_get_client()`/`_db()` 来做预检（私有路径构建含认证信息的 URI 字符串，超出命令级 allowlist 语义）。
- **CLI 包装**：`python -m scripts.t4_preflight.cli preflight-mongo --live-read --timeout 3`。
- **连接构造**：`LegacyConfigResolver` 从 `skills/.env` 经 `dotenv.dotenv_values()`（本地解析，**不污染 `os.environ`**）解析五键 → `ResolvedConfig`（仅布尔，不携带值）→ 通过 `AuthFiveTuple` 内存持有值 → `pymongo.MongoClient(host, port, username, password, authSource=MONGODB_DATABASE, serverSelectionTimeoutMS=3000)`。无 URI、无 fallback、无 CWD 推导。

### 5.2 命令 allowlist 与零写入证明

| 命令 | 允许 | 次数 |
|---|---|---|
| `admin.command("ping")` | ✅ 唯一允许的 admin 命令 | 1 |
| `db.list_collection_names()` | ✅ 唯一允许的集合枚举（无 filter） | 1 |
| `db[collection].options()` | ⚠️ 仅当**非 designated 的陌生 P3 命名集合**意外存在时（获取创建元数据，不读业务数据） | ≤1（条件触发） |
| `client.close()` | ✅ 清理 | 1 |
| 其余一切（find/aggregate/count/watch/DDL/DML/index/change stream） | ❌ | 0 |

**`mongo_calls ≤ 2` 的记账方式（本链裁定）**：`mongo_calls` = 执行路径中实际发出的 Mongo 命令数。标准路径 = ping(1) + list_collection_names(1) = **2**。`write_operations = 0` 由构造保证：allowlist 内无任何写 API；CLI 无写参数；`PREFLIGHT_MAX_OPERATIONS = 4` 硬顶（parse URI + ping + list + P3 check）不可覆盖。T3 在**外层**对执行做命令级审计（捕获 stdout/日志中出现的命令名），并在结论区输出 `mongo_calls: 2`、`write_operations: 0`（现行 `preflight_mongo.yaml` 无 ledger 块，故记账由外层审计补齐，作为 T4 核对项）。**R1：既有 PR-1 执行已冻结（`mongo_calls=2`、`write_operations=0`），后续链只审计 evidence，不重放（§2.6 裁定 4）。**

**before/after 集合清单一致性（F-PR1-008 的精确化）**：本链**不做**两次 `list_collection_names()` 夹取（那会把 mongo_calls 推高到 3，违反 F-PR1-007 `≤2`）。一致性命中 = ① 执行路径只含只读命令（命令级审计）；② 报告 `collections` 为单次枚举观测值；③ T4 将该观测与**冻结基线**（历史 `preflight-mongo-*.yaml`、P3 预期清单）比对。若 Pascal 要求严格 pre/post 夹取，须另行授权并修订预算契约，本链默认不采用。**R1：evidence 中 `collections` 仅允许 baseline 三集合 presence 观测，不枚举陌生集合名（§2.6 裁定 1）。**

### 5.3 状态机

```
START → resolve(live=True)
      → 五键缺失/空白 / PORT 非 int / DB != tradingagents  → env_missing → exit 3（不构造客户端）→ 链停止
      → build_client → ping
          ├─ DNS 解析失败 / 超时(>3s) / 认证拒绝         → dns_failure|timeout|auth_failure → exit 2 → 链停止
      → list_collection_names
          ├─ ping 成功但 list 未授权（collections=None） → exit 1 (conditional_pass) → 暂停待 Pascal 审阅
      → baseline 三集合 presence 观测（R1：存在即预期基线，非 FAIL）
          ├─ 非 designated 的陌生 P3 命名集合存在（baseline_unexpected 非空） → exit 2 → 停止，Pascal 判断遗留 vs 意外
          └─ 观测完成（success） → exit 0 → 进入 PR-2
STOP（任何非 0）：不 fallback 到新连接串/shell client/服务重启；不执行任何写入。
```

> **R1 不可重放**：既有 PR-1 执行（`t_81432128`，`mongo_calls=2`、`write_operations=0`）已冻结，后续链只审计 evidence，不重跑 live 预检（§2.6 裁定 4）。

### 5.4 参数与预算

| 项 | 值 |
|---|---|
| 执行命令 | `python -m scripts.t4_preflight.cli preflight-mongo --live-read --timeout 3` |
| 环境变量白名单 | 同 §4.3（工具经 `skills/.env` 文件读取五键，本地解析不落 `os.environ`）；禁止注入/导出任何 secret |
| 最长运行时间 | ≤ 30s（serverSelectionTimeoutMS=3000 + 本地解析开销） |
| 网络请求预算 | `mongo_calls ≤ 2`（ping + list）；无业务读 |
| 报告写权限 | 仅 `docs/rfc/03_data/smoke_reports/preflight-mongo-YYYYMMDD.yaml` + stdout |

### 5.5 可公开脱敏输出 schema

```yaml
# preflight-mongo-YYYYMMDD.yaml（R1 契约版：仅 baseline 三集合 presence 观测）
preflight_mongo:
  generated_at: "…"
  live_read: true
  connectivity: success        # success / dns_failure / timeout / auth_failure / env_missing / dry_run
  latency_ms: 12.3
  # R1：不枚举陌生集合名；仅观测三张 designated baseline 集合 presence（存在即预期基线，非 FAIL）
  baseline_collections:
    - name: "03_data_ud_market_sector_snapshot"
      present: true
    - name: "03_data_ud_stock_capital_flow"
      present: true
    - name: "03_data_ud_market_sentiment_snapshot"
      present: true
  baseline_unexpected: []      # 非 designated 的陌生 P3 命名集合（正常为空；非空即 exit 2，Pascal 判断）
  warnings: []
  detail: null
overall:
  verdict: pass                 # pass / conditional_pass / fail / unauthorized
ledger_audit:                   # 外层命令级审计补充（本链定义，非现行 CLI 输出）
  mongo_calls: 2
  write_operations: 0
```

**禁止字段**：任何业务 document、秘密值、URI、用户名、陌生集合名枚举（除上述三张 designated baseline 集合名）。

### 5.6 fail-stop

exit 0 → 继续 PR-2；exit 1 → 记录 conditional 证据，暂停待 Pascal 审阅；exit 2/3 → 链停止。所有失败路径保留 stdout 命令 trace 作为审计证据。

---

## 6. PR-2 — bounded Sector Provider smoke（有界 name_em smoke）

> ⚠️ **R2 superseded / out-of-scope（§2.7）**：本章（§6.1-§6.6）为历史执行设计。Pascal 2026-08-04 范畴裁定 `name_em` 实时板块排行不在 Phase 3 实现/生产验证目标内；PR-2 预算**永久废弃**，**不得执行**、不得重试、不得创建 replacement probe、不得改用其他 AKShare endpoint。以下内容（含 §6.1-§6.5 状态机/参数预算/输出 schema）仅保留为历史设计参考，标注不得执行。

### 6.1 执行入口固定（本链核心裁定）

- **唯一允许的 live-read 入口**：`skills.data.unified_data.providers.sector_client.AKShareSectorClient`。
- **调用序列（单次）**：
  ```python
  client = AKShareSectorClient(timeout=30.0)
  df = client.get_sector_ranking(sector_type="industry")   # → ak.stock_board_industry_name_em()
  ```
  - `sector_type` **固定为 `"industry"`**；`"concept"` 分支（`stock_board_concept_name_em`）与本链无关，禁止。
  - 不需要也不允许 `get_sector_snapshot(sector_code=…)` 作为第二个调用——snapshot 与 ranking 共享同一次 `name_em()` 响应（内存过滤），**本链只做一次网络请求**。
- **历史 cons_em 路径（确认存在，本链禁止）**：`scripts/t4_preflight/smoke_sector.py --live-read` 会经 `provider_client.AKShareSmokeClient.fetch_sector_snapshot` 调用 `stock_board_industry_cons_em("BK0489")`（`provider_client.py:295`）。T3 **不得**使用该 CLI、该客户端、该函数。主 DESIGN §15.14.2 的 endpoint 表（cons_em/rank_em）为 P3-A V0.2 裁定前内容，本链以 P3-A RFC/SPEC V0.2 为准（`name_em` 唯一共享主 endpoint）。
- **异常分类（复用 `_raise_classified` 语义，已核验）**：
  - `ProviderUnavailableError`：SSL/TLS/ConnectionError/Timeout/DNS/EOF/certificate/disconnect/reset/broken pipe 关键词、isinstance `(ConnectionError, TimeoutError)`、异常类型名 `sslerror/tlserror`、或 endpoint 函数在已装 akshare 中缺失 → **fail-stop（exit 2）**，记录 `error_class=ProviderUnavailableError`。
  - `ProviderError`：API 内部错误 / 其他异常 → **fail-stop（exit 2）**，记录 `error_class=ProviderError`。
  - `ProxyError/ConnectionError` 且全部调用失败 → 标注 `endpoint_unreachable`（egress 限制线索），由 Pascal 决定是否做单变量网络诊断（本链不执行诊断）。

### 6.2 响应校验与停止条件

| 检查 | 通过 | 停止 |
|---|---|---|
| 非空 | row_count > 0 | row_count = 0 → fail（exit 2，X2 保守：空返回维持 fail） |
| 字段匹配（12 列 expected） | ≥90% → pass (0)；70-90% → conditional (1) | <70% → fail（exit 2，A-DRIFT-5） |
| 核心字段存在 | `板块代码/板块名称/涨跌幅` 均在 | 任一缺失 → fail（exit 2） |
| 类型合理 | `涨跌幅` 等数值列 dtype 为数值 | 类型不匹配 → fail（exit 2） |
| 重试/降级 | 无重试（retry_count=0）、无 fallback（fallback_count=0） | 任何自动重试/降级即违约 |

### 6.3 状态机

```
START → 构造 AKShareSectorClient(timeout=30.0)
      → get_sector_ranking(sector_type="industry") 单次调用
          ├─ 成功 → 非空校验 → 字段匹配 → verdict: pass(0) / conditional_pass(1) / fail(2)
          ├─ ProviderUnavailableError → error_class=ProviderUnavailableError → fail(2) → 链停止（不重试）
          ├─ ProviderError → error_class=ProviderError → fail(2) → 链停止
          └─ ProxyError/ConnectionError 全失败 → endpoint_unreachable 标注 → fail(2) → 记录，Pascal 决定网络诊断
STOP（任何非 0）：不进入 DDL/CANARY 等后续 Gate；不降级为写入；不持久化原始 payload。
```

### 6.4 参数与预算

| 项 | 值 |
|---|---|
| 执行形式 | repo 根 + `.venv/bin/python` 内联片段（import `AKShareSectorClient` 与 `exceptions`），**不修改任何 repo 文件**；片段由 one-call continuation 卡正文固化，Verify 可逐字核对 |
| 请求预算 | `provider_attempts = 1`、`actual_calls ≤ 1`、`retry_count = 0`、`fallback_count = 0` |
| 超时 | `AKShareSectorClient(timeout=30.0)`（客户端超时固定）；超时 → `ProviderUnavailableError` → fail-stop |
| 最长运行时间 | ≤ 60s（import + 30s 超时上限 + pandas 处理） |
| 环境变量白名单 | 无必需键（AKShare 匿名、无 token）；仅继承 PATH/PYTHONPATH 等标准变量；禁止注入/导出任何 secret |
| Mongo/写入 | `mongo_calls = 0`、`write_operations = 0` |

### 6.5 可公开脱敏输出 schema（stdout 优先）

```yaml
# PR-2 name_em-only redacted evidence（T3 stdout 输出；可选落 /tmp 临时文件，见 §7）
capability: sector.ranking          # 本链仅 ranking 语义（共享 name_em 响应）
provider: akshare
smoke_at: "…"
endpoint: stock_board_industry_name_em
connectivity:
  status: success                   # success / failed
  latency_ms: 123.4
  error: null                       # 失败时仅 error_class，不含原始异常消息细节
field_mapping:
  total_expected_fields: 12
  matched_fields: 12
  missing_fields: []
  extra_fields: []
  type_mismatches: []
data_sample:
  row_count: 86                     # 仅计数
  sample_rows: [ … ≤5 行，Sanitizer 截断 … ]   # 仅字段名+类型+标量预览，禁止整行原始 payload
ledger:
  provider_attempts: 1
  actual_calls: 1
  retry_count: 0
  fallback_count: 0
  mongo_calls: 0
  write_operations: 0
overall:
  verdict: pass                     # pass / conditional_pass / fail
```

**禁止字段**：原始 DataFrame 全量、完整行、任何 secret、URI。

### 6.6 fail-stop

失败不重试、不 fallback；记录 error_class/connectivity 后停止；不进入任何后续 Gate。

---

## 7. R1 后续编排（developer Fix → fresh Verify → Review → one-call PR-2 continuation）

> **R1 起替代原「T3 controlled execution 一次性编排」**。原 §7 的 T3 一次性执行序列**已被 T3 冻结事实 + Pascal 裁定取代**（§2.6）：PR-0/PR-1 已执行且不可重放，PR-2 未执行。本节定义 R1 后续链的精确编排。

> **R2 注（§2.7）**：one-call PR-2 continuation（§7.4）已**永久废弃**，不再创建。§7.1 developer Fix（F1/F2/F3）与 §7.2 fresh Verify / §7.3 Review 针对 PR-0/PR-1 合规修复的编排保持有效；任何引用「后续 PR-2 continuation」的文字均为历史编排，不得执行。

### 7.1 developer Fix 卡（assignee=yquantdeveloper，独立最小修复）

| 步骤 | 目标 | 约束 |
|---|---|---|
| F1 | 删除或替换两份不合规 gitignored evidence：`docs/rfc/03_data/smoke_reports/audit-secret-20260804.yaml`、`docs/rfc/03_data/smoke_reports/preflight-mongo-20260804.yaml`，替换为**合规聚合版**（PR-0 仅 single aggregate verdict + generic source-kind + generic error-class；PR-1 仅 baseline 三集合 presence 观测，不枚举陌生集合名） | 仅上述两文件路径；删除或覆盖写；**不得复制不合规内容到 repo/docs** |
| F2 | 审计 SecretVerifier / audit-secret CLI / PreflightRunner 的**输出与报告序列化路径**，确保外部输出不再出现逐 key 名称/状态/password marker/路径 | 仅 `scripts/t4_preflight/` 只读 + `docs/rfc/03_data/smoke_reports/` 允许路径；无真实 I/O、无 Git 写 |
| F3 | **不重跑 PR-1**（`mongo_calls=2`、`write_operations=0` 已冻结）；不重跑 PR-0 live probe（纯本地 stat/probe 可重跑仅当 Pascal 批准，默认不做） | 禁止 Mongo/Provider/network；无 PR-2 执行 |

**Fix 卡完成判定**：F1 完成（两份 evidence 合规化）、F2 输出面审计通过、F3 遵守不重放。**Fix 卡不得顺带执行 PR-2。**

### 7.2 fresh Verify（assignee=yquanttester）

- 对照 §8 可复验项逐项核验 Fix 产物与 R1 契约（A-GATE-015~019 对应项）。
- **不得重跑 PR-1 live 预检；不得重放 PR-2 单次预算请求**（若 continuation 已建，仅审计其 evidence）。

### 7.3 Review（assignee=yquantreviewer）

- 独立审查 Fix diff（仅 §7.1 F1/F2 允许路径）、Fix 后 evidence schema、R1 契约一致性。
- 通过后**方可**创建独立的 one-call PR-2 continuation（预算 `provider_attempts=1`、`actual_calls≤1` 未消耗；见 §6）。

### 7.4 one-call PR-2 continuation（后续独立卡）

> ⚠️ **R2 superseded / out-of-scope（§2.7）**：本小节为历史编排，**永久废弃，不得执行、不得创建**。PR-2 预算不再消耗；不因 scope removal 留作后门。

- **入口**：`AKShareSectorClient(timeout=30.0).get_sector_ranking(sector_type="industry")` 单次调用（§6.1 不变）。
- **预算**：`provider_attempts=1`、`actual_calls≤1`、`retry_count=0`、`fallback_count=0`（未消耗）。
- **前置**：developer Fix → fresh Verify → Review 均通过。
- **禁止**：任何路径调用 `cons_em` / `rank_em`；修改 repo 文件；持久化原始 payload；触发 P3-B/P3-C/northbound。

---

## 8. T4 Independent Verify 分工

### 8.1 可独立复验项（离线，T4 直接执行，不消耗任何 live 预算）

| # | 项 | 方法 |
|---|---|---|
| V-1 | 三份 evidence YAML 存在且 schema 符合 §4.4/§5.5/§6.5（**R2：PR-2 evidence 不再生成，实际为 PR-0/PR-1 两份 YAML；§6.5 schema 仅历史比对用，见 §2.7**） | 文件 + YAML 解析 |
| V-2 | PR-1 账本：`mongo_calls ≤ 2`、`write_operations = 0`；PR-2 账本：`provider_attempts=1`、`actual_calls ≤ 1`、`retry_count=0`、`fallback_count=0`、`mongo_calls=0`、`write_operations=0`（**R2：PR-2 不再执行，此项仅适用于历史 evidence 审计，见 §2.7**） | §5.3/§6.5 字段核对 |
| V-3 | 命令级审计：stdout trace 只出现 allowlist 命令（ping + list_collection_names + name_em 单次）—— **R2**：name_em 单次不再出现（PR-2 superseded，§2.7），现仅核对 ping + list_collection_names | stdout 日志核对 |
| V-4 | PR-1 集合清单与冻结基线（历史报告、P3 预期清单）一致；**R1：evidence 仅 designated 三集合 presence 观测（`baseline_collections`），无陌生集合名枚举（`baseline_unexpected` 语义正确）** | 比对 |
| V-5 | 静态 grep：T3 执行痕迹无 `cons_em`/`rank_em`/`--force`/`--apply`/写 API；无原始 payload 文件；`/tmp/yquant-p3a-pr2-*` 无残留 | grep + find |
| V-6 | exit code 语义与 §15.8 一致（0/1/2/3） | 执行报告核对 |
| V-7 | `git diff --check` exit 0；Fix 变更集仅限 §7.1 F1/F2 允许路径 | git（只读） |
| V-8 | 脱敏：YAML 无 secret 模式（值/URI/用户名/长度） | grep REDACTED / 静态检查 |
| V-9 | **R1：PR-0 evidence 仅 single aggregate verdict + generic source-kind + generic error-class，无逐 key 名称/状态/password marker/路径（§2.6 裁定 2）** | YAML 字段核对 + grep |
| V-10 | **R1：PR-1 evidence 仅 baseline 三集合 presence 观测，无陌生集合名枚举（§2.6 裁定 1）** | YAML 字段核对 + grep |
| V-11 | **R1：既有两份不合规 evidence 已被删除或替换为合规聚合版；Kanban 事实保留，repo/docs 无不合规副本（§2.6 裁定 3）** | stat + git status（只读） |
| V-12 | **R1：未重跑 PR-1 live 预检；PR-2 未重放（§2.6 裁定 4）** | 命令 trace + 账本核对 |

### 8.2 仅审计 T3 redacted evidence 项（**不得重放 live 请求**）

| # | 项 | 规则 |
|---|---|---|
| A-1 | **PR-2 单次预算请求（name_em 线上响应）** | **绝不重复调用**（provider_attempts=1 为硬预算）。T4 只审计 T3 证据的字段匹配比例、row_count、sample_rows、error_class、connectivity 的内部一致性与对 12 列 expected 的符合性；任何疑问 → 在报告中标记并交由 Pascal 决策，不得自行复测。**R2 superseded / out-of-scope（§2.7）：PR-2 不再执行，无新证据可审计；本项仅适用于既有历史 evidence（若有），预算永久废弃** |
| A-2 | PR-0 键声明探测结果 | 默认审计 T3 evidence；如 Pascal 要求，T4 可重跑（纯本地、零网络预算），但非「独立」之必需 |
| A-3 | PR-1 连接/认证结果 | 默认审计 T3 evidence；重跑需 Pascal 批准（2 条只读命令，不消耗 AKShare 预算），非「独立」之必需 |

**原则**：Verify 的「独立性」由证据审计 + 离线复验实现，**不以重复 live 调用为代价**（任务约束：不得为了独立重复 PR-2 的单次预算请求）。**R2：PR-2 已永久废弃（§2.7），本原则对 PR-2 的适用仅为历史约束。**

---

## 9. 一致性声明

- 与 RFC-03-014-p3a-readonly-gate V0.4、SPEC-03-014-p3a-readonly-gate V0.3 语义自洽：Gate 编号、exit code（0/1/2/3）、预算、停止条件、零写入证据、evidence 字段全部对齐；**R1 五裁定在 §2.6 与 RFC §2.4 / SPEC §0 完全一致**；**R2 scope-scission 在 §2.7 与 RFC §2.6 / SPEC §0.2 完全一致（PR-2 superseded / out-of-scope、预算永久废弃、仅保留盘后/历史 trade_date 可复现的 sector read-path 验证）**。
- 与主 RFC/SPEC-03-014（§6.2 / §13.1 / §14.4.5 / §15.8）一致：继承零持久化副作用原则与 B2 冻结证据（offline stub → 本链为 Pascal 授权的一次受控 live-read；`endpoint_unreachable` 时由 Pascal 决定单变量网络诊断）。**R2：受控 live-read 授权已随 PR-2 一并废弃（§2.7），B2 冻结证据仍为历史事实。**
- 与 P3-A RFC/SPEC V0.2 一致：`name_em` 为唯一共享主 endpoint；`rank_em` 不存在；`cons_em` 非主数据源、本链禁止。**R2：endpoint 裁定保留为历史事实；PR-2 不得执行（§2.7）。**
- 与主 DESIGN-03-014 §15.x 的关系：复用其 T4 工具链（audit-secret/preflight-mongo CLI、SecretVerifier、LegacyConfigResolver、PreflightRunner、LedgerBlock、Sanitizer）；主 DESIGN §15.14.2 endpoint 表（cons_em/rank_em）为 V0.2 前内容，本链以 P3-A V0.2 裁定覆盖（不修改主 DESIGN）。
- 与历史 fake-only DESIGN-03-014-p3a-sector-provider-activation 的关系：**不重新激活**其执行授权；本 Design 独立新建 Gate 链。
- 已知语义分层说明（非冲突）：SPEC F-PR0-006 将 port-int/db-value 校验列于 PR-0 NOT_AUTHORIZED；实际工具链中 PR-0 产出键声明布尔、值级校验由 PR-1 resolver 执行。两者可观测契约一致（exit 3 + 不构造客户端 + 链停止），已在 §4.1 记录。

---

## 10. 验收标准

| # | 项 | 通过条件 |
|---|---|---|
| D-1 | Design 文件存在 | `docs/design/03_data/DESIGN-03-014-p3a-readonly-gate.md` 新建 |
| D-2 | RFC/SPEC/Design/当前代码语义自洽 | §2 核验事实 + §9 一致性声明覆盖 |
| D-3 | 可执行卡无需猜 API | PR-0/1/2 入口、构造、调用序列、异常类均为已核验符号（**R2：PR-2 不再可执行，其入口仅保留为历史核验事实，见 §2.7**） |
| D-4 | 权限/预算/零写入/脱敏/停止/后续验证可计算 | §4-§8 全部量化 |
| D-5 | `git diff --check` 通过且仅 Design allowlist | git 只读校验；本卡变更集 = 本 Design 单文件 |
| D-6 | 未触发真实 I/O | 本卡零 Mongo/Provider/HTTP/网络调用；未读 `.env` 内容 |
| D-7 | 中文 handoff，明确 T3 已执行 PR-0/PR-1（冻结）、PR-2 未执行（actual_calls=0）且不可重放 | 本节 + §1 + §2.6 |
| D-8 | **R1：三集合 presence 非 PR-1 FAIL、禁止枚举陌生集合名；PR-0 外部输出仅聚合；既有 evidence 不合规处置；PR-1 不可重放、PR-2 预算未消耗；file-declared/runtime-absent=conditional（§2.6）** | 静态检查 |
| D-9 | **R2（本卡 `t_51c36693`）：PR-2 预算永久废弃、无 one-call continuation、无 replacement probe / 替代 endpoint / 实时 refresh / live retry；`t_55d44505` / `t_81432128` 标记 superseded / historical evidence；P3-A 仅保留盘后/历史、按 trade_date 可复现的 sector read-path 验证（§2.7）；PR-0/PR-1 契约未被动摇** | 静态检查 |

---

## 11. 开放问题（继承 T1）

- OQ-GATE-1：`name_em()` 线上返回的 `领涨股票` 列是代码还是名称（P3-A OQ-P3A-6）——本链只记录字段名/数量/类型，不解析语义。 —— **superseded（R2）**：`name_em` 实时板块排行移出 Phase 3 目标（§2.7），不再适用；保留为历史。
- OQ-GATE-2：`name_em()` 为实时排名、无历史日期维度——本链只验证实时可用性；`snapshot_date` 语义由后续激活设计裁定。 —— **superseded（R2）**：不再适用；保留为历史。
- OQ-GATE-3：若 `name_em()` 因 egress 限制失败（endpoint_unreachable），单变量网络诊断（切换出口/TLS 检查）由 Pascal 手动还是 Agent 辅助——本链不执行诊断。 —— **superseded（R2）**：PR-2 不再执行，不再适用；保留为历史。
- OQ-GATE-4：PR-1 意外发现 P3 预期集合已存在时，Pascal 判断「遗留 vs 意外」的决策入口（board comment / 口头确认）——本链只记录与停止。 —— **已闭合（R1）**：历史集合语义已由 R1 裁定（三集合为 designated historical baseline，presence 非 FAIL，§2.6 裁定 1）；本 OQ 指向 R1 裁定，不再开放。

---

## 12. 声明

本 Design 中涉及的板块/行业数据为辅助研究数据，不构成交易指令或投资建议。

本 Design 的 Gate pass 仅证明「凭证可加载 + Mongo 只读可达 + name_em 返回结构与预期一致」，**不构成生产激活、数据入库或可交易信号**。**R2：PR-2 已 superseded / out-of-scope（§2.7），Gate pass 语义仅剩「凭证可加载 + Mongo 只读可达」；PR-2 定义保留为历史。**

本 Design 未修改 RFC/SPEC 主文档、主 DESIGN-03-014、历史 P3-A fake-only Design、任何代码/配置；未执行任何真实 Mongo/Provider/网络调用；未读取 `skills/.env` 内容。

---

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.3 | 2026-08-04 | **R2 Scope-Scission（本卡 `t_51c36693`）**：Pascal 2026-08-04 范畴裁定 `name_em` 实时板块排行移出 Phase 3 目标（新增 §2.7，与 RFC §2.6 / SPEC §0.2 逐项一致）——PR-2 预算**永久废弃**、不得 retry / replacement probe / 替代 endpoint / 实时 refresh；`t_55d44505` / `t_81432128` 标记 superseded / historical evidence；P3-A 仅保留盘后/历史、按 trade_date 可复现的 sector read-path 验证（无实时 Provider 调用）；PR-2 历史结果（ProviderUnavailable + netprobe 越界）保留为历史事实、不作生产能力失败或 recovery 依据。§1 / §2.6（补 R2 注）/ §3 / §6（整章）/ §7（§7.4 整节，§7 补 R2 注）/ §8（V-1/V-2/V-3/A-1）/ §9 / §10（D-3/D-7 标注，新增 D-9）/ §11（OQ-GATE-1/2/3 superseded、OQ-GATE-4 闭合）/ §12 声明 全部对齐 R2；PR-0/PR-1 契约未被动摇 | YQuant-Principal |
| V0.2 | 2026-08-04 | R1 契约修订：① 三集合明示为 designated historical baseline（presence 非 PR-1 FAIL，禁止枚举陌生集合名）；② PR-0 外部输出收敛为 single aggregate verdict + generic source-kind + generic error-class（禁止逐 key 名称/状态/password marker/路径）；③ 既有两份 gitignored evidence 定为不合规本地工件，developer Fix 仅删除/替换为合规聚合版；④ PR-1 不可重放，PR-2 预算未消耗（actual_calls=0），仅 Fix+Verify+Review 通过后另立 one-call continuation；⑤ file-declared / runtime env absent = conditional，非 secret 值有效性或生产授权；⑥ §7 改写为 R1 后续编排，§8 增 V-9~V-12 | YQuant-Principal |
| V0.1 | 2026-08-04 | 初始创建：P3-A Step-4 PR-0/PR-1/PR-2 受控只读 Gate 的执行编排、已核验入口、状态机、env 白名单、预算、脱敏 schema、fail-stop、T4 Verify 分工 | YQuant-Principal |
