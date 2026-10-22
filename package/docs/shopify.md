# Shopify billing simulation

`pytest_obligation.integrations.shopify` supplies a dependency-free, in-process
provider simulator. It separates request acceptance, application, rejection and
meter visibility so an application's tests cannot treat a 202 as a paid bill.
Install the ordinary `pytest-obligation` package; no Shopify SDK, credentials or
extra is required. This is a test dependency, not a billing client.

```python
from datetime import UTC, datetime, timedelta
from pytest_obligation.integrations.shopify import (
    BillingEvent, BillingWindow, ShopifyBillingSimulator,
)

provider = ShopifyBillingSimulator()  # one app's idempotency namespace
now = datetime(2026, 1, 1, tzinfo=UTC)
event = BillingEvent(
    shop_id="shop-a", event_handle="messages", timestamp=now,
    idempotency_key="usage-1", quantity="10",
)
receipt = provider.send(event, rejection="NO_SUBSCRIPTION")
assert receipt.status_code == 202
assert provider.send(event).outcome == "replayed"
window = BillingWindow(start=now, end=now + timedelta(days=30))
assert provider.total(shop_id="shop-a", event_handle="messages", window=window) == 0
```

For asynchronous outcomes, `accept(event)` records the request without applying
it. A test controls the provider with `apply(key, visible=False)`, `make_visible(key)`
or `reject(key, reason)`. Retrying an accepted-but-unresolved request does not
decide its outcome. Rejected keys cannot become applied; a successful reversal
is a new signed event with a new key. There is no automatic lag or rollover clock.

`attempts` records calls including duplicates; `records` contains one immutable
record per accepted identity, including rejected identities. Use these independent
observations in the test oracle. Application code should see only its real
provider boundary: a receipt, a scoped meter total, or explicitly supplied
rejection evidence. Never let its reconciler inspect the simulator's private
ledger to resolve an ambiguity the real provider cannot resolve.

## Bind the real application

At the substituted send boundary, convert the application's existing request
to `BillingEvent`: `quantity` corresponds to wire `attributes.value`. Adapt the
receipt to the application's own response type. Keep credentials, HTTP retries,
commission rules and reconciliation in their existing owners. An async client
can use a small async wrapper around synchronous `provider.send`.

Use `ExternalCall` or `ProviderControl` at that boundary for lost replies and
worker interruption. Do not reset the simulator during recovery: the external
effect must survive application restart. A new test history gets a new instance.
`reset()` is only a fresh-world convenience, never a retention policy.

The generic [acknowledgement-only fault](interleavings.md#acknowledgement-without-application-opt-in-per-seam)
already exists. Use this simulator when the provider's permanent key consumption,
signed usage or delayed evidence matters. Do not add a second history scheduler.

## Evidence and explicit assumptions

The extraction is based on Gigaverse's billing simulator and its independent
provider-ledger controls; it imports no Gigaverse code. Public sources below
were checked on 2026-10-22. This is a bounded model of App Pricing billing events,
not a complete Shopify emulator or a claim about arbitrary App Events.

| Modeled behavior | Evidence or deliberate limit |
| --- | --- |
| 202 acknowledges receipt, not billing validation | [App Events API](https://shopify.dev/docs/api/app-events/2026-10) |
| Permanent billing-event keys, negative reversals | [Usage charges](https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing/subscription-billing/setup-usage-charges) |
| Separate billing processing and rejection evidence | [Billing-event walkthrough](https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing/subscription-billing/build-billing-event) |
| Explicit visibility lag | Scenario control; no fixed delay is asserted about Shopify |
| Shop/meter/half-open interval totals | Declared simulator model; caller supplies the cycle and evidence policy |
| Different input under an existing key raises ValueError | Test-design guard, not an emulated Shopify HTTP response |
| Valid finite nonzero quantities and aware timestamps only | Invalid wire payloads, authentication, throttling and API-version parsing are outside scope |

The meter is an aggregate. Equal totals alone do not identify individual events:
offsetting omissions, unrelated usage or signed reversals can hide discrepancies.
An adopter must state the reconciliation assumptions that make its verdict sound.
Subscription lifecycle, plan eligibility, taxes, currency conversion and automatic
rejection decisions remain outside this simulator. Rejection codes are explicit
scenario inputs, not guesses about which subscription state implies which code.

The [library controls](../tests/core/test_shopify_billing.py) run without services.
They cover burned keys, pending acceptance, visibility, signed/scoped totals,
immutable evidence and invalid scenario construction.
