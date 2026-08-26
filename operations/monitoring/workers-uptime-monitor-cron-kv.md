# External Uptime Monitoring Using Workers Cron + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need a lightweight, serverless uptime monitor that probes external HTTP endpoints on a schedule, tracks incident state, stores historical uptime in KV for a status page, and sends alerts via MailChannels when a service transitions between up and down states — without operating any additional infrastructure.

## Context

Cloudflare Workers support cron triggers that fire on a schedule defined in `wrangler.toml`. KV is used for two purposes: persisting the current probe state (up/down) between cron invocations and storing aggregated uptime history for a public status page endpoint. MailChannels is available inside Workers to send transactional email without an SMTP server.

## Solution

### wrangler.toml

```toml
name = "uptime-monitor"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[triggers]]
crons = ["* * * * *"]  # every minute

[[kv_namespaces]]
binding = "UPTIME_KV"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
ALERT_FROM = "alerts@example.com"
ALERT_TO   = "oncall@example.com"
FAILURE_THRESHOLD = "3"
PROBE_TIMEOUT_MS  = "5000"
```

### Probe target definition

```typescript
// src/targets.ts

export interface ProbeTarget {
  id: string;
  name: string;
  url: string;
  method: 'GET' | 'HEAD';
  expectedStatus: number;
  timeoutMs: number;
}

export const TARGETS: ProbeTarget[] = [
  {
    id: 'api-prod',
    name: 'Production API',
    url: 'https://api.example.com/healthz',
    method: 'GET',
    expectedStatus: 200,
    timeoutMs: 5000,
  },
  {
    id: 'dashboard',
    name: 'Dashboard',
    url: 'https://app.example.com/ping',
    method: 'HEAD',
    expectedStatus: 200,
    timeoutMs: 5000,
  },
];
```

### HTTP probe with timeout

```typescript
// src/probe.ts

import type { ProbeTarget } from './targets';

export interface ProbeResult {
  targetId: string;
  ok: boolean;
  statusCode: number | null;
  durationMs: number;
  error?: string;
}

export async function probeTarget(target: ProbeTarget): Promise<ProbeResult> {
  const start = Date.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), target.timeoutMs);

  try {
    const res = await fetch(target.url, {
      method: target.method,
      signal: controller.signal,
      headers: { 'User-Agent': 'orchords-uptime-monitor/1.0' },
    });
    clearTimeout(timer);
    const durationMs = Date.now() - start;
    const ok = res.status === target.expectedStatus;
    return { targetId: target.id, ok, statusCode: res.status, durationMs };
  } catch (err: unknown) {
    clearTimeout(timer);
    const error = err instanceof Error ? err.message : 'unknown';
    const isTimeout = error.includes('abort') || error.includes('timeout');
    return {
      targetId: target.id,
      ok: false,
      statusCode: null,
      durationMs: Date.now() - start,
      error: isTimeout ? 'TIMEOUT' : error,
    };
  }
}
```

### KV state model

```typescript
// src/state.ts

export interface TargetState {
  status: 'up' | 'down';
  consecutiveFailures: number;
  lastCheckedAt: number;   // Unix ms
  lastStatusChange: number; // Unix ms
  incidentId?: string;
}

export interface UptimeWindow {
  checks: number;
  failures: number;
  windowStartMs: number;
}

const STATE_PREFIX   = 'state:';
const HISTORY_PREFIX = 'history:';
const WINDOW_HOURS   = 24;

export async function readState(
  kv: KVNamespace,
  targetId: string
): Promise<TargetState> {
  const raw = await kv.get(`${STATE_PREFIX}${targetId}`, 'json');
  return (raw as TargetState | null) ?? {
    status: 'up',
    consecutiveFailures: 0,
    lastCheckedAt: 0,
    lastStatusChange: Date.now(),
  };
}

export async function writeState(
  kv: KVNamespace,
  targetId: string,
  state: TargetState
): Promise<void> {
  await kv.put(`${STATE_PREFIX}${targetId}`, JSON.stringify(state), {
    expirationTtl: 60 * 60 * 24 * 7, // keep 7 days
  });
}

export async function recordUptimeWindow(
  kv: KVNamespace,
  targetId: string,
  failed: boolean
): Promise<void> {
  const key = `${HISTORY_PREFIX}${targetId}:${Date.now()}`;
  const entry = { failed, ts: Date.now() };
  await kv.put(key, JSON.stringify(entry), {
    expirationTtl: 60 * 60 * WINDOW_HOURS,
  });
}

export async function calculateUptime(
  kv: KVNamespace,
  targetId: string
): Promise<number> {
  const list = await kv.list({ prefix: `${HISTORY_PREFIX}${targetId}:` });
  if (list.keys.length === 0) return 100;
  const values = await Promise.all(
    list.keys.map(k => kv.get(k.name, 'json') as Promise<{ failed: boolean } | null>)
  );
  const total = values.length;
  const failures = values.filter(v => v?.failed).length;
  return Math.round(((total - failures) / total) * 10000) / 100; // two decimal places
}
```

### Incident creation and MailChannels alert

```typescript
// src/alert.ts

async function sendAlert({
  to, from, subject, body,
}: { to: string; from: string; subject: string; body: string }) {
  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }] }],
      from: { email: from },
      subject,
      content: [{ type: 'text/plain', value: body }],
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`MailChannels error ${res.status}: ${text}`);
  }
}

export async function notifyStateChange(
  targetName: string,
  newStatus: 'up' | 'down',
  from: string,
  to: string
) {
  const emoji  = newStatus === 'down' ? '🔴' : '🟢';
  const action = newStatus === 'down' ? 'is DOWN' : 'has RECOVERED';
  await sendAlert({
    from,
    to,
    subject: `${emoji} [Uptime] ${targetName} ${action}`,
    body: `${targetName} ${action} at ${new Date().toISOString()}.`,
  });
}
```

### Main cron handler

```typescript
// src/index.ts

import { TARGETS } from './targets';
import { probeTarget } from './probe';
import { readState, writeState, recordUptimeWindow, calculateUptime } from './state';
import { notifyStateChange } from './alert';

interface Env {
  UPTIME_KV: KVNamespace;
  ALERT_FROM: string;
  ALERT_TO: string;
  FAILURE_THRESHOLD: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const threshold = parseInt(env.FAILURE_THRESHOLD, 10);

    await Promise.all(
      TARGETS.map(target => ctx.waitUntil(checkTarget(target, env, threshold)))
    );
  },

  // Optional: status page endpoint
  async fetch(request: Request, env: Env): Promise<Response> {
    const uptime = await Promise.all(
      TARGETS.map(async t => ({
        id: t.id,
        name: t.name,
        uptime24h: await calculateUptime(env.UPTIME_KV, t.id),
      }))
    );
    return Response.json({ updatedAt: new Date().toISOString(), services: uptime });
  },
} satisfies ExportedHandler<Env>;

async function checkTarget(target: typeof TARGETS[0], env: Env, threshold: number) {
  const result = await probeTarget(target);
  const state  = await readState(env.UPTIME_KV, target.id);
  const prevStatus = state.status;

  await recordUptimeWindow(env.UPTIME_KV, target.id, !result.ok);

  if (result.ok) {
    const newState = {
      ...state,
      status: 'up' as const,
      consecutiveFailures: 0,
      lastCheckedAt: Date.now(),
      lastStatusChange: prevStatus !== 'up' ? Date.now() : state.lastStatusChange,
      incidentId: undefined,
    };
    await writeState(env.UPTIME_KV, target.id, newState);
    if (prevStatus === 'down') {
      await notifyStateChange(target.name, 'up', env.ALERT_FROM, env.ALERT_TO);
    }
  } else {
    const failures = state.consecutiveFailures + 1;
    const newState = {
      ...state,
      status: failures >= threshold ? ('down' as const) : state.status,
      consecutiveFailures: failures,
      lastCheckedAt: Date.now(),
      lastStatusChange: failures === threshold ? Date.now() : state.lastStatusChange,
      incidentId: failures === threshold ? crypto.randomUUID() : state.incidentId,
    };
    await writeState(env.UPTIME_KV, target.id, newState);
    if (failures === threshold) {
      await notifyStateChange(target.name, 'down', env.ALERT_FROM, env.ALERT_TO);
    }
  }
}
```

## Implementation Details

- **Cron granularity**: Cloudflare cron supports one-minute minimum intervals. Use `* * * * *` for 1-minute probing. Multiple intervals can be listed in the `crons` array.
- **KV TTL strategy**: Set a 24-hour TTL on history entries so KV does not accumulate indefinitely. State entries get a 7-day TTL as a safety net.
- **Parallel probes**: All targets are checked in parallel via `Promise.all`. Each check is wrapped in `ctx.waitUntil` to ensure completion even if the cron event processing ends early.
- **Incident deduplication**: The `incidentId` is set exactly once when `consecutiveFailures` crosses the threshold, preventing duplicate alerts on every subsequent failure.

## Anti-patterns

- **Single-failure alerting**: Never alert on the first failure. Network glitches cause false positives. Use a consecutive-failure threshold (default: 3).
- **Storing uptime history in a single KV key**: Updating one large JSON blob on every cron creates write contention. Use separate time-stamped keys with TTL.
- **Blocking cron on alert delivery**: Wrap `notifyStateChange` in `ctx.waitUntil` if you want the alert to be best-effort and non-blocking.

## Gotchas

- `AbortController` in Workers requires `compatibility_date` `2022-08-04` or later. The signal is respected by `fetch` but not by all third-party libraries.
- KV `list` returns at most 1000 keys. For targets with high check frequency, prune history keys more aggressively or use Analytics Engine for history storage.
- MailChannels integration requires your domain to have a Cloudflare DNS record with a `mailchannels` SPF entry to avoid DMARC failures.
- Cron events do not fire during a Worker deployment. The first invocation after deployment may skip a minute.

## Verification

```bash
# Trigger cron manually with wrangler
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"

# Check status page
curl https://your-monitor-worker.example.com/

# Inspect KV state
npx wrangler kv key get --binding UPTIME_KV 'state:api-prod'
```

## Related

- `documentation/categories/monitoring/workers-error-budget-tracking-d1.md`
- `documentation/categories/monitoring/workers-structured-logging-analytics-engine.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/kv/api/
- https://support.mailchannels.com/hc/en-us/articles/4565898358413
