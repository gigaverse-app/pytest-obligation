"""An in-process Shopify App Events billing simulator, not an HTTP client.

One instance represents one app's idempotency namespace. Application decisions
and reconciliation stay in the adopter. The provider's accepted-key ledger,
terminal decisions and delayed meter visibility are observed independently.
See ``docs/shopify.md`` for the modeled contract, provenance and limitations.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from pytest_obligation.models import HarnessModel


class BillingEvent(HarnessModel):
    """Normalized valid usage, not the Shopify wire body; quantity is units, not money."""

    shop_id: str = Field(min_length=1)
    event_handle: str = Field(min_length=1)
    timestamp: AwareDatetime
    idempotency_key: str = Field(min_length=1, max_length=64)
    quantity: Decimal

    @field_validator("quantity")
    @classmethod
    def finite_nonzero(cls, quantity: Decimal) -> Decimal:
        if not quantity.is_finite() or quantity == 0:
            raise ValueError("quantity must be finite and nonzero")
        return quantity


class BillingWindow(HarnessModel):
    """An explicitly supplied half-open billing interval; no implicit cycle rollover."""

    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end <= self.start:
            raise ValueError("billing window end must be after start")
        return self

    def contains(self, timestamp: datetime) -> bool:
        return self.start <= timestamp < self.end


class BillingReceipt(HarnessModel):
    """Acceptance metadata deliberately contains no application-success verdict."""

    idempotency_key: str
    status_code: Literal[202] = 202
    outcome: Literal["accepted", "replayed"]


class BillingRecord(HarnessModel):
    """Provider-only evidence; never return this record from the application's send seam."""

    event: BillingEvent
    state: Literal["accepted", "applied", "rejected"] = "accepted"
    visible: bool = False
    rejection: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.visible and self.state != "applied":
            raise ValueError("only applied usage may be visible")
        if (self.state == "rejected") != bool(self.rejection):
            raise ValueError("exactly rejected events carry a nonempty rejection code")
        return self


class ShopifyBillingSimulator:
    """Explicit provider state with immutable observations and no application callbacks.

    ``accept`` retains a request without deciding its outcome. ``send`` is the
    common convenience: accept then apply (possibly invisibly), or reject.
    A retry only acknowledges the existing key, including rejected or unresolved
    keys. Test controls resolve an unresolved key with ``apply`` or ``reject``.
    """

    def __init__(self) -> None:
        self._records: dict[str, BillingRecord] = {}
        self._attempts: list[BillingEvent] = []

    @property
    def records(self) -> tuple[BillingRecord, ...]:
        """Accepted identities, in acceptance order; each identity appears exactly once."""
        return tuple(self._records.values())

    @property
    def attempts(self) -> tuple[BillingEvent, ...]:
        """All valid calls, including retries; distinct from accepted identities and effects."""
        return tuple(self._attempts)

    def reset(self) -> None:
        """Start a fresh test world. This does not model erasure of provider history."""
        self._records.clear()
        self._attempts.clear()

    def accept(self, event: BillingEvent) -> BillingReceipt:
        existing = self._records.get(event.idempotency_key)
        if existing is not None and existing.event != event:
            # Test-design guard, not a prediction of Shopify's HTTP response.
            raise ValueError("idempotency key reused with different input")
        self._attempts.append(event)
        if existing is None:
            self._records[event.idempotency_key] = BillingRecord(event=event)
        return BillingReceipt(
            idempotency_key=event.idempotency_key, outcome="accepted" if existing is None else "replayed"
        )

    def send(self, event: BillingEvent, *, rejection: str | None = None, visible: bool = True) -> BillingReceipt:
        if rejection == "":
            raise ValueError("rejection code must be nonempty")
        receipt = self.accept(event)
        # Acceptance burns the key. Replaying cannot repair rejection or invent
        # a successful completion for a still-unresolved original request.
        if receipt.outcome == "accepted":
            if rejection is None:
                self.apply(event.idempotency_key, visible=visible)
            else:
                self.reject(event.idempotency_key, rejection)
        return receipt

    def apply(self, key: str, *, visible: bool = True) -> None:
        record = self._records[key]
        if record.state == "rejected":
            raise ValueError("a rejected key cannot be applied; replay cannot repair it")
        self._records[key] = record.model_copy(update={"state": "applied", "visible": record.visible or visible})

    def reject(self, key: str, reason: str) -> None:
        record = self._records[key]
        if record.state == "applied":
            raise ValueError("an applied event cannot be rejected")
        if record.state == "rejected" and record.rejection != reason:
            raise ValueError("a rejected event cannot change its rejection")
        self._records[key] = record.model_copy(update={"state": "rejected", "rejection": reason})

    def make_visible(self, key: str) -> None:
        record = self._records[key]
        if record.state != "applied":
            raise ValueError("only applied usage may become visible")
        self._records[key] = record.model_copy(update={"visible": True})

    def total(self, *, shop_id: str, event_handle: str, window: BillingWindow) -> Decimal:
        """Visible signed units for this shop/meter/window, not a per-event receipt."""
        return sum(
            (
                record.event.quantity
                for record in self._records.values()
                if record.visible
                and record.event.shop_id == shop_id
                and record.event.event_handle == event_handle
                and window.contains(record.event.timestamp)
            ),
            Decimal(0),
        )
