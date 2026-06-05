# daily_processor zone 分类改造详细设计

## 1. daily_processor zone 分类现状

### 1.1 代码位置

本次分析的实际代码路径为：

- `skills/research/argus/cli/daily_processor.py`
- `skills/research/argus/core/pool_manager.py`
- `skills/research/argus/config/zone_rules_template.yaml`

请求中给出的 `skills/research/argus/skills/research/argus/...` 路径在当前工作区不存在。

### 1.2 zone 分类相关代码

#### daily_processor.py

1. `process_date()`：`skills/research/argus/cli/daily_processor.py:40`
   - `skills/research/argus/cli/daily_processor.py:59` 创建 `PoolManager()`。
   - `skills/research/argus/cli/daily_processor.py:164-175` 计算 `consensus`、`crowding`，然后调用 `_build_stock_pool_records(...)`。
   - `skills/research/argus/cli/daily_processor.py:176-179` 在 zone 分类后再执行 `BayesianScorer.score_signal_pool_records(...)`。
   - `skills/research/argus/cli/daily_processor.py:182-189` 基于 `record['pool_zone']` 汇总 `pool_summary`。
   - `skills/research/argus/cli/daily_processor.py:225-240` 将 `stock_pool_records` 写入 Argus signal pool，并同步到 Portfolio stock pool。

2. `_build_stock_pool_records()`：`skills/research/argus/cli/daily_processor.py:673`
   - `skills/research/argus/cli/daily_processor.py:683` 将当日 Darwin 事件按行业 `sw1_code` 建索引。
   - `skills/research/argus/cli/daily_processor.py:684-692` 按股票聚合 signals，收集 `stock_signals` 和 `stock_names`。
   - `skills/research/argus/cli/daily_processor.py:696` 计算 `products = sorted({signal.product_code})`。
   - `skills/research/argus/cli/daily_processor.py:697` 计算 `confidence = max(signal['confidence'])`。
   - `skills/research/argus/cli/daily_processor.py:698-703` 计算 `darwin_moment`：单条 signal metadata 有 Darwin，或股票所属行业命中当日 sector Darwin event。
   - `skills/research/argus/cli/daily_processor.py:704-710` 调用 `pool_manager.classify_stock(wind_code, stock_name, confidence, products, darwin_moment)` 得到 `pool_zone`。
   - `skills/research/argus/cli/daily_processor.py:713-732` 生成 stock pool record，将 `pool_zone`、`confidence`、`contributing_products_count`、`consensus_confidence`、`crowding_level`、`darwin_moment` 写入记录。

3. `_annotate_signals()`：`skills/research/argus/cli/daily_processor.py:736`
   - `skills/research/argus/cli/daily_processor.py:742` 建立 `pool_by_stock`。
   - `skills/research/argus/cli/daily_processor.py:750-756` 将 `pool_zone` 和 `contributing_products_count` 回填到 signal metadata。
   - 该函数不做分类，只传播 `_build_stock_pool_records()` 的分类结果。

#### pool_manager.py

1. `PoolManager.ZONES`：`skills/research/argus/core/pool_manager.py:22`
   - 当前固定为 `['SCAN', 'WATCH', 'CANDIDATE', 'CONVICTION']`。

2. `PoolManager.__init__()`：`skills/research/argus/core/pool_manager.py:24`
   - 当前读取 `ARGUS_CONFIG.get('pool_zones', {})`。
   - `ARGUS_CONFIG` 来自 `skills/research/argus/config/config.py:10-11`，只加载 `argus_config.yaml`。
   - 当前没有读取 `zone_rules_template.yaml`。

3. `PoolManager.classify_stock()`：`skills/research/argus/core/pool_manager.py:27`
   - 这是 Argus 初始 zone 分类的核心函数。
   - 输入：`wind_code`、`stock_name`、`confidence`、`contributing_products`、`darwin_moment`。
   - 输出：`SCAN` / `WATCH` / `CANDIDATE` / `CONVICTION`。
   - 当前判断逻辑：
     - `skills/research/argus/core/pool_manager.py:47-51`：若 `darwin_moment=True`，`base_zone='CANDIDATE'`，否则 `base_zone='SCAN'`。
     - `skills/research/argus/core/pool_manager.py:54-57`：读取 `conviction/candidate/watch/scan` 配置；其中 `scan_config` 当前未实际使用。
     - `skills/research/argus/core/pool_manager.py:60-62`：`confidence >= conviction.min_confidence(默认 0.75)` 且 `产品数 >= conviction.min_contributing_products(默认 3)`，返回 `CONVICTION`。
     - `skills/research/argus/core/pool_manager.py:65-67`：`confidence >= candidate.min_confidence(默认 0.60)` 且 `产品数 >= candidate.min_contributing_products(默认 2)`，返回 `CANDIDATE`。
     - `skills/research/argus/core/pool_manager.py:69-70`：若 `darwin_moment=True` 且未命中更高规则，返回 `CANDIDATE`，即 Darwin 保底 CANDIDATE。
     - `skills/research/argus/core/pool_manager.py:73-74`：`confidence >= watch.min_confidence(默认 0.45)`，返回 `WATCH`。
     - `skills/research/argus/core/pool_manager.py:77`：否则返回 `SCAN`。

4. `PoolManager.update_pool()`：`skills/research/argus/core/pool_manager.py:79`
   - 对每个 signal target 调用 `classify_stock()`。
   - 当前 daily_processor 主流程不使用它生成 `stock_pool_records`，但它仍是分类逻辑的另一个入口，应保持兼容。

### 1.3 当前流程图（文字版）

```text
process_date(target_date)
  -> 读取 position/trade/product profile/industry/index 数据
  -> 逐产品生成 signal，初始 signal.pool_zone='SCAN'
  -> DarwinDetector.detect_for_date(...)
  -> ConsensusEngine.calculate_consensus(all_signals)
  -> CrowdingAnalyzer.analyze(...)
  -> _build_stock_pool_records(...)
       -> 按 wind_code 聚合 signals
       -> products = 贡献产品集合
       -> confidence = 该股票相关 signals 的最大 confidence
       -> darwin_moment = signal Darwin OR 同行业当日 Darwin event
       -> PoolManager.classify_stock(confidence, products, darwin_moment)
            -> 命中 CONVICTION 阈值：CONVICTION
            -> 否则命中 CANDIDATE 阈值：CANDIDATE
            -> 否则 Darwin：CANDIDATE
            -> 否则命中 WATCH 阈值：WATCH
            -> 否则：SCAN
       -> 组装 stock_pool_record.pool_zone
  -> BayesianScorer 追加 bayesian_score，不改变 pool_zone
  -> _annotate_signals 回填 metadata.pool_zone
  -> 写入 08_research_argus_signal_pool
  -> Portfolio stock_pool incremental sync
```

## 2. 改造后详细设计

### 2.1 设计目标

改造目标是让 `daily_processor.py` 的股票 zone 初始分类不再依赖 `PoolManager.classify_stock()` 中的硬编码 fallback 阈值，而是读取 `skills/research/argus/config/zone_rules_template.yaml` 的统一配置：

- `zones.order` 和 `zones.default_zone` 定义合法 zone 与默认 zone。
- `score_policy.argus_initial` 定义 Argus 初始分类使用的 score 字段优先级。
- `metric_aliases` 定义输入 record 到标准 metric 的字段映射。
- `argus_signal_pool.entry_rules` 定义 SCAN/WATCH/CANDIDATE/CONVICTION 的阈值。
- `argus_signal_pool.evaluation_order` 定义规则评估顺序。
- `argus_signal_pool.darwin_override` 定义 Darwin 保底 zone。

### 2.2 配置读取方式

当前 `skills/research/argus/config/config.py` 只加载 `argus_config.yaml`。建议新增专用 loader，而不是把 `zone_rules_template.yaml` 直接合并进 `ARGUS_CONFIG`：

- 新增文件：`skills/research/argus/config/zone_rules.py`
- Loader：`load_zone_rules_config(path: Optional[Path] = None) -> Dict[str, Any]`
- 默认路径：`Path(__file__).parent / 'zone_rules_template.yaml'`
- Parser：继续使用项目已有依赖 `yaml.safe_load`。
- 校验：加载后做轻量 schema validation，至少检查以下字段存在：
  - `version`
  - `zones.order`
  - `zones.default_zone`
  - `score_policy`
  - `argus_signal_pool.score_policy`
  - `argus_signal_pool.entry_rules`
  - `argus_signal_pool.evaluation_order`
  - `argus_signal_pool.darwin_override`

建议导出：

```python
ZONE_RULES_CONFIG = load_zone_rules_config()
```

并在 `skills/research/argus/config/__init__.py` 中增加：

```python
from .zone_rules import ZONE_RULES_CONFIG, load_zone_rules_config
```

这样 `ARGUS_CONFIG` 保持原职责，zone rule YAML 成为独立配置源，后续也便于 Portfolio 侧复用同一 loader。

### 2.3 核心运行对象

建议新增运行时规则引擎：

- 新增文件：`skills/research/argus/core/zone_rule_engine.py`
- 参考已有文档草案：`skills/research/argus/docs/zone_rule_engine_interfaces.py`
- 核心类：
  - `ZoneRuleEngine`
  - `ZoneMetrics`
  - `ZoneDecision`

最小可行实现只覆盖 Argus 初始分类：

```python
@dataclass(frozen=True)
class ZoneMetrics:
    confidence: float = 0.0
    bayesian_score: float = 0.0
    contributing_products_count: int = 0
    consensus_confidence: float = 0.0
    crowding_level: str = "LOW"
    darwin_moment: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ZoneDecision:
    target_zone: str
    rule_name: str
    reason: str
    metrics: Dict[str, Any]
    thresholds: Dict[str, Any]
```

### 2.4 改造后的完整流程

#### Step 1：加载 YAML 配置

输入：

- `skills/research/argus/config/zone_rules_template.yaml`

处理：

- `yaml.safe_load()` 解析 YAML。
- 校验必需字段。
- 建立 zone rank：`SCAN=0, WATCH=1, CANDIDATE=2, CONVICTION=3`。

输出：

- `ZONE_RULES_CONFIG: Dict[str, Any]`
- `ZoneRuleEngine(config=ZONE_RULES_CONFIG)`

#### Step 2：daily_processor 创建 PoolManager

输入：

- `PoolManager()` 默认参数。

处理：

- `PoolManager.__init__()` 创建 `ZoneRuleEngine.from_config(ZONE_RULES_CONFIG)`。
- 保留旧 `ARGUS_CONFIG.pool_zones` 作为可选 fallback，仅用于 YAML 缺失或测试显式传入 legacy config。

输出：

- 带 `zone_rule_engine` 的 `PoolManager`。

#### Step 3：daily_processor 聚合股票分类输入

位置：

- `_build_stock_pool_records()`。

输入：

- `signals`
- `consensus`
- `crowding`
- `wind_to_sw1`
- `darwin_events`

处理：

- `products = sorted({signal.product_code})`
- `confidence = max(signal.confidence)`
- `contributing_products_count = len(products)`
- `consensus_confidence = consensus[wind_code].confidence`，缺省 0
- `crowding_level = crowding[wind_code].crowding_level`，缺省 `LOW`
- `darwin_moment = any(signal.metadata.darwin_moment) or sector_darwin_event is not None`

输出：

- 传入 `PoolManager.classify_stock()` 的最小参数；或更推荐传入标准化 record 给 `ZoneRuleEngine.classify_initial_zone()`。

#### Step 4：抽取 score

输入：

- 标准化 metrics 或 stock record。
- YAML 中的 `argus_signal_pool.score_policy: argus_initial`。
- YAML 中的 `score_policy.argus_initial`：
  - `primary: confidence`
  - `fallback: [bayesian_score, score]`
  - `missing_default: 0.0`

处理：

- 优先读取 `confidence`。
- 若缺失或为 `None`，按 fallback 读取 `bayesian_score`、`score`。
- 都缺失时使用 `0.0`。

输出：

- `score: float`

当前 Phase 1 应使用 `confidence`，与既有逻辑一致。注意 daily_processor 当前在分类后才计算 `bayesian_score`，因此不能在 Phase 1 改成 bayesian，否则会改变数据流和分类结果。

#### Step 5：按 evaluation_order 评估 entry_rules

输入：

- `score`
- `contributing_products_count`
- `darwin_moment`
- `argus_signal_pool.entry_rules`
- `argus_signal_pool.evaluation_order`

处理：

按 YAML 当前顺序：

1. `conviction`
   - `score >= 0.75`
   - `contributing_products_count >= 3`
   - 命中则 `target_zone=CONVICTION`
2. `candidate`
   - `score >= 0.60`
   - `contributing_products_count >= 2`
   - 命中则 `target_zone=CANDIDATE`
3. Darwin override
   - 如果 `darwin_override.enabled=True` 且 `darwin_moment=True`
   - 若当前尚未命中高于或等于 `darwin_override.min_zone` 的规则，则保底 `CANDIDATE`
   - 该 override 放在 candidate 后、watch 前，才能保持现有逻辑：Darwin 低分单产品返回 CANDIDATE，而不是 WATCH/SCAN。
4. `watch`
   - `score >= 0.45`
   - `min_contributing_products: null` 表示不检查产品数。
   - 命中则 `target_zone=WATCH`
5. `scan`
   - `condition: otherwise`
   - 返回默认 `SCAN`

输出：

- `ZoneDecision(target_zone, rule_name, reason, metrics, thresholds)`
- `PoolManager.classify_stock()` 对外仍返回 `decision.target_zone`。

### 2.5 改造后流程图（文字版）

```text
process_date(target_date)
  -> PoolManager()
       -> ZoneRuleEngine.from_yaml(zone_rules_template.yaml)
       -> validate zones / score_policy / entry_rules / evaluation_order
  -> 生成 all_signals / darwin_events / consensus / crowding
  -> _build_stock_pool_records(...)
       -> 聚合每只股票的 raw metrics
       -> PoolManager.classify_stock(...)
            -> ZoneRuleEngine.build_metrics(...)
            -> resolve score by score_policy.argus_initial
            -> for rule_name in evaluation_order:
                 conviction: score >= 0.75 and product_count >= 3 -> CONVICTION
                 candidate: score >= 0.60 and product_count >= 2 -> CANDIDATE
                 before watch: if darwin_moment -> min_zone CANDIDATE
                 watch: score >= 0.45 -> WATCH
                 scan: otherwise -> SCAN
            -> return ZoneDecision.target_zone
       -> 写入 stock_pool_record.pool_zone
  -> BayesianScorer 只追加 bayesian_score
  -> _annotate_signals 传播 pool_zone
  -> 写 Mongo / JSON / Portfolio sync
```

### 2.6 伪代码实现

```python
def load_zone_rules_config(path: Optional[Path] = None) -> Dict[str, Any]:
    config_path = path or Path(__file__).parent / "zone_rules_template.yaml"
    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    validate_zone_rules_config(config)
    return config
```

```python
class ZoneRuleEngine:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.zone_order = config["zones"]["order"]
        self.default_zone = config["zones"].get("default_zone", "SCAN")
        self.zone_rank = {zone: index for index, zone in enumerate(self.zone_order)}
        self.argus_config = config["argus_signal_pool"]

    def classify_initial_zone(self, metrics: ZoneMetrics) -> ZoneDecision:
        score = self._resolve_score(metrics, self.argus_config["score_policy"])
        rules = self.argus_config["entry_rules"]

        for rule_name in self.argus_config["evaluation_order"]:
            if rule_name == "scan":
                continue

            rule = rules[rule_name]
            if self._entry_rule_passes(rule, score, metrics):
                return self._decision(rule_name, rule["target_zone"], metrics, rule)

            if rule_name == "candidate":
                darwin_decision = self._darwin_override(score, metrics)
                if darwin_decision is not None:
                    return darwin_decision

        scan_rule = rules.get("scan", {"target_zone": self.default_zone})
        return self._decision("scan", scan_rule["target_zone"], metrics, scan_rule)

    def _entry_rule_passes(self, rule: Dict[str, Any], score: float, metrics: ZoneMetrics) -> bool:
        min_score = rule.get("min_score")
        if min_score is not None and score < float(min_score):
            return False

        min_products = rule.get("min_contributing_products")
        if min_products is not None and metrics.contributing_products_count < int(min_products):
            return False

        return True

    def _darwin_override(self, score: float, metrics: ZoneMetrics) -> Optional[ZoneDecision]:
        override = self.argus_config.get("darwin_override", {})
        if not override.get("enabled") or not metrics.darwin_moment:
            return None

        min_zone = override.get("min_zone", "CANDIDATE")
        confidence_min = override.get("darwin_confidence_min")
        if confidence_min is not None and score < float(confidence_min):
            return None

        return self._decision("darwin_override", min_zone, metrics, override)
```

```python
class PoolManager:
    def __init__(self, zone_rule_engine: Optional[ZoneRuleEngine] = None) -> None:
        self.zone_rule_engine = zone_rule_engine or ZoneRuleEngine.from_yaml(DEFAULT_ZONE_RULES_PATH)
        self.config = ARGUS_CONFIG.get("pool_zones", {})

    def classify_stock(
        self,
        wind_code: str,
        stock_name: str,
        confidence: float,
        contributing_products: List[str],
        darwin_moment: bool = False,
    ) -> str:
        metrics = ZoneMetrics(
            confidence=float(confidence or 0),
            contributing_products_count=len(contributing_products or []),
            darwin_moment=bool(darwin_moment),
            raw={
                "wind_code": wind_code,
                "stock_name": stock_name,
                "contributing_products": contributing_products,
            },
        )
        return self.zone_rule_engine.classify_initial_zone(metrics).target_zone
```

## 3. 具体代码修改计划

### 3.1 新增文件/函数

1. `skills/research/argus/config/zone_rules.py`
   - `DEFAULT_ZONE_RULES_PATH`
   - `load_zone_rules_config(path: Optional[Path] = None) -> Dict[str, Any]`
   - `validate_zone_rules_config(config: Dict[str, Any]) -> None`
   - `ZONE_RULES_CONFIG`

2. `skills/research/argus/core/zone_rule_engine.py`
   - `ZoneMetrics`
   - `ZoneDecision`
   - `ZoneRuleEngine`
   - `ZoneRuleEngine.from_yaml(path: Optional[Path] = None)`
   - `ZoneRuleEngine.from_config(config: Dict[str, Any])`
   - `ZoneRuleEngine.classify_initial_zone(metrics: ZoneMetrics) -> ZoneDecision`
   - `ZoneRuleEngine.extract_metrics(record: Dict[str, Any]) -> ZoneMetrics`

3. 单元测试文件：
   - `skills/research/argus/tests/test_zone_rule_engine.py`

### 3.2 修改文件/函数

1. `skills/research/argus/config/__init__.py`
   - 导出 `ZONE_RULES_CONFIG` 和 `load_zone_rules_config`。

2. `skills/research/argus/core/__init__.py`
   - 如需外部直接 import，导出 `ZoneRuleEngine`、`ZoneMetrics`、`ZoneDecision`。

3. `skills/research/argus/core/pool_manager.py`
   - `__init__()` 增加可注入参数：
     - `zone_rule_engine: Optional[ZoneRuleEngine] = None`
   - `classify_stock()` 改为构造 `ZoneMetrics` 并调用 `ZoneRuleEngine.classify_initial_zone()`。
   - 删除或仅保留 legacy fallback 中的硬编码默认阈值。
   - `ZONES` 可以继续保留，值来自现有常量；Phase 2 可改为从 YAML `zones.order` 读取。

4. `skills/research/argus/cli/daily_processor.py`
   - Phase 1 不需要改调用签名，仍调用 `PoolManager.classify_stock(...)`。
   - 可选增强：在 `_build_stock_pool_records()` 中直接组装完整 record 后调用 `pool_manager.classify_record(record)`，这样能把 `consensus_confidence`、`crowding_level` 等字段纳入统一 metric extraction。但当前 YAML 的 Argus 初始分类只需要 `confidence`、`contributing_products_count`、`darwin_moment`，因此不是必需。

5. `skills/research/argus/tests/test_argus_core.py`
   - 保留现有 `TestPoolManager` 用例，确保 `PoolManager.classify_stock()` 外部行为不变。
   - 增加边界阈值用例。

6. `skills/research/argus/tests/test_argus_phase2_acceptance.py`
   - 保留 Darwin sector event 用例，验证 same-day sector Darwin 仍能把低分单产品股票保底到 `CANDIDATE`。

### 3.3 保留现有哪些逻辑

必须保留：

- `daily_processor.py` 中先生成 signals、再聚合股票、再分类的主流程。
- `confidence = max(signal.confidence)` 的聚合方式。
- `products = unique(product_code)` 与 `contributing_products_count = len(products)`。
- 分类后再执行 `BayesianScorer.score_signal_pool_records()` 的顺序。
- Darwin 保底 CANDIDATE 的语义。
- `PoolManager.classify_stock()` 的公开方法签名，避免影响 `update_pool()` 和现有测试。
- `SCAN` 作为兜底 zone，而不是分数桶。

不建议在本次改造中改变：

- Argus 初始分类的 score_policy 不要从 `confidence` 切到 `bayesian_score`。YAML 注释也说明 Phase 2 才可在 dry-run diff 后切换。
- Portfolio `StockPoolAutoPromoter` 的 promote/demote 逻辑暂不纳入本次实现，除非另开任务统一 Portfolio transition engine。

## 4. 回归验证计划

### 4.1 一致性验证目标

改造后必须满足：在 `zone_rules_template.yaml` 当前阈值下，`PoolManager.classify_stock()` 对所有旧输入返回与现有逻辑完全一致的 zone。

等价关系：

| 场景 | 现有逻辑 | YAML 配置 |
| --- | --- | --- |
| `confidence >= 0.75` 且产品数 `>= 3` | `CONVICTION` | `entry_rules.conviction` |
| `confidence >= 0.60` 且产品数 `>= 2` | `CANDIDATE` | `entry_rules.candidate` |
| Darwin 且未命中更高规则 | `CANDIDATE` | `darwin_override.min_zone=CANDIDATE` |
| `confidence >= 0.45` | `WATCH` | `entry_rules.watch` |
| 其他 | `SCAN` | `entry_rules.scan.condition=otherwise` |

### 4.2 单元测试用例

新增 `test_zone_rule_engine.py`：

1. `test_yaml_loader_loads_required_sections`
   - 验证 `zones`、`score_policy`、`argus_signal_pool` 必需字段存在。

2. `test_classify_conviction_matches_legacy`
   - 输入：`confidence=0.75, product_count=3, darwin=False`
   - 期望：`CONVICTION`

3. `test_classify_candidate_matches_legacy`
   - 输入：`confidence=0.60, product_count=2, darwin=False`
   - 期望：`CANDIDATE`

4. `test_classify_watch_matches_legacy`
   - 输入：`confidence=0.45, product_count=1, darwin=False`
   - 期望：`WATCH`

5. `test_classify_scan_matches_legacy`
   - 输入：`confidence=0.4499, product_count=1, darwin=False`
   - 期望：`SCAN`

6. `test_darwin_candidate_floor_matches_legacy`
   - 输入：`confidence=0.2, product_count=1, darwin=True`
   - 期望：`CANDIDATE`

7. `test_darwin_does_not_downgrade_conviction`
   - 输入：`confidence=0.85, product_count=3, darwin=True`
   - 期望：`CONVICTION`

8. `test_product_count_gate_prevents_high_score_single_product_candidate`
   - 输入：`confidence=0.70, product_count=1, darwin=False`
   - 期望：`WATCH`
   - 目的：验证高分但产品数不足不会直接进 `CANDIDATE`。

9. `test_score_policy_uses_confidence_first`
   - 输入 record 同时有 `confidence=0.5`、`bayesian_score=0.9`、产品数 3。
   - 期望 Phase 1 使用 `confidence`，返回 `WATCH` 而不是 `CONVICTION`。

保留并扩展 `test_argus_core.py::TestPoolManager`：

- 原 `test_conviction_zone`
- 原 `test_scan_zone`
- 原 `test_darwin_zone_is_candidate_minimum`
- 原 `test_pool_update`
- 新增阈值边界测试：0.75/0.60/0.45 正好命中。

保留 `test_argus_phase2_acceptance.py::test_stock_pool_classification_uses_same_day_sector_darwin_event`：

- 验证 `_build_stock_pool_records()` 将 sector Darwin event 转换为 `darwin_moment=True` 后，仍得到 `CANDIDATE`。

### 4.3 Dry-run 差异验证

建议新增一次性回归脚本或测试辅助：

- 输入：历史若干交易日的 `all_signals` / 或 Mongo 中已有 `08_research_argus_signal_pool` 可重建字段。
- 方法：
  - `legacy_zone = LegacyPoolManager.classify_stock(...)`
  - `new_zone = ZoneRuleEngine.classify_initial_zone(...)`
  - 按 `date/wind_code/confidence/product_count/darwin_moment` 输出 diff。
- 验收：
  - 当前 YAML 阈值下 diff 数量必须为 0。
  - 若未来切换 `score_policy.argus_initial.primary` 到 `bayesian_score`，必须先运行该 dry-run，并把 diff 作为有意策略变更审查。

### 4.4 建议运行命令

```bash
python -m pytest skills/research/argus/tests/test_argus_core.py
python -m pytest skills/research/argus/tests/test_argus_phase2_acceptance.py
python -m pytest skills/research/argus/tests/test_zone_rule_engine.py
```

若要覆盖 Portfolio 侧联动风险：

```bash
python -m pytest skills/portfolio/tests/test_stock_pool_ingestion.py
python -m pytest skills/portfolio/tests/test_stock_pool_auto_promoter.py
```

### 4.5 验收标准

1. `PoolManager.classify_stock()` 不再从硬编码默认阈值决定 zone，而是从 `zone_rules_template.yaml` 的 `argus_signal_pool.entry_rules` 读取阈值。
2. `daily_processor.py` 生成的 `stock_pool_records[*].pool_zone` 与改造前在当前 YAML 阈值下完全一致。
3. Darwin 保底逻辑保持：低分单产品但命中 Darwin 的股票仍进入 `CANDIDATE`。
4. `BayesianScorer` 顺序不变：分类后追加 bayesian score，Phase 1 不使用 bayesian 改变分类。
5. 单元测试和接受测试通过。
