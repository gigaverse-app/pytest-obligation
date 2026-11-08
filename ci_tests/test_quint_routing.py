"""Registered contract code, models and tooling must select real replay execution."""

import unittest

import test_routing


class QuintRoutingTests(unittest.TestCase):
    setUpClass = classmethod(test_routing.RoutingTests.setUpClass.__func__)
    tearDownClass = classmethod(test_routing.RoutingTests.tearDownClass.__func__)
    git = classmethod(test_routing.RoutingTests.git.__func__)
    commit = classmethod(test_routing.RoutingTests.commit.__func__)
    selection = test_routing.RoutingTests.selection

    def test_registered_inputs_select_quint_and_unrelated_prose_does_not(self):
        for path in (
            "package/src/pytest_obligation/_cost_plugin.py",
            "package/src/pytest_obligation/host.py",
            "package/src/pytest_obligation/pytest_plugin.py",
            "docs/quint/example/fixed.qnt",
            "docs/quint/example/audit.qnt",
            "docs/quint/example/adapter.py",
            "docs/quint/example/manifest.json",
            "docs/quint/example/README.md",
            "verification_tests/quint/test_report_merge_contract.py",
            "verification_tests/quint/test_session_host_contract.py",
            "verification_tests/quint/test_cost_baseline_contract.py",
        ):
            with self.subTest(path=path):
                self.assertIn("quint", self.selection(path))
        self.assertNotIn("quint", self.selection("docs/unrelated.md"))
