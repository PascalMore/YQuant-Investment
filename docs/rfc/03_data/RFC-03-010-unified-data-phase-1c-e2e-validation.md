# RFC-03-010：Unified Data Phase 1C — 端到端验收与测试收口

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-14 |
| 最后更新 | 2026-07-15 |
| 版本号 | V0.2 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-008（Phase 1B-A 查询平面）、RFC-03-009（Phase 1B-B 持久化缓存平面） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-008（Phase 1B-A 查询平面）、SPEC-03-009（Phase 1B-B 持久化缓存平面） |
| 关联 Design | DESIGN-03-007（Unified Data Layer 总设计）、DESIGN-03-008（Phase 1B-A 查询平面设计）、DESIGN-03-009（Phase 1B-B 持久化缓存平面设计） |
| 替代 RFC | 无（1C 是验证/测试层，不替代任何 RFC） |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #e2e #test #phase1c #validation |

### 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.2 | 2026-07-15 | T2.5 Sector 边界收敛 Amendment：① `stock_sector_info` 移出 1C Router E2E 范围（Pascal 确认 Path A）；② force_refresh trace 修正——两条 `(skipped: force_refresh)`（不含 `ta_cn_internal` 条目）；③ coverage ≥ 60% 提升为硬门禁（阻塞 Closeout）；④ 删除 `pip install coverage` 指令（已安装 7.15.1）；⑤ OQ-01~OQ-04 全部关闭。 | YQuant-Principal |

---

## 1. 执行摘要

Phase 1C 是 Unified Data Layer 1A → 1B-A → 1B-B 完成后的**证据/验收层**，不是新数据能力层。它不新增 Provider、不引入第三方依赖、不修改生产 Router/Provider 行为、不新建 Mongo collection/index/schema。核心交付是：

1. **7 项端到端集成测试**覆盖完整的四步 internal-first 路径（TA-CN → UD 物化 → Query Cache → 外部 Provider）的所有分叉：全部命中、缓存命中零外部调用、fallback 成功、全失败返回 DataResult.error、force_refresh 透传、index 双路径（含 Router 端到端 fallback）、覆盖率门禁 ≥ 60%。
2. **行为缺口补丁**：检查 1B-A / 1B-B 测试中缺失的行为维度（数据合理性、fixture 最小确保、fallback 结果来源可区分），写入可执行的测试矩阵。
3. **覆盖率量化**：明确统计命令、覆盖对象、阈值失败语义；若整体覆盖率已高于 60%，明确 1C 新增哪些「行为缺口」测试而非盲目补行覆盖率。
4. **现有 bug 修复**：test_models.py 中 1 个 DataResult empty freshness 断言失败（预期 "empty"，实际 "delayed"）需要在 1C 中修复。

Phase 1C 全部测试在 pytest + fake provider + mongomock 沙箱中运行，不发起真实外部 API 或真实 Mongo 访问。产出物仅为 `tests/data/unified_data/` 下的新增/修改测试文件。

---

## 2. 背景与动机

### 2.1 现状：已完成三层基础

| 阶段 | 交付物 | 测试规模 | 状态 |
|---|---|---|---|
| Phase 0 | 骨架（SecurityId / DataResult / DataProvider / Registry / Router / Client / Config / Exceptions） | 269 passed | ✅ |
| Phase 1A | TA-CN MongoDB 只读适配器（8 集合 + 11 读方法）+ canonical objects + services + client facade | 269 passed（含 Phase 0） | ✅ |
| Phase 1B-A | internal-first 路由编排（DataRouter Step 1 + Step 4，slot 预留） | 313 passed（增量 ~44 tests） | ✅ |
| Phase 1B-B | LocalMongoAdapter + CacheManager + DataRouter Step 2/3 激活 | 357 passed（增量 ~44 tests） | ✅ |

当前测试套件 357 passed、1 failed。失败原因：`test_models.py::TestDataResultEmpty::test_dataframe_empty_attribute` 中 `DataResult.success` 创建空 DataFrame 时实际 freshness 为 `"delayed"`（Phase 0 默认）而非预期的 `"empty"`，表明 Phase 0 的 `success()` 工厂函数在空 payload 场景未执行自动降级到 `freshness="empty"`，或 `EmptyDataFrame` 检测逻辑不匹配。

### 2.2 动机：从「每段跑通」到「整链可信」

1A/1B-A/1B-B 的测试是**组件级或子阶段级**的——每个组件在自己的沙箱中跑通，但从未作为一个完整链路（1A adapter + 1B-B materialize + 1B-B cache + 1B-A external fallback）一起运行过。以下风险未覆盖：

- **四步组合路径**：TA-CN miss → 物化过期 → Cache miss → 外部 fallback 成功 → 写入 → 下一查询命中物化？当前无端到端验证。
- **fallback 来源可区分**：Cache hit 返回的 `provider` 是否保留了原始 provider 名（如 "tushare"）？物化 hit 是否改为 "ud_materialized"？当前没有测试同时断言三个 Step 的结果来源语义。
- **index 双路径**：`index_basic_info` / `index_daily_quotes` 在 Phase 1A adapter 层已有测试，但在 Router 编排层（adapter + provider fallback combo）没有覆盖。`stock_sector_info` 因缺少 canonical Router capability 与已验证的 external fallback，不在 1C Router E2E 范围内（仍由 Phase 1A `SectorService` + adapter direct read 覆盖）。
- **数据合理性**：fixture 可能以空 payload 伪通过——例如 `LocalMongoAdapter.put()` 写入空 data 后再 get 返回空 data，不检查 data 是否真正包含业务上有意义的字段。
- **覆盖率未量化**：从未跑过覆盖率报告，无法知道当前线覆盖率和分支覆盖率。DESIGN-03-007 §Phase 1C 验收标准要求 "≥ 60%"但无量化依据。
- **force_refresh 约定**：1B-B 已实现 force_refresh 跳过 Step 2/3 + 写入不变的契约，但 End-to-End 端将整个链路（含 TA-CN adapter 行为）一起验证的测试缺失。

### 2.3 业务价值

- **防止回归**：后续 Phase 2（Audit/Quality）改动时，端到端测试能立即发现 Router 编排逻辑破坏。
- **验收凭据**：1A/1B/1C 全部跑通后，unified_data 内核可以标记为「生产可部署」（仅缺 Mongo DDL 审批和 Task Center 集成）。
- **对接信心**：消费方（stock framework、Argus、portfolio）可以基于已验证的 API 行为做集成。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 7 项端到端集成测试覆盖完整四步 internal-first 路径的全部关键分叉（§4.2 场景 1-7）。
- [ ] 现有 1 个 failed test（test_dataframe_empty_attribute）修复。
- [ ] 覆盖率报告可运行且量化；若整体线覆盖率 < 60%，新增测试补齐到 ≥ 60%。
- [ ] index_basic_info / index_daily_quotes 在 Router 编排层的双路径覆盖（TA-CN adapter 内部命中 + provider fallback 兜底）。`stock_sector_info` 因缺少 canonical Router capability 与已验证的 external fallback，不在 1C Router E2E 范围内（仍由 Phase 1A `SectorService` + TA-CN adapter direct read 覆盖）；其未来 Router 统一入口与 external fallback 需另开独立阶段。
- [ ] fixture 数据合理性断言：所有 e2e fixture 填充的 payload 包含业务可理解的字段值，不空数通过。
- [ ] 全部测试在 pytest + mongomock + fake provider 沙箱中运行，零真实外部调用。
- [ ] `force_refresh=True` 路径被端到端覆盖：force_refresh 跳过 Step 1（TA-CN adapter 未被调用）+ Step 2/3（物化/Cache 不被调用）→ 两跳 `(skipped: force_refresh)` trace → 外部 fetch → 写入不变。
- [ ] 全失败路径符合 SPEC-03-009 §4.5 契约：返回 `DataResult.error(provider="error", source_trace=[...])`，不抛 `AllProvidersFailedError`。

### 3.2 非目标（Out of Scope）

- [ ] ❌ 不新增 Provider / adapter / service / domain model。
- [ ] ❌ 不引入第三方依赖（coverage 报告工具已在项目 `.venv/bin/python -m coverage` 可用，版本 7.15.1，不新增 pip 安装）。
- [ ] ❌ 不修改生产 Router / Provider / CacheManager / LocalMongoAdapter 行为（除非后续测试暴露可复现 bug，届时走范围裁决；本 RFC 已预知的 `test_dataframe_empty_attribute` 修复属于 bug fix，允许改 production 代码使空 payload 场景 freshness 正确）。
- [ ] ❌ 不新建 Mongo collection / index / schema，不落地 `AuditLogger` / `QualityScorer` / `03_data_ud_query_audit`（均属 Phase 2）。
- [ ] ❌ 不触碰 Task Center、DSA adapter、TA-CN 写回、cron/systemd、生产 rollout。
- [ ] ❌ 不修改 RFC/SPEC/Design 模板。
- [ ] ❌ 不读取或输出任何凭据。
- [ ] ❌ 不补 Phase 1B-B 已有的 test_router_persistence.py 子集测试（Phase 1C 的端到端场景和已有子集测试是互补而非替代关系——端到端测全链，子集测试只测自己负责的 Step）。

---

## 4. 整体设计

### 4.1 核心设计哲学

Phase 1C 是**证据层**（Validation Layer）——它证明前三个子阶段的组合行为符合契约，而不是增加新能力。7 项端到端场景对应的「契约断言」来自 SPEC-03-007/008/009 和 DESIGN-03-007/008/009 已达成共识的 4.5 错误/降级矩阵。

### 4.2 七项端到端场景

#### 场景 1：全 miss → 外部成功 → 物化/Cache 写入 → 返回

**前置**：TA-CN adapter 对该 capability 返回空/覆盖无数据；物化层无数据；Cache 层无数据。外部 tushare provider 注册并返回有效 payload。

**断言**：
1. `DataResult.provider == "tushare"`
2. `result.data` 非空，来自外部
3. `source_trace` 包含 `ta_cn_internal(empty)` → `ud_materialized(miss)` → `cache(miss)` → `tushare(ok)`
4. 查询后：`LocalMongoAdapter.get(相同 key)` 返回非空、`provider="ud_materialized"`、`data` 匹配
5. 查询后：`CacheManager.get(相同 key)` 返回非空、`freshness="cached"`、原始 provider 保留为 "tushare"
6. 再查询相同参数：物化 hit → `provider="ud_materialized"`，外部 provider 调用数为 0

#### 场景 2：Cache hit → 直接返回，外部调用为 0

**前置**：Cache 层预填充有效数据（未过期）；物化层有也可无（但 Router 按 Step 2 → Step 3 顺序，Step 2 hit 的语义已经被 Step 2/3 子集测试覆盖；本场景确保 Cache 在 Step 2 miss 后命中）。

**断言**：
1. `DataResult.freshness == "cached"`
2. `result.provider` 保持原始 provider 名（如 "tushare"）
3. `source_trace` 包含 `ta_cn_internal(empty)` → `ud_materialized(miss)` → `cache(ok)`
4. 外部 provider 调用次数为 0
5. 不包含 `cache(skipped: ...)` 或 `cache(miss)` 条目

#### 场景 3：Provider A 失败 → Fallback B 成功，source_trace 有序

**前置**：tushare（链中第一）注册但 `raise_on_fetch`；akshare（第二）注册并返回有效 payload。物化/Cache 均 miss。TA-CN 空。

**断言**：
1. `DataResult.provider == "akshare"`
2. `source_trace` 包含 `tushare(error: ...)`（按实际错误文本）→ `akshare(ok)`，顺序可断言
3. `result.data` 非空

#### 场景 4：全失败 → DataResult.error（ta_cn_adapter=None 分支）

**前置**：**ta_cn_adapter=None**（无 TA-CN 层）；所有外部 provider 注册且全部 `raise_on_fetch`。物化/Cache 均 miss。

**语义澄清**：`router.py:308-311` 在 TA-CN adapter 覆盖 capability 且返回空时（`empty_ta_cn` 非 None），外部全失败后返回 `provider="empty"`（SPEC-03-008 §4.3 设计意图）。要验证 `provider="error"` 分支，本场景必须使用 `ta_cn_adapter=None`。TA-CN empty + 外部全失败 → `provider="empty"` 的独立验证由 E2E-403 覆盖（详见 SPEC-03-010 §3.4）。

**断言**：
1. `DataResult.provider == "error"`
2. `result.freshness == "empty"`（说明无数据）
3. `"all external providers failed" in result.warnings`
4. 调用方**不**捕获 `AllProvidersFailedError`（验证此异常不对外抛出）
5. `source_trace` 包含所有尝试的记录（`ud_materialized(miss)` → `cache(miss)` → `tushare(error: ...)` → `akshare(error: ...)`）——**不含** `ta_cn_internal(empty)` 条目（因 `ta_cn_adapter=None`）

#### 场景 5：force_refresh=True → 两条 skipped trace + 外部 fetch + 写入不变

**前置**：TA-CN adapter 有数据可命中（但 Step 1 被 force_refresh 守卫跳过）。物化层和 Cache 层均预填充有效数据。外部 provider 注册。

|**断言**（按 Pascal 2026-07-14 确认的 trace 语义，共两条 `(skipped: force_refresh)`，不含 `ta_cn_internal(skipped: force_refresh)`）：
|1. `source_trace == ["ud_materialized(skipped: force_refresh)", "cache(skipped: force_refresh)", "tushare(ok)"]` — 精确 trace 列表
|2. Step 1（TA-CN adapter）未被调用（call_log 空）
|3. `LocalMongoAdapter.get()` 未被调用（方案 C：_try_materialized 在 force_refresh 时返回 None 不调底层）
4. `CacheManager.get()` 未被调用
5. 查询后，物化层和 Cache 层被**更新**为新数据（写入不变契约满足）
6. 再查询无 force_refresh：物化 hit → 直接返回，外部 provider 调用为 0（证明 force_refresh 后的写入对后续查询生效）

#### 场景 6：index 双路径覆盖

**前置**：为 `index_basic_info`、`index_daily_quotes` 各构造一个双路径场景（`stock_sector_info` 的 Router E2E 不在本阶段范围，见下方说明）。

**子场景 6a（TA-CN 内部命中）**：
1. TA-CN adapter 集合含有效 index_basic_info / index_daily_quotes 数据
2. Router query 对应 capability
3. 断言：`provider == 'ta_cn_internal'`，外部 provider 调用为 0

**子场景 6b（TA-CN 空 → 外部 fallback）**：
1. TA-CN adapter 集合为空
2. 外部 tushare provider 注册并返回该 capability 的有效 payload
3. Router query 对应 capability
4. 断言：`provider == 'tushare'`，payload 非空，trace 包含正确顺序

实际覆盖的 capability（仅 index 两域，不覆盖 stock_sector_info）：
| 集合 | Router capability | ta_cn_adapter 方法 | 外部 provider payload |
|---|---|---|---|
| `index_basic_info` | `metadata.index_list` 或 `metadata.index_info` | `get_index_list` / `get_index_info` | [{"symbol":"000300","name":"沪深300"}] |
| `index_daily_quotes` | `market_data.index_daily` | `get_index_daily_bars` | [{"sector_code":"000300","close":[4000]}] |

> **`stock_sector_info` 说明**：不在 Phase 1C Router E2E 范围内。原因：Router 的 `_TA_CN_CAPABILITY_METHOD_MAP` 中无对应的 canonical capability entry，且不存在已验证的 external fallback provider。现有的 Phase 1A `SectorService` + TA-CN adapter direct read 保持不变。其未来 Router 统一入口与 external fallback 需另开独立阶段——先完成公共 capability 设计、查询粒度、分类体系与 Provider 等价性验证后再实施，具体阶段编号不预设。

#### 场景 7：覆盖率门禁 ≥ 60%

**子场景 7a（覆盖率报告可运行）**：
1. `coverage run -m pytest tests/data/unified_data/` 无错误退出
2. `coverage report --include="skills/data/unified_data/*"` 可输出线覆盖率和分支覆盖率

**子场景 7b（线覆盖率 ≥ 60%）**：
1. 当前线覆盖率若已 ≥ 60%：1C 不需盲目增加行数覆盖，而是写「行为缺口」测试（结合其他 6 个场景）
2. 当前线覆盖率若 < 60%：新增测试（优先补场景 1-6 中未覆盖的重要逻辑分支，其次补高频缺失行）
3. 分支覆盖率作为参考指标（不强约束 ≥ 60%，因为分支覆盖对 pytest + fake provider 环境而言可能因 try/except 路径消耗大量 fixture）

**阈值失败语义（硬门禁）**：
- `coverage report --fail-under=60 --include="skills/data/unified_data/*"` exit 0 = 通过
- exit 非零 = 失败，**阻塞 1C Closeout**（需补齐测试使线覆盖率 ≥ 60% 后重新运行验证）
- coverage 实测基线（2026-07-15 截图）：358 passed，88% 线覆盖率。如需补测，优先补场景 1-6 涉及模块的逻辑分支。
- `coverage` 不可用即验证失败，需人工处理；不允许 `pip install coverage` 或手动估算替代。

### 4.3 测试架构

```
tests/data/unified_data/
├── conftest.py                          # 已有：SecurityId fixtures + FakeProvider + FakeTA_CNAdapter
├── test_router_persistence.py           # 已有：Step 2/3 + materialization (17 UT + 4 IT)
├── test_router_internal_first.py        # 已有：Step 1 (TA-CN) orchestration
├── test_local_mongo_adapter.py          # 已有：LocalMongoAdapter
├── test_cache_manager.py                # 已有：CacheManager
├── test_ta_cn_mongo_adapter.py          # 已有：TA-CN adapter (含 index/sector)
├── test_router.py                       # 已有：Phase 0 router
├── ...                                  # 其他已有测试
│
├── test_e2e_full_chain.py              # [1C NEW] 7 项端到端场景
│   ├── class TestE2EScene1_AllMissExternalSuccess   → 场景 1
│   ├── class TestE2EScene2_CacheHit                 → 场景 2
│   ├── class TestE2EScene3_ProviderFallback         → 场景 3
│   ├── class TestE2EScene4_AllFail                  → 场景 4
│   ├── class TestE2EScene5_ForceRefresh             → 场景 5
│   ├── class TestE2EScene6_IndexDualPath              → 场景 6
│   └── class TestE2EScene7_CoverageGate             → 场景 7
│
└── test_models.py                      # [PATCH] 修复 1 failed test
```

### 4.4 与 1A/1B-A/1B-B 的依赖关系

```
1A (adapter) ──────► 1B-A (router orchestration) ──────► 1B-B (persistence+cache)
     │                          │                                  │
     └──────────────────────────┴──────────────────────────────────┘
                                        │
                                        ▼
                                   1C (e2e validation)
                              ┌─────────────────────┐
                              │ 全链测试 (scenes 1-5) │
                              │ index (scene6) │
                              │ 覆盖率门禁 (scene 7)  │
                              └─────────────────────┘
```

1C 不依赖任何新生产代码——它运行在 1B-B 已交付的代码基础上。修复 `test_dataframe_empty_attribute` 是唯一允许的 production 代码改动。

---

## 5. 详细设计

### 5.1 业务流程（Flow）

每项端到端场景的执行流程与断言在 §4.2 已完整定义。本节描述端到端 fixture 的设计，确保场景间的组合不产生副作用。

#### Fixture 隔离原则

| 维度 | 策略 |
|---|---|
| 数据库 | 每个测试方法创建独立的 `mongomock.MongoClient()` 实例，不从 session 级 fixture 共享 |
| ProviderRegistry | 每个测试方法通过 `fresh_registry` fixture 获取空 registry，显式 register 所需 providers |
| TA-CN adapter | 每个测试方法构造独立的 `FakeTA_CNAdapter`（可带预置数据）或传 `None` |
| 本地数据 | 物化/Cache 预填充数据在测试方法内通过 `LocalMongoAdapter.put()` / `CacheManager.put()` 设置 |

#### 场景 1 fixture 设计（最完整、被其他场景组合复用）

```python
@pytest.fixture
def e2e_ta_cn_miss():
    """TA-CN adapter that returns empty for all 8 capabilities."""
    return FakeTA_CNAdapter(collections={})  # 所有集合空 → 任何 query 返回 empty

@pytest.fixture
def e2e_tushare_ok():
    """Tushare provider that returns valid kline data."""
    return FakeProvider(
        name="tushare",
        payload={"close": [1500, 1510], "open": [1490, 1500]},
        capabilities={"market_data.kline_daily"},
        markets={Market.CN},
    )
```

数据合理性断言的 fixture 设计：payload 必须包含业务上有意义的字段（close、open 非零），不空数通过。外部 provider 返回的 payload 和预先填充到 Cache/物化的 payload 使用不同值，以便在端到端断言中区分数据来源。

### 5.2 数据模型（Data Model）

1C 不新增持久化数据模型。所有数据模型来自 Phase 0（DataResult / SecurityId）和 1B-B（03_data_ud_* / 03_data_ud_cache_* 文档信封）。

### 5.2bis 持久化策略

无持久化需求。所有测试数据在 mongomock 内存中创建和销毁，不落盘、不连接生产 Mongo。

### 5.3 接口契约

1C 不修改任何生产接口。所有测试通过 `DataRouter.query()` 统一入口进行。

### 5.4 AI 模型设计

不涉及。

---

## 6. AI 实装规范

### 6.1 必须执行

- 只修改 `tests/data/unified_data/test_e2e_full_chain.py`（新文件）和 `tests/data/unified_data/test_models.py`（bug fix）。
- 如需修改 production 代码修复 `test_dataframe_empty_attribute`，只改 `DataResult.success` 工厂函数或相关 freshness 逻辑，不改 Router / Provider / Cache / Adapter。
- 不使用 `time.sleep`。所有过期场景通过构造 `expires_at` 为过去时间的文档来模拟，不依赖真实时间等待。
- 运行 `pytest tests/data/unified_data -q --tb=short` 确保全部测试通过。
- 运行 `git diff --check` 确认无空白错误。
- 开放问题（§11）和已标记的边界项在 Verify 阶段确认。

### 6.2 先询问再执行

- 如需修改 `_TA_CN_CAPABILITY_METHOD_MAP` 添加 sector_info 的 capability 条目（当前开放问题），先询问 Pascal。
- 如需新增第三方依赖（如 `pytest-cov`），先询问。
- 如需修改任何非 test_e2e_full_chain.py 或 test_models.py 的现有测试文件，先确认不影响原有测试语义。

### 6.3 绝对禁止

- 禁止连接真实 MongoDB 或外部 API。
- 禁止创建、修改或删除 RFC/SPEC/Design 文档（本 RFC 的 T2 Design 阶段自有 Design 文档）。
- 禁止修改 TA-CN 子项目代码（`skills/apps/TradingAgents-CN/**`）。
- 禁止修改 DSA / Argus / portfolio / task_center / cron / systemd 相关代码。

---

## 7. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| coverage CLI 不可用或版本不兼容 | 低 | 高 | `.venv/bin/python -m coverage` 已安装（7.15.1），Verify 阶段直接使用；不可用时视为验证失败 | 人工处理，不允许 `pip install coverage` 或手动估算替代；不阻塞 1C 研发但阻塞 Closeout |
| Phase 1B-B force_refresh 方案有未发现的实现缺陷（如 Step 1 bypass 守卫影响 force_refresh trace 语义） | 低 | 高 | 场景 5 的完整断言将在端到端链中暴露此问题；一旦发现按范围裁决回退到 T3 | 若暴露 P0 bug，1C crew 立即 block 并通知 orchestrator |
| test_dataframe_empty_attribute 修复需要修改 Phase 0 的 `success()` 工厂函数，可能影响其他测试 | 低 | 中 | 修改后全量跑 `pytest tests/data/unified_data/` 确认无回归 | 若修复导致更多失败，退回并标记为 1C 已知残余风险，在 Closeout 报告中标注 |
| 当前线覆盖率远低于 60%，需大量新增测试 | 低 | 中 | 先跑覆盖率报告确认真实值；若远低，优先补场景 1-6 涉及的行和分支，不追求覆盖每个 `except` 行 | 线覆盖率 ≥ 60% 为硬门禁，未达标则阻塞 Closeout，必须在 1C 内补齐 |
| stock_sector_info 在 Router MAP 中没有独立 capability | 已关闭（Pascal 确认） | 低 | Pascal 已确认选择 Path A：`stock_sector_info` 的 Router E2E 不在 1C 范围；现有的 Phase 1A `SectorService` + adapter direct read 保持不变 | 其未来 Router 统一入口与 external fallback 需另开独立阶段，先做公共 capability 设计、查询粒度、分类体系与 Provider 等价性验证后再实施 |

---

## 8. 备选方案

| 方案 | 描述 | 优缺点 | 结论 |
|---|---|---|---|
| A（采纳） | 独立 `test_e2e_full_chain.py` 文件，7 个 TestClass | 隔离性好、易按场景定位失败、每个类最短 ~15 行。优先推荐 | ✅ 采纳 |
| B（拒绝） | 在现有的 `test_router_persistence.py` / `test_router_internal_first.py` 追加端到端类 | 文件已有 862+428 行，再追加使文件臃肿；且端到端测试的 fixture 组合与现有子集测试不同 | ❌ 不采纳 |
| C（拒绝） | 不建独立文件，通过 pytest marker 标记端到端场景 | 当无 CI 过滤需求时 marker 引入心智负担 | ❌ 不采纳 |

---

## 9. 验收标准

### 9.1 功能验收

| # | 验收项 | 验证方式 |
|---|---|---|
| AC-01 | `test_e2e_full_chain.py` 文件存在于 `tests/data/unified_data/`，含 7 个 TestClass | `ls -la tests/data/unified_data/test_e2e_full_chain.py` |
|| AC-02 | 场景 1（全 miss → 外部成功 → 写入 → 再查询命中）全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene1_AllMissExternalSuccess -q` |
|| AC-03 | 场景 2（Cache hit → 零外部调用）全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene2_CacheHit -q` |
|| AC-04 | 场景 3（Provider A fail → B 成功 → trace 有序）全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene3_ProviderFallback -q` |
|| AC-05 | 场景 4（全失败 → DataResult.error，不抛异常）全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene4_AllFail -q` |
|| AC-06 | 场景 5（force_refresh → 两条 skipped + 外部 fetch + 写入不变）全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene5_ForceRefresh -q` |
|| AC-07 | 场景 6（index 双路径：内部命中 + 外部兜底）全部断言通过 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene6_IndexDualPath -q` |
|| AC-08 | 场景 7（覆盖率报告可运行 + 门禁检查）至少可执行 | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene7_CoverageGate -q` |
| AC-09 | `test_dataframe_empty_attribute` 已修复，全部 358+ 测试通过 | `pytest tests/data/unified_data -q` exit 0 |
| AC-10 | 所有 e2e fixture 包含非空业务数据（不空 payload 伪通过） | 人工审核 fixture payload 定义 |
| AC-11 | | |

### 9.2 非功能验收

| # | 验收项 | 验证方式 |
|---|---|---|
| NFC-01 | 全部测试在 30 秒内完成 | `hyperfine 'pytest tests/data/unified_data/ -q'` 或 time |
| NFC-02 | 不使用真实外部 API 或 Mongo 连接 | 确认所有 import 不含真实 provider 调用 |
| NFC-03 | git diff 无空白错误 | `git diff --check` |
| NFC-04 | 中文交付：变更路径、文档摘要、检查命令/结果、开放问题 | 人工审核 |

---

## 10. 落地计划

### 10.1 阶段划分

本 RFC 后续由 T2 Design（详细设计）、T3 Implement（代码）、T4 Verify（独立验证）、T5 Review（独立审查）依次执行。1C 预计耗时 1-2 天（含测试编写、修复、验证）。

### 10.2 任务清单（T3 Implement → T3 Remediation 两轮）

**第 1 轮（T3 Implement 初始）**：
| 任务 | 文件 | 说明 |
|---|---|---|
| 新建 e2e 测试文件 | `tests/data/unified_data/test_e2e_full_chain.py` | 7 个 TestClass，~300-500 行 |
| 修复 test_models.py bug | `tests/data/unified_data/test_models.py` + 可能 `skills/data/unified_data/models/data_result.py` | 修复空 DataFrame 场景 freshness 断言 |
| 运行覆盖率 | 运行 `coverage run -m pytest tests/data/unified_data/ && coverage report -m --include="skills/data/unified_data/*"` | 产出覆盖率报告 |
| 修补覆盖率缺口 | 若 < 60%，补充到 ≥ 60%（优先场景 1-6 已覆盖的模块行） | 根据覆盖率报告决定 |
| 完整跑通并提交 | `pytest tests/data/unified_data -q --tb=long` 全绿 | |

**第 2 轮（T3 Remediation — 裁决后执行）**：
| 任务 | 文件 | 说明 |
|---|---|---|
| 文件拆分 ≤300 行 | `test_e2e_*.py` 按 DESIGN-03-010 §3.9 拆分 | 入口 + fixtures + 4 场景文件 |
| 精确 source_trace 断言 | 场景 3/4/5 trace 改为 `==` 完整列表 | 按 SPEC-03-010 §6.1.1 执行 |
| 业务字段断言 | 场景 6 index 外部兜底改 `is not None` 为字段级断言 | 按 SPEC-03-010 §6.1.1 执行 |
| 全量回归测试 | `pytest tests/data/unified_data -q --tb=long` 全绿 | 确认 374+ passed |

---

## 11. 开放问题

| # | 问题 | 影响 | 处理结果 |
|---|---|---|---|
| OQ-01 | `stock_sector_info` 在 Router 的 `_TA_CN_CAPABILITY_METHOD_MAP` 中没有对应的 capability entry。场景 6 的 sector 部分需要确认：是否新增 capability？ | 已关闭 | ✅ **Pascal 已确认 Path A**：`stock_sector_info` 不在 1C Router E2E 范围内。现有的 Phase 1A `SectorService` + adapter direct read 保持不变。未来 Router 统一入口需另开独立阶段，先做公共 capability 设计、查询粒度、分类体系与 Provider 等价性验证后再实施。 |
| OQ-02 | 覆盖率工具是否已安装？ | 已关闭 | ✅ `.venv/bin/python -m coverage` 已安装（7.15.1），2026-07-15 实测 358 passed，88% 线覆盖率。不允许 `pip install coverage`。不可用时视为验证失败。 |
| OQ-03 | `test_dataframe_empty_attribute` 的预期行为？ | 已关闭 | ✅ 实测已验证通过：`DataResult.success` 工厂对空 DataFrame 已正确产出 `freshness="empty"`。无需代码改动。 |
| OQ-04 | 线覆盖率门禁 `--fail-under=60` 的失败语义？ | 已关闭 | ✅ 硬门禁：exit 非零 = 失败，**阻塞 1C Closeout**。当前 88% ≥ 60%，大概率无需补测。 |

---

## 12. 参考资料

| 文档 | 路径 |
|---|---|
| RFC-03-007 Unified Data Layer 总纲 | `docs/rfc/03_data/RFC-03-007-unified-data-layer.md` |
| SPEC-03-007 Unified Data Layer 契约 | `docs/spec/03_data/SPEC-03-007-unified-data-layer.md` |
| DESIGN-03-007 Unified Data Layer 总设计 | `docs/design/03_data/DESIGN-03-007-unified-data-layer.md` |
| RFC-03-008 Phase 1B-A 查询平面 | `docs/rfc/03_data/RFC-03-008-unified-data-phase-1b-query-plane.md` |
| SPEC-03-008 Phase 1B-A 查询平面 | `docs/spec/03_data/SPEC-03-008-unified-data-phase-1b-query-plane.md` |
| DESIGN-03-008 Phase 1B-A 查询平面设计 | `docs/design/03_data/DESIGN-03-008-unified-data-phase-1b-query-plane.md` |
| RFC-03-009 Phase 1B-B 持久化缓存平面 | `docs/rfc/03_data/RFC-03-009-unified-data-phase-1b-persistence-plane.md` |
| SPEC-03-009 Phase 1B-B 持久化缓存平面 | `docs/spec/03_data/SPEC-03-009-unified-data-phase-1b-persistence-plane.md` |
| DESIGN-03-009 Phase 1B-B 持久化缓存平面设计 | `docs/design/03_data/DESIGN-03-009-unified-data-phase-1b-persistence-plane.md` |
| unified_data SKILL.md | `skills/data/unified_data/SKILL.md` |
| AI Coding Pipeline SKILL.md | `skills/infra/ai-coding-pipeline/SKILL.md` |

---

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
|| V0.3 | 2026-07-15 | T2.6 Review Remediation：① all-fail 语义收敛——Scene 4 改为 ta_cn_adapter=None 分支，trace 不含 ta_cn_internal(empty)；② 精确断言强化——Scene 3/5 trace 改为 `==` 完整列表，Scene 6 外部兜底改为业务字段断言；③ 测试节点飘移修正——AC-02~AC-08 改用完整类名；④ 文件拆分方案——DESIGN-03-010 §3.9 定义 6 文件 ≤300 行拆分。 | YQuant-Principal |
| V0.1 | 2026-07-14 | 初始创建 | YQuant-Principal |
