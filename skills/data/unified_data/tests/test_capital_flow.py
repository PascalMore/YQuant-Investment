"""Phase 3 P3-B CapitalFlowRecord domain-object tests (offline T3-P3B).

Covers the V0.5 §3.2 / SPEC-03-014 §3.2 contract for the
:class:`CapitalFlowRecord` dataclass:

* Exactly 17 fields (locked count — see V0.5 §0.4 dataclass freeze).
* The three business-key fields (``symbol`` / ``market`` / ``trade_date``)
  default to empty strings when missing from the source dict — this is
  the ``from_dict`松映射、不抛 KeyError`` contract (SPEC §3.2).
* ``*_net_inflow`` sign convention is preserved by ``from_dict``:
  positive = net inflow, negative = net outflow (SPEC §3.2 表 footnote
  「资金流符号约定」). This is enforced as a *passthrough* — the
  dataclass does not transform signs (V0.5 §3.2 stays neutral) but the
  test pins the convention so a future refactor does not silently
  invert it.
* Non-沪/深港通 records persist with all ``northbound_*`` fields as
  ``None`` (V0.5 §2.3 "部分字段不可用" branch). The dataclass must
  preserve this exactly.
* Required ``provider`` field defaults to empty string when missing.
* All other fields default to ``None`` when missing.
* ``trade_date`` keeps the ``"YYYY-MM-DD"`` shape — dataclass does not
  coerce / reformat.

The fixture path mirrors the P3-A sector pattern: a colocated
:class:`CapitalFlowRecord` is the production domain object; the test
suite uses the dict-shaped fixtures from :mod:`flow_fixtures` and
round-trips them through ``CapitalFlowRecord.from_dict``.
"""

from __future__ import annotations

import dataclasses

from skills.data.unified_data.models.domain.flow import CapitalFlowRecord


# ---------------------------------------------------------------------------
# Field count + shape — V0.5 §3.2 lock
# ---------------------------------------------------------------------------


class TestCapitalFlowRecordFields:
    """V0.5 §3.2 frozen dataclass shape."""

    def test_exactly_17_fields(self):
        """Lock the field count — V0.5 §3.2 17 fields freeze.

        Adding / removing a field is a Phase-3 contract change; if this
        count changes without a SPEC update the test fails loudly.
        """
        fields = dataclasses.fields(CapitalFlowRecord)
        assert len(fields) == 17, (
            f"CapitalFlowRecord must have 17 fields (V0.5 §3.2 freeze), "
            f"got {len(fields)}: {[f.name for f in fields]}"
        )

    def test_business_key_fields_are_first_three(self):
        """``{market, symbol, trade_date}`` is the P3-B unique key.

        The order is documented in SPEC §3.2 (symbol / market / trade_date
        first; the rest after). The test pins both presence and order so
        downstream P3PersistenceWriter consumers can rely on the shape.
        """
        fields = [f.name for f in dataclasses.fields(CapitalFlowRecord)]
        assert fields[:3] == ["symbol", "market", "trade_date"]

    def test_provider_is_required_field(self):
        """``provider`` is the (必填) field per SPEC §3.2 — must be present
        and default to empty string when missing.
        """
        fields = {f.name: f for f in dataclasses.fields(CapitalFlowRecord)}
        assert "provider" in fields
        # Default is empty string, not None — SPEC §3.2 lists ``provider``
        # as 必填 with a ``str(provider or "")`` fallback in ``from_dict``.
        record = CapitalFlowRecord(symbol="600519", market="CN", trade_date="2026-07-21")
        assert record.provider == ""


# ---------------------------------------------------------------------------
# from_dict — happy paths
# ---------------------------------------------------------------------------


class TestCapitalFlowRecordFromDict:
    """``CapitalFlowRecord.from_dict`` happy-path contract."""

    def test_round_trip_full_record(self):
        """A complete fixture round-trips through ``from_dict`` losslessly."""
        source = {
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
            "provider": "akshare",
        }
        record = CapitalFlowRecord.from_dict(source)

        assert record.symbol == "600519"
        assert record.market == "CN"
        assert record.trade_date == "2026-07-21"
        assert record.main_net_inflow == 1_230_000.0
        assert record.super_large_net_inflow == 800_000.0
        assert record.large_net_inflow == 430_000.0
        assert record.medium_net_inflow == -50_000.0
        assert record.small_net_inflow == -120_000.0
        assert record.main_net_inflow_ratio == 8.5
        assert record.northbound_net_inflow == 250_000.0
        assert record.northbound_hold_shares == 9_500_000.0
        assert record.northbound_hold_ratio == 7.55
        assert record.margin_buy == 12_000_000.0
        assert record.margin_sell == 9_500_000.0
        assert record.margin_balance == 18_000_000.0
        assert record.fetched_at == "2026-07-21T18:30:00"
        assert record.provider == "akshare"


# ---------------------------------------------------------------------------
# from_dict — sign convention + northbound None
# ---------------------------------------------------------------------------


class TestCapitalFlowRecordSignConvention:
    """Sign convention: positive = 净流入, negative = 净流出.

    Per SPEC §3.2 the dataclass is a *passthrough* — ``from_dict`` must
    preserve whatever sign the source dict carries. The test pins this
    so a future refactor does not silently invert it.
    """

    def test_positive_net_inflow_preserved(self):
        record = CapitalFlowRecord.from_dict(
            {
                "symbol": "600519",
                "market": "CN",
                "trade_date": "2026-07-21",
                "main_net_inflow": 1_000_000.0,
            }
        )
        assert record.main_net_inflow == 1_000_000.0
        assert record.main_net_inflow > 0

    def test_negative_net_inflow_preserved(self):
        record = CapitalFlowRecord.from_dict(
            {
                "symbol": "600519",
                "market": "CN",
                "trade_date": "2026-07-21",
                "main_net_inflow": -500_000.0,
                "super_large_net_inflow": -200_000.0,
                "large_net_inflow": -100_000.0,
                "medium_net_inflow": -150_000.0,
                "small_net_inflow": -50_000.0,
            }
        )
        assert record.main_net_inflow == -500_000.0
        assert record.super_large_net_inflow == -200_000.0
        assert record.large_net_inflow == -100_000.0
        assert record.medium_net_inflow == -150_000.0
        assert record.small_net_inflow == -50_000.0
        # All four *_net_inflow fields are negative = 净流出.
        for value in (
            record.main_net_inflow,
            record.super_large_net_inflow,
            record.large_net_inflow,
            record.medium_net_inflow,
            record.small_net_inflow,
        ):
            assert value < 0


class TestCapitalFlowRecordNorthboundNone:
    """Non-沪/深港通 records carry ``northbound_*`` = ``None``.

    Per V0.5 §2.3 "部分字段不可用" the record is still persisted; only
    the northbound / margin fields become ``None``.
    """

    def test_non_hk_connect_record_keeps_main_flow_but_drops_northbound(self):
        """The second fixture (非沪/深港通) round-trips with None NB fields."""
        from skills.data.unified_data.tests.fixtures.flow_fixtures import (
            sample_capital_flow_records,
        )

        records = sample_capital_flow_records()
        # Second record = 300999 (非沪/深港通). northbound_* / margin_* = None.
        non_hk = next(r for r in records if r["symbol"] == "300999")
        record = CapitalFlowRecord.from_dict(non_hk)

        # Main flow fields are still populated.
        assert record.main_net_inflow is not None
        assert record.super_large_net_inflow is not None
        assert record.large_net_inflow is not None
        assert record.medium_net_inflow is not None
        assert record.small_net_inflow is not None
        # Northbound fields are explicitly None — V0.5 §2.3 部分字段不可用.
        assert record.northbound_net_inflow is None
        assert record.northbound_hold_shares is None
        assert record.northbound_hold_ratio is None
        # Margin fields are also None for non-margin-eligible symbols.
        assert record.margin_buy is None
        assert record.margin_sell is None
        assert record.margin_balance is None


# ---------------------------------------------------------------------------
# from_dict — missing optional fields
# ---------------------------------------------------------------------------


class TestCapitalFlowRecordFromDictToleratesMissing:
    """``from_dict`` must not raise when optional fields are missing."""

    def test_minimal_dict_only_business_keys(self):
        """A dict with just ``symbol`` / ``market`` / ``trade_date`` is valid."""
        record = CapitalFlowRecord.from_dict(
            {
                "symbol": "600519",
                "market": "CN",
                "trade_date": "2026-07-21",
            }
        )
        assert record.symbol == "600519"
        assert record.market == "CN"
        assert record.trade_date == "2026-07-21"
        assert record.main_net_inflow is None
        assert record.super_large_net_inflow is None
        assert record.large_net_inflow is None
        assert record.medium_net_inflow is None
        assert record.small_net_inflow is None
        assert record.main_net_inflow_ratio is None
        assert record.northbound_net_inflow is None
        assert record.northbound_hold_shares is None
        assert record.northbound_hold_ratio is None
        assert record.margin_buy is None
        assert record.margin_sell is None
        assert record.margin_balance is None
        assert record.fetched_at is None
        # provider defaults to empty string (not None).
        assert record.provider == ""

    def test_empty_dict_returns_default_record(self):
        """Empty dict produces a record with all-empty business keys + None rest."""
        record = CapitalFlowRecord.from_dict({})
        assert record.symbol == ""
        assert record.market == ""
        assert record.trade_date == ""
        assert record.provider == ""
        assert record.main_net_inflow is None
        assert record.fetched_at is None


# ---------------------------------------------------------------------------
# Trade-date shape preservation
# ---------------------------------------------------------------------------


class TestCapitalFlowRecordTradeDateShape:
    """``trade_date`` is passed through unchanged — no auto-reformat."""

    def test_trade_date_iso_passthrough(self):
        record = CapitalFlowRecord.from_dict(
            {
                "symbol": "600519",
                "market": "CN",
                "trade_date": "2026-07-21",
            }
        )
        assert record.trade_date == "2026-07-21"

    def test_trade_date_compact_passthrough(self):
        # The dataclass does not normalise compact dates — caller is
        # responsible. Pin the contract so a future "helpful" reformat
        # breaks loudly.
        record = CapitalFlowRecord.from_dict(
            {
                "symbol": "600519",
                "market": "CN",
                "trade_date": "20260721",
            }
        )
        assert record.trade_date == "20260721"