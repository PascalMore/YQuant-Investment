"""Offline stub provider for ``sentiment.market_snapshot`` (Phase 3 P3-B / T3-B).

:class:`StubSentimentProvider` is the offline-only stand-in for the
real (yet-to-be-built) AKShare-backed sentiment source. It mirrors
the shape every other DataProvider in :mod:`skills.data.unified_data.providers`
exposes but performs **no I/O** of any kind:

* No real HTTP / AKShare / Tushare calls.
* No MongoDB writes.
* No network / filesystem / credential access.
* Returns deterministic canned payloads so the service-layer tests can
  reason about the query/refresh wiring without flakiness.

Scope guardrails (T3-B kanban task body):

* Capabilities advertised: ``{"sentiment.market_snapshot"}``. The
  sister capability ``sentiment.limit_up_pool`` (V0.5 §2.2) is
  **explicitly excluded** and arrives in T3-C. The capability name
  matches the frozen ``P3_COLLECTION_BY_CAPABILITY`` key in
  ``adapters/p3_persistence_writer.py``.
* Market coverage defaults to ``{Market.CN}``; tests can override via
  the ``markets`` kwarg.
* ``fetch`` returns a list of plain ``dict`` objects that look exactly
  like what ``P3PersistenceWriter.upsert`` would persist — including
  the ``(market, sentiment_type, market_date)`` business unique key
  the writer enforces (T3-B augments the V0.5 §0.4
  ``{market, snapshot_date, snapshot_time}`` key with
  ``sentiment_type`` so multiple aggregates can coexist in the same
  collection).

The class is intentionally tiny: it is **not** meant to model the real
AKShare sentiment API. Once the real provider ships (post-T3-B), the
service layer / router will continue to work unchanged because the
contract is dictated by :attr:`DataProvider.capabilities` and the
:func:`MarketSentimentSnapshot.from_dict` mapping — not by this
stub's internals.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..exceptions import UnsupportedCapabilityError
from ..models import Market
from ..provider import DataProvider


# Canonical offline payload — one record per sentiment_type so the
# service layer can prove the ``(market, sentiment_type, market_date)``
# uniqueness key flows through unchanged. The numbers are
# deterministic and intentionally boring (so test failures are not
# confused with data changes).
_DEFAULT_SENTIMENT_PAYLOAD: tuple[dict, ...] = (
    {
        "market": "CN",
        "sentiment_type": "market_sentiment",
        "market_date": "2026-07-21",
        "score": 52.3,
        "sample_size": 4250,
        "source": "stub",
        "provider": "stub",
        "notes": "neutral-to-slightly-bullish offline fixture",
    },
    {
        "market": "CN",
        "sentiment_type": "breadth",
        "market_date": "2026-07-21",
        "score": 0.42,
        "sample_size": 4250,
        "source": "stub",
        "provider": "stub",
        "notes": "advance/decline ratio neutral",
    },
)


class StubSentimentProvider(DataProvider):
    """Offline stub provider for ``sentiment.market_snapshot``.

    Knobs (all kw-only):

    * ``payload``           — tuple / list of dicts returned by
      :meth:`fetch`. Defaults to :data:`_DEFAULT_SENTIMENT_PAYLOAD`
      so the typical ``StubSentimentProvider()`` instantiation yields
      a fully-functional provider without test scaffolding.
    * ``capabilities``      — capability set. Defaults to
      ``{"sentiment.market_snapshot"}``. Tests can extend the set to
      cover dispatch edge cases.
    * ``markets``           — covered markets. Defaults to
      ``{Market.CN}``.
    * ``available``         — value of :meth:`is_available` (defaults
      to ``True``).
    * ``raise_on_fetch``    — exception to raise from :meth:`fetch`
      instead of returning the payload. Useful for testing the
      router's failure path.

    Each :meth:`fetch` call appends a record to ``call_log`` so tests
    can assert the right (capability, market, params) tuple reached
    the stub — the same pattern :class:`FakeProvider` uses elsewhere
    in the suite.
    """

    def __init__(
        self,
        name: str = "sentiment_stub",
        *,
        payload: Iterable[dict] | None = None,
        capabilities: Iterable[str] = ("sentiment.market_snapshot",),
        markets: Iterable[Market] = (Market.CN,),
        available: bool = True,
        raise_on_fetch: BaseException | None = None,
    ) -> None:
        self._name = name
        self._capabilities: set[str] = set(capabilities)
        self._markets: set[Market] = set(markets)
        self._payload: tuple[dict, ...] = tuple(
            payload if payload is not None else _DEFAULT_SENTIMENT_PAYLOAD
        )
        self._available = available
        self._raise = raise_on_fetch
        # Each entry: ``(capability, market, params)`` — the same
        # three-tuple pattern used by :class:`FakeProvider` in
        # :mod:`skills.data.unified_data.tests.conftest`.
        self.call_log: list[tuple[str, str, dict]] = []

    # ------------------------------------------------------------------
    # DataProvider protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> set[str]:
        return set(self._capabilities)

    @property
    def markets(self) -> set[Market]:
        return set(self._markets)

    def is_available(self) -> bool:
        return self._available

    def fetch(
        self,
        domain: str,
        operation: str,
        security_id: Any,
        **params: Any,
    ) -> list[dict]:
        """Return a deterministic offline snapshot payload.

        Records the call in ``call_log`` and respects the
        ``raise_on_fetch`` knob. The capability is constructed from
        ``(domain, operation)`` and matched against the configured
        set — anything else triggers :class:`UnsupportedCapabilityError`
        so the stub stays faithful to the :class:`DataProvider`
        contract.
        """
        capability = f"{domain}.{operation}"
        market = getattr(security_id, "market", None)
        market_label = market.value if isinstance(market, Market) else str(market)
        self.call_log.append((capability, market_label, dict(params)))
        if capability not in self._capabilities:
            raise UnsupportedCapabilityError(
                f"{self._name!r} does not declare capability {capability!r}"
            )
        if self._raise is not None:
            raise self._raise
        # Defensive copy so callers cannot mutate the stub's internal
        # payload via in-place edits.
        return [dict(record) for record in self._payload]


__all__ = ["StubSentimentProvider"]