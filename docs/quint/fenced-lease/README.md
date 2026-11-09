# Fenced lease: profile B's reference owner

Profile B (bounded ownership) judges an adopter's claim, lease and fence against a set of
proofs in [`bounded_ownership.py`](../../../package/src/pytest_obligation/profiles/bounded_ownership.py).
Those proofs are calibrated against a reference owner,
[`InMemoryOwner`](../../../package/src/pytest_obligation/references/in_memory.py): it must
pass every proof, and each deliberately broken variant in
[`test_bounded_ownership.py`](../../../package/tests/core/profiles/test_bounded_ownership.py)
must fail exactly its own. This contract states what that reference is supposed to do,
independently of the proofs, and replays generated histories through the real class.

[fixed.qnt](fixed.qnt) models one row. A token is named by age: `last` is the most recently
issued, `previous` the one before. The row's holder is the token that owns it; a `READY` row
has none. [adapter.py](adapter.py) drives the real `InMemoryOwner` and reads back the row's
state, its lease (none, live or expired) and whether the last call was accepted.

```sh
uv run --no-sync pytest verification_tests/quint/test_fenced_lease_contract.py --quint-require-complete
```

## The bug this contract records

Before the fix, re-arming a row (`reclaim_stalled`, `fenced_retry`, `release_unchanged`)
returned it to `READY` but kept the previous owner's token until the next claim. A reaped
owner that woke up in that window could renew a lease on the `READY` row, or write it to
`RETRYABLE`, where neither `claim()` nor the reaper reaches it. The profile B proofs never
saw it: they always claimed the row again before trying the stale token. The fix drops the
token whenever a row returns to `READY`, and the two stale-token proofs now try the token in
both windows.

## Planted bugs

- `shipped-9aa6ff2` runs [`rearm-9aa6ff2.py.txt`](rearm-9aa6ff2.py.txt), the three pre-fix
  methods copied verbatim from `9aa6ff2` and pinned by SHA-256 in `adapter.py`. The
  manifest's `bugs_found` entry names it, so every history is replayed through it.
- `reaper-ignores-lease` re-arms a claim whose lease is still live.
- `unfenced-renewal` renews regardless of the token.

## Limits

One row, the reference's own non-advancing clock, and at most eight calls per history. This
contracts the reference, not an adopter's binding: adopters are judged by the proofs.
