// Maintained API-boundary contract for the shipped ResourceProvider.
// Identity allocation, live ordering and retained objects are observed by replay.
module resource_identity_fixed {
  var event: { op: str, target: int }
  var observed: { live: List[int], issued: List[int], identityRetained: bool, rejected: bool }
  var creates: int
  var turns: int
  pure def members(xs: List[int]): Set[int] = xs.indices().map(i => xs.nth(i))
  action init = all {
    event' = { op: "init", target: 0 }, creates' = 0, turns' = 0,
    observed' = { live: List(), issued: List(), identityRetained: true, rejected: false }
  }
  action create = all {
    creates < 4, turns < 9, creates' = creates + 1, turns' = turns + 1,
    event' = { op: "create", target: 0 },
    observed' = { ...observed, live: observed.live.append(creates + 1),
      issued: observed.issued.append(creates + 1), rejected: false }
  }
  action deleteResource(target: int): bool = all {
    members(observed.live).contains(target), turns < 9, creates' = creates, turns' = turns + 1,
    event' = { op: "delete", target: target },
    observed' = { ...observed, live: observed.live.select(id => id != target), rejected: false }
  }
  action rejectDelete = all {
    turns < 9, creates' = creates, turns' = turns + 1,
    event' = { op: "rejectDelete", target: 99 },
    observed' = { ...observed, rejected: true }
  }
  action delete = {
    nondet target = members(observed.live).oneOf()
    deleteResource(target)
  }
  action step = any { create, rejectDelete, delete }
  val contract = observed.identityRetained and observed.issued.length() == members(observed.issued).size() and
    members(observed.live).subseteq(members(observed.issued))
  action inspection = all { event' = { op: "inspect", target: 0 }, observed' = observed, creates' = creates, turns' = turns }
  run earlierDeletionRecreationTest = init.then(create).then(create).then(deleteResource(1)).then(create)
    .then(all { assert(observed.live == List(2,3) and observed.identityRetained), inspection })
  run latestDeletionRecreationTest = init.then(create).then(create).then(deleteResource(2)).then(create)
    .then(all { assert(observed.live == List(1,3)), inspection })
  run emptyProviderStillAdvancesIdentityTest = init.then(create).then(deleteResource(1)).then(create)
    .then(deleteResource(2)).then(create)
    .then(all { assert(observed.issued == List(1,2,3) and observed.live == List(3)), inspection })
  run rejectedDeletePreservesObjectsTest = init.then(create).then(create).then(rejectDelete)
    .then(deleteResource(1)).then(rejectDelete).then(create)
    .then(all { assert(observed.live == List(2,3) and not(observed.rejected)), inspection })
}
