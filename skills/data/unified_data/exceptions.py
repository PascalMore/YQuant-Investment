"""Exception hierarchy for unified_data.

All exceptions raised from within ``skills.data.unified_data`` inherit from
:class:`UnifiedDataError`. Consumers can catch the base class for a
coarse-grained handler or rely on the specific subclasses for finer control.

This module is deliberately self-contained: no third-party imports, no
dependency on any other ``unified_data`` submodule, so it can be imported
from anywhere in the package without risk of circular imports.
"""

from __future__ import annotations

from typing import Any, Iterable


class UnifiedDataError(Exception):
    """Base class for all unified_data errors.

    Catching this exception covers every domain error raised by the
    unified_data layer. Specific subclasses exist for programming and
    runtime errors that benefit from distinct handling.
    """


class InvalidSecurityIdError(UnifiedDataError, ValueError):
    """Raised when a ``SecurityId`` cannot be constructed from the input.

    Inherits from ``ValueError`` as well so that idiomatic ``except
    ValueError`` blocks continue to work for security-id validation.
    """


class UnsupportedCapabilityError(UnifiedDataError):
    """A provider received a request for a capability it does not declare."""


class ProviderUnavailableError(UnifiedDataError):
    """A provider is currently unusable (missing dependency, no token, ...)."""


class ProviderError(UnifiedDataError):
    """A provider raised an internal error while serving a request."""


class AllProvidersFailedError(UnifiedDataError):
    """Every provider in the fallback chain failed for a given query.

    Attributes:
        capability: The capability string that was requested.
        attempts:   Iterable of ``(provider_name, error_message)`` tuples
                    describing each attempt, in the order they were tried.
    """

    def __init__(
        self,
        capability: str,
        attempts: Iterable[tuple[str, Any]] | None = None,
        message: str | None = None,
    ) -> None:
        attempt_list = list(attempts or [])
        if message is None:
            if attempt_list:
                rendered = ", ".join(
                    f"{name}({err!r})" for name, err in attempt_list
                )
                message = f"All providers failed for capability {capability!r}: {rendered}"
            else:
                message = f"No providers registered for capability {capability!r}"
        super().__init__(message)
        self.capability = capability
        self.attempts: list[tuple[str, Any]] = attempt_list