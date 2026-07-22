"""Phase 3 P3-C sentiment.limit_up_pool offline tests.

Acceptance matrix (kanban task body — minimum 6 tests):

| # | test name                                 | coverage                  |
|---|-------------------------------------------|---------------------------|
| ① | test_limit_up_pool_dataclass_schema       | dataclass / from_dict     |
| ② | test_limit_up_pool_readonly_query         | read-only query via router|
| ③ | test_limit_up_pool_capability_dispatch    | _TA_CN_NOT_COVERED        |
| ④ | test_limit_up_pool_fake_refresh_upsert    | fake refresh upsert       |
| ⑤ | test_limit_up_pool_injection_boundary     | DI boundary               |
| ⑥ | test_limit_up_pool_client_facade          | client.get_limit_up_pool  |

All tests are offline:

* No real MongoDB — uses mongomock / FakeDatabase.
* No real Provider API call — uses StubSentimentProvider.
* No AuditLogger / QualitySummary writes.
* No cron / systemd / webhook side-effects.
"""

from __future__ import annotations

from typing import Any

import mongomock
import pytest

from skills.data.unified_data import (
    DataRouter,
    Market,
    ProviderRegistry,
    SecurityId,
)
from skills.data.unified_data.adapters.p3_persistence_writer import (
    P3PersistenceWriter,
    P3_COLLECTION_BY_CAPABILITY,
)
from skills.data.unified_data.client import UnifiedDataClient
from skills.data.unified_data.exceptions import ProviderUnavailableError
from skills.data.unified_data.models.domain.sentiment import (
    LimitUpPoolRecord,
    MarketSentimentSnapshot,
)
from skills.data.unified_data.providers.sentiment_stub import (
    StubSentimentProvider,
)
from skills.data.unified_data.services.sentiment_service import (
    MarketSentimentService,
)
from skills.data.unified_data.tests.conftest import FakeProvider

LIMIT_UP_CAP = "sentiment.limit_up_pool"
SENTIMENT_COLLECTION = "03_data_ud_market_sentiment_snapshot"


def _make_db() -> Any:
    """Return a fresh mongomock database handle (offline only)."""
    return mongomock.MongoClient().get_database("tradingagents")


def _register_limit_up_stub(
    registry: ProviderRegistry,
    *,
    payload: list[dict] | None = None,
    name: str = "sentiment_stub",
) -> StubSentimentProvider:
    """Register a :class:`StubSentimentProvider` with limit_up_pool capability."""
    stub = StubSentimentProvider(
        name=name,
        payload=payload,
        capabilities=frozenset({LIMIT_UP_CAP, "sentiment.market_snapshot"}),
        markets={m for m in Market},
    )
    registry.register(stub)
    return stub


# ===========================================================================
# Test ① — dataclass schema
# ===========================================================================


class TestLimitUpPoolRecordSchema:
    """LimitUpPoolRecord dataclass + from_dict contract."""

    def test_dataclass_fields_match_spec(self):
        """Verify required and optional fields produce the right shape.

        Per SPEC §3.3 / DESIGN-03-014 V0.6 §3.3 — the record must carry
        per-stock limit-up fields including 封单金额/封成比/连板天数.
        """
        record = LimitUpPoolRecord(
            symbol="600519",
            market="CN",
            trade_date="2026-07-22",
            status="limit_up",
            limit_up_time="09:30:05",
            last_price=150.25,
            pct_chg=10.0,
            order_amount=850_000_000.0,
            turnover_amount=120_000_000.0,
            order_ratio=7.08,
            turnover_rate=0.85,
            consecutive_days=3,
            reason="白酒板块强势+业绩预增",
            market_cap=188_700_000_000.0,
            fetched_at="2026-07-22T10:00:00",
            provider="stub",
        )
        assert record.symbol == "600519"
        assert record.market == "CN"
        assert record.trade_date == "2026-07-22"
        assert record.status == "limit_up"
        assert record.limit_up_time == "09:30:05"
        assert record.last_price == 150.25
        assert record.pct_chg == 10.0
        assert record.order_amount == 850_000_000.0
        assert record.turnover_amount == 120_000_000.0
        assert record.order_ratio == 7.08
        assert record.turnover_rate == 0.85
        assert record.consecutive_days == 3
        assert record.reason == "白酒板块强势+业绩预增"
        assert record.market_cap == 188_700_000_000.0

    def test_from_dict_round_trip(self):
        """from_dict produces a correct LimitUpPoolRecord."""
        data = {
            "symbol": "600519",
            "market": "CN",
            "trade_date": "2026-07-22",
            "status": "limit_up",
            "limit_up_time": "09:30:05",
            "last_price": 150.25,
            "pct_chg": 10.0,
            "order_amount": 850_000_000.0,
            "turnover_amount": 120_000_000.0,
            "order_ratio": 7.08,
            "turnover_rate": 0.85,
            "consecutive_days": 3,
            "reason": "白酒板块强势+业绩预增",
            "market_cap": 188_700_000_000.0,
            "fetched_at": "2026-07-22T10:00:00",
            "provider": "stub",
        }
        record = LimitUpPoolRecord.from_dict(data)
        assert record.symbol == "600519"
        assert record.market == "CN"
        assert record.trade_date == "2026-07-22"
        assert record.status == "limit_up"
        assert record.order_amount == 850_000_000.0
        assert record.order_ratio == 7.08
        assert record.consecutive_days == 3

    def test_from_dict_tolerates_missing_optionals(self):
        """Missing optional fields fall back to defaults."""
        data = {
            "symbol": "000001",
            "market": "CN",
            "trade_date": "2026-07-22",
        }
        record = LimitUpPoolRecord.from_dict(data)
        assert record.symbol == "000001"
        assert record.market == "CN"
        assert record.trade_date == "2026-07-22"
        # Defaults
        assert record.status == "limit_up"
        assert record.limit_up_time is None
        assert record.last_price is None
        assert record.order_amount is None
        assert record.consecutive_days == 1
        assert record.reason is None
        assert record.provider == ""

    def test_from_dict_requires_dict(self):
        """from_dict raises TypeError on non-dict input."""
        with pytest.raises(TypeError):
            LimitUpPoolRecord.from_dict("not_a_dict")  # type: ignore[arg-type]

    def test_business_unique_key_shape(self):
        """Business unique key is {market, symbol, trade_date}."""
        record = LimitUpPoolRecord(
            symbol="600519", market="CN", trade_date="2026-07-22"
        )
        assert record.market == "CN"
        assert record.symbol == "600519"
        assert record.trade_date == "2026-07-22"


# ===========================================================================
# Test ② — read-only query via router
# ===========================================================================


class TestLimitUpPoolReadonlyQuery:
    """Step 4 success path — router + stub, no Step 2/3 leakage."""

    def test_query_path_returns_stub_payload(self):
        registry = ProviderRegistry()
        stub = _register_limit_up_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        result = svc.get_limit_up_pool(trade_date="2026-07-22")

        assert result.succeeded
        assert result.provider == "sentiment_stub"
        # Step 2/3 markers must not appear (read-only path).
        assert "ud_materialized" not in result.source_trace
        assert len(stub.call_log) == 1
        recorded_capability, recorded_market, recorded_params = stub.call_log[0]
        assert recorded_capability == LIMIT_UP_CAP

    def test_query_without_date_returns_all(self):
        registry = ProviderRegistry()
        stub = _register_limit_up_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        result = svc.get_limit_up_pool()

        assert result.succeeded
        assert result.provider == "sentiment_stub"
        assert len(stub.call_log) == 1


# ===========================================================================
# Test ③ — capability dispatch
# ===========================================================================


class TestLimitUpPoolCapabilityDispatch:
    """sentiment.limit_up_pool is registered in _TA_CN_NOT_COVERED."""

    def test_limit_up_pool_is_ta_cn_not_covered(self):
        assert LIMIT_UP_CAP in DataRouter._TA_CN_NOT_COVERED

    def test_limit_up_pool_collection_is_registered(self):
        assert P3_COLLECTION_BY_CAPABILITY[LIMIT_UP_CAP] == SENTIMENT_COLLECTION


# ===========================================================================
# Test ④ — fake refresh upsert
# ===========================================================================


class TestLimitUpPoolFakeRefreshUpsert:
    """Refresh path goes through P3PersistenceWriter (fake)."""

    def test_writer_upsert_round_trip_with_business_key(self):
        writer = P3PersistenceWriter(_make_db())
        records = [
            {
                "symbol": "600519",
                "market": "CN",
                "trade_date": "2026-07-22",
                "status": "limit_up",
                "limit_up_time": "09:30:05",
                "order_amount": 850_000_000.0,
                "provider": "stub",
            },
        ]
        outcome = writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=records,
            unique_key={"market", "symbol", "trade_date"},
        )
        assert outcome.persisted == 1
        assert outcome.failed == 0

        # Read back via the writer.
        docs = writer.get(
            SENTIMENT_COLLECTION,
            {"market": "CN", "symbol": "600519"},
        )
        assert len(docs) == 1
        assert docs[0]["trade_date"] == "2026-07-22"
        assert docs[0]["order_amount"] == 850_000_000.0

    def test_refresh_limit_up_pool_without_writer_raises(self):
        svc = MarketSentimentService(adapter=None)
        with pytest.raises(ProviderUnavailableError) as excinfo:
            svc.refresh_limit_up_pool(
                p3_writer=None,
            )
        assert "no P3PersistenceWriter" in str(excinfo.value)


# ===========================================================================
# Test ⑤ — injection boundary
# ===========================================================================


class TestLimitUpPoolInjectionBoundary:
    """DI surface contract for MarketSentimentService.get_limit_up_pool."""

    def test_no_router_raises_provider_unavailable(self):
        svc = MarketSentimentService(adapter=None)
        with pytest.raises(ProviderUnavailableError) as excinfo:
            svc.get_limit_up_pool(trade_date="2026-07-22")
        assert "no router wired" in str(excinfo.value)

    def test_router_injection_unblocks_query(self):
        registry = ProviderRegistry()
        _register_limit_up_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        result = svc.get_limit_up_pool(trade_date="2026-07-22")
        assert result.succeeded
        assert result.provider == "sentiment_stub"


# ===========================================================================
# Test ⑥ — client facade
# ===========================================================================


class TestLimitUpPoolClientFacade:
    """UnifiedDataClient.get_limit_up_pool wiring."""

    def test_client_get_limit_up_pool_returns_data_result(self):
        registry = ProviderRegistry()
        _register_limit_up_stub(registry)
        client = UnifiedDataClient(registry=registry)

        result = client.get_limit_up_pool(trade_date="2026-07-22")

        assert result.succeeded
        assert result.provider == "sentiment_stub"
        assert isinstance(result.data, (list, type(None)))

    def test_client_get_limit_up_pool_uses_sentiment_service(self):
        """Lazy _sentiment_service is correctly wired."""
        registry = ProviderRegistry()
        _register_limit_up_stub(registry)
        client = UnifiedDataClient(registry=registry)

        svc = client._get_sentiment_service()
        assert isinstance(svc, MarketSentimentService)

        result = svc.get_limit_up_pool(trade_date="2026-07-22")
        assert result.succeeded
