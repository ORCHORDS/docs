# systemd-journald retention, rate limits, and drop observability

**Issue:** Log storms can exhaust storage, while rate limiting can silently remove the evidence needed to diagnose the storm.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Configure journald storage mode, size/free-space limits, and per-service rate limits from incident-evidence requirements and disk budgets. Journald emits a message when messages are dropped, but downstream monitoring must surface it.

## Controls and verification

- Decide explicitly between volatile and persistent storage.
- Reserve disk space for the operating system.
- Tune noisy services at the unit level where supported.
- Alert on dropped-message notices and journal disk pressure.
- Do not disable all limits without a capacity test.
- Generate a controlled log burst and verify retention, drop reporting, rotation, reboot persistence, and forwarding.

## Sources

- [journald.conf](https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html)
- [journalctl](https://www.freedesktop.org/software/systemd/man/latest/journalctl.html)
