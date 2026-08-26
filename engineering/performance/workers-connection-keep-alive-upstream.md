# Upstream Connection Keep-Alive and Reuse Optimisation in Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Every upstream `fetch()` call from a Worker adds 20–150 ms of TCP + TLS handshake latency on top of the actual data transfer time. Under high request rates this overhead is invisible in individual traces but adds up to significant aggregate latency and upstream connection churn. Some APIs rate-limit by connection count; others (legacy HTTP/1.1 backends) become a bottleneck because each Worker request opens a new TCP socket.

## Context

Cloudflare Workers are stateless and short-lived. Unlike a long-running Node.js process where an HTTP agent pools persistent connections, a Worker instance does not maintain a TCP connection pool between requests. However, there are several mechanisms to mitigate this:

1. **Cloudflare's implicit connection reuse** — The Workers runtime reuses TCP connections to the same origin at the PoP level across Worker instances. This is transparent and applies to most `fetch()` calls automatically.
2. **`keepalive` fetch option** — An explicit hint to the runtime to keep the connection alive after the response.
3. **Service Bindings as a connection proxy** — Route upstream calls through a dedicated proxy Worker that maintains a Durable Object connection pool.
4. **Durable Objects as TCP connection holders** — A DO can hold a `connect()` (Cloudflare Sockets) TCP socket open across requests, implementing true connection pooling for raw TCP protocols (databases, Redis).
5. **Retry-on-reset logic** — Reused connections can be reset by the upstream (`ECONNRESET`); Workers must detect and retry transparently.

## Solution

### Pattern 1 — Explicit keepalive hint on fetch

```typescript
// src/upstream-fetch.ts

export interface UpstreamOptions {
  timeout?: number; // ms, default 10000
  retries?: number; // default 2
}

/**
 * Fetch from an upstream service with keepalive hint, timeout, and retry on
 * connection reset (ECONNRESET / "socket hang up").
 */
export async function upstreamFetch(
  url: string | URL,
  init: RequestInit = {},
  opts: UpstreamOptions = {}
): Promise<Response> {
  const { timeout = 10_000, retries = 2 } = opts;

  const requestInit: RequestInit = {
    ...init,
    // keepalive signals the runtime to reuse the TCP connection for subsequent
    // requests to the same origin from this PoP.
    keepalive: true,
    signal: AbortSignal.timeout(timeout),
  };

  let lastError: unknown;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url, requestInit);
      return response;
    } catch (err) {
      lastError = err;
      const msg = String(err);

      // Only retry on connection-level errors — not on 4xx/5xx.
      const isReset =
        msg.includes('ECONNRESET') ||
        msg.includes('socket hang up') ||
        msg.includes('connection reset') ||
        msg.includes('network changed');

      if (!isReset || attempt === retries) {
        throw err;
      }

      // Brief backoff before retry (exponential, capped at 200 ms).
      const delay = Math.min(50 * 2 ** attempt, 200);
      await new Promise(r => setTimeout(r, delay));
    }
  }

  throw lastError;
}
```

### Pattern 2 — Service Binding as a connection proxy

Place a lightweight "upstream proxy" Worker behind a Service Binding. The proxy Worker's runtime instance at each PoP reuses TCP connections across calls from the calling Worker, because from the PoP's perspective the proxy Worker makes repeated requests to the same origin.

```typescript
// workers/upstream-proxy/src/index.ts
// Deployed as a separate Worker; bound via Service Binding in wrangler.toml.

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // Validate the target — never open-proxy arbitrary URLs.
    const allowedOrigins = new Set([
      'https://api.stripe.com',
      'https://api.sendgrid.com',
      'https://db.internal.example.com',
    ]);

    if (!allowedOrigins.has(url.origin)) {
      return new Response('Forbidden', { status: 403 });
    }

    return fetch(request, { keepalive: true });
  },
};
```

```toml
# wrangler.toml (calling Worker)
[[services]]
binding = "UPSTREAM_PROXY"
service = "upstream-proxy-worker"
```

```typescript
// src/worker.ts — calling Worker
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Route through the proxy Worker — connection reuse happens at the proxy.
    const proxyRequest = new Request(
      'https://api.stripe.com/v1/charges',
      {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${env.STRIPE_KEY}`,
        },
      }
    );

    return env.UPSTREAM_PROXY.fetch(proxyRequest);
  },
};
```

### Pattern 3 — Durable Object TCP connection pool (Cloudflare Sockets)

For raw TCP protocols (PostgreSQL, Redis, MySQL), a Durable Object can hold a `connect()` socket open and multiplex requests over it.

```typescript
// src/db-pool.ts
import { DurableObject } from 'cloudflare:workers';
import { connect } from 'cloudflare:sockets';
import type { Socket } from 'cloudflare:sockets';

const MAX_IDLE_MS = 60_000; // close idle socket after 60 s

export class DbPool extends DurableObject {
  private socket: Socket | null = null;
  private idleTimer: ReturnType<typeof setTimeout> | null = null;
  private host: string;
  private port: number;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.host = env.DB_HOST;
    this.port = parseInt(env.DB_PORT ?? '5432');
  }

  async fetch(request: Request): Promise<Response> {
    const body = await request.json() as { query: string; params: unknown[] };

    const socket = await this.getSocket();
    this.resetIdleTimer();

    try {
      // In a real implementation, use a pg wire-protocol library.
      // This illustrates the socket lifecycle management.
      const result = await executeQuery(socket, body.query, body.params);
      return Response.json({ rows: result });
    } catch (err) {
      // If the socket errored, discard it so the next call reconnects.
      this.socket = null;
      throw err;
    }
  }

  private async getSocket(): Promise<Socket> {
    if (this.socket) return this.socket;

    this.socket = connect(
      { hostname: this.host, port: this.port },
      { secureTransport: 'starttls', allowHalfOpen: false }
    );

    return this.socket;
  }

  private resetIdleTimer(): void {
    if (this.idleTimer) clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => {
      this.socket?.close();
      this.socket = null;
    }, MAX_IDLE_MS);
  }
}

// Placeholder — replace with actual pg wire protocol implementation.
async function executeQuery(
  socket: Socket,
  query: string,
  params: unknown[]
): Promise<Record<string, unknown>[]> {
  throw new Error('Implement pg wire protocol or use a library like pg-gateway');
}
```

```typescript
// Env types
export interface Env {
  DB_POOL: DurableObjectNamespace;
  DB_HOST: string;
  DB_PORT: string;
  UPSTREAM_PROXY: Fetcher;
  ANALYTICS: AnalyticsEngineDataset;
  STRIPE_KEY: string;
}
```

### Pattern 4 — Measuring upstream latency reduction

```typescript
// src/latency-instrumentation.ts
import { Env } from './types';

export async function timedFetch(
  url: string,
  init: RequestInit,
  env: Env,
  label: string
): Promise<Response> {
  const start = performance.now();
  let status = 0;

  try {
    const response = await fetch(url, { ...init, keepalive: true });
    status = response.status;
    return response;
  } finally {
    const latencyMs = performance.now() - start;

    env.ANALYTICS.writeDataPoint({
      blobs: [label, String(status)],
      doubles: [latencyMs],
      indexes: ['upstream_latency'],
    });
  }
}

// Usage:
const resp = await timedFetch(
  'https://api.stripe.com/v1/charges',
  { headers: { Authorization: `Bearer ${env.STRIPE_KEY}` } },
  env,
  'stripe'
);
```

### Pattern 5 — Upstream timeout configuration

```typescript
// src/timeout-config.ts

/** Per-upstream timeout budgets in ms. */
export const UPSTREAM_TIMEOUTS: Record<string, number> = {
  'api.stripe.com': 5_000,
  'api.sendgrid.com': 3_000,
  'fonts.googleapis.com': 2_000,
  default: 10_000,
};

export function timeoutForOrigin(url: string | URL): number {
  const hostname = new URL(url).hostname;
  return UPSTREAM_TIMEOUTS[hostname] ?? UPSTREAM_TIMEOUTS.default;
}

// Usage:
const timeout = timeoutForOrigin('https://api.stripe.com/v1/charges');
const response = await fetch(url, {
  signal: AbortSignal.timeout(timeout),
  keepalive: true,
});
```

## Implementation Details

**When keepalive actually helps.** Cloudflare Workers at each PoP share a connection pool to the same origin by default for HTTPS origins. The `keepalive: true` option is an explicit hint to the runtime but in many cases the PoP-level reuse already applies. The biggest gains come from:
1. Origins that close connections aggressively (short `keep-alive` timeouts).
2. Low-traffic origins where the idle connection was evicted between requests.
3. HTTP/1.1 origins that do not support connection multiplexing (no HTTP/2).

**DO socket pool sizing.** A single DO instance holds one socket. For higher throughput, use a pool of DO instances: `idFromName('pool-0')`, `idFromName('pool-1')`, ... `idFromName('pool-N-1')` and round-robin across them in the calling Worker.

**ECONNRESET on keep-alive connections.** A connection reused after idle time may be half-closed by the upstream. The retry logic in Pattern 1 handles this: the first request on a stale connection fails with `ECONNRESET`; the retry opens a fresh connection and succeeds.

**Service Binding latency.** A Service Binding call between two Workers in the same PoP is extremely fast (~0.1 ms overhead) — it is an in-process function call, not an actual HTTP request. This makes Service Bindings an efficient proxy layer.

## Anti-patterns

- **Setting timeouts too high.** A 30 s upstream timeout means a slow origin blocks 30 s of Worker CPU credit. Set per-upstream timeouts based on actual p99 latency with a 2–3× safety margin.
- **Retrying on all errors.** Only retry on connection-level errors (`ECONNRESET`, `ETIMEDOUT`). Retrying on `429 Too Many Requests` or `503 Service Unavailable` worsens the situation.
- **Opening a new DO for every request** when connection pooling is the goal. Use `idFromName` with a stable key so multiple Worker requests route to the same DO and share the socket.
- **Not closing idle sockets.** A DO with an open TCP socket prevents the DO from being evicted, consuming memory and connection slots at the upstream. Always set an idle timer.

## Gotchas

- `AbortSignal.timeout()` requires `compatibility_date >= 2023-03-01`.
- `keepalive` is a hint — the Workers runtime may ignore it if the connection pool is full or the upstream sends `Connection: close`.
- Cloudflare Sockets (`cloudflare:sockets`) are available in Workers on paid plans only. The `connect()` function is not available in the free tier.
- DO socket pools add complexity — instrument heavily with Analytics Engine before introducing them. For most HTTPS APIs, PoP-level connection reuse is sufficient.
- `performance.now()` in Workers returns wall-clock time relative to the Worker's startup; it does not include time before the Worker was invoked (TCP accept etc.).

## Verification

```bash
# Measure p50/p95 upstream latency before and after with Analytics Engine:
# SELECT percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms),
#        percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)
# FROM upstream_latency WHERE label = 'stripe' AND ts > now() - 1h;

# Confirm keepalive is working — look for reused connections in CF-Cache-Status
# or by comparing connection times across rapid sequential requests:
for i in {1..5}; do
  curl -o /dev/null -s -w "Connect: %{time_connect}s | Total: %{time_total}s\n" \
    https://your-worker.example.com/api/charges
done
# Subsequent requests should show time_connect ~0 (reused connection).

# Wrangler tail to watch retry logs:
wrangler tail --format json \
  | jq 'select(.logs[]?.message | test("ECONNRESET|retry"))'
```

Expect p95 upstream latency to drop by 20–80 ms per request when TCP reuse is effective.

## Related

- `workers-request-coalescing-durable-objects.md` — reduce the number of upstream requests entirely via coalescing.
- `workers-cache-api-fine-grained-control.md` — eliminate upstream calls for cacheable responses.
- `workers-streaming-response-time-to-first-byte.md` — once upstream latency is reduced, streaming amplifies the user-visible TTFB improvement.

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/platform/pricing/
- https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- https://developers.cloudflare.com/durable-objects/
