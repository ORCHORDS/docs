# stripe-webhook-setup

**Issue:** Setting up Stripe webhooks in a Cloudflare Workers endpoint
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stripe sends webhook events to notify your server of asynchronous changes. You need an endpoint that verifies the signature and processes events reliably.

## Pattern / Solution
```typescript
export async function handleStripeWebhook(request: Request, env: Env): Promise<Response> {
  const signature = request.headers.get('stripe-signature');
  const body = await request.text();

  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(
      body,
      signature!,
      env.STRIPE_WEBHOOK_SECRET,
    );
  } catch (err) {
    return new Response('Webhook signature verification failed', { status: 400 });
  }

  // Process event
  switch (event.type) {
    case 'checkout.session.completed':
      await handleCheckoutComplete(event.data.object);
      break;
  }

  return new Response('OK');
}
```

Register the endpoint in Dashboard > Developers > Webhooks.

## Gotchas
- Always read the raw body as text before parsing — do not call `request.json()`
- Use `constructEventAsync` in Workers (async) vs `constructEvent` in Node (sync)
- Return 200 quickly; do heavy processing in a queue or background task
- Add webhook endpoint to staging and production separately

## Related
- `stripe-webhook-signature-verification.md`
- `stripe-webhook-idempotency.md`
- `stripe-webhook-retry-handling.md`
