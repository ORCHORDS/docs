# Zip (formerly Quadpay) and Sezzle BNPL Integration via Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

You want to offer "Buy Now, Pay Later" installments at checkout via Zip (formerly Quadpay — splits into 4 payments over 6 weeks) or Sezzle (also 4 payments, 0% interest to shopper). Unlike Klarna or Afterpay (which Stripe wraps), Zip and Sezzle require direct API integrations that your Cloudflare Worker must handle: creating an order session, redirecting the shopper, capturing the webhook confirmation, and settling the authorized amount. BNPL approval decisions are real-time but funds settle to your account on a daily or weekly schedule depending on the provider.

---

## Context

Both Zip and Sezzle follow the same flow pattern:

1. **Order creation** — your Worker POSTs order details (amount, line items, redirect URLs) to the BNPL provider's API and receives a redirect URL.
2. **Shopper redirect** — the shopper is redirected to Zip/Sezzle's hosted UI for identity verification and approval.
3. **Callback redirect** — after approval/decline, the provider redirects back to your `success_url` or `cancel_url` with a token query parameter.
4. **Capture / confirm** — your Worker calls the BNPL API to capture the authorization against the token. If you skip this step, the authorization expires (typically 10–30 minutes).
5. **Webhook confirmation** — the provider sends an `order.authorized` or `order.cancelled` webhook you must validate and reconcile in D1.

This article focuses on Zip's API. The Sezzle integration is structurally identical — replace the base URL and auth scheme (Sezzle uses merchant ID + private key in the Authorization header).

Workers constraints:
- The Zip redirect URL must be HTTPS. Workers satisfy this automatically.
- Zip's API requires your Merchant Access Token in the `Authorization: Bearer` header.
- Store the `order_id` returned by Zip's API in D1 immediately so you can look it up when the redirect callback arrives.

---

## Section 1 — D1 Schema for BNPL Orders

```sql
-- migrations/0030_bnpl_orders.sql
CREATE TABLE IF NOT EXISTS bnpl_orders (
  id                TEXT PRIMARY KEY,     -- internal UUID
  provider          TEXT NOT NULL,        -- 'zip' | 'sezzle'
  provider_order_id TEXT UNIQUE,          -- ID from BNPL provider
  user_id           TEXT,
  amount_cents      INTEGER NOT NULL,
  currency          TEXT NOT NULL DEFAULT 'USD',
  status            TEXT NOT NULL DEFAULT 'pending',
  -- pending | authorized | captured | cancelled | expired | refunded
  redirect_token    TEXT,                 -- token in callback URL
  idempotency_key   TEXT NOT NULL UNIQUE,
  created_at        INTEGER NOT NULL,
  captured_at       INTEGER,
  expires_at        INTEGER
);

CREATE INDEX IF NOT EXISTS idx_bnpl_token ON bnpl_orders (redirect_token);
CREATE INDEX IF NOT EXISTS idx_bnpl_user ON bnpl_orders (user_id, created_at DESC);
```

---

## Section 2 — Creating a Zip Order Session

```typescript
// worker/src/handlers/zip-order.ts
import { v4 as uuidv4 } from "uuid";

export interface Env {
  ZIP_MERCHANT_TOKEN: string;    // Worker secret
  ZIP_ENV: "sandbox" | "production";
  BNPL_DB: D1Database;
}

const ZIP_BASE: Record<string, string> = {
  sandbox: "https://api.sandbox.zip.co",
  production: "https://api.zip.co",
};

interface ZipOrderItem {
  name: string;
  sku: string;
  quantity: number;
  price: number;          // in dollars (Zip uses dollars, not cents)
  item_uri?: string;
  image_uri?: string;
}

export async function createZipOrder(
  userId: string,
  amountCents: number,
  items: ZipOrderItem[],
  idempotencyKey: string,
  env: Env
): Promise<{ redirectUrl: string; orderId: string }> {
  const base = ZIP_BASE[env.ZIP_ENV];

  // Check for existing session
  const existing = await env.BNPL_DB.prepare(
    `SELECT provider_order_id, status FROM bnpl_orders WHERE idempotency_key = ?`
  )
    .bind(idempotencyKey)
    .first<{ provider_order_id: string; status: string }>();

  if (existing?.provider_order_id) {
    throw new Error(`Order already exists for idempotency key: ${idempotencyKey}`);
  }

  const internalId = uuidv4();
  const amountDollars = (amountCents / 100).toFixed(2);

  const resp = await fetch(`${base}/v2/checkouts`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.ZIP_MERCHANT_TOKEN}`,
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({
      shopper: { redirect: {
        success_uri: `https://example.com/checkout/zip/callback?status=success&ref=${internalId}`,
        cancel_uri:  `https://example.com/checkout/zip/callback?status=cancel&ref=${internalId}`,
      }},
      order: {
        amount: parseFloat(amountDollars),
        currency: "USD",
        reference: internalId,
        items,
      },
    }),
  });

  if (!resp.ok) {
    const err = await resp.json() as { message?: string };
    throw new Error(`Zip order creation failed: ${err.message}`);
  }

  const data = await resp.json() as {
    id: string;
    uri: string;            // redirect URL for the shopper
    expires_at: string;     // ISO 8601
  };

  const expiresAt = Math.floor(new Date(data.expires_at).getTime() / 1000);

  await env.BNPL_DB.prepare(
    `INSERT INTO bnpl_orders
       (id, provider, provider_order_id, user_id, amount_cents, status,
        idempotency_key, created_at, expires_at)
     VALUES (?, 'zip', ?, ?, ?, 'pending', ?, ?, ?)`
  )
    .bind(internalId, data.id, userId, amountCents,
          idempotencyKey, Math.floor(Date.now() / 1000), expiresAt)
    .run();

  return { redirectUrl: data.uri, orderId: internalId };
}
```

---

## Section 3 — Handling the Redirect Callback and Capturing the Authorization

```typescript
// worker/src/handlers/zip-callback.ts
import { Env } from "./zip-order";

const ZIP_BASE: Record<string, string> = {
  sandbox: "https://api.sandbox.zip.co",
  production: "https://api.zip.co",
};

export async function handleZipCallback(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const status = url.searchParams.get("status");
  const internalRef = url.searchParams.get("ref");
  const zipOrderId = url.searchParams.get("checkoutId"); // Zip appends this

  if (!internalRef || !zipOrderId) {
    return new Response("Missing parameters", { status: 400 });
  }

  const order = await env.BNPL_DB.prepare(
    `SELECT id, amount_cents, status, expires_at FROM bnpl_orders WHERE id = ?`
  )
    .bind(internalRef)
    .first<{ id: string; amount_cents: number; status: string; expires_at: number }>();

  if (!order) return new Response("Order not found", { status: 404 });
  if (order.status !== "pending") {
    return Response.redirect("https://example.com/checkout/complete", 302);
  }

  if (status === "cancel") {
    await env.BNPL_DB.prepare(
      `UPDATE bnpl_orders SET status = 'cancelled', redirect_token = ? WHERE id = ?`
    ).bind(zipOrderId, internalRef).run();
    return Response.redirect("https://example.com/checkout/cancelled", 302);
  }

  // Capture the authorization
  const base = ZIP_BASE[env.ZIP_ENV];
  const captureResp = await fetch(`${base}/v2/checkouts/${zipOrderId}/captures`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.ZIP_MERCHANT_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ amount: (order.amount_cents / 100).toFixed(2) }),
  });

  if (!captureResp.ok) {
    const err = await captureResp.json() as { message?: string };
    await env.BNPL_DB.prepare(
      `UPDATE bnpl_orders SET status = 'expired', redirect_token = ? WHERE id = ?`
    ).bind(zipOrderId, internalRef).run();
    console.error("Zip capture failed:", err.message);
    return Response.redirect("https://example.com/checkout/error", 302);
  }

  await env.BNPL_DB.prepare(
    `UPDATE bnpl_orders
     SET status = 'captured', redirect_token = ?, captured_at = ?
     WHERE id = ?`
  ).bind(zipOrderId, Math.floor(Date.now() / 1000), internalRef).run();

  return Response.redirect("https://example.com/checkout/success", 302);
}
```

---

## Section 4 — Webhook Handler for Async Notifications

```typescript
// worker/src/handlers/zip-webhook.ts
import { Env } from "./zip-order";

export async function handleZipWebhook(
  request: Request,
  env: Env & { ZIP_WEBHOOK_SECRET: string }
): Promise<Response> {
  const body = await request.text();

  // Zip signs webhooks with HMAC-SHA256 in X-Zip-Signature header
  const sig = request.headers.get("X-Zip-Signature") ?? "";
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.ZIP_WEBHOOK_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]
  );
  const computed = await crypto.subtle.sign(
    "HMAC", key, new TextEncoder().encode(body)
  );
  const computedHex = Array.from(new Uint8Array(computed))
    .map(b => b.toString(16).padStart(2, "0")).join("");

  if (sig !== computedHex) return new Response("Unauthorized", { status: 401 });

  const event = JSON.parse(body) as {
    event_type: string;
    payload: { order_id: string; status: string };
  };

  const statusMap: Record<string, string> = {
    "order.authorised": "authorized",
    "order.cancelled": "cancelled",
    "order.refunded": "refunded",
  };

  const newStatus = statusMap[event.event_type];
  if (newStatus) {
    await env.BNPL_DB.prepare(
      `UPDATE bnpl_orders SET status = ? WHERE redirect_token = ?`
    )
      .bind(newStatus, event.payload.order_id)
      .run();
  }

  return new Response(JSON.stringify({ received: true }), { status: 200 });
}
```

---

## Section 5 — Sezzle Adapter (Structural Differences from Zip)

```typescript
// worker/src/lib/sezzle.ts
// Sezzle uses: Authorization: Bearer {token} obtained via /v2/authentication
// Base: https://sandbox.gateway.sezzle.com (sandbox)
//       https://gateway.sezzle.com (production)
// Session create: POST /v2/session
// Capture: POST /v2/order/{order_uuid}/capture
// Amounts: in cents (same as Stripe) unlike Zip which uses dollars

export async function getSezzleToken(merchantId: string, apiKey: string, sandbox: boolean): Promise<string> {
  const base = sandbox ? "https://sandbox.gateway.sezzle.com" : "https://gateway.sezzle.com";
  const resp = await fetch(`${base}/v2/authentication`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ public_key: merchantId, private_key: apiKey }),
  });
  const data = await resp.json() as { token: string };
  return data.token;
}

// The session creation payload mirrors Zip but uses `order.intent = "AUTH"`
// and amounts in cents. The redirect flow is otherwise identical.
// See: https://docs.sezzle.com/#create-a-session
```

---

## Anti-Patterns

- **Granting order fulfillment before calling the capture endpoint.** The shopper's callback redirect confirms *intent*, not funds. You must call the capture endpoint and receive a `200 OK` before considering the order paid. Skipping capture means the authorization expires unpaid.
- **Using the callback redirect URL as the sole source of truth.** Redirect callbacks can be replayed or forged. Always reconcile against the webhook event (`order.authorised`) before fulfilling high-value orders.
- **Storing the BNPL order in the client session (cookie/localStorage) only.** Workers are stateless across requests; the callback arrives in a new Worker request context. The `internalRef` in the redirect URL is the only cross-request identifier — look it up from D1.
- **Mixing Zip dollar amounts with Sezzle cent amounts.** Zip's API uses floating-point dollar strings; Sezzle uses integer cent amounts. Build provider-specific adapters rather than a shared amount field.
- **Not enforcing expiry.** Zip authorizations expire (typically 10–60 minutes depending on merchant config). If the shopper doesn't complete the flow before `expires_at`, the capture endpoint returns a 422. Check expiry in D1 before attempting capture.

---

## Gotchas

1. **Zip renamed from Quadpay.** Merchant dashboards and older docs may still reference "Quadpay" branding. The API domain is `api.zip.co`; test credentials from the Zip Partner Portal.
2. **Sezzle's session UUID is the capture reference, not the checkout ID.** Sezzle returns `order.uuid` in the session response; this UUID — not the session ID — is used in the capture endpoint path.
3. **Both providers send webhooks asynchronously after capture.** The `order.authorised` webhook may arrive seconds to minutes after your capture API call returns. Do not wait synchronously for it.
4. **Zip requires HTTPS for redirect URIs in production.** Workers provide HTTPS automatically; custom domains must have a valid TLS certificate deployed before going live.
5. **Refunds go through the BNPL provider, not your acquirer.** You cannot issue a Zip/Sezzle refund through Stripe's refund endpoint. Call Zip's `POST /v2/orders/{id}/refunds` or Sezzle's `POST /v2/order/{uuid}/refund` endpoint.

---

## Verification

```bash
# 1. Create a Zip sandbox checkout session via the Worker
curl -X POST https://api.example.com/checkout/zip/create \
  -H "Content-Type: application/json" \
  -d '{"amountCents":15000,"userId":"test-user","idempotencyKey":"test-001",
       "items":[{"name":"Widget","sku":"SKU1","quantity":1,"price":150.00}]}'
# Expect: {"redirectUrl":"https://checkout.sandbox.zip.co/...","orderId":"uuid"}

# 2. Simulate the approval redirect (sandbox skips real checkout)
# Navigate to the redirectUrl in a browser, complete sandbox flow

# 3. Verify D1 status transitions
wrangler d1 execute BNPL_DB --remote \
  --command "SELECT id, provider_order_id, status, captured_at FROM bnpl_orders ORDER BY created_at DESC LIMIT 5;"

# 4. Confirm webhook updates the status
# Send a test webhook via the Zip Partner Portal sandbox webhook tester
wrangler d1 execute BNPL_DB --remote \
  --command "SELECT status FROM bnpl_orders WHERE redirect_token = 'SANDBOX_ORDER_ID';"
```

---

## Related

- `documentation/docs/policies/payments/affirm-bnpl-workers-integration.md`
- `documentation/docs/policies/payments/stripe-afterpay-integration.md`
- `documentation/docs/policies/payments/stripe-klarna-bnpl.md`
- `documentation/docs/policies/payments/payment-state-machine-design.md`
- `documentation/docs/policies/payments/idempotency-keys-payment-apis.md`

---

## Sources

- Zip API documentation — https://docs.zip.co/reference/
- Zip checkout flow — https://docs.zip.co/docs/checkout-flow
- Sezzle API reference — https://docs.sezzle.com/
- Sezzle session create — https://docs.sezzle.com/#create-a-session
- Cloudflare D1 — https://developers.cloudflare.com/d1/
