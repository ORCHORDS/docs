# Node test force-exit diagnostic boundary

**Issue**

Forcing the Node test runner to exit can make CI finish while hiding leaked handles and incomplete cleanup.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Keep force-exit disabled in authoritative CI.
- Use it only in a diagnostic lane after collecting open-handle evidence.
- Fix resource ownership and teardown rather than normalizing leaks.

## Verification

1. Seed leaked servers, timers, workers, and sockets.
2. Compare natural completion with forced exit.
3. Verify reports flush before any diagnostic termination.

## Gotchas

- Forced exit can truncate reporters.
- Leaks can create cross-test interference.
- Job timeout remains a final safety net.

## Official source

- [Official documentation](https://nodejs.org/api/test.html)
