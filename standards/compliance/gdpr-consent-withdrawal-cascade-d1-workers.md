# GDPR Consent Withdrawal Cascade — D1 + Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A user clicks "Withdraw All Consent" in your preference centre. Under GDPR Article 7(3) processing must stop "without delay," but your data sits across multiple D1 tables (profiles, analytics_events, marketing_segments, third_party_sync). A naive single-table DELETE leaves orphan rows still flowing to downstream processors, triggering Article 17 erasure risk and processor liability under Article 28.

## Context

Cloudflare D1 supports multi-statement batch transactions via `db.batch()`. A consent withdrawal must: (1) mark the consent record revoked, (2) halt future processing flags, (3) cascade-pseudonymise or delete all derivative tables atomically, and (4) enqueue a downstream processor notification via Queues. The entire flow must complete within a single Worker invocation or be reliably retried via Durable Objects.

---

## 1. Consent Record Schema

```sql
-- migrations/0001_consent.sql
CREATE TABLE consent_records (
  user_id      TEXT NOT NULL,
  purpose_id   TEXT NOT NULL,
  granted_at   INTEGER,
  withdrawn_at INTEGER,
  status       TEXT CHECK(status IN ('granted','withdrawn','expired')) NOT NULL,
  PRIMARY KEY (user_id, purpose_id)
);

CREATE TABLE marketing_segments (
  user_id   TEXT NOT NULL,
  segment   TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE analytics_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    TEXT NOT NULL,
  event_name TEXT NOT NULL,
  recorded_at INTEGER NOT NULL
);

CREATE INDEX idx_analytics_user ON analytics_events(user_id);
CREATE INDEX idx_segments_user  ON marketing_segments(user_id);
```

## 2. Cascade Withdrawal Handler

```typescript
// src/handlers/consentWithdraw.ts
import type { Env } from '../types';

export async function handleConsentWithdrawal(
  userId: string,
  purposes: string[],
  env: Env,
): Promise<Response> {
  const now = Math.floor(Date.now() / 1000);
  const pseudoId = `ANON_${crypto.randomUUID()}`;

  const statements = [
    // 1. Revoke each purpose
    ...purposes.map((p) =>
      env.DB.prepare(
        `UPDATE consent_records
         SET status = 'withdrawn', withdrawn_at = ?
         WHERE user_id = ? AND purpose_id = ?`,
      ).bind(now, userId, p),
    ),

    // 2. Pseudonymise analytics (retain aggregate value, remove identity)
    env.DB.prepare(
      `UPDATE analytics_events SET user_id = ? WHERE user_id = ?`,
    ).bind(pseudoId, userId),

    // 3. Delete marketing segments (no legitimate interest override)
    env.DB.prepare(
      `DELETE FROM marketing_segments WHERE user_id = ?`,
    ).bind(userId),

    // 4. Audit trail — append-only, never modified
    env.DB.prepare(
      `INSERT INTO consent_audit (user_id, action, purposes, ts)
       VALUES (?, 'withdrawal_cascade', ?, ?)`,
    ).bind(userId, JSON.stringify(purposes), now),
  ];

  await env.DB.batch(statements);

  // 5. Notify downstream processors via Queue
  await env.CONSENT_QUEUE.send({
    type: 'CONSENT_WITHDRAWN',
    userId,
    pseudoId,
    purposes,
    withdrawnAt: now,
  });

  return new Response(JSON.stringify({ ok: true, pseudoId }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## 3. Durable Object Retry Guard

```typescript
// src/do/ConsentCascadeDO.ts
export class ConsentCascadeDO implements DurableObject {
  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(req: Request): Promise<Response> {
    const { userId, purposes } = await req.json<{
      userId: string;
      purposes: string[];
    }>();

    const key = `cascade:${userId}`;
    const done = await this.state.storage.get<boolean>(key);
    if (done) {
      return new Response(JSON.stringify({ ok: true, cached: true }), {
        status: 200,
      });
    }

    const res = await handleConsentWithdrawal(userId, purposes, this.env);
    if (res.ok) {
      await this.state.storage.put(key, true);
    }
    return res;
  }
}
```

## 4. Queue Consumer — Third-party Processor Notification

```typescript
// src/queues/consentConsumer.ts
export default {
  async queue(batch: MessageBatch<ConsentWithdrawnMsg>, env: Env) {
    for (const msg of batch.messages) {
      const { userId, purposes, withdrawnAt } = msg.body;
      // Call each processor's deletion API
      await Promise.allSettled(
        purposes.map((p) =>
          fetch(`https://processor.example.com/gdpr/withdraw`, {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${env.PROCESSOR_TOKEN}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ userId, purpose: p, withdrawnAt }),
          }),
        ),
      );
      msg.ack();
    }
  },
};
```

## 5. wrangler.toml Bindings

```toml
[[d1_databases]]
binding     = "DB"
database_name = "app-db"
database_id   = "<your-d1-id>"

[[queues.producers]]
binding    = "CONSENT_QUEUE"
queue      = "consent-events"

[[queues.consumers]]
queue              = "consent-events"
max_batch_size     = 10
max_retries        = 5
dead_letter_queue  = "consent-events-dlq"

[[durable_objects.bindings]]
name       = "CONSENT_CASCADE"
class_name = "ConsentCascadeDO"
```

## 6. Verification Query

```typescript
// Confirm cascade completed
async function verifyWithdrawal(userId: string, env: Env) {
  const [consent, segments, events] = await env.DB.batch([
    env.DB.prepare(
      `SELECT COUNT(*) AS c FROM consent_records
       WHERE user_id = ? AND status = 'withdrawn'`,
    ).bind(userId),
    env.DB.prepare(
      `SELECT COUNT(*) AS c FROM marketing_segments WHERE user_id = ?`,
    ).bind(userId),
    env.DB.prepare(
      `SELECT COUNT(*) AS c FROM analytics_events WHERE user_id = ?`,
    ).bind(userId),
  ]);
  return {
    revokedPurposes: (consent.results[0] as any).c,
    orphanSegments:  (segments.results[0] as any).c, // must be 0
    plainEvents:     (events.results[0] as any).c,   // must be 0
  };
}
```

---

## Anti-patterns

- Running per-table DELETEs in sequential awaits — a mid-flight crash leaves the identity in some tables.
- Soft-deleting with `is_deleted = 1` but keeping PII columns populated — still a GDPR violation.
- Relying on application-level foreign keys instead of D1 batch for atomicity.
- Notifying processors after the response is sent without a Queue — fire-and-forget fetch() calls are silently dropped on Worker eviction.

## Gotchas

- D1 `db.batch()` is a single HTTP round-trip but D1 does **not** support `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` — if the batch itself fails, re-run the entire idempotent batch.
- `crypto.randomUUID()` is available globally in Workers without imports.
- Queue messages are delivered **at-least-once**; the Durable Object dedup guard prevents double-pseudonymisation.
- D1 `INTEGER` stores Unix epoch seconds; JavaScript `Date.now()` returns milliseconds — always divide by 1000.

## Verification

```bash
# Trigger withdrawal
curl -X POST https://your-worker.workers.dev/api/consent/withdraw \
  -H "Authorization: Bearer <token>" \
  -d '{"userId":"u_123","purposes":["marketing","analytics"]}'

# Check audit log
wrangler d1 execute app-db \
  --command "SELECT * FROM consent_audit WHERE user_id='u_123';"

# Confirm no orphan segments
wrangler d1 execute app-db \
  --command "SELECT COUNT(*) FROM marketing_segments WHERE user_id='u_123';"
# => 0
```

## Related

- `gdpr-consent-management-cloudflare-workers.md`
- `gdpr-lawful-basis-workers-d1-consent.md`
- `gdpr-right-to-erasure-d1-r2-pipeline.md`
- `gdpr-article-17-erasure.md`
- `data-minimization-workers-d1-pii-redaction.md`

## Sources

- GDPR Article 7(3) — right to withdraw consent
- GDPR Article 17 — right to erasure
- GDPR Article 28 — processor obligations
- Cloudflare D1 Batch API docs: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
