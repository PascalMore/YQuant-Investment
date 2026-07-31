"""Sector HTTP client abstraction for P3-A external provider activation.

This module ships three cooperating types that together implement the
``sector.snapshot`` / ``sector.ranking`` real call path for the AKShare
provider (DESIGN-03-014-p3a §3.3):

* :class:`SectorClient` — a ``typing.Protocol`` describing the structural
  contract every concrete sector client must satisfy. Protocol (not ABC)
  is used on purpose so the implementations below are structurally typed
  without forcing an explicit inheritance relationship. Mirrors the
  Phase 1D :class:`KlineClient` injection pattern.
* :class:`AKShareSectorClient` — production client. Imports the optional
  ``akshare`` dependency lazily inside ``_call_name_em`` so the module
  stays importable when the SDK is absent. Token-less (AKShare is
  anonymous). Calls ``stock_board_industry_name_em()`` (the shared
  endpoint for both snapshot and ranking, per DESIGN §1.1 endpoint
  correction).
* :class:`FakeSectorClient` — test-only stand-in. Records every call in
  ``call_log`` and returns either a canned ``DataFrame`` or raises a
  configured exception. Never reads the environment and never performs
  any I/O.

All real SDK imports live inside ``_call_name_em``. The module-level
surface has zero third-party imports beyond ``pandas`` (already a hard
dependency).

Design reference: DESIGN-03-014-p3a-sector-provider-activation §3.3.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import pandas as pd

from ..exceptions import ProviderError, ProviderUnavailableError


# ---------------------------------------------------------------------------
# SectorClient Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SectorClient(Protocol):
    """Injectable sector data client abstraction (P3-A).

    Mirrors the Phase 1D :class:`KlineClient` injection pattern. Two
    implementations:

    * :class:`FakeSectorClient` — test fixture, no network, no SDK import.
    * :class:`AKShareSectorClient` — production, lazy-imports ``akshare``,
      calls ``stock_board_industry_name_em()``.

    Both methods internally call the same upstream endpoint
    (``name_em``); ``get_sector_snapshot()`` filters the full result
    by ``sector_code`` at the Client layer.

    Implementations must raise:

    * :class:`ProviderUnavailableError` for network/timeout/SSL failures.
    * :class:`ProviderError` for API-internal failures.
    """

    def get_sector_snapshot(
        self,
        sector_code: str,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        """Return board-level aggregate row for a single sector.

        Internally calls ``stock_board_industry_name_em()`` and
        filters by ``sector_code``. Returns a 1-row DataFrame (or
        empty if ``sector_code`` not found).

        Raises:
            ProviderUnavailableError: network/timeout/SSL.
            ProviderError: API internal error / unsupported sector_type.
        """
        ...

    def get_sector_ranking(
        self,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        """Return ranking DataFrame for all sectors of a type.

        Internally calls ``stock_board_industry_name_em()`` and
        returns the full result.

        Raises:
            ProviderUnavailableError: network/timeout/SSL.
            ProviderError: API internal error / unsupported sector_type.
        """
        ...


# ---------------------------------------------------------------------------
# FakeSectorClient (test fixture)
# ---------------------------------------------------------------------------


class FakeSectorClient:
    """Test-only :class:`SectorClient` implementation.

    Construct with a ranking DataFrame (and optionally a separate
    snapshot DataFrame). ``get_sector_snapshot()`` filters the ranking
    DataFrame by ``板块代码 == sector_code`` unless an explicit
    ``snapshot_df`` is provided; ``get_sector_ranking()`` returns the
    full ranking DataFrame. Both methods record every invocation in
    ``call_log``.

    The fake never reads the environment, never imports the real SDK,
    and never performs I/O. It is the canonical injection point for
    the P3-A provider unit tests.
    """

    def __init__(
        self,
        *,
        ranking_df: pd.DataFrame | None = None,
        snapshot_df: pd.DataFrame | None = None,
        exception: BaseException | None = None,
    ) -> None:
        self._ranking_df = ranking_df
        self._snapshot_df = snapshot_df  # if None, derive from ranking_df
        self._exc = exception
        self.call_log: list[dict[str, Any]] = []

    def get_sector_snapshot(
        self,
        sector_code: str,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        self.call_log.append(
            {"method": "snapshot", "sector_code": sector_code, "sector_type": sector_type}
        )
        if self._exc is not None:
            raise self._exc
        # If explicit snapshot_df provided, use it; otherwise filter ranking_df
        if self._snapshot_df is not None:
            return self._snapshot_df.copy()
        if self._ranking_df is None:
            return pd.DataFrame()
        if "板块代码" in self._ranking_df.columns and sector_code:
            mask = self._ranking_df["板块代码"] == sector_code
            return self._ranking_df[mask].copy()  # type: ignore[return-value]
        return self._ranking_df.iloc[0:0]

    def get_sector_ranking(
        self,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        self.call_log.append({"method": "ranking", "sector_type": sector_type})
        if self._exc is not None:
            raise self._exc
        if self._ranking_df is None:
            return pd.DataFrame()
        return self._ranking_df.copy()


# ---------------------------------------------------------------------------
# Production client (lazy SDK import)
# ---------------------------------------------------------------------------


def _raise_classified(exc: Exception) -> None:
    """Normalise an SDK exception into Provider*Error (P-10).

    Mirrors :meth:`TushareKlineClient._raise_classified` keyword
    matching so connection-level failures are classified as
    :class:`ProviderUnavailableError` (Router can transparently fall
    back) and API-internal failures as :class:`ProviderError`.

    The message is deliberately category-only; the raw exception is
    chained via ``from exc``.
    """
    msg = str(exc).lower()
    exc_type = type(exc).__name__.lower()
    if (
        any(
            keyword in msg
            for keyword in (
                "timeout",
                "connection",
                "network",
                "eof",
                "ssl",
                "tls",
                "certificate",
                "disconnect",
                "connection reset",
                "broken pipe",
            )
        )
        or isinstance(exc, (ConnectionError, TimeoutError))
        or exc_type in ("sslerror", "tlserror")
    ):
        raise ProviderUnavailableError("akshare sector API unavailable") from exc
    raise ProviderError("akshare sector API error") from exc


class AKShareSectorClient:
    """Production AKShare sector client (lazy SDK import).

    AKShare is token-less. ``stock_board_industry_name_em()`` returns
    all industry boards in one call — no pagination, no date parameter.
    The endpoint always returns the latest available snapshot.

    Both ``get_sector_snapshot()`` and ``get_sector_ranking()``
    internally call ``name_em()``; snapshot filters the result by
    ``sector_code``.

    The returned DataFrame column order is frozen by the AKShare
    source code (verified via ``inspect.getsource``)::

        排名, 板块名称, 板块代码, 最新价, 涨跌额, 涨跌幅,
        总市值, 换手率, 上涨家数, 下跌家数, 领涨股票, 领涨股票-涨跌幅
    """

    _INDUSTRY_FN_NAME = "stock_board_industry_name_em"
    _CONCEPT_FN_NAME = "stock_board_concept_name_em"

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def _call_name_em(self, sector_type: str) -> pd.DataFrame:
        """Shared internal: call name_em for the given sector_type."""
        if sector_type == "industry":
            fn_name = self._INDUSTRY_FN_NAME
        elif sector_type == "concept":
            fn_name = self._CONCEPT_FN_NAME
        else:
            raise ProviderError(
                f"akshare sector: unsupported sector_type {sector_type!r}; "
                f"only 'industry' and 'concept' are supported"
            )

        import akshare as ak  # type: ignore[import-not-found]  # lazy import
        fn = getattr(ak, fn_name, None)
        if fn is None:
            raise ProviderUnavailableError(
                f"akshare sector: endpoint {fn_name!r} not found in installed package"
            )
        try:
            df = fn()
        except Exception as exc:
            _raise_classified(exc)
            raise  # pragma: no cover
        return df if df is not None else pd.DataFrame()

    def get_sector_snapshot(
        self,
        sector_code: str,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        df = self._call_name_em(sector_type)
        if "板块代码" in df.columns and sector_code:
            mask = df["板块代码"] == sector_code
            return df[mask].copy()  # type: ignore[return-value]
        return df.iloc[0:0]  # empty with same columns

    def get_sector_ranking(
        self,
        sector_type: str = "industry",
    ) -> pd.DataFrame:
        return self._call_name_em(sector_type)


__all__ = [
    "SectorClient",
    "FakeSectorClient",
    "AKShareSectorClient",
]
