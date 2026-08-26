# Cloudflare Pages 522 Origin Timeout Debugging

2026-08-24 / example.com / production

---

## Symptom / Use-case

A Cloudflare Pages site or a Pages Function returns HTTP **522 (Connection Timed Out)** for some or all requests. The error page is served by Cloudflare's edge, not the origin application. Users see "Error 522: Connection timed out" with the Cloudflare rayID visible.

Common patterns:
- 522s appear only for Pages Functions routes, not for static asset routes on the same site
- 522s occur on specific geographical regions or PoPs but not others
- The error appears intermittently under normal load but consistently under any moderate traffic spike
- A Pages Function that calls a third-party API or a Worker via `fetch()` returns 522 when the upstream is slow

---

## Context

Error 522 in Cloudflare's error taxonomy means Cloudflare's edge **successfully established a TCP connection to the origin but the origin did not send an HTTP response within the timeout window**. For Cloudflare Pages:

- **Static assets** are served from Cloudflare's own edge cache — they cannot produce a 522
- **Pages Functions** execute as Workers at the edge. A 522 from a Pages Function means the Function itself is taking too long to return a `Response`, or the Function is making a `fetch()` to an external origin that is not responding in time
- The timeout Cloudflare applies before returning 522 is **100 seconds** for Workers/Pages Functions (the subrequest timeout)
- A Pages Function that performs a `waitUntil()` task after returning a Response cannot cause a 522 for that response, but a long-running background task that blocks the response *can*

The 522 error will **not** appear in your Pages Function's logs because the Function either never started, never returned, or Cloudflare gave up waiting before the log flush. Use Cloudflare's Workers Trace Events and Real User Monitoring (RUM) to correlate.

---

## Diagnosing 522s from Pages Functions

### Step 1 — Distinguish static vs. Function 522s by route

```typescript
// functions/_middleware.ts
// Add a header to every Function response to confirm the Function ran
export const onRequest: PagesFunction = async (context) => {
  const t0 = Date.now();
  const response = await context.next();

  // If this header appears in devtools, the Function responded; 522 is downstream
  const result = new Response(response.body, response);
  result.headers.set('X-Pages-Function-Ms', String(Date.now() - t0));
  return result;
};
```

If the 522 response does **not** carry `X-Pages-Function-Ms`, the Function never returned a response (timed out or never started). If it does carry the header, the 522 is from an upstream the Function depends on.

### Step 2 — Add hard timeouts to all external fetch calls

```typescript
// functions/api/data.ts
export const onRequestGet: PagesFunction<Env> = async (context) => {
  const controller = new AbortController();
  // Abort after 8 seconds to stay well within the 30s budget you want
  const timeout = setTimeout(() => controller.abort(), 8_000);

  try {
    const upstream = await fetch('https://api.example.com/data', {
      signal: controller.signal,
    });

    if (!upstream.ok) {
      return new Response(`upstream error: ${upstream.status}`, { status: 502 });
    }

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json',
        'Cache-Control': 'public, max-age=60',
      },
    });
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      return new Response('upstream timed out', { status: 504 });
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }
};
```

### Step 3 — Detect and short-circuit long-running init paths

```typescript
// functions/api/heavy.ts
// Module-level init that runs once per isolate cold start
let initPromise: Promise<void> | null = null;
let initData: Record<string, unknown> | null = null;

async function initialize(env: Env): Promise<void> {
  if (initData) return; // already initialized in this isolate
  const raw = await env.CONFIG_KV.get('heavy-config', { type: 'json' });
  initData = raw as Record<string, unknown>;
}

export const onRequestGet: PagesFunction<Env> = async (context) => {
  // Gate init on a deadline — don't let a slow KV read 522 every user
  const initDeadline = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error('init timeout')), 2_000)
  );

  try {
    await Promise.race([initialize(context.env), initDeadline]);
  } catch {
    // Serve a degraded response rather than timing out
    return new Response(JSON.stringify({ error: 'initializing', retry: true }), {
      status: 503,
      headers: { 'Retry-After': '2' },
    });
  }

  return new Response(JSON.stringify(initData), {
    headers: { 'Content-Type': 'application/json' },
  });
};
```

### Step 4 — Add route-level timing telemetry

```typescript
// functions/_middleware.ts (enhanced)
export const onRequest: PagesFunction<Env> = async (context) => {
  const routeStart = performance.now();
  const url = new URL(context.request.url);

  try {
    const response = await context.next();
    const elapsed = performance.now() - routeStart;

    // Warn if we're approaching the 100s limit
    if (elapsed > 5_000) {
      console.warn(JSON.stringify({
        level: 'warn',
        route: url.pathname,
        elapsed_ms: elapsed.toFixed(1),
        msg: 'slow Pages Function — risk of 522 under load',
      }));
    }

    return response;
  } catch (err) {
    const elapsed = performance.now() - routeStart;
    console.error(JSON.stringify({
      level: 'error',
      route: url.pathname,
      elapsed_ms: elapsed.toFixed(1),
      error: String(err),
    }));
    return new Response('internal error', { status: 500 });
  }
};
```

### Step 5 — Stream large responses instead of buffering

```typescript
// functions/api/export.ts
// BAD — buffers the entire response body before returning, can exhaust CPU/memory
export const onRequestGetBad: PagesFunction<Env> = async (context) => {
  const rows = await context.env.DB.prepare('SELECT * FROM large_table').all();
  return new Response(JSON.stringify(rows.results), {
    headers: { 'Content-Type': 'application/json' },
  });
};

// GOOD — streams rows as NDJSON, returns immediately and streams body
export const onRequestGet: PagesFunction<Env> = async (context) => {
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();

  context.waitUntil(
    (async () => {
      const stmt = context.env.DB.prepare('SELECT * FROM large_table');
      const { results } = await stmt.all();
      for (const row of results) {
        await writer.write(encoder.encode(JSON.stringify(row) + '\n'));
      }
      await writer.close();
    })()
  );

  return new Response(readable, {
    headers: { 'Content-Type': 'application/x-ndjson' },
  });
};
```

### Step 6 — Check for cold-start recursion via Worker-to-Worker fetch

```typescript
// functions/api/proxy.ts
// Calling env.MY_WORKER.fetch() can itself time out if MY_WORKER is cold
// and MY_WORKER in turn calls back into the Pages Function — circular dependency
export const onRequestGet: PagesFunction<Env> = async (context) => {
  // Always pass an AbortSignal when calling a bound Worker service
  const signal = AbortSignal.timeout(10_000);

  const workerResponse = await context.env.MY_WORKER.fetch(context.request, { signal });
  return workerResponse;
};
```

---

## Anti-patterns

- **Not setting timeouts on `fetch()` calls inside Pages Functions** — upstream services that take >100 s will cause a 522 that looks like a Cloudflare problem but is an application design issue.
- **Doing blocking work in a module-level initializer without a deadline** — slow KV reads, large JSON parses, or DNS lookups at module scope block the first request to each isolate and can push total response time past the timeout.
- **Streaming a response body but forgetting `context.waitUntil()`** — the runtime may terminate the isolate before the stream is complete if the async work is not registered with `waitUntil`.
- **Using `Response.json(bigArray)` for large datasets** — `JSON.stringify()` on a large array is synchronous and blocks the JS thread; it counts against both CPU time and wall-clock response time.
- **Routing all traffic through a single Pages Function that calls a single-region backend** — if that backend region has degraded connectivity to Cloudflare's PoP, 522s will be regional and hard to distinguish from platform issues.

---

## Gotchas

- Error 522 is emitted by Cloudflare's **edge**, not by your Function. The error page itself is not logged in your Pages Function logs; correlate using the rayID visible in the response body.
- A Pages Function that returns early but keeps the readable stream open for body delivery can still 522 if the body stream stalls — Cloudflare's timeout applies to the entire response, not just the headers.
- `setTimeout`/`setInterval` inside a Pages Function are subject to the same CPU and wall-clock constraints as the rest of the invocation; a 100 s `setTimeout` does not extend the Function's lifetime.
- Pages Functions that call a `env.BINDING` (Durable Object, Workers AI, etc.) can 522 if the binding itself times out. Each bound service call has its own timeout budget that shares the parent Function's wall-clock window.
- `wrangler pages dev` uses local simulation; timeout behavior in local dev does not match production. A Function that works locally in 5 s may 522 in production if cold-start + upstream latency push it past the limit.

---

## Verification

1. Deploy the middleware timing header (Step 1) and trigger the 522-producing route. Check whether the `X-Pages-Function-Ms` header is present in the 522 response — absent means the Function never returned.
2. Add the route-level timing logger (Step 4). Use `wrangler pages deployment tail` to stream live logs and identify which route segment is slow.
3. Reproduce the timeout artificially: add `await new Promise(r => setTimeout(r, 105_000))` to the Function and confirm a 522 is returned. Then verify that adding `AbortSignal.timeout(8_000)` prevents the 522 and returns a 504 instead.
4. Use Cloudflare's Speed → Observability dashboard to review Time to First Byte (TTFB) percentiles by route, identifying routes with p99 TTFB > 5 000 ms as 522 candidates.
5. Check Cloudflare Analytics → Pages for 5xx error rates by route to confirm the fix reduced 522 frequency.

---

## Related

- `pages-build-env-vars-vs-runtime.md`
- `worker-subrequest-limit.md`
- `worker-memory-limit-exceeded.md`
- `fetch-no-throw-on-4xx.md`

---

## Sources

- Cloudflare Support — Error 522: https://developers.cloudflare.com/support/troubleshooting/cloudflare-errors/troubleshooting-cloudflare-5xx-errors/#error-522-connection-timed-out
- Cloudflare Pages Functions: https://developers.cloudflare.com/pages/functions/
- Cloudflare Workers — Limits: https://developers.cloudflare.com/workers/platform/limits/
- Cloudflare Pages — Deployment tailing: https://developers.cloudflare.com/pages/functions/debugging-and-logging/
