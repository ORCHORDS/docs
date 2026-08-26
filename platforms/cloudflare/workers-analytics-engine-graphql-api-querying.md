# Workers Analytics Engine: GraphQL API Querying

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You are writing events to Analytics Engine from a Worker and now need to query those metrics via the GraphQL API to build dashboards, alerting, or usage-billing reports without shipping data to an external warehouse.

## Context
Analytics Engine stores events written via `env.AE.writeDataPoint()` in Cloudflare's edge-native OLAP store. Data becomes queryable through the Cloudflare GraphQL Analytics API at `https://api.cloudflare.com/client/v4/graphql` within ~60 seconds of ingestion. Queries are scoped to a `zoneTag` or `accountTag` and use cursor-based pagination. The dataset name in GraphQL matches the binding name used in `wrangler.toml`.

## Defining the Dataset Schema with TypeScript Types

Before querying, model the schema your Worker writes so TypeScript stays in sync with your blobs and doubles layout.

```typescript
// types/analytics.ts
export interface ApiRequestDataPoint {
  // blobs[0] = route, blobs[1] = method, blobs[2] = status_class
  route: string;
  method: string;
  statusClass: string;
  // doubles[0] = latency_ms, doubles[1] = response_bytes
  latencyMs: number;
  responseBytes: number;
}

export interface AEQueryRow {
  blob1: string; // route
  blob2: string; // method
  blob3: string; // status_class
  double1: number; // latency_ms avg
  double2: number; // response_bytes sum
  count: number;
  dimensions: {
    ts: string;
  };
}

export interface AEGraphQLResponse {
  data: {
    viewer: {
      accounts: Array<{
        apiRequestsAdaptiveGroups: AEQueryRow[];
      }>;
    };
  };
  errors?: Array<{ message: string }>;
}
```

## Building the GraphQL Query

Analytics Engine uses `AdaptiveGroups` nodes. Always specify the time range with `datetimeGeq` / `datetimeLt` and limit results to avoid timeouts.

```typescript
// lib/ae-query.ts
const AE_GQL_ENDPOINT = "https://api.cloudflare.com/client/v4/graphql";

export function buildAEQuery(
  accountId: string,
  datasetName: string,
  from: string,
  to: string,
  limit = 500
): string {
  return JSON.stringify({
    query: `
      query AnalyticsEngineQuery($accountTag: string!, $from: string!, $to: string!) {
        viewer {
          accounts(filter: { accountTag: $accountTag }) {
            ${datasetName}AdaptiveGroups(
              filter: {
                datetimeGeq: $from
                datetimeLt: $to
              }
              limit: ${limit}
              orderBy: [datetimeHour_ASC]
            ) {
              count
              dimensions {
                ts: datetimeHour
                blob1
                blob2
                blob3
              }
              avg {
                double1
              }
              sum {
                double2
              }
            }
          }
        }
      }
    `,
    variables: {
      accountTag: accountId,
      from,
      to,
    },
  });
}
```

## Executing the Query from a Worker

Fetch the GraphQL endpoint with a Cloudflare API token that has `Analytics: Read` permission. Store the token in a Workers secret.

```typescript
// worker.ts
export interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string; // secret: Analytics Read
  AE: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/metrics") return new Response("Not found", { status: 404 });

    const now = new Date();
    const from = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
    const to = now.toISOString();

    const body = buildAEQuery(env.CF_ACCOUNT_ID, "apiRequests", from, to);

    const resp = await fetch("https://api.cloudflare.com/client/v4/graphql", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
      },
      body,
    });

    if (!resp.ok) {
      return new Response(`GraphQL error: ${resp.status}`, { status: 502 });
    }

    const json = (await resp.json()) as AEGraphQLResponse;

    if (json.errors?.length) {
      return new Response(JSON.stringify(json.errors), { status: 502 });
    }

    const rows =
      json.data.viewer.accounts[0]?.apiRequestsAdaptiveGroups ?? [];

    return Response.json({ rows, count: rows.length });
  },
};

// keep buildAEQuery in same bundle or import from lib/ae-query.ts
function buildAEQuery(accountId: string, dataset: string, from: string, to: string) {
  return JSON.stringify({
    query: `{
      viewer {
        accounts(filter: { accountTag: "${accountId}" }) {
          ${dataset}AdaptiveGroups(
            filter: { datetimeGeq: "${from}", datetimeLt: "${to}" }
            limit: 500
            orderBy: [datetimeHour_ASC]
          ) {
            count
            dimensions { ts: datetimeHour blob1 blob2 blob3 }
            avg { double1 }
            sum { double2 }
          }
        }
      }
    }`,
  });
}
```

## Cursor Pagination for Large Result Sets

Analytics Engine limits each response to 10 000 rows. Use the `after` cursor to page through results.

```typescript
// lib/ae-paginate.ts
export async function fetchAllAERows(
  accountId: string,
  apiToken: string,
  datasetName: string,
  from: string,
  to: string
): Promise<AEQueryRow[]> {
  const allRows: AEQueryRow[] = [];
  let cursor: string | null = null;

  do {
    const afterClause = cursor ? `, after: "${cursor}"` : "";
    const query = `{
      viewer {
        accounts(filter: { accountTag: "${accountId}" }) {
          ${datasetName}AdaptiveGroups(
            filter: { datetimeGeq: "${from}", datetimeLt: "${to}" }
            limit: 10000
            orderBy: [datetimeHour_ASC]
            ${afterClause}
          ) {
            count
            dimensions { ts: datetimeHour blob1 blob2 blob3 }
            avg { double1 }
            sum { double2 }
            cursor
          }
        }
      }
    }`;

    const resp = await fetch("https://api.cloudflare.com/client/v4/graphql", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiToken}`,
      },
      body: JSON.stringify({ query }),
    });

    const json = (await resp.json()) as AEGraphQLResponse;
    const rows =
      json.data?.viewer?.accounts[0]?.[`${datasetName}AdaptiveGroups`] ?? [];

    allRows.push(...rows);
    cursor = rows.at(-1)?.cursor ?? null;
  } while (cursor !== null);

  return allRows;
}
```

## Anti-patterns
- Querying without a time range — omitting `datetimeGeq`/`datetimeLt` causes full-table scans and slow/failed queries
- Using `offset` instead of cursor pagination — Analytics Engine GraphQL does not support SQL-style OFFSET
- Storing the API token in `wrangler.toml` vars — always use `wrangler secret put CF_API_TOKEN`
- Requesting all blobs and doubles when you only need a subset — select only the fields you aggregate to reduce payload size
- Querying from within a high-traffic fetch handler on every request — cache results in KV or Durable Objects with a short TTL

## Gotchas
- The dataset node name in GraphQL is `<bindingName>AdaptiveGroups` — if your binding is `MY_AE`, the node is `MY_AEAdaptiveGroups` (camelCase required)
- Analytics Engine uses `datetimeHour` as the lowest granularity for grouping; minute-level grouping is not available in AdaptiveGroups
- New datasets require at least one written data point before the GraphQL node appears; querying a zero-row dataset returns an empty array, not an error
- The API token must have `Account > Analytics > Read`; zone-level tokens cannot query account-scoped datasets

## Verification
1. Write a test data point: `env.AE.writeDataPoint({ blobs: ["test", "GET", "2xx"], doubles: [42, 1024] })`
2. Wait ~60 seconds, then POST the GraphQL query against the Cloudflare API
3. Confirm the returned row has `blob1 = "test"`, `avg.double1 = 42`, `sum.double2 = 1024`
4. Run `wrangler tail` during the query fetch to inspect the subrequest and confirm no 401/403 errors

## Related
- `cloudflare-workers-analytics-engine-custom-metrics.md`
- `workers-analytics-engine.md`
- `workers-logpush.md`
- `workers-tail-workers.md`

## Sources
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/graphql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
