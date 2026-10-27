from pathlib import Path

from pytest_obligation.coverage.config import CoverageConfig
from pytest_obligation.coverage.scan import scan
from pytest_obligation.coverage.sites import DJANGO


def test_external_bridge_counts_its_adopter_and_explicit_scope_preserves_inventory(tmp_path: Path) -> None:
    app = tmp_path / "shop"
    app.mkdir()
    (app / "__init__.py").write_text("")
    (app / "orders.py").write_text(
        "from vendor.transport import after_commit\n"
        "from celery import shared_task\n"
        "def admit():\n    after_commit(send)\n"
        "def send():\n    task.delay()\n"
    )
    config = CoverageConfig(
        root=tmp_path,
        production_packages=("shop",),
        source_roots=(".",),
        test_paths=("tests",),
        kinds=(DJANGO,),
        detect_sites=False,
        bridges={"vendor.transport.after_commit": 1},
        baseline={"shop.orders.admit": 1},
    )
    report = scan(config)
    report.raise_for_problems()
    assert set(report.sites) == {"shop.orders.admit"}
    assert set(report.dispositions) == {"shop.orders.admit"}
