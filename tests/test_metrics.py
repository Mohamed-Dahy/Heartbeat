"""Tests for the Prometheus metrics.

get_sample_value() is the documented way to read a metric back in a test. It
asks the registry "what is the current value for this name and these labels",
which is exactly what Prometheus itself would see.
"""

from prometheus_client import REGISTRY

from app.metrics import record_round


def up_value(provider: str) -> float | None:
    return REGISTRY.get_sample_value(
        "heartbeat_provider_up", {"provider": provider}
    )


def duration_value(provider: str) -> float | None:
    return REGISTRY.get_sample_value(
        "heartbeat_check_duration_seconds", {"provider": provider}
    )


def test_down_provider_reports_zero():
    record_round([
        {"provider": "metrics-test-down", "status": "down", "response_time_ms": 5000.0},
    ])

    assert up_value("metrics-test-down") == 0


def test_slow_provider_still_counts_as_up():
    # "slow" means it answered, just not quickly. For the up/down gauge that
    # is still reachable — the slowness shows in the duration instead.
    record_round([
        {"provider": "metrics-test-slow", "status": "slow", "response_time_ms": 2500.0},
    ])

    assert up_value("metrics-test-slow") == 1


def test_duration_is_converted_to_seconds():
    # Our probe measures milliseconds; Prometheus wants base units.
    record_round([
        {"provider": "metrics-test-units", "status": "up", "response_time_ms": 1500.0},
    ])

    assert duration_value("metrics-test-units") == 1.5


def test_counter_climbs_with_each_round():
    def total() -> float:
        return REGISTRY.get_sample_value(
            "heartbeat_checks_total",
            {"provider": "metrics-test-counter", "status": "up"},
        ) or 0.0

    before = total()

    row = {"provider": "metrics-test-counter", "status": "up", "response_time_ms": 100.0}
    record_round([row])
    record_round([row])

    assert total() == before + 2
