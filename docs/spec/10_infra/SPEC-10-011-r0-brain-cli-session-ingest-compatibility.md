# SPEC-10-011：r0 Brain CLI 统一入口与 Hermes session 导入兼容

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-08-04 |
| 最后更新 | 2026-08-04 |
| 版本号 | V0.2 |
| 来源 RFC | [RFC-10-011-r0-brain-cli-session-ingest-compatibility](../../rfc/10_infra/RFC-10-011-r0-brain-cli-session-ingest-compatibility.md)（V0.2） |
| 目标模块 | 10_infra（基础设施 / 知识管理） |
| 关联 Design | [DESIGN-10-011-r0-brain-cli-session-ingest-compatibility](../../design/10_infra/DESIGN-10-011-r0-brain-cli-session-ingest-compatibility.md)（V0.2） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

## 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-08-04 | 初始创建：固化 canonical 入口、schema 兼容读取契约、时间/cursor 语义、溯源字段、候选安全边界、文件级 allowlist、错误分类、测试矩阵（两 profile 对称）、强制约束与回滚契约 | YQuant-Principal |
| V0.2 | 2026-08-04 | **P0 修订（Option A，替代失败 Verify t_d1827953）**：secret 扫描升级为两级结果——blocking 真实凭据（E-005，exit 1，不落盘）vs non-blocking warning（W-001，exit 0，ingest 继续）；新增 F-111~F-114 功能契约与值形态分类规则；`security_warnings` 摘要页可选计数；A 组 allowlist 新增 `secret_scan.py` 与 `test_secret_scan.py`；强制不动清单明确 `source-hashes.json`；测试矩阵新增 U-009~U-013 / F-008 / R-002 修订 / R-007；明确旧 T4 Verify 被 supersede、新 Verify 重新独立执行 | YQuant-Principal |

---

## 1. 需求摘要

本 SPEC 将 RFC-10-011 落为可执行、可验证的工程契约。核心交付：

1. 单一 canonical Brain command resolution 规则与允许/禁止入口形式。
2. `ingest-sessions` 对 Hermes schema 的只读兼容读取契约（变体检测、列映射、时间换算、确定性排序、文件名唯一性、fail-stop）。
3. session summary 溯源字段与候选生成安全边界。
4. 文件级 allowlist（A 组 r0 adapter / B 组 profile-local entrypoint / C 组 cron prompt 接入）与强制不动清单。
5. 错误分类（E-001~E-007）与退出码契约。
6. 测试矩阵：单元 + fixture + dry-run + 真实只读 smoke，YQuant / Yinglong 双 profile 对称。
7. 强制约束：源只读、禁写 Hermes SQLite、禁吞错、cron 时间表/投递不变、回滚契约。
8. **两级 secret 扫描契约（P0 修订）**：blocking 真实凭据 findings（E-005）与 non-blocking 安全 warning（W-001）分离；env 名含敏感词不再无条件阻断；探测/状态字段（`TOKEN_PRESENT`/`KEY_CONFIGURED` 等）产生 warning 并允许 ingest 继续；warning 可观测但不回显值、不持久化探测字段原文。

**本 SPEC 不进入 Design 级实现细节**（adapter 函数签名、entrypoint 脚本内容、cron prompt diff 由 DESIGN-10-011 产出）。

---

## 2. 范围

### 2.1 In Scope

- [ ] 定义 canonical Brain 入口解析规则（§3.1）与失败语义（§3.3）。
- [ ] 定义 ingest-sessions 兼容读取契约（§3.2 / §4.1 / §4.2）：schema 变体检测、列映射、时间换算、确定性排序、cursor、文件名唯一性。
- [ ] 定义 summary 溯源字段与候选生成安全边界（§4.3 / §4.4）。
- [ ] 定义文件级 allowlist 与强制不动清单（§5）。
- [ ] 定义错误分类与退出码（§3.3）。
- [ ] 定义测试矩阵（§6）：单元、fixture、dry-run、真实只读 smoke × 2 profile。
- [ ] 定义强制约束（§7）：只读红线、吞错禁止、cron 不变、回滚契约。

### 2.2 Out of Scope

- [ ] 不在本阶段实现任何代码（T3 Implement 产出）。
- [ ] 不修改 Hermes core、profile config、shell PATH、凭据、gateway、数据库、JMap 文件。
- [ ] 不对 Hermes SQLite 做任何写入或 schema 变更。
- [ ] 不改变 cron 时间表与投递策略。
- [ ] 不实现/不引入影子拷贝、VIEW、trigger、全局 PATH 方案（RFC §8 已否决）。
- [ ] 不在本阶段创建候选、提升/合并/覆盖/删除 JMap 正式知识页。
- [ ] 不重构其他 brain 子命令的入口（仅固化统一解析规则复用）。

---

## 3. 功能规格

### 3.1 canonical Brain command resolution

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | 唯一生产入口解析 | 子命令参数 | 以绝对路径执行 `/home/pascal/workspace/llm-wiki_obsidian_hermes_r0b0tlabbra1n/.venv/bin/brain <subcommand> ...` | 该路径必须存在且可执行；不存在时 entrypoint 报错并 exit 非零（E-006） |
| F-002 | 等价入口（允许） | 同一 venv | `.venv/bin/python -m r0b0tlabbra1n.cli <subcommand> ...` | 仅限 r0 venv 解释器；不得使用系统 python |
| F-003 | 进程内复用（skill 脚本，只读子命令） | `import r0b0tlabbra1n...` | 在 r0 venv 内执行 | 仅限只读子命令（如 search）；不得用其绕过 ingest 的 vault 写入边界 |
| F-004 | 禁止裸 `brain` | — | — | 禁止依赖 PATH 解析；禁止以修改全局/用户 PATH 作为方案一部分 |
| F-005 | entrypoint 参数固定 | profile 名 | `--hermes-home ~/.hermes/profiles/<profile> --vault /mnt/e/Data/Yinglong/JMap` | yquant / yinglong 各自一份；参数不允许运行时自由改写 |

### 3.2 ingest-sessions 兼容读取契约

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-101 | 只读连接 | `state.db` 路径 | `sqlite3.connect("file:<path>?mode=ro", uri=True)` | 禁止 rw 打开；禁止 `PRAGMA journal_mode` 等写操作 |
| F-102 | schema 变体检测 | `PRAGMA table_info(sessions)` | 变体 A（有 `created_at`）/ 变体 B（无 `created_at` 有 `started_at`）/ 变体 C（两者皆无） | 表缺失 → E-001；C → E-002 fail-stop（任何 vault 写入前中止） |
| F-103 | 时间字段映射 | `started_at REAL` | `created_at := datetime.fromtimestamp(started_at, tz=+08:00).isoformat()`（微秒精度） | 变体 A 直接使用原 `created_at` 字符串；禁止保留 epoch 数值（否则日期前缀变 `unknown`） |
| F-104 | 模型列映射 | `sessions.model` | `model_name := model`，NULL → `"unknown"` | 不再引用不存在的 `model_name` 列 |
| F-105 | provider 派生 | `session_model_usage.billing_provider` | `provider_name` 按优先级：该 session 最近一次（`last_seen DESC`）非空 `billing_provider`；无 → `"unknown"` | 允许空串视为无；禁止从 messages 内容猜测 |
| F-106 | 确定性排序 | — | `ORDER BY created_at ASC, id ASC` | id 为次级排序键；不允许仅按 created_at |
| F-107 | cursor 语义 | `--since <ISO-8601 +08:00 字符串>` | `WHERE created_at > ?`（标量比较） | 非法格式 → E-007；同值边界重复扫描由 manifest 去重兜底 |
| F-108 | 摘要页文件名唯一 | 完整 session id | `sessions/summaries/{date_prefix}-{sid}.md`，`date_prefix = created 的 %Y-%m-%d` | 禁止使用 `sid[:8]` 截断（同日内冲突）；禁止覆盖已存在文件 |
| F-109 | 幂等 | 已 ingest 的 session | 跳过，`Ingested 0 sessions`（第二次执行） | 唯一事实来源 `_meta/ingestion-manifest.jsonl` |
| F-110 | secret 扫描（两级） | 生成内容 | `scan_for_secrets_detailed` 返回 `blocking` 与 `warnings`；blocking 非空 → E-005（不落盘该页、退出码 1）；仅 warnings → W-001 + 计数、页正常落盘、退出码 0 | blocking 定义见 F-111；warning 定义见 F-112；输出见 F-113 |
| F-111 | blocking 分类（E-005 触发条件） | 私钥 / 已知 provider/token 格式 / JWT / Bearer / AWS/Google / 可证明 credential-value 形态 assignment 或 env 值 | 归类 blocking | 布尔、枚举、存在性、redacted marker、`*_PRESENT`/`*_CONFIGURED`/`*_ENABLED` 等状态/probe 形态**不得**归类 blocking |
| F-112 | warning 分类（W-001 触发条件） | env 名含 `KEY/TOKEN/SECRET/PASSWORD/PASS/AUTH/CREDENTIAL` 子串，但值为探测/状态字段（布尔/枚举/存在性/redacted/短值/计数），或 key 名以 `_PRESENT`/`_CONFIGURED`/`_ENABLED` 等状态后缀结尾 | 归类 warning（非阻塞） | 仅当值本身具备 credential-value 形态时升级为 blocking（F-111） |
| F-113 | warning 可观测输出 | warnings 非空 | stderr 每项输出 `WARNING W-001: <非敏感类别> for session <sid>`（不回显值/原文）；stdout 摘要 `Ingested N sessions (W security warnings).`；退出码 0 | warning 不得被静默吞没；不得把探测字段原文或 session 原文持久化为 metadata |
| F-114 | 摘要页 warning 计数 | 每 session warning 数 | frontmatter 可选字段 `security_warnings: W`（非敏感整数，默认 0） | 不改变 manifest 结构（仍 `{session_id, ingested_at}`） |

### 3.3 错误分类与退出码

| 编号 | 触发条件 | 行为 | 退出码 |
|---|---|---|---|
| E-000 | 成功（含 Ingested 0） | stdout：`Ingested N sessions.` | 0 |
| E-001 | sessions/messages 表缺失，或 messages 缺 `session_id/role/content` | stderr + 中止 | 1 |
| E-002 | 无可用时间字段（变体 C） | stderr + 中止，vault 零写入 | 1 |
| E-003 | 列映射后 SQL 解析错误（适配缺陷） | stderr + 中止 | 1 |
| E-004 | vault 写失败（权限/磁盘/路径逃逸） | stderr + 中止 | 1 |
| E-005 | secret 扫描命中 **blocking 真实凭据**（F-111：私钥/provider 格式/JWT/Bearer/AWS/Google/可证明 credential-value 形态） | stderr + 中止，不落盘该页 | 1 |
| E-006 | state.db 只读打开失败 / 入口路径不可执行 | stderr + 中止 | 1 |
| E-007 | `--since` 非法格式 | stderr + 中止 | 3 |
| W-001 | secret 扫描命中 **non-blocking warning**（F-112：探测/状态字段形态） | stderr `WARNING W-001` + 摘要计数；**不中止**，页正常落盘 | 0 |

调用方（entrypoint / cron agent）必须透传退出码。任何"命令失败但任务标记成功"的路径都被视为违反本 SPEC（§7.2）。**W-001 warning 不是失败**：不触发中止、不改退出码；仅非零退出码视为失败（禁止吞错仅针对失败）。

---

## 4. 数据与接口契约

### 4.1 schema 兼容映射表（契约级）

| r0 需要 | 真实 Hermes schema | 适配规则 | 必填 | 默认/派生 |
|---|---|---|---|---|
| `sessions.created_at` | `sessions.started_at REAL NOT NULL` | epoch → ISO-8601 +08:00 微秒精度 | 是 | `datetime.fromtimestamp(started_at, tz=+08:00).isoformat()` |
| `sessions.model_name` | `sessions.model TEXT` | 直接映射 | 否 | NULL → `"unknown"` |
| `sessions.provider_name` | `session_model_usage.billing_provider TEXT` | 按 session 最近一次非空值派生 | 否 | 无 → `"unknown"` |
| `sessions.parent_session_id` | `sessions.parent_session_id TEXT` | 直接映射 | 否 | NULL → `""` |
| `messages.session_id / role / content` | 同名列 | 直接映射，`ORDER BY id ASC` | 是 | — |
| 排序 | — | `ORDER BY created_at ASC, id ASC` | 是 | — |
| 摘要页文件名 | — | `{date_prefix}-{full_sid}.md` | 是 | `date_prefix = %Y-%m-%d` |

### 4.2 provider 派生优先级（确定性）

1. `session_model_usage.billing_provider`（该 session 最近一次 `last_seen DESC` 的非空值）；
2. `"unknown"`。

禁止从 `sessions.model_config` 之外猜测 provider；`model_config` 解析是否纳入由 DESIGN-10-011 决定（默认不纳入，保持最小契约）。

### 4.3 summary 溯源字段（frontmatter 契约）

| 字段 | 类型 | 必填 | 来源 | 约束 |
|---|---|---|---|---|
| `title` | string | 是 | `Session {sid[:12]}` | 不变 |
| `created` | string | 是 | 适配后 ISO-8601 | 与文件名日期前缀同源 |
| `type` | string | 是 | `session` | 不变 |
| `status` | string | 是 | `active` | 不变 |
| `memory_type` | string | 是 | `episodic` | 不变 |
| `tier` | string | 是 | `cold` | 不变 |
| `model` | string | 是 | 映射后 `model_name` | 缺省 `unknown` |
| `provider` | string | 是 | 派生后 `provider_name` | 缺省 `unknown` |
| `session_id` | string | 是 | 完整 sid | 非空、唯一 |
| `parent_session_id` | string | 是 | 映射 | 无父 → `""` |
| `msg_count` | int | 是 | messages 计数 | ≥ 0 |
| `provenance` | string | 是 | `ingest` | 固定 |
| `security_warnings` | int | 否（V0.2 新增） | ingest 扫描 warnings 计数 | 默认 0；非敏感整数，不含探测字段原文/session 原文 |

### 4.4 候选生成安全边界

- ingest 写集**仅限**：`sessions/summaries/<page>.md`、`_meta/ingestion-manifest.jsonl`、`--include-transcripts` 时 `raw/hermes-sessions/<sid>.json`。
- ingest **绝不**写：`inbox/candidates/`、`dashboards/knowledge-review.md`、任何正式知识页。
- 摘要页正文保留 `Review status: generated summary, needs human review`；候选提炼由 cron agent 依 `knowledge` skill 执行，本 SPEC 不改变其规则。

### 4.bis 持久化契约

| 存储对象 | 字段/索引 | 类型 | 必填 | 默认/派生规则 | 生命周期/TTL | 隐私级别 |
|---|---|---|---|---|---|---|
| JMap `sessions/summaries/{date}-{sid}.md` | 见 §4.3 frontmatter | markdown | 是 | ingest 生成，文件名唯一；`security_warnings` 可选计数 | 长期保留；由 knowledge 生命周期审阅（候选/提升/归档） | L2（会话摘要，不含原文） |
| JMap `_meta/ingestion-manifest.jsonl` | `session_id`、`ingested_at` | jsonl 追加 | 是 | 每成功 ingest 一条 | 长期保留；只追加不重写 | L1 |
| JMap `raw/hermes-sessions/{sid}.json` | `metadata.trusted=false`、`messages[]` | json | 仅 `--include-transcripts` | 含完整对话原文 | 长期保留；隐私敏感，默认不启用 | L3（默认不落盘） |
| Hermes `state.db` | — | sqlite | — | **只读**，零写入 | — | — |

隐私分级说明：L3 的 raw transcript 默认不落盘（cron 未传 `--include-transcripts`）；若未来启用必须经过 Pascal 确认。W-001 warning 只以非敏感计数（stderr 行 / stdout 摘要 / frontmatter `security_warnings`）可见，**不得**把探测字段原文或 session 原文作为 metadata 持久化。

---

## 5. 文件级 allowlist 与强制不动清单

### 5.1 A 组：r0 adapter（Implement 允许修改）

| 文件 | 类型 | 授权改动 | 说明 |
|---|---|---|---|
| `r0b0tlabbra1n/ingest/hermes_sessions.py`（r0 仓库） | 可增量修改 | 实现 §3.2 / §4.1 契约；secret 扫描接入两级分类（F-110~F-114）；保持只读 URI、manifest、摘要生成语义 | 单一适配点；editable 安装下改源码即时生效 |
| `tests/test_hermes_session_ingest.py`（r0 仓库） | 可增量修改 | 新增真实 schema fixture 与映射/排序/文件名/失败用例；新增两级扫描 ingest 用例（F-008 等） | 与 §6 测试矩阵对应 |
| `r0b0tlabbra1n/security/secret_scan.py`（r0 仓库，**V0.2 新增**） | 可增量修改 | 实现 §3.2 F-110~F-114 两级分类：blocking patterns 保持；env 分支按 credential-value 形态分类（blocking/warning/safe）；新增 `scan_for_secrets_detailed` 返回 `ScanResult(blocking, warnings)`；`scan_for_secrets`/`is_safe` 保持向后兼容（仅 blocking 语义，供 lint/write_ops 继续 hard-block） | 仅此一处新增 scanner 实现文件 |
| `tests/test_secret_scan.py`（r0 仓库，**V0.2 新增**） | 可增量修改 | 新增两级分类用例（U-009~U-013 等）：状态字段→warning、真实凭据→blocking、lint/write_ops 公共调用方 hard-block 不变 | 与 §6 测试矩阵对应 |

### 5.2 B 组：profile-local entrypoint（Implement 可新增）

| 文件（候选，Design 定名） | 类型 | 授权改动 | 说明 |
|---|---|---|---|
| `~/.hermes/profiles/yquant/scripts/brain_ingest_sessions.{sh,py}` | 可新增 | 固定参数 + 透传退出码 + stderr 错误分类 | yquant 变体 |
| `~/.hermes/profiles/yinglong/scripts/brain_ingest_sessions.{sh,py}` | 可新增 | 同上 | yinglong 变体 |

entrypoint 必选行为：调用 canonical 路径（F-001）；`--hermes-home <profile> --vault /mnt/e/Data/Yinglong/JMap`；把 brain 的退出码原样返回；非零时 stderr 输出错误分类行。

### 5.3 C 组：cron prompt 接入（Implement 允许修改）

| 文件 | 类型 | 授权改动 | 说明 |
|---|---|---|---|
| `~/.hermes/profiles/yquant/cron/jobs.json`（job `7fd3367324c4`） | 可增量修改 | 仅替换 prompt 内联 brain 调用为 entrypoint；`schedule`/`deliver`/`skills`/`workdir`/`repeat` 不变 | 时间表 02:45 不变 |
| `~/.hermes/profiles/yinglong/cron/jobs.json`（job `c91202e2a61f`） | 可增量修改 | 同上 | 时间表 02:05 不变 |

### 5.4 强制不动清单

以下文件/范围在本任务任何阶段绝对禁止创建、修改、删除或纳入变更：

```text
hermes-agent/                                        # Hermes core（schema/查询/gateway 语义）
~/.hermes/profiles/{yquant,yinglong}/config.yaml     # profile 配置（external_dirs/hooks/PATH/凭据）
~/.hermes/profiles/{yquant,yinglong}/state/*.db*     # Hermes SQLite（任何写入）
~/.hermes/profiles/{yquant,yinglong}/state/jmap-candidate-queue.jsonl  # session queue
/mnt/e/Data/Yinglong/JMap/                           # 本阶段 JMap 任何写操作
tests/fixtures/eval-vault/_meta/source-hashes.json   # r0 共享工作树外部/旧 dirty timestamp（仅 generated_at）；不可修改、不得 reset/stash/清理或误归因
~/.bashrc ~/.profile /etc/environment                # 全局 PATH / 环境
```

---

## 6. 测试矩阵

### 6.1 单元测试（r0 仓库）

| 编号 | 场景 | 操作 | 预期结果 |
|---|---|---|---|
| U-001 | schema 变体检测 | 变体 A（有 created_at）/ 变体 B（有 started_at）/ 变体 C（皆无） | 分别判定 A/B/C；C 触发 E-002 |
| U-002 | epoch → ISO 换算 | `started_at=1722733200.5`（+08:00） | `created_at` 为 `+08:00` 偏移 ISO 字符串，微秒保留，`%Y-%m-%d` 日期正确 |
| U-003 | 列映射 | 真实 schema fixture | `model_name=sessions.model`；无 provider 记录 → `provider_name="unknown"` |
| U-004 | 确定性排序 | 同 started_at 的多 session | 输出顺序 `(created_at, id)` 稳定 |
| U-005 | 文件名唯一性 | 同一自然日 3 个 session（真实 id 格式） | 3 个不同文件，无覆盖；文件名含完整 sid |
| U-009 | 两级分类：状态字段→warning | `TOKEN_PRESENT=False` / `TOKEN_PRESENT=true` / `KEY_CONFIGURED=0` / `TOKEN_ENABLED=1` / `API_KEY="***"` | blocking 为空、warnings 非空 |
| U-010 | 两级分类：真实凭据→blocking | `OPENAI_API_KEY="sk-<40字符>"` / `SECRET=<32 高熵>` / 私钥 / JWT / Bearer / AWS/Google 形态 | blocking 非空（E-005 触发）、warnings 可并存 |
| U-011 | 公共调用方 hard-block 不变 | `is_safe()` / `scan_for_secrets()` 对 blocking credential | 仍返回 False / 非空（lint/write_ops 行为不变）；warning-only 内容 `is_safe()` 为 True（不阻断） |
| U-012 | redacted marker→warning | `TOKEN=***` / `API_KEY="«redacted:...»"` / `[REDACTED]` | blocking 为空、warnings 非空 |
| U-013 | env 值形态分类 | 值高熵/命中已知格式（如 `FOO_TOKEN=<64 高熵>`）→ blocking；值布尔/枚举/短值（`FOO_TOKEN=off`）→ warning | 与 U-009/U-010 规则一致 |

### 6.2 fixture 测试（r0 仓库 + 临时 vault）

| 编号 | 场景 | 操作 | 预期结果 |
|---|---|---|---|
| F-001 | 真实 Hermes schema 全链路 | 构造真实 schema fixture（无 created_at、`started_at REAL`、`model`、`session_model_usage`）+ `init_vault` 临时 vault → `ingest` | N 个 session 全部 ingest；摘要页 N 个；manifest N 行；frontmatter 溯源字段完整 |
| F-002 | 上游 schema 向后兼容 | 原 r0 fixture（有 `created_at`） | 仍可正常 ingest（不回归） |
| F-003 | fail-stop（E-002） | 变体 C fixture | 非零退出；vault 零写入 |
| F-004 | 幂等 | F-001 后再次 ingest | `Ingested 0 sessions`；无重复页、manifest 不重复 |
| F-005 | cursor | `--since` 取中间 ISO | 仅返回该时间之后的 session；边界重复扫描由 manifest 跳过 |
| F-006 | secret 命中（E-005） | fixture 消息含 token 样式串 | 该页不落盘、非零退出 |
| F-007 | include-transcripts | 启用 flag | `raw/hermes-sessions/{sid}.json` 生成，`metadata.trusted=false` |
| F-008 | 状态字段 warning（P0 修订） | 真实 schema fixture 消息含 `TOKEN_PRESENT=False` 等探测行 | ingest 完整完成（全部 session 落盘）；stderr 出现 W-001；stdout 摘要含 warning 计数；退出码 0；frontmatter `security_warnings ≥ 1`；manifest 完整 |

### 6.3 dry-run / 真实只读 smoke（两 profile 对称）

| 编号 | 场景 | 操作 | 预期结果 |
|---|---|---|---|
| R-001 | yquant 真实只读 smoke | `brain ingest-sessions --hermes-home ~/.hermes/profiles/yquant --vault <临时 vault>` | 退出 0；临时 vault 出现摘要页；真实 JMap 哈希不变；`state.db`/`-wal`/`-shm` 哈希与行数不变 |
| R-002 | yinglong 真实只读 smoke（P0 修订） | 同上（yinglong profile） | 退出 0；**含 `TOKEN_PRESENT` 探测字段的 session（如 `20260720_232434_b1bcf1`）产生 W-001 warning 而非 E-005**；临时 vault 完整生成（全部 session 摘要页，含该 sid）；真实 JMap / `state.db`/`-wal`/`-shm` / queue 哈希与行数不变 |
| R-003 | 对称性 | 比较 R-001 / R-002 行为 | 均退出 0、错误分类一致、无 JMap 写、无 SQLite 写 |
| R-004 | 失败注入（吞错禁止） | entrypoint 指向不存在的 hermes-home / 变体 C fixture | 非零退出 + stderr 错误分类；cron 输出记录失败 |
| R-005 | cron 配置不变 | 对比 jobs.json 修改前后 | `schedule` / `deliver` 完全一致；仅 prompt 替换 |
| R-006 | 回滚演练 | revert A/B/C 组改动 | 恢复原状；JMap 与 session queue 零变化 |
| R-007 | 真实凭据 fail-stop（P0 修订） | 临时 vault 中真实凭据形态 fixture | E-005 退出码非零；该页不落盘；其余 session 摘要页不受影响；真实 JMap / state.db / queue 不变 |

---

## 7. 强制约束

### 7.1 零副作用红线（Implement/Verify 绝对禁止）

1. 以非只读方式打开 Hermes `state.db`（含 `-wal`/`-shm`）。
2. 对 Hermes SQLite 执行 `ALTER TABLE` / `ADD COLUMN` / `CREATE VIEW` / `CREATE INDEX` / `INSERT` / `UPDATE` / `DELETE` / `VACUUM`。
3. 创建 state.db 影子拷贝作为生产路径。
4. 修改任何 profile `config.yaml`、PATH、凭据、gateway、cron 时间表/投递策略。
5. 修改 `/mnt/e/Data/Yinglong/JMap/` 任何正式页、`inbox/candidates/`、`dashboards/knowledge-review.md`。
6. 删除 `jmap-candidate-queue.jsonl` / `jmap-candidate-processed.json` 内容。
7. 吞错：把 ingest 失败（非零退出）标记为成功。
8. **警告不削弱保护（P0 修订）**：warning（W-001）不是失败、不触发中止；但 blocking credential（E-005）的 fail-stop、不落盘语义在任何调用方（ingest/lint/write_ops）中不得削弱；`vault/lint.py`、`vault/write_ops.py` 保持 hard-block。
9. **不得修改** `tests/fixtures/eval-vault/_meta/source-hashes.json`（外部/旧 dirty timestamp），不得 reset/stash/清理或将其误归因于本链。

### 7.2 约束检查清单（Review 逐项核查）

- [ ] 源连接仅使用 `file:...?mode=ro` URI。
- [ ] 无任何写入 Hermes SQLite 的代码路径（含注释中的 DDL/DML）。
- [ ] 错误分类 E-001~E-007 全部实现并有测试；W-001 warning 有测试且退出码为 0。
- [ ] entrypoint 透传退出码；失败注入测试（R-004）通过。
- [ ] 两级扫描：U-009~U-013 全通过；lint/write_ops 对 blocking credential 仍 hard-block（U-011）；warning-only 不阻断。
- [ ] R-002 通过：yinglong 真实只读 smoke 退出 0，`TOKEN_PRESENT` 会话产生 W-001 而非 E-005，临时 vault 完整生成。
- [ ] R-007 通过：真实凭据形态仍 E-005 fail-stop、不落盘。
- [ ] `source-hashes.json` 全程零改动（path attribution 排除）。
- [ ] cron `schedule` / `deliver` 前后一致（R-005 通过）。
- [ ] 文件名使用完整 session id；无同日内覆盖。
- [ ] 验收全程真实 JMap 哈希不变、session queue 不变。
- [ ] 回滚演练（R-006）通过：仅 revert A/B/C 组。

---

## 8. 依赖与引用

- **来源 RFC**：`docs/rfc/10_infra/RFC-10-011-r0-brain-cli-session-ingest-compatibility.md`（V0.2）
- **关联 Design**：`docs/design/10_infra/DESIGN-10-011-r0-brain-cli-session-ingest-compatibility.md`（V0.2）
- **引用文件（只读）**：
  - `r0b0tlabbra1n/ingest/hermes_sessions.py`、`r0b0tlabbra1n/cli.py`、`r0b0tlabbra1n/security/secret_scan.py`、`tests/test_hermes_session_ingest.py`、`tests/test_secret_scan.py`（r0 仓库）
  - `hermes_state_common.py`（Hermes core schema，只读参考）
  - `~/.hermes/profiles/{yquant,yinglong}/config.yaml`、`cron/jobs.json`、`scripts/jmap_session_capture.py`
  - `/mnt/e/Data/Yinglong/JMap/_meta/ingestion-manifest.jsonl`、`sessions/summaries/`
  - `hermes/skills/llm-wiki-brain/SKILL.md`（r0 仓库）

---

## 9. 附录

### A. 实测失败证据（2026-08-04）

```text
$ .venv/bin/brain ingest-sessions --hermes-home ~/.hermes/profiles/yquant --vault /tmp/brain-smoke-empty
Traceback ...
ValueError: Unsupported sessions schema; missing columns: ['created_at']
EXIT=1
（yinglong 相同；vault 零写入）
```

### B. 真实 schema 与 r0 期望对照速查

| r0 期望 | 真实 Hermes | 处理 |
|---|---|---|
| `sessions.created_at` | `sessions.started_at REAL NOT NULL` | 换算 ISO +08:00 |
| `sessions.model_name` | `sessions.model` | 映射 |
| `sessions.provider_name` | `session_model_usage.billing_provider` | 派生 |
| `sessions.parent_session_id` | 同名 | 直用 |
| `messages(session_id, role, content)` | 同名 | 直用 |
| 文件名 `{date}-{sid[:8]}.md` | sid 前 8 位=日期 | 改为完整 sid |

### C. 两级扫描速查（P0 修订，Option A）

| 内容形态 | 示例 | 分类 | 行为 |
|---|---|---|---|
| 私钥 | `-----BEGIN RSA PRIVATE KEY-----` | blocking | E-005，不落盘，exit 1 |
| 已知 provider/token 格式 | `hf_...` / `sk-...` / `sk-ant-...` / `ghp_...` / `am_...` / `AIza...` / `AKIA...` / `aws_secret_access_key=...` | blocking | E-005，不落盘，exit 1 |
| JWT / Bearer | `eyJ...` / `Bearer <40字符>` | blocking | E-005，不落盘，exit 1 |
| 可证明 credential-value assignment | `API_KEY="<16+ 字符>"` / `FOO_TOKEN=<64 高熵>` | blocking | E-005，不落盘，exit 1 |
| 状态/探测字段（值形态） | `TOKEN_PRESENT=False` / `TOKEN_PRESENT=true` / `KEY_CONFIGURED=0` / `TOKEN_ENABLED=1` / `FOO_TOKEN=off` | warning | W-001，页落盘，exit 0 |
| 状态/探测字段（key 后缀） | `*_PRESENT` / `*_CONFIGURED` / `*_ENABLED` / `*_DISABLED` / `*_ACTIVE` / `*_SET` / `*_REQUIRED` / `*_AVAILABLE` | warning（除非值 credential 形态） | W-001，页落盘，exit 0 |
| redacted marker | `TOKEN=***` / `API_KEY="«redacted:...»"` / `[REDACTED]` | warning | W-001，页落盘，exit 0 |
| 已知安全 env（allowlist） | `PATH` / `HOME` / `USER` / `SHELL` / `LANG` 等 | safe | 不产生任何 finding |

### D. 旧 Verify supersede 声明（P0 修订）

旧 T4 Verify（`t_d1827953`）对 yinglong R-002 判定 FAIL（rc=1，根因为 `TOKEN_PRESENT` 状态字段误判触发 E-005），该 FAIL 是**有效证据**，不得改写为 PASS；本 SPEC V0.2（含 RFC/Design 同步修订）**supersede** 旧 Verify 的裁决依据（SPEC §6.3 R-002「退出 0」与 E-005 的冲突已通过两级分类消除）。**新 Verify 必须重新独立执行**：R-002 期望 yinglong 真实只读 smoke 退出 0、`TOKEN_PRESENT` 会话产生 W-001 warning 且临时 vault 完整生成；旧 FAIL 不自动解除，只有新 Verify 全量通过才算解除。
