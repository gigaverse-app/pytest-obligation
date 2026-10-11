"""Database-legal boundary values, shared by recovery and discovery proofs."""

from __future__ import annotations

from typing import Any

from django.db import DataError, IntegrityError, connection, models, transaction

from pytest_obligation.models import HarnessModel

POSITIVE_INTEGER_FIELDS = (
    models.PositiveBigIntegerField,
    models.PositiveIntegerField,
    models.PositiveSmallIntegerField,
)


class CandidateEdge(HarnessModel):
    """One database-legal value for one field that no validated writer produces."""

    field: str
    kind: str
    value: object

    @property
    def id(self) -> str:
        return f"{self.field}-{self.kind}"


def database_legal_edges(field: models.Field[Any, Any]) -> tuple[CandidateEdge, ...]:
    """The cheap boundary values a NOT NULL column accepts without model validation."""
    if not field.concrete or field.primary_key or field.null or field.is_relation:
        return ()
    if isinstance(field, (models.CharField, models.TextField, models.FileField)):
        # FileField is not a CharField, but stores its name in a varchar column.
        edges = [CandidateEdge(field=field.attname, kind="blank", value="")]
        if field.max_length:
            edges.append(CandidateEdge(field=field.attname, kind="max_length", value="x" * field.max_length))
        if field.choices:
            # Choices are enforced only by validation: a renamed or retired member stays in old rows.
            edges.append(CandidateEdge(field=field.attname, kind="unknown_choice", value=_unknown_choice(field)))
        return tuple(edges)
    if isinstance(field, models.IntegerField) and not isinstance(field, models.AutoField):
        edges = [CandidateEdge(field=field.attname, kind="zero", value=0)]
        # Positive fields carry a CHECK constraint; -1 cannot exist in such a row.
        if not isinstance(field, POSITIVE_INTEGER_FIELDS):
            edges.append(CandidateEdge(field=field.attname, kind="negative", value=-1))
        # The column's own maximum: a counter there cannot be incremented again.
        _minimum, maximum = connection.ops.integer_field_range(field.get_internal_type())
        edges.append(CandidateEdge(field=field.attname, kind="maximum", value=maximum))
        return tuple(edges)
    return ()


def _unknown_choice(field: models.Field[Any, Any]) -> str:
    """A value that fits the column and is no member of its choices (``unknown`` is a durable-work state)."""
    known = {str(value) for value, _label in field.flatchoices}
    width = field.max_length or 16
    for candidate in ("not-a-member", "~", "~~"):
        if candidate[:width] not in known:
            return candidate[:width]
    raise AssertionError(f"{field}: no unknown-choice edge fits the column")


def model_edges(model: type[models.Model]) -> tuple[CandidateEdge, ...]:
    """Every edge of every concrete field of ``model``, in field order; collection and suites share this list."""
    return tuple(edge for field in model._meta.concrete_fields for edge in database_legal_edges(field))


def write_unvalidated(model: type[models.Model], pk: Any, edge: CandidateEdge) -> bool:
    """
    ARRANGE: write a value the way legacy rows got it, without model validation.

    ``_base_manager`` because a scoped default manager would hide the row from
    the update while production, which builds its own queryset, still sees it.
    False when the database rejects the value: no row can hold it.
    """
    try:
        with transaction.atomic():
            updated = model._base_manager.filter(pk=pk).update(**{edge.field: edge.value})
    except (DataError, IntegrityError):
        return False
    assert updated == 1, f"{model._meta.label_lower}: the row {pk} vanished before {edge.id} was written"
    return True
