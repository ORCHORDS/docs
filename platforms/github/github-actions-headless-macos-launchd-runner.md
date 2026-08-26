# Headless macOS runner launchd lifecycle

**Issue**

A Mac reachable over SSH is not yet a durable Actions runner. The runner must start after boot under the intended account, survive logout, stop cleanly for maintenance, and expose diagnostics without depending on an interactive Terminal.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use GitHub's `svc.sh` service integration on supported macOS runner releases and inspect the generated launchd definition.
- Run under a dedicated non-admin account with explicit working, tool-cache, and diagnostic directories.
- Keep registration tokens short-lived and remove the runner through GitHub's supported configuration flow before reprovisioning.
- Test boot-start, graceful drain, update, restart, and log collection without a logged-in GUI user.

## Verification

1. Reboot with no console login and dispatch a labeled smoke workflow.
2. Kill the runner listener and confirm launchd recovery matches policy.
3. Drain before OS updates and prove queued jobs route only to compatible capacity.

## Gotchas

- A LaunchAgent and LaunchDaemon have different session and GUI access.
- SSH environment variables do not define launchd's environment.
- Required checks must remain required during maintenance.

## Official sources

- [GitHub configure self-hosted runner as service](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application-as-a-service)
- [Apple launchd](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
