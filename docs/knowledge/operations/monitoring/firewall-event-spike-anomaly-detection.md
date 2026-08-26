# Cloudflare Firewall Event Spike Anomaly Detection

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your WAF or rate-limiting rules start blocking a surge of requests — scraping
bursts, credential-stuffing waves, or DDoS probe traffic — but you only notice
it 30 minutes later when a human checks the dashboard. You need automated
detection that fires within 2–5 minutes of an anomalous spike in firewall
events (any action: `block`, `challenge`, `jschallenge`, `managed_challenge`)
and routes an alert to PagerDuty or Slack before the spike degrades origin
capacity.

---

## Context

Cloudflare exposes firewall event data through two surfaces:

1. **GraphQL Analytics API** — `firewallEventsAdaptiveGroups` dataset
   aggregated to 1-minute buckets. Suitable for polling-based anomaly
   detection.
2. **Logpush** — real-time streaming of individual firewall events to R2,
   S3, or an HTTP endpoint. Suitable for event-driven processing.

The polling approach (GraphQL + Cron Worker) is simpler to operate and
sufficient for 2-minute detection windows. Logpush is preferred when you need
individual event details (rule ID, IP, ASN) for incident triage.

This article covers the GraphQL polling approach with a statistical anomaly
detector implemented in a Cron Worker.

---

## Detection Algorithm

A simple but effective method: compare the current 1-minute bucket count
against a trailing baseline of the same minute-of-day across the previous 7
days (same time, same zone) and alert when:

```
current_count > baseline_mean + (k * baseline_stddev)
```

where `k = 3` (three-sigma) is a reasonable starting threshold. For highly
variable traffic, use a relative threshold instead:

```
current_count > baseline_mean * multiplier  (e.g. 5×)
```

---

## TypeScript Implementation

### wrangler.toml

```toml
name = "firewall-anomaly-detector"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[triggers]
crons = ["* * * * *"]   # every minute

[vars]
CF_ZONE_TAG    = "your-zone-tag-here"
ALERT_THRESHOLD_MULTIPLIER = "5"
```

### src/index.ts

```typescript
const GQL_URL = "https://api.cloudflare.com/client/v4/graphql";

export interface Env {
  CF_API_TOKEN: string;
  CF_ZONE_TAG: string;
  ALERT_THRESHOLD_MULTIPLIER: string;
  ALERT_WEBHOOK_URL: string;    // Slack / PagerDuty webhook
  BASELINE_KV: KVNamespace;     // stores rolling baseline
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runDetection(env));
  },
};

async function runDetection(env: Env): Promise<void> {
  const now = new Date();
  const currentMinute = floorToMinute(now);
  const prevMinute    = new Date(currentMinute.getTime() - 60_000);

  // 1. Fetch last 2 minutes (the most recent complete minute)
  const current = await queryFirewallCount(env, prevMinute, currentMinute);

  // 2. Fetch baseline: same time slot for the past 7 days
  const baselineCounts = await queryBaselineWeek(env, prevMinute);

  // 3. Statistical check
  const mean   = average(baselineCounts);
  const stddev = standardDeviation(baselineCounts, mean);
  const multiplier = Number(env.ALERT_THRESHOLD_MULTIPLIER);

  // Use whichever bound is higher: absolute floor or relative
  const threshold = Math.max(mean * multiplier, mean + 3 * stddev, 100);

  if (current > threshold) {
    await sendAlert(env, {
      current,
      mean: Math.round(mean),
      threshold: Math.round(threshold),
      timestamp: prevMinute.toISOString(),
    });
  }

  // 4. Update stored baseline with today's reading
  await updateBaseline(env, prevMinute, current);
}

// ── GraphQL helpers ─────────────────────────────────────────────────────────

async function queryFirewallCount(
  env: Env,
  from: Date,
  to: Date,
): Promise<number> {
  const query = `
    query FWCount($zoneTag: String!, $from: String!, $to: String!) {
      viewer {
        zones(filter: { zoneTag: $zoneTag }) {
          firewallEventsAdaptiveGroups(
            limit: 1
            filter: {
              datetime_geq: $from
              datetime_leq: $to
              action_in: ["block","challenge","jschallenge","managed_challenge"]
            }
          ) {
            count
          }
        }
      }
    }`;

  const res = await gql(env, query, {
    zoneTag: env.CF_ZONE_TAG,
    from: from.toISOString(),
    to:   to.toISOString(),
  });

  const groups = res?.viewer?.zones?.[0]?.firewallEventsAdaptiveGroups ?? [];
  return groups[0]?.count ?? 0;
}

async function queryBaselineWeek(env: Env, minute: Date): Promise<number[]> {
  // Query the same 1-minute window on each of the past 7 days
  const counts: number[] = [];
  for (let d = 1; d <= 7; d++) {
    const from = new Date(minute.getTime() - d * 86_400_000);
    const to   = new Date(from.getTime() + 60_000);
    const c    = await queryFirewallCount(env, from, to);
    counts.push(c);
  }
  return counts;
}

async function gql(env: Env, query: string, variables: object): Promise<any> {
  const res = await fetch(GQL_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, variables }),
  });
  const { data, errors } = await res.json<any>();
  if (errors?.length) throw new Error(JSON.stringify(errors));
  return data;
}

// ── Math helpers ─────────────────────────────────────────────────────────────

function average(nums: number[]): number {
  return nums.length ? nums.reduce((s, n) => s + n, 0) / nums.length : 0;
}

function standardDeviation(nums: number[], mean: number): number {
  if (nums.length < 2) return 0;
  const variance = nums.reduce((s, n) => s + (n - mean) ** 2, 0) / nums.length;
  return Math.sqrt(variance);
}

function floorToMinute(d: Date): Date {
  return new Date(Math.floor(d.getTime() / 60_000) * 60_000);
}

// ── Alerting ─────────────────────────────────────────────────────────────────

interface AlertPayload {
  current: number;
  mean: number;
  threshold: number;
  timestamp: string;
}

async function sendAlert(env: Env, p: AlertPayload): Promise<void> {
  const body = {
    text: `Firewall spike detected at ${p.timestamp}: ${p.current} events (baseline mean: ${p.mean}, threshold: ${p.threshold})`,
    attachments: [
      {
        color: "danger",
        fields: [
          { title: "Current (1 min)", value: String(p.current), short: true },
          { title: "Baseline mean",   value: String(p.mean),    short: true },
          { title: "Threshold",       value: String(p.threshold), short: true },
        ],
      },
    ],
  };

  await fetch(env.ALERT_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── Baseline persistence in KV ────────────────────────────────────────────────

async function updateBaseline(env: Env, minute: Date, count: number): Promise<void> {
  const key = `baseline:${minute.getUTCHours()}:${minute.getUTCMinutes()}`;
  const existing = await env.BASELINE_KV.get<number[]>(key, "json") ?? [];
  const updated = [...existing.slice(-13), count]; // keep 14 days rolling
  await env.BASELINE_KV.put(key, JSON.stringify(updated), {
    expirationTtl: 86_400 * 15,
  });
}
```

---

## Anti-patterns

**Querying the current (open) minute bucket.**
Cloudflare's GraphQL aggregation closes buckets at the minute boundary.
Always query `prevMinute → currentMinute`; querying an open bucket returns
partial counts that will cause spurious alerts at low traffic times.

**Setting a fixed absolute threshold.**
Traffic patterns vary by hour-of-day and day-of-week. A fixed threshold of
1 000 events/min that is appropriate at 3 AM will miss significant spikes at
peak hours when baseline is 50 000. Use a relative/statistical threshold.

**Running the Cron Worker every 30 seconds.**
Cloudflare Cron Triggers have a minimum interval of 1 minute. Polling faster
requires a Durable Object alarm or a Tail Worker approach.

**Alerting on every minute exceeding threshold.**
Add a cooldown using KV (store last alert timestamp and suppress duplicates
within a 5-minute window) to prevent alert storms during sustained attacks.

---

## Gotchas

- `firewallEventsAdaptiveGroups` uses adaptive sampling at high event rates.
  Counts are estimates; treat them as signals, not exact billing figures.
- The GraphQL API rate-limits at 1 200 requests per 5 minutes per token. A
  Cron Worker polling every minute and querying 7 baseline days sends 8 GQL
  calls per tick — well within limit but worth tracking.
- The `action_in` filter requires the exact string values Cloudflare uses
  internally; `"blocked"` will return no results — use `"block"`.
- The `datetime_geq` / `datetime_leq` filter values must be ISO 8601 strings
  with second precision; milliseconds in the string are not accepted.

---

## Verification

1. Deploy the Worker and confirm the Cron Trigger fires at `*/1 * * * *`.
2. Use the Cloudflare dashboard to temporarily create a rate-limit rule that
   blocks your own test IP, send traffic, then remove the rule.
3. Watch for the Slack/PagerDuty notification within 2 minutes.
4. Check KV keys `baseline:HH:MM` to confirm baseline values are accumulating.

---

## Related

- `analytics-engine-graphql-api-time-series-dashboard.md`
- `cloudflare-notifications-webhook-workers-routing.md`
- `anomaly-detection-alerts.md`
- `workers-request-size-anomaly-detection-d1.md`
- `logpush-filter-expressions-cost-control.md`

---

## Sources

- Cloudflare GraphQL firewall datasets — https://developers.cloudflare.com/analytics/graphql-api/features/data-sets/
- firewallEventsAdaptiveGroups schema — https://developers.cloudflare.com/firewall/cf-firewall-rules/graphql/
- Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
