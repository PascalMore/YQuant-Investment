# SPEC-03-013：Unified Data Phase 1E — 情绪数据最小垂直切片

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-20 |
| 最后更新 | 2026-07-20 |
| 来源 RFC | RFC-03-013（Phase 1E Sentiment Minimal Slice） |
| 关联 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-011（Phase 2 质量与审计治理） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-008（Phase 1B-A 查询平面） |
| 关联 Design | DESIGN-03-013（Phase 1E Sentiment Minimal Slice，后续 T2 交付） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 版本号 | V0.1 |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

### 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-20 | 初始创建。将 RFC-03-013 的 Phase 1E 情绪数据最小切片需求落为可执行契约，定义 `sentiment.stock_score` capability、`StockSentimentScore` schema、ETLV 验证点、读/写路径边界、fixture 验收标准。 | YQuant-Principal |

---

## 0. 术语对齐与基线锚定

本 SPEC 继承 RFC-03-007 / SPEC-03-007 / SPEC-03-008 的全部基线，不重述背景，只锁定 Phase 1E 必须一致的措辞：

- **Phase 1E** = Sentiment Minimal Slice。紧接 Phase 1D 之后，与 Phase 2（质量审计治理）独立可并行。
- **新增唯一能力** = `sentiment.stock_score`，domain = `sentiment`，operation = `stock_score`，market = `CN`。
- **不声明任何真实 provider 的 sentiment capability**：TushareProvider、AKShareProvider、TA-CN adapter 均不新增 `sentiment.stock_score` 到其 `capabilities` 集合。
- **external_fallback_chain（sentiment.stock_score）** = 空元组 `()`。Phase 1E 无真实外部 provider，Router fallback 路径在 Step 4 无 provider 可调用，返回 `DataResult.error(provider="error", source_trace=["sentiment.stock_score: no fallback providers"])`。
- **DataResult 语义**：当无 provider 可 fallback 时，Router 返回 `DataResult.error(provider="error")`；fixture/测试路径使用 mock provider 返回 `DataResult.success(...)`。
- **StockSentimentScore** 定义见 §2。不修改任何已有 domain object 的签名。

### 0.1 与 SPEC-03-007 / SPEC-03-008 的关系

本 SPEC 是 `sentiment.stock_score` 能力的形式化定义，不替代 SPEC-03-007 / SPEC-03-008：

- SPEC-03-007 定义了 Market、SecurityId、Capability、DataResult、DataProvider、ProviderRegistry、DataRouter、UnifiedDataClient、UnifiedDataConfig 的全部基线——**全部沿用，不修改签名**。
- SPEC-03-008 定义了 DataRouter internal-first 编排、`external_fallback_chains`、FreshnessPolicy、RateLimiter——**全部沿用**。Phase 1E 仅在 `external_fallback_chains` 中预留 `sentiment.stock_score` 条目（空值），在 FreshnessPolicy 中注册默认 TTL。
- 本 SPEC 只对 `sentiment.stock_score` 的字段契约、fixture 设计、验证点、不改动清单制定可执行规范。

### 0.2 六项不变量逐条对应（RFC-03-007 §14 / SPEC-03-007 §0.2）

| # | 不变量 | Phase 1E SPEC 落点 |
|---|---|---|
| 1 | 共享物理数据库 `tradingagents` | §6 不改动清单：不新增集合、不写数据库 |
| 2 | Internal-First 读取路径 | §2.3：`sentiment.stock_score` 属 TA-CN 不覆盖能力，fallback 链为空 |
| 3 | DSA 不是运行时数据源 | §2.2 Out of Scope：不实现 DSA sentiment adapter |
| 4 | Collection Ownership 不可回写 | §6：不写任何集合 |
| 5 | Task Center 先行 | §2.2：不实现 Task Center |
| 6 | 三层语义分离 | §4.bis：无持久化，不触碰 `03_data_ud_*`/`03_data_ud_cache_*` |

---

## 1. 需求摘要

将 RFC-03-013 的 Phase 1E 情绪数据最小垂直切片需求落为可执行契约，核心交付 3 件事：

1. **`StockSentimentScore` canonical domain object**：在 `models/domain/sentiment.py` 中定义标准化情绪分数记录的数据结构，含 14 个字段（类型、必填性、语义严格定义）。
2. **Capability / Router / Stub / Freshness 注册**：在 proviers 注册、stub columns、FreshnessPolicy 等处注册 `sentiment.stock_score` 占位条目；external_fallback_chain 为空。
3. **Fixture 验证框架**：最小 2 条 mock `StockSentimentScore` 记录，覆盖正面/负面情绪；Router 查询验证 capability 注册与非 fallback 行为；Regression 确认现有 48 项测试不受影响。

全部组件用 fixture/mock 验证，**不依赖真实网络、真实 token、真实 Mongo 写入**。

---

## 2. 范围

### 2.1 In Scope

- [ ] `StockSentimentScore` domain object 定义（`models/domain/sentiment.py` 新增文件）
- [ ] `sentiment.stock_score` 在 `external_fallback_chains` 中注册（空链：通过 `Router(external_fallback_chains=...)` 构造参数传入）
- [ ] `sentiment.stock_score` 在 `providers/_stub_columns.py` 的 `STUB_COLUMNS` 中注册（stub 列名）
- [ ] `sentiment` domain 在 `freshness.py` 的 FreshnessPolicy 中注册（默认 TTL = 3600s）
- [ ] `sentiment.stock_score` 在 `router.py` 的 `_TA_CN_NOT_COVERED` 中确认不属于 TA-CN 覆盖范围
- [ ] fixture 数据（`skills/data/unified_data/tests/fixtures/sentiment_fixtures.py` 新增，至少 2 条 mock 记录）
- [ ] Router 测试（`skills/data/unified_data/tests/test_sentiment_*.py` 新增，验证 capability 注册、查询路径、无 fallback 行为）
- [ ] Regression 确认：现有 48 项（Phase 1D 基线）已存测试全 PASS

### 2.2 Out of Scope

- **不做真实 API 调用**：不调用 Tushare、AKShare、或其他外部情绪数据 API
- **不做情绪计算/NLP**：不引入 LLM、BERT、词典等；不实现情绪分析逻辑
- **不做 MongoDB 持久化**：不写 `03_data_ud_*` 集合；不写 CacheManager / AuditLogger / QualitySummary
- **不新增 UnifiedDataClient 方法**：消费方通过 `client.query("sentiment", "stock_score", sid)` 访问；不添加 `client.get_stock_sentiment(sid)` 方法
- **不修改 NewsItem 已有 sentiment 字段**：`NewsItem.sentiment`（`str | None`）保持向后兼容
- **不修改 DataRouter 编排逻辑**：sentiment.stock_score 走现有 Step 1→2→3→4 路径不变
- **不声明真实 provider 的 sentiment 能力**：TushareProvider、AKShareProvider 的 `capabilities` 不变
- **不实现 data-pipeline / cron / task_center 集成**
- **不实现 DSA sentiment 适配器**

---

## 3. StockSentimentScore — 字段级契约

```python
# skills/data/unified_data/models/domain/sentiment.py

@dataclass
class StockSentimentScore:
    """个股标准化情绪分数（Phase 1E）。

    每条记录表示个股在某观测时点的情绪评估。
    分数由外部数据源/模型产生，本域不生产分数。
    """
    symbol: str                             # (必填) 标的代码，如 "600519"
    market: str                             # (必填) 市场，如 "CN"
    sentiment_score: float | None = None    # [可选] 标准化分数 -1.0~1.0；None=未计算
    label: str | None = None                # [可选] 标签：positive/neutral/negative/unknown
    confidence: float | None = None         # [可选] 置信度 0.0~1.0；None=数据源未提供
    source: str = ""                        # (必填) 数据来源标识，如 "fixture"
    source_item_id: str | None = None       # [可选] 来源原始条目 ID，用于溯源
    model_version: str | None = None        # [可选] 模型/规则版本号，如 "v1.0"
    observed_at: str | None = None          # [可选] 情绪被观测的精确时间，ISO-8601
    as_of_date: str = ""                    # (必填) 情绪对应交易日，格式 "YYYY-MM-DD"
    language: str | None = None             # [可选] 文本语言，如 "zh-CN"
    summary_text: str | None = None         # [可选] 文本摘要/引用（不存储全文）
    quality_flags: dict | None = None       # [可选] 质量标记（Phase 2 预留占位）
    ingested_at: str | None = None          # [可选] 摄取时间，ISO-8601 格式

    @classmethod
    def from_dict(cls, d: dict) -> "StockSentimentScore":
        """从字典构造，缺失字段填 None。松弛映射，不抛 KeyError。"""
        return cls(
            symbol=str(d.get("symbol", "")),
            market=str(d.get("market", "")),
            sentiment_score=d.get("sentiment_score"),
            label=d.get("label"),
            confidence=d.get("confidence"),
            source=str(d.get("source", "")),
            source_item_id=d.get("source_item_id"),
            model_version=d.get("model_version"),
            observed_at=d.get("observed_at"),
            as_of_date=str(d.get("as_of_date", "")),
            language=d.get("language"),
            summary_text=d.get("summary_text"),
            quality_flags=d.get("quality_flags"),
            ingested_at=d.get("ingested_at"),
        )
```

### 3.1 字段语义

- **`sentiment_score`（float | None）**：标准化的情绪分数，范围为闭区间 `[-1.0, 1.0]`。`-1.0` = 最负面，`0.0` = 中性，`1.0` = 最正面。`None` = 该记录未包含数值分数（例如仅标记了 `label`）。
  - `-1.0`: 最负面
  - `-0.5 ~ -1.0`: 较强负面
  - `-0.1 ~ -0.5`: 轻微负面
  - `0.0`: 中性
  - `0.1 ~ 0.5`: 轻微正面
  - `0.5 ~ 1.0`: 较强正面
  - `1.0`: 最正面
- **`label`（str | None）**：情绪标签。允许值 `"positive"`、`"neutral"`、`"negative"`、`"unknown"`。`None` = 标签未生成。
- **`confidence`（float | None）**：模型/规则对情绪判断的置信度，范围 `[0.0, 1.0]`。`0.0` = 完全不确定，`1.0` = 完全确定。`None` = 数据源未提供置信度。
- **`model_version`（str | None）**：产生该评分的模型或规则版本。预期值如 `"tushare-default-v1"`、`"akshare-sentiment-v2"`、`"llm-gpt4-2026Q2"`、`"fixture"`。自由字符串。
- **`source_item_id`（str | None）**：原始数据源内部的条目级 ID，用于正向溯源（如果原始记录被删除，此字段可能失效）。
- **`summary_text`（str | None）**：文本摘要，长度建议 ≤ 500 字符。不存储全文，仅用于人类快速理解上下文。

### 3.2 缺失/unknown 的处理

| 场景 | `sentiment_score` | `label` | `confidence` |
|---|---|---|---|
| 数据源返回了完整分数 | -0.75 | "negative" | 0.85 |
| 数据源只返回了标签 | None | "negative" | None |
| 数据源无法判断 | 0.0 | "neutral" | 0.0 |
| 数据源未处理 | None | "unknown" | None |
| 数据源异常/空结果 | None | None | None |

### 3.3 模型/规则可追溯性

- `model_version` 是自由字符串，但建议采用统一格式 `<source>-<type>-<version>`，如 `tushare-news-sentiment-v1`。
- 本阶段不对格式做强校验，后续 Phase 可引入版本号治理。

---

## 4. 注册点与不改动清单

### 4.1 external_fallback_chains

通过 `DataRouter` 构造参数 `external_fallback_chains` 传入（或通过 `UnifiedDataConfig.capability_fallback_overrides` → registry `set_external_fallback_chains`），优先级：constructor → `UnifiedDataConfig.fallback_for(capability)` → registry 注册顺序。Phase 1E 传入空链：

```python
external_fallback_chains = {
    "sentiment.stock_score": [],  # Phase 1E: no real providers
}
```

**不改动**：现有所有 capability 的 fallback 链不变。

### 4.2 STUB_COLUMNS（`providers/_stub_columns.py`）

在 `STUB_COLUMNS` dict 中新增条目：
```python
"sentiment.stock_score": [
    "symbol", "market", "sentiment_score", "label", "confidence",
    "source", "source_item_id", "model_version", "observed_at",
    "as_of_date", "language",
],
```

**不改动**：现有所有 stub 列定义不变。

### 4.3 FreshnessPolicy（`freshness.py`）

在 FreshnessPolicy 的默认 TTL 映射中新增 `sentiment` domain 条目（`get_ttl(domain)` 按 domain 键查找；未知 domain 回退至 `_DEFAULT_TTL=3600`；使用 capability 字符串 `sentiment.stock_score` 作为 key 会落入回退值而非显式配置）：

```python
"sentiment": 3600,  # 1 hour — aligns with intraday sentiment demand
```

**不改动**：现有所有 TTL 值不变。

### 4.4 DataRouter `_TA_CN_NOT_COVERED`（`router.py`）

确认 `"sentiment.stock_score"` 不在 `_TA_CN_CAPABILITY_METHOD_MAP` 中，且不属于 `_TA_CN_NOT_COVERED` 的预填集合时需新增：
```python
_TA_CN_NOT_COVERED: frozenset[str] = frozenset({
    ...
    "sentiment.stock_score",
})
```

**不改动**：现有 `_TA_CN_CAPABILITY_METHOD_MAP` 和已存在的 `_TA_CN_NOT_COVERED` 条目不变。

### 4.5 Provider capabilities 不改动清单

| Provider | `sentiment.stock_score` in capabilities? | 操作 |
|---|---|---|
| TushareProvider | ❌ 不新增 | 保持 13-capability 不变 |
| AKShareProvider | ❌ 不新增 | 保持 7-capability 不变 |
| TA-CN adapter | ❌ 不新增 | 保持 11-capability 不变 |

### 4.6 Capability 常量（如有能力常量模块）

如项目已有 `KLINE_DAILY_CAPABILITY = "market_data.kline_daily"` 模式，在相应常量集合中新增：
```python
SENTIMENT_STOCK_SCORE = "sentiment.stock_score"
```
如无常量模块，Design 阶段裁定是否新增。

---

## 4.bis 持久化契约

**无持久化需求**。Phase 1E 不创建 MongoDB 集合、不写入 CacheManager、不写入 AuditLogger、不写入 QualitySummary。全部数据流为：
- 外部数据：尚未接入，fallback 链为空
- 读取路径：Router 返回 `DataResult.error(provider="error")`
- fixture 测试：mock provider → DataResult.success(data=[list[StockSentimentScore]]) → 消费方收到 mock 数据
- 不落盘，无 TTL/生命周期/隐私分级

---

## 5. ETLV 验证点

| # | 验证点 | 描述 | 验证方式 |
|---|---|---|---|
| V-1 | **时间有效性** | `as_of_date` 格式验证为 `YYYY-MM-DD`；`observed_at` 格式验证为 ISO-8601 | 消费方自行校验 |
| V-2 | **去重** | 相同 `(market, symbol, as_of_date, source)` 视作同源同日重复记录 | 本阶段不作硬去重；后续持久化阶段的 unique key 可基于此组合 |
| V-3 | **标的映射** | `symbol` + `market` 可映射为 `SecurityId` | 消费方在调用 `query()` 时已构造 `SecurityId`，本阶段不额外验证 |
| V-4 | **语言/文本质量** | `summary_text` 长度建议 ≤ 500 字符；超长可截断 | 本阶段不作强校验 |
| V-5 | **来源可追溯性** | `source` + `source_item_id` + `model_version` 联合溯源 | fixture 验证：3 字段均非空 |
| V-6 | **质量标记** | `quality_flags` 为 Phase 2 预留；本阶段 fixture 可设为 `None` | 确认不阻塞写入 |
| V-7 | **失败语义** | 无 provider 可用时返回 `DataResult.error(provider="error")` | Router 测试验证 |

---

## 6. 读路径与写路径边界

| 路径 | Phase 1E 行为 | 后续 Phase 展望 |
|---|---|---|
| **读路径（fixture）** | `Router.query("sentiment", "stock_score", sid)` → 通过 mock provider 返回 `DataResult.success(data=[...])` | Phase 2+ 接入真实 provider 后进入 Step 4 fallback |
| **读路径（无 provider）** | `Router.query(...)` → `DataResult.error(provider="error", source_trace=[...])` | 同左 |
| **写路径（生产）** | **禁止** | Phase 2+ 经 Pascal 授权后通过 `data-pipeline` 的 ETL 写入 |
| **写路径（测试）** | fixture 内存构造，MockProvider 返回 `DataResult.success(data=fixtures)` | Design 阶段可决定 fixture 存储位置 |

---

## 7. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | `StockSentimentScore` domain object 定义完整，含全部 14 个字段（类型/默认值/`from_dict`） | Python import 成功；`from_dict({"symbol": "600519", "market": "CN"})` 返回有效对象 |
| A-002 | `sentiment.stock_score` 在 `external_fallback_chains` 中注册为空链 | 断言 `registry.get_external_fallback_chain("sentiment.stock_score") == []` |
| A-003 | `sentiment.stock_score` 在 `STUB_COLUMNS` 中注册 stub 列 | `stub_dataframe_for("sentiment.stock_score").columns` 含预期列 |
| A-004 | `sentiment.stock_score` 在 `_TA_CN_NOT_COVERED` 中 | `"sentiment.stock_score" in Router._TA_CN_NOT_COVERED` |
| A-005 | 现有 48 项（Phase 1D 基线）测试 Regression PASS | `pytest skills/data/unified_data/tests -q` exit 0 |
| A-006 | fixture 测试：mock provider 注册后 `Router.query("sentiment", "stock_score", sid)` 返回 `DataResult.success` | Python 断言：`result.succeeded == True`；`result.data` 为 `list[StockSentimentScore]` |
| A-007 | fixture 测试：无 provider 注册时返回 `DataResult.error(provider="error")` | Python 断言：`result.succeeded == False`；`result.provider == "error"` |
| A-008 | `git diff --check` exit 0 | 终端命令 |
| A-009 | `git diff --name-status` 仅含目标文件，不含模板/SKILL/README/现有代码修改 | 终端命令 |
| A-010 | 文档明确声明「情绪分数不构成交易决策」 | 【T2+ 后置验证】grep 搜索 RFC/SPEC（不含 Design，因 DESIGN 尚不存在）含此声明 |

---

## 8. 测试要求

### 8.1 单元测试

| 测试 | 覆盖内容 | 预期用例数 | 是否需要网络 |
|---|---|---|---|
| `test_stock_sentiment_score` | `StockSentimentScore` 构造、`from_dict()`、字段默认值、边界值（score=-1.0/0.0/1.0/None） | 8 | 否 |
| `test_sentiment_capability` | `sentiment.stock_score` 注册、stub columns、fallback 链 | 4 | 否 |
| `test_sentiment_router` | MockSentimentProvider 注册后查询成功 / 无 provider 时返回 error | 4 | 否 |

### 8.2 Fixture

| Fixture 文件 | 内容 |
|---|---|
| `skills/data/unified_data/tests/fixtures/sentiment_fixtures.py` | 至少 2 条 `StockSentimentScore` mock 记录：正面（score=0.75, label="positive", confidence=0.85）和负面（score=-0.60, label="negative", confidence=0.72） |
| `skills/data/unified_data/tests/fixtures/sentiment_fixtures.py` | 额外 1 条未知情绪记录（score=None, label="unknown", confidence=None） |

### 8.3 回归测试

```bash
# Phase 1D 基线 — 跑前确认
.venv/bin/python -m pytest skills/data/unified_data/tests -q --tb=short  # exit 0

# Phase 1E 新增测试
.venv/bin/python -m pytest skills/data/unified_data/tests/test_sentiment_*.py -q --tb=short
```

### 8.4 不可自动化验证项

- RFC/SPEC/Design 中关于「情绪分数不是交易信号」的声明：人工审核。

---

## 9. 实现约束

### 9.1 禁止事项

- ❌ 任何形式的真实网络请求（HTTP、API、MCP）
- ❌ MongoDB 读取或写入（含 CacheManager、AuditLogger、QualitySummary）
- ❌ 读取 `.env` 或任何凭据文件
- ❌ 修改 `NewsItem`（`models/domain/news.py`）中已有的 `sentiment` 字段
- ❌ 修改 `UnifiedDataClient` 的方法签名（`client.py`）
- ❌ 修改 `DataRouter` 的 `query()` 逻辑（`router.py`）
- ❌ 修改 `DataResult` 或 `Capability` 的签名（`models/__init__.py`）

### 9.2 依赖限制

- 不新增任何第三方 Python 包依赖
- MockSentimentProvider 继承 `DataProvider` ABC，注册到 `ProviderRegistry`，不走 HTTP 客户端

### 9.3 性能/安全/风控约束

- 情绪分数在 API docstring 和注释中标注「仅供参考，不构成投资建议」
- fixture 数据不包含真实股票数据，仅用于契约验证

---

## 10. 开放问题

- [ ] OQ-1：`sentiment` domain TTL 基准值 3600s 是否合适？本阶段不实现刷新，仅注册默认值。
- [ ] OQ-2：`sentiment_score` 的取值区间是否需要严格 [-1.0, 1.0] 约束？当前为宽松 `float | None`。
- [ ] OQ-3：是否需在 Phase 1E 就引入 `quality_score`（Phase 2）的预留位？当前通过 `quality_flags: dict` 占位。
- [ ] OQ-4：`as_of_date` 与 `observed_at` 的区分是否满足消费方需求？Review 阶段确认。

---

## 11. 不改动清单（Confirm No Changes）

以下文件/组件在本 Phase **不得被修改**。任何触及这些文件的 diff 将触发验收 FAIL：

| 文件/组件 | 理由 |
|---|---|
| `skills/data/unified_data/models/domain/news.py` | `NewsItem.sentiment` 保持向后兼容 |
| `skills/data/unified_data/models/domain/__init__.py` | 现有 8 个导出符号不变 |
| `skills/data/unified_data/client.py` | 不新增方法、不修改签名 |
| `skills/data/unified_data/router.py` `query()` 方法逻辑 | Router internal-first 编排不变 |
| `skills/data/unified_data/models/__init__.py` 中 `DataResult` / `Capability` / `SecurityId` | Phase 0 公共契约不变 |
| `skills/data/unified_data/providers/tushare.py` 的 `capabilities` | 不声明 `sentiment.stock_score` |
| `skills/data/unified_data/providers/akshare.py` 的 `capabilities` | 同上 |
| 任何 Template / README / SKILL | 全局规约源不变 |
| 任何非 `docs/rfc/03_data/`、`docs/spec/03_data/`、`docs/design/03_data/`、`skills/data/unified_data/models/domain/`、`skills/data/unified_data/tests/` 的文件 | 范围外文件不触碰 |

---

## 12. 参考资料

- RFC-03-013（Phase 1E Sentiment Minimal Slice）—— 本 SPEC 的来源文档
- SPEC-03-007（Unified Data Layer 契约基线）
- SPEC-03-008（Phase 1B-A 查询平面）
- `skills/data/unified_data/models/domain/news.py`（NewsItem.sentiment —— 保持向后兼容）
- `skills/data/unified_data/freshness.py`（FreshnessPolicy TTL 注册点）
- `skills/data/unified_data/providers/_stub_columns.py`（STUB_COLUMNS 注册点）
- `skills/data/unified_data/router.py`（external_fallback_chains 通过构造参数传入；DataRouter._external_chains 为最终来源）
- `skills/data/unified_data/router.py`（_TA_CN_NOT_COVERED 注册点）
