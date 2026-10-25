# Framework integrations

The core accepts plain Python callables and depends on pytest and pydantic,
not on a framework. Optional extras install adapters for failure boundaries a
framework or driver exposes. A test still needs production bindings,
independent observation, and the recovery path the application actually runs.

```python
# conftest.py
from pytest_obligation import configure
from pytest_obligation.integrations.django import django_host

configure(django_host(production_packages={"myapp"}))
```

| Extra | Scope |
| --- | --- |
| `[django]` | `django_host()`: transaction and commit faults, PostgreSQL plan inspection, lifecycle-state proofs, and pytest-django marks |
| `[celery]` | Beat-schedule evidence, held or refused publications, real worker death points, callback failures, and `worker_contract()` |
| `[procrastinate]` | Worker recovery, stalled-job arrangement, and periodic-task evidence |
| `[dbos]` | Application restart through its own startup for process-level crash histories |
| `[redis]` | `redis_host()`: Redis write/pipeline commit counting and lost write replies |
| `[rq]` | Real RQ worker and recovery, ownership proofs, callback breaker, and `worker_contract()` |
| `[mongodb]` | Acknowledged writes, transaction commits, worker death, and lost replies for PyMongo; Motor uses its delegate. [Boundaries](mongodb.md) |
| `[prefect]` | Real flow-body execution and declared recurrence checks. [Scope](prefect.md) |
| `[aiokafka]` | `AIOKafkaConsumer` acknowledgement and offset-commit faults with broker replay. [Scope](aiokafka.md) |

The harness can test a Shopify integration or any other external API through
the application's real Python call and observed effects. The optional-import,
dependency-free [Shopify billing simulator](shopify.md) models accepted keys,
rejections and delayed meter visibility; it is not a Shopify HTTP client or a
complete provider emulator. To build a fake for another provider, start from the
provider-neutral [faithful-fake building blocks](faithful-fakes.md). See
[the adopter capability map](https://github.com/gigaverse-app/pytest-obligation/blob/main/docs/adopter-capabilities.md) for what existing suites
actually exercise.

## Bounded ownership racers

`FencedOwnership.race_timeout` and the race proof's explicit `timeout` must be
finite and at least 0.01 seconds. A smaller value can round a PostgreSQL lock
bound to zero, which means waiting indefinitely.

A host's `connection_scope` runs inside each racer thread. It may yield a
`ConnectionCleanup` callback that is safe to invoke from the waiting thread.
The race invokes that callback only for a racer still alive at its deadline,
before raising the failed-proof assertion. Returning `None` retains the default
behavior for hosts without external resources.

The Django integration uses `integrations.django.worker_connections` to set
lock, statement and idle-transaction bounds on each worker's own connection
settings. It restores settings and closes connections on scope exit. Its
cleanup terminates only the stalled worker's PostgreSQL session, so a thread
stuck in Python cannot leave row locks blocking test teardown. The shared helper
also backs Due's work-table histories. Both psycopg drivers are exercised in CI.
A connection setup failure is reported by the proof, rather than escaping as an
unobserved thread exception.

## Database visibility scopes without application models

`pytest_obligation.integrations.django.transactions.transaction_in_progress()`
holds an independent PostgreSQL transaction with an assigned xid while its body
runs, then closes that connection on success or failure. The caller's connection
and transaction ownership are unchanged. This reproduces old snapshot horizons
that can make newly rebuilt indexes temporarily unusable in concurrent CI.
It defines no Django models and imports no application registry.

Due re-exports the same helper from its existing conformance database module;
applications that only need the transaction scope should import it here directly.
`worker_connections` separately owns bounded worker-thread connections, and
`lock_order` owns the shared per-process lock-order ledger. Import those public
owners instead of retaining private copies: two recorders with separate ledgers
cannot detect ordering cycles across their callers.

## Bind application outcomes once

A generated contract automatically runs its `handoffs`, `process_handoffs`, and
claimed `replay` proofs. Attach the binding to the contract; a helper function
that nothing references provides no coverage. History and replay bindings require an
independently declared `expected` outcome when executed by a contract. A missing
outcome fails even when a legacy divergence is a known gap. Standalone history
and replay functions still support convergence-only checks. A generated replay
gap accepts only `ReplayDiverged`: a correct first execution followed by a
different result on replay. Missing declarations and wrong first results fail
independently, even when the replay case has a known gap.

Use `expected=` on `HandoffHistory`, `ProcessHistory`, and `ReplaySafeEffect`.
It accepts a value (including `None`) or a callback from the arranged handle to
the required outcome. Derive that value from the command's input, never by
reading the result being judged. Replay proofs check it after both executions;
crash proofs check normal operation before comparing interrupted histories.
Existing proof names and contract wiring are unchanged.

The [catalog binding](https://github.com/gigaverse-app/pytest-obligation/blob/main/examples/adopter/test_bindings.py) is reused by the
inline, Celery and RQ suites: it admits `"red"`, executes the real worker,
observes remote content, and declares `expected="red"`. Its
[negative control](https://github.com/gigaverse-app/pytest-obligation/blob/main/examples/adopter/tests/test_catalog_failures.py) corrupts
the provider payload and runs the generated contract case. Equal wrong results
must fail. The Procrastinate, Wagtail, DBOS and Saleor demos similarly declare
indexed books, deleted objects, sent events, or completed orders and money.
`celery_worker.worker_history()` requires and forwards `expected=` as well.
RQ and django-tasks worker contracts accept `expected=TaskOutcome(...)` and
forward it through their shared task-queue binding, including two-queue histories.

When copying a binding with `model_copy(update={"observe": ...})`, update
`expected` to the new observation's contract too. These are bounded proofs of
the declared outcomes and fault boundaries, not a proof of all application
behavior or arbitrary provider failures.
