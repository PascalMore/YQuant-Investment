"""AKShareProvider — Phase 1B-A stub + Phase 1D ``kline_daily`` activation.

Phase 1B-A shipped AKShareProvider as a stub returning canonical empty
``pd.DataFrame`` shapes for every declared capability. Phase 1D
(DESIGN-03-012) activates the ``market_data.kline_daily`` real call
path while keeping the other 6 capabilities on the stub path.

Activated behaviour (Phase 1D, ``kline_daily`` only):

* Declares the conservative 7-capability subset from SPEC-03-008 §4.5
  (AKShare does not expose ``adj_factor``, the three financial
  statements, ``index_members`` or ``stock_news``).
* Reports availability based on whether the optional ``akshare``
  dependency can be imported. **No token is required** and none is ever
  read (P-10).
* :meth:`fetch` for ``kline_daily``:
  1. Acquires the shared rate limiter (EP-106).
  2. Lazily constructs a default :class:`AKShareKlineClient` on first
     use (http_client=None); a caller-injected :class:`KlineClient` is
     used as-is.
  3. Calls the client which performs the real
     ``ak.stock_zh_a_hist(symbol, period=\"daily\", adjust=\"\")``
     HTTP round-trip and normalises exceptions into
     :class:`ProviderUnavailableError` / :class:`ProviderError`.
  4. Maps the raw Chinese-named DataFrame to ``list[DailyBar]`` via
     :meth:`_to_canonical` (AKShare columns, ``成交量``=股,
     ``成交额``=元). Trade dates are converted from ``YYYY-MM-DD`` to
     ``YYYYMMDD``.
  5. Truncates the list by the requested ``limit`` (``stock_zh_a_hist``
     does not support ``limit`` natively).
  6. Raises :class:`ProviderUnavailableError` on empty payload so the
     Router falls back to the next provider (DESIGN §3.6).

Capability set (7 entries, from SPEC-03-008 §4.5):
    market_data.kline_daily, market_data.kline_weekly,
    market_data.realtime_quote, valuation.daily_basic,
    calendar.trading_days, calendar.is_trading_day, metadata.stock_list
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from ..exceptions import ProviderError, ProviderUnavailableError
from ..models import Market
from ..models.domain.market_data import DailyBar, _f
from .base_external import BaseExternalProvider
from ._stub_columns import stub_dataframe_for
from .kline_client import AKShareKlineClient, KlineClient

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

    from ..models import SecurityId


KLINE_DAILY_CAPABILITY = "market_data.kline_daily"


class AKShareProvider(BaseExternalProvider):
    """AKShare provider with the 7-capability subset (Phase 1D: kline_daily active).

    Args:
        rate_limit_rpm: Per-minute budget (defaults to ``200``). Forwarded
            to :class:`BaseExternalProvider`.
        retry_max_attempts: Forwarded to :class:`BaseExternalProvider`.
        retry_backoff_base: Forwarded to :class:`BaseExternalProvider`.
        http_client: Optional :class:`KlineClient` for the kline_daily
            real call path. ``None`` (default) defers construction of an
            :class:`AKShareKlineClient` to the first ``kline_daily``
            fetch. Tests inject a :class:`FakeKlineClient`.
        request_timeout_seconds: Forwarded to the lazily-constructed
            real client.
        emit_unit_warning: Reserved for future use (Phase 1D no-op).
            AKShare reports volume in 股 and amount in 元; the unit
            warning cannot currently surface through ``DataResult``
            because the Router overwrites ``warnings`` on the external
            success branch. The knob is retained for forward
            compatibility (DESIGN-03-012 §3.7).
    """

    @property
    def name(self) -> str:
        """Stable provider identifier — always ``"akshare"``."""
        return "akshare"

    @property
    def capabilities(self) -> set[str]:
        """7-capability subset per SPEC-03-008 §4.5."""
        return {
            "market_data.kline_daily",
            "market_data.kline_weekly",
            "market_data.realtime_quote",
            "valuation.daily_basic",
            "calendar.trading_days",
            "calendar.is_trading_day",
            "metadata.stock_list",
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
        http_client: KlineClient | None = None,
        request_timeout_seconds: float = 30.0,
        emit_unit_warning: bool = True,
    ) -> None:
        super().__init__(
            rate_limit_rpm=rate_limit_rpm,
            retry_max_attempts=retry_max_attempts,
            retry_backoff_base=retry_backoff_base,
        )
        self._http_client: KlineClient | None = http_client
        self._request_timeout_seconds = request_timeout_seconds
        self._emit_unit_warning = emit_unit_warning

    # ------------------------------------------------------------------
    # Availability (P-10: no token to read)
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return ``True`` iff the optional ``akshare`` package imports.

        AKShare does not require authentication, so availability is
        determined purely by importability of the optional dependency.
        """
        try:  # noqa: SIM105 - import guard is intentional
            import akshare  # type: ignore[import-not-found]  # noqa: F401
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

        Phase 1D activates the ``market_data.kline_daily`` capability
        (see class docstring). Every other capability remains on the
        Phase 1B-A stub path.

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

        # Stub path for the remaining 6 capabilities (EP-103).
        df = stub_dataframe_for(capability)
        return self._to_canonical(df, capability)

    def _fetch_kline_daily(
        self,
        security_id: "SecurityId",
        params: dict[str, Any],
    ) -> list[DailyBar]:
        """Phase 1D kline_daily real call path (see class docstring)."""
        self._rate_limiter.acquire()

        if self._http_client is None:
            self._http_client = AKShareKlineClient(
                timeout=self._request_timeout_seconds,
            )

        start_date = params.get("start_date")
        end_date = params.get("end_date")
        limit = params.get("limit")
        raw_df = self._http_client.get_kline_daily(
            security_id,
            start_date=start_date,
            end_date=end_date,
        )

        bars = self._to_canonical(raw_df, KLINE_DAILY_CAPABILITY)

        # AKShare does not support limit; apply truncation here
        # (DESIGN-03-012 §3.4.2).
        if limit is not None and len(bars) > limit:
            bars = bars[:limit]

        if not bars:
            raise ProviderUnavailableError(
                "akshare kline_daily: empty payload for "
                f"{getattr(security_id, 'canonical', security_id)!r}"
            )
        return bars

    # ------------------------------------------------------------------
    # Canonical mapping (Phase 1D override — DESIGN §3.4.2)
    # ------------------------------------------------------------------

    def _to_canonical(
        self,
        raw_df: "pd.DataFrame",
        capability: str,
    ) -> Any:
        """Dispatch canonical mapping by capability.

        ``market_data.kline_daily`` → ``list[DailyBar]`` (AKShare
        Chinese columns, units: ``成交量``=股, ``成交额``=元). Trade
        dates are converted from ``YYYY-MM-DD`` to ``YYYYMMDD``. Every
        other capability inherits the base no-op behaviour.
        """
        if capability == KLINE_DAILY_CAPABILITY:
            return _akshare_df_to_daily_bars(raw_df)
        return super()._to_canonical(raw_df, capability)


# ---------------------------------------------------------------------------
# AKShare DataFrame → list[DailyBar] mapping (module-level, DESIGN §3.4.2)
# ---------------------------------------------------------------------------


def _akshare_df_to_daily_bars(raw_df: "pd.DataFrame") -> list[DailyBar]:
    """Map an AKShare ``stock_zh_a_hist`` DataFrame to ``list[DailyBar]``.

    Field mapping (DESIGN-03-012 §3.4.2):

    ============== ============== ==================== ===========
    DailyBar       AKShare col    conversion           unit
    ============== ============== ==================== ===========
    symbol         —              security_id.symbol   6-digit
    trade_date     日期            YYYY-MM-DD→YYYYMMDD  YYYYMMDD
    open/high/low  开盘/最高/最低     _f()                 元
    close          收盘            _f()                 元 (key)
    pre_close      —              close-涨跌额         元 (optional)
    change         涨跌额          _f()                 元
    pct_chg        涨跌幅          _f()                 百分比
    volume         成交量          _f()                 股
    amount         成交额          _f()                 元
    turnover_rate  换手率          _f()                 百分比
    volume_ratio   —              None                 —
    ============== ============== ==================== ===========

    Row-level dropping: ``收盘`` (close) or ``日期`` (trade_date)
    empty → row dropped.
    Column-level missing: key columns (``日期``, ``收盘``) →
    :class:`ProviderError`; optional columns → field stays ``None``.
    """
    import pandas as pd  # local import

    if raw_df is None or len(raw_df) == 0:
        return []

    columns = set(raw_df.columns)
    for required in ("日期", "收盘"):
        if required not in columns:
            raise ProviderError(f"missing required column: {required}")

    def _col(name: str) -> pd.Series | None:
        return raw_df[name] if name in columns else None  # type: ignore[return-value]

    trade_date_col = raw_df["日期"]
    close_col = raw_df["收盘"]
    open_col = _col("开盘")
    high_col = _col("最高")
    low_col = _col("最低")
    change_col = _col("涨跌额")
    pct_chg_col = _col("涨跌幅")
    volume_col = _col("成交量")
    amount_col = _col("成交额")
    turnover_col = _col("换手率")

    bars: list[DailyBar] = []
    for idx in range(len(raw_df)):
        trade_date_val = trade_date_col.iloc[idx]
        if trade_date_val is None or str(trade_date_val).strip() == "":
            continue
        close_raw = close_col.iloc[idx]
        close_value = _safe_float_akshare(close_raw, field="收盘")
        if close_value is None:
            continue

        # Convert YYYY-MM-DD to YYYYMMDD (DESIGN §3.4.2).
        trade_date_str = str(trade_date_val).replace("-", "")

        # pre_close = close - 涨跌额 (optional; both entries must be
        # non-None or we leave pre_close as None).
        change_val = _safe_series_value_akshare(change_col, idx)
        pre_close: float | None = None
        if close_value is not None and change_val is not None:
            pre_close = close_value - change_val

        bars.append(
            DailyBar(
                symbol="",  # filled by the Router/consumer from security_id
                trade_date=trade_date_str,
                open=_safe_series_value_akshare(open_col, idx, field="开盘"),
                high=_safe_series_value_akshare(high_col, idx, field="最高"),
                low=_safe_series_value_akshare(low_col, idx, field="最低"),
                close=close_value,
                pre_close=pre_close,
                change=change_val,
                pct_chg=_safe_series_value_akshare(pct_chg_col, idx, field="涨跌幅"),
                volume=_safe_series_value_akshare(volume_col, idx, field="成交量"),
                amount=_safe_series_value_akshare(amount_col, idx, field="成交额"),
                turnover_rate=_safe_series_value_akshare(
                    turnover_col, idx, field="换手率"
                ),
                volume_ratio=None,
            )
        )
    return bars


def _safe_float_akshare(value: Any, *, field: str) -> float | None:
    """Coerce a raw cell to ``float`` following ``_f()`` semantics."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        return _f(value, field=field)
    except (ValueError, TypeError) as exc:
        raise ProviderError(
            f"akshare kline_daily: non-numeric {field}: {exc}"
        ) from exc


def _safe_series_value_akshare(
    series: Any,
    idx: int,
    *,
    field: str = "value",
) -> float | None:
    """Read ``series.iloc[idx]`` defensively and coerce via ``_safe_float_akshare``."""
    if series is None:
        return None
    try:
        value = series.iloc[idx]
    except (IndexError, KeyError):
        return None
    return _safe_float_akshare(value, field=field)


__all__ = ["AKShareProvider"]
