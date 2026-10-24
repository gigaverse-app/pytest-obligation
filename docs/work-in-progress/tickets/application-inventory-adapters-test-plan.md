# Inventory Due applications and explicit wrappers

The backend report cannot claim complete application scope while static inventory omits Due decorators and application wrappers. Preserve non-importing discovery and require explicit wrapper names. Let actions parse source with the adopter Python syntax. This changes report metadata, not behavioral evidence.

- [x] Red controls: direct Due and configured wrapper declarations are absent before the change.
- [x] Core discovery finds both, preserves source/class identity and never imports the application; unknown wrappers remain excluded.
- [x] Collection and report CLI preserve configured wrappers and reuse current-run collected node IDs.
- [x] Actual composite collect/report scripts execute against Python 3.14 syntax and an explicit wrapper, reuse one current-run collected node ID, and report one skipped test without importing application code.
- [x] Scan the actual backend tree on Python 3.14 and compare discovered suite identities with current report evidence.
- [x] Reporting/collection validation: 88 passed. Pyrefly: 0 errors after installing the pinned demo dependencies.
- [ ] Publish a reviewable PR and adopt the released action inputs in consuming workflows.

Measured backend scan: default discovery found 5 suites; configuring its single public-suite wrapper found all 37 baseline reported applications with no unreadable files or unmatched identities. This verifies the existing report inventory; scheduled selections and other repositories still need their separate audit. Local execution evidence: `/tmp/inventory-adapters-first.log`, `/tmp/inventory-action-smoke.py`, `/tmp/backend-static-inventory.json`.
