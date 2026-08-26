# TypeScript project references and build-boundary integrity

**Issue:** A monolithic TypeScript project can make typechecking slow and blur component boundaries, while incorrect incremental outputs can hide dependency errors.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

TypeScript project references divide a program into composite projects. Referenced projects expose declaration outputs, and `tsc --build` orders projects and detects which are out of date.

Make each reference represent a real dependency boundary. Referenced projects require `composite`, complete input inclusion, and declaration output. On modern TypeScript versions, review build-mode error continuation semantics and use the documented stop-on-build-errors option where CI must halt downstream work.

## Operational controls

- Pin the TypeScript version across local development and CI.
- Keep source inclusion explicit and validate generated declaration boundaries.
- Treat `.tsbuildinfo` as disposable build metadata, not source evidence.
- Run periodic clean builds to detect stale-output assumptions.
- Prevent downstream packages from importing unexported source internals.
- Publish or check in generated outputs only under a deliberate repository policy.

## Verification

1. Run a clean `tsc -b` and confirm dependency order.
2. Change a public type and verify dependents rebuild and report errors.
3. Change an implementation-only detail and inspect the affected build set.
4. Delete build metadata and compare clean outputs.
5. Test CI failure behavior with an upstream type error.

## Sources

- [TypeScript: Project References](https://www.typescriptlang.org/docs/handbook/project-references.html)
- [TypeScript: TSConfig composite](https://www.typescriptlang.org/tsconfig/composite.html)
- [TypeScript: TypeScript 5.6 build mode](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-6.html)
