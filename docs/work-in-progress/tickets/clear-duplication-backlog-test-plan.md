# Clear the accepted duplication backlog

The accepted backlog started with 32 remaining pairs and eight previously cleaned pairs.
The complete strict sweep now reports zero duplicates: 31 more accepted pairs are cleaned,
one is explicitly dismissed, and zero remain. The baseline keeps its original 40 entries;
no detection threshold, include/exclude scope or accepted allowance was widened.

The dismissed pair has independent transaction policies: handoff ownership requires resolved
Django `atomic`, while publication reach recognizes arbitrary `.atomic` scopes and configured
openers. Other narrow distinctions preserve binding guards versus state-changing contract
proofs, keyed versus unkeyed replay controls, and SQL membership versus expression rewriting.

## Shared owners

- Python source walking, imports and names: `_internal/python_source.py`; project re-exports
  resolve through `Project.resolve`.
- Selection identities and gap grammar: `selection.py`; Django queryset validation and row
  reads stay in the integration.
- Commit counting, fencing, death cleanup and reply-breaker lifetimes: `worker_death.py`,
  used by the ledger, Django, Redis, MongoDB and aiokafka adapters as appropriate.
- Reference recovery ordering: `references/recovery.py`, with the database clock supplied by
  the adapter. Poison isolation shares one oracle with an explicit later-poll backoff option.
- Balanced SQL groups and temporary model-table ownership reuse their existing owners.
- Metadata validation retains the stronger positive/negative Unicode test; the redundant
  README-equality test is removed.

See [architecture](../../../package/docs/architecture.md#shared-analysis-and-fault-policy)
for the ownership boundaries. This count includes pairs removed or judged separate by the
sweep; it does not claim 31 independent refactorings.

## Validation

The full local core suite passed (1,621 passed, two expected skips), as did the PostgreSQL
suite (486 passed, one expected xfail). After the final extractions, coverage/inventory
passed 190 tests, crash/gap controls passed 59 tests, and the full PostgreSQL suite passed
again. Ruff and Pyrefly on modified sources pass. Existing controls exercise callback removal,
post-death fencing, lost-reply identity, import resolution, SQL parsing, selection grammar,
ordered/bounded identities, and healthy progress during poison backoff.

The complete sweep evaluates 613 candidate pairs: 99 resolved by rules and 514 judged or
reused from the verdict cache, with zero reported duplicates. Repeating the ratchet leaves
baseline, progress and README bytes unchanged and makes no new judge calls.

[PR #206](https://github.com/gigaverse-app/pytest-obligation/pull/206) carries current-head CI,
including real Redis, MongoDB and Kafka integration lanes. The final handoff requires these
checks and the required validation gate to pass. Full audit output belongs in CI artifacts,
not in this repository.
