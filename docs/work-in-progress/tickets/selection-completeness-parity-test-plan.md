# Current backend parity

Port backend #5350 provider helpers, #5351 selection-completeness proofs and #5332 unclean recovery observations. Keep generic Django proofs in pytest-obligation and runtime-bound discovery in Due.

- [x] Port and run real PostgreSQL controls for omitted own/related state branches, lying exclusions, broken ticks, deferred work and strict per-combination debt.
- [x] Preserve SQL-failure isolation, whitespace edges and lifecycle path behavior.
- [x] Exercise Due discovery through generated suites; run recovery metric controls for clean, failed, aborted and non-heartbeat ticks.
- [x] Run framework-free imports, lint, types and package suites.
- [x] Refresh BE baseline/public rehearsal at the pinned current main, compare identities/outcomes and document every change.

Production cutover remains separate from this harness and behavior parity work.

Local controls: 929 core passed (one optional skip), 364 Django passed (one declared xfail); Ruff and Pyrefly pass. SQL failure in a downstream Celery delivery failed before the host fix and passes after it. Both Django CI driver lanes install the opt-in exploration dependency.

BE fd921da14: 2,005 passing + 70 xfailed baseline outcomes preserved, with 15 additional passing public admission guards (2,020 passed). Both driver suites pass. Broader demo CI reproduced three additional upstream whitespace findings, now declared narrowly as strict gaps in Wagtail and Saleor.
