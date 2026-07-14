"""AKShareProvider — Phase 1B-A stub.

Phase 1B-A does **not** perform real AKShare HTTP calls. The provider:

* Declares the conservative 7-capability subset from SPEC-03-008 §4.5
  (AKShare does not expose ``adj_factor``, the three financial
  statements, ``index_members`` or ``stock_news``).
* Reports availability based on whether the optional ``akshare``
  dependency can be imported. **No token is required** and none is ever
  read (P-10).
* :meth:`fetch` returns the canonical stub ``pd.DataFrame`` defined in
  :mod:`skills.data.unified_data.providers`. Real API integration is
  scheduled for Phase 1B-B.

Capability set (7 entries, from SPEC-03-008 §4.5):
    market_data.kline_daily, market_data.kline_weekly,
    market_data.realtime_quote, valuation.daily_basic,
    calendar.trading_days, calendar.is_trading_day, metadata.stock_list
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models import Market
from .base_external import BaseExternalProvider
from ._stub_columns import stub_dataframe_for

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

    from ..models import SecurityId


class AKShareProvider(BaseExternalProvider):
    """Stub AKShare provider with the 7-capability subset.

    Args:
        rate_limit_rpm: Per-minute budget (defaults to ``200``). Forwarded
            to :class:`BaseExternalProvider`.
        retry_max_attempts: Forwarded to :class:`BaseExternalProvider`.
        retry_backoff_base: Forwarded to :class:`BaseExternalProvider`.
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
    ) -> None:
        super().__init__(
            rate_limit_rpm=rate_limit_rpm,
            retry_max_attempts=retry_max_attempts,
            retry_backoff_base=retry_backoff_base,
        )

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


__all__ = ["AKShareProvider"]