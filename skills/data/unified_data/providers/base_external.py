"""Abstract base class for external providers (Phase 1B-A).

External providers in Phase 1B-A do **not** call any real network API.
Their :meth:`fetch` returns a pre-defined stub ``pd.DataFrame`` (see
:data:`skills.data.unified_data.providers.STUB_COLUMNS`). The base class
exists to give TushareProvider / AKShareProvider a uniform surface for
future real-API work:

* Owns a :class:`RateLimiter` instance so subclasses do not duplicate
  the throttling state.
* Exposes :meth:`_check_capability` so subclasses can validate the
  requested capability at the top of :meth:`fetch` without re-implementing
  the boilerplate.
* Exposes :meth:`_to_canonical` as a hook for the eventual
  ``pd.DataFrame → canonical domain object`` transformation (Phase 1B-B).
  In 1B-A it is a no-op stub returning ``raw_df`` unchanged.

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
    """Common base for Phase 1B-A stub providers.

    Concrete subclasses must still implement :attr:`name`,
    :attr:`capabilities`, :attr:`markets`, :meth:`is_available` and
    :meth:`fetch`. They inherit:

    * ``self._rate_limiter`` — a :class:`RateLimiter` configured for the
      subclass's expected traffic profile. Use ``self._rate_limiter.acquire()``
      before performing a real API call (no-op in 1B-A).
    * :meth:`_check_capability` — wraps :meth:`DataProvider._assert_capability`
      to validate the requested capability at the top of :meth:`fetch`.
    * :meth:`_to_canonical` — Phase 1B-B hook for converting raw provider
      payloads into canonical domain objects. Phase 1B-A returns the
      raw DataFrame unchanged.
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
    ) -> "pd.DataFrame":
        """Hook for converting raw provider payloads to canonical objects.

        Phase 1B-A is a stub: this method returns ``raw_df`` unchanged.
        Phase 1B-B is expected to override this in subclasses (or in a
        dedicated transformer module) to perform the actual
        ``pd.DataFrame`` → canonical mapping.
        """
        return raw_df


__all__ = ["BaseExternalProvider"]