"""The probe: one function that asks a URL whether it is alive, and times it."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

# How long we wait for a reply before giving up. Without a timeout, a provider
# that accepts our connection and then goes silent would hang us forever.
DEFAULT_TIMEOUT_SECONDS = 5.0

# A reply slower than this is still a reply, but it is worth flagging.
#
# Was 1000ms, which was too tight. Healthy providers answer in 300-760ms when
# checked alone, but 1000-1450ms on the first request of a round, because each
# check pays for a fresh connection handshake. At 1000ms, Anthropic flipped
# between "up" and "slow" on a 119ms difference that meant nothing.
#
# 2000ms leaves room for that handshake, so "slow" means something is genuinely
# wrong. An alert that fires on noise is an alert people learn to ignore.
DEFAULT_SLOW_THRESHOLD_MS = 2000.0

UP = "up"
SLOW = "slow"
DOWN = "down"


@dataclass
class ProbeResult:
    """What one check found out."""

    url: str
    status: str  # one of UP, SLOW, DOWN
    response_time_ms: float
    status_code: int | None = None  # None when we never got a reply at all
    error: str | None = None  # why it failed, when it failed


async def check_url(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    slow_threshold_ms: float = DEFAULT_SLOW_THRESHOLD_MS,
) -> ProbeResult:
    """Send one GET request to `url` and report whether it is up, slow or down."""
    started = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(url)
    except httpx.RequestError as exc:
        # No usable reply: timeout, DNS failure, refused connection, TLS error.
        elapsed_ms = (time.perf_counter() - started) * 1000
        return ProbeResult(
            url=url,
            status=DOWN,
            response_time_ms=round(elapsed_ms, 1),
            error=type(exc).__name__,
        )

    elapsed_ms = (time.perf_counter() - started) * 1000

    if response.status_code >= 500:
        # The server answered, but only to say it is broken.
        status = DOWN
    elif elapsed_ms > slow_threshold_ms:
        status = SLOW
    else:
        # Anything else, including 401, counts as up: the server is alive and
        # answering us. A 401 means "I hear you, you just have no key".
        status = UP

    return ProbeResult(
        url=url,
        status=status,
        response_time_ms=round(elapsed_ms, 1),
        status_code=response.status_code,
    )
