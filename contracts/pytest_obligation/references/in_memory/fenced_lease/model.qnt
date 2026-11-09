/**
 * Fenced lease: profile B's reference owner.
 *
 * Models:  package/src/pytest_obligation/references/in_memory.py :: InMemoryOwner
 * Why:     the profile B proofs (profiles/bounded_ownership.py) are calibrated against this
 *          class. If it is wrong, every adopter with the same bug passes profile B.
 * Covers:  one row through claim, the reaper, and owner calls (write, retry, release, renew)
 *          carrying either the current token or the one before it.
 * Not:     several rows, a real clock, adopters' bindings (the proofs judge those).
 * Update:  whenever claim, reclaim, retry, release, renew or the token rule changes.
 *
 * Tokens are named by age: "last" is the most recently issued, "previous" the one before.
 * The row's holder is the token that owns it, 0 when no one does.
 */
module fenced_lease {
  type Row = { state: str, holder: int, lease: str }
  type View = { state: str, lease: str, accepted: bool }

  var row: Row          // model-only: holder is not observable through the public API
  var issued: int       // model-only: how many tokens claim() has issued
  var event: { op: str, token: str }
  var observed: View    // what the driver reads back after every step
  var turns: int

  pure val MAX_TURNS = 8
  pure def tokenId(token: str, n: int): int = if (token == "last") n else n - 1

  action emit(after: Row, nextIssued: int, op: str, token: str, accepted: bool): bool = all {
    row' = after, issued' = nextIssued, event' = { op: op, token: token },
    observed' = { state: after.state, lease: after.lease, accepted: accepted }, turns' = turns + 1
  }

  /// A fresh owner with one claimable row.
  action init = all {
    row' = { state: "READY", holder: 0, lease: "none" }, issued' = 0, turns' = 0,
    event' = { op: "init", token: "" }, observed' = { state: "READY", lease: "none", accepted: false }
  }

  /// Drives InMemoryOwner.claim(). Takes a READY row, issues a fresh token and a live lease.
  action claim = all {
    turns < MAX_TURNS,
    if (row.state == "READY") emit({ state: "CLAIMED", holder: issued + 1, lease: "live" }, issued + 1, "claim", "", true)
    else emit(row, issued, "claim", "", false)
  }

  /// Drives InMemoryOwner.expire_lease(row): fault injection, the owner stopped renewing.
  action expire = all { turns < MAX_TURNS, emit({ ...row, lease: "expired" }, issued, "expire", "", false) }

  /// Drives InMemoryOwner.reclaim_stalled(row), the reaper. Re-arms only an expired claim,
  /// and a re-armed row has no owner: the dead owner's token stops working right here.
  action reclaim = all {
    turns < MAX_TURNS,
    if (row.state == "CLAIMED" and row.lease == "expired")
      emit({ state: "READY", holder: 0, lease: row.lease }, issued, "reclaim", "", true)
    else emit(row, issued, "reclaim", "", false)
  }

  /// An owner-gated call: accepted only with the holder's token, and a refused call changes nothing.
  action owned(op: str, token: str, after: Row): bool = {
    val ok = tokenId(token, issued) > 0 and tokenId(token, issued) == row.holder
    all { turns < MAX_TURNS, if (ok) emit(after, issued, op, token, true) else emit(row, issued, op, token, false) }
  }
  /// Drives InMemoryOwner.fenced_write(row, token): the attempt is done, the row awaits a retry.
  action write(token: str): bool = owned("write", token, { ...row, state: "RETRYABLE", lease: "none" })
  /// Drives InMemoryOwner.fenced_retry(row, token): the attempt failed, the row goes back unowned.
  action retry(token: str): bool = owned("retry", token, { state: "READY", holder: 0, lease: "none" })
  /// Drives InMemoryOwner.release_unchanged(row, token): the owner steps aside, the row goes back unowned.
  action release(token: str): bool = owned("release", token, { state: "READY", holder: 0, lease: "none" })
  /// Drives InMemoryOwner.renew_lease(row, token): the owner's heartbeat.
  action renew(token: str): bool = owned("renew", token, { ...row, lease: "live" })

  action step = {
    nondet token = Set("last", "previous").oneOf()
    any { claim, expire, reclaim, write(token), retry(token), release(token), renew(token) }
  }

  // @invariant A READY row has no owner, so no token can write it until the next claim.
  val contract = row.state != "READY" or row.holder == 0

  /// A read-only step: final assertions emit it instead of repeating the last call.
  action inspect = all {
    row' = row, issued' = issued, turns' = turns, observed' = observed, event' = { op: "inspect", token: "" }
  }

  // WITNESSES
  //   reapedOwnerCannotWriteTest      the dead owner writes after the reaper, before anyone claims
  //   reapedOwnerCannotRenewTest      the dead owner renews after the reaper, before anyone claims
  //   supersededOwnerCannotWriteTest  the dead owner writes after another worker claimed the row
  //   currentOwnerWritesTest          the rightful owner's write is accepted (the fence is not a wall)
  //   liveLeaseBlocksReclaimTest      the reaper leaves a live claim alone
  run reapedOwnerCannotWriteTest = init.then(claim).then(expire).then(reclaim).then(write("last"))
    .then(all { assert(observed.state == "READY" and not(observed.accepted)), inspect })
  run reapedOwnerCannotRenewTest = init.then(claim).then(expire).then(reclaim).then(renew("last"))
    .then(all { assert(observed.lease == "expired" and not(observed.accepted)), inspect })
  run supersededOwnerCannotWriteTest = init.then(claim).then(expire).then(reclaim).then(claim).then(write("previous"))
    .then(all { assert(observed.state == "CLAIMED" and not(observed.accepted)), inspect })
  run currentOwnerWritesTest = init.then(claim).then(write("last"))
    .then(all { assert(observed.state == "RETRYABLE" and observed.accepted), inspect })
  run liveLeaseBlocksReclaimTest = init.then(claim).then(reclaim)
    .then(all { assert(observed.state == "CLAIMED" and not(observed.accepted)), inspect })
}
