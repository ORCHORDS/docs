# Testing Cloudflare Queues Consumers Locally with Miniflare Batch Simulation

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You have a Cloudflare Worker that consumes messages from a Queue — processing orders, sending emails, indexing records, or fan-out notifications. You need to test:

- That the consumer handles individual messages correctly.
- That batch processing applies the right acknowledgement strategy (partial ack on failures).
- That retry logic and dead-letter semantics work as intended.
- That the consumer does not silently drop messages when a downstream call fails.

Running against a real Cloudflare Queue in dev costs latency, requires network access, and is not reproducible in offline CI.

---

## Context

Miniflare 3 (embedded in `@cloudflare/vitest-pool-workers`) exposes a `getQueueConsumer` test API that lets you send batches of messages directly to the consumer's `queue()` handler, inspect which messages were acknowledged or retried, and verify side-effects — all in-process without deploying.

Key concepts:

- **`MessageBatch<T>`** — the object passed to your `queue()` handler, with `messages: Message<T>[]` and `.ackAll()` / `.retryAll()` methods.
- **`getQueueConsumer(env, queueName)`** — Miniflare helper that returns a callable proxy to invoke the `queue()` handler directly.
- **`QueueMessage<T>`** — individual message with `.ack()`, `.retry()`, `.body`, `.id`, `.timestamp`.

Stack: **Cloudflare Workers + Queues, Vitest 2, `@cloudflare/vitest-pool-workers` ≥ 0.5**.

---

## 1. Project Setup

### `wrangler.toml`

```toml
name = "order-processor"
compatibility_date = "2025-09-01"

[[queues.consumers]]
queue = "orders"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "orders-dlq"

[[queues.producers]]
binding = "ORDER_QUEUE"
queue = "orders"
```

### `vitest.config.ts`

```typescript
import { defineConfig } from "vitest/config";
import { defineWorkersProject } from "@cloudflare/vitest-pool-workers/config";

export default defineConfig({
  test: {
    projects: [
      defineWorkersProject({
        test: {
          poolOptions: {
            workers: {
              wranglerConfigPath: "./wrangler.toml",
              isolatedStorage: true,
            },
          },
        },
      }),
    ],
  },
});
```

---

## 2. The Queue Consumer Under Test

```typescript
// src/queue-consumer.ts
export interface OrderMessage {
  orderId: string;
  customerId: string;
  amount: number;
  currency: string;
}

export interface Env {
  DB: D1Database;
  EMAIL_SERVICE: Fetcher;
  ORDER_QUEUE: Queue<OrderMessage>;
}

export async function queue(
  batch: MessageBatch<OrderMessage>,
  env: Env
): Promise<void> {
  const failed: string[] = [];

  for (const message of batch.messages) {
    const { orderId, customerId, amount, currency } = message.body;

    try {
      // Write to D1
      await env.DB.prepare(
        `UPDATE orders SET status = 'processing', processed_at = ? WHERE id = ?`
      )
        .bind(new Date().toISOString(), orderId)
        .run();

      // Send confirmation email via a service binding
      const emailResponse = await env.EMAIL_SERVICE.fetch(
        "https://email/send",
        {
          method: "POST",
          body: JSON.stringify({ customerId, orderId, amount, currency }),
          headers: { "Content-Type": "application/json" },
        }
      );

      if (!emailResponse.ok) {
        throw new Error(`Email failed: ${emailResponse.status}`);
      }

      message.ack();
    } catch (err) {
      console.error(`Failed to process order ${orderId}:`, err);
      failed.push(orderId);
      message.retry();
    }
  }

  if (failed.length > 0) {
    console.warn(`Batch had ${failed.length} failures:`, failed);
  }
}
```

---

## 3. Test Helpers — Message Factory

```typescript
// tests/helpers/queue-messages.ts
import type { OrderMessage } from "../../src/queue-consumer";

let messageIdCounter = 0;

export function makeQueueMessage(
  body: Partial<OrderMessage> = {}
): MessageBatch<OrderMessage>["messages"][0] {
  messageIdCounter++;

  const defaultBody: OrderMessage = {
    orderId: `order-${messageIdCounter}`,
    customerId: `customer-${messageIdCounter}`,
    amount: 9999,
    currency: "usd",
  };

  let acknowledged = false;
  let retried = false;

  const message = {
    id: `msg-${messageIdCounter}-${Date.now()}`,
    timestamp: new Date(),
    body: { ...defaultBody, ...body },
    ack: () => {
      acknowledged = true;
    },
    retry: () => {
      retried = true;
    },
    attempts: 1,
    get acknowledged() {
      return acknowledged;
    },
    get retried() {
      return retried;
    },
  };

  return message as any;
}

export function makeMessageBatch<T>(
  messages: ReturnType<typeof makeQueueMessage>[]
): MessageBatch<T> {
  let allAcked = false;
  let allRetried = false;

  return {
    queue: "orders",
    messages: messages as any,
    ackAll() {
      allAcked = true;
      messages.forEach((m) => m.ack());
    },
    retryAll() {
      allRetried = true;
      messages.forEach((m) => m.retry());
    },
    get ackAllCalled() {
      return allAcked;
    },
    get retryAllCalled() {
      return allRetried;
    },
  } as any;
}
```

---

## 4. Happy Path — All Messages Acknowledged

```typescript
// tests/queue-consumer.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { queue } from "../src/queue-consumer";
import { makeQueueMessage, makeMessageBatch } from "./helpers/queue-messages";

describe("queue consumer — happy path", () => {
  beforeEach(() => {
    // Seed the database with orders
    // (Uses Miniflare's in-memory D1 via isolatedStorage)
  });

  it("acks all messages when processing succeeds", async () => {
    // Mock email service: always succeeds
    const mockEmailService = {
      fetch: vi.fn().mockResolvedValue(new Response("ok", { status: 200 })),
    };

    const messages = [
      makeQueueMessage({ orderId: "order-1", customerId: "cust-1" }),
      makeQueueMessage({ orderId: "order-2", customerId: "cust-2" }),
      makeQueueMessage({ orderId: "order-3", customerId: "cust-3" }),
    ];
    const batch = makeMessageBatch(messages);

    // Seed orders in D1
    for (const msg of messages) {
      await env.DB.prepare(
        `INSERT INTO orders (id, status) VALUES (?, 'pending')`
      )
        .bind(msg.body.orderId)
        .run();
    }

    await queue(batch, {
      ...env,
      EMAIL_SERVICE: mockEmailService as any,
    });

    // All messages should be acknowledged
    expect(messages[0].acknowledged).toBe(true);
    expect(messages[1].acknowledged).toBe(true);
    expect(messages[2].acknowledged).toBe(true);

    // None should be retried
    expect(messages.some((m) => m.retried)).toBe(false);

    // Email service called once per message
    expect(mockEmailService.fetch).toHaveBeenCalledTimes(3);
  });
});
```

---

## 5. Partial Failure — Selective Retry

```typescript
// tests/queue-consumer-partial.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, vi } from "vitest";
import { queue } from "../src/queue-consumer";
import { makeQueueMessage, makeMessageBatch } from "./helpers/queue-messages";

describe("queue consumer — partial failure", () => {
  it("retries only failed messages and acks successful ones", async () => {
    const good1 = makeQueueMessage({ orderId: "good-1" });
    const bad = makeQueueMessage({ orderId: "bad-1" });
    const good2 = makeQueueMessage({ orderId: "good-2" });

    const batch = makeMessageBatch([good1, bad, good2]);

    // Seed orders
    for (const id of ["good-1", "bad-1", "good-2"]) {
      await env.DB.prepare(
        `INSERT INTO orders (id, status) VALUES (?, 'pending')`
      )
        .bind(id)
        .run();
    }

    let callCount = 0;
    const mockEmailService = {
      fetch: vi.fn().mockImplementation(async (url: string, opts: any) => {
        callCount++;
        const body = JSON.parse(opts.body);
        if (body.orderId === "bad-1") {
          return new Response("upstream error", { status: 503 });
        }
        return new Response("ok", { status: 200 });
      }),
    };

    await queue(batch, { ...env, EMAIL_SERVICE: mockEmailService as any });

    // good-1 and good-2 acked, bad-1 retried
    expect(good1.acknowledged).toBe(true);
    expect(good1.retried).toBe(false);

    expect(bad.acknowledged).toBe(false);
    expect(bad.retried).toBe(true);

    expect(good2.acknowledged).toBe(true);
    expect(good2.retried).toBe(false);
  });

  it("does not ack a message if DB write fails", async () => {
    const msg = makeQueueMessage({ orderId: "no-such-order" });
    const batch = makeMessageBatch([msg]);

    // Do NOT seed the order in D1 — DB write will fail (FK constraint or NOT NULL)
    const mockEmailService = {
      fetch: vi.fn().mockResolvedValue(new Response("ok", { status: 200 })),
    };

    await queue(batch, { ...env, EMAIL_SERVICE: mockEmailService as any });

    expect(msg.retried).toBe(true);
    expect(msg.acknowledged).toBe(false);
    // Email should not have been sent
    expect(mockEmailService.fetch).not.toHaveBeenCalled();
  });
});
```

---

## 6. Using `getQueueConsumer` for Integration-Style Tests

```typescript
// tests/queue-consumer-integration.test.ts
import { env, getQueueConsumer } from "cloudflare:test";
import { describe, it, expect, vi } from "vitest";
import type { OrderMessage } from "../src/queue-consumer";

describe("queue consumer — integration via getQueueConsumer", () => {
  it("processes a batch sent via queue binding", async () => {
    const consumer = getQueueConsumer<OrderMessage>(env, "orders");

    const mockEnv = {
      ...env,
      EMAIL_SERVICE: {
        fetch: vi.fn().mockResolvedValue(new Response("ok", { status: 200 })),
      } as any,
    };

    // Seed
    await env.DB.prepare(
      `INSERT INTO orders (id, status) VALUES ('int-order-1', 'pending')`
    ).run();

    const result = await consumer.send(
      [{ orderId: "int-order-1", customerId: "cust-x", amount: 500, currency: "usd" }],
      { env: mockEnv }
    );

    expect(result.outcome).toBe("ackAll");
    expect(result.acknowledged).toHaveLength(1);
    expect(result.retried).toHaveLength(0);
  });

  it("reports retry outcome when consumer calls message.retry()", async () => {
    const consumer = getQueueConsumer<OrderMessage>(env, "orders");

    const mockEnv = {
      ...env,
      EMAIL_SERVICE: {
        fetch: vi
          .fn()
          .mockResolvedValue(new Response("error", { status: 500 })),
      } as any,
    };

    await env.DB.prepare(
      `INSERT INTO orders (id, status) VALUES ('retry-order-1', 'pending')`
    ).run();

    const result = await consumer.send(
      [{ orderId: "retry-order-1", customerId: "cust-y", amount: 200, currency: "usd" }],
      { env: mockEnv }
    );

    expect(result.outcome).toBe("retryAll");
    expect(result.retried).toHaveLength(1);
    expect(result.acknowledged).toHaveLength(0);
  });
});
```

---

## Anti-patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Calling `batch.ackAll()` without per-message logic | Silently acks failed messages; they are lost instead of retried | Use per-message `message.ack()` / `message.retry()` in a try/catch |
| Not testing partial-failure batches | Consumer that works for all-or-nothing fails silently when some messages error | Write a test where exactly one message in a batch of three fails |
| Mocking the entire `queue()` handler | Tests nothing about consumer logic | Mock only external dependencies (email service, fetch calls), not the handler itself |
| Using real `Date.now()` for `processed_at` without range checks | Tests fail when run at midnight UTC due to date boundaries | Assert the date is approximately correct with `toBeGreaterThan(before)` |
| Checking `ackAllCalled` on the batch instead of per-message | `ackAll()` is for the all-or-nothing path; per-message logic uses `.ack()` on each | Mirror the actual consumer's ack strategy in your assertions |

---

## Gotchas

- **`getQueueConsumer` requires the queue name in `wrangler.toml`** under `[[queues.consumers]]`; if the queue is not listed, the helper throws `"Queue not found"`.
- **`isolatedStorage: true` applies to D1 and KV but not to `vi.fn()` mocks** — reset mocks with `vi.clearAllMocks()` in `beforeEach` when sharing mock instances.
- **Message `id` uniqueness** — Cloudflare generates unique IDs; your test helper should also generate unique IDs to catch bugs where your consumer de-dupes by ID.
- **`batch.retryAll()` vs `message.retry()`** — calling `retryAll()` retries the entire batch; if your consumer uses per-message `retry()`, asserting `retryAllCalled` will be `false` even if all messages were individually retried.
- **Dead-letter queue not simulated** — Miniflare does not automatically route messages to the DLQ after `max_retries`; test DLQ behavior by observing that `retry()` was called the expected number of times.
- **Batch timeout testing** — `max_batch_timeout` is a runtime scheduling concern; test it by asserting that your consumer handles a batch of size 1 correctly (Cloudflare flushes partial batches at timeout).

---

## Verification

```bash
# Run queue consumer tests
npx vitest run tests/queue-consumer*.test.ts

# Watch mode during development
npx vitest tests/queue-consumer.test.ts

# Expected output:
# ✓ acks all messages when processing succeeds
# ✓ retries only failed messages and acks successful ones
# ✓ does not ack a message if DB write fails
# ✓ processes a batch sent via queue binding
# ✓ reports retry outcome when consumer calls message.retry()
```

---

## Related

- [`miniflare-d1-integration-testing.md`](miniflare-d1-integration-testing.md) — D1 integration with Miniflare
- [`kv-testing-miniflare.md`](kv-testing-miniflare.md) — KV binding tests
- [`durable-objects-miniflare-fake-timers.md`](durable-objects-miniflare-fake-timers.md) — DO unit testing
- [`event-driven-testing.md`](event-driven-testing.md) — general event-driven test patterns
- [`idempotency-retry-safety-testing.md`](idempotency-retry-safety-testing.md) — retry and idempotency testing

---

## Sources

- [Cloudflare Docs — Queues](https://developers.cloudflare.com/queues/)
- [Cloudflare Docs — Testing Queues with Miniflare](https://developers.cloudflare.com/queues/testing/)
- [`@cloudflare/vitest-pool-workers` — Queue test APIs](https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers)
- [Cloudflare Queues — Consumer retries and DLQ](https://developers.cloudflare.com/queues/configuration/consumer-concurrency/)
