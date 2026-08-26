# Request Coalescing with Durable Objects

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Under burst traffic, multiple Workers instances simultaneously issue the same upstream fetch (e.g. a slow third-party API, a database read, or an expensive KV computation). Each concurrent request pays the full latency cost, the upstream sees N × the load, and rate-limit budgets drain quickly. The desired behaviour is that only **one** outgoing request flies while all other callers await the same result — a classic thundering-herd / cache-stampede fix.

## Context

Cloudflare Workers are stateless and isolated per-request. Two Workers handling two concurrent requests for `/api/prices` cannot share an in-process `Map` of pending promises the way a Node.js server can. Durable Objects (DOs) provide the missing shared mutable state: a single-threaded JavaScript environment with a stable identity that multiple Workers can route to. This makes DOs the natural coalescing lock primitive.

Key properties that enable coalescing:
- A DO stub routes all calls to one specific instance identified by a string `id`.
- DO methods execute serially (one at a time) inside the DO — no concurrent mutation bugs.
- A `Map<string, Promise>` stored on the DO class instance survives the lifetime of a DO activation (seconds to minutes).
- DO Alarms can act as a watchdog to clean up stuck promises.

## Solution

### Worker entry point (`src/worker.ts`)

```typescript
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only coalesce reads; pass-through mutations directly.
    if (request.method !== 'GET') {
      return fetch(request);
    }

    // Derive a stable coalesce key from the normalised path + query.
    const coalesceKey = `${url.pathname}${url.search}`;

    // Route to the coalescing DO — one instance per cache shard.
    const shardKey = coalesceKey.slice(0, 64); // keep key reasonable
    const id = env.COALESCER.idFromName(shardKey);
    const stub = env.COALESCER.get(id);

    // Forward the coalesce request to the DO.
    const doRequest = new Request(
      `https://do-internal/coalesce?key=<redacted-secret>&upstream=${encodeURIComponent(url.toString())}`,
      { method: 'POST' }
    );

    return stub.fetch(doRequest);
  },
};
```

### Durable Object (`src/coalescer.ts`)

```typescript
import { DurableObject } from 'cloudflare:workers';
import { Env } from './types';

interface PendingEntry {
  promise: Promise<CoalescedResult>;
  resolve: (r: CoalescedResult) => void;
  reject: (e: unknown) => void;
  callers: number;
  createdAt: number;
}

interface CoalescedResult {
  body: string;
  status: number;
  headers: Record<string, string>;
}

const COALESCE_TTL_MS = 30_000; // 30 s max wait
const ALARM_DELAY_MS = 35_000;  // alarm fires slightly after TTL

export class Coalescer extends DurableObject {
  private pending = new Map<string, PendingEntry>();

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const key = url.searchParams.get('key') ?? '';
    const upstream = url.searchParams.get('upstream') ?? '';

    if (!key || !upstream) {
      return new Response('Bad request', { status: 400 });
    }

    // --- First caller: nobody is pending yet ---
    if (!this.pending.has(key)) {
      let resolveFn!: (r: CoalescedResult) => void;
      let rejectFn!: (e: unknown) => void;

      const promise = new Promise<CoalescedResult>((res, rej) => {
        resolveFn = res;
        rejectFn = rej;
      });

      const entry: PendingEntry = {
        promise,
        resolve: resolveFn,
        reject: rejectFn,
        callers: 1,
        createdAt: Date.now(),
      };

      this.pending.set(key, entry);

      // Ensure a watchdog alarm is set.
      const currentAlarm = await this.ctx.storage.getAlarm();
      if (currentAlarm === null) {
        await this.ctx.storage.setAlarm(Date.now() + ALARM_DELAY_MS);
      }

      // Perform the upstream fetch without blocking other callers from joining.
      this.fetchUpstream(key, upstream, entry);
    } else {
      // --- Subsequent callers: increment counter and reuse existing promise ---
      this.pending.get(key)!.callers++;
    }

    // All callers await the same promise.
    const entry = this.pending.get(key)!;
    let result: CoalescedResult;

    try {
      result = await Promise.race([
        entry.promise,
        this.timeout(COALESCE_TTL_MS, key),
      ]);
    } catch (err) {
      this.pending.delete(key);
      return new Response(
        JSON.stringify({ error: String(err) }),
        { status: 502, headers: { 'content-type': 'application/json' } }
      );
    }

    return new Response(result.body, {
      status: result.status,
      headers: {
        ...result.headers,
        'x-coalesced-callers': String(entry.callers),
      },
    });
  }

  // Alarm fires if a DO was left with pending entries (e.g. after a crash).
  async alarm(): Promise<void> {
    const now = Date.now();
    for (const [key, entry] of this.pending) {
      if (now - entry.createdAt > COALESCE_TTL_MS) {
        entry.reject(new Error('Coalesce alarm timeout'));
        this.pending.delete(key);
      }
    }
    // Reschedule if there are still active entries.
    if (this.pending.size > 0) {
      await this.ctx.storage.setAlarm(Date.now() + ALARM_DELAY_MS);
    }
  }

  private async fetchUpstream(
    key: string,
    upstream: string,
    entry: PendingEntry
  ): Promise<void> {
    try {
      const response = await fetch(upstream, {
        cf: { cacheTtl: 0 }, // bypass CDN cache — we manage our own
      });

      const body = await response.text();
      const headers: Record<string, string> = {};

      // Forward safe headers only.
      for (const h of ['content-type', 'cache-control', 'etag']) {
        const v = response.headers.get(h);
        if (v) headers[h] = v;
      }

      entry.resolve({ body, status: response.status, headers });
    } catch (err) {
      entry.reject(err);
    } finally {
      // Clean up once all awaiting callers have received the result.
      // A microtask delay ensures in-flight awaits settle first.
      Promise.resolve().then(() => this.pending.delete(key));
    }
  }

  private timeout(ms: number, key: string): Promise<never> {
    return new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`Coalesce timeout for ${key}`)), ms)
    );
  }
}
```

### Types & bindings (`src/types.ts`)

```typescript
export interface Env {
  COALESCER: DurableObjectNamespace;
}
```

### `wrangler.toml`

```toml
name = "coalescer-worker"
main = "src/worker.ts"
compatibility_date = "2024-09-23"

[[durable_objects.bindings]]
name = "COALESCER"
class_name = "Coalescer"

[[migrations]]
tag = "v1"
new_classes = ["Coalescer"]
```

## Implementation Details

**Serial execution guarantee.** Because a Durable Object processes one request at a time, the `if (!this.pending.has(key))` branch is safe without any mutex — no two requests inside the DO run concurrently.

**Promise registry lifetime.** The `pending` Map lives in the DO's JS heap. It persists as long as the DO is active (Cloudflare keeps a DO alive while WebSocket connections or inflight fetches hold it open). After the last caller's `await` resolves, the entry is deleted and, if the Map is empty, the DO can be evicted.

**Cache population.** After coalescing resolves, the caller Worker can write the result to `caches.default` or KV so subsequent requests after the DO entry is cleaned up are served from cache rather than re-coalescing.

```typescript
// In the Worker, after receiving the DO response:
const cached = new Response(doResponse.body, doResponse);
const cacheKey = new Request(url.toString());
await caches.default.put(cacheKey, cached.clone());
```

**Shard strategy.** Using `idFromName(coalesceKey)` means all requests for the exact same URL hash to the same DO instance. If the key space is very large (millions of distinct URLs), consider using a tiered key: `idFromName(pathname)` so the DO coalesces all query-variant URLs for a given path.

## Anti-patterns

- **Storing the result body in DO storage.** DO storage is for durable state. In-memory `Map` is correct here; the DO is acting as a coordination point, not a cache.
- **Forgetting `Promise.resolve().then(...)` cleanup.** Deleting the pending entry synchronously inside `fetchUpstream` can race with callers who are about to `await` the same promise. The microtask delay ensures they see a settled promise, not `undefined`.
- **Using one DO instance for all keys.** A single DO serialises all requests globally. Shard by pathname or a hash bucket to allow per-resource coalescing in parallel.
- **No timeout / alarm.** If the upstream hangs, all callers hang indefinitely. Always set both a `Promise.race` timeout and a DO Alarm fallback.

## Gotchas

- DO activation latency (~1–5 ms within the same datacenter) adds a small fixed overhead on every request. This is worthwhile only when upstream latency is >> 5 ms.
- `idFromName` is deterministic and global — two Workers in different regions talking to `COALESCER.idFromName('/api/prices')` route to the same physical DO instance. The DO runs in the region where it was first activated, so cross-region coalescing may add geographic RTT.
- The Workers runtime limits a DO to 128 MB of memory. A large `pending` Map (many distinct keys) can approach this. Monitor with the DO Metrics dashboard and tune shard granularity.
- DO Alarms require at least one write to `ctx.storage` to persist; `setAlarm` counts as that write.

## Verification

```bash
# Run 50 concurrent requests and observe x-coalesced-callers header.
pnpx autocannon -c 50 -d 2 -p 50 https://your-worker.example.com/api/prices \
  | grep -E 'coalesced|latency'

# Check coalesced-callers in a single curl:
curl -si https://your-worker.example.com/api/prices | grep x-coalesced
# Expected: x-coalesced-callers: 47  (or similar burst count)

# Wrangler tail to watch DO logs:
wrangler tail --format json | jq '.logs[] | select(.message | test("Coalesce"))'
```

Expect upstream call count to drop by roughly `(concurrency - 1) / concurrency` under sustained burst.

## Related

- `workers-cache-api-fine-grained-control.md` — populate cache after coalescing to avoid cold-start re-coalescing.
- `workers-connection-keep-alive-upstream.md` — reuse TCP connections on the one upstream call that does fly.
- Cloudflare Durable Objects documentation — storage, alarms, WebSocket hibernation.

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/reference/alarms/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
