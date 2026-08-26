# Feature-flag expiry and removal proof

**Issue:** Temporary flags become permanent alternate architectures with untested combinations and stale access paths.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Classify release, experiment, operational, permission, and kill-switch flags. Record owner, default, audience, created date, expiry/removal condition, security impact, and fallback. Keep evaluation semantics vendor-neutral where possible. Alert before expiry and remove flag, dead branch, tests, metrics, and configuration together.

## Verification

Test both states before release; enumerate interaction-critical combinations; exercise kill switches; after removal, search code/config/telemetry and prove only the intended path remains.

## Gotchas

A disabled flag can still expose code or endpoints. Client-side flags are not authorization. Stale SDK defaults can differ during outages.

## Sources

- [OpenFeature specification](https://openfeature.dev/specification/)
