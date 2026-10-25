# 4. The module you ship

[Previous: 3. A suite that keeps finding more](framework-3-growing.md) · [All chapters](tutorial-framework-authors.md#chapters) · [Vocabulary](vocabulary.md)

Chapters 1 and 2 built the pieces: a host that knows where the library writes,
a worker pass, a recovery, and the ownership and retry bindings. This chapter
puts them behind one function an application calls. That function is the
first-party testing support you offer your users, and it is the main reason
to adopt pytest-obligation as a library owner.

## One function, two sides

For RQ, the function is the integration's `worker_contract`:

<!-- fmt:off -->
```python
def worker_contract(
    connection: Any,
    *,
    name: str,
    queue: str,
    enqueue: Callable[[], str],
    effect: Callable[[str], Any],
    expected: TaskOutcome | Callable[[str], TaskOutcome],
    enqueue_failing: Callable[[], str],
    failures: Callable[[str], int],
    max_retries: int,
    other_queue: str | None = None,
    external_calls: Sequence[ExternalCall] = (),
    delivery: Delivery | None = None,
    gaps: dict[Profile, dict[str, str]] | None = None,
    handoff_gaps: dict[str, str] | None = None,
    findings: Mapping[str, Findings] | None = None,
    fixtures: tuple[str, ...] = (),
) -> ObligationContract:
```
<!-- fmt:on -->

It returns an **`ObligationContract`**: pytest-obligation's declaration of
everything to test about one piece of work. The split between what the
library fills in and what the application supplies is the whole design:

| The library fills in | The application supplies |
| --- | --- |
| The crash history of a worker pass (chapter 1), and the recovery after it | `enqueue`: its own command that enqueues one of its jobs |
| Ownership, bound to RQ's worker, heartbeats and cleanup (chapter 2) | `effect`: how to see what the job did |
| Retries, bound to RQ's `Retry` (chapter 2) | `expected`: what that should be after one successful run |
| An answer to each of the ten standard questions (below) | `enqueue_failing`, `failures`, `max_retries`: a job that keeps failing, and how to count its attempts |
| Which pytest-obligation proofs apply to an RQ job | `external_calls`: the outside systems the job calls |

The application knows nothing about Redis writes, heartbeats or registries.
The library knows nothing about welcome emails.

## Answering the standard questions once

A contract answers ten standard questions, the
[profiles A to J](vocabulary.md#profiles-a-to-j). The library answers them
once, for every application:

| Question | RQ's answer |
| --- | --- |
| B: who owns a job, and what happens when the owner dies? | **Claim**, proven against RQ's own machinery |
| J: does a failing job stop at its limit? | **Claim**, proven against RQ's `Retry` |
| A, C, D | Declined, each with RQ's reason: a dead worker's job is found by cleanup, not by a sweep; RQ is at-least-once, and only the job's function knows whether a dead attempt reached its service; finished jobs expire by Redis TTL on the server's clock |
| E, F | Not applicable: one worker settles each job, and the job itself is the obligation |
| G, H, I | Declined: whether a job may run yet, whether it is safe to repeat, and whether it is enqueued together with the application's writes are questions about the application's code, which its own crash history answers |

Reasons that apply to any task queue come ready-worded in
`pytest_obligation.integrations.task_queues` (`settled_by_one_worker`,
`the_obligation_is_the`, `replay_safety_is_the_functions`, `application_gate`,
`application_admission`), so different libraries answer those questions the
same way.

## Declaring your library's own properties

Chapter 2 found one property of RQ 2.12: a worker whose job was already given
back can still record a result. That is true for every application on RQ, so
no application should have to discover it or write it down. The module you
ship declares it, once. In the example this is
[`rq_testing`](../../examples/rq_tutorial/rq_testing/__init__.py), standing in
for "what RQ ships":

```python
#: How the pinned RQ version behaves, declared once for every application. Each entry is a strict
#: expected failure: if a later RQ version behaves differently, the case fails and the entry goes.
RQ_PROPERTIES = {
    Profile.B: {
        "assert_stale_token_is_rejected": (
            "RQ identifies a running job by its id, not by the execution holding it, so a worker whose job "
            "was already cleaned up can still record a result for it"
        )
    }
}


def job_contract(connection: Any, **application: Any) -> ObligationContract:
    """RQ's contract with its worker, for one of the application's jobs."""
    return worker_contract(connection, gaps=RQ_PROPERTIES, **application)
```

Each entry becomes a [strict expected failure](vocabulary.md#strict-expected-failure):
the case is expected to fail with exactly that property, and if a later version
of the library behaves differently, the case fails and the entry has to be
revisited. Your declared properties stay true of the version your users pin.
pytest-obligation's django-tasks-db integration does the same inside its own
`worker_contract`, declaring that integration's known properties for every
caller.

## For your library: six things to write

Everything above maps to six pieces, whatever your library is:

| Piece | RQ's version | What it is for your library |
| --- | --- | --- |
| A host | `redis_host` | Count your library's commits and kill the worker after any of them; add reply, callback or publication faults if your storage or broker has them |
| A worker pass | `worker_pass` | Run your real worker, in process, for one burst |
| A recovery | `maintenance_passes` | What a deployment runs after a crash: time passes, workers start, your library's own cleanup runs |
| An ownership binding | `ownership` | Point `FencedOwnership` at your claim, your result writes, your heartbeat, your cleanup |
| A retry binding | `bounded_retry` | Point `BoundedRetry` at your retry policy |
| A contract function | `worker_contract` plus your declared properties | Assemble the rest, answer the ten questions, and take from the application only what is about its own jobs |

Run the same contract function in your own CI against a reference job that is
safe to repeat, as pytest-obligation's RQ suite does. Then the contract your
users rely on is the one you test, and any problem it finds is the library's.

## A heavier version: Due

[Due](https://github.com/gigaverse-app/due), a durable-work library for
Django, takes the same idea further. An application registers a unit of work
with Due; Due derives most bindings from it and decides which proofs apply
from the kind of work it is. The application describes only its outside call
and what a correct result looks like. The example in its
[conformance guide](https://github.com/gigaverse-app/due/blob/main/package/docs/conformance.md)
is one such declaration, and turns into 66 generated cases. The six pieces above are
where to start; Due shows how far the same pattern goes.

[Next: 5. An application on your library](framework-5-application.md)
