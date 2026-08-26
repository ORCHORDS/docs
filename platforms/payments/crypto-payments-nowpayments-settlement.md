# Crypto Payments — NOWPayments Settlement

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Crypto payment webhooks arrive but orders remain in `waiting`
state, partial payments are silently dropped, or the exchange
rate lock expires before a user completes the transfer, leading
to underpayment disputes.

## Context

example.com accepts crypto as a payment alternative (anonymous
users who prefer not to attach a card). We use NOWPayments as
the on/off-ramp. Our Cloudflare Worker handles the webhook,
verifies the HMAC-SHA512 signature, and writes idempotent
records to D1. Creators can choose fiat auto-convert or USDT
hold for their earnings.

## 1. NOWPayments API — Create Payment

```typescript
// workers/src/payments/nowpayments.ts
const BASE = "https://api.nowpayments.io/v1";

export interface CreatePaymentRequest {
  price_amount: number;       // USD value
  price_currency: "usd";
  pay_currency: string;       // "btc" | "eth" | "sol" | "usdttrc20"
  order_id: string;           // WAM internal order UUID
  order_description: string;
  ipn_callback_url: string;   // must be HTTPS
}

export interface NowPayment {
  payment_id: string;
  payment_status: string;     // see state machine below
  pay_address: string;        // user sends crypto here
  price_amount: number;
  price_currency: string;
  pay_amount: number;         // crypto amount expected
  pay_currency: string;
  created_at: string;
  expiration_estimate_date: string; // ~30 min rate lock
}

export async function createPayment(
  body: CreatePaymentRequest,
  apiKey: string,
): Promise<NowPayment> {
  const resp = await fetch(`${BASE}/payment`, {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`NOWPayments error ${resp.status}: ${err}`);
  }
  return resp.json<NowPayment>();
}
```

Store `payment_id`, `pay_address`, `pay_amount`, and
`expiration_estimate_date` in D1 `crypto_payments` immediately.

## 2. Payment Status State Machine

```
waiting ──► confirming ──► confirmed ──► sending ──► finished
   │                                                      │
   │                                                      │
   └──► partially_paid  ──► (manual review)               │
   │                                                      │
   └──► failed                                            │
   └──► expired          ─────────────────────────────────┘
                                               (no action)
```

Only `finished` should unlock access. `confirmed` means the
block is confirmed but settlement is not complete — do not
provision at this stage.

## 3. Webhook Signature Verification (HMAC-SHA512)

NOWPayments signs every IPN callback with the API secret using
HMAC-SHA512 over the JSON body sorted by keys.

```typescript
// workers/src/payments/nowpayments-webhook.ts
import { createHmac } from "node:crypto"; // unavailable in Workers
// Use SubtleCrypto instead:

async function verifySignature(
  rawBody: string,
  signature: string,
  secret: string,
): Promise<boolean> {
  const encoder = new TextEncoder();

  // NOWPayments sorts JSON keys alphabetically before signing
  const parsed = JSON.parse(rawBody);
  const sorted = JSON.stringify(
    Object.fromEntries(Object.entries(parsed).sort()),
  );

  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-512" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign(
    "HMAC",
    key,
    encoder.encode(sorted),
  );
  const computed = Array.from(new Uint8Array(mac))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return computed === signature.toLowerCase();
}

export async function handleIpn(
  request: Request,
  env: Env,
): Promise<Response> {
  const sig = request.headers.get("x-nowpayments-sig");
  if (!sig) return new Response("Missing signature", { status: 401 });

  const rawBody = await request.text();
  const valid = await verifySignature(rawBody, sig, env.NOW_IPN_SECRET);
  if (!valid) return new Response("Invalid signature", { status: 401 });

  const payload = JSON.parse(rawBody);
  await processIpn(payload, env);
  return new Response("OK");
}
```

## 4. Idempotency via D1

NOWPayments may re-deliver the same webhook (network timeout,
retry). Use `payment_id` + `payment_status` as the idempotency
key:

```typescript
async function processIpn(
  payload: Record<string, unknown>,
  env: Env,
): Promise<void> {
  const { payment_id, payment_status, actually_paid,
    pay_amount, order_id } = payload as {
    payment_id: string;
    payment_status: string;
    actually_paid: number;
    pay_amount: number;
    order_id: string;
  };

  // Idempotency check
  const existing = await env.DB.prepare(
    `SELECT id FROM crypto_ipn_log
     WHERE payment_id = ? AND status = ?`,
  ).bind(payment_id, payment_status).first();
  if (existing) return; // already processed

  await env.DB.prepare(
    `INSERT INTO crypto_ipn_log
     (payment_id, status, actually_paid, received_at)
     VALUES (?, ?, ?, ?)`,
  ).bind(payment_id, payment_status,
    actually_paid, Date.now()).run();

  if (payment_status === "finished") {
    await grantAccess(order_id, env);
  } else if (payment_status === "partially_paid") {
    await flagPartialPayment(payment_id,
      actually_paid, pay_amount, env);
  }
}
```

## 5. Exchange Rate Lock and Partial Payments

NOWPayments locks the exchange rate for approximately 30 minutes
(`expiration_estimate_date`). If the user sends after expiry,
the `pay_amount` required changes and underpayment occurs.

Underpayment thresholds:

```
┌─────────────────────────┬───────────────────────────────┐
│ Shortfall               │ Action                        │
├─────────────────────────┼───────────────────────────────┤
│ < 1 % of pay_amount     │ Accept as full (rounding)     │
│ 1 % – 10 %              │ Flag as partially_paid;        │
│                         │ request top-up or refund       │
│ > 10 %                  │ Treat as failed; full refund  │
└─────────────────────────┴───────────────────────────────┘
```

Configure the threshold in NOWPayments Dashboard under
"Partially paid threshold." WAM default: 1 %. The platform
absorbs rounding differences < 1 %.

On partial payment, send the user an in-app notification with
the shortfall amount and a new deposit address via a
`create_payment` call referencing the same `order_id` with
suffix `-top-up-1`.

## 6. Settlement — Fiat Auto-Convert vs USDT Hold

Creators choose settlement currency during onboarding:

```typescript
// NOWPayments sub-partner payout config
// Set via Dashboard or Custody API
const settlementOptions = {
  auto_convert: {
    // NOWPayments converts to USD and sends via ACH/SWIFT
    currency: "usd",
    payout_destination: "bank_account_xxxx",
  },
  usdt_hold: {
    // Holds USDT in custodial wallet; creator withdraws
    currency: "usdttrc20",
    payout_destination: "TRC20_wallet_address",
  },
};
```

For WAM, creators on Solana wallets can also receive USDT-SPL
via Helius-facilitated transfers. This path requires
co-ordination with the Solana/Helius integration team and
is out of scope for NOWPayments settlement itself.

## 7. FinCEN Compliance for Crypto-Accepting Platforms

example.com is a payment facilitator accepting convertible
virtual currency (CVC). FinCEN guidance (FIN-2019-G001)
classifies us as a Money Services Business (MSB) when we:

1. Accept crypto from users and convert to fiat on their behalf.
2. Transfer value from user to creator.

Obligations:
- Register as MSB with FinCEN (fincen.gov/msb-registrant-search).
- Implement AML/BSA program: CIP for transactions > $3,000;
  SAR filing for suspicious activity > $2,000; CTR for cash
  > $10,000 (crypto equivalent at time of transaction).
- Retain transaction records for 5 years.
- Do not accept crypto from OFAC-sanctioned addresses;
  screen `pay_address` origin against Chainalysis or TRM Labs
  before crediting creator.

```typescript
// Minimal OFAC screen before crediting
async function screenAddress(address: string): Promise<boolean> {
  // POST to TRM Labs /v2/screening/addresses
  const resp = await fetch(env.TRM_ENDPOINT, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.TRM_API_KEY}` },
    body: JSON.stringify({ address }),
  });
  const { risk } = await resp.json<{ risk: string }>();
  return risk !== "HIGH"; // block HIGH-risk addresses
}
```

## Anti-patterns

- Granting access on `confirmed` status — the funds may not
  settle; use `finished` only.
- Skipping key-sorting before HMAC verification — the computed
  MAC will never match; all webhooks silently fail.
- Using `payment_id` alone as the idempotency key — NOWPayments
  sends multiple events with the same `payment_id` but
  different `payment_status` values; key on both.
- Auto-accepting partial payments without a threshold check —
  creates an underpayment loss that the platform absorbs.

## Gotchas

- `actually_paid` in the IPN payload is in crypto units, not
  USD. Compare to `pay_amount` (also crypto units) — do not
  compare to `price_amount` (USD).
- NOWPayments test mode uses a separate API key
  (`x-api-key: sandbox_...`); the IPN signature secret is also
  different in sandbox. Store both in Workers Secrets.
- The `expiration_estimate_date` is an estimate, not a
  guarantee. Actual lock expiry can be ± 5 minutes depending
  on network congestion.
- SOL and SPL tokens on Solana settle faster (< 1 s finality)
  than BTC (1 conf ≈ 10 min). `confirming` → `confirmed`
  timing varies wildly by currency.

## Verification

```bash
# Check D1 idempotency log for recent payments
wrangler d1 execute wam-db \
  --command "SELECT payment_id, status, received_at
             FROM crypto_ipn_log ORDER BY received_at
             DESC LIMIT 20"

# Replay a test IPN (sign manually)
curl -X POST https://api.example.com/webhooks/nowpayments \
  -H "x-nowpayments-sig: <computed_hmac>" \
  -H "Content-Type: application/json" \
  -d '{"payment_id":"test_001","payment_status":"finished",
       "actually_paid":0.001,"pay_amount":0.001,
       "order_id":"ord_test_001"}'
```

Expected: HTTP 200 and a corresponding row in `crypto_ipn_log`
with `status = finished`; `orders` table row updated to `paid`.

## Related

- `pci-dss-scope-reduction-tokenization.md`
- `stripe-connect-marketplace-platform-payments.md`
- `payment-fraud-detection-velocity-checks.md`

## Source URLs (verified 2026-08-17)

- https://nowpayments.io/docs/api
- https://nowpayments.io/docs/ipn-webhooks
- https://www.fincen.gov/resources/statutes-regulations/guidance/fin-2019-g001
- https://developers.cloudflare.com/d1/
- https://www.chainalysis.com/free-cryptocurrency-sanctions-screening-tools/
