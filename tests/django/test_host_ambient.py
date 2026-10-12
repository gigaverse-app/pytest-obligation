from pytest_obligation.integrations.django import django_host
from pytest_obligation.profiles.automatic_recovery import AMBIENT_CONTEXT_PROOFS


def test_declared_ambient_context_enrolls_its_restoration_proof():
    host = django_host(production_packages=set(), ambient_context=lambda: "tenant")
    assert set(AMBIENT_CONTEXT_PROOFS) <= set(host.sweep_proofs)


def test_no_ambient_context_makes_no_tenancy_claim():
    host = django_host(production_packages=set())
    assert not set(AMBIENT_CONTEXT_PROOFS) & set(host.sweep_proofs)
