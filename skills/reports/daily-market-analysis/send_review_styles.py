#!/usr/bin/env python3
"""发送复盘样式预览邮件（样式B · 简约卡片）"""
import sys, os, re, ssl, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/src')
from new_services.market_data_adapter import MarketDataAdapter
from new_services.report_generator import ReportGenerator

# 获取数据
a = MarketDataAdapter()
r = ReportGenerator()

cn_review = a.get_cn_market_review() or ""
us_review = a.get_us_market_review() or ""

# LLM 总结作为副标题
cn_summary = r._get_analysis("A股") or "暂无分析"
us_summary = r._get_analysis("美股") or "暂无分析"

# 去掉 markdown 第一行大标题（## 2026-04-17 大盘复盘 / ## US Market Recap）
def strip_first_heading(text):
    lines = text.split('\n')
    # 跳过第一个 ## 开头的标题行
    start = 0
    for i, line in enumerate(lines):
        if re.match(r'^#{1,2}\s+\S', line.strip()):
            start = i + 1
            break
    return '\n'.join(lines[start:]).strip()

cn_body = strip_first_heading(cn_review)
us_body = strip_first_heading(us_review)

# ─── MD → HTML（含表格转换）─────────────────────────────
def md_to_html(text):
    html = text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    html = re.sub(r'```(\w+)?\n(.*?)```', r'<pre><code>\2</code></pre>', html, flags=re.DOTALL)
    html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
    # 去掉 ## 标题（正文已无大标题）
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)

    def convert_table_block(m):
        block = m.group(0)
        lines = [l for l in block.strip().split('\n') if l.startswith('|')]
        if len(lines) < 2:
            return block
        headers = [c.strip() for c in lines[0].split('|')[1:-1]]
        aligns = []
        if len(lines) > 1 and '---' in lines[1]:
            for cell in lines[1].split('|')[1:-1]:
                cell = cell.strip()
                if ':' in cell:
                    align = 'center' if cell.startswith(':') and cell.endswith(':') else ('left' if cell.startswith(':') else 'right')
                else:
                    align = 'left'
                aligns.append(align)
        start = 3 if len(lines) > 1 and '---' in lines[1] else 1
        rows_html = ''
        for row in lines[start:]:
            cells = [c.strip() for c in row.split('|')[1:-1]]
            cells_html = ''.join(
                f'<td style="text-align:{aligns[i] if i < len(aligns) else "left"};padding:6px 10px;border-bottom:1px solid #eee">{cells[i] if i < len(cells) else ""}</td>'
                for i in range(len(cells))
            )
            rows_html += f'<tr>{cells_html}</tr>'
        header_html = ''.join(
            f'<th style="text-align:{aligns[i] if i < len(aligns) else "left"};padding:7px 10px;background:#f5f5f5;font-weight:600;font-size:12px;border-bottom:2px solid #ddd">{h}</th>'
            for i, h in enumerate(headers)
        )
        return f'<table style="width:100%;border-collapse:collapse;font-size:13px;margin:10px 0">{header_html}{rows_html}</table>'

    html = re.sub(r'\|.+\|(?:\n\|.+\|)+', convert_table_block, html)

    lines = html.split('\n')
    result, in_list = [], False
    for line in [l.strip() for l in lines if l.strip()]:
        if line.startswith('<h') or line.startswith('<pre') or line.startswith('<table') or line.startswith('<blockquote'):
            if in_list:
                result.append('</ul>')
                in_list = False
            result.append(line)
        elif line.startswith('- ') or line.startswith('* '):
            if not in_list:
                result.append('<ul>')
                in_list = True
            result.append(f'  <li>{line[2:]}</li>')
        elif line[0].isdigit() and '. ' in line[:5]:
            if not in_list:
                result.append('<ol>')
                in_list = True
            result.append(f'  <li>{line[line.index(". ")+2:]}</li>')
        else:
            if in_list:
                result.append('</ul>')
                in_list = False
            result.append(f'<p>{line}</p>')
    if in_list:
        result.append('</ul>')
    return '\n'.join(result)

# ─── 样式B CSS（简约卡片）──────────────────────────────
STYLE_B_CSS = """
.market-review-b { display:flex; flex-direction:column; gap:12px }
.market-review-b .review-card { background:#fafafa; border-radius:10px; border:1px solid #e8e8e8; overflow:hidden }
.market-review-b .review-card-header { padding:10px 16px; display:flex; align-items:flex-start; gap:10px; border-bottom:1px solid #e8e8e8 }
.market-review-b .review-card-header .market-emoji { font-size:20px; flex-shrink:0; margin-top:1px }
.market-review-b .review-card-header .market-title { font-size:14px; font-weight:700; color:#1a1a1a; line-height:1.35 }
.market-review-b .review-card-header .market-summary { font-size:12px; color:#555; line-height:1.55; margin-top:1px; word-break:break-all }
.market-review-b .review-cn  .review-card-header .market-dot { display:none }
.market-review-b .review-us  .review-card-header .market-dot { display:none }
.market-review-b .review-cn  .review-card-header .market-dot { background:#e74c3c }
.market-review-b .review-us  .review-card-header .market-dot { background:#2980b9 }
.market-review-b .review-card-body { padding:13px 16px; height:300px; overflow-y:auto; -webkit-overflow-scrolling:touch; scrollbar-width:thin; scrollbar-color:#bbb transparent }
.market-review-b .review-card-body::-webkit-scrollbar { width:4px }
.market-review-b .review-card-body::-webkit-scrollbar-thumb { background:#bbb; border-radius:2px }
.market-review-b .md-content { font-size:13px; line-height:1.8; color:#444 }
.market-review-b .md-content h2 { font-size:13.5px; font-weight:600; margin:11px 0 6px; color:#222 }
.market-review-b .md-content h3 { font-size:13px; font-weight:600; margin:8px 0 4px; color:#333 }
.market-review-b .md-content p { margin:0 0 7px }
.market-review-b .md-content ul,.market-review-b .md-content ol { margin:0 0 7px; padding-left:18px }
.market-review-b .md-content li { margin-bottom:3px }
.market-review-b .md-content strong { font-weight:700; color:#111 }
.market-review-b .md-content blockquote { border-left:3px solid #ccc; padding:5px 10px; color:#777; margin:7px 0 }
.market-review-b .md-content code { background:#f0f0f0; padding:1px 4px; border-radius:2px; font-size:11.5px; color:#c0392b }
.market-review-b .md-content table { width:100%; border-collapse:collapse; font-size:12.5px; margin:9px 0 }
.market-review-b .md-content th { background:#f5f5f5; font-weight:600; padding:6px 8px; border-bottom:1px solid #ddd; text-align:left }
.market-review-b .md-content td { padding:5px 8px; border-bottom:1px solid #f5f5f5 }
.market-review-b .md-content .up { color:#e74c3c;font-weight:600 }
.market-review-b .md-content .down { color:#27ae60;font-weight:600 }
"""

def make_card(emoji, title, summary, content, css_class):
    header = f"""<div class="review-card-header">
        <div style="flex:1;min-width:0">
            <div class="market-title">{title} {emoji}</div>
            <div class="market-summary">{summary}</div>
        </div>
    </div>"""
    return f'<div class="review-card {css_class}">{header}<div class="review-card-body"><div class="md-content">{md_to_html(content)}</div></div></div>'

cn_card = make_card("🇨🇳", "A股复盘", cn_summary, cn_body, "review-cn")
us_card = make_card("🇺🇸", "美股复盘", us_summary, us_body, "review-us")

html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>样式B · 简约卡片</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;background:#f0f2f5;padding:20px 16px}}
.header{{text-align:center;margin-bottom:24px}}
.header h1{{font-size:20px;font-weight:700;color:#1a1a1a;margin-bottom:4px}}
.header p{{font-size:12px;color:#999}}
{STYLE_B_CSS}
</style></head>
<body>
<div class="header">
    <h1>📊 样式B · 简约卡片</h1>
    <p>固定高度300px · LLM总结为副标题 · 正文已去掉大标题</p>
</div>
<div class="market-review-b">{cn_card}{us_card}</div>
</body></html>"""

def do_send(html_content, subject):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = formataddr(('YQuant智能投资助手', '532484187@qq.com'))
    msg['To'] = '532484187@qq.com'
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    ctx = ssl.create_default_context()
    server = smtplib.SMTP_SSL('smtp.qq.com', 465, context=ctx)
    server.login('532484187@qq.com', 'vyzfsxtfuqufcaed')
    server.send_message(msg)
    server.quit()
    print(f"✅ {subject}")

do_send(html, "【样式B定稿版】复盘卡片预览")
