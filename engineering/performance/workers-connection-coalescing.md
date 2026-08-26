# HTTP Connection Coalescing and Keep-Alive Optimisation in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A single Worker request fans out to multiple upstream services (database proxy,
auth service, media CDN, analytics collector). Each subrequest opens a new TCP
connection, paying the full TCP + TLS handshake cost. Round-trip latency
accumulates when those calls are serialised.

Common signals:
- Worker CPU time looks low but wall-clock latency is high (> 300 ms).
- Cloudflare trace shows many small subrequest spans separated by idle gaps.
- `CF-Ray` log shows `subrequest_count` near the per-isolate limit (currently 50
  for free, 1 000 for paid plans).

---

## Context

Cloudflare Workers share a connection pool scoped to the isolate (not the
request). Connections to the same `host:port` origin are reused across requests
within the same isolate, functioning like HTTP/1.1 keep-alive or HTTP/2
multiplexing. The key insight: **concurrent subrequests to the same origin are
more efficient than sequential ones** because they run over the same connection
and the origin can pipeline responses.

Connection coalescing means deliberately structuring your fetch calls so that:
1. Multiple requests to the same origin are issued in parallel.
2. Requests to different origins are batched into a single composite API call
   where the upstream supports it.
3. Subrequest count is tracked to avoid hitting platform limits.

---

## Solution

```typescript
// connection-coalescing.ts
import type { ExecutionContext } from '@cloudflare/workers-types';

export interface Env {
  API_ORIGIN: string;    // e.g. https://internal-api.example.com
  AUTH_ORIGIN: string;   // e.g. https://auth.example.com
}

// ---------------------------------------------------------------------------
// Subrequest budget tracker
// Paid Workers plan limit: 1 000 subrequests per isolate invocation.
// We leave headroom for retries and non-critical background calls.
// ---------------------------------------------------------------------------
const SUBREQUEST_BUDGET = 20;

class SubrequestBudget {
  private used = 0;
  private readonly limit: number;

  constructor(limit = SUBREQUEST_BUDGET) {
    this.limit = limit;
  }

  consume(count = 1): void {
    this.used += count;
    if (this.used > this.limit) {
      throw new Error(
        `Subrequest budget exhausted: ${this.used}/${this.limit}`
      );
    }
  }

  get remaining(): number {
    return Math.max(0, this.limit - this.used);
  }
}

// ---------------------------------------------------------------------------
// Batch request helper
// Many REST and GraphQL APIs accept a batch endpoint that returns multiple
// resource payloads in one round-trip.
// ---------------------------------------------------------------------------

interface BatchItem<T> {
  id: string;
  result?: T;
  error?: string;
}

interface BatchResponse<T> {
  items: BatchItem<T>[];
}

async function batchFetch<T>(
  origin: string,
  endpoint: string,
  ids: string[],
  budget: SubrequestBudget,
  init?: RequestInit
): Promise<Map<string, T>> {
  budget.consume(1); // single subrequest for N items

  const resp = await fetch(`${origin}${endpoint}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...(init?.headers as Record<string, string>) },
    body: JSON.stringify({ ids }),
    ...init,
  });

  if (!resp.ok) {
    throw new Error(`Batch fetch failed: ${resp.status} ${resp.statusText}`);
  }

  const data: BatchResponse<T> = await resp.json();
  const map = new Map<string, T>();
  for (const item of data.items) {
    if (item.result !== undefined) {
      map.set(item.id, item.result);
    }
  }
  return map;
}

// ---------------------------------------------------------------------------
// Parallel fetch with budget guard
// Replaces sequential await chains that waste RTT time.
// ---------------------------------------------------------------------------

type FetchTask<T> = () => Promise<T>;

async function parallelFetch<T extends readonly unknown[]>(
  tasks: { [K in keyof T]: FetchTask<T[K]> },
  budget: SubrequestBudget
): Promise<{ [K in keyof T]: Awaited<T[K]> | Error }> {
  budget.consume(tasks.length);
  const results = await Promise.allSettled(tasks.map((t) => t()));
  return results.map((r) =>
    r.status === 'fulfilled' ? r.value : r.reason
  ) as { [K in keyof T]: Awaited<T[K]> | Error };
}

// ---------------------------------------------------------------------------
// RTT measurement via Performance API
// ---------------------------------------------------------------------------

interface RttSample {
  label: string;
  durationMs: number;
}

function measureAsync<T>(
  label: string,
  fn: () => Promise<T>
): Promise<[T, RttSample]> {
  const start = performance.now();
  return fn().then((result) => [
    result,
    { label, durationMs: performance.now() - start },
  ]);
}

// ---------------------------------------------------------------------------
// Example Worker: fetch track, artist, and licence in parallel
// ---------------------------------------------------------------------------

interface Track {
  id: string;
  title: string;
  artistId: string;
  licenceId: string;
}

interface Artist {
  id: string;
  name: string;
}

interface Licence {
  id: string;
  type: string;
  expiresAt: string;
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const trackId = url.searchParams.get('trackId');
    if (!trackId) {
      return new Response('Missing trackId', { status: 400 });
    }

    const budget = new SubrequestBudget();

    // Step 1: Fetch the primary resource (1 subrequest)
    const [track, trackRtt] = await measureAsync('track', async () => {
      budget.consume(1);
      const r = await fetch(`${env.API_ORIGIN}/tracks/${trackId}`, {
        headers: { authorization: request.headers.get('authorization') ?? '' },
      });
      if (!r.ok) throw new Error(`Track not found: ${r.status}`);
      return r.json() as Promise<Track>;
    });

    // Step 2: Fan-out to artist + licence in parallel (2 subrequests, same RTT)
    // Both calls target env.API_ORIGIN, so Workers reuses the existing connection.
    const [[artistResult, licenceResult], fanoutRtt] = await measureAsync(
      'fanout',
      () =>
        parallelFetch(
          [
            () =>
              fetch(`${env.API_ORIGIN}/artists/${track.artistId}`).then(
                (r) => r.json() as Promise<Artist>
              ),
            () =>
              fetch(`${env.API_ORIGIN}/licences/${track.licenceId}`).then(
                (r) => r.json() as Promise<Licence>
              ),
          ] as const,
          budget
        )
    );

    // Step 3: Optional batch call for related track IDs (1 subrequest for N items)
    const relatedIds = ['t2', 't3', 't4'];
    const relatedMap = await batchFetch<Track>(
      env.API_ORIGIN,
      '/tracks/batch',
      relatedIds,
      budget
    );

    const artist = artistResult instanceof Error ? null : artistResult;
    const licence = licenceResult instanceof Error ? null : licenceResult;

    const body = JSON.stringify({
      track,
      artist,
      licence,
      related: Array.from(relatedMap.values()),
      _debug: {
        subrequestsUsed: SUBREQUEST_BUDGET - budget.remaining,
        rtt: [trackRtt, fanoutRtt],
      },
    });

    return new Response(body, {
      headers: {
        'content-type': 'application/json',
        'cache-control': 'private, max-age=30',
      },
    });
  },
};
```

---

## Implementation Details

**Connection reuse across requests**: Within one isolate, Cloudflare Workers
pools TCP+TLS connections per `(origin host, port)` tuple. Two concurrent
fetches to `https://api.example.com` share a connection (HTTP/2 multiplexed)
or a keep-alive socket (HTTP/1.1). Sequential fetches also benefit if the first
response headers carry `Connection: keep-alive` and the isolate stays warm.

**Promise.all vs Promise.allSettled**: Use `allSettled` when partial failure is
acceptable (graceful degradation). Use `all` when all results are required and
you want to fail fast on the first rejection.

**Batch endpoints**: If the upstream supports a `/resources/batch` POST, a
single subrequest replaces N individual fetches. This dramatically reduces
subrequest count for high-fan-out patterns (e.g., fetching metadata for 50
playlist tracks).

**RTT measurement**: `performance.now()` in Workers returns a monotonic clock
with microsecond precision. Recording per-call RTTs surfaces the dominant
latency contributor without external tooling.

---

## Anti-patterns

- **Sequential await chain**: `const a = await fetchA(); const b = await fetchB()`
  wastes one full round-trip when A and B are independent. Always ask: "does B
  depend on A's result?" If not, issue both in parallel.
- **N+1 subrequests**: Fetching a list then individually fetching each item's
  detail is the classic N+1. Batch or include endpoints eliminate it.
- **Ignoring the subrequest limit**: On the free plan, 50 subrequests per
  invocation. Exceeding it silently drops subsequent fetches. Track consumption
  with a budget object.
- **Fetching the same URL twice**: Cache intermediate results in a request-scoped
  `Map` to avoid redundant subrequests within a single Worker invocation.

---

## Gotchas

- `fetch` in Workers does NOT support `keepalive: true` in `RequestInit` the
  same way browsers do. Connection reuse is managed automatically by the runtime.
- HTTP/2 multiplexing requires the upstream to speak HTTP/2. Many internal
  services use HTTP/1.1 even over TLS; in that case, parallel fetches still open
  separate connections, but Workers reuses them across isolate requests.
- `Promise.allSettled` does not throw; always check each result's `.status`
  before accessing `.value`.
- Subrequest limits are per-isolate-invocation, not per-Worker. A long-lived
  streaming response counts as one invocation.

---

## Verification

```bash
# Cloudflare trace shows subrequest timelines
wrangler tail --format json 2>/dev/null | jq '.logs[] | select(.level == "log")'

# Check CF-Ray subrequest_count in response headers (visible in Logpush)
# Look for _debug.rtt in the JSON response to compare sequential vs parallel RTT
curl -s 'https://api.example.com/v1/track-bundle?trackId=t1' | jq '._debug'
```

---

## Related

- `kv-bulk-prefetch-pattern.md` — Prefetching multiple KV keys in one round-trip
- `workers-cache-warming-strategy.md` — Avoiding origin fan-out with pre-warmed cache
- `workers-ttfb-optimization.md` — Reducing KV/D1 call count per request

---

## Sources

- [Cloudflare Workers — Subrequest limits](https://developers.cloudflare.com/workers/platform/limits/#subrequests)
- [Fetch API — MDN](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API)
- [HTTP/2 Multiplexing — RFC 9113](https://www.rfc-editor.org/rfc/rfc9113)
- [Performance API in Workers](https://developers.cloudflare.com/workers/runtime-apis/performance/)
