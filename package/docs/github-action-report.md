# A PR report that explains what your tests establish

Add `pytest-obligation/report` after the tests that generate your contract evidence.
It updates one comment per PR and report key, writes a job summary, and uploads the
full JSON and Markdown. A failed pytest step still fails the job. Reporting does
not change your validation policy. Fork PRs get the same comment from a separate,
trusted job: see [Fork PRs](#fork-prs-publish-from-a-workflow_run-job).

The banner and compact headline follow CI-esta's sticky layout. Expand an application
to see its guarantees, missing evidence, failed checks and recovery state.

Read the workflow status first. A failed workflow starts with a red heading and a
warning above the report, even if the uploaded evidence claims success. That status
comes from GitHub for the exact run attempt. A report published inside the test job
uses the test-step outcome supplied to the action instead.
The workflow link sits at the bottom: `run` for the first attempt, then `run 2`,
`run 3`, and so on. Successful workflows need no extra status heading.

The graphics count **obligation contract checks**. Other pytest tests and workflow
steps are outside these counts. Green means a contract check passed or an issue
count is zero; red means contract failures or rejected bindings; amber means blocked
checks, coverage gaps or an unknown count (`?`). A failed workflow keeps these colors:
it can contain both passing and failing contracts. For example, 17 green contract
checks and zero contract failures can coexist with a red workflow because an ordinary
pytest test failed. Missing evidence is marked unavailable and never gets green zeroes.

The header counts applications and passing contract checks on the left, with contract
failures, blocked checks, coverage gaps and rejected bindings after a divider.
Application names use the full available width and wrap when needed. Their colored
counts align to the right underneath, and stay visible while the details are closed.
One to three applications appear directly; larger reports use an outer disclosure.
Applications sort by failed assertions, rejected bindings, blocked execution, then
coverage gaps, with the largest count in the first applicable category first.

GitHub strips custom CSS. The reporter assembles a finite set of themed SVG digits,
labels and spacers around native application names, expanders, source links and
text. For example, `251` references the existing `2`, `5` and `1` images. Wider
counts keep the same column positions. Zero issues use green digits.

The reusable assets in `docs/assets/report-glyphs/` total about 25 KB. They ship
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
Markdown are retained as workflow artifacts. A fork PR's run keeps the summary
and artifact; [the `publish` action](#fork-prs-publish-from-a-workflow_run-job)
posts its comment.

## What the counts measure

Passing, failed, blocked and rejected counts partition unique expected checks.
Related guarantees referencing the same check do not multiply its count. A setup
or cleanup failure is blocked execution; a harness binding rejection takes
precedence over that classification. An executed check declared as a known defect that
xfails counts as a failure, alongside unexpected assertion failures. The headline
breaks these down as unexpected and known expected, and explicitly says when CI
succeeded with expected failures. These are failed checks, not distinct product
bugs; inspect the application reasons and test assumptions before deciding on a fix.

An unexecuted known-defect declaration does not count as an executed failure.
Binding-debt and unclassified expected failures, setup-phase xfails, and unexpected
passes remain blocked evidence with their explicit outcome in the details.

Coverage gaps count guarantees, not tests. Each guarantee with a missing
assessment, missing scenario family, no expected checks or declared gap counts
once. A declared known defect also leaves its guarantee incomplete. A failed or
filtered check alone, without such a declaration, does not add a coverage gap.
Declined and not-applicable guarantees are deliberate exclusions, listed
separately with their application reasons; they do not establish passing coverage.

Application detail separates declared known defects, unassessed guarantees/scenarios and
deliberate exclusions. Expected failures retain the underlying exception diagnostics,
including binding rejections and setup errors. A declared gap without a behavior
probe, or a failed proof precondition, is not a reproduced product defect. Generated strict expected failures retain their canonical
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

Scheduled-selection suites report a separate **Scheduled selection and loop** scope.
It covers the declared query, schedule evidence and any supplied loop checks. It
never claims the full automatic-recovery profile A. Expected failures retain their
reasons and tickets, filtered checks remain incomplete, and an explicit
`unscheduled_because` declaration stays visible as excluded schedule evidence.
The JSON uses the `selection` key in the existing `profiles` mapping; this is a
reporting scope, not an additional profile in the A–J catalog. Older JSON keeps
its original interpretation.

Executable handoff exemptions report their own **Handoff exemption** scope and
the application's reason. A passing probe verifies only that stated exemption;
it does not claim A–J lifecycle coverage. Failed setup, proof or cleanup, and
filtered exemption tests remain incomplete. A class declaring both a contract
and an exemption retains both sets of evidence. Static discovery uses the
exemption class name when no literal application name exists. The JSON uses the
`exemption` key in the existing `profiles` mapping.

## Start with your existing test job

### Account for applications outside the selected tests

Pass `application-paths` as newline-separated source roots after checking out the
tested revision. The reporter reads Python source without importing applications,
loading fixtures or collecting tests. It recognizes directly decorated
`due_work_contract_suite`, `safety_contract_suite`, `scheduled_selection_suite`, `exempt_due_work_suite` and Due
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
explicit pytest skips. It shows an amber **?** when uncollected applications or incomplete
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

A fork PR's token is read-only, so its run cannot comment: the report step keeps
the summary and artifact and says, in its log and summary, that a `workflow_run`
publisher posts the sticky. Add one as described in
[Fork PRs](#fork-prs-publish-from-a-workflow_run-job). `post-comment: 'false'`
disables publication from the test run; remove the write permission in that case.
Missing comment permission preserves the summary/artifact. Missing or invalid reports
produce **Evidence unavailable**, never a green verdict. Valid empty objects report
that no application contract checks ran. Do not run
untrusted PR code with a write token under `pull_request_target` to bypass this.

Pass `test-outcome` so a collection error or a failure outside the generated
contracts remains visible even when the recorded contract checks passed. Without
it, overall test-step status is explicitly **unknown**.

## Fork PRs: publish from a `workflow_run` job

**The publisher is safe to enable for fork PRs because the contributor never receives
its commenting token.** Tests run with a read-only token. A separate publisher reads
their evidence in an offline container with no credentials, then updates the matching
PR. It never checks out or runs the contributor's code.

You choose the publisher version by pinning a reviewed commit. Its GitHub action,
container image and Python dependencies are pinned too. An update requires changing
that pin in your workflow, where you can review it like any other dependency update.

### Set it up

Use a fresh GitHub-hosted Linux runner (`ubuntu-latest`) for the publisher. Docker is
already available there. Give this job only `actions: read` and `pull-requests: write`;
use its default `GITHUB_TOKEN`. It needs no personal access token, repository secret,
checkout, application installation or connection to a pytest-obligation service.

The test workflow generates the report and artifact. With a publisher installed, the
test job can use read-only permissions for both fork and same-repository PRs:

```yaml
name: Application contracts
on: pull_request
permissions:
  contents: read
jobs:
  contracts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
      - run: uv sync --locked
      - name: Test application contracts
        id: tests
        run: uv run --no-sync pytest tests/contracts --due-work-profile-report=obligation-profiles.json
      - name: Explain the evidence
        if: always()
        uses: gigaverse-app/pytest-obligation/report@03273d99b1dec050aeeab8175ade23e8927d7c1a
        with:
          report-path: obligation-profiles.json
          sticky-key: application-contracts
          test-outcome: ${{ steps.tests.outcome }}
          post-comment: 'false'
```

Put the publisher in a **separate workflow file on your default branch**. The name
under `workflows` matches the test workflow, and `sticky-key` matches its report step:

```yaml
name: Application contracts sticky
on:
  workflow_run:
    workflows: [Application contracts]
    types: [completed]
permissions: {}
jobs:
  publish:
    if: ${{ github.event.workflow_run.event == 'pull_request' }}
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      actions: read
      pull-requests: write
    concurrency:
      group: application-contracts-sticky-${{ github.event.workflow_run.head_repository.full_name }}-${{ github.event.workflow_run.head_branch }}
      cancel-in-progress: false
    steps:
      - uses: gigaverse-app/pytest-obligation/publish@03273d99b1dec050aeeab8175ade23e8927d7c1a
        with:
          sticky-key: application-contracts
```

The commit above includes the publisher and its tested dependencies. Review it before
adopting it. To update later, review a newer release and replace the full commit SHA.
Floating `@v1` tags remain available for projects that choose automatic action updates.
A version predating `publish/action.yml` cannot publish fork reports.

### Why a fork cannot use the publisher's token

The two jobs have different responsibilities:

```text
Contributor's PR -> tests, read-only token -> evidence archive
                                                   |
Your default branch -> pinned publisher ------------+
                          |
                          +-> offline container: read data, render text
                          |      no token, no network, no checkout
                          |      no writable host directory
                          |
                          +-> GitHub API: update the matching PR comment
```

1. **The contributor cannot change the running publisher.** GitHub reads its workflow
   from your default branch. The commit pin selects the publisher's code; the archive
   cannot replace it or any of its dependencies.
2. **Evidence is opened without credentials.** The container reads JSON and JUnit as
   data. It ignores uploaded Markdown and Python files. It has no network access,
   runs as an unprivileged user and cannot write to the host. Only a bounded text
   result comes back. That text is never executed or interpreted as workflow commands.
3. **The archive cannot choose where to comment.** GitHub's API supplies the run and
   PR identity. The publisher requires one open PR with the matching head repository
   and commit in your repository, and checks the head again before writing. Artifact
   IDs and hashes come from GitHub; the download must match that hash.
4. **Oversized or malformed input has a safe result.** Download, extraction and rendering
   have explicit limits. Invalid paths, links, duplicate entries and excessive input
   are rejected. The sticky says **Evidence unavailable** and links the original run.
   It does not silently turn a failed render into a passing result.
5. **Application text cannot impersonate the publisher.** The reporter escapes markup
   and breaks automatic mentions, issue references and bare links. Explicit debt-ticket
   URLs remain labelled links. The publisher identifies its sticky only by the trailer
   it appends, so a marker inside application text cannot select another comment or
   prevent a newer report from replacing it.

The token is only sent to GitHub's API. It is not passed to artifact storage or the
container. The job requests no source-write, release, package-write or OIDC permission.
GitHub's `pull-requests: write` permission covers more than one comment; the reviewed
publisher code narrows its use to the matched PR. Keep this as a dedicated job with
the permissions shown above.

### What the report proves

The **GitHub workflow** status comes from GitHub's API for the exact run attempt. A
failed workflow gets a red heading and warning above the graphics, even if the
uploaded evidence says "success". Contract graphics keep their own colors: a green
passing count does not mean the whole workflow passed.
Source links point to the API-verified PR head.

The check results, application names and test-step outcome come from the PR's evidence.
They are labelled as reported values. As with any contributor-controlled test, a PR
can change a test or fabricate its output. The sticky helps you inspect that evidence;
it does not approve the PR, change required checks or certify that the contributor's
code is honest. Review the code and test changes as usual.

### Does using it give the pytest-obligation maintainer access to my repository?

There is no hosted service or maintainer token. The publisher runs on **your runner
with your repository's short-lived token**, using the code you pinned. Nothing sends
that token to the pytest-obligation project. Someone using the action in another
repository receives no access to yours, or to the action maintainer's repository.

Running it in pytest-obligation itself has the same rules: outside contributors can
supply evidence, and that evidence goes through the same sandbox and limits.

### Showing it before a project adopts it

GitHub requires a `workflow_run` workflow to exist on the default branch. Adding the
publisher to the first adoption PR does not activate it. This is the project's opt-in
boundary.

**Use the preview command to show the report on that first PR. The target project
does not need to merge anything, install an app or give you a token.** You run tests
in your public fork and publish an ordinary comment under your own GitHub account.
Running the command again updates your preview comment.

The message for the adopter is simple: **it is safe to inspect because it is a GitHub
comment. Viewing it runs no project code and grants no repository access.** The report
identifies the fork run and exact commit. Its results are contributor-reported evidence;
they are not the target project's CI or approval.

#### Generate evidence in your fork

Use a fresh GitHub-hosted runner in a fork with no repository, organization or
environment secrets available to its test job. Give the job only `contents: read`,
disable checkout credential persistence, and do not grant OIDC or deployment access.
Installing dependencies and running tests can execute the project's code, so do not
run them on the computer that holds your maintainer credentials.

Configure your fork's test workflow to run on `push` (or `workflow_dispatch`). Use the
report step above with `post-comment: 'false'`. Choose the branch and commit used by
your adoption PR. The preview accepts a completed run from that exact public fork,
branch and commit. A `pull_request` merge run is not interchangeable with a fork's
head-commit run.

This setup is entirely in **your fork**. The upstream default branch needs no workflow.
You can remove demonstration-only workflow files from the adoption diff later; rerun
the evidence for the new commit before updating the preview.

#### Publish from your trusted computer

Use Node.js 22 or later, a local Docker daemon, and the GitHub CLI signed in as the
account that opened the PR. Run the command from a reviewed pytest-obligation checkout,
kept separate from the adopter's checkout. Do not run a copy supplied by the adopter.
There is no npm installation or adopter package installation in this step.

The tested preview implementation is commit
[`2ea1185fce02fd909b80a86228bfa2a4184d5e74`](https://github.com/gigaverse-app/pytest-obligation/tree/2ea1185fce02fd909b80a86228bfa2a4184d5e74).
For a new installation, clone pytest-obligation into a separate directory, review
that commit, and check it out with `git checkout --detach 2ea1185fce02fd909b80a86228bfa2a4184d5e74`.
To update later, review and select a newer commit; the command does not update itself.

```bash
# In your reviewed pytest-obligation checkout, outside the adopter's repository:
gh auth login --hostname github.com  # only if you have not already signed in
node preview/cli.cjs \
  --pr https://github.com/UPSTREAM/PROJECT/pull/123 \
  --run https://github.com/YOUR-ACCOUNT/PROJECT/actions/runs/456 \
  --sticky-key application-contracts
```

Use the same `sticky-key` as the report step. For a specific retry, the run URL can
end in `/attempts/2`; otherwise the command uses the latest attempt. Keep invocations
for one PR and key sequential. The command prints the created or updated comment URL.
It never prints the downloaded report, subprocess diagnostics or authentication token.

The command uses your existing `gh` authentication, or `GH_TOKEN`/`GITHUB_TOKEN` if
already set. It does not accept a token on the command line, create a token or request
broader scopes. Your account and its authentication must already be allowed to read
the fork artifact and comment on the public PR. Repository interaction restrictions
still apply. Never put that credential in the fork's test job.

#### Why the maintainer's credentials stay isolated

```text
Your fork -> disposable test runner, no maintainer secrets -> evidence artifact
                                                               |
Your trusted computer -> preview command -----------------------+
                          |
                          +-> offline renderer: data in, Markdown out
                          |      no credentials, network or project checkout
                          |
                          +-> GitHub API: create/update your preview comment
```

- **The command never checks out the project, installs its dependencies or runs its
  tests.** It fetches GitHub metadata and an evidence archive. Only the pinned renderer
  container opens the archive, with the same limits as the regular publisher.
- **The commenting credential stays in the trusted host process.** It is sent only to
  GitHub's API. The signed artifact-storage request receives no token. Docker subprocesses
  receive an allowlisted operating-system environment; the container receives no host
  environment, credential files, Docker socket or writable host directory.
- **You choose the destination.** GitHub must confirm an open PR authored by your signed-in
  account, a public source fork, and a matching completed run. Artifact contents cannot
  choose the PR, commit, source repository or comment author.
- **Updates preserve ownership and freshness.** Only your numeric GitHub author ID and
  the preview's final marker can identify an existing comment. Other people's comments
  and the regular Actions sticky are separate. Older runs cannot replace newer evidence,
  and the PR head is checked again immediately before writing. Each comment records its
  commit so later PR changes remain visible; there is no automatic background watcher.
- **Bad evidence has a useful, safe result.** Oversized, invalid or unrenderable evidence
  produces an **Evidence unavailable** preview with the real fork workflow status. The
  command never retries parsing outside the sandbox. A mismatched PR or run is not posted.

The operator still trusts the reviewed preview code and their local Docker installation,
as with any authenticated tool. The adopter grants neither of them any new access.
This command supports public github.com repositories; it will not copy a private
repository's evidence into a public comment.

After adoption, the project's default-branch publisher can maintain its own Actions
sticky. The preview remains clearly attributed to its contributor.

#### Verified without target setup

The [first-adoption rehearsal](https://github.com/gigaverse-app/pytest-obligation-preview-rehearsal/pull/1)
ran on October 25, 2026. The target default branch stayed at
`57946fd7632297d427599dbb79f7d7ac43938418`, containing only a README and **zero workflows**.
The source fork had no repository secrets or environments; its test job received only
Contents read and Metadata read permissions.

- A [successful fork run](https://github.com/aviadr1/pytest-obligation-preview-rehearsal/actions/runs/40183439411)
  created [one contributor preview](https://github.com/gigaverse-app/pytest-obligation-preview-rehearsal/pull/1#issuecomment-6396323316).
- After advancing the PR, attempting to publish the old run was rejected without
  changing the comment.
- A [deliberately failed fork run](https://github.com/aviadr1/pytest-obligation-preview-rehearsal/actions/runs/40183633504)
  planted Markdown, a Python file, a false success claim and a forged revision. The
  command updated the same comment, retained the API's failure status, labelled the
  reported claim and excluded the planted Markdown, Python and revision.
- A [run with a broken obligation contract](https://github.com/aviadr1/pytest-obligation-preview-rehearsal/actions/runs/40187568413)
  produced **30 passing contract checks, 4 failing contract checks and 0 rejected
  bindings**. The binding passes the ownership guard, but its deriver never discovers
  owed work. A separate ordinary pytest test also fails, so pytest reports 5 failures
  while the contract report correctly counts 4. The same comment now starts with
  **Fork workflow failed**, followed by green passing counts, red contract failures
  and an amber `?` for the unknown skipped count. The graphical captions explicitly
  say **Contract checks passed** and **Contract failures**. This was checked in
  GitHub's rendered view and through the API, including the forged success claim.

### Limits and maintenance

The [public fork rehearsal](https://github.com/gigaverse-app/pytest-obligation-publisher-rehearsal/pull/1)
tested the pinned version above on October 25, 2026. The test job had only Contents
read permission. The separate publisher had Actions read and PullRequests write.

| Real fork scenario | Result |
| --- | --- |
| [Passing test run](https://github.com/gigaverse-app/pytest-obligation-publisher-rehearsal/actions/runs/40180897969) | [The publisher](https://github.com/gigaverse-app/pytest-obligation-publisher-rehearsal/actions/runs/40180924850) created one sticky with the generated contract results. |
| [Failed run with a forged success claim, revision and Markdown](https://github.com/gigaverse-app/pytest-obligation-publisher-rehearsal/actions/runs/40181008839) | [The publisher](https://github.com/gigaverse-app/pytest-obligation-publisher-rehearsal/actions/runs/40181037997) updated that same sticky. GitHub failure remained visible; forged Markdown and revision were absent. |

The container integration tests also exercise the actual sandbox: no token, external
network, Docker socket or checkout, read-only input and image, unprivileged UID, zero
capabilities, and enforced memory/process limits. Archive and transport tests cover
the bounds below and safe recovery when evidence is rejected.

| Resource | Enforced limit |
| --- | --- |
| Downloaded ZIP | 32 MiB, checked against actual streamed bytes; 60 seconds |
| ZIP entries | 256, including ignored files and directories |
| Expanded archive | 64 MiB total |
| Individual JSON report or JUnit file | 10 MB |
| Manifest / inventory | 64 KB / 50 MB |
| Renderer | 512 MiB memory, 1 CPU, 32 processes, 120 seconds |
| Writable container scratch space | 96 MiB; no writable host mount |
| Captured renderer output | 256 KiB; final comment body at most 55,000 characters |
| Publisher workflow | 10 minutes in the example above |

The publisher skips runs unrelated to a PR, ambiguous/stale PR matches, and absent or
expired artifacts. It runs after both successful and failed workflows. A rejected
archive or failed renderer produces an unavailable report while preserving the
original evidence artifact. It never retries rendering outside the sandbox.

Use one `publish` step per `sticky-key` for multiple reports. Outputs are
`pull-request`, `published` and `markdown-path`. A trusted `workflow_dispatch` job can
pass `run-id` and optionally `run-attempt` to republish an existing run. The same PR
identity and sandbox checks still apply.

The publisher uses a digest-pinned Python image and installs only hash-verified
wheels from `publish/requirements.txt`. The image build receives only publisher source
and its locked requirements; it never receives the PR archive. Dependabot proposes
updates to the action, image and Python requirements. The publisher's Python version
is fixed independently of the Python version used to run the project's tests.

For local inspection, `python -m pytest_obligation.reporting.republish` accepts the
ZIP or an already staged directory plus the run's head SHA, ID and attempt. The
GitHub action always uses the container, including for a manual republish. The layout
is `manifest.json`, `reports/*.json`, `junit/*.xml`, optional `inventory.json`, and
`report.md` for people. The publisher never reads that uploaded Markdown.

## Keep the report in a README

A repository can show its latest report on its front page, with a badge. Add the two
markers to a Markdown document once:

```markdown
[![pytest-obligation](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/OWNER/REPO/main/.github/obligation-badge.json)](#contracts)

<!-- pytest-obligation:start -->
<!-- pytest-obligation:end -->
```

Then pass `readme-path` and `badge-path` to `report` in a job that runs the contracts on
the default branch, and commit the two files when they change:

```yaml
on:
  schedule: [{cron: "17 5 * * *"}]
  workflow_dispatch:
permissions:
  contents: write
jobs:
  contracts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      # Your environment setup and the contract run go here, writing obligation-profiles.json.
      - uses: gigaverse-app/pytest-obligation/report@v1
        if: ${{ !cancelled() }}
        with:
          report-path: obligation-profiles.json
          expected-reports: '1'
          test-outcome: ${{ steps.tests.outcome }}
          post-comment: 'false'
          readme-path: .github/README.md
          readme-source: daily run on the default branch
          badge-path: .github/obligation-badge.json
      - if: ${{ !cancelled() }}
        run: |
          git add .github/README.md .github/obligation-badge.json
          git diff --cached --quiet && exit 0
          git -c user.name=github-actions -c user.email=github-actions@users.noreply.github.com \
            commit -m "Update the pytest-obligation report"
          git push
```

- **Only the markers' contents change.** Everything else in the document is yours, so it
  can be edited, or merged from upstream, independently. A document without exactly one
  start marker followed by one end marker fails the report step in words.
- **It changes only when the evidence does.** The document's copy leaves out elapsed and
  summed check times, the run link and source links pinned to the run's commit, and its
  source line is `readme-source`. A run that finds the same thing commits nothing.
- **The badge says what the report says.** It is a
  [shields.io endpoint](https://shields.io/badges/endpoint-badge) built from the report's
  own counts: green when every check passed, yellow when the only failures are declared
  known defects, orange for blocked checks, red for an unexpected failure, a rejected
  binding or a failed test step, and grey when the evidence is unavailable. A known defect
  that a dependency fixes passes unexpectedly, which a strict expected failure turns into a
  failed run: the badge shows it as blocked and red until the declaration is updated.
- **GitHub shows `.github/README.md` first.** A fork can keep its upstream `README` untouched
  and put its own front page, with the report, in `.github/README.md`.

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
contract reasons also enter the artifact/comment. The renderer escapes HTML and
Markdown and breaks mentions and references; that is not secret redaction. Review your report before
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
