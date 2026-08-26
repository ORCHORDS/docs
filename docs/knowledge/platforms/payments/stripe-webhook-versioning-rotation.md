# Stripe Webhook Endpoint Versioning and Rotation Strategy in Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You need to upgrade your Stripe API version (e.g. from `2023-10-16` to `2025-03-31.acacia`) without dropping live webhook events during the migration window. Additionally, your webhook signing secret was potentially exposed in a git commit and needs emergency rotation. Both scenarios require zero-downtime endpoint management.

This article covers: dual-endpoint blue/green versioning, secret rotation without downtime, API version pinning per endpoint, and Workers routing logic that handles both old and new event shapes simultaneously.

---

## Context

Stripe sends webhooks in the API version of the **endpoint**, not the version of the API call that triggered the event. Each webhook endpoint has its own pinned `api_version`. When you upgrade your Stripe API version, existing endpoints continue to receive events in the old format until you explicitly update the endpoint's API version.

This means you can:
1. Create a new endpoint at a new URL pinned to the new API version.
2. Register both endpoints in Stripe simultaneously during a migration window.
3. Route events to the appropriate handler based on the `Stripe-Signature` header (which signing secret matches).
4. Decommission the old endpoint once all event types are confirmed working on the new version.

Key Stripe objects:
- `WebhookEndpoint` — a registered URL with a pinned `api_version` and list of subscribed event types
- `secret` — the signing secret returned once at creation time (`whsec_...`)
- `Stripe-Signature` header — used for HMAC-SHA256 verification; version-specific

---

## Section 1 — Dual-Endpoint Blue/Green Registration

```typescript
// scripts/register-webhook-endpoints.ts  (run as a one-off migration script)
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2025-03-31.acacia',
});

const WORKER_BASE_URL = 'https://api.yourapp.com';

async function registerEndpoints() {
  // Blue endpoint — old API version (kept alive during migration)
  const blue = await stripe.webhookEndpoints.create({
    url: `${WORKER_BASE_URL}/webhooks/stripe/v1`,
    enabled_events: ['*'],
    api_version: '2023-10-16' as unknown as Stripe.WebhookEndpointCreateParams.ApiVersion,
  });
  console.log('Blue endpoint secret:', blue.secret);   // store in KV as STRIPE_WH_SECRET_V1

  // Green endpoint — new API version
  const green = await stripe.webhookEndpoints.create({
    url: `${WORKER_BASE_URL}/webhooks/stripe/v2`,
    enabled_events: ['*'],
    api_version: '2025-03-31.acacia' as unknown as Stripe.WebhookEndpointCreateParams.ApiVersion,
  });
  console.log('Green endpoint secret:', green.secret);  // store in KV as STRIPE_WH_SECRET_V2
}

registerEndpoints();
```

Store both secrets in Cloudflare Workers Secrets (not KV, not wrangler.toml):

```bash
echo "whsec_blue..." | wrangler secret put STRIPE_WH_SECRET_V1
echo "whsec_green..." | wrangler secret put STRIPE_WH_SECRET_V2
```

---

## Section 2 — Workers Router for Dual-Version Endpoints

```typescript
// workers/src/webhooks/stripe-router.ts
import Stripe from 'stripe';
import { handleEventV1 } from './stripe-v1';
import { handleEventV2 } from './stripe-v2';

interface StripeWebhookEnv {
  STRIPE_WH_SECRET_V1: string;
  STRIPE_WH_SECRET_V2: string;
}

export async function routeStripeWebhook(
  request: Request,
  env: StripeWebhookEnv & Env,
): Promise<Response> {
  const body = await request.text();
  const signature = request.headers.get('stripe-signature') ?? '';

  // Determine which endpoint was hit by the URL path
  const url = new URL(request.url);
  const isV2 = url.pathname.includes('/v2');
  const secret = isV2 ? env.STRIPE_WH_SECRET_V2 : env.STRIPE_WH_SECRET_V1;

  let event: Stripe.Event;
  try {
    event = Stripe.webhooks.constructEvent(body, signature, secret);
  } catch (err) {
    console.error('Webhook signature verification failed', err);
    return new Response('Invalid signature', { status: 400 });
  }

  // Dispatch to version-specific handler
  if (isV2) {
    await handleEventV2(env, event);
  } else {
    await handleEventV1(env, event);
  }

  return new Response('ok', { status: 200 });
}
```

Register routes in your Hono app:

```typescript
// workers/src/index.ts  (excerpt)
app.post('/webhooks/stripe/v1', (c) =>
  routeStripeWebhook(c.req.raw, c.env),
);
app.post('/webhooks/stripe/v2', (c) =>
  routeStripeWebhook(c.req.raw, c.env),
);
```

---

## Section 3 — Secret Rotation (Emergency or Scheduled)

When a webhook secret is compromised, Stripe does not let you rotate the secret of an existing endpoint. You must create a new endpoint and delete the old one. Zero-downtime procedure:

```typescript
// scripts/rotate-webhook-secret.ts
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2025-03-31.acacia',
});

async function rotateSecret(compromisedEndpointId: string) {
  // 1. List current endpoint config
  const oldEndpoint = await stripe.webhookEndpoints.retrieve(
    compromisedEndpointId,
  );

  // 2. Create a replacement endpoint at the SAME URL but new signing secret
  const replacement = await stripe.webhookEndpoints.create({
    url: oldEndpoint.url,
    enabled_events: oldEndpoint.enabled_events as Stripe.WebhookEndpointCreateParams.EnabledEvent[],
    api_version: oldEndpoint.api_version as unknown as Stripe.WebhookEndpointCreateParams.ApiVersion,
  });

  console.log('NEW secret (store immediately):', replacement.secret);
  // ^^^ This is the ONLY time you can read the secret

  // 3. Update Workers secret — do this BEFORE deleting the old endpoint
  // Run: echo "<new_secret>" | wrangler secret put STRIPE_WH_SECRET
  // Confirm deployment, then proceed:

  // 4. Delete the compromised endpoint (stops events to old URL signing)
  await stripe.webhookEndpoints.del(compromisedEndpointId);
  console.log('Old endpoint deleted:', compromisedEndpointId);
}
```

> WARNING: Between step 2 (create) and step 4 (delete), Stripe sends events to the same URL with TWO different secrets. Your Workers handler must attempt verification against both secrets for the rotation window.

---

## Section 4 — Dual-Secret Verification During Rotation Window

```typescript
// workers/src/webhooks/dual-secret-verify.ts
import Stripe from 'stripe';

/**
 * Attempts HMAC verification against multiple secrets.
 * Returns the first successfully verified event, or throws if all fail.
 * Use during webhook secret rotation windows only.
 */
export function constructEventMultiSecret(
  payload: string,
  signature: string,
  secrets: string[],
): Stripe.Event {
  for (const secret of secrets) {
    try {
      return Stripe.webhooks.constructEvent(payload, signature, secret);
    } catch {
      // Try next secret
    }
  }
  throw new Error('Webhook signature verification failed with all secrets');
}

// Usage in rotation mode (set env var ROTATION_MODE=true):
export async function handleStripeWebhook(
  request: Request,
  env: Env & { STRIPE_WH_SECRET: string; STRIPE_WH_SECRET_OLD?: string },
): Promise<Response> {
  const body = await request.text();
  const sig = request.headers.get('stripe-signature') ?? '';

  const secrets = [
    env.STRIPE_WH_SECRET,
    ...(env.STRIPE_WH_SECRET_OLD ? [env.STRIPE_WH_SECRET_OLD] : []),
  ];

  let event: Stripe.Event;
  try {
    event = constructEventMultiSecret(body, sig, secrets);
  } catch {
    return new Response('Invalid signature', { status: 400 });
  }

  await dispatchEvent(env, event);
  return new Response('ok', { status: 200 });
}
```

After confirming the old endpoint is deleted and no events with the old secret arrive for 10 minutes, remove `STRIPE_WH_SECRET_OLD` from Workers:

```bash
wrangler secret delete STRIPE_WH_SECRET_OLD
```

---

## Section 5 — API Version Canary Testing with Test-Mode Endpoint

```typescript
// scripts/register-test-endpoint.ts
// Register a test-mode endpoint pointed at a staging Worker to validate new API version
// before migrating production.

const testStripe = new Stripe(process.env.STRIPE_TEST_SECRET_KEY!, {
  apiVersion: '2025-03-31.acacia',
});

const testEndpoint = await testStripe.webhookEndpoints.create({
  url: 'https://staging.yourapp.com/webhooks/stripe',
  enabled_events: [
    'payment_intent.succeeded',
    'customer.subscription.updated',
    'invoice.payment_failed',
    // ... your full event list
  ],
  api_version: '2025-03-31.acacia' as unknown as Stripe.WebhookEndpointCreateParams.ApiVersion,
});

console.log('Staging test endpoint secret:', testEndpoint.secret);
```

Use `stripe trigger <event>` in test mode against the staging endpoint to confirm the new event shape is handled correctly before cutting over production.

---

## Anti-patterns

- **Updating `api_version` on an existing live endpoint in place**: Stripe changes the event shape immediately. Any in-flight events or events in the retry queue will arrive in the new format before your handler is updated. Always create a new endpoint, not update an existing one.
- **Reading the webhook secret from environment variables in plain text logs**: `console.log(env.STRIPE_WH_SECRET)` leaks the secret into Cloudflare Logs. Never log secrets.
- **Not deleting the old endpoint after rotation**: the compromised secret remains valid for as long as the endpoint exists in Stripe. Delete it immediately after confirming the replacement is working.
- **Hardcoding the API version in `wrangler.toml`**: the API version used for webhook delivery is set on the endpoint in Stripe, not in your SDK instantiation. Mismatching these causes confusing shape errors.
- **Using a wildcard `'*'` event subscription in production with no filtering**: your worker receives every event type, burning CPU for events you do not handle. Subscribe only to the events you consume.

---

## Gotchas

- Stripe's webhook secret is shown **only once** at endpoint creation. If you lose it, you must delete and recreate the endpoint.
- The Stripe CLI's `--forward-to` flag uses its own temporary signing secret (not your production endpoint's secret). Never use the CLI secret in your production handler.
- Stripe's event retry window is 3 days. During a rotation, failed deliveries to the old endpoint will keep retrying to the old URL (which may still be live) with the old secret. Both are safe to handle through the dual-secret path.
- Endpoint `api_version` can only be set to versions released at or after your Stripe account's default API version. Check your Stripe Dashboard → Developers → API versions for the valid range.
- Workers `wrangler secret put` triggers a new deployment. Test with `wrangler secret put --dry-run` to validate before deploying.
- The `Stripe-Signature` header includes a `t=` timestamp. Stripe rejects replayed events if `t` is more than 300 seconds old. Ensure your Workers clock is not skewed (it uses Cloudflare's infrastructure time, so this is normally fine).

---

## Verification

```bash
# 1. List all registered webhook endpoints
stripe webhook_endpoints list | jq '.data[] | {id, url, api_version, status}'

# 2. Send a test event to the new endpoint
stripe trigger payment_intent.succeeded \
  --webhook-endpoint we_xxx_green

# 3. Confirm event received and processed
wrangler tail --format pretty | grep 'payment_intent.succeeded'

# 4. Rotate secret — create replacement and immediately capture secret
# (see Section 3 script above)

# 5. Update Workers secret
echo "whsec_new..." | wrangler secret put STRIPE_WH_SECRET

# 6. Confirm old endpoint deleted
stripe webhook_endpoints retrieve we_xxx_old
# Expected: No such webhook endpoint: 'we_xxx_old'

# 7. Remove rotation fallback secret after clean 10-minute window
wrangler secret delete STRIPE_WH_SECRET_OLD
```

---

## Related

- `stripe-webhook-setup.md` — initial endpoint creation and event selection
- `stripe-webhook-signature-verification.md` — HMAC-SHA256 verification details
- `stripe-webhook-idempotency-workers.md` — idempotent event processing
- `stripe-webhook-retry-handling.md` — exponential back-off and retry queue
- `stripe-thin-events-fetch-and-idempotent-processing.md` — thin event hydration after upgrade

---

## Sources

- Stripe Docs — Webhook versioning: https://stripe.com/docs/webhooks/versioning
- Stripe Docs — API changelog: https://stripe.com/docs/upgrades
- Stripe Docs — Webhook endpoint management: https://stripe.com/docs/api/webhook_endpoints
- Stripe CLI triggers: https://stripe.com/docs/stripe-cli/triggers
- Cloudflare Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
