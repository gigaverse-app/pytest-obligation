# Independent outcomes for process histories

The normal run and every recovered run must reach an independently declared product outcome; agreement alone can preserve the same application bug. Reuse the handoff outcome oracle, including explicit None and per-handle expectations. Preserve convergence-only callers, but expose a strict declaration check for application bindings.

First reproduce a consistent wrong outcome passing the process proof. Cover constants, callbacks, explicit None, missing declarations, and existing convergence/death controls. Run core tests and Django crash histories; CI also exercises downstream Due. No runtime behavior or fault protocol changes.

The new field without the verdict check reproduced three false passes (wrong constant, wrong callback and explicit None). The shared assertion rejects all three. Core: 954 passed, one optional skip; focused histories after the additional explicit-None positive control: 53 passed. Existing convergence-only declarations remain valid; Due opts into the strict declaration requirement.
