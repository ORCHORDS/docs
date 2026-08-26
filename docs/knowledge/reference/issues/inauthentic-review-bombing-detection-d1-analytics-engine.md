# Inauthentic Review Bombing Detection via D1 and Analytics Engine

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Review bombing occurs when a coordinated group submits large volumes of negative (or artificially positive) ratings in a short window to manipulate aggregate scores — for a user profile, a piece of content, a community, or a creator. On anonymous platforms the lack of identity makes it trivial to generate many votes from throwaway accounts. Left unchecked, review bombing distorts trust signals, discourages legitimate users, and can be weaponised for targeted harassment or commercial manipulation.

## Context

Detection requires two complementary data stores: Cloudflare Analytics Engine captures high-frequency rating events as time-series data points without impacting D1 write throughput; D1 stores the canonical aggregate score and per-account vote records for deduplication and audit. A scheduled Worker queries Analytics Engine's SQL API for statistical anomalies (velocity spikes, entropy collapse, ASN concentration) and writes suppression flags back to D1 when a bombing pattern is confirmed. Flagged rating batches are excluded from aggregate calculation until a human reviewer lifts the suppression.

## Rating Ingestion — Analytics Engine Write Path

Every rating event is written to Analytics Engine immediately. D1 only receives a deduplication record; the heavy time-series analysis stays in Analytics Engine to avoid D1 write contention.

```typescript
// worker: rating-ingest.ts
export interface Env {
  DB: D1Database;
  ANALYTICS: AnalyticsEngineDataset;
}

interface RatingEvent {
  targetId: string;   // content or user being rated
  targetType: 'post' | 'user' | 'community';
  score: number;      // e.g. 1-5 or -1/+1
  accountId: string;  // hashed anonymous account token
}

export async function ingestRating(
  req: Request,
  env: Env,
  event: RatingEvent
): Promise<Response> {
  const cf = req.cf as Record<string, string | number | undefined>;
  const asn = String(cf?.asn ?? 0);
  const country = String(cf?.country ?? 'XX');
  const now = Math.floor(Date.now() / 1000);

  // Deduplicate: one vote per account per target
  const existing = await env.DB.prepare(
    `SELECT vote_id FROM votes
     WHERE account_id = ?1 AND target_id = ?2 LIMIT 1`
  ).bind(event.accountId, event.targetId).first();

  if (existing) {
    return Response.json({ status: 'duplicate' }, { status: 409 });
  }

  // Write to D1 for deduplication and audit
  await env.DB.prepare(
    `INSERT INTO votes (vote_id, account_id, target_id, target_type, score, asn, country, created_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)`
  ).bind(
    crypto.randomUUID(), event.accountId, event.targetId,
    event.targetType, event.score, asn, country, now
  ).run();

  // Write to Analytics Engine — zero impact on D1 write throughput
  env.ANALYTICS.writeDataPoint({
    blobs: [event.targetId, event.targetType, asn, country],
    doubles: [event.score],
    indexes: [event.targetId],
  });

  return Response.json({ status: 'accepted' });
}
```

## Anomaly Detection in Scheduled Worker

A scheduled Worker queries Analytics Engine's SQL API for each active target and looks for three signals: velocity (votes per minute above baseline), entropy collapse (proportion from a single ASN above threshold), and polarity collapse (>90% of scores are identical).

```typescript
// worker: bombing-detector.ts (scheduled every 5 minutes)
export interface Env {
  DB: D1Database;
  AE_ACCOUNT_ID: string;
  AE_API_TOKEN: string;
}

interface AERow {
  target_id: string;
  vote_count: number;
  dominant_asn_share: number; // 0-1
  polarity_share: number;     // fraction with score == modal score
}

async function queryAnalyticsEngine(
  env: Env,
  lookbackMinutes: number
): Promise<AERow[]> {
  const sql = `
    SELECT
      blob1 AS target_id,
      COUNT() AS vote_count,
      MAX(asn_count) / CAST(COUNT() AS FLOAT) AS dominant_asn_share,
      MAX(score_count) / CAST(COUNT() AS FLOAT) AS polarity_share
    FROM (
      SELECT
        blob1,
        double1,
        COUNT() OVER (PARTITION BY blob1, blob3) AS asn_count,
        COUNT() OVER (PARTITION BY blob1, double1) AS score_count
      FROM ANALYTICS_ENGINE_DATASET
      WHERE timestamp > NOW() - INTERVAL '${lookbackMinutes}' MINUTE
    )
    GROUP BY blob1
    HAVING vote_count >= 10
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.AE_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.AE_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  const json = await res.json<{ data: AERow[] }>();
  return json.data ?? [];
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const rows = await queryAnalyticsEngine(env, 10); // last 10 minutes

    const flagged: string[] = [];

    for (const row of rows) {
      const isBombing =
        row.vote_count >= 30 ||              // velocity: ≥30 votes in 10 min
        row.dominant_asn_share >= 0.6 ||     // entropy: >60% from one ASN
        row.polarity_share >= 0.9;           // polarity: >90% same score

      if (isBombing) {
        flagged.push(row.target_id);
      }
    }

    if (flagged.length === 0) return;

    // Write suppression flags to D1
    const stmts = flagged.map((targetId) =>
      env.DB.prepare(
        `INSERT INTO bombing_suppressions (target_id, detected_at, status, reviewer_action)
         VALUES (?1, unixepoch(), 'active', 'pending')
         ON CONFLICT(target_id) DO UPDATE SET
           detected_at    = unixepoch(),
           status         = 'active',
           reviewer_action = 'pending'`
      ).bind(targetId)
    );

    for (let i = 0; i < stmts.length; i += 100) {
      await env.DB.batch(stmts.slice(i, i + 100));
    }

    console.log(`[bombing-detector] flagged ${flagged.length} targets`);
  },
};
```

## Score Aggregation Excluding Suppressed Votes

The aggregate rating served to users excludes votes cast during an active suppression window so manipulated scores do not surface.

```typescript
// worker: score-aggregator.ts
export interface Env {
  DB: D1Database;
}

export async function getTargetScore(
  env: Env,
  targetId: string
): Promise<{ score: number; voteCount: number; suppressed: boolean }> {
  // Check for active suppression
  const suppression = await env.DB.prepare(
    `SELECT detected_at FROM bombing_suppressions
     WHERE target_id = ?1 AND status = 'active' LIMIT 1`
  ).bind(targetId).first<{ detected_at: number }>();

  if (suppression) {
    // Serve score from before the bombing window (votes cast before detection)
    const { results } = await env.DB.prepare(
      `SELECT AVG(score) AS avg_score, COUNT(*) AS cnt FROM votes
       WHERE target_id = ?1 AND created_at < ?2`
    ).bind(targetId, suppression.detected_at)
      .all<{ avg_score: number; cnt: number }>();

    const row = results[0];
    return {
      score: row?.avg_score ?? 0,
      voteCount: row?.cnt ?? 0,
      suppressed: true,
    };
  }

  const row = await env.DB.prepare(
    `SELECT AVG(score) AS avg_score, COUNT(*) AS cnt FROM votes WHERE target_id = ?1`
  ).bind(targetId).first<{ avg_score: number; cnt: number }>();

  return {
    score: row?.avg_score ?? 0,
    voteCount: row?.cnt ?? 0,
    suppressed: false,
  };
}
```

## Reviewer Lift and Audit Trail

Trust & Safety reviewers can lift a suppression (genuine votes) or confirm it (votes purged). Both actions are written to an immutable audit log.

```typescript
// worker: suppression-review.ts
export interface Env {
  DB: D1Database;
}

type ReviewerDecision = 'lift' | 'confirm_purge';

export async function resolveSupression(
  env: Env,
  targetId: string,
  reviewerId: string,
  decision: ReviewerDecision
): Promise<void> {
  const newStatus = decision === 'lift' ? 'lifted' : 'confirmed';

  await env.DB.batch([
    env.DB.prepare(
      `UPDATE bombing_suppressions
       SET status = ?1, reviewer_action = ?2, resolved_at = unixepoch()
       WHERE target_id = ?3`
    ).bind(newStatus, decision, targetId),

    env.DB.prepare(
      `INSERT INTO bombing_audit_log (target_id, reviewer_id, decision, logged_at)
       VALUES (?1, ?2, ?3, unixepoch())`
    ).bind(targetId, reviewerId, decision),

    // On confirmed purge: soft-delete the bombing votes
    ...(decision === 'confirm_purge'
      ? [env.DB.prepare(
          `UPDATE votes SET purged = 1
           WHERE target_id = ?1 AND created_at >= (
             SELECT detected_at FROM bombing_suppressions WHERE target_id = ?1
           )`
        ).bind(targetId)]
      : []),
  ]);
}
```

## Anti-patterns

- Writing every rating event to D1 synchronously — high-volume rating bursts will hit D1's per-database write throughput limit; use Analytics Engine for the time-series hot path
- Using only absolute vote count as the bombing signal — a popular post legitimately receives many votes; combine velocity with ASN concentration and polarity to reduce false positives
- Hard-deleting suspected bombing votes immediately — retain purged votes with a `purged = 1` flag for audit and appeal; hard deletion destroys evidence
- Serving cached aggregate scores without checking suppression state — a cached score calculated during a bombing window will remain manipulated until cache expiry; invalidate on suppression flag writes
- Using reviewer account IDs as PII in the audit log if reviewers are also anonymous — hash reviewer IDs the same way user IDs are hashed

## Gotchas

- Analytics Engine SQL API uses `blob1`/`blob2`... column names for `blobs` array entries and `double1`/`double2`... for `doubles` — there are no named columns; map by position
- Analytics Engine data has approximate real-time availability (~30-second lag); do not use it for real-time request blocking — use D1 or KV for that
- `ON CONFLICT(target_id) DO UPDATE` in D1 requires a unique index or primary key on `target_id`; create one explicitly: `CREATE UNIQUE INDEX idx_suppressions_target ON bombing_suppressions(target_id)`
- Window functions (`COUNT() OVER (PARTITION BY ...)`) are available in Analytics Engine SQL but not in D1 SQLite without `SELECT` subqueries; the two SQL dialects differ
- Analytics Engine dataset names in `wrangler.toml` must match the binding name used in `env.ANALYTICS.writeDataPoint`; a mismatch produces a silent no-op rather than an error in local dev

## Verification

1. Insert 35 votes for a single `target_id` with `created_at` in the last 10 minutes; fire the detector Worker; assert a `bombing_suppressions` row with `status = 'active'` is created.
2. Call `getTargetScore` for the flagged target; confirm `suppressed: true` and that the returned score reflects only pre-detection votes.
3. Call `resolveSupression` with `decision = 'confirm_purge'`; verify `votes.purged = 1` for post-detection rows and that the `bombing_audit_log` row exists.
4. Call `resolveSupression` with `decision = 'lift'`; verify `bombing_suppressions.status = 'lifted'` and `getTargetScore` now returns `suppressed: false`.
5. Send votes from 3+ distinct ASNs but with identical scores (polarity collapse) and verify the detector still flags via the `polarity_share >= 0.9` branch.

## Related

- `coordinated-inauthentic-behavior-detection-d1.md`
- `fake-engagement-metrics-detection-workers-ai.md`
- `anonymous-brigading-detection-durable-objects.md`
- `platform-reputation-score-decay-d1-workers.md`
- `poll-vote-manipulation-detection-d1.md`
- `platform-health-score-dashboard-analytics-engine.md`

## Sources

- Cloudflare Analytics Engine documentation — SQL API and data point structure: https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare D1 documentation — batch and conflict resolution: https://developers.cloudflare.com/d1/
- Yelp Engineering — "Detecting Fake Reviews" (2016): https://engineeringblog.yelp.com/2016/08/review-bombing.html
- ACM FAccT 2023 — Coordinated Inauthentic Behavior on Rating Platforms
