# Correlation ID Propagation Across Workers Service Bindings

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A example project request touches the edge Worker, then the moderation Worker via a service binding, then a notification Worker, then writes to D1. When something fails mid-chain, the tail logs across all four Workers show four unrelated request IDs and no way to stitch the trace back together. Debugging latency spikes or silent failures requires correlating logs across multiple Workers that have no shared identifier.

## Context

Cloudflare service bindings let Workers call other Workers directly, without going through the public internet. Each sub-call generates its own `cf-ray` trace ID, which is scoped to that individual Worker invocation. Without explicit propagation of a **correlation ID** — a stable identifier minted at the system boundary and carried through every downstream call — distributed tracing across service bindings is impossible. This pattern establishes the convention: one ID minted at the edge, forwarded as a request header in every binding call, attached to every `console.log` via a structured logging wrapper, and persisted to D1 audit rows for durable correlation.

## 1. Minting the Correlation ID at the Edge

The outermost Worker is the trust boundary. If an incoming request carries a `X-Correlation-Id` header (from a trusted internal caller or client-side SDK), validate and reuse it. Otherwise, generate a new one using `crypto.randomUUID()`.

```typescript
const CORRELATION_HEADER = 'X-Correlation-Id';
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function getOrMintCorrelationId(request: Request): string {
  const incoming = request.headers.get(CORRELATION_HEADER);
  if (incoming && UUID_RE.test(incoming)) return incoming;
  return crypto.randomUUID();
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const correlationId = getOrMintCorrelationId(request);
    const logger = makeLogger(correlationId);

    logger.info('request_received', { path: new URL(request.url).pathname });

    const response = await handleRequest(request, env, ctx, correlationId);

    return new Response(response.body, {
      status: response.status,
      headers: {
        ...Object.fromEntries(response.headers),

      },
    });
  },
};
```

## 2. Forwarding Through Service Binding Calls

When calling a downstream Worker via a service binding, always inject the correlation ID as a header on the synthesised request. The downstream Worker reads it with the same `getOrMintCorrelationId` helper and treats it as the authoritative ID for its own logs.

```typescript
async function callModerationWorker(
  payload: ModerationPayload,
  correlationId: string,
  env: Env,
): Promise<ModerationResult> {
  const request = new Request('https://moderation.internal/evaluate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',

    },
    body: JSON.stringify(payload),
  });

  const response = await env.MODERATION_WORKER.fetch(request);
  if (!response.ok) {
    throw new Error(`moderation_failed status=${response.status} cid=${correlationId}`);
  }
  return response.json<ModerationResult>();
}
```

Service binding definition in `wrangler.toml`:

```toml
[[services]]
binding = "MODERATION_WORKER"
service = "example project-moderation"
entrypoint = "default"
```

## 3. Structured Logging Wrapper

Attach the correlation ID to every log line automatically so that Tail Workers and external log sinks can group all lines by `correlationId` without post-processing.

```typescript
interface LogEntry {
  level: 'info' | 'warn' | 'error';
  event: string;
  correlationId: string;
  ts: string;

}

function makeLogger(correlationId: string) {
  return {
    info: (event: string, fields: Record<string, unknown> = {}) =>
      log('info', event, correlationId, fields),
    warn: (event: string, fields: Record<string, unknown> = {}) =>
      log('warn', event, correlationId, fields),
    error: (event: string, fields: Record<string, unknown> = {}) =>
      log('error', event, correlationId, fields),
  };
}

function log(
  level: LogEntry['level'],
  event: string,
  correlationId: string,
  fields: Record<string, unknown>,
): void {
  const entry: LogEntry = {
    level,
    event,
    correlationId,
    ts: new Date().toISOString(),
    ...fields,
  };
  console.log(JSON.stringify(entry));
}
```

## 4. Persisting Correlation IDs to D1 for Durable Audit

For requests that result in a write (post creation, moderation actions), store the correlation ID in the D1 audit row so that queries against D1 can always reconstruct the originating request.

```typescript
async function auditWrite(
  db: D1Database,
  correlationId: string,
  action: string,
  entityId: string,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO audit_log (correlation_id, action, entity_id, created_at)
       VALUES (?, ?, ?, CURRENT_TIMESTAMP)`,
    )
    .bind(correlationId, action, entityId)
    .run();
}
```

D1 schema:

```sql
CREATE TABLE audit_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  correlation_id TEXT NOT NULL,
  action        TEXT NOT NULL,
  entity_id     TEXT NOT NULL,
  created_at    TEXT NOT NULL
);
CREATE INDEX idx_audit_correlation ON audit_log(correlation_id);
```

## 5. Tail Worker Log Aggregation

A Tail Worker receives structured log lines from all bound Workers. Index by `correlationId` to reconstruct the full trace from a single identifier.

```typescript
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      for (const log of event.logs) {
        try {
          const entry = JSON.parse(log.message[0] as string);
          if (entry.correlationId) {
            await env.LOGS_KV.put(
              `trace:${entry.correlationId}:${Date.now()}`,
              JSON.stringify(entry),
              { expirationTtl: 86400 * 7 },
            );
          }
        } catch {
          // non-JSON log line; skip
        }
      }
    }
  },
};
```

## Anti-patterns

- **Trusting incoming `X-Correlation-Id` without validation** — an untrusted caller can inject an arbitrary ID; always validate UUID format before accepting external values.
- **Generating a new ID inside downstream Workers** — this defeats the purpose; always forward the ID received from the parent, never mint a new one mid-chain.
- **Using `cf-ray` as a correlation ID** — `cf-ray` is per-Worker-invocation; it changes on every service binding hop and cannot be used to correlate across the chain.
- **Logging correlation IDs as plain strings without a structured key** — log shipping pipelines need a predictable field name; always use `correlationId` in a JSON log envelope.

## Gotchas

- Service bindings do not automatically forward request headers — every header must be explicitly set on the synthesised `Request` object; Workers have no "header inheritance" from the parent call.
- `crypto.randomUUID()` is available in the Workers runtime since compatibility date `2022-07-21`; confirm your `compatibility_date` in `wrangler.toml`.
- Tail Workers receive logs with a ~1-second delay; they are not suitable for real-time tracing but are sufficient for post-hoc debugging.
- The correlation ID must be treated as an opaque token for external callers — never embed user-identifiable information in it; use UUID v4.

## Verification

1. Make an end-to-end request and inspect the `X-Correlation-Id` header in the response; assert it is a valid UUID v4.
2. Inspect structured logs across the edge Worker and moderation Worker for the same request; assert `correlationId` field is identical in both.
3. Query `audit_log` in D1 for the returned correlation ID; assert rows for all write actions in the request are present.
4. Submit a request with a malformed `X-Correlation-Id`; assert the system mints a fresh valid UUID and does not echo the malformed value.

## Related

- `distributed-tracing-architecture.md`
- `observability-architecture.md`
- `workers-tail-handlers-observability.md`
- `proxy-pattern-workers-service-binding-abstraction.md`
- `worker-to-worker-rpc-service-bindings.md`

## Sources

- Cloudflare Workers service bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Tail Workers: https://developers.cloudflare.com/workers/observability/tail-workers/
- W3C Trace Context specification: https://www.w3.org/TR/trace-context/
