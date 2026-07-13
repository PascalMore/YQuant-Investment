"""Domain services — Phase 1A.

Five services wrap the eight TA-CN MongoDB collections under a single
provider tag (``"ta_cn_adapter"``). Each service class accepts a
:class:`TA_CNMongoAdapter` and exposes only the methods listed in
DESIGN-03-007 §Phase 1A "服务→adapter 调用流与完整矩阵".

The package-level helpers (``PROVIDER``, ``SERVICE_ERRORS``,
``wrap_success``, ``wrap_empty``, ``wrap_error``) are the shared wrapping
logic every service uses to convert raw adapter output into a
``DataResult`` with the canonical ``provider`` / ``freshness`` /
``source_trace`` contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..adapters import TA_CNMongoAdapter
from ..exceptions import ProviderError, ProviderUnavailableError
from ..models import DataResult, SecurityId

try:  # pymongo is optional at import time; the adapter itself is structural.
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
except ImportError:  # pragma: no cover - exercised only in minimal environments
    MONGO_CONNECTION_ERRORS: tuple[type[BaseException], ...] = ()
else:
    MONGO_CONNECTION_ERRORS = (ConnectionFailure, ServerSelectionTimeoutError)


PROVIDER = "ta_cn_adapter"
SERVICE_ERRORS = (
    ProviderUnavailableError,
    ProviderError,
    ConnectionError,
    TimeoutError,
    ValueError,
    TypeError,
    *MONGO_CONNECTION_ERRORS,
)


def _now() -> datetime:
    """Naive UTC timestamp matching the Phase 0 ``DataResult`` default."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def wrap_success(
    data: Any,
    security_id: SecurityId,
    domain: str,
    operation: str,
    *,
    fetched_at: datetime | None = None,
    source_trace: list[str] | None = None,
) -> DataResult:
    """Build a successful ``DataResult`` carrying a non-empty payload."""
    return DataResult.success(
        data=data,
        security_id=security_id,
        domain=domain,
        operation=operation,
        provider=PROVIDER,
        fetched_at=fetched_at or _now(),
        source_trace=source_trace or [f"{PROVIDER}(ok)"],
    )


def wrap_empty(
    security_id: SecurityId,
    domain: str,
    operation: str,
    *,
    fetched_at: datetime | None = None,
) -> DataResult:
    """Build an empty ``DataResult`` (``data=None``).

    The freshness label is forced to ``"empty"`` by ``DataResult.success``
    when ``data`` is ``None``; the provider is also coerced to
    ``"empty"`` per the Phase 0 contract.
    """
    return DataResult.success(
        data=None,
        security_id=security_id,
        domain=domain,
        operation=operation,
        provider=PROVIDER,
        fetched_at=fetched_at or _now(),
        source_trace=[f"{PROVIDER}(ok)"],
    )


def wrap_error(
    security_id: SecurityId,
    domain: str,
    operation: str,
    error: BaseException,
    *,
    fetched_at: datetime | None = None,
) -> DataResult:
    """Build an error ``DataResult`` from an exception.

    ``DataResult.error`` records ``provider="error"`` and places
    ``"<provider>(error: <msg>)"`` in ``source_trace`` automatically.
    """
    return DataResult.error(
        security_id=security_id,
        domain=domain,
        operation=operation,
        provider=PROVIDER,
        error=error,
        fetched_at=fetched_at or _now(),
    )


# Service classes — imported at the bottom because each one re-imports
# the wrapping helpers defined above from this package.
from .event_service import EventService  # noqa: E402
from .fundamental_service import FundamentalService  # noqa: E402
from .market_data_service import MarketDataService  # noqa: E402
from .metadata_service import MetadataService  # noqa: E402
from .sector_service import SectorService  # noqa: E402


__all__ = [
    # adapter type re-export (so consumers can do ``from .services import TA_CNMongoAdapter``)
    "TA_CNMongoAdapter",
    # shared wrapping helpers
    "PROVIDER",
    "SERVICE_ERRORS",
    "wrap_success",
    "wrap_empty",
    "wrap_error",
    # service classes
    "EventService",
    "FundamentalService",
    "MarketDataService",
    "MetadataService",
    "SectorService",
]
