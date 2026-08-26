# workers-cold-start-optimization

**Issue:** Workers take too long to initialize on first request
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare Workers use V8 isolates with near-zero cold starts (< 1ms). However, large Worker bundles or expensive module-level initialization code can still slow first-request performance.

## Pattern / Solution
1. Keep Worker bundle size small; Cloudflare's limit is 1 MB compressed (10 MB on paid).\n2. Move initialization out of module scope into the fetch handler with lazy initialization.\n3. Use dynamic imports sparingly; they add to bundle complexity.\n4. Avoid top-level await for non-critical initialization.\n5. Use globalThis for caching initialized values across requests within the same isolate.

## Gotchas
- Module-level code runs once per isolate creation; it doesn't run per request.\n- Isolates are recycled when idle; don't rely on globalThis caches to always be warm.\n- Workers bundled with many dependencies approach size limits; audit bundle size with wrangler build.

## Related
cloudflare-workers-performance, workers-cpu-profiling, javascript-bundle-size
