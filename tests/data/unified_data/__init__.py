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

Pandas fallback (Phase 1B-A)
----------------------------
The :mod:`skills.data.unified_data.providers` package unconditionally
``import pandas as pd`` at module load time. Some CI / hermes-agent
runner environments do not have ``pandas`` installed. To keep those
test runs green without weakening the Phase 1B-A behaviour contract,
this ``__init__`` installs a minimal :mod:`pandas` stub into
``sys.modules`` **only when the real package is missing**. The stub
exposes a no-op :class:`pandas.DataFrame` constructor plus the
``columns`` accessor the stub DataFrame payloads need.
"""

from __future__ import annotations

import sys
import types


def _ensure_pandas_stub() -> None:
    """Inject a minimal :mod:`pandas` stub when the real package is absent.

    The stub is *only* used by the providers test code paths that ask
    for ``pd.DataFrame(columns=[...])`` and read ``.columns`` /
    ``len()``. Anything more elaborate is unnecessary in 1B-A because
    the providers themselves return empty DataFrames — there is no
    arithmetic, no group-by, no I/O.
    """
    if "pandas" in sys.modules:
        return
    try:
        import pandas  # noqa: F401
        return
    except Exception:
        pass

    pd_stub = types.ModuleType("pandas")

    class _DataFrame:  # minimal subset for the providers stub tests
        def __init__(self, columns=None, data=None):
            self._columns = list(columns or ["data"])
            self._rows = list(data or [])

        @property
        def columns(self):
            return list(self._columns)

        def __len__(self) -> int:  # noqa: D401 - test stub
            return len(self._rows)

    pd_stub.DataFrame = _DataFrame  # type: ignore[attr-defined]
    sys.modules["pandas"] = pd_stub


_ensure_pandas_stub()

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
