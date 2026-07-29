"""Facade tests for the P3-A sector client entry methods."""

from __future__ import annotations

from unittest.mock import Mock

from skills.data.unified_data import DataResult, Market, SecurityId, UnifiedDataClient


def _result(operation: str) -> DataResult:
    return DataResult.success(
        data={"operation": operation},
        security_id=SecurityId(market=Market.CN, symbol="sector"),
        domain="sector",
        operation=operation,
        provider="sector_stub",
    )


def test_get_sector_snapshot_delegates_and_returns_same_data_result() -> None:
    client = UnifiedDataClient()
    service = Mock()
    expected = _result("snapshot")
    service.get_sector_snapshot.return_value = expected
    client._sector_service = service

    actual = client.get_sector_snapshot("BK0489", date="2026-07-21")

    service.get_sector_snapshot.assert_called_once_with(
        "BK0489",
        date="2026-07-21",
    )
    assert actual is expected


def test_get_sector_ranking_delegates_and_returns_same_data_result() -> None:
    client = UnifiedDataClient()
    service = Mock()
    expected = _result("ranking")
    service.get_sector_ranking.return_value = expected
    client._sector_service = service

    actual = client.get_sector_ranking(
        date="2026-07-21",
        sector_type="industry",
        limit=7,
    )

    service.get_sector_ranking.assert_called_once_with(
        date="2026-07-21",
        sector_type="industry",
        limit=7,
    )
    assert actual is expected
