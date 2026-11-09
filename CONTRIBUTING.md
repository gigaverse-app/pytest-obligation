# Contributing

## Conventional Commits

Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
for commits you create and PR titles (the squash commit that lands on `main`):

```text
fix(parser): handle empty input
feat: add a new output format
feat(api)!: remove the deprecated argument
docs: clarify installation
```

Allowed types are `feat`, `fix`, `perf`, `revert`, `docs`, `style`,
`refactor`, `test`, `build`, `ci`, and `chore`. Scope is optional.
Use `!` before the colon for breaking changes and explain the migration in the
PR body. Choose the type for the actual change, since release tooling uses it.

The `conventional-commit` check uses
[amannn/action-semantic-pull-request](https://github.com/amannn/action-semantic-pull-request).
It reads PR metadata, including for forks, without checking out contributor code.
If it fails on a title, rename the PR; the edited event reruns the check.
Keep the existing PR and commits. Work-in-progress commits need not be rewritten.

Use **Squash and merge**, with the PR title as the commit title. Check the final
message before merging, including single-commit PRs, and preserve any
`BREAKING CHANGE:` explanation in the body. The repository's squash defaults
support this, but a maintainer can still edit the final message.
See [RELEASING.md](RELEASING.md) for versioning and publishing.

## Tooling

The project is managed with [uv](https://docs.astral.sh/uv/). `uv.lock` is
committed, and CI installs from it with `--locked`, so a change to dependencies
must come with `uv lock`.

```bash
uv sync --all-packages --all-extras                      # everything: the core, every integration, lint and type-check tools
uv run ruff check && uv run ruff format --check
uv run pyrefly check                      # the demos type-check against their upstream code: fetch it first (below)
```

## Tests

The core must work with no framework installed, and CI proves it with an
environment that has only the package and pytest:

```bash
uv sync --all-packages --no-default-groups
uv run python scripts/check_core_is_framework_free.py
uv run pytest package/tests/core
```

The Django integration's self-tests need PostgreSQL (the standard `PG*`
variables; defaults `postgres:postgres@localhost:5432`):

```bash
uv sync --all-packages --no-default-groups --extra django --extra celery
uv run pytest package/tests/django --ds=tests.django.settings
```

The demos run the harness against upstream demo applications pinned by commit:

```bash
uv run --no-project python demos/fetch_upstream.py
uv sync --all-packages --no-default-groups --extra django --group demos
uv pip install -e demos/.upstream/procrastinate
PGDATABASE=procrastinate_demo uv run --no-sync pytest demos/procrastinate_demo_django --ds=demos.procrastinate_demo_django.settings
uv run --no-sync pytest demos/dbos_transactional_outbox -p no:django
```

## Rules the code follows

Redis-backed self-tests own their servers, including a separate server for
server-wide faults. Install `redis-server` and the Redis/Celery/RQ extras, then run:

```bash
uv run python -m pytest_obligation.integrations.redis_server -- pytest package/tests/rq package/tests/celery_worker -n 4
uv run python scripts/check_celery_regressions.py
```

The second command verifies observer sensitivity against two pinned upstream fix
reversions using real workers; it creates a temporary checkout and disposable
Redis. See [contract validation](package/docs/validating-contracts.md) for the
framework-independent control and evidence requirements. Direct destructive
self-test runs require explicit dedicated-server configuration; localhost is
never assumed disposable.

See [ARCHITECTURE.md](package/docs/architecture.md). In short: nothing outside
`src/pytest_obligation/integrations/` imports a framework; integrations import
theirs only when installed; every harness defense is self-tested in both
directions (a conforming binding passes, a counterfeit fails with its specific
message).

## Finding weaknesses in other projects

A new demo, an integration, or an upstream report follows [the upstream playbook](docs/upstream-playbook.md), with the templates in [`docs/upstream-templates`](docs/upstream-templates). With Claude Code, the `find-upstream-weaknesses` skill in `.claude/skills` runs the whole cycle.

See [package ownership and subtree development](package/docs/development.md) for library edits made inside an adopter checkout.


## Selective CI inputs

[CI-esta](https://github.com/gigaverse-app/ci-esta)'s `plan-work` plans complete
framework/conformance lanes before any runner starts. The lanes are the names the
jobs' conditions read (`fromJSON(needs.select-tests.outputs.lanes).<lane>`), and a
change selects a lane through what its jobs run: the tests that import it
([pytest-selective](https://github.com/gigaverse-app/pytest-selective)'s graph), the
files tests declare they read, the Node tests' module graph, the files the wheel
contains, and the scripts and local actions the job executes. A MongoDB-only test
change runs MongoDB; the pytest plugin, which pytest loads into every session through
its entry point, and anything it imports run every test lane; locks, project and
pytest configuration run everything. Explicit full runs and planner failures retain
full-suite execution; ordinary main pushes use dependency selection.

Changes confined to `package/docs/`, the root README, `docs/` prose or the Read the
Docs site (`documentation/`, its requirements files and `mkdocs.yml`) run no tests,
builds or smoke checks. `package/README.md` and `package/LICENSE` are embedded in the
distributions, so they select the jobs that build the wheel: `build` and `due`. Root
`docs/demo.tape` and `docs/demo_env.sh` select the demo lane because the executable
README demo reads them. If tests begin consuming package documentation, declare that input.

When a test or a script starts reading a file by path, declare it next to the reader:
a `<test>.gv-dependency.yaml` sidecar (`pytest-selective audit --write-declarations`
writes them from a recorded run) or a `# gv:test-dependency: PATH` comment.
[.github/test-lanes.json](.github/test-lanes.json) extends the workflow with only
what the graphs cannot see: the `core` lane's roots, the environment files that run
every lane, and the type-check's project files. `uv run --no-project --with
"ci-esta[selection]>=1.12.0" ci-esta lanes --config .github/test-lanes.json --base
origin/main` shows what a change would run and why. A test outside every lane's roots
falls back to every lane; add a new test directory to a job's test command.
# Measured conformance execution

The Wagtail and Due sessions run every conformance case with four isolated
pytest workers. Wagtail migrates/restores one database and uses CI-esta to clone
the exact schema and seed rows for each worker. Keep all required-case and
profile validators after pytest; parallel reports must merge in the controller.

In the recorded before/after pair, demos fell from 325 to 262 seconds and Due
from 293 to 159 seconds. The overall gate fell from 506 to 422 seconds; Saleor
became the critical path. All 1,183 demo/Due test identities and pass/skip
outcomes matched. See [raw reports, inventories and the isolation tutorial](https://github.com/gigaverse-app/ci-esta/blob/main/docs/benchmarks/2026-10-23-critical-execution.md).

## Shared instructions for Codex and Claude

[AGENTS.md](AGENTS.md) is the canonical repository guidance. Codex reads it
directly; Claude reads the tracked `CLAUDE.md -> AGENTS.md` symlink. Edit
`AGENTS.md` once, including commit-policy changes, so both tools receive the
same instructions.

[dallay/agentsync](https://github.com/dallay/agentsync) manages that link through
[agentsync.toml](agentsync.toml). After cloning, or to repair a
missing or stale link, run these commands from the repository root with Node.js
18+ and npm installed:

```bash
npx --yes @dallay/agentsync@1.52.3 apply
npx --yes @dallay/agentsync@1.52.3 status
```

The CLI version is pinned for reproducible setup. Review and update both commands
when upgrading AgentSync. The configuration disables managed gitignore changes
because we intentionally commit the relative link, following AgentSync's
[committed-destination workflow](https://dallay.github.io/agentsync/guides/gitignore-team-workflows/).
Ordinary instruction edits propagate immediately through the link.

On native Windows, enable Developer Mode and Git symlink support
(`git config core.symlinks true`), then run `apply` to repair a checkout that
materialized the link as plain text. Alternatively, use WSL for a checkout in
the Linux filesystem. See the
[Windows setup guide](https://dallay.github.io/agentsync/guides/windows-symlink-setup/).
If AgentSync backs up an existing `CLAUDE.md`, review and preserve any unique
guidance in `AGENTS.md`; do not commit the backup as another instruction source.

## Documentation-only CI

Documentation-only PRs execute zero tests unless a test or lane explicitly
declares that documentation as an input. This includes CI contract tests,
installed-wheel smoke, package builds and public-action smoke. Local link checks
and the documentation site build still validate documentation; the package build
and metadata checks run only when the package lane is selected. Declare execution
workflows, selector configuration, helpers, locks and non-import inputs; missing
history or failed planning must execute the full affected lanes and fail the
required planning gate. Ordinary PRs and pushes use selection; manual/release/scheduled/full overrides
remain complete checkpoints.

## Duplication

Install both hooks once in each clone:

```bash
uvx pre-commit install
```

The staged `dry-lint` hook uses Sonnet and the same `.dry-lint/baseline.json` as CI. Set your own
`ANTHROPIC_API_KEY` in the shell or an untracked `.env`. Missing credentials fail strict judging.
The `dry-lint-trailers` hook runs at `prepare-commit-msg`: duplicates fixed before the first push are
recorded in the commit message and counted by the PR sticky. The hook environment uses Python 3.13,
independently of the project's runtime environments.

Model duplication review also runs by default in the staged hook and PR check, starting with dry-lint 1.4.0.
Use `rev: v1` for hooks and `@v1` for the Action and CLI installs. If a cached hook environment still runs an
older version, run `uvx pre-commit clean` and rerun the hook.
With our Sonnet setup, model candidates require source review; Sonnet judges functions, and no TypeSafe key
is required for model detection. Review declarations and consumers before accepting or dismissing a pair.
The function baseline and weekly function sweep do not certify the existing model inventory. Follow
[model adoption](https://github.com/gigaverse-app/dry-lint/blob/main/docs/model-adoption.md) for its separate
reviewed baseline. The explicit opt-out is `--no-models` locally or `models: false` on the Action.

The required judged `dry-lint` check rejects new blocking duplicates, incomplete judging and baseline
widening. Forks first run `dry-lint detect`, then a trusted workflow judges the artifact. Read both
functions in a finding: reuse the existing owner for the same concept, preserving behavior and running
the affected tests; for different concepts, add a narrow `# dry-lint: distinct-from path::function`
with the reason. Do not mechanically refactor from a score or add blanket ignores.

The PR sticky tracks fixes across pushes, accepted-backlog cleanup and local-hook credit. Default-branch
runs fold merged PRs into the repository's cumulative ledger. The README sign shows new duplicates kept
out separately from old debt cleaned up; these are pair counts, not lines or estimated time savings.
The cache-backed ledger restarts its counting period if evicted. Dismissals never earn cleanup credit.

The weekly/manual **dry-lint audit** retains its complete report as an artifact, then opens or updates
one `dry-lint/ratchet` PR containing only baseline, progress JSON and README metadata. It uses the inherited
`GV_CI_CROSS_REPO_TOKEN` so normal PR checks run. Missing authentication, incomplete judgment or new debt
fails visibly. A human or agent chooses and tests application refactors; the workflow does not edit application code.

To inspect and record cleanup locally:

```bash
uv tool install --no-config --python 3.13 'dry-lint[anthropic] @ git+https://github.com/gigaverse-app/dry-lint@v1'
dry-lint sweep --budget-usd 5 --report audit.json --output audit.md
# Review findings, refactor selected code, and run its tests before updating the baseline.
dry-lint sweep --update --budget-usd 5 --readme README.md --repository gigaverse-app/pytest-obligation --repository-id 1389937039
```

Commit the metadata with the refactor, or dispatch the weekly workflow after the cleanup merges. Preserve
the existing baseline and its history; never reinitialize or broaden it. Keep raw reports and verdict caches
out of Git. No-change audits leave metadata unchanged. The scope currently uses dry-lint defaults, excluding
tests and migrations; changing the detection contract requires a reviewed migration.

See the [full adoption playbook](https://github.com/gigaverse-app/dry-lint/blob/main/docs/adoption-playbook.md)
and [sweep semantics](https://github.com/gigaverse-app/dry-lint/blob/main/docs/sweeps.md).
