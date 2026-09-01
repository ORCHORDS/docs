# Cache API Stale-While-Revalidate Governance

The Workers Cache API lets a Worker read and write Cloudflare's cache programmatically, and its staleness controls decide what a user sees while a fresh copy is being fetched. Stale-while-revalidate semantics — serve the stale entry immediately, refresh it in the background — feel like a free latency win, but they are a set of promises about how old a response may be, who refreshes it, and what happens when revalidation fails. Governance means those promises are written down, encoded in the cache-control directives the Worker sets, and verified at the edge cases where SWR quietly misbehaves: the moment of expiry, the first request after a deploy, and the failed revalidation that serves increasingly ancient content.

## Scope

Covers the Workers Cache API (`caches.default`) with a focus on stale-while-revalidate behavior: directive configuration, edge cases around expiry and revalidation failure, and governance of which resources may be served stale. Applies to Workers that cache their own responses or proxy-and-cache upstream responses. Excludes Cloudflare CDN default caching governed by zone-level cache rules, Cache Reserve (covered separately), and browser-side caching.

## Workflow or implementation guidance

1. Enumerate what the Worker caches and classify each resource class by staleness tolerance: real-time (never stale), near-real-time (seconds), user-visible (minutes), and immutable-ish (hours or forever with content-hash keys). SWR is only appropriate from near-real-time onward.
2. For each class, decide three numbers together: `max-age` (how long an entry is fresh), `stale-while-revalidate` (how long past expiry a stale entry may still be served while refreshing), and `stale-if-error` (how long a stale entry may serve when the origin fails). Setting SWR without stale-if-error leaves the most valuable case ungoverned.
3. Encode the directives where the Worker writes the cached response — the `Cache-Control` header set at `cache.put()` time governs later behavior at `cache.match()`, so the numbers decided in step 2 must appear in the stored response, not just in the outgoing one.
4. Implement the read path explicitly: `cache.match()` with the cache key, serve on hit regardless of freshness only within the SWR budget, fetch upstream on miss, and kick off the background refresh when serving stale. Do not rely on implicit behavior where an explicit branch is testable.
5. Handle key discipline: cache keys must include every input that changes the response (variant, version, normalization). SWR amplifies key mistakes because a wrong-keyed stale entry keeps being served and refreshed.
6. Test the three edge cases deliberately: the first request after `max-age` expires (should serve stale and refresh), a request during upstream failure within the stale-if-error budget (should serve stale, not error), and a request after both budgets lapse (must not serve the ancient entry).
7. On deploy of response-shape changes, purge or version cache keys so old-format stale entries cannot be re-served during their SWR window.
8. Record the per-class directive table as the governance baseline, and review it whenever a resource class's freshness requirement changes.

## Controls

- Staleness budget table: every cached resource class has recorded `max-age`, `stale-while-revalidate`, and `stale-if-error` values with rationale.
- No-SWR-by-default rule: enabling stale serving on a class requires an explicit entry in the table; unlisted classes are strict.
- stale-if-error requirement: classes with SWR must also declare a stale-if-error position, even if that position is zero.
- Key composition review: cache key construction is reviewed for variant coverage whenever a new response input is added.
- Deploy-time invalidation step: changes to response shape include a purge or key-version bump before gradual rollout.
- Edge-case test suite: the three SWR edge cases run as automated tests against the Worker in a staging environment.

## Validation evidence

- The staleness budget table with per-class directives and review dates.
- Response headers captured from `cache.put()`-stored entries showing the directives actually encoded in cache.
- Edge-case test transcripts: post-expiry request serving stale with refresh, upstream-failure request serving within stale-if-error, and post-budget request not serving ancient content.
- Key composition examples per class demonstrating variant coverage.
- Deploy record showing purge or key-version bump accompanying a response-shape change.
- Header inspection of live responses confirming the outgoing `Cache-Control` matches the class table.

## Failure modes and correction

- Stale entries served far longer than intended: the SWR or stale-if-error budget was never bounded, or the clock semantics differ from assumption; set explicit finite values and re-verify with the edge-case tests.
- Users see mixed old and new content after a deploy: stale entries from the old version remained in their SWR window; version cache keys or purge on deploy, which is what the invalidation step control requires.
- Upstream outage serves errors despite SWR: stale-if-error was absent, so the stale entry was not eligible during failure; add it with a deliberate budget.
- Wrong-variant responses served stale repeatedly: a response input (encoding, locale, experiment) was not in the key; extend key composition and purge existing entries.
- Revalidation stampede on a hot key at expiry: concurrent requests each trigger refresh; coalesce refreshes in the Worker (single-flight within the isolate) or accept the cost knowingly.
- Directives set on the outgoing response but not the stored one: behavior diverges from the table; encode directives at `put()` time, verified by reading stored headers.

## Limitations

- Cache API behavior is best-effort; the edge cache may evict entries at any time, so SWR budgets describe maximums, not guarantees.
- Clock interpretation and directive support specifics follow the Workers runtime documentation and may differ from browser semantics.
- Background revalidation in Workers is bounded by the request lifecycle; a closed connection can cut refresh short, leaving the next request to complete it.
- SWR budgets cannot exceed what the stored directives permit; tightening requires rewriting entries, not just changing Worker code.
- Cross-colo cache behavior means observed staleness can vary by location even with identical directives.

## Canonical sources

- Cloudflare Workers docs, "Cache" (Workers Cache API): https://developers.cloudflare.com/workers/runtime-apis/cache/
- Cloudflare Cache docs, "Concepts" (TTL, revalidation, cache control): https://developers.cloudflare.com/cache/about/
