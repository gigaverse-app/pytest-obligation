# Latest BE harness parity

Source: gigaverse-backend c64a0249f, following the earlier 04786fb2d port.

- [ ] Owed-row fault controls: reject a row hidden by a failing delivery unless termination or a gapless retry budget is proven; reject a still-owed oracle that cannot distinguish a served row.
- [ ] Retry applicability: inspect real Django selections, including negated and nested predicates, and reject a false profile-J NotApplicable declaration.
- [ ] Debt collection: opt-in application-owned baseline rejects added/stale strict expected failures and distinguishes binding debt from ticketed defects; preserve partial selection and xdist behavior.
- [ ] Source policy: observation equality helpers are not standalone proof declarations.
- [ ] Run core, real PostgreSQL integration and current Due conformance, including expected failing controls.
- [ ] Rehearse current BE declarations with installed packages and compare collected cases, outcomes and explicit debt with the local harness baseline.

Keep Django inspection in its integration, shared metadata and debt enforcement in the framework-free core, and application paths/tickets/baselines in BE. No production deployment or evidence transfer is performed by these package changes.
