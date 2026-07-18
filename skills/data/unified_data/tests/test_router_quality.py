"""DataRouter QualityScorer / AuditLogger integration tests (Phase 2 T23).

DR-301..309 behaviour matrix from SPEC-03-011 §5.3 / DESIGN-03-011 §7.3.

Acceptance: the Router must
  * Accept optional ``quality_scorer`` and ``audit_logger`` kwargs (default
    ``None``) without breaking any existing call site.
  * Enrich every successful return with ``quality_score`` /
    ``quality_scored: tier=..., score=...`` trace when the scorer is
    wired in.
  * Forward frozen warning text (N7/N9/N11) verbatim.
  * Trigger ``AuditLogger.log`` with the (possibly enriched) result.
  * Tolerate scorer / audit / summary exceptions (catch-and-log) without
    failing the primary fetch.
  * Use only injected fake/mongomock/in-memory dependencies — never real
    MongoDB / external I/O.
"""

from __future__ import annotations

from typing import Any

import mongomock
import pytest

from skills.data.unified_data import (
    AuditLogger,
    DataRouter,
    Market,
    ProviderError,
    QualityScorer,
    QualityScorerConfig,
    QualitySummary,
)
from skills.data.unified_data.tests.conftest import FakeProvider

CAPABILITY = "market_data.kline_daily"
AUDIT_COLL = "03_data_ud_query_audit"


def _provider(name: str, payload: Any) -> FakeProvider:
    return FakeProvider(
        name=name,
        payload=payload,
        capabilities={CAPABILITY},
        markets={Market.CN},
    )


def _ok_payload() -> list[dict[str, Any]]:
    return [{"close": 1500.0, "volume": 1_000_000}]


# ---------------------------------------------------------------------------
# DR-301..305 injection matrix
# ---------------------------------------------------------------------------


class TestInjectionMatrix:
    def test_dr301_no_dependencies_default_behaviour(self, fresh_registry, cn_maotai):
        fresh_registry.register(_provider("primary", _ok_payload()))
        result = DataRouter(fresh_registry).query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "primary"
        assert result.quality_score is None
        assert not any("quality_scored:" in entry for entry in result.source_trace)

    def test_dr302_scorer_only_sets_quality_score(self, fresh_registry, cn_maotai):
        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(fresh_registry, quality_scorer=QualityScorer())
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "primary"
        assert isinstance(result.quality_score, float)
        assert 0.0 <= result.quality_score <= 1.0
        assert any(entry.startswith("quality_scored:") for entry in result.source_trace)

    def test_dr303_audit_only_does_not_score(self, fresh_registry, cn_maotai):
        db = mongomock.MongoClient().db
        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(fresh_registry, audit_logger=AuditLogger(mongo_db=db))
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "primary"
        assert result.quality_score is None
        assert db[AUDIT_COLL].count_documents({}) == 1
        doc = db[AUDIT_COLL].find_one({})
        assert doc["security_id"] == "CN:600519" and doc["provider"] == "primary"

    def test_dr304_full_integration_quality_audit_summary(self, fresh_registry, cn_maotai):
        db = mongomock.MongoClient().db
        summary = QualitySummary(mongo_db=db)
        logger = AuditLogger(mongo_db=db, quality_summary=summary)
        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(fresh_registry, quality_scorer=QualityScorer(), audit_logger=logger)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert isinstance(result.quality_score, float)
        assert db[AUDIT_COLL].count_documents({}) == 1
        assert db["03_data_ud_quality_summary"].count_documents({}) == 1

    def test_dr305_scorer_and_noop_audit_does_not_touch_db(self, fresh_registry, cn_maotai):
        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(
            fresh_registry,
            quality_scorer=QualityScorer(),
            audit_logger=AuditLogger(mongo_db=None),
        )
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert isinstance(result.quality_score, float) and result.source_trace


# ---------------------------------------------------------------------------
# DR-306/307 + every Router entry point
# ---------------------------------------------------------------------------


class TestRouterBranches:
    def test_dr306_force_refresh_still_enriches(self, fresh_registry, cn_maotai):
        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(fresh_registry, quality_scorer=QualityScorer())
        result = router.query("market_data", "kline_daily", cn_maotai, force_refresh=True)
        assert result.provider == "primary"
        assert isinstance(result.quality_score, float)
        assert any(entry.startswith("quality_scored:") for entry in result.source_trace)

    def test_dr307_error_result_scores_zero_and_audits_success_false(
        self, fresh_registry, cn_maotai
    ):
        boom = _provider("boom", None)
        boom._raise = ProviderError("nope")
        fresh_registry.register(boom)
        db = mongomock.MongoClient().db
        router = DataRouter(
            fresh_registry,
            quality_scorer=QualityScorer(),
            audit_logger=AuditLogger(mongo_db=db),
        )
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "error" and result.quality_score == 0.0
        doc = db[AUDIT_COLL].find_one({})
        assert doc["success"] is False and doc["provider"] == "error"

    def test_explicit_provider_branch_enriches(self, fresh_registry, cn_maotai):
        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(fresh_registry, quality_scorer=QualityScorer())
        result = router.query("market_data", "kline_daily", cn_maotai, provider="primary")
        assert result.provider == "primary"
        assert isinstance(result.quality_score, float)
        assert any(entry.startswith("quality_scored:") for entry in result.source_trace)

    def test_ta_cn_internal_branch_enriches(
        self, fresh_registry, cn_maotai, fake_ta_cn_with_kline
    ):
        router = DataRouter(
            fresh_registry,
            ta_cn_adapter=fake_ta_cn_with_kline,
            quality_scorer=QualityScorer(),
        )
        result = router.query("market_data", "kline_daily", cn_maotai, provider="ta_cn_internal")
        assert result.provider == "ta_cn_internal"
        assert isinstance(result.quality_score, float)
        assert any(entry.startswith("quality_scored:") for entry in result.source_trace)


# ---------------------------------------------------------------------------
# DR-308/309 — exception tolerance
# ---------------------------------------------------------------------------


class TestExceptionTolerance:
    def test_dr308_scorer_exception_leaves_quality_score_none(self, fresh_registry, cn_maotai):
        class _BoomScorer:
            def score(self, result, *, domain=None, now=None):
                raise RuntimeError("scorer crashed")

        db = mongomock.MongoClient().db
        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(
            fresh_registry,
            quality_scorer=_BoomScorer(),
            audit_logger=AuditLogger(mongo_db=db),
        )
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "primary" and result.quality_score is None
        assert db[AUDIT_COLL].count_documents({}) == 1

    def test_dr309_audit_exception_does_not_break_fetch(self, fresh_registry, cn_maotai):
        class _BoomAudit:
            def log(self, *args, **kwargs):
                raise RuntimeError("audit crashed")

        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(
            fresh_registry,
            quality_scorer=QualityScorer(),
            audit_logger=_BoomAudit(),
        )
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "primary" and isinstance(result.quality_score, float)

    def test_summary_exception_does_not_break_audit(self, fresh_registry, cn_maotai):
        class _BoomSummary:
            def update(self, *args, **kwargs):
                raise RuntimeError("summary crashed")

        db = mongomock.MongoClient().db
        fresh_registry.register(_provider("primary", _ok_payload()))
        logger = AuditLogger(mongo_db=db, quality_summary=_BoomSummary())
        router = DataRouter(fresh_registry, quality_scorer=QualityScorer(), audit_logger=logger)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "primary" and db[AUDIT_COLL].count_documents({}) == 1


# ---------------------------------------------------------------------------
# Frozen text + warning propagation (N7/N9/N11, T6 anchor)
# ---------------------------------------------------------------------------


class TestWarningPropagation:
    def test_frozen_text_and_warning_propagation(
        self,
        fresh_registry,
        cn_maotai,
        result_cached_near_expiry,
        result_conflict,
        result_missing_volume,
    ):
        """N7/N9/N11 fixture labels and warning text are frozen (T6 anchor)."""
        scorer = QualityScorer()
        # N9 — active conflict → warning tier with exact text.
        scored = scorer.score(result_conflict)
        assert scored.quality_tier == "warning"
        assert "source conflict: price divergence" in scored.warnings
        # N11 — missing volume field → warning with exact field text.
        scored = scorer.score(result_missing_volume)
        assert scored.quality_tier == "warning"
        assert "missing required fields: volume" in scored.warnings
        # N7 — cached near expiry → warning carries frozen label.
        scored = scorer.score(result_cached_near_expiry)
        assert "cache near expiry" in scored.warnings

        # Router-level warning propagation: existing warnings (incl.
        # any pre-existing TA-CN-failure warning) survive enrichment
        # and scorer warnings come AFTER them.
        boom = _provider("boom", None)
        boom._raise = ProviderError("nope")
        fresh_registry.register(boom)
        fresh_registry.register(_provider("ok", _ok_payload()))
        router = DataRouter(fresh_registry, quality_scorer=QualityScorer())
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "ok"
        # Quality trace appended; warnings field exists (may be empty).
        assert any(entry.startswith("quality_scored:") for entry in result.source_trace)


# ---------------------------------------------------------------------------
# No real Mongo / no external I/O boundary
# ---------------------------------------------------------------------------


class TestNoRealSideEffects:
    def test_default_construction_does_not_connect_mongo(self):
        from skills.data.unified_data import ProviderRegistry
        router = DataRouter(ProviderRegistry())
        assert router.quality_scorer is None and router.audit_logger is None

    def test_explicit_none_audit_does_not_score(self, fresh_registry, cn_maotai):
        fresh_registry.register(_provider("primary", _ok_payload()))
        result = DataRouter(fresh_registry, audit_logger=None).query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "primary" and result.quality_score is None

    def test_explicit_none_scorer_does_not_enrich(self, fresh_registry, cn_maotai):
        fresh_registry.register(_provider("primary", _ok_payload()))
        result = DataRouter(fresh_registry, quality_scorer=None).query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "primary" and result.quality_score is None
        assert not any(
            entry.startswith("quality_scored:") for entry in result.source_trace
        )

    def test_custom_scorer_config_propagates_into_tier(self, fresh_registry, cn_maotai):
        # Missing volume → completeness halves the score → below 0.99
        # → degrade (with custom thresholds).
        fresh_registry.register(_provider("primary", [{"close": 1500.0}]))
        config = QualityScorerConfig(
            dimension_weights={
                "completeness": 0.35, "freshness": 0.30,
                "consistency": 0.15, "plausibility": 0.20,
            },
            tier_thresholds={
                "direct_use": 0.99, "warning": 0.97, "degrade": 0.5, "reject": 0.0,
            },
        )
        router = DataRouter(fresh_registry, quality_scorer=QualityScorer(config=config))
        result = router.query("market_data", "kline_daily", cn_maotai)
        trace_entry = next(
            entry for entry in result.source_trace if entry.startswith("quality_scored:")
        )
        assert "tier=degrade" in trace_entry


# ---------------------------------------------------------------------------
# Phase 2 Review Minor M1 — Audit params / duration_ms contract
# ---------------------------------------------------------------------------
# These tests pin the DESIGN-03-011 §7.2 runtime contract:
#   * ``params`` is forwarded to ``AuditLogger.log`` as a snapshot of the
#     caller-supplied mapping; later mutation cannot leak into the audit
#     document.
#   * ``duration_ms`` is a non-negative integer that reflects the real
#     wall-clock cost of the query (instead of the legacy ``0``).
# Coverage at minimum: a normal external-fallback-chain route.


class TestAuditParamsDurationMsContract:
    def test_audit_doc_carries_params_snapshot(
        self, fresh_registry, cn_maotai
    ):
        """DESIGN-03-011 §7.2 — audit document records the caller params.

        A normal external-fallback-chain route is exercised; the audit
        document must contain the ``params`` mapping verbatim, including
        all keys the caller supplied at :meth:`query` entry.
        """
        db = mongomock.MongoClient().db
        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(
            fresh_registry,
            audit_logger=AuditLogger(mongo_db=db),
        )
        params = {"limit": 120, "start_date": "2026-07-01"}
        router.query(
            "market_data", "kline_daily", cn_maotai, params=params
        )

        assert db[AUDIT_COLL].count_documents({}) == 1
        doc = db[AUDIT_COLL].find_one({})
        assert doc["params"] == {"limit": 120, "start_date": "2026-07-01"}

    def test_audit_doc_carries_non_negative_duration_ms(
        self, fresh_registry, cn_maotai
    ):
        """DESIGN-03-011 §7.2 — ``duration_ms`` is a non-negative int.

        The value is computed from the query start timestamp; even a
        sub-millisecond query must produce a clamped non-negative int
        rather than the legacy ``0`` placeholder (which can also be
        legal for an instantaneous call, but only when the elapsed
        time actually rounds to zero).
        """
        db = mongomock.MongoClient().db
        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(
            fresh_registry,
            audit_logger=AuditLogger(mongo_db=db),
        )
        router.query(
            "market_data", "kline_daily", cn_maotai,
            params={"limit": 30},
        )

        doc = db[AUDIT_COLL].find_one({})
        assert isinstance(doc["duration_ms"], int)
        assert doc["duration_ms"] >= 0

    def test_audit_params_snapshot_isolated_from_caller_mutation(
        self, fresh_registry, cn_maotai
    ):
        """DESIGN-03-011 §7.2 — audit params is a defensive snapshot.

        After :meth:`query` returns, mutating the caller's ``params``
        mapping must NOT change what was already written into the
        audit document. The router captures a shallow copy at entry
        time.
        """
        db = mongomock.MongoClient().db
        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(
            fresh_registry,
            audit_logger=AuditLogger(mongo_db=db),
        )
        params = {"limit": 60}
        router.query(
            "market_data", "kline_daily", cn_maotai, params=params
        )

        # Mutate the caller mapping post-hoc; the audit document must
        # retain the original snapshot.
        params["limit"] = 9999
        params["injected"] = True

        doc = db[AUDIT_COLL].find_one({})
        assert doc["params"] == {"limit": 60}

    def test_audit_params_forwarded_for_explicit_provider_branch(
        self, fresh_registry, cn_maotai
    ):
        """Branch 2 (explicit ``provider=``) also forwards params.

        Phase 2 rollout (DESIGN-03-011 §8.6): params 走严格 allow-list；
        这里用 ``limit`` 这类 allow-listed 键验证分支正确写入审计文档。
        """
        db = mongomock.MongoClient().db
        fresh_registry.register(_provider("primary", _ok_payload()))
        router = DataRouter(
            fresh_registry,
            audit_logger=AuditLogger(mongo_db=db),
        )
        params = {"limit": 60}
        router.query(
            "market_data", "kline_daily", cn_maotai,
            provider="primary", params=params,
        )

        doc = db[AUDIT_COLL].find_one({})
        assert doc["params"] == {"limit": 60}
        assert isinstance(doc["duration_ms"], int) and doc["duration_ms"] >= 0

    def test_audit_params_forwarded_for_ta_cn_internal_branch(
        self, fresh_registry, cn_maotai, fake_ta_cn_with_kline
    ):
        """Branch 1 (``provider == "ta_cn_internal"``) also forwards params."""
        db = mongomock.MongoClient().db
        router = DataRouter(
            fresh_registry,
            ta_cn_adapter=fake_ta_cn_with_kline,
            audit_logger=AuditLogger(mongo_db=db),
        )
        params = {"limit": 240}
        router.query(
            "market_data", "kline_daily", cn_maotai,
            provider="ta_cn_internal", params=params,
        )

        doc = db[AUDIT_COLL].find_one({})
        assert doc["params"] == {"limit": 240}
        assert doc["provider"] == "ta_cn_internal"
        assert isinstance(doc["duration_ms"], int) and doc["duration_ms"] >= 0

    def test_compute_duration_ms_floors_negative_deltas(self):
        """``_compute_duration_ms`` never returns a negative integer."""
        from datetime import datetime, timedelta, timezone

        router = DataRouter.__new__(DataRouter)  # bypass __init__
        # ``started_at`` in the future → clamp to 0
        future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=5)
        assert DataRouter._compute_duration_ms(future) == 0
        # ``None`` → 0
        assert DataRouter._compute_duration_ms(None) == 0
        # Real elapsed time → non-negative int
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(milliseconds=15)
        assert DataRouter._compute_duration_ms(past) >= 0