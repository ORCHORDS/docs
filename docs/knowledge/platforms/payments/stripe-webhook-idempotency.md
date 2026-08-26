# stripe-webhook-idempotency

**Issue:** Making Stripe webhook handlers idempotent to prevent duplicate processing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stripe retries webhook delivery for up to 72 hours if your endpoint does not return a 2xx response. Without idempotency, retries cause duplicate orders, emails, or provisioning.

## Pattern / Solution
```typescript
async function handleWebhook(event: Stripe.Event) {
  const processed = await db.query(
    'SELECT 1 FROM processed_events WHERE stripe_event_id = ?',
    [event.id]
  );
  if (processed.rows.length > 0) return; // already handled

  await db.transaction(async (tx) => {
    await processEvent(tx, event);
    await tx.query(
      'INSERT INTO processed_events (stripe_event_id, processed_at) VALUES (?, NOW())',
      [event.id]
    );
  });
}
```

## Gotchas
- Use the event `id` (e.g., `evt_xxx`) as the idempotency key, not the object ID
- Store processed event IDs in a database, not in-memory (Workers are stateless)
- Clean up old processed event IDs after 30 days to prevent unbounded table growth
- Verify the event by re-fetching from Stripe API in high-security scenarios instead of trusting the webhook payload

## Related
- `stripe-webhook-setup.md`
- `stripe-webhook-retry-handling.md`
