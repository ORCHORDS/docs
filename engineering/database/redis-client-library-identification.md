# Redis client library identification contract

**Issue**

Unidentified client libraries make connection incidents and phased compatibility changes harder to attribute.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Send `CLIENT SETINFO LIB-NAME` and `LIB-VER` from libraries, not user secrets.
- Use stable bounded values and track server support.
- Treat identification as telemetry, not authentication.

## Verification

1. Inspect CLIENT LIST metadata.
2. Test old servers and reconnects.
3. Reject high-cardinality dynamic versions.

## Gotchas

- Servers may ignore unsupported info.
- Values are visible to administrators.
- Identity does not grant trust.

## Official source

- [Official documentation](https://redis.io/docs/latest/commands/client-setinfo/)
