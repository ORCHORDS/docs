# compression-gzip-brotli

**Issue:** Text resources are served uncompressed or with suboptimal compression
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Brotli (br) compresses 15-25% better than gzip for text resources. All modern browsers support it over HTTPS. Uncompressed JS/CSS/HTML is a quick win for reducing transfer size.

## Pattern / Solution
1. Enable Brotli on nginx: brotli on; brotli_comp_level 6; brotli_types text/html text/css application/javascript.\n2. Pre-compress static assets at build time for maximum compression level.\n3. Verify with curl -H Accept-Encoding: br -I https://example.com and check Content-Encoding: br.\n4. Fall back to gzip for clients that don't support Brotli.\n5. CDNs (Cloudflare, Fastly) apply Brotli automatically -- verify in response headers.

## Gotchas
- Dynamic content compressed on-the-fly at high Brotli levels is CPU-intensive; use level 4-6 for runtime.\n- Binary assets (images, fonts, WebP) are already compressed; do not attempt gzip/br on them.\n- Compression effectiveness varies: JS compresses ~70%; minified JS still compresses 50%+.

## Related
javascript-bundle-size, cache-control-headers, cdn-cache-strategy
