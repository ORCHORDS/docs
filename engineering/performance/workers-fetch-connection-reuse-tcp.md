# TCP Connection Reuse and Fetch Optimization in Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Worker that makes repeated `fetch()` calls to the same upstream host experiences
50–150 ms of overhead on each request due to TLS handshakes and TCP slow-start. Under
moderate load this overhead compounds: 10 subrequests to the same host at 120 ms TLS
overhead each adds 1.2 seconds of pure handshake time to every Worker invocation. The
fix is understanding how the Workers runtime manages connection pooling, how to
structure requests to maximise reuse, and which header choices prevent connection
sharing.

## Context

The Cloudflare Workers runtime maintains a **per-datacenter connection pool** shared
across all Worker invocations in that PoP. Connections to a given `host:port` tuple
are kept alive between invocations and reused when a new `fetch()` targets the same
host. This means connection reuse is largely automatic — but several common coding
patterns accidentally defeat it. Understanding the mechanism lets you write Workers
that benefit from the warm-connection pool rather than constantly paying TLS setup
costs. The runtime uses HTTP/2 multiplexing where the upstream supports it, further
amortising handshake cost across concurrent subrequests.

## Verifying Connection Reuse with Server-Timing

The first diagnostic step is measuring whether the TLS handshake occurs on each call.
Expose timing via `server-timing` headers or Workers observability:

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const timings: string[] = [];

    for (let i = 0; i < 3; i++) {
      const t0 = Date.now();
      const r = await fetch("https://api.example.com/data");
      await r.arrayBuffer(); // drain body to release connection back to pool
      timings.push(`req${i};dur=${Date.now() - t0}`);
    }

    return new Response("ok", {
      headers: { "server-timing": timings.join(", ") },
    });
  },
};
```

On a warm pool the second and third calls will be 40–80 ms faster than the first
(the first pays TLS setup; subsequent calls reuse the TCP session). If all three are
within 5 ms of each other the pool is not being used — investigate the patterns below.

## Patterns That Enable Connection Reuse

**Keep the URL host stable.** Connection pooling is keyed on `host:port`. If your code
dynamically builds URLs with different subdomains per request (e.g., shard-based routing
via `shard-${id}.api.example.com`), each shard gets a separate pool entry and the
amortisation benefit shrinks proportionally.

```typescript
// GOOD: fixed host, varied path — same pool entry
const res = await fetch(`https://api.example.com/items/${itemId}`);

// BAD: varied host — new TLS handshake per shard
const res = await fetch(`https://shard-${shardId}.api.example.com/items/${itemId}`);
```

**Drain response bodies before returning from the Worker.** Leaving a response body
unconsumed holds the underlying TCP connection open until the runtime garbage-collects
it. The connection cannot return to the pool in a clean state. Always call one of:
- `await res.arrayBuffer()`
- `await res.text()`
- `await res.json()`
- `await res.body?.cancel()`

```typescript
async function safeFetch(url: string): Promise<unknown> {
  const res = await fetch(url);
  if (!res.ok) {
    await res.body?.cancel(); // release connection on error path too
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json(); // drains body, returns connection to pool
}
```

**Avoid per-request `Connection: close` headers.** Sending this header instructs the
server to terminate the TCP connection after the response, defeating keep-alive.

```typescript
// BAD: forces connection teardown
const res = await fetch(url, {
  headers: { connection: "close" },
});

// GOOD: omit the header entirely; the runtime defaults to keep-alive
const res = await fetch(url);
```

## HTTP/2 Multiplexing for Parallel Subrequests

When the upstream supports HTTP/2, the Workers runtime multiplexes multiple concurrent
`fetch()` calls over a single TCP+TLS connection. This is even more efficient than
connection reuse because it avoids head-of-line blocking at the TCP level.

```typescript
// These three requests travel over a single HTTP/2 connection if the upstream
// supports HTTP/2 — zero additional handshake cost
const [a, b, c] = await Promise.all([
  fetch("https://api.example.com/resource/1"),
  fetch("https://api.example.com/resource/2"),
  fetch("https://api.example.com/resource/3"),
]);
```

To verify HTTP/2 is in use, check the `alt-svc` response header from the upstream or
inspect the `cf-cache-status` and protocol fields in Workers Logs.

## Prewarming the Connection Pool with waitUntil

On a cold Worker startup (new isolate), the first request to any upstream host pays the
full TLS handshake cost. You can prewarm the pool using `waitUntil` on the previous
request, causing the next invocation's connection to be ready before the request
arrives.

```typescript
let poolWarmed = false;

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const result = await fetch("https://api.example.com/data");
    const body = await result.json();

    if (!poolWarmed) {
      // Fire a HEAD request to prewarm for the next invocation
      ctx.waitUntil(
        fetch("https://api.example.com/health", { method: "HEAD" })
          .then((r) => r.body?.cancel())
          .then(() => { poolWarmed = true; })
      );
    }

    return Response.json(body);
  },
};
```

`waitUntil` executes after the response is sent, so it adds no latency to the current
request. The connection established by the HEAD request remains in the pool and is
available to the next invocation in the same isolate.

## Service Bindings vs External fetch

For Worker-to-Worker calls within the same account, service bindings (`env.MY_SERVICE`)
bypass the public internet entirely. They use an in-process RPC mechanism with no TCP
overhead at all — latency is typically under 1 ms vs 20–150 ms for an external fetch.

```typescript
interface Env {
  PRODUCT_SERVICE: Fetcher; // service binding
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // Zero TCP overhead — stays inside Cloudflare's internal fabric
    const productRes = await env.PRODUCT_SERVICE.fetch(
      new Request("https://product-service/items/42")
    );
    return productRes;
  },
};
```

Use service bindings for any Worker-to-Worker communication; reserve external `fetch()`
for third-party or customer-hosted origins.

## Anti-patterns

**Building a new `Headers` object with `content-length` set manually** — some HTTP/1.1
legacy code sets `content-length` as a signal to close after the body. Workers targets
HTTP/1.1 keep-alive and HTTP/2 by default; manual content-length on a fetch request
body is usually redundant and occasionally incorrect.

**Using unique `User-Agent` strings per request** — some API clients append request IDs
to `User-Agent`. This does not affect connection pooling (pooling is host-keyed, not
header-keyed), but it does prevent Cloudflare's cache from coalescing identical requests.

**Ignoring TLS certificate errors with `rejectUnauthorized: false`** — not applicable in
Workers (there is no such option), but worth noting that Workers enforces TLS certificate
validation on all subrequests. Upstream services with self-signed certs must use
Cloudflare Tunnel or present a valid certificate.

**Creating a new `fetch` wrapper that rebuilds the `Request` object unnecessarily** —
reconstructing a `Request` from scratch loses the original body stream and forces the
runtime to re-resolve DNS for the host on some implementations.

## Gotchas

- Connection pool state is **per-PoP and per-isolate**. A Worker invocation in
  Frankfurt does not share the pool with one in Singapore. Cold-start isolates also
  start with an empty pool.
- The Workers runtime limits the connection pool size per host. Very high concurrency
  to a single upstream (hundreds of simultaneous Worker invocations) may still pay
  handshake costs when the pool is exhausted.
- `fetch()` with `keep-alive: false` in the `headers` map is silently ignored by the
  runtime; connection lifecycle is managed internally and cannot be forced closed by
  user code.
- HTTP/3 (QUIC) between Workers and upstreams is not currently supported. HTTP/2 is
  the highest protocol version for outbound subrequests.

## Verification

```bash
# Use wrangler tail to observe subrequest timing fields
wrangler tail MY_WORKER --format json | \
  jq '.logs[] | select(.message | test("subrequest"))'

# From an upstream nginx, check if keep-alive connections are being reused
tail -f /var/log/nginx/access.log | grep "HTTP/2"
```

Add `server-timing` probes around sequential fetches to the same host and confirm the
second call is at least 40 ms faster than the first on a warm pool.

## Related

- `workers-subrequest-fanout-parallelism.md`
- `tls-handshake-0rtt-resumption.md`
- `http2-multiplexing.md`
- `workers-cold-start-optimization.md`
- `latency-budget-allocation.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/workers/observability/logs/workers-logs/
- https://developers.cloudflare.com/workers/platform/limits/#fetch-requests
