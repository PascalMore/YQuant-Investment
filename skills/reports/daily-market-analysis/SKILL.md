---
name: daily-market-analysis
description: 生成每日全球市场研究报告，覆盖美股、A/H 股、数字货币、大宗商品四大市场。包括市场概览、TOP5 全球热点、各市场 Top3 资讯、未来 1 个月金融日历、小 Q 洞察与机会提示。使用于每个交易日早上自动生成市场日报。
---

# Daily Market Analysis

## Overview

每日全球市场研究报告生成技能，为 Pascal 提供专业、全面、可执行的市场简报。

**核心价值：**
- 📊 四大市场全覆盖（美股、A/H 股、数字货币、大宗商品）
- 🔥 热点资讯聚合 + 排序（Top5 全球 + 各市场 Top3）
- 📆 未来 1 个月金融日历
- 💡 AI 驱动洞察（DeepSeek/Gemini）
- ⚡ 自动化推送（邮件，每个交易日 08:30）

## When to Use

- 每个交易日早上 8:00 自动生成
- Pascal 询问"今天市场怎么样"
- 需要快速了解隔夜市场动态
- 盘前准备和当日策略制定

## Data Sources

### 市场数据
| 市场 | 数据源 | 优先级 |
|------|--------|--------|
| 美股 | YFinance | P0 |
| A 股 | AKShare | P0 |
| 港股 | AKShare | P0 |
| 数字货币 | Binance API | P0 |
| 大宗商品 | AKShare + YFinance | P1 |

### 新闻资讯
| 类型 | 数据源 | 优先级 |
|------|--------|--------|
| 全球财经 | Tavily API | P0 |
| 美股新闻 | Yahoo Finance RSS | P0 |
| A 股新闻 | 东方财富 RSS | P0 |
| 港股新闻 | 腾讯财经 RSS | P1 |
| Crypto 新闻 | CoinDesk RSS + Twitter | P0 |
| 大宗商品 | Investing.com RSS | P1 |

### 金融日历
| 类型 | 数据源 | 优先级 |
|------|--------|--------|
| 全球经济数据 | TradingEconomics | P0 |
| 中国数据 | 金十数据 | P0 |
| 财报日历 | Yahoo Finance | P0 |

## Workflow

```
1. 数据获取 (06:00-07:00)
   ├─ 美股收盘数据
   ├─ A/H 股盘前数据
   ├─ 数字货币 24h 数据
   ├─ 大宗商品价格
   └─ 金融日历数据

2. 新闻聚合 (07:00-07:30)
   ├─ RSS 抓取
   ├─ Tavily 搜索
   ├─ 去重 + 排序
   └─ Top5/Top3筛选

3. AI 洞察生成 (07:30-07:45)
   ├─ 市场趋势分析
   ├─ 机会提示
   └─ 风险预警

4. 报告格式化 (07:45-08:00)
   ├─ Markdown 排版
   ├─ 表格生成
   └─ 置信度标注

5. 推送 (08:00)
   └─ 飞书 Webhook
```

## Output Format

```markdown
# 📈 每日市场研究报告
**日期：** 2026-04-05 周一
**生成时间：** 08:00 CST

## 🌍 一、全球市场概览
（四大市场核心指数表格）

## 🔥 二、TOP5 全球影响力热点
（影响等级 + 解读）

## 📰 三、各市场 Top3 热点资讯
（美股/A/H/Crypto/大宗）

## 📆 四、未来 1 个月金融日历
（高影响事件优先）

## 💡 五、小 Q 洞察与机会提示
（重点关注 + 风险提示 + 潜在机会）

## 📊 六、持仓/自选股异动（可选）
```

## Scripts

- `scripts/main.py` - 主入口，协调各模块
- `scripts/data_fetcher.py` - 统一数据获取接口
- `scripts/news_aggregator.py` - 新闻聚合 + 排序
- `scripts/calendar.py` - 金融日历获取
- `scripts/insight_generator.py` - AI 洞察生成
- `scripts/report_formatter.py` - 报告格式化
- `scripts/feishu_push.py` - 飞书推送

## Configuration

配置采用**分区契约**：

| 范围 | 文件 | 入库 | 内容 |
|------|------|------|------|
| 敏感 / 准敏感 | `.env`（基于 `.env.example` 复制） | 否（.gitignore） | API Key、SMTP 凭据、收件人列表 |
| 非敏感运行时 | `config.json` | 是 | 数据源开关、SMTP 服务器 / 端口、推送策略、排程、自选股、AI 模型 |

加载入口：`src/config.py::load_skill_config()`。
- 系统环境变量优先于 `.env`（`load_dotenv(override=False)`）
- 邮件推送启用时校验 `username` / `password` / `recipients` 三项必填，缺失立即 `SystemExit`，避免静默失败。

字段映射（config.json key → .env 变量）：

| config.json 路径 | .env 变量 |
|------------------|-----------|
| `data_sources.tavily.api_key` | `TAVILY_API_KEY` |
| `data_sources.gnews.api_key` | `GNEWS_API_KEY` |
| `data_sources.tradingeconomics.api_key` | `TRADING_ECONOMICS_API_KEY` |
| `push.email.username` | `EMAIL_USERNAME` |
| `push.email.password` | `EMAIL_PASSWORD` |
| `push.email.recipients` | `EMAIL_RECIPIENTS`（英文逗号分隔） |

`config.json` 中**不应**包含任何 `api_key` / `username` / `password` / `recipients` 字面量；这些字段运行时由 loader 从 `.env` 注入。

首次部署：

```bash
cp .env.example .env
# 编辑 .env 填入真实凭据（不入 git）
```

## Examples

### 触发示例

```
生成今天的市场日报

昨晚美股怎么样？

最近有什么重要财经事件？
```

### 输出示例

```markdown
## 美股 Top3
1. 🔴 美联储官员讲话：通胀仍在高位，加息预期升温
   - 来源：Bloomberg
   - 影响：美股期货下跌 1%

2. 🟡 苹果财报超预期，盘后 +5%
   - 来源：CNBC
   - 影响：科技股普涨

3. 🟢 特斯拉交付量创新高
   - 来源：Reuters
   - 影响：电动车板块走强
```

## Quality Standards

### 数据准确性
- ✅ 核心数据（指数、价格）准确率 >95%
- ✅ 新闻来源可追溯
- ✅ 时间戳准确（CST）

### 报告完整性
- ✅ 四大市场数据完整
- ✅ Top5/Top3 资讯完整
- ✅ 金融日历覆盖未来 30 天
- ✅ AI 洞察有具体建议

### 推送准时性
- ✅ 每个交易日 08:00 前送达
- ✅ 失败时自动重试（3 次）
- ✅ 失败通知（飞书提醒）

## Maintenance

### 定期检查
- [ ] 每周检查数据源稳定性
- [ ] 每月更新 RSS 源列表
- [ ] 每季度回顾 AI 洞察质量

### 常见问题
- **数据源失败** → 启用备用源
- **推送失败** → 检查 Webhook + 重试
- **新闻质量下降** → 调整排序算法

## References

- `references/data_sources.md` - 数据源详细清单
- `references/rss_feeds_list.md` - RSS 源列表
- `references/api_keys.md` - API Key 管理说明

## Related Skills

- `stock-research` - 个股深度分析
- `portfolio` - 组合管理
- `market-monitor` - 实时市场监控

---

_小 Q 备注：拒绝闭门造车，所有分析基于市场数据 + 纵横对标。_
