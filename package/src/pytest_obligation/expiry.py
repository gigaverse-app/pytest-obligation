"""An exemption whose stale external state is bounded by passive expiry."""

from collections.abc import Callable
from datetime import timedelta

from pytest_obligation.binding import assert_test_binding_delegates_to_production
from pytest_obligation.helpers import Binding, entered_binding
from pytest_obligation.models import HarnessModel


class ExpiryObservation(HarnessModel):
    """Production publication/update commands and independent external observations.

    ``lose_update`` calls the real invalidation producer with its publication
    suppressed. The scope owning the client and clock stays open for all checks.
    ``advance_by`` advances only external time; it must not delete or repair state.
    """

    publish: Callable[[], object]
    lose_update: Callable[[], object]
    present: Callable[[], bool]
    needs_update: Callable[[], bool]
    lost_publications: Callable[[], int]
    remaining_seconds: Callable[[], float]
    advance_by: Callable[[float], object]


class LossExpiresWithin(HarnessModel):
    """Prove a lost update leaves stale state only until the producer's real TTL.

    Unlike an active absorber, expiry is an external service behavior. The
    publisher and update producer must reach production, while the external
    clock is a test seam. No fake recovery command is required.
    """

    binding: Binding[ExpiryObservation]
    max_age: timedelta

    def __call__(self) -> None:
        assert self.max_age.total_seconds() > 0, "expiry bound must be positive"
        with entered_binding(self.binding) as example:
            for field in ("publish", "lose_update"):
                command = example.publish if field == "publish" else example.lose_update
                assert_test_binding_delegates_to_production(
                    adopter="bounded expiry exemption",
                    field=field,
                    binding=command,
                    production_shape="the real publication or invalidation producer",
                )
            example.publish()
            assert example.present(), "expiry control did not publish external state"
            assert not example.needs_update(), "published state was already stale before the lost update"
            lost = example.lost_publications()
            example.lose_update()
            assert example.lost_publications() > lost, "the update did not lose a publication"
            assert example.present() and example.needs_update(), "lost update did not leave observable stale state"
            remaining = example.remaining_seconds()
            assert 0 < remaining <= self.max_age.total_seconds(), "publisher omitted or exceeded the expiry bound"
            example.advance_by(remaining / 2)
            assert example.present(), "expiry observer lost state before the declared remaining TTL"
            example.advance_by(remaining / 2 + 0.01)
            assert not example.present(), "stale external state survived its expiry bound"
