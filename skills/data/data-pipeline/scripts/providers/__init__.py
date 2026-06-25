"""Vision provider package (RFC-03-006 / SPEC-03-006).

Public surface (used by ``MiniMaxImageExtractor``):
  - bootstrap_registry()        : register concrete providers (minimax, zai)
  - RouterConfig / VisionProviderRouter : sequential fallback router
  - MiniMaxVisionProvider / ZAIVisionProvider : concrete providers
  - health_check_all()          : startup readiness helper
  - VisionProvider, ProviderResult, ProviderError, FailureKind, FailureReason
  - extract_json, normalize_columns, clean_data, classify_failure, sanitize_error

Auto-bootstrap on import: providers/__init__.py registers minimax + zai.
"""
from __future__ import annotations

# Order matters: extract_json/classify/base/registry/prompts before providers.
from .base import (
    AttemptRecord,
    FailureKind,
    FailureReason,
    ProviderError,
    ProviderResult,
    VisionProvider,
)
from .registry import (
    clear_registry,
    get_provider,
    is_registered,
    list_providers,
    register_provider,
    unregister_provider,
)
from .classify import classify_failure, sanitize_error
from .extract_json import (
    clean_data,
    extract_json,
    normalize_columns,
)
from .health_check import check_minimax_cli, check_zai_mcp, health_check_all
from .router import RouterConfig, VisionProviderRouter

__all__ = [
    "AttemptRecord",
    "FailureKind",
    "FailureReason",
    "ProviderError",
    "ProviderResult",
    "VisionProvider",
    "RouterConfig",
    "VisionProviderRouter",
    "get_provider",
    "list_providers",
    "register_provider",
    "unregister_provider",
    "bootstrap_registry",
    "check_minimax_cli",
    "check_zai_mcp",
    "health_check_all",
    "classify_failure",
    "sanitize_error",
    "clean_data",
    "extract_json",
    "normalize_columns",
    "clear_registry",
    "is_registered",
]


def bootstrap_registry() -> None:
    """Register built-in providers (idempotent).

    Safe to call multiple times: ``register_provider`` raises ValueError on
    duplicate; we swallow it. Tests can call ``unregister_provider`` first to
    install a mock under the same name.
    """
    # Imported here to avoid circular imports.
    from .minimax_provider import MiniMaxVisionProvider
    from .zai_provider import ZAIVisionProvider

    for name, cls in (
        ("minimax", MiniMaxVisionProvider),
        ("zai", ZAIVisionProvider),
    ):
        try:
            register_provider(name, cls)
        except ValueError:
            # Already registered (e.g. double-import); keep existing entry.
            pass


# Eagerly bootstrap on package import so callers can use the registry without
# having to remember to call bootstrap_registry() manually.
bootstrap_registry()
