# Anti-Entropy Periodic Consistency Check with Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Over time, derived stores diverge from their source of truth. Workers KV caches grow
stale. D1 read replicas (or secondary tables materialised from events) drift. Queued
messages are dropped. The mismatch is rarely visible until a user reports "wrong data"
or a downstream system breaks.

Anti-entropy is a distributed-systems technique for detecting and correcting these
divergences proactively, without relying on individual requests to trigger repair
(that is read repair's job). A periodic background process compares every record in
a derived store against its canonical source, and repairs any discrepancy it finds.

On Cloudflare Workers the natural vehicle is a **Cron Trigger Worker** that paginates
through the derived store, hashes or versions each record, compares it to the
canonical version, and applies corrections via `ctx.waitUntil` chains.

---

## Context

Anti-entropy is the complement of read repair:

| Mechanism      | Trigger               | Coverage           | Latency impact |
|----------------|-----------------------|--------------------|----------------|
| Read repair    | User read of a key    | Keys that are read | Hot-path       |
| Anti-entropy   | Periodic Cron run     | All keys           | Background     |

Together they form a layered consistency strategy: read repair fixes recently accessed
keys fast; anti-entropy finds the long tail of keys that are never read but still wrong.

Use cases:

- KV cache holding user profile snapshots from D1 — profiles updated via a rare admin
  flow that does not always invalidate KV.
- A D1 `metrics_summary` table maintained by a Queues consumer — messages occasionally
  DLQ'd without being retried, leaving summary counts behind.
- A KV feature-flag store synchronised from an external vendor API that sometimes fails
  mid-sync.

---

## Architecture

```
Cron Trigger (hourly / daily)
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  Anti-Entropy Worker                                 │
│                                                      │
│  1. Fetch page of keys from derived store (KV list   │
│     or D1 SELECT with cursor)                        │
│  2. For each key, load canonical value from D1       │
│  3. Hash/version compare                             │
│  4. If diverged → write correct value + log          │
│  5. Store cursor in KV → Cron fires next chunk       │
└─────────────────────────────────────────────────────┘
```

Because a Cron Worker has a 30-second CPU time limit (Workers Paid plan) and cannot
iterate over all keys in a large store in one run, the worker is designed to run
incrementally: it processes one page per Cron firing and stores the cursor for the
next run.

---

## Implementation

### 1. `wrangler.toml`

```toml
name = "anti-entropy"

[[kv_namespaces]]
binding = "PROFILE_KV"
id      = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[kv_namespaces]]
binding = "CURSOR_KV"
id      = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"

[[d1_databases]]
binding  = "DB"
database_id = "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
database_name = "main"

[triggers]
crons = ["0 * * * *"]   # hourly
```

### 2. KV page scanner

```typescript
// scanner.ts
export interface ScanPage {
  keys: string[];
  cursor: string | null;  // null = reached the end; restart from beginning
  done: boolean;
}

const PAGE_SIZE = 100;

export async function nextPage(
  kv: KVNamespace,
  prefix: string,
  currentCursor: string | undefined,
): Promise<ScanPage> {
  const result = await kv.list({ prefix, limit: PAGE_SIZE, cursor: currentCursor });
  return {
    keys: result.keys.map(k => k.name),
    cursor: result.list_complete ? null : result.cursor,
    done: result.list_complete,
  };
}
```

### 3. Version fingerprint helper

```typescript
// fingerprint.ts
// Cheap structural fingerprint — compare without full deserialization when possible
export function fingerprint(obj: unknown): string {
  // FNV-1a over JSON bytes — good enough for divergence detection
  const str = JSON.stringify(obj);
  let hash = 2166136261;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = (hash * 16777619) >>> 0;
  }
  return hash.toString(16);
}
```

### 4. Canonical loader from D1

```typescript
// canon.ts
export interface UserProfile {
  userId: string;
  email: string;
  displayName: string;
  version: number;
  updatedAt: string;
}

// Batch-load up to 100 profiles from D1 by userId array
export async function batchLoadProfiles(
  db: D1Database,
  userIds: string[],
): Promise<Map<string, UserProfile>> {
  if (userIds.length === 0) return new Map();

  const placeholders = userIds.map(() => "?").join(", ");
  const rows = await db
    .prepare(`SELECT * FROM user_profiles WHERE user_id IN (${placeholders})`)
    .bind(...userIds)
    .all<UserProfile>();

  const map = new Map<string, UserProfile>();
  for (const row of rows.results) {
    map.set(row.userId, row);
  }
  return map;
}
```

### 5. Anti-entropy Worker

```typescript
// index.ts
import { nextPage } from "./scanner";
import { batchLoadProfiles, type UserProfile } from "./canon";
import { fingerprint } from "./fingerprint";

interface Env {
  PROFILE_KV:  KVNamespace;
  CURSOR_KV:   KVNamespace;
  DB:          D1Database;
}

const KV_PREFIX = "profile:";
const CURSOR_KEY = "anti-entropy:profile:cursor";

interface RepairStats {
  scanned: number;
  repaired: number;
  missing: number;  // in KV but not in D1 — deleted records
  errors: number;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runAntiEntropy(env));
  },
};

async function runAntiEntropy(env: Env): Promise<void> {
  const stats: RepairStats = { scanned: 0, repaired: 0, missing: 0, errors: 0 };
  const startMs = Date.now();

  // Load the cursor from the previous run (if any)
  const storedCursor = await env.CURSOR_KV.get(CURSOR_KEY);

  const page = await nextPage(
    env.PROFILE_KV,
    KV_PREFIX,
    storedCursor ?? undefined,
  );

  if (page.keys.length === 0) {
    // Nothing to scan — reset cursor so next run starts from the top
    await env.CURSOR_KV.delete(CURSOR_KEY);
    logStats(stats, startMs, "nothing_to_scan");
    return;
  }

  // Extract user IDs from keys like "profile:user-123"
  const userIds = page.keys.map(k => k.replace(KV_PREFIX, ""));

  // Batch-load canonical records from D1
  const canonicalMap = await batchLoadProfiles(env.DB, userIds);

  // Load KV values in parallel (one batch of getWithMetadata calls)
  const kvLoads = await Promise.allSettled(
    page.keys.map(k => env.PROFILE_KV.get<UserProfile>(k, "json")),
  );

  const repairs: Promise<void>[] = [];

  for (let i = 0; i < page.keys.length; i++) {
    const key = page.keys[i];
    const userId = userIds[i];
    stats.scanned++;

    const kvResult = kvLoads[i];
    if (kvResult.status === "rejected") {
      stats.errors++;
      continue;
    }

    const kvValue = kvResult.value;
    const canonical = canonicalMap.get(userId);

    if (!canonical) {
      // User deleted from D1 — remove stale KV entry
      stats.missing++;
      repairs.push(env.PROFILE_KV.delete(key));
      continue;
    }

    if (!kvValue) {
      // KV entry missing — backfill
      stats.repaired++;
      repairs.push(env.PROFILE_KV.put(key, JSON.stringify(canonical), { expirationTtl: 86400 }));
      continue;
    }

    // Compare fingerprints — if equal, no repair needed
    if (fingerprint(kvValue) !== fingerprint(canonical)) {
      stats.repaired++;
      repairs.push(env.PROFILE_KV.put(key, JSON.stringify(canonical), { expirationTtl: 86400 }));
    }
  }

  // Apply all repairs concurrently
  const repairResults = await Promise.allSettled(repairs);
  stats.errors += repairResults.filter(r => r.status === "rejected").length;

  // Save cursor for the next Cron run
  if (page.done) {
    // Reached the end of the KV namespace — reset to start over
    await env.CURSOR_KV.delete(CURSOR_KEY);
  } else {
    await env.CURSOR_KV.put(CURSOR_KEY, page.cursor!, { expirationTtl: 7200 }); // 2-hour TTL as safety net
  }

  logStats(stats, startMs, page.done ? "cycle_complete" : "partial");
}

function logStats(stats: RepairStats, startMs: number, phase: string): void {
  console.log(
    JSON.stringify({
      event:     "anti_entropy_run",
      phase,
      durationMs: Date.now() - startMs,
      ...stats,
    }),
  );
}
```

---

## Repair Rate Limiting

For large namespaces the repair loop may generate bursts of KV writes that briefly
exceed rate limits. Spread repairs across time using a micro-delay:

```typescript
async function repairWithThrottle(
  repairs: Array<() => Promise<void>>,
  concurrency = 10,
): Promise<void> {
  for (let i = 0; i < repairs.length; i += concurrency) {
    const batch = repairs.slice(i, i + concurrency);
    await Promise.all(batch.map(fn => fn()));
  }
}
```

---

## Anti-patterns

- **Scanning the entire namespace in a single Cron run** — a large KV namespace can
  have millions of keys. Cursor-based incremental scanning spreads the work over many
  Cron firings without hitting CPU limits.
- **Repairing with blind overwrites** — always compare fingerprints or versions before
  writing. Unconditional overwrites waste write quota and reset KV TTLs unnecessarily.
- **Comparing raw JSON strings for equality** — field order in JSON is unstable across
  serialisers. Always compare a canonical hash or use a struct field comparison.
- **Running anti-entropy on every write event** — this is read repair disguised as
  anti-entropy. True anti-entropy is periodic and covers all keys, not just recently
  touched ones.
- **Not resetting the cursor on cycle completion** — without a reset, the next run
  starts from a cursor that points past the end and scans nothing, silently skipping
  the whole namespace.

---

## Gotchas

- `kv.list()` returns keys ordered lexicographically. If you delete a key between runs
  and the cursor lands exactly on it, the list may skip the next key. Use prefix-based
  scoping to reduce cursor instability.
- Cron Workers have a 30-second CPU limit on Paid plan and 10 seconds on Free. Keep
  the batch size (`PAGE_SIZE`) small enough to finish within 25 seconds, leaving a
  safety margin for D1 latency spikes.
- The cursor stored in `CURSOR_KV` uses a 2-hour TTL as a dead-man's switch. If a
  Cron run crashes after writing the cursor but before the next one fires, the cursor
  does not persist forever — the next cycle restarts from the beginning after 2 hours.
- Batch D1 queries with `IN (...)` have a practical limit of ~100 values per query
  before performance degrades. Match `PAGE_SIZE` to this limit.

---

## Verification

```bash
# Monitor repair events in real time
wrangler tail --env production --format json | \
  jq 'select(.logs[].message | test("anti_entropy_run"))'

# Manually corrupt a KV record and verify repair within one Cron cycle
wrangler kv put --namespace-id=<ID> "profile:user-test" '{"displayName":"CORRUPTED"}'
# Wait for the next Cron fire (or trigger manually in wrangler dev)
curl "http://localhost:8787/__scheduled?cron=0+*+*+*+*"
# Verify the KV record is restored to the D1 value
wrangler kv get --namespace-id=<ID> "profile:user-test" | jq .displayName
```

---

## Related

- `read-repair-workers-kv.md` — per-request repair for hot keys
- `write-behind-cache-kv-d1.md` — async write propagation that anti-entropy can correct
- `materialized-view-d1-workers.md` — derived tables that benefit from entropy checks
- `deduplication-window-kv-fingerprint.md` — fingerprinting technique for idempotency

---

## Sources

- DeCandia, G. et al. "Dynamo: Amazon's Highly Available Key-value Store" (SOSP 2007) — anti-entropy via Merkle trees
- Kleppmann, M. "Designing Data-Intensive Applications" (O'Reilly) — Chapter 5, Replication
- Cloudflare KV list API — developers.cloudflare.com/kv/api/list-keys/
- Cloudflare Cron Triggers — developers.cloudflare.com/workers/configuration/cron-triggers/
