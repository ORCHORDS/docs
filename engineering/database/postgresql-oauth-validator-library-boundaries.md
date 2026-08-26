# PostgreSQL OAuth validator library boundaries

**Issue**

Server-side OAuth validator libraries execute inside PostgreSQL and become part of authentication availability and trust.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Load only reviewed libraries from controlled server paths.
- Pin provider, issuer, audience, clock-skew, and claim mapping policy.
- Roll out with a password or certificate recovery path that is independently tested.

## Verification

1. Test valid, expired, wrong-audience, wrong-issuer, revoked, and malformed tokens.
2. Restart and reload under unavailable identity-provider conditions.
3. Audit mapped database roles and session identity.

## Gotchas

- A valid token is not authorization to every database.
- Library failure can block login.
- Token contents are sensitive and must not enter logs.

## Official source

- [Official documentation](https://www.postgresql.org/docs/current/oauth-authentication.html)
