# Contributing

## Pull request titles

Pull requests are squash-merged with their title as the commit message, and the
title decides the next release, so it must be a
[Conventional Commit](https://www.conventionalcommits.org/): `fix: ...`,
`feat: ...`, `feat!: ...` for a breaking change, or `docs:`, `test:`, `ci:`,
`build:`, `refactor:`, `chore:` for changes that do not release on their own.
The `PR title` check enforces it. See [RELEASING.md](RELEASING.md).

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
