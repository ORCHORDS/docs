# Status Page Automation with Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You operate a public-facing service and your status page is perpetually out of date. When an incident starts, someone must manually post an update to Statuspage or Instatus. By the time the post is up, customers have already tweeted. You want the status page to reflect real-time origin health — updated automatically within 60 seconds of a degradation, without a human in the loop for the initial "Investigating" update.

## Context

This article covers two automation patterns:

1. **Poll-then-push** — a Cloudflare Workers Cron trigger probes your own `/healthz` endpoints from multiple regions and posts a component status update to a hosted status page provider (Statuspage.io or Instatus) when degradation is detected.
2. **Health-check-webhook-bridge** — a Worker receives Cloudflare Health Check webhook notifications and translates them into status page component updates in real time.

Pattern 2 is preferred when you are already using Cloudflare's standalone Health Checks (see `cloudflare-health-checks-origin-monitoring.md`) because it avoids duplicating probe logic. Pattern 1 is a self-contained fallback that works without a paid Cloudflare plan.

Both patterns require:
- A status page provider account (Statuspage.io or Instatus) with API access.
- A Workers secret binding for the status page API key.
- A mapping between your service components and the provider's component IDs.

## Pattern 1: Cron Trigger Polling

```toml
# wrangler.toml
name = "status-page-automation"
main = "src/index.js"
compatibility_date = "2024-11-01"

[vars]
CHECK_REGIONS = '["WEU","ENAM","APAC"]'
PROBE_TIMEOUT_MS = "5000"

[[triggers.crons]]
cron = "*/1 * * * *"  # Every minute

[secrets]
# Set via: wrangler secret put STATUSPAGE_API_KEY
# Set via: wrangler secret put STATUSPAGE_PAGE_ID
```

```javascript
// src/index.js
const COMPONENT_MAP = {
  'api.example.com': 'comp_api_id',
  'app.example.com': 'comp_web_id',
  'cdn.example.com': 'comp_cdn_id',
};

const HEALTH_PATHS = {
  'api.example.com': '/healthz',
  'app.example.com': '/health',
  'cdn.example.com': '/ping',
};

export default {
  async scheduled(event, env, ctx) {
    const results = await Promise.allSettled(
      Object.keys(COMPONENT_MAP).map((host) => probeHost(host, env))
    );

    for (let i = 0; i < results.length; i++) {
      const host = Object.keys(COMPONENT_MAP)[i];
      const componentId = COMPONENT_MAP[host];
      const result = results[i];

      let status;
      if (result.status === 'fulfilled') {
        status = result.value.ok ? 'operational' : 'degraded_performance';
        if (result.value.statusCode >= 500) status = 'major_outage';
        if (result.value.statusCode >= 400) status = 'partial_outage';
      } else {
        // Promise rejected = probe itself failed (DNS, timeout, TLS)
        status = 'major_outage';
      }

      ctx.waitUntil(
        updateStatuspageComponent(componentId, status, env)
      );
    }
  },
};

async function probeHost(host, env) {
  const path = HEALTH_PATHS[host] ?? '/healthz';
  const url = `https://${host}${path}`;

  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    parseInt(env.PROBE_TIMEOUT_MS ?? '5000', 10)
  );

  try {
    const resp = await fetch(url, {
      signal: controller.signal,
      headers: { 'User-Agent': 'status-page-probe/1.0' },
    });
    return { ok: resp.ok, statusCode: resp.status };
  } finally {
    clearTimeout(timeout);
  }
}

async function updateStatuspageComponent(componentId, status, env) {
  const url = `https://api.statuspage.io/v1/pages/${env.STATUSPAGE_PAGE_ID}/components/${componentId}`;
  const resp = await fetch(url, {
    method: 'PATCH',
    headers: {
      Authorization: `OAuth ${env.STATUSPAGE_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ component: { status } }),
  });

  if (!resp.ok) {
    console.error(
      `Failed to update component ${componentId} to ${status}:`,
      resp.status,
      await resp.text()
    );
  }
}
```

## Pattern 2: Health Check Webhook Bridge

When using Cloudflare Health Checks, configure the notification webhook to point to a Worker that translates the payload and calls the status page API.

```javascript
// src/bridge.js
export default {
  async fetch(request, env) {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    // Optional: verify Cloudflare webhook signature
    const body = await request.text();
    const payload = JSON.parse(body);

    const healthCheckName = payload?.data?.name;
    const cfStatus = payload?.data?.status; // 'Healthy' | 'Unhealthy' | 'Degraded'

    if (!healthCheckName || !cfStatus) {
      return new Response('Missing fields', { status: 400 });
    }

    // Map Cloudflare health check name to Statuspage component ID
    const componentId = env.COMPONENT_MAP
      ? JSON.parse(env.COMPONENT_MAP)[healthCheckName]
      : null;

    if (!componentId) {
      console.warn(`No component mapping for health check: ${healthCheckName}`);
      return new Response('No mapping', { status: 200 });
    }

    const statuspageStatus = {
      Healthy: 'operational',
      Degraded: 'degraded_performance',
      Unhealthy: 'major_outage',
    }[cfStatus] ?? 'under_maintenance';

    await updateStatuspageComponent(componentId, statuspageStatus, env);

    // Optionally create/resolve an incident automatically
    if (cfStatus === 'Unhealthy') {
      await createInvestigatingIncident(componentId, healthCheckName, env);
    } else if (cfStatus === 'Healthy') {
      await resolveOpenIncident(componentId, healthCheckName, env);
    }

    return new Response('OK', { status: 200 });
  },
};
```

## Auto-Creating and Resolving Incidents

Updating a component status is often enough for monitoring consumers. However, posting a visible incident communicates a narrative. Automate the first incident post ("Investigating") and the resolution; leave manual control for the "Identified" and "Update" posts that require human judgment.

```javascript
async function createInvestigatingIncident(componentId, componentName, env) {
  // First check if an open incident for this component already exists to avoid duplicates
  const existing = await getOpenIncident(componentName, env);
  if (existing) return;

  const resp = await fetch(
    `https://api.statuspage.io/v1/pages/${env.STATUSPAGE_PAGE_ID}/incidents`,
    {
      method: 'POST',
      headers: {
        Authorization: `OAuth ${env.STATUSPAGE_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        incident: {
          name: `Investigating issue with ${componentName}`,
          status: 'investigating',
          impact_override: 'minor',
          body: 'We are investigating reports of degraded performance. This post will be updated as more information becomes available.',
          component_ids: [componentId],
          components: { [componentId]: 'degraded_performance' },
          deliver_notifications: true,
          auto_transition_to_maintenance_state: false,
        },
      }),
    }
  );

  const incident = await resp.json();
  // Store incident ID in KV so we can resolve it later
  await env.STATUS_KV.put(
    `incident:${componentName}`,
    JSON.stringify({ id: incident.id, openedAt: Date.now() }),
    { expirationTtl: 86400 }
  );
}

async function resolveOpenIncident(componentId, componentName, env) {
  const raw = await env.STATUS_KV.get(`incident:${componentName}`);
  if (!raw) return;

  const { id } = JSON.parse(raw);

  await fetch(
    `https://api.statuspage.io/v1/pages/${env.STATUSPAGE_PAGE_ID}/incidents/${id}`,
    {
      method: 'PATCH',
      headers: {
        Authorization: `OAuth ${env.STATUSPAGE_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        incident: {
          status: 'resolved',
          body: 'This incident has been resolved. All systems are now operating normally.',
          components: { [componentId]: 'operational' },
          deliver_notifications: true,
        },
      }),
    }
  );

  await env.STATUS_KV.delete(`incident:${componentName}`);
}
```

KV bindings needed:
```toml
[[kv_namespaces]]
binding = "STATUS_KV"
id = "<KV_NAMESPACE_ID>"
```

## Instatus Alternative

If you use Instatus instead of Statuspage.io, the API shape differs slightly:

```javascript
async function updateInstatus(componentId, status, env) {
  // Instatus statuses: 'OPERATIONAL' | 'UNDERMAINTENANCE' | 'DEGRADEDPERFORMANCE'
  //                    | 'PARTIALOUTAGE' | 'MAJOROUTAGE'
  const instatus = {
    operational: 'OPERATIONAL',
    degraded_performance: 'DEGRADEDPERFORMANCE',
    partial_outage: 'PARTIALOUTAGE',
    major_outage: 'MAJOROUTAGE',
  };

  await fetch(
    `https://api.instatus.com/v1/${env.INSTATUS_PAGE_ID}/components/${componentId}`,
    {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${env.INSTATUS_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ status: instatus[status] ?? 'UNDERMAINTENANCE' }),
    }
  );
}
```

## Anti-patterns

- **Updating status on every cron tick without state comparison** — if the component is already `operational`, POSTing `operational` again generates noise in the audit log and burns API rate limits. Read current status from KV (where you cache it after each update) and only call the API when status changes.
- **Not rate-limiting the bridge Worker** — a misconfigured Cloudflare Health Check can fire notifications in a tight loop. Add a KV-based rate limiter (one update per component per minute) in the bridge to protect Statuspage API quotas.
- **Resolving incidents automatically without a cooldown** — a flapping origin (fail → recover → fail in under 2 minutes) produces a flood of incident open/resolve emails to subscribers. Require the origin to be healthy for at least 3 consecutive checks before resolving, using a counter in KV.
- **Storing API keys in `[vars]` instead of secrets** — `[vars]` values are visible in the Cloudflare dashboard. Always use `wrangler secret put` for credentials.

## Gotchas

- **Statuspage API rate limit** — Statuspage.io caps component update requests at 20 per minute per page. With many components and a 1-minute cron, you can exceed this. Batch updates or stagger across 30-second intervals.
- **Cron trigger minimum granularity is 1 minute** — you cannot schedule a Worker more frequently than every minute. For sub-minute health visibility, use Cloudflare Health Checks (15-second probes on Business/Enterprise) paired with the webhook bridge.
- **Workers do not receive their own subdomain as origin** — do not probe `your-worker.workers.dev` from another Worker Cron; the probe will be served by the edge, not the origin. Probe the true origin IP or hostname directly.
- **Statuspage component status vocabulary** — allowed values are `operational`, `degraded_performance`, `partial_outage`, `major_outage`, `under_maintenance`. Any other string returns a 422.

## Verification

1. Force a health check failure (return 500 from `/healthz`) and wait one cron cycle.
2. Confirm the Statuspage component transitions from `operational` to `major_outage`.
3. Confirm a new incident is created with status `investigating`.
4. Restore the endpoint to healthy; wait one cycle.
5. Confirm the component returns to `operational` and the incident is resolved.
6. Check KV for residual incident keys — there should be none after resolution.

## Related

- `cloudflare-health-checks-origin-monitoring.md` — Cloudflare Health Checks for the webhook source
- `status-page-communication-discipline.md` — communication standards during incidents
- `uptime-monitoring-workers-cron-synthetic.md` — broader synthetic monitoring from Workers Cron
- `incident-severity-classification-automation.md` — automated severity routing

## Sources

- Statuspage.io API: https://developer.statuspage.io/
- Instatus API: https://instatus.com/help/api
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare Notifications: https://developers.cloudflare.com/notifications/
