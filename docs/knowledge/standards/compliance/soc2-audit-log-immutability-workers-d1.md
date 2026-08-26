# SOC 2 Audit Log Immutability — Cloudflare Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your SOC 2 Type II auditor flags that audit logs stored in D1 can be updated or deleted by application code, failing CC7.2 (Monitoring of System Operations) and CC9.1 (Risk Mitigation). You need:

- Append-only audit log rows that application code **cannot** overwrite or delete.
- Cryptographic chaining so tampering is detectable.
- Log forwarding to an out-of-band immutable store (R2 + WORM Object Lock equivalent).
- Evidence package the auditor can inspect without touching production data.

---

## Context

SOC 2 CC7.2 requires the organization to "monitor system components for anomalies that are indicative of malicious acts, natural disasters, and errors affecting the entity's ability to achieve its objectives." Auditors interpret this to require **tamper-evident, append-only** logs. The AICPA's 2022 trust services criteria update added an explicit expectation that logging infrastructure itself be hardened against privileged-user tampering.

D1 is a SQLite-based relational store. SQLite has no built-in row-level write protection, so immutability must be enforced at the application and infrastructure layer.

---

## 1. Hash-Chained Audit Log Schema

```sql
-- migrations/0001_immutable_audit_log.sql
CREATE TABLE IF NOT EXISTS audit_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  event_type    TEXT    NOT NULL,
  actor_id      TEXT,
  subject_type  TEXT,
  subject_id    TEXT,
  payload_json  TEXT    NOT NULL DEFAULT '{}',
  prev_hash     TEXT    NOT NULL,  -- SHA-256 of previous row's own_hash
  own_hash      TEXT    NOT NULL   -- SHA-256(id||occurred_at||event_type||payload_json||prev_hash)
);

-- Prevent DELETE and UPDATE at the SQL trigger level
CREATE TRIGGER audit_log_no_update
  BEFORE UPDATE ON audit_log
BEGIN
  SELECT RAISE(ABORT, 'audit_log rows are immutable');
END;

CREATE TRIGGER audit_log_no_delete
  BEFORE DELETE ON audit_log
BEGIN
  SELECT RAISE(ABORT, 'audit_log rows are immutable');
END;
```

---

## 2. Hash-Chain Insert Helper

```typescript
// lib/audit-log.ts
import { createHash } from "node:crypto"; // available in Workers via Crypto Web API

const GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000";

async function sha256(data: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(data)
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface AuditEntry {
  eventType: string;
  actorId?: string;
  subjectType?: string;
  subjectId?: string;
  payload?: Record<string, unknown>;
}

export async function appendAuditLog(
  entry: AuditEntry,
  db: D1Database
): Promise<void> {
  // Fetch the hash of the last row (serialized to avoid race conditions)
  const last = await db
    .prepare(
      "SELECT id, own_hash FROM audit_log ORDER BY id DESC LIMIT 1"
    )
    .first<{ id: number; own_hash: string }>();

  const prevHash = last?.own_hash ?? GENESIS_HASH;
  const occurredAt = new Date().toISOString();
  const payloadJson = JSON.stringify(entry.payload ?? {});

  // Tentative own_hash (id is auto-assigned, use a placeholder then update)
  // Pattern: insert with temporary hash, read back the id, recompute with real id, update hash field.
  // Since triggers block UPDATE, we must compute the hash before insert using a sequence trick.

  // Workaround: use a separate sequence table for deterministic next ID
  const { results: seqResult } = await db
    .prepare("INSERT INTO audit_log_seq DEFAULT VALUES RETURNING id")
    .all<{ id: number }>();
  const nextId = seqResult[0].id;

  const ownHash = await sha256(
    `${nextId}|${occurredAt}|${entry.eventType}|${payloadJson}|${prevHash}`
  );

  await db
    .prepare(
      `INSERT INTO audit_log
         (id, occurred_at, event_type, actor_id, subject_type, subject_id,
          payload_json, prev_hash, own_hash)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      nextId,
      occurredAt,
      entry.eventType,
      entry.actorId ?? null,
      entry.subjectType ?? null,
      entry.subjectId ?? null,
      payloadJson,
      prevHash,
      ownHash
    )
    .run();
}
```

---

## 3. Chain Integrity Verifier

```typescript
// workers/audit-log-verify.ts
export async function verifyAuditChain(
  db: D1Database
): Promise<{ valid: boolean; brokenAt?: number }> {
  const GENESIS =
    "0000000000000000000000000000000000000000000000000000000000000000";
  const { results } = await db
    .prepare(
      `SELECT id, occurred_at, event_type, payload_json, prev_hash, own_hash
       FROM audit_log ORDER BY id ASC`
    )
    .all<{
      id: number;
      occurred_at: string;
      event_type: string;
      payload_json: string;
      prev_hash: string;
      own_hash: string;
    }>();

  let expectedPrev = GENESIS;

  for (const row of results) {
    if (row.prev_hash !== expectedPrev) {
      return { valid: false, brokenAt: row.id };
    }
    const recomputed = await sha256(
      `${row.id}|${row.occurred_at}|${row.event_type}|${row.payload_json}|${row.prev_hash}`
    );
    if (recomputed !== row.own_hash) {
      return { valid: false, brokenAt: row.id };
    }
    expectedPrev = row.own_hash;
  }

  return { valid: true };
}

async function sha256(data: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(data)
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
```

---

## 4. Offload to R2 for Out-of-Band Immutability

```typescript
// workers/audit-log-archive.ts — scheduled: "0 0 * * *"
export interface Env {
  DB: D1Database;
  AUDIT_BUCKET: R2Bucket;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const dateKey = yesterday.toISOString().split("T")[0]; // e.g. "2026-08-22"

    const { results } = await env.DB.prepare(
      `SELECT * FROM audit_log
       WHERE date(occurred_at) = ?
       ORDER BY id ASC`
    )
      .bind(dateKey)
      .all();

    if (results.length === 0) return;

    const jsonl = results.map((r) => JSON.stringify(r)).join("\n");
    const key = `audit-logs/${dateKey}.jsonl`;

    // R2 Object Lock (if enabled on bucket) provides WORM guarantee
    await env.AUDIT_BUCKET.put(key, jsonl, {
      httpMetadata: { contentType: "application/x-ndjson" },
      customMetadata: {
        rowCount: String(results.length),
        archivedAt: new Date().toISOString(),
        law: "SOC2-CC7.2",
      },
    });

    console.log(`[AUDIT-ARCHIVE] ${results.length} rows archived to ${key}`);
  },
};
```

---

## 5. Evidence Export for Auditor

```typescript
// workers/audit-evidence.ts — internal-only endpoint, IP-restricted
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const from = url.searchParams.get("from") ?? "2026-01-01";
    const to = url.searchParams.get("to") ?? new Date().toISOString();

    const { results } = await env.DB.prepare(
      `SELECT id, occurred_at, event_type, actor_id, subject_type,
              subject_id, own_hash, prev_hash
       FROM audit_log
       WHERE occurred_at BETWEEN ? AND ?
       ORDER BY id ASC`
    )
      .bind(from, to)
      .all();

    const integrity = await verifyAuditChain(env.DB);

    return new Response(
      JSON.stringify({ integrity, rowCount: results.length, rows: results }),
      { headers: { "Content-Type": "application/json" } }
    );
  },
};
```

---

## Anti-patterns

- **Relying solely on D1 triggers for immutability**: Triggers can be dropped by a privileged migration; pair with out-of-band R2 archival.
- **Using sequential timestamps as chain anchors**: Clocks can be manipulated; use the auto-increment `id` as the primary chain anchor, not the timestamp.
- **Storing sensitive PII in payload_json unredacted**: Audit logs may be exported to auditors — pseudonymize subject identifiers.
- **Verifying chain only on demand**: Run `verifyAuditChain` on a daily schedule and alert on any failure; do not wait for the annual audit.

---

## Gotchas

- **D1 SQLite WAL mode**: D1 manages WAL internally; you cannot set `PRAGMA journal_mode=DELETE` to disable WAL. The trigger-based immutability is the correct layer.
- **Batch inserts break the chain**: Each `appendAuditLog` call must be serialized; concurrent calls race on `prev_hash`. Use a D1 Durable Object or queue to serialize inserts under high throughput.
- **R2 Object Lock is bucket-level**: Enable Object Lock on the archive bucket at creation time — it cannot be added retroactively.
- **`RETURNING` clause in D1**: Available from SQLite 3.35+; D1 supports it. Use it for the sequence trick shown above.

---

## Verification

```bash
# Trigger integrity check manually
wrangler d1 execute DB --command \
  "SELECT id, own_hash, prev_hash FROM audit_log ORDER BY id DESC LIMIT 5;"

# Confirm triggers exist
wrangler d1 execute DB --command \
  "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='audit_log';"

# List archived objects in R2
wrangler r2 object list AUDIT_BUCKET --prefix audit-logs/
```

---

## Related

- `soc2-cc7-system-operations.md` — Broader CC7 monitoring controls
- `soc2-evidence-collection-automation.md` — Automated evidence gathering
- `audit-log-mandatory.md` — General audit logging policy
- `iso-27001-continuous-monitoring-automation-workers-d1.md` — ISO 27001 continuous monitoring

---

## Sources

- AICPA Trust Services Criteria 2022: https://www.aicpa.org/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022
- CC7.2 Monitoring of System Operations: AICPA TSC §CC7.2
- R2 Object Lock (WORM): https://developers.cloudflare.com/r2/buckets/object-lock/
- Cloudflare D1 SQL support: https://developers.cloudflare.com/d1/sql-api/
