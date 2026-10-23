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

See [ARCHITECTURE.md](package/docs/architecture.md). In short: nothing outside
`src/pytest_obligation/integrations/` imports a framework; integrations import
theirs only when installed; every harness defense is self-tested in both
directions (a conforming binding passes, a counterfeit fails with its specific
message).

## Finding weaknesses in other projects

A new demo, an integration, or an upstream report follows [the upstream playbook](docs/upstream-playbook.md), with the templates in [`docs/upstream-templates`](docs/upstream-templates). With Claude Code, the `find-upstream-weaknesses` skill in `.claude/skills` runs the whole cycle.

See [package ownership and subtree development](package/docs/development.md) for library edits made inside an adopter checkout.


## Selective CI inputs

`.github/test-lanes.json` selects complete framework/conformance lanes. A
MongoDB-only test change runs MongoDB; changes to the shared plugin/runtime,
shims, locks or CI configuration retain full testing. Main, `test:full` and
planner failures retain full-suite execution.

Changes confined to `package/README.md` or `package/docs/` need packaging checks,
not live framework test services. Build, lint and type checks always run; the
build job still builds the distribution, checks its contents, installs the wheel
without framework dependencies and runs compatibility/identity controls. The
package prose is not executed by the test lanes. Root `docs/demo.tape` and
`docs/demo_env.sh` remain demo-lane inputs because the executable README demo
reads them. If tests begin consuming package documentation, declare that input.

The planner JSON names the tests/inputs selecting each lane. An affected test
outside all configured lane roots falls back to every lane and names the missing
mapping. Add new test directories to a lane whose pytest command executes them.
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
