# compression-dictionary-transport

**Issue:** Standard gzip and Brotli compression treat every response as an independent byte stream, which means a returning visitor re-downloads megabytes of redundant framework code, API payloads, and template markup that is nearly identical to what they already cached. Compression Dictionary Transport fixes this by letting the server and client agree on a shared dictionary (a previous response or a static file) and then sending only a delta compressed against it, often cutting transfer sizes for updated resources by 80-98%. Until recently this was an IETF experiment; with RFC 9841 (Shared Brotli) and RFC 9842 (Compression Dictionary Transport) published and Chromium shipping support in stable Chrome (roughly v123-127 rollout, general availability afterward), shared-dictionary compression became a real 2025-2026 frontend performance lever, and Cloudflare now offers it as a product feature. Teams that skip it pay for the same bytes on every deploy.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the mechanism works

1. **Dictionary negotiation.** The client advertises dictionaries it holds via the Available-Dictionary request header (a hash-based identifier of a cached or explicitly stored dictionary), and the server responds with a dictionary-compressed body plus Dictionary-ID so the client knows which dictionary to use for decompression. This is pure HTTP negotiation; no JavaScript decompression step is needed when the browser supports it.
2. **Use-As-Dictionary declaration.** A response can carry the Use-As-Dictionary response header, telling the browser "store this resource and offer it as a dictionary for future requests matching this path pattern." This lets a v1 bundle automatically become the dictionary for the v2 bundle, so each deploy only transmits the delta.
3. **Two registered encodings.** RFC 9842 registers content encodings for both Shared Brotli (sbr) and Shared Zstandard (sz) built on RFC 9841's shared Brotli container format. Zstd generally compresses and decompresses faster at similar ratios; shared Brotli squeezes slightly smaller deltas for text-heavy assets. Either is a massive win over identity or plain gzip for repeat visits.
4. **Static dictionaries for first visits.** Dictionaries do not have to be old versions of the same file. You can ship a static dictionary (for example, a common framework build) referenced from the root HTML, so even a first-time visitor decompresses your JS against a dictionary fetched once and then reused across every chunk that shares that vocabulary.

## Where it pays off most

1. **Frequently redeployed JS bundles.** Hashed bundle filenames change every release, but 90-99% of the code is identical between versions. Delta-compressing the new bundle against the cached old one routinely turns a 300 KB chunk into a 5-20 KB transfer, which compounds across every route-level chunk a SPA loads.
2. **Repetitive JSON API responses.** Feeds, tables, and search results re-serialize the same schema with slightly different values on every poll. A dictionary built from a previous response lets the server emit only the changed values, shrinking payloads for dashboards and infinite-scroll apps that poll aggressively.
3. **HTML and template-heavy pages.** Server-rendered pages from the same layout share enormous boilerplate (head, nav, inline bootstrap CSS). Google's own case studies on dictionary compression of HTML showed multi-fold size reductions for navigations within a site.

## Implementation checklist

1. **Pick assets with stable vocabulary.** Start with your main JS bundle and your largest JSON endpoint, not everything. Measure the delta size after adding Use-As-Dictionary headers and compare against the uncompressed baseline in Chrome DevTools' network panel, which shows the dictionary transfer in the Size column.
2. **Serve the dictionary from the same origin or CORS-enabled storage.** Dictionaries must be reliably cacheable and SameOrigin (or properly CORS-configured), otherwise the browser will silently refuse to advertise them. Verify the Available-Dictionary header actually appears on subsequent requests before assuming the setup works.
3. **Fall back gracefully.** Safari support is only emerging (WebKit previews/flags) and Firefox has been experimental, so the server must negotiate: if no Available-Dictionary header arrives, send normal Brotli or gzip. Never make dictionary delivery a hard dependency for rendering.
4. **Regenerate dictionaries on deploy.** For static dictionaries, generate the dictionary file as part of the CI build (with a tool such as the shared-dictionary helpers in the Dictcompress/Chrome tooling family), version it alongside the bundle, and update the declaration in the HTML. A stale dictionary reference means the client ignores it and you silently lose the win.
5. **Measure with real users, not just lab.** Track transfer size and LCP for returning visitors separately from first visits; the benefit concentrates in the returning cohort, so an all-users average will understate it.

## Pitfalls and cautions

1. **CPU cost of dictionary construction.** Building an optimal shared dictionary is expensive offline work; do it in CI, not at request time, unless your CDN (Cloudflare Shared Dictionaries) does it for you at the edge.
2. **Compression bomb surface.** Dictionary-compressed responses can expand dramatically; make sure intermediaries and your CDN enforce sane expansion limits so a small delta cannot decompress into an unbounded stream.
3. **Cache-key hygiene.** A dictionary tied to a specific bundle hash must be evicted when that bundle is evicted, or you accumulate orphaned dictionaries. Use deterministic naming and short TTLs for dictionary resources you expect to churn.
