# Scheduled selections in obligation reports

The static application inventory and runtime report omit scheduled-selection suites, hiding their existing strict failures from the sticky. Report their own narrow selection/loop scope without claiming full automatic recovery or changing runtime APIs.

- [x] Demonstrate omission using real generated pytest suites and static discovery without imports.
- [x] Preserve known-defect reasons/tickets, failed teardown, filtered cases, and explicit schedule-evidence exclusions.
- [x] Exercise serial and distributed reporting and render the normal sticky from the same evidence.
- [x] Run the backend's actual scheduled-selection suites and keep existing product bugs visible.
- [x] Run reporting regression tests, lint and types; publish a Conventional Commits PR.

## Evidence

- Before: serial and xdist generated suites pass four checks but write an empty report. Static discovery also omits both positional and keyword selection decorators.
- After: **109 reporting regression tests passed**, including 14 new positive/negative controls. Those controls exercise known defects/tickets, actual failures, failed teardown, filtering, absent schedule evidence and worker merging.
- Backend runtime reporting controls: **12 passed** against its vendored package.
- Real PostgreSQL adoption: **19 scheduled-selection suites, 479 passed and 19 xfailed**, with identical test outcomes before and after. The old report was `{}`; the new report has all 19 suites and all 19 known-defect cases with tickets.
- Existing defects: BE-1098 (10 cases), BE-1093 (5), BE-1096 (2), BE-1097 (1), BE-899 (1). No product behavior was changed or defect suppressed.
- Ruff and Pyrefly pass. Full automatic recovery is never inferred from this narrower scope.

## Executable exemptions

The AI shelf audit found the same omission for `exempt_due_work_suite`: both real TTL-loss probes passed but emitted an empty report. Include these as their own handoff-exemption scope, with the application's reason, actual outcome and no inferred A–J guarantees.

- Before: real shelf suite **22 passed, 3 xfailed**, with an empty profile report. The three existing expected failures are separately declared cache limitations/gaps, not generated exemption cases.
- After: the two existing TTL exemption probes pass against real Redis/MongoDB with the public reporter supplied through `PYTHONPATH`; both suites appear in JSON. No package pin, source or production behavior was changed in AI for this validation.
- **11 reporting controls** cover static discovery, serial/xdist passing and failing probes, failed cleanup, filtering, and a class carrying both a normal contract and an exemption. The original omission fails the new controls.
- The local Docker services exited during setup; restart of the owned Redis container restored the required service. Connection failures were environment failures, not product findings.
