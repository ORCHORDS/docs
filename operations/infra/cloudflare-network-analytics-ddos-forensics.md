# Cloudflare Network Analytics DDoS Forensics

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

After a volumetric DDoS attack you need to reconstruct: which ASNs sent traffic, what protocols were abused, when mitigation kicked in, and whether any legitimate traffic was dropped.
Cloudflare's Network Analytics v2 API (GraphQL) exposes per-minute L3/L4 telemetry — but it is not surfaced in the dashboard at attack resolution.
A Tail Worker pipeline can pull this data post-event and write a structured forensics report to R2 for compliance and postmortem use.

## Context

Cloudflare Network Analytics v2 provides GraphQL access to `networkAnalyticsAdaptiveGroups` and `dosdAttackAnalyticsGroups`.
Data is available for the last 30 days at minute-level granularity.
The typical forensics workflow: pull raw event groups, correlate mitigation actions with packet-rate spikes, identify top source ASNs, and export a JSON/CSV artifact.
Workers can be triggered on-demand (via a Cron Trigger or manual HTTP request) and write outputs directly to R2.

## Querying Network Analytics via GraphQL from a Worker

```typescript
// src/forensics.ts
export interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;   // scoped: Analytics:Read
  REPORT_BUCKET: R2Bucket;
}

async function queryNetworkAnalytics(
  env: Env,
  startTime: string,
  endTime: string,
): Promise<any> {
  const query = `
    query DDoSForensics($accountTag: string, $start: string, $end: string) {
      viewer {
        accounts(filter: { accountTag: $accountTag }) {
          networkAnalyticsAdaptiveGroups(
            filter: { datetime_geq: $start, datetime_leq: $end }
            limit: 10000
            orderBy: [packets_DESC]
          ) {
            sum { packets bytes }
            dimensions {
              datetime
              sourceASN
              sourceCountry
              ipProtocol
              outcome
              coloCity
            }
          }
        }
      }
    }
  `;

  const res = await fetch('https://api.cloudflare.com/client/v4/graphql', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query,
      variables: {
        accountTag: env.CF_ACCOUNT_ID,
        start: startTime,
        end: endTime,
      },
    }),
  });

  const data = await res.json() as any;
  if (data.errors) throw new Error(JSON.stringify(data.errors));
  return data.data.viewer.accounts[0].networkAnalyticsAdaptiveGroups;
}
```

## Correlating Mitigation Actions with Traffic Spikes

```typescript
interface AttackWindow {
  startTime: string;
  endTime: string;
  peakPacketsPerMinute: number;
  topASNs: Array<{ asn: string; packets: number; mitigated: number }>;
}

function analyzeAttackWindow(groups: any[]): AttackWindow {
  const byMinute: Record<string, number> = {};
  const asnMap: Record<string, { total: number; mitigated: number }> = {};

  for (const g of groups) {
    const minute = g.dimensions.datetime.slice(0, 16); // truncate to minute
    byMinute[minute] = (byMinute[minute] ?? 0) + g.sum.packets;

    const asn = g.dimensions.sourceASN ?? 'unknown';
    if (!asnMap[asn]) asnMap[asn] = { total: 0, mitigated: 0 };
    asnMap[asn].total += g.sum.packets;
    if (g.dimensions.outcome === 'drop') asnMap[asn].mitigated += g.sum.packets;
  }

  const peakMinute = Object.entries(byMinute).sort(([, a], [, b]) => b - a)[0];
  const topASNs = Object.entries(asnMap)
    .sort(([, a], [, b]) => b.total - a.total)
    .slice(0, 10)
    .map(([asn, v]) => ({ asn, packets: v.total, mitigated: v.mitigated }));

  return {
    startTime: groups[0]?.dimensions.datetime ?? '',
    endTime: groups[groups.length - 1]?.dimensions.datetime ?? '',
    peakPacketsPerMinute: peakMinute?.[1] ?? 0,
    topASNs,
  };
}
```

## Writing the Forensics Report to R2

```typescript
async function writeForensicsReport(
  env: Env,
  attackId: string,
  window: AttackWindow,
  rawGroups: any[],
): Promise<void> {
  const report = {
    generated_at: new Date().toISOString(),
    attack_id: attackId,
    summary: window,
    raw_groups: rawGroups,
  };

  const key = `ddos-forensics/${attackId}/report-${Date.now()}.json`;
  await env.REPORT_BUCKET.put(key, JSON.stringify(report, null, 2), {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: { attack_id: attackId, peak_ppm: String(window.peakPacketsPerMinute) },
  });

  // Also write a lightweight summary for quick review
  const summaryKey = `ddos-forensics/${attackId}/summary.json`;
  await env.REPORT_BUCKET.put(summaryKey, JSON.stringify(window, null, 2), {
    httpMetadata: { contentType: 'application/json' },
  });
}
```

## Cron-Triggered Forensics Worker

```typescript
// wrangler.toml
// [triggers]
// crons = ["0 * * * *"]  # run hourly; also invokable manually

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    // Forensics window: last completed hour
    const end = new Date();
    end.setMinutes(0, 0, 0);
    const start = new Date(end.getTime() - 60 * 60 * 1000);

    const groups = await queryNetworkAnalytics(
      env,
      start.toISOString(),
      end.toISOString(),
    );

    if (groups.length === 0) return; // no traffic data, skip

    const dropped = groups.filter((g: any) => g.dimensions.outcome === 'drop');
    if (dropped.length === 0) return; // no drops, not an attack window

    const window = analyzeAttackWindow(groups);
    const attackId = `${start.toISOString().slice(0, 13)}-auto`;
    await writeForensicsReport(env, attackId, window, groups);
  },

  async fetch(req: Request, env: Env): Promise<Response> {
    const { searchParams } = new URL(req.url);
    const start = searchParams.get('start') ?? '';
    const end = searchParams.get('end') ?? '';
    if (!start || !end) return new Response('start and end required', { status: 400 });

    const groups = await queryNetworkAnalytics(env, start, end);
    const window = analyzeAttackWindow(groups);
    return Response.json(window);
  },
};
```

## Anti-patterns

- **Pulling 30-day history in one query** — the GraphQL endpoint paginates at 10,000 rows; chunk queries into hour-long windows.
- **Storing raw groups without aggregation** — raw groups at packet granularity can reach hundreds of MB; always write both a summary and the raw artifact separately.
- **Using `datetime_geq` without timezone normalization** — all timestamps must be UTC ISO-8601; local time offsets cause misaligned windows.
- **Not filtering by `outcome`** — total packet counts conflate legitimate and mitigated traffic; always split on `outcome` for accurate forensics.

## Gotchas

- `networkAnalyticsAdaptiveGroups` uses **adaptive sampling** at high traffic volumes — packet counts are estimates, not exact, above ~10 Mpps.
- The GraphQL API rate-limits to 500 requests per 10 minutes per token; space forensics queries with back-off.
- `sourceASN` is absent for traffic from Cloudflare's own infrastructure (e.g., health checks); filter `sourceASN == null` rows before ranking.
- Mitigation events from Magic Transit (`outcome = "filter"`) differ from HTTP-layer mitigations (`outcome = "drop"`); they appear in separate analytics datasets.

## Verification

```bash
# Manual forensics pull for a known attack window
curl -X GET "https://forensics.workers.example.com/?start=2026-08-20T14:00:00Z&end=2026-08-20T16:00:00Z"

# Confirm report written to R2
wrangler r2 object list REPORT_BUCKET --prefix ddos-forensics/

# Inspect summary
wrangler r2 object get REPORT_BUCKET ddos-forensics/2026-08-20T14-auto/summary.json
```

## Related

- `cloudflare-network-error-logging-workers.md`
- `workers-opentelemetry-tail-workers.md`
- `cloudflare-r2-backup-restore-strategy.md`
- `aws-waf-rules.md`

## Sources

- https://developers.cloudflare.com/analytics/graphql-api/features/data-sets/
- https://developers.cloudflare.com/analytics/network-analytics/
- https://developers.cloudflare.com/ddos-protection/reference/analytics/
