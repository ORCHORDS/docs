# Node.js dotenv file-loading boundary

**Problem**

Loading environment files mutates process configuration from filesystem content and can silently preserve or override values according to API semantics.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use during controlled bootstrap for non-secret or locally protected configuration.

## Controls

- Resolve an exact approved path.
- Restrict file permissions and never commit production secrets.
- Validate required values after load.

## Implementation

- Call the supported process API before consumers initialize.
- Keep environment precedence documented.
- Fail closed on malformed/missing required config.

## Tests

- Test missing, malformed, duplicate, multiline, existing environment, permissions, and workers.

## Gotchas

- Process environment is global mutable state.
- Values can leak to children/logs.
- Dotenv is not a secret manager.

## Official sources

- [Official documentation](https://nodejs.org/api/process.html#processloadenvfilepath)
