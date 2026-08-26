# Durable Objects Namespace Sharding — idFromName Distribution Strategy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A real-time leaderboard stores scores for one million players in a single Durable Object (`idFromName("global-leaderboard")`). All score writes and reads converge on one DO, exhausting its single-threaded CPU budget. Response times climb above 500 ms under moderate load. The solution is to shard the namespace: distribute the work across N DOs and aggregate on reads.

## Context

`DurableObjectNamespace.idFromName(name)` deterministically maps a string to a DO instance. Two Workers calling `idFromName("foo")` always reach the same object — that predictability is the feature, but it also means a single hot name becomes a hot partition.

Sharding strategies for Durable Objects:

1. **Key-based sharding** — `idFromName(\`shard:${key % N}\`)` routes by entity ID modulo shard count.
2. **Prefix-based sharding** — `idFromName(\`${prefix}:${entityId}\`)` isolates by domain or tenant.
3. **Consistent hashing** — compute a bucket from a hash of the key, independent of a fixed N.
4. **Time-based sharding** — `idFromName(\`leaderboard:${weekNumber}\`)` creates a fresh DO each time window.

---

## Key-Based Sharding

```typescript
const SHARD_COUNT = 16; // power of 2; change requires resharding

function shardId(env: Env, entityId: string): DurableObjectId {
  // FNV-1a-inspired 32-bit hash for deterministic bucket assignment
  let h = 0x811c9dc5;
  for (let i = 0; i < entityId.length; i++) {
    h ^= entityId.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  const shard = h % SHARD_COUNT;
  return env.LEADERBOARD.idFromName(`leaderboard:shard:${shard}`);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { playerId, score } = await request.json<{ playerId: string; score: number }>();
    const id = shardId(env, playerId);
    const stub = env.LEADERBOARD.get(id);
    return stub.fetch(new Request('https://do/score', {
      method: 'POST',
      body: JSON.stringify({ playerId, score }),
      headers: { 'Content-Type': 'application/json' },
    }));
  },
};
```

---

## Durable Object Shard Implementation

```typescript
interface ScoreEntry { playerId: string; score: number }

export class LeaderboardShard implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/score') {
      const { playerId, score } = await request.json<ScoreEntry>();
      const existing = (await this.state.storage.get<number>(playerId)) ?? 0;
      if (score > existing) {
        await this.state.storage.put(playerId, score);
      }
      return new Response('ok');
    }

    if (url.pathname === '/top') {
      // Return top-K within this shard
      const k = parseInt(url.searchParams.get('k') ?? '10');
      const all = await this.state.storage.list<number>();
      const sorted = [...all.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, k)
        .map(([playerId, score]) => ({ playerId, score }));
      return Response.json(sorted);
    }

    return new Response('not found', { status: 404 });
  }
}
```

---

## Fan-Out Read (Scatter–Gather)

```typescript
async function getGlobalTop(env: Env, k: number): Promise<ScoreEntry[]> {
  // Query all shards in parallel
  const results = await Promise.all(
    Array.from({ length: SHARD_COUNT }, (_, i) => {
      const id = env.LEADERBOARD.idFromName(`leaderboard:shard:${i}`);
      const stub = env.LEADERBOARD.get(id);
      return stub.fetch(new Request(`https://do/top?k=${k}`))
        .then(r => r.json<ScoreEntry[]>());
    })
  );

  // Merge and re-sort across shard results
  return results
    .flat()
    .sort((a, b) => b.score - a.score)
    .slice(0, k);
}
```

---

## Consistent Hashing Alternative

When SHARD_COUNT must change without full data migration, use consistent hashing to minimise remapping:

```typescript
// Virtual nodes: each physical shard holds V virtual nodes
const V = 10;
const ring: Array<{ hash: number; shard: number }> = [];

for (let s = 0; s < SHARD_COUNT; s++) {
  for (let v = 0; v < V; v++) {
    const label = `shard:${s}:vnode:${v}`;
    let h = 0x811c9dc5;
    for (const c of label) { h ^= c.charCodeAt(0); h = Math.imul(h, 0x01000193) >>> 0; }
    ring.push({ hash: h, shard: s });
  }
}
ring.sort((a, b) => a.hash - b.hash);

function consistentShardId(env: Env, key: string): DurableObjectId {
  let h = 0x811c9dc5;
  for (const c of key) { h ^= c.charCodeAt(0); h = Math.imul(h, 0x01000193) >>> 0; }
  // Walk ring clockwise to find the first node ≥ h
  const node = ring.find(n => n.hash >= h) ?? ring[0];
  return env.LEADERBOARD.idFromName(`leaderboard:shard:${node.shard}`);
}
```

---

## Time-Based Sharding (Rolling Windows)

```typescript
function currentWindowId(env: Env): DurableObjectId {
  const week = Math.floor(Date.now() / (7 * 24 * 60 * 60 * 1000));
  return env.LEADERBOARD.idFromName(`leaderboard:week:${week}`);
}
// Each week, a fresh DO starts clean — no migration needed
// Previous weeks' DOs become read-only archives
```

---

## Shard Count Guidance

| Write TPS | Recommended Shards |
|---|---|
| < 100 | 1 (no sharding) |
| 100–1 000 | 4–8 |
| 1 000–10 000 | 16–64 |
| > 10 000 | 64+ with hierarchical aggregation |

The DO CPU limit is 30 s wall-clock per request; the single-threaded model means a shard handling 1 000 concurrent writes serially will queue. Measure `storage.put` latency under load before choosing N.

---

## Anti-patterns

- **Choosing non-power-of-2 shard counts** — modulo bias. For random keys, use a power of 2 to ensure even distribution.
- **Hard-coding shard count in both writer and reader** — a mismatch sends writes to `shard:15` but reads only query `shard:0..7`. Store `SHARD_COUNT` in a KV config key.
- **Using `idFromString` (UUID) for shards** — generates cryptographically random IDs; you lose the ability to enumerate shards on read. Always use `idFromName` with a predictable naming scheme for shardable namespaces.
- **Not padding shard indices** — `shard:1` and `shard:10` sort correctly in logs but `idFromName` is hash-based, so this is aesthetic only. Use zero-padding for readability.

---

## Gotchas

- Durable Objects are billed per unique object activated. Increasing SHARD_COUNT from 8 to 16 mid-deployment creates 8 new (empty) shards. Old data stays in the original 8. You must migrate or dual-read during the transition.
- DO storage is limited to 128 KB per key and 128 GB total per DO. A shard holding too many large values hits the per-DO limit, not just CPU. Shard on both key volume and value size.
- `Promise.all` across 64 shards on every read consumes 64 subrequests from the Worker's 1 000-subrequest budget per request. For very high shard counts, use a hierarchical aggregator DO instead.

---

## Verification

```bash
# Send 10 000 score updates and check distribution
for i in $(seq 1 10000); do
  curl -s -X POST https://your-worker.workers.dev/score \
    -H 'Content-Type: application/json' \
    -d "{\"playerId\":\"player-$i\",\"score\":$((RANDOM % 1000))}" &
done
wait

# Query global top-10
curl https://your-worker.workers.dev/top?k=10 | jq .

# Confirm shard balance via Cloudflare analytics (requests per DO)
wrangler tail --format pretty | grep '"shard"' | sort | uniq -c
```

---

## Related

- `hot-partition-mitigation.md` — broader hot partition strategies
- `consistent-hashing.md` — ring-based hash routing theory
- `fan-in-aggregator-durable-objects-coordination.md` — aggregating results from multiple DOs
- `scatter-gather-workers-service-bindings.md` — scatter-gather via service bindings
- `competing-consumers-durable-objects.md` — DO-per-queue-consumer pattern

---

## Sources

- Cloudflare DO naming: https://developers.cloudflare.com/durable-objects/api/namespace/#idFromName
- Karger et al., "Consistent Hashing and Random Trees" (1997 STOC)
- Cloudflare DO limits: https://developers.cloudflare.com/durable-objects/platform/limits/
