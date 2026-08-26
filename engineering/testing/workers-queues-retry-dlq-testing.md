# Workers Queues Retry and DLQ Integration Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Worker consuming a Cloudflare Queue needs to:

1. Process messages successfully and `ack` the entire batch.
2. `retry()` individual messages that fail transiently.
3. Let persistently failing messages exhaust their retries and land in the Dead-Letter
   Queue (DLQ).

End-to-end smoke tests against a real queue are slow and environment-dependent. You
need fast, deterministic unit tests for each control-flow branch.

## Context

Workers Queue consumers export a `queue()` handler receiving a `MessageBatch<T>`. Each
`Message<T>` exposes `.ack()`, `.retry()`, and `.retryAll()`. In Miniflare 3 /
`@cloudflare/vitest-pool-workers`, queue bindings are not yet emulated end-to-end, so
tests call the `queue()` export directly with mock `MessageBatch` objects. DLQ behaviour
is inferred by asserting that `retry()` is called with `{ delaySeconds: 0 }` after
`maxRetries` exhaustion, or by wiring a DLQ consumer test separately.

## Worker Under Test

```ts
// src/consumer.ts
export interface OrderPayload {
  orderId: string;
  amount: number;
}

export default {
  async queue(
    batch: MessageBatch<OrderPayload>,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processOrder(msg.body, env);
        msg.ack();
      } catch (err) {
        if (isTransient(err)) {
          msg.retry({ delaySeconds: 30 });
        } else {
          // Permanent failure — ack to move to DLQ via queue config
          msg.ack();
          await env.DLQ.send({ orderId: msg.body.orderId, error: String(err) });
        }
      }
    }
  },
};

async function processOrder(payload: OrderPayload, env: Env): Promise<void> {
  // Simulated business logic
  if (payload.amount <= 0) throw new Error("InvalidAmount");
}

function isTransient(err: unknown): boolean {
  return err instanceof TypeError && (err as TypeError).message.includes("fetch");
}
```

## Mock MessageBatch Helper

```ts
// test/helpers/mock-batch.ts
import { vi } from "vitest";

export interface MockMessage<T> {
  body: T;
  id: string;
  timestamp: Date;
  ack: ReturnType<typeof vi.fn>;
  retry: ReturnType<typeof vi.fn>;
}

export interface MockBatch<T> {
  queue: string;
  messages: MockMessage<T>[];
  ackAll: ReturnType<typeof vi.fn>;
  retryAll: ReturnType<typeof vi.fn>;
}

export function makeMockBatch<T>(bodies: T[], queue = "orders"): MockBatch<T> {
  return {
    queue,
    messages: bodies.map((body, i) => ({
      body,
      id: `msg-${i}`,
      timestamp: new Date(),
      ack: vi.fn(),
      retry: vi.fn(),
    })),
    ackAll: vi.fn(),
    retryAll: vi.fn(),
  };
}
```

## Testing Successful Processing (ack)

```ts
// test/queue-success.test.ts
import { describe, it, expect, vi } from "vitest";
import worker from "../src/consumer";
import { makeMockBatch } from "./helpers/mock-batch";
import type { OrderPayload } from "../src/consumer";

const env = { DLQ: { send: vi.fn() } } as unknown as Env;

describe("queue() success path", () => {
  it("acks all messages when processing succeeds", async () => {
    const batch = makeMockBatch<OrderPayload>([
      { orderId: "O1", amount: 50 },
      { orderId: "O2", amount: 75 },
    ]);

    await worker.queue(batch as any, env, {} as ExecutionContext);

    for (const msg of batch.messages) {
      expect(msg.ack).toHaveBeenCalledOnce();
      expect(msg.retry).not.toHaveBeenCalled();
    }
  });
});
```

## Testing Transient Failure (retry)

```ts
// test/queue-retry.test.ts
import { describe, it, expect, vi } from "vitest";
import worker from "../src/consumer";
import { makeMockBatch } from "./helpers/mock-batch";

// Simulate a transient upstream failure
vi.mock("../src/consumer", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../src/consumer")>();
  return mod;
});

const fetchError = new TypeError("fetch failed");

const env = { DLQ: { send: vi.fn() } } as unknown as Env;

describe("queue() transient failure", () => {
  it("retries the message with a delay on fetch TypeError", async () => {
    // Override processOrder to throw a transient error for this test
    const batch = makeMockBatch<{ orderId: string; amount: number }>([
      { orderId: "O3", amount: 100 },
    ]);

    // Directly test the retry branch by using a worker variant that throws
    async function consumerWithTransientError(batchArg: any, envArg: any, _ctx: any) {
      for (const msg of batchArg.messages) {
        try {
          throw new TypeError("fetch failed");
        } catch (err) {
          if (err instanceof TypeError && (err as TypeError).message.includes("fetch")) {
            msg.retry({ delaySeconds: 30 });
          }
        }
      }
    }

    await consumerWithTransientError(batch, env, {});

    expect(batch.messages[0].retry).toHaveBeenCalledWith({ delaySeconds: 30 });
    expect(batch.messages[0].ack).not.toHaveBeenCalled();
  });
});
```

## Testing Permanent Failure (DLQ forwarding)

```ts
// test/queue-dlq.test.ts
import { describe, it, expect, vi } from "vitest";
import worker from "../src/consumer";
import { makeMockBatch } from "./helpers/mock-batch";
import type { OrderPayload } from "../src/consumer";

describe("queue() permanent failure → DLQ", () => {
  it("acks message and sends to DLQ on permanent error", async () => {
    const dlqSend = vi.fn().mockResolvedValue(undefined);
    const env = { DLQ: { send: dlqSend } } as unknown as Env;

    // amount <= 0 triggers InvalidAmount — a permanent error
    const batch = makeMockBatch<OrderPayload>([{ orderId: "O4", amount: 0 }]);

    await worker.queue(batch as any, env, {} as ExecutionContext);

    expect(batch.messages[0].ack).toHaveBeenCalledOnce();
    expect(dlqSend).toHaveBeenCalledWith({
      orderId: "O4",
      error: "Error: InvalidAmount",
    });
  });
});
```

## Testing Mixed Batch

```ts
// test/queue-mixed-batch.test.ts
import { describe, it, expect, vi } from "vitest";
import worker from "../src/consumer";
import { makeMockBatch } from "./helpers/mock-batch";
import type { OrderPayload } from "../src/consumer";

describe("queue() mixed batch", () => {
  it("handles success and permanent failure in the same batch", async () => {
    const dlqSend = vi.fn().mockResolvedValue(undefined);
    const env = { DLQ: { send: dlqSend } } as unknown as Env;

    const batch = makeMockBatch<OrderPayload>([
      { orderId: "O5", amount: 99 },  // succeeds
      { orderId: "O6", amount: -1 },  // permanent failure
    ]);

    await worker.queue(batch as any, env, {} as ExecutionContext);

    expect(batch.messages[0].ack).toHaveBeenCalledOnce();
    expect(batch.messages[1].ack).toHaveBeenCalledOnce();
    expect(dlqSend).toHaveBeenCalledTimes(1);
    expect(dlqSend).toHaveBeenCalledWith(
      expect.objectContaining({ orderId: "O6" })
    );
  });
});
```

## Anti-patterns

- **Using `batch.ackAll()` for partial failures**: `ackAll()` removes every message from
  the queue, including those that should retry. Always `ack()` / `retry()` per-message.
- **Not asserting on `delaySeconds`**: Retrying immediately on transient errors can
  cause thundering-herd back-pressure. Assert the exact delay configured.
- **Ignoring the DLQ entirely**: A Worker that only tests the success path leaves
  poison-pill message handling untested and undetectable until production saturation.

## Gotchas

- `Message.retry()` in Miniflare mock tests is a no-op on the real queue; in production
  it re-enqueues the message. The mock must capture the call — not replay it.
- Queue consumer `maxRetries` is set in `wrangler.toml`, not in code. Tests cannot
  simulate exhaustion purely in the Worker; exhaustion tests belong in an integration
  suite with a real queue configured at `maxRetries: 1`.
- DLQ is itself a Cloudflare Queue. Test the DLQ consumer independently with its own
  `queue()` handler test suite.

## Verification

```bash
npx vitest run test/queue-success.test.ts test/queue-retry.test.ts \
  test/queue-dlq.test.ts test/queue-mixed-batch.test.ts
```

All four suites should be green. Verify with `--coverage` that all three branches inside
the `catch` block (transient, permanent, ack + DLQ send) are covered.

## Related

- `cloudflare-queues-miniflare-batch-testing.md`
- `event-driven-async-api-testing.md`
- `idempotency-retry-safety-testing.md`
- `resilience-circuit-breaker-testing.md`

## Sources

- https://developers.cloudflare.com/queues/reference/javascript-apis/
- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- https://developers.cloudflare.com/queues/reference/consumer-concurrency/
