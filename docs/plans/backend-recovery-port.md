# Recovery harness port (2026-10-11)

Port reusable conformance changes after backend f933d6075 through 04786fb2d,
while preserving the public ObligationContract API, Python 3.11, and the
framework-free core. Runtime work-table implementations and application-specific
registrations remain in the backend.

- [x] Port poison-row isolation and stop-request oracles, with healthy and faulty controls.
- [x] Generate native sweep and light-contract poison cases with specific legacy gap types.
- [x] Port database-legal owed-row edge cases through the Django integration,
      including related rows, delayed handoffs, and commit callbacks.
- [x] Port shared binding and handoff guard improvements where applicable.
- [ ] Exercise core, Django/PostgreSQL, Celery, compatibility, lint and types.
- [x] Document the source-to-public mapping and intentional backend-only exclusions.

No repository PR template was found. This is test-library work and requires no
backend deployment followups.

See [the port and migration guide](../recovery-edge-cases.md) for source mapping and explicit exclusions.
