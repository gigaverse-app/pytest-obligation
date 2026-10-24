# A PR report that explains what your tests establish

Add `pytest-obligation/report` after the tests that generate your contract evidence.
It updates one comment per PR and report key, writes a job summary, and uploads the
full JSON and Markdown. A failed pytest step still fails the job. Reporting does
not change your validation policy.

The banner and compact headline follow CI-esta's sticky layout. Expand an application
to see its guarantees, missing evidence, failed checks and recovery state.

The header counts applications and passing checks on the left, with failures,
blocked checks, coverage gaps and rejected bindings after a divider. Zero issues
are green. Missing evidence produces an unavailable message instead of green zeroes.
Each application has an aligned row with its counts visible while closed.
Names wider than 20 monospace columns are abbreviated in the row; their full value
remains in the tooltip and expanded application details.
One to three applications appear directly; larger reports use an outer disclosure.
Applications sort by failed assertions, rejected bindings, blocked execution, then
coverage gaps, with the largest count in the first applicable category first.

GitHub strips custom CSS. The reporter assembles a finite set of themed SVG digits,
labels and spacers around native application names, expanders, source links and
text. For example, `251` references the existing `2`, `5` and `1` images. Wider
counts keep the same column positions. Zero issues use green digits.

The 95 reusable assets in `docs/assets/report-glyphs/` total about 22 KB. They ship
with the library, just like the fixed banner, and are served from the action
revision in this public repository. Changing a report only changes its Markdown.
The action generates no SVG files, uploads no images, creates no asset branch,
and needs no image service or repository content-write permission. Application
names, reasons and source paths never appear in image URLs; the assets contain
only generic digits and labels. The same assets also work in private repositories.

The first digit's alt text contains the complete count and category. Other digits
and spacers have empty alt text. `graphics: 'false'` selects plain text. Large
reports automatically switch to plain text before graphical markup would force
application details out of the comment budget. The full JSON and rendered
Markdown are retained as workflow artifacts. Fork PRs still retain the summary
and artifact without posting a comment.

## What the counts measure

Passing, failed, blocked and rejected counts partition unique expected checks.
Related guarantees referencing the same check do not multiply its count. A setup
or cleanup failure is blocked execution; a harness binding rejection takes
precedence over that classification. Expected failures and unexpected passes
remain blocked evidence with their explicit outcome in the details.

Coverage gaps count guarantees, not tests. Each guarantee with a missing
assessment, missing scenario family, no expected checks or declared gap counts
once. A failed or filtered check alone does not also add a coverage gap.
Declined and not-applicable guarantees are deliberate exclusions, listed
separately with their application reasons; they do not establish passing coverage.

Application detail separates known defects, unassessed guarantees/scenarios and
deliberate exclusions. Generated strict expected failures retain their canonical
debt classification and current declaration reason. When a debt baseline is
configured, its matching case/kind supplies the ticket. Use a full HTTP(S) ticket
URL in the baseline for a clickable link; issue keys remain text because the
library does not guess your tracker. Shards must agree on this metadata.
Older reports remain readable, but an unclassified expected failure is never
inferred to be a known defect. Update the test-side package to emit the metadata.

Application details include the contract setup assignment when discoverable,
otherwise the suite definition. Links point to the workflow's tested commit,
including the merge commit when that is what checkout tested. Factories and
imported contracts are not traced speculatively to another definition.

New reports record whole pytest-session elapsed time and summed setup/call/cleanup
durations. Per-application durations include retries and parallel work; they are
not elapsed latency and do not measure unrelated tests. Older JSON explicitly
shows missing timing, source and Hypothesis evidence.

The Hypothesis disclosure reports optional generated schedule-exploration cases
and their actual outcomes. Disabled cases appear as disabled and do not inflate
blocked-check counts. Selected exploration cases contribute to the same observed
check counts as other tests. These are scenario-check counts, not example counts;
shrinking statistics and replay histories are not captured here. Failing histories
remain in the pytest log. Hypothesis use inside arbitrary application callbacks
is outside this view. Existing fixed-history proof rules remain unchanged.

## Start with your existing test job

### Account for applications outside the selected tests

Pass `application-paths` as newline-separated source roots after checking out the
tested revision. The reporter reads Python source without importing applications,
loading fixtures or collecting tests. It recognizes directly decorated
`due_work_contract_suite`, `safety_contract_suite` and Due
`due.django.conformance.suite.effect_contract_suite` classes, including import
aliases, and follows local named bindings for literal application names.
Declarations remain in the tests; no second application registry is needed.

For a project wrapper around these decorators, list its fully qualified import
name in `suite-decorators`. This explicitly declares which wrappers create
application suites; discovery does not execute wrappers or guess from their names.
The same setting is available on both `collect` and `report` and as the repeatable
CLI option `--suite-decorator`. Unresolved display names retain the class identity.

Choose `python-version` when application source requires newer syntax than the
actions' default Python 3.11. For example, a Python 3.14 application can use:

```yaml
    python-version: '3.14'
    suite-decorators: project.testing.application_contract_suite
```

These options affect inventory only. A discovered declaration supplies neither
passing evidence nor collected-test counts; real report and collection artifacts
still provide those. The collector includes these settings in its cache identity.

```yaml
- uses: actions/checkout@v7
- uses: gigaverse-app/pytest-obligation/report@v1
  if: always()
  with:
    application-paths: tests
    report-path: evidence/**/obligation-*.json
    expected-reports: ${{ needs.plan.outputs.report-count }}
    test-outcome: ${{ needs.tests.result }}
```

Use a count derived from the admitted sessions, not the number of downloaded
files. A wholly skipped lane uses `expected-reports: '0'` and
`test-outcome: skipped`. Keep the reporting job admitted on that path so it
replaces an older sticky. This does not require running any tests.

The collapsed application inventory distinguishes recorded results from **Not run** (not
collected or filtered out in this invocation). If expected reports are missing
or invalid, absent applications are **Unknown**, not assumed skipped. Valid empty
`{}` reports say no application contract checks ran and never claim passing
contract coverage. Without an inventory, the report explicitly says it cannot
list uncollected applications.

The graphical summary counts the union of discovered and reported applications,
even when none ran. Its **Skipped tests** counter uses known deselections and
explicit pytest skips. It shows **?** when uncollected applications or incomplete
reports prevent an exact total. Application lists and skip explanations stay
collapsed; zero recorded checks use neutral colors when no execution was reported.

### Exact skipped-test counts without executing tests

Use the `collect` action to reuse a current-run selector's complete, pre-filter
nodeid list (or metadata mapping keyed by nodeid). It scans declarations first and
collects only application source files missing from that data. Its output is bound
to the checkout revision. A matching output is reused; stale or damaged output is
recollected. Never feed it prior-run selector files as current evidence.

```yaml
- uses: actions/checkout@v7
# Your existing environment setup goes here, if collection needs dependencies.
- uses: gigaverse-app/pytest-obligation/collect@v1
  id: inventory
  with:
    application-paths: tests
    collection-input: artifacts/current-run-collected-nodeids.json
    pytest-command: uv run --no-sync pytest --no-selective
- uses: gigaverse-app/pytest-obligation/report@v1
  with:
    inventory-path: ${{ steps.inventory.outputs.inventory-path }}
    report-path: artifacts/**/obligation-*.json
    junit-path: artifacts/**/junit-*.xml
    expected-reports: ${{ needs.plan.outputs.report-count }}
    test-outcome: ${{ needs.tests.result }}
```

Omit `pytest-command` for a cheap planning pass. Restore dependencies and call the
action again only when `outputs.required == 'true'`. Both calls reuse the same
`inventory-path`. Use your project's pytest command; `--no-selective` above is
appropriate when using pytest-selective. The collector always adds `--collect-only`,
preserves configured pytest plugins and targets only missing files. Collection imports those
files and runs collection hooks, but does not execute fixtures or test bodies.
The timeout defaults to 120 seconds and is configurable.

### Reuse collection across runs

For deterministic collection, add the same cache settings to both planning and
collection calls. Start with the entire tracked checkout, then narrow the inputs
only after reviewing imports, pytest plugins, data files, configuration and locks:

```yaml
    cache-inputs: .
    cache-context: ubuntu-24.04/python-3.14/pytest-environment
```

`cache-inputs` accepts newline-separated literal files or directories. It hashes
tracked file contents, including additions and deletions, without walking virtual
environments. The key also includes the action's actual reporter code, application
roots, platform and `cache-context`. Put interpreter and environment choices that
affect collection in that context; do not cache time-, network- or secret-dependent
collection. Empty `cache-inputs` disables cross-run caching.

A matching complete inventory skips application dependency setup and collection.
Only names and collected test IDs are cached. The collector validates the inventory
and binds it to the current revision; JUnit and pass/fail evidence still come from
the current run. Fresh current-run node IDs take precedence. Invalid or partial
entries fall back to collection. Immutable run/attempt cache entries let a repaired
inventory supersede a broken entry without mixing different input identities.

The actions reuse an installed `uv` and disable setup-uv's recursive dependency
cache scan. They do not traverse the application's `.venv` merely to prepare a report.

The top-level **Skipped tests** counter joins collected IDs to the existing JUnit
results. Tests absent from completed admitted sessions, deselections and explicit
pytest skips count as skipped; executed failures remain failures. Repeated XML
reports cannot double-count tests. Missing/invalid evidence, stale inventory or an
interrupted run retains **?**, rather than misclassifying lost execution as a skip.
No historical pass is substituted for current execution. The same CLI is available
as `python -m pytest_obligation.reporting.collect`; the report CLI accepts
`--inventory`, `--collection-revision` and `--junit-input`. Install the `report` extra
for safe JUnit parsing.

Static discovery does not certify a complete inventory of dynamic factories,
generated classes or custom decorators. Those limits and unresolved names are
shown; suites observed at runtime still appear in the evidence details. The full
inventory is preserved beside the Markdown artifact. Restrict the roots to
application contract tests if the repository is very large. The CLI equivalent is
`python -m pytest_obligation.reporting --application-path tests --input 'evidence/*.json' --output report.md`.

Your project needs pytest-obligation with profile reporting (the current source
includes structured failures; older profile JSON remains readable). Install it in
your normal test environment and bind your application's contract using the
[adoption guide](adopting.md). Installing the reporter alone does not generate
application tests.

```yaml
name: Application contracts
on: pull_request
permissions:
  contents: read
concurrency:
  group: obligation-${{ github.workflow }}-${{ github.event.pull_request.number }}
  cancel-in-progress: true
jobs:
  contracts:
    permissions:
      contents: read
      pull-requests: write
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
      - run: uv sync --locked
      - name: Test application contracts
        id: tests
        run: >-
          uv run --no-sync pytest tests/contracts
          --due-work-profile-report=obligation-profiles.json
      - name: Explain the evidence
        if: always()
        uses: gigaverse-app/pytest-obligation/report@main
        with:
          report-path: obligation-profiles.json
          sticky-key: application-contracts
          test-outcome: ${{ steps.tests.outcome }}
```

Use your existing test command, services and test path. The reporter installs its
own isolated Python runtime from the action revision; it does not import your
application or alter its environment. Pin the action to a reviewed commit for
production. The action is available on `main`. A release pin must contain `report/action.yml`;
older releases without that path cannot provide this action.

Use a stable, distinct `sticky-key` for each independently reported test lane.
For a sharded lane, upload each session's JSON with a unique filename, download
only this run's artifacts into a clean directory, then publish once:

```yaml
- uses: gigaverse-app/pytest-obligation/report@main
  if: always()
  with:
    report-path: obligation-evidence/obligation-group-*.json
    expected-reports: ${{ needs.plan.outputs.shard-count }}
    sticky-key: application-contracts
    test-outcome: ${{ needs.tests.result }}
```

The glob combines shards from the same revision and declared test lane using the
plugin's distributed-evidence merger. Missing expected files, malformed JSON or
disagreeing declarations keep the aggregate from claiming complete evidence;
valid reports remain visible. Empty `{}` reports from shards without contracts
are valid inputs. Never mix prior runs, retries or unrelated lanes. This does not
certify contracts absent from the selected tests. Workflow concurrency should
serialize writers for the same PR/key. The publisher also checks the current PR
head and refuses older run IDs/attempts; GitHub comments have no atomic update API.

Fork PRs receive a summary and artifact without a comment. `post-comment: 'false'`
also disables publication; remove the write permission in that case. Missing
comment permission preserves the summary/artifact. Missing or invalid reports
produce **Evidence unavailable**, never a green verdict. Valid empty objects report
that no application contract checks ran. Do not run
untrusted PR code with a write token under `pull_request_target` to bypass this.

Pass `test-outcome` so a collection error or a failure outside the generated
contracts remains visible even when the recorded contract checks passed. Without
it, overall test-step status is explicitly **unknown**.

## Which words belong to whom?

| Report content | Owner |
| --- | --- |
| Application name, suite path, scenario name, reason for a gap | Your contract/test code; explicitly labeled **application** |
| Receipt status, attempt, retry time and other diagnostic fields | Your `RecoveryExample.diagnose` callback; labeled **State (application)** |
| Guarantee names, result labels, phase, fault count, owed/progress observations | pytest-obligation's evidence model |
| Generated case IDs | Library profile/check IDs, sometimes including application-supplied scenario names |

For example, `pending` is an application receipt state. It is not a failing pytest
result. The failure is the assertion that recovery should have completed while the
observed item is still owed. The report keeps those concepts in separate columns.

## More tests, better tests, or a real failure?

| Result | What it establishes | What you should do |
| --- | --- | --- |
| **Supported by this run** | Every check and assessed scenario required by this declared claim passed | Keep adding meaningful application-specific risks as you discover them |
| **Coverage not assessed** | A guarantee or scenario family has no assessment | Bind production code and add scenarios, or state why it is outside scope |
| **Test not collected / filtered out / skipped or incomplete** | Existing expected checks did not finish successfully in this session | Run those checks; writing more tests alone does not fix this |
| **Known gap declared** | Your application explicitly describes a limitation | Read its reason: it may require implementation changes, bindings, or both |
| **Test binding rejected** | A harness guard rejected this test's connection to production behavior | Fix that binding. The affected check provides no supporting evidence |
| **Check failed** | An executed assertion failed | Inspect behavior and the contract's assumptions; do not assume every assertion failure is an application bug |
| **Test setup/cleanup failed** | The fixture/environment failed before or after the behavioral assertion | Repair it and rerun; successful call output alone is insufficient |
| **Not claimed / not applicable** | Your application deliberately excludes a guarantee | Review the reason; a passing declaration check does not prove the excluded guarantee |

The report cannot generally decide that a passing test is meaningless. It flags
binding rejections from actual harness guards, such as test-authored callbacks
that reference no production code. Those guards are targeted checks, not a proof
that all other tests are good. Unknown failure types remain **Check failed**.
The displayed advice is derived from recorded states, not an AI diagnosis.

## Failure details and data exposure

The plugin adds phase, failure category, a bounded exception message and structured
recovery notes to profile JSON. These fields survive distributed report merging.
Old JSON without the new optional fields still renders, with less detail. Tools
using the older strict JSON model must be upgraded to read the new fields.

On recovery failures, the comment shows fault counts, still-owed/progress
observations and application diagnostic state. Only provide safe metadata in
`diagnose`: never customer content, tokens, or credentials. Exception messages and
contract reasons also enter the artifact/comment. The renderer escapes HTML,
Markdown and mentions; escaping is not secret redaction. Review your report before
publishing it to a public repository. Large comments explicitly omit details and
point to the retained JSON artifact.

## Render locally

```bash
python -m pytest_obligation.reporting \
  --input obligation-profiles.json --output obligation-report.md
```

This reads JSON as data and recomputes verdicts from evidence. Stored `verified`
and `passed` display values cannot turn missing/failed execution into green.
The terminal's `--due-work-summary` remains available alongside the PR report.
