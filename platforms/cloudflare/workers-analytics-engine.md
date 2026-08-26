# workers-analytics-engine

**Issue:** Writing and querying custom analytics events using Workers Analytics Engine
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workers Analytics Engine (WAE) is a time-series data store built for Workers. Unlike KV or D1, WAE is write-optimised for high-volume event ingestion and queryable via the GraphQL Analytics API.

## Pattern / Solution

```toml
# wrangler.toml
[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "my_events"
```

```typescript
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Write a data point — fire-and-forget (no await needed)
    env.ANALYTICS.writeDataPoint({
      // Up to 1 index (string, max 512 bytes) — used for filtering
      indexes: [url.pathname],
      // Up to 20 blobs (string, max 512 bytes each)
      blobs: [
        request.cf?.country as string ?? 'XX',
        request.headers.get('user-agent') ?? '',
        url.searchParams.get('ref') ?? '',
      ],
      // Up to 20 doubles (float64)
      doubles: [
        Date.now(),
        Number(request.headers.get('content-length') ?? 0),
      ],
    });

    return new Response('OK');
  },
};
```

**Querying via GraphQL (Cloudflare API):**
```graphql
{
  viewer {
    accounts(filter: { accountTag: $accountId }) {
      myEventsAdaptiveGroups(
        filter: { date_geq: "2026-08-01", blob1: "US" }
        limit: 10
        orderBy: [count_DESC]
      ) {
        count
        dimensions {
          index1   # pathname
          blob1    # country
        }
      }
    }
  }
}
```

```bash
curl -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"..."}'
```

## Gotchas
- `writeDataPoint` is **non-blocking** — do not `await` it; doing so may add unnecessary latency.
- WAE data is available with ~1 minute lag; it is not real-time.
- Maximum **20 blobs**, **20 doubles**, **1 index** per data point. Excess fields are silently dropped.
- The dataset name in `wrangler.toml` must match the GraphQL field name (camelCase of `dataset_name`).
- WAE data is retained for **90 days** on paid plans.
- You cannot delete individual data points; the entire dataset can be dropped via the API.
- GraphQL filtering uses `blob1`…`blob20` and `double1`…`double20` — not the field names you imagine.

## Related
- `workers-logpush.md`
- `workers-tail-workers.md`
- `workers-best-practices.md`
