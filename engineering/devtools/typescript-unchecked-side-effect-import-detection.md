# TypeScript unchecked side-effect import detection

**Issue:** A misspelled side-effect-only import can be silently ignored when TypeScript cannot resolve it, leaving expected polyfills, registrations, or styles absent at runtime.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Enable `noUncheckedSideEffectImports`. Add ambient module declarations only for intentionally loader-handled asset patterns, keep declarations narrow, and make the bundler's resolution aliases match TypeScript. Treat newly exposed unresolved imports as migration findings.

## Verification

Misspell a side-effect import in a fixture and require typecheck failure. Exercise valid CSS or asset imports through both typecheck and production bundling, then run the behavior that depends on registration.

## Gotchas

A blanket `declare module "*"` defeats the control. Successful TypeScript resolution does not prove the runtime loader includes or executes the resource.

## Official sources

- https://www.typescriptlang.org/tsconfig/noUncheckedSideEffectImports.html
- https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-6.html
