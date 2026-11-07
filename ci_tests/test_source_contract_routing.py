"""Source proofs and their executable contracts must retain their CI lane."""

import unittest

import test_routing


class SourceContractRoutingTests(unittest.TestCase):
    setUpClass = classmethod(test_routing.RoutingTests.setUpClass.__func__)
    tearDownClass = classmethod(test_routing.RoutingTests.tearDownClass.__func__)
    git = classmethod(test_routing.RoutingTests.git.__func__)
    commit = classmethod(test_routing.RoutingTests.commit.__func__)
    selection = test_routing.RoutingTests.selection

    def test_executable_contract_inputs_select_source_contracts(self):
        for path in (
            "package/src/pytest_obligation/profiles/reporting.py",
            "package/src/pytest_obligation/profiles/coverage.py",
            "package/src/pytest_obligation/profiles/reporting.proofs.dfy",
            "veripy-project.json",
            "verification_tests/source_contracts/test_report_source_contract.py",
            "scripts/source_contracts/required-tests.json",
            "scripts/source_contracts/mutations.py",
            "scripts/bootstrap_source_verifier.py",
            "tooling/source-contracts/verifier.patch",
            "docs/source-contracts/report-merge.md",
            "docs/quint/report-merge/adapter.py",
            "scripts/quint/replay.py",
        ):
            with self.subTest(path=path):
                self.assertIn("source_contracts", self.selection(path))
        self.assertNotIn("source_contracts", self.selection("docs/unrelated.md"))
