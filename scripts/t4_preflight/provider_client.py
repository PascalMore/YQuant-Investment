"""T4 AKShare safe-call smoke client (PR-2 / PR-3 / PR-4).

DESIGN-03-014 §15.6 / SPEC-03-014 §14.4 / RFC-03-014 §13.4.

The :class:`AKShareSmokeClient` enforces the design's hard limits:

* Single security / single date (or ≤3 trading-day window).
* Hard cap on call count per capability
  (``config.AKSHARE_MAX_CALLS``).
* Hard minimum interval between calls (≥1s).
* No retries on failure.
* No persistence — the only output is an in-memory
  :class:`SmokeCallResult` and the field-mapping step is a pure
  function over the in-memory result.

The client does NOT import :mod:`akshare` at module load time. The
import is deferred to the first live call. Tests can inject a fake
via :func:`set_call_dispatcher`.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any, Callable, Mapping, Protocol

from .config import (
    AKSHARE_MAX_CALLS,
    DEFAULT_TEST_TARGETS,
    MIN_INTERVAL_SECONDS,
)
from .models import (
    DataSampleResult,
    FieldMappingResult,
    OverallVerdict,
    PermissionResult,
    SmokeCallResult,
)

__all__ = [
    "AKShareSmokeClient",
    "set_call_dispatcher",
    "reset_call_dispatcher",
    "FieldMapper",
    "verdict_for_mapping",
]


# ---------------------------------------------------------------------------
# Plug-in seam (test override)
# ---------------------------------------------------------------------------


class _CallDispatcher(Protocol):
    def __call__(self, fn_name: str, **kwargs: Any) -> Any: ...


def _default_dispatcher(fn_name: str, **kwargs: Any) -> Any:
    """Default dispatcher: import :mod:`akshare` lazily and call.

    Returns whatever the underlying AKShare function returns (a
    :class:`pandas.DataFrame` in production). The caller is
    responsible for normalising the result into a row dict.
    """
    import akshare as ak  # type: ignore[import-not-found]

    fn = getattr(ak, fn_name, None)
    if fn is None:
        raise AttributeError(f"akshare has no attribute {fn_name!r}")
    return fn(**kwargs)


_dispatcher: _CallDispatcher = _default_dispatcher


def set_call_dispatcher(dispatcher: _CallDispatcher) -> None:
    """Override the AKShare call dispatcher (test seam)."""
    global _dispatcher
    _dispatcher = dispatcher


def reset_call_dispatcher() -> None:
    """Reset to the default AKShare dispatcher."""
    global _dispatcher
    _dispatcher = _default_dispatcher


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------


def verdict_for_mapping(matched_ratio: float) -> str:
    """Apply the §15.6.2 thresholds."""
    if matched_ratio >= 0.90:
        return "pass"
    if matched_ratio >= 0.70:
        return "conditional_pass"
    return "fail"


class FieldMapper:
    """Pure function helpers for field-mapping comparison."""

    @staticmethod
    def compare(
        *,
        actual_fields: list[str] | tuple[str, ...],
        expected_fields: list[str] | tuple[str, ...],
    ) -> FieldMappingResult:
        total = len(expected_fields)
        actual_set = set(actual_fields)
        expected_set = set(expected_fields)
        matched = sum(1 for f in expected_fields if f in actual_set)
        missing = tuple(f for f in expected_fields if f not in actual_set)
        extra = tuple(sorted(f for f in actual_fields if f not in expected_set))
        return FieldMappingResult(
            total_expected_fields=total,
            matched_fields=matched,
            missing_fields=missing,
            extra_fields=extra,
            type_mismatches=(),
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def _normalise_rows(raw: Any) -> tuple[dict[str, Any], ...]:
    """Convert a pandas DataFrame or list of dicts to tuple-of-dicts."""
    if raw is None:
        return ()
    # pandas DataFrame — try the common path
    try:
        import pandas as pd  # type: ignore[import-not-found]

        if isinstance(raw, pd.DataFrame):
            out: list[dict[str, Any]] = []
            head = raw.head(5)
            for _, row in head.iterrows():
                out.append({str(k): v for k, v in row.to_dict().items()})
            return tuple(out)
    except Exception:  # noqa: BLE001
        pass
    # Already an iterable of dicts
    if isinstance(raw, Mapping):
        return (dict(raw),)
    try:
        iterator = iter(raw)
    except TypeError:
        return ()
    out: list[dict[str, Any]] = []
    for item in iterator:
        if isinstance(item, Mapping):
            out.append(dict(item))
        else:
            out.append({"_row": str(item)})
        if len(out) >= 5:
            break
    return tuple(out)


def _coerce_field_names(raw: Any) -> list[str]:
    """Extract field names from a DataFrame-like."""
    if raw is None:
        return []
    try:
        import pandas as pd  # type: ignore[import-not-found]

        if isinstance(raw, pd.DataFrame):
            return [str(c) for c in raw.columns]
    except Exception:  # noqa: BLE001
        pass
    if isinstance(raw, Mapping):
        return [str(k) for k in raw.keys()]
    if isinstance(raw, (list, tuple)) and raw and isinstance(raw[0], Mapping):
        return [str(k) for k in raw[0].keys()]
    return []


class AKShareSmokeClient:
    """AKShare safe-call smoke client (DESIGN §15.6.1)."""

    def __init__(
        self,
        *,
        timeout_seconds: int = 30,
        min_interval_seconds: float = MIN_INTERVAL_SECONDS,
    ) -> None:
        self._timeout = timeout_seconds
        self._min_interval = min_interval_seconds
        self._last_call_at: float | None = None
        self._call_counters: dict[str, int] = {
            k: 0 for k in AKSHARE_MAX_CALLS
        }

    # ----- Rate limiting ---------------------------------------------------

    def _rate_limit(self) -> None:
        if self._last_call_at is None:
            return
        elapsed = time.perf_counter() - self._last_call_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

    def _enforce_cap(self, capability: str) -> None:
        cap = AKSHARE_MAX_CALLS.get(capability)
        if cap is None:
            raise ValueError(f"unknown capability: {capability!r}")
        if self._call_counters[capability] >= cap:
            raise RuntimeError(
                f"cap exhausted for {capability!r}: "
                f"{self._call_counters[capability]} / {cap}"
            )

    # ----- One-shot call wrapper -------------------------------------------

    def _one_call(
        self,
        *,
        capability: str,
        call_index: int,
        fn_name: str,
        params: dict[str, Any],
    ) -> SmokeCallResult:
        self._enforce_cap(capability)
        self._rate_limit()
        try:
            t0 = time.perf_counter()
            raw = _dispatcher(fn_name, **params)
            latency_ms = (time.perf_counter() - t0) * 1000.0
        except Exception as exc:  # noqa: BLE001
            self._call_counters[capability] += 1
            self._last_call_at = time.perf_counter()
            name = exc.__class__.__name__
            connectivity = "error"
            if "timeout" in name.lower():
                connectivity = "timeout"
            elif "rate" in name.lower() or "limit" in name.lower():
                connectivity = "rate_limited"
            return SmokeCallResult(
                capability=capability,
                call_index=call_index,
                connectivity=connectivity,
                latency_ms=None,
                raw_row_count=None,
                actual_fields=None,
                sample=None,
                error=f"{name}: {exc.__class__.__module__}",
            )

        self._call_counters[capability] += 1
        self._last_call_at = time.perf_counter()
        rows = _normalise_rows(raw)
        fields = _coerce_field_names(raw)
        return SmokeCallResult(
            capability=capability,
            call_index=call_index,
            connectivity="success",
            latency_ms=latency_ms,
            raw_row_count=len(rows) if rows else 0,
            actual_fields=tuple(fields) if fields else None,
            sample=rows if rows else None,
            error=None,
        )

    # ----- Public capability methods --------------------------------------

    def fetch_sector_snapshot(
        self, symbol: str, *, live: bool = False
    ) -> SmokeCallResult:
        if not live:
            return SmokeCallResult(
                capability="sector.snapshot",
                call_index=1,
                connectivity="skipped",
            )
        return self._one_call(
            capability="sector.snapshot",
            call_index=1,
            fn_name="stock_board_industry_cons_em",
            params={"symbol": symbol},
        )

    def fetch_sector_ranking(
        self, *, live: bool = False
    ) -> SmokeCallResult:
        if not live:
            return SmokeCallResult(
                capability="sector.ranking",
                call_index=1,
                connectivity="skipped",
            )
        return self._one_call(
            capability="sector.ranking",
            call_index=1,
            fn_name="stock_board_industry_name_em",
            params={},
        )

    def fetch_capital_flow(
        self, symbol: str, market: str, *, live: bool = False
    ) -> SmokeCallResult:
        if not live:
            return SmokeCallResult(
                capability="flow.capital_flow_daily",
                call_index=1,
                connectivity="skipped",
            )
        return self._one_call(
            capability="flow.capital_flow_daily",
            call_index=1,
            fn_name="stock_individual_fund_flow",
            params={"stock": symbol, "market": market},
        )

    def fetch_northbound_flow(
        self, symbol: str, *, live: bool = False
    ) -> SmokeCallResult:
        if not live:
            return SmokeCallResult(
                capability="flow.northbound_daily",
                call_index=1,
                connectivity="skipped",
            )
        return self._one_call(
            capability="flow.northbound_daily",
            call_index=1,
            fn_name="stock_hsgt_individual_em",
            params={"stock": symbol},
        )

    def fetch_market_sentiment(
        self, date: str, *, live: bool = False
    ) -> SmokeCallResult:
        if not live:
            return SmokeCallResult(
                capability="sentiment.market_snapshot",
                call_index=1,
                connectivity="skipped",
            )
        return self._one_call(
            capability="sentiment.market_snapshot",
            call_index=1,
            fn_name="stock_market_fund_flow",
            params={},
        )

    def fetch_limit_up_pool(
        self, date: str, *, live: bool = False
    ) -> SmokeCallResult:
        if not live:
            return SmokeCallResult(
                capability="sentiment.limit_up_pool",
                call_index=1,
                connectivity="skipped",
            )
        return self._one_call(
            capability="sentiment.limit_up_pool",
            call_index=1,
            fn_name="stock_zt_pool_em",
            params={"date": date},
        )


# ---------------------------------------------------------------------------
# Convenience: target lookup
# ---------------------------------------------------------------------------


def default_target(capability: str) -> str:
    """Return the design-default test target for a capability."""
    return DEFAULT_TEST_TARGETS[capability]
