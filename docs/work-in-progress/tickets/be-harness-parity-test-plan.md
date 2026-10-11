# Latest BE harness parity

Source: gigaverse-backend c64a0249f, following the earlier 04786fb2d port.

- [x] Owed-row fault controls: reject a row hidden by a failing delivery unless termination or a gapless retry budget is proven; reject a still-owed oracle that cannot distinguish a served row.
- [x] Retry applicability: inspect real Django selections, including negated and nested predicates, and reject a false profile-J NotApplicable declaration.
- [x] Debt collection: opt-in application-owned baseline rejects added/stale strict expected failures and distinguishes binding debt from ticketed defects; preserve partial selection and xdist behavior.
- [x] Source policy: observation equality helpers are not standalone proof declarations.
- [x] Run core, real PostgreSQL integration and current Due conformance, including expected failing controls.
- [x] Rehearse current BE declarations with installed packages and compare collected cases, outcomes and explicit debt with the local harness baseline.

Keep Django inspection in its integration, shared metadata and debt enforcement in the framework-free core, and application paths/tickets/baselines in BE. No production deployment or evidence transfer is performed by these package changes.

Validated locally: 906 core passes, one optional skip; 328 Django passes and one expected failure. Two PostgreSQL plan cases required disabling unavailable LLVM JIT on the isolated server; rerun separately.

All 20 CI checks pass, including all PostgreSQL plan checks, Python 3.11–3.14, minimum models, integration adopters, demos, types and build. Due companion full run: 1,256 passed, 4 explicit expected failures. BE work-table replacement: 1,340 passed and the same 6 expected failures; all 1,331 baseline outcomes preserved, with 15 additional passing admission-binding cases. Reproduction and the separate native/light comparison are in gigaverse-backend PR #5355.
