# DESIGN-03-014: Unified Data Phase 3 — 受控持久化扩展详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-21 |
| 最后更新 | 2026-07-21（V0.5 Design Correction — 闭合 T2.7 REVISE 的 MINOR-N2：§4.5/§5.2 security_id 签名统一为 optional，匹配 SPEC §5.1） |
| 版本号 | V0.5 |
| 来源 RFC | RFC-03-014（Phase 3 持久化扩展） |
| 来源 SPEC | SPEC-03-014（Phase 3 持久化扩展契约） |
| 关联 Design | DESIGN-03-007（Unified Data Layer 总体设计，V3.4） |
| 关联 RFC | RFC-03-012（Phase 1D CN 日线真实外部 Provider 激活）、RFC-03-011（Phase 2 质量与审计治理）、RFC-03-013（Phase 1E 情绪最小切片） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约基线）、SPEC-03-008（Phase 1B-A 查询平面）、SPEC-03-013（Phase 1E 情绪最小切片） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

### 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-21 | 初始创建。基于 RFC-03-014 V0.2 + SPEC-03-014 V0.2（均经独立 Review T1.4 APPROVE），给出 P3-A/P3-B/P3-C 三子阶段的精确文件矩阵、数据流图、接口契约、异常分类、测试策略与回滚/停止条件。 | YQuant-Principal |
| V0.2 | 2026-07-21 | **Design Correction（T2.2 REVISE）**。修复 3 个阻断 (B1: query `_materialize()` 基线冲突 / B2: LocalMongoAdapter 键模型不兼容 / B3: refresh 无 PersistenceResult) + 7 个 Major 一致性问题（Router 模式冰结、quality_flags 移除、Freshness 事实修正、northbound security_id 必填、MongoDB-first 约束、STUB_COLUMNS 双定义、Gate 索引增强）。 | YQuant-Principal |
|| V0.3 | 2026-07-21 | **Design Correction（T2.4 实现边界冻结）**。消除 T2.3 独立复审遗留的 1 MAJOR + 1 MINOR 图文歧义：① §2.1 明确 post-Gate `_materialize()` 写入路径经由 P3PersistenceWriter 而非 LocalMongoAdapter（图文一致，与 §0.4/§7.4 对齐）；② §0.4 补充 `UpsertOutcome` dataclass 定义（P3PersistenceWriter.upsert() 返回类型冻结）；③ §2.1 测试验证目标精确化为 P3PersistenceWriter 写入路径。 | YQuant-Principal |
|| V0.4 | 2026-07-21 | **Design Correction（T2.6 消除 T2.5 REVISE 阻断）**。关闭 T2.5 Synthesis 提出的 2 BLOCKING + 1 MAJOR + 4 MINOR 共 7 项 finding：① BLOCKING ① §2.1 l.229 post-Gate `_materialize()` 写入违背只读承诺 → 重写为"查询路径保持只读，写入仅 refresh 路径"；② BLOCKING ② §0.4/§2.1 关于 `_try_materialized()` 的内部冲突 → 采用方案 A（允许最小扩展：追加 capability 参数 + P3PersistenceWriter 注入，显式声明为 query() 编排的唯一例外）；③ MINORs 全数对齐 RFC/SPEC 一致性与措辞。 | YQuant-Principal |
|| V0.5 | 2026-07-21 | **Design Correction（T2.8 闭合 MINOR-N2）**。闭合 T2.7 REVISE 发现的 MINOR-N2：§4.5 l.704（client 层 `security_id: SecurityId | None = None`）与 §5.2 l.842-844（service 层 `security_id: SecurityId` 必填）签名矛盾——采用方案 Y，§5.2 统一为 `security_id: SecurityId | None = None`（匹配 §4.5 与 SPEC §5.1 l.577）。移除"必填/不得 placeholder"措辞，改为"默认 None=市场级，非 None=个股级"。SPEC §5.1 已为 optional 无需修改；RFC 无签名引用无需修改。 | YQuant-Principal |

---

## 0. 现有代码基线（不可变更的事实状态）

本 Design 的所有拟议变动均基于以下已交付的事实状态。任何对「已存在」「不存在」「尚未实现」的误判将直接导致 Design 失效。

### 0.1 已存在的 Phase 3 候选文件

| 路径 | 现实状态 | 说明 |
|---|---|---|
| `models/domain/sector.py` | ✅ 存在。包含 `SectorClassification`（Phase 1A，44 行）——从 `stock_sector_info` 映射的行业/板块分类 | **不包含** `SectorSnapshot`。文件内仅有 `SectorClassification` 一个 class |
| `services/sector_service.py` | ✅ 存在。`SectorService`（Phase 1A，123 行）——3 个 TA-CN MongoDB 只读方法：`get_stock_sector`、`get_stocks_by_sector`、`get_sector_index_bars` | **不包含** `get_sector_snapshot` / `get_sector_ranking` |
| `models/domain/__init__.py` | ✅ 存在。导出 9 个 symbol（DailyBar, IndexDailyBar, RealtimeQuote, FinancialStatement, VALID_STATEMENT_TYPES, IndexInfo, StockInfo, NewsItem, SectorClassification） | **不包含** SectorSnapshot、CapitalFlowRecord、MarketSentimentSnapshot |
| `services/__init__.py` | ✅ 存在。导出 5 个 Service class | **不包含** FlowService、SentimentService |
| `client.py` | ✅ 存在。`UnifiedDataClient` 有 5 个 lazy service 属性（_market_data, _fundamental, _sector, _event, _metadata） | **不包含** `_flow_service`、`_sentiment_service`；**不包含** Phase 3 域方法 |
| `router.py` | ✅ 存在。`DataRouter` 含 1194 行。**关键事实**：Step 4 成功的外部 Provider 结果后，`query()` 在第 679-687 行自动调用 `self._materialize(security_id, domain, operation, params, external_result)`——将成功的外部查询结果自动持久化写入 LocalMongoAdapter + Cache。**这不是 Phase 3 行为，而是当前基线行为** | `_TA_CN_NOT_COVERED` 有 6 项，**无** Phase 3 能力项；`_TA_CN_CAPABILITY_METHOD_MAP` 无 Phase 3 项；`_try_materialized()` 和 `_try_cache()` 签名到位但 LocalMongoAdapter 仍为 None（Phase 1B-B slot） |
| `freshness.py` | ✅ 存在。`FreshnessPolicy` 含 142 行 | `DEFAULT_TTLS` 有 6 域，**无** `flow`/`sector`/`sentiment` 条目 |
| `audit/logger.py` | ✅ 存在。`AuditLogger` 含 213 行 | Phase 2 已交付，noop 当 `mongo_db=None`；**不可在 Phase 3 默认写入路径启用** |
| `cache_manager.py` | ✅ 存在。`CacheManager` 含 262 行 | Phase 1B-B 已交付，使用 `03_data_ud_cache_` 前缀；get/put/invalidate 均为 catch-and-log |
| `providers/akshare.py` | ✅ 存在。`AKShareProvider` 含 359 行，7 个 capability（Phase 1D: kline_daily real，其余 stub） | **无** sector/flow/sentiment capability |
| `providers/_stub_columns.py` | ✅ 存在。`STUB_COLUMNS` 有 15 项 | **无** Phase 3 的 6 项 |
| `providers/__init__.py` | ✅ 存在。含 `STUB_COLUMNS` 孪生定义 | 同上，**无** Phase 3 项 |

### 0.2 不存在的文件（需 Phase 3 新建）

| 路径 | 状态 | 说明 |
|---|---|---|
| `models/domain/flow.py` | ❌ **不存在** | SPEC-03-014 §3.2 要求 `CapitalFlowRecord` domain object |
| `models/domain/sentiment.py` | ❌ **不存在** | SPEC-03-014 §3.3 要求 `MarketSentimentSnapshot` domain object（与 Phase 1E 的 `StockSentimentScore` 同文件） |
| `services/flow_service.py` | ❌ **不存在** | SPEC-03-014 §5.1 要求 `get_capital_flow` / `get_northbound_flow` |
| `services/sentiment_service.py` | ❌ **不存在** | SPEC-03-014 §5.1 要求 `get_market_sentiment` / `get_limit_up_pool` |
| `adapters/p3_persistence_writer.py` | ❌ **不存在** | **新建**：Phase 3 业务集合（按业务唯一键读写）的独立 persistence reader/writer。不复用 `LocalMongoAdapter` 的 `materialized_key` 单文档模型（见 §0.4） |

### 0.3 需修改的现有文件

| 路径 | 修改类型 | 说明 |
|---|---|---|
| `models/domain/sector.py` | 追加 | 追加 `SectorSnapshot` dataclass + `from_dict()` |
| `models/domain/__init__.py` | 追加 | 导出 SectorSnapshot、CapitalFlowRecord、MarketSentimentSnapshot |
| `services/sector_service.py` | 追加 | 追加 `get_sector_snapshot()` / `get_sector_ranking()` |
| `services/__init__.py` | 追加 | 导出 FlowService、SentimentService；追加 wrap 逻辑 |
| `client.py` | 追加 | 追加 `_flow_service` / `_sentiment_service` + 6 个域方法 |
| `router.py` | 追加 | `_TA_CN_NOT_COVERED` 追加 6 项 Phase 3 capability |
| `freshness.py` | 追加 | `DEFAULT_TTLS` 追加 flow=43200 / sector=21600 / sentiment=3600 |
| `providers/akshare.py` | 追加 | capabilities 追加 6 项；`fetch()` 追加 sector/flow/sentiment 分支；`_to_canonical()` 追加 3 条映射路径 |
| `providers/_stub_columns.py` | 追加 | STUB_COLUMNS 追加 6 项 Phase 3 capability |
| `providers/__init__.py` | 追加 | 同上同步 |
| `services/__init__.py` | 追加 | 导入 FlowService、SentimentService |

### 0.4 键模型不兼容性：LocalMongoAdapter vs Phase 3 业务集合

**关键事实（代码基线已存在）**：

- 文件 `local_mongo_adapter.py`（278 行，Phase 1B-B 已交付）**已存在**——不在 `adapters/` 子目录，而在 `skills/data/unified_data/` 根目录。
- `LocalMongoAdapter` 使用单 `materialized_key`（`SHA256(security_id|domain|operation|params)` 的前 64 字符）作为 MongoDB 文档的唯一键，适用于参数组合不可穷举的通用缓存场景。
- LocalMongoAdapter 的 `get()`/`put()` 接收 `(security_id, domain, operation, params, result)` 五元组，无法用业务唯一键（如 `{market, sector_code, snapshot_date}`）直接查询——它只能用 `materialized_key` 查。
- 「`adapters/` 目录不存在」和「LocalMongoAdapter 尚未作为独立文件实现」**均为不准确**。正确表述：LocalMongoAdapter 存在但**不适用于** Phase 3 按业务键查询/写入的三个集合。

**设计决议**：

Phase 3 的**三个业务集合**（`03_data_ud_market_sector_snapshot`、`03_data_ud_stock_capital_flow`、`03_data_ud_market_sentiment_snapshot`）由独立的 **P3PersistenceWriter**（模块路径 `adapters/p3_persistence_writer.py`，class 名 `P3PersistenceWriter`，**已冻结**）按 RFC/SPEC 定义的三组业务唯一键读写。该组件：

- **不**继承 `LocalMongoAdapter`——不使用 `materialized_key` 模型
- **按业务唯一键**（`{market, sector_code, snapshot_date}` 等）读写
- 使用 `from_dict()` / `asdict()` 序列化/反序列化 Domain Object
- 支持通过业务键 filter 查询（Router Step 2 匹配 `refresh` 写入的记录）
- 与 `LocalMongoAdapter` 共享 `03_data_ud_` 集合前缀空间但**独立代码路径**
- 不扩展现有 `LocalMongoAdapter` 的接口——设计成独立组件，保持两组件接口清晰

**P3PersistenceWriter 最小公开接口（已冻结）**：

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UpsertOutcome:
    """P3PersistenceWriter.upsert() 的返回值。"""

    persisted: int = 0               # 成功 upsert 的记录数
    failed: int = 0                  # 失败记录数
    failed_keys: list[dict] = field(default_factory=list)  # 失败记录的 business key 列表
    errors: list[str] = field(default_factory=list)        # 错误摘要列表


class P3PersistenceWriter:
    def __init__(self, mongo_db): ...

    def get(self, collection: str, filter: dict) -> list[dict]:
        """按业务唯一键 filter 查询。返回 list[dict]，消费方反序列化为 Domain Object。"""

    def upsert(self, collection: str, records: list[dict],
               unique_key: set[str]) -> UpsertOutcome:
        """按 unique_key upsert。返回 UpsertOutcome（persisted, failed, failed_keys, errors）。"""

    def delete(self, collection: str, filter: dict) -> int:
        """按 filter 删除记录（回滚/停止用）。返回删除记录数。"""
```

**Capability → Collection 映射（已冻结）**：

| Capability | 目标 Collection | 业务唯一键 |
|---|---|---|
| `sector.snapshot`, `sector.ranking` | `03_data_ud_market_sector_snapshot` | `{market, sector_code, snapshot_date}` |
| `flow.capital_flow_daily`, `flow.northbound_daily` | `03_data_ud_stock_capital_flow` | `{market, symbol, trade_date}` |
| `sentiment.market_snapshot`, `sentiment.limit_up_pool` | `03_data_ud_market_sentiment_snapshot` | `{market, snapshot_date, snapshot_time}` |

**P3PersistenceWriter 与 Router / refresh 的单一路径关系（已冻结，含方案 A 扩展声明）**：
- **读路径（§2.1 Step 2）**：`DataRouter._try_materialized()` 在 Phase 3 capability 上调用 `P3PersistenceWriter.get()`，**不走** `LocalMongoAdapter.get()`。非 Phase 3 capability 的物化读仍走 `LocalMongoAdapter`。实现方式：`_try_materialized()` 须追加 `capability` 参数 + 可选 `P3PersistenceWriter` 注入引用（见 §2.1「读取路径不变形约束」第三条）。这是 `DataRouter.query()` 主编排逻辑的唯一最小允许扩展。
- **写路径（§2.2 refresh）**：`refresh_xxx()` 方法调用 `P3PersistenceWriter.upsert()`。`DataRouter.query()` Step 4 的自动 `_materialize()` 对 Phase 3 capability **不触发**（参见 §2.1「读取路径不变形约束」）。
- **不共存**：同一 capability 的物化读/写路径要么全走 `LocalMongoAdapter`（非 P3），要么全走 `P3PersistenceWriter`（P3）。不存在同一 capability 混用两条路径的情形。

**不得**把多记录列表塞进 LocalMongoAdapter 的 `materialized_key` 单文档路径。

### 0.5 当前基线 `DataRouter._materialize()` 自动写入行为

**关键事实**：当前 `DataRouter.query()` 在第 679-687 行有一个**非条件性的自动回写**——Step 4 外部 Provider 成功后立即调用：

```python
if external_result.provider not in ("error", "empty"):
    self._materialize(security_id, domain, operation, params, external_result)
```

这意味着任何已注册 + 已激活的 capability 的外部查询都**自动写入** LocalMongoAdapter 和 Cache。此行为对 Phase 1D 的已有 capability（如 `kline_daily`）是正确的，但对 Phase 3 的 6 个新 capability 构成了**未授权的写入路径**——必须规避。

**解决策略**：Phase 3 的 6 个 P3 capability 在对应 Gate 授权前，**不得交付 T3 实现**。即它们在 T2 Design 阶段永不到达 router.py Step 4（参见 §2.1 「读取路径不变形约束」）。只有 Gate 授权后的子阶段才引入对应的 Router 注册和 Step 4 写入。设计层面，该约束通过 §4 的 capability 注册/注销开关 + §2.1 的显式 `_materialize()` skip 实现。

---

## 1. 子阶段范围界定与独立授权

### 1.1 P3-A / P3-B / P3-C 三期方案

遵循 RFC §4.2 / SPEC §0：三子阶段**可独立授权、独立实现、独立验证、独立部署**。推荐执行顺序为 P3-A → P3-B → P3-C（风险递增），但不构成严格前置依赖。若 Pascal 指定其他顺序，以 Pascal 确认为准。一次性部署全部三个集合为 **FAIL**。

| 子阶段 | 持久化集合 | 新增 Capabilities | Provider | 域 | 依赖 |
|---|---|---|---|---|---|
| **P3-A** | `03_data_ud_market_sector_snapshot` | `sector.snapshot`, `sector.ranking` | AKShare | sector | 无（起始阶段推荐） |
| **P3-B** | `03_data_ud_stock_capital_flow` | `flow.capital_flow_daily`, `flow.northbound_daily` | AKShare | flow | 无；建议 P3-A 后 |
| **P3-C** | `03_data_ud_market_sentiment_snapshot` | `sentiment.market_snapshot`, `sentiment.limit_up_pool` | AKShare | sentiment | 无；建议 P3-B 后 |

### 1.2 每子阶段最小交付物

每子阶段必须独立产出以下全部内容，组合成为一个完整的「授权 → 实现 → 验证」单元：

| # | 交付物 | P3-A | P3-B | P3-C |
|---|---|---|---|---|
| 1 | Domain object dataclass + `from_dict()` | SectorSnapshot（在 sector.py 中追加） | CapitalFlowRecord（flow.py 新建） | MarketSentimentSnapshot（sentiment.py 新建） |
| 2 | Domain object 注册到 `models/domain/__init__.py` | ✅ | ✅ | ✅ |
| 3 | STUB_COLUMNS 条目（2 条 capability） | ✅ | ✅ | ✅ |
| 4 | AKShareProvider capabilities 追加（2 项） | ✅ | ✅ | ✅ |
| 5 | AKShareProvider `fetch()` / `_to_canonical()` 新增分支 | ✅ | ✅ | ✅ |
| 6 | `_TA_CN_NOT_COVERED` 追加（2 项） | ✅ | ✅ | ✅ |
|| 7 | FreshnessPolicy `DEFAULT_TTLS` 追加 | —（sector=21600：值已决定，将于 T3 按 §4.4 顺序显式追加） | flow=43200 | sentiment=3600 |
| 8 | Domain service 方法 | sector_service 追加 | flow_service.py 新建 | sentiment_service.py 新建 |
| 9 | `services/__init__.py` 导出 | —（已有 sector_service） | 追加 FlowService | 追加 SentimentService |
| 10 | `UnifiedDataClient` 域方法（2 个） | get_sector_snapshot / get_sector_ranking | get_capital_flow / get_northbound_flow | get_market_sentiment / get_limit_up_pool |
| 11 | `client.py` lazy service 属性 | —（已有 _sector_service） | _flow_service | _sentiment_service |
| 12 | 单元测试文件（≥2 个） | test_sector_snapshot.py + test_sector_service.py | test_capital_flow.py + test_flow_service.py | test_market_sentiment.py + test_sentiment_service.py |
| 13 | Fixture 文件 | sector_fixtures.py | flow_fixtures.py | sentiment_fixtures.py |
| 14 | 唯一键 upsert 验证 | V-GEN-1 | V-GEN-1 | V-GEN-1 |

**重要**：T3 Implement 阶段必须按子阶段逐一提交 PR/commit，不得混合。每子阶段完成单元测试 + fixture + 验收项（A-001~A-015 中对应项）后方可进入该子阶段的 Pascal Gate。

---

## 2. 数据流图与读写职责边界

### 2.1 读取路径（Internal-First，与 DESIGN-03-007 §7.4 一致）

```
消费者调用 UnifiedDataClient.get_sector_snapshot("BK0489")
    │
    ├─ Step 1: TA-CN TA_CNMongoAdapter 查询
    │   [P3-A NOT_COVERED] §2.1 已冻结——sector.snapshot 不可走 TA-CN adapter 推导
    │   [P3-B] flow.capital_flow_daily — 资金流非 TA-CN 既有范围 → 跳过
    │   [P3-C] sentiment.market_snapshot — 市场情绪非 TA-CN 既有范围 → 跳过
    │   命中 → DataResult(provider="ta_cn_internal", freshness="delayed")
    │   未命中/不支持 → 继续
    │
    ├─ Step 2: P3PersistenceWriter → 03_data_ud_* 业务集合（按业务唯一键查询）
    │   [P3-A] 查询 03_data_ud_market_sector_snapshot
    │   [P3-B] 查询 03_data_ud_stock_capital_flow
    │   [P3-C] 查询 03_data_ud_market_sentiment_snapshot
    │   命中 + 未过期 → DataResult(provider="ud_p3_persisted", freshness="cached")
    │   未命中 → 继续
    │
    ├─ Step 3: CacheManager.get() → 03_data_ud_cache_*
    │   [统一] 查询对应 capability 的 cache 集合
    │   命中 + 未过期 → DataResult(freshness="cached")
    │   未命中 → 继续
    │
    └─ Step 4: AKShareProvider.fetch(domain, operation, ...)
           成功 → DataResult(provider="akshare", freshness="delayed")
           （**不写入物化集合**、**不写入 Cache**）
```

**读取路径不变形约束**：
- `DataRouter.query()` **对非 Phase 3 的已有 capability**（如 `kline_daily`）：保持当前基线行为不变——Step 4 成功后自动调用 `_materialize()` 写入 LocalMongoAdapter + Cache（router.py 第 679-687 行）。这**不是 Phase 3 引入的新行为**，无需修改现有代码。
- **对 Phase 3 的 6 个 P3 capability**（`sector.snapshot`、`sector.ranking`、`flow.capital_flow_daily`、`flow.northbound_daily`、`sentiment.market_snapshot`、`sentiment.limit_up_pool`）：T3 Implement 在对应 Gate 授权前**不得**将这些 capability 注册到 Router/AKShareProvider。因此它们在未授权状态下永不进入 Step 4，自然不触发 `_materialize()`。**Gate 授权后**，Step 4 成功获取外部数据后仍然**不触发** `_materialize()`——查询路径保持全程只读（与 RFC §4.4 / SPEC §4.bis.2 一致）。所有写入仅通过显式 refresh 路径（§2.2）进行。不依赖运行时的 `force_refresh` 等条件判断来跳过写入（`force_refresh` 不是普通 query 的正确语义）。
- `_try_materialized()` 和 `_try_cache()` 的逻辑已存在于 router.py（V3.4 基线）。Phase 3 采用**方案 A**——允许对 `_try_materialized()` 做最小扩展：追加 `capability` 参数 + 可选 `P3PersistenceWriter` 注入引用。注入后，P3 capability 在该方法内路由到 `P3PersistenceWriter.get()`，非 P3 capability 保留原 `LocalMongoAdapter.get()` 路径。这是 `DataRouter.query()` 主编排逻辑的唯一可接受改动，显式声明为 V0.4 的单一例外。`P3PersistenceWriter` 未注入时降级为仅 `LocalMongoAdapter` 路径（对非 P3 capability 行为不变）。
- Step 1 对 P3-B/P3-C 的跳过行为通过 `_TA_CN_NOT_COVERED` 注册自动实现（O(1) 判断，router.py 第 456-457 行）。P3-A 的 `sector.snapshot` 同样注册到 `_TA_CN_NOT_COVERED`——不可走 TA-CN adapter 推导。
- **离线测试验证**：在未授权状态下通过注册测试 provider 调用 `router.query("sector", "snapshot", ...)`，验证 `source_trace` 中不包含 `"ud_materialized"` 或 `"cache"` 条目（即 `_materialize()` 未被触发）。Gate 授权后再次测试，确认 `refresh_xxx()` 路径通过 P3PersistenceWriter 正确写入 `03_data_ud_*` 业务集合，且标准 query 路径的 `source_trace` 仍无 `"ud_materialized"` 条目。

### 2.2 写入路径（仅显式 refresh——受控 Gate）

```
外部触发器（手动 Python 调用 / CLI / 未来 Task Center Job）
    │
    ▼
Domain Service.refresh_xxx() 方法
    │
    ├─ 1. AKShareProvider.fetch(domain, operation, ...)  ← Gate G-A-2/G-B-2/G-C-2
    │      成功 → 继续
    │      失败 → 返回 PersistenceResult（failure status + 错误摘要），不写物化
    │
    ├─ 2. P3PersistenceWriter.upsert(
    │       collection="03_data_ud_*",
    │       filter={business_unique_key},
    │       records=[...],               ← list[DomainObject]，非单文档
    │   )                                ← Gate G-A-1/G-B-1/G-C-1
    │      全部成功 → 继续
    │      部分失败 → 返回 PersistenceResult（partial_failure + failed 记录列表 + 错误摘要）
    │      全部失败 → 返回 PersistenceResult（failure + 错误摘要），不写 Cache
    │
    ├─ 3. CacheManager.put(key, value)
    │      成功 → 更新 Query Cache
    │      失败 → catch-and-log，**不阻断**（Cache 写入失败不阻断 refresh 整体成功）
    │
    └─ 4. **不写入 AuditLogger**（Phase 2 默认关闭；预留 try-pass 扩展点）
        **不写入 QualitySummary**（QualitySummary 仍冻结）
```

**写入路径关键约束**：
1. refresh 方法仅可通过 **显式调用** 触发。`DataRouter.query()` 不会隐式触发 refresh。`UnifiedDataClient` 的标准域方法（`get_*`）不会隐式触发 refresh。
2. refresh 方法必须有独立的能力注册/取消注册开关（见 §4.1），在未通过 Pascal Gate 前不会被调用路径执行。
3. P3PersistenceWriter.upsert() 的 collection 名称和业务唯一键必须精确匹配 SPEC §4.bis.1 定义，**不可硬编码**——必须通过参数或配置传入。
4. CacheManager.put() 在 refresh 路径中为幂等操作，失败不阻断 refresh。
5. **P3PersistenceWriter.upsert() 必须返回 `PersistenceResult`，而非 catch-and-log 静默吞掉失败**。部分失败必须明确返回 partial_failure 状态和失败记录列表（见 §5.4 `PersistenceResult` 定义）。
6. refresh 方法整体返回值也是 `PersistenceResult`——消费方通过 `overall_status` 字段判断写入是否全部成功/部分失败/全部失败。**不得返回 `DataResult`**（`DataResult` 的 `succeeded` / `is_empty` 语义只对读查询有意义）。
7. **MongoDB-first**：Phase 3 的持久化层仅 MongoDB。SQLite 不是 Phase 3 的运行时可选项——仅用于 legacy 数据迁移/离线分析/测试 mock。严禁 Phase 3 生产代码向 SQLite 写入。
8. **Cache materialization 禁写默认**：`CacheManager.put()` 在 `DataRouter.query()` 路径中默认关闭（§2.1）。仅在显式 refresh 路径中，且对应 Cache Gate（非独立 Gate——与对应子阶段的 G-*-1 绑定）授权后方可启用。
9. 所有 collection/index DDL/DML、canary、cron 均通过对应子阶段 Gate 逐项授权（见 §12）。Gate 未授权前，T3 不得创建集合、索引或执行任何数据定义操作。

### 2.3 空数据/失败写入处理

| 场景 | 行为 |
|---|---|
| Provider fetch 成功但返回空数据 | 不写入物化集合，不写入 Cache；返回 `PersistenceResult(status="skip_empty", records_attempted=0, records_persisted=0)` |
| Provider 不可用/请求失败 | 返回 `PersistenceResult(status="failure", error=...)`；不写入物化集合 |
| 部分记录 MongoDB 写入失败 | 返回 `PersistenceResult(status="partial_failure", records_persisted=N, records_failed=M, failed_keys=[...], errors=[...])`；已写入记录不删除（无可信回滚——见 §10.3） |
| 全部记录 MongoDB 写入失败 | 返回 `PersistenceResult(status="failure", records_persisted=0, records_failed=N, error=...)`；不写 Cache |
| 北向字段对非标的不可用 | 对应字段为 None 正常写入 not null 字段。该场景不属于「失败」——属于「部分字段不可用」，记录仍然写入 |

---

## 3. Domain Object 精确规范

### 3.1 SectorSnapshot（P3-A）

**文件位置**：`models/domain/sector.py` 中追加（现有 SectorClassification 之后）。

**Python dataclass**：

```python
@dataclass
class SectorSnapshot:
    """板块/行业快照（Phase 3 P3-A）。

    每日各板块的聚合快照。每条记录表示一个板块在某交易日收盘后的快照数据。
    消费方可通过 sector.snapshot（单板块）和 sector.ranking（当日排名）获取。

    本数据为辅助研究数据，不构成交易指令或投资建议。
    """
    sector_code: str                           # (必填) 板块代码，如 "BK0489"
    sector_name: str                           # (必填) 板块名称，如 "白酒"
    sector_type: str                           # (必填) 板块类型：industry / concept / region / style
    snapshot_date: str                         # (必填) 快照日期，格式 "YYYY-MM-DD"
    market: str = "CN"                         # (必填) 市场
    provider: str = ""                         # (必填) 数据来源，如 "akshare"

    # 排名与涨跌
    rank: int | None = None                    # [可选] 当日涨幅排名（1=涨幅最高）
    pct_chg: float | None = None               # [可选] 板块涨跌幅 %（如 2.35）

    # 领涨信息
    leading_stock: str | None = None           # [可选] 领涨股代码（如 "600519"）
    leading_stock_name: str | None = None      # [可选] 领涨股名称
    leading_pct_chg: float | None = None       # [可选] 领涨股涨幅 %

    # 涨跌家数
    advance_count: int = 0                     # 上涨家数
    decline_count: int = 0                     # 下跌家数
    total_count: int = 0                       # 成分股总数

    # 资金流与量价
    turnover_rate: float | None = None         # [可选] 板块换手率 %
    main_net_inflow: float | None = None       # [可选] 主力净流入（元）

    # 元数据
    members: list[str] | None = None           # [可选] 成分股代码列表（用于离线分析，非核心查询字段）
    fetched_at: str | None = None              # [可选] 数据获取时间，ISO-8601
    raw_payload: dict | None = None            # [可选] 原始 AKShare 返回（调试/审计用，不用于生产查询路径）

    @classmethod
    def from_dict(cls, d: dict) -> "SectorSnapshot":
        """从字典构造，缺失字段填 None。松弛映射，不抛 KeyError。"""
        return cls(
            sector_code=str(d.get("sector_code", "")),
            sector_name=str(d.get("sector_name", "")),
            sector_type=str(d.get("sector_type", "")),
            snapshot_date=str(d.get("snapshot_date", "")),
            market=str(d.get("market", "CN")),
            provider=str(d.get("provider", "")),
            rank=d.get("rank"),
            pct_chg=d.get("pct_chg"),
            leading_stock=d.get("leading_stock"),
            leading_stock_name=d.get("leading_stock_name"),
            leading_pct_chg=d.get("leading_pct_chg"),
            advance_count=d.get("advance_count", 0) or 0,
            decline_count=d.get("decline_count", 0) or 0,
            total_count=d.get("total_count", 0) or 0,
            turnover_rate=d.get("turnover_rate"),
            main_net_inflow=d.get("main_net_inflow"),
            members=d.get("members"),
            fetched_at=d.get("fetched_at"),
            raw_payload=d.get("raw_payload"),
        )
```

**字段语义与约定**：

| 字段 | 约束 | 说明 |
|---|---|---|
| `sector_code` | 非空，最大 32 字符 | 东方财富板块代码，如 `BK0489` |
| `sector_type` | 枚举值：industry/concept/region/style | 行业/概念/地域/风格 |
| `rank` | 正整数，1=最高 | 若板块指数不可比则 None |
| `pct_chg` | float，无边界约束 | 板块指数当日涨跌幅 |
| `advance_count` + `decline_count` | 应 <= `total_count`，但不强校验 | 由 Provider 数据质量保证 |
| `members` | 最大 1000 个代码 | 长列表主要用于离线分析 |

**查询边界**：
- 主查询维度：`(sector_code, snapshot_date)` 或 `(snapshot_date, sector_type)` 或 `(snapshot_date)` 按 rank 排序
- 禁止在 `members` 字段上建多键索引（数组字段不用于查询条件）
- 禁止在 `raw_payload` 字段上建索引

**MongoDB 唯一键**：`{market, sector_code, snapshot_date}`
**MongoDB 索引建议**：
- `{sector_code: 1, snapshot_date: -1}` — 按板块查询时序
- `{snapshot_date: -1}` — 按日查询全部板块
- `{sector_type: 1, snapshot_date: -1}` — 按板块类型 + 日期排序

### 3.2 CapitalFlowRecord（P3-B）

**文件位置**：`models/domain/flow.py`（新建文件，Phase 3 首次使用该文件）。

```python
@dataclass
class CapitalFlowRecord:
    """个股资金流记录（Phase 3 P3-B）。

    每条记录表示个股在某交易日的资金流向数据。
    消费方可通过 flow.capital_flow_daily（个股）和 flow.northbound_daily（北向资金-个股级）获取。

    本数据为辅助研究数据，不构成交易指令或投资建议。

    record_scope 说明：
    - flow.capital_flow_daily 查询填充全部资金流字段（主力/大单/中单/小单/北向/融资融券）。
    - flow.northbound_daily 查询仅填充 northbound_* 字段（symbol/market/trade_date 必有，其余资金流字段为空）。
    两者共享同一集合 `03_data_ud_stock_capital_flow` 和同一 domain object，但查询时填充的字段子集不同。
    """
    symbol: str                              # (必填) 标的代码，如 "600519"
    market: str                              # (必填) 市场，如 "CN"
    trade_date: str                          # (必填) 交易日，格式 "YYYY-MM-DD"

    # 资金流核心字段
    main_net_inflow: float | None = None     # [可选] 主力净流入（元）；正=净流入，负=净流出
    super_large_net_inflow: float | None = None  # [可选] 超大单净流入（元）
    large_net_inflow: float | None = None    # [可选] 大单净流入（元）
    medium_net_inflow: float | None = None   # [可选] 中单净流入（元）
    small_net_inflow: float | None = None    # [可选] 小单净流入（元）
    main_net_inflow_ratio: float | None = None  # [可选] 主力净流入占比 %（如 8.5）

    # 北向资金（仅沪/深港通标的）
    northbound_net_inflow: float | None = None   # [可选] 北向净买入（元）
    northbound_hold_shares: float | None = None  # [可选] 北向持股数（股）
    northbound_hold_ratio: float | None = None   # [可选] 北向持股比例 %

    # 融资融券
    margin_buy: float | None = None              # [可选] 融资买入额（元）
    margin_sell: float | None = None             # [可选] 融券卖出额（元）
    margin_balance: float | None = None          # [可选] 融资余额（元）

    # 元数据
    fetched_at: str | None = None              # [可选] 数据获取时间，ISO-8601
    provider: str = ""                         # (必填) 数据来源，如 "akshare"
```

**字段语义与约定**：

| 字段 | 约束 | 说明 |
|---|---|---|
| `main_net_inflow` | 正=净流入，负=净流出 | 通常为超大单+大单净流入之和 |
| `super_large_net_inflow` | 同上 | ≥500 万元（超大单阈值） |
| `large_net_inflow` | 同上 | ≥100 万且 < 500 万元（大单阈值） |
| `medium_net_inflow` | 同上 | ≥20 万且 < 100 万元（中单阈值） |
| `small_net_inflow` | 同上 | < 20 万元（小单阈值） |
| `northbound_*` | 非沪深港通标的返回 None | [待验证] |
| `margin_*` | 融资融券标的返回数值；非标返回 None | [待验证] |

**资金流符号约定**：所有 `*_net_inflow` 字段统一符号约定：**正值 = 净流入（资金买入）**，**负值 = 净流出（资金卖出）**。

**禁止字段**：本 domain object **不包含** `raw_payload` 字段——资金流数据量大（全市场日均数千条），不宜携带原始 payload。

**MongoDB 唯一键**：`{market, symbol, trade_date}`
**MongoDB 索引建议**：
- `{symbol: 1, trade_date: -1}` — 按个股查询时序
- `{trade_date: -1}` — 按日查询全市场资金流

### 3.3 MarketSentimentSnapshot（P3-C）

**文件位置**：`models/domain/sentiment.py`（新建文件，Phase 3 追加；Phase 1E 的 `StockSentimentScore` 同文件——当前 Phase 1E 为计划态契约，此处仅占位，不实现 `StockSentimentScore`）。

```python
@dataclass
class MarketSentimentSnapshot:
    """市场情绪快照（Phase 3 P3-C）。

    每条记录表示全市场在某观测时点的情绪/温度快照数据。
    消费方可通过 sentiment.market_snapshot（市场快照）和 sentiment.limit_up_pool（涨停池）获取。

    本数据为辅助研究数据，不构成交易指令或投资建议。
    """
    snapshot_date: str                        # (必填) 快照日期，格式 "YYYY-MM-DD"
    snapshot_time: str                        # (必填) 快照时间，24h 格式如 "15:00:00" 或 "close"
    market: str = "CN"                        # (必填) 市场

    # 涨跌停数据
    limit_up_count: int = 0                   # 涨停家数（含 ST）
    limit_down_count: int = 0                 # 跌停家数（含 ST）
    limit_up_count_ex_st: int | None = None   # [可选] 涨停家数（不含 ST）
    limit_down_count_ex_st: int | None = None # [可选] 跌停家数（不含 ST）

    # 全市场涨跌数据
    advance_count: int = 0                    # 全市场上涨家数
    decline_count: int = 0                    # 全市场下跌家数
    flat_count: int = 0                       # 平盘家数
    total_listed_count: int | None = None     # [可选] 全市场上市公司总数

    # 指数与温度
    market_temperature: float | None = None   # [可选] 市场温度 0-100（基于多指标合成）
    total_turnover: float | None = None       # [可选] 全市场成交额（元）

    # 热门概念与连板
    hot_concepts: list[str] | None = None     # [可选] 当日热门概念列表
    continuous_limit_up: list[dict] | None = None  # [可选] 连板股票：[{"symbol":..., "days": N, "reason":...}]
    max_continuous_days: int | None = None    # [可选] 当日最大连板天数

    # 北向与额外资
    northbound_net_flow: float | None = None  # [可选] 北向资金净流入（元）

    # 涨停/跌停池
    limit_up_pool: list[str] | None = None    # [可选] 涨停股票代码列表
    limit_down_pool: list[str] | None = None  # [可选] 跌停股票代码列表

    # 元数据
    fetched_at: str | None = None             # [可选] 数据获取时间，ISO-8601
    provider: str = ""                        # (必填) 数据来源，如 "akshare"
    raw_payload: dict | None = None           # [可选] 原始 Provider 返回（调试/审计用）
```

**字段语义与约定**：

| 字段 | 约束 | 说明 |
|---|---|---|
| `snapshot_time` | 格式 "HH:MM:SS" 或 "close" | `close` 表示收盘后快照 |
| `market_temperature` | 0-100 区间 | 合成指标：[假设] 基于涨跌比、涨停强度、成交额等多指标合成 |
| `limit_up_pool` / `limit_down_pool` | 每个列表最大 500 个代码 | 若独立提供 `sentiment.limit_up_pool` capability，此集合中的对应字段可为空 |
| `continuous_limit_up` | list of dict，每条含 `symbol`, `days`, `reason` | reason 为自由字符串 |

**温度合成公式待定**：`market_temperature` 为派生字段，由 `sentiment_service` 在 Provider 原始数据上合成。本 Design 阶段不定义合成公式，留作 Domain Service 内部实现细节（OQ-2 / SPEC §3.3 约定）。

**MongoDB 唯一键**：`{market, snapshot_date, snapshot_time}`
**MongoDB 索引建议**：
- `{snapshot_date: -1}` — 按日查询
- `{snapshot_time: -1}` — 按时点查询

---

## 4. 接口契约与注册点

### 4.1 AKShareProvider 扩展

**文件**：`providers/akshare.py`

在 `capabilities` 属性中追加：

```python
@property
def capabilities(self) -> set[str]:
    return {
        # Phase 1D 既有 7 项（不变）
        "market_data.kline_daily",
        "market_data.kline_weekly",
        "market_data.realtime_quote",
        "valuation.daily_basic",
        "calendar.trading_days",
        "calendar.is_trading_day",
        "metadata.stock_list",
        # Phase 3 新增 6 项
        "sector.snapshot",
        "sector.ranking",
        "flow.capital_flow_daily",
        "flow.northbound_daily",
        "sentiment.market_snapshot",
        "sentiment.limit_up_pool",
    }
```

在 `fetch()` 方法中追加分支（与既有 `kline_daily` real path 结构一致）：

```python
def fetch(self, domain, operation, security_id, **params):
    capability = self._check_capability(domain, operation)

    if capability == KLINE_DAILY_CAPABILITY:
        return self._fetch_kline_daily(security_id, params)

    # Phase 3 real path (T3 实施时按子阶段激活，activate=True 时走 real path)
    # 在 G-A-2/G-B-2/G-C-2 授权前，全部走 stub path（与 Phase 1B-A 行为一致）
    ACTIVE_P3_CAPABILITIES = {}  # 空 dict 表示全 stub；通过配置或注册启用
    if capability in ACTIVE_P3_CAPABILITIES:
        # real path 映射（见 §4.2）
        ...

    # Stub path for all other capabilities
    df = stub_dataframe_for(capability)
    return self._to_canonical(df, capability)
```

_canonical 映射需追加 3 条路径：sector.snapshot/ranking → list[SectorSnapshot], flow.capital_flow_daily → list[CapitalFlowRecord], sentiment.market_snapshot → list[MarketSentimentSnapshot]。

**STUB_COLUMNS 追加**（`providers/_stub_columns.py` + `providers/__init__.py`）：

依照 SPEC §4.3 精确列定义。两文件必须同步修改以避免 import 冲突（当前架构中 `_stub_columns.py` 是 canonical 源，`providers/__init__.py` 含孪生定义）。

**STUB_COLUMNS 双定义约束**：`_stub_columns.py` 和 `providers/__init__.py` 中的 `STUB_COLUMNS` 是孪生定义，必须保持等价。T3 Implement 必须至少：
1. 以 `_stub_columns.py` 为 canonical 源先行追加
2. 手动同步到 `providers/__init__.py`
3. 编写离线等价性测试（`test_provider_phase3.py` 中验证 `stub_columns.STUB_COLUMNS == providers.STUB_COLUMNS`）

**不得**仅改一处导致两文件不同步。

### 4.2 AKShare→Canonical 映射模式

本 Design 提供映射模式模板，具体 AKShare 列名在 T3 实施阶段通过 `akshare` 库函数实测确定。

```
sector.snapshot (AKShare 东方财富板块接口)
    ┌─────────────────────────┬──────────────────────────┐
    │ SectorSnapshot 字段      │ AKShare 预期列            │
    ├─────────────────────────┼──────────────────────────┤
    │ sector_code             │ block_code               │
    │ sector_name             │ block_name               │
    │ sector_type             │ 固定 "industry" (接口限定) │
    │ snapshot_date           │ date / trade_date        │
    │ rank                    │ rank                     │
    │ pct_chg                 │ change_percent           │
    │ leading_stock           │ leader_symbol            │
    │ leading_stock_name      │ leader_name              │
    │ leading_pct_chg         │ leader_change_percent    │
    │ advance_count           │ advance                  │
    │ decline_count           │ decline                  │
    │ total_count             │ total_members            │
    │ main_net_inflow         │ net_inflow               │
    │ turnover_rate           │ turnover_rate            │
    │ members                 │ members                  │
    └─────────────────────────┴──────────────────────────┘
```

**映射假设声明**：上述 AKShare 列名为「**设计假设**」，在 T3 实施阶段通过真实 API smoke 验证（FV-1 ~ FV-8）。若实际列名/类型/粒度与假设不符，T3 实施者须修正映射并在实施报告中说明偏离。

### 4.3 `_TA_CN_NOT_COVERED` 追加

**文件**：`router.py`

```python
_TA_CN_NOT_COVERED: frozenset[str] = frozenset({
    # Phase 1D 既有 6 项（不变）
    "market_data.kline_weekly",
    "market_data.adj_factor",
    "valuation.daily_basic",
    "calendar.trading_days",
    "calendar.is_trading_day",
    "metadata.index_members",
    # Phase 3 新增 6 项
    "sector.snapshot",
    "sector.ranking",
    "flow.capital_flow_daily",
    "flow.northbound_daily",
    "sentiment.market_snapshot",
    "sentiment.limit_up_pool",
})
```

### 4.4 FreshnessPolicy 追加

**文件**：`freshness.py`

```python
DEFAULT_TTLS: dict[str, int] = {
    # Phase 1B-A 既有 6 域（不变）
    "market_data": 21600,    # 6 hours
    "financial": 86400,      # 24 hours
    "valuation": 43200,      # 12 hours
    "calendar": 604800,      # 7 days
    "metadata": 604800,      # 7 days
    "news": 3600,            # 1 hour
    # Phase 3 新增 3 域
    "sector": 21600,         # 6h — 板块快照收盘后刷新即可。[T3 新增，当前 DEFAULT_TTLS 无此域]
    "flow": 43200,           # 12h — 资金流数据日盘后刷新即可。[T3 新增]
    "sentiment": 3600,       # 1h — 市场级情绪数据。[T3 新增]（注意：`"news": 3600` 是已有条目，与 sentiment 非同一域）
}
```

### 4.5 UnifiedDataClient 新增域方法

**文件**：`client.py`

惰性属性：

```python
self._flow_service: FlowService | None = None
self._sentiment_service: SentimentService | None = None

@property
def _flow(self) -> FlowService:
    if self._flow_service is None:
        from .services.flow_service import FlowService
        # Phase 3 P3-B: 不走 TA-CN adapter。FlowService 通过 Router 查询，
        # Router 已通过 config / registry 获得 TA-CN adapter（如需）。
        # 不调用 self._require_ta_cn()。
        self._flow_service = FlowService(self._router)
    return self._flow_service

@property
def _sentiment(self) -> SentimentService:
    if self._sentiment_service is None:
        from .services.sentiment_service import SentimentService
        # Phase 3 P3-C: 不走 TA-CN adapter。同上。
        self._sentiment_service = SentimentService(self._router)
    return self._sentiment_service
```

域方法：

```python
# ---- Phase 3 P3-A ----
def get_sector_snapshot(self, sector_code: str, date: str | None = None) -> DataResult:
    """返回单板块快照（SectorSnapshot 单条）。"""
    # 将 sector_code 作为查询参数，通过 Router 的 sector.snapshot capability 路由

def get_sector_ranking(self, date: str | None = None,
                       sector_type: str | None = None,
                       limit: int = 20) -> DataResult:
    """返回当日板块排名（list[SectorSnapshot]）。"""

# ---- Phase 3 P3-B ----
def get_capital_flow(self, security_id: SecurityId,
                     limit: int = 60,
                     start_date: str | None = None,
                     end_date: str | None = None) -> DataResult:
    """返回个股日资金流（list[CapitalFlowRecord]）。"""

def get_northbound_flow(self, security_id: SecurityId | None = None,  # 可选；None 表示市场级聚合（仅可用标的的总计），非个股级查询
                        date: str | None = None,
                        start_date: str | None = None,
                        end_date: str | None = None) -> DataResult:
    """返回个股级北向资金（list[CapitalFlowRecord]，仅 northbound_* 字段）。"""

# ---- Phase 3 P3-C ----
def get_market_sentiment(self, date: str | None = None) -> DataResult:
    """返回市场情绪快照（MarketSentimentSnapshot 单条，收盘后）。"""

def get_limit_up_pool(self, date: str | None = None) -> DataResult:
    """返回涨停/跌停池（list[dict]）。"""
```

**实现模式冰结**：Phase 3 的 UnifiedDataClient 域方法使用**模式 B（Router 模式）**，理由：

- P3-B 和 P3-C 的 Step 1（TA-CN）不可用（注册到 `_TA_CN_NOT_COVERED`），Router 的 internal-first 路径对它们相当于跳过 Step 1 → 走 Step 2/3 物化+Cache → 最后 Step 4 外部 Provider
- P3-A 的 `sector.snapshot` 和 `sector.ranking` 同样注册到 `_TA_CN_NOT_COVERED`，**不可**走 TA-CN adapter `index_daily_quotes` 推导路径，必须走明确的 external fallback 链
- Router 模式保证了未来 Phase 4+ 的 fallback 可扩展性而不需修改 client 方法

**构造/注入契约**：

```python
# Phase 3 domain services 不接收 TA_CNMongoAdapter——接收 DataRouter
class FlowService:
    def __init__(self, router: DataRouter):
        self._router = router

class SentimentService:
    def __init__(self, router: DataRouter):
        self._router = router
```

**未冻结的能力**：核心 schema/granularity/TA-CN coverage 在设计阶段已冻结（§3）。如有任何未冻结的 domain 能力（如 `OQ-7 sector.snapshot` 的 TA-CN 可推导性），必须保持 stub——不得进入对应子阶段的 T3 实现。

### 4.6 External Fallback Chains

Phase 3 的六个 capability 的 external_fallback_chain 通过 `UnifiedDataClient(external_fallback_chains=...)` 构造参数传入（Router 内部第 133-134 行 `config=...` 参数）：

```python
external_fallback_chains = {
    # P3-A
    "sector.snapshot": ["akshare"],
    "sector.ranking": ["akshare"],
    # P3-B
    "flow.capital_flow_daily": ["akshare"],
    "flow.northbound_daily": ["akshare"],
    # P3-C
    "sentiment.market_snapshot": ["akshare"],
    "sentiment.limit_up_pool": ["akshare"],
}
```

**不改动**：现有所有 capability 的 fallback 链不变。Phase 3 的六个 capability 当前仅注册 AKShare 一个 Provider。

**单 Provider 失败语义**：当 AKShareProvider.fetch() 失败（不可用/超时/异常），Router 抛出的 `AllProvidersFailedError` 内部的 attempts 列表中的单条记录应为 `("akshare", ProviderError(...))`。External fallback 链中单 provider 失败对外表现为 `DataResult.error(provider='error', source_trace=["akshare(error: ...)"])`——与 Phase 1D 其他 capability 的单 provider 失败模式一致。**不得**使用未定义异常类型或静默返回空数据。

**Mock Provider 注册约定**：所有 Phase 3 测试（T4 Verify）中使用的 mock/fake provider 必须通过 `ProviderRegistry.register()` 注册到 Router，而非直接注入 Router 的构造函数或替换其内部属性——与 Phase 0/Phase 1 的测试约定一致，保持 Router 的依赖注入边界不变。

---

## 5. Domain Service 设计

### 5.1 SectorService 追加（P3-A）

**文件**：`services/sector_service.py`

在已有的 `SectorService` 中追加：

```python
class SectorService:
    """板块/行业域服务（Phase 1A + Phase 3 P3-A 扩展）。"""

    # 已有 Phase 1A 方法（不变）

    def get_sector_snapshot(
        self,
        sector_code: str,
        date: str | None = None,
        *,
        security_id: SecurityId | None = None,
    ) -> DataResult:
        """返回单板块快照。走 Router external_fallback chain。

        sector_code 直接作为查询参数（板块层面查询，非个股层面）。
        """
        # 通过 Router.query("sector", "snapshot", ...) 路由
        ...

    def get_sector_ranking(
        self,
        date: str | None = None,
        sector_type: str | None = None,
        limit: int = 20,
        *,
        security_id: SecurityId | None = None,
    ) -> DataResult:
        """返回板块排名。"""
        ...
```

**与 Phase 1A 方法的区别**：Phase 3 的 `get_sector_snapshot` / `get_sector_ranking` 不走 TA-CN adapter（`sector.snapshot` 在 `_TA_CN_NOT_COVERED` 中），直接经由 Router 的 external fallback。因此它们与 Phase 1A 的 `get_stock_sector` / `get_stocks_by_sector` / `get_sector_index_bars` 共享同一个 Service class 但通过不同的查询路径执行。

**构造方式（已冻结）**：SectorService（Phase 1A）当前通过 `self._require_ta_cn()` 构造，接收 `TA_CNMongoAdapter`。Phase 3 追加的 P3-A 方法（`get_sector_snapshot` / `get_sector_ranking`）需额外接收 `router: DataRouter`。

**冻结决议**：在 SectorService 现有构造器中追加可选的 `router: DataRouter | None = None` 参数：

```python
class SectorService:
    def __init__(self, ta_cn_adapter: TA_CNMongoAdapter,
                 router: DataRouter | None = None):
        self._ta_cn = ta_cn_adapter
        self._router = router   # Phase 3 P3-A 方法使用
```

- P3-A 方法（`get_sector_snapshot` / `get_sector_ranking`）内部通过 `self._router.query()` 路由，**不得调用 `self._require_ta_cn()`**。
- 若 `self._router is None` 时调用 P3-A 方法，应抛出 `ProviderUnavailableError("P3-A methods require DataRouter: not injected")`。
- Phase 1A 既有方法（`get_stock_sector` / `get_stocks_by_sector` / `get_sector_index_bars`）保持使用 `self._ta_cn`，不受影响。
- `UnifiedDataClient` 的 `_sector_service` lazy property（`client.py`）中传递 `self._router` 给 SectorService 构造器：`SectorService(self._require_ta_cn(), router=self._router)`。

### 5.2 FlowService 新建（P3-B）

**文件**：`services/flow_service.py`（新建文件）

```python
class FlowService:
    """个股资金流域服务（Phase 3 P3-B）。"""

    def get_capital_flow(
        self,
        security_id: SecurityId,
        limit: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> DataResult:
        """返回个股日资金流。通过 Router 的 flow.capital_flow_daily capability 路由。"""
        ...

    def get_northbound_flow(
        self,
        security_id: SecurityId | None = None,  # 可选；None 表示市场级聚合（仅可用标的的总计），非个股级查询
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> DataResult:
        """返回个股级北向资金（仅 northbound_* 字段）。"""
        ...

    def refresh_capital_flow(
        self,
        security_id: SecurityId,
        date: str | None = None,
        *,
        mongo_db=None,     # Pascal Gate G-B-1/G-B-2 确认后注入
        cache_manager=None,
    ) -> DataResult:
        """【受控写入路径】显式刷新个股资金流：Provider fetch → MongoDB upsert → Cache put。"""
        ...
```

### 5.3 SentimentService 新建（P3-C）

**文件**：`services/sentiment_service.py`（新建文件）

```python
class SentimentService:
    """市场情绪域服务（Phase 3 P3-C）。"""

    def get_market_sentiment(
        self,
        date: str | None = None,
    ) -> DataResult:
        """返回市场情绪快照。通过 Router 的 sentiment.market_snapshot capability 路由。"""
        ...

    def get_limit_up_pool(
        self,
        date: str | None = None,
    ) -> DataResult:
        """返回涨停/跌停池。"""
        ...

    def refresh_market_sentiment(
        self,
        date: str | None = None,
        *,
        mongo_db=None,     # Pascal Gate G-C-1/G-C-2 确认后注入
        cache_manager=None,
    ) -> DataResult:
        """【受控写入路径】显式刷新市场情绪。"""
        ...
```

### 5.4 Refresh 方法实现契约

#### 5.4.1 `PersistenceResult` 类型定义

三个子阶段的 `refresh_xxx()` 方法统一返回 `PersistenceResult`，而非 `DataResult`。定义如下：

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

class PersistenceStatus(Enum):
    ALL_SUCCESS = "all_success"         # Provider fetch + 全部 persistence 写入成功
    PARTIAL_FAILURE = "partial_failure" # 部分记录 persistence 写入失败
    FAILURE = "failure"                 # Provider fetch 失败，或全部 persistence 写入失败
    SKIP_EMPTY = "skip_empty"           # Provider fetch 成功但返回空数据，不写入

@dataclass
class PersistenceResult:
    """持久化操作的可判定结果。

    用于所有 Phase 3 refresh 方法的返回值。与 DataResult 的「读查询成功/失败」
    语义分离——refresh 的「成功」指 persistence 写入完成而非数据获取。
    """
    overall_status: PersistenceStatus    # 全局状态
    provider_fetch_status: str | None = None  # "success" / "failed" / "skipped"
    records_attempted: int = 0           # Provider 返回的记录数
    records_persisted: int = 0           # 成功写入 MongoDB 的记录数
    records_failed: int = 0              # 写入失败的记录数
    failed_keys: list[dict] = field(default_factory=list)      # 失败记录的 business key 列表
    errors: list[str] = field(default_factory=list)            # 错误摘要列表
    cache_updated: bool = False          # Cache 是否写入成功
    collection_name: str = ""            # 写入的目标集合名
    source_trace: list[str] = field(default_factory=list)      # Provider fetch trace

    @property
    def succeeded(self) -> bool:
        return self.overall_status == PersistenceStatus.ALL_SUCCESS

    @property
    def is_failure(self) -> bool:
        return self.overall_status in (PersistenceStatus.FAILURE,)

    @property
    def is_partial(self) -> bool:
        return self.overall_status == PersistenceStatus.PARTIAL_FAILURE
```

#### 5.4.2 Refresh 方法通用模板

```python
def refresh_sector_snapshot(
    self,
    sector_code: str,
    date: str | None = None,
    *,
    p3_writer: P3PersistenceWriter | None = None,  # 外部注入，非 self 创建；Gate G-A-1 确认后非 None
    cache_manager=None,   # 外部注入，非 self 创建
) -> PersistenceResult:
    # 1. Provider fetch（走 AKShareProvider）
    domain_result = self._router.query(
        "sector", "snapshot",
        security_id=...,  # Gate 确认后使用正确 security_id
        provider="akshare",
        force_refresh=True,  # 跳过 Cache
        params={...},
    )

    # 1b. Provider fetch 失败
    if not domain_result.succeeded:
        return PersistenceResult(
            overall_status=PersistenceStatus.FAILURE,
            provider_fetch_status="failed",
            source_trace=list(domain_result.source_trace),
            errors=[f"Provider fetch failed: {domain_result.error or 'unknown'}"]
        )

    records = domain_result.data  # list[SectorSnapshot] 或其他
    if not records:
        return PersistenceResult(
            overall_status=PersistenceStatus.SKIP_EMPTY,
            provider_fetch_status="success",
            records_attempted=0,
        )

    # 2. P3PersistenceWriter.upsert()（仅当 p3_writer 可用）
    writer_result = PersistenceResult(
        overall_status=PersistenceStatus.ALL_SUCCESS,
        provider_fetch_status="success",
        records_attempted=len(records),
        source_trace=list(domain_result.source_trace),
        collection_name="03_data_ud_market_sector_snapshot",
    )

    if p3_writer is not None:
        try:
            upsert_outcome = p3_writer.upsert(
                collection="03_data_ud_market_sector_snapshot",
                records=records,          # list[DomainObject]
                unique_key={"market", "sector_code", "snapshot_date"},  # 显式传入业务键
            )
            writer_result.records_persisted = upsert_outcome.persisted
            writer_result.records_failed = upsert_outcome.failed
            writer_result.failed_keys = upsert_outcome.failed_keys
            writer_result.errors = upsert_outcome.errors
            if upsert_outcome.failed > 0 and upsert_outcome.persisted > 0:
                writer_result.overall_status = PersistenceStatus.PARTIAL_FAILURE
            elif upsert_outcome.failed > 0 and upsert_outcome.persisted == 0:
                writer_result.overall_status = PersistenceStatus.FAILURE
        except Exception as exc:
            writer_result.overall_status = PersistenceStatus.FAILURE
            writer_result.records_failed = len(records)
            writer_result.errors = [f"P3PersistenceWriter raise: {exc}"]

    # 3. Cache put（仅当 cache_manager 可用；不阻断）
    if cache_manager is not None and writer_result.records_persisted > 0:
        try:
            cache_manager.put(key=..., value=records)
            writer_result.cache_updated = True
        except Exception as exc:
            logger.warning("Phase 3 refresh: Cache put failed: %s", exc)
            # Cache 失败不阻断——writer_result 的 overall_status 不变

    # 4. 不写入 AuditLogger（默认关闭）
    # 5. 不写入 QualitySummary（冻结）

    return writer_result
```

#### 5.4.3 幂等、停止/禁写与已写记录处理

| 场景 | 行为 |
|---|---|
| **同业务键重复 refresh** | P3PersistenceWriter.upsert() 按业务唯一键做 `update_one` with `$set`，幂等。重复调用不会产生重复记录 |
| **某子阶段 Gate 尚未确认** | p3_writer 为 None，refresh 方法返回 `PersistenceResult(status="failure", errors=["p3_writer not injected: G-A-1 not confirmed"])`。**不得**静默跳过写入后返回假成功 |
| **Provider fetch 部分成功** | 返回 `PersistenceResult(status="partial_failure")`，已获取的记录正常写入，缺失的记录在 `failed_keys` 中列出 |
| **写入过程中断（进程退出）** | 已写入的记录保持原样：**无回滚**。MongoDB 单行 upsert 是原子的；已写入的行不受后续退出影响。消费方通过 `records_persisted` 和 `failed_keys` 判断不完整写入 \[注1\] |
| **需要停止某子阶段** | 在入口处移除对应的 capability 注册 + 将 p3_writer 置为 None。现有物化数据保留。无需清空集合（见 §10.1） |

> \[注1\]：Phase 3 不支持跨多条记录的事务回滚（MongoDB 单副本架构，无事务保障）。如 Phase 5+ 需要原子批量写入，需升级到 MongoDB 副本集 + 事务。

#### 5.4.4 离线测试矩阵

| 测试场景 | 注入 | 期望 `PersistenceResult` | 对应验收项 |
|---|---|---|---|
| Provider fetch 成功 + 全部写入成功 | mock provider 返回 3 条记录 + mock writer 全部 upsert 成功 | `overall_status=ALL_SUCCESS, records_persisted=3` | A-010 |
| Provider fetch 成功 + 全部写入失败 | mock provider 返回 3 条记录 + mock writer 全部 upsert 失败 | `overall_status=FAILURE, records_persisted=0, records_failed=3` | A-011 |
| Provider fetch 成功 + 部分写入失败 | mock provider 返回 3 条记录 + mock writer 2 成功 1 失败 | `overall_status=PARTIAL_FAILURE, records_persisted=2, records_failed=1, failed_keys=[{...}]` | A-012 |
| Provider fetch 失败（不可用） | mock provider raise ProviderUnavailableError | `overall_status=FAILURE, provider_fetch_status="failed"` | A-013 |
| Provider fetch 返回空数据 | mock provider 返回空列表 | `overall_status=SKIP_EMPTY, records_attempted=0` | A-014 |
| p3_writer 为 None（Gate 未确认） | p3_writer=None | `overall_status=FAILURE, errors=["p3_writer not injected"]` | A-015 |
| Cache 写入失败 | cache_manager.put raise 异常 | `overall_status=ALL_SUCCESS`（不阻断），`cache_updated=False` | A-016 |

---

## 6. MongoDB 集合设计（仅 Design，不执行）

### 6.1 集合与唯一键

| 集合名 | 子阶段 | 唯一键 | 索引 | TTL |
|---|---|---|---|---|
| `03_data_ud_market_sector_snapshot` | P3-A | `{market, sector_code, snapshot_date}` | `{sector_code:1, snapshot_date:-1}`, `{snapshot_date:-1}`, `{sector_type:1, snapshot_date:-1}` | 无（物化可追溯数据） |
| `03_data_ud_stock_capital_flow` | P3-B | `{market, symbol, trade_date}` | `{symbol:1, trade_date:-1}`, `{trade_date:-1}` | 无（物化可追溯数据） |
| `03_data_ud_market_sentiment_snapshot` | P3-C | `{market, snapshot_date, snapshot_time}` | `{snapshot_date:-1}`, `{snapshot_time:-1}` | 无（物化可追溯数据） |

**唯一键语义**：同一唯一键的记录通过 upsert（`update_one` with `$set`）更新，相同键的后续写入覆盖先前的完整记录。不保留历史版本（如需版本跟踪属 Phase 5+）。

### 6.2 集合创建脚本

以下脚本在 Pascal 确认 Gate G-A-1/G-B-1/G-C-1 后执行。示例（以 P3-A 为例）：

```javascript
// P3-A: 创建板块快照集合
db.createCollection("03_data_ud_market_sector_snapshot");

// 创建索引（在创建集合后执行）
db["03_data_ud_market_sector_snapshot"].createIndex(
    {sector_code: 1, snapshot_date: -1},
    {background: true, name: "sector_code_date"}
);
db["03_data_ud_market_sector_snapshot"].createIndex(
    {snapshot_date: -1},
    {background: true, name: "snapshot_date"}
);
db["03_data_ud_market_sector_snapshot"].createIndex(
    {sector_type: 1, snapshot_date: -1},
    {background: true, name: "sector_type_date"}
);
```

### 6.3 记录级可追溯字段

依据 SPEC §4.bis.1，每条记录至少包含以下字段：

| 字段 | 说明 | 所属 domain object | 待定状态 |
|---|---|---|---|
| `provider` | 数据来源标识，如 `"akshare"` | 全部三个 | 已定 ✅ |
| `fetched_at` | 数据获取时间，ISO-8601 格式 | 全部三个 | 已定 ✅ |
| `schema_version` | 该记录的 domain object schema 版本号（语义版本号） | 全部三个 | **[待定]** T2 Design 裁定是否需要 |

**本 Design 裁定**：
- `quality_flags`：❌ **不纳入** Phase 3 domain schema。Phase 3 的 3 个 domain object 不包含 `quality_flags` 字段。此字段属于 Phase 2 `QualitySummary` 范畴—QualitySummary 仍冻结（RFC-03-011），Phase 3 不触及其 schema。任何未来新增 `quality_flags` 需求需独立 RFC/SPEC 变更。
- `source_record_id`：❌ 暂不纳入。AKShare 为免费接口，不返回行级唯一 ID。如后续 Provider 切换或有需求，Phase 4+ 追加。
- `schema_version`：❌ 暂不纳入。Phase 3 三个 domain object 的 schema 在 V0.1 定稿后通过版本历史追溯，不写入每条记录。如后续 schema 演进需要行级版本标识，Phase 5+ 追加。

**禁止字段**：上述集合中**不包含** `quality_summary`、`quality_score`、`quality_flags` 等 Phase 2 质量字段——QualitySummary 仍冻结（RFC-03-011）。

---

## 7. 异常分类

### 7.1 异常类型矩阵

| 异常 | 触发条件 | 结果 | 子阶段 |
|---|---|---|---|
| `UnsupportedCapabilityError` | 能力未在 provider capabilities 集合中声明 | `DataResult.error(provider="error")` | 全部 |
| `ProviderUnavailableError` | akshare 包不可导入 / 网络不通 / 接口超时 / 空返回 | `DataResult.error(provider="error", source_trace=["akshare(unavailable: ...)"])` | 全部 |
| `ProviderError` | AKShare API 返回异常 / 缺失必填列 / 字段类型异常 | `DataResult.error(provider="error", source_trace=["akshare(error: ...)"])` | 全部 |
| `AllProvidersFailedError` | fallback 链全部失败（当前链仅 akshare，等价于 ProviderUnavailableError） | 抛异常，由 Router 调用方处理 | 全部 |
| `ValueError`（构造失败） | `SectorSnapshot.from_dict()` 字段缺失无法构造 | `DataResult.error(provider="error")` | P3-A |
| `KeyError`（字段映射） | AKShare 返回的 DataFrame 列名与预期映射不匹配 | `ProviderError` | 全部 |

### 7.2 AKShare 特有的异常路径

| 场景 | AKShare 行为 | 映射 | 
|---|---|---|
| 板块代码不存在 | 返回空 DataFrame | `ProviderUnavailableError`（走空数据处理逻辑，不写物化） |
| 交易日期无数据（非交易日） | 返回空 DataFrame | `ProviderUnavailableError`（与 Phase 1D kline_daily 一致） |
| 北向资金数据对非标的不存在 | 数据为空列 | 对应 `northbound_*` 字段为 None，正常写入 |
| 涨停池查询超时（盘后可用） | API 响应缓慢 | 走配置超时参数，超时后 `ProviderUnavailableError` |
| 频率限制（短时间内多次调用） | AKShare 可能 HTTP 429 | 走 `rate_limiter`（与 Phase 1D 一致，每请求间隔为可配置参数） |

---

## 8. 文件矩阵与实施顺序建议

### 8.1 文件清单

| # | 操作 | 文件路径 | IN/OUT | 子阶段 | 
|---|---|---|---|---|
| **Domain Models** | | | | |
| 1 | 追加 | `models/domain/sector.py` | SectorSnapshot dataclass | P3-A |
| 2 | 新建 | `models/domain/flow.py` | CapitalFlowRecord dataclass + from_dict | P3-B |
| 3 | 新建 | `models/domain/sentiment.py` | MarketSentimentSnapshot dataclass + from_dict | P3-C |
| 4 | 追加 | `models/domain/__init__.py` | 导出 3 个新 domain object + 版本号声明 | 全部 |
| **Services** | | | | |
| 5 | 追加 | `services/sector_service.py` | get_sector_snapshot / get_sector_ranking | P3-A |
| 6 | 新建 | `services/flow_service.py` | FlowService（get_capital_flow / get_northbound_flow / refresh_capital_flow） | P3-B |
| 7 | 新建 | `services/sentiment_service.py` | SentimentService（get_market_sentiment / get_limit_up_pool / refresh_market_sentiment） | P3-C |
| 8 | 追加 | `services/__init__.py` | 导入 FlowService、SentimentService | 全部 |
| **Client** | | | | |
| 9 | 追加 | `client.py` | 2 个 lazy service 属性 + 6 个域方法 | 全部 |
| **Router** | | | | |
| 10 | 追加 | `router.py` | `_TA_CN_NOT_COVERED` 追加 6 项 | 全部 |
| **Freshness** | | | | |
| 11 | 追加 | `freshness.py` | DEFAULT_TTLS 追加 3 域 | 全部 |
| **AKShare Provider** | | | | |
| 12 | 追加 | `providers/akshare.py` | capabilities + fetch 分支 + _to_canonical 映射 | 全部 |
| 13 | 追加 | `providers/_stub_columns.py` | STUB_COLUMNS 追加 6 项 | 全部 |
| 14 | 追加 | `providers/__init__.py` | 同上同步 | 全部 |
| **Tests & Fixtures** | | | | |
| 15 | 新建 | `tests/test_sector_snapshot.py` | SectorSnapshot 构造 + from_dict + 字段边界 + 枚举值（8 用例） | P3-A |
| 16 | 新建 | `tests/test_sector_service.py` | get_sector_snapshot/ranking（mock provider）+ 空数据 + error（6 用例） | P3-A |
| 17 | 新建 | `tests/fixtures/sector_fixtures.py` | 2 条 SectorSnapshot：industry（白酒）+ concept（AI） | P3-A |
| 18 | 新建 | `tests/test_capital_flow.py` | CapitalFlowRecord 构造 + from_dict + 符号约定 + 北向空处理（10 用例） | P3-B |
| 19 | 新建 | `tests/test_flow_service.py` | get_capital_flow/northbound_flow（mock provider）+ 分页（6 用例） | P3-B |
| 20 | 新建 | `tests/fixtures/flow_fixtures.py` | 2 条 CapitalFlowRecord：含北向 + 不含北向 | P3-B |
| 21 | 新建 | `tests/test_market_sentiment.py` | MarketSentimentSnapshot 构造 + from_dict + 温度范围（8 用例） | P3-C |
| 22 | 新建 | `tests/test_sentiment_service.py` | get_market_sentiment/limit_up_pool（mock provider）+ 连板交叉验证（6 用例） | P3-C |
| 23 | 新建 | `tests/fixtures/sentiment_fixtures.py` | 2 条 MarketSentimentSnapshot：正常 + 极端行情 | P3-C |
| 24 | 新建 | `tests/test_provider_phase3.py` | AKShareProvider Phase 3 stub fetch + STUB_COLUMNS 验证（6 用例） | 全部 |

**总量**：24 个文件操作（12 新建 + 12 追加），按子阶段渐进实施。

### 8.2 实施顺序建议

```
准备阶段（可预先完成，不与任何子阶段绑定）
  ├─ STUB_COLUMNS 追加（#13, #14）
  └─ _TA_CN_NOT_COVERED 追加（#10）
  └─ FreshnessPolicy 追加（#11）

P3-A 阶段
  ├─ Domain: #1, #4（SectorSnapshot 部分）
  ├─ AKShare: #12（sector 部分 capabilities + fetch + _to_canonical）
  ├─ Service: #5
  ├─ Client: #9（sector 部分方法）
  └─ Tests: #15, #16, #17
  └─ (Gate G-A-1/G-A-2/G-A-3)

P3-B 阶段
  ├─ Domain: #2, #4（CapitalFlowRecord 部分）
  ├─ AKShare: #12（flow 部分 capabilities + fetch + _to_canonical）
  ├─ Service: #6
  ├─ Client: #9（flow 部分方法）
  └─ Tests: #18, #19, #20
  └─ (Gate G-B-1/G-B-2/G-B-3)

P3-C 阶段
  ├─ Domain: #3, #4（MarketSentimentSnapshot 部分）
  ├─ AKShare: #12（sentiment 部分 capabilities + fetch + _to_canonical）
  ├─ Service: #7
  ├─ Client: #9（sentiment 部分方法）
  └─ Tests: #21, #22, #23
  └─ (Gate G-C-1/G-C-2/G-C-3)

验证阶段（所有子阶段完成后）
  └─ Test: #24（test_provider_phase3.py — 全 Phase 3 stub 验证）
  └─ Regression: pytest skills/data/unified_data/tests -q exit 0
```

---

## 9. 测试策略

### 9.1 单元测试清单

| 测试文件 | 覆盖内容 | 预期用例数 | 子阶段 | 是否需网络 |
|---|---|---|---|---|
| `test_sector_snapshot.py` | SectorSnapshot 构造、from_dict、字段边界、枚举值 | 8 | P3-A | 否 |
| `test_sector_service.py` | get_sector_snapshot/ranking（mock provider）、空数据、error 分支 | 6 | P3-A | 否 |
| `test_capital_flow.py` | CapitalFlowRecord 构造、from_dict、符号约定、北向空处理 | 10 | P3-B | 否 |
| `test_flow_service.py` | get_capital_flow/northbound_flow（mock provider）、分页、限流 | 6 | P3-B | 否 |
| `test_market_sentiment.py` | MarketSentimentSnapshot 构造、from_dict、温度范围 | 8 | P3-C | 否 |
| `test_sentiment_service.py` | get_market_snapshot/limit_up_pool（mock provider）、连板交叉验证 | 6 | P3-C | 否 |
| `test_provider_phase3.py` | AKShareProvider Phase 3 新增 capability 的 stub/fake fetch、STUB_COLUMNS 验证 | 6 | 全部 | 否 |

### 9.2 测试工具与 mock 策略

| 组件 | 测试工具 | 说明 |
|---|---|---|
| Domain object 构造 | 纯 Python（无外部依赖） | `from_dict()` 的正向/异常路径 |
| Router 集成 | `ProviderRegistry` + 注入 mock/fake provider | 注册 stub AKShareProvider，验证 DataRouter 返回 DataResult |
| Service 方法 | fake/mock provider 注入到 Router | 验证 service.get_xxx() 的正确路由 |
| AKShareProvider | `_stub_columns.py` 的 stub DataFrame 或 fake DataFrame | 验证 `_to_canonical()` 字段映射正确性 |
| 离线约束 | 仅 mongomock ± fake provider | 不做网络请求、不做 MongoDB 写入 |

### 9.3 Fixture 设计

| Fixture 文件 | 内容 | 子阶段 |
|---|---|---|
| `sector_fixtures.py` | 2 条 SectorSnapshot：industry（白酒）+ concept（AI），正常交易日 + 极端行情 | P3-A |
| `flow_fixtures.py` | 2 条 CapitalFlowRecord：含北向数据（沪深港通标的）+ 不含北向（非标的） | P3-B |
| `sentiment_fixtures.py` | 2 条 MarketSentimentSnapshot：正常交易日 + 极端行情（大量涨停） | P3-C |

### 9.4 回归测试

```bash
# Phase 1D 基线 — 跑前确认
.venv/bin/python -m pytest skills/data/unified_data/tests -q --tb=short  # exit 0

# Phase 3 新增测试（按子阶段）
# P3-A
.venv/bin/python -m pytest skills/data/unified_data/tests/test_sector_*.py -q --tb=short
# P3-B
.venv/bin/python -m pytest skills/data/unified_data/tests/test_capital_*.py skills/data/unified_data/tests/test_flow_*.py -q --tb=short
# P3-C
.venv/bin/python -m pytest skills/data/unified_data/tests/test_market_sentiment*.py skills/data/unified_data/tests/test_sentiment_service*.py -q --tb=short
```

### 9.5 不可自动化验证项

- 「所有数据为辅助研究数据」的声明在 SPEC 三份 domain object docstring 中通过静态 grep 验证（V-GEN-6 / A-015）
- Pascal Gate 逐项授权确认：非自动化项
- AKShare 实际 API 响应格式与字段映射（FV-1 ~ FV-8）：需 T3 实施阶段编写最小 smoke 测试验证

---

## 10. 回滚与停止条件

### 10.1 子阶段级回滚

| 条件 | 动作 | 子阶段 |
|---|---|---|
| 单元测试覆盖未达预期（A-001~A-003 任意 FAIL） | 退回 T3 Implement | 对应子阶段 |
| AKShare 真实 API 与 Design 假设严重不一致（FV-1 ~ FV-8 中多数 FAIL） | 停止该子阶段，重新评估 Provider 选择 | 对应子阶段 |
| MongoDB 集合创建失败或索引与 Design 不一致 | 停止 Gate G-*1 | 对应子阶段 |
| Canary 写入后发现严重数据质量问题 | 清空 canary 集合，排查 Provider 映射 | 对应子阶段 |

### 10.2 全阶段停止

| 条件 | 动作 |
|---|---|
| AKShare 免费接口服务中断或大幅变化 | 停止全部 Phase 3，评估替代 Provider（Tushare / Baostock）|
| Phase 2 AuditLogger/QualitySummary 未按计划解冻且 Phase 3 需要 | 降级：Phase 3 继续但 AuditLogger/QualitySummary 保持冻结 |
| 存储成本超出预期（全量日级资金流数据量过大） | 回溯成本估算，可能降级为部分标的 subset |

### 10.3 部分失败处理

| 场景 | 行为 |
|---|---|
| 某日 Provider 部分板块/标的无数据 | 有数据的写入物化，无数据的跳过。消费方通过 `PersistenceResult.records_persisted` / `failed_keys` 判断。整体状态视成功/失败比例定为 `ALL_SUCCESS` 或 `PARTIAL_FAILURE` |
| Provider 全天服务不可用 | 返回 `PersistenceResult(status=FAILURE, provider_fetch_status="failed")`。当日不写入物化集合，消费方读取已有物化数据（freshness="delayed"/"stale"） |
| 部分记录 MongoDB 写入失败 | 返回 `PersistenceResult(status=PARTIAL_FAILURE, records_persisted=N, records_failed=M, failed_keys=[...])`。已写入记录保留（无可信回滚 - §5.4.3） |
| 全部记录 MongoDB 写入失败 | 返回 `PersistenceResult(status=FAILURE, records_persisted=0, records_failed=N, error=...)`。不写 Cache。消费方不应依赖物化数据 |
| 某子阶段已写入生产数据后需停止 | 保留物化集合，停止该子阶段的新写入。现有数据继续被 Router Step 2 读取。不执行集合 DDL/DML |

---

## 11. 开放问题

| # | 问题 | 影响 | 建议决议方式 |
|---|---|---|---|
| OQ-1 | 资金流数据是否需要分钟级盘中快照？当前仅日级 | P3-B 集合 schema 如果需增加 `snapshot_time` 维度，唯一键变为 `{market, symbol, trade_date, snapshot_time}` | 当前保留日级。如需盘中快照，P3-B T3 阶段追加 `snapshot_time` 字段 |
| OQ-2 | `market_temperature` 合成公式？ | MarketSentimentSnapshot 的 `market_temperature` 字段定义不完整 | 留作 Domain Service 内部实现。T3 阶段定义公式或确认保留为 None |
| OQ-3 | `SectorSnapshot.members` 字段是否必要？ | 如不需要，可减少 MongoDB 文档大小 | 当前保留。若 T3 阶段发现数据量过大（>1000 个代码/板块），可拆分为独立集合 |
| OQ-4 | 3 个子阶段的执行顺序是否接受推荐序（P3-A → P3-B → P3-C）？ | 影响 T3 实施排期 | 等待 Pascal 确认 |
| OQ-5 | `03_data_ud_stock_capital_flow` 的倒填（backfill）策略？是否需要回填历史 N 个月数据？ | 影响 G-B-3 canary 后的计划 | 仅日级 forward，不倒填，除非 Pascal 另行授权 |
| OQ-6 | AKShare `flow.northbound_daily` 返回的北向资金是个股级还是市场级？ | 影响 CapitalFlowRecord 的 `northbound_*` 字段填充 | 假设为个股级（FV-4）。T3 阶段验证，与 SPEC §3.2 northbound_daily scope 一致 |
| OQ-7 | `sector.snapshot` 的 Step 1 是否可通过 TA-CN `index_daily_quotes` 部分推导？ | 影响 P3-A 的 internal-first 读路径效率 | ❌ **已关闭**。§2.1 已冻结 `sector.snapshot` 在 `_TA_CN_NOT_COVERED` 中——不可走 TA-CN adapter 推导，必须走明确的 external fallback 路径 |

---

## 12. Pascal 授权 Gate 索引

| Gate ID | 动作 | 影响 | 最小样本 | 计量/预算单位 | Design § 参考 | SPEC § 参考 |
|---|---|---|---|---|---|---|
| G-A-1 | 创建 MongoDB 集合 `03_data_ud_market_sector_snapshot` + 索引 | P3-A 可写 | — | MongoDB 存储量 [待验证] | §6.1, §6.2 | §10 |
| G-A-2 | AKShareProvider 首次真实调用 `sector.snapshot` / `sector.ranking` | P3-A 可读 | 1 日期 5 板块 [待 Pascal 确认] | AKShare API 调用次数 [待验证] | §4.1, §4.2 | §10 |
| G-A-3 | 手动触发一日 canary：当日板块快照采集 | P3-A 生产验证 | 1 日 [待 Pascal 确认] | MongoDB 文档数 [待验证] | §5.4, §2.2 | §10 |
| G-B-1 | 创建 MongoDB 集合 `03_data_ud_stock_capital_flow` + 索引 | P3-B 可写 | — | MongoDB 存储量 [待验证] | §6.1, §6.2 | §10 |
| G-B-2 | AKShareProvider 首次真实调用 `flow.capital_flow_daily` / `flow.northbound_daily` | P3-B 可读 | 1 日期 5 标的 [待 Pascal 确认] | AKShare API 调用次数 [待验证] | §4.1, §4.2 | §10 |
| G-B-3 | 手动触发 canary：单日个股资金流采集（分批限速） | P3-B 生产验证 | 1 日 50 标的 [待 Pascal 确认] | MongoDB 文档数 + API 调用配额 [待验证] | §5.4, §2.2 | §10 |
| G-C-1 | 创建 MongoDB 集合 `03_data_ud_market_sentiment_snapshot` + 索引 | P3-C 可写 | — | MongoDB 存储量 [待验证] | §6.1, §6.2 | §10 |
| G-C-2 | AKShareProvider 首次真实调用 `sentiment.market_snapshot` / `sentiment.limit_up_pool` | P3-C 可读 | 1 日期 [待 Pascal 确认] | AKShare API 调用次数 [待验证] | §4.1, §4.2 | §10 |
| G-C-3 | 手动触发 canary：单日情绪快照采集 | P3-C 生产验证 | 1 日 [待 Pascal 确认] | MongoDB 文档数 [待验证] | §5.4, §2.2 | §10 |

**授权原则**：
- 所有 `[待 Pascal 确认]` 项在对应子阶段 T3 Implement 开始前由 Pascal 确认具体数值。
- 所有 `[待验证]` 项在对应子阶段 canary 阶段（G-*-3）由 T3 实施者评估实际消耗并记录，作为是否继续该子阶段的输入。
- 每个子阶段的三道 Gate（G-*-1 → G-*-2 → G-*-3）**必须依序通过**，不得跳过。
- Gate 未授权前的操作（创建集合、调用真实 API、执行 canary）属违规。当前 Design 未授权任何 Gate。

**后续授权**（不在 Phase 3 范围）：长期调度（cron / systemd）和 Task Center Job 创建属独立授权；生产 canary 仅支持手动触发。

---

## 13. 非交易声明

本 Design 涉及的全部三个 domain object（SectorSnapshot、CapitalFlowRecord、MarketSentimentSnapshot）在 docstring 中均包含以下精确措辞（通过 SPEC A-015 / V-GEN-6 静态 grep 验证）：

> 本数据为辅助研究数据，不构成交易指令或投资建议。

---

## 14. 本 Design 的无改动声明

本 Design 是 Design 文档，不代表任何代码实现已经发生。以下确认本 Design 阶段的不变状态：

- ❌ 未创建任何 Python `.py` 文件（除本 Design 文档外）
- ❌ 未修改任何现有 `.py` 文件
- ❌ 未读取 `.env` 或任何凭据文件
- ❌ 未连接 MongoDB 或执行任何网络/API/Provider 调用
- ❌ 未执行 DDL/DML
- ❌ 未修改 `DataRouter.query()` 的编排逻辑
- ❌ 未修改 `DataResult` / `Capability` / `SecurityId` 的签名
- ❌ 未创建 Task Center Job / cron / systemd 配置
- ❌ QualitySummary 仍冻结；AuditLogger 默认关闭
- ❌ 未创建 Implement / Verify / Review 子任务
- ❌ 未将任何假设标记为已验证事实
