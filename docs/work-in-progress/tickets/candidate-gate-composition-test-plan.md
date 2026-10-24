# Candidate selection and execution-gate composition

The Shopify collector selects owed order candidates, then calls its canonical
subscription gate before making a billing claim or provider call. The A/G proof
previously required blocked work to be absent from the sweep's candidate read,
rejecting this layout before observing actual blocked behavior.

Reuse the existing blocked-gate proof against the contract sweep itself. After
activation, keep the existing selection membership and recorded-dispatch tie.
No new execution mode, declaration field, opt-out or application behavior.

## Evidence

- Five new controls failed before the fix: a conforming candidate loop and four
  distinct mutations were all rejected at the candidate membership check.
- All 75 eligibility controls now pass, including lost intent, hidden writes,
  rewritten intent, blocked execution, unrelated sweeps and bypassed dispatch.
- The generated Shopify suite now passes 225 cases with 12 explicit strict
  expected failures. Those retain actual recovery guarantee/policy gaps.
- A separate real-MongoDB 102-order probe spans two pages and produces 104
  provider effects for 104 transactions, preserving the distinct units.

The complete core suite passes: 1298 passed and one existing optional skip.
Ruff, Pyrefly (zero errors), documentation links and diff checks pass.
