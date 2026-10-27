"""Reference workload and independent observer shared by contracts and regression controls."""

from typing import cast

from celery import chord
from celery.result import AsyncResult

from tests.celery_worker import app as reference


def send_chord() -> str:
    """Observe false errors on each header task as well as the chord body."""
    reference.empty()
    header = [reference.send_message.s(f"order {n} has shipped").on_error(reference.report_failure.s()) for n in (1, 2)]
    return chord(header)(reference.announce_all.s().on_error(reference.report_failure.s())).id


def what_happened(task_id: str) -> tuple[str, int, tuple[str, ...]]:
    # decode_responses=True makes every reply a str; redis-py's annotations do not follow it.
    announced = cast("list[str]", reference.RECORDS.lrange("announced", 0, -1))
    return (
        str(AsyncResult(task_id, app=reference.app).state),
        reference.RECORDS.llen("sent"),
        # The link and error callback run in different processes, in either order.
        tuple(sorted(announced)),
    )
