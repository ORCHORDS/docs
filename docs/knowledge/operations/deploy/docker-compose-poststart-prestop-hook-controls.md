# Docker Compose post-start and pre-stop hook controls

**Issue**

Compose lifecycle hooks run privileged operational commands around container startup and shutdown, but exact timing and completion relative to the main process require explicit idempotency and failure policy.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Keep hook commands in version-controlled images or configuration and run with least privilege.
- Make post-start initialization idempotent and protect it with an application readiness gate.
- Give pre-stop work a bounded duration below the platform termination budget.
- Do not pass secrets in command arguments or hook logs.

## Verification

1. Start, restart, stop, kill, and recreate services and record hook order and exit behavior.
2. Force each hook to fail or hang and verify deployment response.
3. Run concurrent replicas against shared initialization state.

## Gotchas

- Post-start timing is not guaranteed relative to the entrypoint.
- Pre-stop cannot run after abrupt host or process loss.
- Hooks do not replace application retry or durable shutdown design.

## Official source

- [Official documentation](https://docs.docker.com/compose/how-tos/lifecycle/)
