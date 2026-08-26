# r2-custom-domains-cache-rules

**Issue:** Serve intentionally public R2 objects efficiently without accidentally exposing protected objects through an alternate public bucket URL.
**Date:** 2026-08-20
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** verified against Cloudflare documentation updated 2026-06-16

## Public access paths are independent

R2 buckets are private by default. Public access must be enabled explicitly, and Cloudflare provides two independent public routes:

1. **Public Development URL (`pub-<hash>.r2.dev`)** — intended for testing, rate-limited, and not suitable for production. It does not provide the custom-domain cache, WAF, Access, or Bot Management controls.
2. **R2 custom domain** — the production public-delivery path. It puts the hostname on Cloudflare's network so Cache Rules, WAF, Access, redirects, analytics, and related zone features can apply.

Enabling or disabling one route does not automatically change the other. Removing a custom domain does not disable `r2.dev`; disabling `r2.dev` does not disconnect a custom domain.

## The authorization-boundary trap

A Worker may correctly enforce login, ownership, takedown, or entitlement checks and still fail to protect an object if the same bytes remain reachable through a raw public R2 URL.

Example failure:

```text
GET https://api.example.com/films/abc/master.m3u8
→ Worker checks status and returns 404 after takedown

GET https://pub-<hash>.r2.dev/films/abc/master.m3u8
→ 200 because the bucket's Public Development URL still exposes the object
```

The Worker is not broken; the storage topology bypasses it. Application authorization governs only the route that executes the application code.

### Rules that prevent the bypass

1. **Do not store protected and public objects in the same publicly exposed bucket unless every protected object is separately encrypted and unusable without a protected key.** A hidden prefix is not an access-control boundary.
2. **Use a private R2 bucket bound to a Worker for application-authorized assets.** The Worker can read the private bucket through its binding while users cannot address the bucket directly.
3. **Use S3 presigned URLs for narrow, time-limited direct access** when the application can safely grant one object operation. Presigned URLs use the R2 S3 API hostname and cannot be used on a custom domain.
4. **When protecting an R2 custom domain with Cloudflare Access or WAF, disable the Public Development URL.** Cloudflare explicitly warns that leaving `r2.dev` enabled keeps the bucket public around those controls.
5. **Audit every connected custom domain and public development URL.** Security depends on the least-protected active route, not the best-protected one.

## Migration: future writes are not enough

Moving new protected uploads to a private bucket does not secure copies that already exist in a public bucket or cache.

Use this migration order:

1. Create or identify the private bucket. Do not enable its Public Development URL or attach an unprotected custom domain.
2. Bind it to the serving Worker and move all protected reads and writes to that binding.
3. Copy existing protected objects into the private bucket.
4. Verify the application route still serves authorized users and still denies unauthorized or takedown states.
5. Delete the old copies from every public bucket.
6. Purge any custom-domain cache entries that may still contain the public copies.
7. Re-run negative tests against every old raw public URL.

A strong verification uses both a negative and a positive control:

```text
protected old key at raw public hostname → 404
known public control key at same hostname → 200
```

The positive control proves the public endpoint is actually reachable, so the protected-key `404` is not a false pass caused by DNS, network, or a disabled hostname.

## Custom-domain cache behavior

1. **Default eligibility is content/type dependent.** Cloudflare caches only default-cache-eligible responses unless a Cache Rule changes eligibility. JSON, extensionless keys, and some manifests commonly need an explicit rule.
2. **Cache Rules can make a matching response eligible and set Edge TTL.** Scope the rule to the exact hostname and path class; do not apply an immutable media TTL to authenticated or mutable API responses.
3. **Respect origin headers when asset classes differ.** Per-object `Cache-Control` is useful when immutable segments and mutable playlists share a hostname. A fixed Edge TTL is simpler for content-addressed immutable assets.
4. **Verify, do not assume.** `CF-Cache-Status: MISS` followed by `HIT` demonstrates edge reuse. `DYNAMIC` or `BYPASS` means the request was not cached under the tested conditions.
5. **Cache changes the delivery copy, not the authorization model.** Never put user-specific or takedown-sensitive responses into a shared public cache unless the cache key and bypass rules are deliberately designed for them.
6. **Purge or version keys on change.** Content-hashed object keys remove most purge requirements. Mutable manifests need explicit TTL and purge behavior.

## Access-control choices

### Intentionally public assets

Use a custom domain plus narrowly scoped Cache Rules. Public Development URLs are acceptable for temporary testing only.

### Team-only bucket

Create the Cloudflare Access application before connecting the custom domain, then verify the policy and disable `r2.dev`. Cloudflare warns that connecting the domain first makes it public by default until Access is active.

### Per-user application authorization

Keep the bucket private and serve through a Worker binding. Perform authorization before `get()`, and ensure no secondary public hostname exposes the bucket.

### Direct temporary access

Generate a short-lived presigned S3 URL for one object and operation. Treat it as a bearer token and avoid logs, analytics, referrers, or support screenshots that expose its query string.

## Security and correctness checklist

- [ ] Inventory Public Development URLs and all R2 custom domains.
- [ ] Classify each bucket as public, team-restricted, or application-authorized.
- [ ] Keep protected objects out of public buckets; prefixes are organizational, not security boundaries.
- [ ] Disable `r2.dev` whenever custom-domain WAF or Access is the intended gate.
- [ ] Confirm presigned URLs use the S3 API hostname, not a custom domain.
- [ ] Scope Cache Rules by hostname and path.
- [ ] Purge cached objects after access-policy or CORS changes when required.
- [ ] Test the application route and every alternate raw-storage route.
- [ ] Migrate and delete old public copies, not only future writes.
- [ ] Apply lifecycle rules to staging and orphaned-upload prefixes.

## References

1. Cloudflare R2 — Public buckets: https://developers.cloudflare.com/r2/buckets/public-buckets/
2. Cloudflare Cache — Enable cache in an R2 bucket: https://developers.cloudflare.com/cache/interaction-cloudflare-products/r2/
3. Cloudflare R2 — Protect an R2 bucket with Cloudflare Access: https://developers.cloudflare.com/r2/tutorials/cloudflare-access/
4. Cloudflare R2 — Presigned URLs: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
5. Cloudflare R2 — Workers API: https://developers.cloudflare.com/r2/get-started/workers-api/
6. Cloudflare R2 — Limits for managed public buckets: https://developers.cloudflare.com/r2/platform/limits/

## Related

- `r2-cors-config.md`
- `r2-signed-urls.md`
- `r2-streaming-hls-pipeline.md`
- `r2-best-practices.md`
