# Queues Message Size Limit Exceeded Production Incident

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A document-processing pipeline started silently dropping messages. The Queues consumer received messages but the downstream processor never received the document content. Investigation revealed the producer was failing `queue.send()` calls with:

```
Error: Message body too large. Maximum message body size is 128 KB.
```

The error was swallowed by a catch block that only logged to console — which is not surfaced in Workers Tail during high-volume operation. The pipeline processed ~300 documents/minute with no visible failure rate in Grafana because the metric tracked queue consumer invocations, not successful document completions.

## Context

The team added a new document type — rich-text exports from a CMS — that included embedded SVG illustrations and base64-encoded image previews. The average payload ballooned from ~12 KB to ~210 KB. Cloudflare Queues enforces a **128 KB maximum message body size**. Messages above the limit are rejected at `send()` time; they never enter the queue. There is no dead-letter handling for send-time rejections — the producer simply receives an error. The payload was not validated before sending and the consumer retry mechanism could not surface a message that was never enqueued.

## 1. Understanding the Queues Size Limit

```typescript
// Cloudflare Queues limits (as of 2026)
const LIMITS = {
  maxMessageBodyBytes: 128 * 1024,       // 128 KB per message
  maxBatchSize: 100,                      // messages per batch send
  maxRetries: 3,                          // before dead-letter or discard
  maxMessageTtlSeconds: 4 * 24 * 3600,  // 4 days
} as const;

// What was being sent:
const payload = {
  documentId: "doc_xyz",
  content: richTextHtml,   // 180 KB of CMS HTML + SVG
  preview: base64Image,    // 40 KB base64 thumbnail
};
// JSON.stringify(payload) === ~230 KB — EXCEEDS 128 KB
```

## 2. Guard at the Producer

Validate payload size before attempting to enqueue. Fail fast and loudly:

```typescript
const QUEUE_MAX_BYTES = 128 * 1024;

export async function enqueueDocument(
  queue: Queue,
  doc: DocumentJob
): Promise<void> {
  const body = JSON.stringify(doc);
  const byteLength = new TextEncoder().encode(body).length;

  if (byteLength > QUEUE_MAX_BYTES) {
    // Do not swallow — surface to the caller so it can use the reference pattern
    throw new Error(
      `Document "${doc.documentId}" too large for queue: ${byteLength} bytes ` +
        `(limit ${QUEUE_MAX_BYTES}). Store payload in R2 and enqueue a reference instead.`
    );
  }

  await queue.send(doc, { contentType: "json" });
}
```

## 3. The Reference Pattern: Large Payloads via R2

Store the large payload in R2, enqueue a lightweight reference message with the R2 key, and have the consumer fetch from R2:

```typescript
// Producer Worker
interface DocumentReference {
  type: "document-reference";
  documentId: string;
  r2Key: string;
  byteLength: number;
  uploadedAt: string;
}

export async function enqueueDocumentReference(
  queue: Queue,
  bucket: R2Bucket,
  doc: { documentId: string; content: string; preview: string }
): Promise<void> {
  const payload = JSON.stringify(doc);
  const r2Key = `queue-payloads/documents/${doc.documentId}.json`;

  // Upload full payload to R2
  await bucket.put(r2Key, payload, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: { documentId: doc.documentId, uploadedAt: new Date().toISOString() },
  });

  // Enqueue a small reference (~200 bytes)
  const ref: DocumentReference = {
    type: "document-reference",
    documentId: doc.documentId,
    r2Key,
    byteLength: new TextEncoder().encode(payload).length,
    uploadedAt: new Date().toISOString(),
  };

  await queue.send(ref, { contentType: "json" });
}
```

```typescript
// Consumer Worker
export default {
  async queue(batch: MessageBatch<DocumentReference>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const ref = message.body;
      try {
        // Fetch full payload from R2
        const obj = await env.PAYLOAD_BUCKET.get(ref.r2Key);
        if (!obj) {
          console.error(`R2 object not found for document ${ref.documentId}: ${ref.r2Key}`);
          message.retry();
          continue;
        }

        const doc = await obj.json<{ documentId: string; content: string; preview: string }>();
        await processDocument(doc);

        // Clean up R2 payload after successful processing
        await env.PAYLOAD_BUCKET.delete(ref.r2Key);
        message.ack();
      } catch (err) {
        console.error(`Failed to process document ${ref.documentId}:`, err);
        message.retry();
      }
    }
  },
};
```

## 4. Tiered Routing Based on Payload Size

For pipelines with mixed payload sizes, route automatically to the reference pattern only when needed:

```typescript
export async function smartEnqueue(
  queue: Queue,
  bucket: R2Bucket,
  doc: DocumentJob
): Promise<"inline" | "reference"> {
  const INLINE_THRESHOLD = 100 * 1024; // 100 KB — leave safety margin

  const serialized = JSON.stringify(doc);
  const size = new TextEncoder().encode(serialized).length;

  if (size <= INLINE_THRESHOLD) {
    await queue.send(doc, { contentType: "json" });
    return "inline";
  }

  await enqueueDocumentReference(queue, bucket, doc as any);
  return "reference";
}
```

## 5. Monitoring Enqueue Failures

Use Analytics Engine to track send-time failures so they are not invisible:

```typescript
export async function monitoredEnqueue(
  queue: Queue,
  bucket: R2Bucket,
  doc: DocumentJob,
  analytics: AnalyticsEngineDataset
): Promise<void> {
  const size = new TextEncoder().encode(JSON.stringify(doc)).length;

  try {
    const mode = await smartEnqueue(queue, bucket, doc);
    analytics.writeDataPoint({
      blobs: ["document_enqueue", mode, "success"],
      doubles: [size],
      indexes: ["enqueue_ok"],
    });
  } catch (err) {
    analytics.writeDataPoint({
      blobs: ["document_enqueue", "error", String(err)],
      doubles: [size],
      indexes: ["enqueue_error"],
    });
    throw err;
  }
}
```

Query in Workers Analytics Engine to detect regressions:

```sql
SELECT
  blob2 AS mode,
  blob3 AS status,
  sum(double1) / count() AS avg_size_bytes,
  count() AS count
FROM document_enqueue_metrics
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY blob2, blob3
ORDER BY count DESC
```

## Anti-patterns

- Swallowing `queue.send()` errors in a generic catch block — they are not retriable the same way as consumer failures.
- Embedding binary or base64 content inline in queue messages. Base64 encoding adds ~33% overhead, making a 90 KB binary balloon to 120 KB before the rest of the envelope.
- Using queue messages as a synchronous transfer mechanism for large blobs — this is what R2 (or D1 for structured data) is for.
- Relying on consumer retry logic to handle messages that were never enqueued — producer rejections are invisible to the consumer.

## Gotchas

- The 128 KB limit applies to the **body** of the message, not the total message size including headers. The body is the object passed to `queue.send()`.
- `queue.sendBatch()` has the same per-message limit and an additional **total batch size** limit. Each message in the batch must individually be under 128 KB.
- R2 objects referenced from the queue can be deleted before the consumer processes them if TTL-based lifecycle rules are configured aggressively. Set a minimum R2 lifecycle TTL of at least 4 days (the max message TTL).
- `message.retry()` backs off exponentially but does not change the message body — if the R2 object is corrupted or missing, retries will all fail. Implement a max-retry DLQ to surface these cases.

## Verification

```bash
# Confirm no oversized messages are reaching the queue
# (check producer logs for the size guard error)
wrangler tail document-producer --format pretty | grep "too large for queue"

# Confirm R2 reference objects are being cleaned up after processing
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/r2/buckets/$BUCKET/objects?prefix=queue-payloads/documents/" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result.objects | length'
```

## Related

- queues-consumer-crash-loop-dlq-overflow-postmortem.md
- queues-consumer-visibility-timeout-retry-storm-postmortem.md
- r2-multipart-upload-size-limit-lesson.md
- kv-metadata-size-limit-exceeded-production-incident.md

## Sources

- https://developers.cloudflare.com/queues/platform/limits/
- https://developers.cloudflare.com/queues/reference/message-batching/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
