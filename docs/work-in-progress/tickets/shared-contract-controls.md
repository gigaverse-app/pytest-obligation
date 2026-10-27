# Shared contract controls and audits

- [ ] Preserve binding setup/cleanup failures so diagnostic text cannot count them as detected regressions.
- [ ] Declare configured regression controls through the shared contract generator, retaining production binding checks and reports.
- [ ] Add a bounded-expiry exemption probe with independent early/late observations and omitted/extended-TTL negative controls.
- [ ] Share repository-wide coverage/debt audits and compare reviewed baselines against a Git base revision.
- [ ] Preserve production-bound declarations while migrating backend exemption and negative-control users.
- [ ] Update agent guidance and documentation; validate core behavior, real PostgreSQL adopters, typing, package boundaries and CI.

Review evidence: Due #136 and backend #5579 document the cleanup assertion and exemption-baseline counterexamples. This work fixes those counterexamples in shared owners and removes the backend-specific workarounds.
