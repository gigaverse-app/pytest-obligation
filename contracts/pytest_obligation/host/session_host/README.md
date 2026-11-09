# Application host ownership across pytest sessions

[history/audit.qnt](history/audit.qnt) is the **unchanged historical audit model** (`session_persistence.qnt`) used to express and reproduce this report against [389c5bb](https://github.com/gigaverse-app/pytest-obligation/tree/389c5bb84f7ab186fa9c7815c2e15cb9332b67a4). Its unsafe behavior is intentional; it describes the pre-fix implementation. [model.qnt](model.qnt) is a separate model of this PR's decision boundary.

Historical model SHA-256: `64bc901c721adc767ad27fabddd39d843bfeb8b8fbcb8a5fa637f32ee8f0dd54`.

The reported history is `init → configureA → nextSession`: session B has no host setting but still observes A.

## Source mapping

| Model transition / field | Implementation boundary |
| --- | --- |
| `configureA`, `previous` | Ini host installation through `pytest_configure` and `hosted()` snapshots the prior raw state |
| `nextSession` | `config.add_cleanup` closes the host scope after success or collection failure |
| `host`, `configured` | Global host/factory ownership rather than framework behavior |
| `manualSessionWithoutIni` | No ini host means deliberate manual configuration remains in effect |

Implementation evidence: [plugin](../../../../package/src/pytest_obligation/pytest_plugin.py), [host scope](../../../../package/src/pytest_obligation/host.py), [repeated-session regressions](../../../../package/tests/core/test_host_initialization.py).

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
npx --yes @informalsystems/quint@0.33.1 run fixed.qnt --main session_host_fixed --invariant maintained --max-samples 1000 --max-steps 12 --seed 1 --backend typescript
```

The historical witness and invariant commands reproduce the old defect. The current model-to-code bridge uses the exact witness names, seed and bounds declared in `quint-connect.json`; its recorded results and generated traces are retained as CI artifacts, separately from historical audit evidence.

## Scope

The fixed model represents a prior host or factory by an opaque identity (`manual`) and two sessions; it does not execute imports, lazy factories or pytest cleanup. Runtime regressions establish exact object restoration, absence of eager factory resolution, and cleanup after collection failure. Direct manual configure calls remain process-wide. The historical audit file also contains the separate baseline-deletion finding; only the host invariant/witness selected in the commands above belongs to this PR.

These are handwritten state-machine specifications. The maintained bridge checks generated traces against the production API projection; it does not instrument production execution or establish exhaustive refinement, arbitrary concurrency or liveness. The linked full-lifecycle regressions remain independent evidence. Model files and adapters are not part of the installed package.


## Maintained model-to-code replay

The current `model.qnt` exports ITF `event` and `observed` records. Its registered
[manifest](quint-connect.json) maps operations to the [production adapter](session_host_adapter.py),
pins witness/bounded generation and semantic controls, and protects historical
`audit.qnt` with its original hash. CI now replays the generated events against
real pytest configuration/cleanup and host APIs in the current checkout.

[pytest-quint-connect](https://github.com/gigaverse-app/pytest-quint-connect) generates
fresh traces and replays each through the adapter as its own pytest case
([guide](../../../README.md)):

```sh
uv run --no-sync pytest -c contracts/quint.ini contracts/pytest_obligation/host/session_host
```

The independent projection reads the raw host identity and actual manual
and application factory counters after every event. Host resolution is an
explicit `current_host()` event; observing through that API would itself change
lazy state. Inputs cover manual hosts and unresolved factories, used/unused ini
hosts, cleanup and a following configuration without host settings. The same
generated traces must catch two planted bugs:

- `shipped-389c5bb` runs [`history/pytest_configure-389c5bb.py.txt`](history/pytest_configure-389c5bb.py.txt),
  the pre-fix `pytest_configure` copied verbatim from `389c5bb` and pinned by SHA-256 in
  `session_host_adapter.py`. The manifest's `bugs_found` entry names it, so every history is replayed
  through it and the report shows how many diverge. It replaces the earlier hand-written
  `omit-host-restoration` control, which reproduced the same behavior.
- `eager-previous-resolution` resolves the previous lazy factory while scoping.

The adapter sets `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` for its inner sessions, which load
the plugin with `-p`; the old runner set it process-wide.

The adapter unitizes `Config._do_configure` / `_ensure_unconfigure` and host APIs;
it does not collect full test sessions. Existing `pytest.main()` regressions
retain full lifecycle and collection-failure coverage. These serial bounded
histories do not cover arbitrary nested or concurrent embedded sessions. Review
implementation, model, adapter and manifest together; do not weaken a mismatch.
