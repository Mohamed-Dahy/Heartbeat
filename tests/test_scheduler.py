"""Tests for the background checker.

Same idea as the probe tests: no real network. Here we also point the database
at a temporary file, so a test run never touches your real heartbeat.db.
"""

import httpx
import pytest
import respx

from app import db
from app.providers import PROVIDERS
from app.scheduler import run_check_round


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Give each test its own empty database in a throwaway folder."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return db


def mock_all_providers(status_code: int = 401) -> None:
    for url in PROVIDERS.values():
        respx.get(url).mock(return_value=httpx.Response(status_code))


@respx.mock
async def test_round_saves_one_row_per_provider(temp_db):
    mock_all_providers()

    returned = await run_check_round()

    assert len(returned) == len(PROVIDERS)

    saved = temp_db.recent_checks(limit=100)
    assert len(saved) == len(PROVIDERS)
    assert {row["provider"] for row in saved} == set(PROVIDERS)


@respx.mock
async def test_every_row_in_a_round_shares_one_timestamp(temp_db):
    # The status page groups checks into rounds by their timestamp, so all
    # four rows from one round must agree on the time.
    mock_all_providers()

    await run_check_round()

    stamps = {row["checked_at"] for row in temp_db.recent_checks(limit=100)}
    assert len(stamps) == 1


@respx.mock
async def test_status_shows_only_the_newest_round(temp_db):
    mock_all_providers()
    await run_check_round()

    # Second round: everyone is now broken.
    respx.clear()
    mock_all_providers(status_code=503)
    await run_check_round()

    latest = temp_db.latest_per_provider()

    # Two rounds happened, but status reports one row per provider...
    assert len(latest) == len(PROVIDERS)
    # ...and it is the newer one.
    assert all(row["status"] == "down" for row in latest)
    assert len(temp_db.recent_checks(limit=100)) == len(PROVIDERS) * 2
