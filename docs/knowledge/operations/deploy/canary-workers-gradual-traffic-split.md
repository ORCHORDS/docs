# canary-workers-gradual-traffic-split

**Issue:** Canary deployments for Cloudflare Workers with gradual
traffic splitting, cookie/header routing, mobile client awareness,
rollback triggers, and D1 migration coordination
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

A new Worker version is deployed directly to 100% of traffic. Within
minutes, error rate spikes because the new code has a regression in a
rarely-tested mobile request path. Rolling back requires a full
`wrangler deploy` of the previous version, which takes ~30 seconds
during which all traffic sees errors. Had the canary been limited to
5% of traffic, only 5% of users would have been affected.

## Context

Cloudflare Workers supports first-class canary deployments through the
**Versions** API (`wrangler versions upload` + `wrangler versions
deploy`). This allows percentage-based traffic splitting between two
Worker versions without any application-level routing code. For
organisations that cannot yet use Versions (Workers Free plan, or need
header/cookie-based routing for internal beta users), a manual split
inside the Worker is the alternative.

**Source:** Cloudflare Docs — Versions and Deployments; Cloudflare
Blog — Gradual deploys for Workers.

## The "wrangler versions percentage split" pattern

The native approach: upload as a new version (no traffic), then
gradually shift traffic to it.

```bash
# 1. Upload the new version (no traffic yet)
VERSION_ID=$(npx wrangler versions upload --env production \
  --message "v2.1.0 — new mobile search handler" \
  | grep "Version ID" | awk '{print $NF}')

echo "Uploaded version: $VERSION_ID"

# 2. Send 5% of traffic to the new version
npx wrangler versions deploy \
  --version-id "$VERSION_ID" \
  --percentage 5 \
  --env production

# 3. Monitor for 30 minutes, then promote to 50%
npx wrangler versions deploy \
  --version-id "$VERSION_ID" \
  --percentage 50 \
  --env production

# 4. Promote to 100% (full rollout)
npx wrangler versions deploy \
  --version-id "$VERSION_ID" \
  --percentage 100 \
  --env production
```

Rollback at any point — restoring 100% to the previous version:

```bash
# Rollback: set new version to 0%
npx wrangler versions deploy \
  --version-id "$VERSION_ID" \
  --percentage 0 \
  --env production
```

## The "cookie-based canary routing" pattern

When you need opt-in canary (e.g., internal QA on mobile devices),
route based on a `canary` cookie rather than random percentage:

```typescript
// src/canary.ts
export function resolveCanary(request: Request): "stable" | "canary" {
  const cookie = request.headers.get("cookie") ?? "";
  if (/\bcanary=1\b/.test(cookie)) return "canary";

  // 5% random assignment for users without a cookie
  if (Math.random() < 0.05) return "canary";

  return "stable";
}

export function setCanarycookie(response: Response): Response {
  // Stamp the cookie so the same user always gets canary
  const headers = new Headers(response.headers);
  headers.append("Set-Cookie",
    "canary=1; Path=/; Max-Age=3600; SameSite=Lax");
  return new Response(response.body, { ...response, headers });
}
```

Use in the main handler:

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const lane = resolveCanary(req);

    if (lane === "canary") {
      const res = await handleCanary(req, env);
      return setCanarycookie(res);
    }
    return handleStable(req, env);
  },
};
```

## The "header-based canary for mobile clients" pattern

Mobile clients (iOS / Android) can opt into a canary build by sending
`X-Client-Version: canary` or a custom header set by the app's
internal feature flag system:

```typescript
export function isMobileCanary(request: Request): boolean {
  const header = request.headers.get("x-client-channel");
  return header === "canary" || header === "beta";
}
```

```
+--------------------------+------------------+----------------+
| Client signal            | Header value     | Lane           |
+--------------------------+------------------+----------------+
| Production app release   | (absent)         | stable         |
| TestFlight / internal    | x-client-channel | canary         |
|   beta build             | = "beta"         |                |
| Developer / QA build     | x-client-channel | canary         |
|                          | = "canary"       |                |
+--------------------------+------------------+----------------+
```

## The "automatic rollback trigger" pattern

Automate rollback when error rate in the canary lane exceeds a
threshold. Query Cloudflare Analytics Engine from a scheduled Worker:

```typescript
// src/rollback-monitor.cron.ts
export async function checkCanaryHealth(env: Env): Promise<void> {
  const query = `
    SELECT
      version,
      countIf(status >= 500) AS errors,
      count()                 AS total
    FROM workers_analytics
    WHERE timestamp > now() - INTERVAL '5' MINUTE
    GROUP BY version
  `;
  const result = await env.ANALYTICS.query(query);

  for (const row of result.rows) {
    const errorRate = row.errors / row.total;
    if (row.version === "canary" && errorRate > 0.02) {
      // >2% errors in canary — rollback
      await fetch("https://api.cloudflare.com/client/v4/workers/...", {
        method: "PUT",
        headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
        body: JSON.stringify({ percentage: 0 }),
      });
      await notifySlack(env, `Canary rolled back: error rate ${errorRate}`);
    }
  }
}
```

Add to `wrangler.toml`:

```toml
[triggers]
crons = ["*/5 * * * *"]   # run every 5 minutes
```

## The "D1 migration coordination" pattern

When the canary version requires a new D1 schema column, the migration
must run *before* the canary receives any traffic, and be backward-
compatible with the stable version (which still runs in parallel).

```
Timeline:
  t=0   Run D1 migration (additive: new column with NULL default)
  t=1   Deploy canary at 5% — reads/writes new column
  t=2   Stable version ignores the new column (SELECT still works)
  t=3   Canary promoted to 100%
  t=4   Stable retired — no longer needs backward compat
```

Additive migration example:

```sql
-- migrations/0012_add_mobile_push_token.sql
ALTER TABLE users ADD COLUMN push_token TEXT;
-- Existing rows get NULL; stable Worker ignores the column.
```

Never run a destructive migration (DROP COLUMN, RENAME) while a
canary split is active. The stable version will break.

## Anti-patterns

- **Canary with a breaking D1 migration.** If the schema change is
  not backward-compatible, the stable 95% of traffic fails after
  the migration runs.
- **Long-lived canary (>24 hours) without promoting or rolling back.**
  Canary code diverges from main; merge conflicts accumulate.
- **Stamping a canary cookie from the stable handler.** Users who
  hit stable should not receive a canary cookie; only the canary
  handler should stamp it.
- **Using `wrangler deploy` instead of `wrangler versions deploy`.**
  `wrangler deploy` cuts over to 100% immediately; it ignores
  percentage splits.
- **No error-rate baseline.** Setting a rollback threshold of 2%
  without knowing stable's normal error rate may trigger false
  rollbacks. Measure stable first.

## Gotchas

- Cloudflare's Versions API is available on Workers Paid plan. Free
  plan workers fall back to manual cookie/header routing.
- `wrangler versions upload` does not restart the Worker; it queues
  a new script version. Traffic continues on the current version
  until `wrangler versions deploy` is called.
- Mobile clients with aggressive retry logic may amplify canary
  errors; a 5% traffic split can generate far more than 5% of
  support tickets if the canary path is the mobile-specific one.
- Set `x-client-channel` only in debug or beta builds. Ensure
  production app builds never send this header to avoid accidentally
  routing all users to canary.

## Verification

- **5% canary:** `curl -H "x-client-channel: canary"
  https://api.example.com/health` returns a response header
  `x-worker-version: canary`.
- **Rollback:** Set percentage to 0 and confirm Analytics Engine
  shows 0 canary requests within 60 s.
- **D1 compat:** Run integration tests against the canary lane with
  a stable-version client to confirm the schema is backward-compat.

## Related

- `documentation/docs/policies/deploy/wrangler-deploy-github-actions-workers.md`
- `documentation/docs/policies/deploy/workers-secrets-rotation-zero-downtime.md`
- `documentation/docs/policies/deploy/blue-green-traffic-switch.md`
- `documentation/docs/policies/deploy/feature-flag-deploy-coupling.md`
- `documentation/docs/policies/deploy/database-migration-deploy-strategy.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/\
  versions-and-deployments/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/d1/reference/migrations/
