"""Shared asset identity review helpers for Smart Money pipelines."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from stock_name_corrections import STOCK_NAME_ALIASES, STOCK_NAME_CORRECTIONS
from transformers.a_share_name_corrector import (
    AUDIT_ATTR,
    MASTER_NAME_COL,
    REVIEW_REASON_COL,
    REVIEW_STATUS_COL,
    STATUS_AUTO_CORRECTED,
    STATUS_MATCHED,
    STATUS_MISSING_MASTER,
    STATUS_PENDING_REVIEW,
    correct_dataframe_asset_names,
    names_are_compatible,
)

PENDING_REVIEW_STATUSES = {STATUS_PENDING_REVIEW, STATUS_MISSING_MASTER}


def standardize_asset_name(name: Any) -> Any:
    """Normalize OCR stock names without changing business identity."""
    if not isinstance(name, str):
        return name
    name = re.sub(r"\s+", "", name)
    name = name.replace("（", "(").replace("）", ")")
    name = name.replace("－", "-").replace("—", "-")
    return name.translate(str.maketrans(
        "ＷＸＹＺＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶ",
        "WXYZABCDEFGHIJKLMNOPQRSTUV",
    ))


def standardize_df_asset_names(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize the asset-name column when present."""
    result = df.copy()
    if "资产名称" in result.columns:
        result["资产名称"] = result["资产名称"].apply(standardize_asset_name)
    return result


def correct_stock_names(df: pd.DataFrame) -> pd.DataFrame:
    """Apply static stock-name corrections with conservative review gating."""
    result = df.copy()
    if "资产名称" not in result.columns or "Wind代码" not in result.columns:
        return result

    for col in (REVIEW_STATUS_COL, MASTER_NAME_COL, REVIEW_REASON_COL):
        if col not in result.columns:
            result[col] = ""

    audit: list[dict[str, Any]] = []

    def correct_name(row: pd.Series) -> Any:
        code = row.get("Wind代码", "")
        name = row.get("资产名称", "")
        if not code or not name:
            return name
        expected_name = STOCK_NAME_CORRECTIONS.get(code)
        if not expected_name:
            return name
        result.at[row.name, MASTER_NAME_COL] = expected_name
        if name == expected_name:
            result.at[row.name, REVIEW_STATUS_COL] = STATUS_MATCHED
            return name
        aliases = STOCK_NAME_ALIASES.get(code, set())
        if names_are_compatible(name, expected_name) or name in aliases:
            result.at[row.name, REVIEW_STATUS_COL] = STATUS_AUTO_CORRECTED
            result.at[row.name, REVIEW_REASON_COL] = "静态名称映射与OCR名称兼容，已按映射标准化"
            audit.append({
                "row": row.name,
                "code": code,
                "ocr_name": name,
                "standard_name": expected_name,
                "status": STATUS_AUTO_CORRECTED,
                "reason": "compatible static code/name mapping",
            })
            return expected_name
        result.at[row.name, REVIEW_STATUS_COL] = STATUS_PENDING_REVIEW
        result.at[row.name, REVIEW_REASON_COL] = "OCR名称与静态代码名称映射不兼容，疑似代码或名称识别错误"
        audit.append({
            "row": row.name,
            "code": code,
            "ocr_name": name,
            "standard_name": expected_name,
            "status": STATUS_PENDING_REVIEW,
            "reason": "incompatible static code/name mapping",
        })
        return name

    result["资产名称"] = result.apply(correct_name, axis=1)
    result.attrs[AUDIT_ATTR] = audit
    return result


def apply_asset_identity_review(df: pd.DataFrame) -> pd.DataFrame:
    """Run all asset identity review steps on a pipeline DataFrame."""
    reviewed = standardize_df_asset_names(df)
    reviewed = correct_stock_names(reviewed)
    static_audit = list(reviewed.attrs.get(AUDIT_ATTR, []))
    reviewed = correct_dataframe_asset_names(reviewed)
    reviewed.attrs[AUDIT_ATTR] = static_audit + list(reviewed.attrs.get(AUDIT_ATTR, []))
    return reviewed


def pending_review_mask(df: pd.DataFrame) -> pd.Series:
    """Return a boolean mask for rows requiring human review."""
    if REVIEW_STATUS_COL not in df.columns:
        return pd.Series(False, index=df.index)
    return df[REVIEW_STATUS_COL].isin(PENDING_REVIEW_STATUSES)


def split_review_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a reviewed DataFrame into accepted and pending rows."""
    mask = pending_review_mask(df)
    return df.loc[~mask].copy(), df.loc[mask].copy()


def high_risk_asset_name_issues(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Return audit records that require manual confirmation."""
    return [
        item for item in df.attrs.get(AUDIT_ATTR, [])
        if item.get("status") in PENDING_REVIEW_STATUSES
    ]


def _date_value(row: pd.Series, fmt: str) -> str:
    column = "日期" if fmt == "trade" else "截止日期"
    value = row.get(column, "")
    return str(value)[:10] if value is not None else ""


def pending_identity_keys(df: pd.DataFrame, fmt: str) -> set[tuple[Any, ...]]:
    """Build row identity keys used to filter normalized records."""
    keys: set[tuple[Any, ...]] = set()
    if df.empty:
        return keys

    for _, row in df.iterrows():
        base = (
            _date_value(row, fmt),
            str(row.get("产品代码", "") or "").strip(),
            str(row.get("Wind代码", "") or "").strip(),
            str(row.get("资产名称", "") or "").strip(),
        )
        if fmt == "trade":
            keys.add((*base, str(row.get("方向", "") or "").strip()))
        else:
            keys.add(base)
    return keys


def filter_pending_normalized_records(normalized: dict, pending_df: pd.DataFrame, fmt: str) -> dict:
    """Remove pending position/trade records from normalized data."""
    pending_keys = pending_identity_keys(pending_df, fmt)
    if not pending_keys:
        return normalized

    if fmt == "trade":
        normalized["trade"] = [
            record for record in normalized.get("trade", [])
            if (
                str(record.get("trade_date", "") or "")[:10],
                str(record.get("product_code", "") or "").strip(),
                str(record.get("asset_wind_code", "") or "").strip(),
                str(record.get("asset_name", "") or "").strip(),
                str(record.get("direction", "") or "").strip(),
            ) not in pending_keys
        ]
    else:
        normalized["position"] = [
            record for record in normalized.get("position", [])
            if (
                str(record.get("position_date", "") or "")[:10],
                str(record.get("product_code", "") or "").strip(),
                str(record.get("asset_wind_code", "") or "").strip(),
                str(record.get("asset_name", "") or "").strip(),
            ) not in pending_keys
        ]
    return normalized


def save_pending_review(
    *,
    pending_df: pd.DataFrame,
    audit: list[dict[str, Any]],
    source_root: Path,
    folder_date: str,
    prefix: str,
    timestamp: str,
    fmt: str,
    source_path: str,
    excel_path: str,
) -> dict[str, Any]:
    """Persist pending rows and metadata for manual review."""
    if pending_df.empty:
        return {}

    review_dir = source_root / folder_date / "review_pending"
    review_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{prefix}_{timestamp}_pending"
    csv_path = review_dir / f"{base_name}.csv"
    json_path = review_dir / f"{base_name}.json"
    counter = 1
    while csv_path.exists() or json_path.exists():
        csv_path = review_dir / f"{base_name}_{counter:02d}.csv"
        json_path = review_dir / f"{base_name}_{counter:02d}.json"
        counter += 1

    pending_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    payload = {
        "status": "pending_review",
        "format": fmt,
        "source": source_path,
        "excel": excel_path,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "rows": len(pending_df),
        "review_status_column": REVIEW_STATUS_COL,
        "review_reason_column": REVIEW_REASON_COL,
        "audit": audit,
        "csv": str(csv_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # F-008: 生成标准补录命令，供 pipeline 调用方（AI/Orchestrator）直接使用
    apply_cmd = (
        f"python3 {Path(__file__).parent.parent / 'load_pending_confirmed.py'}"
        f" --csv \"{csv_path}\""
    )
    return {"csv": str(csv_path), "json": str(json_path), "rows": len(pending_df), "issues": audit, "apply_command": apply_cmd}


def build_review_summary(
    *,
    total_rows: int,
    accepted_rows: int,
    pending_rows: int,
    audit: list[dict[str, Any]],
    pending: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact review summary for pipeline results."""
    status_counts: dict[str, int] = {}
    for item in audit:
        status = str(item.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "total_rows": total_rows,
        "accepted_rows": accepted_rows,
        "pending_rows": pending_rows,
        "audit_count": len(audit),
        "status_counts": status_counts,
        "pending_files": {
            key: pending[key]
            for key in ("csv", "json")
            if pending and pending.get(key)
        },
    }
