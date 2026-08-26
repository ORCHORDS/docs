# Payment Method ML Ranking with Workers AI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You want to dynamically rank and surface the most likely-to-convert payment method for each user at checkout — rather than showing a static ordered list — using a machine learning model running inside Cloudflare Workers AI, informed by past payment behavior stored in D1 and KV.

## Context

Payment method conversion rates vary significantly by user geography, device, purchase amount, time-of-day, and purchase history. A static ranked list (e.g., Card > PayPal > Apple Pay) leaves conversion on the table. Workers AI provides a serverless inference endpoint that runs ONNX or built-in `@cf/...` text classification / tabular models within the same Worker invocation. This article covers: feature extraction from D1, batch scoring with Workers AI, returning ranked methods to the checkout frontend, and storing feedback for model retraining.

---

## 1. Feature Engineering at Request Time

```typescript
// src/features.ts
interface Env {
  DB: D1Database;
}

export interface CheckoutFeatures {
  userId: string;
  cartAmountCents: number;
  countryCode: string;
  deviceType: 'mobile' | 'desktop' | 'tablet';
  hourOfDay: number;
  hasSavedCard: boolean;
  hasSavedPaypal: boolean;
  pastCardSuccessRate: number;
  pastPaypalSuccessRate: number;
  pastBnplSuccessRate: number;
  isFirstPurchase: boolean;
}

export async function extractFeatures(
  env: Env,
  userId: string,
  cartAmountCents: number,
  countryCode: string,
  deviceType: string
): Promise<CheckoutFeatures> {
  const history = await env.DB.prepare(
    `SELECT
       payment_method,
       COUNT(*) AS total,
       SUM(CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END) AS succeeded
     FROM payment_attempts
     WHERE user_id = ?
     GROUP BY payment_method`
  ).bind(userId).all<{
    payment_method: string;
    total: number;
    succeeded: number;
  }>();

  const rates: Record<string, number> = {};
  let totalAttempts = 0;
  for (const row of history.results) {
    rates[row.payment_method] = row.total > 0 ? row.succeeded / row.total : 0;
    totalAttempts += row.total;
  }

  const saved = await env.DB.prepare(
    'SELECT payment_method FROM saved_payment_methods WHERE user_id = ?'
  ).bind(userId).all<{ payment_method: string }>();
  const savedMethods = new Set(saved.results.map((r) => r.payment_method));

  return {
    userId,
    cartAmountCents,
    countryCode,
    deviceType: deviceType as CheckoutFeatures['deviceType'],
    hourOfDay: new Date().getUTCHours(),
    hasSavedCard: savedMethods.has('card'),
    hasSavedPaypal: savedMethods.has('paypal'),
    pastCardSuccessRate: rates['card'] ?? 0,
    pastPaypalSuccessRate: rates['paypal'] ?? 0,
    pastBnplSuccessRate: rates['klarna'] ?? 0,
    isFirstPurchase: totalAttempts === 0,
  };
}
```

---

## 2. Scoring Payment Methods with Workers AI Text Embeddings + Cosine Similarity

This approach uses `@cf/baai/bge-small-en-v1.5` to encode a feature string, then compares it against pre-computed "ideal buyer profile" embeddings per payment method stored in KV.

```typescript
// src/pm-ranker.ts
interface Env {
  AI: Ai;
  PM_EMBEDDINGS: KVNamespace; // pre-stored method profile embeddings
}

const PAYMENT_METHODS = ['card', 'paypal', 'klarna', 'apple_pay', 'bank_transfer'];

function featuresToText(f: CheckoutFeatures): string {
  return [
    `amount:${Math.floor(f.cartAmountCents / 100)}`,
    `country:${f.countryCode}`,
    `device:${f.deviceType}`,
    `hour:${f.hourOfDay}`,
    `saved_card:${f.hasSavedCard}`,
    `saved_paypal:${f.hasSavedPaypal}`,
    `card_rate:${f.pastCardSuccessRate.toFixed(2)}`,
    `paypal_rate:${f.pastPaypalSuccessRate.toFixed(2)}`,
    `bnpl_rate:${f.pastBnplSuccessRate.toFixed(2)}`,
    `first_purchase:${f.isFirstPurchase}`,
  ].join(' ');
}

function cosineSimilarity(a: number[], b: number[]): number {
  const dot = a.reduce((sum, v, i) => sum + v * b[i], 0);
  const magA = Math.sqrt(a.reduce((s, v) => s + v * v, 0));
  const magB = Math.sqrt(b.reduce((s, v) => s + v * v, 0));
  return magA && magB ? dot / (magA * magB) : 0;
}

export async function rankPaymentMethods(
  env: Env,
  features: CheckoutFeatures
): Promise<Array<{ method: string; score: number }>> {
  const featureText = featuresToText(features);

  const { data: [queryEmbedding] } = await env.AI.run(
    '@cf/baai/bge-small-en-v1.5',
    { text: [featureText] }
  ) as { data: number[][] };

  const scores: Array<{ method: string; score: number }> = [];

  for (const method of PAYMENT_METHODS) {
    const stored = await env.PM_EMBEDDINGS.get(
      `embedding:${method}`,
      { type: 'json' }
    ) as number[] | null;
    if (!stored) continue;
    scores.push({ method, score: cosineSimilarity(queryEmbedding, stored) });
  }

  return scores.sort((a, b) => b.score - a.score);
}
```

---

## 3. Pre-computing Method Profile Embeddings (Bootstrap Script)

```typescript
// scripts/seed-embeddings.ts  (run as a one-time Workers Script or local script)
// Represents the "ideal context" for each payment method

const METHOD_PROFILES: Record<string, string> = {
  card:
    'amount:high country:US device:desktop saved_card:true card_rate:0.95 first_purchase:false',
  paypal:
    'amount:medium country:US device:mobile saved_paypal:true paypal_rate:0.90',
  klarna:
    'amount:medium country:DE device:mobile bnpl_rate:0.80 first_purchase:false',
  apple_pay:
    'amount:low country:US device:mobile saved_card:true hour:12',
  bank_transfer:
    'amount:high country:NL device:desktop first_purchase:false',
};

async function seedEmbeddings(env: { AI: Ai; PM_EMBEDDINGS: KVNamespace }) {
  for (const [method, profile] of Object.entries(METHOD_PROFILES)) {
    const { data: [embedding] } = await env.AI.run(
      '@cf/baai/bge-small-en-v1.5',
      { text: [profile] }
    ) as { data: number[][] };
    await env.PM_EMBEDDINGS.put(
      `embedding:${method}`,
      JSON.stringify(embedding),
      { expirationTtl: 60 * 60 * 24 * 30 } // 30 days
    );
  }
}

export { seedEmbeddings };
```

---

## 4. Worker Entry Point — Checkout Ranking Endpoint

```typescript
// src/index.ts
import { extractFeatures } from './features';
import { rankPaymentMethods } from './pm-ranker';

interface Env {
  DB: D1Database;
  AI: Ai;
  PM_EMBEDDINGS: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method !== 'POST' || url.pathname !== '/rank-payment-methods')
      return new Response('Not found', { status: 404 });

    const { userId, cartAmountCents, countryCode, deviceType } =
      await request.json<{
        userId: string;
        cartAmountCents: number;
        countryCode: string;
        deviceType: string;
      }>();

    const features = await extractFeatures(
      env, userId, cartAmountCents, countryCode, deviceType
    );
    const ranked = await rankPaymentMethods(env, features);

    // Log for offline retraining
    await env.DB.prepare(
      `INSERT INTO pm_ranking_logs (user_id, ranked_methods, features_json, created_at)
       VALUES (?, ?, ?, CURRENT_TIMESTAMP)`
    )
      .bind(userId, JSON.stringify(ranked.map((r) => r.method)), JSON.stringify(features))
      .run();

    return Response.json({ ranked });
  },
};
```

---

## 5. Feedback Loop — Recording Actual Method Chosen

```typescript
// src/feedback.ts
export async function recordPaymentChoice(
  db: D1Database,
  userId: string,
  chosenMethod: string,
  status: 'succeeded' | 'failed'
): Promise<void> {
  await db.prepare(
    `INSERT INTO payment_attempts (user_id, payment_method, status, created_at)
     VALUES (?, ?, ?, CURRENT_TIMESTAMP)`
  ).bind(userId, chosenMethod, status).run();
}
```

---

## Anti-patterns

- **Running embedding inference on every checkout page load without caching** — Cache the user's ranked list in KV with a 30-minute TTL; re-rank on cart change or session expiry only.
- **Using only historical success rates** — A user who has only ever used card will always score card highest even if BNPL has better conversion for their cart size. Blend population-level priors with individual history.
- **Storing raw model weights in KV** — KV values cap at 25 MB; use R2 for model assets and only store embeddings (384 floats ≈ 3 KB) in KV.
- **Ranking non-eligible methods** — Filter out methods not supported in the user's country or for their cart amount *before* passing to the ranker.

## Gotchas

- `@cf/baai/bge-small-en-v1.5` output is a 384-dimensional float array; `@cf/baai/bge-base-en-v1.5` is 768-dim and more accurate but ~2× slower.
- Workers AI inference counts toward your AI Gateway quota; add an AI Gateway binding for logging and rate limiting if usage spikes.
- The cosine similarity approach is a proxy — for higher accuracy, fine-tune a tabular classifier (XGBoost, LightGBM) offline and export to ONNX for Workers AI inference.
- Cold-start latency for Workers AI models is ~50–150 ms; pre-warm by keeping the Worker active or use a longer `max_age` in your KV TTL for embeddings.

## Verification

```bash
curl -X POST https://your-worker.workers.dev/rank-payment-methods \
  -H 'Content-Type: application/json' \
  -d '{"userId":"usr_123","cartAmountCents":4999,"countryCode":"DE","deviceType":"mobile"}'

# Expected: ranked array with method + score, ordered highest-first
# {"ranked":[{"method":"klarna","score":0.94},{"method":"card","score":0.88},...]}'
```

## Related

- `payment-method-prioritization-ux.md`
- `fraud-scoring-pipeline-workers-ai.md`
- `card-bin-lookup-intelligent-routing-workers.md`
- `payment-orchestration-multi-psp-routing.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers-ai/models/bge-small-en-v1.5/
- https://developers.cloudflare.com/kv/
- https://baike.sber.ai/docs/research/bgem3
