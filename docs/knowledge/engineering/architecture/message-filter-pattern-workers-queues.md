# Message Filter Pattern — Workers & Queues

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A Queue consumer receives every event published to a topic, but only a subset are relevant to a downstream service. Processing irrelevant messages wastes CPU, inflates costs, and couples consumers to producer schemas. The Message Filter pattern intercepts messages before they reach business logic and discards those that do not match a declared predicate.

---

## Context

Cloudflare Queues deliver messages to a Worker consumer. There is no broker-side filter (unlike SNS filter policies). Filtering must happen in the consumer code before the message reaches any handler. Two variants exist:

- **Drop filter**: acknowledge and discard non-matching messages so they are not retried.
- **Route filter**: forward matching messages to sub-consumers via service bindings or additional queues; non-matching messages are acknowledged without further action.

The filter predicate should be a pure function to remain testable without infrastructure.

---

## Filter Predicate (Pure, Typed)

```typescript
// src/filters/OrderEventFilter.ts
export interface QueueMessage<T = unknown> {
  type: string;
  tenantId: string;
  payload: T;
}

export type FilterPredicate<T> = (msg: QueueMessage<T>) => boolean;

// Only process order events for paying tenants in the EU region
export const euPayingOrderFilter: FilterPredicate<unknown> = (msg) =>
  msg.type.startsWith("order.") &&
  msg.tenantId !== "demo" &&
  (msg.payload as Record<string, unknown>)["region"] === "EU";
```

---

## Filtered Consumer Worker

```typescript
// src/consumers/filteredOrderConsumer.ts
import type { MessageBatch, Queue } from "@cloudflare/workers-types";
import { euPayingOrderFilter, type QueueMessage } from "../filters/OrderEventFilter";
import { processOrderEvent } from "../handlers/orderHandler";

export interface Env {
  DEAD_LETTER_QUEUE: Queue;
}

export default {
  async queue(batch: MessageBatch<QueueMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const body = message.body;

      if (!euPayingOrderFilter(body)) {
        // Acknowledge immediately — not an error, just not relevant to this consumer
        message.ack();
        continue;
      }

      try {
        await processOrderEvent(body);
        message.ack();
      } catch (err) {
        // Send to DLQ on processing failure; do not ack (Queue retries)
        await env.DEAD_LETTER_QUEUE.send({ original: body, error: String(err) });
        message.ack(); // ack after DLQ send to prevent infinite retry loop
      }
    }
  },
};
```

---

## Composable Filter Pipeline

```typescript
// src/filters/filterPipeline.ts
export function composeFilters<T>(
  ...predicates: Array<(msg: T) => boolean>
): (msg: T) => boolean {
  return (msg: T) => predicates.every((p) => p(msg));
}

// Usage
import { euPayingOrderFilter } from "./OrderEventFilter";

const hasValidSchema = (msg: QueueMessage): boolean =>
  typeof msg.type === "string" && typeof msg.tenantId === "string";

const isNotReplay = (msg: QueueMessage): boolean =>
  (msg.payload as Record<string, unknown>)["replay"] !== true;

export const orderFilter = composeFilters(hasValidSchema, isNotReplay, euPayingOrderFilter);
```

---

## Content-Based Router with Filter (Fan-Out)

```typescript
// src/consumers/routingConsumer.ts — routes to downstream queues based on message type
import type { MessageBatch, Queue } from "@cloudflare/workers-types";

export interface Env {
  ORDERS_QUEUE: Queue;
  PAYMENTS_QUEUE: Queue;
  INVENTORY_QUEUE: Queue;
}

const ROUTE_MAP: Record<string, keyof Env> = {
  "order.placed":     "ORDERS_QUEUE",
  "order.shipped":    "ORDERS_QUEUE",
  "payment.captured": "PAYMENTS_QUEUE",
  "stock.reserved":   "INVENTORY_QUEUE",
};

export default {
  async queue(batch: MessageBatch<{ type: string; [k: string]: unknown }>, env: Env): Promise<void> {
    const sends: Promise<void>[] = [];

    for (const message of batch.messages) {
      const destination = ROUTE_MAP[message.body.type];

      if (!destination) {
        // No route — silently ack (drop filter)
        message.ack();
        continue;
      }

      sends.push(
        env[destination].send(message.body).then(() => message.ack())
      );
    }

    await Promise.all(sends);
  },
};
```

---

## Schema Validation Filter (Zod)

```typescript
// src/filters/schemaFilter.ts
import { z } from "zod";

const OrderPlacedSchema = z.object({
  type: z.literal("order.placed"),
  tenantId: z.string().min(1),
  payload: z.object({
    orderId: z.string().uuid(),
    total: z.number().positive(),
    region: z.string(),
  }),
});

export function makeSchemaFilter<T extends z.ZodTypeAny>(schema: T) {
  return (msg: unknown): msg is z.infer<T> => schema.safeParse(msg).success;
}

export const isValidOrderPlaced = makeSchemaFilter(OrderPlacedSchema);

// In consumer:
// if (!isValidOrderPlaced(message.body)) { message.ack(); continue; }
```

---

## Anti-patterns

- **Nacking instead of acking filtered messages**: calling `message.retry()` on non-matching messages causes infinite retry loops; always `ack()` discards.
- **Filtering inside business logic**: embedding `if (msg.type !== "order.placed") return` inside domain handlers couples infrastructure concerns to domain code.
- **Throwing on filter mismatch**: uncaught exceptions on mismatched messages put them back in the queue; filters must be non-throwing or wrapped in try/catch.
- **Stateful filter predicates**: predicates that call external services (e.g., checking feature flags per message) become bottlenecks; cache flags in KV or pass as constructor arguments.

---

## Gotchas

- **Batch partial failures**: Cloudflare Queues require either `batch.ackAll()` / `batch.retryAll()` or per-message `ack()`/`retry()`. Mixing per-message acks with `batch.ackAll()` has undefined semantics — pick one strategy per consumer.
- **Message ordering**: Queues do not guarantee order across batches; a filter relying on "the previous message set state X" will behave incorrectly.
- **Filter cost**: every message incurs CPU for the filter predicate even if discarded; minimize predicate cost (avoid JSON.parse if the type field is a top-level key already deserialized).
- **Dead-letter coupling**: routing to a DLQ with `message.ack()` means the original Queue will not retry; ensure the DLQ consumer handles retries independently.

---

## Verification

```typescript
// test/orderEventFilter.test.ts
import { describe, it, expect } from "vitest";
import { euPayingOrderFilter } from "../src/filters/OrderEventFilter";

describe("euPayingOrderFilter", () => {
  it("passes EU paying order events", () => {
    expect(euPayingOrderFilter({ type: "order.placed", tenantId: "acme", payload: { region: "EU" } })).toBe(true);
  });

  it("rejects demo tenants", () => {
    expect(euPayingOrderFilter({ type: "order.placed", tenantId: "demo", payload: { region: "EU" } })).toBe(false);
  });

  it("rejects non-EU orders", () => {
    expect(euPayingOrderFilter({ type: "order.placed", tenantId: "acme", payload: { region: "US" } })).toBe(false);
  });

  it("rejects non-order event types", () => {
    expect(euPayingOrderFilter({ type: "payment.captured", tenantId: "acme", payload: { region: "EU" } })).toBe(false);
  });
});
```

---

## Related

- `message-translator-workers-queues.md` — transforming message schemas before processing
- `dead-letter-queue-architecture.md` — DLQ handling for unroutable messages
- `event-bridge-pattern-workers-queues-routing.md` — rule-based routing across queues
- `poison-pill-message-handling-workers-queues.md` — handling malformed messages
- `competing-consumers-queues.md` — parallel consumer workers on the same queue

---

## Sources

- Hohpe, G. & Woolf, B. (2003). *Enterprise Integration Patterns*. Addison-Wesley. Ch. 8 — Message Filter
- Cloudflare Queues documentation — per-message ack/retry semantics
- Cloudflare Queues batch consumer API reference
