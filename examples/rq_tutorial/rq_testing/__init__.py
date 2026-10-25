"""What an RQ maintainer would ship for applications: RQ's worker contract, with RQ's own properties declared once.

pytest-obligation's RQ integration builds the contract from RQ's real worker,
heartbeats, cleanup and retries. This module adds what only RQ's maintainers
decide: which behaviours of the pinned RQ version every application's contract
should expect, so no application has to discover or restate them.
"""

from typing import Any

from pytest_obligation import ObligationContract, Profile
from pytest_obligation.integrations.rq import worker_contract

#: How the pinned RQ version behaves, declared once for every application. Each entry is a strict
#: expected failure: if a later RQ version behaves differently, the case fails and the entry goes.
RQ_PROPERTIES = {
    Profile.B: {
        "assert_stale_token_is_rejected": (
            "RQ identifies a running job by its id, not by the execution holding it, so a worker whose job "
            "was already cleaned up can still record a result for it"
        )
    }
}


def job_contract(connection: Any, **application: Any) -> ObligationContract:
    """RQ's contract with its worker, for one of the application's jobs."""
    return worker_contract(connection, gaps=RQ_PROPERTIES, **application)
