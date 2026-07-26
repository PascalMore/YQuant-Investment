# DESIGN-03-014: Unified Data Phase 3 — 受控持久化扩展详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-21 |
| 最后更新 | 2026-07-26（V0.17 Pascal C+X2 决策同步 — 工具链设计收敛：依据 RFC-03-014 §13.4.5 V0.11 / SPEC-03-014 §14.4.5 V0.10 的 C+X2 决策，§4.2.1 PR-3 三选一收敛为 C（northbound_net_inflow 恒 None，不指向真实 endpoint，不引入 A/B endpoint skeleton）；§4.2.1 PR-4 空返回语义收敛为 X2（verdict=fail 保守，移除 empty_semantics 分类）；§15.14 reporter 账本移除 worktree_changed/empty_semantics，仅保留 provider_attempts/actual_calls/retry_count/fallback_count/mongo_calls/write_operations；§15.14.1 northbound 字段集标注 C 已选；§15.14.2 endpoint 选择逻辑标注 C 已选；§15.14.4/§15.14.5/§15.14.6 同步更新。删除全部「未选择/阻塞等待 Pascal」失效文本。不动 §3 domain object、不动 §6.4 DDL 契约、不动既有授权范围） |
| 版本号 | V0.17 |
| 来源 RFC | RFC-03-014（Phase 3 持久化扩展，V0.11） |
| 来源 SPEC | SPEC-03-014（Phase 3 持久化扩展契约，V0.10） |
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
| V0.3 | 2026-07-21 | **Design Correction（T2.4 实现边界冻结）**。消除 T2.3 独立复审遗留的 1 MAJOR + 1 MINOR 图文歧义：① §2.1 明确 post-Gate `_materialize()` 写入路径经由 P3PersistenceWriter 而非 LocalMongoAdapter（图文一致，与 §0.4/§7.4 对齐）；② §0.4 补充 `UpsertOutcome` dataclass 定义（P3PersistenceWriter.upsert() 返回类型冻结）；③ §2.1 测试验证目标精确化为 P3PersistenceWriter 写入路径。 | YQuant-Principal |
| V0.4 | 2026-07-21 | **Design Correction（T2.6 消除 T2.5 REVISE 阻断）**。关闭 T2.5 Synthesis 提出的 2 BLOCKING + 1 MAJOR + 4 MINOR 共 7 项 finding：① BLOCKING ① §2.1 l.229 post-Gate `_materialize()` 写入违背只读承诺 → 重写为"查询路径保持只读，写入仅 refresh 路径"；② BLOCKING ② §0.4/§2.1 关于 `_try_materialized()` 的内部冲突 → 采用方案 A（允许最小扩展：追加 capability 参数 + P3PersistenceWriter 注入，显式声明为 query() 编排的唯一例外）；③ MINORs 全数对齐 RFC/SPEC 一致性与措辞。 | YQuant-Principal |
| V0.5 | 2026-07-21 | **Design Correction（T2.8 闭合 MINOR-N2）**。闭合 T2.7 REVISE 发现的 MINOR-N2：§4.5 l.704（client 层 `security_id: SecurityId | None = None`）与 §5.2 l.842-844（service 层 `security_id: SecurityId` 必填）签名矛盾——采用方案 Y，§5.2 统一为 `security_id: SecurityId | None = None`（匹配 §4.5 与 SPEC §5.1 l.577）。移除"必填/不得 placeholder"措辞，改为"默认 None=市场级，非 None=个股级"。SPEC §5.1 已为 optional 无需修改；RFC 无签名引用无需修改。 | YQuant-Principal |
| V0.6 | 2026-07-22 | **Contract Gate Adjudication（T3-P3B 契约裁断）**。闭合 Fix-M23 Review 发现的 PersistenceResult 形状冲突：采纳方向 B（实现形状可接受），将 §5.4.1 中 `PersistenceStatus` Enum + 多字段 canonical 定义替换为 P3-B FlowService 的实际 `PersistenceResult(frozen, slots)` 实现（`status: str` / `capability` / `collection` / `persisted` / `failed` / `skipped` / `reason` / `writer_outcome`）；同步更新 §5.4.2 模板代码、§2.2 constraint #6 `overall_status→status`、§2.3 场景表字段对齐。RFC/SPEC 无此项引用，不受影响。 | YQuant-Principal |
| V0.13 | 2026-07-25 | **B1-P3A DDL 契约冻结**。新增 §6.4（P3-A DDL 执行、回滚、审计、失败矩阵、退出码），面向 PR-DDL-P3A Gate：§6.4.1 rollback 脚本（dropIndex 反向顺序 + dropCollection，落到 `/tmp/yquant-p3-ddl-p3a-20260725/rollback.js`）；§6.4.2 audit.json 字段定义（`{operation, collection, index, ts, exit_code, error, rollback_script_path}`，不引入新 audit 集合）；§6.4.3 失败处理矩阵（已存在/index 冲突/auth 失败/timeout/网络，全部 fail-stop 不自动回滚）；§6.4.4 退出码 0/2/3/4（与 SPEC §14.6.4 对齐，退出码 1 不使用以避免与 §15.5.4 PR-1 conditional pass 歧义）。仅冻结 P3-A；P3-B/P3-C 的对应 §6.4 版本待各自 B1 阶段独立补充。不引入新依赖、不动既有 §3.1/§6.1/§6.2/§6.3。 | YQuant-Principal |
| V0.14 | 2026-07-25 | **B1-P3B DDL 契约冻结**。新增 §6.4.bis（P3-B DDL 执行、回滚、审计、失败矩阵、退出码），面向 PR-DDL-P3B Gate：§6.4.bis.1 rollback 脚本（dropIndex 反向顺序 + dropCollection，落到 `/tmp/yquant-p3-ddl-p3b-20260725/rollback-p3b.js`，两条索引 `symbol_trade_date` / `trade_date`）；§6.4.bis.2 audit-p3b.json 字段定义（与 P3-A 同字段集 `{operation, collection, index, ts, exit_code, error, rollback_script_path}`，collection 固定 `03_data_ud_stock_capital_flow`）；§6.4.bis.3 失败处理矩阵（preflight 已存在→exit 2、collection create fail→exit 3、index create fail→exit 4，全部 fail-stop 不自动回滚，DDL 前必做独立 read-only probe）；§6.4.bis.4 退出码 0/2/3/4（与 SPEC §14.6.bis 对齐，语义按 task 授权：0=PASS / 2=preflight target already exists / 3=collection create fail / 4=index create fail）。同步更新 §6.4 授权范围标注「P3-B 已在 §6.4.bis 冻结」。仅冻结 P3-A + P3-B；P3-C 仍阻塞。不引入新依赖、不动既有 §3.1/§6.1/§6.2/§6.3。 | YQuant-Principal |
| V0.15 | 2026-07-25 | **B1-P3C DDL 契约冻结**。新增 §6.4.ter（P3-C DDL 执行、回滚、审计、失败矩阵、退出码），面向 PR-DDL-P3C Gate：§6.4.ter.1 rollback 脚本（dropIndex 反向顺序 + dropCollection，落到 `/tmp/yquant-p3-ddl-p3c-20260725/rollback-p3c.js`，两条索引 `snapshot_date` / `snapshot_time`）；§6.4.ter.2 audit-p3c.json 字段定义（与 P3-A/P3-B 同字段集 `{operation, collection, index, ts, exit_code, error, rollback_script_path}`，collection 固定 `03_data_ud_market_sentiment_snapshot`）；§6.4.ter.3 失败处理矩阵（preflight 已存在→exit 2、collection create fail→exit 3、index create fail→exit 4，全部 fail-stop 不自动回滚，DDL 前必做独立 read-only probe）；§6.4.ter.4 退出码 0/2/3/4（与 SPEC §14.6.ter 对齐，语义按 task 授权：0=PASS / 2=preflight target already exists / 3=collection create fail / 4=index create fail）。同步更新 §6.4 / §6.4.bis 授权范围标注「P3-A + P3-B + P3-C 均已在 §6.4 / §6.4.bis / §6.4.ter 冻结」。仅冻结 P3-A + P3-B + P3-C；Phase 3 三子阶段 DDL 全部授权。不引入新依赖、不动既有 §3.1/§3.2/§3.3/§6.1/§6.2/§6.3/§6.4/§6.4.bis。 | YQuant-Principal |
| V0.16 | 2026-07-26 | **B2 实测映射契约冻结 — 工具链设计**。依据 RFC-03-014 §13.4.5 V0.10 / SPEC-03-014 §14.4.5 V0.9 冻结的可执行契约，在 §4.2 更新 AKShare→Canonical 映射模式（PR-3 北向持股历史≠净流入三选一、PR-4 empty_semantics 空返回语义区分、PR-2 未 live-read 验证的 expected 字段集标注），在 §15.14 新增 B2 工具链设计（expected 字段集、endpoint 选择逻辑、reporter 账本字段、fixture 更新、验证计划）。同步更新 §15.13 一致性表追加行。不动 §3 domain object、不动 §6.4 DDL 契约、不动既有授权范围。 | YQuant-Principal |
| V0.17 | 2026-07-26 | **Pascal C+X2 决策同步 — 工具链设计收敛（Recovery/T2.5）**。依据 RFC-03-014 §13.4.5 V0.11 / SPEC-03-014 §14.4.5 V0.10 的 Pascal C+X2 决策：(1) §4.2.1 PR-3 三选一收敛为 **C**——northbound_net_inflow 恒 None，fetch 路径不指向真实 endpoint，不引入 A/B endpoint skeleton，持股历史仅作辅助参考。(2) §4.2.1 PR-4 空返回语义收敛为 **X2**——verdict=fail（保守），移除 empty_semantics 三分类。(3) §15.14.1 northbound expected 字段集标注 C 已选（4~6 行 northbound_* 标注恒 None）。(4) §15.14.2 endpoint 选择逻辑标注 C 已选。(5) §15.14.3 reporter 账本移除 worktree_changed/empty_semantics，仅保留 6 个必要字段。(6) §15.14.4 fixture、§15.14.5 验证计划、§15.14.6 风险表同步更新。删除全部「未选择/阻塞等待 Pascal」失效文本。§3 domain object、§6.4 DDL 契约、§15.13 一致性表、既有授权范围不变。 | YQuant-Principal |

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
| 7 | FreshnessPolicy `DEFAULT_TTLS` 追加 | —（sector=21600：值已决定，将于 T3 按 §4.4 顺序显式追加） | flow=43200 | sentiment=3600 |
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

#### 4.2.1 B2 实测映射修正（依据 RFC-03-014 §13.4.5 / SPEC-03-014 §14.4.5 冻结契约）

**冻结证据**：2026-07-26 B2 一次性只读 smoke 报告的只读副本位于 `/tmp/yquant-b2-pr234-20260726/`（pr2/smoke-sector.yaml / pr3/smoke-flow.yaml / pr4/smoke-sentiment.yaml）。不可移动/提交/重跑。本阶段已用尽 live-read 预算（PR-2=2 / PR-3=3 / PR-4=2），T2/T3 不得以「需要再验证」为由重跑。

**PR-3 `flow.northbound_daily` — 端点到语义不匹配（关键阻断）**

| 维度 | B2 冻结值 |
|---|---|
| 实际 endpoint | `akshare.stock_hsgt_individual_em(symbol='600519')` |
| 网络层 | success（~1131ms），auth=authorized，permissions=ok |
| 实际返回字段（9 个） | `持股日期` / `当日收盘价` / `当日涨跌幅` / `持股数量` / `持股市值` / `持股数量占A股百分比` / `今日增持股数` / `今日增持资金` / `今日持股市值变化` |
| 现有 expected（脚本中） | `date` / `stock` / `northbound_net_inflow` + 8 个资金流字段 = 11，matched 0/11 |
| **语义判定** | 返回**北向持股历史**（holding history），**非北向净流入**（net inflow） |
| **禁止伪装** | 将 `持股数量`/`持股市值`/`今日增持资金` 映射为 `northbound_net_inflow` 的别名 → **FAIL**，退回 |
| **禁止伪装** | 在 `CapitalFlowRecord.northbound_net_inflow` 中静默填入持股语义值 → **FAIL** |
| **禁止伪装** | 在 mapping 文档中把「持股历史」表述为「净流入」 → **FAIL** |

**Pascal 决策（2026-07-26）：选 C — 放弃净流入，字段保持 None**

Pascal 已明确选择 **C**：当前 Phase 3 不提供北向净流入数据，`northbound_net_inflow` 保持 None，持股历史作为辅助保留。选项 A、B 均**未被选择**。

| 选项 | 落地动作 | 影响 | 状态 |
|---|---|---|---|
| **A. 分流到正确 endpoint** | 在 AKShare 中寻找真正返回北向净流入的 endpoint（候选：`stock_hsgt_fund_flow_summary_sina` / `stock_em_hsgt_north_net_flow_in`），将 `flow.northbound_daily` fetch 路径指向它 | 需新增 capability（超出本卡范围，需 Pascal 确认） | **未选（Pascal 2026-07-26 明确放弃）** |
| **B. 变更 capability 语义** | 将 `flow.northbound_daily` 语义改为「北向持股历史」，回头修订 SPEC §3.2 `CapitalFlowRecord` `northbound_*` 字段定义 | 下游消费方契约变更；本卡允许，但须 Pascal 确认 | **未选（Pascal 2026-07-26 明确放弃）** |
| **C. Pascal 确认放弃净流入（已选）** | 当前 Phase 3 不提供北向净流入；`northbound_net_inflow` 保持 None；持股历史作为辅助保留 | 能力缺口（已接受） | **✅ Pascal 2026-07-26 已确认选择** |

**C 选项落地约束（硬约束，T2/T3 须遵守）**：
- `flow.northbound_daily` capability **保留**，但其 fetch 路径在当前 Phase 3 **不指向任何真实 endpoint**——`northbound_net_inflow` 恒为 None。
- `CapitalFlowRecord.northbound_net_inflow`（SPEC §3.2）字段定义**不变**（仍为 `float | None = None`），只是当前 Phase 3 永不填充非 None 值。
- 持股历史（B2 返回的 9 个持股字段）作为**辅助参考**，可在 DESIGN 工具链中以参考字段标注，但**不得**映射入 `northbound_net_inflow` 或任何 `*_net_inflow` 字段。
- 不引入新 endpoint、新 capability、新 endpoint skeleton（A 选项的候选 endpoint 不在当前 Phase 3 范围）。

**PR-4 `sentiment.market_snapshot`+`sentiment.limit_up_pool` — 空返回语义分类**

| 维度 | B2 冻结值 |
|---|---|
| 实际 endpoint | `akshare.stock_market_fund_flow()` + `akshare.stock_zt_pool_em(date)` |
| 网络层 | success（~1525ms），auth=authorized，permissions=ok |
| row_count | 0（两调用均为空） |
| actual_fields | 0，matched 0/31，missing=[] |
| **本次判定** | verdict=fail（保守，X2）——空返回不进一步细分原因 |
| **后续收敛** | 后续独立 live-read（非本阶段）在交易日复验；reporter 不输出 `empty_semantics` 字段（X2 已移除） |

**Pascal 决策（2026-07-26）：选 X2 — 空返回语义收敛为保守 fail，移除 empty_semantics 分类**

空返回维持 verdict=fail（保守）。原三分类（undetermined/no_trading_data/schema_drift/call_anomaly）的 `empty_semantics` reporter 字段在 X2 下**移除**。后续独立 live-read 在交易日复验时，若返回非空数据则按正常字段匹配流程判定。

| B2 观测事实 | X2 下的 verdict |
|---|---|
| row_count=0 且 actual_fields=0（本次 B2 即此） | **fail**（保守，不进一步细分原因） |
| endpoint 抛异常、返回非 DataFrame、JSON 解析失败 | **fail**（停止该子阶段；记录异常类；不自动重试） |

**PR-2 `sector.snapshot` — SSL 网络停止 + 推断字段集**

| 维度 | B2 冻结值 |
|---|---|
| 实际 endpoint | `akshare.stock_board_industry_cons_em("BK0489")` ×2 |
| 网络层 | **failed** — 两调用均 SSLError（`requests.exceptions`），latency=null |
| `endpoint_status` | `endpoint_unreachable`（egress restriction，非代码 defect） |
| auth/permissions | authorized/restricted |
| **mapping 修复策略** | expected 字段集基于 AKShare 公开文档 + 离线 fixture 推断更新；**标注「未 live-read 验证」** |
| **禁止行为** | PR-2 SSL 失败不得与 PR-3/PR-4 mapping 修复耦合；仅允许后续单变量网络诊断（Pascal 独立授权） |

**PR-2 `sector.snapshot` expected 字段集（推断版，未 live-read 验证）**：

| SectorSnapshot 字段 | 推断 AKShare 列 | 置信度 | 来源 |
|---|---|---|---|
| sector_code | `板块代码` | medium | AKShare `stock_board_industry_cons_em` 公开文档 |
| sector_name | `板块名称` | high | 同上 |
| sector_type | `industry`（固定） | high | 接口限定东方财富行业板块 |
| snapshot_date | `交易日期` | medium | 惯例 |
| rank | `排名` | low | 需 live-read 确认 |
| pct_chg | `涨跌幅` | high |  |
| leading_stock | `领涨股代码` | medium |  |
| leading_stock_name | `领涨股名称` | medium |  |
| leading_pct_chg | `领涨股涨幅` | low |  |
| advance_count | `上涨家数` | medium |  |
| decline_count | `下跌家数` | medium |  |
| total_count | `总家数` | medium |  |
| turnover_rate | `换手率` / `换手率%` | low |  |
| main_net_inflow | `主力净流入` | low |  |
| members | 成分股代码列表（接口限定） | medium | 接口返回值 `members` 字段 |

> 上表为**推断版**，置信度标注为 low/medium/high。T3 Implement 须据此实现映射，但**必须标注「未 live-read 验证」**。后续独立 live-read（非本阶段）在 SSL 诊断通过后复验。

**零写入边界（已遵守，T2/T3 须继承）**：无重试 / 无 fallback / 零 Mongo 写入 / 零 Cache 写入 / 零 AuditLogger 写入 / 零 DDL / 零 cron 注册。

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
| **某子阶段 Gate 尚未确认** | p3_writer 为 None，refresh 方法返回 `PersistenceResult(status="skipped", skipped=True, reason="write_forbidden")`。**不得**静默跳过写入后返回假成功 |
| **Provider fetch 部分成功** | 返回 `PersistenceResult(status="partial_failure")`，已获取的记录正常写入，缺失的记录通过 `writer_outcome.failed_keys` 回溯 |
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

### 6.4 P3-A DDL 执行、回滚与审计契约（B1-P3A 冻结）

> **授权范围（B1-P3A）**：本节**仅**冻结 P3-A 子阶段 `03_data_ud_market_sector_snapshot` 的 DDL 范围、回滚脚本、audit 字段、失败处理与退出码。P3-B 的 DDL 契约已在 §6.4.bis 独立冻结；P3-C 的 DDL 契约已在 §6.4.ter 独立冻结。权威的集合创建与索引脚本以 §6.2 为准；本节定义其执行语义、失败处理与可审计工件。

本节面向 **PR-DDL-P3A** Gate（SPEC §14.6.4 / RFC §13.6）。约束：

- **写入目标**：仅集合 `03_data_ud_market_sector_snapshot`，库 `tradingagents`，主仓 `main` 本地工作树。
- **写入身份**：复用现有 `MONGODB_USERNAME`（Phase 2 PortfolioMongoLoader 已验证的组件式构造连接，非 URI）。DDL 完成后权限摘要落到 `/tmp/yquant-p3-ddl-p3a-20260725/audit.json`。最小权限收敛（如 DDL 专用角色/收回 createCollection 权限）放到后续独立 Gate，不在本契约内。
- **索引定义**：完全照 §6.2 当前定稿版本——三条索引名 `sector_code_date` / `snapshot_date` / `sector_type_date`，全部 `background: true`。本节不重新定义索引，仅引用 §6.2。
- **写入原子性**：失败即停，**不自动回滚**。`createCollection` 与 `createIndex` 在目标已存在时 fail-stop，由操作员手动评估（见 §6.4.3）。
- **写入前审计**：仅 stdout 与 `/tmp/yquant-p3-ddl-p3a-20260725/audit.json`，字段定义见 §6.4.2。**不引入**新的 audit 集合（`03_data_ud_query_audit` 写入属 Phase 2，不在本 Gate）。
- **不授权范围**：不 refresh、不 upsert 业务数据、不写 Cache、不写 AuditLogger、不写 QualitySummary、不动 cron/systemd、不动 `.env`、不建新角色、不动生产代码树（本节为设计文档增补 + `/tmp` 下 rollback.js 文件生成）。

#### 6.4.1 Rollback 脚本（drop 顺序）

回滚脚本随 DDL 同步生成到 `/tmp/yquant-p3-ddl-p3a-20260725/rollback.js`（**不提交到仓库**），作为操作员手动回滚的安全网。脚本权威内容（与 §6.2 创建脚本严格对称）：

```javascript
// P3-A rollback: 回滚 03_data_ud_market_sector_snapshot 的 DDL
// 适用场景：DDL 全部成功后操作员决定撤销；或 DDL 部分成功后清理残留。
// 顺序：先逐条 dropIndex（反向），再 dropCollection。
// 失败即停，不自动级联——由操作员逐条评估。

// Step 1: 反向 dropIndex（与 §6.2 创建顺序相反）
db["03_data_ud_market_sector_snapshot"].dropIndex("sector_type_date");
db["03_data_ud_market_sector_snapshot"].dropIndex("snapshot_date");
db["03_data_ud_market_sector_snapshot"].dropIndex("sector_code_date");

// Step 2: dropCollection
db["03_data_ud_market_sector_snapshot"].drop();
```

**部分索引已建的处理**：若 `createIndex` 仅成功前 N 条即失败（§6.4.3 的 `INDEX_PARTIAL` 场景），操作员按**已实际建成索引的反向顺序**逐条 `dropIndex`，最后执行 `dropCollection`。`dropCollection` 本身会级联删除剩余索引，因此即便跳过逐条 `dropIndex` 也可完成回滚——逐条 `dropIndex` 的价值在于让操作员在每一步确认状态，而非功能性必需。

**回滚脚本边界**：

- 回滚脚本仅处理 P3-A 一个集合；P3-B 的回滚脚本见 §6.4.bis.1，P3-C 的回滚脚本见 §6.4.ter.1。
- 回滚脚本是**安全网**，不是自动机制——DDL 失败时 **fail-stop**，等待操作员决定是否运行回滚（见 §6.4.3 失败矩阵的「operator action」列）。
- 回滚脚本不删除业务数据——DDL 之前该集合不存在业务数据，DDL 之后若已运行 CANARY 写入则业务数据回滚属 PR-CANARY 清理脚本职责，不在本 §6.4 范围。

#### 6.4.2 Audit JSON 字段定义

DDL 执行过程产出结构化审计，落到 stdout（人类可读）与 `/tmp/yquant-p3-ddl-p3a-20260725/audit.json`（机读）。**不引入**新 audit 集合；本 JSON 为本次 DDL 的单次工件，非持续写入。

`audit.json` 为 JSON 数组，每个元素描述一次原子操作（`createCollection` / 每条 `createIndex`），字段定义：

| 字段 | 类型 | 说明 |
|---|---|---|
| `operation` | string | `"createCollection"` / `"createIndex"` |
| `collection` | string | 固定为 `"03_data_ud_market_sector_snapshot"`（P3-A 范围） |
| `index` | string \| null | `createIndex` 操作时为索引名（`sector_code_date` / `snapshot_date` / `sector_type_date`）；`createCollection` 时为 `null` |
| `ts` | string | 操作完成（或失败）的 ISO-8601 时间戳，带时区 |
| `exit_code` | int | 该操作的退出码（见 §6.4.4）：`0`=成功，`2`=DDL 失败，`3`=权限不足，`4`=目标已存在（fail-stop） |
| `error` | string \| null | 失败时的错误摘要（**不含** secret / 连接串 / 凭据明文）；成功时为 `null` |
| `rollback_script_path` | string | 固定指向 `/tmp/yquant-p3-ddl-p3a-20260725/rollback.js`，便于操作员快速定位回滚脚本 |

**审计约束**：

- `audit.json` 不记录任何凭据值、URI、用户名、密码长度——与 SPEC §14.1 / RFC §13.1 的 secret 禁输出原则一致。
- `audit.json` 是单次 DDL 工件，**不**作为 `03_data_ud_query_audit`（Phase 2 AuditLogger 集合）的替代或前身。
- `audit.json` 落在 `/tmp`，不提交仓库，不纳入 cron/systemd。

#### 6.4.3 失败处理矩阵

DDL 执行（`createCollection` → 三条 `createIndex`）的失败场景、对应退出码与操作员动作：

| 场景 | 触发信号 | 退出码 | operator action |
|---|---|---|---|
| `createCollection` 成功 + 三条 `createIndex` 全部成功 | `audit.json` 全部 `exit_code=0` | **0**（整体成功） | 无需动作；进入 PR-CANARY-P3A 评估 |
| `createCollection` 成功但某条 `createIndex` 失败 | 该条 `exit_code=2`，`error` 含索引错误 | **2**（DDL 失败） | fail-stop；操作员评估是否运行 `rollback.js`（§6.4.1）清理残留索引+集合 |
| `createCollection` 失败（非已存在） | `createCollection` 行 `exit_code=2` | **2**（DDL 失败） | fail-stop；集合未创建，无需回滚；排查 Mongo 错误后重试需 Pascal 重新授权 |
| 目标集合已存在 | `createCollection` 行 `exit_code=4` | **4**（fail-stop） | fail-stop；**不自动覆盖**；操作员确认是遗留还是意外，参考 PR-1 `p3_collections_found` 结论决定是否降级处理 |
| 索引已存在（createCollection 成功后某索引名冲突） | 对应 `createIndex` 行 `exit_code=4` | **4**（fail-stop） | fail-stop；操作员确认索引定义是否与 §6.2 一致，决定保留或 dropIndex 后重建 |
| 认证 / 权限不足（无 createCollection 或 createIndex 权限） | `exit_code=3`，`error` 含 auth/permission 摘要 | **3**（权限不足） | fail-stop；不重试；Pascal 授予 DDL 所需权限或换连接身份后重新授权 |
| 网络超时 / 连接中断 | `exit_code=2`，`error` 含 timeout/网络摘要 | **2**（DDL 失败） | fail-stop；不自动重试；操作员确认 Mongo 连通性（参考 PR-1 结论）后由 Pascal 决定是否重试 |

**通用原则**：

- **fail-stop，不自动回滚**：任何非 0 退出码立即停止后续步骤，**不**自动运行 `rollback.js`。是否回滚由操作员按上表「operator action」列判断。
- **已存在 = fail-stop 而非覆盖**：`createCollection` / `createIndex` 在目标已存在时返回 exit 4，等待操作员评估——绝不静默覆盖既有集合或索引。
- **不自动重试**：与 PR-smoke 的「不自动重试」原则一致（RFC §6.4 / SPEC §14.8）。失败后重试需 Pascal 重新授权。
- **secret 安全**：`error` 字段不得包含凭据、URI、用户名、密码长度——仅含操作类型与失败类别摘要。

#### 6.4.4 退出码（与 SPEC §14.6.4 对齐）

本 §6.4.4 退出码**仅**作用于 PR-DDL-P3A 的 DDL 执行阶段（`createCollection` + `createIndex`），与 §15.5.4 的 PR-1 只读预检退出码（0/1/2/3，针对 ping + list_collections）**不冲突**——两者作用于不同 Gate（PR-DDL-P3A vs PR-1）、不同操作（DDL 写入 vs 只读连通性检查）。

| 退出码 | 含义 | 对应场景 |
|---|---|---|
| **0** | DDL 成功 | `createCollection` + 三条 `createIndex` 全部成功 |
| **2** | DDL 失败（非权限、非已存在） | `createCollection` / `createIndex` 执行错误、网络超时、连接中断 |
| **3** | 权限不足 | 认证拒绝或缺少 createCollection / createIndex 权限 |
| **4** | 目标已存在（fail-stop） | 集合或索引已存在，等待操作员评估 |

退出码 1 在本 DDL 契约中**不使用**（1 在 §15.5.4 中表示 PR-1 的 conditional pass，语义不同，避免歧义）。退出码 ≥5 为后续 Gate 预留，本 P3-A 契约不定义。

---

### 6.4.bis P3-B DDL 执行、回滚与审计契约（B1-P3B 冻结）

> **授权范围（B1-P3B）**：本节**仅**冻结 P3-B 子阶段 `03_data_ud_stock_capital_flow` 的 DDL 范围、回滚脚本、audit 字段、失败处理与退出码。P3-A 的 DDL 契约已在 §6.4 独立冻结；P3-C 的 DDL 契约已在 §6.4.ter 独立冻结。权威的集合创建与索引脚本以 §6.2 为准；本节定义其执行语义、失败处理与可审计工件。

本节面向 **PR-DDL-P3B** Gate（SPEC §14.6.bis / RFC §13.6）。约束：

- **写入目标**：仅集合 `03_data_ud_stock_capital_flow`，库 `tradingagents`，主仓 `main` 本地工作树。
- **写入身份**：复用现有 `MONGODB_USERNAME`（Phase 2 PortfolioMongoLoader 已验证的组件式构造连接，非 URI；与 P3-A 同一账号）。DDL 完成后权限摘要落到 `/tmp/yquant-p3-ddl-p3b-20260725/audit-p3b.json`。**不**新建最小权限角色（依赖链复杂，DDL 完成后仅在 audit JSON 中记录账号权限摘要；最小权限收敛放到后续独立 Gate）。
- **索引定义**：完全照 §6.2 当前定稿版本——两条索引名 `symbol_trade_date`（`{symbol:1, trade_date:-1}`）与 `trade_date`（`{trade_date:-1}`），全部 `background: true`。本节不重新定义索引，仅引用 §6.2。
- **写入原子性**：失败即停，**不自动回滚**。`createCollection` 与 `createIndex` 在目标已存在时 fail-stop，由操作员手动评估（见 §6.4.bis.3）。
- **写入前审计**：仅 stdout 与 `/tmp/yquant-p3-ddl-p3b-20260725/audit-p3b.json`，字段定义见 §6.4.bis.2。**不引入**新的 audit 集合（`03_data_ud_query_audit` 写入属 Phase 2，不在本 Gate）。
- **不授权范围**：不 refresh、不 upsert 业务数据、不写 Cache、不写 AuditLogger、不写 QualitySummary、不动 cron/systemd、不动 `.env`、不建新角色、不动生产代码树（本节为设计文档增补；`/tmp` 下 rollback-p3b.js 文件由下游 Implement 阶段生成，不在本 §6.4.bis 范围）。

#### 6.4.bis.1 Rollback 脚本（drop 顺序）

回滚脚本随 DDL 同步生成到 `/tmp/yquant-p3-ddl-p3b-20260725/rollback-p3b.js`（**不提交到仓库**），作为操作员手动回滚的安全网。脚本权威内容（与 §6.2 创建脚本严格对称）：

```javascript
// P3-B rollback: 回滚 03_data_ud_stock_capital_flow 的 DDL
// 适用场景：DDL 全部成功后操作员决定撤销；或 DDL 部分成功后清理残留。
// 顺序：先逐条 dropIndex（反向），再 dropCollection。
// 失败即停，不自动级联——由操作员逐条评估。

// Step 1: 反向 dropIndex（与 §6.2 创建顺序相反）
db["03_data_ud_stock_capital_flow"].dropIndex("trade_date");
db["03_data_ud_stock_capital_flow"].dropIndex("symbol_trade_date");

// Step 2: dropCollection
db["03_data_ud_stock_capital_flow"].drop();
```

**部分索引已建的处理**：若 `createIndex` 仅成功前 N 条即失败（§6.4.bis.3 的 `INDEX_PARTIAL` 场景），操作员按**已实际建成索引的反向顺序**逐条 `dropIndex`，最后执行 `dropCollection`。`dropCollection` 本身会级联删除剩余索引，因此即便跳过逐条 `dropIndex` 也可完成回滚——逐条 `dropIndex` 的价值在于让操作员在每一步确认状态，而非功能性必需。

**回滚脚本边界**：

- 回滚脚本仅处理 P3-B 一个集合；P3-A 的回滚脚本见 §6.4.1，P3-C 的回滚脚本见 §6.4.ter.1。
- 回滚脚本是**安全网**，不是自动机制——DDL 失败时 **fail-stop**，等待操作员决定是否运行回滚（见 §6.4.bis.3 失败矩阵的「operator action」列）。
- 回滚脚本不删除业务数据——DDL 之前该集合不存在业务数据，DDL 之后若已运行 CANARY 写入则业务数据回滚属 PR-CANARY 清理脚本职责，不在本 §6.4.bis 范围。

#### 6.4.bis.2 Audit JSON 字段定义

DDL 执行过程产出结构化审计，落到 stdout（人类可读）与 `/tmp/yquant-p3-ddl-p3b-20260725/audit-p3b.json`（机读）。**不引入**新 audit 集合；本 JSON 为本次 DDL 的单次工件，非持续写入。

`audit-p3b.json` 为 JSON 数组，每个元素描述一次原子操作（`createCollection` / 每条 `createIndex`），字段定义：

| 字段 | 类型 | 说明 |
|---|---|---|
| `operation` | string | `"createCollection"` / `"createIndex"` |
| `collection` | string | 固定为 `"03_data_ud_stock_capital_flow"`（P3-B 范围） |
| `index` | string \| null | `createIndex` 操作时为索引名（`symbol_trade_date` / `trade_date`）；`createCollection` 时为 `null` |
| `ts` | string | 操作完成（或失败）的 ISO-8601 时间戳，带时区 |
| `exit_code` | int | 该操作的退出码（见 §6.4.bis.4）：`0`=成功，`2`=collection create fail，`3`=collection create fail（权限语义见失败矩阵），`4`=index create fail / 目标已存在 |
| `error` | string \| null | 失败时的错误摘要（**不含** secret / 连接串 / 凭据明文）；成功时为 `null` |
| `rollback_script_path` | string | 固定指向 `/tmp/yquant-p3-ddl-p3b-20260725/rollback-p3b.js`，便于操作员快速定位回滚脚本 |

**审计约束**：

- `audit-p3b.json` 不记录任何凭据值、URI、用户名、密码长度——与 SPEC §14.1 / RFC §13.1 的 secret 禁输出原则一致。
- `audit-p3b.json` 是单次 DDL 工件，**不**作为 `03_data_ud_query_audit`（Phase 2 AuditLogger 集合）的替代或前身。
- `audit-p3b.json` 落在 `/tmp`，不提交仓库，不纳入 cron/systemd。

#### 6.4.bis.3 失败处理矩阵

DDL 执行（`createCollection` → 两条 `createIndex`）的失败场景、对应退出码与操作员动作：

| 场景 | 触发信号 | 退出码 | operator action |
|---|---|---|---|
| `createCollection` 成功 + 两条 `createIndex` 全部成功 | `audit-p3b.json` 全部 `exit_code=0` | **0**（整体成功） | 无需动作；进入 PR-CANARY-P3B 评估 |
| `createCollection` 成功但某条 `createIndex` 失败 | 该条 `exit_code=4`（index create fail），`error` 含索引错误 | **4**（index create fail） | fail-stop；操作员评估是否运行 `rollback-p3b.js`（§6.4.bis.1）清理残留索引+集合 |
| `createCollection` 失败（非已存在） | `createCollection` 行 `exit_code=3`（collection create fail） | **3**（collection create fail） | fail-stop；集合未创建，无需回滚；排查 Mongo 错误后重试需 Pascal 重新授权 |
| 目标集合已存在（preflight probe 命中） | preflight `list_collections` 返回该集合 | **2**（preflight target already exists） | fail-stop；**不自动覆盖**；操作员确认是遗留还是意外，参考 PR-1 `p3_collections_found` 结论决定是否降级处理 |
| 索引已存在（createCollection 成功后某索引名冲突） | 对应 `createIndex` 行 `exit_code=4` | **4**（fail-stop） | fail-stop；操作员确认索引定义是否与 §6.2 一致，决定保留或 dropIndex 后重建 |
| 认证 / 权限不足（无 createCollection 或 createIndex 权限） | `exit_code=3`，`error` 含 auth/permission 摘要 | **3**（collection create fail / 权限不足） | fail-stop；不重试；Pascal 授予 DDL 所需权限或换连接身份后重新授权 |
| 网络超时 / 连接中断 | `exit_code=3` 或 `4`，`error` 含 timeout/网络摘要 | **3/4**（视失败发生在哪个操作） | fail-stop；不自动重试；操作员确认 Mongo 连通性（参考 PR-1 结论）后由 Pascal 决定是否重试 |

**通用原则**：

- **fail-stop，不自动回滚**：任何非 0 退出码立即停止后续步骤，**不**自动运行 `rollback-p3b.js`。是否回滚由操作员按上表「operator action」列判断。
- **已存在 = fail-stop 而非覆盖**：preflight probe 命中目标集合返回 exit 2；`createCollection` / `createIndex` 在目标已存在时返回 exit 4，等待操作员评估——绝不静默覆盖既有集合或索引。
- **不自动重试**：与 PR-smoke 的「不自动重试」原则一致（RFC §6.4 / SPEC §14.8）。失败后重试需 Pascal 重新授权。
- **secret 安全**：`error` 字段不得包含凭据、URI、用户名、密码长度——仅含操作类型与失败类别摘要。
- **DDL 前独立 read-only probe**：DDL 执行前必须先做独立 read-only probe（`list_collections` / `list_indexes`）确认目标不存在，probe 命中即 exit 2，不进入 DDL 写入。

#### 6.4.bis.4 退出码（与 SPEC §14.6.bis 对齐）

本 §6.4.bis.4 退出码**仅**作用于 PR-DDL-P3B 的 DDL 执行阶段（preflight probe + `createCollection` + `createIndex`），与 §15.5.4 的 PR-1 只读预检退出码（0/1/2/3，针对 ping + list_collections）**不冲突**——两者作用于不同 Gate（PR-DDL-P3B vs PR-1）、不同操作（DDL 写入 vs 只读连通性检查）。PR-DDL-P3B 的 preflight probe 属于本 Gate 内部的 read-only 子步骤，与 PR-1 的独立只读预检 Gate 分离。

| 退出码 | 含义 | 对应场景 |
|---|---|---|
| **0** | DDL 成功（PASS） | preflight 目标不存在 + `createCollection` + 两条 `createIndex` 全部成功 |
| **2** | preflight target already exists | preflight probe（`list_collections`）发现 `03_data_ud_stock_capital_flow` 已存在 |
| **3** | collection create fail | `createCollection` 执行错误、认证/权限不足、网络超时（失败发生在集合创建阶段） |
| **4** | index create fail | `createIndex` 执行错误、索引名冲突、网络超时（失败发生在索引创建阶段） |

退出码 1 在本 DDL 契约中**不使用**（1 在 §15.5.4 中表示 PR-1 的 conditional pass，语义不同，避免歧义）。退出码 ≥5 为后续 Gate 预留，本 P3-B 契约不定义。

---

### 6.4.ter P3-C DDL 执行、回滚与审计契约（B1-P3C 冻结）

> **授权范围（B1-P3C）**：本节**仅**冻结 P3-C 子阶段 `03_data_ud_market_sentiment_snapshot` 的 DDL 范围、回滚脚本、audit 字段、失败处理与退出码。P3-A 的 DDL 契约已在 §6.4 独立冻结；P3-B 的 DDL 契约已在 §6.4.bis 独立冻结。权威的集合创建与索引脚本以 §6.2 为准；本节定义其执行语义、失败处理与可审计工件。

本节面向 **PR-DDL-P3C** Gate（SPEC §14.6.ter / RFC §13.6）。约束：

- **写入目标**：仅集合 `03_data_ud_market_sentiment_snapshot`，库 `tradingagents`，主仓 `main` 本地工作树。
- **写入身份**：复用现有 `MONGODB_USERNAME`（Phase 2 PortfolioMongoLoader 已验证的组件式构造连接，非 URI；与 P3-A / P3-B 同一账号）。DDL 完成后权限摘要落到 `/tmp/yquant-p3-ddl-p3c-20260725/audit-p3c.json`。**不**新建最小权限角色（依赖链复杂，DDL 完成后仅在 audit JSON 中记录账号权限摘要；最小权限收敛放到后续独立 Gate）。
- **索引定义**：完全照 §6.2 当前定稿版本——两条索引名 `snapshot_date`（`{snapshot_date:-1}`）与 `snapshot_time`（`{snapshot_time:-1}`），全部 `background: true`。本节不重新定义索引，仅引用 §6.2。
- **写入原子性**：失败即停，**不自动回滚**。`createCollection` 与 `createIndex` 在目标已存在时 fail-stop，由操作员手动评估（见 §6.4.ter.3）。
- **写入前审计**：仅 stdout 与 `/tmp/yquant-p3-ddl-p3c-20260725/audit-p3c.json`，字段定义见 §6.4.ter.2。**不引入**新的 audit 集合（`03_data_ud_query_audit` 写入属 Phase 2，不在本 Gate）。
- **不授权范围**：不 refresh、不 upsert 业务数据、不写 Cache、不写 AuditLogger、不写 QualitySummary、不动 cron/systemd、不动 `.env`、不建新角色、不动生产代码树（本节为设计文档增补；`/tmp` 下 rollback-p3c.js 文件由下游 Implement 阶段生成，不在本 §6.4.ter 范围）。

#### 6.4.ter.1 Rollback 脚本（drop 顺序）

回滚脚本随 DDL 同步生成到 `/tmp/yquant-p3-ddl-p3c-20260725/rollback-p3c.js`（**不提交到仓库**），作为操作员手动回滚的安全网。脚本权威内容（与 §6.2 创建脚本严格对称）：

```javascript
// P3-C rollback: 回滚 03_data_ud_market_sentiment_snapshot 的 DDL
// 适用场景：DDL 全部成功后操作员决定撤销；或 DDL 部分成功后清理残留。
// 顺序：先逐条 dropIndex（反向），再 dropCollection。
// 失败即停，不自动级联——由操作员逐条评估。

// Step 1: 反向 dropIndex（与 §6.2 创建顺序相反）
db["03_data_ud_market_sentiment_snapshot"].dropIndex("snapshot_time");
db["03_data_ud_market_sentiment_snapshot"].dropIndex("snapshot_date");

// Step 2: dropCollection
db["03_data_ud_market_sentiment_snapshot"].drop();
```

**部分索引已建的处理**：若 `createIndex` 仅成功前 N 条即失败（§6.4.ter.3 的 `INDEX_PARTIAL` 场景），操作员按**已实际建成索引的反向顺序**逐条 `dropIndex`，最后执行 `dropCollection`。`dropCollection` 本身会级联删除剩余索引，因此即便跳过逐条 `dropIndex` 也可完成回滚——逐条 `dropIndex` 的价值在于让操作员在每一步确认状态，而非功能性必需。

**回滚脚本边界**：

- 回滚脚本仅处理 P3-C 一个集合；P3-A 的回滚脚本见 §6.4.1，P3-B 的回滚脚本见 §6.4.bis.1。
- 回滚脚本是**安全网**，不是自动机制——DDL 失败时 **fail-stop**，等待操作员决定是否运行回滚（见 §6.4.ter.3 失败矩阵的「operator action」列）。
- 回滚脚本不删除业务数据——DDL 之前该集合不存在业务数据，DDL 之后若已运行 CANARY 写入则业务数据回滚属 PR-CANARY 清理脚本职责，不在本 §6.4.ter 范围。

#### 6.4.ter.2 Audit JSON 字段定义

DDL 执行过程产出结构化审计，落到 stdout（人类可读）与 `/tmp/yquant-p3-ddl-p3c-20260725/audit-p3c.json`（机读）。**不引入**新 audit 集合；本 JSON 为本次 DDL 的单次工件，非持续写入。

`audit-p3c.json` 为 JSON 数组，每个元素描述一次原子操作（`createCollection` / 每条 `createIndex`），字段定义：

| 字段 | 类型 | 说明 |
|---|---|---|
| `operation` | string | `"createCollection"` / `"createIndex"` |
| `collection` | string | 固定为 `"03_data_ud_market_sentiment_snapshot"`（P3-C 范围） |
| `index` | string \| null | `createIndex` 操作时为索引名（`snapshot_date` / `snapshot_time`）；`createCollection` 时为 `null` |
| `ts` | string | 操作完成（或失败）的 ISO-8601 时间戳，带时区 |
| `exit_code` | int | 该操作的退出码（见 §6.4.ter.4）：`0`=成功，`2`=preflight target already exists，`3`=collection create fail（含权限/网络），`4`=index create fail |
| `error` | string \| null | 失败时的错误摘要（**不含** secret / 连接串 / 凭据明文）；成功时为 `null` |
| `rollback_script_path` | string | 固定指向 `/tmp/yquant-p3-ddl-p3c-20260725/rollback-p3c.js`，便于操作员快速定位回滚脚本 |

**审计约束**：

- `audit-p3c.json` 不记录任何凭据值、URI、用户名、密码长度——与 SPEC §14.1 / RFC §13.1 的 secret 禁输出原则一致。
- `audit-p3c.json` 是单次 DDL 工件，**不**作为 `03_data_ud_query_audit`（Phase 2 AuditLogger 集合）的替代或前身。
- `audit-p3c.json` 落在 `/tmp`，不提交仓库，不纳入 cron/systemd。

#### 6.4.ter.3 失败处理矩阵

DDL 执行（`createCollection` → 两条 `createIndex`）的失败场景、对应退出码与操作员动作：

| 场景 | 触发信号 | 退出码 | operator action |
|---|---|---|---|
| `createCollection` 成功 + 两条 `createIndex` 全部成功 | `audit-p3c.json` 全部 `exit_code=0` | **0**（整体成功） | 无需动作；进入 PR-CANARY-P3C 评估 |
| `createCollection` 成功但某条 `createIndex` 失败 | 该条 `exit_code=4`（index create fail），`error` 含索引错误 | **4**（index create fail） | fail-stop；操作员评估是否运行 `rollback-p3c.js`（§6.4.ter.1）清理残留索引+集合 |
| `createCollection` 失败（非已存在） | `createCollection` 行 `exit_code=3`（collection create fail） | **3**（collection create fail） | fail-stop；集合未创建，无需回滚；排查 Mongo 错误后重试需 Pascal 重新授权 |
| 目标集合已存在（preflight probe 命中） | preflight `list_collections` 返回该集合 | **2**（preflight target already exists） | fail-stop；**不自动覆盖**；操作员确认是遗留还是意外，参考 PR-1 `p3_collections_found` 结论决定是否降级处理 |
| 索引已存在（createCollection 成功后某索引名冲突） | 对应 `createIndex` 行 `exit_code=4` | **4**（fail-stop） | fail-stop；操作员确认索引定义是否与 §6.2 一致，决定保留或 dropIndex 后重建 |
| 认证 / 权限不足（无 createCollection 或 createIndex 权限） | `exit_code=3`，`error` 含 auth/permission 摘要 | **3**（collection create fail / 权限不足） | fail-stop；不重试；Pascal 授予 DDL 所需权限或换连接身份后重新授权 |
| 网络超时 / 连接中断 | `exit_code=3` 或 `4`，`error` 含 timeout/网络摘要 | **3/4**（视失败发生在哪个操作） | fail-stop；不自动重试；操作员确认 Mongo 连通性（参考 PR-1 结论）后由 Pascal 决定是否重试 |

**通用原则**：

- **fail-stop，不自动回滚**：任何非 0 退出码立即停止后续步骤，**不**自动运行 `rollback-p3c.js`。是否回滚由操作员按上表「operator action」列判断。
- **已存在 = fail-stop 而非覆盖**：preflight probe 命中目标集合返回 exit 2；`createCollection` / `createIndex` 在目标已存在时返回 exit 4，等待操作员评估——绝不静默覆盖既有集合或索引。
- **不自动重试**：与 PR-smoke 的「不自动重试」原则一致（RFC §6.4 / SPEC §14.8）。失败后重试需 Pascal 重新授权。
- **secret 安全**：`error` 字段不得包含凭据、URI、用户名、密码长度——仅含操作类型与失败类别摘要。
- **DDL 前独立 read-only probe**：DDL 执行前必须先做独立 read-only probe（`list_collections` / `list_indexes`）确认目标不存在，probe 命中即 exit 2，不进入 DDL 写入。

#### 6.4.ter.4 退出码（与 SPEC §14.6.ter 对齐）

本 §6.4.ter.4 退出码**仅**作用于 PR-DDL-P3C 的 DDL 执行阶段（preflight probe + `createCollection` + `createIndex`），与 §15.5.4 的 PR-1 只读预检退出码（0/1/2/3，针对 ping + list_collections）**不冲突**——两者作用于不同 Gate（PR-DDL-P3C vs PR-1）、不同操作（DDL 写入 vs 只读连通性检查）。PR-DDL-P3C 的 preflight probe 属于本 Gate 内部的 read-only 子步骤，与 PR-1 的独立只读预检 Gate 分离。

| 退出码 | 含义 | 对应场景 |
|---|---|---|
| **0** | DDL 成功（PASS） | preflight 目标不存在 + `createCollection` + 两条 `createIndex` 全部成功 |
| **2** | preflight target already exists | preflight probe（`list_collections`）发现 `03_data_ud_market_sentiment_snapshot` 已存在 |
| **3** | collection create fail | `createCollection` 执行错误、认证/权限不足、网络超时（失败发生在集合创建阶段） |
| **4** | index create fail | `createIndex` 执行错误、索引名冲突、网络超时（失败发生在索引创建阶段） |

退出码 1 在本 DDL 契约中**不使用**（1 在 §15.5.4 中表示 PR-1 的 conditional pass，语义不同，避免歧义）。退出码 ≥5 为后续 Gate 预留，本 P3-C 契约不定义。

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
| RFC-03-014 | V0.6 §13 | 生产就绪详细规范（副作用矩阵、规程模板、停止条件）——PR-1 凭据来源已对齐至 skills/.env 五组件键 |
| SPEC-03-014 | V0.5 §14 | 生产就绪契约（YAML 报告模板、Zero-Persistence-Write、DDL Gate 细则）——PR-1 凭据来源已对齐至 skills/.env 五组件键 |
| **DESIGN-03-014（本 §）** | **V0.11** | **实现设计（文件 allowlist、CLI 接口、安全契约、LegacyConfigResolver 组件式构造、PreflightRunner 预检流程、Verify/Review 验收命令）** |

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
| 14 | 新建 | `tests/scripts/t4_preflight/test_audit_secret.py` | Secret 审计单元测试 | PR-0 |
| 15 | 新建 | `tests/scripts/t4_preflight/test_preflight_mongo.py` | MongoDB 预检单元测试（mongomock） | PR-1 |
| 16 | 新建 | `tests/scripts/t4_preflight/test_smoke_sector.py` | Sector smoke 单元测试（mock AKShare） | PR-2 |
| 17 | 新建 | `tests/scripts/t4_preflight/test_smoke_flow.py` | Flow smoke 单元测试 | PR-3 |
| 18 | 新建 | `tests/scripts/t4_preflight/test_smoke_sentiment.py` | Sentiment smoke 单元测试 | PR-4 |
| 19 | 新建 | `tests/scripts/t4_preflight/test_reporter.py` | 报告序列化/脱敏/格式测试 | PR-0 ~ PR-4 |
| **夹具** | | | | |
| 20 | 新建 | `tests/scripts/t4_preflight/fixtures/t4_secret_fixtures.py` | 模拟 .env 文件 + 环境变量场景 | PR-0 |
| 21 | 新建 | `tests/scripts/t4_preflight/fixtures/t4_mongo_fixtures.py` | 模拟 mongomock 集合清单场景 | PR-1 |
| 22 | 新建 | `tests/scripts/t4_preflight/fixtures/t4_akshare_fixtures.py` | 模拟 AKShare API 响应（含字段变体） | PR-2/3/4 |
| **根 package marker** | | | | |
| 23 | 新建 | `scripts/__init__.py` | 让 `from scripts.t4_preflight import ...` 可被 `tests/scripts/t4_preflight/test_*.py` 解析；pytest collection 必要前提（T4B 77/77 PASS 已验证） | PR-0 ~ PR-4 |

**总量**：23 个新建文件，位于 `scripts/__init__.py`、`scripts/t4_preflight/` 和 `tests/scripts/t4_preflight/` 下。

> **Principal 正式裁决（2026-07-22）**：`scripts/__init__.py`（#23）为 T4 测试集合的必要 package marker，不包含任何运行时逻辑（仅 docstring），pytest 解析 `from scripts.t4_preflight import ...` 依赖其存在。正式确认其进入 T4 allowlist。该符号属 DESIGN 级实现细节，RFC/SPEC 无需提及。

> **未进入 allowlist**：现有 unified_data 代码（`models/`、`services/`、`providers/` 等）在 T4 阶段不做任何修改。T4 工具链独立于 unified_data 主库，仅在最终 Review PASS 后通过 `--live-read` 驱动真实环境验证。不修改 `unified_data` 核心模块的 `SKILL.md`、`README`、`requirements`、`pyproject.toml`。

### 15.3 公共安全契约

**MONGODB_DATABASE 值校验（跨阶段强制规则）**：
`MONGODB_DATABASE` 键值**必须等于** `tradingagents`，否则视为 NOT_AUTHORIZED、退出码 3、零连接。此规则在以下三处一致执行：
- **§15.3.3 audit-secret --live-read**：resolve 阶段验证 key 存在且非空（现有），追加值等于 `"tradingagents"` 检查
- **§15.4.2 审计矩阵**：`MONGODB_DATABASE` 行声明 value must equal `tradingagents`（追加）
- **§15.5.2 resolve(live=True)**：`database_ok` 调整为存在 + 值等于 `"tradingagents"` 双重检查；build_client() 的 `authSource` 取自 `MONGODB_DATABASE` 键值（resolve 阶段已校验等于 `tradingagents`）

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

> **状态对象语义**：dry-run 产物为 `SecretProbeResult`（§15.4.1），只含路径/依赖/参数级元数据，**不含任何 key 级存在性字段**（如 `key_declared`、`five_keys_declared`）。key 级状态属 live-read 的 `ResolvedConfig.*_resolved` 职责域，两者语义隔离、不重叠。

默认（无 `--live-read`）时，所有命令执行受限的零连接探测：

| 命令 | Dry-Run 行为 |
|---|---|
| `audit-secret` | 检查 `skills/.env` 文件存在性 + 可读性（`os.access`），**不**调用 `dotenv_values()`、不读取文件内容。输出元数据仅限路径级：`skills/.env: exists=true, readable=true`。**不得**输出任何键状态、键计数、值、长度、URI、host、用户名、collection 名 |
| `preflight-mongo` | 检查 `pymongo` importable + `python-dotenv` importable + `skills/.env` 路径可达。不实例化 MongoClient、不建立网络连接。输出元数据仅限 import/路径级：`pymongo: importable=true, dotenv: importable=true, skills_env_path: accessible=true`。**不得**输出 `five_keys_declared` 或任何键状态/计数。MONGODB_DATABASE 值校验（必须等于 `tradingagents`）在 live-read 阶段由 `audit-secret --live-read` 执行，dry-run 不读取键值 |
| `smoke-sector` | 检查 `akshare` importable + 测试参数初始化。输出「akshare: importable=true, test_symbol=BK0489, date_range=2026-07-20..2026-07-22, would_call: 2」 |
| `smoke-flow` | 同上行为 |
| `smoke-sentiment` | 同上行为 |

#### 15.3.3 Live-Read 模式（`--live-read`）

> **状态对象语义**：live-read 产物为 `ResolvedConfig.*_resolved` / live 状态（§15.5.2），含 key 级布尔字段（如 `database_resolved`、各 `declared` 状态）。与 dry-run 的 `SecretProbeResult`（无 key 级输出）语义隔离、不重叠。`declared=true` 等 key 级布尔仅出现在 live-read 输出中，不违反 §15.3.2 的 dry-run 禁令。

当 `--live-read` 被显式传递时，各命令才执行实际网络/MongoDB 调用：

| 命令 | Live-Read 动作 | 约束 |
|---|---|---|
| `audit-secret` | 实际调用 `dotenv_values(skills/.env)` 解析五组件，验证 MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE 五个键全部非空**且 MONGODB_DATABASE 值等于 `"tradingagents"`**（但**不**输出值/长度）。**禁止**调用 `load_dotenv()`（全局 env 污染禁令，见 §15.5.2 不可违反复核清单）；仅使用 `dotenv_values()` 的本地无副作用解析 |
| `preflight-mongo` | `LegacyConfigResolver(skills/.env).build_client(timeout=3)` → `admin.command("ping")` → `list_collection_names()` | 不读业务数据；超时 3s；需 PR-0 已确认五键全部 authorized |
| `smoke-sector` | `akshare.stock_board_industry_cons_em("BK0489")` | 单板块 + ≤3 交易日；AKShare 匿名调用，不依赖 PR-0 授权 |
| `smoke-flow` | `akshare.stock_individual_fund_flow("600519", market="sh")` | 2-4 次调用，限速 ≥1s；AKShare 匿名调用 |
| `smoke-sentiment` | `akshare.stock_zt_pool_em("20260722")` / `stock_market_fund_flow()` | 单日期；AKShare 匿名调用 |

**Live-Read 执行门槛**：
1. MongoDB 预检 `preflight-mongo --live-read` 前，前序的 `audit-secret --live-read` 必须针对 `skills/.env` 的五组件键（`MONGODB_HOST`/`PORT`/`USERNAME`/`PASSWORD`/`DATABASE`）**全部**为 `declared=true` 且 `loadable=true`，**且** MONGODB_DATABASE 值等于 `"tradingagents"`（MongoDB 连接秘密已授权，目标库已验证）
2. AKShare smoke（`smoke-sector/flow/sentiment --live-read`）**不依赖 PR-0 授权**——AKShare 为匿名调用，可直接执行
3. `audit-secret` 的输出中 `MONGODB_HOST`/`PORT`/`USERNAME`/`PASSWORD`/`DATABASE` 全五键状态为 `AUTHORIZED` **且** MONGODB_DATABASE 值已验证等于 `"tradingagents"` 后，方可执行 `preflight-mongo --live-read`
4. smoke 命令的 `preflight-mongo --live-read` 输出中 `ping=success`

**不强制执行**：以上门槛由 CLI 输出 check 手动确认（非自动阻断——审查人通过查看报告链确认顺序合规）。但 `audit-secret --live-read` 未通过时（任一五键缺失或 MONGODB_DATABASE 值不等于 `"tradingagents"`），MongoDB preflight 命令应输出 `WARN: PR-0 not confirmed — skills/.env five keys(MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE) not all authorized or MONGODB_DATABASE != "tradingagents"` 并将 `overall.verdict` 降为 `conditional_pass`。AKShare smoke 不受此警告影响。

### 15.4 Secret Source 非泄露审计设计（PR-0）

#### 15.4.1 SecretVerifier 接口

```python
# scripts/t4_preflight/secrets.py（设计草图，非最终实现）

@dataclass(frozen=True)
class SecretProbeResult:
    """非泄露秘密探测结果。只输出布尔/枚举结论，不输出值/长度/URI/用户名。

    与 ResolvedConfig（§15.5.2）的职责边界：SecretProbeResult 负责文件级元数据
    （exists/readable/importable），不包含键级存在性信息——键级状态由
    ResolvedConfig 的 database_resolved 等布尔字段覆盖。

    **dry-run vs live-read 边界**：SecretProbeResult 是 dry-run 状态对象，
    任何 declared / five_keys_declared 字段在 dry-run 下均不输出（仅含路径/依赖/
    参数级元数据）。key 级布尔（如 database_resolved、各 declared 状态）属
    live-read 的 ResolvedConfig.*_resolved 职责域。
    """
    source_name: str                          # 候选源名称，如 "project_root_env"
    file_exists: bool                         # 文件存在
    file_readable: bool | None = None         # 文件可读（dry-run 为 None）
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

#### 15.4.2 候选 Secret Source 审计矩阵（Dry-run / Live-read 双列）

遵循 SPEC §14.3 / RFC §13.3 及 T1 t_cafc0903 最终契约：MongoDB 连接凭据的唯一来源为 **Phase 2 `skills/.env` 五组件键**。

| 候选路径 | 键名 | Dry-run（SecretProbeResult）× 无键级输出 | Live-read（dotenv_values + ResolvedConfig）× 仅布尔键级输出 |
|---|---|---|---|
| `skills/.env`（Phase 2 已存在） | `MONGODB_HOST` | **仅路径/依赖/参数级元数据**：检查文件存在性 + 可读性（`os.access`） + python-dotenv / pymongo importable。**不调用 `dotenv_values()`**，不读取文件内容。**不输出任何键级信息**（无 declared / count / 存在性 / 值 / 长度 / URI / host 地址 / 用户名 / 端口） | `dotenv_values()` → `key in parsed` + `present and non-empty` → `bool`（仅 `declared=true/false` / `loadable=true/false` 布尔状态）。**不输出值、长度、URI、host 地址、用户名、端口号** |
| `skills/.env` | `MONGODB_PORT` | 同上 | 同上 |
| `skills/.env` | `MONGODB_USERNAME` | 同上 | 同上 |
| `skills/.env` | `MONGODB_PASSWORD` | 同上 | 同上 |
| `skills/.env` | `MONGODB_DATABASE` | 同上 | `dotenv_values()` → `key in parsed` + `present and non-empty` + **value must equal `"tradingagents"`** → `bool`（仅 `declared` / `loadable` / `authorized` 布尔状态）。**不输出值、长度、数据库名、集合名** |
| AKShare 匿名调用 | 无需密钥审计 | 跳过 ✅（AKShare 为匿名数据源，不依赖 PR-0 检查） | 跳过 ✅ |

**已移除的候选路径**（依据 T1 t_cafc0903 契约，见 RFC-03-014 V0.6 / SPEC-03-014 V0.5）：

| 已移除路径 | 移除理由 |
|---|---|
| `$(pwd)/.env`（项目根） | 已由 T1 裁定为 superseded——Phase 3 不复用此源 |
| `~/.hermes/profiles/yquant/.env`（Hermes profile） | 已由 T1 裁定从审计表中移除——不再是 MongoDB 凭据候选 |
| `MONGO_URI`（env 变量键） | 已由 T1 裁定为 superseded——component-based 构造替代 URI |
| `MONGODB_URI`（env 变量键） | 已由 T0.4 → T1 裁定弃用，且与 `MONGODB_*` 五组件键命名空间冲突——不再计入审计 |

**禁止**：`MongoClient` 构造不得使用 `MONGO_URI`、`MONGODB_URI` 或任何组合后的 URI 字符串。所有候选源的路由为 `LegacyConfigResolver`（§15.5.2）从 `skills/.env` 读取五组件键后按如下方式构造：

```python
MongoClient(
    host=MONGODB_HOST,
    port=int(MONGODB_PORT),
    username=MONGODB_USERNAME,
    password=MONGODB_PASSWORD,
    authSource=MONGODB_DATABASE,
    serverSelectionTimeoutMS=3000,
)
```

**输出示例**（dry-run）：

> **规格变更说明**：本示例代表 T2.1 修正后的 dry-run 输出格式。之前版本（V0.11 §15.4）包含键级 `declared: true` 输出，已在 T2.1 下标记为 superseded——dry-run 不得读取文件内容，因此无法也不应输出键存在性/状态/计数。

```yaml
# audit-result-YYYYMMDD.yaml (dry-run)
secret_audit:
  generated_at: "2026-07-24T03:30:00+08:00"
  source: "phase2_skills_env"
  source_path: "skills/.env"
  file_exists: true
  file_readable: true               # os.access check only — no content read
  # keys: 不在 dry-run 下求值——不调用 dotenv_values()，不输出键状态/计数/值
  importable:
    python_dotenv: true             # module import check only
    pymongo: true                   # module import check only
  superseded_sources:               # 信息性——仅供审查人追溯
    - "$(pwd)/.env: MONGO_URI → superseded by T1"
    - "profile .env: MONGO_URI → superseded by T1"
    - "runtime env: MONGO_URI → superseded by T1"
overall:
  mode: dry_run
  # status 评价需要在 live-read 模式下完成；dry-run 不判断 authorized/unauthorized
  note: "仅路径/import 元数据——需 --live-read 确认完整授权"
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

#### 15.5.2 LegacyConfigResolver 与组件式 MongoClient 工厂

```python
# scripts/t4_preflight/mongo_client.py（设计草图）

from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass(frozen=True)
class ResolvedConfig:
    """五组件解析结果。不包含原始值、长度、URI。"""
    source_label: str = "phase2_skills_env"   # 审计来源标签（唯一恒定值）
    source_path: str = "skills/.env"          # dotenv 相对路径
    host_resolved: bool = False               # MONGODB_HOST 存在且非空
    port_resolved: bool = False               # MONGODB_PORT 存在且可转换为 int
    username_resolved: bool = False           # MONGODB_USERNAME 存在
    password_resolved: bool = False           # MONGODB_PASSWORD 存在
    database_resolved: bool = False           # MONGODB_DATABASE 存在
    all_resolved: bool = False                # 五键全部解析成功
    errors: list[str] = field(default_factory=list)  # 解析错误列表，不含原始值


@dataclass(frozen=True)
class MongoPreflightResult:
    connectivity: str                         # "success" / "dns_failure" / "timeout" / "auth_failure" / "env_missing"
    latency_ms: float | None
    collections: list[str] | None             # list_collection_names() 结果；None 表示 list 不可用
    p3_collections_found: list[str]           # 匹配 03_data_ud_ 前缀的意外集合
    warnings: list[str]


class LegacyConfigResolver:
    """Phase 2 skills/.env 五组件遗留配置解析器。

    单一职责：从明确的 dotenv 路径读取 MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE，
    组件式构造 MongoClient。绝不 fallback 到 MONGO_URI/MONGODB_URI/profile .env。
    绝不依赖 CWD 搜索或 load_dotenv() 全局污染。
    """

    def __init__(self, dotenv_path: str = "skills/.env"):
        if not dotenv_path:
            raise ValueError("dotenv_path must be explicit, not empty")
        self._dotenv_path = dotenv_path
        self._resolved: ResolvedConfig | None = None
        self._client: MongoClient | None = None

    # --- 解析接口 ---

    def resolve(self, *, live: bool = False) -> ResolvedConfig:
        """解析五组件键。

        live=False（dry-run 默认）：检查文件存在性 + 权限，不读取内容。
        不加载 dotenv、不实例化 MongoClient。返回 ResolvedConfig(all_resolved=False)。
        所有字段为 False/空列表。

        live=True：实际调用 dotenv_values(self._dotenv_path) 加载，验证五键全部非空、
        PORT 可转换为 int。返回 ResolvedConfig 含解析状态。
        绝不输出/记录/返回原始值、长度、字符切片、URI。
        """
        if not live:
            # dry-run: 仅检查文件存在性
            exists = os.path.isfile(self._dotenv_path)
            readable = os.access(self._dotenv_path, os.R_OK) if exists else False
            errors = []
            if not exists:
                errors.append("file_not_found")
            elif not readable:
                errors.append("file_not_readable")
            return ResolvedConfig(all_resolved=False, errors=errors)

        # live-read: 实际读取 dotenv
        try:
            from dotenv import dotenv_values
        except ImportError:
            return ResolvedConfig(all_resolved=False, errors=["python-dotenv not installed"])

        parsed = dotenv_values(self._dotenv_path)
        errors = []
        host_ok = bool(parsed.get("MONGODB_HOST", "") or "")
        port_raw = parsed.get("MONGODB_PORT", "") or ""
        port_ok = bool(port_raw)
        if port_ok:
            try:
                int(port_raw)
            except (ValueError, TypeError):
                errors.append("MONGODB_PORT not a valid integer")
                port_ok = False
        username_ok = bool(parsed.get("MONGODB_USERNAME", "") or "")
        password_ok = bool(parsed.get("MONGODB_PASSWORD", "") or "")
        db_value = parsed.get("MONGODB_DATABASE", "") or ""
        database_ok = bool(db_value) and db_value.strip().lower() == "tradingagents"
        if bool(db_value) and not database_ok:
            errors.append("MONGODB_DATABASE must equal 'tradingagents', got different value")
        all_ok = host_ok and port_ok and username_ok and password_ok and database_ok

        return ResolvedConfig(
            source_label="phase2_skills_env",
            source_path=self._dotenv_path,
            host_resolved=host_ok,
            port_resolved=port_ok,
            username_resolved=username_ok,
            password_resolved=password_ok,
            database_resolved=database_ok,
            all_resolved=all_ok,
            errors=errors,
        )

    # --- 连接构造 ---

    def build_client(self, *, live: bool = False, timeout: int = 3) -> MongoClient | None:
        """构造组件式 MongoClient（非 URI）。

        仅当 live=True 且 resolve() 五键全部通过时才构造。
        dry-run 返回 None。
        同一实例最多创建一个 client——二次调用返回同一 client 引用。

        强制 DB=tradingagents——仅当 resolve(live=True) 已确认五键全部通过且
        MONGODB_DATABASE 值等于 "tradingagents" 时才构造连接。
        authSource 取自 MONGODB_DATABASE 键值（resolve 阶段已校验必须等于 tradingagents）。
        绝不通过其他来源推断或硬编码 authSource。绝不依赖 CWD 搜索或 load_dotenv()。
        """
        if not live:
            return None

        if self._client is not None:
            return self._client  # 最多一个 client

        if self._resolved is None or not self._resolved.all_resolved:
            cfg = self.resolve(live=True)
            self._resolved = cfg
            if not cfg.all_resolved:
                return None

        # 仅 live-read 时加载 dotenv——函数内 import 避免全局污染
        from dotenv import dotenv_values
        parsed = dotenv_values(self._dotenv_path)

        import pymongo
        self._client = pymongo.MongoClient(
            host=str(parsed.get("MONGODB_HOST", "")),
            port=int(str(parsed.get("MONGODB_PORT", "27017"))),
            username=str(parsed.get("MONGODB_USERNAME", "")),
            password=str(parsed.get("MONGODB_PASSWORD", "")),
            authSource=str(parsed["MONGODB_DATABASE"]),  # resolve 阶段已校验 MONGODB_DATABASE 键存在且值等于 "tradingagents"；直接取不设 fallback——键缺失时 fail-fast KeyError
            serverSelectionTimeoutMS=timeout * 1000,
        )
        return self._client

    def close(self):
        """关闭 client。幂等。"""
        if self._client:
            self._client.close()
            self._client = None
            self._resolved = None


class PreflightRunner:
    """预检运行器——封装 LegacyConfigResolver → ping → list_collections 流程。"""

    def __init__(self, resolver: LegacyConfigResolver | None = None):
        self.resolver = resolver or LegacyConfigResolver()

    def run_preflight(self, *, live: bool = False, timeout: int = 3) -> MongoPreflightResult:
        """执行预检三步：(1) 解析五组件 → (2) ping → (3) list_collections。

        所有步骤不携带业务数据 filter。dry-run 返回预检未执行的元数据报告。
        """
        cfg = self.resolver.resolve(live=live)
        if not live:
            return MongoPreflightResult(
                connectivity="dry_run",
                latency_ms=None,
                collections=None,
                p3_collections_found=[],
                warnings=["dry-run: config resolved, no connection attempted"],
            )

        if not cfg.all_resolved:
            return MongoPreflightResult(
                connectivity="env_missing",
                latency_ms=None,
                collections=None,
                p3_collections_found=[],
                warnings=[f"skills/.env five keys not all resolved: {cfg.errors}"],
            )

        import time
        t0 = time.monotonic()

        client = self.resolver.build_client(live=True, timeout=timeout)
        if client is None:
            return MongoPreflightResult(
                connectivity="env_missing",
                latency_ms=None,
                collections=None,
                p3_collections_found=[],
                warnings=["Failed to build client from resolved config"],
            )

        try:
            # Step 1: ping
            client.admin.command("ping")
            latency_ms = (time.monotonic() - t0) * 1000

            # Step 2: list_collections (in tradingagents DB)
            db = client["tradingagents"]
            collections = db.list_collection_names()

            # Step 3: check P3 collections
            p3_patterns = [
                "03_data_ud_market_sector_snapshot",
                "03_data_ud_stock_capital_flow",
                "03_data_ud_market_sentiment_snapshot",
            ]
            p3_found = [c for c in collections if c in p3_patterns]

            return MongoPreflightResult(
                connectivity="success",
                latency_ms=latency_ms,
                collections=collections,
                p3_collections_found=p3_found,
                warnings=[],
            )
        except pymongo.errors.ServerSelectionTimeoutError:
            latency_ms = (time.monotonic() - t0) * 1000
            return MongoPreflightResult(
                connectivity="timeout",
                latency_ms=latency_ms,
                collections=None,
                p3_collections_found=[],
                warnings=["Server selection timeout (>3s)"],
            )
        except pymongo.errors.OperationFailure as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            code = str(exc)
            if "Authentication" in code or "auth" in code.lower():
                return MongoPreflightResult(connectivity="auth_failure", latency_ms=latency_ms,
                                            collections=None, p3_collections_found=[],
                                            warnings=[f"auth_failure: {exc.code if hasattr(exc, 'code') else 'unknown'}"])
            return MongoPreflightResult(connectivity="dns_failure", latency_ms=latency_ms,
                                        collections=None, p3_collections_found=[],
                                        warnings=[f"operation_failure: {exc}"])
        finally:
            self.resolver.close()
```

**不可违反复核清单**（在 Implement Reviewer 阶段强制检查）：

- `LegacyConfigResolver.__init__` 的 `dotenv_path` **必须**是显式路径（如 `"skills/.env"`），不得允许 CWD 推导或空字符串
- `resolve(live=True)` 必须使用 `dotenv.dotenv_values()`（文件级解析），不得使用 `dotenv.load_dotenv()`（全局 env 污染）
- `build_client(live=True)` **必须**使用五组件 `MongoClient(host, port, username, password, authSource)` 签名，不得组装为 `MongoClient(f"mongodb://{user}:{pwd}@{host}:{port}")` URI 串
- `authSource` 必须来自 `MONGODB_DATABASE` 键值（`parsed["MONGODB_DATABASE"]` 直接取值——无 fallback 字面量），resolve 阶段已校验键存在且值等于 `"tradingagents"`——键缺失时 fail-fast KeyError
- `build_client()` **不得**接受或引用 `MONGO_URI` / `MONGODB_URI` 变量
- 所有 `dotenv_values()` 的返回值仅用于 `bool()` 判断和参数构造，**绝不**被赋予日志、print、YAML 输出
- `ResolvedConfig` 的字符串字段仅含 `source_label` 和 `source_path`，**不包含** `host`、`port`、`username`、`password`、`database` 的实际值

#### 15.5.3 集合存在检查

执行 `list_collection_names()` 后，用正则匹配检查集合名是否包含以下模式：
- `03_data_ud_market_sector_snapshot`
- `03_data_ud_stock_capital_flow`
- `03_data_ud_market_sentiment_snapshot`

如果任一集合存在，输出标记为 `UNEXPECTED_EXISTENCE`，列出 `options()` 元数据（创建时间戳、UUID、配置），**不读业务数据**。序列化 options() 时跳过 `wiredTiger` 引擎实现细节（仅保留 first-level 键）。预检停止，等待 Pascal 判断。

#### 15.5.4 失败分类

| 观察到的错误 | 报告状态 | 退出码 |
|---|---|---|
| `skills/.env` 文件不存在或不可读 | `connectivity: env_missing` | 3（unauthorized） |
| `MONGODB_DATABASE` 值不等于 `"tradingagents"` | `connectivity: env_missing` + warning 注明实际值 | 3（unauthorized） |
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
    # `metadata.endpoint_status: str | None` is an **optional** field
    # on the SmokeMetadata header. It is written only when the live-read
    # ran AND ALL PR-2 calls failed with ProxyError/ConnectionError
    # (Fix E in scripts/t4_preflight/smoke_sector.py, see
    # SPEC-03-014 §14.4.2). It MUST be absent in dry-run, success,
    # partial-failure (any_success=True), and generic RuntimeError
    # paths; reporters MUST NOT serialize the key as `null`.
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
# 预期：dry-run 输出技能/.env 元数据（file_exists, file_readable），不含 any secret，退出码 0

# PR-1 dry-run: 验证 import + 配置准备 + 五组件声明显式
python -m scripts.t4_preflight.cli preflight-mongo
# 预期：dry-run 报告 pymongo importable=true + dotenv importable=true + ResolvedConfig(source=phase2_skills_env, all_resolved=false) + 文件可达性，退出码 0

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
.venv/bin/python -m pytest tests/scripts/t4_preflight/test_reporter.py::test_zero_write_spy -q
```

**禁止通过 dry-run 泛化为生产结论**：dry-run 的导入+配置检查不得标注为「生产验证通过」。Review 报告必须明确区分 dry-run（离线）与 live-read（生产）结果。

#### 15.10.3 T4 Live-Read 命令（Review PASS 后执行）

以下命令仅在 Review 通过、Pascal 确认后执行。执行人为 Pascal 或 Pascal 授权的 DevOps（对应 SPEC §14.6 / RFC §13.6）：

```bash
# Step 1: PR-0 live — 实际验证 skills/.env 五组件可加载
python -m scripts.t4_preflight.cli audit-secret --live-read
# 输出：audit-result-YYYYMMDD.yaml，要求 overall.status=authorized + missing_keys=[]

# Step 2: PR-1 live — 实际 MongoDB ping + 集合清单（通过 LegacyConfigResolver）
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
| RC-8 | 零写入 spy 测试通过 | `pytest tests/scripts/t4_preflight/test_reporter.py::test_zero_write_spy -q` | exit 0 |

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
| §13.2 MongoDB 预检规程 | §14.2 MongoDB 预检规程 | §15.5 MongoDB 零写入预检（含 LegacyConfigResolver + PreflightRunner） | ✅ 对齐停止条件与白名单；PR-1 凭据来源改为 skills/.env 五组件键（匹配 RFC V0.6 / SPEC V0.5） |
| §13.3 Secret Source 审计 | §14.3 Secret Source 审计 | §15.4 SecretVerifier + 候选矩阵 | ✅ 非泄露三布尔；候选源缩为单一 skills/.env（匹配 RFC V0.6 / SPEC V0.5） |
| §13.4 Provider Smoke | §14.4 Provider Smoke | §15.6 AKShare 安全调用包装 | ✅ 单标的 ≤3 日 |
| §13.5 Zero-Persistence-Write | §14.5 Zero-Persistence-Write | §15.9 零写入 spy | ✅ 通过 spy 模式验证 |
| §13.6 DDL/DML 独立 Gate | §14.6 DDL/DML 独立 Gate | §15.11 Live-Read 执行流程 | ✅ DDL 仍 Pascal 独立 Gate |
| §13.7 成功标准 | §14.7 成功标准 | §15.10 Verify/Review 验收 | ✅ 退出码 + 检查表 |
| **§13.4.5 B2 实测映射契约冻结** | **§14.4.5 B2 实测映射契约冻结** | **§4.2.1 B2 映射修正 + §15.14 工具链设计** | **✅ V0.16 新增 — 映射模式更新 + 字段集/账本/验证计划** |

---

### 15.14 B2 实测映射契约冻结 — 工具链设计（V0.16 新增）

> **权威定位**：本节是 RFC-03-014 §13.4.5 / SPEC-03-014 §14.4.5 引用的工具链设计层。B2 冻结证据的权威业务语义在 SPEC §14.4.5；本节定义 expected 字段集、endpoint 选择逻辑、reporter 账本字段、fixture 结构与验证计划。如 §4.2.1 与本节出现差异，以 §4.2.1 的映射表为准。

#### 15.14.1 Expected 字段集（基于 B2 证据 + 公开文档推断）

每个 capability 的 expected 字段集供 `smoke_{capability}.py` / `provider_client.py` 使用。

##### sector.snapshot + sector.ranking（推断版，未 live-read 验证）

| # | Canonical 字段 | 推断 AKShare 列名 | 类型 | 必填 | 备注 |
|---|---|---|---|---|---|
| 1 | `sector_code` | `板块代码` | str | ✅ | |
| 2 | `sector_name` | `板块名称` | str | ✅ | |
| 3 | `sector_type` | — | str | ✅ | 接口限定 `industry`，固定值 |
| 4 | `snapshot_date` | `交易日期` | str | ✅ | YYYY-MM-DD |
| 5 | `market` | — | str | ✅ | 固定 `CN` |
| 6 | `rank` | `排名` | int | — | 需 live-read 确认 |
| 7 | `pct_chg` | `涨跌幅` | float | — | |
| 8 | `leading_stock` | `领涨股代码` | str | — | |
| 9 | `leading_stock_name` | `领涨股名称` | str | — | |
| 10 | `leading_pct_chg` | `领涨股涨幅` | float | — | |
| 11 | `advance_count` | `上涨家数` | int | — | |
| 12 | `decline_count` | `下跌家数` | int | — | |
| 13 | `total_count` | `总家数` | int | — | |
| 14 | `turnover_rate` | `换手率%` | float | — | |
| 15 | `main_net_inflow` | `主力净流入` | float | — | 元 |
| 16 | `members` | `members` | list[str] | — | 成分股代码列表 |

> **重要**：上表为**推断版**，所有字段标注「未 live-read 验证」。T3 Implement 须实现此映射并标注状态。后续独立 live-read 在 PR-2 SSL 诊断通过后复验。

##### flow.capital_flow_daily（基于 AKShare 公开文档）

| # | Canonical 字段 | 推断 AKShare 列名 | 类型 | 必填 | 备注 |
|---|---|---|---|---|---|
| 1 | `symbol` | `股票代码` | str | ✅ | |
| 2 | `market` | — | str | ✅ | 固定 `CN` |
| 3 | `trade_date` | `交易日期` | str | ✅ | YYYY-MM-DD |
| 4 | `main_net_inflow` | `主力净流入` | float | — | 元，正=净流入 |
| 5 | `super_large_net_inflow` | `超大单净流入` | float | — | 元 |
| 6 | `large_net_inflow` | `大单净流入` | float | — | 元 |
| 7 | `medium_net_inflow` | `中单净流入` | float | — | 元 |
| 8 | `small_net_inflow` | `小单净流入` | float | — | 元 |
| 9 | `main_net_inflow_ratio` | `主力净流入占比%` | float | — | |
| 10 | `northbound_net_inflow` | — | float | — | 需解耦后另定 |
| 11 | `northbound_hold_shares` | — | float | — | 同北向 endpoint |
| 12 | `northbound_hold_ratio` | — | float | — | 同北向 endpoint |
| 13 | `margin_buy` | `融资买入额` | float | — | |
| 14 | `margin_sell` | `融券卖出额` | float | — | |
| 15 | `margin_balance` | `融资余额` | float | — | |

##### flow.northbound_daily（B2 冻结 — 北向持股历史语义）

| # | Canonical 字段 | B2 实际 AKShare 列 | 类型 | 必填 | 备注 |
|---|---|---|---|---|---|
| 1 | `symbol` | — | str | ✅ | 查询参数传入 |
| 2 | `market` | — | str | ✅ | 固定 `CN` |
| 3 | `trade_date` | `持股日期` | str | ✅ | YYYY-MM-DD |
| 4~6 | `northbound_net_inflow` / `northbound_hold_shares` / `northbound_hold_ratio` | — | — | — | **Pascal 已选 C（2026-07-26）**：当前 Phase 3 恒 None，不指向真实 endpoint；见 §4.2.1 |
| 7 | `hold_shares` * | `持股数量` | float | — | 辅助参考字段（C 下不映射入 canonical） |
| 8 | `hold_market_value` * | `持股市值` | float | — | 同上 |
| 9 | `hold_ratio` * | `持股数量占A股百分比` | float | — | 同上 |
| 10 | `daily_change_shares` * | `今日增持股数` | float | — | 同上 |
| 11 | `daily_change_value` * | `今日增持资金` | float | — | 同上 |
| 12 | `market_value_change` * | `今日持股市值变化` | float | — | 同上 |

> `*` 号字段为持股历史参考字段（原选项 B 候选 canonical 字段名）。Pascal 已选 C（2026-07-26），这些字段在当前 Phase 3 **不映射入 canonical** `northbound_*` 字段，仅作为 B2 冻结证据的辅助参考保留。
>
> **B2 实际返回的额外字段**（未被 expected 覆盖）：`当日收盘价` / `当日涨跌幅` — 可标记为 extra、可丢弃或另作参考字段。

##### sentiment.market_snapshot + sentiment.limit_up_pool（推断版，空返回未验证）

| # | Canonical 字段 | 推断 AKShare 列名 | 类型 | 必填 | 备注 |
|---|---|---|---|---|---|
| 1 | `snapshot_date` | — | str | ✅ | 查询参数传入 |
| 2 | `snapshot_time` | — | str | ✅ | 固定 `close` |
| 3 | `market` | — | str | ✅ | 固定 `CN` |
| 4 | `limit_up_count` | `涨停家数` | int | — | |
| 5 | `limit_down_count` | `跌停家数` | int | — | |
| 6 | `advance_count` | `上涨家数` | int | — | |
| 7 | `decline_count` | `下跌家数` | int | — | |
| 8 | `flat_count` | `平盘家数` | int | — | |
| 9 | `total_turnover` | `成交额` | float | — | 元 |

> PR-4 空返回导致以上字段均为推断（暂无 live-read 验证）。`akshare.stock_market_fund_flow()` 和 `akshare.stock_zt_pool_em()` 两个 endpoint 的返回结构需后续独立 live-read 在交易日确认。

#### 15.14.2 Endpoint 选择逻辑

| Capability | 当前 endpoint | B2 状态 | 后续选择逻辑 |
|---|---|---|---|
| `sector.snapshot` | `stock_board_industry_cons_em` | SSL 失败 | 单变量网络诊断通过后复验；endpoint 合理无需变更 |
| `sector.ranking` | `stock_board_industry_rank_em` | 未测试（SSL 阻断） | 同 sector.snapshot 诊断后一并测试 |
| `flow.capital_flow_daily` | `stock_individual_fund_flow` | success | 保留，无需变更 |
| `flow.northbound_daily` | `stock_hsgt_individual_em` | success 但语义不匹配 | **Pascal 已选 C（2026-07-26）**：当前 Phase 3 不指向真实 endpoint，`northbound_net_inflow` 恒 None |
| `sentiment.market_snapshot` | `stock_market_fund_flow` | success 但空 | 保留；后续交易日 live-read 复验 |
| `sentiment.limit_up_pool` | `stock_zt_pool_em` | success 但空 | 保留；同 market_snapshot |

**endpoint 变更规则**：
- sector / flow.capital_flow_daily : 当前 endpoint 合理，**不得擅自替换**。
- flow.northbound_daily : **Pascal 已选 C**——当前 Phase 3 fetch 路径不指向真实 endpoint，`northbound_net_inflow` 恒 None；不引入 A/B endpoint skeleton。
- sentiment : endpoint 正确，空返回非 endpoint 问题。

#### 15.14.3 Reporter 账本字段（最小实现）

smoke 报告 YAML 中（§13.4.2 模板）增补以下账本字段（X2 收敛后，仅保留 6 个必要字段）：

| 字段 | 类型 | 说明 | 来源 |
|---|---|---|---|
| `provider_attempts` | int | 该 provider 在当前 smoke 调用中被尝试的次数（含重试） | reporter 统计 |
| `actual_calls` | int | 实际发送至 endpoint 的网络请求数 | reporter 统计 |
| `retry_count` | int | 自动重试次数（当前零重试，字段占位） | reporter 统计 |
| `fallback_count` | int | 切换 fallback provider 的次数（当前零 fallback） | reporter 统计 |
| `mongo_calls` | int | MongoDB 查询次数（当前零查询） | reporter 统计 |
| `write_operations` | int | 持久化写入次数（当前零写入） | reporter 统计 |

> **X2 移除的字段**（不再输出）：`worktree_changed`（runtime git-worktree 探测）、`empty_semantics`（空返回语义分类）。原 V0.16 中这两个字段的定义已由 Pascal 2026-07-26 X2 决策否决。

**最小实现要求**：
- `provider_attempts` / `actual_calls` 为 **REQUIRED** — 反映实际 API 消耗
- `retry_count` / `fallback_count` / `mongo_calls` / `write_operations` 为 **OPTIONAL** — 当前恒为 0，但字段名须在 models.py/Types 中声明占位，不得在 reporter 中硬编码
- reporter **不输出** `worktree_changed` 与 `empty_semantics`（X2 已移除）；空返回 verdict 一律 fail（保守），不引入 verdict 篡改逻辑

#### 15.14.4 Fixture 更新指引

| Fixture 文件 | 更新内容 | 依据 |
|---|---|---|
| `sector_fixtures.py` | SectorSnapshot 的 `leading_stock` / `leading_stock_name` / `pct_chg` 等字段使用中文列名（B2 格式） | AKShare 接口惯例 |
| `flow_fixtures.py` | CapitalFlowRecord 的 `northbound_*` 字段按 C 已选调整（恒 None）；持股历史参考字段（`hold_shares` / `hold_market_value` 等）不映射入 canonical，仅 placeholder | §4.2.1 Pascal 已选 C |
| `sentiment_fixtures.py` | MarketSentimentSnapshot 字段保留现有推断名；不补充 empty_semantics 场景（X2 已移除） | SPEC §14.4.5.3 X2 |

**fixture 约束**：
- 禁止在 fixture 中包含原始 AKShare 列名映射表（该映射在 §4.2.1 / §15.14.1 定义即可）
- fixture 应使用 canonical 字段名，不导入 AKShare 特定依赖
- 所有在 B2 中实测为空的字段（如 PR-4 返回 0 行），fixture 中仍提供 mock 数据（测试需可执行）

#### 15.14.5 验证计划

##### 5.1 单元 / Fixture 测试（T3 Implement 阶段执行）

| 测试文件 | 测试内容 | 涉及 capability |
|---|---|---|
| `test_sector_snapshot.py` | SectorSnapshot 构造、`from_dict()` 松弛映射、边界值 | sector.snapshot, sector.ranking |
| `test_sector_service.py` | SectorService P3-A 方法（mock provider） | sector.snapshot, sector.ranking |
| `test_capital_flow.py` | CapitalFlowRecord 构造、资金流符号约定 | flow.capital_flow_daily |
| `test_flow_service.py` | FlowService（mock provider）；C 路径 stub（northbound 恒 None） | flow.capital_flow_daily, flow.northbound_daily |
| `test_market_sentiment.py` | MarketSentimentSnapshot 构造、温度范围验证 | sentiment.market_snapshot |
| `test_sentiment_service.py` | SentimentService（mock provider） | sentiment.market_snapshot, sentiment.limit_up_pool |
| `test_reporter.py` | Reporter 账本字段输出（6 字段，X2 移除 empty_semantics/worktree_changed） | 全部 |
| `test_provider_mapping.py` | AKShare→Canonical 映射函数（mock akshare 返回值） | 全部 |

##### 5.2 离线回归测试（T3 Implement 阶段执行）

| 验证项 | 方法 | 通过条件 |
|---|---|---|
| 字段映射完整性 | 对每个 capability，mock AKShare 返回与 expected 字段集匹配的数据，验证 canonical 输出字段名/类型正确 | 所有 canonical 字段均被填充 |
| 符号约定验证 | CapitalFlowRecord 的 `*_net_inflow` 正/负值测试 | 正值=净流入，负值=净流出 |
| 空返回处理 | Provider 返回空 DataFrame，验证 service 层返回 `PersistenceResult(status="skipped", reason="empty_payload")` | status=skipped |
| empty_semantics 分类 | **X2 已移除**——不再模拟 empty_semantics 场景；空返回 verdict=fail（保守），reporter 不输出 empty_semantics 字段 | 空返回 verdict=fail，无 empty_semantics 字段 |

##### 5.3 静态零写入扫描（T3 Implement 阶段执行）

| 扫描项 | 工具 | 通过条件 |
|---|---|---|
| DataRouter.query() 无 materialize | spy 验证：`_materialize()` 在 P3 capability query 路径中不被调用 | spy 计数=0 |
| 无未授权的 Mongo 写入 | grep `insert\|update\|delete\|bulk_write` 在 query 路径代码中 | 0 匹配（显式 refresh 路径除外） |
| 无硬编码集合名 | grep `03_data_ud_` 在 provider/service 层 = 仅通过配置/参数引用 | 无直接字符串字面量 |
| reporter 账本字段完整性 | grep 账本字段名在 reporter 输出函数中 | 6 个字段全部声明（X2 移除 worktree_changed/empty_semantics） |

##### 5.4 后续独立 Live-Read 验证计划（T4 阶段，不在本阶段执行）

| 步骤 | 内容 | 前置条件 | 执行人 |
|---|---|---|---|
| LR-1 | PR-2 SSL 单变量网络诊断 | Pascal 授权 | Pascal / DevOps |
| LR-2 | sector.snapshot + sector.ranking live-read（复验推断字段集） | LR-1 pass | Pascal / DevOps |
| LR-3 | flow.northbound_daily live-read（验证 C 落地：northbound_net_inflow 恒 None） | Pascal 已选 C（2026-07-26） | Pascal / DevOps |
| LR-4 | sentiment.market_snapshot + limit_up_pool 交易日 live-read（复验空返回语义） | 交易日当天 | Pascal / DevOps |
| LR-5 | 全 capability 差异复验（B2→修正后字段映射） | LR-2/3/4 pass | Pascal / DevOps |

> **LW-1**：Live-read 预算：每个 LR 步骤仅允许单日单标的单次调用（≤3 次/步骤），**不自动重试**，**不降级为写入**。所有 LR 须在 Pascal 明确授权后执行。

#### 15.14.6 风险与边界

| # | 风险 | 影响 | 缓解措施 |
|---|---|---|---|
| R-1 | ~~Pascal 尚未选择 PR-3 三选一（A/B/C），T3 Implement 无法继续~~ **已解决**：Pascal 2026-07-26 已选 C，northbound_net_inflow 恒 None，fetch 路径不指向真实 endpoint | 无阻塞 | C 已选：T3 实施 `flow.northbound_daily` 的 fetch 路径返回恒 None 的 stub；持股历史作为辅助参考字段标注但不映射入 canonical |
| R-2 | PR-2 SSL 网络诊断持续受阻（基础设施限制），sector 推断字段集一直无法 live-read 验证 | sector 映射停留在推断状态 | T3 按推断字段集实现，标注「未 live-read 验证」；验收时接受 conditional_pass |
| R-3 | ~~PR-4 的 `empty_semantics=undetermined` 在后续交易日 live-read 后收敛为 `no_trading_data`~~ **X2 已移除 empty_semantics**：空返回 verdict=fail（保守），reporter 不再区分空返回语义 | 无影响 | X2 收敛后 reporter 不输出 empty_semantics；后续 live-read 返回非空数据时按正常字段匹配流程判定 |
| R-4 | 零写入边界的 runtime 保证被 T3 实现意外突破 | 生产数据污染 | 通过 §15.14.5.3 静态零写入扫描 + Review RC-4/RC-5 双重防御 |

## 16. 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.12-T2.5 | 2026-07-24 | **Design Correction（T2.5 消除 authSource fallback 字面量与 dry-run/live-read 状态对象混淆）**。基于 T2.4 Re-Review (PASS) 的两项残余张力修正：(1) §15.5.2 `build_client()` 的 `authSource` 从 `parsed.get("MONGODB_DATABASE", "tradingagents")` 改为 `parsed["MONGODB_DATABASE"]` 直接取值——移除 fallback 字面量，键缺失时 fail-fast KeyError；同步更新 §15.5.2 不可违反复核清单对应描述。(2) §15.3.2/§15.3.3 入口分别新增状态对象语义声明——dry-run 的 `SecretProbeResult` 不含 key 级字段，live-read 的 `ResolvedConfig.*_resolved` 含 key 级布尔，两者语义隔离不重叠；同步更新 §15.4.1 SecretProbeResult docstring。V0.12 主体版本号不变，追加 T2.5 标记。 | **YQuant-Codex-Principal（T2.5）** |
| V0.11 | 2026-07-24 | **PR-1 凭证来源契约对齐 T1 t_cafc0903**。基于 RFC-03-014 V0.6 / SPEC-03-014 V0.5 裁定，将 MongoDB 连接凭据来源从 MONGO_URI + `$(pwd)/.env` + Hermes profile `.env` 统一为复用 Phase 2 `skills/.env` 五组件键（MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE）。具体变更：§15.3.2 Dry-Run 输出改为五组件键声明状态；§15.3.3 Live-Read 门槛改为检查五键全部 authorized；§15.4.2 审计矩阵重写——候选源从 3 路径缩为单一 `skills/.env`，`MONGO_URI` 全部标为 superseded；§15.5.2 重写——新增 `LegacyConfigResolver` 组件式解析 + `PreflightRunner` 预检流程，消除 `MongoClientFactory` URI 构造模式；§15.5.4 新增 `env_missing` 失败分类；§15.10.2/§15.10.3 验收命令预期输出同步更新。 | **YQuant-Codex-Principal** |
| V0.9 | 2026-07-22 | **Principal 正式裁定收口（本卡 T5C2）**。正式确认 §15.2 allowlist 的 `scripts/__init__.py` package marker 进入正式契约；§15.12 重写为分类治理边界：`tmp_out_mongo/` 推荐 Implement 阶段迁移至 `tmp_path`（`docs/**/smoke_reports/` 保持 `.gitignore`）。V0.8 由 Developer 临时落地，本版由 Principal 正式裁决。RFC-03-014 / SPEC-03-014 不变（allowlist 属 DESIGN 级实现细节）。 | **YQuant-Principal** |
| V0.8 | 2026-07-22 | **T4 测试副作用收口（临时落地）**。§15.2 allowlist 由 22 增至 23 个正式文件，新增 `scripts/__init__.py` package marker；§15.12 固化 `tmp_out_mongo/` 与 `docs/**/smoke_reports/` 的根 `.gitignore` 规则。RFC-03-014 / SPEC-03-014 不变。 | YQuant-Developer-Engineer |
| V0.7 | 2026-07-22 | **T4 Preflight & Smoke 工具链设计**（新增 §15）。定义 T4 阶段的 22 文件 allowlist、CLI 入口与安全契约、SecretVerifier 非泄露接口、MongoDB 零写入预检、Provider smoke 安全包装、报告脱敏、退出码分类、零写入 spy 机制、Verify/Review 验收命令与 Review PASS 后的 live-read 执行流程。与 RFC-03-014 V0.3 §13 及 SPEC-03-014 V0.3 §14 完全对齐。 | YQuant-Codex-Principal |
| V0.6 | 2026-07-22 | Contract Gate Adjudication — 闭合 Fix-M23 Review 发现的 PersistenceResult §5.4.1 契约冲突 | YQuant-Principal |
| V0.5 | 2026-07-21 | Design Correction（T2.8 闭合 MINOR-N2） | YQuant-Principal |
| V0.4 | 2026-07-21 | Design Correction（T2.6 消除 T2.5 REVISE 阻断） | YQuant-Principal |
| V0.3 | 2026-07-21 | Design Correction（T2.4 实现边界冻结） | YQuant-Principal |
| V0.2 | 2026-07-21 | Design Correction（T2.2 REVISE） | YQuant-Principal |
| V0.1 | 2026-07-21 | 初始创建 | YQuant-Principal |
