# Payment Fraud Detection in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You process payments globally and see card-testing attacks, carding bots, and account-takeover attempts. Stripe alone cannot block fast enough — you need an edge-side fraud gate that runs before any charge is attempted, scores each transaction in milliseconds, and logs signals for offline ML training.

---

## Context

Cloudflare Workers sit in front of your payment API. KV stores rolling velocity counters (no cold-start latency). D1 persists fraud signal rows for periodic model training. The risk scorer is a weighted composite: velocity abuse contributes ~40 %, BIN/geo mismatch ~30 %, device fingerprint anomalies ~20 %, historical account behaviour ~10 %.

All checks run in parallel using `Promise.all` to keep median latency under 8 ms.

---

## Solution

```typescript
// workers-payment-fraud-detection/src/index.ts

import { Env } from './types';
import { velocityCheck, VelocityResult } from './velocity';
import { binLookup, BinResult } from './bin';
import { deviceAnomalyScore } from './device';
import { logFraudSignal } from './db';

export interface FraudRequest {
  cardBin: string;           // first 6-8 digits
  cardFingerprint: string;   // Stripe pm fingerprint
  billingCountry: string;    // ISO 3166-1 alpha-2
  billingZip: string;
  amountCents: number;
  currency: string;
  customerId: string;
  deviceId: string;          // fingerprint from client SDK
  ipAddress: string;
  userAgent: string;
}

export interface FraudResult {
  allowed: boolean;
  riskScore: number;         // 0-100
  signals: string[];
  requestId: string;
}

// ── Weights ──────────────────────────────────────────────────────────────────
const W = {
  velocityCard: 0.20,
  velocityIp: 0.12,
  velocityDevice: 0.08,
  binMismatch: 0.20,
  binHighRiskCountry: 0.10,
  deviceAnomaly: 0.20,
  highAmount: 0.10,
};

// ── Worker Entry ─────────────────────────────────────────────────────────────
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    let body: FraudRequest;
    try {
      body = await request.json<FraudRequest>();
    } catch {
      return new Response('Bad Request', { status: 400 });
    }

    const requestId = crypto.randomUUID();
    const result = await evaluate(body, env, requestId);

    // Fire-and-forget: persist fraud signals to D1 for ML pipeline
    ctx.waitUntil(logFraudSignal(env.DB, { requestId, input: body, result }));

    return Response.json(result, {
      status: result.allowed ? 200 : 402,
    });
  },
};

// ── Main Evaluator ────────────────────────────────────────────────────────────
async function evaluate(
  req: FraudRequest,
  env: Env,
  requestId: string,
): Promise<FraudResult> {
  const signals: string[] = [];
  let rawScore = 0;

  // Run all checks in parallel
  const [velCard, velIp, velDevice, bin, deviceScore] = await Promise.all([
    velocityCheck(env.KV, `card:${req.cardFingerprint}`, 10, 300),   // 10 hits / 5 min
    velocityCheck(env.KV, `ip:${req.ipAddress}`, 20, 300),           // 20 hits / 5 min
    velocityCheck(env.KV, `dev:${req.deviceId}`, 15, 300),           // 15 hits / 5 min
    binLookup(env.KV, req.cardBin),
    deviceAnomalyScore(env.KV, req.deviceId, req.userAgent),
  ]);

  // ── Velocity signals ──────────────────────────────────────────────────────
  if (velCard.exceeded) {
    signals.push(`velocity:card:${velCard.count}`);
    rawScore += W.velocityCard * 100;
  }
  if (velIp.exceeded) {
    signals.push(`velocity:ip:${velIp.count}`);
    rawScore += W.velocityIp * 100;
  }
  if (velDevice.exceeded) {
    signals.push(`velocity:device:${velDevice.count}`);
    rawScore += W.velocityDevice * 100;
  }

  // ── BIN / geo signals ────────────────────────────────────────────────────
  if (bin && bin.countryCode && bin.countryCode !== req.billingCountry) {
    signals.push(`bin_country_mismatch:${bin.countryCode}!=${req.billingCountry}`);
    rawScore += W.binMismatch * 100;
  }
  if (bin?.highRisk) {
    signals.push(`bin_high_risk_country:${bin.countryCode}`);
    rawScore += W.binHighRiskCountry * 100;
  }

  // ── Device anomaly ───────────────────────────────────────────────────────
  if (deviceScore > 60) {
    signals.push(`device_anomaly:${deviceScore}`);
    rawScore += W.deviceAnomaly * (deviceScore / 100);
  }

  // ── High-value anomaly ───────────────────────────────────────────────────
  if (req.amountCents > 100_000) {  // > $1 000
    signals.push(`high_amount:${req.amountCents}`);
    rawScore += W.highAmount * 100;
  }

  const riskScore = Math.min(100, Math.round(rawScore));
  const allowed = riskScore < 70;

  return { allowed, riskScore, signals, requestId };
}
```

```typescript
// workers-payment-fraud-detection/src/velocity.ts

export interface VelocityResult {
  count: number;
  exceeded: boolean;
}

export async function velocityCheck(
  kv: KVNamespace,
  key: string,
  limit: number,
  windowSecs: number,
): Promise<VelocityResult> {
  const kvKey = `fraud:velocity:${key}`;
  const raw = await kv.get(kvKey);
  const count = raw ? parseInt(raw, 10) + 1 : 1;

  // Write-back; reset TTL each time (sliding window approximation)
  await kv.put(kvKey, String(count), { expirationTtl: windowSecs });

  return { count, exceeded: count > limit };
}
```

```typescript
// workers-payment-fraud-detection/src/bin.ts

export interface BinResult {
  countryCode: string;
  highRisk: boolean;
  brand: string;
  type: 'credit' | 'debit' | 'prepaid' | 'unknown';
}

// High-risk issuing countries per internal policy
const HIGH_RISK_COUNTRIES = new Set([
  'NG', 'RO', 'VN', 'PK', 'BD', 'GH',
]);

export async function binLookup(
  kv: KVNamespace,
  bin: string,
): Promise<BinResult | null> {
  const cached = await kv.get<BinResult>(`fraud:bin:${bin}`, 'json');
  if (cached) return cached;

  // In production: call internal BIN table in D1 or licensed BIN API.
  // Stub returns null (no penalty) when BIN is unknown.
  return null;
}

export function isHighRiskCountry(countryCode: string): boolean {
  return HIGH_RISK_COUNTRIES.has(countryCode.toUpperCase());
}
```

```typescript
// workers-payment-fraud-detection/src/device.ts

export async function deviceAnomalyScore(
  kv: KVNamespace,
  deviceId: string,
  userAgent: string,
): Promise<number> {
  const seenKey = `fraud:dev:ua:${deviceId}`;
  const previousUa = await kv.get(seenKey);

  let score = 0;

  if (!previousUa) {
    // First time we see this device — mild signal
    score += 15;
    await kv.put(seenKey, userAgent, { expirationTtl: 86_400 * 30 });
  } else if (previousUa !== userAgent) {
    // UA changed — moderate signal (could be bot rotating agents)
    score += 45;
    await kv.put(seenKey, userAgent, { expirationTtl: 86_400 * 30 });
  }

  // Headless / automation signals in UA
  if (/HeadlessChrome|PhantomJS|Selenium|Puppeteer/i.test(userAgent)) {
    score += 80;
  }

  return Math.min(100, score);
}
```

```typescript
// workers-payment-fraud-detection/src/db.ts

import { FraudRequest, FraudResult } from './index';

export async function logFraudSignal(
  db: D1Database,
  payload: { requestId: string; input: FraudRequest; result: FraudResult },
): Promise<void> {
  const { requestId, input, result } = payload;
  await db
    .prepare(
      `INSERT INTO fraud_signals
         (request_id, customer_id, ip_address, device_id, card_bin,
          billing_country, amount_cents, risk_score, signals, allowed, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`,
    )
    .bind(
      requestId,
      input.customerId,
      input.ipAddress,
      input.deviceId,
      input.cardBin,
      input.billingCountry,
      input.amountCents,
      result.riskScore,
      JSON.stringify(result.signals),
      result.allowed ? 1 : 0,
    )
    .run();
}
```

---

## Implementation Details

**KV layout** — all keys are prefixed with `fraud:` to isolate the namespace. Sliding-window TTL is reset on every hit, which slightly over-counts across window boundaries but keeps KV operations to a single write per check.

**BIN lookup** — production builds store a snapshot of BIN data in D1 (`bins` table, indexed on `bin_prefix`) and cache individual lookups in KV for 24 hours to avoid hot D1 queries.

**D1 schema**:
```sql
CREATE TABLE fraud_signals (
  request_id    TEXT PRIMARY KEY,
  customer_id   TEXT NOT NULL,
  ip_address    TEXT NOT NULL,
  device_id     TEXT NOT NULL,
  card_bin      TEXT NOT NULL,
  billing_country TEXT NOT NULL,
  amount_cents  INTEGER NOT NULL,
  risk_score    INTEGER NOT NULL,
  signals       TEXT NOT NULL,    -- JSON array
  allowed       INTEGER NOT NULL, -- 0/1
  created_at    TEXT NOT NULL
);
CREATE INDEX idx_fs_customer  ON fraud_signals (customer_id, created_at);
CREATE INDEX idx_fs_ip        ON fraud_signals (ip_address,  created_at);
CREATE INDEX idx_fs_device    ON fraud_signals (device_id,   created_at);
```

**`wrangler.toml` bindings required**:
```toml
[[kv_namespaces]]
binding = "KV"
id      = "<FRAUD_KV_ID>"

[[d1_databases]]
binding  = "DB"
database_name = "payments"
database_id   = "<D1_ID>"
```

---

## Anti-patterns

- **Do not block in `waitUntil`** — D1 writes must use `ctx.waitUntil`; blocking the response on them adds ~10-40 ms of latency for every transaction.
- **Do not use fixed-window counters** — they create burst holes at the window boundary; use the sliding-window TTL-reset approach above or a two-bucket Lua-style counter.
- **Do not hard-code country lists in code** — store them in KV under a versioned key and refresh via a Scheduled Worker so policy changes deploy without a code push.
- **Do not skip the device score when `deviceId` is absent** — treat a missing device ID as `score = 50` (unknown), not 0.

---

## Gotchas

- KV `expirationTtl` minimum is 60 seconds; use 300 s (5 min) as the smallest practical velocity window.
- `Promise.all` failures will throw if any sub-check rejects. Wrap individual checks in try/catch and default to score = 0 so a BIN API outage does not block all payments.
- Cloudflare's `request.headers.get('CF-Connecting-IP')` gives the true client IP behind the proxy; `req.ipAddress` should be populated from this header in the calling layer, not from an X-Forwarded-For chain.
- KV reads have eventual consistency; a card-testing burst from two PoPs simultaneously may under-count by one window cycle. Acceptable at the edge — the absolute block is applied server-side by Stripe rules.

---

## Verification

```bash
# Local dev with Wrangler
npx wrangler dev --local

curl -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -d '{
    "cardBin": "411111",
    "cardFingerprint": "fp_abc123",
    "billingCountry": "US",
    "billingZip": "10001",
    "amountCents": 5000,
    "currency": "usd",
    "customerId": "cus_test",
    "deviceId": "dev_xyz",
    "ipAddress": "1.2.3.4",
    "userAgent": "Mozilla/5.0"
  }'
# Expected: { allowed: true, riskScore: <70, signals: [] }

# Trigger velocity block: send 11 requests with same cardFingerprint in < 5 min
for i in $(seq 1 11); do curl -s -X POST http://localhost:8787 -H 'Content-Type: application/json' -d '{...}' | jq .riskScore; done
```

---

## Related

- `documentation/categories/payments/stripe-webhook-idempotency.md`
- `documentation/categories/payments/payment-retry-exponential-backoff.md`
- `documentation/categories/payments/workers-3ds-authentication-flow.md`
- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/

---

## Sources

- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- https://stripe.com/docs/radar/rules
- https://www.binlist.net/
- https://owasp.org/www-community/attacks/Card_Testing
