// Maintained contract for profile B's reference owner (references/in_memory.py::InMemoryOwner).
// One row. A token is named by age: "last" is the most recently issued token,
// "previous" the one before it. The row's holder is the token that owns it, 0 when no one does.
module fenced_lease_fixed {
  type Row = { state: str, holder: int, lease: str }
  type View = { state: str, lease: str, accepted: bool }
  var row: Row
  var issued: int
  var event: { op: str, token: str }
  var observed: View
  var turns: int

  pure def tokenId(age: str, n: int): int = if (age == "last") n else n - 1

  action emit(after: Row, nextIssued: int, op: str, token: str, accepted: bool): bool = all {
    row' = after, issued' = nextIssued, event' = { op: op, token: token },
    observed' = { state: after.state, lease: after.lease, accepted: accepted }, turns' = turns + 1
  }

  action init = all {
    row' = { state: "READY", holder: 0, lease: "none" }, issued' = 0, turns' = 0,
    event' = { op: "init", token: "" }, observed' = { state: "READY", lease: "none", accepted: false }
  }

  // claim() takes a READY row, issues a fresh token and a live lease.
  action claim = all {
    turns < 8,
    if (row.state == "READY") emit({ state: "CLAIMED", holder: issued + 1, lease: "live" }, issued + 1, "claim", "", true)
    else emit(row, issued, "claim", "", false)
  }

  // Fault injection: the owner stopped renewing; the deadline is in the past.
  action expire = all { turns < 8, emit({ ...row, lease: "expired" }, issued, "expire", "", false) }

  // The reaper re-arms only an expired claim, and a re-armed row has no owner.
  action reclaim = all {
    turns < 8,
    if (row.state == "CLAIMED" and row.lease == "expired")
      emit({ state: "READY", holder: 0, lease: row.lease }, issued, "reclaim", "", true)
    else emit(row, issued, "reclaim", "", false)
  }

  // Owner-gated operations: accepted only with the holder's token.
  action owned(op: str, age: str, after: Row): bool = {
    val ok = tokenId(age, issued) > 0 and tokenId(age, issued) == row.holder
    all { turns < 8, if (ok) emit(after, issued, op, age, true) else emit(row, issued, op, age, false) }
  }
  action write = { nondet age = Set("last", "previous").oneOf() owned("write", age, { ...row, state: "RETRYABLE", lease: "none" }) }
  action retry = { nondet age = Set("last", "previous").oneOf() owned("retry", age, { state: "READY", holder: 0, lease: "none" }) }
  action release = { nondet age = Set("last", "previous").oneOf() owned("release", age, { state: "READY", holder: 0, lease: "none" }) }
  action renew = { nondet age = Set("last", "previous").oneOf() owned("renew", age, { ...row, lease: "live" }) }

  action step = any { claim, expire, reclaim, write, retry, release, renew }

  // A READY row has no owner, so no token can write it until the next claim.
  val contract = row.state != "READY" or row.holder == 0

  action inspect = all {
    row' = row, issued' = issued, turns' = turns, observed' = observed, event' = { op: "inspect", token: "" }
  }

  run reapedOwnerCannotWriteTest = init.then(claim).then(expire).then(reclaim).then(owned("write", "last", { ...row, state: "RETRYABLE", lease: "none" }))
    .then(all { assert(observed.state == "READY" and not(observed.accepted)), inspect })
  run reapedOwnerCannotRenewTest = init.then(claim).then(expire).then(reclaim).then(owned("renew", "last", { ...row, lease: "live" }))
    .then(all { assert(observed.lease == "expired" and not(observed.accepted)), inspect })
  run supersededOwnerCannotWriteTest = init.then(claim).then(expire).then(reclaim).then(claim)
    .then(owned("write", "previous", { ...row, state: "RETRYABLE", lease: "none" }))
    .then(all { assert(observed.state == "CLAIMED" and not(observed.accepted)), inspect })
  run currentOwnerWritesTest = init.then(claim).then(owned("write", "last", { ...row, state: "RETRYABLE", lease: "none" }))
    .then(all { assert(observed.state == "RETRYABLE" and observed.accepted), inspect })
  run liveLeaseBlocksReclaimTest = init.then(claim).then(reclaim)
    .then(all { assert(observed.state == "CLAIMED" and not(observed.accepted)), inspect })
}
