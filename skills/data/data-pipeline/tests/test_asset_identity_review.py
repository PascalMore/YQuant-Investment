"""Unit tests for transformers/asset_identity_review.py.

Covers the Smart Money review gate (DESIGN-03-004): static Wind-code →
asset-name mapping compatibility check, and the filter that drops
pending-review rows from the normalized output that gets written to
MongoDB. No real MongoDB / OCR / network.
"""
import sys
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_unified_image_pipeline as image_pipeline  # noqa: E402
from transformers import a_share_name_corrector  # noqa: E402
from transformers.a_share_name_corrector import correct_dataframe_asset_names  # noqa: E402
from transformers.asset_identity_review import (  # noqa: E402
    REVIEW_STATUS_COL,
    filter_pending_normalized_records,
    split_review_rows,
)


def test_static_code_mapping_requires_compatible_name():
    df = pd.DataFrame(
        [
            {"Wind代码": "0700.HK", "资产名称": "腾讯控股"},
            {"Wind代码": "0700.HK", "资产名称": "阿里巴巴-W"},
        ]
    )

    result = image_pipeline.correct_stock_names(df)

    assert result.loc[0, "资产名称"] == "腾讯控股"
    assert result.loc[1, "资产名称"] == "阿里巴巴-W"


def test_static_code_mapping_mismatch_goes_pending():
    df = pd.DataFrame(
        [{"Wind代码": "0700.HK", "资产名称": "阿里巴巴-W"}]
    )

    result = image_pipeline.apply_asset_identity_review(df)
    accepted_df, pending_df = split_review_rows(result)

    assert result.loc[0, "资产名称"] == "阿里巴巴-W"
    assert result.loc[0, REVIEW_STATUS_COL] == "pending_review"
    assert accepted_df.empty
    assert len(pending_df) == 1
    assert image_pipeline.high_risk_asset_name_issues(result)[0]["standard_name"] == "腾讯控股"


def test_pending_rows_are_filtered_from_normalized_positions(monkeypatch):
    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: {"000333.SZ": "美的集团"},
    )
    df = pd.DataFrame(
        [
            {
                "截止日期": "2025-10-21",
                "产品代码": "SM001",
                "Wind代码": "0700.HK",
                "资产名称": "腾讯控股",
            },
            {
                "截止日期": "2025-10-21",
                "产品代码": "SM001",
                "Wind代码": "000333.SZ",
                "资产名称": "贵州茅台",
            },
        ]
    )
    reviewed = correct_dataframe_asset_names(df)
    accepted_df, pending_df = split_review_rows(reviewed)
    normalized = {
        "position": [
            {
                "position_date": "2025-10-21",
                "product_code": "SM001",
                "asset_wind_code": "0700.HK",
                "asset_name": "腾讯控股",
            },
            {
                "position_date": "2025-10-21",
                "product_code": "SM001",
                "asset_wind_code": "000333.SZ",
                "asset_name": "贵州茅台",
            },
        ]
    }

    filtered = filter_pending_normalized_records(normalized, pending_df, "portfolio")

    assert len(accepted_df) == 1
    assert len(pending_df) == 1
    assert filtered["position"] == [
        {
            "position_date": "2025-10-21",
            "product_code": "SM001",
            "asset_wind_code": "0700.HK",
            "asset_name": "腾讯控股",
        }
    ]
