// Allocate from lifetime creates, independently of the live resource count.
module resource_identity_fixed {
  var s: { resources: Set[int], creates: int, replacements: int }
  action init = s' = { resources: Set(), creates: 0, replacements: 0 }
  action create = all {
    s.creates < 3,
    s' = { resources: s.resources.union(Set(s.creates + 1)), creates: s.creates + 1,
      replacements: s.replacements + (if (s.resources.contains(s.creates + 1)) 1 else 0) }
  }
  action deleteFirst = all {
    s.resources.contains(1), s' = { ...s, resources: s.resources.exclude(Set(1)) }
  }
  action deleteLast = all {
    s.resources.contains(2), s' = { ...s, resources: s.resources.exclude(Set(2)) }
  }
  action stay = s' = s
  action step = any { create, deleteFirst, deleteLast, stay }
  val noLiveOverwrite = s.replacements == 0
  run survivorIdentityPreservedTest = init.then(create).then(create).then(deleteFirst).then(create)
    .then(all { assert(noLiveOverwrite and s.resources == Set(2, 3)), stay })
  run deleteLastControlTest = init.then(create).then(create).then(deleteLast).then(create)
    .then(all { assert(noLiveOverwrite and s.resources == Set(1, 3)), stay })
}
