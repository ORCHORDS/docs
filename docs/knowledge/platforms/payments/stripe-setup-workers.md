# stripe-setup-workers

**Issue:** Initializing Stripe SDK inside Cloudflare Workers environment
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workers runs in V8 isolates without Node.js built-ins. The standard `stripe` npm package requires careful initialization to avoid runtime errors around `fetch` and crypto.

## Pattern / Solution
```typescript
import Stripe from 'stripe';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
      apiVersion: '2024-06-20',
      httpClient: Stripe.createFetchHttpClient(),
    });
    // use stripe client
  }
};
```

Set `STRIPE_SECRET_KEY` as a Workers secret via `wrangler secret put STRIPE_SECRET_KEY`.

## Gotchas
- Never use the Node HTTP client in Workers; always pass `httpClient: Stripe.createFetchHttpClient()`
- `apiVersion` must be pinned to avoid surprise breaking changes on Stripe's end
- Do not instantiate the client at module level if you need per-request env bindings

## Related
- `stripe-webhook-setup.md`
- `stripe-payment-intents.md`
