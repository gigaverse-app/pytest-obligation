# Recovery must survive the rows normal writers never create

A recovery query reads persisted rows, including values that model validation
would refuse today. A green test over a valid example does not establish that an
empty filename, retired choice, or exhausted integer counter is recoverable.

## Poison isolation and stopping

Profile A generates two cases for every `DueWorkSweep`:

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
The standalone `assert_one_failing_row_does_not_stall_the_tick` uses this
same oracle. Replace its old `fail_dispatch_for=` with `switch=PoisonSwitch()`
and `still_owed=`; a loop that swallows an exception no longer passes.

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

A selection-only contract also takes `extras=`, the same `ExtraProof` tuple an
`ObligationContract` takes, for a standalone proof the loop needs (for example
`assert_provider_call_holds_no_transaction` around the loop's provider call).
Extras are validated as on the full contract and each one collects as an
`extra-<name>` case; a gap on an extra counts against the `NEW_FEATURE` policy
like an entry in `gaps`.

The suite checks the production bindings, a valid row's completion, and that the
dispatch recorder follows the selection order. It then generates poison/stop
cases and two cases per edge: the selected row is handled or excluded, and it
does not block the next valid row. A recorder entry or no-op commit callback is
not progress. Legacy edge gaps absorb only `OwedRowNotHandled`, never a broken
binding or positive control.

### Polling selections

The valid-row control above requires a served row to leave the selection,
because that is how the suite tells "served" from "did nothing at all". Some
loops are served by staying selected: a sweep over rows in a long-lived active
state re-reads each one every tick, and a producer that records nothing lets the
next period select the same identity again. Declare that, with the reason:

```python
from pytest_obligation import Polling, ScheduledSelection

selection = ScheduledSelection(
    name="active sessions",
    due_work=select_active_sessions,
    assert_scheduled=schedule_evidence,
    owed_rows=bind_session_poll,
    owed_edges={"session": EdgeFamily(model=Session)},
    polling=Polling("sessions stay active for hours; every tick re-reads their provider state"),
)
```

Polling replaces exactly one case and extends another; the case list shows which:

- `assert_a_polled_row_is_served_and_stays_selected` replaces
  `assert_valid_owed_row_leaves_the_selection`. One delivery to `execute` and
  two production ticks must each finish without raising, write something or
  add an effect counted by `effect_calls_for` (bind it when the per-tick effect
  is only a provider call), and leave the row selected; each tick must also
  record the row in `dispatched_ids`. A row that leaves the selection fails it,
  so a sweep whose served rows leave cannot declare polling to skip the default
  control. A tick that serves each row once (a cursor, an already-served set)
  fails it too.
- `assert_one_poisoned_identity_does_not_stall_the_tick` runs its usual tick,
  then one more with the poison still armed: the healthy row must be dispatched
  again (`PoisonStalled`) and the poisoned one still selected
  (`PoisonDropped`). A loop that backs off the whole tick after a failure fails
  only here. The second tick may hold the poisoned row back, as a per-identity
  backoff would.

The stop-request and per-edge cases are unchanged; a polled row is always still
selected, so any raise on it, or a delivery that does nothing to it, fails its
edge case. `still_owed` does not apply: a polling selection keeps the row it
served, so its own selection is the owner the poison cases read.

### External-resource identities

Some loops owe work to identities that are not rows: a reconciler that lists a
provider's resources and deletes the orphans owes one deletion per orphan, and
nothing in the database names an orphan. Declare that, and bind the production
listing seam on `OwedRows`, with the provider fake supplying the resources:

```python
from pytest_obligation import ExternalIdentities, ScheduledSelection


def bind_orphan_reconciler() -> OwedRows:
    # ARRANGE: a provider fake installed for this case.
    provider = FakeChannelProvider()
    reconciler = ChannelReconciler(provider)
    # REAL PRODUCTION: the reconciler's listing, per-orphan step and tick.
    # EXTERNAL SEAM: the fake supplies the resources; a PoisonSwitch the step consults fails one.
    refusals = reconciler.refusals
    # OBSERVE: the reconciler's own record of what each tick deleted.
    return OwedRows(
        make_owed=provider.create_channel,  # one more orphan in the fake
        listed=reconciler.orphaned_channels,  # the production listing seam
        identity_of=lambda channel: channel.id,  # required: a resource has no primary key
        execute=reconciler.delete_orphan,
        run_tick=reconciler.tick,
        dispatched_ids=reconciler.deleted_ids,
        poison=lambda channel: refusals.poisoned(channel.id),
    )


selection = ScheduledSelection(
    name="orphaned channels",
    due_work=select_known_channels,  # what the loop reads from the database
    assert_scheduled=schedule_evidence,
    owed_rows=bind_orphan_reconciler,
    external_identities=ExternalIdentities("orphans are provider channels no row names"),
)
```

The binding guard, valid-identity control, order control, poison and
stop-request cases are generated as for rows, reading `listed` wherever they
would read `due_work`: a served orphan must leave the listing, and a poisoned
one must still be listed after the tick. `due_work` is still required and
still runs the selection proofs (authorship, index-served, primary), but no
owed-row case reads it. Bind it to a narrowed, production-bound query the loop
runs every tick. A loop whose only database read is "every known resource"
fails the index-served proof, and one that reads nothing from the database
cannot declare this yet; both are known limits of this first version.
There is no row to give database-legal values, so `owed_edges` and
`state_fields` are refused. The guard checks `listed` reaches production like
`execute`; binding `listed` without the declaration, or declaring it without
`listed` or `identity_of`, fails. `ExternalIdentities` and `Polling` compose,
for a listing whose resources stay listed after each tick.

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

## Real database errors at a poison seam

For a PostgreSQL loop whose per-identity savepoint must isolate failed SQL, use
`pytest_obligation.integrations.django.database_faults.fail_like_a_database_error`.
Pass the binding's `PoisonSwitch`, identity and message at the real persistence
seam. An armed identity executes a failing SQL statement before re-raising the
original poison or cooperative-stop exception. An unarmed identity does no SQL.

The helper deliberately opens no transaction or savepoint: the production
caller must roll back its own failed transaction before later identities can
progress. In autocommit the failed statement rolls back independently. Use a
broker refusal instead when database isolation is not the boundary under test.


## Retry waits inside the executor

A persistent-retry selector may return waiting candidates while the production
runner checks their deadline. With `PersistentRetry(waits=True)`, the proof now
invokes that runner when a waiting identity remains selected. Its failure-attempt
count, terminal status and observable state must stay unchanged. Once the bound
wait is advanced, the next invocation must reach the failing dependency again.

This supports an execution gate without copying its predicate into the test's
selection. A hot-looping runner, a hidden state change or abandoned work still
fails. `waits=False` continues to describe a lifecycle with no per-identity delay;
the separate schedule binding establishes its recurring cadence.

## Eligibility inside a recovery loop

A recovery read can return owed candidates and let the real worker check their
eligibility before mutation or effects. The A/G composition proof runs that
actual sweep while the gate is blocked and applies the existing no-write,
no-execution, no-provider-effect and retained-intent assertions. It then requires
the released identity in the sweep selection and observes its recovery through
the sweep's dispatch path. The binding does not need to move the application's
gate into a copied database predicate.
