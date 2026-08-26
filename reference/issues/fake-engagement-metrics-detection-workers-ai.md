# Fake Engagement Metrics Detection with Workers AI Time-Series Anomaly

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project (example.com) surfaces posts by engagement score: upvotes, shares, and comment counts drive content ranking. Adversarial actors inflate these metrics by scripting coordinated vote-bursts, buying engagement from bot networks, or exploiting session tokens to cast duplicate votes through anonymized proxies. The symptom is a post that rises from zero to hundreds of upvotes in under a minute with no corresponding organic traffic, then plateaus abruptly — a pattern invisible to simple threshold checks but detectable as a time-series anomaly.

Fake engagement harms the platform on two axes: it degrades content discovery for genuine users and exposes example project to regulatory scrutiny under DSA Article 37 (systemic risk assessments) which requires demonstrable mechanisms to detect and mitigate artificial amplification of content.

## Context

Cloudflare Workers record per-post engagement events in a time-bucketed format using Workers Analytics Engine for high-throughput write performance. A scheduled Worker reads recent time-series data via Analytics Engine's SQL API, feeds statistical anomaly detection logic (z-score over rolling baseline), and then invokes a Workers AI classification model to confirm suspicious patterns before writing flags to D1.

The system deliberately avoids attempting to identify the individual accounts behind fake votes — that information is unavailable on an anonymous platform and is not needed. The unit of analysis is the post's engagement curve, not any user.

## Engagement Event Ingestion to Analytics Engine

Every vote, share, or comment action emits a data point to Workers Analytics Engine. This provides sub-millisecond write latency with no D1 write contention under burst conditions.

```typescript
// worker: engagement-recorder.ts
export interface Env {
  ENGAGEMENT_ENGINE: AnalyticsEngineDataset;
  DB: D1Database;
}

type EngagementType = 'upvote' | 'downvote' | 'share' | 'comment';

interface EngagementEvent {
  postId: string;
  engagementType: EngagementType;
  sessionBucket: string; // hashed anon session prefix, not full ID
  ipAsn: string;
}

const METRIC_INDEX: Record<EngagementType, number> = {
  upvote: 0,
  downvote: 1,
  share: 2,
  comment: 3,
};

export async function recordEngagement(
  env: Env,
  event: EngagementEvent
): Promise<void> {
  const metricIdx = METRIC_INDEX[event.engagementType];
  const doubles = [0, 0, 0, 0];
  doubles[metricIdx] = 1;

  env.ENGAGEMENT_ENGINE.writeDataPoint({
    blobs: [event.postId, event.sessionBucket, event.ipAsn],
    doubles,
    indexes: [event.postId], // partition by post for efficient time-series queries
  });

  // Also update aggregate counters in D1 for ranking (eventual consistency is fine here)
  await env.DB.prepare(`
    INSERT INTO post_engagement (post_id, upvotes, downvotes, shares, comments, updated_at)
    VALUES (?1, ?2, ?3, ?4, ?5, unixepoch())
    ON CONFLICT(post_id) DO UPDATE SET
      upvotes   = upvotes + excluded.upvotes,
      downvotes = downvotes + excluded.downvotes,
      shares    = shares + excluded.shares,
      comments  = comments + excluded.comments,
      updated_at = unixepoch()
  `).bind(
    event.postId,
    doubles[0], doubles[1], doubles[2], doubles[3]
  ).run();
}
```

## Time-Series Anomaly Detection via Analytics Engine SQL API

A scheduled Worker queries Analytics Engine for per-post upvote counts in 1-minute buckets over the past 2 hours and applies a z-score computation to identify buckets that deviate significantly from the baseline rate.

```typescript
// worker: anomaly-detector.ts (scheduled every 5 minutes)
export interface Env {
  DB: D1Database;
  AI: Ai;
  ACCOUNT_ID: string;
  AE_TOKEN: string; // Analytics Engine read token from secret
}

interface BucketRow {
  minute_bucket: string;
  post_id: string;
  bucket_upvotes: number;
}

interface PostTimeSeries {
  postId: string;
  buckets: number[]; // upvote count per 1-minute bucket, oldest first
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Query Analytics Engine for recent upvote time-series
    const query = `
      SELECT
        toStartOfInterval(timestamp, INTERVAL '1' MINUTE) AS minute_bucket,
        blob1 AS post_id,
        SUM(double1) AS bucket_upvotes
      FROM engagement_events
      WHERE timestamp >= NOW() - INTERVAL '2' HOUR
        AND double1 > 0
      GROUP BY minute_bucket, post_id
      ORDER BY post_id, minute_bucket
    `;

    const aeUrl = `https://api.cloudflare.com/client/v4/accounts/${env.ACCOUNT_ID}/analytics_engine/sql`;
    const aeResponse = await fetch(aeUrl, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.AE_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    });

    if (!aeResponse.ok) {
      console.error('Analytics Engine query failed', await aeResponse.text());
      return;
    }

    const data = await aeResponse.json<{ data: BucketRow[] }>();
    const seriesMap = groupByPost(data.data);

    for (const series of seriesMap.values()) {
      const anomalyScore = computeZScoreAnomaly(series.buckets);
      if (anomalyScore < 3.0) continue; // z-score below 3σ: normal variation

      // Confirm with AI classification
      const confirmed = await classifyWithAI(env, series);
      if (!confirmed) continue;

      await env.DB.prepare(`
        INSERT INTO post_flags (post_id, flag_type, confidence, detected_at)
        VALUES (?1, 'fake_engagement', ?2, unixepoch())
        ON CONFLICT(post_id, flag_type) DO UPDATE SET
          confidence  = MAX(excluded.confidence, post_flags.confidence),
          detected_at = unixepoch()
      `).bind(series.postId, Math.min(1.0, anomalyScore / 10)).run();

      // Suppress from ranking immediately
      await env.DB.prepare(`
        UPDATE post_engagement
        SET ranking_suppressed = 1
        WHERE post_id = ?1
      `).bind(series.postId).run();
    }
  },
};

function groupByPost(rows: BucketRow[]): Map<string, PostTimeSeries> {
  const map = new Map<string, PostTimeSeries>();
  for (const row of rows) {
    if (!map.has(row.post_id)) {
      map.set(row.post_id, { postId: row.post_id, buckets: [] });
    }
    map.get(row.post_id)!.buckets.push(row.bucket_upvotes);
  }
  return map;
}

function computeZScoreAnomaly(buckets: number[]): number {
  if (buckets.length < 10) return 0; // insufficient history

  // Use the first 80% of buckets as the baseline, last 20% as the observation window
  const splitAt = Math.floor(buckets.length * 0.8);
  const baseline = buckets.slice(0, splitAt);
  const recent = buckets.slice(splitAt);

  const mean = baseline.reduce((s, v) => s + v, 0) / baseline.length;
  const variance = baseline.reduce((s, v) => s + (v - mean) ** 2, 0) / baseline.length;
  const stddev = Math.sqrt(variance) || 1;

  const recentMean = recent.reduce((s, v) => s + v, 0) / recent.length;
  return (recentMean - mean) / stddev;
}

async function classifyWithAI(env: Env, series: PostTimeSeries): Promise<boolean> {
  // Describe the time-series as a text prompt for a zero-shot classification
  const description = `
Post engagement time series (upvotes per minute, last 2 hours):
${series.buckets.join(', ')}
Does this pattern indicate artificial vote manipulation (sudden spike followed by flatline)?
`.trim();

  try {
    const result = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      prompt: description,
      max_tokens: 10,
    }) as { response: string };

    const answer = result.response.toLowerCase();
    return answer.includes('yes') || answer.includes('artificial') || answer.includes('manipul');
  } catch {
    // AI unavailable — trust the z-score alone
    return true;
  }
}
```

## Ranking Suppression and Recovery

Posts flagged for fake engagement are excluded from trending and recommendation feeds immediately. A separate Worker runs recovery logic: if a post's engagement pattern normalises over the following hour (no further anomalous bursts), the suppression is lifted and the post is re-admitted to ranking with its organic vote count.

```typescript
// worker: suppression-recovery.ts (scheduled every 30 minutes)
export interface Env {
  DB: D1Database;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Find posts flagged more than 2 hours ago but not yet cleared
    const flagged = await env.DB.prepare(`
      SELECT pf.post_id
      FROM post_flags pf
      JOIN post_engagement pe ON pe.post_id = pf.post_id
      WHERE pf.flag_type = 'fake_engagement'
        AND pf.detected_at < unixepoch() - 7200
        AND pe.ranking_suppressed = 1
        AND pf.cleared_at IS NULL
    `).all<{ post_id: string }>();

    for (const row of flagged.results) {
      // Check that no new anomaly flag was set in the past 2 hours
      const recent = await env.DB.prepare(`
        SELECT COUNT(*) AS cnt
        FROM post_flags
        WHERE post_id = ?1
          AND flag_type = 'fake_engagement'
          AND detected_at > unixepoch() - 7200
          AND cleared_at IS NULL
      `).bind(row.post_id).first<{ cnt: number }>();

      if ((recent?.cnt ?? 1) > 0) continue;

      // Restore ranking, clear flag
      await env.DB.batch([
        env.DB.prepare(`
          UPDATE post_engagement SET ranking_suppressed = 0 WHERE post_id = ?1
        `).bind(row.post_id),
        env.DB.prepare(`
          UPDATE post_flags SET cleared_at = unixepoch()
          WHERE post_id = ?1 AND flag_type = 'fake_engagement'
        `).bind(row.post_id),
      ]);
    }
  },
};
```

## Anti-patterns

- Using a simple total-vote threshold to detect fake engagement — a post can legitimately go viral and receive thousands of votes quickly; the time-series shape (spike-then-plateau vs. organic growth curve) is the signal, not the absolute number
- Writing engagement counts directly to D1 on every vote — at example project scale, concurrent vote writes cause D1 write contention and row locking; use Analytics Engine for the hot write path and D1 only for aggregated counters updated on a short schedule
- Running the LLM classifier on every post — only invoke AI after the z-score pre-filter has already identified a statistical anomaly; this keeps AI costs proportional to actual suspect events
- Permanently suppressing a post without a recovery path — false-positive suppression with no appeal or automatic recovery damages creator trust and can cause legal exposure in jurisdictions with platform accountability laws
- Ignoring the ASN distribution of voting sessions — a burst of upvotes from a single ASN is a strong secondary signal that should increase anomaly score weight

## Gotchas

- Analytics Engine SQL API requires the `analytics_engine_read` permission token, separate from the main API token used by `wrangler`; store it as a Worker secret (`wrangler secret put AE_TOKEN`)
- `toStartOfInterval` in Analytics Engine SQL is not standard SQLite; it is ClickHouse-dialect and only available via the Analytics Engine SQL API endpoint, not via D1
- Workers AI LLM responses are non-deterministic; the `classifyWithAI` function uses a simple keyword match on the response — in production, use `@cf/meta/llama-3.1-8b-instruct` with a structured output schema or a `@cf/huggingface/distilbert-sst-2-int8` text-classification model for deterministic binary output
- Analytics Engine data can have up to 30 seconds of ingestion lag; anomaly detection runs every 5 minutes, so detections are at worst 5.5 minutes behind a burst — acceptable for engagement fraud but insufficient for real-time blocking (handle that with a Durable Object rate limiter instead)
- `ranking_suppressed` in D1 must be indexed on `post_engagement(ranking_suppressed, updated_at)` to avoid full table scans in the ranking query

## Verification

1. Insert synthetic Analytics Engine data via the REST API with a time series showing 2 upvotes/minute for 90 minutes then 150 upvotes in the 91st minute.
2. Trigger the scheduled `anomaly-detector` Worker manually via `wrangler dev --test-scheduled`.
3. Query D1 `post_flags` — expect a row with `flag_type = 'fake_engagement'` and `confidence > 0.8`.
4. Query `post_engagement` — expect `ranking_suppressed = 1`.
5. Advance detected_at by 3 hours in the test fixture and run `suppression-recovery` — expect `ranking_suppressed = 0` and `cleared_at` set.
6. Repeat with a legitimately viral pattern (linear growth to 500 votes over 2 hours) and confirm no flag is inserted.

## Related

- `engagement-bait-detection.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `platform-manipulation-brigading-detection.md`
- `recommendation-bias-detection-workers-ai-audit.md`

## Sources

- Cloudflare Analytics Engine documentation: https://developers.cloudflare.com/analytics/analytics-engine/
- Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
- DSA Article 37 systemic risk assessment obligations: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022R2065
