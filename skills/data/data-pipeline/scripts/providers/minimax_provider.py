"""MiniMax Vision provider (SPEC-03-006 F-003).

Wraps the existing ``mmx vision describe`` subprocess call, the 3-attempt
exponential-backoff retry loop, and the shared ``extract_json`` /
``normalize_columns`` / ``clean_data`` pipeline.

Behaviour parity with the legacy ``minimax_image_extractor._run_vision_extraction``:
  - subprocess.run([..., timeout=120])
  - 3 attempts, exponential backoff (1s, 2s) on retryable failures
  - debug JSON written to debug_dir for retry/error events
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from datetime import datetime
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


class MiniMaxVisionProvider(VisionProvider):
    """MiniMax CLI vision provider.

    Uses ``mmx vision describe --image <path> --prompt "<prompt>"`` and parses
    the JSON wrapper format ``{"content": "...", "base_resp": {...}}`` before
    delegating to the shared JSON / column / data pipeline.
    """

    name = "minimax"

    def __init__(
        self,
        *,
        output_dir: Path | str | None = None,
        date_str: str | None = None,
        timeout_seconds: int = 120,
        max_attempts: int = 3,
        **kwargs: Any,
    ) -> None:
        super().__init__(output_dir=output_dir, date_str=date_str, **kwargs)
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.debug_dir = self.output_dir  # may be None
        if self.debug_dir is not None:
            self.debug_dir.mkdir(parents=True, exist_ok=True)

    async def health_check(self) -> bool:
        """Return True if ``mmx`` is on PATH. Never raises."""
        try:
            return shutil.which("mmx") is not None
        except Exception:
            return False

    async def describe(self, image_path: Path) -> ProviderResult:
        """Run mmx vision describe with up to ``max_attempts`` retries.

        Returns a ProviderResult with ``name='minimax'`` and
        ``fallback_used=False`` on success.

        Raises:
            FileNotFoundError: if image_path doesn't exist.
            ProviderError: classified failure.
        """
        image_path = Path(image_path)
        # File-not-found on the *image* is a caller bug, not an upstream
        # provider failure. Raise FileNotFoundError so pipeline-level code
        # surfaces it clearly (mirrors the legacy behaviour).
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        attempts: list[AttemptRecord] = []
        errors: list[str] = []
        cmd = [
            "mmx", "vision", "describe",
            "--image", str(image_path),
            "--prompt", VISION_PROMPT,
        ]
        last_stdout = ""
        last_stderr = ""
        last_returncode: int | None = None
        last_exception: BaseException | None = None

        for attempt in range(1, self.max_attempts + 1):
            started = time.monotonic()
            try:
                proc = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout_seconds,
                    ),
                )
                duration_ms = int((time.monotonic() - started) * 1000)
                last_stdout, last_stderr, last_returncode = proc.stdout, proc.stderr, proc.returncode
                if proc.returncode == 0:
                    if attempts:
                        # Audit trail: retries that finally succeeded. The
                        # provider_status block carries the same shape as the
                        # final ProviderResult so the debug JSON is a
                        # self-contained failure log.
                        self._write_debug(
                            "retry",
                            image_path,
                            cmd,
                            attempts,
                            provider_status=self._build_debug_provider_status(attempts, errors),
                        )
                    return self._build_result(
                        image_path=image_path,
                        attempts=attempts,
                        errors=errors,
                        stdout=proc.stdout,
                    )
                # Non-zero returncode
                failure = classify_failure(
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    returncode=proc.returncode,
                )
                attempts.append(AttemptRecord(
                    provider=self.name,
                    success=False,
                    duration_ms=duration_ms,
                    error_kind=failure.kind,
                    error_message=failure.message,
                ))
                errors.append(f"[{self.name}] {failure.kind.value}: {failure.message}")
                if failure.retryable and attempt < self.max_attempts:
                    backoff = 2 ** (attempt - 1)
                    print(
                        f"  [{self.name} Vision] transient failure, retrying "
                        f"({attempt}/{self.max_attempts}) after {backoff}s..."
                    )
                    await asyncio.sleep(backoff)
                    continue
                self._write_debug(
                    "error",
                    image_path,
                    cmd,
                    attempts,
                    provider_status=self._build_debug_provider_status(attempts, errors),
                )
                raise ProviderError(self.name, failure)
            except subprocess.TimeoutExpired as e:
                duration_ms = int((time.monotonic() - started) * 1000)
                last_exception = e
                failure = classify_failure(exception=e)
                attempts.append(AttemptRecord(
                    provider=self.name,
                    success=False,
                    duration_ms=duration_ms,
                    error_kind=failure.kind,
                    error_message=failure.message,
                ))
                errors.append(f"[{self.name}] {failure.kind.value}: {failure.message}")
                if attempt < self.max_attempts:
                    backoff = 2 ** (attempt - 1)
                    print(
                        f"  [{self.name} Vision] Timeout, retrying "
                        f"({attempt}/{self.max_attempts}) after {backoff}s..."
                    )
                    await asyncio.sleep(backoff)
                    continue
                self._write_debug(
                    "error",
                    image_path,
                    cmd,
                    attempts,
                    provider_status=self._build_debug_provider_status(attempts, errors),
                )
                raise ProviderError(self.name, failure)
            except FileNotFoundError as e:
                # mmx not in PATH
                last_exception = e
                failure = classify_failure(exception=e)
                self._write_debug(
                    "error",
                    image_path,
                    cmd,
                    attempts,
                    provider_status=self._build_debug_provider_status(attempts, errors),
                )
                raise ProviderError(self.name, failure)

        # Defensive: should not be reached (loop either returns or raises).
        raise ProviderError(
            self.name,
            FailureReason(
                FailureKind.UNKNOWN,
                False,
                sanitize_error("exhausted retries without raising"),
            ),
        )

    # -- internals --------------------------------------------------------

    def _build_result(
        self,
        *,
        image_path: Path,
        attempts: list[AttemptRecord],
        errors: list[str],
        stdout: str,
    ) -> ProviderResult:
        output = (stdout or "").strip()
        # Unwrap mmx JSON wrapper if present.
        output = self._unwrap_mmx_response(output)
        if self.debug_dir is not None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            (self.debug_dir / f"pic_{ts}_vision_raw.json").write_text(
                output, encoding="utf-8"
            )
        rows = extract_json(output)
        if not rows:
            failure = FailureReason(
                FailureKind.PARSE_ERROR,
                False,
                sanitize_error("no JSON array in mmx output"),
            )
            raise ProviderError(self.name, failure)
        df = pd.DataFrame(rows)
        df = normalize_columns(df)
        df = clean_data(df)
        print(f"  [{self.name} Vision] {image_path.name}: {len(df)} rows, {len(df.columns)} columns")
        # Successful attempt is appended here so the router sees attempts=[..., success]
        duration_ms = 0  # cumulative; not critical for the success entry
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

    @staticmethod
    def _unwrap_mmx_response(raw: str) -> str:
        """Strip ``{"content": "...", "base_resp": {...}}`` wrapper if present."""
        try:
            wrapper = json.loads(raw)
            if isinstance(wrapper, dict) and "content" in wrapper:
                return str(wrapper["content"])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return raw

    def _build_debug_provider_status(
        self,
        attempts: list[AttemptRecord],
        errors: list[str],
        *,
        fallback_used: bool = False,
    ) -> dict[str, Any]:
        """Build the provider_status dict embedded in debug JSON payloads.

        Mirrors the SPEC-03-006 §4.7 contract: ``name / fallback_used /
        attempts / errors`` (4 keys). Used by ``_write_debug`` so that the
        debug JSON is a self-contained audit log even when no successful
        ProviderResult is produced.

        ``fallback_used`` defaults to False here because the provider itself
        has no notion of cross-provider fallback (Router's job). The Router
        layer overlays its own ``fallback_used`` marker when it propagates a
        successful result, but the debug JSON written at *failure* time
        always reflects the provider's local view.
        """
        return {
            "name": self.name,
            "fallback_used": fallback_used,
            "attempts": [a.to_dict() for a in attempts],
            "errors": list(errors),
        }

    def _write_debug(
        self,
        status: str,
        image_path: Path,
        cmd: list[str],
        attempts: list[AttemptRecord],
        *,
        provider_status: dict[str, Any] | None = None,
    ) -> Path | None:
        if self.debug_dir is None:
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_path = self.debug_dir / f"pic_{ts}_vision_{status}.json"
        payload: dict[str, Any] = {
            "status": status,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "image_path": str(image_path),
            "image_name": image_path.name,
            "command": cmd,
            "attempts": [a.to_dict() for a in attempts],
        }
        # SPEC-03-006 F-012 / A-004: debug JSON MUST include a top-level
        # ``provider_status`` field on failure paths so audit consumers can
        # join the debug trail with the Router-level provider_status without
        # re-parsing the attempts array.
        if provider_status is not None:
            payload["provider_status"] = provider_status
        debug_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return debug_path
