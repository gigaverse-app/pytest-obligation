# Prove your task library's guarantees, and give your users tests

[All tutorials](tutorials.md) · [Vocabulary](vocabulary.md)

This tutorial is for people who maintain a library that runs work in the
background: a task queue, a job scheduler, a workflow engine, a durable
execution library. You know your domain well, and you probably already have
good tests for its hardest parts.

pytest-obligation offers you two things on top of that:

1. **First-party tests for the people who build on your library.** This is the
   bigger one. An application on your library has promises of its own: a
   payment taken once, a receipt sent once. Whether they hold depends mostly on
   your machinery (how jobs are recorded, claimed, retried and recovered), and
   your users cannot test that without reimplementing your internals. You can
   ship a small testing module that knows your internals, so an application
   gets a generated failure suite for *its own* jobs in a few lines, and finds
   out, for example, whether its job is safe to run twice.
2. **A suite for your hardest problems that keeps growing.** You bind your
   library once. pytest-obligation generates the failure cases (a worker dying
   after every write, lost replies, racing workers, a late worker writing after
   its replacement) and checks the outcomes. Each release adds proofs and
   histories, and its optional Hypothesis integration searches for orderings
   nobody wrote down.

## The worked example: RQ

The tutorial uses [RQ](https://python-rq.org/), a simple Redis-backed task
queue for Python. pytest-obligation ships an RQ integration, and that
integration is exactly the testing module an RQ maintainer would ship: it
knows where RQ writes, how RQ recovers a dead worker's job, and how RQ
retries. Read it as the blueprint for the module you would write for your own
library.

The application is [`examples/rq_tutorial`](../../examples/rq_tutorial): when a
user signs up, an RQ job emails them a welcome message. By the end, that
application gets 25 generated test cases from one short declaration, and the
crash test alone runs its job through 52 different failure histories.

To run it you need Redis, and Linux or macOS (RQ does not support Windows; WSL
works):

```bash
git clone https://github.com/gigaverse-app/pytest-obligation.git
cd pytest-obligation
uv sync --all-packages --locked --extra rq
docker run -d --rm -p 6379:6379 redis:7
cd examples/rq_tutorial
REDIS_URL=redis://localhost:6379/14 uv run --project ../.. --no-sync pytest
```

It should end with `47 passed, 3 xfailed` in about a minute. The test empties
the Redis database it uses, so point `REDIS_URL` at one you do not need.

**How to read the code.** Names imported from `pytest_obligation` are explained
before they are used, with a short table after the block. `welcome_rq` is the
application, the part your users write. `rq_testing` is the small module that
plays the role of "what RQ ships"; chapter 4 builds it. Bindings carry four
labelled comments, `ARRANGE`, `REAL PRODUCTION`, `EXTERNAL SEAM` and `OBSERVE`,
which say what is test setup, what is the code under test, what stands in for
an outside system, and what proves the work happened.

## Chapters

| Chapter | You will |
| --- | --- |
| [1. Bind your library once](framework-1-bind.md) | See how the RQ integration tells pytest-obligation where RQ writes and how it recovers, and watch a job survive 52 failure histories |
| [2. Test your hardest problems](framework-2-hard-problems.md) | Bind RQ's ownership and retries, and see what generated tests check that a hand-written test usually does not |
| [3. A suite that keeps finding more](framework-3-growing.md) | See how new releases and Hypothesis exploration add cases to bindings you already have |
| [4. The module you ship](framework-4-module.md) | Assemble everything into one contract function your users call, and declare your library's own properties once |
| [5. An application on your library](framework-5-application.md) | Watch the welcome app get its suite in a few lines, and find its own duplicate-email bug |

[Start: 1. Bind your library once](framework-1-bind.md)
