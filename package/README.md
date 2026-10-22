# pytest-obligation

Executable contracts for durable work: bind real selection, execution and independent observations to reusable failure/recovery proofs. This directory is the editable library imported by application repositories.

- [Adoption guide](docs/adopting.md)
- [Architecture and guarantees](docs/architecture.md)
- [Pytest plugin](docs/pytest-plugin.md)
- [Writing bindings](docs/harness-guide.md)
- [Interpreting a green result](docs/what-a-green-result-means.md)
- [Public applications and demos](https://github.com/gigaverse-app/pytest-obligation#readme)

The [full repository](https://github.com/gigaverse-app/pytest-obligation) owns demo dependencies, integration tests and release workflows. The library source, controls and maintenance documentation live here.

[Local development, package tests and bidirectional subtree sync](docs/development.md).

## Use the projects together

[![Durable runtime: Due](https://img.shields.io/badge/durable_runtime-Due-0F766E)](https://github.com/gigaverse-app/due)
[![Recovery proofs: pytest-obligation](https://img.shields.io/badge/recovery_proofs-pytest--obligation-7C3AED)](https://github.com/gigaverse-app/pytest-obligation)
[![Test selection: pytest-selective](https://img.shields.io/badge/test_selection-pytest--selective-2563EB)](https://github.com/gigaverse-app/pytest-selective)

[Due](https://github.com/gigaverse-app/due) provides durable Django/PostgreSQL
execution and recovery. pytest-obligation can exercise that runtime or other
application workflows through explicit contract bindings.
[pytest-selective](https://github.com/gigaverse-app/pytest-selective) plans affected
tests before application startup. For conformance suites, select the complete
lane so its collection and evidence checks remain intact; retain full-suite
checkpoints.

The harness does not require Due or the selector. Its core and pytest-selective
support Python 3.11+; Due requires Python 3.14+. Use a planner interpreter that
understands your source syntax; planning can run separately from tests.
See [Due's binding guide](https://github.com/gigaverse-app/due/blob/main/package/docs/conformance.md)
and [whole-lane action](https://github.com/gigaverse-app/pytest-selective/tree/main/.github/actions/plan-lanes).

<!-- CI selection benchmark: package documentation only. -->
