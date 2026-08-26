# Stripe Test Clock Deterministic Billing Scenarios

**Issue:** Billing tests depend on wall-clock waits or ad hoc timestamp edits, leaving renewals, trials, dunning, schedule transitions, and webhook-driven access changes unverified.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Create an isolated Stripe sandbox simulation/test clock for one scenario, attach only test customers and billing objects created for that clock, and advance frozen time through explicit checkpoints. Treat clock advancement as asynchronous: wait for the clock to return to `ready` using its events or status before asserting invoice, payment, subscription, and entitlement state.

Write scenario manifests containing starting time, products/prices, expected events, expected object states, and checkpoints. Make webhook consumers idempotent and record event IDs so a deterministic simulation also tests replay handling. Delete completed simulations to limit clutter.

## Verification

Cover trial end, successful and failed renewal, retry/dunning, mid-cycle upgrade, customer balance, schedule phase change, month-end/leap-day anchor, cancellation, and delayed webhook processing. Assert both Stripe objects and the application's access/ledger projection at each ready checkpoint. Run unrelated scenarios in separate clocks.

## Gotchas

Time can only advance forward, and advancement limits depend on attached objects. Processing takes time after the request. Test clocks operate in sandboxes and do not prove live payment-method behavior, network faults, or production configuration parity. Deleting a simulation also removes its associated test objects.

## Sources

- [Stripe test clocks API and advanced usage](https://docs.stripe.com/billing/testing/test-clocks/api-advanced-usage)
- [Stripe test clocks overview](https://docs.stripe.com/billing/testing/test-clocks)
