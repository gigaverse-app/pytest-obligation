"""Moving one frozen clock preserves task order, every horizon, and clock restoration."""

from datetime import datetime

import pytest
from django.conf import settings
from django.utils import timezone
from freezegun import freeze_time
from saleor.celeryconf import app
from test_order_confirmation import RECOVERY_HORIZONS, run_beat_schedule


def test_recovery_runs_every_task_at_every_horizon(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[tuple[str, datetime]] = []

    @app.task(name="obligation.clock.first")
    def first() -> None:
        observed.append(("first", timezone.now()))

    @app.task(name="obligation.clock.second")
    def second() -> None:
        observed.append(("second", timezone.now()))

    monkeypatch.setattr(
        settings,
        "CELERY_BEAT_SCHEDULE",
        {
            "first": {"task": first.name},
            "second": {"task": second.name},
        },
    )
    try:
        with freeze_time("2026-01-01"):
            start = timezone.now()
            run_beat_schedule()
            assert timezone.now() == start
        assert observed == [(name, start + horizon) for horizon in RECOVERY_HORIZONS for name in ("first", "second")]
    finally:
        app.tasks.pop(first.name)
        app.tasks.pop(second.name)
