# D1 Audit Log Tamper Detection in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your D1 audit log table stores who did what and when. A compromised admin account
or a rogue Worker could silently delete or rewrite rows. You need a way to detect
that the log has been altered without requiring an external write-once store.

## Context

A hash-chained audit log links each row to the hash of the previous row — the same
technique blockchains use. Any deletion, insertion, or modification of an existing row
breaks every hash from that point forward, making tampering evident during a routine
integrity sweep. The chain root can be published externally (e.g. Cloudflare KV or an
email digest) for additional assurance.

---

## Schema: creating the chained table

```sql
CREATE TABLE IF NOT EXISTS audit_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT    NOT NULL,
  actor     TEXT    NOT NULL,
  action    TEXT    NOT NULL,
  target    TEXT    NOT NULL,
  ts        INTEGER NOT NULL,          -- Unix ms, from Date.now()
  payload   TEXT    NOT NULL DEFAULT '{}',
  prev_hash TEXT    NOT NULL DEFAULT '',
  row_hash  TEXT    NOT NULL
);

CREATE INDEX idx_audit_tenant_ts ON audit_log (tenant_id, ts);
```

`prev_hash` is the `row_hash` of the immediately preceding row for the same tenant.
`row_hash` covers all columns except itself.

---

## Computing a row hash

```typescript
async function computeRowHash(
  id: number,
  tenantId: string,
  actor: string,
  action: string,
  target: string,
  ts: number,
  payload: string,
  prevHash: string,
): Promise<string> {
  const canonical = JSON.stringify({ id, tenantId, actor, action, target, ts, payload, prevHash });
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical));
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}
```

All fields are included in the canonical JSON in a deterministic key order to prevent
canonicalization attacks.

---

## Appending a new audit entry

```typescript
export async function appendAuditEntry(
  db: D1Database,
  tenantId: string,
  actor: string,
  action: string,
  target: string,
  payload: Record<string, unknown> = {},
): Promise<void> {
  const ts = Date.now();
  const payloadStr = JSON.stringify(payload);

  // Fetch the most recent row for this tenant (serialized per-tenant chain)
  const prev = await db
    .prepare('SELECT id, row_hash FROM audit_log WHERE tenant_id = ? ORDER BY id DESC LIMIT 1')
    .bind(tenantId)
    .first<{ id: number; row_hash: string }>();

  const prevHash = prev?.row_hash ?? '';

  // Insert with a placeholder to get the autoincrement id, then compute hash
  const ins = await db
    .prepare(
      `INSERT INTO audit_log (tenant_id, actor, action, target, ts, payload, prev_hash, row_hash)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(tenantId, actor, action, target, ts, payloadStr, prevHash, 'pending')
    .run();

  const newId = Number(ins.meta.last_row_id);
  const rowHash = await computeRowHash(
    newId, tenantId, actor, action, target, ts, payloadStr, prevHash,
  );

  await db
    .prepare('UPDATE audit_log SET row_hash = ? WHERE id = ?')
    .bind(rowHash, newId)
    .run();
}
```

---

## Verifying chain integrity

```typescript
export async function verifyAuditChain(
  db: D1Database,
  tenantId: string,
): Promise<{ valid: boolean; brokenAt?: number }> {
  const rows = await db
    .prepare(
      `SELECT id, tenant_id, actor, action, target, ts, payload, prev_hash, row_hash
       FROM audit_log WHERE tenant_id = ? ORDER BY id ASC`,
    )
    .bind(tenantId)
    .all<{
      id: number; tenant_id: string; actor: string; action: string;
      target: string; ts: number; payload: string; prev_hash: string; row_hash: string;
    }>();

  let expectedPrevHash = '';

  for (const row of rows.results) {
    if (row.prev_hash !== expectedPrevHash) {
      return { valid: false, brokenAt: row.id };
    }
    const computed = await computeRowHash(
      row.id, row.tenant_id, row.actor, row.action,
      row.target, row.ts, row.payload, row.prev_hash,
    );
    if (computed !== row.row_hash) {
      return { valid: false, brokenAt: row.id };
    }
    expectedPrevHash = row.row_hash;
  }
  return { valid: true };
}
```

Run this on a schedule (Cron Trigger) and alert on `valid: false`.

---

## Publishing the chain tip to KV for external verification

```typescript
export async function publishChainTip(
  db: D1Database,
  kv: KVNamespace,
  tenantId: string,
): Promise<void> {
  const tip = await db
    .prepare('SELECT id, row_hash FROM audit_log WHERE tenant_id = ? ORDER BY id DESC LIMIT 1')
    .bind(tenantId)
    .first<{ id: number; row_hash: string }>();

  if (!tip) return;

  await kv.put(
    `chain-tip:${tenantId}`,
    JSON.stringify({ id: tip.id, hash: tip.row_hash, publishedAt: Date.now() }),
    { expirationTtl: 60 * 60 * 24 * 90 }, // 90-day retention
  );
}
```

The KV entry acts as an independently verifiable checkpoint. An attacker who can only
write to D1 cannot retroactively alter the KV tip.

---

## Anti-patterns

- **Hashing only `id` and `ts`**: trivially replayable; all mutable columns must be in the hash.
- **Using `Math.random()` or `Date.now()` as the `prev_hash` seed**: destroys chain verifiability; the genesis row's `prev_hash` must be an empty string or a documented constant.
- **Updating rows after insert**: breaks the hash of every subsequent row. Audit logs must be append-only; use a separate `corrections` table if a business event must be annotated.
- **Skipping per-tenant chain isolation**: a cross-tenant hash chain lets one tenant's log growth affect another tenant's chain position.

## Gotchas

- D1 `AUTOINCREMENT` guarantees monotone ids within a database but D1 is eventually consistent in read paths — always read `prev_hash` in the same Worker that writes, or use Durable Objects for strict serialization in high-throughput scenarios.
- SHA-256 is synchronous in most runtimes but is `async` in the Workers Web Crypto API — always `await` it.
- The two-step insert (insert then update) opens a tiny window where `row_hash = 'pending'`. Wrap both statements in a D1 batch (`db.batch([...])`) to reduce that window; note D1 batches are not ACID transactions across writes in all D1 tiers.

## Verification

```bash
# Count rows where prev_hash does not match the prior row_hash
wrangler d1 execute <DB_NAME> --command \
  "SELECT COUNT(*) FROM audit_log a
   JOIN audit_log b ON b.id = a.id - 1 AND b.tenant_id = a.tenant_id
   WHERE a.prev_hash != b.row_hash"
```

A count > 0 indicates at least one break in the chain.

## Related

- `workers-audit-log-immutable-r2-worm-pattern.md`
- `audit-log-security.md`
- `d1-atomic-transactions-toctou-prevention.md`
- `d1-row-level-security-tenant-isolation.md`

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- NIST SP 800-92 Guide to Computer Security Log Management
- Web Crypto API SHA-256 — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
