# pytest-obligation as a pytest plugin

pytest-obligation generates crash, retry, and recovery tests from a
`ObligationContract` bound to an application's production code. The generated
cases run alongside ordinary pytest tests, using the project's fixtures and
test services. The Claude/Codex skills help an agent create those bindings;
the Python package supplies the pytest integration and fault-injection engine.

## Install and discover

Migrating from `due-work-harness`? Follow the
[package migration guide](package-migration.md).
New code imports `pytest_obligation.ObligationContract`; the compatibility shim
preserves `due_work_harness.DueWorkContract` and existing pytest options.

Install in the Python environment that runs your application's tests:

```bash
pip install pytest-obligation
# Or choose your project's package manager:
uv add --dev pytest-obligation
poetry add --group dev pytest-obligation
```

Pytest automatically loads installed plugins registered in the `pytest11`
entry-point group. This distribution registers:

```toml
[project.entry-points.pytest11]
due_work_harness = "pytest_obligation.pytest_plugin"
```

Confirm the registration and available options:

```bash
pytest --trace-config --collect-only
pytest --help
```

If your environment disables plugin autoload, load it explicitly with
`pytest -p pytest_obligation.pytest_plugin`. To disable it, use `pytest -p no:due_work_harness`.
See [pytest's plugin-discovery documentation](https://docs.pytest.org/en/stable/how-to/writing_plugins.html#making-your-plugin-installable-by-others).

The PyPI metadata includes `Framework :: Pytest`, a pytest-focused summary and
keywords, and documentation/source/changelog links. The classifier helps people
and catalogs identify it as a pytest plugin; the entry point makes pytest load
it. Installing the plugin alone does not generate application tests: first
declare a contract and expose a class decorated with
`@due_work_contract_suite(CONTRACT)`. Follow the [adoption guide](adopting.md)
and [runnable example](https://github.com/gigaverse-app/pytest-obligation/blob/main/examples/adopter/README.md).

## Binding lifetimes

`pytest_obligation.helpers.Binding[T]` names a factory returning either a value
or a context manager yielding that value. `entered_binding` keeps that scope
alive through the proof and uses `proof_context` to preserve failures: cleanup
receives the original exception, but cannot turn a failed proof green by
suppressing it. Profile cases, handoff histories and Due's work-table bindings
share this entry path.

## Generated tests and selection

The contract decorator generates pytest cases at collection time, rather than
writing test source files. Applicable A–J profiles exercise lost messages,
worker deaths, uncertain external effects, competing results, replay, atomic
admission, and retry limits. New checks for an already-bound profile can extend
an existing suite after a package upgrade; new profiles or bindings require
assessment. See [the guarantee catalog](how-it-works.md#the-a-j-guarantees).

Generated cases carry the registered `due_work` marker. Optional generated
schedule searches also carry `due_work_exploration`:

```bash
pytest --collect-only -m due_work
pytest -m due_work --due-work-summary
```

Normal pytest selection, fixtures, JUnit reports, and CI runners still apply.
Summary and executed-profile reporting support pytest-xdist; findings recording
requires a single process.

### Recovery coverage without another test inventory

Profile A uses the existing `DueWorkSweep` product and poison bindings to test
a full failing page followed by healthy work. Each fault must fire; every tick
encountering a fault must report it, preserve what remains owed and reach healthy
work within two ticks. Once faults stop, failed work must progress. If retries
use backoff, bind `resume_recovery` to a test clock/eligibility control; it must
never perform a recovery transition or manufacture completion.

The plugin automatically checks all generated cases when a whole module/class
is collected. Removing a generated method or parameter fails collection even
without a reporting or verification flag. Explicit node-level selections remain
usable for debugging; `-k` and ordinary deselection operate after completeness
is checked. No adopter maintains a second list of required test names.

Runtime integrations use `pytest_obligation.recovery.validate_recovery_bindings`
with an independently obtained executable inventory, and
`assert_recovery_history` with product examples and runtime clock controls.
Due supplies its actual registered steps; it does not delegate discovery to
test authors. A generic opaque `run_tick` cannot reveal every internal loop:
the native proof covers its supplied per-identity seam, not undisclosed stages.
Prefer structured runtime registrations when extending a multi-step recovery.

## Options and reports

| Option | Behavior |
| --- | --- |
| `--due-work-summary` | Lists generated cases and a VERIFIED/UNVERIFIED contract verdict, with missing proofs and assessment reasons. Works without a JSON destination. |
| `--due-work-profile-report=profiles.json` | Writes declared, collected, selected, and executed A–J evidence, including setup/call/teardown results. |
| `--due-work-require-assessed` | Rejects unassessed profiles and convergence families before pytest filters cases. |
| `--due-work-verify` | Fails if a contract or exemption counted by the static handoff scan ran no case in this session. Requires scan configuration. |
| `--due-work-record-findings` | Prints observed history findings for review before pinning them. Run without xdist's `-n`; this mode records instead of checking declared findings tables. |
| `--due-work-explore=smoke` or `deep` | Enables additional Hypothesis schedule search; requires the `[exploration]` extra. |

Use `--junitxml=results.xml` for pytest's standard CI artifact. Known gaps are
strict XFAILs; `NotAssessed` records unfinished assessment. Neither is a verified
guarantee. The [green-result guide](what-a-green-result-means.md) explains the
scope of a pass and how to assess findings.

### Read the contract verdict

```bash
pytest tests/contracts --due-work-summary
# Parallel runs merge the same evidence in the controller:
pytest tests/contracts -n auto --due-work-summary --due-work-profile-report=profiles.json
```

The contract section names every profile, its assessment, and its passed/expected
behavioral proof count. It lists uncollected, deselected and incomplete proofs,
including setup, call and teardown outcomes. Convergence families have their own
assessment and reason. A passing known-gap probe or decline never verifies a claim.

`VERIFIED` requires at least one claimed profile, complete successful execution
of every claimed profile and its required families, and passing extra proofs and
assessment checks. Other profiles must be explicitly not applicable. A contract
with a known gap, decline or unfinished assessment remains `UNVERIFIED`. A failed
or deselected extra proof also blocks the contract verdict. The JSON report uses
the same `verified` value and includes these checks under `additional_cases`.

The scope is **collected contract suites**. This does not certify unimported
contracts, undeclared application behavior or untested schedules. Existing case
tallies describe individual execution outcomes; the contract verdict describes
the completeness of the evidence. Focused debugging runs keep their normal pytest
exit status even when the contract is unverified. For enforcement, use the existing
assessment and static-coverage policies above as appropriate.

### Diagnose a recovery failure

Recovery histories attach a `Recovery diagnostics:` JSON note to the original
exception. The note reports the stage (`arranging`, `control`, `poisoned`, `held`
or `resumed`), attempted ticks and each arranged candidate's identity, role,
cumulative fault count, last observed owed state and whether it ever progressed.
`observed_after_tick` shows when each product observation was made. A reporting
failure might stop a tick before observation; its earlier snapshot stays clearly
dated. `null` means that observation has not completed.

No extra recovery ticks or product observations run to construct this evidence.
The original exception type, traceback and cause remain intact, so a strict
known-gap classifier continues to match the same failure.

Runtime integrations can add retry eligibility or another useful detail to an
existing `RecoveryExample`:

```python
def retry_details(identity):
    state = read_retry_state(identity)  # Your read-only runtime observation.
    return {"retry_at": state.retry_at.isoformat(), "attempts": str(state.attempts)}


example = example.model_copy(update={"diagnose": retry_details})
```

`diagnose` is optional and returns a mapping of strings to strings. It runs only
on failure, once per candidate, after fault injection has ended. It must not run
recovery or mutate eligibility. Return only details safe to include in test logs.
A failed or invalid metadata callback records `diagnostic_error` for that candidate
without replacing the proof failure. These optional details are captured at failure
time; the core owed/progress fields retain their own observation timestamps.

## Host configuration

Configure the host appropriate to the real database or execution boundary in
`conftest.py`, as described in [integrations](integrations.md). Alternatively,
the plugin accepts a dotted path to a `Host` or a zero-argument host factory:

```toml
[tool.pytest.ini_options]
due_work_harness_host = "myapp.testing:make_due_work_host"
```

The host path is configured before collection and imported on the first host read
by a declaration or proof. A session containing only unrelated tests never imports
the application adapter; a missing or broken adapter still fails when required.
The application still supplies
production transitions, independent observations, and real recovery behavior.
The [handoff coverage scan](coverage.md) complements runtime proofs by finding
production handoffs that have not yet been accounted for.


### Application wrappers around suite decorators

A consumer that scopes its own manifest around a public generator can declare the
exact reviewed wrapper in `CoverageConfig.suite_aliases`, or in TOML:

```toml
[tool.due-work-harness.suite-aliases]
"app.tests.harness.effect_contract_suite" = "effect_contract_suite"
```

This is an explicit trust boundary for static handoff inventory. The wrapper must
call the named public generator and preserve its collection/outcome hooks; it
must not replace proof logic. Without this declaration, an application function
with the same name is rejected. The runtime suite guards still verify all generated
proofs; a static coverage declaration alone cannot certify execution.

### Generating additional contract cases

Integration authors can collect a `ContractCase` through
`case.parameter(transactional=True, gap=reason, raises=InvariantFailure)`.
`transactional=None` requests no database marks, `False` asks for the host's
ordinary database mode, and `True` asks for real commits. `gap=None` is an ordinary
case; a reason creates a strict expected failure, limited to `raises` when
supplied. A broken binding must not be hidden by an invariant-only gap. This
method preserves the case's ID and fixture declaration; ordinary adopters should
continue using contract decorators and `ExtraProof`.

## Validate fixtures before optional tests are skipped

`pytest --due-work-check-fixtures` resolves fixtures for every retained item at
collection time, including skipped external-provider tests. Missing fixture
imports therefore fail ordinary CI instead of waiting for the first opt-in run.
Direct parametrization is not mistaken for a fixture; indirect parametrization
must resolve one. Deselected tests are outside this run. Dynamic calls to
`request.getfixturevalue` remain runtime checks.

The check works with xdist: workers collect the same single failing diagnostic
item, so a missing fixture reports a normal failure rather than crashing worker
collection. The runnable catalog and upstream adopter CI enable this option.
