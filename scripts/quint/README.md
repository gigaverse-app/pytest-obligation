# Maintained Quint contracts

From the repository root, with Node.js 24/npm and uv installed:

```sh
uv run --locked --all-packages --extra debt --extra django --extra celery python scripts/quint/replay.py
```

This discovers `docs/quint/*/manifest.json`, installs the integrity-locked npm
toolchain if absent, verifies Quint **0.33.1**, typechecks each current model,
generates ITF traces from every required named witness and deterministic bounded
simulation, and replays those exact traces against current-checkout production
APIs. Missing dependencies, topics, traces or action coverage fail the command.
It then replays the same traces through each declared semantic mutation and
requires an observed-state mismatch. Setup exceptions are failures, not evidence
that a mutation was detected. Adapters are not Python copies of the model.

`audit.qnt` is immutable historical evidence, verified against the manifest hash;
it describes the old bug and is never used as the current implementation oracle.
`fixed.qnt` is the maintained contract. Each ITF state contains an input `event`
record with `op` plus arguments, and an expected `observed` record. The adapter
applies each event to production APIs and independently reads the concrete state.
Assertions/stutters emit an explicit `inspect` event: equal events are never
silently deduplicated. The manifest maps each operation to its API/source owner,
declares bounds, mandatory witnesses, mutations, source inputs and assumptions.

Review implementation, model, manifest and adapter together when registered
behavior changes. Investigate mismatches; never automatically weaken the
specification, omit a failing witness or accept a mutation that survived. Retain
both a conforming positive history and a known-bad semantic control. Contracts
outside the discovered registry are not connected to this bridge.

Evidence is written under `.artifacts/quint`: complete generated ITF files,
generator logs, source-head and file hashes, imported production-module paths,
bounds/seed, mutation mismatch details and run status. Setup failures overwrite
stale green results. CI uploads this directory even on failure. Reproduce a
saved failure using its recorded source head and environment, for example:

```sh
uv run --locked --all-packages --extra debt --extra django --extra celery python scripts/quint/replay.py --topic TOPIC --replay PATH_TO_TRACE.itf.json
```

Replay-only results identify the source trace and do not claim fresh Quint
generation. To regenerate, use the first command; topic manifests pin seeds and
bounds. The bridge's own negative controls require freshly generated evidence:

```sh
uv run --no-sync python -m unittest discover -s scripts/quint -p test_replay.py -v
```

The selected `quint` CI lane runs generation/replay and these controls. Its inputs
explicitly include registered topic models, adapters, manifests and README files,
shared tool/config files and package implementation. Ordinary unrelated prose
does not select it. Planner failure executes the lane and the aggregate planning
gate still fails; missing Quint or empty traces can never become a skip/pass.

These are bounded API-level refinement checks for declared serial histories.
They do not establish exhaustive safety, liveness, arbitrary concurrency, service
scheduling or behavior outside the registered projections. Keep the existing real
pytest lifecycle/service regression suites alongside this bridge.
