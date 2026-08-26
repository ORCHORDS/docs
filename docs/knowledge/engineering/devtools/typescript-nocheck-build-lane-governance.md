# TypeScript noCheck build-lane governance

**Issue:** Fast emit-only builds can accidentally replace type safety rather than complementing it.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

If `--noCheck` is used to accelerate emission, keep a separate required `tsc --noEmit` or build-mode type-check lane on the same commit. Separate build-info files when lanes can run concurrently, and use `isolatedDeclarations` when declaration generation must remain syntactic. Pin TypeScript, surface diagnostics from the checking lane, and prohibit publishing if that lane did not succeed. Treat noCheck as scheduling separation, not evidence of correctness.

## Verification

Inject a known type error that still emits and verify the emit lane succeeds while the required type lane blocks release. Confirm generated declarations match the checked source and concurrent lanes do not overwrite incremental state.

## Gotchas

- Confirm behavior against the exact deployed version; feature state and defaults can change.
- Preserve logs and artifacts needed to reproduce failures without recording secrets or personal data.
- Roll out behind a reversible change and define the rollback trigger before production use.

## Official source

- [Primary documentation](https://www.typescriptlang.org/tsconfig/noCheck.html)
