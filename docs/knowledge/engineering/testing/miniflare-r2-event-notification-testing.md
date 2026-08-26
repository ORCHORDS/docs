# Miniflare R2 Event Notification Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have a Worker that reacts to R2 event notifications (object created, object deleted) delivered via a Queue consumer, and you need deterministic unit/integration tests without deploying to production or relying on real bucket events.

## Context

R2 event notifications in production route through a Cloudflare Queue: when an object is uploaded or deleted, a message is enqueued with an `R2EventNotification` payload and your consumer Worker processes it. Miniflare (v3+) supports Queues in `@cloudflare/vitest-pool-workers`, so you can enqueue synthetic notification messages directly and assert on side-effects without touching a real bucket.

This pattern tests:
- Message schema validation (required fields, bucket name, key)
- Business logic triggered per event type (`EventType: "ObjectCreatedPut"` vs `"ObjectDeletedDelete"`)
- Error handling when the payload is malformed
- DLQ promotion when the consumer throws

---

## Setting Up the Test Environment

`wrangler.toml`:
```toml
[[queues.consumers]]
queue = "r2-notifications"
max_batch_size = 10
max_retries = 2
dead_letter_queue = "r2-notifications-dlq"

[[r2_buckets]]
binding = "ASSETS"
bucket_name = "assets-dev"
```

`vitest.config.ts`:
```typescript
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          queues: {
            "r2-notifications": { maxBatchSize: 10 },
            "r2-notifications-dlq": { maxBatchSize: 10 },
          },
        },
      },
    },
  },
});
```

---

## Building a Synthetic R2 Notification Message

```typescript
// test/helpers/r2-notification.ts
import type { R2EventNotification } from "@cloudflare/workers-types";

export function makeR2Notification(
  overrides: Partial<R2EventNotification> = {}
): R2EventNotification {
  return {
    account: "test-account-id",
    bucket: "assets-dev",
    eventTime: new Date().toISOString(),
    action: "PutObject",
    object: {
      key: "uploads/sample.png",
      size: 42_000,
      eTag: "abc123def456",
    },
    copySource: null,
    ...overrides,
  };
}

export function makeQueueMessage(
  notification: R2EventNotification
): MessageSendRequest {
  return {
    body: JSON.stringify(notification),
    contentType: "json",
  };
}
```

---

## Testing ObjectCreated Events

```typescript
// test/r2-notifications.test.ts
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { makeR2Notification, makeQueueMessage } from "./helpers/r2-notification";
import worker from "../src/index";

describe("R2 ObjectCreated notifications", () => {
  it("indexes a newly uploaded object into KV", async () => {
    const notification = makeR2Notification({
      action: "PutObject",
      object: { key: "avatars/user-123.webp", size: 8_500, eTag: "e1" },
    });

    const ctx = createExecutionContext();
    await worker.queue(
      {
        messages: [
          {
            id: "msg-1",
            timestamp: new Date(),
            body: notification,
            ack: () => {},
            retry: () => {},
          },
        ],
        ackAll: () => {},
        retryAll: () => {},
      } as MessageBatch<R2EventNotification>,
      env,
      ctx
    );
    await waitOnExecutionContext(ctx);

    const indexed = await env.KV_INDEX.get("avatars/user-123.webp");
    expect(JSON.parse(indexed!)).toMatchObject({ size: 8_500 });
  });
});
```

---

## Testing ObjectDeleted Events

```typescript
describe("R2 ObjectDeleted notifications", () => {
  beforeEach(async () => {
    await env.KV_INDEX.put(
      "avatars/user-123.webp",
      JSON.stringify({ size: 8_500 })
    );
  });

  it("removes the object index entry from KV on delete", async () => {
    const notification = makeR2Notification({
      action: "DeleteObject",
      object: { key: "avatars/user-123.webp", size: 0, eTag: "" },
    });

    const ctx = createExecutionContext();
    await worker.queue(
      buildBatch([notification]),
      env,
      ctx
    );
    await waitOnExecutionContext(ctx);

    const entry = await env.KV_INDEX.get("avatars/user-123.webp");
    expect(entry).toBeNull();
  });
});

function buildBatch(
  notifications: R2EventNotification[]
): MessageBatch<R2EventNotification> {
  return {
    messages: notifications.map((body, i) => ({
      id: `msg-${i}`,
      timestamp: new Date(),
      body,
      ack: () => {},
      retry: () => {},
    })),
    ackAll: () => {},
    retryAll: () => {},
  } as unknown as MessageBatch<R2EventNotification>;
}
```

---

## Testing Malformed Payloads and DLQ Promotion

```typescript
describe("malformed R2 notification payloads", () => {
  it("calls retry on a message missing the bucket field", async () => {
    const retryCalls: string[] = [];
    const batch = {
      messages: [
        {
          id: "msg-bad",
          timestamp: new Date(),
          body: { action: "PutObject" } as unknown as R2EventNotification,
          ack: () => {},
          retry: () => retryCalls.push("msg-bad"),
        },
      ],
      ackAll: () => {},
      retryAll: () => {},
    } as unknown as MessageBatch<R2EventNotification>;

    const ctx = createExecutionContext();
    await worker.queue(batch, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(retryCalls).toContain("msg-bad");
  });
});
```

---

## Anti-patterns

- **Mocking the Queue binding directly** instead of using `worker.queue()` — skips real Miniflare Queue message dispatch and misses retry semantics.
- **Asserting only on logs** rather than on observable state (KV, D1 writes) — brittle and ties tests to implementation details.
- **Using real R2 bucket HEAD calls** inside Queue consumer tests — introduces network dependency and test flakiness.

## Gotchas

- The `body` field in `MessageBatch` messages is the **already-deserialized** object when `contentType: "json"` — do not `JSON.parse` it again inside the consumer.
- Miniflare's Queue does not simulate actual retry delays; `message.retry()` simply marks the message for retry counting but does not re-enqueue it within the same test.
- `ackAll()` and `retryAll()` on the batch object are no-ops in Miniflare unless your consumer explicitly calls them — individual `message.ack()` / `message.retry()` take precedence.

## Verification

```bash
npx vitest run test/r2-notifications.test.ts --reporter=verbose
```

All three test groups (created, deleted, malformed) should pass without network access.

## Related

- `miniflare-d1-integration-testing.md`
- `cloudflare-queues-miniflare-batch-testing.md`
- `workers-queues-retry-dlq-testing.md`
- `r2-bucket-miniflare-testing.md`

## Sources

- https://developers.cloudflare.com/r2/buckets/event-notifications/
- https://developers.cloudflare.com/queues/reference/message-batches/
- https://miniflare.dev/storage/r2
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
