# Stripe Subscription Schedule Phase Governance

**Issue:** Multi-phase contracts are edited as ordinary subscriptions, causing surprise prorations, phase drift, conflicting updates, or accidental cancellation when a schedule should have been released.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Model the Stripe Subscription Schedule as the authority for planned changes. Persist the schedule ID, current phase, phase boundaries, end behavior, source contract revision, and the last processed event. Use phase `duration` on API versions where Stripe removed `iterations`, and pin/test the account and webhook API versions before migration.

Separate lifecycle actions: updating phases changes future policy; releasing leaves the underlying subscription running without remaining scheduled changes; canceling can cancel the associated subscription. Gate each action by current schedule status and an operator intent token. Preview invoice/proration effects before applying a material amendment.

## Verification

In a sandbox, test not-started and active schedules, phase transitions, release, cancel, overlapping operator updates, webhook replay/out-of-order delivery, discounts, trial phases, tax, and API-version upgrade. Re-fetch the schedule after writes and reconcile local projections from Stripe state. Verify no access decision relies only on the UI request succeeding.

## Gotchas

A schedule supports a limited number of phases and cannot encode every contract indefinitely. Dates, anchors, and proration interact. A release is not a refund and a cancellation is not a release. API-version changes can remove parameters, so generated clients and stored request templates need upgrade tests.

## Sources

- [Stripe subscription schedule use cases](https://docs.stripe.com/billing/subscriptions/subscription-schedules/use-cases)
- [Stripe changelog — phase duration replaces iterations](https://docs.stripe.com/changelog/clover/2025-09-30/remove-iterations)
