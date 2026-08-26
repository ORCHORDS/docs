# makefile-developer-tasks

**Issue:** Project setup, build, and test commands not documented or standardized
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
New developers read README to find the right commands; commands change but docs do not.

## Pattern / Solution
Makefile at repo root with targets: make setup, make dev, make test, make lint, make build. Use .PHONY for non-file targets. Add help target with double-hash comments. Works on any Unix system without extra tooling.

## Gotchas
- Makefile requires tabs for indentation (not spaces) — editors may convert silently
- macOS ships with BSD make; GNU make features may not be available without brew install make

## Related
- taskfile-patterns, just-task-runner, vscode-tasks-json
