# Upstream cutover improvements

Bring the consumer's reusable scanner, host and Django delivery improvements
into the public harness while preserving the framework-free core.

- [x] Core controls: lazy application host initialization, invalid factories,
  reviewed suite wrappers and configured task names.
- [x] Django controls: selection completeness and owed-row proofs both use one
  production-delivery owner, including commit callbacks and delayed handoffs.
- [x] Source audit: account for pre-cutover proofs, controls and tools that a
  subtree-only export could miss.
- [x] Packaging, lint and types. The optional integration matrix is enforced by
  [public PR checks](https://github.com/gigaverse-app/pytest-obligation/pull/55/checks).
- [x] Consumer compatibility with this source and the matching Due candidate.

## Validation (2026-10-12)

- Core: **936 passed, one optional-dependency skip**.
- PostgreSQL/Django: **364 passed, one existing strict expected failure**.
- Paired Due candidate: **1,355 passed, four existing expected failures**.
- Ruff and changed-module Pyrefly pass; wheel and source archive build.
- The first public CI revision passed every integration, demo, Python and
  framework-free lane; final-revision CI and consumer validation follow.
- Ownership and intentional exclusions: [cutover audit](../../backend-harness-port.md#cutover-follow-through-october-2026).
- BE with both public candidates: **2,113 passed, 70 existing expected failures,
  six existing collection exclusions**. This includes adopters, concrete counter
  callers, source/debt/Beat policy, populated migration and packaging boundaries.

The final body-level audit recovered the original race deadline validation and
stalled-session cleanup too. Before the fix, eight timeout controls and the
real PostgreSQL stalled-transaction control failed. With the fix, **948 core
tests pass** and the Django race controls release locks even when a transaction
starts late in the race. Due reuses this implementation through its existing
worker-connection exports.

Both driver paths now pass: **366 Django tests with psycopg2**, and the final
**nine PostgreSQL claim-race controls with psycopg 3** in addition to the full
365-test run before the late-transaction parameter was added. The paired Due
suite remains **1,357 passed, four expected failures**.

## Second audit: concurrent BE consolidation (now merged as #5361)

- [x] Preserve generated case IDs, fixture requirements, host database marks and exception-limited strict gaps while centralizing parameter creation.
- [x] Exercise binding authorship/delegation controls, including cycles and trusted harness boundaries.
- [x] Preserve selected-row and handoff verdicts while passing canonical row/edge bindings.
- [x] Exercise projection and scheduled receipt retention, stale repair, reaper isolation and settlement callbacks.
- [x] Run standalone suites and the paired BE adopter/policy checks; retain every existing debt entry.

Second-pass validation: **965 core passed, one optional skip; 366 Django passed,
one expected failure; 84 final SQL/lock controls passed**. Paired Due had
**1,364 passed, four expected failures** before its latest main merge.
The paired BE selection passed **2,093 cases with 70 expected failures and six
collection exclusions**. Final revision checks are published on the
[follow-up PR](https://github.com/gigaverse-app/pytest-obligation/pull/57/checks).
