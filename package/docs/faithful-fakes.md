# Faithful provider fakes

A test that replaces a provider SDK client with a fake proves only what the fake
lets happen. A fake that accepts any request size, never fails, and applies every
operation the moment it replies lets an application pass tests the real provider
would fail. The application can then:

- send more items in one request than the provider accepts;
- leak the SDK's raw exception, or give up on a rate limit it should retry;
- treat a reply that only acknowledges receipt (a task id, an HTTP 202) as the effect itself.

`pytest_obligation.fakes` gives a fake author three provider-neutral building
blocks, one per fact above. They know nothing about any provider. The author
supplies each error in the provider SDK's own exception type, so the
application's real error handling runs.

| Block | Models | Test controls | Observations |
| --- | --- | --- | --- |
| `ProviderBoundary(request_limits=, limit_error=)` | Per-operation request-size limits | `fail_next(operation, error, times=)` scripts failures, for example a rate limit | `calls`, `calls_to(operation)`, `assert_scripts_consumed()` |
| `AsyncTasks()` | Operations acknowledged now and applied later | `held()`, `complete(task_id)`, `fail(task_id)`, `complete_pending()` | `status(task_id)`, `accepted`, `applied`, `pending` |

## Writing a fake

Call the boundary first in every fake method, then apply or accept:

```python
from pytest_obligation.fakes import AsyncTasks, ProviderBoundary


class FakeChat:
    def __init__(self) -> None:
        self.boundary = ProviderBoundary(
            request_limits={"upsert_users": 100, "delete_users": 100},
            limit_error=lambda operation, size, limit: ChatAPIError(400, f"{operation}: {size} > {limit}"),
        )
        self.tasks = AsyncTasks()
        self.users: set[str] = set()

    def upsert_users(self, users: list[dict]) -> None:
        self.boundary.call("upsert_users", users)
        self.users.update(user["id"] for user in users)

    def delete_users(self, user_ids: list[str]) -> dict[str, str]:
        self.boundary.call("delete_users", user_ids)
        task_id = self.tasks.accept("delete_users", lambda: self.users.difference_update(user_ids))
        return {"task_id": task_id}

    def get_task(self, task_id: str) -> dict[str, str]:
        return {"status": self.tasks.status(task_id).value}
```

A test scripts a rate limit in the SDK's shape and checks the application's handling:

```python
chat.boundary.fail_next("upsert_users", lambda: ChatAPIError(429, "Too many requests"), times=2)
service.sync_profiles(users)
chat.boundary.assert_scripts_consumed()
```

## Defaults keep ordinary tests honest without rewriting them

- A limit applies only to operations named in `request_limits`. Set it to the
  provider's documented limit; an oversized request then fails the test the way
  production would.
- `AsyncTasks` applies a task on acceptance unless the acceptance happens inside
  `held()`. Existing tests that read provider state after a call keep passing;
  tests about acknowledgement use `held()` and decide the outcome with
  `complete` or `fail`.
- `fail_next` raises a fresh exception each time, as a real client does.
  `assert_scripts_consumed()` fails a test whose scripted failure never reached
  the fake, because such a test proved nothing about handling it.

## Proving a reply is not treated as the effect

An `AsyncTasks`-backed fake is the provider half of profile C's
[acknowledged-effect binding](what-a-green-result-means.md#why-profiles-not-one-interface):
`hold_acknowledgements` is `tasks.held()`, `apply_acknowledged` is
`tasks.complete_pending()`, and `applied` reads the fake's provider state. The
binding then proves that a held acknowledgement leaves the obligation owed, and
that once the provider applies it, production discharges the obligation within a
bounded number of runs. Declare it only for an API whose documented contract
acknowledges receipt rather than completion.

## What belongs in a fake

A fake holds provider state and observations: which users exist, which tasks are
pending, which requests arrived. It never decides application lifecycle, such as
when the application's work counts as complete. A fake that makes that decision
re-implements the system under test, and a regression in production then passes.
The [Shopify billing simulator](shopify.md) is a complete provider-specific
example of the same separation between acceptance and application.
