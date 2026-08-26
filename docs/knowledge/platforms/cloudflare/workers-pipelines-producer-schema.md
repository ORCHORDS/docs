# Workers Pipelines — Producer Patterns with Schema Enforcement

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need a high-throughput event ingestion path where a Workers fetch handler writes structured records to Cloudflare Pipelines, the records are validated against a schema before ingestion, and the pipeline delivers them to R2 (or an HTTP endpoint) in micro-batches without you managing queues or consumers. Dropped or malformed records should be captured separately rather than silently discarded.

## Context

Cloudflare Pipelines is a fully managed event streaming product. A Worker binds to a Pipeline and writes records via the `pipeline.send()` method. Cloudflare buffers records, applies micro-batching (up to 100 MB or 100 000 records per batch), and delivers to the configured sink — R2 or an HTTP endpoint. Unlike Queues, Pipelines are append-only and optimised for high write throughput with no per-message acknowledgement. The Worker is the producer; the sink is the consumer. Schema enforcement must happen in the Worker because Pipelines does not validate record shape.

## Binding Declaration

```toml
# wrangler.toml
name = "event-ingest"
compatibility_date = "2025-09-01"

[[pipelines]]
binding = "EVENTS_PIPELINE"
pipeline = "prod-events"
```

## Schema Validation and Write

```typescript
import type { Pipeline } from "@cloudflare/workers-types";

export interface Env {
  EVENTS_PIPELINE: Pipeline;
  DLQ_PIPELINE: Pipeline;    // Dead-letter pipeline for rejected records
}

// The canonical event shape your pipeline expects
interface ClickEvent {
  type: "click";
  sessionId: string;
  userId: string | null;
  url: string;
  elementId: string;
  ts: number;
}

interface PageViewEvent {
  type: "pageview";
  sessionId: string;
  userId: string | null;
  url: string;
  referrer: string;
  ts: number;
}

type AppEvent = ClickEvent | PageViewEvent;

function validateEvent(raw: unknown): AppEvent | null {
  if (typeof raw !== "object" || raw === null) return null;
  const obj = raw as Record<string, unknown>;

  if (typeof obj["type"] !== "string") return null;
  if (typeof obj["sessionId"] !== "string" || obj["sessionId"].length === 0) return null;
  if (typeof obj["url"] !== "string") return null;
  if (typeof obj["ts"] !== "number" || obj["ts"] <= 0) return null;

  switch (obj["type"]) {
    case "click":
      if (typeof obj["elementId"] !== "string") return null;
      return {
        type: "click",
        sessionId: obj["sessionId"] as string,
        userId: typeof obj["userId"] === "string" ? obj["userId"] : null,
        url: obj["url"] as string,
        elementId: obj["elementId"] as string,
        ts: obj["ts"] as number,
      };
    case "pageview":
      return {
        type: "pageview",
        sessionId: obj["sessionId"] as string,
        userId: typeof obj["userId"] === "string" ? obj["userId"] : null,
        url: obj["url"] as string,
        referrer: typeof obj["referrer"] === "string" ? (obj["referrer"] as string) : "",
        ts: obj["ts"] as number,
      };
    default:
      return null;
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/events") {
      return new Response("Not found", { status: 404 });
    }

    let rawBody: unknown;
    try {
      rawBody = await request.json();
    } catch {
      return Response.json({ error: "Invalid JSON" }, { status: 400 });
    }

    // Accept a batch (array) or a single event
    const rawEvents: unknown[] = Array.isArray(rawBody) ? rawBody : [rawBody];

    if (rawEvents.length === 0) {
      return Response.json({ error: "Empty batch" }, { status: 400 });
    }

    // Hard cap: Pipelines allows up to 1 000 records per send() call
    if (rawEvents.length > 1000) {
      return Response.json({ error: "Batch too large (max 1000)" }, { status: 413 });
    }

    const valid: AppEvent[] = [];
    const invalid: Array<{ index: number; raw: unknown }> = [];

    for (let i = 0; i < rawEvents.length; i++) {
      const event = validateEvent(rawEvents[i]);
      if (event) {
        valid.push(event);
      } else {
        invalid.push({ index: i, raw: rawEvents[i] });
      }
    }

    // Write valid events to the main pipeline
    if (valid.length > 0) {
      // pipeline.send() is non-blocking; use waitUntil so it completes after
      // the response is flushed
      ctx.waitUntil(env.EVENTS_PIPELINE.send(valid));
    }

    // Route invalid events to a DLQ pipeline for analysis
    if (invalid.length > 0) {
      const dlqRecords = invalid.map((item) => ({
        ts: Date.now(),
        index: item.index,
        raw: JSON.stringify(item.raw),
        source: request.cf?.asn ?? null,
      }));
      ctx.waitUntil(env.DLQ_PIPELINE.send(dlqRecords));
    }

    return Response.json({
      accepted: valid.length,
      rejected: invalid.length,
    });
  },
};
```

## Backpressure Handling for Burst Traffic

```typescript
// Pipelines batch internally but the Worker still has a 6 MB request body limit.
// For very high-throughput producers, split large arrays client-side.
// In the Worker, handle oversized payloads gracefully:

async function safeSend(
  pipeline: Pipeline,
  records: unknown[],
  ctx: ExecutionContext
): Promise<void> {
  const CHUNK_SIZE = 500; // stay well under the 1 000-record limit

  const chunks: unknown[][] = [];
  for (let i = 0; i < records.length; i += CHUNK_SIZE) {
    chunks.push(records.slice(i, i + CHUNK_SIZE));
  }

  for (const chunk of chunks) {
    // Each send() is fire-and-forget; Pipelines handles buffering
    ctx.waitUntil(pipeline.send(chunk));
  }
}
```

## Reading Pipeline Output from R2 (Sink Verification)

```typescript
// Pipelines writes Newline-Delimited JSON (NDJSON) files to R2.
// File naming: <pipeline>/<year>/<month>/<day>/<hour>/<uuid>.ndjson
// Use the R2 binding to verify delivery in an ops Worker:

import type { R2Bucket } from "@cloudflare/workers-types";

export interface SinkEnv {
  EVENTS_BUCKET: R2Bucket;
}

export async function listRecentPipelineFiles(
  env: SinkEnv,
  date: Date
): Promise<string[]> {
  const prefix = [
    "prod-events",
    date.getUTCFullYear(),
    String(date.getUTCMonth() + 1).padStart(2, "0"),
    String(date.getUTCDate()).padStart(2, "0"),
    String(date.getUTCHours()).padStart(2, "0"),
  ].join("/");

  const listed = await env.EVENTS_BUCKET.list({ prefix, limit: 100 });
  return listed.objects.map((o) => o.key);
}

export async function countRecordsInFile(
  env: SinkEnv,
  key: string
): Promise<number> {
  const obj = await env.EVENTS_BUCKET.get(key);
  if (!obj) return 0;
  const text = await obj.text();
  // NDJSON: one JSON record per line
  return text.split("\n").filter((line) => line.trim().length > 0).length;
}
```

## Anti-patterns

- Awaiting `pipeline.send()` without `ctx.waitUntil` — the Worker may be terminated before the send completes, silently dropping records.
- Sending records larger than 1 MB individually — Pipelines enforces a per-record size limit; compress large payloads or store them in R2 and send only the key.
- Using Pipelines for request-response workloads — Pipelines is append-only with no acknowledgement; use Queues when you need delivery confirmation or retries.

## Gotchas

- The `Pipeline` type is only available from `@cloudflare/workers-types` ≥ 4.20250801.0; older type packages expose the binding as `any`, making it easy to miss method signatures.
- Pipeline R2 output files are written in micro-batches on a schedule (not per-record); do not poll R2 expecting sub-second file appearance — the minimum flush interval is approximately 5 seconds under load.

## Verification

```bash
# Send a test batch via curl
curl -X POST "https://event-ingest.example.workers.dev/events" \
  -H "Content-Type: application/json" \
  -d '[{"type":"pageview","sessionId":"s1","url":"/home","referrer":"","ts":1753920000000}]'
# Expected: {"accepted":1,"rejected":0}

# Send an invalid record (missing ts)
curl -X POST "https://event-ingest.example.workers.dev/events" \
  -H "Content-Type: application/json" \
  -d '[{"type":"click","sessionId":"s1","url":"/home","elementId":"btn"}]'
# Expected: {"accepted":0,"rejected":1}

# List R2 output files after a few minutes
wrangler r2 object list prod-events-bucket --prefix "prod-events/$(date -u +%Y/%m/%d/%H)"
```

## Related

- `cloudflare/pipelines-r2-ingest-etl.md`
- `cloudflare/cloudflare-queues-dead-letter-dlq.md`
- `cloudflare/workers-analytics-engine.md`

## Sources

- https://developers.cloudflare.com/pipelines/
- https://developers.cloudflare.com/pipelines/get-started/
- https://developers.cloudflare.com/pipelines/reference/limits/
