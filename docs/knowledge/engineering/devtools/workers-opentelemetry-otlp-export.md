# Exporting OpenTelemetry Traces from Workers to an OTLP Endpoint

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need distributed tracing for a Cloudflare Worker that calls D1 databases, KV stores, and external APIs. The built-in Cloudflare Logpush gives logs but not spans. You want traces to appear in Grafana Tempo (or any OpenTelemetry-compatible backend) alongside traces from your other services.

## Context

Cloudflare Workers run in a V8 isolate with no native OTLP SDK support. The `@microlabs/otel-cf-workers` library wraps the OpenTelemetry JS SDK so it works inside the isolate environment. It patches the Workers runtime's `fetch`, D1, and KV bindings to emit spans automatically, and it exports spans over HTTPS to any OTLP/HTTP endpoint before the isolate is torn down.

The key constraint is the Workers execution model: when the response is returned, the isolate may be recycled. Span export must be deferred with `ctx.waitUntil()` to guarantee delivery.

## Instrumentation Setup

```typescript
// src/instrumentation.ts
import { instrument, ResolvedTraceConfig } from '@microlabs/otel-cf-workers';
import { Resource } from '@opentelemetry/resources';
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions';
import { TracesSampler } from '@microlabs/otel-cf-workers';

export interface Env {
  DB: D1Database;
  KV: KVNamespace;
  OTEL_EXPORTER_OTLP_ENDPOINT: string; // Workers secret
  OTEL_EXPORTER_OTLP_HEADERS: string;  // Workers secret, JSON string
}

// Define tracing configuration — called once per isolate cold start
const config = (env: Env): ResolvedTraceConfig => ({
  exporter: {
    url: env.OTEL_EXPORTER_OTLP_ENDPOINT,     // e.g. https://tempo.example.com/otlp/v1/traces
    headers: JSON.parse(env.OTEL_EXPORTER_OTLP_HEADERS ?? '{}'),
  },
  service: {
    name: 'api-worker',
    version: '1.0.0',
  },
  resource: new Resource({
 ?? 'production',
  }),
  // Respect the W3C traceparent header from upstream callers;
  // always sample when the parent says to, never sample otherwise
  sampling: {
    headSampler: TracesSampler.PARENT_BASED_ALWAYS_ON,
  },
  // Automatically instrument these bindings
  bindings: {
    d1: true,   // wraps all D1 prepare/run/batch calls
    kv: true,   // wraps KV get/put/delete
    fetch: true, // wraps global fetch() and service bindings
  },
});

// Your actual worker handler
const worker = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const { tracer } = await import('./tracer');

    return tracer.startActiveSpan('handle-request', async (span) => {
      try {
        span.setAttribute('http.method', request.method);
        span.setAttribute('http.url', request.url);

        // D1 call is automatically traced by the binding wrapper
        const result = await env.DB
          .prepare('SELECT * FROM users WHERE id = ?')
          .bind(1)
          .first();

        // KV call is also automatically traced
        const cached = await env.KV.get('some-key');

        span.setAttribute('cache.hit', cached !== null);
        span.setStatus({ code: 1 }); // SpanStatusCode.OK
        return Response.json({ user: result, cached });
      } catch (err) {
        span.recordException(err as Error);
        span.setStatus({ code: 2, message: (err as Error).message });
        return new Response('Internal Server Error', { status: 500 });
      } finally {
        span.end();
        // Flush spans after the response is sent — critical pattern
        ctx.waitUntil(tracer.flush());
      }
    });
  },
};

// Wrap the worker with the instrumentation layer
export default instrument(worker, config);
```

## Secrets Configuration

```bash
# Set OTLP endpoint — the base URL, path is appended by the SDK
npx wrangler secret put OTEL_EXPORTER_OTLP_ENDPOINT
# Paste: https://tempo.internal.example.com/otlp/v1/traces

# Set auth headers as a JSON string
npx wrangler secret put OTEL_EXPORTER_OTLP_HEADERS
# Paste: {"Authorization":"Bearer <your-tempo-token>","X-Scope-OrgID":"my-org"}

# Or bulk-import both at once
cat > otel-secrets.json <<'EOF'
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://tempo.internal.example.com/otlp/v1/traces",
  "OTEL_EXPORTER_OTLP_HEADERS": "{\"Authorization\":\"Bearer abc123\"}"
}
EOF
npx wrangler secret bulk otel-secrets.json --env production
rm otel-secrets.json
```

## Sampling Strategy

```typescript
// Parent-based sampling — the most useful default for microservice architectures:
// - If the upstream request carries a sampled traceparent, always sample
// - If there is no parent, never sample (let the edge gateway decide)
// - Result: 100% of traced requests are complete; untraced noise is excluded
sampling: { headSampler: TracesSampler.PARENT_BASED_ALWAYS_ON }

// Alternative: always sample every request (useful for low-traffic Workers)
sampling: { headSampler: TracesSampler.ALWAYS_ON }

// Alternative: sample 10% of requests with no parent
import { TraceIdRatioBased } from '@opentelemetry/sdk-trace-base';
sampling: { headSampler: new TraceIdRatioBased(0.1) }
```

## Viewing Traces in Grafana Tempo

```yaml
# docker-compose.yml excerpt — local Tempo for development
tempo:
  image: grafana/tempo:latest
  command: ["-config.file=/etc/tempo.yaml"]
  volumes:
    - ./tempo.yaml:/etc/tempo.yaml
  ports:
    - "4318:4318"  # OTLP/HTTP receiver
    - "3200:3200"  # Tempo query API

grafana:
  image: grafana/grafana:latest
  environment:
    - GF_FEATURE_TOGGLES_ENABLE=traceqlEditor
  ports:
    - "3000:3000"
```

```bash
# Point local wrangler dev at local Tempo
npx wrangler dev \
  --var OTEL_EXPORTER_OTLP_ENDPOINT:http://localhost:4318/v1/traces \
  --var 'OTEL_EXPORTER_OTLP_HEADERS:{"X-Scope-OrgID":"dev"}'
```

## The `ctx.waitUntil(tracer.flush())` Pattern

The Workers runtime guarantees that tasks registered with `ctx.waitUntil()` run to completion even after the `Response` is returned to the client. Without this, spans buffered in memory are discarded when the isolate is recycled.

```typescript
// WRONG — flush called without waitUntil; spans may be lost
await span.end();
await tracer.flush(); // no guarantee this completes
return response;

// CORRECT — response sent immediately; flush continues in the background
span.end();
ctx.waitUntil(tracer.flush()); // runtime waits for this before recycling
return response;
```

## Anti-patterns

- **Hardcoding the OTLP endpoint or auth token in source code.** Both should be Workers secrets so they are rotated without a redeploy.
- **Calling `await tracer.flush()` without `ctx.waitUntil()`.** The `await` only resolves if the isolate is still alive; the runtime may recycle it before export completes.
- **Sampling 100% of high-traffic Workers at the trace level.** OTLP export adds latency and egress cost. Use `PARENT_BASED_ALWAYS_ON` or a ratio sampler for busy Workers.
- **Importing heavy OTEL packages at the module level.** Tree-shake unused exporters. Only import the OTLP/HTTP exporter, not the gRPC one, as Workers do not support Node.js gRPC bindings.

## Gotchas

- `@microlabs/otel-cf-workers` requires `compatibility_date = "2023-03-01"` or later in `wrangler.toml` for the `fetch` instrumentation patch to work correctly.
- The `OTEL_EXPORTER_OTLP_HEADERS` secret must be valid JSON. A common mistake is omitting quotes around the key when constructing the string in a shell script.
- D1 spans include the SQL statement text. Avoid logging sensitive data (PII, passwords in query strings) — either redact spans with a custom `SpanProcessor` or avoid parameterizing sensitive values as literals.
- `ctx.waitUntil` is not available in Durable Objects — use the `alarm()` handler pattern there instead.

## Verification

```bash
# After deploying, trigger a request and check Tempo
curl https://your-worker.example.workers.dev/api/users/1

# Query Tempo for traces from the service
curl "http://localhost:3200/api/search?service.name=api-worker&limit=10" | jq '.traces[].traceID'

# Or use TraceQL in Grafana Explore:
# { resource.service.name = "api-worker" } | duration > 100ms
```

## Related

- `wrangler-secret-bulk-import-workers.md` — setting OTLP secrets via bulk import
- `vitest-workers-env-type-generation.md` — typed `Env` for testing instrumented Workers
- Cloudflare Workers Observability docs

## Sources

- https://github.com/evanderkoogh/otel-cf-workers
- https://developers.cloudflare.com/workers/observability/
- https://opentelemetry.io/docs/specs/otel/trace/sdk/#sampling
- https://grafana.com/docs/tempo/latest/
