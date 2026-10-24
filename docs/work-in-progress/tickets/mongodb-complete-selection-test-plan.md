# Complete MongoDB selection observation

A native first-page cursor cannot represent an application's entire paginated
selection or its converted result objects. Observe the complete read once and
retain its returned rows beside every executed native find.

## Controls

- A production generator performs multiple pages and converts documents. Observe
  all returned objects without changing their order, shape or pagination.
- A later page with an unbounded leading index key and secondary-capable routing
  must fail the same shared checks even when the first page is healthy.
- Keep all existing cursor/query, write-death, lost-reply and transaction controls.

## Validation

All 40 real MongoDB tests pass on PyMongo 4.18.3 and the supported floor, 4.9.2.
The combined core, Prefect and MongoDB suite passes (1351 passed, one existing
optional skip). Ruff, Pyrefly and documentation checks pass.

The real Shopify selection probe observes the full SDK/HTTP/MongoDB path and
passes selection equivalence, native routing and index proofs. Other recovery
guarantee failures remain visible; this is not a full application adoption claim.

No application runtime, Due execution API, dependency pin or release tag changes.
