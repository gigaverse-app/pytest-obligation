# Tutorials

pytest-obligation tests the failures that happen between the lines of your
code: a worker killed right after a commit, a message the broker loses, a retry
that repeats an email. Pick the tutorial that matches what you build. Both run
locally with nothing to install beyond the repository, show the real output of
every step, and are split into short chapters.

| You build | Start with | You will |
| --- | --- | --- |
| An application whose workflows touch a database, a queue, a cache, a payment provider and email | [Test a workflow that spans many systems](tutorial-many-systems.md) | Find a charge with no order and a duplicate receipt in a checkout, fix both, and turn the description into a generated suite |
| A task queue or durable-work library | [Prove your task library's guarantees, and give your users tests](tutorial-framework-authors.md) | See how far generated tests reach on your hardest problems, how the suite keeps growing with releases and Hypothesis search, and how to give your users first-party tests, as Due does |

New to words like *handoff*, *lease* or *idempotency key*? The
[vocabulary](vocabulary.md) defines each in a sentence or two, starting from the
failure it prevents.

When you are ready to adopt the library in your own code, continue with
[adopting pytest-obligation](adopting.md).
