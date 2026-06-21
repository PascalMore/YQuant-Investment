#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件发送脚本 - OpenClaw Skill
支持命令行参数和环境变量配置
"""

import smtplib
import os
import ssl
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

# ========== 配置区域 - 从环境变量读取，兼容 skills/.env ==========
SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.qq.com")
_port = os.getenv("EMAIL_SMTP_PORT")
SMTP_PORT = int(_port) if _port else 465
SENDER_EMAIL = os.getenv("EMAIL_SENDER")
SENDER_NAME = os.getenv("EMAIL_SENDER_NAME", "YQuant智能投资助手")
AUTHORIZATION_CODE = os.getenv("EMAIL_SMTP_PASSWORD") or os.getenv("EMAIL_PASSWORD")
USE_TLS = (os.getenv("EMAIL_USE_TLS") or "false").lower() == "true"
# ===============================================

def send_email(to_email, subject, content, attachment_path=None):
    """发送邮件
    
    Args:
        to_email: 收件人邮箱
        subject: 邮件主题
        content: 邮件正文
        attachment_path: 可选附件路径
    
    Returns:
        bool: 发送是否成功
    """
    if not all([SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, AUTHORIZATION_CODE]):
        print("❌ 错误：请配置环境变量 EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, EMAIL_SENDER, EMAIL_SMTP_PASSWORD（在 ~/.openclaw/openclaw.json skills.entries.send-email.env）")
        return False

    try:
        recipients = [email.strip() for email in to_email.split(",") if email.strip()]
        if not recipients:
            print("❌ 错误：收件人邮箱不能为空")
            return False

        # 创建邮件
        if attachment_path and os.path.exists(attachment_path):
            msg = MIMEMultipart()
            msg.attach(MIMEText(content, 'plain', 'utf-8'))
            # 添加附件
            from email.mime.base import MIMEBase
            from email import encoders
            with open(attachment_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {os.path.basename(attachment_path)}'
                )
                msg.attach(part)
        else:
            msg = MIMEMultipart()
            msg.attach(MIMEText(content, 'plain', 'utf-8'))

        msg['From'] = formataddr([SENDER_NAME, SENDER_EMAIL])
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject

        # 连接SMTP服务器并发送
        context = ssl.create_default_context()
        if USE_TLS:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls(context=context)
        else:
            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context)
        
        server.login(SENDER_EMAIL, AUTHORIZATION_CODE)
        server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
        server.quit()

        print(f"✅ 邮件已成功发送到: {', '.join(recipients)}")
        if attachment_path:
            print(f"   附件: {os.path.basename(attachment_path)}")
        return True

    except Exception as e:
        print(f"❌ 发送失败: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: send_email.py <收件人> <主题> <正文> [附件路径]")
        print("\n环境变量:")
        print("  EMAIL_SMTP_SERVER     SMTP 服务器（可选，默认 smtp.qq.com）")
        print("  EMAIL_SMTP_PORT       SMTP 端口（可选，默认 465）")
        print("  EMAIL_SENDER          发件人邮箱（必填）")
        print("  EMAIL_SMTP_PASSWORD   授权码/密码（必填，未设置时读取 EMAIL_PASSWORD）")
        print("  EMAIL_SENDER_NAME     发件人名称（可选）")
        print("  EMAIL_USE_TLS          true 使用 TLS，否则 SSL（可选）")
        sys.exit(1)
    
    to_email = sys.argv[1]
    subject = sys.argv[2]
    content = sys.argv[3]
    attachment = sys.argv[4] if len(sys.argv) > 4 else None
    
    success = send_email(to_email, subject, content, attachment)
    sys.exit(0 if success else 1)
