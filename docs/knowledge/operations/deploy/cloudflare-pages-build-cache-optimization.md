# cloudflare-pages-build-cache-optimization

**Issue:** Optimizing Cloudflare Pages build times with cache
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

Cloudflare Pages builds take 4–8 minutes per push because every build
re-downloads `node_modules` from npm, re-compiles TypeScript, and
re-runs a full Next.js build. On a mobile-first deployment pipeline
where a slow build means delayed hotfixes, this compounds: a mobile
crash fix takes longer to reach users than it should.

## Context

Cloudflare Pages build workers are ephemeral; they do not persist the
filesystem between runs. However, Pages exposes a `NODE_VERSION`
environment variable and honours a preset build system (Next.js,
Remix, Astro, etc.) that enables Next.js's `.next/cache` persistence
when the build command uses the `next build` preset. For custom build
commands, cache must be managed explicitly through the build output
directory convention or via cache busting environment variables.

**Source:** Cloudflare Docs — Build caching (Pages); Vercel — Next.js
build caching.

## The "node_modules restore via package-lock hash" pattern

Cloudflare Pages does not have a first-class `cache:` directive like
GitHub Actions, but the Next.js preset automatically restores
`.next/cache` between builds. For `node_modules`, the fastest
approach is to avoid reinstalling when the lockfile has not changed.

When using a custom build command, add an install guard:

```bash
# pages-build.sh  (set as Build command in dashboard)
#!/bin/bash
set -e

# Re-use node_modules if package-lock.json has not changed.
LOCK_HASH=$(sha256sum package-lock.json | awk '{print $1}')
CACHE_TAG=".cache-tag-${LOCK_HASH}"

if [ ! -f "$CACHE_TAG" ]; then
  echo "package-lock changed — running npm ci"
  npm ci --prefer-offline
  touch "$CACHE_TAG"
else
  echo "package-lock unchanged — skipping npm ci"
fi

npm run build
```

This reduces install time from ~90 s to ~5 s on cache hits.

## The "Next.js .next/cache persistence" pattern

The Cloudflare Pages Next.js preset (`@cloudflare/next-on-pages`)
preserves `.next/cache` across builds automatically. Verify this is
active and not disabled by a custom build command:

```
# Dashboard: Settings → Build & deployments
Build system version:  2 (required for cache)
Framework preset:      Next.js
Build command:         npx @cloudflare/next-on-pages
Build output dir:      .vercel/output/static
```

Explicitly warm up the turborepo / Next.js remote cache if you use a
monorepo:

```bash
# In Build command (append after framework command)
npx turbo build --cache-dir=.turbo
```

Provide the `TURBO_TOKEN` and `TURBO_TEAM` environment variables in
the Pages dashboard to enable Turbo remote cache.

## The "cache key strategy" pattern

Cache busting strategy matrix:

```
+---------------------+-----------------------+------------------+
| What to cache       | Key input             | Bust when        |
+---------------------+-----------------------+------------------+
| node_modules        | sha256(package-       | lockfile changes |
|                     | lock.json)            |                  |
+---------------------+-----------------------+------------------+
| .next/cache         | Next.js preset        | automatic        |
| (incremental)       | manages internally    |                  |
+---------------------+-----------------------+------------------+
| Turbo build cache   | TURBO_TEAM +          | code changes     |
|                     | content hash          | (automatic)      |
+---------------------+-----------------------+------------------+
| Generated assets    | git SHA of assets/    | any asset change |
| (SVG sprites, etc.) | directory             |                  |
+---------------------+-----------------------+------------------+
```

Never use a time-based cache key (e.g., `$(date +%Y-%m-%d)`) — it
busts daily regardless of whether anything changed.

## The "mobile-first deployment pipeline" pattern

A mobile client that cold-starts over a 4G connection needs the
CDN edge populated before the app store release lands. Slow Pages
builds create a window where the app update is live but the Workers
API or the Pages asset edge cache is stale.

Timeline target with cache optimisation:

```
+----------------------------+----------+------------------+
| Step                       | Baseline | With cache       |
+----------------------------+----------+------------------+
| npm ci                     |  95 s    |   4 s (hit)      |
| Next.js compile (cold)     | 180 s    |  35 s (incr.)    |
| Cloudflare asset upload    |  45 s    |  45 s (no cache) |
| Worker deploy + propagate  |  20 s    |  20 s            |
+----------------------------+----------+------------------+
| Total                      | ~5.7 min | ~1.7 min         |
+----------------------------+----------+------------------+
```

The 1.7-minute build means a mobile hotfix is globally propagated
within 3 minutes of merge, rather than 7–9 minutes.

## The "build cache invalidation via environment variable" pattern

Force a full cache bust without touching the lockfile by setting a
`CACHE_BUST` environment variable in the Pages dashboard:

```bash
# pages-build.sh
CACHE_BUST="${CACHE_BUST:-0}"
LOCK_HASH=$(sha256sum package-lock.json | awk '{print $1}')
CACHE_TAG=".cache-tag-${LOCK_HASH}-${CACHE_BUST}"
```

Increment `CACHE_BUST` in the Pages dashboard when `node_modules`
becomes corrupt or a native addon needs recompiling.

## Anti-patterns

- **Using `npm install` instead of `npm ci`.** `npm install` can
  mutate the lockfile; `npm ci` is reproducible and faster in CI.
- **Committing `node_modules` to the repo.** Enormous clone time
  negates any install savings, and the Pages build still re-clones.
- **Setting Build command to `npm install && npm run build`.**
  This always installs from scratch. Move install into a script
  with lockfile-hash guarding.
- **Ignoring `.next/cache` size growth.** Incremental Next.js
  cache grows unbounded; bust it monthly via `CACHE_BUST` or when
  build output size exceeds 500 MB.
- **Disabling the Pages Next.js preset for a manual Webpack build.**
  You lose automatic cache management and must replicate it manually.

## Gotchas

- Pages build caching only applies within the same branch. Preview
  deployments for feature branches always start cold on first push.
- The `.next/cache` restore adds ~10 s of overhead even on a hit;
  this is still a net win over a full rebuild (3+ minutes).
- `wrangler pages deploy` (CI-driven) does not benefit from the
  Pages dashboard's build cache. Cache only applies to builds
  triggered by the Pages Git integration.
- Mobile clients cached by a service worker may continue serving
  stale Pages assets after a deploy. Ensure your service worker
  uses a network-first strategy for HTML and a stale-while-
  revalidate strategy for JS/CSS with short max-age.

## Verification

- **Build log:** `package-lock unchanged — skipping npm ci` appears
  on the second build after a no-lockfile-change push.
- **Dashboard:** Pages → Build → Duration drops below 2 minutes for
  non-lockfile-change pushes.
- **Live:** `curl -I https://your-pages-project.pages.dev` returns
  `cf-cache-status: HIT` on the second request.

## Related

- `documentation/docs/policies/deploy/wrangler-deploy-github-actions-workers.md`
- `documentation/docs/policies/deploy/docker-layer-caching-ci.md`
- `documentation/docs/policies/deploy/mobile-app-store-staged-rollout.md`
- `documentation/docs/policies/deploy/cdn-deploy-cache-purge-orchestration.md`

## Sources

- https://developers.cloudflare.com/pages/configuration/build-caching/
- https://developers.cloudflare.com/pages/framework-guides/nextjs/
- https://turbo.build/repo/docs/crafting-your-repository/caching
