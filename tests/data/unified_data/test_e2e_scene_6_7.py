"""Phase 1C E2E scenes 6 and 7.

Scene inventory (per DESIGN-03-010 §3.2 / SPEC-03-010 §3):

* Scene 6 (E2E-601..604): index dual path (TA-CN internal hit +
  external fallback) for ``metadata.index_list`` and
  ``market_data.index_daily``. ``stock_sector_info`` is **out of
  scope** per Pascal's Path A decision (DESIGN §3.5.6 OQ-01).
* Scene 7 (E2E-701, E2E-702): coverage gate — ``coverage run`` +
  ``coverage report --fail-under=60`` exit 0.
"""

from __future__ import annotations

# Load the Phase 1C E2E fixtures module so the @pytest.fixture functions
# defined there are auto-discoverable by pytest for this file's tests.
# We can't add them to the package-level ``conftest.py`` because that's
# excluded from this task's permitted-files list (Design §3.9.4).
pytest_plugins = ["tests.data.unified_data.test_e2e_fixtures"]

import subprocess
import sys
from typing import Any

from skills.data.unified_data import (
    CacheManager,
    DataRouter,
    LocalMongoAdapter,
    ProviderRegistry,
    SecurityId,
)

from tests.data.unified_data.conftest import FakeProvider, FakeTA_CNAdapter

from .test_e2e_fixtures import INDEX_DAILY_CAP, INDEX_LIST_CAP, PROJECT_ROOT


# ---------------------------------------------------------------------------
# Scene 6: index dual path (internal hit + external fallback)
# ---------------------------------------------------------------------------


class TestE2EScene6_IndexDualPath:
    """Index capability has both internal-first (TA-CN) and external
    fallback paths.

    Covers ``metadata.index_list`` and ``market_data.index_daily`` only
    — ``stock_sector_info`` is **out of scope** for Phase 1C
    (Pascal Path A; see DESIGN-03-010 §3.5.6 OQ-01).
    """

    def test_index_list_internal(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_with_index: FakeTA_CNAdapter,
        e2e_tushare_index_list_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-601: TA-CN index_basic_info hit -> no external call."""
        e2e_registry.register(e2e_tushare_index_list_ok)
        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=e2e_ta_cn_with_index,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        result = router.query("metadata", "index_list", cn_maotai)

        assert result.provider == "ta_cn_internal"
        # Two entries in the canned index_basic_info collection.
        assert isinstance(result.data, list)
        assert len(result.data) >= 1
        # Business-field assertion (SPEC-03-010 §6.1.1): the first
        # entry's symbol + name must match the canned fixture so an
        # empty-list false positive is impossible.
        assert result.data[0].get("symbol") == "000300"
        assert result.data[0].get("name") == "沪深300"
        # External provider was never invoked.
        assert e2e_tushare_index_list_ok.call_log == []

    def test_index_list_external(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_miss: FakeTA_CNAdapter,
        e2e_tushare_index_list_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-602: TA-CN empty -> external index_list fallback."""
        e2e_registry.register(e2e_tushare_index_list_ok)
        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=e2e_ta_cn_miss,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        result = router.query("metadata", "index_list", cn_maotai)

        assert result.provider == "tushare"
        # Business-field assertion (SPEC-03-010 §6.1.1): non-empty list
        # with the canonical ``symbol`` + ``name`` fields.
        assert result.data is not None
        assert isinstance(result.data, list)
        assert len(result.data) >= 1
        assert result.data[0].get("symbol") == "000300"
        assert result.data[0].get("name") == "沪深300"
        # The external provider saw the canonical capability.
        assert len(e2e_tushare_index_list_ok.call_log) == 1
        assert e2e_tushare_index_list_ok.call_log[0][1] == INDEX_LIST_CAP

    def test_index_daily_internal(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_with_index: FakeTA_CNAdapter,
        e2e_tushare_index_daily_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-603: TA-CN index_daily_quotes hit -> no external call."""
        e2e_registry.register(e2e_tushare_index_daily_ok)
        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=e2e_ta_cn_with_index,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        result = router.query("market_data", "index_daily", cn_maotai)

        assert result.provider == "ta_cn_internal"
        assert isinstance(result.data, list)
        assert len(result.data) >= 1
        # Sector code and close price must be present and reasonable.
        first = result.data[0]
        assert first.get("sector_code") == "000300"
        assert first.get("close") > 0
        assert e2e_tushare_index_daily_ok.call_log == []

    def test_index_daily_external(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_miss: FakeTA_CNAdapter,
        e2e_tushare_index_daily_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-604: TA-CN empty -> external index_daily fallback."""
        e2e_registry.register(e2e_tushare_index_daily_ok)
        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=e2e_ta_cn_miss,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        result = router.query("market_data", "index_daily", cn_maotai)

        assert result.provider == "tushare"
        # Business-field assertion (SPEC-03-010 §6.1.1): non-empty list
        # with the canonical ``sector_code`` + ``close`` fields and a
        # positive close price.
        assert result.data is not None
        assert isinstance(result.data, list)
        assert len(result.data) >= 1
        assert result.data[0].get("sector_code") == "000300"
        assert result.data[0].get("close") > 0
        # The external provider saw the canonical capability.
        assert len(e2e_tushare_index_daily_ok.call_log) == 1
        assert e2e_tushare_index_daily_ok.call_log[0][1] == INDEX_DAILY_CAP


# ---------------------------------------------------------------------------
# Scene 7: coverage gate (hard requirement --fail-under=60)
# ---------------------------------------------------------------------------


class TestE2EScene7_CoverageGate:
    """E2E-701/702: ``coverage report --fail-under=60`` exits 0.

    Runs ``coverage`` as a subprocess against the existing
    unified_data test suite. The 60% line-coverage bar is a **hard
    gate** for Phase 1C Closeout (DESIGN-03-010 §7 / SPEC-03-010 §3
    E2E-702).
    """

    def test_coverage_report_runs(self) -> None:
        """E2E-701 + E2E-702: ``coverage run`` + ``coverage report
        --fail-under=60`` both exit 0.

        Both commands run against the existing
        ``tests/data/unified_data`` suite (no path filter on the run
        side — collection is fast and avoids touching production code).
        """
        # Step 1: coverage run on the whole unified_data suite. Exclude
        # ``test_coverage_report_runs`` itself to avoid recursion
        # (this test spawns pytest on the same directory, which would
        # re-enter this method and recurse forever).
        run_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                "-m",
                "pytest",
                "tests/data/unified_data",
                "-q",
                "-k",
                "not test_coverage_report_runs",
            ],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=120,
        )
        assert run_result.returncode == 0, (
            f"coverage run failed (rc={run_result.returncode})\n"
            f"STDOUT tail:\n{run_result.stdout[-2000:]}\n"
            f"STDERR tail:\n{run_result.stderr[-2000:]}"
        )

        # Step 2: coverage report with the hard --fail-under=60 gate.
        report_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "report",
                "--include=skills/data/unified_data/*",
                "--fail-under=60",
            ],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=30,
        )
        assert report_result.returncode == 0, (
            f"coverage --fail-under=60 failed (rc={report_result.returncode})\n"
            f"STDOUT:\n{report_result.stdout}\n"
            f"STDERR:\n{report_result.stderr}"
        )
        # ``TOTAL`` line surfaces the line-coverage percentage for log
        # transparency. (``coverage report`` writes ``TOTAL`` in caps.)
        assert "TOTAL" in report_result.stdout