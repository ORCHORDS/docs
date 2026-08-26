# Distributed Tracing with OpenTelemetry in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A request to your API Worker fans out to an Auth Service Binding, two D1 queries, and a KV read. When p99 latency spikes you can see the total duration in your Tail Worker logs but you cannot see which hop caused it. You need end-to-end distributed traces — with spans for each sub-operation — exported to an OTLP collector (Honeycomb, Grafana Tempo, or a self-hosted OTEL Collector) so you can identify the bottleneck without guessing.

## Context

The `@opentelemetry/sdk-trace-base` package works in Workers because it has no Node.js-specific imports. You provide a custom exporter that uses the Workers `fetch` API to POST spans to an OTLP/HTTP endpoint at the end of each request.

Trace context propagates between Services using the W3C `traceparent` header (`00-<traceId>-<spanId>-<flags>`). Each Service Binding call injects the header outbound and extracts it inbound, stitching spans from multiple Workers into one trace tree.

Stack:
- **`@opentelemetry/sdk-trace-base`** — core tracer, span model
- **`@opentelemetry/core`** — W3C propagator, hex encoding helpers
- **Workers Service Bindings** — inter-Worker RPC
- **D1 / KV** — instrumented storage operations
- **OTLP/HTTP endpoint** — Honeycomb, Tempo, or OTEL Collector

## Solution

```typescript
// tracing.ts  —  self-contained OpenTelemetry setup for Workers
import {
  BasicTracerProvider,
  BatchSpanProcessor,
  ReadableSpan,
  SpanExporter,
  SimpleSpanProcessor,
} from '@opentelemetry/sdk-trace-base';
import {
  W3CTraceContextPropagator,
  CompositePropagator,
} from '@opentelemetry/core';
import {
  context,
  propagation,
  trace,
  SpanStatusCode,
  SpanKind,
  Context,
  ROOT_CONTEXT,
} from '@opentelemetry/api';
import type { D1Database, KVNamespace } from '@cloudflare/workers-types';

// ── OTLP/HTTP exporter ────────────────────────────────────────────────────────
// Sends spans to any OTLP-compatible backend using Workers fetch.

class OtlpFetchExporter implements SpanExporter {
  constructor(
    private readonly endpoint: string,
    private readonly headers: Record<string, string>
  ) {}

  async export(
    spans: ReadableSpan[],
    resultCallback: (result: { code: number }) => void
  ): Promise<void> {
    const body = this.encodeSpans(spans);
    try {
      const res = await fetch(this.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...this.headers },
        body,
      });
      resultCallback({ code: res.ok ? 0 : 1 });
    } catch {
      resultCallback({ code: 1 });
    }
  }

  shutdown(): Promise<void> {
    return Promise.resolve();
  }

  // Minimal JSON encoding of OTLP span format (protobuf not available in Workers).
  private encodeSpans(spans: ReadableSpan[]): string {
    const resourceSpans = [{
      resource: { attributes: [{ key: 'service.name', value: { stringValue: 'orchords-api' } }] },
      scopeSpans: [{
        scope: { name: 'workers-otel', version: '1.0.0' },
        spans: spans.map((s) => ({
          traceId: s.spanContext().traceId,
          spanId: s.spanContext().spanId,
          parentSpanId: s.parentSpanId ?? '',
          name: s.name,
          kind: s.kind,
          startTimeUnixNano: String(s.startTime[0] * 1e9 + s.startTime[1]),
          endTimeUnixNano: String(s.endTime[0] * 1e9 + s.endTime[1]),
          status: { code: s.status.code === SpanStatusCode.ERROR ? 2 : 1 },
          attributes: Object.entries(s.attributes).map(([key, value]) => ({
            key,
            value: typeof value === 'number'
              ? { doubleValue: value }
              : { stringValue: String(value) },
          })),
          events: s.events.map((e) => ({
            name: e.name,
            timeUnixNano: String(e.time[0] * 1e9 + e.time[1]),
          })),
        })),
      }],
    }];
    return JSON.stringify({ resourceSpans });
  }
}

// ── provider factory ──────────────────────────────────────────────────────────
// Call once per request (or cache in module scope if provider is cheap to reuse).

export function createProvider(otlpEndpoint: string, otlpHeaders: Record<string, string>) {
  const provider = new BasicTracerProvider();
  const exporter = new OtlpFetchExporter(otlpEndpoint, otlpHeaders);
  // Use SimpleSpanProcessor so spans flush synchronously inside ctx.waitUntil.
  provider.addSpanProcessor(new SimpleSpanProcessor(exporter));
  provider.register({
    propagator: new CompositePropagator({ propagators: [new W3CTraceContextPropagator()] }),
  });
  return provider;
}

// ── context propagation helpers ───────────────────────────────────────────────

export function extractContext(headers: Headers): Context {
  const carrier: Record<string, string> = {};
  headers.forEach((value, key) => (carrier[key] = value));
  return propagation.extract(ROOT_CONTEXT, carrier);
}

export function injectContext(ctx: Context, headers: Headers): void {
  const carrier: Record<string, string> = {};
  propagation.inject(ctx, carrier);
  for (const [k, v] of Object.entries(carrier)) {
    headers.set(k, v);
  }
}

// ── D1 instrumented wrapper ───────────────────────────────────────────────────

export async function tracedD1Query<T>(
  db: D1Database,
  parentCtx: Context,
  sql: string,
  params: unknown[],
  spanName = 'd1.query'
): Promise<T | null> {
  const tracer = trace.getTracer('workers-otel');
  const span = tracer.startSpan(
    spanName,
    {
      kind: SpanKind.CLIENT,
      attributes: {
        'db.system': 'd1',
        'db.statement': sql.slice(0, 200),
        'db.params_count': params.length,
      },
    },
    parentCtx
  );
  try {
    const result = await db.prepare(sql).bind(...params).first<T>();
    span.setStatus({ code: SpanStatusCode.OK });
    return result;
  } catch (err) {
    span.recordException(err as Error);
    span.setStatus({ code: SpanStatusCode.ERROR, message: String(err) });
    throw err;
  } finally {
    span.end();
  }
}

// ── KV instrumented wrapper ───────────────────────────────────────────────────

export async function tracedKvGet(
  kv: KVNamespace,
  parentCtx: Context,
  key: string
): Promise<string | null> {
  const tracer = trace.getTracer('workers-otel');
  const span = tracer.startSpan(
    'kv.get',
    {
      kind: SpanKind.CLIENT,
      attributes: { 'db.system': 'cloudflare-kv', 'kv.key': key },
    },
    parentCtx
  );
  try {
    const val = await kv.get(key);
    span.setAttribute('kv.hit', val !== null);
    span.setStatus({ code: SpanStatusCode.OK });
    return val;
  } catch (err) {
    span.recordException(err as Error);
    span.setStatus({ code: SpanStatusCode.ERROR, message: String(err) });
    throw err;
  } finally {
    span.end();
  }
}

// ── main Worker with full tracing ─────────────────────────────────────────────

import type { Env as BaseEnv } from './types';

export interface Env extends BaseEnv {
  DB: D1Database;
  APP_KV: KVNamespace;
  AUTH: Fetcher;            // Service Binding to the auth Worker
  OTLP_ENDPOINT: string;
  OTLP_HEADERS: string;     // JSON: {"x-honeycomb-team": "<key>"}
  SAMPLE_RATE: string;      // 0–1, default "0.1"
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const sampleRate = parseFloat(env.SAMPLE_RATE ?? '0.1');
    if (Math.random() > sampleRate) {
      // Not sampled — process normally without tracing overhead.
      return handleRequest(request, env, ctx, null, ROOT_CONTEXT);
    }

    const otlpHeaders = JSON.parse(env.OTLP_HEADERS ?? '{}') as Record<string, string>;
    const provider = createProvider(env.OTLP_ENDPOINT, otlpHeaders);
    const tracer = trace.getTracer('workers-otel');

    // Extract incoming trace context (from upstream caller or browser).
    const parentCtx = extractContext(request.headers);

    const rootSpan = tracer.startSpan(
      `${request.method} ${new URL(request.url).pathname}`,
      {
        kind: SpanKind.SERVER,
        attributes: {
          'http.method': request.method,
          'http.url': request.url,
          'http.scheme': new URL(request.url).protocol.replace(':', ''),
          'http.target': new URL(request.url).pathname,
          'cf.colo': (request as unknown as { cf: { colo: string } }).cf?.colo ?? '',
        },
      },
      parentCtx
    );

    const reqCtx = trace.setSpan(parentCtx, rootSpan);

    let response: Response;
    try {
      response = await handleRequest(request, env, ctx, tracer, reqCtx);
      rootSpan.setAttribute('http.status_code', response.status);
      rootSpan.setStatus({
        code: response.status >= 500 ? SpanStatusCode.ERROR : SpanStatusCode.OK,
      });
    } catch (err) {
      rootSpan.recordException(err as Error);
      rootSpan.setStatus({ code: SpanStatusCode.ERROR, message: String(err) });
      response = new Response('Internal Server Error', { status: 500 });
    } finally {
      rootSpan.end();
    }

    // Flush spans after response is sent.
    ctx.waitUntil(provider.forceFlush());
    return response;
  },
};

async function handleRequest(
  request: Request,
  env: Env,
  _ctx: ExecutionContext,
  tracer: ReturnType<typeof trace.getTracer> | null,
  reqCtx: Context
): Promise<Response> {
  // Propagate trace context to the Auth Service Binding.
  const authHeaders = new Headers({ 'Content-Type': 'application/json' });
  injectContext(reqCtx, authHeaders);

  const authSpan = tracer?.startSpan('auth.verify', { kind: SpanKind.CLIENT, attributes: { 'rpc.system': 'service-binding', 'rpc.service': 'auth' } }, reqCtx);
  const authCtx = authSpan ? trace.setSpan(reqCtx, authSpan) : reqCtx;
  const authRes = await env.AUTH.fetch('https://auth/verify', { method: 'POST', headers: authHeaders });
  authSpan?.setAttribute('http.status_code', authRes.status);
  authSpan?.setStatus({ code: authRes.ok ? SpanStatusCode.OK : SpanStatusCode.ERROR });
  authSpan?.end();

  if (!authRes.ok) return new Response('Unauthorized', { status: 401 });

  // D1 query with tracing.
  const user = await tracedD1Query<{ id: string; name: string }>(
    env.DB,
    authCtx,
    'SELECT id, name FROM users WHERE token = ? LIMIT 1',
    [request.headers.get('authorization') ?? ''],
    'd1.users.lookup'
  );

  if (!user) return new Response('Not Found', { status: 404 });

  // KV read with tracing.
  const cached = await tracedKvGet(env.APP_KV, authCtx, `user:${user.id}:profile`);

  return Response.json({ user, cached: cached !== null });
}
```

## Implementation Details

**`SimpleSpanProcessor` vs `BatchSpanProcessor`**: BatchSpanProcessor queues spans and flushes them on a timer or when the queue is full. In Workers, timers don't run between requests. Use `SimpleSpanProcessor` and flush explicitly via `ctx.waitUntil(provider.forceFlush())` at the end of each request.

**OTLP JSON not protobuf**: Workers cannot run the protobuf runtime. The custom `OtlpFetchExporter` serialises spans as `application/json` using the OTLP JSON encoding, which all major backends accept.

**Service Binding propagation**: `injectContext` writes the `traceparent` header into the outbound request headers. The downstream Worker calls `extractContext` on its inbound headers. Both Workers must share the same OpenTelemetry propagator setup — otherwise the context cannot be decoded.

**Sampling at the root**: The `SAMPLE_RATE` environment variable gates tracing at the outermost Worker. Downstream Service Bindings receive the sampling flag in the `traceparent` `flags` byte (`01` = sampled, `00` = not sampled) and should respect it rather than making independent decisions.

## Anti-patterns

- **Creating a new `BasicTracerProvider` in the module scope**: the provider holds a reference to the exporter which contains the OTLP endpoint URL and headers. These come from `env`, which is request-scoped. Create the provider inside the fetch handler.
- **Forgetting `ctx.waitUntil(provider.forceFlush())`**: without this, spans are dropped when the isolate idles between requests. The flush must happen after `rootSpan.end()`.
- **Tracing 100 % of requests at 50 k req/s**: at 50 k req/s, 100 % sampling produces 50 k OTLP POST requests/s. Sample at 1–10 % for routine requests; always sample errors via tail sampling.
- **Storing the provider in module-level state**: Cloudflare Workers may run millions of isolates. Module-level state is per-isolate — the provider's in-memory span buffer is not shared, which is correct, but be careful not to accumulate unbounded state.

## Gotchas

- **`@opentelemetry/sdk-trace-base` bundle size**: the package adds ~120 KB to your bundle. Run `npx wrangler deploy --dry-run --outdir dist` and check the bundle size; add it to `trees` in `wrangler.toml` only if you need it for non-tracing paths.
- **`trace.getTracer` without a registered provider returns a no-op tracer**: always call `provider.register()` before any `trace.getTracer()` call. In the pattern above, `register()` is called inside `createProvider`.
- **Clock skew across Workers**: each Worker instance has its own high-resolution clock. Span timestamps may drift by a few microseconds. OTLP backends tolerate this; trace viewers show relative durations, not absolute wall-clock times.

## Verification

```bash
# Deploy and send a test request with a synthetic traceparent.
curl -s https://api.example.com/users/me \
  -H "Authorization: Bearer test" \
  -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

# Check Honeycomb for spans (replace with your backend's UI).
# The trace ID 4bf92f3577b34da6a3ce929d0e0e4736 should appear with
# child spans: auth.verify, d1.users.lookup, kv.get.

# Verify the OTLP endpoint received the export.
npx wrangler tail --format pretty 2>&1 | grep -i otlp

# If using Grafana Tempo, query by trace ID:
curl -s "http://tempo:3100/api/traces/4bf92f3577b34da6a3ce929d0e0e4736" | jq '.batches[].scopeSpans[].spans[].name'
```

## Related

- `documentation/categories/monitoring/workers-log-sampling-strategy.md` — sampling policies
- `documentation/categories/monitoring/synthetic-monitoring-playwright.md` — end-to-end traces
- `documentation/categories/monitoring/cost-per-request-tracking.md` — span-level cost attribution

## Sources

- OpenTelemetry JS SDK — https://github.com/open-telemetry/opentelemetry-js
- OTLP JSON encoding — https://opentelemetry.io/docs/specs/otlp/#json-encoding
- W3C Trace Context — https://www.w3.org/TR/trace-context/
- Cloudflare Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Workers bundle size limits — https://developers.cloudflare.com/workers/platform/limits/#worker-size
