# CRDT Conflict Resolution for Offline-First D1 Sync (SQLite)
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Mobile or PWA clients maintain a local SQLite copy (via `sqlite-wasm` or the OPFS adapter)
and sync with Cloudflare D1 when connectivity is restored. Two users edit the same record
offline. On reconnect, both submit divergent versions. You need deterministic, convergent
conflict resolution without a central arbitrator being online at write time.

## Context

CRDTs (Conflict-free Replicated Data Types) provide mathematical guarantees that any set of
concurrent updates, applied in any order, converges to the same final state. In a D1
architecture, the canonical store lives in Cloudflare D1 (SQLite over HTTP). Each client
runs a local SQLite via `@sqlite.org/sqlite-wasm` in the browser or a native SQLite on
mobile, periodically pushing a delta log to a Cloudflare Worker that merges into D1.

Three CRDT strategies map cleanly onto SQLite's row-oriented model:

| Strategy | Data shape | Convergence rule |
|----------|-----------|-----------------|
| LWW Register | Single value per key | Higher `hlc` (Hybrid Logical Clock) wins |
| G-Counter / PN-Counter | Numeric aggregates | Sum per replica; never decrement a replica's own slot |
| OR-Set | Set membership | Union of (element, unique-tag) pairs; remove only own tag |

This article focuses on LWW Register with Hybrid Logical Clocks (HLC) as it covers the
widest range of record-level edits.

---

## Hybrid Logical Clocks in SQLite

A HLC combines a physical wall-clock component with a logical counter to produce a monotone
timestamp even when clocks skew between devices.

```sql
-- migrations/0010_hlc_support.sql

-- HLC stored as "physical_ms:logical:node_id" text for human readability,
-- or as a 128-bit blob (two 64-bit integers) for compact storage.
-- We use TEXT here for debuggability.

CREATE TABLE IF NOT EXISTS hlc_state (
  node_id   TEXT PRIMARY KEY,
  pt        INTEGER NOT NULL DEFAULT 0,  -- physical time ms
  lc        INTEGER NOT NULL DEFAULT 0   -- logical counter
);

-- Insert once per client on first sync registration
INSERT OR IGNORE INTO hlc_state (node_id, pt, lc)
VALUES ('client-' || hex(randomblob(8)), 0, 0);
```

Worker-side HLC tick function (TypeScript):

```typescript
// src/hlc.ts

export interface HLC {
  pt: number; // physical ms
  lc: number; // logical counter
  node: string;
}

export function hlcTick(local: HLC, received?: HLC): HLC {
  const now = Date.now();
  if (!received) {
    // Local event
    const pt = Math.max(local.pt, now);
    const lc = pt === local.pt ? local.lc + 1 : 0;
    return { pt, lc, node: local.node };
  }
  // Merge with incoming
  const pt = Math.max(local.pt, received.pt, now);
  let lc: number;
  if (pt === local.pt && pt === received.pt) {
    lc = Math.max(local.lc, received.lc) + 1;
  } else if (pt === local.pt) {
    lc = local.lc + 1;
  } else if (pt === received.pt) {
    lc = received.lc + 1;
  } else {
    lc = 0;
  }
  return { pt, lc, node: local.node };
}

export function hlcCompare(a: HLC, b: HLC): number {
  if (a.pt !== b.pt) return a.pt - b.pt;
  if (a.lc !== b.lc) return a.lc - b.lc;
  return a.node < b.node ? -1 : a.node > b.node ? 1 : 0;
}

export function hlcToString(h: HLC): string {
  return `${h.pt.toString(36).padStart(11, "0")}:${h.lc.toString(36).padStart(5, "0")}:${h.node}`;
}

export function hlcFromString(s: string): HLC {
  const [pt, lc, node] = s.split(":");
  return { pt: parseInt(pt, 36), lc: parseInt(lc, 36), node };
}
```

---

## LWW Column-Level Merge Schema

Column-level LWW (Last Write Wins) tracks a separate HLC per column, enabling concurrent
edits to different fields of the same row to merge without conflict.

```sql
-- Column-level LWW for the `documents` table
CREATE TABLE IF NOT EXISTS documents (
  id          TEXT PRIMARY KEY,
  title       TEXT,
  body        TEXT,
  status      TEXT CHECK(status IN ('draft','published','archived')),
  updated_at  TEXT NOT NULL DEFAULT ''      -- ISO 8601 wall clock (display only)
);

-- Separate tombstone table for HLC-per-column tracking
CREATE TABLE IF NOT EXISTS documents_clocks (
  doc_id      TEXT NOT NULL,
  col_name    TEXT NOT NULL,
  hlc         TEXT NOT NULL,    -- "pt:lc:node" string
  PRIMARY KEY (doc_id, col_name)
);

-- Tombstone table for deleted documents
CREATE TABLE IF NOT EXISTS documents_tombstones (
  doc_id  TEXT PRIMARY KEY,
  hlc     TEXT NOT NULL
);
```

---

## Sync Protocol: Client Delta Push

Clients accumulate an outbox of mutations tagged with HLC values:

```typescript
// Client-side outbox (local SQLite via sqlite-wasm)
interface Mutation {
  table: string;
  row_id: string;
  col: string;
  value: string | null;  // null = tombstone
  hlc: string;
  client_id: string;
}
```

```sql
-- Local client outbox table
CREATE TABLE IF NOT EXISTS outbox (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  table_name TEXT NOT NULL,
  row_id     TEXT NOT NULL,
  col        TEXT NOT NULL,
  value      TEXT,          -- NULL means delete
  hlc        TEXT NOT NULL,
  synced     INTEGER NOT NULL DEFAULT 0
);
```

Push delta to Worker:

```typescript
// src/sync-push.ts
export async function pushDelta(env: Env, mutations: Mutation[]): Promise<void> {
  // Group by table for efficient batch processing
  const byTable = Map.groupBy(mutations, (m) => m.table);

  for (const [table, rows] of byTable) {
    await env.DB.batch(
      rows.map((m) =>
        env.DB.prepare(
          `INSERT INTO sync_log (table_name, row_id, col, value, hlc, client_id)
           VALUES (?, ?, ?, ?, ?, ?)`
        ).bind(table, m.row_id, m.col, m.value, m.hlc, m.client_id)
      )
    );
  }

  await applyMutations(env, mutations);
}
```

---

## Server-Side LWW Merge in D1

```typescript
// src/crdt-merge.ts
import { hlcCompare, hlcFromString } from "./hlc";
import type { Env } from "./types";

export async function applyLwwMutation(
  db: D1Database,
  table: string,
  rowId: string,
  col: string,
  incomingValue: string | null,
  incomingHlcStr: string
): Promise<"applied" | "skipped"> {
  // 1. Read current clock for this column
  const existing = await db
    .prepare(
      `SELECT hlc FROM ${table}_clocks WHERE doc_id = ? AND col_name = ?`
    )
    .bind(rowId, col)
    .first<{ hlc: string }>();

  if (existing) {
    const existingHlc = hlcFromString(existing.hlc);
    const incomingHlc = hlcFromString(incomingHlcStr);
    if (hlcCompare(incomingHlc, existingHlc) <= 0) {
      // Incoming is older or equal — discard
      return "skipped";
    }
  }

  // 2. Apply the winning value
  if (incomingValue === null) {
    // Tombstone — soft delete
    await db.batch([
      db.prepare(`DELETE FROM ${table} WHERE id = ?`).bind(rowId),
      db.prepare(
        `INSERT OR REPLACE INTO ${table}_tombstones (doc_id, hlc) VALUES (?, ?)`
      ).bind(rowId, incomingHlcStr),
    ]);
  } else {
    await db.batch([
      // Upsert the row value
      db.prepare(
        `INSERT INTO ${table} (id, ${col}) VALUES (?, ?)
         ON CONFLICT(id) DO UPDATE SET ${col} = excluded.${col}`
      ).bind(rowId, incomingValue),
      // Update the column clock
      db.prepare(
        `INSERT OR REPLACE INTO ${table}_clocks (doc_id, col_name, hlc) VALUES (?, ?, ?)`
      ).bind(rowId, col, incomingHlcStr),
    ]);
  }

  return "applied";
}
```

---

## Pull / Bootstrap: Sending Server State to Client

```typescript
// src/sync-pull.ts
export async function pullChanges(
  db: D1Database,
  clientId: string,
  sinceHlc: string
): Promise<Mutation[]> {
  // Return all mutations newer than client's last known HLC
  const rows = await db
    .prepare(
      `SELECT table_name, row_id, col, value, hlc, client_id
       FROM   sync_log
       WHERE  hlc > ?
         AND  client_id != ?   -- skip own mutations reflected back
       ORDER  BY hlc ASC
       LIMIT  500`
    )
    .bind(sinceHlc, clientId)
    .all<Mutation>();

  return rows.results;
}
```

Client applies pulled mutations using the same `applyLwwMutation` logic against local SQLite.

---

## Anti-patterns

- **Wall-clock LWW without logical counters**: Pure `Date.now()` timestamps collide when two
  devices write at the same millisecond. Always use HLC or Lamport clocks.

- **Full-row replace on conflict**: Replacing the entire row discards concurrent edits to
  other columns. Column-level LWW prevents this.

- **No tombstone tracking**: Deleting from the main table and forgetting the HLC means a
  later offline-created version with an older HLC can resurrect the row. Always write a
  tombstone before deleting.

- **Unbounded sync_log growth**: The log table accumulates indefinitely. Prune entries older
  than the earliest `sinceHlc` across all known clients using a background Cron Trigger.

- **Mixing CRDT sync with normal `UPDATE` statements**: Any write that bypasses HLC stamping
  creates an invisible mutation. Gate all writes through the outbox path.

---

## Gotchas

- **SQLite `TEXT` comparison for HLC strings**: The zero-padded base-36 format ensures
  lexicographic ordering matches numeric ordering. Verify with `SELECT '0000a' < '0000b'` = 1.

- **D1's read-your-writes guarantee is local**: After a Worker writes, reads in the same
  request see the update. But a second Worker invocation (e.g., a pull request) may hit a
  replica without the just-applied mutation for a brief window. Apply a small delay or use
  Durable Objects to serialize.

- **`ON CONFLICT` and generated columns**: If `id` uses a generated column expression,
  `ON CONFLICT(id)` may not resolve correctly. Prefer explicit primary keys.

- **Integer overflow in logical counters**: 32-bit integers wrap at ~4 billion. Use 53-bit
  safe integers in JS (`Number`) or switch to `BigInt` if lc could exceed `Number.MAX_SAFE_INTEGER`.

---

## Verification

```sql
-- Confirm no document has a newer data HLC than its clock record (drift check)
SELECT d.id,
       dc.hlc  AS clock_hlc,
       sl.hlc  AS log_hlc
FROM   documents d
JOIN   documents_clocks dc ON dc.doc_id = d.id AND dc.col_name = 'body'
LEFT   JOIN sync_log sl
  ON   sl.row_id = d.id AND sl.col = 'body'
 AND   sl.hlc > dc.hlc
WHERE  sl.hlc IS NOT NULL;

-- Count skipped vs applied mutations in last sync run
SELECT outcome, COUNT(*) FROM sync_results GROUP BY outcome;
```

---

## Related

- `sqlite-wasm-offline-d1-sync.md` — OPFS setup and sync transport layer
- `d1-batch-operations-performance.md` — batching mutation applies efficiently
- `d1-foreign-keys-referential-integrity.md` — FK constraints interact with tombstone deletes
- `eventual-consistency-patterns.md` — broader eventual consistency theory
- `optimistic-locking-version-column.md` — simpler alternative when offline edits are rare

## Sources

- Hybrid Logical Clocks paper: Kulkarni et al., 2014 https://cse.buffalo.edu/tech-reports/2014-04.pdf
- Electric SQL CRDT implementation: https://electric-sql.com/docs/api/clients/typescript
- SQLite CRDT patterns: https://vlcn.io/docs/cr-sqlite/
- Cloudflare D1 Durable Object consistency: https://developers.cloudflare.com/d1/reference/data-location/
