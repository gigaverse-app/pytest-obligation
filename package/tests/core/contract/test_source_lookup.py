"""Binding review must inspect its source without walking unrelated modules."""

import importlib.util
import sys
from types import ModuleType
from typing import Any

import pytest

from pytest_obligation.binding import authored_inversion_names
from pytest_obligation.contract import _adopter_annotation_defect


@pytest.mark.parametrize("case", ["annotated", "unannotated", "swallowed", "reraised"])
def test_binding_review_does_not_scan_unrelated_modules(tmp_path, monkeypatch, case):
    class UnrelatedModule(ModuleType):
        reads = 0

        def __getattribute__(self, name: str) -> Any:
            if name == "__file__":
                self.reads += 1
            return super().__getattribute__(name)

    unrelated = UnrelatedModule("unrelated_source_probe")
    unrelated.__file__ = str(tmp_path / "unrelated.py")
    monkeypatch.setitem(sys.modules, unrelated.__name__, unrelated)
    path = tmp_path / "test_binding_source.py"
    path.write_text(
        "def annotated():\n"
        "    # ARRANGE\n    # REAL PRODUCTION\n    # EXTERNAL SEAM\n    # OBSERVE\n"
        "    return 1\n\n"
        "def unannotated():\n    return 1\n\n"
        "def swallowed():\n"
        "    try:\n        assert False\n"
        "    except AssertionError:\n        return True\n\n"
        "def reraised():\n"
        "    try:\n        assert False\n"
        "    except AssertionError:\n        raise\n"
    )
    spec = importlib.util.spec_from_file_location("binding_source_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    binding = vars(module)[case]
    if case in {"annotated", "unannotated"}:
        defect = _adopter_annotation_defect("source probe", binding)
        assert (defect is None) is (case == "annotated")
        if defect is not None:
            assert "missing adopter evidence annotations" in defect
    else:
        names = authored_inversion_names(binding)
        assert ("AssertionError" in names) is (case == "swallowed")
    assert unrelated.reads == 0, "reviewing one binding scanned an unrelated module's filesystem path"


def test_decorated_callable_reviews_the_same_wrapper_as_its_bytecode(tmp_path, monkeypatch):
    path = tmp_path / "test_callable_source.py"
    path.write_text(
        "from functools import wraps\n\n"
        "def annotated(original):\n"
        "    @wraps(original)\n"
        "    def wrapper(self):\n"
        "        # ARRANGE\n        # REAL PRODUCTION\n        # EXTERNAL SEAM\n        # OBSERVE\n"
        "        return original(self)\n"
        "    return wrapper\n\n"
        "class CallableProbe:\n"
        "    @annotated\n"
        "    def __call__(self):\n"
        "        return 1\n"
    )
    spec = importlib.util.spec_from_file_location("callable_source_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    # The callable resolver checks the __call__ wrapper's bytecode. Its source
    # must not silently unwrap to the unannotated method below that wrapper.
    assert _adopter_annotation_defect("callable probe", module.CallableProbe()) is None
