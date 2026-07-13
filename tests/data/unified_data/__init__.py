"""Test package for unified_data Phase 0 skeleton + Phase 1A.

Located under ``tests/data/unified_data/`` to mirror the
``skills/data/unified_data/`` layout. Tests rely exclusively on fake /
mock providers — no real MongoDB, no real external API calls.

This package also exposes :class:`FakeTA_CNMongoAdapter` — a tiny
test-only mock that lets each test override exactly one adapter method
while still being a structural :class:`TA_CNMongoAdapter` subclass. It
is consolidated here (instead of a separate ``_fakes.py`` module) so
the T2 file plan's single test-package entry point remains the
canonical location.
"""

from __future__ import annotations

from typing import Any

from skills.data.unified_data import TA_CNMongoAdapter


class FakeTA_CNMongoAdapter(TA_CNMongoAdapter):
    """Mock adapter that lets each test override exactly one method.

    Each non-overridden method returns ``None`` / ``[]`` (the "empty"
    signal); tests call :meth:`set_payload` or :meth:`set_error` to
    configure per-method behavior, then assert the *correct* provider /
    freshness / ``source_trace`` wrapping occurred.

    Usage::

        adapter = FakeTA_CNMongoAdapter()
        adapter.set_payload("get_realtime_quotes", {"current_price": 1.0})
        result = client.get_realtime_quote(sid)
    """

    def __init__(self) -> None:
        super().__init__(db={})
        self._payloads: dict[str, Any] = {}
        self._errors: dict[str, BaseException] = {}
        self.call_log: list[tuple[str, tuple]] = []

    def set_payload(self, method: str, value: Any) -> None:
        self._payloads[method] = value

    def set_error(self, method: str, exc: BaseException) -> None:
        self._errors[method] = exc

    def _log(self, name: str, args: tuple) -> Any:
        self.call_log.append((name, args))
        if name in self._errors:
            raise self._errors[name]
        return self._payloads.get(name)

    # -- stock_basic_info --
    def get_stock_info(self, symbol, market="CN"):  # type: ignore[override]
        return self._log("get_stock_info", (symbol, market))

    def get_stock_list(self, market="CN", status="L", limit=0):  # type: ignore[override]
        return self._log("get_stock_list", (market, status, limit))

    # -- market_quotes --
    def get_realtime_quotes(self, symbol):  # type: ignore[override]
        return self._log("get_realtime_quotes", (symbol,))

    # -- stock_daily_quotes --
    def get_daily_bars(self, symbol, start_date=None, end_date=None, limit=120):  # type: ignore[override]
        return self._log("get_daily_bars", (symbol, start_date, end_date, limit))

    # -- stock_financial_data --
    def get_financials(self, symbol, report_period=None):  # type: ignore[override]
        return self._log("get_financials", (symbol, report_period))

    # -- stock_news --
    def get_news(self, symbol, limit=20):  # type: ignore[override]
        return self._log("get_news", (symbol, limit))

    # -- index_basic_info --
    def get_index_info(self, symbol):  # type: ignore[override]
        return self._log("get_index_info", (symbol,))

    def get_index_list(self, market="CN"):  # type: ignore[override]
        return self._log("get_index_list", (market,))

    # -- index_daily_quotes --
    def get_index_daily_bars(  # type: ignore[override]
        self, symbol=None, sector_code=None, start_date=None, end_date=None, limit=120,
    ):
        return self._log(
            "get_index_daily_bars", (symbol, sector_code, start_date, end_date, limit),
        )

    # -- stock_sector_info --
    def get_stock_sector_info(self, full_symbol, classify_system=None):  # type: ignore[override]
        return self._log("get_stock_sector_info", (full_symbol, classify_system))

    def get_stocks_by_sector(self, l1_code, classify_system="SW"):  # type: ignore[override]
        return self._log("get_stocks_by_sector", (l1_code, classify_system))


__all__ = ["FakeTA_CNMongoAdapter"]
