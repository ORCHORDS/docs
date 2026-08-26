# Two-Phase Commit Across D1 and KV

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to write atomically to two stores that do not share a transaction boundary: a D1 (SQLite) database and Workers KV. A simple sequential write leaves the system inconsistent if the Worker is killed between the two writes.

## Context

Two-phase commit (2PC) coordinates a distributed transaction:

1. **Prepare phase** — write an intent record to D1 (the coordinator log). If this fails, abort cleanly.
2. **Commit phase** — apply the KV write. On success, mark the D1 record committed.
3. **Rollback / Recovery** — a scheduled Worker scans stale PREPARE records and either completes or rolls them back.

Because Workers have a 30-second wall-clock limit and KV propagation can take ~60 s, the coordinator must be idempotent and tolerate partial failures.

---

## Section 1 — D1 Coordinator Log Schema

```sql
-- migrations/0001_coordinator_log.sql

CREATE TABLE IF NOT EXISTS coordinator_log (
  txn_id         TEXT PRIMARY KEY,
  phase          TEXT NOT NULL DEFAULT 'PREPARE',
  kv_namespace   TEXT NOT NULL,
  kv_key         TEXT NOT NULL,
  kv_value       TEXT NOT NULL,
  kv_ttl_seconds INTEGER,
  initiated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  committed_at   TEXT,
  rolled_back_at TEXT,
  timeout_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_coordinator_log_phase
  ON coordinator_log (phase, timeout_at);
```

## Section 2 — Prepare Phase

```typescript
// two-phase-commit.ts
export interface Env {
  DB: D1Database;
  CACHE_KV: KVNamespace;
}

const TIMEOUT_SECONDS = 30;

export interface TxnIntent {
  txnId: string;
  kvKey: string;
  kvValue: unknown;
  kvTtlSeconds?: number;
}

export async function preparePhase(
  db: D1Database,
  intent: TxnIntent,
): Promise<{ txnId: string; alreadyPrepared: boolean }> {
  const timeoutAt = new Date(Date.now() + TIMEOUT_SECONDS * 1_000).toISOString();

  const existing = await db
    .prepare('SELECT phase FROM coordinator_log WHERE txn_id = ?')
    .bind(intent.txnId)
    .first<{ phase: string }>();

  if (existing) {
    if (existing.phase !== 'PREPARE') {
      throw new Error(`Transaction ${intent.txnId} is already in phase ${existing.phase}`);
    }
    return { txnId: intent.txnId, alreadyPrepared: true };
  }

  await db
    .prepare(
      `INSERT INTO coordinator_log
         (txn_id, kv_namespace, kv_key, kv_value, kv_ttl_seconds, timeout_at)
       VALUES (?, 'CACHE_KV', ?, ?, ?, ?)`,
    )
    .bind(
      intent.txnId,
      intent.kvKey,
      JSON.stringify(intent.kvValue),
      intent.kvTtlSeconds ?? null,
      timeoutAt,
    )
    .run();

  return { txnId: intent.txnId, alreadyPrepared: false };
}
```

## Section 3 — Commit Phase and Rollback

```typescript
// two-phase-commit.ts (continued)

export async function commitPhase(
  db: D1Database,
  kv: KVNamespace,
  txnId: string,
): Promise<{ committed: boolean; reason?: string }> {
  const row = await db
    .prepare('SELECT * FROM coordinator_log WHERE txn_id = ?')
    .bind(txnId)
    .first<{
      phase: string;
      kv_key: string;
      kv_value: string;
      kv_ttl_seconds: number | null;
      timeout_at: string;
    }>();

  if (!row) return { committed: false, reason: 'txn-not-found' };
  if (row.phase === 'COMMITTED') return { committed: true };
  if (row.phase === 'ROLLED_BACK') return { committed: false, reason: 'rolled-back' };

  if (new Date(row.timeout_at) < new Date()) {
    await rollback(db, txnId, 'timeout');
    return { committed: false, reason: 'timed-out' };
  }

  const putOptions = row.kv_ttl_seconds ? { expirationTtl: row.kv_ttl_seconds } : undefined;
  await kv.put(row.kv_key, row.kv_value, putOptions);

  await db
    .prepare(
      `UPDATE coordinator_log
       SET phase = 'COMMITTED', committed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
       WHERE txn_id = ? AND phase = 'PREPARE'`,
    )
    .bind(txnId)
    .run();

  return { committed: true };
}

export async function rollback(
  db: D1Database,
  txnId: string,
  reason: string,
): Promise<void> {
  await db
    .prepare(
      `UPDATE coordinator_log
       SET phase = 'ROLLED_BACK', rolled_back_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
       WHERE txn_id = ? AND phase = 'PREPARE'`,
    )
    .bind(txnId)
    .run();
  console.warn(`[2PC] rolled back txn ${txnId}: ${reason}`);
}
```

## Section 4 — Recovery Worker (Cron Trigger)

```typescript
// recovery-worker.ts
import { commitPhase, rollback } from './two-phase-commit';

export interface Env {
  DB: D1Database;
  CACHE_KV: KVNamespace;
}

async function runRecovery(env: Env): Promise<number> {
  const now = new Date().toISOString();
  const { results } = await env.DB
    .prepare(
      `SELECT txn_id, timeout_at FROM coordinator_log
       WHERE phase = 'PREPARE'
       ORDER BY timeout_at ASC
       LIMIT 50`,
    )
    .all<{ txn_id: string; timeout_at: string }>();

  let recovered = 0;
  for (const row of results) {
    if (row.timeout_at < now) {
      await rollback(env.DB, row.txn_id, 'recovery-timeout');
      recovered++;
    } else {
      const result = await commitPhase(env.DB, env.CACHE_KV, row.txn_id);
      if (result.committed) recovered++;
    }
  }
  console.log(`[2PC recovery] processed ${results.length}, recovered ${recovered}`);
  return recovered;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runRecovery(env));
  },
  async fetch(_request: Request, env: Env): Promise<Response> {
    return Response.json({ recovered: await runRecovery(env) });
  },
};
```

## Section 5 — Entry-Point Worker

```typescript
// worker.ts
import { preparePhase, commitPhase } from './two-phase-commit';

export interface Env {
  DB: D1Database;
  CACHE_KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST only', { status: 405 });

    const { key, value, ttl } = await request.json<{
      key: string;
      value: unknown;
      ttl?: number;
    }>();

    const txnId = crypto.randomUUID();

    await preparePhase(env.DB, { txnId, kvKey: key, kvValue: value, kvTtlSeconds: ttl });
    const result = await commitPhase(env.DB, env.CACHE_KV, txnId);

    if (!result.committed) {
      return Response.json({ ok: false, txnId, reason: result.reason }, { status: 503 });
    }

    return Response.json({ ok: true, txnId });
  },
};
```

## Anti-patterns

- Writing to KV before D1: if KV succeeds but D1 fails, there is no intent record and the write cannot be undone.
- Not including `timeout_at`: stale PREPARE records accumulate and recovery cannot distinguish in-flight from abandoned.
- Using KV as the coordinator log: KV is eventually consistent and can lose a write before propagation.
- Not making `commitPhase` idempotent: recovery must safely retry commits after a crash between KV write and D1 update.

## Gotchas

- KV writes return before global propagation (~60 s); 2PC ensures eventual correctness, not strong consistency.
- `UPDATE ... WHERE phase = 'PREPARE'` acts as an optimistic lock; two racing recovery Workers will only one succeed.
- Cron Trigger minimum interval is 1 minute; set `TIMEOUT_SECONDS >= 60`.
- `coordinator_log` grows over time; add a cleanup job deleting COMMITTED/ROLLED_BACK records older than 7 days.

## Verification

```bash
# Happy path
curl -s -X POST https://worker.example.com/ \
  -H 'Content-Type: application/json' \
  -d '{"key":"foo","value":{"bar":1},"ttl":3600}' | jq .

# Inspect coordinator log
wrangler d1 execute <DB_NAME> --command \
  "SELECT txn_id, phase, committed_at FROM coordinator_log ORDER BY initiated_at DESC LIMIT 5"

# Verify KV write
wrangler kv key get --namespace-id=<CACHE_KV_ID> foo

# Manual recovery trigger
curl -s https://recovery-worker.example.com/ | jq '{recovered}'
```

## Related

- documentation/categories/patterns/event-sourcing-d1-append-only-log.md
- documentation/categories/patterns/leader-election-durable-objects.md
- documentation/categories/patterns/idempotent-receiver-workers-kv.md

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/platform/triggers/cron-triggers/
- Jim Gray & Andreas Reuter, *Transaction Processing: Concepts and Techniques*, Chapter 12
