# Atomic admission of distributed report evidence

[fixed.qnt](fixed.qnt) is a maintained bounded replay contract for the real `merge_reports()` API. [adapter.py](adapter.py) applies Quint-generated events to the current checkout's imported production implementation, reads actual evidence and derived verdicts, and compares that projection with **every** generated `observed` state. It does not implement a second Python merge model.

[audit.qnt](audit.qnt) remains the unchanged historical pre-fix audit model, pinned to source revision `389c5bb84f7ab186fa9c7815c2e15cb9332b67a4`, SHA-256 `1d2a1941bc98e48a0f0151e8490b7639c4fcf495dff15b93ce7c8c619b878375`. Its partial-promotion witness intentionally describes the old defect. It is historical evidence, not the passing contract for current code.

## Run model checks and real implementation replay

From the repository root, install Node.js as pinned in CI and the locked Python dependencies, then run:

```sh
uv sync --locked --all-packages --no-default-groups --extra debt --extra django --extra celery
uv run --no-sync python scripts/quint/replay.py --topic report-merge
```

The shared runner installs the exact Quint dependency from `scripts/quint/package-lock.json` with `npm ci` when needed, requires Quint **0.33.1**, typechecks the maintained model, checks its invariant and named scenarios, writes fresh ITF traces, then replays them. The CI job executes both model checks and replay, including semantic mutation controls. Missing tooling, missing topics/witnesses/traces, empty traces, unknown events, escaped imports, mismatches and surviving mutants fail the command. Existing traces are removed before generation so stale output cannot satisfy a generation check.

The checked-in [manifest](manifest.json) declares seed `20261107`, 150 bounded samples, 16 emitted sample traces, at most six API calls per sampled trace, plus five named witness traces. `.artifacts/quint/results.json` records the source head/hashes, imported production paths, covered actions, mutation mismatches and bounds. ITF files and command logs remain beside it, including on CI failure. A mismatch identifies the trace, state, event, expected projection and actual projection. To replay a saved trace against the current implementation:

```sh
uv run --no-sync python scripts/quint/replay.py --topic report-merge --replay .artifacts/quint/report-merge/sample-0.itf.json
```

`--replay` checks that trace directly; the default generate-and-replay command also enforces witness/action coverage and mutation sensitivity. No external application checkout or database service is needed.

## API and observation mapping

| Model event / observation | Actual implementation boundary |
| --- | --- |
| `init` | Construct real `SuiteCoverage`, `ProfileCoverage` and `CaseEvidence` fixtures. Two existing suites have one incomplete case and one completed case. |
| `merge` | Call `profiles.reporting.merge_reports(target, shard)` directly. The emitted location chooses one suite or an ordered shard containing an existing suite, a new suite and a later existing suite. |
| `reject` | Call the same API with the emitted family, debt, declaration, expected-case-set, source or assessment mismatch. Observe the actual `AssertionError` and subsequent target state. No validation guard is patched in positive replay. |
| `inspect` | Read real case outcomes/collection/selection, failure counts, exact eighth-second duration units, suite verdicts, and retained suite/case object references. Assertions emit this explicit read event instead of accidentally repeating the preceding mutating call. |
| `observed` | Phase report counts, sticky bad outcomes, collection/selection, diagnostic counts, new-suite admission, derived `.verified` and Python object identity. All are derived from real API results; expectations come from Quint. |

The model emits repeated compatible merges, late rejection before and after success, repeated incompatible shards, failed-then-passed evidence, and a completed attempt followed by an interrupted repeat. Rejection must preserve all observed evidence and existing object identities. A compatible merge accumulates reports without erasing earlier failures or missing phases.

Implementation: [merge API](../../../package/src/pytest_obligation/profiles/reporting.py), [evidence models](../../../package/src/pytest_obligation/profiles/coverage.py). The existing [Python regressions](../../../package/tests/core/test_profile_coverage.py) remain useful independent controls, but are not substitutes for generated trace replay.

## Repeatable sensitivity controls

The normal runner command replays the **same emitted traces** against both fixed code and these deliberate implementation mutants; only `ReplayMismatch` counts as detection. Import/setup exceptions do not count.

- `incremental-admission` compiles the current real `merge_reports` source with its commit loop moved inside preflight and new suites admitted immediately. This restores the old mutation-before-late-validation defect; target evidence/new-suite admission diverges from the emitted expected state.
- `replace-case-identity` is an explicit post-call output mutation: after the real compatible merge, replace a retained case by an equal deep copy. It tests whether observation checks retained object identity as well as values. This is not presented as original production source.

Mutants are scoped to replay resources and do not edit production files. The results artifact records their concrete mismatch and the emitted trace that rejected each one.

## Maintaining the contract

Changes to admission, compatibility checks, case evidence or identity behavior require reviewing this model, adapter, manifest, witnesses and CI input mapping in the **same change**. Explain any intended contract change and keep a discriminating old-source or implementation-mutant control. Do not silence a mismatch by dropping an observation, removing a witness/mutant, increasing a permissive bound, weakening an invariant, or accepting exceptions as detection. A deliberate weakening requires explicit rationale and maintainer review; update the contract openly instead of silently making CI green. Preserve `audit.qnt` as historical evidence.

All topic files are executable-contract inputs despite living under `docs/`; `.github/test-lanes.json` and the shared CI job must retain model/adapter/manifest/documentation/toolchain inputs as well as the mapped implementation sources. Shared runner and toolchain changes must run every registered topic.

## Limits

This contract covers two cases per suite, two existing suites and one optional new suite, six incompatibility shapes, and three phase-payload shapes in finite histories. Failure diagnostic **content**, arbitrary profile matrices, hostile Python object behavior, true xdist execution, threading and filesystem IO are outside the projection. The composer still explicitly warns about incompatible evidence; no formerly silent successful whole pytest run is claimed. Quint sampling and API-level projection are executable drift detection, not exhaustive verification, liveness proof or full-source refinement. Broader audit models without an adapter remain unconnected historical abstractions.

## Current-source effect proof

The [Python source contract](../../source-contracts/report-merge.md) now checks the
real merge AST in addition to this bounded API replay. Its conditional rejection
frame and structural mutation rules use explicit external model contracts; it
does not prove the concrete truth of compatibility predicates. The normal replay
therefore also includes four **actual source** mutants: an early evidence write,
a retained-case replacement, removed compatibility assertions and an omitted
commit. The last two prevent a vacuous conditional source theorem from satisfying
the complete lane. Their helper `scripts/source_contracts/mutations.py` is an
explicit input to both the Quint and source-contract lanes. All six mutations
must produce an observation mismatch on fresh traces. Historical `audit.qnt`
remains unchanged.
