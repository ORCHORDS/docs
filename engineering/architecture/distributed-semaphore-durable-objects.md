# Distributed Semaphore with Durable Objects

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Multiple concurrent Workers need to access a shared resource with bounded parallelism — for example, at most 10 simultaneous calls to an expensive third-party API or 5 concurrent database migrations. A distributed semaphore enforces the concurrency ceiling without a central database and without polling.

## Context
Durable Objects serialize all incoming requests to a single instance, making them ideal semaphore managers. The single-writer guarantee eliminates compare-and-swap races. The object maintains a permit counter in its transactional storage, grants permits to callers via HTTP, and releases them when callers signal completion or when a lease TTL expires via an alarm. Unlike Redis-based semaphores this runs entirely within the Cloudflare edge with no external dependency.

## Semaphore Durable Object

The object owns the permit counter and a per-holder lease registry.

```typescript
// src/durable-objects/semaphore.ts
export interface SemaphoreRequest {
  action: 'acquire' | 'release';
  holderId: string;
  leaseTtlMs?: number;
}

interface LeaseEntry {
  holderId: string;
  expiresAt: number;
}

export class Semaphore implements DurableObject {
  private readonly maxPermits: number;
  private storage: DurableObjectStorage;

  constructor(state: DurableObjectState, _env: unknown) {
    this.storage = state.storage;
    this.maxPermits = 10; // override via DO name convention or KV config
  }

  async fetch(req: Request): Promise<Response> {
    const body = await req.json<SemaphoreRequest>();

    if (body.action === 'acquire') {
      return this.acquire(body.holderId, body.leaseTtlMs ?? 30_000);
    }
    if (body.action === 'release') {
      return this.release(body.holderId);
    }
    return Response.json({ error: 'unknown action' }, { status: 400 });
  }

  private async acquire(holderId: string, leaseTtlMs: number): Promise<Response> {
    await this.evictExpiredLeases();

    const leases = await this.getLeases();
    if (leases.size >= this.maxPermits) {
      return Response.json({ granted: false, reason: 'capacity_reached' }, { status: 429 });
    }

    const expiresAt = Date.now() + leaseTtlMs;
    leases.set(holderId, { holderId, expiresAt });
    await this.saveLeases(leases);
    await this.storage.setAlarm(Math.min(expiresAt, (await this.nextAlarm()) ?? Infinity));

    return Response.json({ granted: true, expiresAt });
  }

  private async release(holderId: string): Promise<Response> {
    const leases = await this.getLeases();
    const existed = leases.delete(holderId);
    if (existed) {
      await this.saveLeases(leases);
    }
    return Response.json({ released: existed });
  }

  async alarm(): Promise<void> {
    await this.evictExpiredLeases();
    // Reschedule if any leases remain
    const leases = await this.getLeases();
    if (leases.size > 0) {
      const next = Math.min(...Array.from(leases.values()).map((l) => l.expiresAt));
      await this.storage.setAlarm(next);
    }
  }

  private async evictExpiredLeases(): Promise<void> {
    const now = Date.now();
    const leases = await this.getLeases();
    let changed = false;
    for (const [id, lease] of leases) {
      if (lease.expiresAt <= now) {
        leases.delete(id);
        changed = true;
      }
    }
    if (changed) await this.saveLeases(leases);
  }

  private async getLeases(): Promise<Map<string, LeaseEntry>> {
    const raw = await this.storage.get<Record<string, LeaseEntry>>('leases');
    return new Map(Object.entries(raw ?? {}));
  }

  private async saveLeases(leases: Map<string, LeaseEntry>): Promise<void> {
    await this.storage.put('leases', Object.fromEntries(leases));
  }

  private async nextAlarm(): Promise<number | null> {
    return this.storage.getAlarm();
  }
}
```

## Client Helper — Acquire with Retry

Workers call the semaphore DO via its stub. The helper retries acquisition with exponential backoff.

```typescript
// src/lib/semaphore-client.ts
interface Env {
  SEMAPHORE: DurableObjectNamespace;
}

function getSemaphoreStub(env: Env, resourceName: string) {
  const id = env.SEMAPHORE.idFromName(resourceName);
  return env.SEMAPHORE.get(id);
}

export async function withSemaphore<T>(
  env: Env,
  resourceName: string,
  holderId: string,
  fn: () => Promise<T>,
  options: { leaseTtlMs?: number; maxRetries?: number } = {}
): Promise<T> {
  const { leaseTtlMs = 25_000, maxRetries = 5 } = options;
  const stub = getSemaphoreStub(env, resourceName);

  let granted = false;
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const resp = await stub.fetch('https://semaphore/', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action: 'acquire', holderId, leaseTtlMs }),
    });

    const data = await resp.json<{ granted: boolean }>();
    if (data.granted) {
      granted = true;
      break;
    }

    // Exponential backoff with jitter: 200ms * 2^attempt ± 50ms
    const delay = 200 * 2 ** attempt + (Math.random() * 100 - 50);
    await new Promise((r) => setTimeout(r, delay));
  }

  if (!granted) {
    throw new Error(`Semaphore '${resourceName}' unavailable after ${maxRetries} attempts`);
  }

  try {
    return await fn();
  } finally {
    await stub.fetch('https://semaphore/', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action: 'release', holderId }),
    });
  }
}
```

## Usage in a Worker Handler

```typescript
// src/workers/export-worker.ts
import { withSemaphore } from '../lib/semaphore-client';
import { crypto } from 'cloudflare:crypto';

interface Env {
  SEMAPHORE: DurableObjectNamespace;
  DATA_API_URL: string;
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const holderId = crypto.randomUUID();

    try {
      const result = await withSemaphore(
        env,
        'third-party-export-api', // semaphore name = resource name
        holderId,
        async () => {
          const resp = await fetch(`${env.DATA_API_URL}/export`, {
            headers: { authorization: `Bearer ${env.DATA_API_KEY}` },
          });
          return resp.json();
        },
        { leaseTtlMs: 20_000, maxRetries: 4 }
      );

      return Response.json(result);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'unknown error';
      return Response.json({ error: message }, { status: 503 });
    }
  },
};
```

## Observability — Active Permit Count

Expose a read endpoint on the DO to query the current permit occupancy for dashboards.

```typescript
// Add to Semaphore.fetch() routing:
if (req.method === 'GET') {
  const leases = await this.getLeases();
  await this.evictExpiredLeases();
  return Response.json({
    active: leases.size,
    capacity: this.maxPermits,
    holders: Array.from(leases.values()),
  });
}
```

## Anti-patterns
- Using KV for the permit counter — eventual consistency allows concurrent over-issuance
- Never releasing permits on exception — `try/finally` in the client wrapper is mandatory
- Setting TTL shorter than the actual operation duration — auto-eviction releases a permit while the holder is still active, breaking the isolation guarantee
- Creating one DO instance for all resources — a single instance becomes a bottleneck; use `idFromName(resourceName)` to shard by resource

## Gotchas
- Durable Object storage `put` is synchronous within the JavaScript event loop but only durable after the transaction commits; do not rely on in-memory state across awaits in the same handler
- The alarm fires *approximately* at the scheduled time; add 5–10 % grace to `leaseTtlMs` so leases are not evicted marginally early
- If the Worker holding a permit crashes mid-operation the lease auto-expires via the alarm — size TTL generously to cover your P99 operation time
- `idFromName` is deterministic per namespace; the same resource name always maps to the same DO instance globally

## Verification
```bash
# Acquire 10 permits simultaneously (should all succeed)
for i in $(seq 1 10); do
  curl -sX POST https://api.example.workers.dev/export &
done
wait

# The 11th concurrent request should return HTTP 503
curl -sX POST https://api.example.workers.dev/export | jq .error

# Query current permit occupancy
wrangler durable-objects get SEMAPHORE --name third-party-export-api \
  | curl $(cat -) | jq .
```

## Related
- [Distributed Lock Design](distributed-lock-design.md)
- [Leader Election Patterns](leader-election-patterns.md)
- [Actor Model with Durable Objects](actor-model-durable-objects-workers.md)
- [Rate Limiting Architecture Workers](rate-limiting-architecture-workers.md)

## Sources
- Dijkstra, E.W. (1968) — Cooperating Sequential Processes, semaphore concept
- Cloudflare Durable Objects transactional storage: https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/
- Cloudflare Durable Objects alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
