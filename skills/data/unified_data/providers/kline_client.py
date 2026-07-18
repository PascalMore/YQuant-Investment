"""Kline HTTP client abstraction for Phase 1D external provider activation.

This module ships four cooperating types that together implement the
``market_data.kline_daily`` real call path for the Tushare / AKShare
providers:

* :class:`KlineClient` — a ``typing.Protocol`` describing the structural
  contract every concrete client must satisfy. Protocol (not ABC) is
  used on purpose so the three implementations below are structurally
  typed without forcing an explicit inheritance relationship.
* :class:`FakeKlineClient` — test-only stand-in. Records every call in
  ``call_log`` and returns either a canned ``DataFrame`` or raises a
  configured exception. Never reads the environment and never performs
  any I/O.
* :class:`TushareKlineClient` — production Tushare client. Imports the
  optional ``tushare`` dependency lazily inside ``get_kline_daily`` so
  the module stays importable when the SDK is absent. Token is injected
  via the constructor and is never printed, logged, or echoed in
  exception messages (P-10).
* :class:`AKShareKlineClient` — production AKShare client. Also lazily
  imports ``akshare``. No token required.

All real SDK imports live inside the respective ``get_kline_daily``
methods. The module-level surface has zero third-party imports beyond
``pandas`` (which is already a hard dependency of the package).

Security (P-10):
    Real clients normalise every SDK exception into one of
    :class:`ProviderUnavailableError` / :class:`ProviderError`. Messages
    deliberately describe only the *category* of failure (network,
    quota, API error) and never embed the token or any other
    credential.

Design reference: DESIGN-03-012 §3.3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import pandas as pd

from ..exceptions import ProviderError, ProviderUnavailableError

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from ..models import SecurityId


# ---------------------------------------------------------------------------
# KlineClient Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class KlineClient(Protocol):
    """Injectable kline_daily HTTP client abstraction (Phase 1D).

    Three implementations satisfy this protocol:

    * :class:`FakeKlineClient` — test fixture, no environment, no I/O.
    * :class:`TushareKlineClient` — production, lazy-imports ``tushare``,
      calls ``pro_api(token).daily(...)``.
    * :class:`AKShareKlineClient` — production, lazy-imports ``akshare``,
      calls ``stock_zh_a_hist(adjust="")``.

    Date arguments follow the **unified** ``YYYYMMDD`` format (no
    hyphens) so the canonical :class:`~skills.data.unified_data.models.domain.DailyBar`
    ``trade_date`` is produced consistently regardless of the upstream
    provider's native format.

    Implementations must raise:

    * :class:`ProviderUnavailableError` for network/quota/timeout-style
      failures (so the Router can transparently fall back to the next
      provider in the chain).
    * :class:`ProviderError` for API-internal failures.
    """

    def get_kline_daily(
        self,
        security_id: Any,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Return the provider-native DataFrame for the requested kline.

        Raises:
            ProviderUnavailableError: network/timeout/quota/empty payload.
            ProviderError: API internal error / missing required columns.
        """
        ...


# ---------------------------------------------------------------------------
# FakeKlineClient (test fixture)
# ---------------------------------------------------------------------------


class FakeKlineClient:
    """Test-only :class:`KlineClient` implementation.

    Construct with either a canned ``DataFrame`` (returned on every
    call) or an ``exception`` (raised on every call). Records every
    invocation in ``call_log`` so tests can assert on call arguments.

    The fake never reads the environment, never imports the real SDK,
    and never performs I/O. It is the canonical injection point for the
    Phase 1D provider unit tests.
    """

    def __init__(
        self,
        *,
        dataframe: pd.DataFrame | None = None,
        exception: BaseException | None = None,
    ) -> None:
        self._df = dataframe
        self._exc = exception
        self.call_log: list[dict[str, Any]] = []

    def get_kline_daily(
        self,
        security_id: Any,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        self.call_log.append(
            {
                "security_id": security_id,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
            }
        )
        if self._exc is not None:
            raise self._exc
        if self._df is None:
            return pd.DataFrame()
        return self._df.copy()


# ---------------------------------------------------------------------------
# Production clients (lazy SDK import)
# ---------------------------------------------------------------------------


def _security_id_to_tushare_ts_code(security_id: Any) -> str:
    """Return the Tushare ``ts_code`` form for ``security_id``.

    Reuses :meth:`SecurityId.to_tushare_code` when available so the
    conversion has a single source of truth. Falls back to a defensive
    error for non-:class:`SecurityId` inputs (tests that inject bare
    objects should route through the fake client instead).
    """
    ts_code = getattr(security_id, "to_tushare_code", None)
    if ts_code is None:
        raise ProviderError(
            "tushare kline_daily requires a SecurityId with to_tushare_code"
        )
    resolved = ts_code()
    if not resolved:
        raise ProviderUnavailableError(
            "tushare kline_daily: cannot resolve ts_code for security_id"
        )
    return resolved


class TushareKlineClient:
    """Production Tushare kline_daily client (lazy SDK import).

    The Tushare token is constructor-injected by the provider (which
    reads it from the environment). The client never reads the
    environment itself, never logs the token, and normalises every SDK
    exception to one of :class:`ProviderUnavailableError` /
    :class:`ProviderError` with a category-only message.
    """

    def __init__(self, token: str, *, timeout: float = 30.0) -> None:
        if not token or not token.strip():
            raise ProviderUnavailableError("tushare token missing")
        self._token = token
        self._timeout = timeout

    def get_kline_daily(
        self,
        security_id: Any,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        import tushare as ts  # type: ignore[import-not-found]  # lazy import

        ts_code = _security_id_to_tushare_ts_code(security_id)
        kwargs: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        if limit:
            kwargs["limit"] = limit
        try:
            pro = ts.pro_api(self._token)
            df = pro.daily(**kwargs)
        except Exception as exc:
            self._raise_classified("tushare", exc)
            # _raise_classified always raises; following lines are unreachable
            raise  # pragma: no cover
        return df if df is not None else pd.DataFrame()

    @staticmethod
    def _raise_classified(provider: str, exc: Exception) -> None:
        """Normalise an SDK exception into Provider*Error (P-10).

        The message is deliberately category-only; the raw exception is
        chained via ``from exc`` so debug builds can still inspect it
        without leaking credentials through the surfaced string.

        Connection-level failures (EOF, SSL/TLS, remote disconnect,
        connection reset, broken pipe) are classified as
        :class:`ProviderUnavailableError` via both keyword matching
        and ``isinstance(exc, ConnectionError)`` so the Router can
        transparently fall back.
        """
        msg = str(exc).lower()
        if (
            any(
                keyword in msg
                for keyword in (
                    "quota",
                    "limit",
                    "timeout",
                    "connection",
                    "network",
                    "eof",
                    "ssl",
                    "tls",
                    "disconnect",
                    "connection reset",
                    "broken pipe",
                )
            )
            or isinstance(exc, ConnectionError)
        ):
            raise ProviderUnavailableError(
                f"{provider} API unavailable"
            ) from exc
        raise ProviderError(f"{provider} daily API error") from exc


class AKShareKlineClient:
    """Production AKShare kline_daily client (lazy SDK import).

    AKShare is token-less, so construction takes only an optional
    timeout. ``stock_zh_a_hist`` does not support a ``limit`` argument,
    so ``limit`` is accepted by this method but ignored here — the
    provider's canonical mapping is responsible for truncating the
    resulting ``list[DailyBar]`` (DESIGN-03-012 §3.4.2).
    """

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def get_kline_daily(
        self,
        security_id: Any,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,  # noqa: ARG002 - ignored (see class docstring)
    ) -> pd.DataFrame:
        import akshare as ak  # type: ignore[import-not-found]  # lazy import

        symbol = getattr(security_id, "symbol", None)
        if not symbol:
            raise ProviderError(
                "akshare kline_daily requires a security_id with a symbol"
            )
        kwargs: dict[str, Any] = {
            "symbol": symbol,
            "period": "daily",
            "adjust": "",
        }
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        try:
            df = ak.stock_zh_a_hist(**kwargs)
        except Exception as exc:
            TushareKlineClient._raise_classified("akshare", exc)
            raise  # pragma: no cover
        return df if df is not None else pd.DataFrame()


__all__ = [
    "KlineClient",
    "FakeKlineClient",
    "TushareKlineClient",
    "AKShareKlineClient",
]
