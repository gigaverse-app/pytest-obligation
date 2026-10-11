"""Temporary PostgreSQL tables for the primitive and its conformance references."""

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection, models


@contextmanager
def model_tables(*model_types: type[models.Model]) -> Iterator[None]:
    """Create in dependency order; drop in reverse order even when the history fails."""
    with connection.schema_editor() as editor:
        for model in model_types:
            editor.create_model(model)
    try:
        yield
    finally:
        with connection.schema_editor() as editor:
            for model in reversed(model_types):
                editor.delete_model(model)
