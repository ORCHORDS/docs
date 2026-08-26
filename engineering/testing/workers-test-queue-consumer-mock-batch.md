# Testing Workers Queue Consumer with Mock MessageBatch

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Worker implements a Queue consumer (`queue(batch, env)` handler) and you need to unit-test message processing logic — including individual `ack()`/`retry()` calls, dead-letter queue routing on max retries, and snapshot assertions of processed output — without a real Cloudflare Queue delivering messages.

---

## Context
Cloudflare Queues deliver a `MessageBatch<T>` object to the `queue()` handler. In tests you can construct a plain object that satisfies the `MessageBatch` interface: a `queue` name string, an array of `Message<T>` objects (each with `id`, `timestamp`, `attempts`, `body`, `ack()`, and `retry()` methods), plus `retryAll()` and `ackAll()` batch-level methods. Using `vi.fn()` for `ack` and `retry` lets you assert exactly which messages were acknowledged or retried. This approach works inside `@cloudflare/vitest-pool-workers` or plain Vitest — no sandbox required for pure logic tests.

---

## Setup / Config

```toml
# wrangler.toml
name = "queue-consumer"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[queues.consumers]]
queue = "orders-queue"
max_retries = 3
dead_letter_queue = "orders-dlq"

[[queues.producers]]
binding = "DLQ"
queue = "orders-dlq"
```

## Implementation

```typescript
// src/index.ts
export interface Env {
  DLQ: Queue<OrderMessage>;
}

export interface OrderMessage {
  orderId: string;
  productId: string;
  quantity: number;
}

export interface ProcessedOrder {
  orderId: string;
  total: number;
  processedAt: string;
}

const PRICE_MAP: Record<string, number> = {
  "prod-001": 4999,
  "prod-002": 9999,
};

const MAX_ATTEMPTS = 3;

export async function processMessage(
  message: Message<OrderMessage>,
  env: Env
): Promise<ProcessedOrder | null> {
  const { orderId, productId, quantity } = message.body;

  const pricePerUnit = PRICE_MAP[productId];
  if (!pricePerUnit) {
    // Unknown product — send to DLQ if max retries exhausted, else retry
    if (message.attempts >= MAX_ATTEMPTS) {
      await env.DLQ.send({ orderId, productId, quantity });
      message.ack(); // ack so the queue doesn't retry endlessly
      return null;
    }
    message.retry();
    return null;
  }

  const total = pricePerUnit * quantity;
  message.ack();
  return { orderId, total, processedAt: new Date().toISOString() };
}

export default {
  async queue(
    batch: MessageBatch<OrderMessage>,
    env: Env
  ): Promise<void> {
    for (const message of batch.messages) {
      await processMessage(message, env);
    }
  },
};
```

## Testing

```typescript
// src/index.test.ts
import { describe, it, expect, vi, afterEach } from "vitest";
import type { OrderMessage, Env, ProcessedOrder } from "./index";
import { processMessage } from "./index";

// ---- Mock helpers -------------------------------------------------------

function mockMessage(
  body: OrderMessage,
  overrides: { attempts?: number } = {}
): Message<OrderMessage> {
  return {
    id: `msg-${crypto.randomUUID()}`,
    timestamp: new Date(),
    attempts: overrides.attempts ?? 1,
    body,
    ack: vi.fn(),
    retry: vi.fn(),
    leaseExpiry: new Date(Date.now() + 30_000),
  };
}

function mockBatch(
  messages: Message<OrderMessage>[]
): MessageBatch<OrderMessage> {
  return {
    queue: "orders-queue",
    messages,
    retryAll: vi.fn(),
    ackAll: vi.fn(),
  };
}

function mockEnv(): Env {
  return {
    DLQ: {
      send: vi.fn().mockResolvedValue(undefined),
      sendBatch: vi.fn().mockResolvedValue(undefined),
    } as unknown as Queue<OrderMessage>,
  };
}

// ---- Tests --------------------------------------------------------------

describe("Queue consumer — processMessage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("acks a valid message and returns processed order", async () => {
    const msg = mockMessage({ orderId: "ord-1", productId: "prod-001", quantity: 2 });
    const env = mockEnv();

    const result = await processMessage(msg, env);

    expect(msg.ack).toHaveBeenCalledOnce();
    expect(msg.retry).not.toHaveBeenCalled();
    expect(result).not.toBeNull();
    expect(result!.orderId).toBe("ord-1");
    expect(result!.total).toBe(9998); // 4999 * 2
  });

  it("retries an unknown product when under max attempts", async () => {
    const msg = mockMessage(
      { orderId: "ord-2", productId: "unknown-prod", quantity: 1 },
      { attempts: 2 }
    );
    const env = mockEnv();

    const result = await processMessage(msg, env);

    expect(msg.retry).toHaveBeenCalledOnce();
    expect(msg.ack).not.toHaveBeenCalled();
    expect(result).toBeNull();
    expect(env.DLQ.send).not.toHaveBeenCalled();
  });

  it("routes to DLQ and acks on max retries for unknown product", async () => {
    const msg = mockMessage(
      { orderId: "ord-3", productId: "unknown-prod", quantity: 1 },
      { attempts: 3 } // == MAX_ATTEMPTS
    );
    const env = mockEnv();

    const result = await processMessage(msg, env);

    expect(env.DLQ.send).toHaveBeenCalledOnce();
    expect(env.DLQ.send).toHaveBeenCalledWith({
      orderId: "ord-3",
      productId: "unknown-prod",
      quantity: 1,
    });

    expect(msg.ack).toHaveBeenCalledOnce();
    expect(msg.retry).not.toHaveBeenCalled();
    expect(result).toBeNull();
  });

  it("processes a full batch calling ack on each valid message", async () => {
    const messages = [
      mockMessage({ orderId: "ord-10", productId: "prod-001", quantity: 1 }),
      mockMessage({ orderId: "ord-11", productId: "prod-002", quantity: 3 }),
      mockMessage({ orderId: "ord-12", productId: "prod-001", quantity: 2 }),
    ];
    const batch = mockBatch(messages);
    const env = mockEnv();

    const { default: worker } = await import("./index");
    await worker.queue(batch, env);

    for (const msg of messages) {
      expect(msg.ack).toHaveBeenCalledOnce();
      expect(msg.retry).not.toHaveBeenCalled();
    }

    expect(batch.retryAll).not.toHaveBeenCalled();
    expect(batch.ackAll).not.toHaveBeenCalled();
  });

  it("snapshot of processed output for a valid message", async () => {
    vi.setSystemTime(new Date("2026-08-24T12:00:00.000Z"));

    const msg = mockMessage({
      orderId: "ord-snapshot",
      productId: "prod-002",
      quantity: 1,
    });
    const env = mockEnv();

    const result = await processMessage(msg, env);

    expect(result).toMatchInlineSnapshot(`
      {
        "orderId": "ord-snapshot",
        "processedAt": "2026-08-24T12:00:00.000Z",
        "total": 9999,
      }
    `);

    vi.useRealTimers();
  });

  it("individual message retry does not affect other messages in batch", async () => {
    const goodMsg = mockMessage({
      orderId: "ord-good",
      productId: "prod-001",
      quantity: 1,
    });
    const badMsg = mockMessage(
      { orderId: "ord-bad", productId: "no-such-product", quantity: 1 },
      { attempts: 1 }
    );
    const batch = mockBatch([goodMsg, badMsg]);
    const env = mockEnv();

    const { default: worker } = await import("./index");
    await worker.queue(batch, env);

    expect(goodMsg.ack).toHaveBeenCalledOnce();
    expect(goodMsg.retry).not.toHaveBeenCalled();
    expect(badMsg.retry).toHaveBeenCalledOnce();
    expect(badMsg.ack).not.toHaveBeenCalled();
  });
});
```

---

## Anti-patterns
- **Calling `batch.retryAll()` on any error** — this retries ALL messages including ones that already processed successfully; always `retry()` individual messages.
- **Not resetting `vi.setSystemTime`** — forgetting `vi.useRealTimers()` after a fixed-time test will cause subsequent tests to see a frozen clock.
- **Asserting `ack` was called without asserting `retry` was not** — both assertions together confirm the message took exactly one path.
- **Using real Queue bindings in unit tests** — the Queue infrastructure adds latency and requires a real Workers environment; mock it so tests run in milliseconds.

---

## Gotchas
- The `Message<T>` interface includes `leaseExpiry` in some SDK versions; add it to your mock or TypeScript will complain if the type requires it.
- `vi.setSystemTime` must be called before the code under test calls `new Date()`; Vitest patches the global `Date` object.
- `toMatchInlineSnapshot` auto-updates the snapshot string on the first run; commit the generated snapshot string so future runs can diff against it.
- Queue batch processing is sequential in the default handler pattern; if you parallelise with `Promise.all`, assert call counts rather than call order.
- `env.DLQ.send` returns a `Promise<void>`; always `await` it in production code or errors will be silently swallowed.

---

## Verification

```bash
# Run all queue consumer tests
npx vitest run src/index.test.ts

# Update inline snapshots after intentional output changes
npx vitest run --update-snapshots src/index.test.ts

# Coverage report
npx vitest run --coverage src/index.test.ts
```

---

## Related
- `workers-vitest-env-bindings-mock-service.md`
- `workers-test-durable-object-alarm-vitest.md`

---

## Sources
- Cloudflare Queues consumer docs — https://developers.cloudflare.com/queues/reference/how-queues-works/
- Cloudflare Queues dead letter queues — https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- Vitest snapshot testing — https://vitest.dev/guide/snapshot.html
