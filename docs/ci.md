# CI selection and execution costs

Pull requests use pytest-selective's Python import graph plus consumer-owned lane
inputs in [test-lanes.json](../.github/test-lanes.json). Once a lane is affected,
CI runs its complete suite and existing evidence checks. It does not trim a
conformance suite to individual tests.

## Which changes run which checks?

| Change | Validation |
| --- | --- |
| Root/package README or prose in `package/docs/` | Local documentation links, CI routing contracts, lint, wheel/sdist build, strict metadata/Markdown validation, installed-package compatibility checks |
| Python source or tests | Import-dependent complete lanes, explicit integration inputs, and type checking |
| Demo recording tape/environment | Complete demo lane, including the executable GIF assertions |
| Adoption evidence validator | Its direct workflow consumers and Python-dependent guard tests |
| Published `check` action | Demo, Saleor, and example action lanes |
| Published `test` action | Example action lane |
| Lock files, project configuration, or GitHub workflow/configuration | All lanes |
| Main push, manual dispatch, `test:full` label, or missing history/planning proof | All lanes |

The build and lightweight documentation checks always run. The link checker
validates inline local Markdown file destinations, excluding fenced examples and
template substitution fields. It does not validate remote URLs, anchors, HTML,
or reference-style links. Twine validates both distribution descriptions, and a
separate check verifies that both archives contain the current package README.

Package implementation changes retain explicit compatibility coverage across
integrations, including Due's external checkout, whose tests are not present in
this repository's import graph. The shared Python graph remains responsible for
local dependencies. Do not replace these boundaries with a blanket `docs/**`,
`scripts/**`, or package README global trigger.

## Regression checks

`ci-contracts` installs the exact immutable selector revision used by the
workflow's action, resolved by `scripts/ci/selector_requirement.py`. It creates
real Git snapshots of this repository and verifies README/guide changes, demo
inputs, validator consumers, action consumers, Python changes, test deletion,
global environment changes, missing history, and explicit full checkpoints.
Failures block the PR; they must be fixed rather than bypassed with `test:full`.

The original upstream extraction preserved the selector implementation and
backend-common's historical aliases. The consumer configuration had separately
classified `package/README.md` and `package/docs/**` as global inputs. That policy
overrode dependency reachability. Algorithm tests alone did not exercise this
consumer's routing; these repository-level regression checks cover that gap.

## Measure before changing execution

Every CI run retains `test-lane-selection` with changed paths and the planning
reason. After completion, the separate `CI observability` workflow uses
[CI-esta](https://github.com/gigaverse-app/ci-esta) to retain
`ci-esta-<run-id>-<attempt>` artifacts with measured job/step durations, a slowest
step per job summary, versioned JSON and Prometheus metrics. The shared reporter
also distinguishes job admission delay and estimated rounded runner minutes.
Missing step times remain unavailable. Gate latency remains unassessed until
required gates are explicitly configured. Reporting adds no job to CI's
validation path and does not execute the observed PR's code.

The [pre-change run](https://github.com/gigaverse-app/pytest-obligation/actions/runs/39842526610)
used 1,735 summed runner-seconds for a README change. Its longest jobs were:

| Job | Job seconds | Longest step seconds |
| --- | ---: | ---: |
| Due | 362 | 249 (complete work-table/application conformance) |
| Saleor | 292 | 229 (checkout tests) |
| Demos | 268 | 118 (Wagtail tests) |
| Prefect | 151 | 138 (integration tests) |

These are one run's measured execution durations, not promised future timings.
Due and Prefect now print their slowest test durations, alongside the existing
Saleor/demo reports. Saleor's slow cases exercise repeated crash and recovery
histories; database services, cached migrations, complete profile checks, and
full-suite checkpoints remain intact. The first optimization is avoiding these
jobs for unrelated prose, without weakening what their passing result proves.
