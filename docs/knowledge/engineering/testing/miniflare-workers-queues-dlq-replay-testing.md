# Miniflare Workers Queues DLQ Replay Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Queues supports a dead-letter queue (DLQ): messages that exceed their retry budget
are forwarded to a separate queue for inspection and replay. Unit tests that only mock the
`queue` binding miss a critical failure mode — the Worker's `queue` handler throwing repeatedly
until messages land in the DLQ — and integration tests against the real Queues service require
a deployed Worker. Miniflare 3 exposes a `MiniflareQueues` class that lets you drive the full
retry-and-DLQ lifecycle in-process. This article shows how to wire up queue batch delivery,
exhaust retries, observe DLQ forwarding, and replay from the DLQ — all within Vitest.

## Context

The example project platform uses Queues for async processing: `email-send-queue` (consumer in
`apps/email-worker`) and `event-ingest-queue` (consumer in `apps/analytics-worker`). Both
queues declare a DLQ in `wrangler.toml`. Flaky third-party APIs (SES, segment) cause
transient failures; messages that fail all retries must land in the DLQ, be inspectable, and
be replayable after the upstream is restored. This must be verifiable without deploying.

---

## Miniflare Queue Setup with DLQ

```typescript
// test/setup/miniflare-queues.ts
import { Miniflare } from "miniflare";
import type { MiniflareOptions } from "miniflare";

export function createQueueMiniflare(opts?: Partial<MiniflareOptions>): Miniflare {
  return new Miniflare({
    modules: true,
    scriptPath: "apps/email-worker/dist/index.js",

    queueProducers: {
      EMAIL_QUEUE: { queueName: "email-send-queue" },
    },

    queueConsumers: {
      "email-send-queue": {
        maxBatchSize: 5,
        maxWaitMs: 100,
        maxRetries: 2,              // exhaust in tests quickly
        deadLetterQueue: "email-dlq",
      },
      // DLQ itself has a consumer so we can observe forwarded messages
      "email-dlq": {
        maxBatchSize: 10,
        maxWaitMs: 50,
        maxRetries: 0,              // no retries for DLQ consumer
      },
    },

    bindings: {
      SEND_EMAIL_FAILS: "false",    // control via env binding in tests
    },

    ...opts,
  });
}
```

---

## Worker Queue Handler Under Test

```typescript
// apps/email-worker/src/index.ts (relevant excerpt)
export default {
  async queue(
    batch: MessageBatch<{ to: string; subject: string; body: string }>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      if (env.SEND_EMAIL_FAILS === "true") {
        // Signal permanent failure: all messages in batch will retry
        msg.retry();
        continue;
      }
      try {
        await sendViaProvider(msg.body, env);
        msg.ack();
      } catch (err) {
        // Transient failure: individual retry
        msg.retry({ delaySeconds: 5 });
      }
    }
  },
};
```

---

## Test: Messages Exhaust Retries and Land in DLQ

```typescript
// test/queues/dlq-replay.test.ts
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { createQueueMiniflare } from "../setup/miniflare-queues";
import type { Miniflare } from "miniflare";

describe("email-send-queue DLQ behaviour", () => {
  let mf: Miniflare;

  beforeEach(async () => {
    mf = createQueueMiniflare({
      bindings: { SEND_EMAIL_FAILS: "true" },  // force retries
    });
    await mf.ready;
  });

  afterEach(async () => {
    await mf.dispose();
  });

  it("forwards undeliverable messages to DLQ after maxRetries", async () => {
    // Enqueue via the producer binding
    const ns = await mf.getQueueProducer("email-send-queue");
    await ns.send({ to: "user@example.com", subject: "Test", body: "Hello" });

    // Drain the queue — Miniflare processes batches synchronously when triggered
    // Attempt 1
    await mf.dispatchQueue("email-send-queue");
    // Attempt 2 (maxRetries = 2)
    await mf.dispatchQueue("email-send-queue");
    // After 2 retries the message should move to the DLQ
    await mf.dispatchQueue("email-send-queue");

    // Read DLQ
    const dlqMessages = await mf.getQueueMessages("email-dlq");
    expect(dlqMessages).toHaveLength(1);
    expect(dlqMessages[0].body).toMatchObject({ to: "user@example.com" });
  });

  it("includes original message metadata in DLQ entry", async () => {
    const ns = await mf.getQueueProducer("email-send-queue");
    await ns.send(
      { to: "admin@example.com", subject: "Alert", body: "Down" },
      { contentType: "json" }
    );

    // exhaust retries
    for (let i = 0; i <= 2; i++) await mf.dispatchQueue("email-send-queue");

    const [dlqMsg] = await mf.getQueueMessages("email-dlq");
    expect(dlqMsg.attempts).toBe(3);            // original + 2 retries
    expect(dlqMsg.timestamp).toBeDefined();
  });
});
```

---

## Test: DLQ Replay After Upstream Recovery

```typescript
// test/queues/dlq-replay.test.ts (continued)
describe("DLQ replay after recovery", () => {
  let mf: Miniflare;

  beforeEach(async () => {
    // Start with email sending disabled → messages fail to DLQ
    mf = createQueueMiniflare({ bindings: { SEND_EMAIL_FAILS: "true" } });
    await mf.ready;

    // Populate DLQ by failing the main queue
    const ns = await mf.getQueueProducer("email-send-queue");
    await ns.sendBatch([
      { body: { to: "a@example.com", subject: "S", body: "B" } },
      { body: { to: "b@example.com", subject: "S", body: "B" } },
    ]);
    for (let i = 0; i <= 2; i++) await mf.dispatchQueue("email-send-queue");
  });

  afterEach(() => mf.dispose());

  it("DLQ has 2 messages before replay", async () => {
    const msgs = await mf.getQueueMessages("email-dlq");
    expect(msgs).toHaveLength(2);
  });

  it("re-enqueueing DLQ messages to main queue succeeds after recovery", async () => {
    // Simulate upstream recovery
    await mf.setOptions({ bindings: { SEND_EMAIL_FAILS: "false" } });

    const dlqMsgs = await mf.getQueueMessages("email-dlq");
    const producer = await mf.getQueueProducer("email-send-queue");

    // Replay: re-send each DLQ message body back to the main queue
    await producer.sendBatch(dlqMsgs.map((m) => ({ body: m.body })));

    // Drain DLQ (consumer acks after reading)
    await mf.dispatchQueue("email-dlq");

    // Drain main queue — should succeed now
    await mf.dispatchQueue("email-send-queue");

    // Verify main queue is empty
    const remaining = await mf.getQueueMessages("email-send-queue");
    expect(remaining).toHaveLength(0);
  });
});
```

---

## Test: Batch Partial Failure — Only Failed Messages Go to DLQ

```typescript
// test/queues/partial-batch.test.ts
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createQueueMiniflare } from "../setup/miniflare-queues";

describe("partial batch failure", () => {
  it("only individually-retried messages land in DLQ", async () => {
    let callCount = 0;
    const mf = createQueueMiniflare({
      // Override script to selectively fail message 0 only
      script: `
        export default {
          async queue(batch, env) {
            for (const msg of batch.messages) {
              if (msg.body.index === 0) { msg.retry(); }
              else { msg.ack(); }
            }
          }
        }
      `,
      modules: true,
    });
    await mf.ready;

    const ns = await mf.getQueueProducer("email-send-queue");
    await ns.sendBatch([
      { body: { index: 0, to: "fail@example.com" } },
      { body: { index: 1, to: "pass@example.com" } },
    ]);

    // Exhaust retries for msg 0
    for (let i = 0; i <= 2; i++) await mf.dispatchQueue("email-send-queue");

    const dlq = await mf.getQueueMessages("email-dlq");
    expect(dlq).toHaveLength(1);
    expect(dlq[0].body).toMatchObject({ to: "fail@example.com" });

    await mf.dispose();
  });
});
```

---

## Observability: Asserting Queue Metrics

```typescript
// test/queues/metrics.test.ts
import { describe, it, expect } from "vitest";
import { createQueueMiniflare } from "../setup/miniflare-queues";

describe("queue metrics", () => {
  it("tracks retry count per message", async () => {
    const mf = createQueueMiniflare({ bindings: { SEND_EMAIL_FAILS: "true" } });
    await mf.ready;

    const ns = await mf.getQueueProducer("email-send-queue");
    await ns.send({ to: "x@example.com", subject: "S", body: "B" });

    const dispatches: number[] = [];
    for (let attempt = 0; attempt <= 2; attempt++) {
      await mf.dispatchQueue("email-send-queue");
      const pending = await mf.getQueueMessages("email-send-queue");
      dispatches.push(pending.length);
    }

    // After 2 retries message leaves the main queue
    expect(dispatches[dispatches.length - 1]).toBe(0);

    const dlq = await mf.getQueueMessages("email-dlq");
    expect(dlq[0].attempts).toBeGreaterThanOrEqual(2);

    await mf.dispose();
  });
});
```

---

## Anti-patterns

- **Not asserting DLQ is populated** – Testing only that the main queue empties misses the
  case where messages are silently dropped. Always assert `getQueueMessages("email-dlq")`.
- **Using `batch.retryAll()` instead of per-message `retry()`** – `retryAll()` retries every
  message together; partial failures require per-message control. Tests that use `retryAll()`
  in the Worker handler cannot reproduce partial-batch DLQ scenarios.
- **Disposing Miniflare before all dispatches complete** – `dispatchQueue` is async; awaiting
  it inside a `beforeEach` without proper sequencing causes flaky tests where the DLQ is
  not yet populated when assertions run.
- **Setting `maxRetries: 0` on the main queue** – Tests pass instantly but don't validate
  retry spacing, backoff configuration, or that transient errors recover. Keep `maxRetries`
  at 2 to match the lowest production value.
- **Re-enqueueing to the DLQ queue itself** – Replay means sending back to the original
  queue, not to the DLQ. Sending to the DLQ again creates an infinite forwarding loop in
  production.

---

## Gotchas

- Miniflare's `dispatchQueue` is a test-only method; it is not exposed in the production
  runtime. It forces immediate delivery regardless of `maxWaitMs`.
- `getQueueMessages` returns a snapshot; it does not consume the messages. Call
  `dispatchQueue` on the DLQ's consumer to ACK them and clear the list.
- `setOptions` in Miniflare (used to toggle `SEND_EMAIL_FAILS`) rebuilds the Worker
  module in some versions. Dispose and re-create the instance if `setOptions` behaviour
  is inconsistent in your Miniflare version.
- Cloudflare Queues does not guarantee message ordering; the DLQ may receive messages in
  a different order than they were originally sent. Assert on `body` content, not array index.
- `delaySeconds` in `msg.retry({ delaySeconds: N })` is honoured by the real Queues
  backend but Miniflare's `dispatchQueue` ignores it and delivers immediately — useful for
  fast tests but means delay-based backoff is not tested here.

---

## Verification

```bash
# Run all queue DLQ tests
pnpm vitest run test/queues/

# Verbose to confirm batch dispatch counts
pnpm vitest run --reporter=verbose test/queues/dlq-replay.test.ts

# Type-check Worker and test files
pnpm tsc --noEmit

# Coverage on the queue handler module
pnpm vitest run --coverage \
  --coverage.include="apps/email-worker/src/**" \
  test/queues/
```

Expected: all assertions green, `dlq` queue populated after retry exhaustion, `email-send-queue`
empty after successful replay.

---

## Related

- `cloudflare-queues-miniflare-batch-testing.md`
- `workers-queues-retry-dlq-testing.md`
- `k6-workers-queues-consumer-throughput.md`
- `miniflare-d1-integration-testing.md`
- `event-driven-async-api-testing.md`

---

## Sources

- Cloudflare Queues DLQ docs: https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- Miniflare Queue testing API: https://github.com/cloudflare/workers-sdk/blob/main/packages/miniflare/README.md#queues
- Cloudflare Queues message retries: https://developers.cloudflare.com/queues/configuration/batching-retries/
- `@cloudflare/vitest-pool-workers` integration: https://developers.cloudflare.com/workers/testing/vitest-integration/
