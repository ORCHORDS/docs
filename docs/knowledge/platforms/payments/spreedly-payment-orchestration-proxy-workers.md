# Spreedly Payment Orchestration Proxy via Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

You want to accept card payments across multiple payment gateways — Stripe, Braintree, Authorize.Net, Adyen — without storing raw PANs on your servers or rebuilding tokenization for each gateway. Spreedly acts as a PAN vault and payment proxy: card numbers are tokenized once in Spreedly's PCI-DSS Level 1 vault, and Spreedly forwards the purchase to whichever gateway you route to via a single API. The Cloudflare Worker handles routing logic, stores transaction records in D1, and proxies the Spreedly API without ever touching raw card data.

---

## Context

Spreedly's model has three key entities:
1. **Payment Methods** — tokenized card or bank account. Created client-side via Spreedly.js or server-side via the tokenize endpoint. The resulting token (`payment_method_token`) is a stable identifier you store in D1.
2. **Gateways** — PSP connections configured in the Spreedly dashboard (each has a `gateway_token`). You can have multiple gateways of the same or different types.
3. **Transactions** — a purchase, authorize, capture, void, or credit against a payment method routed to a specific gateway.

The Worker's role:
- Receive the client's `payment_method_token` from the browser (set via Spreedly.js — the raw PAN never reaches your Worker).
- Apply routing logic: primary gateway, fallback gateway, cost optimization, geographic routing.
- POST to Spreedly's `/gateways/{gateway_token}/purchase.json` (or authorize/capture for deferred flows).
- Store the resulting transaction token and status in D1.
- Handle Spreedly webhook deliveries for async status updates.

Spreedly uses basic auth: `SPREEDLY_ENV_KEY:SPREEDLY_ENV_SECRET` as the Authorization header, base64-encoded.

---

## Section 1 — D1 Schema and Routing Configuration

```sql
-- migrations/0025_spreedly.sql
CREATE TABLE IF NOT EXISTS spreedly_payment_methods (
  id                    TEXT PRIMARY KEY,
  spreedly_token        TEXT NOT NULL UNIQUE,   -- pm_... token from Spreedly
  user_id               TEXT NOT NULL,
  card_type             TEXT,                   -- visa, master, american_express
  last_four             TEXT,
  exp_month             INTEGER,
  exp_year              INTEGER,
  created_at            INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS spreedly_transactions (
  id                    TEXT PRIMARY KEY,
  spreedly_token        TEXT UNIQUE,             -- transaction token from Spreedly
  payment_method_token  TEXT NOT NULL,
  gateway_token         TEXT NOT NULL,
  amount_cents          INTEGER NOT NULL,
  currency_code         TEXT NOT NULL DEFAULT 'USD',
  transaction_type      TEXT NOT NULL DEFAULT 'purchase',
  -- purchase | authorize | capture | void | credit
  succeeded             INTEGER NOT NULL DEFAULT 0,
  response_code         TEXT,
  gateway_message       TEXT,
  idempotency_key       TEXT NOT NULL UNIQUE,
  created_at            INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sp_txn_pm ON spreedly_transactions (payment_method_token, created_at DESC);
```

```typescript
// worker/src/lib/spreedly.ts
export interface Env {
  SPREEDLY_ENV_KEY: string;
  SPREEDLY_ENV_SECRET: string;
  SPREEDLY_GATEWAY_PRIMARY: string;    // gateway_token for primary PSP
  SPREEDLY_GATEWAY_FALLBACK: string;   // gateway_token for fallback PSP
  SPREEDLY_DB: D1Database;
}

const SPREEDLY_BASE = "https://core.spreedly.com/v1";

export function spreedlyHeaders(env: Env): HeadersInit {
  const creds = btoa(`${env.SPREEDLY_ENV_KEY}:${env.SPREEDLY_ENV_SECRET}`);
  return {
    Authorization: `Basic ${creds}`,
    "Content-Type": "application/json",
    Accept: "application/json",
  };
}
```

---

## Section 2 — Gateway Routing Logic with Fallback

```typescript
// worker/src/lib/spreedly-router.ts
import { Env, spreedlyHeaders, SPREEDLY_BASE } from "./spreedly";

interface SpreedlyPurchaseResult {
  transactionToken: string;
  succeeded: boolean;
  responseCode: string;
  message: string;
  gatewayToken: string;
}

async function attemptPurchase(
  gatewayToken: string,
  paymentMethodToken: string,
  amountCents: number,
  currencyCode: string,
  idempotencyKey: string,
  env: Env
): Promise<SpreedlyPurchaseResult> {
  const resp = await fetch(
    `${SPREEDLY_BASE}/gateways/${gatewayToken}/purchase.json`,
    {
      method: "POST",
      headers: {
        ...spreedlyHeaders(env),
        "X-Spreedly-Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({
        transaction: {
          payment_method_token: paymentMethodToken,
          amount: amountCents,
          currency_code: currencyCode,
          retain_on_success: true,   // keep PM in vault on success
        },
      }),
    }
  );

  const data = await resp.json() as {
    transaction: {
      token: string;
      succeeded: boolean;
      response: { error_code: string; message: string };
    };
  };

  return {
    transactionToken: data.transaction.token,
    succeeded: data.transaction.succeeded,
    responseCode: data.transaction.response?.error_code ?? "",
    message: data.transaction.response?.message ?? "",
    gatewayToken,
  };
}

const RETRIABLE_CODES = new Set([
  "call_issuer", "processing_error", "card_velocity_exceeded"
]);

export async function routeAndCharge(
  paymentMethodToken: string,
  amountCents: number,
  currencyCode: string,
  idempotencyKey: string,
  env: Env
): Promise<SpreedlyPurchaseResult> {
  // Try primary gateway
  let result = await attemptPurchase(
    env.SPREEDLY_GATEWAY_PRIMARY,
    paymentMethodToken,
    amountCents,
    currencyCode,
    `${idempotencyKey}:primary`,
    env
  );

  if (result.succeeded) return result;

  // Retry on fallback only for soft declines
  if (RETRIABLE_CODES.has(result.responseCode)) {
    const fallback = await attemptPurchase(
      env.SPREEDLY_GATEWAY_FALLBACK,
      paymentMethodToken,
      amountCents,
      currencyCode,
      `${idempotencyKey}:fallback`,
      env
    );
    if (fallback.succeeded) return fallback;
  }

  return result; // return primary result if fallback also failed
}
```

---

## Section 3 — Worker Purchase Handler with D1 Persistence

```typescript
// worker/src/handlers/spreedly-purchase.ts
import { v4 as uuidv4 } from "uuid";
import { routeAndCharge, Env } from "../lib/spreedly-router";

export async function handlePurchase(request: Request, env: Env): Promise<Response> {
  const body = await request.json() as {
    paymentMethodToken: string;
    amountCents: number;
    currencyCode?: string;
    idempotencyKey: string;
    userId: string;
  };

  const {
    paymentMethodToken,
    amountCents,
    currencyCode = "USD",
    idempotencyKey,
    userId,
  } = body;

  // Check for prior attempt
  const existing = await env.SPREEDLY_DB.prepare(
    `SELECT spreedly_token, succeeded FROM spreedly_transactions WHERE idempotency_key = ?`
  )
    .bind(idempotencyKey)
    .first<{ spreedly_token: string; succeeded: number }>();

  if (existing) {
    return Response.json({
      transactionToken: existing.spreedly_token,
      succeeded: existing.succeeded === 1,
      duplicate: true,
    });
  }

  const internalId = uuidv4();

  // Insert pending row before calling Spreedly
  await env.SPREEDLY_DB.prepare(
    `INSERT INTO spreedly_transactions
       (id, payment_method_token, gateway_token, amount_cents, currency_code,
        transaction_type, succeeded, idempotency_key, created_at)
     VALUES (?, ?, 'routing', ?, ?, 'purchase', 0, ?, ?)`
  )
    .bind(internalId, paymentMethodToken, amountCents, currencyCode,
          idempotencyKey, Math.floor(Date.now() / 1000))
    .run();

  const result = await routeAndCharge(
    paymentMethodToken, amountCents, currencyCode, idempotencyKey, env
  );

  await env.SPREEDLY_DB.prepare(
    `UPDATE spreedly_transactions
     SET spreedly_token = ?, gateway_token = ?, succeeded = ?,
         response_code = ?, gateway_message = ?
     WHERE id = ?`
  )
    .bind(
      result.transactionToken,
      result.gatewayToken,
      result.succeeded ? 1 : 0,
      result.responseCode,
      result.message,
      internalId
    )
    .run();

  return Response.json({
    transactionToken: result.transactionToken,
    succeeded: result.succeeded,
    responseCode: result.responseCode,
    message: result.message,
  }, { status: result.succeeded ? 200 : 402 });
}
```

---

## Section 4 — Tokenizing a Card via Spreedly.js (Client-Side Pattern)

```html
<!-- client/checkout.html — hosted payment form -->
<!-- Spreedly.js never sends the raw PAN to your server -->
<script src="https://core.spreedly.com/iframe/iframe-v1.min.js"></script>
<script>
  Spreedly.init("YOUR_ENV_KEY", {
    numberEl: "spreedly-number",
    cvvEl: "spreedly-cvv",
  });

  Spreedly.on("ready", () => Spreedly.setStyle("number", "font-size:16px;"));

  Spreedly.on("paymentMethod", async (token, pmData) => {
    // token is the payment_method_token — send to your Worker, never the raw PAN
    const resp = await fetch("/api/purchase", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        paymentMethodToken: token,
        amountCents: 4999,
        currencyCode: "USD",
        idempotencyKey: crypto.randomUUID(),
        userId: currentUserId,
      }),
    });
    const result = await resp.json();
    // handle result.succeeded
  });

  document.getElementById("pay-btn").addEventListener("click", () => {
    Spreedly.tokenizeCreditCard({
      full_name: document.getElementById("name").value,
      month: document.getElementById("exp-month").value,
      year: document.getElementById("exp-year").value,
    });
  });
</script>
```

---

## Section 5 — Webhook Handler for Async Transaction Updates

```typescript
// worker/src/handlers/spreedly-webhook.ts
import { Env } from "../lib/spreedly";

export async function handleSpreedlyWebhook(
  request: Request,
  env: Env & { SPREEDLY_WEBHOOK_SECRET: string }
): Promise<Response> {
  // Spreedly signs webhooks with HMAC-SHA256 via X-Spreedly-Signature header
  const body = await request.text();
  const sig = request.headers.get("X-Spreedly-Signature") ?? "";

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.SPREEDLY_WEBHOOK_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]
  );
  const expected = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const expectedHex = Array.from(new Uint8Array(expected))
    .map(b => b.toString(16).padStart(2, "0")).join("");

  if (sig !== expectedHex) {
    return new Response("Invalid signature", { status: 401 });
  }

  const event = JSON.parse(body) as {
    event: string;
    transaction: {
      token: string;
      succeeded: boolean;
      response: { error_code: string; message: string };
    };
  };

  if (event.event.startsWith("gateway_transaction.")) {
    const txn = event.transaction;
    await env.SPREEDLY_DB.prepare(
      `UPDATE spreedly_transactions
       SET succeeded = ?, response_code = ?, gateway_message = ?
       WHERE spreedly_token = ?`
    )
      .bind(
        txn.succeeded ? 1 : 0,
        txn.response?.error_code ?? null,
        txn.response?.message ?? null,
        txn.token
      )
      .run();
  }

  return new Response(JSON.stringify({ received: true }), { status: 200 });
}
```

---

## Anti-Patterns

- **Sending the raw PAN to your Worker for tokenization.** The entire point of Spreedly is to keep raw card data out of your infrastructure. Always tokenize client-side via Spreedly.js or directly via the Spreedly server-to-server tokenize endpoint with TLS — never pass PANs through your Workers.
- **Using a single gateway token for all traffic.** Spreedly's value is multi-gateway routing. Hard-coding one gateway recreates single-gateway lock-in without the vault benefits.
- **Retrying hard declines on the fallback gateway.** Routing a `do_not_honor` or `stolen_card` decline to a second gateway wastes quota and increases fraud risk. Only retry soft/technical declines.
- **Storing the raw `spreedly_token` in your UI.** Expose only your internal transaction ID to the client; transaction tokens carry enough information to query sensitive data from Spreedly's API.
- **Forgetting `retain_on_success: true`.** Without this flag, Spreedly removes the payment method from the vault after a successful transaction. If you want to reuse the card for subscriptions or future charges, include it.

---

## Gotchas

1. **Amount is in cents (minor currency units), not dollars.** Spreedly's `amount` field is an integer in the smallest currency unit — same as Stripe. This is the opposite of Dwolla.
2. **Idempotency key scope is per environment.** Spreedly idempotency keys are scoped to your environment key. A key used in sandbox is independent from the same key in production.
3. **`gateway_transaction.pending` does not mean succeeded.** Some gateways (e.g., ACH-backed) return a pending status. Listen for `gateway_transaction.succeeded` webhooks for authoritative completion.
4. **Payment method expiry.** Spreedly stores expiry dates but does not automatically retire expired cards. Implement your own expiry check before routing to avoid predictable soft declines.
5. **Test card numbers per gateway.** Each gateway in Spreedly sandbox uses its own test card set. Spreedly's sandbox `test` gateway (`token: T0k3nTe5t`) accepts generic test numbers, but real gateway test credentials require the gateway's own test cards.

---

## Verification

```bash
# 1. Tokenize a test card directly via Spreedly REST
curl -X POST https://core.spreedly.com/v1/payment_methods.json \
  -u "ENV_KEY:ENV_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"payment_method":{"credit_card":{"first_name":"Test","last_name":"User",
       "number":"4111111111111111","month":"12","year":"2030","verification_value":"123"}}}'

# 2. Run a purchase against the Spreedly test gateway
curl -X POST "https://core.spreedly.com/v1/gateways/GATEWAY_TOKEN/purchase.json" \
  -u "ENV_KEY:ENV_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"transaction":{"payment_method_token":"PM_TOKEN","amount":1000,"currency_code":"USD"}}'

# 3. Verify D1 transaction record
wrangler d1 execute SPREEDLY_DB --remote \
  --command "SELECT id, succeeded, gateway_token, response_code FROM spreedly_transactions ORDER BY created_at DESC LIMIT 5;"

# 4. Confirm idempotency (call purchase endpoint twice with the same key)
# Second call should return the cached row, not a new Spreedly transaction
```

---

## Related

- `documentation/docs/policies/payments/payment-orchestration-multi-psp-routing.md`
- `documentation/docs/policies/payments/gateway-failover-circuit-breakers.md`
- `documentation/docs/policies/payments/tokenization-vault-patterns.md`
- `documentation/docs/policies/payments/pci-dss-scope-reduction-tokenization.md`
- `documentation/docs/policies/payments/idempotency-keys-payment-apis.md`

---

## Sources

- Spreedly Core API reference — https://docs.spreedly.com/reference/api/v1/
- Spreedly.js tokenization — https://docs.spreedly.com/spreedly-js/
- Spreedly gateway routing — https://docs.spreedly.com/basics/gateway/
- Spreedly webhook signatures — https://docs.spreedly.com/basics/integration/webhooks/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
