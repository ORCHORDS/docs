# workers-cron-triggers

**Issue:** Scheduled Workers (Cron Triggers) — wrangler.toml syntax, long-running jobs, idempotency, error alerting
**Date:** 2026-08-11
**Status:** documented

## Symptom
Your nightly cleanup job never runs. A cron Worker times out after 30s
because it processes too many rows. The same row gets double-processed
after a retry. You have no idea when the cron fails.

## Root cause
**Cron Triggers fire the `scheduled` handler, not `fetch`.** Workers
have a default 30 s CPU limit; long-running jobs must be chunked or
delegated to Queues. Without idempotency guards, retries cause
duplicate side-effects.

**Source:** https://developers.cloudflare.com/workers/configuration/cron-triggers/

## wrangler.toml syntax

```toml
name = "example project-cron"
main = "src/index.ts"
compatibility_date = "2025-01-01"

# One or more cron expressions (UTC)
[triggers]
crons = [
  "0 3 * * *",    # daily at 03:00 UTC
  "*/5 * * * *",  # every 5 minutes
  "0 0 * * 1",    # every Monday midnight UTC
]
```

Supported subset of cron syntax:
- `*` `*/n` `n` `n-m` `n,m` for minute/hour/day/month/weekday
- No seconds field (minute-level granularity only)
- Maximum 5 cron expressions per Worker

## The `scheduled` handler

```typescript
export interface Env {
  DB: D1Database;
  CLEANUP_QUEUE: Queue;
  ALERT_EMAIL: string; // email binding name
}

export default {
  // fetch handler still required for health checks
  async fetch(_request: Request, _env: Env): Promise<Response> {
    return new Response("cron worker", { status: 200 });
  },

  async scheduled(
    controller: ScheduledController,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    console.log(`Cron fired: cron=${controller.cron} scheduledTime=${controller.scheduledTime}`);

    // Use waitUntil so async work outlives the handler return
    ctx.waitUntil(runCleanup(env, controller.scheduledTime));
  },
};
```

`controller.cron` is the matched cron expression string.
`controller.scheduledTime` is the Unix epoch (ms) of the scheduled run.

## Handling long-running jobs — chunk via Queue

Workers have a 30 s CPU limit on the paid plan (300 s with Unbound).
For jobs that touch thousands of rows, push work items onto a Queue and
let Queue consumers process them in parallel.

```typescript
async function runCleanup(env: Env, scheduledTime: number): Promise<void> {
  // 1. Discover work items (fast DB query)
  const staleIds = await env.DB
    .prepare(`SELECT id FROM sessions WHERE expires_at < ? LIMIT 5000`)
    .bind(scheduledTime)
    .all<{ id: string }>();

  if (!staleIds.results.length) return;

  // 2. Enqueue in batches of 100 (Queue max batch size)
  const chunks = chunk(staleIds.results.map((r) => r.id), 100);
  await Promise.all(
    chunks.map((ids) =>
      env.CLEANUP_QUEUE.sendBatch(
        ids.map((id) => ({ body: { id, scheduledTime } })),
      ),
    ),
  );

  console.log(`Enqueued ${staleIds.results.length} sessions for cleanup`);
}

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}
```

```toml
# wrangler.toml
[[queues.producers]]
binding = "CLEANUP_QUEUE"
queue = "example project-cleanup-queue"

[[queues.consumers]]
queue = "example project-cleanup-queue"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "example project-cleanup-dlq"
```

## Idempotency for cron tasks

Cloudflare may retry a cron invocation if the Worker crashes or if the
zone experiences issues. Always guard side-effects with an idempotency
key derived from `scheduledTime`.

```typescript
// Queue consumer — idempotent delete
export default {
  async queue(batch: MessageBatch<{ id: string; scheduledTime: number }>, env: Env) {
    for (const msg of batch.messages) {
      const { id, scheduledTime } = msg.body;
      const idempotencyKey = `cleanup:${scheduledTime}:${id}`;

      // Check if already processed (KV as idempotency store)
      const done = await env.KV.get(idempotencyKey);
      if (done) {
        msg.ack();
        continue;
      }

      try {
        await env.DB.prepare(`DELETE FROM sessions WHERE id = ?`).bind(id).run();
        // Mark done for 48h (well past any retry window)
        await env.KV.put(idempotencyKey, "1", { expirationTtl: 172800 });
        msg.ack();
      } catch (err) {
        console.error(`Failed to delete session ${id}:`, err);
        msg.retry();
      }
    }
  },
};
```

## Error alerting via Email Binding

Cloudflare Workers support sending email via `send_email` binding
(requires Email Routing enabled on the zone).

```toml
# wrangler.toml
[[send_email]]
name = "ALERT_EMAIL"
destination_address = "ops@example.com"
```

```typescript
import { EmailMessage } from "cloudflare:email";
import { createMimeMessage } from "mimetext";

async function alertOnFailure(
  env: Env,
  error: unknown,
  context: string,
): Promise<void> {
  const msg = createMimeMessage();
  msg.setSender({ name: "example project Cron", addr: "cron@example.com" });
  msg.setRecipient("ops@example.com");
  msg.setSubject(`[ALERT] Cron failure: ${context}`);
  msg.addMessage({
    contentType: "text/plain",
    data: `Cron job "${context}" failed.\n\nError: ${String(error)}\n\nTime: ${new Date().toISOString()}`,
  });

  await (env.ALERT_EMAIL as any).send(
    new EmailMessage("cron@example.com", "ops@example.com", msg.asRaw()),
  );
}

// In the scheduled handler:
async scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext) {
  ctx.waitUntil(
    runCleanup(env, controller.scheduledTime).catch((err) =>
      alertOnFailure(env, err, controller.cron),
    ),
  );
}
```

## Testing crons locally

```bash
# wrangler dev starts a local server; trigger cron manually:
curl "http://localhost:8787/__scheduled?cron=0+3+*+*+*"
```

In production, the Cloudflare dashboard has a "Trigger" button under
Workers → (your worker) → Triggers → Cron Triggers.

## Verification
- Dashboard → Workers → example project-cron → Triggers — confirm cron shows up
- Trigger manually in dashboard; check Workers Logs for `Cron fired:`
- Insert test rows; trigger cron; verify rows are enqueued/deleted
- Force an error; verify alert email is received

## Gotchas
- **The "no fetch handler" gotcha.** A Worker with only a `scheduled`
  export still needs a `fetch` handler or deployment fails.
- **The "CPU limit" gotcha.** The 30 s CPU limit applies to the
  `scheduled` handler itself, not to work done inside `waitUntil`.
  Use `ctx.waitUntil` for anything async.
- **The "cron drift" gotcha.** Cron Triggers fire within ±30 s of the
  scheduled time. Do not assume exact timing.
- **The "duplicate fire" gotcha.** Cloudflare may fire the same cron
  twice during edge failover. Always use idempotency keys.
- **The "LIMIT" gotcha.** Always add `LIMIT` to the discovery query;
  without it, a D1 query can return 50,000+ rows and OOM the Worker.

## Related
- `cloudflare/workers-best-practices.md`
- `cloudflare/workers-workers-queues-patterns.md`
- `cloudflare/d1-best-practices.md`
- `cloudflare/kv-best-practices.md`
- CF Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- CF Email Binding: https://developers.cloudflare.com/email-routing/email-workers/send-email-workers/
- CF Queues: https://developers.cloudflare.com/queues/
