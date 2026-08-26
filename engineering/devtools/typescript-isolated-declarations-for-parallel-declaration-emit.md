# TypeScript isolated declarations for parallel declaration emit

**Issue:** Declaration generation can require whole-program inference, limiting parallel builds and making exported type boundaries implicit.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

TypeScript's `isolatedDeclarations` mode requires sufficient annotations for declaration emit without relying on inference across the whole program. Adopt it when tooling and build architecture benefit from independently generated declarations, not merely to silence errors.

## Controls and verification

- Pin a supporting TypeScript version.
- Add annotations at public boundaries without weakening types.
- Compare emitted declarations before and after.
- Test project references, declaration maps, and package exports.
- Keep a full typecheck as the correctness gate.
- Benchmark whether parallel emit produces material benefit.

## Sources

- [TypeScript: TSConfig isolatedDeclarations](https://www.typescriptlang.org/tsconfig/isolatedDeclarations.html)
- [TypeScript 5.5 release notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-5.html)
