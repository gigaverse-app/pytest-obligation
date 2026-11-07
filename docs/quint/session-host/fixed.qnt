// Ini configuration is a scope over the process's prior raw host or factory.
module session_host_fixed {
  var s: { phase: int, host: str, previous: str, configured: bool }
  action init = s' = { phase: 0, host: "manual", previous: "manual", configured: false }
  action configureA = all {
    s.phase == 0,
    s' = { ...s, phase: 1, previous: s.host, host: "A", configured: true }
  }
  // Config cleanup runs after success or collection failure; session B has no ini host.
  action nextSession = all {
    s.phase == 1,
    s' = { ...s, phase: 2, host: s.previous, configured: false }
  }
  action manualSessionWithoutIni = all {
    s.phase == 0, s' = { ...s, phase: 3 }
  }
  action stay = s' = s
  action step = any {
    configureA, nextSession, manualSessionWithoutIni,
    all { s.phase >= 2, stay }
  }
  val sessionIsolated = s.phase != 2 or (s.host == "manual" and not(s.configured))
  val manualPreserved = s.phase != 3 or s.host == "manual"
  run independentSessionRestoresTest = init.then(configureA).then(nextSession)
    .then(all { assert(sessionIsolated), stay })
  run manualConfigurationControlTest = init.then(manualSessionWithoutIni)
    .then(all { assert(manualPreserved), stay })
}
