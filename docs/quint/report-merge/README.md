# Atomic admission of distributed report evidence

[audit.qnt](audit.qnt) is the **unchanged historical audit model** (`report_merge_atomicity.qnt`) used to express and reproduce this report against [389c5bb](https://github.com/gigaverse-app/pytest-obligation/tree/389c5bb84f7ab186fa9c7815c2e15cb9332b67a4). Its unsafe behavior is intentional; it describes the pre-fix implementation. [fixed.qnt](fixed.qnt) is a separate model of this PR's decision boundary.

Historical model SHA-256: `1d2a1941bc98e48a0f0151e8490b7639c4fcf495dff15b93ce7c8c619b878375`.

The reported history is `init → validateSuite → mergeFirst → rejectSecond`: a rejected shard has already promoted the first case. `composeCatches` adds an unavailable warning but retains that mutation.

## Source mapping

| Model transition / field | Implementation boundary |
| --- | --- |
| `validateSuite` | Suite/profile declaration and expected-case agreement checks |
| `stageCandidates` | Local `pairs` and `additions` collect prospective changes without mutating target evidence |
| `rejectLaterMismatch` | A later source/profile/case/debt/family/declaration assertion rejects the shard |
| `commitCompatibleShard` | `target.update(additions)` and the evidence mutation loop run only after all validation |
| `composeCatches`, `unavailable` | `reporting.compose.merge_evidence` catches rejection and explains unavailable evidence |

Implementation evidence: [merge implementation](../../../package/src/pytest_obligation/profiles/reporting.py), [composer](../../../package/src/pytest_obligation/reporting/compose.py), [runtime regressions and controls](../../../package/tests/core/test_profile_coverage.py).

## Reproduce

Run from this directory with Node.js and npm available. Commands pin Quint **0.33.1** and use the TypeScript backend. `quint test` checks explicit histories; `quint run` samples bounded traces.

```sh
npx --yes @informalsystems/quint@0.33.1 typecheck audit.qnt
npx --yes @informalsystems/quint@0.33.1 typecheck fixed.qnt
npx --yes @informalsystems/quint@0.33.1 test audit.qnt --main report_merge_atomicity --match partialPromotionWitnessTest --max-samples 1 --seed 1 --backend typescript
npx --yes @informalsystems/quint@0.33.1 test fixed.qnt --main report_merge_fixed --max-samples 1 --seed 1 --backend typescript
```

The historical witness test **passes when the old bug occurs**. To ask for the desired invariant instead, run:

```sh
npx --yes @informalsystems/quint@0.33.1 run audit.qnt --main report_merge_atomicity --invariant rejectedShardAtomic --max-samples 1000 --max-steps 12 --seed 1 --backend typescript
```

This command is **expected to exit 1 with `Invariant violated`** and a counterexample. It is evidence of the pre-fix bug, not a required passing check for current code. The corresponding fixed check is:

```sh
npx --yes @informalsystems/quint@0.33.1 run fixed.qnt --main report_merge_fixed --invariant rejectedShardAtomic --max-samples 1000 --max-steps 12 --seed 1 --backend typescript
```

Executed with Quint 0.33.1: both files typechecked; the historical witness and fixed scenarios passed; the historical invariant produced its expected counterexample; the fixed invariant had no violation in 1,000 sampled traces of at most 12 steps (seed 1).

## Scope

The model has two case-verdict booleans and one possible new suite; metadata incompatibility is an event, not a reimplementation of every Pydantic field. It assumes the current validation assertions identify incompatibility. Runtime tests exercise actual late family/debt/declaration/case-set/source mismatches within and across suites. The existing unavailable warning is modeled explicitly: this finding does not claim a previously silent successful whole report or xdist run.

These are handwritten state-machine abstractions, **not runtime contracts or a proof that Python/YAML refines the model**. Bounded sampling is not exhaustive model checking or a liveness proof. The linked runtime regressions independently exercise the implementation boundary; the `.qnt` files are reviewable evidence, not part of the installed package or automatic PR CI.
