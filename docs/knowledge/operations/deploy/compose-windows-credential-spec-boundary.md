# Docker Compose Windows credential-spec boundary

**Problem**

Windows gMSA credential specs connect containers to domain identity and can grant broad network authority if reused or mis-scoped.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only for Windows services requiring managed domain authentication.

## Controls

- Store specifications in governed config or registry locations.
- Assign distinct gMSA identities by service role.
- Restrict deployment and host access.

## Implementation

- Reference `credential_spec` explicitly and validate the effective Compose model.
- Keep secrets out of environment variables.
- Audit domain use.

## Tests

- Test allowed/denied resources, identity rotation, host restart, scale, and spec removal.

## Gotchas

- This is Windows-specific.
- A credential spec is sensitive configuration.
- Host domain setup is a prerequisite.

## Official sources

- [Official documentation](https://docs.docker.com/reference/compose-file/services/#credential_spec)
