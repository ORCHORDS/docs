# Observer Pattern: Typed Event Bus in Durable Objects for Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Multiple Workers (or multiple logical components within one Worker) need to react to the same domain events—an order placed, a payment confirmed, a user deactivated—without the publisher knowing who the subscribers are. Hardcoding calls to each downstream service inside the event-producing handler creates tight coupling: adding a new subscriber means touching the producer, and a failing subscriber can block the entire request.

Classic signs:
- A single handler that calls 5–8 downstream services serially, most of which are "fire and forget"
- New feature requests always land as "just add a call inside `handleOrderCreated`"
- Tests for the order-creation path must mock every subscriber, even irrelevant ones
- A slow notification service times out and rolls back the order

---

## Context

The Observer (Publish-Subscribe) pattern decouples event producers from consumers. In the Cloudflare Workers model the natural host for a mutable subscriber registry is a **Durable Object**: it persists subscription state across requests, serialises concurrent subscribe/unsubscribe operations, and can fan out events to named Workers via Service Bindings or store them for downstream polling.

```
Producer Worker
  │
  ▼
EventBus DO (stores subscriptions, fans out via fetch or Queue)
  ├─► NotificationWorker (Service Binding)
  ├─► AuditWorker       (Service Binding)
  └─► AnalyticsWorker   (Service Binding)
```

The bus receives typed events, looks up registered subscribers for that event type, and dispatches to each concurrently with `Promise.allSettled` so one failing subscriber cannot block others.

---

## Durable Object: EventBus

```typescript
// src/event-bus.ts
import { DurableObject } from "cloudflare:workers";

export interface EventEnvelope<T = unknown> {
  type: string;
  payload: T;
  publishedAt: string; // ISO-8601
  id: string;          // idempotency key
}

interface Subscription {
  id: string;
  eventType: string;    // "*" = all events
  workerName: string;   // name of the Service Binding key on Env
  createdAt: string;
}

export class EventBus extends DurableObject {
  private subscriptions: Map<string, Subscription> = new Map();
  private loaded = false;

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    switch (`${request.method} ${url.pathname}`) {
      case "POST /subscribe":
        return this.handleSubscribe(request);
      case "DELETE /subscribe":
        return this.handleUnsubscribe(request);
      case "POST /publish":
        return this.handlePublish(request);
      case "GET /subscriptions":
        return this.handleList();
      default:
        return new Response("Not found", { status: 404 });
    }
  }

  private async load() {
    if (this.loaded) return;
    const stored = await this.ctx.storage.get<Subscription[]>("subscriptions");
    for (const sub of stored ?? []) {
      this.subscriptions.set(sub.id, sub);
    }
    this.loaded = true;
  }

  private async persist() {
    await this.ctx.storage.put("subscriptions", [...this.subscriptions.values()]);
  }

  private async handleSubscribe(request: Request): Promise<Response> {
    await this.load();
    const body = await request.json<Omit<Subscription, "id" | "createdAt">>();
    const sub: Subscription = {
      ...body,
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
    };
    this.subscriptions.set(sub.id, sub);
    await this.persist();
    return Response.json({ subscriptionId: sub.id }, { status: 201 });
  }

  private async handleUnsubscribe(request: Request): Promise<Response> {
    await this.load();
    const { subscriptionId } = await request.json<{ subscriptionId: string }>();
    this.subscriptions.delete(subscriptionId);
    await this.persist();
    return new Response(null, { status: 204 });
  }

  private async handlePublish(request: Request): Promise<Response> {
    await this.load();
    const env = this.env as Env;
    const envelope = await request.json<EventEnvelope>();

    const matched = [...this.subscriptions.values()].filter(
      (s) => s.eventType === "*" || s.eventType === envelope.type
    );

    const results = await Promise.allSettled(
      matched.map(async (sub) => {
        const binding = (env as Record<string, Fetcher>)[sub.workerName];
        if (!binding) throw new Error(`No binding for ${sub.workerName}`);
        const resp = await binding.fetch("https://internal/event", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(envelope),
        });
        if (!resp.ok) throw new Error(`Subscriber ${sub.workerName} returned ${resp.status}`);
      })
    );

    const failures = results
      .map((r, i) => (r.status === "rejected" ? { sub: matched[i].workerName, reason: (r as PromiseRejectedResult).reason?.message } : null))
      .filter(Boolean);

    return Response.json({
      dispatched: matched.length,
      failures,
    });
  }

  private async handleList(): Promise<Response> {
    await this.load();
    return Response.json([...this.subscriptions.values()]);
  }
}
```

---

## Env and Wrangler Configuration

```typescript
// src/types.ts
export interface Env {
  EVENT_BUS: DurableObjectNamespace;
  // Service bindings for subscribers
  NOTIFICATION_WORKER: Fetcher;
  AUDIT_WORKER: Fetcher;
  ANALYTICS_WORKER: Fetcher;
}
```

```toml
# wrangler.toml (excerpt)
[[durable_objects.bindings]]
name = "EVENT_BUS"
class_name = "EventBus"

[[services]]
binding = "NOTIFICATION_WORKER"
service = "notification-worker"

[[services]]
binding = "AUDIT_WORKER"
service = "audit-worker"

[[services]]
binding = "ANALYTICS_WORKER"
service = "analytics-worker"
```

---

## Producer Worker: Publishing an Event

```typescript
// src/worker.ts
import type { Env } from "./types";

function getBus(env: Env): DurableObjectStub {
  // Single global bus; shard by topic for high-throughput scenarios
  const id = env.EVENT_BUS.idFromName("global");
  return env.EVENT_BUS.get(id);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

    const order = await request.json<{ orderId: string; total: number }>();

    // Do the primary work (create in DB, charge payment, etc.)
    // ...

    // Publish — fire and forget, or await for confirmation
    const bus = getBus(env);
    const envelope = {
      type: "order.created",
      payload: order,
      publishedAt: new Date().toISOString(),
      id: crypto.randomUUID(),
    };

    // Use waitUntil so the response isn't blocked by fan-out latency
    const ctx = { waitUntil: (p: Promise<unknown>) => p } as ExecutionContext;
    ctx.waitUntil(
      bus.fetch("https://bus/publish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(envelope),
      })
    );

    return Response.json({ orderId: order.orderId, status: "created" }, { status: 201 });
  },
};
```

---

## Subscriber Worker Skeleton

```typescript
// src/notification-worker.ts
export default {
  async fetch(request: Request): Promise<Response> {
    if (request.url.endsWith("/event") && request.method === "POST") {
      const envelope = await request.json<{ type: string; payload: unknown }>();
      if (envelope.type === "order.created") {
        // send email / push notification
        console.log("Notifying about order:", JSON.stringify(envelope.payload));
      }
      return new Response(null, { status: 204 });
    }
    return new Response("Not found", { status: 404 });
  },
};
```

---

## Anti-patterns

- **Storing subscriber callback URLs instead of service binding names**: External HTTP callbacks introduce authentication complexity and network hops. Use Service Bindings for Workers-to-Workers calls within the same account.
- **Publishing synchronously inside a transaction**: A publish call inside a D1 transaction that subsequently rolls back will have already dispatched events. Publish only after the primary operation succeeds, or use the Outbox pattern.
- **One Durable Object instance for all events at high volume**: The DO serialises writes. For > ~100 publishes/second shard by event category (`EVENT_BUS.idFromName("order")`, `"payment"`, etc.).
- **Swallowing `Promise.allSettled` failures silently**: Always log failures and expose them in the publish response. Consider a dead-letter Queue for persistently failing subscribers.
- **Unbounded subscription growth**: Add a maximum subscription count per event type and TTL cleanup; otherwise a subscription leak accumulates stale entries.

---

## Gotchas

- The Durable Object `fetch` handler must be exported as a named class export and registered in `wrangler.toml`; forgetting the `[[durable_objects.migrations]]` section causes a 500 on the first request.
- `Promise.allSettled` never rejects; always inspect each `result.status`. Use `Promise.all` only if you want a single failure to abort all fan-out (rarely correct for observers).
- Service Bindings require both workers to be deployed in the same account and the binding to be declared in `wrangler.toml`; local `wrangler dev --service-binding` flags are needed for local development.
- The in-memory `subscriptions` Map is rebuilt from storage on the first request after a cold start (`loaded = false`). This adds one storage read per DO activation; consider caching in DO memory with a TTL if the subscription list is large and stable.
- `waitUntil` is only available on the `ExecutionContext` passed to the `fetch` handler. Do not call it from inside a Durable Object's own `fetch`—the DO has its own lifecycle.

---

## Verification

1. Subscribe two workers (`NOTIFICATION_WORKER`, `AUDIT_WORKER`) to `"order.created"` via `POST /subscribe`.
2. Publish an `"order.created"` event and verify the response shows `dispatched: 2, failures: []`.
3. Stop one subscriber (return 500) and verify `failures` contains exactly one entry while the other subscriber still received the event.
4. Unsubscribe one worker and verify the next publish shows `dispatched: 1`.
5. Publish an `"unmatched.event"` and verify `dispatched: 0` for a subscriber registered for `"order.created"` only.

---

## Related

- `outbox-pattern-d1-reliable-publishing.md` — guarantee-at-least-once delivery before publishing
- `saga-pattern-multi-step-workers.md` — coordinating multi-step flows triggered by events
- `distributed-lock-durable-objects.md` — preventing concurrent fan-out for the same event ID
- `dead-letter-queue-pattern.md` — capturing persistently failing subscriber deliveries

---

## Sources

- Gamma et al. — Design Patterns: Elements of Reusable Object-Oriented Software (1994): Observer
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Cloudflare Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- `Promise.allSettled` MDN: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/allSettled
