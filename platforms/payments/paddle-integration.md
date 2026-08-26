# paddle-integration

**Issue:** Integrating Paddle as a merchant of record for SaaS billing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Paddle acts as the merchant of record, handling VAT/sales tax automatically. The API and webhook model differ significantly from Stripe — prices are created in the Paddle dashboard and referenced by ID.

## Pattern / Solution
Use Paddle.js v2 for the checkout overlay or redirect flow. Prices are defined in the dashboard with billing periods. On backend, listen to subscription.created, transaction.completed, and subscription.cancelled webhooks. Verify via Paddle's public key signature.

## Gotchas
Paddle takes a higher revenue cut than Stripe but removes tax compliance burden. Price IDs are environment-specific — sandbox vs production IDs differ. Customer data is owned by Paddle, limiting CRM enrichment.

## Related
lemonsqueezy-integration, vat-calculation-eu, payment-provider-abstraction
