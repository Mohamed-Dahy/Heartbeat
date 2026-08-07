"""Checking every provider on a timer, without anyone asking.

This is what turns the project from a button you press into a monitor that
watches things while you sleep.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import asdict

from app.db import delete_checks_older_than, save_results
from app.metrics import record_round
from app.probe import check_url
from app.providers import PROVIDERS

logger = logging.getLogger(__name__)

# How long to wait between rounds. Configurable so tests and demos do not have
# to sit through a real minute, and so the interval can be raised on the server
# without changing code if a provider ever objects to the traffic.
DEFAULT_INTERVAL_SECONDS = 60.0

# How much history to keep. 30 days is roughly 173,000 rows — plenty for the
# status page and any "was it broken last week?" question, and small enough to
# stay fast forever.
DEFAULT_RETENTION_DAYS = 30

# Old rows are deleted once a day, not every round. Running the delete 1,439
# extra times a day to find nothing is pure waste.
CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60


def interval_seconds() -> float:
    return float(os.getenv("CHECK_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS))


def retention_days() -> int:
    return int(os.getenv("HEARTBEAT_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))


async def run_check_round() -> list[dict]:
    """Check every provider once, save the results, and return them."""
    names = list(PROVIDERS)

    # gather() starts all the checks at the same time instead of one after
    # another. Four 700ms checks take about 700ms, not 2.8 seconds.
    results = await asyncio.gather(*(check_url(PROVIDERS[name]) for name in names))

    # strict=True makes zip raise if the two lists are ever different lengths,
    # instead of silently stopping at the shorter one. They cannot differ today,
    # but a silent truncation here would mean quietly dropping a provider from
    # every round — exactly the kind of bug nobody notices.
    payload = [
        {"provider": name, **asdict(result)}
        for name, result in zip(names, results, strict=True)
    ]

    # sqlite3 is synchronous: it stops everything until the write finishes.
    # to_thread moves it off to the side so the server can keep answering
    # other requests while the disk does its work.
    await asyncio.to_thread(save_results, payload)

    # Two places remember each round: the database keeps the full history on
    # disk, and these live in memory for Prometheus to read.
    record_round(payload)

    return payload


async def run_cleanup() -> int:
    """Delete history older than the retention window."""
    days = retention_days()
    deleted = await asyncio.to_thread(delete_checks_older_than, days)
    logger.info("cleanup: removed %d checks older than %d days", deleted, days)
    return deleted


async def check_loop() -> None:
    """Run a round, wait, repeat — for as long as the app is alive."""
    logger.info(
        "check loop started, every %.0fs, keeping %d days of history",
        interval_seconds(),
        retention_days(),
    )

    # None rather than 0, so the first pass always cleans up. monotonic() has no
    # defined starting point, so comparing against 0 would be meaningless.
    last_cleanup: float | None = None

    while True:
        try:
            results = await run_check_round()
            logger.info(
                "check round done: %s",
                {row["provider"]: row["status"] for row in results},
            )

            # monotonic() only ever counts forwards. The wall clock can jump
            # backwards when the machine syncs its time, which would leave this
            # waiting a very long time for the next cleanup.
            now = time.monotonic()
            if last_cleanup is None or now - last_cleanup >= CLEANUP_INTERVAL_SECONDS:
                await run_cleanup()
                last_cleanup = now
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
