"""OQ-11 production composition root (SPEC-03-014 V0.26 EOD-8.2).

Minimal pure-assembler. No provider / Mongo / cache / network /
refresh / file-write side effects. Default keeps the offline
path (``completed_session_policy=None``).

The module is the **unique** production composition root for the
production ``MarketSentimentService`` (DESIGN-03-014 V0.33
§OQ-11B.1 — candidate a; candidates b/c/d were ruled out by
T2 on disk facts):

* b) ``services/__init__.py`` extension — current export
  surface; mixing assembly in would pollute the import boundary
  and create implicit real-clock construction.
* c) ``client.py`` facade — ``UnifiedDataClient._get_sentiment_service()``
  is the library-level lazy assembler; SPEC §3.3 EOD-8.2
  explicitly disallows treating the facade as the production
  root, and the OQ-11 closure-only blocklist forbids touching
  it.
* d) ``scripts/unified_data/`` production CLI — no consumer
  process currently exists in the repo.

The composition seam is **opt-in** by design. Calling
:func:`build_production_sentiment_service()` with no arguments
returns a service with ``completed_session_policy=None`` —
identical to the legacy offline path. Passing ``clock=...``
explicitly assembles the production policy via
:class:`skills.infra.session_policy.AShareCompletedSessionPolicy`.
No caller-side default ever spawns a real clock.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from skills.infra.session_policy import (
    AShareCompletedSessionPolicy,
    Clock,
)
from skills.data.unified_data.services.sentiment_service import MarketSentimentService


def build_production_sentiment_service(
    clock: Clock | None = None,
    *,
    cutoff_grace: timedelta = timedelta(0),
) -> MarketSentimentService:
    """Build a ``MarketSentimentService`` for production use.

    - ``clock=None`` (default): returns a service with
      ``completed_session_policy=None`` — identical to the
      offline path. **No real policy is injected by default**
      (EOD-8.8). The legacy stub/defer path stays intact.
    - ``clock`` provided: builds
      :class:`AShareCompletedSessionPolicy` with that clock
      and injects it via the existing
      :class:`MarketSentimentService` constructor seam.
      ``SystemClock()`` is the intended production value but
      may be swapped for a fake in tests.

    Args:
        clock: Optional :class:`Clock` to feed into the
            production :class:`AShareCompletedSessionPolicy`.
            ``None`` (default) keeps the offline permissive
            path.
        cutoff_grace: Independent, configurable, auditable
            policy parameter forwarded to the policy (default
            ``timedelta(0)`` — close instant == completion).

    Returns:
        A new :class:`MarketSentimentService` with
        ``completed_session_policy`` either ``None`` (default)
        or a configured :class:`AShareCompletedSessionPolicy`.

    Side effects:
        None. The function is a pure assembler — no provider
        fetch, no writer upsert, no cache put, no Mongo /
        network / file write. The :class:`AShareCompletedSessionPolicy`
        constructor itself performs a clock probe (fail-fast
        on naive clock) but no side-channel I/O.
    """
    policy: Optional[AShareCompletedSessionPolicy] = None
    if clock is not None:
        policy = AShareCompletedSessionPolicy(
            clock=clock, cutoff_grace=cutoff_grace
        )
    return MarketSentimentService(completed_session_policy=policy)
