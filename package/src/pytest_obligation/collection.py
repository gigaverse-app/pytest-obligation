"""Public selector semantics shared by generated-suite collection policies."""

from pathlib import Path


def requires_complete_suite(arguments: list[str], module: Path, class_name: str) -> bool:
    """A broad selector still requires the whole suite beside any narrow selectors."""
    for argument in arguments:
        path, *nodes = argument.split("::")
        selected_path = Path(path).resolve()
        if selected_path == module or selected_path in module.parents:
            if not nodes or nodes == [class_name]:
                return True
    return False
