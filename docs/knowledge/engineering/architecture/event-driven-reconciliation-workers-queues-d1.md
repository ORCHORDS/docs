# Event-Driven Reconciliation — Workers, Queues, and D1

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your system has drifted: the D1 database says an order is "pending" but the
payment provider marked it "paid" three hours ago. Webhooks were missed, a
Worker crashed mid-processing, or an at-least-once message was not retried.
You need a background reconciliation loop that detects drift and emits
corrective events — without polling every row on every tick.

---

## Context

**Reconciliation** is the process of comparing the expected state (your local
record) against an external or computed truth, then issuing compensating
commands to close the gap. In a Cloudflare Workers environment:

- A **scheduled Worker** scans D1 for records in "limbo" states (pending >
  threshold, processing > timeout, etc.)
- It enqueues corrective events to a **Cloudflare Queue**
- A **consumer Worker** processes each corrective event and updates D1 or
  calls external APIs

This separates detection (periodic, cheap) from correction (event-driven,
retryable), prevents thundering-herd corrections, and gives you a complete
audit trail.

```
Cron (1 min)
    │
    ▼
Reconciler Worker
    │  SELECT stale rows
    ▼
D1 (state store)
    │  enqueue ReconcileNeeded events
    ▼
Cloudflare Queue
    │
    ▼
Corrector Worker
    │  call external API / update D1
    ▼
D1 (corrected state) + Audit log
```

---

## Detecting Drift — Limbo State Query

```typescript
interface Env {
  DB: D1Database;
  RECONCILE_QUEUE: Queue<ReconcileEvent>;
}

interface ReconcileEvent {
  type: "OrderPaymentReconcile" | "SubscriptionStatusReconcile";
  recordId: string;
  currentState: string;
  staleSinceIso: string;
}

const STALE_THRESHOLDS: Record<string, number> = {
  pending_payment: 15 * 60 * 1000,   // 15 min
  processing:      10 * 60 * 1000,   // 10 min
  awaiting_webhook: 5 * 60 * 1000,   // 5 min
};

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const now = Date.now();
    const batch: ReconcileEvent[] = [];

    for (const [state, maxAgeMs] of Object.entries(STALE_THRESHOLDS)) {
      const cutoff = new Date(now - maxAgeMs).toISOString();

      const { results } = await env.DB
        .prepare(
          `SELECT id, status, updated_at
             FROM orders
            WHERE status = ?
              AND updated_at < ?
            LIMIT 100`
        )
        .bind(state, cutoff)
        .all<{ id: string; status: string; updated_at: string }>();

      for (const row of results) {
        batch.push({
          type: "OrderPaymentReconcile",
          recordId: row.id,
          currentState: row.status,
          staleSinceIso: row.updated_at,
        });
      }
    }

    if (batch.length === 0) return;

    // Send in Queue batches of 10
    for (let i = 0; i < batch.length; i += 10) {
      await env.RECONCILE_QUEUE.sendBatch(
        batch.slice(i, i + 10).map((msg) => ({ body: msg }))
      );
    }

    console.log(`Enqueued ${batch.length} reconciliation events`);
  },
};
```

---

## Corrector Worker — Processing Reconcile Events

```typescript
import type { MessageBatch, Message } from "@cloudflare/workers-types";

interface CorrectorEnv {
  DB: D1Database;
  PAYMENT_API_KEY: string;
}

export default {
  async queue(
    batch: MessageBatch<ReconcileEvent>,
    env: CorrectorEnv
  ): Promise<void> {
    for (const message of batch.messages) {
      const { success, retry } = await reconcileOrder(message.body, env);
      if (success) {
        message.ack();
      } else if (retry) {
        message.retry({ delaySeconds: 60 });
      } else {
        message.ack(); // permanent failure — already logged to audit
      }
    }
  },
};

interface ReconcileOutcome {
  success: boolean;
  retry: boolean;
}

async function reconcileOrder(
  event: ReconcileEvent,
  env: CorrectorEnv
): Promise<ReconcileOutcome> {
  // 1. Re-read current state — may have been corrected by another path
  const row = await env.DB
    .prepare("SELECT status FROM orders WHERE id = ?")
    .bind(event.recordId)
    .first<{ status: string }>();

  if (!row || row.status !== event.currentState) {
    // State changed between detection and correction — no-op
    await writeAuditLog(env.DB, event, "skipped", "state_already_changed");
    return { success: true, retry: false };
  }

  // 2. Query external source of truth
  let externalStatus: string;
  try {
    externalStatus = await fetchPaymentStatus(event.recordId, env.PAYMENT_API_KEY);
  } catch (err) {
    await writeAuditLog(env.DB, event, "error", String(err));
    return { success: false, retry: true };
  }

  // 3. Apply correction if drift confirmed
  const correctedState = mapPaymentStatus(externalStatus);
  if (correctedState === event.currentState) {
    // No drift — external agrees, refresh updated_at to reset stale timer
    await env.DB
      .prepare("UPDATE orders SET updated_at = ? WHERE id = ?")
      .bind(new Date().toISOString(), event.recordId)
      .run();
    await writeAuditLog(env.DB, event, "no_drift", externalStatus);
    return { success: true, retry: false };
  }

  // Drift detected: apply correction
  await env.DB
    .prepare("UPDATE orders SET status = ?, updated_at = ? WHERE id = ? AND status = ?")
    .bind(correctedState, new Date().toISOString(), event.recordId, event.currentState)
    .run();
  await writeAuditLog(env.DB, event, "corrected", `${event.currentState} → ${correctedState}`);
  return { success: true, retry: false };
}

function mapPaymentStatus(external: string): string {
  const map: Record<string, string> = {
    succeeded: "paid",
    failed: "payment_failed",
    pending: "pending_payment",
    canceled: "cancelled",
  };
  return map[external] ?? "unknown";
}

async function fetchPaymentStatus(
  orderId: string,
  apiKey: string
): Promise<string> {
  const response = await fetch(
    `https://api.stripe.com/v1/payment_intents?metadata[order_id]=${orderId}`,
    { headers: { Authorization: `Bearer ${apiKey}` } }
  );
  if (!response.ok) throw new Error(`Payment API ${response.status}`);
  const data = await response.json<{ data: Array<{ status: string }> }>();
  return data.data[0]?.status ?? "pending";
}
```

---

## Audit Log — Immutable Reconciliation Trail

```typescript
interface AuditEntry {
  id?: number;
  record_id: string;
  event_type: string;
  outcome: string;
  detail: string;
  created_at: string;
}

async function writeAuditLog(
  db: D1Database,
  event: ReconcileEvent,
  outcome: string,
  detail: string
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO reconciliation_audit
         (record_id, event_type, outcome, detail, created_at)
       VALUES (?, ?, ?, ?, ?)`
    )
    .bind(
      event.recordId,
      event.type,
      outcome,
      detail,
      new Date().toISOString()
    )
    .run();
}
```

---

## Idempotency Guard — Preventing Double-Correction

Use a `reconcile_lock` table to prevent two Workers from simultaneously
correcting the same record:

```typescript
async function tryLockForReconciliation(
  db: D1Database,
  recordId: string,
  ttlSeconds = 120
): Promise<boolean> {
  const expires = new Date(Date.now() + ttlSeconds * 1000).toISOString();
  const result = await db
    .prepare(
      `INSERT OR IGNORE INTO reconcile_lock (record_id, expires_at)
       VALUES (?, ?)
       ON CONFLICT(record_id) DO UPDATE SET expires_at = ?
         WHERE expires_at < datetime('now')`
    )
    .bind(recordId, expires, expires)
    .run();
  return result.meta.changes === 1;
}
```

---

## Anti-patterns

- **Reconciling all records every cycle**: Scan only records in limbo states
  past a threshold. Full-table reconciliation causes unnecessary API calls and
  write amplification.
- **Correcting without re-reading current state**: State may have been fixed
  between detection and correction; always recheck before applying updates.
- **Infinite retry on external API 404**: A missing payment record means the
  order was never charged — map to a terminal state, not a retry loop.
- **Writing corrections without audit entries**: Reconciliation changes are
  invisible without an immutable log, making debugging near-impossible.

---

## Gotchas

- Queue `retry()` with a `delaySeconds` backs off from transient payment API
  failures; without delay, the corrector floods the external API.
- D1's serialised writes mean the limbo scan and correction both complete
  atomically per row, but the scan itself is eventually consistent across
  D1 replicas — run the cron only from one location to avoid duplicate events.
- `ON CONFLICT … DO UPDATE WHERE` is SQLite 3.39+ syntax; D1 supports it as
  of 2024, but verify the version in your environment.
- Set `maxRetries` on the Queue consumer; unresolvable records (external API
  permanently down) must eventually be acked to avoid poison-pill loops.

---

## Verification

```bash
# Inspect limbo orders
wrangler d1 execute <DB_NAME> \
  --command "SELECT id, status, updated_at FROM orders
             WHERE status = 'pending_payment'
               AND updated_at < datetime('now', '-15 minutes')"

# Check audit log for recent corrections
wrangler d1 execute <DB_NAME> \
  --command "SELECT * FROM reconciliation_audit
             ORDER BY created_at DESC LIMIT 20"

# Manually trigger reconciliation (if exposed)
curl -X POST https://api.example.com/admin/reconcile/run \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Drain queue metrics
wrangler queues consumer get reconcile-queue
```

---

## Related

- `outbox-pattern.md`
- `change-data-capture-d1-queues.md`
- `saga-pattern-orchestration.md`
- `dead-letter-queue-architecture.md`
- `at-least-once-delivery.md`

---

## Sources

- Cloudflare Queues documentation — Consumer retry and delay
- Cloudflare D1 documentation — Batch API and transactions
- Gregor Hohpe & Bobby Woolf — Enterprise Integration Patterns (2003)
- AWS Well-Architected — Reliability Pillar, Reconciliation patterns
