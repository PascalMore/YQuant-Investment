"""Shared prompt constants for Vision providers (SPEC-03-006 §4.6).

Both ``MiniMaxVisionProvider`` and ``ZAIVisionProvider`` consume the same
prompt so that schema mapping (``_normalize_columns`` / ``_clean_data``) is
the only place we need to deal with column-name drift.
"""

VISION_PROMPT = """请仔细分析这张图片，这是一张Excel表格截图（可能是持仓记录或交易记录）。

请提取所有数据行，每行数据用 JSON 对象表示，包含所有可见列的字段。
请根据图片实际内容判断格式，不要假设：

持仓格式字段：截止日期、产品名称、产品代码、Wind代码、资产名称、持仓比例、数量、市值(本币)、最新净值、最新份额、最新规模
交易格式字段：日期/截止日期、产品名称、产品代码、Wind代码、资产名称、变化比例（不是持仓比例）、变化金额（不是数量）、方向（买入/卖出）

重要：
- 如果看到"变化比例"、"变化金额"、"方向"等列，请使用这些确切的列名
- 如果看到"持仓比例"、"数量"等列，请使用这些确切的列名
- 不要混淆两种格式

返回格式：直接输出 JSON 数组，不要有额外的解释文字。"""
