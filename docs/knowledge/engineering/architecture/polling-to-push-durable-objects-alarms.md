# Polling-to-Push Conversion with Durable Objects Alarms

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Clients poll a status endpoint every few seconds to detect job completion, causing a thundering-herd of redundant requests against D1 or an upstream API. The pattern replaces client polling with server-side long-polling backed by a Durable Object that watches the resource and pushes completion to waiting clients the moment it is detected.

## Context
A Durable Object per job maintains a list of waiting HTTP connections (held open via Promises), a watermark of the last-known state, and an alarm that drives periodic re-checks against the authoritative source. When the DO detects a state change it resolves all pending connection promises simultaneously. Clients receive their response within one alarm interval of the actual transition, eliminating the polling amplification while keeping server-side load proportional to the number of *jobs* rather than the number of *clients*.

## Job Watcher Durable Object

Each job gets one DO instance keyed by job ID. The DO holds open HTTP responses from waiting callers.

```typescript
// src/durable-objects/job-watcher.ts
interface Env {
  DB: D1Database;
}

interface JobRow {
  id: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  result: string | null;
  finished_at: number | null;
}

const POLL_INTERVAL_MS = 2_000;  // server-side check cadence
const CLIENT_TIMEOUT_MS = 25_000; // max long-poll hold time

export class JobWatcher implements DurableObject {
  private storage: DurableObjectStorage;
  private env: Env;
  /** Resolve callbacks for each waiting request */
  private waiters: Array<(job: JobRow) => void> = [];

  constructor(state: DurableObjectState, env: Env) {
    this.storage = state.storage;
    this.env = env;
  }

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    const jobId = url.pathname.slice(1); // /job-123 → "job-123"

    // Check current state immediately before waiting
    const current = await this.loadJob(jobId);
    if (current && this.isTerminal(current.status)) {
      return Response.json(current);
    }

    // Schedule a check if not already armed
    if (!(await this.storage.getAlarm())) {
      await this.storage.setAlarm(Date.now() + POLL_INTERVAL_MS);
      await this.storage.put('jobId', jobId);
    }

    // Long-poll: hold the connection open up to CLIENT_TIMEOUT_MS
    return new Promise<Response>((resolve) => {
      const timer = setTimeout(() => {
        // Timeout — reply with current state (may still be pending)
        this.loadJob(jobId).then((job) => {
          resolve(Response.json(job ?? { status: 'pending' }, { status: 202 }));
        });
        this.waiters = this.waiters.filter((w) => w !== onComplete);
      }, CLIENT_TIMEOUT_MS);

      const onComplete = (job: JobRow): void => {
        clearTimeout(timer);
        resolve(Response.json(job));
        this.waiters = this.waiters.filter((w) => w !== onComplete);
      };

      this.waiters.push(onComplete);
    });
  }

  async alarm(): Promise<void> {
    const jobId = await this.storage.get<string>('jobId');
    if (!jobId) return;

    const job = await this.loadJob(jobId);
    if (!job) {
      await this.storage.setAlarm(Date.now() + POLL_INTERVAL_MS);
      return;
    }

    if (this.isTerminal(job.status)) {
      // Notify all waiting clients and stop polling
      for (const resolve of this.waiters) resolve(job);
      this.waiters = [];
    } else {
      // Reschedule for next check
      await this.storage.setAlarm(Date.now() + POLL_INTERVAL_MS);
    }
  }

  private async loadJob(jobId: string): Promise<JobRow | null> {
    return this.env.DB.prepare(
      'SELECT id, status, result, finished_at FROM jobs WHERE id = ?'
    )
      .bind(jobId)
      .first<JobRow>();
  }

  private isTerminal(status: string): boolean {
    return status === 'done' || status === 'failed';
  }
}
```

## Gateway Worker — Route Clients to the Right DO

```typescript
// src/workers/job-status-gateway.ts
interface Env {
  JOB_WATCHER: DurableObjectNamespace;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    // Expected path: /jobs/<jobId>/wait
    const match = url.pathname.match(/^\/jobs\/([^/]+)\/wait$/);
    if (!match) {
      return new Response('Not Found', { status: 404 });
    }

    const jobId = match[1];
    const doId = env.JOB_WATCHER.idFromName(jobId);
    const stub = env.JOB_WATCHER.get(doId);

    // Proxy the long-poll request into the DO
    return stub.fetch(`https://watcher/${jobId}`, { method: 'GET' });
  },
};
```

## Job Submission — Kick Off Server-Side Watch Immediately

When a job is created, proactively wake the DO so the alarm is scheduled before any client polls.

```typescript
// src/workers/job-submit.ts
interface Env {
  DB: D1Database;
  JOB_WATCHER: DurableObjectNamespace;
  JOB_PROCESSOR: Queue<{ jobId: string }>;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { payload } = await req.json<{ payload: unknown }>();
    const jobId = crypto.randomUUID();

    await env.DB.prepare(
      "INSERT INTO jobs (id, status, result, finished_at) VALUES (?, 'pending', NULL, NULL)"
    ).bind(jobId).run();

    // Arm the watcher before the job is even picked up
    const doId = env.JOB_WATCHER.idFromName(jobId);
    const stub = env.JOB_WATCHER.get(doId);
    // Fire-and-forget the initial prime (the DO will set the alarm)
    env.JOB_PROCESSOR.send({ jobId });

    return Response.json({ jobId, statusUrl: `/jobs/${jobId}/wait` }, { status: 202 });
  },
};
```

## Graceful Degradation — SSE Upgrade

For browsers that support Server-Sent Events, upgrade the response before entering the long-poll:

```typescript
// Alternative response path inside JobWatcher.fetch() for EventStream clients
if (req.headers.get('accept')?.includes('text/event-stream')) {
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();

  const onComplete = (job: JobRow): void => {
    const data = `data: ${JSON.stringify(job)}\n\n`;
    writer.write(new TextEncoder().encode(data)).then(() => writer.close());
    this.waiters = this.waiters.filter((w) => w !== onComplete);
  };

  this.waiters.push(onComplete);

  return new Response(readable, {
    headers: {
      'content-type': 'text/event-stream',
      'cache-control': 'no-cache',
    },
  });
}
```

## Anti-patterns
- Holding connections open inside a stateless Worker — Workers have a request CPU limit and no native connection-level blocking; only Durable Objects can hold open responses across the event loop via Promise
- Polling D1 directly from every client connection — O(clients × poll_interval) queries; the DO amortises this to O(jobs × poll_interval)
- Not clearing the alarm when the job reaches a terminal state — the DO continues firing and running DB queries for completed jobs indefinitely
- Sharing one DO instance for multiple jobs — state collisions; always use `idFromName(jobId)`

## Gotchas
- Durable Objects can hold at most ~6 concurrent inbound HTTP connections per instance; for high fan-in (>6 clients waiting on one job) use a WebSocket-based fan-out DO instead
- The `POLL_INTERVAL_MS` alarm fires *at minimum* that interval; actual lag depends on Cloudflare scheduler load — design client retry to tolerate ±500 ms jitter
- If the DO is evicted while clients are waiting, the pending Promises are destroyed and clients see a closed connection — clients must retry on disconnect
- Long-poll responses held in a Worker via `stub.fetch()` count against the parent Worker's 30-second request timeout unless the gateway itself also uses a DO

## Verification
```bash
# Submit a job
JOB=$(curl -sX POST https://api.example.workers.dev/jobs \
  -H 'content-type: application/json' \
  -d '{"payload":{"task":"export"}}' | jq -r .jobId)

# Long-poll for completion (waits up to 25s, exits immediately when done)
curl -s "https://api.example.workers.dev/jobs/${JOB}/wait" | jq .

# Simulate a slow job and verify 202 is returned after CLIENT_TIMEOUT_MS
curl -s -w "\nHTTP %{http_code}\n" \
  "https://api.example.workers.dev/jobs/nonexistent-job/wait"
```

## Related
- [Durable Object Alarm API Scheduled Retry](durable-object-alarm-api-scheduled-retry.md)
- [Durable Objects WebSocket Architecture](workers-do-websocket-architecture.md)
- [PubSub Durable Objects WebSocket Broadcast](pubsub-durable-objects-websocket-broadcast.md)
- [Async Job Queue with Cloudflare Queues and DO](async-job-queue-cloudflare-queues-do.md)

## Sources
- Cloudflare Durable Objects alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- Long-polling vs WebSockets vs SSE: https://ably.com/blog/websockets-vs-long-polling
- Cloudflare Workers request lifecycle: https://developers.cloudflare.com/workers/runtime-apis/fetch-event/
