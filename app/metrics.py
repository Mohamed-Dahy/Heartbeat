"""Numbers for Prometheus to collect.

The one idea that makes the rest of Phase 10 make sense: Prometheus **pulls**.
It visits our /metrics page on a schedule and reads it, the same way a browser
reads a web page. We never push anything anywhere, and we do not need to know
Prometheus exists.

That is why /metrics is plain text and not JSON — it is a format built to be
read quickly, thousands of times a day, by a machine.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge

from app.probe import DOWN

# A GAUGE is a value that moves both ways — like a speedometer. Right now, is
# this provider reachable?
PROVIDER_UP = Gauge(
    "heartbeat_provider_up",
    "1 if the provider answered our last check, 0 if it did not.",
    ["provider"],
)

# Seconds, not milliseconds. Prometheus convention is base units, always, and
# every dashboard and alert example you will ever read assumes it.
CHECK_DURATION = Gauge(
    "heartbeat_check_duration_seconds",
    "How long the last check took, in seconds.",
    ["provider"],
)

# A COUNTER only ever climbs — like a car's odometer. You never read it
# directly; you ask "how fast is it rising", which is how you get rates.
# The _total suffix is the convention for counters.
CHECKS_TOTAL = Counter(
    "heartbeat_checks_total",
    "How many checks we have done, split by result.",
    ["provider", "status"],
)


def record_round(rows: list[dict]) -> None:
    """Update the metrics after a round of checks."""
    for row in rows:
        provider = row["provider"]

        # "slow" still counts as reachable — it answered, just not quickly.
        # Slowness is visible in the duration and in the counter below.
        PROVIDER_UP.labels(provider=provider).set(0 if row["status"] == DOWN else 1)

        CHECK_DURATION.labels(provider=provider).set(row["response_time_ms"] / 1000)

        CHECKS_TOTAL.labels(provider=provider, status=row["status"]).inc()
