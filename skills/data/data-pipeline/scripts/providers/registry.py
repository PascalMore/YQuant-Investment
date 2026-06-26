"""Vision provider registry (dict-based; SPEC-03-006 §4.3).

Provider implementations register themselves by stable name; Router looks them
up at construction time. Tests use ``unregister_provider`` for isolation.
"""
from __future__ import annotations

from typing import Any, Callable

from .base import VisionProvider

ProviderFactory = Callable[..., VisionProvider]

_REGISTRY: dict[str, type[VisionProvider]] = {}


def register_provider(name: str, cls: type[VisionProvider]) -> None:
    """Register a VisionProvider implementation under a stable string name.

    Raises:
        ValueError: if name is already registered.
        TypeError:  if cls is not a VisionProvider subclass.
    """
    if name in _REGISTRY:
        raise ValueError(
            f"provider '{name}' already registered; unregister first to override"
        )
    if not isinstance(cls, type) or not issubclass(cls, VisionProvider):
        raise TypeError(f"{cls} is not a VisionProvider subclass")
    _REGISTRY[name] = cls


def unregister_provider(name: str) -> None:
    """Remove a provider from the registry (used in tests / hot reload)."""
    _REGISTRY.pop(name, None)

def get_provider(
    name: str,
    *,
    output_dir: Any = None,
    **kwargs: Any,
) -> VisionProvider:
    """
    Instantiate a registered provider by name.

    Raises:
        KeyError: if name is not registered.
    """
    if name not in _REGISTRY:
        raise KeyError(f"unknown provider '{name}'; registered={sorted(_REGISTRY)}")
    return _REGISTRY[name](output_dir=output_dir, **kwargs)


def list_providers() -> list[str]:
    """Return sorted list of registered provider names."""
    return sorted(_REGISTRY)


def is_registered(name: str) -> bool:
    """Return True if name is in the registry (cheap, no instantiation)."""
    return name in _REGISTRY


def clear_registry() -> None:
    """Remove all entries from the registry. Test-only helper."""
    _REGISTRY.clear()
