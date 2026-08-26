# Miniflare R2 Event Notification Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Worker uses R2 event notifications to trigger downstream processing
(e.g., resizing an image after upload, archiving deleted objects). Production
notifications flow through Cloudflare Queues or EventBridge, but in local dev
there is no real notification infrastructure, so you cannot verify that your
consumer Worker actually runs in response to R2 operations.

---

## Context

Cloudflare R2 event notifications (GA since 2024) fire a Queue message whenever
a configured action occurs on a bucket (PutObject, DeleteObject,
CompleteMultipartUpload, CopyObject, LifecycleDeletion). Miniflare 3/4 ships a
local Queue implementation and an R2 binding, but does not automatically wire
the notification side-channel. You must simulate the notification payload
yourself and deliver it via the programmatic Queue API.

The canonical notification payload shape is documented in the Cloudflare R2
docs; the fields relevant to local testing are `account`, `bucket`, `object`,
`action`, and `eventTime`.

---

## 1. Notification Payload Shape

```typescript
// src/types/r2-notification.ts
export interface R2EventNotification {
  account: string;
  bucket: string;
  object: {
    key: string;
    size: number;
    eTag: string;
  };
  action:
    | "PutObject"
    | "DeleteObject"
    | "CompleteMultipartUpload"
    | "CopyObject"
    | "LifecycleDeletion";
  eventTime: string; // ISO-8601
  copySource?: { bucket: string; object: string };
}

export function makeR2Event(
  bucket: string,
  key: string,
  action: R2EventNotification["action"] = "PutObject",
  overrides: Partial<R2EventNotification> = {}
): R2EventNotification {
  return {
    account: "test-account-id",
    bucket,
    object: { key, size: 1024, eTag: `"${crypto.randomUUID()}"` },
    action,
    eventTime: new Date().toISOString(),
    ...overrides,
  };
}
```

---

## 2. Miniflare Harness with Fake Queue Delivery

```typescript
// tests/harness/miniflare.ts
import { Miniflare, Log, LogLevel } from "miniflare";

export async function createHarness() {
  const mf = new Miniflare({
    modules: true,
    scriptPath: "dist/worker.js",
    r2Buckets: ["MY_BUCKET"],
    queueProducers: { NOTIFICATION_QUEUE: "r2-notifications" },
    queueConsumers: {
      "r2-notifications": { maxBatchSize: 10, maxWaitMs: 50 },
    },
    bindings: { ACCOUNT_ID: "test-account-id" },
    log: new Log(LogLevel.WARN),
  });

  await mf.ready;

  return {
    mf,
    r2: await mf.getR2Bucket("MY_BUCKET"),
    queue: await mf.getQueue("r2-notifications"),
    async teardown() {
      await mf.dispose();
    },
  };
}
```

---

## 3. Sending a Synthetic R2 Notification

```typescript
// tests/r2-notification.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { createHarness } from "./harness/miniflare.js";
import { makeR2Event } from "../src/types/r2-notification.js";

let ctx: Awaited<ReturnType<typeof createHarness>>;

beforeAll(async () => {
  ctx = await createHarness();
});

afterAll(() => ctx.teardown());

describe("R2 → Queue notification consumer", () => {
  it("processes a PutObject event and stores metadata", async () => {
    const { r2, queue, mf } = ctx;

    // 1. Write a real object so the consumer can read it back
    await r2.put("images/photo.jpg", new Uint8Array([0xff, 0xd8, 0xff]));

    // 2. Synthesise the notification Cloudflare would have sent
    const event = makeR2Event("MY_BUCKET", "images/photo.jpg", "PutObject");

    // 3. Push it into the local queue exactly as Cloudflare would
    await queue.send(event, { contentType: "json" });

    // 4. Wait for the queue consumer batch to flush (maxWaitMs = 50 ms)
    await new Promise((r) => setTimeout(r, 200));

    // 5. Assert the consumer Worker wrote the expected KV entry
    const kv = await mf.getKVNamespace("METADATA_KV");
    const stored = await kv.get("images/photo.jpg", "json");
    expect(stored).toMatchObject({ action: "PutObject", bucket: "MY_BUCKET" });
  });
});
```

---

## 4. Testing a DeleteObject Cascade

```typescript
it("removes downstream KV entry on DeleteObject", async () => {
  const { r2, queue, mf } = ctx;

  const kv = await mf.getKVNamespace("METADATA_KV");

  // Seed existing metadata so the consumer has something to delete
  await kv.put(
    "docs/report.pdf",
    JSON.stringify({ action: "PutObject", bucket: "MY_BUCKET" })
  );

  // Delete the actual object first (consumer may verify it's gone)
  await r2.delete("docs/report.pdf");

  const event = makeR2Event("MY_BUCKET", "docs/report.pdf", "DeleteObject", {
    object: { key: "docs/report.pdf", size: 0, eTag: '""' },
  });
  await queue.send(event, { contentType: "json" });
  await new Promise((r) => setTimeout(r, 200));

  const entry = await kv.get("docs/report.pdf");
  expect(entry).toBeNull();
});
```

---

## 5. Batch-Delivery and Retry Simulation

```typescript
// tests/r2-notification-batch.test.ts
it("handles a mixed batch with one failure (retry semantics)", async () => {
  const { queue, mf } = ctx;

  const events = [
    makeR2Event("MY_BUCKET", "a.txt", "PutObject"),
    makeR2Event("MY_BUCKET", "b.txt", "PutObject"),
    // third event has an invalid key that the consumer should reject
    makeR2Event("MY_BUCKET", "", "PutObject"),
  ];

  for (const e of events) {
    await queue.send(e, { contentType: "json" });
  }

  await new Promise((r) => setTimeout(r, 300));

  // Miniflare re-queues messages whose item.retry() was called
  const dlqKv = await mf.getKVNamespace("DLQ_STORE");
  const dlqCount = await dlqKv.get<number>("retry-count", "json");
  expect(dlqCount).toBe(1);
});
```

---

## 6. Integration with `wrangler dev` via Unstable API

```typescript
// scripts/seed-r2-notifications.ts
// Run alongside `wrangler dev` to inject test events without Miniflare
import { unstable_dev } from "wrangler";

const worker = await unstable_dev("src/consumer.ts", {
  experimental: { disableExperimentalWarning: true },
  vars: { ACCOUNT_ID: "local-test" },
});

const event = makeR2Event("MY_BUCKET", "seed/test.txt", "PutObject");
const res = await worker.fetch("http://localhost/internal/queue", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ messages: [{ body: event }] }),
});
console.log(await res.text());
await worker.stop();
```

---

## Anti-patterns

- **Calling `r2.put()` and expecting automatic notification dispatch** –
  Miniflare does not wire R2 operations to Queue messages automatically. You
  must send the Queue message manually in tests.
- **Asserting immediately after `queue.send()`** – The consumer runs
  asynchronously in the Miniflare event loop. Always add a short `setTimeout`
  or poll until the assertion passes.
- **Reusing the same `eTag` value across test objects** – Some consumer Workers
  deduplicate by eTag. Use `crypto.randomUUID()` per event.
- **Testing with `maxWaitMs: 0`** – Setting zero wait makes the batch flush
  instantly but may miss slow I/O inside the consumer; prefer 50–100 ms for
  realism.

---

## Gotchas

- Queue consumers in Miniflare run in the same isolate as the producer; if your
  consumer imports modules that clash with the producer, bundle them separately.
- The `size` field in the notification is the byte count **before** any
  transformation; for deleted objects it should be `0`.
- R2 notifications in production include a `CF-R2-Notification-ID` header for
  idempotency; the local simulation does not add this. If your consumer checks
  it, inject it as a Queue message metadata field.
- Miniflare 4's `getQueue()` returns a different class than Miniflare 3's
  `getQueueProducer()`; check the Miniflare version in use.

---

## Verification

```bash
# Run the test suite with verbose queue logging
MINIFLARE_LOG=debug vitest run tests/r2-notification.test.ts

# Confirm message delivery count
vitest run --reporter=verbose tests/r2-notification-batch.test.ts | grep "DLQ"
```

---

## Related

- `miniflare-d1-test-seeding-fixtures.md`
- `miniflare-durable-objects-fake-clock-testing.md`
- `miniflare-storage-backend-testing.md`
- `vitest-workers-queue-batch-testing.md`
- `wrangler-dev-local-d1-r2-kv.md`

---

## Sources

- Cloudflare R2 event notifications docs: https://developers.cloudflare.com/r2/buckets/event-notifications/
- Miniflare Queue API: https://miniflare.dev/storage/queues
- workers-sdk `unstable_dev` API: https://github.com/cloudflare/workers-sdk/tree/main/packages/wrangler#unstable_dev
