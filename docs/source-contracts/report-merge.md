# Current-source report merge contracts

`merge_reports` remains the production implementation in
[`reporting.py`](../../package/src/pytest_obligation/profiles/reporting.py).
Its public API, two-pass algorithm, retained suite/case identities and compatible
merge semantics are unchanged. Its `#@ verified` enrollment and explicit
`# heap-schema` comments feed the reviewed `dafny-heap` compiler. The only other
production edit supplies the existing pytest hook's missing generic type argument.

From the repository root, install uv, Node.js 24, and the reviewed toolchain:

```sh
uv sync --all-packages --locked --no-default-groups --extra debt --group xdist
.venv/bin/python scripts/bootstrap_source_verifier.py
bash tooling/source-contracts/install-dafny.sh
export PATH="$PWD/.source-contract-tooling/dafny:$PATH"
.venv/bin/python -m scripts.source_contracts.check
```

The bootstrap fetches the exact public upstream commit in
[`verifier.json`](../../tooling/source-contracts/verifier.json), applies the
committed reviewed patch and installs its hash-locked dependencies. It compares
the installed compiler's Python source tree with the reviewed tree. No model API,
secret or remote write is used. The Dafny installer verifies the pinned 4.11.0
archive checksum. Quint's existing runner installs integrity-locked 0.33.1.

The check command requires all three forms of evidence:

1. `veripy project check veripy-project.json --json` checks fixed source
   enrollment, source/dependency/sidecar freshness, the type gate and real Dafny.
2. Twelve explicitly enrolled tests execute the current Pydantic API, check
   rejection against independent snapshots, check retained suite/profile/case
   and evidence-container references, and reject real source mutations through
   Dafny. Missing, deselected, skipped or failed tests fail the command.
3. The registered Quint report contract generates and replays 21 fresh traces
   through current production code. All six mutation controls must produce a
   semantic observation mismatch. Import/setup failures do not count as detection.

`.artifacts/source-contracts/results.json`, runtime XML, exact positive/mutated Python and generated Dafny plus full backend
output under `.artifacts/source-contracts/backend`,
project artifacts and `.artifacts/quint-connect` retain outcomes and source hashes. A
failed command overwrites a previous green receipt. CI uploads them on failure.
The `source_contracts` lane declares source, dependencies, sidecar, compiler
patch/lock/bootstrap, enrollment, runtime inventory, model and adapter inputs;
selector failure runs it and fails the aggregate planning gate.

## What the source proof establishes

This is a conservative **structural effect proof** of the actual function AST.
It does not replace the merge with a handwritten state-machine summary. The
lowering traverses every admitted statement, propagates local bindings and
container aliases in its provenance analysis, and retains branch, loop,
assertion and explicit validation-exception exit structure in the generated
program. Fresh staging mutations are analyzed without adding borrowed-write
events. Metadata predicates are nondeterministic, so both
outcomes are checked regardless of their concrete business values. Each borrowed
mutation appends its source location to a trace. Real Dafny proves that every
modeled rejection exit has an empty write trace. Loop invariants preserve either
an unchanged trace or its entry prefix; no finite iteration bound is imposed.
The theorem is partial correctness for finite executions.

The compiler also requires every admitted write to satisfy its structural effect
rules: boolean OR, list append/extend, empty-list `setdefault`, or dictionary
admission whose keys were staged under an absence guard for that exact borrowed
map. Those rules preserve existing object references, list prefixes and true
boolean evidence under the builtin/type contracts below. This is a checked
effect discipline; no quantified theorem about all Pydantic implementation
internals is claimed. Pair lists and map/list wrappers retain borrowed provenance;
loop-carried aliases are joined to a fixed point. Key rebinding, including an
annotated assignment, kills the corresponding absence guard. Updates to fresh
containers propagate inserted aliases and key capabilities. Unknown effects,
helpers, comprehensions, exception handlers and unsupported syntax fail closed.
Strict zip failures remain possible during and after iteration and after an
iterator-consuming extend. Potential dictionary iterator invalidation remains a
post-write exceptional exit; an unchanged current iterator key permits safe
setdefault even when borrowed maps alias. Exception causes and nested format
specifications are visited for effects;
formatting opaque metadata is rejected. Shadowed builtins are rejected.

The rejection theorem covers `AssertionError`, explicit admitted validation
exceptions and the conservatively modeled dictionary/strict-zip/nullable-read
failures and modeled dictionary-iterator invalidation. It does **not** claim rollback for `MemoryError`, asynchronous
interruption, interpreter failure or concurrent mutation during commit. Those
exceptions are excluded explicitly; the API is not a transaction for arbitrary
Python failures. The proof is conditional on rejection: removing all guards or
returning without accumulating evidence can satisfy that theorem. Mandatory real
API replay therefore also checks incompatibility rejection and successful
accumulation, with guard-removal and omitted-commit controls.

## Trusted external contracts

Inputs have the declared passive Pydantic model shapes, ordinary builtin
containers and primitive keys/evidence. Schema `opaque` metadata supports passive
reads and pure comparison; it is not asserted to be a concrete string. Optional
exploration dictionaries are represented explicitly. `case_groups()` is an
external pure iterator yielding borrowed additional/profile case dictionaries.
A native contract test checks those exact returned references and absence of
observable mutation; dependency hashes bind the proof to `coverage.py`,
`models.py`, `debt.py` and `failures.py`.

Reads, equality, iteration and allowed builtin writes have their ordinary
semantics, without hostile descriptors, monkeypatching, reentrancy or concurrent
changes. The compiler and these external semantic contracts are trusted. This is
not a mechanized proof of CPython, Pydantic, xdist collection or arbitrary user
objects. The real Pydantic histories and existing full pytest tests are retained
alongside the source proof.

## Update and review

After an intentional source/dependency/contract edit:

```sh
.venv/bin/python -m scripts.source_contracts.check --generate
```

Generation proves before replacing artifacts and preserves checked proof additions
in [`reporting.proofs.dfy`](../../package/src/pytest_obligation/profiles/reporting.proofs.dfy).
Review the generated source map, write effects, external contracts, source hashes
and complete logs. Enrollment changes require the project's explicit
`--update-enrollment` workflow. A reviewed contract or governing type-checker
configuration change requires `--update-contracts`; this is separate from
source-only regeneration. Do not regenerate enrollment merely to remove a
failing target. Missing/zero targets and stale outputs must fail. Keep runtime
inventory changes reviewable and retain every semantic control.

Review the maintained [Quint guide](../quint/report-merge/README.md), model,
adapter and action mapping together. `audit.qnt` remains immutable historical
evidence; its SHA-256 stays checked by the existing registry. A compiler or
external contract change requires rerunning the complete source lane and generic
backend tests, including all retained root-discovered regressions. No surviving
mutant, unsupported required target, omitted observation or weakened invariant
can be reported as verified.

For another passive batch API, begin with the [onboarding example](onboarding.md).
