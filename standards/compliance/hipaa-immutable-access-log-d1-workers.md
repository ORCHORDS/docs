# HIPAA Immutable PHI Access Log — D1 + Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

HIPAA Security Rule §164.312(b) requires audit controls that "record and examine activity in information systems that contain or use ePHI." A mutable audit log — rows that can be UPDATEd or DELETEd by the application — fails OCR audit. You need a tamper-evident, append-only log in Cloudflare D1 backed by a Durable Object serialisation lock, with a hash-chain that surfaces any post-write modification during review.

## Context

D1 has no native row-level immutability or trigger support, so immutability is enforced at the application layer: (1) a Durable Object serialises all writes through a single in-order queue, (2) each row stores a SHA-256 hash of `previous_hash || record_data`, forming a chain auditors can verify offline, and (3) a separate read-only D1 binding (no INSERT/DELETE) is exposed to the API layer while the DO holds the write binding.

---

## 1. Audit Log Schema

```sql
-- migrations/0002_phi_audit.sql
CREATE TABLE phi_access_log (
  seq          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts           INTEGER NOT NULL,         -- Unix epoch seconds
  user_id      TEXT    NOT NULL,         -- workforce member
  patient_id   TEXT    NOT NULL,         -- de-identified or token
  resource     TEXT    NOT NULL,         -- e.g. "record/12345"
  action       TEXT    NOT NULL,         -- READ | WRITE | DELETE | EXPORT
  outcome      TEXT    NOT NULL,         -- SUCCESS | DENIED
  client_ip    TEXT,
  prev_hash    TEXT    NOT NULL,
  row_hash     TEXT    NOT NULL,
  signature    TEXT                      -- optional HSM signature
);
-- No UPDATE or DELETE privileges granted to the app service account
```

## 2. Durable Object — Serialised Append

```typescript
// src/do/PhiAuditLogDO.ts
export class PhiAuditLogDO implements DurableObject {
  private lastHash: string | null = null;

  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(req: Request): Promise<Response> {
    const entry = await req.json<PhiAccessEntry>();
    return this.state.blockConcurrencyWhile(() => this.append(entry));
  }

  private async append(entry: PhiAccessEntry): Promise<Response> {
    const ts = Math.floor(Date.now() / 1000);

    // Fetch previous hash from storage (survives eviction)
    if (this.lastHash === null) {
      this.lastHash =
        (await this.state.storage.get<string>('lastHash')) ?? 'GENESIS';
    }

    const payload = JSON.stringify({
      ts,
      ...entry,
      prev_hash: this.lastHash,
    });

    const hashBuf = await crypto.subtle.digest(
      'SHA-256',
      new TextEncoder().encode(payload),
    );
    const rowHash = bufToHex(hashBuf);

    await this.env.DB.prepare(
      `INSERT INTO phi_access_log
         (ts, user_id, patient_id, resource, action, outcome, client_ip, prev_hash, row_hash)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        ts,
        entry.userId,
        entry.patientId,
        entry.resource,
        entry.action,
        entry.outcome,
        entry.clientIp ?? null,
        this.lastHash,
        rowHash,
      )
      .run();

    this.lastHash = rowHash;
    await this.state.storage.put('lastHash', rowHash);

    return new Response(JSON.stringify({ ok: true, seq: rowHash }), {
      status: 201,
    });
  }
}

function bufToHex(buf: ArrayBuffer): string {
  return [...new Uint8Array(buf)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
```

## 3. Worker Middleware — Auto-log PHI Access

```typescript
// src/middleware/phiAudit.ts
import type { Env } from '../types';

export async function withPhiAudit(
  req: Request,
  env: Env,
  ctx: ExecutionContext,
  next: () => Promise<Response>,
): Promise<Response> {
  const userId = req.headers.get('X-User-Id') ?? 'unknown';
  const clientIp = req.headers.get('CF-Connecting-IP') ?? undefined;
  const resource = new URL(req.url).pathname;

  const res = await next();

  const entry: PhiAccessEntry = {
    userId,
    patientId: req.headers.get('X-Patient-Id') ?? 'unknown',
    resource,
    action: methodToAction(req.method),
    outcome: res.status < 400 ? 'SUCCESS' : 'DENIED',
    clientIp,
  };

  // Fire-and-forget via DO — use waitUntil so it survives response flush
  const doId = env.PHI_AUDIT_LOG.idFromName('singleton');
  const stub = env.PHI_AUDIT_LOG.get(doId);
  ctx.waitUntil(
    stub.fetch('https://do/append', {
      method: 'POST',
      body: JSON.stringify(entry),
    }),
  );

  return res;
}

function methodToAction(method: string): string {
  return (
    { GET: 'READ', POST: 'WRITE', PUT: 'WRITE', DELETE: 'DELETE' }[method] ??
    'READ'
  );
}
```

## 4. Offline Chain Verification Script

```typescript
// scripts/verifyChain.ts  (Node.js — run during audit)
import { createHash } from 'node:crypto';

interface LogRow {
  seq: number;
  ts: number;
  user_id: string;
  patient_id: string;
  resource: string;
  action: string;
  outcome: string;
  client_ip: string | null;
  prev_hash: string;
  row_hash: string;
}

async function verifyChain(rows: LogRow[]): Promise<void> {
  let prevHash = 'GENESIS';
  for (const row of rows) {
    if (row.prev_hash !== prevHash) {
      throw new Error(`Chain break at seq=${row.seq}: expected ${prevHash}`);
    }
    const payload = JSON.stringify({
      ts: row.ts,
      userId: row.user_id,
      patientId: row.patient_id,
      resource: row.resource,
      action: row.action,
      outcome: row.outcome,
      clientIp: row.client_ip,
      prev_hash: row.prev_hash,
    });
    const computed = createHash('sha256').update(payload).digest('hex');
    if (computed !== row.row_hash) {
      throw new Error(`Hash mismatch at seq=${row.seq}`);
    }
    prevHash = row.row_hash;
  }
  console.log(`Chain valid — ${rows.length} rows verified`);
}
```

## 5. wrangler.toml

```toml
[[d1_databases]]
binding       = "DB"
database_name = "phi-db"
database_id   = "<your-d1-id>"

[[durable_objects.bindings]]
name       = "PHI_AUDIT_LOG"
class_name = "PhiAuditLogDO"

[migrations]
tag = "v1"
new_classes = ["PhiAuditLogDO"]
```

## 6. Scheduled Chain Integrity Check

```typescript
// src/scheduled/chainCheck.ts
export async function scheduledChainCheck(env: Env): Promise<void> {
  const { results } = await env.DB.prepare(
    `SELECT seq, prev_hash, row_hash FROM phi_access_log ORDER BY seq DESC LIMIT 1`,
  ).all<{ seq: number; prev_hash: string; row_hash: string }>();

  // Store latest known-good hash in KV for comparison each run
  const stored = await env.KV.get('phi:lastVerifiedHash');
  const current = results[0]?.row_hash ?? 'GENESIS';

  if (stored && stored !== results[0]?.prev_hash) {
    await env.ALERT_QUEUE.send({
      severity: 'CRITICAL',
      message: `PHI audit chain integrity failure at seq=${results[0]?.seq}`,
    });
  }
  await env.KV.put('phi:lastVerifiedHash', current);
}
```

---

## Anti-patterns

- Using `UPDATE phi_access_log SET ... WHERE seq = ?` anywhere in the app — breaks the chain and defeats the purpose.
- Logging only failures — HIPAA §164.312(b) requires logging all access, including successful reads.
- Storing the DO's `lastHash` only in memory without `state.storage.put()` — it resets on eviction, breaking the chain.
- Skipping `blockConcurrencyWhile` — concurrent writes produce non-deterministic `prev_hash` ordering.

## Gotchas

- D1 `AUTOINCREMENT` guarantees monotonic integers within a single DB but is not a global ordering guarantee across partitions; use the hash chain as the integrity anchor, not `seq`.
- `crypto.subtle.digest` returns a `Promise<ArrayBuffer>` — always `await` it inside the DO method.
- The Durable Object `singleton` pattern works for low-write-volume audit logs (<100 writes/sec); for high-throughput PHI systems, shard by `floor(patientId hash % N)` DOs.
- OCR expects 6-year retention; D1 has no native TTL — export monthly snapshots to R2 with Object Lock enabled.

## Verification

```bash
# Tail recent access log
wrangler d1 execute phi-db \
  --command "SELECT seq, ts, user_id, action, outcome FROM phi_access_log ORDER BY seq DESC LIMIT 20;"

# Dump full log for offline chain verification
wrangler d1 execute phi-db \
  --command "SELECT * FROM phi_access_log ORDER BY seq ASC;" \
  --json > /tmp/phi_export.json

npx ts-node scripts/verifyChain.ts /tmp/phi_export.json
```

## Related

- `hipaa-audit-controls.md`
- `hipaa-technical-safeguards-web-api.md`
- `soc2-audit-log-immutability-workers-d1.md`
- `nist-800-53-access-control-ac-family-workers.md`

## Sources

- HIPAA Security Rule 45 CFR §164.312(b) — Audit Controls
- HHS OCR Audit Protocol — https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/audit/protocol/index.html
- Cloudflare Durable Objects — blockConcurrencyWhile: https://developers.cloudflare.com/durable-objects/api/
- NIST SP 800-92 — Guide to Computer Security Log Management
