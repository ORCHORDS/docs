# Stripe Tax registration effective-date controls

**Issue:** Enabling tax calculation without the correct jurisdiction registration and effective date can collect tax too early, too late, or not at all. Threshold alerts are evidence for review, not legal determinations.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented — tax decisions require qualified review

## Decision

Maintain a reviewed registration ledger outside transient dashboard state, then configure Stripe Tax registrations to match approved jurisdictions and effective dates. Separate threshold monitoring, authority registration, Stripe configuration, collection, filing, and remittance.

## Controls

- Record jurisdiction, registration type/number where appropriate, authority status, effective/end dates, owner, and evidence.
- Require qualified tax approval before collection begins or ends.
- Reconcile Stripe threshold inputs with non-Stripe sales channels.
- Schedule future registrations only from approved dates.
- Test tax-inclusive/exclusive behavior before activation.
- Update existing subscriptions, invoices, and Payment Links explicitly; global enablement may not retrofit them.
- Restrict and audit registration changes.
- Preserve closed-period evidence and corrections.

## Verification

Test sales before/on/after effective dates, refunds, subscriptions spanning activation, inclusive and exclusive prices, exempt customers, multiple channels, and registration end dates. Reconcile collected tax by jurisdiction to Stripe reports and the filing ledger.

## Gotchas

Stripe monitoring may not see external transactions or all facts creating nexus. Registration rules and grace periods change. Software does not replace advice from the relevant authority or qualified professional.

## Sources

- [Stripe Tax setup and registrations](https://docs.stripe.com/tax/set-up)
- [Stripe: Use Stripe to register for sales tax](https://docs.stripe.com/tax/use-stripe-to-register)
