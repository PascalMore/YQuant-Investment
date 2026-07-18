"""Unit tests for run_unified_image_pipeline.run_pipeline().

Covers the Smart Money image-input pipeline partial-load behavior
(DESIGN-03-004): when some rows are auto-corrected and others go to
pending review, only the accepted rows are written to MongoDB while the
pending rows are persisted to a review CSV.

The current run_pipeline signature is:
    run_pipeline(image_path, source_root, folder_date=None, output_dir=None, dry_run=False)

``folder_date`` is the *system* date (archive folder), not the business
date — the business date (position_date / nav_date) is read from the
OCR-extracted ``截止日期`` column. OCR / MongoDB are faked.
"""
import asyncio
import sys
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_unified_image_pipeline as image_pipeline  # noqa: E402
from transformers import a_share_name_corrector  # noqa: E402


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
            source_root=tmp_path,
            folder_date="2026-06-15",
            dry_run=False,
        )
    )

    assert result["status"] == "partial_success"
    assert result["position"] == 1
    assert result["review"]["pending_rows"] == 1
    assert Path(result["pending"]["csv"]).exists()
    assert captured["normalized"]["position"][0]["asset_wind_code"] == "0700.HK"
