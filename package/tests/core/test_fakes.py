"""The faithful-fake building blocks: request limits, scripted failures and asynchronous acceptance."""

import pytest

from pytest_obligation.fakes import AsyncTasks, ProviderBoundary, TaskStatus


class _ProviderError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _limit_error(operation: str, size: int, limit: int) -> _ProviderError:
    return _ProviderError(400, f"{operation}: {size} items exceeds {limit}")


def test_a_request_over_the_limit_is_refused_in_the_providers_shape() -> None:
    boundary = ProviderBoundary(request_limits={"upsert": 2}, limit_error=_limit_error)

    boundary.call("upsert", ["a", "b"])
    with pytest.raises(_ProviderError, match="3 items exceeds 2") as refused:
        boundary.call("upsert", ["a", "b", "c"])

    assert refused.value.status == 400
    assert [(call.size, call.refused is not None) for call in boundary.calls_to("upsert")] == [(2, False), (3, True)]


def test_operations_without_a_limit_take_any_size() -> None:
    boundary = ProviderBoundary(request_limits={"upsert": 1}, limit_error=_limit_error)

    boundary.call("query", list(range(1000)))
    boundary.call("ping")

    assert [call.size for call in boundary.calls] == [1000, None]


def test_a_limit_without_the_providers_error_is_refused() -> None:
    with pytest.raises(ValueError, match="need limit_error"):
        ProviderBoundary(request_limits={"upsert": 100})
    with pytest.raises(ValueError, match="at least one item"):
        ProviderBoundary(request_limits={"upsert": 0}, limit_error=_limit_error)


def test_scripted_failures_raise_fresh_errors_then_stop() -> None:
    boundary = ProviderBoundary()
    boundary.fail_next("upsert", lambda: _ProviderError(429, "rate limited"), times=2)

    raised = []
    for _ in range(2):
        with pytest.raises(_ProviderError) as error:
            boundary.call("upsert", ["a"])
        raised.append(error.value)
    boundary.call("upsert", ["a"])
    boundary.call("delete", ["a"])

    assert raised[0] is not raised[1], "each failure is a fresh exception, as a real client raises"
    assert [call.refused is not None for call in boundary.calls] == [True, True, False, False]
    boundary.assert_scripts_consumed()


def test_an_unreached_script_is_reported() -> None:
    boundary = ProviderBoundary()
    boundary.fail_next("upsert", lambda: _ProviderError(429, "rate limited"))

    with pytest.raises(AssertionError, match="never reached the fake: {'upsert': 1}"):
        boundary.assert_scripts_consumed()


def test_tasks_apply_on_acceptance_by_default() -> None:
    applied: list[str] = []
    tasks = AsyncTasks()

    task_id = tasks.accept("delete", lambda: applied.append("a"))

    assert task_id == "task-1"
    assert applied == ["a"]
    assert tasks.status(task_id) is TaskStatus.COMPLETED
    assert (tasks.accepted, tasks.applied, tasks.pending) == (1, 1, [])


def test_held_tasks_apply_only_when_the_provider_completes_them() -> None:
    applied: list[str] = []
    tasks = AsyncTasks(id_prefix="delete")

    with tasks.held():
        first = tasks.accept("delete", lambda: applied.append("first"))
        second = tasks.accept("delete", lambda: applied.append("second"))
    third = tasks.accept("delete", lambda: applied.append("third"))

    assert applied == ["third"], "the reply is not the effect while acceptances are held"
    assert tasks.pending == [first, second]
    tasks.complete(first)
    tasks.fail(second)
    assert applied == ["third", "first"]
    assert [tasks.status(task) for task in (first, second, third)] == [
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.COMPLETED,
    ]
    assert tasks.operation(second) == "delete"


def test_a_task_settles_once() -> None:
    tasks = AsyncTasks()
    with tasks.held():
        task_id = tasks.accept("delete", lambda: None)
    tasks.fail(task_id)

    with pytest.raises(AssertionError, match="already failed"):
        tasks.complete(task_id)


def test_complete_pending_finishes_every_held_task_in_order() -> None:
    applied: list[int] = []
    tasks = AsyncTasks()
    with tasks.held():
        for value in range(3):
            tasks.accept("delete", lambda value=value: applied.append(value))

    tasks.complete_pending()

    assert applied == [0, 1, 2]
    assert tasks.pending == []


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status


def test_a_refusal_that_is_not_an_exception_is_returned_as_the_reply() -> None:
    # An HTTP client reports a rate limit in its response rather than by raising.
    boundary = ProviderBoundary(
        request_limits={"purge": 2},
        limit_error=lambda operation, size, limit: _Response(400),
    )
    boundary.fail_next("purge", lambda: _Response(429))

    throttled = boundary.call("purge", ["a"])
    oversized = boundary.call("purge", ["a", "b", "c"])
    accepted = boundary.call("purge", ["a"])

    assert isinstance(throttled, _Response) and throttled.status == 429
    assert isinstance(oversized, _Response) and oversized.status == 400
    assert accepted is None
    assert [call.refused is not None for call in boundary.calls] == [True, True, False]
