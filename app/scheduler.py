"""Checking every provider on a timer, without anyone asking.

This is what turns the project from a button you press into a monitor that
watches things while you sleep.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict

from app.db import save_results
from app.metrics import record_round
from app.probe import check_url
from app.providers import PROVIDERS

logger = logging.getLogger(__name__)

# How long to wait between rounds. Configurable so tests and demos do not have
# to sit through a real minute, and so the interval can be raised on the server
# without changing code if a provider ever objects to the traffic.
DEFAULT_INTERVAL_SECONDS = 60.0


def interval_seconds() -> float:
    return float(os.getenv("CHECK_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS))


async def run_check_round() -> list[dict]:
    """Check every provider once, save the results, and return them."""
    names = list(PROVIDERS)

    # gather() starts all the checks at the same time instead of one after
    # another. Four 700ms checks take about 700ms, not 2.8 seconds.
    results = await asyncio.gather(*(check_url(PROVIDERS[name]) for name in names))

    payload = [
        {"provider": name, **asdict(result)}
        for name, result in zip(names, results)
    ]

    # sqlite3 is synchronous: it stops everything until the write finishes.
    # to_thread moves it off to the side so the server can keep answering
    # other requests while the disk does its work.
    await asyncio.to_thread(save_results, payload)

    # Two places remember each round: the database keeps the full history on
    # disk, and these live in memory for Prometheus to read.
    record_round(payload)

    return payload


async def check_loop() -> None:
    """Run a round, wait, repeat — for as long as the app is alive."""
    logger.info("check loop started, every %.0fs", interval_seconds())

    while True:
        try:
            results = await run_check_round()
            logger.info(
                "check round done: %s",
                {row["provider"]: row["status"] for row in results},
            )
        except asyncio.CancelledError:
            # The server is shutting down. Let the cancellation through.
            logger.info("check loop stopping")
            raise
        except Exception:
            # Never let one bad round kill the loop. This is the important
            # line: without it, a single unexpected error would end the loop
            # and the app would keep serving happily while checking nothing —
            # broken in the one way nobody would notice.
            logger.exception("check round failed, continuing")

        # Sleep AFTER the work finishes, not on a fixed clock. If a round takes
        # 20 seconds, the next starts 60 seconds later rather than 40 — so slow
        # rounds can never pile up on top of each other.
        await asyncio.sleep(interval_seconds())
