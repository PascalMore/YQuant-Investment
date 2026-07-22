"""Capital-flow fixtures for T3-P3B offline implementation tests (Phase 3 P3-B).

This fixture module provides:

* :func:`sample_capital_flow_records` — two offline ``dict`` payloads that
  cover the two query shapes a T3-P3B test suite needs to reason about:

    1. A **沪深港通** record (``600519``) with the full set of capital-flow
       fields populated, **including** ``northbound_*`` fields.
    2. A **非沪深港通** record (``000001`` is in the SZSE/HK Connect list
       but this fixture uses a deliberate synthetic symbol — ``300999`` —
       that no沪/深港通 channel touches) where the ``northbound_*`` fields
       are explicitly ``None`` and every other capital-flow field is still
       populated. This matches the V0.5 contract that **non-沪/深港通
       symbols write all main/super/large/medium/small fields plus None
       northbound fields, not skip the whole record**.

* :class:`StubFlowProvider` — a minimal :class:`DataProvider`-compatible
  stub that advertises ``flow.capital_flow_daily`` and
  ``flow.northbound_daily`` and returns the fixture records. **Not** the
  production ``AKShareProvider`` — Phase 3 capability registration with
  the real provider is *out of T3-P3B scope* (kanban task body explicitly
  forbids editing ``providers/akshare.py``).

The fixture deliberately stays lightweight: no real AKShare call, no
MongoDB DDL, no schema impact.
"""

from __future__ import annotations

from typing import Any, Iterable

from skills.data.unified_data import DataProvider, Market


# Canonical offline payloads — covers the three documented
# northbound shapes (mainland / HK / US) plus a non-港通
# counter-example. Each record carries the full 17-field V0.5 schema
# so the service / router can resolve the northbound projection
# without additional shape hardening.
#
# The four records share ``trade_date="2026-07-21"`` so a single
# date filter resolves exactly one doc per shape — tests can pin
# "mainland vs HK vs US" without timing flakiness.
#
# Records:
#
#   * A: 600519  (沪股通) — full bands + main NB + margin populated.
#   * B: 300999  (非港通) — full bands + NB / margin explicitly None.
#   * C: 000001  (深港通 / HK Connect) — northbound shape with HK-side
#                     attributes (e.g. ``northbound_hold_ratio`` is
#                     decimal-precision distinct from the 沪 record).
#   * D: AAPL    (US stock, not on Stock Connect) — model "US"
#                     northbound slot; northbound_* fields absent
#                     in real data, but the schema carries the same
#                     ``None`` slot.
_SAMPLE_FLOW_RECORDS: tuple[dict, ...] = (
    # Record A: 600519 (沪股通) — main flow populated AND northbound
    # populated (positive net buy, share balance, ratio). ``provider``
    # field is non-empty per V0.5 §6.1 V-GEN-5 traceability check.
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
    # Record B: 300999 (非沪/深港通) — main flow populated but
    # ``northbound_*`` and ``margin_*`` fields explicitly ``None``.
    # The fixture exercises the V0.5 §2.3 "部分字段不可用" branch
    # (records still persist when only some fields are unavailable).
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
    # Record C: 000001 (深港通 / HK Connect) — same date; full bands
    # populated, northbound fields populated with the HK-side
    # precision convention (4-decimal ratio, smaller share count
    # scale). The fixture makes the shape distinction explicit so
    # the ``_project_northbound`` test can pin "mainland / HK / US"
    # without the per-market differences being conflated.
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
    # Record D: AAPL (US stock, not on Stock Connect) — northbound
    # fields are present in the dataclass schema but the US market
    # does not carry them in production; they are explicitly None.
    # The fixture pins "US-shaped" northbound row as an outlier so
    # ``_project_northbound`` projections still hold even when the
    # record's market label does not match the canonical CN/HK
    # stock-connect set.
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


def sample_capital_flow_records() -> list[dict]:
    """Return two canonical offline capital-flow records (defensive copy).

    The first record covers a symbol with full capital-flow fields **plus**
    ``northbound_*`` populated (沪/深港通标的). The second covers a symbol
    with main flow fields populated but ``northbound_*`` / ``margin_*``
    explicitly ``None`` (非沪/深港通标的).

    Each call returns a fresh ``list[dict]`` so callers can mutate the
    payload without contaminating the canonical fixture.
    """
    return [dict(record) for record in _SAMPLE_FLOW_RECORDS]


class StubFlowProvider(DataProvider):
    """In-memory stand-in for AKShare's Phase 3 flow capabilities.

    The real AKShare integration is out of T3-P3B scope; this stub
    advertises only the two P3-B capabilities and returns the fixture
    records so router-level injection tests can assert the
    internal-first / Step-2 dispatch.

    Knobs (kw-only):

    * ``payload`` — list of dicts returned by :meth:`fetch`. Defaults
      to :func:`sample_capital_flow_records`.
    * ``raise_on_fetch`` — exception to raise instead of returning the
      payload (default ``None``).
    * ``available`` — value of :meth:`is_available` (default ``True``).
    * ``capabilities`` — capability set (default
      ``{"flow.capital_flow_daily", "flow.northbound_daily"}``).
    * ``markets`` — covered markets (default ``{Market.CN}``).
    """

    def __init__(
        self,
        name: str = "flow_stub",
        *,
        payload: Iterable[dict] | None = None,
        capabilities: Iterable[str] = (
            "flow.capital_flow_daily",
            "flow.northbound_daily",
        ),
        markets: Iterable[Market] = (Market.CN,),
        raise_on_fetch: BaseException | None = None,
        available: bool = True,
    ) -> None:
        self._name = name
        self._capabilities = set(capabilities)
        self._markets = set(markets)
        if payload is None:
            payload = sample_capital_flow_records()
        self._payload = [dict(record) for record in payload]
        self._raise = raise_on_fetch
        self._available = available
        # Each entry: ``(capability, market_label, params)``. The
        # security_id's canonical string is NOT recorded — the
        # P3-B boundary contract states the security_id is sanitised
        # by the router before reaching the provider.
        self.call_log: list[tuple[str, str, dict]] = []

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
        capability = f"{domain}.{operation}"
        market = getattr(security_id, "market", None)
        market_label = market.value if isinstance(market, Market) else str(market)
        self.call_log.append((capability, market_label, dict(params)))
        if self._raise is not None:
            raise self._raise
        # Defensive copy so callers cannot mutate the stub's internal
        # payload via in-place edits.
        return [dict(record) for record in self._payload]


__all__ = [
    "sample_capital_flow_records",
    "StubFlowProvider",
]