# DESIGN-03-010: Unified Data Phase 1C — 端到端验收与测试收口详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
|| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-15 |
| 最后更新 | 2026-07-15 |
| 来源 RFC | RFC-03-010（Unified Data Phase 1C — 端到端验收与测试收口） |
| 来源 SPEC | SPEC-03-010（Unified Data Phase 1C — 端到端验收与测试收口） |
| 关联 Design | DESIGN-03-007（Unified Data Layer 总设计）、DESIGN-03-008（Phase 1B-A 查询平面设计）、DESIGN-03-009（Phase 1B-B 持久化缓存平面设计） |
| 关联 SPEC | SPEC-03-007/008/009 |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 版本号 | V0.2 |
| 适配 Agent | YQuant-Developer-Engineer (T3 Implement), YQuant-Test-Engineer (T4 Verify) |

---

## 1. 设计摘要

Phase 1C 是 Unified Data Layer 的**证据/验收层**，不是新数据能力层。核心交付：

1. **`tests/data/unified_data/test_e2e_full_chain.py`** — 7 个 TestClass / 16 个测试方法，覆盖四步 internal-first 路径（TA-CN → UD 物化 → Query Cache → 外部 Provider）的全部关键分叉。
2. **覆盖率门禁 ≥ 60%** — `coverage run + coverage report --fail-under=60` 可量化执行。
3. **空 DataFrame freshness 修复** — `DataResult.success` 工厂对空 DataFrame 已正确产出 `freshness="empty"`（2026-07-15 实测验证通过，测试本身由环境修复；确认无代码改动必要，但作为回归断言列入场景覆盖）。
4. **零真实外部依赖** — 全部测试在 `pytest + mongomock + FakeProvider + FakeTA_CNAdapter` 沙箱中运行。

### 1.1 与上游设计的关系

Phase 1C 构建在前三个子阶段已交付代码之上：

```
1A (adapter) ──────► 1B-A (router orchestration) ──────► 1B-B (persistence+cache)
     │                          │                                  │
     └──────────────────────────┴──────────────────────────────────┘
                                        │
                                        ▼
                                   1C (e2e validation)
```

- **1A** 提供 FakeTA_CNAdapter（conftest.py）可直接复用
- **1B-A** 提供 FakeProvider、DataRouter、internal-first 编排骨架
- **1B-B** 提供 LocalMongoAdapter、CacheManager、force_refresh 语义（方案 C）、catch-and-log 模式

Phase 1C 不修改以上任何已交付代码（除 DataResult.success 空 payload 检查逻辑已就位、无需修改）。Design 文档约定：**只读复现**（read-only validation）——测试证明前三个阶段的行为组合符合契约。

---

## 2. 现状分析

### 2.1 相关文件

| 文件 | 行数（约） | 状态 |
|---|---|---|
| `tests/data/unified_data/test_e2e_full_chain.py` | — | **新增**（300-500 行，本 Design 定义） |
| `tests/data/unified_data/test_models.py` | 395 | **可能修改**（验证 test_dataframe_empty_attribute 是否需修复；2026-07-15 实测 358 passed，无失败。若 T3 Implement 环境仍发现失败，需修复断言或工厂逻辑） |
| `skills/data/unified_data/models/__init__.py` | 524 | **可能修改**（仅当 test_dataframe_empty_attribute 在 T3 环境仍失败时，修复 _is_empty_payload 或 success 工厂；2026-07-15 .venv 环境已验证通过） |
| `skills/data/unified_data/router.py` | 981 | **不修改**（1B-B 已交付路线逻辑，1C 只验证不修改） |
| `skills/data/unified_data/cache_manager.py` | — | **不修改** |
| `skills/data/unified_data/local_mongo_adapter.py` | — | **不修改** |
| `tests/data/unified_data/conftest.py` | 306 | **不修改**（FakeProvider / FakeTA_CNAdapter 直接复用） |
| `tests/data/unified_data/test_router_persistence.py` | 862 | **不修改**（1B-B 的 21 个子集测试保持独立） |

### 2.2 现有测试基线

| 测试文件 | 数量 | 用途 |
|---|---|---|
| `test_models.py` | 54 UT | SecurityId / DataResult / Capability 模型测试 |
| `test_router.py` | 78 UT | Phase 0 基础路由 |
| `test_provider_registry.py` | 39 UT | ProviderRegistry 测试 |
| `test_router_internal_first.py` | 106 UT | 1B-A 内部优先编排（Step 1 + Step 4） |
| `test_ta_cn_mongo_adapter.py` | 18 UT | 1A TA-CN adapter（含 index/sector） |
| `test_local_mongo_adapter.py` | 26 UT | 1B-B LocalMongoAdapter |
| `test_cache_manager.py` | 17 UT | 1B-B CacheManager |
| `test_router_persistence.py` | 17 UT + 4 IT | 1B-B Step 2/3 + 持久化集成 |

T3 Implement 新增 7 TestClass / 16 方法后，预期基线变为：358 + 16 = **374 passed**（若 test_models.py 无失败）。

### 2.3 四步 internal-first 路径现状（已由 1B-B 实现）

```
Step 1: TA-CN adapter (_try_ta_cn)
  ├─ capability not in _TA_CN_CAPABILITY_METHOD_MAP → skipped: not covered → Step 4
  ├─ 命中 ✓ → provider="ta_cn_internal", 返回
  ├─ 返回 None/空列表 → empty DataResult, 返回 (不继续 fallback)
  └─ raise → error trace → Step 4

Step 2: Materialized layer (_try_materialized)
  ├─ adapter is None → skipped: no adapter → Step 3
  ├─ force_refresh=True → skipped: force_refresh → Step 3 (get() 未被调用)
  ├─ 命中非过期 → provider="ud_materialized", freshness="cached", 返回
  ├─ 过期 → miss → Step 3
  └─ exception → error trace → Step 3

Step 3: Query cache (_try_cache)
  ├─ manager is None → skipped: no manager → Step 4
  ├─ force_refresh=True → skipped: force_refresh → Step 4 (get() 未被调用)
  ├─ 命中非过期 → freshness="cached", 原始 provider 保留, 返回
  ├─ 过期 → miss → Step 4
  └─ exception → error trace → Step 4

Step 4: External fallback chain (_query_external_chain)
  ├─ 外部成功 → _materialize() 写入物化+Cache → 返回 DataResult.success
  ├─ 全部失败 → DataResult.error(provider="error"), warnings=["all external providers failed"]
  └─ catch-and-log: 物化/Cache 写入异常不阻断返回
```

### 2.4 force_refresh 语义（方案 C，1B-B 已落地）

`_try_materialized` 和 `_try_cache` 已实现方案 C 守卫：
- `force_refresh=True` 时两个 helper **返回 None**，不调用底层 `get()`，只追加 `(skipped: force_refresh)` trace 条目
- 此行为由 1B-B `test_router_persistence.py::UT-PR-007` 验证（monkeypatch 断言 `adapter.get()` 和 `cache.get()` 未被调用）
- Phase 1C 的 E2E-501/502/503 扩展验证：全链路（含 TA-CN adapter）的 force_refresh 行为一致

### 2.5 现有约束

- `DataResult.success()` 工厂已包含 `_is_empty_payload()` 检测（`getattr(data, "empty", None)` + `isinstance(empty_attr, bool)`），能正确处理 `pd.DataFrame().empty == True`
- `FreshnessPolicy.label(from_cache=True)` 已就位
- `source_trace` 使用字符串列表，格式为 `"<component>(<outcome>)"`，entries 顺序反映实际执行顺序
- `mongomock` 已在测试依赖中
- 项目用 `.venv/bin/python`（Python 3.11）运行测试，pandas 已安装

---

## 3. 方案设计

### 3.1 文件改动清单

T3 Implement（初始交付）：
| 文件 | 操作 | 预计新增行 | 依赖 |
|---|---|---|---|
| `tests/data/unified_data/test_e2e_full_chain.py` | **新建** | 350-500 | conftest.py: FakeProvider, FakeTA_CNAdapter |
| `tests/data/unified_data/test_models.py` | **可能修改** | 0-3 | 仅在 T3 环境仍发现 test_dataframe_empty_attribute 失败时 |
| `skills/data/unified_data/models/__init__.py` | **可能修改** | 0-3 | 同上，仅在 success 工厂或 _is_empty_payload 需修复时 |

T3 Remediation（文件拆分 + 断言强化，本裁决后的下一 T3 Implementing step）：
| 文件 | 操作 | 预计新增行 | 依赖 |
|---|---|---|---|
| `tests/data/unified_data/test_e2e_full_chain.py` | **重写为入口**（仅 imports + re-exports） | ~30 | 子模块 |
| `tests/data/unified_data/test_e2e_fixtures.py` | **新建**（from test_e2e_full_chain.py 抽取） | ~260 | 无 |
| `tests/data/unified_data/test_e2e_scene_1_2_3.py` | **新建**（from test_e2e_full_chain.py 抽取） | ~230 | test_e2e_fixtures |
| `tests/data/unified_data/test_e2e_scene_4.py` | **新建** | ~110 | test_e2e_fixtures |
| `tests/data/unified_data/test_e2e_scene_5.py` | **新建** | ~220 | test_e2e_fixtures |
| `tests/data/unified_data/test_e2e_scene_6_7.py` | **新建** | ~180 | test_e2e_fixtures |

> **注意**：T3 Remediation 阶段只做文件拆分 + 断言强化，不改 Router / Provider / Cache / Adapter / conftest / 已有测试。每条断言按 SPEC §6.1.1 和 Design §3.2 Assertion Style 列的精度执行。

**始终禁止修改**：`router.py`、`cache_manager.py`、`local_mongo_adapter.py`、`client.py`、`freshness.py`、`config.py`、`registry.py`、`conftest.py`、`test_router_persistence.py` 及其他已有测试文件。

### 3.2 测试类矩阵

每个 TestClass 对应一个 SPEC E2E-xxx 场景。每项对应 SPEC E2E 编号与测试方法（Assertion Style 列注释判定强度）：

| 场景 | TestClass | 测试方法 | 断言数量 | SPEC E2E | Assertion Style |
|---|---|---|---|---|---|
| 1 全 miss→外部成功→写入→再查询 | `TestE2EScene1_AllMissExternalSuccess` | `test_returns_external_data` | 5 | E2E-101 | exact trace (`==` list), exact data |
| | | `test_materialized_written` | 4 | E2E-102 | exact provider/data |
| | | `test_cache_written` | 4 | E2E-103 | exact freshness/provider |
| | | `test_subsequent_hit_materialized` | 3 | E2E-104 | provider call count |
| 2 Cache hit→0 外部调用 | `TestE2EScene2_CacheHit` | `test_cache_hit_zero_external` | 5 | E2E-201 | exact freshness/provider/data, `call_log==[]` |
| 3 Provider A fail→B 成功 | `TestE2EScene3_ProviderFallback` | `test_fallback_ordered` | 4 | E2E-301 | **精确 source_trace**（`==` 完整列表），call count 断言 |
| 4 全失败→DataResult.error | `TestE2EScene4_AllFail` | `test_returns_error_result` | 4 | E2E-401 | exact error/freshness/warnings |
| | | `test_trace_completeness` | 3 | E2E-402 | **精确 trace**（不含 ta_cn_internal） |
| 5 force_refresh | `TestE2EScene5_ForceRefresh` | `test_skipped_trace` | 5 | E2E-501 | **精确 trace**（`==` 完整列表），TA-CN call_log 空，get() 计数间接 |
| | | `test_write_unchanged` | 2 | E2E-502 | exact payload |
| | | `test_subsequent_hit` | 2 | E2E-503 | provider call count |
| 6 index 双路径 | `TestE2EScene6_IndexDualPath` | `test_index_list_internal` | 3 | E2E-601 | exact provider, call_log==[] |
| | | `test_index_list_external` | 3 | E2E-602 | **业务字段断言**（symbol/name），不只是 `is not None` |
| | | `test_index_daily_internal` | 3 | E2E-603 | exact provider, call_log==[], 字段值合理性 |
| | | `test_index_daily_external` | 3 | E2E-604 | **业务字段断言**（sector_code/close），不只是 `is not None` |
| 7 覆盖率门禁 | `TestE2EScene7_CoverageGate` | `test_coverage_report_runs` | 2 | E2E-701, E2E-702 | subprocess exit 0, TOTAL 行存在 |

**总计**：7 个 TestClass × 16 个测试方法。全部16个测试方法的断言必须按 Assertion Style 列标注的精度实现。

### 3.3 时序图

#### 3.3.1 场景 1：全 miss → 外部成功 → 写入 → 再查询命中

```
┌─────────────────────────────────────────────────────────────────────┐
│ TestE2EScene1: test_returns_external_data                           │
│                                                                     │
│  DataRouter.query(market_data.kline_daily, CN:600519)              │
│    │                                                                 │
│    ├─ Step 1: _try_ta_cn()                                          │
│    │   └─ FakeTA_CNAdapter(collections={}) → None/[] → empty       │
│    │      trace: [ta_cn_internal(empty)]                            │
│    │                                                                 │
│    ├─ Step 2: _try_materialized()                                   │
│    │   └─ LocalMongoAdapter.get() → None → miss                    │
│    │      trace: [..., ud_materialized(miss)]                       │
│    │                                                                 │
│    ├─ Step 3: _try_cache()                                          │
│    │   └─ CacheManager.get() → None → miss                         │
│    │      trace: [..., cache(miss)]                                 │
│    │                                                                 │
│    ├─ Step 4: _query_external_chain()                               │
│    │   └─ tushare (registered, payload non-empty) → ok             │
│    │      trace: [..., tushare(ok)]                                 │
│    │   └─ _materialize() → 写入物化+Cache                           │
│    │                                                                 │
│    └─ Assert: provider="tushare", data 非空, source_trace 完整      │
│                                                                     │
│ test_materialized_written: LocalMongoAdapter.get() → 非空           │
│ test_cache_written: CacheManager.get() → 非空, freshness="cached"  │
│ test_subsequent_hit_materialized: 再查询→provider="ud_materialized"│
└─────────────────────────────────────────────────────────────────────┘
```

#### 3.3.2 场景 5：force_refresh

```
┌─────────────────────────────────────────────────────────────────────────┐
│ TestE2EScene5_ForceRefresh                                              │
│                                                                         │
│ 前置：TA-CN adapter 有数据；物化层预填充；Cache 预填充；外部 provider OK │
│                                                                         │
│  DataRouter.query(kline_daily, CN:600519, force_refresh=True)          │
│    │                                                                     │
│    ├─ Step 1: _try_ta_cn()  // 守卫：force_refresh → bypass            │
│    │  (Pascal 确认：force_refresh 跳过 Step 1—TA-CN adapter          │
│    │   不被调用且无 `ta_cn_internal(skipped: force_refresh)` trace)   │
│    │   └─ FakeTA_CNAdapter 未被调用 → call_log 为空                    │
│    │                                                                     │
│    ├─ Step 2: _try_materialized(force_refresh=True)                    │
│    │   └─ skipped: force_refresh → get() 0 次                           │
│    │      trace: [ud_materialized(skipped: force_refresh)]              │
│    │                                                                     │
│    ├─ Step 3: _try_cache(force_refresh=True)                           │
│    │   └─ skipped: force_refresh → get() 0 次                           │
│    │      trace: [..., cache(skipped: force_refresh)]                   │
│    │                                                                     │
│    ├─ Step 4: tushare → ok                                              │
│    │   trace: [..., tushare(ok)]                                        │
│    │   └─ _materialize() → 写入物化+Cache（写入不变）                   │
│    │                                                                     │
│    └─ Assert: trace 含两条 skipped（ud_materialized + cache），          │
│       不含 `ta_cn_internal(skipped: force_refresh)`；                   │
│       物化.get() 0 次；cache.get() 0 次                                 │
│                                                                         │
│ test_write_unchanged: 物化+Cache 被更新为新数据                          │
│ test_subsequent_hit: 再查询 force_refresh=False → 物化 hit              │
└─────────────────────────────────────────────────────────────────────────┘
```

> **force_refresh vs Step 1 TA-CN adapter 的交互确认**：`query()` 主分支的条件是 `not force_refresh and self._ta_cn_adapter is not None and capability in method_map`。当 `force_refresh=True` 时，Step 1 被整个跳过——TA-CN adapter 不会被调用。Pascal 已确认：force_refresh 场景的 trace 不含 `ta_cn_internal(skipped: force_refresh)` 条目，仅包含 ud_materialized 与 cache 两条 skipped trace。

### 3.4 Fixture 设计

#### 3.4.1 文件级 fixture

| fixture | 作用域 | 类型 | 说明 |
|---|---|---|---|
| `e2e_db` | function | mongomock | 独立 `mongomock.MongoClient().get_database("tradingagents")` |
| `e2e_registry` | function | ProviderRegistry | 空 registry（同 `fresh_registry`），每测试独立 |
| `e2e_ta_cn_miss` | function | FakeTA_CNAdapter | `collections={}` — 所有集合空 |
| `e2e_ta_cn_with_index` | function | FakeTA_CNAdapter | `collections={"index_basic_info": [...], "index_daily_quotes": [...]}` — 仅含 index 数据 |
| `e2e_tushare_ok` | function | FakeProvider | 返回有效 kline payload（close/open 非零，区分度值） |
| `e2e_tushare_index_list_ok` | function | FakeProvider | 返回 index_list payload（含 symbol/name 字段） |
| `e2e_tushare_index_daily_ok` | function | FakeProvider | 返回 index_daily payload（含 sector_code/close 字段） |
| `e2e_tushare_fail` | function | FakeProvider | `raise_on_fetch=ProviderError("tushare down")` |
| `e2e_akshare_ok` | function | FakeProvider | 返回有效 kline payload（与 tushare payload 值不同，可区分数据来源） |

#### 3.4.2 fixture 数据合理性标准

所有 fixture payload **必须包含业务可理解的字段**，不得空 payload 伪通过：

| fixture | 最小 payload 要求 |
|---|---|
| kline payload | `{"close": [1500, 1510], "open": [1490, 1500], "trade_date": ["20260701", "20260702"]}` |
| index_list payload | `[{"symbol": "000300", "full_symbol": "000300.SH", "name": "沪深300", "market": "SH"}]` |
| index_daily payload | `[{"sector_code": "000300", "trade_date": "20260701", "close": 4000.0, "pct_chg": 0.5}]` |
| 物化预填充 payload | `{"close": [100, 101]}`（≠ 外部 tushare payload，以区分来源） |
| Cache 预填充 payload | `{"close": [200, 201]}`（≠ 物化 payload，以区分来源） |

#### 3.4.3 fixture 隔离原则

- **数据库**：每测试方法通过 `e2e_db` fixture 获取独立 mongomock 实例
- **ProviderRegistry**：每测试方法通过 `e2e_registry` 获取空 registry，显式注册所需 provider
- **TA-CN adapter**：每测试方法获取独立 FakeTA_CNAdapter 实例
- **物化/Cache 预填充**：在测试方法内通过 `LocalMongoAdapter.put()` / `CacheManager.put()` 显式设置
- **无 session 级 fixture**：不共享 mongomock 数据库或 Registry，避免测试间状态污染

### 3.5 场景级详细设计

#### 3.5.1 场景 1：全 miss → 外部成功 → 写入 → 再查询命中（E2E-101~104）

**前置条件**：
- TA-CN：`e2e_ta_cn_miss`（所有集合空）
- 物化层：不预填充（`LocalMongoAdapter(mongo_db=e2e_db)`，未 put）
- Cache 层：不预填充（`CacheManager(mongo_db=e2e_db)`，未 put）
- 外部：`e2e_registry.register(e2e_tushare_ok)` — tushare 注册，kline payload 非空

**Router 构建参数**：
```python
DataRouter(
    registry=e2e_registry,
    ta_cn_adapter=e2e_ta_cn_miss,
    local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
    cache_manager=CacheManager(mongo_db=e2e_db),
)
```

**断言（test_returns_external_data）**：
1. `result.provider == "tushare"`
2. `result.data` 非空（`{"close": [1500, 1510], ...}`）
3. `result.source_trace == ["ta_cn_internal(empty)", "ud_materialized(miss)", "cache(miss)", "tushare(ok)"]` — 顺序和成员精确断言
4. `result.freshness` 非 "empty"（外部返回非空数据）
5. `result.warnings == []`

**断言（test_materialized_written）**：
1. `adapter = LocalMongoAdapter(mongo_db=e2e_db); got = adapter.get(cn_maotai, "market_data", "kline_daily", {})`
2. `got is not None`
3. `got.provider == "ud_materialized"`
4. `got.data == {"close": [1500, 1510], ...}`（数据匹配）

**断言（test_cache_written）**：
1. `cache = CacheManager(mongo_db=e2e_db); got = cache.get(cn_maotai, "market_data", "kline_daily", {})`
2. `got is not None`
3. `got.freshness == "cached"`
4. `got.provider == "tushare"`（原始 provider 保留）

**断言（test_subsequent_hit_materialized）**：
1. 再次 `router.query("market_data", "kline_daily", cn_maotai)`
2. `result.provider == "ud_materialized"`
3. `e2e_registry.get("tushare").call_log` 长度 == 1（第一次调用，第二次未调用外部）

#### 3.5.2 场景 2：Cache hit → 零外部调用（E2E-201）

**前置条件**：
- TA-CN：`e2e_ta_cn_miss`（空 → Step 1 返回 empty，不继续 fallback）
  - ⚠️ **注意**：TA-CN 返回 empty DataResult 会 **短接**（SPEC-03-008 §4.3），不会走到 Step 2/3/4。因此 Cache hit 场景需要 TA-CN **不覆盖该 capability**（`covered_capabilities=set()`）或跳过 TA-CN。
  - **方案**：使用 `FakeTA_CNAdapter(collections={}, covered_capabilities=set())` 或传 `ta_cn_adapter=None` 让 Step 1 无 TA-CN adapter 可用。

**Router 构建参数**：
```python
# 方案 A（推荐）：ta_cn_adapter=None 让 Step 1 被跳过的语义更清晰
DataRouter(
    registry=e2e_registry,       # 含 e2e_tushare_ok 已注册
    ta_cn_adapter=None,          # Step 1 skipped: no adapter
    local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),   # 空，Step 2 miss
    cache_manager=CacheManager(mongo_db=e2e_db),
)
# 预先将有效数据写入 Cache：
cache = CacheManager(mongo_db=e2e_db)
cache.put(cn_maotai, "market_data", "kline_daily", {}, DataResult(... 原始 provider="tushare"))
```

**断言**：
1. `result.freshness == "cached"`
2. `result.provider == "tushare"`（原始 provider 保留）
3. `result.data == {"close": [200, 201]}`（缓存 payload 不变）
4. 外部 provider 调用数 `0`：`e2e_tushare_ok.call_log == []`
5. `result.source_trace` 不含任何 `cache(skipped: ...)` 或 `cache(miss)` 条目（证明 cache 真的 hit 了，不是 skip 或 miss）

#### 3.5.3 场景 3：Provider A → B fallback（E2E-301）

**前置条件**：
- TA-CN：`e2e_ta_cn_miss`
- 物化/Cache：空（默认）
- 外部：`e2e_tushare_fail`（`raise_on_fetch=ProviderError("tushare rate limit")`） + `e2e_akshare_ok`（kline payload 非空）

**Router config fallback chain**：
```python
UnifiedDataConfig(
    default_fallback_chain=("tushare", "akshare"),
)
```

**断言（test_fallback_ordered）**：
1. `result.provider == "akshare"`
2. `result.data == {"close": [2500, 2510], "open": [2490, 2500], "trade_date": ["20260701", "20260702"]}`（来自 akshare payload，值应与 tushare payload 不同以区分来源）
3. `result.source_trace == ["ta_cn_internal(empty)", "ud_materialized(miss)", "cache(miss)", "tushare(error: tushare rate limit)", "akshare(ok)"]` — **使用 `==` 精确断言完整 trace 列表**（参见 SPEC §6.1.1）
4. `e2e_tushare_fail.call_log` 长度为 1（tushare 被调用一次后失败）

#### 3.5.4 场景 4：全失败 → DataResult.error（E2E-401/402）

|**前置条件**：
|- TA-CN：**ta_cn_adapter=None**（无 TA-CN 层——Step 1 被跳过，无 `ta_cn_internal(empty)` trace 条目，`empty_ta_cn` 为 None 确保 `provider="error"` 分支可达）
|- 物化/Cache：空
|- 外部：两个 provider 全部 `raise_on_fetch`：`e2e_tushare_fail` + `e2e_akshare_fail`

**Router fallback chain**：`("tushare", "akshare")`

> ⚠️ **重要设计决策**：当前 `router.py:308-311` 在 TA-CN adapter 覆盖 capability 且返回空时（`empty_ta_cn` 非 None），外部全失败后会**返回 `empty_ta_cn`（`provider="empty"`）**而非 `provider="error"`。这是 SPEC-03-008 §4.3 设计意图。因此，要验证 `provider="error"` 分支，本场景必须使用 `ta_cn_adapter=None`。单独的「TA-CN empty + 外部全失败 → `provider="empty"」验证不属于本场景范围（若需要，在 T3 中作为独立测试方法添加，预期 `provider="empty"`）。**本阶段不修改生产 Router（L308-311）。**

**断言（test_returns_error_result）**：
1. `result.provider == "error"`
2. `result.freshness == "empty"`
3. `"all external providers failed" in result.warnings`
4. **不捕获** `AllProvidersFailedError` — 验证异常不对外抛出

**断言（test_trace_completeness）**：
1. `result.source_trace` 包含：`ud_materialized(miss)` → `cache(miss)` → `tushare(error: ...)` → `akshare(error: ...)`
2. 全部 4 个条目存在且顺序正确
3. **不包含** `ta_cn_internal(empty)` 条目（Step 1 因 `ta_cn_adapter=None` 跳过）

#### 3.5.5 场景 5：force_refresh（E2E-501/502/503）

**前置条件**：
- TA-CN：`fake_ta_cn_with_kline`（有 kline 数据可命中）
- 物化层：预填充（与 tushare payload 不同值）
- Cache 层：预填充（与物化 payload 不同值）
- 外部：`e2e_tushare_ok`

**关键行为确认**：

`force_refresh` 在 `query()` 主分支的守卫逻辑（`router.py` lines 270-274）：

```python
if (
    not force_refresh
    and self._ta_cn_adapter is not None
    and capability not in self._TA_CN_NOT_COVERED
    and capability in self._TA_CN_CAPABILITY_METHOD_MAP
):
    ta_cn_result = self._try_ta_cn(...)
```

当 `force_refresh=True`：Step 1 被跳过，TA-CN adapter 不被调用。trace 由 `_query_external_chain_with_cache` 中的 `inherited_trace` 容器承载。

因此，全链路 force_refresh 的 trace 应为（Pascal 已确认，不含 `ta_cn_internal(skipped: force_refresh)`）：
```
["ud_materialized(skipped: force_refresh)", "cache(skipped: force_refresh)", "tushare(ok)"]
```

**验证方法**：T3 Implement 阶段先运行 1B-B 已有的 `test_force_refresh_skips_step2_3` 确认 UT-PR-007 通过。然后构建端到端场景 5 验证全链路 trace 是否符合预期。

**断言（test_skipped_trace）**：
1. `result.provider == "tushare"`
2. `result.source_trace == ["ud_materialized(skipped: force_refresh)", "cache(skipped: force_refresh)", "tushare(ok)"]` — 使用 `==` 精确断言完整 trace（不含 `ta_cn_internal` 条目）
3. `e2e_ta_cn_with_kline.call_log == []`（TA-CN adapter 未被调用）
4. trace 中不含 `ud_materialized(ok)` 和 `ud_materialized(miss)`（间接证明 LocalMongoAdapter.get() 未被调用——force_refresh 守卫返回 None 不调底层 get()）
5. trace 中不含 `cache(ok)` 和 `cache(miss)`（间接证明 CacheManager.get() 未被调用）

**断言（test_write_unchanged）**：
1. 查询后：`LocalMongoAdapter.get()` 返回新数据（来自 tushare payload）
2. `CacheManager.get()` 返回新数据

**断言（test_subsequent_hit）**：
1. 再次 `router.query(... force_refresh=False)` → `provider == "ud_materialized"` 或 `"tushare"`（取决于物化 hit 时间窗口）

#### 3.5.6 场景 6：index 双路径（E2E-601~604）

**能力映射确认**：

| 集合 | Router capability | TA-CN adapter 方法 | 状态 |
|---|---|---|---|
| `index_basic_info` | `metadata.index_list` | `get_index_list` | ✅ 已映射 |
| `index_basic_info` | `metadata.index_info` | `get_index_info` | ✅ 已映射 |
| `index_daily_quotes` | `market_data.index_daily` | `get_index_daily_bars` | ✅ 已映射 |
| `stock_sector_info` | **无对应 capability** | `get_stock_sector_info` 未在 map 中 | ✅ 已关闭（Pascal 确认 Path A） |

**OQ-01 处理结论（Pascal 已确认 Path A）**：

> **`stock_sector_info` 不在 Phase 1C 场景 6 范围内**。原因：
> 1. Router 的 `_TA_CN_CAPABILITY_METHOD_MAP` 无对应 capability entry
> 2. `FakeTA_CNAdapter`（conftest.py）未实现 `get_stock_sector_info` 方法
> 3. 新增 capability entry 需修改生产 Router 代码，违反 Phase 1C "不修改生产代码" 原则
> 4. `stock_sector_info` 的 Phase 1A adapter 测试（`test_ta_cn_mongo_adapter.py`）已是本层的独立性覆盖
>
> `stock_sector_info` 并非功能删除：现有的 Phase 1A `SectorService` + TA-CN adapter direct read 保持不变。其未来 Router 统一入口与 external fallback 需另开独立阶段，先做公共 capability 设计、查询粒度、分类体系与 Provider 等价性验证后再实施（具体阶段编号不预设）。**不得写成"留到 Phase 2 Audit/Quality"**。

**E2E-601：index_basic_info 内部命中**
```python
# TA-CN adapter 含 index_basic_info 数据
adapter = FakeTA_CNAdapter(collections={
    "index_basic_info": [{"symbol": "000300", "full_symbol": "000300.SH", "name": "沪深300"}]
})
router = DataRouter(registry, ta_cn_adapter=adapter, ...)
result = router.query("metadata", "index_list", cn_maotai)
assert result.provider == "ta_cn_internal"
assert fresh_registry.get("tushare").call_log == []  # 外部未被调用
```

**E2E-602：index_basic_info 外部兜底**
```python
adapter = FakeTA_CNAdapter(collections={})  # 空 → 返回 empty
result = router.query("metadata", "index_list", cn_maotai)
assert result.provider == "tushare"  # 外部兜底
assert len(result.data) >= 1  # 非空
assert result.data[0].get("symbol") == "000300"  # 业务字段最小断言
assert result.data[0].get("name") == "沪深300"
```

**E2E-604：index_daily_quotes 外部兜底**
```python
adapter = FakeTA_CNAdapter(collections={})  # 空
result = router.query("market_data", "index_daily", cn_maotai)
assert result.provider == "tushare"
assert len(result.data) >= 1
assert result.data[0].get("sector_code") == "000300"
assert result.data[0].get("close") > 0
```

**E2E-603：index_daily_quotes 内部命中**（断言与 E2E-601 类似，验证 `provider="ta_cn_internal"` 和 `call_log==[]`）

#### 3.5.7 场景 7：覆盖率门禁（E2E-701/702）

**断言（test_coverage_report_runs）**：
```python
import subprocess
import sys

def test_coverage_report_runs():
    """Verify coverage CLI can produce a report for unified_data module."""
    result = subprocess.run(
        [sys.executable, "-m", "coverage", "run", "-m", "pytest",
         "tests/data/unified_data/", "-q"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
        timeout=30,
    )
    assert result.returncode == 0, f"coverage run failed: {result.stderr}"

    result2 = subprocess.run(
        [sys.executable, "-m", "coverage", "report",
         "--include=skills/data/unified_data/*", "--fail-under=60"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
        timeout=15,
    )
    # 线覆盖率 ≥ 60% 为硬门禁：exit 非零 = 阻塞 1C Closeout
    assert result2.returncode == 0, (
        f"coverage --fail-under=60 failed (rc={result2.returncode}). "
        f"缺口分析:\n{result2.stderr}"
    )
```

**覆盖率缺口填补策略**：
- 运行 `coverage report -m --include="skills/data/unified_data/*"` 查看缺失行
- 优先补场景 1-6 涉及模块的逻辑分支（`router.py` 的 Step 1/2/3/4 分叉、`cache_manager.py` get/put 分支）
- 尽量补分支覆盖，其次行覆盖
- 忽略 try/except 的纯异常路径和 `__init__.py` 的条件 import

### 3.6 DataResult.success 空 DataFrame 修复（OQ-03）

**2026-07-15 实测结果**：`.venv/bin/python -m pytest` 下全部 358 test passed，`test_dataframe_empty_attribute` 通过（freshness == "empty"）。

**修复决策**：
- T3 Implement 环境若同 `.venv` → 无需修改任何代码
- T3 Implement 环境若另起 env（如 `conda` / 系统 python）→ 先确认 pytest 使用 .venv 的 python
- 若 `_is_empty_payload()` 检测失败：问题在 `getattr(data, "empty", None)` 对 `pd.DataFrame()` 返回非 bool，或 pandas 版本差异。修复路径：在 `_is_empty_payload` 中加 `try: import pandas as pd; if isinstance(data, pd.DataFrame): return data.empty` 显式分支。

**回归断言**：`test_dataframe_empty_attribute` 作为独立测试方法保留在 `test_models.py` 中，新增到 `TestE2EScene?` 不属于端到端场景但作为回归基线。若 T3 修改了工厂逻辑，全量跑 `pytest tests/data/unified_data -q` 确认无回归。

### 3.7 错误语义矩阵（与 SPEC-03-009 §4.5 一致）

| 场景 | DataResult.provider | DataResult.freshness | source_trace 最后条目 | warnings | 物化/Cache 写入 |
|---|---|---|---|---|---|
| 全 miss + 外部成功 | `"tushare"` | `label(...)` | `tushare(ok)` | `[]` | ✅ |
| Cache hit | 原始 provider | `"cached"` | `cache(ok)` | `[]` | 不写入 |
| Fallback A→B 成功 | `"akshare"` | `label(...)` | `akshare(ok)` | `[]` | ✅ |
| 全失败 | "error" | "empty" | akshare(error: ...)（注：ta_cn_adapter=None 分支，无 ta_cn_internal 条目） | ["all external providers failed"] | 不写入 |
| force_refresh | `"tushare"` | `label(...)` | `tushare(ok)` | `[]` | ✅ |
| TA-CN 内部命中 | `"ta_cn_internal"` | `label(...)` | `ta_cn_internal(ok)` | `[]` | 不写入 |
| TA-CN 内部空 | `"empty"` | `"empty"` | `ta_cn_internal(empty)` | `[]` | 不写入（短接） |

### 3.8 幂等性与隔离

- 每个 TestClass 可独立运行：`pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene1_AllMissExternalSuccess -q`
- 各 TestClass 运行顺序不影响其他类的结果
- 每测试方法通过 fixture 获取独立的 mongomock 数据库 + 空 registry
- 所有 e2e 测试合计应在 10 秒内完成（纯内存，无 I/O）

### 3.9 文件拆分方案（CLAUDE.md ≤300 行约束）

当前 `test_e2e_full_chain.py` 约 993 行，违反 CLAUDE.md:182 的 `每个文件不超过 300 行` 约束。T3 Remediation 必须按以下方案拆分：

#### 3.9.1 拆分原则

- **保留** `test_e2e_full_chain.py` 作为**入口文件/命名空间**（仅 imports + re-exports），不包含测试类定义
- **新建** 5 个文件，每个 ≤ 300 行
- 公共 fixture/constants 抽取到独立文件 `test_e2e_fixtures.py`
- 各场景文件从 `test_e2e_fixtures.py` 导入 fixture，不重复定义
- 每个拆分文件可独立运行：`pytest tests/data/unified_data/test_e2e_scene_4.py -q`

#### 3.9.2 文件划分矩阵

| 文件 | 内容 | 预计行数 | 关键约束 |
|---|---|---|---|
| `test_e2e_full_chain.py` | **入口**（保留）：模块 docstring + import re-exports（`from .test_e2e_scene_1_2_3 import *` 等） | ~30 | 仅 imports，不含测试类定义 |
| `test_e2e_fixtures.py` | constants（KLINE_CAP 等）+ 全部 fixture 定义（`e2e_db`, `e2e_registry`, `e2e_ta_cn_miss`, …）+ `_make_db()` helper | ~260 | ≤ 300 行；不含 TestClass |
| `test_e2e_scene_1_2_3.py` | `TestE2EScene1_AllMissExternalSuccess` + `TestE2EScene2_CacheHit` + `TestE2EScene3_ProviderFallback` | ~230 | ≤ 300 行 |
| `test_e2e_scene_4.py` | `TestE2EScene4_AllFail` | ~110 | ≤ 300 行 |
| `test_e2e_scene_5.py` | `TestE2EScene5_ForceRefresh`（含 `_build_router` helper） | ~220 | ≤ 300 行 |
| `test_e2e_scene_6_7.py` | `TestE2EScene6_IndexDualPath` + `TestE2EScene7_CoverageGate` | ~180 | ≤ 300 行 |

#### 3.9.3 验证方法

```bash
# 各文件独立可运行
wc -l tests/data/unified_data/test_e2e_*.py           # 每文件 ≤ 300
pytest tests/data/unified_data/test_e2e_scene_4.py -q --tb=short    # exit 0
pytest tests/data/unified_data/test_e2e_scene_5.py -q --tb=short    # exit 0

# 全量测试无回归
pytest tests/data/unified_data -q --tb=short          # 374+ passed
```

#### 3.9.4 注意事项

- 从 `test_e2e_full_chain.py` 迁移到拆分文件时，`PROJECT_ROOT` 定义保留在 `test_e2e_fixtures.py` 中
- 拆分后入口模块为 `test_e2e_full_chain.py`（实际为空壳），`grep -c "class TestE2E"` 应仍返回 7（从子模块 import 后）
- 不建议将 fixture 移入 `conftest.py`——e2e fixture 是 Phase 1C 私有（其他测试文件不需要），在 `conftest.py` 中引入会增加所有 unified_data 测试的 fixture 加载开销

---

## 4. 数据模型

Phase 1C 不新增持久化数据模型。所有数据模型来自：
- Phase 0：`SecurityId` / `DataResult` / `Capability` / `DataResult.success/error`
- 1B-B：`LocalMongoAdapter` / `CacheManager` 文档信封（`03_data_ud_*` / `03_data_ud_cache_*`）

### 4.1 测试中使用的 capability 常量

```python
KLINE_CAP = "market_data.kline_daily"
INDEX_LIST_CAP = "metadata.index_list"
INDEX_DAILY_CAP = "market_data.index_daily"
```

---

## 5. 向后兼容

- 端到端测试**不修改** conftest.py 中的 FakeProvider / FakeTA_CNAdapter 定义
- 端到端测试**不修改** 1B-B 已有测试文件或 fixture
- `DataResult.success()` 工厂的空 payload 检测逻辑已就位，不做额外签名修改
- 若 T3 发现需要修改 `test_models.py` 中的断言（如 `test_dataframe_empty_attribute` 期望值），不破坏已有测试语义

---

## 6. 实现约束

### 6.1 改动范围

| 可修改（T3 Implement 初始） | 可修改（T3 Remediation 追加） | 不可修改 |
|---|---|---|
| `tests/data/unified_data/test_e2e_full_chain.py`（新建） | `test_e2e_full_chain.py`（重写为入口） | `skills/data/unified_data/router.py` |
| `tests/data/unified_data/test_models.py`（最小修复，如需要） | `test_e2e_fixtures.py`（新增） | `skills/data/unified_data/cache_manager.py` |
| `skills/data/unified_data/models/__init__.py`（仅 _is_empty_payload 修复） | `test_e2e_scene_1_2_3.py`（新增） | `skills/data/unified_data/local_mongo_adapter.py` |
| — | `test_e2e_scene_4.py`（新增） | `skills/data/unified_data/client.py` |
| — | `test_e2e_scene_5.py`（新增） | `skills/data/unified_data/freshness.py` |
| — | `test_e2e_scene_6_7.py`（新增） | `skills/data/unified_data/config.py` |
| — | — | `skills/data/unified_data/registry.py` |
| — | — | `tests/data/unified_data/conftest.py` |
| — | — | `tests/data/unified_data/test_router_persistence.py` |
| — | — | `skills/apps/TradingAgents-CN/**`（TA-CN 子项目） |
| — | — | 生产 MongoDB DDL / index / schema |

### 6.2 禁止事项

- ❌ 不新增第三方 pip 依赖（coverage 若缺失则视为验证失败，不允许 `pip install coverage`）
- ❌ 不新建 MongoDB collection / index / schema validator
- ❌ 不做真实 MongoDB 连接或外部 API 调用
- ❌ 不修改 TA-CN / DSA / Argus / portfolio / task_center 代码
- ❌ 不修改 RFC/SPEC/Design 文档模板
- ❌ 不触碰 cron / systemd / 生产 rollout
- ❌ 不读取或输出任何凭据
- ❌ 不引入 time.sleep（过期场景通过构造 expires_at 过去时间来模拟）
- ❌ 不修改 `_TA_CN_CAPABILITY_METHOD_MAP`（sector mapping 已由 Pascal 确认不纳入本阶段）

### 6.3 性能约束

- 全部 16 个端到端测试合计 ≤ 10 秒（mongomock + fake provider，无 I/O）
- 覆盖率报告运行 ≤ 30 秒

### 6.4 语言约束

- 测试方法名用英文（遵循现有惯例 `test_*`）
- 文档字符串用英文
- 注释可用中文辅助
- T3 Implement git commit 用中文

---

## 7. 验收标准

| 编号 | 验收项 | 验证命令 | 期望 |
|---|---|---|---|
| A-001 | test_e2e_full_chain.py 存在 | `ls -la tests/data/unified_data/test_e2e_full_chain.py` | 文件存在，> 300 行 |
| A-002 | 7 个 TestClass | `grep -c "class TestE2E" tests/data/unified_data/test_e2e_full_chain.py` | 7 |
| A-003 | 场景 1 全 PASS | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene1_AllMissExternalSuccess -q --tb=short` | exit 0 |
| A-004 | 场景 2 全 PASS | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene2_CacheHit -q --tb=short` | exit 0 |
| A-005 | 场景 3 全 PASS | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene3_ProviderFallback -q --tb=short` | exit 0 |
| A-006 | 场景 4 全 PASS | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene4_AllFail -q --tb=short` | exit 0 |
| A-007 | 场景 5 全 PASS | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene5_ForceRefresh -q --tb=short` | exit 0 |
| A-008 | 场景 6 全 PASS | `pytest tests/data/unified_data/test_e2e_full_chain.py::TestE2EScene6_IndexDualPath -q --tb=short` | exit 0 |
| A-009 | 场景 7 覆盖率报告可运行 | `coverage run -m pytest tests/data/unified_data/test_e2e_full_chain.py -q && coverage report --include="skills/data/unified_data/*"` | exit 0 |
| A-010 | 全量 374+ 测试通过 | `pytest tests/data/unified_data -q --tb=long` | exit 0，无 FAILED |
| A-011 | git diff 无空白错误 | `git diff --check` | exit 0 |
| A-012 | 零真实外部调用 | grep 确认所有 import 不含真实 provider/Tushare/AKShare/MongoClient(host=) | 0 matches |

### 7.1 不可自动化的验证项

| 项 | 原因 | 替代方案 |
|---|---|---|
| fixture 数据合理性（payload 字段业务意义） | 需人工判断 | T3 Implement 阶段人工审核 fixture payload |
| 覆盖率 < 60% 时的缺口分析 | 需动态分析缺口内容 | T4 Verify 阶段运行覆盖率并记录缺口 |

---

## 8. T3 Implement 交接

### 8.1 必须执行

1. **只新建/修改**约定范围内的文件（§6.1）
2. 在 `test_e2e_full_chain.py` 文件顶部声明测试常量
3. 每个 TestClass 内部使用独立的 fixture 获取 mongomock 数据库 + 空 Registry
4. 外部 provider 的 payload 使用**不同值**（例如 tushare=close [1500,1510]，akshare=close [2500,2510]）以便断言区分数据来源
5. 先确认 `coverage` 命令是否可用；不可用时视为验证失败（不允许 `pip install coverage`）
6. 所有测试通过后运行 `git diff --check`

### 8.2 可自行判断

1. `PROJECT_ROOT` 常量的定义方式（`os.path.dirname(...)` 或 `pathlib.Path`）
2. `test_coverage_report_runs` 中 `subprocess.run` 的 cwd 路径
3. 测试间共享的 `KLINE_CAP` 等常量放在模块级还是 conftest 级别
4. `_build_router` helper 函数的实现细节（参考试卷 `test_router_persistence.py` 的 `_build_router`）

### 8.3 遇到以下情况退回 Principal

1. 发现需要修改 §6.1 "不可修改" 列表中的文件
2. 发现 force_refresh trace 行为与 §3.5.5 描述不一致（如 `ta_cn_internal(skipped: force_refresh)` 条目缺失或格式不同）
3. 发现 mongomock 不支持某个 pymongo 操作导致关键断言无法实现
4. 发现 `coverage` 安装后与项目 Python 版本不兼容
5. 发现现有 1B-B 测试因新增 test_e2e_full_chain.py 而失败

### 8.4 Open Issues 传递

| OQ | 状态 | T3 Implement 需要做什么 |
|---|---|---|
| OQ-01（stock_sector_info mapping） | ✅ **已关闭（Pascal 确认 Path A）** | 只覆盖 index（E2E-601~604），不覆盖 sector。Pascal 已确认：`stock_sector_info` 的 Router E2E 不在 1C 范围。 |
| OQ-02（coverage CLI 可用性） | ✅ **已关闭** | `.venv/bin/python -m coverage` 可用（7.15.1）。不允许 `pip install coverage`。 |
| OQ-03（empty DataFrame freshness） | ✅ **已验证通过**（2026-07-15 .venv） | T3 环境先运行 `test_dataframe_empty_attribute` 确认通过。若仍失败，在 `_is_empty_payload` 中加显式 pandas isinstance 分支 |

---

## 9. 风险与应对

| 风险 | 概率 | 影响 | 应对 | 降级 |
|---|---|---|---|---|
| force_refresh trace 中无 `ta_cn_internal(skipped: force_refresh)` 条目（Pascal 已确认的正确行为：仅 2 条 skipped） | 低 | 低 | 场景 5 的 trace 断言已按 Pascal 确认更新（不含该条目），T3 Implement 按 DESIGN §3.5.5 trace 预期实现。 | 若 router.py 当前实现意外产生了该条目，需修改 router.py（走范围裁决回退 T3）。 |
| coverage 当前线覆盖率已 ≥ 60%，无缺口需补 | 中 | 低 | 场景 7 只验证可运行性；Closeout 记录覆盖率值 | — |
| stock_sector_info 在 T3 前新增 capability mapping | 低 | 低 | 已由 Pascal 确认 Path A：不在 1C Router E2E 范围，不新增。 | 无需升级 |
| 现有 1B-B 测试因 mongomock 版本差异或并发冲突失败 | 低 | 高 | T3 先单独运行 1B-B 测试确认基线 | 退回 Principal 分析兼容性 |
| `test_dataframe_empty_attribute` 在不同 Python 环境 pandas 版本下行为不一致 | 低 | 低 | `_is_empty_payload` 加显式 `isinstance(data, pd.DataFrame) and data.empty` 分支 | Closeout 记录环境差异 |

---

## 10. 参考资料

| 文档 | 路径 |
|---|---|
| RFC-03-010 | `docs/rfc/03_data/RFC-03-010-unified-data-phase-1c-e2e-validation.md` |
| SPEC-03-010 | `docs/spec/03_data/SPEC-03-010-unified-data-phase-1c-e2e-validation.md` |
| DESIGN-03-009 | `docs/design/03_data/DESIGN-03-009-unified-data-phase-1b-persistence-plane.md` |
| DESIGN-03-008 | `docs/design/03_data/DESIGN-03-008-unified-data-phase-1b-query-plane.md` |
| DESIGN-03-007 | `docs/design/03_data/DESIGN-03-007-unified-data-layer.md` |
| SPEC-03-009 | `docs/spec/03_data/SPEC-03-009-unified-data-phase-1b-persistence-plane.md` |
| unified_data SKILL.md | `skills/data/unified_data/SKILL.md` |
| AI Coding Pipeline SKILL.md | `skills/infra/ai-coding-pipeline/SKILL.md` |
| 现有测试参考（_build_router 模式） | `tests/data/unified_data/test_router_persistence.py` L69-92 |

---

## 版本记录

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
|| V0.3 | 2026-07-15 | T2.6 Review Remediation：① all-fail 语义收敛（§3.5.4）；② 精确断言矩阵（§3.2 Assertion Style 列）；③ 方法名飘移修正（test_index_list_*）；④ §3.9 文件拆分方案 + §3.1/§6.1 重构清单同步。 | YQuant-Principal |
|| V0.2 | 2026-07-15 | T2.5 Sector 边界收敛 Amendment：场景 6 改名为 `TestE2EScene6_IndexDualPath`（去 sector 引用）；force_refresh trace 修正——不含 `ta_cn_internal(skipped: force_refresh)`（Pascal 确认）；coverage ≥ 60% 提升为硬门禁（assert + --fail-under=60）；删除 `pip install coverage` 指令（已安装 7.15.1）；OQ-01~OQ-03 全部关闭。 | YQuant-Principal |
|| V0.1 | 2026-07-15 | 初始创建。覆盖 7 场景/16 测试方法的详细设计、fixture 矩阵、时序图、force_refresh 行为确认（§3.5.5）、OQ-01 sector 暂不覆盖决策、OQ-03 实测通过。 | YQuant-Principal |
