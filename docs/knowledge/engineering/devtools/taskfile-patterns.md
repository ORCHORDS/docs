# taskfile-patterns

**Issue:** Makefile syntax is arcane; need modern cross-platform task runner
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Makefile does not work well on Windows; YAML is more accessible to the team than Make syntax.

## Pattern / Solution
Install Task (task binary). Create Taskfile.yml. Define tasks with cmds, deps, env, dotenv. Support includes for shared tasks. Cross-platform via OS-conditional commands. task --list shows available tasks.

## Gotchas
- Tasks run with sh by default on Unix, cmd on Windows
- method: checksum caches tasks based on source file checksums to avoid redundant runs

## Related
- makefile-developer-tasks, just-task-runner
