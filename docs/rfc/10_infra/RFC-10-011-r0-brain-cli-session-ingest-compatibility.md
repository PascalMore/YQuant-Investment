# RFC-10-011：r0 Brain CLI 统一入口与 Hermes session 导入兼容

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-08-04 |
| 最后更新 | 2026-08-04 |
| 版本号 | V0.2 |
| 所属模块 | 10_infra（基础设施 / 知识管理） |
| 依赖RFC | 无（独立引入；与 RFC-10-003 infra 架构无冲突） |
| 关联SPEC | [SPEC-10-011-r0-brain-cli-session-ingest-compatibility](../../spec/10_infra/SPEC-10-011-r0-brain-cli-session-ingest-compatibility.md)（V0.2） |
| 关联Design | [DESIGN-10-011-r0-brain-cli-session-ingest-compatibility](../../design/10_infra/DESIGN-10-011-r0-brain-cli-session-ingest-compatibility.md)（V0.2） |
| 替代RFC | 无 |
| AI适配 | Hermes Kanban profile worker（yquantprincipal → yquantdeveloper → yquanttester → yquantreviewer） |
| 标签 | #infra #brain #hermes #ingest #schema-compat #jmap #cron |

## 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-08-04 | 初始创建：定义 Brain 统一入口解析规则、ingest-sessions 对 Hermes schema 的只读兼容读取策略、时间/cursor 语义、summary 可追溯性与候选生成安全边界、双 profile 对称验收与回滚契约 | YQuant-Principal |
| V0.2 | 2026-08-04 | **P0 修订（Option A，替代失败 Verify t_d1827953 的前置阶段）**：secret 扫描升级为两级结果（blocking 真实凭据 vs non-blocking warning）；E-005 仅在命中具体、可识别的真实凭据值/密钥材料时 fail-stop；`TOKEN_PRESENT`/`KEY_CONFIGURED` 等探测/状态字段降级为 warning 并允许 ingest 继续；定义 warning 可观测性（W-001 + summary 计数）与 scanner API 契约；Implement allowlist 新增 `r0b0tlabbra1n/security/secret_scan.py` 与 `tests/test_secret_scan.py`（仅此两项），并明确 `tests/fixtures/eval-vault/_meta/source-hashes.json` 不可修改；明确旧 T4 Verify（t_d1827953）被本修订 supersede，新 Verify 必须重新独立执行，旧 FAIL 不自动解除 | YQuant-Principal |

---

## 1. 执行摘要

当前两个 Hermes profile（`yquant`、`yinglong`）每日自动候选提炼 cron 的第一步都调用 `brain ingest-sessions`，但 r0 的 `r0b0tlabbra1n/ingest/hermes_sessions.py` 硬性要求 `sessions.created_at` 字段，而真实 Hermes `state.db` 的 `sessions` 表没有该字段（时间字段为 `started_at REAL`），导致 ingest 必然失败（实测 exit=1、`ValueError: missing columns: ['created_at']`），JMap 的 `sessions/summaries/` 至今为空、`_meta/ingestion-manifest.jsonl` 为 0 字节。同时裸 `brain` 不在 PATH 中，自动化只能依赖专用绝对路径，缺少统一、可验证的入口契约。

本 RFC 定义一个最小、可验证的契约：**单一 canonical Brain 命令解析规则**（禁止依赖裸 `brain` PATH）、**ingest-sessions 对 Hermes schema 的只读兼容读取策略**（保留 read-only、幂等、确定性排序/cursor 语义，禁止 schema migration、禁止向 Hermes SQLite 写入）、**session summary 来源/时间可追溯字段与候选生成安全边界**、**两 profile 对称验收准则**（YQuant / Yinglong 各自 dry-run / fixture / 真实只读 smoke），并固化 cron 时间表与投递策略不变、禁止吞错报成功、以及"仅退回 r0 adapter + profile-local entrypoint 改动"的回滚契约。后续 Design/Implement 阶段据此落地。

**P0 修订（V0.2，Option A）**：r0 `secret_scan.py` 的 env 分支对 key 名含 `KEY/TOKEN/SECRET/PASSWORD/PASS/AUTH/CREDENTIAL` 的任意值无条件返回 blocking issue，导致真实 yinglong session 中的探测/状态字段（如 `TOKEN_PRESENT=False`，2026-07-20 排查回执，非 secret 值）被误判为 secret 并触发 E-005；独立 Verify（`t_d1827953`）确认 yinglong R-002 rc=1 与 SPEC「退出 0」契约不可调和。本修订按 Pascal 选定的 Option A 收紧 E-005：**仅当发现具体、可识别的真实凭据值/密钥材料时 fail-stop**；`TOKEN_PRESENT`/`KEY_CONFIGURED` 等探测/状态字段降级为**非阻塞 warning**，ingest 继续并产生可观测的安全警告（W-001 + 非敏感计数）。三层文档同步升 V0.2，scanner 实现 allowlist 相应扩展（新增 `security/secret_scan.py` 与 `tests/test_secret_scan.py`）。

---

## 2. 背景与动机

### 2.1 现状痛点

#### 2.1.1 ingest-sessions 与真实 Hermes schema 不兼容

r0 `r0b0tlabbra1n/ingest/hermes_sessions.py` 的 `_validate_schema()` 要求 `sessions` 表必须同时存在 `id` 与 `created_at` 两列；随后 `SELECT id, created_at, parent_session_id, model_name, provider_name FROM sessions ... ORDER BY created_at ASC`。而真实 Hermes `state.db`（来源：`/home/pascal/workspace/hermes-agent/hermes_state_common.py` 的 `SCHEMA_SQL`）的 `sessions` 表：

- **没有 `created_at`**；时间字段是 `started_at REAL NOT NULL`（Unix epoch 秒）与 `ended_at REAL`；
- 模型列名是 **`model`**（不是 `model_name`）；
- **没有 `provider_name`**；provider 信息存于关联表 `session_model_usage.billing_provider`（及 `sessions.model_config` JSON）；
- 存在 `parent_session_id TEXT`、`messages` 表存在 `session_id / role / content / timestamp REAL`。

结论：即使补上 `created_at`，原 `SELECT` 仍会因 `model_name` / `provider_name` 不存在而失败。兼容读取必须同时处理列名映射与 provider 来源，仅加一列不解决问题。

#### 2.1.2 裸 `brain` 不可依赖

实测 `which brain` 未命中（不在 PATH）。可用的唯一入口是专用绝对路径 `/home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/.venv/bin/brain`（`brain, version 0.1.0`）。r0 包在该 venv 中为 **editable 安装**（`__editable__.r0b0tlabbra1n-0.1.0.pth`），修改仓库源码即时生效、无需重装。当前 cron 与 `knowledge` skill 已经在使用该绝对路径（事实上的既定模式），但 `llm-wiki-brain` skill 文档仍写 `brain ingest-sessions --hermes-home ~/.hermes`（默认指向 default profile，语义不一致）。缺少一个统一的、profile 感知的解析规则。

#### 2.1.3 cron 吞错风险

两个每日候选提炼 cron（YQuant `7fd3367324c4` 每日 02:45；Yinglong `c91202e2a61f` 每日 02:05）的 prompt 第一步都内联调用 `brain ingest-sessions`。实测该命令必然失败，但 cron `last_status` 仍为 `ok`，说明 agent 层把 ingest 失败当作可继续的中间步骤，存在"吞错报成功"的路径——违背"失败必须显式暴露"的可观测性原则。

#### 2.1.4 附加兼容缺陷（同日内页面文件名冲突）

真实 Hermes session id 形如 `20260802_082716_1dcbdfdd`（`日期_时间_随机后缀`）。r0 `_create_session_page()` 生成文件名 `{date_prefix}-{sid[:8]}.md`，其中 `sid[:8]` 恰好是日期（如 `20260802`），导致**同一自然日的所有 session 会写入同一文件名并静默互相覆盖**。r0 自带测试 fixture 的 sid（`test-session-0000`）掩盖了该问题。适配必须修复文件名唯一性，否则摘要页会丢失。

#### 2.1.5 secret 扫描对状态字段误判（E-005 过宽，P0 修订触发点）

r0 `r0b0tlabbra1n/security/secret_scan.py` 的 env 分支（`([A-Z_]{3,})=["']?([^"'\n]{8,})["']?`）对 key 名包含 `KEY/TOKEN/SECRET/PASSWORD/PASS/AUTH/CREDENTIAL` 任一子串的**任意值**无条件返回 blocking issue（`Env secret variable: <key>`）。真实 yinglong session `20260720_232434_b1bcf1` 的 3 条消息包含 `TOKEN_PRESENT`（2026-07-20 排查 t_d299a658 真伪的探测回执，非 secret 值）即命中该分支，触发 E-005 fail-stop。独立 Verify（`t_d1827953`）确认：yquant R-001 rc=0、yinglong R-002 rc=1，根因仅为状态字段误判；SPEC R-002 要求 rc=0、DESIGN 亦规定非零为 FAIL——**契约不可调和**。Pascal 选定 Option A：收紧 E-005 语义（仅真实凭据值/密钥材料阻断），探测/状态字段降级为 warning 并允许 ingest 继续。

### 2.2 实测证据（2026-08-04 复核）

| # | 事实 | 证据 |
|---|---|---|
| 1 | 真实 Hermes sessions 无 `created_at`，有 `started_at REAL NOT NULL`、`model`、无 `provider_name`；provider 在 `session_model_usage.billing_provider` | `hermes_state_common.py` SCHEMA_SQL（权威 schema） |
| 2 | `brain ingest-sessions` 对 yquant / yinglong 真实 state.db 均失败 | 实测：`ValueError: Unsupported sessions schema; missing columns: ['created_at']`，EXIT=1，vault 零写入 |
| 3 | 裸 `brain` 不在 PATH；绝对路径入口可用（0.1.0） | `which brain` 未命中；`.venv/bin/brain --version` 正常 |
| 4 | 两 profile 的 cron 均用绝对路径调用 ingest | `~/.hermes/profiles/{yquant,yinglong}/cron/jobs.json` |
| 5 | 两 profile 均配置 `on_session_end -> jmap_session_capture.py`，hook 只入队、不运行 Brain | 两 profile `config.yaml` `hooks.on_session_end`；hook 源码为 queue-only |
| 6 | 两 profile 均在 `skills.external_dirs` 加载 r0 `hermes/skills`（含 `llm-wiki-brain`） | 两 profile `config.yaml` `skills.external_dirs` |
| 7 | JMap 从未成功 ingest：`_meta/ingestion-manifest.jsonl` 0 字节；`sessions/summaries/` 为空；无 `raw/hermes-sessions/` | `/mnt/e/Data/Yinglong/JMap` 只读检查 |
| 8 | yquant state.db 约 1.6 GB、yinglong 约 172 MB，均 WAL 模式（`-wal`/`-shm` 存在） | `ls -la` 两 profile 目录 |
| 9 | r0 `secret_scan.py` env 分支对 key 名含 `KEY/TOKEN/SECRET/PASSWORD/PASS/AUTH/CREDENTIAL` 的任意值无条件返回 blocking issue；真实 yinglong session 的 `TOKEN_PRESENT` 探测回执触发 E-005 | 独立 Verify t_d1827953：yquant R-001 rc=0、yinglong R-002 rc=1（仅状态字段误判）；r0 源码 `r0b0tlabbra1n/security/secret_scan.py` 行 82-86 |

### 2.3 业务价值

- **恢复知识沉淀链路**：候选提炼 cron 的第一步（session → JMap summary）真正可用，`sessions/summaries/` 开始积累，候选提炼与 `knowledge` skill 工作流恢复完整闭环。
- **可观测**：ingest 失败以非零退出码 + stderr 显式暴露，cron 不再静默吞错；两个 profile 行为对称、可独立验证。
- **可维护**：唯一 canonical 入口 + 单一 r0 侧适配，避免每个 profile 各自复制逻辑；不触碰 Hermes core、不迁移 schema、不写 Hermes SQLite。
- **零风险回滚**：变更面收敛为 r0 adapter + profile-local entrypoint（+ cron prompt 接入），回滚不触碰 JMap 内容与 session 队列。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 定义单一 canonical Brain command resolution：自动化 / Skill / 脚本不得依赖裸 `brain` PATH；明确允许的入口形式与失败语义。
- [ ] `ingest-sessions` 对 Hermes schema 的兼容读取策略：保留 read-only、幂等、确定性排序 / cursor 语义；明确旧 schema 与真实 schema 的时间/排序字段 fallback；无可用时 fail-stop；禁止 schema migration、禁止向 Hermes SQLite 写入。
- [ ] 修复同日内 session 摘要页文件名冲突（使用完整 session id 保证唯一）。
- [ ] 两级 secret 扫描结果（P0 修订）：blocking 真实凭据 findings 与 non-blocking 安全 warning 分离；E-005 仅在命中真实凭据值/密钥材料（私钥、已知 provider/token 格式、JWT、Bearer、AWS/Google 等 credential value pattern，或具备可证明 credential-value 形态的 assignment）时 fail-stop；不得因布尔、枚举、存在性、redacted marker、`*_PRESENT`/`*_CONFIGURED`/`*_ENABLED` 等状态/probe 文字触发 E-005。
- [ ] warning 可观测（P0 修订）：不写出 secret 值；warning 不得被静默吞没；ingest summary/page 使用非敏感 warning 计数或安全类别标记，不得把探测字段原文或 session 原文作为 metadata 持久化。
- [ ] 定义 session summary 的来源 / 时间可追溯字段（完整 `session_id`、`parent_session_id`、ISO 时间、`model`、`provider`、`provenance`），并界定候选生成的安全边界（ingest 只写 summaries/manifest/可选 raw transcript，绝不直接生成候选或改正式页）。
- [ ] 双 profile 对称验收：YQuant / Yinglong 各自 dry-run / fixture / 真实只读 smoke 的明确准则；验收过程中不得创建候选或修改 JMap 正式页。
- [ ] cron 现有时间表、投递策略不变；不得通过吞错将 ingest failure 报为成功。
- [ ] 回滚契约：仅退回本次 r0 adapter 与 profile-local entrypoint 改动；不得删除 JMap 内容或 session queue。

### 3.2 非目标（Out of Scope）

- [ ] 不修改 Hermes core（`hermes-agent` 仓库）的 schema、查询或 gateway 语义。
- [ ] 不修改任何 profile 的 `skills.external_dirs`、shell PATH、凭据、gateway 配置、JMap 文件或数据库。
- [ ] 不做 schema migration（不 `ALTER TABLE` / `ADD COLUMN` / `CREATE VIEW` / `CREATE INDEX` 于 Hermes SQLite）。
- [ ] 不做 state.db 快照/影子拷贝作为生产路径（yquant state.db 约 1.6 GB，每日全量拷贝不可接受）。
- [ ] 不改 cron 时间表与投递策略（仅允许将 prompt 内联 brain 调用替换为统一入口调用）。
- [ ] 本阶段不创建候选、不提升/合并/覆盖/删除任何 JMap 正式知识页。
- [ ] 不实现 `ingest-sessions` 之外的其他 brain 子命令（`search` / `build-index` / `lint` 等）的入口重构；仅固化"入口解析规则"使其复用同一 canonical 解析。

---

## 4. 整体设计

### 4.1 核心设计哲学

**只读兼容、最小侵入、显式失败**：

1. **源只读**：对 Hermes `state.db` 只做只读连接（`file:...?mode=ro`），任何兼容逻辑都不得以写方式打开、修改或迁移源库。
2. **适配收敛到 r0 单点**：schema 兼容映射（列名、时间换算、provider 来源）放在 r0 `ingest` 适配层一处，两个 profile 共享同一份修复，天然对称。
3. **入口收敛为 profile-local 薄封装**：每个 profile 一个 entrypoint 脚本，固定 `--hermes-home <profile>` 与 `--vault /mnt/e/Data/Yinglong/JMap`，透传非零退出码，杜绝吞错。
4. **确定性优先**：排序用 `(created_at, id)`，时间统一为带固定时区的 ISO-8601，cursor 语义与 manifest 幂等去重共同保证可重复执行。
5. **失败必须可见**：schema 不兼容、无可用时间字段、blocking secret 命中（真实凭据）、vault 写失败等一律非零退出 + stderr 描述；cron 必须按失败处理。W-001 warning（探测/状态字段）不是失败：stderr 可见 + 摘要计数，退出码 0，ingest 继续。

### 4.2 统一入口解析规则（canonical Brain command resolution）

| 层级 | 允许形式 | 说明 |
|---|---|---|
| Canonical（唯一生产入口） | `/home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/.venv/bin/brain <subcommand> ...` | 绝对路径；cron、entrypoint、knowledge skill 统一使用 |
| 等价形式（允许，但非首选） | `.venv/bin/python -m r0b0tlabbra1n.cli <subcommand> ...` | 同一 venv 解释器入口，语义等价 |
| 进程内复用（skill 脚本） | 在 r0 venv 内 `import r0b0tlabbra1n...` | `llm-wiki-brain/scripts/brain_search.py` 现有模式，仅限只读子命令 |
| 禁止形式 | 裸 `brain`（依赖 PATH） | 当前不在 PATH；禁止新增 PATH 修改作为本方案一部分 |

失败语义：任何入口形式在失败时必须返回非零退出码并向 stderr 输出机器可读的错误描述（错误分类见 SPEC §3.3）；调用方（cron / skill / 脚本）必须透传，不得吞错。

### 4.3 兼容读取策略

`ingest` 适配层按以下策略读取 Hermes `state.db`（只读 URI 不变）：

1. **schema 变体检测**：读取 `PRAGMA table_info(sessions)`，判定存在 `created_at`（r0 测试 fixture / 上游约定 schema）还是 `started_at`（真实 Hermes schema）。
2. **时间字段映射**：
   - 真实 schema：`created_at := started_at`（REAL epoch 秒）换算为固定时区（Asia/Shanghai, +08:00）的 ISO-8601 字符串（微秒精度）；
   - 上游 schema：直接使用既有 `created_at` 字符串；
   - 两者皆无：fail-stop（错误分类 E-002），在任何 vault 写入前中止。
3. **列名映射**：`model_name := sessions.model`（空则 `unknown`）；`provider_name` 从 `session_model_usage.billing_provider` 按确定性优先级派生（见 SPEC §4.2），兜底 `unknown`。
4. **确定性排序**：`ORDER BY created_at ASC, id ASC`（id 为次级排序键，保证同时间戳 session 顺序确定）。
5. **cursor 语义**：维持 r0 CLI 的标量 `--since` 字符串（`WHERE created_at > ?`）；同值 session 会被重复扫描，由 manifest 幂等去重兜底，不丢数据（见 §5.3）。
6. **摘要页文件名唯一性**：`{date_prefix}-{full_session_id}.md`（完整 session id 唯一），消除同日内覆盖。

### 4.4 双 profile 对称性与共享 vault

- 两 profile 共享同一 JMap vault（`/mnt/e/Data/Yinglong/JMap`），`_meta/ingestion-manifest.jsonl` 为 vault 级去重；Hermes session id 全局唯一（含随机后缀），跨 profile 不会互相误去重。
- 两 profile 各自拥有独立的 `jmap-candidate-queue.jsonl`（hook 入队）与 entrypoint；适配与验收必须对 yquant / yinglong 完全对称执行。
- 验收阶段所有写入类验证（ingest 到 vault）只允许指向临时/夹具 vault，真实 JMap 保持只读、哈希不变。

### 4.5 两级 secret 扫描契约（P0 修订，Option A）

1. **结果分层**：scanner 输出 `blocking`（真实凭据）与 `warnings`（安全警告）两级；ingest 对 `blocking` 走 E-005 fail-stop（不落盘该页、退出码 1），对 `warnings` 打印 W-001、继续 ingest、退出码 0。
2. **E-005 收紧定义**：仅以下形态触发 E-005——
   - 私钥：`-----BEGIN (RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----`；
   - 已知 provider/token 格式：`hf_`（HF）、`sk-`/`sk-proj-`（OpenAI）、`sk-ant-`（Anthropic）、`gh[pousr]_`（GitHub）、`am_`（AgentMail）、`AIza...`（Google）、`AKIA...`/`aws_secret_access_key=`（AWS）；
   - JWT（`eyJ...`）、Bearer token；
   - 引号包裹且长度 ≥16 的 `(api[_-]?key|apikey|secret|token|password)\s*[:=]` assignment；
   - env 赋值值本身具备可证明 credential-value 形态（高熵不透明串 ≥16 或命中上述已知格式）。
   布尔、枚举、存在性、redacted marker（`***`/`[REDACTED]`/`redacted:...`/`«redacted:...»`）、`*_PRESENT`/`*_CONFIGURED`/`*_ENABLED` 等状态/probe 文字**不触发** E-005（归类为 warning）。
3. **warning 可观测性**：stderr 输出 `WARNING W-001: <非敏感类别> for session <sid>`（不回显 secret 值、不回显完整原文）；stdout 摘要 `Ingested N sessions (W security warnings).`；摘要页 frontmatter 可选 `security_warnings: W` 非敏感计数；manifest 结构不变；**不得**把探测字段原文或 session 原文作为 metadata 持久化。warning 不得被静默吞没（须可见），但不是失败。
4. **公共调用方不变**：`vault/lint.py`、`vault/write_ops.py` 继续使用 blocking 语义（`is_safe`/`scan_for_secrets` 向后兼容），对 blocking credential 保持 hard-block；warning 行为不得削弱真实密钥保护。
5. **allowlist 扩展**：scanner 的后继 Implement allowlist 新增且仅新增 `r0b0tlabbra1n/security/secret_scan.py` 与 `tests/test_secret_scan.py`，保留既有 A/B/C 闭集（r0 adapter/test、两 entrypoint、两 jobs.json）；`tests/fixtures/eval-vault/_meta/source-hashes.json` 为外部/旧 dirty timestamp 变化（仅 `generated_at`），**明确不可修改**，不得 reset/stash/清理或误归因于本链。
6. **Supersede**：旧 T4 Verify（`t_d1827953`，R-002 rc=1 FAIL）被本 P0 修订 supersede；其 FAIL 是有效证据，不得改写为 PASS；新 Verify 必须重新独立执行，旧 FAIL 不自动解除。

---

## 5. 详细设计

### 5.1 业务流程

```text
[每日 cron 02:45 / 02:05 触发（时间表、投递不变）]
        │
        ▼
[profile-local entrypoint（yquant / yinglong 各自一份）]
        │ 1) 用 canonical 绝对路径调用 brain ingest-sessions
        │    --hermes-home <对应 profile> --vault /mnt/e/Data/Yinglong/JMap [--since <cursor>] [--include-transcripts]
        │ 2) 透传退出码；非零 → stderr 输出错误分类 → cron 记失败，绝不报成功
        ▼
[ingest 适配层（r0 侧，只读连接 state.db）]
        │ 1) schema 变体检测（created_at / started_at / 两者皆无）
        │ 2) 映射 created_at/model/provider + 确定性排序 (created_at, id)
        │ 3) 逐 session：读取 messages → 生成摘要页（完整 sid 文件名）
        │    → 两级 secret 扫描（blocking→E-005 不落盘 / warning→W-001 + 计数）
        │    → 写 vault sessions/summaries/（+可选 raw/hermes-sessions/）
        │    → 追加 _meta/ingestion-manifest.jsonl
        │ 4) 全程只读源库；无可用时间字段 → fail-stop E-002
        ▼
[输出] 成功：Ingested N sessions (W security warnings)（exit 0）；失败：错误分类 + exit != 0
        │
        ▼
[cron agent 继续既有候选提炼流程（knowledge skill 约束，本 RFC 不改变）]
```

### 5.2 schema 兼容映射表（契约级）

| r0 需要 | 真实 Hermes schema | 适配规则 |
|---|---|---|
| `sessions.created_at`（必须） | `sessions.started_at REAL NOT NULL` | epoch → ISO-8601 +08:00 微秒精度；上游 schema 已有 `created_at` 时直接使用 |
| `sessions.model_name` | `sessions.model TEXT` | 直接映射；NULL → `"unknown"` |
| `sessions.provider_name` | `session_model_usage.billing_provider TEXT` | 按确定性优先级派生；无 → `"unknown"` |
| `sessions.parent_session_id` | `sessions.parent_session_id TEXT` | 直接映射（已存在） |
| `messages.session_id / role / content` | 同名列 | 直接映射；`ORDER BY id ASC` 不变 |
| 排序 | — | 强制 `ORDER BY created_at ASC, id ASC` |
| 摘要页文件名 | — | `{date_prefix}-{full_session_id}.md`（修复 sid[:8] 同日内冲突） |

### 5.3 时间与 cursor 语义

- **时间基准**：`started_at`（REAL epoch，UTC 秒）经 `datetime.fromtimestamp(..., tz=+08:00)` 换算为 `YYYY-MM-DDTHH:MM:SS.ffffff+08:00`；同偏移下 ISO 字典序 == 时间序，保证排序确定性。
- **日期前缀**：`created` 的 `%Y-%m-%d`（Asia/Shanghai 自然日）用于文件名前缀；微秒精度避免同秒 session 时间戳重复。
- **cursor**：`--since <ISO-8601 +08:00 字符串>`，沿用 `WHERE created_at > ?`。同值边界被重复扫描，由 manifest 去重跳过；不要求 tuple cursor（r0 CLI 面保持标量）。
- **幂等**：`_meta/ingestion-manifest.jsonl` 为唯一事实来源；同一 session_id 重复执行一律跳过；重复执行第二次输出 `Ingested 0 sessions`。

### 5.4 session summary 来源/时间可追溯字段与候选生成安全边界

**摘要页 frontmatter 必须保留的溯源字段**（r0 现有契约 + 适配确认）：

| 字段 | 语义 | 约束 |
|---|---|---|
| `session_id` | 完整 Hermes session id | 非空、唯一 |
| `parent_session_id` | 父 session id | 空字符串表示无父 |
| `created` | ISO-8601（适配后） | 与文件名日期前缀同源 |
| `model` / `provider` | 模型名 / provider | 映射后值，缺省 `unknown` |
| `provenance` | 固定 `ingest` | 标记为机器生成摘要 |
| `msg_count` | 消息数 | 与 messages 查询一致 |

**候选生成安全边界**（本 RFC 硬约束）：

1. `ingest` 自身只写三处：`sessions/summaries/*.md`、`_meta/ingestion-manifest.jsonl`、以及仅当 `--include-transcripts` 时的 `raw/hermes-sessions/*.json`（含 `trusted:false` 警告）。**绝不**直接创建 `inbox/candidates/` 页、**绝不**修改 `dashboards/knowledge-review.md` 或任何正式知识页。
2. 候选提炼仍由 cron agent 在 `knowledge` skill 约束下执行（来源明确、跨任务可复用、不含敏感信息才建候选；finance/quant 标记待 Yquant 复核）。
3. 摘要页本身是"生成的摘要，需人工审阅"（`Review status: generated summary, needs human review`），不自动提升。

### 5.5 失败语义与错误分类（契约级）

| 分类 | 触发条件 | 行为 | 退出码 |
|---|---|---|---|
| E-000 | 成功（含 Ingested 0） | stdout 输出计数 | 0 |
| E-001 | sessions/messages 表缺失，或 messages 缺 `session_id/role/content` | stderr + 中止 | 1 |
| E-002 | sessions 同时无 `created_at` 与 `started_at`（无可映射时间字段） | stderr + 中止，vault 零写入 | 1 |
| E-003 | 列映射后仍出现 SQL 解析错误（适配缺陷） | stderr + 中止 | 1 |
| E-004 | vault 写失败（路径逃逸、权限、磁盘） | stderr + 中止 | 1 |
| E-005 | secret 扫描命中 **blocking 真实凭据**（私钥 / provider 格式 / JWT / Bearer / AWS/Google / 可证明 credential-value 形态） | stderr + 中止，不落盘该页 | 1 |
| E-006 | state.db 只读打开失败（缺失 / WAL 文件不可读） | stderr + 中止 | 1 |
| E-007 | `--since` 非法格式（非 ISO-8601） | stderr + 中止 | 3 |
| W-001 | secret 扫描命中 **non-blocking warning**（env 名含敏感词但值为探测/状态字段：布尔 / 枚举 / 存在性 / redacted marker / `*_PRESENT` / `*_CONFIGURED` / `*_ENABLED` 等） | stderr `WARNING W-001` + 摘要计数；**不中止**，页正常落盘 | 0 |

调用方（entrypoint / cron agent）必须透传退出码；任何"命令失败但任务标记成功"的路径都被视为违反本 RFC。**W-001 warning 不是失败**：不触发中止语义、不改变退出码；仅非零退出码视为失败（禁止吞错仅针对失败）。

---

## 6. 变更面与 allowlist（供 SPEC/Design 具象化）

### A 组：r0 adapter（单一适配点，Implement 阶段允许修改）

| 文件 | 授权改动 |
|---|---|
| `r0b0tlabbra1n/ingest/hermes_sessions.py` | 实现 §4.3/§5.2/§5.3 的兼容读取：schema 变体检测、列映射、时间换算、确定性排序、文件名唯一性、错误分类；secret 扫描接入两级分类（§4.5）；保持只读 URI、manifest、摘要生成语义 |
| `tests/test_hermes_session_ingest.py`（r0 仓库） | 新增真实 Hermes schema fixture（无 created_at、`started_at REAL`、`model`、无 provider_name、含 `session_model_usage`）与映射/排序/文件名/失败用例；新增两级扫描 ingest 用例（F-008 等） |
| `r0b0tlabbra1n/security/secret_scan.py`（P0 修订新增） | 实现 §4.5 两级分类：blocking patterns 保持；env 分支按 credential-value 形态分类（blocking/warning/safe）；新增 `scan_for_secrets_detailed` 返回 `ScanResult(blocking, warnings)`；`scan_for_secrets`/`is_safe` 保持向后兼容（仅 blocking 语义） |
| `tests/test_secret_scan.py`（r0 仓库，P0 修订新增） | 新增两级分类用例（U-009~U-013 等）：状态字段→warning、真实凭据→blocking、lint/write_ops 公共调用方 hard-block 不变 |

### B 组：profile-local entrypoint（每 profile 一份，可新增）

| 文件（候选，Design 定名） | 授权改动 |
|---|---|
| `~/.hermes/profiles/yquant/scripts/brain_ingest_sessions.{sh,py}` | 新增：固定 hermes-home=vault=绝对路径参数，透传退出码，stderr 带错误分类 |
| `~/.hermes/profiles/yinglong/scripts/brain_ingest_sessions.{sh,py}` | 同上（yinglong 变体） |

### C 组：cron prompt 接入（仅替换调用，不动时间表/投递）

| 文件 | 授权改动 |
|---|---|
| `~/.hermes/profiles/yquant/cron/jobs.json` | 仅把 prompt 内联 brain 调用替换为调用 B 组 entrypoint；`schedule`、`deliver`、`skills`、`workdir` 不变 |
| `~/.hermes/profiles/yinglong/cron/jobs.json` | 同上 |

### 禁止清单（本任务任何阶段不得触碰）

```text
hermes-agent/                                    # Hermes core：schema、查询、gateway 语义
~/.hermes/profiles/{yquant,yinglong}/config.yaml  # profile 配置（external_dirs、hooks、PATH、凭据）
~/.hermes/profiles/{yquant,yinglong}/state/*.db*  # Hermes SQLite（任何写入）
/mnt/e/Data/Yinglong/JMap/                        # 本阶段 JMap 任何写操作；验收仅允许临时/夹具 vault
~/.hermes/profiles/{yquant,yinglong}/state/jmap-candidate-queue.jsonl  # session queue（只读引用）
tests/fixtures/eval-vault/_meta/source-hashes.json # r0 共享工作树外部/旧 dirty timestamp（仅 generated_at）；不可修改、不得 reset/stash/清理或误归因
/mnt/c /mnt/d 全局 PATH / 系统级配置              # 全局环境
```

---

## 7. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| started_at 与 session id 内嵌时间（本地时区）不一致，导致摘要页日期与预期不符 | 低 | 中 | SPEC 固定 +08:00 换算；验收对比 session id 日期字段（R 组 smoke） | 若证实 Hermes 用 UTC 生成 id，仅在适配层调整时区常量，不影响其余契约 |
| 1.6 GB state.db 只读打开慢 / WAL 快照不一致 | 中 | 低 | 只读 URI + SQLite 快照读；按 session_id 精确查询，避免全表大扫描 | 错误分类 E-006 显式暴露；不做影子拷贝 |
| 同秒多 session 的 cursor 边界重复扫描 | 中 | 低 | manifest 幂等去重兜底；重复扫描只读、不写 | 文档化标量 cursor 局限，不升级为 tuple cursor |
| cron agent 仍吞错报成功 | 中 | 高 | entrypoint 透传非零退出码；SPEC 验收含"失败注入 → cron 输出必须为失败" | Review 阶段核对 cron 输出；关闭吞错路径 |
| provider 派生不完整（model_config 无 provider 线索） | 中 | 低 | 优先级链兜底 `unknown`；摘要页明确标注 | 不影响 ingest 成功，只影响溯源完整度 |
| 修改 r0 仓库与上游版本漂移 | 低 | 中 | 适配集中在 ingest 单文件；回滚契约仅退本 adapter | git revert 单文件，JMap/队列零接触 |
| secret 扫描误判状态字段导致 ingest 中断 | 已实证 | 高 | P0 修订（Option A）两级分类：探测/状态字段→warning 继续 ingest；真实凭据仍 E-005 fail-stop | 若未来出现新误判形态，扩展值形态分类器（warning 路径），不放松 blocking 语义 |
| 未来 Hermes schema 再变（如新增时间列） | 低 | 中 | 变体检测先行：新列存在则优先使用，向后兼容 | fail-stop E-001/E-002，不静默降级 |

---

## 8. 备选方案（Alternatives Considered）

1. **影子拷贝 + 归一化 state.db 再 ingest**：复制 state.db（约 1.6 GB）到临时文件，加 `created_at` 列后让 r0 原样运行。
   - 优点：r0 改动最小。
   - 缺点：每日全量拷贝 1.6 GB、占用临时盘、WAL 一致性需额外处理；违背"最小、可验证"与成本约束。**不选用**。
2. **对 Hermes state.db 执行 schema migration（ADD COLUMN created_at）**：
   - 优点：直接满足 r0 校验。
   - 缺点：向 Hermes SQLite 写入，违背只读红线；migration 影响 gateway 运行中的数据库；回滚困难。**禁止**。
3. **SQLite VIEW 或触发器暴露归一化视图**：
   - 缺点：VIEW/触发器本质是对源库的 schema 变更（需写权限），同样越界。**禁止**。
4. **修改全局 PATH 使裸 `brain` 可用**：
   - 优点：命令最短。
   - 缺点：任务明确禁止以全局 PATH 修改为本轮方案；多 venv 环境下裸命令解析不可控。**不选用**（保留 canonical 绝对路径）。
5. **Hermes core 增加 `created_at` 兼容列**：
   - 缺点：改第三方 core，影响面大、升级即失效；远超本任务范围。**不选用**。

---

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收

- [ ] 对真实 yquant / yinglong `state.db`，`brain ingest-sessions`（经 canonical 入口 + entrypoint）均能成功完成至少一次 ingest，退出码 0。
- [ ] 生成的摘要页文件名唯一（含完整 session id），日期前缀来自 `started_at` 换算的 Asia/Shanghai 自然日；frontmatter 含完整溯源字段（`session_id` / `parent_session_id` / `created` / `model` / `provider` / `provenance: ingest` / `msg_count`）。
- [ ] 幂等：同一 state.db 连续 ingest 两次，第二次 `Ingested 0 sessions`。
- [ ] 上游 schema fixture（含 `created_at` 的 r0 原约定）仍可正常 ingest（向后兼容）。
- [ ] 无可用时间字段 fixture → fail-stop（E-002），vault 零写入、退出码非零。
- [ ] 同日内多 session → 生成多个不同文件，无覆盖。
- [ ] 真实凭据（私钥 / `sk-` / `hf_` / JWT / Bearer / AWS / Google 形态）→ E-005、该页不落盘、退出码非零。
- [ ] `TOKEN_PRESENT=False` / `TOKEN_PRESENT=true` / `KEY_CONFIGURED=0` 等探测/状态字段 → W-001 warning、页正常落盘、退出码 0。

### 9.2 非功能验收

- [ ] 源只读：ingest 前后 Hermes `state.db`（含 `-wal`/`-shm`）内容不变（哈希/行数校验），无 `ALTER TABLE` / `ADD COLUMN` / `CREATE VIEW` / `CREATE INDEX`。
- [ ] 真实 JMap 只读：验收全程 `/mnt/e/Data/Yinglong/JMap` 哈希不变；无候选创建、无正式页修改。
- [ ] 两 profile 对称：yquant / yinglong 各完成 dry-run / fixture / 真实只读 smoke 全套，结果一致。
- [ ] 失败显式：E-001~E-007 分类均有对应测试；W-001 warning 有对应测试且退出码为 0；entrypoint 对失败注入透传非零退出码；cron 输出必须体现失败（不吞错）。
- [ ] 两级扫描：`vault/lint.py`、`vault/write_ops.py` 对 blocking credential 仍 hard-block；warning-only 内容不阻断（`is_safe` 兼容语义）。
- [ ] warning 可观测：stderr 出现 W-001 且不回显 secret 值；stdout 摘要含 warning 计数；摘要页 frontmatter 计数可选；manifest 无探测字段原文/session 原文。
- [ ] cron 时间表与投递策略不变（`jobs.json` 的 `schedule` / `deliver` 前后一致）。
- [ ] 回滚契约：仅 revert A/B/C 组改动即可恢复原状；JMap 内容与 session queue 不被删除。

---

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分（Full Flow 后续阶段）

| 阶段 | 产出 | 负责人（profile） |
|---|---|---|
| T2 Design | `docs/design/10_infra/DESIGN-10-011-r0-brain-cli-session-ingest-compatibility.md`：adapter 实现细节、entrypoint 定名与内容、cron prompt diff、fixture 设计、回滚步骤 | yquantprincipal |
| T3 Implement | A 组 r0 adapter（含 `secret_scan.py` 两级分类与 `test_secret_scan.py` 用例）+ B 组 entrypoint + C 组 cron prompt 接入 | yquantdeveloper |
| T4 Verify | SPEC §6 测试矩阵全套（两 profile 对称） | yquanttester |
| T5 Review | 独立审查 diff、测试结果、与 RFC/SPEC 一致性 | yquantreviewer |

### 10.2 关键任务与门禁

- Design 完成：SPEC §5 的 A/B/C 文件级 allowlist 具象化，给出精确路径与 diff 草案。
- Implement 完成：r0 adapter 单文件 + entrypoint 双文件 + cron prompt 两处替换；不改任何被禁文件。
- Verify 完成：SPEC §6 全部用例通过 + 两 profile 对称性报告 + 失败注入证据。
- Review 通过：无 Red-line 违反（只读、禁写、不吞错、cron 不变）。

---

## 11. 开放问题（Open Questions）

- [ ] Q-1：Hermes session id 内嵌时间（`YYYYMMDD_HHMMSS_xxx`）是本地时区还是 UTC 生成？将影响摘要页日期前缀的时区常量（设计默认为 +08:00，需在 Verify 阶段用真实样本核对）。
- [ ] Q-2：`--include-transcripts` 是否在两个 cron 中启用？当前 cron 未传该 flag（保持现状）；raw transcript 含完整对话内容，涉及隐私，默认关闭。
- [ ] Q-3：是否同时更新 `llm-wiki-brain/SKILL.md` 与 r0 README 的 `ingest-sessions` 文档（默认 `~/.hermes` 的语义修正）？属 r0 仓库文档改动，Design 阶段定夺是否纳入 A 组。
- [ ] Q-4：entrypoint 是否需要维护 per-profile 持久 cursor（`state/brain-ingest-cursor.json`）以加速增量？正确性不依赖它（manifest 兜底），默认不引入，Design 确认。
- [x] Q-5（V0.2 已决）：Pascal 选定 Option A——E-005 仅对真实凭据值/密钥材料 fail-stop，探测/状态字段（`TOKEN_PRESENT`/`KEY_CONFIGURED` 等）降级 warning 并允许 ingest 继续；同步修订 RFC/SPEC/DESIGN 至 V0.2，scanner allowlist 新增 `secret_scan.py` 与 `test_secret_scan.py`；旧 T4 Verify（t_d1827953）被 supersede，新 Verify 重新独立执行。

---

## 12. 参考资料（References）

- Hermes schema 权威定义：`/home/pascal/workspace/hermes-agent/hermes_state_common.py`（`SCHEMA_SQL`）。
- r0 ingest 实现：`/home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/r0b0tlabbra1n/ingest/hermes_sessions.py`、`cli.py`、`tests/test_hermes_session_ingest.py`。
- `llm-wiki-brain` skill：`/home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/hermes/skills/llm-wiki-brain/SKILL.md`。
- 两 profile cron：`~/.hermes/profiles/{yquant,yinglong}/cron/jobs.json`；hook：`~/.hermes/profiles/{yquant,yinglong}/scripts/jmap_session_capture.py`。
- JMap vault：`/mnt/e/Data/Yinglong/JMap`（`_meta/ingestion-manifest.jsonl`、`sessions/summaries/`）。
- `knowledge` skill：`/home/pascal/workspace/yq-yinglong/skills/knowledge/SKILL.md`。
- 配套 SPEC：`docs/spec/10_infra/SPEC-10-011-r0-brain-cli-session-ingest-compatibility.md`（V0.2）。
- 配套 Design：`docs/design/10_infra/DESIGN-10-011-r0-brain-cli-session-ingest-compatibility.md`（V0.2）。
## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-08-04 | 初始创建 | YQuant-Principal |
| V0.2 | 2026-08-04 | P0 修订（Option A）：E-005 收紧为真实凭据阻断；探测/状态字段降级 warning；scanner allowlist 扩展并明确 `source-hashes.json` 不可修改；supersede 旧 Verify t_d1827953 | YQuant-Principal |
