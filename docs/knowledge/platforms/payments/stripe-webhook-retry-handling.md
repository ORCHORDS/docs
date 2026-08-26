# stripe-webhook-retry-handling

**Issue:** Handling Stripe webhook retries and failures gracefully
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stripe retries failed webhook deliveries with exponential backoff for up to 72 hours. Your handler must be fast, idempotent, and return 200 even for events you don't handle.

## Pattern / Solution
```typescript
export async function handleWebhook(request: Request): Promise<Response> {
  const event = await verifyAndParseEvent(request);

  // Respond immediately — process async
  const ctx = { waitUntil: (p: Promise<any>) => p }; // Workers context
  ctx.waitUntil(processEventAsync(event));

  return new Response('OK', { status: 200 });
}

async function processEventAsync(event: Stripe.Event) {
  try {
    switch (event.type) {
      case 'invoice.paid': await handleInvoicePaid(event); break;
      default: console.log(`Unhandled event type: ${event.type}`);
    }
  } catch (err) {
    // Log but don't re-throw — we already returned 200
    await logError(err, event);
  }
}
```

## Gotchas
- Never return 4xx or 5xx for events you don't handle — this triggers retries unnecessarily
- Returning 200 before processing completes risks data loss on Worker crash; use Queues for durability
- Monitor the Stripe webhook dashboard for delivery failure rates
- Stripe sends events out of order — use event timestamps, not arrival order, for sequencing

## Related
- `stripe-webhook-setup.md`
- `stripe-webhook-idempotency.md`
