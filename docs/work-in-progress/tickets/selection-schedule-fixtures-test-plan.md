# Scheduled-selection fixture propagation

The generated schedule-evidence case omitted declared fixtures. A real Shopify
binding therefore raised `LookupError` before reaching its Prefect deployment
check, even though the selection/index cases initialized the same resources.

- [x] Reproduce through the real pytest suite generator with serial and xdist runs.
- [x] Forward the existing fixtures to schedule evidence and declared absence cases.
- [x] Verify a valid fixture-backed schedule passes and a missing schedule still fails.
- [x] Run core contract/report checks: 239 pass, including serial/xdist reporting.
- [x] Actual Shopify, retained MongoDB/Kafka and cache-exemption suite: 307 passed,
  16 strict expected failures for existing application behavior. All seven declared
  suites appear in the report; the schedule evidence now passes.

No new API, application behavior, batching policy or Due runtime mode is introduced.

The conforming schedule failed with `LookupError` before the fix in both serial
and two-worker execution. The missing-schedule control still fails its actual
assertion after fixture initialization. Ruff, Pyrefly and diff checks pass.
