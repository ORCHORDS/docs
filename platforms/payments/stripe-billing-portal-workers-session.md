# Stripe Billing Portal Integration with Workers Session Management

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You use Stripe's hosted Customer Portal (`stripe.billingPortal.sessions.create`) so customers can manage their subscriptions, update payment methods, and download invoices — but you hit these problems:

1. **The portal URL contains a Stripe session ID that expires in 5 minutes** and must be generated fresh per request. Reusing stale URLs causes "This link has expired" errors.
2. **Authentication state must be validated server-side** before generating the portal URL — you cannot expose portal generation to unauthenticated requests.
3. **Return URL handling** must gracefully reload the customer's subscription state in your app after portal actions (plan change, cancellation, payment method update).
4. **On Cloudflare Workers**, there is no session middleware (no Express, no Next.js cookies) — you need to implement JWT or signed-cookie session validation yourself.

---

## Context

Stripe Customer Portal is a hosted UI that eliminates the need to build subscription management UI. The integration has three steps:

1. Customer clicks "Manage Subscription" in your app
2. Your server creates a `billingPortal.sessions` object and redirects to its `url`
3. After the customer acts in the portal, Stripe redirects to your `return_url`
4. Your app handles the return and syncs state from Stripe webhooks

On Cloudflare Workers + Pages, "session management" means validating a signed JWT (stored in an `HttpOnly` cookie set at login) before calling Stripe. There is no server-side session store needed — the JWT carries the `customerId` claim.

---

## Auth Architecture

```
Login endpoint (Workers)
  → issues signed JWT containing { sub: userId, stripeCustomerId }
  → sets HttpOnly cookie: session=<JWT>; SameSite=Lax; Secure; Path=/

"Manage Subscription" button
  → POST /api/billing/portal (sends cookie)

Workers: portal endpoint
  → extract and verify JWT from cookie
  → stripe.billingPortal.sessions.create({ customer: stripeCustomerId })
  → return { url: portalSession.url }

Browser redirects to Stripe portal
  → customer manages subscription
  → Stripe redirects to return_url

return_url endpoint
  → invalidate portal cache if any
  → webhook has already updated D1 subscription state
  → render updated UI
```

---

## JWT Session Library (Zero-dependency, Web Crypto)

```typescript
// lib/auth/jwt.ts
// Uses Web Crypto API — available in all Cloudflare Workers runtimes.

const ALGORITHM = { name: 'HMAC', hash: 'SHA-256' };
const EXPIRY_SECONDS = 7 * 24 * 3600; // 7 days

export interface SessionClaims {
  sub: string;            // internal user ID
  stripeCustomerId: string;
  email: string;
  iat: number;
  exp: number;
}

async function importKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    ALGORITHM,
    false,
    ['sign', 'verify']
  );
}

function base64url(data: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(data)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

function decodeBase64url(str: string): Uint8Array {
  const padded = str.replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(padded.padEnd(padded.length + ((4 - padded.length % 4) % 4), '='));
  return new Uint8Array([...raw].map(c => c.charCodeAt(0)));
}

export async function signJwt(
  claims: Omit<SessionClaims, 'iat' | 'exp'>,
  secret: string
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const payload: SessionClaims = { ...claims, iat: now, exp: now + EXPIRY_SECONDS };

  const header = base64url(new TextEncoder().encode(JSON.stringify({ alg: 'HS256', typ: 'JWT' })));
  const body   = base64url(new TextEncoder().encode(JSON.stringify(payload)));
  const signingInput = `${header}.${body}`;

  const key = await importKey(secret);
  const sig = await crypto.subtle.sign(ALGORITHM, key, new TextEncoder().encode(signingInput));

  return `${signingInput}.${base64url(sig)}`;
}

export async function verifyJwt(
  token: string,
  secret: string
): Promise<SessionClaims | null> {
  const parts = token.split('.');
  if (parts.length !== 3) return null;

  const [header, body, sig] = parts;
  const signingInput = `${header}.${body}`;

  const key = await importKey(secret);
  const valid = await crypto.subtle.verify(
    ALGORITHM,
    key,
    decodeBase64url(sig),
    new TextEncoder().encode(signingInput)
  );
  if (!valid) return null;

  let claims: SessionClaims;
  try {
    claims = JSON.parse(new TextDecoder().decode(decodeBase64url(body)));
  } catch {
    return null;
  }

  if (claims.exp < Math.floor(Date.now() / 1000)) return null; // expired
  return claims;
}

export function parseCookies(cookieHeader: string | null): Record<string, string> {
  if (!cookieHeader) return {};
  return Object.fromEntries(
    cookieHeader.split(';').map(c => {
      const [k, ...v] = c.trim().split('=');
      return [k.trim(), decodeURIComponent(v.join('='))];
    })
  );
}
```

---

## Portal Session Worker

```typescript
// workers/billing-portal.ts
import Stripe from 'stripe';
import { verifyJwt, parseCookies } from '../lib/auth/jwt';

export interface Env {
  STRIPE_SECRET_KEY: string;
  JWT_SECRET: string;
  APP_URL: string;                // e.g. https://app.yourapp.com
  PORTAL_CONFIG_ID?: string;      // Optional: Stripe portal configuration ID
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': env.APP_URL,
          'Access-Control-Allow-Methods': 'POST',
          'Access-Control-Allow-Headers': 'Content-Type',
          'Access-Control-Allow-Credentials': 'true',
        },
      });
    }

    if (request.method !== 'POST') return new Response('', { status: 405 });

    // 1. Extract and verify session JWT from cookie
    const cookies = parseCookies(request.headers.get('cookie'));
    const token = cookies['session'];
    if (!token) {
      return new Response(JSON.stringify({ error: 'unauthenticated' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const claims = await verifyJwt(token, env.JWT_SECRET);
    if (!claims) {
      return new Response(JSON.stringify({ error: 'invalid_session' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // 2. Parse optional request body for return path override
    let returnPath = '/account/billing';
    try {
      const body = await request.json() as { returnPath?: string };
      if (body.returnPath && body.returnPath.startsWith('/')) {
        returnPath = body.returnPath;
      }
    } catch { /* ignore */ }

    // 3. Create Stripe billing portal session
    const stripe = new Stripe(env.STRIPE_SECRET_KEY);

    let portalSession: Stripe.BillingPortal.Session;
    try {
      portalSession = await stripe.billingPortal.sessions.create({
        customer: claims.stripeCustomerId,
        return_url: `${env.APP_URL}${returnPath}?portal_return=1`,
        ...(env.PORTAL_CONFIG_ID && { configuration: env.PORTAL_CONFIG_ID }),
      });
    } catch (err: unknown) {
      const stripeErr = err as Stripe.StripeError;
      if (stripeErr.code === 'resource_missing') {
        return new Response(JSON.stringify({
          error: 'no_subscription',
          message: 'No Stripe customer record found for this account.',
        }), { status: 404, headers: { 'Content-Type': 'application/json' } });
      }
      throw err;
    }

    // 4. Return portal URL (client-side redirect preserves SPA state)
    return new Response(JSON.stringify({ url: portalSession.url }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store',       // Never cache — portal URL is single-use
        'Access-Control-Allow-Origin': env.APP_URL,
        'Access-Control-Allow-Credentials': 'true',
      },
    });
  },
};
```

---

## Client-Side Integration

```typescript
// src/lib/billing.ts
export async function openBillingPortal(returnPath = '/account/billing'): Promise<void> {
  const response = await fetch('/api/billing/portal', {
    method: 'POST',
    credentials: 'include',   // sends HttpOnly session cookie
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ returnPath }),
  });

  if (response.status === 401) {
    // Session expired — redirect to login
    window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
    return;
  }

  if (!response.ok) {
    const error = await response.json() as { error: string; message?: string };
    throw new Error(error.message ?? error.error);
  }

  const { url } = await response.json() as { url: string };
  // Full navigation — Stripe portal runs in its own tab context
  window.location.href = url;
}
```

```html
<!-- SvelteKit component example -->
<script lang="ts">
  import { openBillingPortal } from '$lib/billing';
  let loading = false;
  let error = '';

  async function handleManageBilling() {
    loading = true;
    error = '';
    try {
      await openBillingPortal('/account/billing');
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to open billing portal';
      loading = false;
    }
  }
</script>

<button on:click={handleManageBilling} disabled={loading}>
  {loading ? 'Opening...' : 'Manage Billing'}
</button>
{#if error}<p class="error">{error}</p>{/if}
```

---

## Return URL Handler

```typescript
// workers/portal-return.ts
// Handles GET /account/billing?portal_return=1
// Syncs subscription state from Stripe (belt-and-suspenders alongside webhooks)

import Stripe from 'stripe';
import { verifyJwt, parseCookies } from '../lib/auth/jwt';

export interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
  JWT_SECRET: string;
}

export async function handlePortalReturn(request: Request, env: Env): Promise<Response | null> {
  const url = new URL(request.url);
  if (!url.searchParams.has('portal_return')) return null;

  const cookies = parseCookies(request.headers.get('cookie'));
  const claims = await verifyJwt(cookies['session'] ?? '', env.JWT_SECRET);
  if (!claims) return null; // will be handled by auth middleware

  // Sync current subscription state from Stripe
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);
  const subscriptions = await stripe.subscriptions.list({
    customer: claims.stripeCustomerId,
    status: 'all',
    limit: 5,
  });

  if (subscriptions.data.length > 0) {
    const sub = subscriptions.data[0];
    await env.DB.prepare(
      `UPDATE subscriptions
       SET status = ?, current_period_end = ?, cancel_at_period_end = ?,
           updated_at = datetime('now')
       WHERE stripe_customer_id = ?`
    ).bind(
      sub.status,
      new Date(sub.current_period_end * 1000).toISOString(),
      sub.cancel_at_period_end ? 1 : 0,
      claims.stripeCustomerId
    ).run();
  }

  // Strip ?portal_return from URL and redirect to clean path
  url.searchParams.delete('portal_return');
  return Response.redirect(url.toString(), 302);
}
```

---

## Stripe Portal Configuration (Wrangler D1 Seed)

```typescript
// scripts/create-portal-config.ts
// Run once to create a portal configuration for your brand

import Stripe from 'stripe';
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

const config = await stripe.billingPortal.configurations.create({
  business_profile: {
    headline: 'Manage your subscription',
    privacy_policy_url: 'https://yourapp.com/privacy',
    terms_of_service_url: 'https://yourapp.com/terms',
  },
  features: {
    customer_update: {
      enabled: true,
      allowed_updates: ['email', 'address'],
    },
    invoice_history: { enabled: true },
    payment_method_update: { enabled: true },
    subscription_cancel: {
      enabled: true,
      mode: 'at_period_end',
      proration_behavior: 'none',
    },
    subscription_update: {
      enabled: true,
      default_allowed_updates: ['price', 'quantity', 'promotion_code'],
      proration_behavior: 'create_prorations',
      products: [
        {
          product: 'prod_YOUR_PRODUCT_ID',
          prices: ['price_monthly', 'price_annual'],
        },
      ],
    },
  },
});

console.log('Portal configuration ID:', config.id);
// Add to wrangler.toml as PORTAL_CONFIG_ID = "bpc_..."
```

---

## Webhook Handler for Portal Events

```typescript
// workers/stripe-webhooks.ts (relevant section)
// Portal actions fire these events — your webhook handler must process them
// to keep D1 in sync regardless of portal_return handler

const PORTAL_EVENTS = [
  'customer.subscription.updated',
  'customer.subscription.deleted',
  'customer.updated',
  'payment_method.attached',
  'payment_method.detached',
] as const;

async function handlePortalWebhook(
  event: Stripe.Event,
  env: { DB: D1Database }
): Promise<void> {
  switch (event.type) {
    case 'customer.subscription.updated': {
      const sub = event.data.object as Stripe.Subscription;
      await env.DB.prepare(
        `UPDATE subscriptions
         SET status = ?, cancel_at_period_end = ?,
             current_period_end = ?, updated_at = datetime('now')
         WHERE stripe_subscription_id = ?`
      ).bind(
        sub.status,
        sub.cancel_at_period_end ? 1 : 0,
        new Date(sub.current_period_end * 1000).toISOString(),
        sub.id
      ).run();
      break;
    }
    case 'customer.subscription.deleted': {
      const sub = event.data.object as Stripe.Subscription;
      await env.DB.prepare(
        `UPDATE subscriptions SET status = 'canceled', updated_at = datetime('now')
         WHERE stripe_subscription_id = ?`
      ).bind(sub.id).run();
      break;
    }
  }
}
```

---

## Anti-patterns

- **Generating the portal URL at page load and embedding in a link**: Portal URLs expire in 5 minutes. Always generate on demand (when the user clicks the button), never on page render.

- **Caching the portal URL in KV or the browser**: A `billingPortal.sessions` URL is single-use. After the customer visits the portal once, the URL is invalid. Never cache it.

- **Passing `stripeCustomerId` in the request body from the client**: A malicious user could substitute another customer's ID. Always derive `stripeCustomerId` from the verified server-side session (JWT), never from client-supplied data.

- **Using `window.open` for the portal URL**: Stripe's portal does not function correctly in a popup because it sets `SameSite=Lax` cookies. Always do a full-page navigation (`window.location.href = url`).

- **Not setting `Cache-Control: no-store` on the portal URL response**: A shared CDN or browser cache serving a stale portal URL to another user would expose a session link.

- **Relying solely on the `return_url` handler to sync state**: The user can close the tab before the return redirect. Stripe webhook processing is the authoritative sync path — `portal_return` is a convenience to refresh state immediately.

---

## Gotchas

1. **`stripe.billingPortal.sessions.create` requires the customer to have a Stripe Customer object**. If the user signed up without a payment method, they may not have a Stripe customer yet. Create the customer lazily on first billing action.

2. **Portal `return_url` must be an HTTPS URL** in production (not `localhost`). For local dev, use `http://localhost:5173` — Stripe allows it in test mode only.

3. **The portal URL path is `https://billing.stripe.com/p/session/...`** — it is not on your domain. You cannot inject your own CSP headers or analytics into the portal.

4. **If the customer cancels their subscription in the portal and you use `cancel_at_period_end: true`**, the `customer.subscription.updated` event fires immediately with `cancel_at_period_end: true` and status `active`. The `customer.subscription.deleted` event fires at the period end.

5. **Stripe portal sessions are tied to the customer, not a subscription**. A customer with multiple subscriptions sees all of them in the portal.

6. **Workers do not have `document.cookie`**. Cookie parsing must be done from the `Cookie` request header using a helper like `parseCookies()` above.

7. **JWT `exp` should be checked in UTC seconds**, not milliseconds. `Date.now() / 1000` vs `Date.now()` bugs are the most common JWT auth bug in Workers code.

---

## Verification

```bash
# 1. Create portal configuration
STRIPE_SECRET_KEY=sk_test_... npx ts-node scripts/create-portal-config.ts

# 2. Deploy workers
wrangler deploy

# 3. Test portal session creation (with valid JWT cookie)
curl -X POST https://YOUR_WORKER.workers.dev/api/billing/portal \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_TEST_JWT" \
  -d '{}'
# Expect: {"url": "https://billing.stripe.com/p/session/..."}

# 4. Verify URL expires
# Copy the URL, wait 6 minutes, open in browser
# Expect: "This link has expired" Stripe page

# 5. Test with Stripe test mode customer
# Create customer in Stripe test dashboard, subscribe them to a plan
# Then create JWT with { stripeCustomerId: 'cus_test...' } and test portal access

# 6. Verify webhook sync
stripe trigger customer.subscription.updated --api-key sk_test_...
wrangler d1 execute payments \
  --command "SELECT status, cancel_at_period_end, updated_at FROM subscriptions LIMIT 5"
```

---

## Related

- `stripe-customer-portal.md` — Portal configuration and feature reference
- `stripe-cancellation-flow.md` — Cancellation handling and retention flows
- `stripe-subscription-lifecycle.md` — Subscription state machine
- `stripe-payment-elements.md` — Payment method update outside of portal
- `stripe-webhook-idempotency-workers.md` — Idempotency for webhook processing
- `subscription-dunning-retry-recovery.md` — Recovery after payment failure via portal

---

## Sources

- [Stripe — Customer Portal](https://docs.stripe.com/customer-management)
- [Stripe — billingPortal.sessions.create](https://docs.stripe.com/api/customer_portal/sessions/create)
- [Stripe — billingPortal.configurations.create](https://docs.stripe.com/api/customer_portal/configurations/create)
- [Web Crypto API — SubtleCrypto.sign](https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign)
- [Cloudflare Workers — Cookies](https://developers.cloudflare.com/workers/examples/set-cookie/)
- [RFC 7519 — JSON Web Token (JWT)](https://datatracker.ietf.org/doc/html/rfc7519)
