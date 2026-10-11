"""
The root-owned gap probes, exercised in both directions.

These probes exist so an adopter's ``detect``/``prove``/exemption evidence is a
binding rather than a hand-rolled assertion. That only pays off if the probes
themselves are pinned, which is what this module does — every one of them can
otherwise pass for the wrong reason and nobody would see it.
"""

import pytest
from sample_production import cache

from pytest_obligation.gap_probes import LossDropsOnlyANotification, LossIsAbsorbedElsewhere
from pytest_obligation.host import Host, hosted

# Every test here binds an absorbing path the probe must recognise as production.
pytestmark = pytest.mark.usefixtures("production_host")


class _Effect:
    """A cache-shaped effect: present, absent, and re-derivable on read."""

    def __init__(self, *, rederives: bool = True) -> None:
        self.present: set[int] = set()
        self.rederives = rederives
        self._ids = iter(range(1, 100))

    def strand(self) -> int:
        """Publish the work without dispatching the effect."""
        return next(self._ids)

    def observe(self, identity: int) -> bool:
        return identity in self.present

    def absorb(self, identity: int) -> None:
        # The production read path the exemption names; a cache that does not
        # rederive on read only reads.
        if self.rederives:
            cache.rederive(self.present, identity)
        else:
            cache.read_only(self.present, identity)


def test_an_exemption_whose_absorbing_path_produces_the_effect_holds() -> None:
    effect = _Effect()
    LossIsAbsorbedElsewhere(strand=effect.strand, observe=effect.observe, absorb=effect.absorb)()


def test_an_exemption_whose_absorbing_path_does_nothing_is_refused() -> None:
    """The reason claims something re-establishes the effect. Make it."""
    effect = _Effect(rederives=False)
    with pytest.raises(AssertionError, match="losing this callback loses the work"):
        LossIsAbsorbedElsewhere(strand=effect.strand, observe=effect.observe, absorb=effect.absorb)()


def test_an_exemption_whose_effect_was_never_absent_is_refused() -> None:
    """
    The positive control.

    If the effect is present before the absorbing path runs, the probe cannot
    tell "the loss is absorbed" from "the dispatch was never suppressed" — and
    the second reading is the one that makes an exemption look sound.
    """
    effect = _Effect()

    def strand_without_suppressing() -> int:
        identity = effect.strand()
        effect.present.add(identity)
        return identity

    with pytest.raises(AssertionError, match="never actually suppressed"):
        LossIsAbsorbedElsewhere(strand=strand_without_suppressing, observe=effect.observe, absorb=effect.absorb)()


def test_a_test_authored_absorbing_path_is_refused() -> None:
    """
    An exemption is a claim about PRODUCTION absorbing the loss.

    A test-side absorber proves only that the test can produce the effect,
    which is never what the exemption's reason says.
    """
    effect = _Effect()

    def absorb_here(identity: int) -> None:
        effect.present.add(identity)

    with pytest.raises(AssertionError, match="absorb is test code that references no production"):
        LossIsAbsorbedElsewhere(strand=effect.strand, observe=effect.observe, absorb=absorb_here)()


def test_production_is_what_the_host_says_it_is() -> None:
    """The same absorber is test code under a host that names no production package."""
    effect = _Effect()
    with hosted(Host()), pytest.raises(AssertionError, match="absorb is test code that references no production"):
        LossIsAbsorbedElsewhere(strand=effect.strand, observe=effect.observe, absorb=effect.absorb)()


class _Announcement:
    """A best-effort notification beside product state the producer commits on its own."""

    def __init__(self, *, sends: bool = True, writes_product: bool = False) -> None:
        self.sent: set[int] = set()
        self.committed: dict[int, str] = {}
        self.sends = sends
        self.writes_product = writes_product
        self._ids = iter(range(1, 100))

    def strand(self) -> int:
        """Commit the product state; the notification's dispatch is lost."""
        identity = next(self._ids)
        self.committed[identity] = "scheduled"
        return identity

    def notified(self, identity: int) -> bool:
        return identity in self.sent

    def product(self, identity: int) -> str | None:
        return self.committed.get(identity)

    def deliver(self, identity: int) -> None:
        cache.read_only(self.sent, identity)
        if self.sends:
            self.sent.add(identity)
        if self.writes_product:
            self.committed[identity] = "announced"


def _drops_only(announcement: _Announcement) -> LossDropsOnlyANotification:
    return LossDropsOnlyANotification(
        strand=announcement.strand,
        notified=announcement.notified,
        product=announcement.product,
        deliver=announcement.deliver,
    )


def test_a_notification_nothing_waits_for_holds() -> None:
    _drops_only(_Announcement())()


def test_a_dispatch_that_also_writes_product_state_is_refused() -> None:
    """Delivering it changes what the product reads, so losing it loses more than a notification."""
    with pytest.raises(AssertionError, match="does more than notify"):
        _drops_only(_Announcement(writes_product=True))()


def test_product_state_that_waits_for_the_dispatch_is_refused() -> None:
    announcement = _Announcement()

    def strand_awaiting_the_dispatch() -> int:
        identity = announcement.strand()
        del announcement.committed[identity]
        return identity

    with pytest.raises(AssertionError, match="something waits for it"):
        _drops_only(announcement).model_copy(update={"strand": strand_awaiting_the_dispatch})()


def test_a_notification_that_was_never_suppressed_is_refused() -> None:
    """The positive control before delivery: absence must be the dispatch's doing."""
    announcement = _Announcement()

    def strand_without_suppressing() -> int:
        identity = announcement.strand()
        announcement.sent.add(identity)
        return identity

    with pytest.raises(AssertionError, match="never actually suppressed"):
        _drops_only(announcement).model_copy(update={"strand": strand_without_suppressing})()


def test_an_observation_the_dispatch_never_produces_is_refused() -> None:
    """The positive control after delivery: `notified` must see what this dispatch does."""
    with pytest.raises(AssertionError, match="produced no notification"):
        _drops_only(_Announcement(sends=False))()


def test_a_test_authored_deliverer_is_refused() -> None:
    announcement = _Announcement()

    def deliver_here(identity: int) -> None:
        announcement.sent.add(identity)

    with pytest.raises(AssertionError, match="deliver is test code that references no production"):
        _drops_only(announcement).model_copy(update={"deliver": deliver_here})()
