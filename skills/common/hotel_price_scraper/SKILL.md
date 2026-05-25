---
name: hotel_price_scraper
description: 每周抓取 Jalan、Booking、Trip.com/Ctrip 目标酒店未来 30 天标准双人间 1 晚价格走势，合并输出 Excel 并通过邮件发送；用于酒店价格监控、周报附件生成、cookie 初始化和价格抓取失败排查。
---

# Hotel Price Scraper

## 触发条件

使用本技能处理以下任务：

- 每周一自动抓取酒店价格走势。
- 查询 Jalan、Booking、Trip.com/Ctrip 指定酒店未来 30 天房价。
- 生成酒店价格 Excel 周报并邮件发送。
- 初始化或刷新 Trip.com Selenium cookie。
- 排查酒店价格抓取、cookie 过期、平台页面解析失败等问题。

## 输入

核心输入是目标酒店配置文件：

`~/.openclaw/workspace-yquant/skills/common/hotel_price_scraper/config.yaml`

配置应包含：

- 查询参数：`days_ahead`、`nights`、`adults`、`children`、`rooms`、`currency`。
- 房型匹配关键词：用于识别标准双人间。
- 酒店列表：每个酒店的内部 `hotel_key`、展示名和各平台 ID。
- 平台 cookie 引用：Jalan/Booking 使用 requests session cookie；Trip 默认读取旧版 `skills/common/su-scraper/scripts/trip_cookies.json`。
- 酒店列表：统一写在 `config.yaml`，每个酒店提供 `hotel_key`、展示名和各平台 ID。

邮件配置固定从以下文件读取：

`~/.openclaw/workspace-yquant/skills/.env`

必需环境变量：

- `EMAIL_SENDER`
- `EMAIL_PASSWORD`
- `EMAIL_RECEIVERS`

## 输出

每次运行输出一个 Excel 文件和一封邮件。

Excel 文件：

`output/hotel_price_report_YYYY-MM-DD.xlsx`

Sheet：

- `summary`：按酒店、平台、入住日期汇总标准双人间优先报价。
- `jalan`：Jalan 原始标准化记录。
- `booking`：Booking 原始标准化记录。
- `trip`：Trip 原始标准化记录。
- `errors`：单平台、单酒店、单日期失败记录。
- `run_meta`：运行元数据、配置摘要和统计。

邮件：

- 主题：`【YQuant】酒店价格周报 YYYY-MM-DD`
- 正文：成功平台、失败平台、酒店数、有效报价数、错误摘要。
- 附件：统一 Excel 文件。

## 依赖环境

Python 依赖：

```bash
pip install pandas openpyxl requests beautifulsoup4 selenium python-dotenv pyyaml
```

系统依赖：

- Chrome 或 Chromium。
- 与浏览器版本匹配的 ChromeDriver，或 Selenium Manager 可自动解析驱动。
- 可访问目标平台网页的网络环境。

## 使用方式

### 每周抓取并发送邮件

```bash
cd /home/pascal/.openclaw/workspace-yquant/skills/common/hotel_price_scraper
python3 run.py --config config.yaml --env /home/pascal/.openclaw/workspace-yquant/skills/.env --output-dir output --days 30 --send-email
```

### 只运行单个平台

```bash
python3 run.py --config config.yaml --platform booking --days 30
python3 run.py --config config.yaml --platform all --days 30
```

支持平台：

- `jalan`
- `booking`
- `trip`

### 初始化 Trip cookie

Trip.com 需要 Selenium 打开页面并人工完成登录或验证。

```bash
python3 init_trip_cookie.py --cookie-path /home/pascal/.openclaw/workspace-yquant/skills/common/su-scraper/scripts/trip_cookies.json
```

运行后等待浏览器打开，在 60 秒内完成登录或验证，脚本保存：

`skills/common/su-scraper/scripts/trip_cookies.json`

### crontab

每周一 06:10 CST 运行：

```cron
10 6 * * 1 cd /home/pascal/.openclaw/workspace-yquant/skills/common/hotel_price_scraper && /usr/bin/python3 run.py --config config.yaml --env /home/pascal/.openclaw/workspace-yquant/skills/.env --output-dir output --days 30 --send-email >> logs/cron.log 2>&1
```

## 操作原则

- 邮件凭据不得写入脚本或配置，只能读取 `skills/.env`。
- 单平台失败不应中断全局任务；记录错误后继续其他平台。
- 每次请求间隔 3 秒，调度器并发上限为 2。
- Jalan 和 Booking 使用 `requests.Session` 维持 cookie。
- Trip 使用 Selenium 初始化和复用 cookie。
- 不自动绕过验证码，不使用高并发代理池。
- 输出 Excel 必须三平台合并到一个文件，不再生成三个独立附件。

## 开发测试

```bash
cd /home/pascal/.openclaw/workspace-yquant/skills/common/hotel_price_scraper
python3 -m pytest tests
python3 run.py --platform jalan --days 1
python3 run.py --platform all --days 1
```

## 参考文档

- 需求与技术方案：`RFC.md`
- su-scraper 重构设计：`REFACTOR_DESIGN.md`
