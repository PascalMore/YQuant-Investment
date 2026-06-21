# Argus - 机构智慧资金行为追踪系统

基于 YQuant-Investment 的 Argus 子项目，实现机构资金行为的日度追踪与分析。

## 目录结构

```
skills/research/argus/
├── argus_portfolio_subscriber.py # Phase 5: Argus signal -> Portfolio ingestion payload
├── config/                    # 配置文件
│   ├── argus_config.yaml      # 主配置
│   ├── config.py              # 配置加载
│   └── product_alias.yaml     # 产品化名映射
├── core/                      # 核心业务逻辑
│   ├── bayesian_scoring.py   # Signal-pool 加权评分
│   ├── consensus_direction.py # Phase 4C: Prosperity Gauge + Conviction Radar
│   ├── consensus_engine.py   # 多产品共识
│   ├── credibility.py        # 产品信誉评分
│   ├── crowding.py           # C8 L1-L4 拥挤度
│   ├── darwin_detector.py    # Phase 4B: Darwin 时刻
│   ├── industry_weight_calculator.py # Phase 4A: 行业权重
│   ├── pool_manager.py       # 四区股票池
│   ├── rebalancing_detector.py # 调仓检测
│   └── signal_generator.py   # 信号生成
├── cli/                       # 命令行工具
│   ├── daily_processor.py    # Phase 4/5 日度主流程
│   ├── refresh_all.py        # 清空 + 回填脚本
│   ├── backfill_phase4_bc.py # Phase 4B/4C 回填
│   └── verify_collections.py # Mongo 集合检查
├── tests/                     # 单元测试
└── docs/                      # 文档
```

## 快速开始

### 日度处理

```bash
python -m skills.research.argus.cli.daily_processor 2026-03-11
```

### 运行测试

```bash
python -m pytest skills/research/argus/tests/test_argus_core.py -v
```

## 核心模块

### CredibilityScorer
产品信誉评分引擎，计算产品行为可信度，并写入 `08_research_argus_credential_score`。

### BayesianScorer
Signal-pool 评分器。当前实现是 `rebalancing_score / product_credibility / consensus_score / direction_score` 的加权平均，不是真正 Beta 分布后验。

### SignalGenerator
从持仓比例变化生成标准化信号，写入 `08_research_argus_signal`。

### PoolManager
四区股票池管理：SCAN / WATCH / CANDIDATE / CONVICTION，写入 `08_research_argus_signal_pool`。

### RebalancingDetector
调仓事件检测，识别持仓比例突变。

### CrowdingAnalyzer
C8 四层拥挤度分析：L1 macro / L2 sector / L3 micro / L4 event。

### IndustryWeightCalculator
按申万一级行业聚合产品持仓，输出 `weight_pct` 与 `weight_change_1d/30d/60d`。

### DarwinDetector
Phase 4B 达尔文时刻检测：行业 20 日回撤 + 弱/强产品 `weight_change_30d` 分歧。

### ConsensusEngine
多产品共识引擎，跨产品汇聚信号。

### ConsensusDirectionEngine
Phase 4C 共识方向引擎：Prosperity Gauge + Conviction Radar。

### ArgusPortfolioSubscriber
Phase 5 订阅器：读取 `08_research_argus_signal`，按日期、置信度、pool zone 过滤，转换为 Portfolio stock-pool ingestion payload。

## 输出

- 日志：`logs/research/argus/argus_{YYYYMMDD}.log`
- 信号：`logs/research/argus/argus_signal_{YYYYMMDD}.json`
- MongoDB：
  - `08_research_argus_credential_score`
  - `08_research_argus_signal`
  - `08_research_argus_signal_pool`
  - `08_research_argus_industry_weight`
  - `08_research_argus_darwin_event`
  - `08_research_argus_consensus_direction`
  - `05_portfolio_stock_pool`
  - `05_portfolio_stock_pool_audit`

## 依赖

- skills/data/ - 数据接口
- skills/infra/ - 基础设施
- skills/portfolio/stock_pool/ - Phase 5 股票池同步
