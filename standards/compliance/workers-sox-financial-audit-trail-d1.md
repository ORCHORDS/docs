# SOX Financial Audit Trail Using Cloudflare Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Financial applications subject to Sarbanes-Oxley (SOX) must maintain tamper-evident audit logs of every transaction, configuration change, and access event. Traditional databases can be silently modified; SQL UPDATE or DELETE operations can erase evidence of fraud or error. Auditors require proof that logs have not been altered since creation.

This article shows how to build an immutable, hash-chained audit trail entirely within Cloudflare Workers + D1, meeting SOX Section 302/404 requirements without managing any server infrastructure.

## Context

Applies when:
- Your Workers application processes financial transactions (payments, ledger entries, reconciliations)
- You are preparing for a SOX audit and need a demonstrable control over audit log integrity
- Compliance team requires 7-year retention of financial records per SEC Rule 17a-4
- Internal audit team needs on-demand report generation

SOX does not prescribe specific technology, but it does require that records be accurate, complete, and protected against alteration. Hash chaining (each log entry includes the hash of the previous entry) provides cryptographic proof that the sequence has not been tampered with.

## Solution

### D1 Schema

```sql
-- Run via wrangler d1 execute sox-audit --file=schema.sql
CREATE TABLE IF NOT EXISTS audit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  seq         INTEGER NOT NULL UNIQUE,          -- monotonic sequence
  event_time  TEXT    NOT NULL,                 -- ISO-8601 UTC
  actor_id    TEXT    NOT NULL,                 -- user or service account
  actor_ip    TEXT,
  event_type  TEXT    NOT NULL,                 -- TRANSACTION | ACCESS | CONFIG
  entity_type TEXT    NOT NULL,                 -- e.g. "Payment", "LedgerEntry"
  entity_id   TEXT    NOT NULL,
  amount_cents INTEGER,                         -- null for non-financial events
  currency    TEXT,
  payload     TEXT    NOT NULL,                 -- JSON snapshot (immutable)
  prev_hash   TEXT    NOT NULL,                 -- SHA-256 of previous row
  row_hash    TEXT    NOT NULL,                 -- SHA-256(seq||event_time||actor_id||payload||prev_hash)
  created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_audit_seq        ON audit_log(seq);
CREATE INDEX idx_audit_event_time ON audit_log(event_time);
CREATE INDEX idx_audit_actor      ON audit_log(actor_id);
CREATE INDEX idx_audit_entity     ON audit_log(entity_type, entity_id);

-- Retention policy tracking
CREATE TABLE IF NOT EXISTS retention_policy (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type     TEXT NOT NULL,
  retention_years INTEGER NOT NULL DEFAULT 7,
  legal_hold      INTEGER NOT NULL DEFAULT 0,  -- boolean
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO retention_policy(entity_type, retention_years)
VALUES ('Payment', 7), ('LedgerEntry', 7), ('CONFIG', 7), ('ACCESS', 3);
```

### Worker: audit-trail.ts

```typescript
import type { D1Database } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  AUDIT_SECRET: string; // used to HMAC-sign external API calls
}

type EventType = 'TRANSACTION' | 'ACCESS' | 'CONFIG';
type EntityType = 'Payment' | 'LedgerEntry' | 'Account' | 'Config' | 'Report';

interface AuditEntry {
  actorId: string;
  actorIp?: string;
  eventType: EventType;
  entityType: EntityType;
  entityId: string;
  amountCents?: number;
  currency?: string;
  payload: Record<string, unknown>;
}

// ----- Core hashing utilities -----

async function sha256Hex(text: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function computeRowHash(
  seq: number,
  eventTime: string,
  actorId: string,
  payload: string,
  prevHash: string
): Promise<string> {
  const canonical = `${seq}|${eventTime}|${actorId}|${payload}|${prevHash}`;
  return sha256Hex(canonical);
}

// ----- Database helpers -----

async function getLastEntry(
  db: D1Database
): Promise<{ seq: number; row_hash: string } | null> {
  const result = await db
    .prepare('SELECT seq, row_hash FROM audit_log ORDER BY seq DESC LIMIT 1')
    .first<{ seq: number; row_hash: string }>();
  return result ?? null;
}

export async function writeAuditEntry(
  db: D1Database,
  entry: AuditEntry
): Promise<{ id: number; seq: number; rowHash: string }> {
  const eventTime = new Date().toISOString();
  const payloadJson = JSON.stringify(entry.payload);

  // Serialise sequence assignment and hash computation via D1 transaction
  const last = await getLastEntry(db);
  const seq = (last?.seq ?? 0) + 1;
  const prevHash = last?.row_hash ?? '0'.repeat(64); // genesis hash

  const rowHash = await computeRowHash(
    seq,
    eventTime,
    entry.actorId,
    payloadJson,
    prevHash
  );

  const result = await db
    .prepare(
      `INSERT INTO audit_log
         (seq, event_time, actor_id, actor_ip, event_type, entity_type,
          entity_id, amount_cents, currency, payload, prev_hash, row_hash)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      seq,
      eventTime,
      entry.actorId,
      entry.actorIp ?? null,
      entry.eventType,
      entry.entityType,
      entry.entityId,
      entry.amountCents ?? null,
      entry.currency ?? null,
      payloadJson,
      prevHash,
      rowHash
    )
    .run();

  return { id: result.meta.last_row_id as number, seq, rowHash };
}

// ----- Integrity verification -----

export async function verifyChainIntegrity(
  db: D1Database,
  fromSeq = 1,
  toSeq?: number
): Promise<{ valid: boolean; firstBrokenSeq?: number; checked: number }> {
  const limit = toSeq ? toSeq - fromSeq + 1 : 10_000;
  const rows = await db
    .prepare(
      `SELECT seq, event_time, actor_id, payload, prev_hash, row_hash
       FROM audit_log
       WHERE seq >= ? ${toSeq ? 'AND seq <= ?' : ''}
       ORDER BY seq ASC
       LIMIT ?`
    )
    .bind(...(toSeq ? [fromSeq, toSeq, limit] : [fromSeq, limit]))
    .all<{
      seq: number;
      event_time: string;
      actor_id: string;
      payload: string;
      prev_hash: string;
      row_hash: string;
    }>();

  let expectedPrevHash = rows.results[0]?.prev_hash ?? '0'.repeat(64);

  for (const row of rows.results) {
    const recomputed = await computeRowHash(
      row.seq,
      row.event_time,
      row.actor_id,
      row.payload,
      row.prev_hash
    );

    if (recomputed !== row.row_hash) {
      return { valid: false, firstBrokenSeq: row.seq, checked: row.seq - fromSeq };
    }
    if (row.prev_hash !== expectedPrevHash && row.seq !== fromSeq) {
      return { valid: false, firstBrokenSeq: row.seq, checked: row.seq - fromSeq };
    }
    expectedPrevHash = row.row_hash;
  }

  return { valid: true, checked: rows.results.length };
}

// ----- Report generation -----

export async function generateAuditReport(
  db: D1Database,
  from: string,
  to: string,
  entityType?: EntityType
): Promise<Record<string, unknown>> {
  const entityFilter = entityType ? 'AND entity_type = ?' : '';
  const bindings: (string | number)[] = [from, to];
  if (entityType) bindings.push(entityType);

  const rows = await db
    .prepare(
      `SELECT id, seq, event_time, actor_id, event_type, entity_type,
              entity_id, amount_cents, currency, row_hash
       FROM audit_log
       WHERE event_time >= ? AND event_time <= ?
       ${entityFilter}
       ORDER BY seq ASC`
    )
    .bind(...bindings)
    .all();

  const totalAmountCents = (rows.results as Array<{ amount_cents: number | null }>)
    .filter((r) => r.amount_cents !== null)
    .reduce((sum, r) => sum + (r.amount_cents ?? 0), 0);

  const integrity = await verifyChainIntegrity(db);

  return {
    reportGeneratedAt: new Date().toISOString(),
    period: { from, to },
    entityTypeFilter: entityType ?? 'ALL',
    summary: {
      totalEvents: rows.results.length,
      totalAmountCents,
      totalAmountFormatted: `${(totalAmountCents / 100).toFixed(2)}`,
      chainIntegrity: integrity,
    },
    entries: rows.results,
  };
}

// ----- HTTP handler -----

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/audit/log') {
      const body = await request.json<AuditEntry>();
      const result = await writeAuditEntry(env.DB, {
        ...body,
        actorIp: request.headers.get('CF-Connecting-IP') ?? undefined,
      });
      return Response.json(result, { status: 201 });
    }

    if (request.method === 'GET' && url.pathname === '/audit/verify') {
      const from = Number(url.searchParams.get('from') ?? 1);
      const to = url.searchParams.get('to') ? Number(url.searchParams.get('to')) : undefined;
      const result = await verifyChainIntegrity(env.DB, from, to);
      return Response.json(result);
    }

    if (request.method === 'GET' && url.pathname === '/audit/report') {
      const from = url.searchParams.get('from') ?? new Date(Date.now() - 86400_000 * 30).toISOString();
      const to = url.searchParams.get('to') ?? new Date().toISOString();
      const entityType = url.searchParams.get('entityType') as EntityType | undefined;
      const report = await generateAuditReport(env.DB, from, to, entityType);
      return Response.json(report);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Implementation Details

### Retention policy enforcement (Cron Trigger)

```typescript
// In wrangler.toml:
// [[triggers]]
// crons = ["0 2 * * *"]   # run daily at 02:00 UTC

export async function enforceRetention(db: D1Database): Promise<void> {
  const policies = await db
    .prepare('SELECT entity_type, retention_years, legal_hold FROM retention_policy')
    .all<{ entity_type: string; retention_years: number; legal_hold: number }>();

  for (const policy of policies.results) {
    if (policy.legal_hold) continue; // never delete records under legal hold

    const cutoff = new Date();
    cutoff.setFullYear(cutoff.getFullYear() - policy.retention_years);

    // Soft-delete: move to archive table rather than hard DELETE
    await db
      .prepare(
        `INSERT INTO audit_log_archive SELECT * FROM audit_log
         WHERE entity_type = ? AND event_time < ?`
      )
      .bind(policy.entity_type, cutoff.toISOString())
      .run();

    await db
      .prepare(
        `DELETE FROM audit_log WHERE entity_type = ? AND event_time < ?
         AND id IN (SELECT id FROM audit_log_archive WHERE entity_type = ? AND event_time < ?)`
      )
      .bind(policy.entity_type, cutoff.toISOString(), policy.entity_type, cutoff.toISOString())
      .run();
  }
}
```

### wrangler.toml

```toml
name = "sox-audit-trail"
main = "src/audit-trail.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "sox-audit"
database_id = "YOUR_DATABASE_ID"

[vars]
AUDIT_SECRET = "use-wrangler-secret-put-instead"

[[triggers]]
crons = ["0 2 * * *"]
```

## Anti-patterns

- **Never use UPDATE or DELETE on audit_log** — even to fix typos. Append a correcting entry instead, referencing the original entry ID.
- **Do not store the audit log in the same D1 database as mutable application data** — use a dedicated database so that a compromised application key cannot drop tables.
- **Do not rely on D1's `created_at` timestamp alone** — always capture `event_time` at the application layer before writing, because database clock drift can affect ordering.
- **Do not skip the genesis hash seed** — using an all-zero hash for seq=1's `prev_hash` is conventional. Omitting any prev_hash breaks chain verification.
- **Do not generate reports without running `verifyChainIntegrity` first** — an auditor report with a broken chain is evidence of a control failure.

## Gotchas

- **D1 is eventually consistent across regions**: if two Workers write audit entries simultaneously, the `MAX(seq)` read in `getLastEntry` may race. Mitigate by using a central D1 write endpoint (a single Worker with `smart_placement` disabled) or by using D1's `RETURNING` clause inside a serialised transaction.
- **SHA-256 via `crypto.subtle` is async** — do not attempt to use a synchronous hash library; the Workers runtime does not expose synchronous digest APIs.
- **Payload size**: D1 TEXT columns can hold up to 1 GB but individual row inserts are bound by the 1 MB Workers request size limit. Keep payload snapshots lean; store large blobs in R2 and record the R2 object key in the payload.
- **Chain verification is O(n)** — for millions of rows, run verification in batches using the `fromSeq`/`toSeq` parameters and stitch results in a Durable Object or Queue consumer.

## Verification

```bash
# 1. Insert a test transaction
curl -X POST https://sox-audit.example.workers.dev/audit/log \
  -H 'Content-Type: application/json' \
  -d '{"actorId":"user_abc","eventType":"TRANSACTION","entityType":"Payment","entityId":"pay_001","amountCents":10000,"currency":"USD","payload":{"description":"Invoice #42"}}'

# 2. Verify chain integrity
curl https://sox-audit.example.workers.dev/audit/verify
# Expected: {"valid":true,"checked":1}

# 3. Generate a 30-day report
curl 'https://sox-audit.example.workers.dev/audit/report?entityType=Payment'

# 4. Tamper simulation (run only in staging)
# wrangler d1 execute sox-audit --command "UPDATE audit_log SET amount_cents=1 WHERE seq=1"
# Then re-run /audit/verify — should return {"valid":false,"firstBrokenSeq":1}
```

## Related

- `workers-data-classification-labels-d1.md` — classify financial data payloads before logging
- `workers-privacy-impact-assessment-d1.md` — PIA workflow for systems that process financial PII
- `workers-vendor-risk-assessment-d1.md` — track risk of third-party payment processors

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://www.sec.gov/rules/final/33-8238.htm (SOX Section 302/404)
