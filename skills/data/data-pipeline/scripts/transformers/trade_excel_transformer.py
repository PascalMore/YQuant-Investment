"""
Trade → Nested JSON Transformer for Portfolio Trade data.

Receives a pandas DataFrame from Message text or Image OCR with columns:
    日期, 产品代码, 产品名称, Wind代码, 资产名称, 变化比例, 变化金额, 方向

Output structure:
{
    "daily_data": [
        {
            "date": "2026-05-07",
            "products": [
                {
                    "产品代码": "SM001",
                    "产品名称": "JS-001",
                    "trades": [
                        {
                            "Wind代码": "603893.SH",
                            "资产名称": "瑞芯微",
                            "change_ratio": 0.0026,
                            "change_amount": 671297,
                            "direction": "买入",
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


class TradeExcelTransformer(BaseTransformer):
    """
    Converts Excel DataFrame from Message text or Image OCR into nested JSON for trade data.

    Input DataFrame columns (both full-width and ASCII variants accepted):
        日期, 产品代码, 产品名称, Wind代码, 资产名称, 变化比例, 变化金额, 方向

    Output: nested JSON dict with 'daily_data' key
    """

    def __init__(self):
        self.source_type = "excel_trade"

    # Standard column names and aliases
    _COL_MAP = {
        # 日期 variants
        "截止日期": "日期", "date": "日期", "日期": "日期",
        # 产品代码 variants
        "产品代码": "产品代码", "代码": "产品代码",
        # 产品名称 variants
        "产品名称": "产品名称", "产品": "产品名称",
        # Wind代码 variants
        "Wind代码": "Wind代码", "Wind": "Wind代码",
        # 资产名称 variants
        "资产名称": "资产名称", "资产": "资产名称",
        # 变化比例 variants
        "变化比例": "变化比例", "比例": "变化比例",
        # 变化金额 variants
        "变化金额": "变化金额", "金额": "变化金额",
        # 方向 variants
        "方向": "方向",
    }
    _STD_COLS = set(_COL_MAP.values())  # {"日期", "产品代码", ...}

    def _std_col(self, col: str) -> str | None:
        """Normalize column name to standard via _COL_MAP."""
        return self._COL_MAP.get(col.strip()) or self._COL_MAP.get(col)

    def transform(self, records: list[dict]) -> list[dict]:
        """
        Args:
            records: List containing a single dict with keys:
                - 'df': pandas DataFrame from Excel or OCR
                - 'source_path': original path (optional, for logging)

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
            df = pd.read_excel(df)

        return self._convert(df)

    def _convert(self, df: pd.DataFrame) -> list[dict]:
        """Convert Excel DataFrame into nested JSON structure for trades."""
        # ---- Normalize column names ----
        rename_map = {c: self._std_col(c) for c in df.columns if self._std_col(c) is not None}
        if rename_map:
            df = df.rename(columns=rename_map)

        REQUIRED_COLS = ["日期", "产品代码", "资产名称", "方向"]
        for col in REQUIRED_COLS:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # Drop rows where 产品代码 is null/empty
        df = df[df["产品代码"].notna() & (df["产品代码"].astype(str).str.strip() != "")]

        # Ensure numeric types for 变化金额 (变化比例 is string % and handled per-row)
        for col in ["变化金额"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Normalize direction values
        if "方向" in df.columns:
            df["方向"] = df["方向"].apply(lambda x: str(x).strip())

        daily_data = []
        for date, date_group in df.groupby("日期", sort=False):
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
                        "trades": [],
                    }

                # Normalize change_ratio: "0.26%" → 0.0026
                # OCR may output "变化比例" or "持仓比例" depending on image content
                change_ratio = row.get("变化比例") or row.get("持仓比例")
                if pd.notna(change_ratio) and isinstance(change_ratio, str):
                    if "%" in change_ratio:
                        change_ratio = float(change_ratio.replace("%", "").strip()) / 100
                    else:
                        change_ratio = float(change_ratio)
                elif pd.isna(change_ratio):
                    change_ratio = None
                else:
                    change_ratio = float(change_ratio)

                # Append trade
                trade = {
                    "Wind代码": str(row.get("Wind代码") or "").strip(),
                    "资产名称": str(row.get("资产名称") or "").strip(),
                    "change_ratio": self._to_float(change_ratio),
                    "change_amount": self._to_float(row.get("变化金额")),
                    "direction": str(row.get("方向") or "").strip(),
                }
                products_map[code]["trades"].append(trade)

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
