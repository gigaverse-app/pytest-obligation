// CostCompleteness: absence proves retirement only after complete execution.
module cost_baseline_fixed {
  var s: {
    phase: str, baseline: Set[str], visited: Set[str], incomplete: bool,
    collected: int, finished: int, status: int, serial: bool, collectOnly: bool
  }
  action init = s' = {
    phase: "collecting", baseline: Set("required", "retired"), visited: Set(),
    incomplete: false, collected: 0, finished: 0, status: 0,
    serial: true, collectOnly: false
  }
  action collectionError = all {
    s.phase == "collecting", s' = { ...s, phase: "finish", incomplete: true, status: 2 }
  }
  action skipOrDeselect = all {
    s.phase == "collecting",
    s' = { ...s, phase: "finish", incomplete: true, collected: 1, finished: 1 }
  }
  action earlySuccessfulExit = all {
    s.phase == "collecting", s' = { ...s, phase: "finish", collected: 2, finished: 1 }
  }
  action testFailure = all {
    s.phase == "collecting",
    s' = { ...s, phase: "finish", incomplete: true, status: 1, collected: 1, finished: 1 }
  }
  action collectOnly = all {
    s.phase == "collecting", s' = { ...s, phase: "finish", collectOnly: true, collected: 1 }
  }
  action distributedRun = all {
    s.phase == "collecting",
    s' = { ...s, phase: "finish", serial: false, collected: 1, finished: 1, visited: Set("required") }
  }
  action completeRun = all {
    s.phase == "collecting",
    s' = { ...s, phase: "finish", collected: 1, finished: 1, visited: Set("required") }
  }
  action emptyCollection = all {
    s.phase == "collecting", s' = { ...s, phase: "finish", status: 5 }
  }
  val completeEvidence = s.serial and not(s.collectOnly) and not(s.incomplete)
    and s.collected == s.finished and Set(0, 5).contains(s.status)
  action finishUpdate = all {
    s.phase == "finish",
    s' = { ...s, phase: "done",
      baseline: if (completeEvidence) s.baseline.intersect(s.visited) else s.baseline }
  }
  action stay = s' = s
  action step = any {
    collectionError, skipOrDeselect, earlySuccessfulExit, testFailure, collectOnly,
    distributedRun, completeRun, emptyCollection, finishUpdate,
    all { s.phase == "done", stay }
  }
  val incompletePreservesBaseline = s.phase != "done" or completeEvidence
    or s.baseline == Set("required", "retired")
  run failedCollectionPreservesTest = init.then(collectionError).then(finishUpdate)
    .then(all { assert(s.baseline == Set("required", "retired")), stay })
  run skippedRunPreservesTest = init.then(skipOrDeselect).then(finishUpdate)
    .then(all { assert(incompletePreservesBaseline), stay })
  run earlyExitPreservesTest = init.then(earlySuccessfulExit).then(finishUpdate)
    .then(all { assert(s.baseline == Set("required", "retired")), stay })
  run failurePreservesTest = init.then(testFailure).then(finishUpdate)
    .then(all { assert(incompletePreservesBaseline), stay })
  run collectionOnlyPreservesTest = init.then(collectOnly).then(finishUpdate)
    .then(all { assert(incompletePreservesBaseline), stay })
  run distributedRunPreservesTest = init.then(distributedRun).then(finishUpdate)
    .then(all { assert(incompletePreservesBaseline), stay })
  run retirementControlTest = init.then(completeRun).then(finishUpdate)
    .then(all { assert(s.baseline == Set("required")), stay })
  run emptyRetirementControlTest = init.then(emptyCollection).then(finishUpdate)
    .then(all { assert(s.baseline == Set()), stay })
}
