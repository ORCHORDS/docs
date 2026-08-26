# Cloudflare Workers: Cron Triggers and Scheduling

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Scheduled jobs (nightly age-verification sweeps, moderation
batch runs, engagement-score rollups) either never fire, time
out silently after 30 seconds, or double-process records on
retries. No reliable signal when an invocation fails.

## Context

WAM (example.com) uses Cloudflare Workers with Cron Triggers
for all async platform maintenance: expiring unverified accounts
at 03:00 UTC, running weekly content-moderation sweeps, and
publishing push-notification digests. Jobs that exceed the
CPU budget need to fan out to Cloudflare Queues. This entry
covers the full scheduling stack from `wrangler.toml` syntax
through observability.

## 1. wrangler.toml [triggers].crons Syntax

Declare cron schedules inside a `[triggers]` block. All times
are evaluated in UTC. Expressions use the standard five-field
cron format; a sixth seconds field is NOT supported.

```toml
name = "wam-maintenance"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[triggers]
crons = [
  "0 3 * * *",      # daily at 03:00 UTC — account sweeps
  "0 */6 * * *",    # every 6 hours     — moderation pass
  "30 8 * * 1"      # Monday 08:30 UTC  — weekly digest
]
```

The `scheduled` export receives `controller`, `env`, and `ctx`.
Route multiple schedules by matching `controller.cron`:

```typescript
export default {
  async scheduled(
    controller: ScheduledController,
    env: Env,
    ctx: ExecutionContext,
  ) {
    switch (controller.cron) {
      case "0 3 * * *":
        ctx.waitUntil(runAccountSweep(env));
        break;
      case "0 */6 * * *":
        ctx.waitUntil(runModerationPass(env));
        break;
      case "30 8 * * 1":
        ctx.waitUntil(sendWeeklyDigest(env));
        break;
    }
  },
};
```

`controller.scheduledTime` is a Unix timestamp (ms) and
`controller.cron` is the exact expression string including
whitespace — it must match character-for-character.

## 2. Cron Triggers vs Durable Object Alarms

| Dimension              | Cron Trigger               | DO Alarm                      |
|------------------------|----------------------------|-------------------------------|
| Schedule source        | `wrangler.toml` (static)   | `alarm()` set programmatically|
| Granularity            | Minute-level (5-field cron)| Millisecond-precise timestamp |
| Retry on failure       | No automatic retry         | Yes — exponential back-off    |
| Scope                  | Global (runs once per fire) | Per-DO instance               |
| Max concurrent         | One per Worker per fire    | One per DO instance           |
| Best for               | Platform-wide batch jobs   | Per-user / per-object tasks   |
| Limits                 | 3 expressions per Worker   | 1 alarm per DO instance       |
| CPU budget (paid)      | 30 s or 15 min (see §3)    | 30 s (same as fetch handler)  |

Use Cron Triggers for fleet-wide maintenance. Use DO alarms
for anything scoped to an individual object — e.g. expiring
a single user's session token at a computed future time.

## 3. Execution Time Limits

Workers operate under two separate time budgets:

| Plan    | Trigger interval | CPU time  | Wall-clock time |
|---------|-----------------|-----------|-----------------|
| Free    | any             | 10 ms     | 15 min          |
| Paid    | < 1 hour        | 30 s      | 15 min          |
| Paid    | ≥ 1 hour        | 15 min    | 15 min          |

**CPU time** counts only active JavaScript execution; network
I/O pauses the clock. **Wall-clock time** counts everything
including I/O waits. A job that reads a D1 table of 50,000
rows and calls an external API per row will exhaust wall time
long before CPU time.

Per-account limits: 5 cron triggers on Free; 250 on Paid.
Per-Worker limit: 3 cron expressions in the `crons` array.

## 4. Handling Long Jobs: Fan-Out to Queues

When a single cron invocation cannot finish in the allotted
time, use the scheduled handler only to enqueue work items
and let Queue consumers do the heavy lifting.

```typescript
// Scheduled handler — enqueue only, < 1 s CPU
async scheduled(controller, env, ctx) {
  const userIds = await fetchPendingUserIds(env.DB);
  const messages = userIds.map((id) => ({
    body: { userId: id, task: "age-sweep" },
  }));
  ctx.waitUntil(
    env.SWEEP_QUEUE.sendBatch(messages),
  );
},

// Queue consumer — processes one batch at a time
async queue(batch: MessageBatch<SweepMsg>, env: Env) {
  for (const msg of batch.messages) {
    await processUser(msg.body.userId, env);
    msg.ack();
  }
},
```

Queue batch size defaults to 10; set `max_batch_size` and
`max_batch_timeout` in `wrangler.toml` under `[[queues.consumers]]`
to tune throughput.

## 5. Idempotency and Testing

**Idempotency:** Cron Triggers do not retry on failure, but
network errors inside a `waitUntil` can leave partial work.
Guard every write with an idempotent key:

```typescript
await env.DB.prepare(
  `INSERT INTO sweep_log (user_id, run_date)
   VALUES (?, ?)
   ON CONFLICT (user_id, run_date) DO NOTHING`,
).bind(userId, todayISO).run();
```

**Testing locally:**

```bash
# Start dev server, then trigger the scheduled handler:
wrangler dev &
curl "http://localhost:8787/cdn-cgi/handler/scheduled"

# Simulate a specific cron expression:
curl "http://localhost:8787/cdn-cgi/handler/scheduled\
?cron=0+3+*+*+*"
```

**Monitoring in Workers Logs / Analytics Engine:**
Every cron invocation produces a log entry. Query failures
via the GraphQL Analytics API or pipe to Analytics Engine
for dashboards:

```bash
wrangler tail --format=json wam-maintenance \
  | jq 'select(.outcome != "ok")'
```

## Anti-patterns

- Putting business logic directly in the scheduled handler
  instead of behind a `ctx.waitUntil`; a thrown exception
  before `waitUntil` registration silently drops the job.
- Using `crons = ["* * * * *"]` (every minute) on the Free
  plan — the 10 ms CPU budget makes this near-useless.
- Relying on `controller.scheduledTime` as a unique job ID;
  two firings in the same minute share the same rounded value
  on some runtimes — use a generated UUID instead.
- Storing mutable state in module-level variables across cron
  invocations; Workers may spin up fresh isolates each fire.

## Gotchas

- Cron trigger changes (add/edit/delete) propagate to the
  global network in up to 15 minutes after deployment.
- A cron Worker that returns a non-2xx from any awaited
  fetch does NOT automatically retry — implement your own
  dead-letter logic or push failures to a DLQ-backed Queue.
- `wrangler dev --test-scheduled` was deprecated; use the
  `/cdn-cgi/handler/scheduled` endpoint shown above instead.
- The Free plan 10 ms CPU limit makes cron Workers nearly
  useless without upgrading; budget for the Paid plan when
  scheduling production batch work.
- Changing the cron expression string in `wrangler.toml`
  creates a new trigger and leaves the old one in place
  until the next `wrangler deploy` fully replaces it.

## Verification

1. Deploy: `wrangler deploy`.
2. Confirm triggers in dashboard:
   Workers & Pages → your worker → Triggers → Cron Triggers.
3. Fire immediately via curl (see §5) and check
   Workers Logs for `outcome: "ok"`.
4. Inspect past runs: dashboard → Triggers →
   Past Events (last 24 h of invocations shown).
5. Add a Notification in the dashboard under Alerts to page
   on cron failure (Workers Cron Trigger Error alert type).

## Related

- `workers-cron-triggers.md` — older, shorter reference entry
- `durable-objects-alarms-scheduling.md` — DO alarm deep-dive
- `queues-batch-processing.md` — Queue consumer configuration
- `queues-dlq-patterns.md` — dead-letter queue setup
- `workers-analytics-engine.md` — structured event emission

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/
- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers/examples/multiple-cron-triggers/
- https://developers.cloudflare.com/workers/wrangler/configuration/
