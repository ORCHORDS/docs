# npm debug-log retention budget

**Problem**

Repeated failed installs can accumulate debug logs containing paths, registry details, and command context on persistent runners.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use on shared or long-lived developer and CI hosts.

## Controls

- Set `logs-max` and log directory policy explicitly.
- Keep logs outside caches shared across trust boundaries.
- Redact and expire logs before artifact upload.

## Implementation

- Configure npm through controlled user/project scope.
- Collect a failing log only when needed, then delete it with exact paths.
- Monitor directory size.

## Tests

- Generate more failures than the limit, run concurrent npm processes, and scan retained logs for tokens and URLs.

## Gotchas

- Zero disables retention but can hurt diagnosis.
- Log cleanup does not sanitize already uploaded artifacts.
- Config scope can differ under sudo.

## Official sources

- [Official documentation](https://docs.npmjs.com/cli/v11/using-npm/config#logs-max)
