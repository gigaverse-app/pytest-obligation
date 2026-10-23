# Readable sticky validation

- [x] Real generated pytest suites in serial and xdist: timing/source survives JSON and worker merging; verdicts unchanged.
- [x] Counts partition observed checks, deduplicate shared profile cases, and count each coverage-gap guarantee once.
- [x] Application ordering prioritizes failures, rejected bindings, blocked execution, then missing coverage.
- [x] One to three applications flatten; larger reports retain the outer disclosure; summaries keep aligned counts.
- [x] Source links use the tested revision and reject paths outside the repository.
- [x] Optional generated exploration is reported separately; disabled exploration does not inflate blocked checks.
- [x] Old JSON retains an explicit unknown timing/source/exploration state.
- [x] Actual bot sticky on GitHub: inspect collapsed and expanded layout, source links and count images.

Validation evidence: core suite passed locally (1,154 passed, one skipped). After exercising CI checkout boundaries, the affected reporting tests passed (34 tests), including an outside-checkout source case. Ruff, Pyrefly, documentation links and the nine publisher tests passed.

GitHub verification: the actual bot comment on PR #127 renders the collapsed counts and expanded contract source, coverage gaps and Hypothesis 3/3 scenario checks. A three-application preview in GitHub's own comment editor confirmed identical x-coordinates for all five badge columns across different application names; the illustrative preview was cleared without posting it. Final CI and live-comment links are recorded in the PR description.
