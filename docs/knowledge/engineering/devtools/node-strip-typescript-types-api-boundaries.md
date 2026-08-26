# Node.js TypeScript type-stripping API boundaries

**Issue**

`module.stripTypeScriptTypes()` can remove erasable syntax or transform TypeScript constructs at runtime, but its output and source-map behavior are not a stable substitute for a pinned build compiler.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin the exact Node release and mode (`strip` or `transform`).
- Use the API only for controlled tooling inputs; never execute transformed untrusted source.
- Keep production builds on a reviewed compiler pipeline and compare emitted behavior.
- When generating source maps, preserve source identity without leaking host paths.

## Verification

1. Test erasable syntax, enums, namespaces, decorators, JSX, invalid syntax, and source maps.
2. Compare runtime behavior with the supported TypeScript compiler target.
3. Assert deterministic output only within the pinned Node version.

## Gotchas

- Output may change between Node versions.
- Strip mode rejects syntax requiring transformation.
- The API performs transformation, not type checking.

## Official source

- [Official documentation](https://nodejs.org/api/module.html#modulestriptypescripttypescode-options)
