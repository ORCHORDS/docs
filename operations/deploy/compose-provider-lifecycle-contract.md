# Docker Compose provider lifecycle contract

**Issue**

Provider services delegate resource lifecycle to external binaries, expanding deployment behavior beyond container definitions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin and authenticate the provider binary.
- Define idempotent create/delete behavior and durable state ownership.
- Keep generated connection data scoped and secret-safe.

## Verification

1. Test create, update, failure, cancellation, and teardown.
2. Run concurrent projects with name collisions.
3. Verify orphan cleanup and audit logs.

## Gotchas

- Provider support depends on Compose version.
- External resources can outlive the project.
- Provider output is untrusted input to dependent services.

## Official source

- [Official documentation](https://docs.docker.com/reference/compose-file/services/#provider)
