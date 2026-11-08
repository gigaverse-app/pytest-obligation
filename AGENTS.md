# Working on pytest-obligation

Read [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and validation.
Use [RELEASING.md](RELEASING.md) for the release process.

## Commits and pull requests

- Use Conventional Commits for commits you create and PR titles:
  `type(optional-scope): description`, for example
  `fix(parser): handle empty input`.
- Allowed types: `feat`, `fix`, `perf`, `revert`, `docs`, `style`,
  `refactor`, `test`, `build`, `ci`, and `chore`. Choose the type for the
  actual change. Mark breaking changes with `!` before the colon and explain
  the migration in the PR body.
- Repair an invalid PR title in place. Preserve useful work; do not close or
  replace the PR, or rewrite existing commits just to satisfy the title check.
- Squash merges use the checked PR title. Keep any `BREAKING CHANGE:` details
  in the body. Follow [CONTRIBUTING.md](CONTRIBUTING.md) and
  [RELEASING.md](RELEASING.md).

## Shared agent instructions

Edit this root `AGENTS.md` as the single source for Codex and Claude.
`CLAUDE.md` is an AgentSync-managed relative symlink to this file, not a
separate instruction document. The configuration is
[agentsync.toml](agentsync.toml). To restore and verify the link:

```bash
npx --yes @dallay/agentsync@1.52.3 apply
npx --yes @dallay/agentsync@1.52.3 status
```

Keep the symlink tracked in Git. See CONTRIBUTING.md for platform setup.

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

## GitHub Actions versions

- ALWAYS use published major-version tags for established GitHub Actions, for example `actions/checkout@v7` and `actions/upload-artifact@v7`, so compatible fixes arrive without per-commit maintenance. NEVER replace those tags with commit hashes unless the user explicitly requests that exact exception. If a publisher has no major-version tag, use its published release tag rather than inventing a ref or substituting a hash.
- ALWAYS use `gigaverse-app/dry-lint@main` until its v1 launch, then use `@v1`. Apply the same ref in workflow examples and adoption instructions.

## Maintained Quint contracts

For behavior covered by a registered `docs/quint/*/manifest.json`, review the
production implementation, current `fixed.qnt`, adapter and action mapping
together. Run `uv run --no-sync pytest verification_tests/quint --quint-require-complete`
([guide](docs/quint/README.md)) before publishing a behavior change. Keep historical `audit.qnt` files immutable,
retain known-bad mutation controls, and investigate drift instead of automatically
weakening an invariant or expected observation. This applies to registered
contracts; unrelated changes do not require inventing a new specification.

## Maintained Python source contracts

`veripy-project.json` enrolls the current report merge AST. For edits to its source,
external model dependencies, heap schema, proof sidecar or verifier toolchain,
review the source/effect proof and real API observations together, then run
`python -m scripts.source_contracts.check` as described in
[the source contract guide](docs/source-contracts/report-merge.md). Intentional
source changes use `--generate` to prove and refresh artifacts before checking.
Keep enrollment and exact runtime inventory nonempty and fixed; retain semantic
source mutants and guard-removal/no-op runtime controls. Unsupported required
targets, missing observations, stale proof artifacts and surviving mutants fail.
State external purity/type assumptions and exception exclusions explicitly.
Preserve the registered Quint contract and immutable historical audit model.
