# Adyen balance-platform sweep controls

**Issue:** Balance Platform sweeps can move funds automatically between balance accounts on schedules and conditions. A mis-scoped account, priority, currency, or amount rule can drain operational funds repeatedly before a human notices.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Treat sweep configuration as audited financial infrastructure. Resolve source and destination balance-account ownership, legal entity, currency, direction, trigger, schedule, amount type, priority, and effective state before creation. Require least-privilege roles and dual review for production changes. Store provider sweep/configuration IDs and an immutable local change record.

Model configuration separately from executions. Ingest sweep transactions idempotently, reconcile them to both balance accounts and bank/settlement evidence, and alert on failure, unexpected direction, amount, currency, frequency, or residual balance. Pause safely rather than deleting evidence when investigating.

## Verification

Test scheduled and threshold triggers, multiple priorities, insufficient balance, currency mismatch, disabled accounts, duplicate webhook/API events, timeout-after-create, daylight-saving/calendar boundaries, modification during execution, and rollback. Confirm sandbox identifiers cannot reach production.

## Gotchas

A configured sweep is not a guaranteed transfer; execution and settlement can fail or be delayed. Priority interactions and account eligibility are provider contracts, not assumptions. Automated movement may require treasury and regulatory review.

## Sources

- Adyen Docs, [Manage sweeps](https://docs.adyen.com/platforms/manage-funds/manage-sweeps/)
- Adyen API Explorer, [Balance Platform API](https://docs.adyen.com/api-explorer/balanceplatform/latest/overview)
