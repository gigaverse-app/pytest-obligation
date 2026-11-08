"""pytest-quint-connect driver: drive production pytest configuration and host APIs from Quint-generated events."""

import hashlib
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest

from pytest_obligation import host, pytest_plugin

SHIPPED_389C5BB_SHA256 = "7abe6ac9e0ea7a686633b2db414b269af189c1b24b928f29776b59ac17094ad8"


class Adapter:
    def __init__(self, root: Path, work: Path, mutant: str | None) -> None:
        self.root = root
        self.work = work
        self.original = host._host
        self.configs: list[pytest.Config] = []
        self.manual_calls = 0
        self.application_calls = 0
        self.manual = host.Host(production_packages={"manual"})
        self.application = host.Host(production_packages={"A"})
        self.patches: list[Any] = []
        original_scope = pytest_plugin.hosted
        if mutant == "shipped-389c5bb":
            # The exact pre-fix pytest_configure, run in the real module's namespace. The hash
            # keeps this frozen evidence from being edited until it agrees with the model.
            shipped = Path(__file__).with_name("pytest_configure-389c5bb.py.txt")
            text = shipped.read_bytes()
            assert hashlib.sha256(text).hexdigest() == SHIPPED_389C5BB_SHA256, f"{shipped} was edited"
            namespace = {**vars(pytest_plugin), "configure": host.configure}
            exec(compile(text, str(shipped), "exec"), namespace)
            self.patches.append(patch.object(pytest_plugin, "pytest_configure", namespace["pytest_configure"]))
        elif mutant == "eager-previous-resolution":

            @contextmanager
            def eager(value: Any):
                host.current_host()
                with original_scope(value) as current:
                    yield current

            self.patches.append(patch.object(pytest_plugin, "hosted", eager))
        elif mutant is not None:
            raise ValueError(mutant)
        # The inner sessions load the plugin with -p; entry-point autoload would register it twice.
        self.patches.append(patch.dict(os.environ, {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}))
        module = ModuleType("quint_replay_application")
        module.make_host = self.application_factory  # type: ignore[attr-defined]
        self.patches.append(patch.dict(sys.modules, {module.__name__: module}))
        for replacement in self.patches:
            replacement.start()

    def manual_factory(self) -> host.Host:
        self.manual_calls += 1
        return self.manual

    def application_factory(self) -> host.Host:
        self.application_calls += 1
        return self.application

    def configure(self, name: str, *, application: bool) -> pytest.Config:
        directory = self.work / name
        directory.mkdir()
        ini = directory / "pytest.ini"
        ini.write_text(
            "[pytest]\n" + ("due_work_harness_host = quint_replay_application:make_host\n" if application else ""),
            encoding="utf-8",
        )
        config = pytest.Config.fromdictargs(
            {}, ["-c", str(ini), "--rootdir", str(directory), "-p", "pytest_obligation.pytest_plugin"]
        )
        self.configs.append(config)
        config._do_configure()
        return config

    def step(self, step: Any) -> None:
        event, op = step.args, step.action
        if op in ("initFactory", "initManual"):
            host.configure(self.manual_factory if event["kind"] == "factory" else self.manual)
        elif op == "configureA":
            self.first = self.configure("first", application=True)
        elif op == "resolveApplication" or op == "resolveManual":
            host.current_host()
        elif op == "cleanupA":
            self.first._ensure_unconfigure()
        elif op == "configureWithoutIni":
            self.second = self.configure("second", application=False)
        elif op == "cleanupB":
            self.second._ensure_unconfigure()
        elif op != "inspect":
            raise ValueError(op)

    def observe(self) -> dict[str, Any]:
        # Inspecting through current_host would itself resolve a factory and hide
        # premature imports. Resolution is a separate generated API event.
        current = host._host
        if current is self.manual:
            identity = "manual"
        elif current is self.application:
            identity = "A"
        elif current == self.manual_factory:
            identity = "manual_factory"
        elif callable(current):
            identity = "application_factory"
        else:
            identity = "unrecognized"
        return {"host": identity, "manualCalls": self.manual_calls, "applicationCalls": self.application_calls}

    def close(self) -> None:
        try:
            for config in reversed(self.configs):
                config._ensure_unconfigure()
        finally:
            host.configure(self.original)
            for replacement in reversed(self.patches):
                replacement.stop()


def create(root: Path, work: Path, mutant: str | None = None) -> Adapter:
    return Adapter(root, work, mutant)
