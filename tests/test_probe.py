"""Tests for the probe.

Every test here is wrapped in @respx.mock. That decorator intercepts outgoing
HTTP requests before they leave the machine and hands back a reply we wrote
ourselves, so no real network call ever happens.

The tests are `async def` because the probe is async. pytest-asyncio runs them
(see asyncio_mode in pytest.ini).
"""

import httpx
import respx

from app.probe import DOWN, SLOW, UP, check_url

URL = "https://api.example.com/v1/models"


@respx.mock
async def test_healthy_response_is_up():
    respx.get(URL).mock(return_value=httpx.Response(200))

    result = await check_url(URL)

    assert result.status == UP
    assert result.status_code == 200
    assert result.response_time_ms >= 0


@respx.mock
async def test_unauthorized_is_still_up():
    # 401 means the server heard us and replied. It is alive.
    respx.get(URL).mock(return_value=httpx.Response(401))

    result = await check_url(URL)

    assert result.status == DOWN   # deliberately wrong: 401 means up
    assert result.status_code == 401


@respx.mock
async def test_server_error_is_down():
    respx.get(URL).mock(return_value=httpx.Response(503))

    result = await check_url(URL)

    assert result.status == DOWN
    assert result.status_code == 503


@respx.mock
async def test_timeout_is_down():
    # side_effect raises instead of replying, which is how we reproduce a
    # timeout on demand. A real provider will not time out just because we
    # asked it to.
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("timed out"))

    result = await check_url(URL)

    assert result.status == DOWN
    assert result.status_code is None
    assert result.error == "ConnectTimeout"


@respx.mock
async def test_slow_response_is_slow():
    respx.get(URL).mock(return_value=httpx.Response(200))

    # A mocked reply comes back instantly, so we lower the bar instead of
    # making the test wait a real second. This relies on the measured time
    # being strictly greater than zero, which it always is: even an instant
    # reply burns a few microseconds on the clock.
    result = await check_url(URL, slow_threshold_ms=0.0)

    assert result.status == SLOW
