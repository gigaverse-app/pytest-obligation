"""Registered contract code, models and tooling must select real replay execution."""

import unittest

from routing import RoutingSnapshot


class QuintRoutingTests(RoutingSnapshot):

    def test_registered_inputs_select_quint_and_unrelated_prose_does_not(self):
        for path in (
            "package/src/pytest_obligation/_cost_plugin.py",
            "package/src/pytest_obligation/host.py",
            "package/src/pytest_obligation/pytest_plugin.py",
            "contracts/quint.ini",
            "contracts/README.md",
            "contracts/pytest_obligation/example/example_contract/model.qnt",
            "contracts/pytest_obligation/example/example_contract/quint-connect.json",
            "contracts/pytest_obligation/example/example_contract/conftest.py",
            "contracts/pytest_obligation/example/example_contract/example_contract_driver.py",
            "contracts/pytest_obligation/example/example_contract/history/audit.qnt",
            "contracts/pytest_obligation/references/in_memory/fenced_lease/test_fenced_lease_contract.py",
        ):
            with self.subTest(path=path):
                self.assertIn("quint", self.selection(path))
        self.assertNotIn("quint", self.selection("docs/unrelated.md"))
