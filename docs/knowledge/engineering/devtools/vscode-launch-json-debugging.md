# vscode-launch-json-debugging

**Issue:** Developers run apps in terminal and cannot set breakpoints easily
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
No .vscode/launch.json means each dev configures debugging manually or skips it.

## Pattern / Solution
Commit .vscode/launch.json with configurations for node, ts-node, jest, and chrome. Use preLaunchTask to build before debug. Use dollar-workspaceFolder variables for portability.

## Gotchas
- sourceMap must be true for TS breakpoints to work
- skipFiles: [<node_internals>/**] reduces noise in call stack

## Related
- vscode-tasks-json, vscode-typescript-config
