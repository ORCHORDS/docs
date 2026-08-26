# Domain Event AI Enrichment Pipeline on Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Raw domain events — `OrderPlaced`, `ReviewSubmitted`, `SupportTicketCreated` — carry structured data but lack derived intelligence: sentiment scores, category labels, language tags, embedding vectors. Downstream consumers need these enrichments without coupling the source bounded context to AI inference logic or blocking the synchronous request path.

## Context

Cloudflare Workers AI provides inference at the edge with sub-100 ms latency for small models. By placing AI enrichment in an asynchronous pipeline between the event producer (D1 + Queues publisher) and event consumers, you avoid adding inference latency to user-facing writes. The enriched events are written back to D1 and re-published to a downstream Queue, enabling consumers to subscribe only to enriched events and never implement their own AI calls.

## Pipeline Architecture

```
Source Worker (write path)
  └─ INSERT domain event → D1 events table
  └─ publish raw event → "raw-events" Queue

Enrichment Worker (Queue consumer)
  ├─ batch.messages[] from "raw-events" Queue
  ├─ Workers AI: sentiment / embedding / classification
  ├─ UPDATE D1 events table with enrichment columns
  └─ publish enriched event → "enriched-events" Queue

Downstream Consumers
  └─ subscribe to "enriched-events" Queue
```

## D1 Schema

```sql
-- migrations/0001_events.sql
CREATE TABLE domain_events (
  id          TEXT PRIMARY KEY,
  type        TEXT NOT NULL,
  payload     TEXT NOT NULL,  -- JSON
  occurred_at TEXT NOT NULL,

  -- Enrichment columns (nullable until filled)
  sentiment      REAL,
  sentiment_label TEXT,
  embedding_id   TEXT,         -- reference to Vectorize index entry
  categories     TEXT,         -- JSON array of labels
  language       TEXT,
  enriched_at    TEXT
);

CREATE INDEX idx_events_type_occurred ON domain_events (type, occurred_at);
CREATE INDEX idx_events_enriched ON domain_events (enriched_at) WHERE enriched_at IS NULL;
```

## Source Worker: Publish Raw Events

```typescript
// src/source-worker.ts
interface Env {
  DB: D1Database;
  RAW_EVENTS: Queue<RawEvent>;
}

interface RawEvent {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  occurredAt: string;
}

function newEventId(): string {
  return crypto.randomUUID();
}

export async function publishDomainEvent(
  env: Env,
  type: string,
  payload: Record<string, unknown>
): Promise<string> {
  const event: RawEvent = {
    id: newEventId(),
    type,
    payload,
    occurredAt: new Date().toISOString(),
  };

  // Transactional write — event persisted before Queue message
  await env.DB.prepare(
    `INSERT INTO domain_events (id, type, payload, occurred_at)
     VALUES (?1, ?2, ?3, ?4)`
  )
    .bind(event.id, event.type, JSON.stringify(event.payload), event.occurredAt)
    .run();

  // Queue message carries minimal envelope — enrichment worker re-reads from D1
  await env.RAW_EVENTS.send(event);

  return event.id;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = (await request.json()) as {
      type: string;
      payload: Record<string, unknown>;
    };

    const id = await publishDomainEvent(env, body.type, body.payload);
    return Response.json({ id });
  },
};
```

## Enrichment Worker: Queue Consumer

```typescript
// src/enrichment-worker.ts
interface Env {
  DB: D1Database;
  AI: Ai;
  ENRICHED_EVENTS: Queue<EnrichedEvent>;
}

interface RawEvent {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  occurredAt: string;
}

interface EnrichedEvent extends RawEvent {
  sentiment: number;
  sentimentLabel: string;
  categories: string[];
  language: string;
  enrichedAt: string;
}

// Extract the text field most relevant for NLP from each event type
function extractText(event: RawEvent): string | null {
  const p = event.payload;
  switch (event.type) {
    case "ReviewSubmitted":
      return `${p.title ?? ""} ${p.body ?? ""}`.trim();
    case "SupportTicketCreated":
      return `${p.subject ?? ""} ${p.description ?? ""}`.trim();
    case "OrderPlaced":
      return null; // Structured — no free-text enrichment needed
    default:
      return typeof p.text === "string" ? p.text : null;
  }
}

async function enrichEvent(env: Env, event: RawEvent): Promise<EnrichedEvent | null> {
  const text = extractText(event);
  if (!text) return null;

  // Sentiment analysis
  const sentimentResult = await env.AI.run(
    "@cf/huggingface/distilbert-sst-2-int8",
    { text }
  ) as { label: string; score: number }[];

  const topSentiment = sentimentResult.sort((a, b) => b.score - a.score)[0];

  // Zero-shot classification
  const classResult = await env.AI.run(
    "@cf/facebook/bart-large-mnli",
    {
      text,
      candidate_labels: ["billing", "technical", "feedback", "general", "urgent"],
    }
  ) as { labels: string[]; scores: number[] };

  // Language detection via translation model (as a proxy)
  // Production: use a dedicated langdetect model
  const topCategories = classResult.labels
    .map((label, i) => ({ label, score: classResult.scores[i] }))
    .filter((c) => c.score > 0.15)
    .map((c) => c.label);

  return {
    ...event,
    sentiment: topSentiment.score,
    sentimentLabel: topSentiment.label.toLowerCase(),
    categories: topCategories,
    language: "en", // simplified; replace with langdetect
    enrichedAt: new Date().toISOString(),
  };
}

export default {
  async queue(batch: MessageBatch<RawEvent>, env: Env): Promise<void> {
    const enriched: EnrichedEvent[] = [];

    for (const msg of batch.messages) {
      const event = msg.body;
      try {
        const result = await enrichEvent(env, event);
        if (result) {
          enriched.push(result);
        }
        msg.ack();
      } catch (err) {
        console.error(`Enrichment failed for event ${event.id}:`, err);
        msg.retry({ delaySeconds: 30 });
      }
    }

    if (enriched.length === 0) return;

    // Batch update D1
    const stmts = enriched.map((e) =>
      env.DB.prepare(
        `UPDATE domain_events
         SET sentiment = ?1, sentiment_label = ?2,
             categories = ?3, language = ?4, enriched_at = ?5
         WHERE id = ?6`
      ).bind(
        e.sentiment,
        e.sentimentLabel,
        JSON.stringify(e.categories),
        e.language,
        e.enrichedAt,
        e.id
      )
    );

    await env.DB.batch(stmts);

    // Publish enriched events downstream
    await Promise.all(
      enriched.map((e) => env.ENRICHED_EVENTS.send(e))
    );
  },
};
```

## wrangler.toml

```toml
name = "event-enrichment"
main = "src/enrichment-worker.ts"
compatibility_date = "2024-09-23"

[ai]
binding = "AI"

[[d1_databases]]
binding = "DB"
database_name = "events-db"
database_id = "YOUR_D1_ID"

[[queues.consumers]]
queue = "raw-events"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "raw-events-dlq"

[[queues.producers]]
binding = "ENRICHED_EVENTS"
queue = "enriched-events"
```

## Idempotency and Re-enrichment

Re-delivery of a Queue message must not double-enrich. Check `enriched_at` before running inference:

```typescript
async function isAlreadyEnriched(env: Env, eventId: string): Promise<boolean> {
  const row = await env.DB.prepare(
    "SELECT enriched_at FROM domain_events WHERE id = ?1"
  )
    .bind(eventId)
    .first<{ enriched_at: string | null }>();
  return row?.enriched_at != null;
}
```

Call this at the top of the `queue` handler and `msg.ack()` early if already enriched.

## Anti-patterns

- **Enriching in the synchronous write path** — AI inference adds 50–500 ms; the user's request should return immediately; always enrich asynchronously via Queues.
- **Calling AI once per message when batching is available** — Workers AI supports batched inputs for embedding models; group text inputs per batch to reduce round-trips.
- **Storing embeddings in D1 TEXT columns** — large float arrays degrade D1 query performance; store them in Vectorize and keep only the Vectorize entry ID in D1.
- **Not handling AI model errors distinctly from retryable errors** — model overload returns 429 (retry with backoff); invalid input returns 400 (dead-letter immediately).
- **Enriching all event types regardless of text content** — structured events like `PaymentProcessed` carry no natural-language content; skip them at the `extractText` stage.

## Gotchas

- Workers AI requests count against your AI Gateway quota; high-volume pipelines should route through AI Gateway for rate-limit visibility and caching.
- `@cf/huggingface/distilbert-sst-2-int8` is an INT8-quantized model; scores near 0.5 are ambiguous and should be labeled "neutral" rather than "positive" or "negative".
- `batch.messages` order is not guaranteed to match D1 insertion order; never assume sequence for downstream projections.
- D1 `batch()` is atomic per call but not across multiple `batch()` calls; if the Worker crashes mid-loop some D1 rows are updated while others are not — rely on idempotency checks rather than transaction semantics.
- Workers AI cold-start for large models can exceed 500 ms; keep `max_batch_timeout` high enough (≥5 s) to amortize across the batch.

## Verification

1. POST a `ReviewSubmitted` event and record the returned `id`.
2. Poll `SELECT sentiment, categories, enriched_at FROM domain_events WHERE id = '...'` until `enriched_at` is non-null.
3. Verify `sentiment_label` is "positive" or "negative" and `categories` is a non-empty JSON array.
4. Re-send the same Queue message ID; confirm D1 row is not overwritten (idempotency check passes).
5. Check `wrangler tail enrichment-worker` for any retry or DLQ routing.

## Related

- `event-driven-architecture-overview.md`
- `event-sourcing-d1-append-only-store.md`
- `command-pattern-workers-queues-async-processing.md`
- `workers-tail-handlers-observability.md`
- `cqrs-cloudflare-workers-d1.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
