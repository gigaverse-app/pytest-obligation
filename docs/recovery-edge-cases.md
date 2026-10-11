# Recovery must survive the rows normal writers never create

A recovery query reads persisted rows, including values that model validation
would refuse today. A green test over a valid example does not establish that an
empty filename, retired choice, or exhausted integer counter is recoverable.

This port follows gigaverse-backend through `04786fb2d` (2026-10-11).

## Poison isolation and stopping

Profile A now generates two additional cases for every `DueWorkSweep`:

- `assert_one_poisoned_identity_does_not_stall_the_tick`: the injected failure
  fires, the following identity progresses, the tick reports the failure, and
  the poisoned identity remains owed.
- `assert_a_soft_time_limit_ends_the_tick`: the same seam raises a cooperative
  stop request. The tick propagates it, leaves the identity owed, and does not
  run the following identity.

Bind `poison(row)` as a context manager yielding a callable that counts injected
failures. `pytest_obligation.poison.PoisonSwitch` supplies `check(identity)` and
`poisoned(identity)`. Patch the per-row dependency the real loop calls; do not
replace the loop. For Celery publications use
`pytest_obligation.integrations.celery.refusing_publication(switch, task)`.

The framework-free default stop exception is `StopRequested`. A Celery host must
set `stop_exception=celery.exceptions.SoftTimeLimitExceeded`; the Django host
accepts that option. This checks the exception production actually handles.
Other synchronous workers can supply their own `Exception` subclass.

`progressed(row)` can observe completed work when merely reaching or publishing
an identity is insufficient. `still_owed(row)` observes a backoff or successor
selection when the failure legitimately moves a row out of the current selection.
Without it, the poisoned identity must remain in the original selection.

A legacy failure can name its precise outcome:

```python
Claim(
    gaps={
        "assert_one_poisoned_identity_does_not_stall_the_tick[stalled]": "the current loop stops at its first publication error",
    }
)
```

Poison outcomes are `stalled`, `dropped`, and `unreported`. Stop outcomes are
`dropped`, `swallowed`, `isolated`, and `continued`. These marks accept only the
named invariant failure; a missing seam or a non-firing fault still fails.
New-feature contracts cannot declare gaps. Existing profile-A adopters must bind
the new seam or explicitly record their legacy assessment gap.

## Django owed-row cases

Configure `django_host(...)`. A full `ObligationContract` opts into generated
edge cases with `owed_model=YourModel`; its sweep supplies `lifecycle.execute`
and `dispatched_ids`. The declaration must name the model its selection returns.
The public harness also supports non-ORM sweeps, so this field is optional;
profile A without `owed_model` does **not** certify database-legal edge values.

A selection-only contract can bind its per-row loop directly:

```python
from pytest_obligation import ScheduledSelection
from pytest_obligation.integrations.django.owed_rows import EdgeFamily, OwedRows

selection = ScheduledSelection(
    name="pending deliveries",
    due_work=select_pending,
    assert_scheduled=schedule_evidence,
    owed_rows=bind_delivery_loop,  # a factory returning OwedRows
    owed_edges={"delivery": EdgeFamily(model=Delivery)},
)
```

`OwedRows` binds `make_owed`, `execute`, `run_tick`, `dispatched_ids`, and `poison`.
Optional `deliver` transforms a row into the worker argument; `effect_calls_for`
observes external progress; `still_owed` follows an obligation handed to another
selection. Add a related-row family with
`EdgeFamily(model=Account, edge_row=lambda delivery: delivery.account)`.

The suite checks the production bindings, a valid row's completion, and that the
dispatch recorder follows the selection order. It then generates poison/stop
cases and two cases per edge: the selected row is handled or excluded, and it
does not block the next valid row. A recorder entry or no-op commit callback is
not progress. Legacy edge gaps absorb only `OwedRowNotHandled`, never a broken
binding or positive control.

The catalog covers empty strings, maximum string lengths, unknown string
choices, zero, negative one where legal, and each integer column's maximum.
It skips nullable, primary-key and relational columns; database constraints can
reject a candidate. It does not certify combinations, all possible values,
or an external provider's input rules.

## Follow the handoff to its outcome

For Django/Celery use:

```python
from celery.exceptions import SoftTimeLimitExceeded
from pytest_obligation.integrations.celery import celery_handoffs, celery_publications

host = django_host(
    production_packages={"myapp"},
    publication_recorder=celery_publications,
    handoff_runner=celery_handoffs,
    stop_exception=SoftTimeLimitExceeded,
)
```

`celery_handoffs` captures publications and executes the real Celery task bodies
through `Task.apply`, including autoretry behavior. It follows delayed handoffs
and executes commit callbacks, including under a test transaction. A delivered
task rescheduling itself is treated as a retry rather than drained indefinitely;
profile J owns retry budgets. A chain still publishing after 20 deliveries fails.
This is deterministic in-process execution, not a substitute for the existing
real-worker integration tests.

`Publication` now includes an optional fourth field, `options`, so countdown and
ETA information survives capture. Three-argument construction still works;
consumers unpacking exactly three values must switch to named attributes.
A host without a handoff runner refuses an observed publication rather than
certifying an unexecuted downstream effect.

## Other ports and boundaries

`LossDropsOnlyANotification` proves a best-effort notification exemption: product
state is complete without the dispatch, delivering the dispatch actually
notifies, and delivery leaves that product state unchanged. Binding integrity
now checks the first caller-supplied argument through partials, bound methods,
callable objects, and varargs.

Source mapping:

| Backend changes | Public equivalent |
| --- | --- |
| #5308, #5327, #5345 | Shared poison/stop oracles and generated profile-A cases |
| #5307, #5312, #5313, #5314, #5322 | Django edge catalog, related-row families, generated native/light cases |
| #5317, #5321 | Captured Celery options, real retry behavior, delayed/callback handoff execution |
| #5343 | Notification-only exemption probe and controls |
| Binding fixes in the same range | Caller-argument checks through partials and receivers |
| Backend multi-capability recovery ticks | Existing public `DeliverySession.recover()` owns composed downstream recovery |

The work-table runtime, its capability-specific generated histories (including
synchronous completion, discovery admission and dependent wakes), database
retention benchmarks, provider registrations, Beat inventory, backend CI source
scanner, Redis test-lane wiring, and publication policy are backend-owned. They
are not copied into this framework-neutral package. The public package's own
coverage scanner and real-worker adapters remain the owners of their respective
boundaries. This change does not extract or publish the runtime primitive.
