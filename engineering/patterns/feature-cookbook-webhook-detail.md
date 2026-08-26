# feature-cookbook-webhook-detail

**Issue:** Webhooks — receive, sign, retry
**Date:** 2026-08-09
**Status:** documented

## Symptom
A customer reports "I subscribed but the account
isn't upgraded." You check the DB. The subscription
is there. The webhook never fired. Or the webhook
fired but the handler failed.

## Root cause
**Webhooks are async + fragile.** Handle them
carefully.

**Source:** Stripe — Webhook best practices.

## The "webhook" pattern

For a webhook, three things:
1. **Verify signature:** The sender
2. **Idempotency:** No double-process
3. **Retry:** Survive failures

## The "signature" pattern

For Stripe:
```ts
import Stripe from 'stripe';

const stripe = new Stripe(STRIPE_API_KEY);

app.post('/webhooks/stripe', async (req) => {
  const sig = req.headers.get('stripe-signature');
  const body = await req.text();

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig!, STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return new Response('Invalid signature', { status: 400 });
  }

  // Process
  await processEvent(event, env);
  return new Response('OK');
});
```

The signature is verified.

**Source:** Stripe webhooks:
https://stripe.com/docs/webhooks/signatures

## The "HMAC signature" pattern (generic)

For a generic HMAC:
```ts
import { createHmac, timingSafeEqual } from 'node:crypto';

async function verifySignature(
  payload: string,
  signature: string,
  secret: string,
): Promise<boolean> {
  const expected = createHmac('sha256', secret).update(payload).digest('hex');
  const expectedBuffer = Buffer.from(expected, 'hex');
  const signatureBuffer = Buffer.from(signature, 'hex');

  if (expectedBuffer.length !== signatureBuffer.length) return false;
  return timingSafeEqual(expectedBuffer, signatureBuffer);
}
```

The HMAC is verified.

## The "idempotency" pattern

For idempotency:
```ts
async function processEvent(event: WebhookEvent, env: Env): Promise<void> {
  const processed = await env.KV!.get(`webhook:${event.id}`);
  if (processed) return;

  await handleEvent(event, env);
  await env.KV!.put(`webhook:${event.id}`, '1', { expirationTtl: 86400 * 7 });
}
```

The event is processed once.

## The "retry" pattern

For retry:
```ts
async function withRetry<T>(fn: () => Promise<T>, maxAttempts = 3): Promise<T> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (attempt === maxAttempts - 1) throw err;
      if (!isRetryable(err)) throw err;
      await sleep(Math.min(2 ** attempt * 1000, 30_000));
    }
  }
  throw new Error('unreachable');
}
```

The handler is retried.

## The "200 OK fast" pattern

For 200 OK fast:
```ts
app.post('/webhooks', async (req) => {
  // 1. Parse the body
  const body = await req.text();
  const event = parseEvent(body);

  // 2. Enqueue the processing
  await env.QUEUE.send(event);

  // 3. Return 200 immediately
  return new Response('OK');
});
```

The webhook returns fast.

## The "DLQ" pattern

For DLQ:
```ts
async function processWithDLQ(event: WebhookEvent, env: Env, maxAttempts = 5): Promise<void> {
  const attempts = await getAttempts(event.id, env);

  try {
    await handleEvent(event, env);
    await env.KV!.delete(`attempts:${event.id}`);
  } catch (err) {
    if (attempts >= maxAttempts - 1) {
      await env.DLQ.send({ ...event, error: String(err) });
      return;
    }
    await env.KV!.put(`attempts:${event.id}`, String(attempts + 1));
    throw err;
  }
}
```

Failed events go to DLQ.

## The "outgoing webhook" pattern

For outgoing webhooks:
```ts
async function sendWebhook(url: string, payload: any, secret: string, env: Env): Promise<void> {
  const signature = createHmac('sha256', secret).update(JSON.stringify(payload)).digest('hex');

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-signature': signature,
          'x-attempt': String(attempt + 1),
        },
        body: JSON.stringify(payload),
      });

      if (response.ok) return;
      throw new Error(`HTTP ${response.status}`);
    } catch (err) {
      if (attempt === 2) throw err;
      await sleep(2 ** attempt * 1000);
    }
  }
}
```

The outgoing webhook is signed + retried.

## The "webhook observability" pattern

For observability:
- **Received:** Total received
- **Processed:** Successfully processed
- **Failed:** Failed
- **DLQ:** In DLQ
- **Latency:** Time to process

```ts
metrics.increment('webhook.received_total', { type: event.type });
metrics.increment('webhook.processed_total', { type: event.type });
metrics.histogram('webhook.duration_ms', duration, { type: event.type });
```

The webhook is monitored.

## The "webhook testing" pattern

For testing, use a tool:
- **Stripe CLI:** `stripe listen --forward-to localhost:8787/webhook`
- **ngrok:** Public URL for local
- **webhook.site:** Capture + inspect

```bash
stripe listen --forward-to localhost:8787/webhook
```

The webhook is tested.

## The "webhook security" pattern

For security:
- **Signature:** Verify
- **Timestamp:** Reject old (> 5 min)
- **HTTPS:** Always
- **IP allowlist:** For known senders

```ts
function isFresh(timestamp: number, toleranceSec = 300): boolean {
  return Math.abs(Date.now() / 1000 - timestamp) < toleranceSec;
}
```

The webhook is secure.

## The "webhook anti-pattern" anti-patterns

### 1. No signature verification
- **Issue:** Anyone can trigger
- **Fix:** Verify signature

### 2. No idempotency
- **Issue:** Double-process
- **Fix:** Idempotency keys

### 3. Slow response
- **Issue:** Sender times out, retries
- **Fix:** 200 fast + async process

### 4. No retry
- **Issue:** Transient failure = lost
- **Fix:** Retry with backoff

### 5. No DLQ
- **Issue:** Failed events lost
- **Fix:** DLQ

### 6. No monitoring
- **Issue:** Don't know about failures
- **Fix:** Metrics + alerts

## Verification
- **Test:** Signature is verified
- **Test:** Idempotency works
- **Test:** Retry works
- **Test:** DLQ captures
- **Live:** Webhook health
- **Audit:** Quarterly review

## Gotchas
- **The "no signature" anti-pattern.** Verify.
- **The "no idempotency" anti-pattern.** Idempotency
  keys.
- **The "slow response" anti-pattern.** 200 fast.

## Related
- `feature-cookbook-webhook.md`
- `feature-cookbook-billing.md`
- `feature-cookbook-queues.md`
- `feature-cookbook-event-driven.md`
- `idempotency-keys.md`
- `feature-cookbook-error-recovery.md`
- Stripe: https://stripe.com/docs/webhooks
