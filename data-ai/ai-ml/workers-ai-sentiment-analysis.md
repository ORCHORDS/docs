# Workers AI — Sentiment Analysis Pipeline with Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to score the sentiment of user reviews, support comments, and social mentions in real time, track sentiment trends over time, fire alerts when sentiment drops suddenly (indicating a product incident or PR crisis), and correlate sentiment with A/B test variants to measure feature impact on user satisfaction.

---

## Context

Cloudflare Workers AI includes `@cf/huggingface/distilbert-sst-2-int8`, a quantized DistilBERT model fine-tuned on the Stanford Sentiment Treebank (SST-2). It classifies text as POSITIVE or NEGATIVE with a probability score. For more granular sentiment (1–5 stars) or topic-level sentiment, a text-generation model can return structured scores.

Sentiment data is written to **Workers Analytics Engine** (a time-series data points API) for trend queries via the Cloudflare GraphQL Analytics API. Sudden-drop detection uses a Cloudflare **Cron Trigger** that queries the last 30 minutes and compares to a 7-day baseline.

---

## Solution

```typescript
export interface Env {
  AI: Ai;
  SENTIMENT_DATASET: AnalyticsEngineDataset;
  DB: D1Database;
  ALERT_WEBHOOK_URL: string; // set via wrangler secret
}

// ── Types ────────────────────────────────────────────────────────────────────

interface SentimentScore {
  label: 'POSITIVE' | 'NEGATIVE';
  score: number;       // 0–1 probability for the winning label
  normalised: number;  // -1 to +1: POSITIVE → score, NEGATIVE → -score
}

interface ReviewEvent {
  reviewId: string;
  text: string;
  entityId: string;    // product ID, page slug, A/B variant, etc.
  sessionId?: string;
  abVariant?: string;
}

// ── 1. DistilBERT sentiment scoring ──────────────────────────────────────────

async function scoreSentiment(
  ai: Ai,
  text: string,
): Promise<SentimentScore> {
  // DistilBERT SST-2 accepts up to 512 tokens; truncate at ~1800 chars
  const truncated = text.slice(0, 1800);

  const result = await ai.run('@cf/huggingface/distilbert-sst-2-int8', {
    text: truncated,
  });

  // Result: Array<{ label: string; score: number }> sorted desc by score
  const classifications = result as Array<{ label: string; score: number }>;
  const top = classifications[0];

  const label = top.label as 'POSITIVE' | 'NEGATIVE';
  const normalised = label === 'POSITIVE' ? top.score : -top.score;

  return { label, score: top.score, normalised };
}

// ── 2. Fine-grained scoring with LLM (optional upgrade path) ─────────────────

interface DetailedSentiment {
  overall: number;          // -1 to +1
  aspects: Record<string, number>; // { pricing: 0.8, support: -0.3, quality: 0.6 }
  emotions: string[];       // ['frustrated', 'satisfied']
}

async function scoreDetailedSentiment(
  ai: Ai,
  text: string,
  aspects: string[],
): Promise<DetailedSentiment> {
  const result = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      {
        role: 'system',
        content: `You are a sentiment analysis engine. Return ONLY valid JSON with this schema:
{
  "overall": <number -1 to 1>,
  "aspects": { ${aspects.map((a) => `"${a}": <number -1 to 1>`).join(', ')} },
  "emotions": [<string>, ...]
}
No markdown, no explanation.`,
      },
      { role: 'user', content: text.slice(0, 1500) },
    ],
    response_format: { type: 'json_object' },
    max_tokens: 256,
    temperature: 0.1,
  });

  try {
    const parsed = JSON.parse((result as { response: string }).response.trim());
    return parsed as DetailedSentiment;
  } catch {
    return { overall: 0, aspects: {}, emotions: [] };
  }
}

// ── 3. Write to Analytics Engine ─────────────────────────────────────────────

function writeSentimentEvent(
  dataset: AnalyticsEngineDataset,
  event: ReviewEvent,
  sentiment: SentimentScore,
): void {
  dataset.writeDataPoint({
    // blobs: string dimensions for GROUP BY in GraphQL queries
    blobs: [
      event.entityId,              // blob1: product/page identifier
      sentiment.label,             // blob2: POSITIVE | NEGATIVE
      event.abVariant ?? 'none',  // blob3: A/B variant
      event.reviewId,              // blob4: review ID for dedup
    ],
    // doubles: numeric metrics
    doubles: [
      sentiment.normalised,        // double1: -1 to +1 sentiment score
      sentiment.score,             // double2: confidence (0-1)
      1,                           // double3: event count for aggregation
    ],
    indexes: [event.entityId],    // index1: partition key for fast queries
  });
}

// ── 4. Store in D1 for individual review history ──────────────────────────────

async function persistReviewSentiment(
  db: D1Database,
  event: ReviewEvent,
  sentiment: SentimentScore,
): Promise<void> {
  await db.prepare(
    `INSERT OR REPLACE INTO review_sentiments
       (review_id, entity_id, ab_variant, label, score, normalised, analysed_at)
     VALUES (?, ?, ?, ?, ?, ?, datetime('now'))`,
  )
    .bind(
      event.reviewId,
      event.entityId,
      event.abVariant ?? null,
      sentiment.label,
      sentiment.score,
      sentiment.normalised,
    )
    .run();
}

// ── 5. Sudden-drop detection (called from Cron Trigger) ──────────────────────

// Queries Analytics Engine via the Cloudflare GraphQL API
async function getSentimentAverage(
  accountId: string,
  apiToken: string,
  entityId: string,
  minutesBack: number,
): Promise<number | null> {
  const query = `
    query SentimentAvg($accountId: string!, $since: Time!, $entityId: string!) {
      viewer {
        accounts(filter: { accountTag: $accountId }) {
          sentimentData: workersAnalyticsEngineAdaptiveGroups(
            dataset: "SENTIMENT_DATASET"
            filter: {
              datetime_gt: $since
              blob1: $entityId
            }
            limit: 1
          ) {
            avg { double1 }
            count
          }
        }
      }
    }`;

  const since = new Date(Date.now() - minutesBack * 60 * 1000).toISOString();

  const response = await fetch('https://api.cloudflare.com/client/v4/graphql', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, variables: { accountId, since, entityId } }),
  });

  const json = await response.json<{ data: { viewer: { accounts: Array<{ sentimentData: Array<{ avg: { double1: number }; count: number }> }> } } }>();
  const groups = json.data?.viewer?.accounts?.[0]?.sentimentData ?? [];
  if (!groups.length || groups[0].count === 0) return null;
  return groups[0].avg.double1;
}

async function checkSentimentDrop(
  env: Env & { ACCOUNT_ID: string; CF_API_TOKEN: string },
  entityId: string,
): Promise<void> {
  const recent = await getSentimentAverage(env.ACCOUNT_ID, env.CF_API_TOKEN, entityId, 30);
  const baseline = await getSentimentAverage(env.ACCOUNT_ID, env.CF_API_TOKEN, entityId, 60 * 24 * 7);

  if (recent === null || baseline === null) return;

  const DROP_THRESHOLD = 0.25; // alert if recent avg drops > 0.25 below baseline
  const drop = baseline - recent;

  if (drop > DROP_THRESHOLD) {
    console.warn(`Sentiment drop detected for ${entityId}: baseline=${baseline.toFixed(3)}, recent=${recent.toFixed(3)}, drop=${drop.toFixed(3)}`);

    await fetch(env.ALERT_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        alert: 'sentiment_drop',
        entityId,
        baseline: baseline.toFixed(3),
        recent: recent.toFixed(3),
        drop: drop.toFixed(3),
        timestamp: new Date().toISOString(),
      }),
    });
  }
}

// ── 6. A/B test sentiment comparison ─────────────────────────────────────────

async function compareAbVariants(
  db: D1Database,
  entityId: string,
  sinceHours: number = 24,
): Promise<Record<string, { avg: number; count: number }>> {
  const rows = await db.prepare(
    `SELECT ab_variant, AVG(normalised) as avg_sentiment, COUNT(*) as review_count
     FROM review_sentiments
     WHERE entity_id = ?
       AND ab_variant IS NOT NULL
       AND analysed_at >= datetime('now', ?)
     GROUP BY ab_variant`,
  )
    .bind(entityId, `-${sinceHours} hours`)
    .all<{ ab_variant: string; avg_sentiment: number; review_count: number }>();

  return Object.fromEntries(
    rows.results.map((r) => [
      r.ab_variant,
      { avg: r.avg_sentiment, count: r.review_count },
    ]),
  );
}

// ── 7. Worker entry point ─────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /sentiment — score a single review
    if (url.pathname === '/sentiment' && request.method === 'POST') {
      const event = await request.json<ReviewEvent>();

      if (!event.text || event.text.trim().length < 3) {
        return Response.json({ ok: false, error: 'text too short' }, { status: 400 });
      }

      const sentiment = await scoreSentiment(env.AI, event.text);

      // Fire-and-forget: write to Analytics Engine and D1
      writeSentimentEvent(env.SENTIMENT_DATASET, event, sentiment);
      await persistReviewSentiment(env.DB, event, sentiment);

      return Response.json({ ok: true, ...sentiment });
    }

    // GET /sentiment/trend?entityId=...&hours=24
    if (url.pathname === '/sentiment/trend' && request.method === 'GET') {
      const entityId = url.searchParams.get('entityId');
      const hours = parseInt(url.searchParams.get('hours') ?? '24', 10);

      if (!entityId) return new Response('Missing entityId', { status: 400 });

      const rows = await env.DB.prepare(
        `SELECT
           strftime('%Y-%m-%dT%H:00:00', analysed_at) as hour,
           AVG(normalised) as avg_sentiment,
           COUNT(*) as review_count
         FROM review_sentiments
         WHERE entity_id = ? AND analysed_at >= datetime('now', ?)
         GROUP BY hour
         ORDER BY hour ASC`,
      )
        .bind(entityId, `-${hours} hours`)
        .all<{ hour: string; avg_sentiment: number; review_count: number }>();

      return Response.json({ ok: true, trend: rows.results });
    }

    // GET /sentiment/ab?entityId=...&hours=24
    if (url.pathname === '/sentiment/ab' && request.method === 'GET') {
      const entityId = url.searchParams.get('entityId');
      const hours = parseInt(url.searchParams.get('hours') ?? '24', 10);

      if (!entityId) return new Response('Missing entityId', { status: 400 });

      const comparison = await compareAbVariants(env.DB, entityId, hours);
      return Response.json({ ok: true, variants: comparison });
    }

    return new Response('Not found', { status: 404 });
  },

  // Cron trigger: runs every 15 minutes to check for sentiment drops
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const WATCHED_ENTITIES = ['product-homepage', 'checkout-flow', 'pricing-page'];
    const envWithSecrets = env as Env & { ACCOUNT_ID: string; CF_API_TOKEN: string };

    for (const entityId of WATCHED_ENTITIES) {
      await checkSentimentDrop(envWithSecrets, entityId);
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

**DistilBERT SST-2** — Binary (POSITIVE/NEGATIVE) classifier. The model returns all class probabilities; the first element is the highest-score class. Convert to a -1/+1 scale by negating NEGATIVE scores for arithmetic averaging and threshold comparisons.

**Analytics Engine data points** — `writeDataPoint` is synchronous in the API but committed asynchronously; it never fails the outer request. Use up to 20 blobs (string dimensions), 20 doubles (metrics), and 1 index (partition key). The index field powers efficient `filter` in GraphQL queries.

**Trend query in D1** — `strftime('%Y-%m-%dT%H:00:00', analysed_at)` buckets records hourly. For finer granularity (5-minute buckets), use `strftime('%Y-%m-%dT%H:%M', analysed_at, 'start of minute', '-' || (strftime('%M', analysed_at) % 5) || ' minutes')`.

**A/B sentiment** — Tag each review with its A/B variant at ingestion time. The `compareAbVariants` query gives an average normalised score per variant over a time window. A difference of > 0.1 is typically statistically significant with N > 200 reviews per variant.

**Alert threshold** — The 0.25 drop threshold on a -1/+1 scale is equivalent to moving from "mostly positive" (0.6) to "mixed" (0.35). Tune per entity; product pages may need tighter thresholds than marketing pages.

**Cron trigger** — Declared in `wrangler.toml` as `[triggers] crons = ["*/15 * * * *"]`. The `scheduled` export handler runs without an incoming HTTP request. Keep execution under 10s to avoid timeout.

---

## Anti-patterns

- **Scoring sentiment on text shorter than 3 words** — Results are unreliable; return neutral (0) for very short inputs.
- **Using sentiment scores as the sole content moderation signal** — Negative sentiment ≠ harmful content. Use the dedicated moderation pipeline for safety decisions.
- **Querying D1 for real-time trend dashboards at high frequency** — D1 is not a time-series database. Use Analytics Engine GraphQL for aggregate trend queries; D1 for per-review lookups and A/B comparisons.
- **Blocking the request on `writeDataPoint`** — The call is fire-and-forget; do not `await` it inside the request path or it adds no latency benefit over a regular write.
- **Alerting on a single 15-minute drop** — Require two consecutive drop intervals before paging, to avoid alert fatigue from statistical noise.

---

## Gotchas

- `@cf/huggingface/distilbert-sst-2-int8` only classifies into POSITIVE/NEGATIVE. For 5-star sentiment or aspect-based sentiment analysis, fall through to the LLM path.
- Analytics Engine has a maximum of 25 data points per `fetch()` invocation across all `writeDataPoint` calls. Batch reviews via Queues if processing more than 25 in a single Worker invocation.
- The Cloudflare GraphQL Analytics API requires a `Zone:Analytics:Read` scoped API token, not the Worker's own token. Store it as a Worker secret (`ALERT_WEBHOOK_URL` pattern above).
- D1 `AVG()` returns `null` for empty result sets, not `0`. Guard with `?? 0` when computing differences.
- SST-2 model scores near 0.5 (e.g., 0.52 POSITIVE) indicate genuinely ambiguous text; treat as neutral rather than weakly positive.

---

## Verification

```bash
# Enable Analytics Engine in wrangler.toml
# [[analytics_engine_datasets]]
# binding = "SENTIMENT_DATASET"
# dataset = "sentiment_events"

npx wrangler deploy

# Score a positive review
curl -X POST https://your-worker.workers.dev/sentiment \
  -H 'Content-Type: application/json' \
  -d '{"reviewId":"r1","text":"Absolutely love this product, best purchase ever!","entityId":"product-homepage","abVariant":"A"}'
# Expected: { ok: true, label: "POSITIVE", score: 0.999, normalised: 0.999 }

# Score a negative review
curl -X POST https://your-worker.workers.dev/sentiment \
  -H 'Content-Type: application/json' \
  -d '{"reviewId":"r2","text":"Terrible experience, broken on arrival and support ignored me.","entityId":"product-homepage","abVariant":"B"}'
# Expected: { ok: true, label: "NEGATIVE", score: 0.998, normalised: -0.998 }

# Get hourly trend
curl 'https://your-worker.workers.dev/sentiment/trend?entityId=product-homepage&hours=48'

# Compare A/B variants
curl 'https://your-worker.workers.dev/sentiment/ab?entityId=product-homepage&hours=24'
# Expected: { ok: true, variants: { A: { avg: 0.76, count: 142 }, B: { avg: 0.54, count: 138 } } }
```

```toml
# wrangler.toml additions
[[analytics_engine_datasets]]
binding = "SENTIMENT_DATASET"
dataset = "sentiment_events"

[triggers]
crons = ["*/15 * * * *"]
```

```sql
-- D1 schema
CREATE TABLE IF NOT EXISTS review_sentiments (
  review_id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL,
  ab_variant TEXT,
  label TEXT NOT NULL CHECK(label IN ('POSITIVE', 'NEGATIVE')),
  score REAL NOT NULL,
  normalised REAL NOT NULL,
  analysed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rs_entity_time ON review_sentiments(entity_id, analysed_at);
CREATE INDEX IF NOT EXISTS idx_rs_ab ON review_sentiments(entity_id, ab_variant, analysed_at);
```

---

## Related

- `documentation/categories/ai-ml/workers-ai-content-moderation.md` — combining sentiment with safety classification
- `documentation/categories/ai-ml/workers-ai-structured-output.md` — detailed aspect-based sentiment via LLM JSON mode
- `documentation/categories/ai-ml/workers-ai-rag-pipeline.md` — retrieving sentiment context for personalization
- [Cloudflare Analytics Engine documentation](https://developers.cloudflare.com/analytics/analytics-engine/)
- [DistilBERT SST-2 model card](https://huggingface.co/distilbert-base-uncased-finetuned-sst-2-english)
- [Workers Analytics Engine GraphQL schema](https://developers.cloudflare.com/analytics/graphql-api/)

---

## Sources

- Cloudflare Workers AI model catalog, August 2026
- Cloudflare Analytics Engine documentation
- SST-2 benchmark, Stanford NLP Group
- Cloudflare D1 documentation
- Internal example.com review analytics pipeline, production since 2025-Q1
