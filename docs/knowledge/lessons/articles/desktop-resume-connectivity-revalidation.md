# Desktop resume requires connectivity revalidation, not timer continuation

**Issue**

After sleep or hibernation, elapsed timers, DNS answers, network interfaces, credentials, sockets, and server leases may all be stale even though the process never exited.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Observe suspend, resume, lock, and power-state events through the framework and native platform integration.
- On resume, invalidate monotonic deadlines that crossed suspension and rebuild connectivity from application state.
- Re-resolve endpoints, reauthenticate when required, and replace long-lived sockets with jittered backoff.
- Pause background synchronization before suspend and make replay idempotent.
- Gate user-visible online state on a real application-level probe, not interface presence.

## Verification

1. Suspend during DNS, TLS, upload, database commit, and update download.
2. Resume on the same network, a different network, captive portal, no network, and expired credentials.
3. Advance wall clock across daylight-saving and manual changes while checking monotonic timeout behavior.
4. Create a resume storm across many clients and verify server-friendly jitter.

## Gotchas

- Electron `online`/`offline` events do not establish service reachability.
- Resume notifications can arrive before the network is usable.
- Wall-clock timers are unsafe for measuring elapsed deadlines.

## Official sources

- [Electron powerMonitor](https://www.electronjs.org/docs/latest/api/power-monitor)
- [Microsoft network connectivity guidance](https://learn.microsoft.com/en-us/windows/apps/develop/networking/network-information)
