"""Sequential fallback router for vision providers (SPEC-03-006 §4.4).

Tries providers in ``RouterConfig.provider_order``. On primary success, returns
the result with ``fallback_used=False``. On primary failure, instantiates the
next provider and retries. Never falls back twice (decision #6).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .base import AttemptRecord, ProviderError, ProviderResult, VisionProvider
from .registry import get_provider

ProviderFactory = Callable[..., VisionProvider]


@dataclass
class RouterConfig:
    """Configuration loaded from config.yaml.

    Defaults match DESIGN-03-006 §3.9.1: ``order=["minimax", "zai"]``,
    timeouts 120/90s. Empty dicts from old configs get these defaults.
    """

    provider_order: list[str] = field(default_factory=lambda: ["minimax", "zai"])
    primary_timeout_seconds: int = 120
    fallback_timeout_seconds: int = 90
    health_check_on_start: bool = True
    include_provider_status_in_debug: bool = True

    @classmethod
    def from_dict(cls, data: dict | None) -> "RouterConfig":
        """Construct from a config dict. Missing keys → defaults.

        ``provider_order`` is accepted either as ``order`` (canonical) or
        ``provider_order`` (alias). Empty / missing → ["minimax", "zai"].
        """
        data = data or {}
        order = data.get("order") or data.get("provider_order") or ["minimax", "zai"]
        if not isinstance(order, list) or not order:
            order = ["minimax", "zai"]
        return cls(
            provider_order=list(order),
            primary_timeout_seconds=int(data.get("primary_timeout_seconds", 120)),
            fallback_timeout_seconds=int(data.get("fallback_timeout_seconds", 90)),
            health_check_on_start=bool(data.get("health_check_on_start", True)),
            include_provider_status_in_debug=bool(
                data.get("include_provider_status_in_debug", True)
            ),
        )


class VisionProviderRouter:
    """Sequential provider router with single fallback (decision #6).

    On primary success → returns ProviderResult(fallback_used=False).
    On primary failure → tries fallback once, no further retries.
    On double failure → raises RuntimeError with both providers' messages.
    """

    def __init__(
        self,
        config: RouterConfig | None = None,
        *,
        factories: dict[str, ProviderFactory] | None = None,
        output_dir: Path | str | None = None,
        date_str: str | None = None,
    ) -> None:
        self.config = config or RouterConfig()
        self._factories = factories  # optional override map (name -> factory)
        self.output_dir = output_dir
        self.date_str = date_str
        # Track which providers we actually instantiated (for UT-20).
        self._instantiated: dict[str, VisionProvider] = {}

    # -- public ----------------------------------------------------------

    async def describe(self, image_path: Path) -> ProviderResult:
        """Run primary → fallback chain for one image.

        Raises:
            FileNotFoundError: if image_path doesn't exist.
            RuntimeError: if all providers in the chain fail.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        attempts: list[AttemptRecord] = []
        errors: list[str] = []
        last_failure_messages: list[str] = []

        for index, name in enumerate(self.config.provider_order):
            try:
                provider = self._instantiate(name)
            except KeyError as e:
                last_failure_messages.append(f"[{name}] unknown provider: {e}")
                attempts.append(AttemptRecord(
                    provider=name,
                    success=False,
                    duration_ms=0,
                    error_message=str(e),
                ))
                continue

            timeout = (
                self.config.primary_timeout_seconds
                if index == 0
                else self.config.fallback_timeout_seconds
            )
            # Apply timeout to the provider's own default if it accepts one.
            try:
                result = await asyncio.wait_for(
                    provider.describe(image_path),
                    timeout=timeout + 30,  # allow extra buffer for the provider's own loop
                )
            except ProviderError as e:
                attempts.append(AttemptRecord(
                    provider=name,
                    success=False,
                    duration_ms=0,
                    error_kind=e.failure.kind,
                    error_message=e.failure.message,
                ))
                errors.append(f"[{name}] {e.failure.kind.value}: {e.failure.message}")
                last_failure_messages.append(
                    f"[{name}] {e.failure.kind.value}: {e.failure.message}"
                )
                continue
            except Exception as e:
                # Unclassified exception: classify generically.
                attempts.append(AttemptRecord(
                    provider=name,
                    success=False,
                    duration_ms=0,
                    error_message=str(e)[:200],
                ))
                errors.append(f"[{name}] unknown: {str(e)[:200]}")
                last_failure_messages.append(f"[{name}] unknown: {str(e)[:200]}")
                continue

            # Success: attach Router-level metadata
            result.provider_status["attempts"] = (
                attempts + list(result.provider_status.get("attempts") or [])
            ) if isinstance(result.provider_status.get("attempts"), list) else (
                attempts + [
                    AttemptRecord(
                        provider=name, success=True, duration_ms=0
                    ).to_dict()
                ]
            )
            result.provider_status["name"] = name
            result.provider_status["fallback_used"] = index > 0
            # Errors are always the cumulative list of *prior* failures
            # (successful path adds no error)
            result.provider_status["errors"] = errors
            return result

        # All providers failed
        joined = " / ".join(last_failure_messages) or "no providers configured"
        # SPEC-03-006 F-012 / Review M1: cache the merged audit state on
        # the Router instance so callers (notably the Extractor layer) can
        # write a Router-level error.json that mirrors the
        # provider_status shape used by successful results. Without this
        # cache the attempts/errors lists are lost as soon as the local
        # scope unwinds.
        self._last_failed_status = {
            "name": "router",
            "fallback_used": True,
            "attempts": [a.to_dict() for a in attempts],
            "errors": list(errors),
        }
        raise RuntimeError(f"all providers failed: {joined}")

    async def health_check_all(self) -> dict[str, bool]:
        """Run health_check on every provider in provider_order. Never raises."""
        results: dict[str, bool] = {}
        for name in self.config.provider_order:
            try:
                provider = self._instantiate(name)
                results[name] = await provider.health_check()
            except Exception:
                results[name] = False
        return results

    @property
    def instantiated_providers(self) -> dict[str, VisionProvider]:
        """Names → provider instances that have been materialised (UT-20)."""
        return dict(self._instantiated)

    # -- internals -------------------------------------------------------

    def _instantiate(self, name: str) -> VisionProvider:
        if name in self._instantiated:
            return self._instantiated[name]
        if self._factories is not None and name in self._factories:
            provider = self._factories[name](
                output_dir=self.output_dir, date_str=self.date_str
            )
        else:
            provider = get_provider(
                name,
                output_dir=self.output_dir,
                date_str=self.date_str,
            )
        self._instantiated[name] = provider
        return provider
