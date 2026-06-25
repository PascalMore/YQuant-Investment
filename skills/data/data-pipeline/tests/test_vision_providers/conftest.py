"""
Shared pytest fixtures for the OCR provider fallback test suite
(Smart Money / RFC-03-006 / SPEC-03-006).

This file lives under tests/test_vision_providers/conftest.py so it is
auto-loaded by pytest for every test in this directory. The fixtures it
provides:

  * put the data-pipeline ``scripts/`` directory on ``sys.path`` (the
    package layout assumes this for `from providers import ...` imports
    used by both the providers and the test code).
  * build a tiny in-memory test image (PNG) so describe() has a real file
    to point at without us having to ship a binary fixture.
  * provide a router_config_override (RouterConfig) and a mock-factory
    registry reset helper, so each test can wire its own providers in.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make ``import providers`` work for the test process. The data-pipeline
# entry-points (run_unified_image_pipeline.py etc.) do the same trick at
# startup; we replicate it here so the test files can import providers
# directly without per-test boilerplate.
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def test_image_path(tmp_path: Path) -> Path:
    """Return a path to a tiny but real PNG file. Used as the input to
    describe() so we never hit mmx or any real upstream OCR service."""
    # A 4x4 transparent PNG (smallest valid PNG that PIL/Pillow writes).
    # Pre-encoded base64 of a 1x1 transparent PNG.
    import base64
    png_bytes = base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9ZyJ8g0AAAAASUVORK5CYII="
    )
    p = tmp_path / "fixture.png"
    p.write_bytes(png_bytes)
    return p


@pytest.fixture
def reset_provider_registry():
    """Snapshot the global registry before each test and restore it after.

    Tests that swap in mock providers (e.g. with the same name as a
    built-in) call this fixture to ensure no leakage between tests.
    """
    from providers import registry

    original = dict(registry._REGISTRY)
    try:
        yield registry
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(original)
