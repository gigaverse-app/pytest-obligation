# Contract summary and recovery diagnostics

- [x] Baseline: profile evidence, legacy terminal summary and recovery history controls (25 passed).
- [x] Terminal summary: actual pytest runs, serial and xdist, with and without JSON.
- [x] Positive control: every claimed proof completes; explicit inapplicability stays visible.
- [x] Negative controls: filtering, explicit node selection, missing assessment, known gaps, teardown failure, failed extras and interrupted evidence never become verified.
- [x] Recovery: conforming histories still pass; starvation, dropped work, unused seams and abandonment retain their failure types and gain candidate evidence.
- [x] Diagnostic callbacks run outside injected faults; callback failure preserves the original error; successful histories do not invoke diagnostic callbacks.
- [x] Full core tests: 1,125 passed, one skipped. Final targeted run: 46 passed, including two tests added after the full run.
- [x] Framework-free import check: 76 core modules imported; lint, formatting, documentation links and full type checking passed.

The PR records the actual terminal output and validation commands. Publication
checks include verifying the Conventional Commits title immediately after creation
and again before handoff. No repository PR template was found.
