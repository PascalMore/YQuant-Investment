# DESIGN-03-014: Unified Data Phase 3 — 受控持久化扩展详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-21 |
| 最后更新 | 2026-07-22（V0.10 AKShare 无 Token + 复用 Phase 2 MONGO_URI 同步：§15.3.2 Dry-Run 示例移除 AKSHARE_TOKEN、preflight-mongo 改为 MONGO_URI_env；§15.3.3 Live-Read 门槛分割 AKShare 不依赖 PR-0；§15.4.2 审计矩阵移除 AKSHARE_TOKEN、MONGODB_URI→MONGO_URI；YAML 输出示例同步更新） |
| 版本号 | V0.10 |
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
|| V0.6 | 2026-07-22 | **Contract Gate Adjudication（T3-P3B 契约裁断）**。闭合 Fix-M23 Review 发现的 PersistenceResult 形状冲突：采纳方向 B（实现形状可接受），将 §5.4.1 中 `PersistenceStatus` Enum + 多字段 canonical 定义替换为 P3-B FlowService 的实际 `PersistenceResult(frozen, slots)` 实现（`status: str` / `capability` / `collection` / `persisted` / `failed` / `skipped` / `reason` / `writer_outcome`）；同步更新 §5.4.2 模板代码、§2.2 constraint #6 `overall_status→status`、§2.3 场景表字段对齐。RFC/SPEC 无此项引用，不受影响。 | YQuant-Principal |

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
6. refresh 方法整体返回值也是 `PersistenceResult`——消费方通过 `status` 字段判断写入状态（"ok"/"partial_failure"/"skipped"）。**不得返回 `DataResult`**（`DataResult` 的 `succeeded` / `is_empty` 语义只对读查询有意义）。
7. **MongoDB-first**：Phase 3 的持久化层仅 MongoDB。SQLite 不是 Phase 3 的运行时可选项——仅用于 legacy 数据迁移/离线分析/测试 mock。严禁 Phase 3 生产代码向 SQLite 写入。
8. **Cache materialization 禁写默认**：`CacheManager.put()` 在 `DataRouter.query()` 路径中默认关闭（§2.1）。仅在显式 refresh 路径中，且对应 Cache Gate（非独立 Gate——与对应子阶段的 G-*-1 绑定）授权后方可启用。
9. 所有 collection/index DDL/DML、canary、cron 均通过对应子阶段 Gate 逐项授权（见 §12）。Gate 未授权前，T3 不得创建集合、索引或执行任何数据定义操作。

### 2.3 空数据/失败写入处理

| 场景 | 行为 |
|---|---|
| Provider fetch 成功但返回空数据 | 不写入物化集合，不写入 Cache；返回 `PersistenceResult(status="skipped", persisted=0, failed=0, skipped=True, reason="empty_payload")` |
| Provider 不可用/请求失败 | 返回 `PersistenceResult(status="skipped", skipped=True, reason="provider_failed")`；不写入物化集合 |
| 部分记录 MongoDB 写入失败 | 返回 `PersistenceResult(status="partial_failure", persisted=N, failed=M, writer_outcome=<UpsertOutcome>)`；已写入记录不删除（无可信回滚——见 §10.3） |
| 全部记录 MongoDB 写入失败 | 返回 `PersistenceResult(status="skipped", persisted=0, failed=M, skipped=True, reason="writer_raised: ...")`；不写 Cache |
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

三个子阶段的 `refresh_xxx()` 方法统一返回 `PersistenceResult`，而非 `DataResult`。当前以 P3-B FlowService `flow_service.py` 的实现为事实契约，后续 P3-A/P3-C 视需求扩展。

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    """持久化操作的可判定结果（P3-B 实现事实）。

    与 DataResult 的「读查询成功/失败」语义分离——refresh 的「成功」
    指 persistence 写入完成而非数据获取。当前为 FlowService 服务，
    未来 P3-A/P3-C 如有联合字段需求可从此扩展。
    """

    status: str  # "ok" / "partial_failure" / "skipped"
    capability: str               # 目标 capability（审计友好）
    collection: str | None        # P3 目标集合；skip 分支为 None
    persisted: int = 0            # 成功 upsert 的记录数
    failed: int = 0               # 写入失败的记录数
    skipped: bool = False         # True 时 writer 未被调用
    reason: str | None = None     # skipped=True 的原因（"empty_payload" / "write_forbidden" / "already_written_idempotent"）
    writer_outcome: Any | None = None  # UpsertOutcome（writer 被调用时保留，skip 分支为 None）

    @property
    def success(self) -> bool:
        """``True`` when persisted records exist (idempotent re-runs OK)."""
        return self.status in ("ok", "partial_failure") and self.persisted >= 0
```

> **注**：`PersistenceResult` 使用字符串 `status` 作为分支鉴别器，而非 `PersistenceStatus` Enum——因为 P3-B 是当前唯一的实现者，字符串方案足够简单且对齐 §2.3 的表格措辞。未来如果 P3-A/P3-C 引入聚合状态枚举，可以在 `status` 之上构建 Enum 兼容层。

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
            status="skipped",
            capability="domain.operation",
            collection=None,
            persisted=0,
            failed=0,
            skipped=True,
            reason="provider_failed",
            writer_outcome=None,
        )

    records = domain_result.data  # list[SectorSnapshot] 或其他
    if not records:
        return PersistenceResult(
            status="skipped",
            capability="domain.operation",
            collection=collection_name,
            persisted=0,
            failed=0,
            skipped=True,
            reason="empty_payload",
            writer_outcome=None,
        )

    # 2. P3PersistenceWriter.upsert()（仅当 p3_writer 可用）
    if p3_writer is not None:
        try:
            upsert_outcome = p3_writer.upsert(
                collection="03_data_ud_market_sector_snapshot",
                records=records,          # list[DomainObject]
                unique_key={"market", "sector_code", "snapshot_date"},  # 显式传入业务键
            )
            # writer_result — 将 writer outcome 映射到 PersistenceResult
            status = "ok" if upsert_outcome.failed == 0 else "partial_failure"
            return PersistenceResult(
                status=status,
                capability="domain.operation",
                collection="03_data_ud_market_sector_snapshot",
                persisted=upsert_outcome.persisted,
                failed=upsert_outcome.failed,
                skipped=False,
                reason=None,
                writer_outcome=upsert_outcome,
            )
        except Exception as exc:
            return PersistenceResult(
                status="skipped",
                capability="domain.operation",
                collection="03_data_ud_market_sector_snapshot",
                persisted=0,
                failed=0,
                skipped=True,
                reason=f"writer_raised: {exc}",
                writer_outcome=None,
            )
    else:
        # p3_writer 未注入——skip（Gate 未授权，写入尚未启用）
        return PersistenceResult(
            status="skipped",
            capability="domain.operation",
            collection=collection_name,
            persisted=0,
            failed=0,
            skipped=True,
            reason="write_forbidden",
            writer_outcome=None,
        )

    # 3. Cache put 与 AuditLogger 由调用方处理，不在 refresh 方法内默认执行。
    # 参考 FlowService._fetch_for_refresh 的接口边界——refresh 只做 fetch→upsert→return。
```

#### 5.4.3 幂等、停止/禁写与已写记录处理

| 场景 | 行为 |
|---|---|
| **同业务键重复 refresh** | P3PersistenceWriter.upsert() 按业务唯一键做 `update_one` with `$set`，幂等。重复调用不会产生重复记录 |
|| **某子阶段 Gate 尚未确认** | p3_writer 为 None，refresh 方法返回 `PersistenceResult(status="skipped", skipped=True, reason="write_forbidden")`。**不得**静默跳过写入后返回假成功 |
|| **Provider fetch 部分成功** | 返回 `PersistenceResult(status="partial_failure")`，已获取的记录正常写入，缺失的记录通过 `writer_outcome.failed_keys` 回溯 |
| **写入过程中断（进程退出）** | 已写入的记录保持原样：**无回滚**。MongoDB 单行 upsert 是原子的；已写入的行不受后续退出影响。消费方通过 `persisted` 和 `writer_outcome.failed_keys` 判断不完整写入 \[注1\] |
| **需要停止某子阶段** | 在入口处移除对应的 capability 注册 + 将 p3_writer 置为 None。现有物化数据保留。无需清空集合（见 §10.1） |

> \[注1\]：Phase 3 不支持跨多条记录的事务回滚（MongoDB 单副本架构，无事务保障）。如 Phase 5+ 需要原子批量写入，需升级到 MongoDB 副本集 + 事务。

#### 5.4.4 离线测试矩阵

| 测试场景 | 注入 | 期望 `PersistenceResult` | 对应验收项 |
|---|---|---|---|
| Provider fetch 成功 + 全部写入成功 | mock provider 返回 3 条记录 + mock writer 全部 upsert 成功 | `status="ok", persisted=3` | A-010 |
| Provider fetch 成功 + 全部写入失败 | mock provider 返回 3 条记录 + mock writer 全部 upsert 失败 | `status="skipped", skipped=True, reason="writer_raised: ..."` | A-011 |
| Provider fetch 成功 + 部分写入失败 | mock provider 返回 3 条记录 + mock writer 2 成功 1 失败 | `status="partial_failure", persisted=2, failed=1` | A-012 |
| Provider fetch 失败（不可用） | mock provider raise ProviderUnavailableError | `status="skipped", skipped=True, reason="provider_failed"` | A-013 |
| Provider fetch 返回空数据 | mock provider 返回空列表 | `status="skipped", skipped=True, reason="empty_payload"` | A-014 |
| p3_writer 为 None（Gate 未确认） | p3_writer=None | `ProviderUnavailableError` (raises, not returned) | A-015 |
| Cache 写入失败 | 非 refresh 路径职责 | 不适用 | A-016 |

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
| 某日 Provider 部分板块/标的无数据 | 有数据的写入物化，无数据的跳过。消费方通过 `PersistenceResult.persisted` / `writer_outcome.failed_keys` 判断。整体状态视成功/失败比例定为 `"ok"` 或 `"partial_failure"` |
| Provider 全天服务不可用 | 返回 `PersistenceResult(status="skipped", skipped=True, reason="provider_failed")`。当日不写入物化集合，消费方读取已有物化数据（freshness="delayed"/"stale"） |
| 部分记录 MongoDB 写入失败 | 返回 `PersistenceResult(status="partial_failure", persisted=N, failed=M, writer_outcome=...)`。已写入记录保留（无可信回滚 - §5.4.3） |
| 全部记录 MongoDB 写入失败 | 返回 `PersistenceResult(status="skipped", skipped=True, reason="writer_raised: ...")`。不写 Cache。消费方不应依赖物化数据 |
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

---

## 15. T4 生产就绪 Preflight & Smoke 工具链设计

### 15.1 概述与架构

本 §15 为 T4 生产就绪阶段的设计。T4 处于 T3 离线实现之后（DESIGN-03-014 V0.6 对应 T3，已完成），在真实生产环境执行零写入只读预检与真实 Provider Smoke。本 §15 定义预检/smoke 工件的精确文件 allowlist、CLI 入口与执行模式、安全契约、以及验证/Review 流程的验收命令。T4 阶段的严格执行顺序为 PR-0 → PR-1 → PR-2/3/4 → Pascal 审阅 → PR-DDL-* → PR-CANARY-*（对应 RFC §13.6 / SPEC §14.6）。

#### 15.1.1 Phase 里程碑对齐

| 文档 | 版本 | T4 覆盖内容 |
|---|---|---|
| RFC-03-014 | V0.3 §13 | 生产就绪详细规范（副作用矩阵、规程模板、停止条件） |
| SPEC-03-014 | V0.3 §14 | 生产就绪契约（YAML 报告模板、Zero-Persistence-Write、DDL Gate 细则） |
| **DESIGN-03-014（本 §）** | **V0.8** | **实现设计（文件 allowlist、CLI 接口、安全契约、Verify/Review 验收命令、测试副作用输出目录）** |

#### 15.1.2 设计哲学

1. **默认安全**：所有工具默认 dry-run（零连接或仅元数据探测），显式 `--live-read` 才执行实际数据读取。
2. **零持久化写**：禁止 `--apply` 或任何写分支；所有工具的输出为 YAML 报告文件 + stdout。
3. **秘密非泄露**：secret 检查输出仅为布尔结论（present/absent/declared/loadable），不输出值、长度、URI、用户名。
4. **独立可审阅**：每 Capability 产出一份独立 YAML 报告，包含 connectivity/auth/permissions/field_mapping/data_sample/vs_fixture 六节。
5. **可审计不自动重试**：失败仅记录，不自动重试，不降级为写入。

### 15.2 文件 Allowlist

以下文件为 T4 工具链的完整 allowlist。Implement 阶段仅允许创建/修改这些文件：

| # | 操作 | 文件路径 | 说明 | 对应 Gate |
|---|---|---|---|---|
| **T4 CLI 入口** | | | | |
| 1 | 新建 | `scripts/t4_preflight/cli.py` | 统一 CLI 入口（`python -m scripts.t4_preflight.cli`） | PR-0 ~ PR-4 |
| 2 | 新建 | `scripts/t4_preflight/__init__.py` | 包标记 | --- |
| 3 | 新建 | `scripts/t4_preflight/config.py` | 配置常量：连接超时、api 端点、报告路径、默认日期窗口 | PR-0 ~ PR-4 |
| **Secret Source 审计** | | | | |
| 4 | 新建 | `scripts/t4_preflight/audit_secret.py` | Secret source 非泄露审计模块 | PR-0 |
| **MongoDB 预检** | | | | |
| 5 | 新建 | `scripts/t4_preflight/preflight_mongo.py` | MongoDB 零写入只读预检模块 | PR-1 |
| **Provider Smoke** | | | | |
| 6 | 新建 | `scripts/t4_preflight/smoke_sector.py` | AKShare sector.snapshot + sector.ranking smoke | PR-2 |
| 7 | 新建 | `scripts/t4_preflight/smoke_flow.py` | AKShare flow.capital_flow_daily + northbound_daily smoke | PR-3 |
| 8 | 新建 | `scripts/t4_preflight/smoke_sentiment.py` | AKShare sentiment.market_snapshot + limit_up_pool smoke | PR-4 |
| **报告模型** | | | | |
| 9 | 新建 | `scripts/t4_preflight/models.py` | SmokeReport / SecretAuditResult / MongoPreflightResult 等 dataclass | PR-0 ~ PR-4 |
| 10 | 新建 | `scripts/t4_preflight/reporter.py` | YAML 报告序列化（脱敏输出） | PR-0 ~ PR-4 |
| **工具函数** | | | | |
| 11 | 新建 | `scripts/t4_preflight/secrets.py` | 非泄露 SecretVerifier（仅 boolean 结果） | PR-0 |
| 12 | 新建 | `scripts/t4_preflight/mongo_client.py` | 安全 MongoDB 客户端工厂（零写入模式） | PR-1 |
| 13 | 新建 | `scripts/t4_preflight/provider_client.py` | AKShare 安全调用包装（超时、限速、异常分类） | PR-2/3/4 |
| **测试** | | | | |
| 14 | 新建 | `tests/scripts/test_t4_audit_secret.py` | Secret 审计单元测试 | PR-0 |
| 15 | 新建 | `tests/scripts/test_t4_preflight_mongo.py` | MongoDB 预检单元测试（mongomock） | PR-1 |
| 16 | 新建 | `tests/scripts/test_t4_smoke_sector.py` | Sector smoke 单元测试（mock AKShare） | PR-2 |
| 17 | 新建 | `tests/scripts/test_t4_smoke_flow.py` | Flow smoke 单元测试 | PR-3 |
| 18 | 新建 | `tests/scripts/test_t4_smoke_sentiment.py` | Sentiment smoke 单元测试 | PR-4 |
| 19 | 新建 | `tests/scripts/test_t4_reporter.py` | 报告序列化/脱敏/格式测试 | PR-0 ~ PR-4 |
| **夹具** | | | | |
| 20 | 新建 | `tests/scripts/fixtures/t4_secret_fixtures.py` | 模拟 .env 文件 + 环境变量场景 | PR-0 |
| 21 | 新建 | `tests/scripts/fixtures/t4_mongo_fixtures.py` | 模拟 mongomock 集合清单场景 | PR-1 |
| 22 | 新建 | `tests/scripts/fixtures/t4_akshare_fixtures.py` | 模拟 AKShare API 响应（含字段变体） | PR-2/3/4 |
| **根 package marker** | | | | |
| 23 | 新建 | `scripts/__init__.py` | 让 `from scripts.t4_preflight import ...` 可被 `tests/scripts/test_t4_*.py` 解析；pytest collection 必要前提（T4B 77/77 PASS 已验证） | PR-0 ~ PR-4 |

**总量**：23 个新建文件，位于 `scripts/__init__.py`、`scripts/t4_preflight/` 和 `tests/scripts/` 下。

> **Principal 正式裁决（2026-07-22）**：`scripts/__init__.py`（#23）为 T4 测试集合的必要 package marker，不包含任何运行时逻辑（仅 docstring），pytest 解析 `from scripts.t4_preflight import ...` 依赖其存在。正式确认其进入 T4 allowlist。该符号属 DESIGN 级实现细节，RFC/SPEC 无需提及。

> **未进入 allowlist**：现有 unified_data 代码（`models/`、`services/`、`providers/` 等）在 T4 阶段不做任何修改。T4 工具链独立于 unified_data 主库，仅在最终 Review PASS 后通过 `--live-read` 驱动真实环境验证。不修改 `unified_data` 核心模块的 `SKILL.md`、`README`、`requirements`、`pyproject.toml`。

### 15.3 公共安全契约

#### 15.3.1 CLI 入口语法

```text
python -m scripts.t4_preflight.cli <command> [--live-read] [--output-dir PATH] [--timeout SEC] [options]

命令：
  audit-secret         PR-0: Secret source 非泄露审计
  preflight-mongo      PR-1: MongoDB 零写入只读预检
  smoke-sector         PR-2: AKShare sector.snapshot + sector.ranking smoke
  smoke-flow           PR-3: AKShare flow.capital_flow_daily + northbound_daily smoke
  smoke-sentiment      PR-4: AKShare sentiment.market_snapshot + limit_up_pool smoke
```

**关键参数**：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--live-read` | False（不指定 = dry-run） | 显式标志才执行实际网络/MongoDB 调用 |
| `--output-dir` | `./docs/rfc/03_data/smoke_reports/` | YAML 报告输出路径 |
| `--timeout` | 3（秒） | 连接/请求超时 |
| `--date` | 最近一个交易日 | smoke 的模拟/实际日期 |
| `--symbol` | 预置默认标的 | 测试标的代码（sector: BK0489, flow: 600519 + 000001, sentiment: auto） |
| `--no-color` | False | 禁用彩色输出 |

**禁止参数**：
- ❌ `--apply`、`--write`、`--exec`、`--commit` 等任何暗示写入的参数
- ❌ 任何接收 secret 值/URI/密码的参数（secret 仅通过运行时 env / 文件系统加载）
- ❌ `--force`、`--skip-stop` 等绕过停止条件的参数

#### 15.3.2 Dry-Run 默认行为

默认（无 `--live-read`）时，所有命令执行受限的零连接探测：

| 命令 | Dry-Run 行为 |
|---|---|
| `audit-secret` | 检查文件存在性 + 权限（os.access），不读取内容。仅输出「secret_home/.env: readable=true, key='MONGO_URI': absent」形式的元数据 |
| `preflight-mongo` | 检查 `pymongo` importable + 配置路径可达。不实例化 MongoClient、不建立网络连接。输出「pymongo: importable=true, MONGO_URI_env: declared=true」 |
| `smoke-sector` | 检查 `akshare` importable + 测试参数初始化。输出「akshare: importable=true, test_symbol=BK0489, date_range=2026-07-20..2026-07-22, would_call: 2」 |
| `smoke-flow` | 同上行为 |
| `smoke-sentiment` | 同上行为 |

#### 15.3.3 Live-Read 模式（`--live-read`）

当 `--live-read` 被显式传递时，各命令才执行实际网络/MongoDB 调用：

| 命令 | Live-Read 动作 | 约束 |
|---|---|---|
| `audit-secret` | 实际调用 `os.getenv("KEY")` 验证值非 None（但**不**输出值/长度）。额外验证 `.env` 可被 `python-dotenv` 加载 |
| `preflight-mongo` | `MongoClient(timeout=3s)` → `admin.command("ping")` → `list_collection_names()` | 不读业务数据；超时 3s；需 `MONGO_URI` 已在 PR-0 授权 |
| `smoke-sector` | `akshare.stock_board_industry_cons_em("BK0489")` | 单板块 + ≤3 交易日；AKShare 匿名调用，不依赖 PR-0 授权 |
| `smoke-flow` | `akshare.stock_individual_fund_flow("600519", market="sh")` | 2-4 次调用，限速 ≥1s；AKShare 匿名调用 |
| `smoke-sentiment` | `akshare.stock_zt_pool_em("20260722")` / `stock_market_fund_flow()` | 单日期；AKShare 匿名调用 |

**Live-Read 执行门槛**：
1. MongoDB 预检 `preflight-mongo --live-read` 前，前序的 `audit-secret --live-read` 必须针对 `MONGO_URI` 为 PASS（MongoDB 连接秘密已授权）
2. AKShare smoke（`smoke-sector/flow/sentiment --live-read`）**不依赖 PR-0 授权**——AKShare 为匿名调用，可直接执行
3. `audit-secret` 的输出中 `MONGO_URI` 的状态为 `AUTHORIZED` 后，方可执行 `preflight-mongo --live-read`
4. smoke 命令的 `preflight-mongo --live-read` 输出中 `ping=success`

**不强制执行**：以上门槛由 CLI 输出 check 手动确认（非自动阻断——审查人通过查看报告链确认顺序合规）。但 `audit-secret --live-read` 未通过时，MongoDB preflight 命令应输出 `WARN: PR-0 not confirmed — MONGO_URI secret source presumed missing` 并将 `overall.verdict` 降为 `conditional_pass`。AKShare smoke 不受此警告影响。

### 15.4 Secret Source 非泄露审计设计（PR-0）

#### 15.4.1 SecretVerifier 接口

```python
# scripts/t4_preflight/secrets.py（设计草图，非最终实现）

@dataclass(frozen=True)
class SecretProbeResult:
    """非泄露秘密探测结果。只输出布尔/枚举结论，不输出值/长度/URI/用户名。"""
    source_name: str                          # 候选源名称，如 "project_root_env"
    file_exists: bool                         # 文件存在
    file_readable: bool | None = None         # 文件可读（dry-run 为 None）
    key_declared: bool | None = None          # 目标键在加载环境中是否存在
    is_loadable: bool | None = None           # 运行时可加载（os.getenv 非 None）


class SecretVerifier:
    """秘密验证器。所有方法返回 `SecretProbeResult`，仅输出布尔结论。"""

    def probe_file(self, path: str) -> SecretProbeResult:
        """检查文件存在性 + 读权限。**不读取内容**。"""

    def probe_env(self, key: str, *, live: bool = False) -> SecretProbeResult:
        """检查运行时 env 键声明。live=True 时实际调用 os.getenv(key) 返回非 None 判断。
        绝不记录或输出 os.getenv() 返回的值。"""
```

**不可违反规则**（在代码 review 时强制检查）：
- `probe_env(live=True)` 必须使用 `os.getenv(key)` 的返回值仅用于 `is not None` 判断，不得赋值给日志、print、write 输出
- `SecretProbeResult` 的任何字段不得包含字符串长度、字符切片、模式前缀
- YAML 序列化前必须通过 `Sanitizer.strip_secret(result)` 清洗（reporter.py §15.7）

#### 15.4.2 候选 Secret Source 审计矩阵

遵循 SPEC §14.3 / RFC §13.3，审计以下候选源：

| 候选路径 | 键名 | 验证方法 |
|---|---|---|
| `$(pwd)/.env` | `MONGO_URI` | `os.path.isfile()` + `os.access(R_OK)` + dotenv load |
| `~/.hermes/profiles/yquant/.env` | `MONGO_URI` | 同上 |
| `MONGO_URI` env | `MONGO_URI` | `os.getenv("MONGO_URI") is not None` |
| AKShare 匿名调用 | 无需密钥审计 | AKShare 为匿名数据源，跳过 PR-0 检查 |

**输出示例**（dry-run）：

```yaml
# audit-result-20260722.yaml
secret_audit:
  generated_at: "2026-07-22T03:30:00+08:00"
  sources:
    - source: "project_root_env"
      path_checked: "/home/pascal/workspace/yquant-investment/.env"
      file_exists: true
      file_readable: null      # dry-run: 未实际读取
      keys:
        MONGO_URI:
          declared: true       # detected in parsed env
          loadable: null       # dry-run
    - source: "runtime_env"
      keys:
        MONGO_URI:
          declared: true
          loadable: null
    - source: "akshare_anonymous"
      note: "AKShare 为匿名数据源，跳过 PR-0 密钥审计"
overall:
  status: conditional_authorized     # dry-run — 需 live-read 确认
  missing_keys: []
```

### 15.5 MongoDB 零写入只读预检设计（PR-1）

#### 15.5.1 允许操作白名单

**仅允许**：

| 操作 | MongoDB API | 影响 |
|---|---|---|
| Ping | `admin.command("ping")` | 验证连通性 |
| List Collections | `db.list_collection_names()` | 获取集合清单（不含数据） |
| Collection Options | `db[collection].options()` | 仅当目标集合意外存在时执行，获取创建元数据 |
| 关闭连接 | `client.close()` | 清理 |

**禁止操作**：

- ❌ 任何业务数据查询（`find()`、`aggregate()`、`distinct()`、`count_documents()`）
- ❌ `watch()`、`change_streams()`、`map_reduce()`
- ❌ 任何集合创建、索引操作
- ❌ 任何写操作（`insert_one/insert_many/update_one/update_many/replace_one/delete_one/delete_many/bulk_write`）
- ❌ 查询 `stock_basic_info`、`market_quotes`、`stock_daily_quotes` 等 TA-CN 业务集合

#### 15.5.2 MongoDB 客户端工厂

```python
# scripts/t4_preflight/mongo_client.py（设计草图）

@dataclass(frozen=True)
class MongoPreflightResult:
    connectivity: str           # "success" / "dns_failure" / "timeout" / "auth_failure"
    latency_ms: float | None
    collections: list[str] | None   # list_collection_names() 结果；None 表示 list 不可用
    p3_collections_found: list[str]  # 匹配 03_data_ud_ 前缀的意外集合
    warnings: list[str]


class MongoClientFactory:
    """安全 MongoDB 客户端工厂（零写入模式）。"""

    def create_preflight_client(self, timeout: int = 3) -> MongoClient | None:
        """创建只读预检专用 MongoClient。以 short timeout + read_preference=secondaryPreferred 初始化。
        在 dry-run 模式返回 None。"""

    def run_preflight(self, *, live: bool = False) -> MongoPreflightResult:
        """执行预检四步：(1) parse URI from env → (2) ping → (3) list_collections → (4) check P3 collections。
        所有步骤不携带业务数据 filter。"""
```

#### 15.5.3 集合存在检查

执行 `list_collection_names()` 后，用正则匹配检查集合名是否包含以下模式：
- `03_data_ud_market_sector_snapshot`
- `03_data_ud_stock_capital_flow`
- `03_data_ud_market_sentiment_snapshot`

如果任一集合存在，输出标记为 `UNEXPECTED_EXISTENCE`，列出 `options()` 元数据（创建时间戳、UUID、配置），**不读业务数据**。序列化 options() 时跳过 `wiredTiger` 引擎实现细节（仅保留 first-level 键）。预检停止，等待 Pascal 判断。

#### 15.5.4 失败分类

| 观察到的错误 | 报告状态 | 退出码 |
|---|---|---|
| DNS 解析失败 | `connectivity: dns_failure` | 2 |
| 网络超时（>3s） | `connectivity: timeout` | 2 |
| 认证拒绝（AuthFailure） | `connectivity: auth_failure` | 2 |
| list_collections 无权限 | `collections: null` + `warnings: ["list_collections_unauthorized"]` | 1（conditional pass） |
| 目标集合意外存在 | `p3_collections_found: ["03_data_ud_market_sector_snapshot"]` | 2（需 Pascal 确认） |
| 全部正常 | `connectivity: success` + `p3_collections_found: []` | 0 |

### 15.6 Provider Smoke 设计（PR-2/PR-3/PR-4）

#### 15.6.1 通用 AKShare 安全调用包装

```python
# scripts/t4_preflight/provider_client.py（设计草图）

@dataclass(frozen=True)
class SmokeCallResult:
    capability: str                            # 如 "sector.snapshot"
    call_index: int                            # 第几次调用（≤3）
    connectivity: str                          # "success" / "timeout" / "rate_limited" / "error"
    latency_ms: float | None
    raw_row_count: int | None                  # 返回记录数
    actual_fields: list[str] | None            # 返回的列名
    sample: list[dict] | None                  # 前 5 行（脱敏后，不含 secret）
    error: str | None                          # 错误摘要（不含 secret）


class AKShareSmokeClient:
    """AKShare 安全 smoke 客户端。"""

    def __init__(self, timeout: int = 30, min_interval: float = 1.0):
        self.timeout = timeout
        self.min_interval = min_interval  # 限速：≥1s/call（SPEC §14.4.1）

    def fetch_sector_snapshot(self, symbol: str, dates: list[str],
                               *, live: bool = False) -> SmokeCallResult:
        """调用 akshare.stock_board_industry_cons_em(symbol)。live=False 返回模拟元数据。"""

    def fetch_sector_ranking(self, date: str, *,
                              live: bool = False) -> SmokeCallResult:
        """调用 akshare.stock_board_industry_name_em() + 排名计算。"""

    def fetch_capital_flow(self, symbol: str, market: str, dates: list[str],
                           *, live: bool = False) -> SmokeCallResult:
        """调用 akshare.stock_individual_fund_flow(stock=symbol, market=market)。"""

    def fetch_northbound_flow(self, symbol: str, *, live: bool = False) -> SmokeCallResult:
        """调用个股北向接口。"""

    def fetch_market_sentiment(self, date: str, *, live: bool = False) -> SmokeCallResult:
        """调用 akshare.stock_zt_pool_em(date) + stock_market_fund_flow()。"""
```

**调用次数上限**（硬编码在 `config.py` 中，不可被运行参数覆盖）：

| Capability | Max Calls | 限制原因 |
|---|---|---|
| `sector.snapshot` | 1 | 单板块代码 BK0489 |
| `sector.ranking` | 1 | 单日期 |
| `flow.capital_flow_daily` | 2 | 单标的 × 2 市场（600519 sh + 000001 sz） |
| `flow.northbound_daily` | 1 | 单标的 × 1 |
| `sentiment.market_snapshot` | 1 | 单日期 |
| `sentiment.limit_up_pool` | 1 | 单日期 |

总计：单个调用不超过 7 次 AKShare API 请求（不分阶段并行）。支持单独 PR-2/PR-3/PR-4 命令分段执行，此时每命令调用上限分别为 2/3/2 次。

#### 15.6.2 字段映射比较

`reporter.py` 中的字段映射比较器将实际 AKShare 返回列名与 SPEC §3 定义的 domain object 字段列表做对照：

```python
# 调用后自动执行
field_mapping = FieldMapper.compare(
    actual_fields=smoke_result.actual_fields,          # e.g. ["block_code", "block_name", ...]
    expected_fields=sector_snapshot_columns,           # SPEC §§3.1 定义，含别名候选
    expected_types={
        "sector_code": str, "pct_chg": float, ...
    },
)

# 输出到报告
field_mapping.matched_ratio     # float 0.0~1.0
field_mapping.missing_fields    # list[str]
field_mapping.extra_fields      # list[str]
field_mapping.type_mismatches   # list[{"field": str, "expected": str, "actual": str}]
```

匹配率阈值（硬编码，不可被运行参数覆盖）：
- ≥90% → `pass`
- 70%-90% → `conditional_pass`
- <70% → `fail`

这些阈值对应 SPEC §14.4.4 的字段映射匹配分级。与 SPEC 的 >50% 停止条件相比，本 Design 采用更保守的起始阈值（>=90% pass），在首次 smoke 时优先确保兼容性。Pascal 可在审阅后调低（通过 `docs/design/decisions/` 记录）。

### 15.7 报告模型与脱敏（Reporter）

#### 15.7.1 SmokeReport DataClass

```python
# scripts/t4_preflight/models.py（设计草图）

@dataclass
class SmokeReport:
    """标准 smoke 报告模型。序列化为 YAML 时自动脱敏。"""
    metadata: SmokeMetadata          # capability, provider, smoke_at, test_target
    connectivity: ConnectionResult   # status, latency_ms, error
    auth: AuthResult                 # status, error
    permissions: PermissionResult    # status, note
    field_mapping: FieldMappingResult  # total_expected, matched, missing, extra, type_mismatches
    data_sample: DataSampleResult    # row_count, sample_rows, null_ratio
    vs_fixture: FixtureDeviationResult  # deviations list
    overall: OverallVerdict          # verdict (pass/conditional_pass/fail), memo
```

#### 15.7.2 Sanitizer 脱敏规则

YAML 序列化前自动应用以下规则：

| 规则 | 触发条件 | 处理 |
|---|---|---|
| Strip secret patterns | 字段值匹配 `mongodb://`、`https://`、`password`、`token`、`api_key` | 替换为 `"[REDACTED]"` |
| Truncate long strings | 长度 > 500 字符 | 截断为 `"$prefix... (${len} chars truncated)"` |
| Truncate large lists | 元素 > 100 个 | 取前 100，附加 `(and ${N-100} more)` |
| Remove null secrets | 任何 `SecretProbeResult` 的字段名含 `value`、`password`、`secret` | 从序列化输出中彻底移除 |

**绝对不保留**：原始 secret 值、长度（精确字符数）、URI（含 `mongodb://`、`https://`）、用户名、全路径+键值组合。

### 15.8 退出码分类

所有 T4 CLI 命令遵循统一退出码约定：

| 退出码 | 含义 | 对应 YAML verdict | 后续动作 |
|---|---|---|---|
| 0 | PASS — 所有检查通过 | `pass` | 可进入下一 Gate |
| 1 | CONDITIONAL PASS — 部分差异/警告 | `conditional_pass` | 需 Pascal 审阅后决定是否继续 |
| 2 | FAIL — 阻断性错误 | `fail` | 停止该 Gate 序列，不自动重试 |
| 3 | UNAUTHORIZED — secret 缺失或权限不足 | `unauthorized` | 不执行后续依赖的 smoke 步骤 |
| 128+ | 信号终止（SIGINT/SIGTERM） | — | 清理临时资源后退出 |

### 15.9 读路径零写入 Spy

验证 DataRouter.query() 对 P3 capability 不触发持久化写的 spy 机制：

```python
class MaterializeSpy:
    """Router._materialize() 调用的 spy/验证器。"""

    def __init__(self, router: DataRouter):
        self._original_materialize = router._materialize
        self.calls: list[tuple] = []
        router._materialize = self._spy  # monkey-patch

    def _spy(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        # 对 P3 capability — 记录但不执行实际写入
        if "sector" in str(args[0]) or "flow" in str(args[0]) or "sentiment" in str(args[0]):
            return  # skip actual write
        return self._original_materialize(*args, **kwargs)

    def assert_no_p3_calls(self):
        """断言 P3 capability 未触发 _materialize()。"""
        p3_called = any(
            any(p3_keyword in str(call) for p3_keyword in ("sector", "flow", "sentiment"))
            for call, _ in self.calls
        )
        assert not p3_called, f"P3 materialize called: {self.calls}"
```

此 spy 在 T4 Verify/Review 阶段注入 Router 实例，验证 `query()` 对 P3 capability 的 source_trace 不包含 `"ud_materialized"` 或 `"cache"` 条目（对应 SPEC A-021）。

### 15.10 Verify/Review 验收命令

#### 15.10.1 离线单元测试（T3 Implement + T4 Verify 公共基础）

```bash
# 全量回归
.venv/bin/python -m pytest skills/data/unified_data/tests -q --tb=short

# T4 工具链单元测试（mock/fake，无网络/MongoDB 依赖）
.venv/bin/python -m pytest tests/scripts/ -q --tb=short
```

#### 15.10.2 T4 密封测试（Review PASS 前——dry-run 模式）

```bash
# PR-0 dry-run: Secret 源不可达时验证错误处理
python -m scripts.t4_preflight.cli audit-secret
# 预期：dry-run 输出有界元数据，退出码 0，不含任何 secret

# PR-1 dry-run: 验证 import + 配置准备
python -m scripts.t4_preflight.cli preflight-mongo
# 预期：dry-run 报告 importable=true + 配置可达性，退出码 0

# PR-2 dry-run: 确认 smoke 初始化参数
python -m scripts.t4_preflight.cli smoke-sector
# 预期：输出 would_call=2，退出码 0

# PR-3 dry-run:
python -m scripts.t4_preflight.cli smoke-flow
# 预期：输出 would_call=3，退出码 0

# PR-4 dry-run:
python -m scripts.t4_preflight.cli smoke-sentiment
# 预期：输出 would_call=2，退出码 0

# A-021: 零写入 spy 验证（离线验证 DataRouter query() 无 materialize）
.venv/bin/python -m pytest tests/scripts/test_t4_reporter.py::test_zero_write_spy -q
```

**禁止通过 dry-run 泛化为生产结论**：dry-run 的导入+配置检查不得标注为「生产验证通过」。Review 报告必须明确区分 dry-run（离线）与 live-read（生产）结果。

#### 15.10.3 T4 Live-Read 命令（Review PASS 后执行）

以下命令仅在 Review 通过、Pascal 确认后执行。执行人为 Pascal 或 Pascal 授权的 DevOps（对应 SPEC §14.6 / RFC §13.6）：

```bash
# Step 1: PR-0 live — 实际验证 secret 可加载
python -m scripts.t4_preflight.cli audit-secret --live-read
# 输出：audit-result-YYYYMMDD.yaml，要求 overall.status=authorized

# Step 2: PR-1 live — 实际 MongoDB ping + 集合清单
python -m scripts.t4_preflight.cli preflight-mongo --live-read
# 输出：preflight-mongo-YYYYMMDD.yaml，要求 connectivity=success + p3_collections_found empty

# Step 3: PR-2 live — 真实 AKShare sector smoke
python -m scripts.t4_preflight.cli smoke-sector --live-read
# 输出：smoke-sector-YYYYMMDD.yaml

# Step 4: PR-3 live — 真实 AKShare flow smoke（可并行于 Step 3）
python -m scripts.t4_preflight.cli smoke-flow --live-read
# 输出：smoke-flow-YYYYMMDD.yaml

# Step 5: PR-4 live — 真实 AKShare sentiment smoke（可并行于 Step 3/4）
python -m scripts.t4_preflight.cli smoke-sentiment --live-read
# 输出：smoke-sentiment-YYYYMMDD.yaml
```

#### 15.10.4 Review 验收检查表

| # | 检查项 | 验证方式 | 通过条件 |
|---|---|---|---|
| RC-1 | 文件 allowlist 对齐 | `diff approved_list actual_files_created` | 无额外文件 |
| RC-2 | 所有 CL args 无 `--apply` | `grep -r "apply" scripts/t4_preflight/cli.py` | 0 匹配 |
| RC-3 | SecretVerifier 无泄漏 | `grep -r "os.getenv" scripts/t4_preflight/secrets.py` | 仅存在于 probe_env()，值不输出 |
| RC-4 | Mongo preflight 无写操作 | `grep -r "create_collection\|insert\|update\|delete\|bulk_write" scripts/t4_preflight/mongo_client.py` | 0 匹配 |
| RC-5 | Dry-run 默认行为验证 | `scripts/t4_preflight/cli audit-secret` → exit 0，不连接网络 | stdout 含 "dry-run" |
| RC-6 | 退出码标准化 | 每个命令的 error/status 映射到 {0,1,2,3} | pytest 参数化测试验证 |
| RC-7 | 报告脱敏 | YAML 输出不含 secret 模式 | `grep -c "REDACTED" report.yaml` ≥ 预期脱敏字段数 |
| RC-8 | 零写入 spy 测试通过 | `pytest tests/scripts/test_t4_reporter.py::test_zero_write_spy -q` | exit 0 |

### 15.11 Review PASS 后的 Live-Read 执行流程

1. **Reviewer 在 Review 报告中标记所有 RC 检查为 PASS**（RC-1 ~ RC-8）
2. **Pascal 审阅 Review 报告**，确认接受 RC 中发现的任何 `conditional_pass` 项
3. **Pascal 或授权 DevOps 执行 §15.10.3 的 live-read 命令**，按 PR-0 → PR-1 → PR-2/3/4（可并行）顺序
4. **每步 live-read 产出 YAML 报告**到 `docs/rfc/03_data/smoke_reports/`
5. **Pascal 审阅报告**，根据 SPEC §14.4.4 判定 verdict：
   - `pass` / `conditional_pass` → 可进入 PR-DDL-* Gate
   - `fail` / `unauthorized` → 停止序列，排查问题后重做
6. **Pascal 独立执行 PR-DDL**（DDL 脚本样式见 SPEC §14.6 / DESIGN §6.2），Pascal 手动执行
7. **Pascal 独立执行 PR-CANARY**：手动调用 `service.refresh_xxx()` 写入对应集合，验证 DataResult 返回正常

**Agent 不执行**：任何真实 DDL/DML/CANARY 写入（§6.2 集合创建脚本、§5.4 refresh 方法）在 Pascal Gate 授权前由 Pascal 手动执行。Agent 生成的 smoke 报告作为 Pascal 决策输入。

### 15.12 测试副作用输出治理（Principal 正式裁决）

T4 离线测试与默认 dry-run 会生成 fixture/report 输出；这些文件是可再生的测试副作用，不属于正式交付物。

#### 治理边界

| 输出类别 | 来源 | 治理策略 | 责任方 | 依据 |
|---|---|---|---|---|
| `tmp_out_mongo/` | `test_t4_preflight_mongo.py::test_cli_dry_run_exits_pass` 使用 `REPO_ROOT / "tmp_out_mongo"` | **推荐改为 `tmp_path`（pytest fixture）**：测试内生成的临时输出应走 `tmp_path`，自动清理，不依赖 `.gitignore` | Implement | 测试输出不应写入工作树；`tmp_path` 是 pytest 标准模式 |
| `docs/**/smoke_reports/` | CLI 默认 `--output-dir`（如 `smoke-sector --date 20260721` 的输出） | **保留 `.gitignore`**：该目录是 CLI 默认输出路径，供 Pascal 审阅；非测试产物，入 `.gitignore` 避免误提交 | 设计约束 | 这是 CLI 的公共接口行为，不是测试实现细节 |

#### 根 `.gitignore` 约束

根 `.gitignore` 固化以下行以确保 CI/审阅环境不误提交运行产物：

```gitignore
# T4 test side-effect outputs
tmp_out_mongo/
docs/**/smoke_reports/
```

- **不添加 `tmp_t5_*/`**：该类临时目录已清理，当前测试不再生成。

> **裁决说明**：`tmp_out_mongo/` 属于「历史兼容模式」——它由 Developer 在 Implement 阶段创建，已在 V0.8 入 `.gitignore` 防止误提交。Implement 阶段应将其迁移至 `tmp_path`，届时可删除该 `.gitignore` 行。本文档不修改代码/`.gitignore`，仅做正式裁决与边界声明。

### 15.13 T4 设计文件与 RFC/SPEC 一致性检查

| RFC §13 | SPEC §14 | DESIGN §15 | 一致性 |
|---|---|---|---|
| §13.1 副作用矩阵 | §14.1 副作用矩阵 | §15.3 公共安全契约 + §15.5/15.6 约束 | ✅ 设计实现 RFC/SPEC 约束 |
| §13.2 MongoDB 预检规程 | §14.2 MongoDB 预检规程 | §15.5 MongoDB 零写入预检 | ✅ 对齐停止条件与白名单 |
| §13.3 Secret Source 审计 | §14.3 Secret Source 审计 | §15.4 SecretVerifier + 候选矩阵 | ✅ 非泄露三布尔 |
| §13.4 Provider Smoke | §14.4 Provider Smoke | §15.6 AKShare 安全调用包装 | ✅ 单标的 ≤3 日 |
| §13.5 Zero-Persistence-Write | §14.5 Zero-Persistence-Write | §15.9 零写入 spy | ✅ 通过 spy 模式验证 |
| §13.6 DDL/DML 独立 Gate | §14.6 DDL/DML 独立 Gate | §15.11 Live-Read 执行流程 | ✅ DDL 仍 Pascal 独立 Gate |
| §13.7 成功标准 | §14.7 成功标准 | §15.10 Verify/Review 验收 | ✅ 退出码 + 检查表 |

---

## 16. 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.9 | 2026-07-22 | **Principal 正式裁定收口（本卡 T5C2）**。正式确认 §15.2 allowlist 的 `scripts/__init__.py` package marker 进入正式契约；§15.12 重写为分类治理边界：`tmp_out_mongo/` 推荐 Implement 阶段迁移至 `tmp_path`（`docs/**/smoke_reports/` 保持 `.gitignore`）。V0.8 由 Developer 临时落地，本版由 Principal 正式裁决。RFC-03-014 / SPEC-03-014 不变（allowlist 属 DESIGN 级实现细节）。 | **YQuant-Principal** |
| V0.8 | 2026-07-22 | **T4 测试副作用收口（临时落地）**。§15.2 allowlist 由 22 增至 23 个正式文件，新增 `scripts/__init__.py` package marker；§15.12 固化 `tmp_out_mongo/` 与 `docs/**/smoke_reports/` 的根 `.gitignore` 规则。RFC-03-014 / SPEC-03-014 不变。 | YQuant-Developer-Engineer |
| V0.7 | 2026-07-22 | **T4 Preflight & Smoke 工具链设计**（新增 §15）。定义 T4 阶段的 22 文件 allowlist、CLI 入口与安全契约、SecretVerifier 非泄露接口、MongoDB 零写入预检、Provider smoke 安全包装、报告脱敏、退出码分类、零写入 spy 机制、Verify/Review 验收命令与 Review PASS 后的 live-read 执行流程。与 RFC-03-014 V0.3 §13 及 SPEC-03-014 V0.3 §14 完全对齐。 | YQuant-Codex-Principal |
| V0.6 | 2026-07-22 | Contract Gate Adjudication — 闭合 Fix-M23 Review 发现的 PersistenceResult §5.4.1 契约冲突 | YQuant-Principal |
| V0.5 | 2026-07-21 | Design Correction（T2.8 闭合 MINOR-N2） | YQuant-Principal |
| V0.4 | 2026-07-21 | Design Correction（T2.6 消除 T2.5 REVISE 阻断） | YQuant-Principal |
| V0.3 | 2026-07-21 | Design Correction（T2.4 实现边界冻结） | YQuant-Principal |
| V0.2 | 2026-07-21 | Design Correction（T2.2 REVISE） | YQuant-Principal |
| V0.1 | 2026-07-21 | 初始创建 | YQuant-Principal |
