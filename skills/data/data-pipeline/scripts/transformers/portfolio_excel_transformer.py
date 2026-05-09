"""
Excel → Nested JSON Transformer for Portfolio data.

Receives a pandas DataFrame from any source (Message text or Image OCR)
with columns: 截止日期/产品名称/产品代码/Wind代码/资产名称/
持仓比例/数量/市值（本币）/最新净值/最新份额/最新规模,
converts it into the nested JSON structure expected by image_portfolio_normalizer.

Output structure:
{
    "daily_data": [
        {
            "date": "2026-04-23",
            "products": [
                {
                    "产品代码": "80PF11234",
                    "产品名称": "",
                    "最新净值": 1.1,
                    "最新份额": 209090909.1,
                    "最新规模": 230000000,
                    "positions": [
                        {
                            "Wind代码": "002415.SZ",
                            "资产名称": "海康威视",
                            "持仓比例": 0.1169,
                            "数量": 2415,
                            "market_value": 2415,
                        },
                        ...
                    ]
                },
                ...
            ]
        },
        ...
    ]
}
"""
import sys
from pathlib import Path

# Inject venv packages so this module can run standalone
_venv = Path(__file__).parent.parent.parent / "common" / "paddleocr_table2excel" / ".venv" / "lib" / "python3.10" / "site-packages"
if str(_venv) not in sys.path:
    sys.path.insert(0, str(_venv))

import pandas as pd
from .base import BaseTransformer


class PortfolioExcelTransformer(BaseTransformer):
    """
    Converts Excel DataFrame from Message text or Image OCR into nested JSON.

    Input DataFrame columns (both full-width and ASCII variants accepted):
        截止日期, 产品名称, 产品代码, Wind代码, 资产名称,
        持仓比例, 数量, 市值（本币）/市值(本币), 最新净值, 最新份额, 最新规模

    Output: nested JSON dict with 'daily_data' key
    """

    def __init__(self):
        self.source_type = "excel_portfolio"

    # Standard column names - all use full-width parentheses
    _STD_COLS = {
        "截止日期", "产品名称", "产品代码", "Wind代码", "资产名称",
        "持仓比例", "数量", "最新净值", "最新份额", "最新规模",
    }
    # 市值(本币) has two common forms: full-width （） and ASCII ()
    _MV_COLS = ("市值（本币）", "市值(本币)")

    def _std_col(self, col: str) -> str | None:
        """
        Normalize column name to standard, or return None if not a standard col.
        Handles the common case of full-width vs ASCII parentheses in 市值(本币).
        """
        col = col.strip()
        if col in self._STD_COLS:
            return col
        # 市值(本币) → 市值（本币） regardless of parenthesis style
        if col in self._MV_COLS:
            return "市值（本币）"
        return None

    def transform(self, records: list[dict]) -> list[dict]:
        """
        Args:
            records: List containing a single dict with keys:
                - 'df': pandas DataFrame from Excel or OCR
                - 'source_path': original image path (optional, for logging)

        Returns:
            List containing a single dict with 'daily_data' key
        """
        if not records:
            return []

        record = records[0]
        df = record.get("df")
        if df is None:
            raise ValueError("No DataFrame found in records[0]['df']")

        if isinstance(df, str):
            # It's a file path — load it
            df = pd.read_excel(df)

        return self._convert(df)

    def _convert(self, df: pd.DataFrame) -> list[dict]:
        """
        Convert Excel DataFrame into nested JSON structure.

        Strategy:
        - Normalize all column names first (handles full-width vs ASCII parens)
        - Group by (date, product_code) to build product-level records
        - Aggregate positions per product
        """
        # ---- Normalize column names ----
        # 市值(本币) (ASCII parens) → 市值（本币）(full-width) in one pass
        rename_map = {c: self._std_col(c) for c in df.columns if self._std_col(c) is not None}
        if rename_map:
            df = df.rename(columns=rename_map)

        REQUIRED_COLS = ["截止日期", "产品代码", "资产名称", "持仓比例"]
        for col in REQUIRED_COLS:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # Drop rows where 产品代码 is null/empty
        df = df[df["产品代码"].notna() & (df["产品代码"].astype(str).str.strip() != "")]

        # Ensure numeric types (use standard col names after rename)
        for col in ["持仓比例", "数量", "市值（本币）", "最新净值", "最新份额", "最新规模"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        daily_data = []
        for date, date_group in df.groupby("截止日期", sort=False):
            products_map = {}

            for _, row in date_group.iterrows():
                code = str(row.get("产品代码", "")).strip()
                if not code:
                    continue

                if code not in products_map:
                    name = str(row.get("产品名称") or "").strip()
                    if name in ("", "nan", "None"):
                        name = ""
                    products_map[code] = {
                        "产品代码": code,
                        "产品名称": name,
                        "最新净值": self._to_float(row.get("最新净值")),
                        "最新份额": self._to_float(row.get("最新份额")),
                        "最新规模": self._to_int(row.get("最新规模")),
                        "positions": [],
                    }

                # Append position
                pos = {
                    "Wind代码": str(row.get("Wind代码") or "").strip(),
                    "资产名称": str(row.get("资产名称") or "").strip(),
                    "持仓比例": self._to_float(row.get("持仓比例")),
                    "数量": self._to_int(row.get("数量")),
                    "market_value": self._to_int(row.get("市值（本币）")),
                }
                products_map[code]["positions"].append(pos)

            daily_data.append({
                "date": str(date)[:10] if date else "",
                "products": list(products_map.values()),
            })

        return [{"daily_data": daily_data}]

    @staticmethod
    def _to_float(v):
        try:
            return float(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_int(v):
        try:
            if v is None:
                return None
            return int(float(v))
        except (ValueError, TypeError):
            return None
