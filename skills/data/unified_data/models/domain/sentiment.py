"""Market-level sentiment snapshot domain object (Phase 3 P3-B / T3-B).

:class:`MarketSentimentSnapshot` is the canonical shape for the
``sentiment.market_snapshot`` capability (DESIGN-03-014 §3.3, abridged
to the T3-B offline scope). It is intentionally minimal — only the
fields the offline T3-B implementation needs to round-trip through
:mod:`mongomock` and the persistence writer's unique-key filter.

Scope (T3-B kanban task body):

* Required: ``market``, ``sentiment_type``, ``market_date``, ``score``,
  ``sample_size``, ``source``.
* Optional (defaulted): all other fields.
* No ``raw_payload`` (kept off the wire to avoid leaking provider
  internals).
* No ``snapshot_time`` granularity — V0.5 §3.3 supports it but the
  T3-B scope uses a single ``(market, sentiment_type, market_date)``
  triple.  ``sentiment_type`` keeps the uniqueness key expressive
  enough to coexist with future sub-aggregates (``market_sentiment``,
  ``breadth``, ``limit_up_temperature``, ...).

The dataclass is ``frozen=True, slots=True`` for immutability — matches
the canonical-object convention used by :class:`SecurityId` /
:class:`Capability` and avoids accidental mutation when records are
copied into service-layer return payloads.

``from_dict`` is deliberately permissive: every field defaults, no
``KeyError`` is raised on missing keys, and types are not enforced —
the canonical source of truth remains the persistence writer's
record schema, not the dataclass itself.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarketSentimentSnapshot:
    """Market-level sentiment snapshot (Phase 3 P3-B / T3-B offline).

    Each record represents a single sentiment aggregate for a market on
    a single calendar date. Consumers reach this object via
    :meth:`MarketSentimentService.get_market_sentiment_snapshot` (the
    P3-B implementation under ``services/sentiment_service.py``).

    The data is auxiliary research material — it does not constitute a
    trade instruction or investment recommendation.

    Attributes:
        market:          Market identifier (e.g. ``"CN"``).
        sentiment_type:  Which aggregate the record represents (e.g.
                         ``"market_sentiment"``, ``"breadth"``). The
                         canonical ``market.sentiment_snapshot``
                         capability is intentionally broader than a
                         single metric so future sub-aggregates can
                         share the same collection.
        market_date:     Calendar date the snapshot covers
                         (``"YYYY-MM-DD"``).
        score:           The aggregate score in the provider's native
                         units. Allowed range depends on
                         ``sentiment_type``; this dataclass does not
                         enforce it.
        sample_size:     Number of underlying observations the score
                         was derived from. Zero is allowed (e.g. a
                         null day); callers can choose to filter it
                         out.
        source:          Provider / source identifier (e.g.
                         ``"akshare"``, ``"stub"``). Empty string is
                         tolerated and treated as "unknown" by
                         downstream consumers.
        provider:        Concrete provider object name (matches the
                         ``source`` field in :class:`DataResult`). Same
                         semantics as :attr:`SectorClassification.datasource`.
        fetched_at:      ISO-8601 timestamp recorded by the provider.
        notes:           Free-form annotation field — kept tiny so it
                         fits inside MongoDB documents without
                         blowing up the index size. Optional.
        metadata:        Carries context the service / router may add
                         (``security_id`` placeholder, ``extra`` tags,
                         etc.). Not part of the unique key.
    """

    market: str
    sentiment_type: str
    market_date: str
    score: float
    sample_size: int
    source: str = ""
    provider: str = ""
    fetched_at: str | None = None
    notes: str | None = None
    metadata: dict[str, object] | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "MarketSentimentSnapshot":
        """Build a snapshot from a MongoDB-shaped ``dict``.

        Missing fields fall back to their declared defaults. ``None``
        inputs are coerced to empty strings for the required textual
        fields so downstream comparisons do not blow up on missing
        MongoDB documents.

        Args:
            data: MongoDB document / writer payload.

        Returns:
            A new :class:`MarketSentimentSnapshot` instance.
        """
        if not isinstance(data, dict):
            raise TypeError(
                "MarketSentimentSnapshot.from_dict expects a dict, "
                f"got {type(data).__name__}"
            )
        return cls(
            market=str(data.get("market") or ""),
            sentiment_type=str(data.get("sentiment_type") or ""),
            market_date=str(data.get("market_date") or ""),
            score=float(data.get("score") or 0.0),
            sample_size=int(data.get("sample_size") or 0),
            source=str(data.get("source") or ""),
            provider=str(data.get("provider") or ""),
            fetched_at=data.get("fetched_at"),
            notes=data.get("notes"),
            metadata=data.get("metadata"),
        )


__all__ = ["MarketSentimentSnapshot"]