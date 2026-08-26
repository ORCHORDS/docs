# Turnstile Analytics API Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have deployed Cloudflare Turnstile widgets across multiple pages and need programmatic access to solve rates, challenge counts, and failure breakdowns — not just manual review in the dashboard. You want a Worker that fetches Turnstile analytics from the Cloudflare API and surfaces them as a JSON endpoint or pushes them into Analytics Engine for custom dashboards.

## Context

Cloudflare exposes Turnstile analytics through both the GraphQL Analytics API and the REST Turnstile Logs endpoint. Workers can query either interface with an API token scoped to `Zone:Read` + `Turnstile:Read`. Metrics available include: total challenges issued, solve rate, solve time distribution, failure reasons (bot score, IP reputation, browser fingerprint), and widget-level breakdown. This is distinct from server-side token validation (`/siteverify`) — analytics read historical aggregate data, not per-request results.

## Fetching Widget-Level Solve Rates via REST

```typescript
const CF_API = "https://api.cloudflare.com/client/v4";

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { searchParams } = new URL(req.url);
    const siteKey = searchParams.get("siteKey") ?? env.TURNSTILE_SITE_KEY;
    const since = searchParams.get("since") ?? new Date(Date.now() - 86_400_000).toISOString();

    const resp = await fetch(
      `${CF_API}/accounts/${env.CF_ACCOUNT_ID}/challenges/widgets/${siteKey}/analytics` +
        `?since=${encodeURIComponent(since)}`,
      {
        headers: {
          Authorization: `Bearer ${env.CF_API_TOKEN}`,
          "Content-Type": "application/json",
        },
      }
    );

    if (!resp.ok) {
      const err = await resp.json();
      return Response.json({ error: err }, { status: resp.status });
    }

    const data = await resp.json<TurnstileAnalytics>();
    return Response.json({
      siteKey,
      solveRate: data.result.solve_rate,
      totalChallenges: data.result.total_challenges,
      solvedChallenges: data.result.solved_challenges,
      failureReasons: data.result.failure_reasons,
    });
  },
} satisfies ExportedHandler<Env>;

interface TurnstileAnalytics {
  result: {
    solve_rate: number;
    total_challenges: number;
    solved_challenges: number;
    failure_reasons: Record<string, number>;
  };
}

interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  TURNSTILE_SITE_KEY: string;
}
```

## Querying Turnstile Data via GraphQL Analytics API

```typescript
const GRAPHQL_ENDPOINT = "https://api.cloudflare.com/client/v4/graphql";

export async function fetchTurnstileGraphQL(env: Env, widgetSiteKey: string): Promise<TurnstileStats> {
  const now = new Date();
  const minus24h = new Date(now.getTime() - 86_400_000);

  const query = `
    query TurnstileStats($accountTag: string!, $siteKey: string!, $start: Time!, $end: Time!) {
      viewer {
        accounts(filter: { accountTag: $accountTag }) {
          turnstileSolveAdaptiveGroups(
            filter: { siteKey: $siteKey, datetimeHour_geq: $start, datetimeHour_leq: $end }
            limit: 168
            orderBy: [datetimeHour_ASC]
          ) {
            datetimeHour
            sum {
              solvesCount
              challengesCount
              failureCount
            }
            avg {
              solveTime
            }
          }
        }
      }
    }
  `;

  const resp = await fetch(GRAPHQL_ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query,
      variables: {
        accountTag: env.CF_ACCOUNT_ID,
        siteKey: widgetSiteKey,
        start: minus24h.toISOString(),
        end: now.toISOString(),
      },
    }),
  });

  const json = await resp.json<{ data: { viewer: { accounts: Array<{ turnstileSolveAdaptiveGroups: TurnstileStats[] }> } } }>();
  return json.data.viewer.accounts[0]?.turnstileSolveAdaptiveGroups ?? [];
}

type TurnstileStats = Array<{
  datetimeHour: string;
  sum: { solvesCount: number; challengesCount: number; failureCount: number };
  avg: { solveTime: number };
}>;
```

## Pushing Analytics into Analytics Engine for Custom Dashboards

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(syncTurnstileMetrics(env));
  },
} satisfies ExportedHandler<Env>;

async function syncTurnstileMetrics(env: Env): Promise<void> {
  const stats = await fetchTurnstileGraphQL(env, env.TURNSTILE_SITE_KEY);

  for (const hour of stats) {
    env.METRICS.writeDataPoint({
      blobs: [env.TURNSTILE_SITE_KEY, hour.datetimeHour],
      doubles: [
        hour.sum.solvesCount,
        hour.sum.challengesCount,
        hour.sum.failureCount,
        hour.avg.solveTime ?? 0,
      ],
      indexes: ["turnstile_hourly"],
    });
  }
}

interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  TURNSTILE_SITE_KEY: string;
  METRICS: AnalyticsEngineDataset;
}
```

## Caching Analytics Responses in KV

```typescript
const CACHE_TTL = 300; // 5 minutes

export async function getCachedAnalytics(env: Env): Promise<object> {
  const cacheKey = `turnstile:analytics:${env.TURNSTILE_SITE_KEY}`;
  const cached = await env.KV.get(cacheKey, "json");
  if (cached) return cached as object;

  const fresh = await fetchLiveAnalytics(env);
  await env.KV.put(cacheKey, JSON.stringify(fresh), { expirationTtl: CACHE_TTL });
  return fresh;
}

async function fetchLiveAnalytics(env: Env): Promise<object> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/challenges/widgets/${env.TURNSTILE_SITE_KEY}/analytics`,
    { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
  );
  return resp.json();
}
```

## Anti-patterns

- Calling the analytics API on every user request — Turnstile analytics are aggregate/eventual; cache results in KV for 5+ minutes.
- Using a Global API Key instead of a scoped API token — use `Turnstile:Read` + `Account:Read` only; never embed wide-permission tokens in Workers secrets.
- Mixing `siteverify` (token validation) with analytics queries in the same code path — they serve different purposes and have different latency profiles.
- Parsing `failure_reasons` keys without a fallback — the key set can expand; always handle unknown keys gracefully.

## Gotchas

- The GraphQL field name is `turnstileSolveAdaptiveGroups` for widget-adaptive challenges and differs for managed/invisible widget types — always confirm the field name against the schema explorer at `https://graphql.cloudflare.com/explorer`.
- Analytics data has up to 10-minute lag; freshness guarantees are not real-time.
- The REST analytics endpoint requires the `siteKey` path parameter (the public widget key, `0x4AAAAAAA...`), not the secret key used in `siteverify`.
- GraphQL queries must include `accountTag` as the top-level filter; omitting it returns an empty result set without an error.
- API token must have the `Turnstile: Read` permission specifically — `Zone: Analytics: Read` alone is insufficient.

## Verification

```bash
# Verify API token has correct permissions
curl -sS https://api.cloudflare.com/client/v4/user/tokens/verify \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.status'

# Fetch widget list to confirm siteKey
curl -sS "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/challenges/widgets" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[].sitekey'

# Manual analytics fetch for last hour
curl -sS "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/challenges/widgets/$SITE_KEY/analytics" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.solve_rate'
```

## Related

- `cloudflare-turnstile-invisible-widget-server-validation.md` — server-side `siteverify` token validation
- `turnstile-best-practices.md` — widget configuration and action namespacing
- `cloudflare-workers-analytics-engine-custom-metrics.md` — Analytics Engine data model
- `workers-analytics-engine-graphql-api-querying.md` — GraphQL API patterns for other datasets
- `kv-best-practices.md` — short-lived result caching patterns

## Sources

- https://developers.cloudflare.com/turnstile/get-started/analytics/
- https://developers.cloudflare.com/analytics/graphql-api/
- https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- https://api.cloudflare.com/#turnstile-widget-analytics
