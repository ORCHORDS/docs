# webhook-implementation

**Issue:** Webhook patterns — receive, send, retry, security
**Date:** 2026-08-09
**Status:** documented

## Symptom
A vendor sends a webhook to your app. The webhook is
received. The handler takes 30 seconds. The vendor's
connection times out. The vendor retries. Your handler
runs again. The data is duplicated.

## Root cause
**Webhooks have timeouts + retries.** Your handler must be
fast, idempotent, and reliable.

**Source:** Stripe webhook docs:
https://stripe.com/docs/webhooks

## The "receive" pattern

```ts
// Webhook endpoint
export async function onRequestPost(request: Request, env: Env): Promise<Response> {
  // 1. Verify the signature
  const signature = request.headers.get('Stripe-Signature');
  if (!signature) return new Response('Missing signature', { status: 400 });

  const body = await request.text();
  const event = verifyStripeSignature(body, signature, env.STRIPE_WEBHOOK_SECRET);

  // 2. Process the event (fast!)
  await processStripeEvent(event, env);

  // 3. Return 200 quickly
  return new Response('OK', { status: 200 });
}
```

The handler is fast (the heavy work is async).

## The "verify signature" pattern

For Stripe:
```ts
function verifyStripeSignature(payload: string, header: string, secret: string): Stripe.Event {
  const [timestampPart, signaturePart] = header.split(',');
  const timestamp = parseInt(timestampPart.split('=')[1]);
  const signature = signaturePart.split('=')[1];

  // 1. Check the timestamp (within 5 min)
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - timestamp) > 300) {
    throw new Error('Timestamp too old');
  }

  // 2. Compute the HMAC
  const signedPayload = `${timestamp}.${payload}`;
  const expected = crypto.createHmac('sha256', secret).update(signedPayload).digest('hex');

  // 3. Compare
  if (!crypto.timingSafeEqual(Buffer.from(signature, 'hex'), Buffer.from(expected, 'hex'))) {
    throw new Error('Invalid signature');
  }

  return JSON.parse(payload);
}
```

The signature is verified; the timestamp is checked; replay
attacks are blocked.

## The "idempotency" pattern

For retries, use an idempotency key:
```ts
async function processStripeEvent(event: Stripe.Event, env: Env): Promise<void> {
  // 1. Check if already processed
  const processed = await env.KV.get(`webhook:${event.id}`);
  if (processed) return;

  // 2. Process the event
  switch (event.type) {
    case 'payment_intent.succeeded':
      await handlePaymentSucceeded(event.data.object, env);
      break;
    case 'customer.subscription.created':
      await handleSubscriptionCreated(event.data.object, env);
      break;
    // ... etc
  }

  // 3. Mark as processed
  await env.KV.put(`webhook:${event.id}`, '1', { expirationTtl: 86400 * 7 });  // 7 days
}
```

The idempotency key is the event ID.

## The "async processing" pattern

For slow processing, queue the event:
```ts
async function processStripeEvent(event: Stripe.Event, env: Env): Promise<void> {
  const processed = await env.KV.get(`webhook:${event.id}`);
  if (processed) return;

  // Queue the event for async processing
  await env.WEBHOOK_QUEUE.send(event);
  await env.KV.put(`webhook:${event.id}`, '1', { expirationTtl: 86400 * 7 });
}
```

The webhook returns 200 quickly; the worker processes the
queue.

## The "send" pattern

For sending webhooks to your users:
```ts
async function sendWebhook(url: string, payload: any, env: Env): Promise<void> {
  // 1. Sign the payload
  const timestamp = Math.floor(Date.now() / 1000);
  const signedPayload = `${timestamp}.${JSON.stringify(payload)}`;
  const signature = crypto.createHmac('sha256', env.WEBHOOK_SECRET).update(signedPayload).digest('hex');

  // 2. Send
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Signature': signature,
      'X-Timestamp': String(timestamp),
    },
    body: JSON.stringify(payload),
  });

  // 3. Handle the response
  if (!response.ok) {
    throw new Error(`Webhook failed: ${response.status}`);
  }
}
```

The webhook is signed; the user can verify it.

## The "retry" pattern

For failed sends, retry with backoff:
```ts
async function sendWebhookWithRetry(url: string, payload: any, env: Env, maxAttempts = 5): Promise<void> {
  let lastError: Error | undefined;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      await sendWebhook(url, payload, env);
      return;
    } catch (err) {
      lastError = err as Error;
      if (attempt === maxAttempts - 1) break;

      // Don't retry on 4xx (except 429)
      if (err.message.includes('4') && !err.message.includes('429')) break;

      // Exponential backoff
      const delay = Math.min(60_000 * 2 ** attempt, 24 * 60 * 60 * 1000);
      await sleep(delay);
    }
  }

  // All retries failed
  await env.WEBHOOK_DLQ.send({ url, payload, error: String(lastError) });
}
```

Retries 5 times with exponential backoff; 4xx errors don't
retry.

## The "webhook subscription" pattern

For per-user webhook subscriptions:
```sql
CREATE TABLE webhook_subscriptions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  url TEXT NOT NULL,
  events TEXT NOT NULL,  -- JSON array
  secret TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

```ts
async function dispatchEvent(event: WebhookEvent, env: Env): Promise<void> {
  const subs = await env.DB!.prepare(
    `SELECT * FROM webhook_subscriptions WHERE user_id = ? AND active = 1`
  ).bind(event.userId).all<WebhookSubscription>();

  for (const sub of subs.results) {
    const events = JSON.parse(sub.events);
    if (!events.includes(event.type)) continue;

    // Send (async, retry)
    await env.WEBHOOK_QUEUE.send({ sub, event });
  }
}
```

Users subscribe to specific events.

## The "webhook signature" pattern

The user verifies the signature:
```ts
// On the receiver side
function verifyWebhookSignature(payload: string, header: string, secret: string): boolean {
  const [timestampPart, signaturePart] = header.split(',');
  const timestamp = parseInt(timestampPart.split('=')[1]);
  const signature = signaturePart.split('=')[1];

  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - timestamp) > 300) return false;

  const signedPayload = `${timestamp}.${payload}`;
  const expected = crypto.createHmac('sha256', secret).update(signedPayload).digest('hex');

  return crypto.timingSafeEqual(Buffer.from(signature, 'hex'), Buffer.from(expected, 'hex'));
}
```

The receiver verifies the HMAC.

## The "webhook documentation" pattern

Document the webhooks:
```markdown
## Webhooks

We send webhooks for these events:

### `user.created`
Triggered when a user is created.
```json
{
  "id": "u_123",
  "email": "alice@example.com",
  "displayName": "Alice",
  "createdAt": "2026-08-09T14:30:00.000Z"
}
```

### `user.deleted`
Triggered when a user is deleted.
```json
{
  "id": "u_123"
}
```

### Signature
All webhooks include `X-Signature` and `X-Timestamp` headers.
Verify with HMAC-SHA256.
```

The doc is the API for the webhook receiver.

## The "webhook log" pattern

For debugging, log every webhook:
```sql
CREATE TABLE webhook_log (
  id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload TEXT,
  response_status INTEGER,
  response_body TEXT,
  attempts INTEGER DEFAULT 0,
  sent_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

The log shows the history; debugging is easy.

## The "webhook security" pattern

For secure webhooks:
- **HTTPS only:** Reject HTTP webhooks
- **Signature verification:** HMAC-SHA256
- **Timestamp check:** Block replays
- **Secret rotation:** Rotate the secret periodically
- **IP allowlist:** Only accept from known IPs (optional)

## Verification
- **Test:** Webhook is received + processed
- **Test:** Replay attack is blocked
- **Test:** Retry on failure
- **Test:** Idempotency (same event twice = one effect)
- **Live:** Webhook delivery is monitored

## Gotchas
- **The "slow webhook handler" anti-pattern.** The vendor
  times out. Make the handler fast (queue the work).
- **The "no idempotency" anti-pattern.** The vendor retries;
  your handler runs twice. Use an idempotency key.
- **The "no signature verification" anti-pattern.** Anyone
  can send a webhook to your endpoint. Always verify.
- **The "webhook receiver down" anti-pattern.** Your
  service is down; the vendor's webhook fails. The vendor
  may give up. Have a high-availability endpoint.
- **The "webhook with PII" anti-pattern.** The payload
  may contain PII. Encrypt at rest; restrict access.
- **The "no replay protection" anti-pattern.** A captured
  webhook can be replayed. Use timestamp + signature.

## Related
- `idempotency-keys.md`
- `retry-with-exponential-backoff.md`
- `cloudflare/workers-workers-queues-patterns.md`
- `audit-log-as-product.md`
- `secure-defaults.md`
- Stripe: https://stripe.com/docs/webhooks
- GitHub: https://docs.github.com/en/webhooks
