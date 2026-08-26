# html-performance-resource-hints

**Issue:** Critical resources are discovered late during parsing, delaying page load
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A Google Font stylesheet is discovered only after the HTML is parsed; the font blocks text rendering.

## Pattern / Solution
```html
<!-- dns-prefetch: resolve DNS early -->
<link rel="dns-prefetch" href="//api.example.com">

<!-- preconnect: DNS + TCP + TLS handshake early -->
<link rel="preconnect" href="https://fonts.googleapis.com" crossorigin>

<!-- preload: fetch critical resource with high priority -->
<link rel="preload" as="font"  type="font/woff2" crossorigin>
<link rel="preload" as="script" >

<!-- prefetch: fetch low-priority resource for future navigation -->
<link rel="prefetch" >

<!-- modulepreload: preload ES module and its dependencies -->
<link rel="modulepreload" >
```

## Gotchas
- preconnect for more than 4-6 origins reduces benefit (wasted TCP connections)
- preload must be consumed or the browser warns about unused preloads
- crossorigin attribute is required for CORS resources even if same origin

## Related
- `html-web-vitals-lcp.md`
- `prefetching-strategies.md`
