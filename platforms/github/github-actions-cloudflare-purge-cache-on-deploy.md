# GitHub Actions Cloudflare Purge Cache on Deploy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

After deploying a new version of static assets (JS, CSS, images) or a Workers site, Cloudflare's edge cache still serves the stale version to users for up to the asset's `Cache-Control: max-age`. You need CI to purge the relevant cache entries immediately after every successful deployment, with support for purging by URL list, cache tag, or entire zone depending on the deployment scope.

## Context

Cloudflare's Cache Purge API accepts three modes: purge by URL list (up to 30 URLs per request), purge by cache tag (requires Enterprise or Cache Reserve), and full zone purge. For most Workers + Pages deployments the URL-list approach covers HTML entry points and versioned asset manifests. Cache tags are the preferred approach when assets are tagged at the Worker level via the `Cache-Tag` response header. The Cloudflare API endpoint is `POST /zones/{zone_id}/purge_cache`. The operation is idempotent and typically propagates globally within 150 ms.

---

## 1. Purge by URL List After Deploy

```yaml
# .github/workflows/deploy-and-purge.yml
name: Deploy + Purge Cache

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    outputs:
      deploy_ok: ${{ steps.deploy.outcome }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'pnpm' }

      - run: pnpm install --frozen-lockfile

      - name: Deploy to Cloudflare Workers / Pages
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: pnpm wrangler deploy

  purge-cache:
    needs: deploy
    if: needs.deploy.outputs.deploy_ok == 'success'
    runs-on: ubuntu-latest

    steps:
      - name: Purge entry-point URLs
        env:
          CF_ZONE_ID:   ${{ secrets.CF_ZONE_ID }}
          CF_API_TOKEN: ${{ secrets.CF_CACHE_PURGE_TOKEN }}
        run: |
          curl -sf -X POST \
            "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/purge_cache" \
            -H "Authorization: Bearer $CF_API_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{
              "files": [
                "https://example.com/",
                "https://example.com/index.html",
                "https://example.com/app.webmanifest"
              ]
            }' | jq '.success'
```

## 2. Purge by Cache Tag (Workers Paid / Enterprise)

```typescript
// src/index.ts — tag responses at the Worker level
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const response = await fetch(request);

    // Clone response and add Cache-Tag header for later targeted purge
    const tagged = new Response(response.body, response);
    const tags: string[] = ['global'];

    if (url.pathname.startsWith('/api/')) tags.push('api');
    if (url.pathname.startsWith('/blog/')) tags.push('blog', `post-${url.pathname.split('/')[2]}`);

    tagged.headers.set('Cache-Tag', tags.join(','));
    tagged.headers.set('Cache-Control', 'public, max-age=86400');
    return tagged;
  },
} satisfies ExportedHandler<Env>;
```

```yaml
      - name: Purge by cache tag
        env:
          CF_ZONE_ID:   ${{ secrets.CF_ZONE_ID }}
          CF_API_TOKEN: ${{ secrets.CF_CACHE_PURGE_TOKEN }}
          PURGE_TAGS:   ${{ vars.PURGE_TAGS }}   # e.g. "global,api" stored as a repo variable
        run: |
          curl -sf -X POST \
            "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/purge_cache" \
            -H "Authorization: Bearer $CF_API_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"tags\": $(echo "$PURGE_TAGS" | jq -R 'split(",")')}" \
            | jq '.success'
```

## 3. Generate URL List Dynamically from Wrangler Build Output

```yaml
      - name: Generate purge URL list from build manifest
        id: urls
        run: |
          # Read asset manifest produced by wrangler pages build
          URLS=$(node -e "
            const manifest = require('./.cloudflare/manifest.json');
            const base = 'https://example.com';
            const urls = [base + '/', ...Object.keys(manifest).map(k => base + k)];
            // Cloudflare allows max 30 URLs per request
            console.log(JSON.stringify(urls.slice(0, 30)));
          ")
          echo "urls=$URLS" >> "$GITHUB_OUTPUT"

      - name: Purge dynamic URL list
        env:
          CF_ZONE_ID:   ${{ secrets.CF_ZONE_ID }}
          CF_API_TOKEN: ${{ secrets.CF_CACHE_PURGE_TOKEN }}
        run: |
          curl -sf -X POST \
            "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/purge_cache" \
            -H "Authorization: Bearer $CF_API_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"files\": ${{ steps.urls.outputs.urls }}}" \
            | jq -e '.success == true'
```

## 4. Purge in Batches When URL Count Exceeds 30

```typescript
// scripts/purge-cache.ts
const ZONE_ID   = process.env.CF_ZONE_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;

async function purgeUrls(urls: string[]): Promise<void> {
  const BATCH_SIZE = 30;
  for (let i = 0; i < urls.length; i += BATCH_SIZE) {
    const batch = urls.slice(i, i + BATCH_SIZE);
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${API_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ files: batch }),
      },
    );
    const data = (await res.json()) as { success: boolean; errors: unknown[] };
    if (!data.success) {
      console.error(`Batch ${i / BATCH_SIZE + 1} failed:`, data.errors);
      process.exit(1);
    }
    console.log(`Purged batch ${i / BATCH_SIZE + 1}: ${batch.length} URLs`);
    // Respect rate limit: 1000 purge requests per minute per zone
    if (i + BATCH_SIZE < urls.length) await new Promise(r => setTimeout(r, 100));
  }
}

const allUrls: string[] = JSON.parse(process.argv[2]);
await purgeUrls(allUrls);
```

## 5. Scope the API Token to Cache Purge Only

The `CF_CACHE_PURGE_TOKEN` secret should be scoped to the minimum permission needed:

```
Cloudflare Dashboard → My Profile → API Tokens → Create Token
  - Template: "Cache Purge"
  - Permissions: Zone → Cache Purge → Purge
  - Zone Resources: Include → Specific Zone → example.com
```

```yaml
      - name: Verify token scope (dry-run)
        env:
          CF_API_TOKEN: ${{ secrets.CF_CACHE_PURGE_TOKEN }}
        run: |
          curl -sf "https://api.cloudflare.com/client/v4/user/tokens/verify" \
            -H "Authorization: Bearer $CF_API_TOKEN" \
            | jq '.result.status'
          # Should return "active"
```

---

## Anti-patterns

- Using a full `Zone:Edit` or `Account:Admin` token for cache purge — a leaked token grants far more than cache operations; scope it to `Cache Purge` only.
- Purging the entire zone on every deploy (`"purge_everything": true`) — this invalidates shared CDN cache for all users across all paths, causing a cache cold-start storm on high-traffic sites; prefer URL list or cache tag purges.
- Purging before the deployment is confirmed successful — purging first and then having the deploy fail leaves users with a cache miss that returns a stale or 500 response.
- Ignoring `jq -e '.success == true'` exit code — `curl -sf` returns 0 even when the Cloudflare API returns `{"success": false}` with an HTTP 200 body.

## Gotchas

- Cloudflare rate-limits cache purge requests to 1,000 per minute per zone; batching more than 1,000 URLs without a delay will result in 429 errors.
- Cache tags require the `Cache-Tag` response header to be set by the Worker or origin — Cloudflare does not auto-generate tags from URL patterns.
- Pages deployments to `*.pages.dev` preview URLs are not cached at the edge by default; purge only applies to custom domain deployments.
- The Zone ID and the Account ID are different values; `CF_ZONE_ID` maps to a specific domain, not the account. Find it in the Cloudflare Dashboard → domain overview → right sidebar.

## Verification

```bash
# Confirm purge succeeded
curl -I https://example.com/ | grep -i 'cf-cache-status'
# Should return: cf-cache-status: MISS on first request after purge
# Then: cf-cache-status: HIT on subsequent requests
```

## Related

- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-workers-preview-environments.md`
- `github-actions-cache-wrangler-build-optimization.md`
- `github-actions-wrangler-pages-functions-deploy-pipeline.md`

## Sources

- https://developers.cloudflare.com/cache/how-to/purge-cache/
- https://developers.cloudflare.com/api/operations/zone-purge
- https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-cache-tags/
- https://developers.cloudflare.com/fundamentals/api/reference/limits/
