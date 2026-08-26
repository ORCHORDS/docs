# Stripe early fraud warning lifecycle

**Issue:** A merchant treats an early fraud warning as a dispute, ignores it, or refunds without reconciling later warning/dispute/payment events.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Stripe early fraud warnings indicate card-network fraud reports before or without a formal dispute. Model warning, payment, refund, dispute, and evidence states separately and make the response policy amount/risk-aware.

**Source:** [Stripe early fraud warnings](https://docs.stripe.com/disputes/measuring#early-fraud-warnings)

## Controls

- ingest webhook events idempotently by immutable IDs;
- retrieve the authoritative payment/warning;
- decide refund, service restriction, or review through documented policy;
- prevent duplicate refund across warning and dispute workflows;
- preserve evidence and customer communication;
- feed confirmed outcomes into fraud controls.

## Verification

Test warning before/after refund, later dispute, duplicate/out-of-order events, uncaptured payment, partial refund, multiple warnings, and webhook delay. Ledger and fulfillment state must reconcile.

## Gotchas

A warning is not a dispute and not proof of customer intent. Refund timing may not prevent every dispute or fee. Do not automatically punish an account without reviewed evidence.
