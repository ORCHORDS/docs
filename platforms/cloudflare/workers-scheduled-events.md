# workers-scheduled-events

**Issue:** Running Workers on a cron schedule using the `scheduled` handler
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workers expose a `scheduled` export that fires on cron triggers configured in `wrangler.toml`. This is separate from the `fetch` handler and has its own execution context and limits.

## Pattern / Solution

```toml
# wrangler.toml
[triggers]
crons = ["*/5 * * * *", "0 9 * * 1-5"]  # every 5 min + weekdays at 09:00 UTC
```

```typescript
export interface Env {
  DB: D1Database;
  ALERT_URL: string;
}

export default {
  // Regular HTTP handler
  async fetch(request: Request, env: Env): Promise<Response> {
    return new Response('OK');
  },

  // Scheduled handler — receives ScheduledEvent, not Request
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    console.log(`cron: ${event.cron} at ${new Date(event.scheduledTime).toISOString()}`);

    // Use ctx.waitUntil to keep the isolate alive for async work
    ctx.waitUntil(runJob(env));
  },
};

async function runJob(env: Env): Promise<void> {
  const { results } = await env.DB.prepare(
    `SELECT id FROM items WHERE processed = 0 LIMIT 100`
  ).all<{ id: number }>();

  for (const { id } of results) {
    await env.DB.prepare(`UPDATE items SET processed = 1 WHERE id = ?`).bind(id).run();
  }

  if (results.length === 0) return;

  await fetch(env.ALERT_URL, {
    method: 'POST',
    body: JSON.stringify({ processed: results.length }),
    headers: { 'Content-Type': 'application/json' },
  });
}
```

**Testing locally:**
```bash
# Trigger the scheduled handler via Wrangler
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"
```

## Gotchas
- The `scheduled` handler has a **30-second CPU time limit** (same as a regular Worker on paid, 10 ms on free — but scheduled events always get 30 s).
- There is no `request` object; you cannot read incoming headers or body.
- `event.scheduledTime` is the intended fire time (milliseconds), which may differ from `Date.now()` by a few seconds.
- If the Worker fails or times out the cron simply does not retry automatically; build your own retry logic in the job.
- Multiple cron expressions are allowed per Worker; inspect `event.cron` to branch on which trigger fired.
- Wrangler's `--test-scheduled` flag enables `/__scheduled` in local dev mode.

## Related
- `workers-cron-triggers.md`
- `workers-best-practices.md`
- `wrangler-toml-reference.md`
