# Workers Queues Dead-Letter Queue Deploy Configuration

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Queues consumer Worker starts throwing errors after a deploy — bad schema, unreachable binding, logic regression. Without a dead-letter queue (DLQ), the same poisoned messages retry indefinitely, block healthy messages from processing, and exhaust the retry budget silently. By the time you notice, the queue is thousands of messages deep. A correctly deployed DLQ topology catches poison messages, routes them to a safe holding queue, and lets the main pipeline continue — while giving you a recovery path to replay or inspect failures.

## Context

Cloudflare Queues (2024+) support a `dead_letter_queue` field on each consumer binding. When a message exhausts all retries (`max_retries` attempts), it is automatically moved to the named DLQ. The DLQ is itself a standard Cloudflare Queue and can have its own consumer. Because the DLQ must exist before the primary queue's consumer is deployed, DLQ provisioning must happen earlier in the CI pipeline than the Worker deploy step.

---

## 1. DLQ Topology Design

A minimal example project pattern uses two queues per logical pipeline:

```
Producer → [main-queue] → consumer Worker → success
                       ↓ (max_retries exhausted)
                 [main-queue-dlq] → DLQ inspector Worker (optional)
```

For high-volume pipelines, add a DLQ consumer that writes failures to R2 for offline analysis:

```
[main-queue-dlq] → dlq-archiver Worker → R2 bucket (failures/)
```

---

## 2. Provision Queues in Dependency Order

```bash
#!/usr/bin/env bash
set -euo pipefail

ENV="${1:-staging}"  # staging | production

MAIN_QUEUE="example project-jobs-${ENV}"
DLQ="example project-jobs-dlq-${ENV}"

# DLQ must exist FIRST — wrangler deploy will fail if the DLQ name doesn't resolve
wrangler queues create "$DLQ"   2>/dev/null || echo "DLQ $DLQ already exists"
wrangler queues create "$MAIN_QUEUE" 2>/dev/null || echo "Queue $MAIN_QUEUE already exists"

echo "Queues provisioned: $MAIN_QUEUE → DLQ: $DLQ"
```

---

## 3. wrangler.toml with DLQ Binding

```toml
name = "example project-job-consumer"
main = "src/consumer.ts"
compatibility_date = "2025-09-01"

# ── Staging ────────────────────────────────────────────────────────────────
[env.staging]
[[env.staging.queues.consumers]]
queue             = "example project-jobs-staging"
max_batch_size    = 5
max_batch_timeout = 10
max_retries       = 2                        # fewer retries in staging for faster feedback
dead_letter_queue = "example project-jobs-dlq-staging"

# ── Production ─────────────────────────────────────────────────────────────
[env.production]
[[env.production.queues.consumers]]
queue             = "example project-jobs-production"
max_batch_size    = 25
max_batch_timeout = 30
max_retries       = 5
dead_letter_queue = "example project-jobs-dlq-production"
```

---

## 4. Consumer Worker with Explicit Error Classification

Distinguish transient errors (should retry) from permanent errors (should DLQ immediately via `msg.retry({ delaySeconds: 0, maxRetries: 0 })`):

```typescript
export interface Env {
  /* no extra bindings needed for DLQ routing — it's automatic */
}

interface Job {
  type: string;
  payload: Record<string, unknown>;
  schemaVersion: number;
}

const CURRENT_SCHEMA_VERSION = 3;

export default {
  async queue(batch: MessageBatch<Job>, _env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;

      // Permanent failure: schema mismatch — send straight to DLQ
      if (job.schemaVersion !== CURRENT_SCHEMA_VERSION) {
        console.error(
          `Schema mismatch: expected v${CURRENT_SCHEMA_VERSION}, got v${job.schemaVersion}. Sending to DLQ.`
        );
        // Exhaust retries immediately by setting retry to 0 remaining
        msg.retry({ delaySeconds: 0 });
        // Note: Cloudflare doesn't support "skip to DLQ immediately" today;
        // the approach is to throw after marking this as the last retry attempt.
        // Until direct DLQ send lands, increment a KV counter and ack on threshold.
        continue;
      }

      try {
        await processJob(job);
        msg.ack();
      } catch (err) {
        const isTransient = isTransientError(err);
        if (isTransient) {
          console.warn(`Transient error for job ${job.type}, will retry:`, err);
          msg.retry({ delaySeconds: 10 });
        } else {
          console.error(`Permanent error for job ${job.type}, exhausting retries:`, err);
          // retry without delay so max_retries is hit quickly
          msg.retry({ delaySeconds: 0 });
        }
      }
    }
  },
};

function isTransientError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  return (
    err.message.includes("network") ||
    err.message.includes("timeout") ||
    err.message.includes("503")
  );
}

async function processJob(job: Job): Promise<void> {
  // business logic here
  console.log(`Processing ${job.type}`, job.payload);
}
```

---

## 5. DLQ Inspector Worker (Optional but Recommended)

Deploy a lightweight consumer on the DLQ that archives failures to R2 and emits an alert:

```typescript
// src/dlq-inspector.ts
export interface Env {
  FAILURES: R2Bucket;
  ALERT_QUEUE: Queue;
}

export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    const timestamp = new Date().toISOString().slice(0, 10);

    for (const msg of batch.messages) {
      const key = `failures/${timestamp}/${msg.id}.json`;
      const body = JSON.stringify({
        id: msg.id,
        timestamp: msg.timestamp,
        attempts: msg.attempts,
        body: msg.body,
      });

      await env.FAILURES.put(key, body, {
        httpMetadata: { contentType: "application/json" },
        customMetadata: { source: "dlq", attempts: String(msg.attempts) },
      });

      msg.ack();
    }

    // Alert if batch is non-empty
    if (batch.messages.length > 0) {
      await env.ALERT_QUEUE.send({
        dlq: batch.queue,
        count: batch.messages.length,
        timestamp: new Date().toISOString(),
      });
    }
  },
};
```

---

## 6. CI Gate: Verify DLQ Depth Post-Deploy

Run this check 2 minutes after deploy to catch immediate consumer failures:

```bash
#!/usr/bin/env bash
set -euo pipefail

DLQ_NAME="example project-jobs-dlq-${DEPLOY_ENV}"
MAX_ALLOWED=0

echo "Waiting 120s for initial consumer run..."
sleep 120

DEPTH=$(wrangler queues info "$DLQ_NAME" --json 2>/dev/null | jq -r '.messages_ready // 0')

echo "DLQ depth after deploy: $DEPTH"
if [ "$DEPTH" -gt "$MAX_ALLOWED" ]; then
  echo "ERROR: DLQ has $DEPTH messages — deploy likely introduced a regression."
  echo "Rolling back..."
  wrangler rollback --env "$DEPLOY_ENV"
  exit 1
fi

echo "DLQ gate passed."
```

---

## Anti-patterns

- Deploying the consumer Worker before the DLQ queue exists — Wrangler accepts the `wrangler.toml` but the runtime binding is broken; messages that exhaust retries are silently dropped.
- Setting `max_retries = 0` in production — every transient network hiccup immediately DLQs the message.
- Not deploying a DLQ consumer — messages accumulate indefinitely; there is a per-account queue storage quota.
- Sharing a DLQ between multiple main queues — complicates triage and replay because messages from different pipelines are interleaved.

## Gotchas

- The DLQ `queue` name in `wrangler.toml` must match the queue name exactly (case-sensitive). A mismatch causes a deploy error, not a runtime error.
- DLQ messages retain the original message body but lose custom metadata added by the producer; store metadata inside the message body itself if you need it during DLQ inspection.
- Cloudflare Queues does not yet support "send directly to DLQ" — the only path to the DLQ is exhausting `max_retries`. For immediate routing, use a KV-backed attempt counter and `msg.ack()` after threshold.
- Queue storage quota is shared across all queues in the account. Large DLQ backlogs count against this quota and can block new message ingestion on *other* queues.

## Verification

```bash
# Confirm DLQ exists and is empty pre-deploy
wrangler queues info example project-jobs-dlq-production --json | jq '{name,messages_ready,messages_delayed}'

# Send a synthetic poison message and verify it lands in DLQ after max_retries
wrangler queues send example project-jobs-production \
  --message '{"type":"test","payload":{},"schemaVersion":0}' \
  --env production

# Wait for retries to exhaust (max_retries * delay), then check DLQ
sleep 60
wrangler queues info example project-jobs-dlq-production --json | jq '.messages_ready'
```

## Related

- `workers-queues-consumer-worker-deployment.md`
- `workers-r2-event-notification-trigger-deploy.md`
- `deployment-health-gates-automated-rollback.md`
- `rollback-runbook.md`
- `deploy-gate-antipatterns.md`

## Sources

- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- https://developers.cloudflare.com/queues/platform/limits/
- https://developers.cloudflare.com/workers/wrangler/configuration/#queues
- https://developers.cloudflare.com/queues/reference/how-queues-works/
