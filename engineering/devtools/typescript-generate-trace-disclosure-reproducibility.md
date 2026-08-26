# TypeScript generateTrace disclosure and reproducibility

**Issue:** TypeScript compiler slowdowns are hard to localize from wall-clock time alone, while performance traces can expose source code and workspace paths and are not a stable interchange format.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Reproduce the slowdown with a pinned TypeScript version, dependency lock, `tsconfig`, clean incremental state, and representative project invocation. Capture `tsc -p <project> --generateTrace <private-directory>` only on approved source, then analyze it with a compatible `@typescript/analyze-trace` version or a browser trace viewer. Store raw traces under the same access and retention controls as source code.

Use traces to identify expensive relations and files, then reduce the case before changing types or compiler settings. Compare changes with repeated warm and cold runs on equivalent hardware. Do not build automation on undocumented trace-event names because the format may change between TypeScript releases.

## Verification

Seed a known expensive type fixture and confirm it appears in analysis, then simplify it and measure the expected improvement without new diagnostics. Verify the trace directory is excluded from commits and public CI artifacts. Repeat after compiler upgrades and keep the reduced source reproduction with the measurement record.

## Gotchas

- A command-line trace may approximate but not exactly reproduce editor-language-server work.
- Trace generation adds overhead; compare like with like.
- Raw traces may include source content and absolute paths.

## Official sources

- [TypeScript performance guidance](https://github.com/microsoft/TypeScript/wiki/Performance)
- [TypeScript performance tracing](https://github.com/microsoft/TypeScript/wiki/Performance-Tracing)
