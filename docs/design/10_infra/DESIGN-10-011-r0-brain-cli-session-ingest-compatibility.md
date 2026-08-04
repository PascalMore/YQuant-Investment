# DESIGN-10-011：r0 Brain CLI 统一入口与 Hermes session 导入兼容

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-08-04 |
| 最后更新 | 2026-08-04 |
| 版本号 | V0.2 |
| 所属模块 | 10_infra（基础设施 / 知识管理） |
| 来源 RFC | [RFC-10-011-r0-brain-cli-session-ingest-compatibility](../../rfc/10_infra/RFC-10-011-r0-brain-cli-session-ingest-compatibility.md)（V0.2） |
| 来源 SPEC | [SPEC-10-011-r0-brain-cli-session-ingest-compatibility](../../spec/10_infra/SPEC-10-011-r0-brain-cli-session-ingest-compatibility.md)（V0.2） |
| 适配 Agent | YQuant-Developer-Engineer、YQuant-Test-Engineer、YQuant-Reviewer-Principal |
| 标签 | #infra #brain #hermes #ingest #schema-compat #jmap #cron #design |

> 本文件即 RFC/SPEC 元数据表中的「关联 Design」所指文件；RFC-10-011 / SPEC-10-011 元数据中的 Design 链接已解析为真实文件（V0.2）。

## 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-08-04 | 初始创建：r0 adapter 函数级设计、profile-local entrypoint 定名与内容、cron prompt 精确替换、fixture/测试矩阵、回滚流程、并发/WAL/隐私边界 | YQuant-Principal |
| V0.2 | 2026-08-04 | **P0 修订（Option A，替代失败 Verify t_d1827953）**：新增 §3.9 scanner 模块函数级设计（`ScanResult`/`scan_for_secrets_detailed`/`classify_env_assignment`、值形态分类器、状态后缀列表）；§3.6/§3.7 接入两级扫描（E-005 仅 blocking、W-001 warning exit 0）；§1.2 allowlist 新增 `secret_scan.py` 与 `test_secret_scan.py`、禁止清单明确 `source-hashes.json`；测试矩阵新增 U-009~U-013 / F-008 / R-002 修订 / R-007；§9 回滚扩至 A 组 4 文件；§13 交接含两级扫描契约；明确旧 T4 Verify 被 supersede、新 Verify 重新独立执行 | YQuant-Principal |

---

## 1. 结论与范围

### 1.1 结论

本设计把 RFC-10-011 / SPEC-10-011 落为可实施、可测试、可回滚的工程契约，核心决策：

1. **r0 adapter 单点适配**（`r0b0tlabbra1n/ingest/hermes_sessions.py`）：用「schema 变体检测 → 变体化 SELECT → 行归一化 → provider 派生」四步把真实 Hermes schema（`started_at REAL`、`model`、`session_model_usage.billing_provider`）映射为 r0 原有语义（`created_at`、`model_name`、`provider_name`），保持 `mode=ro`、排序 `(created_at,id)`、标量 cursor、manifest 幂等与 secret 扫描不变。文件名从 `{date}-{sid[:8]}.md` 改为 `{date}-{full_sid}.md`。
2. **错误分类内聚到 adapter**：新增 `IngestError(SystemExit)` 异常，携带 `code`/`exit_code`/`message`；`_abort()` 写 stderr 机器可读行（`ERROR E-00X: ...`）后 raise。因为 `cli.py` 不在 allowlist 内，`IngestError` 继承 `SystemExit` 使得未修改的 `cli.py` 也能透传契约退出码（E-001~E-006 → 1，E-007 → 3）。
3. **B 组 entrypoint 为薄封装 bash**：每 profile 一份 `brain_ingest_sessions.sh`，固定 canonical 绝对路径与 `--hermes-home`/`--vault` 生产默认值，`"$@"` 透传可选参数（供 Verify/手工使用），原样返回 brain 退出码、非零时 stderr 输出错误行。全程零 PATH 依赖。
4. **C 组 cron prompt 仅替换两处**：ingest 内联调用改为 entrypoint；裸 `brain lint / brain build-index` 改为 canonical 绝对路径；追加「非零退出即中止并报告失败」硬性语义。`schedule`/`deliver`/`skills`/`workdir`/`repeat` 等字段一律不动。
5. **Q-1 已实证解决**：真实样本（yquant state.db 只读 probe）显示 session id 内嵌时间与 `started_at` 的 +08:00 换算完全一致（`20260804_071750_43a935ba` ↔ 上海 07:17:50），时区常量 `+08:00` 无需调整（详见 §2.2）。
6. **两级 secret 扫描（P0 修订，Option A）**：`r0b0tlabbra1n/security/secret_scan.py` 重构为 `ScanResult(blocking, warnings)` 两级输出——blocking（私钥/provider 格式/JWT/Bearer/AWS/Google/可证明 credential-value 形态）走 E-005 fail-stop（不落盘、exit 1）；warning（`TOKEN_PRESENT`/`KEY_CONFIGURED` 等探测/状态字段、redacted marker、布尔/枚举/短值形态）走 W-001（stderr + 摘要计数 + frontmatter `security_warnings`，exit 0、页正常落盘）。`scan_for_secrets`/`is_safe` 保持向后兼容，`vault/lint.py`、`vault/write_ops.py` 对 blocking credential 继续 hard-block（详见 §3.9）。

### 1.2 本卡 Implement allowlist（精确且封闭）

| 路径 | 允许动作 | 目的 |
|---|---:|---|
| `r0b0tlabbra1n/ingest/hermes_sessions.py`（r0 仓库） | 增量修改 | 实现 §3 的兼容读取、归一化、错误分类、文件名唯一性；secret 扫描接入两级分类（§3.6/§3.9）；保持只读 URI/manifest/摘要语义 |
| `tests/test_hermes_session_ingest.py`（r0 仓库） | 增量修改 | 新增真实 schema fixture 与映射/排序/文件名/错误/幂等用例（对应 SPEC §6.1/§6.2）；新增两级扫描 ingest 用例（F-008） |
| `r0b0tlabbra1n/security/secret_scan.py`（r0 仓库，**V0.2 新增**） | 增量修改 | 实现 §3.9 两级分类：blocking patterns 保持；env 分支按 credential-value 形态分类（blocking/warning/safe）；新增 `scan_for_secrets_detailed`/`ScanResult`；`scan_for_secrets`/`is_safe` 向后兼容 |
| `tests/test_secret_scan.py`（r0 仓库，**V0.2 新增**） | 增量修改 | 新增两级分类用例（U-009~U-013 等）：状态字段→warning、真实凭据→blocking、lint/write_ops 公共调用方 hard-block 不变 |
| `~/.hermes/profiles/yquant/scripts/brain_ingest_sessions.sh` | 新增 | yquant 变体 entrypoint（§4） |
| `~/.hermes/profiles/yinglong/scripts/brain_ingest_sessions.sh` | 新增 | yinglong 变体 entrypoint（§4） |
| `~/.hermes/profiles/yquant/cron/jobs.json` | 增量修改（仅 job `7fd3367324c4` 的 `prompt` 字段） | §5.1 |
| `~/.hermes/profiles/yinglong/cron/jobs.json` | 增量修改（仅 job `c91202e2a61f` 的 `prompt` 字段） | §5.2 |

以下文件/范围**禁止**创建、修改、删除、暂存或提交：

```text
hermes-agent/                                        # Hermes core（schema/查询/gateway）
r0b0tlabbra1n/cli.py                                  # 不在 allowlist：错误分类由 adapter 承担
~/.hermes/profiles/{yquant,yinglong}/config.yaml     # external_dirs/hooks/PATH/凭据
~/.hermes/profiles/{yquant,yinglong}/state/*.db*     # Hermes SQLite（只读打开，零写入）
~/.hermes/profiles/{yquant,yinglong}/state/jmap-candidate-queue.jsonl / jmap-candidate-processed.json
/mnt/e/Data/Yinglong/JMap/                           # 本阶段只读；任何写仅允许临时 vault
tests/fixtures/eval-vault/_meta/source-hashes.json   # r0 共享工作树外部/旧 dirty timestamp（仅 generated_at）；不可修改、不得 reset/stash/清理或误归因
~/.bashrc ~/.profile /etc/environment /mnt/c /mnt/d  # 全局 PATH / 环境
r0 hermes/skills/llm-wiki-brain/SKILL.md、r0 README  # 本卡不纳入（决策见 §12）
```

### 1.3 非目标

- 不修改 `cli.py`、Hermes core、任何 profile `config.yaml`、shell PATH、凭据、gateway。
- 不对 Hermes SQLite 做任何写入/schema 变更/影子拷贝（RFC §8 已否决的方案一律不做）。
- 不改 cron 时间表与投递策略；只替换 prompt 内联 brain 调用。
- 本阶段不创建候选、不提升/合并/覆盖/删除任何 JMap 正式知识页；验证只用临时 vault。
- 不实现/不启用 `--include-transcripts`（cron 现状不传；默认关闭，L3 启用需 Pascal 确认）。
- 不重构其他 brain 子命令（`search`/`build-index`/`lint` 等）入口，仅固化统一解析规则。
- 不削弱 scanner 公共调用方（`vault/lint.py`、`vault/write_ops.py`）对 blocking credential 的 hard-block 语义（P0 修订约束）；两级分类只影响 ingest 侧 E-005/W-001 分流。

---

## 2. 已核实的输入事实与设计决策

### 2.1 运行时事实（2026-08-04 只读 probe 证据）

| # | 事实 | 证据 |
|---|---|---|
| 1 | yquant `sessions` 无 `created_at`，有 `started_at REAL`、`model`、`parent_session_id`、`model_config`；无 `model_name`/`provider_name` 列 | `PRAGMA table_info(sessions)`（yquant 139 行 / yinglong 68 行） |
| 2 | `session_model_usage` 列：`session_id, model, billing_provider, billing_base_url, billing_mode, task, api_call_count, ..., first_seen REAL, last_seen REAL`；无独立自增主键（PK 为复合键） | `PRAGMA table_info(session_model_usage)` + `hermes_state_common.py` SCHEMA_SQL |
| 3 | provider 实样：yquant `20260804_071750_43a935ba` 有多行 usage：`gpt-5.6-terra/openai-codex`（`last_seen` 最新）、`gpt-5.6-terra/auto`、`MiniMax-M3/custom:minimax` → `ORDER BY last_seen DESC` 可取 `openai-codex` | 只读查询 sample |
| 4 | yinglong 亦有 usage 行（`custom:minimax` 等）；cron 类 session id 形如 `cron_c91202e2a61f_20260804_020547`（无随机后缀，前 8 位非日期） | 只读查询 sample |
| 5 | r0 venv Python 为 3.12.13；`datetime.fromisoformat` 支持带 `+08:00` 偏移的 ISO 串；`fromtimestamp(ts, tz=+08:00)` 可用 | `.venv/bin/python --version` |
| 6 | 两 profile `cron/jobs.json`：yquant job `7fd3367324c4`（`45 2 * * *`）、yinglong job `c91202e2a61f`（`5 2 * * *`），均 `deliver: local`、`skills: [knowledge]`、`no_agent: false`，prompt 内联调用 canonical brain 且末尾有裸 `brain lint / brain build-index` | jobs.json 全文 |
| 7 | yquant/yinglong `scripts/` 下尚无 `brain_ingest*` 文件 | `search_files` |

### 2.2 Q-1 结论：session id 内嵌时间 = 上海本地时间（+08:00）

| sid | id 内嵌时间 | `started_at` 换算 UTC | `started_at` 换算 +08:00 |
|---|---|---|---|
| `20260804_125148_ab87f0` | 12:51:48 | 04:52:01 | 12:52:01 |
| `20260804_071750_43a935ba` | 07:17:50 | 23:17:50 (08-03) | 07:17:50 (08-04) |
| `cron_7fd3367324c4_20260804_024601` | 02:46:01 | 18:46:02 (08-03) | 02:46:02 (08-04) |

id 内嵌时间与 +08:00 换算一致（秒级含约 1 秒偏差，来自 started_at 写入时间戳与 id 生成顺序）。**结论：RFC Q-1 关闭，时区常量固定 +08:00，无需按 UTC 调整。** Verify 仍按 SPEC R 组用真实样本复核一次（§7.4）。

### 2.3 关键设计决策

| # | 决策 | 理由 |
|---|---|---|
| D-1 | schema 变体优先级：`created_at` 存在 → `upstream`；无 `created_at` 但有 `started_at` → `hermes`；两者皆无 → E-002 | RFC §4.3.1/§7「新列存在则优先使用，向后兼容」 |
| D-2 | 排序在 SQL 层按底层时间列（`upstream: created_at` / `hermes: started_at`）+ `id ASC`；语义等价于契约 `(created_at, id)` | epoch→ISO+08:00 严格单调，两序一致；避免函数式 ORDER BY |
| D-3 | provider 派生 SQL：`session_model_usage` 按 `COALESCE(last_seen, first_seen, 0) DESC, model ASC` 取首个非空 `billing_provider`；表缺失/无行 → `"unknown"` | SPEC §4.2 优先级 1；`model` 为 PK 成员，作确定性 tiebreak；不读 `sessions.model_config`（SPEC 默认不纳入，最小契约） |
| D-4 | `IngestError(SystemExit)`：adapter 内聚错误分类与退出码，`cli.py` 零改动 | allowlist 不含 `cli.py`；SystemExit 传播保证 E-001~E-007 退出码正确 |
| D-5 | entrypoint 生产默认值固定，`"$@"` 透传可选 `--hermes-home/--vault/--since/--include-transcripts` 覆盖 | SPEC F-005 固定参数约束针对生产调用路径（cron 零参数）；覆盖能力是 SPEC §6.3 R-001/R-002/R-004 验证 entrypoint 失败注入的必要手段，非生产路径 |
| D-6 | r0 skill/README 文档更新**不纳入**本卡 allowlist | 理由见 §12；零测试影响 |
| D-7 | 真实 JMap 写入**不在**本卡 Verify 默认路径；生产首次 ingest 由既有 cron 时间表（02:05/02:45）在 Review/Closeout 后自然触发 | SPEC §4.bis/§7.1：验收全程真实 JMap 只读、哈希不变 |
| D-8 | **两级扫描（P0 修订）**：`secret_scan.py` 输出 `ScanResult(blocking, warnings)`；blocking→E-005 fail-stop，warnings→W-001 + 计数 + ingest 继续 | 旧 Verify t_d1827953 有效证据：`TOKEN_PRESENT` 状态字段被误判为 blocking；Option A 按值形态与状态后缀分类 |
| D-9 | **向后兼容公共 API**：`scan_for_secrets`/`is_safe` 语义不变（仅 blocking）；`vault/lint.py`、`vault/write_ops.py` 零改动、hard-block 不变 | SPEC §7.1 第 8 条：warning 行为不得削弱真实密钥保护 |
| D-10 | **warning 可观测**：stderr `WARNING W-001`（不回显值/原文）+ stdout 摘要计数 + frontmatter `security_warnings`；manifest 结构不变 | SPEC F-113/F-114：不得把探测字段原文/session 原文作为 metadata 持久化 |
| D-11 | **allowlist 扩展与 path attribution**：A 组新增 `secret_scan.py`、`test_secret_scan.py`（仅此两项）；`source-hashes.json` 明确不可修改 | r0 工作树该文件为外部/旧 dirty timestamp；不得 reset/stash/清理或误归因 |

---

## 3. A 组：r0 adapter 模块/函数级设计

目标文件：`/home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/r0b0tlabbra1n/ingest/hermes_sessions.py`（editable 安装，改后即时生效，无需重装）。

### 3.1 文件内函数清单（现状 → 目标）

| 函数 | 现状 | 目标改动 |
|---|---|---|
| `ingest(state_db_path, vault_path, since_cursor=None, include_transcripts=False) -> int` | 调用 `_validate_schema`、固定 SELECT | 签名不变；改为「变体检测 → 变体化 SELECT → 归一化 → 页面/transcript/manifest」，全程 try/except 映射错误分类 |
| `_validate_schema(conn)` | 要求 `{id, created_at}`，缺列 raise ValueError | **删除**，由 `_detect_schema_variant` 取代 |
| `_detect_schema_variant(conn) -> str` | — | **新增**：返回 `"upstream"` / `"hermes"`；表缺失/messages 缺列 → E-001；时间列皆无 → E-002 |
| `_sessions_query(variant, since_cursor) -> tuple[str, list]` | — | **新增**：按变体构造 SELECT 与参数（含 `WHERE created_at > ?` 与 `ORDER BY <time_col> ASC, id ASC`） |
| `_epoch_to_iso(epoch: float) -> str` | — | **新增**：`datetime.fromtimestamp(epoch, tz=timezone(timedelta(hours=8))).isoformat()`，微秒精度 |
| `_derive_provider(conn, sid) -> str` | — | **新增**：D-3 SQL；`session_model_usage` 表缺失 → `"unknown"` |
| `_normalize_session(row, variant, conn) -> dict` | — | **新增**：产出 canonical dict `{id, created_at(ISO str), parent_session_id, model_name, provider_name}` |
| `_create_session_page(conn, session, vault_path) -> Optional[Path]` | `session["created_at"]` 直用、文件名 `{date}-{sid[:8]}.md` | 输入改为 normalized dict（现有字段访问兼容）；文件名改 `{date}-{full_sid}.md`；secret 扫描改两级（blocking→`_abort` E-005；warnings→W-001 + `security_warnings` 计数，§3.9） |
| `_messages(conn, sid)` | messages 缺列时静默返回 `[]` | 缺列 → E-001（SPEC E-001）；正常路径不变 |
| `_load_ingested` / `_record_ingested` / `_summarize_messages` / `_section` / `_write_transcript` | 现状 | 不变（manifest 追加保持单行 O_APPEND 原子写） |
| `IngestError` / `_abort` | — | **新增**：错误分类载体（§3.7） |

### 3.2 `ingest()` 控制流（目标实现）

```text
ingest(state_db_path, vault_path, since_cursor, include_transcripts)
 ├─ manifest_path = vault/_meta/ingestion-manifest.jsonl；ingested_ids = _load_ingested(manifest)
 ├─ uri = f"file:{state_db_path}?mode=ro"；conn = sqlite3.connect(uri, uri=True)；row_factory = Row
 ├─ try:
 │   ├─ variant = _detect_schema_variant(conn)            # E-001 / E-002 fail-stop
 │   ├─ 若 since_cursor 非 None：校验 ISO-8601（datetime.fromisoformat 包裹）；非法 → E-007 (exit 3)
 │   ├─ sql, params = _sessions_query(variant, since_cursor)
 │   ├─ for row in conn.execute(sql, params):
 │   │   ├─ sid = row["id"]；若 sid in ingested_ids → continue
 │   │   ├─ norm = _normalize_session(row, variant, conn)  # 时间换算 + 列映射 + provider 派生
 │   │   ├─ page = _create_session_page(conn, norm, vault_path)   # E-004/E-005
 │   │   ├─ if page and include_transcripts: _write_transcript(conn, norm, state_db_path, vault_path)
 │   │   ├─ _record_ingested(manifest_path, sid)；count += 1
 │   └─ return count
 └─ finally: conn.close()
```

### 3.3 变体检测与 SELECT（函数级契约）

`_detect_schema_variant(conn)`：

1. `tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}`；`{"sessions","messages"} - tables` 非空 → `_abort("E-001", 1, f"missing tables: {sorted(missing)}")`。
2. `mcols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}`；`{"session_id","role","content"} - mcols` 非空 → E-001（不再静默 `[]`）。
3. `scols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}`：
   - `"created_at" in scols` → `"upstream"`；
   - `elif "started_at" in scols` → `"hermes"`；
   - `else` → `_abort("E-002", 1, "no usable time column (created_at/started_at)")`（任何 vault 写入前中止）。

`_sessions_query(variant, since_cursor)`：

- `upstream`：`SELECT id, created_at, parent_session_id, model_name, provider_name FROM sessions`
- `hermes`：`SELECT id, started_at, parent_session_id, model, NULL AS provider_name FROM sessions`
- 共用追加：`since_cursor` 非空时 `WHERE <time_col> > ?`；`ORDER BY <time_col> ASC, id ASC`。
- 实现注记：列名取自 §3.3 检测结果而非硬编码，避免「引用不存在列 → E-003」；E-003 仅保留给真正的适配缺陷（如 SQL 拼装错误）。

### 3.4 行归一化（时间换算 + 列映射）

`_normalize_session(row, variant, conn) -> dict`：

| canonical 键 | upstream 来源 | hermes 来源 | 默认 |
|---|---|---|---|
| `id` | `row["id"]` | `row["id"]` | — |
| `created_at` | `row["created_at"]`（原字符串直用） | `_epoch_to_iso(row["started_at"])` | — |
| `parent_session_id` | `row["parent_session_id"]` | `row["parent_session_id"]` | `""`（NULL → `""`） |
| `model_name` | `row["model_name"]` | `row["model"]` | `"unknown"`（NULL/空） |
| `provider_name` | `row["provider_name"]` | `_derive_provider(conn, sid)` | `"unknown"` |

`_epoch_to_iso`：`TZ = timezone(timedelta(hours=8))`；`datetime.fromtimestamp(epoch, tz=TZ).isoformat()`（例：`1722733200.5` → `2024-08-04T12:00:00.500000+08:00`）。禁止把 epoch 数值直接当作 `created_at` 传入（`fromisoformat` 会失败导致日期前缀变 `unknown`，SPEC F-103 红线）。

### 3.5 provider 派生（函数级契约）

`_derive_provider(conn, sid) -> str`：

```sql
SELECT billing_provider FROM session_model_usage
WHERE session_id = ? AND billing_provider != ''
ORDER BY COALESCE(last_seen, first_seen, 0) DESC, model ASC
LIMIT 1
```

- 表不存在（`sqlite_master` 未命中 `session_model_usage`）或查询抛错 → 返回 `"unknown"`（provider 为可选字段，SPEC §4.1 必填=否）。
- 空串视为无（`billing_provider != ''`）；`COALESCE(last_seen, first_seen, 0)` 处理真实数据中 `last_seen` 可能为 NULL 的 fixture；`model ASC` 为复合 PK 成员的确定性 tiebreak。
- 真实证据（§2.1 #3）确认该查询在 yquant 上取 `openai-codex`。

### 3.6 摘要页生成与文件名唯一性

`_create_session_page(conn, session, vault_path)`：

- `created = session["created_at"]`（normalized ISO str）；`date_prefix = datetime.fromisoformat(created).strftime("%Y-%m-%d")`（Python 3.12 支持 `+08:00` 偏移）。
- **文件名**：`page_dir / f"{date_prefix}-{sid}.md"`（`sid` 为完整 session id，如 `2026-08-04-20260804_071750_43a935ba.md`）。**禁止** `sid[:8]` 截断（同日内冲突）；禁止覆盖已存在文件（同一 session 因 manifest 幂等不会重写；若文件已存在但不在 manifest，视为异常 E-004 或由实现选择 fail-stop，二选一并在测试锁定）。
- frontmatter 保持 SPEC §4.3 全字段（title/created/type/status/memory_type/tier/model/provider/session_id/parent_session_id/msg_count/provenance: ingest），正文保留 `Review status: generated summary, needs human review`。
- secret 扫描（两级，P0 修订）：调用 `scan_for_secrets_detailed(content, str(page_path))`——`blocking` 非空 → `_abort("E-005", 1, f"Secrets detected while ingesting session {sid}: {'; '.join(blocking)}")`（只回显 pattern 名与 sid，不回显 secret 值），不落盘该页；`warnings` 非空 → stderr 输出 `WARNING W-001: <非敏感类别> for session <sid>`（不回显值/原文）、计数进 frontmatter `security_warnings`，页正常落盘（详见 §3.9）。

### 3.7 错误分类与退出码（`IngestError` / `_abort`）

```python
class IngestError(SystemExit):
    """契约错误：code ∈ E-001..E-007；exit_code 为进程退出码。"""
    def __init__(self, code: str, exit_code: int, message: str):
        super().__init__(exit_code)
        self.code = code
        self.exit_code = exit_code
        self.message = message

def _abort(code: str, exit_code: int, message: str) -> None:
    import sys
    print(f"ERROR {code}: {message}", file=sys.stderr)
    raise IngestError(code, exit_code, message)
```

| 分类 | 触发点（本文件内） | 退出码 |
|---|---|---|
| E-000 | 正常返回 `count`（含 Ingested 0） | 0 |
| E-001 | `_detect_schema_variant`：表缺失 / messages 缺列 | 1 |
| E-002 | `_detect_schema_variant`：无 `created_at` 且无 `started_at` | 1 |
| E-003 | `_sessions_query`/SQL 执行捕获到 `sqlite3.Error`（适配缺陷） | 1 |
| E-004 | vault 写失败（`_create_session_page`/`_write_transcript`/`_record_ingested` 的 OSError） | 1 |
| E-005 | secret 扫描命中 **blocking 真实凭据**（§3.9：私钥/provider 格式/JWT/Bearer/AWS/Google/可证明 credential-value 形态） | 1 |
| E-006 | `sqlite3.connect(mode=ro)` 抛 `sqlite3.Error`（只读打开失败）；entrypoint 侧 brain 不可执行亦标 E-006（§4） | 1 |
| E-007 | `since_cursor` 非 ISO-8601（`datetime.fromisoformat` 失败） | 3 |
| W-001 | secret 扫描命中 **non-blocking warning**（§3.9：探测/状态字段、redacted marker、布尔/枚举/短值形态） | 0 |

- **为什么继承 `SystemExit`**：`cli.py` 不在 allowlist；`ingest_sessions` 命令对异常只有「未捕获 → 退出 1」路径。`SystemExit` 子类可直接把 `exit_code`（含 E-007 的 3）传播到进程，`cli.py` 零改动。`pytest.raises(IngestError)` 可捕获并断言 `code`/`exit_code`。
- **W-001 不走 `IngestError`**：warning 不中止、不改退出码；由 ingest 流程计数并输出 `WARNING W-001: ...` stderr 行后继续（exit 0）。
- 现有 `ValueError("Unsupported sessions schema; missing columns: ['created_at']")` 路径全部由 `_abort` 取代；stderr 行格式固定为 `ERROR E-00X: <message>`，供 cron/entrypoint/脚本机器可读。

### 3.8 不修改 `cli.py` 的边界说明

`cli.py` 的 `ingest_sessions`（未改动）：`state_db.exists()` 检查先行（不存在 → click echo `Error: ... not found` + `exit 1`，无 E 标签——保持现状，非零退出已满足「失败显式」）；随后调用 `ingest(...)`。所有契约错误分类由 adapter 承担；`--since` 校验也下沉到 adapter（因为 cli.py 不校验）。README/skill 中若提到 CLI 层行为，以本设计为准。

### 3.9 scanner 模块函数级设计（P0 修订新增）

目标文件：`/home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/r0b0tlabbra1n/security/secret_scan.py`（增量修改）。

#### 3.9.1 数据模型与公共 API

```python
@dataclass(frozen=True)
class ScanResult:
    """两级扫描结果。blocking 非空 → E-005 fail-stop；warnings 非空 → W-001 + 计数。"""
    blocking: list[str]      # 真实凭据 findings（私钥/provider 格式/JWT/Bearer/AWS/Google/可证明 credential-value 形态）
    warnings: list[str]      # 非阻塞安全警告（探测/状态字段、redacted marker、布尔/枚举/短值形态）
```

| 函数 | 签名 | 语义 | 兼容性 |
|---|---|---|---|
| `scan_for_secrets_detailed` | `(content: str, source: str = "<unknown>") -> ScanResult` | **新增**：完整两级扫描（`_SECRET_PATTERNS` blocking + env 分支按值形态分类） | 供 `ingest/hermes_sessions.py` 使用 |
| `scan_for_secrets` | `(content: str, source: str = "<unknown>") -> list[str]` | 保持：**仅返回 blocking findings**（`ScanResult.blocking`）；env 分支中仅 credential-value 形态计入 | 向后兼容；`vault/lint.py`、`vault/write_ops.py` 行为不变（hard-block） |
| `is_safe` | `(content: str) -> bool` | 保持：`len(scan_for_secrets(content)) == 0` | 向后兼容；warning-only 内容返回 True（不阻断） |
| `classify_env_assignment` | `(key: str, value: str) -> Literal["blocking", "warning", "safe"]` | **新增**（可私有）：env 赋值形态分类器，见 §3.9.2 | 供 env 分支复用，单测直测 |

#### 3.9.2 `classify_env_assignment` 判定规则（顺序短路）

1. `key` 在既有 known-good allowlist（`PATH/HOME/USER/SHELL/LANG/PWD/TERM/DISPLAY/EDITOR/PAGER/HOSTNAME/LOGNAME`）→ `safe`。
2. `key` 命中状态/探测后缀（`_PRESENT` / `_CONFIGURED` / `_ENABLED` / `_DISABLED` / `_ACTIVE` / `_SET` / `_REQUIRED` / `_AVAILABLE` / `_USED`，大小写不敏感）→ 走第 4 步值形态判定（默认 `warning`，除非值本身 credential 形态）。
3. `key.upper()` 不含 `KEY/TOKEN/SECRET/PASSWORD/PASS/AUTH/CREDENTIAL` 任一子串 → `safe`（env 赋值不因 key 名本身产生 finding）。
4. **值形态判定**（credential-value 形态 → `blocking`；否则 `warning`）：
   - `blocking`：值命中 `_SECRET_PATTERNS` 中任一已知格式；或值为高熵不透明串（去引号后长度 ≥16 且含大小写字母+数字混合，或 base64-like 字符集），如 `FOO_TOKEN=<64 高熵>`、`OPENAI_API_KEY="sk-<40字符>"`；
   - `warning`：布尔（`True/False/true/false/1/0/yes/no/on/off`）、枚举/短值（<16 且非高熵）、redacted marker（`***`、`[REDACTED]`、`redacted:...`、`«redacted:...»`）、空值——如 `TOKEN_PRESENT=False`、`KEY_CONFIGURED=0`、`API_KEY="***"`。

> 说明：`TOKEN_PRESENT=False` 的 `False` 为 5 字符短值，即使按现状正则（值 ≥8）本不匹配，本规则仍显式覆盖“探测字段 + 短值/布尔”场景，杜绝任何 env 名敏感词+探测值组合被误判为 blocking（旧 Verify t_d1827953 有效证据）。

#### 3.9.3 ingest 接入点（`hermes_sessions.py` 改动）

- `_create_session_page` / `_write_transcript`：改用 `scan_for_secrets_detailed(content, source)`：
  - `result.blocking` 非空 → `_abort("E-005", 1, ...)`（不回显值，仅 pattern 名 + sid；不落盘该页）；
  - `result.warnings` 非空 → 每条 stderr 输出 `WARNING W-001: <非敏感类别> for session <sid>`（不回显值/原文）；累计 warning 计数传入摘要页 frontmatter（`security_warnings: W`）与 stdout 摘要（`Ingested N sessions (W security warnings).`）。
- 退出码：有 warning 但无 blocking → 正常返回 count（exit 0）。
- `vault/lint.py`、`vault/write_ops.py` **零改动**（继续调用 `scan_for_secrets` 的 blocking-only 语义）。

#### 3.9.4 隐私约束（warning 路径）

- stderr/摘要/frontmatter 只含非敏感计数与类别；**不得**输出 secret 值、探测字段原文、session 原文。
- manifest 结构不变（`{session_id, ingested_at}`），不持久化 warning 明细。

---

## 4. B 组：profile-local entrypoint（每 profile 一份）

### 4.1 文件定名与权限

| profile | 路径 | 类型 | 权限 |
|---|---|---|---|
| yquant | `/home/pascal/.hermes/profiles/yquant/scripts/brain_ingest_sessions.sh` | 新增 bash | `0755`（`chmod +x`） |
| yinglong | `/home/pascal/.hermes/profiles/yinglong/scripts/brain_ingest_sessions.sh` | 新增 bash | `0755` |

选择 bash 而非 python：与 yquant `scripts/` 既有 `.sh`（如 `weekly-hotel-price-scraper.sh`、`daily-global-market-report.sh`）风格一致；无依赖、零导入成本。

### 4.2 脚本内容（yquant 变体；yinglong 仅 `HERMES_HOME` 不同）

```bash
#!/usr/bin/env bash
# YQuant profile-local entrypoint: brain ingest-sessions (canonical absolute CLI).
# 生产固定参数：--hermes-home <本 profile>、--vault /mnt/e/Data/Yinglong/JMap。
# 可选透传：--hermes-home/--vault/--since/--include-transcripts（仅供 Verify/手工；cron 零参数）。
# 透传 brain 退出码；非零时 stderr 输出错误行；绝不吞错。零 PATH 依赖。
set -u

BRAIN="/home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/.venv/bin/brain"
HERMES_HOME="/home/pascal/.hermes/profiles/yquant"
VAULT="/mnt/e/Data/Yinglong/JMap"

if [ ! -x "$BRAIN" ]; then
  echo "ERROR E-006: brain executable not found or not executable: $BRAIN" >&2
  exit 1
fi

"$BRAIN" ingest-sessions --hermes-home "$HERMES_HOME" --vault "$VAULT" "$@"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "ERROR: brain ingest-sessions failed with exit code $rc" >&2
fi
exit "$rc"
```

yinglong 变体仅把 `HERMES_HOME="/home/pascal/.hermes/profiles/yinglong"`，其余逐字一致。

### 4.3 输入/输出/退出码契约

| 项 | 契约 |
|---|---|
| 生产调用 | `brain_ingest_sessions.sh`（无参数）→ 固定 `--hermes-home <profile> --vault /mnt/e/Data/Yinglong/JMap` |
| 可选参数 | `--hermes-home <path>` / `--vault <path>` / `--since <ISO>` / `--include-transcripts`，经 `"$@"` 透传覆盖默认值；仅限 Verify/显式手工 |
| stdout | brain 原样输出（`Ingested N sessions (W security warnings).` 等） |
| stderr | brain 错误原样透传；非零时追加 `ERROR: brain ingest-sessions failed with exit code <rc>`；brain 不可执行时输出 `ERROR E-006: ...`；W-001 warning 行原样透传（不吞没） |
| 退出码 | 与 brain 退出码完全一致（`exit "$rc"`）；brain 不可执行 → 1；**W-001 warning 不影响退出码**（仅 blocking E-005 等非零） |
| 禁止 | 不得修改任何 `config.yaml`；不得读写 `PATH`；不得自行重写 hermes-home/vault 语义（生产零参数路径） |

---

## 5. C 组：cron prompt 接入（两 profile jobs.json）

### 5.1 yquant `~/.hermes/profiles/yquant/cron/jobs.json`（job `7fd3367324c4`，时间表 `45 2 * * *`）

仅改 `prompt` 字段，**精确替换两处子串**：

| 位置 | 现状（原文） | 替换为 |
|---|---|---|
| 首步 ingest 调用 | `先运行 /home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/.venv/bin/brain ingest-sessions --hermes-home /home/pascal/.hermes/profiles/yquant --vault /mnt/e/Data/Yinglong/JMap；` | `先运行 /home/pascal/.hermes/profiles/yquant/scripts/brain_ingest_sessions.sh；若该命令退出码非零，立即中止并向用户报告失败，禁止继续后续步骤、禁止将失败标记为成功；` |
| 末尾 lint/index | `最后运行 brain lint 和 brain build-index。` | `最后运行 /home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/.venv/bin/brain lint 和 /home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/.venv/bin/brain build-index。` |

其余 prompt 文本（候选提炼规则、`jmap_session_capture.py --list/--ack`、frontmatter 约束、`domain: finance` 等）**逐字不变**。

### 5.2 yinglong `~/.hermes/profiles/yinglong/cron/jobs.json`（job `c91202e2a61f`，时间表 `5 2 * * *`）

同样替换两处（路径改为 yinglong）：

- `先运行 /home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/.venv/bin/brain ingest-sessions --hermes-home /home/pascal/.hermes/profiles/yinglong --vault /mnt/e/Data/Yinglong/JMap；` → `先运行 /home/pascal/.hermes/profiles/yinglong/scripts/brain_ingest_sessions.sh；若该命令退出码非零，立即中止并向用户报告失败，禁止继续后续步骤、禁止将失败标记为成功；`
- `最后运行 brain lint 和 brain build-index。` → canonical 绝对路径（同上，yinglong 无差异）。

### 5.3 不变字段与失败不可吞语义

**不变字段**（R-005 前后 diff 必须完全一致）：

```json
schedule, schedule_display, deliver, skills, skill, repeat, enabled, no_agent,
model, provider, provider_snapshot, model_snapshot, base_url, script, context_from,
workdir, origin, enabled_toolsets, name, id
```

`workdir` 保持 yquant=`/home/pascal/workspace/yquant-investment`、yinglong=`/home/pascal/workspace/yq-yinglong`；`updated_at` 由 cron 运行时自然更新（不算字段变更）。

**失败不可吞执行语义**（双保险，P0 修订后 warning 除外）：

1. entrypoint 透传非零退出码（§4.3），cron agent 执行命令时能观察到非零 `rc`；
2. prompt 显式要求「退出码非零 → 立即中止并报告失败，禁止继续、禁止标记成功」——消除 agent 把 ingest 失败当可继续中间步骤的路径（RFC §2.1.3 现状）；
3. R-004 用失败注入验证：entrypoint 指向不存在 hermes-home → 非零 + stderr 分类行；agent 必须输出失败（不产生候选、不 ack、不运行 lint/build-index）。

**W-001 warning 不是失败**（P0 修订）：warning 场景退出码仍为 0，prompt 的「非零即中止」规则不触发；cron agent 对 W-001 只须在报告中提及 warning 计数，不得将其当作失败吞掉或当作成功掩盖。

---

## 6. 持久化设计（对应 SPEC §4.bis）

| 存储对象 | 写入触发点（文件:函数/命令） | 写入字段子集 | 写入前过滤/校验 | 错误处理与回滚 |
|---|---|---|---|---|
| 临时/生产 JMap `sessions/summaries/{date}-{sid}.md` | `r0b0tlabbra1n/ingest/hermes_sessions.py:_create_session_page`（由 `ingest()` 驱动） | frontmatter 全字段（§3.6）+ 可选 `security_warnings: W` | `scan_for_secrets_detailed`（§3.9）：blocking→E-005；warnings→W-001 + 计数；normalized dict 必填字段校验 | E-005 不落盘该页；E-004 中止；幂等由 manifest 保证不覆盖 |
| JMap `_meta/ingestion-manifest.jsonl` | `hermes_sessions.py:_record_ingested` | `{"session_id", "ingested_at"}` 单行 | 仅成功页后追加 | 单行 `open("a")` + 一次 `write()` + close（O_APPEND 原子性）；损坏行被 `_load_ingested` 容忍跳过 |
| JMap `raw/hermes-sessions/{sid}.json`（默认不落盘） | `hermes_sessions.py:_write_transcript`（仅 `--include-transcripts`） | `{metadata.trusted=false, session_id, messages[]}` | `scan_for_secrets`（E-005） | 同摘要页；L3 默认关闭，启用需 Pascal 确认 |
| Hermes `state.db` | — | — | — | **只读**（`file:...?mode=ro`）；零写入、零 schema 变更 |

错误处理映射：连接失败 → E-006；SQL 缺陷 → E-003；vault 磁盘/权限/路径逃逸 → E-004；secret → E-005；时间列缺失 → E-002。所有 fail-stop 均在任何下一次写入前中止，且退出码非零（§3.7）。

---

## 7. 测试策略（可执行）

### 7.1 测试文件与 fixture

- 测试文件：`/home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/tests/test_hermes_session_ingest.py`（增量修改，保留现有 `test_ingest_sessions`/`test_ingest_sessions_since_cursor` 作 upstream 回归）。
- 新增 helper（测试内私有函数）：
  - `_create_real_schema_db(db_path, num_sessions)`：真实 Hermes schema —— `sessions(id TEXT PK, started_at REAL NOT NULL, model TEXT, parent_session_id TEXT)`、`messages(id INTEGER PK AUTOINCREMENT, session_id TEXT, role TEXT, content TEXT)`、`session_model_usage(session_id TEXT, model TEXT, billing_provider TEXT, first_seen REAL, last_seen REAL)`；sid 用真实格式 `20260804_071750_43a935ba`。
  - `_create_no_time_col_db(db_path)`：变体 C —— `sessions(id TEXT PRIMARY KEY)` + `messages` 完整。
  - `_create_usage_rows(conn, sid, rows)`：构造多行 usage 供 provider 优先级测试。

### 7.2 单元测试（对应 SPEC §6.1）

| 编号 | 用例 | 断言 |
|---|---|---|
| U-001a | `_detect_schema_variant` 变体 A（有 `created_at`） | `"upstream"` |
| U-001b | 变体 B（有 `started_at`） | `"hermes"` |
| U-001c | 变体 C | `pytest.raises(IngestError)` 且 `code == "E-002"` |
| U-002 | `_epoch_to_iso(1722733200.5)` | `"2024-08-04T12:00:00.500000+08:00"`（微秒保留、+08:00、`%Y-%m-%d` 正确） |
| U-003 | 真实 schema 列映射（无 usage 行） | `model_name == sessions.model`；`provider_name == "unknown"` |
| U-004 | 确定性排序：同 `started_at` 多 session | 输出按 `(created_at, id)` 稳定；等价断言按 `(started_at, id)` 升序 |
| U-005 | 文件名唯一：同一自然日 3 个真实格式 sid | 3 个不同 `.md`，文件名含完整 sid；无 `sid[:8]` |
| U-006 | provider 优先级：多行 usage 不同 `last_seen` | 取 `COALESCE(last_seen, first_seen, 0)` 最大且非空 `billing_provider` |
| U-007 | `--since` 非法（`"not-an-iso"`） | `pytest.raises(IngestError)`，`code == "E-007"`，`exit_code == 3` |
| U-008 | secret 命中 | `pytest.raises(IngestError)`，`code == "E-005"`；目标页未落盘 |
| U-009 | 两级分类：状态字段→warning | `scan_for_secrets_detailed('TOKEN_PRESENT=False')` 等：`blocking == []`、`warnings` 非空；`is_safe` 为 True |
| U-010 | 两级分类：真实凭据→blocking | `scan_for_secrets_detailed('OPENAI_API_KEY="sk-<40字符>"')` / `FOO_TOKEN=<64 高熵>` / 私钥 / JWT / Bearer / AWS/Google 形态：`blocking` 非空；`is_safe` 为 False |
| U-011 | 公共调用方 hard-block 不变 | `scan_for_secrets` / `is_safe`：blocking credential → 非空/False（lint/write_ops 行为不变）；warning-only → 空/True（不阻断） |
| U-012 | redacted marker→warning | `TOKEN=***` / `API_KEY="«redacted:...»"` / `[REDACTED]`：`blocking == []`、`warnings` 非空 |
| U-013 | env 值形态分类 | `FOO_TOKEN=off`（短值）→ warning；`FOO_TOKEN=<64 高熵>` → blocking；与 `classify_env_assignment` 规则一致 |

### 7.3 fixture 测试（对应 SPEC §6.2）

| 编号 | 用例 | 断言 |
|---|---|---|
| F-001 | 真实 schema 全链路：`_create_real_schema_db(N=3)` + `init_vault(tmp)` → `ingest(db, tmp)` | count==3；summaries 3 个文件；manifest 3 行；frontmatter 溯源字段齐全 |
| F-002 | upstream 向后兼容：现有 fixture（`created_at`） | count==3（现有测试不回归） |
| F-003 | 变体 C fail-stop | 非零/`IngestError E-002`；vault 零写入（`summaries/` 为空、manifest 不存在或 0 行） |
| F-004 | 幂等：F-001 后再次 ingest | `Ingested 0 sessions`（count==0）；无重复页、manifest 行数不变 |
| F-005 | cursor：`since_cursor` 取中间 ISO | 仅返回其后 session；同值边界重复扫描由 manifest 跳过（不产生重复页） |
| F-006 | secret 命中（E-005） | 同 U-008 但走完整 `ingest()` |
| F-007 | `include_transcripts=True` | `raw/hermes-sessions/{sid}.json` 生成，`metadata.trusted == false` |
| F-008 | 状态字段 warning（P0 修订） | `_create_real_schema_db` 的 messages 注入 `TOKEN_PRESENT=False` / `KEY_CONFIGURED=0` 探测行 → 完整 `ingest()`：count==N 全部落盘（含该 session 页）；stderr 含 `WARNING W-001`；stdout 摘要含 warning 计数；退出 0；frontmatter `security_warnings ≥ 1`；manifest N 行 |

### 7.4 真实只读 smoke（SPEC §6.3 R 组，两 profile 对称）

前置：确认当前无 cron 在运行（yquant `45 2 * * *` / yinglong `5 2 * * *` 不在执行窗口）；所有 smoke 用 `mktemp -d` 临时 vault，**绝不指向真实 JMap**。

R-001/R-002（每 profile 一次）：

```bash
tmp=$(mktemp -d)
before=$(sha256sum /home/pascal/.hermes/profiles/<p>/state.db \
        /home/pascal/.hermes/profiles/<p>/state.db-wal \
        /home/pascal/.hermes/profiles/<p>/state.db-shm 2>/dev/null | sha256sum)
/usr/bin/env python3 - <<'PY'
import sqlite3
p='<p>'; c=sqlite3.connect(f'file:/home/pascal/.hermes/profiles/{p}/state.db?mode=ro', uri=True)
print('sessions', c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0])
print('messages', c.execute('SELECT COUNT(*) FROM messages').fetchone()[0])
PY
/home/pascal/.hermes/profiles/<p>/scripts/brain_ingest_sessions.sh --vault "$tmp"
rc=$?
after=$(sha256sum /home/pascal/.hermes/profiles/<p>/state.db \
        /home/pascal/.hermes/profiles/<p>/state.db-wal \
        /home/pascal/.hermes/profiles/<p>/state.db-shm 2>/dev/null | sha256sum)
echo "rc=$rc before=$before after=$after"
ls -1 "$tmp/sessions/summaries" | wc -l
```

断言：`rc==0`；`before==after`；行数前后一致；临时 vault 出现摘要页且文件名含完整 sid；真实 JMap 哈希不变（§7.5）。**R-002 额外断言（P0 修订）**：yinglong 含 `TOKEN_PRESENT` 探测字段的 session（`20260720_232434_b1bcf1`）产生 W-001 warning 而非 E-005；stderr 含 `WARNING W-001`；临时 vault **完整生成**（全部 session 摘要页，含该 sid）；stdout 摘要含 warning 计数。

R-003 对称性：R-001/R-002 结果（退出码、错误分类、无真实写）两 profile 一致；生成汇总表。

R-004 失败注入（吞错禁止）：

```bash
/home/pascal/.hermes/profiles/<p>/scripts/brain_ingest_sessions.sh \
  --hermes-home /nonexistent/nowhere ; echo "rc=$?"
# 期望：非零退出；stderr 含 "ERROR"（E-006 或 cli 的 not found 行）；stdout 无 "Ingested N sessions."
```

再验证 cron agent 行为：手工按新 prompt 执行一次（或对 entrypoint 注入失败后询问 agent 是否继续后续步骤）——必须输出失败、不产生候选、不 ack、不运行 lint/build-index。

R-005 cron 配置不变：Implement 前 `cp jobs.json /tmp/jobs.json.<p>.before`；Implement 后对比：

```bash
/usr/bin/env python3 - <<'PY'
import json
b=json.load(open('/tmp/jobs.json.yquant.before'))['jobs']; a=json.load(open('/home/pascal/.hermes/profiles/yquant/cron/jobs.json'))['jobs']
bm={j['id']:j for j in b}; am={j['id']:j for j in a}
for jid in ('7fd3367324c4',):
    for k in ('schedule','schedule_display','deliver','skills','skill','repeat','enabled','no_agent','model','provider','workdir','script','context_from','name'):
        assert bm[jid][k]==am[jid][k], f'{jid}.{k} changed'
    assert bm[jid]['prompt']!=am[jid]['prompt']
print('yquant cron immutable fields OK; prompt changed')
PY
```

（yinglong 用 `c91202e2a61f` 同理。）

R-007 真实凭据 fail-stop（P0 修订）：

```bash
tmp=$(mktemp -d)
# 临时 vault 中构造含真实凭据形态的 fixture 消息（如 sk-<40字符>、-----BEGIN ... PRIVATE KEY-----、eyJ...JWT）
/home/pascal/.hermes/profiles/<p>/scripts/brain_ingest_sessions.sh --vault "$tmp" --since <该 fixture 时间之前>
# 期望：非零退出（E-005）；含凭据的 session 页不落盘；其余 session 摘要页不受影响；真实 JMap/state.db/queue 哈希不变
```

R-006 回滚演练（放在所有测试之后执行，最后恢复实现状态供 Review 审阅）：

```bash
# 1) 快照实现态
cd /home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n && git stash push -m design-10-011-verify \
    -- r0b0tlabbra1n/ingest/hermes_sessions.py tests/test_hermes_session_ingest.py \
       r0b0tlabbra1n/security/secret_scan.py tests/test_secret_scan.py
cp /home/pascal/.hermes/profiles/yquant/scripts/brain_ingest_sessions.sh /tmp/brain_ingest_sessions.yquant.sh
cp /home/pascal/.hermes/profiles/yinglong/scripts/brain_ingest_sessions.sh /tmp/brain_ingest_sessions.yinglong.sh
cp /home/pascal/.hermes/profiles/yquant/cron/jobs.json /tmp/jobs.json.yquant.after
cp /home/pascal/.hermes/profiles/yinglong/cron/jobs.json /tmp/jobs.json.yinglong.after
# 2) 回滚
git -C /home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n stash drop   # = revert A（等价 git checkout --）
rm -f /home/pascal/.hermes/profiles/yquant/scripts/brain_ingest_sessions.sh \
      /home/pascal/.hermes/profiles/yinglong/scripts/brain_ingest_sessions.sh
cp /tmp/jobs.json.yquant.before /home/pascal/.hermes/profiles/yquant/cron/jobs.json
cp /tmp/jobs.json.yinglong.before /home/pascal/.hermes/profiles/yinglong/cron/jobs.json
# 3) 断言恢复原状：r0 两文件无 diff；entrypoint 不存在；jobs.json 与 .before 一致；JMap/queue 哈希不变
# 4) 恢复实现态（供 Review）
git -C /home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n stash pop
cp /tmp/brain_ingest_sessions.yquant.sh /home/pascal/.hermes/profiles/yquant/scripts/brain_ingest_sessions.sh
cp /tmp/brain_ingest_sessions.yinglong.sh /home/pascal/.hermes/profiles/yinglong/scripts/brain_ingest_sessions.sh
cp /tmp/jobs.json.yquant.after /home/pascal/.hermes/profiles/yquant/cron/jobs.json
cp /tmp/jobs.json.yinglong.after /home/pascal/.hermes/profiles/yinglong/cron/jobs.json
```

### 7.5 不变检查命令（JMap / state.db / queue）

```bash
# 真实 JMap 聚合哈希（前后各跑一次，必须相等）
find /mnt/e/Data/Yinglong/JMap -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum
ls -la /mnt/e/Data/Yinglong/JMap/sessions/summaries | wc -l
stat -c %s /mnt/e/Data/Yinglong/JMap/_meta/ingestion-manifest.jsonl
# session queue 哈希（前后各跑一次，必须相等）
sha256sum /home/pascal/.hermes/profiles/{yquant,yinglong}/state/jmap-candidate-queue.jsonl 2>/dev/null
# Hermes SQLite 三件套哈希 + 行数（§7.4 R-001/R-002 已含）
```

### 7.6 测试命令清单（Verify 阶段执行顺序）

```bash
# 1) r0 单测 + fixture（含 scanner 两级分类）
cd /home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n \
  && .venv/bin/python -m pytest tests/test_hermes_session_ingest.py tests/test_secret_scan.py -v
# 2) 真实只读 smoke × 2 profile（§7.4 R-001~R-004、R-007）
# 3) 不变检查（§7.5）
# 4) cron 配置不变（R-005）
# 5) 回滚演练（R-006，最后执行，随后恢复实现态）
# 6) 文档自检（Design 完成前，§9.2）
```

### 7.7 停止条件（fail-stop 判据）

| 条件 | 判定 |
|---|---|
| 任一 r0 单测/fixture 失败 | FAIL → block |
| R-001/R-002 退出码非零或临时 vault 页数异常 | FAIL → block |
| **R-002 将状态字段误判为 E-005（应 W-001 warning）**（P0 修订） | FAIL → block（两级分类未生效） |
| R-007 真实凭据未 E-005 / 该页落盘 | FAIL → block（blocking 语义被削弱） |
| state.db / `-wal` / `-shm` 哈希或行数变化 | FAIL → block（只读红线违反） |
| 真实 JMap 聚合哈希变化 / summaries 计数增加 / manifest 字节变化 | FAIL → block（真实写违反） |
| queue 哈希变化 | FAIL → block |
| cron `schedule`/`deliver`/`skills`/`workdir`/`repeat` 任一变化（R-005） | FAIL → block |
| 失败注入后 cron agent 仍继续/标记成功（R-004） | FAIL → block（吞错红线） |
| 实现超出 §1.2 allowlist（如改 cli.py、config.yaml、PATH） | FAIL → block |

---

## 8. 实现顺序（Implement 阶段）

1. A 组-前置（P0 修订）：改 `security/secret_scan.py`（§3.9 两级分类）→ 改 `tests/test_secret_scan.py`（U-009~U-013）→ 跑 scanner 单测全绿。
2. A 组：改 `hermes_sessions.py`（§3，接入两级扫描）→ 改 `tests/test_hermes_session_ingest.py`（§7.2/§7.3，含 F-008）→ 跑单测全绿。
3. B 组：写两份 entrypoint（§4），`chmod +x`；`bash -n` 语法检查。
4. C 组：备份两 `jobs.json`（`/tmp/jobs.json.<p>.before`）→ 按 §5 精确替换 prompt → R-005 对比脚本确认仅 prompt 变化。
5. 手工 smoke：`--vault $(mktemp -d)` 对两 profile 各跑一次（§7.4 R-001/R-002），确认真实 JMap/state.db/queue 哈希不变；R-007 真实凭据 fail-stop。
6. 失败注入（R-004）、不变检查（§7.5）。
7. 回滚演练（R-006）→ 恢复实现态。
8. 输出变更汇总 + 测试报告（含 E-001~E-007 + W-001 覆盖表、两 profile 对称表、哈希前后对照）。

---

## 9. 回滚流程（一次性且精确）

仅允许退回 A/B/C 三组改动；**不得删除 JMap 任何内容（含本卡后产生的 summaries/manifest 行）与 session queue**。

| 步 | 动作 | 命令 | 验证 |
|---|---|---|---|
| 1 | 回滚 A（r0 adapter + scanner + 测试） | `git -C /home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n checkout -- r0b0tlabbra1n/ingest/hermes_sessions.py tests/test_hermes_session_ingest.py r0b0tlabbra1n/security/secret_scan.py tests/test_secret_scan.py`（若已提交则 `git revert <commit>` 仅限这四文件；**不含** `tests/fixtures/eval-vault/_meta/source-hashes.json`） | `git -C <r0> status --short` 仅剩既有的 `source-hashes.json` dirty；原单测仍绿 |
| 2 | 回滚 B（entrypoint） | `rm -f /home/pascal/.hermes/profiles/yquant/scripts/brain_ingest_sessions.sh /home/pascal/.hermes/profiles/yinglong/scripts/brain_ingest_sessions.sh` | 文件不存在 |
| 3 | 回滚 C（cron prompt） | `cp /tmp/jobs.json.yquant.before /home/pascal/.hermes/profiles/yquant/cron/jobs.json`（yinglong 同理） | diff 为空 |
| 4 | 终检 | §7.5 全部哈希对照 | JMap/queue/state.db 零变化 |

回滚后的系统状态 = 现状（ingest 仍会失败但不再新增任何行为），这正是「仅退本 adapter + entrypoint 改动」的契约语义；不删除 JMap/queue（RFC §3.1 回滚契约）。

---

## 10. 风险、降级与并发/WAL 边界

| 风险 | 概率 | 影响 | 应对 | 降级 |
|---|---|---|---|---|
| 1.6 GB state.db 只读打开慢 / WAL 快照 | 中 | 低 | `mode=ro` URI；SQLite WAL 天然支持并发读；按 session 精确查询（`idx_messages_session`、`idx_session_model_usage_session`） | E-006 显式暴露；不做影子拷贝 |
| 两 cron（02:05/02:45）同 vault 并发写 manifest | 低 | 低 | 不同 profile 不同 DB → session id 全局唯一，摘要页不可能同名；manifest 单行 `open("a")` 一次 `write()` + close（POSIX O_APPEND 小行原子）；`_load_ingested` 容忍损坏行 | 若罕见交错致一行坏 → 该行被跳过，次日幂等重扫兜底，不丢数据 |
| started_at 与 id 内嵌时间时区偏差 | 已实证 | — | §2.2 关闭 Q-1：+08:00 固定 | Verify R 组再核对一次 |
| cron agent 仍吞错 | 中 | 高 | entrypoint 透传退出码 + prompt 硬性中止语义（§5.3）；R-004 注入验证 | Review 核对 cron 输出；关闭吞错路径 |
| provider 派生不完整 | 中 | 低 | `"unknown"` 兜底 + 摘要页明确标注 | 不影响 ingest 成功 |
| 未来 Hermes schema 再变 | 低 | 中 | 变体检测先行：`created_at` 存在即优先 | E-001/E-002 fail-stop |
| r0 上游版本漂移 | 低 | 中 | 适配集中在单文件 | git revert 单文件，JMap/队列零接触 |
| 真实 JMap 被 Verify 误写 | 低 | 高 | 所有 smoke 强制 `mktemp -d`；§7.5 哈希哨兵 | FAIL → block |
| 两级分类误判新形态（P0 修订） | 低 | 中 | 值形态分类器 + 状态后缀列表显式覆盖布尔/枚举/redacted/短值；U-009~U-013 锁定 | 若出现新误判，扩展分类器（warning 路径），不放松 blocking 语义；Review 复核分类表 |

**WAL 边界**：禁止对真实 state.db 执行 `PRAGMA journal_mode`、checkpoint、`VACUUM` 或任何写；`mode=ro` 连接在 gateway 运行中读取安全（WAL 快照隔离）。可选项（防御性）在 adapter 连接后执行 `PRAGMA query_only=ON`——这是只读 pragma，不改变源库，是否加由 Implement 自行判断，不改变契约。

---

## 11. 隐私与授权边界

- **L2**：摘要页只含前 180 字摘录与元数据；`scan_for_secrets_detailed` blocking 命中 → E-005 不落盘；stderr 只回显 pattern 名 + sid，不回显 secret 值。
- **W-001 warning 路径（P0 修订）**：warning 只以非敏感计数可见（stderr `WARNING W-001` 行 / stdout 摘要 `(W security warnings)` / frontmatter `security_warnings`）；**不得**输出 secret 值、探测字段原文、session 原文；manifest 不持久化 warning 明细。
- **L3**：raw transcript 默认不落盘（`--include-transcripts` 关闭）；SPEC §4.bis 明确启用需 Pascal 确认，本卡不启用。
- **授权边界**：本卡 Verify 全程真实 JMap 只读（哈希哨兵）；真实 JMap 的首次 ingest 写入只由既有 cron（02:05/02:45，Pascal 已授权排程）在 Review/Closeout 后触发，不在本卡内执行。
- 不得在任何 task summary/metadata/评论中记录真实 secret 或凭据。

---

## 12. r0 skill/README 更新决策（RFC Q-3）

**本卡不纳入** `r0 hermes/skills/llm-wiki-brain/SKILL.md` 与 r0 README 的文档更新。理由：

1. **非必要**：canonical 解析已由 entrypoint 强制（§4），skill 文档中过时的 `brain ingest-sessions --hermes-home ~/.hermes` 描述不影响任何运行时行为；
2. **范围收敛**：RFC/SPEC allowlist 的 A/B/C 三组均为代码/配置，未授权文档文件；纳入会无边界扩大 diff；
3. **测试影响为零**：文档改动不进任何测试路径，可独立走文档卫生任务。

后续建议：Closeout 后开独立轻量任务，把 `llm-wiki-brain/SKILL.md` 的 ingest-sessions 示例改为 canonical 绝对路径 + 两 profile entrypoint 引用，并同步 r0 README。

---

## 13. 交接给实现者

**必须遵守**：
- 只动 §1.2 allowlist 内文件（含 P0 修订新增的 `secret_scan.py`、`test_secret_scan.py`）；禁止触碰 §1.2 禁止清单（尤其 `cli.py`、`config.yaml`、state.db、真实 JMap、PATH、`source-hashes.json`）。
- `mode=ro` 只读连接；零写入 Hermes SQLite；零 schema 变更。
- E-001~E-007 + W-001 全部实现并有测试；stderr 行格式 `ERROR E-00X: <message>` / `WARNING W-001: <message>`。
- **两级扫描（P0 修订）**：blocking（真实凭据）→ E-005 不落盘、exit 1；warning（探测/状态字段、redacted、布尔/枚举/短值）→ W-001 + 计数、exit 0、页落盘；`scan_for_secrets`/`is_safe` 向后兼容，`vault/lint.py`、`vault/write_ops.py` 零改动（hard-block 不变）。
- warning 可观测但不回显值/原文；摘要页 frontmatter `security_warnings` 仅计数；manifest 结构不变。
- 文件名必须用完整 session id；保持 `(created_at,id)` 排序语义、标量 cursor、manifest 幂等。
- entrypoint 生产零参数路径固定 hermes-home/vault；退出码原样透传（W-001 不影响退出码）；非零 stderr 输出错误行。
- cron prompt 只按 §5 精确替换；`schedule`/`deliver`/`skills`/`workdir`/`repeat` 等字段一字不动。
- 真实 JMap 只读；所有写向临时 vault。
- **Supersede**：旧 T4 Verify（`t_d1827953`）被本修订 supersede，其 FAIL 是有效证据不得改写为 PASS；新 Verify 必须重新独立执行。
- 完成后状态选择：验收全 PASS → `kanban_complete(status="done", summary=..., metadata={residual_risks:[...]})`；任何验收 FAIL → `block` 写明哪条 FAIL + 期望 vs 实际；不因非阻塞残余风险 block。

**可自行判断**：
- 内部 helper 命名与组织（保持 §3.1 函数级契约与签名不变）；
- 是否在 adapter 加 `PRAGMA query_only=ON` 防御；
- 测试 fixture 的具体行数与真实 id 样本；
- 错误消息措辞（前缀与分类编号固定）。

**遇到以下情况退回 Principal**：
- 需要修改 `cli.py`、config.yaml、PATH 或任何禁止清单文件（含 `source-hashes.json`）才能实现契约；
- 发现 SPEC §4.2 provider 派生与真实数据冲突（如 `session_model_usage` 结构性缺失）；
- 真实 smoke 显示时区/日期前缀与预期不符（Q-1 复核失败）；
- 两级分类与真实数据冲突（如真实 session 中出现新的探测/状态字段形态导致误判，或 blocking/warning 判定与 SPEC 附录 C 速查表不一致）；
- 任何 allowlist 需要扩大。

---

## 14. 参考资料

- RFC-10-011（V0.2）：`docs/rfc/10_infra/RFC-10-011-r0-brain-cli-session-ingest-compatibility.md`
- SPEC-10-011（V0.2）：`docs/spec/10_infra/SPEC-10-011-r0-brain-cli-session-ingest-compatibility.md`
- r0 现状实现：`r0b0tlabbra1n/ingest/hermes_sessions.py`、`r0b0tlabbra1n/cli.py`、`r0b0tlabbra1n/security/secret_scan.py`、`tests/test_hermes_session_ingest.py`、`tests/test_secret_scan.py`
- Hermes schema 权威定义：`/home/pascal/workspace/hermes-agent/hermes_state_common.py`（`SCHEMA_SQL`）
- 两 profile cron：`~/.hermes/profiles/{yquant,yinglong}/cron/jobs.json`
- JMap vault：`/mnt/e/Data/Yinglong/JMap`（`_meta/ingestion-manifest.jsonl`、`sessions/summaries/`）
- 只读 probe 脚本（本卡实证）：`/tmp/probe_state_db_schema.py`、`/tmp/probe_q1_timezone.py`（临时，不属交付物）
