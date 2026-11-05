# Clear the accepted duplication backlog

Start from the 32 remaining accepted pairs. Consolidate shared policy into existing owners; retain independently
meaningful behavior with narrow, explained decisions. Preserve the baseline contract and record outcomes through
the sweep command. Do not weaken detection or replace the baseline.

## Verification plan

- [ ] Coverage discovery and reporting: preserve import resolution, scope traversal, transaction detection and
  production-site classification through the existing coverage/reporting tests. Add focused cases for any newly
  reconciled edge behavior before changing that behavior.
- [ ] Worker death and lost replies: preserve commit counts, callback clearing, failure identity and fencing
  through core crash-history tests and real PostgreSQL commit/connection tests.
- [ ] Selection and recovery: preserve ordered versus set identity semantics, gaps, poison isolation and actual
  queryset validation through profile tests and Django recovery tests.
- [ ] SQL parsing and table ownership: preserve matching-parenthesis rules and table teardown under failure;
  exercise existing plan, lock-order and reference-table tests against PostgreSQL.
- [ ] Redis/MongoDB reply boundaries: preserve backend-specific failure and restoration behavior; run the relevant
  real integration lanes if those implementations change.
- [ ] Metadata tests: preserve each CLI's independent rejection behavior while sharing genuinely repeated fixtures.
- [ ] Run Ruff, project type checking, source-consumer searches, and a complete strict sweep after consolidation.
- [ ] Ratchet to zero remaining accepted pairs, rerun for idempotence, and wait for current-head CI.

Each round must search again for the shared owner and its consumers. Reports and probe output stay outside Git;
the PR links the final evidence and distinguishes actual consolidation from deliberate exclusions.
