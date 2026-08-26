# macOS runner Rosetta architecture routing

**Issue**

Rosetta can make x86_64 tools run on Apple silicon, but mixed architecture caches and dependency resolution can hide unsupported native builds.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Label native architecture and Rosetta capability separately.
- Keep cache keys and artifacts architecture-specific.
- Run required native arm64 validation even when compatibility jobs pass.

## Verification

1. Inspect process and binary architectures.
2. Test native and translated dependency installs.
3. Disable Rosetta on a canary.

## Gotchas

- Translated success is not native support.
- Rosetta availability is host state.
- Universal binaries contain multiple slices.

## Official source

- [Official documentation](https://support.apple.com/en-us/102527)
