# RFC-08-002：Argus 信号接口标准
## 元数据（Metadata）
| 项 | 值|
|---|---|
| 状态 | 已采纳（Accepted） |
| 作者 | YQuant |
| 创建日期 | 2026-05-18 |
| 最后更新 | 2026-06-07 |
| 版本号 | V0.6 |
| 所属模块 | 08_research（投研分析） |
| 依赖RFC | RFC-00-001-yquant-investment-global-architecture, RFC-08-001-argus-integration |
| 替代RFC | 无 |
| 适配AI工具 | OpenClaw、Claude Code |
| 标签 | #argus #接口 #信号 #portfolio #标准化 |

### 版本历史（Changelog）
| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.6 | 2026-06-07 | 补充 dry_run 与执行路径共享 `zone_rules_template.yaml` / `ZoneRuleEngine` 阈值逻辑，更新 Portfolio 状态机迁移接口说明 | YQuant |
| V0.5 | 2026-06-06 | 补充 Signal ID 幂等性设计，明确 signal_id 由业务键确定性生成 | YQuant |
| V0.4 | 2026-06-06 | Phase 3：补充 stock_pool_record 派生字段、ZoneRuleEngine 分类结果、Darwin override 语义和 bayesian_score 前置约束 | YQuant |
| V0.3 | 2026-05-19 | 补充 ArgusPortfolioSubscriber、Portfolio ingestion endpoint、MongoDB-only 数据流与 zone 映射 | YQuant |
| V0.2 | 2026-05-18 | 状态更新：Draft → Accepted；集合名称更新为 tradingagents.08_research_argus_signal | YQuant |
| V0.1 | 2026-05-18 | 初始创建，定义 Argus 信号接口标准 | YQuant |

## 1. 执行摘要
本文档定义 Argus 系统输出的机构资金行为信号（argus_signal）的标准格式、以及与 portfolio/strategy/trading 模块的消费接口契约。本 RFC 是 RFC-08-001 的接口层面补充，专注于信号格式、订阅机制和消费规范。

## 2. 背景与动机
### 2.1 为什么要单独定义接口标准
- Argus 输出的信号需要被 portfolio、strategy、trading 等多个模块消费
- 信号格式必须全局统一，才能实现模块解耦
- 置信度阈值、降级策略需要显式声明，避免误用

### 2.2 与 RFC-08-001 的关系
- RFC-08-001：定义 Argus 如何纳入 YQuant 体系、数据源选择、模块定位
- **RFC-08-002**：定义 Argus 输出信号的格式和消费接口契约
- 两者共同构成 Argus 与其他模块的完整接口规范

## 3. argus_signal 信号格式

### 3.1 标准 JSON Schema
```json
{
  "signal_id": "argus:5f2c9b7e1a4d8c0b3e91",
  "source": "argus",
  "version": "1.0.0",
  "product_code": "SM001",
  "product_name": "JS-001",
  "signal_type": "BUY | SELL | HOLD",
  "confidence": 0.85,
  "direction": "LONG | SHORT | FLAT",
  "target_stocks": [
    {
      "wind_code": "603737.SH",
      "stock_name": "三棵树",
      "action": "BUY | SELL | HOLD",
      "holding_ratio_change": 0.023,
      "market_value_change": 520000.00
    }
  ],
  "reason": "机构资金大幅流入，持仓比例增加2.3%，目标股票进入CONVICTION池",
  "generated_at": "2026-03-11T08:00:00+08:00",
  "valid_until": "2026-03-12",
  "metadata": {
    "credibility_score": 0.85,
    "crowding_level": "LOW | MEDIUM | HIGH",
    "time_horizon": "FAST | MEDIUM | SLOW",
    "pool_zone": "SCAN | WATCH | CANDIDATE | CONVICTION",
    "contributing_products_count": 3,
    "darwin_moment": false,
    "consensus_direction": "BULLISH | BEARISH | NEUTRAL"
  }
}
```

### 3.2 字段定义

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| signal_id | String | 是 | 信号唯一标识，格式为 `argus:{sha256_hash}` 前 20 字符 |
| source | String | 是 | 信号来源，固定为 "argus" |
| version | String | 是 | 信号格式版本，如 "1.0.0" |
| product_code | String | 是 | 产品代码 |
| product_name | String | 是 | 产品名称 |
| signal_type | Enum | 是 | 信号类型：BUY/SELL/HOLD |
| confidence | Float | 是 | 置信度，0.0-1.0 |
| direction | Enum | 是 | 方向：LONG/SHORT/FLAT |
| target_stocks | Array | 是 | 目标股票列表 |
| reason | String | 是 | 信号生成原因简述 |
| generated_at | DateTime | 是 | 信号生成时间（ISO 8601） |
| valid_until | Date | 是 | 信号有效期（当日有效） |
| metadata | Object | 是 | 扩展元数据 |

### 3.3 metadata 字段定义

| 字段 | 类型 | 说明 |
|---|---|---|
| credibility_score | Float | 贝叶斯信誉评分，0.0-1.0 |
| crowding_level | Enum | 拥挤度：LOW/MEDIUM/HIGH |
| time_horizon | Enum | 时间视野：FAST/MEDIUM/SLOW |
| pool_zone | Enum | 所属股票池区域 |
| contributing_products_count | Integer | 贡献信号的产品数量 |
| darwin_moment | Boolean | 是否命中产品级或行业级 Darwin 事件；仅作为 zone floor 正向证据，不直接强制 CONVICTION |
| darwin_confidence | Float | Darwin 事件置信度，缺失时为 null |
| consensus_direction | Enum | 共识方向 |

### 3.4 Signal ID 生成策略（幂等性设计）

`signal_id` 使用确定性生成策略，不再使用随机 UUID。生成原则如下：

- **设计原则**：`signal_id` 基于业务键 `date, product_code, wind_code, signal_type` 的确定性 hash。
- **格式**：`argus:{sha256_hash}` 前 20 字符。
- **目的**：支持 MongoDB upsert 语义，同一交易日、同一产品、同一股票、同一信号类型重跑不会重复插入，保证日度处理幂等。
- **对比**：旧方案使用随机 UUID，每次重跑都会产生新记录，导致 `signal_id` 去重只能事后按最新时间戳裁剪。

标准实现等价于：

```python
key = f"{date}:{product_code}:{wind_code}:{signal_type}"
signal_id = f"argus:{sha256(key.encode()).hexdigest()[:20]}"
```

### 3.5 stock_pool_record 派生字段

Argus 写入 `08_research_argus_signal_pool` 前，会把 `argus_signal` 聚合为单股单日记录。Phase 3 后该记录是 zone 分类的标准输入：

| 字段 | 类型 | 说明 |
|---|---|---|
| date | Date | 处理日期 |
| wind_code | String | 股票 Wind 代码 |
| stock_name | String | 股票名称 |
| confidence | Float | 原始信号置信度聚合值，保留用于兼容和审计 |
| bayesian_score | Float | BayesianScorer 输出的主评分；必须在 zone 分类前存在 |
| contributing_products | Array[String] | 贡献信号产品列表 |
| contributing_products_count | Integer | 贡献产品数 |
| consensus_direction | Enum | BUY/SELL/HOLD 或 BULLISH/BEARISH/NEUTRAL 的归一化方向 |
| consensus_confidence | Float | 单股共识置信度 |
| crowding_score | Float | 拥挤度分数 |
| crowding_level | Enum | LOW/MEDIUM/HIGH/DANGER |
| darwin_moment | Boolean | 产品级或行业级 Darwin 标记 |
| darwin_confidence | Float/null | 行业级 Darwin 事件置信度 |
| darwin_event_id | String/null | Darwin 事件引用 |
| pool_zone | Enum | ZoneRuleEngine 输出的最终 zone |
| zone_decision | Object | `rule_name/reason/metrics/thresholds`，用于审计分类来源 |

接口约束：`pool_zone` 不再由 `confidence` 硬编码阈值直接决定，而由 `ZoneRuleEngine.classify_initial_zone()` 基于 `bayesian_score`、产品数、共识、拥挤度和 Darwin override 统一生成。

## 4. Portfolio 模块消费接口

### 4.1 数据订阅机制
```python
# 订阅 Argus 信号
class ArgusSignalSubscriber:
    """Portfolio 模块订阅 Argus 信号的接口"""
    
    def __init__(self, signal_dir: str = "logs/research/"):
        self.signal_dir = signal_dir
    
    def get_latest_signals(
        self, 
        min_confidence: float = 0.7,
        pool_zone: Optional[str] = None
    ) -> List[Dict]:
        """
        获取最新信号
        
        Args:
            min_confidence: 最低置信度阈值，默认0.7
            pool_zone: 可选，按股票池区域过滤
        
        Returns:
            List[Dict]: 符合条件的信号列表
        """
        pass
    
    def get_stock_signals(
        self, 
        wind_code: str,
        days: int = 7
    ) -> List[Dict]:
        """
        获取特定股票最近N天的信号
        
        Args:
            wind_code: Wind代码
            days: 天数，默认7天
        
        Returns:
            List[Dict]: 信号列表
        """
        pass
```

Phase 2 后 Portfolio 侧使用 `ArgusPortfolioSubscriber` 作为 Argus 项目内的对接层。该接口直接读取
MongoDB `tradingagents.08_research_argus_signal`，并只输出 Portfolio ingestion 所需 payload，
不直接写入 `05_portfolio_stock_pool`。

```python
class ArgusPortfolioSubscriber:
    """Argus 信号到 Portfolio 股票池 ingestion payload 的订阅接口。"""

    def get_latest_signals(
        self,
        trade_date: str,
        min_confidence: float = 0.7,
        pool_zone: str | None = None,
    ) -> list[dict]:
        """按交易日、最低置信度和可选股票池 zone 获取最新 Argus 信号。"""

    def to_portfolio_ingest_payload(
        self,
        signals: list[dict],
        mode: str = "upsert_scan_only",
    ) -> list[dict]:
        """将 Argus signal 转换为 StockPoolIngestionService.ingest_signals payload。"""

    def get_stock_signals(
        self,
        wind_code: str,
        days: int = 7,
        min_confidence: float = 0.7,
    ) -> list[dict]:
        """获取某只股票最近 N 天内的 Argus 信号。"""
```

### 4.2 置信度阈值规则

| 置信度 | 处理规则 |
|--------|----------|
| ≥ 0.8 | 高置信度信号，直接纳入组合权重计算 |
| 0.6 - 0.8 | 中置信度信号，降权纳入（×0.5） |
| 0.4 - 0.6 | 低置信度信号，仅供观察，不纳入组合 |
| < 0.4 | 忽略，不处理 |

### 4.3 降级策略

| 异常场景 | 降级处理 |
|----------|----------|
| argus_signal 文件不存在 | 返回空列表，日志 WARNING |
| signal_id 重复 | 取最新时间戳，忽略旧信号 |
| 字段缺失 | 拒绝该信号，日志 ERROR |
| 置信度异常（非0-1） | 拒绝该信号，日志 ERROR |

## 5. 与 portfolio 模块的数据交换

### 5.1 MongoDB-only 交换格式
- **数据库**：`tradingagents`
- **Argus 信号集合**：`08_research_argus_signal`
- **Portfolio 股票池集合**：`05_portfolio_stock_pool`
- **频率**：日度 T+1（每日 08:00 前生成）
- **废弃项**：SQLite 与 JSONL 文件交换均不再作为标准接口；历史描述只保留为迁移参考。

### 5.2 Portfolio transition endpoint
Portfolio 应暴露 `POST /ingest-signals` 或等价应用层入口，通过依赖注入获取
`StockPoolTransitionPipeline`。该 pipeline 使用 `StockPoolIngestionService` 做持久化边界，并调用
`ZoneRuleEngine.classify_transition()` 生成 entry / promote / demote / exit / retain 决策：

```python
class StockPoolTransitionPipeline:
    def run_incremental_transition(
        self,
        current_signals: list[dict],
        previous_signals: list[dict],
        actor: str = "system:argus",
        dry_run: bool = False,
    ) -> dict:
        """按 YAML-backed ZoneRuleEngine 执行 Portfolio stock_pool 增量迁移。"""
```

推荐请求体：

```json
{
  "source": "argus",
  "actor": "system:argus",
  "dry_run": false,
  "previous_signals": [],
  "signals": []
}
```

执行语义：

| 字段 / 模式 | 行为 |
|---|---|
| `dry_run=false` | 执行状态机迁移并写入 `05_portfolio_stock_pool` 与审计集合 |
| `dry_run=true` | 只返回拟处理结果，不写入 MongoDB；预览使用与执行完全相同的 `zone_rules_template.yaml` 和 `ZoneRuleEngine.classify_transition()` 逻辑 |
| `previous_signals` | 用于识别保留、升降级与 `missing_from_current_signal_pool` exit；节假日缺口应使用最近一次 prior signal_pool |

接口约束：Portfolio stock_pool zone 不由 Argus 当日 `pool_zone` 或 ingestion payload 直接覆盖。`pool_zone` 是状态机输出，必须通过 YAML 中的 `portfolio_transitions.promote_rules`、`demote_rules`、`exit_rules` 与 hysteresis retention 计算。

### 5.3 Zone 映射表

| Argus zone | Portfolio zone | 说明 |
|---|---|---|
| SCAN | SCAN | 初筛观察 |
| WATCH | WATCH | 重点跟踪 |
| CANDIDATE | CANDIDATE | 候选研究 |
| CONVICTION | CONVICTION | 高确信度 |
| focus | CONVICTION | 旧 RFC 残留命名，统一迁移为 CONVICTION |

### 5.3.1 Darwin override 语义

Darwin override 是 floor-only 规则：

- 命中 `darwin_moment=true` 且满足 YAML 中 `darwin_override.score_guard` 时，最低提升到 `CANDIDATE`。
- Darwin 不直接强制 `CONVICTION`；进入 `CONVICTION` 仍需常规规则满足 `bayesian_score`、产品数、共识和拥挤度条件。
- 若 `crowding_level` 超过目标 zone 允许上限，ZoneRuleEngine 会按 YAML 规则限制目标 zone。
- 旧 `PoolManager.classify_stock(..., confidence, darwin_moment=True)` 是兼容 API；新 pipeline 应传入完整 `stock_pool_record`。

### 5.4 标准数据流

```text
Argus signal (MongoDB 08_research_argus_signal)
  -> ArgusPortfolioSubscriber.get_latest_signals(trade_date, min_confidence)
  -> ArgusPortfolioSubscriber.to_portfolio_ingest_payload(signals, mode)
  -> StockPoolTransitionPipeline.run_incremental_transition(current_signals, previous_signals, dry_run)
  -> ZoneRuleEngine.classify_transition(metrics, current_zone)
  -> StockPoolRepository.create()/update_fields() when dry_run=false
  -> 05_portfolio_stock_pool
```

## 6. 验收标准
- [ ] argus_signal JSON 格式符合 Schema
- [ ] ArgusPortfolioSubscriber 接口可通过单元测试
- [ ] StockPoolIngestionService 接口可通过单元测试
- [ ] 置信度阈值规则正确执行
- [ ] 降级策略正确处理异常场景
- [ ] 与 portfolio 模块联调通过

## 7. 开放问题
| 问题 | 状态 | 说明 |
|---|---|---|
| 是否需要实时信号推送 | 待讨论 | 当前设计为日度 T+1 MongoDB ingestion |
| 信号有效期精确到小时还是日 | 待定 | 当前设计为当日有效 |
