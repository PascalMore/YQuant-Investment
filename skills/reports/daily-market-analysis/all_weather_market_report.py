# -*- coding: utf-8 -*-
"""
全天候市场报告 - All Weather Market Report
"""

import os
import sys
from datetime import datetime, date
from typing import Dict, List, Optional

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_CURRENT_DIR, 'src'))
sys.path.insert(0, os.path.join(_CURRENT_DIR, 'src', 'new_services'))

INITIAL_ALLOCATION = {
    "A+H股": 0.53,
    "美股": 0.18,
    "中债": 0.18,
    "数字货币": 0.05,
    "大宗商品": 0.03,
    "美债": 0.03,
}


class AllWeatherMarketReport:
    def __init__(self, config=None):
        self.config = config
        self.report_date = date.today()
        self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M CST")
        self.initial_allocation = INITIAL_ALLOCATION.copy()
        self._data_adapter = None
        self._cn_review = None
        self._us_review = None
        self._hk_review = None
        self._crypto_review = None
    
    @property
    def data_adapter(self):
        if self._data_adapter is None:
            from new_services import get_market_adapter
            self._data_adapter = get_market_adapter(self.config)
        return self._data_adapter
    
    def generate(self) -> str:
        self._fetch_reviews()
        
        sections = [
            self._generate_header(),
            self._generate_market_overview(),
            self._generate_hot_news(),
            self._generate_market_reviews(),
            self._generate_financial_calendar(),
            self._generate_insights(),
        ]
        return "\n\n".join(filter(None, sections))
    
    def _fetch_reviews(self):
        self._cn_review = self._get_cn_review()
        self._us_review = self._get_us_review()
        hk_raw = self.data_adapter.get_hk_market_review()
        self._hk_review = self._strip_ai_tags(hk_raw) if hk_raw else None
        crypto_raw = self.data_adapter.get_crypto_market_review()
        self._crypto_review = self._strip_ai_tags(crypto_raw) if crypto_raw else None
    
    def _generate_header(self) -> str:
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][self.report_date.weekday()]
        return f"""# 📈 每日全球市场研究报告

**日期：** {self.report_date} {weekday}  
**生成时间：** {self.generated_at}"""
    
    def _summarize_review(self, review_text: str, max_sentences: int = 5) -> str:
        if not review_text:
            return "数据获取中..."
        
        lines = [l.strip() for l in review_text.split('\n') if l.strip()]
        key_points = []
        skip_keywords = ['#', '---', '**', '##', '```', '>>>']
        
        # 先收集所有普通句子（优先）和段落，再补充少量关键 bullet
        plain_sentences = []
        bullet_candidates = []
        
        for line in lines:
            if any(kw in line for kw in skip_keywords):
                continue
            if len(line) < 15:
                continue
            # Bullet points: only keep reasonable length ones
            if line.startswith('- ') or line.startswith('1.') or line.startswith('2.') or line.startswith('3.'):
                if 15 < len(line) <= 250:
                    bullet_candidates.append(line)
            # Plain sentences: keep all lengths (English analysis sentences are often long)
            else:
                plain_sentences.append(line)
            
            if len(plain_sentences) >= max_sentences:
                break
        
        # 优先用普通句子，不够才用 bullet 补充
        if len(plain_sentences) >= max_sentences:
            key_points = plain_sentences[:max_sentences]
        elif len(plain_sentences) > 0:
            key_points = plain_sentences + bullet_candidates[:max_sentences - len(plain_sentences)]
        else:
            key_points = bullet_candidates[:max_sentences]
        
        if len(key_points) < 3:
            for line in lines[len(lines)//3:len(lines)*2//3]:
                if line not in key_points and len(line) > 30 and not line.startswith('- '):
                    key_points.append(line)
                    if len(key_points) >= max_sentences:
                        break
        
        if len(key_points) < 3:
            for line in lines[len(lines)//3:len(lines)*2//3]:
                if line not in key_points and len(line) > 30:
                    key_points.append(line)
                    if len(key_points) >= max_sentences:
                        break
        
        if key_points:
            result = '；'.join(key_points[:max_sentences])
            result = result.replace('**', '').replace('- ', '').strip()
            return result if len(result) > 20 else "市场数据收集中..."
        return "市场数据获取中..."
    
    def _generate_market_overview(self) -> str:
        alloc_lines = " | ".join([f"{k} {int(v*100)}%" for k, v in self.initial_allocation.items()])
        
        cn_indices = self._get_cn_indices()
        hk_indices = self._get_hk_indices()
        us_indices = self._get_us_indices()
        crypto_data = self._get_crypto_data()
        
        cn_analysis = self._summarize_review(self._cn_review, 5) if self._cn_review else "数据获取中..."
        us_analysis = self._summarize_review(self._us_review, 5) if self._us_review else "数据获取中..."
        hk_analysis = self._summarize_review(self._hk_review, 3) if self._hk_review else "港股数据获取中..."
        crypto_analysis = self._get_crypto_analysis(crypto_data)
        
        shanghai = self._find_index(cn_indices, ["上证指数", "000001"])
        hs300 = self._find_index(cn_indices, ["沪深300", "000300", "HS300"])
        hsi = self._find_index(hk_indices, ["恒生指数", "HSI"])
        hstech = self._find_index(hk_indices, ["恒生科技", "HSTECH"])
        spx = self._find_index(us_indices, ["标普", "SPX", "S&P"])
        nasdaq = self._find_index(us_indices, ["纳斯达克", "NDX", "NASDAQ"])
        
        rows = []
        
        # A 股：上证指数
        if shanghai:
            emoji = self._emoji(shanghai.get('change_pct', 0))
            price = shanghai.get('current', shanghai.get('price', 0))
            change = shanghai.get('change_pct', 0)
            rows.append(f"| 上证指数 | {emoji} {price:.2f} | {change:+.2f}% | {cn_analysis} | 标配 40% | 核心资产 |")
        else:
            rows.append(f"| 上证指数 | ⚪ — | — | {cn_analysis} | 标配 40% | 核心资产 |")
        
        # A 股：沪深300（重复分析）
        if hs300:
            emoji = self._emoji(hs300.get('change_pct', 0))
            price = hs300.get('current', hs300.get('price', 0))
            change = hs300.get('change_pct', 0)
            rows.append(f"| 沪深300 | {emoji} {price:.2f} | {change:+.2f}% | {cn_analysis} | 标配 40% | 核心资产 |")
        else:
            rows.append(f"| 沪深300 | ⚪ — | — | {cn_analysis} | 标配 40% | 核心资产 |")
        
        # 港股：恒生指数
        if hsi:
            emoji = self._emoji(hsi.get('change_pct', 0))
            price = hsi.get('current', hsi.get('price', 0))
            change = hsi.get('change_pct', 0)
            rows.append(f"| 恒生指数 | {emoji} {price:.2f} | {change:+.2f}% | {hk_analysis} | 低配 15% | 南向待观察 |")
        else:
            rows.append(f"| 恒生指数 | ⚪ — | — | {hk_analysis} | 低配 15% | 南向待观察 |")
        
        # 港股：恒生科技（重复分析）
        if hstech:
            emoji = self._emoji(hstech.get('change_pct', 0))
            price = hstech.get('current', hstech.get('price', 0))
            change = hstech.get('change_pct', 0)
            rows.append(f"| 恒生科技 | {emoji} {price:.2f} | {change:+.2f}% | {hk_analysis} | 低配 15% | 南向待观察 |")
        else:
            rows.append(f"| 恒生科技 | ⚪ — | — | {hk_analysis} | 低配 15% | 南向待观察 |")
        
        # 美股：标普500
        if spx:
            emoji = self._emoji(spx.get('change_pct', 0))
            price = spx.get('current', spx.get('price', 0))
            change = spx.get('change_pct', 0)
            rows.append(f"| 标普500 | {emoji} {price:.2f} | {change:+.2f}% | {us_analysis} | 标配 20% | 估值偏高 |")
        else:
            rows.append(f"| 标普500 | ⚪ — | — | {us_analysis} | 标配 20% | 估值偏高 |")
        
        # 美股：纳斯达克（重复分析）
        if nasdaq:
            emoji = self._emoji(nasdaq.get('change_pct', 0))
            price = nasdaq.get('current', nasdaq.get('price', 0))
            change = nasdaq.get('change_pct', 0)
            rows.append(f"| 纳斯达克 | {emoji} {price:.2f} | {change:+.2f}% | {us_analysis} | 标配 20% | 估值偏高 |")
        else:
            rows.append(f"| 纳斯达克 | ⚪ — | — | {us_analysis} | 标配 20% | 估值偏高 |")
        
        # BTC
        btc = self._find_crypto(crypto_data, ["BTC", "比特币"])
        if btc:
            emoji = self._emoji(btc.get('change_pct', 0))
            price = btc.get('price', 0)
            change = btc.get('change_pct', 0)
            if price >= 1000:
                price_str = f"${price:,.0f}"
            else:
                price_str = f"${price:,.2f}"
            rows.append(f"| BTC | {emoji} {price_str} | {change:+.2f}% | {crypto_analysis} | 超配 10% | ETF净流入 |")
        else:
            rows.append(f"| BTC | ⚪ — | — | {crypto_analysis} | 超配 10% | ETF净流入 |")
        
        # 黄金/原油
        commodity_data = self._get_commodity_data()
        bond_data = self._get_bond_data()
        for item in commodity_data:
            emoji = self._emoji(item.get('change_pct', 0))
            price = item.get('price', 0)
            change = item.get('change_pct', 0)
            amount = item.get('amount', 0)
            amount_str = f"{amount/1e8:.2f}亿" if amount >= 1e8 else f"{amount/1e4:.2f}万" if amount >= 1e4 else "-"
            name = item.get('name', '')
            code = item.get('code', '')
            unit = item.get('unit', '')
            # 大宗商品：名称加上期货代码（如 黄金 AU2606、原油 SC2605）
            if code and not code.isalpha() and '.' in code:
                display_name = f"{name} {code.split('.')[0]}"  # AU2606.SHF → AU2606
            else:
                display_name = name
            if name == '黄金':
                rows.append(f"| {display_name} | {emoji} {price:.2f}{unit} | {change:+.2f}% | 成交金额 {amount_str} | 标配 5% | — |")
            elif name == '原油':
                rows.append(f"| {display_name} | {emoji} {price:.2f}{unit} | {change:+.2f}% | 成交金额 {amount_str} | 低配 3% | — |")

        # 债券
        for item in bond_data:
            name = item.get('name', '')
            rate = item.get('rate_10y', 0)
            if '美国' in name:
                chg_bp = item.get('change_pct', 0)
                chg_str = f"+{chg_bp:.0f}bp" if chg_bp > 0 else (f"{chg_bp:.0f}bp" if chg_bp < 0 else "0bp")
                rows.append(f"| 美国国债(10Y) | ⚪ {rate:.2f}% | {chg_str} | 参考利率 | 标配 3% | — |")
            elif '中国' in name:
                chg_bp = item.get('change_pct', 0)
                chg_str = f"+{chg_bp:.0f}bp" if chg_bp > 0 else (f"{chg_bp:.0f}bp" if chg_bp < 0 else "0bp")
                rows.append(f"| 中国国债(10Y) | ⚪ {rate:.2f}% | {chg_str} | 参考利率 | 超配 5% | — |")
        
        table = f"""## 一、全球市场概览

📊 **初始配置比例：** {alloc_lines}

| 市场 | 最新价 | 涨跌幅 | 市场分析 | 仓位建议 | 理由 |
|------|--------|--------|----------|----------|------|
"""
        table += '\n'.join(rows)
        
        return table
    
    def _emoji(self, value) -> str:
        if value > 0:
            return "🟢"
        elif value < 0:
            return "🔴"
        else:
            return "⚪"
    
    def _get_crypto_analysis(self, crypto_data: List[Dict]) -> str:
        if not crypto_data:
            return "数据获取中..."
        
        btc = self._find_crypto(crypto_data, ["BTC", "比特币"])
        if not btc:
            return "数据获取中..."
        
        change = btc.get('change_pct', 0)
        if change > 5:
            return "BTC 强势突破，市场 FOMO 情绪升温"
        elif change > 2:
            return "BTC 震荡偏强，市场情绪乐观"
        elif change > 0:
            return "BTC 小幅上涨，趋势偏多"
        elif change < -5:
            return "BTC 大幅回调，注意风险控制"
        elif change < -2:
            return "BTC 震荡偏弱，市场情绪谨慎"
        elif change < 0:
            return "BTC 小幅下跌，观望情绪浓厚"
        else:
            return "BTC 横盘整理，等待方向选择"
    
    def _find_index(self, indices: List[Dict], names: List[str]) -> Optional[Dict]:
        for idx in indices:
            name = idx.get('name', '')
            code = idx.get('code', '')
            for target in names:
                if target in name or target in code:
                    return idx
        return indices[0] if indices else None
    
    def _find_crypto(self, crypto_data: List[Dict], symbols: List[str]) -> Optional[Dict]:
        for c in crypto_data:
            sym = c.get('symbol', '')
            name = c.get('name', '')
            for target in symbols:
                if target in sym or target in name:
                    return c
        return crypto_data[0] if crypto_data else None
    
    def _get_cn_indices(self) -> List[Dict]:
        try:
            return self.data_adapter.get_cn_index_data()
        except:
            return []
    
    def _get_hk_indices(self) -> List[Dict]:
        try:
            return self.data_adapter.get_hk_index_data()
        except:
            return []
    
    def _get_us_indices(self) -> List[Dict]:
        try:
            return self.data_adapter.get_us_index_data()
        except:
            return []
    
    def _get_crypto_data(self) -> List[Dict]:
        try:
            return self.data_adapter.get_crypto_data()
        except:
            return []

    def _get_commodity_data(self) -> List[Dict]:
        try:
            return self.data_adapter.get_commodity_data()
        except:
            return []

    def _get_bond_data(self) -> List[Dict]:
        try:
            return self.data_adapter.get_bond_data()
        except:
            return []

    def _generate_hot_news(self) -> str:
        global_news = self.data_adapter.get_global_news(limit=3)
        cn_news = self.data_adapter.get_market_news("cn", limit=3)
        hk_news = self.data_adapter.get_market_news("hk", limit=3)
        us_news = self.data_adapter.get_market_news("us", limit=3)
        crypto_news = self.data_adapter.get_market_news("crypto", limit=3)
        commodity_news = self.data_adapter.get_market_news("commodity", limit=3)
        
        lines = ["## 二、热点资讯 Top 3 (过去24小时)", ""]
        
        lines.append("### 🌍 全球宏观影响力")
        if global_news:
            for i, news in enumerate(global_news[:3], 1):
                title = news.get('title', '无标题')
                source = news.get('source', '未知来源')
                lines.append(f"{i}. **{title}**")
                lines.append(f"   → 来源：{source}")
        else:
            lines.append("1. 【待接入】")
            lines.append("2. 【待接入】")
            lines.append("3. 【待接入】")
        
        lines.append("")
        lines.append("### 🇨🇳 A 股市场")
        if cn_news:
            for i, news in enumerate(cn_news[:3], 1):
                lines.append(f"{i}. {news.get('title', '—')}")
        else:
            lines.append("1. 【待接入】")
            lines.append("2. 【待接入】")
            lines.append("3. 【待接入】")
        
        lines.append("")
        lines.append("### 🇭🇰 港股市场")
        if hk_news:
            for i, news in enumerate(hk_news[:3], 1):
                lines.append(f"{i}. {news.get('title', '—')}")
        else:
            lines.append("1. 【待接入】")
            lines.append("2. 【待接入】")
            lines.append("3. 【待接入】")
        
        lines.append("")
        lines.append("### 🇺🇸 美股市场")
        if us_news:
            for i, news in enumerate(us_news[:3], 1):
                lines.append(f"{i}. {news.get('title', '—')}")
        else:
            lines.append("1. 【待接入】")
            lines.append("2. 【待接入】")
            lines.append("3. 【待接入】")
        
        lines.append("")
        lines.append("### ₿ 数字货币")
        if crypto_news:
            for i, news in enumerate(crypto_news[:3], 1):
                lines.append(f"{i}. {news.get('title', '—')}")
        else:
            lines.append("1. 【待接入】")
            lines.append("2. 【待接入】")
            lines.append("3. 【待接入】")
        
        lines.append("")
        lines.append("### 🥇 大宗商品")
        if commodity_news:
            for i, news in enumerate(commodity_news[:3], 1):
                lines.append(f"{i}. {news.get('title', '—')}")
        else:
            lines.append("1. 【待接入】")
            lines.append("2. 【待接入】")
            lines.append("3. 【待接入】")
        
        return "\n".join(lines)


    def _generate_market_reviews(self) -> str:
        sections = ["## 三、各市场复盘", ""]
        
        sections.append("### 3.1 A 股市场复盘")
        sections.append(self._cn_review if self._cn_review else "[获取失败]")
        sections.append("")
        
        sections.append("### 3.2 美股市场复盘")
        sections.append(self._us_review if self._us_review else "[获取失败]")
        sections.append("")
        
        sections.append("### 3.3 港股市场复盘")
        sections.append(self._hk_review if self._hk_review else "[获取失败]")
        sections.append("")
        
        sections.append("### 3.4 数字货币市场复盘")
        sections.append(self._crypto_review if self._crypto_review else "[获取失败]")
        sections.append("")
        
        sections.append("### 3.5 大宗商品市场复盘")
        sections.append(self.data_adapter.get_commodity_market_review())
        sections.append("")
        
        sections.append("### 3.6 债券市场复盘")
        sections.append(self.data_adapter.get_bond_market_review())
        
        return "\n".join(sections)
    
    def _strip_ai_tags(self, text: str) -> str:
        """去掉文本中的 AI 思考标签和残余内容"""
        import re
        # 去掉 <think> ...（有闭合）和 <think> ...（无闭合）
        text = re.sub(r'<th[\s\S]*?>', '', text)   # 去掉 <th...> 到对应 </th>（非贪婪）
        text = re.sub(r'<th[\s\S]*', '', text)    # 去掉 <th...> 到字符串末尾（无闭合）
        # 去掉 Markdown 图片/链接格式残留（AI 思考中可能插入的链接）
        text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
        return text.strip()

    def _get_cn_review(self) -> Optional[str]:
        try:
            review = self.data_adapter.get_cn_market_review()
            if review:
                review = self._strip_ai_tags(review)
                lines = review.split('\n')
                result_lines = []
                skip_title = True
                for line in lines:
                    if skip_title and line.startswith('#'):
                        continue
                    skip_title = False
                    result_lines.append(line)
                return '\n'.join(result_lines).strip()
            return None
        except Exception as e:
            print(f"[Report] A 股复盘获取失败：{e}")
            return None
    
    def _get_us_review(self) -> Optional[str]:
        try:
            review = self.data_adapter.get_us_market_review()
            if review:
                review = self._strip_ai_tags(review)
                lines = review.split('\n')
                result_lines = []
                skip_title = True
                for line in lines:
                    if skip_title and line.startswith('#'):
                        continue
                    skip_title = False
                    result_lines.append(line)
                return '\n'.join(result_lines).strip()
            return None
        except Exception as e:
            print(f"[Report] 美股复盘获取失败：{e}")
            return None
    
    def _generate_financial_calendar(self) -> str:
        calendar = self.data_adapter.get_financial_calendar(days=30)
        if calendar:
            lines = ["| 日期 | 事件 | 市场 | 预期影响 |", "|------|------|------|----------|"]
            for event in calendar:
                lines.append(f"| {event.get('date', '-')} | {event.get('event', '-')} | {event.get('market', '-')} | {event.get('impact', '-')} |")
            table = "\n".join(lines)
        else:
            table = "| 日期 | 事件 | 市场 | 预期影响 |\n|------|------|------|----------|\n| — | 金融日历数据待接入 | — | — |"
        
        return f"## 四、金融日历\n\n{table}"
    
    def _generate_insights(self) -> str:
        return """## 五、小Q洞察

🎯 **今日核心判断：**
- 风险偏好：—
- 重点关注：—

💡 **机会提示：**
1. —

⚠️ **风险提示：**
1. —

📋 **操作建议：**
| 操作 | 标的 | 理由 |
|------|------|------|
| — | — | — |

---
*本报告仅供参考，不构成投资建议。*"""


def generate_report() -> str:
    report = AllWeatherMarketReport()
    return report.generate()


def main():
    print("正在生成每日市场报告...")
    print("=" * 60)
    report = generate_report()
    print(report)
    print("=" * 60)
    print(f"报告生成完成，长度：{len(report)} 字符")


if __name__ == "__main__":
    main()



