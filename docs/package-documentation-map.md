# Documentation ownership

The package subtree includes the docs needed to change and operate the library. Repository guides and application showcases stay with their full checkout. Each document has one owner.

| Previous path | Canonical path | Owner |
| --- | --- | --- |
| `ADOPTING.md` | `package/docs/adopting.md` | Library API, guarantees, adoption or maintenance |
| `ARCHITECTURE.md` | `package/docs/architecture.md` | Library API, guarantees, adoption or maintenance |
| `docs/aiokafka.md` | `package/docs/aiokafka.md` | Library API, guarantees, adoption or maintenance |
| `docs/backend-harness-port.md` | `package/docs/backend-harness-port.md` | Library API, guarantees, adoption or maintenance |
| `docs/coverage.md` | `package/docs/coverage.md` | Library API, guarantees, adoption or maintenance |
| `docs/debt-baseline.md` | `package/docs/debt-baseline.md` | Library API, guarantees, adoption or maintenance |
| `docs/false-greens.md` | `package/docs/false-greens.md` | Library API, guarantees, adoption or maintenance |
| `docs/harness-guide.md` | `package/docs/harness-guide.md` | Library API, guarantees, adoption or maintenance |
| `docs/how-it-works.md` | `package/docs/how-it-works.md` | Library API, guarantees, adoption or maintenance |
| `docs/integrations.md` | `package/docs/integrations.md` | Library API, guarantees, adoption or maintenance |
| `docs/interleavings.md` | `package/docs/interleavings.md` | Library API, guarantees, adoption or maintenance |
| `docs/jepsen-analogy.md` | `package/docs/jepsen-analogy.md` | Library API, guarantees, adoption or maintenance |
| `docs/mongodb.md` | `package/docs/mongodb.md` | Library API, guarantees, adoption or maintenance |
| `docs/package-migration.md` | `package/docs/package-migration.md` | Library API, guarantees, adoption or maintenance |
| `docs/prefect.md` | `package/docs/prefect.md` | Library API, guarantees, adoption or maintenance |
| `docs/pytest-plugin.md` | `package/docs/pytest-plugin.md` | Library API, guarantees, adoption or maintenance |
| `docs/recovery-edge-cases.md` | `package/docs/recovery-edge-cases.md` | Library API, guarantees, adoption or maintenance |
| `docs/selection-completeness.md` | `package/docs/selection-completeness.md` | Library API, guarantees, adoption or maintenance |
| `docs/source-policies.md` | `package/docs/source-policies.md` | Library API, guarantees, adoption or maintenance |
| `docs/what-a-green-result-means.md` | `package/docs/what-a-green-result-means.md` | Library API, guarantees, adoption or maintenance |

Root `README.md`, contributor/release guides, project plans and demo-specific documentation remain outside the package. `package/README.md` is the library entry point; it links to the public showcase instead of duplicating it.

The package-local [development guide](../package/docs/development.md) owns reusable test commands and the source/split/export model. Full application integration proofs stay in `integration_tests/`; their fixtures are colocated there when they depend on demo applications.
