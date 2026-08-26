# Workers R2 Event Notification Trigger Deploy

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A example project pipeline needs to process objects the moment they land in R2 — resizing images, running virus scans, generating signed URLs, or kicking off a downstream workflow. The traditional approach (polling the bucket) wastes CPU and adds latency. R2 Event Notifications push object lifecycle events to a Cloudflare Queue, which a consumer Worker drains. Deploying this topology correctly — bucket, notification rule, queue, consumer Worker — requires ordering and idempotency discipline to avoid duplicate-processing or missed events during rolling deploys.

## Context

R2 Event Notifications (GA 2024) route bucket events (`object:create`, `object:delete`) to a Cloudflare Queue. The Queue then fans out to one or more consumer Workers. Because the notification rule references both the R2 bucket and the Queue by name, all three resources must exist before the rule is created. Wrangler can create the queue and deploy the consumer, but the notification rule itself must be created via the Cloudflare API or dashboard — it is not yet a `wrangler.toml` primitive.

---

## 1. Resource Creation Order

Always provision in dependency order:

```
R2 Bucket  →  Cloudflare Queue  →  Consumer Worker deploy  →  Notification Rule
```

Reversing this order causes the API call for the notification rule to fail with a 404 on the queue or bucket reference.

```bash
# 1. Bucket (idempotent — no-op if exists)
wrangler r2 bucket create example project-uploads-prod

# 2. Queue
wrangler queues create example project-upload-events-prod

# 3. Deploy consumer Worker (see section 3)
wrangler deploy --env production --config wrangler.consumer.toml

# 4. Notification rule (via API — do after queue and Worker exist)
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/event_notifications/r2/$BUCKET_NAME/configuration" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [{
      "actions": ["PutObject", "CopyObject"],
      "queue": "example project-upload-events-prod"
    }]
  }'
```

---

## 2. Consumer Worker wrangler.toml

```toml
name = "example project-r2-consumer"
main = "src/consumer.ts"
compatibility_date = "2025-09-01"

[[queues.consumers]]
queue = "example project-upload-events-prod"
max_batch_size    = 10
max_batch_timeout = 5
max_retries       = 3
dead_letter_queue = "example project-upload-events-dlq-prod"

[env.production]
[[env.production.r2_buckets]]
binding    = "UPLOADS"
bucket_name = "example project-uploads-prod"
```

---

## 3. Consumer Worker Source

```typescript
export interface Env {
  UPLOADS: R2Bucket;
}

interface R2EventMessage {
  account: string;
  bucket: string;
  object: { key: string; size: number; eTag: string };
  action: "PutObject" | "CopyObject" | "DeleteObject";
  eventTime: string;
}

export default {
  async queue(batch: MessageBatch<R2EventMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { object, action } = msg.body;

      if (action !== "PutObject" && action !== "CopyObject") {
        msg.ack(); // skip deletes
        continue;
      }

      try {
        const head = await env.UPLOADS.head(object.key);
        if (!head) {
          // Object deleted between event emission and processing — safe to skip
          msg.ack();
          continue;
        }

        await processUpload(env, object.key, head);
        msg.ack();
      } catch (err) {
        console.error(`Failed processing ${object.key}:`, err);
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function processUpload(env: Env, key: string, head: R2Object): Promise<void> {
  const contentType = head.httpMetadata?.contentType ?? "application/octet-stream";
  // Route to appropriate handler by type
  console.log(`Processing ${key} (${contentType}, ${head.size} bytes)`);
}
```

---

## 4. Idempotent Notification Rule Management in CI

The notification rule API is not idempotent by default — posting twice creates duplicates. Wrap it in a check-then-upsert pattern:

```bash
#!/usr/bin/env bash
set -euo pipefail

EXISTING=$(curl -s \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/event_notifications/r2/$BUCKET_NAME/configuration")

RULE_COUNT=$(echo "$EXISTING" | jq '.result.rules | length')

if [ "$RULE_COUNT" -eq "0" ]; then
  echo "No rules found — creating notification rule..."
  curl -X POST \
    "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/event_notifications/r2/$BUCKET_NAME/configuration" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"rules\":[{\"actions\":[\"PutObject\",\"CopyObject\"],\"queue\":\"$QUEUE_NAME\"}]}"
else
  echo "Notification rule already exists ($RULE_COUNT rules). Skipping."
fi
```

---

## 5. Blue-Green Consumer Worker Swap

When updating the consumer logic, deploy a new Worker version and verify queue drain before cutting over:

```bash
# 1. Deploy new version without pointing the queue consumer yet
wrangler versions upload --env production --config wrangler.consumer.toml

# 2. Verify queue backlog is zero before migration
BACKLOG=$(wrangler queues info example project-upload-events-prod --json | jq '.messages_ready')
if [ "$BACKLOG" -gt "100" ]; then
  echo "Queue backlog $BACKLOG too high — deferring consumer swap"
  exit 1
fi

# 3. Migrate traffic to new version
wrangler versions deploy --env production --percentage 100
```

---

## 6. Dead-Letter Queue Drain Monitoring Post-Deploy

```typescript
// Monitoring Worker: alert if DLQ accumulates messages post-deploy
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const dlqDepth = await getDlqDepth(env);
    if (dlqDepth > 0) {
      await env.ALERTS.send({
        subject: "R2 consumer DLQ has messages",
        body: `DLQ depth: ${dlqDepth}. Investigate consumer errors.`,
      });
    }
  },
};
```

---

## Anti-patterns

- Creating the notification rule before the queue exists — the API returns 200 but the rule silently drops events.
- Using `object:*` wildcard actions without filtering on the consumer side — delete events trigger unnecessary processing attempts on already-gone objects.
- Not configuring a dead-letter queue — failed messages retry indefinitely, blocking fresh events behind them.
- Deleting and recreating the notification rule during deploys — there is a race window where events are dropped.

## Gotchas

- R2 Event Notifications guarantee **at-least-once** delivery. Consumer logic must be idempotent (check `eTag` or a processed-keys KV store).
- Notification rules survive Worker redeployment. Only the consumer Worker needs redeploying — not the rule — for code changes.
- Queue messages carry the event at **emission time**. The object may have been overwritten or deleted by the time the consumer reads it; always `HEAD` before `GET`.
- Max queue message size is 128 KB; R2 event payloads are small, but if you enrich the message in a transform Worker, watch the limit.

## Verification

```bash
# Upload a test object and confirm the consumer processed it
wrangler r2 object put example project-uploads-prod/smoke-test.txt \
  --file /dev/null --env production

# Tail the consumer Worker logs for 30 s
wrangler tail example project-r2-consumer --env production --format pretty &
TAIL_PID=$!
sleep 30
kill $TAIL_PID

# Check DLQ depth is still 0
wrangler queues info example project-upload-events-dlq-prod --json | jq '.messages_ready'
```

## Related

- `workers-queues-consumer-worker-deployment.md`
- `workers-queues-dead-letter-queue-deploy.md`
- `zero-downtime-r2-bucket-migration.md`
- `r2-bucket-cors-configuration-deploy.md`
- `deployment-health-gates-automated-rollback.md`

## Sources

- https://developers.cloudflare.com/r2/buckets/event-notifications/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/workers/runtime-apis/queues/
