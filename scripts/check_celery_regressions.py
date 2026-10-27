"""Reproduce the observer blind spot with real workers and two pinned upstream reversions.

Run with the repository's celery/redis extras installed. This owns all Redis
processes and clones Celery into a temporary directory; it never edits an
existing checkout. No upstream posts or dependency changes are performed.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pytest_obligation.integrations.redis_server import redis_environment
from pytest_obligation.regression_controls import assert_detects_regression

BASE = "e3cc7cc532a9a0ef0be575a66a03cfff52ef23be"
FIXES = (
    ("10752", BASE, "celery/worker/request.py", "task_postrun"),
    ("10759", "380b4a930224c9ac8248094d3a2e27524caa97f8", "celery/app/trace.py", "the task's on_success hook raised"),
)
ROOT = Path(__file__).resolve().parents[1]


def probe(stage: str, blind: bool) -> None:
    # Only the probe process imports Celery, from the checkout selected in PYTHONPATH.
    from celery import chord
    from celery.result import AsyncResult

    from pytest_obligation import Findings
    from pytest_obligation.integrations.celery_worker import worker_history
    from pytest_obligation.process_histories import assert_pinned_process_outcomes
    from tests.celery_worker import app as reference
    from tests.celery_worker.observations import send_chord, what_happened

    def old_chord() -> str:
        reference.empty()
        header = [reference.send_message.s(f"order {n} has shipped") for n in (1, 2)]
        return chord(header)(reference.announce_all.s().on_error(reference.report_failure.s())).id

    delivered = ("SUCCESS", 2, ("sent 2 messages",))
    history = worker_history(
        name="chord regression control",
        app="tests.celery_worker.app:app",
        task=reference.send_message.name,
        send=old_chord if blind else send_chord,
        observe=what_happened,
        initial=("PENDING", 0, ()),
        expected=delivered,
        settled=lambda task_id: AsyncResult(task_id, app=reference.app).ready(),
        death_points=(stage,) if stage == "task_postrun" else (),
        failure_points=() if stage == "task_postrun" else (stage,),
        findings=Findings(delivered),
        env={"PYTHONPATH": os.environ["PYTHONPATH"]},
    )
    assert_pinned_process_outcomes(history, delivered=delivered, outcomes={})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe")
    parser.add_argument("--blind", action="store_true")
    args = parser.parse_args()
    if args.probe:
        probe(args.probe, args.blind)
        return
    with tempfile.TemporaryDirectory(prefix="obligation-celery-control-") as temporary:
        checkout = Path(temporary) / "celery"
        subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--filter=blob:none",
                "--no-checkout",
                "https://github.com/celery/celery.git",
                str(checkout),
            ],
            check=True,
        )
        subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet", BASE], check=True)
        with redis_environment() as env:
            env.update(
                {
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": os.pathsep.join((str(checkout), str(ROOT / "package"))),
                }
            )
            for number, commit, source, stage in FIXES:
                patch = subprocess.check_output(
                    ["git", "-C", str(checkout), "diff", f"{commit}^", commit, "--", source]
                )

                @contextmanager
                def reverted(patch: bytes = patch) -> Iterator[None]:
                    subprocess.run(["git", "-C", str(checkout), "apply", "--reverse", "-"], input=patch, check=True)
                    try:
                        yield
                    finally:
                        subprocess.run(["git", "-C", str(checkout), "apply", "-"], input=patch, check=True)

                def check(*, blind: bool = False, stage: str = stage) -> None:
                    command = [sys.executable, str(Path(__file__).resolve()), "--probe", stage]
                    if blind:
                        command.append("--blind")
                    result = subprocess.run(
                        command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180
                    )
                    assert result.returncode == 0, result.stdout

                check(blind=True)
                with reverted():
                    check(blind=True)
                print(f"#{number}: original observer passes both baseline and reverted fix (blind)", flush=True)
                assert_detects_regression(
                    check,
                    regression=reverted,
                    match=re.escape(
                        "these histories no longer leave what the table pins: "
                        + ("died at " if stage == "task_postrun" else "")
                        + stage
                    ),
                )
                print(f"#{number}: improved observer passes baseline and detects reverted fix at {stage}", flush=True)


if __name__ == "__main__":
    main()
