// Maintained API-boundary contract. event drives actual merge_reports;
// observed is compared with the real SuiteCoverage/CaseEvidence projection.
module report_merge_fixed {
  type Evidence = { setup: int, call: int, teardown: int, bad: bool, selected: bool, collected: bool, durationTicks: int, failureCount: int }
  type Observation = { mainFirst: Evidence, mainSecond: Evidence, laterFirst: Evidence,
    laterSecond: Evidence, extraFirst: Evidence, extraSecond: Evidence,
    extraExists: bool, rejected: bool, identityRetained: bool,
    mainVerified: bool, laterVerified: bool, extraVerified: bool }
  var event: { op: str, mismatch: str, location: str, payload: str }
  var observed: Observation
  var turns: int
  pure val empty = { setup: 0, call: 0, teardown: 0, bad: false, selected: false, collected: false, durationTicks: 0, failureCount: 0 }
  pure val passed = { setup: 1, call: 1, teardown: 1, bad: false, selected: true, collected: true, durationTicks: 3, failureCount: 0 }
  pure def completed(e: Evidence): bool = e.selected and e.collected and not(e.bad) and e.setup > 0 and e.setup == e.call and e.call == e.teardown
  pure def evidence(payload: str): Evidence = { ...passed,
    teardown: if (payload == "incomplete") 0 else 1, bad: payload == "failed", durationTicks: if (payload == "incomplete") 2 else 3,
    failureCount: if (payload == "failed") 1 else 0 }
  pure def accumulated(old: Evidence, incoming: Evidence): Evidence = {
    setup: old.setup + incoming.setup, call: old.call + incoming.call,
    teardown: old.teardown + incoming.teardown, bad: old.bad or incoming.bad,
    selected: old.selected or incoming.selected, collected: old.collected or incoming.collected,
    durationTicks: old.durationTicks + incoming.durationTicks, failureCount: old.failureCount + incoming.failureCount }
  action init = all {
    event' = { op: "init", mismatch: "", location: "", payload: "" }, turns' = 0,
    observed' = { mainFirst: empty, mainSecond: passed, laterFirst: empty,
      laterSecond: passed, extraFirst: empty, extraSecond: empty,
      extraExists: false, rejected: false, identityRetained: true,
      mainVerified: false, laterVerified: false, extraVerified: false }
  }
  action reject(kind: str, location: str): bool = all {
    turns < 6, turns' = turns + 1,
    event' = { op: "reject", mismatch: kind, location: location, payload: "passed" },
    observed' = { ...observed, rejected: true }
  }
  action merge(payload: str, location: str): bool = {
    val nextFirst = accumulated(observed.mainFirst, evidence(payload))
    val nextSecond = accumulated(observed.mainSecond, passed)
    val withLater = location == "later-suite"
    val laterFirst = if (withLater) accumulated(observed.laterFirst, evidence(payload)) else observed.laterFirst
    val laterSecond = if (withLater) accumulated(observed.laterSecond, passed) else observed.laterSecond
    val extraFirst = if (withLater) accumulated(observed.extraFirst, evidence(payload)) else observed.extraFirst
    val extraSecond = if (withLater) accumulated(observed.extraSecond, passed) else observed.extraSecond
    all {
      turns < 6, turns' = turns + 1,
      event' = { op: "merge", mismatch: "", location: location, payload: payload },
      observed' = { ...observed, mainFirst: nextFirst, mainSecond: nextSecond,
        laterFirst: laterFirst, laterSecond: laterSecond, extraFirst: extraFirst, extraSecond: extraSecond,
        extraExists: observed.extraExists or withLater, rejected: false,
        mainVerified: completed(nextFirst) and completed(nextSecond),
        laterVerified: completed(laterFirst) and completed(laterSecond),
        extraVerified: completed(extraFirst) and completed(extraSecond) }
    }
  }
  action step = {
    nondet location = Set("same-suite", "later-suite").oneOf()
    nondet kind = Set("family", "debt", "declaration", "case-set", "source", "assessment").oneOf()
    nondet payload = Set("passed", "failed", "incomplete").oneOf()
    any { reject(kind, location), merge(payload, location) }
  }
  val contract = observed.identityRetained and
    (not(observed.mainVerified) or completed(observed.mainFirst)) and
    (not(observed.laterVerified) or completed(observed.laterFirst)) and
    (not(observed.extraVerified) or observed.extraExists)
  action inspection = all { observed' = observed, event' = { op: "inspect", mismatch: "", location: "", payload: "" }, turns' = turns }
  run repeatedLateRejectionTest = init.then(reject("family", "later-suite"))
    .then(reject("debt", "later-suite")).then(reject("declaration", "same-suite"))
    .then(all { assert(not(observed.mainVerified) and not(observed.extraExists)), inspection })
  run compatibleRepeatedEvidenceTest = init.then(merge("passed", "later-suite"))
    .then(merge("passed", "later-suite"))
    .then(all { assert(observed.mainVerified and observed.extraVerified and observed.identityRetained), inspection })
  run lateRejectionRetainsPriorSuccessTest = init.then(merge("passed", "later-suite"))
    .then(reject("family", "later-suite")).then(reject("source", "later-suite"))
    .then(reject("case-set", "same-suite")).then(reject("assessment", "later-suite"))
    .then(all { assert(observed.mainFirst.setup == 1 and observed.mainVerified), inspection })
  run failedRepeatCannotBecomeVerifiedTest = init.then(merge("failed", "same-suite"))
    .then(merge("passed", "same-suite"))
    .then(all { assert(observed.mainFirst.bad and not(observed.mainVerified)), inspection })
  run interruptedRepeatRevokesSuccessTest = init.then(merge("passed", "same-suite"))
    .then(merge("incomplete", "same-suite"))
    .then(all { assert(not(observed.mainVerified)), inspection })
}
