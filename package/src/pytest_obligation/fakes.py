"""
Building blocks for faithful provider fakes.

A fake replaces a provider SDK client in tests. It is faithful when it keeps
the parts of the provider's contract the application must handle: requests the
provider refuses, failures it reports, and replies that acknowledge work the
provider has not done yet. A fake that accepts any request size, never fails
and applies everything on reply lets an application pass tests that the real
provider would fail.

Each block models one of those facts and knows nothing about any provider:

* :class:`ProviderBoundary` records every request, refuses one larger than the
  provider's per-request limit, and delivers failures a test scripts (a rate
  limit is one script). The fake author supplies each refusal in the provider's
  own shape, so the application's real error handling runs: an exception the
  SDK raises, or a reply object for an API that reports failure in its
  response (an HTTP client returning a 429 response instead of raising).
* :class:`AsyncTasks` models an operation the provider acknowledges now and
  applies later: the reply is a task id, not the effect. By default a task
  applies on acceptance, so ordinary tests keep working; :meth:`AsyncTasks.held`
  keeps acceptances pending until the test completes or fails them.

A fake method calls the boundary first, then applies or accepts::

    class FakeUsers:
        def __init__(self) -> None:
            self.boundary = ProviderBoundary(
                request_limits={"delete_users": 100},
                limit_error=lambda operation, size, limit: ProviderError(400, f"{operation}: {size} > {limit}"),
            )
            self.tasks = AsyncTasks()
            self.existing: set[str] = set()

        def delete_users(self, user_ids: list[str]) -> dict[str, str]:
            self.boundary.call("delete_users", user_ids)
            task_id = self.tasks.accept("delete_users", lambda: self.existing.difference_update(user_ids))
            return {"task_id": task_id}

The blocks hold only provider state and observations. Application lifecycle
decisions never belong in a fake: a fake that decides when work is complete
re-implements the system under test.
"""

from collections import defaultdict, deque
from collections.abc import Callable, Iterator, Mapping, Sized
from contextlib import contextmanager
from enum import StrEnum

from pytest_obligation.interleavings.engine.provider import AcceptedProviderRequest
from pytest_obligation.models import HarnessModel

#: Builds the provider's refusal of an oversized request: (operation, request size, limit) -> refusal.
#: A refusal that is an exception is raised; anything else is returned by :meth:`ProviderBoundary.call`.
LimitError = Callable[[str, int, int], object]


class ProviderCall(HarnessModel):
    """One request a fake received, including requests the provider refused."""

    operation: str
    #: Number of items in the request, when the operation takes a collection.
    size: int | None = None
    #: The refusal the boundary raised or returned instead of letting the request through, if any.
    refused: str | None = None


class ProviderBoundary:
    """Record requests and refuse them as the provider would: oversized, or failing by script."""

    def __init__(
        self,
        *,
        request_limits: Mapping[str, int] | None = None,
        limit_error: LimitError | None = None,
    ) -> None:
        self.request_limits = dict(request_limits or {})
        if self.request_limits and limit_error is None:
            raise ValueError(
                "request_limits need limit_error: the provider's refusal must take the provider's own shape, "
                "or the application's real error handling never runs"
            )
        if any(limit < 1 for limit in self.request_limits.values()):
            raise ValueError("a request limit allows at least one item")
        self._limit_error = limit_error
        self._scripted: defaultdict[str, deque[Callable[[], object]]] = defaultdict(deque)
        self.calls: list[ProviderCall] = []

    def fail_next(self, operation: str, error: Callable[[], object], *, times: int = 1) -> None:
        """
        Make the next ``times`` requests to ``operation`` fail with a fresh ``error()``, then succeed.

        An exception is raised from :meth:`call`; any other value (an error
        response) is returned from it for the fake to return as its reply.
        """
        if times < 1:
            raise ValueError("fail_next scripts at least one failure")
        self._scripted[operation].extend([error] * times)

    def call(self, operation: str, items: Sized | None = None) -> object | None:
        """
        Record one request to ``operation`` and deliver the provider's refusal, if it refuses it.

        Returns ``None`` when the request goes through. A refusal that is an
        exception is raised; any other refusal is returned, and the fake returns
        it as its reply without applying the request::

            refused = self.boundary.call("purge", urls)
            if refused is not None:
                return refused
        """
        size = None if items is None else len(items)
        limit = self.request_limits.get(operation)
        refusal: object | None = None
        if limit is not None and size is not None and size > limit:
            assert self._limit_error is not None, "checked in __init__"
            refusal = self._limit_error(operation, size, limit)
        elif self._scripted[operation]:
            refusal = self._scripted[operation].popleft()()
        self.calls.append(
            ProviderCall(operation=operation, size=size, refused=None if refusal is None else repr(refusal))
        )
        if isinstance(refusal, BaseException):
            raise refusal
        return refusal

    def calls_to(self, operation: str) -> list[ProviderCall]:
        """Requests to ``operation`` in arrival order, refused ones included."""
        return [call for call in self.calls if call.operation == operation]

    def assert_scripts_consumed(self) -> None:
        """Fail a test whose scripted failure never reached the provider: it proved nothing about handling it."""
        unused = {operation: len(errors) for operation, errors in self._scripted.items() if errors}
        assert not unused, f"scripted provider failures never reached the fake: {unused}"


class TaskStatus(StrEnum):
    """Where an acknowledged operation stands at the provider."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class AsyncTasks:
    """
    Operations the provider acknowledges now and applies later.

    :meth:`accept` returns a task id. The effect runs on acceptance unless the
    acceptance happens inside :meth:`held`; then it waits for :meth:`complete`
    (applies exactly once) or :meth:`fail` (never applies). Only the provider's
    state shows whether a task applied; the reply never does.
    """

    def __init__(self, *, id_prefix: str = "task") -> None:
        self._id_prefix = id_prefix
        self._requests: dict[str, AcceptedProviderRequest] = {}
        self._operations: dict[str, str] = {}
        self._status: dict[str, TaskStatus] = {}
        self._holding = 0

    @contextmanager
    def held(self) -> Iterator["AsyncTasks"]:
        """Keep every acceptance inside this block pending, as a provider still working on it would."""
        self._holding += 1
        try:
            yield self
        finally:
            self._holding -= 1

    def accept(self, operation: str, apply: Callable[[], None]) -> str:
        """Acknowledge ``operation`` and return its task id; apply it now unless acceptances are held."""
        task_id = f"{self._id_prefix}-{len(self._requests) + 1}"
        self._requests[task_id] = AcceptedProviderRequest(apply=apply)
        self._operations[task_id] = operation
        self._status[task_id] = TaskStatus.PENDING
        if not self._holding:
            self.complete(task_id)
        return task_id

    def complete(self, task_id: str) -> None:
        """The provider finishes the task: its effect applies, exactly once."""
        self._require_pending(task_id)
        self._requests[task_id].complete()
        self._status[task_id] = TaskStatus.COMPLETED

    def fail(self, task_id: str) -> None:
        """The provider gives up on the task: its effect never applies."""
        self._require_pending(task_id)
        self._requests[task_id].expire()
        self._status[task_id] = TaskStatus.FAILED

    def complete_pending(self) -> None:
        """Finish every pending task in acceptance order."""
        for task_id in self.pending:
            self.complete(task_id)

    def status(self, task_id: str) -> TaskStatus:
        """The task's provider-side state, as the provider's task-status API would report it."""
        return self._status[task_id]

    def operation(self, task_id: str) -> str:
        return self._operations[task_id]

    @property
    def accepted(self) -> int:
        """Acknowledged operations, applied or not: the positive control that a request reached the provider."""
        return len(self._requests)

    @property
    def applied(self) -> int:
        return sum(status is TaskStatus.COMPLETED for status in self._status.values())

    @property
    def pending(self) -> list[str]:
        return [task_id for task_id, status in self._status.items() if status is TaskStatus.PENDING]

    def _require_pending(self, task_id: str) -> None:
        assert self._status[task_id] is TaskStatus.PENDING, f"{task_id} is already {self._status[task_id].value}"


__all__ = ["AsyncTasks", "LimitError", "ProviderBoundary", "ProviderCall", "TaskStatus"]
