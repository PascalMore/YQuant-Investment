"""Freshness policy for unified_data (Phase 1B-A).

:class:`FreshnessPolicy` is a tiny pure-function helper used by the
:class:`DataRouter` and downstream code to derive a
:class:`FreshnessLabel` from the time elapsed since a payload was
fetched. It performs **no I/O** — no MongoDB, no HTTP, no clock
side-effects beyond :func:`datetime.now` for the age calculation.

Three public surfaces:

* :attr:`DEFAULT_TTLS` — class-level default TTL table (seconds).
* :meth:`get_ttl` — returns the TTL for a domain (default ``3600``).
* :meth:`label` — computes the freshness label given the fetch
  timestamp, the data date, the domain and a ``from_cache`` flag.

Phase 1B-A constraints (SPEC-03-008 §0):

* ``from_cache`` is **always** ``False`` because the CacheManager is
  scheduled for Phase 1B-B. ``cached`` / ``stale`` labels are still
  produced when ``from_cache=True`` is passed in (the logic is in
  place); they just never fire in normal 1B-A query paths.
* The supported output set is ``{"realtime", "delayed", "cached",
  "stale", "empty"}``; 1B-A only emits ``realtime`` / ``delayed`` /
  ``empty`` in practice.

Design references
-----------------
* SPEC-03-008 §3.5 / §4.6
* DESIGN-03-008 §3.3.8
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from .models import FreshnessLabel


class FreshnessPolicy:
    """Pure-function freshness policy.

    Args:
        ttl_overrides: Optional per-domain TTL overrides (seconds).
            Merged on top of :attr:`DEFAULT_TTLS` so callers can
            customise without touching the module-level defaults.
    """

    DEFAULT_TTLS: dict[str, int] = {
        "market_data": 21600,    # 6 hours
        "financial": 86400,      # 24 hours
        "valuation": 43200,      # 12 hours
        "calendar": 604800,      # 7 days
        "metadata": 604800,      # 7 days
        "news": 3600,            # 1 hour
        # Phase 3 P3-A: sector snapshot TTL = 21600s (6h) — sector
        # snapshot refresh is acceptable on the same day once a fresh
        # close is observed. DESIGN-03-014 §4.4 l.649 reconciliation
        # for the P3-A sector domain. P3-B (flow=43200) and P3-C
        # (sentiment=3600) land in their own sub-stage tasks.
        "sector": 21600,
        # Phase 3 P3-B (T3-B): market sentiment snapshot TTL = 3600s
        # (1h). Sentiment data is highly time-sensitive — a stale
        # "market temperature" reading loses relevance within an
        # hour, so the TTL is intentionally tight. Matches V0.5 §4.4
        # l.650 alignment with the sector pattern (single-line
        # addition, same shape as P3-A sector).
        "market_sentiment": 3600,
        # Phase 3 P3-B (T3-P3B): capital-flow TTL = 43200s (12h).
        # Per V0.5 §4.4 l.650 reconciliation, capital-flow data is
        # valid for half a day — once a fresh close is observed the
        # previous reading can be refreshed. Matches the same shape
        # as the P3-A sector entry: explicit TTL, single-line
        # addition. Per the V0.5 §2.1 "explicit TTL" rule this
        # value is hard-coded here rather than relying on the
        # _DEFAULT_TTL fallback so consumers can read the intent
        # directly off the table.
        "flow": 43200,
        # Phase 3 P3-C (T3-P3C): limit-up pool TTL = 3600s (1h).
        # Per-stock limit-up data (封单金额/封成比/连板) is highly
        # time-sensitive — stale readings lose relevance within an
        # hour. Matches the market_sentiment TTL pattern.
        "sentiment_limit_up_pool": 3600,
    }

    # Boundaries for the realtime / delayed split (seconds since fetch).
    _REALTIME_THRESHOLD = 60
    _DELAYED_THRESHOLD = 900  # 15 minutes

    _DEFAULT_TTL = 3600

    def __init__(self, ttl_overrides: Mapping[str, int] | None = None) -> None:
        # Defensive copy — never mutate the class-level dict.
        self._ttls: dict[str, int] = dict(self.DEFAULT_TTLS)
        if ttl_overrides:
            self._ttls.update(ttl_overrides)

    # ------------------------------------------------------------------
    # TTL lookup
    # ------------------------------------------------------------------

    def get_ttl(self, domain: str) -> int:
        """Return the TTL (seconds) for ``domain``.

        Unknown domains fall back to :data:`_DEFAULT_TTL` (3600).
        """
        return self._ttls.get(domain, self._DEFAULT_TTL)

    # ------------------------------------------------------------------
    # Label computation
    # ------------------------------------------------------------------

    def label(
        self,
        fetched_at: datetime,
        data_date: str | None,
        domain: str,
        from_cache: bool,
    ) -> FreshnessLabel:
        """Compute the freshness label for the supplied inputs.

        Args:
            fetched_at: When the payload was fetched (UTC-naive is
                expected — see SPEC-03-008 §4.6).
            data_date: ``"YYYY-MM-DD"`` string describing the data
                itself, or ``None`` when the payload is empty. An
                empty data signal short-circuits to ``"empty"``.
            domain: Domain name (``"market_data"``, ...). Used for TTL
                lookup when ``from_cache`` is ``True``.
            from_cache: ``True`` when the payload came from the cache
                layer (Phase 1B-B). Phase 1B-A always passes
                ``False``.

        Returns:
            A :data:`FreshnessLabel` value:

            * ``"empty"`` — ``data_date is None`` (caller signals an
              empty payload).
            * ``"cached"`` — ``from_cache=True`` and within TTL.
            * ``"stale"`` — ``from_cache=True`` and past TTL.
            * ``"realtime"`` — fetch within 60s and not cached.
            * ``"delayed"`` — fetch older than 60s and not cached
              (covers the >15 min branch too).

        Notes:
            No I/O is performed. The function reads
            ``datetime.now(timezone.utc)`` only to compute the
            age of ``fetched_at``.
        """
        if data_date is None:
            return "empty"

        # Compute age from "now". Use UTC for consistency and strip
        # tzinfo so we compare naive datetimes (matches DataRouter).
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        age = (now - fetched_at).total_seconds()

        if from_cache:
            ttl = self.get_ttl(domain)
            if age > ttl:
                return "stale"
            return "cached"

        if age < self._REALTIME_THRESHOLD:
            return "realtime"
        if age < self._DELAYED_THRESHOLD:
            return "delayed"
        return "delayed"


__all__ = ["FreshnessPolicy"]