# TypeScript custom export-condition parity

**Issue:** Type checking can resolve a different package export branch from the runtime or bundler and approve APIs that production never loads.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use customConditions only with node16, nodenext, or bundler module resolution. Define the same ordered condition set in TypeScript, the production runtime, bundler, test runner, and declaration generator. Conditions are contract names, not environment detection; document who publishes each branch and ensure a default fallback remains valid.

## Verification

Build a fixture package with visibly different exports for each condition. Compare TypeScript traceResolution, development execution, production bundle, tests, and clean consumer install. Fail when resolved files or declaration surfaces diverge.

## Gotchas

- Pin and verify exact platform versions before rollout.
- Preserve reproducible diagnostics without secrets or personal data.
- Define rollback and stop conditions before production use.

## Official source

- [Primary documentation](https://www.typescriptlang.org/tsconfig/customConditions.html)
