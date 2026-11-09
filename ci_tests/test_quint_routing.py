"""Registered contract code, models and tooling must select real replay execution."""

from routing import RoutingSnapshot

# A real contract: its sidecar declares the files pytest-quint-connect loads by name.
CONTRACT = "contracts/pytest_obligation/references/in_memory/fenced_lease"


class QuintRoutingTests(RoutingSnapshot):
    def test_registered_inputs_select_quint_and_unrelated_prose_does_not(self):
        for path in (
            "package/src/pytest_obligation/_cost_plugin.py",
            "package/src/pytest_obligation/host.py",
            "package/src/pytest_obligation/pytest_plugin.py",
            "contracts/quint.ini",
            f"{CONTRACT}/README.md",
            f"{CONTRACT}/model.qnt",
            f"{CONTRACT}/quint-connect.json",
            f"{CONTRACT}/conftest.py",
            f"{CONTRACT}/fenced_lease_driver.py",
            f"{CONTRACT}/history/rearm-9aa6ff2.py.txt",
            f"{CONTRACT}/test_fenced_lease_contract.py",
        ):
            with self.subTest(path=path):
                self.assertIn("quint", self.selection(path))
        # The index of contracts is prose; each contract's own README is part of its contract.
        for path in ("docs/unrelated.md", "contracts/README.md"):
            with self.subTest(path=path):
                self.assertNotIn("quint", self.selection(path))
