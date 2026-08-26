# Workers Isolate Singleton Warm-Pool Pattern

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker performs expensive initialization on every cold start — loading a WASM
module, building an in-memory trie, connecting to a remote schema registry — and that cost
shows up as a spike in P99 wall-clock time even though the CPU time budget is fine. The
standard "lazy init" approach initialises once per isolate but gives no control over how many
live isolates the runtime keeps warm or how quickly they retire.

---

## Context

Each Workers isolate is a V8 isolate running inside a Cloudflare PoP. The runtime recycles
isolates aggressively: after a period of inactivity (typically 30–180 s in practice, though
not contractually defined) an isolate is evicted. Module-scope variables survive for the
lifetime of a single isolate but die with it.

When the underlying resource — a compiled WASM binary, a parsed JSON schema, an SDK client
with an established TCP connection — takes >10 ms to rebuild, every new isolate pays that
cost on its first request. The warm-pool pattern keeps at least one primed copy alive by
using a lightweight heartbeat scheduled via `Durable Objects` or `Cron Triggers`, while
sharing the expensive singleton across all requests served by the same isolate.

Key distinctions versus sibling articles:
- `workers-module-scope-memoization.md` covers the basic "compute once, cache in closure"
  pattern. This article covers the fleet-level strategy for ensuring isolates are kept warm.
- `workers-cold-start-optimization.md` covers reducing what runs at import time. This article
  covers keeping isolates alive so that initialization rarely runs at all.

---

## Module-scope singleton (baseline)

```typescript
// src/singleton.ts
import { init as initWasm } from './vendor/engine.wasm';

interface Singleton {
  engine: ReturnType<typeof initWasm>;
  createdAt: number;
}

let _instance: Singleton | null = null;

export function getSingleton(): Singleton {
  if (!_instance) {
    // Runs once per isolate lifetime
    _instance = { engine: initWasm(), createdAt: Date.now() };
  }
  return _instance;
}
```

The singleton lives for the life of the isolate. The problem is that when the isolate is
evicted, the next cold start re-pays `initWasm()` cost in the critical path of a real request.

---

## Heartbeat Cron Trigger to keep isolates warm

A Cron Trigger firing every 30 s issues a no-op internal request that causes the runtime to
exercise the module, keeping the isolate alive without serving a user request.

```typescript
// wrangler.toml
// [triggers]
// crons = ["*/1 * * * *"]   ← every minute is the minimum; sub-minute not supported

// src/worker.ts
import { getSingleton } from './singleton';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { engine } = getSingleton();
    return engine.handle(request, env);
  },

  async scheduled(_event: ScheduledEvent, _env: Env, ctx: ExecutionContext): Promise<void> {
    // Touch the singleton so this isolate stays warmed
    const s = getSingleton();
    ctx.waitUntil(Promise.resolve(s.createdAt));
  },
};
```

The `scheduled` handler fires in the same isolate pool as the `fetch` handler, so the warm
isolate that handled the last real request receives the heartbeat and does not get evicted.

---

## Durable Object-backed warm pool (multi-isolate)

For workloads that need N warm isolates (e.g., you serve >1 req/s from a single PoP),
use a Durable Object to issue synthetic warm requests at a controlled cadence.

```typescript
// src/warmer.ts
export class IsolateWarmer implements DurableObject {
  private readonly env: Env;

  constructor(_state: DurableObjectState, env: Env) {
    this.env = env;
  }

  async fetch(_request: Request): Promise<Response> {
    // Fan out N synthetic pings to the main worker to touch N isolates
    const POOL_SIZE = 4;
    const pings = Array.from({ length: POOL_SIZE }, (_, i) =>
      this.env.MAIN_WORKER.fetch(
        new Request(`https://internal/warm?slot=${i}`, {
          headers: { 'X-Internal-Warm': '1' },
        })
      )
    );
    await Promise.allSettled(pings);
    return new Response('ok');
  }
}
```

```typescript
// src/worker.ts  (main worker — handles warm pings cheaply)
import { getSingleton } from './singleton';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.headers.get('X-Internal-Warm') === '1') {
      getSingleton(); // touch the singleton, respond immediately
      return new Response(null, { status: 204 });
    }
    const { engine } = getSingleton();
    return engine.handle(request, env);
  },
};
```

---

## Stale singleton refresh without cold-start penalty

Some singletons become stale (e.g., a cached config fetched at init time). Refresh
asynchronously with `waitUntil` so the refresh never blocks a request.

```typescript
// src/singleton.ts
const MAX_AGE_MS = 5 * 60 * 1000; // 5 minutes

export function getSingleton(ctx: ExecutionContext): Singleton {
  if (!_instance) {
    _instance = { engine: initWasm(), createdAt: Date.now() };
  }
  const age = Date.now() - _instance.createdAt;
  if (age > MAX_AGE_MS) {
    // Refresh without blocking the current request
    ctx.waitUntil(
      (async () => {
        _instance = { engine: initWasm(), createdAt: Date.now() };
      })()
    );
  }
  return _instance;
}
```

The request continues to use the existing (potentially stale) instance; the refresh happens
after the response is sent.

---

## Measuring isolate age via telemetry

Tag each request with the age of the current isolate so you can correlate P99 spikes with
cold starts:

```typescript
import { getSingleton } from './singleton';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const s = getSingleton(ctx);
    const isolateAgeMs = Date.now() - s.createdAt;
    const response = await s.engine.handle(request, env);

    // Clone to append header (Workers Response is immutable)
    return new Response(response.body, {
      status: response.status,
      headers: {
        ...Object.fromEntries(response.headers),
        'X-Isolate-Age-Ms': String(isolateAgeMs),
      },
    });
  },
};
```

In Workers Analytics Engine or Tail Workers, bucket `isolateAgeMs < 100` as "warm" and
`isolateAgeMs >= 100` (effectively zero, since fresh isolates start with age ~0 from init
to first request) is not useful — instead look for the bimodal distribution in init cost.

---

## Anti-patterns

- **Storing mutable user state in module scope.** Isolates are shared across requests; any
  per-request state stored at module scope leaks between users.
- **Assuming one isolate per PoP.** The runtime may create many isolates concurrently; the
  warm-pool approach increases the probability that a given request hits a warm isolate, it
  does not guarantee it.
- **Using `caches.default` as a warm-pool substitute.** The Cache API persists across
  requests but does not keep the isolate or its JS heap alive.
- **Over-aggressive heartbeat cadence.** Sub-minute Cron Triggers are not supported. For
  tighter SLAs, use Smart Placement or a dedicated DO alarm.

---

## Gotchas

- Cloudflare does **not** document isolate eviction timing as an SLA; treat any warm-pool
  strategy as a best-effort latency optimization, not a guarantee.
- The DO `IsolateWarmer` pattern counts against your DO request quota.
- `X-Internal-Warm` is a convention; apply proper `env.INTERNAL_SECRET` validation in
  production to prevent external callers from triggering warm pings.
- WASM modules cached in module scope still count against the 128 MB isolate memory limit;
  monitor via `cf-meta` headers or Workers Metrics.

---

## Verification

```bash
# Tail the worker and look for isolate-age distribution
wrangler tail --format=pretty | grep 'X-Isolate-Age-Ms'

# Synthetic cold-start measurement: evict by waiting, then time first request
sleep 300 && curl -w "\n%{time_total}s\n" https://your-worker.workers.dev/probe
```

Plot `isolateAgeMs` as a histogram in Workers Analytics Engine; a healthy warm-pool shows
the vast majority of requests with age > 30 000 ms (long-lived isolate) and only a small
fraction near 0 (genuine cold starts).

---

## Related

- `workers-cold-start-optimization.md`
- `workers-module-scope-memoization.md`
- `workers-module-initialization-lazy-loading.md`
- `durable-objects-alarm-write-coalescing.md`
- `workers-wasm-module-caching.md`

---

## Sources

- Cloudflare Workers runtime behaviour: https://developers.cloudflare.com/workers/reference/how-workers-works/
- Durable Objects: https://developers.cloudflare.com/durable-objects/
- Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Workers Memory limits: https://developers.cloudflare.com/workers/platform/limits/
