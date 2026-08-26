# Scatter-Gather Aggregation with Workers and Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to fan out a single request into N independent sub-tasks, execute them in parallel, and return an aggregated result only when all N results are available. Examples include price-comparison across multiple suppliers, running the same prompt against several LLM providers, or sharding a large search query across regional indexes.

---

## Context

A Cloudflare Worker receives the initial request, generates a `correlationId`, and sends N messages to a Queue — one per sub-task. Each consumer Worker processes its assigned sub-task and writes its result to a D1 table with `INSERT OR IGNORE` keyed by `(correlationId, taskIndex)`, ensuring idempotency on retries. A polling endpoint queries `COUNT(*)` of completed results for the `correlationId` and returns the aggregated payload once all N results are present. A TTL column allows a Cron Worker to clean up stale incomplete gatherings.

---

## Schema — D1 Table

```sql
CREATE TABLE IF NOT EXISTS scatter_results (
  correlation_id TEXT    NOT NULL,
  task_index     INTEGER NOT NULL,
  result         TEXT    NOT NULL,  -- JSON
  created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (correlation_id, task_index)
);

CREATE TABLE IF NOT EXISTS scatter_meta (
  correlation_id TEXT    PRIMARY KEY,
  total_tasks    INTEGER NOT NULL,
  created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
  expires_at     TEXT    NOT NULL  -- ISO-8601
);

CREATE INDEX IF NOT EXISTS idx_scatter_meta_expires
  ON scatter_meta (expires_at);
```

---

## Wrangler Config

```toml
[[d1_databases]]
binding       = "DB"
database_name = "app-db"
database_id   = "<your-d1-database-id>"

[[queues.producers]]
binding    = "TASK_QUEUE"
queue_name = "scatter-tasks"

[[queues.consumers]]
queue             = "scatter-tasks"
max_batch_size    = 10
max_batch_timeout = 5

[triggers]
crons = ["0 * * * *"]  # hourly cleanup
```

---

## Implementation — Scatter Worker (publishes sub-tasks)

```typescript
// scatter-worker.ts
import { v4 as uuid } from 'uuid';

export interface Env {
  DB:         D1Database;
  TASK_QUEUE: Queue<TaskMessage>;
}

export interface TaskMessage {
  correlationId: string;
  taskIndex:     number;
  totalTasks:    number;
  input:         string; // e.g. a search keyword or supplier SKU
}

const TTL_MINUTES = 10;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'POST' && new URL(request.url).pathname === '/scatter') {
      return handleScatter(request, env);
    }
    if (request.method === 'GET' && new URL(request.url).pathname === '/gather') {
      return handleGather(request, env);
    }
    return new Response('Not found', { status: 404 });
  },

  // Cron: purge expired scatter_meta and their results
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await env.DB.prepare(
      `DELETE FROM scatter_results
       WHERE correlation_id IN (
         SELECT correlation_id FROM scatter_meta
         WHERE expires_at < datetime('now')
       )`
    ).run();
    await env.DB.prepare(
      `DELETE FROM scatter_meta WHERE expires_at < datetime('now')`
    ).run();
  },
};

async function handleScatter(request: Request, env: Env): Promise<Response> {
  const { inputs } = await request.json<{ inputs: string[] }>();

  if (!inputs?.length) {
    return Response.json({ error: '"inputs" array required' }, { status: 400 });
  }

  const correlationId = uuid();
  const totalTasks    = inputs.length;
  const expiresAt     = new Date(
    Date.now() + TTL_MINUTES * 60 * 1000
  ).toISOString();

  // Record the expected task count
  await env.DB.prepare(
    `INSERT INTO scatter_meta (correlation_id, total_tasks, expires_at)
     VALUES (?, ?, ?)`
  ).bind(correlationId, totalTasks, expiresAt).run();

  // Fan out to queue
  const messages: MessageSendRequest<TaskMessage>[] = inputs.map((input, i) => ({
    body: { correlationId, taskIndex: i, totalTasks, input },
    contentType: 'json',
  }));

  await env.TASK_QUEUE.sendBatch(messages);

  return Response.json({ correlationId, totalTasks }, { status: 202 });
}

async function handleGather(request: Request, env: Env): Promise<Response> {
  const correlationId = new URL(request.url).searchParams.get('correlationId');
  if (!correlationId) {
    return Response.json({ error: 'correlationId required' }, { status: 400 });
  }

  const meta = await env.DB.prepare(
    `SELECT total_tasks FROM scatter_meta WHERE correlation_id = ?`
  ).bind(correlationId).first<{ total_tasks: number }>();

  if (!meta) {
    return Response.json({ error: 'Unknown correlationId' }, { status: 404 });
  }

  const { results } = await env.DB.prepare(
    `SELECT task_index, result FROM scatter_results
     WHERE correlation_id = ?
     ORDER BY task_index ASC`
  ).bind(correlationId).all<{ task_index: number; result: string }>();

  if (results.length < meta.total_tasks) {
    return Response.json(
      { ready: false, completed: results.length, total: meta.total_tasks },
      { status: 202 }
    );
  }

  const aggregated = results.map((r) => JSON.parse(r.result));
  return Response.json({ ready: true, results: aggregated });
}
```

---

## Implementation — Consumer Worker (processes one sub-task)

```typescript
// consumer-worker.ts
import { TaskMessage } from './scatter-worker';

export interface Env {
  DB: D1Database;
}

export default {
  async queue(batch: MessageBatch<TaskMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const { correlationId, taskIndex, input } = message.body;

      try {
        // Replace with your real sub-task logic
        const result = await processSubTask(input);

        // INSERT OR IGNORE guarantees idempotency on retries
        await env.DB.prepare(
          `INSERT OR IGNORE INTO scatter_results
             (correlation_id, task_index, result)
           VALUES (?, ?, ?)`
        )
          .bind(correlationId, taskIndex, JSON.stringify(result))
          .run();

        message.ack();
      } catch (err) {
        console.error(`Task ${taskIndex} for ${correlationId} failed:`, err);
        message.retry();
      }
    }
  },
};

async function processSubTask(input: string): Promise<{ input: string; score: number }> {
  // Simulate work — replace with real API call / computation
  await scheduler.wait(Math.random() * 200);
  return { input, score: Math.random() };
}
```

---

## Anti-patterns

- **Polling in a tight loop from the client** — Instruct clients to poll with exponential back-off; tight loops hammer D1 read quota unnecessarily.
- **Storing large blobs in the `result` column** — D1 cells have a 1 MB limit per row; for large results write to R2 and store the R2 key.
- **Not recording `total_tasks` before sending** — If the consumer worker wins the race and inserts before `scatter_meta` exists, the gather endpoint incorrectly reports `totalTasks = 0`.
- **Missing `INSERT OR IGNORE`** — Without idempotency protection, a Queue retry from the consumer inserts a duplicate row and breaks the `COUNT(*)` check.

---

## Gotchas

- `max_batch_timeout` on the Queue consumer adds latency for the last message in a small batch; tune it relative to your expected task duration.
- D1 `batch()` is not available inside Queue consumer handlers for the same binding; use sequential `run()` calls.
- The polling endpoint is not a WebSocket; build a short-poll loop (e.g. 1 s interval, 10 s max) on the client side, then fall back to a webhook callback pattern for long-running sub-tasks.
- `scheduler.wait()` is a Workers-only API; do not use it outside of test helpers in production code.

---

## Verification

```bash
# Apply schema
wrangler d1 execute app-db --file=schema.sql

# Scatter 3 tasks
curl -X POST http://localhost:8787/scatter \
  -H 'Content-Type: application/json' \
  -d '{"inputs":["apple","banana","cherry"]}'
# Returns: {"correlationId":"<uuid>","totalTasks":3}

# Poll until ready
CORR=<uuid from above>
until curl -s "http://localhost:8787/gather?correlationId=$CORR" | grep -q '"ready":true'; do
  sleep 1
done
curl "http://localhost:8787/gather?correlationId=$CORR" | jq .

# Check D1
wrangler d1 execute app-db \
  --command "SELECT * FROM scatter_results;"
```

---

## Related

- `outbox-pattern-workers-d1-queues.md`
- `event-driven-saga-compensation-workers.md`
- `cache-aside-pattern-workers-kv-d1.md`

---

## Sources

- Cloudflare Queues Batching — https://developers.cloudflare.com/queues/configuration/batching-retries/
- Cloudflare D1 Worker API — https://developers.cloudflare.com/d1/worker-api/
- Scatter-Gather (Enterprise Integration Patterns) — https://www.enterpriseintegrationpatterns.com/patterns/messaging/BroadcastAggregate.html
