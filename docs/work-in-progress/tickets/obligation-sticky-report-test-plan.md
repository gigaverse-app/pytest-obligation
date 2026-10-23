# Sticky report validation

The report must preserve the difference between observed failures, missing execution,
declared coverage gaps, and rejected test bindings. Application text must remain data.

- [ ] Real generated suite -> pytest JSON -> Markdown: complete, filtered, known-gap and failed runs.
- [ ] Real binding guard rejection -> structured failure -> explicit repair-test advice.
- [ ] Setup/teardown failures, extras, empty input and stored forged verdicts never become supported claims.
- [ ] Markdown escapes application names/reasons; bounded output retains the headline and raw-report pointer.
- [ ] GitHub publisher with fake API boundary: create/update, bot ownership, separate keys, stale head/run, forks, permissions.
- [ ] Action smoke: isolated renderer, job summary, artifact and publication inputs; tests retain their original exit status.
- [ ] Existing core/reporting tests, lint, type checking, package build and documentation links.
