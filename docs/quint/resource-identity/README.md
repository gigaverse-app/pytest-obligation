# Reference-provider identities survive deletion

[audit.qnt](audit.qnt) is the **unchanged historical audit model** (`resource_identity.qnt`) used to express and reproduce this report against [389c5bb](https://github.com/gigaverse-app/pytest-obligation/tree/389c5bb84f7ab186fa9c7815c2e15cb9332b67a4). Its unsafe behavior is intentional; it describes the pre-fix implementation. [fixed.qnt](fixed.qnt) is a separate model of this PR's decision boundary.

Historical model SHA-256: `53fd41e8f0701e9ffef12a2d464386651d86222759164aa9e368749ca3f707c8`.

The reported history is `init → create → create → deleteFirst → create`: `len(resources)+1` allocates identity 2 again and replaces a live resource.

## Source mapping

| Model transition / field | Implementation boundary |
| --- | --- |
| `create`, `resources` | `ResourceProvider.create` inserts a named resource in the live dictionary |
| Historical `resources.size() + 1` | The faulty allocator depends on current live-resource count |
| Fixed `creates + 1` | `_created` is a lifetime creation counter unaffected by deletion |
| `deleteFirst`, `deleteLast` | `ResourceProvider.delete` removes one live identity |
| `replacements`, `noLiveOverwrite` | Creating a new object must not replace an existing live identity |

Implementation evidence: [reference provider](../../../package/src/pytest_obligation/integrations/django/owed_references.py), [real-class regressions and generated recovery tests](../../../package/tests/django/automatic_recovery/test_external_owed_identities.py).

## Reproduce

Run from this directory with Node.js and npm available. Commands pin Quint **0.33.1** and use the TypeScript backend. `quint test` checks explicit histories; `quint run` samples bounded traces.

```sh
npx --yes @informalsystems/quint@0.33.1 typecheck audit.qnt
npx --yes @informalsystems/quint@0.33.1 typecheck fixed.qnt
npx --yes @informalsystems/quint@0.33.1 test audit.qnt --main resource_identity --match identityCollisionWitnessTest --max-samples 1 --seed 1 --backend typescript
npx --yes @informalsystems/quint@0.33.1 test fixed.qnt --main resource_identity_fixed --max-samples 1 --seed 1 --backend typescript
```

The historical witness test **passes when the old bug occurs**. To ask for the desired invariant instead, run:

```sh
npx --yes @informalsystems/quint@0.33.1 run audit.qnt --main resource_identity --invariant noLiveOverwrite --max-samples 1000 --max-steps 12 --seed 1 --backend typescript
```

This command is **expected to exit 1 with `Invariant violated`** and a counterexample. It is evidence of the pre-fix bug, not a required passing check for current code. The corresponding fixed check is:

```sh
npx --yes @informalsystems/quint@0.33.1 run fixed.qnt --main resource_identity_fixed --invariant noLiveOverwrite --max-samples 1000 --max-steps 12 --seed 1 --backend typescript
```

Executed with Quint 0.33.1: both files typechecked; the historical witness and fixed scenarios passed; the historical invariant produced its expected counterexample; the fixed invariant had no violation in 1,000 sampled traces of at most 12 steps (seed 1).

## Scope

The model uses integer identities, at most three creates, and deletions of identities 1 and 2. It represents an overwrite by membership rather than object values. Runtime regressions check actual surviving object identity, listing order and independent deletion. This is a shipped in-memory reference fake, not a claim about external provider or PostgreSQL persistence.

These are handwritten state-machine abstractions, **not runtime contracts or a proof that Python/YAML refines the model**. Bounded sampling is not exhaustive model checking or a liveness proof. The linked runtime regressions independently exercise the implementation boundary; the `.qnt` files are reviewable evidence, not part of the installed package or automatic PR CI.
