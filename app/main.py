"""The web server: reports what the scheduler has found."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.db import init_db, latest_per_provider, recent_checks
from app.scheduler import check_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts: make sure the table exists.
    init_db()

    # Start the background checker. create_task means "run this alongside the
    # server" — we do not await it, or startup would never finish.
    task = asyncio.create_task(check_loop())

    yield

    # Runs once on shutdown. Without this the task is killed mid-write and
    # Python complains about a task that was never awaited.
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Heartbeat", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness: am I running and answering HTTP?

    Deliberately does nothing else. No database, no provider calls. It answers
    in under a millisecond, which is what makes it safe to call every few
    seconds forever.

    Note what this does NOT prove: the database could be unreadable and this
    would still say "ok". That is why Docker's HEALTHCHECK still points at
    /api/history instead. This route is here for Caddy and any external uptime
    checker in Phase 9, which want something cheap.
    """
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    """The page Prometheus reads.

    Plain text, not JSON. generate_latest() turns whatever the counters and
    gauges currently hold into that format. The media type matters — it is how
    Prometheus knows what it is looking at.

    These numbers live in memory, so they reset when the app restarts. Gauges
    refill on the next round and nobody notices. The counter starts again from
    zero, which is normal and which Prometheus is built to handle — worth
    remembering in Phase 10, so a graph dropping to zero reads as "we deployed"
    rather than "everything broke".
    """
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/status")
async def get_status() -> list[dict]:
    """The latest result for each provider, from the last saved round.

    This route used to run the checks itself. It does not any more — the
    scheduler owns checking and writing, and this just reports what is already
    known. Two reasons: refreshing a browser tab should not add extra rows at
    random moments and dent the every-60-seconds rhythm the graphs rely on, and
    reading from disk is instant instead of taking a second.

    Returns an empty list for the first second or so after startup, before the
    first round has finished. Anything reading this has to cope with that.
    """
    return await asyncio.to_thread(latest_per_provider)


@app.get("/api/history")
async def get_history(
    provider: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    """Return past checks, newest first. Optionally filtered to one provider."""
    return await asyncio.to_thread(recent_checks, limit, provider)


# --- The status page -------------------------------------------------------
#
# This mount MUST come last. Starlette matches routes in the order they were
# added, and mounting at "/" catches everything. Put this above the API routes
# and it would swallow /api/status and hand back the HTML page instead — a
# baffling bug with a one-line cause.
#
# html=True makes it serve index.html for "/" instead of a directory listing.
#
# The directory only exists after `npm run build`. Skipping the mount when it is
# missing keeps `uvicorn app.main:app` working for backend-only development,
# where the page is served by Vite on port 5173 instead.
STATIC_DIR = Path(os.getenv("HEARTBEAT_STATIC", "frontend/dist"))

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
else:
    logging.warning("no built frontend at %s — serving API only", STATIC_DIR)
