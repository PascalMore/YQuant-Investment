"""Unit tests for image_batch_state.py.

Covers the YQuant in-session batch closeout state machine
(DESIGN-03-004): results accumulate across multiple image uploads and
are only closed into a closeout message on an explicit batch-end signal
from the user.
"""
import asyncio  # noqa: F401  # kept for parity with sibling test files
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import image_batch_state  # noqa: E402


def test_image_batch_state_closes_only_on_explicit_batch_end(monkeypatch, tmp_path):
    state_file = tmp_path / "image_batch_results.json"
    monkeypatch.setattr(image_batch_state, "RESULTS_FILE", state_file)

    assert image_batch_state.is_batch_end("图片批次已上传")
    assert image_batch_state.is_batch_end("就这些")
    assert image_batch_state.close_batch_now() is None

    image_batch_state.add_image_result(
        {"status": "success", "source": "a.jpg", "rows": 2, "mongodb": {"position": 2}}
    )
    image_batch_state.add_image_result(
        {"status": "success", "source": "b.jpg", "rows": 3, "mongodb": {"position": 3}}
    )

    closeout = image_batch_state.close_batch_now()

    assert closeout is not None
    assert closeout["status"] == "closed_clean"
    assert closeout["totals"]["files"] == 2
    assert closeout["mongodb_counts"] == {"position": 5}
    assert not state_file.exists()
    assert image_batch_state.close_batch_now() is None
