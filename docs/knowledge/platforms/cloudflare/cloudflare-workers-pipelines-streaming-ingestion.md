# Cloudflare Workers Pipelines Streaming Ingestion

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project / example.com generates high-frequency behavioral events — post views, reaction presses, scroll depth, and anonymous session signals — that must be ingested durably at the edge before being aggregated for the recommendation engine. Sending each event synchronously to a D1 write risks back-pressure and latency spikes on the hot path. Cloudflare Pipelines provides a managed, buffered HTTP ingestion layer that batches events and writes them to R2 as Parquet-compatible newline-delimited JSON, without a separate queue worker.

## Context
Cloudflare Pipelines (GA 2025) is a fully managed streaming ingestion service built on top of Workers and R2. A Pipeline exposes an HTTP source endpoint and a Workers binding (`env.PIPELINE.send()`). Events are buffered at the edge, micro-batched, and flushed to an R2 bucket on a configurable interval or byte-size threshold. The pipeline schema is enforced at ingest time; schema violations are sent to a dead-letter path.

## Pipeline Creation and wrangler.toml Binding

```toml
# wrangler.toml
name = "example project-event-ingestor"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[pipelines]]
binding = "EVENTS"
pipeline = "example project-behavioral-events"

[[r2_buckets]]
binding = "EVENTS_BUCKET"
bucket_name = "example project-events-raw"
```

Create the pipeline with Wrangler before deploying the worker:

```bash
npx wrangler pipelines create example project-behavioral-events \
  --r2-bucket example project-events-raw \
  --batch-max-mb 10 \
  --batch-timeout-seconds 30 \
  --compression gzip
```

The pipeline auto-generates an HTTP source URL (format: `https://pipeline-<id>.pipelines.cloudflare.com/`) usable directly from client SDKs or server-side workers.

## Event Schema and Worker Send Binding

Define a TypeScript schema for the event payload and use the binding to send batches.

```typescript
// src/types.ts
export interface BehavioralEvent {
  event_type:
    | "post_view"
    | "reaction"
    | "scroll_depth"
    | "session_start"
    | "session_end";
  anonymous_id: string; // hashed, no PII
  post_id?: string;
  reaction_type?: string;
  scroll_pct?: number; // 0–100
  ts: number; // epoch ms
  country?: string; // from CF-IPCountry header
  device_type?: "mobile" | "desktop" | "tablet";
}

export interface Env {
  EVENTS: Pipeline<BehavioralEvent>;
}
```

```typescript
// src/index.ts
import type { BehavioralEvent, Env } from "./types";

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (req.method !== "POST" || new URL(req.url).pathname !== "/events") {
      return new Response("Not found", { status: 404 });
    }

    let body: BehavioralEvent[];
    try {
      const raw = await req.json<BehavioralEvent | BehavioralEvent[]>();
      body = Array.isArray(raw) ? raw : [raw];
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    // Stamp server-side fields to prevent client spoofing
    const cf = req.cf as CfProperties | undefined;
    const enriched = body.map((ev) => ({
      ...ev,
      country: cf?.country ?? "XX",
      device_type: inferDevice(req.headers.get("User-Agent") ?? ""),
      ingested_at: Date.now(),
    }));

    // Non-blocking: send to pipeline after response is dispatched
    ctx.waitUntil(env.EVENTS.send(enriched));

    return new Response(null, { status: 204 });
  },
};

function inferDevice(ua: string): BehavioralEvent["device_type"] {
  if (/Mobi|Android/i.test(ua)) return "mobile";
  if (/Tablet|iPad/i.test(ua)) return "tablet";
  return "desktop";
}
```

## Handling Schema Violations and Dead-Letter Path

Pipelines reject records that violate the declared schema with a structured error. Configure a dead-letter R2 prefix or a secondary pipeline for invalid events.

```typescript
// src/index.ts — extended with DLQ fallback
import type { Env } from "./types";

export interface ExtendedEnv extends Env {
  EVENTS_DLQ: Pipeline<Record<string, unknown>>; // untyped sink
}

async function sendWithFallback(
  env: ExtendedEnv,
  events: unknown[],
  ctx: ExecutionContext
): Promise<void> {
  try {
    await env.EVENTS.send(events as any);
  } catch (err) {
    // Pipeline rejected batch (schema mismatch, rate limit, etc.)
    console.error("Pipeline send failed, routing to DLQ:", err);
    ctx.waitUntil(
      env.EVENTS_DLQ.send(
        events.map((e) => ({ raw: e, error: String(err), ts: Date.now() }))
      )
    );
  }
}
```

Add a second `[[pipelines]]` stanza for `EVENTS_DLQ` pointing to a `example project-events-dlq` R2 bucket. Monitor DLQ object counts via R2 Event Notifications to alert on sustained schema drift.

## Downstream ETL: Reading Pipeline Output from R2

Pipeline output lands as gzipped NDJSON under a time-partitioned R2 key prefix: `YYYY/MM/DD/HH/<uuid>.ndjson.gz`. A scheduled Worker reads new objects and aggregates them into D1 for the recommendation engine.

```typescript
// src/etl-aggregator.ts
export interface EtlEnv {
  EVENTS_BUCKET: R2Bucket;
  DB: D1Database;
}

export default {
  async scheduled(_: ScheduledEvent, env: EtlEnv, ctx: ExecutionContext) {
    const prefix = utcHourPrefix(new Date(Date.now() - 3_600_000)); // last hour
    const listed = await env.EVENTS_BUCKET.list({ prefix });

    for (const obj of listed.objects) {
      const r2obj = await env.EVENTS_BUCKET.get(obj.key);
      if (!r2obj) continue;

      // Decompress and parse NDJSON
      const ds = new DecompressionStream("gzip");
      const text = await new Response(
        r2obj.body.pipeThrough(ds)
      ).text();

      const rows = text
        .split("\n")
        .filter(Boolean)
        .map((l) => JSON.parse(l));

      // Batch upsert into D1 post_view_counts
      const stmts = rows
        .filter((r) => r.event_type === "post_view" && r.post_id)
        .map((r) =>
          env.DB.prepare(
            `INSERT INTO post_view_counts (post_id, views, hour)
             VALUES (?, 1, ?)
             ON CONFLICT (post_id, hour) DO UPDATE SET views = views + 1`
          ).bind(r.post_id, prefix)
        );

      if (stmts.length > 0) {
        await env.DB.batch(stmts);
      }
    }
  },
};

function utcHourPrefix(d: Date): string {
  return `${d.getUTCFullYear()}/${String(d.getUTCMonth() + 1).padStart(2, "0")}/${String(d.getUTCDate()).padStart(2, "0")}/${String(d.getUTCHours()).padStart(2, "0")}`;
}
```

## Anti-patterns
- Sending one event per `env.PIPELINE.send()` call — batch client-side events into arrays of 50–200 before sending to maximize throughput and reduce per-request overhead
- Using Pipelines as a real-time query source — R2-backed output has 30-second+ flush latency; use Workers Analytics Engine for sub-minute metrics
- Storing PII (email, IP, device fingerprint) in pipeline events without explicit consent signals — the R2 output is long-lived and auditable
- Treating Pipeline send as synchronous acknowledgement — wrap in `ctx.waitUntil()` to avoid blocking the HTTP response
- Relying solely on pipeline schema validation for business logic — validate critical fields in the Worker before calling `send()`

## Gotchas
- `env.PIPELINE.send()` accepts at most 10,000 records per call; split larger batches
- Pipeline HTTP source URLs are unauthenticated by default — place them behind a Worker with token validation if you can't afford event spoofing
- `batch-timeout-seconds` is the maximum delay, not a guaranteed interval; under very low traffic, the first flush may come later than expected
- Gzip compression reduces R2 egress costs but means downstream ETL must decompress; `DecompressionStream` is available in Workers runtime natively
- Pipeline bindings are not available in `wrangler dev --local` mode as of 2026-Q1; test the HTTP source path with `curl` against the preview endpoint

## Verification
1. Deploy: `npx wrangler deploy`
2. Send a test batch: `curl -X POST https://<worker>.workers.dev/events -H "Content-Type: application/json" -d '[{"event_type":"post_view","anonymous_id":"abc","post_id":"p1","ts":1234567890000}]'`
3. Check pipeline status: `npx wrangler pipelines get example project-behavioral-events`
4. After ~60 seconds, list R2 objects: `npx wrangler r2 object list example project-events-raw`
5. Verify output: `npx wrangler r2 object get example project-events-raw/<key> | gunzip | head`

## Related
- `pipelines-http-source-ingestion.md`
- `pipelines-r2-ingest-etl.md`
- `workers-pipelines-producer-schema.md`
- `r2-best-practices.md`
- `d1-best-practices.md`
- `cloudflare-workers-analytics-engine-custom-metrics.md`

## Sources
- https://developers.cloudflare.com/pipelines/
- https://developers.cloudflare.com/pipelines/get-started/
- https://developers.cloudflare.com/pipelines/reference/limits/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/workers/runtime-apis/streams/
