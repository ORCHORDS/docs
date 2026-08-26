# Payment Fraud Detection — Velocity Checks

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Card-testing attacks exhaust Stripe authorization attempts,
spike decline rates, or generate fraudulent charges on the
platform before Radar catches them. New accounts created with
stolen cards produce chargebacks that exceed the 1 % Stripe
threshold.

## Context

example.com is an anonymous 21+ social platform. Anonymity lowers
friction for legitimate users but also for bad actors. Our first
line of defence is Cloudflare Workers (rate limiting via KV
sliding windows) before the Stripe API is ever called. Stripe
Radar is the second layer. 3DS2 step-up is the third.

## 1. Velocity Rule Patterns

Define limits for the three most abused vectors:

```
┌─────────────────────────────┬──────────┬────────────────┐
│ Signal                      │ Window   │ Hard limit     │
├─────────────────────────────┼──────────┼────────────────┤
│ Payment attempts / IP       │ 1 hour   │ 5              │
│ Distinct cards / device fp  │ 24 hours │ 3              │
│ Failed charges / customer   │ 1 hour   │ 3              │
│ New accounts / IP / CIDR24  │ 1 hour   │ 3              │
│ Subscription upgrades / acc │ 24 hours │ 2              │
└─────────────────────────────┴──────────┴────────────────┘
```

Exceeding a limit returns HTTP 429 with `Retry-After` header.
Never reveal which signal triggered the block.

## 2. Cloudflare Workers KV Sliding Window Counter

```typescript
// workers/src/fraud/velocity.ts
const WINDOW_MS = 60 * 60 * 1000; // 1 hour

export async function checkVelocity(
  kv: KVNamespace,
  key: string,
  limit: number,
): Promise<{ allowed: boolean; count: number }> {
  const now = Date.now();
  const windowStart = now - WINDOW_MS;
  const kvKey = `vel:${key}`;

  const raw = await kv.get(kvKey, { type: "json" }) as
    | number[]
    | null;
  const timestamps: number[] = raw ?? [];

  // drop entries outside the window (sliding)
  const active = timestamps.filter((t) => t > windowStart);

  if (active.length >= limit) {
    return { allowed: false, count: active.length };
  }

  active.push(now);
  // TTL = window + 60 s buffer
  await kv.put(kvKey, JSON.stringify(active), {
    expirationTtl: Math.ceil(WINDOW_MS / 1000) + 60,
  });
  return { allowed: true, count: active.length };
}

// Usage in payment handler
const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
const { allowed } = await checkVelocity(
  env.FRAUD_KV,
  `ip:${ip}`,
  5,
);
if (!allowed) {
  return new Response("Too many attempts", { status: 429,
    headers: { "Retry-After": "3600" } });
}
```

KV writes are eventually consistent; for < 10 ms races accept
occasional double-increments — the limit acts as a soft cap,
not a cryptographic guarantee.

## 3. Stripe Radar Rules

Custom Radar rules fire in the Stripe layer, independent of our
Workers logic. Rules are evaluated top-to-bottom; first match
wins.

```
# Block cards issued in high-fraud countries not served by WAM
block if :card_country: in ('NG', 'PK', 'BD', 'VN')
  and :risk_score: > 75

# Block anonymous prepaid cards for subscription upgrades
block if :card_funding: = 'prepaid'
  and :metadata:plan_tier: = 'premium'

# Review when IP country != card country
review if :ip_country: != :card_country:
  and :risk_score: > 50

# Block if more than 2 cards used on same email in 24 h
block if :cards_on_customer: > 2

# 3DS step-up for medium risk
request_three_d_secure if :risk_score: > 65
```

Export the rule set from the Stripe Dashboard and commit to
`config/radar-rules.txt`. Apply via Terraform or the Dashboard
UI; there is no public Radar rules API yet.

## 4. 3DS2 Step-Up on Risk Threshold

Force 3DS2 for charges above $50 or risk_score > 65 by setting
`payment_method_options.card.request_three_d_secure`.

```typescript
const pi = await stripe.paymentIntents.create({
  amount,
  currency: "usd",
  customer: customerId,
  payment_method: paymentMethodId,
  payment_method_options: {
    card: {
      request_three_d_secure:
        riskScore > 65 || amount > 5000 ? "any" : "automatic",
    },
  },
});
```

`"any"` forces 3DS even when the issuer would skip it. If the
issuer does not support 3DS the charge proceeds without it —
liability still shifts to the issuer for enrolled cards.

When `pi.status === "requires_action"` the client must call
`stripe.handleNextAction()`. Ensure the mobile SDK handles this
before marking the subscription active in D1.

## 5. Device Fingerprinting

Combine signals available in a Cloudflare Worker to build a
lightweight fingerprint without client-side JS:

```typescript
export function deviceFingerprint(req: Request): string {
  const cfIp = req.headers.get("CF-Connecting-IP") ?? "";
  const country = req.headers.get("CF-IPCountry") ?? "";
  const ua = req.headers.get("User-Agent") ?? "";
  const accept = req.headers.get("Accept-Language") ?? "";
  // CIDR /24 bucket to group mobile NATs
  const ipBucket = cfIp.split(".").slice(0, 3).join(".");
  const raw = `${ipBucket}|${country}|${ua}|${accept}`;
  // Use SubtleCrypto for hashing inside Worker
  return raw; // caller digests with SHA-256
}
```

For web clients, collect a canvas fingerprint in the frontend
(using FingerprintJS OSS) and pass as `metadata.device_fp` on
the PaymentIntent. Radar can reference `metadata` fields in
custom rules.

## 6. Manual Review Queue

When a charge enters Stripe Radar review or our own rules flag
it, write a row to D1 `fraud_review_queue`:

```sql
CREATE TABLE IF NOT EXISTS fraud_review_queue (
  id          TEXT PRIMARY KEY,
  pi_id       TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  amount      INTEGER NOT NULL,
  currency    TEXT NOT NULL,
  risk_score  INTEGER,
  flag_reason TEXT,
  status      TEXT DEFAULT 'pending', -- pending|approved|declined
  created_at  INTEGER NOT NULL,
  reviewed_at INTEGER,
  reviewer    TEXT
);
```

A Cloudflare Queues consumer polls every 5 minutes. Charges
held in review for > 48 h are auto-declined and refunded.

## Anti-patterns

- Blocking by `CF-Connecting-IP` alone — Tor exit nodes and
  residential proxies rotate IPs; device fingerprint + IP
  together is far more effective.
- Calling the Stripe Customers API inside the velocity check
  — adds 80–120 ms latency; cache customer metadata in KV.
- Setting `request_three_d_secure: "any"` globally — conversion
  drops 8–12 % for low-risk users; gate on risk score.
- Storing raw timestamps as a stringified array in KV for
  windows > 24 h — switch to a sorted-set approach via
  Durable Objects for long windows.

## Gotchas

- Radar custom rules require the `Radar for Fraud Teams` add-on
  ($0.05 per authorization); standard Radar rules are free.
- `cf-ipcountry` returns `XX` for Tor and `T1` for Cloudflare's
  own IPs; guard against these sentinel values.
- KV `get` with `type: "json"` returns `null` on a cache miss,
  not an empty array — always default to `[]`.
- Stripe `risk_score` is only available on the `Charge` object
  after authorization, not on the `PaymentIntent` during
  creation. Fetch `charge.outcome.risk_score` in the
  `charge.succeeded` webhook.

## Verification

```bash
# Check KV velocity counter for a given IP
wrangler kv key get --binding FRAUD_KV "vel:ip:1.2.3.4"

# Query D1 review queue
wrangler d1 execute wam-db \
  --command "SELECT status, COUNT(*) FROM fraud_review_queue
             GROUP BY status"
```

Run a card-testing simulation using Stripe's test card
`4000000000000341` (always blocked by Radar) and confirm
a 429 is returned before the Stripe API is hit.

## Related

- `stripe-connect-marketplace-platform-payments.md`
- `pci-dss-scope-reduction-tokenization.md`
- `subscription-billing-lifecycle-management.md`

## Source URLs (verified 2026-08-17)

- https://stripe.com/docs/radar/rules
- https://stripe.com/docs/payments/3d-secure
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/runtime-apis/request/
- https://stripe.com/docs/disputes/prevention/card-testing
