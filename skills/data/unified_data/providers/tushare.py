"""TushareProvider — Phase 1B-A stub + Phase 1D ``kline_daily`` activation.

Phase 1B-A shipped TushareProvider as a stub returning canonical empty
``pd.DataFrame`` shapes for every declared capability. Phase 1D
(DESIGN-03-012) activates the ``market_data.kline_daily`` real call
path while keeping the other 12 capabilities on the stub path.

Activated behaviour (Phase 1D, ``kline_daily`` only):

* Declares the conservative 13-capability set from SPEC-03-008 §4.5.
* Reports availability based on the presence of the ``TUSHARE_TOKEN``
  environment variable **and** importability of the optional
  ``tushare`` dependency. **No token value is ever read, stored, logged
  or returned** — only the presence/non-emptiness is checked (P-10).
* :meth:`fetch` for ``kline_daily``:
  1. Acquires the shared rate limiter (EP-106).
  2. Lazily constructs a default :class:`TushareKlineClient` on first
     use (http_client=None) using the token read from the environment;
     a caller-injected :class:`KlineClient` is used as-is.
  3. Calls the client which performs the real ``pro_api(token).daily``
     HTTP round-trip and normalises exceptions into
     :class:`ProviderUnavailableError` / :class:`ProviderError`.
  4. Maps the raw DataFrame to ``list[DailyBar]`` via
     :meth:`_to_canonical` (Tushare columns, ``vol``=手, ``amount``=千元).
  5. Raises :class:`ProviderUnavailableError` on empty payload so the
     Router falls back to the next provider (DESIGN §3.6 — Router's
     ``is not None`` check would otherwise treat ``[]`` as success).

Capability set (13 entries, from SPEC-03-008 §4.5):
    market_data.kline_daily, market_data.kline_weekly,
    market_data.realtime_quote, market_data.adj_factor,
    financial.income_statement, financial.balance_sheet,
    financial.cash_flow, valuation.daily_basic,
    calendar.trading_days, calendar.is_trading_day,
    metadata.stock_list, metadata.index_members, news.stock_news
"""

from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING, Any

from ..exceptions import ProviderError, ProviderUnavailableError
from ..models import Market
from ..models.domain.market_data import DailyBar, _f
from .base_external import BaseExternalProvider
from ._stub_columns import stub_dataframe_for
from .kline_client import KlineClient, TushareKlineClient

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

    from ..models import SecurityId


# Environment variable whose **presence** is required for ``is_available``
# to return ``True``. The variable name is configurable via the constructor
# to keep tests deterministic, but defaults to ``"TUSHARE_TOKEN"``.
DEFAULT_TOKEN_ENV = "TUSHARE_TOKEN"

KLINE_DAILY_CAPABILITY = "market_data.kline_daily"


class TushareProvider(BaseExternalProvider):
    """Tushare provider with the 13-capability set (Phase 1D: kline_daily active).

    Args:
        rate_limit_rpm: Per-minute budget (defaults to ``200``). Forwarded
            to :class:`BaseExternalProvider`.
        retry_max_attempts: Forwarded to :class:`BaseExternalProvider`.
        retry_backoff_base: Forwarded to :class:`BaseExternalProvider`.
        token_env: Override the environment variable name. Tests use
            this to point at a fixture variable without leaking real
            tokens.
        http_client: Optional :class:`KlineClient` for the kline_daily
            real call path. ``None`` (default) defers construction of a
            :class:`TushareKlineClient` to the first ``kline_daily``
            fetch — and skips it entirely when ``is_available()`` is
            False. Tests inject a :class:`FakeKlineClient`.
        request_timeout_seconds: Forwarded to the lazily-constructed
            real client.
        emit_unit_warning: Reserved for future use (Phase 1D no-op).
            Tushare reports volume in 手 and amount in 千元; the unit
            warning cannot currently surface through ``DataResult``
            because the Router overwrites ``warnings`` on the external
            success branch. The knob is retained for forward
            compatibility (DESIGN-03-012 §3.7).
    """

    @property
    def name(self) -> str:
        """Stable provider identifier — always ``"tushare"``."""
        return "tushare"

    @property
    def capabilities(self) -> set[str]:
        """13-capability set per SPEC-03-008 §4.5."""
        return {
            "market_data.kline_daily",
            "market_data.kline_weekly",
            "market_data.realtime_quote",
            "market_data.adj_factor",
            "financial.income_statement",
            "financial.balance_sheet",
            "financial.cash_flow",
            "valuation.daily_basic",
            "calendar.trading_days",
            "calendar.is_trading_day",
            "metadata.stock_list",
            "metadata.index_members",
            "news.stock_news",
        }

    @property
    def markets(self) -> set[Market]:
        """Markets this provider covers — A-shares only."""
        return {Market.CN}

    def __init__(
        self,
        *,
        rate_limit_rpm: int = 200,
        retry_max_attempts: int = 3,
        retry_backoff_base: float = 1.0,
        token_env: str = DEFAULT_TOKEN_ENV,
        http_client: KlineClient | None = None,
        request_timeout_seconds: float = 30.0,
        emit_unit_warning: bool = True,
    ) -> None:
        super().__init__(
            rate_limit_rpm=rate_limit_rpm,
            retry_max_attempts=retry_max_attempts,
            retry_backoff_base=retry_backoff_base,
        )
        self._token_env = token_env
        self._http_client: KlineClient | None = http_client
        self._request_timeout_seconds = request_timeout_seconds
        self._emit_unit_warning = emit_unit_warning

    # ------------------------------------------------------------------
    # Availability (P-10: never read or return the token value)
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return ``True`` iff ``TUSHARE_TOKEN`` (or override) is set.

        The check is purely structural: presence **and** non-emptiness
        of the environment variable, plus importability of the optional
        ``tushare`` package. The token's value is never inspected,
        copied, or returned.
        """
        raw = os.environ.get(self._token_env, "")
        if not raw.strip():
            return False
        try:  # noqa: SIM105 - import guard is intentional
            import tushare  # type: ignore[import-not-found]  # noqa: F401
        except Exception:
            return False
        return True

    # ------------------------------------------------------------------
    # Fetch (Phase 1D: kline_daily real path + stub for the rest)
    # ------------------------------------------------------------------

    def fetch(
        self,
        domain: str,
        operation: str,
        security_id: "SecurityId",
        **params: Any,
    ) -> "pd.DataFrame" | list[DailyBar]:
        """Return data for ``domain.operation``.

        Phase 1D activates the ``market_data.kline_daily`` capability:
        the call goes through the (injectable) :class:`KlineClient`,
        the raw DataFrame is mapped to ``list[DailyBar]`` via
        :meth:`_to_canonical`, and empty payloads raise
        :class:`ProviderUnavailableError` so the Router falls back
        (DESIGN-03-012 §3.6).

        Every other capability remains on the Phase 1B-A stub path —
        it returns the canonical empty ``pd.DataFrame`` defined in
        :mod:`._stub_columns` and performs no network I/O.

        Raises:
            UnsupportedCapabilityError: When the requested capability
                is not in :attr:`capabilities`.
            ProviderUnavailableError: kline_daily path: client
                unavailable / network / timeout / empty payload.
            ProviderError: kline_daily path: API internal error /
                missing required column / non-numeric cell.
        """
        capability = self._check_capability(domain, operation)

        if capability == KLINE_DAILY_CAPABILITY:
            return self._fetch_kline_daily(security_id, params)

        # Stub path for the remaining 12 capabilities (EP-103).
        df = stub_dataframe_for(capability)
        return self._to_canonical(df, capability)

    def _fetch_kline_daily(
        self,
        security_id: "SecurityId",
        params: dict[str, Any],
    ) -> list[DailyBar]:
        """Phase 1D kline_daily real call path (see class docstring)."""
        # EP-106: rate limiting before any real network call.
        self._rate_limiter.acquire()

        # Lazy default-client construction (DESIGN §3.3.5). Only
        # happens on the first kline_daily fetch, never when
        # ``is_available()`` is False (the Router short-circuits
        # unavailable providers before calling fetch).
        if self._http_client is None:
            token = os.environ.get(self._token_env, "")
            self._http_client = TushareKlineClient(
                token=token,
                timeout=self._request_timeout_seconds,
            )

        start_date = params.get("start_date")
        end_date = params.get("end_date")
        limit = params.get("limit")
        raw_df = self._http_client.get_kline_daily(
            security_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

        bars = self._to_canonical(raw_df, KLINE_DAILY_CAPABILITY)
        if not bars:
            # DESIGN §3.6 — Router L809 ``is not None`` would treat
            # ``[]`` as success and skip fallback. Raise instead so the
            # Router records an ``unavailable`` trace and continues.
            raise ProviderUnavailableError(
                "tushare kline_daily: empty payload for "
                f"{getattr(security_id, 'canonical', security_id)!r}"
            )
        return bars

    # ------------------------------------------------------------------
    # Canonical mapping (Phase 1D override — DESIGN §3.4.1)
    # ------------------------------------------------------------------

    def _to_canonical(
        self,
        raw_df: "pd.DataFrame",
        capability: str,
    ) -> Any:
        """Dispatch canonical mapping by capability.

        ``market_data.kline_daily`` → ``list[DailyBar]`` (Tushare
        columns, units: ``vol``=手, ``amount``=千元). Every other
        capability inherits the base no-op behaviour (returns the stub
        DataFrame unchanged).
        """
        if capability == KLINE_DAILY_CAPABILITY:
            return _tushare_df_to_daily_bars(raw_df)
        return super()._to_canonical(raw_df, capability)


# ---------------------------------------------------------------------------
# Tushare DataFrame → list[DailyBar] mapping (module-level, DESIGN §3.4.1)
# ---------------------------------------------------------------------------


def _tushare_df_to_daily_bars(raw_df: "pd.DataFrame") -> list[DailyBar]:
    """Map a Tushare ``daily`` DataFrame to ``list[DailyBar]``.

    Field mapping (DESIGN-03-012 §3.4.1):

    ============== ============= =========== ===========
    DailyBar       Tushare col   conversion  unit
    ============== ============= =========== ===========
    symbol         ts_code       strip suffix 6-digit
    trade_date     trade_date    passthrough YYYYMMDD
    open/high/low  open/high/low _f()        元
    close          close         _f()        元 (key)
    pre_close      pre_close     _f()        元
    change         change        _f()        元
    pct_chg        pct_chg       _f()        百分比(×100)
    volume         vol           _f()        手
    amount         amount        _f()        千元
    turnover_rate  —             None        —
    volume_ratio   —             None        —
    ============== ============= =========== ===========

    Row-level dropping: ``close`` or ``trade_date`` empty → row dropped.
    Column-level missing: key columns (``ts_code``, ``trade_date``,
    ``close``) → :class:`ProviderError`; optional columns → field stays
    ``None``.
    """
    import pandas as pd  # local import keeps module-level surface lean

    if raw_df is None or len(raw_df) == 0:
        return []

    columns = set(raw_df.columns)
    for required in ("ts_code", "trade_date", "close"):
        if required not in columns:
            raise ProviderError(f"missing required column: {required}")

    def _col(name: str) -> pd.Series | None:
        return raw_df[name] if name in columns else None

    ts_code_col = raw_df["ts_code"]
    trade_date_col = raw_df["trade_date"]
    close_col = raw_df["close"]
    open_col = _col("open")
    high_col = _col("high")
    low_col = _col("low")
    pre_close_col = _col("pre_close")
    change_col = _col("change")
    pct_chg_col = _col("pct_chg")
    vol_col = _col("vol")
    amount_col = _col("amount")

    bars: list[DailyBar] = []
    for idx in range(len(raw_df)):
        trade_date_val = trade_date_col.iloc[idx]
        if trade_date_val is None or str(trade_date_val).strip() == "":
            continue  # row drop — trade_date empty
        close_raw = close_col.iloc[idx]
        close_value = _safe_float(close_raw, field="close")
        if close_value is None:
            continue  # row drop — close empty (key field)

        ts_code_raw = ts_code_col.iloc[idx]
        symbol = str(ts_code_raw).split(".", 1)[0] if ts_code_raw is not None else ""

        bars.append(
            DailyBar(
                symbol=symbol,
                trade_date=str(trade_date_val),
                open=_safe_series_value(open_col, idx, field="open"),
                high=_safe_series_value(high_col, idx, field="high"),
                low=_safe_series_value(low_col, idx, field="low"),
                close=close_value,
                pre_close=_safe_series_value(pre_close_col, idx, field="pre_close"),
                change=_safe_series_value(change_col, idx, field="change"),
                pct_chg=_safe_series_value(pct_chg_col, idx, field="pct_chg"),
                volume=_safe_series_value(vol_col, idx, field="volume"),
                amount=_safe_series_value(amount_col, idx, field="amount"),
                turnover_rate=None,  # daily endpoint does not provide it
                volume_ratio=None,
            )
        )
    return bars


def _safe_float(value: Any, *, field: str) -> float | None:
    """Coerce a raw cell to ``float`` following ``_f()`` semantics.

    None / NaN / empty string → None. Non-numeric → :class:`ProviderError`
    (wraps the ``ValueError`` raised by ``_f`` so the Router records
    this as a provider error rather than letting it escape).
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        return _f(value, field=field)
    except ValueError as exc:
        raise ProviderError(f"tushare kline_daily: non-numeric {field}: {exc}") from exc
    except TypeError as exc:
        raise ProviderError(
            f"tushare kline_daily: unsupported type for {field}: {exc}"
        ) from exc


def _safe_series_value(
    series: Any,
    idx: int,
    *,
    field: str,
) -> float | None:
    """Read ``series.iloc[idx]`` defensively and coerce via ``_safe_float``."""
    if series is None:
        return None
    try:
        value = series.iloc[idx]
    except (IndexError, KeyError):
        return None
    return _safe_float(value, field=field)


__all__ = ["TushareProvider", "DEFAULT_TOKEN_ENV"]
