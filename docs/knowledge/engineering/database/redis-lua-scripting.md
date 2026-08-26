# redis-lua-scripting

**Issue:** Multi-step Redis operations are not atomic without Lua scripting
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Check-and-set operations have race conditions between steps. Need to atomically update multiple keys or perform conditional operations.

## Pattern / Solution
Use EVAL to execute Lua scripts atomically. All keys must be declared in KEYS array. Load script once with SCRIPT LOAD and reuse SHA via EVALSHA for performance.

## Gotchas
- Scripts run synchronously in Redis -- long scripts block all other commands; keep them fast
- EVALSHA fails with NOSCRIPT if Redis restarts -- fall back to EVAL
- Errors in Lua scripts abort the script but do not roll back already-executed Redis calls

## Related
- redis-data-structures
- transaction-isolation-levels
- redis-caching-patterns
