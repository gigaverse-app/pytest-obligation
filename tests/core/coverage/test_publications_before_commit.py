from pathlib import Path
from textwrap import dedent

import pytest

from pytest_obligation.coverage.config import CoverageConfig
from pytest_obligation.coverage.transactions import publications_before_commit


def config(root: Path) -> CoverageConfig:
    return CoverageConfig(
        root=root,
        production_packages=("shop",),
        source_roots=(".",),
        transaction_openers=frozenset({"shop.core.transactions.decorators.aatomic"}),
    )


def _write_production_module(base: Path, relative: str, source: str) -> None:
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source))


def test_a_publication_in_a_transaction_body_is_found_but_not_its_on_commit_callback(tmp_path) -> None:
    _write_production_module(
        tmp_path,
        "shop/app/services.py",
        """
        from django.db import transaction
        from shop.core.transactions.decorators import aatomic

        @transaction.atomic
        def decorated():
            announce.delay(1)
            transaction.on_commit(lambda: announce.delay(2))

        def with_block():
            with transaction.atomic():
                announce.apply_async(args=(1,))
            announce.delay(3)

        @aatomic
        async def asynchronous():
            celery_app.send_task("announce")

        def autocommit():
            announce.delay(4)
        """,
    )
    assert publications_before_commit(config(tmp_path)) == {
        "shop.app.services.decorated": {"shop.app.services.decorated": ()},
        "shop.app.services.with_block": {"shop.app.services.with_block": ()},
        "shop.app.services.asynchronous": {"shop.app.services.asynchronous": ()},
    }


def test_a_publication_the_transaction_reaches_through_its_collaborators_is_found(tmp_path) -> None:
    """The event-scheduled email's shape: an atomic capability calling a service whose body publishes."""
    _write_production_module(
        tmp_path,
        "shop/app/services.py",
        """
        from django.db import transaction

        class Base:
            def notify(self, event_id):
                announce.delay(event_id)

        class EventService(Base):
            def create_event(self):
                self.record()
                self.notify(1)

            def record(self):
                pass

            def deferred(self):
                transaction.on_commit(lambda: self.notify(2))
        """,
    )
    _write_production_module(
        tmp_path,
        "shop/app/capability.py",
        """
        from asgiref.sync import sync_to_async
        from django.db import transaction
        from shop.app.services import EventService

        class Capability:
            events: EventService = dependency(EventService)

            @transaction.atomic
            def create(self):
                self.events.create_event()
                self.events.record()
                self.events.deferred()

            async def acreate(self):
                with transaction.atomic():
                    await sync_to_async(self.events.create_event)()

            def unresolved(self):
                with transaction.atomic():
                    events = EventService()
                    events.create_event()
        """,
    )
    through_the_service = (
        "shop.app.services.EventService.create_event",
        "shop.app.services.Base.notify",
    )
    publisher = "shop.app.services.Base.notify"
    assert publications_before_commit(config(tmp_path)) == {
        "shop.app.capability.Capability.create": {publisher: through_the_service},
        "shop.app.capability.Capability.acreate": {publisher: through_the_service},
    }


def test_cycles_relative_imports_and_deferred_calls(tmp_path: Path) -> None:
    _write_production_module(
        tmp_path,
        "shop/a.py",
        """
        from django.db import transaction
        from .b import second
        def first():
            second()
        @transaction.atomic
        def command():
            first()
        @transaction.atomic
        def deferred():
            transaction.on_commit(first)
    """,
    )
    _write_production_module(
        tmp_path,
        "shop/b.py",
        """
        from .a import first
        def second():
            first()
            task.delay()
    """,
    )
    assert publications_before_commit(config(tmp_path)) == {
        "shop.a.command": {"shop.b.second": ("shop.a.first", "shop.b.second")},
    }


def test_scan_cannot_report_clean_when_production_is_unreadable(tmp_path: Path) -> None:
    _write_production_module(tmp_path, "shop/broken.py", "def invalid(")
    with pytest.raises(ValueError, match="incomplete"):
        publications_before_commit(config(tmp_path))


def test_cli_reports_transitive_chain(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from pytest_obligation.coverage.cli import main

    from .builders import write_project

    write_project(
        tmp_path,
        {
            "shop/orders.py": """
        from django.db import transaction
        def publish():
            task.delay()
        @transaction.atomic
        def command():
            publish()
    """
        },
    )
    assert main(["before-commit", "--root", str(tmp_path)]) == 1
    assert "shop.orders.command -> shop.orders.publish" in capsys.readouterr().out


def test_reviewed_publication_inventory_cannot_hide_growth_or_stale_exceptions(tmp_path: Path) -> None:
    from pytest_obligation.coverage.transactions import PublishedBeforeCommit, assert_publications_reviewed

    _write_production_module(
        tmp_path,
        "shop/services.py",
        """
        from django.db import transaction
        @transaction.atomic
        def command():
            task.delay()
    """,
    )
    owner = "shop.services.command"
    allowance = PublishedBeforeCommit(
        reason="Existing publication is tracked until its transaction boundary is repaired.",
        publishers=frozenset({owner}),
    )
    assert_publications_reviewed(config(tmp_path), reviewed={owner: allowance})
    with pytest.raises(AssertionError, match="unreviewed"):
        assert_publications_reviewed(config(tmp_path), reviewed={})
    _write_production_module(tmp_path, "shop/services.py", "def command(): pass")
    with pytest.raises(AssertionError, match="stale"):
        assert_publications_reviewed(config(tmp_path), reviewed={owner: allowance})
