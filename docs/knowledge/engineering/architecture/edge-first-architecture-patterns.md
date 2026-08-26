# Edge-First Architecture Patterns

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Every request reaches an origin server regardless of whether
it needs dynamic data. Geo-redirect, A/B assignment, JWT
validation, and rate-limiting logic all add a full round-trip
that multiplies tail latency for users far from the origin.

## Context

Edge-first architecture moves request-handling logic from a
single origin data-center into a distributed network of edge
nodes (Cloudflare Workers). Workers run within ~50 ms of most
internet users, handle TLS termination, and can read/write
edge-local stores (KV, Durable Objects) without phoning home.
The pattern combines a Next.js frontend deployed on Pages with
Workers acting as an API gateway layer in front of D1.

## Worker-as-API-Gateway Pattern

The Worker intercepts every inbound request, validates tokens,
enforces rate limits, rewrites paths, and fans out to origin
or D1 only when the edge cache cannot satisfy the request.

```typescript
// src/worker/gateway.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const token = req.headers.get("Authorization");
    if (!token) {
      return new Response("Unauthorized", { status: 401 });
    }
    const valid = await verifyJWT(token, env.JWT_SECRET);
    if (!valid) {
      return new Response("Forbidden", { status: 403 });
    }
    // Forward to origin with tenant header injected
    const next = new Request(req);
    next.headers.set("X-Tenant-ID", valid.tenantId);
    return env.ORIGIN.fetch(next);
  },
};
```

```toml
# wrangler.toml
[[routes]]
pattern = "api.example.com/*"
zone_name = "example.com"
```

## Request Collapsing

Cache misses under traffic cause a thundering herd of
identical origin fetches. Collapse them using a Durable
Object keyed on the cache-key, so only one isolate calls
origin while the rest await the result.

```typescript
// One DO per unique cache key collapses concurrent misses
const id = env.COLLAPSER.idFromName(cacheKey);
const stub = env.COLLAPSER.get(id);
return stub.fetch(req);
```

The DO's `fetch` handler tracks whether a real origin call
is in flight; subsequent callers subscribe via a stored
`Promise` and receive the same response body.

## Geo-Aware Routing

Workers expose Cloudflare request metadata on every request.

| Property      | Example | Use case                       |
|---------------|---------|--------------------------------|
| cf.country    | DE      | GDPR residency enforcement     |
| cf.colo       | FRA     | Route to nearest D1 read clone |
| cf.region     | Europe  | A/B test cohort assignment     |
| cf.timezone   | CET     | Locale-aware responses         |

Route EU traffic to an EU D1 replica and APAC traffic to a
Singapore origin; keep US traffic on the primary D1.

## When Edge Compute Is the Wrong Choice

Workers must return within a CPU-time budget
(10–30 ms free tier; up to 30 s on paid). Avoid edge for:

- Long-running jobs: video transcoding, PDF generation
- Stateful auth flows requiring server-side session affinity
- Workloads needing full Node.js APIs (native addons, `fs`)
- Multi-table atomic transactions in D1 — no distributed
  transactions exist across edge and origin
- Streaming responses longer than the CPU time limit allows

## Anti-patterns

- Fetching secrets from origin on every request edge handle.
  Cache them in Workers KV with a short TTL instead.
- Running business logic that depends on strongly-consistent
  DB state without modeling the consistency window; stale
  KV reads can be up to 60 s behind.
- Deploying edge Workers purely for perceived speed without
  measuring P95 improvement; cold-start isolates add ~5 ms
  on infrequently hit routes.
- Mixing edge-issued session cookies with origin sessions
  without a shared token store, causing auth split-brain.
- Logging PII in `console.log` inside Workers — logs are
  streamed via `wrangler tail` and may be retained.

## Gotchas

- Workers do not share heap between invocations; global
  variables persist within an isolate's lifetime but are
  reset on isolate eviction without warning.
- `waitUntil` callbacks execute after the response is sent;
  exceptions inside them are silent unless instrumented.
- D1 read replicas can lag the primary by seconds; design
  read paths to tolerate eventual consistency.
- Binding names in `wrangler.toml` must match the `Env`
  interface exactly — TypeScript will not catch a mismatch
  until runtime.

## Verification

- Deploy a canary Worker and inspect `cf-cache-status` and
  `server-timing` response headers to confirm edge hit rates.
- Run `wrangler dev --remote` to exercise the Worker against
  real KV and D1 bindings, not local stubs.
- Compare P50/P95 latency before and after migration using
  Cloudflare Analytics or your APM of choice.
- Assert that JWT validation rejects a tampered token via an
  integration test that bypasses the Next.js layer.

## Related

- architecture/api-gateway-patterns-rate-limiting-routing.md
- architecture/serverless-architecture.md
- architecture/cdn-architecture.md
- cloudflare/workers-kv-patterns.md
- architecture/function-as-a-service-patterns.md

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/workers/runtime-apis/\
request/#incomingrequestcfproperties
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/observability/\
logging/logpush/
