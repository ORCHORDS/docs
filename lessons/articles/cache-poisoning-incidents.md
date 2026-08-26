# cache-poisoning-incidents

**Issue:** A cache or CDN serves the wrong response for the right URL — an attacker-stored payload, another tenant's content, or an error page cached as if it were the real thing — and because the cache is doing exactly its job (fast, high hit rate, "healthy" on every dashboard), nobody notices until users report it or a security researcher does. Cache poisoning incidents are the unholy combination of a security breach and an availability incident: one poisoned cache key can affect millions of requests, the blast radius is your entire cached surface, and the content usually looks legitimate to monitoring because it originates from your own infrastructure. Researcher work in the vein of PortSwigger's James Kettle and the 2022 "Cache Poisoning at Scale" effort (70+ vulnerabilities found across bug bounty programs) shows this is not an exotic bug class but a systemic property of layered caching that most teams have shipped at least once.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How a cache gets poisoned

1. **Unkeyed inputs reach the origin.** A cache decides what to store and serve using a cache key (typically method, path, and a few headers), but the origin often reacts to far more inputs — X-Forwarded-Host, X-Original-URL, fat GET parameters, Accept-Language variants. When an input affects the response but is not part of the key, the first requester's input gets baked into the response served to everyone.
2. **Error responses get cached.** Poisoning an error path is often easier than poisoning content: request a path with a crafted header, get a 500 whose body reflects your payload, and if the CDN caches error status codes, every subsequent user receives your "error" page. Disabling caching for error responses is one of the highest-value, lowest-effort mitigations identified in the Cache Poisoning at Scale research.
3. **Cache-key normalization mismatches.** The cache canonicalizes a URL one way and the origin another (trailing dots, encoded slashes, case in hostnames, duplicate parameters). An attacker requests the variant that maps to attacker-controlled storage while normal users request the variant that maps to the same cache entry.
4. **Intermediate layers add their own keys.** A second proxy, an edge worker, or a service-mesh sidecar may cache on subtly different keys than the front CDN. Multi-layer stacks produce "unexploitable-looking" discrepancies that are exploitable in composition — the core finding of modern cache-deception and poisoning research.

## Why detection lags

1. **The cache reports health.** Hit ratio goes up when poisoned — poisoned entries are extremely popular. Latency is great. Uptime checks pass because the status code is often 200.
2. **The payload looks like it came from you.** Logs show the origin served it (once), the CDN served it (a million times). WAFs see nothing anomalous because the attack was a single weird request, not traffic volume.
3. **Victims are the detectors.** The signal is usually users reporting wrong content, a customer seeing another customer's data, or a researcher's email — hours or days after the poisoned entry landed. Cache TTLs of hours to days extend exposure from one request to an entire audience.
4. **No baseline for content correctness.** Almost nobody diffs cached responses against origin responses in production. Without a canary that periodically fetches through the cache and compares to a direct origin fetch, poisoning is structurally invisible.

## Hardening that works

1. **Normalize and canonicalize before keying.** Reject or canonicalize ambiguous URL forms at the edge (encoding, case, dots, duplicate params) so the cache key and the origin agree on identity. Cloudflare's own cache-security guidance centers on this discipline.
2. **Never cache error codes or reflected headers.** Treat non-2xx responses as uncacheable by default, and strip or ignore hop-by-hop and client-supplied routing headers at the boundary so they cannot reach origin logic uninvited.
3. **Fuzz your own cache keys in CI.** The same property-based technique researchers use — vary unkeyed inputs, diff responses — can run against staging continuously. A nightly job that requests the same URL with 50 header mutations and flags response divergence catches regressions before researchers do.
4. **Cap TTLs on anything sensitive.** Authenticated or per-user content should not be cacheable at all; where caching is legitimate, shorter TTLs bound the lifetime of any poisoning to minutes instead of days.
5. **Purge with the incident, not after it.** Confirm the incident response runbook includes the exact cache-purge command for every cache layer, scoped correctly — and remember a purge is only treatment, not cure, if the vulnerable input path remains.

## Incident lessons

1. **Scope by key, not by URL.** During response, enumerate which cache keys could be affected (including variants you did not directly observe) and purge all of them; poisoned entries frequently exist on multiple edge PoPs independently.
2. **Assume a second payload.** If one unkeyed input was exploitable, audit the whole surface before declaring recovery — follow-up reports after a "fixed" poisoning disclosure are routine in the published case studies.
3. **Log the poisoning request.** Preserve edge logs long enough to identify the original request that seeded the entry; without it you cannot distinguish a targeted attack from a random scanner, which changes disclosure obligations.
