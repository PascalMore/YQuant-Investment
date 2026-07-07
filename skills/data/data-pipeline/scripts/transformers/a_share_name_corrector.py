"""A-share asset name correction from stock_basic_info master data."""
from __future__ import annotations

import logging
import re
import sys
import unicodedata
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

AUDIT_ATTR = "asset_name_audit"
REVIEW_STATUS_COL = "名称复核状态"
MASTER_NAME_COL = "主数据名称"
REVIEW_REASON_COL = "名称复核原因"
STATUS_MATCHED = "matched"
STATUS_AUTO_CORRECTED = "auto_corrected"
STATUS_PENDING_REVIEW = "pending_review"
STATUS_RESOLVED = "resolved"
STATUS_MISSING_MASTER = "missing_master"

_CORPORATE_ACTION_PREFIX_RE = re.compile(r"^(\*?ST|XD|DR|XR|N|C)+", re.IGNORECASE)
_NOISE_CHARS_RE = re.compile(r"[\s\-－—_()（）·.]")


def load_a_share_name_map() -> dict[str, str]:
    """Load code -> standard stock name through the shared StockInfo API."""
    return get_all_stock_names()


def normalize_name_for_match(name: Any) -> str:
    """Normalize stock names for conservative OCR/master-data comparison."""
    value = str(name or "").strip()
    if not value or value.lower() in {"nan", "none"}:
        return ""
    # NFKC normalization: fullwidth ASCII (e.g. Ａ U+FF21) → ASCII (A U+0041).
    # Without this, OCR reads of half-width A vs master-data full-width Ａ
    # never match (2026-07-07 root cause: 京东方A pending_review repeatedly).
    value = unicodedata.normalize("NFKC", value)
    value = _NOISE_CHARS_RE.sub("", value.upper())
    value = _CORPORATE_ACTION_PREFIX_RE.sub("", value)
    return value


def names_are_compatible(ocr_name: Any, standard_name: Any) -> bool:
    """Return whether OCR name can be safely treated as the standard name.

    This intentionally allows only strong textual evidence: exact match after
    normalization, or one normalized name containing the other. It covers common
    OCR/corporate-action forms such as "DR安集科" vs "安集科技" while rejecting
    unrelated code/name pairs that would amplify a Wind-code OCR error.
    """
    ocr = normalize_name_for_match(ocr_name)
    standard = normalize_name_for_match(standard_name)
    if not ocr or not standard:
        return False
    return ocr == standard or ocr in standard or standard in ocr


def _audit_record(
    *,
    row: Any,
    code: str,
    current_name: str,
    standard_name: str | None,
    status: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "row": row,
        "code": code,
        "ocr_name": current_name,
        "standard_name": standard_name or "",
        "status": status,
        "reason": reason,
    }


def _prepare_review_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for col in (REVIEW_STATUS_COL, MASTER_NAME_COL, REVIEW_REASON_COL):
        if col not in result.columns:
            result[col] = ""
    return result


def _mark_all_a_shares_pending(df: pd.DataFrame, reason_cn: str, reason_en: str) -> pd.DataFrame:
    result = _prepare_review_columns(df)
    audit: list[dict[str, Any]] = []
    for idx, row in result.iterrows():
        code = normalize_a_share_code(row.get("Wind代码"))
        if not code:
            continue
        current_name = str(row.get("资产名称") or "").strip()
        result.at[idx, REVIEW_STATUS_COL] = STATUS_PENDING_REVIEW
        result.at[idx, REVIEW_REASON_COL] = reason_cn
        audit.append(
            _audit_record(
                row=idx,
                code=code,
                current_name=current_name,
                standard_name=None,
                status=STATUS_PENDING_REVIEW,
                reason=reason_en,
            )
        )
    result.attrs[AUDIT_ATTR] = audit
    return result


def correct_dataframe_asset_names(df: pd.DataFrame) -> pd.DataFrame:
    """Correct OCR DataFrame asset names before Excel transform and MongoDB load.

    The correction is conservative:
    - compatible OCR/master names are corrected to the master-data name;
    - incompatible code/name pairs are not changed and are marked for review;
    - high-risk mismatches are exposed through ``df.attrs[AUDIT_ATTR]`` and
      review columns so callers can block DB writes while preserving the Excel
      audit trail.
    """
    if "Wind代码" not in df.columns or "资产名称" not in df.columns:
        return df

    try:
        name_map = load_a_share_name_map()
    except Exception as exc:
        logger.warning("[A股名称复核] stock_basic_info unavailable; A-share rows set pending: %s", exc)
        return _mark_all_a_shares_pending(
            df,
            "A股主数据不可用，无法确认代码/名称关系",
            "A-share master data unavailable",
        )

    if not name_map:
        logger.warning("[A股名称复核] stock_basic_info mapping is empty; A-share rows set pending")
        return _mark_all_a_shares_pending(
            df,
            "A股主数据为空，无法确认代码/名称关系",
            "A-share master data map is empty",
        )

    result = _prepare_review_columns(df)
    corrected = 0
    missing = 0
    mismatch = 0
    audit: list[dict[str, Any]] = []

    for idx, row in result.iterrows():
        code = normalize_a_share_code(row.get("Wind代码"))
        if not code:
            continue
        standard_name = name_map.get(code)
        current_name = str(row.get("资产名称") or "").strip()
        if not standard_name:
            missing += 1
            result.at[idx, REVIEW_STATUS_COL] = STATUS_MISSING_MASTER
            result.at[idx, REVIEW_REASON_COL] = "A股代码在 stock_basic_info 中未找到"
            audit.append(
                _audit_record(
                    row=idx,
                    code=code,
                    current_name=current_name,
                    standard_name=None,
                    status=STATUS_MISSING_MASTER,
                    reason="A-share code missing in stock_basic_info",
                )
            )
            continue

        result.at[idx, MASTER_NAME_COL] = standard_name
        if current_name == standard_name:
            result.at[idx, REVIEW_STATUS_COL] = STATUS_MATCHED
            continue

        if not current_name or names_are_compatible(current_name, standard_name):
            result.at[idx, "资产名称"] = standard_name
            result.at[idx, REVIEW_STATUS_COL] = STATUS_AUTO_CORRECTED
            result.at[idx, REVIEW_REASON_COL] = "OCR名称与主数据名称兼容，已按主数据标准化"
            corrected += 1
            audit.append(
                _audit_record(
                    row=idx,
                    code=code,
                    current_name=current_name,
                    standard_name=standard_name,
                    status=STATUS_AUTO_CORRECTED,
                    reason="compatible OCR/master names",
                )
            )
            logger.info(
                "[A股名称更正] row=%s code=%s asset_name %r -> %r",
                idx,
                code,
                current_name,
                standard_name,
            )
            continue

        mismatch += 1
        result.at[idx, REVIEW_STATUS_COL] = STATUS_PENDING_REVIEW
        result.at[idx, REVIEW_REASON_COL] = "OCR名称与Wind代码对应主数据名称不兼容，疑似代码识别错误"
        audit.append(
            _audit_record(
                row=idx,
                code=code,
                current_name=current_name,
                standard_name=standard_name,
                status=STATUS_PENDING_REVIEW,
                reason="incompatible OCR/master names; possible Wind-code OCR error",
            )
        )
        logger.warning(
            "[A股名称复核] row=%s code=%s OCR asset_name=%r conflicts with master=%r; kept OCR name",
            idx,
            code,
            current_name,
            standard_name,
        )

    logger.info(
        "[A股名称更正] checked=%s corrected=%s mismatch=%s missing_master=%s",
        len(result),
        corrected,
        mismatch,
        missing,
    )
    result.attrs[AUDIT_ATTR] = audit
    return result


def correct_position_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Correct normalized portfolio_position-like records in memory.

    This function is intentionally conservative. It only overwrites
    ``asset_name`` when the observed name is empty or strongly compatible with
    the master-data name. Incompatible code/name pairs are left untouched so
    callers can route them to a review gate instead of amplifying a code OCR
    error into a wrong name.
    """
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
        current_name = record.get("asset_name")
        if current_name == standard_name:
            continue
        if current_name and not names_are_compatible(current_name, standard_name):
            logger.warning(
                "[A股名称复核] code=%s asset_name=%r conflicts with master=%r; kept original",
                code,
                current_name,
                standard_name,
            )
            continue
        if current_name != standard_name:
            logger.info(
                "[A股名称更正] code=%s asset_name %r -> %r",
                code,
                current_name,
                standard_name,
            )
            record["asset_name"] = standard_name
            corrected += 1
    logger.info("[A股名称更正] normalized records corrected=%s", corrected)
    return records, corrected
