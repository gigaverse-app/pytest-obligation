"""pytest-quint-connect driver: apply Quint events to the current checkout's real report merge API."""

import ast
import hashlib
import inspect
import sys
from pathlib import Path
from typing import Any

SHIPPED_389C5BB_SHA256 = "964d808f9a012748c9f926bbce853aaf06f5da1e8dad64d1fbe5100156f8b120"


def create(root: Path, work: Path, mutant: str | None = None):
    sys.path.insert(0, str(root / "package/src"))
    from pytest_obligation.profiles import reporting
    from pytest_obligation.profiles.coverage import Assessment, CaseEvidence, ProfileCoverage, SuiteCoverage
    from pytest_obligation.profiles.failures import FailureEvidence

    expected = (root / "package/src/pytest_obligation/profiles/reporting.py").resolve()
    assert Path(reporting.__file__).resolve() == expected, (reporting.__file__, expected)
    merge = reporting.merge_reports
    if mutant == "incremental-admission":
        # Move the real implementation's commit loop back inside preflight.
        # This is the old defect as a source mutation, not an adapter-side model.
        tree = ast.parse(inspect.getsource(merge))
        function = tree.body[0]
        commit = function.body[-1]
        assert isinstance(commit, ast.For) and ast.unparse(commit.target) == "(old, case)"
        mutation = commit.body
        function.body.pop()

        class Incremental(ast.NodeTransformer):
            def visit_Expr(self, node):
                text = ast.unparse(node)
                if text == "pairs.append((old, case))":
                    return mutation
                return node

            def visit_Assign(self, node):
                if ast.unparse(node.targets[0]) == "additions[suite]":
                    return ast.copy_location(ast.parse("target[suite] = report").body[0], node)
                return node

        tree = ast.fix_missing_locations(Incremental().visit(tree))
        work.mkdir(parents=True, exist_ok=True)
        source = work / "incremental-admission.py"
        source.write_text(ast.unparse(tree) + "\n")
        namespace = dict(reporting.__dict__)
        exec(compile(tree, str(source), "exec"), namespace)
        merge = namespace["merge_reports"]
    elif mutant == "shipped-389c5bb":
        # The exact pre-fix merge_reports, run in the real module's namespace. The hash keeps
        # this frozen evidence from being edited until it agrees with the model.
        shipped = Path(__file__).with_name("merge_reports-389c5bb.py.txt")
        text = shipped.read_bytes()
        assert hashlib.sha256(text).hexdigest() == SHIPPED_389C5BB_SHA256, f"{shipped} was edited"
        namespace = dict(reporting.__dict__)
        exec(compile(text, str(shipped), "exec"), namespace)
        merge = namespace["merge_reports"]
    elif mutant not in (None, "replace-case-identity"):
        raise ValueError(f"unknown implementation mutant: {mutant}")

    class Adapter:
        def __init__(self):
            self.target = {}
            self.references = {}
            self.rejected = False

        @staticmethod
        def case(payload):
            outcomes = (
                {}
                if payload == "empty"
                else {
                    "setup": ["passed"],
                    "call": ["failed" if payload == "failed" else "passed"],
                    **({"teardown": ["passed"]} if payload != "incomplete" else {}),
                }
            )
            return CaseEvidence(
                family="behavior",
                collected=payload != "empty",
                selected=payload != "empty",
                outcomes=outcomes,
                durations=[0.125] * len(outcomes),
                failures=[FailureEvidence(phase="call", kind="check", message="Independent failed proof.")]
                if payload == "failed"
                else [],
            )

        def suite(self, payload):
            return SuiteCoverage(
                name="contract",
                profiles={
                    "A": ProfileCoverage(
                        title="Recovery",
                        assessment=Assessment(state="claimed"),
                        cases={"first": self.case(payload), "second": self.case("passed")},
                    )
                },
            )

        def remember(self):
            for name, suite in self.target.items():
                if name not in self.references:
                    self.references[name] = (suite, dict(suite.profiles["A"].cases))

        def step(self, step):
            event = step.args
            op = step.action
            if op == "inspect":
                return
            if op == "init":
                self.target = {"main": self.suite("empty"), "later": self.suite("empty")}
                self.references = {}
                self.rejected = False
                self.remember()
                return
            assert op in ("merge", "reject"), event
            payload = event["payload"]
            shard = {"main": self.suite(payload)}
            incompatible = shard["main"]
            if event["location"] == "later-suite":
                shard["extra"] = self.suite(payload)
                shard["later"] = incompatible = self.suite(payload)
            else:
                assert event["location"] == "same-suite", event
            if op == "reject":
                kind = event["mismatch"]
                last = incompatible.profiles["A"].cases["second"]
                if kind == "family":
                    last.family = "incompatible"
                elif kind == "debt":
                    from pytest_obligation.debt import DebtEntry

                    last.debt = DebtEntry(case="second", kind="known-defect", reason="Reviewed incompatibility.")
                elif kind == "declaration":
                    last.declaration = "not applicable"
                elif kind == "case-set":
                    incompatible.profiles["A"].cases.pop("second")
                elif kind == "source":
                    from pytest_obligation.profiles.coverage import SourceLocation

                    incompatible.source = SourceLocation(path="different.py", line=1)
                elif kind == "assessment":
                    incompatible.profiles["A"].assessment = Assessment(state="declined")
                else:
                    raise ValueError(f"unknown mismatch: {kind}")
            self.rejected = False
            try:
                merge(self.target, shard)
            except AssertionError:
                self.rejected = True
            if not self.rejected:
                if mutant == "replace-case-identity":
                    cases = self.target["main"].profiles["A"].cases
                    cases["first"] = cases["first"].model_copy(deep=True)
                self.remember()

        @staticmethod
        def projection(case):
            return {
                "setup": len(case.outcomes.get("setup", [])),
                "call": len(case.outcomes.get("call", [])),
                "teardown": len(case.outcomes.get("teardown", [])),
                "bad": any(value != "passed" for values in case.outcomes.values() for value in values),
                "selected": case.selected,
                "collected": case.collected,
                "durationTicks": round(sum(case.durations) * 8),
                "failureCount": len(case.failures),
            }

        def observe(self) -> dict[str, Any]:
            result = {"extraExists": "extra" in self.target, "rejected": self.rejected}
            result["identityRetained"] = all(
                self.target.get(name) is suite
                and all(suite.profiles["A"].cases.get(key) is case for key, case in cases.items())
                for name, (suite, cases) in self.references.items()
            )
            for name in ("main", "later", "extra"):
                suite = self.target.get(name)
                result[name + "Verified"] = suite.verified if suite is not None else False
                for key in ("first", "second"):
                    case = suite.profiles["A"].cases[key] if suite is not None else self.case("empty")
                    result[name + key.title()] = self.projection(case)
            return result

        def close(self):
            pass

    return Adapter()
