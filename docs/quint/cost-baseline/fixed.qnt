// CostCompleteness: absence proves retirement only after complete execution.
module cost_baseline_fixed {
  type State = {
    phase: str, baseline: Set[str], visited: Set[str], incomplete: bool,
    collected: int, finished: int, status: int, serial: bool, collectOnly: bool
  }
  var s: State
  var event: { op: str, collected: int, status: int }
  var observed: { baseline: Set[str], visited: Set[str], finished: int }

  // event contains hook inputs; observed contains values independently read by the adapter.
  action emit(nextState: State, op: str): bool = all {
    s' = nextState,
    event' = { op: op, collected: nextState.collected, status: nextState.status },
    observed' = { baseline: nextState.baseline, visited: nextState.visited, finished: nextState.finished }
  }
  action init = emit({
    phase: "collecting", baseline: Set("required", "retired"), visited: Set(),
    incomplete: false, collected: 0, finished: 0, status: 0,
    serial: true, collectOnly: false
  }, "init")
  action collectionError = all {
    s.phase == "collecting", emit({ ...s, phase: "finish", incomplete: true, status: 2 }, "collectionError")
  }
  action skipOrDeselect = all {
    s.phase == "collecting",
    emit({ ...s, phase: "finish", incomplete: true, collected: 1, finished: 1 }, "skipOrDeselect")
  }
  action earlySuccessfulExit = all {
    s.phase == "collecting", emit({ ...s, phase: "finish", collected: 2, finished: 1 }, "earlySuccessfulExit")
  }
  action testFailure = all {
    s.phase == "collecting",
    emit({ ...s, phase: "finish", incomplete: true, status: 1, collected: 1, finished: 1 }, "testFailure")
  }
  action collectOnly = all {
    s.phase == "collecting", emit({ ...s, phase: "finish", collectOnly: true, collected: 1 }, "collectOnly")
  }
  action distributedRun = all {
    s.phase == "collecting",
    emit({ ...s, phase: "finish", serial: false, collected: 1, finished: 1, visited: Set("required") }, "distributedRun")
  }
  action completeRun = all {
    s.phase == "collecting",
    emit({ ...s, phase: "finish", collected: 1, finished: 1, visited: Set("required") }, "completeRun")
  }
  action emptyCollection = all {
    s.phase == "collecting", emit({ ...s, phase: "finish", status: 5 }, "emptyCollection")
  }
  val completeEvidence = s.serial and not(s.collectOnly) and not(s.incomplete)
    and s.collected == s.finished and Set(0, 5).contains(s.status)
  action finishUpdate = all {
    s.phase == "finish",
    emit({ ...s, phase: "done",
      baseline: if (completeEvidence) s.baseline.intersect(s.visited) else s.baseline }, "finishUpdate")
  }
  action inspect = emit(s, "inspect")
  action step = any {
    collectionError, skipOrDeselect, earlySuccessfulExit, testFailure, collectOnly,
    distributedRun, completeRun, emptyCollection, finishUpdate,
    all { s.phase == "done", inspect }
  }
  val incompletePreservesBaseline = s.phase != "done" or completeEvidence
    or s.baseline == Set("required", "retired")
  run failedCollectionPreservesTest = init.then(collectionError).then(finishUpdate)
    .then(all { assert(s.baseline == Set("required", "retired")), inspect })
  run skippedRunPreservesTest = init.then(skipOrDeselect).then(finishUpdate)
    .then(all { assert(incompletePreservesBaseline), inspect })
  run earlyExitPreservesTest = init.then(earlySuccessfulExit).then(finishUpdate)
    .then(all { assert(s.baseline == Set("required", "retired")), inspect })
  run failurePreservesTest = init.then(testFailure).then(finishUpdate)
    .then(all { assert(incompletePreservesBaseline), inspect })
  run collectionOnlyPreservesTest = init.then(collectOnly).then(finishUpdate)
    .then(all { assert(incompletePreservesBaseline), inspect })
  run distributedRunPreservesTest = init.then(distributedRun).then(finishUpdate)
    .then(all { assert(incompletePreservesBaseline), inspect })
  run retirementControlTest = init.then(completeRun).then(finishUpdate)
    .then(all { assert(s.baseline == Set("required")), inspect })
  run emptyRetirementControlTest = init.then(emptyCollection).then(finishUpdate)
    .then(all { assert(s.baseline == Set()), inspect })
}
