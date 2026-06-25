"""Z.AI (GLM) Vision MCP provider (SPEC-03-006 F-004 + §4.6).

Connects to the registered ``Z.AI Vision MCP`` server via Hermes MCP SDK
(stdio transport) and calls its image-analysis tool with the shared
``VISION_PROMPT``.

Design choices (DESIGN-03-006 §3.8):
  - Lazy connect: the MCP client is created on the first ``describe()`` call.
    This guarantees zero overhead on the happy path (UT-20).
  - No retries inside this provider (DESIGN decision #6).
  - Tool name + arguments: deferred to runtime discovery. The MCP server's
    tool list is enumerated after the first ``list_tools()`` call; the first
    tool whose name contains "image" or "analyze" is used. Falls back to the
    first tool in the list. This keeps the provider robust to upstream
    tool-name changes.
  - The provider is importable even when ``mcp`` is not installed; only
    ``describe()`` requires the SDK.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pandas as pd

from .base import (
    AttemptRecord,
    FailureKind,
    FailureReason,
    ProviderError,
    ProviderResult,
    VisionProvider,
)
from .classify import classify_failure, sanitize_error
from .extract_json import clean_data, extract_json, normalize_columns
from .prompts import VISION_PROMPT


# MCP server name in ~/.hermes/profiles/yquant/config.yaml
DEFAULT_MCP_SERVER_NAME = "Z.AI Vision MCP"


class ZAIVisionProvider(VisionProvider):
    """Z.AI (GLM) Vision MCP provider.

    Connects to the Z.AI MCP server registered under ``mcp_servers`` in the
    Hermes profile config, calls the image-analysis tool, and parses the
    result through the shared JSON / column / data pipeline.
    """

    name = "zai"

    def __init__(
        self,
        *,
        output_dir: Path | str | None = None,
        date_str: str | None = None,
        mcp_server_name: str = DEFAULT_MCP_SERVER_NAME,
        timeout_seconds: int = 90,
        config_path: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(output_dir=output_dir, date_str=date_str, **kwargs)
        self.mcp_server_name = mcp_server_name
        self.timeout_seconds = timeout_seconds
        self.config_path = config_path  # if None, ZAIMCPClient falls back to ~/.hermes
        self._mcp_client: Any = None  # ZAIMCPClient, lazy-initialised

    async def health_check(self) -> bool:
        """Return True if ``Z_AI_API_KEY`` is in env. Never raises."""
        try:
            return bool(os.environ.get("Z_AI_API_KEY"))
        except Exception:
            return False

    async def describe(self, image_path: Path) -> ProviderResult:
        """Call the Z.AI MCP image-analysis tool and return a ProviderResult.

        Raises:
            FileNotFoundError: if image_path doesn't exist.
            ProviderError: classified failure (MCP_UNAVAILABLE, PARSE_ERROR, ...).
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        attempts: list[AttemptRecord] = []
        errors: list[str] = []

        # Lazy MCP client init.
        if self._mcp_client is None:
            try:
                self._mcp_client = ZAIMCPClient(
                    server_name=self.mcp_server_name,
                    config_path=self.config_path,
                )
            except Exception as e:
                failure = classify_failure(exception=e)
                attempts.append(AttemptRecord(
                    provider=self.name,
                    success=False,
                    duration_ms=0,
                    error_kind=FailureKind.MCP_UNAVAILABLE,
                    error_message=sanitize_error(str(e)),
                ))
                errors.append(
                    f"[{self.name}] mcp_unavailable: {sanitize_error(str(e))}"
                )
                raise ProviderError(
                    self.name,
                    FailureReason(
                        FailureKind.MCP_UNAVAILABLE,
                        False,
                        sanitize_error(str(e)),
                    ),
                )

        started = time.monotonic()
        try:
            raw = await self._mcp_client.call_image_analysis(
                image_path=image_path,
                prompt=VISION_PROMPT,
                timeout_seconds=self.timeout_seconds,
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - started) * 1000)
            failure = classify_failure(exception=e)
            attempts.append(AttemptRecord(
                provider=self.name,
                success=False,
                duration_ms=duration_ms,
                error_kind=failure.kind,
                error_message=failure.message,
            ))
            errors.append(f"[{self.name}] {failure.kind.value}: {failure.message}")
            raise ProviderError(self.name, failure)

        duration_ms = int((time.monotonic() - started) * 1000)
        rows = extract_json(raw)
        if not rows:
            failure = FailureReason(
                FailureKind.PARSE_ERROR,
                False,
                sanitize_error("no JSON array in zai output"),
            )
            attempts.append(AttemptRecord(
                provider=self.name,
                success=False,
                duration_ms=duration_ms,
                error_kind=failure.kind,
                error_message=failure.message,
            ))
            errors.append(f"[{self.name}] {failure.kind.value}: {failure.message}")
            raise ProviderError(self.name, failure)

        df = pd.DataFrame(rows)
        df = normalize_columns(df)
        df = clean_data(df)
        print(f"  [{self.name} Vision] {image_path.name}: {len(df)} rows, {len(df.columns)} columns")
        attempts.append(AttemptRecord(
            provider=self.name,
            success=True,
            duration_ms=duration_ms,
            error_kind=None,
            error_message=None,
        ))
        return ProviderResult(
            df=df,
            source_path=str(image_path),
            provider_status={
                "name": self.name,
                "fallback_used": False,
                "attempts": [a.to_dict() for a in attempts],
                "errors": errors,
            },
        )


class ZAIMCPClient:
    """Thin wrapper around the Hermes MCP SDK stdio client.

    Why a separate class? It keeps the provider import-safe (no MCP SDK
    needed at module import time) and gives tests an easy way to swap in
    a fake.
    """

    def __init__(self, *, server_name: str, config_path: str | None = None) -> None:
        # Lazy import: ``mcp`` is optional at provider import time so the
        # rest of the data-pipeline still loads when the SDK isn't installed.
        try:
            from mcp import ClientSession, StdioServerParameters  # noqa: F401
        except ImportError as e:  # pragma: no cover - import guard
            raise RuntimeError(
                "mcp SDK not installed; install `mcp` to use ZAIVisionProvider"
            ) from e
        self._server_name = server_name
        self._config_path = config_path
        # StdioServerParameters is constructed from the server's registered
        # config in ``_load_server_params``. We don't start the subprocess
        # here — that happens in ``call_image_analysis``.
        self._params = self._load_server_params()

    def _load_server_params(self):
        """Read ~/.hermes/profiles/yquant/config.yaml and build StdioServerParameters."""
        # Lazy import: keep optional.
        from mcp import StdioServerParameters

        import json
        cfg_path = self._config_path
        if cfg_path is None:
            cfg_path = str(
                Path(os.path.expanduser("~/.hermes/profiles/yquant/config.yaml"))
            )
        if not os.path.exists(cfg_path):
            raise RuntimeError(
                f"Z.AI MCP client: config not found at {cfg_path}; "
                f"set ZAIVisionProvider(config_path=...) explicitly"
            )
        # Minimal YAML-free parse: find the 'mcp_servers:' block and read
        # the indented child key. Avoids requiring PyYAML.
        with open(cfg_path) as f:
            text = f.read()
        servers = _parse_mcp_servers(text)
        if self._server_name not in servers:
            raise RuntimeError(
                f"Z.AI MCP client: server '{self._server_name}' not found in {cfg_path}; "
                f"registered={sorted(servers)}"
            )
        spec = servers[self._server_name]
        command = spec.get("command")
        args = list(spec.get("args") or [])
        env = dict(spec.get("env") or {})
        # Resolve ${VAR} placeholders using current process env, then merge
        # with the parent environment so the subprocess inherits PATH, HOME,
        # and other variables needed by npx/node/uvx.
        resolved = _resolve_env(env, os.environ)
        merged = dict(os.environ)  # inherit full parent environment
        merged.update(resolved)    # server-specific vars take precedence
        if not command:
            raise RuntimeError(
                f"Z.AI MCP client: server '{self._server_name}' has no command"
            )
        return StdioServerParameters(command=command, args=args, env=merged)

    async def call_image_analysis(
        self,
        *,
        image_path: Path,
        prompt: str,
        timeout_seconds: int,
    ) -> str:
        """Open stdio, list tools, call the image-analysis tool, return text.

        ``prompt`` and ``image_path`` are sent together in the call. The
        concrete argument names depend on the upstream tool's schema; we try
        a few common ones and trust whatever the server reports back.
        """
        # Lazy imports (so the rest of the module loads without mcp).
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        image_path = Path(image_path)
        async with stdio_client(self._params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                tools = tools_result.tools if hasattr(tools_result, "tools") else tools_result
                if not tools:
                    raise RuntimeError("Z.AI MCP server returned no tools")
                tool = _pick_image_tool(tools)
                arguments = _build_tool_arguments(tool, image_path, prompt)
                result = await session.call_tool(tool.name, arguments=arguments)
                # Result is a CallToolResult; content is a list of content parts.
                return _extract_text_from_result(result)


def _parse_mcp_servers(text: str) -> dict[str, dict]:
    """Parse ``mcp_servers: { Name: {command: ..., args: [...], env: {...}} }``
    without requiring PyYAML. Sufficient for the Hermes config format.
    """
    servers: dict[str, dict] = {}
    lines = text.splitlines()
    in_block = False
    block_indent = 0
    current_name: str | None = None
    current_dict: dict | None = None
    current_list_key: str | None = None

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    for line in lines:
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            continue
        indent = indent_of(line)
        content = stripped.lstrip()

        if not in_block:
            if content == "mcp_servers:":
                in_block = True
                block_indent = indent
            continue

        # We've left the block if indent drops to block_indent or below.
        if indent <= block_indent and content and not content.startswith("-"):
            in_block = False
            current_name = None
            current_dict = None
            current_list_key = None
            continue

        if indent == block_indent + 2:
            # New server entry: "Name:" with deeper indent than block.
            if ":" in content:
                name, _, _ = content.partition(":")
                name = name.strip().strip('"').strip("'")
                if name and not name.startswith("-"):
                    current_name = name
                    current_dict = {}
                    servers[name] = current_dict
                    current_list_key = None
            continue

        if current_dict is None:
            continue

        # Property line (key: value)
        if ":" in content and not content.startswith("-"):
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                # Nested block or list (next lines indented further)
                current_list_key = key
                continue
            # Scalar value
            current_list_key = None
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                items = [s.strip().strip('"').strip("'") for s in _split_top_commas(inner)]
                current_dict[key] = [x for x in items if x]
            elif value.startswith("{") and value.endswith("}"):
                current_dict[key] = value
            else:
                current_dict[key] = _coerce_scalar(value)
            continue

        # List item
        if content.startswith("- "):
            item = content[2:].strip()
            if current_list_key is not None:
                current_dict.setdefault(current_list_key, [])
                current_dict[current_list_key].append(_coerce_scalar(item))
            continue

    return servers


def _split_top_commas(s: str) -> list[str]:
    """Split on top-level commas (ignoring those inside [ ] or { })."""
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


def _coerce_scalar(value: str):
    """Coerce a YAML-ish scalar to int/bool/str."""
    v = value.strip().strip('"').strip("'")
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


def _resolve_env(env: dict, base: dict) -> dict:
    """Resolve ${VAR} placeholders against the given env mapping."""
    import re
    pat = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
    out: dict = {}
    for k, v in env.items():
        if isinstance(v, str):
            out[k] = pat.sub(lambda m: base.get(m.group(1), m.group(0)), v)
        else:
            out[k] = v
    return out


def _pick_image_tool(tools: list) -> Any:
    """Choose the image-analysis tool from the server's list.

    Heuristics:
      1. Name contains "image" (case-insensitive).
      2. Name contains "analyze"/"analyse" (fallback).
      3. Otherwise: the first tool.
    """
    for t in tools:
        name = (getattr(t, "name", "") or "").lower()
        if "image" in name:
            return t
    for t in tools:
        name = (getattr(t, "name", "") or "").lower()
        if "analyze" in name or "analyse" in name:
            return t
    return tools[0]


def _build_tool_arguments(tool: Any, image_path: Path, prompt: str) -> dict:
    """Build tool-call arguments, honouring the tool's inputSchema if present.

    The Hermes / Z.AI MCP server's tool takes either an image path or URL plus
    a prompt. We try common key names; the server's tool description is the
    authoritative source of truth if exposed.
    """
    image_str = str(image_path.resolve())
    # Try to read inputSchema for required field names.
    schema = getattr(tool, "inputSchema", None) or {}
    required = list(schema.get("required") or []) if isinstance(schema, dict) else []
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}

    candidate_args: dict[str, Any] = {
        "image": image_str,
        "image_path": image_str,
        "path": image_str,
        "url": image_str,
        "prompt": prompt,
        "text": prompt,
    }
    # Use the first matching key from the schema's properties if any are
    # declared; this keeps us robust to upstream renames.
    args: dict[str, Any] = {}
    if isinstance(properties, dict) and properties:
        for prop_name in properties:
            if prop_name in candidate_args:
                args[prop_name] = candidate_args[prop_name]
            else:
                # Best-effort: if it's a string field, send the image; if the
                # field name mentions prompt, send the prompt.
                lname = prop_name.lower()
                if "image" in lname or "path" in lname or "url" in lname:
                    args[prop_name] = image_str
                elif "prompt" in lname or "text" in lname or "query" in lname:
                    args[prop_name] = prompt
    if not args:
        # No schema: send both common keys.
        args = {"image": image_str, "prompt": prompt}
    return args


def _extract_text_from_result(result: Any) -> str:
    """Extract concatenated text from a CallToolResult.

    ``result.content`` is a list of content parts (TextContent, ImageContent, ...).
    We concatenate all text parts. For list/dict content, we ``json.dumps`` it.
    """
    parts: list[str] = []
    content = getattr(result, "content", None) or []
    for part in content:
        # TextContent-like: .text
        text = getattr(part, "text", None)
        if text:
            parts.append(str(text))
            continue
        # Embedded JSON / dict / list
        if isinstance(part, (dict, list)):
            import json
            parts.append(json.dumps(part, ensure_ascii=False))
    if parts:
        return "\n".join(parts)
    # Last resort: full result as string.
    return str(result)
