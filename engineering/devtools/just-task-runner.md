# just-task-runner

**Issue:** Need simple task runner without Makefile complexity or YAML overhead
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams want Make-like simplicity with better cross-platform support and cleaner syntax.

## Pattern / Solution
Install just via cargo or brew. Create justfile at repo root. Recipes with dependencies: build: lint test. Parameters: deploy env=production. just --list shows recipes. Comments become documentation.

## Gotchas
- just is not Make — no pattern rules, no automatic variables
- Shell selection: set shell := [bash, -uc] at top of justfile for explicit shell

## Related
- makefile-developer-tasks, taskfile-patterns
