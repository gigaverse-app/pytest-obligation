"""In-memory specimens for completion oracle self-tests; never application bindings."""

from pytest_obligation.completion import BoundedCompletion, DeliveryReplay


def timer(*, duration=3, reverse=False):
    state = {"time": 0}

    def advance(seconds):
        state["time"] += seconds

    return BoundedCompletion(
        observe=lambda: state["time"] >= duration,
        expected=True,
        advance=advance,
        recover=lambda: None,
        within_seconds=4,
        interval_seconds=0.5,
        not_before_seconds=3,
        remaining=lambda: int(state["time"]) if reverse else max(0, int(duration - state["time"])),
    )


def delivery_example(fault):
    state = {"entries": 0, "callbacks": 0, "outcome": 0}

    def deliver():
        if fault == "skip" and state["entries"]:
            return
        state["entries"] += 1
        if not state["callbacks"] or fault == "repeat":
            state["callbacks"] += 1
            state["outcome"] = 2 if fault == "wrong outcome" else 1

    example = DeliveryReplay(
        deliver=deliver,
        entries=lambda: state["entries"],
        callback_entries=lambda: state["callbacks"],
        observe=lambda: state["outcome"],
        expected=1,
    )
    return example
