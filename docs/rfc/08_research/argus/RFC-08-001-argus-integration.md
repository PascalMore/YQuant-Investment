# RFC-08-001：Argus 子项目接入 YQClaw RFC 体系规范
## 元数据（Metadata）
| 项 | 值|
|---|---|
| 状态 | Accepted |
| 作者 | PascalMao |
| 创建日期 | 2026-05-17 |
| 最后更新 | 2026-06-06 |
| 版本号 | V0.4 |
| 所属模块 | 08_research（投研分析） |
| 依赖RFC | RFC-00-001-yqclaw-investment-global-architecture |
| 替代RFC | 无 |
| 适配AI工具 | OpenClaw、Claude Code |
| 标签 | #argus #子模块 #research #机构资金 #YQClaw标准化 |

### 版本历史（Changelog）
| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.4 | 2026-06-06 | Phase 3：补充 ZoneRuleEngine 共享组件、YAML 统一阈值配置、Darwin/Bayesian/zone 分类计算顺序 | YQuant |
| V0.3 | 2026-05-18 | 数据存储方案：删除独立SQLite，改用MongoDB新建集合（08_research_argus_*）；目录结构更新为skills/data + skills/infra + skills/research/argus；删除db/目录相关描述 | YQuant |
| V0.2 | 2026-05-18 | 状态更新：Draft → Accepted，Phase 0 完成 | YQuant |
| V0.1 | 2026-05-17 | 初始创建，纳入 YQClaw RFC 体系方案 | PascalMao |

## 1. 执行摘要
本文档定义 Argus（机构智慧资金行为追踪系统）如何纳入 YQClaw Investment 统一 RFC 体系，包括 RFC 编号标准化、文档结构适配、模块定位明确、以及底层数据接口对接 TradingAgents MongoDB portfolio 表的修改方案。Argus 现有 RFC-2026-071 保持作为详细设计参考，新文档作为 YQClaw 体系的标准化 wrapper。

## 2. 背景与动机
### 2.1 Argus 现状
- Argus 是独立子系统，追踪对象为**基金产品**（product_code），非基金经理
- 数据频率：日度 T+1 全持仓 + 交易 + NAV
- 技术栈：Python 3.13+ / FastAPI / Jinja2 / HTMX / SQLite WAL
- 数据库：独立 `argus.db`（三层：Raw 4表 / Processed 6表 / Decision 2表 + Fallback 1表）
- 与主系统接口：JSON file exchange + Claude bridge（非直接数据库访问）
- **当前状态**：设计已批准（RFC-2026-071 APPROVED），代码本体尚未实装

### 2.2 纳入 YQClaw 的必要性
1. **RFC 生命周期统一**：Argus 独立 RFC-2026-071 与 YQClaw RFC 机制（Draft→Review→Accepted→Implemented）不兼容
2. **模块依赖标准化**：Argus 的 signal 输出需被 05_portfolio、06_strategy 等模块消费，需标准接口
3. **全局规范一致**：目录结构、代码风格、接口契约、日志规范需对齐 YQClaw 八大标准化体系
4. **AI 实装可追踪**：所有代码实装必须关联 RFC，无 RFC 不许实装

### 2.3 Argus 现有 RFC 结构分析
#### 2.3.1 文档结构（RFC-2026-071）
```
docs/rfc/08_research/argus/
├── README.md                          # Argus RFC 包说明
├── MANIFEST.sha256                    # 文件清单
├── sensitivity_audit.md               # 敏感信息审计
└── RFC-2026-071_ARGUS/
    ├── INDEX.md                       # 总控索引
    ├── 01_MOTIVATION.md               # 动机 + 系统身份
    ├── 02_ARCHITECTURE.md             # 独立架构 + 技术栈
    ├── 03_SCHEMA.md                   # 三层数据库 Schema（13 表）
    ├── 04_SIGNAL_SCORING.md           # 信号引擎 + 贝叶斯评分
    ├── 05_POOL_WEB.md                 # 四区股票池 + Web 界面
    ├── 06_ADVANCED_ANALYSIS.md       # 达尔文时刻 + 多产品共识 + 机会窗口
    ├── 07_IMPACT_ALTERNATIVES.md     # 影响评估 + 替代方案
    ├── 08_MIGRATION_ACCEPTANCE.md     # 迁移计划 + 验收标准
    └── APPENDIX/
        ├── A_PARAMETERS.md           # 参数注册表
        └── B_RISKS.md                # 风险登记册
```

#### 2.3.2 核心设计决策（来自 RFC-2026-071）
| 决策ID | 内容 | 理由 |
|---|---|---|
| D-001 | ARGUS 为独立系统，非 Empire 模块 | 独立数据源/生命周期，情报而非指令 |
| D-002 | 三层数据库：Raw → Processed → Decision | 数据不变性 + 可审计性 + 层间隔离 |
| D-005 | 按产品（product_code）跟踪，非按经理 | 实际数据源以产品为单位 |
| D-006 | 日度 T+1 全持仓，无需 HF 估算 | 每日已有完整快照，Kalman/Lasso 不必要 |
| D-008 | Code 做计算，Claude 做解读 | 确定性操作不依赖 LLM |

#### 2.3.3 核心设计原则（7条）
| ID | 原则 | 英文 |
|---|---|---|
| AR-P1 | 行为优先于方向 | Behavior over Direction |
| AR-P2 | 产品优先于股票 | Product over Stock |
| AR-P3 | 日更新周校准 | Daily Update, Weekly Calibration |
| AR-P4 | 贝叶斯怀疑 | Bayesian Skepticism |
| AR-P5 | 拥挤是引力 | Crowding is Gravity |
| AR-P6 | 诚实信号审计 | Honest Signal Audit |
| AR-P7 | 数据源分层信任 | Data Source Trust Hierarchy |

## 3. 目标与非目标
### 3.1 必须目标（Must-Have）
- [ ] Argus RFC 纳入 YQClaw 统一 RFC 体系，完成编号映射与状态对齐
- [ ] Argus 输出信号（argus_signal）格式符合 YQClaw 全局信号标准
- [ ] Argus 与 portfolio/strategy/trading 模块的接口标准化
- [ ] Argus 底层数据接口对接方案确定（方案 B：SQLite + 接口层）

### 3.2 非目标（Out of Scope）
- [ ] 不修改 Argus 原有 RFC-2026-071 详细设计文档内容
- [ ] 不强制将 argus.db 迁移至 MongoDB（保持独立 SQLite）
- [ ] 不实装 Argus 代码本体（仅完成架构层面接入方案）

## 4. 详细设计
### 4.1 业务流程（Flow）

#### 4.1.1 Argus 核心业务流程
```
数据入口（ETF持仓披露/FOF穿透）
    ↓
Raw Layer 接收（日度 T+1）
    ↓
Processed Layer 处理（产品信誉、调仓事件、Darwin 事件、贝叶斯评分、多时间框架信号融合）
    ↓
Decision Layer 输出（ZoneRuleEngine 基于 bayesian_score / consensus / crowding / Darwin 进行四区分类）
    ↓
Signal 输出（argus_signal JSON → portfolio/strategy/trading）
```

Phase 3 后，`ZoneRuleEngine` 是 Argus 与 Portfolio 共享的 zone 分类/迁移组件：

- 配置入口：`skills/research/argus/config/zone_rules_template.yaml`，Python loader 为 `config/zone_rules.py`。
- Argus 初始分类：`argus_signal_pool.entry_rules` 直接生成 `SCAN/WATCH/CANDIDATE/CONVICTION`。
- Portfolio 增量迁移：`portfolio_transitions` 执行 one-step promote / demote / exit，并使用 hysteresis retention 阈值。
- 旧 `pool_zones` / `zone_thresholds` 中的硬编码阈值仅作为历史兼容参考，新代码不得继续新增分散阈值。

#### 4.1.2 Argus 与 Portfolio 模块的数据交换流程
```
1. Argus 日度生成 signal JSON → logs/research/argus_signal_{YYYYMMDD}.json
2. Portfolio 模块定时监听/订阅该路径
3. Portfolio 解析 signal，纳入组合构建/调仓决策
4. 可选：Portfolio 通过 argus_portfolio_interface.py 查询实时持仓
```

#### 4.1.3 接口模块（argus_portfolio_interface.py）的业务流程
- 触发条件：Portfolio 模块需要 Argus 数据时调用，或 Argus 日度导出时自动调用
- 核心处理逻辑：查询 argus.db → 格式化 → 输出 JSON
- 正常分支：数据完整返回
- 异常降级分支：argus.db 不存在/查询超时 → 返回空列表 + 日志告警

#### 4.1.4 模块定位与依赖关系
- **所属模块**：08_research（投研分析）
- **跟踪对象**：基金产品（product_code），非基金经理
- **数据频率**：日度 T+1（持仓 + 交易 + NAV）
- **输出**：argus_signal（机构资金行为信号）
- **消费方**：05_portfolio（组合管理）、06_strategy（策略研发）、07_trading（交易执行）

```
                    ┌─────────────────┐
                    │  08_research    │
                    │     ARGUS       │
                    │ (机构资金追踪)   │
                    └────────┬────────┘
                             │ argus_signal
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
     │ 05_portfolio │ │ 06_strategy │ │  07_trading │
     │ (组合管理)   │ │ (策略研发)   │ │ (交易执行)  │
     └─────────────┘ └─────────────┘ └─────────────┘
```

### 4.2 数据模型（Data Model）

#### 4.2.1 数据来源：TradingAgents MongoDB Portfolio 表

Argus 的 Raw Layer 数据来源为 TradingAgents MongoDB 的 portfolio 相关表（通过 data-pipeline 从图片/消息导入），不再使用独立的 argus.db。数据接入结构：

| MongoDB 集合 | 说明 | 唯一键（UK） |
|---|---|---|
| `portfolio_basic_info` | 产品基础信息 | `product_code` |
| `portfolio_nav` | 产品净值历史 | `nav_date + product_code` |
| `portfolio_position` | 持仓明细快照 | `position_date + product_code + asset_wind_code` |
| `portfolio_trade` | 交易记录 | `trade_date + product_code + asset_wind_code + direction` |

**字段定义**（来自 `skills/data/data-pipeline/scripts/loaders/mongodb_loader.py`）：

**portfolio_basic_info**
| 字段 | 类型 | 说明 |
|---|---|---|
| product_code | VARCHAR(32) | 产品代码，UK |
| product_name | VARCHAR(128) | 产品名称 |
| latest_nav | DECIMAL(10,6) | 最新净值 |
| latest_share | DECIMAL(18,2) | 最新份额 |
| latest_aum | DECIMAL(18,2) | 最新规模（元） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

**portfolio_nav**
| 字段 | 类型 | 说明 |
|---|---|---|
| nav_date | DATE | 净值日期，UK 前缀 |
| product_code | VARCHAR(32) | 产品代码，UK |
| nav | DECIMAL(10,6) | 单位净值 |
| aum | DECIMAL(18,2) | 资产管理规模 |
| share | DECIMAL(18,2) | 最新份额 |
| created_at | DATETIME | 创建时间 |

**portfolio_position**
| 字段 | 类型 | 说明 |
|---|---|---|
| position_date | DATE | 持仓日期，UK 前缀 |
| product_code | VARCHAR(32) | 产品代码，UK |
| asset_wind_code | VARCHAR(32) | 资产Wind代码，UK |
| asset_name | VARCHAR(128) | 资产名称 |
| holding_ratio | DECIMAL(10,4) | 持仓比例（%） |
| shares | BIGINT | 持仓数量 |
| market_value | DECIMAL(18,2) | 市值（本币） |
| created_at | DATETIME | 创建时间 |

**portfolio_trade**
| 字段 | 类型 | 说明 |
|---|---|---|
| trade_date | DATE | 交易日期，UK 前缀 |
| product_code | VARCHAR(32) | 产品代码，UK |
| asset_wind_code | VARCHAR(32) | 资产Wind代码，UK |
| direction | VARCHAR(16) | 交易方向（BUY/SELL），UK |
| shares | BIGINT | 成交数量 |
| price | DECIMAL(10,4) | 成交价格 |
| amount | DECIMAL(18,2) | 成交金额 |
| created_at | DATETIME | 创建时间 |

#### 4.2.2 Argus Processed Layer（处理层）

在 Raw Layer 基础上，Argus 通过贝叶斯信誉评分引擎生成Processed Layer：

| Processed 表名 | 说明 |
|---|---|
| `argus_product_profile` | 产品行为画像（基于持仓和交易计算） |
| `argus_rebalancing_event` | 调仓事件检测（持仓比例突变） |
| `argus_signal` | 信号输出（最终产品） |
| `argus_consensus` | 共识方向（多产品汇聚） |
| `argus_darwin_event` | 达尔文时刻（拥挤度峰值） — **Phase 4B 已实现** |
| `argus_consensus_direction` | 共识方向详情 — **Phase 4C 已实现** |

#### 4.2.3 Argus Decision Layer（决策层）

| Decision 表名 | 说明 |
|---|---|
| `argus_signal_pool` ⚠️ rename from `argus_stock_pool` | 四区动态股票池（SCAN/WATCH/CANDIDATE/CONVICTION） |
| `argus_stock_pool_history` | 池变更审计轨迹 |

#### 4.2.4 数据流转

```
data-pipeline（图片/消息导入）
    ↓
TradingAgents MongoDB（portfolio_basic_info / portfolio_nav / portfolio_position / portfolio_trade）
    ↓ Read
Argus Processed Layer（贝叶斯评分引擎）
    ↓
Argus Decision Layer（argus_signal → bayesian_score → ZoneRuleEngine → argus_signal_pool）
    ↓ Output
portfolio / strategy / trading 模块消费
```

#### 4.2.5 Phase 3 计算顺序

Phase 3 固化日度处理顺序，避免 zone 分类读取到未完成的派生字段：

1. 读取 raw portfolio 数据并生成产品级信号。
2. 先运行 Darwin 事件检测，形成当日行业级 `darwin_events`。
3. 构造 stock-pool 记录时先合并信号、共识、拥挤度和行业 Darwin 标记。
4. 调用 `BayesianScorer.score_signal_pool_records()` 写入 `bayesian_score`。
5. 最后调用 `ZoneRuleEngine.classify_initial_zone()` 生成 `pool_zone` 和 `zone_decision`。

因此 `bayesian_score` 在 zone 分类前必须存在；`darwin_moment` / `darwin_confidence` 在调用 `BayesianScorer` 和 `ZoneRuleEngine` 时均已可用。

#### 4.2.6 Argus 输出信号格式（YQClaw 全局信号标准）
```json
{
  "signal_id": "uuid",
  "source": "argus",
  "product_code": "xxx",
  "signal_type": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0,
  "direction": "LONG|SHORT|FLAT",
  "target_stocks": ["600519", "000858"],
  "reason": "机构资金大幅流入，提前布局...",
  "generated_at": "YYYY-MM-DDTHH:MM:SS",
  "valid_until": "YYYY-MM-DD",
  "metadata": {
    "credibility_score": 0.85,
    "crowding_level": "LOW|MEDIUM|HIGH",
    "time_horizon": "FAST|MEDIUM|SLOW"
  }
}
```

### 4.3 接口契约（API Contract）

#### 4.3.1 argus_portfolio_interface.py 接口定义

| 方法 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `get_positions(product_code)` | 可选 product_code | `List[Dict]` | 获取跟踪产品的当前持仓 |
| `get_trades(product_code, start_date, end_date)` | 可选过滤条件 | `List[Dict]` | 获取交易记录 |
| `get_signals(signal_type, min_confidence)` | 可选过滤条件 | `List[Dict]` | 获取信号列表 |
| `export_to_portfolio_json(output_path)` | 可选输出路径 | `str`（文件路径） | 导出为 portfolio 可消费的 JSON |

#### 4.3.2 数据交换文件格式
- **路径**：`logs/research/argus_signal_{YYYYMMDD}.json`
- **频率**：日度 T+1
- **格式**：见 4.2.2 argus_signal JSON

#### 4.3.3 Argus 数据读取接口

Argus 通过 `PortfolioMongoReader` 类从 TradingAgents MongoDB 读取 Raw Layer 数据（不再使用独立的 argus.db）：

```python
class PortfolioMongoReader:
    """从 TradingAgents MongoDB 读取 portfolio 数据，供 Argus 处理层使用"""

    def get_positions(self, position_date: str, product_code: Optional[str] = None) -> List[Dict]:
        """读取 portfolio_position"""
        pass

    def get_trades(self, trade_date: str, product_code: Optional[str] = None) -> List[Dict]:
        """读取 portfolio_trade"""
        pass

    def get_nav(self, nav_date: str, product_code: Optional[str] = None) -> List[Dict]:
        """读取 portfolio_nav"""
        pass

    def get_basic_info(self, product_code: Optional[str] = None) -> List[Dict]:
        """读取 portfolio_basic_info"""
        pass
```

#### 4.3.4 Argus 输出接口

Argus 处理完成后，通过 `ArgusSignalExporter` 输出信号到文件或直接写入 MongoDB：
- 输出路径：`logs/research/argus_signal_{YYYYMMDD}.json`
- 可选：直接写入 `argus_signal` 集合（由 Argus 自建，不复用 portfolio_trade 表）

### 4.4 AI模型设计（如有）
不适用。Argus 使用确定性规则引擎（贝叶斯信誉评分），无需 AI/ML 模型。

## 5. AI实装规范
### 5.1 必须执行
- Argus 代码实装前必须先完成 RFC-08-002（接口标准）并进入 Accepted
- 所有新增代码必须遵循 YQClaw 八大标准化体系
- 接口模块使用 `common.utils.logging` 统一日志工具，禁止 print

### 5.2 先询问再执行
- 修改 Argus 底层数据模型（argus.db schema）
- 新增与主系统的直连数据通道（当前 JSON file 方案已定）
- 涉及实盘交易、风控规则变更

### 5.3 绝对禁止
- 在 argus_portfolio_interface.py 中硬编码数据库路径、密钥
- 在未创建 RFC-08-002 的情况下直接实装接口代码
- 删除或修改 RFC-2026-071 原有文档内容

## 6. 风险与应对
### 6.1 风险矩阵
| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| argus.db 文件损坏/丢失 | 低 | 高 | 定期备份 + 导入重新初始化 | 停止 signal 输出，保留历史数据 |
| Argus signal 被 portfolio 误用导致错误调仓 | 中 | 极高 | signal 必须携带 credibility_score，portfolio 设置最低阈值 | 仅接收高置信度 signal（≥0.7） |
| Argus 实装进度延迟影响 portfolio 依赖 | 中 | 中 | portfolio 设计独立的 signal 来源降级方案 | 临时依赖其他 research 信号源 |
| 多产品信号冲突（同一股票不同产品方向相反） | 中 | 高 | 达尔文时刻机制 + 拥挤度指标 | 降低冲突信号的权重 |

### 6.2 Argus 特有风险（D-005 至 D-008）
- 按产品追踪而非按经理，可能漏掉同一经理管理多产品时的协同效应
- 日度 T+1 数据存在 1 天延迟，急涨急跌行情可能无法及时捕捉
- JSON file exchange 作为友邦接口，有一定耦合风险（文件路径/权限依赖）

## 7. 备选方案
### 7.1 方案 A（已选用）：Argus 直接读取 TradingAgents MongoDB Portfolio 表
- **方案**：Argus Raw Layer 直接从 `portfolio_basic_info / portfolio_nav / portfolio_position / portfolio_trade` 读取，不再维护独立的 argus.db
- **优点**：数据单一来源，无冗余；与 data-pipeline 天然集成；维护成本低
- **缺点**：Argus 与 TradingAgents 紧耦合（但可接受，Argus 本就是 YQClaw 体系内）
- **选用原因**：portfolio 数据由 data-pipeline 统一导入，Argus 作为消费方直接订阅，无数据孤岛

### 7.2 方案 B（弃用）：保持独立 SQLite + 接口层
- **方案**：Argus 保持 `argus.db` 独立，新增接口层
- **缺点**：数据冗余；维护两套数据同步成本高；与 data-pipeline 架构冲突
- **弃用原因**：data-pipeline 已将数据写入 MongoDB，Argus 直接读取更简洁

## 8. 验收标准
### 8.1 RFC 纳标验收
- [ ] RFC-08-001 已创建并纳入 YQClaw RFC 索引，状态为 Accepted
- [ ] Argus 原有 RFC-2026-071 作为参考子文档保留，无破坏性修改
- [ ] RFC 编号映射完成（RFC-2026-071 → RFC-08-001）

### 8.2 接口验收
- [ ] `argus_portfolio_interface.py` 已创建并通过单元测试
- [ ] `get_positions()` / `get_trades()` / `get_signals()` 返回格式符合规范
- [ ] `export_to_portfolio_json()` 生成的文件可被 portfolio 模块消费
- [ ] 日志路径（`logs/research/argus_interface_{YYYYMMDD}.log`）、日志格式符合 YQClaw 规范

### 8.3 实装验收（后续）
- [ ] Argus Phase 1 代码实装完成（3 张 Raw 表 + CLI + SQL INSERT 模板）
- [ ] 与 portfolio 模块联调通过
- [ ] 压力测试：每日 1000+ 产品信号处理

## 9. 落地计划
### 9.1 第一阶段：RFC 纳标（1周）
1. 完成 RFC-08-001 进入 Review 并获批 Accepted
2. 创建 `docs/rfc/08_research/argus/INDEX.md` 作为 YQClaw 体系入口
3. 明确 Argus 与 portfolio 模块的接口契约（RFC-08-002 待建）

### 9.2 第二阶段：接口实装（2-3周）
1. 创建 `skills/research/argus/argus_portfolio_interface.py`
2. 实现 `get_positions()` / `get_trades()` / `get_signals()` / `export_to_portfolio_json()`
3. 单元测试 + 冒烟测试
4. argus_signal JSON 格式验证

### 9.3 第三阶段：Argus Phase 1 实装（后续，与 RFC-2026-071 同步）
1. Argus 代码本体实装（3 张 Raw 表 + CLI）
2. Argus Phase 1 与接口模块联调
3. 全链路测试（日度数据入口 → signal 输出 → portfolio 消费）

## 10. 开放问题
| 问题 | 状态 | 说明 |
|---|---|---|
| Argus v2.1.0 增量补丁是否纳入 | 待确认 | v2.1.0 含 xlsx parser + 化名映射机制 |
| Web UI 是否需要（Phase 4） | 待确认 | 当前 Phase 1-3 无 Web UI 计划 |
| 多数据源（私募/公募）接入 | 待讨论 | 当前仅支持日度 T+1 全持仓 |
| Argus 与其他 08_research 子项目（如有）的协同方式 | 待定义 | 等待 08_research 模块总纲 RFC |

## 11. 参考资料
- RFC-00-001-yqclaw-investment-global-architecture（全局架构总纲）
- RFC-2026-071_ARGUS/INDEX.md（Argus 详细设计索引）
- RFC-2026-071_ARGUS/02_ARCHITECTURE.md（独立子系统架构）
- RFC-2026-071_ARGUS/03_SCHEMA.md（13 表 DDL）
- TradingAgents-CN mongo-init.js（MongoDB Schema）
- YQClaw 八大标准化体系（RFC-00-001 第5章）
- docs/rfc/TEMPLATE_DIFF_REPORT.md（模板差异报告）
