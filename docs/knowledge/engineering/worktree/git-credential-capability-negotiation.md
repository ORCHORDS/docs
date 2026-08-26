# Git credential capability negotiation

**Problem**

Credential helpers and Git negotiate optional fields such as authentication type and state; assuming support can leak fields or break multi-stage authentication.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when implementing or deploying a custom credential helper.

## Controls

- Declare only implemented capabilities.
- Treat continuation state and credentials as secrets.
- Keep helper protocol input/output exact and line-bounded.

## Implementation

- Parse fields without shell evaluation.
- Store state only for the required flow lifetime.
- Fail closed on unknown mandatory behavior.

## Tests

- Test helpers with and without `authtype` and state capability, retries, rejection, and malformed output.
- Scan traces for secrets.

## Gotchas

- Capability support is version-sensitive.
- Helpers are executable trust boundaries.
- Logging protocol exchanges can expose credentials.

## Official sources

- [Official documentation](https://git-scm.com/docs/gitcredentials)
