# Local OpenTelemetry Trace Exporter for Cloudflare Workers Development

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

During local `wrangler dev` sessions, Workers emit log lines but give no structured trace data — you cannot see which D1 query is slow, how subrequests fan out, or where latency is hiding. Plugging an OpenTelemetry exporter into the local dev loop lets you visualise traces in Jaeger or Zipkin with zero changes to the production Worker bundle.

## Context

Cloudflare Workers support the OpenTelemetry SDK via the `@microlabs/otel-cf-workers` package, which wraps the standard `@opentelemetry/sdk-trace-base` and exports via OTLP/HTTP. In production you point the exporter at a Baselime or Axiom endpoint. Locally, `wrangler dev` runs a V8 isolate that can reach `localhost` through its service-binding proxy, so you can export traces to a local OTLP collector (Jaeger all-in-one exposes port 4318 for OTLP/HTTP) and inspect them in the Jaeger UI at `http://localhost:16686`.

## Setting Up the Local OTLP Collector

Run Jaeger all-in-one using Docker. The `COLLECTOR_OTLP_ENABLED=true` flag activates the OTLP/HTTP receiver on port 4318.

```bash
docker run --rm -d \
  --name jaeger-local \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 16686:16686 \
  -p 4317:4317 \
  -p 4318:4318 \
  jaegertracing/all-in-one:1.57
```

For Zipkin instead:

```bash
docker run --rm -d \
  --name zipkin-local \
  -p 9411:9411 \
  openzipkin/zipkin:3
```

Verify the OTLP endpoint is reachable before starting `wrangler dev`:

```bash
curl -sf http://localhost:4318/v1/traces \
  -H "Content-Type: application/json" \
  -d '{"resourceSpans":[]}' && echo "OTLP endpoint ready"
```

## Instrumenting the Worker

Install the tracing packages. Use the exact peer versions the Cloudflare preset requires.

```bash
pnpm add @microlabs/otel-cf-workers @opentelemetry/api
pnpm add -D @opentelemetry/sdk-trace-base @opentelemetry/exporter-trace-otlp-http
```

Wrap your Worker export with `instrument` from `@microlabs/otel-cf-workers`:

```typescript
// src/index.ts
import { instrument, ResolveConfigFn } from "@microlabs/otel-cf-workers";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { SimpleSpanProcessor } from "@opentelemetry/sdk-trace-base";

export interface Env {
  DB: D1Database;
  ASSETS: R2Bucket;
  OTEL_EXPORTER_OTLP_ENDPOINT: string; // set in wrangler.toml [vars] for local
}

const handler: ExportedHandler<Env> = {
  async fetch(request, env, ctx): Promise<Response> {
    const { results } = await env.DB.prepare(
      "SELECT id, name FROM products WHERE active = 1 LIMIT 20"
    ).all();

    return Response.json(results);
  },
};

const config: ResolveConfigFn = (env: Env, _trigger) => ({
  exporter: new OTLPTraceExporter({
    url: `${env.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces`,
  }),
  spanProcessors: [
    new SimpleSpanProcessor(
      new OTLPTraceExporter({
        url: `${env.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces`,
      })
    ),
  ],
  service: { name: "example project-api", version: "0.1.0" },
});

export default instrument(handler, config);
```

## Wrangler Configuration for Local vs Production

Use `[env.local]` overrides so the local OTLP endpoint never leaks into the production build:

```toml
# wrangler.toml
name = "example project-api"
compatibility_date = "2026-01-01"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "example project-prod"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
OTEL_EXPORTER_OTLP_ENDPOINT = "https://otel.baselime.io"

[env.local.vars]
OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4318"

[[env.local.d1_databases]]
binding = "DB"
database_name = "example project-local"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

Start the local dev server targeting the `local` environment:

```bash
wrangler dev --env local --local
```

## Trace Propagation and Subrequest Correlation

To correlate traces across Workers subrequests (e.g., a gateway Worker calling a downstream data Worker), propagate W3C `traceparent` headers:

```typescript
// src/gateway.ts
import { context, propagation, trace } from "@opentelemetry/api";

const handler: ExportedHandler<Env> = {
  async fetch(request, env, ctx): Promise<Response> {
    const tracer = trace.getTracer("gateway");

    return tracer.startActiveSpan("handle-request", async (span) => {
      // Inject current trace context into outbound subrequest headers
      const outboundHeaders = new Headers(request.headers);
      propagation.inject(context.active(), outboundHeaders, {
        set: (carrier: Headers, key: string, value: string) =>
          carrier.set(key, value),
      });

      const upstream = await fetch("https://data-worker.example.com/api", {
        headers: outboundHeaders,
      });

      span.setAttribute("http.status_code", upstream.status);
      span.end();
      return upstream;
    });
  },
};
```

On the downstream Worker, extract the incoming context so Jaeger links the spans:

```typescript
// src/data-worker.ts
import { context, propagation, trace } from "@opentelemetry/api";

const handler: ExportedHandler<Env> = {
  async fetch(request, env, ctx): Promise<Response> {
    const extractedCtx = propagation.extract(context.active(), request.headers, {
      get: (carrier: Headers, key: string) => carrier.get(key) ?? undefined,
      keys: (carrier: Headers) => [...carrier.keys()],
    });

    const tracer = trace.getTracer("data-worker");
    return context.with(extractedCtx, () =>
      tracer.startActiveSpan("db-query", async (span) => {
        const { results } = await env.DB.prepare(
          "SELECT * FROM orders WHERE status = 'pending'"
        ).all();
        span.setAttribute("db.row_count", results.length);
        span.end();
        return Response.json(results);
      })
    );
  },
};
```

## Debugging D1 Query Traces

`@microlabs/otel-cf-workers` auto-instruments D1 queries and attaches them as child spans with the SQL statement as `db.statement`. To verify in Jaeger:

1. Open `http://localhost:16686`
2. Select service `example project-api` and click **Find Traces**
3. Expand a trace — D1 spans appear as `cloudflare.d1.prepare` / `cloudflare.d1.all` children under the root fetch span

To add custom attributes to D1 spans, wrap the call manually:

```typescript
import { trace, SpanKind } from "@opentelemetry/api";

async function queryProductsWithSpan(db: D1Database, category: string) {
  const tracer = trace.getTracer("example project-api");

  return tracer.startActiveSpan(
    "d1.products.list",
    { kind: SpanKind.CLIENT, attributes: { "db.category": category } },
    async (span) => {
      try {
        const stmt = db.prepare(
          "SELECT id, name, price FROM products WHERE category = ?1 AND active = 1"
        );
        const { results, meta } = await stmt.bind(category).all();
        span.setAttribute("db.rows_returned", results.length);
        span.setAttribute("db.duration_ms", meta.duration);
        return results;
      } finally {
        span.end();
      }
    }
  );
}
```

## Anti-patterns

- Hardcoding `http://localhost:4318` in the Worker source — it will error in production; always use an env var resolved at runtime.
- Using `BatchSpanProcessor` locally — it buffers spans and flushes on an interval, so fast `wrangler dev` requests may exit before the flush fires; use `SimpleSpanProcessor` in the local env.
- Exporting full stack traces as span attributes in production — OTLP payload size increases dramatically; add a size guard or strip in the production config.

## Gotchas

- `wrangler dev --local` runs in the workerd runtime, which supports `fetch` but not Node.js `http` — the OTLP HTTP exporter must use the Fetch-based transport (`OTLPTraceExporter` from `@opentelemetry/exporter-trace-otlp-http` v0.50+ automatically does this in Workers).
- If the Jaeger container is not running when `wrangler dev` starts, the exporter silently drops spans — it does not crash the Worker, so add a startup readiness check to your dev script.

## Verification

```bash
# Confirm Jaeger is receiving spans
curl -s "http://localhost:16686/api/services" | jq '.data[]'

# Tail wrangler dev logs for OTLP export errors
wrangler dev --env local --local 2>&1 | grep -i "otel\|trace\|export"

# Send a test request and then query Jaeger for traces in the last 5 minutes
curl http://localhost:8787/api/products
sleep 1
curl -s "http://localhost:16686/api/traces?service=example project-api&limit=5" | jq '.data[0].spans | length'
```

## Related

- `devtools/opentelemetry-workers-tracing-setup.md`
- `devtools/opentelemetry-local-dev.md`
- `devtools/wrangler-dev-local-d1-r2-kv.md`
- `devtools/durable-objects-local-debugging.md`

## Sources

- https://developers.cloudflare.com/workers/observability/logs/workers-trace-events/
- https://developers.cloudflare.com/workers/observability/tracing/
- https://github.com/evanderkoogh/otel-cf-workers
- https://opentelemetry.io/docs/specs/otlp/
- https://www.jaegertracing.io/docs/1.57/deployment/#all-in-one
