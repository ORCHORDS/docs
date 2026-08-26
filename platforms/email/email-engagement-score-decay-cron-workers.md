# Email Engagement Score Decay with Workers Cron

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your subscriber engagement scoring model awards points for opens, clicks, and conversions, but scores never decrease. After 12 months a subscriber who opened 20 emails two years ago still shows a high score, skewing segmentation and inflating your "active" list count.

You need a decay function that reduces scores over time for subscribers who have not engaged recently, without requiring a full recompute from raw event history on every send.

---

## Context

Engagement score decay (also called "score ageing" or "time-based decay") models the idea that a recent open is more valuable than one from two years ago. The two most common decay shapes are:

- **Exponential decay** — `score × e^(−λ × days)` — smooth, continuous reduction; half-life controlled by λ.
- **Step decay** — subtract a fixed amount per inactivity period (e.g., −5 points per 30-day no-engagement window).

The implementation runs as a Cloudflare Workers Cron Trigger that processes subscribers in paginated batches, reads the last engagement date from D1, applies the decay formula, and writes the updated score back. Because Cron Workers have a 30-second CPU time limit per invocation (Paid plan), large lists must be processed in batches across multiple invocations using a cursor stored in KV.

---

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS subscribers (
  id                 TEXT PRIMARY KEY,
  email              TEXT NOT NULL UNIQUE,
  engagement_score   REAL NOT NULL DEFAULT 0,
  last_engaged_at    TEXT,             -- ISO-8601 UTC
  score_decayed_at   TEXT,             -- last time decay was applied
  active             INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_subscribers_score
  ON subscribers (engagement_score DESC);

CREATE INDEX IF NOT EXISTS idx_subscribers_last_engaged
  ON subscribers (last_engaged_at);
```

---

## Exponential Decay Formula

```typescript
const HALF_LIFE_DAYS = 30; // score halves every 30 days of inactivity
const LAMBDA = Math.LN2 / HALF_LIFE_DAYS; // ≈ 0.0231

function applyExponentialDecay(
  currentScore: number,
  lastEngagedAt: string | null,
  now: Date
): number {
  if (!lastEngagedAt || currentScore <= 0) return currentScore;

  const lastEngaged = new Date(lastEngagedAt);
  const daysSinceEngagement =
    (now.getTime() - lastEngaged.getTime()) / (1000 * 60 * 60 * 24);

  // Decay only applies after a 7-day grace period
  if (daysSinceEngagement < 7) return currentScore;

  const decayedScore = currentScore * Math.exp(-LAMBDA * daysSinceEngagement);

  // Floor to 0; scores below 1 are treated as disengaged
  return Math.max(0, Math.round(decayedScore * 100) / 100);
}
```

---

## Cron Worker with KV-Backed Pagination Cursor

```typescript
// wrangler.toml
// [triggers]
// crons = ["0 3 * * *"]  # 03:00 UTC daily

const BATCH_SIZE = 500;
const CURSOR_KEY = "decay_cursor:offset";

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const now = new Date();

    // Read pagination cursor (resume across multiple invocations if needed)
    const offsetStr = await env.DECAY_KV.get(CURSOR_KEY);
    let offset = offsetStr ? parseInt(offsetStr, 10) : 0;

    // Reset cursor if this is a fresh daily run (cursor older than 12 hours)
    const cursorMeta = await env.DECAY_KV.getWithMetadata<{ ts: number }>(CURSOR_KEY);
    if (cursorMeta.metadata && Date.now() - cursorMeta.metadata.ts > 12 * 3600 * 1000) {
      offset = 0;
    }

    let processed = 0;

    while (true) {
      const batch = await env.DB.prepare(
        `SELECT id, engagement_score, last_engaged_at
         FROM subscribers
         WHERE active = 1
         ORDER BY id
         LIMIT ? OFFSET ?`
      )
        .bind(BATCH_SIZE, offset)
        .all<{ id: string; engagement_score: number; last_engaged_at: string | null }>();

      if (!batch.results.length) {
        // Done — clear cursor
        await env.DECAY_KV.delete(CURSOR_KEY);
        break;
      }

      await applyDecayBatch(batch.results, now, env);

      processed += batch.results.length;
      offset += BATCH_SIZE;

      // Save cursor in case we approach the 30s CPU limit
      await env.DECAY_KV.put(
        CURSOR_KEY,
        String(offset),
        { metadata: { ts: Date.now() }, expirationTtl: 86400 }
      );

      // Yield to avoid CPU limit — Workers scheduled events are not preempted
      // between synchronous chunks, but D1 await calls provide natural yield points
    }

    console.log(`Decay run complete: ${processed} subscribers processed`);
  },
};
```

---

## Batch Decay Update in D1

```typescript
interface SubscriberRow {
  id: string;
  engagement_score: number;
  last_engaged_at: string | null;
}

async function applyDecayBatch(
  rows: SubscriberRow[],
  now: Date,
  env: Env
): Promise<void> {
  const statements = rows
    .map((row) => {
      const newScore = applyExponentialDecay(
        row.engagement_score,
        row.last_engaged_at,
        now
      );

      // Skip write if score unchanged (avoid unnecessary D1 writes)
      if (Math.abs(newScore - row.engagement_score) < 0.01) return null;

      return env.DB.prepare(
        `UPDATE subscribers
         SET engagement_score = ?, score_decayed_at = ?
         WHERE id = ?`
      ).bind(newScore, now.toISOString(), row.id);
    })
    .filter((s): s is D1PreparedStatement => s !== null);

  if (statements.length === 0) return;

  // D1 batch write — up to 100 statements per batch call
  for (let i = 0; i < statements.length; i += 100) {
    await env.DB.batch(statements.slice(i, i + 100));
  }
}
```

---

## Boosting Score on New Engagement Events

```typescript
// Called by your open/click tracking Worker
export async function recordEngagement(
  subscriberId: string,
  eventType: "open" | "click" | "conversion",
  env: Env
): Promise<void> {
  const boosts: Record<string, number> = {
    open: 5,
    click: 15,
    conversion: 50,
  };

  const boost = boosts[eventType] ?? 5;
  const MAX_SCORE = 100;

  await env.DB.prepare(
    `UPDATE subscribers
     SET
       engagement_score = MIN(?, engagement_score + ?),
       last_engaged_at  = datetime('now')
     WHERE id = ?`
  )
    .bind(MAX_SCORE, boost, subscriberId)
    .run();
}
```

---

## Surfacing Disengaged Subscribers for Sunset

```typescript
export async function getDisengagedSubscribers(
  env: Env,
  scoreThreshold = 5,
  limit = 1000
): Promise<{ id: string; email: string; engagement_score: number }[]> {
  const { results } = await env.DB.prepare(
    `SELECT id, email, engagement_score
     FROM subscribers
     WHERE active = 1 AND engagement_score <= ?
     ORDER BY engagement_score ASC
     LIMIT ?`
  )
    .bind(scoreThreshold, limit)
    .all<{ id: string; email: string; engagement_score: number }>();

  return results;
}
```

---

## Anti-patterns

- **Running decay on every send** — calculating decay inline per-send adds latency and re-computes redundant decay for subscribers not in the current send batch. Centralise decay in the Cron Worker.
- **Applying decay to subscribers with no engagement history** — decaying a score that was never earned (e.g., new subscribers who joined yesterday) penalises legitimate subscribers; apply decay only after the first engagement event or after a minimum age grace period.
- **Using a single global decay rate** — segment-level decay rates (e.g., faster decay for cold leads, slower for paying customers) better reflect business value. Store a per-segment `half_life_days` in D1.
- **Decaying to a negative score** — clamp the score to 0; negative scores break segmentation queries that use `score > threshold` filters.

---

## Gotchas

- Workers Cron Triggers on the Paid plan have a **30-second CPU time limit** per invocation. For lists exceeding ~50,000 subscribers, the KV cursor approach ensures safe pagination across multiple daily invocations.
- D1 `batch()` accepts a maximum of **100 statements** per call; split larger batches accordingly.
- `Math.exp(-λ × days)` with very large `days` (e.g., 3 years) produces a value indistinguishable from 0 in floating-point; set an absolute floor of 0 and consider marking scores below 1 as permanently disengaged.
- If the Cron Worker fails mid-run, the KV cursor preserves the offset so the next invocation resumes rather than starting over — but the `metadata.ts` timestamp check must correctly distinguish a mid-run resume from a fresh daily trigger.

---

## Verification

```bash
# Trigger the Cron Worker manually to test
wrangler dev --test-scheduled

# Or trigger via API
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/scripts/decay-worker/schedules" \
  -H "Authorization: Bearer $CF_API_TOKEN"

# Check score distribution before and after
wrangler d1 execute DB --command \
  "SELECT
     CASE
       WHEN engagement_score >= 50 THEN 'high'
       WHEN engagement_score >= 20 THEN 'medium'
       WHEN engagement_score >= 5  THEN 'low'
       ELSE 'disengaged'
     END AS tier,
     COUNT(*) as count
   FROM subscribers GROUP BY tier"

# Confirm decay timestamp was written
wrangler d1 execute DB --command \
  "SELECT id, engagement_score, score_decayed_at FROM subscribers
   WHERE score_decayed_at IS NOT NULL ORDER BY score_decayed_at DESC LIMIT 10"
```

---

## Related

- `email-engagement-scoring-segmentation.md`
- `email-newsletter-segmentation-d1-workers.md`
- `email-sunset-policy.md`
- `email-fatigue-prevention.md`
- `email-warm-up-cron-workers-schedule.md`

---

## Sources

- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1 Batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- Exponential decay model — https://en.wikipedia.org/wiki/Exponential_decay
