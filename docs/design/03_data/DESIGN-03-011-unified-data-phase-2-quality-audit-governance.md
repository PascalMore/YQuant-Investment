# DESIGN-03-011：Unified Data Phase 2 — Query Audit 受控 rollout 与离线验证设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 已授权受控 rollout、尚未执行 |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-19 |
| 来源 RFC | RFC-03-011 (§6.4, §8.1~§8.6, §8.3a) |
| 来源 SPEC | SPEC-03-011 (§8~§13, §17) |
| 关联 Design | DESIGN-03-007（Unified Data Layer 详细设计） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer, YQuant-Reviewer-Principal |
| 版本号 | V1.0 |

---

## §1 设计概要

本 Design 覆盖 Phase 2 **Audit-only** rollout 的全部工程决策，共 8 部分：

| § | 主题 | 核心产出 |
|---|------|----------|
| §2 | 精确文件矩阵 | Implement/Verify/Review/Activation 各自可触碰的文件与禁止文件，避免并行写冲突 |
| §3 | DDL 状态机与退出码 | audit_rollout.py 的拒绝式 allow-list、防越界、dry-run/verify/apply 状态机与 exit-code 路径 |
| §4 | 凭证 preflight 与运行时注入边界 | 仅说明键存在性、gitignore/权限健康、不返回值；缺失时 fail-fast 与不连接边界 |
| §5 | collection/index expected state 与 role/user 检查 | DDL 返回值检查断言的范围和失败停止条件 |
| §6 | Smoke/Canary 数据模型与执行顺序 | 最小 smoke event / reader readback / 单次 canary 的数据模型和执行顺序；失败仅 `audit_logger=None`，不删记录、不自动重试 |
| §7 | 测试与验证矩阵 | fake/mongomock、本地 static scan、dry-run/越界拒绝、QualitySummary 不可达；明确哪些无法在离线阶段证明 |
| §8 | Production activation runbook | 按 preflight → apply → readonly verify → writer-reader smoke → canary → independent readonly acceptance 列出每步停止/回滚、审计证据和禁止动作 |

---

## §2 精确文件矩阵

本节明确定义 Implement → Verify → Review → Activation 各阶段可触碰的文件与禁止文件，避免 shared-file 并行写冲突。

### §2.1 文件分类规则

| 类别 | 前缀/范围 | 归属 |
|------|----------|------|
| 核心代码 | `skills/data/unified_data/`（不含 test 文件） | Implement 🛠 |
| 测试代码 | `skills/data/unified_data/tests/` | Implement 🛠 + Verify ✅ |
| 脚本 | `scripts/unified_data/` | Implement 🛠 |
| Design 文档 | `docs/design/03_data/` | Review 🔍 + Activation 🚀（只读引用） |
| 生产配置 | `.env`、`.env.local`、`~/.hermes/`、MongoDB | Activation 🚀 **仅** |

### §2.2 各角色文件矩阵

#### Implement（Developer-Engineer）

| 允许读写 | 允许只读 | 禁止 |
|---------|---------|------|
| `skills/data/unified_data/quality/scorer.py` | `docs/rfc/03_data/RFC-03-011*.md` | 生产 MongoDB（任何环境） |
| `skills/data/unified_data/quality/config.py` | `docs/spec/03_data/SPEC-03-011*.md` | 真实外部 provider token |
| `skills/data/unified_data/quality/__init__.py` | `docs/design/03_data/DESIGN-03-011*.md` | `.env` / `.env.local` / secrets |
| `skills/data/unified_data/quality/summary.py` | `skills/data/unified_data/models/__init__.py` | `scripts/unified_data/` 之外的生产脚本 |
| `skills/data/unified_data/audit/logger.py` | 现有 Phase 0/1A/1B 核心代码 | 越权集合引用 |
| `skills/data/unified_data/audit/__init__.py` | | |
| `skills/data/unified_data/registry.py`（priority/health 增强） | | |
| `skills/data/unified_data/router.py`（quality_scorer/audit_logger 注入） | | |
| `skills/data/unified_data/__init__.py`（新增导出） | | |
| `skills/data/unified_data/tests/test_quality_scorer.py` | | |
| `skills/data/unified_data/tests/test_quality_config.py` | | |
| `skills/data/unified_data/tests/test_audit_logger.py` | | |
| `skills/data/unified_data/tests/test_quality_summary.py` | | |
| `skills/data/unified_data/tests/test_registry_governance.py` | | |
| `skills/data/unified_data/tests/test_router_quality.py` | | |
| `skills/data/unified_data/tests/fixtures/quality_fixtures.py` | | |
| `skills/data/unified_data/tests/conftest.py`（可选 quality fixture） | | |
| `scripts/unified_data/audit_rollout.py`（已有，不变） | | |
| `scripts/unified_data/audit_smoke.py`（已有，不变） | | |

> **关键约束**：`audit_rollout.py` 和 `audit_smoke.py` 已是修复后的最终版本。Implement 阶段 **不得修改** 这两个脚本。任何 DDL/DB schema 冲突必须先 Design update 再重新 Implement。

#### Verify（Test-Engineer）

| 允许读写 | 允许只读 | 禁止 |
|---------|---------|------|
| `skills/data/unified_data/tests/test_*.py`（补充验证测试） | `scripts/unified_data/audit_rollout.py` | 生产 MongoDB |
| `skills/data/unified_data/tests/fixtures/*.py`（补充 fixture） | `scripts/unified_data/audit_smoke.py` | 真实外部 provider |
| `skills/data/unified_data/tests/conftest.py`（补充 conftest） | `skills/data/unified_data/audit/logger.py` | `.env` / secrets |
| | `skills/data/unified_data/quality/*.py` | |

#### Review（Reviewer-Principal）

| 允许读写 | 允许只读 | 禁止 |
|---------|---------|------|
| `docs/design/03_data/DESIGN-03-011*.md`（评审意见内联） | 全部实现源码和测试 | 生产 MongoDB |
| | `docs/rfc/03_data/RFC-03-011*.md` | 真实 credentials |
| | `docs/spec/03_data/SPEC-03-011*.md` | |

#### Activation（独立卡，Pascal 执行）

> **注意**：`audit_rollout.py` 的 `--apply` 与 `--verify` 互斥（代码层 `parser.error`），不得组合使用。三步必须严格按序执行：dry-run（默认无参数）→ `--apply`（DDL 写入）→ `--verify`（独立只读验证）。

| 允许操作（按序） | 禁止 |
|-----------------|------|
| Step A: `audit_rollout.py`（默认 dry-run，零副作用） | 复用业务身份 |
| Step B: `audit_rollout.py --apply`（DDL bootstrap） | 越界集合 DDL |
| Step C: `audit_rollout.py --verify`（独立只读验证，与 apply 不同步骤） | QualitySummary DDL |
| 设置环境变量 `YQUANT_UD_AUDIT_DDL_MONGO_*` | `--apply --verify` 组合使用（代码拒绝） |
| 执行 `audit_smoke.py --apply`（仅 Step 4 smoke） | 重新执行隐式测试文件 |
| 在 Router 代码中显式注入 `audit_logger=mongo_db` | rotate 非授权身份 |
| 手动 `db.command({"usersInfo": ...})` 只读验证 | 未经 dry-run 直接 `--apply` |

---

## §3 DDL 状态机与退出码

### §3.1 拒绝式 allow-list 模型

audit_rollout.py 采用 **拒绝式（fail-closed）** allow-list 而非自由模式。全部允许项编译为模块级常量：

| 常量 | 值 | 防越界机制 |
|------|-----|-----------|
| `ALLOWED_DATABASE` | `"tradingagents"` | 非此 DB 即 `ScopeViolation`（退出码 2） |
| `ALLOWED_COLLECTION` | `"03_data_ud_query_audit"` | 非此集合即 `ScopeViolation`（退出码 2） |
| `FORBIDDEN_COLLECTIONS` | `{"03_data_ud_quality_summary"}` | 目标在此集合 → `ScopeViolation`（退出码 2） |
| `ALLOWED_IDENTITY_NAMES` | 4 role/user 名称的 `frozenset` | 不在集合中 → `ScopeViolation`（退出码 2） |
| `INDEX_SPECS` | 3 条 `(name, keys, opts)` 元组 | 索引 key/option 不匹配 → `IdentityPrivilegeMismatch`（退出码 4） |
| `ALLOWED_PARAMS` | 11 键 `frozenset` | 白名单之外键丢弃 |
| `WRITER_ROLE_PRIVILEGES` | `[{resource: {db, collection: audit}, actions: ["insert"]}]` | 精确比对，不匹配退出码 4 |
| `READER_ROLE_PRIVILEGES` | `[{resource: {db, collection: audit}, actions: ["find"]}]` | 精确比对，不匹配退出码 4 |

### §3.2 防越界机制总览

| 层次 | 机制 | 违反后果 |
|------|------|---------|
| 模块加载 | 常量使用 `frozenset` 确保不可变 | N/A |
| 静态校验 | `_validate_targets()`：database/collection 不在 allow-list → `ScopeViolation` | 退出码 2，不创建 MongoDB 连接 |
| 身份校验 | `_validate_identity_name()`：不在 `ALLOWED_IDENTITY_NAMES` → `ScopeViolation` | 退出码 2 |
| Role 比对 | `_role_privileges_match()`：精确比对 privileges | 不一致 → `IdentityPrivilegeMismatch`（退出码 4） |
| User 比对 | `_existing_user_info()`：精确比对 role binding | 不一致 → `IdentityPrivilegeMismatch`（退出码 4） |
| Index 比对 | `_index_matches()`：精确比对 keys + options | 不一致 → `IdentityPrivilegeMismatch`（退出码 4） |
| QS 防御 | `--apply` 中显式检查 `03_data_ud_quality_summary` 不存在 | 存在 → `RolloutError`（退出码 4） |

### §3.3 三模式状态机

```
                          ┌─────────────┐
                          │   main()    │
                          └──────┬──────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
               --apply      --verify     (无参数)
                    │            │            │
                    ▼            ▼            ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │ run_apply│ │run_verify│ │dry_run   │
              └────┬─────┘ └────┬─────┘ └────┬─────┘
                   │            │            │
            ┌──────┴──────┐    │    ┌────────┴────────┐
            │ 连接 MongoDB│    │    │ 不连 MongoDB    │
            │ DDL bootstrap│    │    │ 不读凭证        │
            │ 身份        │    │    │ 打印执行计划     │
            └──────┬──────┘    │    │ 退出码 0        │
                   │           │    └─────────────────┘
            ┌──────┴──────┐    │
            │ Step 0-6     │    │
            │ 幂等创建/校验 │    │
            └──────┬──────┘    │
                   │           │
            ┌──────┴──────┐    │
            │ 退出码 0/4  │    │
            └──────┬──────┘    │
                   │           │
                   ▼           ▼
             成功/失败    只读验证
                          │
                   ┌──────┴──────┐
                   │ V1-V7 逐项  │
                   │ fail-fast   │
                   └──────┬──────┘
                          │
                   ┌──────┴──────┐
                   │ 退出码 0/1  │
                   └─────────────┘
```

### §3.4 退出码完整路径

| 退出码 | 含义 | 触发条件 | 路径 |
|--------|------|----------|------|
| 0 | 成功 | dry-run / --verify 全部通过 / --apply 全部成功 | 所有主路径 |
| 1 | 验证失败 | `--verify` 发现 collection/index/role/user 不符合契约或 QualitySummary 存在 | `run_verify()` |
| 2 | 范围校验失败 | `_validate_targets()` 拒绝、`_validate_identity_name()` 拒绝、argparse 未知参数 | 静态校验层 |
| 3 | 凭证缺失 | DDL bootstrap 凭证缺失、createUser 密码缺失 | `_load_ddl_credentials()` / `_preflight_runtime_users()` |
| 4 | 运行时错误 | pymongo 连接失败、role/index/user 不匹配、已存在身份有约束不一致、QS 集合存在、异常 | `run_apply()` / `run_verify()` |

### §3.5 幂等性与不删除语义

| 操作 | 幂等语义 |
|------|----------|
| `createCollection("03_data_ud_query_audit")` | 已存在静默跳过（MongoDB 原生幂等） |
| `createIndex(...)` | `_ensure_indexes`: 精确比对 → 匹配则 skipped，不匹配则 mismatched（退出码 4） |
| `createRole / createUser` | `_ensure_role` / `_ensure_user`: 已存在→精确比对 privileges/roles/binding；通过则 unchanged，不匹配退出码 4 |
| **删除** | **不存在删除路径**：不 drop collection、不 dropIndex、不 dropRole、不 dropUser、不 delete/remove 文档 |
| QualitySummary 检查 | `--apply` 检查 QS 集合若存在则退出码 4；非删除 QS 集合 |

**不删除原则**：DDL 工具永不做任何删除操作。回滚操作（如 dropRole / dropUser / dropCollection）仅在 Pascal 手动回滚场景通过 mongo shell 执行。

---

## §4 凭证 preflight 与运行时注入边界

### §4.1 凭证仅存在性校验的边界

DDL 工具中的凭证处理严格遵守 "只说明键存在性、gitignore/权限健康、不返回/不回显值" 原则：

| 函数 | 读取环境变量 | 验证方式 | 返回值 | 禁止行为 |
|------|-------------|----------|--------|---------|
| `_load_ddl_credentials()` | `YQUANT_UD_AUDIT_DDL_MONGO_URI/USERNAME/PASSWORD/AUTH_DB` | 空/缺失 → `MissingCredentialError` | `dict[str,str]` | 打印/日志/持久化/回显 |
| `_load_runtime_writer_credentials()` | `YQUANT_UD_AUDIT_WRITER_MONGO_*` | 同上 | `dict[str,str]` | 同上 |
| `_load_runtime_reader_credentials()` | `YQUANT_UD_AUDIT_READER_MONGO_*` | 同上 | `dict[str,str]` | 同上 |

**缺失时的 fail-fast 规则**：

| 场景 | 失败点 | 退出码 | 创建 MongoDB 连接？ |
|------|--------|--------|-------------------|
| DDL bootstrap 凭证缺失 | `_open_ddl_client()` → `_load_ddl_credentials()` | 3 | **不连接**（连 DDL bootstrap 连接也跳过） |
| CreateUser 密码缺失 + 用户不存在 | `_preflight_runtime_users()` → 检测密码 env 缺失 | 3 | 允许 DDL bootstrap 只读 `usersInfo` 连接，但**不发 createUser 写 DDL** |
| 用户已存在且无需密码 | `_existing_user_info()` → 通过 | N/A | 不读密码、不检查密码 env |

### §4.2 安全处理合约（已在脚本中实现）

```
1. pymongo str(exc) 不会进入日志/traceback：ServerSelectionTimeoutError /
   OperationFailure 默认把含 user:password 的完整 URI 嵌入 str(exc)

2. 转换规则：
   - _ensure_user 中 createUser 失败 → 仅输出 `type(exc).__name__`，del password 后抛异常
   - audit_smoke: _write_then_read 内 pymongo 触达点 → WriterRuntimeError /
     ReaderRuntimeError（消息固定，不含 secret）
   - run_apply 兜底 except Exception → 仅 `type(exc).__name__` + 固定短语

3. createUser 密码：仅在 _ensure_user 中的单条 db.command({"createUser": ...,
   "pwd": password}) 使用；执行后 del password，不被持久化、日志、异常链引用
```

### §4.3 凭证健康度的离线验证

离线阶段（实现/验证）验证凭证相关代码的正确性通过：

| 验证项 | 方法 | 离线可证明？ |
|--------|------|-------------|
| 缺失 DDL 凭证 → 退出码 3 | mock os.environ（del key）→ 断言退出码 | ✅ 完全可证明 |
| 缺失 runtime 密码 + 用户不存在 → 退出码 3 | mock `_existing_user_info` 返回 None + mock os.environ 缺失 → 断言退出码 | ✅ 完全可证明 |
| createUser 密码不出现在异常消息 | 检查 `_ensure_user` 中 `del password` 和 `error_type` 路径 | ✅ 静态分析可证明 |
| pymongo 异常翻译为固定消息 | 检查 audit_smoke `_write_then_read` 中的 try/except 覆盖 | ✅ 静态分析可证明 |
| **不能打印 URI/token/password** | `grep -r 'print.*password\|print.*URI\|print.*token'` | ✅ 静态扫描可证明 |
| **凭证实际可用性** | 无真实 MongoDB 环境 | ❌ 离线阶段无法证明；留 Activation 阶段的 smoke 验证 |

---

## §5 collection/index expected state 与 role/user 精确检查

### §5.1 collection 预期状态

| 属性 | 预期值 | 校验函数 | 失败行为 |
|------|--------|---------|---------|
| 集合名 | `03_data_ud_query_audit` | `_validate_targets()` + `db.list_collection_names()` | 不存在 → verify 退出码 1；apply 创建后仍不存在 → 退出码 4 |

### §5.2 3 个索引预期状态

| # | 索引名 | 键 | 选项 | 校验方式 | 失败行为 |
|---|--------|-----|------|---------|---------|
| I1 | `fetched_at_ttl` | `[("fetched_at", 1)]` | `{"expireAfterSeconds": 31536000}` | `_index_matches()` 比对 keys + options: expireAfterSeconds 精确等于 31536000 | mismatch → verify 退出码 1 / apply 退出码 4 |
| I2 | `security_id_fetched_at` | `[("security_id", 1), ("fetched_at", -1)]` | `{"name": "security_id_fetched_at"}` | 同上（expireAfterSeconds=None 且 actual 也必须无） | 同上 |
| I3 | `capability_fetched_at` | `[("capability", 1), ("fetched_at", -1)]` | `{"name": "capability_fetched_at"}` | 同上 | 同上 |

> **注意**：`_index_matches` 对 TTL 索引要求 `actual.get("expireAfterSeconds") == opts.get("expireAfterSeconds")`。非 TTL 索引 target_ttl=None，要求 actual 也无 expireAfterSeconds。

### §5.3 2 个 role 精确 privileges

#### Writer Role: `yquant_ud_audit_writer_role`

| 属性 | 预期值 |
|------|--------|
| Privileges | `[{"resource": {"db": "tradingagents", "collection": "03_data_ud_query_audit"}, "actions": ["insert"]}]` |
| Inherited Roles | `[]`（不继承任何 role） |
| 校验函数 | `_role_privileges_match()` + `_role_inherited_roles_match()` |
| 失败行为 | privileges 长度/资源/actions 任一不匹配 → `IdentityPrivilegeMismatch`（退出码 4）；inherited roles 不匹配 → 同上 |

#### Reader Role: `yquant_ud_audit_reader_role`

| 属性 | 预期值 |
|------|--------|
| Privileges | `[{"resource": {"db": "tradingagents", "collection": "03_data_ud_query_audit"}, "actions": ["find"]}]` |
| Inherited Roles | `[]` |
| 校验函数 | 同上 |
| 失败行为 | 同上 |

### §5.4 2 个 user 精确 role binding

| User | 预期 role binding |
|------|-------------------|
| `yquant_ud_audit_writer_user` | `[{"role": "yquant_ud_audit_writer_role", "db": "tradingagents"}]` |
| `yquant_ud_audit_reader_user` | `[{"role": "yquant_ud_audit_reader_role", "db": "tradingagents"}]` |

校验函数：`_existing_user_info()` → 比对 `sorted(actual_roles)` vs `sorted(expected_roles)`。不匹配 → `IdentityPrivilegeMismatch`（退出码 4）。

### §5.5 禁止复用 runtime identity 做 DDL 的检查

| 约束 | 实现方式 | 验证方式 |
|------|---------|---------|
| `run_apply` 必须使用 DDL bootstrap 身份 | `_open_ddl_client()` 读取 `YQUANT_UD_AUDIT_DDL_MONGO_*` | 代码检查：`_open_ddl_client` 不引用 writer/reader 环境变量 |
| `run_apply` 不得以 runtime writer/reader 身份连接 | 无代码路径加载 writer/reader env | 静态扫描确认 |
| AuditLogger 通过构造函数注入 mongo_db | 不自建 client/连接池 | 代码检查：logger.py 无 `pymongo.MongoClient()` 调用 |

---

## §6 Smoke/Canary 数据模型与执行顺序

### §6.1 Smoke event 精确 schema

字段严格限定于 `ALLOWED_EVENT_FIELDS = {"_id", "event_type", "source", "fetched_at"}`：

| 字段 | 类型 | 值 | 说明 |
|------|------|-----|------|
| `_id` | ObjectId | 自动生成（insert_one 返回） | MongoDB 主键 |
| `event_type` | string | `"audit_smoke_round_trip"` | 标识 smoke round-trip |
| `source` | string | `"audit_smoke_cli"` | 标识来源为 smoke CLI |
| `fetched_at` | datetime | UTC datetime（含 `timezone.utc` tzinfo） | 满足 TTL 索引 |

**字段约束**：
- 禁止包含 `params`、`account`、`security_id`、`market`、`capability`、`provider`、`consumer`、`audit_id`、`duration_ms`、`quality_score`、`quality_warnings` 等业务字段
- 禁止包含 secret/token/password/credential 字段
- `fetched_at` 必须是 UTC 含 tzinfo（`datetime.now(timezone.utc)`），不得使用 naive datetime

### §6.2 Smoke 执行顺序

```
1. _validate_targets(database, collection)    ← 静态校验
2. _build_smoke_event()                       ← 构造 event（仅含标识字段）
3. _validate_event_fields(event)              ← 字段白名单校验
4. writer_client (YQUANT_UD_AUDIT_WRITER_MONGO_*)
5. reader_client (YQUANT_UD_AUDIT_READER_MONGO_*)
6. writer_coll.insert_one(event)              ← writer 写入
7. reader_coll.find_one({"_id": inserted_id}) ← reader 读取
8. 验证 fetched_doc 的 event_type/source 与插入值一致
9. 验证 fetched_doc 字段严格限 ALLOWED_EVENT_FIELDS
10. 关闭 writer_client + reader_client
```

### §6.3 失败处理规则

| 失败阶段 | 后果 | 后续操作 |
|---------|------|---------|
| insert_one 失败 | WriterRuntimeError → 退出码 4 | 保留错误上下文；修复后重新 `--apply` |
| find_one 返回 None | SmokeError → 退出码 4 | 同上；排查 reader 身份权限 |
| 字段越界 | EventContractViolation → 退出码 4 | 修复 smoke 事件构造后重试 |
| 成功后 | 已写入的 smoke event **不删除** | 作为 audit trail 留存 |

### §6.4 Canary 数据模型

Canary 使用 **完整 AuditLogger**（含真实 MongoDB 写入）在 1-2 个低流量 capability 运行：

| 参数 | 值 |
|------|-----|
| 目标 capability | `metadata.*`（如 `metadata.stock_info`、`metadata.trade_calendar`） |
| AuditLogger | `mongo_db=pymongo.database.Database`（真实写入） |
| QualitySummary | `quality_summary=None`（Phase 1 冻结） |
| 观测期 | 24-48h |
| 失败处理 | 仅 `audit_logger=None`（回退到 noop），**不删除已写入记录**，**不自动重试** |

### §6.5 Canary pass/fail 逻辑

```
Canary 启动 →
  启用 1-2 capability 的 AuditLogger 真实写入 →
  持续 24-48h →
    检查 CV-01~CV-05 每 6h 一次 →
      全部通过 → 开放到全部 capability
      任一项触发 CV-05（无 QS 污染）→ 紧急停止
      CV-01/CV-02/CV-03 失败 → audit_logger=None 回退到 noop
      CV-04 触发（QS 存在）→ 紧急停止，报告 Pascal
```

---

## §7 测试与验证矩阵

### §7.1 质量组件测试矩阵

| # | 测试类 | 范围 | 用例数 | 离线可证明？ | 覆盖的契约 |
|---|--------|------|--------|-------------|-----------|
| TQ-1 | `test_quality_config.py` | QualityScorerConfig 默认值、域覆盖 | ≥ 5 | ✅ 纯计算 | §3.4 SPEC |
| TQ-2 | `test_quality_scorer.py` | 四维度评分、hard fail、等级映射 | ≥ 12 | ✅ 纯计算 | N1-N12（§3.5 SPEC） |
| TQ-3 | `test_audit_logger.py` | noop、mongomock、异常 catch-and-log、QS 防御断言 | ≥ 8 | ✅ mongomock | AL-101~105；QS-F2/F3 |
| TQ-4 | `test_quality_summary.py` | noop、upsert 幂等、get_summary | ≥ 5 | ✅ mongomock | QS-101~105 |
| TQ-5 | `test_registry_governance.py` | priority/health/unregister/clear | ≥ 10 | ✅ 纯内存 | R1-R9；P2-U1~U3 |
| TQ-6 | `test_router_quality.py` | 注入矩阵 DR-301~307 | ≥ 7 | ✅ mongomock | §5.3 SPEC |
| TQ-7 | `test_audit_rollout.py` | dry-run/verify/apply 模式、越界拒绝、幂等、QS 防御 | ≥ 15 | ✅ mongomock | §9 SPEC；A1-A10 |
| TQ-8 | `test_audit_smoke.py` | dry-run/apply、事件字段越界拒绝、凭证缺失、凭隔离 | ≥ 10 | ✅ mongomock | §10 SPEC |

### §7.2 QualitySummary 不可达性测试矩阵（SPEC §12.1）

| # | 测试 | 验证点 | 工具 | 离线可证明？ |
|---|------|--------|------|-------------|
| US-1 | AuditLogger 初始化 `quality_summary=None` | `AuditLogger.__init__` 时验证 `_quality_summary is None` | pytest + direct assert | ✅ |
| US-2 | AuditLogger.log() 关联 QS 防御 | mock QS 实例注入后 log() 抛 RuntimeError | pytest + mock | ✅ |
| US-3 | Router query 不触发 QS update | Router 含 AuditLogger 且 quality_summary=None | pytest + mongomock | ✅ |
| US-4 | audit_rollout --apply 拒绝 QS 存在 | mock collection 存在 → 退出码 4 | pytest + mongomock | ✅ |
| US-5 | audit_rollout --verify 检查 QS 不存在 | mock 不存在→0，存在→1 | pytest + mongomock | ✅ |
| US-6 | audit_smoke FORBIDDEN_COLLECTIONS 含 QS | `_validate_targets` 目标 == QS → ScopeViolation | pytest | ✅ |
| US-7 | 代码搜索审计：任何文件不含 QS 的 create/write 代码 | `grep -rn '03_data_ud_quality_summary' skills/data/unified_data/ --include='*.py' \| grep -v test_` | static scan | ✅ |

### §7.3 静态扫描矩阵（SPEC §12.2）

| # | 扫描项 | 命令 | 通过条件 | 离线可证明？ |
|---|--------|------|---------|-------------|
| SCAN-1 | 生产代码中 QS 字符串出现次数 | `grep -rn '03_data_ud_quality_summary' skills/data/unified_data/ --include='*.py' \| grep -v 'test_\|__pycache__\|\.pyc'` | 仅 QS schema 定义和禁止令注释；无 create/insert/update/upsert | ✅ |
| SCAN-2 | `createIndex`/`create_collection` 在 QS 上 | `grep -rn '03_data_ud_quality_summary' scripts/ --include='*.py'` + 检查上下文 | 0 处 | ✅ |
| SCAN-3 | 越权集合在 audit_rollout/smoke 中出现 | 检查 `scripts/unified_data/` 下文件引用 `portfolio_*`/`smart_money_*` 等 | 仅出现在 `FORBIDDEN_COLLECTIONS` 中 | ✅ |

### §7.4 离线阶段无法证明的事项

| # | 事项 | 原因 | 归属阶段 |
|---|------|------|---------|
| U-1 | DDL bootstrap 凭证在实际 MongoDB 上的可用性 | 没有真实 MongoDB 连接 | Activation §8.2 apply |
| U-2 | runtime writer/reader 身份的实际读写权限 | 同上 | Activation §8.3 smoke |
| U-3 | TTL 索引的实际过期行为 | expireAfterSeconds 是 MongoDB 服务端行为 | Activation §8.4 verify |
| U-4 | mongomock 与真实 MongoDB 的行为差异 | mongomock 不支持 TTL 索引/role/user 模拟 | Activation stage |
| U-5 | AuditLogger 写入延迟 p99 | 无生产负载 | Activation §8.5 canary |
| U-6 | 写入失败率 < 0.5% | 同上 | Activation §8.5 canary |

---

## §8 Production Activation Runbook

### §8.1 前置条件

> **注意**：以下前置条件是整个 Activation 的准入 Gate。Review PASS 与 Pascal 授权必须在 Step 1 (Preflight) 之前全部完成。§8.8 流程图将此 Gate 显式标注为"前置 Gate"。

- [ ] Review PASS（Reviewer-Principal 确认）— gating 整个 Activation 开始
- [ ] Pascal 显式授权执行 rollout（独立 Activation 卡）
- [ ] 所在机器可访问 MongoDB（`mongo --host <host> --port <port>` 连通）
- [ ] 准备好 3 组环境变量：DDL / writer / reader

### §8.2 Step 1: Preflight

```bash
# 检查远程 MongoDB 连通性（不暴露密码）
python -c "import pymongo; c=pymongo.MongoClient('<host>', serverSelectionTimeoutMS=5000); c.admin.command('ping'); c.close()"

# 确认无 QualitySummary 泄漏（使用 DDL bootstrap 只读连接）
python -c "
import pymongo, os
uri=os.environ['YQUANT_UD_AUDIT_DDL_MONGO_URI']
user=os.environ['YQUANT_UD_AUDIT_DDL_MONGO_USERNAME']
pw=os.environ['YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD']
c=pymongo.MongoClient(uri, username=user, password=pw, authSource='admin',
  serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
cols=c['tradingagents'].list_collection_names()
if '03_data_ud_quality_summary' in cols:
    print('⚠ QS collection exists! Investigate before proceeding.')
else:
    print('✅ No QS collection found. Safe to proceed.')
c.close()
"
```

| 停止条件 | 触发条件 | 应对 |
|---------|---------|------|
| SC-03 | QS 集合存在 | **紧急停止**，报告 Pascal；排查创建来源 |
| SC-04 | 凭据泄露 | 立即 rotate，重新从 DDL 开始 |
| 连通失败 | ping 超时/认证失败 | 排查网络/凭证后重试 |

### §8.3 Step 2: DDL Apply

```bash
export YQUANT_UD_AUDIT_DDL_MONGO_URI="..."
export YQUANT_UD_AUDIT_DDL_MONGO_USERNAME="..."
export YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD="..."
export YQUANT_UD_AUDIT_DDL_MONGO_AUTH_DB="admin"

# 首次 dry-run（零副作用）
python scripts/unified_data/audit_rollout.py

# Pascal 确认打印计划符合预期后执行
python scripts/unified_data/audit_rollout.py --apply
```

| 停止条件 | 退出码 | 应对 | 审计证据 |
|---------|--------|------|---------|
| SC-01 | 非 0 | 保留已创建工件，排查错误日志 | 终端输出 + 退出码 |
| SC-03 | --apply 内部 QS 防御触发（退出码 4） | **紧急停止** | 异常消息含 "QualitySummary collection must NOT exist" |
| SC-04 | 凭据泄露 | **紧急停止**，rotate 后重来 | — |
| ✅ 成功 | 0 | 继续下一步 | 输出含 indexes/roles/users 状态 |

**允许操作**：❌ 不允许在执行 `--apply` 时修改脚本或 CLI 参数
**回滚**：仅在确认全部失败后，手动通过 mongo shell 清理已创建工件：
```javascript
use tradingagents
db.dropUser("yquant_ud_audit_writer_user");
db.dropUser("yquant_ud_audit_reader_user");
db.dropRole("yquant_ud_audit_writer_role");
db.dropRole("yquant_ud_audit_reader_role");
db.03_data_ud_query_audit.drop();
```

### §8.4 Step 3: Readonly Verify

```bash
# 使用同一个 DDL bootstrap 身份只读验证
python scripts/unified_data/audit_rollout.py --verify
```

| 结果 | 含义 | 应对 |
|------|------|------|
| 退出码 0 | 全部 V1-V7 通过 | 继续下一步 |
| 退出码 1 | 任一项验证失败 | 排查输出问题项（索引、role、user 不匹配），修复后重新 `--verify` |
| 退出码 3 | DDL 凭证缺失 | 检查环境变量 |
| SC-03 | verify 报 QS 集合存在 | **紧急停止** |

### §8.5 Step 4: Writer-Reader Smoke

```bash
# 设置 runtime writer/reader 凭证（之前 DDL --apply 创建的用户）
export YQUANT_UD_AUDIT_WRITER_MONGO_URI="..."
export YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME="yquant_ud_audit_writer_user"
export YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD="..."
export YQUANT_UD_AUDIT_WRITER_MONGO_AUTH_DB="admin"

export YQUANT_UD_AUDIT_READER_MONGO_URI="..."
export YQUANT_UD_AUDIT_READER_MONGO_USERNAME="yquant_ud_audit_reader_user"
export YQUANT_UD_AUDIT_READER_MONGO_PASSWORD="..."
export YQUANT_UD_AUDIT_READER_MONGO_AUTH_DB="admin"

# dry-run
python scripts/unified_data/audit_smoke.py

# Pascal 确认后执行
python scripts/unified_data/audit_smoke.py --apply
```

| 停止条件 | 退出码 | 应对 | 审计证据 |
|---------|--------|------|---------|
| SC-02 | 非 0 | 保留已写入 smoke event；排查 writer/reader 身份权限故障 | 终端输出 |
| SC-04 | 凭据泄露 | **紧急停止** | — |
| ✅ 成功 | 0 | 输出含 inserted ObjectId | 终端输出 + 已写入 smoke event |

确认 writer→reader round-trip 通过后，手动验证：
```javascript
// 通过 mongo shell 以 DDL bootstrap 身份验证
use tradingagents
// 验证 smoke event 写入
db.03_data_ud_query_audit.findOne({"event_type": "audit_smoke_round_trip"})
// 验证无 QS 集合
db.03_data_ud_quality_summary.estimatedDocumentCount()
// 预期：MongoServerError: Collection [tradingagents.03_data_ud_quality_summary] not found.
```

### §8.6 Step 5: Canary（可选，先于全量 rollout）

**前提**：Smoke (Step 4) 通过

**执行步骤**：

1. 在产品代码中为 1-2 个低流量 capability（`metadata.*`）启用 AuditLogger 真实写入
2. 写入频率和字段符合 Design §5 schema
3. 观测 24-48h

| 金丝雀标准 | 阈值 | 检查方式 | 检查频率 | 失败处理 |
|-----------|------|---------|---------|---------|
| CV-01 写入成功率 | ≥ 99.5% | AuditLogger 内部失败计数器 | 每 6h | `audit_logger=None` 回退 noop |
| CV-02 p99 写入延迟 | ≤ 200ms | AuditLogger 内部计时 | 每 6h | 排查连接池/网络后重试 |
| CV-03 主查询无阻断 | 0 次 | DataRouter.query() catch 层 | 每 6h | `audit_logger=None` 回退 noop |
| CV-04 无 QS 污染 | 0 条 | `--verify` 或 mongo shell | 每 24h | **紧急停止**，报告 Pascal |
| CV-05 无越权操作 | 0 次 | 审计日志交叉验证 | 每 24h | **紧急停止** |

**失败时**：仅 `audit_logger=None`，**不删除已写入记录**，**不自动重试**。

### §8.7 Step 6: Post-Canary Readonly Acceptance（four-eye）

> **本节与 §8.1 的 Review PASS 无关**：Review PASS 是 gating 整个 Activation 开始的前置条件（在 Step 1 之前）。本节是 **Activation 内部**的 post-canary four-eye acceptance，仅 gating Step 7 全量 rollout，不 gating Step 2/4/5（它们已被 §8.1 前置 Gate 覆盖）。

由 Pascal 或独立 reviewer（与 §8.1 Review PASS 的 Reviewer-Principal 可为同一人）以 **纯 reader identity** 执行。本节契约：**不产生新 event、不执行任何 DDL/DML、不走 writer round-trip**。独立 reviewer 仅通过已存在的 DDL bootstrap 只读身份或 reader 身份验证既成状态。

| 验证项 | 身份 | 命令 | 本质 |
|--------|------|------|------|
| V-01 DDL 一致性重检 | DDL bootstrap 只读身份 | `python scripts/unified_data/audit_rollout.py --verify` | 与 Step 3 等价但由不同执行者独立复核 |
| V-02 读取一条 canary 期间写入的审计记录 | reader 身份 | `db.03_data_ud_query_audit.findOne({"event_type": "audit_smoke_round_trip"})` 或等价只读查询 | mongo shell 只读查询，**不使用 `audit_smoke.py` — 无写入** |
| V-03 QualitySummary 不存在 | DDL bootstrap 只读身份 | `db.03_data_ud_quality_summary.estimatedDocumentCount()` → 预期 `MongoServerError: Collection not found.` | mongo shell 只读，不存在即通过 |

> 所有验证命令均为只读：无 new event、无 DDL、无 DML、无 writer round-trip。V-02 使用 mongo shell 而非 `audit_smoke.py`，确保 reviewer 不意外触发写入。本节的独立 reviewer 与执行 Step 2/3/4 的 Pascal 应是不同身份（如 Reviewer-Principal），实现 **four-eye principle**。

### §8.8 Rollout 依赖关系

```
--- 前置 Gate（Activation 开始前必须完成） ---
Implement → offline Verify → Review PASS（Reviewer-Principal 确认）
  ↓ Pascal 显式授权（独立 Activation 卡）
--- Activation 执行流程（以下步骤在 Gate 通过后依次执行） ---
Step 1 Preflight
  ↓ 通过
Step 2 DDL Apply
  ↓ 退出码 0
Step 3 Readonly Verify
  ↓ 退出码 0
Step 4 Writer-Reader Smoke
  ↓ 退出码 0
Step 5 Canary (1-2 capability, 24-48h)
  │  ├─ CV-01~CV-05 全部通过 → Step 6
  │  └─ 任何 CV 失败 → audit_logger=None, 修复后重试
  ↓
Step 6 Post-Canary Readonly Acceptance（four-eye，仅 gate Step 7 全量 rollout）
  ↓ Pascal 确认
Step 7 全量 rollout (开放全部 capability)
```

> **Gate 语义总结**：Review PASS（§8.1 前置条件）gating **整个 Activation 的开始**，确保 Step 2（`--apply`）、Step 4（smoke `--apply`）、Step 5（canary）全部在独立审查之后运行。Step 6 的 four-eye acceptance 仅 gating Step 7 全量 rollout，不是 Step 2/4/5 的前置条件。

### §8.9 禁止操作清单

| 禁止操作 | 原因 | 替代方案 |
|---------|------|---------|
| 修改 `audit_rollout.py` / `audit_smoke.py` 实时执行 | 运行时修改引入安全风险 | 先 Design review → 再 Implement → 再 Activation |
| 复用业务数据库身份 | 安全边界破坏 | 使用 DDL bootstrap 身份 |
| 创建 QualitySummary 集合 | Phase 1 禁止 | Phase 1 禁用 |
| 使用 `--apply` 而不先 dry-run | 跳过确认 | 先 dry-run 打印计划 |
| 通过 pytest 直接运行生产 smoke | pytest 框架不处理真实凭证安全 | 使用 `audit_smoke.py --apply` |
| 删除已写入的 audit 记录 | append-only 契约 | 保留用于审计 |
| 向脚本/文档/输出中写入 URI/password | 硬性安全约束 | 仅通过环境变量传递 |

---

## 附录 A：Implement 阶段的实现对照表

| Design § | SPEC § | RFC § | 实现文件 | 是否已实现 | Design 新增决策 |
|----------|--------|-------|---------|-----------|---------------|
| §3.1 allow-list | §9.4 | §8.4.4~§8.5 | `audit_rollout.py` | ✅ 已实现 | 无新增 |
| §3.3 状态机 | §9.2 | §8.4.6 | `audit_rollout.py` | ✅ 已实现 | 无新增 |
| §3.4 退出码 | §9.1~§9.2 | §8.4.6 | `audit_rollout.py` | ✅ 已实现 | 无新增 |
| §4.1 凭证 preflight | §8.7, §10.5 | §8.4.3, §8.4.7 | `audit_rollout.py`, `audit_smoke.py` | ✅ 已实现 | 无新增 |
| §5 index/role/user 检查 | §9.2.2~§9.2.3 | §8.4 | `audit_rollout.py` | ✅ 已实现 | 无新增 |
| §6 smoke schema | §10.3 | §8.3a.4 | `audit_smoke.py` | ✅ 已实现 | 无新增 |
| §8 runbook | §16 | §8.6 | — | — | 本 Design **新增** production runbook |

**结论**：audit_rollout.py 和 audit_smoke.py 的代码实现（经 Remediation Implement 阶段修复后）与 Design §3-§6 的全部契约一致，无需额外代码修改。Implement 阶段的工作集中在 QualityScorer、AuditLogger、QualitySummary、Registry governance 和 Router 质量注入的代码与测试上。

## 附录 B：offline 无法证明项目汇总

| # | 事项 | 原因 | 验证归属 |
|---|------|------|---------|
| U-1 | DDL 凭证在实际 MongoDB 可用 | 无真实 MongoDB | Activation Step 2 |
| U-2 | Runtime writer/reader 实际读写权限 | 同上 | Activation Step 4 |
| U-3 | TTL 索引实际过期行为 | MongoDB 服务端行为 | Activation Step 3 verify |
| U-4 | mongomock 与 pymongo 行为差异 | mongomock 无 TTL/role/user 支持 | Activation stage |
| U-5 | AuditLogger 写入延迟 p99 ≤ 200ms | 无生产负载 | Activation Step 5 canary |
| U-6 | 写入成功率 ≥ 99.5% | 同上 | Activation Step 5 canary |
| U-7 | QualitySummary 不存在于 MongoDB | 离线验证基于假设 | Activation Step 1/3/6 |

---

## 附录 C：验收标准

| # | 验收项 | 验证方式 |
|---|--------|---------|
| A-01 | Design 包含可执行的文件矩阵（§2） | 视觉检查 |
| A-02 | Design 包含三模式状态机与退出码路径（§3） | 视觉检查 |
| A-03 | Design 包含凭证 preflight 边界与安全处理规则（§4） | 视觉检查 |
| A-04 | Design 包含 collection/index/role/user 精确 expected state（§5） | 与 SPEC §9.4 常量对比 |
| A-05 | Design 包含 smoke event schema 与执行顺序（§6） | 与 SPEC §10.3 对比 |
| A-06 | Design 包含完整测试矩阵与离线不可证明项清单（§7） | 视觉检查 |
| A-07 | Design 包含 production activation runbook（§8） | 视觉检查 |
| A-08 | Design 明确 Developer 无生产连接，Activation 是独立卡 | 视觉检查 |
| A-09 | Design 引用 RFC/SPEC 对应章节 | 交叉引用检查 |
| A-10 | `git diff --check -- docs/design/03_data/DESIGN-03-011*.md` 通过 | `git diff` 命令 |
