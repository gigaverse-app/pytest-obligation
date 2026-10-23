# Sticky report validation

The report must preserve the difference between observed failures, missing execution,
declared coverage gaps, and rejected test bindings. Application text must remain data.

- [x] Real generated suite -> pytest JSON -> Markdown: complete, filtered, known-gap and failed runs.
- [x] Real binding guard rejection -> structured failure -> explicit repair-test advice.
- [x] Setup/teardown failures, extras, empty input and stored forged verdicts never become supported claims.
- [x] Markdown escapes application names/reasons; bounded output retains the headline and raw-report pointer.
- [x] GitHub publisher with fake API boundary: create/update, bot ownership, separate keys, stale head/run, forks, permissions.
- [x] Action smoke: isolated renderer, job summary, artifact and publication inputs; tests retain their original exit status.
- [x] Existing core/reporting tests, lint, type checking, package build and documentation links.


Validated in PR #122: 1,139 core tests passed (1 skipped), then 21 focused reporter tests passed after the final optional-diagnostic guard. Nine publisher controls and thirteen CI routing/document controls passed. GitHub's example-adopter action completed and created comment 6370098279 plus the full evidence artifact in run 39990121250. Banner rendering was inspected in the live comment. Read the Docs is separately blocked by the repository's missing .readthedocs.yaml, also absent from main.

