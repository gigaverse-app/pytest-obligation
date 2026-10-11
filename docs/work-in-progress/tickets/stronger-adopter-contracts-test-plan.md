# Stronger adopter contracts (stacked on #46)

Audit every example/demo and framework-backed adopter for the capabilities added
in #46. Bind real production seams, run generated histories, and record specific
observed defects without changing pinned upstream applications.

- [x] Saleor: owed checkout model, real worker/handoff outcomes, poison/stop,
      and any suitable selection-only loops, with exact legacy edge gaps.
- [x] Procrastinate: recovery/admission and production selectors; use owed-row
      declarations where its actual loop supports them.
- [x] Wagtail/django-tasks-db: production worker selection and outcomes, related
      payload values, poison/stop or explicit inapplicability.
- [x] DBOS: assess new capabilities against the actual workflow recovery;
      preserve real-process evidence and avoid inventing a row sweep.
- [x] Catalog example and Redis/Celery/Prefect/MongoDB/Kafka adopters: stronger
      semantic bindings where applicable; preserve non-Django contracts.
- [x] Demonstrate new cases reject a faulty production seam; keep all existing
      findings and positive controls intact.
- [x] Update adopter capability docs and CI evidence requirements, then run
      relevant local suites, types/lint, and the full CI matrix.

No PR template exists. Test/adopter changes require no deployment followups.


Implementation: Saleor binds native checkout edges, related billing-address
edges, actual Celery handoffs, identity-specific retained work and order progress.
Wagtail binds its real database polling loop and task model edges. Both preserve
pinned upstream code and use precise observed gaps. The shared catalog declaration
adds direct application-loop poison/stop proofs; its aborting recovery loop was
caught and fixed. A separate SQLite noticeboard exercises optional-notification
exemption with independent committed-state reads and a product-mutating-worker
negative control.

Procrastinate, DBOS, MongoDB/Motor and aiokafka were audited; their existing native
claims/process/driver paths do not expose an application Django row sweep or an
optional-notification policy. The capability map records why those new bindings
would be inappropriate, without weakening their existing suites.

Local red evidence: catalog poison stalled the healthy tail; Saleor blank and
maximum-length currency edges repeatedly failed completion; Wagtail poisoned and
interrupted tasks became FAILED and left automatic recovery. Guards caught two
binding mistakes during adoption (UUID normalization and a test-authored ORM
filter), both fixed rather than exempted. The READY partial index is now named
for catalog-backed verification, not declared as an index defect.

Validation includes strict positive controls, four broken catalog-loop mutations,
a notification worker changing product state, and CI evidence guard mutations
for missing, filtered, skipped and failed cases. Final CI results are recorded on
PR #47; the PR remains stacked on #46.
