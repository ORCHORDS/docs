# Programmatic Cloudflare CDN Cache Purging from Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

After a content publish, stale HTML or API responses remain in Cloudflare's edge cache for minutes or hours. You need to invalidate specific URLs, tagged groups of assets, or entire zones programmatically — from a Cloudflare Worker triggered by a webhook, a deploy hook, or a scheduled Cron Trigger.

## Context

Cloudflare exposes cache purge operations through the Zones API (`/zones/{zone_id}/purge_cache`). A Worker can call this API using a scoped Cloudflare API token stored as a secret binding. Operations include:

| Method | Scope | Cost |
|---|---|---|
| Purge by URL | Individual files | Per-URL quota |
| Purge by cache tag | Groups of assets | Requires Pro+ plan |
| Purge by host | All assets for a hostname | Zone-wide impact |
| Purge everything | Entire zone | Use with extreme care |

Purge calls are eventually consistent: edge nodes acknowledge within seconds but propagation across all PoPs takes up to 30 s.

## Solution

### 1. Worker setup and bindings

```typescript
// wrangler.toml
// [vars]
// CF_ZONE_ID = "your_zone_id"   # not secret
// [secrets]
// CF_PURGE_TOKEN               # set via: wrangler secret put CF_PURGE_TOKEN

export interface Env {
  CF_ZONE_ID: string;
  CF_PURGE_TOKEN: string;  // secret binding
  PURGE_LOG: D1Database;   // audit log
}
```

### 2. Shared purge helper

```typescript
type PurgePayload =
  | { files: string[] }
  | { tags: string[] }
  | { hosts: string[] }
  | { purge_everything: true };

async function cloudflareZonePurge(
  zoneId: string,
  token: string,
  payload: PurgePayload,
): Promise<{ id: string }> {
  const url = `https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type":  "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Purge failed ${res.status}: ${err}`);
  }

  const json = await res.json<{ result: { id: string }; success: boolean }>();
  if (!json.success) throw new Error("Purge API returned success=false");
  return json.result;
}
```

### 3. Purge by URL

```typescript
async function purgeByUrls(env: Env, urls: string[]): Promise<void> {
  // Max 30 URLs per API call
  const BATCH = 30;
  for (let i = 0; i < urls.length; i += BATCH) {
    const batch = urls.slice(i, i + BATCH);
    const result = await cloudflareZonePurge(env.CF_ZONE_ID, env.CF_PURGE_TOKEN, {
      files: batch,
    });
    await logPurge(env, "url", batch, result.id);
  }
}

// Usage
await purgeByUrls(env, [
  "https://example.com/products/widget-pro",
  "https://example.com/api/catalog",
]);
```

### 4. Purge by cache tag

Cache tags must be set on origin responses via the `Cache-Tag` header (Pro plan required).

```typescript
// Origin Worker: tag responses
return new Response(body, {
  headers: {
    "Cache-Control": "public, max-age=3600",
    "Cache-Tag": "product-42,category-electronics",  // comma-separated
  },
});

// Purge Worker: invalidate by tag
async function purgeByTags(env: Env, tags: string[]): Promise<void> {
  // Max 30 tags per call
  const result = await cloudflareZonePurge(env.CF_ZONE_ID, env.CF_PURGE_TOKEN, {
    tags,
  });
  await logPurge(env, "tag", tags, result.id);
}

await purgeByTags(env, ["product-42"]);
```

### 5. Purge by host

```typescript
async function purgeByHost(env: Env, hostname: string): Promise<void> {
  const result = await cloudflareZonePurge(env.CF_ZONE_ID, env.CF_PURGE_TOKEN, {
    hosts: [hostname],
  });
  await logPurge(env, "host", [hostname], result.id);
}

await purgeByHost(env, "cdn.example.com");
```

### 6. Purge everything (use with care)

```typescript
async function purgeEverything(env: Env, reason: string): Promise<void> {
  // Guard: require explicit reason string to prevent accidental calls
  if (!reason || reason.length < 10) {
    throw new Error("Provide a descriptive reason for full-zone purge");
  }
  const result = await cloudflareZonePurge(env.CF_ZONE_ID, env.CF_PURGE_TOKEN, {
    purge_everything: true,
  });
  await logPurge(env, "everything", [reason], result.id);
}
```

### 7. Rate limiting on purge API

Cloudflare enforces 1,000 purge requests per minute per zone (URL-level purge counts per URL). Implement an exponential backoff retry:

```typescript
async function purgeWithRetry(
  env: Env,
  payload: PurgePayload,
  maxRetries = 3,
): Promise<{ id: string }> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await cloudflareZonePurge(env.CF_ZONE_ID, env.CF_PURGE_TOKEN, payload);
    } catch (err: any) {
      if (attempt === maxRetries) throw err;
      // 429 = rate limited; also retry on 5xx
      const isRetryable = err.message.includes("429") || err.message.includes("5");
      if (!isRetryable) throw err;
      // Exponential backoff: 1s, 2s, 4s
      await new Promise(r => setTimeout(r, 1000 * 2 ** attempt));
    }
  }
  throw new Error("unreachable");
}
```

### 8. Purge audit log in D1

```typescript
async function logPurge(
  env: Env,
  method: string,
  targets: string[],
  cfPurgeId: string,
): Promise<void> {
  await env.PURGE_LOG.prepare(
    `INSERT INTO purge_audit (ts, method, targets, cf_purge_id)
     VALUES (?, ?, ?, ?)`,
  )
    .bind(
      new Date().toISOString(),
      method,
      JSON.stringify(targets),
      cfPurgeId,
    )
    .run();
}

// D1 schema
const SCHEMA = `
CREATE TABLE IF NOT EXISTS purge_audit (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         TEXT    NOT NULL,
  method     TEXT    NOT NULL,  -- url | tag | host | everything
  targets    TEXT    NOT NULL,  -- JSON array
  cf_purge_id TEXT  NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_purge_audit_ts ON purge_audit(ts);
`;
```

### 9. Full Worker handler

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Validate internal secret header
    const secret = <redacted-secret>"X-Purge-Secret");
    if (secret !== env.INTERNAL_PURGE_SECRET) {
      return new Response("Forbidden", { status: 403 });
    }

    const body = await request.json<{ method: string; targets: string[] }>();

    switch (body.method) {
      case "url":  await purgeByUrls(env, body.targets);         break;
      case "tag":  await purgeByTags(env, body.targets);         break;
      case "host": await purgeByHost(env, body.targets[0]);      break;
      default: return new Response("Unknown method", { status: 400 });
    }

    return Response.json({ ok: true });
  },
};
```

## Implementation Details

- The purge token needs `Zone:Cache Purge` permission only — scope it tightly.
- Cache-tag purge requires **Pro plan or higher**. On Free plans, the API call succeeds but is silently ignored.
- `purge_everything` resets the zone's cache epoch; all cached objects are considered stale. CDN hit rate drops to near zero for several minutes.
- URL purge is case-sensitive and must match the exact URL including query string if Cloudflare caches query variants.
- The returned `id` from the purge call is a Cloudflare operation ID usable for support tickets.

## Anti-patterns

- Do not call `purge_everything` from automated pipelines without a human confirmation gate.
- Do not purge by URL with 1,000+ URLs in a single deploy hook — batch and space out over multiple Workers invocations.
- Do not store the purge API token in `wrangler.toml` `[vars]`; always use `wrangler secret put`.
- Do not skip logging — without an audit trail, debugging stale cache incidents is blind.
- Do not rely solely on TTL-based expiry for dynamic content; active purge is required for correctness.

## Gotchas

- Cloudflare returns `200 OK` with `success: false` on some errors (e.g., invalid zone ID). Always check `json.success`.
- Tag purge propagates to the edge asynchronously. A 200 response does not mean all PoPs have invalidated.
- Purge by host purges **all cached assets** under that hostname — this is often broader than intended.
- Workers in `request.cf.colo` may still serve a cached response for up to 1–2 s post-purge due to in-memory caching.
- D1 `run()` is fire-and-forget in Workers; await it or wrap in `ctx.waitUntil()` to avoid log loss.

## Verification

```bash
# Trigger purge via Worker
curl -X POST https://purge.example.com/ \
  -H 'Content-Type: application/json' \
  -H 'X-Purge-Secret: <secret>' \
  -d '{"method":"url","targets":["https://example.com/products/widget-pro"]}'

# Confirm via Cache-Status header (should be MISS after purge)
curl -si https://example.com/products/widget-pro | grep cf-cache-status

# Query audit log
wrangler d1 execute example project-db-prod \
  --command "SELECT * FROM purge_audit ORDER BY ts DESC LIMIT 20;"
```

## Related

- `documentation/categories/infra/workers-pulumi-cloudflare-iac.md`
- `documentation/categories/infra/workers-waf-custom-ruleset-api.md`
- Cloudflare Cache Rules: https://developers.cloudflare.com/cache/how-to/cache-rules/

## Sources

- https://developers.cloudflare.com/api/operations/zone-purge
- https://developers.cloudflare.com/cache/how-to/purge-cache/
- https://developers.cloudflare.com/cache/how-to/cache-tags/
