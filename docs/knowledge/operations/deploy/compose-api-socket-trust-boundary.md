# Docker Compose API socket trust boundary

**Issue**

`use_api_socket` gives a service access to the container engine API and credentials, which is effectively host-level orchestration authority.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Disable it by default and isolate any approved controller service.
- Restrict engine endpoint permissions and repository trust.
- Never expose the socket to fork or unreviewed workflow code.

## Verification

1. Attempt container, image, volume, secret, and host-mount operations.
2. Verify ordinary services cannot reach the API.
3. Audit every engine API call.

## Gotchas

- Container user identity does not neutralize socket authority.
- Read access can expose secrets.
- A proxy reduces scope only if it enforces methods and objects.

## Official source

- [Official documentation](https://docs.docker.com/reference/compose-file/services/#use_api_socket)
