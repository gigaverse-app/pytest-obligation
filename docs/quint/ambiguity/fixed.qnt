// Maintained contract for profile C's reference machine (references/in_memory.py::InMemoryMachine).
// One claimed row. The reaper runs only on an expired lease, and late evidence arrives only for an
// ambiguous or settled row: what should happen outside those cases is an open design question,
// so this model does not decide it.
module ambiguity_fixed {
  type Row = { state: str, attempt: bool, expired: bool }
  var row: Row
  var event: { op: str }
  var observed: { state: str, attempt: bool, due: bool }
  var turns: int

  action emit(after: Row, op: str): bool = all {
    row' = after, event' = { op: op }, turns' = turns + 1,
    observed' = { state: after.state, attempt: after.attempt, due: after.state == "READY" }
  }

  action init = all {
    row' = { state: "CLAIMED", attempt: false, expired: false }, event' = { op: "init" }, turns' = 0,
    observed' = { state: "CLAIMED", attempt: false, due: false }
  }

  // The attempt is recorded before the provider call, while the row is claimed.
  action startAttempt = all { turns < 8, row.state == "CLAIMED", emit({ ...row, attempt: true }, "startAttempt") }

  action expire = all { turns < 8, emit({ ...row, expired: true }, "expire") }

  // The reaper: a dead claim with an open attempt is ambiguous, one without is safe to run again,
  // and settled work stays settled.
  action resolve = all {
    turns < 8, row.expired,
    if (row.state == "SENT") emit(row, "resolve")
    else if (row.attempt) emit({ ...row, state: "UNKNOWN" }, "resolve")
    else emit({ ...row, state: "READY" }, "resolve")
  }

  // Late provider evidence settles ambiguity; re-applying it changes nothing.
  action evidence = all {
    turns < 8, row.state == "UNKNOWN" or row.state == "SENT",
    emit({ ...row, state: "SENT", attempt: false }, "evidence")
  }

  action step = any { startAttempt, expire, resolve, evidence }

  // An effect that may have been applied is never ordinary due work, and settled work is final.
  val contract = (row.state != "UNKNOWN" or not(observed.due)) and (row.state != "SENT" or not(observed.due))

  action inspect = all { row' = row, turns' = turns, observed' = observed, event' = { op: "inspect" } }

  run settledStaysSettledTest = init.then(startAttempt).then(expire).then(resolve).then(evidence).then(resolve)
    .then(all { assert(observed.state == "SENT" and not(observed.due)), inspect })
  run deadClaimWithAttemptIsAmbiguousTest = init.then(startAttempt).then(expire).then(resolve)
    .then(all { assert(observed.state == "UNKNOWN" and not(observed.due)), inspect })
  run deadClaimWithoutAttemptIsRetriedTest = init.then(expire).then(resolve)
    .then(all { assert(observed.state == "READY" and observed.due), inspect })
  run evidenceIsIdempotentTest = init.then(startAttempt).then(expire).then(resolve).then(evidence).then(evidence)
    .then(all { assert(observed.state == "SENT"), inspect })
}
