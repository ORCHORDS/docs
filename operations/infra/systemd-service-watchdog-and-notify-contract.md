# systemd service watchdog and notification contract

**Issue:** A service can remain running while its event loop is deadlocked, so process existence alone is not a sufficient health signal.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

For compatible services, systemd can supervise application liveness using `WatchdogSec=` and readiness/liveness notifications through `sd_notify`. The service must send `READY=1` when initialization is complete and periodic `WATCHDOG=1` notifications within the negotiated interval.

A watchdog is only useful if notifications originate from the critical execution path. A separate healthy thread that continues pinging while the application is wedged creates false assurance.

## Operational controls

- Set `Type=notify` only for software that implements the notification contract correctly.
- Derive the watchdog interval from measured worst-case healthy pauses.
- Configure restart limits and backoff to avoid a crash loop.
- Keep external functional monitoring; host supervision cannot prove end-to-end service behavior.
- Log startup, readiness, watchdog timeout, and restart reasons.
- Test notification permissions and process attribution.

## Verification

1. Confirm readiness is withheld until dependencies and listeners are usable.
2. Block the critical event loop and verify watchdog recovery.
3. Simulate a long healthy operation and confirm it does not false-trigger.
4. Inspect restart-rate limiting during repeated failures.
5. Compare systemd state with an external request probe.

## Sources

- [systemd.service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)
- [sd_notify](https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html)
- [systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)
