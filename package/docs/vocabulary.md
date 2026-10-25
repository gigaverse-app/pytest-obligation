# Words for testing work that must not be lost or repeated

pytest-obligation tests the failures that happen *between* the lines of your
code: a worker that dies one line after a commit, a message the broker loses, a
retry that repeats an email. Those failures have names, and so do the tools that
test them. This page defines both, each in a sentence or two, starting from what
it is for.

The [tutorials](tutorials.md) link here the first time they use a word. You can
start either tutorial without reading this page.

## The problem

### Due work and obligations

**Due work** is work your application records now and finishes later: send the
receipt, publish the event, render the thumbnail, retry the upload. An
**obligation** is the durable record that such work is still owed, usually a
row in your database. Work that exists only as a queue message, or only in the
next few lines of a function, is not an obligation: a crash erases it.

### Handoff

A **handoff** is a step that commits some state and passes work on: a request
that saves an order and publishes "order placed", a consumer that sends a
receipt and records that it did. Handoffs are where work gets lost (the commit
happened, the message did not) or repeated (the email went out, the record that
it went out did not).

### Commit boundary

A point where your code makes a write durable: a database `COMMIT`, an
acknowledged MongoDB write, a Redis write. A crash right after a commit boundary
leaves the write in place and everything after it undone.

### External call

A call to a system outside your database: a payment API, a broker, a cache, an
email service. Its effect happens there, whether or not your process survives to
record it. pytest-obligation calls the place where your code makes such a call a
**seam**, and you name each one with `ExternalCall`.

### Replay-safe and idempotency key

An operation is **replay-safe** when running it twice leaves the same visible
result as running it once. Writing a value to a cache is. Charging a card is not,
unless you send an **idempotency key**: a name for "this particular request"
that the provider uses to recognise a repeat and return the first result instead
of acting again.

### Claim, lease and fencing token

A worker **claims** a job before running it: it marks the job as taken and
records a **lease**, a deadline by which it must finish or renew. A database
cannot tell a dead worker from a slow one, so when the lease expires, the job
goes back to the queue. The cost is that a slow worker may still be running
when a second one starts. A **fencing token**, a fresh value stamped on the job
at every claim and checked on every write, stops the slow one from saving its
result: its token is no longer the job's. This is profile B.

### Recovery

What your application runs to finish owed work after something went wrong: a
scheduled sweep, a worker that redelivers stalled jobs, a restart that resumes
workflows. A test of due work is a test of whether recovery finds everything,
and repeats nothing it should not.

## How pytest-obligation tests it

### History

One run of a step under one fault. pytest-obligation runs a handoff many times:
once normally, once with every message lost, once dying right after each commit,
once dying right after each external call, and so on. Each run, followed by
recovery, is a **history**.

### Normal operation

The history in which nothing fails: the step runs, its messages are delivered,
recovery runs. It is the reference every other history is compared with.

### Divergence

A history that ends somewhere different from normal operation, after recovery
has done all it can. Work was lost or repeated. pytest-obligation raises
`HistoriesDiverged` and names the history and what it reached.

### Expected outcome

The result the step must produce, written down by you before anything runs, for
example "one paid order, one charge, one receipt". Comparing histories with each
other finds losses and repeats; comparing normal operation with the expected
outcome also catches a step that is consistently wrong.

### Delivery

How published work reaches its consumer in your system, how it gets lost, and
how production recovers it. You describe it once (`CallableDelivery`), and every
history uses it.

### Host and worker killer

The **host** tells pytest-obligation what only your framework knows. Its most
important part is the **worker killer**: the piece that counts your commits and
kills the worker right after a chosen one. Integrations supply hosts for Django
with PostgreSQL, MongoDB and Redis; a plain application can supply its own in a
few lines. A host counts commits on **one** database connection. Every other
system takes part through external calls.

### Binding

The code that connects a test to your application: how to set up a fresh
example, which production function to run, how to observe the result. A binding
must *call* your production code, never re-implement it. pytest-obligation
checks this and refuses bindings that do not reach your
**production packages** (the packages you named as the code under test).

### Contract and generated suite

An **`ObligationContract`** declares, once, everything there is to test about one
piece of due work: its handoffs, its delivery, and a disposition for each
profile. Decorating an empty test class with `@due_work_contract_suite(CONTRACT)`
turns it into a **generated suite**: pytest collects one case per proof the
contract implies. You write no test bodies.

### Profiles A to J

Ten standard questions every piece of due work can be asked, such as "after a
lost message, does a scheduled sweep find the work?" (A) or "does repeating one
operation converge to one visible effect?" (H). The full list is in
[how the proofs work](how-it-works.md#the-a-j-guarantees).

### Disposition

Your answer for one profile: **Claim** (this applies; prove it), **Decline**
(deliberately absent, for an architectural reason), **NotApplicable** (the
situation cannot arise here), **KnownGap** (it should hold and does not yet), or
**NotAssessed** (nobody has looked yet). Every profile needs one; silence is not
allowed.

### Strict expected failure

A known finding recorded as `xfail(strict=True)`. The test passes while the
defect exists, and **fails** the day someone fixes it, so the record has to be
updated in the same change. pytest-obligation creates these from `KnownGap`,
`NotAssessed`, `handoff_gaps` and `Claim(gaps=...)`.

### Positive control

A check that the experiment could have failed. Normal operation must change
what you observe; recovery must change something in at least one interrupted
history; a replay must reach the provider a second time. Without positive
controls, a test that observes nothing would always pass.

### False green

A passing result that measured something other than your production code: a
copy of your query in the test, a recovery that does nothing, an observation
that cannot see the effect. [False greens](false-greens.md) lists every kind the
library refuses.

### Interleaving

Two operations racing: a new revision arriving while an old write is still in
flight, receipts arriving out of order. pytest-obligation generates these
orderings as separate cases (profile E). See [interleavings](interleavings.md).

[Back to the tutorials](tutorials.md)
