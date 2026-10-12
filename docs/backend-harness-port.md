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

## Cutover follow-through (October 2026)

A second audit compared the pre-cutover runtime and harness with both public
packages, including controls that remained outside the exported subtrees. The
combined inventory examined 85 implementation modules (803 top-level definitions)
and 998 named test functions. Name matches were only a starting point: renamed
proofs were checked against their new owners and negative controls.

The reusable cutover changes in this package are:

- A configured `Host` factory resolves on the first proof, after application
  setup; sessions that never request a proof do not initialize it. Invalid
  factories and import errors still fail loudly. See
  [host configuration](pytest-plugin.md#host-configuration).
- Static coverage accepts explicitly reviewed suite wrappers through
  `CoverageConfig.suite_aliases`. It never guesses that an arbitrary decorator
  creates a contract. See [plugin configuration](pytest-plugin.md).
- `assert_schedule_contract(..., task_names={"myapp.tasks.sweep": sweep.name})`
  binds a computed Celery name to its actual installed task. Unbound computed
  names still fail the production-task check.
- Owed-row and selection-completeness proofs share
  [one delivery contract and observer](selection-completeness.md#one-delivery-binding-for-both-checks).
- Ownership races retain BE's minimum timeout and stalled-transaction cleanup.
  The Django host and Due histories share bounded worker connections, including
  both psycopg drivers. See [the host cleanup contract](integrations.md#bounded-ownership-racers).
- Source archives and embedded subtrees build with an explicit development
  version fallback when Git tags are unavailable.

The audit also recovered Due-specific database, discovery and enrollment
controls. Their owner is [Due's cutover audit](https://github.com/gigaverse-app/due/blob/d9147b3/docs/cutover-audit.md).

| Original behavior | Current executable controls |
| --- | --- |
| Profiles, binding provenance, narrow known gaps, generated cases | `tests/core/contract`, `tests/core/profiles`, `tests/core/safety` |
| Crash/error chains, scoped arrangements, independent outcomes, seam restoration | `tests/core/test_crash_histories.py`, `test_external_call_seams.py`; `tests/django/test_commit_observer.py` |
| SQL-managed commits, function writes, anonymous blocks, dead-session cleanup | `tests/django/test_commit_observer.py` |
| Legal edges, terminal states, selected/skipped branches, poison and stop requests | `tests/django/automatic_recovery`, `tests/core/automatic_recovery`, `tests/core/test_poison.py` |
| Bounded ownership and real lock races | `tests/core/profiles/test_bounded_ownership.py`, `tests/django/test_claim_race.py` |
| Index eligibility and retained-history scans | `tests/core/automatic_recovery/test_plan_verdict.py`, `test_leading_index_key.py`; `tests/django/automatic_recovery/test_selection_inspector.py` |
| Source coverage, exemptions, publication ordering, Beat inventories, declaration policy | `tests/core/coverage` |
| Debt baselines, subsets, node selection and parallel collection | `tests/core/contract/test_debt_collection.py` |

Application schedules, alert destinations, migration history, provider fixtures,
tenant values, reviewed exceptions and historical debt remain consumer-owned.
The generic scanners and proofs consume those declarations. Due's unused native
lifecycle convenience API is intentionally excluded; generic proofs for
application-owned ORM lifecycles remain supported.

## Second pass: consolidation and SQL evidence

The first cutover comparison used merged backend `main`. A second pass also
examined the concurrent consolidation branch, since merged as backend #5361
(`31c25aa13`), and inspected function bodies and shared helpers outside the
original harness directory. It recovered these additional owners:

- `ContractCase.parameter` applies the configured host's database marks and
  strict, optionally exception-limited gaps across profiles, selections,
  handoffs and interleavings. Case IDs, fixtures and gap restrictions remain.
- Binding guards share cycle-aware traversals while keeping two trust rules:
  authorship stops at production or harness code; delegation follows referenced
  test helpers to establish a production or shared-proof dependency.
- Owed-row proofs consume `OwedRows` and `EdgeFamily` directly; the shared
  selected-row verdict accepts `RowExecution`. `EdgeFamily.target` rejects a
  mismatched model before writing an edge. See the [direct-call migration](selection-completeness.md#direct-proof-call-migration).
- Lifecycle coverage and selection completeness share `lifecycle_paths` and
  `StatePath.choices`, carrying over the earlier backend state-resolution
  consolidation as well as its rejection of mismatched or unenumerable fields.
- Index verdicts reuse the SQL masking that lock-order observation already
  trusted. A column mentioned only inside escaped strings, dollar quotes,
  comments or a different quoted identifier cannot count as an index constraint.
  Six negative controls failed before the fix. Review reproduced two more
  failures with numbered dollar tags and doubled quotes inside identifiers.
  The repaired reader passes all 84 plan controls, including a real-key-positive
  variant of every text counterexample.

The SQL reader lives under `integrations._internal` and imports no framework or
driver; public plan and lock-order interfaces remain in their existing modules.
This remains a lexical proof over captured plans, not an arbitrary SQL parser.

## Third pass: real adopters and adjacent tooling

After #57 and Due #22 merged, the comparison was repeated against backend
`e2c88be1a`, including the nested implementation bodies and the surrounding
session helpers. The inventory covers 86 implementation modules and 804
module-level definitions; name matches were only an index into the behavioral
review, not a claim of equivalence.

| Remaining difference | Disposition |
| --- | --- |
| Fixture validation before skipped-test setup | Ported as `--due-work-check-fixtures`, with subprocess/xdist controls and adopter CI usage; backend can remove its local plugin. |
| Native completion/route wrappers | Intentionally dropped by the owner; they were unused. Generic ORM lifecycle proofs remain. |
| Old commit observer, broker/death helpers and selected-row helpers | Public `integrations.django.writes`, `crash_histories`, Celery handoff runner and `RowExecution` own the equivalent behavior. Driver-independent cursor handling and guarded binding scopes are stronger public behavior. |
| Beat and ambient-universe checks | Public scheduled-source and host scope hooks own the generic proof; backend retains its actual schedule and tenant policy. |
| Plan/index helper names | Public PostgreSQL catalog and lexical plan readers own the proof, including the SQL-literal fixes from #57. |
| Source walkers, real-provider guards, wiring snapshots, migration round trips and optimized transactional flush | Backend-wide test infrastructure with application-specific classification, credentials, migration/deployment and isolation policies; these are not missing due-work library implementations. |

Integration also exposed defects that a source comparison could not: committing
selection histories used an artificial transaction and left initial/gap example
rows behind. The real Wagtail worker now runs with its normal connection behavior;
root regressions require committed histories to clean up their own rows. Exact
edge aliases and an explicit fixed routing scope let that adopter expose precise
lifecycle findings without disabling the proof. See the [adopter capability
matrix](adopter-capabilities.md#integration-of-the-upstream-parity-changes-57).
