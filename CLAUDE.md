# YQuant-Investment - Claude Code 持久上下文

> 项目：YQuant-Investment 智能量化投资系统
> 目录：workspace-yquant
> 行为准则来源：[andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills)，基于 Andrej Karpathy 对 LLM 编码陷阱的观察。

**项目定位**：对标顶级对冲基金的智能量化投资系统，覆盖 A股/Crypto/港股/美股 全品种，基于 OpenClaw 多智能体框架构建。

**核心语言**：Python > C++/Rust（性能敏感路径）
**数据源策略**：多源专业接口（A股: Tushare / Akshare / RQData；Crypto: Binance API / CoinGecko / CCXT 等；港股: FutuOpenD 等；美股: Finnhub / Polygon.io 等）
**量化框架**：VeighNa / NautilusTrader / Hummingbot / QUANTAXIS

---

## The Problem（来自 Karpathy 的观察）

> "LLM 会代表你做出错误假设然后一路执行，不检查、不澄清、不暴露矛盾、不呈现权衡取舍、不该退缩时不退缩。"
> "它们特别喜欢过度设计代码和 API，膨胀抽象层，清理死代码…… 100 行能解决的问题用了 1000 行。"
> "它们仍会顺手修改/删除它们不够理解的注释和代码，即使这些改动与任务完全无关。"

---

## 四大行为原则

### 1. Think Before Coding（先思考，后编码）

**不假设。不隐藏困惑。暴露权衡。**

在实现任何代码之前：
- 明确陈述你的假设。如果不确定，直接问——不要默默猜
- 如果有多种理解方式，全部列出让用户选择——不要自己默默挑一种往下做
- 如果有更简单的替代方案，说出来。在合理的情况下可以提出异议
- 如果某事不清楚，停下来。指出困惑点。问清楚

在实现前：明确你的假设；如果是复杂任务，列出 3-5 个关键步骤和成功标准。

```

// Worse // Better
"我来重构这个回测引擎" "回测引擎重构有3种方案：
A) 基于 NautilusTrader
B) 基于现有 VeighNa 扩展
C) 最小化修改现有代码
你倾哪种？"

```

### 2. Simplicity First（简洁优先）

**最小可行代码——只解决当前问题，不加投机性功能。**

- 不添加用户未要求的任何功能
- 不为一次性的代码增加抽象层或基类
- 不添加未被要求的"灵活性"或"可配置性"
- 不对不可能发生的场景做防御性错误处理
- 如果你写了 200 行而可以缩减到 50 行，重写它

**核心测试**：资深工程师会觉得这是过度设计吗？如果是，简化它。

```

// Worse // Better
class Strategy(ABC): # 策略文件：mean_reversion.py
@abstractmethod def generate_signals(self, prices):
def generate_signals(self): ... zscore = (prices - mean) / std
return -zscore
class MeanRevStrategy(Strategy):
def generate_signals(self): ...

```

### 3. Surgical Changes（精准修改）

**只碰必须碰的代码。只清理自己产生的混乱。**

编辑已有代码时：
- 不要"改进"相邻的代码、注释或格式
- 不要重构没有坏的东西
- 匹配现有的代码风格，即使你自己会写成另一个样子
- 如果发现无关的死代码，可以提及——但不要在未经许可的情况下删除

当你的修改导致孤立代码：
- 删除你的修改导致的未使用 import/变量/函数
- 不要删除预先存在的死代码，除非被要求

**核心测试**：每条被修改的代码行都应该能直接追溯到用户的需求。

```

// Worse // Better
"我顺便把 # TODO: optimize 改成了 "是否也处理 XXX 文件中的

TODO: optimize using vectorization" # TODO 注释？还是只处理当前任务？"

```

### 4. Goal-Driven Execution（目标驱动）

**定义成功标准。循环迭代直到验证达标。**

将模糊任务转化为可验证目标：

| 代替... | 转化为... |
|----------------------|--------------------------------------------|
| "加一个验证" | "为无效输入编写测试，然后让测试通过" |
| "修这个 bug" | "写一个能复现 bug 的测试，然后让它通过" |
| "重构 X" | "确保重构前后所有测试都通过" |
| "新增一个风控模块" | "VaR 计算与 Monte Carlo 方法误差 < 0.5%，并通过所有测试" |

多步任务，陈述简要计划：

```

1. [设计数据结构] → 验证：[schema 通过所有数据源的样本测试]
2. [实现核心引擎] → 验证：[回测 1 年数据，结果与 VeighNa benchmark 偏差 < 0.5%]
3. [集成风控] → 验证：[压力测试产生非零风险指标]

```

强成功标准让你可以独立循环迭代。弱标准（"搞出来就行"）需要不断被澄清。

> "LLM 特别擅长循环直到达成特定目标…… 不要告诉它做什么，给它成功标准，它自然会朝着目标前进。" — Karpathy

---

## 项目架构

### 目录结构

### 目录结构
```

workspace-yquant/
├── soul.md          # 心智模型与行为哲学
├── identity.md      # 角色身份与能力边界
├── agents.md        # 子智能体团队定义与协作流程
├── claude.md        # Claude Code 持久上下文
├── HEARTBEAT.md     # 定期任务调度配置
├── USER.md          # Pascal 用户信息
├── TOOLS.md         # 工具配置（数据源、推送）
├── MEMORY.md        # 长期记忆
├── memory/          # 每日记忆文件
├── skills/         # 技能模块
│ ├── common/       # 通用工具（PDF解析、邮件、爬虫）
│ ├── data/         # 数据采集与处理
│ ├── research/     # 投研分析（因子、市场、另类数据）
│ ├── strategies/    # 策略研发与回测
│ ├── risk/         # 风险管控
│ ├── portfolio/    # 组合管理
│ ├── reports/      # 复盘报告
│ ├── infra/        # 基础设施
│ └── knowledge/    # 知识库
└── auto_push.sh    # 自动推送脚本
```

### 智能体团队
主智能体 @YQuant 调度以下子智能体（详见 agents.md）：
- @YQuant/data-collector、@YQuant/researcher、@YQuant/strategist、@YQuant/risk-manager、@YQuant/portfolio-manager、@YQuant/reporter、@YQuant/common、@YQuant/data-engineer、@YQuant/devops

### 核心依赖
- **量化框架**：VeighNa、NautilusTrader、Hummingbot、QUANTAXIS
- **计算库**：NumPy、Pandas、SciPy、CVXPY、Statsmodels
- **机器学习**：Scikit-learn、XGBoost、PyTorch
- **可视化**：Matplotlib、Plotly、Streamlit
- **编排**：LangGraph（智能体工作流）

### 智能体框架参考
在进行多智能体协作设计时，可参考以下开源项目的架构思想与实践：
- **TradingAgents-CN**：中文版多角色量化交易智能体平台，展示了分析师、研究员、交易员、风控等角色间的辩论与协作机制。
- **daily_stock_analysis**：基于大模型的自动化股票分析工具，其报告生成与多源数据聚合逻辑对 YQuant 的投研流程有借鉴意义。

---

## 编码规范

### Python 规范
- PEP 8, Black (line-length=100), Ruff 静态检查
- 类型注解：所有公共函数必须有
- 文档：Google 风格 docstring，复杂逻辑必须有行内注释
- 命名：snake_case / PascalCase / UPPER_CASE，禁止无意义名称
- 每个文件不超过 300 行

### 回测规范
- 回测和实盘使用相同的事件驱动执行模型
- 必须对比样本内和样本外表现，并提供基准策略对比
- 回测报告至少包含：年化收益、夏普比率、最大回撤、卡玛比率、换手率、信息比率
- 回测结果完全可复现

### 数据管理规范
- 所有数据必须标注来源（如 "Source: Tushare"）
- 行情数据必须包含时间戳和时区
- 需要使用最适合当前市场和数据类型的数据接口
- 不要凭空编造数据库中的模式或表名

---

## How to Know It's Working

这些规范生效的标志：
- **diff 中不必要的修改减少**——只出现你要求的改动
- **因过度设计被重写的次数减少**——代码第一次就足够简洁
- **澄清性问题出现在实现之前**——而非犯错之后
- **pull request 干净、极简**——没有顺手重构、没有"改进"

---

## Tradeoff Note

这些规范偏向**谨慎而非速度**。对于纯机械性任务（简单拼写修正、明显的一行代码修复等），可以用判断力灵活处理——不必每次都动用全部原则。目标是减少非机械性工作中的高代价错误，而非拖慢简单任务的速度。
