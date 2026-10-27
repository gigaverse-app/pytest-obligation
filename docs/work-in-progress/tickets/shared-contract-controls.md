# Shared contract controls and audits

- [x] Preserve binding setup/cleanup failures so diagnostic text cannot count them as detected regressions.
- [x] Declare configured regression controls through the shared contract generator, retaining production binding checks and reports.
- [x] Add a bounded-expiry exemption probe with independent early/late observations and omitted/extended-TTL negative controls.
- [x] Share repository-wide coverage/debt audits and compare reviewed baselines against a Git base revision.
- [x] Preserve production-bound declarations while migrating backend exemption and negative-control users.
- [x] Update agent guidance and documentation; validate core behavior, real PostgreSQL adopters, typing, package boundaries and CI.

Review evidence: Due #136 and backend #5579 document the cleanup assertion and exemption-baseline counterexamples. This work fixes those counterexamples in shared owners and removes the backend-specific workarounds.

Validation: 1,515 core tests passed, one skipped; the real PostgreSQL dependency
probe detected a removed index. After preserving AssertionError compatibility,
22 scope/declaration/decline controls and full type checking passed. All 25 CI
checks passed at `d107f089e62c2bb840f894153d62622ce93b6b45`. Backend #5581 also
verified the real publisher's omitted/excessive TTL and the proof-removal baseline
bypass, in addition to 168 passing adopter tests.
