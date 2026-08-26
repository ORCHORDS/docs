# D1 Bloom Filter Approximate Membership Testing in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to check membership in a large set (blocked emails, used tokens, seen event IDs) before hitting D1, but querying the full table on every request adds latency. A bloom filter stored in KV lets you skip D1 entirely for definite non-members and only query D1 for probable members.

## Context

A bloom filter is a probabilistic data structure: it can say "definitely not in set" (zero false negatives) or "probably in set" (small false positive rate). Ideal for rate-limit bypass, duplicate-event deduplication, and deny-list pre-checks. In Cloudflare Workers the filter lives in KV (serialised bit-array); D1 remains the source of truth for confirmations.

---

## Bit-Array Helpers

```typescript
// bloom.ts
const FILTER_BITS = 1 << 16; // 65 536 bits = 8 KB

function hashPositions(value: string, numHashes: number): number[] {
  const positions: number[] = [];
  for (let seed = 0; seed < numHashes; seed++) {
    let h = seed * 0x9e3779b9;
    for (let i = 0; i < value.length; i++) {
      h = Math.imul(h ^ value.charCodeAt(i), 0x517cc1b727220a95 | 0);
    }
    positions.push(((h >>> 0) % FILTER_BITS));
  }
  return positions;
}

export function bloomCheck(buf: Uint8Array, value: string, numHashes = 7): boolean {
  for (const pos of hashPositions(value, numHashes)) {
    if (!(buf[pos >> 3] & (1 << (pos & 7)))) return false;
  }
  return true; // probable member
}

export function bloomAdd(buf: Uint8Array, value: string, numHashes = 7): void {
  for (const pos of hashPositions(value, numHashes)) {
    buf[pos >> 3] |= (1 << (pos & 7));
  }
}
```

---

## Loading the Filter from KV

```typescript
// filter-loader.ts
export interface Env {
  KV: KVNamespace;
  DB: D1Database;
}

const FILTER_KEY = 'bloom:blocked-emails';
const FILTER_BITS = 1 << 16;

export async function loadFilter(kv: KVNamespace): Promise<Uint8Array> {
  const raw = await kv.get(FILTER_KEY, 'arrayBuffer');
  if (raw) return new Uint8Array(raw);
  return new Uint8Array(FILTER_BITS >> 3); // empty filter on first boot
}
```

---

## Building the Filter from D1

Run this as a Cron Trigger or on first deploy to seed the filter from the source-of-truth table.

```typescript
// build-filter.ts
import { bloomAdd } from './bloom';

export async function rebuildFilter(db: D1Database, kv: KVNamespace): Promise<void> {
  const FILTER_BITS = 1 << 16;
  const buf = new Uint8Array(FILTER_BITS >> 3);

  // Stream all blocked emails in pages to avoid large result sets
  let cursor: string | null = null;
  do {
    const rows = await db
      .prepare(
        cursor
          ? 'SELECT email FROM blocked_emails WHERE email > ? ORDER BY email LIMIT 1000'
          : 'SELECT email FROM blocked_emails ORDER BY email LIMIT 1000'
      )
      .bind(...(cursor ? [cursor] : []))
      .all<{ email: string }>();

    for (const row of rows.results) bloomAdd(buf, row.email);
    cursor = rows.results.length === 1000 ? rows.results.at(-1)!.email : null;
  } while (cursor);

  await kv.put(FILTER_KEY, buf.buffer, { expirationTtl: 3600 });
}

const FILTER_KEY = 'bloom:blocked-emails';
```

---

## Request Handler with Filter Pre-check

```typescript
// worker.ts
import { loadFilter, Env } from './filter-loader';
import { bloomCheck } from './bloom';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { email } = await request.json<{ email: string }>();

    const filter = await loadFilter(env.KV);

    // Definite non-member — skip D1 entirely
    if (!bloomCheck(filter, email)) {
      return Response.json({ blocked: false, source: 'bloom' });
    }

    // Probable member — confirm against D1
    const row = await env.DB
      .prepare('SELECT 1 FROM blocked_emails WHERE email = ? LIMIT 1')
      .bind(email)
      .first();

    return Response.json({
      blocked: !!row,
      source: row ? 'd1' : 'bloom-false-positive',
    });
  },
};
```

---

## Incremental Filter Updates on Write

Add to the filter in KV whenever a new row is inserted, avoiding a full rebuild.

```typescript
async function blockEmail(email: string, env: Env): Promise<void> {
  await env.DB.prepare('INSERT OR IGNORE INTO blocked_emails (email) VALUES (?)').bind(email).run();

  const filter = await loadFilter(env.KV);
  bloomAdd(filter, email);
  await env.KV.put('bloom:blocked-emails', filter.buffer, { expirationTtl: 3600 });
}
```

---

## Anti-patterns

- **Using a bloom filter as the sole gate** — false positives mean some legitimate emails get blocked; always confirm in D1 before taking irreversible action.
- **Too-small bit array** — a 1 KB filter for 100 000 entries saturates immediately; size to keep false-positive rate under 1 % (rule of thumb: ~10 bits per expected element).
- **Ignoring KV consistency on concurrent updates** — two Workers reading and writing the filter concurrently can lose an `add`; use Durable Objects for single-writer serialisation in high-write scenarios.
- **Never rebuilding** — deleted rows are never removed from a bloom filter; schedule a full rebuild nightly to reset.

## Gotchas

- KV `arrayBuffer` values are limited to 25 MB per value — well above bloom filter needs but worth knowing.
- `Math.imul` in Workers returns a 32-bit signed integer; always apply `>>> 0` to get an unsigned value before the modulo.
- Filter KV key expiry causes the first request after expiry to rebuild from scratch; ensure the rebuild Cron Trigger runs before expiry.
- A standard bloom filter cannot delete elements; if deletions are frequent, use a counting bloom filter (4-bit counters per position) at 4x the storage cost.

## Verification

```typescript
// Sanity-check false positive rate
async function auditFilter(kv: KVNamespace): Promise<void> {
  const filter = await loadFilter(kv);
  const NOT_IN_SET = 'definitely-not-blocked@test.invalid';
  console.assert(!bloomCheck(filter, NOT_IN_SET), 'Should be a definite non-member');

  // Empirically measure FPR over a sample of synthetic non-members
  let falsePositives = 0;
  const TRIALS = 10_000;
  for (let i = 0; i < TRIALS; i++) {
    if (bloomCheck(filter, `fpr-test-${i}@x.invalid`)) falsePositives++;
  }
  console.log(`Measured FPR: ${(falsePositives / TRIALS * 100).toFixed(2)}%`);
}
```

## Related

- `d1-kv-cache-aside-pattern-workers.md`
- `d1-rate-limiting-sliding-window-workers.md`
- `d1-full-text-search-fts5.md`
- `kv-ttl-stale-while-revalidate-cache-workers.md`

## Sources

- SQLite / D1 docs: https://developers.cloudflare.com/d1/
- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- Bloom filter theory: https://en.wikipedia.org/wiki/Bloom_filter
