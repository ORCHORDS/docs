# lemonsqueezy-integration

**Issue:** Using Lemon Squeezy as a lightweight merchant of record for digital products
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Lemon Squeezy is optimized for indie SaaS and digital downloads. It provides a hosted checkout, handles tax, and exposes a simple REST API. Webhooks use HMAC-SHA256 with an X-Signature header.

## Pattern / Solution
Create products and variants in the dashboard. Embed checkout via a buy link or JS overlay. Handle subscription_created, order_created, and subscription_cancelled webhooks. Verify: HMAC-SHA256(rawBody, signingSecret) compared to X-Signature header.

## Gotchas
Lemon Squeezy does not support metered billing or usage-based pricing. Custom domains for checkout require a paid plan. Refunds issued in the dashboard do not always fire a webhook reliably — poll the API if needed.

## Related
paddle-integration, payment-provider-abstraction, invoice-generation-pdf
