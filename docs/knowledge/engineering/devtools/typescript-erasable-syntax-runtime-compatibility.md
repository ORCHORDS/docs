# TypeScript erasable-syntax runtime compatibility

**Issue:** TypeScript source that type-checks can still fail under runtimes that strip types without transforming TypeScript constructs with runtime meaning.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Enable `erasableSyntaxOnly` for code intended for direct type stripping and combine it with `verbatimModuleSyntax`. Replace enums, runtime namespaces, parameter properties, legacy import assignments, and angle-bracket assertions with erasable equivalents. Keep a runtime execution lane on the exact supported Node version; the compiler flag checks syntax compatibility but does not validate module resolution or runtime APIs.

## Verification

Seed each forbidden construct and verify compilation rejects it. Execute the emitted-or-stripped entry points under every supported runtime/module mode, including type-only imports and package exports.

## Gotchas

- Pin and test the exact supported version; defaults and feature states can change.
- Preserve reproducible evidence without storing secrets or personal data.
- Define rollback before production rollout.

## Official source

- [Primary documentation](https://www.typescriptlang.org/tsconfig/erasableSyntaxOnly.html)
