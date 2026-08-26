# web-cache-poisoning-unkeyed-inputs

**Issue:** Web cache poisoning turns a shared cache (CDN, reverse proxy, or the browser cache) into a distribution mechanism for attacker-controlled responses. When an application reflects a request input that the cache does not include in its cache key — an "unkeyed" input such as the X-Forwarded-Host header, an obscure X-Original-URL parameter, or a forgotten cookie — an attacker can store a booby-trapped response under the key of a normal URL (for example the site root). Every subsequent user who requests that URL receives the poisoned response, which typically delivers cross-site scripting payloads to the entire user base with a single request. Unlike cache deception (which leaks one victim's data), cache poisoning is a mass-injection attack: one successful poison can affect thousands of sessions, and it bypasses server-side template sanitization entirely because the payload is injected at the cache layer. Any service fronted by Cloudflare, Fastly, nginx proxy_cache, or Varnish must audit how its cache key is constructed versus which request inputs influence the response.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the Attack Works

1. **Cache key versus response inputs.** A cache stores a response keyed on a subset of the request: usually method, path, and Host, plus whatever the Vary header names. If any other input (header, cookie, query parameter) changes the response body, the cache can be made to serve a response that was generated for the attacker but delivered to everyone.
2. **Unkeyed header reflection.** The classic vector is an application that builds absolute URLs or redirects from X-Forwarded-Host, X-Forwarded-Scheme, X-Original-URL, or X-Rewrite-URL without validating them. The attacker sends one request with a hostile X-Forwarded-Host value that lands in a script src attribute; the cache stores it under the clean URL.
3. **Unkeyed cookie and parameter inputs.** Fat GET parameters, DOM-affecting cookies, or profile-style parameters sometimes alter cached pages while remaining outside the cache key. PortSwigger's methodology calls these "unkeyed inputs" and they are the first thing to enumerate.
4. **Cache key injection.** When the cache parses the key sloppily (ignoring port, normalizing %2e, or splitting on #), two different attacker requests can collide onto one key, letting the attacker control which victim request retrieves the poisoned entry.
5. **Gadget chaining.** A reflection alone is not enough; the attacker needs a gadget — a place where the unkeyed value reaches an HTML attribute, a redirect target, an imported script path, or a header-injectable response — to convert the reflection into script execution.

## Defensive Controls at the Edge

1. **Strip or normalize unkeyed headers at the CDN.** Fastly's own guidance is to remove or overwrite inbound X-Forwarded-Host, X-Original-URL, and similar forwarding headers in edge configuration (VCL, Transform Rules, or Workers) before the request reaches cache or origin. Anything the edge does not forward cannot poison anything.
2. **Do not cache responses with reflected input.** Responses whose body or headers are derived from request-supplied values should carry Cache-Control: no-store or private. Caching is an opt-in decision — make the default uncached and allowlist only known-pure endpoints.
3. **Extend the cache key with Vary where inputs matter.** If a header legitimately changes the response (Accept-Language is the common case), the response must include Vary for it, or the cache must be configured to key on it. Missing Vary is the root cause of most stored cross-user contamination.
4. **Fingerprint the cache key deliberately.** Document, per route, exactly which components form the key (path, query, specific headers, cookie subset) and treat any request input that affects the response but is not in the key as a finding. Configuration-as-code makes this reviewable in pull requests.
5. **Pin cache behavior per route.** Rather than blanket caching rules, define per-path policies: static assets cached with long TTLs, API responses either uncached or keyed on the full authorization context.

## Application-Side Hardening

1. **Never trust forwarded headers from arbitrary requests.** Read X-Forwarded-* values only after confirming the connection came from a known proxy tier; otherwise derive host and scheme from server configuration.
2. **Escape on output, not on input.** Any value that can reach HTML — even infrastructure headers — must go through context-appropriate encoding at the template layer, so even a successful poison degrades to inert text.
3. **Use relative URLs in templates.** Build links from configured base URLs rather than request-derived hostnames; this removes the reflection gadget entirely.
4. **Separate static origin from dynamic origin.** Serve user-influenced content from a different hostname than cached static assets so a poisoning gadget on one origin cannot deliver script to the other.
5. **Rotate and version asset URLs.** Content-hashed asset names make stale or poisoned cache entries self-limiting: a deploy changes the URLs and the poison ages out.

## Detection and Testing

1. **Automated unkeyed-input fuzzing.** Tools such as Param Miner (Burp) enumerate hidden headers and parameters; CI scans should replay key requests with candidate unkeyed inputs and diff the responses to catch reflections before an attacker does.
2. **Hunt with a canary.** Send a request with a random canary value in each candidate header; if the canary appears in the response and the response is cacheable, block the route from caching and file a defect.
3. **Monitor cache hit ratios per route.** A sudden spike in hit rate on a dynamic endpoint often indicates someone experimenting with stored responses.
4. **Alert on poisoning-shaped responses.** Log when a cached response contains a reference to a hostname outside the owned domain set; this is the post-fact signature of a successful poison.
5. **Test both directions.** Verify that a poisoned entry can be purged quickly (CDN purge API exercised in drills) and that purge actually propagates to all POPs, because response time to a live poison is part of the blast radius.
