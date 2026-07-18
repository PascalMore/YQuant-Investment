"""Unit tests for ``FreshnessPolicy`` (DESIGN-03-008 §4.2 — FP-001..FP-008).

The policy is a pure-function helper used by the ``DataRouter``. There is
no I/O, no MongoDB connection, no logging — everything can be exercised
deterministically with ``Freezegun``-style ``fetched_at`` values.

The eight tests below mirror the matrices laid out in DESIGN-03-008
§4.2 (FreshnessPolicy row). They cover both ``get_ttl`` and ``label``.
``label`` checks that use ``from_cache=True`` are also included even
though they never fire in 1B-A — the logic must already be correct so
Phase 1B-B can wire it up cleanly.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from skills.data.unified_data.freshness import FreshnessPolicy


# ---------------------------------------------------------------------------
# TTL lookup
# ---------------------------------------------------------------------------


class TestGetTTL:
    def test_get_ttl_known(self):
        """FP-101: a known domain returns its explicit TTL (market_data=6h)."""
        assert FreshnessPolicy().get_ttl("market_data") == 21600

    def test_get_ttl_unknown(self):
        """FP-101: unknown domains fall back to ``_DEFAULT_TTL`` (3600s)."""
        assert FreshnessPolicy().get_ttl("unknown") == 3600


# ---------------------------------------------------------------------------
# Label: from_cache = False branches
# ---------------------------------------------------------------------------


class TestLabelFreshFetch:
    """``from_cache=False`` branches — the only path 1B-A actually emits."""

    def _now(self) -> datetime:
        return datetime(2026, 7, 13, 12, 0, 0)

    def test_label_realtime(self):
        """FP-102: fetch within the ``_REALTIME_THRESHOLD`` window ⇒ realtime."""
        fp = FreshnessPolicy()
        ts = datetime.now() - timedelta(seconds=30)
        assert fp.label(ts, "2026-07-13", "market_data", False) == "realtime"

    def test_label_delayed(self):
        """FP-103: fetch between 60s and 15min ⇒ delayed."""
        # ``FreshnessPolicy`` compares against UTC-naive ``now()``;
        # mirror that here so a 5-minute-old fetch is observed as
        # such regardless of the host timezone.
        from datetime import timezone

        fp = FreshnessPolicy()
        ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
        assert fp.label(ts, "2026-07-13", "market_data", False) == "delayed"

    def test_label_empty(self):
        """FP-106: ``data_date is None`` short-circuits to ``empty``."""
        fp = FreshnessPolicy()
        ts = datetime.now()
        assert fp.label(ts, None, "market_data", False) == "empty"


# ---------------------------------------------------------------------------
# Label: from_cache = True branches
# ---------------------------------------------------------------------------


class TestLabelCached:
    def test_label_cached(self):
        """FP-104: cache hit within TTL ⇒ cached."""
        fp = FreshnessPolicy()
        # 30 seconds before "now", from_cache=True; market_data TTL 21600s.
        ts = datetime.now() - timedelta(seconds=30)
        assert fp.label(ts, "2026-07-13", "market_data", True) == "cached"

    def test_label_stale(self):
        """FP-105: cache hit past TTL ⇒ stale."""
        fp = FreshnessPolicy()
        # 1 day before "now" — past the 6-hour market_data TTL.
        ts = datetime.now() - timedelta(days=1)
        assert fp.label(ts, "2026-07-12", "market_data", True) == "stale"


# ---------------------------------------------------------------------------
# TTL override
# ---------------------------------------------------------------------------


class TestTTLOverride:
    def test_ttl_override(self):
        """FP-107: per-domain overrides win over the class-default table."""
        fp = FreshnessPolicy({"market_data": 100})
        assert fp.get_ttl("market_data") == 100
        # Other domains keep their default behaviour.
        assert fp.get_ttl("news") == 3600

    @pytest.mark.parametrize(
        "domain, expected",
        [
            ("market_data", 21600),
            ("financial", 86400),
            ("valuation", 43200),
            ("calendar", 604800),
            ("metadata", 604800),
            ("news", 3600),
        ],
    )
    def test_default_ttls_constant(self, domain, expected):
        """``DEFAULT_TTLS`` exposes the canonical table from the docs."""
        assert FreshnessPolicy.DEFAULT_TTLS[domain] == expected
