# api-response-compression

**Issue:** API JSON responses are large and slow to transfer
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
JSON API responses can be several hundred KB for complex datasets. Gzip/Brotli compression typically reduces JSON size by 60-80%.

## Pattern / Solution
1. Enable compression middleware in Express: app.use(compression()).\n2. Set Accept-Encoding: gzip, br header in API clients.\n3. For Cloudflare Workers, use the Compression Streams API.\n4. Pre-compress cached responses: store compressed bytes in Redis.\n5. Consider MessagePack or Protobuf for structured data (additional 20-30% reduction vs compressed JSON).

## Gotchas
- Don't compress small responses (< 1 KB) -- compression overhead exceeds savings.\n- Compressing already-compressed content (images, WebP, binary) increases size.\n- Set Vary: Accept-Encoding header so CDNs cache compressed and uncompressed versions separately.

## Related
api-response-caching, compression-gzip-brotli, cdn-cache-strategy
