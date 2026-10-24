# Bind fact-derived fixed effects

Account cleanup explicitly declines F because its effect is deletion, with no
changeable desired payload. That is a missing test-binding capability, not a
reason to abandon discovery and idempotence checks for the whole profile.

- [x] Reproduce the missing binding shape and generated contract support.
- [x] Add a fixed-effect binding reusing the common derivation/settlement guards.
- [x] Prove unrecorded discovery, unchanged derivation, stopped-work exclusion,
  and settlement that stays settled; do not claim desired-value supersession.
- [x] Preserve the existing mutable-state proofs and A/F composition.
- [x] Bind actual backend cleanup through production selection and service calls.
- [x] Use broken controls and real PostgreSQL verification; keep product fixes out.

No Due runtime or batching API is involved.

Validation: 1,295 core tests pass with one existing optional skip; the ten new
fixed-effect controls cover both materialising and selection-only implementations,
missing admission, unfinished/revived settlement, contradictory declarations and
missing recovery selection/dispatch. The old mutable-state controls remain green.
Public Pyrefly reports zero errors. The real backend cleanup/retention/retry/
selection run passes 97 cases with two existing strict expected failures (the
index plan and stale-selection retry-budget race). Both new production-seam
negative controls pass; no product behavior was changed.
