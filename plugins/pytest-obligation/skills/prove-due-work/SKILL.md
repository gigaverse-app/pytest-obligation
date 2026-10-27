---
name: prove-due-work
description: Use pytest-obligation to generate a standardized ObligationContract pytest suite, and add focused fault-injection tests, when Python work could be lost, stuck, or repeated after a commit, worker crash, retry, redelivery, or uncertain API reply. For adoption in a project; not upstream disclosure, gigaverse-backend's internal harness, or ordinary unit-test debugging.
---

# Prove due work survives failure

Use this skill when a user asks why a background task vanished, why a worker repeated an effect, or whether a database-to-queue handoff, webhook, or retry is safe. The primary deliverable is an `ObligationContract` whose decorator generates standardized pytest tests from real application bindings; use the same fault-injection infrastructure for additional focused tests when the domain needs them. The effect may be a payment, order, receipt, email, file, cache purge, import checkpoint, or downstream message. Work through the local repository; this skill does not call a hosted service.

For an external open-source project that the user wants to probe or report upstream, use [probe-upstream-due-work](../probe-upstream-due-work/SKILL.md). Before installing this package or applying its contract, check for a repository-owned due-work harness or instructions. In gigaverse-backend, `.agents/skills/due-work/SKILL.md` and `docs/durable-work-conformance-harness.md` own the internal implementation and test policy; use those instead of this plugin's package-adoption workflow. Both harnesses now use A–J names, but their bindings and runtime ownership are not interchangeable.

## Find the obligation

1. Trace the user-visible operation through production code. Identify the durable fact that creates an obligation, each database or queue commit, the external effect, and the actual recovery path. Search for dispatch, callbacks, scheduled work, retries, acknowledgements, and cleanup by behavior and domain name. Do not assume a familiar framework makes the workflow safe.
2. State the invariant in observable terms: what should exist after normal completion, what must eventually happen after a crash, and what must not happen twice. Observe external effects independently of state that recovery may erase.
3. Inspect existing tests and the project's test environment. Run its relevant baseline before attributing a failure to the harness. Use a disposable test database, broker, or provider stub as appropriate to the user's authorized environment. Do not exercise payments, messages, or other real external effects in production merely to prove a history.

## Map and test

Inventory every production entry point for the same owner, including legacy
retry tasks, webhooks and narrow repairs. Separate producer coverage is not
composition coverage. Bind `ObligationContract.admission_overlaps` for cumulative
scopes and `settlement_interleavings` at observation/settlement checkpoints where
another path can commit product state before completing effects. Reuse
[lifecycle proofs](https://github.com/gigaverse-app/pytest-obligation/blob/main/package/docs/lifecycle-histories.md).
Supply production commands and independent effect observations; never implement
the scope union, settlement decision, or recovery loop in bindings. Verify a
lost-effect regression with unchanged expectations. Document unbound pairs and
checkpoints as outside coverage; A–J pass counts do not cover them implicitly.
Inventory every admitted input field before declaring it immutable. A fixed
owner/provider identity does not freeze the requested effect scope. Bind the
existing convergence and stale-snapshot families when that scope can expand;
do not use identity immutability to decline profile E for the whole operation.

4. Inspect the installed pytest-obligation version, its Python requirements, extras and public API before writing a contract. Current source uses `pytest_obligation.ObligationContract`; older adopters may use the compatibility namespace. Match documentation to the installed release, and do not silently substitute unreleased source for a published dependency. If installation is authorized, add only the development extras needed for the integration. Use [integration boundaries](references/integrations.md) to choose a supported adapter; identify missing boundaries rather than simulating production behavior in the test.
5. If the project has a `[tool.due-work-harness]` scan configuration, run `due-work-harness sites` and `due-work-harness in-transaction` with the project's environment. A scan result is a handoff candidate, not a bug. If configuration is absent, identify `production-packages` from the actual import roots before adding it. The scan covers specific Python handoff APIs; MongoDB writes, Prefect bodies, and Kafka offsets require their respective runtime bindings.
6. Build one small history for the real transition and real recovery. Inject at the supported commit, publication, callback, offset acknowledgement, or external-call boundary. Pair the interrupted history with normal operation and a control that would expose a missing or repeated effect. For process-level work, use the package's process histories where its worker or engine cannot be reached in-process.
7. For a complete adoption on the current A–J API, declare `ObligationContract` with truthful dispositions for all ten profiles. G covers gated execution, H harmless replay, I indivisible admission, and J job retry limits; E's convergence families need independent decisions. Use `NotAssessed(because=...)` for unfinished assessment rather than inventing a claim. Place histories in `handoffs=` or `process_handoffs=` and expose a collected `@due_work_contract_suite(CONTRACT)` class. The decorator generates standardized pytest cases at collection time; do not handwrite copies of those cases. Bind transition, selection, and recovery to production code. A standalone history or focused custom test is useful for a domain-specific risk, but does not replace the contract. For an older installed release, use its matching version of the [adoption guide](https://github.com/gigaverse-app/pytest-obligation/blob/v0.7.0/ADOPTING.md), not the `main` API. Check [current adoption guidance](https://github.com/gigaverse-app/pytest-obligation/blob/main/package/docs/adopting.md) and [green-result limits](https://github.com/gigaverse-app/pytest-obligation/blob/main/package/docs/what-a-green-result-means.md) before interpreting results.
8. Collect the generated cases, run them with `pytest --due-work-summary`, and use `--due-work-verify` for the completed coverage adoption. On an A–J version, use `--due-work-profile-report=profiles.json` for executed profile evidence and `--due-work-require-assessed` when assessment must be complete; XFAILs are not verified guarantees. Record the command, version, relevant environment, passing cases, declared gaps, unassessed profiles, and the specific divergent history. A failing history is a finding only after checking the binding and, for an upstream disclosure, independently reproducing the result against the project's own API.

## Keep recovery adoption small

Before treating a contract as evidence, use [contract validation](https://github.com/gigaverse-app/pytest-obligation/blob/main/package/docs/validating-contracts.md). Map each claim to an independent observation and a deliberate bad behavior the observation can distinguish. Run a passing baseline and that regression with unchanged expectations; require the intended failure. Observe per-identity effects and contradictory success/error events where aggregates could hide them. A pinned table, a reached fault, or an unchanged XFAIL alone does not establish coverage. Prefer owned disposable resources; never erase a default localhost database. Count declaration-only rows separately from executed proofs.

- Prefer the runtime's structured recovery registration over a handwritten loop. With Due, use `RecoveryStep.paged` and a product example (`make_pending`, `pending`); Due derives the fault seam and obligation owns the proof. Do not add another callback inventory in application tests.
- Profile A's existing sweep bindings generate the full-page poison history. Bind `resume_recovery` only when time must pass before a retry; it may advance eligibility, never perform the recovery transition. A green two-row isolation test does not establish fairness behind a poisoned first page.
- Required generated cases are checked automatically during broad collection, including removal of an entire generated method. A narrowed run is for debugging, not evidence that the complete contract passed. For an opaque native tick, state which per-identity seam is covered; do not claim that the harness discovered undisclosed inner stages.

## Report the result

Explain the concrete lost or repeated effect, the exact failure point, what production recovery did, and the smallest test that demonstrates it. If all executed histories pass, state which boundaries were exercised and which remain outside coverage. Keep static scan candidates, code-reading hypotheses, tested findings, and known gaps distinct.
