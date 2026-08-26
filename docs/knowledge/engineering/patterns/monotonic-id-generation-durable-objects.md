# Monotonic ID Generation Pattern — Durable Objects + Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A distributed system needs IDs that are globally unique, sortable by creation time, and monotonically increasing within each logical partition (e.g. tenant, shard). Standard UUIDs are random and un-sortable. `Date.now()` collides under concurrent requests in the same millisecond. Snowflake-style IDs require a reliable node/shard ID registry. Workers are stateless and horizontally distributed — there is no shared memory between instances. A single Durable Object per partition provides the serialization point needed to guarantee monotonicity without a central database sequence.

## Context

- A Durable Object is single-threaded: sequential `fetch()` calls to the same instance never race, so incrementing a counter there is race-free.
- IDs are structured as: `{timestamp_ms}-{sequence}` or encoded as 64-bit integers in a Snowflake layout for compactness and SQL index efficiency.
- The DO stores only the last-issued sequence number and the last-used millisecond timestamp, so storage is minimal.
- For very high throughput (> 1000 IDs/second per partition), a batch-allocation strategy pre-allocates a block of IDs per round trip.
- This pattern is distinct from UUID v7 (which is random within the same millisecond) — here, IDs from the same DO instance are strictly ordered even within a millisecond.

---

## Durable Object — Sequential ID Generator

```typescript
// src/do/id-generator.ts
const SEQUENCE_MAX = 4095; // 12-bit sequence field (0–4095)

export class MonotonicIdGenerator implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState, _env: Env) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const batchSize = Math.min(
      Number(url.searchParams.get('batch') ?? '1'),
      100 // cap batch at 100 per request
    );

    const ids = await this.state.storage.transaction(async (txn) => {
      let lastMs: number   = (await txn.get<number>('lastMs'))  ?? 0;
      let sequence: number = (await txn.get<number>('seq'))     ?? 0;

      const generated: string[] = [];

      for (let i = 0; i < batchSize; i++) {
        let now = Date.now();

        if (now < lastMs) {
          // Clock moved backwards — wait it out to preserve monotonicity
          now = lastMs;
        }

        if (now === lastMs) {
          sequence += 1;
          if (sequence > SEQUENCE_MAX) {
            // Sequence exhausted in this millisecond — advance to next ms
            lastMs += 1;
            now = lastMs;
            sequence = 0;
          }
        } else {
          lastMs = now;
          sequence = 0;
        }

        generated.push(encodeSnowflake(now, sequence));
      }

      await txn.put('lastMs', lastMs);
      await txn.put('seq', sequence);

      return generated;
    });

    return Response.json({ ids });
  }
}

/**
 * Encode a 63-bit Snowflake-style ID as a decimal string.
 *
 * Bit layout (MSB → LSB):
 *   [41 bits: timestamp ms since epoch] [12 bits: sequence]
 *
 * 41 bits of ms gives ~69 years from epoch before overflow.
 * We use a custom epoch (2024-01-01) to extend useful range.
 */
const CUSTOM_EPOCH = 1_704_067_200_000; // 2024-01-01T00:00:00.000Z in ms

export function encodeSnowflake(epochMs: number, sequence: number): string {
  const ts = BigInt(epochMs - CUSTOM_EPOCH);
  const seq = BigInt(sequence & SEQUENCE_MAX);
  const id = (ts << 12n) | seq;
  return id.toString();
}

export function decodeSnowflake(id: string): { epochMs: number; sequence: number } {
  const n = BigInt(id);
  const seq = Number(n & 0xfffn);
  const ts = Number(n >> 12n);
  return { epochMs: ts + CUSTOM_EPOCH, sequence: seq };
}
```

---

## Worker Entrypoint — ID Allocation Service

```typescript
// src/index.ts
export { MonotonicIdGenerator } from './do/id-generator';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const url = new URL(request.url);

    // Partition by tenant (or any logical shard key)
    const partition = url.searchParams.get('partition') ?? 'global';
    const batch = url.searchParams.get('batch') ?? '1';

    const id = env.ID_GENERATOR.idFromName(partition);
    const stub = env.ID_GENERATOR.get(id);

    return stub.fetch(
      new Request(`https://id-gen/?batch=${batch}`, { method: 'GET' })
    );
  },
};
```

---

## Wrangler Configuration

```toml
# wrangler.toml
name = "id-service"
main = "src/index.ts"

[[durable_objects.bindings]]
name = "ID_GENERATOR"
class_name = "MonotonicIdGenerator"

[[migrations]]
tag = "v1"
new_classes = ["MonotonicIdGenerator"]
```

---

## Client-Side Usage in a Worker

```typescript
// src/lib/id-client.ts
export async function allocateId(
  env: Env,
  partition: string = 'global'
): Promise<string> {
  const doId = env.ID_GENERATOR.idFromName(partition);
  const stub = env.ID_GENERATOR.get(doId);
  const res = await stub.fetch(
    new Request(`https://id-gen/?batch=1`, { method: 'GET' })
  );
  const { ids } = await res.json<{ ids: string[] }>();
  return ids[0];
}

export async function allocateBatch(
  env: Env,
  count: number,
  partition: string = 'global'
): Promise<string[]> {
  const doId = env.ID_GENERATOR.idFromName(partition);
  const stub = env.ID_GENERATOR.get(doId);
  const res = await stub.fetch(
    new Request(`https://id-gen/?batch=${count}`, { method: 'GET' })
  );
  const { ids } = await res.json<{ ids: string[] }>();
  return ids;
}
```

---

## Sorting and Decoding IDs

```typescript
// src/lib/id-utils.ts
import { decodeSnowflake } from '../do/id-generator';

/** Sort IDs chronologically (ascending). Works because Snowflake IDs are numeric strings. */
export function sortIds(ids: string[]): string[] {
  return [...ids].sort((a, b) => {
    const diff = BigInt(a) - BigInt(b);
    return diff < 0n ? -1 : diff > 0n ? 1 : 0;
  });
}

/** Extract the creation timestamp from an ID. */
export function idToDate(id: string): Date {
  const { epochMs } = decodeSnowflake(id);
  return new Date(epochMs);
}

/** Construct a lower-bound ID for a given timestamp (for range queries). */
export function idFromTimestamp(epochMs: number): string {
  const { encodeSnowflake } = require('../do/id-generator');
  return encodeSnowflake(epochMs, 0);
}
```

---

## Anti-patterns

- **Using `crypto.randomUUID()` as a sortable ID**: UUID v4 is random — lexicographic sort gives no ordering guarantee. Use UUID v7 (time-ordered) if you do not need strict monotonicity per partition.
- **Using `Date.now()` directly without sequence**: two concurrent Workers can call `Date.now()` in the same millisecond and produce identical IDs. The DO sequence field prevents this.
- **One global DO for all tenants**: a single DO instance is a global serialization bottleneck. Partition by tenant, shard, or resource type.
- **Storing the full ID in the DO storage**: the DO only needs `lastMs` and `seq`. Storing generated IDs wastes storage and slows the transaction.
- **Generating IDs client-side with a combined timestamp + random suffix**: random suffixes are not monotonic within a millisecond and can collide under high concurrency.

## Gotchas

- `state.storage.transaction()` in a DO is serialized within the instance but does not protect against DO migration (rare) — the sequence resets to 0 on new DO startup, so IDs remain unique but the sequence counter restarts. Add the DO instance creation timestamp to the ID if you need cross-migration monotonicity.
- Snowflake IDs as decimal strings fit in a JavaScript `Number` up to ~53 bits. With a 41-bit timestamp and 12-bit sequence the total is 53 bits — exactly at the safe integer boundary. Store IDs as `TEXT` in D1, never as `REAL` or `INTEGER` (SQLite INTEGER is 64-bit signed, so it is safe for the numeric value, but JSON serialization via `JSON.stringify` will lose precision if you convert to `number`). Always keep them as `BigInt` or strings in TS.
- D1 does not have native `BIGINT` columns; store Snowflake IDs as `TEXT`. Sorting `TEXT` columns works correctly because IDs are zero-padded to a fixed length.
- DO instances can be evicted after ~10 s of inactivity; the next call reloads `lastMs` and `seq` from storage. There is no monotonicity gap on eviction — the loaded `lastMs` is the last persisted value, and `Date.now()` at resume will be ≥ `lastMs`.

## Verification

```bash
# Allocate 5 IDs and confirm they are strictly increasing
curl -s -X POST "https://id-service.example.com/?partition=test&batch=5" \
  | jq '.ids | map(tonumber) | to_entries | map(.value > (.[.key-1].value // 0))'
# Expected: [true, true, true, true, true] (all in ascending order)

# Decode an ID to verify the timestamp is recent
curl -s -X POST "https://id-service.example.com/?partition=test&batch=1" \
  | jq -r '.ids[0]'
# Then decode: node -e "const id=BigInt('ID'); console.log(new Date(Number(id>>12n)+1704067200000))"
```

## Related

- `distributed-lock-durable-objects.md`
- `watermark-durable-objects-event-ordering.md`
- `event-sourcing-cloudflare-workers-d1.md`
- `snapshot-durable-objects-versioning.md`
- `per-tenant-durable-object.md`

## Sources

- Twitter Snowflake ID spec: https://github.com/twitter-archive/snowflake/tree/snowflake-2010
- Cloudflare Durable Objects docs — Transactions: https://developers.cloudflare.com/durable-objects/api/storage-api/#transaction
- IETF RFC 9562 — UUID Version 7 (time-ordered): https://www.rfc-editor.org/rfc/rfc9562#section-5.7
