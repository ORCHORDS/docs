# Bitemporal Data Modeling — D1 & Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A regulatory audit requires reconstructing the state of a contract "as it was known on 1 Jan 2026, as of the data available at that time." A standard `updated_at` column cannot answer this: it conflates *when the business event occurred* (valid time) with *when the system learned about it* (transaction time). Bitemporal modeling maintains both timelines independently in D1 and enables point-in-time queries on either axis.

---

## Context

Bitemporality adds two date ranges to every fact row:

| Dimension | Column names | Question answered |
|---|---|---|
| Valid time | `valid_from` / `valid_to` | "When was this true in the real world?" |
| Transaction time | `recorded_from` / `recorded_to` | "When did our system know this?" |

A row is "current" only when both ranges include `NOW()`. Correcting a past mistake creates a new row with adjusted valid-time while the old (erroneous) row retains its transaction-time record — the audit trail is never overwritten.

D1 uses SQLite under the hood; SQLite has no native `daterange` type but ISO-8601 strings collate lexicographically and support between-comparison correctly.

---

## Schema

```sql
-- migrations/0001_bitemporal_contracts.sql
CREATE TABLE contract_history (
  id              TEXT NOT NULL,          -- business identity
  version_id      TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))),

  -- payload
  party_a         TEXT NOT NULL,
  party_b         TEXT NOT NULL,
  value_cents     INTEGER NOT NULL,

  -- valid time  (business time)
  valid_from      TEXT NOT NULL,          -- ISO-8601 e.g. '2025-01-01T00:00:00Z'
  valid_to        TEXT NOT NULL DEFAULT '9999-12-31T23:59:59Z',

  -- transaction time (system time)
  recorded_from   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  recorded_to     TEXT NOT NULL DEFAULT '9999-12-31T23:59:59Z',

  PRIMARY KEY (version_id)
);

CREATE INDEX idx_ch_id_vt  ON contract_history(id, valid_from, valid_to);
CREATE INDEX idx_ch_id_tt  ON contract_history(id, recorded_from, recorded_to);
```

---

## Writing a New Fact (Insert)

```typescript
// src/repositories/ContractRepository.ts
export async function insertContract(
  db: D1Database,
  contract: { id: string; partyA: string; partyB: string; valueCents: number; validFrom: string }
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO contract_history (id, party_a, party_b, value_cents, valid_from)
       VALUES (?, ?, ?, ?, ?)`
    )
    .bind(contract.id, contract.partyA, contract.partyB, contract.valueCents, contract.validFrom)
    .run();
}
```

---

## Correcting a Past Fact (Retroactive Amendment)

```typescript
// Retroactive correction: close the old transaction-time row, insert corrected row
export async function correctContract(
  db: D1Database,
  contractId: string,
  correction: { valueCents: number; validFrom: string; validTo?: string }
): Promise<void> {
  const now = new Date().toISOString();

  await db.batch([
    // Close all open transaction-time rows for this business id and valid period
    db.prepare(
      `UPDATE contract_history
       SET recorded_to = ?
       WHERE id = ? AND recorded_to = '9999-12-31T23:59:59Z'`
    ).bind(now, contractId),

    // Insert corrected row with same valid-time span, new transaction-time open
    db.prepare(
      `INSERT INTO contract_history (id, party_a, party_b, value_cents, valid_from, valid_to)
       SELECT ?, party_a, party_b, ?, ?, ?
       FROM contract_history
       WHERE id = ? AND recorded_to = ?
       ORDER BY recorded_from DESC LIMIT 1`
    ).bind(
      contractId,
      correction.valueCents,
      correction.validFrom,
      correction.validTo ?? "9999-12-31T23:59:59Z",
      contractId,
      now  // the row we just closed
    ),
  ]);
}
```

---

## Point-in-Time Queries

```typescript
// src/queries/bitemporalQueries.ts

/**
 * "As-of" query: state that was valid at `validAt` AND known by `asOf`
 * This answers: "What did we believe was true on validAt, as known on asOf?"
 */
export async function queryAsOf(
  db: D1Database,
  contractId: string,
  validAt: string,   // ISO-8601 valid-time moment
  asOf: string       // ISO-8601 transaction-time moment
): Promise<ContractRow | null> {
  return db
    .prepare(
      `SELECT id, party_a, party_b, value_cents, valid_from, valid_to, recorded_from
       FROM contract_history
       WHERE id = ?
         AND valid_from   <= ?  AND valid_to    > ?
         AND recorded_from <= ? AND recorded_to  > ?
       ORDER BY recorded_from DESC
       LIMIT 1`
    )
    .bind(contractId, validAt, validAt, asOf, asOf)
    .first<ContractRow>();
}

/**
 * Current state: valid now AND known now (the "normal" query most APIs need)
 */
export async function queryCurrent(
  db: D1Database,
  contractId: string
): Promise<ContractRow | null> {
  const now = new Date().toISOString();
  return queryAsOf(db, contractId, now, now);
}

/**
 * Full audit timeline: every version ever recorded, sorted by transaction time
 */
export async function queryAuditTrail(
  db: D1Database,
  contractId: string
): Promise<ContractRow[]> {
  const rows = await db
    .prepare(
      `SELECT * FROM contract_history WHERE id = ? ORDER BY recorded_from ASC`
    )
    .bind(contractId)
    .all<ContractRow>();
  return rows.results;
}
```

---

## Workers API Handler

```typescript
// src/handlers/contractHandler.ts
export async function handleContractQuery(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const id      = url.searchParams.get("id") ?? "";
  const validAt = url.searchParams.get("validAt");
  const asOf    = url.searchParams.get("asOf");

  if (!id) return new Response("id required", { status: 400 });

  if (validAt && asOf) {
    const row = await queryAsOf(env.DB, id, validAt, asOf);
    return row ? Response.json(row) : new Response("Not found", { status: 404 });
  }

  const row = await queryCurrent(env.DB, id);
  return row ? Response.json(row) : new Response("Not found", { status: 404 });
}

// Example requests:
// GET /contracts?id=C1                            → current state
// GET /contracts?id=C1&validAt=2025-06-01T00:00:00Z&asOf=2025-07-01T00:00:00Z → retroactive view
```

---

## Anti-patterns

- **Soft-delete instead of bitemporality**: marking rows `deleted=1` only records transaction-time deletion, not valid-time end; historical queries return ghost records.
- **Overwriting valid-time rows**: `UPDATE ... SET value = ?` erases the audit trail; always insert a new row and close the old one.
- **Using wall-clock `Date.now()` for valid-time**: valid time is a business fact (when the contract was signed), not when the system processes it; accept it as API input, never default it to `NOW()`.
- **Open-ended `valid_to = NULL`**: SQLite comparisons with NULL require `IS NULL` not `<`; use the sentinel value `9999-12-31T23:59:59Z` so standard `<` / `>` operators work.

---

## Gotchas

- **D1 batch atomicity**: the retroactive correction uses `db.batch([...])` for atomic close+insert; without batch, a crash between the two statements leaves orphaned open rows.
- **Index selectivity**: without the composite indexes on `(id, valid_from, valid_to)` and `(id, recorded_from, recorded_to)`, point-in-time queries degrade to full table scans — critical for large history tables.
- **Timezone handling**: store all timestamps in UTC (`Z` suffix); D1's `strftime` default is UTC, but client-supplied dates must be normalized before binding.
- **KV read model staleness**: if a KV projection is derived from the *current* row, it will lag behind retroactive corrections until explicitly refreshed via a rebuild trigger.

---

## Verification

```bash
# Insert a contract valid from 2025-01-01
wrangler d1 execute DB --local --command \
  "INSERT INTO contract_history (id, party_a, party_b, value_cents, valid_from) \
   VALUES ('C1','Acme','Beta',100000,'2025-01-01T00:00:00Z')"

# Query current state
curl "http://localhost:8787/contracts?id=C1"

# Retroactive correction (value was actually 120000)
curl -X POST http://localhost:8787/contracts/C1/correct \
  -d '{"valueCents":120000,"validFrom":"2025-01-01T00:00:00Z"}'

# Query as-of 2026-01-01 with data known only up to 2025-06-01 (sees original 100000)
curl "http://localhost:8787/contracts?id=C1&validAt=2025-06-01T00:00:00Z&asOf=2025-06-01T00:00:00Z"

# Query as-of 2026-01-01 with all knowledge (sees corrected 120000)
curl "http://localhost:8787/contracts?id=C1&validAt=2025-06-01T00:00:00Z&asOf=2026-08-23T00:00:00Z"
```

---

## Related

- `soft-delete-temporal-patterns-d1.md` — single-timeline temporal patterns (valid time only)
- `event-sourcing-d1-append-only-store.md` — append-only store as alternative audit trail
- `optimistic-concurrency-control-d1.md` — version-based locking for concurrent corrections
- `d1-batch-operations-query-optimisation.md` — batching D1 writes for atomicity
- `read-model-projection-workers-kv-cqrs.md` — projecting bitemporal data into a KV read model

---

## Sources

- Snodgrass, R. T. (1999). *Developing Time-Oriented Database Applications in SQL*. Morgan Kaufmann.
- Johnston, T. & Weis, R. (2010). *Managing Time in Relational Databases*. Morgan Kaufmann.
- Fowler, M. — "Temporal Patterns" (martinfowler.com)
- SQLite documentation — `strftime` and ISO-8601 string collation semantics
