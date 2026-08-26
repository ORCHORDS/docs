# Docker Compose model-provider boundary

**Issue**

Compose model resources can connect services to AI model providers, creating credential, endpoint, and portability dependencies outside container images.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin provider/model configuration and scope credentials.
- Treat model output as untrusted input.
- Keep a deterministic test double for required checks.

## Verification

1. Test provider outage, quota, timeout, malformed output, and credential rotation.
2. Verify CI uses approved mock or isolated account.
3. Audit resolved endpoints.

## Gotchas

- Model support depends on Compose implementation.
- Provider behavior can change without image changes.
- Secrets must not enter resolved configuration logs.

## Official source

- [Official documentation](https://docs.docker.com/reference/compose-file/models/)
