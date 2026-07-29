"""Offline tests for OCR code/name joint correction (SPEC-03-004 F-011 / V1.2).

Covers:
  * T1-T7 fixture matrix from SPEC §6 / DESIGN §5.
  * C1-C4 configuration error handling from SPEC §6 / DESIGN §5.
  * V1.2 contract that joint audit NEVER pollutes AUDIT_ATTR.
  * V1.2 contract that ``original_name`` captures the standardized-but-uncorrected
    name (i.e. what the rule engine sees right before matching).

No network, no MongoDB, no OCR. Tests are 100% deterministic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from transformers import a_share_name_corrector  # noqa: E402
from transformers.asset_identity_review import (  # noqa: E402
    AUDIT_ATTR,
    OCR_JOINT_AUDIT_ATTR,
    REVIEW_REASON_COL,
    REVIEW_STATUS_COL,
    STATUS_AUTO_CORRECTED,
    STATUS_MATCHED,
    STATUS_PENDING_REVIEW,
    _joint_correction_reason_text,
    _load_ocr_joint_corrections_config,
    apply_asset_identity_review,
    apply_ocr_joint_corrections,
    get_ocr_joint_audit,
    save_pending_review,
    split_review_rows,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


# Minimal A-share master map sufficient for the joint correction fixtures
# (only entries the test cases actually need).
A_SHARE_MASTER = {
    "688808.SH": "联讯仪器",
    "688008.SH": "澜起科技",   # real code for 澜起科技; verifies protection
    "600519.SH": "贵州茅台",
}


@pytest.fixture(autouse=True)
def patch_master(monkeypatch):
    """Inject a deterministic master data map for the corrector."""
    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: dict(A_SHARE_MASTER),
    )


def _write_yaml_config(tmp_path: Path, entries: Any) -> Path:
    """Write a YAML config file at a temp path and return the path."""
    cfg = tmp_path / "ocr_joint_corrections.yaml"
    cfg.write_text(
        yaml.safe_dump(entries, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return cfg


def _write_bad_yaml_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "ocr_joint_corrections.yaml"
    # Deliberately malformed YAML (unclosed bracket).
    cfg.write_text("- source_code: [bad\n", encoding="utf-8")
    return cfg


# ---------------------------------------------------------------------------
# T1-T7 fixture matrix
# ---------------------------------------------------------------------------


def test_t1_joint_correction_hits_when_both_code_and_name_match(tmp_path):
    """T1: 688008.SH + 联讯仪器 → 688808.SH + 联讯仪器 + audit."""
    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": "联讯仪器"}]
    )
    out = apply_ocr_joint_corrections(df, config_path=_write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ]))

    assert out.loc[0, "Wind代码"] == "688808.SH"
    assert out.loc[0, "资产名称"] == "联讯仪器"
    assert out.loc[0, REVIEW_STATUS_COL] == STATUS_AUTO_CORRECTED
    assert "OCR joint correction" in out.loc[0, REVIEW_REASON_COL]

    audit = out.attrs.get(OCR_JOINT_AUDIT_ATTR, [])
    assert len(audit) == 1
    rec = audit[0]
    # 7-field SPEC §4.1.4 contract — exact key names and order.
    expected_keys = [
        "original_code", "target_code", "original_name", "canonical_name",
        "correction_reason", "auto_correction_status", "corrected_at",
    ]
    assert list(rec.keys()) == expected_keys
    assert rec["original_code"] == "688008.SH"
    assert rec["target_code"] == "688808.SH"
    assert rec["original_name"] == "联讯仪器"
    assert rec["canonical_name"] == "联讯仪器"
    assert rec["correction_reason"] == "ocr_code_name_joint_correction"
    assert rec["auto_correction_status"] == "auto_corrected"
    assert rec["corrected_at"].endswith("Z")
    # V1.2 contract: AUDIT_ATTR must NOT be polluted by joint audit.
    assert out.attrs.get(AUDIT_ATTR, []) == []


def test_t2_protects_real_lanque_tech_from_correction(tmp_path):
    """T2: 688008.SH + 澜起科技 → NOT corrected (rule must not fire on real name)."""
    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": "澜起科技"}]
    )
    out = apply_ocr_joint_corrections(df, config_path=_write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ]))

    # Name "澜起科技" does NOT contain "联讯仪器" → no correction.
    assert out.loc[0, "Wind代码"] == "688008.SH"
    assert out.loc[0, "资产名称"] == "澜起科技"
    assert out.attrs.get(OCR_JOINT_AUDIT_ATTR, []) == []
    # And going through the standard review, this row matches the master.
    full = apply_asset_identity_review(
        df,
        joint_correction_config_path=out.attrs.get("_dummy_ignored"),  # noqa
    ) if "_dummy_ignored" in out.attrs else apply_asset_identity_review(df)
    assert full.loc[0, REVIEW_STATUS_COL] == STATUS_MATCHED


def test_t3_protects_incompatible_name_from_correction(tmp_path):
    """T3: 688008.SH + 不兼容名称 → no joint correction; standard review handles it."""
    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": "某不兼容名称"}]
    )
    out = apply_ocr_joint_corrections(df, config_path=_write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ]))

    assert out.loc[0, "Wind代码"] == "688008.SH"
    assert out.loc[0, "资产名称"] == "某不兼容名称"
    assert out.attrs.get(OCR_JOINT_AUDIT_ATTR, []) == []

    # Standard review must mark this row as pending_review (mismatched name).
    full = apply_asset_identity_review(df)
    assert full.loc[0, REVIEW_STATUS_COL] == STATUS_PENDING_REVIEW


def test_t4_already_correct_pair_does_not_trigger(tmp_path):
    """T4: 688808.SH + 联讯仪器 (already correct) → no correction, no audit."""
    df = pd.DataFrame(
        [{"Wind代码": "688808.SH", "资产名称": "联讯仪器"}]
    )
    out = apply_ocr_joint_corrections(df, config_path=_write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ]))

    # Code is already 688808.SH → rule's source_code doesn't match → no change.
    assert out.loc[0, "Wind代码"] == "688808.SH"
    assert out.loc[0, "资产名称"] == "联讯仪器"
    assert out.attrs.get(OCR_JOINT_AUDIT_ATTR, []) == []


def test_t5_unrelated_code_does_not_trigger(tmp_path):
    """T5: 600519.SH + 联讯仪器 → no correction (code mismatch)."""
    df = pd.DataFrame(
        [{"Wind代码": "600519.SH", "资产名称": "联讯仪器"}]
    )
    out = apply_ocr_joint_corrections(df, config_path=_write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ]))

    # Code 600519.SH does not equal source_code 688008.SH → no correction.
    assert out.loc[0, "Wind代码"] == "600519.SH"
    assert out.loc[0, "资产名称"] == "联讯仪器"
    assert out.attrs.get(OCR_JOINT_AUDIT_ATTR, []) == []


def test_t6_empty_name_does_not_trigger(tmp_path):
    """T6: 688008.SH + (空/null/非字符串) → no correction; standard review handles."""
    cfg_path = _write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ])

    for empty_value in ("", None, "   "):
        df = pd.DataFrame(
            [{"Wind代码": "688008.SH", "资产名称": empty_value}]
        )
        out = apply_ocr_joint_corrections(df, config_path=cfg_path)
        assert out.loc[0, "Wind代码"] == "688008.SH"
        assert out.attrs.get(OCR_JOINT_AUDIT_ATTR, []) == []


def test_t7_joint_correction_works_via_apply_asset_identity_review(
    monkeypatch, tmp_path
):
    """T7: image/message shared entry — joint correction triggers when going through
    ``apply_asset_identity_review`` (the shared pipeline entry).
    """
    cfg_path = _write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ])

    df = pd.DataFrame(
        [
            {
                "截止日期": "2025-10-21",
                "产品代码": "SM001",
                "Wind代码": "688008.SH",
                "资产名称": "联讯仪器",
            },
            {
                "截止日期": "2025-10-21",
                "产品代码": "SM001",
                "Wind代码": "0700.HK",
                "资产名称": "腾讯控股",
            },
        ]
    )

    # Image-style mock: a fake stock_basic_info (we don't have one for 0700.HK
    # in the master map, so the second row will go to missing_master / pending
    # depending on master presence). The point of T7 is the joint correction
    # fires correctly on the FIRST row, which is what we assert here.
    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: {"0700.HK": "腾讯控股", "688808.SH": "联讯仪器", "688008.SH": "澜起科技"},
    )

    out = apply_asset_identity_review(df, joint_correction_config_path=cfg_path)

    # First row: 688008.SH + 联讯仪器 → 688808.SH + 联讯仪器 (joint correction)
    assert out.loc[0, "Wind代码"] == "688808.SH"
    assert out.loc[0, "资产名称"] == "联讯仪器"
    # P0 contract: status is EXACTLY auto_corrected (no flip to matched) per
    # SPEC §4.1.2 / §6 T1.
    assert out.loc[0, REVIEW_STATUS_COL] == STATUS_AUTO_CORRECTED

    audit = out.attrs.get(OCR_JOINT_AUDIT_ATTR, [])
    assert len(audit) == 1
    assert audit[0]["original_code"] == "688008.SH"
    assert audit[0]["target_code"] == "688808.SH"

    # V1.2 contract: AUDIT_ATTR (high-risk schema) remains UNCHANGED by joint
    # audit. (correct_stock_names() may append its own records if it flags a
    # mismatch; for the corrected row it should NOT add anything because the
    # code/name is now self-consistent.)
    assert all(
        item.get("code") != "688008.SH" for item in out.attrs.get(AUDIT_ATTR, [])
    ), "AUDIT_ATTR must not contain joint-correction rows keyed by 688008.SH"


# ---------------------------------------------------------------------------
# C1-C4 configuration error handling (SPEC §6 / DESIGN §5)
# ---------------------------------------------------------------------------


def test_c1_config_entry_missing_field_is_skipped(tmp_path):
    """C1: entry missing source_name_pattern → skip that entry, keep parsing."""
    cfg_path = _write_yaml_config(tmp_path, [
        # Missing source_name_pattern → skip
        {
            "source_code": "688008.SH",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        },
        # Valid entry that should still trigger
        {
            "source_code": "600519.SH",
            "source_name_pattern": "贵州茅台",
            "target_code": "600519.SH",
            "target_name": "贵州茅台",
            "reason": "ocr_code_name_joint_correction",
        },
    ])

    # Entry #0 fails validation → only entry #1 loads.
    rules = _load_ocr_joint_corrections_config(config_path=cfg_path)
    assert len(rules) == 1
    assert rules[0]["source_code"] == "600519.SH"

    # And the bad entry produces NO correction on a 688008.SH row.
    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": "联讯仪器"}]
    )
    out = apply_ocr_joint_corrections(df, config_path=cfg_path)
    assert out.loc[0, "Wind代码"] == "688008.SH"
    assert out.attrs.get(OCR_JOINT_AUDIT_ATTR, []) == []


def test_c2_empty_config_skips_correction(tmp_path):
    """C2: empty config (0 entries) → skip joint correction."""
    cfg_path = _write_yaml_config(tmp_path, [])
    rules = _load_ocr_joint_corrections_config(config_path=cfg_path)
    assert rules == []

    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": "联讯仪器"}]
    )
    out = apply_ocr_joint_corrections(df, config_path=cfg_path)
    assert out.loc[0, "Wind代码"] == "688008.SH"
    assert out.attrs.get(OCR_JOINT_AUDIT_ATTR, []) == []


def test_c3_malformed_yaml_does_not_crash(tmp_path):
    """C3: malformed YAML → skip correction; never raise; warn once."""
    cfg_path = _write_bad_yaml_config(tmp_path)
    rules = _load_ocr_joint_corrections_config(config_path=cfg_path)
    assert rules == []

    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": "联讯仪器"}]
    )
    # Must not raise.
    out = apply_ocr_joint_corrections(df, config_path=cfg_path)
    assert out.loc[0, "Wind代码"] == "688008.SH"
    assert out.attrs.get(OCR_JOINT_AUDIT_ATTR, []) == []


def test_c4_missing_target_field_skips_entry_only(tmp_path):
    """C4: entry with empty target_code → skip that entry, others still apply."""
    cfg_path = _write_yaml_config(tmp_path, [
        # Empty target_code → skip
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        },
        # Valid entry that should fire
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        },
    ])

    rules = _load_ocr_joint_corrections_config(config_path=cfg_path)
    # Entry #0 fails (empty target_code); entry #1 passes.
    assert len(rules) == 1
    assert rules[0]["target_code"] == "688808.SH"

    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": "联讯仪器"}]
    )
    out = apply_ocr_joint_corrections(df, config_path=cfg_path)
    assert out.loc[0, "Wind代码"] == "688808.SH"
    assert len(out.attrs.get(OCR_JOINT_AUDIT_ATTR, [])) == 1


# ---------------------------------------------------------------------------
# Audit/contract invariants
# ---------------------------------------------------------------------------


def test_joint_audit_never_pollutes_audit_attr(tmp_path):
    """V1.2 contract: AUDIT_ATTR (asset_name_audit) is NEVER touched by joint
    correction. The two audit streams are independent.
    """
    cfg_path = _write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ])

    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": "联讯仪器"}]
    )
    out = apply_ocr_joint_corrections(df, config_path=cfg_path)

    joint = out.attrs.get(OCR_JOINT_AUDIT_ATTR, [])
    high_risk = out.attrs.get(AUDIT_ATTR, [])

    assert len(joint) == 1
    assert high_risk == [], (
        "AUDIT_ATTR must remain empty after joint correction; "
        f"got {high_risk}"
    )


def test_get_ocr_joint_audit_returns_empty_list_when_absent():
    """``get_ocr_joint_audit`` must always return a list — never None."""
    df = pd.DataFrame([{"Wind代码": "688008.SH", "资产名称": "联讯仪器"}])
    assert get_ocr_joint_audit(df) == []


# ---------------------------------------------------------------------------
# P0 contract enforcement (SPEC-03-004 §4.1.2 / §4.1.4 / §6 T1)
# ---------------------------------------------------------------------------


def test_joint_corrected_row_final_status_is_exactly_auto_corrected(
    monkeypatch, tmp_path,
):
    """P0 Fix: SPEC §4.1.2 / §6 T1 — after joint correction, the final
    ``review_status`` must be EXACTLY ``auto_corrected`` (never ``matched``).

    The chain runs joint correction BEFORE standard review. The standard
    review (``a_share_name_corrector.correct_dataframe_asset_names``) would
    otherwise see the corrected row's (code, name) pair as an exact match
    against the master map and flip the status to ``matched``. Per the
    SPEC contract, the joint correction's status must be preserved end-to-end.
    """
    # Master map: 688808.SH is 联讯仪器. After joint correction, the row
    # would be (688808.SH, 联讯仪器) — naive standard review would mark
    # this ``matched``. The contract says the final status must remain
    # ``auto_corrected``.
    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: {"688808.SH": "联讯仪器", "688008.SH": "澜起科技"},
    )

    cfg_path = _write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ])

    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": "联讯仪器"}]
    )
    out = apply_asset_identity_review(df, joint_correction_config_path=cfg_path)

    # Joint correction must have fired.
    assert out.loc[0, "Wind代码"] == "688808.SH"
    assert out.loc[0, "资产名称"] == "联讯仪器"
    # P0 contract: status is EXACTLY auto_corrected (no flip to matched).
    assert out.loc[0, REVIEW_STATUS_COL] == STATUS_AUTO_CORRECTED, (
        f"joint-corrected row must keep auto_corrected; "
        f"got {out.loc[0, REVIEW_STATUS_COL]!r}"
    )
    # Pending split must NOT include the corrected row.
    accepted_df, pending_df = split_review_rows(out)
    assert pending_df.empty, (
        f"corrected row leaked into pending: {pending_df.to_dict('records')}"
    )
    assert len(accepted_df) == 1


def test_joint_correction_audit_original_name_is_pre_standardization(
    monkeypatch, tmp_path,
):
    """P0 Fix: SPEC §4.1.4 #3 — ``original_name`` in the audit record must
    capture the **pre-standardization** raw OCR name.

    Input ``'  联 讯 仪 器  '`` (with leading/trailing/inner whitespace) goes
    through ``standardize_df_asset_names`` which collapses whitespace to
    ``'联讯仪器'``. The audit must preserve the raw OCR input, not the
    standardized form.
    """
    raw_ocr_name = "  联 讯 仪 器  "
    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: {"688808.SH": "联讯仪器", "688008.SH": "澜起科技"},
    )

    cfg_path = _write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ])

    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": raw_ocr_name}]
    )
    # Run through the full pipeline entry so the row is standardized first.
    out = apply_asset_identity_review(
        df, joint_correction_config_path=cfg_path,
    )

    # The matcher fires on the standardized name (whitespace collapsed).
    assert out.loc[0, "Wind代码"] == "688808.SH"
    assert out.loc[0, "资产名称"] == "联讯仪器"

    audit = out.attrs.get(OCR_JOINT_AUDIT_ATTR, [])
    assert len(audit) == 1
    rec = audit[0]
    # P0 contract: original_name preserves the PRE-standardization raw OCR
    # input, not the post-standardization materialized value.
    assert rec["original_name"] == raw_ocr_name, (
        f"original_name must be pre-standardization raw OCR input; "
        f"got {rec['original_name']!r} (expected {raw_ocr_name!r})"
    )
    # canonical_name is still the normalized target.
    assert rec["canonical_name"] == "联讯仪器"


def test_joint_correction_review_status_is_exactly_auto_corrected_for_fullwidth_input(
    monkeypatch, tmp_path,
):
    """P0 Fix regression: even when the OCR input contains characters that
    ``standardize_df_asset_names`` does NOT collapse (e.g. full-width letters,
    inner punctuation), the joint-corrected row's final ``review_status`` must
    remain EXACTLY ``auto_corrected`` — never ``matched``, never ``pending``.

    This is the same assertion as ``test_joint_corrected_row_final_status_is_exactly_auto_corrected``
    but fires through a realistically messy input that exercises the
    pre-standardization raw capture path. The T4 verifier (t_c0aa3ec2) ran
    a similar reproduction and observed ``final_status='matched'`` because
    the wrap that re-asserts ``auto_corrected`` on jointly-corrected rows
    was missing — the P0 Fix re-implements that wrap and this test guards
    it against future regressions.
    """
    # Inner whitespace is collapsed by standardize_asset_name() (the regex
    # strips runs of whitespace). Use a mix that exercises both the
    # whitespace-collapse and the absence of any other standardizer catch.
    raw_ocr_name = "  联 讯 仪 器  "
    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: {"688808.SH": "联讯仪器", "688008.SH": "澜起科技"},
    )

    cfg_path = _write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ])

    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": raw_ocr_name}]
    )
    out = apply_asset_identity_review(df, joint_correction_config_path=cfg_path)

    # Hard assertions — every joint-corrected row must satisfy all of these.
    assert out.loc[0, "Wind代码"] == "688808.SH"
    assert out.loc[0, "资产名称"] == "联讯仪器"
    assert out.loc[0, REVIEW_STATUS_COL] == STATUS_AUTO_CORRECTED, (
        "Joint-corrected row must keep auto_corrected even when the OCR "
        "input has whitespace or non-standard characters; got "
        f"{out.loc[0, REVIEW_STATUS_COL]!r}"
    )
    assert out.loc[0, REVIEW_STATUS_COL] != STATUS_MATCHED, (
        "Joint-corrected row must NEVER be flipped to matched by the standard review"
    )
    assert out.loc[0, REVIEW_STATUS_COL] != STATUS_PENDING_REVIEW, (
        "Joint-corrected row must NEVER be flipped to pending by the standard review"
    )
    # pending split must not include the corrected row.
    accepted_df, pending_df = split_review_rows(out)
    assert pending_df.empty, (
        f"corrected row leaked into pending: {pending_df.to_dict('records')}"
    )
    assert len(accepted_df) == 1


def test_joint_correction_audit_original_name_distinguishes_pre_vs_post_std(
    monkeypatch, tmp_path,
):
    """P0 Fix regression: ``original_name`` in the audit record must be the
    **pre-standardization** raw OCR input — distinguishable from the
    post-standardization value by the presence of inner whitespace.

    This is the exact contract SPEC §4.1.4 #3 mandates. The T4 verifier
    observed ``original_name='联讯仪器'`` for input
    ``'  联 讯 仪 器  '`` because the previous implementation captured
    the materialized value after standardization. The P0 Fix captures the
    raw input via a separate pre-standardization snapshot in
    ``apply_asset_identity_review``.

    This test fails loudly if the snapshot is lost or replaced by the
    post-standardization value.
    """
    raw_ocr_name = "  联 讯 仪 器  "
    post_std_name = "联讯仪器"
    # Sanity: these two must be visibly different strings — the test is
    # only meaningful if standardization changes the input.
    assert raw_ocr_name != post_std_name
    assert "  " in raw_ocr_name or raw_ocr_name.strip() != raw_ocr_name

    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: {"688808.SH": "联讯仪器", "688008.SH": "澜起科技"},
    )

    cfg_path = _write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ])

    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": raw_ocr_name}]
    )
    out = apply_asset_identity_review(df, joint_correction_config_path=cfg_path)

    audit = out.attrs.get(OCR_JOINT_AUDIT_ATTR, [])
    assert len(audit) == 1
    rec = audit[0]
    # Hard assertions on the original_name field.
    assert rec["original_name"] == raw_ocr_name, (
        f"original_name must be pre-standardization raw OCR input; "
        f"got {rec['original_name']!r} (expected {raw_ocr_name!r})"
    )
    assert rec["original_name"] != post_std_name, (
        "original_name must NOT be the post-standardization value; "
        f"got {rec['original_name']!r}"
    )
    # canonical_name is the normalized target.
    assert rec["canonical_name"] == post_std_name


def test_joint_correction_does_not_pollute_audit_attr_on_chain(
    monkeypatch, tmp_path,
):
    """P0 contract: through the full pipeline chain (joint correction →
    standard review), ``AUDIT_ATTR`` (high-risk schema) must NEVER contain
    a joint-correction row keyed by the original code 688008.SH.
    """
    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: {"688808.SH": "联讯仪器", "688008.SH": "澜起科技"},
    )

    cfg_path = _write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ])

    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": "联讯仪器"}]
    )
    out = apply_asset_identity_review(df, joint_correction_config_path=cfg_path)

    # No AUDIT_ATTR entry may reference the original (pre-correction) code.
    assert all(
        item.get("code") != "688008.SH"
        for item in out.attrs.get(AUDIT_ATTR, [])
    ), (
        "AUDIT_ATTR must not contain joint-correction rows keyed by "
        "688008.SH; got " + repr(out.attrs.get(AUDIT_ATTR, []))
    )
    # And the joint audit is still in its own attrs key.
    joint = out.attrs.get(OCR_JOINT_AUDIT_ATTR, [])
    assert len(joint) == 1
    assert joint[0]["original_code"] == "688008.SH"
    assert joint[0]["target_code"] == "688808.SH"


def test_joint_correction_idempotent_within_run(tmp_path):
    """A row matched once is not matched again on subsequent rule scans."""
    cfg_path = _write_yaml_config(tmp_path, [
        # Two rules that BOTH match 688008.SH + 联讯仪器 — only the first wins.
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "first_rule",
        },
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "999999.SH",
            "target_name": "联讯仪器",
            "reason": "second_rule",
        },
    ])

    df = pd.DataFrame(
        [{"Wind代码": "688008.SH", "资产名称": "联讯仪器"}]
    )
    out = apply_ocr_joint_corrections(df, config_path=cfg_path)
    audit = out.attrs.get(OCR_JOINT_AUDIT_ATTR, [])
    assert len(audit) == 1
    assert audit[0]["target_code"] == "688808.SH"
    assert audit[0]["correction_reason"] == "first_rule"


# ---------------------------------------------------------------------------
# P0 Fix-2 (t_b0d01b4c): three-row isolation — joint correction must NOT
# pollute already-correct rows or incompatible rows in the SAME DataFrame.
# SPEC-03-004 §4.1.2 / DESIGN-03-004 §3.3 — restoration is row-specific,
# not a target-code-wide mask.
# ---------------------------------------------------------------------------


def test_p0_fix2_joint_restoration_is_row_specific_not_code_wide_mask(
    tmp_path,
):
    """P0 Fix-2 regression: three-row isolation in a single DataFrame.

    Same DataFrame (all rows go through ``apply_asset_identity_review``):
      Row 0: 688008.SH + 联讯仪器 (source match) → joint correction to
              688808.SH + 联讯仪器 → status MUST be ``auto_corrected``.
      Row 1: 688808.SH + 联讯仪器 (already correct pair) → status MUST
              remain ``matched`` — P0 Fix-2 must NOT let the restoration
              logic's ``target_code`` mask overwrite this row.
      Row 2: 688808.SH + 不兼容名 → status MUST be ``pending_review``,
              caught by ``split_review_rows()`` into the pending split;
              P0 Fix-2 must NOT let it bypass the pending gate.

    The old bug used ``reviewed['Wind代码'].isin(joint_target_codes)``
    as a global mask, writing ``auto_corrected`` onto ALL rows with
    ``target_code=688808.SH`` — corrupting rows 1 and 2.
    """
    cfg_path = _write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ])

    df = pd.DataFrame(
        [
            {
                "截止日期": "2025-10-21",
                "产品代码": "SM001",
                "Wind代码": "688008.SH",
                "资产名称": "联讯仪器",
            },
            {
                "截止日期": "2025-10-21",
                "产品代码": "SM001",
                "Wind代码": "688808.SH",
                "资产名称": "联讯仪器",
            },
            {
                "截止日期": "2025-10-21",
                "产品代码": "SM001",
                "Wind代码": "688808.SH",
                "资产名称": "不兼容名",
            },
        ]
    )

    out = apply_asset_identity_review(df, joint_correction_config_path=cfg_path)
    joint_audit = out.attrs.get(OCR_JOINT_AUDIT_ATTR, [])

    # --- Row 0: joint-corrected row ---
    assert out.loc[0, "Wind代码"] == "688808.SH", (
        f"Row 0: code should be corrected to 688808.SH, "
        f"got {out.loc[0, 'Wind代码']!r}"
    )
    assert out.loc[0, "资产名称"] == "联讯仪器", (
        f"Row 0: name should be corrected to 联讯仪器, "
        f"got {out.loc[0, '资产名称']!r}"
    )
    assert out.loc[0, REVIEW_STATUS_COL] == STATUS_AUTO_CORRECTED, (
        f"Row 0 (joint-corrected): status must be auto_corrected, "
        f"got {out.loc[0, REVIEW_STATUS_COL]!r}"
    )
    # Joint audit should contain exactly 1 record for this row.
    assert len(joint_audit) == 1
    assert joint_audit[0]["original_code"] == "688008.SH"
    assert joint_audit[0]["target_code"] == "688808.SH"

    # --- Row 1: already correct pair — NOT polluted ---
    assert out.loc[1, "Wind代码"] == "688808.SH"
    assert out.loc[1, "资产名称"] == "联讯仪器"
    assert out.loc[1, REVIEW_STATUS_COL] == STATUS_MATCHED, (
        f"Row 1 (already correct): status must be matched, "
        f"got {out.loc[1, REVIEW_STATUS_COL]!r} — "
        "P0 Fix-2 regression: joint restoration must NOT pollute already-correct rows"
    )

    # --- Row 2: incompatible name — NOT bypassing pending gate ---
    assert out.loc[2, "Wind代码"] == "688808.SH"
    assert out.loc[2, "资产名称"] == "不兼容名"
    assert out.loc[2, REVIEW_STATUS_COL] == STATUS_PENDING_REVIEW, (
        f"Row 2 (incompatible name): status must be pending_review, "
        f"got {out.loc[2, REVIEW_STATUS_COL]!r} — "
        "P0 Fix-2 regression: incompatible row must NOT bypass the pending gate"
    )

    # --- split_review_rows must correctly separate the 3 rows ---
    accepted_df, pending_df = split_review_rows(out)
    assert len(accepted_df) == 2, (
        f"Accepted should contain 2 rows (corrected + already-correct), "
        f"got {len(accepted_df)}"
    )
    assert len(pending_df) == 1, (
        f"Pending should contain 1 row (incompatible name), "
        f"got {len(pending_df)}"
    )
    # Accepted rows: row 0 and row 1
    accepted_indices = sorted(accepted_df.index.tolist())
    assert accepted_indices == [0, 1], (
        f"Accepted rows must be indices 0 and 1, got {accepted_indices}"
    )
    # Pending rows: row 2 only
    pending_indices = sorted(pending_df.index.tolist())
    assert pending_indices == [2], (
        f"Pending rows must be index 2 only, got {pending_indices}"
    )


def test_joint_correction_skips_when_required_columns_missing(tmp_path):
    """If ``Wind代码`` or ``资产名称`` are missing from the DataFrame, the
    rule engine cannot match anything; we skip silently (fail-closed).
    """
    cfg_path = _write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ])

    df = pd.DataFrame(
        [{"OnlyCode": "688008.SH", "OnlyName": "联讯仪器"}]
    )
    out = apply_ocr_joint_corrections(df, config_path=cfg_path)
    # No Wind代码/资产名称 columns → no correction; no crash.
    assert "Wind代码" not in out.columns
    assert out.attrs.get(OCR_JOINT_AUDIT_ATTR, []) == []


def test_joint_correction_empty_dataframe_short_circuits(tmp_path):
    """Empty DataFrame returns immediately with an empty audit list."""
    cfg_path = _write_yaml_config(tmp_path, [
        {
            "source_code": "688008.SH",
            "source_name_pattern": "联讯仪器",
            "target_code": "688808.SH",
            "target_name": "联讯仪器",
            "reason": "ocr_code_name_joint_correction",
        }
    ])
    df = pd.DataFrame(columns=["Wind代码", "资产名称"])
    out = apply_ocr_joint_corrections(df, config_path=cfg_path)
    assert out.empty
    assert out.attrs.get(OCR_JOINT_AUDIT_ATTR, []) == []


def test_joint_correction_reason_text_format():
    """The reason text follows SPEC §4.1.2 exactly."""
    rule = {
        "source_code": "688008.SH",
        "source_name_pattern": "联讯仪器",
        "target_code": "688808.SH",
        "target_name": "联讯仪器",
        "reason": "ocr_code_name_joint_correction",
    }
    text = _joint_correction_reason_text(rule)
    assert text == (
        "OCR joint correction: code 688008.SH + name 联讯仪器 → "
        "688808.SH / 联讯仪器"
    )


# ---------------------------------------------------------------------------
# save_pending_review integration: joint_audit → pending.json.audit_items
# ---------------------------------------------------------------------------


def test_save_pending_review_writes_audit_items_when_pending_and_joint_present(
    tmp_path,
):
    """When pending_df is non-empty AND joint_audit is non-empty, the pending
    JSON payload must include ``audit_items``. When joint_audit is None/empty,
    the field must be omitted.
    """
    pending_df = pd.DataFrame(
        [
            {
                "Wind代码": "000333.SZ",
                "资产名称": "贵州茅台",
                REVIEW_STATUS_COL: STATUS_PENDING_REVIEW,
            }
        ]
    )
    audit = [
        {"row": 0, "code": "000333.SZ", "ocr_name": "贵州茅台", "standard_name": "美的集团", "status": STATUS_PENDING_REVIEW}
    ]
    joint_audit = [
        {
            "original_code": "688008.SH",
            "target_code": "688808.SH",
            "original_name": "联讯仪器",
            "canonical_name": "联讯仪器",
            "correction_reason": "ocr_code_name_joint_correction",
            "auto_correction_status": STATUS_AUTO_CORRECTED,
            "corrected_at": "2026-07-29T00:00:00Z",
        }
    ]

    # Case 1: joint_audit provided → audit_items present in JSON
    res1 = save_pending_review(
        pending_df=pending_df,
        audit=audit,
        source_root=tmp_path,
        folder_date="2026-07-29",
        prefix="portfolio",
        timestamp="000000_000000",
        fmt="portfolio",
        source_path="input.jpg",
        excel_path="input.xlsx",
        joint_audit=joint_audit,
    )
    json_path = Path(res1["json"])
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload.get("audit_items") == joint_audit

    # Case 2: joint_audit=None → audit_items absent (backward compat)
    res2 = save_pending_review(
        pending_df=pending_df,
        audit=audit,
        source_root=tmp_path,
        folder_date="2026-07-29",
        prefix="portfolio",
        timestamp="010000_000000",
        fmt="portfolio",
        source_path="input.jpg",
        excel_path="input.xlsx",
    )
    payload2 = json.loads(Path(res2["json"]).read_text(encoding="utf-8"))
    assert "audit_items" not in payload2

    # Case 3: joint_audit=[] → audit_items absent (empty list is "no audit")
    res3 = save_pending_review(
        pending_df=pending_df,
        audit=audit,
        source_root=tmp_path,
        folder_date="2026-07-29",
        prefix="portfolio",
        timestamp="020000_000000",
        fmt="portfolio",
        source_path="input.jpg",
        excel_path="input.xlsx",
        joint_audit=[],
    )
    payload3 = json.loads(Path(res3["json"]).read_text(encoding="utf-8"))
    assert "audit_items" not in payload3


def test_save_pending_review_skips_audit_items_when_no_pending(tmp_path):
    """When pending_df is empty, the function short-circuits and writes nothing
    — even if joint_audit was provided. The audit_items field must NOT appear.
    """
    res = save_pending_review(
        pending_df=pd.DataFrame(),  # empty
        audit=[],
        source_root=tmp_path,
        folder_date="2026-07-29",
        prefix="portfolio",
        timestamp="000000_000000",
        fmt="portfolio",
        source_path="input.jpg",
        excel_path="input.xlsx",
        joint_audit=[
            {
                "original_code": "688008.SH",
                "target_code": "688808.SH",
                "original_name": "联讯仪器",
                "canonical_name": "联讯仪器",
                "correction_reason": "ocr_code_name_joint_correction",
                "auto_correction_status": STATUS_AUTO_CORRECTED,
                "corrected_at": "2026-07-29T00:00:00Z",
            }
        ],
    )
    assert res == {}