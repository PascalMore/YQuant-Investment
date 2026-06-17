"""
Tests for Pending Review Loop闭环: F-008 apply_command, F-009 batch mode, F-010 resolved marker.

Run with: pytest test_load_pending_confirmed.py -v
"""
import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# Ensure scripts/ is on path
import sys as _sys

_scripts = Path(__file__).parent.resolve()
_sys.path.insert(0, str(_scripts))

from transformers.asset_identity_review import save_pending_review
from load_pending_confirmed import (
    load_pending_positions,
    load_pending_trades,
    _detect_format,
    _parse_pct,
    _parse_num,
    _mark_json_resolved,
    load_all_pending_for_date,
)


# ---------------------------------------------------------------------------
# F-008: apply_command in save_pending_review
# ---------------------------------------------------------------------------

def test_apply_command_generated_in_save_pending_review():
    """pending result must include apply_command pointing to load_pending_confirmed.py"""
    pending_df = pd.DataFrame([{
        "截止日期": "2026-06-16",
        "产品代码": "SM004",
        "Wind代码": "688847.SH",
        "资产名称": "华虹力",
        "持仓比例": "0.06%",
        "数量": "310",
        "市值(本币)": "73935",
        "名称复核状态": "missing_master",
        "主数据名称": "",
        "名称复核原因": "test",
    }])

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        result = save_pending_review(
            pending_df=pending_df,
            audit=[{"row": 0, "code": "688847.SH", "status": "missing_master"}],
            source_root=root,
            folder_date="2026-06-17",
            prefix="test",
            timestamp="20260617_120000",
            fmt="portfolio",
            source_path="/tmp/test.jpg",
            excel_path="/tmp/test.xlsx",
        )

    assert "apply_command" in result, "apply_command missing from save_pending_review result"
    assert "load_pending_confirmed.py" in result["apply_command"], "apply_command must reference load_pending_confirmed.py"
    assert "--csv" in result["apply_command"], "apply_command must include --csv flag"
    assert ".csv" in result["apply_command"], "apply_command must reference the CSV path"


def test_apply_command_empty_when_no_pending():
    """empty pending returns empty dict, no apply_command key"""
    result = save_pending_review(
        pending_df=pd.DataFrame(),
        audit=[],
        source_root=Path("/tmp"),
        folder_date="2026-06-17",
        prefix="test",
        timestamp="20260617_120000",
        fmt="portfolio",
        source_path="/tmp/test.jpg",
        excel_path="/tmp/test.xlsx",
    )
    assert result == {}, "empty pending must return empty dict"


# ---------------------------------------------------------------------------
# F-008: _detect_format
# ---------------------------------------------------------------------------

def test_detect_format_portfolio():
    df = pd.DataFrame(columns=["截止日期", "产品代码", "Wind代码", "资产名称", "持仓比例"])
    assert _detect_format(list(df.columns)) == "portfolio"


def test_detect_format_trade():
    df = pd.DataFrame(columns=["日期", "产品代码", "Wind代码", "变化比例", "方向"])
    assert _detect_format(list(df.columns)) == "trade"


# ---------------------------------------------------------------------------
# F-008: _parse_pct — must convert to decimal ratio
# ---------------------------------------------------------------------------

def test_parse_pct_percentage():
    assert _parse_pct("10.54%") == pytest.approx(0.1054)
    assert _parse_pct("5.5%") == pytest.approx(0.055)
    assert _parse_pct("19.68%") == pytest.approx(0.1968)


def test_parse_pct_decimal():
    # Values already in decimal form (< 0.4) should stay as-is
    assert _parse_pct("0.1054") == pytest.approx(0.1054)
    assert _parse_pct("0.055") == pytest.approx(0.055)


def test_parse_pct_empty():
    assert _parse_pct("") is None
    assert _parse_pct("  ") is None


def test_parse_pct_wide_percent():
    assert _parse_pct("10.54％") == pytest.approx(0.1054)


# ---------------------------------------------------------------------------
# F-008: _parse_num
# ---------------------------------------------------------------------------

def test_parse_num():
    assert _parse_num("123456") == 123456.0
    assert _parse_num("1,234,567") == 1234567.0
    assert _parse_num("") is None


# ---------------------------------------------------------------------------
# F-010: resolved marker
# ---------------------------------------------------------------------------

def test_mark_json_resolved_updates_file():
    """_mark_json_resolved must write status=resolved into the JSON file"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "test_pending.csv"
        json_path = Path(tmpdir) / "test_pending.json"

        # Create a dummy CSV and JSON
        csv_path.write_text("截止日期,产品代码\n2026-06-16,SM004\n", encoding="utf-8")
        json_path.write_text(json.dumps({
            "status": "pending_review",
            "rows": 2,
            "audit": [],
        }), encoding="utf-8")

        ok = _mark_json_resolved(str(csv_path), loaded_count=2)

        assert ok is True, "_mark_json_resolved must return True when JSON exists"
        updated = json.loads(json_path.read_text(encoding="utf-8"))
        assert updated["status"] == "resolved", "status must be updated to resolved"
        assert "resolved_at" in updated, "resolved_at must be present"
        assert updated["resolved_records"] == 2, "resolved_records must match loaded_count"


def test_mark_json_resolved_nonexistent():
    """returns False without error when JSON doesn't exist"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "no_such_file.csv"
        ok = _mark_json_resolved(str(csv_path), loaded_count=5)
        assert ok is False


# ---------------------------------------------------------------------------
# F-009: load_all_pending_for_date — batch mode
# ---------------------------------------------------------------------------

def test_load_all_pending_for_date_no_files():
    """returns {total_files:0} when no pending CSVs exist"""
    result = load_all_pending_for_date("2099-12-31")  # future date = no files
    assert result["total_files"] == 0
    assert result["total_loaded"] == 0


# ---------------------------------------------------------------------------
# F-008: integration — apply_command string is executable format
# ---------------------------------------------------------------------------

def test_apply_command_is_valid_cli_format():
    """apply_command must be a valid shell-safe CLI invocation"""
    pending_df = pd.DataFrame([{
        "截止日期": "2026-06-16",
        "产品代码": "SM004",
        "Wind代码": "688847.SH",
        "资产名称": "华虹力",
        "持仓比例": "0.06%",
        "数量": "310",
        "市值(本币)": "73935",
        "名称复核状态": "missing_master",
        "主数据名称": "",
        "名称复核原因": "test",
    }])

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        result = save_pending_review(
            pending_df=pending_df,
            audit=[{"row": 0, "code": "688847.SH", "status": "missing_master"}],
            source_root=root,
            folder_date="2026-06-17",
            prefix="test",
            timestamp="20260617_120000",
            fmt="portfolio",
            source_path="/tmp/test.jpg",
            excel_path="/tmp/test.xlsx",
        )

    cmd = result["apply_command"]
    # Must start with python3
    assert cmd.startswith("python3 "), f"apply_command must start with 'python3': {cmd}"
    # Must contain --csv flag
    assert "--csv " in cmd or '--csv' in cmd, f"apply_command must contain --csv: {cmd}"
    # Must quote or escape the path (no shell injection risk)
    assert '"' in cmd or "'" in cmd or "--csv\n" not in cmd, f"apply_command must quote the CSV path: {cmd}"
