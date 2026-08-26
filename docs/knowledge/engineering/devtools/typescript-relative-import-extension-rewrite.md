# TypeScript relative import extension rewriting

**Issue:** Source imports ending in TypeScript extensions can work in a type-stripping development runtime but remain unresolvable in emitted JavaScript.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

For TypeScript 5.7 or later, enable `rewriteRelativeImportExtensions` when relative `.ts`, `.tsx`, `.mts`, and `.cts` specifiers must become their JavaScript equivalents in emitted files. Keep module and module-resolution settings aligned with the production runtime, and distinguish relative imports from package aliases or bare specifiers, which this option does not rewrite. Validate package exports, declaration output, source maps, and dual ESM/CommonJS builds independently.

Do not use rewriting to conceal a mismatch between development and production module graphs. Run the source under its development loader and execute the emitted package exactly as consumers will load it.

## Verification

Build fixtures for every supported source extension, nested relative paths, dynamic imports, declarations, package exports, and imports that must remain unchanged. Install the produced package into a clean consumer and run it under each supported Node version and module mode. Fail CI on emitted references to unavailable TypeScript source.

## Gotchas

- The option rewrites relative paths, not arbitrary aliases.
- Runtime behavior still depends on package type and export maps.
- Pin TypeScript because module emit behavior evolves.

## Official source

- [TypeScript rewriteRelativeImportExtensions](https://www.typescriptlang.org/tsconfig/rewriteRelativeImportExtensions.html)
