---
file_id: ARGUS-03
title: "三层数据库Schema"
rfc_id: RFC-2026-071
doc_status: "DRAFT"
approval_status: "NOT_SUBMITTED"
impl_status: "NOT_STARTED"
version: "2.0.0-draft"
created: "2026-04-12"
drafter: "Internal Review Board"
owner: "Internal Review Board"
depends_on:
  - "ARGUS-000 (INDEX)"
  - "ARGUS-02 (独立架构)"
amendment_level: L2
---

# ARGUS-03: 三层数据库Schema {#ARGUS-03:root}

> **本文件为RFC-2026-071的第三章 (Normative)**。
> **本文件是ARGUS数据库的权威定义**, 所有实现必须与此DDL一致。

---

## 1 三层表一览 {#ARGUS-03:overview}

| # | 层级 | 表名 | 用途 | 频率 |
|:--:|:--:|:--|:--|:--|
| 1 | Raw | `raw_daily_trade` | 每日交易记录 | 日度, 只追加 |
| 2 | Raw | `raw_daily_holding` | 每日全持仓快照 | 日度, 只追加 |
| 3 | Raw | `raw_product_nav` | 产品每日NAV | 日度, 只追加 |
| 4 | Raw | `raw_product_info` | 产品元数据 | 低频, 可更新 |
| 5 | Proc | `argus_product_profile` | 产品画像+贝叶斯信誉 | 日度更新 |
| 6 | Proc | `argus_rebalancing_event` | 调仓路径事件 | 日度生成 |
| 7 | Proc | `argus_signal` | 多时间框架信号 | 日度生成 |
| 8 | Proc | `argus_consensus` | 多产品共识事件 | 日度生成 |
| 9 | Proc | `argus_darwin_event` | 达尔文时刻检测 | 事件驱动 |
| 10 | Proc | `argus_consensus_direction` | 景气度+信念偏移 | 日度更新 |
| 11 | Dec | `argus_stock_pool` | 四区动态股票池 | 日度更新 |
| 12 | Dec | `argus_stock_pool_history` | 池变更审计轨迹 | 事件驱动 |
| 13 | Bak | `argus_hf_estimate` | 高频估算 (仅备用) | 按需 |

**总计**: Raw 4 + Processed 6 + Decision 2 + Fallback 1 = **13表**

---

## 2 第一层 Raw (4表) {#ARGUS-03:raw}

> Raw层只INSERT不UPDATE/DELETE (raw_product_info例外), 触发器强制不变性。

### 2.1 raw_daily_trade

```sql
CREATE TABLE raw_daily_trade (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code    TEXT NOT NULL,
    product_name    TEXT NOT NULL,       -- 含AUM编码 (如"中欧1号-3.6e")
    aum_scale       REAL,               -- AUM规模 (亿元)
    wind_code       TEXT NOT NULL,       -- Wind代码 (如600036.SH)
    stock_name      TEXT NOT NULL,
    change_type     TEXT NOT NULL
        CHECK (change_type IN ('BUY','SELL','INCREASE','DECREASE','NEW_ENTRY','FULL_EXIT')),
    change_amount   REAL,               -- 变动金额 (万元)
    change_shares   REAL,               -- 变动股数 (万股)
    trade_date      TEXT NOT NULL        -- YYYY-MM-DD
        CHECK (trade_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    source_file     TEXT,
    import_batch    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_raw_trade_prod  ON raw_daily_trade(product_code, trade_date);
CREATE INDEX idx_raw_trade_stock ON raw_daily_trade(wind_code, trade_date);
CREATE INDEX idx_raw_trade_date  ON raw_daily_trade(trade_date);
CREATE INDEX idx_raw_trade_type  ON raw_daily_trade(change_type);
```

### 2.2 raw_daily_holding

```sql
CREATE TABLE raw_daily_holding (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code    TEXT NOT NULL,
    product_name    TEXT NOT NULL,
    wind_code       TEXT NOT NULL,
    stock_name      TEXT NOT NULL,
    shares          REAL,               -- 持有股数 (万股)
    market_value    REAL,               -- 市值 (万元)
    weight_pct      REAL CHECK (weight_pct IS NULL OR (weight_pct >= 0 AND weight_pct <= 100)),
    cost_price      REAL,
    current_price   REAL,
    change_flag     TEXT
        CHECK (change_flag IS NULL OR change_flag IN ('NEW','INCREASED','DECREASED','UNCHANGED','EXITED')),
    snapshot_date   TEXT NOT NULL
        CHECK (snapshot_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    source_file     TEXT,
    import_batch    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_raw_hold_prod  ON raw_daily_holding(product_code, snapshot_date);
CREATE INDEX idx_raw_hold_stock ON raw_daily_holding(wind_code, snapshot_date);
CREATE INDEX idx_raw_hold_date  ON raw_daily_holding(snapshot_date);
CREATE UNIQUE INDEX idx_raw_hold_uniq ON raw_daily_holding(product_code, wind_code, snapshot_date);
```

### 2.3 raw_product_nav

```sql
CREATE TABLE raw_product_nav (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code    TEXT NOT NULL,
    nav_date        TEXT NOT NULL
        CHECK (nav_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    nav             REAL NOT NULL CHECK (nav > 0),
    cumulative_nav  REAL,
    daily_return_pct REAL,              -- 日收益率 (%)
    source_file     TEXT,
    import_batch    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_raw_nav_prod ON raw_product_nav(product_code, nav_date);
CREATE UNIQUE INDEX idx_raw_nav_uniq ON raw_product_nav(product_code, nav_date);
```

### 2.4 raw_product_info

```sql
CREATE TABLE raw_product_info (
    product_code    TEXT PRIMARY KEY,
    product_name    TEXT NOT NULL,       -- 含AUM编码
    manager_name    TEXT,
    company_name    TEXT,
    aum_scale       REAL,               -- 亿元
    aum_tier        TEXT CHECK (aum_tier IS NULL OR aum_tier IN ('S','A','B','C','U')),
        -- S>100亿, A:50-100, B:20-50, C:5-20, U:Unknown
    product_type    TEXT CHECK (product_type IS NULL OR product_type IN ('EQUITY','HYBRID','BOND','INDEX','OTHER')),
    style_label     TEXT CHECK (style_label IS NULL OR style_label IN (
        'VALUE','GROWTH','BALANCED','THEMATIC','CONTRARIAN','MOMENTUM','UNKNOWN')),
    benchmark_index TEXT,
    inception_date  TEXT,
    tracking_start  TEXT,               -- ARGUS开始跟踪日期
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## 3 第二层 Processed (6表) {#ARGUS-03:processed}

> Processed层可更新、可重算, 从Raw层经清洗/标准化/分析引擎计算而来。

### 3.1 argus_product_profile

```sql
CREATE TABLE argus_product_profile (
    product_code    TEXT PRIMARY KEY,
    -- 质量指标
    sharpe_ratio    REAL,
    calmar_ratio    REAL,
    max_drawdown    REAL,               -- 最大回撤 (%, 负数)
    annual_return   REAL,
    win_rate        REAL CHECK (win_rate IS NULL OR (win_rate >= 0 AND win_rate <= 100)),
    quality_pass    INTEGER NOT NULL DEFAULT 0 CHECK (quality_pass IN (0,1)),
    -- 贝叶斯信誉 Beta(alpha, beta)
    bayes_alpha     REAL NOT NULL DEFAULT 2.0 CHECK (bayes_alpha > 0),
    bayes_beta      REAL NOT NULL DEFAULT 2.0 CHECK (bayes_beta > 0),
    credibility     REAL NOT NULL DEFAULT 0.5 CHECK (credibility >= 0 AND credibility <= 1),
    credibility_ci  REAL,               -- 95% CI半宽
    last_decay_date TEXT,
    credibility_frozen INTEGER NOT NULL DEFAULT 0 CHECK (credibility_frozen IN (0,1)),
    freeze_reason   TEXT,
    -- 风格与行为
    style_label     TEXT,
    avg_turnover    REAL,
    avg_holding_period REAL,            -- 天
    sell_quality_score REAL,            -- REV-009
    -- 元信息
    signal_count    INTEGER NOT NULL DEFAULT 0,
    correct_count   INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE','INACTIVE','FROZEN','PROBATION')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_code) REFERENCES raw_product_info(product_code)
);
```

### 3.2 argus_rebalancing_event

```sql
CREATE TABLE argus_rebalancing_event (
    event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code    TEXT NOT NULL,
    wind_code       TEXT NOT NULL,
    stock_name      TEXT,
    event_date      TEXT NOT NULL
        CHECK (event_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    event_type      TEXT NOT NULL CHECK (event_type IN (
        'NEW_ENTRY','CONTINUOUS_ADD','CONCENTRATED_ADD','CONSENSUS_ADD',
        'BENCHMARK_REBAL','PROBE',
        'PROFIT_TAKE','STOP_LOSS','PASSIVE_SELL','PARTIAL_EXIT','FULL_EXIT',
        'HOLD_STEADY','SEQUENTIAL_BUILD')),
    buy_intent      TEXT CHECK (buy_intent IS NULL OR buy_intent IN ('HEAVY','NORMAL','PROBE','SEQUENTIAL')),
    sell_quality    TEXT CHECK (sell_quality IS NULL OR sell_quality IN ('STRATEGIC','REACTIVE','PANIC')),
    weight_change_pct REAL,             -- 持仓权重变化 (pp)
    amount          REAL,               -- 交易金额 (万元)
    pnl_pct         REAL,               -- 预估损益 (%)
    sector_sw1      TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_code) REFERENCES raw_product_info(product_code)
);
CREATE INDEX idx_rebal_prod  ON argus_rebalancing_event(product_code, event_date);
CREATE INDEX idx_rebal_stock ON argus_rebalancing_event(wind_code, event_date);
CREATE INDEX idx_rebal_type  ON argus_rebalancing_event(event_type);
CREATE INDEX idx_rebal_date  ON argus_rebalancing_event(event_date);
```

### 3.3 argus_signal

```sql
CREATE TABLE argus_signal (
    signal_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    wind_code       TEXT NOT NULL,
    stock_name      TEXT,
    signal_date     TEXT NOT NULL
        CHECK (signal_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    timeframe       TEXT NOT NULL CHECK (timeframe IN ('FAST','MEDIUM','SLOW')),
    signal_type     TEXT NOT NULL CHECK (signal_type IN (
        'SMART_BUY','SMART_SELL','CONSENSUS_BUY','CONSENSUS_SELL',
        'SEQUENTIAL_BUILD','DARWIN_BUY','SECTOR_ROTATION','DIRECTION_SHIFT')),
    direction       TEXT NOT NULL CHECK (direction IN ('BULLISH','BEARISH','NEUTRAL')),
    -- 贝叶斯评分
    bayesian_score  REAL NOT NULL CHECK (bayesian_score >= 0 AND bayesian_score <= 1),
    prior_score     REAL,
    likelihood_ratio REAL,
    -- 来源
    contributing_products TEXT,          -- JSON array
    product_count   INTEGER NOT NULL DEFAULT 1,
    data_source_tier TEXT NOT NULL DEFAULT 'T1' CHECK (data_source_tier IN ('T0','T1','T2')),
    -- 状态
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE','CONFIRMED','EXPIRED','INVALIDATED')),
    expiry_date     TEXT,
    outcome_tag     TEXT CHECK (outcome_tag IS NULL OR outcome_tag IN ('CORRECT','INCORRECT','PENDING','AMBIGUOUS')),
    outcome_return_pct REAL,
    sector_sw1      TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_sig_stock  ON argus_signal(wind_code, signal_date);
CREATE INDEX idx_sig_date   ON argus_signal(signal_date);
CREATE INDEX idx_sig_tf     ON argus_signal(timeframe);
CREATE INDEX idx_sig_type   ON argus_signal(signal_type);
CREATE INDEX idx_sig_status ON argus_signal(status);
CREATE INDEX idx_sig_score  ON argus_signal(bayesian_score DESC);
```

### 3.4 argus_consensus

```sql
CREATE TABLE argus_consensus (
    consensus_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    wind_code       TEXT NOT NULL,
    stock_name      TEXT,
    detection_date  TEXT NOT NULL
        CHECK (detection_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    consensus_type  TEXT NOT NULL
        CHECK (consensus_type IN ('BUY_CONSENSUS','SELL_CONSENSUS','SECTOR_CONSENSUS','DIRECTION_ALIGNED')),
    product_ids     TEXT NOT NULL,       -- JSON array
    product_count   INTEGER NOT NULL CHECK (product_count >= 2),
    strength        REAL NOT NULL CHECK (strength >= 0 AND strength <= 1),
    avg_credibility REAL,
    high_conviction INTEGER NOT NULL DEFAULT 0 CHECK (high_conviction IN (0,1)),
    window_days     INTEGER NOT NULL DEFAULT 5,
    sector_sw1      TEXT,
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE','CONFIRMED','EXPIRED','INVALIDATED')),
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_cons_stock ON argus_consensus(wind_code, detection_date);
CREATE INDEX idx_cons_date  ON argus_consensus(detection_date);
CREATE INDEX idx_cons_type  ON argus_consensus(consensus_type);
```

### 3.5 argus_darwin_event

```sql
-- 达尔文时刻: 行业回调时高/低信誉产品分歧 (V1高级分析)
CREATE TABLE argus_darwin_event (
    darwin_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_code     TEXT NOT NULL,       -- 申万一级行业代码
    sector_name     TEXT NOT NULL,
    trigger_date    TEXT NOT NULL
        CHECK (trigger_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    drawdown_20d    REAL NOT NULL,       -- 行业20日跌幅 (%, 负数)
    market_drawdown REAL,                -- 同期沪深300跌幅
    is_systemic     INTEGER NOT NULL DEFAULT 0 CHECK (is_systemic IN (0,1)),
    strong_products TEXT NOT NULL,        -- JSON: 高信誉产品行为
    weak_products   TEXT NOT NULL,        -- JSON: 低信誉产品行为
    strong_net_action TEXT NOT NULL CHECK (strong_net_action IN ('ADD','HOLD','REDUCE')),
    weak_net_action TEXT NOT NULL CHECK (weak_net_action IN ('ADD','HOLD','REDUCE')),
    divergence_strength REAL NOT NULL CHECK (divergence_strength >= 0 AND divergence_strength <= 1),
    return_30d      REAL,                -- 触发后30/60/90日行业收益率
    return_60d      REAL,
    return_90d      REAL,
    outcome_tag     TEXT CHECK (outcome_tag IS NULL OR outcome_tag IN ('CONFIRMED','FAILED','PENDING')),
    confidence      REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_darwin_sector ON argus_darwin_event(sector_code, trigger_date);
CREATE INDEX idx_darwin_date   ON argus_darwin_event(trigger_date);
CREATE INDEX idx_darwin_out    ON argus_darwin_event(outcome_tag);
```

### 3.6 argus_consensus_direction

```sql
-- 共识方向引擎: 景气度方向仪 + 信念偏移雷达 (V1高级分析)
CREATE TABLE argus_consensus_direction (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    calc_date       TEXT NOT NULL
        CHECK (calc_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    -- 景气度方向仪
    cyclical_weight  REAL,               -- 周期组总权重 (%)
    defensive_weight REAL,               -- 防御组总权重 (%)
    prosperity_delta REAL,               -- = cyclical - defensive (pp)
    prosperity_delta_30d REAL,           -- 30日滚动均值
    prosperity_signal TEXT CHECK (prosperity_signal IS NULL OR
        prosperity_signal IN ('BULLISH','NEUTRAL','DEFENSIVE')),
    -- 信念偏移雷达
    sector_conviction TEXT,              -- JSON: 行业级信念变化
    top_rising_sectors TEXT,             -- JSON: 信念上升Top-3
    top_falling_sectors TEXT,            -- JSON: 信念下降Top-3
    baseline_window INTEGER NOT NULL DEFAULT 120, -- 基准窗口 (~6个月, Kahneman建议)
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_dir_date   ON argus_consensus_direction(calc_date);
CREATE INDEX idx_dir_signal ON argus_consensus_direction(prosperity_signal);
```

---

## 4 第三层 Decision (2表) {#ARGUS-03:decision}

### 4.1 argus_stock_pool

```sql
CREATE TABLE argus_stock_pool (
    pool_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    wind_code       TEXT NOT NULL UNIQUE, -- 同一股票同时只在一个区
    stock_name      TEXT NOT NULL,
    pool_zone       TEXT NOT NULL CHECK (pool_zone IN ('SCAN','WATCH','CANDIDATE','CONVICTION')),
    -- 评分
    composite_score REAL NOT NULL CHECK (composite_score >= 0 AND composite_score <= 1),
    bayesian_posterior REAL,
    -- 来源
    contributing_products TEXT,           -- JSON array
    product_count   INTEGER NOT NULL DEFAULT 1,
    consensus_strength REAL,
    -- 时间
    entry_date      TEXT NOT NULL,       -- 入池日期
    zone_entry_date TEXT NOT NULL,       -- 进入当前区域日期
    last_signal_date TEXT,
    -- Munger Checklist (V1: 3/5项)
    checklist_darwin     INTEGER NOT NULL DEFAULT 0 CHECK (checklist_darwin IN (0,1)),
    checklist_prosperity INTEGER NOT NULL DEFAULT 0 CHECK (checklist_prosperity IN (0,1)),
    checklist_conviction INTEGER NOT NULL DEFAULT 0 CHECK (checklist_conviction IN (0,1)),
    checklist_score      INTEGER NOT NULL DEFAULT 0 CHECK (checklist_score >= 0 AND checklist_score <= 5),
    -- 其他
    direction       TEXT NOT NULL DEFAULT 'BULLISH' CHECK (direction IN ('BULLISH','BEARISH')),
    sector_sw1      TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_pool_zone   ON argus_stock_pool(pool_zone);
CREATE INDEX idx_pool_score  ON argus_stock_pool(composite_score DESC);
CREATE INDEX idx_pool_sector ON argus_stock_pool(sector_sw1);
```

### 4.2 argus_stock_pool_history

```sql
CREATE TABLE argus_stock_pool_history (
    history_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    wind_code       TEXT NOT NULL,
    stock_name      TEXT,
    action          TEXT NOT NULL CHECK (action IN (
        'ENTER','PROMOTE','DEMOTE','ARCHIVE',
        'SCORE_UPDATE','ZONE_CHANGE','CHECKLIST_UPDATE',
        'DAILY_REFRESH','WEEKLY_CALIBRATE')),
    from_zone       TEXT,
    to_zone         TEXT,
    old_score       REAL,
    new_score       REAL,
    trigger_reason  TEXT,
    action_date     TEXT NOT NULL
        CHECK (action_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_ph_stock  ON argus_stock_pool_history(wind_code, action_date);
CREATE INDEX idx_ph_date   ON argus_stock_pool_history(action_date);
CREATE INDEX idx_ph_action ON argus_stock_pool_history(action);
```

---

## 5 备用表 (1表) {#ARGUS-03:fallback}

```sql
-- 高频估算: 日度全持仓不可用时的备用路径 (V2降级, 正常流程不需要)
CREATE TABLE argus_hf_estimate (
    estimate_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code    TEXT NOT NULL,
    wind_code       TEXT NOT NULL,
    estimate_date   TEXT NOT NULL
        CHECK (estimate_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    method          TEXT NOT NULL CHECK (method IN ('LASSO','KALMAN','HEURISTIC')),
    estimated_weight REAL,
    actual_weight   REAL,
    error_pct       REAL,
    confidence      REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_code) REFERENCES raw_product_info(product_code)
);
CREATE INDEX idx_hf_prod ON argus_hf_estimate(product_code, estimate_date);
CREATE UNIQUE INDEX idx_hf_uniq ON argus_hf_estimate(product_code, wind_code, estimate_date, method);
```

---

## 6 触发器 + 索引 {#ARGUS-03:triggers}

### 6.1 Raw层不变性触发器 (DS_01合规)

```sql
-- raw_daily_trade: 禁止UPDATE
CREATE TRIGGER trg_raw_trade_no_update BEFORE UPDATE ON raw_daily_trade
BEGIN SELECT RAISE(ABORT, '[DS_01] Cannot UPDATE raw_daily_trade'); END;

-- raw_daily_trade: 禁止DELETE (1年内)
CREATE TRIGGER trg_raw_trade_no_delete BEFORE DELETE ON raw_daily_trade
WHEN OLD.created_at > datetime('now', '-365 days')
BEGIN SELECT RAISE(ABORT, '[DS_01] Cannot DELETE raw data < 1 year'); END;

-- raw_daily_holding: 禁止UPDATE
CREATE TRIGGER trg_raw_hold_no_update BEFORE UPDATE ON raw_daily_holding
BEGIN SELECT RAISE(ABORT, '[DS_01] Cannot UPDATE raw_daily_holding'); END;

-- raw_daily_holding: 禁止DELETE (1年内)
CREATE TRIGGER trg_raw_hold_no_delete BEFORE DELETE ON raw_daily_holding
WHEN OLD.created_at > datetime('now', '-365 days')
BEGIN SELECT RAISE(ABORT, '[DS_01] Cannot DELETE raw data < 1 year'); END;

-- raw_product_nav: 禁止UPDATE
CREATE TRIGGER trg_raw_nav_no_update BEFORE UPDATE ON raw_product_nav
BEGIN SELECT RAISE(ABORT, '[DS_01] Cannot UPDATE raw_product_nav'); END;

-- raw_product_nav: 禁止DELETE (1年内)
CREATE TRIGGER trg_raw_nav_no_delete BEFORE DELETE ON raw_product_nav
WHEN OLD.created_at > datetime('now', '-365 days')
BEGIN SELECT RAISE(ABORT, '[DS_01] Cannot DELETE raw data < 1 year'); END;
```

### 6.2 池变更审计触发器

```sql
-- argus_stock_pool UPDATE -> 自动记录到history
CREATE TRIGGER trg_pool_audit_update AFTER UPDATE ON argus_stock_pool
WHEN OLD.pool_zone != NEW.pool_zone OR OLD.composite_score != NEW.composite_score
BEGIN
    INSERT INTO argus_stock_pool_history
        (wind_code, stock_name, action, from_zone, to_zone, old_score, new_score, trigger_reason, action_date)
    VALUES (NEW.wind_code, NEW.stock_name,
        CASE WHEN OLD.pool_zone != NEW.pool_zone THEN 'ZONE_CHANGE' ELSE 'SCORE_UPDATE' END,
        OLD.pool_zone, NEW.pool_zone, OLD.composite_score, NEW.composite_score,
        'Auto audit trigger', date('now'));
END;

-- argus_stock_pool DELETE -> 归档审计
CREATE TRIGGER trg_pool_audit_delete BEFORE DELETE ON argus_stock_pool
BEGIN
    INSERT INTO argus_stock_pool_history
        (wind_code, stock_name, action, from_zone, old_score, trigger_reason, action_date)
    VALUES (OLD.wind_code, OLD.stock_name, 'ARCHIVE', OLD.pool_zone,
        OLD.composite_score, 'Removed from pool', date('now'));
END;
```

### 6.3 updated_at自动更新触发器

```sql
CREATE TRIGGER trg_profile_ts AFTER UPDATE ON argus_product_profile
BEGIN UPDATE argus_product_profile SET updated_at=datetime('now') WHERE product_code=NEW.product_code; END;

CREATE TRIGGER trg_signal_ts AFTER UPDATE ON argus_signal
BEGIN UPDATE argus_signal SET updated_at=datetime('now') WHERE signal_id=NEW.signal_id; END;

CREATE TRIGGER trg_pool_ts AFTER UPDATE ON argus_stock_pool
BEGIN UPDATE argus_stock_pool SET updated_at=datetime('now') WHERE pool_id=NEW.pool_id; END;

CREATE TRIGGER trg_darwin_ts AFTER UPDATE ON argus_darwin_event
BEGIN UPDATE argus_darwin_event SET updated_at=datetime('now') WHERE darwin_id=NEW.darwin_id; END;

CREATE TRIGGER trg_prodinfo_ts AFTER UPDATE ON raw_product_info
BEGIN UPDATE raw_product_info SET updated_at=datetime('now') WHERE product_code=NEW.product_code; END;
```

### 6.4 索引汇总

| 表 | 索引数 | 关键索引 |
|:--|:--:|:--|
| raw_daily_trade | 4 | product+date, stock+date, date, type |
| raw_daily_holding | 4 | product+date, stock+date, date, UNIQUE(prod+stock+date) |
| raw_product_nav | 2 | product+date, UNIQUE(prod+date) |
| argus_rebalancing_event | 4 | product+date, stock+date, type, date |
| argus_signal | 6 | stock+date, date, tf, type, status, score DESC |
| argus_consensus | 3 | stock+date, date, type |
| argus_darwin_event | 3 | sector+date, date, outcome |
| argus_consensus_direction | 2 | date, signal |
| argus_stock_pool | 3 | zone, score DESC, sector |
| argus_stock_pool_history | 3 | stock+date, date, action |
| argus_hf_estimate | 2 | product+date, UNIQUE(prod+stock+date+method) |
| **合计** | **36** | 含6个UNIQUE索引 |

---

## 7 DuckDB视图 (Day 2) {#ARGUS-03:duckdb}

> Day 2引入DuckDB后创建。Day 1可在SQLite中用同名VIEW (ANSI SQL兼容)。
> 前提: `ATTACH 'argus.db' AS argus (TYPE sqlite, READ_ONLY)`

| 视图 | 用途 | 核心窗口/聚合 |
|:--|:--|:--|
| `v_product_rolling_accuracy` | 产品滚动胜率 (60信号窗口) | ROWS 59 PRECEDING, PARTITION BY product |
| `v_signal_bayesian_fusion` | 多时间框架融合视图 | GROUP BY stock+date, PIVOT on timeframe |
| `v_consensus_heatmap` | 行业x产品共识热力图 | GROUP BY sector+product+date, SUM买卖事件 |
| `v_darwin_event_backtest` | 达尔文事件回测统计 | 按outcome_tag和return分类 |
| `v_direction_timeseries` | 景气度方向时序 | 60日滚动AVG(prosperity_delta) |
| `v_opportunity_matrix` | 机会矩阵 (Munger Checklist) | CANDIDATE+CONVICTION区, ORDER BY checklist DESC |

```sql
-- 示例: v_product_rolling_accuracy
CREATE VIEW v_product_rolling_accuracy AS
SELECT contributing_products, signal_date, timeframe,
    COUNT(*) OVER w AS window_total,
    SUM(CASE WHEN outcome_tag='CORRECT' THEN 1 ELSE 0 END) OVER w AS window_correct
FROM argus_signal WHERE outcome_tag IS NOT NULL
WINDOW w AS (PARTITION BY contributing_products ORDER BY signal_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW);

-- 示例: v_signal_bayesian_fusion
CREATE VIEW v_signal_bayesian_fusion AS
SELECT wind_code, stock_name, signal_date,
    MAX(CASE WHEN timeframe='FAST' THEN bayesian_score END) AS fast_score,
    MAX(CASE WHEN timeframe='MEDIUM' THEN bayesian_score END) AS medium_score,
    MAX(CASE WHEN timeframe='SLOW' THEN bayesian_score END) AS slow_score,
    AVG(bayesian_score) AS avg_score, COUNT(DISTINCT timeframe) AS tf_count
FROM argus_signal WHERE status='ACTIVE'
GROUP BY wind_code, stock_name, signal_date;

-- 示例: v_opportunity_matrix (Munger Checklist)
CREATE VIEW v_opportunity_matrix AS
SELECT wind_code, stock_name, pool_zone, composite_score,
    checklist_darwin, checklist_prosperity, checklist_conviction, checklist_score,
    product_count, JULIANDAY('now') - JULIANDAY(zone_entry_date) AS days_in_zone
FROM argus_stock_pool WHERE pool_zone IN ('CANDIDATE','CONVICTION')
ORDER BY checklist_score DESC, composite_score DESC;
```

---

**[存证]**
ARGUS-03 v2.0.0-draft | 2026-04-12
参考来源: Expert Panel WG1 (三层架构+表分配) + WG2 (投资字段) + Advanced Features (Darwin+Consensus Direction) + DS_01审计铁律
表统计: Raw 4 + Processed 6 + Decision 2 + Fallback 1 = 13表
触发器: 6 Raw不变性 + 2 池审计 + 5 updated_at = 13个
索引: 36个 (含6 UNIQUE)
DuckDB视图: 6个 (Day 2, ANSI SQL兼容)
SOP完成: 启动-热场-参考-撰写-复查-收尾
