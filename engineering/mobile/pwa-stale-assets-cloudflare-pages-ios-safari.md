# Stale Assets After Cloudflare Pages Deploys on Mobile / iOS PWA

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Every example project (example.com) deploy is followed by support reports
— broken feeds, blank screens, spinners that never resolve — and
nearly all come from mobile; desktop users hit the same deploy
but recover with one reload. Error tracking shows `ChunkLoadError:
Loading chunk N failed` (404s on `/_next/static/chunks/*.js`)
spiking for 24-72 hours after each deploy, overwhelmingly from
iOS Safari and standalone (home-screen PWA) user agents. Some
iOS PWA users stay "stuck on an old version" for days; only
reinstalling the home-screen icon fixes them.

## Context

example project is a Next.js static export on Cloudflare Pages with a
Worker API; it is installable as a PWA and much of the 21+
audience uses the home-screen install. The session-cookie
age-gate is enforced by the Worker API and must keep working
when users reload on stale HTML. The core problem is a
version-skew triangle: Cloudflare's edge cache, the browser HTTP
cache, and the service worker cache each hold their own copy of
HTML and chunks, and after a deploy they disagree. Desktop
resolves the skew with one reload; iOS Safari and standalone
PWAs hold the old HTML, service worker, and precache for days.

## How Cloudflare Pages serves static assets

```
Layer            Default behavior
──────────────────────────────────────────────────────────────
Browser cache    Cache-Control: public, max-age=0,
                 must-revalidate on cacheable 200s.
                 ETag sent on every 200; browser revalidates
                 with If-None-Match → 304 Not Modified.
Edge cache       Static assets cached per data center
                 (tiered cache, ~1 week TTL, evictable).
Deployments      Atomic. A new deploy replaces the asset
                 manifest; old hashed chunk URLs 404 at
                 origin (old deploys live only on their
                 unique preview URLs).
Stale window     Previous-deploy assets can persist at edge
                 up to a week; "Purge Everything" clears it.

Pages does NOT mark /_next/static/* immutable by itself.
Add it via a _headers file — the hashes make it safe:

  /_next/static/*
    Cache-Control: public, max-age=31536000, immutable
  /sw.js
    Cache-Control: no-cache
  /*.html
    Cache-Control: public, max-age=0, must-revalidate
```

## Why desktop recovers but mobile stays stale

```
Desktop:  reload → If-None-Match → new HTML → new chunks.
          Done. Worst case, hard refresh exists.

Mobile (iOS Safari):
  → No hard-refresh gesture. Pull-to-refresh is a normal
    navigation and may be answered entirely by the service
    worker / memory cache without touching the network.
  → Safari aggressively serves from memory/disk cache, at
    times even preferring it over the service worker.
  → Tabs are frozen, not closed — a waiting service worker
    never reaches zero clients, so it never activates.

Mobile (home-screen PWA, standalone):
  → Isolated storage: clearing Safari's cache does NOT fix
    the installed PWA; its cache + SW live in a separate
    container. Only recovery: delete and reinstall the icon.
  → No URL bar, reload button, or devtools.
  → iOS keeps the standalone process (old SW + old cached
    HTML) alive across days of resume/suspend cycles; the
    navigation that triggers an SW update check may not
    happen for a very long time.
```

## Service worker update lifecycle (and the broken-update loop)

```
1. Browser re-fetches sw.js on navigation to an in-scope
   page (also on push/sync events, at most every 24h).
2. Byte-diff → new worker installs → enters WAITING state.
3. Waiting worker activates only when the existing worker
   controls zero clients. An iOS PWA that is resumed, never
   killed, keeps the old worker controlling forever.
4. skipWaiting() + clients.claim() force immediate takeover
   — old-HTML pages then run under the new worker.

The broken-update-loop trap:
  If sw.js is served with a long max-age, step 1 fetches the
  OLD sw.js from HTTP cache → no byte diff → no update EVER,
  and the old worker keeps serving old precached HTML that
  references deleted chunks. Browsers default updateViaCache:
  'imports' (the main script bypasses HTTP cache), but
  importScripts'd files and any edge rule that long-caches
  /sw.js reintroduce the loop. Serve sw.js no-cache, always.
```

```javascript
// sw.js — take over promptly, drop old caches
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil((async () => {
  for (const k of await caches.keys())
    if (k !== 'example project-v' + BUILD_ID) await caches.delete(k);
  await self.clients.claim();
})()));
```

## The classic failure: ChunkLoadError after deploy

```
t0  Deploy 42 live. /_next/static/chunks/feed.abc123.js
t1  Deploy 43 ships. feed.abc123.js → feed.def456.js;
    abc123 now 404s at origin.
t2  iOS PWA resumes with old HTML (from SW precache or
    Safari cache) referencing abc123.
t3  User taps the feed → dynamic import of abc123 → 404 →
    ChunkLoadError → blank screen / dead feed.
t4  Desktop users who hit the same skew reload and recover;
    the PWA user reopens the app, gets the same stale HTML
    from the same SW, and fails identically for days.
```

The trigger is universal; the recovery path (a revalidating
reload) exists only on desktop — hence the mobile skew.

## Mitigations

```
Rule                          Why
──────────────────────────────────────────────────────────────
Never long-cache HTML or      They are the version pointers.
sw.js (no-cache /             Stale pointer = stale app.
max-age=0, must-revalidate)
Cache-first ONLY for hashed   Content-addressed URLs are the
/_next/static/* assets        only safe immutable targets.
Network-first (fallback       Age-gate check hits the Worker
cache) for HTML in the SW     on every navigation, so the
                              gate survives stale-HTML loads.
Version-check endpoint +      Poll /api/version (Worker) on
in-app update prompt          resume; on BUILD_ID mismatch
                              show "Update available" →
                              reg.update(), reload when the
                              waiting worker activates.
Graceful chunk-error reload   Deleted-chunk 404s become one
handler                       automatic reload, not a blank
                              screen (guard against loops).
Keep old chunks reachable     Edge retention (~1 week) is
                              luck, not contract — copy the
                              prior build's _next/static into
                              the new deploy if skew is common.
```

```javascript
// One-shot recovery from deleted-chunk 404s (app shell)
window.addEventListener('error', (e) => {
  const key = 'chunk-reload-' + BUILD_ID;
  if (/Loading chunk .* failed|ChunkLoadError/.test(e.message || '')
      && !sessionStorage.getItem(key)) {
    sessionStorage.setItem(key, '1');       // no reload loop
    location.reload();
  }
});
```

## Cloudflare cache purge on deploy (custom domains)

example.com is a custom-domain zone, so any Cache Rules added
there can pin old HTML at the edge past a deploy — Cloudflare
recommends not layering custom caching on Pages custom domains
for exactly this reason. If you do have rules, purge on deploy:

```bash
# CI step after `wrangler pages deploy`
curl -sX POST \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/purge_cache" \
  -H "Authorization: Bearer $CF_PURGE_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"purge_everything":true}'
# Prefer targeted purge (URL/prefix/tag); purge-everything
# is rate-limited per plan (5/min on Free).
```

Instant Purge propagates near-immediately, but it only fixes the
edge — it does nothing for HTML already inside an iOS PWA's
service worker cache. Purge AND the SW rules are both required.

## Anti-patterns

- **`Cache-Control: max-age=31536000` on `/*` "for speed"** —
  long-caching HTML and sw.js is the root cause of the
  broken-update loop. Only hashed assets earn `immutable`.
- **Cache-first HTML in the service worker** — every navigation
  serves the old app shell; users never see a deploy until the
  SW updates, which on iOS PWA may be days.
- **Treating "just refresh" as the support answer** — iOS Safari
  has no hard refresh and standalone PWAs have no refresh at
  all; if recovery requires a gesture, mobile users cannot do it.
- **skipWaiting without a reload strategy** — the new worker
  takes over pages built from old HTML; pair skipWaiting and
  clients.claim with a single controllerchange-driven reload.
- **Baking the age-gate result into cached HTML** — the gate
  must be a runtime check against the Worker session cookie so
  a stale-HTML reload still enforces it.

## Gotchas

- **Clearing Safari's cache does not fix the installed PWA** —
  home-screen apps use isolated storage. Only Settings → Safari
  → Advanced → Website Data removal or reinstalling the icon
  clears it. Design so users never need this.
- **updateViaCache protects only the top-level sw.js** — the
  default `'imports'` still HTTP-caches importScripts'd files;
  a stale imported file means a stale worker.
- **Old deployment assets at the Pages edge are best-effort** —
  they can persist "up to a week" per data center but may be
  evicted anytime; never rely on them to cover version skew.
- **iOS suspends in-flight dynamic imports** — a backgrounded
  tab can surface a spurious ChunkLoadError on resume even
  without version skew; the one-shot reload handler covers both.
- **ETag/304 revalidation needs the network** — an SW or memory
  cache that answers first bypasses Pages' safe defaults entirely.

## Verification

- `_headers` sets immutable only on `/_next/static/*`; HTML and
  `sw.js` are `no-cache`/`must-revalidate` — confirm via
  `curl -sI https://example.com/sw.js | grep -i cache-control`.
- iOS home-screen install on a preview branch: deploy again,
  resume the app — update prompt appears and one reload lands
  on the new BUILD_ID, no blank screen.
- Force a deleted-chunk 404: exactly one automatic reload.
- Age-gate: with stale HTML forced from the SW cache, a reload
  without the session cookie still redirects to the gate.
- Post-deploy CI purge succeeds; mobile ChunkLoadError rate
  returns to baseline within an hour, not days.

## Related

- `documentation/categories/mobile/pwa-service-worker-patterns.md`
- `documentation/categories/mobile/pwa-offline-caching-strategies.md`
- `documentation/categories/cloudflare/pages-headers-config.md`
- `documentation/categories/cloudflare/pages-deployment-patterns.md`

## Source URLs (verified 2026-08-17)

- Serving Pages (Cloudflare Pages docs) — https://developers.cloudflare.com/pages/configuration/serving-pages/
- The service worker lifecycle — https://web.dev/articles/service-worker-lifecycle
- ServiceWorkerGlobalScope.skipWaiting() (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerGlobalScope/skipWaiting
- Purge cache (Cloudflare Cache docs) — https://developers.cloudflare.com/cache/how-to/purge-cache/
