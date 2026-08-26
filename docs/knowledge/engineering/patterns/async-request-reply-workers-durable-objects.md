# Async Request-Reply with Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A client submits a long-running job (report generation, video transcoding, multi-step API orchestration) that takes 10–300 seconds. You cannot hold the HTTP connection open for that duration. You need to accept the job immediately, process it asynchronously, let the client poll for status or stream progress via SSE, and guarantee the job times out gracefully if it hangs.

## Context

Cloudflare Workers have a 30-second CPU time limit and are stateless between requests. Durable Objects solve both constraints: they have their own event loop, can hold state across requests, and support alarms for time-based callbacks — making them a natural job executor and status store.

Pattern components:

- **Gateway Worker** — accepts `POST /jobs`, creates the `JobDO`, returns `202 Accepted` with `job_id`.
- **JobDO** — stores job state, runs async processing via an internal `fetch` to itself, exposes `GET /status` and SSE `/stream`.
- **DO Alarm** — fires 5 minutes after job creation; marks job as timed-out and enqueues to DLQ.

## Full Implementation

```typescript
// gateway-worker/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /jobs — create job
    if (request.method === 'POST' && url.pathname === '/jobs') {
      const jobId = crypto.randomUUID();
      const body  = await request.json<{ input: unknown }>();

      const stub = env.JOB_DO.get(env.JOB_DO.idFromName(jobId));
      await stub.fetch('https://internal/init', {
        method: 'POST',
        body:   JSON.stringify({ job_id: jobId, input: body.input }),
      });

      return Response.json({ job_id: jobId, status: 'queued' }, { status: 202 });
    }

    // GET /jobs/:id — poll status
    const pollMatch = url.pathname.match(/^\/jobs\/([\w-]+)$/);
    if (request.method === 'GET' && pollMatch) {
      const jobId = pollMatch[1];
      const stub  = env.JOB_DO.get(env.JOB_DO.idFromName(jobId));
      return stub.fetch('https://internal/status');
    }

    // GET /jobs/:id/stream — SSE stream
    const sseMatch = url.pathname.match(/^\/jobs\/([\w-]+)\/stream$/);
    if (request.method === 'GET' && sseMatch) {
      const jobId = sseMatch[1];
      const stub  = env.JOB_DO.get(env.JOB_DO.idFromName(jobId));
      return stub.fetch('https://internal/stream');
    }

    return new Response('Not found', { status: 404 });
  },
};

// job-do/index.ts
type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'timed_out';

interface JobState {
  job_id:     string;
  status:     JobStatus;
  input:      unknown;
  result?:    unknown;
  error?:     string;
  created_at: string;
  updated_at: string;
}

export class JobDO {
  private storage: DurableObjectStorage;
  // SSE subscribers: controller per connected client
  private subscribers: Set<ReadableStreamDefaultController> = new Set();

  constructor(state: DurableObjectState, private env: Env) {
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/init') {
      const body = await request.json<{ job_id: string; input: unknown }>();
      const now  = new Date().toISOString();
      const state: JobState = {
        job_id:     body.job_id,
        status:     'queued',
        input:      body.input,
        created_at: now,
        updated_at: now,
      };
      await this.storage.put('job', state);
      // Set 5-minute timeout alarm
      await this.storage.setAlarm(Date.now() + 5 * 60 * 1_000);
      // Kick off processing asynchronously (fire-and-forget via waitUntil equivalent)
      void this.process(body.input);
      return Response.json({ accepted: true });
    }

    if (url.pathname === '/status') {
      const state = await this.storage.get<JobState>('job');
      if (!state) return new Response('Not found', { status: 404 });
      return Response.json(state);
    }

    if (url.pathname === '/stream') {
      // Server-Sent Events
      const { readable, writable } = new TransformStream();
      const writer = writable.getWriter();
      const encoder = new TextEncoder();

      // Send current state immediately
      const state = await this.storage.get<JobState>('job');
      if (state) {
        await writer.write(encoder.encode(`data: ${JSON.stringify(state)}\n\n`));
      }

      if (state?.status === 'completed' || state?.status === 'failed' || state?.status === 'timed_out') {
        await writer.close();
      } else {
        // Register subscriber to receive future updates
        this.subscribers.add(writer as unknown as ReadableStreamDefaultController);
        (writer as any).closed.then(() => this.subscribers.delete(writer as any)).catch(() => {});
      }

      return new Response(readable, {
        headers: {
          'Content-Type':  'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection':    'keep-alive',
        },
      });
    }

    return new Response('Not found', { status: 404 });
  }

  private async process(input: unknown): Promise<void> {
    await this.updateState({ status: 'running' });
    try {
      // Replace with your actual async work
      const result = await callExternalApis(input, this.env);
      await this.updateState({ status: 'completed', result });
      // Cancel the timeout alarm — job finished in time
      await this.storage.deleteAlarm();
    } catch (err) {
      await this.updateState({ status: 'failed', error: String(err) });
      await this.storage.deleteAlarm();
    }
  }

  private async updateState(patch: Partial<JobState>): Promise<void> {
    const current = (await this.storage.get<JobState>('job')) ?? {} as JobState;
    const updated = { ...current, ...patch, updated_at: new Date().toISOString() };
    await this.storage.put('job', updated);
    this.broadcast(updated);
  }

  private broadcast(state: JobState): void {
    const msg = new TextEncoder().encode(`data: ${JSON.stringify(state)}\n\n`);
    for (const ctrl of this.subscribers) {
      try { (ctrl as any).write(msg); } catch { this.subscribers.delete(ctrl); }
    }
  }

  async alarm(): Promise<void> {
    const state = await this.storage.get<JobState>('job');
    if (!state || state.status === 'completed' || state.status === 'failed') return;
    await this.updateState({ status: 'timed_out', error: 'Job exceeded 5-minute deadline' });
    // Send to DLQ for retry or alerting
    await this.env.DLQ.send({ job_id: state.job_id, input: state.input, reason: 'timeout' });
  }
}

async function callExternalApis(input: unknown, env: Env): Promise<unknown> {
  // Placeholder: replace with real API orchestration
  return { processed: true, input };
}
```

## Wrangler Configuration

```jsonc
{
  "name": "async-job-worker",
  "durable_objects": {
    "bindings": [{ "name": "JOB_DO", "class_name": "JobDO" }]
  },
  "queues": {
    "producers": [{ "queue": "jobs-dlq", "binding": "DLQ" }]
  }
}
```

## Client Polling Example

```typescript
// Client-side polling (TypeScript)
async function waitForJob(jobId: string, baseUrl: string): Promise<unknown> {
  for (let attempt = 0; attempt < 60; attempt++) {
    await new Promise((r) => setTimeout(r, 5_000));  // poll every 5 s
    const res  = await fetch(`${baseUrl}/jobs/${jobId}`);
    const data = await res.json<{ status: string; result?: unknown; error?: string }>();
    if (data.status === 'completed') return data.result;
    if (data.status === 'failed' || data.status === 'timed_out') {
      throw new Error(data.error ?? 'Job failed');
    }
  }
  throw new Error('Client-side polling timeout');
}
```

## Anti-patterns

- **Spawning new Workers from the DO** — DOs cannot spawn Workers; use queues for side effects, not recursive Worker invocations.
- **Storing large results in DO storage** — DO storage limit is 128 KB per key. Write large results to R2 or D1 and store only the reference in the DO.
- **Forgetting `deleteAlarm` on success** — without it, the alarm fires after job completion and incorrectly marks a done job as timed-out.
- **Not broadcasting state updates** — SSE clients hang if the DO updates storage but forgets to call `broadcast`.

## Gotchas

- `void this.process(...)` is fire-and-forget inside the DO — the DO's event loop continues; the async processing runs independently.
- DO alarms survive Worker restarts and redeployments — a set alarm will fire even after a `wrangler deploy`.
- `storage.deleteAlarm()` is a no-op if no alarm is set; safe to call unconditionally.
- SSE connections to DOs count toward the DO's concurrent-connection limit (currently 1 000 per DO instance).

## Verification

```bash
# Submit a job
JOB=$(curl -s -X POST https://api.example.com/jobs -d '{"input":{"n":42}}' | jq -r .job_id)
echo "Job ID: $JOB"

# Poll until complete
watch -n 5 "curl -s https://api.example.com/jobs/$JOB | jq .status"

# Or stream events
curl -N -H 'Accept: text/event-stream' https://api.example.com/jobs/$JOB/stream
```

## Related

- `fan-in-aggregation-workers-queues-d1.md`
- `rate-limit-sliding-window-durable-objects-workers.md`
- Durable Objects — Alarms API
- Workers — Server-Sent Events

## Sources

- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/workers/runtime-apis/server-sent-events/
- https://developers.cloudflare.com/queues/
