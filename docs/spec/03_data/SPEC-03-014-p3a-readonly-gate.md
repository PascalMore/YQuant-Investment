# SPEC-03-014: P3-A PR-0 / PR-1 / PR-2 受控只读 Gate — 可执行契约

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-08-04 |
| 最后更新 | 2026-08-07 |
| 版本号 | V0.4 |
| 来源 RFC | RFC-03-014-p3a-readonly-gate（V0.5） |
| 关联 RFC | RFC-03-014（Phase 3 主 RFC，V0.26）、RFC-03-014-p3a-sector-provider-activation（V0.2）、RFC-03-007（Unified Data Layer 总纲）、RFC-03-012（Phase 1D Provider 激活模式参考） |
| 关联 SPEC | SPEC-03-014（Phase 3 主 SPEC，V0.26） |
| 关联 Design | DESIGN-03-014（Phase 3 设计 V0.33，§15.x T4 preflight 工具链）；历史 DESIGN-03-014-p3a-sector-provider-activation（fake-only，不得重新激活）；关联 DESIGN-03-014-p3a-readonly-gate（V0.4） |
| 目标模块 | unified_data（`skills/data/unified_data/`）+ t4_preflight（`scripts/t4_preflight/`） |
| 适配 Agent | YQuant-Principal（T2 Design）、YQuant-Developer-Engineer（T3 controlled execution，仅授权后）、YQuant-Test-Engineer（Verify） |

---

## 0. 术语对齐与基线锚定

本 SPEC 继承 SPEC-03-014（Phase 3 主 SPEC V0.26）与 SPEC-03-014-p3a-sector-provider-activation（V0.2）的全部基线，不重述背景。以下锁定 P3-A Step-4 只读 Gate 链必须一致的措辞：

- **Step-4 只读 Gate 链** = PR-0（凭证源可用性审计）→ PR-1（MongoDB 只读预检）→ PR-2（有界 Sector Provider smoke）三个受控只读 Gate 的串行执行契约。**Gate pass ≠ 生产激活、数据入库或可交易信号**。**R2（§0.2）**：PR-2 已 **superseded / out-of-scope**，可执行只读链仅 PR-0 → PR-1（PR-1 亦不可重放，R1）；PR-2 定义保留为历史。
- **Pascal 授权范围**：仅 PR-0 / PR-1 / PR-2 三项只读动作（Step-4）。不含 DDL/DML、upsert、refresh、cache write、file write（除允许的非敏感临时运行日志 / 最终 redacted evidence）、原始 payload 保存、Mongo 业务读、任意其他 Provider/HTTP、P3-B/P3-C/northbound、`cons_em`、services/restarts、cron/systemd、配置/依赖修改、Git 写、秘密输出。**R2（§0.2）**：PR-2 授权随 scope removal 一并废弃，不再构成可执行动作。
- **`name_em` 裁定**（P3-A RFC/SPEC V0.2）：`stock_board_industry_name_em()` 为 `sector.snapshot` / `sector.ranking` 共享主 endpoint（无参数、匿名、返回板块级排名 12 列）。`stock_board_industry_rank_em` **不存在**；`stock_board_industry_cons_em` 返回成分股列表（个股粒度），**不作为** sector snapshot/ranking 主数据源。**PR-2 禁止调用 `cons_em`**。**R2（§0.2）**：`name_em` 实时板块排行移出 Phase 3 目标，PR-2 不得执行；endpoint 裁定保留为历史事实。
- **B2 冻结证据**：2026-07-26 B2 smoke 对 `cons_em("BK0489")` 调用 2 次均 SSLError。`sector.snapshot` / `sector.ranking` 当前为 **offline stub**（主 SPEC §P0.2 状态矩阵）；仅允许后续单变量网络诊断后重试 live-read，且须 Pascal 独立授权。证据冻结在 `/tmp/yquant-b2-pr234-20260726/`（只读副本，不可移动/提交/重跑）。
- **credential 来源**：`skills/.env`（Phase 2 PortfolioMongoLoader 认证语义，组件式五键 `MONGODB_HOST` / `MONGODB_PORT` / `MONGODB_USERNAME` / `MONGODB_PASSWORD` / `MONGODB_DATABASE`）。`MONGO_URI` / `MONGODB_URI` / `./.env` / Hermes profile `.env` 均 superseded，不是候选。
- **exit code 基线**（主 SPEC §14 / DESIGN §15.8）：0=PASS、1=CONDITIONAL_PASS、2=FAIL、3=NOT_AUTHORIZED。
- **R1 裁定锚定（2026-08-04，对应 RFC §2.4）**：
  - **三集合为 designated historical baseline**（`03_data_ud_market_sector_snapshot`、`03_data_ud_stock_capital_flow`、`03_data_ud_market_sentiment_snapshot`）：presence 本身 **不是** PR-1 FAIL，而是 PR-1 PASS 基线；**禁止输出或枚举陌生集合名**；不允许 read business docs、不允许 DDL/DML。
  - **PR-0 外部输出仅 single aggregate authorization verdict + generic source-kind + generic redacted error-class**；禁止逐 key 名称、逐 key presence/runtime/declaration 状态、password marker、路径、值/长度/hash/URI。
  - **既有两份 gitignored evidence（`docs/rfc/03_data/smoke_reports/audit-secret-20260804.yaml`、`docs/rfc/03_data/smoke_reports/preflight-mongo-20260804.yaml`）为不合规本地工件**：developer Fix 仅删除或替换为合规聚合版；审计事实保留在 Kanban，不复制不合规内容到 repo/docs。
  - **PR-1 不可重放**（既有执行 `mongo_calls=2`、`write_operations=0` 已冻结）；**PR-2 预算未消耗**（`actual_calls=0`），仅 Fix + 独立 Verify + Review 通过后另立 one-call continuation。**R2：one-call continuation 永久废弃（§0.2），PR-2 预算不再消耗。**
  - **file-declared / runtime env absent = conditional**，不等价于 secret 值有效性或生产授权。
  - **R1 复核确认（2026-08-07，本卡 `t_76db1800`）**：上述五裁定已编码并与 RFC §2.4 / DESIGN §2.6 同步；stat 复核两份不合规 evidence（`audit-secret-20260804.yaml` / `preflight-mongo-20260804.yaml`）已删除（Fix-1 删除分支满足，§8.1）；补充历史事实——PR-2 `name_em` 唯一一次受控 smoke 由并行卡 `t_91ffe99e`（Pascal 重新授权）执行为 `provider-unavailable-frozen`，R2 永久废弃语义不变（§0.2）。

### 0.1 本 SPEC 不重复定义的契约

| 契约 | 主 SPEC 定义位置 | 本 SPEC 引用方式 |
|---|---|---|
| Gate 编号与触发/停止条件 | SPEC-03-014 §14.1 / RFC-03-014 §13.1 | 继承，精确化为本链 |
| 字段映射阈值（≥90% pass / 70-90% conditional / <70% fail） | SPEC-03-014 §14.4.4（A-DRIFT-5） | PR-2 停止条件引用（**R2：历史引用；PR-2 不再执行，见 §0.2**） |
| Zero-Persistence-Write | SPEC-03-014 §14.5 | 三 Gate 全局约束 |
| `name_em` 字段集（12 列） | SPEC-03-014-p3a §3.1 / §3.2 | PR-2 schema 比对基线（**R2：历史基线；PR-2 不再执行，见 §0.2**） |
| AKShare 匿名（无 token） | RFC-03-014 OQ-8 | PR-0 跳过 AKShare 密钥审计 |

### 0.2 R2 Scope-Scission

> 本节与 RFC §2.6 / DESIGN §2.7 **逐项一致**。Pascal 2026-08-04 范畴裁定（优先级最高）覆盖并取代此前所有将 PR-2 视为可执行目标的表述。

**裁定**：`stock_board_industry_name_em()` / 行业板块 `name_em` 属于**实时板块排行**，不在本次 Unified Data Phase 3 的实现/生产验证目标之内。

1. **PR-2 的 name_em 单次预算永久废弃**（不因 scope removal 留作后门）：`t_55d44505` / `t_81432128` 标记为 **superseded / historical evidence**，不得 unblock、retry、创建 replacement probe 或改用其他 AKShare endpoint。
2. **禁止**为 name_em 新建 Provider recovery、替代 endpoint、实时 refresh 或任何 live retry。
3. P3-A 仅保留**盘后/历史、按 trade_date 可复现**的 sector read-path 验证（消费既有历史集合/物化数据，不发起任何实时 Provider 调用）。
4. PR-2 历史结果（一次尝试 `ProviderUnavailable`、一次越界 netprobe）保留为历史事实，但**不得**作为 P3-A 生产能力失败或后续 recovery 依据。

---

## 1. 需求摘要

将 RFC-03-014-p3a-readonly-gate 的只读 Gate 需求落为可执行契约，核心交付 3 件事：

1. **PR-0 可计算审计契约**：候选 env 文件、五键清单、探测命令 allowlist、输入/输出脱敏契约、NOT_AUTHORIZED 条件、exit code 语义。
2. **PR-1 可计算预检契约**：既有连接路径（`PortfolioMongoLoader` / `PreflightRunner`）、ping + listCollections 命令 allowlist、集合名比对范围、零写入证明、失败即停条件。
3. **PR-2 可计算 smoke 契约**：单次 `name_em` 受控请求、请求预算/超时、响应 schema/非空/字段合理性停止条件、错误分类（含 SSL/connection）、fail-stop、零持久化。

---

## 2. 范围

### 2.1 In Scope

- [x] PR-0 命令级 allowlist 与脱敏契约定义（§3.1）
- [x] PR-1 命令级 allowlist（ping + listCollections）、集合名比对、零写入证明定义（§3.2）
- [x] PR-2 单次 `name_em` 请求预算、超时、停止条件、错误分类定义（§3.3）—— **superseded / out-of-scope（R2）**：定义保留为历史，不得作为可执行契约（§0.2）
- [x] 全局 OUT 清单与禁止行为（§2.2 / §7）
- [x] 验收矩阵与后续 Verify 证据标准（§5 / §6）
- [x] T2 Design 交接点（§8）

### 2.2 Out of Scope

- ❌ 真实 Mongo / Provider / 网络调用（本卡为 T1 文档阶段；T2 Design 后才允许创建 T3 controlled execution）
- ❌ DDL/DML、upsert、refresh、cache write、Mongo 业务读（find / 统计 / 索引检查）
- ❌ file write（除允许的非敏感临时运行日志 / 最终 redacted evidence YAML）
- ❌ 原始 payload 保存
- ❌ 任意其他 Provider / HTTP、P3-B/P3-C/northbound
- ❌ `cons_em` 调用
- ❌ services / restarts / cron / systemd / gateway / webhook
- ❌ 配置 / 依赖修改、Git stage/commit/push/reset/stash/clean
- ❌ 读取 / 打印 / 序列化 / hash / 枚举 / 日志化任何 secret value、完整连接串、URI credentials 或 `.env` 内容
- ❌ 修改 DESIGN（由 T2 负责）、合并 RFC 与 SPEC
- ❌ 修改主 SPEC-03-014 / SPEC-03-014-p3a 已有内容（仅交叉引用）
- ❌ 重新激活历史 P3-A fake-only Design 或执行其任何授权
- ❌ **R2：为 name_em 新建 Provider recovery / 替代 endpoint / 实时 refresh / 任何 live retry；执行 PR-2 smoke 或创建 one-call continuation（PR-2 预算永久废弃，§0.2）**

---

## 3. 功能规格

### 3.1 PR-0 — Credential source availability audit（F-PR0-001 ~ F-PR0-012）

> 候选来源：`skills/.env`（唯一）。候选键：`MONGODB_HOST` / `MONGODB_PORT` / `MONGODB_USERNAME` / `MONGODB_PASSWORD` / `MONGODB_DATABASE`。参考实现：`scripts/t4_preflight/audit_secret.py` + `secrets.py`（`SecretVerifier`）。

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-PR0-001 | 文件存在性探测 | `skills/.env` 路径 | `file_exists: bool` | 只允许 `os.path.isfile`；禁止读取文件内容 |
| F-PR0-002 | 文件可读性探测 | `skills/.env` 路径 | `file_readable: bool` | 只允许 `os.access(path, os.R_OK)` |
| F-PR0-003 | 五键声明探测 | 五键名 | `key_declared: bool`（逐键） | 只允许 `dotenv_values()` 键名比对（dry-run）或 `os.getenv` 布尔探测（live）；禁止输出值/长度/URI/用户名 |
| F-PR0-004 | env 可加载性探测 | 五键名 | `is_loadable: bool` | 仅 live 模式；只返回布尔结论 |
| F-PR0-005 | 聚合结论 | — | `overall.verdict`（single aggregate）+ `source_kind` + `error_class` | **R1：外部输出仅 aggregate verdict（authorized/conditional_authorized/unauthorized）+ generic source-kind + generic redacted error-class；禁止逐 key 名称、逐 key presence/runtime/declaration 状态、password marker、路径** |
| F-PR0-006 | NOT_AUTHORIZED 判定 | 五键探测结果 | exit 3 | 任一：文件不存在 / 任意一键缺失或空白 / `MONGODB_PORT` 非 int / `MONGODB_DATABASE != "tradingagents"` |
| F-PR0-007 | authorized 判定 | 五键探测结果 | exit 0 | 文件存在 + 五键声明 + env 可加载 |
| F-PR0-008 | conditional 判定 | 五键探测结果 | exit 1 | 部分满足（如文件存在但 env 不可加载，或反之）。**R1：file-declared / runtime env absent = conditional，不等价于 secret 值有效性或生产授权** |
| F-PR0-009 | 报告输出 | — | `audit-secret-YYYYMMDD.yaml` | **仅含 single aggregate verdict + generic source-kind + generic redacted error-class（R1 收紧）**；写入 `docs/rfc/03_data/smoke_reports/`（允许的 redacted evidence 路径） |
| F-PR0-010 | 禁止输出 | — | — | 禁止输出值、长度、URI、用户名、全路径+键值组合、`.env` 内容（主 RFC §13.1 PR-0）；**禁止逐 key 名称、逐 key presence/runtime/declaration 状态、password marker、路径（R1）** |
| F-PR0-011 | 跳过 AKShare 密钥审计 | — | — | AKShare 匿名数据源，无 token 审计（RFC OQ-8） |
| F-PR0-012 | 失败即停 | exit 非 0 | 停止 PR-1/PR-2（PR-1 为 PR-2 前置） | 不 fallback 到其他来源；不执行任何写入。**R2：PR-2 已 superseded，见 §0.2** |

### 3.2 PR-1 — MongoDB read-only preflight（F-PR1-001 ~ F-PR1-014）

> 参考实现：`scripts/t4_preflight/preflight_mongo.py` + `mongo_client.py`（`LegacyConfigResolver` → `MongoClientFactory` → `PreflightRunner`）；组件式构造连接（host/port/username/password/authSource），非 URI。既有 `PortfolioMongoLoader`（`skills/data/data-pipeline/scripts/loaders/mongodb_loader.py`）为同一认证语义的 approved connection path。

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-PR1-001 | 五键解析 | `skills/.env` | `ResolvedConfig`（布尔结论） | 仅 `dotenv_values()` 本地解析；不污染 `os.environ`；值不进结果对象（`ResolvedConfig` 不携带值） |
| F-PR1-002 | 数据库名校验 | `MONGODB_DATABASE` | `all_resolved` / exit 3 | 必须等于 `tradingagents`；否则 NOT_AUTHORIZED，**不构造客户端** |
| F-PR1-003 | 客户端构造 | 五键 | `pymongo.MongoClient` | 组件式（host/port/username/password/authSource=db）；`serverSelectionTimeoutMS` ≤ 3000 |
| F-PR1-004 | ping | — | `admin.command("ping")` | 唯一允许的 admin 命令；失败分类：dns_failure / timeout / auth_failure → exit 2 |
| F-PR1-005 | listCollections | — | `db.list_collection_names()` | 唯一允许的集合枚举命令；无 filter |
| F-PR1-006 | 集合名比对范围 | P3 基线清单 | `baseline_collections[]`（designated 三集合 presence）+ `baseline_unexpected[]` | 仅与 `P3_BUSINESS_COLLECTIONS` 比对：`03_data_ud_market_sector_snapshot` / `03_data_ud_stock_capital_flow` / `03_data_ud_market_sentiment_snapshot`。**R1：三集合为 designated historical baseline，presence 即基线，不是 FAIL；禁止输出或枚举陌生集合名** |
| F-PR1-007 | 零写入证明 | — | 报告账本 `mongo_calls` ≤ 2、`write_operations = 0` | 命令级 allowlist 只含 ping + listCollections；`PREFLIGHT_MAX_OPERATIONS = 4` |
| F-PR1-008 | before/after 集合清单一致性 | — | 报告 `collections` | 执行前后 `list_collection_names()` 结果一致（等效只读 command semantics 证据）；报告中不输出任何业务 document；**不枚举陌生集合名（R1）** |
| F-PR1-009 | 基线集合 presence 观测 | P3 基线清单 | exit 0（pass） | **三张 designated baseline 集合 presence 可观测即 pass（存在即预期基线，非 FAIL；R1）** |
| F-PR1-010 | 非基线异常校验 | 基线清单之外的 P3 命名集合 | exit 2（fail）+ `UNEXPECTED_EXISTENCE` warning | **仅当发现非 designated 的陌生 P3 命名集合时**停止，需 Pascal 判断遗留 vs 意外；三张基线集合存在本身不触发（R1） |
| F-PR1-011 | listCollections 未授权 | — | exit 1（conditional_pass） | ping 成功但 listCollections 失败 → 记录 warning（`list_collections_unauthorized`） |
| F-PR1-012 | 连接失败 | — | exit 2（fail） | DNS / 超时 / 认证拒绝 → 立即停在 PR-1；不 fallback 到新连接串 / shell client / 服务重启 |
| F-PR1-013 | 报告输出 | — | `preflight-mongo-YYYYMMDD.yaml` | 写入 `docs/rfc/03_data/smoke_reports/`（允许的 redacted evidence 路径）；不含任何秘密值 |
| F-PR1-014 | 禁止业务读 | — | — | 禁止 `find` / `find_one` / 统计 / 索引检查 / DDL / DML / admin mutation |

### 3.3 PR-2 — bounded Sector Provider smoke（F-PR2-001 ~ F-PR2-016）

> ⚠️ **R2 superseded / out-of-scope（§0.2）**：本节（F-PR2-001 ~ F-PR2-016）为历史功能规格。Pascal 2026-08-04 范畴裁定 `name_em` 实时板块排行不在 Phase 3 实现/生产验证目标内；PR-2 预算**永久废弃**，**不得作为可执行契约**；不得重试、不得创建 replacement probe、不得改用其他 AKShare endpoint。以下条目保留为历史定义。

> 参考实现：`skills/data/unified_data/providers/sector_client.py`（`AKShareSectorClient`，`get_sector_snapshot` / `get_sector_ranking` 均经 `_call_name_em` 调用 `stock_board_industry_name_em()`）。**注意**：历史 `scripts/t4_preflight/smoke_sector.py` 的 live-read 路径对 snapshot 调用 `cons_em`（`provider_client.py fetch_sector_snapshot`），**与 P3-A V0.2 裁定冲突**，本链 PR-2 **不得使用该 cons_em 路径**；T2 Design 必须将 T3 执行入口固定为 `AKShareSectorClient`（name_em-only）或等效 name_em-only 适配层。

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-PR2-001 | endpoint 固定 | — | `stock_board_industry_name_em()` | 唯一允许的 live-read endpoint；无参数（实时排名） |
| F-PR2-002 | 请求预算 | — | `provider_attempts = 1`、`actual_calls ≤ 1` | 单次受控请求；snapshot 与 ranking 共享同一次 `name_em()` 响应（snapshot 在内存按 `sector_code` 过滤） |
| F-PR2-003 | 超时 | — | — | 客户端超时固定（如 `AKShareSectorClient(timeout=30.0)`）；超时 → ProviderUnavailableError → fail-stop |
| F-PR2-004 | 不重试 | 失败 | — | 失败不重试（主 RFC §13.4.5.5 零写入边界）；`retry_count = 0` |
| F-PR2-005 | 响应非空校验 | `name_em()` 返回 | — | 空 DataFrame（row_count=0）→ exit 2（X2 保守：空返回维持 fail，主 RFC §13.4.5.3） |
| F-PR2-006 | 响应 schema 校验 | 返回列名 | 字段匹配比例 | 与离线源码验证的 12 列 expected（`排名/板块名称/板块代码/最新价/涨跌额/涨跌幅/总市值/换手率/上涨家数/下跌家数/领涨股票/领涨股票-涨跌幅`）比对 |
| F-PR2-007 | 字段匹配阈值 | 匹配比例 | verdict | ≥90% → pass（exit 0）；70-90% → conditional_pass（exit 1）；<70% → fail（exit 2，主 SPEC A-DRIFT-5） |
| F-PR2-008 | 字段合理性停止 | 返回列 | — | 核心列缺失（板块代码/板块名称/涨跌幅）→ fail；类型不匹配（如涨跌幅非数值）→ fail |
| F-PR2-009 | SSL/TLS/连接错误 | 异常 | `ProviderUnavailableError` | SSL / TLS / ConnectionError / Timeout / DNS → 记录错误类别（error_class）后 fail-stop |
| F-PR2-010 | API 内部错误 | 异常 | `ProviderError` | API 内部错误 / 字段缺失 → 记录证据后 fail-stop |
| F-PR2-011 | egress 限制标注 | ProxyError/ConnectionError | `endpoint_unreachable` | 仅当所有调用失败且错误类别为 ProxyError/ConnectionError 时标注；需 Pascal 决定是否做单变量网络诊断 |
| F-PR2-012 | 输出最小化 | — | 字段名/数量/类型、redacted schema mismatch、时间戳、source trace | 不输出原始 payload；sample rows ≤ 5（Sanitizer 截断） |
| F-PR2-013 | 禁止持久化 | — | — | 不写 Mongo / cache / file（除允许的非敏感临时运行日志 / 最终 redacted evidence YAML） |
| F-PR2-014 | 禁止 `cons_em` | — | — | 任何路径不得调用 `stock_board_industry_cons_em`；历史 smoke_sector.py cons_em 路径不得使用 |
| F-PR2-015 | 不触 P3-B/P3-C/northbound | — | — | 不调用 flow / sentiment / northbound 相关任何 endpoint |
| F-PR2-016 | 报告输出 | — | `smoke-sector-YYYYMMDD.yaml` | 写入 `docs/rfc/03_data/smoke_reports/`（允许的 redacted evidence 路径）；账本含 provider_attempts / actual_calls / retry_count / fallback_count / mongo_calls / write_operations |

---

## 4. 数据与接口契约

### 4.1 报告证据契约（Gate evidence YAML）

| 报告 | 允许路径 | 核心字段 | 禁止字段 |
|---|---|---|---|
| PR-0 | `docs/rfc/03_data/smoke_reports/audit-secret-YYYYMMDD.yaml` | `generated_at`、`overall.verdict`（single aggregate：authorized/conditional_authorized/unauthorized）、`source_kind`（generic）、`error_class`（generic redacted） | **任何 secret value、长度、URI、用户名、路径+键值组合、逐 key 名称、逐 key presence/runtime/declaration 状态、password marker（R1）** |
| PR-1 | `docs/rfc/03_data/smoke_reports/preflight-mongo-YYYYMMDD.yaml` | `generated_at`、`live_read`、`connectivity`、`latency_ms`、`baseline_collections`（**仅 designated 三集合 presence 观测，不枚举陌生集合名；R1**）、`baseline_unexpected`、`warnings`、`overall.verdict` | 任何业务 document、秘密值、URI、陌生集合名枚举 |
| PR-2 | `docs/rfc/03_data/smoke_reports/smoke-sector-YYYYMMDD.yaml` | `capability`、`provider`、`smoke_at`、`connectivity`、`auth`、`permissions`、`field_mapping`、`data_sample`（row_count + ≤5 sample rows）、`ledger`、`overall` | 原始 payload、秘密值。**R2：PR-2 不再执行，不再生成新 PR-2 evidence；schema 保留为历史** |

### 4.2 零写入证据标准（Verify 阶段核对项）

- PR-1：报告账本 `mongo_calls ≤ 2`、`write_operations = 0`；命令级审计（执行过程只出现 ping + listCollections）；before/after `list_collection_names()` 结果一致。
- PR-2：报告账本 `mongo_calls = 0`、`write_operations = 0`、`retry_count = 0`、`fallback_count = 0`；输出文件仅限 smoke_reports 下 YAML；无 Mongo/cache/file 写日志。**R2：PR-2 不再执行，本项 superseded，仅适用于历史 evidence 审计（§0.2）**。

### 4.3 兼容性约束

- 与主 SPEC-03-014 §14.5 Zero-Persistence-Write 一致。
- 与 SPEC-03-014-p3a §3.1 endpoint 契约一致（`name_em` 共享、`rank_em` 不存在、`cons_em` 非主源）。
- 历史 fake-only Design 及其执行授权不适用本链。

---

## 5. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-GATE-001 | RFC 和 SPEC 两份独立文档存在且互相交叉引用 | 文件存在性检查 |
| A-GATE-002 | PR-0 契约定义完整（F-PR0-001 ~ F-PR0-012） | 静态检查 |
| A-GATE-003 | PR-1 契约定义完整（F-PR1-001 ~ F-PR1-014，含零写入证明） | 静态检查 |
| A-GATE-004 | PR-2 契约定义完整（F-PR2-001 ~ F-PR2-016，含预算/超时/停止/错误分类）—— **superseded / out-of-scope（R2）**：定义保留为历史，不再构成可执行契约（§0.2） | 静态检查 |
| A-GATE-005 | 全局 OUT 清单覆盖全部禁止行为（含 `cons_em`、P3-B/P3-C/northbound、Git 写、秘密输出） | 静态检查 |
| A-GATE-006 | 每个 Gate 有具体 allowlist、停止条件、后续 Verify 的证据标准 | 静态检查 |
| A-GATE-007 | 清晰区分「可用性审计 / Mongo 只读预检 / Provider schema smoke」与「生产激活 / 数据入库 / 可交易信号」 | 静态检查 |
| A-GATE-008 | 与主 RFC/SPEC-03-014（§6.2 / §13.1 / §14.4.5）及 P3-A V0.2 契约无冲突 | 交叉引用检查 |
| A-GATE-009 | 不触发真实 I/O（无 `pymongo.MongoClient` / `akshare.stock_*` 调用代码） | 静态 grep |
| A-GATE-010 | 不读取 / 输出任何 secret value、URI credentials 或 `.env` 内容 | 静态检查 |
| A-GATE-011 | 不修改 DESIGN、不合并 RFC 与 SPEC | 静态检查 |
| A-GATE-012 | `git diff --check` exit 0 | git 命令 |
| A-GATE-013 | `git diff --name-status` 仅含 RFC + SPEC 两份文档（docs/rfc/03_data 与 docs/spec/03_data 允许路径） | git 命令 |
| A-GATE-014 | 声明辅助研究数据，不构成交易指令或投资建议 | 静态 grep |
| A-GATE-015 | **R1：三集合明示为 designated historical baseline，presence 非 PR-1 FAIL，禁止输出/枚举陌生集合名（§0 R1 锚定 1）** | 静态检查 |
| A-GATE-016 | **R1：PR-0 外部输出仅 single aggregate verdict + generic source-kind + generic error-class，禁止逐 key 名称/状态/password marker/路径（§0 R1 锚定 2）** | 静态检查 |
| A-GATE-017 | **R1：既有两份 gitignored evidence 明示为不合规本地工件，developer Fix 仅删除/替换为合规聚合版（§0 R1 锚定 3）** | 静态检查 |
| A-GATE-018 | **R1：PR-1 不可重放；PR-2 预算未消耗，仅 Fix+Verify+Review 通过后另立 one-call continuation（§0 R1 锚定 4）**（**R2：one-call continuation 永久废弃，见 §0.2**） | 静态检查 |
| A-GATE-019 | **R1：file-declared / runtime env absent = conditional，非 secret 值有效性或生产授权（§0 R1 锚定 5）** | 静态检查 |

---

## 6. 测试要求

- **本阶段（T1）**：无执行类测试；静态验证（文件存在、交叉引用、git diff 边界）。
- **T3 controlled execution（后续，需 T2 Design + Pascal 确认）**：按本 SPEC 的 allowlist 与停止条件执行 PR-0 → PR-1 → PR-2；每 Gate 生成 redacted evidence YAML。**R2：PR-2 已 superseded / out-of-scope（§0.2），T3 范围仅 PR-0 → PR-1；PR-1 亦不可重放（R1），实际为审计既有只读 evidence。**
- **Verify（T4，后续）**：对照 §4.2 零写入证据标准逐项核对报告账本与命令级审计；检查 exit code 语义与 §3.x 一致。
- **不可自动化验证项**：真实 `name_em()` 线上 payload 的长期稳定性（属生产激活阶段，不在本链）。**R2：PR-2 已废弃（§0.2），本项不再适用，保留为历史。**

---

## 7. 实现约束

- **禁止事项**：真实 I/O（本 T1 阶段）、DDL/DML、upsert、refresh、cache write、file write（除允许的 evidence）、原始 payload 保存、Mongo 业务读、其他 Provider/HTTP、`cons_em`、P3-B/P3-C/northbound、services/restarts、cron/systemd、配置/依赖修改、Git 写、secret 读取/输出、修改 DESIGN、合并 RFC/SPEC、重新激活历史 fake-only Design。
- **依赖限制**：不新增第三方依赖（pymongo / akshare / python-dotenv 已在现有环境）。
- **性能/安全约束**：PR-1 超时 ≤ 3s、`PREFLIGHT_MAX_OPERATIONS = 4`；PR-2 单次请求、客户端超时固定、失败不重试（**R2：PR-2 不再执行，本约束为历史定义，见 §0.2**）；全程零持久化写。

---

## 8. T2 Design 交接点

T2 Design（由本卡后续阶段创建）必须交付：

| 内容 | 说明 |
|---|---|
| T3 执行编排 | PR-0 → PR-1 → PR-2 串行执行脚本/命令的精确入口与参数（禁止 `--force` / `--apply` / secret 参数）。**R2：仅 PR-0 → PR-1；PR-2 不执行（§0.2）** |
| PR-2 执行入口固定 | 必须固定为 `AKShareSectorClient`（name_em-only）或等效 name_em-only 适配层；**不得**使用历史 smoke_sector.py 的 cons_em 路径（F-PR2-014）。**R2 superseded / out-of-scope（§0.2）**：PR-2 不再成为后续 Design/执行的交接项，本行保留为历史 |
| evidence 报告模板 | 三个 YAML 的精确字段集（§4.1），含 Sanitizer 截断规则（**R2：PR-2 evidence 不再生成，仅 PR-0/PR-1 两个 YAML；PR-2 schema 保留为历史**） |
| allowlist / 禁止修改清单 | T3 允许读取/调用的文件与禁止修改路径 |
| 回滚条件 | 任一 Gate fail 的执行后处理（记录 + 停止 + 不降级写入） |

**禁止**：T2 不得重新激活历史 P3-A fake-only Design 的执行授权；不得将本链 Gate 扩大至 DDL/DML/refresh/cache/canary/cron。

### 8.1 R1 developer Fix 交接（2026-08-04 新增，替代原 T3 路径）

> 本卡（R1 amendment）**只修文档契约，不替代实际脱敏修复**。后续 developer Fix 是独立最小代码/工件修复卡，范围如下：

| 项 | 精确目标 | 待定 allowlist |
|---|---|---|
| Fix-1 | 删除或替换两份不合规 gitignored evidence：`docs/rfc/03_data/smoke_reports/audit-secret-20260804.yaml`、`docs/rfc/03_data/smoke_reports/preflight-mongo-20260804.yaml`，替换为**合规聚合版**（PR-0 仅 single aggregate verdict + generic source-kind + generic error-class；PR-1 仅 baseline 三集合 presence 观测，不枚举陌生集合名） | 仅上述两文件路径；删除或覆盖写，不得复制不合规内容到 repo/docs |
| Fix-2 | 审计 SecretVerifier / audit-secret CLI / PreflightRunner 的**输出与报告序列化路径**，确保外部输出不再出现逐 key 名称/状态/password marker/路径（对应 F-PR0-005/009/010、F-PR1-006/008/009/010 R1 契约） | 仅 `scripts/t4_preflight/` 只读 + `docs/rfc/03_data/smoke_reports/` 允许路径；无真实 I/O、无 Git 写 |
| Fix-3 | **不重跑 PR-1**（`mongo_calls=2`、`write_operations=0` 已冻结）；不重跑 PR-0 live probe（纯本地 stat/probe 可重跑仅当 Pascal 批准，默认不做） | 禁止 Mongo/Provider/network；无 PR-2 执行 |

> **R1 复核确认（`t_76db1800`，2026-08-07）**：本节 Fix-1/Fix-2/Fix-3 为 developer Fix 卡的精确目标与 allowlist。stat 复核：Fix-1 目标两份 evidence 已删除（删除分支满足），repo/docs 无不合规副本；F2 输出面审计、F3 不重放约束仍由 developer Fix 卡执行。**文档说明不替代实际脱敏修复。**

**Fix 完成后流程**：fresh Verify（T4）→ Review（T5）→ 均通过后，才可新建**单独的 one-call PR-2 continuation**（预算 `provider_attempts=1`、`actual_calls≤1` 未消耗，见 §3.3）。**本卡与 Fix 卡均不得顺带执行 PR-2。** **R2：one-call PR-2 continuation 永久废弃（§0.2）——PR-2 预算不再消耗，本句为历史编排，不得执行。**

---

## 9. 开放问题

- [ ] OQ-GATE-1：`name_em()` 线上返回的 `领涨股票` 列是代码还是名称（P3-A OQ-P3A-6）——本 Gate 只记录字段名/数量/类型，不解析该语义。 —— **superseded（R2）**：`name_em` 实时板块排行移出 Phase 3 目标（§0.2），不再适用；保留为历史。
- [ ] OQ-GATE-2：`name_em()` 是实时排名，无历史日期维度（P3-A OQ-P3A-7）——本 Gate 只验证实时可用性。 —— **superseded（R2）**：不再适用；保留为历史。
- [ ] OQ-GATE-3：若 `name_em()` 仍因 egress 限制失败（endpoint_unreachable），单变量网络诊断由 Pascal 手动还是 Agent 辅助？本 Gate 不执行该诊断。 —— **superseded（R2）**：PR-2 不再执行，不再适用；保留为历史。
- [ ] OQ-GATE-4：PR-1 意外发现 P3 预期集合已存在时，Pascal 判断「遗留 vs 意外」的决策入口。 —— **已闭合（R1）**：历史集合语义已由 R1 裁定（三集合为 designated historical baseline，presence 非 FAIL，§0 R1 锚定 1）；本 OQ 指向 R1 裁定，不再开放。

---

## 10. 声明

本 SPEC 中涉及的板块/行业数据为辅助研究数据，不构成交易指令或投资建议。该声明通过静态 grep 验证。

本 SPEC 不修改主 SPEC-03-014 / SPEC-03-014-p3a 的任何已有内容。所有契约以交叉引用方式继承主 SPEC，冲突时以主 SPEC 为准。

本 SPEC 的 Gate pass 仅证明「凭证可加载 + Mongo 只读可达 + name_em 返回结构与预期一致」，**不构成生产激活、数据入库或可交易信号**。**R2：PR-2 已 superseded / out-of-scope（§0.2），Gate pass 语义仅剩「凭证可加载 + Mongo 只读可达」；PR-2 定义保留为历史。**

---

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.4 | 2026-08-07 | **R1 复核确认（本卡 `t_76db1800`）**：确认 R1 五裁定已编码（§0）并与 RFC §2.4 / DESIGN §2.6 同步；stat 复核两份不合规 evidence 已删除（Fix-1 删除分支满足，§8.1）；补充历史事实——PR-2 `name_em` 唯一一次受控 smoke 由并行卡 `t_91ffe99e`（Pascal 重新授权）执行为 `provider-unavailable-frozen`（§0.2 R2 永久废弃语义不变）；Fix-1/2/3 精确目标与 allowlist 保持（§8.1），拒绝以文档说明替代实际脱敏修复 | YQuant-Principal |
| V0.3 | 2026-08-04 | **R2 Scope-Scission（本卡 `t_51c36693`）**：Pascal 2026-08-04 范畴裁定 `name_em` 实时板块排行移出 Phase 3 目标（新增 §0.2，与 RFC §2.6 / DESIGN §2.7 逐项一致）——PR-2 预算**永久废弃**、不得 retry / replacement probe / 替代 endpoint / 实时 refresh；`t_55d44505` / `t_81432128` 标记 superseded / historical evidence；P3-A 仅保留盘后/历史、按 trade_date 可复现的 sector read-path 验证（无实时 Provider 调用）；PR-2 历史结果（ProviderUnavailable + netprobe 越界）保留为历史事实、不作生产能力失败或 recovery 依据。§0 术语 / §2.1 / §2.2 / §3.1 / §3.3 / §4.1 / §4.2 / §5 / §6 / §7 / §8（含 §8.1）中 PR-2 可执行契约均标记 superseded / out-of-scope（R2）；§9 OQ-GATE-1/2/3 标记 superseded、OQ-GATE-4 已闭合（指向 R1）；§10 声明更新 Gate pass 语义 | YQuant-Principal |
| V0.2 | 2026-08-04 | R1 契约修订：① 三集合明示为 designated historical baseline（presence 非 PR-1 FAIL，禁止枚举陌生集合名）；② PR-0 外部输出收敛为 single aggregate verdict + generic source-kind + generic error-class（禁止逐 key 名称/状态/password marker/路径）；③ 既有两份 gitignored evidence 定为不合规本地工件，developer Fix 仅删除/替换为合规聚合版；④ PR-1 不可重放，PR-2 预算未消耗（actual_calls=0），仅 Fix+Verify+Review 通过后另立 one-call continuation；⑤ file-declared / runtime env absent = conditional，非 secret 值有效性或生产授权；⑥ §8.1 新增 R1 developer Fix 交接 | YQuant-Principal |
| V0.1 | 2026-08-04 | 初始创建：P3-A Step-4 PR-0/PR-1/PR-2 受控只读 Gate 的可执行契约（allowlist、集合比对、预算、零写入、证据 schema、验收矩阵） | YQuant-Principal |
