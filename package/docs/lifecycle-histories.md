# Prove overlapping producers and settlement races

A recovery or replay proof can pass while an application loses work when two
different entry points touch the same owner. Inventory migration bridges,
webhooks, repair commands and ordinary producers before choosing bindings.
Running each producer separately does not establish their composition.

A fixed provider identity can still have a growing requested effect scope.
Inventory every admitted input before declaring immutability. Bind the existing
convergence and stale-snapshot families for mutable scope; do not decline all of
profile E merely because the owner ID or provider key cannot change.

Declare named `admission_overlaps` and `settlement_interleavings` on
`ObligationContract`. Each factory yields fresh wiring from
`pytest_obligation.lifecycle` in a context that owns its external seams.
Generated cases have separate report identities. Omitted mappings are reported
as outside coverage, even when every A–J profile passes.

## Cumulative admission

`AdmissionOverlap` binds `first`, `later`, `recover`, `observe`,
`expected_first` and `expected_combined`. Both commands target the same real
owner. The first requests a subset of effects; the later requests more effects.
Suppress notifications so the first command leaves pending work. If the later
command also attempts inline work, inject a provider failure and lose its retry
publication in the binding. Do not replace its admission or recovery decisions.

Two generated histories run the later command while the first is pending and
after it has completed. Each recovers and checks the independently specified
combined outcome, then replays the first command and checks that the broader
promise and once-only effects survive. This applies to cumulative obligations;
replacement semantics belong in the existing convergence profiles instead.

Observe every promised effect and meaningful duplicate count, including the
first producer's result. A work row marked successful is insufficient. The
proof rejects an already-completed first example or identical expectations.
It does not infer which commands share an owner from their names.

## Competing settlement

`SettlementInterleaving` binds `run`, `compete`, `observe_competing`, `during`,
`recover`, `observe` and `expected`. Arrange admitted work first. `during` is a
context factory accepting a checkpoint callback. Install it at the external
observation boundary reached by the real operation. The callback calls the
other production transition, such as a webhook's terminal state transition.

The shared proof requires that checkpoint exactly once during `run`, and
requires the competing command to change observable product state. It then
runs production recovery and checks all promised effects. A failed guarded
update may mean another path committed its state and crashed before effects;
terminal state alone must not discharge those effects.

This is a deterministic ordering at a declared checkpoint, not simultaneous
threads or exhaustive database scheduling. Use process or real-connection
histories when that is the claim. An absent or inert checkpoint, or one invoked
only during setup, is a failing binding, not passing coverage.

## Verify the observer

For a host version that exposes only `extras`, declare
`ExtraProof(name="...", run=LifecycleProof(binding=..., proof=...), transactional=True)`.
`LifecycleProof` runs the same shared assertion with its binding scope open.
This lets an application upgrade its proof library without importing unrelated
runtime or database changes. Declare both admission assertions separately.

Use `RegressionControl` in `ExtraProof` with
`assert_pending_admission_preserves_effects`,
`assert_settled_admission_preserves_effects`, or
`assert_competing_transition_preserves_effects`. Each accepts the same typed
evidence as its generated case and enforces production bindings. Keep the
binding and expected outcomes unchanged. Restore the original faulty production
behavior, require the intended missing/duplicate-effect assertion, and verify
the restored baseline. Binding setup/cleanup errors are not detection.

Record tested producer pairs and checkpoints alongside results. Missing pairs,
partial-progress histories and independent worker races remain review questions;
these cases do not certify undisclosed entry points.
