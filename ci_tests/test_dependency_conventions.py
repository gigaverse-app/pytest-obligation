"""Shared declarations retain per-reader scope, including newly added readers."""

from pytest_selective.impact_graph import GraphCache
from pytest_selective.impact_selection import affected
from routing import RoutingSnapshot


class DependencyConventionTests(RoutingSnapshot):
    def selected_readers(self, revision, inputs, readers):
        config = self.resolved(revision, revision).config.graph
        cache = GraphCache(self.repo / ".test-impact/conventions.sqlite3")
        try:
            return set(affected(self.repo, revision, revision, config, cache, inputs).selected) & readers
        finally:
            cache.close()

    def test_each_contract_reads_only_its_own_model_and_history(self):
        self.reset()
        tests = list(self.repo.glob("contracts/**/test_*_contract.py"))
        readers = {path.relative_to(self.repo).as_posix() for path in tests}
        for test in tests:
            for source in [test.with_name("model.qnt"), *test.parent.glob("history/**/*.*")]:
                path = source.relative_to(self.repo).as_posix()
                with self.subTest(input=path):
                    self.assertEqual(
                        self.selected_readers(self.base, [path], readers),
                        {test.relative_to(self.repo).as_posix()},
                    )

    def test_new_demo_sources_select_only_their_own_inventory(self):
        self.reset()
        tests = list(self.repo.glob("demos/*/test_handoff_inventory.py"))
        readers = {path.relative_to(self.repo).as_posix() for path in tests}
        sources = []
        for test in tests:
            source = test.with_name(f"new_{test.parent.name}_source.py")
            source.write_text("VALUE = 1\n", encoding="utf-8")
            sources.append(source.relative_to(self.repo).as_posix())
        head = self.commit()
        for test, source in zip(tests, sources, strict=True):
            with self.subTest(input=source):
                self.assertEqual(
                    self.selected_readers(head, [source], readers),
                    {test.relative_to(self.repo).as_posix()},
                )

    def test_new_contract_inherits_the_convention_without_a_sidecar(self):
        self.reset()
        directory = self.repo / "contracts/new_example"
        directory.mkdir()
        files = {
            "test_example_contract.py": "def test_example(): pass\n",
            "model.qnt": "module example {}\n",
            "quint-connect.json": "{}\n",
            "README.md": "Example contract\n",
            "history/example.txt": "frozen history\n",
        }
        for name, content in files.items():
            target = directory / name
            target.parent.mkdir(exist_ok=True)
            target.write_text(content, encoding="utf-8")
        head = self.commit()
        readers = {p.relative_to(self.repo).as_posix() for p in self.repo.glob("contracts/**/test_*_contract.py")}
        for name in ("model.qnt", "quint-connect.json", "README.md", "history/example.txt"):
            with self.subTest(input=name):
                self.assertEqual(
                    self.selected_readers(head, [f"contracts/new_example/{name}"], readers),
                    {"contracts/new_example/test_example_contract.py"},
                )
