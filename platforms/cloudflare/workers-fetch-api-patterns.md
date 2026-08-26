# workers-fetch-api-patterns

**Issue:** Common patterns and pitfalls when using the Fetch API inside Cloudflare Workers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workers use the standard Fetch API to make subrequests, but there are several Worker-specific behaviours that differ from browser fetch: subrequest limits, keepalive semantics, and how `cf` options work.

## Pattern / Solution

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Basic subrequest with cf options
    const res = await fetch('https://api.example.com/data', {
      headers: { Authorization: `Bearer ${env.API_TOKEN}` },
      cf: {
        cacheTtl: 300,          // cache at Cloudflare edge for 5 min
        cacheEverything: true,  // cache even non-standard content types
      },
    });

    // Clone before consuming body (body is a ReadableStream — one read only)
    const clone = res.clone();
    const json = await res.json();
    console.log(await clone.text()); // would throw without clone

    // Pass-through with modified headers
    const modified = new Response(res.body, res);
    modified.headers.set('X-Served-By', 'worker');
    return modified;
  },
};

// Parallel subrequests — Workers allow up to 6 concurrent outbound connections
// per isolate (50 total subrequests per request in the free plan, 1000 on paid)
async function parallel(urls: string[]) {
  const results = await Promise.all(urls.map(u => fetch(u)));
  return Promise.all(results.map(r => r.json()));
}

// Streaming passthrough — do NOT await the body before forwarding
async function streamProxy(request: Request): Promise<Response> {
  const upstream = await fetch('https://upstream.example.com', {
    method: request.method,
    headers: request.headers,
    body: request.body,          // pipe body directly, no buffering
    duplex: 'half',              // required when body is a stream
  });
  return upstream;
}
```

## Gotchas
- A `Request` or `Response` body can only be consumed **once**; call `.clone()` before reading if you need it twice.
- `fetch()` inside a Worker does **not** follow the browser Same-Origin Policy but does count against the subrequest budget.
- Subrequest limit: 50 (free) / 1000 (paid) per incoming request. Recursive Worker calls count towards this.
- Setting `cf.cacheKey` lets you store responses under an arbitrary cache key instead of the URL.
- `duplex: 'half'` is required when forwarding a streaming request body; omitting it buffers the entire body first.
- Avoid `await fetch(...)` inside a `waitUntil` if you need the response — `waitUntil` runs after the response is sent and its return value is ignored.

## Related
- `workers-streaming-responses.md`
- `workers-cache-api.md`
- `workers-best-practices.md`
