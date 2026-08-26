# feature-cookbook-webhook

**Issue:** Common webhook patterns — Stripe, GitHub, custom
**Date:** 2026-08-09
**Status:** documented

## Symptom
You integrate with a vendor (Stripe, GitHub, etc.). They
send webhooks. You don't know how to verify them. You
don't know how to handle retries. You don't know how to
test.

## Root cause
**Webhooks have a standard pattern.** Each vendor has
slight differences, but the core is the same.

**Source:** Various vendor webhook docs.

## The "Stripe webhook" pattern

```ts
import Stripe from 'stripe';

const stripe = new Stripe(env.STRIPE_SECRET_KEY);

export async function handleStripeWebhook(request: Request, env: Env): Promise<Response> {
  const signature = request.headers.get('Stripe-Signature');
  if (!signature) return new Response('Missing signature', { status: 400 });

  const body = await request.text();

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, signature, env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return new Response(`Invalid signature: ${(err as Error).message}`, { status: 400 });
  }

  // Process async (don't block the webhook)
  await env.STRIPE_QUEUE.send(event);

  return new Response('OK', { status: 200 });
}

// Queue handler
export async function processStripeEvent(event: Stripe.Event, env: Env): Promise<void> {
  // Idempotency
  const processed = await env.KV.get(`stripe:event:${event.id}`);
  if (processed) return;

  switch (event.type) {
    case 'payment_intent.succeeded':
      await handlePaymentSucceeded(event.data.object, env);
      break;
    case 'customer.subscription.created':
    case 'customer.subscription.updated':
      await handleSubscriptionChange(event.data.object, env);
      break;
    case 'customer.subscription.deleted':
      await handleSubscriptionCancelled(event.data.object, env);
      break;
    case 'invoice.payment_failed':
      await handlePaymentFailed(event.data.object, env);
      break;
  }

  await env.KV.put(`stripe:event:${event.id}`, '1', { expirationTtl: 86400 * 7 });
}
```

## The "GitHub webhook" pattern

```ts
import { createHmac, timingSafeEqual } from 'crypto';

export async function handleGitHubWebhook(request: Request, env: Env): Promise<Response> {
  const signature = request.headers.get('X-Hub-Signature-256');
  if (!signature) return new Response('Missing signature', { status: 400 });

  const body = await request.text();

  // Verify HMAC
  const expected = 'sha256=' + createHmac('sha256', env.GITHUB_WEBHOOK_SECRET).update(body).digest('hex');

  if (!timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) {
    return new Response('Invalid signature', { status: 400 });
  }

  const event = request.headers.get('X-GitHub-Event');
  const payload = JSON.parse(body);

  // Process
  switch (event) {
    case 'push':
      await handlePush(payload, env);
      break;
    case 'pull_request':
      await handlePullRequest(payload, env);
      break;
    // ... etc
  }

  return new Response('OK', { status: 200 });
}
```

## The "Slack webhook" pattern

For sending webhooks to Slack:
```ts
async function sendSlackNotification(channel: string, message: string, env: Env): Promise<void> {
  await fetch(env.SLACK_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      channel,
      text: message,
    }),
  });
}
```

Slack incoming webhooks are URL-based; no signature needed
(the URL is the secret).

## The "Discord webhook" pattern

```ts
async function sendDiscordNotification(webhookUrl: string, message: string): Promise<void> {
  await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content: message,
    }),
  });
}
```

Same pattern as Slack.

## The "webhook signing" pattern

For custom webhooks, sign with HMAC:
```ts
function signPayload(payload: string, secret: string, timestamp: number): string {
  const signedPayload = `${timestamp}.${payload}`;
  return 't=' + timestamp + ',v1=' + createHmac('sha256', secret).update(signedPayload).digest('hex');
}

// On the receiver
function verifySignature(payload: string, header: string, secret: string, toleranceSec = 300): boolean {
  const parts = Object.fromEntries(
    header.split(',').map(p => p.split('='))
  );

  const timestamp = parseInt(parts.t);
  const signature = parts.v1;

  // Check tolerance
  if (Math.abs(Date.now() / 1000 - timestamp) > toleranceSec) return false;

  // Compute expected
  const expected = createHmac('sha256', secret).update(`${timestamp}.${payload}`).digest('hex');

  return timingSafeEqual(Buffer.from(signature, 'hex'), Buffer.from(expected, 'hex'));
}
```

This is the Stripe-style signature.

## The "webhook test" pattern

Use the vendor's test tools:
- **Stripe CLI:** `stripe trigger payment_intent.succeeded`
- **GitHub:** Use the webhook test in repo settings
- **Custom:** Send a signed payload from your test code

```ts
test('webhook handles payment_intent.succeeded', async () => {
  const event = createMockStripeEvent('payment_intent.succeeded');
  const request = createSignedRequest(event, env.STRIPE_WEBHOOK_SECRET);

  const response = await handleStripeWebhook(request, env);
  expect(response.status).toBe(200);

  // Verify the side effect
  const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(event.data.object.metadata.userId).first();
  expect(user.plan).toBe('pro');
});
```

## The "webhook replay" pattern

For testing retries, replay an event:
```ts
// Stripe CLI: stripe events resend evt_123
// Or via the dashboard
```

## The "webhook delivery log" pattern

For debugging, log every delivery:
```ts
async function logWebhookDelivery(delivery: WebhookDelivery, env: Env): Promise<void> {
  await env.DB!.prepare(
    `INSERT INTO webhook_log (id, url, event_type, status, attempts, sent_at) VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(
    crypto.randomUUID(),
    delivery.url,
    delivery.eventType,
    delivery.status,
    delivery.attempts,
    new Date().toISOString(),
  ).run();
}
```

The log is the audit trail.

## The "webhook retry" pattern

For vendor retries, handle them:
- **Stripe:** Up to 3 days, exponential backoff
- **GitHub:** Up to 8 attempts, 30s between
- **Custom:** Configure per your needs

Always use idempotency keys.

## The "webhook dead letter" pattern

For permanently failed webhooks, send to a DLQ:
```ts
async function processWebhookWithDLQ(event: any, env: Env, maxAttempts = 5): Promise<void> {
  const attempts = parseInt(await env.KV.get(`webhook:attempts:${event.id}`) ?? '0');

  try {
    await processEvent(event, env);
    await env.KV.delete(`webhook:attempts:${event.id}`);
  } catch (err) {
    if (attempts >= maxAttempts - 1) {
      await env.WEBHOOK_DLQ.send({ event, error: String(err) });
    } else {
      await env.KV.put(`webhook:attempts:${event.id}`, String(attempts + 1));
      // Re-throw to trigger retry
      throw err;
    }
  }
}
```

The DLQ captures the failures.

## Verification
- **Test:** Webhook is received + processed
- **Test:** Replay is blocked
- **Test:** Retry on failure
- **Live:** Webhook delivery is monitored

## Gotchas
- **The "vendor's webhook is slow" anti-pattern.** A vendor
  that times out. Use a fast handler + async processing.
- **The "no signature verification" anti-pattern.** Anyone
  can send. Always verify.
- **The "vendor's webhook changes" anti-pattern.** Vendors
  add new event types; your handler must handle unknown
  events gracefully.
- **The "webhook with sensitive data" anti-pattern.** The
  payload may have PII; encrypt at rest.
- **The "webhook receiver is down" anti-pattern.** The
  vendor retries; make sure your endpoint is reliable.

## Related
- `webhook-implementation.md`
- `idempotency-keys.md`
- `retry-with-exponential-backoff.md`
- `cloudflare/workers-workers-queues-patterns.md`
- `secure-defaults.md`
- Stripe: https://stripe.com/docs/webhooks
- GitHub: https://docs.github.com/en/webhooks
