// Validate all metadata before admitting new suites or changing prior cases.
module report_merge_fixed {
  var s: {
    phase: int, firstPassed: bool, secondPassed: bool, rejected: bool,
    unavailable: bool, staged: bool, newSuiteAdmitted: bool
  }
  action init = s' = {
    phase: 0, firstPassed: false, secondPassed: true, rejected: false,
    unavailable: false, staged: false, newSuiteAdmitted: false
  }
  action validateSuite = all { s.phase == 0, s' = { ...s, phase: 1 } }
  action stageCandidates = all { s.phase == 1, s' = { ...s, phase: 2, staged: true } }
  action rejectLaterMismatch = all { s.phase == 2, s' = { ...s, phase: 3, rejected: true } }
  action commitCompatibleShard = all {
    s.phase == 2, s.staged,
    s' = { ...s, phase: 4, firstPassed: true, newSuiteAdmitted: true }
  }
  action composeCatches = all { s.phase == 3, s' = { ...s, phase: 5, unavailable: true } }
  action stay = s' = s
  action step = any {
    validateSuite, stageCandidates, rejectLaterMismatch, commitCompatibleShard,
    composeCatches, all { s.phase >= 4, stay }
  }
  val rejectedShardAtomic = not(s.rejected) or (not(s.firstPassed) and not(s.newSuiteAdmitted))
  val composerExplainsRejection = s.phase != 5 or s.unavailable
  run rejectedShardPreservesEvidenceTest = init.then(validateSuite).then(stageCandidates)
    .then(rejectLaterMismatch).then(composeCatches)
    .then(all { assert(rejectedShardAtomic and s.secondPassed and s.unavailable), stay })
  run compatibleShardControlTest = init.then(validateSuite).then(stageCandidates)
    .then(commitCompatibleShard)
    .then(all { assert(s.firstPassed and s.secondPassed and s.newSuiteAdmitted), stay })
}
