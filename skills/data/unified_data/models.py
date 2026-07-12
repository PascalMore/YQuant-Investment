"""Core data models for unified_data.

This module provides three small, self-contained value objects that the
rest of the package depends on:

* :class:`Market`            -- enumeration of supported markets
* :class:`SecurityId`        -- immutable cross-market security identifier
* :class:`Capability`        -- value object describing a provider capability
* :class:`DataResult`        -- standard return value from a query
* ``FreshnessLabel``         -- typing alias for the freshness state

These objects have no I/O, no MongoDB, no provider-specific behavior. They
can be used safely in tests and in any other ``skills.data`` submodule.

Design references: SPEC-03-007 §3.1, §3.2, §3.3, §4.1, §4.2, §4.4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Literal

from .exceptions import InvalidSecurityIdError

# ---------------------------------------------------------------------------
# Market
# ---------------------------------------------------------------------------


class Market(str, Enum):
    """Enumerated markets supported by unified_data.

    ``str`` mixin so the values can be used directly as dict keys or in
    string comparisons without explicit ``.value`` access.
    """

    CN = "CN"          # A 股
    HK = "HK"          # 港股
    US = "US"          # 美股
    CRYPTO = "CRYPTO"  # 加密货币
    INDEX = "INDEX"    # 指数
    FUND = "FUND"      # 基金


# ---------------------------------------------------------------------------
# SecurityId
# ---------------------------------------------------------------------------


# Internal A-share exchange suffix lookup. Kept as a module-level constant
# so it is easy to extend without touching SecurityId logic. The mapping
# covers the four major A-share segments.
_A_SHARE_SUFFIX_RULES: tuple[tuple[range, str], ...] = (
    (range(600000, 610000), "SH"),   # 上海主板
    (range(688000, 690000), "SH"),   # 科创板
    (range(0, 5000), "SZ"),          # 深圳主板
    (range(300000, 302000), "SZ"),   # 创业板
    (range(920000, 930000), "BJ"),   # 北交所
)


def _a_share_suffix(symbol: str) -> str | None:
    """Return the conventional A-share exchange suffix for ``symbol``.

    Returns ``None`` if the symbol is not numeric or does not match a
    known segment. Symbols are expected to be six-digit zero-padded
    strings (e.g. ``"600519"``).
    """
    if not symbol.isdigit() or len(symbol) != 6:
        return None
    try:
        n = int(symbol)
    except ValueError:
        return None
    for span, suffix in _A_SHARE_SUFFIX_RULES:
        if n in span:
            return suffix
    return None


@dataclass(frozen=True, slots=True)
class SecurityId:
    """Immutable cross-market security identifier.

    A ``SecurityId`` is the canonical identifier used everywhere inside
    unified_data. The value is fully determined by ``(market, symbol)``:
    identical inputs always produce equal instances (and the same hash),
    making SecurityId safe to use as dict keys and set members.

    Format conversions (``from_wind_code``, ``from_tushare_code``,
    ``from_full_symbol``, ``from_numeric``) and the inverse
    (``to_wind_code``, ``to_tushare_code``, ``to_full_symbol``,
    ``canonical``) are pure functions of the input — no I/O, no MongoDB.

    Examples::

        SecurityId(market=Market.CN, symbol="600519")
        SecurityId.from_wind_code("600519.SH")
        SecurityId.from_full_symbol("000001.SZ")
    """

    market: Market
    symbol: str

    def __post_init__(self) -> None:
        if not isinstance(self.market, Market):
            # Allow string values for friendlier call sites, but reject
            # anything that does not map to a known market.
            try:
                object.__setattr__(self, "market", Market(self.market))
            except ValueError as exc:
                raise InvalidSecurityIdError(
                    f"Unknown market {self.market!r}; "
                    f"expected one of {[m.value for m in Market]}"
                ) from exc
        if not isinstance(self.symbol, str):
            raise InvalidSecurityIdError(
                f"symbol must be a string, got {type(self.symbol).__name__}"
            )
        symbol = self.symbol.strip()
        if not symbol:
            raise InvalidSecurityIdError("symbol must be a non-empty string")
        if symbol != self.symbol:
            # Normalize leading/trailing whitespace silently. The dataclass
            # is frozen, so we must bypass __setattr__.
            object.__setattr__(self, "symbol", symbol)

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"{self.market.value}:{self.symbol}"

    @property
    def canonical(self) -> str:
        """Return the canonical string form ``"MARKET:SYMBOL"``.

        This is the identifier the unified_data layer uses internally
        when persisting audit/cache entries or building cache keys.
        """
        return str(self)

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_wind_code(cls, code: str) -> "SecurityId":
        """Build a SecurityId from a Wind-style ``"CODE.EXCHANGE"`` string.

        Examples::

            "600519.SH"  -> CN, "600519"
            "00700.HK"   -> HK, "00700"
            "AAPL.US"    -> US, "AAPL"
        """
        return _from_dotted_code(code, source="wind_code")

    @classmethod
    def from_tushare_code(cls, code: str) -> "SecurityId":
        """Build a SecurityId from a Tushare-style ``"CODE.EXCHANGE"`` string.

        Tushare and Wind share the same ``CODE.EXCHANGE`` layout for A
        shares, so the parsing is identical. The dedicated method exists
        so consumers can express intent clearly and we have room to
        diverge in the future if Tushare ever changes its format.
        """
        return _from_dotted_code(code, source="tushare_code")

    @classmethod
    def from_full_symbol(cls, code: str) -> "SecurityId":
        """Build a SecurityId from a generic ``"CODE.EXCHANGE"`` string.

        Alias of :meth:`from_tushare_code`; provided for clarity at call
        sites that already speak in terms of ``full_symbol`` (the TA-CN
        canonical field name).
        """
        return _from_dotted_code(code, source="full_symbol")

    @classmethod
    def from_numeric(cls, code: str, market: Market | str) -> "SecurityId":
        """Build a SecurityId from a bare numeric code plus a market.

        Useful for inputs like ``"600519"`` where the caller already knows
        the market context. Raises :class:`InvalidSecurityIdError` if
        ``code`` is empty after stripping.
        """
        if code is None:
            raise InvalidSecurityIdError("code must not be None")
        code = str(code).strip()
        if not code:
            raise InvalidSecurityIdError("code must be a non-empty string")
        return cls(market=market, symbol=code)

    # ------------------------------------------------------------------
    # Conversions
    # ------------------------------------------------------------------

    def to_wind_code(self) -> str | None:
        """Return the Wind-style ``"CODE.EXCHANGE"`` form, or ``None``.

        Returns ``None`` for markets we do not currently translate (HK,
        US, CRYPTO, INDEX, FUND) — caller should treat that as a signal
        to use the symbol verbatim.
        """
        return _to_dotted_code(self, suffix_for_a_share=True)

    def to_tushare_code(self) -> str | None:
        """Return the Tushare-style ``"CODE.EXCHANGE"`` form, or ``None``."""
        return _to_dotted_code(self, suffix_for_a_share=True)

    def to_full_symbol(self) -> str | None:
        """Return the generic ``"CODE.EXCHANGE"`` form, or ``None``."""
        return _to_dotted_code(self, suffix_for_a_share=True)


# ---------------------------------------------------------------------------
# Internal helpers for SecurityId
# ---------------------------------------------------------------------------


_EXCHANGE_TO_MARKET: dict[str, Market] = {
    "SH": Market.CN,
    "SZ": Market.CN,
    "BJ": Market.CN,
    "HK": Market.HK,
    "US": Market.US,
    "O": Market.US,   # NASDAQ suffix
    "N": Market.US,   # NYSE suffix
}


def _from_dotted_code(code: str, *, source: str) -> SecurityId:
    """Shared parser for ``"CODE.EXCHANGE"`` inputs."""
    if code is None:
        raise InvalidSecurityIdError(f"{source} must not be None")
    text = str(code).strip()
    if not text:
        raise InvalidSecurityIdError(f"{source} must be a non-empty string")
    if "." not in text:
        raise InvalidSecurityIdError(
            f"{source} must contain a dot separator, got {text!r}"
        )
    head, _, tail = text.partition(".")
    if not head or not tail:
        raise InvalidSecurityIdError(
            f"{source} has empty part: code={text!r}"
        )
    market = _EXCHANGE_TO_MARKET.get(tail.upper())
    if market is None:
        raise InvalidSecurityIdError(
            f"{source} has unknown exchange suffix {tail!r}; "
            f"expected one of {sorted(_EXCHANGE_TO_MARKET)}"
        )
    return SecurityId(market=market, symbol=head)


def _to_dotted_code(sid: SecurityId, *, suffix_for_a_share: bool) -> str | None:
    """Inverse of ``_from_dotted_code`` for markets we know how to map."""
    if sid.market is Market.CN:
        if not suffix_for_a_share:
            return None
        suffix = _a_share_suffix(sid.symbol)
        return f"{sid.symbol}.{suffix}" if suffix else None
    market_to_suffix = {
        Market.HK: "HK",
        Market.US: "US",
    }
    suffix = market_to_suffix.get(sid.market)
    if suffix is None:
        return None
    return f"{sid.symbol}.{suffix}"


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Capability:
    """Value object describing a single provider capability.

    A capability names a (domain, operation) pair, e.g.
    ``("market_data", "kline_daily")``. The canonical string form is
    ``"domain.operation"`` and is what :class:`DataProvider` exposes via
    the :attr:`DataProvider.capabilities` set.
    """

    domain: str
    operation: str
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.domain, str) or not self.domain.strip():
            raise ValueError("Capability.domain must be a non-empty string")
        if not isinstance(self.operation, str) or not self.operation.strip():
            raise ValueError("Capability.operation must be a non-empty string")
        if "." in self.domain:
            raise ValueError(
                f"Capability.domain must not contain '.': {self.domain!r}"
            )
        if "." in self.operation:
            raise ValueError(
                f"Capability.operation must not contain '.': {self.operation!r}"
            )

    @property
    def name(self) -> str:
        """Return the canonical ``"domain.operation"`` string form."""
        return f"{self.domain}.{self.operation}"

    @classmethod
    def from_string(cls, capability: str) -> "Capability":
        """Parse a ``"domain.operation"`` string into a Capability.

        Raises ``ValueError`` if the string is malformed.
        """
        if not isinstance(capability, str) or not capability.strip():
            raise ValueError("capability string must be non-empty")
        if capability.count(".") != 1:
            raise ValueError(
                f"capability must be exactly 'domain.operation', got {capability!r}"
            )
        domain, _, operation = capability.partition(".")
        return cls(domain=domain, operation=operation)

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# DataResult
# ---------------------------------------------------------------------------


FreshnessLabel = Literal["realtime", "delayed", "cached", "stale", "empty"]


@dataclass(slots=True)
class DataResult:
    """Standard return value from a unified_data query.

    The result carries both the payload (``data``) and the metadata needed
    to reason about provenance (``provider``, ``fetched_at``,
    ``source_trace``), freshness (``freshness``), and warnings
    (``warnings``).

    Phase 0 keeps the object deliberately small: serialization helpers and
    freshness recomputation belong to later phases. The ``to_dict`` method
    only handles JSON-friendly payloads and raises ``TypeError`` for
    exotic data so callers can decide how to convert it (e.g. via pandas
    ``to_dict(orient="records")``).
    """

    data: Any
    security_id: SecurityId
    domain: str
    operation: str
    provider: str
    fetched_at: datetime
    data_date: str | None = None
    freshness: FreshnessLabel = "cached"
    quality_score: float | None = None
    source_trace: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def success(
        cls,
        data: Any,
        security_id: SecurityId,
        domain: str,
        operation: str,
        provider: str,
        fetched_at: datetime | None = None,
        source_trace: Iterable[str] | None = None,
        warnings: Iterable[str] | None = None,
        **kwargs: Any,
    ) -> "DataResult":
        """Construct a successful result.

        Empty ``data`` (``None`` or empty DataFrame/list) is treated as
        ``freshness="empty"`` and the provider is recorded as
        ``"empty"``. This keeps the empty-result branch explicit and
        avoids accidentally tagging an empty provider response as a real
        success.
        """
        if fetched_at is None:
            fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        trace: list[str] = list(source_trace or [f"{provider}(ok)"])
        warn_list: list[str] = list(warnings or [])

        if data is None or _is_empty_payload(data):
            return cls(
                data=data,
                security_id=security_id,
                domain=domain,
                operation=operation,
                provider="empty",
                fetched_at=fetched_at,
                freshness="empty",
                source_trace=trace,
                warnings=warn_list,
            )

        return cls(
            data=data,
            security_id=security_id,
            domain=domain,
            operation=operation,
            provider=provider,
            fetched_at=fetched_at,
            freshness="delayed",
            source_trace=trace,
            warnings=warn_list,
            **kwargs,
        )

    @classmethod
    def error(
        cls,
        security_id: SecurityId,
        domain: str,
        operation: str,
        provider: str,
        error: BaseException | str,
        fetched_at: datetime | None = None,
        source_trace: Iterable[str] | None = None,
    ) -> "DataResult":
        """Construct an error result.

        ``provider`` is recorded as ``"error"`` and the original provider
        name is preserved in ``source_trace`` as ``"<provider>(error)"``.
        ``warnings`` carries the stringified error.
        """
        if fetched_at is None:
            fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        trace: list[str] = list(
            source_trace or [f"{provider}(error: {error})"]
        )
        warn = [str(error)]
        return cls(
            data=None,
            security_id=security_id,
            domain=domain,
            operation=operation,
            provider="error",
            fetched_at=fetched_at,
            freshness="empty",
            source_trace=trace,
            warnings=warn,
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def is_empty(self) -> bool:
        """Return ``True`` when this result carries no usable payload."""
        return self.freshness == "empty" or self.data is None or _is_empty_payload(self.data)

    @property
    def succeeded(self) -> bool:
        """Return ``True`` for results that carry a non-empty payload."""
        return not self.is_empty()

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result to a JSON-friendly ``dict``.

        ``data`` is passed through verbatim; non-JSON values are flagged
        by a leading ``SerializationError`` exception rather than silently
        coerced. Callers that need a stable wire format should convert
        ``data`` (typically a pandas DataFrame) to records before calling
        :meth:`to_dict`.
        """
        return {
            "data": self.data,
            "security_id": self.security_id.canonical,
            "domain": self.domain,
            "operation": self.operation,
            "provider": self.provider,
            "fetched_at": self.fetched_at.isoformat(),
            "data_date": self.data_date,
            "freshness": self.freshness,
            "quality_score": self.quality_score,
            "source_trace": list(self.source_trace),
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_empty_payload(data: Any) -> bool:
    """Return ``True`` if ``data`` is a recognized empty container.

    A pandas DataFrame, list, tuple, dict or set is empty when it has no
    elements. Strings and numbers are never "empty" by this rule — the
    contract here is intentionally narrow.
    """
    if data is None:
        return True
    # Pandas DataFrame path: ``df.empty`` is the canonical check.
    empty_attr = getattr(data, "empty", None)
    if isinstance(empty_attr, bool):
        return empty_attr
    if isinstance(data, (list, tuple, set, frozenset)):
        return len(data) == 0
    if isinstance(data, dict):
        return len(data) == 0
    return False