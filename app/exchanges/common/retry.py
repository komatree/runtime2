"""Pure retry/backoff helpers.

Adapted selectively from the local legacy reference utilities. The `rand_fn`
hook keeps tests deterministic while allowing jitter in real adapters later.
"""

from __future__ import annotations

from typing import Callable


def exponential_backoff_seconds(
    attempt: int,
    *,
    base_seconds: float = 1.0,
    cap_seconds: float = 30.0,
    jitter: str = "full",
    rand_fn: Callable[[float, float], float] | None = None,
) -> float:
    """Return exponential backoff seconds with optional full jitter."""

    attempt = max(0, int(attempt))
    max_sleep = min(float(cap_seconds), float(base_seconds) * (2.0**attempt))
    if max_sleep <= 0:
        return 0.0
    if jitter == "full":
        if rand_fn is None:
            from random import uniform

            rand_fn = uniform
        return float(rand_fn(0.0, max_sleep))
    return max_sleep
