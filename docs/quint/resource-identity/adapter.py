"""Replay Quint histories against the shipped ResourceProvider, without database IO."""

import ast
import inspect
import sys
import textwrap
from pathlib import Path


def create(root: Path, work: Path, mutant: str | None = None):
    sys.path.insert(0, str(root / "package/src"))
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            INSTALLED_APPS=["pytest_obligation"],
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        )
    django.setup()
    from pytest_obligation.integrations.django import owed_references

    expected = (root / "package/src/pytest_obligation/integrations/django/owed_references.py").resolve()
    assert Path(owed_references.__file__).resolve() == expected, (owed_references.__file__, expected)
    provider_type = owed_references.ResourceProvider
    original_create = provider_type.create
    original_list = provider_type.list
    if mutant == "length-allocation":
        # Compile a deliberate mutation of the real creation method, preserving
        # all its actual resource construction/storage code except the allocator.
        tree = ast.parse(textwrap.dedent(inspect.getsource(original_create)))
        function = tree.body[0]
        assert isinstance(function.body[0], ast.AugAssign)
        assert ast.unparse(function.body[0].target) == "self._created"
        function.body[0] = ast.parse("self._created = len(self.resources) + 1").body[0]
        tree = ast.fix_missing_locations(tree)
        work.mkdir(parents=True, exist_ok=True)
        source = work / "length-allocation.py"
        source.write_text(ast.unparse(tree) + "\n")
        namespace = dict(owed_references.__dict__)
        exec(compile(tree, str(source), "exec"), namespace)
        provider_type.create = namespace["create"]
    elif mutant == "copy-listed-objects":

        def copied(self):
            return [resource.model_copy(deep=True) for resource in original_list(self)]

        provider_type.list = copied
    elif mutant is not None:
        raise ValueError(f"unknown implementation mutant: {mutant}")

    class Adapter:
        def __init__(self):
            self.provider = None
            self.issued = []
            self.first_objects = {}
            self.rejected = False

        def apply(self, event):
            op = event["op"]
            if op == "inspect":
                return
            if op == "init":
                self.provider = provider_type()
                self.issued = []
                self.first_objects = {}
                self.rejected = False
            elif op == "create":
                resource = self.provider.create()
                self.issued.append(int(resource.name.removeprefix("resource-")))
                self.first_objects.setdefault(resource.name, resource)
                self.rejected = False
            elif op in ("delete", "reject-delete"):
                self.rejected = False
                try:
                    self.provider.delete(f"resource-{event['target']:04d}")
                except KeyError:
                    self.rejected = True
            else:
                raise ValueError(f"unknown event: {event}")

        def observe(self):
            resources = self.provider.list()
            return {
                "live": [int(resource.name.removeprefix("resource-")) for resource in resources],
                "issued": list(self.issued),
                "identityRetained": all(self.first_objects.get(resource.name) is resource for resource in resources),
                "rejected": self.rejected,
            }

        def close(self):
            provider_type.create = original_create
            provider_type.list = original_list

    return Adapter()
