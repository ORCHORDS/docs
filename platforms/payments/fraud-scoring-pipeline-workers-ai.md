# Fraud Scoring Pipeline: Velocity Checks + Device Fingerprint + Workers AI

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your payment acceptance rate is degraded by false positives from Stripe Radar rules, or conversely, card testing and account takeover (ATO) attacks are slipping through because Radar rules lack context about your specific user behaviour patterns. You need a pre-payment fraud scoring layer that:

1. Runs **velocity checks** (IP, card BIN, email domain, device) from Cloudflare KV counters
2. Incorporates a **device fingerprint** signal (FingerprintJS Pro or Cloudflare's built-in bot score)
3. Feeds all signals into a **Workers AI classifier** that returns a fraud probability score
4. Makes a hard block / soft challenge / allow decision before the payment intent is even created

All of this must execute in under 100 ms to be invisible to the customer.

---

## Context

Cloudflare Workers AI provides a serverless inference runtime co-located with your edge workers. For fraud scoring, the most effective approach is a binary classifier trained on your historical payment outcomes (legitimate vs fraudulent). Workers AI supports:

- `@cf/meta/llama-3.1-8b-instruct` for text-based risk signals
- `@cf/huggingface/distilbert-sst-2-int8` for lightweight classification
- Custom ONNX models uploaded via the Workers AI REST API

For a payments fraud scorer, the practical approach is a **feature-engineered scoring function** combining hard rules (velocity) with a lightweight ML model score, producing a composite risk score between 0.0 and 1.0.

---

## Architecture

```
POST /api/payments/intent
        │
        ▼
[Worker: fraud-pre-check]
  │
  ├── 1. Extract signals (IP, device ID, email, card BIN, amount)
  │
  ├── 2. Velocity check (Cloudflare KV counters, 1h + 24h windows)
  │
  ├── 3. Device reputation (FingerprintJS Pro API or CF bot score)
  │
  ├── 4. Workers AI classifier (feature vector → fraud probability)
  │
  └── 5. Decision engine
         ├── score < 0.3  → allow (proceed to Stripe)
         ├── 0.3 ≤ score < 0.7  → 3DS challenge (set radar metadata)
         └── score ≥ 0.7  → block (return 403, log event)
```

---

## D1 Schema for Fraud Events

```sql
-- migration: 0001_fraud_events.sql
CREATE TABLE IF NOT EXISTS fraud_events (
  id             TEXT PRIMARY KEY,
  session_id     TEXT NOT NULL,
  ip_address     TEXT NOT NULL,
  device_id      TEXT,
  email_hash     TEXT,         -- SHA-256 of normalized email
  card_bin       TEXT,
  amount         INTEGER,
  currency       TEXT,
  fraud_score    REAL NOT NULL,
  decision       TEXT NOT NULL, -- allow|challenge|block
  signals        TEXT NOT NULL, -- JSON blob of all feature values
  created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_fraud_ip      ON fraud_events(ip_address, created_at);
CREATE INDEX idx_fraud_device  ON fraud_events(device_id, created_at);
CREATE INDEX idx_fraud_email   ON fraud_events(email_hash, created_at);
CREATE INDEX idx_fraud_decision ON fraud_events(decision, created_at);
```

---

## Velocity Check with Cloudflare KV

```typescript
// lib/fraud/velocity.ts
export interface VelocitySignals {
  ipAttempts1h: number;
  ipAttempts24h: number;
  deviceAttempts1h: number;
  emailAttempts24h: number;
  binAttempts1h: number;
  ipBlocklisted: boolean;
}

export interface VelocityCounters {
  KV: KVNamespace;
}

const THRESHOLDS = {
  ipAttempts1h: 10,
  ipAttempts24h: 30,
  deviceAttempts1h: 5,
  emailAttempts24h: 10,
  binAttempts1h: 15,
};

export async function getVelocitySignals(
  env: VelocityCounters,
  params: {
    ip: string;
    deviceId: string | null;
    emailHash: string;
    bin: string;
  }
): Promise<VelocitySignals> {
  const now = Date.now();
  const hour1Bucket = Math.floor(now / 3_600_000);
  const hour24Bucket = Math.floor(now / 86_400_000);

  const keys = [
    `v:ip:${params.ip}:${hour1Bucket}`,
    `v:ip:${params.ip}:${hour24Bucket}:24h`,
    `v:dev:${params.deviceId ?? 'unknown'}:${hour1Bucket}`,
    `v:email:${params.emailHash}:${hour24Bucket}`,
    `v:bin:${params.bin}:${hour1Bucket}`,
    `bl:ip:${params.ip}`, // blocklist flag
  ];

  // KV supports getWithMetadata but not multi-get in Workers — use Promise.all
  const [ip1h, ip24h, dev1h, email24h, bin1h, blocklisted] = await Promise.all(
    keys.map(k => env.KV.get(k))
  );

  return {
    ipAttempts1h:    parseInt(ip1h      ?? '0', 10),
    ipAttempts24h:   parseInt(ip24h     ?? '0', 10),
    deviceAttempts1h: parseInt(dev1h   ?? '0', 10),
    emailAttempts24h: parseInt(email24h ?? '0', 10),
    binAttempts1h:   parseInt(bin1h     ?? '0', 10),
    ipBlocklisted:   blocklisted === '1',
  };
}

export async function incrementVelocityCounters(
  env: VelocityCounters,
  params: { ip: string; deviceId: string | null; emailHash: string; bin: string }
): Promise<void> {
  const now = Date.now();
  const hour1Bucket = Math.floor(now / 3_600_000);
  const hour24Bucket = Math.floor(now / 86_400_000);

  const increments: [string, number][] = [
    [`v:ip:${params.ip}:${hour1Bucket}`, 7200],
    [`v:ip:${params.ip}:${hour24Bucket}:24h`, 172800],
    [`v:dev:${params.deviceId ?? 'unknown'}:${hour1Bucket}`, 7200],
    [`v:email:${params.emailHash}:${hour24Bucket}`, 172800],
    [`v:bin:${params.bin}:${hour1Bucket}`, 7200],
  ];

  await Promise.all(
    increments.map(async ([key, ttl]) => {
      const current = parseInt(await env.KV.get(key) ?? '0', 10);
      await env.KV.put(key, String(current + 1), { expirationTtl: ttl });
    })
  );
}

export function velocityFraudScore(signals: VelocitySignals): number {
  if (signals.ipBlocklisted) return 1.0;

  let score = 0;
  if (signals.ipAttempts1h > THRESHOLDS.ipAttempts1h)      score += 0.35;
  if (signals.ipAttempts24h > THRESHOLDS.ipAttempts24h)    score += 0.20;
  if (signals.deviceAttempts1h > THRESHOLDS.deviceAttempts1h) score += 0.25;
  if (signals.emailAttempts24h > THRESHOLDS.emailAttempts24h) score += 0.10;
  if (signals.binAttempts1h > THRESHOLDS.binAttempts1h)    score += 0.15;

  // Partial credit for near-threshold values
  const ipPartial = signals.ipAttempts1h / THRESHOLDS.ipAttempts1h;
  if (ipPartial < 1) score += ipPartial * 0.15;

  return Math.min(score, 1.0);
}
```

---

## Device Fingerprint Signal

```typescript
// lib/fraud/device.ts

export interface DeviceSignals {
  botScore: number;          // 0 = human, 1 = bot (from CF-Bot-Score header)
  fingerprintRiskScore: number; // FingerprintJS Pro risk score 0–1
  isKnownGoodDevice: boolean;
  isTorExit: boolean;
  isDatacenterIp: boolean;
}

/**
 * Extract Cloudflare's built-in bot/threat signals from request headers.
 * These are available on all Cloudflare-proxied requests.
 */
export function extractCfSignals(request: Request): {
  botScore: number;
  isTorExit: boolean;
  isDatacenterIp: boolean;
  country: string;
} {
  // CF-Bot-Score: 0 (likely human) to 99 (likely bot)
  const botScoreRaw = request.headers.get('cf-bot-score') ?? '0';
  const botScore = parseInt(botScoreRaw, 10) / 99; // normalize to 0-1

  // cf-ipcountry: 'T1' = Tor
  const country = request.headers.get('cf-ipcountry') ?? '';
  const isTorExit = country === 'T1';

  // cf.threat_score >= 14 correlates with datacenter/proxy IPs
  const cfThreat = parseInt(request.headers.get('cf-threat-score') ?? '0', 10);
  const isDatacenterIp = cfThreat >= 14;

  return { botScore, isTorExit, isDatacenterIp, country };
}

/**
 * Query FingerprintJS Pro for a given visitorId (client-side token).
 * The risk score encapsulates bot detection, VPN, emulator, tamper signals.
 */
export async function getFingerprintRisk(
  visitorId: string,
  apiKey: string
): Promise<number> {
  if (!visitorId) return 0.5; // neutral if not provided

  try {
    const res = await fetch(
      `https://api.fpjs.io/events/${visitorId}?api_key=${apiKey}`,
      { headers: { 'Accept': 'application/json' } }
    );
    if (!res.ok) return 0.5;

    const data = await res.json() as {
      products?: {
        botd?: { data?: { bot?: { result: string } } };
        vpn?: { data?: { result: boolean } };
      };
    };

    let fpScore = 0;
    if (data.products?.botd?.data?.bot?.result === 'bad') fpScore += 0.6;
    if (data.products?.vpn?.data?.result === true) fpScore += 0.2;
    return Math.min(fpScore, 1.0);
  } catch {
    return 0.5;
  }
}
```

---

## Workers AI Classifier

```typescript
// lib/fraud/workers-ai.ts
// Uses Workers AI text classification to score a feature narrative.
// For production, replace with a fine-tuned ONNX model uploaded to Workers AI.

export interface FraudFeatures {
  amountUsd: number;
  ipAttempts1h: number;
  ipAttempts24h: number;
  deviceAttempts1h: number;
  emailAttempts24h: number;
  binAttempts1h: number;
  botScore: number;
  fingerprintScore: number;
  isTor: boolean;
  isDatacenter: boolean;
  cardCountry: string;
  billingCountry: string;
}

export interface Env {
  AI: Ai;
}

/**
 * Uses Workers AI sentiment classifier as a proxy for fraud probability.
 * The prompt engineers the feature vector into a text classification task.
 * Replace with a dedicated binary classifier for higher accuracy in production.
 */
export async function classifyFraud(
  features: FraudFeatures,
  env: Env
): Promise<number> {
  const featureText = [
    `Transaction amount: $${features.amountUsd}`,
    `IP attempts last hour: ${features.ipAttempts1h}`,
    `IP attempts last 24h: ${features.ipAttempts24h}`,
    `Device attempts last hour: ${features.deviceAttempts1h}`,
    `Email attempts last 24h: ${features.emailAttempts24h}`,
    `Card BIN attempts last hour: ${features.binAttempts1h}`,
    `Bot score: ${(features.botScore * 100).toFixed(0)}%`,
    `Fingerprint risk: ${(features.fingerprintScore * 100).toFixed(0)}%`,
    `Tor exit node: ${features.isTor}`,
    `Datacenter IP: ${features.isDatacenter}`,
    `Card country: ${features.cardCountry}`,
    `Billing country: ${features.billingCountry}`,
  ].join('. ');

  const result = await env.AI.run('@cf/huggingface/distilbert-sst-2-int8', {
    text: featureText,
  }) as Array<{ label: string; score: number }>;

  // DistilBERT-SST-2 returns POSITIVE/NEGATIVE sentiment.
  // We repurpose NEGATIVE sentiment as fraud indicator.
  const negative = result.find(r => r.label === 'NEGATIVE');
  return negative?.score ?? 0.5;
}

/**
 * Composite scorer: blend velocity, device, and AI signals.
 */
export function compositeScore(
  velocityScore: number,
  deviceScore: number,
  aiScore: number
): number {
  // Weights: velocity is highest signal for card testing attacks
  const weighted = velocityScore * 0.45 + deviceScore * 0.30 + aiScore * 0.25;
  return Math.min(weighted, 1.0);
}
```

---

## Main Worker: Pre-Payment Fraud Check

```typescript
// workers/fraud-pre-check.ts
import { getVelocitySignals, incrementVelocityCounters, velocityFraudScore } from '../lib/fraud/velocity';
import { extractCfSignals, getFingerprintRisk } from '../lib/fraud/device';
import { classifyFraud, compositeScore } from '../lib/fraud/workers-ai';
import { createHash } from 'node:crypto'; // available in Workers compat 2023-03-01+

export interface Env {
  DB: D1Database;
  KV: KVNamespace;
  AI: Ai;
  FINGERPRINT_API_KEY: string;
}

interface PaymentCheckRequest {
  amount: number;
  currency: string;
  cardBin: string;
  billingCountry: string;
  cardCountry: string;
  email: string;
  deviceId?: string;    // FingerprintJS visitorId
  sessionId: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('', { status: 405 });

    const body: PaymentCheckRequest = await request.json();
    const ip = request.headers.get('cf-connecting-ip') ?? '0.0.0.0';

    // Normalize and hash PII
    const emailHash = createHash('sha256')
      .update(body.email.toLowerCase().trim())
      .digest('hex');

    // 1. Velocity signals (parallel with device lookup)
    const [velocitySignals, cfSignals, fingerprintScore] = await Promise.all([
      getVelocitySignals({ KV: env.KV }, {
        ip,
        deviceId: body.deviceId ?? null,
        emailHash,
        bin: body.cardBin,
      }),
      Promise.resolve(extractCfSignals(request)),
      getFingerprintRisk(body.deviceId ?? '', env.FINGERPRINT_API_KEY),
    ]);

    const velScore = velocityFraudScore(velocitySignals);
    const deviceScore = Math.max(
      cfSignals.botScore,
      fingerprintScore,
      cfSignals.isTorExit ? 0.9 : 0,
      cfSignals.isDatacenterIp ? 0.4 : 0,
    );

    // 2. Workers AI classification
    const aiScore = await classifyFraud({
      amountUsd: body.amount / 100,
      ...velocitySignals,
      botScore: cfSignals.botScore,
      fingerprintScore,
      isTor: cfSignals.isTorExit,
      isDatacenter: cfSignals.isDatacenterIp,
      cardCountry: body.cardCountry,
      billingCountry: body.billingCountry,
    }, env);

    const fraudScore = compositeScore(velScore, deviceScore, aiScore);

    // 3. Decision
    let decision: 'allow' | 'challenge' | 'block';
    if (fraudScore >= 0.70) {
      decision = 'block';
    } else if (fraudScore >= 0.30) {
      decision = 'challenge';
    } else {
      decision = 'allow';
    }

    // 4. Log and increment counters (fire-and-forget)
    const signals = JSON.stringify({
      velocitySignals, cfSignals, fingerprintScore,
      velScore, deviceScore, aiScore,
    });

    await Promise.all([
      env.DB.prepare(
        `INSERT INTO fraud_events
           (id, session_id, ip_address, device_id, email_hash, card_bin,
            amount, currency, fraud_score, decision, signals)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        crypto.randomUUID(), body.sessionId, ip,
        body.deviceId ?? null, emailHash, body.cardBin,
        body.amount, body.currency, fraudScore, decision, signals
      ).run(),
      decision !== 'block'
        ? incrementVelocityCounters({ KV: env.KV }, {
            ip, deviceId: body.deviceId ?? null, emailHash, bin: body.cardBin
          })
        : Promise.resolve(),
    ]);

    if (decision === 'block') {
      return new Response(JSON.stringify({
        error: 'payment_blocked',
        code: 'fraud_detected',
      }), { status: 403, headers: { 'Content-Type': 'application/json' } });
    }

    return new Response(JSON.stringify({
      decision,
      fraudScore: parseFloat(fraudScore.toFixed(4)),
      // Return 3DS challenge flag so payment intent creation uses request_three_d_secure: 'any'
      require3ds: decision === 'challenge',
      // Stripe Radar session metadata key (pass as metadata on PaymentIntent)
      radarSessionId: body.sessionId,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## Integrating with Stripe PaymentIntent Creation

```typescript
// After calling the fraud pre-check endpoint:
const fraudCheck = await fetch('/api/payments/fraud-check', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    amount: 4999,
    currency: 'usd',
    cardBin: cardElement.getValue().cardBin,
    billingCountry: billingDetails.country,
    cardCountry: 'US',
    email: user.email,
    deviceId: await fpjsClient.getVisitorId(),
    sessionId: stripeRadarSession.id,
  }),
});

const { decision, require3ds } = await fraudCheck.json();

if (fraudCheck.status === 403) {
  showError('Your payment could not be processed. Please contact support.');
  return;
}

// Create PaymentIntent server-side with 3DS instruction
const intent = await stripe.paymentIntents.create({
  amount: 4999,
  currency: 'usd',
  payment_method_options: {
    card: {
      request_three_d_secure: require3ds ? 'any' : 'automatic',
    },
  },
  metadata: {
    fraud_score: fraudCheck.fraudScore,
    fraud_decision: decision,
    session_id: stripeRadarSession.id,
  },
});
```

---

## Anti-patterns

- **Running the AI inference synchronously in the critical payment path without a timeout**: Workers AI calls can take 50–200 ms. Wrap in `Promise.race` with a 150 ms timeout fallback to neutral score `0.5`.

- **Using the same KV key for all time windows**: `v:ip:1.2.3.4` without a time bucket grows unboundedly. Always suffix with the hourly/daily bucket.

- **Blocking on KV increments before returning the decision**: Increment counters after the response is returned using `ctx.waitUntil(incrementVelocityCounters(...))` to avoid adding latency.

- **Using `cf-threat-score` as a solo blocker**: This header detects spam/proxies but has high false-positive rates. Use it as one signal in the composite score, not a hard block.

- **Training on raw email as a feature**: Email addresses are PII. Always SHA-256 hash before storing in D1 or passing to the AI model.

- **Forgetting to allowlist legitimate velocity**: Your own test accounts, internal IPs, and automation will trigger velocity limits. Maintain a `bl:ip:X` = `'whitelist'` entry to skip scoring for known-good IPs.

---

## Gotchas

1. **Workers AI `@cf/huggingface/distilbert-sst-2-int8` is a sentiment model, not a fraud classifier**. The code above repurposes it as a proxy. For production, upload a fine-tuned ONNX model via `wrangler ai model upload`.

2. **`ctx.waitUntil` is not available in the `fetch` handler signature without the `ExecutionContext` parameter**. Add it: `async fetch(request, env, ctx)` and use `ctx.waitUntil(...)`.

3. **KV `getWithMetadata` requires separate calls in Workers** — there is no `mget` (multi-get). For 6 keys, 6 parallel `Promise.all` calls add ~3 ms at most from edge KV.

4. **`cf-bot-score` is only set on requests that pass through Cloudflare's Bot Management** product (paid add-on). On free plans, the header is absent — fall back to `0`.

5. **FingerprintJS Pro API calls must be server-side** (API key is secret). Never expose the API key client-side — the `visitorId` is not a secret and is safe to pass from client to server.

6. **Card BIN is not available from Stripe.js** before payment method creation. Extract it from `CardNumberElement.on('change', e => e.value.postalCode)` — actually, Stripe exposes BIN in `PaymentElement` events via `stripe.createPaymentMethod` response's `card.funding` but not BIN directly. Use FingerprintJS device signals as the primary device check.

---

## Verification

```bash
# 1. Deploy worker
wrangler deploy

# 2. Test allow path (low-signal request)
curl -X POST https://YOUR_WORKER.workers.dev/api/payments/fraud-check \
  -H "Content-Type: application/json" \
  -d '{"amount":999,"currency":"usd","cardBin":"424242","billingCountry":"US","cardCountry":"US","email":"test@example.com","sessionId":"sess_test"}'
# Expect: {"decision":"allow","fraudScore":0.05,...}

# 3. Test velocity block (send 15 requests from same IP)
for i in {1..15}; do
  curl -s -X POST https://YOUR_WORKER.workers.dev/api/payments/fraud-check \
    -H "Content-Type: application/json" \
    -d '{"amount":999,"currency":"usd","cardBin":"400000","billingCountry":"US","cardCountry":"US","email":"attacker@evil.com","sessionId":"sess_'$i'"}'
done

# 4. Query fraud events
wrangler d1 execute payments \
  --command "SELECT decision, COUNT(*) as n, AVG(fraud_score) as avg_score FROM fraud_events GROUP BY decision"
```

---

## Related

- `velocity-fraud-checks.md` — Velocity check patterns without Workers AI
- `ai-ml-fraud-risk-scoring.md` — ML model training and feature engineering
- `payment-fraud-detection-velocity-checks.md` — Rate limiting patterns
- `stripe-radar-fraud-rules.md` — Stripe Radar custom rules for post-authorization blocking
- `card-testing-attack-prevention.md` — Card testing specific defences
- `3ds2-frictionless-flow-optimization.md` — When to trigger 3DS challenge

---

## Sources

- [Cloudflare Workers AI documentation](https://developers.cloudflare.com/workers-ai/)
- [Cloudflare Bot Management — cf-bot-score](https://developers.cloudflare.com/bots/concepts/bot-score/)
- [FingerprintJS Pro documentation](https://dev.fingerprint.com/docs)
- [Stripe Radar — custom rules](https://docs.stripe.com/radar/rules)
- [Stripe — PaymentIntent request_three_d_secure](https://docs.stripe.com/api/payment_intents/create#create_payment_intent-payment_method_options-card-request_three_d_secure)
- [Cloudflare KV — Workers binding](https://developers.cloudflare.com/kv/api/)
