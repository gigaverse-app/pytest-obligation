// heap-effects-1 source 3fc0d6437b03a46592e1f646bd83cb5709ffc90bc71c7348986e29cc6781e8f3
method merge_reports() returns (rejected: bool, writes: seq<int>)
  ensures rejected ==> writes == []
  decreases *
{
  rejected := false; writes := [];
  var frame1 := writes;
  while *
    decreases *
    invariant writes == frame1
  {
    if * {
      continue;
    } else {
    }
    if * { rejected := true; assert writes == []; return; }
    if * { rejected := true; assert writes == []; return; }
    if * { rejected := true; assert writes == []; return; }
    if * { rejected := true; assert writes == []; return; }
    var frame2 := writes;
    while *
      decreases *
      invariant writes == frame2
    {
      if * { rejected := true; assert writes == []; return; }
      if * { rejected := true; assert writes == []; return; }
    }
    if * { rejected := true; assert writes == []; return; }
    var frame3 := writes;
    while *
      decreases *
      invariant writes == frame3
    {
      if * { rejected := true; assert writes == []; return; }
      if * { rejected := true; assert writes == []; return; }
      var frame4 := writes;
      while *
        decreases *
        invariant writes == frame4
      {
        if * { rejected := true; assert writes == []; return; }
        if * { rejected := true; assert writes == []; return; }
        if * { rejected := true; assert writes == []; return; }
        if * { rejected := true; assert writes == []; return; }
      }
    }
    if * { rejected := true; assert writes == []; return; }
  }
  writes := writes + [280];
  assert true; // retained identities
  assert true; // evidence only accumulates
  var frame5 := writes;
  while *
    decreases *
    invariant frame5 <= writes
  {
    writes := writes + [282];
    assert true; // retained identities
    assert true; // evidence only accumulates
    writes := writes + [283];
    assert true; // retained identities
    assert true; // evidence only accumulates
    var frame6 := writes;
    while *
      decreases *
      invariant frame6 <= writes
    {
      writes := writes + [285];
      assert true; // retained identities
      assert true; // evidence only accumulates
      writes := writes + [285];
      assert true; // retained identities
      assert true; // evidence only accumulates
    }
    writes := writes + [286];
    assert true; // retained identities
    assert true; // evidence only accumulates
    writes := writes + [287];
    assert true; // retained identities
    assert true; // evidence only accumulates
  }
}
// ---- STUB END: proof additions go below ----

// ---- proof additions from reporting.proofs.dfy ----
// Checked proof additions are preserved separately from generated source effects.
// The rejection-frame theorem is generated from the current production AST.
// No axiom, extern method, or assumed atomicity contract is supplied here.
