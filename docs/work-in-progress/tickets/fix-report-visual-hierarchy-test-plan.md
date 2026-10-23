# Restore the sticky's visual hierarchy

- [x] Preserve graphical totals and an aligned overview for every application in a 37-application report.
- [x] Reserve the overview before verbose details; overflow must not hide applications or change verdicts.
- [x] Keep defect reasons/tickets, missing assessments and exclusions in distinct expandable sections.
- [x] Deduplicate identical parent/family exclusions and avoid repeating them in supported guarantees.
- [x] Keep valid disclosure boundaries so GitHub does not display literal Markdown separators.
- [x] Replay the saved 12-shard backend CI evidence and inspect the actual GitHub rendering.
- [x] Run affected reporting, CLI and sharding tests: 60 passed. Repository Ruff lint/format and focused Pyrefly: pass.
- [ ] Verify required CI before publishing at v1.

The regressions failed before the fix: graphics/overview survival under overflow, disclosure boundaries, and duplicated supported-family exclusions. Replayed the original 12 shards from backend run 40035009449; totals remain 37 applications, 2,261 passed, 0 failed, 41 blocked, 13 gaps and 0 rejected. Inspected the posted GitHub preview: all six columns fit, the 28 applications without issues fold away, and actionable application details retain reasons and tickets.
