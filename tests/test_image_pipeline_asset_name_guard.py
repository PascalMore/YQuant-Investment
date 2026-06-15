import sys
import asyncio
from pathlib import Path

import pandas as pd


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "data" / "data-pipeline" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_unified_image_pipeline as image_pipeline  # noqa: E402
import run_unified_message_pipeline as message_pipeline  # noqa: E402
from batch_report import summarize_batch_results  # noqa: E402
from transformers import a_share_name_corrector  # noqa: E402
from transformers.asset_identity_review import (  # noqa: E402
    filter_pending_normalized_records,
    split_review_rows,
)
from transformers.a_share_name_corrector import (  # noqa: E402
    AUDIT_ATTR,
    REVIEW_STATUS_COL,
    correct_dataframe_asset_names,
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
    assert image_pipeline.high_risk_asset_name_issues(result) == []


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
    issues = image_pipeline.high_risk_asset_name_issues(result)

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
    assert image_pipeline.high_risk_asset_name_issues(result)[0]["reason"] == "A-share master data unavailable"


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


def test_message_pipeline_partially_loads_accepted_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: {"000333.SZ": "美的集团"},
    )
    captured = {}

    class FakeLoader:
        def load_all(self, normalized):
            captured["normalized"] = normalized
            return {
                "basic_info": len(normalized.get("basic_info", [])),
                "nav": len(normalized.get("nav", [])),
                "position": len(normalized.get("position", [])),
            }

    monkeypatch.setattr(message_pipeline, "PortfolioMongoLoader", FakeLoader)
    raw = "\n".join(
        [
            "截止日期,产品代码,产品名称,最新净值,最新份额,最新规模,Wind代码,资产名称,持仓比例,数量,市值(本币)",
            "2025-10-21,SM001,JS-001,1.1,1000,1100,0700.HK,腾讯控股,0.01,100,100",
            "2025-10-21,SM001,JS-001,1.1,1000,1100,000333.SZ,贵州茅台,0.02,200,200",
        ]
    )

    result = asyncio.run(
        message_pipeline.run_pipeline(
            raw,
            "2025-10-21",
            tmp_path,
            folder_date="2026-06-15",
            dry_run=False,
        )
    )

    assert result["status"] == "partial_success"
    assert result["position"] == 1
    assert result["review"]["pending_rows"] == 1
    assert Path(result["pending"]["csv"]).exists()
    assert captured["normalized"]["position"][0]["asset_wind_code"] == "0700.HK"


def test_image_pipeline_partially_loads_accepted_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(
        a_share_name_corrector,
        "load_a_share_name_map",
        lambda: {"000333.SZ": "美的集团"},
    )

    image_path = tmp_path / "input.jpg"
    image_path.write_bytes(b"fake image")
    df = pd.DataFrame(
        [
            {
                "截止日期": "2025-10-21",
                "产品代码": "SM001",
                "产品名称": "JS-001",
                "最新净值": "1.1",
                "最新份额": "1000",
                "最新规模": "1100",
                "Wind代码": "0700.HK",
                "资产名称": "腾讯控股",
                "持仓比例": "0.01",
                "数量": "100",
                "市值(本币)": "100",
            },
            {
                "截止日期": "2025-10-21",
                "产品代码": "SM001",
                "产品名称": "JS-001",
                "最新净值": "1.1",
                "最新份额": "1000",
                "最新规模": "1100",
                "Wind代码": "000333.SZ",
                "资产名称": "贵州茅台",
                "持仓比例": "0.02",
                "数量": "200",
                "市值(本币)": "200",
            },
        ]
    )

    class FakeExtractor:
        def __init__(self, *args, **kwargs):
            pass

        async def extract(self, source):
            return [{"df": df.copy(), "source_path": source}]

    captured = {}

    class FakeLoader:
        def load_all(self, normalized):
            captured["normalized"] = normalized
            return {
                "basic_info": len(normalized.get("basic_info", [])),
                "nav": len(normalized.get("nav", [])),
                "position": len(normalized.get("position", [])),
            }

    monkeypatch.setattr(image_pipeline, "MiniMaxImageExtractor", FakeExtractor)
    monkeypatch.setattr(image_pipeline, "PortfolioMongoLoader", FakeLoader)

    result = asyncio.run(
        image_pipeline.run_pipeline(
            str(image_path),
            "2025-10-21",
            tmp_path,
            folder_date="2026-06-15",
            dry_run=False,
        )
    )

    assert result["status"] == "partial_success"
    assert result["position"] == 1
    assert result["review"]["pending_rows"] == 1
    assert Path(result["pending"]["csv"]).exists()
    assert captured["normalized"]["position"][0]["asset_wind_code"] == "0700.HK"


def test_batch_summary_counts_status_and_pending_rows():
    summary = summarize_batch_results(
        [
            {"status": "success", "rows": 2, "mongodb": {"position": 2}},
            {"status": "partial_success", "review": {"accepted_rows": 1, "pending_rows": 1}},
            {"status": "failed", "error": "boom"},
        ]
    )

    assert summary["total"] == 3
    assert summary["success"] == 1
    assert summary["partial_success"] == 1
    assert summary["failed"] == 1
    assert summary["accepted_rows"] == 3
    assert summary["pending_rows"] == 1
    assert summary["mongodb"] == {"position": 2}
