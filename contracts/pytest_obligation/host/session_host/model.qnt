// Maintained contract: actual pytest ini ownership and lazy host resolution.
module session_host_fixed {
  var phase: int
  var event: { op: str, kind: str }
  var observed: { host: str, manualCalls: int, applicationCalls: int }
  var previous: str
  action initFactory = all {
    phase' = 0, previous' = "manual_factory", event' = { op: "initFactory", kind: "factory" },
    observed' = { host: "manual_factory", manualCalls: 0, applicationCalls: 0 }
  }
  action initManual = all {
    phase' = 0, previous' = "manual", event' = { op: "initManual", kind: "host" },
    observed' = { host: "manual", manualCalls: 0, applicationCalls: 0 }
  }
  action init = any { initFactory, initManual }
  action configureA = all {
    phase == 0, phase' = 1, previous' = previous,
    event' = { op: "configureA", kind: "ini" },
    observed' = { ...observed, host: "application_factory" }
  }
  action resolveApplication = all {
    phase == 1, phase' = 2, previous' = previous,
    event' = { op: "resolveApplication", kind: "api" },
    observed' = { ...observed, host: "A", applicationCalls: 1 }
  }
  action cleanupA = all {
    Set(1, 2).contains(phase), phase' = 3, previous' = previous,
    event' = { op: "cleanupA", kind: "cleanup" },
    observed' = { ...observed, host: previous }
  }
  action configureWithoutIni = all {
    Set(0, 3).contains(phase), phase' = 4, previous' = previous,
    event' = { op: "configureWithoutIni", kind: "no-ini" }, observed' = observed
  }
  action resolveManual = all {
    phase == 4, phase' = 5, previous' = previous,
    event' = { op: "resolveManual", kind: "api" },
    observed' = { ...observed, host: "manual", manualCalls: if (previous == "manual_factory") 1 else 0 }
  }
  action cleanupB = all {
    Set(4, 5).contains(phase), phase' = 6, previous' = previous,
    event' = { op: "cleanupB", kind: "cleanup" }, observed' = observed
  }
  action inspect = all {
    phase' = phase, previous' = previous,
    event' = { op: "inspect", kind: "observation" }, observed' = observed
  }
  action step = any {
    configureA, resolveApplication, cleanupA, configureWithoutIni,
    resolveManual, cleanupB, all { phase == 6, inspect }
  }
  val sessionIsolated = phase != 3 or observed.host == previous
  val lazyPrevious = phase > 4 or observed.manualCalls == 0
  val maintained = sessionIsolated and lazyPrevious
  run unusedFactoryRestorationTest = initFactory.then(configureA).then(cleanupA)
    .then(configureWithoutIni).then(resolveManual).then(cleanupB)
    .then(all { assert(observed.host == "manual" and observed.manualCalls == 1), inspect })
  run resolvedFactoryRestorationTest = initFactory.then(configureA).then(resolveApplication)
    .then(cleanupA).then(configureWithoutIni).then(resolveManual).then(cleanupB)
    .then(all { assert(observed.applicationCalls == 1 and observed.manualCalls == 1), inspect })
  run manualConfigurationControlTest = initManual.then(configureWithoutIni).then(resolveManual)
    .then(cleanupB).then(all { assert(observed.host == "manual" and observed.manualCalls == 0), inspect })
  run manualRestorationControlTest = initManual.then(configureA).then(resolveApplication).then(cleanupA)
    .then(all { assert(sessionIsolated), inspect })
}
