"""Abstract base class for external providers (Phase 1D).

External providers in Phase 1B-A did not perform real network I/O —
their :meth:`fetch` returned pre-defined stub ``pd.DataFrame`` shapes
(see :data:`skills.data.unified_data.providers.STUB_COLUMNS`). Phase 1D
activates the ``market_data.kline_daily`` real call path for Tushare /
AKShare via an injectable :class:`~.kline_client.KlineClient`; all
other capabilities remain stubs.

The base class exists to give TushareProvider / AKShareProvider a
uniform surface:

* Owns a :class:`RateLimiter` instance so subclasses do not duplicate
  the throttling state.
* Exposes :meth:`_check_capability` so subclasses can validate the
  requested capability at the top of :meth:`fetch` without
  re-implementing the boilerplate.
* Exposes :meth:`_to_canonical` as a hook for the
  ``pd.DataFrame → canonical domain object`` transformation. The base
  implementation is a no-op stub returning ``raw_df`` unchanged; Phase
  1D subclasses override it for ``kline_daily`` (returning
  ``list[DailyBar]``) while leaving the no-op intact for any future
  capability that has not yet implemented canonical mapping.

Security (P-10):
    Subclasses are explicitly reminded in their module-level docstrings
    that ``is_available()`` must never read or print a credential value.
    The base class itself does not touch any environment variable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..provider import DataProvider
from .rate_limiter import RateLimiter

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    import pandas as pd


class BaseExternalProvider(DataProvider):
    """Common base for external providers (Phase 1B-A stubs + Phase 1D activation).

    Concrete subclasses must still implement :attr:`name`,
    :attr:`capabilities`, :attr:`markets`, :meth:`is_available` and
    :meth:`fetch`. They inherit:

    * ``self._rate_limiter`` — a :class:`RateLimiter` configured for the
      subclass's expected traffic profile. Use ``self._rate_limiter.acquire()``
      before performing a real API call (no-op for stub paths).
    * :meth:`_check_capability` — wraps :meth:`DataProvider._assert_capability`
      to validate the requested capability at the top of :meth:`fetch`.
    * :meth:`_to_canonical` — hook for converting raw provider payloads
      into canonical domain objects. The base implementation is a no-op
      that returns ``raw_df`` unchanged; Phase 1D subclasses override it
      for ``kline_daily`` (returning ``list[DailyBar]``). The base no-op
      is retained so that any future capability without a mapping falls
      through safely rather than crashing.
    """

    def __init__(
        self,
        *,
        rate_limit_rpm: int = 200,
        retry_max_attempts: int = 3,
        retry_backoff_base: float = 1.0,
    ) -> None:
        """Initialise the shared rate limiter / retry policy knobs.

        Args:
            rate_limit_rpm: Per-minute request budget for
                :attr:`_rate_limiter`. Defaults to ``200`` (Tushare
                free-tier guideline).
            retry_max_attempts: Soft upper bound — exposed here so the
                ``with_retry`` decorator can be configured at the call
                site without subclass surgery.
            retry_backoff_base: Back-off base (seconds) for retries.
        """
        super().__init__()
        self._rate_limiter = RateLimiter(max_per_minute=rate_limit_rpm)
        self._retry_max_attempts = retry_max_attempts
        self._retry_backoff_base = retry_backoff_base

    # ------------------------------------------------------------------
    # Capability / canonical helpers (used by subclasses)
    # ------------------------------------------------------------------

    def _check_capability(self, domain: str, operation: str) -> str:
        """Validate the requested capability and return its canonical name.

        Thin wrapper around :meth:`DataProvider._assert_capability` so
        subclasses have a single hook to call. Raises
        :class:`UnsupportedCapabilityError` when the capability is not
        in :attr:`capabilities`.
        """
        return self._assert_capability(domain, operation)

    def _to_canonical(
        self,
        raw_df: "pd.DataFrame",
        capability: str,
    ) -> Any:
        """Hook for converting raw provider payloads to canonical objects.

        The base implementation is a **no-op** that returns ``raw_df``
        unchanged — this preserves a safe default for any capability
        that has not yet implemented canonical mapping (every capability
        except ``market_data.kline_daily`` in Phase 1D).

        Phase 1D subclasses override this method **in their own class
        body** (the base method is deliberately not modified) and
        dispatch on ``capability`` so they can return
        ``list[DailyBar]`` for ``kline_daily`` while leaving all other
        capabilities on the stub path.

        Returns:
            ``pd.DataFrame`` for stub capabilities (the raw input
            unchanged); ``list[DailyBar]`` (or any canonical type) for
            activated capabilities in subclasses.
        """
        return raw_df


__all__ = ["BaseExternalProvider"]