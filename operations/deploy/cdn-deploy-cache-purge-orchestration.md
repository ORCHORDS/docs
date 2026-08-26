# cdn-deploy-cache-purge-orchestration

**Issue:** example project ships its frontend through a CDN, and the deploy pipeline ends at "origin updated." Users report seeing the old UI for up to 30 minutes after a release because the CDN keeps serving cached HTML and stale asset references; when someone manually runs "purge everything" to fix it, the origin takes the full traffic spike at once and 5xx errors spike for two minutes. Cache invalidation is currently a human decision made after complaints, not an orchestrated deploy step.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why Deploys Make CDN State Inconsistent

1. **The deploy and the cache are separate systems.** Updating the origin changes the source of truth but says nothing to edge caches holding copies until TTL expiry; a 1-hour HTML TTL means up to an hour of stale production by default.
2. **HTML references assets, so stale HTML poisons fresh assets.** If `index.html` is cached and references `app.OLDHASH.js`, deploying new assets does nothing for users still receiving the old HTML — the two layers must be invalidated together or not at all.
3. **Multi-CDN multiplies the problem.** With more than one CDN (or CDN plus a service-worker cache plus browser cache), each layer has its own TTL and purge API; purging one layer while another still serves stale content produces "it works on my connection" bug reports.
4. **Thundering herd on full purge.** Purging everything empties every edge node simultaneously; the next request wave revalidates against the origin all at once. This is the self-inflicted outage pattern: the deploy succeeds, the purge knocks the origin over.

## Prefer Immutable Assets Over Purging

1. **Content-hash your asset filenames.** `app.a3f9c2.js` changes filename when content changes, so new deploys are new URLs and old cached entries are simply never requested again. This removes asset purging from the problem entirely.
2. **Never hash the HTML entry point.** `index.html` must stay at a stable URL with short TTL (or `no-cache`) because it is the pointer that routes users to the new hashed assets.
3. **Set cache headers by class.** Hashed assets: `Cache-Control: public, max-age=31536000, immutable`. HTML: `no-cache` or short `max-age` with `stale-while-revalidate` so users get an instant (possibly one-version-stale) page while revalidation happens in the background.
4. **With this layout the purge surface shrinks to one URL** — the HTML entry points — which is a cheap, targeted API call instead of a zone-wide event.

## Purge Scope Selection

1. **Purge by URL or by tag/prefix — never by default to "purge everything."** Cloudflare's own guidance recommends single-file/URL purges as the default and reserves `purge_everything` for releases that truly change most of the zone; it explicitly warns about the origin-load consequences.
2. **Use cache tags or key prefixes for grouped invalidation.** Purge-by-tag (Fastly surrogates, Cloudflare cache-tag purges) lets you invalidate "all product-page fragments" without touching the rest of the zone; this is the right primitive when HTML is composed of cached fragments.
3. **Soft purge where available.** Fastly soft purge marks objects stale but keeps serving them while revalidation happens in the background, flattening the thundering herd into a gradual refetch. If your CDN lacks it, emulate with `stale-while-revalidate` on origin responses.
4. **Respect custom cache keys.** If your zone uses custom cache keys (device type, geo, Accept-Language variants), a plain URL purge may miss key variants — the purge API requires the same key inputs the cache used, and missing them leaves some users on stale content.
5. **Rate-limit your own purge calls.** Purge APIs are rate-limited (Cloudflare's is on the order of 1000 requests/min per zone by default); batch URLs into single API calls rather than fanning out one call per file.

## Orchestration in the Deploy Pipeline

1. **Purge is a first-class deploy step, not a follow-up.** Sequence: build → deploy origin assets → verify origin serves new manifest (smoke check) → purge HTML entry URLs → verify CDN serves new manifest. Purging before the origin is verified serves users a mix of old and broken.
2. **Purge after deploy, never before.** An early purge refills the cache from the old origin during a slow rollout; the window between purge and origin update is exactly when stale content gets re-cached.
3. **Make the purge step idempotent and retryable.** Purge APIs occasionally 5xx under load; retry with backoff and treat an unverified purge as a failed deploy step (see `deployment-verification-smoke-tests.md` for the same principle applied to apps).
4. **Propagate timing assumptions, don't assume instant.** Cloudflare advertises global purge propagation in ~150 ms, but multi-CDN setups and any intermediate proxies layer their own delays; verification should poll the edge (with cache-busting query params on a canary URL) rather than trust the API's 200 response as "live everywhere."
5. **Gate the next deploy on purge completion.** Two deploys in quick succession with interleaved purges produce cache states nobody can reason about; serialize release → purge → verify per zone.

## Failure Modes and Verification

1. **Symptom: users see the old UI after deploy.** Verify each layer independently — browser cache, service worker, CDN edge, origin — with a version echo endpoint (`/__version` returning the build SHA) so the stale layer is identified in one curl instead of guessed at.
2. **Symptom: mixed-version page.** Old HTML referencing deleted hashed assets (404s) means HTML TTL outlived asset retention; keep at least the previous release's assets deployed (deploy N-1 retention) so cached HTML never references a 404.
3. **Symptom: origin melt-down after purge.** That was a purge-everything event hitting a cold cache; switch to URL-scoped purges and `stale-while-revalidate`, and confirm origin autoscaling can actually absorb a full cold-refill before ever using the big red button.
4. **Log every purge.** Who/what triggered it, scope, API response — because "someone purged the zone mid-incident" is a classic confounder when debugging traffic anomalies afterward.
