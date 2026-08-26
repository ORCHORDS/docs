# Stripe Quote Lifecycle and Conversion Controls

**Issue:** Draft quotes are treated as immutable offers, expired/canceled revisions remain actionable, or accepting a quote creates an invoice/subscription that the application fails to reconcile.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Model Stripe Quote states explicitly: draft is editable, finalization opens the offer, acceptance converts it, and cancellation/expiry makes it unusable. Persist quote ID, revision/number, customer, currency, line-item snapshot, expiration, status, and the resulting invoice/subscription/schedule IDs. Require server-side authorization and an idempotency key for finalize, accept, and cancel actions.

Before finalizing, verify product prices, tax, discounts, effective date, terms, and customer identity. After acceptance, re-fetch the Quote and created object: recurring quotes can create a subscription or future-effective subscription schedule; non-recurring quotes create a draft invoice. Provision only from the resulting billing object's verified lifecycle.

## Verification

Test draft revisions, finalize, duplicate acceptance, cancel from draft/open, expiry race, recurring now/future effective date, one-time quote, PDF retrieval authorization, webhook replay/order, stale UI revision, and line-item changes before finalization. Confirm a canceled or expired quote cannot be converted.

## Gotchas

A quote PDF is presentation, not authoritative state. Acceptance can create different object types based on recurring content and effective date. Draft invoices can still need finalization/payment handling. Do not expose file links or quote identifiers as authorization.

## Sources

- [Stripe — How quotes work](https://docs.stripe.com/quotes)
- [Stripe API — Quote object](https://docs.stripe.com/api/quotes/object)
