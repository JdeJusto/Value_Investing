"""Minimal retry helpers with exponential backoff (sync and async).

Only transient network failures are retried; anything else propagates on the
first try so a programming error is never masked by retries.

Provenance note: :class:`~backend.services.price_service.PriceService` does
**not** use these helpers. Its quote path already retries with a domain-aware
policy that classifies HTTP 429/401 as *non-transient* and aborts the whole
price stage instead of burning three attempts per ticker — replacing it with a
generic helper would reintroduce that thundering-herd behaviour. The same
applies to the Yahoo/SEC preflights, which retry internally with the same
domain-aware verdicts. These helpers exist for the remaining network call sites:
async ones use :func:`retry_async`, synchronous ones use :func:`with_retry`.
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Awaitable, Callable

# Errors worth a retry: socket timeouts and connection failures. ``OSError`` is
# the common parent, but the spec names these two explicitly to stay narrow.
RETRYABLE_ERRORS: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError)


def _backoff(attempt: int, base_delay: float, max_delay: float) -> float:
    """``base_delay * 2 ** (attempt - 1)`` capped at ``max_delay`` (>0 guard)."""
    return min(base_delay * 2 ** (attempt - 1), max_delay)


async def retry_async[T](
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 4.0,
) -> T:
    """Call ``fn`` and retry it on transient network errors.

    Delays are ``base_delay * 2 ** (attempt - 1)``, capped at ``max_delay``.
    The final failure is re-raised unchanged.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except RETRYABLE_ERRORS:
            if attempt == attempts:
                raise
            delay = _backoff(attempt, base_delay, max_delay)
            if delay > 0:
                await asyncio.sleep(delay)
    raise AssertionError("retry loop exited without returning")  # pragma: no cover


def with_retry[T](
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 4.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: retry a synchronous callable on transient network errors.

    Same policy as :func:`retry_async` (``base_delay * 2 ** (attempt - 1)``,
    capped at ``max_delay``); the final failure is re-raised unchanged and a
    non-transient exception propagates on the first try. ``sleep`` is
    injectable so tests need not wait in real time.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except RETRYABLE_ERRORS:
                    if attempt == attempts:
                        raise
                    delay = _backoff(attempt, base_delay, max_delay)
                    if delay > 0:
                        sleep(delay)
            raise AssertionError(  # pragma: no cover
                "retry loop exited without returning"
            )

        return wrapper

    return decorator
