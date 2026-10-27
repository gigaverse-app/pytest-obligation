# Evidence from separate CI jobs

- [x] Reproduce complementary lane selection with two real pytest subprocesses and render their combined checks once.
- [x] Validate each lane independently: missing files, mismatched revisions and failed tests survive aggregation, including excess files in another lane.
- [x] Preserve completed evidence while reporting unavailable lanes; never infer a pass from inventory or job success.
- [x] Reuse the existing artifact reader, report merger and renderer for CLI/action aggregation.
- [x] Verify staged aggregate evidence re-renders with unavailable-lane state preserved. Version 2 prevents old publishers from silently dropping it.
- [x] Document CI lane collection and aggregation; 225 focused Python tests, 43 publisher tests, ruff and pyrefly passed. All 25 PR CI checks passed at implementation commit 7dc7bd9.

The backend replay-sensitivity declaration also exposed missing `ReplaySafeEffect`
guard dispatch in `RegressionControl`. A regression test failed before the fix;
the shared control now verifies baseline, duplicate-effect fault and restoration,
and rejects a fault that does not change behavior.
