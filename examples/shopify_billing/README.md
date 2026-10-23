# Billing receipts, delayed meters and rejected keys

This small SQLite application records usage as `pending`, submits it, and records
only `sent` on a receipt. Its explicit reconciliation command combines a meter
with separately supplied rejection evidence. It never resends from reconciliation.

Run from the repository root:

```bash
uv sync --all-packages --locked
uv run --no-sync pytest package/tests/core/test_shopify_billing.py integration_tests/core/test_shopify_billing_example.py -v
```

No network service or credential is needed. The test imports the same
[`BillingApplication`](application.py) that owns the SQL decisions. Its
[`binding`](bindings.py) uses the public simulator and `EvidenceConfluence` engine;
pytest parametrizes the generated permutations, duplicates, recovery gaps and
batches. No separate schedule generator is introduced.

The two events are accepted once each. Event `a` applies but is initially absent
from the meter. Event `b` is rejected and its key stays consumed. Expected local
states are written independently before execution:

| Available evidence | a | b |
| --- | --- | --- |
| None | sent | sent |
| Meter only | sent | sent |
| Rejection only | sent | rejected |
| Both | confirmed | rejected |

Counterfeit controls change the real application after its normal SQL execution:
confirming directly from a receipt, or confirming everything when any meter usage
appears. The same generated history rejects both on its outcome invariant.
A separate file-backed SQLite test loses a reply after provider application,
closes the application connection, and retries the same command on a fresh
connection. Two calls leave one external effect and one confirmed local mark.

## What this establishes

This is a focused provider/evidence example using the standalone E engine. It is
not a complete A–J `ObligationContract` adoption and generates no whole-profile
conformance claim. A real adopter must assess recovery scheduling, admission,
ownership, retention and retry policy, and enroll its own production bindings.
See the [adoption walkthrough](../../package/docs/adopting.md).

The example assumes exclusive ownership of all usage in one shop/meter/cycle,
with no offsetting unexplained events. It demonstrates a bounded reconciliation
policy, not a generally sound inference from any equal aggregate. Rejection
evidence is supplied explicitly; its origin could be an operator or a correlated
provider query. The simulator does not prescribe which API the application uses.
The restart test replays the same command inputs; it does not prove an automatic
recovery scheduler or persistence of the entire request payload.

See the [simulator contract and evidence register](../../package/docs/shopify.md).
No Gigaverse pricing, commissions, account roles or service clients are included.
