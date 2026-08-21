import os
import smtplib
import sys
from email.mime.text import MIMEText
from email.header import Header

report_content = """正在生成每日市场报告...
============================================================
[Adapter] CoinGecko API 错误：429
[Adapter] 获取 A 股指数失败：No module named 'tenacity'
[Adapter] fetcher 美股指数失败：No module named 'tenacity'
[Adapter] CoinGecko API 错误：429
[Adapter] global 国际新闻: 获取失败
[Adapter] us 国际新闻: 获取失败
[Adapter] crypto 国际新闻: 获取失败
# 📈 每日全球市场研究报告

**日期：** 2026-04-09 周四  
**生成时间：** 2026-04-09 08:53 CST

## 一、全球市场概览

📊 **初始配置比例：** A+H股 53% | 美股 18% | 中债 18% | 数字货币 5% | 大宗商品 3% | 美债 3%

| 市场 | 最新价 | 涨跌幅 | 市场分析 | 仓位建议 | 理由 |
|------|--------|--------|----------|----------|------|
| 上证指数 | ⚪ — | — | 今日A股市场呈现强势上攻态势，主要指数全线飘红。两市上涨个股达5174家，仅301家下跌，涨停家数134家，市场赚钱效应显著。值得注意的是，今日两市成交额飙升至24506亿元，较前五个交易日（16236、16689、18578、20248、20059亿元）出现明显放量，单日增量超4000亿元，量能创近期新高，反映出场外资金积极进场。科创50和创业板指分别大涨6.18%和5.91%，领先其他指数，显示科技成长风格明显占优。 | 标配 40% | 核心资产 |
| 沪深300 | ⚪ — | — | 今日A股市场呈现强势上攻态势... | 标配 40% | 核心资产 |
| 恒生指数 | ⚪ 25893.02 | +0.00% | 市场数据获取中... | 低配 15% | 南向待观察 |
| 恒生科技 | 🟢 4923.25 | +5.22% | 市场数据获取中... | 低配 15% | 南向待观察 |
| 标普500 | ⚪ 6782.81 | +0.00% | Risk-On signal, increase equity allocation... | 标配 20% | 估值偏高 |
| 纳斯达克 | ⚪ 22634.99 | +0.00% | Risk-On signal, increase equity allocation... | 标配 20% | 估值偏高 |
| BTC | ⚪ — | — | 数据获取中... | 超配 10% | ETF净流入 |
| 黄金 | ⚪ — | — | 待接入 | 标配 5% | — |
| WTI原油 | ⚪ — | — | 待接入 | 低配 3% | — |
| 美债10Y | ⚪ — | — | 待接入 | 标配 3% | — |
| 中债10Y | ⚪ — | — | 待接入 | 超配 5% | — |

## 二、热点资讯 Top 3 (过去24小时)

### 🇨🇳 A 股市场
1. 美国银行全球大宗商品和衍生品研究主管弗朗西斯科·布兰奇（Francisco Blanch）表示，尽管布伦特和WTI原油期货价格有所回落，但实物市场实际极为紧张
2. 知情人士透露，苹果公司首款折叠屏手机有望在今年晚些时候公司常规iPhone发布期面世
3. 美国芯片制造商英特尔公司将加入埃隆·马斯克的"高风险"计划，为特斯拉公司、SpaceX和xAI开发半导体

## 三、各市场复盘

### 3.1 A 股市场复盘
今日A股市场呈现强势上攻态势，主要指数全线飘红。两市上涨个股达5174家，仅301家下跌，涨停家数134家，市场赚钱效应显著。成交额飙升至24506亿元，较前五个交易日明显放量。

科创50和创业板指分别大涨6.18%和5.91%，显示科技成长风格明显占优。

**策略结论：进攻** | 建议仓位提升至70%-80%，重点配置科技成长方向。

### 3.2 美股市场复盘
US equity markets delivered a powerful broad-based rally, with all three major indices surging over 2.5%. VIX declined 18.39% to 21.04, signaling risk-on posture.

**Stance: Risk-On (cautious)** - Invalidation if SPX fails to hold 6700 on close.

### 3.3-3.6 其他市场
数据待接入。

## 四、金融日历
数据待接入。

## 五、小Q洞察
🎯 今日核心判断：A股科技主线确立，美股风险偏好回升
💡 机会提示：AI应用、半导体产业链、通信设备
⚠️ 风险提示：量能持续性、获利了结压力、地缘局势反复

---
*本报告仅供参考，不构成投资建议。*
============================================================
"""

msg = MIMEText(report_content, 'plain', 'utf-8')
msg['Subject'] = Header('【每日市场报告】2026-04-09', 'utf-8')

# SMTP 凭据来自 .env（EMAIL_USERNAME / EMAIL_PASSWORD），不再硬编码
username = os.environ.get('EMAIL_USERNAME', '').strip()
password = os.environ.get('EMAIL_PASSWORD', '').strip()
recipients_raw = os.environ.get('EMAIL_RECIPIENTS', '').strip()
recipients = [r.strip() for r in recipients_raw.split(',') if r.strip()]

missing = [name for name, val in (
    ('EMAIL_USERNAME', username),
    ('EMAIL_PASSWORD', password),
    ('EMAIL_RECIPIENTS', recipients),
) if not val]
if missing:
    sys.stderr.write(
        'send_report_email: SMTP 凭据缺失 ('
        + ', '.join(missing)
        + ')。请在 .env 设置 EMAIL_USERNAME / EMAIL_PASSWORD / EMAIL_RECIPIENTS 后重试。\n'
    )
    sys.exit(1)

msg['From'] = username
msg['To'] = ', '.join(recipients)

try:
    server = smtplib.SMTP_SSL('smtp.qq.com', 465)
    server.login(username, password)
    server.sendmail(username, recipients, msg.as_string())
    server.quit()
    print('EMAIL_SENT_SUCCESS')
except Exception as e:
    print(f'EMAIL_SEND_FAILED: {e}')
