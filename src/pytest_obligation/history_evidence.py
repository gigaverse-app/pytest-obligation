"""Per-stage diagnostics for both in-process and child-process histories."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytest_obligation.crash_histories import Findings, HistoryRun

_sink: ContextVar[list[dict[str, str]] | None] = ContextVar("obligation_history_evidence", default=None)


@contextmanager
def capture_histories() -> Iterator[list[dict[str, str]]]:
    evidence: list[dict[str, str]] = []
    token = _sink.set(evidence)
    try:
        yield evidence
    finally:
        _sink.reset(token)


def record_histories(name: str, runs: Sequence["HistoryRun"], findings: "Findings | None") -> None:
    """Record stage labels and comparisons, never domain values or a second verdict."""
    sink = _sink.get()
    if sink is None or not runs:
        return
    baseline = runs[0].after
    for index, run in enumerate(runs):
        expected = findings.outcomes.get(run.label, findings.delivered) if findings is not None else baseline
        if index and not run.interrupted:
            status = "fault not reached"
        elif findings is not None and run.after != expected:
            status = "changed from pinned outcome"
        elif not index:
            status = "baseline"
        elif run.after == baseline:
            status = "matches baseline"
        else:
            status = "matches pinned divergence" if findings is not None else "diverged (unpinned)"
        sink.append({"history": name, "stage": run.label, "status": status})
