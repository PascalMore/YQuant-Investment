"""
MiniMax Image-to-Excel Extractor (refactored — RFC-03-006 / SPEC-03-006).

After the OCR Provider Fallback refactor this class is a thin adapter:
it owns the BaseExtractor contract (source_type / extract / validate_source)
and delegates the actual VLM call to ``VisionProviderRouter``.

Public surface (unchanged from pre-refactor):
    - source_type: str  -> "image_minimax"
    - __init__(output_dir)  : debug write dir
    - extract(source, **kwargs) -> list[dict]
    - validate_source(source) -> bool

The router pulls its provider chain from ``RouterConfig`` (defaults to
``["minimax", "zai"]``), so flipping the chain is a config-only change.
Downstream consumers of the returned record dict keep reading
``records[0]["df"]`` / ``records[0]["source_path"]``; the new
``records[0]["provider_status"]`` is an audit-only field.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseExtractor

try:
    from providers import RouterConfig, VisionProviderRouter
except ImportError as e:  # pragma: no cover - import guard
    raise ImportError(
        "MiniMaxImageExtractor requires the `providers` package on the import path. "
        "The pipeline entry-points (run_unified_image_pipeline.py etc.) add "
        "`scripts/` to sys.path automatically; if you import this class from "
        "another entry-point, add the same path manipulation first. "
        f"Original error: {e}"
    ) from e


class MiniMaxImageExtractor(BaseExtractor):
    """
    Adapter that exposes the legacy ``MiniMaxImageExtractor`` contract while
    routing OCR through ``VisionProviderRouter``.

    The class is intentionally minimal: a router instance per call keeps the
    happy path zero-overhead (router only instantiates the primary provider
    on success; the fallback is never constructed).
    """

    def __init__(
        self,
        output_dir: str = None,
        *,
        router_config: RouterConfig | None = None,
    ):
        """
        Args:
            output_dir: Directory for debug JSONs (pic_*_vision_*.json).
            router_config: Optional override for the provider chain. When
                ``None`` the router reads ``~/.hermes/profiles/yquant/config.yaml``
                (block ``ocr_providers``); when that is also missing the
                RouterConfig default of ``["minimax", "zai"]`` is used.
        """
        if output_dir is None:
            output_dir = (
                Path(__file__).resolve().parents[5]
                / "skills"
                / "data"
                / "source"
                / "smart-money"
            )
        self.output_dir = Path(output_dir)
        self.debug_dir = self.output_dir
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        self._router_config_override = router_config

    @property
    def source_type(self) -> str:
        return "image_minimax"

    async def extract(self, source: str | list[str], **kwargs: Any) -> list[dict]:
        """
        Run the configured provider chain on one or more images.

        Args:
            source: Single image path (str) or list of image paths.
            **kwargs: Reserved for future use; ignored today.

        Returns:
            List of dicts, each containing:
                - "df": DataFrame from parsed vision output
                - "source_path": original image path
                - "provider_status": audit dict (name, fallback_used,
                  attempts[], errors[])

        Raises:
            FileNotFoundError: if any image path does not exist.
            RuntimeError:      if every provider in the chain fails. The
                error is re-raised after a merged error.json is written to
                ``self.output_dir`` so audit consumers can inspect the
                Router-level provider_status on the all-providers-failed
                path (SPEC-03-006 F-012 / Review M1).
        """
        images = [source] if isinstance(source, str) else source
        results: list[dict] = []

        # Build the router once for the whole batch. Per-image the router
        # short-circuits on the first successful provider.
        router = self._build_router()

        for img_path in images:
            img_path = Path(img_path)
            if not img_path.exists():
                raise FileNotFoundError(f"Image not found: {img_path}")

            try:
                provider_result = await router.describe(img_path)
            except RuntimeError as router_error:
                # Both providers in the chain failed. The Router has already
                # recorded per-provider attempts internally; we synthesise a
                # Router-level provider_status and persist a merged
                # error.json before re-raising so the pipeline caller still
                # sees the original RuntimeError (SPEC §7.2 fail-fast).
                merged_status = self._build_router_error_status(
                    router_error, router
                )
                self._write_router_error_debug(img_path, router_error, merged_status)
                raise

            record = provider_result.to_record()
            # Defensive: ensure downstream consumers always see the same
            # top-level keys.
            record.setdefault("df", None)
            record.setdefault("source_path", str(img_path))
            record.setdefault("provider_status", provider_result.provider_status)
            results.append(record)

        return results

    async def validate_source(self, source: str | list[str]) -> bool:
        """Check that all image files exist."""
        images = [source] if isinstance(source, str) else source
        return all(Path(p).exists() for p in images)

    # -- internals ---------------------------------------------------------

    def _build_router(self) -> VisionProviderRouter:
        """Construct a router. Honours router_config override, else loads
        the ``ocr_providers`` block from the Hermes profile config; if that
        is also missing, falls back to RouterConfig() defaults."""
        if self._router_config_override is not None:
            config = self._router_config_override
        else:
            config = _load_router_config_from_yaml()
        return VisionProviderRouter(
            config=config,
            output_dir=self.output_dir,
        )

    # -- Router-level failure audit (SPEC-03-006 F-012 / Review M1) ---

    def _build_router_error_status(
        self,
        router_error: RuntimeError,
        router: VisionProviderRouter,
    ) -> dict[str, Any]:
        """Build a Router-level provider_status when all providers fail.

        Wraps the Router's joined error message in the standard
        ``provider_status`` shape (SPEC §4.7) so the audit field is never
        empty on the all-providers-failed path. Per-provider attempts and
        errors are pulled from the Router's last-failed audit cache
        (``_last_failed_status``), which the Router populates right before
        raising. The Router is the single source of truth for these
        values; this method only adapts the shape if the cache is
        unavailable.
        """
        from providers.classify import sanitize_error

        chain = list(router.config.provider_order or [])
        cache = getattr(router, "_last_failed_status", None) or {}

        if cache:
            # Router populated the cache — forward it as-is.
            return dict(cache)

        # Cache miss (e.g. construction errored before either provider
        # was instantiated). Fall back to a single error carrying the
        # joined RuntimeError message, sanitised, so the audit field
        # stays non-empty and downstream assertions can rely on it.
        return {
            "name": "router",
            "fallback_used": len(chain) > 1,
            "attempts": [],
            "errors": [sanitize_error(str(router_error))],
        }

    def _write_router_error_debug(
        self,
        image_path: Path,
        router_error: RuntimeError,
        merged_status: dict[str, Any],
    ) -> None:
        """Persist a merged Router-level error.json.

        Filename matches the existing ``pic_*_vision_*.json`` convention so
        audit tooling does not need to learn a new pattern. Silently
        returns when ``self.output_dir`` is not configured or cannot be
        written — debug writes must never mask the original error.
        """
        from datetime import datetime as _dt

        try:
            debug_dir = self.output_dir
            if debug_dir is None:
                return
            debug_dir.mkdir(parents=True, exist_ok=True)
            ts = _dt.now().strftime("%Y%m%d_%H%M%S")
            debug_path = debug_dir / f"pic_{ts}_vision_error.json"
            import json as _json

            payload = {
                "status": "error",
                "created_at": _dt.now().isoformat(timespec="seconds"),
                "image_path": str(image_path),
                "image_name": Path(image_path).name,
                "command": [],  # Router has no single command
                "attempts": merged_status.get("attempts", []),
                "provider_status": merged_status,
                "router_error": str(router_error),
            }
            debug_path.write_text(
                _json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as debug_exc:  # pragma: no cover - defensive
            # Debug write failure must not replace the original Router
            # error. Log to stderr for human inspection.
            import sys as _sys

            print(
                f"[MiniMaxImageExtractor] failed to persist router error "
                f"debug JSON: {debug_exc}",
                file=_sys.stderr,
            )


def _load_router_config_from_yaml() -> RouterConfig:
    """Read the ``ocr_providers`` block from the yquant profile config.

    Returns ``RouterConfig()`` defaults when the config file or the
    ``ocr_providers`` block is missing — keeps the pipeline runnable on
    legacy environments.
    """
    cfg_path = Path("~/.hermes/profiles/yquant/config.yaml").expanduser()
    if not cfg_path.exists():
        return RouterConfig()
    try:
        text = cfg_path.read_text(encoding="utf-8")
        block = _extract_yaml_block(text, "ocr_providers")
    except Exception:
        return RouterConfig()
    if not block:
        return RouterConfig()
    return RouterConfig.from_dict(block)


def _extract_yaml_block(text: str, key: str) -> dict:
    """Tiny YAML-ish reader: find ``key:`` at column 0 and parse its
    immediate child block as a dict. Sufficient for the flat
    ``ocr_providers`` block documented in SPEC-03-006 §5.1.

    Returns ``{}`` when the key is not present or its body cannot be
    parsed. We deliberately avoid PyYAML to keep the import surface
    small.
    """
    lines = text.splitlines()
    key_prefix = f"{key}:"
    start = -1
    for i, line in enumerate(lines):
        if line.rstrip() == key_prefix or line.startswith(key_prefix + " ") or line == key_prefix:
            start = i
            break
    if start < 0:
        return {}

    # Find the indentation of the first child line.
    child_indent: int | None = None
    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        child_indent = len(line) - len(line.lstrip(" "))
        break
    if child_indent is None:
        return {}

    out: dict = {}
    pending_list_key: str | None = None
    pending_list_indent: int | None = None

    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent < child_indent:
            break  # block ended
        if indent > child_indent:
            # Continuation of a previously started list.
            if pending_list_key and pending_list_indent is not None and indent == pending_list_indent:
                content = line.strip()
                if content.startswith("- "):
                    out.setdefault(pending_list_key, []).append(_coerce_scalar(content[2:]))
            continue

        content = line.strip()
        # New top-level child of ocr_providers
        pending_list_key = None
        pending_list_indent = None
        if ":" not in content:
            continue
        k, _, v = content.partition(":")
        k = k.strip()
        v = v.strip()
        if v == "":
            # Could be a nested dict (not expected here) or a list below.
            # Peek the next non-blank line to decide.
            peek_indent: int | None = None
            for nxt in lines[start + 2:]:
                if not nxt.strip() or nxt.lstrip().startswith("#"):
                    continue
                peek_indent = len(nxt) - len(nxt.lstrip(" "))
                break
            if peek_indent is not None and peek_indent > child_indent:
                # If the first non-blank child line starts with "- ", treat
                # as a list. Otherwise treat as a nested dict (we don't
                # support nested dicts in this block).
                first_child = next(
                    (l.strip() for l in lines[start + 2:] if l.strip() and not l.lstrip().startswith("#")),
                    "",
                )
                if first_child.startswith("- "):
                    pending_list_key = k
                    pending_list_indent = peek_indent
            continue
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            items = [s.strip().strip('"').strip("'") for s in _split_top_commas(inner)]
            out[k] = [x for x in items if x]
        else:
            out[k] = _coerce_scalar(v)
    return out


def _split_top_commas(s: str) -> list[str]:
    out: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in s:
        if ch in "[{(":
            depth += 1
            buf.append(ch)
        elif ch in "]})":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf))
    return out


def _coerce_scalar(v: str):
    v = v.strip().strip('"').strip("'")
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    if v.lower() in ("null", "~", ""):
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v
