# Cloudflare Snippets Latency Impact vs Full Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A full Cloudflare Worker is deployed to handle simple header rewrites and redirect rules, adding 5–15 ms of latency per request even when no KV, D1, or R2 reads are needed. At 10 M+ requests/day, the cost of running a full Worker for lightweight edge logic is both a latency concern and a billing concern. You need sub-millisecond request mutation without the overhead of a full Worker execution context.

## Context

Cloudflare Snippets are a lightweight execution tier that runs JavaScript at the edge for request/response mutation tasks — header injection, redirects, token stripping, A/B routing flags — with sub-millisecond overhead. Unlike Workers, Snippets have no access to KV, D1, R2, Queues, or Durable Objects bindings. They are designed to run before or instead of a Worker on simple paths, and their per-request cost is a small fraction of a Worker invocation. For requests that require data access, the fast path uses a Snippet for the cheap work and delegates to a Worker subrequest only when data is needed.

## Snippets for Fast-Path Header Rewriting

```javascript
// cloudflare-snippet.js — deployed as a Snippet rule in the Cloudflare dashboard
// No bindings, no async I/O — pure synchronous header mutation.
export default {
  async fetch(request) {
    const url = new URL(request.url);

    // Fast redirect: no Worker round-trip needed
    if (url.pathname === '/old-path') {
      return Response.redirect(
        `${url.origin}/new-path${url.search}`,
        301
      );
    }

    // Strip internal headers before forwarding to origin
    const mutableReq = new Request(request);
    mutableReq.headers.delete('X-Internal-Token');
    mutableReq.headers.set('X-Edge-Region', request.cf?.colo ?? 'unknown');
    mutableReq.headers.set('X-Request-Id',  crypto.randomUUID());

    return fetch(mutableReq);
  },
};
```

## Full Worker for Data-Path Requests

```typescript
// src/index.ts — Worker handles requests needing D1/R2/KV
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Only requests reaching here need data bindings.
    // The Snippet handled lightweight cases upstream.
    if (url.pathname.startsWith('/api/')) {
      const start = Date.now();
      const row = await env.DB
        .prepare('SELECT * FROM resources WHERE slug = ?1')
        .bind(url.pathname.replace('/api/', ''))
        .first();

      const elapsed = Date.now() - start;
      const resp = row
        ? Response.json(row)
        : new Response('Not Found', { status: 404 });

      resp.headers.set('Server-Timing', `d1;dur=${elapsed}`);
      return resp;
    }

    return new Response('Not Found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

## Measuring Added Latency Per Layer

Use `cf-cache-status` and `server-timing` headers to attribute latency to each layer:

```bash
# Check cache status and server timing on a Snippet-handled request
curl -sI https://example.com/old-path | grep -E '(cf-cache-status|server-timing|location)'
# Expected:
#   Location: https://example.com/new-path
#   cf-cache-status: MISS  (Snippets bypass cache layer)

# Check latency on a Worker-handled API request
curl -so /dev/null -w 'Total: %{time_total}s\nTTFB: %{time_starttransfer}s\n' \
  https://example.com/api/my-resource

# Worker request with server-timing breakdown
curl -sI https://example.com/api/my-resource | grep server-timing
# Expected: server-timing: d1;dur=5
```

## Snippets vs Workers: Capability and Cost Comparison

| Capability                 | Snippet        | Worker          |
|----------------------------|----------------|-----------------|
| Header read/write          | Yes            | Yes             |
| Redirect                   | Yes            | Yes             |
| KV / D1 / R2 bindings      | No             | Yes             |
| Durable Objects            | No             | Yes             |
| Async subrequests (fetch)  | Yes (limited)  | Yes             |
| Added p50 latency          | <0.5 ms        | 1–5 ms          |
| Added p99 latency          | <2 ms          | 8–20 ms         |
| Cost at 10 M req/day       | ~$0/day        | ~$3–5/day       |

## Combining Snippets + Workers for Hybrid Paths

Route strategy: deploy a Snippet rule matching `/static/*` and `/redirect/*` paths for zero-overhead edge handling. Set a Worker route matching `/api/*` for data-bound requests. Snippets execute before Workers in the request pipeline, so the Snippet can also inject a request header (`X-Fast-Path: true`) that the Worker reads to skip redundant header processing.

## Anti-patterns

- **Using a full Worker for pure redirect logic** — adds 5–15 ms latency and unnecessary billing for a task Snippets handle for free.
- **Attempting KV reads inside a Snippet** — Snippets have no binding support; the call will throw at runtime.
- **Deploying Snippets to replace Workers for A/B testing that reads user profiles** — profile reads require D1/KV; keep those in a Worker, use Snippets only for the cookie-flag read.

## Gotchas

- Snippets are configured via Cloudflare dashboard rules or Terraform, not `wrangler.toml`; they are not part of the Workers deploy pipeline.
- Snippet execution order relative to other HTTP rules (Transform Rules, Redirect Rules) matters — verify execution order in the Rules dashboard.
- `request.cf` is available inside Snippets for geo/colo data; `crypto.randomUUID()` is also available.
- Snippets have a stricter CPU time budget than Workers; avoid loops over large arrays.

## Verification

```bash
# Verify Snippet redirect latency (should be < 2 ms TTFB)
curl -so /dev/null -w 'TTFB: %{time_starttransfer}s\n' https://example.com/old-path

# Confirm Worker adds Server-Timing data for D1 queries
curl -sI https://example.com/api/resource | grep -i server-timing

# Compare TTFB for Snippet-handled vs Worker-handled paths
for path in /old-path /api/resource; do
  echo -n "$path: "; curl -so /dev/null -w '%{time_starttransfer}s\n' "https://example.com$path"
done
```

## Related

- `workers-module-lazy-binding-performance.md`
- `d1-prepared-statement-cache-performance.md`

## Sources

- Cloudflare Snippets — https://developers.cloudflare.com/rules/snippets/
- Cloudflare Workers Pricing — https://developers.cloudflare.com/workers/platform/pricing/
- Server-Timing Header (MDN) — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Server-Timing
