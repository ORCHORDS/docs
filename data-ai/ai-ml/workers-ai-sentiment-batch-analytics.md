# Batch Sentiment Analysis with Workers AI and Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to score large volumes of text — customer reviews, support messages, social mentions — for sentiment without polling a third-party API per item. A Cloudflare Queue consumer processes batches using `@cf/huggingface/distilbert-sst-2-int8`, writes scores to Analytics Engine, and a SQL endpoint exposes per-entity average sentiment over rolling 7-day windows.

---

## Context

Producers enqueue `{text, entityId}` messages (e.g., a new review submitted to your product API). The Queue consumer receives up to 100 messages per batch invocation, calls Workers AI once per message (DistilBERT is fast — ~20 ms per inference), and writes a data point to Analytics Engine with `entityId` as a blob dimension and `score` as a double. Analytics Engine's SQL API (available at `https://api.cloudflare.com/client/v4/accounts/{id}/analytics_engine/sql`) allows aggregate queries over the ingested data. A scheduled Worker runs a daily digest by querying 7-day averages per entity and optionally emits alerts for entities whose average score drops below a threshold.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "sentiment-pipeline"
main = "src/index.ts"
compatibility_date = "2025-04-01"

[ai]
binding = "AI"

[[queues.consumers]]
queue = "sentiment-queue"
binding = "SENTIMENT_QUEUE"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 3

[[queues.producers]]
queue = "sentiment-queue"
binding = "SENTIMENT_QUEUE"

[analytics_engine_datasets]
binding = "ANALYTICS"
dataset = "sentiment_scores"

[vars]
CF_ACCOUNT_ID = "<your-account-id>"

[secrets]
# store CF_API_TOKEN via: wrangler secret put CF_API_TOKEN
```

---

## Section 2 — Queue Consumer and Analytics Writer

```typescript
// src/sentiment.ts
import type { Env } from "./index";

export interface SentimentMessage {
  text: string;
  entityId: string;
  timestamp?: number;
}

export interface SentimentScore {
  entityId: string;
  label: "POSITIVE" | "NEGATIVE";
  score: number; // 0-1 probability
  normalised: number; // -1 (negative) to +1 (positive)
}

const MODEL = "@cf/huggingface/distilbert-sst-2-int8";

export async function scoreSentiment(
  text: string,
  entityId: string,
  env: Env
): Promise<SentimentScore> {
  // DistilBERT SST-2 returns [{label, score}, ...] sorted by score descending
  const results = (await env.AI.run(MODEL, { text })) as Array<{
    label: string;
    score: number;
  }>;

  const top = results[0];
  const label = top.label.toUpperCase() as "POSITIVE" | "NEGATIVE";
  const score = top.score;

  // Normalise to [-1, +1] for easier aggregation
  const normalised = label === "POSITIVE" ? score : -score;

  return { entityId, label, score, normalised };
}

export function writeToAnalytics(
  result: SentimentScore,
  ts: number,
  env: Env
): void {
  // Analytics Engine writeDataPoint is fire-and-forget
  env.ANALYTICS.writeDataPoint({
    // blobs: categorical dimensions (indexed, filterable)
    blobs: [result.entityId, result.label],
    // doubles: numeric measurements
    doubles: [result.normalised, result.score],
    // indexes: high-cardinality field for shard routing
    indexes: [result.entityId],
  });
}

// src/index.ts
import { scoreSentiment, writeToAnalytics, type SentimentMessage } from "./sentiment";

export interface Env {
  AI: Ai;
  SENTIMENT_QUEUE: Queue<SentimentMessage>;
  ANALYTICS: AnalyticsEngineDataset;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
}

export default {
  // ---- HTTP: enqueue a message ----
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/enqueue") {
      const body = await request.json<SentimentMessage | SentimentMessage[]>();
      const messages = Array.isArray(body) ? body : [body];

      await env.SENTIMENT_QUEUE.sendBatch(
        messages.map((m) => ({ body: m, contentType: "json" }))
      );

      return Response.json({ queued: messages.length });
    }

    // ---- HTTP: query 7-day average sentiment per entity ----
    if (request.method === "GET" && url.pathname === "/sentiment/summary") {
      const entityId = url.searchParams.get("entityId");
      const summary = await querySentimentSummary(entityId, env);
      return Response.json(summary);
    }

    return new Response("Not found", { status: 404 });
  },

  // ---- Queue consumer ----
  async queue(
    batch: MessageBatch<SentimentMessage>,
    env: Env
  ): Promise<void> {
    const results = await Promise.allSettled(
      batch.messages.map(async (msg) => {
        const { text, entityId, timestamp } = msg.body;
        const ts = timestamp ?? Date.now();

        try {
          const result = await scoreSentiment(text, entityId, env);
          writeToAnalytics(result, ts, env);
          msg.ack();
        } catch (err) {
          console.error(`Failed to score ${entityId}:`, err);
          msg.retry();
        }
      })
    );

    const failed = results.filter((r) => r.status === "rejected").length;
    if (failed > 0) {
      console.warn(`${failed}/${batch.messages.length} messages failed`);
    }
  },

  // ---- Scheduled: daily digest ----
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const summary = await querySentimentSummary(null, env);
    const alerts = summary.filter(
      (row: { avg_sentiment: number; entity_id: string }) =>
        row.avg_sentiment < -0.3
    );
    if (alerts.length > 0) {
      console.log(
        "Sentiment alert — entities with negative avg:",
        JSON.stringify(alerts)
      );
      // Integrate with PagerDuty / Slack here
    }
  },
};

// ---- Analytics Engine SQL query helper ----
async function querySentimentSummary(
  entityId: string | null,
  env: Env
): Promise<unknown[]> {
  const whereClause = entityId
    ? `AND blob1 = '${entityId.replace(/'/g, "''")}'`
    : "";

  const sql = `
    SELECT
      blob1                          AS entity_id,
      avg(double1)                   AS avg_sentiment,
      count()                        AS sample_count,
      countIf(blob2 = 'POSITIVE')    AS positive_count,
      countIf(blob2 = 'NEGATIVE')    AS negative_count
    FROM sentiment_scores
    WHERE timestamp > now() - INTERVAL '7' DAY
    ${whereClause}
    GROUP BY blob1
    ORDER BY avg_sentiment ASC
    LIMIT 100
  `;

  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Analytics Engine query failed: ${err}`);
  }

  const json = (await response.json()) as { data: unknown[] };
  return json.data;
}
```

---

## Section 3 — Integration Test

```bash
# Deploy worker and queue
npx wrangler deploy

# Enqueue a batch of test messages
curl -sX POST https://sentiment-pipeline.<account>.workers.dev/enqueue \
  -H 'Content-Type: application/json' \
  -d '[
    {"text": "This product is absolutely fantastic!", "entityId": "product-42"},
    {"text": "Worst experience I have ever had.",       "entityId": "product-42"},
    {"text": "It is okay, nothing special.",           "entityId": "product-99"}
  ]' | jq .

# Wait ~10 s for queue consumer to process, then query
curl -s "https://sentiment-pipeline.<account>.workers.dev/sentiment/summary?entityId=product-42" | jq .

# Expected output shape:
# [{"entity_id":"product-42","avg_sentiment":0.12,"sample_count":2,...}]

# Query Analytics Engine SQL API directly
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/<account-id>/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query": "SELECT blob1, avg(double1) FROM sentiment_scores WHERE timestamp > now() - INTERVAL '\''7'\'' DAY GROUP BY blob1"}' \
  | jq .data
```

---

## Anti-patterns

- **Calling `env.AI.run` inside a `Promise.all` with unbounded concurrency** — Workers AI has per-account rate limits; limit concurrent inference calls or use `Promise.allSettled` with a concurrency cap.
- **Writing to Analytics Engine with more than 20 blobs or 20 doubles** — the limit is enforced at write time; excess fields are silently dropped rather than raising an error.
- **Querying the Analytics Engine SQL API from inside the Queue consumer** — queries can take seconds and will slow down your consumer throughput; separate read (HTTP handler / scheduled) from write (queue consumer) paths.
- **Storing raw sentiment text in Analytics Engine** — Analytics Engine is an append-only metric store, not a document store; keep text in D1 or R2 and reference it by ID.

---

## Gotchas

- Analytics Engine data has a ~1-minute ingestion lag before it appears in SQL queries; tests that enqueue and immediately query will return empty results.
- `blob1`...`blob20` and `double1`...`double20` are positional — document your schema (what each index means) since column names are not stored.
- DistilBERT SST-2 is trained on movie reviews; sentiment on technical support text may be less accurate — consider fine-tuning or using a domain-adapted model for critical applications.
- `msg.retry()` re-enqueues the message; if the failure is a permanent model error (e.g., input too long) you should `msg.ack()` and log to a dead-letter store instead to avoid infinite retries.

---

## Verification

```bash
# Confirm queue is configured
npx wrangler queues list

# Tail live queue consumer logs
npx wrangler tail --format pretty

# Check Analytics Engine dataset after ingestion
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/<account-id>/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query": "SELECT count() FROM sentiment_scores"}' | jq .data
```

---

## Related

- `workers-ai-image-classification-vision.md`
- `workers-ai-rag-chunking-vectorize.md`

---

## Sources

- Cloudflare DistilBERT SST-2 model card — https://developers.cloudflare.com/workers-ai/models/distilbert-sst-2-int8/
- Cloudflare Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
