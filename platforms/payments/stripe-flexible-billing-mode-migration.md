# Stripe flexible billing-mode migration

**Issue:** A subscription integration changes Stripe billing mode without modeling differences in proration, credits, invoice timing, and API-version behavior.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Stripe's flexible billing mode changes selected subscription billing behaviors. Treat migration as an accounting change: eligibility, API version, existing credits, pending updates, and customer-visible invoice effects must be evaluated before mutation.

**Source:** [Stripe subscription billing mode documentation](https://docs.stripe.com/billing/subscriptions/billing-mode)

## Controls

- inventory subscription states, schedules, trials, discounts, credit balances, and mixed intervals;
- preview representative changes and reconcile line items against the product's ledger rules;
- pin the Stripe API version used by migration workers and webhook consumers;
- mutate by immutable subscription ID with idempotency keys and durable job checkpoints;
- deploy to a cohort with a documented rollback/compensation procedure.

## Verification

- test clocks cover renewals, upgrades, downgrades, cancellation, trial end, and failed payment;
- previews and finalized invoices reconcile to expected currency minor units;
- duplicate jobs and webhook redelivery do not apply migration twice;
- dashboards compare invoice totals, credits, and support contacts before and after migration.

## Gotchas

- mode changes do not replace webhook-driven state reconciliation.
- past finalized invoices remain accounting records.
- never infer success from a client redirect; retrieve authoritative Stripe objects server-side.
