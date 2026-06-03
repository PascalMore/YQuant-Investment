"""A-share asset name correction from stock_basic_info master data."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

_WORKSPACE_ROOT = Path(__file__).resolve().parents[5]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from skills.data.data_interface.stock.stock_info_api import (  # noqa: E402
    get_all_stock_names,
    normalize_a_share_code,
)

logger = logging.getLogger(__name__)


def load_a_share_name_map() -> dict[str, str]:
    """Load code -> standard stock name through the shared StockInfo API."""
    return get_all_stock_names()


def correct_dataframe_asset_names(df: pd.DataFrame) -> pd.DataFrame:
    """Correct OCR DataFrame asset names before Excel transform and MongoDB load."""
    if "Wind代码" not in df.columns or "资产名称" not in df.columns:
        return df

    try:
        name_map = load_a_share_name_map()
    except Exception as exc:
        logger.warning("[A股名称更正] skipped: failed to load stock_basic_info: %s", exc)
        return df

    if not name_map:
        logger.warning("[A股名称更正] skipped: stock_basic_info mapping is empty")
        return df

    corrected = 0
    missing = 0
    result = df.copy()
    for idx, row in result.iterrows():
        code = normalize_a_share_code(row.get("Wind代码"))
        if not code:
            continue
        standard_name = name_map.get(code)
        if not standard_name:
            missing += 1
            continue
        current_name = str(row.get("资产名称") or "").strip()
        if current_name != standard_name:
            result.at[idx, "资产名称"] = standard_name
            corrected += 1
            logger.info(
                "[A股名称更正] row=%s code=%s asset_name %r -> %r",
                idx,
                code,
                current_name,
                standard_name,
            )

    logger.info(
        "[A股名称更正] checked=%s corrected=%s missing_master=%s",
        len(result),
        corrected,
        missing,
    )
    return result


def correct_position_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Correct normalized portfolio_position-like records in memory."""
    try:
        name_map = load_a_share_name_map()
    except Exception as exc:
        logger.warning("[A股名称更正] skipped: failed to load stock_basic_info: %s", exc)
        return records, 0

    corrected = 0
    for record in records:
        code = normalize_a_share_code(record.get("asset_wind_code"))
        standard_name = name_map.get(code) if code else None
        if not standard_name:
            continue
        if record.get("asset_name") != standard_name:
            logger.info(
                "[A股名称更正] code=%s asset_name %r -> %r",
                code,
                record.get("asset_name"),
                standard_name,
            )
            record["asset_name"] = standard_name
            corrected += 1
    logger.info("[A股名称更正] normalized records corrected=%s", corrected)
    return records, corrected
