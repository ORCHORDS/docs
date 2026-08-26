# Two-Phase Commit Across D1 and R2 in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to atomically record a file upload: write an object to R2 **and** insert its metadata row in D1. If the D1 write succeeds but the R2 `put` fails (or vice versa), the system is left with orphaned rows or orphaned objects. Standard database transactions do not span R2 (an object store) and D1 (a SQL store). You need a coordination protocol to maintain consistency.

---

## Context

True distributed transactions across heterogeneous stores require a coordinator. Classic 2PC uses a coordinator node to achieve:

1. **Prepare phase**: all participants vote yes/no.
2. **Commit phase**: coordinator commits or aborts based on votes.

In Cloudflare Workers, there is no persistent coordinator process — but a **Durable Object** fills that role: it holds durable state across phases, survives Worker restarts, and serialises concurrent requests via its single-threaded actor model.

The protocol is adapted for R2 + D1:
- R2 does not support two-phase writes natively, so we use a **provisional key pattern**: write to a staging prefix first, then rename (copy + delete) on commit.
- D1 supports conditional updates and row-level status flags as the prepare/commit protocol's persistence layer.

---

## Data Model

```sql
-- D1 schema
CREATE TABLE upload_intents (
  id          TEXT PRIMARY KEY,
  r2_staging_key TEXT NOT NULL,   -- e.g. "staging/abc123"
  r2_final_key   TEXT NOT NULL,   -- e.g. "uploads/abc123.pdf"
  file_size   INTEGER,
  content_type TEXT,
  status      TEXT NOT NULL DEFAULT 'PENDING',
  -- 'PENDING' | 'PREPARED' | 'COMMITTED' | 'ABORTED'
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
```

---

## Coordinator Durable Object

```typescript
// coordinator-do/src/index.ts
import { DurableObject } from 'cloudflare:workers';
import { Env } from './types';

type Phase = 'PENDING' | 'PREPARED' | 'COMMITTED' | 'ABORTED';

interface CommitRequest {
  intentId: string;
  r2StagingKey: string;
  r2FinalKey: string;
  fileSize: number;
  contentType: string;
}

export class UploadCoordinatorDO extends DurableObject {
  constructor(state: DurableObjectState, private env: Env) {
    super(state, env);
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/prepare') {
      return this.prepare(await request.json() as CommitRequest);
    }
    if (url.pathname === '/commit') {
      const { intentId } = await request.json() as { intentId: string };
      return this.commit(intentId);
    }
    if (url.pathname === '/abort') {
      const { intentId } = await request.json() as { intentId: string };
      return this.abort(intentId);
    }
    return new Response('Not Found', { status: 404 });
  }

  private async prepare(req: CommitRequest): Promise<Response> {
    // Idempotency: check for existing intent
    const existing = await this.env.DB.prepare(
      'SELECT status FROM upload_intents WHERE id = ?'
    ).bind(req.intentId).first<{ status: Phase }>();

    if (existing?.status === 'COMMITTED') {
      return Response.json({ phase: 'COMMITTED', intentId: req.intentId });
    }
    if (existing?.status === 'ABORTED') {
      return Response.json({ phase: 'ABORTED', intentId: req.intentId }, { status: 409 });
    }

    const now = new Date().toISOString();

    // Verify R2 staging object exists before voting YES
    const r2Meta = await this.env.BUCKET.head(req.r2StagingKey);
    if (!r2Meta) {
      return Response.json({ phase: 'ABORT', reason: 'staging object not found' }, { status: 422 });
    }

    // Write PREPARED status to D1
    await this.env.DB.prepare(`
      INSERT INTO upload_intents (id, r2_staging_key, r2_final_key, file_size, content_type, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, 'PREPARED', ?, ?)
      ON CONFLICT(id) DO UPDATE SET status = 'PREPARED', updated_at = ?
    `).bind(
      req.intentId, req.r2StagingKey, req.r2FinalKey,
      req.fileSize, req.contentType, now, now, now
    ).run();

    return Response.json({ phase: 'PREPARED', intentId: req.intentId });
  }

  private async commit(intentId: string): Promise<Response> {
    const intent = await this.env.DB.prepare(
      'SELECT * FROM upload_intents WHERE id = ?'
    ).bind(intentId).first<{
      status: Phase; r2_staging_key: string; r2_final_key: string;
      file_size: number; content_type: string;
    }>();

    if (!intent) return new Response('Intent not found', { status: 404 });
    if (intent.status === 'COMMITTED') return Response.json({ phase: 'COMMITTED' }); // idempotent
    if (intent.status !== 'PREPARED') {
      return Response.json({ phase: intent.status, error: 'Cannot commit from this state' }, { status: 409 });
    }

    // Phase 2: copy staging → final in R2, then update D1 atomically
    const stagingObj = await this.env.BUCKET.get(intent.r2_staging_key);
    if (!stagingObj) {
      await this.markAborted(intentId);
      return Response.json({ phase: 'ABORTED', reason: 'staging object disappeared' }, { status: 500 });
    }

    // R2 copy (Workers R2 has no native copy; re-stream)
    await this.env.BUCKET.put(intent.r2_final_key, stagingObj.body, {
      httpMetadata: { contentType: intent.content_type },
      customMetadata: { intentId, fileSize: String(intent.file_size) },
    });

    // Commit in D1
    const now = new Date().toISOString();
    await this.env.DB.prepare(
      "UPDATE upload_intents SET status = 'COMMITTED', updated_at = ? WHERE id = ? AND status = 'PREPARED'"
    ).bind(now, intentId).run();

    // Cleanup staging key asynchronously
    await this.env.BUCKET.delete(intent.r2_staging_key);

    return Response.json({ phase: 'COMMITTED', finalKey: intent.r2_final_key });
  }

  private async abort(intentId: string): Promise<Response> {
    await this.markAborted(intentId);
    return Response.json({ phase: 'ABORTED' });
  }

  private async markAborted(intentId: string): Promise<void> {
    const intent = await this.env.DB.prepare(
      'SELECT r2_staging_key FROM upload_intents WHERE id = ?'
    ).bind(intentId).first<{ r2_staging_key: string }>();

    if (intent) {
      await this.env.BUCKET.delete(intent.r2_staging_key);
    }

    await this.env.DB.prepare(
      "UPDATE upload_intents SET status = 'ABORTED', updated_at = ? WHERE id = ?"
    ).bind(new Date().toISOString(), intentId).run();
  }
}
```

---

## Client Worker — Driving the Protocol

```typescript
// upload-worker/src/index.ts
import { Env } from './types';

function getCoordinator(env: Env, intentId: string): DurableObjectStub {
  const id = env.UPLOAD_COORDINATOR.idFromName(intentId);
  return env.UPLOAD_COORDINATOR.get(id);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const intentId = crypto.randomUUID();
    const contentType = request.headers.get('Content-Type') ?? 'application/octet-stream';
    const stagingKey = `staging/${intentId}`;
    const finalKey = `uploads/${intentId}`;

    // Step 1: write to R2 staging
    const body = await request.arrayBuffer();
    await env.BUCKET.put(stagingKey, body, {
      httpMetadata: { contentType },
    });

    const coordinator = getCoordinator(env, intentId);

    // Step 2: Prepare
    const prepareRes = await coordinator.fetch('https://do/prepare', {
      method: 'POST',
      body: JSON.stringify({
        intentId, r2StagingKey: stagingKey, r2FinalKey: finalKey,
        fileSize: body.byteLength, contentType,
      }),
    });

    if (!prepareRes.ok) {
      // Cleanup staging on prepare failure
      await env.BUCKET.delete(stagingKey);
      return new Response('Upload prepare failed', { status: 500 });
    }

    // Step 3: Commit
    const commitRes = await coordinator.fetch('https://do/commit', {
      method: 'POST',
      body: JSON.stringify({ intentId }),
    });

    if (!commitRes.ok) {
      await coordinator.fetch('https://do/abort', {
        method: 'POST',
        body: JSON.stringify({ intentId }),
      });
      return new Response('Upload commit failed', { status: 500 });
    }

    const { finalKey: key } = await commitRes.json() as { finalKey: string };
    return Response.json({ id: intentId, key, status: 'committed' }, { status: 201 });
  },
};
```

---

## Recovery / Reconciliation (Alarm-Based)

```typescript
// coordinator-do/src/index.ts (alarm handler addition)
async alarm(): Promise<void> {
  // Find stale PREPARED intents older than 5 minutes → abort them
  const cutoff = new Date(Date.now() - 5 * 60 * 1000).toISOString();
  const stale = await this.env.DB.prepare(
    "SELECT id FROM upload_intents WHERE status = 'PREPARED' AND updated_at < ?"
  ).bind(cutoff).all<{ id: string }>();

  for (const row of stale.results) {
    await this.abort(row.id);
    console.warn(`[coordinator] Aborted stale intent ${row.id}`);
  }
}
```

---

## Anti-patterns

- **Direct R2 + D1 writes without a coordinator**: writing to both stores in a single handler with no rollback logic results in partial commits on any error.
- **Using D1 transactions to span R2**: D1 `BEGIN`/`COMMIT` has no effect on R2 operations. You cannot include an R2 `put` inside a D1 transaction.
- **Assuming R2 `put` is atomic with D1 `INSERT`**: these are independent stores; the protocol must explicitly handle failure between the two operations.
- **Coordinator DO per upload without TTL**: Durable Object storage is billed per key. Committed or aborted intents should be archived to D1 and purged from DO state.

---

## Gotchas

- R2 has no native copy/rename API (as of 2026). Commit requires streaming the object from staging to final — this counts as an additional read + write operation.
- Durable Objects run in one PoP per ID. Cross-PoP latency to the coordinator adds 20–80 ms for geographically remote clients. Use `idFromName` with consistent hashing if upload volume is high.
- D1 `status = 'PREPARED'` AND `status = 'COMMITTED'` checks in UPDATE are optimistic concurrency guards — always check `.meta.rows_written` to confirm the update applied.
- Alarm handlers fire at most once per scheduled time. If the DO is evicted between prepare and the alarm, the alarm still fires after rehydration because the alarm is stored durably.

---

## Verification

```bash
# Test happy path
curl -X POST https://upload.example.com/ \
  -H 'Content-Type: application/pdf' \
  --data-binary @test.pdf

# Verify D1 row
wrangler d1 execute DB --command "SELECT id, status, r2_final_key FROM upload_intents ORDER BY created_at DESC LIMIT 5"

# Verify R2 final object
wrangler r2 object get uploads/<intentId>

# Simulate failure: delete staging key mid-flight and retry commit
# Should result in ABORTED status in D1 and no orphan in R2
```

---

## Related

- `two-phase-commit-alternatives.md`
- `two-phase-commit-durable-objects-distributed-transaction.md`
- `saga-pattern-orchestration.md`
- `compensating-transaction-workers-saga-rollback.md`
- `durable-objects-workflow-state-machine.md`
- `outbox-pattern-workers-queues-reliable-events.md`

---

## Sources

- Cloudflare R2 API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Durable Objects Alarms — https://developers.cloudflare.com/durable-objects/api/alarms/
- Designing Data-Intensive Applications (2PC chapter) — Martin Kleppmann, O'Reilly 2017
