# Paystack Workers — Africa Payment Integration

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You are building a product for Nigeria, Ghana, Kenya, South Africa, Egypt, Rwanda, or Côte d'Ivoire and need to accept cards, bank transfers, USSD, mobile money, and QR payments from Cloudflare Workers. Paystack (acquired by Stripe, but operating independently) is the dominant gateway across anglophone Africa. Common issues: mishandling the `authorization_code` for recurring charges, confusion between the `initialize` and `charge` endpoints, and webhook verification failure due to body parsing order.

## Context

Paystack's API flow mirrors Stripe's Payment Intents pattern but uses different naming. A transaction is **initialized** on the server (returns `authorization_url` + `reference`), the customer completes on Paystack's hosted page, and your backend **verifies** the transaction using the reference. For saved cards (subscriptions, one-click), Paystack returns an `authorization_code` after first payment — use this for recurring `charge authorization` calls without requiring card re-entry.

Paystack's API base is `https://api.paystack.co`. Auth uses `Bearer sk_live_...` / `Bearer sk_test_...` in the Authorization header. Webhook events use HMAC-SHA512 (not SHA256) signed with your secret key — the same secret used for Bearer auth.

## 1. Environment Setup

```typescript
export interface Env {
  PAYSTACK_SECRET_KEY: string;  // sk_live_... or sk_test_... — Workers Secret
  PAYMENTS_KV: KVNamespace;
}

const PS_API = "https://api.paystack.co";

function psHeaders(env: Env): HeadersInit {
  return {
    Authorization: `Bearer ${env.PAYSTACK_SECRET_KEY}`,
    "Content-Type": "application/json",
  };
}
```

## 2. Initialize a Transaction

The entry point for all customer-facing payments. Returns a hosted checkout URL and a reference to track the transaction.

```typescript
interface PSInitPayload {
  email: string;
  amount: number;              // in kobo (NGN), pesewas (GHS), cents (KES/ZAR) — always smallest unit
  currency?: "NGN" | "GHS" | "KES" | "ZAR" | "EGP" | "RWF" | "XOF";
  reference?: string;          // your idempotency key; Paystack generates one if omitted
  callback_url?: string;       // override account-level callback
  metadata?: Record<string, unknown>;
  channels?: Array<"card" | "bank" | "ussd" | "qr" | "mobile_money" | "bank_transfer">;
}

interface PSInitResponse {
  status: true;
  message: string;
  data: {
    authorization_url: string;
    access_code: string;
    reference: string;
  };
}

async function initializeTransaction(
  env: Env,
  payload: PSInitPayload
): Promise<PSInitResponse["data"]> {
  const res = await fetch(`${PS_API}/transaction/initialize`, {
    method: "POST",
    headers: psHeaders(env),
    body: JSON.stringify(payload),
  });

  const data = await res.json<PSInitResponse | { status: false; message: string }>();

  if (!data.status) {
    throw new Error(`Paystack init error: ${(data as { message: string }).message}`);
  }

  return (data as PSInitResponse).data;
}

// Worker route: POST /checkout/init
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/checkout/init") {
      return new Response("Not found", { status: 404 });
    }

    const body = await request.json<{
      email: string;
      amountNGN: number;
      orderId: string;
    }>();

    const txn = await initializeTransaction(env, {
      email: body.email,
      amount: Math.round(body.amountNGN * 100), // naira → kobo
      currency: "NGN",
      reference: `order_${body.orderId}_${Date.now()}`,
      metadata: { orderId: body.orderId, source: "workers-edge" },
      channels: ["card", "bank", "ussd", "bank_transfer"],
    });

    return Response.json({
      authorizationUrl: txn.authorization_url,
      reference: txn.reference,
    });
  },
};
```

## 3. Verify a Transaction

After the customer completes checkout, your callback URL receives `?reference=...`. Verify server-side before fulfilling.

```typescript
interface PSVerifyResponse {
  status: true;
  data: {
    id: number;
    reference: string;
    status: "success" | "failed" | "abandoned" | "reversed";
    amount: number;
    currency: string;
    paid_at: string;
    gateway_response: string;
    authorization: {
      authorization_code: string;
      card_type: string;
      last4: string;
      exp_month: string;
      exp_year: string;
      reusable: boolean;
      bank: string;
    };
    customer: {
      id: number;
      email: string;
      customer_code: string;
    };
  };
}

async function verifyTransaction(
  env: Env,
  reference: string
): Promise<PSVerifyResponse["data"]> {
  const res = await fetch(
    `${PS_API}/transaction/verify/${encodeURIComponent(reference)}`,
    { headers: psHeaders(env) }
  );

  const data = await res.json<PSVerifyResponse | { status: false; message: string }>();

  if (!data.status) {
    throw new Error(`Paystack verify error: ${(data as { message: string }).message}`);
  }

  const txn = (data as PSVerifyResponse).data;

  if (txn.status !== "success") {
    throw new Error(`Payment not successful: ${txn.gateway_response}`);
  }

  // Persist the authorization_code for recurring charges
  if (txn.authorization.reusable) {
    await env.PAYMENTS_KV.put(
      `ps:auth:${txn.customer.email}`,
      JSON.stringify({
        authCode: txn.authorization.authorization_code,
        last4: txn.authorization.last4,
        cardType: txn.authorization.card_type,
        bank: txn.authorization.bank,
      }),
      { expirationTtl: 60 * 60 * 24 * 365 }
    );
  }

  return txn;
}
```

## 4. Recurring Charge with Authorization Code

Once you have a `reusable` authorization code, charge returning customers without re-entering card details — this is Paystack's equivalent of Stripe's `off_session` payment.

```typescript
async function chargeAuthorization(
  env: Env,
  opts: {
    email: string;
    amountNGN: number;
    authorizationCode: string;
    reference?: string;
    metadata?: Record<string, unknown>;
  }
): Promise<{ id: number; reference: string; status: string; amount: number }> {
  const res = await fetch(`${PS_API}/transaction/charge_authorization`, {
    method: "POST",
    headers: psHeaders(env),
    body: JSON.stringify({
      email: opts.email,
      amount: Math.round(opts.amountNGN * 100),
      authorization_code: opts.authorizationCode,
      reference: opts.reference ?? crypto.randomUUID(),
      metadata: opts.metadata,
    }),
  });

  const data = await res.json<PSVerifyResponse | { status: false; message: string }>();

  if (!data.status) {
    throw new Error(`Charge auth error: ${(data as { message: string }).message}`);
  }

  const txn = (data as PSVerifyResponse).data;
  return {
    id: txn.id,
    reference: txn.reference,
    status: txn.status,
    amount: txn.amount,
  };
}
```

## 5. Webhook Verification (HMAC-SHA512)

Paystack signs webhook events with SHA512, not SHA256. This is a frequent source of bugs when copying patterns from Stripe webhooks.

```typescript
async function verifyPaystackWebhook(
  request: Request,
  secretKey: string
): Promise<{ valid: boolean; body: string }> {
  const body = await request.text(); // read raw text FIRST
  const signature = request.headers.get("x-paystack-signature") ?? "";

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secretKey),
    { name: "HMAC", hash: "SHA-512" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const computed = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  const valid = crypto.timingSafeEqual(
    new TextEncoder().encode(computed),
    new TextEncoder().encode(signature)
  );

  return { valid, body };
}

interface PSWebhookEvent {
  event:
    | "charge.success"
    | "charge.failed"
    | "transfer.success"
    | "transfer.failed"
    | "transfer.reversed"
    | "subscription.create"
    | "subscription.disable";
  data: {
    id: number;
    reference: string;
    amount: number;
    status: string;
    customer: { email: string };
    authorization?: { authorization_code: string; reusable: boolean; last4: string };
  };
}

async function handleWebhook(request: Request, env: Env): Promise<Response> {
  const { valid, body } = await verifyPaystackWebhook(request, env.PAYSTACK_SECRET_KEY);
  if (!valid) return new Response("Unauthorized", { status: 401 });

  const event = JSON.parse(body) as PSWebhookEvent;

  if (event.event === "charge.success") {
    await env.PAYMENTS_KV.put(
      `ps:charge:${event.data.reference}`,
      JSON.stringify({
        id: event.data.id,
        amount: event.data.amount,
        email: event.data.customer.email,
        status: event.data.status,
        authCode: event.data.authorization?.authorization_code,
        reusable: event.data.authorization?.reusable,
      }),
      { expirationTtl: 60 * 60 * 24 * 90 }
    );
  }

  return new Response(null, { status: 200 });
}
```

## Anti-patterns

- **Using SHA256 for webhook verification** — Paystack uses SHA512. SHA256 will always fail, producing a constant stream of 401 errors that look like network or key issues.
- **Fulfilling on redirect callback alone** — the callback URL receives the reference as a query param but is easily faked. Always call `verifyTransaction` from the server before fulfilling.
- **Storing authorization codes in localStorage or cookies** — they're equivalent to card credentials. Store only in KV keyed by your internal customer ID or email.
- **Not specifying `channels`** — leaving `channels` empty defaults to all available methods, including some that add friction for users in specific markets (e.g., QR in Nigeria is uncommon). Filter to what's relevant.
- **Sending amounts in naira instead of kobo** — ₦500 must be sent as `50000`. Paystack will silently create a ₦5 transaction if you send `500`.

## Gotchas

- Paystack Ghana (GHS) requires `currency: "GHS"` explicitly — the account's default may be NGN even on a multi-currency plan.
- Mobile money channels (`mobile_money`) are only available in Ghana and Kenya; attempting them in Nigeria returns a 422.
- Refunds are initiated via `POST /refund` with a `transaction` ID (numeric, not reference string).
- `access_code` (from initialize) expires in 15 minutes. Don't cache it — redirect immediately.
- South Africa (ZAR) transactions via Paystack require the business to be registered in SA or go through a Paystack SA entity — confirm this during onboarding.

## Verification

```bash
# Initialize a test transaction
curl -X POST https://api.paystack.co/transaction/initialize \
  -H "Authorization: Bearer sk_test_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","amount":50000,"currency":"NGN"}'

# Verify a completed test transaction
curl https://api.paystack.co/transaction/verify/YOUR_REFERENCE \
  -H "Authorization: Bearer sk_test_YOUR_KEY"

# Expected verify response: {"status":true,"data":{"status":"success","amount":50000}}
```

## Related

- `flutterwave-workers-pan-africa-payments.md` — Flutterwave for broader African coverage
- `payment-orchestration-multi-psp-routing.md` — routing African traffic between Paystack and Flutterwave
- `nowpayments-webhook-hmac-sha512.md` — SHA512 webhook pattern (same hash algorithm)
- `idempotency-keys-payment-apis.md` — reference uniqueness strategy
- `subscription-billing-lifecycle.md` — using authorization_code for subscriptions

## Sources

- Paystack API reference: https://paystack.com/docs/api/
- Accept Payments: https://paystack.com/docs/payments/accept-payments/
- Recurring charges: https://paystack.com/docs/payments/recurring-charges/
- Webhooks: https://paystack.com/docs/payments/webhooks/
- Multi-currency: https://paystack.com/docs/payments/multi-currency/
