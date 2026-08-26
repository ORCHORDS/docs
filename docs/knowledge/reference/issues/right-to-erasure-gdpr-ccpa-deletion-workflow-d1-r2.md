# Right-to-Erasure GDPR/CCPA User Deletion Pipeline with D1 and R2

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
When users submit account deletion requests, profile rows are cleared but orphaned R2
objects, CDN-cached copies, Workers AI vector embeddings, and third-party processor
notifications are missed — creating GDPR Article 17 and CCPA § 1798.105 violations.

## Context
GDPR requires erasure "without undue delay" and no later than 30 days; CCPA requires
completion within 45 days (extendable once). An anonymous platform may store data under
pseudonymous IDs — the obligation still applies to any data linkable back to a natural
person. The deletion pipeline must fan out across D1 tables, R2 buckets, KV caches, AI
embedding stores, and must notify all downstream processors (email providers, analytics,
moderation vendors) in writing. D1 tracks the overall deletion job as a state machine;
a Cron Trigger drives each phase to completion within the statutory window.

## D1 Deletion Job Schema and Intake

```sql
-- migrations/0018_erasure_requests.sql
CREATE TABLE erasure_requests (
  id              TEXT PRIMARY KEY,
  user_id         TEXT NOT NULL UNIQUE,
  requested_at    INTEGER NOT NULL DEFAULT (unixepoch()),
  deadline_at     INTEGER NOT NULL,   -- requested_at + 30 days (GDPR)
  phase           TEXT NOT NULL DEFAULT 'received'
    CHECK (phase IN (
      'received','content_deleted','metadata_cleared',
      'embeddings_purged','cache_purged','processors_notified',
      'completed','failed'
    )),
  phase_updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
  completed_at    INTEGER,
  error           TEXT
);

CREATE TABLE erasure_processor_notifications (
  id              TEXT PRIMARY KEY,
  request_id      TEXT NOT NULL REFERENCES erasure_requests(id),
  processor_name  TEXT NOT NULL,
  notified_at     INTEGER,
  ack_at          INTEGER,
  status          TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','sent','acked','failed'))
);

CREATE INDEX idx_erasure_due ON erasure_requests(deadline_at)
  WHERE phase != 'completed' AND phase != 'failed';
```

## Erasure Request Intake Worker

```typescript
// src/handlers/erasure-intake.ts
import type { Env } from '../env';
import { nanoid } from 'nanoid';

export async function handleErasureRequest(req: Request, env: Env): Promise<Response> {
  const userId = req.headers.get('X-User-ID');
  if (!userId) return new Response('Unauthorized', { status: 401 });

  // GDPR Art.17(3) exemptions: check for active legal hold before accepting
  const hold = await env.DB.prepare(
    `SELECT id FROM legal_holds WHERE user_id = ? AND released_at IS NULL LIMIT 1`
  ).bind(userId).first<{ id: string }>();

  if (hold) {
    return Response.json({
      error: 'Erasure request cannot be processed while a legal hold is active.',
      hold_id: hold.id,
    }, { status: 409 });
  }

  const existing = await env.DB.prepare(
    `SELECT id, phase FROM erasure_requests WHERE user_id = ?`
  ).bind(userId).first<{ id: string; phase: string }>();

  if (existing && existing.phase !== 'failed') {
    return Response.json({ request_id: existing.id, phase: existing.phase }, { status: 200 });
  }

  const requestId = nanoid();
  const now       = Math.floor(Date.now() / 1000);
  const deadline  = now + 30 * 86400;  // GDPR: 30 days

  await env.DB.prepare(
    `INSERT INTO erasure_requests (id, user_id, requested_at, deadline_at)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(user_id) DO UPDATE
       SET id = excluded.id, phase = 'received',
           requested_at = excluded.requested_at, deadline_at = excluded.deadline_at,
           error = NULL`
  ).bind(requestId, userId, now, deadline).run();

  // Seed processor notification rows
  const processors = ['sendgrid', 'amplitude', 'hive-moderation', 'thorn-csam'];
  await env.DB.batch(
    processors.map(name =>
      env.DB.prepare(
        `INSERT INTO erasure_processor_notifications (id, request_id, processor_name)
         VALUES (?, ?, ?)`
      ).bind(nanoid(), requestId, name)
    )
  );

  // Trigger immediate first phase via Queue
  await env.ERASURE_QUEUE.send({ requestId, userId, phase: 'content_delete' });

  // Confirm receipt to user
  return Response.json({ request_id: requestId, deadline: deadline }, { status: 202 });
}
```

## Phase 1 and 2 — Content and Metadata Deletion

```typescript
// src/jobs/erasure-phases.ts
import type { Env } from '../env';

export async function deleteUserContent(userId: string, requestId: string, env: Env): Promise<void> {
  // 1a. Enumerate and delete all R2 objects owned by user
  let cursor: string | undefined;
  do {
    const list = await env.CONTENT_BUCKET.list({ prefix: `user/${userId}/`, cursor });
    await Promise.all(list.objects.map(obj => env.CONTENT_BUCKET.delete(obj.key)));
    cursor = list.truncated ? list.cursor : undefined;
  } while (cursor);

  // 1b. Delete ephemeral registry entries (triggers key deletion on next purge cron)
  await env.DB.prepare(
    `UPDATE ephemeral_objects SET deleted_at = unixepoch()
     WHERE id IN (
       SELECT eo.id FROM ephemeral_objects eo
       JOIN posts p ON p.r2_key = eo.r2_key
       WHERE p.user_id = ?
     )`
  ).bind(userId).run();

  // 1c. Hard-delete all D1 post/comment/DM content rows
  const tables = ['posts', 'comments', 'direct_messages', 'reactions', 'poll_votes'] as const;
  await env.DB.batch(
    tables.map(t => env.DB.prepare(`DELETE FROM ${t} WHERE user_id = ?`).bind(userId))
  );

  await advancePhase(requestId, 'content_deleted', env);
}

export async function clearUserMetadata(userId: string, requestId: string, env: Env): Promise<void> {
  // 2a. Nullify profile fields (retain row as tombstone for foreign key integrity)
  await env.DB.prepare(
    `UPDATE users
     SET username = NULL, display_name = NULL, bio = NULL,
         avatar_r2_key = NULL, email_hash = NULL, phone_hash = NULL,
         age_verified = 0, deleted = 1, deleted_at = unixepoch()
     WHERE id = ?`
  ).bind(userId).run();

  // 2b. Clear KV session and cache entries
  const sessionKey = `session:${userId}`;
  await env.SESSION_KV.delete(sessionKey);
  await env.RATE_LIMIT_KV.delete(`rl:${userId}`);

  // 2c. Remove from anonymous reputation store
  await env.REPUTATION_KV.delete(`rep:${userId}`);

  await advancePhase(requestId, 'metadata_cleared', env);
}

async function advancePhase(requestId: string, phase: string, env: Env): Promise<void> {
  await env.DB.prepare(
    `UPDATE erasure_requests SET phase = ?, phase_updated_at = unixepoch() WHERE id = ?`
  ).bind(phase, requestId).run();
}
```

## Phase 3 — Vector Embedding Purge and Processor Notifications

```typescript
// src/jobs/erasure-phase3.ts
export async function purgeEmbeddingsAndNotify(
  userId: string,
  requestId: string,
  env: Env,
): Promise<void> {
  // 3a. Delete user's vectors from Workers AI Vectorize index
  //     Vectorize delete accepts up to 500 IDs per call
  const { results: vectors } = await env.DB.prepare(
    `SELECT vectorize_id FROM content_vectors WHERE user_id = ?`
  ).bind(userId).all<{ vectorize_id: string }>();

  const ids = vectors.map(v => v.vectorize_id);
  for (let i = 0; i < ids.length; i += 500) {
    await env.CONTENT_VECTORS.deleteByIds(ids.slice(i, i + 500));
  }
  await env.DB.prepare(`DELETE FROM content_vectors WHERE user_id = ?`).bind(userId).run();

  await advancePhase(requestId, 'embeddings_purged', env);

  // 3b. Notify downstream processors
  const { results: processors } = await env.DB.prepare(
    `SELECT id, processor_name FROM erasure_processor_notifications
     WHERE request_id = ? AND status = 'pending'`
  ).bind(requestId).all<{ id: string; processor_name: string }>();

  await Promise.allSettled(
    processors.map(async p => {
      try {
        await notifyProcessor(p.processor_name, userId, env);
        await env.DB.prepare(
          `UPDATE erasure_processor_notifications
           SET status = 'sent', notified_at = unixepoch() WHERE id = ?`
        ).bind(p.id).run();
      } catch (err) {
        await env.DB.prepare(
          `UPDATE erasure_processor_notifications SET status = 'failed' WHERE id = ?`
        ).bind(p.id).run();
      }
    })
  );

  await advancePhase(requestId, 'processors_notified', env);
  await env.DB.prepare(
    `UPDATE erasure_requests SET phase = 'completed', completed_at = unixepoch() WHERE id = ?`
  ).bind(requestId).run();
}

async function notifyProcessor(name: string, userId: string, env: Env): Promise<void> {
  const endpoints: Record<string, string> = {
    'sendgrid':       env.SENDGRID_ERASURE_ENDPOINT,
    'amplitude':      env.AMPLITUDE_ERASURE_ENDPOINT,
    'hive-moderation': env.HIVE_ERASURE_ENDPOINT,
    'thorn-csam':     env.THORN_ERASURE_ENDPOINT,
  };
  const url = endpoints[name];
  if (!url) throw new Error(`Unknown processor: ${name}`);

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.PROCESSOR_ERASURE_TOKEN}` },
    body: JSON.stringify({ user_id: userId, requested_at: Math.floor(Date.now() / 1000) }),
  });
  if (!res.ok) throw new Error(`Processor ${name} returned ${res.status}`);
}
```

## Anti-patterns
- Soft-deleting rows and calling it erasure — pseudonymous data linked to a natural person must be genuinely deleted or irreversibly anonymized
- Skipping CDN cache purge — cached profile pages may serve deleted data for hours after deletion
- Treating deletion of the D1 `users` row as complete — orphaned content in R2, KV, and Vectorize remains
- Notifying processors but not verifying their acknowledgment — GDPR requires evidence the processor acted
- Not checking for active legal holds before accepting the erasure request — deletion during a hold can constitute obstruction

## Gotchas
- GDPR "erasure" permits anonymization as an alternative; CCPA uses "delete" which courts have interpreted as genuine deletion — do not assume anonymization satisfies CCPA
- Vectorize `deleteByIds` silently succeeds even if IDs don't exist; verify by attempting a subsequent `getByIds`
- R2 `list()` is eventually consistent — run the listing twice and diff if completeness is critical
- The 30-day GDPR clock runs from receipt of the request, not from identity verification; note this in the UX
- Processor notification failures must trigger alerts; a 45-day CCPA deadline with a failed processor notification is a reportable incident

## Verification

```sql
-- Open erasure requests approaching deadline
SELECT id, user_id,
       datetime(deadline_at, 'unixepoch') AS due,
       phase,
       (deadline_at - unixepoch()) / 86400 AS days_remaining
FROM erasure_requests
WHERE phase NOT IN ('completed', 'failed')
ORDER BY deadline_at;

-- Processor notification status for a specific request
SELECT processor_name, status, datetime(notified_at, 'unixepoch') AS notified
FROM erasure_processor_notifications
WHERE request_id = 'REQUEST_ID_HERE';
```

```bash
# Confirm user's R2 prefix is empty after deletion
wrangler r2 object list CONTENT_BUCKET --prefix "user/<userId>/"
# Expected: empty list
```

## Related
- `gdpr-data-export-worker-r2-signed-url.md` — data portability export that precedes erasure
- `legal-hold-evidence-preservation-d1-r2.md` — hold exemption blocking erasure
- `ephemeral-content-secure-deletion-r2.md` — TTL-based deletion for expiring content
- `platform-audit-log-immutable-d1-workers.md` — audit log rows may be retained under Art.17(3)(b)

## Sources
- https://gdpr-info.eu/art-17-gdpr/
- https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1798.105.&lawCode=CIV
- https://developers.cloudflare.com/vectorize/reference/client-api/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/queues/
