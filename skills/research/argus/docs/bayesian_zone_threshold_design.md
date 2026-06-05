# bayesian_score 统一分区阈值设计

## 1. 结论

建议把 Argus signal-pool 初始分区从当前的 `confidence` 两阶段口径切换为一步完成：

1. `daily_processor` 先生成 raw signals、consensus、crowding、Darwin 事件和 stock-level records。
2. `BayesianScorer` 先为每个 stock-level record 计算 `bayesian_score`。
3. 统一 `ZoneRuleEngine` 再基于 `bayesian_score + consensus_confidence + contributing_products_count + crowding_level + darwin_moment` 直接给出 `SCAN/WATCH/CANDIDATE/CONVICTION`。
4. Portfolio 的 entry/promote/demote/exit 复用同一份 `config/zone_rules_template.yaml`。

核心阈值表：

| Zone | Entry / Promote 条件 | Retention 条件 | Exit 条件 | Crowding |
| --- | --- | --- | --- | --- |
| `SCAN` | residual otherwise | terminal bottom | missing from current signal pool | 不限制 |
| `WATCH` | `bayesian_score >= 0.35`, 产品数 `>=1`, consensus `>=0.20` | `bayesian_score >= 0.25`, 产品数 `>=1`, consensus `>=0.10` | missing from current signal pool | 不限制 |
| `CANDIDATE` | `bayesian_score >= 0.55`, 产品数 `>=2`, consensus `>=0.40` | `bayesian_score >= 0.48`, 产品数 `>=1`, consensus `>=0.30` | missing from current signal pool | 允许到 `DANGER` |
| `CONVICTION` | `bayesian_score >= 0.75`, 产品数 `>=3`, consensus `>=0.60` | `bayesian_score >= 0.68`, 产品数 `>=2`, consensus `>=0.50` | missing from current signal pool | 最高 `HIGH`，`DANGER` 不进/不留 |

Darwin override 采用 `darwin_moment` 触发、`bayesian_score` 或 `darwin_confidence` 保护的 floor-only 方案：仅在 `bayesian_score >= 0.45` 或 `darwin_confidence >= 0.70` 时把 zone 至少抬到 `CANDIDATE`；不直接强制 `CONVICTION`，高信念区仍必须满足常规 `bayesian_score/product_count/consensus/crowding` 条件。

## 2. 为什么 defer 到 bayesian_score 后再分类

当前 `daily_processor` 的顺序是：

```text
_build_stock_pool_records()
  -> PoolManager.classify_stock(confidence, products, darwin_moment)
  -> 得到 pool_zone
BayesianScorer.score_signal_pool_records()
  -> 追加 bayesian_score，但不重算 pool_zone
```

这个两阶段流程的问题：

1. 初始分区没有使用最终主评分。`bayesian_score` 聚合了 rebalancing、产品可信度、产品数共识和交易方向，但当前初始 `pool_zone` 只看 raw `confidence` 和产品数。
2. 配置漂移。`PoolManager.classify_stock()` 当前硬编码/读取 `pool_zones` 的 `confidence` 阈值；`StockPoolAutoPromoter` 另有 `ZONE_THRESHOLDS`，使用 `bayesian_score`。同一只股票在 Argus entry 和 Portfolio promote/demote 阶段可能被不同口径判断。
3. 阈值语义不统一。当前 Argus 初始分类边界是 `confidence >= 0.45/0.60/0.75`，Portfolio 升降区边界是 `bayesian >= 0.30/0.50/0.70`，且降区复用升区阈值，没有 hysteresis。
4. 审计解释困难。signal-pool 写出的记录同时包含 `pool_zone` 和 `bayesian_score`，但 zone 不是由 `bayesian_score` 决定，后续 review 会看到“高 bayesian 低 zone”或“低 bayesian 高 zone”的样本。

一步到位的优势：

1. 单一主评分。所有 entry/promote/demote 都以 `bayesian_score` 为主，产品数、consensus、crowding 作为门槛约束。
2. 研究到组合生命周期一致。Argus 初始入池和 Portfolio 生命周期迁移共用同一份 YAML 规则。
3. 更接近真实信号质量。`bayesian_score` 已经吸收产品 credibility、产品数 consensus、rebalancing 类型和方向质量，比 raw `confidence` 更适合作为 zone 边界。
4. 可以自然引入 hysteresis。升区使用 entry/promote 阈值，降区使用 retention 阈值，减少边界附近日内/日间震荡。

## 3. 阈值设计

### 3.1 Entry：Argus signal-pool 初始分类

| 目标 zone | `bayesian_score` | 产品数 | consensus | crowding | 说明 |
| --- | ---: | ---: | ---: | --- | --- |
| `CONVICTION` | `>= 0.75` | `>= 3` | `>= 0.60` | `<= HIGH` | 高分、多产品、强共识，且不能处于拥挤危险态 |
| `CANDIDATE` | `>= 0.55` | `>= 2` | `>= 0.40` | `<= DANGER` | 明确候选，允许拥挤但不直接升最高区 |
| `WATCH` | `>= 0.35` | `>= 1` | `>= 0.20` | 不限制 | 低强度但有可观察支撑 |
| `SCAN` | otherwise | 不限 | 不限 | 不限制 | 残差区，不设置分数上限 |

`SCAN` 必须保留 residual 语义。高分但缺产品数或 consensus 的股票应落入较低 zone，而不是变成“无法分类”。

### 3.2 Promote：Portfolio 存量升区

Portfolio 升区每次最多一级，阈值与 entry 边界保持一致：

| 路径 | `bayesian_score` | 产品数 | consensus | crowding |
| --- | ---: | ---: | ---: | --- |
| `SCAN -> WATCH` | `>= 0.35` | `>= 1` | `>= 0.20` | 不限制 |
| `WATCH -> CANDIDATE` | `>= 0.55` | `>= 2` | `>= 0.40` | `<= DANGER` |
| `CANDIDATE -> CONVICTION` | `>= 0.75` | `>= 3` | `>= 0.60` | `<= HIGH` |

相对当前 `StockPoolAutoPromoter.ZONE_THRESHOLDS` 的变化：

| 路径 | 当前阈值 | 新阈值 | 变化理由 |
| --- | --- | --- | --- |
| `SCAN -> WATCH` | `bayesian >= 0.30`, 产品数 `>=2` | `bayesian >= 0.35`, 产品数 `>=1`, consensus `>=0.20` | WATCH 是观察区，不应强制两产品；但提高 score 并加最低 consensus，过滤弱噪声 |
| `WATCH -> CANDIDATE` | `bayesian >= 0.50`, consensus `>=0.40` | `bayesian >= 0.55`, 产品数 `>=2`, consensus `>=0.40` | CANDIDATE 必须有至少两个产品支撑，减少单产品高分误升 |
| `CANDIDATE -> CONVICTION` | `bayesian >= 0.70`, 产品数 `>=3`, crowding `<=DANGER` | `bayesian >= 0.75`, 产品数 `>=3`, consensus `>=0.60`, crowding `<=HIGH` | CONVICTION 是最高信念区，提高分数/共识门槛，并禁止 DANGER 拥挤状态 |

### 3.3 Demote：Portfolio 保留阈值和 hysteresis

降区不再复用升区阈值，而是用 retention threshold。只要当前 zone 满足 retention 就保留；失败才降一级。

| 当前 zone | 保留阈值 | 对应升区阈值 | Hysteresis |
| --- | --- | --- | --- |
| `WATCH` | `bayesian >= 0.25`, 产品数 `>=1`, consensus `>=0.10` | `SCAN -> WATCH`: `0.35 / 1 / 0.20` | bayesian `-0.10`, consensus `-0.10` |
| `CANDIDATE` | `bayesian >= 0.48`, 产品数 `>=1`, consensus `>=0.30` | `WATCH -> CANDIDATE`: `0.55 / 2 / 0.40` | bayesian `-0.07`, consensus `-0.10`，产品数允许从 2 降到 1 |
| `CONVICTION` | `bayesian >= 0.68`, 产品数 `>=2`, consensus `>=0.50`, crowding `<=HIGH` | `CANDIDATE -> CONVICTION`: `0.75 / 3 / 0.60` | bayesian `-0.07`, consensus `-0.10`，产品数允许从 3 降到 2 |

相对当前 auto_promoter，最大变化是降区不再使用同一组升区阈值。旧逻辑在 `0.50/0.70` 边界附近会频繁 promote/demote，新逻辑把状态机改成“进入更难，保留稍宽”，符合组合管理的低换手要求。

### 3.4 Exit

`exit` 只表示生命周期退出，不是降到 `SCAN`。

当前建议保持现有 ingestion 语义：previous signal-pool 有股票、current signal-pool 缺失时，Portfolio active record 置为 inactive。只要当日仍有 Argus 支撑，即使评分很弱也应通过 `demote` 降到更低 zone，而不是 `exit`。

不建议在本轮加入 `bayesian_score < x` 的强制 exit，因为这会把“弱信号仍存在”和“信号消失”两个不同状态混在一起，影响审计归因。

### 3.5 Crowding

Crowding 只作为高区风险闸门，不作为低区过滤器：

| Zone | Crowding 限制 |
| --- | --- |
| `SCAN` | 不参与 |
| `WATCH` | 不参与 |
| `CANDIDATE` | 允许到 `DANGER`，记录风险但不阻断 |
| `CONVICTION` | 最高 `HIGH`，`DANGER` 阻断 entry/promote/retention |

这比当前 `candidate_to_conviction` 的 `crowding_max: DANGER` 更严格。旧配置实际上不会阻断任何已知 crowding level；新配置明确把 DANGER 作为最高信念区的风险否决项。

## 4. Darwin override

Darwin 是市场状态/行业状态信号，不应替代 stock-level quality score。

建议规则：

1. 触发基于 `darwin_moment`。
2. floor 生效需要满足保护条件：`bayesian_score >= 0.45` 或 `darwin_confidence >= 0.70`。
3. floor 只抬到 `CANDIDATE`，不强制 `CONVICTION`。
4. 如果股票本身满足 `CONVICTION` 常规规则，可以进入 `CONVICTION`；Darwin 不降低常规门槛。

与当前 `PoolManager.classify_stock()` 的区别：当前 Darwin 股票无论 score 如何至少 `CANDIDATE`；新方案要求有最低 bayesian 或 Darwin 事件置信度保护，避免系统性事件把低质量个股直接抬入候选区。

## 5. daily_processor 实施计划调整

当前需要调整计算顺序。

现状代码位于 `skills/research/argus/cli/daily_processor.py`：

```text
consensus = consensus_engine.calculate_consensus(all_signals)
crowding = crowding_analyzer.analyze(...)
stock_pool_records = _build_stock_pool_records(..., pool_manager, ...)
stock_pool_records = BayesianScorer(...).score_signal_pool_records(stock_pool_records, all_signals)
```

目标顺序：

```text
consensus = consensus_engine.calculate_consensus(all_signals)
crowding = crowding_analyzer.analyze(...)
stock_pool_records = _build_stock_pool_records_without_zone(...)
stock_pool_records = BayesianScorer(...).score_signal_pool_records(stock_pool_records, all_signals)
stock_pool_records = ZoneRuleEngine(zone_rules).classify_signal_pool_records(stock_pool_records)
```

需要的具体改动：

1. `_build_stock_pool_records()` 不再调用 `PoolManager.classify_stock()` 做最终 zone；只构造 stock-level metrics。为了兼容迁移期，可先写入临时字段 `legacy_confidence_zone`。
2. `BayesianScorer` 必须在 zone 分类前调用。
3. 新增或接入 `ZoneRuleEngine`，从 `config/zone_rules_template.yaml` 读取 `argus_signal_pool.entry_rules`。
4. `_annotate_signals()` 使用重新分类后的 `pool_zone`。
5. `PoolManager.classify_stock()` 可保留为 legacy facade，但不再作为 daily_processor 主路径。
6. 上线前对最近 60 个交易日做 dry-run diff：输出旧 confidence zone、新 bayesian zone、变更矩阵、按 zone 的样本列表和 Portfolio transition 影响。

验收标准：

1. `bayesian_score` 已存在后才产生最终 `pool_zone`。
2. YAML 中 `score_policy.argus_initial.primary = bayesian_score`。
3. Argus signal-pool entry、Portfolio promote/demote、Darwin floor 都能从同一 YAML 读取阈值。
4. Portfolio `exit` 仍由 current/previous signal-pool 差异驱动，不被低 score 误触发。

## 6. 已更新配置

本设计已更新：

```text
skills/research/argus/config/zone_rules_template.yaml
```

配置版本从 `version: 2` 提升为 `version: 3`，并将 `score_policy.argus_initial.primary` 改为 `bayesian_score`。
