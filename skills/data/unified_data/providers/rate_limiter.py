"""Rate limiting and retry helpers for external providers (Phase 1B-A).

This module is deliberately small and dependency-free. It exposes two
composable primitives:

* :class:`RateLimiter` — a token-bucket rate limiter that callers use
  to throttle outbound calls. Default budget is **200 requests per
  minute** (matches the Tushare free-tier guideline).
* :func:`with_retry` — a decorator that wraps a callable with bounded
  exponential-backoff retries. Default is 3 attempts with a 1.0-second
  back-off base, doubling on every retry.

Both primitives are framework-agnostic. They are designed to be used by
:class:`BaseExternalProvider` (see ``base_external.py``), but can also
be applied independently by other call sites that need similar
behaviour.

Design references
-----------------
* SPEC-03-008 §3.3 (TP-108/109, AK-108)
* DESIGN-03-008 §3.3.5 (BaseExternalProvider composition)
"""

from __future__ import annotations

import threading
import time
from functools import wraps
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


# Exceptions that should trigger a retry. ``ProviderError`` is intentionally
# NOT in this set — caller-visible failures should bubble up unchanged so
# the Router can record them in ``source_trace``.
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
)


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token-bucket rate limiter.

    The bucket starts full and refills at a rate of ``max_per_minute / 60``
    tokens per second. ``acquire()`` blocks until a token is available.

    Args:
        max_per_minute: Maximum number of acquisitions per rolling minute.
            Must be a positive integer.
    """

    def __init__(self, max_per_minute: int) -> None:
        if not isinstance(max_per_minute, int) or max_per_minute <= 0:
            raise ValueError(
                f"max_per_minute must be a positive integer, got {max_per_minute!r}"
            )
        self._max = max_per_minute
        self._refill_per_second: float = max_per_minute / 60.0
        self._tokens: float = float(max_per_minute)
        self._last_refill: float = time.monotonic()
        self._lock = threading.Lock()

    @property
    def max_per_minute(self) -> int:
        """Configured ceiling (requests/minute)."""
        return self._max

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._tokens = min(
            float(self._max), self._tokens + elapsed * self._refill_per_second
        )
        self._last_refill = now

    def acquire(self, *, blocking: bool = True, timeout: float | None = None) -> bool:
        """Acquire one token.

        Args:
            blocking: If ``True`` (default), wait until a token is
                available. If ``False``, return immediately.
            timeout: Maximum seconds to wait when ``blocking`` is
                ``True``. ``None`` means wait indefinitely.

        Returns:
            ``True`` when a token was acquired, ``False`` only when
            ``blocking=False`` and the bucket was empty.
        """
        deadline: float | None = None
        if timeout is not None:
            deadline = time.monotonic() + timeout
        with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                if not blocking:
                    return False
                # Compute how long until 1 token is available.
                need = 1.0 - self._tokens
                wait = need / self._refill_per_second if self._refill_per_second > 0 else 1.0
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    wait = min(wait, remaining)
                # Release the lock while we sleep so other threads can also
                # refill, then re-acquire.
                self._lock.release()
                try:
                    time.sleep(wait)
                finally:
                    self._lock.acquire()


# ---------------------------------------------------------------------------
# with_retry
# ---------------------------------------------------------------------------


def with_retry(
    *,
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_factor: float = 2.0,
    retryable: tuple[type[BaseException], ...] = _RETRYABLE_EXCEPTIONS,
) -> Callable[[F], F]:
    """Decorate ``func`` with bounded exponential-backoff retries.

    Args:
        max_attempts: Maximum number of attempts (>=1). ``1`` means
            "no retry, just call once".
        backoff_base: Base sleep time (seconds) before the second
            attempt. Doubles for each subsequent retry.
        backoff_factor: Multiplier applied to the back-off on every
            retry. ``2.0`` doubles; ``1.0`` keeps the same delay.
        retryable: Tuple of exception types that should trigger a
            retry. Other exceptions bubble up immediately.

    Returns:
        A decorator that wraps the function with the retry policy.

    Raises:
        ValueError: When ``max_attempts < 1``, ``backoff_base < 0`` or
            ``backoff_factor < 1``.
    """
    if max_attempts < 1:
        raise ValueError(
            f"max_attempts must be >= 1, got {max_attempts!r}"
        )
    if backoff_base < 0:
        raise ValueError(
            f"backoff_base must be >= 0, got {backoff_base!r}"
        )
    if backoff_factor < 1:
        raise ValueError(
            f"backoff_factor must be >= 1, got {backoff_factor!r}"
        )

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 1
            delay = backoff_base
            while True:
                try:
                    return func(*args, **kwargs)
                except retryable:
                    if attempt >= max_attempts:
                        raise
                    time.sleep(delay)
                    delay *= backoff_factor
                    attempt += 1

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = ["RateLimiter", "with_retry"]