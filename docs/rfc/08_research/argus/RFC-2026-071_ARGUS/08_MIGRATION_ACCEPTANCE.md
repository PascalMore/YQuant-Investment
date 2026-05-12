---
file_id: ARGUS-08
title: "MVP优先实施计划与验收标准 (Standalone Edition)"
title_en: "MVP Phased Implementation & Acceptance Criteria (Standalone Edition)"
rfc_id: RFC-2026-071
doc_status: AMENDED
approval_status: ACCEPTED
impl_status: PHASE_1_DRAFT
version: "3.0.0"
created: "2026-04-12"
last_updated: "2026-04-22"
drafter: "Internal Review Board"
owner: "Internal Review Board"
depends_on:
  - "ARGUS-04 (架构与数据库设计 v2.0)"
  - "ARGUS-05 (信号引擎与评分 v2.0)"
  - "ARGUS-06 (池管理与Web界面 v2.0)"
  - "ARGUS-07 (影响分析与替代方案 v2.0)"
  - "ARGUS-APP-A (参数注册表 v2.0)"
  - "EXPERT_PANEL_WG3_WG4_WG5.md (WG3 MVP定义 + 芒格简化)"
  - "ADVANCED_FEATURES_DISCUSSION.md (达尔文时刻 + 共识方向引擎)"
supersedes: "ARGUS-06 v0.1.0 (archived to _archive_v1/06_MIGRATION_ACCEPTANCE.md)"
amendment_level: L2
---

# 08 MVP优先实施计划与验收标准 (Standalone Edition) {#ARGUS-08:root}

# MVP Phased Implementation & Acceptance Criteria (Standalone Edition)

> **V2.0 核心变更**: V1.0计划为7阶段17周 (Empire子模块架构)。V2.0遵循芒格简化原则和WG3 MVP定义, 重构为6阶段12周 + 2周纸上交易 = 14周。每阶段聚焦一个可验证的用户价值。
>
> **V2.0 Key Change**: V1.0 was 7 phases / 17 weeks for Empire submodule. V2.0 follows Munger's simplification: 6 phases / 12 weeks + 2-week paper trading = 14 weeks total. Each phase delivers one verifiable user value.

---

## S0 v3.0 beta-light Phase 1 重写 (2026-04-22, <sess>) {#ARGUS-08:v3-phase1}

> **v3.0 仅重写 Phase 1**. Phase 2-6 全部 DEFERRED 至 rearm 触发 (n≥50 条产品行为事件 或 2026-07-22).
> 原 v2.0.1 Phase 1-6 12+2 周计划保留作 Phase 2+ 参考, 不直接执行.

### S0.1 Phase 1 (v3.0 beta-light) 目标

**User Story**: "user 在 Claude 桌面客户端触发 SQL INSERT 模板, 3 Raw 表结构化入库, 首次 mock SM001 3 日冒烟 PASS."

**节奏**: automated workflow 单 session ~3-4h 闭环 (继承 <sess>/107 precedent).

### S0.2 Phase 1 交付物清单

| # | 产出 | 位置 | 来源 (<gov-ref>) |
|:-:|:--|:--|:--|
| 5c | `schema_argus_raw_mvp.sql` — 3 Raw 表 + 索引 + 触发器 + SM00N CHECK | `argus/schema/` | C-2 + C-4 |
| 5d | `argus_insert_templates.md` — 3 套 SQL INSERT 模板 (product_info / trade / holding) | `argus/templates/` | C-3 + C-4 |
| 5e | `argus_insert.py` — R11 两段式 CLI (propose + confirm_r11 + mock + selftest) | `argus/tools/` | C-3 + C-6 |
| 5f | `mock_smoke_SM001.md` — 冒烟报告 (SM001 3 日 product_info + trade + holding) | `argus/tests/` | C-5 |

### S0.3 Phase 1 Gate Check (v3.0)

| # | 验收 | 验证方法 |
|:-:|:--|:--|
| AC-v3-01 | 3 Raw 表 schema migrate 成功 (sqlite3 `.schema` 输出完整) | SQLite CLI |
| AC-v3-02 | SM00N CHECK 约束生效 (SM0AB 非法 RAISE) | INSERT 非法 product_code 测试 |
| AC-v3-03 | DS_01 触发器生效 (UPDATE raw 表 RAISE ABORT) | 尝试 UPDATE raw_daily_trade |
| AC-v3-04 | R11 两段式生效 (propose 产 dict + confirm_r11 校验 require_r11=True 才 INSERT) | argus_insert.py selftest |
| AC-v3-05 | Mock 冒烟 SM001 3 日 PASS (INSERT 成功 + query 数据一致) | argus_insert.py --mock |
| AC-v3-06 | source_file 字段区分 MOCK_SMOKE_S108 vs OPERATOR_MANUAL | query 验证 |

### S0.4 rearm_trigger (Phase 2 启动条件)

| 条件 | 达成方式 |
|:--|:--|
| 数据量触发 | 累计产品行为事件 ≥50 条 (raw_daily_trade + raw_daily_holding 联合) |
| 时间触发 | 2026-07-22 (3 个月 calibration) |
| user 主动 | user R11 明示启动 Phase 2 (手动 rearm) |

**任一触发** → 启动 Phase 2 (Processed 6 表实装), 走 Forum B 新 DR/CL 开口.

### S0.5 DEFERRED 清单 (Phase 2-6 v2.0.1 原计划)

- Phase 2 (v2.0.1) Processed 层引擎 (贝叶斯信誉 + 调仓事件 + 信号 Feed) → **DEFERRED rearm**
- Phase 3 (v2.0.1) Decision 层池引擎 (四区) → **DEFERRED rearm**
- Phase 4 (v2.0.1) 达尔文时刻 + 共识方向 + 机会 Checklist → **DEFERRED rearm**
- Phase 5 (v2.0.1) 回测 + 产品 Win Rate + argus_recommendation JSON 导出 → **DEFERRED rearm**
- Phase 6 (v2.0.1) 2 周纸上交易 → **DEFERRED 至 Phase 5 ACTIVE 后**
- Web UI (FastAPI + /dashboard + /signals + /pool) → **DEFERRED** (v3.0 Phase 1 仅 CLI)
- Excel 批量 import → **DEFERRED** (user 手工录入够用, 若 user 未来要求 Excel 再 rearm)

---

## S1 MVP优先实施计划 (MVP Phased Plan) {#ARGUS-08:plan}

> ⚠️ **v3.0 修订**: 以下 S1 节全部为 v2.0.1 原计划, **Phase 1 已被 S0 重写**, Phase 2-6 DEFERRED 至 rearm. 保留作 Phase 2+ 启动时的参考.

### S1.0 总览 (Overview) {#ARGUS-08:overview}

| 阶段 / Phase | 周次 / Week | 用户价值 / User Value | 中文口号 | 核心交付 / Deliverables |
|:--:|:--:|:--|:--|:--|
| Phase 1 | W1-W2 | See the data | 能看到数据 | argus.db + CLI import + raw dashboard |
| Phase 2 | W3-W4 | Understand the data | 能理解数据 | Bayesian credibility + signal classification |
| Phase 3 | W5-W6 | Manage judgments | 能管理判断 | 4-zone pool + weekly workflow |
| Phase 4 | W7-W8 | See depth | 能看到深度 | Darwin moments + consensus direction |
| Phase 5 | W9-W10 | Assess quality | 能评估质量 | Backtest + product profiles + Empire export |
| Phase 6 | W11-W12 | Paper trading | 纸上交易 | 2-week live validation |

**总周期 / Total Duration**: 12周开发 + 2周纸上交易 = **14周**

> **对比V1.0**: V1.0为7阶段17周, 含4周Paper Trading。V2.0作为独立工具, 纸上交易缩短为2周 (不影响Empire, 风险更低)。

---

**首日初始化规则 (REV-034)**:
- 第一天导入数据时，raw_daily_holding建立基线快照
- 不生成argus_rebalancing_event（无"昨天"可对比）
- argus_product_profile初始化为默认值（credibility=0.5, Beta(2,2)）
- 从第二天起，正常生成调仓事件

### S1.1 Phase 1: 能看到数据 (Week 1-2) {#ARGUS-08:phase1}

**目标 / Goal**: 用户可以导入今天的Excel数据, 并在浏览器中看到原始信号。

**User Story**: "I import today's Excel file and see raw signals in my browser within 1 minute."

**交付物 / Deliverables**:

| 项目 / Item | 说明 / Description |
|:--|:--|
| argus.db SQLite数据库 | Raw层表: raw_daily_trade, raw_daily_holding, raw_daily_nav |
| CLI导入脚本 | `python import.py data/20260411.xlsx` -- 解析Excel, 校验, 写入Raw表 |
| Web upload界面 | FastAPI端点 `/upload` -- 文件上传+行数确认+入库 |
| 基础FastAPI应用 | main.py + Jinja2 + HTMX + Pico CSS |
| 原始信号Dashboard | `/dashboard` 页面 -- 展示当日导入数据摘要, 按产品/股票列表 |
| 数据校验 | 日期非空, 产品代码合法, 数值字段校验, 重复导入检测(idempotent) |
| 配置文件 | config.yaml -- 数据库路径, 端口, 基本参数 |

**技术栈确认 / Tech Stack** (WG3决议):

```
Python 3.11+ / FastAPI / Jinja2 / HTMX (CDN) / Pico CSS (CDN)
SQLite (WAL mode) / openpyxl / PyYAML / pytest + httpx
```

**Phase 1 Gate检查 / Gate Check**:

- [ ] `python import.py` 成功导入一天的Excel数据
- [ ] `python main.py` 启动后浏览器访问 localhost:8000 可看到Dashboard
- [ ] 重复导入同一天数据不产生重复记录
- [ ] 数据异常(空日期、非法代码)被检测并拒绝

---

### S1.2 Phase 2: 能理解数据 (Week 3-4) {#ARGUS-08:phase2}

**目标 / Goal**: Raw数据被处理为有意义的信号, 产品有信誉分, 买入被分类。

**User Story**: "I see classified signals (HEAVY/NORMAL/PROBE) with credibility scores for each product."

**交付物 / Deliverables**:

| 项目 / Item | 说明 / Description |
|:--|:--|
| Processed层表 | product_profile, rebalancing_event, signal |
| 产品画像引擎 | 质量门槛 (Sharpe/Calmar/MaxDD) + AUM分级 (S/A/B/C/U) |
| 贝叶斯信誉引擎 | Beta分布 (alpha, beta) + 信誉分计算 + 自适应衰减 (ARG-009/010) |
| 买入意图分类 | HEAVY (>2% AUM) / NORMAL (0.5-2%) / PROBE (<0.5%) / SEQUENTIAL (连续3+日) |
| 卖出质量三分类 | 止盈 / 止损 / 再平衡 (REV-009) |
| 信号Feed页面 | `/signals` -- 按bayesian_score降序, 支持方向/强度筛选 |
| 产品列表页面 | `/products` -- 信誉分, quality_pass状态, 最近交易 |

**关键算法 / Key Algorithms**:

- 信誉更新: `alpha += 1` (正确预测) / `beta += 1` (错误预测), `credibility = alpha / (alpha + beta)`
- 自适应衰减: `decay = base(0.97) - coeff(0.07) * min(vol / threshold, 1)`, 每90日无新证据触发
- 信誉冻结: 申赎率绝对值 > 30% (ARG-014) 时冻结信誉更新
- 后验饱和: posterior > 0.92 (ARG-012) 时新信号LR贡献递减

**Phase 2 Gate检查 / Gate Check**:

- [ ] 产品画像正确标记quality_pass (基于Sharpe/Calmar/MaxDD门槛)
- [ ] 贝叶斯信誉引擎: 输入100条模拟信号, 信誉分收敛方向正确
- [ ] 买入意图分类: HEAVY/NORMAL/PROBE与预期一致 (10个测试用例)
- [ ] 信号Feed页面正确展示分类后的信号列表

---

### S1.3 Phase 3: 能管理判断 (Week 5-6) {#ARGUS-08:phase3}

**目标 / Goal**: 四区股票池运行, 用户可以在周五执行完整的更新周期。

**User Story**: "Every Friday, I run the weekly update and see stocks promoted/demoted across zones."

**交付物 / Deliverables**:

| 项目 / Item | 说明 / Description |
|:--|:--|
| Decision层表 | stock_pool, pool_history |
| 四区池引擎 | SCAN -> WATCH -> CANDIDATE -> CONVICTION 晋升/降级/清除规则 |
| 池管理Web页面 | `/pool` -- 四区可视化, 每只股票的composite_score/入池日期/贡献产品 |
| 周五更新脚本 | `python weekly_update.py` -- 全量重算信号+池状态+生成变更报告 |
| 池变更审计 | pool_history表记录每次晋升/降级/清除, 含原因和操作时间 |
| 历史页面 | `/history` -- 信号历史+池变更记录时间线 |

**池规则摘要 / Pool Rules Summary**:

| 转换 / Transition | 条件 / Condition | 参数 / Params |
|:--|:--|:--|
| -> SCAN | 任何新信号出现 | 自动 |
| SCAN -> WATCH | bayesian >= 0.30, managers >= 2 | ARG-024, ARG-029 |
| WATCH -> CANDIDATE | bayesian >= 0.50, consensus >= 0.40 | ARG-025, ARG-040 |
| CANDIDATE -> CONVICTION | bayesian >= 0.70, managers >= 3, styles >= 2 | ARG-026, ARG-030, ARG-041 |
| WATCH退出 | bayesian < 0.20 | ARG-027 |
| CANDIDATE退出 | bayesian < 0.35 OR 连续2周下降 | ARG-028, ARG-042 |
| SCAN清除 | 30日无更新 | ARG-039 |

**Phase 3 Gate检查 / Gate Check**:

- [ ] 池引擎正确执行晋升/降级 (15个测试场景)
- [ ] 周五更新脚本端到端运行 < 5分钟
- [ ] 池变更审计: 每次变更有完整记录 (stock, from_zone, to_zone, reason, timestamp)
- [ ] `/pool` 页面正确展示四区, 支持按区域筛选

---

### S1.4 Phase 4: 能看到深度 (Week 7-8) {#ARGUS-08:phase4}

**目标 / Goal**: 检测达尔文时刻, 推断共识方向, 提供机会Checklist。

**User Story**: "I see Darwin events highlighted on the signal page, and a conviction checklist for each stock."

**交付物 / Deliverables**:

| 项目 / Item | 说明 / Description |
|:--|:--|
| 达尔文时刻检测器 | darwin_detector模块: 行业20日跌幅>=10% + 高信誉hold/add + 低信誉sell |
| 共识方向引擎 | 景气度方向仪 (cyclical_weight_delta) + 信念偏移雷达 (30日/60日权重变化) |
| 机会Checklist | Munger Checklist (3/5项V1版): 达尔文时刻 Y/N + 景气度对齐 Y/N + 信念增强 Y/N |
| 分析页面 | `/analysis` -- 达尔文事件列表 + 景气度方向仪 + 信念热力图 |
| 个股Checklist面板 | `/stocks/{code}` -- 每只CANDIDATE/CONVICTION股票的Checklist展示 |

**达尔文时刻检测条件 / Darwin Moment Detection**:

```
条件1 (触发): 申万一级行业指数20日跌幅 >= 10%
条件2 (分歧): credibility < 0.5的产品在该行业净卖出
              credibility > 0.7的产品在该行业净持平或净买入
条件3 (强度): 至少2个高信誉产品显示hold/add行为
过滤器 (芒格): 沪深300同期跌幅 > 8%时, 降低达尔文信号置信度 (系统性风险过滤)
```

**共识方向引擎 / Consensus Direction Engine**:

```
景气度方向:
  cyclical_group  = [有色金属, 钢铁, 化工, 机械, 汽车]
  defensive_group = [食品饮料, 医药, 公用事业, 银行]
  delta = SUM(cyclical权重变化) - SUM(defensive权重变化)
  信号: BULLISH (delta > +2pp) / NEUTRAL / DEFENSIVE (delta < -2pp)

信念偏移:
  per_sector: 30日权重变化 + 60日权重变化
  加速度: 正向加速 = conviction rising, 负向加速 = conviction collapsing
  基准: 6个月滚动均值 (Kahneman建议, 避免锚定效应)
```

**Phase 4 Gate检查 / Gate Check**:

- [ ] 达尔文检测器: 在历史数据上检测到至少1个已知达尔文事件
- [ ] 达尔文误报率: 系统性下跌期间达尔文信号被正确降权
- [ ] 景气度方向: cyclical_weight_delta计算结果与手工验算一致
- [ ] Checklist面板: CANDIDATE/CONVICTION股票均有3项Checklist展示

---

### S1.5 Phase 5: 能评估质量 (Week 9-10) {#ARGUS-08:phase5}

**目标 / Goal**: 回测验证信号准确性, 产品有Win Rate, Empire可接收推荐。

**User Story**: "I see backtest accuracy for signals and products, and Empire receives JSON recommendations."

**交付物 / Deliverables**:

| 项目 / Item | 说明 / Description |
|:--|:--|
| 回测精度追踪 | 每条信号发出后30/60/90日, 自动计算超额收益, 更新accuracy |
| 产品Win Rate | 每个产品的信号正确率统计, 按方向(买/卖)/时间框架(FAST/MEDIUM/SLOW)拆分 |
| 产品详情页 | `/products/{id}` -- 持仓变动时间线, 信誉历史, Win Rate |
| 个股详情页 | `/stocks/{code}` -- 信号历史, 贡献产品, 池状态变更, Checklist |
| Empire JSON导出 | `output/argus_recommendation_YYYYMMDD.json` -- CONVICTION区股票列表+分数 |
| REST API端点 | `GET /api/v1/pool/conviction` -- 备用查询接口 |

**JSON导出格式 / Export Format**:

```json
{
  "date": "2026-06-15",
  "version": "2.0.0",
  "conviction_pool": [
    {
      "stock_code": "603799",
      "stock_name": "华友钴业",
      "composite_score": 0.78,
      "bayesian_score": 0.82,
      "contributing_products": 4,
      "direction": "BUY",
      "zone_since": "2026-05-20",
      "checklist_score": "4/5",
      "darwin_flag": true
    }
  ],
  "alerts": [],
  "meta": {
    "total_pool_size": {"SCAN": 45, "WATCH": 18, "CANDIDATE": 8, "CONVICTION": 3},
    "data_freshness": "2026-06-14"
  }
}
```

**Phase 5 Gate检查 / Gate Check**:

- [ ] 回测引擎: 对历史信号的30日超额收益计算正确
- [ ] 产品Win Rate: 至少5个产品有有效统计数据
- [ ] JSON导出: 文件格式正确, 可被Claude在session中解析
- [ ] REST API: `GET /api/v1/pool/conviction` 返回正确数据

---

### S1.6 Phase 6: 纸上交易 (Week 11-12) {#ARGUS-08:phase6}

**目标 / Goal**: 2周实际运行验证系统稳定性和信号质量。

**User Story**: "The system runs for 2 consecutive weeks with zero failures, and signal quality makes sense."

**验证内容 / Validation Scope**:

| 验证项 / Item | 标准 / Standard | 说明 / Notes |
|:--|:--|:--|
| 每日导入 | 10个交易日零失败 | 每天早上导入Excel, 系统自动完成全链路处理 |
| 周五更新 | 2次周五更新零失败 | 池状态变更合理, 审计日志完整 |
| Dashboard可用性 | 99%可用 (仅允许1次计划内重启) | 浏览器随时可访问localhost:8000 |
| 信号合理性 | 人工抽查10条信号, 方向和强度合理 | 不要求精确预测, 要求方向不荒谬 |
| 告警触发 | 至少1次数据异常告警正确触发 | 如果2周内无自然异常, 人工注入一条异常数据验证 |
| JSON导出 | 2次JSON文件生成正确 | Claude可在session中读取并解读 |
| Checklist有效 | CONVICTION区每只股票Checklist可读 | 3项Y/N判断与手工判断一致 |

**纸上交易说明**: 此阶段为2周而非V1.0的4周, 理由:

- ARGUS是独立工具, 不影响Empire任何操作
- 2周 = 10个交易日, 足以覆盖2次周五更新周期
- 风险极低: 最坏情况 = 删除argus.db + 停止进程

**Phase 6 Gate检查 / Gate Check**:

- [ ] 连续10个交易日零导入失败
- [ ] 连续2个周五更新零处理失败
- [ ] 人工信号抽查: 10条中>=8条方向合理
- [ ] JSON导出被Claude成功解读2次
- [ ] 无未处理的ERROR级日志

---

## S2 数据迁移 (Data Migration) {#ARGUS-08:migration}

### S2.1 V8.1 SMART_MONEY数据迁移 {#ARGUS-08:migration-v81}

Empire V8.1中存在SMART_MONEY相关的event_log条目。这些历史数据可以为ARGUS提供初始训练集。

**迁移范围 / Migration Scope**:

| 数据源 / Source | 目标表 / Target | 迁移方式 / Method |
|:--|:--|:--|
| V8.1 event_log WHERE event_type LIKE 'SMART_MONEY%' | raw_daily_trade | Python脚本一次性导入 |
| V8.1 stock_pool WHERE source='SMART_MONEY' | 仅作参考, 不直接导入 | Claude手动比对 |

**迁移脚本 / Migration Script**:

```
python migrate_v81.py --source empire_data.db --target argus.db --dry-run
python migrate_v81.py --source empire_data.db --target argus.db --execute
```

**迁移规则 / Migration Rules**:

1. 仅迁移event_log中的交易记录, 不迁移池状态 (池应由ARGUS引擎重新计算)
2. 迁移后的数据标记 `source_file = 'V81_MIGRATION'`, `import_timestamp = 迁移时间`
3. dry-run模式先输出统计报告: 预计迁移行数、日期范围、涉及产品
4. 迁移不可逆但可回滚: `DELETE FROM raw_daily_trade WHERE source_file = 'V81_MIGRATION'`

### S2.2 迁移风险 (Migration Risk) {#ARGUS-08:migration-risk}

| 风险 / Risk | 缓解 / Mitigation |
|:--|:--|
| V8.1数据格式与ARGUS不兼容 | 迁移脚本做字段映射+校验, dry-run先验证 |
| 历史数据不完整 (缺少某些天) | 缺失日标记GAP, 不影响ARGUS引擎运行 |
| 迁移后产品ID不匹配 | 建立V8.1产品ID -> ARGUS产品ID映射表 |

---

## S3 验收标准 (Acceptance Criteria) {#ARGUS-08:acceptance}

### S3.1 验收标准总表 (AC Registry) {#ARGUS-08:ac-table}

| AC编号 | Phase | 验收标准 / Acceptance Criteria | 验证方法 / Method | 优先级 |
|:--:|:--:|:--|:--|:--:|
| AC-01 | P1 | CLI导入脚本可解析标准Excel并写入raw_daily_trade | 导入测试文件, 检查DB行数 | P0 |
| AC-02 | P1 | Web upload界面可上传Excel并确认入库 | 手动测试upload流程 | P0 |
| AC-03 | P1 | 重复导入同一天数据不产生重复记录 (idempotent) | 导入同一文件2次, 检查行数不变 | P0 |
| AC-04 | P1 | 数据异常检测: 空日期/非法代码/文本数值被拒绝 | 导入异常测试文件 | P0 |
| AC-05 | P1 | Dashboard页面在导入后显示当日数据摘要 | 浏览器访问localhost:8000 | P0 |
| AC-06 | P2 | 产品质量门槛正确标记quality_pass | 手工计算5个产品的Sharpe/Calmar, 与系统结果比对 | P0 |
| AC-07 | P2 | 贝叶斯信誉: 100条模拟信号后credibility收敛方向正确 | 单元测试: 正确信号增加credibility, 错误信号降低 | P0 |
| AC-08 | P2 | 买入意图分类: HEAVY/NORMAL/PROBE/SEQUENTIAL正确 | 10个测试用例逐一验证 | P0 |
| AC-09 | P2 | 信号Feed页面按bayesian_score降序展示 | 浏览器验证排序 | P1 |
| AC-10 | P3 | 池引擎: SCAN->WATCH->CANDIDATE->CONVICTION晋升正确 | 15个测试场景覆盖所有转换路径 | P0 |
| AC-11 | P3 | 池引擎: 降级和清除规则正确执行 | 测试bayesian低于阈值时降级 | P0 |
| AC-12 | P3 | 周五更新脚本端到端 < 5分钟 | 计时执行weekly_update.py | P1 |
| AC-13 | P3 | 池变更审计: 每次变更有完整记录 | 查询pool_history表 | P0 |
| AC-14 | P4 | 达尔文检测器: 历史数据上检测到已知事件 | 回测验证 | P1 |
| AC-15 | P4 | 系统性风险过滤: 沪深300跌>8%时达尔文信号降权 | 测试用例 | P1 |
| AC-16 | P4 | 景气度方向计算与手工验算一致 | 对比5个交易日的计算结果 | P1 |
| AC-17 | P5 | 回测精度: 信号发出后30日超额收益计算正确 | 手工计算5条信号的30日回报 | P1 |
| AC-18 | P5 | JSON导出: 文件格式正确, 包含required字段 | JSON schema validation | P0 |
| AC-19 | P6 | 纸上交易: 连续10交易日零导入失败 | 运行日志检查 | P0 |
| AC-20 | P6 | 纸上交易: 连续2个周五更新零处理失败 | 运行日志检查 | P0 |

### S3.2 优先级定义 (Priority Definitions) {#ARGUS-08:priority}

| 优先级 / Priority | 定义 / Definition | 阻塞性 / Blocking |
|:--|:--|:--:|
| P0 | 必须通过, 否则不进入下一Phase | YES |
| P1 | 应当通过, 允许带条件进入下一Phase (需记录TODO) | NO |

---

## S4 回滚计划 (Rollback Plan) {#ARGUS-08:rollback}

### S4.1 回滚策略 (Rollback Strategy) {#ARGUS-08:rollback-strategy}

ARGUS V2.0作为独立系统, 回滚极其简单:

As a standalone system, ARGUS V2.0 rollback is trivially simple:

```
Step 1: 停止ARGUS FastAPI进程
  > Ctrl+C (或关闭terminal窗口)

Step 2: 删除argus.db (如果需要完全回滚)
  > del argus.db

Step 3: 完成
  > Empire不受任何影响
  > 无需修改Empire任何配置
  > 无需回滚Empire任何数据
```

### S4.2 回滚影响矩阵 (Rollback Impact) {#ARGUS-08:rollback-impact}

| 回滚操作 / Rollback Action | Empire影响 / Empire Impact | 数据影响 / Data Impact | 可逆性 / Reversibility |
|:--|:--|:--|:--|
| 停止ARGUS进程 | 零影响 | ARGUS数据保留在argus.db中 | 随时可重启 |
| 删除argus.db | 零影响 | ARGUS历史数据丢失 | 不可逆, 但可从备份恢复 |
| 删除ARGUS代码目录 | 零影响 | 代码可从git重新clone | 完全可逆 |
| 删除output/*.json | 零影响 | 推荐历史丢失 | 不可逆, 仅影响历史查看 |

### S4.3 按Phase回滚 (Per-Phase Rollback) {#ARGUS-08:rollback-phase}

| Phase | 回滚触发条件 / Trigger | 回滚动作 / Action | 影响范围 / Scope |
|:--|:--|:--|:--|
| Phase 1 | Excel解析持续失败 | 停止进程, 排查数据格式 | 仅ARGUS |
| Phase 2 | 贝叶斯引擎计算结果荒谬 | 回退到Phase 1代码, 重新设计引擎 | 仅ARGUS |
| Phase 3 | 池规则逻辑错误 | 清空pool/pool_history表, 重新计算 | 仅ARGUS Decision层 |
| Phase 4 | 达尔文检测误报率>50% | 禁用darwin_detector, Phase 5暂跳过 | 仅高级分析功能 |
| Phase 5 | 回测显示信号无预测力 | 调整参数或承认null hypothesis, 系统降级为"观察工具" | 系统定位调整 |
| Phase 6 | 纸上交易不达标 | 延长纸上交易或回退到对应Phase修复 | 仅延迟上线时间 |

> **关键保证 / Key Guarantee**: 任何Phase的任何回滚操作, 对Empire的影响均为**零**。这是V2.0独立架构的根本优势。

---

## Attestation {#ARGUS-08:attestation}

本文档由Internal Review Board基于以下材料编制:

This document was compiled by the Empire Decision Committee based on:

- EXPERT_PANEL_WG3_WG4_WG5.md: WG3 MVP定义 (6核心功能), 芒格简化原则
- ADVANCED_FEATURES_DISCUSSION.md: 达尔文时刻(INCLUDE_V1) + 共识方向引擎(INCLUDE_V1景气度+信念偏移)
- _archive_v1/06_MIGRATION_ACCEPTANCE.md: V1.0迁移计划 (已归档, 供对比)
- ARGUS-APP-A v2.0: 简化参数注册表 (~50参数)
- ARGUS-APP-B v2.0: 更新风险登记簿

V1.0的7阶段17周计划 (含DuckDB验证、SENTINEL集成、IC流程升级、4周Paper Trading) 已归档。V2.0聚焦独立系统的MVP交付, 以用户价值为阶段划分标准。

---

## Changelog {#ARGUS-08:changelog}

| 版本 / Version | 日期 / Date | 作者 / Author | 变更说明 / Changes |
|:--|:--|:--|:--|
| 0.1.0-draft | 2026-04-12 | Claude (SESSION-008) | V1.0初稿: 7阶段17周Empire子模块迁移计划 (已归档) |
| 2.0.0-draft | 2026-04-12 | Internal Review Board | V2.0重写: 6阶段12+2周独立MVP计划; 20项验收标准; 零影响回滚; 达尔文+共识方向纳入Phase 4 |

---

**[ATTESTATION]**
ARGUS-08 V2.0.0-draft | RFC-2026-071 | 2026-04-12
Based on: WG3 MVP (6 features) + Munger simplification + ADVANCED_FEATURES (Darwin V1 + Consensus V1)
SOP: init-context-draft-review-finalize
