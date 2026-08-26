# Stripe Billing Portal Integration with Cloudflare Workers Session Management

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Users click "Manage Subscription" and land on a broken page, get a CSRF error, or are redirected to the wrong domain after completing a portal action. The root problem is almost always missing session state: the Stripe Billing Portal requires a server-issued session URL with an embedded `return_url`, and without Workers-side validation that URL is trivially forgeable, leakable via Referer headers, or left open to open-redirect abuse.

---

## Context

Stripe's Customer Portal is a hosted page that lets subscribers manage their plan, invoices, payment methods, and cancellations without you building any of that UI. Access is gated by a short-lived `portal.session` object whose `url` is valid for 5 minutes. The lifecycle is:

1. Worker authenticates the logged-in user, resolves their Stripe `customer_id`.
2. Worker calls `stripe.billingPortal.sessions.create(...)` with a `return_url`.
3. Worker issues a signed redirect to the session URL (never exposes it in HTML).
4. Stripe redirects the user back to `return_url` when done.

The two engineering problems are: (a) ensuring only authenticated users can generate portal sessions; (b) validating that `return_url` cannot be manipulated into an open redirect.

---

## 1. Resolving the Stripe Customer from Your Session Store

Workers can use a KV namespace or a D1 table as the session store. The pattern below uses a signed JWT stored in an HttpOnly cookie.

```typescript
// src/auth.ts
import { SignJWT, jwtVerify } from "jose";

const SESSION_COOKIE = "__sess";

export interface SessionPayload {
  userId: string;
  stripeCustomerId: string;
  exp: number;
}

export async function getSession(
  request: Request,
  jwtSecret: string
): Promise<SessionPayload | null> {
  const cookie = request.headers.get("Cookie") ?? "";
  const raw = cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${SESSION_COOKIE}=`))
    ?.slice(SESSION_COOKIE.length + 1);

  if (!raw) return null;

  try {
    const secret = new TextEncoder().encode(jwtSecret);
    const { payload } = await jwtVerify(raw, secret);
    return payload as unknown as SessionPayload;
  } catch {
    return null;
  }
}
```

Never store `stripeCustomerId` only in the cookie. Verify it exists in your D1 users table on each portal-session creation to prevent token stuffing attacks.

---

## 2. Return URL Allowlist Validation

The `return_url` must be one of your own origins. Hardcode an allowlist and reject anything else before passing it to Stripe.

```typescript
// src/portal.ts
const ALLOWED_RETURN_ORIGINS = new Set([
  "https://app.example.com",
  "https://www.example.com",
]);

export function validateReturnUrl(raw: string | null): URL {
  const fallback = "https://app.example.com/account";
  const candidate = raw ? decodeURIComponent(raw) : fallback;

  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    return new URL(fallback);
  }

  // Strip any fragment or extra auth before checking origin
  if (!ALLOWED_RETURN_ORIGINS.has(parsed.origin)) {
    return new URL(fallback);
  }

  // Enforce HTTPS
  if (parsed.protocol !== "https:") {
    parsed.protocol = "https:";
  }

  return parsed;
}
```

Passing `return_url` directly from a query parameter without this check creates an open redirect: `?return_url=https://evil.com`.

---

## 3. Worker Route: Creating the Portal Session

```typescript
// src/worker.ts
import Stripe from "stripe";
import { getSession } from "./auth";
import { validateReturnUrl } from "./portal";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/billing/portal" && request.method === "POST") {
      // 1. Authenticate
      const session = await getSession(request, env.JWT_SECRET);
      if (!session) {
        return new Response(null, {
          status: 302,
          headers: { Location: "/login?next=/billing/portal" },
        });
      }

      // 2. Verify customer exists in your DB (prevents stale JWT abuse)
      const row = await env.DB.prepare(
        "SELECT stripe_customer_id FROM users WHERE id = ? LIMIT 1"
      )
        .bind(session.userId)
        .first<{ stripe_customer_id: string }>();

      if (!row || row.stripe_customer_id !== session.stripeCustomerId) {
        return new Response("Unauthorized", { status: 403 });
      }

      // 3. Validate return URL from form body
      const body = await request.formData().catch(() => null);
      const rawReturn = body?.get("return_url") as string | null;
      const returnUrl = validateReturnUrl(rawReturn);

      // 4. Create portal session
      const stripe = new Stripe(env.STRIPE_SECRET_KEY);
      const portalSession = await stripe.billingPortal.sessions.create({
        customer: session.stripeCustomerId,
        return_url: returnUrl.toString(),
      });

      // 5. Redirect — never expose the portal URL in HTML (Referer leak)
      return new Response(null, {
        status: 303,
        headers: {
          Location: portalSession.url,
          "Cache-Control": "no-store",
          "Referrer-Policy": "no-referrer",
        },
      });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

Using `303 See Other` instead of `302` ensures the browser switches to GET for the redirect, eliminating method-confusion issues with some clients.

---

## 4. Configuring Portal Features via the API

Avoid hardcoding portal behavior in the Stripe dashboard. Drive it from your Worker at deploy time using the `billingPortal.configurations` API.

```typescript
// scripts/configure-portal.ts
import Stripe from "stripe";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

async function upsertPortalConfig(): Promise<void> {
  const configs = await stripe.billingPortal.configurations.list({ limit: 1 });
  const existing = configs.data[0];

  const params: Stripe.BillingPortal.ConfigurationUpdateParams = {
    business_profile: {
      headline: "Manage your example.com subscription",
      privacy_policy_url: "https://example.com/privacy",
      terms_of_service_url: "https://example.com/terms",
    },
    features: {
      customer_update: {
        enabled: true,
        allowed_updates: ["email", "address", "tax_id"],
      },
      invoice_history: { enabled: true },
      payment_method_update: { enabled: true },
      subscription_cancel: {
        enabled: true,
        mode: "at_period_end",
        proration_behavior: "none",
        cancellation_reason: {
          enabled: true,
          options: ["too_expensive", "missing_features", "switched_service", "other"],
        },
      },
      subscription_pause: { enabled: false },
      subscription_update: {
        enabled: true,
        default_allowed_updates: ["price", "quantity"],
        proration_behavior: "always_invoice",
        products: [
          {
            product: process.env.STRIPE_PRODUCT_ID!,
            prices: [
              process.env.STRIPE_PRICE_MONTHLY!,
              process.env.STRIPE_PRICE_ANNUAL!,
            ],
          },
        ],
      },
    },
    default_return_url: "https://app.example.com/account",
  };

  if (existing) {
    await stripe.billingPortal.configurations.update(existing.id, params);
    console.log(`Updated portal config ${existing.id}`);
  } else {
    const created = await stripe.billingPortal.configurations.create(params as any);
    console.log(`Created portal config ${created.id}`);
  }
}

upsertPortalConfig().catch(console.error);
```

Run this script in your CI pipeline after infrastructure provisioning so portal configuration is versioned in code, not set-and-forgotten in the dashboard.

---

## 5. Handling Post-Portal Webhook Events

The portal triggers several webhook events. Wire a D1 update for each.

```typescript
// src/webhooks/portal-events.ts
import Stripe from "stripe";
import type { D1Database } from "@cloudflare/workers-types";

export async function handlePortalEvent(
  event: Stripe.Event,
  db: D1Database
): Promise<void> {
  switch (event.type) {
    case "customer.subscription.updated": {
      const sub = event.data.object as Stripe.Subscription;
      await db
        .prepare(
          `UPDATE subscriptions
           SET status = ?, plan_price_id = ?, cancel_at_period_end = ?,
               current_period_end = ?, updated_at = ?
           WHERE stripe_subscription_id = ?`
        )
        .bind(
          sub.status,
          sub.items.data[0]?.price.id ?? null,
          sub.cancel_at_period_end ? 1 : 0,
          new Date(sub.current_period_end * 1000).toISOString(),
          new Date().toISOString(),
          sub.id
        )
        .run();
      break;
    }
    case "customer.subscription.deleted": {
      const sub = event.data.object as Stripe.Subscription;
      await db
        .prepare(
          `UPDATE subscriptions
           SET status = 'canceled', canceled_at = ?, updated_at = ?
           WHERE stripe_subscription_id = ?`
        )
        .bind(
          new Date((sub.canceled_at ?? Date.now() / 1000) * 1000).toISOString(),
          new Date().toISOString(),
          sub.id
        )
        .run();
      break;
    }
    case "billing_portal.session.created": {
      // Audit log — useful for security review
      const ps = event.data.object as Stripe.BillingPortal.Session;
      await db
        .prepare(
          `INSERT OR IGNORE INTO portal_audit_log
           (id, customer_id, return_url, created_at)
           VALUES (?, ?, ?, ?)`
        )
        .bind(
          ps.id,
          ps.customer,
          ps.return_url,
          new Date(ps.created * 1000).toISOString()
        )
        .run();
      break;
    }
  }
}
```

---

## Anti-patterns

- **Embedding the portal URL in HTML or JSON responses.** The URL is valid for 5 minutes but can be crawled by bots, logged by CDNs, or leaked in Referer headers. Always redirect server-side.
- **Accepting `return_url` from query parameters without validation.** A URL like `?return_url=https://phishing.example.com` is an open redirect waiting to happen.
- **Creating a portal session per page load.** Each call counts against Stripe API rate limits and adds latency. Gate creation behind a POST (form or fetch) triggered explicitly by user action.
- **Relying solely on JWT claims for `stripeCustomerId`.** Always cross-reference the database to catch accounts deleted or suspended after the JWT was issued.
- **Disabling all portal features in configuration.** If users cannot update their payment method through the portal, they cannot self-resolve declines — leading to involuntary churn you have to handle manually.

---

## Gotchas

- **Portal sessions expire after 5 minutes.** If your Worker caches the URL (e.g., in a response), it will be stale by the time the user clicks it. Never cache portal session URLs.
- **`return_url` must match a configured domain in your Stripe account** if you have URL restrictions enabled. Ensure your Workers domain is added in Stripe Dashboard > Settings > Billing > Customer Portal.
- **The `billing_portal.session.created` event has no `livemode` guard in test mode.** Set up separate webhook endpoints for test and production environments.
- **`subscription_pause` and `subscription_cancel` are mutually exclusive flows in UX terms.** Enable only one or clearly document to users what each does.
- **Portal does not support coupon application by customers.** Discounts must be applied server-side via `stripe.subscriptions.update`.

---

## Verification

```bash
# 1. Trigger a portal session in Stripe test mode
curl -X POST https://your-worker.example.com/billing/portal \
  -H "Cookie: __sess=<test_jwt>" \
  -d "return_url=https%3A%2F%2Fapp.example.com%2Faccount"
# Expect: 303 redirect to https://billing.stripe.com/p/session/...

# 2. Test open-redirect rejection
curl -X POST https://your-worker.example.com/billing/portal \
  -H "Cookie: __sess=<test_jwt>" \
  -d "return_url=https%3A%2F%2Fevil.com"
# Expect: 303 redirect to portal with return_url = https://app.example.com/account (fallback)

# 3. Test unauthenticated access
curl -X POST https://your-worker.example.com/billing/portal
# Expect: 302 to /login?next=/billing/portal

# 4. Check Stripe portal event in webhook log
# Dashboard > Developers > Webhooks > [endpoint] > Recent deliveries
# Filter for billing_portal.session.created
```

---

## Related

- `stripe-customer-portal.md` — portal feature overview and dashboard setup
- `stripe-subscription-lifecycle.md` — subscription state transitions triggered by portal actions
- `stripe-dunning-management.md` — payment method update flow as part of dunning recovery
- `stripe-cancellation-flow.md` — cancellation reason capture and win-back strategies
- `idempotency-keys-payment-apis.md` — protecting downstream calls from retries

---

## Sources

- Stripe Billing Portal API reference: https://docs.stripe.com/api/customer_portal
- Stripe Billing Portal configuration: https://docs.stripe.com/billing/subscriptions/customer-portal
- Cloudflare Workers Request/Response API: https://developers.cloudflare.com/workers/runtime-apis/request/
- OWASP Open Redirect: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html
- `jose` JWT library for Workers: https://github.com/panva/jose
