# Pipes and Filters Pattern with Workers Queues Pipeline

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to process incoming events (user uploads, webhook payloads, log entries) through a multi-stage transformation pipeline where each stage can fail, retry, or scale independently. A monolithic handler grows too large and a single failure cascades across all processing steps.

---

## Context

The pipes-and-filters enterprise pattern maps cleanly onto Cloudflare Workers Queues: each filter stage is its own consumer Worker, and each pipe is a Queue. Messages flow from queue to queue via `env.NEXT_QUEUE.send()`, so each filter is independently deployable, scalable, and replaceable without touching adjacent stages. Cloudflare Queues provide at-least-once delivery with automatic retries, so transient failures in any stage do not lose messages. Dead-letter queues catch messages that exhaust retries, enabling targeted replay without re-processing already-successful stages. Because each Worker only knows about its input queue and its output queue, adding a new filter stage requires zero changes to upstream or downstream code.

---

## Schema / Config — wrangler.toml

```toml
# wrangler.toml (root — defines all four filter Workers and their queues)

[[queues.producers]]
queue = "raw-events"
binding = "RAW_QUEUE"

[[queues.producers]]
queue = "sanitised-events"
binding = "SANITISED_QUEUE"

[[queues.producers]]
queue = "enriched-events"
binding = "ENRICHED_QUEUE"

[[queues.producers]]
queue = "classified-events"
binding = "CLASSIFIED_QUEUE"

[[queues.producers]]
queue = "dead-letter"
binding = "DLQ"

# ── Filter 1: sanitise ──────────────────────────────────────────────
[[workers]]
name = "filter-sanitise"
main = "src/filters/sanitise.ts"

[[workers.queues.consumers]]
queue = "raw-events"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "dead-letter"

[[workers.queues.producers]]
queue = "sanitised-events"
binding = "NEXT_QUEUE"

# ── Filter 2: enrich ────────────────────────────────────────────────
[[workers]]
name = "filter-enrich"
main = "src/filters/enrich.ts"

[[workers.queues.consumers]]
queue = "sanitised-events"
max_batch_size = 50
max_batch_timeout = 10
max_retries = 3
dead_letter_queue = "dead-letter"

[[workers.queues.producers]]
queue = "enriched-events"
binding = "NEXT_QUEUE"

[[workers.kv_namespaces]]
binding = "GEO_CACHE"
id = "<kv-namespace-id>"

# ── Filter 3: classify ──────────────────────────────────────────────
[[workers]]
name = "filter-classify"
main = "src/filters/classify.ts"

[[workers.queues.consumers]]
queue = "enriched-events"
max_batch_size = 50
max_batch_timeout = 10
max_retries = 3
dead_letter_queue = "dead-letter"

[[workers.queues.producers]]
queue = "classified-events"
binding = "NEXT_QUEUE"

# ── Filter 4: store ─────────────────────────────────────────────────
[[workers]]
name = "filter-store"
main = "src/filters/store.ts"

[[workers.queues.consumers]]
queue = "classified-events"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 5
dead_letter_queue = "dead-letter"

[[workers.d1_databases]]
binding = "DB"
database_name = "events-db"
database_id = "<d1-database-id>"
```

---

## Implementation — shared message types

```typescript
// src/types.ts
export interface RawEvent {
  id: string;
  source: string;
  timestamp: number;
  payload: unknown;
}

export interface SanitisedEvent extends RawEvent {
  payload: Record<string, unknown>; // validated, stripped of PII keys
}

export interface EnrichedEvent extends SanitisedEvent {
  geo?: { country: string; region: string };
  userAgent?: string;
}

export interface ClassifiedEvent extends EnrichedEvent {
  category: "click" | "conversion" | "error" | "other";
  score: number;
}
```

---

## Filter Workers

```typescript
// src/filters/sanitise.ts
import type { RawEvent, SanitisedEvent } from "../types";

const PII_KEYS = new Set(["email", "phone", "ssn", "password", "credit_card"]);

function stripPii(obj: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(obj).filter(([k]) => !PII_KEYS.has(k.toLowerCase()))
  );
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export interface Env {
  NEXT_QUEUE: Queue<SanitisedEvent>;
}

export default {
  async queue(batch: MessageBatch<RawEvent>, env: Env): Promise<void> {
    const sends: Promise<void>[] = [];

    for (const msg of batch.messages) {
      const raw = msg.body;

      // Basic structural validation
      if (!raw.id || typeof raw.timestamp !== "number") {
        console.warn("[sanitise] dropping malformed message", raw);
        msg.ack(); // discard — do not retry
        continue;
      }

      const sanitised: SanitisedEvent = {
        ...raw,
        payload: isPlainObject(raw.payload) ? stripPii(raw.payload) : {},
      };

      sends.push(env.NEXT_QUEUE.send(sanitised));
      msg.ack();
    }

    await Promise.all(sends);
  },
};
```

```typescript
// src/filters/enrich.ts
import type { SanitisedEvent, EnrichedEvent } from "../types";

export interface Env {
  NEXT_QUEUE: Queue<EnrichedEvent>;
  GEO_CACHE: KVNamespace;
}

async function resolveGeo(
  ip: string,
  kv: KVNamespace
): Promise<{ country: string; region: string } | undefined> {
  const cached = await kv.get<{ country: string; region: string }>(ip, "json");
  if (cached) return cached;
  // In production, call an internal geo API; placeholder here.
  return undefined;
}

export default {
  async queue(batch: MessageBatch<SanitisedEvent>, env: Env): Promise<void> {
    const sends: Promise<void>[] = [];

    for (const msg of batch.messages) {
      const ev = msg.body;
      const ip = typeof ev.payload["ip"] === "string" ? ev.payload["ip"] : "";

      const geo = ip ? await resolveGeo(ip, env.GEO_CACHE) : undefined;
      const ua =
        typeof ev.payload["user_agent"] === "string"
          ? (ev.payload["user_agent"] as string)
          : undefined;

      const enriched: EnrichedEvent = { ...ev, geo, userAgent: ua };
      sends.push(env.NEXT_QUEUE.send(enriched));
      msg.ack();
    }

    await Promise.all(sends);
  },
};
```

```typescript
// src/filters/classify.ts
import type { EnrichedEvent, ClassifiedEvent } from "../types";

export interface Env {
  NEXT_QUEUE: Queue<ClassifiedEvent>;
}

function classify(
  ev: EnrichedEvent
): Pick<ClassifiedEvent, "category" | "score"> {
  const src = ev.source.toLowerCase();
  if (src.includes("error")) return { category: "error", score: 0.9 };
  if (src.includes("checkout")) return { category: "conversion", score: 0.8 };
  if (src.includes("click")) return { category: "click", score: 0.5 };
  return { category: "other", score: 0.1 };
}

export default {
  async queue(batch: MessageBatch<EnrichedEvent>, env: Env): Promise<void> {
    const sends: Promise<void>[] = [];

    for (const msg of batch.messages) {
      const classified: ClassifiedEvent = {
        ...msg.body,
        ...classify(msg.body),
      };
      sends.push(env.NEXT_QUEUE.send(classified));
      msg.ack();
    }

    await Promise.all(sends);
  },
};
```

```typescript
// src/filters/store.ts
import type { ClassifiedEvent } from "../types";

export interface Env {
  DB: D1Database;
}

export default {
  async queue(batch: MessageBatch<ClassifiedEvent>, env: Env): Promise<void> {
    const stmt = env.DB.prepare(
      `INSERT OR IGNORE INTO classified_events
         (id, source, timestamp, category, score, geo_country, payload_json)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    );

    const inserts = batch.messages.map((msg) => {
      const ev = msg.body;
      return stmt.bind(
        ev.id,
        ev.source,
        ev.timestamp,
        ev.category,
        ev.score,
        ev.geo?.country ?? null,
        JSON.stringify(ev.payload)
      );
    });

    await env.DB.batch(inserts);

    // Ack all after successful batch insert
    for (const msg of batch.messages) msg.ack();
  },
};
```

---

## Anti-patterns

- **Sending to next queue inside a loop without batching** — call `env.NEXT_QUEUE.sendBatch()` with an array of `MessageSendRequest` objects instead of individual `send()` calls to stay within rate limits and reduce round-trips.
- **Acking before the downstream send succeeds** — always `await` the downstream send (or collect promises) before calling `msg.ack()`; an early ack on a failed forward drops the message silently.
- **Sharing mutable module-scope state between filter stages** — each Worker instance is stateless; module-scope variables are per-isolate and per-invocation-batch only, not shared across concurrent consumers.
- **Using one mega-queue for all stages** — a single queue cannot independently scale or retry individual stages; keep one queue per pipe.

---

## Gotchas

- Cloudflare Queues deliver messages **at least once**; downstream stores must use `INSERT OR IGNORE` or idempotency keys to handle duplicate delivery.
- `max_batch_timeout` begins when the **first** message in a batch arrives, not when the batch fills; tune it relative to your expected message rate.
- Dead-letter queue messages carry the original body unchanged — include a correlation `id` in every event so you can trace which pipeline stage failed.
- `sendBatch()` accepts at most 256 messages and a total body size of 128 MB per call.

---

## Verification

```bash
# 1. Create the queues
wrangler queues create raw-events
wrangler queues create sanitised-events
wrangler queues create enriched-events
wrangler queues create classified-events
wrangler queues create dead-letter

# 2. Deploy all filter Workers
wrangler deploy --config wrangler.toml

# 3. Publish a test message to the head of the pipe
wrangler queues publish raw-events \
  --message '{"id":"test-1","source":"click","timestamp":1234567890,"payload":{"ip":"1.2.3.4","email":"pii@example.com"}}'

# 4. Confirm the message landed in D1 (PII stripped, category=click)
wrangler d1 execute events-db \
  --command "SELECT id, category, score, payload_json FROM classified_events WHERE id='test-1'"

# 5. Inspect dead-letter queue for any failures
wrangler queues list-messages dead-letter
```

---

## Related

- `event-store-workers-d1-append-only.md`
- `shared-nothing-workers-stateless-design.md`

---

## Sources

- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Enterprise Integration Patterns: Pipes and Filters — https://www.enterpriseintegrationpatterns.com/patterns/messaging/PipesAndFilters.html
