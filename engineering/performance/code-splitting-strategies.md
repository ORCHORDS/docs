# code-splitting-strategies

**Issue:** Entire application JS loads on every page even when unused
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Code splitting divides a bundle into smaller chunks loaded on demand. Without it, users download code for routes, modals, and features they never visit.

## Pattern / Solution
1. Route-based splitting: dynamic import each route component.\n2. Component-based splitting: lazy-load heavy components (charts, editors, maps).\n3. Vendor splitting: separate node_modules from app code for better caching.\n4. Use React.lazy + Suspense for React component splitting.\n5. Configure Webpack splitChunks or Vite's manualChunks for fine-grained control.

## Gotchas
- Too many small chunks cause HTTP/1.1 queue head-of-line blocking; target 10-30 chunks with HTTP/2.\n- Shared dependencies can end up duplicated across chunks if not extracted to a common chunk.\n- Suspense fallbacks during lazy load can cause CLS if they shift layout.

## Related
dynamic-import-patterns, javascript-bundle-size, http2-multiplexing, tree-shaking-optimization
