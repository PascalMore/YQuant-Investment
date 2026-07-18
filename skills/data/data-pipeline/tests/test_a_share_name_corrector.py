"""Unit tests for transformers/a_share_name_corrector.py.

Covers the A-share master-data lookup + asset name compatibility check
that feeds the Smart Money review gate (DESIGN-03-004). These tests do
not touch MongoDB, OCR, or network: load_a_share_name_map is monkeypatched
to return a fixed in-memory mapping.
"""
import sys
from pathlib import Path

import pandas as pd

# Put the data-pipeline ``scripts/`` directory on sys.path so that imports
# such as ``from transformers import ...`` resolve the same way the
# production entry-points (run_unified_image_pipeline.py etc.) see them.
# This mirrors the bootstrap those entry-points perform at startup.
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from transformers import a_share_name_corrector  # noqa: E402
from transformers.a_share_name_corrector import (  # noqa: E402
    AUDIT_ATTR,
    REVIEW_STATUS_COL,
    correct_dataframe_asset_names,
)
from transformers.asset_identity_review import (  # noqa: E402
    high_risk_asset_name_issues,
    split_review_rows,
)


def test_compatible_a_share_name_is_auto_corrected(monkeypatch):
    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: {"688019.SH": "安集科技"},
    )
    df = pd.DataFrame(
        [{"Wind代码": "688019.SH", "资产名称": "DR安集科", "持仓比例": 0.01}]
    )

    result = correct_dataframe_asset_names(df)

    assert result.loc[0, "资产名称"] == "安集科技"
    assert result.loc[0, REVIEW_STATUS_COL] == "auto_corrected"
    assert high_risk_asset_name_issues(result) == []


def test_incompatible_a_share_name_is_not_corrected_and_blocks(monkeypatch):
    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: {"000333.SZ": "美的集团"},
    )
    df = pd.DataFrame(
        [{"Wind代码": "000333.SZ", "资产名称": "贵州茅台", "持仓比例": 0.01}]
    )

    result = correct_dataframe_asset_names(df)
    issues = high_risk_asset_name_issues(result)

    assert result.loc[0, "资产名称"] == "贵州茅台"
    assert result.loc[0, REVIEW_STATUS_COL] == "pending_review"
    assert result.attrs[AUDIT_ATTR][0]["standard_name"] == "美的集团"
    assert len(issues) == 1
    assert issues[0]["code"] == "000333.SZ"


def test_a_share_master_data_unavailable_marks_pending(monkeypatch):
    def raise_unavailable():
        raise RuntimeError("db down")

    monkeypatch.setattr(a_share_name_corrector, "load_a_share_name_map", raise_unavailable)
    df = pd.DataFrame(
        [{"Wind代码": "000333.SZ", "资产名称": "美的集团", "持仓比例": 0.01}]
    )

    result = correct_dataframe_asset_names(df)
    accepted_df, pending_df = split_review_rows(result)

    assert result.loc[0, REVIEW_STATUS_COL] == "pending_review"
    assert accepted_df.empty
    assert len(pending_df) == 1
    assert high_risk_asset_name_issues(result)[0]["reason"] == "A-share master data unavailable"
