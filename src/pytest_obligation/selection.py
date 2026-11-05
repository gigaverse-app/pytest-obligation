"""Framework-free identity selection and selection-completeness gap keys."""

from collections.abc import Callable, Iterable
from itertools import islice
from typing import Any, TypeVar

T = TypeVar("T")
SELECTION_COMPLETENESS_PROOF = "assert_selection_is_complete"


def identity(value: T) -> T:
    return value


def selected_identities(
    selection: Callable[[], Iterable[Any]], identity_of: Callable[[Any], Any], *, limit: int | None = None
) -> list[Any]:
    """Evaluate selection once and preserve its order, duplicates and optional consumption limit."""
    return [identity_of(row) for row in islice(selection(), limit)]


def is_selected(operation: Any, selection: Callable[[], Iterable[Any]], identity_of: Callable[[Any], Any]) -> bool:
    """Compare identities lazily; callers may return unhashable identities."""
    expected = identity_of(operation)
    return any(identity_of(item) == expected for item in selection())


def gap_combination(gap: str) -> str | None:
    """The combination in a complete selection-gap key, validating one value per path."""
    prefix = f"{SELECTION_COMPLETENESS_PROOF}["
    if not (gap.startswith(prefix) and gap.endswith("]")):
        return None
    inner = gap[len(prefix) : -1]
    parts = [part.partition(":") for part in inner.split(",")]
    assert inner and all(path and value and "|" not in value for path, _, value in parts), (
        f"{gap!r}: a selection-completeness gap names one value per state path, "
        f"'{SELECTION_COMPLETENESS_PROOF}[path:value,path:value]'; a gap on the whole proof would hide every combination"
    )
    return inner
