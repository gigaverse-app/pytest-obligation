"""Read the database row independently of a stale in-memory model instance."""

from collections.abc import Iterable
from typing import Any

from django.db.models import Model


def persisted_values(model: type[Model], pk: Any, fields: Iterable[str] | None = None) -> dict[str, Any] | None:
    """Selected paths, or all concrete columns; None once the row is deleted."""
    columns = [field.attname for field in model._meta.concrete_fields] if fields is None else fields
    return model._base_manager.filter(pk=pk).values(*columns).first()
