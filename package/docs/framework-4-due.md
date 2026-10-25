# 4. First-party tests for your users: how Due does it

[Previous: 3. A suite that keeps finding more](framework-3-growing.md) · [All chapters](tutorial-framework-authors.md#chapters) · [Vocabulary](vocabulary.md)

Chapters 1 to 3 tested your library. This chapter is about the people who
build on it.

An application built on your library has its own promises: an order is paid
once, a receipt is sent once, a stale result never replaces a new one. Most of
what decides whether those promises hold is your library's machinery (how
work is recorded, claimed, retried and recovered), and your users cannot test
it without reimplementing your internals in their tests. You can test it for
them. [Due](https://github.com/gigaverse-app/due), a durable-work library for
Django, ships its pytest-obligation integration to its users, and this chapter
shows what that gives an application.

## The application's code

Due's own tutorial uses a deliberately small application: it doubles a number
in the background and saves the answer. The application declares the work with
Due:

```python
class DoubleNumber(ReplaySafeEffect[Calculation, CalculationWork, int]):
    def perform_effect(self, work: CalculationWork) -> int:
        return double(work.number)

    def finalize_success(self, work: CalculationWork, result: int) -> None:
        Calculation.objects.filter(pk=work.owner_id).update(result=result, failed=False)


calculate = DoubleNumber.for_owner(work=CalculationWork)
```

`perform_effect` does the work; `finalize_success` saves the answer, and Due
only calls it while the attempt still owns the work. That is all the
application knows about background work.

## The application's test

To test it, the application describes the one thing Due cannot know: what its
outside call is, and what a correct result looks like. This is the whole
declaration, from Due's
[`number_examples.py`](https://github.com/gigaverse-app/due/blob/main/integration_tests/conformance/number_examples.py):

```python
# ARRANGE: create a calculation and call request_number with a captured input.
# REAL PRODUCTION: double sleeps/prints/calculates; guarded settlement saves the answer.
# EXTERNAL SEAM: observe the real stdout; ProviderProbe counts or rejects calls to double.
# OBSERVE: read Calculation.result independently; replay must print the actual answer twice.
SEAM = ProviderSeam(
    environment=environment,
    make_work=make_work,
    observe=lambda provider, work: product(work),
    delivered=lambda provider, work: work.number * 2,
    calls=lambda provider: provider.calls.total,
    calls_for=lambda provider, work: provider.calls.count(work.number),
    provider_state=lambda provider, work: provider.output.getvalue().strip().split("\n")[-1],
    provider_expected=lambda provider, work: f"double({work.number}) = {work.number * 2}",
    refuse=lambda provider: provider.calls.reject(lambda: OSError("calculation unavailable")),
)
```

| Field | What the application tells Due |
| --- | --- |
| `environment` | How to put a counting stand-in in front of the outside call (here, `double`) |
| `make_work` | How to request work through the application's own command |
| `observe`, `delivered` | How to read the result, and what it must be |
| `calls`, `calls_for` | How many times the outside call happened, in total and for this piece of work |
| `provider_state`, `provider_expected` | What the outside system should show afterwards |
| `refuse` | How to make the outside call fail, for retry tests |

And this is the test class:

```python
@effect_contract_suite(calculate, examples=EXAMPLES)
class TestNumberCalculation:
    pass
```

`EXAMPLES` is built from `SEAM` by Due's `seam_examples`, plus a few optional
extras the application chose to add. pytest collects **66 test cases** from
it, against the application's real code and a real PostgreSQL database. Among
them: 21 for recovery after a lost message, 12 for ownership by workers and
leases, and the retry, replay, atomic-admission and stale-result checks.

## Who supplies what

Due's documentation draws the layers like this:

```text
 APPLICATION                    DUE                    PYTEST-OBLIGATION
 production capability --------> mode/policy ------------> required profiles
 real producer / provider seam -> runtime adapters ------> fault histories
 independent product observer --------------------------------> verdict
```

| Layer | Supplies |
| --- | --- |
| The application | Its capability, its command that requests work, one stand-in for its outside call, and what a correct result looks like |
| Due | The host (where commits are), the delivery (how messages reach workers, are lost, and are recovered), and every binding that touches its own machinery: the sweep, ownership, retention, retries. It also decides which proofs a capability needs from its kind: a replay-safe effect needs replay proofs, an external operation needs proofs about uncertain outcomes. |
| pytest-obligation | The failure histories, the proofs and the verdict |

Due also helps make sure nothing is quietly left out. Its enrollment check
(`assert_complete_enrollment`) fails when a registered piece of work has no
suite, and its pytest plugin fails a selected proof that was skipped instead of
run.

The effect for the application author is that strong tests cost almost
nothing: the hard part, binding a durable-work runtime to failure proofs, was
written once by the library's authors, who know that runtime best. Chapter 5
builds the same kind of layer for tinyq.

[Next: 5. Ship the same for your library](framework-5-ship.md)
