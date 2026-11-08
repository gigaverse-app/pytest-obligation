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

The historical witness and invariant commands reproduce the old defect. The current model-to-code bridge uses the exact witness names, seed and bounds declared in `manifest.json`; its recorded results and generated traces are retained as CI artifacts, separately from historical audit evidence.

## Scope

The fixed model bounds the baseline to two contracts and represents outcome families as events. It assumes the caller supplied every cost-test path; neither this model nor pytest can infer omitted paths or custom collection exclusions. Report transport, actual pytest hook ordering and worker crashes are checked by the runtime regressions. The historical audit file also contains the separate host-leak finding; only the baseline invariant/witness selected in the commands above belongs to this PR.

These are handwritten state-machine specifications. The maintained bridge checks generated traces against the production API projection; it does not instrument production execution or establish exhaustive refinement, arbitrary concurrency or liveness. The linked full-lifecycle regressions remain independent evidence. Model files and adapters are not part of the installed package.


## Maintained model-to-code replay

`fixed.qnt` emits ITF `event` and `observed` records. The [manifest](manifest.json)
maps actions to the [production-hook adapter](adapter.py) and declares witnesses,
source files, the immutable historical hash, bounds, planted bugs and the bug this
contract found. [pytest-quint-connect](https://github.com/gigaverse-app/pytest-quint-connect)
generates fresh traces and replays each through the adapter as its own pytest case
([guide](../README.md)):

```sh
uv run --no-sync pytest verification_tests/quint/test_cost_baseline_contract.py --quint-require-complete
```

The adapter compares actual persisted cost entries, visited report contracts and the
completed teardown count after every generated event. It unitizes real pytest
Config/Session, CollectReport/TestReport and CostCompleteness hooks. Existing
subprocess regressions retain full pytest lifecycle and real xdist crash coverage. It
does not infer excluded paths or verify actual SQL costs.

Planted bugs, each of which some generated history must catch:

- `shipped-389c5bb` runs [`sessionfinish-389c5bb.py.txt`](sessionfinish-389c5bb.py.txt),
  the pre-fix `pytest_sessionfinish` copied verbatim from `389c5bb` and pinned by SHA-256
  in `adapter.py`. The manifest's `bugs_found` entry names it, so every history is
  replayed through it and the report shows how many diverge. It replaces the earlier
  hand-written `unconditional-prune` control, which reproduced the same rule.
- `ignore-deselection` drops deselection tracking.
- `disable-retirement` stops legitimate retirement.

Historical `audit.qnt` is not the current replay oracle; modifying it fails its
recorded hash.
