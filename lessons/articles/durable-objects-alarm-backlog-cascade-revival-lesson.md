# Durable Objects Alarm Backlog Cascade on Revival Lesson

Date: 2026-08-23 / Author: example.com / Status: production

---

## Incident Summary

On 2026-04-08 a Durable Object class (`SessionCoordinator`) that had been dormant for
11 days was revived en masse by an influx of new sessions following a marketing
campaign. Each DO instance had a backlog of unprocessed alarms (heartbeat ticks and
session-expiry checks) accumulated during the dormancy period. On revival, the Durable
Object runtime attempted to fire all missed alarms in rapid succession. The resulting
CPU burst exhausted the per-class CPU budget and triggered a cascade of 503 responses
to all active sessions for 22 minutes.

---

## Context

- Durable Object class: `SessionCoordinator`
- Number of DO instances revived in the first 5 minutes: ~14 000
- Alarm type: heartbeat tick every 60 seconds, session-expiry check every 5 minutes
- Dormancy period: 11 days (feature was dark-launched, zero traffic)
- CPU budget exceeded: DO class-level CPU time limit (undocumented internal limit)
- User impact: 22 minutes of 503 errors on session creation and renewal endpoints

---

## Timeline

**2026-03-28 00:00 UTC** — `SessionCoordinator` class deployed but feature behind a
flag. Zero instances created. No alarms fire.

**2026-04-08 10:00 UTC** — Marketing campaign launches. Traffic increases 40x over
baseline in 8 minutes.

**2026-04-08 10:04 UTC** — First 14 000 session creation requests each create a new
`SessionCoordinator` DO instance. Each instance schedules an alarm for `now + 60s`.

**2026-04-08 10:05 UTC** — Existing (pre-dark-launch) DO instances that were never
fully evicted begin to receive wake signals. These instances have alarm timestamps
from 11 days ago. The runtime attempts to call `alarm()` for each missed tick.

**2026-04-08 10:07 UTC** — CPU alert fires. 503 rate climbs to 68% of session
requests.

**2026-04-08 10:09 UTC** — On-call engineer identifies Durable Objects as the source
via tail Workers logs. No immediate mitigation available; no feature flag to disable
the DO class without a full redeploy.

**2026-04-08 10:17 UTC** — Engineer deploys a new Worker version with `alarm()` made
a no-op (immediate return with alarm rescheduled 24 hours out). Deploys in 90 seconds.

**2026-04-08 10:22 UTC** — `alarm()` handlers begin completing without CPU overhead.
503 rate drops to < 1%. Session endpoint recovers.

**2026-04-08 10:29 UTC** — Full recovery. Post-incident review begins.

---

## Root Cause

### Primary: Alarm scheduling inside `fetch()` without dormancy guard

The `SessionCoordinator.fetch()` handler scheduled the first heartbeat alarm
unconditionally on every first request to a new instance:

```ts
// Bug: no guard for the case where alarms are already scheduled
async fetch(request: Request) {
  if (!this.initialized) {
    await this.ctx.storage.put('initialized', true);
    this.ctx.storage.setAlarm(Date.now() + 60_000);  // 60-second tick
    this.initialized = true;
  }
  // ...
}
```

For DO instances that were created during the dark-launch period but never received
traffic (their storage had `initialized = true` from a test write), the `initialized`
flag bypassed the guard. These "zombie" instances had alarms in the past.

### Secondary: No backlog-drain budget in `alarm()`

The `alarm()` handler did not check whether the alarm timestamp was significantly in
the past and did not skip or fast-forward stale ticks:

```ts
// Bug: no staleness check
async alarm() {
  await this.processTick();  // expensive — 15-50 ms per call
  this.ctx.storage.setAlarm(Date.now() + 60_000);
}
```

When the runtime replayed 11 days × 1440 ticks/day = ~15 840 missed alarms per
zombie instance, each `alarm()` invocation performed the full `processTick()` work,
saturating CPU.

---

## Fix (Immediate)

Deploy a no-op `alarm()` handler that reschedules far into the future, giving the
cascade time to drain:

```ts
async alarm() {
  // Emergency: drain backlog by doing nothing and rescheduling far out.
  const EMERGENCY_DELAY_MS = 24 * 60 * 60 * 1000;
  this.ctx.storage.setAlarm(Date.now() + EMERGENCY_DELAY_MS);
}
```

This stops the CPU burst within one deploy cycle (< 2 minutes).

---

## Fix (Structural)

### 1. Guard `alarm()` against stale timestamps

```ts
async alarm() {
  const scheduled = await this.ctx.storage.getAlarm();
  const staleness = Date.now() - (scheduled ?? Date.now());

  // If alarm is more than 2 ticks late, skip work and fast-forward.
  if (staleness > 2 * TICK_INTERVAL_MS) {
    console.warn(`Stale alarm: ${staleness}ms late, skipping tick`);
    await this.ctx.storage.setAlarm(Date.now() + TICK_INTERVAL_MS);
    return;
  }

  await this.processTick();
  await this.ctx.storage.setAlarm(Date.now() + TICK_INTERVAL_MS);
}
```

### 2. Delete alarms before dormancy, restore on revival

When a DO instance goes idle (e.g., session ends), cancel any pending alarm:

```ts
async handleSessionEnd() {
  await this.ctx.storage.deleteAlarm();
  // ... cleanup
}
```

Reschedule only when the DO receives a live `fetch()` request again. This prevents
alarm backlogs from accumulating in idle instances.

### 3. Add a feature-flag guard around alarm scheduling

```ts
async fetch(request: Request) {
  const featureEnabled = await this.env.FLAGS.get('session-heartbeat-enabled');
  if (featureEnabled === 'true' && !this.alarmScheduled) {
    await this.ctx.storage.setAlarm(Date.now() + TICK_INTERVAL_MS);
    this.alarmScheduled = true;
  }
  // ...
}
```

This allows disabling the alarm work without a full redeploy during an incident.

### 4. Cap the alarm revival rate using a global KV counter

Before processing a tick in `alarm()`, check a shared KV counter that limits the
number of alarm invocations per second across all instances of the class:

```ts
async alarm() {
  const count = parseInt(await this.env.KV.get('alarm-inflight') ?? '0');
  if (count > MAX_ALARMS_PER_SECOND) {
    // Backoff and retry later
    await this.ctx.storage.setAlarm(Date.now() + jitter(5_000));
    return;
  }
  await this.env.KV.put('alarm-inflight', String(count + 1), { expirationTtl: 1 });
  await this.processTick();
  // ...
}
```

Note: KV is eventually consistent; this is a soft cap, not a hard rate limit. Combine
with the staleness guard for defence in depth.

---

## Prevention

- **Delete alarms when a DO instance becomes idle.** An idle DO with a scheduled alarm
  will eventually be evicted; on revival it may have a large backlog.
- **Design `alarm()` to be idempotent and cheap.** If an alarm fires late, the handler
  must not assume freshness or do the same amount of work it would do on-time.
- **Test revival latency with production-scale instance counts.** Create N DO instances
  in staging, evict them (via storage flush or TTL expiry), then revive them all at
  once and measure CPU profile.
- **Always have an emergency kill switch for alarm work** reachable without a full
  redeploy. A KV flag checked at the top of `alarm()` is the minimum viable switch.

---

## Anti-patterns

- **Scheduling periodic alarms in `fetch()` with only an `initialized` guard:** The
  guard may be bypassed by pre-existing storage state from test writes.
- **Performing CPU-intensive work in `alarm()` without a staleness check:** Stale
  alarms replayed at burst rates are indistinguishable from a DDoS from the CPU
  budget's perspective.
- **Dark-launching a DO class that schedules alarms:** Any DO instances created during
  the dark-launch period accumulate alarm debt that fires on full launch.
- **No feature flag inside `alarm()`:** Unlike `fetch()` handlers where a Worker
  route can intercept traffic, `alarm()` is triggered by the runtime directly and
  cannot be blocked by routing changes.

---

## Gotchas

- The Durable Objects runtime does not guarantee alarm delivery order across instances.
  During a revival cascade, alarms from different instances fire interleaved, not
  instance-by-instance.
- `ctx.storage.deleteAlarm()` is not available in all Durable Objects runtime versions.
  Confirm your Workers compatibility date supports it before relying on it.
- `ctx.storage.getAlarm()` returns `null` if no alarm is scheduled, not `0`. Always
  handle the null case.
- A DO instance that is evicted mid-alarm (due to CPU timeout) will re-attempt the
  alarm on the next revival. Ensure `alarm()` is idempotent so retries are safe.
- The per-class CPU budget is not documented as a specific number. Treat any sudden
  503 spike on a DO class as a potential CPU exhaustion event and check tail-Worker
  logs for `CPU limit exceeded` entries.

---

## Verification

1. Deploy the structural fix to staging. Create 1 000 DO instances, pause traffic for
   1 hour (simulating dormancy), then resume. Confirm `alarm()` fires with the
   staleness guard skipping stale ticks.
2. Measure `alarm()` CPU time per invocation in Workers Analytics. It should be < 5 ms
   on a skipped (stale) tick and < 20 ms on a live tick.
3. Confirm `ctx.storage.deleteAlarm()` is called in the session-end path by checking
   that alarm counts drop to zero after sessions close.
4. Run a load test simulating 10 000 simultaneous DO revivals. Confirm no 503 errors
   and CPU time per alarm stays within budget.

---

## Related

- `durable-object-alarm-silent-failure-payment-reminders.md`
- `durable-objects-storage-quota-limit-incident.md`
- `durable-objects-websocket-hibernation-migration-adr.md`
- `queue-backlog-death-spirals.md`
- `circuit-breaker-prevents-cascade-failure.md`

---

## Sources

- Cloudflare Durable Objects Alarms documentation:
  https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare Workers CPU limits:
  https://developers.cloudflare.com/workers/platform/limits/
- Internal postmortem ticket PM-2026-021 (restricted)
- Cloudflare Discord #durable-objects thread, 2026-04-09
