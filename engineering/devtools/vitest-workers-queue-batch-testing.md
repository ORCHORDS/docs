# Vitest Workers Queue Batch Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You have a Cloudflare Workers consumer that implements a `queue()` handler for
processing batches from a Queue binding. Unit and integration tests for it are
awkward — `queue()` receives a `MessageBatch` object that is hard to construct
manually, retry semantics are invisible, and you cannot observe which messages were
`ack()`-ed vs `retry()`-ed without wrapping the batch.

## Context

`@cloudflare/vitest-pool-workers` provides a `createMessageBatch` helper and exposes
`getQueueResult()` to inspect which messages were acknowledged or retried after calling
`env.QUEUE.send()` in unit tests. This lets you write deterministic, isolated tests
for queue consumer logic without deploying to production or relying on the real Queue
service.

Dependencies: `@cloudflare/vitest-pool-workers@^0.5`, `vitest@^2`,
`@cloudflare/workers-types@^4`.

---

## 1. Worker with queue consumer handler

```typescript
// src/worker.ts
export interface Env {
  RESULTS_KV: KVNamespace;
}

interface OrderPayload {
  orderId: string;
  amount: number;
}

export default {
  async fetch(): Promise<Response> {
    return new Response("ok");
  },

  async queue(batch: MessageBatch<OrderPayload>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const { orderId, amount } = message.body;

      if (amount <= 0) {
        // Invalid message — don't retry
        message.ack();
        continue;
      }

      try {
        await env.RESULTS_KV.put(`order:${orderId}`, String(amount));
        message.ack();
      } catch {
        message.retry({ delaySeconds: 30 });
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## 2. Vitest pool-workers config

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          kvNamespaces: ["RESULTS_KV"],
          queues: {
            producers: [{ queue: "orders", binding: "ORDERS_QUEUE" }],
            consumers: [{ queue: "orders" }],
          },
        },
      },
    },
  },
});
```

## 3. Creating a MessageBatch in tests

```typescript
// tests/queue-consumer.test.ts
import {
  createMessageBatch,
  getQueueResult,
  env,
} from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import worker from "../src/worker.js";

describe("queue consumer", () => {
  beforeEach(async () => {
    // Reset KV state between tests
    const list = await env.RESULTS_KV.list();
    await Promise.all(list.keys.map((k) => env.RESULTS_KV.delete(k.name)));
  });

  it("acks valid messages and writes to KV", async () => {
    const batch = createMessageBatch<{ orderId: string; amount: number }>(
      "orders",
      [
        { body: { orderId: "ord-1", amount: 99 } },
        { body: { orderId: "ord-2", amount: 50 } },
      ]
    );

    await worker.queue(batch, env);

    const result = getQueueResult(batch);
    expect(result.ackCount).toBe(2);
    expect(result.retryCount).toBe(0);

    expect(await env.RESULTS_KV.get("order:ord-1")).toBe("99");
    expect(await env.RESULTS_KV.get("order:ord-2")).toBe("50");
  });

  it("acks invalid messages without writing to KV", async () => {
    const batch = createMessageBatch<{ orderId: string; amount: number }>(
      "orders",
      [{ body: { orderId: "bad-order", amount: -10 } }]
    );

    await worker.queue(batch, env);

    const result = getQueueResult(batch);
    expect(result.ackCount).toBe(1);
    expect(result.retryCount).toBe(0);
    expect(await env.RESULTS_KV.get("order:bad-order")).toBeNull();
  });
});
```

## 4. Testing retry semantics and delay

```typescript
// tests/queue-retry.test.ts
import {
  createMessageBatch,
  getQueueResult,
  env,
  runWithWorkerContext,
} from "cloudflare:test";
import { it, expect, vi } from "vitest";
import worker from "../src/worker.js";

it("retries messages when KV put throws", async () => {
  // Temporarily make KV throws
  const original = env.RESULTS_KV.put.bind(env.RESULTS_KV);
  const spy = vi.spyOn(env.RESULTS_KV, "put").mockRejectedValueOnce(
    new Error("KV unavailable")
  );

  const batch = createMessageBatch<{ orderId: string; amount: number }>(
    "orders",
    [{ body: { orderId: "ord-3", amount: 25 } }]
  );

  await worker.queue(batch, env);

  const result = getQueueResult(batch);
  expect(result.retryCount).toBe(1);
  expect(result.ackCount).toBe(0);
  // The retry carries the configured delay
  expect(result.retries[0]?.delaySeconds).toBe(30);

  spy.mockRestore();
});
```

## 5. Testing `retryAll()` and `ackAll()` batch methods

```typescript
// tests/queue-batch-methods.test.ts
import { createMessageBatch, getQueueResult, env } from "cloudflare:test";
import { it, expect } from "vitest";

it("retryAll re-queues every message", async () => {
  const batch = createMessageBatch<{ orderId: string; amount: number }>(
    "orders",
    [
      { body: { orderId: "a", amount: 1 } },
      { body: { orderId: "b", amount: 2 } },
    ]
  );

  // Simulate a consumer that gives up on the whole batch
  batch.retryAll({ delaySeconds: 60 });

  const result = getQueueResult(batch);
  expect(result.retryCount).toBe(2);
  expect(result.ackCount).toBe(0);
});

it("ackAll acknowledges every message", async () => {
  const batch = createMessageBatch<{ orderId: string; amount: number }>(
    "orders",
    [
      { body: { orderId: "c", amount: 5 } },
      { body: { orderId: "d", amount: 10 } },
    ]
  );

  batch.ackAll();

  const result = getQueueResult(batch);
  expect(result.ackCount).toBe(2);
  expect(result.retryCount).toBe(0);
});
```

## 6. Testing queue producer sends (end-to-end local)

```typescript
// tests/queue-producer.test.ts
import { env } from "cloudflare:test";
import { it, expect } from "vitest";

it("sends a message to the ORDERS_QUEUE binding", async () => {
  // Using the Miniflare queue binding directly in tests
  await env.ORDERS_QUEUE.send({ orderId: "e2e-1", amount: 42 });
  // In local Miniflare, sent messages are visible via the consumer after flush
  await env.ORDERS_QUEUE.sendBatch([
    { body: { orderId: "e2e-2", amount: 7 } },
    { body: { orderId: "e2e-3", amount: 3 } },
  ]);
  // No assertion here — this test confirms send() does not throw
  expect(true).toBe(true);
});
```

## Anti-patterns

- Constructing a `MessageBatch` object by hand (plain object literal) — the Workers
  runtime enforces internal invariants on the batch; `createMessageBatch` is the only
  correct way to produce one in tests.
- Not resetting KV/DO state between tests — queue consumer tests often write side
  effects; failing to clean up causes false positives/negatives in subsequent tests.
- Asserting on message count from the real Cloudflare Queue dashboard in CI — the
  queue service is eventually consistent; prefer `getQueueResult` on the local batch.

## Gotchas

- `getQueueResult` only works within the `@cloudflare/vitest-pool-workers` runtime.
  Running tests with plain Vitest (no Workers pool) will throw a "not in Workers
  context" error.
- Messages in a batch are processed synchronously within the `queue()` handler; you
  cannot use `waitUntil` to defer acks — they must be called before the handler returns.
- The `delaySeconds` in `retry()` options is recorded by `getQueueResult` but is not
  enforced in local Miniflare — tests that depend on actual delay timing must use
  integration tests against the live Queue service.

## Verification

```bash
# Run queue-specific tests only
pnpm vitest run tests/queue-consumer.test.ts tests/queue-retry.test.ts

# Coverage for queue handler
pnpm vitest run --coverage tests/queue-*.test.ts
```

## Related

- `vitest-pool-workers-cloudflare-test-api.md`
- `vitest-workers-miniflare-testing-setup.md`
- `miniflare-storage-backend-testing.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
