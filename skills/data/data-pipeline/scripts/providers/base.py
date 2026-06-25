"""Vision provider abstraction for Smart Money OCR (RFC-03-006 / SPEC-03-006).

Exposes:
  - VisionProvider  : ABC implemented by every concrete OCR provider
  - ProviderResult  : dataclass with df + source_path + provider_status
  - ProviderError   : classified failure raised by describe()
  - FailureKind     : enum of failure categories
  - FailureReason   : classified failure (kind + retryable + message)
  - AttemptRecord   : single-attempt log (used by Router for audit)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd


class FailureKind(str, Enum):
    """Failure classification used by providers and Router."""

    QUOTA_EXCEEDED = "quota_exceeded"          # 429 / quota / rate limit
    TIMEOUT = "timeout"                        # subprocess.TimeoutExpired / upstream timeout
    NETWORK = "network"                        # 5xx / connection refused
    CLI_NOT_FOUND = "cli_not_found"            # mmx not in PATH
    MCP_UNAVAILABLE = "mcp_unavailable"        # Z.AI MCP cannot connect
    PARSE_ERROR = "parse_error"                # JSON parse failure
    SCHEMA_MISMATCH = "schema_mismatch"        # output schema unexpected
    UNKNOWN = "unknown"                        # catch-all


@dataclass(frozen=True)
class FailureReason:
    """Classified failure with retry decision."""

    kind: FailureKind
    retryable: bool
    message: str  # human-readable, sanitized


class ProviderError(RuntimeError):
    """Provider raised a classified failure that Router may choose to handle."""

    def __init__(self, provider: str, failure: FailureReason):
        super().__init__(f"[{provider}] {failure.kind.value}: {failure.message}")
        self.provider = provider
        self.failure = failure


@dataclass
class AttemptRecord:
    """Record of a single provider invocation attempt."""

    provider: str
    success: bool
    duration_ms: int
    error_kind: FailureKind | None = None
    error_message: str | None = None  # sanitized

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error_kind": self.error_kind.value if self.error_kind else None,
            "error_message": self.error_message,
        }


@dataclass
class ProviderResult:
    """Standardised return value for every VisionProvider implementation."""

    df: pd.DataFrame
    source_path: str
    provider_status: dict[str, Any] = field(default_factory=lambda: {
        "name": "",
        "fallback_used": False,
        "attempts": [],  # list[AttemptRecord.to_dict()]
        "errors": [],    # list[str]
    })

    def to_record(self) -> dict[str, Any]:
        """Serialize to the dict shape consumed by the existing pipeline.

        Contract: downstream pipeline reads only ``df`` and ``source_path``;
        ``provider_status`` is an audit-only field that may be propagated to
        save_pending_review / batch_report.
        """
        return {
            "df": self.df,
            "source_path": self.source_path,
            "provider_status": self.provider_status,
        }


class VisionProvider(ABC):
    """Abstract OCR provider.

    Implementations MUST return ProviderResult on success or raise ProviderError
    with a classified FailureReason on failure. Implementations MUST NOT do any
    cross-provider fallback (that is Router's job). Implementations MUST NOT
    mutate the input file.
    """

    name: str  # class attribute; "minimax" or "zai"

    def __init__(
        self,
        *,
        output_dir: Path | str | None = None,
        date_str: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Providers may accept output_dir / date_str for debug writes.
        # Default to harmless no-op so minimal mocks don't have to wire them.
        self.output_dir = Path(output_dir) if output_dir else None
        self.date_str = date_str
        self._init_kwargs = kwargs

    @abstractmethod
    async def describe(self, image_path: Path) -> ProviderResult:
        """Run OCR on a single image and return a normalised ProviderResult.

        Contract:
          - MUST return ProviderResult on success with df populated.
          - MUST raise ProviderError (with classified FailureReason) on failure.
          - MUST NOT silently swallow errors.
          - MUST NOT do any cross-provider fallback (Router's job).
          - MUST NOT mutate the input file.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Lightweight readiness check used at startup. Must not raise."""
