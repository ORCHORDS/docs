# PayPal Orders confirm-payment-source boundary

**Issue:** Some PayPal Orders flows require confirming a payment source after order creation. Treating confirmation as capture, retrying without identity controls, or trusting only the browser return can duplicate user steps or advance unpaid orders.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Persist the PayPal order ID, local checkout ID, intent, expected amount/currency, and current remote status. Send the documented request ID for retry safety where supported. Confirm only a payment source allowed for the order and environment; follow payer-action links through an allowlisted return flow. After return, fetch the order server-side and advance only from authoritative status.

Confirmation does not equal authorization or capture. Keep separate state transitions and idempotent fulfillment keyed to the final captured transaction. Reject amount, currency, merchant, or local ownership mismatch.

## Verification

Test timeout-before-response, repeated confirmation, payer cancellation, expired order, wrong environment, changed amount, 3DS/payer action, webhook-before-return, return-before-webhook, and capture retry.

## Gotchas

Do not put client secrets in browser code. Browser redirects are user navigation, not settlement evidence; webhooks also require signature verification and deduplication.

## Sources

- PayPal Developer, [Orders v2 API](https://developer.paypal.com/docs/api/orders/v2/)
- PayPal Developer, [PayPal-Request-Id](https://developer.paypal.com/api/rest/reference/idempotency/)
