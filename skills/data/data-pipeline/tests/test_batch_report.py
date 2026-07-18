"""Unit tests for batch_report.py.

Covers the Smart Money batch closeout summarization + formatting
(DESIGN-03-004): per-status counts, accepted/pending row totals,
confirmation item extraction, and structured closeout object assembly.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from batch_report import (  # noqa: E402
    build_batch_closeout,
    format_batch_closeout,
    summarize_batch_results,
)


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


def test_batch_closeout_marks_confirmation_items():
    summary = summarize_batch_results(
        [
            {
                "status": "partial_success",
                "source": "portfolio.jpg",
                "format": "portfolio",
                "rows": 1,
                "review": {
                    "accepted_rows": 1,
                    "pending_rows": 2,
                    "pending_files": {"csv": "review_pending/portfolio_pending.csv"},
                },
            },
            {"status": "failed", "source": "trade.jpg", "error": "MiniMax system error"},
        ]
    )

    closeout = format_batch_closeout(summary, "Smart Money 2026-06-16")

    assert summary["closeout_status"] == "attention_required"
    assert len(summary["needs_confirmation"]) == 2
    assert "确认问题" in closeout
    assert "review_pending/portfolio_pending.csv" in closeout
    assert "MiniMax system error" in closeout


def test_batch_closeout_requests_confirmation_when_clean():
    summary = summarize_batch_results(
        [
            {
                "status": "success",
                "source": "portfolio.jpg",
                "format": "portfolio",
                "rows": 19,
                "review": {"accepted_rows": 19, "pending_rows": 0},
                "mongodb": {"position": 19, "nav": 1, "basic_info": 1},
            }
        ]
    )

    closeout = format_batch_closeout(summary, "Smart Money 2026-06-16")

    assert summary["closeout_status"] == "success"
    assert summary["needs_confirmation"] == []
    assert "已复核完成" in closeout
    assert "确认问题" in closeout


def test_build_batch_closeout_returns_structured_clean_closeout():
    summary = summarize_batch_results(
        [
            {
                "status": "success",
                "source": "portfolio.jpg",
                "rows": 5,
                "mongodb": {"position": 5},
            }
        ]
    )

    closeout = build_batch_closeout(summary)

    assert closeout["kind"] == "smart_money_batch_closeout"
    assert closeout["status"] == "closed_clean"
    assert closeout["confirmation"]["required"] is True
    assert closeout["confirmation"]["expected_user_action"] == "confirm_archive"
    assert closeout["mongodb_counts"] == {"position": 5}
    assert "message_text" in closeout
    assert "确认问题" in closeout["message_text"]


def test_build_batch_closeout_pending_review_requires_confirmation():
    summary = summarize_batch_results(
        [
            {
                "status": "partial_success",
                "source": "portfolio.jpg",
                "review": {
                    "accepted_rows": 3,
                    "pending_rows": 2,
                    "pending_files": {"csv": "review_pending/portfolio.csv"},
                },
            }
        ]
    )

    closeout = build_batch_closeout(summary)

    assert closeout["status"] == "closed_needs_confirmation"
    assert closeout["confirmation"]["expected_user_action"] == "confirm_pending_resolution"
    assert closeout["needs_confirmation_items"][0]["pending_rows"] == 2
    assert "review_pending/portfolio.csv" in closeout["message_text"]


def test_build_batch_closeout_failed_has_priority_over_pending():
    summary = summarize_batch_results(
        [
            {
                "status": "partial_success",
                "source": "portfolio.jpg",
                "review": {"accepted_rows": 1, "pending_rows": 1},
            },
            {"status": "failed", "source": "broken.jpg", "error": "OCR failed"},
        ]
    )

    closeout = build_batch_closeout(summary)

    assert closeout["status"] == "closed_with_failures"
    assert closeout["confirmation"]["expected_user_action"] == "retry_or_ignore_failures"
    assert closeout["failed_items"] == [
        {"source": "broken.jpg", "status": "failed", "error": "OCR failed"}
    ]
