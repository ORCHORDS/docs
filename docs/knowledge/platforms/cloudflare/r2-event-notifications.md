# r2-event-notifications

**Issue:** Receiving real-time notifications when R2 objects are created, deleted, or completed
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
R2 Event Notifications push events to a Cloudflare Queue when objects are created, deleted, or multipart-uploaded. This enables event-driven pipelines: image processing, indexing, virus scanning, etc.

## Pattern / Solution

**Step 1 — Create a Queue:**
```bash
wrangler queues create r2-events-queue
```

**Step 2 — Add event notification rule (Dashboard or API):**
```bash
# Via REST API
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/r2/buckets/my-bucket/event_notifications/r2-events-queue" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "prefix": "uploads/",
        "suffix": ".jpg",
        "actions": ["PutObject", "CompleteMultipartUpload"]
      },
      {
        "prefix": "temp/",
        "actions": ["DeleteObject"]
      }
    ]
  }'
```

**Step 3 — Worker consumes the Queue:**
```typescript
// wrangler.toml
// [[queues.consumers]]
// queue = "r2-events-queue"
// binding = "R2_EVENTS"

interface R2EventMessage {
  account: string;
  action: 'PutObject' | 'DeleteObject' | 'CompleteMultipartUpload';
  bucket: string;
  object: {
    key: string;
    size: number;
    eTag: string;
  };
  eventTime: string;
}

export default {
  async queue(batch: MessageBatch<R2EventMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const { action, bucket, object } = message.body;
      console.log(`R2 event: ${action} on s3://${bucket}/${object.key}`);

      if (action === 'PutObject' && object.key.endsWith('.jpg')) {
        // Trigger image processing
        await processImage(object.key, env);
      }

      message.ack();
    }
  },
};

async function processImage(key: string, env: Env): Promise<void> {
  const obj = await env.R2.get(key);
  if (!obj) return;
  // ... process image ...
  await env.R2.put(`processed/${key}`, processedBody);
}
```

## Gotchas
- Event notifications are delivered **at least once** — your consumer must be idempotent.
- There is a small delay (seconds) between the R2 action and the queue message arrival.
- `CopyObject` actions do **not** trigger event notifications — only `PutObject`, `DeleteObject`, `DeleteObjects`, and `CompleteMultipartUpload`.
- Each bucket can have multiple event notification rules targeting different queues.
- If the Queue consumer fails (throws), the message is retried according to Queue retry settings.
- Prefix and suffix filters in rules are matched against the object key; both must match if specified.
- Listing or reading objects does NOT generate events.

## Related
- `r2-lifecycle-rules.md`
- `workers-workers-queues-patterns.md`
- `queues-batch-processing.md`
- `r2-best-practices.md`
