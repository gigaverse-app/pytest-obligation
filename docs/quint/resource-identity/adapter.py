"""pytest-quint-connect driver: replay Quint histories against the shipped ResourceProvider, without database IO."""

import hashlib
import sys
from pathlib import Path

SHIPPED_389C5BB_SHA256 = "80cbc999951e8472d93cfbf3ec4c8df2b9c916a2e0dfbd19c1d5a8be023dd71a"


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
    if mutant == "shipped-389c5bb":
        # The exact pre-fix create(), run in the real module's namespace. The hash keeps this
        # frozen evidence from being edited until it agrees with the model.
        shipped = Path(__file__).with_name("create-389c5bb.py.txt")
        text = shipped.read_bytes()
        assert hashlib.sha256(text).hexdigest() == SHIPPED_389C5BB_SHA256, f"{shipped} was edited"
        namespace = dict(owed_references.__dict__)
        exec(compile(text, str(shipped), "exec"), namespace)
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

        def step(self, step):
            event, op = step.args, step.action
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
            elif op in ("delete", "rejectDelete"):
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
