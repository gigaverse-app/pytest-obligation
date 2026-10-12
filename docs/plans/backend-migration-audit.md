# Can Gigaverse replace its local harness with pytest-obligation?

> Historical scope: the remaining reusable harness checks and Due integration are
> now covered by the [complete port](../../package/docs/backend-harness-port.md). The ownership decisions below
> describe the earlier extraction; application runtime/data cutover remains separate.

Not completely yet. The generic recovery port and stronger adopters are useful,
but they are not a complete replacement for the backend's current test harness.
The principal missing integration is the work-table conformance suite. It is
**test functionality**, even though it depends on the separately extracted `due`
runtime. Calling it runtime-only scope would hide a real migration blocker.

Audited on 2026-10-11 against backend `04786fb2d0c0027526785c415178d0486d9dc989`
(also `origin/main` when checked) and pytest-obligation `b819cbf5c8de2b133a4c3812779f07a8740104b2`
(PR #47, stacked on #46). The backend checkout and its environment were unchanged;
the rehearsal used a disposable archive, existing interpreter, public source on
`PYTHONPATH`, dummy provider settings and isolated PostgreSQL 16.

## Inventory and missing behavior

AST inventory found 68 non-self-test Python modules in the backend's `due_work`
harness, including 15 work-table modules. Outside that package, 65 Python files
import 122 distinct module/symbol pairs; 34 of those files import work-table
helpers. These counts include application tests and supporting test tooling,
not just adopter declarations. Symbol matching is an inventory aid, not a proof
of semantic equivalence.

| Area | Replacement status |
| --- | --- |
| Generic profiles A–J, binding guards, poison/stop, row edges, lifecycle states and notification exemption | Public implementations exist. The real native/light rehearsal below checks two consumers, not every profile or application. |
| Work-table recovery phases | Missing adapter for phase enumeration, per-phase positive controls, poison/backoff, later-phase progress and cooperative stop. Shared poison assertions alone do not replace these histories. |
| Work-table discovery | Missing candidate admissibility and healthy-tail histories over the primitive's bounded candidates, owner mapping, derivation and outstanding-work observation. Existing owed-row edges exercise already admitted work. |
| Admission, synchronous callers and settlement | Missing primitive-bound producer/rejection/receipt/inline-completion scenarios, dependent wakes, terminal failure/rearm and competing-delivery settlement. |
| Observations and compensation | Missing registry-derived observation recovery without resending, composition examples and compensation enrollment. |
| Enrollment, collection and outcomes | Missing primitive-derived required examples/profile dispositions, complete-suite checks, strict outcome enforcement and worker report merging. Public A–J reporting is not an equivalent replacement. |
| Backend schedule and source policy | Keep the Beat registry/exemption policy, alert-threshold rules, provider guard and transitive pre-commit-publication scan in BE. The public lexical coverage scan does not replace them. |
| Simulated broker and application wiring | Retain BE glue for primitive routing/worker-option assertions, retry-signature and jitter behavior, universe context, provider fakes and composition-root installation until equivalent bindings are demonstrated. |

The detailed ownership decisions in [recovery edge cases](../../package/docs/recovery-edge-cases.md)
remain valid. They explain where remaining work belongs; they do not make the
full backend migration complete. The missing work-table harness should be bound
to `due` through an integration with a declared version contract, while the
primitive's implementation stays in its own repository.

## Migration rehearsal

Three real backend adopters collected 185 tests before substitution: email
campaign unpark (light selection), stale recording recovery (native profile A),
and profile-picture renditions (work-table capability). Blind package-name
substitution failed collection; the complete-suite hook also correctly rejected
the selected rendition suite disappearing.

The targeted rehearsal migrated the first two adopters and their shared email
recovery helper. It deliberately retained work-table code and BE session policy.
It required:

1. Map `DueWorkContract` to `ObligationContract`, move ORM lifecycle/owed-row
   imports to `integrations.django`, and move schedule evidence to
   `integrations.celery`.
2. Use `EdgeFamily(model=...)` and the public `refusing_publication(switch, task)`
   helper. Keep each poison seam and its proof on the same public exception types.
3. Configure the Django host with `gigaverse` as production code, actual Celery
   publication/handoff helpers, `SoftTimeLimitExceeded`, replica aliases and
   `get_current_universe`. Preserve the existing `owed_model=RoomEgress` binding.
4. Append `AMBIENT_CONTEXT_PROOFS` to the host's `sweep_proofs`. Merely supplying
   `ambient_context` did **not** generate the check: the first adapted collection
   silently fell from 98 to 97 cases. The generic proof is present but opt-in.
5. Give the public plugin sole ownership of `--due-work-explore`; loading both
   original plugins raised `argparse.ArgumentError` for the duplicate option.
   BE's `extended` versus public `deep` exploration levels still need an explicit
   migration decision. Exploration was off in this rehearsal. Keep BE's separate
   complete-suite and outcome hooks.

| Execution | Cases | Passed | Strict expected failures |
| --- | ---: | ---: | ---: |
| Original backend harness | 98 | 90 | 8 |
| Public harness, first host configuration | 97 | 89 | 8 |
| Public harness, ambient proof restored and public plugin enabled | 98 | 90 | 8 |

The final comparison matched every normalized case identity and outcome, allowing
only `assert_the_tick_restores_the_ambient_universe` to become
`assert_the_tick_restores_the_ambient_context`. It found no missing/added cases or
changed outcomes. The eight expected failures preserve existing strict declared
gaps/debt; no new gaps or skips were added to make the rehearsal green. Both
complete runs emitted the existing BE threadpool-cleanup warning.

Evidence retained with the local audit: import inventory, adaptation script,
unified migration patch, baseline/public JUnit, public profile report, normalized
case comparison, and failed-startup logs. The public host and CLI changes are
rehearsal artifacts, not edits to the user's backend checkout.

Passing these consumers establishes a practical path for the generic harness.
It does not establish full migration: their email fake broker still imports the
local work-table worker-option checker when a primitive task is dispatched.
Removing the local package would break that path and the other work-table users.

## Completion criteria for a real migration

- Port the missing work-table test integration against `due`, including its
  recovery/discovery, synchronous caller, observation and settlement histories.
- Bind representative registered capabilities and exercise the integration's
  negative controls; do not replace registry-driven checks with manually listed
  generic profiles.
- Migrate imports and host/plugin configuration across the complete consumer
  inventory. Keep backend policies as explicit local owners.
- Compare normalized generated case identities, outcomes and strict gaps before
  and after for every adopter; account for renamed proofs explicitly. Reject
  lost cases, regular skips, weakened bindings and narrowed failure coverage.
- Run the full backend harness/adopter and exploration lanes, then remove the
  old generic implementation only when the dependency graph proves it unused.

This audit does not claim a full backend test run, complete runtime extraction,
or portability of every self-test/reference implementation. It identifies the
missing behaviors and verifies a bounded, executable migration slice.
