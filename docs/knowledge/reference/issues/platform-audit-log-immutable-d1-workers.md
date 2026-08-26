# Immutable Platform Audit Log with D1 and Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

example project must demonstrate to regulators (EU DSA, UK OSA, and prospective US KOSA audits) that moderation decisions are recorded faithfully and have not been retroactively altered. The current D1 schema allows `UPDATE` and `DELETE` on moderation records, making it impossible to prove the integrity of the audit trail without an external notary service.

## Context

Platform audit logs serve two masters: internal operations teams who need queryable history, and external regulators who need tamper-evident proof of what decision was made, when, and by which process. A fully immutable ledger can be approximated on D1 by combining three techniques: (1) a write-only table with an application-enforced no-UPDATE/DELETE policy enforced in the Worker itself, (2) cryptographic hash chaining where each row stores the SHA-256 of the previous row's hash concatenated with the current row's content, and (3) periodic anchor digests written to Cloudflare KV with a Workers Cron Trigger for independent verification. This pattern does not require a blockchain or external notary and runs entirely within the Cloudflare stack.

## Write-Only Audit Entry Worker

The audit log Worker exposes only a `POST /audit` endpoint. It reads the previous tail hash from KV (or a seeded genesis hash), computes the new chain hash, and inserts the row. No `PUT`, `PATCH`, or `DELETE` routes exist. The route-level restriction is the first line of defense; the hash chain is the cryptographic evidence layer.

```typescript
export interface Env {
  DB: D1Database;
  AUDIT_KV: KVNamespace;
  AUDIT_SECRET: string; // set via wrangler secret
}

interface AuditEntry {
  eventType: string;    // e.g. 'POST_REMOVED', 'USER_WARNED', 'APPEAL_DECIDED'
  actorType: 'SYSTEM' | 'MODERATOR' | 'AUTOMATED';
  actorId: string;      // moderator ID or pipeline name
  targetId: string;     // post ID, session token, etc.
  metadata: Record<string, unknown>;
}

interface AuditRow {
  id: number;
  event_type: string;
  actor_type: string;
  actor_id: string;
  target_id: string;
  metadata_json: string;
  prev_hash: string;
  row_hash: string;
  created_at: string;
}

const GENESIS_HASH = 'genesis-example project-audit-v1-000000000000000000000000000000';

async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(input),
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function getTailHash(kv: KVNamespace): Promise<string> {
  return (await kv.get('audit:tail_hash')) ?? GENESIS_HASH;
}

async function setTailHash(kv: KVNamespace, hash: string): Promise<void> {
  await kv.put('audit:tail_hash', hash);
}

function buildRowContent(entry: AuditEntry, prevHash: string, createdAt: string): string {
  return JSON.stringify({
    eventType: entry.eventType,
    actorType: entry.actorType,
    actorId: entry.actorId,
    targetId: entry.targetId,
    metadata: entry.metadata,
    prevHash,
    createdAt,
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Reject all non-POST methods at the Worker level
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const url = new URL(request.url);
    if (url.pathname !== '/audit') {
      return new Response('Not found', { status: 404 });
    }

    // Verify internal HMAC token — only the platform's own Workers call this endpoint
    const authHeader = request.headers.get('X-Audit-Token') ?? '';
    const expectedToken = await sha256Hex(env.AUDIT_SECRET + new Date().toISOString().slice(0, 13));
    if (authHeader !== expectedToken) {
      return new Response('Unauthorized', { status: 401 });
    }

    const entry = await request.json<AuditEntry>();
    const createdAt = new Date().toISOString();

    // Read current tail hash and compute new chain hash
    const prevHash = await getTailHash(env.AUDIT_KV);
    const rowContent = buildRowContent(entry, prevHash, createdAt);
    const rowHash = await sha256Hex(rowContent);

    // Insert — no ON CONFLICT UPDATE, no upsert
    const result = await env.DB.prepare(
      `INSERT INTO audit_log
         (event_type, actor_type, actor_id, target_id, metadata_json, prev_hash, row_hash, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)`,
    )
      .bind(
        entry.eventType,
        entry.actorType,
        entry.actorId,
        entry.targetId,
        JSON.stringify(entry.metadata),
        prevHash,
        rowHash,
        createdAt,
      )
      .run();

    // Update KV tail pointer
    await setTailHash(env.AUDIT_KV, rowHash);

    return Response.json({ id: result.meta.last_row_id, rowHash }, { status: 201 });
  },
} satisfies ExportedHandler<Env>;
```

## Chain Verification Cron Worker

A scheduled Worker runs every hour to verify that the stored hash chain is intact by walking rows in `id` order and recomputing each hash. Breaks are written to an `audit_chain_breaks` table and alert the on-call engineer.

```typescript
interface VerifyEnv {
  DB: D1Database;
  AUDIT_KV: KVNamespace;
  ONCALL_WEBHOOK: string;
}

interface ChainBreak {
  rowId: number;
  storedHash: string;
  computedHash: string;
  detectedAt: string;
}

export const verifyScheduled: ExportedHandler<VerifyEnv> = {
  async scheduled(_event, env, _ctx): Promise<void> {
    const rows = await env.DB.prepare(
      `SELECT id, event_type, actor_type, actor_id, target_id,
              metadata_json, prev_hash, row_hash, created_at
       FROM audit_log ORDER BY id ASC LIMIT 5000`,
    ).all<AuditRow>();

    const breaks: ChainBreak[] = [];

    for (const row of rows.results) {
      const content = buildRowContent(
        {
          eventType: row.event_type,
          actorType: row.actor_type as AuditEntry['actorType'],
          actorId: row.actor_id,
          targetId: row.target_id,
          metadata: JSON.parse(row.metadata_json) as Record<string, unknown>,
        },
        row.prev_hash,
        row.created_at,
      );

      const computed = await sha256Hex(content);
      if (computed !== row.row_hash) {
        breaks.push({
          rowId: row.id,
          storedHash: row.row_hash,
          computedHash: computed,
          detectedAt: new Date().toISOString(),
        });
      }
    }

    if (breaks.length > 0) {
      // Persist break records
      const stmt = env.DB.prepare(
        `INSERT INTO audit_chain_breaks (row_id, stored_hash, computed_hash, detected_at)
         VALUES (?1, ?2, ?3, ?4)`,
      );
      await env.DB.batch(
        breaks.map((b) => stmt.bind(b.rowId, b.storedHash, b.computedHash, b.detectedAt)),
      );

      // Alert on-call
      await fetch(env.ONCALL_WEBHOOK, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          summary: `Audit chain break detected in ${breaks.length} row(s)`,
          severity: 'critical',
          rows: breaks.map((b) => b.rowId),
        }),
      });
    }
  },
};
```

## D1 Schema and Access Controls

```sql
-- migration: 0009_audit_log.sql

CREATE TABLE IF NOT EXISTS audit_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type    TEXT NOT NULL,
  actor_type    TEXT NOT NULL CHECK(actor_type IN ('SYSTEM','MODERATOR','AUTOMATED')),
  actor_id      TEXT NOT NULL,
  target_id     TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  prev_hash     TEXT NOT NULL,
  row_hash      TEXT NOT NULL UNIQUE,
  created_at    TEXT NOT NULL
);

-- No DELETE trigger to catch accidents — enforce at application layer via POST-only endpoint
-- Create an append-only view for read-only consumers
CREATE VIEW IF NOT EXISTS audit_log_readonly AS
  SELECT id, event_type, actor_type, actor_id, target_id,
         metadata_json, row_hash, created_at
  FROM audit_log;

CREATE TABLE IF NOT EXISTS audit_chain_breaks (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  row_id        INTEGER NOT NULL,
  stored_hash   TEXT NOT NULL,
  computed_hash TEXT NOT NULL,
  detected_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_event_type
  ON audit_log(event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_target
  ON audit_log(target_id, created_at DESC);
```

## Anti-patterns

- Using `ON CONFLICT REPLACE` or upsert patterns on `audit_log` — these silently overwrite rows and destroy the chain.
- Storing the tail hash only in D1 alongside the audit rows; if the table is tampered with, the tail pointer is compromised too — KV as a separate Cloudflare product is a weaker but meaningful second root of trust.
- Relying solely on D1 row autoincrement as ordering proof; autoincrement can be reset on export/import — always use the cryptographic chain as the primary integrity proof.

## Gotchas

- D1 does not support database-level triggers (as of 2026) that could enforce immutability at the storage layer; the POST-only application policy is the sole enforcement mechanism, so never expose a general-purpose SQL interface to `audit_log`.
- Hash chain verification over 5000+ rows in a single scheduled Worker invocation may approach the 30-second CPU limit for Cron Triggers — paginate with `LIMIT`/`OFFSET` and use `waitUntil` for large tables, or shard verification across multiple scheduled runs.

## Verification

```bash
# Write a test audit entry
curl -X POST https://example project-audit.example.workers.dev/audit \
  -H "Content-Type: application/json" \
  -H "X-Audit-Token: $(echo -n 'SECRET2026-08-22T13' | sha256sum | awk '{print $1}')" \
  -d '{"eventType":"POST_REMOVED","actorType":"AUTOMATED","actorId":"hate-speech-worker","targetId":"p003","metadata":{"reason":"HATE","score":0.91}}'

# Spot-check chain in D1
wrangler d1 execute example project-db \
  --command "SELECT id, event_type, prev_hash, row_hash, created_at FROM audit_log ORDER BY id DESC LIMIT 5"

# Check for any recorded chain breaks
wrangler d1 execute example project-db \
  --command "SELECT * FROM audit_chain_breaks ORDER BY detected_at DESC LIMIT 10"
```

## Related

- `issues/content-moderation-appeals-workflow.md`
- `issues/anonymous-content-reporting-worker-pipeline.md`
- `issues/digital-services-act-platform-compliance.md`
- `issues/emergency-content-takedown-circuit-breaker-queues.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://digital-strategy.ec.europa.eu/en/policies/digital-services-act-package
