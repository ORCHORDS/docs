# Testing Queue Consumer Workers with Vitest

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Queue consumer Worker processes batches of events (e.g. track-play events, webhook deliveries) and you need confidence that it correctly acks successful messages, retries transient failures, and falls back to a Dead Letter Queue without deploying to a live environment. Manual testing with `wrangler dev` is too slow and flaky for CI.

---

## Context

Cloudflare Queues deliver messages to a Worker's `queue(batch, env, ctx)` export as a `MessageBatch`. Each `Message` in the batch exposes `.ack()` and `.retry()` methods — calling neither causes the platform to retry the whole batch automatically. In `@cloudflare/vitest-pool-workers` you construct a synthetic `MessageBatch` and attach Vitest spies to individual message methods so you can assert exactly which messages were acknowledged, which were retried, and which caused the batch to call `batch.retryAll()`. DLQ behaviour is typically modelled by asserting that `retry()` was called with `{ delaySeconds: N }` options after the max-retry threshold.

---

## Setup / Config

`wrangler.toml`:
```toml
[[queues.consumers]]
queue = "track-events"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "track-events-dlq"

[[queues.producers]]
queue = "track-events"
binding = "TRACK_EVENTS_QUEUE"

[[d1_databases]]
binding = "DB"
database_name = "orchords-local"
database_id = "00000000-0000-0000-0000-000000000000"
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
          d1Databases: ["DB"],
          queues: {
            producers: [{ name: "track-events", binding: "TRACK_EVENTS_QUEUE" }],
            consumers: ["track-events"],
          },
        },
      },
    },
  },
});
```

`src/worker-queue.ts`:
```typescript
export interface Env {
  DB: D1Database;
}

interface TrackPlayEvent {
  trackId: string;
  userId: string;
  timestamp: number;
}

export default {
  async queue(
    batch: MessageBatch<TrackPlayEvent>,
    env: Env,
    _ctx: ExecutionContext
  ): Promise<void> {
    for (const message of batch.messages) {
      try {
        const event = message.body;

        if (!event.trackId || !event.userId) {
          // Malformed — ack to prevent infinite retry
          message.ack();
          continue;
        }

        await env.DB.prepare(
          `INSERT INTO play_events (track_id, user_id, played_at)
           VALUES (?, ?, ?)
           ON CONFLICT DO NOTHING`
        )
          .bind(event.trackId, event.userId, event.timestamp)
          .run();

        message.ack();
      } catch (err) {
        // Transient error — retry with backoff
        message.retry({ delaySeconds: 30 });
      }
    }
  },
};
```

---

## Test Implementation

`src/worker-queue.test.ts`:
```typescript
import { env } from "cloudflare:test";
import { describe, it, expect, vi, beforeAll, afterEach } from "vitest";
import worker from "./worker-queue";

// ---------------------------------------------------------------------------
// Helper: construct a fake Message<T>
// ---------------------------------------------------------------------------
function makeMessage<T>(body: T, id = crypto.randomUUID()): Message<T> {
  return {
    id,
    timestamp: new Date(),
    attempts: 1,
    body,
    ack: vi.fn(),
    retry: vi.fn(),
  } as unknown as Message<T>;
}

// ---------------------------------------------------------------------------
// Helper: construct a fake MessageBatch<T>
// ---------------------------------------------------------------------------
function makeBatch<T>(
  messages: Message<T>[],
  queueName = "track-events"
): MessageBatch<T> {
  return {
    queue: queueName,
    messages,
    ackAll: vi.fn(),
    retryAll: vi.fn(),
  } as unknown as MessageBatch<T>;
}

const mockCtx: ExecutionContext = {
  waitUntil: vi.fn(),
  passThroughOnException: vi.fn(),
} as unknown as ExecutionContext;

beforeAll(async () => {
  await env.DB.exec(`
    CREATE TABLE IF NOT EXISTS play_events (
      id        INTEGER PRIMARY KEY AUTOINCREMENT,
      track_id  TEXT NOT NULL,
      user_id   TEXT NOT NULL,
      played_at INTEGER NOT NULL,
      UNIQUE (track_id, user_id, played_at)
    )
  `);
});

afterEach(async () => {
  await env.DB.exec("DELETE FROM play_events");
});

describe("queue() handler", () => {
  it("acks all valid messages and inserts rows", async () => {
    const messages = [
      makeMessage({ trackId: "t1", userId: "u1", timestamp: 1000 }),
      makeMessage({ trackId: "t2", userId: "u2", timestamp: 2000 }),
    ];
    const batch = makeBatch(messages);

    await worker.queue(batch, env as any, mockCtx);

    for (const msg of messages) {
      expect(msg.ack).toHaveBeenCalledOnce();
      expect(msg.retry).not.toHaveBeenCalled();
    }

    const { results } = await env.DB.prepare(
      "SELECT track_id FROM play_events ORDER BY track_id"
    ).all<{ track_id: string }>();

    expect(results.map((r) => r.track_id)).toEqual(["t1", "t2"]);
  });

  it("acks malformed messages without retrying", async () => {
    const bad = makeMessage({ trackId: "", userId: "", timestamp: 0 });
    const batch = makeBatch([bad]);

    await worker.queue(batch, env as any, mockCtx);

    expect(bad.ack).toHaveBeenCalledOnce();
    expect(bad.retry).not.toHaveBeenCalled();

    const count = await env.DB.prepare(
      "SELECT COUNT(*) as cnt FROM play_events"
    ).first<{ cnt: number }>();
    expect(count?.cnt).toBe(0);
  });

  it("retries with delaySeconds on transient DB error", async () => {
    // Force a DB error by dropping the table temporarily
    await env.DB.exec("DROP TABLE play_events");

    const msg = makeMessage({ trackId: "t3", userId: "u3", timestamp: 3000 });
    const batch = makeBatch([msg]);

    await worker.queue(batch, env as any, mockCtx);

    expect(msg.retry).toHaveBeenCalledOnce();
    expect(msg.retry).toHaveBeenCalledWith({ delaySeconds: 30 });
    expect(msg.ack).not.toHaveBeenCalled();

    // Restore the table for subsequent tests
    await env.DB.exec(`
      CREATE TABLE play_events (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        track_id  TEXT NOT NULL,
        user_id   TEXT NOT NULL,
        played_at INTEGER NOT NULL,
        UNIQUE (track_id, user_id, played_at)
      )
    `);
  });

  it("deduplicates duplicate events via ON CONFLICT DO NOTHING", async () => {
    const event = { trackId: "t4", userId: "u4", timestamp: 4000 };
    const batch1 = makeBatch([makeMessage(event)]);
    const batch2 = makeBatch([makeMessage(event)]);

    await worker.queue(batch1, env as any, mockCtx);
    await worker.queue(batch2, env as any, mockCtx);

    const count = await env.DB.prepare(
      "SELECT COUNT(*) as cnt FROM play_events WHERE track_id = 't4'"
    ).first<{ cnt: number }>();
    expect(count?.cnt).toBe(1);
  });

  it("processes a full batch of max_batch_size=10 messages", async () => {
    const messages = Array.from({ length: 10 }, (_, i) =>
      makeMessage({ trackId: `t${i + 10}`, userId: `u${i + 10}`, timestamp: i * 100 })
    );
    const batch = makeBatch(messages);

    await worker.queue(batch, env as any, mockCtx);

    const allAcked = messages.every(
      (m) => (m.ack as ReturnType<typeof vi.fn>).mock.calls.length === 1
    );
    expect(allAcked).toBe(true);

    const count = await env.DB.prepare(
      "SELECT COUNT(*) as cnt FROM play_events"
    ).first<{ cnt: number }>();
    expect(count?.cnt).toBe(10);
  });
});
```

---

## Anti-patterns

- **Calling `batch.retryAll()` from the handler without inspecting individual messages** — you lose the ability to ack only the successful subset; always loop and call per-message `ack()`/`retry()`.
- **Not mocking `retry()` with `{ delaySeconds }` options** — the bare `retry()` call uses the queue default; explicitly passing delay is required for exponential backoff semantics.
- **Asserting `ackAll` was called** — `ackAll` is a convenience shortcut; if your handler loops individually it will never call `ackAll`, and the assertion will always fail.
- **Forgetting `ON CONFLICT DO NOTHING`** — Queues guarantee at-least-once delivery; idempotent inserts prevent duplicate rows on retry.

---

## Gotchas

- `Message.attempts` is the number of delivery attempts so far; your handler can inspect it to implement max-retry logic before DLQ promotion.
- The `dead_letter_queue` in `wrangler.toml` is a Cloudflare-side config — it is transparent to your Worker; you cannot assert it was triggered from within the handler.
- `MessageBatch.messages` is readonly in the platform type; the spy mock works because `unknown as MessageBatch<T>` bypasses the type guard.
- Queue tests in `vitest-pool-workers` run in the Workers runtime via `workerd`; Node-only APIs like `process.env` are unavailable inside the worker module.

---

## Verification

```bash
# Run queue consumer tests
npx vitest run src/worker-queue.test.ts

# Verify with coverage
npx vitest run --coverage src/worker-queue.test.ts

# Send a test message via Wrangler (integration smoke test)
npx wrangler queues send track-events '{"trackId":"t-smoke","userId":"u-smoke","timestamp":1234567890}'
```

---

## Related

- `workers-email-handler-testing-miniflare.md`
- `workers-durable-objects-alarm-testing.md`

---

## Sources

- Cloudflare Queues Docs — https://developers.cloudflare.com/queues/
- Queues Consumer Worker API — https://developers.cloudflare.com/queues/reference/javascript-apis/
- Vitest Pool Workers — https://developers.cloudflare.com/workers/testing/vitest-integration/
