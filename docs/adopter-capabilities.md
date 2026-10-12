# Where the shipped adopters exercise the capabilities

This is the adoption map for the generated capabilities ported in #34 and strengthened in #46. CI runs
these contracts with `--due-work-require-assessed` and uploads executed JSON
profile reports. CI also checks required adopter names and executed profiles
against those reports, so deleting a suite cannot leave an empty green report. The option rejects assessment debt before `-k`/marker filtering;
reports distinguish declarations, selected cases, actual outcomes and verification.
A Decline or known gap remains unverified. A report covers collected suites only.

| Adopter | New executable adoption | Scope and remaining guarantees |
| --- | --- | --- |
| [SQLite catalog](../examples/adopter/README.md) | G/H/I; E revisions, retirement, transport, receipts, batches, separate connections, retry turnover; optional Hypothesis and JSON replay | Full demonstration of the new engines on persisted application state; no periodic scheduler or lease claim |
| RQ integration | Same application bindings through Redis + SimpleWorker; H on the existing message job; G with one and two real dependencies | Message replay exposes duplicate sends as a strict gap; existing ownership/retry/crash findings remain pinned |
| Celery integration | Same application bindings through Redis and a real Celery solo worker; H on the existing message task | Deterministic interleavings do not claim broker scheduling; the existing prefork process suite checks actual worker deaths and callbacks |
| Prefect integration | Same bindings through the actual Prefect flow engine and isolated API server | Flow execution and application invariants; deployment delivery remains outside this local test |
| Django integration | I against real PostgreSQL atomic and nested transactions, split-commit negative controls | Shared SQL-boundary fault adapter never supplies a transaction or rollback |
| Procrastinate Django demo | I on the real create-book view; commit-death histories for index_book's follow-up admission | Split admission fails; the existing ATOMIC_REQUESTS variant passes. Existing H/J/B/D remain executable; no product readiness gate or mutable-result merge |
| DBOS transactional outbox | I on real order INSERT + SQL workflow enqueue; H on the actual notification step | Atomic admission passes; replaying the step duplicates the notification. Existing process deaths, D and J remain; no post-admission gate |
| Wagtail media | I on image/document deletion; H/J separately for image, document and feature detection; E on stale crop calculation | Product/task split commits and stale crop overwrite remain strict gaps; deletion is immediately eligible |
| Wagtail publishing | I on page publication; H/J on the real CDN purge task | Split commit is a strict gap; repeated invalidation is harmless; persistent CDN failure exhausts execution |
| Saleor checkout, both payment variants | H confirmation replay and executable I gap probes with real crash histories and confirmation observations | After-commit obligations lack durable admission. Automatic completion protects the paid order but still loses confirmation. No invented obligation before payment |
| Saleor payment reports | E charge/refund evidence, duplicate delivery, recovery, separate actors and optional Hypothesis; I commit interruption; overlapping request regression | Sequential evidence histories pass. Interrupted projection and overlapping aggregate writes leave incorrect money even after redelivery |
| MongoDB/Motor, aiokafka | Existing real-server driver/offset fault controls continue in CI | These are host/protocol controls, not application contracts. A driver cannot supply product intent, desired revisions, evidence or approval predicates; the application supplies those bindings |

Framework worker factories explicitly decline application-owned admission and
gating instead of inheriting unexplained `NotAssessed` placeholders. This does
not assert that RQ dependencies, Celery canvases or arbitrary user tasks are safe.
An application's contract can compose/override the worker declaration with its
own bindings, as the RQ and Celery message replay suites do.

G can be used with native recovery without claiming an A-style sweep. If A is
claimed, the additional G/A proof still requires the gate's recovery to dispatch
its identity through the contract's actual sweep. Existing negative controls
continue to reject an unrelated recovery implementation.

Application-specific E bindings cover Wagtail's stale snapshot and Saleor's
payment evidence. Other E families retain explicit reasons where the application
has no corresponding lifecycle. The catalog demonstrates the remaining generated
scenarios without claiming they prove an upstream application's behavior.

## Deeper application coverage

The follow-up extends executable guarantees, not just assessment rows:

- RQ dependency gates: one and two prerequisites, with real Redis job-write observation.
- Wagtail media: separate image/document/automatic-crop replay and service-failure limits;
  stale queued automatic crops versus newer editor choices (E).
- Wagtail publishing: real worker exhaustion when the CDN is unavailable (J).
- DBOS: actual notification-step replay (H), alongside existing real process-death histories.
- Procrastinate: index_book's follow-up admission now has commit-death histories and
  leaves the static scanner baseline.
- Saleor: both confirmation callbacks now have replay proofs; payment-event reports
  exercise charge/refund permutations, duplicate delivery, recovery and separate actors.
  Commit interruption and genuinely overlapping requests independently check the money projection.

Newly reproduced failures: Saleor retains a charge event but leaves the transaction
amount zero after a crash before projection; overlapping reports can overwrite a
newer aggregate, and identical redelivery repairs neither. Wagtail's queued detector
can overwrite a manual crop chosen after enqueue. These are strict expected failures
against the pinned upstream versions, not claims that the applications pass.

Named `replay` and `retry` bindings run every independent effect through the same
profile proofs. A passing image-delete test cannot stand in for document deletion
or automatic crop calculation. The existing singular factory form remains supported.


## Stronger bindings from #46

The stacked adopter change exercises the new surfaces where the application's
actual execution model supplies them:

| Adopter | Binding and observation | Result and limits |
| --- | --- | --- |
| Saleor automatic completion | `owed_model=Checkout`, the real completion task in `Lifecycle.execute`, captured Celery publications and bounded delivery of their follow-up tasks | Every database-legal checkout edge is delivered to the worker. Empty, whitespace-only and arbitrary three-character currencies remain selected after a money mismatch: three precise strict gaps. Other existing A findings remain. |
| Saleor related billing addresses | `ScheduledSelection` + `OwedRows` + `EdgeFamily(Address, edge_row=...)`, projected from the same sweep | Addresses are separate copies per checkout, so poisoning one cannot alter the healthy tail's address. Generated controls require successful service of the unmodified row and real dispatch order. |
| Saleor poison/stop | `still_owed` consumes the checkout identity and reads the actual production selection; `progressed` observes an order | A publication counter cannot substitute for completion in the native poison proof. The Beat publisher still abandons the tail on refusal; its soft time limit propagates. |
| Wagtail database worker | The real `Worker.run` selection at its claim boundary; `Worker.run_task`; task model edges; successful completion signals normalized to model UUIDs | Its READY partial index is verified against PostgreSQL's catalog. Ordinary receiver failure and an injected cooperative stop both make the task FAILED, outside recovery. Both are specific `[dropped]` gaps. Blank and maximum-length unconfigured queue names raise again during error reporting and abandon the healthy tail: two further edge-specific gaps. |
| SQLite catalog, including shared RQ/Celery/Prefect declarations | Standalone poison and stop oracles, provider faults, remote progress, SQL retention | These extras run the application recovery loop directly. They do not claim transport cancellation behavior. The stronger poison proof exposed an aborting loop; the example now isolates ordinary errors, reports an ExceptionGroup, and propagates cancellation immediately. |
| Optional noticeboard alert example | `LossDropsOnlyANotification` on a real SQLite producer and worker; a separate connection observes committed product state | The alert can be absent while the notice is complete; delivering it must send the alert and leave the notice unchanged. A worker that edits the notice fails the exemption. This policy does not exempt Saleor confirmations or DBOS notifications. |

The Wagtail query observer temporarily suppresses connection cleanup while
observing the query, because Django's plan tests hold an enclosing transaction.
Its executing worker keeps the production connection management, claim, and
signal behavior. The cooperative-stop case exercises exception handling; it is
not a test of the command's SIGINT/SIGTERM shutdown handler.

The existing Saleor host keeps general lifecycle-state proofs disabled. Its
`Lifecycle` binding supplies the real worker for owed-row checks; declaring it
here does not certify a complete checkout state machine.

Procrastinate's claim is a SQL procedure combining selection and acquisition;
it has no Django ORM job selector to bind to `EdgeFamily`. DBOS similarly owns
native workflow recovery rather than an application row sweep. Their existing
real-process admission, replay, retention and retry proofs remain applicable.
MongoDB/Motor and aiokafka remain driver/offset controls, without application
intent from which to derive row or notification contracts. None of those adapters
is made to invent product semantics merely to fill a capability column.

CI checks JUnit execution evidence for these exact classes and proof families
in addition to the A–J profile reports. Missing families, ordinary skips, failed
setup/teardown and failed proofs are rejected; strict expected failures remain
executed evidence, not passing guarantees. The catalog's mutation controls also
reject aborting the loop, deleting failed intent, swallowing the report, and
isolating cancellation as an ordinary failure.

The whitespace catalog also exposes django-tasks-db’s unconfigured-queue failure: a whitespace-only queue is selected, `InvalidTask` escapes after the claim, and error reporting abandons the healthy tail. These two cases remain separate strict gaps alongside the blank and maximum-length queue findings. The upstream demo CI reproduced all three new whitespace findings before the declarations were added; no production predicate, worker or oracle was changed.


## Independent replay outcomes

Every shipped replay binding declares `expected`, including Procrastinate indexing,
Wagtail deletion/crop/CDN effects, DBOS notifications, both Saleor confirmations,
RQ/Celery message tasks and the catalog shared across executors. Generated flat,
named and safety contracts require the outcome before running any replay proof.
Known duplicate-send gaps accept only a divergence after a correct first result.
CI requires every canonical replay case for each named demo effect, so removing
one binding or filtering a proof cannot leave a passing aggregate profile.

## Integration of the upstream parity changes (#57)

| Capability | Actual adopter evidence | Limits |
| --- | --- | --- |
| Failure-preserving binding scopes | The runnable SQLite catalog executes its generated H positive control through cleanup that swallows assertions. The real worker passes; changing `Catalog.execute` to a no-op still fails against the independent provider ledger. | The mutation control deliberately breaks application code; normal bindings still replace only external systems. |
| Canonical lifecycle paths and selected/skipped-row exploration | Wagtail's real database worker declares `status`, terminal exclusions and its fixed backend ownership. The proof executes actual task bodies and connection cleanup. | RUNNING tasks and four exact invalid-status edges have strict findings; this is evidence of defects, not a passing recovery guarantee. |
| Committing history isolation | Wagtail lifecycle histories run in autocommit; root controls retain an unrelated pre-existing row and require every proof-created row to disappear after both success and failure. | External effects remain owned by each binding's scope. |
| Collection-time fixture resolution, recovered in the third BE audit | Catalog and upstream-adopter CI enable `--due-work-check-fixtures`; subprocess controls cover skipped tests, direct/indirect parameters, deselection and real xdist workers. | Dynamic fixture lookup cannot be resolved before execution. |

The underlying production execution is shared with the existing provider,
process-death, retry and replay demonstrations. CI also requires the Wagtail
selection-completeness cases to appear in JUnit evidence; a missing or ordinary
skipped proof cannot preserve a coverage claim.
