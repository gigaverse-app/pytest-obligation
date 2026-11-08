# Maintained Quint contracts

Each `docs/quint/<topic>/manifest.json` registers a maintained contract: a current
`fixed.qnt` model, an immutable historical `audit.qnt` pinned by SHA-256, a driver
(`adapter.py`) that applies model events to the real production API and reads its
state back, and the declared witnesses, sampling bounds and mutation controls.
[pytest-quint-connect](https://github.com/gigaverse-app/pytest-quint-connect) runs
them as ordinary pytest cases from `verification_tests/quint/`:

```sh
uv run --no-sync pytest verification_tests/quint --quint-require-complete
```

| Topic | Implementation | Test |
| --- | --- | --- |
| [report-merge](report-merge/README.md) | `profiles.reporting.merge_reports` | [test_report_merge_contract.py](../../verification_tests/quint/test_report_merge_contract.py) |
| [fenced-lease](fenced-lease/README.md) | Profile B's reference `InMemoryOwner` | [test_fenced_lease_contract.py](../../verification_tests/quint/test_fenced_lease_contract.py) |

To register a topic, add its directory with an `adapter.py` exposing
`create(root, work, mutant)`, and a test module declaring
`quint_contract(manifest, driver="quint_adapter")`, which uses the shared fixture in
`verification_tests/quint/conftest.py`. Add the topic's name to `QUINT_REQUIRED_CONTRACTS`
in the `quint` job of `.github/workflows/ci.yml`, and its implementation sources to the
`quint` lane in `.github/test-lanes.json`. Review implementation, model, manifest and driver together
when registered behavior changes. Investigate mismatches; never weaken the
specification, drop a witness or accept a surviving mutation to make CI green. Keep
a conforming positive history and a known-bad semantic control for every topic.

These are bounded API-level refinement checks of declared serial histories. They do
not establish exhaustive safety, liveness, arbitrary concurrency or behavior outside
the registered projections; keep the existing pytest suites alongside them.
