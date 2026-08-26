# Cloudflare R2 Event Notifications Triggering Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case**: Objects uploaded to or deleted from an R2 bucket need to trigger downstream processing — image resizing, metadata indexing, virus scanning, audit logging, cache invalidation — without polling the bucket or running a scheduled cron. You want event-driven, sub-second reaction to R2 state changes, wired entirely within the Cloudflare network using R2 Event Notifications and Cloudflare Queues.

**Context**: R2 Event Notifications (GA 2024) publish events to a Cloudflare Queue when objects are created, overwritten, deleted, or when multipart uploads complete. A consumer Worker bound to the queue processes these events asynchronously. This eliminates S3 event → SNS → SQS → Lambda wiring and runs entirely on Cloudflare's network with no egress charges. Terraform provisions the bucket, queue, notification configuration, and consumer Worker binding.

---

## Terraform: R2 Bucket + Queue + Event Notification Rule

```hcl
# terraform/r2-events.tf

resource "cloudflare_r2_bucket" "uploads" {
  account_id = var.cloudflare_account_id
  name       = "user-uploads"
  location   = "ENAM"
}

# Cloudflare Queue that receives R2 events
resource "cloudflare_queue" "r2_events" {
  account_id = var.cloudflare_account_id
  name       = "r2-upload-events"

  settings {
    delivery_delay          = 0
    message_retention_period = 86400  # 24h retention
  }
}

# Event notification rule — fires on all PUT/POST events in the "uploads/" prefix
resource "cloudflare_r2_bucket_event_notification" "on_upload" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.uploads.name

  rules = [
    {
      queue_id = cloudflare_queue.r2_events.id
      prefix   = "uploads/"
      suffix   = ""     # Match all suffixes; set ".jpg" to filter by extension
      actions  = ["PutObject", "CompleteMultipartUpload"]
    },
    {
      queue_id = cloudflare_queue.r2_events.id
      prefix   = "uploads/"
      suffix   = ""
      actions  = ["DeleteObject"]
    }
  ]
}

# Consumer Worker that processes the queue
resource "cloudflare_worker_script" "r2_event_processor" {
  account_id = var.cloudflare_account_id
  name       = "r2-event-processor"
  content    = file("${path.module}/../dist/r2-event-processor.js")

  r2_bucket_binding {
    name        = "UPLOADS_BUCKET"
    bucket_name = cloudflare_r2_bucket.uploads.name
  }

  queue_binding {
    binding = "EVENTS_QUEUE"
    queue   = cloudflare_queue.r2_events.name
  }

  plain_text_binding {
    name = "RESIZE_QUEUE_URL"
    text = var.resize_queue_url
  }
}

# Wire the consumer: queue consumer = the processor worker
resource "cloudflare_queue_consumer" "r2_processor" {
  account_id   = var.cloudflare_account_id
  queue_name   = cloudflare_queue.r2_events.name
  script_name  = cloudflare_worker_script.r2_event_processor.name

  settings {
    batch_size          = 10
    max_retries         = 3
    max_wait_time_ms    = 5000   # wait up to 5s to fill a batch
    visibility_timeout_ms = 30000
  }
}
```

## R2 Event Notification Payload Shape

```typescript
// types/r2-event.ts — shape of messages delivered from the Queue

export interface R2EventMessage {
  account: string;
  bucket: string;
  eventTime: string;       // ISO 8601
  action: R2EventAction;
  object: {
    key: string;
    size: number;
    eTag: string;
    versionId?: string;
    storageClass: "Standard";
  };
  copySource?: {           // Only present for CopyObject events
    bucket: string;
    object: string;
  };
}

export type R2EventAction =
  | "PutObject"
  | "CopyObject"
  | "DeleteObject"
  | "LifecycleDeletion"
  | "CompleteMultipartUpload";
```

## Consumer Worker Implementation

```typescript
// r2-event-processor/src/index.ts

import type { R2EventMessage, R2EventAction } from "./types/r2-event";

export interface Env {
  UPLOADS_BUCKET: R2Bucket;
  EVENTS_QUEUE: Queue;            // For dead-letter forwarding
  D1_META: D1Database;            // Index metadata
  IMAGE_EXTENSIONS: string;       // ".jpg,.png,.webp,.gif"
}

export default {
  async queue(batch: MessageBatch<R2EventMessage>, env: Env): Promise<void> {
    const imageExts = env.IMAGE_EXTENSIONS.split(",").map((e) => e.trim().toLowerCase());

    for (const msg of batch.messages) {
      const event = msg.body;
      try {
        await processEvent(event, imageExts, env);
        msg.ack();
      } catch (err) {
        console.error(`Failed to process ${event.action} on ${event.object.key}:`, err);
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function processEvent(
  event: R2EventMessage,
  imageExts: string[],
  env: Env
): Promise<void> {
  const key = event.object.key;
  const ext = key.split(".").pop()?.toLowerCase() ?? "";

  switch (event.action as R2EventAction) {
    case "PutObject":
    case "CompleteMultipartUpload":
    case "CopyObject":
      await handleUpsert(key, ext, event, imageExts, env);
      break;

    case "DeleteObject":
    case "LifecycleDeletion":
      await handleDelete(key, env);
      break;
  }
}

async function handleUpsert(
  key: string,
  ext: string,
  event: R2EventMessage,
  imageExts: string[],
  env: Env
): Promise<void> {
  // 1. Index metadata in D1
  await env.D1_META.prepare(
    `INSERT INTO object_index (bucket, key, size, etag, uploaded_at)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT (bucket, key) DO UPDATE
       SET size=excluded.size, etag=excluded.etag, uploaded_at=excluded.uploaded_at`
  )
    .bind(event.bucket, key, event.object.size, event.object.eTag, event.eventTime)
    .run();

  // 2. Trigger image resizing for image objects
  if (imageExts.includes(`.${ext}`)) {
    await triggerImageResize(key, event.bucket, env);
  }

  // 3. Log audit entry
  console.log(JSON.stringify({
    type: "r2_object_created",
    bucket: event.bucket,
    key,
    size: event.object.size,
    ts: event.eventTime,
  }));
}

async function handleDelete(key: string, env: Env): Promise<void> {
  await env.D1_META.prepare(
    "DELETE FROM object_index WHERE bucket = ? AND key = ?"
  ).bind("user-uploads", key).run();

  console.log(JSON.stringify({ type: "r2_object_deleted", key, ts: new Date().toISOString() }));
}

async function triggerImageResize(key: string, bucket: string, env: Env): Promise<void> {
  // Enqueue to a separate resize queue (or call an Image Resizing Worker)
  await env.EVENTS_QUEUE.send({
    type: "resize_request",
    bucket,
    key,
    variants: ["thumbnail_200x200", "preview_800x600"],
  });
}
```

## Wrangler Configuration

```toml
# r2-event-processor/wrangler.toml
name = "r2-event-processor"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[queues.consumers]]
queue = "r2-upload-events"
max_batch_size     = 10
max_batch_timeout  = 5
max_retries        = 3
dead_letter_queue  = "r2-upload-events-dlq"

[[r2_buckets]]
binding     = "UPLOADS_BUCKET"
bucket_name = "user-uploads"

[[d1_databases]]
binding       = "D1_META"
database_name = "object-metadata"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
IMAGE_EXTENSIONS = ".jpg,.jpeg,.png,.webp,.gif,.avif"
```

## D1 Schema for Object Index

```sql
-- migrations/0001_object_index.sql
CREATE TABLE IF NOT EXISTS object_index (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  bucket      TEXT    NOT NULL,
  key         TEXT    NOT NULL,
  size        INTEGER NOT NULL,
  etag        TEXT    NOT NULL,
  uploaded_at TEXT    NOT NULL,
  UNIQUE (bucket, key)
);

CREATE INDEX IF NOT EXISTS idx_obj_bucket_key ON object_index (bucket, key);
CREATE INDEX IF NOT EXISTS idx_obj_uploaded   ON object_index (uploaded_at DESC);
```

---

**Anti-patterns**:
- Processing R2 events synchronously in a fetch handler (polling) — use the Queue consumer pattern so events are processed durably with retries.
- Setting `max_retries` to 0 on the queue consumer — transient D1 failures or downstream API errors will permanently drop events.
- Omitting a dead-letter queue (`dead_letter_queue`) — poisoned messages cycle indefinitely, blocking the batch.
- Filtering by file extension in the notification rule `suffix` and also in the Worker — double-filtering is harmless but the rule-level filter reduces queue volume; prefer rule-level filtering for known static extensions.
- Triggering expensive operations (e.g., virus scan) synchronously inside the queue consumer — chain to a second queue to avoid consumer timeout (30s default).

**Gotchas**:
- R2 Event Notifications are delivered **at-least-once** — the consumer must be idempotent (use `ON CONFLICT DO UPDATE` in D1, check ETag before reprocessing).
- Event delivery has up to ~60s latency after the R2 operation completes — do not use this for latency-sensitive real-time features.
- The `action` field uses PascalCase (`PutObject`, not `PUT`) — TypeScript discriminated union types help catch mismatches at compile time.
- Notification rules are per-bucket, not per-prefix globally — if you need different queues for different prefixes, add multiple rule entries in the `cloudflare_r2_bucket_event_notification` resource.
- Deleting the `cloudflare_r2_bucket_event_notification` resource in Terraform does not delete the queue — destroy the `cloudflare_queue` resource separately.

**Verification**:
```bash
# Upload a test object and watch queue depth
wrangler r2 object put user-uploads/uploads/test.jpg --file=test.jpg
sleep 5
wrangler queues consumer list r2-upload-events

# Query D1 to verify indexing
wrangler d1 execute object-metadata --remote \
  --command "SELECT key, size, uploaded_at FROM object_index ORDER BY uploaded_at DESC LIMIT 5"

# Check consumer Worker logs for processed events
wrangler tail r2-event-processor --format=pretty
```

**Related**:
- `cloudflare-r2-backup-restore-strategy.md`
- `cloudflare-r2-presigned-urls-workers.md`
- `cloudflare-queues-terraform-provisioning.md`
- `keda-cloudflare-queue-consumers.md`
- `cloudflare-workers-logdrain-d1-sink.md`

**Sources**:
- https://developers.cloudflare.com/r2/buckets/event-notifications/
- https://developers.cloudflare.com/queues/configuration/configure-queues/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/r2_bucket_event_notification
- https://developers.cloudflare.com/queues/reference/message-batching/
