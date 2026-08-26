# Pages Deploy Rollback Cache Invalidation Gap

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

A Cloudflare Pages project was rolled back to the previous deployment after a regression was detected in production. The rollback completed in under 30 seconds, the Pages dashboard confirmed the older deployment was serving traffic — but roughly 15–20 % of end-users continued to receive stale assets from the broken deployment for up to 12 minutes. Support tickets reported broken layouts and JS errors that had already been confirmed fixed by the engineering team who were themselves seeing the correct build.

## Context

Cloudflare Pages serves static assets through Cloudflare's edge cache. When a new deployment is promoted, assets are served from the new deployment's asset namespace. Rollback via the dashboard swaps the "active deployment" pointer but does **not** issue a Cache Purge API call for the previous deployment's asset paths — that is left to the operator. Cache-Control headers on the broken build's JS/CSS bundles were set to `max-age=31536000, immutable` (correct for content-addressed filenames), but the HTML entrypoints were `max-age=300` (5 minutes). Edge nodes that had cached the broken HTML within that 5-minute window continued serving it, along with the correct (but wrong-version) JS chunks referenced therein, for the remainder of the TTL window.

The team only discovered the gap 8 minutes into the incident when a customer in a different region filed a support ticket. Internal engineers had already busted their own browser caches manually.

---

## 1. How Pages Rollback Actually Works

Rolling back via the dashboard (or via Wrangler `pages deployment rollback`) promotes an older deployment UUID as the canonical one. It does **not**:

- Purge edge cache for the prior deployment's assets.
- Invalidate Cache Rules that matched the old paths.
- Reset `ETag` / `Last-Modified` on objects that edge nodes already hold.

The Pages CDN uses immutable content-addressed filenames for JS/CSS (`/assets/main.abc123.js`), so those rarely cause issues on rollback — the new (old) HTML will reference different hashes and download fresh chunks. The risk is with HTML files themselves and any non-hashed assets (images, fonts, `robots.txt`, `sitemap.xml`).

```typescript
// Wrangler CLI rollback — does NOT purge cache
// wrangler pages deployment rollback <DEPLOYMENT_ID> --project-name my-project

// You must separately call the Cache Purge API
const purgeResponse = await fetch(
  `https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache`,
  {
    method: "POST",
    headers: {
      Authorization: `Bearer ${CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      // Purge all HTML entry points by URL pattern
      files: [
        `https://example.com/`,
        `https://example.com/index.html`,
        `https://example.com/404.html`,
      ],
    }),
  }
);
const result = await purgeResponse.json();
if (!result.success) throw new Error(JSON.stringify(result.errors));
```

---

## 2. Detecting the Gap with Workers

A lightweight Worker placed in front of Pages can emit a version header that Logpush can track. When the header stops matching the expected deployment ID, cache staleness can be detected programmatically.

```typescript
// worker: version-probe.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const response = await env.ASSETS.fetch(request);
    const mutable = new Response(response.body, response);
    // Deployment ID injected at build time via wrangler.toml [vars]
    mutable.headers.set("X-Deployment-Id", env.DEPLOYMENT_ID);
    return mutable;
  },
} satisfies ExportedHandler<Env>;
```

```toml
# wrangler.toml
[vars]
DEPLOYMENT_ID = "v2.14.3-abc1234"
```

After rollback, update `DEPLOYMENT_ID` and redeploy the Worker; a mismatch between observed and expected headers signals cached stale content.

---

## 3. Automated Post-Rollback Cache Purge Script

Wrap the Wrangler rollback step and the purge call together so neither can be done without the other.

```typescript
// scripts/rollback-and-purge.ts
import { execSync } from "node:child_process";

const ZONE_ID = process.env.CF_ZONE_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;
const PROJECT = process.env.CF_PAGES_PROJECT!;
const DEPLOYMENT_ID = process.argv[2];
const BASE_URL = process.env.SITE_BASE_URL!; // e.g. https://example.com

if (!DEPLOYMENT_ID) {
  console.error("Usage: ts-node rollback-and-purge.ts <deployment-id>");
  process.exit(1);
}

// Step 1: rollback
console.log(`Rolling back ${PROJECT} to ${DEPLOYMENT_ID}...`);
execSync(
  `wrangler pages deployment rollback ${DEPLOYMENT_ID} --project-name ${PROJECT}`,
  { stdio: "inherit" }
);

// Step 2: purge HTML entry points and well-known paths
const urlsToPurge = ["/", "/index.html", "/404.html", "/robots.txt", "/sitemap.xml"].map(
  (path) => `${BASE_URL}${path}`
);

console.log("Purging cache for:", urlsToPurge);
const res = await fetch(`https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache`, {
  method: "POST",
  headers: { Authorization: `Bearer ${API_TOKEN}`, "Content-Type": "application/json" },
  body: JSON.stringify({ files: urlsToPurge }),
});
const data = (await res.json()) as { success: boolean; errors: unknown[] };
if (!data.success) throw new Error(`Purge failed: ${JSON.stringify(data.errors)}`);
console.log("Cache purge complete.");
```

---

## 4. Cache-Control Strategy for Pages HTML

Setting an aggressive max-age on HTML files is the root cause of the long invalidation window. Prefer short TTLs on HTML while keeping immutable long-TTLs on hashed assets.

```typescript
// _headers file at the root of your Pages project
/*
  Cache-Control: public, max-age=0, must-revalidate

/*.html
  Cache-Control: public, max-age=0, must-revalidate

/assets/*
  Cache-Control: public, max-age=31536000, immutable
```

Alternatively, use a Cache Rule in the Cloudflare dashboard scoped to `*.html` paths with **Edge TTL: Bypass** so the edge always re-validates HTML with the Pages origin.

---

## 5. Runbook Addition

Add a post-rollback verification step to the existing incident runbook:

```markdown
## Rollback Runbook — Pages Projects

1. Identify target deployment ID from `wrangler pages deployment list --project-name <name>`.
2. Run `npm run rollback -- <deployment-id>` (wraps rollback + purge script).
3. Wait 30 s, then hit `curl -I https://example.com/ | grep x-deployment-id`.
4. Confirm `X-Deployment-Id` matches expected value from three edge locations
   (use `--resolve example.com:443:<edge-ip>` with known PoP IPs, or a tool like
   `cf-trace` / `dog` against different regions).
5. Check Logpush stream for any remaining requests returning old deployment ID.
6. Escalate to CDN team if stale responses persist beyond 2 minutes post-purge.
```

---

## Anti-patterns

- Treating a Pages rollback as an atomic, cache-coherent operation — it is not.
- Using `max-age=300` on HTML entrypoints and assuming 5 minutes is acceptable during incidents. 5 minutes is an eternity in a P0.
- Manually verifying rollback from a single browser on a single machine — browser caches, ISP caches, and corporate proxies all add layers of staleness invisible from one seat.
- Purging by tag instead of by URL for HTML files — tag-based purge only works for assets that had a `Cache-Tag` header set at response time, which Pages does not add automatically.

## Gotchas

- `purge_cache` with `files` only purges the exact URL (including query string). Pass both `https://example.com/` and `https://example.com/index.html` separately.
- Cloudflare Free and Pro plans are rate-limited to 30 individual-URL purge requests per API call; batch them if you have more paths.
- Rollback via the dashboard uses the same underlying API as Wrangler; neither path triggers a purge.
- If your Pages project uses a custom domain **and** the `pages.dev` preview URL, purge both zone IDs (or use `purge_everything` on the `pages.dev` zone, which has no end-user traffic implications).
- Workers placed in front of Pages that cache responses independently add a second cache layer that also requires invalidation.

## Verification

```bash
# Confirm active deployment
wrangler pages deployment list --project-name my-project | head -5

# Check edge-served deployment header from three regions
for region in lax fra sin; do
  echo "=== $region ==="
  curl -sI --http1.1 "https://example.com/" \
    -H "X-Forwarded-For: <$region-ip>" | grep -i "x-deployment\|cf-cache-status"
done

# Confirm purge API call succeeded (exit 0 = success)
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/purge_cache" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"files":["https://example.com/"]}' | jq '.success'
```

## Related

- `r2-eventual-consistency-cache-invalidation-incident.md`
- `cache-invalidation-is-harder-than-caching.md`
- `cache-cold-start-avalanche.md`
- `zero-downtime-deployment-workers.md`
- `always-test-rollback-before-deploying.md`

## Sources

- Cloudflare Pages docs — Deployments and Rollbacks: https://developers.cloudflare.com/pages/configuration/rollbacks/
- Cloudflare Cache Purge API: https://developers.cloudflare.com/cache/how-to/purge-cache/
- Cloudflare `_headers` file reference: https://developers.cloudflare.com/pages/configuration/headers/
- Cloudflare Cache Rules: https://developers.cloudflare.com/cache/how-to/cache-rules/
