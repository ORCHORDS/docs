# pipelines-r2-ingest-etl

Using Cloudflare Pipelines to ingest, transform with SQL, and deliver streaming
events to R2 as Apache Iceberg tables or Parquet/JSON files. Pipelines is the
serverless streaming ingestion layer of the Cloudflare Data Platform — it
eliminates the need to run Kafka, Flink, or self-managed ETL infrastructure.

## Symptom

You need to collect high-volume event streams (clicks, logs, IoT telemetry,
analytics events) and land them in R2 for querying, but every existing path
has a painful trade-off:

- **Workers writing directly to R2**: works, but you must handle batching,
  retries, and file format conversion yourself. Your Worker becomes 200 lines
  of plumbing code for what should be one config line.
- **Workers Analytics Engine**: great for metrics, but you can't run SQL
  analytics or export to data warehouse tools.
- **External ETL (Kafka + Flink)**: powerful but expensive and complex to
  operate. You're managing infrastructure instead of building product.

The missing piece: a serverless pipeline that takes events in, transforms them
with SQL, and writes query-ready Iceberg/Parquet files to R2 automatically.

```text
Without Pipelines:
  Worker → custom batching logic → R2 PUT (raw JSON dumps)
  Then:  R2 → download → Python/Spark job → Parquet → re-upload → query
  (6 moving parts, 2 failure modes, zero SQL at ingest time)

With Pipelines:
  Worker → Pipeline (SQL transform) → R2 Iceberg table → query directly
  (1 config block, 0 custom ETL code)
```

## Background: What Pipelines does

Cloudflare Pipelines is a streaming ingestion service. It accepts events via
HTTP or Workers binding, applies SQL transformations, and delivers the output
to R2 in analytics-ready formats.

```text
┌──────────┐     ┌──────────────────┐     ┌─────────────┐
│  Worker   │────→│   Pipeline        │────→│  R2 Bucket  │
│ (source)  │     │  SQL transform    │     │ Iceberg/    │
└──────────┘     │  + batching       │     │ Parquet/JSON│
                  │  + delivery       │     └──────┬──────┘
┌──────────┐     └──────────────────┘            │
│ HTTP POST│────→│                                  │
│ (source)  │     │                                  ↓
└──────────┘     │                           ┌──────────────┐
                  └──────────────────────────→│ R2 Data      │
                                              │ Catalog      │
                                              │ (query with  │
                                              │  any tool)   │
                                              └──────────────┘
```

Key properties:
- **Zero egress fees** (R2's defining advantage carries through)
- **SQL transformations at ingest time** (filter, aggregate, enrich before storage)
- **Apache Iceberg output** (queryable by Spark, Trino, DuckDB, Athena, etc.)
- **Stateful transformations** coming via Arroyo acquisition (2025)

## Solution: Set up a Pipeline

### Step 1: Create a Pipeline via Wrangler

```bash
npx wrangler pipelines create my-events-pipeline \
  --destination-r2-bucket my-data-bucket \
  --format iceberg
```

### Step 2: Bind the Pipeline to your Worker

```toml
# wrangler.toml
[[pipelines]]
binding = "MY_PIPELINE"
pipeline = "my-events-pipeline"
```

### Step 3: Send events from a Worker

```typescript
interface Env {
  MY_PIPELINE: Pipeline;
}

interface AnalyticsEvent {
  event: string;
  userId: string;
  timestamp: number;
  properties: Record<string, unknown>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const event: AnalyticsEvent = await request.json();

    // Send event to the Pipeline — it handles batching, SQL transform, R2 delivery
    await env.MY_PIPELINE.send(event);

    return Response.json({ ok: true });
  },
};
```

### Step 4: Send events via HTTP (no Worker needed)

```bash
# Events can also be posted directly to the Pipeline endpoint
curl -X POST https://pipelines.cloudflare.com/accounts/{account_id}/pipelines/my-events-pipeline/events \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"event":"page_view","userId":"u123","timestamp":1697000000,"properties":{"path":"/home"}}'
```

### Step 5: Apply SQL transformations at ingest

```bash
# Define a SQL transform that filters, projects, and enriches before storage
npx wrangler pipelines update my-events-pipeline \
  --transform "SELECT event, userId, timestamp, properties.page AS page, properties.referrer AS referrer FROM input WHERE event IS NOT NULL"
```

This SQL runs on every batch before it's written to R2 — so your stored
data is already clean, filtered, and in the right shape for analytics.

## Use case: Logpush → Pipelines → R2

Cloudflare's own access logs can be routed through Pipelines:

```bash
# Enable Pipelines as a Logpush destination
npx wrangler logpush create \
  --destination-type pipelines \
  --pipeline my-logs-pipeline
```

Now HTTP request logs (with 100+ fields) flow through SQL transform and land
as Iceberg tables in R2 — queryable without any external warehouse.

## Gotchas

- **Pipelines is not real-time in the sub-second sense.** It's micro-batch:
  events are buffered and flushed periodically (seconds to minutes depending
  on volume). If you need <1s latency, use Workers Analytics Engine or
  Durable Objects instead.
- **Iceberg tables need a catalog.** R2 Data Catalog manages Iceberg table
  metadata. Without it, you get Parquet files (still queryable but without
  Iceberg's snapshot/transaction semantics). Enable the catalog explicitly.
- **SQL transforms must be deterministic and stateless (for now).** The
  current transform engine applies SQL per-batch. Cross-batch stateful
  operations (sessionization, windowed joins) require the Arroyo-powered
  stateful engine — check GA status before relying on it.
- **Schema evolution is your responsibility.** If you add a new field to
  events, old Parquet files won't have it. Iceberg handles schema evolution
  better than raw Parquet — another reason to prefer Iceberg format.
- **R2 bucket must exist before Pipeline creation.** The Pipeline doesn't
  create the bucket for you. Create it first:
  `npx wrangler r2 bucket create my-data-bucket`.
- **No backpressure signaling to the caller.** `pipeline.send()` returns
  quickly (it buffers), so your Worker won't know if the downstream is
  overwhelmed. If Pipelines is degraded, events may be dropped silently.
  Monitor Pipeline ingestion metrics.
- **Cost model is ingestion-volume based.** You pay per event ingested and
  per GB stored in R2. For very high-volume event streams (billions/day),
  estimate costs carefully — aggregation at the Worker level before sending
  can dramatically reduce ingest cost.
- **Pipelines is newer than the rest of the platform.** APIs and config
  syntax may change. Pin your Wrangler version and check the changelog
  before upgrading in production.
- **Don't confuse Pipelines with Workers Analytics Engine.** Analytics Engine
  is for time-series metrics (counters, gauges). Pipelines is for structured
  event data landing in R2. Use Analytics Engine for dashboards; use
  Pipelines for data lake / warehouse workloads.

## When to use Pipelines vs. alternatives

| Need                          | Use                         |
|-------------------------------|-----------------------------|
| Event stream → R2 data lake   | **Pipelines**               |
| Simple metrics counters       | Workers Analytics Engine    |
| Real-time alerting on events  | Queues + Worker consumer    |
| Structured logs → warehouse   | Logpush → Pipelines         |
| Ad-hoc R2 file queries        | R2 Data Catalog + DuckDB    |

## Sources

- [Cloudflare Pipelines — Docs](https://developers.cloudflare.com/pipelines/)
- [Announcing the Cloudflare Data Platform — Blog](https://blog.cloudflare.com/cloudflare-data-platform/)
- [R2 Data Catalog — Docs](https://developers.cloudflare.com/r2/data-catalog/)
