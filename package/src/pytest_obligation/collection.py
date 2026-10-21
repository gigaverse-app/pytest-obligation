"""Public selector semantics shared by generated-suite collection policies."""

from pathlib import Path


def assert_collected_proofs(expected: set[str], actual: set[str], suite: str) -> None:
    """A generated suite cannot certify a runtime after its required cases disappear."""
    assert not (expected - actual), f"{suite}: registered capability lost collected proofs: {sorted(expected - actual)}"


def requires_complete_suite(arguments: list[str], module: Path, class_name: str) -> bool:
    """A broad selector still requires the whole suite beside any narrow selectors."""
    for argument in arguments:
        path, *nodes = argument.split("::")
        selected_path = Path(path).resolve()
        if selected_path == module or selected_path in module.parents:
            if not nodes or nodes == [class_name]:
                return True
    return False
