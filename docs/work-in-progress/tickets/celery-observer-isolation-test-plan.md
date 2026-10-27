# Contract evidence and resource ownership

- [x] Disposable Redis uses a fresh process and removes it after a failed test; another server's sentinel survives.
- [x] A missing or failed server startup never connects to a default Redis.
- [x] Regression controls accept a passing baseline, reject a blind detector, and propagate setup, teardown and unrelated failures.
- [x] Declaration-only cases remain visible without counting as behavioral passes; executable decline proofs still run.
- [x] History summaries expose each fault's observed status without changing pinned findings or xfail semantics.
- [x] Real Celery worker histories observe header errors, and targeted upstream regressions change the pinned observations.
- [x] Run affected core and Redis suites, lint, types, skill validation, and CI; document exact scope and results in the PR.

Local validation: 1,489 core tests passed (9 optional skips); 438 Redis/RQ/Celery tests passed, 10 known xfails, 85 declarations; both pinned upstream reversions detected. CI routing, changed-file types, lint, framework-free imports, documentation links and skill validation passed. GitHub CI results are recorded on the PR.
