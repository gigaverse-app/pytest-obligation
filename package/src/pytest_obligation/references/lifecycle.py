"""Small executable subjects for the lifecycle oracles' own sensitivity tests."""

from contextlib import contextmanager

from pytest_obligation.lifecycle import AdmissionOverlap, PartialProgress, SettlementInterleaving


def admission_example(fault=None):
    promised = set()
    effects = []

    def admit(values):
        if fault == "retain-first" and promised:
            return
        if fault == "replace":
            promised.clear()
        promised.update(values)

    def recover():
        for value in sorted(promised):
            if value not in effects or fault == "duplicate":
                effects.append(value)

    return AdmissionOverlap(
        first=lambda: admit({"receipt"}),
        later=lambda: admit({"receipt", "archive"}),
        recover=recover,
        observe=lambda: tuple(sorted(effects)),
        expected_first=("receipt",),
        expected_combined=("archive", "receipt"),
    )


def settlement_example(fault=None):
    state = {"terminal": False, "owed": True, "effects": 0}
    callback = None

    def compete():
        state["terminal"] = True

    def run():
        before = state["terminal"]
        if callback is not None:
            try:
                callback()
            except AssertionError:
                if fault != "swallow":
                    raise
        if fault == "discard" and before != state["terminal"]:
            state["owed"] = False
        recover()

    def recover():
        if state["owed"] or fault == "duplicate":
            state["effects"] += 1
            state["owed"] = False

    @contextmanager
    def during(checkpoint):
        nonlocal callback
        callback = None if fault == "unreached" else checkpoint
        try:
            yield
        finally:
            callback = None

    return SettlementInterleaving(
        run=run,
        compete=compete,
        observe_competing=lambda: state["terminal"],
        during=during,
        recover=recover,
        observe=lambda: state["effects"],
        expected=1,
    )


def partial_progress_example(fault=None):
    state = {"first": 0, "second": 0, "pending": True, "broken": False, "hits": 0}

    @contextmanager
    def failure():
        state["broken"] = True
        try:
            yield lambda: state["hits"]
        finally:
            state["broken"] = False

    def recover():
        if not state["pending"]:
            return
        if not state["first"] or fault == "repeat":
            state["first"] += 1
        if state["broken"] and fault != "unreached":
            state["hits"] += 1
            if fault == "discard":
                state["pending"] = False
            return
        state["second"] += 1
        state["pending"] = False

    return PartialProgress(
        run=recover,
        recover=recover,
        failure=failure,
        observe=lambda: (state["first"], state["second"]),
        expected_partial=(1, 0),
        expected=(1, 1),
        completed_effects=lambda: state["first"],
    )
