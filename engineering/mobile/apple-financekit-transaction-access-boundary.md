# Apple FinanceKit transaction-access boundary

**Issue:** FinanceKit can expose sensitive financial accounts and transactions with user authorization. Treating authorization as permanent, uploading broad histories, or failing to reconcile updates creates privacy and correctness failures.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** restricted capability

## Controls and implementation
Check platform, regional, entitlement, and authorization availability before presenting the feature. Explain the narrow purpose and request access in user context. Minimize fields and time range, process locally where possible, encrypt retained records, and maintain deletion/revocation workflows. Use stable framework identifiers only within their documented scope and make imports idempotent.

Model unavailable, denied, authorized, changed, and revoked states. Reconcile updates without treating absence as deletion until the framework contract confirms it.

## Verification
Test denial/revocation, empty history, duplicate/update transactions, account removal, region/device unsupported, process death, clock/currency differences, deletion, and restore.

## Gotchas
Financial data is highly sensitive and may carry legal obligations beyond platform permission. Framework access is not consent for unrelated analytics or cloud synchronization.

## Sources
- Apple Developer, [FinanceKit](https://developer.apple.com/documentation/financekit)
- Apple Developer, [Protecting user privacy](https://developer.apple.com/documentation/uikit/protecting_the_user_s_privacy)
