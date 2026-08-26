# R2 Eventual Consistency — Cache Invalidation Incident (Postmortem)

- Date: 2026-08-22
- Author: example.com
- Status: production

## Summary

After uploading updated static assets to R2, users continued to receive stale file versions
for up to 90 minutes because CDN edge caches were not purged and R2 itself did not surface the
new objects consistently at all edge PoPs. The incident taught us that layering Cloudflare's
CDN cache on top of R2 without an explicit purge-on-write strategy creates an invisible
freshness contract that will eventually break in production.

## Timeline / What Happened

- **09:14 UTC** — Engineering deploys a new release; updated JS bundle and CSS file uploaded
  to R2 bucket `orchords-assets-prod` via `wrangler r2 object put`.
- **09:15 UTC** — Smoke tests pass in the deployer's browser (warm cache served the old files
  but the deployer had a hard-refreshed tab, bypassing browser cache; Worker cache was not
  checked).
- **09:22 UTC** — First Slack message from QA: "seeing an old build in staging-prod mirror."
- **09:31 UTC** — User reports on Discord: broken UI after the deploy; assets load but look
  wrong. Support ticket opened.
- **09:44 UTC** — On-call engineer checks R2 directly via signed URL — correct new file is
  there. Suspects CDN layer.
- **09:51 UTC** — Cache-Control headers inspected on production responses:
  `Cache-Control: public, max-age=86400` — a 24-hour TTL set months earlier and never
  revisited. No `s-maxage` or `stale-while-revalidate` tuning.
- **10:02 UTC** — On-call manually triggers a Cloudflare Cache Purge via Dashboard for the
  affected paths.
- **10:07 UTC** — User reports resolve; all edge PoPs serving fresh objects.
- **10:09 UTC** — RCA investigation begins.

## Root Cause

Two separate but compounding problems existed simultaneously.

**Problem 1 — Stale CDN edge caches.** The Workers route serving `/assets/*` was configured
to cache R2 responses at the CDN layer with a 24-hour TTL. When new objects were uploaded,
the CDN had no reason to re-fetch them. No cache purge was issued as part of the deploy
pipeline.

```typescript
// BEFORE — Worker serving R2 assets, cache headers not updated on upload
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.replace(/^\/assets\//, "");

    const object = await env.ASSETS_BUCKET.get(key);
    if (!object) return new Response("Not Found", { status: 404 });

    // BUG: 24-hour TTL, no purge mechanism, no content hash in URL
    return new Response(object.body, {
      headers: {
        "Content-Type": object.httpMetadata?.contentType ?? "application/octet-stream",
        "Cache-Control": "public, max-age=86400",
      },
    });
  },
};
```

**Problem 2 — R2 eventual consistency across PoPs.** R2 is an eventually consistent object
store. After a `PUT`, reads from edge PoPs that are geographically distant from the write
origin may return the previous object version for a short window. With a CDN cache TTL of
24 hours masking this, the eventual consistency window became invisible — and the two effects
compounded each other, extending the stale-serving window far beyond what either problem
alone would have caused.

## Fix Applied

Three changes were deployed together:

**1. Content-addressed URLs** — Asset filenames include a content hash at build time
(`main.a1b2c3d4.js`), making each release serve from a fresh cache key by construction.
No purge needed for immutable assets; only `index.html` (which references them) needs
short-lived caching.

**2. Cache-Control headers tuned per asset type.**

```typescript
// AFTER — content-addressed assets are immutable; index.html is short-lived
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.replace(/^\/assets\//, "");

    const object = await env.ASSETS_BUCKET.get(key);
    if (!object) return new Response("Not Found", { status: 404 });

    // Heuristic: paths with a content hash (8+ hex chars before extension) are immutable
    const isImmutable = /\.[a-f0-9]{8,}\.(js|css|woff2|png|svg)$/.test(key);

    const cacheControl = isImmutable
      ? "public, max-age=31536000, immutable"   // 1 year — safe because URL changes on update
      : "public, max-age=60, stale-while-revalidate=30"; // 1 min for index.html / manifests

    return new Response(object.body, {
      headers: {
        "Content-Type": object.httpMetadata?.contentType ?? "application/octet-stream",
        "Cache-Control": cacheControl,
        "ETag": object.etag ?? "",
      },
    });
  },
};
```

**3. Purge-on-write helper** called from the deploy script for the small set of
non-content-addressed paths (`index.html`, `manifest.json`).

```typescript
// deploy/purge.ts — called after wrangler r2 object put for mutable paths
async function purgeCloudflareCache(paths: string[]): Promise<void> {
  const zoneId = process.env.CF_ZONE_ID!;
  const apiToken = process.env.CF_API_TOKEN!;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ files: paths.map(p => `https://example.com${p}`) }),
    }
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Cache purge failed: ${res.status} ${body}`);
  }
}
```

## Prevention Checklist

- [ ] All static assets produced by the build pipeline include a content hash in the filename.
- [ ] `index.html` and other mutable entry points use `max-age <= 60` with
      `stale-while-revalidate`.
- [ ] Deploy pipeline calls `purgeCloudflareCache` for every non-hashed path before marking
      the deploy complete.
- [ ] Smoke tests verify the `ETag` or `Last-Modified` header reflects the new deploy, not a
      cached value.
- [ ] R2 bucket CORS and cache settings are reviewed in every deploy checklist.
- [ ] On-call runbook includes a "force purge assets" step as an immediate mitigation.

## Lesson Learned

R2's eventual consistency model is correct and fast in practice, but it becomes dangerous when
combined with a long CDN TTL because the two staleness windows compound. Designing assets to
be content-addressed eliminates the need to reason about either window for the common case.
Any mutable object that is served through a CDN must have an explicit, automated purge step
wired into every publish operation — not a manual step that happens only when someone notices
a problem.

## Anti-patterns This Exposed

- Setting a long `Cache-Control` TTL on mutable R2 objects without a purge strategy.
- Assuming a successful `wrangler r2 object put` immediately means all edge PoPs serve the new
  object — R2 replication is eventually consistent.
- Running smoke tests from the deployer's own browser, which may already have a warm CDN edge
  connection to the nearest PoP (where the write landed first).
- No automated assertion in the deploy pipeline that the live CDN response matches the newly
  uploaded object checksum.

## Related

- `cache-invalidation-is-harder-than-caching.md`
- `kv-read-costs-capacity-planning-retrospective.md`
- `cloudflare-storage-primitive-selection.md`
- `logpush-r2-backpressure-dropped-observability.md`

## Sources

- Cloudflare R2 docs — Consistency model
- Cloudflare Cache Purge API — `POST /zones/:id/purge_cache`
- MDN — Cache-Control: immutable
