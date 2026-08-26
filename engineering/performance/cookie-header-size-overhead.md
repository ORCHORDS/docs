# cookie-header-size-overhead

**Issue:** Every cookie matching a request's domain and path is attached by the browser to that request — HTML documents, API calls, images, scripts, pixels, everything. Unlike response compression, which shrinks bytes on the way down, request cookies ride the upload path, which is the narrowest, most congested link on mobile and home networks. A 4 KB analytics plus auth plus consent cookie stack multiplied across 80 requests per page load can add hundreds of kilobytes of pure uplink overhead, inflating request-start time and TTFB on exactly the segments (low-end Android, weak signal) where Core Web Vitals already struggle. Worse, cookies grow silently: every tool a team adopts appends its own, until servers start rejecting requests with 431 or truncating headers. Cookie weight is a slow, invisible performance and correctness debt that deserves the same budgeting discipline as bundle size.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why cookie bytes are expensive

1. **Upload bandwidth is the scarcest resource.** Downstream capacity on LTE/5G often exceeds upstream by an order of magnitude. Request headers cannot be compressed in HTTP/1.1 at all, and in practice most of the win (HPACK/QPACK header compression) applies to response-side headers the client repeats — cookies set by the server still cost on requests where QPACK indexing helps less than assumed.

2. **Overhead multiplies per request, not per page.** If six cookies total 3 KB and a page view issues 90 requests to the same registrable domain, the browser transmits roughly 270 KB of cookie bytes before the page is fully loaded — comparable to a large hero image, but with zero rendering value.

3. **Cookies delay every request equally.** Because the header must be serialized before the request starts, large cookies add latency to the HTML navigation itself, directly inflating TTFB and therefore LCP — the effect is visible in lab tests as uniformly slow request-start phases across all same-site resources.

4. **Size creep has hard failure limits.** Browsers cap individual cookies around 4 KB and implementations reject oversized or header-heavy requests (HTTP 431). Marketing tags and consent platforms append cookies over quarters, so the system fails long after the decision that caused it.

## Auditing cookie weight

1. **Measure per-request header bytes.** In Chrome DevTools Network panel, add the cookie/size-on-request columns or export HAR and sum request cookie bytes per page load. The number to record is total cookie bytes uploaded for a typical navigation, not the size of any single cookie.

2. **Inventory the setters.** For each cookie, document owner (first-party app, analytics, consent manager, ad tech), purpose, scope (Domain/Path), and expiry. Any cookie without an owner is removal candidate number one — orphaned cookies from abandoned experiments are the most common dead weight.

3. **Check per-domain fan-out.** Cookies scoped to the registrable domain (Domain=example.com) transmit to every subdomain including static assets. List which subdomains receive which cookies; that matrix drives the domain-topology fix.

4. **Re-audit on a schedule.** Tag managers can add cookies without code review. Fold a cookie-weight check into quarterly performance reviews, with a budget (for example, under 1.5 KB total for the document origin) that alerts like a bundle-size budget.

## Reduction strategies

1. **Store state server-side behind an opaque ID.** The scalable pattern is a small session-identifier cookie backed by server-side storage (session store, KV, Redis). A 40-80 byte ID replaces multi-KB preference or profile blobs; the server joins state on its own fast storage.

2. **Scope Domain and Path tightly.** Omit the Domain attribute so the cookie is host-only and never leaks to siblings or subdomains. Set the narrowest Path that the consuming endpoints share. Scoping is the cheapest fix and often halves transmitted bytes by excluding static subdomains.

3. **Remove analytics and consent cookies where alternatives exist.** Modern measurement can run cookieless (server-side event forwarding, aggregate APIs) or with a single short-lived ID. Consent platforms frequently persist multi-KB preference JSON; hash it to a version key and store the detail server-side.

4. **Expire aggressively and delete on logout.** Short Max-Age forces re-issue instead of indefinite accumulation, and a full logout flow must clear the family of cookies, not just the auth token. Zombie auth cookies that reattach to every asset request are a classic audit finding.

5. **Use partitioned cookies where cross-site context is unavoidable.** The CHIPS Partitioned attribute lets a third-party service keep its cookie without being attached across sites, which both reduces surprise transmissions and aligns with the browser privacy direction of 2025-2026.

## Domain topology tactics

1. **Serve static assets from a cookie-free origin.** Historically this meant a separate cookieless domain for images/scripts. With HTTP/2+ same-origin multiplexing, the trade-off changed — splitting domains costs connection setup and DNS — so the modern version is a subdomain scoped so cookies never reach it (host-only cookies plus assets.example.com), keeping most multiplexing benefits.

2. **Keep the document origin's cookie set minimal.** The navigation request must carry auth, so move everything optional (features, experiments, theme) out of cookies entirely — into URL params for first paint or fetched after load. Only genuinely server-required-on-first-byte state belongs in a cookie.

3. **Isolate API and app domains deliberately.** If APIs live on api.example.com, host-only cookies mean the app origin's cookies do not ride API calls, and vice versa. Design the split around which cookies each surface truly needs rather than defaulting to Domain-wide sharing.

4. **CDN cacheability interacts with cookies.** CDN edge caches often bypass or fragment on requests carrying cookies, so cookie-laden asset requests defeat edge caching even when URLs match. Keeping cookies off asset hostnames preserves hit ratios, which is a bigger latency lever than the bytes themselves.

## Failure modes and guardrails

1. **HTTP 431 and truncated headers.** Oversized cookie stacks manifest as failed navigations or broken API calls, sometimes only for heavy users (long-lived consent and experiment cookies). A 431 alert in server logs is the late-stage symptom; the audit is the early one.

2. **Mobile-first verification.** Validate cookie budgets on throttled mobile profiles, where uplink constraints make the cost visible; desktop lab tests on fast connections systematically understate it.

3. **Functional regression testing after deletion.** Removing or rescoping cookies breaks login sessions, CSRF protection, and feature flags in non-obvious ways. Pair every cookie-removal change with an auth-flow and consent-flow test pass on a real device.

4. **Automate the budget in CI.** A simple navigation test asserting total request-cookie bytes stay under threshold prevents the next tag from quietly reintroducing the debt.
