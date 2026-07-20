# RFC-03-013：Unified Data Phase 1E — 情绪数据最小垂直切片

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-20 |
| 最后更新 | 2026-07-20 |
| 版本号 | V0.1 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-011（Phase 2 质量与审计治理） |
| 依赖 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-008（Phase 1B-A 查询平面）、SPEC-03-013（Phase 1E Sentiment Minimal Slice） |
| 关联 Design | DESIGN-03-013（Phase 1E 情绪数据最小垂直切片，后续 T2 交付） |
| 替代 RFC | 无（不替代任何 RFC；为情绪数据域首次形式化定义） |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #sentiment #phase1e #capability |

### 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-20 | 初始创建。定义 Phase 1E 为 Unified Data 的情绪数据垂直切片，限定为 CN 个股标准化情绪分数单项能力，明确非目标、数据源风险、验收边界与授权门禁。 | YQuant-Principal |

---

## 1. 执行摘要

Phase 1E 为 Unified Data 新增 `sentiment.stock_score` 这一标准化情绪分数能力，覆盖 CN 个股。当前系统只通过 `NewsItem.sentiment`（原始字符串，取值 "positive"/"neutral"/"negative"）附带在新闻条目中，没有独立的情绪分数 capability、没有标准化数值评分、没有置信度、没有模型/规则可追溯性、没有统一契约。Phase 1E 不构建完整情绪平台、不接入真实 API、不持久化写入 MongoDB、不运行 NLP 模型，仅定义能力契约、记录规范、读取路径与 fixture 验证框架，为后续 Phase 2+ 接入真实数据源和持久化提供可执行的基线。

## 2. 背景与动机

### 2.1 现状

| 现状 | 说明 |
|---|---|
| `NewsItem.sentiment` 仅作为新闻附带的字符串标签 | 存在于 `stock_news` 集合和 `NewsItem` domain object，无统一分数、无置信度、无模型版本；消费方无法区分「未分析」「可信度低」「不同模型产出」 |
| 无独立的情绪 capability | `sentiment.*` 不在任何 Provider 的 `capabilities` 集合中，不存在专用 Router 路由、external_fallback_chain 或 FreshnessPolicy |
| 无情绪数据质量标记 | 与 Phase 2 QualityScorer 的 quality_score 没有对接，消费方无法判断情绪分数的可信度 |
| DSA 情绪数据不经过 Unified Data | DSA 的 `social_sentiment_service.py`（`skills/research/daily_stock_analysis/src/services/social_sentiment_service.py`）是其私有实现，不对外提供统一契约 |

### 2.2 业务价值

引入标准化情绪能力后，消费方（strategies、research、reports、argus）可以通过 `UnifiedDataClient` 的统一接口获取 CN 个股的情绪分数，无需各自对接不同数据源或处理不同 schema。最小垂直切片验证了 capability 路径后，后续 Phase 可以低摩擦接入真实情绪数据源（Tushare 新闻情绪、AKShare 舆情因子、LLM 分析等）。

### 2.3 触发原因

需求驱动：Pascal 选择情绪作为 Phase 1B 之后的下一优先域。Phase 1D 已验证「外部 Provider 真实激活」的完整链路，现将其经验和契约模式复制到情绪域——先定义契约和能力边界，再逐步激活真实数据。

### 2.4 命名衔接：Phase 1E

本阶段紧接 Phase 1D 之后、与 Phase 2（质量审计治理，RFC-03-011）独立且可并行：

| Phase | 名称 | 定位 |
|---|---|---|
| 1D | External Provider Activation | 激活 `kline_daily` 真实调用 |
| **1E** | **Sentiment Minimal Slice** | **新增 `sentiment.stock_score` capability，契约+fixture 优先，不触外部网络** |
| 2 | Quality & Audit Governance | 质量评分、审计日志、Provider 治理 |
| 3 | 重要持久化扩展 | 市场情绪快照、资金流、板块等真实数据集合 |

Phase 1E **不是** Phase 3 的替代或前置；Phase 3 的 `03_data_ud_market_sentiment_snapshot` 是市场级别的（涨停家数、温度指数等），而 Phase 1E 聚焦**个股级别标准化情绪分数**，两者构成完整的情绪数据栈（个股分数→市场聚合）。

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 定义 `sentiment.stock_score` capability，明确 domain="sentiment"、operation="stock_score"
- [ ] 定义 `StockSentimentScore` canonical domain object：数值分数（-1.0~1.0）、标签（positive/neutral/negative/unknown）、置信度（0.0~1.0）、模型/规则版本号、时间戳、来源、来源条目 ID、语言、质量标记
- [ ] 在 `Capability` 枚举注册 `sentiment.stock_score`，支持消费方通过 `has_capability("sentiment.stock_score", market="CN")` 查询
- [ ] 定义 `external_fallback_chains` 中 `sentiment.stock_score` 的 fallback 顺序，但 Phase 1E **所有 provider 返回 stub/fixture 数据**（不做真实调用）
- [ ] 定义 FreshnessPolicy `sentiment` domain TTL 基准值（建议 3600s，与盘中情绪高频需求一致；由 T2 Design 确定最小实现落点）
- [ ] 定义读取路径：只读 fixture 验证（不修改 Router 已有 internal-first 编排）
- [ ] fixture 验证框架：最小 2 条 `StockSentimentScore` fixture 数据，覆盖正/负/未知情绪；Router 查询验证 capability 注册与非 fallback 行为
- [ ] 文档中交叉引用现有 RFC-03-007（总纲）、Phase 2（quality_score 对接预留）、Phase 3（市场情绪快照与个股分数的层级关系）

### 3.2 非目标（Out of Scope）

- **不做真实外部 API 调用**：不调用 Tushare/ AKShare/ 其他 API 获取情绪数据；所有 provider 基于 fixture/ stub
- **不做 NLP 模型或情绪分析**：不引入 LLM、BERT、词典方法等情绪计算；分数由数据源提供或 fixture 构造
- **不做 MongoDB 持久化写入**：不创建 `03_data_ud_*` 集合；不写 CacheManager / AuditLogger / QualitySummary
- **不做市场级情绪聚合**：不涉及 `03_data_ud_market_sentiment_snapshot`（涨停家数、温度指数等，属 Phase 3）
- **不做实时 SLA 承诺**：本次定义的 TTL 和 FreshnessPolicy 是基准建议，不实现真实刷新
- **不做自动交易信号**：情绪分数是辅助数据，不构成买入/卖出决策依据
- **不修改现有 API**：`UnifiedDataClient` 不新增方法；`get_news()` 的 `NewsItem.sentiment` 保留原样，`sentiment.stock_score` 通过 `query("sentiment", "stock_score", sid)` 访问
- **不触及 NewsItem 已有 sentiment 字段**：`NewsItem.sentiment`（string）保持向后兼容，不修改其类型或语义
- **不新增外部 Provider 注册**：TushareProvider / AKShareProvider 已声明 `news.stock_news` 但不声明 `sentiment.stock_score`；此能力当前无真实 Provider
- **不实现 data-pipeline / cron / task_center 集成**

## 4. 整体设计

### 4.1 核心设计哲学

情绪数据作为 Unified Data 的独立域（`sentiment`），与市场数据（`market_data`）、财务（`financial`）等域并列。Phase 1E 仅定义契约和骨架，不做任何真实数据获取——保证消费方代码可以按统一接口开发，而真实数据注入是后续 Phase 的职责。

### 4.2 架构总览

```
消费方 (strategies/reports/research)
       │ UnifiedDataClient.query("sentiment", "stock_score", sid)
       ▼
┌─────────────────────────────┐
│        DataRouter           │  ← capability → external_fallback_chain
│    sentinel.stock_score     │     (当前为空：无真实 provider)
└─────────────┬───────────────┘
              │
   ┌──────────┴──────────┐
   │  DataResult<StockSentimentScore> │
   │  .succeeded / .is_empty          │
   └─────────────────────────┘
```

由于 Phase 1E 不激活真实 provider，`sentiment.stock_score` 的 fallback 链为空或仅含「占位 stub provider」——Router 返回 `DataResult.error(provider="error")` 或 fixture 驱动的 mock。消费方代码按 Handle empty/error 编写。

### 4.3 与已有情绪数据的层级关系

```
┌──────────────────────────────────────────────────────┐
│                 情绪数据栈（Unified Data 视角）          │
├──────────────────────────────────────────────────────┤
│  ├─ Phase 1A ✅ NewsItem.sentiment  (string 标签，     │
│  │    附属于 stock_news 集合/新闻条目内)                │
│  ├─ Phase 1E 📋 StockSentimentScore (标准化数值分数，  │
│  │    独立 capability，契约先于数据)                   │
│  └─ Phase 3 📅 MarketSentimentSnapshot (市场级聚合，  │
│        涨停/跌停/温度指数等)                           │
└──────────────────────────────────────────────────────┘
```

三个层级互相补充，不互相替代：`NewsItem.sentiment` 保持向后兼容；`StockSentimentScore` 是更丰富、独立的个股分数；`MarketSentimentSnapshot` 是市场全局视图。

## 5. 详细设计

### 5.1 业务流程（Flow）

**触发条件**：消费方通过 `router.query("sentiment", "stock_score", security_id, ...)` 或 `client.query(...)` 请求个股情绪。

**正常分支**：
1. Router 解析 capability → `sentiment.stock_score`
2. 查找 external_fallback_chain（Phase 1E 为空 → 无外部 provider 可 fallback）
3. TA-CN step 1 检查（Phase 1E：TA-CN adapter 不实现 `get_stock_sentiment`，保持 stub）
4. 全部跳过 → 返回 `DataResult.error(provider="error", source_trace=[])`，或 fixture 测试路径返回 mock 数据

**异常降级分支**：
- 无外部 provider → 返回空 error；消费方按 `.is_empty` 或 `.succeeded == False` 处理

### 5.2 数据模型

```python
@dataclass
class StockSentimentScore:
    """个股标准化情绪分数 — Phase 1E。

    每条记录表示个股在某观测时点的一个标准化情绪评估。
    分数由外部情绪数据源提供，Phase 1E 不生产分数。
    """
    symbol: str                         # 标的代码（如 "600519"）
    market: str                         # 市场（如 "CN"）
    sentiment_score: float | None       # 标准化情绪分数，取值 [-1.0, 1.0]
    label: str | None                   # 标签："positive" / "neutral" / "negative" / "unknown"
    confidence: float | None            # 置信度，取值 [0.0, 1.0]；None = 数据源未提供
    source: str                         # 数据来源标识（如 "tushare_news_sentiment", "akshare_sentiment", "fixture"）
    source_item_id: str | None          # 来源原始条目 ID（如新闻 ID、报告 ID），用于溯源
    model_version: str | None           # 情绪分析模型/规则版本（如 "v1.0", "rule-based-2026Q2"）
    observed_at: str                    # 情绪被观测/计算的时间点，格式 "YYYY-MM-DDTHH:MM:SS+08:00"
    as_of_date: str                     # 情绪对应的交易日/日期，格式 "YYYY-MM-DD"
    language: str | None                # 文本语言（如 "zh-CN", "en"），None = 未知
    summary_text: str | None            # 文本摘要或引用（不存储全文，仅用于追溯上下文）
    quality_flags: dict | None          # 质量标记（Phase 2 placeholder；如 {"is_stale": true}）
    ingested_at: str | None             # 记录被 Unified Data 摄取的时间，格式 ISO-8601

    @classmethod
    def from_dict(cls, d: dict) -> "StockSentimentScore":
        """从字典构造，缺失字段填 None。"""
        ...
```

### 5.3 接口契约

**Router 查询路径**（不新增 API）：
```
DataRouter.query(
    domain="sentiment",
    operation="stock_score",
    security_id=SecurityId(market="CN", symbol="600519"),
    params={"as_of_date": "2026-07-20"}  # 可选：指定日期
) -> DataResult
```

**DataResult.data 类型**：`list[StockSentimentScore]`（Phase 1E 的 `DataResult.data` 是 `Any`，与 Phase 0 一致）

**外部 fallback 链**（Phase 1E 为空）：
```python
# UnifiedDataConfig 新增
capability_fallback_overrides = {
    "sentiment.stock_score": (),  # 空 — 无真实 provider
}
```

### 5.4 Capability 注册

Capability 常量（如后续新增常量模块，由 T2 Design 裁定）：

```python
# 在项目已有 CAPABILITY 常量模块中新增
SENTIMENT_STOCK_SCORE = "sentiment.stock_score"
```

外部 fallback 链通过 `DataRouter` 构造参数 `external_fallback_chains` 传入（优先级：constructor → `UnifiedDataConfig.capability_fallback_overrides` → registry 注册顺序）；Phase 1E 传入空链：

```python
external_fallback_chains = {
    "sentiment.stock_score": [],  # Phase 1E: 无真实 provider
}
```

STUB_COLUMNS 新增 stub 列（在 `providers/__init__.py` 的 `STUB_COLUMNS` dict 中）：
```python
"sentiment.stock_score": [
    "symbol", "market", "sentiment_score", "label", "confidence",
    "source", "source_item_id", "model_version", "observed_at",
    "as_of_date", "language",
],
```

## 6. AI 实装规范

### 6.1 必须执行

- `sentiment.stock_score` 所有 provider 返回 stub/fixture，**不得**发真实网络请求
- 新增 canonical domain object 必须在 `models/domain/` 下独立文件 `sentiment.py`
- fixture 数据写在 `skills/data/unified_data/tests/fixtures/` 下
- 所有变更保留可追溯的 git diff

### 6.2 先询问再执行

- 需要修改 `DataRouter` 的 internal-first 编排逻辑（Phase 1E 预期不改）
- 需要新增 `UnifiedDataClient` 方法（Phase 1E 预期不新增）
- 需要操作 MongoDB 或创建集合（Phase 1E 禁止）

### 6.3 绝对禁止

- 调用任何外部 API、网络请求
- 读取 `.env` 或真实凭据
- 写 MongoDB（含 CacheManager、AuditLogger、QualitySummary）
- 修改 Phase 1A 已有 domain object 的字段签名（如 `NewsItem.sentiment` 的类型）
- 修改 RFC/SPEC 模板或项目全局 README

## 7. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| 情绪分数规范过于简化，后续真实数据源无法对齐 | 中 | 中 | 字段设计保留 `model_version` + `source_item_id` + `quality_flags` 扩展点；`from_dict()` 宽松映射 | 后续 Phase 可继承本契约添加字段，不修改已有字段类型 |
| sentiment_score 取值区间理解不一致 | 低 | 中 | 明确 -1.0（最负面）~ 1.0（最正面），0.0 = 中性，None = 未计算 | 消费方使用时判断 `None` |
| 与 Phase 3 market_sentiment_snapshot 范围重叠混淆 | 中 | 低 | 在 RFC/SPEC/Design 中明确层级关系：个股分数 vs 市场聚合快照 | 消费方根据场景选择对应 capability |
| 消费方错误将情绪分数解释为交易信号 | 低 | 高 | RFC §1/§3.2 明确声明「辅助数据，不构成交易决策」；后续 Design 在 API docstring 中重申 | 不需要降级，属消费方使用规范 |
| 后续真实 Provider 可用性有限（quota/频率） | 中 | 中 | Phase 1E 契约预留 source_trace + quality_flags，后续 Phase 可以标记数据可用性问题 | 消费方在 query 时通过 `.warnings` 或 `.quality_flags` 感知 |
| provider 模型版本号格式不统一 | 中 | 低 | `model_version` 字段为自由字符串，不做强校验 | 后续 Phase 可引入版本号治理 |

## 8. 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **A. Phase 1E 最小切片（选定）** | 风险隔离、验证 capability 路径后扩展、不过度设计 | 消费方在 Phase 1E 无法获取真实数据 | 契约先于数据，符合 Unified Data 分层原则 |
| **B. 直接跳到 Phase 3 全量情绪快照** | 一次性获得完整情绪能力（含市场级数据） | 范围过大、缺少个股级标准化分数的契约基础 | Phase 3 的市场级情绪快照与个股分数正交，不宜跳过 |
| **C. 复用 NewsItem.sentiment 不新增 capability** | 零工作量 | 无法表达置信度、模型版本、数值分数；消费方只能拿到字符串标签 | sentiment 独立 capability 的必要性已由 Pascal 确认 |
| **D. 在 TushareProvider 声明 sentiment.stock_score** | 复用现有 provider 架构 | 真实 Tushare 新闻情绪接口未经验证；会误报 capability 可用性 | Phase 1E 不声明任何真实 provider 的 sentiment capability |

## 9. 验收标准

### 9.1 功能验收

- [ ] `sentiment.stock_score` 在外部 fallback 链、STUB_COLUMNS、FreshnessPolicy（默认注册）中正确举例
- [ ] `StockSentimentScore` domain object 定义完整，含字段类型、必填非空说明
- [ ] fixture 测试：最小 2 条 fixture 数据覆盖正面/负面/未知情绪；`Router.query()` 在 mock provider 注册后返回值正确
- [ ] 现有 48 项测试 Regression PASS（Phase 1D 基线）
- [ ] `git diff --check` exit 0

### 9.2 非功能验收

- [ ] 文档明确情绪分数**不构成交易决策**（在 RFC/SPEC 中声明）
- [ ] 与 Phase 3 市场情绪快照的层级关系在文档中明确定义
- [ ] 质量标记字段（`quality_flags`）预留 Phase 2 对接点

## 10. 落地计划

### 10.1 阶段划分

| 阶段 | 阶段编号 | 产出 |
|---|---|---|
| T1 RFC+SPEC | 本文档 + SPEC-03-013 | 需求定义、契约规范、验收标准 |
| T2 Design | DESIGN-03-013 | 设计细节、文件清单、测试计划 |
| T3 Implement | — | 代码实现 |
| T4 Verify | — | 测试验证 |
| T5 Review | — | 独立审查 |
| Closeout | — | 收口 |

### 10.2 T2 Design 建议输入

T1 为本阶段 RFC+SPEC。建议 T2 Design 阶段重点关注以下输入：

1. **文件清单**：`skills/data/unified_data/models/domain/sentiment.py`（新增）、`skills/data/unified_data/tests/fixtures/sentiment_fixtures.py`（新增）、`skills/data/unified_data/tests/test_sentiment_*.py`（新增）
2. **外部 fallback 链**：`sentiment.stock_score` 在 Phase 1E 为空；通过 `Router(external_fallback_chains=...)` 构造参数传入
3. **STUB_COLUMNS**：在 `providers/__init__.py` 的 `STUB_COLUMNS` 中新增 `sentiment.stock_score` 条目
4. **FreshnessPolicy**：在 `freshness.py` 中为 `sentiment` domain 注册 TTL，建议值 3600s（1h）；由 T2 确定最小实现落点
5. **DataRouter**：在 `router.py` 的 `_TA_CN_NOT_COVERED` 集合中确认 `sentiment.stock_score` 不属于 TA-CN 覆盖范围
6. **Capability const**：考虑是否在 capabilitiy 常量模块中定义 `SENTIMENT_STOCK_SCORE = "sentiment.stock_score"`（类似 `KLINE_DAILY_CAPABILITY`）
7. **fixture 设计**：至少 2 条 mock 记录，覆盖正/负两种情绪；Router fixture 中注册一个 `MockSentimentProvider` 用于验证查询路径

## 11. 开放问题

- [ ] OQ-1：`sentiment` domain TTL 基准值 3600s 是否合适？如需盘中高频刷新（如 15min），可调整为 900s。本阶段仅定义建议值不实现刷新。
- [ ] OQ-2：`sentiment_score` 的取值区间是否有必要限制为 [-1.0, 1.0]？还是允许部分数据源输出 [0, 100] 等区间？本阶段保留 `float | None` 不做额外约束。
- [ ] OQ-3：是否需要在 Phase 1E 就引入 `quality_score`（Phase 2 QualityScorer 的字段）的预留位？当前通过 `quality_flags: dict` 占位，后续若需要正式字段可在 Design 阶段裁定。
- [ ] OQ-4：`as_of_date` 与 `observed_at` 的区分是否清晰？`as_of_date` = 情绪对应的业务日期（交易日），`observed_at` = 情绪被计算/采样的精确时间点。Review 阶段确认是否满足消费方需求。

## 12. 参考资料

- RFC-03-007（Unified Data Layer 总纲）
- RFC-03-011（Phase 2 质量与审计治理）
- RFC-03-012（Phase 1D CN 日线真实外部 Provider 激活）
- SPEC-03-007（Unified Data Layer 契约基线）
- SPEC-03-008（Phase 1B-A 查询平面）
- DESIGN-03-007（Unified Data Layer 详细设计），§5.3.2 `03_data_ud_market_sentiment_snapshot`、§Phase 3
- `skills/data/unified_data/models/domain/news.py`（NewsItem 已有 sentiment 字段）
- `skills/research/daily_stock_analysis/src/services/social_sentiment_service.py`（DSA 私有情绪服务）
