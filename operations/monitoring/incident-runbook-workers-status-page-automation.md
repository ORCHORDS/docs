# Automated Incident Runbook: Workers Detects Degradation and Updates Status Page

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

During an outage, on-call engineers spend the first critical minutes manually posting status page updates and notifying stakeholders instead of diagnosing the problem. A scheduled Worker that continuously evaluates error-rate and latency thresholds can open incidents automatically on a status page API and page on-call engineers via PagerDuty, so humans focus entirely on remediation from the moment they receive the alert.

## Context

The runbook Worker runs on a 1-minute cron trigger, queries the last 5-minute aggregates from Analytics Engine, and compares them against per-route SLO thresholds stored in a Durable Object. When a threshold is breached it creates or updates an incident on Betterstack (or Atlassian Statuspage) and enqueues a PagerDuty event. A Durable Object (`IncidentRegistry`) acts as the source of truth for open incidents, preventing duplicate pages and ensuring a single `resolve` event fires when the condition clears. Runbook steps are embedded as structured metadata on the PagerDuty event so the responder sees them immediately in the mobile app.

## Durable Object — Incident Registry

```typescript
// durable-objects/incident-registry.ts
export interface OpenIncident {
  id: string;           // PagerDuty dedup key
  route: string;
  metric: string;
  openedAt: number;     // Unix ms
  statusPageId?: string;
}

export class IncidentRegistry {
  private readonly state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const { action, incident } = await request.json() as {
      action: "open" | "resolve" | "list";
      incident?: OpenIncident;
    };

    if (action === "open" && incident) {
      const existing = await this.state.storage.get<OpenIncident>(incident.id);
      if (existing) return Response.json({ already_open: true, incident: existing });
      await this.state.storage.put(incident.id, incident);
      return Response.json({ opened: true, incident });
    }

    if (action === "resolve" && incident) {
      const existing = await this.state.storage.get<OpenIncident>(incident.id);
      if (!existing) return Response.json({ not_found: true });
      await this.state.storage.delete(incident.id);
      return Response.json({ resolved: true, incident: existing });
    }

    if (action === "list") {
      const all = await this.state.storage.list<OpenIncident>();
      return Response.json({ incidents: [...all.values()] });
    }

    return new Response("Bad action", { status: 400 });
  }
}
```

## Runbook Worker — Detection and Dispatch

```typescript
// workers/runbook/index.ts
export interface Env {
  INCIDENT_REGISTRY: DurableObjectNamespace;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  PAGERDUTY_KEY: string;
  STATUSPAGE_API_KEY: string;
  STATUSPAGE_PAGE_ID: string;
}

interface RouteHealth {
  route: string;
  error_rate: number;
  p99_ms: number;
  requests: number;
}

const THRESHOLDS: Record<string, { error_rate: number; p99_ms: number }> = {
  "/api/v1/checkout":   { error_rate: 0.01, p99_ms: 3000 },
  "/api/v1/products":   { error_rate: 0.02, p99_ms: 1500 },
  "/api/v1/search":     { error_rate: 0.05, p99_ms: 2000 },
};

const RUNBOOK_STEPS = {
  error_rate: [
    "1. Check Cloudflare Workers tail: `wrangler tail <worker-name> --format pretty`",
    "2. Review recent deployments in the Cloudflare dashboard or `wrangler deployments list`",
    "3. Check D1 / KV bindings for timeouts: look for 'Error: Timeout' in tail output",
    "4. If a bad deploy: `wrangler rollback` to the previous version",
  ],
  p99_ms: [
    "1. Check Workers CPU time in Analytics (Workers > Metrics > CPU time p99)",
    "2. Run EXPLAIN on slow D1 queries identified in the last 15 min of logs",
    "3. Check upstream API health via health-check endpoint",
    "4. Consider enabling Workers Smart Placement for latency-sensitive routes",
  ],
};

async function queryHealth(accountId: string, apiToken: string): Promise<RouteHealth[]> {
  const sql = `
    SELECT
      blob1                              AS route,
      countIf(double2 >= 500) / count()  AS error_rate,
      quantileWeighted(0.99)(double1, 1) AS p99_ms,
      count()                            AS requests
    FROM worker_requests
    WHERE timestamp >= now() - INTERVAL '5' MINUTE
    GROUP BY route
    HAVING requests >= 10
  `;
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${apiToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ query: sql }),
    },
  );
  const json = await res.json() as { data: RouteHealth[] };
  return json.data;
}

async function registryRequest(
  ns: DurableObjectNamespace,
  body: object,
): Promise<Response> {
  const stub = ns.get(ns.idFromName("global"));
  return stub.fetch("https://do/registry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const rows = await queryHealth(env.CF_ACCOUNT_ID, env.CF_API_TOKEN);

    for (const row of rows) {
      const thresholds = THRESHOLDS[row.route];
      if (!thresholds) continue;

      for (const metric of ["error_rate", "p99_ms"] as const) {
        const value = row[metric];
        const threshold = thresholds[metric];
        const breached = value > threshold;
        const dedupKey = `${row.route}::${metric}`;

        if (breached) {
          const regRes = await registryRequest(env.INCIDENT_REGISTRY, {
            action: "open",
            incident: { id: dedupKey, route: row.route, metric, openedAt: Date.now() },
          });
          const reg = await regRes.json() as { already_open: boolean; incident: { statusPageId?: string } };
          if (reg.already_open) continue;  // already paging, avoid duplicate

          // Open status page incident
          const spId = await openStatusPageIncident(env, row.route, metric, value, threshold);

          // Update registry with status page ID
          await registryRequest(env.INCIDENT_REGISTRY, {
            action: "open",
            incident: { id: dedupKey, route: row.route, metric, openedAt: Date.now(), statusPageId: spId },
          });

          // Page on-call
          await pagePagerDuty(env.PAGERDUTY_KEY, dedupKey, row.route, metric, value, threshold);
        } else {
          // Auto-resolve
          const regRes = await registryRequest(env.INCIDENT_REGISTRY, {
            action: "resolve",
            incident: { id: dedupKey, route: row.route, metric, openedAt: 0 },
          });
          const reg = await regRes.json() as { not_found?: boolean; incident?: { statusPageId?: string } };
          if (reg.not_found) continue;

          if (reg.incident?.statusPageId) {
            await resolveStatusPageIncident(env, reg.incident.statusPageId);
          }
          await resolvePagerDuty(env.PAGERDUTY_KEY, dedupKey);
        }
      }
    }
  },
};

async function openStatusPageIncident(
  env: Env, route: string, metric: string, value: number, threshold: number,
): Promise<string> {
  const res = await fetch(`https://betterstack.com/api/v2/incidents`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.STATUSPAGE_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name: `Elevated ${metric} on ${route}`,
      summary: `${metric} = ${value.toFixed(3)} (threshold ${threshold}). Auto-detected by runbook Worker.`,
      status: "investigating",
    }),
  });
  const json = await res.json() as { data: { id: string } };
  return json.data.id;
}

async function resolveStatusPageIncident(env: Env, incidentId: string): Promise<void> {
  await fetch(`https://betterstack.com/api/v2/incidents/${incidentId}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${env.STATUSPAGE_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ status: "resolved" }),
  });
}

async function pagePagerDuty(
  key: string, dedupKey: string, route: string, metric: string, value: number, threshold: number,
): Promise<void> {
  const steps = RUNBOOK_STEPS[metric] ?? [];
  await fetch("https://events.pagerduty.com/v2/enqueue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      routing_key: key,
      event_action: "trigger",
      dedup_key: dedupKey,
      payload: {
        summary: `${route} ${metric} breached: ${value.toFixed(3)} > ${threshold}`,
        severity: "critical",
        source: "workers-runbook",
        custom_details: { route, metric, value, threshold, runbook: steps },
      },
    }),
  });
}

async function resolvePagerDuty(key: string, dedupKey: string): Promise<void> {
  await fetch("https://events.pagerduty.com/v2/enqueue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ routing_key: key, event_action: "resolve", dedup_key: dedupKey }),
  });
}
```

## Anti-patterns

- Storing open incident state in a Workers global variable — isolates are evicted; the Durable Object is the only correct place for durable runbook state.
- Not using a dedup key on PagerDuty events — a 1-minute cron without dedup fires a new alert every minute, generating dozens of pages before anyone can ack.
- Opening status page incidents without an auto-resolve path — incidents accumulate and erode customer trust in the status page.

## Gotchas

- Betterstack and Atlassian Statuspage have different REST shapes; the `openStatusPageIncident` helper above targets Betterstack. Adapt the endpoint and body schema when using Atlassian.
- The 5-minute Analytics Engine window can lag by up to 60 seconds; a persistent breach that is already resolving may trigger an alert and an immediate auto-resolve within the same cron cycle. Add a minimum open duration (e.g. 2 consecutive breached ticks) before paging.

## Verification

```bash
# Manually trigger the cron to test the full runbook without waiting for the minute boundary
wrangler scheduled-event runbook --trigger-type scheduled

# Check open incidents in the Durable Object via a debug fetch
curl -X POST https://your-worker.workers.dev/__debug/incidents \
  -d '{"action":"list"}' -H "x-debug-key: $DEBUG_KEY"

# Tail to watch detection logic in real time
wrangler tail runbook --format pretty | grep -E "breach|open|resolve|page"
```

## Related

- `monitoring/workers-error-alerting-pagerduty-integration.md`
- `monitoring/status-page-automation-workers.md`
- `monitoring/analytics-engine-sql-api-programmatic-querying.md`
- `monitoring/durable-objects-alarm-heartbeat-monitoring.md`
- `monitoring/escalation-policy-design.md`

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTgx-send-an-alert-event
- https://betterstack.com/docs/uptime/api/incidents/
