"""Explicit image batch state for YQuant chat-driven closeout.

The Smart Money image pipeline still processes each image independently. This
module only stores those per-image results until the user sends a batch-end
message such as "图片批次已上传". The caller then invokes ``close_batch_now()``
and sends the returned ``message_text``.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
import threading

WORKSPACE = Path(__file__).resolve().parents[4]  # workspace-yquant
STATE_DIR = WORKSPACE / ".openclaw"
RESULTS_FILE = STATE_DIR / "image_batch_results.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)

_state_lock = threading.Lock()


# --------------------------------------------------------------------
# Batch-end trigger phrases
# --------------------------------------------------------------------
BATCH_END_PHRASES = [
    "图片批次已上传",
    "就这些",
    "处理完了",
    "发完了",
    "没有了",
]


def is_batch_end(message: str) -> bool:
    """Return True if ``message`` contains a batch-end trigger phrase.


    Case-insensitive match. Call this when processing each user message
    to detect "图片批次已上传" and similar phrases.
    """
    lower = message.lower()
    return any(phrase.lower() in lower for phrase in BATCH_END_PHRASES)


def _load_results() -> list[dict[str, Any]]:
    """Load currently accumulated image results."""
    if not RESULTS_FILE.exists():
        return []
    data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    results = data.get("results", [])
    return results if isinstance(results, list) else []


def _save_results(results: list[dict[str, Any]]) -> None:
    """Persist accumulated image results."""
    payload = {"results": results, "saved_at": datetime.now().isoformat()}
    RESULTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_results() -> None:
    RESULTS_FILE.unlink(missing_ok=True)


def check_and_send_pending_closeout() -> dict[str, Any] | None:
    """Compatibility no-op.

    The current design is explicitly triggered by user text, not by a timer.
    Call ``close_batch_now()`` when ``is_batch_end(user_message)`` is true.
    """
    return None


def add_image_result(result: dict[str, Any]) -> None:
    """Add one per-image pipeline result to the current explicit batch."""
    with _state_lock:
        results = _load_results()
        results.append(result)
        _save_results(results)


def close_batch_now() -> dict[str, Any] | None:
    """Close the current explicit image batch and return its closeout dict."""
    with _state_lock:
        results = _load_results()
        if not results:
            return None

        from batch_report import build_batch_closeout, summarize_batch_results

        closeout = build_batch_closeout(summarize_batch_results(results))
        _clear_results()
        return closeout
