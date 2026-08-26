# Wrangler Logpush Local Dev Debugging

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

During local development of example project Workers, `console.log` output appears in the Wrangler terminal but lacks structure, timestamps, or severity levels. Filtering specific request paths or user IDs from the flood of local log output is painful and slows debugging cycles.

## Context

Cloudflare Workers Logpush is a production feature that streams structured logs to destinations like R2, Supabase, or third-party observability platforms. In local dev (`wrangler dev`), the equivalent is `wrangler tail` combined with structured logging on the Worker side. Understanding how to replicate Logpush semantics locally — structured JSON, severity fields, trace IDs — dramatically speeds up debugging anonymous social platform features like feed generation or DM fanout.

## Structured Logging Utility

Define a typed logger that emits JSON lines in the same schema Logpush uses so logs are parseable both locally and in production.

```typescript
// src/lib/logger.ts
export type LogLevel = "debug" | "info" | "warn" | "error";

interface LogEntry {
  level: LogLevel;
  message: string;
  ts: number;
  traceId?: string;
  userId?: string;
  path?: string;
  durationMs?: number;

}

export function createLogger(ctx: { traceId: string; path: string }) {
  return {
    debug: (msg: string, fields?: Record<string, unknown>) =>
      emit("debug", msg, ctx, fields),
    info: (msg: string, fields?: Record<string, unknown>) =>
      emit("info", msg, ctx, fields),
    warn: (msg: string, fields?: Record<string, unknown>) =>
      emit("warn", msg, ctx, fields),
    error: (msg: string, fields?: Record<string, unknown>) =>
      emit("error", msg, ctx, fields),
  };
}

function emit(
  level: LogLevel,
  message: string,
  ctx: Record<string, unknown>,
  fields?: Record<string, unknown>,
): void {
  const entry: LogEntry = {
    level,
    message,
    ts: Date.now(),
    ...ctx,
    ...fields,
  };
  // Single console.log call keeps Wrangler output clean
  console.log(JSON.stringify(entry));
}
```

## Wrangler Tail With JSON Filtering

`wrangler tail` accepts `--format json` and can be piped to `jq` for real-time filtering. Use this during local or remote dev sessions.

```bash
# Stream all logs as pretty JSON
wrangler tail --env local --format json | jq .

# Filter to errors only
wrangler tail --format json | jq 'select(.logs[].level == "error")'

# Filter by path prefix (feed routes)
wrangler tail --format json \
  | jq 'select(.event.request.url | test("/api/feed"))'

# Filter by sampled user ID — pass as search string
wrangler tail --search "userId\":\"usr_42" --format json | jq .
```

For `wrangler dev` (local mode), tail runs against the local Workers runtime, so no egress occurs.

## Trace ID Propagation

Assign a trace ID at the Worker entry point so every log line for a single request shares an ID. This mirrors Logpush's `rayId` field.

```typescript
// src/index.ts
import { createLogger } from "./lib/logger";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const traceId =
      request.headers.get("cf-ray") ??
      request.headers.get("x-trace-id") ??
      crypto.randomUUID();

    const log = createLogger({ traceId, path: new URL(request.url).pathname });

    log.info("request.start", { method: request.method });
    const t0 = Date.now();

    try {
      const response = await handleRequest(request, env, ctx, log);
      log.info("request.end", { status: response.status, durationMs: Date.now() - t0 });
      return response;
    } catch (err) {
      log.error("request.unhandled", {
        error: err instanceof Error ? err.message : String(err),
        durationMs: Date.now() - t0,
      });
      return new Response("Internal Server Error", { status: 500 });
    }
  },
};
```

## Local Logpush Simulation via R2 Binding

When you want to verify the exact payload Logpush would emit before enabling it in production, write logs to a local R2 binding in the same JSON-newline format.

```typescript
// src/lib/logpush-sink.ts
export class LogpushSink {
  private buffer: string[] = [];

  constructor(
    private readonly r2: R2Bucket,
    private readonly prefix: string = "logs",
  ) {}

  append(entry: Record<string, unknown>): void {
    this.buffer.push(JSON.stringify(entry));
  }

  async flush(ctx: ExecutionContext): Promise<void> {
    if (this.buffer.length === 0) return;
    const key = `${this.prefix}/${new Date().toISOString()}.ndjson`;
    const body = this.buffer.join("\n") + "\n";
    ctx.waitUntil(this.r2.put(key, body, { httpMetadata: { contentType: "application/x-ndjson" } }));
    this.buffer = [];
  }
}
```

In `wrangler.toml`, bind a local R2 bucket:

```toml
[[r2_buckets]]
binding = "LOG_SINK"
bucket_name = "example project-logs-local"
```

Run `wrangler dev` with `--local` and inspect the NDJSON files with `wrangler r2 object get`.

## Anti-patterns

- Using `console.log(obj)` (non-JSON) makes log lines unparseable by `jq` or downstream sinks
- Logging inside tight loops (e.g., per-post in feed assembly) at `info` — downgrade to `debug` and gate with an env flag
- Emitting PII (email, phone) in log fields even in local dev — use anonymised IDs only
- Forgetting to call `sink.flush(ctx)` before the request returns, causing buffered logs to drop

## Gotchas

- `wrangler tail --format json` in local mode requires `wrangler dev` to be running in a separate terminal; tail connects to the dev runtime socket
- `cf-ray` is only present when the Worker is invoked through Cloudflare's edge; in local dev it will be absent, so always fall back to `crypto.randomUUID()`
- `ctx.waitUntil` is a no-op in local Workers by default unless `wrangler dev --persist` is set; the R2 sink may appear silent
- Log volumes in `wrangler tail` are rate-limited in production (≤ 100 messages per invocation); local dev has no such limit

## Verification

```bash
# 1. Start local dev
wrangler dev --local --persist

# 2. In a second terminal, tail with JSON filtering
wrangler tail --format json | jq 'select(.logs[].level)'

# 3. Hit an endpoint
curl http://localhost:8787/api/feed

# 4. Verify structured fields appear in the tail output:
#    { "level": "info", "message": "request.start", "traceId": "...", "path": "/api/feed" }
```

## Related

- `wrangler-dev-local-d1-r2-kv.md`
- `wrangler-tail-log-streaming-production.md`
- `wrangler-tail-log-filtering-advanced.md`
- `opentelemetry-workers-tracing-setup.md`

## Sources

- https://developers.cloudflare.com/workers/observability/logs/logpush/
- https://developers.cloudflare.com/workers/wrangler/commands/#tail
- https://developers.cloudflare.com/r2/reference/data-location/
