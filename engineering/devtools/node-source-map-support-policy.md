# Node.js source-map support policy

**Problem**

Runtime source-map support changes stack locations and can expose source paths or consume memory in production diagnostics.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when shipped JavaScript has reviewed source maps and mapped stacks improve operations.

## Controls

- Enable explicitly and control whether sources are included.
- Keep maps matched to exact artifacts.
- Redact absolute build paths and source content.

## Implementation

- Configure with the supported module API.
- Publish maps under controlled access.
- Record build/source-map digests.

## Tests

- Test inline/external/missing/stale maps, exceptions, workers, and memory overhead.

## Gotchas

- Maps can reveal source.
- Stale maps mislead responders.
- Enabling after code load has lifecycle nuances.

## Official sources

- [Official documentation](https://nodejs.org/api/module.html#modulesetsourcemapssupportenabled-options)
