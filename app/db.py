"""Saving check results to SQLite, so they survive a restart."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# One file, sitting next to the code. No server, no password, no setup.
#
# The location can be overridden with the HEARTBEAT_DB environment variable.
# We need that in Docker: a container's own disk is wiped every time it is
# replaced, so the database has to live on a volume mounted from outside.
DB_PATH = Path(os.getenv("HEARTBEAT_DB", "heartbeat.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    provider         TEXT    NOT NULL,
    url              TEXT    NOT NULL,
    status           TEXT    NOT NULL,
    response_time_ms REAL    NOT NULL,
    status_code      INTEGER,
    error            TEXT,
    checked_at       TEXT    NOT NULL
)
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    # Return rows we can read by column name instead of by number.
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the table if it is not there yet. Safe to run every startup."""
    conn = get_connection()
    try:
        with conn:
            conn.execute(SCHEMA)
    finally:
        conn.close()


def save_results(rows: list[dict]) -> None:
    """Save one round of checks."""
    # Stored in UTC. A server in Germany and a laptop in Egypt must agree on
    # what "10:00" means, and UTC is the one clock everybody shares.
    checked_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        # `with conn` commits if all goes well, and undoes everything if not.
        with conn:
            conn.executemany(
                """
                INSERT INTO checks
                    (provider, url, status, response_time_ms, status_code, error, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["provider"],
                        row["url"],
                        row["status"],
                        row["response_time_ms"],
                        row["status_code"],
                        row["error"],
                        checked_at,
                    )
                    for row in rows
                ],
            )
    finally:
        conn.close()


def latest_per_provider() -> list[dict]:
    """The most recent check for each provider — what /api/status reports."""
    # MAX(id) per provider gives the newest row for each one. Because ids only
    # ever climb, "biggest id" and "most recent" are the same thing here.
    sql = """
        SELECT * FROM checks
        WHERE id IN (SELECT MAX(id) FROM checks GROUP BY provider)
        ORDER BY provider
    """
    conn = get_connection()
    try:
        return [dict(row) for row in conn.execute(sql)]
    finally:
        conn.close()


def recent_checks(limit: int = 50, provider: str | None = None) -> list[dict]:
    """Return the most recent checks, newest first."""
    sql = "SELECT * FROM checks"
    params: list = []

    if provider:
        sql += " WHERE provider = ?"
        params.append(provider)

    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    conn = get_connection()
    try:
        # The values go in as `?` placeholders, never glued into the string.
        # That is what stops someone passing a provider name that is really SQL.
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()
