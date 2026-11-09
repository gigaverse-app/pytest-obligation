# CI selection and execution costs

Pull requests plan lanes with [CI-esta](https://github.com/gigaverse-app/ci-esta)'s
`plan-work`. The lanes are the names the jobs' conditions read, and a change selects
a lane through what its jobs run: pytest-selective's Python import graph, the files
tests declare they read (`<test>.gv-dependency.yaml` sidecars and
`# gv:test-dependency:` comments), the Node tests' module graph, the files the wheel
contains, and the scripts and local actions each job executes.
[test-lanes.json](../.github/test-lanes.json) extends that with only what the graphs
cannot see. Once a lane is affected, CI runs its complete suite and existing evidence
checks. It does not trim a conformance suite to individual tests.

## Which changes run which checks?

| Change | Validation |
| --- | --- |
| Root README, `docs/` prose, the Read the Docs site (`documentation/`, including its requirements files, `mkdocs.yml`), example READMEs or `package/docs/` | Local documentation links, lint and the documentation site build; no tests, builds or smoke checks unless a test declares the document |
| Package README or LICENSE (embedded in the distributions) | Package lane: wheel/sdist build, Twine and metadata validation, installed-wheel smoke |
| Python source or tests | Complete lanes whose tests import the change, the jobs that run it, and type checking for every file in `[tool.pyrefly].project-includes`. The pytest plugin (`pytest_obligation.pytest_plugin`) is the package's `pytest11` entry point: pytest loads it into every session, so a change to it or to anything it imports starts every test lane, while a framework integration starts only the lanes that import it. Package source also runs the wheel build and Due's conformance, which install the wheel |
| Demo recording tape/environment | Complete demo lane, including the executable GIF assertions |
| Adoption evidence validator | Its direct workflow consumers and Python-dependent guard tests |
| Published `check` action | Demo, Saleor, and example action lanes |
| Published `test` action | Example action lane |
| Lock files, project/pytest configuration, `.python-version`, the planner job or the lane file | All lanes |
| A job in `ci.yml` | The lanes that job runs; a comment changes nothing |
| Publisher container requirements (`publish/requirements.txt`) | Action and contract lanes |
| Ordinary main push | Affected lanes, including zero runtime tests for unrelated prose |
| Manual dispatch, rerun, `test:full` label, or missing history/planning proof | All lanes |

The selector's shared `full: auto` policy owns event decisions. The workflow no
longer copies an expression that can omit reruns or future safety fixes. Override
with `full: 'true'` for a checkpoint or `full: 'false'` for a deliberate selective
experiment; missing-history fallback still runs every lane. The default base is
the PR base or push's previous commit. See the
[staged adoption checklist](https://github.com/gigaverse-app/ci-esta/blob/main/docs/tutorials/adoption-checklist.md)
for additional capabilities and their opt-in boundaries. Retained timing history
stays off here: whole-lane conformance uses the existing matrix/xdist strategy,
and a scheduling change needs measurements first.

Only planning, lint, `ci-esta check-workflow`, the local link check, the
documentation site build and the `Validation gate` run on every PR. The link checker
validates inline local Markdown file destinations, excluding fenced examples and
template substitution fields. It does not validate remote URLs, anchors, HTML,
or reference-style links. The `build` job follows the `package` lane: package
sources, `package/README.md` and `package/LICENSE` (pyproject's `readme` and
`license-files`), the metadata checker, and global lock/configuration inputs.
There, Twine validates both distribution descriptions, and a separate check
verifies that both archives contain the current package README.

CI-esta's built-in `python-environment` rule treats any `*requirements*.txt` as a
test environment, which would make a Read the Docs dependency bump run every lane.
The lane file therefore replaces that rule with this repository's environment files:
every `pyproject.toml`, `uv.lock` and pytest configuration, `.python-version`, and
alternate installer files at the root or in `package/`. `documentation/` is not
among them; the documentation workflow installs its requirements itself.
`publish/requirements.txt` is the publisher container's, so it runs the jobs that
build that container.

Package implementation changes retain explicit compatibility coverage across
integrations, including Due's external checkout, whose tests are not present in
this repository's import graph. The shared Python graph remains responsible for
local dependencies. Do not replace these boundaries with a blanket `docs/**`,
`scripts/**`, or package README global trigger.

## Regression checks

`ci-contracts` installs the CI-esta revision the workflow's `plan-work` action
uses, resolved by `scripts/ci/selector_requirement.py`, and Bun for the Node tests'
module graph, as `plan-work` has. It creates
real Git snapshots of this repository and verifies README/guide changes, a
documentation-only commit (including `documentation/requirements.txt`) that
selects no lane, package-distribution inputs, demo inputs, validator consumers, action consumers, Python changes, test deletion,
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
