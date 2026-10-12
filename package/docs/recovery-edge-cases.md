# Recovery must survive the rows normal writers never create

> Historical scope: the remaining reusable harness checks and Due integration are
> now covered by the [complete port](backend-harness-port.md). The ownership decisions below
> describe the earlier extraction; application runtime/data cutover remains separate.

A recovery query reads persisted rows, including values that model validation
would refuse today. A green test over a valid example does not establish that an
empty filename, retired choice, or exhausted integer counter is recoverable.

This port audits gigaverse-backend `f933d6075..04786fb2d` (2026-10-11).
The primitive is being extracted separately to `gigaverse-app/due`; this PR
changes only `gigaverse-app/pytest-obligation`.

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
The standalone `assert_one_failing_row_does_not_stall_the_tick` now uses this
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

Celery schedule evidence now checks the app's task registry. A registered name
may differ from the Python import path; an importable function that is absent
from the registry no longer passes. Tests supplying an app stand-in must supply
its `tasks` registry as well as `conf.beat_schedule`.

Source mapping:

| Backend changes | Public equivalent |
| --- | --- |
| #5308, #5327, #5345 | Shared poison/stop oracles and generated profile-A cases |
| #5307, #5312, #5313, #5314, #5322 | Django edge catalog, related-row families, generated native/light cases |
| #5317, #5321 | Captured Celery options, real retry behavior, delayed/callback handoff execution |
| #5343 | Notification-only exemption probe and controls |
| Binding fixes in the same range | Caller-argument checks through partials and receivers |
| #5174 schedule evidence after task-module moves | `celery_beat_evidence` checks registered task names |
| Backend multi-capability recovery ticks | Existing public `DeliverySession.recover()` owns composed downstream recovery |

## Audit of the remaining backend changes

These are deliberate ownership decisions, not claims that the public package
implements every backend policy. Primitive-specific conformance needs an adapter
for `due` once that project's API exists; it must not import Gigaverse models.

| Source area / changes | Disposition and evidence |
| --- | --- |
| `contract.py`, `binding.py`, `gap_probes.py`, `poison.py`, `edge_values.py` | Ported shared behavior; core and generated Django controls exercise both valid and faulty declarations. Compatibility imports still reach the canonical implementation. |
| `profiles/automatic_recovery/{sweep,owed_row_admissibility,terminal_states}.py` | Ported new behavior, including the standalone poison wrapper, related rows, precise gap failures, recorder controls, and handoff effect observation. Existing public lifecycle-state proofs remain in the Django integration. |
| `profiles/automatic_recovery/handoff_crashes.py` | Backend adds downstream `recovery_ticks`. The public `CallableDelivery.recover` / `DeliverySession.recover` already owns the complete recovery sequence and has a production-binding guard (`tests/core/test_crash_histories.py`). No second recovery owner is added. |
| `coherence.py`, `primitive.py`, bounded ownership, fact-derived obligations | Changes are source/doc paths and a note about the new work-table discovery tests. Public A–J names and composition already shipped in the previous port. |
| Reference implementations and moved `conftest` fixtures | Public controls use the package's existing reference owners. Backend application fixture moves are not copied. |
| Work-table `recovery_isolation.py` (#5298, #5303, #5327, #5345) | Shared oracle ported. Per-phase adapters directly import capability registrations, `RecoveryDeferral`, `RecoveryPhase`, the reap policy and generated task. Those cases belong with the `due` integration, including healthy controls, backoff, later-phase progress and phase exhaustiveness. |
| Work-table `discovery_admissibility.py` (#5304, #5322) | Edge catalog ported. Discovery cases require `Discovery.bounded_candidates`, `owner_attname`, `derive()` and `outstanding_work`, which the public harness does not own. Preserve these cases when binding `due`; native owed-row coverage does **not** certify discovery admission. |
| Work-table `scenarios.py`, `suite.py`, `bindings.py` (#5261, #5263, #5262) | Synchronous caller and dependent-wake histories drive the primitive's admission/inline completion/recovery/settlement APIs. They are integration work for `due`, not generic callbacks that this port could truthfully certify. |
| Work-table collection, enrollment, composition, observations, reporting (#5142, #5184, #5342) | These derive suites and profile dispositions from the registered primitive. Public generated A–J reporting and explicit assessment debt already exist; primitive-derived enrollment and dispositions require `due`'s registry. |
| Work-table query-scale tests (#5286) | Fixes the backend's retained-history fixture and index visibility. The public database selection tests retain their own real PostgreSQL controls. No primitive schema benchmark is copied. |
| `background_work.py` (#5317, #5321) | Ported owed-row delivery of delayed handoffs, commit callbacks and real Celery retry detection. The backend's full simulated broker (retry signatures, jitter, failure accounting and primitive task routing) is not duplicated: the public harness already has real-worker delivery adapters. `celery_handoffs` deliberately fails an owed-row proof on a retry; it does not certify retry timing or budgets. |
| `background_beat.py`, `beat_sweeps.py` and their inventory tests (#5328) | The backend requires every Beat entry to use its `recovery_tick` primitive or a reviewed exemption, and ties intervals to its alert threshold. That policy and concrete schedule stay with Gigaverse. The portable registry evidence fix is included above. |
| `test_adopters_declare_rather_than_call_proofs.py` (#5314) | Repository policy forbids direct proof calls except its pinned allowance list. Public standalone proofs remain supported; generated native/light paths include the new cases. This port does not impose that policy on all external adopters. |
| Registry/source scanning (#5343) | Notification exemption probe ported. The backend's transitive pre-commit publication prohibition and pinned grandfather lists remain backend policy. Public `coverage` and `--due-work-verify` retain their own enrollment contract; `in-transaction` is a lexical scan and is **not** equivalent to the backend's transitive check. |
| Real-Redis/Hypothesis lanes (#5329), provider guard, session wiring and migration fixture changes | Public CI already runs exploration, Redis, real Celery workers and its integrations. Gigaverse provider allowlists, composition-root installation, migration models and test-session plugins are application-specific. |

The additional port controls reject a stop exception wrapped in an exception
group inside its own handler, and keep `PoisonSwitch` firing counts local to
each arm. A previous arm cannot satisfy the positive control for a seam that
never fires in this run; nested arms restore the outer arm.

### Real database errors at a poison seam

For a PostgreSQL loop whose per-identity savepoint must isolate failed SQL, use
`pytest_obligation.integrations.django.database_faults.fail_like_a_database_error`.
Pass the binding's `PoisonSwitch`, identity and message at the real persistence
seam. An armed identity executes a failing SQL statement before re-raising the
original poison or cooperative-stop exception. An unarmed identity does no SQL.

The helper deliberately opens no transaction or savepoint: the production
caller must roll back its own failed transaction before later identities can
progress. In autocommit the failed statement rolls back independently. Use a
broker refusal instead when database isolation is not the boundary under test.
