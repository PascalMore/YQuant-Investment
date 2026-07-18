"""Unit tests for smart_money_watcher.process_existing_files().

Covers the YQuant Smart Money watcher daemon (DESIGN-03-004): files that
were archived (but not yet processed) should be picked up on startup,
with the archive folder date being used as the system date passed to
the per-image processor. No real MongoDB / OCR / network.
"""
import asyncio
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import smart_money_watcher  # noqa: E402


def test_watcher_once_uses_file_date_for_existing_files(monkeypatch, tmp_path):
    image_dir = tmp_path / "2026-05-03" / "image"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "portfolio.jpg"
    image_path.write_bytes(b"fake image")
    captured = {}

    async def fake_process_image(self, path, date_str=None):
        captured["path"] = path
        captured["date_str"] = date_str
        return {
            "type": "image",
            "status": "success",
            "source": str(path),
            "rows": 1,
            "mongodb": {"position": 1},
        }

    monkeypatch.setattr(smart_money_watcher, "SOURCE_ROOT", tmp_path)
    monkeypatch.setattr(
        smart_money_watcher.PortfolioPipeline,
        "process_image",
        fake_process_image,
    )

    results = asyncio.run(
        smart_money_watcher.process_existing_files(set(), "2026-05-03")
    )

    assert len(results) == 1
    assert captured["path"] == image_path
    assert captured["date_str"] == "2026-05-03"
