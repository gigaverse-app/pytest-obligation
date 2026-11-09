"""Exercise this consumer's real configuration against real Git snapshots."""

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

    def test_embedded_distribution_files_select_only_the_package_build(self):
        # pyproject's readme and license-files: twine and check_metadata.py validate them in the build job.
        for path in ("package/README.md", "package/LICENSE"):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), {"package"})

    def test_global_environment_changes_keep_full_validation(self):
        for path in (
            "uv.lock",
            "examples/adopter/uv.lock",
            "package/pyproject.toml",
            "demos/wagtail_tasks/pyproject.toml",
            ".python-version",
            ".github/workflows/ci.yml",
            ".github/test-lanes.json",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), self.lanes)

    def test_other_dependency_installers_keep_every_lane(self):
        for path in ("requirements.txt", "package/requirements-dev.txt", "poetry.lock", "pylock.toml"):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), self.lanes)

    def test_publisher_container_dependencies_start_its_consumers(self):
        self.assertEqual(self.selection("publish/requirements.txt"), {"actions", "contracts"})

    def test_demo_recording_inputs_keep_the_complete_demo_lane(self):
        for path in ("docs/demo.tape", "docs/demo_env.sh"):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), {"demos"})

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
        self.assertEqual(self.selection(f"{reporting}/_nodeids_plugin.py"), loader)

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
                "due",
                "typecheck",
                "contracts",
            },
        )

    def test_published_actions_only_start_their_consumers(self):
        self.assertEqual(self.selection("check/action.yml"), {"demos", "saleor", "actions"})
        self.assertEqual(self.selection("test/action.yml"), {"actions"})
        self.assertEqual(self.selection("report/action.yml"), {"actions", "contracts"})
        self.assertEqual(self.selection("publish/action.yml"), {"actions", "contracts"})
        self.assertEqual(self.selection("preview/preview.cjs"), {"actions", "contracts"})

    def test_python_changes_still_typecheck(self):
        self.assertIn("typecheck", self.selection("package/src/pytest_obligation/host.py"))

    def test_missing_history_and_explicit_full_checkpoint_run_every_lane(self):
        for result in (
            self.plan("missing-history", self.base),
            self.plan(self.base, self.base, full=True),
        ):
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
