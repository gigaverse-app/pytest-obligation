# Choose an application example

Start with an example whose failure boundary matches your application. Read its
production binding, independent outcome observation and declared gaps before
adapting the contract. A driver adapter alone cannot supply your product's intent.

## Capabilities in the example suites

These are examples exercised by the repository's integration and demo suites,
not certifications of the upstream projects. Known findings apply to the pinned
versions used by the demos; inspect the current declarations and reports when
changing versions.

| Adopter | Executable coverage | Scope and remaining guarantees |
| --- | --- | --- |
| [SQLite catalog](../examples/adopter/README.md) | G/H/I; E revisions, retirement, transport, receipts, batches, separate connections, retry turnover; optional Hypothesis and JSON replay | Demonstration of the engines on persisted application state; no periodic scheduler or lease claim |
| RQ integration | Same application bindings through Redis + SimpleWorker; H on the existing message job; G with one and two real dependencies | Message replay exposes duplicate sends as a strict gap; existing ownership/retry/crash findings remain pinned |
| Celery integration | Same application bindings through Redis and a real Celery solo worker; H on the existing message task | Deterministic interleavings do not claim broker scheduling; the existing prefork process suite checks actual worker deaths and callbacks |
| Prefect integration | Same bindings through the actual Prefect flow engine and isolated API server | Flow execution and application invariants; deployment delivery remains outside this local test |
| Django integration | I against real PostgreSQL atomic and nested transactions, split-commit negative controls | Shared SQL-boundary fault adapter never supplies a transaction or rollback |
| Procrastinate Django demo | I on the real create-book view; commit-death histories for index_book's follow-up admission | Split admission fails; the existing ATOMIC_REQUESTS variant passes. Existing H/J/B/D remain executable; no product readiness gate or mutable-result merge |
| DBOS transactional outbox | I on real order INSERT + SQL workflow enqueue; H on the actual notification step | Atomic admission passes; replaying the step duplicates the notification. Existing process deaths, D and J remain; no post-admission gate |
| Wagtail media | I on image/document deletion; H/J separately for image, document and feature detection; E on stale crop calculation | Product/task split commits and stale crop overwrite remain strict gaps; deletion is immediately eligible |
| Wagtail publishing | I on page publication; H/J on the real CDN purge task | Split commit is a strict gap; repeated invalidation is harmless; persistent CDN failure exhausts execution |
| Wagtail's Cloudflare backend | J classified failure on Wagtail's real `CloudflareBackend` over a faithful Cloudflare fake | A throttled purge ends SUCCESSFUL and is never retried (strict gap as shipped; the fixed control passes) |
| Saleor checkout, both payment variants | H confirmation replay and executable I gap probes with real crash histories and confirmation observations | After-commit obligations lack durable admission. Automatic completion protects the paid order but still loses confirmation. No invented obligation before payment |
| Saleor payment reports | E charge/refund evidence, duplicate delivery, recovery, separate actors and optional Hypothesis; I commit interruption; overlapping request regression | Sequential evidence histories pass. Interrupted projection and overlapping aggregate writes leave incorrect money even after redelivery |
| MongoDB/Motor, aiokafka | Existing real-server driver/offset fault controls continue in CI | These are host/protocol controls, not application contracts. A driver cannot supply product intent, desired revisions, evidence or approval predicates; the application supplies those bindings |

## Find and run the examples

- [SQLite catalog](../examples/adopter/README.md): start here for a small persisted
  application with explicit admission, effects and independent observations.
- [Upstream application demos](../demos/README.md): use the pinned Procrastinate,
  DBOS, Wagtail and Saleor applications to study framework-specific boundaries.
- [Framework integrations](../package/docs/integrations.md): choose the database,
  worker or driver adapter that exposes the failure you need to exercise.
- [Development setup](../CONTRIBUTING.md): install the relevant extras and services
  and run the chosen suite.

## Interpret a result before copying a binding

An executed strict expected failure documents a known defect; it is not a passing
guarantee. A decline or unassessed capability also remains unverified. Generated
reports distinguish declarations, selected cases, execution and verification.
Check the actual profile and JUnit artifacts for the revision you run.

Keep named effects independent. A passing image-deletion case cannot stand in
for document deletion or crop calculation. Replay bindings need an independent
`expected` outcome, and the first execution must produce that outcome before a
duplicate-delivery finding is meaningful.

Framework worker factories can decline application-owned admission or gating.
Your application must supply those bindings when it claims those guarantees.
Do not invent product state merely to fill a capability column: MongoDB and
aiokafka controls exercise driver and offset behavior, while your application
owns the business outcome.

Follow [what a green result means](../package/docs/what-a-green-result-means.md)
and [the harness guide](../package/docs/harness-guide.md) when adapting an example.
