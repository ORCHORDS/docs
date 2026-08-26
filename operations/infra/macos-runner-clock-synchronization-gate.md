# macOS runner clock-synchronization gate

**Issue**

Clock drift breaks TLS, signing timestamps, cache freshness, and distributed-test deadlines while appearing as unrelated CI failures.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Keep network time enabled against approved sources.
- Monitor offset and drain runners beyond tolerance.
- Use monotonic clocks for elapsed test budgets.

## Verification

1. Block time sync and induce safe offset in a lab host.
2. Test TLS, signing, and distributed tests.
3. Verify recovery before accepting jobs.

## Gotchas

- Wall-clock correction can jump.
- VM/container clocks follow host behavior.
- Time sync is not timezone configuration.

## Official source

- [Official documentation](https://support.apple.com/guide/mac-help/set-the-date-and-time-automatically-mchlp2996/mac)
