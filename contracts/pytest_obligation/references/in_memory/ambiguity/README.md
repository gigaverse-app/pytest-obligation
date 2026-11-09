# Ambiguity: profile C's reference machine

Profile C (crash ambiguity) judges how an adopter recovers a claim whose owner died mid-call,
through the proofs in [`crash_ambiguity.py`](../../../../../package/src/pytest_obligation/profiles/crash_ambiguity.py).
Those proofs are calibrated against a reference machine,
[`InMemoryMachine`](../../../../../package/src/pytest_obligation/references/in_memory.py), and the
broken variants in [`test_crash_ambiguity.py`](../../../../../package/tests/core/profiles/test_crash_ambiguity.py).
This contract states what the reference must do and replays generated histories through it.

[model.qnt](model.qnt) models one claimed row: whether an attempt is open, whether the lease
expired, and its state (`CLAIMED`, `READY`, `UNKNOWN`, `SENT`). [adapter.py](ambiguity_adapter.py)
drives the real `InMemoryMachine` and reads back the state, whether an attempt is open, and
whether the row is in `due_work_ids()`.

```sh
uv run --no-sync pytest -c contracts/quint.ini contracts/pytest_obligation/references/in_memory/ambiguity
```

## The bug this contract records

Settling an ambiguous row with late evidence also clears its open attempt. Before the fix, the
next reaper sweep saw a dead claim with no attempt and re-armed it `READY`, so an effect that
was already applied became due work and would be sent again. Invariant 6 ("settled work cannot
be resurrected") only re-applied evidence; it never ran the reaper on a settled row. The fix
leaves terminal rows alone, and invariant 6 now runs a sweep on the settled row.

## Planted bugs

- `shipped-9aa6ff2` runs [`history/resolve-9aa6ff2.py.txt`](history/resolve-9aa6ff2.py.txt), the pre-fix
  reaper copied verbatim from `9aa6ff2` and pinned by SHA-256 in `ambiguity_adapter.py`.
- `blind-retry` re-arms every dead claim, even one whose call may have applied.
- `ambiguous-redispatch` puts `UNKNOWN` rows in the due-work selection.

## Open questions this model does not decide

The reference also lets the reaper mark a claim with a **live** lease as `UNKNOWN`, and lets
late evidence settle a row that is still `CLAIMED`. Profile B has a "live lease blocks reclaim"
invariant; profile C has none. Whether either should be refused is a design decision, so the
model only runs the reaper on an expired lease and only applies evidence to an ambiguous or
settled row.
