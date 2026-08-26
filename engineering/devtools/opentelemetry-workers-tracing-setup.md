# opentelemetry-workers-tracing-setup

**Issue:** Cloudflare Workers produce no distributed traces by default.
Requests from the mobile app flow through the Worker, hit D1, call
third-party APIs, and return — but when a request is slow or errors,
there is no trace to show which step took how long. Adding OpenTelemetry
SDK to Workers surfaces latency breakdowns, cross-service context
propagation, and mobile-vs-desktop trace comparison in a single backend.

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

```
# Sentry shows a 3-second p99 on POST /api/session
# No breakdown of: auth check / D1 query / third-party call / response
# Mobile clients time out at 5 s; desktop clients do not — unknown why

wrangler tail --format=json | jq '.logs[] | .message'
# Only sees console.log output, no structured spans or trace IDs
```

Without traces, root-cause analysis of latency regressions requires
adding temporary `Date.now()` calls and redeploying — a slow loop that
misses concurrent-request interactions and cold-start overhead.

## Context

OpenTelemetry (OTel) is the vendor-neutral observability standard for
traces, metrics, and logs. The Cloudflare Workers runtime supports a
constrained version of the Web Streams API and `fetch`, which the OTel
JS SDK can target. The key constraint is that Workers have no long-lived
network connections — the OTLP exporter must send spans before the
request ends, using `waitUntil()` so the export does not block the
response. Cloudflare Logpush can receive OTLP-formatted trace data and
forward it to a backend (Grafana Cloud, Honeycomb, Jaeger). Workers
Trace Events (available in the dashboard) give a coarser alternative
for quick inspection without a full OTel setup.

## SDK installation

```bash
pnpm add \
  @opentelemetry/api \
  @opentelemetry/sdk-trace-base \
  @opentelemetry/otlp-exporter-base \
  @opentelemetry/exporter-trace-otlp-http \
  @opentelemetry/resources \
  @opentelemetry/semantic-conventions \
  --filter @example project/worker
```

Cloudflare Workers do not support Node.js-specific packages.
`@opentelemetry/sdk-node` must NOT be used. Use `sdk-trace-base`
(the browser/edge-compatible base) instead.

## Tracer initialisation

```ts
// src/observability/tracer.ts
import { trace, context, propagation } from "@opentelemetry/api";
import { BasicTracerProvider, BatchSpanProcessor } from "@opentelemetry/sdk-trace-base";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { Resource } from "@opentelemetry/resources";
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from "@opentelemetry/semantic-conventions";
import { W3CTraceContextPropagator } from "@opentelemetry/core";

let provider: BasicTracerProvider | null = null;

export function initTracer(env: Env): void {
  if (provider) return; // already initialised in this isolate lifetime

  const exporter = new OTLPTraceExporter({
    url: env.OTLP_ENDPOINT, // e.g. https://otel.honeycomb.io/v1/traces
    headers: {
      "x-honeycomb-team": env.HONEYCOMB_API_KEY,
      // or for Grafana:
      // Authorization: `Basic ${btoa(env.GRAFANA_INSTANCE_ID + ":" + env.GRAFANA_API_KEY)}`
    },
  });

  provider = new BasicTracerProvider({
    resource: new Resource({

 ?? "dev",
      "deployment.environment": env.ENVIRONMENT ?? "production",
    }),
    spanProcessors: [new BatchSpanProcessor(exporter)],
  });

  provider.register({
    propagator: new W3CTraceContextPropagator(),
  });
}

export function getTracer() {
  return trace.getTracer("example project-worker", "1.0.0");
}
```

## Request handler integration

```ts
// src/index.ts
import { context, propagation, trace, SpanStatusCode } from "@opentelemetry/api";
import { initTracer, getTracer } from "./observability/tracer";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    initTracer(env);
    const tracer = getTracer();

    // Extract incoming trace context (from mobile app or Next.js)
    const carrier: Record<string, string> = {};
    request.headers.forEach((value, key) => { carrier[key] = value; });
    const parentContext = propagation.extract(context.active(), carrier);

    const url = new URL(request.url);
    const span = tracer.startSpan(
      `${request.method} ${url.pathname}`,
      {
        attributes: {
          "http.method": request.method,
          "http.url": request.url,
          "http.scheme": url.protocol.replace(":", ""),
          "http.host": url.host,
          "http.target": url.pathname + url.search,
          "user_agent.original": request.headers.get("user-agent") ?? "",
          "example project.client_type": request.headers.get("x-example project-client") ?? "unknown",
        },
      },
      parentContext
    );

    return context.with(trace.setSpan(parentContext, span), async () => {
      try {
        const response = await handleRequest(request, env, ctx);
        span.setAttributes({
          "http.status_code": response.status,
        });
        if (response.status >= 500) {
          span.setStatus({ code: SpanStatusCode.ERROR });
        }
        return response;
      } catch (err) {
        span.recordException(err as Error);
        span.setStatus({ code: SpanStatusCode.ERROR, message: String(err) });
        throw err;
      } finally {
        span.end();
        // Flush spans before the isolate is terminated
        ctx.waitUntil(
          (provider as any)._activeSpanProcessor.forceFlush()
        );
      }
    });
  },
};
```

## Child spans for D1 queries

```ts
// src/db/query.ts
import { trace, context } from "@opentelemetry/api";

export async function queryUser(db: D1Database, userId: string) {
  const tracer = trace.getTracer("example project-worker");
  const span = tracer.startSpan("d1.query.getUser", {
    attributes: {
      "db.system": "sqlite",
      "db.name": "example project-db",
      "db.operation": "SELECT",
      "db.statement": "SELECT * FROM users WHERE id = ?",
    },
  });

  try {
    const result = await db
      .prepare("SELECT * FROM users WHERE id = ?")
      .bind(userId)
      .first();
    span.setAttributes({ "db.rows_returned": result ? 1 : 0 });
    return result;
  } catch (err) {
    span.recordException(err as Error);
    throw err;
  } finally {
    span.end();
  }
}
```

## Trace context propagation to the mobile app

The mobile app (Expo/React Native) should include a `traceparent` header
on every API request so the Worker can link mobile spans to server spans:

```ts
// apps/mobile/src/api/client.ts
import { fetch as expoFetch } from "expo/fetch";

// Generate W3C traceparent: version-traceId-spanId-flags
function makeTraceparent(): string {
  const traceId = crypto.randomUUID().replace(/-/g, "");
  const spanId = crypto.randomUUID().replace(/-/g, "").slice(0, 16);
  return `00-${traceId}-${spanId}-01`;
}

export async function apiRequest(path: string, options?: RequestInit) {
  const traceparent = makeTraceparent();
  return expoFetch(`${process.env.EXPO_PUBLIC_API_URL}${path}`, {
    ...options,
    headers: {
      ...options?.headers,
      "traceparent": traceparent,
      "x-example project-client": "mobile",       // identify client type in spans
    },
  });
}
```

The Next.js web app sets `x-example project-client: web` and forwards the
`traceparent` from the incoming browser request to upstream Worker calls.

## Mobile vs desktop trace comparison

With `"example project.client_type"` on every root span, filter by client in your
tracing backend:

```
# Honeycomb / Grafana query (pseudo-SQL)
SELECT
  "example project.client_type",
  p50(duration_ms),
  p95(duration_ms),
  p99(duration_ms)
FROM traces
WHERE name = "POST /api/session"
  AND time > now() - 1h
GROUP BY "example project.client_type"
```

This surfaces whether mobile clients hit a different code path (e.g.
different auth token size, different geographic Cloudflare PoP) that
explains higher p99 latency.

## Logpush as OTLP backend

Cloudflare Logpush can forward Worker trace events to an OTLP-compatible
destination without a separate exporter:

```toml
# wrangler.toml — enable Workers Trace Events
[observability]
enabled = true
head_sampling_rate = 1   # 0.0–1.0; 1 = 100% of requests traced
```

This gives automatic span data (CPU time, wall time, subrequest count)
without the OTel SDK. For custom business spans (D1 query times, auth
latency) the SDK approach above is still needed and complements Logpush.

## .dev.vars for local OTel

```bash
# apps/worker/.dev.vars
OTLP_ENDPOINT="https://api.honeycomb.io/v1/traces"
HONEYCOMB_API_KEY="your-dev-api-key"
ENVIRONMENT="local"
WORKER_VERSION="dev"
```

In local dev, spans are exported to the real backend (or a local
Jaeger instance on `http://localhost:4318/v1/traces`).

## Anti-patterns

- **Using `@opentelemetry/sdk-node`** — imports Node.js built-ins
  (`os`, `fs`, `perf_hooks`) that are not available in Workers;
  Wrangler will fail to bundle.
- **Awaiting span export in the response path** — blocks the response
  for 50–200 ms; always use `ctx.waitUntil()` for the flush.
- **`SimpleSpanProcessor` in production** — sends one HTTP request per
  span; use `BatchSpanProcessor` to amortise export overhead.
- **Sampling at 100 % in production** — generates large volumes of spans;
  drop to 10–20 % at steady state with a `ParentBasedSampler`.
- **No `traceparent` from the mobile app** — server spans cannot be
  linked to the mobile call chain; always inject `traceparent` headers.

## Gotchas

- Workers isolate lifetime is short; `BatchSpanProcessor` may not flush
  if the span queue has not filled; always call `forceFlush()` in
  `waitUntil()`.
- `crypto.randomUUID()` is available in Workers (Web Crypto API) but
  not in the OTel JS SDK's default ID generator; the SDK uses its own
  random bytes implementation that works correctly in Workers.
- Cloudflare Workers Logpush `[observability]` stanza and the SDK are
  additive — spans from both appear in the backend and can be correlated
  by `trace_id` if the SDK propagates context correctly.
- The `W3CTraceContextPropagator` is the right choice for HTTP; use
  `B3MultiPropagator` only if integrating with a Zipkin-based system.

## Verification

```bash
# Send a request and check spans appear in backend
curl -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  http://localhost:8787/api/health

# Locally: start Jaeger
docker run -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:latest
# Set OTLP_ENDPOINT=http://localhost:4318/v1/traces in .dev.vars
# Open http://localhost:16686 — search service "example project-worker"

# Confirm waitUntil flush completes
wrangler tail --format=json | jq 'select(.outcome == "ok") | .duration'
# Duration should show non-trivial waitUntil time (50–200 ms for export)
```

## Related

- `documentation/categories/devtools/opentelemetry-local-dev.md`
- `documentation/categories/devtools/opentelemetry-sdk-instrumentation-tracing.md`
- `documentation/categories/devtools/sentry-error-monitoring-setup.md`
- `documentation/categories/devtools/wrangler-dev-local-d1-r2-kv.md`
- `documentation/categories/devtools/typescript-cloudflare-workers-strict.md`

## Sources

- https://developers.cloudflare.com/workers/observability/tracing/
- https://developers.cloudflare.com/workers/observability/logs/logpush/
- https://opentelemetry.io/docs/languages/js/getting-started/browser/
- https://opentelemetry.io/docs/specs/otel/trace/api/
- https://www.w3.org/TR/trace-context/
- https://github.com/open-telemetry/opentelemetry-js
