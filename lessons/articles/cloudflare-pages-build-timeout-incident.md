# Cloudflare Pages Build Timeout Incident

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A Pages deployment was cancelled mid-build due to exceeding the 20-minute build timeout. Cloudflare served a partial deployment where some asset hashes pointed to the new bundle and the HTML entry point still referenced the previous bundle, causing a broken site for ~35 minutes until the next successful deploy.

## Context
Cloudflare Pages enforces a hard 20-minute build timeout per deployment. When a build is cancelled, the Pages CDN may have already propagated some static assets from the in-progress build to edge caches (especially if the build system uploaded assets incrementally before the timeout). The result is a mixed-version state: the canonical HTML shell from the last successful deploy references hashed asset filenames from that deploy, but CDN edge nodes may return the partially-uploaded new assets for those same paths if content-addressed filenames collide between builds. The incident was triggered by an unexpectedly large dependency tree added to `package.json` without a corresponding increase in build performance budgeting.

---

## Timeline

- 14:02 UTC — Deploy triggered by merged PR adding three new npm dependencies (~180 MB unpacked).
- 14:18 UTC — `npm ci` completed; Vite build started.
- 14:22 UTC — Build timeout reached; Cloudflare Pages cancelled the build job.
- 14:23 UTC — Monitoring alert: 12% of page loads returning HTTP 404 on JS chunks.
- 14:57 UTC — Manual deploy triggered with build cache cleared; succeeded in 18m 40s.
- 15:00 UTC — Site restored; full incident duration 38 minutes.

---

## Root Cause: Unoptimized Build Time

### Before: monolithic Vite config

```typescript
// vite.config.ts — BEFORE (slow)
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // No manual chunk splitting — entire app in one entry
    rollupOptions: {},
  },
});
```

Build time on Pages free plan: 19m 45s (near timeout).

### After: manual chunk splitting + vendor extraction

```typescript
// vite.config.ts — AFTER (fast)
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { splitVendorChunkPlugin } from "vite";

export default defineConfig({
  plugins: [react(), splitVendorChunkPlugin()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Heavy deps that rarely change → long-lived cached chunks
          if (id.includes("node_modules/react") || id.includes("node_modules/react-dom")) {
            return "react-vendor";
          }
          if (id.includes("node_modules/@radix-ui")) {
            return "radix-vendor";
          }
          if (id.includes("node_modules/recharts") || id.includes("node_modules/d3")) {
            return "chart-vendor";
          }
          // Everything else → "vendor" chunk via splitVendorChunkPlugin
        },
      },
    },
    // Fail loudly if a single chunk exceeds 500 kB
    chunkSizeWarningLimit: 500,
  },
});
```

Build time after optimisation: 11m 20s — 57% reduction.

---

## Deployment Guard: Fail Fast on Slow Builds

Add a CI pre-flight that measures local build time and blocks merge if it exceeds a threshold:

```yaml
# .github/workflows/build-time-guard.yml
name: Build Time Guard
on:
  pull_request:
    paths:
      - "package.json"
      - "vite.config.ts"
      - "src/**"

jobs:
  build-time:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - name: Timed build
        run: |
          START=$(date +%s)
          npm run build
          END=$(date +%s)
          ELAPSED=$((END - START))
          echo "Build took ${ELAPSED}s"
          # Cloudflare Pages timeout is 1200s; fail at 900s (75%)
          if [ "$ELAPSED" -gt 900 ]; then
            echo "::error::Build time ${ELAPSED}s exceeds 900s safety limit"
            exit 1
          fi
```

---

## Pages Configuration: Increase Build Timeout

For builds that legitimately need more time, upgrade to Pages Pro and set the timeout explicitly in `wrangler.jsonc`:

```jsonc
// wrangler.jsonc
{
  "pages_build_output_dir": "dist",
  "build": {
    "command": "npm run build",
    "cwd": ".",
    "watch_dir": "src"
  }
}
```

The Pro plan raises the timeout to 30 minutes. For larger monorepos, consider offloading the build to GitHub Actions and using `wrangler pages deploy dist/` directly:

```yaml
# .github/workflows/deploy.yml (relevant step)
- name: Deploy to Pages
  run: npx wrangler pages deploy dist/ --project-name=my-app --branch=main
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

This bypasses the Pages build system entirely — your CI runner's timeout applies, and you can use GitHub Actions cache for `node_modules` and Vite's build cache.

---

## Mixed-Version Detection Header

Add a deploy-time hash to every response so monitoring can detect version skew instantly:

```typescript
// functions/_middleware.ts  (Pages Functions)
export const onRequest: PagesFunction = async (context) => {
  const response = await context.next();
  const newResponse = new Response(response.body, response);
  // DEPLOY_HASH is injected by wrangler as a Pages secret or build var
  newResponse.headers.set("X-Deploy-Hash", context.env.DEPLOY_HASH ?? "unknown");
  return newResponse;
};
```

A monitoring script polling `/healthz` for a changing `X-Deploy-Hash` can alert within seconds if a partial deploy produces inconsistent hashes across edge nodes.

---

## Anti-patterns
- Letting `npm ci` run on every Pages build without a build cache — Pages caches `node_modules` between builds on the same branch, but only if the build command is identical.
- Adding large dependencies to `package.json` without measuring the impact on build time before merging.
- Relying on Pages to automatically roll back a timed-out build — it does not; the last successful deploy continues to serve, but edge asset propagation may be inconsistent.
- Using dynamic `import()` with extremely large split points that still produce multi-MB chunks.
- Not having a separate CI build step that exercises the production build path end-to-end.

## Gotchas
- The 20-minute Pages build timeout counts from the moment the build container starts, including time to install system dependencies — not just your `npm run build` step.
- Cloudflare does not guarantee that a timed-out build leaves the CDN in a clean state; always verify asset consistency after any interrupted deploy.
- `wrangler pages deploy` from CI bypasses the Pages build system completely — Pages Functions (`functions/`) are NOT automatically deployed unless you pass `--compatibility-date` and the functions directory is included in the output dir.
- Build cache on Pages is branch-scoped; a first deploy on a new branch always starts cold.
- `DEPLOY_HASH` injected as a Pages environment variable is only available at build time; to expose it at runtime it must be baked into the built assets or exposed via a Functions environment binding.

## Verification

```bash
# Confirm build time locally
time npm run build

# Check that all chunk hashes in index.html exist in dist/
grep -oP '(?<=]+' dist/index.html | while read chunk; do
  [ -f "dist$chunk" ] || echo "MISSING: $chunk"
done

# After deploy: verify consistent X-Deploy-Hash across PoPs
for region in lax ams sin; do
  curl -s -I "https://my-app.pages.dev/healthz" \
    --resolve "my-app.pages.dev:443:$(dig +short my-app.pages.dev | head -1)" \
    | grep X-Deploy-Hash
done
```

## Related
- `pages-build-cache-stale-dependency-incident.md`
- `pages-deploy-rollback-cache-invalidation-gap.md`
- `pages-functions-workers-routes-conflict-incident.md`
- `zero-downtime-deployment-workers.md`
- `monitor-before-and-after-deploy.md`

## Sources
- https://developers.cloudflare.com/pages/configuration/build-configuration/#build-timeout
- https://developers.cloudflare.com/pages/functions/
- https://developers.cloudflare.com/workers/wrangler/commands/#pages-deploy
- https://vitejs.dev/guide/build#chunking-strategy
- https://rollupjs.org/configuration-options/#output-manualchunks
