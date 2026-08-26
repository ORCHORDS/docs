# ESLint ignored-file warning contract

**Problem**

Linting a directly named ignored file can warn, fail through warning budgets, or become silent depending on configuration.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when CI constructs explicit file lists or change-based lint inputs.

## Controls

- Set ignored-file behavior deliberately and keep required CI fail-closed.
- Do not use `--no-warn-ignored` to hide path-selection bugs.
- Assert the selected file count before invoking ESLint.

## Implementation

- Generate file lists with NUL-safe tooling.
- Separate intentional ignore policy from missing-path policy.
- Keep max-warnings explicit.

## Tests

- Name ignored, unignored, missing, and out-of-root files; verify exit codes and diagnostics.
- Test flat-config global ignores.

## Gotchas

- Directory ignores and file ignores differ.
- Warnings can become failures under `--max-warnings 0`.
- Shell globbing changes inputs.

## Official sources

- [Official documentation](https://eslint.org/docs/latest/use/command-line-interface#--no-warn-ignored)
