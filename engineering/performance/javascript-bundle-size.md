# javascript-bundle-size

**Issue:** Large JS bundles delay parse, compile, and execution
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
JavaScript is the most expensive resource per byte -- it must be downloaded, parsed, compiled, and executed. A 1 MB JS bundle takes 5-10x longer to process than a 1 MB image.

## Pattern / Solution
1. Analyze bundles with webpack-bundle-analyzer or vite-bundle-visualizer.\n2. Set a performance budget: < 170 KB gzipped for initial JS.\n3. Remove unused dependencies; audit with npm-check or depcheck.\n4. Replace heavy libraries with lighter alternatives.\n5. Enable minification (Terser) and tree shaking in production builds.

## Gotchas
- Gzip size is what travels over the wire; parse/execute cost relates to uncompressed size.\n- Dynamic imports split the bundle but add round trips; balance splitting with preloading.\n- Polyfills for modern browsers waste bytes; use @babel/preset-env with targets configured.

## Related
code-splitting-strategies, tree-shaking-optimization, dead-code-elimination, compression-gzip-brotli
