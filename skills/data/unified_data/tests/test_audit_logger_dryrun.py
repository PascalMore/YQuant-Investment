"""T3-A P0.1 AuditLogger dry-run tests (decision B.b).

These tests pin the P0.1 (decision B.b) contract added on top of the
T3-A P3-A sector.snapshot scaffold:

* ``P3PersistenceWriter.upsert(...)`` invokes ``audit_logger.attempt(...)``
  with allow-listed fields (fail-open: a logger crash never blocks the
  refresh path).
* ``P3PersistenceWriter`` ships with a built-in no-op logger so the
  default behaviour is side-effect free.
* Audit kwargs are filtered through a strict allow-list — non-allow-listed
  keys are silently dropped even if the caller tries to sneak them in.

Acceptance matrix (kanban task body, decision B.b):

| # | test name                                       | file                              |
|---|-------------------------------------------------|-----------------------------------|
| ⑤ | test_audit_logger_attempt_called_on_refresh     | test_audit_logger_dryrun.py       |
| ⑥ | test_audit_logger_failure_does_not_block_refresh | test_audit_logger_dryrun.py      |
| ⑦ | test_audit_logger_allowlist_enforced            | test_audit_logger_dryrun.py       |

Scope (offline, mirroring the rest of the Phase 3 T3-A series):

* No real MongoDB / Provider API / cron / AuditLogger persistence — only
  the writer-side hook is exercised; the audit sink itself is a
  capturing mock or :class:`_NoopAuditLogger`.
* No RFC/SPEC/DESIGN edits (V0.5 final).
"""

from __future__ import annotations

import io
import logging
from typing import Any

import mongomock
import pytest

from skills.data.unified_data.adapters.p3_persistence_writer import (
    P3PersistenceWriter,
    UpsertOutcome,
)


SECTOR_COLLECTION = "03_data_ud_market_sector_snapshot"
SECTOR_UNIQUE_KEY = frozenset({"market", "sector_code", "snapshot_date"})

AUDIT_ALLOWLIST = frozenset({
    "security_id",
    "domain",
    "operation",
    "outcome",
    "latency_ms",
    "row_count",
})


class CapturingAuditLogger:
    """Records every ``attempt(**kwargs)`` call for inspection."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def attempt(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)

    def record(self, **kwargs: Any) -> None:  # pragma: no cover — unused here
        # Reserved by the contract but not exercised by the writer.
        self.calls.append({"record": kwargs})


class RaisingAuditLogger:
    """``attempt()`` always raises — proves fail-open semantics."""

    def __init__(self, exc: BaseException | None = None) -> None:
        self.exc = exc or RuntimeError("simulated audit sink failure")
        self.calls = 0

    def attempt(self, **kwargs: Any) -> None:
        self.calls += 1
        raise self.exc

    def record(self, **kwargs: Any) -> None:  # pragma: no cover — unused here
        self.calls += 1
        raise self.exc


def _make_writer(audit_logger: Any = None) -> P3PersistenceWriter:
    """Build a writer backed by a fresh in-memory mongomock database."""
    db = mongomock.MongoClient().get_database("tradingagents")
    return P3PersistenceWriter(db, audit_logger=audit_logger)


def _sample_records() -> list[dict]:
    return [
        {
            "market": "CN",
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "pct_chg": 2.35,
            "rank": 5,
        },
        {
            "market": "CN",
            "sector_code": "BK0500",
            "sector_name": "证券",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "pct_chg": -0.50,
            "rank": 88,
        },
    ]


# ---------------------------------------------------------------------------
# Test ⑤ — AuditLogger dry-run on refresh path
# ---------------------------------------------------------------------------


class TestAuditLoggerAttemptCalledOnRefresh:
    """``upsert()`` invokes the injected audit logger's ``attempt()`` method."""

    def test_noop_logger_is_default_and_does_not_raise(self):
        """No logger injected → built-in no-op logger, no side effects."""
        writer = P3PersistenceWriter(mongomock.MongoClient().get_database("t"))
        # ``audit_logger`` property always returns a real object
        # (never ``None``) — the no-op sentinel in this case.
        assert writer.audit_logger is not None
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert outcome.persisted == 2
        assert outcome.failed == 0

    def test_capturing_logger_receives_attempt_after_successful_upsert(self):
        """An injected capturing logger sees exactly one ``attempt()`` call
        with allow-listed fields and ``outcome='ok'`` after a clean
        upsert."""
        cap = CapturingAuditLogger()
        writer = _make_writer(audit_logger=cap)
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert outcome.persisted == 2
        assert outcome.failed == 0
        # Exactly one ``attempt()`` call after the upsert.
        assert len(cap.calls) == 1
        call = cap.calls[0]
        # All keys must lie within the allow-list — no leakage of
        # query payloads / secrets / non-deserialisable objects.
        assert set(call.keys()).issubset(AUDIT_ALLOWLIST), (
            f"non-allow-listed keys leaked: {set(call.keys()) - AUDIT_ALLOWLIST}"
        )
        assert call["operation"] == "upsert"
        assert call["domain"] == SECTOR_COLLECTION
        assert call["outcome"] == "ok"
        assert call["row_count"] == 2
        assert isinstance(call["latency_ms"], int)
        assert call["latency_ms"] >= 0

    def test_partial_failure_emits_outcome_partial_failure(self):
        """A per-record failure flips the audit ``outcome`` to
        ``'partial_failure'`` while keeping the upsert return value
        populated."""
        cap = CapturingAuditLogger()
        writer = _make_writer(audit_logger=cap)
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=[
                # OK
                {
                    "market": "CN",
                    "sector_code": "BK0001",
                    "snapshot_date": "2026-07-21",
                    "pct_chg": 1.0,
                },
                # Missing ``sector_code`` → per-record capture.
                {
                    "market": "CN",
                    "snapshot_date": "2026-07-21",
                    "pct_chg": 1.5,
                },
            ],
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert outcome.persisted == 1
        assert outcome.failed == 1
        assert len(cap.calls) == 1
        assert cap.calls[0]["outcome"] == "partial_failure"
        assert cap.calls[0]["row_count"] == 2

    def test_empty_records_skips_audit_emit(self):
        """Empty ``records`` is a caller-side no-op and must NOT fire
        ``attempt()`` (no refresh activity to record)."""
        cap = CapturingAuditLogger()
        writer = _make_writer(audit_logger=cap)
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=[],
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert outcome.persisted == 0
        assert outcome.failed == 0
        assert cap.calls == []  # no audit call


# ---------------------------------------------------------------------------
# Test ⑥ — audit logger failures must not block the refresh path
# ---------------------------------------------------------------------------


class TestAuditLoggerFailureDoesNotBlockRefresh:
    """A misbehaving audit logger must NOT break the main upsert flow."""

    def test_raising_logger_does_not_block_upsert(self, capsys):
        """A logger that raises ``RuntimeError`` inside ``attempt()``
        leaves the upsert return value intact; a stderr warning is
        emitted but the caller still gets a normal :class:`UpsertOutcome`."""
        raising = RaisingAuditLogger()
        writer = _make_writer(audit_logger=raising)
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        # Main flow completes normally.
        assert outcome.persisted == 2
        assert outcome.failed == 0
        # The logger was actually invoked (we counted the call).
        assert raising.calls == 1
        # A warning line is printed to stderr so operators can see
        # the mismatch without losing the upsert.
        captured = capsys.readouterr()
        assert "audit_logger.attempt() raised RuntimeError" in captured.err

    def test_raising_logger_does_not_block_partial_failure(self, capsys):
        """Even with a partial per-record failure + a raising audit
        logger, the main flow returns a fully populated
        :class:`UpsertOutcome`."""
        raising = RaisingAuditLogger()
        writer = _make_writer(audit_logger=raising)
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=[
                {"market": "CN", "sector_code": "BK0001",
                 "snapshot_date": "2026-07-21", "pct_chg": 1.0},
                # Missing 'sector_code' triggers ValueError, captured.
                {"market": "CN", "snapshot_date": "2026-07-21", "pct_chg": 1.5},
            ],
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert outcome.persisted == 1
        assert outcome.failed == 1
        assert raising.calls == 1  # fail-open: logger was attempted

    def test_logger_without_attempt_method_logs_and_continues(self, capsys):
        """A logger that does NOT implement ``attempt()`` (or ``record()``)
        is tolerated: a one-line stderr message is emitted and the
        upsert still completes."""

        class IncompleteLogger:
            pass

        writer = _make_writer(audit_logger=IncompleteLogger())
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert outcome.persisted == 2
        assert outcome.failed == 0
        captured = capsys.readouterr()
        assert "missing 'attempt'" in captured.err

    def test_raising_logger_returns_through_normal_audit_logger_property(self):
        """The ``audit_logger`` property surfaces whatever was injected
        (including a raising one) so the router-side exception handler
        can call it — fail-open still applies."""
        raising = RaisingAuditLogger()
        writer = _make_writer(audit_logger=raising)
        assert writer.audit_logger is raising
        # Calling ``attempt`` through the property directly also fails
        # open at the user level — but the writer's own internal
        # ``_safe_audit_call`` wrapper catches the exception.
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert outcome.persisted == 2


# ---------------------------------------------------------------------------
# Test ⑦ — audit attempt fields are strictly allow-listed
# ---------------------------------------------------------------------------


class TestAuditLoggerAllowlistEnforced:
    """Audit ``attempt()`` kwargs are filtered through a strict allow-list."""

    def test_attempt_kwargs_are_subset_of_allowlist(self):
        """The captured call's keys must all lie inside the allow-list."""
        cap = CapturingAuditLogger()
        writer = _make_writer(audit_logger=cap)
        writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert len(cap.calls) == 1
        keys = set(cap.calls[0].keys())
        # Must be a non-empty subset of the allow-list.
        assert keys.issubset(AUDIT_ALLOWLIST)
        assert keys, "expected at least one allow-listed key in attempt() call"

    def test_attempt_call_does_not_leak_records_or_payload(self):
        """The writer never forwards raw records / query payloads /
        secret-looking strings into the audit call."""
        cap = CapturingAuditLogger()
        writer = _make_writer(audit_logger=cap)
        # These records contain raw payloads that must NOT be forwarded.
        writer.upsert(
            collection=SECTOR_COLLECTION,
            records=[
                {
                    "market": "CN",
                    "sector_code": "BK0489",
                    "snapshot_date": "2026-07-21",
                    # Even with attacker-controlled values the audit
                    # contract only carries the allow-listed summary.
                    "raw_payload": {"secret_key": "should_not_appear"},
                    "token": "bearer abcdef",
                }
            ],
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert len(cap.calls) == 1
        forbidden_keys = {
            "params",
            "payload",
            "raw_payload",
            "records",
            "params_summary",
            "token",
            "secret_key",
        }
        leaked = forbidden_keys & set(cap.calls[0].keys())
        assert not leaked, f"audit call leaked keys: {leaked}"
        # The ``row_count`` carries the count, not the records themselves.
        assert cap.calls[0]["row_count"] == 1

    def test_attempt_call_exposes_expected_allow_listed_fields(self):
        """Pin the exact set of allow-listed fields the writer emits on a
        happy path. ``security_id`` is not present because the writer
        operates at collection level — domain + operation + outcome +
        latency_ms + row_count are the five the writer actually carries."""
        cap = CapturingAuditLogger()
        writer = _make_writer(audit_logger=cap)
        writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert len(cap.calls) == 1
        expected_subset = {
            "operation",
            "domain",
            "outcome",
            "latency_ms",
            "row_count",
        }
        assert set(cap.calls[0].keys()) == expected_subset
        assert cap.calls[0]["operation"] == "upsert"
        assert cap.calls[0]["domain"] == SECTOR_COLLECTION
        assert cap.calls[0]["outcome"] == "ok"
        assert cap.calls[0]["row_count"] == 2

    def test_noop_logger_silently_accepts_arbitrary_kwargs(self):
        """The no-op logger's ``attempt()`` accepts any kwargs without
        raising — the writer uses this to forward allow-listed fields
        without per-call reflection."""
        from skills.data.unified_data.adapters.p3_persistence_writer import (
            _NoopAuditLogger,
        )

        noop = _NoopAuditLogger()
        # Empty kwargs.
        assert noop.attempt() is None
        # Allow-listed kwargs.
        assert noop.attempt(domain="x", operation="upsert", outcome="ok") is None
        # Even non-allow-listed kwargs are silently dropped by the
        # writer-side allow-list filter, so the no-op logger must
        # accept them too (defensive).
        assert noop.attempt(
            domain="x",
            operation="upsert",
            outcome="ok",
            secret="ignored",
            payload=["also", "ignored"],
        ) is None
