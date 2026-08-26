# Analytics Engine GraphQL API Time-Series Dashboard

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to query Cloudflare's **platform-level** analytics — Workers
invocations, HTTP request volumes, cache ratios, Durable Object activity —
over a rolling time window and render them as time-series charts in a
self-hosted dashboard or Grafana. The Cloudflare GraphQL Analytics API covers
this data; Analytics Engine's SQL API covers your own custom writeDataPoint
events. This article explains when to use each and how to build time-series
queries with the GraphQL API.

---

## Context

Cloudflare exposes two distinct query surfaces:

| Surface | Endpoint | Data covered |
|---------|----------|--------------|
| **GraphQL Analytics API** | `https://api.cloudflare.com/client/v4/graphql` | Platform data: HTTP requests, firewall events, Workers invocations, DO operations, Cache analytics — sourced from Cloudflare's internal edge pipeline |
| **Analytics Engine SQL API** | `https://api.cloudflare.com/client/v4/accounts/{accountId}/analytics_engine/sql` | Custom `writeDataPoint` data from your Workers |

For time-series dashboards of platform data, the GraphQL API is the correct
choice. It supports adaptive sampling and returns pre-aggregated buckets in
`datetimeHour`, `datetimeFifteenMinutes`, and `datetimeMinute` granularities.

---

## GraphQL API Authentication

All requests require a Cloudflare API token with **Account Analytics: Read**
permission (and **Zone Analytics: Read** for zone-scoped datasets).

```bash
curl -s https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data-raw '{"query":"{ viewer { zones(filter:{zoneTag:\"ZONE_ID\"}){ httpRequests1mGroups(limit:5, orderBy:[datetime_ASC]){ dimensions{ datetime } sum { requests } } } } }"}'
```

---

## Core Time-Series Query Pattern

GraphQL time-series nodes follow a consistent pattern:

```graphql
{dataset}Groups(
  limit: Int,
  filter: {datetime_geq: "ISO8601", datetime_leq: "ISO8601"},
  orderBy: [datetime_ASC]
) {
  dimensions { datetime }
  sum { ... }
  avg { ... }
  quantiles { ... }
}
```

### Workers Invocations by Outcome (1-hour buckets)

```graphql
query WorkersTimeSeries($accountTag: String!, $from: String!, $to: String!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      workersInvocationsAdaptive(
        limit: 10000
        filter: { datetime_geq: $from, datetime_leq: $to }
        orderBy: [datetime_ASC]
      ) {
        dimensions {
          datetime
          scriptName
          status
        }
        sum {
          requests
          errors
          subrequests
        }
        quantiles {
          cpuTimeP50
          cpuTimeP99
          durationP50
          durationP99
        }
      }
    }
  }
}
```

Variables:
```json
{
  "accountTag": "abc123",
  "from": "2026-08-23T00:00:00Z",
  "to":   "2026-08-23T06:00:00Z"
}
```

---

## TypeScript Worker: GraphQL Proxy for Grafana JSON datasource

Grafana's **JSON** datasource plugin expects a `/query` POST endpoint that
returns time-series frames. The Worker below proxies GraphQL calls and
transforms the response.

```typescript
export interface Env {
  CF_API_TOKEN: string;
  CF_ACCOUNT_TAG: string;
}

const GQL_ENDPOINT = "https://api.cloudflare.com/client/v4/graphql";

const WORKERS_QUERY = `
query WorkerTS($accountTag: String!, $from: String!, $to: String!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      workersInvocationsAdaptive(
        limit: 10000
        filter: { datetime_geq: $from, datetime_leq: $to }
        orderBy: [datetime_ASC]
      ) {
        dimensions { datetime scriptName status }
        sum { requests errors }
        quantiles { cpuTimeP99 durationP99 }
      }
    }
  }
}`;

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (new URL(req.url).pathname !== "/query") {
      return new Response("Not found", { status: 404 });
    }

    const body = await req.json<{ range: { from: string; to: string } }>();
    const from = body.range.from;
    const to   = body.range.to;

    const gqlRes = await fetch(GQL_ENDPOINT, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query: WORKERS_QUERY,
        variables: { accountTag: env.CF_ACCOUNT_TAG, from, to },
      }),
    });

    const { data, errors } = await gqlRes.json<any>();
    if (errors) {
      return new Response(JSON.stringify({ errors }), { status: 502 });
    }

    const rows: any[] =
      data.viewer.accounts[0].workersInvocationsAdaptive;

    // Transform to Grafana time-series frames
    const frames = buildFrames(rows);
    return new Response(JSON.stringify(frames), {
      headers: { "Content-Type": "application/json" },
    });
  },
};

interface Row {
  dimensions: { datetime: string; scriptName: string; status: string };
  sum: { requests: number; errors: number };
  quantiles: { cpuTimeP99: number; durationP99: number };
}

function buildFrames(rows: Row[]) {
  // Group by scriptName for one series per script
  const series = new Map<string, { times: number[]; values: number[] }>();

  for (const row of rows) {
    const key = row.dimensions.scriptName;
    if (!series.has(key)) series.set(key, { times: [], values: [] });
    const s = series.get(key)!;
    s.times.push(new Date(row.dimensions.datetime).getTime());
    s.values.push(row.sum.requests);
  }

  return [...series.entries()].map(([name, { times, values }]) => ({
    target: name,
    datapoints: times.map((t, i) => [values[i], t]),
  }));
}
```

---

## Anti-patterns

**Polling at sub-minute granularity.**
The `datetimeMinute` node has a minimum bucket of 1 minute and imposes
stricter rate limits than hourly nodes. Avoid polling it faster than every
60 seconds.

**Fetching unbounded time windows with no `limit`.**
Without a `limit` the API caps at 10 000 rows server-side. Always set an
explicit `limit` and paginate with `after` cursors if needed.

**Mixing zone-scoped and account-scoped queries in one request.**
The `viewer` resolver allows both, but zone nodes require `zoneTag` and
account nodes require `accountTag`. Mix them only when you have both IDs
available; otherwise query them separately.

**Using the Analytics Engine SQL endpoint for platform data.**
The SQL endpoint only sees your custom `writeDataPoint` events. If you query
it for `workersInvocationsAdaptive` you will get an empty result, not an
error.

---

## Gotchas

- The `workersInvocationsAdaptive` node uses **adaptive sampling**: at very
  high request volumes counts are estimates. For precise counts at low volume
  it is exact.
- `datetime` values in responses are UTC ISO 8601 strings aligned to the
  bucket boundary (`datetimeMinute` → `:00` seconds, etc.).
- `cpuTimeP99` is in **microseconds** — divide by 1 000 to get milliseconds
  for display.
- Rate limit: 1 200 requests per 5 minutes per token. Cache responses in KV
  when building high-refresh dashboards.

---

## Verification

```bash
# Confirm auth works and account tag is correct
curl -s -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"{ viewer { accounts { accountTag } } }"}' | jq .

# Fetch last 1 hour of Workers invocations
FROM=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)
TO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

Check that `workersInvocationsAdaptive` returns rows whose `dimensions.datetime`
values are evenly spaced by the node granularity.

---

## Related

- `cloudflare-analytics-engine-grafana-dashboard.md`
- `analytics-engine-sql-api-programmatic-querying.md`
- `cloudflare-workers-analytics.md`
- `firewall-event-spike-anomaly-detection.md`

---

## Sources

- Cloudflare GraphQL Analytics API — https://developers.cloudflare.com/analytics/graphql-api/
- Workers invocations schema — https://developers.cloudflare.com/analytics/graphql-api/features/data-sets/
- Grafana JSON datasource plugin — https://grafana.com/grafana/plugins/simpod-json-datasource/
