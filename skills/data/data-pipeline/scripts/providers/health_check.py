"""Provider readiness checks (SPEC-03-006 §5.2)."""
from __future__ import annotations

from typing import Any

from .router import RouterConfig, VisionProviderRouter


async def health_check_all(config: RouterConfig | dict | None = None) -> dict[str, bool]:
    """Run health checks on every provider in the configured chain.

    Accepts either a RouterConfig instance or a raw dict (forward-compat with
    the config.yaml ocr_providers block). Returns {name: ok_bool}. Never raises.
    """
    if isinstance(config, dict):
        config = RouterConfig.from_dict(config)
    if config is None:
        config = RouterConfig()
    router = VisionProviderRouter(config=config)
    return await router.health_check_all()


async def check_minimax_cli() -> bool:
    """Return True if ``mmx`` is on PATH."""
    import shutil
    try:
        return shutil.which("mmx") is not None
    except Exception:
        return False


async def check_zai_mcp() -> bool:
    """Return True if ``Z_AI_API_KEY`` is in os.environ."""
    import os
    try:
        return bool(os.environ.get("Z_AI_API_KEY"))
    except Exception:
        return False
