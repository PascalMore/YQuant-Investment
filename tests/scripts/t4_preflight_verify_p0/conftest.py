"""Path setup for the independent P0 verify suite.

We mirror the bootstrap the implementation team's conftest uses:
append the repo root to ``scripts.__path__`` so
``scripts.t4_preflight.*`` resolves.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts  # noqa: E402

scripts.__path__.append(str(_REPO_ROOT / "scripts"))
