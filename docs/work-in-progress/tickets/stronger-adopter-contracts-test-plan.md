# Stronger adopter contracts (stacked on #46)

Audit every example/demo and framework-backed adopter for the capabilities added
in #46. Bind real production seams, run generated histories, and record specific
observed defects without changing pinned upstream applications.

- [ ] Saleor: owed checkout model, real worker/handoff outcomes, poison/stop,
      and any suitable selection-only loops, with exact legacy edge gaps.
- [ ] Procrastinate: recovery/admission and production selectors; use owed-row
      declarations where its actual loop supports them.
- [ ] Wagtail/django-tasks-db: production worker selection and outcomes, related
      payload values, poison/stop or explicit inapplicability.
- [ ] DBOS: assess new capabilities against the actual workflow recovery;
      preserve real-process evidence and avoid inventing a row sweep.
- [ ] Catalog example and Redis/Celery/Prefect/MongoDB/Kafka adopters: stronger
      semantic bindings where applicable; preserve non-Django contracts.
- [ ] Demonstrate new cases reject a faulty production seam; keep all existing
      findings and positive controls intact.
- [ ] Update adopter capability docs and CI evidence requirements, then run
      relevant local suites, types/lint, and the full CI matrix.

No PR template exists. Test/adopter changes require no deployment followups.
