# TypeScript libReplacement resolution policy

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Replacing built-in lib declaration files through packages can change ambient types without an obvious source-code diff.

## When to use

Use only when a project intentionally supplies versioned replacement lib declarations.

## Controls

Pin replacement packages, lock resolution, keep skipLibCheck off in a validation lane, and review ambient surface diffs.

## Implementation

Set libReplacement explicitly, capture traceResolution, compile representative browser and Node targets, and canary the toolchain update.

## Tests

Test clean installs, missing replacements, duplicate globals, editor/compiler agreement, declaration emit, and rollback.

## Gotchas

Type compatibility does not guarantee runtime API availability; replacement packages are supply-chain inputs.

## Official sources

- [Official documentation](https://www.typescriptlang.org/tsconfig/libReplacement.html)
