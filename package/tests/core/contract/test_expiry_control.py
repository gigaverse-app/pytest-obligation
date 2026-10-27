from datetime import timedelta

import pytest
from sample_production.expiry import Cache

from pytest_obligation.expiry import ExpiryObservation, LossExpiresWithin

pytestmark = pytest.mark.usefixtures("production_host")


def probe(cache: Cache) -> LossExpiresWithin:
    return LossExpiresWithin(
        max_age=timedelta(seconds=60),
        binding=lambda: ExpiryObservation(
            publish=cache.publish,
            lose_update=cache.invalidate,
            present=cache.present,
            needs_update=lambda: cache.stale,
            lost_publications=lambda: cache.lost,
            remaining_seconds=lambda: cache.ttl,
            advance_by=cache.advance,
        ),
    )


def test_passive_expiry_needs_no_fake_production_recovery_command() -> None:
    probe(Cache())()


@pytest.mark.parametrize(
    "cache,diagnostic",
    [
        (Cache(ttl=-1, expires=False), "omitted or exceeded"),
        (Cache(ttl=120), "omitted or exceeded"),
        (Cache(expires=False), "survived its expiry"),
        (Cache(loses_update=False), "did not lose a publication"),
    ],
)
def test_expiry_exemption_rejects_broken_external_behavior(cache: Cache, diagnostic: str) -> None:
    with pytest.raises(AssertionError, match=diagnostic):
        probe(cache)()


def test_expiry_cannot_be_proven_by_a_test_written_publisher() -> None:
    cache = Cache()
    example = probe(cache).binding()
    assert isinstance(example, ExpiryObservation)
    example = example.model_copy(update={"publish": lambda: None})
    with pytest.raises(AssertionError, match="references no production"):
        LossExpiresWithin(binding=lambda: example, max_age=timedelta(seconds=60))()
