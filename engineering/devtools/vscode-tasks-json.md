# vscode-tasks-json

**Issue:** Build and lint tasks not wired to editor keyboard shortcuts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Devs switch to terminal for build/lint instead of using Ctrl+Shift+B or problem matchers.

## Pattern / Solution
Define tasks in .vscode/tasks.json with type: shell or npm. Use problemMatcher ($tsc, $eslint-stylish) to surface errors in Problems panel. Set isBackground: true for watch tasks.

## Gotchas
- dependsOn lets you chain tasks but order is not guaranteed without dependsOrder: sequence
- Problem matchers must match compiler output format exactly

## Related
- vscode-launch-json-debugging, makefile-developer-tasks
