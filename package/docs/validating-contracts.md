# Validate the contract before claiming coverage

A fault reaching production does not prove that your observation can see its
consequences. Start with one user-visible obligation and name the bad outcomes
you intend to distinguish: lost work, duplicate effects, contradictory success
and failure notifications, premature completion, or exhausted retries.

For each claim, record:

| Claim | Independent observation | Deliberate bad behavior | Expected diagnostic |
| --- | --- | --- | --- |
| An email is sent once | Provider inbox keyed by the logical message | Disable deduplication | Duplicate delivery |
| Completion is truthful | Stored status **and** success/error events for each participant | Revert the success guard | Changed pinned outcome |
| Retry eventually settles work | Outstanding obligation and provider receipt | Disable the production recovery tick | Work remains owed |

Use stable logical identities, not random task IDs or timestamps. Aggregate
success can hide a participant's false failure. A count can hide one missing
effect and another duplicated effect. A table copied from today's observations
is a regression baseline; it is not an independent specification of correctness.

## Check the detector in both directions

`pytest_obligation.regression_controls.assert_detects_regression` runs a check
on the working baseline, then inside a context that introduces a regression:

```python
from pytest_obligation.regression_controls import assert_detects_regression

assert_detects_regression(
    check_delivery,  # Arrange fresh work, execute production, inspect effects.
    regression=deduplication_disabled,  # Context manager; restores behavior.
    match="duplicate delivery",  # The specific expected behavioral assertion.
)
```

The context must change the production path or an external dependency. Leave
the observer, expected result, and pinned findings unchanged. A reverted fix is
particularly useful when you claim to guard that fix. The helper accepts only
the matching assertion from the check; setup, cleanup and unrelated exceptions
propagate. Do not catch every failure and label it a reproduced bug.

For a contract with known gaps, use `assert_pinned_process_outcomes` or
`assert_pinned_outcomes` as the check. They pass when the existing findings stay
unchanged and fail when the deliberate regression changes a row. An unchanged
aggregate XFAIL is not evidence of regression detection. Run with the expected
failure marker removed when checking a newly reported defect's exact reason.

This control proves sensitivity to the behavior you introduced, not every
possible implementation defect. If a proposed control is invisible, improve
the observation, choose a control for the actual claim, or narrow the claim.
Do not silently bless the new result by regenerating the findings table.

## Own destructive test resources

Prefer the target project's disposable fixtures. For Redis, the library offers
`pytest_obligation.integrations.redis_server.redis_server`, a context manager
yielding a fresh Redis URL and stopping that process on exit. It requires the
Redis extra, a local `redis-server`, and POSIX. It never reuses a default URL.

For subprocesses or a whole pytest session:

```bash
python -m pytest_obligation.integrations.redis_server -- pytest path/to/contracts
```

This supplies `REDIS_URL` and a separate `CELERY_OWN_BROKER_URL` for server-wide
faults. It clears inherited Celery endpoint overrides so the test application
can derive separate worker databases from `REDIS_URL`. Tests must use these
endpoints. It is not a sandbox for code that ignores
them. The package's destructive self-tests refuse an ordinary direct invocation
unless `REDIS_URL` and `PYTEST_OBLIGATION_REDIS_RESET=1` explicitly authorize a
dedicated test server. Never infer ownership from localhost or a high database
number. Namespaced keys do not isolate server-wide configuration changes.

## Report what ran

- `DECLARED` rows document exclusions without executing behavioral checks.
  They remain visible in the terminal and are skipped with a reason in JUnit.
  A decline with a real `prove` callback still executes and can fail.
- `--due-work-summary` includes each completed history stage's comparison:
  baseline, matching outcome, pinned divergence, changed outcome, or unreached
  fault. These are diagnostic rows, not additional passing tests. The same
  metadata travels through xdist and JUnit without serializing product values.
- Distinguish passing checks, known gaps, declarations, selection omissions,
  and environment failures. Include the command, exact revision, dependency
  versions, and the baseline/regression comparison supporting each claim.

The repository's `scripts/check_celery_regressions.py` demonstrates the method
with real workers and Redis. It pins Celery, reverses #10752 and #10759
individually, and compares the old observer with the corrected one. It does not
claim to validate Redis chord deduplication (#10919), which needs its own
duplicate-header control and observation.
