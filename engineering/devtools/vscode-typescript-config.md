# vscode-typescript-config

**Issue:** TypeScript language server errors differ between editor and build
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Editor uses workspace TS version, build uses project TS version — errors differ.

## Pattern / Solution
Set typescript.tsdk in workspace settings to ./node_modules/typescript/lib. Use Select TypeScript Version > Use Workspace Version from command palette. Ensures editor and tsc use same version.

## Gotchas
- strict in tsconfig must be enabled to catch nullability bugs in editor
- Restart TS server after tsconfig changes

## Related
- vscode-settings-json, vscode-eslint-prettier-setup
