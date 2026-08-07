"""Saving check results to SQLite, so they survive a restart."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta
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

# An index is a lookup table the database keeps on the side — like the index at
# the back of a book. Without one, answering "which rows are for openai?" means
# reading every single row.
#
# We add exactly two, because each one costs a little on every write and a
# little disk. These are the two our actual queries need.
INDEXES = [
    # Serves both the status page (newest row per provider) and history filtered
    # to one provider. Provider first because that is what we filter on; id
    # second because that is what we then sort by.
    "CREATE INDEX IF NOT EXISTS idx_checks_provider_id ON checks (provider, id)",
    # Serves the daily cleanup, which deletes everything older than a date.
    "CREATE INDEX IF NOT EXISTS idx_checks_checked_at ON checks (checked_at)",
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    # Return rows we can read by column name instead of by number.
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the table and indexes if missing. Safe to run every startup.

    IF NOT EXISTS on both means this also upgrades a database that already has
    data: SQLite builds the missing indexes over the existing rows and leaves
    everything else alone.
    """
    conn = get_connection()
    try:
        with conn:
            conn.execute(SCHEMA)
            for statement in INDEXES:
                conn.execute(statement)
    finally:
        conn.close()


def save_results(rows: list[dict]) -> None:
    """Save one round of checks."""
    # Stored in UTC. A server in Germany and a laptop in Egypt must agree on
    # what "10:00" means, and UTC is the one clock everybody shares.
    checked_at = datetime.now(UTC).isoformat()

    conn = get_connection()
    try:
        # `with conn` commits if all goes well, and undoes everything if not.
        with conn:
            conn.executemany(
                """
                INSERT INTO checks (
                    provider, url, status, response_time_ms,
                    status_code, error, checked_at
                )
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


def delete_checks_older_than(days: int) -> int:
    """Delete checks older than `days`. Returns how many rows went.

    Without this the table grows forever: four rows a minute is 5,760 a day and
    about 2.1 million a year. The disk is not really the problem — the problem
    is that every query has more rows to wade through, on a small server, for
    the rest of the app's life.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    conn = get_connection()
    try:
        with conn:
            # checked_at is stored as an ISO timestamp, and ISO timestamps sort
            # correctly as plain text — so a simple "<" comparison works and can
            # use the index.
            cursor = conn.execute("DELETE FROM checks WHERE checked_at < ?", (cutoff,))
            return cursor.rowcount
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
