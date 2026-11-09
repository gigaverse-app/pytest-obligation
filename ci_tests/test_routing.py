"""Exercise this consumer's real configuration against real Git snapshots."""

import subprocess
import unittest

from routing import RoutingSnapshot


class RoutingTests(RoutingSnapshot):
    def test_nested_or_new_pytest_collection_policy_forces_every_lane(self):
        for path in ("package/pyproject.toml", "package/.pytest.ini"):
            with self.subTest(path=path):
                self.reset()
                target = self.repo / path
                if target.exists():
                    target.write_text(
                        target.read_text().replace('testpaths = ["tests"]', 'testpaths = ["other_tests"]')
                    )
                else:
                    target.write_text("[pytest]\ntestpaths = other_tests\n")
                result = self.plan(self.base, self.commit())
                self.assertTrue(all(result.lanes.values()), result.model_dump_json())
                self.assertIn("fallback", result.reason)

    def test_prose_does_not_start_runtime_lanes(self):
        for path in (
            "README.md",
            "package/docs/adopting.md",
            "examples/adopter/README.md",
            "documentation/index.md",
            "mkdocs.yml",
            ".readthedocs.yaml",
            "docs/guide.rst",
            "md/guide.md",
            ".github/pull_request_template.md",
            ".github/ISSUE_TEMPLATE/bug.md",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), set())

    def test_documentation_only_change_selects_no_lane(self):
        # One real commit across the documentation surfaces, including the Read the Docs dependencies.
        self.assertEqual(
            self.selection(
                "README.md",
                "docs/ci.md",
                "documentation/index.md",
                "documentation/requirements.in",
                "documentation/requirements.txt",
                "mkdocs.yml",
                "examples/adopter/README.md",
            ),
            set(),
        )

    def test_documentation_site_dependencies_are_not_test_environment(self):
        for path in ("documentation/requirements.txt", "documentation/requirements.in"):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), set())

    def test_embedded_distribution_files_select_only_the_wheel_builders(self):
        # pyproject's readme and license-files are in the wheel: the build job validates it with twine and
        # check_metadata.py, and Due's conformance installs it. ci_tests/test_metadata.py exercises
        # check_metadata.py, which reads the README.
        for path, lanes in (
            ("package/README.md", {"package", "due", "contracts"}),
            ("package/LICENSE", {"package", "due"}),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), lanes)

    def test_global_environment_changes_keep_full_validation(self):
        for path in (
            "uv.lock",
            "examples/adopter/uv.lock",
            "package/pyproject.toml",
            "demos/wagtail_tasks/pyproject.toml",
            ".python-version",
            ".github/test-lanes.json",
            ".github/selector-constraints.txt",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), self.lanes)

    def edited(self, path, old, new):
        """Lanes selected by one commit that replaces old with new in path."""
        self.reset()
        file = self.repo / path
        text = file.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, old)
        file.write_bytes(text.replace(old, new).encode("utf-8"))
        result = self.plan(self.base, self.commit())
        self.assertNotIn("fallback", result.reason, result.model_dump_json())
        return {name for name, enabled in result.lanes.items() if enabled}

    def test_a_workflow_edit_selects_the_lanes_of_the_jobs_it_changes(self):
        workflow = ".github/workflows/ci.yml"
        # A comment changes no job: only the tests that read the workflow run.
        self.assertEqual(self.selection(workflow), {"contracts"})
        # One job's command runs that job's lane.
        self.assertEqual(
            self.edited(workflow, "pytest package/tests/mongodb -q", "pytest package/tests/mongodb -q -rA"),
            {"mongodb", "contracts"},
        )
        # The planner decides every lane, so changing it runs them all.
        planner = "  select-tests:\n    runs-on: ubuntu-latest"
        self.assertEqual(self.edited(workflow, planner, planner.replace("ubuntu-latest", "ubuntu-24.04")), self.lanes)

    def test_other_dependency_installers_keep_every_lane(self):
        for path in ("requirements.txt", "package/requirements-dev.txt", "poetry.lock", "pylock.toml"):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), self.lanes)

    def test_publisher_container_dependencies_start_its_consumers(self):
        # The sandbox smoke builds the publisher container from them; the contracts lane's Node tests do not.
        for path in ("publish/requirements.txt", "publish/Dockerfile"):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), {"actions"})

    def test_demo_recording_inputs_keep_the_complete_demo_lane(self):
        # contracts too: its job checks ci.yml, which names the README GIF test that reads them.
        for path in ("docs/demo.tape", "docs/demo_env.sh"):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), {"demos", "contracts"})

    def test_framework_test_and_deletion_keep_its_lane(self):
        test_file = next((self.repo / "package/tests/mongodb").glob("test_*.py")).relative_to(self.repo).as_posix()
        self.assertIn("mongodb", self.selection(test_file))
        self.assertIn("mongodb", self.selection(test_file, delete=True))

    def test_package_code_keeps_external_due_conformance(self):
        self.assertIn("due", self.selection("package/src/pytest_obligation/host.py"))

    # Framework lanes follow the import graph; the plugin is loaded into every session as a global module.
    FRAMEWORK_LANES = {"django", "django_psycopg2", "redis", "mongodb", "aiokafka", "prefect", "demos", "saleor"}

    def test_a_framework_integration_starts_only_the_lanes_that_import_it(self):
        integrations = "package/src/pytest_obligation/integrations"
        for module, lanes in (
            ("aiokafka.py", {"aiokafka"}),
            ("prefect.py", {"prefect"}),
            ("redis_server.py", {"redis"}),
            ("django/transactions.py", {"django", "django_psycopg2"}),
        ):
            with self.subTest(module=module):
                selected = self.selection(f"{integrations}/{module}")
                self.assertEqual(selected & self.FRAMEWORK_LANES, lanes)
                # Distribution, typing and external Due conformance still see every package change.
                self.assertLessEqual({"due", "package", "typecheck"}, selected)

    def test_the_pytest_plugin_and_what_it_imports_start_every_rooted_lane(self):
        rooted = {name for name, lane in self.resolved(self.base, self.base).config.lanes.items() if lane.roots}
        for path in ("pytest_plugin.py", "host.py"):
            with self.subTest(path=path):
                self.assertLessEqual(rooted, self.selection(f"package/src/pytest_obligation/{path}"))

    def test_a_subprocess_plugin_follows_the_module_that_loads_it(self):
        reporting = "package/src/pytest_obligation/reporting"
        loader = self.selection(f"{reporting}/collect.py")
        self.assertTrue(loader & {"core", "actions"}, loader)
        # At least the loader's lanes; the actions job also reaches it through collect.py's declaration.
        self.assertLessEqual(loader, self.selection(f"{reporting}/_nodeids_plugin.py"))

    def test_evidence_validators_only_start_their_consuming_lanes(self):
        self.assertEqual(
            self.selection("scripts/check_adoption_report.py"),
            # The core guard tests also import this validator; the Python graph must keep them.
            {
                "core",
                "minimum_models",
                "exploration",
                "redis",
                "prefect",
                "demos",
                "saleor",
                "actions",
                # The due job runs Due's own scripts/check_adoption_report.py in its checkout of
                # gigaverse-app/due; the planner resolves that path to this repository's copy.
                "due",
                "typecheck",
                "contracts",
            },
        )
        # The due job runs no case validator of its own name, so this repository's does not start it.
        self.assertNotIn("due", self.selection("scripts/check_adoption_cases.py"))

    def test_published_actions_only_start_their_consumers(self):
        # contracts too: these routing tests plan through every local action the workflow uses.
        self.assertEqual(self.selection("check/action.yml"), {"demos", "saleor", "actions", "contracts"})
        self.assertEqual(self.selection("test/action.yml"), {"actions", "contracts"})
        self.assertEqual(self.selection("report/action.yml"), {"actions", "contracts"})
        self.assertEqual(self.selection("publish/action.yml"), {"actions", "contracts"})
        self.assertEqual(self.selection("preview/preview.cjs"), {"actions", "contracts"})

    def test_python_changes_still_typecheck(self):
        self.assertIn("typecheck", self.selection("package/src/pytest_obligation/host.py"))

    def test_missing_history_and_explicit_full_checkpoint_run_every_lane(self):
        result = self.plan(self.base, self.base, full=True)
        self.assertTrue(all(result.lanes.values()), result.model_dump_json())
        # An unknown base either plans every lane or fails the planner, and a failed planner runs every
        # job (test_execution_admission.py requires that fallback on each one).
        try:
            result = self.plan("missing-history", self.base)
        except subprocess.CalledProcessError:
            return
        self.assertTrue(all(result.lanes.values()), result.model_dump_json())

    def test_documentation_dependency_selects_its_declared_reader(self):
        self.reset()
        reader = self.repo / "package/tests/core/test_declared_doc.py"
        reader.parent.mkdir(parents=True, exist_ok=True)
        reader.write_text("# gv:test-dependency: md/declared.md\ndef test_document(): pass\n")
        doc = self.repo / "md/declared.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("before\n")
        base = self.commit()
        doc.write_text("after\n")
        result = self.plan(base, self.commit())
        self.assertTrue(result.lanes["core"], result.model_dump_json())
        self.assertNotIn("fallback", result.reason)

    def test_execution_helpers_select_contracts_and_package(self):
        self.assertIn("contracts", self.selection("ci_tests/test_routing.py"))
        self.assertIn("package", self.selection("scripts/check_core_is_framework_free.py"))
        self.assertIn("package", self.selection("scripts/ci/check_metadata.py"))

    def test_example_adopter_code_at_any_depth_starts_the_action_smoke(self):
        # Files no test imports: only the explicit input globs can select the lane.
        for path in ("examples/adopter/new_module.py", "examples/adopter/adopter_app/new_module.py"):
            with self.subTest(path=path):
                self.assertIn("actions", self.selection(path))


if __name__ == "__main__":
    unittest.main()
