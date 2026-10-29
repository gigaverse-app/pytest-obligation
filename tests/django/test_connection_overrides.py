"""Observe effective Django connection methods even when an adopter overrides them."""

from contextlib import nullcontext

import pytest
from django.db import transaction

from pytest_obligation.integrations.django import lifecycle_references as ref
from pytest_obligation.integrations.django.callbacks import django_callback_breaker
from pytest_obligation.integrations.django.commits import django_worker_killer
from pytest_obligation.worker_death import CallbackFailed, WorkerDied

pytestmark = pytest.mark.django_db(transaction=True)
_MISSING = object()


@pytest.mark.parametrize("override", ["none", "bound", "wrapper"])
@pytest.mark.parametrize("kill_after", [None, 1])
def test_effective_commit_is_counted_and_killed_without_changing_the_binding(monkeypatch, override, kill_after):
    target = transaction.get_connection()
    called = []
    if override != "none":
        original = target.commit

        def wrapped():
            called.append("commit")
            return original()

        monkeypatch.setitem(vars(target), "commit", original if override == "bound" else wrapped)
    before = vars(target).get("commit", _MISSING)
    callbacks = []
    with ref.lifecycle_attempt_table():
        row = ref.LifecycleAttempt.objects.create(status=ref.Status.RUNNING)
        called.clear()  # Schema setup is outside the observed worker.
        with pytest.raises(WorkerDied) if kill_after else nullcontext():
            with django_worker_killer(kill_after) as worker:
                with transaction.atomic():
                    ref.LifecycleAttempt.objects.filter(pk=row.pk).update(status=ref.Status.COMPLETE)
                    transaction.on_commit(lambda: callbacks.append("published"))
        assert worker.commits == 1
        assert worker.dead == bool(kill_after)
        assert ref.LifecycleAttempt.objects.get(pk=row.pk).status == ref.Status.COMPLETE
        assert called == (["commit"] if override == "wrapper" else [])
    assert callbacks == ([] if kill_after else ["published"])
    assert vars(target).get("commit", _MISSING) is before


@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize("fail_at", [None, 1])
def test_effective_callback_registration_is_observed_and_restored(monkeypatch, override, fail_at):
    target = transaction.get_connection()
    if override:
        monkeypatch.setitem(vars(target), "on_commit", target.on_commit)
    before = vars(target).get("on_commit", _MISSING)
    ran = []
    with pytest.raises(CallbackFailed) if fail_at else nullcontext():
        with django_callback_breaker(fail_at) as callbacks:
            with transaction.atomic():
                transaction.on_commit(lambda: ran.append("published"))
    assert callbacks.count == 1
    assert bool(callbacks.failure) == bool(fail_at)
    assert ran == ([] if fail_at else ["published"])
    assert vars(target).get("on_commit", _MISSING) is before
