# stripe-webhook-signature-verification

**Issue:** Verifying Stripe webhook signatures to prevent spoofed events
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Anyone can POST to your webhook URL. Signature verification confirms the request genuinely came from Stripe using HMAC-SHA256.

## Pattern / Solution
```typescript
// Node.js
const event = stripe.webhooks.constructEvent(
  rawBody,      // Buffer or string — MUST be raw bytes
  signatureHeader,
  webhookSecret,
);

// Cloudflare Workers (async WebCrypto)
const event = await stripe.webhooks.constructEventAsync(
  rawBody,
  signatureHeader,
  webhookSecret,
);
```

The `stripe-signature` header contains:
- `t=` timestamp (Unix seconds)
- `v1=` HMAC signature

Stripe rejects events older than 300 seconds by default (configurable via `tolerance` param).

## Gotchas
- The raw body must not be parsed or modified before verification — JSON.parse destroys it
- In Express, use `express.raw()` middleware on the webhook route, not `express.json()`
- Each webhook endpoint has its own secret; do not reuse the same secret across endpoints
- A 400 response causes Stripe to retry — return 200 even if you choose to ignore an event type

## Related
- `stripe-webhook-setup.md`
- `stripe-webhook-idempotency.md`
