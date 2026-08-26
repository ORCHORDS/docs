# Message Fan-out with Cloudflare Queues

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

An API endpoint or Worker needs to trigger multiple downstream actions (send email, update analytics, index into search, notify Slack) without blocking the HTTP response. A monolithic handler becomes brittle and slow. You need reliable async fan-out where each action can fail independently without affecting the others.

## Context

Cloudflare Queues is a durable, at-least-once message queue built into the Workers platform. A producer Worker (or Pages Function) calls `env.QUEUE.send()` and returns immediately. One or more consumer Workers process messages in batches asynchronously. Queues integrate natively with Workers — no external broker, no VPC peering, no connection strings.

Fan-out pattern approaches:
1. **Single queue, single consumer, internal routing** — consumer inspects `message.body.type` and dispatches internally. Simple but sequential within a batch.
2. **Multiple queues, dedicated consumers** — producer routes messages to different queues by type. Each consumer handles one concern. True parallel fan-out.
3. **Broadcast via multiple `send()` calls** — producer sends the same payload to N queues in parallel. Each consumer gets exactly one copy.

This article covers approach 3 (true parallel fan-out) with approach 1 as a fallback.

## Solution

### 1. wrangler.toml: Multiple Queues

```toml
# wrangler.toml
name = "producer-worker"
main = "src/producer.ts"
compatibility_date = "2024-09-23"

# Producer sends to all fan-out queues
[[queues.producers]]
binding = "EMAIL_QUEUE"
queue = "user-events-email"

[[queues.producers]]
binding = "ANALYTICS_QUEUE"
queue = "user-events-analytics"

[[queues.producers]]
binding = "SEARCH_INDEX_QUEUE"
queue = "user-events-search"

[[queues.producers]]
binding = "DEAD_LETTER_QUEUE"
queue = "user-events-dlq"
```

```toml
# wrangler.email-consumer.toml — separate Worker for email
name = "email-consumer"
main = "src/consumers/email.ts"
compatibility_date = "2024-09-23"

[[queues.consumers]]
queue = "user-events-email"
max_batch_size = 10          # Messages per batch
max_batch_timeout = 5       # Seconds to wait before delivering a partial batch
max_retries = 3             # Retry attempts before DLQ
dead_letter_queue = "user-events-dlq"
max_concurrency = 5         # Parallel batch invocations
```

### 2. Create Queues via CLI

```bash
npx wrangler queues create user-events-email
npx wrangler queues create user-events-analytics
npx wrangler queues create user-events-search
npx wrangler queues create user-events-dlq
```

### 3. TypeScript Types

```typescript
// src/types.ts
export type EventType = 'user.created' | 'user.updated' | 'user.deleted' | 'order.placed';

export interface UserEvent {
  type: EventType;
  userId: string;
  payload: Record<string, unknown>;
  timestamp: string;
  traceId: string;
}

export interface ProducerEnv {
  EMAIL_QUEUE: Queue<UserEvent>;
  ANALYTICS_QUEUE: Queue<UserEvent>;
  SEARCH_INDEX_QUEUE: Queue<UserEvent>;
}

export interface ConsumerEnv {
  // Consumer-specific bindings (DB, KV, etc.)
  DB: D1Database;
}
```

### 4. Producer Worker: Fan-out Send

```typescript
// src/producer.ts
import type { ProducerEnv, UserEvent } from './types';
import { crypto } from 'cloudflare:runtime';

export default {
  async fetch(request: Request, env: ProducerEnv): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/users') {
      return Response.json({ error: 'Not found' }, { status: 404 });
    }

    const body = await request.json<{ name: string; email: string }>();
    const userId = crypto.randomUUID();

    // Simulate DB insert (abbreviated)
    // await env.DB.prepare('INSERT INTO users ...').bind(...).run();

    const event: UserEvent = {
      type: 'user.created',
      userId,
      payload: { name: body.name, email: body.email },
      timestamp: new Date().toISOString(),
      traceId: crypto.randomUUID(),
    };

    // Fan-out: send to all queues in parallel — one failure does not block others
    const results = await Promise.allSettled([
      env.EMAIL_QUEUE.send(event, { contentType: 'json' }),
      env.ANALYTICS_QUEUE.send(event, { contentType: 'json' }),
      env.SEARCH_INDEX_QUEUE.send(event, { contentType: 'json' }),
    ]);

    const failures = results.filter((r) => r.status === 'rejected');
    if (failures.length > 0) {
      console.error('Queue send failures:', failures);
      // Do not fail the HTTP response — some messages were queued successfully
    }

    return Response.json({ userId }, { status: 201 });
  },
};
```

### 5. Email Consumer: Batch Handler

```typescript
// src/consumers/email.ts
import type { ConsumerEnv, UserEvent } from '../types';

export default {
  async queue(
    batch: MessageBatch<UserEvent>,
    env: ConsumerEnv
  ): Promise<void> {
    // Process each message; ack individually for partial-batch success
    for (const message of batch.messages) {
      try {
        await handleEmailEvent(message.body, env);
        message.ack();  // Remove from queue permanently
      } catch (err) {
        console.error(`Email handler failed for ${message.id}:`, err);
        // message.retry() is the default on uncaught throw;
        // call explicitly to retry with custom delay:
        message.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function handleEmailEvent(event: UserEvent, env: ConsumerEnv): Promise<void> {
  if (event.type === 'user.created') {
    // Send welcome email via Email Routing or external provider
    console.log(`Sending welcome email to user ${event.userId}`);
    // await sendEmail({ to: event.payload.email, template: 'welcome', ... });
  }
  // Ignore other event types — silently ack them
}
```

### 6. Analytics Consumer: Batch-optimised Handler

```typescript
// src/consumers/analytics.ts
import type { ConsumerEnv, UserEvent } from '../types';

export default {
  async queue(
    batch: MessageBatch<UserEvent>,
    env: ConsumerEnv
  ): Promise<void> {
    // Collect all messages and write in bulk for efficiency
    const events = batch.messages.map((m) => m.body);

    try {
      await bulkInsertAnalytics(events, env);
      // Ack the entire batch at once
      batch.ackAll();
    } catch (err) {
      console.error('Bulk analytics insert failed:', err);
      // Retry the entire batch
      batch.retryAll();
    }
  },
};

async function bulkInsertAnalytics(
  events: UserEvent[],
  env: ConsumerEnv
): Promise<void> {
  const stmts = events.map((e) =>
    env.DB.prepare(
      'INSERT INTO analytics_events (event_type, user_id, payload, created_at) VALUES (?1, ?2, ?3, ?4)'
    ).bind(e.type, e.userId, JSON.stringify(e.payload), e.timestamp)
  );
  await env.DB.batch(stmts);
}
```

### 7. Dead Letter Queue Consumer

```typescript
// src/consumers/dlq.ts
// Deployed as a separate Worker consuming user-events-dlq
export default {
  async queue(batch: MessageBatch<unknown>): Promise<void> {
    for (const message of batch.messages) {
      // Log, alert, or store for manual inspection
      console.error('DLQ message received:', {
        id: message.id,
        timestamp: message.timestamp,
        attempts: message.attempts,
        body: message.body,
      });
      // Always ack DLQ messages — retrying from DLQ is a manual operation
      message.ack();
    }
  },
};
```

### 8. Monitor Queue Depth via Analytics Engine

```typescript
// src/monitoring.ts — write metrics from consumer
import type { AnalyticsEngineDataset } from '@cloudflare/workers-types';

interface MonitoringEnv extends ConsumerEnv {
  ANALYTICS: AnalyticsEngineDataset;
}

export function recordQueueMetrics(
  env: MonitoringEnv,
  queueName: string,
  batchSize: number,
  processingMs: number,
  failureCount: number
): void {
  env.ANALYTICS.writeDataPoint({
    blobs: [queueName, failureCount > 0 ? 'partial_failure' : 'success'],
    doubles: [batchSize, processingMs, failureCount],
    indexes: [queueName],
  });
}
```

```sql
-- Query queue throughput in Workers Analytics Engine SQL API
SELECT
  blob1 AS queue_name,
  SUM(double1) AS total_messages,
  AVG(double2) AS avg_processing_ms,
  SUM(double3) AS total_failures,
  toStartOfHour(timestamp) AS hour
FROM analytics_events
GROUP BY queue_name, hour
ORDER BY hour DESC;
```

## Implementation Details

**At-least-once delivery:** Queues guarantee at-least-once delivery. Design consumers to be idempotent — use the message `id` as an idempotency key when writing to external systems.

**Batch tuning:** `max_batch_size` (1–10000) and `max_batch_timeout` (0–30 s) trade latency for throughput. Low latency requirements: small batch size and timeout. High throughput: larger batch, longer timeout.

**max_concurrency:** Controls how many concurrent consumer invocations Queues will run for one queue. Default is uncapped. Set it to prevent overwhelming downstream services.

**Message size limit:** Each message body is limited to 128 KB. For large payloads, store the data in R2 or D1 and send only a reference ID in the queue message.

**Delay delivery:** `queue.send(msg, { delaySeconds: N })` schedules a message to be delivered at least N seconds in the future (max 12 hours). Useful for scheduled reminders or debounce patterns.

## Anti-patterns

- Do not use `batch.retryAll()` when only a subset of messages failed — it re-processes already-successful messages, causing duplicates unless handlers are idempotent.
- Do not call `message.ack()` before the side effect is confirmed complete — a crash after ack but before the DB write loses the message.
- Do not fan out into a single queue and rely on the consumer to route — separate queues give independent retry and DLQ policies per concern.
- Do not send large binary blobs as message bodies — send an R2 object key and fetch in the consumer.

## Gotchas

- Queues consumers run in a separate Worker deployment from the producer. They must be deployed and configured independently via their own `wrangler.toml`.
- The `queue()` handler does not have a `request` object — it receives `MessageBatch` and the `env` bindings of the **consumer** Worker, not the producer.
- Messages that exceed `max_retries` without ack are moved to the DLQ. If no DLQ is configured they are dropped silently.
- `wrangler dev` simulates queues locally but does not persist messages between restarts.

## Verification

```bash
# List queues
npx wrangler queues list

# Check consumer configuration
npx wrangler queues consumer list user-events-email

# Send a test message manually
npx wrangler queues send user-events-email \
  --body='{"type":"user.created","userId":"test-1","payload":{},"timestamp":"2026-08-24T00:00:00Z","traceId":"abc"}'

# Tail consumer logs
npx wrangler tail --env production email-consumer

# Monitor DLQ accumulation
npx wrangler queues consumer list user-events-dlq
```

## Related

- `workers-workflows-durable-execution.md` — durable multi-step processing triggered by a queue message
- `workers-vectorize-semantic-search.md` — async document indexing triggered by a queue
- Queues docs: https://developers.cloudflare.com/queues/

## Sources

- https://developers.cloudflare.com/queues/get-started/
- https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- https://developers.cloudflare.com/queues/reference/batching-retries/
