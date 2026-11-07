# Application host ownership across pytest sessions

[audit.qnt](audit.qnt) is the **unchanged historical audit model** (`session_persistence.qnt`) used to express and reproduce this report against [389c5bb](https://github.com/gigaverse-app/pytest-obligation/tree/389c5bb84f7ab186fa9c7815c2e15cb9332b67a4). Its unsafe behavior is intentional; it describes the pre-fix implementation. [fixed.qnt](fixed.qnt) is a separate model of this PR's decision boundary.

Historical model SHA-256: `64bc901c721adc767ad27fabddd39d843bfeb8b8fbcb8a5fa637f32ee8f0dd54`.

The reported history is `init → configureA → nextSession`: session B has no host setting but still observes A.

## Source mapping

| Model transition / field | Implementation boundary |
| --- | --- |
| `configureA`, `previous` | Ini host installation through `pytest_configure` and `hosted()` snapshots the prior raw state |
| `nextSession` | `config.add_cleanup` closes the host scope after success or collection failure |
| `host`, `configured` | Global host/factory ownership rather than framework behavior |
| `manualSessionWithoutIni` | No ini host means deliberate manual configuration remains in effect |

Implementation evidence: [plugin](../../../package/src/pytest_obligation/pytest_plugin.py), [host scope](../../../package/src/pytest_obligation/host.py), [repeated-session regressions](../../../package/tests/core/test_host_initialization.py).

## Reproduce

Run from this directory with Node.js and npm available. Commands pin Quint **0.33.1** and use the TypeScript backend. `quint test` checks explicit histories; `quint run` samples bounded traces.

```sh
npx --yes @informalsystems/quint@0.33.1 typecheck audit.qnt
npx --yes @informalsystems/quint@0.33.1 typecheck fixed.qnt
npx --yes @informalsystems/quint@0.33.1 test audit.qnt --main session_persistence --match leakedHostWitnessTest --max-samples 1 --seed 1 --backend typescript
npx --yes @informalsystems/quint@0.33.1 test fixed.qnt --main session_host_fixed --max-samples 1 --seed 1 --backend typescript
```

The historical witness test **passes when the old bug occurs**. To ask for the desired invariant instead, run:

```sh
npx --yes @informalsystems/quint@0.33.1 run audit.qnt --main session_persistence --invariant sessionIsolated --max-samples 1000 --max-steps 12 --seed 1 --backend typescript
```

This command is **expected to exit 1 with `Invariant violated`** and a counterexample. It is evidence of the pre-fix bug, not a required passing check for current code. The corresponding fixed check is:

```sh
npx --yes @informalsystems/quint@0.33.1 run fixed.qnt --main session_host_fixed --invariant sessionIsolated --max-samples 1000 --max-steps 12 --seed 1 --backend typescript
```

Executed with Quint 0.33.1: both files typechecked; the historical witness and fixed scenarios passed; the historical invariant produced its expected counterexample; the fixed invariant had no violation in 1,000 sampled traces of at most 12 steps (seed 1).

## Scope

The fixed model represents a prior host or factory by an opaque identity (`manual`) and two sessions; it does not execute imports, lazy factories or pytest cleanup. Runtime regressions establish exact object restoration, absence of eager factory resolution, and cleanup after collection failure. Direct manual configure calls remain process-wide. The historical audit file also contains the separate baseline-deletion finding; only the host invariant/witness selected in the commands above belongs to this PR.

These are handwritten state-machine abstractions, **not runtime contracts or a proof that Python/YAML refines the model**. Bounded sampling is not exhaustive model checking or a liveness proof. The linked runtime regressions independently exercise the implementation boundary; the `.qnt` files are reviewable evidence, not part of the installed package.


## Maintained model-to-code replay

The current `fixed.qnt` exports ITF `event` and `observed` records. Its registered
[manifest](manifest.json) maps operations to the [production adapter](adapter.py),
pins witness/bounded generation and semantic controls, and protects historical
`audit.qnt` with its original hash. CI now replays the generated events against
real pytest configuration/cleanup and host APIs in the current checkout.

Run the [one-command bridge](../../../scripts/quint/README.md) from the repository
root. The independent projection reads the raw host identity and actual manual
and application factory counters after every event. Host resolution is an
explicit `current_host()` event; observing through that API would itself change
lazy state. Inputs cover manual hosts and unresolved factories, used/unused ini
hosts, cleanup and a following configuration without host settings. The bridge
must reject omitted restoration and eager previous-factory resolution using the
same generated traces.

The adapter unitizes `Config._do_configure` / `_ensure_unconfigure` and host APIs;
it does not collect full test sessions. Existing `pytest.main()` regressions
retain full lifecycle and collection-failure coverage. These serial bounded
histories do not cover arbitrary nested or concurrent embedded sessions. Review
implementation, model, adapter and manifest together; do not weaken a mismatch.
