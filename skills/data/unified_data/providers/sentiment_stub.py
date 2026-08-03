"""Offline stub provider for ``sentiment.market_snapshot`` (Phase 3 P3-C / T3R).

:class:`StubSentimentProvider` is the offline-only stand-in for the
real (yet-to-be-built) AKShare-backed sentiment source. It mirrors
the shape every other DataProvider in :mod:`skills.data.unified_data.providers`
exposes but performs **no I/O** of any kind:

* No real HTTP / AKShare / Tushare calls.
* No MongoDB writes.
* No network / filesystem / credential access.
* Returns deterministic canned payloads so the service-layer tests can
  reason about the query/refresh wiring without flakiness.

Scope guardrails (T3R kanban task body):

* Capabilities advertised: `{"sentiment.market_snapshot"}`. The
  sister capability `sentiment.limit_up_pool` (V0.5 section 2.2) is
  **explicitly included** from T3-C onward. The capability name
  matches the frozen `P3_COLLECTION_BY_CAPABILITY` key in
  `adapters/p3_persistence_writer.py`.
* Market coverage defaults to ``{Market.CN}``; tests can override via
  the ``markets`` kwarg.
* The default ``market_snapshot`` fetch returns one deterministic,
  fully populated canonical 22-field record keyed by
  ``{market, snapshot_date, snapshot_time}``. It is an offline fixture,
  not a fabricated market reading: ``market_temperature`` and
  ``northbound_net_flow`` stay ``None``.

The class is intentionally tiny: it is **not** meant to model the real
AKShare sentiment API. Once the real provider ships, the service layer /
router will continue to work unchanged because the contract is dictated
by :attr:`DataProvider.capabilities` and
:func:`MarketSentimentSnapshot.from_dict` — not by this stub's internals.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..exceptions import UnsupportedCapabilityError
from ..models import Market
from ..provider import DataProvider


# Canonical 22-field offline fixture. Values are deterministic markers for
# tests, not live market observations. In particular, no temperature formula
# is implied and no northbound endpoint is consulted.
_DEFAULT_SENTIMENT_PAYLOAD: tuple[dict, ...] = (
    {
        "snapshot_date": "2026-07-21",
        "snapshot_time": "close",
        "market": "CN",
        "limit_up_count": 42,
        "limit_down_count": 8,
        "limit_up_count_ex_st": 38,
        "limit_down_count_ex_st": 7,
        "advance_count": 3250,
        "decline_count": 1500,
        "flat_count": 250,
        "total_listed_count": 5000,
        "market_temperature": None,
        # EOD-6 (SPEC V0.22 §3.3): total_turnover is permanently None on
        # the canonical offline stub. The contract is enforced twice:
        # (a) the stub payload itself ships ``None``; (b) ``from_dict``
        # coerces any non-None value back to ``None`` so an upstream
        # change cannot silently reintroduce a numeric value.
        "total_turnover": None,
        "hot_concepts": ["offline_fixture"],
        "continuous_limit_up": [
            {
                "symbol": "OFFLINE-001",
                "days": 1,
                "reason": "deterministic offline fixture",
            }
        ],
        "max_continuous_days": 1,
        "northbound_net_flow": None,
        "limit_up_pool": ["OFFLINE-001"],
        "limit_down_pool": ["OFFLINE-002"],
        "fetched_at": "2026-07-21T15:30:00+08:00",
        "provider": "sentiment_stub",
        "raw_payload": {
            "source": "deterministic_offline_fixture",
            "live_data": False,
        },
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
      ``{"sentiment.market_snapshot", "sentiment.limit_up_pool"}``.
      Tests can subset the set to cover dispatch edge cases.
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
        capabilities: Iterable[str] = (
            "sentiment.market_snapshot",
            "sentiment.limit_up_pool",
        ),
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