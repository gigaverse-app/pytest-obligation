# Retry waits enforced inside the production runner

The commission selector returns pending candidates; the real collector keeps a
fresh claim unchanged until its stale deadline. The persistent-retry proof had
classified candidate membership alone as a hot loop, before trying that guard.

Run the actual runner when a waiting identity remains selected. Require zero
new failure attempts, a non-terminal obligation and unchanged observable state.
After advancing only the wait, still require exactly one new failure attempt.
No new declaration fields, execution mode, retry policy or application changes.

## Controls and results

- Three new cases failed at the old membership assertion: a conforming candidate
  runner plus mutation/abandonment controls. The hot-loop counterfeit remains a
  failure in both versions.
- All 20 bounded/persistent-retry controls pass.
- Full core suite: 1302 passed, one existing optional skip.
- The real Shopify retry profile cases pass: 10 passed across the three billing
  contracts and the existing ingestion non-applicability declaration.
- Ruff, formatting and Pyrefly (zero errors) pass.

The application still has an open product-policy question about whether uncertain
pending sends should eventually require operator review. These tests describe
its current persistent retry behavior; they do not choose a new retry budget.
