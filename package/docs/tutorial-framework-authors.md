# Prove your task library's guarantees, and give your users tests

[All tutorials](tutorials.md) · [Vocabulary](vocabulary.md)

This tutorial is for people who maintain a library that runs work in the
background: a task queue, a job scheduler, a workflow engine, a durable
execution library. You know your domain well. You know what a lease is, why
workers get presumed dead, and why a job sometimes runs twice. You probably
already have tests for the hardest parts.

What this tutorial shows is what pytest-obligation adds on top of that:

1. **A test suite for your hardest problems that keeps growing.** You bind your
   library to pytest-obligation once. It then generates the failure cases
   (worker deaths after every commit, lost replies, racing workers, a late
   worker writing after its replacement) and checks the outcomes. Each release
   of pytest-obligation adds proofs and histories, and its optional Hypothesis
   integration searches for orderings nobody wrote down. Your suite gets
   stronger without you writing more tests.
2. **First-party tests for the people who build on your library.** Your users'
   applications fail in ways your library could warn them about, such as a
   task that is not safe to run twice. With a small testing module, your users
   get a generated suite for their own code in a few lines, because your
   library supplies everything it knows about itself. Due, a durable-work
   library for Django, does exactly this, and chapter 4 shows how.

## The example: tinyq

The library under test is `tinyq`, a deliberately small task queue in
[`examples/task_queue_tutorial`](../../examples/task_queue_tutorial). It keeps
jobs as rows in one table, and everything about a job is in its `status`:

```text
             enqueue
                |
                v
   +-------> ready ---- a worker takes it ----> running ---- task succeeds ----> done
   |                                              |
   +--- task failed, attempts left ---------------+
   +--- worker's time ran out (presumed dead) ----+
                                                  +---- task failed, no attempts left ----> failed
```

It makes the three promises most task queues make: a job survives its worker
dying; a failing job is retried a few times and then marked failed; a worker
that comes back late cannot change a job someone else has since taken. Its
whole implementation is in
[`tinyq/__init__.py`](../../examples/task_queue_tutorial/tinyq/__init__.py),
one or two short SQL statements per method.

To run everything in this tutorial:

```bash
git clone https://github.com/gigaverse-app/pytest-obligation.git
cd pytest-obligation
uv sync --all-packages --locked
cd examples/task_queue_tutorial
uv run --project ../.. --no-sync pytest
```

It should end with `75 passed, 1 xfailed`.

**How to read the code.** Names imported from `pytest_obligation` are explained
before they are used, with a short table after the block. `tinyq` and
`tinyq.testing` are the library under test, the part you replace with your own.
`welcome` is an application built on tinyq, the part your users write. Bindings
carry four labelled comments, `ARRANGE`, `REAL PRODUCTION`, `EXTERNAL SEAM` and
`OBSERVE`, which say what is test setup, what is the code under test, what
stands in for an outside system, and what proves the work happened.

## Chapters

Each chapter is one page and ends with a link to the next.

| Chapter | You will |
| --- | --- |
| [1. Bind your library once](framework-1-bind.md) | Tell pytest-obligation where tinyq commits and how it recovers, and watch it kill a worker at every point |
| [2. Test your hardest problems](framework-2-hard-problems.md) | Prove retries and ownership, and see what the generated tests catch that a hand-written test usually does not |
| [3. A suite that keeps finding more](framework-3-growing.md) | See how new releases and Hypothesis exploration add cases to the binding you already have |
| [4. First-party tests for your users: how Due does it](framework-4-due.md) | See how an application on Due gets 66 generated cases from one short declaration |
| [5. Ship the same for your library](framework-5-ship.md) | Build `task_contract` for tinyq, and see a user's task tested in a few lines |

[Start: 1. Bind your library once](framework-1-bind.md)
