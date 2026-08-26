# cron-scheduling

**Issue:** Cron jobs, scheduled tasks, retries
**Date:** 2026-08-09
**Status:** documented

## Symptom
You need a daily report. You write a script. You set up
cron. The script runs at 3am. It fails silently. The
report is missed. You find out a week later.

## Root cause
**Cron jobs are not "set and forget."** They need
monitoring, error handling, and idempotency.

**Source:** CF Cron Triggers:
https://developers.cloudflare.com/workers/configuration/cron-triggers/

## The "CF Cron Triggers" pattern

```ts
// In a Worker
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Run the task
    await sendDailyReport(env);
  },
};
```

```toml
# wrangler.toml
[triggers]
crons = ["0 3 * * *"]  # Every day at 3am UTC
```

The Worker is invoked by CF on the schedule.

## The "cron expression" syntax

```
* * * * * *
| | | | | |
| | | | | day of week (0-6, 0=Sun)
| | | | month (1-12)
| | | day of month (1-31)
| | hour (0-23)
| minute (0-59)
| second (0-59, optional)
```

Examples:
- `0 3 * * *` — Every day at 3am
- `0 */6 * * *` — Every 6 hours
- `0 0 * * 1` — Every Monday at midnight
- `*/15 * * * *` — Every 15 minutes
- `0 0 1 * *` — First of every month

## The "timezone" gotcha

Cron runs in **UTC** by default. For "9am in the user's
timezone," the cron runs at the UTC equivalent.

```ts
// Run at 9am in each timezone
export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    // Get current hour in UTC
    const utcHour = new Date().getUTCHours();

    // For each timezone, check if it's 9am
    const timezones = [
      { tz: 'America/New_York', users: env.US_USERS },
      { tz: 'Asia/Tokyo', users: env.JP_USERS },
    ];

    for (const { tz, users } of timezones) {
      const localHour = new Date().toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: tz });
      if (parseInt(localHour) === 9) {
        await sendDailyReport(users, env);
      }
    }
  },
};
```

The cron runs hourly; the handler dispatches based on the
user's timezone.

## The "idempotency" pattern

Cron jobs may run multiple times (e.g. on retry). Make them
idempotent:
```ts
async function sendDailyReport(env: Env): Promise<void> {
  const today = new Date().toISOString().split('T')[0];
  const idempotencyKey = `daily-report:${today}`;

  const alreadySent = await env.KV.get(idempotencyKey);
  if (alreadySent) {
    console.log({ msg: 'daily.report.skipped', date: today });
    return;
  }

  // Generate and send the report
  const report = await generateReport(env);
  await sendEmail(report, env);

  // Mark as sent
  await env.KV.put(idempotencyKey, '1', { expirationTtl: 86400 * 2 });  // 2 days
}
```

The idempotency key prevents double-sending.

## The "monitoring" pattern

For cron jobs, monitor:
- **Last run:** When did it last run?
- **Duration:** How long did it take?
- **Errors:** Did it fail?
- **Result:** What was the outcome?

```ts
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const start = Date.now();
    const runId = crypto.randomUUID();

    try {
      // ... do work

      const duration = Date.now() - start;
      logEvent('cron.success', 'info', { job: 'daily-report', runId, duration });
    } catch (err) {
      const duration = Date.now() - start;
      logEvent('cron.error', 'error', { job: 'daily-report', runId, duration, error: String(err) });

      // Alert
      await pageOncall('Cron job failed', { job: 'daily-report', runId, error: String(err) });
    }
  },
};
```

## The "alert on missed run" pattern

For critical crons, alert if the run is missed:
```ts
// In another cron that runs more frequently (every 5 min)
export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    const lastRun = await env.KV.get<string>('last-daily-report-run');
    const lastRunTime = lastRun ? new Date(lastRun).getTime() : 0;
    const hoursSinceLastRun = (Date.now() - lastRunTime) / (1000 * 60 * 60);

    if (hoursSinceLastRun > 25) {
      // The daily report should run every 24h; > 25h is missed
      await pageOncall('Cron job missed', { job: 'daily-report', hoursSinceLastRun });
    }
  },
};
```

## The "long-running cron" gotcha

CF Workers have CPU limits:
- **Bundled:** 30s CPU per request
- **Unbound:** 5 min HTTP, 15 min cron (at the time of
  writing)

For long-running work:
- **Batch the work** (process N items per run)
- **Use multiple crons** (one per batch)
- **Use a queue** (worker processes the queue)

## The "cron vs queue" choice

| Use case | Use |
|---|---|
| Periodic batch work (reports, cleanup) | Cron |
| Real-time events (user actions) | Queue |
| Both | Both |

For periodic work, cron is the right tool.

## The "DST" gotcha

Cron runs in UTC, which doesn't have DST. For "9am local
time," the UTC offset changes twice a year.

The handler must check the user's timezone, not assume a
fixed offset.

## The "multiple instances" gotcha

CF may run multiple instances of the cron. Each Worker
isolate runs its own copy.

For stateful cron (e.g. only one run at a time), use a DO:
```ts
// Acquire a lock
const lockId = env.LOCK.idFromName('daily-report');
const lock = env.LOCK.get(lockId);
const acquired = await lock.fetch('https://lock/acquire');
if (!acquired.ok) {
  console.log({ msg: 'cron.skipped', reason: 'lock-held' });
  return;
}

try {
  await sendDailyReport(env);
} finally {
  await lock.fetch('https://lock/release');
}
```

The lock ensures only one run at a time.

## The "cron expression" tooling

For complex expressions, use a tool:
- crontab.guru: https://crontab.guru/
- Cronitor: https://crontab.cronitor.io/

## The "daylight saving" for cron

CF Cron Triggers uses UTC. The "9am in Tokyo" cron may
run at 0:00 UTC (winter) or 1:00 UTC (summer) depending
on DST in the user's region.

For the cron to work in all timezones, the handler must
check the timezone, not assume a fixed UTC hour.

## Verification
- **Test:** Cron handler has unit tests
- **Live:** Cron runs are logged + monitored
- **Audit:** Quarterly review of cron jobs

## Gotchas
- **The "cron in UTC" gotcha.** Cron is in UTC; the handler
  must convert for the user's timezone.
- **The "cron silent failure" gotcha.** A cron that fails
  silently is a bug. Always log + monitor.
- **The "cron that runs too long" gotcha.** CPU limits can
  kill the Worker. Batch the work.
- **The "cron that runs at the wrong time" gotcha.** Test
  the cron expression in staging first.
- **The "cron with side effects" gotcha.** A cron that
  modifies data must be idempotent + transactional.
- **The "cron without monitoring" anti-pattern.** A cron
  that you don't know is running is worse than no cron.

## Related
- `cloudflare/workers-workers-queues-patterns.md`
- `idempotency-keys.md`
- `retry-with-exponential-backoff.md`
- `observability-three-pillars-detail.md`
- CF Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- crontab.guru: https://crontab.guru/
