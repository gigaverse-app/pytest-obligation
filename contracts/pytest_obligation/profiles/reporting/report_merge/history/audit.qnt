// profiles/reporting.merge_reports validates per-case metadata while mutating.
// Two cases; target second is complete, first only arrives from the rejected shard.
module report_merge_atomicity {
  type State = { phase: int, firstPassed: bool, secondPassed: bool, rejected: bool,
    unavailable: bool, beforeFirst: bool }
  var s: State
  action init = s' = { phase: 0, firstPassed: false, secondPassed: true, rejected: false,
    unavailable: false, beforeFirst: false }
  action validateSuite = all { s.phase == 0, s' = { ...s, phase: 1, beforeFirst: s.firstPassed } }
  action mergeFirst = all { s.phase == 1, s' = { ...s, phase: 2, firstPassed: true } }
  action rejectSecond = all { s.phase == 2, s' = { ...s, phase: 3, rejected: true } }
  action composeCatches = all { s.phase == 3, s' = { ...s, phase: 4, unavailable: true } }
  action step = any { validateSuite, mergeFirst, rejectSecond, composeCatches }
  val rejectedShardAtomic = not(s.rejected) or s.firstPassed == s.beforeFirst
  val composerExplainsRejection = s.phase != 4 or s.unavailable
  run partialPromotionWitnessTest = init.then(validateSuite).then(mergeFirst).then(rejectSecond).then(composeCatches)
    .then(all { assert(s.firstPassed and s.secondPassed and s.unavailable), s' = s })
}
