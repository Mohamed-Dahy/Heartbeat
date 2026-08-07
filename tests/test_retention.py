"""Tests for keeping the database from growing forever.

Each test gets its own throwaway database, so nothing here touches real data.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app import db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return db


def insert_at(database, provider: str, days_ago: float) -> None:
    """Put one row in the table with a hand-picked age."""
    checked_at = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    conn = database.get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO checks (
                    provider, url, status, response_time_ms,
                    status_code, error, checked_at
                )
                VALUES (?, 'https://example.com', 'up', 100.0, 401, NULL, ?)
                """,
                (provider, checked_at),
            )
    finally:
        conn.close()


def test_old_rows_are_deleted(temp_db):
    insert_at(temp_db, "openai", days_ago=40)
    insert_at(temp_db, "openai", days_ago=31)

    deleted = temp_db.delete_checks_older_than(30)

    assert deleted == 2
    assert temp_db.recent_checks(limit=100) == []


def test_recent_rows_survive(temp_db):
    insert_at(temp_db, "openai", days_ago=1)
    insert_at(temp_db, "anthropic", days_ago=29)

    deleted = temp_db.delete_checks_older_than(30)

    assert deleted == 0
    assert len(temp_db.recent_checks(limit=100)) == 2


def test_only_the_old_ones_go(temp_db):
    insert_at(temp_db, "openai", days_ago=100)
    insert_at(temp_db, "openai", days_ago=2)
    insert_at(temp_db, "groq", days_ago=200)
    insert_at(temp_db, "groq", days_ago=3)

    deleted = temp_db.delete_checks_older_than(30)

    assert deleted == 2
    remaining = temp_db.recent_checks(limit=100)
    assert len(remaining) == 2
    # The survivors are the recent ones, one per provider.
    assert {row["provider"] for row in remaining} == {"openai", "groq"}


def test_deleting_from_an_empty_table_is_fine(temp_db):
    assert temp_db.delete_checks_older_than(30) == 0


def test_status_query_uses_the_index(temp_db):
    """The point of the index: stop reading the whole table.

    EXPLAIN QUERY PLAN asks SQLite how it intends to answer a query. "SCAN"
    means it reads every row; "SEARCH ... USING INDEX" means it jumps straight
    there. Before this change, the plan said SCAN.
    """
    insert_at(temp_db, "openai", days_ago=1)

    conn = temp_db.get_connection()
    try:
        plan = conn.execute("""
            EXPLAIN QUERY PLAN
            SELECT * FROM checks WHERE provider = 'openai' ORDER BY id DESC LIMIT 30
        """).fetchall()
    finally:
        conn.close()

    detail = " ".join(row["detail"] for row in plan)
    assert "idx_checks_provider_id" in detail, detail
    assert "SCAN checks" not in detail, detail
