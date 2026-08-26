# Stripe Issuing real-time authorization decisions

**Issue:** A card program performs slow or non-idempotent work in an authorization webhook, causing timeouts, inconsistent approvals, or duplicate ledger reservations.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Stripe Issuing real-time authorizations have strict response timing and may be retried. Make the decision from locally available policy and balances, reserve funds atomically, and reconcile later authorization updates and reversals.

**Source:** [Stripe Issuing real-time authorizations](https://docs.stripe.com/issuing/controls/real-time-authorizations)

## Controls

- verify webhook signatures against the raw body;
- deduplicate by immutable authorization/event identifiers;
- evaluate card status, spending controls, merchant category, currency, and available balance locally;
- reserve funds transactionally before approval;
- set a safe timeout/default policy and keep external calls off the critical path;
- reconcile capture, incremental update, reversal, and expiry.

## Verification

Test duplicate/out-of-order events, timeout, concurrent authorizations, partial/incremental amounts, offline/fallback behavior, reversal, currency conversion, and ledger failure. Confirm retries cannot reserve twice.

## Gotchas

Authorization is not settlement. A webhook acknowledgement without the required decision semantics may follow Stripe's default outcome. Logging payloads can expose cardholder and merchant data.
