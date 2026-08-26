# Cloudflare Health Checks for Origin Monitoring

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your origin server occasionally becomes unreachable — a container OOM-kills the process, a database connection pool exhausts, or a deployment leaves the app in a 502 state — but you only learn about it from user complaints minutes later. You need continuous, Cloudflare-side health probing that fires an alert the moment the origin degrades, independently of any synthetic test you run from a third-party region.

## Context

Cloudflare offers two distinct health-check products:

1. **Standalone Health Checks** (under Traffic > Health Checks in the dashboard) — periodic HTTP or TCP probes to one or more origins, with email/webhook notifications. Available on all paid plans.
2. **Load Balancer Health Monitors** — probes attached to a Load Balancer pool; origins are automatically removed from rotation when they fail. Requires Load Balancing add-on.

This article covers the standalone product. If you are already running a Load Balancer, configure health on the pool monitor instead — running both doubles probe traffic without extra benefit.

Cloudflare's probes originate from the same edge PoPs that serve your traffic, so they are testing the real network path, not a synthetic path from a third-party monitoring vendor. Probe frequency is as low as 60 seconds on free/pro and 15 seconds on Business/Enterprise.

## Configuring a Standalone Health Check via the API

The dashboard is adequate for simple cases. The API is mandatory when you need to manage checks as code or integrate with CI/CD deployments.

```bash
# Create a health check
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/healthchecks" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "api-origin-health",
    "description": "HTTP health probe for api.example.com",
    "type": "HTTP",
    "address": "origin.example.com",
    "port": 443,
    "path": "/healthz",
    "method": "GET",
    "expected_codes": "200",
    "follow_redirects": false,
    "allow_insecure": false,
    "interval": 60,
    "retries": 2,
    "timeout": 5,
    "check_regions": ["WEU", "ENAM", "APAC"],
    "notification_email": "ops@example.com",
    "suspend": false,
    "consecutive_fails": 2,
    "consecutive_successes": 2
  }'
```

Key fields:

- `consecutive_fails` — how many consecutive probe failures before the check is marked unhealthy. Set to 2 to avoid single-packet loss events flapping alerts.
- `consecutive_successes` — required successes before returning to healthy. Mirrors `consecutive_fails` so recovery is as strict as failure detection.
- `check_regions` — list of Cloudflare regions from which probes are launched. Use at least two geographically spread regions to avoid false positives from a single PoP issue.
- `retries` — per-probe retries before counting a probe as failed. `retries: 2` means three attempts per probe cycle.

Available region codes: `WNAM`, `ENAM`, `WEU`, `EEU`, `NSAM`, `SSAM`, `OC`, `ME`, `NAF`, `SAF`, `SAS`, `SEAS`, `NEAS`.

## Configuring TCP Health Checks

Use a TCP check when the service speaks a non-HTTP protocol, or when you want to verify raw port reachability without touching the application layer.

```bash
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/healthchecks" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "postgres-primary-tcp",
    "type": "TCP",
    "address": "db.internal.example.com",
    "port": 5432,
    "interval": 60,
    "retries": 1,
    "timeout": 5,
    "consecutive_fails": 3,
    "consecutive_successes": 1,
    "check_regions": ["WEU", "ENAM"]
  }'
```

Note: TCP checks only test that the port accepts a connection. They do not verify application-level health (e.g., a PostgreSQL instance that accepts connections but refuses queries due to max_connections will still pass a TCP probe). Pair with an HTTP `/healthz` check at the application layer.

## Routing Notifications to PagerDuty via Cloudflare Webhook Notifications

The built-in email notification is adequate for awareness but does not integrate with on-call rotation. Use Cloudflare's notification webhook to route health-check state changes into PagerDuty.

### Step 1: Create a PagerDuty integration key

In PagerDuty: Service > Integrations > Add integration > "Events API v2". Copy the integration key.

### Step 2: Create a Cloudflare notification webhook

```bash
# Register the PagerDuty endpoint as a webhook destination
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/alerting/v3/destinations/webhooks" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "pagerduty-health-checks",
    "url": "https://events.pagerduty.com/v2/enqueue",
    "secret": ""
  }'
```

### Step 3: Create a notification policy

```bash
# Map health check events to the webhook
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/alerting/v3/policies" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "health-check-degraded-to-pd",
    "alert_type": "health_check_status_notification",
    "enabled": true,
    "mechanisms": {
      "webhooks": [{"id": "<WEBHOOK_DESTINATION_ID>"}]
    },
    "filters": {
      "health_check_id": ["<HEALTH_CHECK_ID>"],
      "status": ["Unhealthy", "Degraded"]
    }
  }'
```

The Cloudflare notification payload is generic JSON; PagerDuty's Events API v2 expects a specific shape. Use a Cloudflare Worker as an adapter if you need proper `dedup_key`, `severity`, and `component` fields in PagerDuty.

## Worker Adapter: Translating Cloudflare Health Check Webhooks to PagerDuty Events API v2

```javascript
// health-check-pd-adapter/src/index.js
export default {
  async fetch(request, env) {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const payload = await request.json();

    // Cloudflare sends alert_type, data.health_check_id, data.status, etc.
    const status = payload?.data?.status ?? 'Unknown';
    const checkName = payload?.data?.name ?? 'unknown-check';
    const checkId = payload?.data?.health_check_id ?? 'unknown';

    const isRecovery = status === 'Healthy';

    const pdEvent = {
      routing_key: env.PD_INTEGRATION_KEY,
      event_action: isRecovery ? 'resolve' : 'trigger',
      dedup_key: `cf-healthcheck-${checkId}`,
      payload: {
        summary: `[${status}] Cloudflare Health Check: ${checkName}`,
        source: 'cloudflare-health-checks',
        severity: isRecovery ? 'info' : 'critical',
        component: checkName,
        custom_details: payload.data ?? {},
      },
    };

    const resp = await fetch('https://events.pagerduty.com/v2/enqueue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pdEvent),
    });

    const result = await resp.json();
    return new Response(JSON.stringify(result), {
      status: resp.status,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

Deploy this Worker on a Workers route and point the Cloudflare notification webhook to its URL. The `dedup_key` matches trigger and resolve events so PagerDuty auto-resolves incidents when the origin recovers.

## Listing and Auditing Health Checks as Code

```bash
# List all checks in a zone
curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/healthchecks" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | {id, name, type, address, port, status: .status.status}'

# Fetch current status snapshot
curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/healthchecks/${HC_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result.status'
```

The `status` object returned includes `status` (`healthy`, `unhealthy`, `degraded`) and `failure_reason` (the last probe error message). Scrape this on a schedule from a Workers Cron trigger to export origin health as a custom Analytics Engine metric.

```javascript
// Export health check status into Analytics Engine
export default {
  async scheduled(event, env) {
    const resp = await fetch(
      `https://api.cloudflare.com/client/v4/zones/${env.ZONE_ID}/healthchecks`,
      { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
    );
    const { result } = await resp.json();

    const statusMap = { healthy: 1, degraded: 0.5, unhealthy: 0 };
    const now = Date.now();

    for (const hc of result) {
      env.ANALYTICS.writeDataPoint({
        blobs: [hc.name, hc.address, hc.status?.status ?? 'unknown'],
        doubles: [statusMap[hc.status?.status] ?? 0],
        indexes: [hc.id],
      });
    }
  },
};
```

This gives you a queryable time-series of origin health that can be visualized in Grafana via the Analytics Engine datasource.

## Anti-patterns

- **Probing a Cloudflare-proxied hostname** — if `address` resolves through Cloudflare's proxy (orange-cloud), the probe hits the edge cache, not the origin. Set `address` to the origin IP or a grey-cloud DNS name.
- **Single check-region** — a probe from one region can fail due to regional routing issues unrelated to your origin. Use at least two geographically distinct regions and set `consecutive_fails` ≥ 2.
- **Using the health-check path as the deep health path** — `/healthz` must respond within `timeout` seconds. If your database connection test inside `/healthz` takes 4 seconds and your timeout is 5, you have 1 second of margin. Instrument the health endpoint separately from application request latency.
- **Not pairing with load balancer health** — if you have a Load Balancer, the standalone health check fires an alert but does not pull traffic. Enable health monitors on the pool to get both alerting and automatic failover.

## Gotchas

- **Probe IP ranges change** — Cloudflare periodically adds PoP IPs. If your firewall allowlists Cloudflare probe IPs, subscribe to `https://api.cloudflare.com/client/v4/ips` and automate the allowlist refresh.
- **`suspended: true` silently stops probing** — the API accepts `suspend` on create/update. A suspended check still appears in the list and retains its last status. Always check the `suspended` field when auditing.
- **Email notifications have a minimum of 30-minute deduplication** — Cloudflare de-dupes notification emails per check per 30 minutes. For faster incident response, always use a webhook to PagerDuty or Slack.
- **Notification policies are account-scoped, health checks are zone-scoped** — you need both the zone ID (for health check CRUD) and the account ID (for notification policies and webhooks). These are different API namespaces.

## Verification

1. Temporarily block traffic from Cloudflare IP ranges at your origin firewall; within `(interval × (consecutive_fails + retries))` seconds the check should transition to `unhealthy`.
2. Confirm the PagerDuty incident fires with the correct `dedup_key`.
3. Restore access; confirm the PagerDuty incident resolves automatically.
4. Query Analytics Engine to confirm the status time-series recorded the gap:
   ```sql
   SELECT blob1 AS check_name, double1 AS health_score, timestamp
   FROM analytics_engine_dataset
   WHERE timestamp > NOW() - INTERVAL '1' HOUR
   ORDER BY timestamp ASC
   ```

## Related

- `health-check-endpoint-design.md` — designing the `/healthz` endpoint the probe hits
- `uptime-monitoring-workers-cron-synthetic.md` — synthetic uptime probes from Workers Cron
- `workers-error-alerting-pagerduty-integration.md` — routing Worker errors to PagerDuty
- `cloudflare-analytics-engine.md` — writing custom metrics from Workers

## Sources

- Cloudflare Health Checks API: https://developers.cloudflare.com/health-checks/
- Cloudflare Notifications API: https://developers.cloudflare.com/notifications/
- PagerDuty Events API v2: https://developer.pagerduty.com/docs/events-api-v2/
- Cloudflare IP ranges: https://www.cloudflare.com/ips/
