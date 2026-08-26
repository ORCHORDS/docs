# web-cache-deception-path-confusion

**Issue:** The site's CDN or caching proxy caches any URL that looks static (rules keyed on extensions like `.css`/`.js`/`.ico`, directories like `/assets`, or well-known filenames). The application, however, resolves paths differently — a REST router that ignores unknown trailing segments, a framework that truncates at `;` or `.`, or an origin that decodes `%2f` where the cache does not. An attacker gets a logged-in victim to request `/profile/nonexistent.css`: the cache stores the personalized response because of the extension, the origin returns the victim's private data because the path maps to `/profile`, and the attacker then fetches that same URL and reads the cached copy. Unlike cache poisoning (which injects malicious content), web cache deception leaks other users' data.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How path confusion triggers the leak

1. **Static-extension rules.** The cache rule matches `.css`, `.js`, `.jpg`, `.ico` suffixes; the origin's router ignores the unknown segment and serves `/profile`. Variants include delimiter tricks the framework truncates at: `/profile;foo.css` (Spring matrix variables), `/profile.json` (Rails format handling), and NUL-byte paths (`%00`) on some servers.
2. **Encoded delimiter mismatches.** Encoded characters such as `%23` (`#`) or `%3f` (`?`) are decoded by only one side, so the cache and origin tokenize the URL differently and disagree about which route was requested.
3. **Static-directory rules plus traversal.** Rules caching everything under `/assets` are exploitable when only one layer normalizes encoded dot-segments: `/<static-dir>/..%2f<profile>` or `<profile>%2f%2e%2e%2f<static-dir>` resolves to the profile page at the origin while still matching the static-directory rule at the cache.
4. **Exact-filename rules.** Rules for `robots.txt` or `favicon.ico` are exploitable only when the cache resolves encoded dot-segments, making them lower priority but still in scope.
5. **Retrieval and detection surface.** The attacker simply requests the same crafted URL and reads the victim's data from cache; testers detect the bug with `X-Cache: HIT/MISS` headers, `Cache-Control: public, max-age>0` on an authenticated response, and response-timing differences. Large-scale 2023-2025 studies (Omer Gil and follow-ups) found WCD on PayPal, Shopify, and many other major properties, so assume any personalized page behind a cache is testable.

## What leaks

1. **Full personalized response bodies.** Whatever the dynamic endpoint returns gets cached verbatim — profile details, account identifiers, order history, and personal data that may not even render in the browser but is visible in the raw response.
2. **Tokens in HTML.** CSRF tokens, anti-XSRF metadata, and occasionally session material embedded in page markup become readable by whoever fetches the crafted URL next.
3. **Cache lifetime as exposure window.** The private page remains publicly fetchable for the cache TTL; long TTLs on "static-looking" content turn a one-time victim visit into hours of public availability.

## Defenses

1. **`Cache-Control: no-store` (or `private, no-cache`) on all authenticated dynamic responses.** Set it centrally (middleware/framework default) rather than per-route, because a single forgotten personalized endpoint reopens the hole.
2. **Deny-by-default caching.** Only cache responses that explicitly opt in with `Cache-Control: public, max-age=...`; never derive cacheability from URL extension, path prefix, or filename patterns.
3. **Ensure the CDN cannot override origin `Cache-Control`.** Audit cache rules and Edge Cache TTL settings — an edge rule that forces caching of "static-looking" paths silently defeats origin no-store directives.
4. **Cache deception armor at the edge.** Cloudflare's Cache Deception Armor (a Cache Rules setting) skips caching when the URL's file extension does not match the response `Content-Type` (e.g., `.jpg` returning `text/html`); apply it to dynamic/personalized paths, and note it is weakened if Origin Cache Control or an Edge Cache TTL rule overrides it.
5. **Consistent path parsing between cache and origin.** The origin must reject (404) unknown segments, delimiters, and encoded dot-segments on dynamic routes instead of "recovering" to a parent route; normalize `%2f`, `%23`, `%3f`, `%00`, and `;` identically on both layers.
6. **Monitoring.** Alert on authenticated users requesting odd file extensions appended to dynamic endpoints (`.css` on `/profile/...`) — the attack leaves a distinctive log signature before any data is retrieved.

## Sources

1. **PortSwigger Web Security Academy — Web cache deception.** https://portswigger.net/web-security/web-cache-deception (path confusion taxonomy, Black Hat USA 2024 "Gotta Cache 'em all" research basis, labs).
2. **Cloudflare docs — Cache Deception Armor.** https://developers.cloudflare.com/cache/cache-security/cache-deception-armor/ (extension/Content-Type mismatch check, enabling, limitations).
3. **OWASP — Web Cache Deception.** https://owasp.org/www-community/attacks/ (prevention checklist framing).
