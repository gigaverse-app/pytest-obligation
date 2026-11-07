# Cost-baseline retirement after incomplete execution

[audit.qnt](audit.qnt) is the **unchanged historical audit model** (`session_persistence.qnt`) used to express and reproduce this report against [389c5bb](https://github.com/gigaverse-app/pytest-obligation/tree/389c5bb84f7ab186fa9c7815c2e15cb9332b67a4). Its unsafe behavior is intentional; it describes the pre-fix implementation. [fixed.qnt](fixed.qnt) is a separate model of this PR's decision boundary.

Historical model SHA-256: `64bc901c721adc767ad27fabddd39d843bfeb8b8fbcb8a5fa637f32ee8f0dd54`.

The reported history is `init → collectionError → finishUpdate`: no test measures `required`, and update mode deletes it.

## Source mapping

| Model transition / field | Implementation boundary |
| --- | --- |
| `collectionError`, `skipOrDeselect`, `testFailure` | `CostCompleteness.pytest_collectreport`, `pytest_deselected`, `pytest_runtest_logreport` record incomplete execution |
| `collectOnly`, `distributedRun` | Configuration excludes collection-only and xdist update pruning |
| `collected`, `finished`, `status` | Session test count, teardown reports and final exit status |
| `finishUpdate`, `completeEvidence` | `CostCompleteness.pytest_sessionfinish` gates `prune_cost_entries` |
| `completeRun`, `emptyCollection` | Legitimate retirement, including the final contract |

Implementation evidence: [implementation](../../../package/src/pytest_obligation/_cost_plugin.py), [runtime regressions](../../../package/tests/core/test_costs.py), [semantics](../../../package/docs/cost-contracts.md).

## Reproduce

Run from this directory with Node.js and npm available. Commands pin Quint **0.33.1** and use the TypeScript backend. `quint test` checks explicit histories; `quint run` samples bounded traces.

```sh
npx --yes @informalsystems/quint@0.33.1 typecheck audit.qnt
npx --yes @informalsystems/quint@0.33.1 typecheck fixed.qnt
npx --yes @informalsystems/quint@0.33.1 test audit.qnt --main session_persistence --match baselineDeletionWitnessTest --max-samples 1 --seed 1 --backend typescript
npx --yes @informalsystems/quint@0.33.1 test fixed.qnt --main cost_baseline_fixed --max-samples 1 --seed 1 --backend typescript
```

The historical witness test **passes when the old bug occurs**. To ask for the desired invariant instead, run:

```sh
npx --yes @informalsystems/quint@0.33.1 run audit.qnt --main session_persistence --invariant failedCollectionPreservesBaseline --max-samples 1000 --max-steps 12 --seed 1 --backend typescript
```

This command is **expected to exit 1 with `Invariant violated`** and a counterexample. It is evidence of the pre-fix bug, not a required passing check for current code. The corresponding fixed check is:

```sh
npx --yes @informalsystems/quint@0.33.1 run fixed.qnt --main cost_baseline_fixed --invariant incompletePreservesBaseline --max-samples 1000 --max-steps 12 --seed 1 --backend typescript
```

Executed with Quint 0.33.1: both files typechecked; the historical witness and fixed scenarios passed; the historical invariant produced its expected counterexample; the fixed invariant had no violation in 1,000 sampled traces of at most 12 steps (seed 1).

## Scope

The fixed model bounds the baseline to two contracts and represents outcome families as events. It assumes the caller supplied every cost-test path; neither this model nor pytest can infer omitted paths or custom collection exclusions. Report transport, actual pytest hook ordering and worker crashes are checked by the runtime regressions. The historical audit file also contains the separate host-leak finding; only the baseline invariant/witness selected in the commands above belongs to this PR.

These are handwritten state-machine abstractions, **not runtime contracts or a proof that Python/YAML refines the model**. Bounded sampling is not exhaustive model checking or a liveness proof. The linked runtime regressions independently exercise the implementation boundary; the `.qnt` files are reviewable evidence, not part of the installed package.


## Maintained model-to-code replay

`fixed.qnt` now emits ITF `event` and `observed` records. The registered
[manifest](manifest.json) maps actions to the [production-hook adapter](adapter.py)
and declares witness coverage, source files, immutable historical hash, bounds
and known-bad controls. The selected CI lane generates these traces and replays
them against the current checkout; it does not run a Python clone of the model.

Run the [one-command bridge](../../../scripts/quint/README.md) from the repository
root. Baseline projection compares actual persisted cost entries, visited report
contracts and completed teardown count after every generated event. The bridge
unitizes real pytest Config/Session, CollectReport/TestReport and CostCompleteness
hooks. Existing subprocess regressions retain full pytest lifecycle and real
xdist crash coverage. It does not infer excluded paths or verify actual SQL costs.

The same generated traces must detect unconditional historical-style pruning,
omitted deselection tracking, and disabled legitimate retirement. Artifacts retain
seed, bounds, exact trace, source/tool hashes and mismatch observations. Historical
`audit.qnt` is not the current replay oracle; modifying it fails its recorded hash.
