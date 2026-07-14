"""TushareProvider — Phase 1B-A stub.

Phase 1B-A does **not** perform real Tushare HTTP calls. The provider:

* Declares the conservative 13-capability set from SPEC-03-008 §4.5.
* Reports availability based on the presence of the ``TUSHARE_TOKEN``
  environment variable **and** importability of the optional ``tushare``
  dependency. **No token value is ever read, stored, logged or
  returned** — only the presence/non-emptiness is checked (P-10).
* :meth:`fetch` returns the canonical stub ``pd.DataFrame`` defined in
  :mod:`skills.data.unified_data.providers`. Real API integration is
  scheduled for Phase 1B-B.

Capability set (13 entries, from SPEC-03-008 §4.5):
    market_data.kline_daily, market_data.kline_weekly,
    market_data.realtime_quote, market_data.adj_factor,
    financial.income_statement, financial.balance_sheet,
    financial.cash_flow, valuation.daily_basic,
    calendar.trading_days, calendar.is_trading_day,
    metadata.stock_list, metadata.index_members, news.stock_news
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from ..models import Market
from .base_external import BaseExternalProvider
from ._stub_columns import stub_dataframe_for

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

    from ..models import SecurityId


# Environment variable whose **presence** is required for ``is_available``
# to return ``True``. The variable name is configurable via the constructor
# to keep tests deterministic, but defaults to ``"TUSHARE_TOKEN"``.
DEFAULT_TOKEN_ENV = "TUSHARE_TOKEN"


class TushareProvider(BaseExternalProvider):
    """Stub Tushare provider with the 13-capability set.

    Args:
        rate_limit_rpm: Per-minute budget (defaults to ``200``). Forwarded
            to :class:`BaseExternalProvider`.
        retry_max_attempts: Forwarded to :class:`BaseExternalProvider`.
        retry_backoff_base: Forwarded to :class:`BaseExternalProvider`.
        token_env: Override the environment variable name. Tests use
            this to point at a fixture variable without leaking real
            tokens.
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
    ) -> None:
        super().__init__(
            rate_limit_rpm=rate_limit_rpm,
            retry_max_attempts=retry_max_attempts,
            retry_backoff_base=retry_backoff_base,
        )
        self._token_env = token_env

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
    # Fetch (stub)
    # ------------------------------------------------------------------

    def fetch(
        self,
        domain: str,
        operation: str,
        security_id: "SecurityId",
        **params: Any,
    ) -> "pd.DataFrame":
        """Return the stub ``pd.DataFrame`` for ``domain.operation``.

        Phase 1B-A does **not** perform any network I/O — see module
        docstring. Real HTTP integration lands in Phase 1B-B.

        Raises:
            UnsupportedCapabilityError: When the requested capability
                is not in :attr:`capabilities`.
        """
        capability = self._check_capability(domain, operation)
        df = stub_dataframe_for(capability)
        return self._to_canonical(df, capability)


__all__ = ["TushareProvider", "DEFAULT_TOKEN_ENV"]