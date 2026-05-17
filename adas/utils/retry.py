"""Retry utility for transient network and API failures."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")

# HTTP status codes that indicate a transient server-side failure worth retrying.
RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def call_with_retry(
    fn: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 1.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Call fn(), retrying on retryable_exceptions with exponential backoff.

    Raises the last exception when all attempts are exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(base_delay * (2 ** attempt))
    assert last_exc is not None
    raise last_exc
