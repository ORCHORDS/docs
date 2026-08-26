# Viral Misinformation Spread Containment — Workers + Queues

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A single piece of content flagged as likely misinformation begins spreading exponentially through example project's share graph before human moderators can review it. Unchecked, it reaches thousands of anonymous sessions within minutes, and deleting it after the fact does not undo the spread. The platform needs to detect the viral trajectory early and throttle resharing velocity without suppressing true organic news.

## Context

example project content sharing is processed by a Cloudflare Worker that writes share-graph edges to D1 and fan-out notifications to a Queue. Durable Objects track real-time share counters per content item. When a content item has previously been submitted to the misinformation review pipeline (via Workers AI or a third-party fact-check API), its `review_status` is stored in D1. The containment mechanism intercepts the share Queue consumer and applies a reshare rate limit using KV before allowing fan-out to continue.

## Detection — Viral Trajectory Scoring

```typescript
// workers/misinformation-spread-detector.ts
interface Env {
  DB: D1Database;
  SHARE_KV: KVNamespace;       // per-content rolling share counters
  REVIEW_KV: KVNamespace;      // cached misinformation review results
  SPREAD_QUEUE: Queue;
  AI: Ai;
}

interface ShareEvent {
  contentId: string;
  sharerSession: string;
  sourceSession: string;       // who they reshared from
  ts: number;
}

interface SpreadMetrics {
  sharesLast5Min: number;
  sharesLast30Min: number;
  uniqueSharersLast5Min: number;
  depthMax: number;            // longest share chain length
  reviewStatus: "clean" | "disputed" | "false" | "unreviewed";
}

async function getSpreadMetrics(contentId: string, env: Env): Promise<SpreadMetrics> {
  const [fast, slow, review] = await Promise.all([
    env.DB.prepare(
      `SELECT COUNT(*) AS c, COUNT(DISTINCT sharer_session) AS u
       FROM share_events
       WHERE content_id = ? AND occurred_at >= datetime('now', '-5 minutes')`
    ).first<{ c: number; u: number }>().bind(contentId),
    env.DB.prepare(
      `SELECT COUNT(*) AS c FROM share_events
       WHERE content_id = ? AND occurred_at >= datetime('now', '-30 minutes')`
    ).first<{ c: number }>().bind(contentId),
    env.DB.prepare(
      `SELECT review_status FROM content_review
       WHERE content_id = ? ORDER BY reviewed_at DESC LIMIT 1`
    ).first<{ review_status: string }>().bind(contentId),
    env.DB.prepare(
      `SELECT COALESCE(MAX(chain_depth), 0) AS d
       FROM share_events WHERE content_id = ?`
    ).first<{ d: number }>().bind(contentId),
  ]);

  return {
    sharesLast5Min: (await fast)?.c ?? 0,
    sharesLast30Min: (await slow)?.c ?? 0,
    uniqueSharersLast5Min: (await fast)?.u ?? 0,
    depthMax: 0, // resolved below
    reviewStatus: (review?.review_status as SpreadMetrics["reviewStatus"]) ?? "unreviewed",
  };
}

// Viral threshold parameters
const VIRAL_SHARES_5M  = 50;    // 50 shares in 5 min = viral velocity
const VIRAL_SHARES_30M = 200;   // 200 in 30 min = sustained viral
const VIRAL_UNIQUE_5M  = 30;    // 30 distinct sharers = organic spread (not bot)

function spreadRiskScore(m: SpreadMetrics): number {
  let score = 0;

  // Velocity signals
  if (m.sharesLast5Min >= VIRAL_SHARES_5M)  score += 0.3;
  if (m.sharesLast30Min >= VIRAL_SHARES_30M) score += 0.2;
  if (m.uniqueSharersLast5Min >= VIRAL_UNIQUE_5M) score += 0.1;

  // Misinformation status multiplier
  if (m.reviewStatus === "false")    score *= 2.0;
  if (m.reviewStatus === "disputed") score *= 1.5;
  if (m.reviewStatus === "unreviewed" && m.sharesLast5Min >= VIRAL_SHARES_5M) score += 0.25;

  // Depth signal (deep chains indicate successive resharing, not bots)
  if (m.depthMax >= 5) score += 0.15;

  return Math.min(score, 1.0);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const event = await request.json<ShareEvent>();

    // Compute chain depth from source
    const sourceDepth = await env.DB.prepare(
      `SELECT COALESCE(MAX(chain_depth), 0) AS d FROM share_events
       WHERE content_id = ? AND sharer_session = ?`
    ).bind(event.contentId, event.sourceSession).first<{ d: number }>();

    const chainDepth = (sourceDepth?.d ?? 0) + 1;

    // Write share event
    await env.DB.prepare(
      `INSERT INTO share_events
         (content_id, sharer_session, source_session, chain_depth, occurred_at)
       VALUES (?, ?, ?, ?, datetime(?, 'unixepoch'))`
    )
      .bind(event.contentId, event.sharerSession, event.sourceSession, chainDepth, Math.floor(event.ts / 1000))
      .run();

    // Throttle score computation to once per 30 s per content item
    const throttleKey = `spread-score:${event.contentId}`;
    const cached = await env.SHARE_KV.get(throttleKey, "json") as { score: number } | null;
    if (cached) {
      return new Response(JSON.stringify({ score: cached.score }), { status: 200 });
    }

    const metrics = await getSpreadMetrics(event.contentId, env);
    // Patch in the live chain depth
    const { results: depthRes } = await env.DB.prepare(
      `SELECT COALESCE(MAX(chain_depth), 0) AS d FROM share_events WHERE content_id = ?`
    ).bind(event.contentId).all<{ d: number }>();
    metrics.depthMax = depthRes[0]?.d ?? 0;

    const score = spreadRiskScore(metrics);

    await env.SHARE_KV.put(throttleKey, JSON.stringify({ score }), { expirationTtl: 30 });

    if (score >= 0.6) {
      await env.SPREAD_QUEUE.send({
        type: score >= 0.8 ? "MISINFO_VIRAL_HIGH" : "MISINFO_VIRAL_REVIEW",
        contentId: event.contentId,
        score,
        metrics,
        ts: Date.now(),
      });
    }

    return new Response(JSON.stringify({ score }), { status: 200 });
  },
};
```

## Response and Enforcement — Reshare Rate Limiting and Labelling

```typescript
// workers/misinformation-responder.ts
interface SpreadAlert {
  type: "MISINFO_VIRAL_HIGH" | "MISINFO_VIRAL_REVIEW";
  contentId: string;
  score: number;
  metrics: {
    sharesLast5Min: number;
    sharesLast30Min: number;
    reviewStatus: string;
  };
  ts: number;
}

// Queue consumer for share fan-out with containment gate
export default {
  async queue(batch: MessageBatch<SpreadAlert>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const evt = msg.body;

      if (evt.type === "MISINFO_VIRAL_HIGH") {
        // 1. Apply reshare rate cap: max 5 reshares per minute per content item
        await env.DB.prepare(
          `INSERT OR REPLACE INTO content_rate_caps
             (content_id, max_reshares_per_minute, reason, applied_at)
           VALUES (?, 5, 'viral_misinfo', CURRENT_TIMESTAMP)`
        ).bind(evt.contentId).run();

        // 2. Apply a visible label to the content item
        const label = evt.metrics.reviewStatus === "false"
          ? "fact_checked_false"
          : "under_review";

        await env.DB.prepare(
          `INSERT OR REPLACE INTO content_labels
             (content_id, label, applied_by, applied_at)
           VALUES (?, ?, 'system_spread_detector', CURRENT_TIMESTAMP)`
        ).bind(evt.contentId, label).run();

        // 3. Trigger a priority review task if unreviewed
        if (evt.metrics.reviewStatus === "unreviewed") {
          await env.DB.prepare(
            `INSERT OR IGNORE INTO priority_review_queue
               (content_id, reason, score, queued_at)
             VALUES (?, 'viral_unreviewed_content', ?, CURRENT_TIMESTAMP)`
          ).bind(evt.contentId, evt.score).run();
        }

        // 4. Log suppression event for audit
        await env.DB.prepare(
          `INSERT INTO spread_interventions
             (content_id, intervention_type, score, triggered_at)
           VALUES (?, 'rate_cap', ?, CURRENT_TIMESTAMP)`
        ).bind(evt.contentId, evt.score).run();
      }

      if (evt.type === "MISINFO_VIRAL_REVIEW") {
        await env.DB.prepare(
          `INSERT OR IGNORE INTO priority_review_queue
             (content_id, reason, score, queued_at)
           VALUES (?, 'viral_spread_review', ?, CURRENT_TIMESTAMP)`
        ).bind(evt.contentId, evt.score).run();
      }

      msg.ack();
    }
  },
};

// Reshare gate — call this in the share fan-out Worker before delivering notifications
export async function checkReshareGate(
  contentId: string,
  env: Env
): Promise<{ allowed: boolean; reason?: string }> {
  const [cap, recentCount] = await Promise.all([
    env.DB.prepare(
      `SELECT max_reshares_per_minute FROM content_rate_caps WHERE content_id = ?`
    ).first<{ max_reshares_per_minute: number }>().bind(contentId),
    env.DB.prepare(
      `SELECT COUNT(*) AS c FROM share_events
       WHERE content_id = ? AND occurred_at >= datetime('now', '-1 minute')`
    ).first<{ c: number }>().bind(contentId),
  ]);

  if (!cap) return { allowed: true };
  if ((await recentCount)?.c ?? 0 >= (await cap)?.max_reshares_per_minute) {
    return { allowed: false, reason: "rate_cap_viral_misinfo" };
  }
  return { allowed: true };
}
```

## Audit and Compliance — Schema and Reporting

```sql
-- D1 migration
CREATE TABLE IF NOT EXISTS share_events (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id      TEXT    NOT NULL,
  sharer_session  TEXT    NOT NULL,
  source_session  TEXT    NOT NULL,
  chain_depth     INTEGER NOT NULL DEFAULT 0,
  occurred_at     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_share_content_time
  ON share_events(content_id, occurred_at);

CREATE TABLE IF NOT EXISTS content_rate_caps (
  content_id              TEXT PRIMARY KEY,
  max_reshares_per_minute INTEGER NOT NULL,
  reason                  TEXT    NOT NULL,
  applied_at              TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS spread_interventions (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id        TEXT NOT NULL,
  intervention_type TEXT NOT NULL,
  score             REAL NOT NULL,
  triggered_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS priority_review_queue (
  content_id TEXT NOT NULL,
  reason     TEXT NOT NULL,
  score      REAL NOT NULL,
  queued_at  TEXT NOT NULL,
  PRIMARY KEY (content_id, reason)
);

-- Weekly spread containment report
SELECT
  strftime('%Y-%W', triggered_at) AS week,
  COUNT(*)                         AS interventions,
  AVG(score)                       AS avg_risk_score,
  SUM(intervention_type = 'rate_cap') AS rate_caps_applied
FROM spread_interventions
GROUP BY week
ORDER BY week DESC
LIMIT 8;
```

## Anti-patterns

- **Deleting viral misinformation immediately** without preserving the share graph — evidence of the spread pattern is needed for appeals and compliance reporting.
- **Applying rate caps to all viral content** regardless of review status — a breaking news event will naturally go viral; only apply caps when misinformation signals are also present.
- **Waiting for a human review** before any intervention on content with `review_status = 'false'` and viral velocity — the spread doubles every minute; automated rate caps must fire first.
- **Counting total shares as the sole viral signal** — a single bot account sharing 200 times looks viral but is easily banned; `uniqueSharersLast5Min` distinguishes bots from organic spread.
- **Setting the reshare cap to zero** (full block) on first detection — prefer a low rate cap (5/min) that slows spread while human review is pending; zero-cap is reserved for confirmed serious harms.

## Gotchas

- D1 `datetime('now', '-5 minutes')` is evaluated at query execution time in UTC — ensure all `occurred_at` timestamps are stored as UTC ISO-8601 strings.
- Queue consumers have a 15-minute visibility timeout; if the consumer fails and the message retries, ensure `INSERT OR IGNORE` / `INSERT OR REPLACE` are idempotent.
- `chain_depth` relies on reading the source session's max depth before writing — under concurrent share bursts this can race; use a Durable Object to serialize depth computation if accuracy is critical.
- The throttle KV key (`spread-score:{contentId}`) resets after 30 s; during a fast burst, up to 30 s of shares proceed without re-scoring. Tune this TTL based on acceptable detection latency.
- `content_rate_caps` rows are never auto-expired; once a rate cap is applied it persists until a moderator removes it. Add a scheduled Worker to release caps after human review clears the content.

## Verification

```bash
# 1. Seed 60 share events for "post-abc" within 1 minute
for i in $(seq 1 60); do
  curl -s -X POST https://example.com/internal/share-event \
    -H "Content-Type: application/json" \
    -d "{\"contentId\":\"post-abc\",\"sharerSession\":\"u$i\",
         \"sourceSession\":\"u0\",\"ts\":$(date +%s%3N)}" &
done; wait

# 2. Confirm spread_interventions row
wrangler d1 execute example project-db --command \
  "SELECT * FROM spread_interventions WHERE content_id='post-abc';"

# 3. Confirm rate cap applied
wrangler d1 execute example project-db --command \
  "SELECT * FROM content_rate_caps WHERE content_id='post-abc';"

# 4. Verify reshare gate blocks after cap
curl -X POST https://example.com/internal/reshare-gate \
  -H "Content-Type: application/json" \
  -d '{"contentId":"post-abc"}'
# Expect: {"allowed":false,"reason":"rate_cap_viral_misinfo"}

# 5. Confirm content label applied
wrangler d1 execute example project-db --command \
  "SELECT label FROM content_labels WHERE content_id='post-abc';"
```

## Related

- `election-misinformation-detection-workers-ai.md`
- `viral-content-cascade-rate-limiting-durable-objects.md`
- `emergency-content-takedown-circuit-breaker-queues.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `misinformation-labeling-pipeline-ugc.md`

## Sources

- https://www.poynter.org/fact-checking/
- https://firstdraftnews.org/long-form-article/understanding-information-disorder/
- https://developers.cloudflare.com/queues/
