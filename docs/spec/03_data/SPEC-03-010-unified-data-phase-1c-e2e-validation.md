# SPEC-03-010: Unified Data Phase 1C — 端到端验收与测试收口

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-14 |
|| 最后更新 | 2026-07-15 |
|| 来源 RFC | RFC-03-010（Unified Data Phase 1C — 端到端验收与测试收口） |
|| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-008（Phase 1B-A 查询平面）、SPEC-03-009（Phase 1B-B 持久化缓存平面） |
|| 目标模块 | unified_data（`skills/data/unified_data/`） |
|| 版本号 | V0.2 |
| 适配 Agent | YQuant-Developer-Engineer (Implement), YQuant-Test-Engineer (Verify) |

---

## 1. 需求摘要

将 RFC-03-010 定义的 7 项端到端验收场景落为可执行、可断言的测试契约。核心交付：

1. **`test_e2e_full_chain.py`** — 7 个 TestClass，覆盖全部 7 项场景。使用 `pytest` + `mongomock` + `FakeProvider` + `FakeTA_CNAdapter`，零真实外部依赖。
2. **`test_models.py` bug fix** — 修复 `TestDataResultEmpty::test_dataframe_empty_attribute` 中空 DataFrame 场景的 `freshness` 断言（当前实际 `"delayed"`，契约期望 `"empty"`）。
3. **覆盖率门禁** — `coverage run && coverage report --fail-under=60` 可执行；若当前线覆盖率 < 60%，新增测试补齐至 ≥ 60%。
4. **Fixture 数据合理性** — 所有端到端 fixture 的 payload 包含非空、有业务意义的字段值，不空 payload 伪通过。

---

## 2. 范围

### 2.1 In Scope

- [ ] `tests/data/unified_data/test_e2e_full_chain.py` — 7 个 TestClass（每场景一个）。
- [ ] `tests/data/unified_data/test_models.py` — 修复 `test_dataframe_empty_attribute`。
- [ ] （如需要）`skills/data/unified_data/models/data_result.py` — 修复空 DataFrame 的 freshness 产生逻辑。
- [ ] 覆盖率报告运行 + 门禁校验。

### 2.2 Out of Scope

- [ ] ❌ 不新增 Provider / adapter / service / domain model。
- [ ] ❌ 不引入第三方依赖（coverage 已在项目 `.venv/bin/python -m coverage` 可用，不新增 pip 安装）。
- [ ] ❌ 不修改生产 Router / CacheManager / LocalMongoAdapter 行为（除 `test_dataframe_empty_attribute` 修复所需的 `DataResult.success` 工厂函数或 `freshness` 产生逻辑外）。
- [ ] ❌ 不新建 Mongo collection / index / schema。
- [ ] ❌ 不落地 `AuditLogger` / `QualityScorer` / `03_data_ud_query_audit`（Phase 2）。
- [ ] ❌ 不修改 TA-CN / DSA / Argus / portfolio / task_center 代码。
- [ ] ❌ 不修改 RFC/SPEC/Design 文档模板。
- [ ] ❌ 不触碰 cron / systemd / 生产 rollout。
- [ ] ❌ 不读取或输出任何凭据。

---

## 3. 功能规格

### 3.1 场景 1：全 miss → 外部成功 → 物化/Cache 写入 → 返回 → 再查询命中

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| E2E-101 | 全 miss + 外部成功 + 写入 | TA-CN 空；物化/Cache 空；tushare 注册且 payload 非空 | `provider="tushare"`，data 非空，trace 含 `ta_cn_internal(empty)` → `ud_materialized(miss)` → `cache(miss)` → `tushare(ok)` | — |
| E2E-102 | 写入验证（物化） | 同 E2E-101 查询后 | `LocalMongoAdapter.get(同 key)` 返回非空，`provider="ud_materialized"`，data 匹配 | — |
| E2E-103 | 写入验证（Cache） | 同 E2E-101 查询后 | `CacheManager.get(同 key)` 返回非空，`freshness="cached"`，原始 provider 保留 "tushare" | — |
| E2E-104 | 再查询命中物化 | 同 E2E-101 查询后再次 query 相同参数 | `provider="ud_materialized"`，外部 provider 调用数为 0 | — |

### 3.2 场景 2：Cache hit → 直接返回，外部调用为 0

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| E2E-201 | Cache miss at Step 2 + hit at Step 3 | TA-CN 空；物化层空；Cache 层预填充含有效未过期数据；tushare 注册 | `freshness="cached"`，provider 保留原始名，trace 含 `ta_cn_internal(empty)` → `ud_materialized(miss)` → `cache(ok)`，外部调用数 0 | 不包含 `cache(skipped:...)` 或 `cache(miss)` |

### 3.3 场景 3：Provider A 失败 → B 成功

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| E2E-301 | Fallback 有序 | TA-CN 空；tushare 注册 + `raise_on_fetch`；akshare 注册 + payload 非空 | `provider="akshare"`，trace 顺序 `tushare(error: ...)` → `akshare(ok)` | data 非空 |

### 3.4 场景 4：全失败 → DataResult.error（ta_cn_adapter=None 分支）

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| E2E-401 | 全部 provider 失败（ta_cn_adapter=None 分支） | **ta_cn_adapter=None**（无 TA-CN 层）；所有外部 provider `raise_on_fetch` | `DataResult(provider="error", freshness="empty")`，`"all external providers failed" in warnings` | **不抛** `AllProvidersFailedError`；调用方用 `assert result.provider == "error"` 而非 `try/except` |
| E2E-402 | trace 完整性（ta_cn_adapter=None 分支） | 同上 | trace 包含：`ud_materialized(miss)` → `cache(miss)` → `tushare(error: ...)` → `akshare(error: ...)` | **不含** `ta_cn_internal(empty)` 条目——Step 1 因 ta_cn_adapter=None 跳过 |

> **关键语义澄清**：`ta_cn_adapter=None` 下 Step 1 被跳过（trace 不产生 `ta_cn_internal(...)` 条目）。若 TA-CN adapter 覆盖该 capability 且返回空（empty_ta_cn 非 None），`router.py:308-311` 会在外部全失败时**返回保存的 empty DataResult（`provider="empty"`）**，而非 `provider="error"`。这一行为是 SPEC-03-008 §4.3 设计意图——当 TA-CN 有数据（即使空）时优先返回内部空结果，而不是外部失败。本场景（E2E-401/402）刻意使用 `ta_cn_adapter=None` 以验证 `provider="error"` 分支。TA-CN empty + 外部全失败 → `provider="empty"` 的独立行为验证由 E2E-403 覆盖。**本阶段不修改生产 Router（L308-311）**。

### 3.5 场景 5：force_refresh=True

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| E2E-501 | force_refresh 两条 skipped + 外部 fetch | TA-CN adapter 有数据可命中（但 Step 1 被 force_refresh 守卫跳过）；物化和 Cache 预填充；tushare 注册；`force_refresh=True` | trace 含 `ud_materialized(skipped: force_refresh)` → `cache(skipped: force_refresh)` → `tushare(ok)`（不含 `ta_cn_internal(skipped: force_refresh)`） | TA-CN adapter 未被调用；物化/Cache get() 未被调用 |
| E2E-502 | force_refresh 后写入验证 | 同 E2E-501 查询后 | 物化层和 Cache 层被更新为新数据 | — |
| E2E-503 | force_refresh 后再次查询无 force_refresh 命中 | 同 E2E-501 查询后，再次 `force_refresh=False` | 物化 hit → `provider="ud_materialized"`，外部调用 0 | 证明 force_refresh 后的写入对后续查询生效 |

### 3.6 场景 6：index 双路径

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| E2E-601 | index_basic_info 内部命中 | TA-CN adapter 含 index_basic_info 数据 | `provider="ta_cn_internal"`，外部 provider 调用为 0 | — |
| E2E-602 | index_basic_info 外部兜底 | TA-CN adapter 空；tushare 注册 + index_list payload | `provider="tushare"`，data 非空 | — |
| E2E-603 | index_daily_quotes 内部命中 | TA-CN adapter 含 index_daily_quotes 数据 | `provider="ta_cn_internal"` | — |
| E2E-604 | index_daily_quotes 外部兜底 | TA-CN adapter 空；tushare 注册 + index_daily payload | `provider="tushare"` | — |

**注意**：`stock_sector_info` 因缺少 canonical Router capability 与已验证的 external fallback，不在 Phase 1C Router E2E 范围内（仍由 Phase 1A `SectorService` + TA-CN adapter direct read 覆盖）。其未来 Router 统一入口与 external fallback 需另开独立阶段，先做公共 capability 设计、查询粒度、分类体系与 Provider 等价性验证后再实施（具体阶段编号不预设）。

### 3.7 场景 7：覆盖率门禁

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
|| E2E-701 | 覆盖率报告运行 | `cd /proj && python -m coverage run -m pytest tests/data/unified_data/ && coverage report --include="skills/data/unified_data/*"` | exit 0，输出线覆盖率和分支覆盖率 | 若 coverage 命令不可用，视为验证失败（不允许 `pip install coverage`） |
| E2E-702 | 线覆盖率 ≥ 60%（硬门禁） | `python -m coverage report --fail-under=60 --include="skills/data/unified_data/*"` | exit 0 | exit 非零 = 失败，阻塞 1C Closeout |

---

## 4. 数据与接口契约

### 4.1 测试文件矩阵

| 文件 | 操作 | 预计新增行 | 依赖文件 |
|---|---|---|---|
| `tests/data/unified_data/test_e2e_full_chain.py` | **新建** | 300-500 | conftest.py（FakeProvider / FakeTA_CNAdapter / fixtures） |
| `tests/data/unified_data/test_models.py` | **修改**（修复 1 个测试） | 2-5 | — |
| `skills/data/unified_data/models/data_result.py` | **可能修改**（修复 empty freshness） | 1-10 | — |

### 4.2 导入路径与测试常量

```python
from skills.data.unified_data import (
    CacheManager,
    DataResult,
    DataRouter,
    LocalMongoAdapter,
    Market,
    ProviderError,
    ProviderRegistry,
    SecurityId,
)
from tests.data.unified_data.conftest import FakeProvider, FakeTA_CNAdapter
```

共享常量（放在文件级）：

```python
KLINE_CAP = "market_data.kline_daily"
INDEX_LIST_CAP = "metadata.index_list"
INDEX_DAILY_CAP = "market_data.index_daily"
# 注意：stock_sector_info 因缺少 canonical Router capability 与已验证的 external fallback，
# 不在 Phase 1C Router E2E 范围内（仍由 Phase 1A SectorService + TA-CN adapter direct read 覆盖）。
# 无 SECTOR_CAP 常量——不强制用 metadata.stock_list 冒充 sector capability。
```

### 4.3 Fixture 设计

| fixture | 作用域 | 说明 |
|---|---|---|
| `e2e_ta_cn_empty` | function | `FakeTA_CNAdapter(collections={})` — 所有集合空，返回 empty |
| `e2e_ta_cn_with_index` | function | `FakeTA_CNAdapter(collections={"index_basic_info": [...], "index_daily_quotes": [...]})` |
| `e2e_db` | function | 独立 `mongomock.MongoClient().get_database("tradingagents")` |
| `e2e_build_router` | function | 接收 registry / db / with_local_mongo / with_cache / ta_cn_adapter 等参数，返回 DataRouter 实例 |

### 4.4 错误语义（SPEC-03-010 与 SPEC-03-009 §4.5 保持一致）

| 场景 | DataResult.provider | DataResult.freshness | DataResult.source_trace | DataResult.warnings | 物化/Cache 写入 |
|---|---|---|---|---|---|
| 全 miss + 外部成功（场景 1） | `"tushare"` | `label(...)` | `[ta_cn_internal(empty), ud_materialized(miss), cache(miss), tushare(ok)]` | `[]` | ✅ |
| Cache hit（场景 2） | 原始 provider | `"cached"` | `[ta_cn_internal(empty), ud_materialized(miss), cache(ok)]` | `[]` | 不写入 |
| Fallback 成功（场景 3） | `"akshare"` | `label(...)` | `[ta_cn_internal(empty), ud_materialized(miss), cache(miss), tushare(error: ...), akshare(ok)]` | `[]` | ✅ |
| 全失败（场景 4） | "error" | "empty" | [ud_materialized(miss), cache(miss), tushare(error: ...), akshare(error: ...)]（注：ta_cn_adapter=None 下 Step 1 跳过，无 ta_cn_internal 条目） | ["all external providers failed"] | 不写入 |
| force_refresh（场景 5） | `"tushare"` | `label(...)` | `[ud_materialized(skipped: force_refresh), cache(skipped: force_refresh), tushare(ok)]` | `[]` | ✅ |

### 4.5 向后兼容

- 端到端测试**不修改**现有测试文件中的 fixture 定义（conftest.py 的 `FakeProvider` 和 `FakeTA_CNAdapter` 保持不变）。
- 若修复 `test_dataframe_empty_attribute` 涉及修改 `DataResult.success()` 工厂函数签名，不得破坏已有调用方。

### 4.6 幂等性要求

- 每个端到端 TestClass 可独立运行（`pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2ESceneN -q` 应通过）。
- 运行的先后顺序不影响其他 TestClass 的结果。

---

## 4.bis 持久化契约

无持久化需求。所有测试数据在 mongomock 内存中创建和销毁，不落盘、不连接生产 Mongo、不创建 collection/index/validator。

---

## 5. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | test_e2e_full_chain.py 文件存在 | `ls -la tests/data/unified_data/test_e2e_full_chain.py` |
| A-002 | 7 个 TestClass 各包含至少 1 个断言方法 | `grep -c "class TestE2E" tests/data/unified_data/test_e2e_full_chain.py` == 7 |
| A-003 | 场景 1 全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene1_AllMissExternalSuccess -q --tb=short` exit 0 |
| A-004 | 场景 2 全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene2_CacheHit -q --tb=short` exit 0 |
| A-005 | 场景 3 全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene3_ProviderFallback -q --tb=short` exit 0 |
| A-006 | 场景 4 全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene4_AllFail -q --tb=short` exit 0 |
| A-007 | 场景 5 全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene5_ForceRefresh -q --tb=short` exit 0 |
| A-008 | 场景 6 全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene6_IndexDualPath -q --tb=short` exit 0 |
| A-009 | 场景 7 至少可运行覆盖率报告 | `coverage run -m pytest tests/data/unified_data/test_e2e_full_chain.py -q && coverage report --include="skills/data/unified_data/*"` exit 0 |
| A-010 | test_dataframe_empty_attribute 修复，全量 358+ 测试通过 | `pytest tests/data/unified_data -q --tb=long` exit 0，无 FAILED |
| A-011 | git diff --check 无空白错误 | `git diff --check` exit 0 |

---

## 6. 测试要求

### 6.1 单元测试

场景 1-6 各自对应一个 TestClass，每个 TestClass 包含断言其场景所有分叉的测试方法。完整的测试方法清单（含 assertion style 注释）：

| 场景 | TestClass | 测试方法 | 数量 | Assertion Style |
|---|---|---|---|---|
| 1 | `TestE2EScene1_AllMissExternalSuccess` | `test_returns_external_data`, `test_materialized_written`, `test_cache_written`, `test_subsequent_hit_materialized` | 4 | exact trace (`==`), exact data, provider call count |
| 2 | `TestE2EScene2_CacheHit` | `test_cache_hit_zero_external` | 1 | exact freshness/provider/data, `call_log == []` |
| 3 | `TestE2EScene3_ProviderFallback` | `test_fallback_ordered` | 1 | **精确 source_trace**（`==` 完整列表），provider call count 顺序断言 |
| 4 | `TestE2EScene4_AllFail` | `test_returns_error_result`, `test_trace_completeness` | 2 | **精确 trace**（不含 `ta_cn_internal`），error/freshness/warnings 精确断言，调用方不捕获异常 |
| 5 | `TestE2EScene5_ForceRefresh` | `test_skipped_trace`, `test_write_unchanged`, `test_subsequent_hit` | 3 | **精确 trace**（两条 skipped + external ok），TA-CN call_log 空，物化/Cache get() 计数可断言（须通过 spy 或 trace 间接验证），子查询无外部调用 |
| 6 | `TestE2EScene6_IndexDualPath` | `test_index_list_internal`, `test_index_list_external`, `test_index_daily_internal`, `test_index_daily_external` | 4 | **外部兜底方法必须断言业务字段**（symbol/name/sector_code/close 非空且合理），不只是 `is not None` |
| 7 | `TestE2EScene7_CoverageGate` | `test_coverage_report_runs` | 1 | subprocess exit 0，TOTAL 行存在 |

总计：16 个测试方法。

#### 6.1.1 精确断言规范（T3 Remediation 必须落实）

以下为 T5 Review 确认当前实现中**断言不足**的关键路径，T3 Remediation 必须改为精确断言：

**场景 3（E2E-301）：`test_fallback_ordered`**
- ❌ 当前：`any("tushare(error:" in entry ...)` + `"akshare(ok)" in result.source_trace`
- ✅ 预期：`result.source_trace == ["ta_cn_internal(empty)", "ud_materialized(miss)", "cache(miss)", "tushare(error: tushare rate limit)", "akshare(ok)"]`
- ✅ 附加：`e2e_registry.get("tushare").call_log` 长度为 1（tushare 确实被调用过一次后失败）

**场景 4（E2E-402）：`test_trace_completeness`**
- ✅ 当前已使用精确 trace 顺序断言（index ordering），但 trace 条目不含 `ta_cn_internal(empty)`（已确认正确行为见 §3.4）

**场景 5（E2E-501）：`test_skipped_trace`**
- ❌ 当前：`"ud_materialized(skipped: force_refresh)" in result.source_trace` + `"cache(skipped: force_refresh)" in result.source_trace`
- ✅ 预期：`result.source_trace == ["ud_materialized(skipped: force_refresh)", "cache(skipped: force_refresh)", "tushare(ok)"]`
- ✅ 附加：TA-CN adapter `call_log == []` ✅ 已有。**物化.get() 和 Cache.get() 调用计数**：当前测试不直接计数（因 `_try_materialized` / `_try_cache` 的 force_refresh 守卫在函数内部，外部无法直接 spy）。T3 可通过验证 trace **不含** `ud_materialized(ok)` / `ud_materialized(miss)` （证明 get() 未返回有效结果也未返回 miss）来间接证明 get() 未被调用。若 Router 提供 call counter 或日志钩子，优先使用。

**场景 5（E2E-502）：`test_write_unchanged`**
- ✅ 当前：`local.get()` 和 `cache.get()` 后断言 `is not None` + `data == expected_payload` ✅ 充分

**场景 6（E2E-602/604）：`test_index_list_external` / `test_index_daily_external`**
- ❌ 当前：仅 `assert result.data is not None`，空列表可伪绿
- ✅ 预期（index_list_external）：`assert result.provider == "tushare"` + `assert len(result.data) >= 1` + 首位元素 `result.data[0].get("symbol") == "000300"` + `result.data[0].get("name") == "沪深300"` 或类似的业务字段最小断言
- ✅ 预期（index_daily_external）：`assert result.provider == "tushare"` + `assert len(result.data) >= 1` + 首位元素 `result.data[0].get("sector_code") == "000300"` + `result.data[0].get("close") > 0`

### 6.2 集成测试

无新增集成测试（已有的 IT-PR-001~004 在 test_router_persistence.py 中）。端到端测试本身是集成性质（全链路），但归入 `test_e2e_full_chain.py` 作为独立类别。

### 6.3 回归测试

- 修改 `test_models.py` 或 `models/data_result.py` 后，运行 `pytest tests/data/unified_data -q --tb=long` 确认无回归。
- 不修改 Router / CacheManager / LocalMongoAdapter 代码，因此不需要对这些模块的回归测试。

### 6.4 不可自动化验证项

| 项 | 原因 | 替代方案 |
|---|---|---|
| index 的 fixture 数据合理性（是否带业务意义的字段值） | 需人工判断"有意义"的定义 | T2 Design 阶段人工审核 fixture payload |

---

## 7. 实现约束

### 7.1 禁止事项（不改动清单）

| 路径 | 理由 |
|---|---|
| `skills/apps/TradingAgents-CN/**` | TA-CN 子项目，只读复用 |
| `skills/research/daily_stock_analysis/**` | DSA 独立子系统 |
| `skills/data/data-pipeline/**` | ETL 管道，职责正交 |
| `skills/data/data_interface/**` | RFC-03-003 IReader/IWriter |
| `skills/infra/task_center/**` | 任务中心 |
| `skills/data/unified_data/router.py`（除非 bug） | 路由逻辑成熟，不可随意修改 |
| `skills/data/unified_data/cache_manager.py` | 缓存逻辑成熟 |
| `skills/data/unified_data/local_mongo_adapter.py` | 物化逻辑成熟 |
| 生产 MongoDB 集合的 schema validator / DDL / 索引 | 零 DDL 研发阶段 |
| cron / systemd / gateway / 外部推送配置 | 不碰调度和推送 |

### 7.2 依赖限制

- 不新增 pip 依赖。`mongomock`、`pytest` 已是项目测试依赖。
- `python -m coverage` 已在项目 `.venv` 中可用（7.15.1），不允许 `pip install coverage`。不可用时视为验证失败。

### 7.3 性能约束

- 全部 16 个端到端测试方法合计应在 10 秒内完成（mongomock + fake provider 在内存中运行，无 I/O 等待）。

### 7.4 语言约束

- 测试方法名用英文（遵循现有测试风格），文档字符串用英文，注释可用中文辅助。
- git commit message 用中文。

---

## 8. 开放问题（全部已关闭）

| # | 问题 | 影响 | 处理结果 |
|---|---|---|---|
| OQ-01 | `stock_sector_info` 在 `_TA_CN_CAPABILITY_METHOD_MAP` 无独立 capability 映射 | 场景 6 不覆盖 sector | ✅ **已关闭**：Pascal 确认 Path A——`stock_sector_info` 不在 1C Router E2E 范围，未来另开独立阶段。 |
| OQ-02 | `coverage` CLI 是否可用？ | 影响场景 7 验收 | ✅ **已关闭**：`.venv/bin/python -m coverage` 可用（7.15.1），实测 358 passed / 88%。不允许 `pip install coverage`。 |
| OQ-03 | `test_dataframe_empty_attribute` 的契约语义 | 影响 Phase 0 工厂行为 | ✅ **已关闭**：实测已验证通过（freshness="empty"），无需代码改动。 |

---

## 附录 A：验证命令速查

```bash
# 1. 全部 unified_data 测试
pytest tests/data/unified_data -q --tb=short      # 期望：全 PASS（357+16=373+）

# 2. 端到端测试独立运行
pytest tests/data/unified_data/test_e2e_full_chain.py -q --tb=short

# 3. 覆盖率报告
cd /home/pascal/workspace/yquant-investment
coverage run -m pytest tests/data/unified_data -q
coverage report --include="skills/data/unified_data/*"
coverage report --fail-under=60 --include="skills/data/unified_data/*"

# 4. 空白检查
git diff --check

# 5. 文件存在性
ls -la tests/data/unified_data/test_e2e_full_chain.py

# 6. TestClass 数量
grep -c "class TestE2E" tests/data/unified_data/test_e2e_full_chain.py    # 期望：7
```

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
|| V0.3 | 2026-07-15 | T2.6 Review Remediation：① all-fail 语义收敛（Scene 4 precondition clarified, trace 修正）；② 精确断言规范 §6.1.1；③ 测试节点/方法名飘移修正；④ 文件拆分方案（Design §3.9）。 | YQuant-Principal |
|| V0.2 | 2026-07-15 | T2.5 Sector 边界收敛 Amendment：场景 6 改名为 `TestE2EScene6_IndexDualPath`（去 sector 引用）；`stock_sector_info` 说明同步；coverage 门禁强化。 | YQuant-Principal |
| V0.1 | 2026-07-14 | 初始创建，基于 RFC-03-010 V0.1 | YQuant-Principal |
