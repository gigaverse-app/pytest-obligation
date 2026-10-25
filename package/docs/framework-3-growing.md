# 3. A suite that keeps finding more

[Previous: 2. Test your hardest problems](framework-2-hard-problems.md) · [All chapters](tutorial-framework-authors.md#chapters) · [Vocabulary](vocabulary.md)

A hand-written test suite checks what its authors thought of, on the day they
wrote it. The bindings from chapters 1 and 2 are different. They describe your
library's operations, not test scenarios, so anything that can be generated
from them keeps working as pytest-obligation learns to generate more. This
chapter shows the two ways that happens.

## New releases, same binding

The harness's proofs and histories grow with each release, and the work of
writing them is done once, upstream, for every library that binds the same
operations. Some new checks apply to the bindings you already have; others
are a flag or one more callback on the same binding. Two recent examples, one adding histories and one making findings more precise:

| Release | What it added | What an adopter changed |
| --- | --- | --- |
| [0.17.0](https://github.com/gigaverse-app/pytest-obligation/pull/141) | Generated histories for a record that is retired and recreated while an old request is still in flight, and for a rejected command that is retried | One flag (`recreation=True`) and one callback on an existing binding. In the application that drove it, the generated histories replaced 12 hand-written schedule tests. |
| [0.13.0](https://github.com/gigaverse-app/pytest-obligation/pull/80) | A held provider request now expires after a declared lifetime, as real SDK timeouts do, so the harness stops reporting orderings production cannot produce | One number (`request_lifetime_seconds`) on the existing binding |

The workflow is the one you already use for any dependency: bump the version,
run the suite, read what is new. A new case that passes is coverage you did
not write. A new case that fails is a finding: fix it, or record it as a
strict expected failure (chapters 4 and 5 show how) so it stays visible.

## Searching for orderings nobody wrote down

Some promises are about order rather than crashes: a late write overtaking a
newer one, receipts arriving out of order, a retry racing a cancellation. For
these, pytest-obligation generates a fixed set of orderings as ordinary test
cases, and can also *search* for more with
[Hypothesis](https://hypothesis.readthedocs.io/), the property-based testing
library:

```bash
uv add --dev 'pytest-obligation[exploration]'
uv run pytest -m due_work --due-work-explore=smoke
uv run pytest -m due_work --due-work-explore=deep
```

`smoke` tries up to 20 generated schedules per scenario, with up to 15 steps
each; `deep` tries up to 200, with up to 50 steps. Normal runs leave
exploration off. Search runs inside generated pytest cases, so it needs no
extra test code, and when it finds a failure it shrinks it to a short ordering
and prints it as a JSON trace you can save and replay without Hypothesis.

This is where the strangest bugs come from. The search added in 0.17.0, which
repeats retire-and-restore cycles and permutes when old requests complete,
found a defect that every fixed history missed: a broken implementation that
only went wrong at the sixth revision of the same record.

Exploration applies to the ordering families of profile E (in-flight requests,
and evidence arriving in pieces). RQ's contract does not claim E, because one
worker settles each job and no two results race. A library that keeps external
views in sync, merges receipts or projects state does. The repository's
[SQLite adopter example](../../examples/adopter) binds both families; with
`--due-work-explore=smoke` its suite runs in about ten seconds.

## Findings stay findings

Whether a new failure comes from an upgrade or from a search, it is recorded
the same way: a strict expected failure that names what is wrong. It passes
while the defect exists and fails the day someone fixes it, so a record can
never outlive the bug it describes, and a fix never goes unnoticed. The
profile report (`--due-work-profile-report=profiles.json`) keeps proven
guarantees, declined ones and known gaps apart, so a growing suite does not
blur what is actually guaranteed.

[Next: 4. The module you ship](framework-4-module.md)
