"""Minimal async retry helper with exponential backoff.

Only transient network failures are retried; anything else propagates on the
first try so a programming error is never masked by retries.

Provenance note: :class:`~backend.services.price_service.PriceService` does
**not** use this helper. Its quote path already retries with a domain-aware
policy that classifies HTTP 429/401 as *non-transient* and aborts the whole
price stage instead of burning three attempts per ticker — replacing it with
this generic helper would reintroduce that thundering-herd behaviour. This
helper exists for the remaining async network call sites.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

# Errors worth a retry: socket timeouts and connection failures. ``OSError`` is
# the common parent, but the spec names these two explicitly to stay narrow.
RETRYABLE_ERRORS: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError)


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
            delay = min(base_delay * 2 ** (attempt - 1), max_delay)
            if delay > 0:
                await asyncio.sleep(delay)
    raise AssertionError("retry loop exited without returning")  # pragma: no cover
