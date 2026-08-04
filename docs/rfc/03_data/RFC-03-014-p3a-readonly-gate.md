# RFC-03-014: P3-A PR-0 / PR-1 / PR-2 受控只读 Gate — 动机、授权边界与成功/失败语义

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-08-04 |
| 最后更新 | 2026-08-04 |
| 版本号 | V0.4 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-014（Unified Data Phase 3 主 RFC，V0.26）、RFC-03-014-p3a-sector-provider-activation（V0.2）、RFC-03-007（Unified Data Layer 总纲）、RFC-03-012（Phase 1D 外部 Provider 激活模式参考） |
| 依赖 SPEC | SPEC-03-014-p3a-readonly-gate（本 RFC 对应之 SPEC，V0.3） |
| 关联 Design | DESIGN-03-014（Phase 3 主设计 V0.33，§15.x T4 preflight 工具链）；历史 DESIGN-03-014-p3a-sector-provider-activation（fake-only，**不得重新激活**）；关联 DESIGN-03-014-p3a-readonly-gate（V0.3） |
| 替代 RFC | 无（不替代主 RFC-03-014；为主 RFC 的 P3-A Step-4 只读 Gate 提供授权契约） |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #phase3 #p3a #gate #readonly #mongo #akshare #credential |

---

## 1. 执行摘要

本 RFC 为 Unified Data Phase 3 的 P3-A Step-4 定义**受控只读 Gate 链**（PR-0 凭证源可用性审计 → PR-1 MongoDB 只读预检 → PR-2 有界 Sector Provider smoke）的动机、授权范围、风险、停止/回滚条件与成功/失败含义。

**核心原则**：Pascal 已授权 Step-4 所需全部**只读**动作；本 Gate 链仅把「可用性审计 / Mongo 只读预检 / Provider schema smoke」落为可执行、可审计、最小权限的契约。Gate 成功只意味着「凭证可加载 + Mongo 只读可达 + name_em 返回结构与预期一致」——**不等于**生产激活、数据入库或可交易信号。任何 DDL/DML、upsert、refresh、cache/file 写入、`cons_em` 调用、P3-B/P3-C/northbound、服务重启、cron/systemd、Git 写操作均不在本 Gate 授权内。**R2（2026-08-04）**：Pascal 范畴裁定 `name_em` 实时板块排行移出 Phase 3 实现/生产验证目标，PR-2 预算**永久废弃**，不再构成可执行 Gate（见 §2.6）；本段 PR-2 相关描述保留为历史定义。

**成功标准**：RFC + SPEC 两份独立文档存在且互相一致；不触发真实 I/O；每个 Gate 有具体 allowlist、停止条件与后续 Verify 的证据标准；`git diff --check` 通过且 diff 仅限 `docs/rfc/03_data/` 与 `docs/spec/03_data/` 允许路径。

---

## 2. 背景与动机

### 2.1 现状

- P3 Step-3 已 Closeout（`t_af9da6ab`）：本地契约 P3-P1 / F1 / F2 / F3 / F4 均 current-verified（F3 经 direct tripwire 三条断言 + falsify 3/3 证明闭合），Step-3 全部门禁通过（基线仲裁 → F3 实现 → 独立 Verify 28/28 + 1426/1426 → F4 Review → Step-3 Final Review 0 blocker/0 major/0 minor）。**真实 I/O 仍为 0**：未发起任何 Provider / Mongo / 网络调用，未执行 Git 写入。
- 历史 B2 冻结证据（2026-07-26）：`sector.snapshot` / `sector.ranking` 对 `stock_board_industry_cons_em("BK0489")` 调用两次均 SSLError；证据冻结在 `/tmp/yquant-b2-pr234-20260726/`（只读副本，不可移动/提交/重跑）。
- P3-A 离线契约（RFC/SPEC-03-014-p3a-sector-provider-activation V0.2）已裁定：`stock_board_industry_rank_em` 不存在；`cons_em` 返回成分股列表（个股粒度），**不是**板块级聚合主数据源；`stock_board_industry_name_em()` 为 `sector.snapshot` / `sector.ranking` 共享主 endpoint（无参数、匿名、返回板块级排名 12 列）。
- 历史 P3-A fake-only Design（`DESIGN-03-014-p3a-sector-provider-activation.md`）及其历史卡**不得重新激活**；Step-4 的 T2 Design 将新建 Gate 链设计。

### 2.2 触发原因

Pascal 明确授权当前 Step-4 所需的全部只读动作：PR-0、PR-1、PR-2。本地契约已验证不代表真实环境可用——`skills/.env` 是否存在并含五组件键、Mongo 是否可 ping、`name_em` 线上 payload 是否与离线源码推断一致，均需在**受控、最小权限、零写入**的 Gate 中一次性确认。**R2：PR-2 授权已随 scope removal 一并废弃（§2.6），不再构成可执行动作。**

### 2.3 为何要单独定义 Gate 契约（而非直接执行）

1. **可审计性**：授权与执行的边界必须固化在文档中，执行者无歧义；事后 Verify 可对照契约逐项核对证据。
2. **最小权限**：只读 Gate 的每个命令都进 allowlist，越界命令即违约；错误分类与停止条件预先定义，避免执行者「猜测连接实现或 API」。
3. **零写入证明**：PR-1 必须有 before/after zero-write proof 或等效只读 command semantics 证据；PR-2 不得持久化原始 payload。
4. **区分语义**：Gate 成功 ≠ 生产激活。明确「可用性审计 / Mongo 只读预检 / Provider schema smoke」与「生产激活 / 数据入库 / 可交易信号」的边界，防止 gate pass 被误读为放行后续写入。

### 2.4 R1 修订（2026-08-04）——已冻结 T3 事实与 Pascal 裁定

> 本卡为**契约/文档 amendment**，非执行或代码修复卡。本节固化已冻结 T3 事实与 Pascal 裁定；T3 live evidence 不重跑。禁止访问 `.env`/secret 内容、Mongo/Provider/network、smoke report 内容（仅可 stat/path existence）。

**已冻结 T3 事实（`t_81432128` 执行，`t_15ed064c` 之后，本卡不重跑）**：

- PR-0 返回 `CONDITIONAL_AUTHORIZED`，但其 redacted evidence / task handoff 记录了逐 `MONGODB_*` key 的 declared/runtime 状态；**未泄露任何值、URI、长度、hash 或凭据**，仍违反「只输出联合 boolean、不得逐 key status」契约。
- PR-1 仅执行 `ping + list_collection_names`（`mongo_calls=2`、`write_operations=0`），未读取任何业务文档；三张预期 P3 集合存在。
- PR-2 未执行，`actual_calls=0`。

**Pascal 裁定（R1 采纳，写死为契约）**：

1. `03_data_ud_market_sector_snapshot`、`03_data_ud_stock_capital_flow`、`03_data_ud_market_sentiment_snapshot` 为 **designated historical baseline（intentional pre-existing）**：其 presence 本身 **不是** PR-1 FAIL；PR-1 成功基线 = 三集合 presence 可观测；**禁止输出或枚举陌生集合名**（evidence 中不得出现未指定集合名）；不允许 read business docs、不允许 DDL/DML。
2. PR-0 外部输出允许字段收敛到 **single aggregate authorization verdict + generic source-kind + generic redacted error-class**；禁止逐 key 名称、逐 key presence/runtime/declaration 状态、password marker、路径、值/长度/hash/URI。
3. 已生成的 gitignored evidence（`docs/rfc/03_data/smoke_reports/audit-secret-20260804.yaml`、`docs/rfc/03_data/smoke_reports/preflight-mongo-20260804.yaml`）视为 **不合规本地工件**：后续 developer Fix **必须仅**删除或替换为合规聚合版；审计事实保留在 Kanban，**不复制不合规内容到 repo/docs**。
4. **PR-1 不可重放**：继续链只能审计既有只读 evidence；**PR-2 预算未消耗**（`actual_calls=0`），但只有 developer Fix → fresh Verify → Review 均通过后，才可新建**单独的 one-call continuation**（不得由本卡或 T3' 顺带执行）。
5. PR-0「file-declared / runtime env absent」= `conditional_authorized`，**不等价于** secret 值有效性或生产授权。

> **R2 注（2026-08-04）**：本节 R1 裁定 4 中「另立 one-call continuation」路径已被 §2.6 R2 裁定**取代**：PR-2 预算**永久废弃**，不再创建 continuation。其余 R1 裁定保留。

### 2.5 P0 Incident Record：netprobe 越界（2026-08-04 12:19:56）

> 本节为 **P0 incident record**（审计固化），由 T5 Final Review（`t_14f0590d`，VERDICT=REVISE）独立复核确认证据齐备后落档。**本节落档完成即 P0 收口，解锁 Step-4 Closeout**。本卡（`t_f85382b3`）仅为文档记录：未执行任何网络调用 / Provider 重试 / live smoke / Mongo 写 / Git 写 / `.env` 内容读取（仅 stat 与静态源码核对）。

**事件**：

| 项 | 值 |
|---|---|
| 时间 | 2026-08-04 12:19:56（+0800） |
| 脚本 | `/tmp/yquant_pr2_netprobe.py`（mtime 2026-08-04 12:19:54，size 781B，权限 600） |
| 行为 | `socket.create_connection` + `ssl.wrap_socket` 直连三 host:443 |
| hosts | `82.push2.eastmoney.com`、`push2.eastmoney.com`、`www.baidu.com` |
| 结果 | 三 host 全部 TLS ok（cipher 正常），EXIT=0 |
| 执行上下文 | T3 会话 `20260804_121845_f28ca1` 消息 30511；T3 block reason 原文「eastmoney TCP/TLS 直连畅通」互证 |

**越界点**：T3 任务 body（`t_55d44505`）唯一允许操作 = 单次 `AKShareSectorClient(timeout=30.0).get_sector_ranking(sector_type="industry")`；netprobe 不在 single-call allowlist 内，且含与 Provider 无关的 `www.baidu.com`。

**裁定**（T5 独立复核确认）：

1. **越界事实成立**：netprobe 超出 T3 single-call allowlist，属 P0 finding，不得以「仅连通性探测」淡化。
2. **TLS 可达 ≠ Provider 可用**：TCP/TLS 握手成功仅证明网络路径可达，不证明 AKShare endpoint 返回 schema 正确、数据非空或集成可用。**禁止**以 TCP/TLS 直连结果作为 Provider 可用性证据。
3. **Cold-skip 业务结果可接受**：PR-2 = `ProviderUnavailable`（可用性冻结）非 PASS；不因 netprobe TLS ok 改变该语义。

**附加记录项（Minor）**：

1. `actual_calls` 字段语义澄清：smoke 脚本 `/tmp/yquant_pr2_smoke.py` 仅在成功路径置 `actual_calls=1`（line 173），异常路径打印初始值 0（line 115；会话 30507 输出 `actual_calls=0`），与 T3 交接语义 `actual_calls=1` 不一致；实际尝试恰 1 次且失败（`provider_attempts=1` + 时间戳 + EXIT=3 佐证）。**字段语义定义为 attempts=1 / success_calls=0**，后续引用一律以此为准。
2. 先前 `t_e94a487a` 声称「119/119 零 .env read」表述不准确：pytest 全量包含 2 个 `--live-read` CLI 测试（`tests/scripts/t4_preflight/test_audit_secret.py` line 234/251），经 `_run_cli` cwd=REPO_ROOT + `CANDIDATE_ENV_FILES=("skills/.env",)` + `probe_env_in_file(live=True)` 真实 `read_text` `skills/.env`（`scripts/t4_preflight/secrets.py` line 298）。**非泄露事件**（值从未序列化/打印，测试断言输出不含 value/URI），但表述须修正为「119/119 零 secret value 输出；其中 2 个 `--live-read` 测试真实读取 `skills/.env` 内容（仅 boolean 判定）」，后续引用禁止使用原「零 .env read」表述。

**收口声明**：本 incident record 落档完成即 P0 收口，解锁 Step-4 Closeout；netprobe 结果不得被后续任何流程引用为 Provider 可用性证据；SPEC/DESIGN-03-014-p3a-readonly-gate 版本指针不因本卡变更（本卡仅 RFC 审计固化）。

> **R2 注（2026-08-04）**：本节 P0 incident record 保留为审计事实，不删改。Pascal 2026-08-04 范畴裁定将 `name_em` 实时板块排行移出 Phase 3 目标（见 §2.6）；本节记录的 netprobe 越界事件与 PR-2 历史结果（ProviderUnavailable + netprobe 越界）仅作历史事实，**不得作为 P3-A 生产能力失败或后续 recovery 依据**。

### 2.6 R2 Scope-Scission：name_em 实时板块排行移出 Phase 3 目标（Pascal 2026-08-04 裁定）

> 本节为 **R2 scope-scission 契约**（Pascal 2026-08-04 范畴裁定，优先级最高），覆盖并取代此前所有将 PR-2 视为可执行目标的表述。以下裁定写死为契约，三份文档（RFC §2.6 / SPEC §0.2 / DESIGN §2.7）逐项一致。

**裁定**：`stock_board_industry_name_em()` / 行业板块 `name_em` 属于**实时板块排行**，不在本次 Unified Data Phase 3 的实现/生产验证目标之内。

1. **PR-2 的 name_em 单次预算永久废弃**（不因 scope removal 留作后门）：`t_55d44505` / `t_81432128` 标记为 **superseded / historical evidence**，不得 unblock、retry、创建 replacement probe 或改用其他 AKShare endpoint。
2. **禁止**为 name_em 新建 Provider recovery、替代 endpoint、实时 refresh 或任何 live retry。
3. P3-A 仅保留**盘后/历史、按 trade_date 可复现**的 sector read-path 验证（消费既有历史集合/物化数据，不发起任何实时 Provider 调用）。
4. PR-2 历史结果（一次尝试 `ProviderUnavailable`、一次越界 netprobe）保留为历史事实，但**不得**作为 P3-A 生产能力失败或后续 recovery 依据。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 定义 PR-0（凭证源可用性审计）的命令级 allowlist、输入/输出脱敏契约、NOT_AUTHORIZED 条件
- [ ] 定义 PR-1（MongoDB 只读预检）的命令级 allowlist（ping + listCollections）、集合名比对范围、零写入证明、失败即停条件
- [ ] 定义 PR-2（有界 Sector Provider smoke）的单次 `name_em` 受控请求、请求预算/超时、响应 schema/非空/字段合理性停止条件、错误分类（含 SSL/connection）与 fail-stop —— **superseded / out-of-scope（R2）**：`name_em` 实时板块排行移出 Phase 3 目标（§2.6），本条保留为历史定义，**不得执行**、不再构成可执行目标
- [ ] 明确全局 OUT：DDL/DML、upsert、refresh、cache write、file write（除允许的非敏感临时运行日志/最终 redacted evidence）、原始 payload 保存、Mongo 业务读、任意其他 Provider/HTTP、P3-B/P3-C/northbound、`cons_em`、services/restarts、cron/systemd、配置/依赖修改、Git stage/commit/push/reset/stash/clean、秘密输出
- [ ] 每个 Gate 定义后续 Verify 的证据标准（YAML 报告字段、exit code、账本字段）
- [ ] 保持与主 RFC-03-014（§6.2 / §13.1 PR-0~PR-4 / §13.4.5 B2 冻结）及 SPEC-03-014-p3a-readonly-gate 无冲突

### 3.2 非目标（Out of Scope）

- **不执行真实 Mongo / Provider / 网络调用**（本卡为 Full Flow T1 RFC/SPEC 文档阶段；T2 Design 后才允许创建 T3 controlled execution）
- 不创建/修改 Design（由 T2 负责新建 Gate 链 Design）
- 不修改历史 P3-A fake-only Design、不重新激活其历史卡
- 不修改主 RFC-03-014 / SPEC-03-014 / DESIGN-03-014 已有内容（仅交叉引用）
- 不修改任何代码、配置、requirements、SKILL/README、脚本、cron/systemd、gateway/webhook
- 不读取/打印/序列化/hash/枚举/日志化任何 secret value、完整连接串、URI credentials 或 `.env` 内容
- 不执行 `cons_em`、不触及 P3-B/P3-C/northbound
- 不执行 Git stage/commit/push/reset/stash/clean
- 不合并 RFC 与 SPEC（两份独立文件）

---

## 4. 整体设计

### 4.1 核心设计哲学

**授权链 = 命令级 allowlist + 零写入证明 + fail-stop**。三个 Gate 串行执行（PR-0 → PR-1 → PR-2），每个 Gate 的 allowlist 独立、停止条件独立、证据标准独立。任一 Gate 失败即停在该 Gate，不 fallback 到新连接串、shell client、生产服务重启，也不降级为写入操作。

```
PR-0 凭证源可用性审计（skills/.env 五组件键，仅 boolean/source-kind/redacted error-class）
  │  pass
  ▼
PR-1 MongoDB 只读预检（既有 PortfolioMongoLoader/approved connection path；ping + listCollections；
  │  集合名仅与 P3-A/03_data 预期清单比对；before/after zero-write proof；失败即停）
  │  pass
  ▼
PR-2 有界 Sector Provider smoke（P3-A Design 已裁定 name_em 单次受控请求；失败不重试；
      输出仅字段名/数量/类型 + redacted schema mismatch + 时间戳 + source trace；不持久化 payload；
      不写 Mongo/cache/file；不调用 cons_em；不触 P3-B/P3-C/northbound）
```

> **R2 注**：上图中 PR-2 块为历史编排，已 **superseded / out-of-scope（§2.6）**，不得执行；可执行链仅 PR-0 → PR-1（PR-1 亦不可重放，R1，实际为审计既有只读 evidence）。

### 4.2 与主 RFC / SPEC 的关系

本 RFC 是主 RFC-03-014 的 **P3-A Step-4 只读 Gate 精确化**，不替代主 RFC。主 RFC §6.2 / §13.1 定义 PR-0~PR-4 的授权 Gate 表；本 RFC 将 P3-A 的 PR-0/PR-1/PR-2 落为可执行契约，继承主 RFC 的零持久化副作用原则（§13.1「PR-0 到 PR-4 的所有步骤设计为零持久化副作用」）。

**交叉引用约束**：
- 主 RFC §6.2 PR-0（Secret source 审计）/ PR-1（MongoDB 只读连通预检）/ PR-2（AKShare Provider smoke：sector.snapshot + sector.ranking）定义触发时机、影响范围、停止条件、执行人。本 RFC 继承并精确化这三项（**R2：PR-2 精确化仅保留为历史定义，不再构成可执行契约，见 §2.6**）。
- 主 RFC §13.4.5 B2 冻结证据：`sector.snapshot` / `sector.ranking` 为 **offline stub**，预期字段集基于公开文档推断，标注「未 live-read 验证」；仅允许后续单变量网络诊断后重试 live-read，且须 Pascal 独立授权。
- 主 SPEC §14.4.5（V0.9）为 PR smoke 可执行契约的权威定义；本 SPEC（SPEC-03-014-p3a-readonly-gate）继承其 exit code、字段映射阈值、账本字段。
- P3-A RFC/SPEC V0.2 裁定 `name_em` 为共享 endpoint；PR-2 只允许该 endpoint。

### 4.3 与历史 fake-only Design 的关系

历史 `DESIGN-03-014-p3a-sector-provider-activation.md`（V0.2）是 fake-only 离线设计（SectorClient 接口、FakeSectorClient、canonical mapping、离线实现计划），其历史卡不得重新激活。Step-4 的 T2 Design 将新建只读 Gate 链设计（PR-0/PR-1/PR-2 的执行编排、evidence 报告模板、T3 controlled execution 的精确命令与路径），**不得**复用/恢复历史 Design 中「真实 smoke 与 production activation」的执行授权。**R2：PR-2 执行编排不再进入 T2 Design 交接（§2.6），仅 PR-0/PR-1 为可执行 Gate。**

---

## 5. 详细设计（Gate 契约）

> 本节省略命令级细节（由 SPEC-03-014-p3a-readonly-gate 提供可计算契约）；此处给出动机、授权边界、风险、停止/回滚与成功/失败含义。

### 5.1 PR-0 — Credential source availability audit（凭证源可用性审计）

**动机**：确认项目既有、指定的 Mongo 连接配置来源（`skills/.env`，Phase 2 PortfolioMongoLoader 认证语义，组件式五键 `MONGODB_HOST` / `MONGODB_PORT` / `MONGODB_USERNAME` / `MONGODB_PASSWORD` / `MONGODB_DATABASE`）「可用/不可用」。PR-0 通过是 PR-1 的前置条件。

**授权边界**：
- 仅允许确认该来源的「可用/不可用」状态；候选文件仅 `skills/.env`（`./.env`、Hermes profile `.env`、`MONGO_URI`/`MONGODB_URI` 均已由主 RFC V0.6 标记 superseded，不是候选）。
- **外部输出仅允许 single aggregate authorization verdict（`authorized` / `conditional_authorized` / `unauthorized`）+ generic source-kind 标签 + generic redacted error-class（R1 收紧，覆盖 §2.4 裁定 2）**。
- 禁止读取、打印、序列化、hash、枚举、日志化任何 secret value、完整连接串、URI credentials 或 `.env` 内容；禁止输出值、长度、URI、用户名、全路径+键值组合（主 RFC §13.1 PR-0）；**禁止逐 key 名称、逐 key presence/runtime/declaration 状态、password marker、路径**。

**成功含义**：存在至少一个来源同时满足「文件存在 + 五键声明 + env 可加载」→ `authorized`（exit 0）。**失败含义**：候选文件不存在、任意一键缺失/空白、端口无效、数据库名不等于 `tradingagents` → `NOT_AUTHORIZED`（exit 3）；部分满足 → `conditional_authorized`（exit 1）。**R1 语义澄清（§2.4 裁定 5）**：「file-declared / runtime env absent」属于 conditional，**不等价于** secret 值有效性或生产授权。PR-0 失败则 PR-1/PR-2 不得执行（AKShare 匿名 smoke 不依赖 PR-0 pass，但本链为 P3-A 全链，PR-1 为 PR-2 前置，见 §5.3）。

### 5.2 PR-1 — MongoDB read-only preflight（MongoDB 只读预检）

**动机**：确认 `tradingagents` 库只读可达（ping）、集合清单与 P3-A/03_data 预期一致（`03_data_ud_market_sector_snapshot` 等 **不应存在**），且整个过程零写入。

**授权边界**：
- 仅允许经项目既有 `PortfolioMongoLoader` / approved existing connection path（`scripts/t4_preflight/preflight_mongo.py` + `mongo_client.py` 的 `LegacyConfigResolver` → `PreflightRunner`，组件式构造连接，非 URI）执行：`ping`（`admin.command("ping")`）与 `listCollections`（`db.list_collection_names()`）。
- 集合名仅可与 P3-A/03_data 预期集合清单比对（`P3_BUSINESS_COLLECTIONS`：`03_data_ud_market_sector_snapshot`、`03_data_ud_stock_capital_flow`、`03_data_ud_market_sentiment_snapshot`）。**R1 裁定（§2.4 裁定 1）**：三集合为 **designated historical baseline**，其 presence 本身 **不是** PR-1 FAIL，而是 PR-1 PASS 基线；**禁止输出或枚举陌生集合名**（evidence 中不得出现未指定集合名）；不允许 read business docs、不允许 DDL/DML。
- 禁止读取业务 document、`find`、统计、索引检查、DDL、DML、admin mutation；不建集合、不读业务数据（主 RFC §13.1 PR-1）。
- 必须提供 before/after zero-write proof 或等效只读 command semantics 证据（命令级 allowlist 只含 ping + listCollections；报告账本 `mongo_calls` ≤ 2、`write_operations = 0`；操作预算 `PREFLIGHT_MAX_OPERATIONS = 4`）。

**成功含义**：ping 成功 + listCollections 成功 + **三张 designated baseline 集合 presence 可观测（存在即预期基线，不因存在而 FAIL；R1）** → `pass`（exit 0）。**失败含义**：
- ping 成功但 listCollections 未授权 → `conditional_pass`（exit 1）；
- 连接失败 / 认证拒绝 / DNS / 超时 → `fail`（exit 2），**立即停在 PR-1**；
- 五键缺失/空白、`MONGODB_DATABASE != "tradingagents"` → `NOT_AUTHORIZED`（exit 3），不构造客户端；
- 意外发现**非 designated 的陌生 P3 命名集合**（不属于上述三张基线集合，且带 P3 前缀）→ `fail`（exit 2）+ 记录存在情况，需 Pascal 判断是遗留还是意外（主 RFC §13.1 停止条件）。**三张基线集合的存在本身不触发该分支（R1）**。

**R1 不可重放**：本卡之前已执行的 PR-1（`t_81432128`，`mongo_calls=2`、`write_operations=0`）**不得重跑**；后续继续链只能审计既有只读 evidence（§2.4 裁定 4）。

**停止/回滚**：PR-1 失败不得 fallback 到新连接串、shell client、生产服务重启；不执行任何写入操作；报告记录后停止。

### 5.3 PR-2 — bounded Sector Provider smoke（有界 Sector Provider smoke）

> ⚠️ **R2 superseded / out-of-scope（§2.6）**：本节为历史定义。Pascal 2026-08-04 范畴裁定 `name_em` 实时板块排行不在 Phase 3 实现/生产验证目标内；PR-2 预算**永久废弃**，**不得执行**、不得重试、不得创建 replacement probe、不得改用其他 AKShare endpoint。以下内容仅保留为历史事实与设计参考。

**动机**：确认 P3-A Design 已裁定的 sector `name_em`（`stock_board_industry_name_em()`）线上真实可用、返回结构与离线源码推断一致（schema 匹配、非空、字段合理），为后续（非本链）生产激活提供唯一 live-read 证据。

**授权边界**：
- 仅允许调用 P3-A Design 已裁定的 `stock_board_industry_name_em()` live read，**一次受控请求**（若失败则不重试）。
- 输出必须只保留：字段名 / 数量 / 类型、必要的 redacted schema mismatch、时间戳、source trace。
- 禁止持久化原始 payload、禁止写 Mongo/cache/file（除允许的非敏感临时运行日志 / 最终 redacted evidence YAML）、禁止调用 `cons_em`、禁止触及 P3-B/P3-C/northbound。
- 必须定义明确请求预算、超时、响应 schema/非空/字段合理性停止条件与错误分类；任何异常（含 SSL/connection）记录证据后 fail-stop。

**成功含义**：单次 `name_em()` 调用返回非空 DataFrame，字段匹配比例 ≥ 90% → `pass`（exit 0）；70%–90% → `conditional_pass`（exit 1）。**失败含义**：
- 连接失败 / SSL / TLS / 超时 / DNS / 认证拒绝 → `fail`（exit 2），记录错误类别（`ProviderUnavailableError` 类）后 fail-stop，不重试；
- 空返回（row_count=0）→ `fail`（X2 保守，主 RFC §13.4.5.3 / §P0）；
- 字段匹配比例 < 70% → `fail`（需重新调整映射后重试，主 RFC §13.4.4 / SPEC A-DRIFT-5）；
- API 内部错误 / 字段缺失 → `fail`（`ProviderError` 类），记录证据后停止。

**停止/回滚**：PR-2 失败不进入 DDL/CANARY 等后续 Gate；不降级为写入操作；报告记录后停止。

**与主 RFC 关系**：主 RFC §13.4.5.8 B2 裁决 `sector.snapshot` / `sector.ranking` 为 **offline stub**——「仅允许后续单变量网络诊断后重试 live-read，且须 Pascal 独立授权」。本 Gate 即该授权的一次受控 live-read；若 `name_em` 仍因 egress 限制失败，记录 `endpoint_unreachable`（ProxyError/ConnectionError 类），由 Pascal 决定是否做单变量网络诊断。

---

## 6. 授权 Gate 与副作用矩阵

### 6.1 本阶段（T1 RFC/SPEC）副作用矩阵

| 操作 | 本阶段权限 | 风险 |
|---|---|---|
| 读写 RFC/SPEC 文档（仅 docs/rfc/03_data 与 docs/spec/03_data 允许路径） | ✅ | 无 |
| 读取现有代码/测试/文档（只读） | ✅ | 无 |
| 真实 Mongo / Provider / 网络调用 | ❌ 禁止 | — |
| DDL/DML / upsert / refresh / cache write | ❌ 禁止 | — |
| file write（除允许的非敏感临时运行日志 / 最终 redacted evidence） | ❌ 禁止 | — |
| 原始 payload 保存 | ❌ 禁止 | — |
| Mongo 业务读（find / 统计 / 索引检查） | ❌ 禁止 | — |
| 任意其他 Provider / HTTP | ❌ 禁止 | — |
| `cons_em` | ❌ 禁止 | — |
| P3-B / P3-C / northbound | ❌ 禁止 | — |
| services / restarts / cron / systemd | ❌ 禁止 | — |
| 配置 / 依赖修改 | ❌ 禁止 | — |
| Git stage/commit/push/reset/stash/clean | ❌ 禁止 | — |
| 读取 secrets / `.env` 内容 / 输出秘密 | ❌ 禁止 | — |

### 6.2 Gate 链依赖与授权

| Gate | 内容 | 前置条件 | 授权方 | 成功含义（gate pass） |
|---|---|---|---|---|
| PR-0 | 凭证源可用性审计（skills/.env 五键） | 无 | Pascal（Step-4 已授权） | **single aggregate verdict（authorized/conditional_authorized/unauthorized）**；仅可用性，不授权读取值；**外部输出禁止逐 key 名称/状态（R1）** |
| PR-1 | Mongo 只读预检（ping + listCollections） | PR-0 pass | Pascal（Step-4 已授权） | tradingagents 只读可达、**三张 designated baseline 集合 presence 可观测（存在即预期基线，非 FAIL；R1）**、零写入证明；**不得重跑既有 PR-1（R1）** |
| PR-2 | 有界 name_em smoke（单次受控请求） | PR-1 pass（本链序）；AKShare smoke 本身不依赖 PR-0 pass | Pascal（Step-4 已授权） | name_em 非空返回、schema 匹配 ≥ 90%、零持久化；**预算未消耗（actual_calls=0），仅 Fix+Verify+Review 通过后另立 one-call continuation（R1）**。**（R2）superseded / out-of-scope**：PR-2 不再构成可执行目标，预算**永久废弃**（§2.6）；本行保留为历史定义，不得执行 |

**后续 Gate（不在本链）**：PR-DDL-P3A（Mongo 集合创建 + 索引，已冻结，主 RFC §13.6）、G-A-2（refresh 生产激活）、PR-CANARY-P3A（手动 canary 写入）——均需 Pascal 独立确认，不在 Step-4 授权内。

---

## 7. 验收标准

### 7.1 功能验收

- [ ] RFC-03-014-p3a-readonly-gate.md 与 SPEC-03-014-p3a-readonly-gate.md 两份独立文档存在且互相交叉引用
- [ ] 每份文档区分「已验证事实」「假设」「待验证」「Pascal 授权 Gate」
- [ ] 清晰区分「可用性审计 / Mongo 只读预检 / Provider schema smoke」与「生产激活 / 数据入库 / 可交易信号」
- [ ] 每个 Gate（PR-0/1/2）都有具体 allowlist、停止条件、后续 Verify 的证据标准（**R2：PR-2 条目已 superseded / out-of-scope，见 §2.6，仅 PR-0/PR-1 为可执行 Gate**）
- [ ] 明确全局 OUT 清单（含 `cons_em`、P3-B/P3-C/northbound、Git 写、秘密输出）
- [ ] 与主 RFC-03-014 / SPEC-03-014（§6.2、§13.1、§13.4.5）及 P3-A RFC/SPEC V0.2 契约无冲突
- [ ] 声明本 Gate 成功不构成生产激活、数据入库或可交易信号
- [ ] **R1：三集合（sector_snapshot / stock_capital_flow / market_sentiment_snapshot）明示为 designated historical baseline，presence 非 FAIL（§2.4 裁定 1）**
- [ ] **R1：PR-0 外部输出仅 single aggregate verdict + generic source-kind + generic error-class，禁止逐 key 名称/状态/password marker/路径（§2.4 裁定 2）**
- [ ] **R1：既有两份 gitignored evidence 明示为不合规本地工件，developer Fix 仅删除/替换为合规聚合版（§2.4 裁定 3）**
- [ ] **R1：PR-1 不可重放；PR-2 预算未消耗，仅 Fix+Verify+Review 通过后另立 one-call continuation（§2.4 裁定 4）**（**R2：one-call continuation 永久废弃，见 §2.6**）
- [ ] **R1：file-declared / runtime env absent = conditional，非 secret 值有效性或生产授权（§2.4 裁定 5）**
- [ ] **R2（本卡 `t_f85382b3`）：P0 incident record 落档于 §2.5，包含事件事实（时间/脚本/三 host/TLS ok/EXIT=0）、裁定（越界成立；TLS 可达 ≠ Provider 可用，禁止以 TCP/TLS 直连结果为 Provider 可用性证据；Cold-skip PR-2=ProviderUnavailable 非 PASS）、actual_calls 字段语义（attempts=1 / success_calls=0）、t_e94a487a「119/119 零 .env read」表述修正（2 个 `--live-read` 测试真实 read_text skills/.env，非泄露）；落档完成即 P0 收口并解锁 Step-4 Closeout**

### 7.2 非功能验收

- [ ] 不触发真实 Mongo / Provider / 网络调用（静态检查：本阶段无 `pymongo.MongoClient` / `akshare.stock_*` 调用代码）
- [ ] 不读取 / 输出任何 secret value、URI credentials 或 `.env` 内容
- [ ] 不修改 DESIGN（由 T2 负责）、不合并 RFC 与 SPEC
- [ ] 不修改主 RFC/SPEC/DESIGN-03-014 已有内容（仅交叉引用）
- [ ] `git diff --check` exit 0
- [ ] `git diff --name-status` 中本卡 diff 仅含本 RFC 和对应 SPEC 两份文档（docs/rfc/03_data 与 docs/spec/03_data 允许路径）
- [ ] 声明所有板块/行业数据为辅助研究数据，不构成交易指令或投资建议

### 7.3 与主 RFC 的一致性验收

- [ ] Gate 编号 PR-0/PR-1/PR-2 与主 RFC §6.2 / §13.1 一致
- [ ] PR-2 的 `name_em` 唯一 endpoint 裁定与 P3-A RFC/SPEC V0.2 一致（不引用 `rank_em`、不以 `cons_em` 为主数据源）—— **R2**：裁定保留为历史事实；PR-2 不得执行（§2.6）
- [ ] B2 冻结证据（offline stub → 待授权 live-read）被正确继承
- [ ] 本 RFC 不引入与主 RFC 冲突的决策

---

## 8. 开放问题

- [ ] OQ-GATE-1：PR-2 的 `name_em()` 线上返回的 `领涨股票` 列是代码还是名称（P3-A OQ-P3A-6）——本 Gate 只记录字段名/数量/类型，不解析该语义；解析留待后续映射设计。 —— **superseded（R2）**：`name_em` 实时板块排行移出 Phase 3 目标（§2.6），本开放问题不再适用；保留为历史。
- [ ] OQ-GATE-2：`name_em()` 是实时排名，无历史日期维度（P3-A OQ-P3A-7）——本 Gate 只验证实时可用性；`snapshot_date` 语义由后续激活设计裁定。 —— **superseded（R2）**：不再适用；保留为历史。
- [ ] OQ-GATE-3：若 `name_em()` 仍因 egress 限制失败（endpoint_unreachable），单变量网络诊断（切换网络出口 / TLS 版本检查）由 Pascal 手动还是 Agent 辅助？本 Gate 不执行该诊断。 —— **superseded（R2）**：PR-2 不再执行，本问题不再适用；保留为历史。
- [ ] OQ-GATE-4：PR-1 意外发现 P3 预期集合已存在时，Pascal 判断「遗留 vs 意外」的决策入口（board comment / 口头确认）——本 Gate 只负责记录与停止。 —— **已闭合（R1）**：历史集合语义已由 R1 裁定（三集合为 designated historical baseline，presence 非 FAIL，§2.4 裁定 1）；本 OQ 指向 R1 裁定，不再开放。

---

## 9. 参考资料

- RFC-03-014（Unified Data Phase 3 主 RFC，V0.26）—— §6.2 / §13.1 PR-0~PR-4 Gate 表、§13.4.5 B2 冻结证据、§P0/P1 状态矩阵
- SPEC-03-014（Phase 3 契约，V0.26）—— §14.4.5 PR smoke 可执行契约、§14.5 Zero-Persistence-Write
- DESIGN-03-014（Phase 3 详细设计，V0.33）—— §15.x T4 preflight 工具链（scripts/t4_preflight/）
- RFC/SPEC-03-014-p3a-sector-provider-activation（V0.2）—— `name_em` 共享 endpoint 裁定、字段映射、smoke 最小参数
- 历史 DESIGN-03-014-p3a-sector-provider-activation（fake-only，不得重新激活）
- 代码入口：`scripts/t4_preflight/`（audit_secret.py / preflight_mongo.py / smoke_sector.py / config.py / provider_client.py / mongo_client.py）、`skills/data/data-pipeline/scripts/loaders/mongodb_loader.py`（PortfolioMongoLoader）、`skills/data/unified_data/providers/sector_client.py`（AKShareSectorClient）
- B2 smoke 冻结证据：`/tmp/yquant-b2-pr234-20260726/`（只读副本，不可移动/提交/重跑）
- 历史 smoke 报告格式：`docs/rfc/03_data/smoke_reports/`（audit-secret-*.yaml / preflight-mongo-*.yaml / smoke-sector-*.yaml）

---

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.4 | 2026-08-04 | **R2 Scope-Scission（本卡 `t_51c36693`）**：Pascal 2026-08-04 范畴裁定 `name_em` 实时板块排行移出 Phase 3 目标（新增 §2.6）——PR-2 预算**永久废弃**、不得 retry / replacement probe / 替代 endpoint / 实时 refresh；`t_55d44505` / `t_81432128` 标记 superseded / historical evidence；P3-A 仅保留盘后/历史、按 trade_date 可复现的 sector read-path 验证（无实时 Provider 调用）；PR-2 历史结果（ProviderUnavailable + netprobe 越界）保留为历史事实、不作生产能力失败或 recovery 依据。§2.5 P0 incident record 保留（补一行指向 §2.6）；§3.1 / §4.1 / §5.3 / §6.2 / §7.1 / §7.3 中 PR-2 条目标记 superseded / out-of-scope（R2）；§8 OQ-GATE-1/2/3 标记 superseded、OQ-GATE-4 已闭合（指向 R1） | YQuant-Principal |
| V0.3 | 2026-08-04 | **P0 Incident Record 落档（本卡 `t_f85382b3`，T5 Final Review `t_14f0590d` REVISE 闭环）**：新增 §2.5，固化 2026-08-04 12:19:56 netprobe 越界事件（`/tmp/yquant_pr2_netprobe.py`，`socket.create_connection` + `ssl.wrap_socket` 直连 `82.push2.eastmoney.com` / `push2.eastmoney.com` / `www.baidu.com` 三 host:443，全部 TLS ok、EXIT=0；超出 T3 single-call allowlist，含与 Provider 无关的 www.baidu.com）。裁定：① 越界事实成立（P0）；② TLS 可达 ≠ Provider 可用，禁止以 TCP/TLS 直连结果为 Provider 可用性证据；③ Cold-skip 业务结果 PR-2=ProviderUnavailable（非 PASS）可接受。附加记录项：① `actual_calls` 字段语义澄清（attempts=1 / success_calls=0，smoke 脚本成功路径置 1、异常路径打印初始 0）；② `t_e94a487a`「119/119 零 .env read」表述修正（2 个 `--live-read` CLI 测试真实 read_text skills/.env，非泄露）。**本 record 落档完成即 P0 收口，解锁 Step-4 Closeout**；SPEC/DESIGN 版本指针不变（本卡仅 RFC 审计固化） | YQuant-Principal |
| V0.2 | 2026-08-04 | R1 契约修订：① 三集合明示为 designated historical baseline（presence 非 PR-1 FAIL，禁止枚举陌生集合名）；② PR-0 外部输出收敛为 single aggregate verdict + generic source-kind + generic error-class（禁止逐 key 名称/状态/password marker/路径）；③ 既有两份 gitignored evidence 定为不合规本地工件，developer Fix 仅删除/替换为合规聚合版；④ PR-1 不可重放，PR-2 预算未消耗（actual_calls=0），仅 Fix+Verify+Review 通过后另立 one-call continuation；⑤ file-declared / runtime env absent = conditional，非 secret 值有效性或生产授权 | YQuant-Principal |
| V0.1 | 2026-08-04 | 初始创建：P3-A Step-4 PR-0/PR-1/PR-2 受控只读 Gate 的动机、授权边界、风险、停止/回滚、成功/失败语义 | YQuant-Principal |
