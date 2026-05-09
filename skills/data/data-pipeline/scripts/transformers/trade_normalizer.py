"""
Normalize decoded trade JSON into flat record lists.

Input: nested JSON dict with 'daily_data' key from TradeExcelTransformer
Output: dict with 'trade' key mapping to list of flat trade records
"""

from typing import Any


def normalize_all(decoded: dict) -> dict:
    """
    Normalize entire decoded trade JSON.

    Args:
        decoded: Full decoded JSON from trade data with 'daily_data' key.

    Returns:
        Dict with 'trade' key mapping to record list.
    """
    records = []

    date = decoded.get("date")
    for product in decoded.get("products", []):
        product_code = product.get("产品代码")
        for trade in product.get("trades", []):
            records.append({
                "trade_date": date,
                "product_code": product_code,
                "asset_wind_code": trade.get("Wind代码"),
                "asset_name": trade.get("资产名称"),
                "change_ratio": trade.get("change_ratio"),
                "change_amount": trade.get("change_amount"),
                "direction": trade.get("direction"),
            })

    return {"trade": records}
