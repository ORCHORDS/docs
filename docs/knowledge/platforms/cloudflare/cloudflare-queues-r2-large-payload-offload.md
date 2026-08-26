# Cloudflare Queues: R2 Large-Payload Offload Pattern

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A Worker needs to enqueue messages that exceed the Cloudflare Queues 128 KB body limit — for example, full JSON event batches, compressed audit logs, or ML inference results — without dropping data or fragmenting messages across multiple queue entries.

## Context
Cloudflare Queues enforces a 128 KB maximum per-message body. When producers generate larger payloads, the standard pattern is to write the body to R2 and enqueue only a lightweight pointer message containing the R2 object key and metadata. The consumer Worker fetches the body from R2, processes it, then deletes the object. This keeps the queue fast and cheap while R2 handles arbitrarily large blobs.

## Producer: Writing Payload to R2 and Enqueuing a Pointer

Generate a collision-resistant key using `crypto.randomUUID()`, write the payload to R2, then enqueue a small pointer JSON.

```typescript
// producer/worker.ts
export interface Env {
  QUEUE: Queue;
  PAYLOAD_BUCKET: R2Bucket;
}

interface QueuePointer {
  payloadKey: string;
  contentType: string;
  byteLength: number;
  enqueuedAt: string;
  topic: string;
}

async function enqueueWithR2Offload(
  env: Env,
  topic: string,
  body: unknown
): Promise<void> {
  const serialized = JSON.stringify(body);
  const bytes = new TextEncoder().encode(serialized);
  const INLINE_LIMIT = 100_000; // stay safely under 128 KB

  if (bytes.byteLength <= INLINE_LIMIT) {
    // Small enough to send inline
    await env.QUEUE.send({ topic, payload: body });
    return;
  }

  // Offload to R2
  const key = `queue-payloads/${topic}/${crypto.randomUUID()}`;
  await env.PAYLOAD_BUCKET.put(key, bytes, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: { topic, enqueuedAt: new Date().toISOString() },
  });

  const pointer: QueuePointer = {
    payloadKey: key,
    contentType: "application/json",
    byteLength: bytes.byteLength,
    enqueuedAt: new Date().toISOString(),
    topic,
  };

  await env.QUEUE.send(pointer);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
    const body = await request.json();
    await enqueueWithR2Offload(env, "events", body);
    return new Response("Enqueued", { status: 202 });
  },
};
```

## Consumer: Detecting Pointer Messages and Fetching from R2

The consumer inspects each message and resolves R2 objects before processing.

```typescript
// consumer/worker.ts
export interface Env {
  PAYLOAD_BUCKET: R2Bucket;
}

interface InlineMessage {
  topic: string;
  payload: unknown;
}

interface PointerMessage {
  payloadKey: string;
  contentType: string;
  byteLength: number;
  enqueuedAt: string;
  topic: string;
}

type QueueMessage = InlineMessage | PointerMessage;

function isPointer(msg: QueueMessage): msg is PointerMessage {
  return "payloadKey" in msg;
}

async function resolvePayload(
  env: Env,
  msg: QueueMessage
): Promise<{ topic: string; payload: unknown }> {
  if (!isPointer(msg)) {
    return { topic: msg.topic, payload: msg.payload };
  }

  const obj = await env.PAYLOAD_BUCKET.get(msg.payloadKey);
  if (!obj) throw new Error(`R2 object not found: ${msg.payloadKey}`);

  const text = await obj.text();
  const payload = JSON.parse(text);
  return { topic: msg.topic, payload };
}

async function processEvent(topic: string, payload: unknown): Promise<void> {
  // domain logic here
  console.log(`Processing topic=${topic}`, typeof payload);
}

export default {
  async queue(batch: MessageBatch<QueueMessage>, env: Env): Promise<void> {
    const deleteKeys: string[] = [];

    for (const message of batch.messages) {
      try {
        const { topic, payload } = await resolvePayload(env, message.body);
        await processEvent(topic, payload);

        if (isPointer(message.body)) {
          deleteKeys.push(message.body.payloadKey);
        }

        message.ack();
      } catch (err) {
        console.error("Failed to process message", err);
        message.retry({ delaySeconds: 30 });
      }
    }

    // Batch-delete R2 objects after successful processing
    if (deleteKeys.length > 0) {
      await env.PAYLOAD_BUCKET.delete(deleteKeys);
    }
  },
};
```

## Handling R2 Object Expiry and Orphan Cleanup

If a consumer fails repeatedly and exhausts retries, R2 objects become orphans. Add an R2 lifecycle rule to auto-expire them after a safe TTL.

```typescript
// wrangler.toml snippet (TOML, not TS — shown for context)
// [[r2_buckets]]
// binding = "PAYLOAD_BUCKET"
// bucket_name = "queue-payloads"
// lifecycle = [{ id = "expire-orphans", prefix = "queue-payloads/", expiration_days = 7 }]

// Alternatively configure via API:
async function setOrphanLifecycleRule(
  accountId: string,
  bucketName: string,
  apiToken: string
): Promise<void> {
  const body = {
    rules: [
      {
        id: "expire-queue-orphans",
        status: "enabled",
        filter: { prefix: "queue-payloads/" },
        expiration: { days: 7 },
      },
    ],
  };

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/r2/buckets/${bucketName}/lifecycle`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiToken}`,
      },
      body: JSON.stringify(body),
    }
  );

  if (!resp.ok) throw new Error(`Lifecycle rule failed: ${resp.status}`);
}
```

## Wrangler Bindings Configuration

```toml
# wrangler.toml
name = "queue-producer"
compatibility_date = "2025-10-01"

[[queues.producers]]
queue = "large-payload-queue"
binding = "QUEUE"

[[r2_buckets]]
binding = "PAYLOAD_BUCKET"
bucket_name = "queue-payloads"
```

```toml
# consumer/wrangler.toml
name = "queue-consumer"
compatibility_date = "2025-10-01"

[[queues.consumers]]
queue = "large-payload-queue"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "large-payload-dlq"

[[r2_buckets]]
binding = "PAYLOAD_BUCKET"
bucket_name = "queue-payloads"
```

## Anti-patterns
- Deleting the R2 object before `message.ack()` — if processing fails after deletion, the payload is permanently lost
- Using a shared key prefix without topic namespacing — makes orphan debugging and lifecycle rules harder to scope
- Relying on the queue DLQ to preserve R2 keys — the DLQ message still holds the key, but the object may have expired if TTL is too short
- Sending arbitrarily large binary blobs through the pointer; always set a maximum size cap (e.g. 50 MB) and reject oversized payloads at ingestion

## Gotchas
- `R2Bucket.delete()` accepts an array of up to 1000 keys; batch deletes are free API calls but still bounded
- R2 `get()` on a non-existent key returns `null`, not an error — always check for null before calling `.text()`
- Queue `message.retry()` re-delivers the pointer message, not the original payload; ensure R2 objects persist longer than the maximum retry backoff window
- The 128 KB limit applies to the serialized message body after JSON encoding, not the original object size

## Verification
1. POST a payload larger than 128 KB to the producer endpoint and confirm `202 Accepted`
2. Verify the R2 object exists in the bucket under `queue-payloads/<topic>/<uuid>`
3. Confirm the queue message body is small (under 512 bytes) by inspecting queue metrics
4. Trigger consumer processing and verify the R2 object is deleted post-ack
5. Simulate a consumer failure (throw before `message.ack()`) and confirm retry re-fetches from R2

## Related
- `cloudflare-queues-dead-letter-dlq.md`
- `queues-batch-processing.md`
- `r2-large-file-patterns.md`
- `r2-lifecycle-rules.md`
- `workers-queues-patterns.md`

## Sources
- https://developers.cloudflare.com/queues/configuration/javascript-apis/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/queues/reference/message-size/
