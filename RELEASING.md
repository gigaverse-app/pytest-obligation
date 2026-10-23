# Releasing pytest-obligation

## The release PR is the manual publishing decision

Normal feature and fix PRs run the complete `CI` workflow, including the OSS
application/demo suites. After a successful CI run on the current `main` head,
Release Please opens or updates one release PR with the accumulated version and
changelog. Leave that PR open while alpha development continues; ordinary merges
**do not publish a version**.

The release PR runs the same normal CI. Merging it authorizes publication:

1. Normal CI tests the merged commit on `main`.
2. `Release` runs after CI succeeds, creates `vX.Y.Z` and the GitHub release,
   then builds that exact tag. An outdated CI completion cannot release a newer head.
3. The build verifies that the resolved tag has a successful **push CI run on
   main for that exact SHA**, checks distribution metadata, and smoke-tests the wheel.
4. The isolated `pypi` job publishes the wheel and source distribution with
   Trusted Publishing; the distributions are attached to the GitHub release.

A failed or cancelled main CI run cannot publish. A release build can repeat
packaging checks because it builds a newly tagged version, but it does not run a
second copy of the test suite. If the main head advances during release creation,
the exact-tag CI check still prevents publication of an untested commit.

## Why GitHub can ask to approve CI

Release Please's default `GITHUB_TOKEN` creates PR workflow runs that need approval
on every update. This is a [GitHub token rule](https://docs.github.com/en/actions/concepts/security/github_token#when-github_token-triggers-workflow-runs),
not PyPI approval and not a request to publish. Approving those workflows only runs
CI; **merging the release PR** is the publishing decision.

Release Please uses the existing organization secret `GV_CI_CROSS_REPO_TOKEN`.
In the organization's Actions secret settings, include this repository in that
secret's selected repositories. The credential needs Contents and Pull requests
read/write access. The release job fails clearly when it is absent; it never
falls back to `GITHUB_TOKEN` and recreates the approval prompt.

The `release-automation` environment restricts the release job to `main` without
required reviewers. The shared secret is repository-accessible, not scoped to
that environment; maintainers who can change trusted workflows can use it.
Release automation follows the shared CI credential's existing rotation lifecycle
and no longer stores a separate copy of the maintainer's GitHub CLI credential.

## One-time publisher setup

Configure the PyPI Trusted Publisher for project `pytest-obligation`:

- Owner: `gigaverse-app`
- Repository: `pytest-obligation`
- Workflow filename: `release.yml`
- Environment: `pypi`

For a new project, use a pending publisher under PyPI Account → Publishing.
For an existing project, use its Publishing settings. TestPyPI is separate;
configure the same identity with environment `testpypi` for rehearsals.

The GitHub `pypi` environment should allow only `main`, without required reviewers:
the release PR merge already supplies the manual decision. Manual dispatch must
also run from `main`. Keep default Actions permissions read-only and allow Actions
to create pull requests. Prefer squash-merging ordinary PRs with their checked
Conventional Commit titles.

## Versions and retries

Release Please calculates SemVer from Conventional Commits: `fix:` and `perf:`
bump the patch, `feat:` bumps the minor, and breaking changes bump the minor while
below 1.0. Docs, style, refactoring, tests, build, CI and chore changes do not independently
request a release unless they declare a breaking change. A `feat:` bumps the minor
even below 1.0; a breaking change bumps the major once the package reaches 1.0.
`hatch-vcs` derives package versions from Git tags. Untagged source builds as a
development version; embedded subtrees use the explicit development fallback.
Neither the package metadata nor the lock needs a version edit on release PRs.

Use `Actions → Release → Run workflow`, on `main`, with an existing `vX.Y.Z` tag
to retry a failed publish. Choose `pypi` explicitly; the default is `testpypi`.
Production retries still require successful main CI for the resolved tag commit.
Re-run that commit's failed CI first. An empty tag is allowed only for a TestPyPI
development rehearsal. A successful upload is immutable; do not reuse a version
for different source.

Successful releases also maintain the existing floating `v0` action tag so
`gigaverse-app/pytest-obligation/check@v0` follows the latest compatible release.
