# Emergency Content Takedown: Circuit Breaker Pattern for Mass Removal with Cloudflare Queues

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

A viral post containing CSAM, doxxing, or incitement to violence spreads to thousands of derivative posts within minutes. The standard single-record delete is too slow; a naive mass-delete loop overwhelms D1 write throughput and trips Worker CPU limits. You need a circuit-breaker-backed, queue-fanned mass-removal pipeline that can take down tens of thousands of content items in under five minutes without degrading the live platform.

---

## Context

Emergency takedowns differ from routine moderation in scale and urgency:

- **Scale**: one piece of viral content may spawn 50k+ reposts, replies, and reactions within an hour.
- **Urgency**: NCMEC CyberTipline SLAs require CSAM removal within hours, not days.
- **Blast radius**: a naive `DELETE FROM posts WHERE content_hash = ?` touches every D1 replica simultaneously, causing write latency spikes for normal traffic.
- **Reversibility**: takedowns must be auditable and partially reversible if a false positive is detected mid-sweep.

The pattern: a human moderator triggers a takedown job; a Controller Worker fans the workload onto a Cloudflare Queue; Consumer Workers pull batches and apply deletions with a circuit breaker that pauses delivery if error rates spike.

---

## Section 1: Takedown Job Schema

```sql
-- migration 0041_takedown_jobs.sql
CREATE TABLE IF NOT EXISTS takedown_job (
  job_id       TEXT    NOT NULL PRIMARY KEY,
  triggered_by TEXT    NOT NULL,
  reason_code  TEXT    NOT NULL, -- CSAM | DOXX | INCITEMENT | DMCA | OTHER
  target_type  TEXT    NOT NULL, -- CONTENT_HASH | ACCOUNT | POST_ID | KEYWORD
  target_value TEXT    NOT NULL,
  status       TEXT    NOT NULL DEFAULT 'PENDING',
  -- PENDING | RUNNING | PAUSED | COMPLETED | FAILED
  total_items  INTEGER,
  removed_items INTEGER DEFAULT 0,
  error_count  INTEGER DEFAULT 0,
  started_at   INTEGER,
  finished_at  INTEGER,
  audit_json   TEXT
);

CREATE TABLE IF NOT EXISTS takedown_item (
  job_id     TEXT    NOT NULL,
  item_id    TEXT    NOT NULL,
  item_type  TEXT    NOT NULL, -- POST | COMMENT | MEDIA | REACTION
  status     TEXT    NOT NULL DEFAULT 'QUEUED',
  -- QUEUED | REMOVED | FAILED | SKIPPED
  error_msg  TEXT,
  processed_at INTEGER,
  PRIMARY KEY (job_id, item_id)
);
```

---

## Section 2: Controller Worker — Job Initiation and Fan-Out

```typescript
// src/workers/takedown-controller.ts
import { randomUUID } from 'crypto';
import type { Env, TakedownRequest } from '../types';

const BATCH_SIZE = 500; // Queue message size limit is 128 KB; 500 IDs fits comfortably

export async function initiateTakedown(
  env: Env,
  req: TakedownRequest
): Promise<{ jobId: string; totalItems: number }> {
  const jobId = randomUUID();
  const now   = Date.now();

  // 1. Resolve all matching item IDs from D1
  const { results: items } = await env.DB
    .prepare(resolveQuery(req))
    .bind(req.targetValue)
    .all<{ id: string; type: string }>();

  if (items.length === 0) {
    throw new Error('No items matched takedown target');
  }

  // 2. Insert job record
  await env.DB.prepare(
    `INSERT INTO takedown_job
       (job_id, triggered_by, reason_code, target_type, target_value,
        status, total_items, started_at, audit_json)
     VALUES (?, ?, ?, ?, ?, 'RUNNING', ?, ?, ?)`
  ).bind(
    jobId, req.triggeredBy, req.reasonCode,
    req.targetType, req.targetValue,
    items.length, now, JSON.stringify(req.auditJson ?? {})
  ).run();

  // 3. Seed takedown_item rows in batches (D1 batch limit: 1000 stmts)
  for (let i = 0; i < items.length; i += 1000) {
    const batch = items.slice(i, i + 1000);
    await env.DB.batch(
      batch.map(item =>
        env.DB.prepare(
          `INSERT INTO takedown_item (job_id, item_id, item_type, status)
           VALUES (?, ?, ?, 'QUEUED')`
        ).bind(jobId, item.id, item.type)
      )
    );
  }

  // 4. Fan out work onto the Queue in BATCH_SIZE chunks
  const messages: MessageSendRequest<TakedownBatch>[] = [];
  for (let i = 0; i < items.length; i += BATCH_SIZE) {
    messages.push({
      body: {
        jobId,
        items: items.slice(i, i + BATCH_SIZE).map(it => ({ id: it.id, type: it.type })),
      },
    });
  }

  // sendBatch supports up to 100 messages per call
  for (let i = 0; i < messages.length; i += 100) {
    await env.TAKEDOWN_QUEUE.sendBatch(messages.slice(i, i + 100));
  }

  return { jobId, totalItems: items.length };
}

function resolveQuery(req: TakedownRequest): string {
  switch (req.targetType) {
    case 'CONTENT_HASH':
      return `SELECT id, 'POST' AS type FROM posts WHERE content_hash = ?
              UNION ALL
              SELECT id, 'COMMENT' AS type FROM comments WHERE content_hash = ?`;
    case 'ACCOUNT':
      return `SELECT id, 'POST' AS type FROM posts WHERE author_id = ?
              UNION ALL
              SELECT id, 'COMMENT' AS type FROM comments WHERE author_id = ?`;
    case 'POST_ID':
      return `SELECT ? AS id, 'POST' AS type`;
    default:
      throw new Error(`Unsupported target type: ${req.targetType}`);
  }
}

interface TakedownBatch {
  jobId: string;
  items: Array<{ id: string; type: string }>;
}

interface MessageSendRequest<T> {
  body: T;
}
```

---

## Section 3: Consumer Worker with Circuit Breaker

```typescript
// src/workers/takedown-consumer.ts
import type { Env } from '../types';

interface TakedownBatch {
  jobId: string;
  items: Array<{ id: string; type: string }>;
}

// Circuit breaker state in KV (shared across consumer instances)
const CB_KEY        = 'takedown:circuit_breaker';
const CB_OPEN_TTL   = 120; // seconds the circuit stays open before retrying
const ERROR_THRESHOLD = 0.2; // 20% error rate opens the circuit

export default {
  async queue(batch: MessageBatch<TakedownBatch>, env: Env): Promise<void> {
    const cbState = await env.TAKEDOWN_KV.get(CB_KEY, 'json') as
      { open: boolean; openedAt: number } | null;

    if (cbState?.open) {
      const age = (Date.now() - cbState.openedAt) / 1000;
      if (age < CB_OPEN_TTL) {
        // Circuit open — requeue messages for later delivery
        batch.retryAll();
        return;
      }
      // Half-open: allow one batch through as a probe
      await env.TAKEDOWN_KV.delete(CB_KEY);
    }

    let successCount = 0;
    let errorCount   = 0;

    for (const msg of batch.messages) {
      const { jobId, items } = msg.body;
      try {
        await processItems(env, jobId, items);
        successCount += items.length;
        msg.ack();
      } catch (err) {
        errorCount += items.length;
        msg.retry();
        console.error(`Takedown batch error for job ${jobId}:`, err);
      }
    }

    const total     = successCount + errorCount;
    const errorRate = total > 0 ? errorCount / total : 0;

    if (errorRate >= ERROR_THRESHOLD && total >= 50) {
      await env.TAKEDOWN_KV.put(
        CB_KEY,
        JSON.stringify({ open: true, openedAt: Date.now() }),
        { expirationTtl: CB_OPEN_TTL * 2 }
      );
      console.warn(`Takedown circuit breaker OPENED — error rate ${(errorRate * 100).toFixed(1)}%`);
    }
  },
};

async function processItems(
  env: Env,
  jobId: string,
  items: Array<{ id: string; type: string }>
): Promise<void> {
  const now = Date.now();

  // Soft-delete: mark removed rather than hard-delete to preserve audit trail
  const stmts = items.flatMap(({ id, type }) => {
    const table = type === 'POST' ? 'posts' : type === 'COMMENT' ? 'comments' : null;
    if (!table) return [];
    return [
      env.DB.prepare(
        `UPDATE ${table} SET status = 'TAKEDOWN', taken_down_at = ? WHERE id = ?`
      ).bind(now, id),
      env.DB.prepare(
        `UPDATE takedown_item SET status = 'REMOVED', processed_at = ?
         WHERE job_id = ? AND item_id = ?`
      ).bind(now, jobId, id),
    ];
  });

  await env.DB.batch(stmts);

  // Update running counter on the job record
  await env.DB.prepare(
    `UPDATE takedown_job
     SET removed_items = removed_items + ?
     WHERE job_id = ?`
  ).bind(items.length, jobId).run();
}
```

---

## Section 4: Pause and Resume Controls

Moderators can pause a running job if a false positive is suspected.

```typescript
// src/workers/takedown-controller.ts  (additional endpoints)

export async function pauseTakedown(env: Env, jobId: string): Promise<void> {
  await env.DB.prepare(
    `UPDATE takedown_job SET status = 'PAUSED' WHERE job_id = ? AND status = 'RUNNING'`
  ).bind(jobId).run();

  // Open the circuit breaker so the consumer backs off
  await env.TAKEDOWN_KV.put(
    'takedown:circuit_breaker',
    JSON.stringify({ open: true, openedAt: Date.now() }),
    { expirationTtl: 3600 }
  );
}

export async function resumeTakedown(env: Env, jobId: string): Promise<void> {
  await env.DB.prepare(
    `UPDATE takedown_job SET status = 'RUNNING' WHERE job_id = ? AND status = 'PAUSED'`
  ).bind(jobId).run();

  await env.TAKEDOWN_KV.delete('takedown:circuit_breaker');
}
```

---

## Section 5: R2 Media Purge

Posts removed from D1 still have media objects in R2. A separate async step purges them using the R2 `list` + `delete` API.

```typescript
// src/cib/media-purge.ts
import type { Env } from '../types';

export async function purgeMediaForJob(env: Env, jobId: string): Promise<void> {
  const { results } = await env.DB
    .prepare(
      `SELECT p.media_key
       FROM posts p
       JOIN takedown_item ti ON ti.item_id = p.id
       WHERE ti.job_id = ? AND ti.status = 'REMOVED' AND p.media_key IS NOT NULL`
    )
    .bind(jobId)
    .all<{ media_key: string }>();

  // R2 deleteMultiple supports up to 1000 keys per call
  for (let i = 0; i < results.length; i += 1000) {
    const keys = results.slice(i, i + 1000).map(r => r.media_key);
    await env.MEDIA_BUCKET.delete(keys);
  }

  console.log(`Media purge for job ${jobId}: ${results.length} objects deleted`);
}
```

---

## Section 6: Job Status Dashboard Query

```sql
-- Real-time progress view
SELECT
  job_id,
  reason_code,
  target_type,
  target_value,
  status,
  total_items,
  removed_items,
  error_count,
  ROUND(100.0 * removed_items / NULLIF(total_items, 0), 1) AS pct_complete,
  ROUND((julianday('now') - julianday(datetime(started_at / 1000, 'unixepoch'))) * 86400) AS elapsed_sec
FROM takedown_job
ORDER BY started_at DESC
LIMIT 20;
```

---

## Anti-patterns

- **Synchronous mass DELETE in a single transaction** — D1 write transactions have a 30-second limit; a mass-delete of 50k rows will timeout mid-flight leaving partial state.
- **Hard-deleting without an audit trail** — NCMEC CyberTipline submissions require evidence preservation; soft-delete first, then purge after the legal hold period.
- **A single circuit breaker key shared across all jobs** — one bad job pauses all takedown work. Namespace the circuit breaker key by `job_id` if you run concurrent takedowns.
- **Not acknowledging messages on success** — unacked messages redeliver after the Queue visibility timeout (default 30s), causing duplicate `UPDATE` statements. Always call `msg.ack()` on success.
- **Skipping the fan-out and doing it inline** — a Worker with a 30-second wall-clock limit cannot process 50k items inline; Queue fan-out is mandatory at scale.

---

## Gotchas

- Cloudflare Queues batch consumer receives up to 100 messages per invocation by default; configure `max_batch_size: 100` and `max_batch_timeout: 5` in `wrangler.toml`.
- D1 `batch()` is limited to 1000 statements. Chunk your item lists before batching.
- `env.MEDIA_BUCKET.delete(keys)` with an array argument requires Workers runtime v3+. Verify with `wrangler --version`.
- The circuit breaker KV state is eventually consistent across edge caches. In a 2–5 second window after opening, some consumers may still process batches. This is acceptable; the breaker is a throttle, not a hard stop.
- R2 `delete` is idempotent — deleting a key that does not exist returns no error.

---

## Verification

```bash
# 1. Trigger a test takedown on a known test post
curl -X POST https://api.example.com/internal/moderation/takedown \
  -H "Authorization: Bearer $MOD_TOKEN" \
  -d '{"targetType":"POST_ID","targetValue":"test-post-001","reasonCode":"OTHER"}'

# 2. Monitor job progress
wrangler d1 execute example project-db --command \
  "SELECT job_id, status, total_items, removed_items FROM takedown_job ORDER BY started_at DESC LIMIT 5"

# 3. Verify consumer queue depth drops
wrangler queues consumer --queue takedown-queue --tail

# 4. Confirm media object removed from R2
wrangler r2 object get media-bucket test-post-001/image.jpg  # should 404
```

---

## Related

- `copyright-dmca-takedown-worker-pipeline.md`
- `877-csam-vendor-integration.md`
- `content-moderation-appeals-workflow.md`
- `emergency-content-takedown-circuit-breaker-queues.md`
- `anonymous-content-reporting-worker-pipeline.md`

---

## Sources

- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Cloudflare D1 batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Netflix Circuit Breaker pattern (Hystrix) — https://github.com/Netflix/Hystrix/wiki
- NCMEC CyberTipline — https://www.missingkids.org/gethelpnow/cybertipline
- DSA Article 17 (Content Moderation Obligations) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
