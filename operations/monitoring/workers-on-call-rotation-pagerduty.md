# On-Call Rotation Integration with PagerDuty via Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Alerts from your Workers monitoring pipeline need to page the right engineer immediately, deduplicate repeated notifications, auto-resolve when the condition clears, and respect on-call schedules so that incidents are routed to whoever is currently on rotation — not a static Slack channel.

## Context

PagerDuty provides the Events API v2 (REST) for triggering, acknowledging, and resolving incidents from any HTTP client. Workers can call this API from tail Workers, cron Workers, or request-path alert handlers. A deduplication key (`dedup_key`) prevents duplicate pages for the same condition. Severity levels map to PagerDuty's four tiers: `critical`, `error`, `warning`, `info`. The PagerDuty REST API (separate from Events API) lets you query the current on-call engineer and their escalation policy.

## Solution

### 1. PagerDuty Events API v2 — trigger helper

```typescript
// src/lib/pagerduty.ts
export type PDSeverity = 'critical' | 'error' | 'warning' | 'info';

export interface PDTriggerPayload {
  summary: string;       // one-line human description
  source: string;        // component/hostname that fired
  severity: PDSeverity;
  component?: string;    // e.g. 'auth-worker'
  group?: string;        // e.g. 'production'
  class?: string;        // e.g. 'latency'
  customDetails?: Record<string, unknown>;
}

export interface PDEventResult {
  dedupKey: string;
  status: 'success' | 'error';
  message: string;
}

const PD_EVENTS_URL = 'https://events.pagerduty.com/v2/enqueue';

export async function triggerAlert(
  routingKey: string,
  dedupKey: string,
  payload: PDTriggerPayload
): Promise<PDEventResult> {
  const res = await fetch(PD_EVENTS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      routing_key: routingKey,
      dedup_key: dedupKey,
      event_action: 'trigger',
      payload: {
        summary: payload.summary,
        source: payload.source,
        severity: payload.severity,
        component: payload.component,
        group: payload.group,
        class: payload.class,
        custom_details: payload.customDetails,
        timestamp: new Date().toISOString(),
      },
    }),
  });

  const json = (await res.json()) as { dedup_key?: string; status: string; message: string };
  return {
    dedupKey: json.dedup_key ?? dedupKey,
    status: res.ok ? 'success' : 'error',
    message: json.message,
  };
}

export async function resolveAlert(
  routingKey: string,
  dedupKey: string
): Promise<PDEventResult> {
  const res = await fetch(PD_EVENTS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      routing_key: routingKey,
      dedup_key: dedupKey,
      event_action: 'resolve',
    }),
  });

  const json = (await res.json()) as { dedup_key?: string; status: string; message: string };
  return {
    dedupKey: json.dedup_key ?? dedupKey,
    status: res.ok ? 'success' : 'error',
    message: json.message,
  };
}

export async function acknowledgeAlert(
  routingKey: string,
  dedupKey: string
): Promise<PDEventResult> {
  const res = await fetch(PD_EVENTS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      routing_key: routingKey,
      dedup_key: dedupKey,
      event_action: 'acknowledge',
    }),
  });

  const json = (await res.json()) as { dedup_key?: string; status: string; message: string };
  return {
    dedupKey: json.dedup_key ?? dedupKey,
    status: res.ok ? 'success' : 'error',
    message: json.message,
  };
}
```

### 2. Severity mapping from internal alert levels

```typescript
// src/lib/severity-map.ts
import { PDSeverity } from './pagerduty';

export type InternalSeverity = 'p1' | 'p2' | 'p3' | 'p4' | 'p5';

const SEVERITY_MAP: Record<InternalSeverity, PDSeverity> = {
  p1: 'critical',
  p2: 'error',
  p3: 'warning',
  p4: 'info',
  p5: 'info',
};

export function mapSeverity(internal: InternalSeverity): PDSeverity {
  return SEVERITY_MAP[internal] ?? 'info';
}

// Stable dedup key from alert name + affected entity
export function buildDedupKey(alertName: string, entity: string): string {
  return `${alertName}::${entity}`.toLowerCase().replace(/[^a-z0-9:_-]/g, '-');
}
```

### 3. Alert Worker with auto-resolve on recovery

```typescript
// src/workers/alert-dispatcher.ts
import { triggerAlert, resolveAlert, buildDedupKey, mapSeverity } from '../lib';

interface Env {
  PD_ROUTING_KEY: string;
  ALERT_STATE: KVNamespace;  // tracks open alert dedupKeys
  DB: D1Database;
}

interface AlertEvent {
  name: string;
  entity: string;
  severity: 'p1' | 'p2' | 'p3' | 'p4' | 'p5';
  summary: string;
  source: string;
  component?: string;
  details?: Record<string, unknown>;
  firing: boolean;  // true = problem, false = recovery
}

export async function dispatchAlert(env: Env, alert: AlertEvent): Promise<void> {
  const dedupKey = buildDedupKey(alert.name, alert.entity);

  if (alert.firing) {
    // Check if already open to avoid log spam (PD deduplicates via dedupKey)
    const existing = await env.ALERT_STATE.get(dedupKey);
    if (!existing) {
      await env.ALERT_STATE.put(dedupKey, new Date().toISOString(), {
        expirationTtl: 86_400, // auto-expire state after 24h as safety net
      });
    }

    const result = await triggerAlert(env.PD_ROUTING_KEY, dedupKey, {
      summary: alert.summary,
      source: alert.source,
      severity: mapSeverity(alert.severity),
      component: alert.component,
      customDetails: alert.details,
    });

    console.log(`[PD] trigger sent dedupKey=${dedupKey} status=${result.status}`);

    // Persist incident record
    await env.DB.prepare(`
      INSERT OR IGNORE INTO incidents (dedup_key, alert_name, entity, severity, summary, opened_at)
      VALUES (?, ?, ?, ?, ?, datetime('now'))
    `).bind(dedupKey, alert.name, alert.entity, alert.severity, alert.summary).run();
  } else {
    // Recovery path
    const wasOpen = await env.ALERT_STATE.get(dedupKey);
    if (wasOpen) {
      await env.ALERT_STATE.delete(dedupKey);
      const result = await resolveAlert(env.PD_ROUTING_KEY, dedupKey);
      console.log(`[PD] resolve sent dedupKey=${dedupKey} status=${result.status}`);

      await env.DB.prepare(`
        UPDATE incidents SET resolved_at = datetime('now') WHERE dedup_key = ? AND resolved_at IS NULL
      `).bind(dedupKey).run();
    }
  }
}
```

### 4. Query current on-call from PagerDuty API

```typescript
// src/lib/pd-oncall.ts
interface OnCallUser {
  id: string;
  name: string;
  email: string;
  schedule_name: string;
  escalation_policy: string;
}

export async function getCurrentOnCall(
  pdApiToken: string,
  scheduleId: string
): Promise<OnCallUser[]> {
  const url = new URL('https://api.pagerduty.com/oncalls');
  url.searchParams.set('schedule_ids[]', scheduleId);
  url.searchParams.set('earliest', 'true');
  url.searchParams.set('include[]', 'users');

  const res = await fetch(url.toString(), {
    headers: {
      Authorization: `Token token=${pdApiToken}`,
      Accept: 'application/vnd.pagerduty+json;version=2',
    },
  });

  if (!res.ok) throw new Error(`PD oncalls API ${res.status}`);

  const json = (await res.json()) as {
    oncalls: Array<{
      user: { id: string; name: string; email: string };
      schedule: { summary: string };
      escalation_policy: { summary: string };
    }>;
  };

  return json.oncalls.map((o) => ({
    id: o.user.id,
    name: o.user.name,
    email: o.user.email,
    schedule_name: o.schedule?.summary ?? '',
    escalation_policy: o.escalation_policy?.summary ?? '',
  }));
}

export async function getEscalationPolicy(
  pdApiToken: string,
  policyId: string
): Promise<{ name: string; num_loops: number; rules_count: number }> {
  const res = await fetch(`https://api.pagerduty.com/escalation_policies/${policyId}`, {
    headers: {
      Authorization: `Token token=${pdApiToken}`,
      Accept: 'application/vnd.pagerduty+json;version=2',
    },
  });
  if (!res.ok) throw new Error(`PD escalation policy API ${res.status}`);
  const json = (await res.json()) as {
    escalation_policy: { name: string; num_loops: number; escalation_rules: unknown[] };
  };
  const ep = json.escalation_policy;
  return { name: ep.name, num_loops: ep.num_loops, rules_count: ep.escalation_rules.length };
}
```

### 5. On-call status API endpoint

```typescript
// src/workers/oncall-status.ts
import { Hono } from 'hono';
import { getCurrentOnCall } from '../lib/pd-oncall';

interface Env {
  PD_API_TOKEN: string;
  PD_SCHEDULE_ID: string;
  ONCALL_CACHE: KVNamespace;
}

const app = new Hono<{ Bindings: Env }>();

app.get('/oncall', async (c) => {
  const cacheKey = `oncall:${c.env.PD_SCHEDULE_ID}`;
  const cached = await c.env.ONCALL_CACHE.get(cacheKey, 'json');
  if (cached) return c.json({ source: 'cache', ...cached as object });

  const oncall = await getCurrentOnCall(c.env.PD_API_TOKEN, c.env.PD_SCHEDULE_ID);
  await c.env.ONCALL_CACHE.put(cacheKey, JSON.stringify({ oncall }), { expirationTtl: 300 });
  return c.json({ source: 'live', oncall });
});

export default app;
```

## Implementation Details

- **Dedup key design**: `alertName::entity` produces a stable, deterministic key. PagerDuty will correlate all `trigger` events with the same `dedup_key` to a single incident until a `resolve` is sent.
- **KV as alert state store**: KV tracks which alerts are currently firing so the resolution path can send exactly one `resolve` event. The 24-hour TTL is a safety net for alerts that never recover (prevents stale KV entries).
- **Events API vs REST API**: The Events API (`events.pagerduty.com`) is for alert lifecycle (trigger/ack/resolve). The REST API (`api.pagerduty.com`) is for reading schedules, users, and policies. They use different auth schemes (routing key vs API token).
- **Rate limits**: Events API allows 120 requests/minute per routing key. REST API is 960 requests/minute per token. Cache on-call responses for 5 minutes in KV.

## Anti-patterns

- **No dedup key**: Omitting `dedup_key` causes PagerDuty to create a new incident on every trigger event, flooding on-call with duplicate pages.
- **Sending `resolve` without checking state**: Sending a resolve for an alert that was never opened is harmless but wastes quota and pollutes incident history.
- **Hardcoding on-call email**: Always query the schedule at alert time. Hardcoding bypasses rotations and vacations.
- **Mapping all alerts to `critical`**: Severity fatigue leads to engineers silencing alerts. Use the full severity range; only page critical for actual outages.

## Gotchas

- PagerDuty's Events API returns HTTP 202 on success (not 200). Check `res.status === 202` or `res.ok`.
- Schedule IDs and escalation policy IDs are different. The `/oncalls` endpoint needs schedule IDs; `/escalation_policies/:id` needs policy IDs.
- On-call shift boundaries: if you query `/oncalls` exactly at a shift change, you may briefly get zero results. Add a fallback to the previous on-call or alert via a secondary channel.
- Workers do not have persistent in-memory state. Always store alert state in KV, not a module-level `Map`.

## Verification

1. Call `dispatchAlert` with `firing: true` and confirm a PagerDuty incident appears within 30 seconds.
2. Call `dispatchAlert` again with the same alert name/entity — confirm no duplicate incident is created (PD deduplicates).
3. Call `dispatchAlert` with `firing: false` — confirm the incident auto-resolves in PagerDuty.
4. Hit `GET /oncall` and confirm the response includes the current on-call engineer's name and email.
5. Wait 5 minutes and call again — confirm cache hit response.

## Related

- `dead-man-switch-cron-alert` — alert source that triggers PagerDuty when a cron stops
- `workers-synthetic-monitoring-playwright` — synthetic check failures routed through this dispatcher
- `workers-dependency-health-check-service` — dependency down events dispatched via this integration
- `tail-worker-request-sampling` — tail Worker errors routed to PagerDuty

## Sources

- https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTgw-events-api-v2-overview
- https://developer.pagerduty.com/api-reference/a7d81b0e9200f-list-the-users-on-call
- https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTgx-send-an-alert-event
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
