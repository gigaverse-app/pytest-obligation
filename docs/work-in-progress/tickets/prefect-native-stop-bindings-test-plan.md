# Prefect native stop bindings

The AI recovery audit exposed two binding defects: an asyncio runner could retain
an older context instead of the current fault scope, and the generic stop signal
was an ordinary exception while Prefect cancellation derives from BaseException.
No application runtime or Due execution mode changes.

## Controls

- Initialize the runner before entering the host and poison scopes; the flow must
  receive the current host stop exception. Before the context fix it received an
  ordinary PoisonedIdentity instead.
- Run Prefect's actual zero-deadline asynchronous cancellation scope. The composed
  host must name the exception it raises and preserve the base host's capabilities.
- Run the same stop oracle against ordinary and asyncio cancellation exceptions.
  Passing, dropped, swallowed, grouped, continued and never-fired cases must retain
  their distinct verdicts. Unrelated KeyboardInterrupt/SystemExit must escape.
- Re-run the real Shopify recovery probe using the composed MongoDB/Prefect host;
  classify only failures remaining after the binding mismatch is removed.

## Validation

The new cancellation controls first failed (six host validation failures and two
missing-adapter failures). After the fix, 42 core poison and Prefect tests pass.
The context regression separately failed with PoisonedIdentity before its fix.
The full core, Prefect and MongoDB selection/write suites pass: 1351 passed and
one existing optional skip. Ruff, Pyrefly and documentation checks pass. The real
Shopify stop proof passes with the composed host; four unrelated recovery
guarantee failures remain visible (14 of 18 recovery probes pass).
