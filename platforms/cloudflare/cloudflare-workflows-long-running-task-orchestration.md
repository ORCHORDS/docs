# Cloudflare Workflows Long-Running Task Orchestration

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to orchestrate multi-step jobs that span minutes, hours, or even days inside
Cloudflare Workers — media transcoding pipelines, SaaS onboarding flows, nightly ETL
sagas, or approval chains — where a plain `fetch` chain times out and a Durable Object
alarm loses context across retries.

Cloudflare Workflows provide durable, resumable execution with built-in sleep, retry
policies, and structured state that survives Worker restarts.

---

## Context

Cloudflare Workflows (GA 2025) are defined as Workers classes that extend `WorkflowEntrypoint`.
Each step is a unit of retryable work. The engine persists state between steps so a
transient infrastructure failure does not require re-running already-completed steps.

Key constraints:
- Maximum workflow wall-clock duration: **1 year**
- Maximum step execution time: **10 minutes** of CPU per step
- Sleep precision: ~1 second (millisecond values are rounded up)
- Concurrent workflow instances: 1 000 per script (configurable per-account)
- Workflow state is stored in Cloudflare's global persistence layer (not D1)

example project platform uses Workflows for: media ingest pipelines (upload → transcode → thumbnail →
notify), multi-tenant provisioning, and scheduled reconciliation jobs.

---

## Defining a Workflow

```typescript
// src/workflows/media-ingest.ts
import {
  WorkflowEntrypoint,
  WorkflowStep,
  WorkflowEvent,
} from 'cloudflare:workers';

export interface MediaIngestParams {
  assetId: string;
  r2Key: string;
  ownerId: string;
}

export class MediaIngestWorkflow extends WorkflowEntrypoint<Env, MediaIngestParams> {
  async run(event: WorkflowEvent<MediaIngestParams>, step: WorkflowStep) {
    const { assetId, r2Key, ownerId } = event.payload;

    // Step 1: Validate the R2 object exists before spending credits
    const meta = await step.do('validate-asset', async () => {
      const obj = await this.env.MEDIA_BUCKET.head(r2Key);
      if (!obj) throw new Error(`R2 key not found: ${r2Key}`);
      return { size: obj.size, contentType: obj.httpMetadata?.contentType ?? 'unknown' };
    });

    // Step 2: Call external transcoding service (retried up to 3 times)
    const transcodeJob = await step.do(
      'submit-transcode',
      { retries: { limit: 3, delay: '10 seconds', backoff: 'exponential' } },
      async () => {
        const resp = await fetch('https://transcode.internal/jobs', {
          method: 'POST',
          headers: { Authorization: `Bearer ${this.env.TRANSCODE_SECRET}` },
          body: JSON.stringify({ r2Key, contentType: meta.contentType }),
        });
        if (!resp.ok) throw new Error(`Transcode submit failed: ${resp.status}`);
        return resp.json<{ jobId: string }>();
      },
    );

    // Step 3: Poll until done (durable sleep between polls)
    let status = 'pending';
    let attempts = 0;
    while (status === 'pending' && attempts < 60) {
      await step.sleep('wait-for-transcode', '30 seconds');
      status = await step.do(`poll-transcode-${attempts}`, async () => {
        const resp = await fetch(
          `https://transcode.internal/jobs/${transcodeJob.jobId}`,
          { headers: { Authorization: `Bearer ${this.env.TRANSCODE_SECRET}` } },
        );
        const body = await resp.json<{ status: string }>();
        return body.status;
      });
      attempts++;
    }

    if (status !== 'done') {
      throw new Error(`Transcode job ${transcodeJob.jobId} timed out after ${attempts} polls`);
    }

    // Step 4: Generate thumbnail
    await step.do('generate-thumbnail', async () => {
      await fetch('https://thumbnail.internal/generate', {
        method: 'POST',
        body: JSON.stringify({ assetId, jobId: transcodeJob.jobId }),
      });
    });

    // Step 5: Update D1 record
    await step.do('mark-complete', async () => {
      await this.env.DB.prepare(
        'UPDATE assets SET status = ? WHERE id = ?',
      ).bind('ready', assetId).run();
    });

    // Step 6: Notify owner via Queue (fire-and-forget)
    await step.do('enqueue-notification', async () => {
      await this.env.NOTIFY_QUEUE.send({ ownerId, assetId, event: 'ingest_complete' });
    });
  }
}
```

---

## Binding and Triggering Workflows

```toml
# wrangler.toml
[[workflows]]
name        = "media-ingest"
binding     = "MEDIA_INGEST_WF"
class_name  = "MediaIngestWorkflow"
```

```typescript
// src/worker.ts — trigger from an HTTP handler
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('POST only', { status: 405 });

    const body = await req.json<{ assetId: string; r2Key: string; ownerId: string }>();

    // Use assetId as idempotency key — same ID = same instance URL
    const instance = await env.MEDIA_INGEST_WF.create({
      id: `media-${body.assetId}`,
      params: body,
    });

    return Response.json({ instanceId: instance.id, status: await instance.status() });
  },
};
```

---

## Checking and Waiting on Instance Status

```typescript
// Poll workflow status from an API route
async function waitForWorkflow(
  wf: Workflow,
  instanceId: string,
  timeoutMs = 30_000,
): Promise<WorkflowInstanceStatus> {
  const instance = await wf.get(instanceId);
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const status = await instance.status();
    if (status.status !== 'running') return status;
    await new Promise(r => setTimeout(r, 2_000));
  }

  throw new Error(`Workflow ${instanceId} still running after ${timeoutMs}ms`);
}

// In a status endpoint:
const status = await waitForWorkflow(env.MEDIA_INGEST_WF, instanceId, 5_000);
return Response.json({
  state: status.status,   // 'running' | 'complete' | 'errored' | 'paused'
  output: status.output,  // final return value if complete
  error: status.error,    // Error message if errored
});
```

---

## Human-in-the-Loop Pause Pattern

```typescript
// Inside a workflow step, park the instance until an external signal
export class ProvisioningWorkflow extends WorkflowEntrypoint<Env, { tenantId: string }> {
  async run(event: WorkflowEvent<{ tenantId: string }>, step: WorkflowStep) {
    const { tenantId } = event.payload;

    await step.do('create-trial', async () => {
      await this.env.DB.prepare('INSERT INTO tenants (id, status) VALUES (?, ?)')
        .bind(tenantId, 'trial').run();
    });

    // Sleep for 14 days (trial period) — durable across restarts
    await step.sleep('trial-period', '14 days');

    // After sleep, check if tenant upgraded
    const upgraded = await step.do('check-upgrade', async () => {
      const row = await this.env.DB.prepare('SELECT status FROM tenants WHERE id = ?')
        .bind(tenantId).first<{ status: string }>();
      return row?.status === 'paid';
    });

    if (!upgraded) {
      await step.do('suspend-tenant', async () => {
        await this.env.DB.prepare('UPDATE tenants SET status = ? WHERE id = ?')
          .bind('suspended', tenantId).run();
      });
    }
  }
}
```

---

## Error Handling and Partial Replay Safety

```typescript
// Steps must be idempotent — the engine may replay them on retry
await step.do(
  'upsert-record',
  { retries: { limit: 5, delay: '5 seconds', backoff: 'linear' } },
  async () => {
    // Use INSERT OR REPLACE (D1) or conditional write to make this safe to replay
    await this.env.DB.prepare(
      `INSERT INTO jobs (id, status, updated_at)
       VALUES (?1, 'pending', unixepoch())
       ON CONFLICT(id) DO UPDATE SET updated_at = unixepoch()`,
    ).bind(jobId).run();
  },
);
```

Step names must be unique within a workflow run. The engine de-duplicates by step name,
so a replayed workflow skips already-completed steps and returns their cached output.

---

## Wrangler Tail for Live Debugging

```bash
# Stream workflow instance logs during development
wrangler tail --format pretty --search "WorkflowInstance"

# Inspect a specific instance via REST API
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workflows/media-ingest/instances/$INSTANCE_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.status'
```

---

## Anti-patterns

- **Accumulating large `step.do` return values** — every step return is stored in
  Workflow state. Return only what subsequent steps need; offload blobs to R2/KV.
- **Non-idempotent steps** — never assume a step runs exactly once. Use upserts,
  conditional writes, or external idempotency keys.
- **Sleeping inside `fetch` without `step.sleep`** — `setTimeout`/`setInterval` are
  not durable. Use `step.sleep('label', '1 hour')` instead.
- **Deeply nested error handling** — let `step.do` bubble errors; the retry policy
  handles transient faults. Reserve `try/catch` for business-logic branching only.
- **Re-using instance IDs across different workflows** — IDs are scoped per workflow
  binding but must be globally unique within that binding.

---

## Gotchas

- `step.do` callbacks must not capture mutable closed-over state that changes between
  retries — the callback is re-executed from scratch each retry.
- Workflow instances cannot be cancelled from within the workflow itself; use the REST
  API or the dashboard to terminate runaway instances.
- `step.sleep` minimum granularity is approximately 1 second; sub-second values are
  rounded up but the actual wake time may drift by a few seconds.
- The `event.timestamp` field reflects when the workflow was **created**, not when the
  current step started — use `Date.now()` inside steps for step-level timing.
- Workflows running in `wrangler dev` use an in-process emulator; some edge cases
  (e.g. durable sleep > 1 minute) behave differently than production.

---

## Verification

```typescript
// Integration test: run workflow to completion in Vitest + workers-pool
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';

describe('MediaIngestWorkflow', () => {
  it('completes for a valid R2 key', async () => {
    await env.MEDIA_BUCKET.put('test/video.mp4', new Uint8Array(16));

    const instance = await env.MEDIA_INGEST_WF.create({
      id: 'test-ingest-1',
      params: { assetId: 'asset-1', r2Key: 'test/video.mp4', ownerId: 'user-1' },
    });

    // Poll until terminal state (test environment skips real sleep durations)
    let status = await instance.status();
    let i = 0;
    while (status.status === 'running' && i++ < 20) {
      await new Promise(r => setTimeout(r, 500));
      status = await instance.status();
    }

    expect(status.status).toBe('complete');
  });
});
```

---

## Related

- `workflows-best-practices.md`
- `cloudflare-workflows-human-in-the-loop-approval.md`
- `workflows-parallel-step-execution.md`
- `cloudflare-queues-delayed-delivery-scheduling.md`
- `durable-objects-alarms-scheduling.md`

---

## Sources

- https://developers.cloudflare.com/workflows/
- https://developers.cloudflare.com/workflows/reference/step-options/
- https://developers.cloudflare.com/workflows/reference/sleeping/
- https://developers.cloudflare.com/workflows/observability/
- https://blog.cloudflare.com/cloudflare-workflows-generally-available/
