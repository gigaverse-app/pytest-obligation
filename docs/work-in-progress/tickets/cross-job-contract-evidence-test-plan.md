# Evidence from separate CI jobs

- [ ] Reproduce complementary lane selection with real pytest reports and render their combined checks once.
- [ ] Validate each lane independently: missing files, mismatched revisions and failed tests must survive aggregation.
- [ ] Preserve completed evidence while reporting unavailable lanes; never infer a pass from inventory or job success.
- [ ] Reuse the existing artifact reader, report merger and renderer for CLI/action aggregation.
- [ ] Verify staged aggregate evidence re-renders identically for trusted publication.
- [ ] Document CI lane collection and aggregation; verify package checks and action tests.
