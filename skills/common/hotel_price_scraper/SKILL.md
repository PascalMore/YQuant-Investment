---
name: hotel_price_scraper
description: 每周一抓取 Booking 和 Jalan 目标酒店未来 30 天大床房（ダブル）和双床房（ツイン）最低价，合并输出 Excel 并通过邮件发送；用于酒店价格监控、周报附件生成和价格抓取失败排查。
---

# Hotel Price Scraper

## 触发条件

使用本技能处理以下任务：

- 每周一自动抓取酒店价格走势。
- 查询 Booking、Jalan 指定酒店未来 30 天**大床房和双床房**最低价。
- 生成酒店价格 Excel 周报并邮件发送。
- 排查酒店价格抓取、cookie 过期、平台页面解析失败等问题。

## 目标酒店（10 家）

| # | hotel_key | 酒店名 | Booking | Jalan |
|---|-----------|--------|---------|-------|
| 1 | legasta_shirakawa | ホテルレガスタ京都白川三条 | ✅ | ✅ |
| 2 | ms_sanjo_wakoku | エムズホテル三条WAKOKU | ✅ | ✅ |
| 3 | stay_sakura_higashiyama | ステイサクラ京都東山三条 | ✅ | ✅ |
| 4 | rakuten_urban_shijo | 楽天ステイアーバン四条河原町 | ✅ | ❌ |
| 5 | carta_gion | カルタホテル京都祇園 | ✅ | ❌ |
| 6 | travertin_kiyamachi | ホテルトラベルティン京都木屋町 | ✅ | ❌ |
| 7 | waka_asakusa_wakokoro | 若・浅草和心ホテル | ✅ | ❌ |
| 8 | super_hotel_asakusa | スーパーホテル浅草 | ✅ | ❌ |
| 9 | other_space_asakusa | OTHER SPACE Asakusa | ✅ | ❌ |
| 10 | hop_inn_tokyo_asakusa | Hop Inn Tokyo Asakusa | ✅ | ❌ |

## 输入

核心输入是目标酒店配置文件：

`~/.openclaw/workspace-yquant/skills/common/hotel_price_scraper/config.yaml`

配置应包含：

- 查询参数：`days_ahead`、`nights`、`adults`、`children`、`rooms`、`currency`。
- 酒店列表：每个酒店的 `hotel_key`、展示名和各平台 ID。
- 平台 cookie：Jalan/Booking 使用 requests session cookie。

邮件配置从以下文件读取：

`~/.openclaw/workspace-yquant/skills/.env`

必需环境变量：

- `EMAIL_SENDER`
- `EMAIL_PASSWORD`
- `EMAIL_RECEIVERS`（多个收件人用逗号分隔）

## 房型规则

每次抓取同时收集两种房型：

| room_category | 匹配关键词（不区分大小写） |
|---------------|-------------------------|
| `double` | ダブル、double |
| `twin` | ツイン、twin |

- 匹配优先级：先检查 twin，再检查 double
- 每种房型在同一家酒店同一天取**最低价**
- 不匹配任何关键词的房型自动跳过

## 输出

每次运行输出一个 Excel 文件和一封邮件。

Excel 文件：

`output/hotel_price_report_YYYY-MM-DD.xlsx`

Sheet：

- `Summary`：交叉对比表（hotel_name × checkin_date → booking_double/twin, jalan_double/twin 最低价）。
- `Booking`：Booking 原始标准化记录（含 room_category 列）。
- `Jalan`：Jalan 原始标准化记录（含 room_category 列）。
- `Errors`：单平台、单酒店、单日期失败记录。
- `RunMeta`：运行元数据、配置摘要和统计。

邮件：

- 主题：`【YQuant】酒店价格周报 YYYY-MM-DD`
- 正文：酒店数、有效报价数、错误数、错误摘要。
- 附件：统一 Excel 文件。

## 依赖环境

Python 依赖：

```bash
pip install pandas openpyxl requests beautifulsoup4 python-dotenv pyyaml
```

> Trip.com 相关的 selenium 依赖已不再是必需（第一版不含 Trip 平台）。

## 使用方式

### 每周抓取并发送邮件

```bash
cd /home/pascal/.openclaw/workspace-yquant/skills/common/hotel_price_scraper
python3 run.py --config config.yaml --env /home/pascal/.openclaw/workspace-yquant/skills/.env --output-dir output --days 30 --send-email
```

### 只运行单个平台

```bash
python3 run.py --config config.yaml --platform booking --days 30
python3 run.py --config config.yaml --platform jalan --days 30
python3 run.py --config config.yaml --platform all --days 30
```

支持平台：`jalan`、`booking`、`all`

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
- 不自动绕过验证码，不使用高并发代理池。
- 输出 Excel 必须所有平台合并到一个文件。

## 开发测试

```bash
cd /home/pascal/.openclaw/workspace-yquant/skills/common/hotel_price_scraper
python3 -m pytest tests
python3 run.py --platform booking --days 1
python3 run.py --platform all --days 1
```

## 参考文档

- 需求与技术方案：`docs/rfc/02_common/RFC-02-003-hotel-price-scraper.md`
- su-scraper 重构设计：`REFACTOR_DESIGN.md`
