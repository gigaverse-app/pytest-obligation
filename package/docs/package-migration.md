# Moving to pytest-obligation

New code uses the canonical package and contract:

```python
from pytest_obligation import ObligationContract, due_work_contract_suite
from pytest_obligation.integrations.django import django_host
```

Existing code continues to work without an import migration:

```python
from due_work_harness import DueWorkContract, due_work_contract_suite
from due_work_harness.integrations.django import django_host
```

`DueWorkContract` is an alias of `ObligationContract`, not a subclass or a second
model. `DueWorkContractDesignError` similarly aliases
`ObligationContractDesignError`. The contract fields, validation, decorators,
generated A–J tests, and framework bindings are unchanged.

## Compatibility boundary

All implementation lives in `src/pytest_obligation`. The old namespace lives
in `shims/due_work_harness`, with lazy module forwarding and typing stubs.
Old submodule imports resolve to the canonical module objects, sharing host
contexts, registries, class identity, and monkeypatches. Framework adapters
remain optional: importing either root package does not load them eagerly.
Historical pickle class paths resolve through the shim as well.

Static coverage scans accept both declaration namespaces and both contract
names without importing an application's tests. Existing pytest flags,
`due_work_harness_host`, `due_work` markers, `[tool.due-work-harness]` settings,
and the `due-work-harness` console command remain supported. The pytest entry
point retains its `due_work_harness` registration name, but loads
`pytest_obligation.pytest_plugin`; this avoids registering hooks twice and
preserves `-p due_work_harness` / `-p no:due_work_harness` behavior.

## Package-manager migration

Replace the `due-work-harness` dependency with
`pytest-obligation`, retaining the same extras. Remove the old distribution
before installing the new one: both provide the old namespace and must not be
installed together. Keep the prior release's adoption guide if remaining on
an older version; the new import and contract names are not available there.

## Migrating an existing declaration

This version requires Pydantic 2.11 or newer; the minimum is exercised in CI.
The canonical names and enum values now follow the A–J vocabulary in the
[profile table](how-it-works.md#the-a-j-guarantees). This is an API migration:

- Move nested `safety.profiles` into `ObligationContract.profiles`: old
  `SafetyProfile.REPLAY_SAFE_EXECUTION` becomes `Profile.HARMLESS_REPLAY` (H),
  and `SafetyProfile.BOUNDED_RETRY` becomes `Profile.JOB_RETRY_LIMITS` (J).
  Move `replay=` and `retry=` onto the same `ObligationContract`, preserving their
  fixtures, real-commit requirement and legacy gap policy.
- Add G and I decisions. Claim G when binding `eligibility=`; claim I when binding
  named `admission=` commands. Use `NotAssessed(because="...")` when assessment
  is unfinished. It produces a strict XFAIL until replaced with evidence or an
  applicability decision. Existing H/J test IDs remain stable.
- `SafetyContract` remains a standalone H/J-only view for independently scoped
  effects, using `Profile.H` and `Profile.J`. It is no longer nested in a domain
  contract. The implementations live in `profiles.harmless_replay` and
  `profiles.job_retry_limits`; G lives in `profiles.gated_execution`.
- E's four families are independently assessed. Existing bindings imply a claim
  for their own family only. Unbound families generate assessment XFAILs; declare
  `convergence_families={ConvergenceFamily.IN_FLIGHT: NotApplicable("reason")}`
  only when that family truly cannot apply. Exact behavioral failures belong in
  `Claim.gaps` or the scenario's history/invariant gaps, not blanket family waivers.

`pytest --due-work-profile-report=profiles.json` records every expected behavioral
case, which cases were collected and selected, and their setup/call/teardown
outcomes. It supports xdist and never treats an XFAIL as a verified guarantee.
This complements the static handoff scan and `--due-work-verify`; neither a
collected declaration nor one passing test certifies a whole profile.

See [interleavings](interleavings.md) for generated competing-event tests,
optional exploration and deterministic replay. Profile I's callbacks are documented
in [`indivisible_admission.py`](../src/pytest_obligation/profiles/indivisible_admission.py):
bind a real standalone command, independently observed product intent and work,
an external-publication recorder, and a fault boundary reached after partial writes.
The host must supply `in_transaction`; fault fixtures must not supply the transaction.
