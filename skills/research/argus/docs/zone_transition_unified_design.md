# Argus 升区/降区统一设计方案

## 1. 改造前状态确认

本节记录本设计形成时的改造前代码状态，用于说明为什么需要统一 `ZoneRuleEngine`；当前 runtime 状态见 §2.3。

- `skills/research/argus/core/pool_manager.py`
  - `PoolManager.classify_stock()` 负责 Argus signal-pool 初始分区。
  - 使用 `confidence` 和 `contributing_products` 做直接分类。
  - `CONVICTION`: `confidence >= 0.75` 且贡献产品数 `>= 3`。
  - `CANDIDATE`: `confidence >= 0.60` 且贡献产品数 `>= 2`。
  - `WATCH`: `confidence >= 0.45`。
  - `SCAN`: 所有不满足上面规则的股票默认落入。
  - Darwin moment 至少落到 `CANDIDATE`。
  - 改造前没有 hysteresis。

- `skills/portfolio/stock_pool/auto_promoter.py`
  - `StockPoolAutoPromoter` 负责 Portfolio stock-pool active 记录的自动升降区。
  - 升区每次最多一级：`SCAN -> WATCH -> CANDIDATE -> CONVICTION`。
  - 降区每次最多一级：`CONVICTION -> CANDIDATE -> WATCH -> SCAN`。
  - 升区和降区共用同一组 `ZONE_THRESHOLDS`。
  - 降区逻辑是“当前 zone 对应阈值不再满足则降一级”。
  - 改造前没有独立 hysteresis 阈值。

- `skills/portfolio/stock_pool/ingestion.py`
  - `ingest_signals_incremental()` 根据 current / previous signal-pool 差异产生 `entry/promote/demote/exit/update`。
  - `exit` 不是降区，而是当 previous 有股票、current 已无股票时，将 Portfolio active record 置为 inactive。

统一配置模板落地在：

```text
skills/research/argus/config/zone_rules_template.yaml
```

接口草案见：

```text
skills/research/argus/docs/zone_rule_engine_interfaces.py
```

该接口文件是早期 documentation-only 草案；当前 runtime 实现以 `skills/research/argus/core/zone_rule_engine.py` 为准。

## 2. 核心设计决策

### 2.0 Signal ID 生成策略（幂等性设计）

**设计原则**：signal_id 基于业务键的确定性 hash，不使用随机 UUID。

**生成公式**：
```python
key = f"{trade_date}:{product_code}:{wind_code}:{signal_type}"
signal_id = f"argus:{sha256(key).hexdigest()[:20]}"
```

**目的**：
- 支持 upsert 语义：同一业务键重跑时更新而非重复插入
- 确保幂等性：相同输入永远产生相同的 signal_id
- 支持增量更新：refresh_all 重跑不会膨胀数据

**对比旧方案**：
| 项目 | 旧方案 | 新方案 |
|------|--------|--------|
| signal_id 生成 | `uuid.uuid4()` 随机 | SHA256 确定性 hash |
| 重跑行为 | 插入新记录，数据膨胀 | upsert 更新，幂等 |
| ID 长度 | 36 字符 | 26 字符（argus: + 20 hex）|


**实现文件**：
- `skills/research/argus/core/signal_generator.py` — `_create_signal()` 方法
- `skills/research/argus/cli/daily_processor.py` — `_write_signals_to_mongodb()` 使用 `bulk_write(upsert=True)`

### 2.1 SCAN 入口规则

采用 Option A：SCAN 无条件进入，作为最低区兜底。

原因：

1. 这与现有 `PoolManager.classify_stock()` 行为一致：所有不满足 `WATCH/CANDIDATE/CONVICTION` 的股票最终返回 `SCAN`。
2. SCAN 是生命周期最低区，不是一个“低分区间”。如果设置 `bayesian < 0.30` 或 `confidence < 0.45` 才能进入 SCAN，会出现高分但缺少产品数、共识或其他门槛的股票无法归类。
3. Portfolio incremental ingestion 也默认把缺失 `pool_zone` 的 Argus 信号映射为 `SCAN`，因此 SCAN 应保持 residual/default semantics。

模板中的实现：

```yaml
argus_signal_pool:
  entry_rules:
    scan:
      target_zone: SCAN
      condition: otherwise
      min_score: null
      max_score: null
      terminal: true
  evaluation_order:
    - conviction
    - candidate
    - watch
    - scan
```

如果未来需要低质量过滤，建议新增 `quality_gate` 或 `inactive/noise` 状态，而不是给 SCAN 添加上限阈值。

### 2.2 entry / promote / demote / exit 的统一语义

统一后四个操作覆盖四个 zone 的方式如下：

| 操作 | 适用对象 | zone 覆盖 | 语义 | 当前代码来源 |
| --- | --- | --- | --- | --- |
| `entry` | 新进入 Argus / Portfolio 的股票 | `SCAN/WATCH/CANDIDATE/CONVICTION` | current 有、previous 无；按初始规则给目标 zone | `PoolManager` + `StockPoolIngestionService._apply_entry()` |
| `promote` | 已 active 的股票 | `SCAN->WATCH`, `WATCH->CANDIDATE`, `CANDIDATE->CONVICTION` | 通过下一层 zone 的 promote rule，每次最多升一级 | `StockPoolAutoPromoter.evaluate_and_promote()` |
| `demote` | 已 active 的股票 | `CONVICTION->CANDIDATE`, `CANDIDATE->WATCH`, `WATCH->SCAN` | 不满足当前层 retention rule，每次最多降一级 | 当前代码是 fail current threshold；新模板改为 retention threshold |
| `exit` | 已 active 但当日不再有 Argus 支撑的股票 | 任意当前 zone | 置为 inactive，不是降到 SCAN | `StockPoolIngestionService._apply_exit()` |

注意：

- `SCAN` 可以 entry、promote、exit；不能继续 demote。
- `CONVICTION` 可以 entry、demote、exit；不能继续 promote。
- `exit` 是生命周期退出，不能与 `demote` 混用。弱信号但仍有支撑时应降区；无当日支撑时才退出。

### 2.3 Zone 转换 - Hysteresis 机制

已启用独立 hysteresis 阈值。

设计目的是避免边界震荡。例如 `WATCH -> CANDIDATE` 升区阈值为 `bayesian >= 0.55` 且 `consensus >= 0.40`，若次日只轻微回落，不应立即降回 WATCH；只有当前级 retention rule 失败时才降一级。

统一模板采用 retention threshold：

| 当前 zone | 升区阈值 | 降区 retention 阈值 | 设计意图 |
| --- | --- | --- | --- |
| `WATCH` | `SCAN -> WATCH`: `bayesian >= 0.30`, 产品数 `>= 2` | `bayesian >= 0.25`, 产品数 `>= 1` | 给新进入 WATCH 的弱信号留观察空间 |
| `CANDIDATE` | `WATCH -> CANDIDATE`: `bayesian >= 0.50`, `consensus >= 0.40` | `bayesian >= 0.45`, `consensus >= 0.30` | 避免共识轻微波动导致反复降回 WATCH |
| `CONVICTION` | `CANDIDATE -> CONVICTION`: `bayesian >= 0.70`, 产品数 `>= 3` | `bayesian >= 0.65`, 产品数 `>= 2` | 高信念区需要更稳定，但不因单日小幅衰减立刻降区 |

模板中的实现：

```yaml
portfolio_transitions:
  hysteresis:
    enabled: true
    policy: independent_retention_thresholds
  demote_rules:
    watch_retention:
      bayesian_min: 0.25
      product_count_min: 1
    candidate_retention:
      bayesian_min: 0.45
      consensus_min: 0.30
    conviction_retention:
      bayesian_min: 0.65
      product_count_min: 2
      crowding_max: DANGER
```

当前状态机由 `ZoneRuleEngine.classify_transition(metrics, current_zone)` 执行，顺序固定为：

1. exit 优先：`missing_from_signal_pool` 时直接 `EXIT`，这是生命周期退出，不是降到 `SCAN`。
2. promote 限一步：未退出时只检查下一档 zone 的晋级规则，最多上移一级。
3. demote 限一步：若当前 zone 的 retention rule 失败，最多下移一级。
4. retain：metrics 无显著变化、既未满足下一档晋级也未触发保留失败时，保持当前 zone。

旧方案使用 `classify_initial_zone()` 每日重新计算，无历史状态，无法表达“进入更难、保留稍宽”的 retention buffer。

## 3. 统一 YAML 结构

`zone_rules_template.yaml` v2 的核心结构：

```yaml
zones:
  order: [SCAN, WATCH, CANDIDATE, CONVICTION]
  default_zone: SCAN

score_policy:
  argus_initial:
    primary: confidence
  portfolio_transition:
    primary: bayesian_score

argus_signal_pool:
  classification_mode: direct_target
  entry_rules:
    conviction: ...
    candidate: ...
    watch: ...
    scan:
      condition: otherwise

portfolio_transitions:
  transition_mode: one_step
  entry_rules: ...
  promotion_path: ...
  demotion_path: ...
  promote_rules: ...
  demote_rules: ...
  exit_rules: ...
  hysteresis: ...
```

设计边界：

- `zones.order` 是唯一 zone rank 来源。
- `argus_signal_pool.entry_rules` 负责初始分类，可直接跳到任意目标 zone。
- `portfolio_transitions.promote_rules` 负责存量升区，每次最多一级。
- `portfolio_transitions.demote_rules` 负责存量降区，每次最多一级，并使用 retention threshold。
- `portfolio_transitions.exit_rules` 负责 active record 退出，不参与 zone rank。

## 4. ZoneRuleEngine 最小接口

如果后续新建 `ZoneRuleEngine`，必须提供以下方法签名。`zone_rule_engine_interfaces.py` 已有草案，可不改运行代码。

```python
class ZoneRuleEngine:
    @classmethod
    def from_yaml(cls, path: str) -> "ZoneRuleEngine": ...

    @classmethod
    def from_argus_config(cls, argus_config: dict) -> "ZoneRuleEngine": ...

    def extract_metrics(self, record: dict) -> ZoneMetrics: ...

    def classify_initial_zone(self, metrics: ZoneMetrics) -> ZoneDecision: ...

    def classify_signal_pool_record(self, record: dict) -> dict: ...

    def classify_transition(self, metrics: ZoneMetrics, current_zone: str) -> ZoneDecision: ...

    def zone_delta_action(self, previous_zone: str | None, current_zone: str) -> str | None: ...

    def normalize_zone(self, zone: str) -> str: ...
```

实现要求：

- 规则引擎必须是纯函数式业务模块，不直接读写 Mongo。
- `PoolManager` 可作为兼容 facade，委托 `classify_initial_zone()`。
- `StockPoolAutoPromoter` 只负责读取 active records、调用 `classify_transition()`、执行 `move_entry()`。
- `StockPoolIngestionService` 可复用 `zone_delta_action()` 和 `extract_metrics()`，但仍保留同步和审计边界。

## 5. 接入策略

### Phase 1: 配置落地

目标：

- `zone_rules_template.yaml` 成为统一规则模板。
- 保持现有 runtime 行为不变。
- 用 dry-run 对比 `argus_config.yaml.zone_thresholds`、`StockPoolAutoPromoter.ZONE_THRESHOLDS` 与模板是否漂移。

### Phase 2: 规则引擎接入

目标：

- 新增 `skills/research/argus/core/zone_rule_engine.py`。
- `PoolManager`、`StockPoolAutoPromoter`、`StockPoolIngestionService` 复用同一个 zone rank、metrics extraction、threshold evaluation。
- 初始默认保持 `argus_initial.primary = confidence`，保证旧测试通过。

必测用例：

- SCAN unconditional entry。
- CONVICTION / CANDIDATE / WATCH 初始分类兼容旧 `PoolManager`。
- Darwin floor 至少 CANDIDATE。
- `SCAN -> WATCH -> CANDIDATE -> CONVICTION` 一步升区。
- `CONVICTION -> CANDIDATE -> WATCH -> SCAN` 一步降区。
- retention hysteresis 边界。
- `missing_from_current_signal_pool` 触发 exit。

### Phase 3: Bayesian 口径切换

目标：

- `daily_processor` 在 Bayesian scoring 后再调用 `ZoneRuleEngine.classify_signal_pool_record()`。
- 将 `argus_signal_pool.score_policy.primary` 从 `confidence` 切到 `bayesian_score` 前，先对最近 60 个交易日生成 dry-run diff。

验收标准：

- feature flag 为 `confidence` 时，结果与当前 `PoolManager` 一致。
- feature flag 为 `bayesian_score` 时，输出 zone transition matrix 和变更样本。
- Portfolio audit 仍能正确产生 `entry/promote/demote/exit/update`。
