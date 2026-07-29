"""Shared asset identity review helpers for Smart Money pipelines."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

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

# V1.2 (SPEC-03-004 F-011 / DESIGN-03-004 §3.3): separate attrs key for
# OCR joint correction audit. The joint audit NEVER enters AUDIT_ATTR
# (which is reserved for high-risk asset_name_audit schema).
OCR_JOINT_AUDIT_ATTR = "ocr_joint_audit"

# V1.2 default config path (relative to scripts/ directory).
DEFAULT_OCR_JOINT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "ocr_joint_corrections.yaml"

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# V1.2 (SPEC-03-004 F-011 / DESIGN-03-004 §3.3):
# OCR 代码/名称联合修正
# ---------------------------------------------------------------------------

# Required fields per SPEC-03-004 §4.2 — all five must be present and non-empty.
_JOINT_CONFIG_REQUIRED_FIELDS = (
    "source_code",
    "source_name_pattern",
    "target_code",
    "target_name",
    "reason",
)


def _load_ocr_joint_corrections_config(
    config_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Load OCR joint correction rules from YAML config (fail-closed).

    Resolution order (SPEC-03-004 §4.2 / DESIGN-03-004 §3.3):
      1. If ``config_path`` is provided, use it directly.
      2. Otherwise resolve relative to ``<scripts>/config/ocr_joint_corrections.yaml``.
      3. File not found / parse error / empty → return ``[]`` (skip joint
         correction; data falls back to standard review).

    Single-entry field missing or empty → skip that entry, keep parsing the
    rest (SPEC §4.2 / DESIGN §3.3 fail-closed).

    Returns:
        list of validated rule dicts. Each rule contains the 5 required
        fields and may include extra keys (which are ignored).
    """
    path = Path(config_path) if config_path is not None else DEFAULT_OCR_JOINT_CONFIG_PATH

    if not path.exists():
        logger.warning(
            "[ocr_joint_corrections] config not found at %s; skipping joint correction",
            path,
        )
        return []

    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        logger.warning(
            "[ocr_joint_corrections] failed to parse %s: %s; skipping joint correction",
            path,
            exc,
        )
        return []

    if not isinstance(raw, list):
        logger.warning(
            "[ocr_joint_corrections] config root must be a list, got %s; skipping joint correction",
            type(raw).__name__,
        )
        return []

    if not raw:
        logger.warning(
            "[ocr_joint_corrections] config %s is empty; skipping joint correction",
            path,
        )
        return []

    valid: list[dict[str, Any]] = []
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            logger.warning(
                "[ocr_joint_corrections] entry #%s is not a mapping (got %s); skipping",
                idx, type(entry).__name__,
            )
            continue
        missing = [
            f for f in _JOINT_CONFIG_REQUIRED_FIELDS
            if f not in entry or entry[f] is None or str(entry[f]).strip() == ""
        ]
        if missing:
            logger.warning(
                "[ocr_joint_corrections] entry #%s missing/empty fields %s; skipping",
                idx, missing,
            )
            continue
        valid.append(entry)

    return valid


def _joint_correction_reason_text(rule: dict[str, Any]) -> str:
    """Human-readable correction reason for a matched rule (SPEC §4.1.2)."""
    return (
        f"OCR joint correction: code {rule['source_code']} + name "
        f"{rule['source_name_pattern']} → {rule['target_code']} / {rule['target_name']}"
    )


def apply_ocr_joint_corrections(
    df: pd.DataFrame,
    config_path: str | Path | None = None,
    original_names: pd.Series | None = None,
) -> pd.DataFrame:
    """Apply OCR code/name joint correction rules (V1.2 / SPEC-03-004 F-011).

    MUST be called AFTER ``standardize_df_asset_names()`` (so that name
    matching uses the standardized name) and BEFORE
    ``correct_stock_names()`` / ``correct_dataframe_asset_names()`` (so the
    corrected (code, name) pair flows through the standard review as a
    matched pair, not as a new pending row).

    Matching semantics (SPEC §4.1.1):
      * ``Wind代码`` exact-equals ``source_code`` (no substring/prefix/fuzzy).
      * Standardized ``资产名称`` contains ``source_name_pattern``.
      * Both conditions must hold; single condition → no correction.
      * Single row may trigger at most one joint correction in a run.

    On every correction:
      * ``Wind代码`` is rewritten to ``target_code``.
      * ``资产名称`` is rewritten to ``target_name``.
      * ``名称复核状态`` (if column exists) → ``auto_corrected``.
      * ``名称复核原因`` (if column exists) → rule's reason text.
      * A 7-field audit record is appended to ``df.attrs[OCR_JOINT_AUDIT_ATTR]``.

    Audit ``original_name`` (SPEC §4.1.4 #3):
      * If ``original_names`` is provided (a Series aligned to ``df.index``),
        the audit record's ``original_name`` is taken from it — this is the
        **pre-standardization** raw OCR name (e.g. ``'  联 讯 仪 器  '``).
      * Otherwise (``original_names=None``), the audit record uses the
        current row's ``资产名称`` (post-standardization) as a backward-
        compatible fallback. This matches the V1.2 T1-T7 fixture behavior
        where the input is already standardized.

    Fail-closed (SPEC §4.2): config missing/empty/invalid → returns the
    original DataFrame unchanged with an empty audit list. Never raises.
    Never silently overwrites with wrong values.
    """
    if df.empty:
        result = df.copy()
        result.attrs[OCR_JOINT_AUDIT_ATTR] = []
        return result

    # Required columns must both exist; otherwise the rule engine cannot
    # match anything and we skip silently (fail-closed).
    if "Wind代码" not in df.columns or "资产名称" not in df.columns:
        result = df.copy()
        result.attrs[OCR_JOINT_AUDIT_ATTR] = []
        return result

    rules = _load_ocr_joint_corrections_config(config_path=config_path)
    if not rules:
        result = df.copy()
        result.attrs[OCR_JOINT_AUDIT_ATTR] = []
        return result

    result = df.copy()
    # Ensure audit attrs survive pandas copy.
    result.attrs[OCR_JOINT_AUDIT_ATTR] = []

    # Ensure status/reason columns exist for downstream reviewers.
    if REVIEW_STATUS_COL not in result.columns:
        result[REVIEW_STATUS_COL] = ""
    if REVIEW_REASON_COL not in result.columns:
        result[REVIEW_REASON_COL] = ""

    audit: list[dict[str, Any]] = []
    corrected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    has_original_names = original_names is not None

    for idx in result.index:
        code_raw = result.at[idx, "Wind代码"]
        name_std = result.at[idx, "资产名称"]

        # Name must be a non-empty string; rule cannot match otherwise.
        if not isinstance(name_std, str) or not name_std:
            continue
        if not isinstance(code_raw, str) or not code_raw:
            continue

        # ORIGINAL_NAME for audit (SPEC §4.1.4 #3):
        #   * When ``original_names`` is provided (the V1.2 P0 Fix path),
        #     capture the pre-standardization raw OCR name.
        #   * Otherwise fall back to the current (standardized) value — this
        #     preserves the V1.2 T1 fixture semantics for callers that
        #     invoke this function in isolation with already-standardized input.
        original_code = code_raw
        if has_original_names:
            try:
                raw_value = original_names.loc[idx]
            except Exception:
                raw_value = name_std
            if isinstance(raw_value, str) and raw_value:
                original_name = raw_value
            else:
                original_name = name_std
        else:
            original_name = name_std
        canonical_name: str | None = None
        target_code: str | None = None
        reason_text: str | None = None

        for rule in rules:
            # Exact-match code (no substring / prefix / fuzzy).
            if code_raw != rule["source_code"]:
                continue
            # Pattern must be a substring of the standardized name.
            pattern = rule["source_name_pattern"]
            if not pattern or pattern not in name_std:
                continue

            # Both conditions satisfied → apply correction.
            target_code = rule["target_code"]
            target_name = rule["target_name"]
            reason_text = _joint_correction_reason_text(rule)
            canonical_name = target_name

            result.at[idx, "Wind代码"] = target_code
            result.at[idx, "资产名称"] = target_name
            result.at[idx, "_ocr_joint_original_code"] = original_code
            result.at[idx, "_ocr_joint_original_name"] = original_name
            result.at[idx, REVIEW_STATUS_COL] = STATUS_AUTO_CORRECTED
            result.at[idx, REVIEW_REASON_COL] = reason_text

            audit.append({
                "original_code": original_code,
                "target_code": target_code,
                "original_name": original_name,
                "canonical_name": canonical_name,
                "correction_reason": rule["reason"],
                "auto_correction_status": STATUS_AUTO_CORRECTED,
                "corrected_at": corrected_at,
            })
            # Single-row single-trigger: matched one rule, stop scanning.
            break

    result.attrs[OCR_JOINT_AUDIT_ATTR] = audit
    return result


def get_ocr_joint_audit(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Return the list of OCR joint correction audit records from a DataFrame.

    Always returns a list (possibly empty). Used by pipeline entry points
    to populate ``review.audit_items[]``.
    """
    return list(df.attrs.get(OCR_JOINT_AUDIT_ATTR, []) or [])


def apply_asset_identity_review(
    df: pd.DataFrame,
    joint_correction_config_path: str | Path | None = None,
) -> pd.DataFrame:
    """Run all asset identity review steps on a pipeline DataFrame.

    V1.2 (DESIGN-03-004 §3.2 / SPEC-03-004 §4.1): inserts the OCR joint
    correction step between name standardization and the static master
    review. The joint audit is stored in a SEPARATE attrs key
    (``OCR_JOINT_AUDIT_ATTR``) and is NEVER merged into ``AUDIT_ATTR``
    (the high-risk schema stays clean).

    P0 Fix contract (SPEC §4.1.2 / §4.1.4 / §6 T1):
      * The pre-standardization raw ``资产名称`` is captured BEFORE
        ``standardize_df_asset_names`` and forwarded to
        ``apply_ocr_joint_corrections`` so the audit record's
        ``original_name`` reflects the raw OCR input (e.g.
        ``'  联 讯 仪 器  '``), not the standardized materialized value.
      * After the standard review runs, the joint-corrected rows are
        restored to ``review_status = auto_corrected`` (the standard
        review's ``matched`` flip is suppressed for rows that were
        jointly corrected). This is the only way to satisfy SPEC §4.1.2
        / §6 T1 without touching ``a_share_name_corrector.py``.
    """
    # P0 Fix: capture raw (pre-standardization) asset names so the joint
    # audit's ``original_name`` reflects the original OCR input.
    raw_asset_names: pd.Series | None = None
    if "资产名称" in df.columns:
        raw_col = df["资产名称"]
        # Pandas ``__getitem__`` may return a DataFrame when the column is
        # itself a structured dtype; for our schema (always a string column)
        # this is a Series. Defensive cast keeps mypy/pyright happy.
        if isinstance(raw_col, pd.Series):
            raw_asset_names = raw_col.copy()

    reviewed = standardize_df_asset_names(df)
    # V1.2 Step 1.5: joint correction. Store its audit separately.
    # Forward ``original_names`` so the audit captures the raw OCR input.
    reviewed = apply_ocr_joint_corrections(
        reviewed,
        config_path=joint_correction_config_path,
        original_names=raw_asset_names,
    )
    reviewed = correct_stock_names(reviewed)
    static_audit = list(reviewed.attrs.get(AUDIT_ATTR, []))
    reviewed = correct_dataframe_asset_names(reviewed)
    reviewed.attrs[AUDIT_ATTR] = static_audit + list(reviewed.attrs.get(AUDIT_ATTR, []))

    # P0 Fix: SPEC §4.1.2 / §6 T1 — joint-corrected rows must keep
    # ``review_status = auto_corrected`` end-to-end. The standard review
    # (above) may have flipped them to ``matched`` when the corrected pair
    # resolves cleanly against the master map. Restore the joint-correction
    # status here for those rows only.
    joint_audit = list(reviewed.attrs.get(OCR_JOINT_AUDIT_ATTR, []) or [])
    if joint_audit and REVIEW_STATUS_COL in reviewed.columns:
        # P0 contract: restoration is row-specific, not a target-code-wide mask.
        joint_rows = {
            (rec.get("original_code"), rec.get("original_name"), rec.get("target_code"))
            for rec in joint_audit
        }
        if joint_rows:
            for idx, row in reviewed.iterrows():
                key = (
                    row.get("_ocr_joint_original_code"),
                    row.get("_ocr_joint_original_name"),
                    row.get("Wind代码"),
                )
                if key in joint_rows:
                    reviewed.loc[idx, REVIEW_STATUS_COL] = STATUS_AUTO_CORRECTED

    # NOTE (V1.2 contract — narrative §3.3 + SPEC §4.1.4):
    # joint audit remains in reviewed.attrs[OCR_JOINT_AUDIT_ATTR] only.
    # It must NOT be merged into AUDIT_ATTR (that key is reserved for
    # high-risk asset_name_audit schema and must stay unchanged).
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
    provider_status: dict[str, Any] | None = None,
    joint_audit: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Persist pending rows and metadata for manual review.

    Args:
        provider_status: Optional dict returned by the OCR provider router
            (RFC-03-006 / SPEC-03-006). When provided, a ``provider`` column
            is appended to the pending CSV and a ``provider_status`` block
            is embedded in the pending JSON payload. Backward compatible:
            when ``None`` (legacy callers) the new field is omitted.
        joint_audit: V1.2 (SPEC-03-004 §4.1.4) — when the pending batch has
            at least one row AND ``joint_audit`` is non-empty, write the
            7-field joint correction audit records into
            ``payload["audit_items"]``. Backward compatible: ``None`` or
            empty list → field is omitted entirely.
    """
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

    # F-010 (SPEC-03-006 §4.8): if a provider_status was provided, write the
    # active provider name into a new CSV column. We do this *only* when
    # provider_status is non-None — legacy callers get a backward-compatible
    # CSV with no new column.
    if provider_status:
        provider_name = str(provider_status.get("name") or "unknown")
        pending_df = pending_df.copy()
        pending_df["provider"] = provider_name
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
    if provider_status:
        payload["provider_status"] = provider_status
    # V1.2 (SPEC-03-004 §4.1.4): joint audit only when there ARE pending
    # rows AND joint audit is non-empty. pending_df.empty short-circuits
    # above so we always have at least one pending row here.
    if joint_audit:
        payload["audit_items"] = list(joint_audit)
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
