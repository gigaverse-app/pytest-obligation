# Complete backend harness port

The reusable backend harness is split between two public owners:
`pytest-obligation` owns framework-neutral assertions and static checks;
`due.django.conformance` owns bindings and generated scenarios that require Due's
work-table runtime. Install Due's `testing` extra for that integration. Do not
copy it back into this package or bind it to a second implementation of Due.

The extraction source is gigaverse-backend `04786fb2d`. Due's core integration landed in
[Due #5](https://github.com/gigaverse-app/due/pull/5);
[Due #9](https://github.com/gigaverse-app/due/pull/9) completes the scheduler and
interleaving adapters, bounded downstream handoff recovery, query-scale proof,
and the remaining mutation controls. This repository's CI installs its
candidate wheel over that checkout's locked obligation dependency, then runs the
complete suite and requires both primitive and application evidence reports.

## Ownership and migration map

| Backend harness | Public owner |
| --- | --- |
| `contract`, binding guards, poison, profiles A–J, exemptions, observations, interleavings | `pytest_obligation`; `DueWorkContract` becomes `ObligationContract` |
| Recovery sweep and poison/stop proofs | `pytest_obligation.profiles.automatic_recovery` and `.poison` |
| Lifecycle, edge catalog, owed rows, observed writes and lock order | `pytest_obligation.integrations.django` |
| Handoff crash histories | `pytest_obligation.crash_histories`; scoped arrangements, independent `expected` oracles and production-bound `recovery_ticks`; Due delivery runs bounded downstream rounds |
| Celery schedule evidence, publications and handoffs | `pytest_obligation.integrations.celery` |
| All 15 `work_table` modules | `due.django.conformance`: bindings, suite, scenarios, recovery isolation, discovery admissibility, observations, composition, concurrency, indexes, database, enrollment, collected effects, collection validation and reporting |
| Full simulated broker, delayed retries, failure accounting, worker connections and registration fixtures | `due.django.conformance.background`, `.worker_connection`, `.registrations`, `.background_beat`, `.interleavings` |
| Primitive-derived enrollment/session outcomes | Due's pytest plugin and `_suite_inventory`; application source roots and registration fixture remain explicit |
| Source/disposition coverage | `pytest_obligation.coverage`; recognizes Due's exact `effect_contract_suite` decorator as well as generic suites |
| Transitive publication-before-commit tripwire | `pytest_obligation.coverage.transactions` |
| Beat classification, call chain, idle return, stale threshold and exemption inventory checks | `pytest_obligation.coverage.schedules` |
| Optional declare-rather-than-call policy | `pytest_obligation.coverage.proof_calls` |

The final three analysis engines were previously left in backend tests alongside
application allowlists. Their reusable behavior is now public. Backend-specific
schedule entries, exemption reasons, frozen migrations, production/provider
wiring, tenant values and application fixtures remain application data. Public
scanners take those inputs; they do not embed Gigaverse policy or import its code.
Reference models/self-tests are test implementations, not application runtime
requirements; the public packages supply their own reference owners.

## Static checks without importing production

The existing coverage configuration supplies source roots and production packages.
Add project-specific transaction decorators explicitly:

```toml
[tool.due-work-harness]
production-packages = ["myapp"]
transaction-openers = ["myapp.transactions.aatomic"]
```

`pytest-obligation before-commit` traces direct Celery publications back through
transaction-held calls, including typed collaborators, inherited methods,
relative imports and `sync_to_async`. It reports the call chain and exits 1 if
any exists; malformed or hidden production source is an error. Use
`assert_publications_reviewed(config, reviewed=...)` for a precise application-owned
legacy inventory. Added publishers, stale entries and thin reasons fail.
`in-transaction` retains its existing lexical, multi-framework behavior.

The transitive scan deliberately does not infer arbitrary local variables,
factory results, concrete implementations behind abstract ports, or deferred
lambda/nested-function execution. It is a tripwire, not complete Python
call-graph analysis or a substitute for runtime admission histories.

`assert_schedule_contract(Project(config), schedule, sweeps, intervals=...,
default_stale_after=...)` accepts entry-to-task names, task classifications and
policy values. `RecoveryTick(via=...)` follows production callables;
`NoPerRowLoop(reason=...)` checks the claimed structure; `Grandfathered` requires
an exact reviewed set. Generated recovery tasks supply their explicit registry
mapping via `generated_recovery`. Static task names can be literals or imported
constants. Static recovery thresholds must equal twice the shortest cadence,
with the caller's minimum threshold. A computed threshold is reported for review.
These checks preserve the backend's source-shape limits; runtime poison proofs
still establish actual row isolation.

`proof_calls(module, source)` finds direct public-harness proof calls outside
`ExtraProof` runners. Applications that require generated enrollment can use
`assert_declared_proofs(sources, reviewed=...)`. Standalone proofs remain supported;
the library does not impose this application policy globally.

## Preserve coverage during migration

A Django host supplied with `ambient_context` now automatically includes the
restoration proof, so tenant coverage cannot disappear merely because a second
opt-in was omitted. Remove an older manual append of `AMBIENT_CONTEXT_PROOFS`.
Retain `owed_model` for native ORM contracts and related `owed_edges` for selection
contracts. Install the actual Celery stop exception and handoff/publication hooks.
Give the public pytest plugin sole ownership of `--due-work-explore`; translate
BE's `extended` setting to the public `deep` mode deliberately.

The earlier [migration rehearsal](plans/backend-migration-audit.md) remains
historical evidence: native/light consumers matched 98 cases (90 passed, eight
unchanged strict expected failures), but the work-table port did not exist then.
The work-table gap is filled by Due #5 and #9. This completes the reusable harness extraction, not
BE's production runtime/data cutover: retained receipts, table identity, queued
task aliases, tenant routing and all application journeys still need a separate
migration. No backend production code or database is changed by this port.

## Verification

The complete Due suite ran against this obligation source with isolated
PostgreSQL 17 and Redis: **887 passed before the final gate controls**, including real Celery worker and
process-death histories. CI also installs the built candidate wheel into Due's
locked environment and requires executed A–J and application reports.

Core plus the example adopter: **1,083 passed, one optional-dependency skip,
three inventory cases deselected**; the example inventory runs separately in CI.
The static coverage suite includes the extracted backend controls and new
negative controls for stale/growing exceptions, broken scheduling declarations,
unreadable production and counterfeit Due suite decorators.

Against the real backend source at the extraction revision, the public engines
matched all **78 task definitions**, validated **40 Beat entries and 24 task
classifications**, found the identical **two transaction-held publication paths**,
and matched the **five reviewed hand-called proofs across 932 test modules**.
The same backend-reviewed exceptions passed unchanged. These comparisons ran in
a disposable backend archive with dummy settings; application code was not edited.

The migration audit also found three controls that import parity misses.
`HandoffHistory.expected` accepts a value or pre-transition handle callback; a
consistently wrong delivered result fails outside known-gap handling.
`recovery_ticks` are checked as production bindings and require a delivery with
`recover_with(ticks)` support, so unsupported adapters cannot silently omit them.
Due advances three bounded recovery rounds beyond leases and pending ETAs, runs
the primary and downstream ticks, lifts task-instance recorders, and rejects
unobserved queued work. Consumers can configure the round count and delay.

Due's final controls cover generated eligibility (including same-value SQL and
writable CTE mutations), dependent wakes, receipt repair, rejection policy and
simple-callback races. Its shared retained-history proof measures total PostgreSQL
reads, checks equivalent renamed indexes, and rejects full-history scans and
missing access paths. Historical BE migration schemas, alert configuration and
application-specific evidence-boundary allowlists retain their application owner.
