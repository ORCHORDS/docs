# Node.js SEA embedded-asset boundaries

**Problem**

Single executable applications can embed assets, but unchecked names, encodings, and extraction paths can create nondeterminism or overwrite risk.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when distributing a Node SEA that needs immutable templates, WASM, or configuration.

## Controls

- Declare assets in the SEA configuration and pin Node.
- Treat embedded bytes as build inputs with recorded digests.
- Never derive extraction paths directly from untrusted asset names.

## Implementation

- Read with `getAsset`, `getAssetAsBlob`, or copied asset APIs according to lifetime needs.
- Decode explicitly and validate format before use.
- Prefer in-memory consumption.

## Tests

- Test missing assets, binary/text encoding, mutation of copied buffers, reproducible builds, and hostile extraction names.

## Gotchas

- Assets increase executable size.
- Embedded content is readable, not secret.
- API behavior is version-bound.

## Official sources

- [Official documentation](https://nodejs.org/api/single-executable-applications.html)
