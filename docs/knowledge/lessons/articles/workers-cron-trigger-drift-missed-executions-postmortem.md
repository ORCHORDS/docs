# Workers Cron Trigger Drift and Missed Executions Postmortem

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A nightly billing reconciliation Cron Trigger that was scheduled for `0 2 * * *` (02:00 UTC) silently
stopped executing for three consecutive nights following a `wrangler deploy` that pushed a new Worker
version at 01:58 UTC, leaving invoices un-generated and accounts in a stale billing state.

## Context
The reconciliation job runs at 02:00 UTC to aggregate the previous day's usage and generate invoices.
The deployment at 01:58 UTC was a routine dependency bump with no changes to business logic. The team
did not realize that a deployment within the two-minute window before a scheduled Cron Trigger can cause
the trigger to be skipped for that execution cycle. Three nights passed before a customer reported a
missing invoice, at which point the team had no way to retroactively trigger the missed runs without
manual intervention.

Cloudflare's documentation notes that Cron Triggers may be skipped if a Worker is being deployed or if
the Worker script errors during the triggered execution and does not retry. Neither behaviour was covered
by the team's deployment runbook.

## The Deployment Window Problem

Workers Cron Triggers are scheduled globally at the edge. When a new Worker version is deployed,
there is a propagation window during which some PoPs may run the old version and others the new one.
If the cron fire time falls inside the propagation window, some edges may determine the trigger has
already been handled and skip it — resulting in zero executions for that cycle.

The practical rule: **avoid deploying within 5 minutes of a scheduled Cron Trigger**.

The team's CI pipeline had no guard against this:

```yaml
# OLD: no cron-aware deploy gate
- name: Deploy Worker
  run: wrangler deploy
```

The fix was a deploy gate that checks the current UTC time against all cron expressions in `wrangler.toml`:

```bash
#!/usr/bin/env bash
# scripts/cron-safe-deploy.sh
# Abort deploy if any cron trigger fires within the next 5 minutes

CRON_EXPRESSIONS=(
  "0 2 * * *"   # nightly reconciliation
  "*/15 * * * *" # health-check poller
)

NOW_MIN=$(date -u +%H%M | sed 's/^0//')
LOOKAHEAD=5

for expr in "${CRON_EXPRESSIONS[@]}"; do
  NEXT=$(npx --yes cronstrue "$expr" --timezone UTC 2>/dev/null || true)
  NEXT_MIN=$(node -e "
    const CronJob = require('cron').CronJob;
    const j = CronJob.from({ cronTime: '$expr', onTick: ()=>{} });
    const ms = j.nextDate().toMillis() - Date.now();
    process.stdout.write(String(Math.floor(ms/60000)));
  " 2>/dev/null || echo "999")
  if [ "$NEXT_MIN" -lt "$LOOKAHEAD" ]; then
    echo "ERROR: Deploy blocked — cron '$expr' fires in ${NEXT_MIN}m (< ${LOOKAHEAD}m window)"
    exit 1
  fi
done
echo "Cron window clear — proceeding with deploy"
```

## Idempotent Execution with a Run Lock

Even with the deploy guard in place, Cron Triggers are at-most-once by default. A transient Worker
error during execution will not automatically retry the scheduled run (unlike Queue consumers which
have built-in retry semantics). The fix was to gate each reconciliation run on a KV-backed run lock
that records the last successful execution timestamp:

```typescript
const RUN_LOCK_KEY = "reconciliation:last_run";
const MAX_GAP_MS = 26 * 60 * 60 * 1000; // 26 hours — allows one missed trigger before alert

export default {
  async scheduled(
    _event: ScheduledEvent,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    const lastRunRaw = await env.LOCKS_KV.get(RUN_LOCK_KEY);
    const lastRun = lastRunRaw ? parseInt(lastRunRaw, 10) : 0;
    const now = Date.now();

    if (now - lastRun < 20 * 60 * 60 * 1000) {
      // Already ran within the last 20 hours — skip (safety against double-fire)
      console.info(JSON.stringify({ event: "cron_skipped_already_ran", lastRun, now }));
      return;
    }

    try {
      await runReconciliation(env);
      await env.LOCKS_KV.put(RUN_LOCK_KEY, String(now));
      console.info(JSON.stringify({ event: "cron_success", now }));
    } catch (err) {
      console.error(JSON.stringify({ event: "cron_failure", error: String(err), now }));
      throw err; // Surface to tail worker
    }
  },
};
```

## Alerting on Missed Runs

A separate health-check Cron Trigger (scheduled every 15 minutes) reads the run lock and fires a
PagerDuty alert if the gap exceeds 26 hours:

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const lastRunRaw = await env.LOCKS_KV.get(RUN_LOCK_KEY);
    const lastRun = lastRunRaw ? parseInt(lastRunRaw, 10) : 0;
    const gapHours = (Date.now() - lastRun) / 3_600_000;

    if (gapHours > 26) {
      await fetch(env.PAGERDUTY_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          routing_key: env.PAGERDUTY_KEY,
          event_action: "trigger",
          payload: {
            summary: `Reconciliation cron has not run in ${gapHours.toFixed(1)} hours`,
            severity: "critical",
            source: "workers-cron-health-check",
          },
        }),
      });
    }
  },
};
```

## Manual Backfill Recovery

For the three missed nights, reconciliation was run manually via the `wrangler cron trigger` command
(available since Workers CLI 3.x):

```bash
# Manually fire the scheduled handler
wrangler cron trigger reconciliation-worker
```

This is fire-and-forget from the CLI; the Worker must handle its own idempotency to avoid
double-processing if the original run did partially complete.

## Anti-patterns
- Deploying a Worker within 5 minutes of any of its scheduled Cron Trigger times
- Treating Cron Trigger execution as guaranteed at-least-once without an external health-check
- Using wall-clock time inside the scheduled handler as the canonical "this run covers X period"
  without persisting the coverage window to durable storage
- Relying on `wrangler tail` alone to discover missed cron runs — it only shows live executions

## Gotchas
- Cloudflare does not send a notification or log a missed Cron Trigger; missed executions are
  invisible without an external watchdog
- `wrangler cron trigger` fires the `scheduled` handler but does not set `event.cron` to the
  original schedule string; test your handler's behaviour when `event.cron` is an empty string
- Cron expressions in `wrangler.toml` use UTC; there is no per-trigger timezone override
- A Cron Trigger that throws an uncaught error will not be retried for that scheduled slot

## Verification
1. Use Miniflare's `env.MINIFLARE_WORKERS_SCHEDULE` API to simulate a scheduled event and assert the
   run lock is written after a successful execution.
2. Simulate a missed run by setting `LOCKS_KV.put(RUN_LOCK_KEY, String(Date.now() - 28*3600*1000))`
   in staging and confirm the health-check alert fires within 15 minutes.
3. Validate the deploy gate script blocks a deploy when the system clock is within 5 minutes of
   `0 2 * * *` (mock `date` output in CI).

## Related
- `durable-object-alarm-silent-failure-payment-reminders.md`
- `queue-backlog-death-spirals.md`
- `write-the-runbook-before-the-incident.md`
- `alert-fatigue-masks-real-outages-2026.md`
- `idempotency-keys-for-all-payment-calls.md`

## Sources
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- wrangler cron trigger command — https://developers.cloudflare.com/workers/wrangler/commands/#cron-trigger
- ScheduledEvent API — https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/
