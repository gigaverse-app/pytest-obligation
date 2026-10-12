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
