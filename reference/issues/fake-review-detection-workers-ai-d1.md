# Fake Review Detection Pipeline with Workers AI and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A marketplace notices sudden bursts of 5-star reviews on specific products, often from newly created accounts that have not purchased the item. Organic review velocity analysis, purchase verification, and text similarity checks are needed to catch review farms at submission time before the reviews go live.

## Context

The pipeline scores every review on submission across four axes:

1. **Burst score** — reviews-per-hour for the product in the last 6 hours vs. the 30-day baseline.
2. **Account age** — reviewer account age in days (new accounts are higher risk).
3. **Purchase verification** — whether the reviewer has a verified purchase for the product.
4. **AI authenticity score** — Workers AI text classifier probability that the review is machine-generated or template-based.

Signals are written to `review_signals` in D1. Reviews below a composite threshold enter a moderation queue. An n-gram similarity check catches copy-paste review farms within the same product. Once a farm network is confirmed, a bulk suppression endpoint bans all member accounts and removes their reviews.

## Submission-Time Scoring Worker

```typescript
import { Ai } from '@cloudflare/ai';

export interface Env {
  DB: D1Database;
  AI: Ai;
  REVIEWS_KV: KVNamespace; // stores rolling burst counters
}

const COMPOSITE_THRESHOLD = 0.45; // below this → moderation queue

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST' || new URL(req.url).pathname !== '/review/submit') {
      return new Response('not found', { status: 404 });
    }

    const { review_id, product_id, reviewer_id, review_text, verified_purchase } =
      await req.json<{
        review_id: string; product_id: string; reviewer_id: string;
        review_text: string; verified_purchase: boolean;
      }>();

    // 1. Burst score
    const burstScore = await computeBurstScore(env, product_id);

    // 2. Account age
    const accountRow = await env.DB.prepare(
      'SELECT registered_at FROM accounts WHERE id = ?',
    ).bind(reviewer_id).first<{ registered_at: number }>();
    const ageDays = accountRow
      ? Math.floor((Date.now() / 1000 - accountRow.registered_at) / 86400)
      : 0;

    // 3. AI authenticity score (lower = more suspicious)
    const aiResult = await (env.AI as any).run(
      '@cf/example-org/example-repo',
      { text: review_text },
    ) as { label: string; score: number }[];
    const authenticityScore = aiResult.find(r => r.label === 'authentic')?.score ?? 0;

    // 4. Composite score (0 = very suspicious, 1 = clean)
    const purchaseFactor = verified_purchase ? 1.0 : 0.3;
    const ageFactor = Math.min(ageDays / 90, 1.0); // caps at 90 days
    const burstFactor = Math.max(0, 1.0 - burstScore);
    const composite = (
      authenticityScore * 0.4 +
      purchaseFactor   * 0.3 +
      ageFactor        * 0.2 +
      burstFactor      * 0.1
    );

    // 5. Write signals to D1
    await env.DB.prepare(`
      INSERT INTO review_signals
        (review_id, burst_score, account_age_days, verified_purchase,
         ai_authenticity_score, composite_score, status, submitted_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, unixepoch())
    `).bind(
      review_id, burstScore, ageDays, verified_purchase ? 1 : 0,
      authenticityScore, composite,
      composite < COMPOSITE_THRESHOLD ? 'queued' : 'approved',
    ).run();

    // 6. N-gram similarity check for copy-paste farms
    if (composite < COMPOSITE_THRESHOLD) {
      const isFarm = await checkNgramSimilarity(env, product_id, review_text, review_id);
      if (isFarm) {
        await env.DB.prepare(
          "UPDATE review_signals SET status = 'farm_suspect' WHERE review_id = ?",
        ).bind(review_id).run();
      }
    }

    return Response.json({
      review_id,
      composite_score: composite,
      status: composite < COMPOSITE_THRESHOLD ? 'pending_moderation' : 'approved',
    });
  },
};

async function computeBurstScore(env: Env, productId: string): Promise<number> {
  const key = `burst:${productId}:${Math.floor(Date.now() / 3600000)}`;
  const current = parseInt(await env.REVIEWS_KV.get(key) ?? '0', 10) + 1;
  await env.REVIEWS_KV.put(key, String(current), { expirationTtl: 21600 }); // 6h window

  // Fetch 30-day baseline from D1
  const row = await env.DB.prepare(`
    SELECT AVG(hourly_count) AS baseline
    FROM (
      SELECT COUNT(*) AS hourly_count
      FROM review_signals
      WHERE review_id IN (
        SELECT review_id FROM reviews WHERE product_id = ?
      )
      AND submitted_at > unixepoch('now', '-30 days')
      GROUP BY (submitted_at / 3600)
    )
  `).bind(productId).first<{ baseline: number | null }>();

  const baseline = row?.baseline ?? 1;
  return Math.min(current / Math.max(baseline * 5, 1), 1.0); // normalized 0–1
}

async function checkNgramSimilarity(
  env: Env, productId: string, newText: string, excludeId: string,
): Promise<boolean> {
  const existing = await env.DB.prepare(`
    SELECT rs.review_id, r.review_text
    FROM review_signals rs
    JOIN reviews r ON r.id = rs.review_id
    WHERE r.product_id = ? AND rs.review_id != ?
    ORDER BY rs.submitted_at DESC
    LIMIT 100
  `).bind(productId, excludeId).all<{ review_id: string; review_text: string }>();

  const newNgrams = buildNgrams(newText, 4);
  for (const row of existing.results) {
    const existingNgrams = buildNgrams(row.review_text, 4);
    const intersection = [...newNgrams].filter(g => existingNgrams.has(g)).length;
    const jaccard = intersection / (newNgrams.size + existingNgrams.size - intersection);
    if (jaccard > 0.65) return true; // 65% n-gram overlap = likely copy-paste
  }
  return false;
}

function buildNgrams(text: string, n: number): Set<string> {
  const tokens = text.toLowerCase().split(/\s+/);
  const grams = new Set<string>();
  for (let i = 0; i <= tokens.length - n; i++) {
    grams.add(tokens.slice(i, i + n).join(' '));
  }
  return grams;
}
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS review_signals (
  review_id            TEXT PRIMARY KEY,
  burst_score          REAL NOT NULL,
  account_age_days     INTEGER NOT NULL,
  verified_purchase    INTEGER NOT NULL DEFAULT 0,
  ai_authenticity_score REAL NOT NULL,
  composite_score      REAL NOT NULL,
  status               TEXT NOT NULL DEFAULT 'approved', -- approved | queued | farm_suspect | suppressed
  submitted_at         INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rs_status ON review_signals (status, submitted_at DESC);
```

## Bulk Suppression of a Review Farm Network

Once a moderator confirms a farm cluster, call the suppression endpoint with the list of `review_id` values:

```typescript
async function suppressFarm(env: Env, reviewIds: string[]): Promise<number> {
  const placeholders = reviewIds.map(() => '?').join(',');

  // Mark reviews as suppressed
  await env.DB.prepare(
    `UPDATE review_signals SET status = 'suppressed' WHERE review_id IN (${placeholders})`,
  ).bind(...reviewIds).run();

  // Suspend the reviewer accounts
  const reviewerRows = await env.DB.prepare(
    `SELECT DISTINCT reviewer_id FROM reviews WHERE id IN (${placeholders})`,
  ).bind(...reviewIds).all<{ reviewer_id: string }>();

  if (reviewerRows.results.length) {
    const suspendStmt = env.DB.prepare('UPDATE accounts SET suspended = 1 WHERE id = ?');
    await env.DB.batch(reviewerRows.results.map(r => suspendStmt.bind(r.reviewer_id)));
  }

  return reviewerRows.results.length;
}
```

## Anti-patterns

- **Approving reviews synchronously without scoring** — every review, even from trusted accounts, should pass through the pipeline to maintain consistent signal data.
- **Using only purchase verification as the gate** — review farms often obtain real purchases specifically to bypass verification; always combine signals.
- **Hard-coding the composite threshold** — expose it as a Worker secret or D1 config row so it can be adjusted without redeployment during an active farm attack.
- **Ignoring burst score decay** — old burst counters must expire from KV; use `expirationTtl` on every write.

## Gotchas

- D1 does not support `IN (?)` with an array binding — build the placeholder string dynamically and spread the array as individual bind arguments.
- The n-gram check is O(n × m) and becomes expensive for products with thousands of reviews; limit the comparison window to the 100 most recent reviews.
- Workers AI custom models must be deployed to the correct Cloudflare account before the `AI.run` binding resolves.
- `burst_score` can spike legitimately for viral products — tune the burst factor weight (`0.1`) or use a longer baseline window for popular items.

## Verification

```bash
# Check distribution of review statuses
wrangler d1 execute example project-db --command \
  "SELECT status, COUNT(*) AS cnt FROM review_signals GROUP BY status;"

# Find farm suspects in the last 24h
wrangler d1 execute example project-db --command \
  "SELECT review_id, composite_score, submitted_at FROM review_signals WHERE status = 'farm_suspect' AND submitted_at > unixepoch('now', '-1 day');"
```

## Related

- `platform-manipulation-sock-puppet-detection-d1.md`
- Cloudflare Workers AI — text classification
- Cloudflare KV — TTL-based counters

## Sources

- Cloudflare Workers AI: https://developers.cloudflare.com/workers-ai/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Ott et al., "Finding Deceptive Opinion Spam by Any Stretch of the Imagination" (ACL 2011)
