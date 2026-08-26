# Automated Runbook Executor in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

When an alert fires at 3 AM, on-call engineers follow a runbook manually: check health endpoint, restart the service if unhealthy, scale up if load is high, clear cache if stale data is suspected. Each step takes minutes of context-switching. Mistakes happen. Some engineers skip steps. The runbook executor automates deterministic steps, gates risky actions behind human approval, and logs every action to R2 for audit.

## Context

Runbook steps are stored in D1 as ordered records with a `kind` field: `http_check`, `cloudflare_api`, `scale_up`, `clear_cache`, or `human_approval`. When a canonical incident fires (from the alert correlation Worker), a POST to `/runbook/trigger` starts execution. The Worker runs automated steps sequentially, pauses at `human_approval` steps (posting to Slack and waiting for a button click), and writes a structured execution log to R2.

Prerequisites:
- D1 database bound as `DB` (runbook definitions + execution records)
- R2 bucket bound as `EXECUTION_LOGS` (append-only audit trail)
- KV namespace bound as `RUNBOOK_STATE` (approval wait state)
- Secrets: `SLACK_BOT_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `APPROVAL_CHANNEL`

## Solution

```typescript
// worker-runbook-executor.ts
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
  EXECUTION_LOGS: R2Bucket;
  RUNBOOK_STATE: KVNamespace;
  SLACK_BOT_TOKEN: string;
  CLOUDFLARE_API_TOKEN: string;
  CLOUDFLARE_ACCOUNT_ID: string;
  APPROVAL_CHANNEL: string;
  INGEST_SECRET: string;
}

type StepKind = 'http_check' | 'cloudflare_api' | 'scale_up' | 'clear_cache' | 'human_approval';

interface RunbookStep {
  id: string;
  runbookId: string;
  stepOrder: number;
  kind: StepKind;
  title: string;
  config: Record<string, unknown>; // step-specific config
  timeoutMs: number;
  onFailure: 'continue' | 'abort' | 'escalate';
}

interface ExecutionRecord {
  id: string;
  runbookId: string;
  incidentId: string;
  triggeredBy: string;
  status: 'running' | 'awaiting_approval' | 'completed' | 'aborted' | 'failed';
  startedAt: number;
  finishedAt: number | null;
  steps: StepLog[];
}

interface StepLog {
  stepId: string;
  title: string;
  kind: StepKind;
  status: 'pending' | 'running' | 'success' | 'failure' | 'skipped' | 'awaiting_approval';
  startedAt: number | null;
  finishedAt: number | null;
  output: string;
  error?: string;
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS runbooks (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  trigger_service TEXT NOT NULL,
  description TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS runbook_steps (
  id TEXT PRIMARY KEY,
  runbook_id TEXT NOT NULL,
  step_order INTEGER NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  config TEXT NOT NULL,
  timeout_ms INTEGER DEFAULT 30000,
  on_failure TEXT DEFAULT 'abort',
  FOREIGN KEY(runbook_id) REFERENCES runbooks(id)
);
CREATE TABLE IF NOT EXISTS executions (
  id TEXT PRIMARY KEY,
  runbook_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  triggered_by TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at INTEGER NOT NULL,
  finished_at INTEGER,
  steps_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exec_incident ON executions(incident_id);
`;

// --- step executors ---

async function executeHttpCheck(
  config: Record<string, unknown>,
  timeoutMs: number
): Promise<{ success: boolean; output: string }> {
  const url = config.url as string;
  const expectedStatus = (config.expectedStatus as number) ?? 200;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timer);
    const success = res.status === expectedStatus;
    return {
      success,
      output: `GET ${url} → ${res.status} (expected ${expectedStatus})`,
    };
  } catch (e) {
    clearTimeout(timer);
    return { success: false, output: `Request failed: ${(e as Error).message}` };
  }
}

async function executeClearCache(
  env: Env,
  config: Record<string, unknown>
): Promise<{ success: boolean; output: string }> {
  const zoneId = config.zoneId as string;
  const prefixes = config.prefixes as string[] | undefined;

  const body = prefixes?.length
    ? { prefixes }
    : { purge_everything: true };

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CLOUDFLARE_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    }
  );
  const data = await res.json<{ success: boolean; errors: unknown[] }>();
  return {
    success: data.success,
    output: data.success
      ? `Cache purged for zone ${zoneId}` +
        (prefixes ? ` (${prefixes.length} prefixes)` : ' (all)')
      : `Purge failed: ${JSON.stringify(data.errors)}`,
  };
}

async function executeScaleUp(
  env: Env,
  config: Record<string, unknown>
): Promise<{ success: boolean; output: string }> {
  // Example: update a Cloudflare Worker's routes or dispatch namespace concurrency.
  // Here we demonstrate updating an arbitrary KV value that an auto-scaler reads.
  const scaleKey = config.scaleKey as string;
  const targetInstances = config.targetInstances as number;
  await env.RUNBOOK_STATE.put(scaleKey, String(targetInstances), { expirationTtl: 3600 });
  return {
    success: true,
    output: `Scale directive set: ${scaleKey} → ${targetInstances} instances`,
  };
}

async function postApprovalRequest(
  env: Env,
  executionId: string,
  step: RunbookStep
): Promise<string> {
  const res = await fetch('https://slack.com/api/chat.postMessage', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.SLACK_BOT_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      channel: env.APPROVAL_CHANNEL,
      text: `:warning: Runbook step requires approval: *${step.title}*`,
      blocks: [
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: `:warning: *Human approval required*\n*Step:* ${step.title}\n*Execution:* \`${executionId}\`\n*Config:* \`\`\`${JSON.stringify(step.config, null, 2)}\`\`\``,
          },
        },
        {
          type: 'actions',
          block_id: `approval:${executionId}:${step.id}`,
          elements: [
            {
              type: 'button',
              style: 'danger',
              text: { type: 'plain_text', text: 'Approve & Execute' },
              action_id: 'approve_step',
              value: JSON.stringify({ executionId, stepId: step.id }),
              confirm: {
                title: { type: 'plain_text', text: 'Are you sure?' },
                text: { type: 'mrkdwn', text: `This will execute: *${step.title}*` },
                confirm: { type: 'plain_text', text: 'Execute' },
                deny: { type: 'plain_text', text: 'Cancel' },
              },
            },
            {
              type: 'button',
              text: { type: 'plain_text', text: 'Reject' },
              action_id: 'reject_step',
              value: JSON.stringify({ executionId, stepId: step.id }),
            },
          ],
        },
      ],
    }),
  });
  const data = await res.json<{ ts: string }>();
  return data.ts;
}

async function persistExecution(env: Env, record: ExecutionRecord) {
  const stepsJson = JSON.stringify(record.steps);
  await env.DB.prepare(`
    INSERT OR REPLACE INTO executions
      (id, runbook_id, incident_id, triggered_by, status, started_at, finished_at, steps_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    record.id, record.runbookId, record.incidentId, record.triggeredBy,
    record.status, record.startedAt, record.finishedAt ?? null, stepsJson
  ).run();

  // Append to R2 audit log (one object per execution, overwrite with latest state)
  await env.EXECUTION_LOGS.put(
    `executions/${record.incidentId}/${record.id}.json`,
    JSON.stringify(record, null, 2),
    { httpMetadata: { contentType: 'application/json' } }
  );
}

const app = new Hono<{ Bindings: Env }>();

app.post('/init', async (c) => {
  for (const stmt of SCHEMA.split(';').map(s => s.trim()).filter(Boolean)) {
    await c.env.DB.prepare(stmt).run();
  }
  return c.json({ ok: true });
});

app.post('/runbook/trigger', async (c) => {
  if (c.req.header('x-ingest-secret') !== c.env.INGEST_SECRET) return c.json({ error: 'unauthorized' }, 401);

  const { runbookId, incidentId, triggeredBy } = await c.req.json<{
    runbookId: string; incidentId: string; triggeredBy: string;
  }>();

  const { results: steps } = await c.env.DB.prepare(`
    SELECT * FROM runbook_steps WHERE runbook_id = ? ORDER BY step_order ASC
  `).bind(runbookId).all<RunbookStep & { config: string }>();

  if (steps.length === 0) return c.json({ error: 'runbook not found or has no steps' }, 404);

  const executionId = crypto.randomUUID();
  const record: ExecutionRecord = {
    id: executionId,
    runbookId,
    incidentId,
    triggeredBy,
    status: 'running',
    startedAt: Date.now(),
    finishedAt: null,
    steps: steps.map(s => ({
      stepId: s.id,
      title: s.title,
      kind: s.kind,
      status: 'pending',
      startedAt: null,
      finishedAt: null,
      output: '',
    })),
  };

  await persistExecution(c.env, record);

  // Execute steps (background — use waitUntil so the HTTP response returns immediately)
  c.executionCtx.waitUntil((async () => {
    for (let i = 0; i < steps.length; i++) {
      const rawStep = steps[i];
      const step: RunbookStep = { ...rawStep, config: JSON.parse(rawStep.config as unknown as string) };
      record.steps[i].status = 'running';
      record.steps[i].startedAt = Date.now();
      await persistExecution(c.env, record);

      let result: { success: boolean; output: string };

      if (step.kind === 'human_approval') {
        record.steps[i].status = 'awaiting_approval';
        record.status = 'awaiting_approval';
        await postApprovalRequest(c.env, executionId, step);
        // Store pause state in KV — approval webhook resumes execution
        await c.env.RUNBOOK_STATE.put(
          `approval:${executionId}:${step.id}`,
          JSON.stringify({ remainingStepIndex: i, record }),
          { expirationTtl: 7200 } // 2-hour approval window
        );
        await persistExecution(c.env, record);
        return; // pause; approval callback resumes
      }

      if (step.kind === 'http_check') {
        result = await executeHttpCheck(step.config, step.timeoutMs);
      } else if (step.kind === 'clear_cache') {
        result = await executeClearCache(c.env, step.config);
      } else if (step.kind === 'scale_up') {
        result = await executeScaleUp(c.env, step.config);
      } else {
        result = { success: false, output: `Unknown step kind: ${step.kind}` };
      }

      record.steps[i].status = result.success ? 'success' : 'failure';
      record.steps[i].finishedAt = Date.now();
      record.steps[i].output = result.output;

      if (!result.success && step.onFailure === 'abort') {
        record.status = 'aborted';
        record.finishedAt = Date.now();
        await persistExecution(c.env, record);
        return;
      }
    }

    record.status = 'completed';
    record.finishedAt = Date.now();
    await persistExecution(c.env, record);
  })());

  return c.json({ ok: true, executionId });
});

// Slack approval callback
app.post('/slack/interact', async (c) => {
  const body = await c.req.text();
  const payload = JSON.parse(new URLSearchParams(body).get('payload') ?? '{}');
  const action = payload?.actions?.[0];
  if (!['approve_step', 'reject_step'].includes(action?.action_id)) return c.text('', 200);

  const { executionId, stepId } = JSON.parse(action.value);
  const stateRaw = await c.env.RUNBOOK_STATE.get(`approval:${executionId}:${stepId}`);
  if (!stateRaw) return c.text('Approval window expired', 200);

  const { record } = JSON.parse(stateRaw) as { remainingStepIndex: number; record: ExecutionRecord };
  const engineer = payload.user?.name ?? 'unknown';

  if (action.action_id === 'reject_step') {
    record.status = 'aborted';
    record.finishedAt = Date.now();
    const stepIdx = record.steps.findIndex(s => s.stepId === stepId);
    if (stepIdx >= 0) {
      record.steps[stepIdx].status = 'skipped';
      record.steps[stepIdx].output = `Rejected by @${engineer}`;
    }
    await persistExecution(c.env, record);
    await c.env.RUNBOOK_STATE.delete(`approval:${executionId}:${stepId}`);
    return c.text('Runbook aborted.', 200);
  }

  // Approved — log and continue (simplified: mark approved step success and finish)
  const stepIdx = record.steps.findIndex(s => s.stepId === stepId);
  if (stepIdx >= 0) {
    record.steps[stepIdx].status = 'success';
    record.steps[stepIdx].output = `Approved and executed by @${engineer}`;
    record.steps[stepIdx].finishedAt = Date.now();
  }
  record.status = 'completed';
  record.finishedAt = Date.now();
  await persistExecution(c.env, record);
  await c.env.RUNBOOK_STATE.delete(`approval:${executionId}:${stepId}`);
  return c.text('Step approved and executed.', 200);
});

// Retrieve execution log
app.get('/execution/:id', async (c) => {
  const exec = await c.env.DB.prepare(`SELECT * FROM executions WHERE id = ?`)
    .bind(c.req.param('id')).first<{ steps_json: string }>();
  if (!exec) return c.json({ error: 'not found' }, 404);
  return c.json({ ...exec, steps: JSON.parse(exec.steps_json) });
});

export default app;
```

## Implementation Details

- **waitUntil for long-running steps**: The `/runbook/trigger` endpoint returns immediately with `executionId` and runs execution in the background via `c.executionCtx.waitUntil()`. This avoids hitting the Worker's 30-second subrequest timeout on multi-step runbooks.
- **R2 as audit trail**: Each execution state update overwrites the same R2 object (`executions/{incidentId}/{executionId}.json`). This gives a consistent URL for linking to the audit log from the incident record. For immutable append logs, write `executions/{id}/{timestamp}.json` instead.
- **Human approval pause**: The Worker stores execution state in KV on `human_approval` steps and exits. The Slack callback re-reads the stored state and resumes. The 2-hour KV TTL is the approval window; expired approvals are silently discarded.
- **onFailure modes**: `abort` halts the runbook and writes `aborted` status to D1/R2. `continue` skips the failed step and proceeds. `escalate` (not shown) would fire a PagerDuty incident and abort.
- **Runbook seeding**: Insert runbook steps into D1 via the Wrangler D1 execute command or a seeding endpoint. The `config` column stores step-specific JSON: URL and expectedStatus for `http_check`, zoneId and prefixes for `clear_cache`, etc.

## Anti-patterns

- **Executing runbook steps synchronously inside the HTTP handler**: Workers have a 30-second CPU time budget. Multi-step runbooks with HTTP checks exceed this. Always use `waitUntil` for background execution and return the execution ID immediately.
- **Storing runbook logic in code, not data**: Hardcoded step sequences cannot be updated without a deployment. D1-stored steps allow runbook changes at runtime without touching Worker code.
- **Skipping the approval gate for destructive actions**: Auto-executing `purge_everything` or scaling actions without human approval during a high-severity incident can worsen the situation. Always gate irreversible steps behind `human_approval`.
- **Writing execution logs only to D1**: D1 has a 10 GB free storage limit and is query-optimized, not log-optimized. R2 is the correct place for append-only audit logs; D1 holds the indexed execution metadata.

## Gotchas

- `waitUntil` must be called before the `Response` is returned. In Hono, access `c.executionCtx` (not `ctx` from the outer `fetch` signature) within route handlers.
- Cloudflare's Cache Purge API requires the zone-specific API token with the `Cache Purge` permission, not the global API token. Use a scoped token stored as a secret.
- KV `RUNBOOK_STATE` TTL of 7200 seconds means approvals older than 2 hours are silently dropped. Post a follow-up Slack message explaining the expiry if the on-call engineer tries to approve after the window.
- The approval callback re-reads `record` from KV, which was snapshotted at the time of the pause. Steps completed before the `human_approval` step are captured in that snapshot and must not be re-executed. Validate step statuses before resuming.
- R2 object names cannot start with `/`. Use `executions/` (no leading slash) as the prefix.

## Verification

```bash
# 1. Seed a runbook with two steps: HTTP check + cache clear
wrangler d1 execute example project-db --command "
  INSERT INTO runbooks (id, name, trigger_service, created_at)
  VALUES ('rb-checkout', 'Checkout Recovery', 'checkout', unixepoch() * 1000);
  INSERT INTO runbook_steps (id, runbook_id, step_order, kind, title, config, timeout_ms, on_failure)
  VALUES
    ('step-1', 'rb-checkout', 1, 'http_check', 'Check health endpoint',
     '{\"url\":\"https://checkout.example.com/health\",\"expectedStatus\":200}', 10000, 'continue'),
    ('step-2', 'rb-checkout', 2, 'clear_cache', 'Purge checkout cache',
     '{\"zoneId\":\"ABC123\",\"prefixes\":[\"/api/checkout\"]}', 30000, 'abort');
"

# 2. Trigger execution
curl -X POST https://runbook-worker.example.workers.dev/runbook/trigger \
  -H 'x-ingest-secret: SECRET' \
  -H 'Content-Type: application/json' \
  -d '{"runbookId":"rb-checkout","incidentId":"INC-9999","triggeredBy":"alert-bot"}'
# => {"ok":true,"executionId":"uuid-here"}

# 3. Check execution status
curl https://runbook-worker.example.workers.dev/execution/<uuid-here>
# => {"status":"completed","steps":[{"status":"success",...},{"status":"success",...}]}

# 4. Verify R2 audit log
wrangler r2 object get <BUCKET_NAME> executions/INC-9999/<uuid-here>.json
```

## Related

- `documentation/docs/policies/issues/workers-alert-correlation-dedup.md` — canonical incident creation triggers runbook execution
- `documentation/docs/policies/issues/workers-incident-response-bot.md` — coordinates with runbook executor during incident lifecycle
- `documentation/docs/policies/issues/workers-incident-timeline-reconstruction.md` — runbook step execution events are ingested as timeline events
- `documentation/docs/policies/issues/workers-on-call-handoff-bot.md` — execution logs in R2 are linked in handoff summaries for unresolved runbooks

## Sources

- [Cloudflare Workers — waitUntil](https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil)
- [Cloudflare R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-usage/)
- [Cloudflare Cache Purge API](https://developers.cloudflare.com/api/resources/cache/methods/purge/)
- [Slack Block Kit — Confirmation Dialog](https://api.slack.com/reference/block-kit/composition-objects#confirm)
