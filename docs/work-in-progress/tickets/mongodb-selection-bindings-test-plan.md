# MongoDB selection binding test plan

The AI adoption has real MongoDB crash histories, but its host could not run the
shared query-plan or routing proofs. This change adds only those test capabilities.
It does not change any application or Due runtime, or introduce batch execution.

## Invariants and controls

- Capture the production cursor at its actual send boundary; unused queries,
  other clients and other collections do not count. Callback failures propagate
  and release the observation patch.
- Preserve ordering, limits, projection and collation; changing production read
  ordering changes the next captured query. The helper does not remove pagination.
- A normal bounded leading-key index passes. Missing indexes, an unrelated hinted
  index, and a bound only on a trailing key fail on real MongoDB plans.
- OR branches must all be served. A catalog-confirmed partial index passes;
  replacing it with a full index under the same name fails.
- Primary routing passes; primaryPreferred, secondaryPreferred and nearest cannot
  become green because the fixture has only one primary.
- Motor executor reads use the same observations. EOF and unsupported plan shapes
  remain missing evidence, not claimed coverage. No SQL buffer units are invented.

## Validation

Initial selection test collection failed because the API was absent.
The full MongoDB suite passes on both PyMongo 4.18 and the supported floor 4.9.2,
including existing wire-death, transaction, lost-reply and generated outbox histories.
Type checking and formatting are checked before publishing.

An application probe uses the actual Shopify `_billable_orders` path through its
persistence SDK and HTTP service against real MongoDB, for global and shop-scoped
reads. The probe also removes the actual billing index to verify the shared proof
rejects the resulting global scan. This is query evidence only; Shopify profile A
remains incomplete until its other recovery bindings are finished.
