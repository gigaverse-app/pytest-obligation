// Extracted lifecycle bug models. No production fixes. Expected invariant failures.
module session_persistence {
  var phase: int
  var host: str
  var configured: bool
  var baseline: Set[str]
  var visited: Set[str]
  var collectionFailed: bool
  action init = all {
    phase' = 0, host' = "empty", configured' = false,
    baseline' = Set("required"), visited' = Set(), collectionFailed' = false
  }
  action configureA = all {
    phase == 0, phase' = 1, host' = "A", configured' = true,
    baseline' = baseline, visited' = visited, collectionFailed' = collectionFailed
  }
  // There is no plugin host-unconfigure hook. Session B has no host setting.
  action nextSession = all {
    phase == 1, phase' = 2, host' = host, configured' = false,
    baseline' = baseline, visited' = visited, collectionFailed' = collectionFailed
  }
  action collectionError = all {
    phase == 0, phase' = 3, host' = host, configured' = configured,
    baseline' = baseline, visited' = visited, collectionFailed' = true
  }
  // _cost_plugin.CostCompleteness prunes on every sessionfinish in update mode.
  action finishUpdate = all {
    phase == 3, phase' = 4, host' = host, configured' = configured,
    baseline' = baseline.intersect(visited), visited' = visited, collectionFailed' = collectionFailed
  }
  action step = any { configureA, nextSession, collectionError, finishUpdate }
  action unchanged = all {
    phase' = phase, host' = host, configured' = configured,
    baseline' = baseline, visited' = visited, collectionFailed' = collectionFailed
  }
  // Passing witnesses of the CURRENT defects, not desired safety tests.
  run leakedHostWitnessTest = init.then(configureA).then(nextSession)
    .then(all { assert(host == "A" and not(configured)), unchanged })
  run baselineDeletionWitnessTest = init.then(collectionError).then(finishUpdate)
    .then(all { assert(baseline == Set()), unchanged })
  val sessionIsolated = phase != 2 or host == "empty"
  val failedCollectionPreservesBaseline = not(collectionFailed) or baseline.contains("required")
}
