#!/usr/bin/env python3
"""
每日市场分析报告 - 主入口

生成全球金融市场日报，包括：
- A/H 股、美股、数字货币、大宗商品行情
- 各市场 Top3 热点资讯
- 小 Q 洞察与机会提示

Usage:
    python main.py [--date YYYY-MM-DD] [--output markdown|email] [--debug]
"""

import argparse
import base64
import json
import os
import smtplib
import sys
from datetime import datetime, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from email.header import Header
from pathlib import Path
from pymongo import MongoClient

# 添加父目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

# 导入新的报告生成器
from all_weather_market_report import AllWeatherMarketReport
from src.new_services.report_generator import ReportGenerator


def load_config():
    """加载配置文件"""
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        print("⚠️ 配置文件不存在，使用默认配置")
        return get_default_config()
    
    with open(config_path, "r", encoding='utf-8') as f:
        return json.load(f)


def get_default_config():
    """默认配置"""
    return {
        "data_sources": {
            "akshare": {"enabled": True},
            "yfinance": {"enabled": True},
            "binance": {"enabled": True},
            "tavily": {"enabled": False, "api_key": ""}
        },
                "push": {
            "email": {
                "enabled": True,
                "smtp_server": "smtp.qq.com",
                "smtp_port": 587,
                "username": "532484187@qq.com",
                "password": "vyzfsxtfuqufcaed",
                "recipients": ["532484187@qq.com"],
                "sender_name": "YQClaw智能投资助手",
                "is_html": True
            }
        },
        "schedule": {
            "timezone": "Asia/Shanghai",
            "time": "08:30",
            "trading_days_only": True
        },
        "watchlist": {
            "stocks": ["600519", "00700", "AAPL", "NVDA"],
            "crypto": ["BTC", "ETH", "BNB", "SOL"]
        }
    }


def send_email(report: str, config: dict, report_date: str, is_html=None):
    """发送邮件报告"""
    email_config = config.get("push", {}).get("email", {})
    
    if not email_config.get("enabled"):
        print("⚠️ 邮件推送未启用")
        return False
    
    # 使用配置的 is_html 值（如果未指定）
    if is_html is None:
        is_html = email_config.get('is_html', False)
    
    try:
        # 创建邮件
        msg = MIMEMultipart()
        # 发件人：如果有 sender_name 则使用，否则只用邮箱
        sender_name = email_config.get('sender_name', '')
        if sender_name:
            msg['From'] = f"=?UTF-8?B?{base64.b64encode(sender_name.encode('utf-8')).decode()}?= <{email_config['username']}>"
        else:
            msg['From'] = email_config['username']
        msg['To'] = ", ".join(email_config['recipients'])
        msg['Subject'] = f"📈 每日全球市场报告 - {report_date}"
        
        # 添加报告内容
        if is_html:
            msg.attach(MIMEText(report, 'html', 'utf-8'))
        else:
            msg.attach(MIMEText(report, 'plain', 'utf-8'))
        
        # 发送邮件
        server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'], timeout=15)
        server.starttls()
        server.login(email_config['username'], email_config['password'])
        server.send_message(msg)
        server.quit()
        print("✅ 邮件推送成功")
        # 标记今日已发送
        marker = Path(os.path.expanduser('~/.openclaw/workspace-yquant/skills/reports/daily-market-analysis/.last_sent'))
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return True
        
    except Exception as e:
        print(f"❌ 邮件推送失败：{e}")
        return False


def _get_mongo_client():
    """获取 MongoDB 客户端"""
    host = os.environ.get('MONGODB_HOST', '172.25.240.1')
    port = int(os.environ.get('MONGODB_PORT', '27017'))
    username = os.environ.get('MONGODB_USERNAME', 'myq')
    password = os.environ.get('MONGODB_PASSWORD', '6812345')
    client = MongoClient(host, port, username=username, password=password,
                         serverSelectionTimeoutMS=5000)
    # 验证连接
    client.server_info()
    return client


def _get_portfolio_latest_date():
    """获取组合持仓数据最新日期（从 portfolio_trade）"""
    try:
        client = _get_mongo_client()
        db = client[os.environ.get('MONGODB_DATABASE', 'tradingagents')]
        latest = db['portfolio_trade'].find_one(
            sort=[('trade_date', -1)],
            projection={'trade_date': 1}
        )
        client.close()
        if latest and 'trade_date' in latest:
            td = latest['trade_date']
            if isinstance(td, datetime):
                return td.date()
            if isinstance(td, str) and td:
                return datetime.strptime(td[:10], '%Y-%m-%d').date()
            return td
    except Exception as e:
        print(f"[警告] 无法获取组合最新日期: {e}")
    return None


def _should_skip_report(report_date: date) -> bool:
    """
    检查今日是否应该跳过报告生成（市场日报）。
    逻辑：
    - 检查标记文件是否已存在且为今日创建
    - 如果是，跳过发送
    - 不检查组合数据日期（那是 SmartMoney 报告的逻辑）
    """
    marker = Path(os.path.expanduser('~/.openclaw/workspace-yquant/skills/reports/daily-market-analysis/.last_sent'))
    today = date.today()

    # 非当日报告不检查
    if report_date != today:
        return False

    # 检查是否已发送
    if marker.exists():
        try:
            last_sent = datetime.fromtimestamp(marker.stat().st_mtime).date()
            if last_sent == today:
                print(f"[跳过检查] 今日报告已发送（标记文件）")
                return True
        except Exception:
            pass

    return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="每日市场分析报告生成器")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y-%m-%d"),
                        help="报告日期 (YYYY-MM-DD)")
    parser.add_argument("--output", type=str, choices=["markdown", "email", "both"],
                        default="markdown", help="输出方式")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--force", action="store_true", help="强制执行（跳过组合数据日期检查）")
    
    args = parser.parse_args()
    
    print(f"🚀 开始生成 {args.date} 的市场报告...")
    print("=" * 60)
    
    # ── 检查是否需要跳过（基于标记文件）────────────────────────
    report_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    if not args.force and _should_skip_report(report_date):
        print(f"⏭️  今日报告已发送，跳过报告生成")
        return

    # 加载配置
    config = load_config()
    
    # 生成 Markdown 报告（保存用）
    print("\n📝 生成 Markdown 报告...")
    report_generator = AllWeatherMarketReport(config)
    md_report = report_generator.generate()
    
    # 保存 Markdown 报告
    output_dir = Path(__file__).parent.parent / "reports"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"daily_report_{args.date}.md"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md_report)
    
    print(f"✅ Markdown 报告已保存：{output_path}")
    
    # 生成 HTML 报告（邮件用）
    print("\n📝 生成 HTML 报告...")
    html_gen = ReportGenerator()
    html_report = html_gen.generate_html_report()
    
    # 邮件推送
    if args.output in ["email", "both"]:
        print("\n📧 发送 HTML 邮件...")
        send_email(html_report, config, args.date, is_html=True)
    
    print("\n" + "=" * 60)
    print("✅ 报告生成完成！")
    print(f"📁 保存位置：{output_path}")
    print(f"📊 报告长度：{len(md_report)} 字符")
    print("=" * 60)
    
    # 打印预览
    if args.debug:
        print("\n📋 报告预览 (前 1500 字符):")
        print(report[:1500])


if __name__ == "__main__":
    main()
