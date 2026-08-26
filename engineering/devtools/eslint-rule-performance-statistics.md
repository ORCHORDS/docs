# ESLint rule-performance statistics governance

**Issue**

Slow lint rules can dominate feedback time, but optimization decisions made without per-rule evidence can weaken coverage.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Collect ESLint statistics on representative files with pinned rules and plugins.
- Set performance budgets separately from correctness severity.
- Optimize configuration or rule implementation before disabling valuable checks.

## Verification

1. Measure cold/warm, serial/concurrent, and cache-disabled runs.
2. Confirm findings remain identical after tuning.
3. Track p50 and tail time across repository partitions.

## Gotchas

- Statistics add measurement overhead.
- One pathological file can hide behind averages.
- Rule timing changes with parser and type information.

## Official source

- [Official documentation](https://eslint.org/docs/latest/use/command-line-interface#--stats)
