"""End-to-end test entry stub for the Unified Data Layer (Phase 1C).

The original 993-line test blob was split per
``DESIGN-03-010 §3.9`` into five ``<= 300``-line modules:

* :mod:`tests.data.unified_data.test_e2e_fixtures` — shared constants
  and ``@pytest.fixture`` definitions for the E2E suite.
* :mod:`tests.data.unified_data.test_e2e_scene_1_2_3` — Scene 1
  (all-miss + external success + write + subsequent hit), Scene 2
  (cache hit -> zero external calls), Scene 3 (provider A -> B
  fallback with **exact** source_trace equality).
* :mod:`tests.data.unified_data.test_e2e_scene_4` — Scene 4
  (all external providers fail -> ``DataResult.error``).
* :mod:`tests.data.unified_data.test_e2e_scene_5` — Scene 5
  (``force_refresh=True`` bypasses Step 1/2/3, writes back).
* :mod:`tests.data.unified_data.test_e2e_scene_6_7` — Scene 6
  (index dual path: internal hit + external fallback for
  ``metadata.index_list`` and ``market_data.index_daily``) and
  Scene 7 (coverage gate ``--fail-under=60``).

This file is kept as the **module entry point** so that
``pytest tests/data/unified_data/test_e2e_full_chain.py`` continues
to discover the full Phase 1C test inventory. ``grep -c "class
TestE2E"`` against the per-scene modules still returns 7
TestClass definitions; this file deliberately owns none.

Test inventory
--------------
7 TestClass x 16 test methods, per DESIGN-03-010 §3.2 / SPEC-03-010 §3.

Implementation discipline
-------------------------
* No production code changes — this file is **read-only** with
  respect to ``router.py`` / ``cache_manager.py`` /
  ``local_mongo_adapter.py`` / ``conftest.py``.
* No real MongoDB or external API calls.
* No new pip dependencies; uses ``mongomock`` (already in dev deps)
  and ``coverage`` (already installed in ``.venv``).
* Each TestClass in the per-scene modules is independently runnable
  and uses isolated :func:`pytest.fixture` state from
  ``test_e2e_fixtures``.
"""

from __future__ import annotations

# Load the Phase 1C E2E fixtures so the entry stub can resolve fixture
# names when invoked directly via ``pytest test_e2e_full_chain.py``.
# pytest only auto-loads ``pytest_plugins`` from the *collected* test
# file — re-exporting the per-scene modules below does not transfer
# their own ``pytest_plugins`` declaration to this entry file. Without
# this line, ``pytest test_e2e_full_chain.py::TestE2ESceneN`` would
# fail with ``fixture 'e2e_db' not found`` even though every TestClass
# is imported here.
pytest_plugins = ["tests.data.unified_data.test_e2e_fixtures"]

# Re-export the per-scene modules so ``pytest tests/data/unified_data
# test_e2e_full_chain.py`` still discovers every TestClass. ``import *
# `` is avoided because we explicitly want to expose the test classes
# while keeping the module docstring as the user-facing reference.
from .test_e2e_scene_1_2_3 import (  # noqa: F401
    TestE2EScene1_AllMissExternalSuccess,
    TestE2EScene2_CacheHit,
    TestE2EScene3_ProviderFallback,
)
from .test_e2e_scene_4 import TestE2EScene4_AllFail  # noqa: F401
from .test_e2e_scene_5 import TestE2EScene5_ForceRefresh  # noqa: F401
from .test_e2e_scene_6_7 import (  # noqa: F401
    TestE2EScene6_IndexDualPath,
    TestE2EScene7_CoverageGate,
)

# Phase 1C E2E fixtures are also re-exported so direct
# ``pytest tests/data/unified_data/test_e2e_full_chain.py`` collection
# can resolve fixture names without the per-scene modules' own
# ``pytest_plugins`` declaration being the only entry point.
from .test_e2e_fixtures import (  # noqa: F401
    KLINE_CAP,
    INDEX_LIST_CAP,
    INDEX_DAILY_CAP,
    PROJECT_ROOT,
)