"""
Django-bound conforming references, for the harness's own self-tests only.

The framework-free references live in :mod:`pytest_obligation.references.in_memory`;
this module holds the ones that need a real Django database. The same fence
applies: an adopter contract that imports these is measuring the reference
instead of its own domain.
"""

from typing import TYPE_CHECKING

from django.db.models import QuerySet

if TYPE_CHECKING:
    from django.contrib.contenttypes.models import ContentType


def reference_scheduled_selection_queryset() -> "QuerySet[ContentType]":
    """
    A primary-key range of a framework table: the shape the selection proofs accept.

    Used by the end-to-end scheduled-selection self-test, which needs a real
    queryset that passes authorship (defined here, inside the harness package),
    the index verdict (its own condition, a range on the primary key, positions
    the scan; a bare walk with no condition reads the whole index and is refused), and replica routing
    (the default database) — without borrowing any domain's production selection.

    The model import is deferred so importing this module does not require the
    app registry to be ready.
    """
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.filter(pk__gt=0).order_by("pk")


__all__ = ["reference_scheduled_selection_queryset"]
