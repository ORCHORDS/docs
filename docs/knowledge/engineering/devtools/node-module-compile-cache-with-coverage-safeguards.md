# Node.js module compile cache with coverage safeguards

**Issue:** Recompiling unchanged JavaScript and module graphs increases repeated runner startup time, but indiscriminate compile-cache reuse can reduce coverage precision or create ineffective cross-version caches.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Supported Node.js releases can persist V8 code cache for CommonJS, ECMAScript, and supported TypeScript modules through `module.enableCompileCache()` or `NODE_COMPILE_CACHE`. The first load may be slower; later loads of unchanged module graphs can be faster.

Partition or naturally isolate cache data by exact Node version and runner environment. Node documents the on-disk layout as an implementation detail and does not promise reuse across Node versions. Disable the compile cache for authoritative V8 coverage runs because deserialized functions can produce less precise coverage.

## Operational controls

- Benchmark the actual workload; short-lived jobs may not recover the first-run and transfer cost.
- Keep the cache directory disposable and size-bounded.
- Do not place secrets, source credentials, or unrelated mutable state in it.
- Use `NODE_DISABLE_COMPILE_CACHE=1` for coverage gates that require precision.
- If a parent process needs children to reuse newly generated entries before exit, use the documented flush mechanism where supported.
- Treat portable mode as best effort and test workspace relocation explicitly.

## Verification

1. Measure cold, warm, and disabled startup times with the pinned Node version.
2. Compare test results between cached and uncached execution.
3. Compare coverage with the cache disabled and enabled; retain the disabled result as authoritative.
4. Change Node versions and verify isolation rather than assuming cache compatibility.
5. Remove or corrupt the cache directory and confirm the job still succeeds correctly.

## Sources

- [Node.js: node:module API — module compile cache](https://nodejs.org/api/module.html#module-compile-cache)
- [Node.js: Environment variables](https://nodejs.org/api/cli.html#environment-variables)
