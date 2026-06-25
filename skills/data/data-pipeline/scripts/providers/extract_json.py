"""Robust JSON extraction + DataFrame normalisation shared by all providers.

Two responsibilities:

  1. ``extract_json(raw)``  : take the raw text returned by an LLM/VLM and
     pull out the first JSON array (or object). Handles markdown fences
     (```json ...``` and ``` ...```), surrounding prose, and full-width
     brackets. Returns the parsed list[dict] or None on failure.

  2. ``normalize_columns(df)`` + ``clean_data(df)`` + ``_parse_date`` /
     ``_parse_percentage`` / ``_parse_number`` : standardise the OCR output
     to the column names and value shapes expected by the downstream
     ``PortfolioExcelTransformer`` / ``TradeExcelTransformer``.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*([\s\S]*?)\s*```")
_ARRAY_RE = re.compile(r"(\[[\s\S]*?\])")
_OBJECT_RE = re.compile(r"(\{[\s\S]*?\})")


def extract_json(raw: str) -> list[dict[str, Any]] | None:
    """Extract a JSON list[dict] from raw LLM/VLM output.

    Strategy (in order):
      1. Strip a markdown ```json ... ``` (or ``` ... ```) fence.
      2. Match the first balanced JSON array in the text.
      3. Fallback: match the first JSON object (then wrap in a list).
      4. Return None when nothing parses.
    """
    if not raw:
        return None
    text = raw.strip()

    # 1. Markdown fence
    fence = _FENCE_RE.search(text)
    if fence:
        candidate = fence.group(1).strip()
        parsed = _try_loads(candidate)
        if parsed is not None:
            return _coerce_list(parsed)

    # 2. JSON array (greedy from first '[' to last ']')
    arr = _find_balanced_array(text)
    if arr is not None:
        parsed = _try_loads(arr)
        if parsed is not None:
            return _coerce_list(parsed)

    # 3. JSON object
    obj_match = _OBJECT_RE.search(text)
    if obj_match:
        candidate = obj_match.group(1)
        parsed = _try_loads(candidate)
        if parsed is not None and isinstance(parsed, dict):
            return [parsed]

    return None


def _try_loads(s: str) -> Any:
    """json.loads with trimmed trailing commas & tolerant whitespace."""
    if not s:
        return None
    cleaned = s.strip()
    # Tolerate trailing commas (some LLMs emit them)
    cleaned = re.sub(r",\s*([\]\}])", r"\1", cleaned)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None


def _find_balanced_array(text: str) -> str | None:
    """Find the first balanced JSON array in ``text``."""
    start = text.find("[")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        # Unbalanced → no more balanced arrays from this start
        start = text.find("[", start + 1)
    return None


def _coerce_list(parsed: Any) -> list[dict[str, Any]] | None:
    """Coerce parsed JSON into list[dict], or return None if it can't be."""
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)] or None
    if isinstance(parsed, dict):
        return [parsed]
    return None


# ---------------------------------------------------------------------------
# Column normalisation (SPEC-03-006 §4.6)
# ---------------------------------------------------------------------------

# Both MiniMax and Z.AI outputs may include English / snake_case aliases.
# We standardise to the Chinese column names that the existing
# PortfolioExcelTransformer / TradeExcelTransformer / detect_format expect.
_COLUMN_MAP: dict[str, str] = {
    # Dates
    "截止日期": "截止日期",
    "date": "截止日期",
    "asOfDate": "截止日期",
    "as_of_date": "截止日期",
    "asofdate": "截止日期",
    "日期": "截止日期",
    # Product name
    "产品名称": "产品名称",
    "name": "产品名称",
    "fundName": "产品名称",
    "fund_name": "产品名称",
    "基金名称": "产品名称",
    # Product code
    "产品代码": "产品代码",
    "code": "产品代码",
    "productCode": "产品代码",
    "product_code": "产品代码",
    "基金代码": "产品代码",
    # Wind code
    "Wind代码": "Wind代码",
    "windCode": "Wind代码",
    "wind_code": "Wind代码",
    "windcode": "Wind代码",
    # Asset name
    "资产名称": "资产名称",
    "assetName": "资产名称",
    "asset_name": "资产名称",
    "assetname": "资产名称",
    "holdingName": "资产名称",
    "holding_name": "资产名称",
    "持仓名称": "资产名称",
    "证券名称": "资产名称",
    # Holding ratio
    "持仓比例": "持仓比例",
    "ratio": "持仓比例",
    "positionRatio": "持仓比例",
    "position_ratio": "持仓比例",
    "比例": "持仓比例",
    "占比": "持仓比例",
    # Shares
    "数量": "数量",
    "shares": "数量",
    "持有数量": "数量",
    "股数": "数量",
    # Market value
    "市值(本币)": "市值(本币)",
    "marketValue": "市值(本币)",
    "market_value": "市值(本币)",
    "marketvalue": "市值(本币)",
    "value": "市值(本币)",
    "市值": "市值(本币)",
    # Latest NAV
    "最新净值": "最新净值",
    "nav": "最新净值",
    "净值": "最新净值",
    # Latest shares
    "最新份额": "最新份额",
    "share": "最新份额",
    "份额": "最新份额",
    "持有份额": "最新份额",
    # AUM
    "最新规模": "最新规模",
    "aum": "最新规模",
    "规模": "最新规模",
    "总规模": "最新规模",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to the standard Chinese names used by downstream code.

    Strategy: exact match first; if no exact match, do a case-insensitive
    substring match against the mapping keys. Columns with no mapping are
    preserved unchanged.
    """
    if df.empty:
        return df
    rename: dict[str, str] = {}
    used: set[str] = set()
    for col in df.columns:
        if col in _COLUMN_MAP:
            target = _COLUMN_MAP[col]
            if target not in used or col == target:
                rename[col] = target
                used.add(target)
    if rename:
        df = df.rename(columns=rename)
    return df


# ---------------------------------------------------------------------------
# Data cleaning
# ---------------------------------------------------------------------------

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y%m%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
)
_NUMERIC_COLUMNS = ("数量", "市值(本币)", "最新净值", "最新份额", "最新规模")


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace, normalise dates/percentages/numbers in df."""
    if df.empty:
        return df

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(_strip_if_str)

    for col in df.columns:
        if "日期" in col or "date" in col.lower():
            df[col] = df[col].apply(_parse_date)

    for col in df.columns:
        if "比例" in col or "ratio" in col.lower():
            df[col] = df[col].apply(_parse_percentage)

    for col in _NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = df[col].apply(_parse_number)

    return df


def _strip_if_str(x: Any) -> Any:
    return x.strip() if isinstance(x, str) else x


def _parse_date(value: Any) -> str | None:
    if pd.isna(value) or value == "" or value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Tolerate trailing annotations like "2026-04-23 (1)"
    match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    if match:
        return match.group(1)
    return value


def _parse_percentage(value: Any) -> float | None:
    if pd.isna(value) or value == "" or value is None:
        return None
    value = str(value).strip().replace("%", "").replace("％", "")
    if not value:
        return None
    try:
        return float(value) / 100
    except ValueError:
        return None


_MULTIPLIERS = {
    "万": 10_000,
    "亿": 100_000_000,
    "K": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
}


def _parse_number(value: Any) -> float | None:
    if pd.isna(value) or value == "" or value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    value = re.sub(r"[,\s]", "", value)
    for suffix, mult in _MULTIPLIERS.items():
        if suffix in value:
            try:
                return float(value.replace(suffix, "")) * mult
            except ValueError:
                pass
    try:
        return float(value)
    except ValueError:
        return None
