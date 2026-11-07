// Actual ResourceProvider.create/delete in integrations/django/owed_references.
// Name allocation uses len(resources)+1 and can replace an existing live identity.
module resource_identity {
  type State = { resources: Set[int], creates: int, replacements: int }
  var s: State
  action init = s' = { resources: Set(), creates: 0, replacements: 0 }
  action create = all { s.creates < 3,
    s' = { resources: s.resources.union(Set(s.resources.size() + 1)), creates: s.creates + 1,
      replacements: s.replacements + (if (s.resources.contains(s.resources.size() + 1)) 1 else 0) } }
  action deleteFirst = all { s.resources.contains(1), s' = { ...s, resources: s.resources.exclude(Set(1)) } }
  action deleteLast = all { s.resources.contains(2), s' = { ...s, resources: s.resources.exclude(Set(2)) } }
  action step = any { create, deleteFirst, deleteLast }
  val noLiveOverwrite = s.replacements == 0
  run identityCollisionWitnessTest = init.then(create).then(create).then(deleteFirst).then(create)
    .then(all { assert(s.resources == Set(2) and s.replacements == 1), s' = s })
  run deleteLastControlTest = init.then(create).then(create).then(deleteLast).then(create)
    .then(all { assert(noLiveOverwrite and s.resources == Set(1,2)), s' = s })
}
