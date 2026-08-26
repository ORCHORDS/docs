# PayPal shipment-tracking state

**Issue:** Adding tracking information to a PayPal transaction affects customer visibility and operational evidence. Duplicate submissions, wrong carrier codes, or linking tracking to the wrong capture can disclose another order and corrupt fulfillment state.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation
Bind the PayPal capture/transaction ID to the local order and merchant before sending tracking. Validate carrier and tracking-number formats without inventing status, use documented custom-carrier fields when needed, and make submission idempotent through a local operation key and reconciliation. Store request/response evidence and expose corrections through an audited workflow.

Tracking acceptance is not proof of delivery. Fulfillment state should reconcile carrier evidence, PayPal state, refunds/disputes, and local inventory independently.

## Verification
Test duplicate/retry, timeout-after-success, wrong capture ownership, unsupported/custom carrier, multiple shipments, corrected number, partial fulfillment, refund/dispute, and sandbox/production separation.

## Gotchas
Tracking numbers may contain personal/order information and should be access-controlled. Carrier scans are eventually consistent.

## Sources
- PayPal Developer, [Tracking API](https://developer.paypal.com/docs/api/tracking/v1/)
- PayPal Developer, [REST API idempotency](https://developer.paypal.com/api/rest/reference/idempotency/)
