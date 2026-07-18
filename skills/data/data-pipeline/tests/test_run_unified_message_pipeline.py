"""Unit tests for run_unified_message_pipeline.run_pipeline().

Covers the Smart Money message-input pipeline partial-load behavior
(DESIGN-03-004): when some rows are auto-corrected and others go to
pending review, only the accepted rows are written to MongoDB while the
pending rows are persisted to a review CSV. OCR / MongoDB are faked.
"""
import asyncio
import sys
from pathlib import Path

import pandas as pd  # noqa: F401  # kept for parity with sibling test files

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_unified_message_pipeline as message_pipeline  # noqa: E402
from transformers import a_share_name_corrector  # noqa: E402


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
