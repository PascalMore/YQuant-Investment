"""Offline stub provider for ``flow.capital_flow_daily`` and
``flow.northbound_daily`` (Phase 3 P3-B / T3-P3B).

:class:`StubFlowProvider` is the offline-only stand-in for the real
(yet-to-be-built) AKShare-backed capital-flow source. It mirrors the
shape every other DataProvider in
:mod:`skills.data.unified_data.providers` exposes but performs **no
I/O** of any kind:

* No real HTTP / AKShare / Tushare calls.
* No MongoDB writes.
* No network / filesystem / credential access.
* Returns deterministic canned payloads so the service-layer tests can
  reason about the query/refresh wiring without flakiness.

Scope guardrails (T3-P3B kanban task body):

* Capabilities advertised: ``{"flow.capital_flow_daily",
  "flow.northbound_daily"}``. Both map to the single P3-B collection
  ``03_data_ud_stock_capital_flow`` via the frozen
  :data:`P3_COLLECTION_BY_CAPABILITY` table in
  ``adapters/p3_persistence_writer.py`` (V0.5 §0.4).
* Market coverage defaults to ``{Market.CN}``; tests can override via
  the ``markets`` kwarg.
* ``fetch`` returns a list of plain ``dict`` objects that look exactly
  like what ``P3PersistenceWriter.upsert`` would persist — including the
  ``(market, symbol, trade_date)`` business unique key the writer
  enforces.

The class is intentionally tiny: it is **not** meant to model the real
AKShare capital-flow API. Once the real provider ships (post-T3-P3B),
the service layer / router will continue to work unchanged because the
contract is dictated by :attr:`DataProvider.capabilities` and the
:func:`CapitalFlowRecord.from_dict` mapping — not by this stub's
internals.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..exceptions import UnsupportedCapabilityError
from ..models import Market
from ..provider import DataProvider

# The production stub ships its own minimal offline payload (see
# ``_build_default_payload`` below) so the production runtime has
# zero dependency on the test fixture module (T3-P3B m4 "production
# stub 自带 payload 或由调用方注入"). Tests that want richer payloads
# should call this stub with a custom ``payload=...`` kwarg rather
# than rely on a hard-coded test fixture. (The previous reverse
# import ``from ..tests.fixtures.flow_fixtures import
# sample_capital_flow_records`` was removed — it coupled production
# code to a test-only module.)


def _build_default_payload() -> tuple[dict, ...]:
    """Return the default offline payload (three 沪/深港通 + one 非).

    Four records mirror the production test fixture so the stub's
    default behaviour is consistent across the test suite and any
    ad-hoc exploration. The 17-field V0.5 schema is preserved end-to-
    end so the service / router can resolve the northbound projection
    without needing to import the test-fixture module.

    Four records (matching the T3-P3B m4 fixture expansion):

    * A: 600519 (沪股通) — full bands + northbound + margin populated.
    * B: 300999 (非港通) — full bands + None NB / margin.
    * C: 000001 (深港通) — northbound fields with HK-side precision.
    * D: AAPL (US, not on Stock Connect) — full bands + None NB.

    The four-record default ensures market-level northbound calls
    (``security_id=None``) return >= 3 records so the V0.5 §3.2
    ``record_scope`` projection can be exercised end-to-end without
    custom fixtures.
    """
    return (
        # Record A: 600519 (沪股通) — full bands + northbound + margin
        {
            "symbol": "600519",
            "market": "CN",
            "trade_date": "2026-07-21",
            "main_net_inflow": 1_230_000.0,
            "super_large_net_inflow": 800_000.0,
            "large_net_inflow": 430_000.0,
            "medium_net_inflow": -50_000.0,
            "small_net_inflow": -120_000.0,
            "main_net_inflow_ratio": 8.5,
            "northbound_net_inflow": 250_000.0,
            "northbound_hold_shares": 9_500_000.0,
            "northbound_hold_ratio": 7.55,
            "margin_buy": 12_000_000.0,
            "margin_sell": 9_500_000.0,
            "margin_balance": 18_000_000.0,
            "fetched_at": "2026-07-21T18:30:00",
            "provider": "flow_stub",
        },
        # Record B: 300999 (非沪/深港通) — full bands + None NB / margin
        {
            "symbol": "300999",
            "market": "CN",
            "trade_date": "2026-07-21",
            "main_net_inflow": -340_000.0,
            "super_large_net_inflow": -150_000.0,
            "large_net_inflow": -190_000.0,
            "medium_net_inflow": 30_000.0,
            "small_net_inflow": 80_000.0,
            "main_net_inflow_ratio": -2.1,
            "northbound_net_inflow": None,
            "northbound_hold_shares": None,
            "northbound_hold_ratio": None,
            "margin_buy": None,
            "margin_sell": None,
            "margin_balance": None,
            "fetched_at": "2026-07-21T18:30:00",
            "provider": "flow_stub",
        },
        # Record C: 000001 (深港通 / HK Connect) — northbound fields
        # with HK-side precision convention.
        {
            "symbol": "000001",
            "market": "CN",
            "trade_date": "2026-07-21",
            "main_net_inflow": 320_000.0,
            "super_large_net_inflow": 120_000.0,
            "large_net_inflow": 200_000.0,
            "medium_net_inflow": -10_000.0,
            "small_net_inflow": 10_000.0,
            "main_net_inflow_ratio": 3.4,
            "northbound_net_inflow": 480_000.0,
            "northbound_hold_shares": 4_750_000.0,
            "northbound_hold_ratio": 4.2,
            "margin_buy": 8_500_000.0,
            "margin_sell": 7_900_000.0,
            "margin_balance": 12_400_000.0,
            "fetched_at": "2026-07-21T18:30:00",
            "provider": "flow_stub",
        },
        # Record D: AAPL (US, not on Stock Connect) — full bands +
        # None NB / margin. Pins "US-shaped" northbound row so the
        # ``record_scope`` projection still holds for non-CN markets.
        {
            "symbol": "AAPL",
            "market": "US",
            "trade_date": "2026-07-21",
            "main_net_inflow": 9_800_000.0,
            "super_large_net_inflow": 5_400_000.0,
            "large_net_inflow": 4_400_000.0,
            "medium_net_inflow": -1_200_000.0,
            "small_net_inflow": 600_000.0,
            "main_net_inflow_ratio": 1.8,
            "northbound_net_inflow": None,
            "northbound_hold_shares": None,
            "northbound_hold_ratio": None,
            "margin_buy": None,
            "margin_sell": None,
            "margin_balance": None,
            "fetched_at": "2026-07-21T18:30:00",
            "provider": "flow_stub",
        },
    )


class StubFlowProvider(DataProvider):
    """Offline stub provider for the two Phase 3 P3-B flow capabilities.

    Knobs (all kw-only):

    * ``payload``           — tuple / list of dicts returned by
      :meth:`fetch`. Defaults to
      :func:`sample_capital_flow_records` so the typical
      ``StubFlowProvider()`` instantiation yields a fully-functional
      provider without test scaffolding.
    * ``capabilities``      — capability set. Defaults to
      ``{"flow.capital_flow_daily", "flow.northbound_daily"}``. Tests
      can shrink the set to cover dispatch edge cases.
    * ``markets``           — covered markets. Defaults to
      ``{Market.CN}``.
    * ``available``         — value of :meth:`is_available` (defaults to
      ``True``).
    * ``raise_on_fetch``    — exception to raise from :meth:`fetch`
      instead of returning the payload. Useful for testing the router's
      failure path.

    Each :meth:`fetch` call appends a record to ``call_log`` so tests
    can assert the right (capability, market, params) tuple reached the
    stub — the same pattern :class:`FakeProvider` uses elsewhere in the
    suite.
    """

    _DEFAULT_CAPABILITIES = (
        "flow.capital_flow_daily",
        "flow.northbound_daily",
    )

    def __init__(
        self,
        name: str = "flow_stub",
        *,
        payload: Iterable[dict] | None = None,
        capabilities: Iterable[str] = _DEFAULT_CAPABILITIES,
        markets: Iterable[Market] = (Market.CN,),
        available: bool = True,
        raise_on_fetch: BaseException | None = None,
    ) -> None:
        self._name = name
        self._capabilities: set[str] = set(capabilities)
        self._markets: set[Market] = set(markets)
        if payload is None:
            payload = _build_default_payload()
        self._payload: tuple[dict, ...] = tuple(
            dict(record) for record in payload
        )
        self._available = available
        self._raise = raise_on_fetch
        # Each entry: ``(capability, market_label, params)`` — the same
        # three-tuple pattern used by :class:`StubSentimentProvider`
        # in :mod:`skills.data.unified_data.providers.sentiment_stub`.
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
        """Return a deterministic offline capital-flow payload.

        Records the call in ``call_log`` and respects the
        ``raise_on_fetch`` knob. The capability is constructed from
        ``(domain, operation)`` and matched against the configured set
        — anything else triggers :class:`UnsupportedCapabilityError` so
        the stub stays faithful to the :class:`DataProvider` contract.
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


__all__ = ["StubFlowProvider"]